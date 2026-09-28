"""Phase 5.2 Workload-Aware Router Evaluation.

Executes 24 verified routing decisions:
- 8 sustained (warm steady-state median)
- 8 idle_loaded (warm session after 10s idle sleep)
- 8 cold_start (session creation + first inference after 10s idle sleep)

Shuffled in random order across GPU-favoured large models and CPU-favoured small models.
Every device (cpu, dml:0, dml:1) is measured in every decision.

Reports:
1. Per-decision breakdown with chosen source (measured vs ratio) and actual measured times.
2. Baseline comparison (same 24 decisions) with exact counts.
3. Accuracy and mean/p90 regret per workload.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.db import AIModel, Decision, Device, engine, init_db
from app.router import compute_decision_statistics, execute_verification, route_model


def build_decision_list() -> list[dict]:
    """Build 24 decisions: 8 sustained + 8 idle_loaded + 8 cold_start across 8 configurations."""
    configs = [
        ("mlp-256w-4l", 1),
        ("mlp-256w-4l", 8),
        ("mlp-1024w-4l", 1),
        ("mlp-3072w-4l", 1),
        ("mlp-3072w-4l", 8),
        ("conv-16c-4l", 1),
        ("conv-96c-4l", 1),
        ("conv-96c-4l", 8),
    ]

    decisions = []
    for mname, batch in configs:
        decisions.append({"model": mname, "batch": batch, "workload": "sustained"})
        decisions.append({"model": mname, "batch": batch, "workload": "idle_loaded"})
        decisions.append({"model": mname, "batch": batch, "workload": "cold_start"})

    # Shuffle with fixed seed for honest reproducibility
    random.seed(42)
    random.shuffle(decisions)
    return decisions


def run_evaluation():
    init_db()
    decisions_to_run = build_decision_list()

    with Session(engine) as session:
        models = {m.name: m for m in session.exec(select(AIModel)).all()}
        devices = {d.id: d for d in session.exec(select(Device)).all()}

        print("=" * 115)
        print("SILICONROUTE PHASE 5.2: 24 WORKLOAD-AWARE VERIFIED DECISIONS")
        print("  8 Sustained  |  8 Idle-Loaded (Warm + 10s Idle)  |  8 Cold-Start (Create + 1st Inf)")
        print("=" * 115)

        results = []
        for i, spec in enumerate(decisions_to_run, 1):
            model = models[spec["model"]]
            workload = spec["workload"]
            batch = spec["batch"]

            # Idle sleep before cold/idle decisions to guarantee device enters low-power P8 state
            if workload in ("idle_loaded", "cold_start"):
                print(f"\n[{i}/24] Idling 10 s for GPU P8 low-power state...")
                time.sleep(10.0)

            tag = f"[{i}/24] {model.name} B={batch} {workload}"
            print(f"{tag}: routing...", end=" ", flush=True)

            decision_dict = route_model(
                session=session,
                model_id=model.id,
                batch=batch,
                mode="fastest",
                workload=workload,
                allow_explore=False,
            )

            dec_record = execute_verification(
                session=session,
                decision_dict=decision_dict,
                workload=workload,
            )

            chosen_dev = devices.get(dec_record.chosen_device_id)
            best_dev = devices.get(dec_record.best_device_id_actual)
            status = "WIN" if dec_record.was_best else f"LOSS (regret {dec_record.regret_pct:.1f}%)"
            print(f"-> {chosen_dev.key if chosen_dev else '?'} | "
                  f"actual={dec_record.actual_ms:.3f} ms | "
                  f"best={best_dev.key if best_dev else '?'} | {status}")

            ctx = json.loads(dec_record.context_json) if dec_record.context_json else {}
            cands = json.loads(dec_record.candidates_json) if dec_record.candidates_json else []
            m_times = {int(k): v for k, v in ctx.get("measured_times_ms", {}).items()}

            results.append({
                "id": dec_record.id,
                "model": model.name,
                "batch": batch,
                "workload": workload,
                "chosen": chosen_dev.key if chosen_dev else "?",
                "best": best_dev.key if best_dev else "?",
                "actual_ms": dec_record.actual_ms,
                "was_best": dec_record.was_best,
                "regret_pct": dec_record.regret_pct,
                "candidates": cands,
                "measured_times": m_times,
            })

        # -------------------------------------------------------------
        # 1. Per-Decision Summary Table
        # -------------------------------------------------------------
        print("\n" + "=" * 115)
        print(f"{'ID':<4} | {'Model':<14} | {'B':>2} | {'Workload':<12} | {'Chosen':<6} | {'Source':<18} | "
              f"{'Pred(ms)':>8} | {'Act(ms)':>8} | {'Best':>6} | {'Match':>5} | {'Regret':>7}")
        print("-" * 115)
        for r in results:
            pred_ms = 0.0
            source_str = "?"
            for c in r["candidates"]:
                if c["device_key"] == r["chosen"]:
                    pred_ms = c.get("effective_latency_ms", 0.0)
                    source_str = c.get("source", "?")
                    break
            print(f"{r['id']:<4} | {r['model']:<14} | {r['batch']:>2} | {r['workload']:<12} | "
                  f"{r['chosen']:<6} | {source_str:<18} | {pred_ms:>8.3f} | {r['actual_ms']:>8.3f} | "
                  f"{r['best']:>6} | {'Yes' if r['was_best'] else 'No':>5} | "
                  f"{r['regret_pct']:>6.1f}%")

        # -------------------------------------------------------------
        # 2. Baseline Comparison Table (Same 24 Decisions)
        # -------------------------------------------------------------
        print("\n" + "=" * 115)
        print("BASELINE COMPARISON (same 24 decisions)")
        print("=" * 115)

        decision_ids = [r["id"] for r in results]
        stats = compute_decision_statistics(session, decision_ids=decision_ids)
        n = stats["total_verified"]
        sr = stats["siliconroute"]

        print(f"\nEvaluated on the {n} decisions of this run:")
        print(f"\n{'Strategy':<20} | {'Wins':>5} | {'Total':>5} | {'Measured In':>11} | "
              f"{'Accuracy':>8} | {'MeanReg':>8} | {'P90Reg':>8}")
        print("-" * 90)
        print(f"{'SiliconRoute':<20} | {sr['wins']:>5} | {sr['total']:>5} | "
              f"{'':>11} | {sr['accuracy_pct']:>7.1f}% | {sr['mean_regret_pct']:>7.2f}% | "
              f"{sr['p90_regret_pct']:>7.2f}%")

        for name, key in [("Always-CPU", "always_cpu"), ("Always-RTX", "always_rtx"),
                          ("Fit-Only Router", "fit_only_router")]:
            b = stats["baselines"][key]
            m_in = b.get("measured_in", "")
            print(f"{name:<20} | {b['wins']:>5} | {b['total']:>5} | {m_in:>11} | "
                  f"{b['accuracy_pct']:>7.1f}% | {b['mean_regret_pct']:>7.2f}% | "
                  f"{b['p90_regret_pct']:>7.2f}%")

        ort = stats["baselines"]["ort_policy"]
        print(f"{'ORT Policy':<20} | {ort['status']}: {ort['reason']}")

        # -------------------------------------------------------------
        # 3. Accuracy and Regret Per Workload Breakdown
        # -------------------------------------------------------------
        print("\n" + "=" * 115)
        print("PER-WORKLOAD BREAKDOWN (8 decisions each)")
        print("=" * 115)
        print(f"\n{'Workload':<16} | {'Wins':>5} | {'Total':>5} | {'Accuracy':>8} | {'MeanReg':>8} | {'P90Reg':>8}")
        print("-" * 65)

        per_wl = stats.get("per_workload", {})
        for wl_key in ["sustained", "idle_loaded", "cold_start"]:
            w = per_wl.get(wl_key, {})
            print(f"{wl_key:<16} | {w.get('wins', 0):>5} | {w.get('total', 0):>5} | "
                  f"{w.get('accuracy_pct', 0.0):>7.1f}% | {w.get('mean_regret_pct', 0.0):>7.2f}% | "
                  f"{w.get('p90_regret_pct', 0.0):>7.2f}%")

        # -------------------------------------------------------------
        # 4. Per-Decision Measured Times For Every Device
        # -------------------------------------------------------------
        print("\n" + "=" * 115)
        print("PER-DECISION MEASURED TIMES FOR EVERY DEVICE")
        print("=" * 115)
        for r in results:
            mt = r["measured_times"]
            parts = []
            for did, ms in sorted(mt.items()):
                dev = devices.get(did)
                dk = dev.key if dev else f"id={did}"
                parts.append(f"{dk}={ms:.3f}ms")
            times_str = ", ".join(parts)
            print(f"  Dec {r['id']:>3} {r['model']:<14} B={r['batch']:>2} {r['workload']:<12} "
                  f"chose={r['chosen']:<6} best={r['best']:<6} | {times_str}")


if __name__ == "__main__":
    run_evaluation()
