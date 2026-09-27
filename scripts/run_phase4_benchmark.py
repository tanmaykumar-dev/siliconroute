"""Phase 4 Benchmark and Predictor Validation Script.

1. Generates and registers the synthetic MLP and Conv ladders (SPEC Section 3).
2. Executes full latency benchmark across all available hardware devices (CPU, dml:0, dml:1)
   and batches [1, 8, 32] with 5 warmups and 30 timed runs.
3. Fits the latency models (F1 roofline, F2 roofline+cache, F3 log-linear) per device,
   computing LOO MAPE, t0, GFLOP/s, and GB/s.
4. Computes MLP crossover at batches [1, 8, 32].
5. Computes cold-start latency and wake penalties with NVIDIA P-state split.
6. Prints out all gate tables directly from real SQLite measurements.
"""

from datetime import datetime, timezone
import json
import logging
import sys
import time
from typing import Any

import numpy as np
from sqlmodel import Session, select

from app.benchmark import execute_latency_job
from app.config import (
    BATCHES,
    TIMED_RUNS,
    WARMUP_RUNS,
)
from app.db import AIModel, BenchSession, Device, Fit, Run, engine, init_db
from app.models_gen import create_and_register_synthetic
from app.predictor import calculate_crossover, fit_device, get_cold_start_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase4_benchmark")


def ensure_ladders(session: Session) -> list[AIModel]:
    """Generate and register the full MLP and Conv model ladders from SPEC Section 3."""
    models: list[AIModel] = []

    mlp_widths = [32, 64, 128, 256, 384, 512, 768, 1024, 1536, 2048]
    logger.info("Generating MLP ladder (L=4): widths %s", mlp_widths)
    for w in mlp_widths:
        m = create_and_register_synthetic(session, family="mlp", size=w, layers=4)
        models.append(m)

    conv_channels = [8, 16, 32, 48, 64]
    logger.info("Generating Conv ladder (H=W=64, L=4): channels %s", conv_channels)
    for c in conv_channels:
        m = create_and_register_synthetic(session, family="conv", size=c, layers=4)
        models.append(m)

    return models


def get_target_devices(session: Session) -> list[Device]:
    """Retrieve the 3 real compute devices: CPU, Radeon 610M (dml:0), RTX 5070 (dml:1)."""
    devices = session.exec(
        select(Device).where(
            Device.is_available == True,
            Device.key.in_(["cpu", "dml:0", "dml:1"]),
        ).order_by(Device.id)
    ).all()
    return list(devices)


