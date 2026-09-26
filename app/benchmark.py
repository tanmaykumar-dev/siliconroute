"""Benchmark engine for SiliconRoute.

Executes latency measurements following SPEC Section 2.1 exactly:
- Session cold-start timing
- Provider mismatch verification
- Warmup and timed runs using time.perf_counter_ns()
- Comprehensive summary statistics (median, p10, p90, mean, cv, etc.)
- Correctness check vs CPU reference outputs
- System hygiene (power scheme, thermal cooldown, battery status)
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import random
import subprocess
import time
from typing import Any, Optional

import numpy as np
import onnxruntime as ort
import psutil
from sqlmodel import Session

from app.config import (
    COOLDOWN_S,
    SEED,
    TIMED_RUNS,
    UNSTABLE_CV,
    WARMUP_RUNS,
)
from app.db import AIModel, BenchSession, Device, Run, engine
from app.devices import make_session

logger = logging.getLogger(__name__)


def get_power_scheme() -> Optional[str]:
    """Read the active Windows power scheme via powercfg."""
    try:
        proc = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return proc.stdout.strip() or None
    except Exception as exc:
        logger.debug("Failed to read power scheme: %s", exc)
        return None


def get_system_battery() -> tuple[Optional[float], Optional[bool]]:
    """Return current battery percentage and plugged-in status."""
    b = psutil.sensors_battery()
    if b is None:
        return None, None
    return float(b.percent), bool(b.power_plugged)


def prepare_input_tensor(
    model: AIModel,
    batch: int,
    sess: ort.InferenceSession,
) -> tuple[str, np.ndarray]:
    """Generate fixed-seed float32 inputs tailored to the model's expected shape."""
    inp_meta = sess.get_inputs()[0]
    inp_name = inp_meta.name

    raw_shape = inp_meta.shape
    concrete_shape = []
    for idx, dim in enumerate(raw_shape):
        if idx == 0 or dim is None or isinstance(dim, str) or dim < 1:
            concrete_shape.append(batch)
        else:
            concrete_shape.append(int(dim))

    # Deterministic RNG based on SEED + model id + batch
    seed_val = (SEED + (model.id or 0) * 1000 + batch) % (2**32 - 1)
    rng = np.random.default_rng(seed_val)
    input_data = rng.standard_normal(concrete_shape).astype(np.float32)

    return inp_name, input_data


