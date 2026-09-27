"""Phase 3 automated verification script.

Executes:
1. Full NVML diagnostics table testing 8 functions.
2. Benchmark Session A (MLP 256 and 1024, batches 1 and 8 on CPU, dml:0, dml:1).
3. 60-second cooldown timer.
4. Benchmark Session B (identical configuration).
5. Reproducibility & stability comparison table.
6. 10 consecutive telemetry samples from the live sampler.
"""

from datetime import datetime, timezone
import json
import os
import sys
import time

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath("."))

from sqlmodel import Session, select
import pynvml

from app.benchmark import execute_latency_job
from app.config import TIMED_RUNS, WARMUP_RUNS
from app.db import AIModel, BenchSession, Device, Run, engine
from app.power import BatteryReader, NVMLReader
from app.telemetry import sample_telemetry


def run_nvml_diagnostics():
    print("=" * 80)
    print("PART 1: NVML 8-FUNCTION DIAGNOSTICS TABLE (Standard User Process)")
    print("=" * 80)

    try:
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            print("No NVIDIA devices detected by NVML.")
            return
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    except Exception as exc:
        print(f"Failed to initialize NVML: {exc}")
        return

    funcs = [
        ("nvmlDeviceGetName", lambda: pynvml.nvmlDeviceGetName(handle)),
        ("nvmlDeviceGetPowerUsage", lambda: f"{pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0:.3f} W"),
        ("nvmlDeviceGetTemperature", lambda: f"{pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)} °C"),
        ("nvmlDeviceGetUtilizationRates", lambda: f"GPU: {pynvml.nvmlDeviceGetUtilizationRates(handle).gpu}%, Mem: {pynvml.nvmlDeviceGetUtilizationRates(handle).memory}%"),
        ("nvmlDeviceGetMemoryInfo", lambda: f"Used: {pynvml.nvmlDeviceGetMemoryInfo(handle).used / 1e6:.1f} MB, Total: {pynvml.nvmlDeviceGetMemoryInfo(handle).total / 1e6:.1f} MB"),
        ("nvmlDeviceGetPerformanceState", lambda: f"P{pynvml.nvmlDeviceGetPerformanceState(handle)}"),
        ("nvmlDeviceGetClockInfo(NVML_CLOCK_SM)", lambda: f"{pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_SM)} MHz"),
        ("nvmlDeviceGetTotalEnergyConsumption", lambda: f"{pynvml.nvmlDeviceGetTotalEnergyConsumption(handle)} mJ"),
    ]

    print(f"{'Function':<38} | {'Status':<10} | {'Output / Return Value'}")
    print("-" * 80)
    for fname, fn in funcs:
        try:
            val = fn()
            status = "OK"
            out = str(val)
        except Exception as exc:
            status = "FAILED"
            out = f"{type(exc).__name__}: {exc}"
        print(f"{fname:<38} | {status:<10} | {out}")
    print()


def run_benchmark_session(name: str) -> int:
    print("=" * 80)
    print(f"RUNNING: {name}")
    print("=" * 80)
    now_iso = datetime.now(timezone.utc).isoformat()
    with Session(engine) as session:
        # Models 8 (mlp-256w-4l) and 9 (mlp-1024w-4l)
        # Devices 1 (cpu), 2 (dml:0 AMD 610M), 3 (dml:1 NVIDIA RTX 5070)
        m_ids = [8, 9]
        d_ids = [1, 2, 3]
        batches = [1, 8]

        sess = BenchSession(
            kind="latency",
            status="queued",
            config_json=json.dumps({"model_ids": m_ids, "device_ids": d_ids, "batches": batches}),
            created_at=now_iso,
            notes=name,
        )
        session.add(sess)
        session.commit()
        session.refresh(sess)
        sess_id = sess.id

    progress = {"done": 0, "total": 0, "item": "Starting"}
    execute_latency_job(
        bench_session_id=sess_id,
        model_ids=m_ids,
        device_ids=d_ids,
        batches=batches,
        warmup_runs=WARMUP_RUNS,
        timed_runs=TIMED_RUNS,
        progress_state=progress,
    )
    print(f"Completed {name} -> BenchSession ID = {sess_id}\n")
    return sess_id


def format_comparison_row(ra: Run, rb: Run, model_name: str, batch_val: int, dev_key: str) -> str:
    """Format side-by-side comparison row showing separate per-session stability flags."""
    med_a = ra.median_ms
    med_b = rb.median_ms
    diff_pct = abs(med_b - med_a) / med_a * 100.0 if med_a > 0 else 0.0

    unstable_a_str = "YES" if ra.unstable else "No"
    unstable_b_str = "YES" if rb.unstable else "No"
    nv_info = "-"
    if ra.nvml_clock_sm_start_mhz is not None or rb.nvml_clock_sm_start_mhz is not None:
        nv_info = f"A:{ra.nvml_clock_sm_start_mhz}->{ra.nvml_clock_sm_end_mhz} | B:{rb.nvml_clock_sm_start_mhz}->{rb.nvml_clock_sm_end_mhz}"

    return (
        f"{model_name:<14} | {batch_val:<5} | {dev_key:<8} | "
        f"{ra.first_run_ms:<9.3f} | {med_a:<8.3f} | {ra.ci_rel:<8.4f} | {unstable_a_str:<10} | "
        f"{rb.first_run_ms:<9.3f} | {med_b:<8.3f} | {rb.ci_rel:<8.4f} | {unstable_b_str:<10} | "
        f"{diff_pct:<6.2f}% | {nv_info}"
    )


