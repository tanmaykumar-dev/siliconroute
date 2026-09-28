"""Energy measurement engine for SiliconRoute.

Implements SPEC Section 2.2:
- Whole-laptop battery discharge method via WMI (only when unplugged).
- GPU-board energy counter via NVML (for NVIDIA GPUs, works plugged in).
- Idle baselining and load window accounting.
"""

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Optional

import numpy as np
from sqlmodel import Session

from app.config import IDLE_WINDOW_S, LOAD_WINDOW_S, SETTLE_S
from app.db import AIModel, BenchSession, Device, Run, engine
from app.devices import make_session
from app.power import BatteryReader, nvml_reader

logger = logging.getLogger(__name__)


def measure_idle_battery_w(duration_s: int = IDLE_WINDOW_S) -> Optional[float]:
    """Sample idle baseline discharge rate over duration_s seconds."""
    reader = BatteryReader()
    samples: list[float] = []
    t_end = time.time() + duration_s

    while time.time() < t_end:
        data = reader.read()
        w = data.get("discharge_w")
        if w is not None and w > 0:
            samples.append(w)
        time.sleep(1.0)

    return float(np.median(samples)) if samples else None


def run_energy_measurement(
    session: Session,
    bench_session_id: int,
    model: AIModel,
    device: Device,
    batch: int,
    idle_baseline_w: Optional[float] = None,
    load_duration_s: int = LOAD_WINDOW_S,
    settle_s: int = SETTLE_S,
) -> Run:
    """Execute an energy benchmark window for (model, device, batch)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    device_opts = json.loads(device.provider_options_json or "{}")
    device_id = device_opts.get("device_id")

    # 1. Prepare session and fixed input
    sess = make_session(model.path, device.provider, device_id=device_id, device=device)
    inp_meta = sess.get_inputs()[0]
    inp_name = inp_meta.name
    raw_shape = inp_meta.shape
    concrete_shape = [batch if (i == 0 or d is None or isinstance(d, str) or d < 1) else int(d) for i, d in enumerate(raw_shape)]
    inp_tensor = np.ones(concrete_shape, dtype=np.float32)
    feed_dict = {inp_name: inp_tensor}

    battery_reader = BatteryReader()
    is_nvidia_gpu = (device.provider == "DmlExecutionProvider" and nvml_reader.is_available and "nvidia" in (device.label or "").lower())

    # 2. Before-load energy counters
    nvml_energy_before = nvml_reader.get_total_energy_mj() if is_nvidia_gpu else None

    # 3. Load window loop
    t_start = time.time()
    t_settle_end = t_start + settle_s
    t_window_end = t_start + load_duration_s

    counted_inferences = 0
    counted_battery_samples: list[float] = []
    nvml_power_samples_w: list[float] = []
    last_sample_t = 0.0

    while time.time() < t_window_end:
        sess.run(None, feed_dict)
        now = time.time()

        if now >= t_settle_end:
            counted_inferences += 1

            # Sample battery / power once per second
            if now - last_sample_t >= 1.0:
                last_sample_t = now
                batt_data = battery_reader.read()
                dw = batt_data.get("discharge_w")
                if dw is not None:
                    counted_battery_samples.append(dw)

                if is_nvidia_gpu:
                    gpu_data = nvml_reader.read_metrics()
                    gw = gpu_data.get("gpu_power_w")
                    if gw is not None:
                        nvml_power_samples_w.append(gw)

    counted_duration_s = max(t_window_end - t_settle_end, 1.0)
    nvml_energy_after = nvml_reader.get_total_energy_mj() if is_nvidia_gpu else None

    # 4. Energy calculations
    energy_mj_per_inf: Optional[float] = None
    energy_above_idle_mj_per_inf: Optional[float] = None
    energy_method: Optional[str] = None
    idle_w: Optional[float] = idle_baseline_w
    load_w: Optional[float] = None

    if nvml_energy_before is not None and nvml_energy_after is not None and nvml_energy_after >= nvml_energy_before:
        # NVML hardware energy counter (mJ)
        delta_mj = nvml_energy_after - nvml_energy_before
        if counted_inferences > 0:
            energy_mj_per_inf = round(delta_mj / counted_inferences, 3)
            energy_method = "nvml_counter"
            if idle_baseline_w is not None:
                idle_energy_mj = idle_baseline_w * counted_duration_s * 1000.0
                delta_above_idle_mj = max(delta_mj - idle_energy_mj, 0.0)
                energy_above_idle_mj_per_inf = round(delta_above_idle_mj / counted_inferences, 3)
        if nvml_power_samples_w:
            load_w = float(np.median(nvml_power_samples_w))
    elif counted_battery_samples and idle_baseline_w is not None:
        # Whole-laptop battery delta method
        load_w = float(np.median(counted_battery_samples))
        delta_w = max(load_w - idle_baseline_w, 0.0)
        if counted_inferences > 0:
            total_energy_mj = (load_w * counted_duration_s * 1000.0)
            energy_mj_per_inf = round(total_energy_mj / counted_inferences, 3)
            energy_above_idle_mj_per_inf = round((delta_w * counted_duration_s * 1000.0) / counted_inferences, 3)
            energy_method = "battery_delta"

    # Store run record
    run = Run(
        session_id=bench_session_id,
        ai_model_id=model.id,
        device_id=device.id,
        provider_used=device.provider,
        provider_mismatch=False,
        batch=batch,
        intra_op_threads=1,
        warmup_runs=0,
        timed_runs=counted_inferences,
        inner_loop_k=1,
        session_create_ms=0.0,
        median_ms=round((counted_duration_s * 1000.0) / max(counted_inferences, 1), 3),
        p10_ms=0.0,
        p90_ms=0.0,
        mean_ms=0.0,
        min_ms=0.0,
        max_ms=0.0,
        stdev_ms=0.0,
        cv=0.0,
        spread=0.0,
        unstable=False,
        throughput_per_s=round(counted_inferences / counted_duration_s, 2),
        raw_ms_json="[]",
        energy_mj_per_inf=energy_mj_per_inf,
        energy_above_idle_mj_per_inf=energy_above_idle_mj_per_inf,
        energy_method=energy_method,
        idle_w=round(idle_w, 3) if idle_w is not None else None,
        load_w=round(load_w, 3) if load_w is not None else None,
        created_at=now_iso,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def execute_energy_job(
    bench_session_id: int,
    model_ids: list[int],
    device_ids: list[int],
    batches: list[int],
    progress_state: dict[str, Any],
) -> None:
    """Worker task executing energy measurements for a session."""
    with Session(engine) as session:
        bench_sess = session.get(BenchSession, bench_session_id)
        if not bench_sess:
            logger.error("Session %d not found in database", bench_session_id)
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        bench_sess.status = "running"
        bench_sess.started_at = now_iso
        session.add(bench_sess)
        session.commit()

        models = [session.get(AIModel, mid) for mid in model_ids]
        models = [m for m in models if m is not None]
        devices = [session.get(Device, did) for did in device_ids]
        devices = [d for d in devices if d is not None and d.is_available]

    total_runs = len(models) * len(devices) * len(batches)
    progress_state["total"] = total_runs
    progress_state["done"] = 0

    # Optional idle baseline measurement if battery is discharging (unplugged)
    idle_w: Optional[float] = None
    batt_reader = BatteryReader()
    batt_info = batt_reader.read()
    if not batt_info.get("power_online"):
        progress_state["item"] = f"Measuring idle battery baseline ({IDLE_WINDOW_S}s)..."
        idle_w = measure_idle_battery_w(duration_s=IDLE_WINDOW_S)

    completed = 0
    final_status = "done"
    error_msg = None
    try:
        for model in models:
            for device in devices:
                if progress_state.get("cancel"):
                    final_status = "cancelled"
                    break

                for batch in batches:
                    if progress_state.get("cancel"):
                        final_status = "cancelled"
                        break

                    item_desc = f"Energy: {model.name} on {device.label} (B={batch})"
                    progress_state["item"] = item_desc
                    logger.info("Benchmarking energy: %s", item_desc)

                    with Session(engine) as run_session:
                        run_energy_measurement(
                            session=run_session,
                            bench_session_id=bench_session_id,
                            model=model,
                            device=device,
                            batch=batch,
                            idle_baseline_w=idle_w,
                        )
                    completed += 1
                    progress_state["done"] = completed

            if final_status == "cancelled":
                break

    except Exception as exc:
        logger.exception("Error executing energy session %d: %s", bench_session_id, exc)
        final_status = "failed"
        error_msg = str(exc)

    with Session(engine) as finish_session:
        bs = finish_session.get(BenchSession, bench_session_id)
        if bs:
            bs.status = final_status
            bs.error = error_msg
            bs.finished_at = datetime.now(timezone.utc).isoformat()
            finish_session.add(bs)
            finish_session.commit()

