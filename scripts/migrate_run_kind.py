"""Database migration script for SiliconRoute Phase 6: run_kind, nullable unstable, WorkloadMeasurement columns, and cleanup."""

import sqlite3
from pathlib import Path

def migrate():
    db_path = Path("data/siliconroute.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. Check if unstable has NOT NULL in run
    table_sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='run'").fetchone()[0]
    has_not_null_unstable = "unstable BOOLEAN NOT NULL" in table_sql or "unstable INTEGER NOT NULL" in table_sql

    if has_not_null_unstable:
        print("Migrating run table to make unstable nullable...")
        c.execute("PRAGMA foreign_keys=OFF")
        
        # Get list of existing columns in run
        cols_info = c.execute("PRAGMA table_info(run)").fetchall()
        col_names = [col[1] for col in cols_info]
        cols_str = ", ".join(col_names)
        
        # Build create table statement for run_new with unstable nullable
        # Replace 'unstable BOOLEAN NOT NULL' with 'unstable BOOLEAN'
        new_sql = table_sql.replace("unstable BOOLEAN NOT NULL", "unstable BOOLEAN")
        new_sql = new_sql.replace("unstable INTEGER NOT NULL", "unstable INTEGER")
        new_sql = new_sql.replace("CREATE TABLE run (", "CREATE TABLE run_new (", 1)
        new_sql = new_sql.replace('CREATE TABLE "run" (', 'CREATE TABLE "run_new" (', 1)
        
        c.execute(new_sql)
        c.execute(f"INSERT INTO run_new ({cols_str}) SELECT {cols_str} FROM run")
        c.execute("DROP TABLE run")
        c.execute("ALTER TABLE run_new RENAME TO run")
        
        # Recreate indexes
        c.execute("CREATE INDEX IF NOT EXISTS ix_run_ai_model_id ON run (ai_model_id)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_run_device_id ON run (device_id)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_run_batch ON run (batch)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_run_model_device_batch ON run (ai_model_id, device_id, batch)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_run_kind ON run (run_kind)")
        c.execute("PRAGMA foreign_keys=ON")
        fk_check = c.execute("PRAGMA foreign_key_check").fetchall()
        if fk_check:
            raise RuntimeError(f"Foreign key violations after migration: {fk_check}")
        print("Successfully migrated run table.")

    # 2. Add columns to workloadmeasurement if missing
    wm_cols = [r[1] for r in c.execute("PRAGMA table_info(workloadmeasurement)").fetchall()]
    if "decision_id" not in wm_cols:
        c.execute("ALTER TABLE workloadmeasurement ADD COLUMN decision_id INTEGER")
        print("Added decision_id to workloadmeasurement")
    if "pstate_before" not in wm_cols:
        c.execute("ALTER TABLE workloadmeasurement ADD COLUMN pstate_before INTEGER")
        print("Added pstate_before to workloadmeasurement")

    # 3. Backfill run_kind and unstable
    c.execute("""
        UPDATE run
        SET run_kind = 'single_cold', unstable = NULL
        WHERE timed_runs = 1 AND warmup_runs = 0
    """)
    print("Updated single_cold runs:", c.rowcount)

    c.execute("""
        UPDATE run
        SET run_kind = 'energy', unstable = NULL
        WHERE energy_method IS NOT NULL OR session_id = 38
    """)
    print("Updated energy runs:", c.rowcount)

    c.execute("""
        UPDATE run
        SET run_kind = 'verify_sustained'
        WHERE session_id IN (SELECT id FROM benchsession WHERE kind = 'verify')
          AND timed_runs >= 10
    """)
    print("Updated verify_sustained runs:", c.rowcount)

    c.execute("""
        UPDATE run
        SET run_kind = 'sustained'
        WHERE session_id IN (SELECT id FROM benchsession WHERE kind = 'latency')
          AND (energy_method IS NULL AND session_id != 38)
    """)
    print("Updated sustained runs:", c.rowcount)

    # For safety: any run with timed_runs < 10 gets unstable = NULL
    c.execute("""
        UPDATE run
        SET unstable = NULL
        WHERE timed_runs < 10
    """)
    print("Ensured unstable is NULL for timed_runs < 10:", c.rowcount)

    # Clean unverified UI test decisions >= 117
    c.execute("DELETE FROM decision WHERE id >= 117")
    print("Deleted unverified test decisions >= 117:", c.rowcount)

    conn.commit()

    # Print verification summary
    print("--- Verification Summary ---")
    total_runs = c.execute("SELECT COUNT(*) FROM run").fetchone()[0]
    print(f"Total runs in DB: {total_runs}")
    for row in c.execute("SELECT run_kind, COUNT(*), SUM(CASE WHEN unstable IS NULL THEN 1 ELSE 0 END) FROM run GROUP BY run_kind"):
        print(f"run_kind={row[0]}: count={row[1]}, unstable_is_null={row[2]}")
    dec_info = c.execute("SELECT COUNT(*), MIN(id), MAX(id) FROM decision").fetchone()
    print(f"Remaining decisions: count={dec_info[0]}, min_id={dec_info[1]}, max_id={dec_info[2]}")
    conn.close()

if __name__ == "__main__":
    migrate()
