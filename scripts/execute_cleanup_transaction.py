"""Atomic cleanup script for data/siliconroute.db.

Executes all test row deletions in ONE single transaction:
1. Deletes Fits on test devices
2. Deletes Runs from test sessions (both on test devices and test runs on CPU)
3. Deletes test BenchSessions
4. Deletes test AIModels (test_*)
5. Deletes test Devices (test_dev_*, dml_dup_*)
6. Verifies remaining counts:
   - cpu: 65
   - dml:0: 65
   - dml:1: 66
   - dml:2: 8 (total 204)
   - Sessions: 9, 17, 18, 32, 33, 38, 84
   - Zero test_* / dml_dup_* entities
If ANY count or condition differs, restores data/backup_before_cleanup.db immediately.
"""

import os
from pathlib import Path
import shutil
import sqlite3
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from sqlmodel import Session, select, func
from app.db import engine, Device, AIModel, BenchSession, Run, Fit, Decision
from app.config import DB_PATH

BACKUP_PATH = Path("data/backup_before_cleanup.db")
REAL_SESSION_IDS = {9, 17, 18, 32, 33, 38, 84}
REAL_DEVICE_KEYS = {"cpu", "dml:0", "dml:1", "dml:2"}


def execute_cleanup():
    assert BACKUP_PATH.exists(), f"Backup file {BACKUP_PATH} missing! Aborting cleanup."

    print("=" * 80)
    print("STARTING ATOMIC DATABASE CLEANUP IN ONE TRANSACTION")
    print(f"Target Database: {DB_PATH}")
    print(f"Safety Backup:   {BACKUP_PATH} ({BACKUP_PATH.stat().st_size} bytes)")
    print("=" * 80)

    # Apply lightweight column migrations if new fields exist
    from app.db import init_db
    init_db()

    from sqlalchemy import delete, or_

    try:
        # 1. Identify real devices
        with Session(engine) as session:
            real_devices = session.exec(select(Device).where(Device.key.in_(REAL_DEVICE_KEYS))).all()
            real_dev_ids = {d.id: d.key for d in real_devices}
            print(f"Identified {len(real_devices)} real devices: {real_dev_ids}")

        with engine.begin() as conn:
            # 2. Delete test decisions if any reference test devices or test models
            res_dec = conn.execute(
                delete(Decision).where(
                    or_(
                        ~Decision.chosen_device_id.in_(list(real_dev_ids.keys())),
                        Decision.ai_model_id.in_(select(AIModel.id).where(AIModel.name.like("test_%"))),
                    )
                )
            )
            print(f"Deleted {res_dec.rowcount} test Decision rows.")

            # 3. Delete test fits
            res_fits = conn.execute(delete(Fit).where(~Fit.device_id.in_(list(real_dev_ids.keys()))))
            print(f"Deleted {res_fits.rowcount} test Fit rows.")

            # 4. Delete all test runs (session_id is NULL or not in REAL_SESSION_IDS)
            res_runs = conn.execute(
                delete(Run).where(
                    or_(
                        Run.session_id.is_(None),
                        ~Run.session_id.in_(list(REAL_SESSION_IDS)),
                    )
                )
            )
            print(f"Deleted {res_runs.rowcount} test Run rows.")

            # 5. Delete test sessions
            res_sess = conn.execute(delete(BenchSession).where(~BenchSession.id.in_(list(REAL_SESSION_IDS))))
            print(f"Deleted {res_sess.rowcount} test BenchSession rows.")

            # 6. Delete test models
            res_models = conn.execute(delete(AIModel).where(AIModel.name.like("test_%")))
            print(f"Deleted {res_models.rowcount} test AIModel rows.")

            # 7. Delete test devices
            res_devs = conn.execute(delete(Device).where(~Device.key.in_(list(REAL_DEVICE_KEYS))))
            print(f"Deleted {res_devs.rowcount} test Device rows.")

            print("\nTransaction COMMITTED successfully.")

    except Exception as exc:
        print(f"\nERROR during cleanup transaction: {exc}")
        print("Restoring database from backup...")
        shutil.copy2(BACKUP_PATH, DB_PATH)
        print("Restored data/backup_before_cleanup.db -> data/siliconroute.db")
        sys.exit(1)

    # Post-cleanup verification
    print("\n" + "=" * 80)
    print("POST-CLEANUP VERIFICATION")
    print("=" * 80)

    with Session(engine) as session:
        # Check remaining devices
        devices = session.exec(select(Device).order_by(Device.id)).all()
        dev_map = {d.id: d.key for d in devices}
        print(f"Remaining Devices ({len(devices)}):")
        for d in devices:
            print(f"  - ID {d.id}: key='{d.key}', label='{d.label}', kind='{d.kind}', available={d.is_available}")

        # Check remaining sessions
        sessions = session.exec(select(BenchSession).order_by(BenchSession.id)).all()
        sess_ids = {s.id for s in sessions}
        print(f"\nRemaining BenchSessions ({len(sessions)}): IDs {sorted(sess_ids)}")

        # Check runs by session
        print("\nRuns per Session:")
        runs_by_session = {}
        all_runs = session.exec(select(Run).order_by(Run.id)).all()
        for r in all_runs:
            runs_by_session[r.session_id] = runs_by_session.get(r.session_id, 0) + 1
        for sid in sorted(runs_by_session.keys()):
            print(f"  - Session {sid}: {runs_by_session[sid]} runs")

        # Check runs by device
        print(f"\nTotal Runs: {len(all_runs)}")
        runs_by_dev = {}
        for r in all_runs:
            k = dev_map.get(r.device_id, f"unknown_dev_{r.device_id}")
            runs_by_dev[k] = runs_by_dev.get(k, 0) + 1
        for k in sorted(runs_by_dev.keys()):
            print(f"  - {k}: {runs_by_dev[k]} runs")

        # Check test entities
        test_dev_remaining = [d for d in devices if d.key.startswith("test") or "dup" in d.key]
        test_models_remaining = session.exec(select(AIModel).where(AIModel.name.like("test_%"))).all()
        test_sessions_remaining = [s for s in sessions if s.id not in REAL_SESSION_IDS]

        print(f"\nRemaining test devices:  {len(test_dev_remaining)}")
        print(f"Remaining test models:   {len(test_models_remaining)}")
        print(f"Remaining test sessions: {len(test_sessions_remaining)}")

        # Validation conditions
        errors = []
        if sess_ids != REAL_SESSION_IDS:
            errors.append(f"Sessions mismatch: expected {REAL_SESSION_IDS}, got {sess_ids}")
        if runs_by_dev.get("cpu") != 65:
            errors.append(f"CPU runs mismatch: expected 65, got {runs_by_dev.get('cpu')}")
        if runs_by_dev.get("dml:0") != 65:
            errors.append(f"dml:0 runs mismatch: expected 65, got {runs_by_dev.get('dml:0')}")
        if runs_by_dev.get("dml:1") != 66:
            errors.append(f"dml:1 runs mismatch: expected 66, got {runs_by_dev.get('dml:1')}")
        if runs_by_dev.get("dml:2") != 8:
            errors.append(f"dml:2 runs mismatch: expected 8, got {runs_by_dev.get('dml:2')}")
        if len(all_runs) != 204:
            errors.append(f"Total runs mismatch: expected 204, got {len(all_runs)}")
        if test_dev_remaining or test_models_remaining or test_sessions_remaining:
            errors.append("Test artifacts still remain in database!")

        if errors:
            print("\nVALIDATION FAILED!")
            for e in errors:
                print(f"  - {e}")
            print("\nRestoring database from backup...")
            shutil.copy2(BACKUP_PATH, DB_PATH)
            print("Database restored. Exiting.")
            sys.exit(1)
        else:
            print("\nALL CONDITIONS MET PERFECTLY!")
            print("Confirmed:")
            print("  - cpu:   65 runs")
            print("  - dml:0: 65 runs")
            print("  - dml:1: 66 runs")
            print("  - dml:2:  8 runs (confirmed on duplicate adapter dml:2)")
            print("  - Total: 204 genuine runs in sessions {9, 17, 18, 32, 33, 38, 84}")
            print("  - Zero rows linked to test_* or dml_dup_* entities.")
            print("=" * 80)


if __name__ == "__main__":
    execute_cleanup()
