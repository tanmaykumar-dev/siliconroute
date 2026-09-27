"""Tests for test database isolation and production database protection."""

import hashlib
import os
from pathlib import Path
from sqlmodel import Session, select

from app.config import DB_PATH
import app.db as app_db
from app.db import Device


def test_pytest_never_touches_real_database():
    """Verify that tests execute exclusively in an isolated temporary database.

    Fails immediately if:
    1. SILICONROUTE_DB environment variable is missing or points to the production DB.
    2. engine database URL matches the production database path.
    3. Writing a canary record into the active test session leaks into data/siliconroute.db.
    """
    env_db = os.environ.get("SILICONROUTE_DB")
    assert env_db is not None, "SILICONROUTE_DB environment variable must be set during tests"
    assert Path(env_db).resolve() != DB_PATH.resolve(), (
        f"Test database must not point to production database {DB_PATH}"
    )

    # Verify engine URL points to isolated DB
    engine_url_str = str(app_db.engine.url)
    assert DB_PATH.name not in engine_url_str or "isolated_test" in engine_url_str or "tmp" in engine_url_str.lower(), (
        f"Engine URL {engine_url_str} appears to target production database!"
    )

    # Read production DB hash before write
    if DB_PATH.exists():
        with open(DB_PATH, "rb") as f:
            h_before = hashlib.sha256(f.read()).hexdigest()
    else:
        h_before = ""

    # Write a canary row into test DB
    with Session(app_db.engine) as session:
        canary = Device(
            key="isolation_canary_test_device",
            label="Isolation Canary",
            kind="unknown",
            provider="CPUExecutionProvider",
            provider_options_json="{}",
            is_available=True,
            detected_at="2026-09-28T00:00:00Z",
        )
        session.add(canary)
        session.commit()
        session.refresh(canary)
        assert canary.id is not None

    # Verify production DB is completely untouched
    if DB_PATH.exists():
        with open(DB_PATH, "rb") as f:
            h_after = hashlib.sha256(f.read()).hexdigest()
        assert h_before == h_after, "Production database was modified during test write!"


def test_production_db_guard_raises_under_pytest():
    """Verify that create_db_engine refuses to connect to production database during pytest."""
    import pytest
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION"):
        app_db.create_db_engine(DB_PATH)
