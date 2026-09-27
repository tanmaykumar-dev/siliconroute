"""Phase 4.1 execution script:
1. Generates extended synthetic models (MLP 3072, 4096; Conv 96, 128) with RAM safety check.
2. Benchmarks extended models across CPU, dml:0, and dml:1 (B=1, 8, 32).
3. Executes the idle-gap GPU wake test (0.5s, 2s, 10s, 30s) measuring pre-inference P-states.
4. Refits hardware models for all 3 chips on genuine data only with 500-round bootstrap 95% CIs.
5. Computes fine-grid crossovers (250 points) between CPU and RTX 5070.
6. Prints all verification tables.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, os.path.abspath("."))

import numpy as np
import psutil
from sqlmodel import Session, select

from app.benchmark import run_latency_measurement, check_and_mark_duplicate_devices
from app.config import (
    COOLDOWN_S,
    DEVICE_CACHE_MB,
    SEED,
    TIMED_RUNS,
    WARMUP_RUNS,
)
from app.db import AIModel, BenchSession, Device, Fit, Run, engine, init_db
from app.devices import make_session
from app.models_gen import create_and_register_synthetic
from app.power import nvml_reader
from app.predictor import calculate_crossover, fit_device

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase4_ext")


def check_ram_safe(weight_bytes: int) -> bool:
    """Ensure free RAM is at least 2x model weight bytes."""
    avail = psutil.virtual_memory().available
    needed = weight_bytes * 2
    if avail < needed:
        logger.warning("Skipping model: Available RAM (%d MB) < 2x weight (%d MB)", avail // 1048576, needed // 1048576)
        return False
    return True


def step1_create_extended_models(session: Session) -> list[AIModel]:
    print("\n" + "=" * 80)
    print("STEP 1: GENERATING EXTENDED SYNTHETIC LADDERS (MLP 3072, 4096; Conv 96, 128)")
    print("=" * 80)

    extended_specs = [
        ("mlp", 3072, 4),
        ("mlp", 4096, 4),
        ("conv", 96, 4),
        ("conv", 128, 4),
    ]

    models: list[AIModel] = []
    for family, sz, layers in extended_specs:
        approx_weights = (layers * sz * sz * (9 if family == "conv" else 1)) * 4
        if not check_ram_safe(approx_weights):
            continue
        print(f"Generating {family.upper()} size={sz} (layers={layers}, approx {approx_weights / (1024*1024):.1f} MB)...")
        m = create_and_register_synthetic(session, family, sz, layers)
        models.append(m)
        print(f"  -> Created {m.name}: {m.params:,} params, {m.weight_bytes / (1024*1024):.2f} MB, {m.flops_per_sample / 1e9:.4f} GFLOP/sample")

    return models


def step2_benchmark_extended_models(session: Session, models: list[AIModel]):
    print("\n" + "=" * 80)
    print("STEP 2: BENCHMARKING EXTENDED MODELS ACROSS CHIPS (cpu, dml:0, dml:1)")
    print("=" * 80)

    devices = session.exec(select(Device).where(Device.is_available == True).order_by(Device.id)).all()
    batches = [1, 8, 32]

    now_iso = datetime.now(timezone.utc).isoformat()
    bench_sess = BenchSession(
        kind="latency",
        status="running",
        config_json=json.dumps({"extended_phase4": True}),
        created_at=now_iso,
        notes="Phase 4.1: Extended synthetic ladders to locate batch-1 crossover",
    )
    session.add(bench_sess)
    session.commit()
    session.refresh(bench_sess)

    results_table = []

    for model in models:
        for batch in batches:
            for dev in devices:
                print(f"Benchmarking {model.name} (B={batch}) on {dev.key} ({dev.label})...")
                run = run_latency_measurement(
                    session=session,
                    bench_session_id=bench_sess.id,
                    model=model,
                    device=dev,
                    batch=batch,
                    warmup_runs=WARMUP_RUNS,
                    timed_runs=TIMED_RUNS,
                )
                results_table.append({
                    "model": model.name,
                    "batch": batch,
                    "device": dev.key,
                    "median_ms": run.median_ms,
                    "p10_ms": run.p10_ms,
                    "p90_ms": run.p90_ms,
                    "ci_rel": run.ci_rel,
                    "first_run_ms": run.first_run_ms,
                    "unstable": run.unstable,
                })
                time.sleep(0.5)

    bench_sess.status = "done"
    bench_sess.finished_at = datetime.now(timezone.utc).isoformat()
    session.add(bench_sess)
    session.commit()

    print("\nEXTENDED BENCHMARK RESULTS:")
    print(f"{'Model':<16} {'B':<3} {'Device':<8} {'Median (ms)':<12} {'P10-P90':<14} {'CI rel':<8} {'First Run':<10}")
    print("-" * 75)
    for r in results_table:
        print(f"{r['model']:<16} {r['batch']:<3} {r['device']:<8} {r['median_ms']:<12.3f} {r['p10_ms']:.2f}-{r['p90_ms']:.2f} ms   {r['ci_rel'] or 0:.3f}    {r['first_run_ms'] or 0:.3f} ms")


def step3_idle_gap_wake_test(session: Session):
    print("\n" + "=" * 80)
    print("STEP 3: IDLE-GAP GPU WAKE TEST (0.5s, 2s, 10s, 30s) ON NVIDIA RTX 5070")
    print("=" * 80)

    # Use mlp-1024w-4l, batch 1 on dml:1
    model = session.exec(select(AIModel).where(AIModel.name.like("mlp-1024%"))).first()
    dev = session.exec(select(Device).where(Device.key == "dml:1")).first()
    assert model is not None and dev is not None

    gaps = [0.5, 2.0, 10.0, 30.0]

    # Create session once
    dml_opts = json.loads(dev.provider_options_json) if dev.provider_options_json else {}
    sess = make_session(model.path, dev.provider, dml_opts.get("device_id", 1))

    from app.benchmark import prepare_input_tensor
    inp_name, inp_data = prepare_input_tensor(model, 1, sess)

    # Sustained warmup to make sure it's active initially
    for _ in range(50):
        sess.run(None, {inp_name: inp_data})

    # Measure active steady-state median latency
    steady_times = []
    for _ in range(20):
        t0 = time.perf_counter()
        sess.run(None, {inp_name: inp_data})
        steady_times.append((time.perf_counter() - t0) * 1000.0)
    steady_med = float(np.median(steady_times))
    print(f"Warm active GPU steady-state latency: {steady_med:.3f} ms")

    wake_results = []
    for gap in gaps:
        print(f"\nWaiting {gap} seconds idle gap...")
        time.sleep(gap)

        # Read pre-inference hardware state
        m_before = nvml_reader.read_metrics()
        pstate_before = m_before.get("gpu_pstate")
        clock_before = m_before.get("gpu_clock_sm_mhz")
        power_before = m_before.get("gpu_power_w")

        # Time single first inference
        t0 = time.perf_counter()
        sess.run(None, {inp_name: inp_data})
        t_first = (time.perf_counter() - t0) * 1000.0

        # Read post-inference hardware state
        m_after = nvml_reader.read_metrics()
        pstate_after = m_after.get("gpu_pstate")
        clock_after = m_after.get("gpu_clock_sm_mhz")

        penalty_ms = t_first - steady_med

        wake_results.append({
            "gap_s": gap,
            "pstate_before": pstate_before,
            "clock_before_mhz": clock_before,
            "power_before_w": power_before,
            "first_run_ms": round(t_first, 3),
            "pstate_after": pstate_after,
            "clock_after_mhz": clock_after,
            "penalty_ms": round(penalty_ms, 3),
        })

        print(f"  Gap: {gap} s | Pre-P-state: P{pstate_before} ({clock_before} MHz, {power_before_w if (power_before_w:=power_before) else 0:.1f} W) | 1st Run: {t_first:.3f} ms | Penalty: +{penalty_ms:.3f} ms | Post-P-state: P{pstate_after}")

    print("\nIDLE-GAP WAKE TEST SUMMARY:")
    print(f"{'Idle Gap (s)':<14} {'Pre P-state':<12} {'Pre Clock':<12} {'1st Run (ms)':<14} {'Steady (ms)':<12} {'Wake Penalty':<14}")
    print("-" * 80)
    for r in wake_results:
        print(f"{r['gap_s']:<14.1f} P{r['pstate_before']:<11} {r['clock_before_mhz'] or 0:<12} {r['first_run_ms']:<14.3f} {steady_med:<12.3f} +{r['penalty_ms']:<13.3f} ms")


def step4_refit_and_crossovers(session: Session):
    print("\n" + "=" * 80)
    print("STEP 4: REFITTING HARDWARE PREDICTORS ON CLEAN DATA ONLY")
    print("=" * 80)

    devices = session.exec(select(Device).where(Device.is_available == True).order_by(Device.id)).all()

    fits = {}
    for dev in devices:
        print(f"Fitting hardware predictor for {dev.key} ({dev.label})...")
        fit = fit_device(session, dev.id, target="latency")
        fits[dev.key] = fit
        notes_parsed = json.loads(fit.notes) if fit.notes else {}
        cis = notes_parsed.get("parameter_cis", {})

        print(f"  Form:        {fit.model_form}")
        print(f"  LOO MAPE:    {fit.loo_mape_pct:.2f}%")
        print(f"  R^2 (log):   {fit.r2_log:.4f}")
        print(f"  t0:          {fit.t0_ms:.4f} ms")
        if "t0_ms" in cis:
            c = cis["t0_ms"]
            print(f"    -> 95% CI: [{c['ci_low']:.4f}, {c['ci_high']:.4f}] ms (rel ±{c['rel_half_width']*100:.1f}%, {c['status']})")
        if fit.compute_gflops:
            print(f"  Compute:     {fit.compute_gflops:.1f} GFLOP/s")
            if "compute_gflops" in cis:
                c = cis["compute_gflops"]
                print(f"    -> 95% CI: [{c['ci_low']:.1f}, {c['ci_high']:.1f}] GFLOP/s (rel ±{c['rel_half_width']*100:.1f}%, {c['status']})")
        if fit.bandwidth_gb_s:
            print(f"  Bandwidth:   {fit.bandwidth_gb_s:.1f} GB/s")
            if "bandwidth_gb_s" in cis:
                c = cis["bandwidth_gb_s"]
                print(f"    -> 95% CI: [{c['ci_low']:.1f}, {c['ci_high']:.1f}] GB/s (rel ±{c['rel_half_width']*100:.1f}%, {c['status']})")

    # Step 5: Fine-grid crossovers
    print("\n" + "=" * 80)
    print("STEP 5: FINE-GRID CROSSOVER ANALYSIS (250 EVALUATION POINTS)")
    print("=" * 80)

    cpu_dev = next(d for d in devices if d.key == "cpu")
    rtx_dev = next(d for d in devices if d.key == "dml:1")

    for family in ["mlp", "conv"]:
        for batch in [1, 8, 32]:
            cross = calculate_crossover(session, cpu_dev.id, rtx_dev.id, family=family, batch=batch)
            c = cross["crossover"]
            if c:
                print(f"[{family.upper()} B={batch}] Crossover: width/channels={c['width']} ({c['params']:,} params, {c['params']*4/(1024*1024):.2f} MB)")
                print(f"    CPU latency: {c['pred_a_ms']:.3f} ms vs RTX 5070: {c['pred_b_ms']:.3f} ms -> Switched to {c['switched_to']}")
            else:
                print(f"[{family.upper()} B={batch}] {cross['summary']}")


def main():
    init_db()
    with Session(engine) as session:
        models = step1_create_extended_models(session)
        step2_benchmark_extended_models(session, models)
        step3_idle_gap_wake_test(session)
        step4_refit_and_crossovers(session)
    print("\nPhase 4.1 execution complete.")


if __name__ == "__main__":
    main()
