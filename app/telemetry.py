"""Periodic hardware telemetry sampler and SSE broadcast service.

Runs a dedicated 1 Hz sampler thread reading CPU, RAM, NVML, and battery sensors.
Buffers readings in an in-memory deque, writes batches to SQLite every 10 s,
and streams live JSON samples to connected browser clients via Server-Sent Events.
"""

import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import logging
import threading
import time
from typing import Any, Optional

from fastapi import APIRouter, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
import psutil
from sqlmodel import Session

from app.config import TELEMETRY_FLUSH_S, TELEMETRY_HZ
from app.db import TelemetrySample, engine
from app.power import BatteryReader, nvml_reader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

# In-memory circular buffer for fast time-series queries
telemetry_buffer: deque[dict[str, Any]] = deque(maxlen=3600)
_buffer_lock = threading.Lock()

# SSE event stream subscribers
subscribers: set[asyncio.Queue] = set()
loop_holder: dict[str, Optional[asyncio.AbstractEventLoop]] = {"loop": None}

_sampler_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def _safe_put(q: asyncio.Queue, item: dict[str, Any]) -> None:
    """Non-blocking put into subscriber queue, dropping oldest if full."""
    if not q.full():
        q.put_nowait(item)


def publish(sample: dict[str, Any]) -> None:
    """Push sample to all active SSE subscribers from the background thread."""
    loop = loop_holder["loop"]
    if loop is not None and not loop.is_closed():
        for q in list(subscribers):
            try:
                loop.call_soon_threadsafe(_safe_put, q, sample)
            except Exception:
                pass


def sample_telemetry(battery_reader: BatteryReader) -> dict[str, Any]:
    """Capture a single instantaneous hardware snapshot."""
    now_iso = datetime.now(timezone.utc).isoformat()
    cpu_pct = float(psutil.cpu_percent(interval=None))
    ram_pct = float(psutil.virtual_memory().percent)

    cpu_freq_info = psutil.cpu_freq()
    cpu_freq_mhz = float(cpu_freq_info.current) if cpu_freq_info else None

    # Battery via psutil and WMI
    batt = psutil.sensors_battery()
    batt_pct = float(batt.percent) if batt else None
    plugged_in = bool(batt.power_plugged) if batt else None

    wmi_data = battery_reader.read()
    discharge_w = wmi_data.get("discharge_w")

    # GPU via NVML
    gpu_data = nvml_reader.read_metrics()

    return {
        "ts": now_iso,
        "cpu_pct": cpu_pct,
        "cpu_freq_mhz": cpu_freq_mhz,
        "ram_pct": ram_pct,
        "battery_pct": batt_pct,
        "plugged_in": plugged_in,
        "discharge_w": discharge_w,
        "gpu_util_pct": gpu_data.get("gpu_util_pct"),
        "gpu_power_w": gpu_data.get("gpu_power_w"),
        "gpu_temp_c": gpu_data.get("gpu_temp_c"),
        "gpu_mem_used_mb": gpu_data.get("gpu_mem_used_mb"),
        "gpu_pstate": gpu_data.get("gpu_pstate"),
        "gpu_clock_sm_mhz": gpu_data.get("gpu_clock_sm_mhz"),
    }


def sampler_loop(stop: threading.Event) -> None:
    """Background 1 Hz telemetry sampling and SQLite persistence thread."""
    logger.info("SiliconRoute telemetry sampler thread started.")
    # Prime cpu_percent
    psutil.cpu_percent(interval=None)

    battery_reader = BatteryReader()
    pending_db_samples: list[dict[str, Any]] = []
    last_flush = time.time()
    interval = 1.0 / max(TELEMETRY_HZ, 1)

    while not stop.is_set():
        t0 = time.time()
        try:
            sample = sample_telemetry(battery_reader)

            with _buffer_lock:
                telemetry_buffer.append(sample)

            publish(sample)
            pending_db_samples.append(sample)

            # Flush to SQLite every TELEMETRY_FLUSH_S seconds
            if time.time() - last_flush >= TELEMETRY_FLUSH_S:
                if pending_db_samples:
                    try:
                        with Session(engine) as session:
                            for s in pending_db_samples:
                                row = TelemetrySample(
                                    ts=s["ts"],
                                    cpu_pct=s["cpu_pct"],
                                    cpu_freq_mhz=s["cpu_freq_mhz"],
                                    ram_pct=s["ram_pct"],
                                    battery_pct=s["battery_pct"],
                                    plugged_in=s["plugged_in"],
                                    discharge_w=s["discharge_w"],
                                    gpu_util_pct=s["gpu_util_pct"],
                                    gpu_power_w=s["gpu_power_w"],
                                    gpu_temp_c=s["gpu_temp_c"],
                                    gpu_mem_used_mb=s["gpu_mem_used_mb"],
                                )
                                session.add(row)
                            session.commit()
                        pending_db_samples.clear()
                    except Exception as db_err:
                        logger.debug("Failed to flush telemetry to DB: %s", db_err)
                last_flush = time.time()

        except Exception as exc:
            logger.debug("Error in telemetry sampler loop: %s", exc)

        elapsed = time.time() - t0
        to_sleep = max(interval - elapsed, 0.05)
        time.sleep(to_sleep)

    logger.info("SiliconRoute telemetry sampler thread stopped.")


def start_sampler() -> None:
    """Start the telemetry sampler thread."""
    global _sampler_thread
    if _sampler_thread is None or not _sampler_thread.is_alive():
        _stop_event.clear()
        _sampler_thread = threading.Thread(
            target=sampler_loop,
            args=(_stop_event,),
            name="TelemetrySamplerThread",
            daemon=True,
        )
        _sampler_thread.start()


def stop_sampler() -> None:
    """Signal the telemetry sampler to stop and join."""
    _stop_event.set()
    if _sampler_thread is not None and _sampler_thread.is_alive():
        _sampler_thread.join(timeout=2.0)


# -----------------------------------------------------------------------------
# Telemetry API Routes
# -----------------------------------------------------------------------------

@router.get("/latest")
def get_latest_telemetry() -> dict[str, Any]:
    """Return the most recent telemetry sample."""
    with _buffer_lock:
        if telemetry_buffer:
            return telemetry_buffer[-1]
    # Return instantaneous sample if buffer is empty
    return sample_telemetry(BatteryReader())


@router.get("")
def get_recent_telemetry(seconds: int = Query(default=120, ge=1, le=3600)) -> list[dict[str, Any]]:
    """Return recent telemetry samples from the ring buffer within the requested seconds."""
    with _buffer_lock:
        samples = list(telemetry_buffer)

    if not samples:
        return []

    cutoff_idx = max(0, len(samples) - seconds)
    return samples[cutoff_idx:]


@router.get("/stream", response_class=EventSourceResponse)
async def telemetry_stream(request: Request):
    """Server-Sent Events (SSE) streaming live 1 Hz hardware telemetry samples."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    subscribers.add(q)
    try:
        while not await request.is_disconnected():
            try:
                sample = await asyncio.wait_for(q.get(), timeout=5.0)
                yield ServerSentEvent(data=json.dumps(sample), event="message")
            except asyncio.TimeoutError:
                yield ServerSentEvent(data="ping", event="ping")
    finally:
        subscribers.discard(q)

