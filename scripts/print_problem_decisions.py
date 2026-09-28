"""Print exact diagnosis for Decisions 7, 16, and 17 as requested by user."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select
from app.db import AIModel, Decision, Device, Run, engine, init_db


def main():
    init_db()
    with Session(engine) as s:
        devs = {d.id: d for d in s.exec(select(Device)).all()}
        models = {m.id: m for m in s.exec(select(AIModel)).all()}

        for did in [7, 16, 17]:
            d = s.get(Decision, did)
            m = models[d.ai_model_id]
            ctx = json.loads(d.context_json)
            cands = json.loads(d.candidates_json)
            excl = ctx.get("excluded_candidates", [])
            m_times = ctx.get("measured_times_ms", {})
            rules = ctx.get("rules", [])

            print("=" * 90)
            print(f"DECISION {d.id}: {m.name} | Batch {d.batch} | Mode {d.mode}")
            print(f"  Chosen: {devs[d.chosen_device_id].key} | Result: actual={d.actual_ms} ms, was_best={d.was_best}, regret={d.regret_pct}%")
            print(f"  Context Rules: {rules}")
            print(f"  Candidates Considered: {len(cands)}")
            for c in cands:
                print(f"    - {c.get('device_key')}: source={c.get('source')}, base={c.get('base_latency_ms')} ms, fit={c.get('fit_latency_ms')} ms, wake_pen={c.get('wake_penalty_ms')} ms, effective={c.get('effective_latency_ms')} ms, score={c.get('raw_score')}, wake_status='{c.get('wake_status')}'")
            print(f"  Excluded Candidates: {excl}")

            # Check what historical runs existed at decision time that caused exclusion
            mismatches = s.exec(
                select(Run).where(
                    Run.ai_model_id == m.id,
                    Run.output_matches_cpu == False,
                )
            ).all()
            if mismatches:
                print("  Root Cause of GPU Exclusion in Phase 5:")
                for mis in mismatches:
                    dev_key = devs[mis.device_id].key
                    print(f"    - Device {dev_key} had historical Run {mis.id} flagged with output_matches_cpu=False (max_rel_err={mis.max_rel_err}) at batch {mis.batch} in Session {mis.session_id}")

            print("  Verification Details:")
            v_sess_id = ctx.get("verification_session_id")
            print(f"    Verification Session ID: {v_sess_id}")
            print(f"    Devices measured in verification: {m_times}")
            v_runs = s.exec(select(Run).where(Run.session_id == v_sess_id)).all()
            for vr in v_runs:
                dev_key = devs[vr.device_id].key
                print(f"    Run {vr.id} on {dev_key}: warm median={vr.median_ms} ms, cold first_run={vr.first_run_ms} ms (warmups={vr.warmup_runs}, timed={vr.timed_runs}, inner_k={vr.inner_loop_k}, pstate_start={vr.nvml_pstate_start}, pstate_end={vr.nvml_pstate_end})")


if __name__ == "__main__":
    main()