def main():
    init_db()
    with Session(engine) as session:
        devices = get_target_devices(session)
        logger.info("Target devices for Phase 4: %s", [(d.id, d.key, d.label) for d in devices])
        if len(devices) < 3:
            logger.error("Expected 3 available devices (cpu, dml:0, dml:1), found: %d", len(devices))
            sys.exit(1)

        models = ensure_ladders(session)
        logger.info("Total models in Phase 4 ladder: %d", len(models))

        # Create latency benchmark session
        model_ids = [int(m.id) for m in models]
        device_ids = [int(d.id) for d in devices]

        now_iso = datetime.now(timezone.utc).isoformat()
        bench_sess = BenchSession(
            kind="latency",
            status="queued",
            config_json=json.dumps({
                "models": model_ids,
                "devices": device_ids,
                "batches": BATCHES,
                "warmup_runs": WARMUP_RUNS,
                "timed_runs": TIMED_RUNS,
            }),
            created_at=now_iso,
            notes="Phase 4 full ladder benchmark for hardware model fits and crossover",
        )
        session.add(bench_sess)
        session.commit()
        session.refresh(bench_sess)
        session_id = bench_sess.id

    logger.info("Starting execution of Benchmark Session %d...", session_id)
    progress_state: dict[str, Any] = {"done": 0, "total": 0, "cancel": False, "item": None}

    execute_latency_job(
        bench_session_id=session_id,
        model_ids=model_ids,
        device_ids=device_ids,
        batches=BATCHES,
        warmup_runs=WARMUP_RUNS,
        timed_runs=TIMED_RUNS,
        progress_state=progress_state,
    )

    logger.info("Benchmark session %d finished. Progress: %d / %d", session_id, progress_state["done"], progress_state["total"])

    # Perform fits for each device
    with Session(engine) as session:
        devices = get_target_devices(session)
        fits = {}
        for dev in devices:
            fit_rec = fit_device(session, dev.id, target="latency")
            fits[dev.key] = fit_rec
            logger.info("Fit for %s: form=%s, LOO MAPE=%.2f%%, t0=%.3f ms", dev.key, fit_rec.model_form, fit_rec.loo_mape_pct, fit_rec.t0_ms or 0.0)

        # Print Gate Table 1: Device Fits & Physical Parameters
        print("\n" + "=" * 90)
        print("PHASE 4 GATE TABLE 1: PER-DEVICE HARDWARE MODEL FITS (REAL MEASUREMENTS)")
        print("=" * 90)
        hdr = f"{'Device':<8} | {'Label':<28} | {'Chosen Form':<13} | {'LOO F1':<7} | {'LOO F2':<7} | {'LOO F3':<7} | {'t0 (ms)':<8} | {'GFLOP/s':<9} | {'GB/s':<8} | {'R2_log':<6}"
        print(hdr)
        print("-" * len(hdr))

        for dev in devices:
            f = fits[dev.key]
            loo_dict = json.loads(f.loo_mape_all_json) if f.loo_mape_all_json else {}
            loo_f1 = f"{loo_dict.get('f1_roofline', 0.0):.1f}%"
            loo_f2 = f"{loo_dict.get('f2_cache', 0.0):.1f}%"
            loo_f3 = f"{loo_dict.get('f3_loglinear', 0.0):.1f}%"
            t0_str = f"{f.t0_ms:.3f}" if f.t0_ms is not None else "N/A"
            gf_str = f"{f.compute_gflops:.1f}" if f.compute_gflops is not None else "N/A"
            gb_str = f"{f.bandwidth_gb_s:.1f}" if f.bandwidth_gb_s is not None else "N/A"
            r2_str = f"{f.r2_log:.3f}" if f.r2_log is not None else "N/A"
            print(f"{dev.key:<8} | {dev.label:<28} | {f.model_form:<13} | {loo_f1:<7} | {loo_f2:<7} | {loo_f3:<7} | {t0_str:<8} | {gf_str:<9} | {gb_str:<8} | {r2_str:<6}")
        print("=" * 90)

        # Print Gate Table 2: MLP Crossover Analysis at Batches 1, 8, 32
        print("\n" + "=" * 90)
        print("PHASE 4 GATE TABLE 2: MLP CROSSOVER POINTS (CPU vs RTX 5070 dGPU)")
        print("=" * 90)
        cpu_dev = next(d for d in devices if d.key == "cpu")
        rtx_dev = next(d for d in devices if d.key == "dml:1")
        rad_dev = next(d for d in devices if d.key == "dml:0")

        for b in [1, 8, 32]:
            xo = calculate_crossover(session, cpu_dev.id, rtx_dev.id, family="mlp", batch=b)
            cp = xo.get("crossover")
            print(f"\n--- Batch B={b} ---")
            if cp:
                print(f"  Crossover point: Width = {cp['width']} ({cp['params']:,} params, {cp['params']*4/1e6:.2f} MB)")
                print(f"  Switched to: {cp['switched_to']} (Faster)")
                print(f"  CPU predicted: {cp['pred_a_ms']:.3f} ms | RTX 5070 predicted: {cp['pred_b_ms']:.3f} ms")
                print(f"  Extrapolated: {cp['extrapolated']}")
            else:
                grid = xo["grid"]
                print(f"  No crossover detected in range: {grid[0]['faster_device']} is faster across the entire measured range (width {grid[0]['width']} to {grid[-1]['width']})")
                print(f"  Width {grid[0]['width']}: CPU={grid[0]['pred_a_ms']:.3f} ms, RTX={grid[0]['pred_b_ms']:.3f} ms ({grid[0]['faster_device']} faster)")
                print(f"  Width {grid[-1]['width']}: CPU={grid[-1]['pred_a_ms']:.3f} ms, RTX={grid[-1]['pred_b_ms']:.3f} ms ({grid[-1]['faster_device']} faster)")

        print("\n" + "=" * 90)
        print("PHASE 4 GATE TABLE 3: COLD-START & WAKE PENALTY SUMMARY")
        print("=" * 90)
        cold_summary = get_cold_start_summary(session)
        cs_hdr = f"{'Device':<8} | {'Label':<28} | {'Samples':<7} | {'Med 1st (ms)':<12} | {'Wake Pen (ms)':<13} | {'P8 Wake (ms)':<12} | {'Active 1st (ms)':<15}"
        print(cs_hdr)
        print("-" * len(cs_hdr))
        for cs in cold_summary:
            dev_k = cs["device_key"]
            lbl = cs["device_label"]
            cnt = cs["sample_count"]
            m1 = f"{cs['median_first_run_ms']:.3f}" if cs.get("median_first_run_ms") is not None else "N/A"
            wp = f"{cs['median_wake_penalty_ms']:.3f}" if cs.get("median_wake_penalty_ms") is not None else "N/A"
            p8_w = f"{cs['p8_sleep_penalty_ms']:.3f}" if cs.get("p8_sleep_penalty_ms") is not None else "N/A"
            act_1 = f"{cs['active_first_run_ms']:.3f}" if cs.get("active_first_run_ms") is not None else "N/A"
            print(f"{dev_k:<8} | {lbl:<28} | {cnt:<7} | {m1:<12} | {wp:<13} | {p8_w:<12} | {act_1:<15}")
        print("=" * 90)


if __name__ == "__main__":
    main()
