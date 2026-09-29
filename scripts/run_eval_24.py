"""Fresh 24-decision hardware evaluation (Decisions 117-140) matching Phase 5.3 design."""

import json
import time
from datetime import datetime, timezone
import numpy as np
from sqlmodel import Session, select
from app.db import create_db_engine, Device, AIModel, Decision, WorkloadMeasurement, Run
from app.router import route_model, execute_verification, compute_decision_statistics

# Exact 24-decision workload plan matching decisions 93-116
DECISION_PLAN = [
    ("conv-16c-4l", 1, "fastest", "sustained"),
    ("mlp-256w-4l", 8, "fastest", "cold_start"),
    ("conv-96c-4l", 1, "fastest", "sustained"),
    ("conv-96c-4l", 8, "fastest", "cold_start"),
    ("mlp-3072w-4l", 8, "fastest", "idle_loaded"),
    ("mlp-3072w-4l", 1, "fastest", "idle_loaded"),
    ("conv-16c-4l", 1, "fastest", "cold_start"),
    ("mlp-3072w-4l", 1, "fastest", "cold_start"),
    ("mlp-3072w-4l", 8, "fastest", "cold_start"),
    ("conv-16c-4l", 1, "fastest", "idle_loaded"),
    ("mlp-256w-4l", 1, "fastest", "idle_loaded"),
    ("mlp-3072w-4l", 8, "fastest", "sustained"),
    ("conv-96c-4l", 8, "fastest", "sustained"),
    ("mlp-1024w-4l", 1, "fastest", "sustained"),
    ("mlp-3072w-4l", 1, "fastest", "sustained"),
    ("mlp-256w-4l", 1, "fastest", "cold_start"),
    ("conv-96c-4l", 8, "fastest", "idle_loaded"),
    ("mlp-256w-4l", 8, "fastest", "idle_loaded"),
    ("conv-96c-4l", 1, "fastest", "idle_loaded"),
    ("mlp-1024w-4l", 1, "fastest", "idle_loaded"),
    ("mlp-1024w-4l", 1, "fastest", "cold_start"),
    ("mlp-256w-4l", 1, "fastest", "sustained"),
    ("mlp-256w-4l", 8, "fastest", "sustained"),
    ("conv-96c-4l", 1, "fastest", "cold_start"),
]

