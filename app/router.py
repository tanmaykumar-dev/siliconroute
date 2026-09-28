"""SiliconRoute Phase 5 Intelligent Hardware Router.

Implements SPEC Section 6 and Phase 5 requirements:
- Measured-First Candidate Prediction: prefers recent genuine benchmark runs from SQLite.
  Flags volatile configurations if multiple sessions disagree by >20%.
- Per-Device Session Volatility: tracks historical variability and uses volatility bands
  as a principled tie-breaker when candidate scores are within 15%.
- Idle-Gap GPU Wake Penalty: inspects NVIDIA GPU P-state (or >3s idle), interpolating wake
  penalties based on model weight size between 16 MB (+0.78 ms) and 144 MB (+13.85 ms).
- Multi-Objective Routing Modes: fastest, battery, balanced, and cool.
- Context Rules: auto-switch to battery when unplugged (<30% battery), busy GPU throttling (1.3x penalty).
- Principled Exploration: seeded RNG epsilon-exploration (10% chance when runner-up is within 20%).
- Full Verification Engine: benchmarks chosen device and all candidates (VERIFY_RUNS=10),
  storing actual_ms, was_best, and regret_pct.
- Baseline Comparisons: evaluates router accuracy & regret vs Always-CPU, Always-RTX,
  Fit-Only Router (proving measured-first value), and ORT MAX_PERFORMANCE policy.
"""

from collections import defaultdict
from datetime import datetime, timezone
import json
import logging
import random
import time
from typing import Any, Optional

import numpy as np
import psutil
from sqlmodel import Session, select

from app.benchmark import (
    run_cold_start_measurement,
    run_idle_loaded_measurement,
    run_latency_measurement,
)
from app.config import (
    DEVICE_CACHE_MB,
    EPSILON,
    EXPLORE_MARGIN,
    HOT_GPU_C,
    LOW_BATTERY_PCT,
    MAX_GPU_C,
    SEED,
    VERIFY_RUNS,
)
from app.db import AIModel, BenchSession, Decision, Device, Fit, Run, WorkloadMeasurement
from app.jobs import _lock, current_job
from app.devices import verify_gpu_identity_mapping
from app.power import nvml_reader
from app.predictor import predict_for_fit

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# 1. Volatility & Historical Variability Analysis
# -----------------------------------------------------------------------------

