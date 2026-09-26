"""Benchmark engine for SiliconRoute.

Executes latency measurements following SPEC Section 2.1 exactly:
- Session cold-start timing
- Provider mismatch verification
- Adaptive inner-loop timing for sub-millisecond runs (>= 1.0 ms duration)
- Robust stability metric (spread = (p90 - p10) / median)
- Correctness check vs CPU reference outputs
- System hygiene (power scheme, thermal cooldown, battery status)
- Duplicate DML adapter detection
"""

from datetime import datetime, timezone
import hashlib
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
from sqlmodel import Session, select

from app.config import (
    BOOTSTRAP_ROUNDS,
    CI_THRESHOLD,
    COOLDOWN_S,
    DUPLICATE_DIFF_PCT,
    DUPLICATE_MIN_RUNS,
    MAX_INNER_LOOP_K,
    MIN_SAMPLE_MS,
    SEED,
    SPREAD_THRESHOLD,
    TIMED_RUNS,
    UNSTABLE_CV,
    WARMUP_RUNS,
    WARMUP_SUSTAINED_MS,
)
from app.db import AIModel, BenchSession, Device, Run, engine
from app.devices import make_session
from app.power import nvml_reader

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

    seed_val = (SEED + (model.id or 0) * 1000 + batch) % (2**32 - 1)
    rng = np.random.default_rng(seed_val)
    input_data = rng.standard_normal(concrete_shape).astype(np.float32)

    return inp_name, input_data


def check_and_mark_duplicate_devices(session: Session) -> list[tuple[str, str]]:
    """Detect if two DML devices produce bit-identical outputs and <5% diff medians across >= 3 runs.

    Marks the higher-index adapter as unavailable with a reason explaining the duplicate.
    """
    dml_devices = session.exec(
        select(Device).where(Device.provider == "DmlExecutionProvider").order_by(Device.id)
    ).all()

    if len(dml_devices) < 2:
        return []

    duplicates_found: list[tuple[str, str]] = []

    for i in range(len(dml_devices)):
        dev_a = dml_devices[i]
        for j in range(i + 1, len(dml_devices)):
            dev_b = dml_devices[j]
            if not dev_b.is_available and dev_b.unavailable_reason:
                continue

            runs_a = session.exec(select(Run).where(Run.device_id == dev_a.id)).all()
            runs_b = session.exec(select(Run).where(Run.device_id == dev_b.id)).all()

            map_a = {(r.session_id, r.ai_model_id, r.batch): r for r in runs_a}
            map_b = {(r.session_id, r.ai_model_id, r.batch): r for r in runs_b}

            common_keys = set(map_a.keys()) & set(map_b.keys())
            matching_duplicate_runs = 0
            for key in common_keys:
                ra = map_a[key]
                rb = map_b[key]
                # Check bit-identical output
                hash_match = False
                if ra.output_hash and rb.output_hash:
                    hash_match = (ra.output_hash == rb.output_hash)
                elif ra.output_matches_cpu is not None and rb.output_matches_cpu is not None:
                    hash_match = (ra.output_matches_cpu == rb.output_matches_cpu and ra.max_rel_err == rb.max_rel_err)

                if hash_match:
                    max_med = max(ra.median_ms, rb.median_ms)
                    if max_med > 0:
                        diff_pct = abs(ra.median_ms - rb.median_ms) / max_med
                        if diff_pct < DUPLICATE_DIFF_PCT:
                            matching_duplicate_runs += 1

            if matching_duplicate_runs >= DUPLICATE_MIN_RUNS:
                reason = f"suspected duplicate of {dev_a.key}"
                dev_b.is_available = False
                dev_b.unavailable_reason = reason
                session.add(dev_b)
                session.commit()
                session.refresh(dev_b)
                logger.warning(
                    "Marked device %s as unavailable: %s (matched on %d runs)",
                    dev_b.key,
                    reason,
                    matching_duplicate_runs,
                )
                duplicates_found.append((dev_b.key, dev_a.key))

    return duplicates_found


