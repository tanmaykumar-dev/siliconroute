"""Hardware performance analysis API endpoints (crossover, cold-start, variability, physics notes, and plot data)."""

from collections import defaultdict
import json
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
import numpy as np
from sqlmodel import Session, select

from app.config import DEVICE_CACHE_MB
from app.db import AIModel, Device, Fit, Run, WorkloadMeasurement, get_session
from app.predictor import calculate_crossover, get_cold_start_summary, predict_for_fit
from app.router import calculate_device_volatility_bands

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/crossover")
def get_crossover_analysis(
    dev_a: str = Query(default="cpu", description="Key of first device, e.g. cpu"),
    dev_b: str = Query(default="dml:1", description="Key of second device, e.g. dml:1"),
    family: str = Query(default="mlp", description="Model family (mlp | conv)"),
    batch: int = Query(default=1, ge=1, le=256),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Calculate the crossover model size between two devices for a given family and batch."""
    da = session.exec(select(Device).where(Device.key == dev_a)).first()
    db = session.exec(select(Device).where(Device.key == dev_b)).first()

    if not da:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device {dev_a} not found")
    if not db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device {dev_b} not found")

    try:
        return calculate_crossover(session, da.id, db.id, family=family, batch=batch)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/crossovers-all")
def get_all_crossovers(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Retrieve all standard pairwise crossover points across CPU, AMD iGPU (dml:0), and NVIDIA dGPU (dml:1)."""
    pairs = [("cpu", "dml:1"), ("cpu", "dml:0"), ("dml:0", "dml:1")]
    configs = [
        ("mlp", 1),
        ("mlp", 8),
        ("conv", 1),
        ("conv", 8),
    ]

    results: list[dict[str, Any]] = []
    for family, batch in configs:
        for dev_a, dev_b in pairs:
            da = session.exec(select(Device).where(Device.key == dev_a)).first()
            db = session.exec(select(Device).where(Device.key == dev_b)).first()
            if not da or not db:
                continue
            try:
                co = calculate_crossover(session, da.id, db.id, family=family, batch=batch)
                results.append({
                    "dev_a": dev_a,
                    "dev_b": dev_b,
                    "dev_a_label": da.label,
                    "dev_b_label": db.label,
                    "family": family,
                    "batch": batch,
                    "crossover": co.get("crossover"),
                    "summary": co.get("summary"),
                })
            except Exception:
                continue

    return results


@router.get("/cold-start")
def get_cold_start_data(
    device_id: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Retrieve cold-start latencies and wake-up penalties per device."""
    return get_cold_start_summary(session, device_id=device_id)


@router.get("/variability")
def get_session_variability(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Retrieve the multi-session variability table and volatility bands per device."""
    bands = calculate_device_volatility_bands(session)
    devices = session.exec(select(Device).where(Device.is_available == True)).all()
    dev_map = {d.id: d for d in devices}

    # Query all valid, non-suspect runs
    runs = session.exec(
        select(Run, AIModel, Device)
        .join(AIModel, Run.ai_model_id == AIModel.id)
        .join(Device, Run.device_id == Device.id)
        .where(
            Run.session_id != None,
            Run.unstable == False,
            Run.identity_suspect == False,
        )
    ).all()

    # Group runs by (device_id, ai_model_id, batch) -> {session_id: list[median_ms]}
    configs: dict[tuple[int, int, int], dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    config_metadata: dict[tuple[int, int, int], dict[str, Any]] = {}

    for run, model, dev in runs:
        if run.session_id is not None:
            key = (run.device_id, run.ai_model_id, run.batch)
            configs[key][run.session_id].append(run.median_ms)
            if key not in config_metadata:
                config_metadata[key] = {
                    "device_id": dev.id,
                    "device_key": dev.key,
                    "device_label": dev.label,
                    "model_id": model.id,
                    "model_name": model.name,
                    "family": model.family,
                    "batch": run.batch,
                }

    details: list[dict[str, Any]] = []
    device_multi_counts: dict[int, int] = defaultdict(int)

    for key, sess_dict in configs.items():
        if len(sess_dict) > 1:
            meta = config_metadata[key]
            device_multi_counts[meta["device_id"]] += 1
            sess_meds = {sid: round(float(np.median(vals)), 3) for sid, vals in sorted(sess_dict.items())}
            min_val = min(sess_meds.values())
            max_val = max(sess_meds.values())
            diff_pct = round(((max_val - min_val) / max(min_val, 1e-4)) * 100.0, 1)

            details.append({
                **meta,
                "session_count": len(sess_dict),
                "sessions": sess_meds,
                "min_median_ms": min_val,
                "max_median_ms": max_val,
                "diff_pct": diff_pct,
            })

    details.sort(key=lambda x: x["diff_pct"], reverse=True)

    summary: list[dict[str, Any]] = []
    for d in devices:
        band = bands.get(d.id, 15.0)
        cnt = device_multi_counts.get(d.id, 0)
        summary.append({
            "device_id": d.id,
            "device_key": d.key,
            "device_label": d.label,
            "kind": d.kind,
            "volatility_band_pct": band,
            "multi_session_configs_count": cnt,
            "description": f"+/-{band}% historical session variability",
        })

    return {
        "summary": summary,
        "details": details,
    }


@router.get("/physics-notes")
def get_physics_notes(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Retrieve runs with physics notes (e.g. Winograd minimal filtering convolution speedups)."""
    # Theoretical ceilings (datasheet values, not measured)
    peaks = {
        "cpu": {"peak_gflops": 1400.0, "dram_gb_s": 83.2, "note": "AMD Ryzen 9 8940HX (datasheet, not measured)"},
        "dml:0": {"peak_gflops": 563.0, "dram_gb_s": 83.2, "note": "AMD Radeon 610M (datasheet, not measured)"},
        "dml:1": {"peak_gflops": 25000.0, "vram_gb_s": 320.0, "note": "NVIDIA RTX 5070 Laptop (datasheet, not measured)"},
    }

    runs = session.exec(
        select(Run, AIModel, Device)
        .join(AIModel, Run.ai_model_id == AIModel.id)
        .join(Device, Run.device_id == Device.id)
        .where(
            Run.median_ms > 0,
            (Run.physics_note != None) | ((AIModel.family == "conv") & (Device.key == "dml:0"))
        )
        .order_by(Run.id)
    ).all()

    exceeding_records: list[dict[str, Any]] = []
    for r, m, d in runs:
        total_flops = (m.flops_per_sample or 0) * r.batch
        implied_gflops = round(total_flops / (r.median_ms * 1e6), 1) if r.median_ms > 0 else 0.0
        peak_info = peaks.get(d.key, {"peak_gflops": 1000.0, "note": "Unknown"})
        peak_gflops = peak_info["peak_gflops"]

        is_exceeding = implied_gflops > peak_gflops
        note = r.physics_note
        if is_exceeding and not note:
            note = f"Algorithmic Winograd complexity reduction (implied {implied_gflops} GFLOP/s > peak {peak_gflops})"

        if note or is_exceeding:
            exceeding_records.append({
                "run_id": r.id,
                "session_id": r.session_id,
                "device_key": d.key,
                "device_label": d.label,
                "model_name": m.name,
                "family": m.family,
                "batch": r.batch,
                "median_ms": round(r.median_ms, 3),
                "implied_gflops": implied_gflops,
                "datasheet_peak_gflops": peak_gflops,
                "datasheet_note": peak_info["note"],
                "identity_suspect": r.identity_suspect,
                "physics_note": note,
                "is_effective_speed": True,
            })

    return {
        "explanation": (
            "Under Winograd minimal filtering algorithms (F(2x2, 3x3) or F(4x4, 3x3)), 3x3 2D convolution requires "
            "2.25x to 4x fewer multiplications than direct GEMM. The implied GFLOP/s exceeds theoretical hardware "
            "compute peaks because DirectML executes Winograd transformations on small tiles rather than brute-force "
            "matrix multiplications. These numbers represent EFFECTIVE computational throughput, not raw silicon frequency. "
            "Hardware peaks are datasheet theoretical limits, not measured."
        ),
        "datasheet_peaks": peaks,
        "runs": exceeding_records,
    }


@router.get("/chart-data")
def get_chart_data(
    family: str = Query(default="mlp", description="Model family (mlp | conv)"),
    batch: int = Query(default=1, ge=1, le=256),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Retrieve measured run points and smooth predicted curves for log-log scaling charts."""
    devices = session.exec(select(Device).where(Device.is_available == True)).all()
    devices_info = [{"id": d.id, "key": d.key, "label": d.label, "kind": d.kind} for d in devices]

    # Query measured runs for this family and batch
    runs = session.exec(
        select(Run, AIModel, Device)
        .join(AIModel, Run.ai_model_id == AIModel.id)
        .join(Device, Run.device_id == Device.id)
        .where(
            AIModel.family == family,
            Run.batch == batch,
            Run.median_ms > 0,
            Run.identity_suspect == False,
        )
        .order_by(AIModel.params, Run.id)
    ).all()

    runs_by_device: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r, m, d in runs:
        runs_by_device[d.key].append({
            "run_id": r.id,
            "session_id": r.session_id,
            "device_key": d.key,
            "model_name": m.name,
            "params": m.params,
            "weight_bytes": m.weight_bytes,
            "weight_mb": round(m.weight_bytes / (1024 * 1024), 2),
            "flops_per_sample": m.flops_per_sample,
            "batch": r.batch,
            "median_ms": round(r.median_ms, 3),
            "p10_ms": round(r.p10_ms, 3) if r.p10_ms is not None else None,
            "p90_ms": round(r.p90_ms, 3) if r.p90_ms is not None else None,
            "inner_loop_k": r.inner_loop_k,
            "cv": round(r.cv, 3) if r.cv is not None else None,
            "unstable": r.unstable,
        })

    # Generate smooth fitted curve points using active fits
    curves_by_device: dict[str, list[dict[str, Any]]] = {}
    fits_info: dict[str, Any] = {}

    if family == "conv":
        widths = [8, 12, 16, 24, 32, 48, 64, 96, 128, 160, 192]
    else:
        widths = [32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096]

    for d in devices:
        fit = session.exec(select(Fit).where(Fit.device_id == d.id, Fit.is_active == True)).first()
        if not fit:
            continue

        fits_info[d.key] = {
            "model_form": fit.model_form,
            "t0_ms": round(fit.t0_ms, 4) if fit.t0_ms is not None else 0.0,
            "compute_gflops": round(fit.compute_gflops, 1) if fit.compute_gflops is not None else 0.0,
            "dram_bandwidth_gb_s": round(fit.bandwidth_dram_gb_s, 1) if fit.bandwidth_dram_gb_s is not None else 0.0,
            "sram_bandwidth_gb_s": round(fit.bandwidth_gb_s, 1) if fit.bandwidth_gb_s is not None else 0.0,
            "loo_mape_pct": round(fit.loo_mape_pct, 1) if fit.loo_mape_pct is not None else None,
        }

        curve_points: list[dict[str, Any]] = []
        for w in widths:
            if family == "conv":
                params = 4 * w * w * 9
                flops = float(2 * 4 * 64 * 64 * w * w * 9)
            else:
                params = 4 * w * w
                flops = float(2 * 4 * w * w)
            dummy_m = AIModel(
                name=f"{family}_{w}",
                family=family,
                path="",
                params=params,
                flops_per_sample=flops,
                weight_bytes=params * 4,
            )
            cache_mb = DEVICE_CACHE_MB.get(d.key, 32.0)
            pred_ms = predict_for_fit(fit, dummy_m, batch, cache_mb)
            curve_points.append({
                "params": params,
                "weight_mb": round((params * 4) / (1024 * 1024), 2),
                "pred_ms": round(pred_ms, 3),
            })

        curves_by_device[d.key] = curve_points

    return {
        "family": family,
        "batch": batch,
        "devices": devices_info,
        "runs": runs_by_device,
        "curves": curves_by_device,
        "fits": fits_info,
    }


@router.get("/wake-cold")
def get_wake_cold_analysis(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Retrieve detailed wake penalties, cold starts, and workload measurements."""
    cold_summary = get_cold_start_summary(session)

    # Fetch measurements from WorkloadMeasurement table
    measurements = session.exec(
        select(WorkloadMeasurement, AIModel, Device)
        .join(AIModel, WorkloadMeasurement.ai_model_id == AIModel.id)
        .join(Device, WorkloadMeasurement.device_id == Device.id)
        .order_by(WorkloadMeasurement.id)
    ).all()

    workload_rows: list[dict[str, Any]] = []
    for wm, m, d in measurements:
        workload_rows.append({
            "id": wm.id,
            "model_name": m.name,
            "device_key": d.key,
            "device_label": d.label,
            "batch": wm.batch,
            "workload": wm.workload,
            "latency_ms": round(wm.latency_ms, 3) if wm.latency_ms is not None else None,
            "session_create_ms": round(wm.session_create_ms, 3) if wm.session_create_ms is not None else None,
            "first_run_ms": round(wm.first_run_ms, 3) if wm.first_run_ms is not None else None,
            "nvml_pstate": wm.nvml_pstate,
        })

    return {
        "summary": cold_summary,
        "measurements": workload_rows,
    }
