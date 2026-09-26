"""Database module for SiliconRoute.

Configures SQLite with WAL pragmas via SQLAlchemy/SQLModel and defines
all data tables specified in SPEC Section 4.
"""

from collections.abc import Generator
from pathlib import Path
from typing import Optional
from sqlalchemy import Index, event
from sqlmodel import Field, Session, SQLModel, create_engine

from app.config import DATA_DIR, DB_PATH

# Ensure local data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Normalized SQLite database URL
sqlite_url = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(
    sqlite_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_pragmas(dbapi_conn, _record) -> None:
    """Set SQLite pragmas for high concurrency and resilience."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")    # readers never block the writer
    cur.execute("PRAGMA synchronous=NORMAL")  # recommended with WAL
    cur.execute("PRAGMA busy_timeout=5000")   # wait up to 5 s instead of 'database is locked'
    cur.execute("PRAGMA foreign_keys=ON")     # enforce relational integrity
    cur.close()


# -----------------------------------------------------------------------------
# SQLModel Table Definitions (SPEC Section 4)
# -----------------------------------------------------------------------------

class Device(SQLModel, table=True):
    """Represents a measured hardware compute device (CPU, GPU, NPU)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)  # e.g. "cpu", "dml:0", "dml:1", "qnn:0"
    label: str                                 # User-assigned friendly name
    kind: str                                  # cpu | igpu | dgpu | npu | software | unknown
    provider: str                              # CPUExecutionProvider | DmlExecutionProvider | ...
    provider_options_json: str = "{}"          # Serialized options dict
    is_available: bool = True
    unavailable_reason: Optional[str] = None   # Reason when is_available is false (e.g. duplicate)
    detected_at: str                           # ISO UTC timestamp


