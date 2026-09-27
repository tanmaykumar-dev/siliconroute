"""Hardware power and telemetry sensor readers.

Provides robust access to NVML (NVIDIA GPUs) and Windows WMI BatteryStatus.
Every reader safely catches exceptions and returns None when metrics are
unavailable, adhering strictly to AGENTS.md Hard Rule 1 (never invent/mock numbers).
"""

import logging
import time
from typing import Any, Optional
import psutil

logger = logging.getLogger(__name__)


class NVMLReader:
    """Reader for NVIDIA GPU power, clock, temperature, and energy metrics.

    Retries initialization every 30s if unavailable instead of disabling permanently.
    """

    def __init__(self, retry_interval_s: float = 30.0) -> None:
        self.retry_interval_s = retry_interval_s
        self._initialized = False
        self._handle = None
        self._device_name: Optional[str] = None
        self._init_error: Optional[str] = None
        self._last_init_attempt: float = 0.0
        self._init_nvml()

    def _init_nvml(self) -> None:
        self._last_init_attempt = time.time()
        try:
            import pynvml
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            if count > 0:
                self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self._device_name = str(pynvml.nvmlDeviceGetName(self._handle))
                self._initialized = True
                self._init_error = None
            else:
                self._init_error = "No NVIDIA devices found"
                self._initialized = False
        except Exception as exc:
            self._init_error = f"{type(exc).__name__}: {exc}"
            self._initialized = False
            self._handle = None

    def _ensure_initialized(self) -> None:
        if not self.is_available:
            if time.time() - self._last_init_attempt >= self.retry_interval_s:
                self._init_nvml()

    @property
    def is_available(self) -> bool:
        return self._initialized and self._handle is not None

    @property
    def device_name(self) -> Optional[str]:
        return self._device_name

    @property
    def last_error(self) -> Optional[str]:
        return self._init_error

    def read_metrics(self) -> dict[str, Any]:
        """Read instantaneous GPU telemetry; returns None for any unavailable metric."""
        self._ensure_initialized()
        if not self.is_available:
            return {
                "gpu_power_w": None,
                "gpu_temp_c": None,
                "gpu_util_pct": None,
                "gpu_mem_used_mb": None,
                "gpu_pstate": None,
                "gpu_clock_sm_mhz": None,
                "gpu_error": self._init_error,
            }

        import pynvml
        h = self._handle
        out: dict[str, Any] = {}

        try:
            out["gpu_power_w"] = round(pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0, 3)
        except Exception:
            out["gpu_power_w"] = None

        try:
            out["gpu_temp_c"] = float(pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU))
        except Exception:
            out["gpu_temp_c"] = None

        try:
            out["gpu_util_pct"] = float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)
        except Exception:
            out["gpu_util_pct"] = None

        try:
            out["gpu_mem_used_mb"] = round(pynvml.nvmlDeviceGetMemoryInfo(h).used / 1e6, 2)
        except Exception:
            out["gpu_mem_used_mb"] = None

        try:
            out["gpu_pstate"] = int(pynvml.nvmlDeviceGetPerformanceState(h))
        except Exception:
            out["gpu_pstate"] = None

        try:
            out["gpu_clock_sm_mhz"] = int(pynvml.nvmlDeviceGetClockInfo(h, pynvml.NVML_CLOCK_SM))
        except Exception:
            out["gpu_clock_sm_mhz"] = None

        return out

    def get_total_energy_mj(self) -> Optional[float]:
        """Read cumulative energy counter in mJ since driver load."""
        self._ensure_initialized()
        if not self.is_available:
            return None
        import pynvml
        try:
            return float(pynvml.nvmlDeviceGetTotalEnergyConsumption(self._handle))
        except Exception:
            return None


class BatteryReader:
    """Reader for whole-laptop battery discharge rate via Windows WMI.

    Must be instantiated or called in the thread that uses it (COM is per-thread).
    """

    def __init__(self) -> None:
        self._conn = None
        self._com_initialized = False

    def _ensure_conn(self) -> None:
        if self._conn is None:
            try:
                import pythoncom
                import wmi
                pythoncom.CoInitialize()
                self._com_initialized = True
                self._conn = wmi.WMI(namespace=r"root\wmi")
            except Exception as exc:
                logger.debug("Failed to initialize WMI connection: %s", exc)
                self._conn = None

    def read(self) -> dict[str, Any]:
        """Read discharge rate in W and AC power online status."""
        self._ensure_conn()
        if self._conn is None:
            return {"discharge_w": None, "power_online": None}

        try:
            rows = self._conn.query("SELECT DischargeRate, PowerOnline FROM BatteryStatus WHERE Voltage > 0")
            if not rows:
                return {"discharge_w": None, "power_online": None}

            r = rows[0]
            power_online = bool(r.PowerOnline)
            raw_rate = r.DischargeRate or 0
            # DischargeRate is in mW (reads 0 while charging or on AC)
            discharge_w = round(raw_rate / 1000.0, 3) if not power_online and raw_rate > 0 else None

            return {
                "discharge_w": discharge_w,
                "power_online": power_online,
            }
        except Exception as exc:
            logger.debug("WMI BatteryStatus query failed: %s", exc)
            return {"discharge_w": None, "power_online": None}


# Global singleton reader for process-wide NVML access
nvml_reader = NVMLReader()
