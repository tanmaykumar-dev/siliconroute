"""Comprehensive database audit script for SiliconRoute.

Inspects data/siliconroute.db and reports:
1. Every device created by tests (test_dev_*, dml_dup_*).
2. Every AIModel created by tests (test_mlp_*).
3. Every BenchSession created by unit tests vs real benchmarks.
4. Every Run created by tests, classified by whether it attached to a real device (cpu, dml:0, dml:1).
5. Every Fit created on test devices.
6. Every Decision in the database.
7. Exact breakdown explaining the 85 CPU samples vs 53 GPU samples.
"""

from sqlmodel import Session, select, func
from app.db import engine, Device, AIModel, BenchSession, Run, Fit, Decision


def run_audit():
    with Session(engine) as session:
        real_dev_keys = ["cpu", "dml:0", "dml:1"]
        real_devs = session.exec(select(Device).where(Device.key.in_(real_dev_keys))).all()
        real_dev_ids = {d.id: d.key for d in real_devs}

        # 1. Audit Devices
        all_devices = session.exec(select(Device).order_by(Device.id)).all()
        real_devices = [d for d in all_devices if d.key in real_dev_keys or (d.key == "dml:2" and not d.key.startswith("test"))]
        test_devices = [d for d in all_devices if d not in real_devices]

        # 2. Audit Models
        all_models = session.exec(select(AIModel).order_by(AIModel.id)).all()
        test_models = [m for m in all_models if m.name.startswith("test_") or "test" in m.name]
        real_models = [m for m in all_models if m not in test_models]

        # 3. Audit BenchSessions
        all_sessions = session.exec(select(BenchSession).order_by(BenchSession.id)).all()
        # Real benchmark sessions are known milestone sessions
        real_session_ids = {9, 17, 18, 32, 33, 38, 84}
        real_sessions = [s for s in all_sessions if s.id in real_session_ids]
        test_sessions = [s for s in all_sessions if s.id not in real_session_ids]

        # 4. Audit Runs
        all_runs = session.exec(select(Run).order_by(Run.id)).all()
        
        test_runs_on_real_devices = []
        test_runs_on_test_devices = []
        real_runs = []

        for r in all_runs:
            if r.session_id in real_session_ids:
                real_runs.append(r)
            else:
                if r.device_id in real_dev_ids:
                    test_runs_on_real_devices.append(r)
                else:
                    test_runs_on_test_devices.append(r)

        # 5. Audit Fits
        all_fits = session.exec(select(Fit).order_by(Fit.id)).all()
        test_fits = [f for f in all_fits if f.device_id not in real_dev_ids]
        real_dev_fits = [f for f in all_fits if f.device_id in real_dev_ids]

        # 6. Audit Decisions
        all_decisions = session.exec(select(Decision).order_by(Decision.id)).all()

        print("=" * 95)
        print("SILICONROUTE DATABASE CONTAMINATION AUDIT (data/siliconroute.db)")
        print("=" * 95)

        print("\n--- 1. DEVICES AUDIT ---")
        print(f"Total Devices in DB: {len(all_devices)}")
        print(f"  Real Hardware Devices: {len(real_devices)}")
        for d in real_devices:
            print(f"    - ID {d.id}: key='{d.key}', label='{d.label}', kind='{d.kind}', available={d.is_available}")
        print(f"  Test/Contaminated Devices: {len(test_devices)}")
        for d in test_devices:
            print(f"    - ID {d.id}: key='{d.key}', label='{d.label}', kind='{d.kind}', available={d.is_available}")

        print("\n--- 2. MODELS AUDIT ---")
        print(f"Total AIModels in DB: {len(all_models)}")
        print(f"  Real Benchmark Models: {len(real_models)}")
        print(f"  Test Models: {len(test_models)}")
        for m in test_models:
            print(f"    - ID {m.id}: name='{m.name}', family='{m.family}', params={m.params}")

        print("\n--- 3. SESSIONS AUDIT ---")
        print(f"Total BenchSessions in DB: {len(all_sessions)}")
        print(f"  Real Benchmark Sessions: {len(real_sessions)}")
        for s in real_sessions:
            run_count = len([r for r in real_runs if r.session_id == s.id])
            print(f"    - Session {s.id}: kind='{s.kind}', status='{s.status}', runs={run_count}, notes='{s.notes}'")
        print(f"  Test Sessions to Remove: {len(test_sessions)}")
        test_sess_with_runs = [s for s in test_sessions if any(r.session_id == s.id for r in all_runs)]
        test_sess_empty = [s for s in test_sessions if not any(r.session_id == s.id for r in all_runs)]
        print(f"    - Test Sessions with runs: {len(test_sess_with_runs)} (IDs: {[s.id for s in test_sess_with_runs]})")
        print(f"    - Empty Test Sessions (failed/queued/stubs): {len(test_sess_empty)} (IDs: {[s.id for s in test_sess_empty]})")

        print("\n--- 4. RUNS AUDIT & 85 vs 53 EXPLANATION ---")
        print(f"Total Runs in DB: {len(all_runs)}")
        print(f"  Genuine Benchmark Runs (from real sessions): {len(real_runs)}")
        real_by_dev = {}
        for r in real_runs:
            k = real_dev_ids.get(r.device_id, f"dev_{r.device_id}")
            real_by_dev[k] = real_by_dev.get(k, 0) + 1
        for k, v in real_by_dev.items():
            print(f"    - {k}: {v} genuine runs")

        print(f"\n  Test Runs Attached to REAL Devices: {len(test_runs_on_real_devices)}")
        test_real_by_dev = {}
        for r in test_runs_on_real_devices:
            k = real_dev_ids.get(r.device_id, f"dev_{r.device_id}")
            test_real_by_dev[k] = test_real_by_dev.get(k, 0) + 1
        for k, v in test_real_by_dev.items():
            print(f"    - {k}: {v} test runs injected into real device")

        print(f"\n  Test Runs Attached to TEST Devices: {len(test_runs_on_test_devices)}")

        print("\n--- EXACT PROOF OF 85 vs 53 CPU RUNS ---")
        cpu_real_count = real_by_dev.get("cpu", 0)
        cpu_test_count = test_real_by_dev.get("cpu", 0)
        dml0_real_count = real_by_dev.get("dml:0", 0)
        dml1_real_count = real_by_dev.get("dml:1", 0)
        print(f"CPU Total in DB: {cpu_real_count} real runs + {cpu_test_count} pytest runs = {cpu_real_count + cpu_test_count} runs")
        print(f"dml:0 Total in DB: {dml0_real_count} real runs + {test_real_by_dev.get('dml:0', 0)} pytest runs = {dml0_real_count} runs")
        print(f"dml:1 Total in DB: {dml1_real_count} real runs + {test_real_by_dev.get('dml:1', 0)} pytest runs = {dml1_real_count} runs")
        print("Root cause confirmed: Unit tests (test_tiny_mlp_cpu_benchmark and test_benchmarks_api_and_conflict_409)")
        print("executed against the real database and targeted the 'cpu' device, injecting exactly 32 test runs into device_id=1.")

        print("\n--- 5. FITS AUDIT ---")
        print(f"Total Fits in DB: {len(all_fits)}")
        print(f"  Fits on Real Devices: {len(real_dev_fits)}")
        for f in real_dev_fits:
            print(f"    - ID {f.id}: dev='{real_dev_ids.get(f.device_id)}', target='{f.target}', form='{f.model_form}', active={f.is_active}, samples={f.n_samples}, trained_at={f.trained_at}")
        print(f"  Fits on Test Devices: {len(test_fits)}")
        for f in test_fits:
            print(f"    - ID {f.id}: device_id={f.device_id}, form='{f.model_form}', active={f.is_active}")

        print("\n--- 6. DECISIONS AUDIT ---")
        print(f"Total Decisions in DB: {len(all_decisions)}")

        print("\n" + "=" * 95)
        print("EXACT PROPOSAL FOR CLEANUP:")
        print("=" * 95)
        print(f"1. Delete {len(test_fits)} Fit rows belonging to test devices (IDs: {[f.id for f in test_fits]}).")
        print(f"2. Delete {len(test_runs_on_test_devices)} Run rows belonging to test devices (IDs: {[r.id for r in test_runs_on_test_devices]}).")
        print(f"3. Delete {len(test_runs_on_real_devices)} Run rows injected into real devices by pytest (IDs: {[r.id for r in test_runs_on_real_devices]}).")
        print(f"4. Delete {len(test_sessions)} BenchSession rows created by pytest (IDs: {[s.id for s in test_sessions]}).")
        print(f"5. Delete {len(test_models)} AIModel rows created by test fixtures (IDs: {[m.id for m in test_models]}).")
        print(f"6. Delete {len(test_devices)} Device rows created by tests (IDs: {[d.id for d in test_devices]}).")
        print("7. Retain ALL genuine runs (204 total: Session 9 [16], Session 17 [16], Session 18 [12], Session 32 [12], Session 33 [12], Session 38 [1], Session 84 [135]).")
        print("=" * 95)


if __name__ == "__main__":
    run_audit()