def run_latency_measurement(
    session: Session,
    bench_session_id: int,
    model: AIModel,
    device: Device,
    batch: int,
    warmup_runs: int = WARMUP_RUNS,
    timed_runs: int = TIMED_RUNS,
) -> Run:
    """Execute a single latency measurement run for (model, device, batch)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    intra_threads = psutil.cpu_count(logical=False) or 1
    device_opts = json.loads(device.provider_options_json or "{}")
    device_id = device_opts.get("device_id")

    # 1. Create session and record session_create_ms
    t_create_start = time.perf_counter_ns()
    sess = make_session(model.path, device.provider, device_id=device_id)
    session_create_ms = (time.perf_counter_ns() - t_create_start) / 1e6

    # 2. Verify provider actually used
    providers_active = sess.get_providers()
    provider_used = providers_active[0] if providers_active else "Unknown"
    provider_mismatch = (provider_used != device.provider)

    # 3. Fixed input preparation
    inp_name, inp_tensor = prepare_input_tensor(model, batch, sess)
    feed_dict = {inp_name: inp_tensor}

    # 4. Warm-up runs
    for _ in range(warmup_runs):
        sess.run(None, feed_dict)

    # 5. Timed runs
    raw_timings_ms: list[float] = []
    last_output: Optional[np.ndarray] = None
    for _ in range(timed_runs):
        t0 = time.perf_counter_ns()
        outputs = sess.run(None, feed_dict)
        t1 = time.perf_counter_ns()
        raw_timings_ms.append((t1 - t0) / 1e6)
        last_output = outputs[0]

    # 6. Statistical calculation
    timings = np.array(raw_timings_ms, dtype=np.float64)
    median_ms = float(np.median(timings))
    p10_ms = float(np.percentile(timings, 10))
    p90_ms = float(np.percentile(timings, 90))
    mean_ms = float(np.mean(timings))
    min_ms = float(np.min(timings))
    max_ms = float(np.max(timings))
    stdev_ms = float(np.std(timings, ddof=1)) if len(timings) > 1 else 0.0
    cv = float(stdev_ms / mean_ms) if mean_ms > 0 else 0.0
    unstable = bool(cv > UNSTABLE_CV)
    throughput_per_s = float((batch * 1000.0) / median_ms) if median_ms > 0 else 0.0

    # 7. Correctness check vs CPU reference output
    output_matches_cpu: Optional[bool] = None
    max_rel_err: Optional[float] = None
    if last_output is not None:
        if device.key == "cpu":
            output_matches_cpu = True
            max_rel_err = 0.0
        else:
            try:
                cpu_sess = make_session(model.path, "CPUExecutionProvider")
                ref_outputs = cpu_sess.run(None, feed_dict)
                ref_out = ref_outputs[0]
                diff = np.abs(last_output - ref_out)
                denom = np.abs(ref_out) + 1e-9
                rel_err = float(np.max(diff / denom))
                max_rel_err = rel_err
                output_matches_cpu = bool(rel_err <= 1e-2)
            except Exception as exc:
                logger.warning("Failed CPU reference comparison: %s", exc)

    battery_pct, plugged_in = get_system_battery()

    run = Run(
        session_id=bench_session_id,
        ai_model_id=model.id,
        device_id=device.id,
        provider_used=provider_used,
        provider_mismatch=provider_mismatch,
        batch=batch,
        intra_op_threads=intra_threads,
        warmup_runs=warmup_runs,
        timed_runs=timed_runs,
        session_create_ms=round(session_create_ms, 3),
        median_ms=round(median_ms, 3),
        p10_ms=round(p10_ms, 3),
        p90_ms=round(p90_ms, 3),
        mean_ms=round(mean_ms, 3),
        min_ms=round(min_ms, 3),
        max_ms=round(max_ms, 3),
        stdev_ms=round(stdev_ms, 3),
        cv=round(cv, 4),
        unstable=unstable,
        throughput_per_s=round(throughput_per_s, 2),
        raw_ms_json=json.dumps([round(t, 3) for t in raw_timings_ms]),
        output_matches_cpu=output_matches_cpu,
        max_rel_err=round(max_rel_err, 6) if max_rel_err is not None else None,
        gpu_temp_start_c=None,
        gpu_temp_end_c=None,
        plugged_in=plugged_in,
        battery_pct=battery_pct,
        energy_mj_per_inf=None,
        energy_method=None,
        idle_w=None,
        load_w=None,
        created_at=now_iso,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def execute_latency_job(
    bench_session_id: int,
    model_ids: list[int],
    device_ids: list[int],
    batches: list[int],
    warmup_runs: int,
    timed_runs: int,
    progress_state: dict[str, Any],
) -> None:
    """Worker task executing all latency benchmarks for a session."""
    with Session(engine) as session:
        bench_sess = session.get(BenchSession, bench_session_id)
        if not bench_sess:
            logger.error("Session %d not found in database", bench_session_id)
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        bench_sess.status = "running"
        bench_sess.started_at = now_iso
        bench_sess.ram_pct_start = psutil.virtual_memory().percent
        bench_sess.power_scheme = get_power_scheme()
        batt_pct, plugged = get_system_battery()
        bench_sess.battery_start = batt_pct
        bench_sess.plugged_in = plugged
        session.add(bench_sess)
        session.commit()

        # Query models and devices
        models = [session.get(AIModel, mid) for mid in model_ids]
        models = [m for m in models if m is not None]
        devices = [session.get(Device, did) for did in device_ids]
        devices = [d for d in devices if d is not None and d.is_available]

        total_runs = len(models) * len(devices) * len(batches)
        progress_state["total"] = total_runs
        progress_state["done"] = 0

        completed = 0
        error_msg: Optional[str] = None

        try:
            for model in models:
                # Shuffle devices per model to mitigate thermal bias
                shuffled_devices = list(devices)
                random.shuffle(shuffled_devices)

                for dev_idx, device in enumerate(shuffled_devices):
                    if progress_state.get("cancel"):
                        logger.info("Session %d cancelled by user", bench_session_id)
                        bench_sess.status = "cancelled"
                        break

                    # Thermal cooldown when switching devices
                    if dev_idx > 0 and COOLDOWN_S > 0:
                        time.sleep(COOLDOWN_S)

                    for batch in batches:
                        if progress_state.get("cancel"):
                            bench_sess.status = "cancelled"
                            break

                        item_desc = f"{model.name} on {device.label} (B={batch})"
                        progress_state["item"] = item_desc
                        logger.info("Benchmarking %s", item_desc)

                        run_latency_measurement(
                            session=session,
                            bench_session_id=bench_session_id,
                            model=model,
                            device=device,
                            batch=batch,
                            warmup_runs=warmup_runs,
                            timed_runs=timed_runs,
                        )

                        completed += 1
                        progress_state["done"] = completed

                if bench_sess.status == "cancelled":
                    break

            if bench_sess.status != "cancelled":
                bench_sess.status = "done"

        except Exception as exc:
            logger.exception("Error executing benchmark session %d: %s", bench_session_id, exc)
            bench_sess.status = "failed"
            bench_sess.error = str(exc)

        batt_pct_end, _ = get_system_battery()
        bench_sess.battery_end = batt_pct_end
        bench_sess.finished_at = datetime.now(timezone.utc).isoformat()
        session.add(bench_sess)
        session.commit()
