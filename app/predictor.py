"""Hardware performance predictor and model selection engine for SiliconRoute.

Implements SPEC Section 5:
- Four candidate hardware models:
    * F1 Roofline: t = t0 + a * work_gflop + b * data_gb (weighted NNLS)
    * F2 Roofline + Cache: t = t0 + a * work_gflop + b1 * min(data, cache) + b2 * max(data - cache, 0)
    * F3 Log-Linear: log10(t) = c0 + c1 * log10(params) + c2 * log10(batch) (OLS)
    * F4 Family Roofline: t = t0 + a_mlp * work_mlp_gflop + a_conv * work_conv_gflop + b * data_gb (weighted NNLS)
- Leave-one-out (LOO) MAPE evaluation across all candidate forms.
- Automatic selection of lowest LOO error form per chip.
- Physical parameter extraction (t0 ms, GFLOP/s compute, GB/s bandwidth).
- Cold-start latency and wake-up penalty accounting.
- Crossover analysis between chips with 2x extrapolation limits.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Optional

import numpy as np
from scipy.optimize import nnls
from sqlmodel import Session, select

from app.config import DEVICE_CACHE_MB, MIN_FIT_SAMPLES
from app.db import AIModel, Device, Fit, Run

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# 1. Candidate Form Fitting & Prediction Functions
# -----------------------------------------------------------------------------

def fit_f1(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit F1 Roofline: t_ms = t0 + a*work_gflop + b*data_gb via weighted NNLS (weights 1/t)."""
    weights = 1.0 / np.maximum(y, 1e-6)
    coef, _ = nnls(X * weights[:, None], y * weights)
    return coef


def predict_f1(X: np.ndarray, coef: np.ndarray) -> np.ndarray:
    """Predict latency using F1 Roofline parameters."""
    return np.maximum(X @ coef, 0.0001)


