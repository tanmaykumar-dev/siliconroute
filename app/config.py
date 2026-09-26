"""SiliconRoute configuration constants.

Centralized constants defining benchmark runs, hardware models,
timeouts, and routing parameters as specified in SPEC Section 10.
"""

from pathlib import Path

# Random seed for reproducible synthetic weights and inputs
SEED: int = 1234

# Benchmark run parameters
WARMUP_RUNS: int = 5
TIMED_RUNS: int = 30
VERIFY_RUNS: int = 10
COOLDOWN_S: int = 2

# Stability detection threshold (coefficient of variation = stdev / mean)
UNSTABLE_CV: float = 0.15
EXCLUDE_UNSTABLE: bool = True

# Energy measurement windows (in seconds)
IDLE_WINDOW_S: int = 15
LOAD_WINDOW_S: int = 30
SETTLE_S: int = 5

# Identification test duration (seconds)
IDENTIFY_S: int = 8

# Hardware model fitting parameters
MIN_FIT_SAMPLES: int = 6
REFIT_EVERY: int = 10

# Router exploration and margin parameters
EPSILON: float = 0.10
EXPLORE_MARGIN: float = 0.20

# Battery and temperature thresholds
LOW_BATTERY_PCT: int = 30
HOT_GPU_C: int = 75
MAX_GPU_C: int = 87

# Telemetry sampling and database persistence intervals
TELEMETRY_HZ: int = 1
TELEMETRY_FLUSH_S: int = 10

# Model generation and sizing constraints
MAX_WEIGHT_MB: int = 300
BATCHES: list[int] = [1, 8, 32]
CPU_CACHE_MB: int = 64
GPU_CACHE_MB: int = 0

# File system paths
BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = BASE_DIR / "data"
MODELS_DIR: Path = BASE_DIR / "models"
DB_PATH: Path = DATA_DIR / "siliconroute.db"
