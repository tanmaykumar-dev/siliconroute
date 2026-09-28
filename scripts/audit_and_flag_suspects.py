"""Audit all database runs for hardware identity suspect flagging and physics notes.

Rule:
- identity_suspect: ONLY with evidence of a swap:
  1. Inverted verification sessions where dml:0 ran faster than dml:1 on compute-bound models:
     Sessions 156, 158, 167, 168, 169, 170.
  2. Any dml:0 run faster than dml:1 baseline for the same model/batch (and vice versa).
- physics_note: records when implied compute exceeds datasheet theoretical peaks
  due to algorithm shortcuts (e.g. Winograd / FFT convolution), kept strictly
  as a note, NOT an identity flag.
"""

from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select
from app.db import AIModel, Decision, Device, Run, engine, init_db
from app.predictor import fit_device
from app.router import compute_decision_statistics


def run_audit(dry_run: bool = False):
    init_db()
    con = sqlite3.connect("data/siliconroute.db")
    cur = con.cursor()

    # 1. Fetch current flags for before/after comparison
    old_flags = {row[0]: row[1] for row in con.execute("SELECT id, identity_suspect FROM run;").fetchall()}

    # 2. Build verified baseline medians per (model_id, batch) for dml:0 and dml:1
    # Exclude known inverted sessions
    inverted_sessions = {156, 158, 167, 168, 169, 170}

    dml1_medians = {}
    for m_id, batch, med in con.execute(f"""
        SELECT ai_model_id, batch, AVG(median_ms)
        FROM run
        WHERE device_id = 3 AND session_id NOT IN ({','.join(str(s) for s in inverted_sessions)})
        GROUP BY ai_model_id, batch
    """).fetchall():
        dml1_medians[(m_id, batch)] = med

    dml0_medians = {}
    for m_id, batch, med in con.execute(f"""
        SELECT ai_model_id, batch, AVG(median_ms)
        FROM run
        WHERE device_id = 2 AND session_id NOT IN ({','.join(str(s) for s in inverted_sessions)})
        GROUP BY ai_model_id, batch
    """).fetchall():
        dml0_medians[(m_id, batch)] = med

    # 3. Evaluate all runs
    all_runs = con.execute("""
        SELECT r.id, r.session_id, r.device_id, d.key, m.name, r.batch, r.median_ms,
               m.flops_per_sample, r.ai_model_id
        FROM run r
        JOIN device d ON r.device_id = d.id
        JOIN aimodel m ON r.ai_model_id = m.id
        ORDER BY r.id;
    """).fetchall()

    new_suspects = {}
    physics_notes = {}

    for rid, sid, did, dkey, mname, batch, med_ms, flops_sample, mid in all_runs:
        total_flops = (flops_sample or 0) * batch
        gflops = (total_flops / (med_ms * 1e6)) if med_ms > 0 else 0

        # Physics check: dml:0 convolution exceeding ~600 GFLOP/s
        if dkey == "dml:0" and gflops > 600.0:
            physics_notes[rid] = (
                f"Winograd hypothesis: implied {gflops:.1f} GFLOP/s exceeds RDNA2 2-CU peak (563 GFLOP/s) "
                f"due to reduced multiplication complexity in convolution"
            )

        # Identity swap check:
        # A. Known inverted verification sessions where adapter order reversed
        if sid in inverted_sessions and dkey in ("dml:0", "dml:1"):
            t_rtx = dml1_medians.get((mid, batch), 0)
            t_rad = dml0_medians.get((mid, batch), 0)
            new_suspects[rid] = (
                f"Inverted session {sid}: {dkey} ran at opposite GPU speed "
                f"({med_ms:.3f} ms vs RTX {t_rtx:.3f} ms, Radeon {t_rad:.3f} ms)"
            )
            continue

        # B. Direct comparison check: dml:0 running at RTX speed
        t_rtx = dml1_medians.get((mid, batch))
        t_rad = dml0_medians.get((mid, batch))
        if dkey == "dml:0" and t_rtx is not None and t_rad is not None and (t_rad > t_rtx * 1.5):
            # Compute-bound model where RTX is physically faster
            if med_ms < t_rtx * 1.2 and med_ms < t_rad * 0.5:
                new_suspects[rid] = (
                    f"dml:0 ran at RTX speed ({med_ms:.3f} ms vs RTX {t_rtx:.3f} ms, Radeon {t_rad:.3f} ms)"
                )
        elif dkey == "dml:1" and t_rtx is not None and t_rad is not None and (t_rad > t_rtx * 1.5):
            if med_ms > t_rad * 0.8 and med_ms > t_rtx * 2.0:
                new_suspects[rid] = (
                    f"dml:1 ran at Radeon speed ({med_ms:.3f} ms vs RTX {t_rtx:.3f} ms, Radeon {t_rad:.3f} ms)"
                )

    print("=" * 110)
    print("HARDWARE IDENTITY & PHYSICS AUDIT RESULTS")
    print("=" * 110)
    print(f"Total runs evaluated: {len(all_runs)}")
    print(f"Old identity_suspect count: {sum(1 for v in old_flags.values() if v)}")
    print(f"New identity_suspect count: {len(new_suspects)}")
    print(f"Physics notes added:       {len(physics_notes)}")

    # Print changes
    print("\n--- RUNS UN-FLAGGED (REVERTED TO TRUSTED RADEON RUNS) ---")
    unflagged = [rid for rid, old_v in old_flags.items() if old_v and rid not in new_suspects]
    for rid in unflagged:
        run_info = next(r for r in all_runs if r[0] == rid)
        _, sid, _, dkey, mname, batch, med_ms, flops_s, _ = run_info
        gflops = ((flops_s or 0) * batch / (med_ms * 1e6)) if med_ms > 0 else 0
        p_note = physics_notes.get(rid, "None")
        print(f"  Run {rid:>4} | Sess {sid:>3} | {dkey:<5} | {mname:<14} B={batch:>2} | {med_ms:>8.3f} ms | {gflops:>6.1f} GFLOP/s")
        print(f"         Physics note: {p_note}")

    print("\n--- FINAL IDENTITY SUSPECT RUNS (VERIFIED SWAPS ONLY) ---")
    for rid, reason in sorted(new_suspects.items()):
        run_info = next(r for r in all_runs if r[0] == rid)
        _, sid, _, dkey, mname, batch, med_ms, _, _ = run_info
        print(f"  Run {rid:>4} | Sess {sid:>3} | {dkey:<5} | {mname:<14} B={batch:>2} | {med_ms:>8.3f} ms | Reason: {reason}")

    if not dry_run:
        # Reset all flags
        cur.execute("UPDATE run SET identity_suspect = 0, physics_note = NULL;")
        # Apply new suspect flags
        for rid in new_suspects:
            cur.execute("UPDATE run SET identity_suspect = 1 WHERE id = ?;", (rid,))
        # Apply physics notes
        for rid, note in physics_notes.items():
            cur.execute("UPDATE run SET physics_note = ? WHERE id = ?;", (note, rid))

        con.commit()
        print("\nDatabase updated successfully.")

    con.close()

    if not dry_run:
        # Refit predictor models with updated suspect exclusion
        print("\nRefitting hardware predictor models with clean suspect filtering...")
        with Session(engine) as s:
            devices = s.exec(select(Device).where(Device.is_available == True)).all()
            for dev in devices:
                try:
                    fit = fit_device(s, dev.id, target="latency")
                    print(f"  {dev.key:<6} Form={fit.model_form:<12} LOO={fit.loo_mape_pct:.1f}% n={fit.n_samples} compute={fit.compute_gflops} GFLOP/s")
                except Exception as exc:
                    print(f"  {dev.key:<6} fit skipped: {exc}")

            # Recompute router statistics for decisions 93-116
            print("\nRecomputing router decision statistics for decisions 93-116...")
            stats = compute_decision_statistics(s, decision_ids=list(range(93, 117)))
            sr = stats["siliconroute"]
            print(f"SiliconRoute accuracy: {sr['wins']}/{sr['total']} ({sr['accuracy_pct']}%), Mean regret: {sr['mean_regret_pct']}%, P90 regret: {sr['p90_regret_pct']}%")


if __name__ == "__main__":
    run_audit(dry_run=False)
