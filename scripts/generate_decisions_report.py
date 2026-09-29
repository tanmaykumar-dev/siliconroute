"""Report generator for SiliconRoute Phase 6 Decisions 117-140."""

import json
from sqlmodel import Session, select
from app.db import create_db_engine, Device, AIModel, Decision, WorkloadMeasurement
from app.router import compute_decision_statistics

def main():
    engine = create_db_engine()
    print("=" * 115)
    print("SILICONROUTE PHASE 6: FRESH 24 WORKLOAD-AWARE VERIFIED DECISIONS (117-140)")
    print("  8 Sustained  |  8 Idle-Loaded (Warm + Idle)  |  8 Cold-Start (Create + 1st Inf)")
    print("=" * 115)

    created_decision_ids = list(range(117, 141))

    with Session(engine) as session:
        decisions = session.exec(
            select(Decision).where(Decision.id.in_(created_decision_ids)).order_by(Decision.id)
        ).all()
        dev_map = {d.id: d.key for d in session.exec(select(Device)).all()}
        model_map = {m.id: m.name for m in session.exec(select(AIModel)).all()}

        print(f"{'ID':<4} | {'Model':<15} | {'B':<2} | {'Workload':<12} | {'Chosen':<6} | {'Source':<20} | {'Pred(ms)':<8} | {'Act(ms)':<8} | {'Best':<6} | {'Match':<5} | {'Regret':<7}")
        print("-" * 115)
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

        print("\n" + "=" * 115)
        print("BASELINE COMPARISON (Fresh 24 decisions: IDs 117-140)")
        print("=" * 115)

        stats_new = compute_decision_statistics(session, decision_ids=created_decision_ids)
        stats_old = compute_decision_statistics(session, decision_ids=list(range(93, 117)))

        print(f"{'Strategy':<20} | {'Wins':<5} | {'Total':<5} | {'Accuracy':<9} | {'MeanReg':<9} | {'P90Reg':<9}")
        print("-" * 68)
        # 1. SiliconRoute
        sr = stats_new["siliconroute"]
        print(f"{'SiliconRoute':<20} | {sr['wins']:<5} | {sr['total']:<5} | {sr['accuracy_pct']:>8.1f}% | {sr['mean_regret_pct']:>8.2f}% | {sr['p90_regret_pct']:>8.2f}%")
        # 2. Always-CPU
        ac = stats_new["baselines"]["always_cpu"]
        print(f"{'Always-CPU':<20} | {ac['wins']:<5} | {ac['total']:<5} | {ac['accuracy_pct']:>8.1f}% | {ac['mean_regret_pct']:>8.2f}% | {ac['p90_regret_pct']:>8.2f}%")
        # 3. Always-RTX
        ar = stats_new["baselines"]["always_rtx"]
        print(f"{'Always-RTX':<20} | {ar['wins']:<5} | {ar['total']:<5} | {ar['accuracy_pct']:>8.1f}% | {ar['mean_regret_pct']:>8.2f}% | {ar['p90_regret_pct']:>8.2f}%")
        # 4. Fit-Only Router
        fo = stats_new["baselines"]["fit_only_router"]
        print(f"{'Fit-Only Router':<20} | {fo['wins']:<5} | {fo['total']:<5} | {fo['accuracy_pct']:>8.1f}% | {fo['mean_regret_pct']:>8.2f}% | {fo['p90_regret_pct']:>8.2f}%")
        print(f"{'ORT Policy':<20} | not available: ORT ExecutionProviderDevicePolicy was not executed on hardware")

        print("\n" + "=" * 115)
        print("COMPARISON: OLD (93-116) VS NEW (117-140)")
        print("=" * 115)
        print(f"{'Strategy':<20} | {'Old Wins/Acc':<16} | {'New Wins/Acc':<16} | {'Old MeanReg':<14} | {'New MeanReg':<14}")
        print("-" * 90)
        
        # SiliconRoute
        old_sr, new_sr = stats_old["siliconroute"], stats_new["siliconroute"]
        print(f"{'SiliconRoute':<20} | {old_sr['wins']}/{old_sr['total']} ({old_sr['accuracy_pct']:.1f}%) | {new_sr['wins']}/{new_sr['total']} ({new_sr['accuracy_pct']:.1f}%) | {old_sr['mean_regret_pct']:>12.2f}% | {new_sr['mean_regret_pct']:>12.2f}%")
        # Always-CPU
        old_ac, new_ac = stats_old["baselines"]["always_cpu"], stats_new["baselines"]["always_cpu"]
        print(f"{'Always-CPU':<20} | {old_ac['wins']}/{old_ac['total']} ({old_ac['accuracy_pct']:.1f}%) | {new_ac['wins']}/{new_ac['total']} ({new_ac['accuracy_pct']:.1f}%) | {old_ac['mean_regret_pct']:>12.2f}% | {new_ac['mean_regret_pct']:>12.2f}%")
        # Always-RTX
        old_ar, new_ar = stats_old["baselines"]["always_rtx"], stats_new["baselines"]["always_rtx"]
        print(f"{'Always-RTX':<20} | {old_ar['wins']}/{old_ar['total']} ({old_ar['accuracy_pct']:.1f}%) | {new_ar['wins']}/{new_ar['total']} ({new_ar['accuracy_pct']:.1f}%) | {old_ar['mean_regret_pct']:>12.2f}% | {new_ar['mean_regret_pct']:>12.2f}%")
        # Fit-Only Router
        old_fo, new_fo = stats_old["baselines"]["fit_only_router"], stats_new["baselines"]["fit_only_router"]
        print(f"{'Fit-Only Router':<20} | {old_fo['wins']}/{old_fo['total']} ({old_fo['accuracy_pct']:.1f}%) | {new_fo['wins']}/{new_fo['total']} ({new_fo['accuracy_pct']:.1f}%) | {old_fo['mean_regret_pct']:>12.2f}% | {new_fo['mean_regret_pct']:>12.2f}%")

        # Per-Workload Breakdown
        print("\n" + "=" * 115)
        print("PER-WORKLOAD BREAKDOWN (8 decisions each in fresh run 117-140)")
        print("=" * 115)
        print(f"{'Workload':<14} | {'Strategy':<18} | {'Wins':<5} | {'Total':<5} | {'Accuracy':<9} | {'MeanReg':<9} | {'P90Reg':<9}")
        print("-" * 80)

        pw = stats_new["per_workload"]
        for wl in ["sustained", "idle_loaded", "cold_start"]:
            wl_d = pw.get(wl, {})
            # SiliconRoute
            print(f"{wl:<14} | {'SiliconRoute':<18} | {wl_d.get('wins', 0):<5} | {wl_d.get('total', 0):<5} | {wl_d.get('accuracy_pct', 0.0):>8.1f}% | {wl_d.get('mean_regret_pct', 0.0):>8.2f}% | {wl_d.get('p90_regret_pct', 0.0):>8.2f}%")
            # Always-CPU
            ac = wl_d.get("always_cpu", {})
            print(f"{'':<14} | {'Always-CPU':<18} | {ac.get('wins', 0):<5} | {ac.get('total', 0):<5} | {ac.get('accuracy_pct', 0.0):>8.1f}% | {ac.get('mean_regret_pct', 0.0):>8.2f}% | {ac.get('p90_regret_pct', 0.0):>8.2f}%")
            # Always-RTX
            ar = wl_d.get("always_rtx", {})
            print(f"{'':<14} | {'Always-RTX':<18} | {ar.get('wins', 0):<5} | {ar.get('total', 0):<5} | {ar.get('accuracy_pct', 0.0):>8.1f}% | {ar.get('mean_regret_pct', 0.0):>8.2f}% | {ar.get('p90_regret_pct', 0.0):>8.2f}%")
            # Fit-Only
            fo = wl_d.get("fit_only", {})
            print(f"{'':<14} | {'Fit-Only':<18} | {fo.get('wins', 0):<5} | {fo.get('total', 0):<5} | {fo.get('accuracy_pct', 0.0):>8.1f}% | {fo.get('mean_regret_pct', 0.0):>8.2f}% | {fo.get('p90_regret_pct', 0.0):>8.2f}%")
            print("-" * 80)

        # Check WorkloadMeasurement rows created
        wm_rows = session.exec(
            select(WorkloadMeasurement).where(WorkloadMeasurement.decision_id.in_(created_decision_ids))
        ).all()
        print(f"\nWorkloadMeasurement rows inserted for decisions 117-140: {len(wm_rows)}")
        print("Sample rows:")
        for wm in wm_rows[:6]:
            print(f"  id={wm.id:<3} | dec_id={wm.decision_id} | dev={dev_map.get(wm.device_id):<6} | model_id={wm.ai_model_id} B={wm.batch:<2} | {wm.workload:<12} | lat={wm.latency_ms:>7.3f} ms | pstate_before={wm.pstate_before}")

if __name__ == "__main__":
    main()
