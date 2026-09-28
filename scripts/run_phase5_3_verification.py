"""Phase 5.3 Workload-Aware Router Evaluation with Guaranteed Hardware Identity.

Executes 24 verified routing decisions:
- 8 sustained (warm steady-state median)
- 8 idle_loaded (warm session after idle sleep)
- 8 cold_start (session creation + first inference after idle sleep)

Guarantees DXGI adapter enumeration and NVML load fingerprinting before running.
Every device (cpu, dml:0, dml:1) is measured in every decision.

Outputs:
1. Per-decision breakdown with chosen source and actual measured times.
2. Baseline comparison (same 24 decisions) with exact counts.
3. Accuracy and mean/p90 regret per workload for SiliconRoute and all baselines.
4. Per-decision measured times for every device.
5. Saves formatted output to results/phase5_3_report.txt.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.db import AIModel, Decision, Device, engine, init_db
from app.devices import verify_gpu_identity_mapping
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


class OutputCapture:
    """Captures printed lines while also streaming to stdout."""
    def __init__(self):
        self.lines = []

    def write(self, s):
        sys.stdout.write(s)
        self.lines.append(s)

    def print(self, *args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        msg = sep.join(str(a) for a in args) + end
        self.write(msg)

    def get_text(self):
        return "".join(self.lines)


def run_evaluation():
    init_db()
    # 0. Verify physical GPU adapter mapping via DXGI and NVML load fingerprint
    verify_gpu_identity_mapping()

    out = OutputCapture()
    decisions_to_run = build_decision_list()

    with Session(engine) as session:
        models = {m.name: m for m in session.exec(select(AIModel)).all()}
        devices = {d.id: d for d in session.exec(select(Device)).all()}

        out.print("=" * 115)
        out.print("SILICONROUTE PHASE 5.3: 24 WORKLOAD-AWARE VERIFIED DECISIONS")
        out.print("  Guaranteed Physical Adapter Mapping: DXGI + NVML Fingerprint")
        out.print("  8 Sustained  |  8 Idle-Loaded (Warm + Idle)  |  8 Cold-Start (Create + 1st Inf)")
        out.print("=" * 115)

        results = []
        for i, spec in enumerate(decisions_to_run, 1):
            model = models[spec["model"]]
            workload = spec["workload"]
            batch = spec["batch"]

            # Idle sleep before cold/idle decisions to guarantee device enters low-power P8/P4 state
            if workload in ("idle_loaded", "cold_start"):
                out.print(f"\n[{i}/24] Idling 5 s for GPU low-power state...")
                time.sleep(5.0)

            tag = f"[{i}/24] {model.name} B={batch} {workload}"
            out.write(f"{tag}: routing... ")

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
            out.print(f"-> {chosen_dev.key if chosen_dev else '?'} | "
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
        out.print("\n" + "=" * 115)
        out.print(f"{'ID':<4} | {'Model':<14} | {'B':>2} | {'Workload':<12} | {'Chosen':<6} | {'Source':<18} | "
                  f"{'Pred(ms)':>8} | {'Act(ms)':>8} | {'Best':>6} | {'Match':>5} | {'Regret':>7}")
        out.print("-" * 115)
        for r in results:
            pred_ms = 0.0
            source_str = "?"
            for c in r["candidates"]:
                if c["device_key"] == r["chosen"]:
                    pred_ms = c.get("effective_latency_ms", 0.0)
                    source_str = c.get("source", "?")
                    break
            out.print(f"{r['id']:<4} | {r['model']:<14} | {r['batch']:>2} | {r['workload']:<12} | "
                      f"{r['chosen']:<6} | {source_str:<18} | {pred_ms:>8.3f} | {r['actual_ms']:>8.3f} | "
                      f"{r['best']:>6} | {'Yes' if r['was_best'] else 'No':>5} | "
                      f"{r['regret_pct']:>6.1f}%")

        # -------------------------------------------------------------
        # 2. Baseline Comparison Table (Same 24 Decisions)
        # -------------------------------------------------------------
        out.print("\n" + "=" * 115)
        out.print("BASELINE COMPARISON (same 24 decisions)")
        out.print("=" * 115)

        decision_ids = [r["id"] for r in results]
        stats = compute_decision_statistics(session, decision_ids=decision_ids)
        n = stats["total_verified"]
        sr = stats["siliconroute"]

        out.print(f"\nEvaluated on the {n} decisions of this run:")
        out.print(f"\n{'Strategy':<20} | {'Wins':>5} | {'Total':>5} | {'Measured In':>11} | "
                  f"{'Accuracy':>8} | {'MeanReg':>8} | {'P90Reg':>8}")
        out.print("-" * 90)
        out.print(f"{'SiliconRoute':<20} | {sr['wins']:>5} | {sr['total']:>5} | "
                  f"{'':>11} | {sr['accuracy_pct']:>7.1f}% | {sr['mean_regret_pct']:>7.2f}% | "
                  f"{sr['p90_regret_pct']:>7.2f}%")

        for name, key in [("Always-CPU", "always_cpu"), ("Always-RTX", "always_rtx"),
                          ("Fit-Only Router", "fit_only_router")]:
            b = stats["baselines"][key]
            m_in = str(b.get("measured_in", ""))
            out.print(f"{name:<20} | {b['wins']:>5} | {b['total']:>5} | {m_in:>11} | "
                      f"{b['accuracy_pct']:>7.1f}% | {b['mean_regret_pct']:>7.2f}% | "
                      f"{b['p90_regret_pct']:>7.2f}%")

        ort = stats["baselines"]["ort_policy"]
        out.print(f"{'ORT Policy':<20} | {ort['status']}: {ort['reason']}")

        # -------------------------------------------------------------
        # 3. Accuracy and Regret Per Workload Breakdown
        # -------------------------------------------------------------
        out.print("\n" + "=" * 115)
        out.print("PER-WORKLOAD BREAKDOWN (8 decisions each)")
        out.print("=" * 115)
        out.print(f"\n{'Workload':<14} | {'Strategy':<16} | {'Wins':>5} | {'Total':>5} | {'Accuracy':>8} | {'MeanReg':>8} | {'P90Reg':>8}")
        out.print("-" * 85)

        per_wl = stats.get("per_workload", {})
        for wl_key in ["sustained", "idle_loaded", "cold_start"]:
            w = per_wl.get(wl_key, {})
            out.print(f"{wl_key:<14} | {'SiliconRoute':<16} | {w.get('wins', 0):>5} | {w.get('total', 0):>5} | "
                      f"{w.get('accuracy_pct', 0.0):>7.1f}% | {w.get('mean_regret_pct', 0.0):>7.2f}% | "
                      f"{w.get('p90_regret_pct', 0.0):>7.2f}%")
            if "always_cpu" in w:
                c = w["always_cpu"]
                out.print(f"{'':<14} | {'Always-CPU':<16} | {c.get('wins', 0):>5} | {c.get('total', 0):>5} | "
                          f"{c.get('accuracy_pct', 0.0):>7.1f}% | {c.get('mean_regret_pct', 0.0):>7.2f}% | "
                          f"{c.get('p90_regret_pct', 0.0):>7.2f}%")
            if "always_rtx" in w:
                r_stat = w["always_rtx"]
                out.print(f"{'':<14} | {'Always-RTX':<16} | {r_stat.get('wins', 0):>5} | {r_stat.get('total', 0):>5} | "
                          f"{r_stat.get('accuracy_pct', 0.0):>7.1f}% | {r_stat.get('mean_regret_pct', 0.0):>7.2f}% | "
                          f"{r_stat.get('p90_regret_pct', 0.0):>7.2f}%")
            if "fit_only" in w:
                f_stat = w["fit_only"]
                out.print(f"{'':<14} | {'Fit-Only':<16} | {f_stat.get('wins', 0):>5} | {f_stat.get('total', 0):>5} | "
                          f"{f_stat.get('accuracy_pct', 0.0):>7.1f}% | {f_stat.get('mean_regret_pct', 0.0):>7.2f}% | "
                          f"{f_stat.get('p90_regret_pct', 0.0):>7.2f}%")
            out.print("-" * 85)

        # -------------------------------------------------------------
        # 4. Per-Decision Measured Times For Every Device
        # -------------------------------------------------------------
        out.print("\n" + "=" * 115)
        out.print("PER-DECISION MEASURED TIMES FOR EVERY DEVICE")
        out.print("=" * 115)
        for r in results:
            mt = r["measured_times"]
            parts = []
            for did, ms in sorted(mt.items()):
                dev = devices.get(did)
                dk = dev.key if dev else f"id={did}"
                parts.append(f"{dk}={ms:.3f}ms")
            times_str = ", ".join(parts)
            out.print(f"  Dec {r['id']:>3} {r['model']:<14} B={r['batch']:>2} {r['workload']:<12} "
                      f"chose={r['chosen']:<6} best={r['best']:<6} | {times_str}")

        # Save to results/phase5_3_report.txt
        report_path = Path("results/phase5_3_report.txt")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(out.get_text(), encoding="utf-8")
        out.print(f"\nReport written to {report_path.resolve()}")


if __name__ == "__main__":
    run_evaluation()
