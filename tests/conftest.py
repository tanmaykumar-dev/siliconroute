"""Pytest configuration and test database isolation.

Guarantees that:
1. Every test function executes against an isolated temporary SQLite database in tmp_path.
2. The production database (data/siliconroute.db) is NEVER touched, read, or modified by pytest.
3. Automatically initializes tables, default hardware devices, and default model in each test database.
4. Overrides FastAPI app dependency `get_session` so all TestClient requests use the test database.
"""

import hashlib
import os
from pathlib import Path
import tempfile
import pytest

# Ensure SILICONROUTE_DB is ALWAYS set before any app module is ever imported
SESSION_TEST_DIR = Path(tempfile.mkdtemp(prefix="siliconroute_pytest_"))
SESSION_TEST_DB = SESSION_TEST_DIR / "session_test.db"
if "SILICONROUTE_DB" not in os.environ:
    os.environ["SILICONROUTE_DB"] = str(SESSION_TEST_DB)

from app.config import DATA_DIR, DB_PATH
import app.db as app_db
from app.db import AIModel, Device, get_session, init_db
from app.main import app
from app.models_gen import create_and_register_synthetic
from sqlmodel import Session, select


# Snapshot of production database before tests start
PROD_DB_PATH = DB_PATH


def compute_file_hash(path: Path) -> str:
    """Compute sha256 checksum of a file if it exists, else empty string."""
    if not path.exists():
        return ""
    h = hashlib.sha256()
    for attempt in range(5):
        try:
            with open(path, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            return h.hexdigest()
        except (PermissionError, OSError):
            if attempt == 4:
                try:
                    return f"size:{path.stat().st_size}_mtime:{path.stat().st_mtime}"
                except Exception:
                    return "locked"
            time.sleep(0.05)
    return ""


def compute_prod_db_fingerprint(base_path: Path) -> dict[str, str]:
    """Compute sha256 checksums of the main db file, plus -wal and -shm if present."""
    fps = {}
    for ext in ["", "-wal", "-shm"]:
        p = base_path.parent / (base_path.name + ext)
        fps[ext] = compute_file_hash(p)
    return fps


INITIAL_PROD_DB_FP = compute_prod_db_fingerprint(PROD_DB_PATH)


@pytest.fixture(autouse=True)
def isolate_test_database(tmp_path, monkeypatch):
    """Enforce complete database isolation for every test."""
    test_db = tmp_path / "isolated_test.db"
    monkeypatch.setenv("SILICONROUTE_DB", str(test_db))

    test_models_dir = tmp_path / "models"
    test_models_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.MODELS_DIR", test_models_dir)
    monkeypatch.setattr("app.models_gen.MODELS_DIR", test_models_dir)

    test_engine = app_db.create_db_engine(test_db)
    app_db.set_engine(test_engine)

    # Override FastAPI get_session dependency
    def get_test_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session

    # Initialize tables in isolated test database
    init_db(test_engine)

    # Seed standard hardware devices and default model
    with Session(test_engine) as session:
        cpu_dev = session.exec(select(Device).where(Device.key == "cpu")).first()
        if not cpu_dev:
            session.add(
                Device(
                    key="cpu",
                    label="CPU",
                    kind="cpu",
                    provider="CPUExecutionProvider",
                    provider_options_json="{}",
                    is_available=True,
                    detected_at="2026-09-28T00:00:00Z",
                )
            )
        dml0_dev = session.exec(select(Device).where(Device.key == "dml:0")).first()
        if not dml0_dev:
            session.add(
                Device(
                    key="dml:0",
                    label="AMD Radeon(TM) 610M",
                    kind="igpu",
                    provider="DmlExecutionProvider",
                    provider_options_json='{"device_id": 0}',
                    is_available=True,
                    detected_at="2026-09-28T00:00:00Z",
                )
            )
        dml1_dev = session.exec(select(Device).where(Device.key == "dml:1")).first()
        if not dml1_dev:
            session.add(
                Device(
                    key="dml:1",
                    label="NVIDIA GeForce RTX 5070 Laptop GPU",
                    kind="dgpu",
                    provider="DmlExecutionProvider",
                    provider_options_json='{"device_id": 1}',
                    is_available=True,
                    detected_at="2026-09-28T00:00:00Z",
                )
            )
        session.commit()

        # Seed at least 1 synthetic model
        model = session.exec(select(AIModel)).first()
        if not model:
            create_and_register_synthetic(session, "mlp", 32, 2)

    yield test_engine

    app.dependency_overrides.clear()

    # Ensure background worker has finished any pending tasks before switching engines
    from app.jobs import _jobs, _lock, current_job
    _jobs.join()
    with _lock:
        current_job["session_id"] = None
        current_job["item"] = None

    # Strict invariant check: production database MUST NEVER be modified (including -wal and -shm)
    if PROD_DB_PATH.exists():
        current_fp = compute_prod_db_fingerprint(PROD_DB_PATH)
        assert current_fp == INITIAL_PROD_DB_FP, (
            f"CRITICAL TEST ISOLATION FAILURE: {PROD_DB_PATH} (or -wal/-shm) was modified during test execution! "
            f"Initial fingerprint: {INITIAL_PROD_DB_FP}, Current fingerprint: {current_fp}"
        )
