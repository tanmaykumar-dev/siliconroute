"""Phase 5.1 Diagnostic: dump every recorded decision with full candidate detail."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select
from app.db import AIModel, Decision, Device, Run, engine, init_db


def main():
    init_db()
    with Session(engine) as session:
        devices = {d.id: d for d in session.exec(select(Device)).all()}
        models = {m.id: m for m in session.exec(select(AIModel)).all()}

        decisions = session.exec(select(Decision).order_by(Decision.id)).all()
        if not decisions:
            print("No decisions recorded.")
            return

        for d in decisions:
            model = models.get(d.ai_model_id)
            model_name = model.name if model else f"id={d.ai_model_id}"
            ctx = json.loads(d.context_json) if d.context_json else {}
            cands = json.loads(d.candidates_json) if d.candidates_json else []
            measured_map = ctx.get("measured_times_ms", {})
            verify_session_id = ctx.get("verification_session_id")

            workload = ctx.get("workload", "sustained")
            print("=" * 100)
            print(f"Decision {d.id} | {model_name} B={d.batch} mode={d.mode} workload={workload}")
            chosen_dev = devices.get(d.chosen_device_id)
            print(f"  Chosen: {chosen_dev.key if chosen_dev else '?'} (id={d.chosen_device_id})")
            print(f"  Result: actual={d.actual_ms} ms, was_best={d.was_best}, regret={d.regret_pct}%")
            best_dev = devices.get(d.best_device_id_actual)
            print(f"  Best actual: {best_dev.key if best_dev else '?'}")
            print()

            # Context rules
            rules = ctx.get("rules", [])
            if rules:
                print(f"  Context Rules:")
                for r in rules:
                    print(f"    - {r}")
                print()

            # Candidates
            print(f"  CANDIDATES ({len(cands)}):")
            print(f"  {'Key':<8} {'Source':<10} {'BaseLat(ms)':<11} {'FitLat(ms)':<10} "
                  f"{'WakePen(ms)':<11} {'EffLat(ms)':<10} {'Score':<8} {'Volatile':<8} "
                  f"{'VolPct':<6} {'WakeStatus'}")
            print(f"  {'-'*98}")
            for c in cands:
                print(f"  {c.get('device_key','?'):<8} "
                      f"{c.get('source','?'):<10} "
                      f"{c.get('base_latency_ms',0):<11.3f} "
                      f"{(c.get('fit_latency_ms') or 0):<10.3f} "
                      f"{c.get('wake_penalty_ms',0):<11.3f} "
                      f"{c.get('effective_latency_ms',0):<10.3f} "
                      f"{c.get('raw_score',0):<8.4f} "
                      f"{str(c.get('is_volatile',False)):<8} "
                      f"{(c.get('volatility_pct') or 0):<6.1f} "
                      f"{c.get('wake_status','?')}")
            print()

            # Excluded candidates
            excluded = ctx.get("excluded_candidates") or []
            # Also try from the decision dict structure
            if not excluded:
                # excluded_candidates not stored in context_json; check candidates_json structure
                pass
            if excluded:
                print(f"  EXCLUDED:")
                for e in excluded:
                    print(f"    {e.get('device_key','?')}: {e.get('reason','?')}")
                print()

            # Verification runs
            if verify_session_id and measured_map:
                print(f"  VERIFICATION (Session {verify_session_id}):")
                print(f"  {'Key':<8} {'Measured(ms)':<12} {'Method'}")
                print(f"  {'-'*40}")

                # Look up the actual verification runs
                for dev_id_str, meas_ms in measured_map.items():
                    dev_id = int(dev_id_str)
                    dev = devices.get(dev_id)
                    dev_key = dev.key if dev else f"id={dev_id}"

                    # Find the verification run to check warmup/timed
                    v_run = session.exec(
                        select(Run).where(
                            Run.session_id == verify_session_id,
                            Run.device_id == dev_id,
                            Run.ai_model_id == d.ai_model_id,
                            Run.batch == d.batch,
                        )
                    ).first()
                    if v_run:
                        method = f"warm median (W={v_run.warmup_runs}, T={v_run.timed_runs}, K={v_run.inner_loop_k})"
                        print(f"  {dev_key:<8} {meas_ms:<12.3f} {method}")
                        print(f"           pstate_start={v_run.nvml_pstate_start} pstate_end={v_run.nvml_pstate_end} "
                              f"clock_start={v_run.nvml_clock_sm_start_mhz} clock_end={v_run.nvml_clock_sm_end_mhz}")
                    else:
                        print(f"  {dev_key:<8} {meas_ms:<12.3f} (no matching Run found)")
                print()

            # Stored runs for this model+batch on dml:1
            dml1 = next((d2 for d2 in devices.values() if d2.key == "dml:1"), None)
            if dml1:
                stored_runs = session.exec(
                    select(Run).where(
                        Run.ai_model_id == d.ai_model_id,
                        Run.device_id == dml1.id,
                        Run.batch == d.batch,
                        Run.unstable == False,
                        Run.provider_mismatch == False,
                        Run.session_id != None,
                    ).order_by(Run.id.desc())
                ).all()
                if stored_runs:
                    print(f"  STORED dml:1 RUNS for {model_name} B={d.batch} ({len(stored_runs)} runs):")
                    for sr in stored_runs[:5]:
                        print(f"    session={sr.session_id} median={sr.median_ms:.3f} ms "
                              f"pstate_start={sr.nvml_pstate_start} pstate_end={sr.nvml_pstate_end}")
                    print()

        # Baseline denominator check
        print("=" * 100)
        print("BASELINE DENOMINATOR CHECK")
        print("=" * 100)
        verified = [d for d in decisions if d.actual_ms is not None and d.best_device_id_actual is not None]
        print(f"Total verified decisions: {len(verified)}")

        cpu_dev = next((d2 for d2 in devices.values() if d2.key == "cpu"), None)
        rtx_dev = next((d2 for d2 in devices.values() if d2.key == "dml:1"), None)
        dml0_dev = next((d2 for d2 in devices.values() if d2.key == "dml:0"), None)

        for baseline_name, baseline_dev in [("Always-CPU", cpu_dev), ("Always-RTX", rtx_dev), ("ORT(dml:0)", dml0_dev)]:
            if not baseline_dev:
                print(f"  {baseline_name}: device not found")
                continue
            wins = 0
            counted = 0
            for vd in verified:
                ctx = json.loads(vd.context_json) if vd.context_json else {}
                m_times = {int(k): v for k, v in ctx.get("measured_times_ms", {}).items()}
                if not m_times:
                    continue
                if baseline_dev.id not in m_times:
                    print(f"  {baseline_name}: Decision {vd.id} MISSING {baseline_dev.key} from measured_times")
                    continue
                counted += 1
                t_best = min(m_times.values())
                t_base = m_times[baseline_dev.id]
                if t_base <= t_best + 1e-4:
                    wins += 1
            print(f"  {baseline_name}: {wins}/{counted} wins out of {len(verified)} verified "
                  f"(denominator mismatch: {counted != len(verified)})")


if __name__ == "__main__":
    main()