def fit_f2(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit F2 Roofline+Cache via weighted NNLS."""
    weights = 1.0 / np.maximum(y, 1e-6)
    coef, _ = nnls(X * weights[:, None], y * weights)
    return coef


def predict_f2(X: np.ndarray, coef: np.ndarray) -> np.ndarray:
    """Predict latency using F2 Roofline+Cache parameters."""
    return np.maximum(X @ coef, 0.0001)


def fit_f3(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit F3 Log-Linear: log10(t) = c0 + c1*log10(params) + c2*log10(batch) via OLS."""
    log_y = np.log10(np.maximum(y, 1e-6))
    coef, _, _, _ = np.linalg.lstsq(X, log_y, rcond=None)
    return coef


def predict_f3(X: np.ndarray, coef: np.ndarray) -> np.ndarray:
    """Predict latency using F3 Log-Linear parameters."""
    log_pred = X @ coef
    return 10.0 ** log_pred


def fit_f4(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit F4 Family Roofline: t = t0 + a_mlp*W_mlp + a_conv*W_conv + b*data_gb via weighted NNLS."""
    weights = 1.0 / np.maximum(y, 1e-6)
    coef, _ = nnls(X * weights[:, None], y * weights)
    return coef


def predict_f4(X: np.ndarray, coef: np.ndarray) -> np.ndarray:
    """Predict latency using F4 Family Roofline parameters."""
    return np.maximum(X @ coef, 0.0001)


# -----------------------------------------------------------------------------
# 2. Leave-One-Out Cross Validation
# -----------------------------------------------------------------------------

def loo_mape(X: np.ndarray, y: np.ndarray, fit_fn, pred_fn) -> float:
    """Calculate Leave-One-Out Mean Absolute Percentage Error (LOO MAPE)."""
    n = len(y)
    if n <= 1:
        return 0.0
    errs: list[float] = []
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        coef = fit_fn(X[mask], y[mask])
        pred = float(pred_fn(X[i:i + 1], coef)[0])
        actual = float(y[i])
        errs.append(abs(pred - actual) / max(actual, 1e-6))
    return 100.0 * float(np.mean(errs))


def compute_r2_log(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute R^2 on log10 transformed values for goodness of fit."""
    log_true = np.log10(np.maximum(y_true, 1e-6))
    log_pred = np.log10(np.maximum(y_pred, 1e-6))
    ss_res = float(np.sum((log_true - log_pred) ** 2))
    ss_tot = float(np.sum((log_true - np.mean(log_true)) ** 2))
    if ss_tot <= 1e-9:
        return 1.0 if ss_res <= 1e-9 else 0.0
    return float(max(0.0, 1.0 - (ss_res / ss_tot)))


# -----------------------------------------------------------------------------
# 3. Feature Extraction from Real Database Runs
# -----------------------------------------------------------------------------

def prepare_fit_dataset(
    session: Session,
    device_id: int,
    target: str = "latency",
) -> tuple[list[Run], dict[str, np.ndarray], np.ndarray]:
    """Retrieve steady-state valid runs for a device and build design matrices.

    Excludes runs with provider_mismatch or unstable flags.
    """
    dev = session.get(Device, device_id)
    if not dev:
        raise ValueError(f"Device {device_id} not found")

    cache_mb = DEVICE_CACHE_MB.get(dev.key, 32.0)
    cache_gb = cache_mb / 1024.0

    query = select(Run).where(
        Run.device_id == device_id,
        Run.provider_mismatch == False,
        Run.unstable == False,
    )

    if target == "latency":
        query = query.where(Run.median_ms > 0)
    elif target == "energy":
        query = query.where(Run.energy_mj_per_inf != None, Run.energy_mj_per_inf > 0)

    runs = session.exec(query.order_by(Run.id)).all()
    if len(runs) < MIN_FIT_SAMPLES:
        raise ValueError(
            f"Not enough valid steady-state samples for device {dev.key} "
            f"(need at least {MIN_FIT_SAMPLES}, got {len(runs)})"
        )

    # Cache model metadata to avoid repeated DB lookups
    models_map = {m.id: m for m in session.exec(select(AIModel)).all()}

    n = len(runs)
    work_gflop = np.zeros(n, dtype=np.float64)
    work_mlp_gflop = np.zeros(n, dtype=np.float64)
    work_conv_gflop = np.zeros(n, dtype=np.float64)
    data_gb = np.zeros(n, dtype=np.float64)
    params = np.zeros(n, dtype=np.float64)
    batches = np.zeros(n, dtype=np.float64)
    y = np.zeros(n, dtype=np.float64)

    for i, r in enumerate(runs):
        m = models_map.get(r.ai_model_id)
        if not m:
            continue
        b = r.batch
        gflop = (m.flops_per_sample * b) / 1e9
        work_gflop[i] = gflop
        if getattr(m, "family", "") == "conv":
            work_conv_gflop[i] = gflop
        else:
            work_mlp_gflop[i] = gflop
        data_gb[i] = m.weight_bytes / 1e9
        params[i] = max(m.params, 1)
        batches[i] = max(b, 1)
        y[i] = r.median_ms if target == "latency" else (r.energy_mj_per_inf or 0.0)

    # Design matrices
    # F1: [1, work_gflop, data_gb]
    X_f1 = np.column_stack([np.ones(n), work_gflop, data_gb])

    # F2: [1, work_gflop, min(data, cache), max(data - cache, 0)]
    cache_fit = np.minimum(data_gb, cache_gb)
    dram_overflow = np.maximum(data_gb - cache_gb, 0.0)
    X_f2 = np.column_stack([np.ones(n), work_gflop, cache_fit, dram_overflow])

    # F3: [1, log10(params), log10(batch)]
    X_f3 = np.column_stack([np.ones(n), np.log10(params), np.log10(batches)])

    # F4: [1, work_mlp_gflop, work_conv_gflop, data_gb]
    X_f4 = np.column_stack([np.ones(n), work_mlp_gflop, work_conv_gflop, data_gb])

    matrices = {
        "f1": X_f1,
        "f2": X_f2,
        "f3": X_f3,
        "f4": X_f4,
        "work_gflop": work_gflop,
        "data_gb": data_gb,
    }
    return runs, matrices, y


# -----------------------------------------------------------------------------
# 4. Device Predictor Fitting and Database Persistence
# -----------------------------------------------------------------------------

def bootstrap_parameter_cis(
    X: np.ndarray,
    y: np.ndarray,
    fit_fn,
    chosen_form: str,
    rounds: int = 500,
    seed: int = 1234,
) -> dict[str, Any]:
    """Calculate 95% bootstrap confidence intervals for physical parameters.
    
    Uses 500 resamples with fixed seed. If relative half-width > 0.50, flags as 'not reliable'.
    """
    n = len(y)
    if n < 4 or chosen_form not in ("f1_roofline", "f2_cache", "f4_family"):
        return {}

    rng = np.random.default_rng(seed)
    boot_t0 = []
    boot_compute = []
    boot_compute_mlp = []
    boot_compute_conv = []
    boot_bw = []
    boot_bw_dram = []

    for _ in range(rounds):
        idx = rng.choice(n, size=n, replace=True)
        c = fit_fn(X[idx], y[idx])
        boot_t0.append(float(c[0]))
        if chosen_form == "f4_family":
            if c[1] > 1e-7:
                boot_compute_mlp.append(1000.0 / float(c[1]))
            if c[2] > 1e-7:
                boot_compute_conv.append(1000.0 / float(c[2]))
            if c[3] > 1e-7:
                boot_bw.append(1000.0 / float(c[3]))
        else:
            if c[1] > 1e-7:
                boot_compute.append(1000.0 / float(c[1]))
            if c[2] > 1e-7:
                boot_bw.append(1000.0 / float(c[2]))
            if chosen_form == "f2_cache" and len(c) > 3 and c[3] > 1e-7:
                boot_bw_dram.append(1000.0 / float(c[3]))

    results: dict[str, Any] = {}
    for name, vals in [
        ("t0_ms", boot_t0),
        ("compute_gflops", boot_compute),
        ("compute_mlp_gflops", boot_compute_mlp),
        ("compute_conv_gflops", boot_compute_conv),
        ("bandwidth_gb_s", boot_bw),
        ("bandwidth_dram_gb_s", boot_bw_dram),
    ]:
        if not vals:
            continue
        v_arr = np.array(vals)
        low = float(np.percentile(v_arr, 2.5))
        high = float(np.percentile(v_arr, 97.5))
        med = float(np.median(v_arr))
        half_w = (high - low) / 2.0
        rel_ci = half_w / max(med, 1e-6)
        reliable = bool(rel_ci <= 0.50)
        results[name] = {
            "median": round(med, 3),
            "ci_low": round(low, 3),
            "ci_high": round(high, 3),
            "rel_half_width": round(rel_ci, 3),
            "reliable": reliable,
            "status": "reliable" if reliable else "not reliable (CI > ±50%)",
        }
    return results


def fit_device(
    session: Session,
    device_id: int,
    target: str = "latency",
) -> Fit:
    """Fit all 3 candidate forms for a device, pick lowest LOO MAPE, and store Fit."""
    runs, matrices, y = prepare_fit_dataset(session, device_id, target=target)

    # 1. Evaluate LOO error on each form
    loo_f1 = loo_mape(matrices["f1"], y, fit_f1, predict_f1)
    loo_f2 = loo_mape(matrices["f2"], y, fit_f2, predict_f2)
    loo_f3 = loo_mape(matrices["f3"], y, fit_f3, predict_f3)
    loo_f4 = loo_mape(matrices["f4"], y, fit_f4, predict_f4)

    loo_all = {
        "f1_roofline": round(loo_f1, 2),
        "f2_cache": round(loo_f2, 2),
        "f3_loglinear": round(loo_f3, 2),
        "f4_family": round(loo_f4, 2),
    }

    # 2. Select lowest LOO MAPE form
    candidates = [
        ("f1_roofline", loo_f1, matrices["f1"], fit_f1, predict_f1),
        ("f2_cache", loo_f2, matrices["f2"], fit_f2, predict_f2),
        ("f3_loglinear", loo_f3, matrices["f3"], fit_f3, predict_f3),
        ("f4_family", loo_f4, matrices["f4"], fit_f4, predict_f4),
    ]
    candidates.sort(key=lambda c: c[1])
    chosen_form, best_loo, X_chosen, fit_chosen, pred_chosen = candidates[0]

    # Full fit on all available steady-state data
    coef = fit_chosen(X_chosen, y)
    y_pred = pred_chosen(X_chosen, coef)
    r2_log = compute_r2_log(y, y_pred)

    # 3. Physical parameter extraction when F1, F2, or F4 wins
    t0_ms: Optional[float] = None
    compute_gflops: Optional[float] = None
    bandwidth_gb_s: Optional[float] = None
    bandwidth_dram_gb_s: Optional[float] = None
    notes: Optional[str] = None
    notes_dict: dict[str, Any] = {}

    if chosen_form in ("f1_roofline", "f2_cache", "f4_family"):
        t0_ms = round(float(coef[0]), 4)

        if chosen_form == "f4_family":
            # coef: [t0, a_mlp, a_conv, b]
            if coef[1] > 1e-7:
                compute_gflops = round(1000.0 / float(coef[1]), 2)
                notes_dict["compute_mlp_gflops"] = compute_gflops
            if coef[2] > 1e-7:
                notes_dict["compute_conv_gflops"] = round(1000.0 / float(coef[2]), 2)
            if coef[3] > 1e-7:
                bandwidth_gb_s = round(1000.0 / float(coef[3]), 2)
        elif chosen_form == "f1_roofline":
            if coef[1] > 1e-7:
                compute_gflops = round(1000.0 / float(coef[1]), 2)
            if coef[2] > 1e-7:
                bandwidth_gb_s = round(1000.0 / float(coef[2]), 2)
        else:
            if coef[1] > 1e-7:
                compute_gflops = round(1000.0 / float(coef[1]), 2)
            if coef[2] > 1e-7:
                bandwidth_gb_s = round(1000.0 / float(coef[2]), 2)
            if coef[3] > 1e-7:
                bandwidth_dram_gb_s = round(1000.0 / float(coef[3]), 2)

        # Check parameter separability (need diverse compute-to-memory ratios)
        work_arr = matrices["work_gflop"]
        data_arr = matrices["data_gb"]
        work_span = (np.max(work_arr) - np.min(work_arr)) / max(np.mean(work_arr), 1e-6)
        data_span = (np.max(data_arr) - np.min(data_arr)) / max(np.mean(data_arr), 1e-6)
        if work_span < 0.1 or data_span < 0.1:
            notes = "compute and memory terms not separable"

    # Compute bootstrap 95% confidence intervals for physical parameters (500 resamples)
    ci_results = bootstrap_parameter_cis(X_chosen, y, fit_chosen, chosen_form, rounds=500, seed=1234)
    if notes:
        notes_dict["separability"] = notes
    if ci_results:
        notes_dict["parameter_cis"] = ci_results
    final_notes = json.dumps(notes_dict) if notes_dict else None

    # Deactivate previous active fits for this device and target
    existing_fits = session.exec(
        select(Fit).where(Fit.device_id == device_id, Fit.target == target, Fit.is_active == True)
    ).all()
    for ef in existing_fits:
        ef.is_active = False
        session.add(ef)

    now_iso = datetime.now(timezone.utc).isoformat()
    fit_record = Fit(
        device_id=device_id,
        target=target,
        model_form=chosen_form,
        loo_mape_all_json=json.dumps(loo_all),
        coef_json=json.dumps([round(float(c), 6) for c in coef]),
        n_samples=len(runs),
        r2_log=round(r2_log, 4),
        loo_mape_pct=round(best_loo, 2),
        t0_ms=t0_ms,
        compute_gflops=compute_gflops,
        bandwidth_gb_s=bandwidth_gb_s,
        bandwidth_dram_gb_s=bandwidth_dram_gb_s,
        notes=final_notes,
        trained_at=now_iso,
        is_active=True,
    )
    session.add(fit_record)
    session.commit()
    session.refresh(fit_record)
    return fit_record


def predict_for_fit(fit: Fit, model: AIModel, batch: int, cache_mb: float = 32.0) -> float:
    """Predict latency in ms for a given model and batch using the fitted model."""
    coef = np.array(json.loads(fit.coef_json), dtype=np.float64)
    work_gflop = (model.flops_per_sample * batch) / 1e9
    data_gb = model.weight_bytes / 1e9
    cache_gb = cache_mb / 1024.0

    if fit.model_form == "f1_roofline":
        X = np.array([[1.0, work_gflop, data_gb]])
        return float(predict_f1(X, coef)[0])
    elif fit.model_form == "f2_cache":
        c_part = min(data_gb, cache_gb)
        d_part = max(data_gb - cache_gb, 0.0)
        X = np.array([[1.0, work_gflop, c_part, d_part]])
        return float(predict_f2(X, coef)[0])
    elif fit.model_form == "f4_family":
        is_conv = getattr(model, "family", "") == "conv"
        w_mlp = 0.0 if is_conv else work_gflop
        w_conv = work_gflop if is_conv else 0.0
        X = np.array([[1.0, w_mlp, w_conv, data_gb]])
        return float(predict_f4(X, coef)[0])
    else:
        # f3_loglinear
        X = np.array([[1.0, np.log10(max(model.params, 1)), np.log10(max(batch, 1))]])
        return float(predict_f3(X, coef)[0])


# -----------------------------------------------------------------------------
# 5. Cold-Start Analysis & Summary
# -----------------------------------------------------------------------------

def get_cold_start_summary(session: Session, device_id: Optional[int] = None) -> list[dict[str, Any]]:
    """Compute cold-start overhead summary per device, including NVIDIA P-state split."""
    devices_query = select(Device).where(Device.is_available == True)
    if device_id is not None:
        devices_query = devices_query.where(Device.id == device_id)
    devices = session.exec(devices_query).all()

    summary: list[dict[str, Any]] = []
    for d in devices:
        runs = session.exec(
            select(Run).where(
                Run.device_id == d.id,
                Run.first_run_ms != None,
                Run.median_ms > 0,
            )
        ).all()

        if not runs:
            continue

        first_runs = np.array([r.first_run_ms for r in runs if r.first_run_ms is not None])
        medians = np.array([r.median_ms for r in runs if r.first_run_ms is not None])
        deltas = first_runs - medians

        med_first = float(np.median(first_runs)) if len(first_runs) else None
        med_delta = float(np.median(deltas)) if len(deltas) else None

        item: dict[str, Any] = {
            "device_id": d.id,
            "device_key": d.key,
            "device_label": d.label,
            "kind": d.kind,
            "sample_count": len(runs),
            "median_first_run_ms": round(med_first, 3) if med_first is not None else None,
            "median_wake_penalty_ms": round(med_delta, 3) if med_delta is not None else None,
        }

        # For dml:1 / NVIDIA GPU: split by P8 (sleep) vs P0-P5 (active)
        if d.key == "dml:1" or d.kind == "dgpu":
            p8_runs = [r for r in runs if r.nvml_pstate_start == 8]
            act_runs = [r for r in runs if r.nvml_pstate_start is not None and r.nvml_pstate_start < 8]

            if p8_runs:
                p8_firsts = np.array([r.first_run_ms for r in p8_runs if r.first_run_ms is not None])
                p8_meds = np.array([r.median_ms for r in p8_runs if r.first_run_ms is not None])
                item["p8_sleep_first_run_ms"] = round(float(np.median(p8_firsts)), 3)
                item["p8_sleep_penalty_ms"] = round(float(np.median(p8_firsts - p8_meds)), 3)

            if act_runs:
                act_firsts = np.array([r.first_run_ms for r in act_runs if r.first_run_ms is not None])
                act_meds = np.array([r.median_ms for r in act_runs if r.first_run_ms is not None])
                item["active_first_run_ms"] = round(float(np.median(act_firsts)), 3)
                item["active_penalty_ms"] = round(float(np.median(act_firsts - act_meds)), 3)

        summary.append(item)

    return summary


# -----------------------------------------------------------------------------
# 6. Crossover Analysis
# -----------------------------------------------------------------------------

def calculate_crossover(
    session: Session,
    device_a_id: int,
    device_b_id: int,
    family: str = "mlp",
    batch: int = 1,
) -> dict[str, Any]:
    """Find the crossover model size between two devices for a given family and batch."""
    dev_a = session.get(Device, device_a_id)
    dev_b = session.get(Device, device_b_id)
    if not dev_a or not dev_b:
        raise ValueError("One or both devices not found")

    fit_a = session.exec(select(Fit).where(Fit.device_id == dev_a.id, Fit.is_active == True)).first()
    fit_b = session.exec(select(Fit).where(Fit.device_id == dev_b.id, Fit.is_active == True)).first()

    if not fit_a or not fit_b:
        raise ValueError(f"Active fits not found for {dev_a.key} and/or {dev_b.key}")

    # Build model grid for this family
    measured_models = session.exec(
        select(AIModel).where(AIModel.family == family).order_by(AIModel.params)
    ).all()
    if not measured_models:
        raise ValueError(f"No models registered for family {family}")

    max_measured_params = max(m.params for m in measured_models)
    max_extrapolated_params = max_measured_params * 2

    # Define search bounds and fine evaluation grid (>= 200 points)
    if family == "conv":
        min_sz, max_sz = 8, 192
        display_sizes = [8, 12, 16, 24, 32, 48, 64, 96, 128]
    else:
        min_sz, max_sz = 32, 4096
        display_sizes = [32, 64, 128, 256, 512, 768, 1024, 1536, 2048, 3072, 4096]

    fine_sizes = [int(x) for x in np.unique(np.round(np.logspace(np.log10(min_sz), np.log10(max_sz), num=250)).astype(int))]

    crossover_point: Optional[dict[str, Any]] = None
    prev_faster: Optional[str] = None
    fine_crossover_size: Optional[int] = None

    # Helper function to predict for a size
    def predict_size(s: int) -> tuple[float, float, int, float, bool]:
        if family == "conv":
            params = 4 * s * s * 9
            flops_per_sample = float(2 * 4 * 64 * 64 * s * s * 9)
        else:
            params = 4 * s * s
            flops_per_sample = float(2 * 4 * s * s)
        dummy_model = AIModel(
            name=f"{family}_{s}",
            family=family,
            path="",
            params=params,
            flops_per_sample=flops_per_sample,
            weight_bytes=params * 4,
        )
        pred_a = predict_for_fit(fit_a, dummy_model, batch, DEVICE_CACHE_MB.get(dev_a.key, 32.0))
        pred_b = predict_for_fit(fit_b, dummy_model, batch, DEVICE_CACHE_MB.get(dev_b.key, 32.0))
        is_extrapolated = bool(params > max_measured_params)
        return pred_a, pred_b, params, flops_per_sample, is_extrapolated

    # 1. Fine-grid search over 250 log-spaced points
    for s in fine_sizes:
        pa, pb, params, flops, is_extrapolated = predict_size(s)
        if params > max_extrapolated_params:
            break
        faster = dev_a.key if pa < pb else dev_b.key
        if prev_faster is not None and faster != prev_faster and crossover_point is None:
            crossover_point = {
                "size": s,
                "width": s,
                "params": params,
                "switched_to": faster,
                "pred_a_ms": round(pa, 4),
                "pred_b_ms": round(pb, 4),
                "extrapolated": is_extrapolated,
            }
            fine_crossover_size = s
        prev_faster = faster

    # 2. Build display grid points
    grid_points = []
    combined_display_sizes = sorted(set(display_sizes + ([fine_crossover_size] if fine_crossover_size else [])))
    for s in combined_display_sizes:
        pa, pb, params, flops, is_extrapolated = predict_size(s)
        if params > max_extrapolated_params:
            continue
        grid_points.append({
            "size": s,
            "width": s,
            "params": params,
            "pred_a_ms": round(pa, 4),
            "pred_b_ms": round(pb, 4),
            "faster_device": dev_a.key if pa < pb else dev_b.key,
            "extrapolated": is_extrapolated,
        })

    summary_text = (
        f"Crossover at size={crossover_point['size']} ({crossover_point['params']} params) where {crossover_point['switched_to']} becomes faster"
        if crossover_point
        else f"{prev_faster} is faster across the entire measured range"
    )

    return {
        "device_a": dev_a.key,
        "device_b": dev_b.key,
        "family": family,
        "batch": batch,
        "crossover": crossover_point,
        "summary": summary_text,
        "grid": grid_points,
    }