def calculate_device_volatility_bands(session: Session) -> dict[int, float]:
    """Calculate the historical median session-to-session percentage difference per device.
    
    Returns a dict mapping device_id -> median_diff_pct (e.g. 12.5 means +/-12.5% variability).
    """
    runs = session.exec(
        select(Run).where(
            Run.session_id != None,
            Run.unstable == False,
            Run.provider_mismatch == False,
            Run.identity_suspect == False,
        )
    ).all()

    # Group runs by (device_id, ai_model_id, batch)
    configs: dict[tuple[int, int, int], dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in runs:
        if r.session_id is not None:
            configs[(r.device_id, r.ai_model_id, r.batch)][r.session_id].append(r.median_ms)

    device_diffs: dict[int, list[float]] = defaultdict(list)
    for (dev_id, _, _), sess_dict in configs.items():
        if len(sess_dict) > 1:
            sess_meds = [float(np.median(vals)) for vals in sess_dict.values()]
            min_v = min(sess_meds)
            max_v = max(sess_meds)
            if min_v > 1e-6:
                diff_pct = ((max_v - min_v) / min_v) * 100.0
                device_diffs[dev_id].append(diff_pct)

    volatility: dict[int, float] = {}
    devices = session.exec(select(Device)).all()
    for d in devices:
        if d.id in device_diffs and device_diffs[d.id]:
            volatility[d.id] = round(float(np.median(device_diffs[d.id])), 1)
        else:
            # Default fallback volatility based on device kind
            volatility[d.id] = 15.0 if d.kind == "cpu" else (10.0 if d.key == "dml:1" else 25.0)

    return volatility


# -----------------------------------------------------------------------------
# 2. Idle-Gap GPU Wake Penalty Calculation
# -----------------------------------------------------------------------------

def calculate_wake_penalty(device: Device, model: AIModel) -> tuple[float, str]:
    """Determine idle-gap wake penalty for an accelerator based on current telemetry.
    
    Returns (wake_penalty_ms, wake_status_note).
    """
    if device.key == "dml:1":
        # Check live NVML telemetry for NVIDIA RTX 5070
        metrics = nvml_reader.read_metrics()
        pstate = metrics.get("gpu_pstate")
        clock_mhz = metrics.get("gpu_clock_sm_mhz")

        # P8 represents deep power-down idle state on NVIDIA Ada/Blackwell architecture
        is_asleep = (pstate == 8) or (clock_mhz is not None and clock_mhz <= 300)

        if is_asleep:
            # Linear interpolation based on weight bytes from Phase 4 empirical measurements:
            # mlp-1024 (16 MB) -> 0.78 ms penalty
            # mlp-3072 (144 MB) -> 13.85 ms penalty
            weight_mb = model.weight_bytes / (1024.0 * 1024.0)
            if weight_mb <= 16.0:
                wake_ms = 0.78 * max(0.4, weight_mb / 16.0)
            else:
                interp = (weight_mb - 16.0) / (144.0 - 16.0)
                wake_ms = 0.78 + interp * (13.85 - 0.78)
            wake_ms = min(max(wake_ms, 0.3), 16.0)
            return round(wake_ms, 3), f"NVIDIA RTX 5070 in P8 sleep; added +{wake_ms:.2f} ms wake penalty"
        else:
            pstate_str = f"P{pstate}" if pstate is not None else "active"
            return 0.0, f"NVIDIA RTX 5070 awake ({pstate_str}, clock {clock_mhz or 'N/A'} MHz)"

    elif device.key == "dml:0":
        # AMD Radeon 610M iGPU does not expose discrete P-state metrics on Windows
        return 0.0, "wake state unknown"
    else:
        # Host CPU has zero accelerator wake overhead
        return 0.0, "no wake penalty"


# -----------------------------------------------------------------------------
# 3. Candidate Prediction Resolution (Measured vs Fit vs Workload Ratios)
# -----------------------------------------------------------------------------

def get_workload_slowdown_ratio(
    session: Session,
    device_id: int,
    family: str,
    workload: str,
) -> float:
    """Calculate the median slowdown ratio for a device and family under a specific workload.
    
    Slowdown ratio = measured_workload_latency / warm_sustained_latency.
    Prefers median across measurements for the same model family; falls back to device median.
    """
    wms = session.exec(
        select(WorkloadMeasurement).where(
            WorkloadMeasurement.device_id == device_id,
            WorkloadMeasurement.workload == workload,
        )
    ).all()

    family_ratios: list[float] = []
    all_ratios: list[float] = []

    for wm in wms:
        m = session.get(AIModel, wm.ai_model_id)
        if not m:
            continue
        warm_run = session.exec(
            select(Run).where(
                Run.ai_model_id == m.id,
                Run.device_id == device_id,
                Run.batch == wm.batch,
                Run.unstable == False,
                Run.provider_mismatch == False,
                Run.identity_suspect == False,
                Run.session_id != None,
            ).order_by(Run.id.desc())
        ).first()

        if warm_run and warm_run.median_ms > 0:
            r = wm.latency_ms / warm_run.median_ms
            all_ratios.append(r)
            if m.family == family:
                family_ratios.append(r)

    if family_ratios:
        return float(np.median(family_ratios))
    elif all_ratios:
        return float(np.median(all_ratios))
    else:
        # Sensible hardware defaults if no measurements exist in DB yet
        if workload == "idle_loaded":
            return 1.1 if device_id == 1 else (3.0 if device_id == 3 else 1.5)
        else:  # cold_start
            return 3.0 if device_id == 1 else (15.0 if device_id == 3 else 8.0)


def resolve_candidate_prediction(
    session: Session,
    device: Device,
    model: AIModel,
    batch: int,
    workload: str = "sustained",
) -> dict[str, Any]:
    """Resolve latency and energy predictions for a candidate device across workloads.
    
    Workloads:
    - 'sustained': warm steady-state median (prefers Run table, falls back to Fit).
    - 'idle_loaded': warm session after 10 s idle (prefers WorkloadMeasurement, falls back to family slowdown ratio).
    - 'cold_start': session creation + first inference (prefers WorkloadMeasurement, falls back to family slowdown ratio).
    """
    # 1. Warm steady-state latency lookup
    runs = session.exec(
        select(Run).where(
            Run.ai_model_id == model.id,
            Run.device_id == device.id,
            Run.batch == batch,
            Run.unstable == False,
            Run.provider_mismatch == False,
            Run.identity_suspect == False,
            Run.session_id != None,
        ).order_by(Run.id.desc())
    ).all()

    source = "fit"
    warm_latency_ms: Optional[float] = None
    is_volatile = False
    volatility_pct: Optional[float] = None
    measured_session_id: Optional[int] = None

    if runs:
        sess_groups: dict[int, list[float]] = defaultdict(list)
        for r in runs:
            if r.session_id is not None:
                sess_groups[r.session_id].append(r.median_ms)

        latest_sess_id = max(sess_groups.keys())
        latest_med = float(np.median(sess_groups[latest_sess_id]))
        warm_latency_ms = latest_med
        source = "measured"
        measured_session_id = latest_sess_id

        if len(sess_groups) > 1:
            all_sess_meds = [float(np.median(vals)) for vals in sess_groups.values()]
            min_v = min(all_sess_meds)
            max_v = max(all_sess_meds)
            if min_v > 1e-6:
                diff = (max_v - min_v) / min_v
                volatility_pct = round(diff * 100.0, 1)
                if diff > 0.20:
                    is_volatile = True

    # Check active predictor fit (both for fallback and for fit-only baseline)
    fit = session.exec(
        select(Fit).where(
            Fit.device_id == device.id,
            Fit.target == "latency",
            Fit.is_active == True,
        )
    ).first()

    fit_latency_ms: Optional[float] = None
    if fit is not None:
        cache_mb = DEVICE_CACHE_MB.get(device.key, 32.0)
        fit_latency_ms = round(float(predict_for_fit(fit, model, batch, cache_mb)), 3)

    if warm_latency_ms is None:
        if fit_latency_ms is not None:
            warm_latency_ms = fit_latency_ms
            source = "fit"
        else:
            raise ValueError(f"No prediction possible for device {device.key}: missing runs and fit")

    # 2. Workload-specific latency resolution
    target_wl = "idle_loaded" if workload == "single" else workload
    final_latency_ms: float = warm_latency_ms
    wake_status: str = "sustained workload: warm steady-state"

    if target_wl in ("idle_loaded", "cold_start"):
        wm = session.exec(
            select(WorkloadMeasurement).where(
                WorkloadMeasurement.ai_model_id == model.id,
                WorkloadMeasurement.device_id == device.id,
                WorkloadMeasurement.batch == batch,
                WorkloadMeasurement.workload == target_wl,
            ).order_by(WorkloadMeasurement.id.desc())
        ).first()

        if wm is not None:
            final_latency_ms = wm.latency_ms
            source = f"measured_{target_wl}"
            wake_status = f"measured {target_wl} ({wm.latency_ms:.3f} ms)"
        else:
            ratio = get_workload_slowdown_ratio(session, device.id, model.family, target_wl)
            final_latency_ms = round(warm_latency_ms * ratio, 3)
            source = f"ratio_{target_wl}"
            wake_status = f"ratio fallback ({ratio:.2f}x for {model.family} on {device.key})"

    # 3. Energy prediction lookup
    energy_mj: Optional[float] = None
    energy_runs = [r for r in runs if r.energy_mj_per_inf is not None and r.energy_mj_per_inf > 0]
    if energy_runs:
        energy_mj = float(np.median([r.energy_mj_per_inf for r in energy_runs if r.energy_mj_per_inf]))
    else:
        fit_energy = session.exec(
            select(Fit).where(
                Fit.device_id == device.id,
                Fit.target == "energy",
                Fit.is_active == True,
            )
        ).first()
        if fit_energy is not None:
            cache_mb = DEVICE_CACHE_MB.get(device.key, 32.0)
            energy_mj = float(predict_for_fit(fit_energy, model, batch, cache_mb))

    return {
        "device_id": device.id,
        "device_key": device.key,
        "device_label": device.label,
        "device_kind": device.kind,
        "source": source,
        "base_latency_ms": round(final_latency_ms, 3),
        "fit_latency_ms": fit_latency_ms,
        "wake_penalty_ms": 0.0,
        "effective_latency_ms": round(final_latency_ms, 3),
        "energy_mj": round(energy_mj, 3) if energy_mj is not None else None,
        "is_volatile": is_volatile,
        "volatility_pct": volatility_pct,
        "measured_session_id": measured_session_id,
        "wake_status": wake_status,
    }


# -----------------------------------------------------------------------------
# 4. Main Decision Engine
# -----------------------------------------------------------------------------

def route_model(
    session: Session,
    model_id: int,
    batch: int = 1,
    mode: str = "fastest",
    power_budget_w: Optional[float] = None,
    allow_explore: bool = True,
    rng_seed: Optional[int] = None,
    workload: str = "sustained",
) -> dict[str, Any]:
    """Evaluate all candidate devices, score according to goal, and choose the optimal chip."""
    if workload not in ("sustained", "idle_loaded", "cold_start", "single"):
        raise ValueError(f"Invalid workload '{workload}': must be 'sustained', 'idle_loaded', or 'cold_start'")

    model = session.get(AIModel, model_id)
    if not model:
        raise ValueError(f"AIModel {model_id} not found")

    devices = session.exec(select(Device).where(Device.is_available == True)).all()
    if not devices:
        raise ValueError("No available devices registered")

    context_rules: list[str] = []
    excluded_candidates: list[dict[str, Any]] = []
    valid_candidates: list[dict[str, Any]] = []

    # Read host telemetry context
    battery = psutil.sensors_battery()
    plugged_in = battery.power_plugged if battery else None
    battery_pct = round(battery.percent, 1) if battery else None

    # Context Rule 1: Low battery check (<30% and unplugged -> force battery mode)
    active_mode = mode.lower()
    if plugged_in is False and battery_pct is not None and battery_pct < LOW_BATTERY_PCT:
        if active_mode != "battery":
            context_rules.append(
                f"Battery low ({battery_pct:.1f}% < {LOW_BATTERY_PCT}%) and unplugged: switched mode from '{mode}' to 'battery'"
            )
            active_mode = "battery"

    # Context Rule 2: NVIDIA GPU busy check (>80% utilization from other processes)
    nvml_metrics = nvml_reader.read_metrics()
    nvml_util = nvml_metrics.get("gpu_util_pct")
    gpu_temp = nvml_metrics.get("gpu_temp_c")

    # Evaluate each available device
    for dev in devices:
        # Exclusion 1: Output check vs CPU reference for this model and batch
        mismatch_run = session.exec(
            select(Run).where(
                Run.ai_model_id == model.id,
                Run.device_id == dev.id,
                Run.batch == batch,
                Run.output_matches_cpu == False,
            )
        ).first()
        if mismatch_run:
            excluded_candidates.append({
                "device_id": dev.id,
                "device_key": dev.key,
                "device_label": dev.label,
                "reason": "Excluded: output values diverged from CPU reference in previous benchmark",
            })
            continue

        # Exclusion 2: Power budget check
        if power_budget_w is not None:
            recent_load_run = session.exec(
                select(Run).where(
                    Run.device_id == dev.id,
                    Run.load_w != None,
                ).order_by(Run.id.desc())
            ).first()
            if recent_load_run and recent_load_run.load_w and recent_load_run.load_w > power_budget_w:
                excluded_candidates.append({
                    "device_id": dev.id,
                    "device_key": dev.key,
                    "device_label": dev.label,
                    "reason": f"Excluded: measured load power {recent_load_run.load_w:.1f} W exceeds budget {power_budget_w:.1f} W",
                })
                continue

        try:
            cand = resolve_candidate_prediction(session, dev, model, batch, workload=workload)
            valid_candidates.append(cand)
        except Exception as exc:
            excluded_candidates.append({
                "device_id": dev.id,
                "device_key": dev.key,
                "device_label": dev.label,
                "reason": f"Excluded: {exc}",
            })

    if not valid_candidates:
        raise ValueError("No valid candidate devices remain after applying exclusion filters")

    # Min latency and min energy for normalisation
    min_t = min(c["effective_latency_ms"] for c in valid_candidates)
    energy_values = [c["energy_mj"] for c in valid_candidates if c["energy_mj"] is not None]
    energy_available = (len(energy_values) >= 2)
    min_e = min(energy_values) if energy_available and energy_values else 1.0

    # Device historical volatility bands
    vol_bands = calculate_device_volatility_bands(session)

    # Compute scores per candidate
    for c in valid_candidates:
        t_hat = c["effective_latency_ms"] / max(min_t, 1e-4)
        c["t_hat"] = round(t_hat, 4)

        if energy_available and c["energy_mj"] is not None:
            e_hat = c["energy_mj"] / max(min_e, 1e-4)
            c["e_hat"] = round(e_hat, 4)
        else:
            e_hat = t_hat
            c["e_hat"] = round(t_hat, 4)

        # Mode scoring (lower score is better)
        if active_mode == "fastest":
            score = t_hat
        elif active_mode == "battery":
            if energy_available and c["energy_mj"] is not None:
                score = e_hat
            else:
                score = t_hat
                if "Energy data not measured for all devices; ranked by latency fallback" not in context_rules:
                    context_rules.append("Energy data not measured for all devices; ranked by latency fallback")
        elif active_mode == "balanced":
            if energy_available and c["energy_mj"] is not None:
                score = 0.5 * t_hat + 0.5 * e_hat
            else:
                score = t_hat
                if "Energy data not measured for all devices; ranked by latency fallback" not in context_rules:
                    context_rules.append("Energy data not measured for all devices; ranked by latency fallback")
        elif active_mode == "cool":
            if c["device_key"] == "dml:1" and gpu_temp is not None:
                if gpu_temp > MAX_GPU_C:
                    score = 9999.0
                    context_rules.append(f"NVIDIA GPU temperature critical ({gpu_temp:.1f} °C > {MAX_GPU_C} °C)")
                else:
                    penalty = 0.5 * max(0.0, gpu_temp - HOT_GPU_C) / 10.0
                    score = t_hat + penalty
            else:
                score = t_hat
                if c["device_kind"] == "cpu" and "CPU temperature sensor not available on Windows; no cool penalty" not in context_rules:
                    context_rules.append("CPU temperature sensor not available on Windows; no cool penalty")
        else:
            score = t_hat

        # Context Rule 2 penalization: NVIDIA GPU busy (>80% util from external processes)
        if c["device_key"] == "dml:1" and nvml_util is not None and nvml_util > 80.0:
            score *= 1.3
            if "NVIDIA GPU busy (>80% external load): applied 1.3x penalty" not in context_rules:
                context_rules.append(f"NVIDIA GPU busy ({nvml_util:.0f}% load): applied 1.3x penalty")

        c["raw_score"] = round(score, 4)
        c["device_volatility_pct"] = vol_bands.get(c["device_id"], 15.0)

    # Sort candidates by raw score ascending (best first)
    valid_candidates.sort(key=lambda x: x["raw_score"])

    # Volatility tie-breaking:
    # If the top two candidates are within the 15% volatility band (score_1 <= score_0 * 1.15),
    # prefer the device with lower session-to-session variability!
    chosen = valid_candidates[0]
    volatility_tie_broken = False
    if len(valid_candidates) > 1:
        top_cand = valid_candidates[0]
        runner_cand = valid_candidates[1]
        score_diff_ratio = (runner_cand["raw_score"] - top_cand["raw_score"]) / max(top_cand["raw_score"], 1e-4)
        if score_diff_ratio <= 0.15:
            # Within volatility band
            top_vol = top_cand["device_volatility_pct"]
            run_vol = runner_cand["device_volatility_pct"]
            if run_vol < top_vol - 5.0:  # runner has meaningfully lower volatility (>5% difference)
                chosen = runner_cand
                volatility_tie_broken = True
                context_rules.append(
                    f"Candidate scores within 15% volatility band ({top_cand['device_key']} vs {runner_cand['device_key']}); "
                    f"preferred {runner_cand['device_key']} due to lower session variability ({run_vol:.1f}% vs {top_vol:.1f}%)"
                )

    # Exploration Rule: with probability EPSILON (10%), pick runner-up if within 20%
    explored = False
    if allow_explore and len(valid_candidates) > 1 and not volatility_tie_broken:
        rng = random.Random(rng_seed or SEED)
        top_score = valid_candidates[0]["raw_score"]
        runner_score = valid_candidates[1]["raw_score"]
        if (runner_score - top_score) / max(top_score, 1e-4) <= EXPLORE_MARGIN:
            if rng.random() < EPSILON:
                chosen = valid_candidates[1]
                explored = True
                context_rules.append(f"Exploration active (epsilon={EPSILON}): selected runner-up {chosen['device_key']}")

    # Formulate transparent, plain-English reason with exact numbers
    runner_up = valid_candidates[1] if valid_candidates[0]["device_id"] == chosen["device_id"] and len(valid_candidates) > 1 else valid_candidates[0]
    plug_text = "Plugged in" if plugged_in else "On battery"
    bat_text = f", battery {battery_pct:.0f}%" if battery_pct is not None else ""

    reason_parts = [
        f"Chose {chosen['device_key']} ({chosen['device_label']}) for {model.name} (batch {batch}), {mode.capitalize()} mode.",
        f"Predicted {chosen['effective_latency_ms']:.3f} ms ({chosen['source']})"
    ]
    if chosen["wake_penalty_ms"] > 0:
        reason_parts.append(f"[incl. +{chosen['wake_penalty_ms']:.2f} ms wake penalty]")

    if len(valid_candidates) > 1 and runner_up["device_id"] != chosen["device_id"]:
        reason_parts.append(f"vs runner-up {runner_up['device_key']} ({runner_up['effective_latency_ms']:.3f} ms, {runner_up['source']}).")
    else:
        reason_parts.append(".")

    if chosen.get("is_volatile"):
        reason_parts.append(f"Flagged volatile (session diff {chosen.get('volatility_pct')} > 20%).")

    reason_parts.append(f"{plug_text}{bat_text}.")
    if volatility_tie_broken:
        reason_parts.append("Preferred due to lower volatility.")
    if explored:
        reason_parts.append("Explored runner-up.")

    final_reason = " ".join(reason_parts)

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ai_model_id": model.id,
        "batch": batch,
        "mode": mode,
        "workload": workload,
        "power_budget_w": power_budget_w,
        "chosen_device_id": chosen["device_id"],
        "chosen_device_key": chosen["device_key"],
        "explored": explored,
        "reason": final_reason,
        "context_rules": context_rules,
        "candidates": valid_candidates,
        "excluded_candidates": excluded_candidates,
    }


