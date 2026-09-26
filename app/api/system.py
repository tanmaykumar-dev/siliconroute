"""System and health API endpoints for SiliconRoute."""

import platform
from typing import Any, Optional
import winreg

from fastapi import APIRouter
import onnxruntime as ort
import psutil

router = APIRouter(tags=["system"])


def _get_cpu_name() -> str:
    """Retrieve the human-readable CPU brand string from Windows registry or platform."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        )
        val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        name = str(val).strip()
        if name:
            return name
    except Exception:
        pass
    return platform.processor() or "Unknown CPU"


def _get_nvml_info() -> dict[str, Any]:
    """Inspect NVIDIA Management Library (NVML) availability without raising."""
    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        device_names: list[str] = []
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            device_names.append(str(pynvml.nvmlDeviceGetName(h)))
        return {
            "available": True,
            "device_count": count,
            "devices": device_names,
        }
    except Exception as exc:
        return {
            "available": False,
            "device_count": 0,
            "reason": str(exc),
        }


@router.get("/api/health")
def get_health() -> dict[str, str]:
    """Health check endpoint as defined in SPEC Section 8."""
    return {"status": "ok", "version": "1.0.0"}


@router.get("/api/system")
def get_system() -> dict[str, Any]:
    """Return real host system hardware and environment specs."""
    battery = psutil.sensors_battery()
    battery_pct: Optional[float] = float(battery.percent) if battery else None
    plugged_in: Optional[bool] = bool(battery.power_plugged) if battery else None

    ram_total_gb = round(psutil.virtual_memory().total / (1024**3), 2)

    return {
        "cpu_name": _get_cpu_name(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "ram_gb": ram_total_gb,
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "ort_version": ort.__version__,
        "providers": ort.get_available_providers(),
        "nvml": _get_nvml_info(),
        "battery": battery_pct,
        "plugged_in": plugged_in,
    }