def print_comparison_table(sess_a_id: int, sess_b_id: int):
    print("=" * 125)
    print(f"PART 2: REPRODUCIBILITY & STABILITY COMPARISON (Session {sess_a_id} vs Session {sess_b_id}, 60s apart)")
    print("=" * 125)

    with Session(engine) as session:
        runs_a = session.exec(select(Run).where(Run.session_id == sess_a_id)).all()
        runs_b = session.exec(select(Run).where(Run.session_id == sess_b_id)).all()
        dev_map = {d.id: d for d in session.exec(select(Device)).all()}
        mod_map = {m.id: m for m in session.exec(select(AIModel)).all()}

    map_a = {(r.ai_model_id, r.device_id, r.batch): r for r in runs_a}
    map_b = {(r.ai_model_id, r.device_id, r.batch): r for r in runs_b}

    headers = (
        f"{'Model':<14} | {'Batch':<5} | {'Device':<8} | "
        f"{'1stRun A':<9} | {'Med A':<8} | {'CI_rel A':<8} | {'Unstable A':<10} | "
        f"{'1stRun B':<9} | {'Med B':<8} | {'CI_rel B':<8} | {'Unstable B':<10} | "
        f"{'% Diff':<7} | {'NV Clocks (MHz)'}"
    )
    print(headers)
    print("-" * 125)

    all_keys = sorted(list(set(map_a.keys()) | set(map_b.keys())))
    for k in all_keys:
        ra = map_a.get(k)
        rb = map_b.get(k)
        if not ra or not rb:
            continue

        model_name = mod_map[ra.ai_model_id].name.replace("w-4l", "")
        batch_val = ra.batch
        dev_key = dev_map[ra.device_id].key
        print(format_comparison_row(ra, rb, model_name, batch_val, dev_key))
    print()



def print_live_telemetry_samples():
    print("=" * 90)
    print("PART 3: 10 CONSECUTIVE LIVE TELEMETRY SAMPLES (1 Hz)")
    print("=" * 90)
    batt_reader = BatteryReader()
    samples = []
    print("Sampling live hardware state...")
    for i in range(10):
        s = sample_telemetry(batt_reader)
        samples.append(s)
        time.sleep(1.0)

    header = (
        f"{'Timestamp':<25} | {'CPU%':<6} | {'RAM%':<6} | {'Batt%':<6} | "
        f"{'Plugged':<7} | {'Discharge(W)':<12} | {'GPU%':<6} | {'GPU(W)':<7} | {'GPU(°C)':<7}"
    )
    print(header)
    print("-" * 90)
    for s in samples:
        ts = s['ts'][:19]
        cpu_p = f"{s['cpu_pct']:.1f}"
        ram_p = f"{s['ram_pct']:.1f}"
        batt_p = f"{s['battery_pct']:.0f}%" if s['battery_pct'] is not None else "N/A"
        plug = str(s['plugged_in'])
        dw = f"{s['discharge_w']:.2f} W" if s['discharge_w'] is not None else "0 W (AC)"
        g_util = f"{s['gpu_util_pct']:.0f}%" if s['gpu_util_pct'] is not None else "N/A"
        g_pow = f"{s['gpu_power_w']:.2f} W" if s['gpu_power_w'] is not None else "N/A"
        g_temp = f"{s['gpu_temp_c']:.0f} °C" if s['gpu_temp_c'] is not None else "N/A"

        print(f"{ts:<25} | {cpu_p:<6} | {ram_p:<6} | {batt_p:<6} | {plug:<7} | {dw:<12} | {g_util:<6} | {g_pow:<7} | {g_temp:<7}")
    print()


if __name__ == "__main__":
    run_nvml_diagnostics()
    sess_a = run_benchmark_session("Phase 3 Gate - Benchmark Session A")
    print("Pausing 60 seconds between sessions to assess thermal/power state repeatability...")
    for remaining in range(60, 0, -10):
        print(f"  Cooldown countdown: {remaining}s remaining...")
        time.sleep(10)
    print("Cooldown complete.\n")
    sess_b = run_benchmark_session("Phase 3 Gate - Benchmark Session B")
    print_comparison_table(sess_a, sess_b)
    print_live_telemetry_samples()
    print("=" * 80)
    print("Phase 3 Gate Verification Run Complete.")
    print("=" * 80)
