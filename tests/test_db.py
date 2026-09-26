"""Tests for database engine, pragmas, and schema."""

from sqlalchemy import text
from sqlmodel import Session, inspect

from app.db import (
    AIModel,
    BenchSession,
    Decision,
    Device,
    Fit,
    Run,
    TelemetrySample,
    engine,
    init_db,
)


def test_sqlite_wal_pragma():
    """Verify that SQLite engine operates in WAL journal mode."""
    init_db()
    with Session(engine) as session:
        row = session.exec(text("PRAGMA journal_mode")).one()
        journal_mode = row[0]
        assert str(journal_mode).lower() == "wal", f"Expected WAL mode, got {journal_mode}"


def test_tables_created():
    """Verify that all 7 SQLModel tables are created in the database."""
    init_db()
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    expected_tables = {
        "device",
        "aimodel",
        "benchsession",
        "run",
        "telemetrysample",
        "fit",
        "decision",
    }
    assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"
