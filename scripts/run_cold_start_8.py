"""Run 8 new verified cold-start decisions (IDs 141-148) with cold-start rule."""

import json
import time
from datetime import datetime, timezone
import numpy as np
from sqlmodel import Session, select
from app.db import create_db_engine, Device, AIModel, Decision, WorkloadMeasurement
from app.router import route_model, execute_verification, compute_decision_statistics

COLD_START_PLAN = [
    ("mlp-256w-4l", 8, "fastest", "cold_start"),
    ("conv-96c-4l", 8, "fastest", "cold_start"),
    ("conv-16c-4l", 1, "fastest", "cold_start"),
    ("mlp-3072w-4l", 1, "fastest", "cold_start"),
    ("mlp-3072w-4l", 8, "fastest", "cold_start"),
    ("mlp-256w-4l", 1, "fastest", "cold_start"),
    ("mlp-1024w-4l", 1, "fastest", "cold_start"),
    ("conv-96c-4l", 1, "fastest", "cold_start"),
]

def main():
    engine = create_db_engine()
    print("=" * 115)
    print("SILICONROUTE PHASE 7+8: 8 NEW VERIFIED COLD-START DECISIONS (COLD-START RULE ACTIVE)")
    print("  Rule: Choose CPU unless another chip is predicted >30% lower latency")
    print("=" * 115)

    created_ids = []

    with Session(engine) as session:
        devices = {d.id: d for d in session.exec(select(Device)).all()}
        models = {m.name: m for m in session.exec(select(AIModel)).all()}

        for idx, (m_name, batch, mode, workload) in enumerate(COLD_START_PLAN, 1):
            model = models.get(m_name)
            if not model:
                raise ValueError(f"Model {m_name} not found in database")

            print(f"[{idx}/8] Idling 3 s for accelerator sleep state...")
            time.sleep(3.0)

            # Route model with deterministic mode (allow_explore=False)
            dec_dict = route_model(
                session=session,
                model_id=model.id,
                batch=batch,
                mode=mode,
                power_budget_w=None,
                workload=workload,
                allow_explore=False,
            )

            # Execute verification
            dec_record = execute_verification(
                session=session,
                decision_dict=dec_dict,
                runs_count=20,
            )
            created_ids.append(dec_record.id)

            chosen_dev = devices[dec_record.chosen_device_id]
            best_dev = devices[dec_record.best_device_id_actual]
            cands = json.loads(dec_record.candidates_json)
            chosen_cand = next((c for c in cands if c["device_id"] == dec_record.chosen_device_id), {})
            source = chosen_cand.get("source", "unknown")
            pred_ms = chosen_cand.get("effective_latency_ms", 0.0)

            print(
                f"Created Decision #{dec_record.id}: {m_name} B={batch} {workload} | "
                f"Chosen={chosen_dev.key} ({source}) | Pred={pred_ms:.3f} ms | "
                f"Act={dec_record.actual_ms:.3f} ms | Best={best_dev.key} | "
                f"Match={'Yes' if dec_record.was_best else 'No'} | Regret={dec_record.regret_pct:.1f}%"
            )
            print(f"  Reason: {dec_record.reason}")

        # Summary Table
        print("\n" + "=" * 115)
        print("SUMMARY TABLE: NEW COLD-START DECISIONS (IDs 141-148)")
        print("=" * 115)
        header = f"{'ID':<4} | {'Model':<15} | {'B':<2} | {'Workload':<12} | {'Chosen':<6} | {'Source':<20} | {'Pred(ms)':>8} | {'Act(ms)':>8} | {'Best':<6} | {'Match':<5} | {'Regret':>7}"
        print(header)
        print("-" * len(header))

        for dec_id in created_ids:
            d = session.get(Decision, dec_id)
            m = session.get(AIModel, d.ai_model_id)
            c_dev = devices[d.chosen_device_id]
            b_dev = devices[d.best_device_id_actual]
            cands = json.loads(d.candidates_json)
            ch_cand = next((c for c in cands if c["device_id"] == d.chosen_device_id), {})
            src = ch_cand.get("source", "unknown")
            p_ms = ch_cand.get("effective_latency_ms", 0.0)
            print(
                f"{d.id:<4} | {m.name:<15} | {d.batch:<2} | {'cold_start':<12} | {c_dev.key:<6} | {src:<20} | "
                f"{p_ms:8.3f} | {d.actual_ms:8.3f} | {b_dev.key:<6} | {'Yes' if d.was_best else 'No':<5} | {d.regret_pct:6.1f}%"
            )

        # Baseline evaluation on new cold-start decisions (141-148)
        new_stats = compute_decision_statistics(session, decision_ids=created_ids)
        print("\n" + "=" * 115)
        print(f"BASELINE COMPARISON: NEW COLD-START DECISIONS (IDs {min(created_ids)}-{max(created_ids)})")
        print("=" * 115)
        sr = new_stats["siliconroute"]
        bl = new_stats["baselines"]
        print(f"{'Strategy':<20} | {'Wins':<5} | {'Total':<5} | {'Accuracy':>9} | {'MeanReg':>9} | {'P90Reg':>9}")
        print("-" * 68)
        print(f"{'SiliconRoute':<20} | {sr['wins']:<5} | {sr['total']:<5} | {sr['accuracy_pct']:8.1f}% | {sr['mean_regret_pct']:8.2f}% | {sr['p90_regret_pct']:8.2f}%")
        cpu_bl = bl["always_cpu"]
        print(f"{'Always-CPU':<20} | {cpu_bl['wins']:<5} | {cpu_bl['total']:<5} | {cpu_bl['accuracy_pct']:8.1f}% | {cpu_bl['mean_regret_pct']:8.2f}% | {cpu_bl['p90_regret_pct']:8.2f}%")
        rtx_bl = bl["always_rtx"]
        print(f"{'Always-RTX':<20} | {rtx_bl['wins']:<5} | {rtx_bl['total']:<5} | {rtx_bl['accuracy_pct']:8.1f}% | {rtx_bl['mean_regret_pct']:8.2f}% | {rtx_bl['p90_regret_pct']:8.2f}%")
        fit_bl = bl["fit_only_router"]
        print(f"{'Fit-Only Router':<20} | {fit_bl['wins']:<5} | {fit_bl['total']:<5} | {fit_bl['accuracy_pct']:8.1f}% | {fit_bl['mean_regret_pct']:8.2f}% | {fit_bl['p90_regret_pct']:8.2f}%")

        # Comparison with decisions 117-140 cold-start run
        # Old cold-start decisions were [118, 120, 123, 124, 125, 132, 137, 140]
        old_cold_ids = [118, 120, 123, 124, 125, 132, 137, 140]
        old_cold_stats = compute_decision_statistics(session, decision_ids=old_cold_ids)
        print("\n" + "=" * 115)
        print("COMPARISON: OLD COLD-START (Decisions 117-140) VS NEW COLD-START (Decisions 141-148)")
        print("=" * 115)
        old_sr = old_cold_stats["siliconroute"]
        old_cpu = old_cold_stats["baselines"]["always_cpu"]
        print(f"{'Strategy':<20} | {'Old Wins/Acc (No Rule)':<24} | {'New Wins/Acc (With Rule)':<24} | {'Old MeanReg':>11} | {'New MeanReg':>11}")
        print("-" * 100)
        print(f"{'SiliconRoute':<20} | {old_sr['wins']}/{old_sr['total']} ({old_sr['accuracy_pct']:.1f}%)" + " " * 10 + f"| {sr['wins']}/{sr['total']} ({sr['accuracy_pct']:.1f}%)" + " " * 10 + f"| {old_sr['mean_regret_pct']:10.2f}% | {sr['mean_regret_pct']:10.2f}%")
        print(f"{'Always-CPU':<20} | {old_cpu['wins']}/{old_cpu['total']} ({old_cpu['accuracy_pct']:.1f}%)" + " " * 9 + f"| {cpu_bl['wins']}/{cpu_bl['total']} ({cpu_bl['accuracy_pct']:.1f}%)" + " " * 9 + f"| {old_cpu['mean_regret_pct']:10.2f}% | {cpu_bl['mean_regret_pct']:10.2f}%")

        # Count new WorkloadMeasurement rows
        wm_rows = session.exec(
            select(WorkloadMeasurement).where(WorkloadMeasurement.decision_id.in_(created_ids))
        ).all()
        print(f"\nWorkloadMeasurement rows inserted for decisions {min(created_ids)}-{max(created_ids)}: {len(wm_rows)}")
        for r in wm_rows[:6]:
            print(f"  id={r.id:<4} | dec_id={r.decision_id} | dev_id={r.device_id} | model_id={r.ai_model_id} B={r.batch:<2} | {r.workload:<12} | lat={r.latency_ms:7.3f} ms | pstate_before={r.pstate_before}")

if __name__ == "__main__":
    main()