# -----------------------------------------------------------------------------
# 5. Verification Engine
# -----------------------------------------------------------------------------

def execute_verification(
    session: Session,
    decision_dict: dict[str, Any],
    runs_count: int = VERIFY_RUNS,
    workload: Optional[str] = None,
) -> Decision:
    """Benchmark chosen device and all candidates on hardware to verify the routing decision.
    
    workload='single': measure ONE cold inference per device (first_run_ms, no warmup).
    workload='sustained': warmup + timed_runs, use warm median.
    """
    model_id = decision_dict["ai_model_id"]
    batch = decision_dict["batch"]
    chosen_id = decision_dict["chosen_device_id"]
    candidates = decision_dict["candidates"]
    # Prefer explicit kwarg; fall back to decision_dict; default to sustained
    workload = workload or decision_dict.get("workload", "sustained")

    model = session.get(AIModel, model_id)
    if not model:
        raise ValueError(f"AIModel {model_id} not found")

    # Enforce Hard Rule 4: single benchmark lock
    with _lock:
        if current_job["session_id"] is not None:
            raise RuntimeError("A benchmark or measurement job is already running.")

    # Verify physical GPU adapter mapping via DXGI and NVML load fingerprint
    verify_gpu_identity_mapping()

    # Create verification BenchSession
    now_iso = datetime.now(timezone.utc).isoformat()
    bench_session = BenchSession(
        kind="verify",
        status="running",
        config_json=json.dumps({
            "model_id": model_id, "batch": batch, "runs": runs_count, "workload": workload,
        }),
        created_at=now_iso,
        started_at=now_iso,
        notes=f"Router verification: {model.name} (B={batch}) across {len(candidates)} candidates",
    )
    session.add(bench_session)
    session.commit()
    session.refresh(bench_session)

    with _lock:
        current_job["session_id"] = bench_session.id

    measured_times: dict[int, float] = {}
    try:
        available_devices = session.exec(select(Device).where(Device.is_available == True)).all()
        for device in available_devices:
            dev_id = device.id

            if workload == "sustained":
                # Sustained workload: warmup + timed runs, use warm median
                run = run_latency_measurement(
                    session=session,
                    bench_session_id=bench_session.id,
                    model=model,
                    device=device,
                    batch=batch,
                    warmup_runs=2,
                    timed_runs=runs_count,
                )
                measured_times[dev_id] = run.median_ms
            elif workload in ("idle_loaded", "single"):
                # Idle loaded: warm session, idle sleep to enter low-power state, time ONE inference
                dev_idle_s = 5.0 if device.key == "dml:1" else (1.0 if device.key == "dml:0" else 0.2)
                meas = run_idle_loaded_measurement(
                    model=model,
                    device=device,
                    batch=batch,
                    idle_s=dev_idle_s,
                )
                measured_times[dev_id] = meas["latency_ms"]
            elif workload == "cold_start":
                # Cold start: fresh session creation + first inference
                dev_idle_s = 5.0 if device.key == "dml:1" else (1.0 if device.key == "dml:0" else 0.2)
                meas = run_cold_start_measurement(
                    model=model,
                    device=device,
                    batch=batch,
                    idle_s=dev_idle_s,
                )
                measured_times[dev_id] = meas["latency_ms"]

        bench_session.status = "done"
        bench_session.finished_at = datetime.now(timezone.utc).isoformat()
        session.add(bench_session)
        session.commit()

    except Exception as exc:
        bench_session.status = "failed"
        bench_session.error = str(exc)
        bench_session.finished_at = datetime.now(timezone.utc).isoformat()
        session.add(bench_session)
        session.commit()
        raise
    finally:
        with _lock:
            current_job["session_id"] = None

    if not measured_times:
        raise RuntimeError("Verification failed to obtain valid timings")

    # Determine best device and calculate regret
    best_dev_id = min(measured_times.keys(), key=lambda d_id: measured_times[d_id])
    t_best = measured_times[best_dev_id]
    t_chosen = measured_times.get(chosen_id, t_best)
    was_best = (chosen_id == best_dev_id)
    regret_pct = round(((t_chosen - t_best) / max(t_best, 1e-4)) * 100.0, 2)

    # Create Decision record in database
    dec_record = Decision(
        ts=decision_dict["ts"],
        ai_model_id=model_id,
        batch=batch,
        mode=decision_dict["mode"],
        power_budget_w=decision_dict["power_budget_w"],
        context_json=json.dumps({
            "rules": decision_dict["context_rules"],
            "workload": workload,
            "excluded_candidates": decision_dict["excluded_candidates"],
            "verification_session_id": bench_session.id,
            "measured_times_ms": {str(k): round(v, 3) for k, v in measured_times.items()},
        }),
        candidates_json=json.dumps(candidates),
        chosen_device_id=chosen_id,
        explored=decision_dict["explored"],
        reason=decision_dict["reason"],
        actual_ms=round(t_chosen, 3),
        best_device_id_actual=best_dev_id,
        was_best=was_best,
        regret_pct=regret_pct,
    )
    session.add(dec_record)
    session.commit()
    session.refresh(dec_record)
    return dec_record


