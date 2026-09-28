"""Phase 5.1 Workload-Aware Router Evaluation.

Runs 24 verified routing decisions (12 sustained + 12 single) in randomized
order, covering GPU-favoured large cases and CPU-favoured small cases.

For 'single' cases, idles 10 s before each decision to let the GPU sleep (P8).
Reports accuracy and mean/p90 regret for SiliconRoute, fit-only, always-CPU
and always-RTX on the SAME 24 decisions, with counts.
"""

import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.db import AIModel, Decision, Device, engine, init_db
from app.router import compute_decision_statistics, execute_verification, route_model

IDLE_BEFORE_SINGLE_S = 10


def build_decision_list() -> list[dict]:
    """Build 24 decisions: 12 sustained + 12 single, mixed GPU- and CPU-favoured."""
    # GPU-favoured: large models at various batches
    gpu_cases = [
        ("mlp-3072w-4l", 1),
        ("mlp-3072w-4l", 8),
        ("mlp-3072w-4l", 32),
        ("conv-96c-4l", 1),
        ("conv-96c-4l", 8),
        ("conv-96c-4l", 32),
    ]
    # CPU-favoured: small models
    cpu_cases = [
        ("mlp-256w-4l", 1),
        ("mlp-256w-4l", 8),
        ("mlp-256w-4l", 32),
        ("mlp-1024w-4l", 1),
        ("conv-16c-4l", 1),
        ("conv-16c-4l", 8),
    ]

    decisions = []
    for name, batch in gpu_cases:
        decisions.append({"model": name, "batch": batch, "workload": "sustained"})
        decisions.append({"model": name, "batch": batch, "workload": "single"})
    for name, batch in cpu_cases:
        decisions.append({"model": name, "batch": batch, "workload": "sustained"})
        decisions.append({"model": name, "batch": batch, "workload": "single"})

    # Shuffle with fixed seed for reproducibility
    random.seed(42)
    random.shuffle(decisions)
    return decisions


def run_phase51():
    init_db()
    decisions = build_decision_list()

    with Session(engine) as session:
        models = {m.name: m for m in session.exec(select(AIModel)).all()}
        devices = {d.id: d for d in session.exec(select(Device)).all()}

        # Verify all target models exist
        needed = {d["model"] for d in decisions}
        missing = needed - set(models.keys())
        if missing:
            print(f"ERROR: missing models: {missing}")
            sys.exit(1)

        print("=" * 110)
        print("SILICONROUTE PHASE 5.1: 24 WORKLOAD-AWARE VERIFIED DECISIONS")
        print("=" * 110)

        results = []
        for i, spec in enumerate(decisions, 1):
            model = models[spec["model"]]
            workload = spec["workload"]

            if workload == "single":
                print(f"\n[{i}/24] Idling {IDLE_BEFORE_SINGLE_S} s for GPU P8 sleep...")
                time.sleep(IDLE_BEFORE_SINGLE_S)

            tag = f"[{i}/24] {model.name} B={spec['batch']} {workload}"
            print(f"{tag}: routing...", end=" ", flush=True)

            decision_dict = route_model(
                session=session,
                model_id=model.id,
                batch=spec["batch"],
                mode="fastest",
                workload=workload,
                allow_explore=False,   # No random exploration for evaluation
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

            # Parse candidates and measured_times from stored decision
            ctx = json.loads(dec_record.context_json) if dec_record.context_json else {}
            cands = json.loads(dec_record.candidates_json) if dec_record.candidates_json else []
            m_times = {int(k): v for k, v in ctx.get("measured_times_ms", {}).items()}

            results.append({
                "id": dec_record.id,
                "model": model.name,
                "batch": spec["batch"],
                "workload": workload,
                "chosen": chosen_dev.key if chosen_dev else "?",
                "best": best_dev.key if best_dev else "?",
                "actual_ms": dec_record.actual_ms,
                "was_best": dec_record.was_best,
                "regret_pct": dec_record.regret_pct,
                "candidates": cands,
                "measured_times": m_times,
            })

        # Print summary table
        print("\n" + "=" * 110)
        print(f"{'ID':<4} | {'Model':<16} | {'B':>2} | {'WL':<9} | {'Chosen':<6} | "
              f"{'Pred(ms)':>9} | {'Act(ms)':>8} | {'Best':>6} | {'Match':>5} | {'Regret':>7}")
        print("-" * 110)
        for r in results:
            # Find chosen candidate's predicted latency
            pred_ms = 0.0
            for c in r["candidates"]:
                if c["device_key"] == r["chosen"]:
                    pred_ms = c.get("effective_latency_ms", 0.0)
                    break
            print(f"{r['id']:<4} | {r['model']:<16} | {r['batch']:>2} | {r['workload']:<9} | "
                  f"{r['chosen']:<6} | {pred_ms:>9.3f} | {r['actual_ms']:>8.3f} | "
                  f"{r['best']:>6} | {'Yes' if r['was_best'] else 'No':>5} | "
                  f"{r['regret_pct']:>6.1f}%")

        # Compute baselines on the SAME 24 decisions
        print("\n" + "=" * 110)
        print("BASELINE COMPARISON (same 24 decisions)")
        print("=" * 110)

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

        # Per-decision detail for every measured time
        print("\n" + "=" * 110)
        print("PER-DECISION MEASURED TIMES")
        print("=" * 110)
        for r in results:
            mt = r["measured_times"]
            parts = []
            for did, ms in sorted(mt.items()):
                dev = devices.get(did)
                dk = dev.key if dev else f"id={did}"
                parts.append(f"{dk}={ms:.3f}ms")
            times_str = ", ".join(parts)
            print(f"  Dec {r['id']:>3} {r['model']:<16} B={r['batch']:>2} {r['workload']:<9} "
                  f"chose={r['chosen']:<6} best={r['best']:<6} | {times_str}")


if __name__ == "__main__":
    run_phase51()