def main():
    engine = create_db_engine()
    print("=" * 115)
    print("SILICONROUTE PHASE 6: FRESH 24 WORKLOAD-AWARE VERIFIED DECISIONS (117-140)")
    print("  8 Sustained  |  8 Idle-Loaded (Warm + Idle)  |  8 Cold-Start (Create + 1st Inf)")
    print("=" * 115)

    created_decision_ids = []

    with Session(engine) as session:
        devices = {d.id: d for d in session.exec(select(Device)).all()}
        models = {m.name: m for m in session.exec(select(AIModel)).all()}

        for idx, (m_name, batch, mode, workload) in enumerate(DECISION_PLAN, 1):
            model = models.get(m_name)
            if not model:
                raise ValueError(f"Model {m_name} not found in database")

            if workload in ("idle_loaded", "cold_start"):
                print(f"[{idx}/24] Idling 5 s for GPU low-power state...")
                time.sleep(5.0)

            # Route model
            decision_dict = route_model(
                session=session,
                model_id=model.id,
                batch=batch,
                mode=mode,
                workload=workload,
                allow_explore=False,
            )

            # Execute verification
            dec_rec = execute_verification(
                session=session,
                decision_dict=decision_dict,
                workload=workload,
            )
            created_decision_ids.append(dec_rec.id)

            chosen_dev = devices[dec_rec.chosen_device_id]
            best_dev = devices[dec_rec.best_device_id_actual]
            win_str = "WIN" if dec_rec.was_best else f"LOSS (regret {dec_rec.regret_pct:.1f}%)"

            print(
                f"[{idx}/24] {m_name} B={batch} {workload}: routing... -> {chosen_dev.key} | "
                f"actual={dec_rec.actual_ms:.3f} ms | best={best_dev.key} | {win_str}"
            )

    print("\n" + "=" * 115)
    print("DECISIONS 117-140 TABLE")
    print("=" * 115)
    print(f"{'ID':<4} | {'Model':<15} | {'B':<2} | {'Workload':<12} | {'Chosen':<6} | {'Source':<20} | {'Pred(ms)':<8} | {'Act(ms)':<8} | {'Best':<6} | {'Match':<5} | {'Regret':<7}")
    print("-" * 115)

    with Session(engine) as session:
        decisions = session.exec(
            select(Decision).where(Decision.id.in_(created_decision_ids)).order_by(Decision.id)
        ).all()
        dev_map = {d.id: d.key for d in session.exec(select(Device)).all()}
        model_map = {m.id: m.name for m in session.exec(select(AIModel)).all()}

        for d in decisions:
            ctx = json.loads(d.context_json)
            candidates = json.loads(d.candidates_json)
            chosen_c = next((c for c in candidates if c["device_id"] == d.chosen_device_id), {})
            source = chosen_c.get("source", "n/a")
            pred_ms = chosen_c.get("effective_latency_ms", 0.0)
            m_name = model_map.get(d.ai_model_id, str(d.ai_model_id))
            chosen_k = dev_map.get(d.chosen_device_id, str(d.chosen_device_id))
            best_k = dev_map.get(d.best_device_id_actual, str(d.best_device_id_actual))
            match_str = "Yes" if d.was_best else "No"
            print(
                f"{d.id:<4} | {m_name:<15} | {d.batch:<2} | {ctx.get('workload', 'sustained'):<12} | "
                f"{chosen_k:<6} | {source:<20} | {pred_ms:>8.3f} | {d.actual_ms:>8.3f} | "
                f"{best_k:<6} | {match_str:<5} | {d.regret_pct:>6.1f}%"
            )

    # Compute Baseline Statistics
    print("\n" + "=" * 115)
    print("BASELINE COMPARISON (Fresh 24 decisions: IDs 117-140)")
    print("=" * 115)

    with Session(engine) as session:
        stats_new = compute_decision_statistics(session, decision_ids=created_decision_ids)
        stats_old = compute_decision_statistics(session, decision_ids=list(range(93, 117)))

        print(f"{'Strategy':<20} | {'Wins':<5} | {'Total':<5} | {'Accuracy':<9} | {'MeanReg':<9} | {'P90Reg':<9}")
        print("-" * 68)
        for strat in ["router", "always_cpu", "always_rtx", "fit_only"]:
            s_data = stats_new[strat]
            strat_label = (
                "SiliconRoute" if strat == "router"
                else "Always-CPU" if strat == "always_cpu"
                else "Always-RTX" if strat == "always_rtx"
                else "Fit-Only Router"
            )
            print(
                f"{strat_label:<20} | {s_data['wins']:<5} | {s_data['total']:<5} | "
                f"{s_data['accuracy_pct']:>8.1f}% | {s_data['mean_regret_pct']:>8.2f}% | {s_data['p90_regret_pct']:>8.2f}%"
            )

        print("\n" + "=" * 115)
        print("COMPARISON: OLD (93-116) VS NEW (117-140)")
        print("=" * 115)
        print(f"{'Strategy':<20} | {'Old Wins/Acc':<16} | {'New Wins/Acc':<16} | {'Old MeanReg':<14} | {'New MeanReg':<14}")
        print("-" * 90)
        for strat in ["router", "always_cpu", "always_rtx", "fit_only"]:
            old_s = stats_old[strat]
            new_s = stats_new[strat]
            strat_label = (
                "SiliconRoute" if strat == "router"
                else "Always-CPU" if strat == "always_cpu"
                else "Always-RTX" if strat == "always_rtx"
                else "Fit-Only Router"
            )
            old_str = f"{old_s['wins']}/{old_s['total']} ({old_s['accuracy_pct']:.1f}%)"
            new_str = f"{new_s['wins']}/{new_s['total']} ({new_s['accuracy_pct']:.1f}%)"
            print(f"{strat_label:<20} | {old_str:<16} | {new_str:<16} | {old_s['mean_regret_pct']:>12.2f}% | {new_s['mean_regret_pct']:>12.2f}%")

        # Per-Workload Breakdown
        print("\n" + "=" * 115)
        print("PER-WORKLOAD BREAKDOWN (8 decisions each in fresh run 117-140)")
        print("=" * 115)
        print(f"{'Workload':<14} | {'Strategy':<18} | {'Wins':<5} | {'Total':<5} | {'Accuracy':<9} | {'MeanReg':<9} | {'P90Reg':<9}")
        print("-" * 80)

        for wl in ["sustained", "idle_loaded", "cold_start"]:
            wl_ids = [
                d.id for d in decisions
                if json.loads(d.context_json).get("workload") == wl
            ]
            wl_stats = compute_decision_statistics(session, decision_ids=wl_ids)
            for s_idx, strat in enumerate(["router", "always_cpu", "always_rtx", "fit_only"]):
                s_data = wl_stats[strat]
                strat_label = (
                    "SiliconRoute" if strat == "router"
                    else "Always-CPU" if strat == "always_cpu"
                    else "Always-RTX" if strat == "always_rtx"
                    else "Fit-Only"
                )
                wl_label = wl if s_idx == 0 else ""
                print(
                    f"{wl_label:<14} | {strat_label:<18} | {s_data['wins']:<5} | {s_data['total']:<5} | "
                    f"{s_data['accuracy_pct']:>8.1f}% | {s_data['mean_regret_pct']:>8.2f}% | {s_data['p90_regret_pct']:>8.2f}%"
                )
            print("-" * 80)

        # Check WorkloadMeasurement rows created
        wm_count = session.exec(
            select(WorkloadMeasurement).where(WorkloadMeasurement.decision_id.in_(created_decision_ids))
        ).all()
        print(f"\nWorkloadMeasurement rows inserted for decisions 117-140: {len(wm_count)}")
        print(f"Sample row: id={wm_count[0].id}, decision_id={wm_count[0].decision_id}, workload={wm_count[0].workload}, latency_ms={wm_count[0].latency_ms}, idle_s={wm_count[0].idle_s}, pstate_before={wm_count[0].pstate_before}")

if __name__ == "__main__":
    main()