class AIModel(SQLModel, table=True):
    """Represents an ONNX neural network model (synthetic or scanned)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    family: str                                # mlp | conv | attn | file
    source: str                                # synthetic | file
    path: str
    sha256: str
    params: int
    flops_per_sample: Optional[float] = None
    weight_bytes: int
    size_mb: float
    precision: str                             # fp32 | fp16 | int8
    input_shape_json: str
    created_at: str


class BenchSession(SQLModel, table=True):
    """Tracks a sequence of benchmarks or energy measurements."""
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str                                  # latency | energy | verify
    status: str                                # queued | running | done | failed | cancelled
    config_json: str                           # Serialized job parameters
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    plugged_in: Optional[bool] = None
    battery_start: Optional[float] = None
    battery_end: Optional[float] = None
    ram_pct_start: Optional[float] = None
    power_scheme: Optional[str] = None
    notes: Optional[str] = None
    error: Optional[str] = None


class Run(SQLModel, table=True):
    """A single measurement run for a (model, device, batch) tuple."""
    __table_args__ = (
        Index("ix_run_model_device_batch", "ai_model_id", "device_id", "batch"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: Optional[int] = Field(default=None, foreign_key="benchsession.id")
    ai_model_id: int = Field(foreign_key="aimodel.id", index=True)
    device_id: int = Field(foreign_key="device.id", index=True)
    provider_used: str
    provider_mismatch: bool = False
    batch: int = Field(index=True)
    intra_op_threads: int
    warmup_runs: int
    timed_runs: int
    inner_loop_k: int = Field(default=1)       # Number of runs timed together in inner loop
    session_create_ms: float
    first_run_ms: Optional[float] = None       # Cold-start latency (1st inference after creation)
    median_ms: float
    p10_ms: float
    p90_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float
    stdev_ms: float
    cv: float                                  # Coefficient of variation (stdev / mean)
    spread: float = Field(default=0.0)         # Robust spread: (p90 - p10) / median
    ci_rel: Optional[float] = None             # Bootstrap 95% CI half-width / median
    ci_low_ms: Optional[float] = None          # Bootstrap 95% CI 2.5 percentile
    ci_high_ms: Optional[float] = None         # Bootstrap 95% CI 97.5 percentile
    unstable: bool                             # True if ci_rel > CI_THRESHOLD (0.10)
    throughput_per_s: float
    raw_ms_json: str
    output_matches_cpu: Optional[bool] = None
    max_rel_err: Optional[float] = None
    output_hash: Optional[str] = None          # SHA256 of inference output for duplicate detection
    nvml_pstate_start: Optional[int] = None    # NVIDIA GPU P-state at timing start
    nvml_pstate_end: Optional[int] = None      # NVIDIA GPU P-state at timing end
    nvml_clock_sm_start_mhz: Optional[int] = None # NVIDIA SM clock (MHz) at timing start
    nvml_clock_sm_end_mhz: Optional[int] = None   # NVIDIA SM clock (MHz) at timing end
    gpu_temp_start_c: Optional[float] = None
    gpu_temp_end_c: Optional[float] = None
    plugged_in: Optional[bool] = None
    battery_pct: Optional[float] = None
    energy_mj_per_inf: Optional[float] = None
    energy_method: Optional[str] = None
    idle_w: Optional[float] = None
    load_w: Optional[float] = None
    created_at: str


class TelemetrySample(SQLModel, table=True):
    """A 1 Hz periodic hardware telemetry reading."""
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: str = Field(index=True)
    session_id: Optional[int] = Field(default=None, foreign_key="benchsession.id")
    cpu_pct: float
    cpu_freq_mhz: Optional[float] = None
    ram_pct: float
    battery_pct: Optional[float] = None
    plugged_in: Optional[bool] = None
    discharge_w: Optional[float] = None
    gpu_util_pct: Optional[float] = None
    gpu_power_w: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    gpu_mem_used_mb: Optional[float] = None


class Fit(SQLModel, table=True):
    """Learned hardware predictor parameters for a device."""
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id", index=True)
    target: str                                # latency | energy
    model_form: str                            # roofline | roofline_cache | loglinear
    loo_mape_all_json: str
    coef_json: str
    n_samples: int
    r2_log: float
    loo_mape_pct: float
    trained_at: str
    is_active: bool = True


class Decision(SQLModel, table=True):
    """Router decision log and verification results."""
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: str
    ai_model_id: int = Field(foreign_key="aimodel.id")
    batch: int
    mode: str                                  # fastest | battery | balanced | cool
    power_budget_w: Optional[float] = None
    context_json: str
    candidates_json: str
    chosen_device_id: int = Field(foreign_key="device.id")
    explored: bool = False
    reason: str
    actual_ms: Optional[float] = None
    best_device_id_actual: Optional[int] = None
    was_best: Optional[bool] = None
    regret_pct: Optional[float] = None


def _migrate_columns(target_engine) -> None:
    """Ensure existing SQLite tables have newly added columns."""
    from sqlalchemy import text
    try:
        with target_engine.connect() as conn:
            # Check run columns
            run_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(run)")).fetchall()}
            if run_cols:
                new_run_cols = [
                    ("inner_loop_k", "INTEGER DEFAULT 1"),
                    ("spread", "FLOAT DEFAULT 0.0"),
                    ("output_hash", "TEXT"),
                    ("first_run_ms", "FLOAT"),
                    ("ci_rel", "FLOAT"),
                    ("ci_low_ms", "FLOAT"),
                    ("ci_high_ms", "FLOAT"),
                    ("nvml_pstate_start", "INTEGER"),
                    ("nvml_pstate_end", "INTEGER"),
                    ("nvml_clock_sm_start_mhz", "INTEGER"),
                    ("nvml_clock_sm_end_mhz", "INTEGER"),
                ]
                for col_name, col_type in new_run_cols:
                    if col_name not in run_cols:
                        conn.execute(text(f"ALTER TABLE run ADD COLUMN {col_name} {col_type}"))

            # Check device columns
            dev_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(device)")).fetchall()}
            if dev_cols:
                if "unavailable_reason" not in dev_cols:
                    conn.execute(text("ALTER TABLE device ADD COLUMN unavailable_reason TEXT"))

            conn.commit()
    except Exception:
        pass


def init_db(engine_instance=None) -> None:
    """Create all SQLModel tables in SQLite and apply lightweight column migrations."""
    target_engine = engine_instance or engine
    SQLModel.metadata.create_all(target_engine)
    _migrate_columns(target_engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a short-lived DB session."""
    with Session(engine) as session:
        yield session
