"""Hardware power and telemetry sensor readers.

Provides robust access to NVML (NVIDIA GPUs) and Windows WMI BatteryStatus.
Every reader safely catches exceptions and returns None when metrics are
unavailable, adhering strictly to AGENTS.md Hard Rule 1 (never invent/mock numbers).
"""

import logging
import threading
import time
from typing import Any, Optional
import numpy as np
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


class NVMLMeasurementSampler:
    """Samples NVML power and temperature continuously in a background thread during active inference.
    
    Hard enforcement: Runs ONLY for NVIDIA dGPU devices. Attempts to start this sampler
    for CPU or non-NVIDIA devices raise a ValueError.
    """

    active_device_keys: list[str] = []

    def __init__(self, reader: Optional[NVMLReader] = None, sample_interval_s: float = 0.005) -> None:
        self.reader = reader or nvml_reader
        self.sample_interval_s = sample_interval_s
        self.device_key: Optional[str] = None
        self.power_samples_w: list[float] = []
        self.temp_samples_c: list[float] = []
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self, device_key: Optional[str] = None) -> None:
        self.device_key = device_key
        if device_key is not None:
            dk_lower = device_key.lower()
            if dk_lower in ("cpu", "dml:0") or "cpu" in dk_lower or "amd" in dk_lower:
                raise ValueError(f"PROHIBITED: NVMLMeasurementSampler must never run on non-NVIDIA device '{device_key}'")

        if not self.reader.is_available:
            return
        self.power_samples_w = []
        self.temp_samples_c = []
        self._stop_event.clear()
        if device_key is not None:
            NVMLMeasurementSampler.active_device_keys.append(device_key)
        self._thread = threading.Thread(target=self._run, name=f"NVMLSampler-{device_key or 'gpu'}", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            metrics = self.reader.read_metrics()
            p = metrics.get("gpu_power_w")
            t = metrics.get("gpu_temp_c")
            if p is not None:
                self.power_samples_w.append(p)
            if t is not None:
                self.temp_samples_c.append(t)
            time.sleep(self.sample_interval_s)

    def stop(self) -> dict[str, Any]:
        if self._thread is not None:
            self._stop_event.set()
            self._thread.join(timeout=1.0)
            self._thread = None
        # Collect final reading right at completion
        if self.reader.is_available:
            metrics = self.reader.read_metrics()
            p = metrics.get("gpu_power_w")
            t = metrics.get("gpu_temp_c")
            if p is not None:
                self.power_samples_w.append(p)
            if t is not None:
                self.temp_samples_c.append(t)

        med_p = round(float(np.median(self.power_samples_w)), 2) if self.power_samples_w else None
        max_p = round(float(np.max(self.power_samples_w)), 2) if self.power_samples_w else None
        med_t = round(float(np.median(self.temp_samples_c)), 1) if self.temp_samples_c else None
        max_t = round(float(np.max(self.temp_samples_c)), 1) if self.temp_samples_c else None

        return {
            "power_samples_w": self.power_samples_w,
            "temp_samples_c": self.temp_samples_c,
            "median_power_w": med_p,
            "max_power_w": max_p,
            "median_temp_c": med_t,
            "max_temp_c": max_t,
            "sample_count": len(self.power_samples_w),
        }