def run_latency_measurement(
    session: Session,
    bench_session_id: int,
    model: AIModel,
    device: Device,
    batch: int,
    warmup_runs: int = WARMUP_RUNS,
    timed_runs: int = TIMED_RUNS,
) -> Run:
    """Execute a single latency measurement run with adaptive timing and robust stability."""
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

    # 3b. Measure cold-start latency (1st inference after session creation, before warmups)
    t_first_start = time.perf_counter_ns()
    sess.run(None, feed_dict)
    first_run_ms = (time.perf_counter_ns() - t_first_start) / 1e6

    # 4. Warm-up runs: for DML devices, sustain for >= WARMUP_SUSTAINED_MS (300 ms)
    # to ensure the GPU exits idle power-saving states (e.g. P8 -> P0/P2)
    warmup_t0 = time.perf_counter_ns()
    warmups_done = 0
    if "Dml" in device.provider:
        while ((time.perf_counter_ns() - warmup_t0) / 1e6 < WARMUP_SUSTAINED_MS) or (warmups_done < warmup_runs):
            sess.run(None, feed_dict)
            warmups_done += 1
    else:
        for _ in range(warmup_runs):
            sess.run(None, feed_dict)
            warmups_done += 1

    # Check if this device is an NVIDIA GPU to read NVML telemetry
    is_nvidia_gpu = (
        device.provider == "DmlExecutionProvider"
        and nvml_reader.is_available
        and ("nvidia" in (device.label or "").lower() or device.key == "dml:1" or device.kind == "dgpu")
    )
    nvml_pstate_start: Optional[int] = None
    nvml_clock_sm_start_mhz: Optional[int] = None
    gpu_temp_start_c: Optional[float] = None
    if is_nvidia_gpu:
        m_start = nvml_reader.read_metrics()
        nvml_pstate_start = m_start.get("gpu_pstate")
        nvml_clock_sm_start_mhz = m_start.get("gpu_clock_sm_mhz")
        gpu_temp_start_c = m_start.get("gpu_temp_c")

    # Adaptive inner-loop determination for sub-millisecond workloads (target >= MIN_SAMPLE_MS)
    t_trial_0 = time.perf_counter_ns()
    sess.run(None, feed_dict)
    t_trial_ms = (time.perf_counter_ns() - t_trial_0) / 1e6

    inner_loop_k = 1
    if t_trial_ms < MIN_SAMPLE_MS:
        inner_loop_k = int(np.ceil(MIN_SAMPLE_MS / max(t_trial_ms, 0.0001)))
        inner_loop_k = min(max(inner_loop_k, 1), MAX_INNER_LOOP_K)

    # 5. Timed runs (samples >= timed_runs, each sample times inner_loop_k runs)
    raw_timings_ms: list[float] = []
    last_output: Optional[np.ndarray] = None
    for _ in range(timed_runs):
        t0 = time.perf_counter_ns()
        for _ in range(inner_loop_k):
            outputs = sess.run(None, feed_dict)
        t1 = time.perf_counter_ns()
        sample_ms = (t1 - t0) / 1e6
        raw_timings_ms.append(sample_ms / inner_loop_k)
        last_output = outputs[0]

    # Post-timing NVML telemetry
    nvml_pstate_end: Optional[int] = None
    nvml_clock_sm_end_mhz: Optional[int] = None
    gpu_temp_end_c: Optional[float] = None
    if is_nvidia_gpu:
        m_end = nvml_reader.read_metrics()
        nvml_pstate_end = m_end.get("gpu_pstate")
        nvml_clock_sm_end_mhz = m_end.get("gpu_clock_sm_mhz")
        gpu_temp_end_c = m_end.get("gpu_temp_c")

    # 6. Statistical calculations & Bootstrap 95% Confidence Interval
    timings = np.array(raw_timings_ms, dtype=np.float64)
    median_ms = float(np.median(timings))
    p10_ms = float(np.percentile(timings, 10))
    p90_ms = float(np.percentile(timings, 90))
    mean_ms = float(np.mean(timings))
    min_ms = float(np.min(timings))
    max_ms = float(np.max(timings))
    stdev_ms = float(np.std(timings, ddof=1)) if len(timings) > 1 else 0.0
    cv = float(stdev_ms / mean_ms) if mean_ms > 0 else 0.0
    spread = float((p90_ms - p10_ms) / median_ms) if median_ms > 0 else 0.0

    # 1000 bootstrap resamples of the median
    boot_rng = np.random.default_rng(SEED + (model.id or 0) * 100 + batch)
    boot_indices = boot_rng.integers(0, len(timings), size=(BOOTSTRAP_ROUNDS, len(timings)))
    boot_medians = np.median(timings[boot_indices], axis=1)
    ci_low_ms = float(np.percentile(boot_medians, 2.5))
    ci_high_ms = float(np.percentile(boot_medians, 97.5))
    ci_half_width = (ci_high_ms - ci_low_ms) / 2.0
    ci_rel = float(ci_half_width / median_ms) if median_ms > 0 else 0.0

    # Stability rule: unstable when ci_rel > CI_THRESHOLD (0.10)
    unstable = bool(ci_rel > CI_THRESHOLD)
    throughput_per_s = float((batch * 1000.0) / median_ms) if median_ms > 0 else 0.0

    # Output hash for bit-identical duplicate checking
    output_hash: Optional[str] = None
    if last_output is not None:
        output_hash = hashlib.sha256(last_output.tobytes()).hexdigest()

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
        inner_loop_k=inner_loop_k,
        session_create_ms=round(session_create_ms, 3),
        first_run_ms=round(first_run_ms, 3),
        median_ms=round(median_ms, 3),
        p10_ms=round(p10_ms, 3),
        p90_ms=round(p90_ms, 3),
        mean_ms=round(mean_ms, 3),
        min_ms=round(min_ms, 3),
        max_ms=round(max_ms, 3),
        stdev_ms=round(stdev_ms, 3),
        cv=round(cv, 4),
        spread=round(spread, 4),
        ci_rel=round(ci_rel, 4),
        ci_low_ms=round(ci_low_ms, 3),
        ci_high_ms=round(ci_high_ms, 3),
        unstable=unstable,
        throughput_per_s=round(throughput_per_s, 2),
        raw_ms_json=json.dumps([round(t, 4) for t in raw_timings_ms]),
        output_matches_cpu=output_matches_cpu,
        max_rel_err=round(max_rel_err, 6) if max_rel_err is not None else None,
        output_hash=output_hash,
        nvml_pstate_start=nvml_pstate_start,
        nvml_pstate_end=nvml_pstate_end,
        nvml_clock_sm_start_mhz=nvml_clock_sm_start_mhz,
        nvml_clock_sm_end_mhz=nvml_clock_sm_end_mhz,
        gpu_temp_start_c=gpu_temp_start_c,
        gpu_temp_end_c=gpu_temp_end_c,
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

        models = [session.get(AIModel, mid) for mid in model_ids]
        models = [m for m in models if m is not None]
        devices = [session.get(Device, did) for did in device_ids]
        devices = [d for d in devices if d is not None and d.is_available]

        total_runs = len(models) * len(devices) * len(batches)
        progress_state["total"] = total_runs
        progress_state["done"] = 0

        completed = 0

        try:
            for model in models:
                shuffled_devices = list(devices)
                random.shuffle(shuffled_devices)

                for dev_idx, device in enumerate(shuffled_devices):
                    if progress_state.get("cancel"):
                        logger.info("Session %d cancelled by user", bench_session_id)
                        bench_sess.status = "cancelled"
                        break

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

            # Check and mark duplicate DirectML adapters if criteria are met
            check_and_mark_duplicate_devices(session)

        except Exception as exc:
            logger.exception("Error executing benchmark session %d: %s", bench_session_id, exc)
            bench_sess.status = "failed"
            bench_sess.error = str(exc)

        batt_pct_end, _ = get_system_battery()
        bench_sess.battery_end = batt_pct_end
        bench_sess.finished_at = datetime.now(timezone.utc).isoformat()
        session.add(bench_sess)
        session.commit()