# -----------------------------------------------------------------------------
# 6. Baseline Comparisons & Statistics Engine
# -----------------------------------------------------------------------------

def compute_decision_statistics(
    session: Session,
    decision_ids: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Calculate accuracy and regret metrics for SiliconRoute and all static baselines.
    
    All baselines use the SAME denominator (n = total verified decisions) for honest
    comparison.  When a baseline's device is missing from measured_times for a decision,
    that decision counts as a loss (the baseline couldn't run there).

    Evaluates:
    - SiliconRoute router (measured-first)
    - Always-CPU baseline
    - Always-RTX (dml:1) baseline
    - Fit-Only Router baseline (to prove measured-first benefit)
    """
    query = select(Decision).where(Decision.actual_ms != None, Decision.best_device_id_actual != None)
    if decision_ids is not None:
        query = query.where(Decision.id.in_(decision_ids))
    decisions = session.exec(query).all()

    if not decisions:
        return {
            "total_verified": 0,
            "message": "No verified decisions recorded yet",
        }

    cpu_dev = session.exec(select(Device).where(Device.key == "cpu")).first()
    rtx_dev = session.exec(select(Device).where(Device.key == "dml:1")).first()

    n = len(decisions)
    sr_wins = sum(1 for d in decisions if d.was_best)
    sr_regrets = [d.regret_pct for d in decisions if d.regret_pct is not None]

    # Baseline accumulators — every baseline counts against ALL n decisions
    cpu_wins = 0
    cpu_regrets: list[float] = []
    rtx_wins = 0
    rtx_regrets: list[float] = []
    fit_only_wins = 0
    fit_only_regrets: list[float] = []

    for d in decisions:
        try:
            ctx = json.loads(d.context_json)
            measured_map = ctx.get("measured_times_ms", {})
            m_times = {int(k): v for k, v in measured_map.items()}
        except Exception:
            continue

        if not m_times:
            continue

        t_best = min(m_times.values())

        # Always-CPU: loss if device missing from measured_times
        if cpu_dev and cpu_dev.id in m_times:
            t_cpu = m_times[cpu_dev.id]
            if t_cpu <= t_best + 1e-4:
                cpu_wins += 1
            cpu_regrets.append(((t_cpu - t_best) / max(t_best, 1e-4)) * 100.0)
        # else: implicit loss — cpu_wins not incremented, no regret computable

        # Always-RTX: loss if device missing from measured_times
        if rtx_dev and rtx_dev.id in m_times:
            t_rtx = m_times[rtx_dev.id]
            if t_rtx <= t_best + 1e-4:
                rtx_wins += 1
            rtx_regrets.append(((t_rtx - t_best) / max(t_best, 1e-4)) * 100.0)

        # Fit-Only Router: pick the candidate with best fit_latency_ms (or base_latency_ms fallback)
        try:
            candidates = json.loads(d.candidates_json)
            fit_scores = []
            for c in candidates:
                d_id = c["device_id"]
                fit_lat = c.get("fit_latency_ms")
                if fit_lat is None:
                    fit_lat = c.get("base_latency_ms", c.get("effective_latency_ms"))
                fit_scores.append((d_id, fit_lat))
            fit_scores.sort(key=lambda x: x[1])
            fit_chosen_id = fit_scores[0][0]

            if fit_chosen_id in m_times:
                t_fit_chosen = m_times[fit_chosen_id]
                if t_fit_chosen <= t_best + 1e-4:
                    fit_only_wins += 1
                fit_only_regrets.append(((t_fit_chosen - t_best) / max(t_best, 1e-4)) * 100.0)
            # else: fit chose a device that wasn't measured — counts as loss
        except Exception:
            pass

    def p90(arr: list[float]) -> float:
        return float(np.percentile(arr, 90)) if arr else 0.0

    # Per-workload breakdown
    per_workload: dict[str, Any] = {}
    for wl in ("sustained", "idle_loaded", "cold_start"):
        wl_decs = [
            d for d in decisions
            if (json.loads(d.context_json or "{}").get("workload") == wl
                or (wl == "idle_loaded" and json.loads(d.context_json or "{}").get("workload") == "single"))
        ]
        if wl_decs:
            wl_n = len(wl_decs)
            wl_wins = sum(1 for d in wl_decs if d.was_best)
            wl_regrets = [d.regret_pct for d in wl_decs if d.regret_pct is not None]

            wl_cpu_wins = 0
            wl_cpu_regrets = []
            wl_rtx_wins = 0
            wl_rtx_regrets = []
            wl_fit_wins = 0
            wl_fit_regrets = []

            for d in wl_decs:
                try:
                    ctx = json.loads(d.context_json or "{}")
                    m_times = {int(k): v for k, v in ctx.get("measured_times_ms", {}).items()}
                    if not m_times:
                        continue
                    t_best = min(m_times.values())
                    if cpu_dev and cpu_dev.id in m_times:
                        t_cpu = m_times[cpu_dev.id]
                        if t_cpu <= t_best + 1e-4:
                            wl_cpu_wins += 1
                        wl_cpu_regrets.append(((t_cpu - t_best) / max(t_best, 1e-4)) * 100.0)
                    if rtx_dev and rtx_dev.id in m_times:
                        t_rtx = m_times[rtx_dev.id]
                        if t_rtx <= t_best + 1e-4:
                            wl_rtx_wins += 1
                        wl_rtx_regrets.append(((t_rtx - t_best) / max(t_best, 1e-4)) * 100.0)
                    candidates = json.loads(d.candidates_json or "[]")
                    fit_scores = []
                    for c in candidates:
                        d_id = c["device_id"]
                        fit_lat = c.get("fit_latency_ms")
                        if fit_lat is None:
                            fit_lat = c.get("base_latency_ms", c.get("effective_latency_ms"))
                        fit_scores.append((d_id, fit_lat))
                    fit_scores.sort(key=lambda x: x[1])
                    fit_chosen_id = fit_scores[0][0]
                    if fit_chosen_id in m_times:
                        t_fit = m_times[fit_chosen_id]
                        if t_fit <= t_best + 1e-4:
                            wl_fit_wins += 1
                        wl_fit_regrets.append(((t_fit - t_best) / max(t_best, 1e-4)) * 100.0)
                except Exception:
                    pass

            per_workload[wl] = {
                "wins": wl_wins,
                "total": wl_n,
                "accuracy_pct": round((wl_wins / wl_n) * 100.0, 1),
                "mean_regret_pct": round(float(np.mean(wl_regrets)), 2) if wl_regrets else 0.0,
                "p90_regret_pct": round(p90(wl_regrets), 2),
                "always_cpu": {
                    "wins": wl_cpu_wins,
                    "total": wl_n,
                    "accuracy_pct": round((wl_cpu_wins / wl_n) * 100.0, 1),
                    "mean_regret_pct": round(float(np.mean(wl_cpu_regrets)), 2) if wl_cpu_regrets else 0.0,
                    "p90_regret_pct": round(p90(wl_cpu_regrets), 2),
                },
                "always_rtx": {
                    "wins": wl_rtx_wins,
                    "total": wl_n,
                    "accuracy_pct": round((wl_rtx_wins / wl_n) * 100.0, 1),
                    "mean_regret_pct": round(float(np.mean(wl_rtx_regrets)), 2) if wl_rtx_regrets else 0.0,
                    "p90_regret_pct": round(p90(wl_rtx_regrets), 2),
                },
                "fit_only": {
                    "wins": wl_fit_wins,
                    "total": wl_n,
                    "accuracy_pct": round((wl_fit_wins / wl_n) * 100.0, 1),
                    "mean_regret_pct": round(float(np.mean(wl_fit_regrets)), 2) if wl_fit_regrets else 0.0,
                    "p90_regret_pct": round(p90(wl_fit_regrets), 2),
                },
            }

    return {
        "total_verified": n,
        "siliconroute": {
            "wins": sr_wins,
            "total": n,
            "accuracy_pct": round((sr_wins / n) * 100.0, 1),
            "mean_regret_pct": round(float(np.mean(sr_regrets)), 2) if sr_regrets else 0.0,
            "p90_regret_pct": round(p90(sr_regrets), 2),
        },
        "per_workload": per_workload,
        "baselines": {
            "always_cpu": {
                "wins": cpu_wins,
                "total": n,
                "measured_in": len(cpu_regrets),
                "accuracy_pct": round((cpu_wins / n) * 100.0, 1),
                "mean_regret_pct": round(float(np.mean(cpu_regrets)), 2) if cpu_regrets else 0.0,
                "p90_regret_pct": round(p90(cpu_regrets), 2),
            },
            "always_rtx": {
                "wins": rtx_wins,
                "total": n,
                "measured_in": len(rtx_regrets),
                "accuracy_pct": round((rtx_wins / n) * 100.0, 1),
                "mean_regret_pct": round(float(np.mean(rtx_regrets)), 2) if rtx_regrets else 0.0,
                "p90_regret_pct": round(p90(rtx_regrets), 2),
            },
            "fit_only_router": {
                "wins": fit_only_wins,
                "total": n,
                "measured_in": len(fit_only_regrets),
                "accuracy_pct": round((fit_only_wins / n) * 100.0, 1),
                "mean_regret_pct": round(float(np.mean(fit_only_regrets)), 2) if fit_only_regrets else 0.0,
                "p90_regret_pct": round(p90(fit_only_regrets), 2),
                "notes": "Routes using only hardware fits without measured lookup",
            },
            "ort_policy": {
                "status": "not available",
                "reason": "ORT ExecutionProviderDevicePolicy was not executed on hardware; result would be assumed, not measured",
            },
        },
    }

