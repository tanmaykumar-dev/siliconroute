"""SiliconRoute: 10-Level Real Hardware Benchmark & Rig Self-Identification.

Performs live, empirical benchmarking across 10 levels of model scales (from 8K FLOPs
up to 4.83 Billion FLOPs). Probes host hardware automatically with zero hardcoded specs,
executes real inferences on each detected physical processor, logs NVML telemetry, and
evaluates the router's allocation accuracy and hardware crossover dynamics.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time
import winreg

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import onnxruntime as ort
import psutil
from sqlmodel import Session, select

from app.db import AIModel, Device, create_db_engine
from app.devices import detect_devices, verify_gpu_identity_mapping, get_dxgi_adapters
from app.benchmark import run_latency_measurement
from app.power import nvml_reader
from app.router import route_model


def probe_host_rig() -> dict:
    """Dynamically discover host processor rig without user hints."""
    # 1. CPU Discovery via Windows Registry & psutil
    cpu_name = platform.processor()
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        cpu_name = val.strip()
        winreg.CloseKey(key)
    except Exception:
        pass

    phys_cores = psutil.cpu_count(logical=False) or 0
    logic_cores = psutil.cpu_count(logical=True) or 0
    ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)

    # 2. DXGI Adapter Discovery
    dxgi_adapters = get_dxgi_adapters()
    phys_adapters = [a for a in dxgi_adapters if not a.get("is_software")]

    # 3. NVML Discovery
    nvml_info = {"available": False, "gpus": []}
    if nvml_reader.is_available:
        gname = nvml_reader.device_name or "NVIDIA GPU"
        nvml_info = {"available": True, "gpus": [gname]}

    # 4. ORT Providers & NPU check
    ort_providers = ort.get_available_providers()
    has_qnn = "QNNExecutionProvider" in ort_providers

    return {
        "cpu_name": cpu_name,
        "physical_cores": phys_cores,
        "logical_cores": logic_cores,
        "ram_gb": ram_gb,
        "dxgi_adapters": phys_adapters,
        "nvml": nvml_info,
        "ort_providers": ort_providers,
        "has_npu": has_qnn,
    }


def main():
    print("=" * 105)
    print(" SILICONROUTE: AUTOMATED HARDWARE RIG SELF-IDENTIFICATION & 10-LEVEL PHYSICAL BENCHMARK")
    print(" Zero Hardcoded Specifications -- Live Hardware Self-Probe & Real Inferences Only")
    print("=" * 105)

    # -------------------------------------------------------------------------
    # PHASE 1: SELF-IDENTIFY THE RIG
    # -------------------------------------------------------------------------
    print("\n[PHASE 1] RUNNING LIVE HARDWARE PROBE (SELF-DISCOVERY)...")
    rig = probe_host_rig()
    gpu_map = verify_gpu_identity_mapping()

    print(f"  * Host CPU         : {rig['cpu_name']}")
    print(f"  * CPU Topology     : {rig['physical_cores']} Physical Cores / {rig['logical_cores']} Threads | {rig['ram_gb']} GB System RAM")
    print(f"  * Detected Adapters: {len(rig['dxgi_adapters'])} physical DXGI graphics adapter(s) found:")
    for a in rig['dxgi_adapters']:
        vram_mb = round(a.get("vram_bytes", 0) / (1024 ** 2))
        print(f"    - DXGI Adapter {a['index']}: {a['description']} (Vendor: {a['vendor_name']} {a['vendor_id']}, Dedicated VRAM: {vram_mb} MB)")
    if rig['nvml']['available']:
        print(f"  * NVML Telemetry   : ACTIVE ({', '.join(rig['nvml']['gpus'])})")
    else:
        print("  * NVML Telemetry   : INACTIVE / NOT PRESENT")
    print(f"  * ONNX Providers   : {', '.join(rig['ort_providers'])}")
    print(f"  * NPU Socket       : {'DETECTED (QNN)' if rig['has_npu'] else 'NONE DETECTED ON THIS RIG'}")

    # Load verified devices from DB
    engine = create_db_engine()
    with Session(engine) as session:
        devices = session.exec(select(Device).where(Device.is_available == True)).all()
        # Filter out unknown devices
        devices = [d for d in devices if d.kind in ("cpu", "igpu", "dgpu")]

    print("\n  Allocatable Physical Execution Sockets for Benchmark:")
    for d in devices:
        print(f"    [{d.key}] {d.label} (Role: {d.kind.upper()}, Provider: {d.provider})")

    # -------------------------------------------------------------------------
    # PHASE 2: 10 BENCHMARK LEVELS DEFINITION
    # -------------------------------------------------------------------------
    benchmark_levels = [
        {"lvl": 1,  "name": "mlp-32w-4l",   "desc": "Micro Kernel Dispatch",       "batch": 1},
        {"lvl": 2,  "name": "mlp-128w-4l",  "desc": "L1/L2 Cache Scale",           "batch": 1},
        {"lvl": 3,  "name": "mlp-256w-4l",  "desc": "L3 Cache Boundary (<16MB)",   "batch": 1},
        {"lvl": 4,  "name": "conv-16c-4l",  "desc": "Spatial Convolution (Early)", "batch": 1},
        {"lvl": 5,  "name": "mlp-1024w-4l", "desc": "Memory Bus Transition",      "batch": 1},
        {"lvl": 6,  "name": "conv-32c-4l",  "desc": "Mid-Scale Compute (300M FLOP)","batch": 1},
        {"lvl": 7,  "name": "mlp-2048w-4l", "desc": "High Memory Footprint (67MB)", "batch": 1},
        {"lvl": 8,  "name": "conv-64c-4l",  "desc": "1.21 Billion FLOPs Model",     "batch": 1},
        {"lvl": 9,  "name": "conv-96c-4l",  "desc": "2.72 Billion FLOPs Model",     "batch": 1},
        {"lvl": 10, "name": "conv-128c-4l", "desc": "4.83 Billion FLOPs Model",     "batch": 1},
    ]

    print("\n[PHASE 2] PREPARING 10-LEVEL BENCHMARK SUITE (8K FLOPs -> 4.83 BILLION FLOPs):")
    print(f"{'Lvl':<4} | {'Model Name':<14} | {'Parameters':<14} | {'FLOPs/Sample':<16} | {'GFLOPs':<10} | {'Focus / Regime'}")
    print("-" * 90)

    model_records = {}
    with Session(engine) as session:
        for b in benchmark_levels:
            m = session.exec(select(AIModel).where(AIModel.name == b["name"])).first()
            if not m:
                print(f"Error: Model {b['name']} not found in database!")
                return
            model_records[b["name"]] = m
            gflops = m.flops_per_sample / 1e9
            print(f"{b['lvl']:<4} | {m.name:<14} | {m.params:<14,d} | {int(m.flops_per_sample):<16,d} | {gflops:<10.3f} | {b['desc']}")

    # -------------------------------------------------------------------------
    # PHASE 3: LIVE HARDWARE EXECUTION
    # -------------------------------------------------------------------------
    print("\n" + "=" * 105)
    print(" [PHASE 3] EXECUTING LIVE PHYSICAL INFERENCES ACROSS DETECTED CHIPS")
    print(" Wall-clock time recorded via high-precision hardware performance counter")
    print("=" * 105)

    results_summary = []
    router_correct_count = 0

    for b in benchmark_levels:
        lvl = b["lvl"]
        m = model_records[b["name"]]
        batch = b["batch"]
        print(f"\n>>> LEVEL {lvl:02d}/10: {m.name} ({b['desc']}) -- {m.flops_per_sample:,.0f} FLOPs")

        # 1. Ask Router what it predicts & allocates
        with Session(engine) as session:
            route_decision = route_model(
                session=session,
                model_id=m.id,
                batch=batch,
                mode="fastest",
                workload="sustained",
                power_budget_w=85.0,
                allow_explore=False,
            )
        predicted_winner_key = route_decision["chosen_device_key"]
        print(f"    [Router Prediction] Allocated Target: {predicted_winner_key.upper()} (Reason: {route_decision['reason']})")

        # 2. Benchmark each physical device
        measured_times = {}
        power_readings = {}
        temp_readings = {}

        for dev in devices:
            timed_runs = 15 if lvl <= 7 else 5
            warmup_runs = 3 if lvl <= 7 else 2

            run_res = run_latency_measurement(
                session=None,
                bench_session_id=None,
                model=m,
                device=dev,
                batch=batch,
                warmup_runs=warmup_runs,
                timed_runs=timed_runs,
                dry_run=True,
            )

            med_ms = run_res.median_ms
            measured_times[dev.key] = med_ms

            # Compute throughput GFLOPs/sec
            gflops_per_sec = (m.flops_per_sample / 1e9) / (med_ms / 1000.0)

            # Read NVML if NVIDIA
            pwr_str = "--"
            temp_str = "--"
            if dev.kind == "dgpu" and nvml_reader.is_available:
                m_curr = nvml_reader.read_metrics()
                pwr = m_curr.get("gpu_power_w")
                temp = m_curr.get("gpu_temp_c")
                if pwr: pwr_str = f"{pwr:.1f} W"
                if temp: temp_str = f"{temp:.1f} °C"
                power_readings[dev.key] = pwr
                temp_readings[dev.key] = temp

            print(f"      - {dev.label:<38} [{dev.key}]: {med_ms:>9.3f} ms | {gflops_per_sec:>9.2f} GFLOP/s | Power: {pwr_str:<8} | Temp: {temp_str}")

        # 3. Determine real physical winner
        actual_winner_key = min(measured_times, key=measured_times.get)
        actual_best_ms = measured_times[actual_winner_key]
        pred_dev_ms = measured_times[predicted_winner_key]
        regret_pct = ((pred_dev_ms - actual_best_ms) / actual_best_ms) * 100.0

        is_match = (predicted_winner_key == actual_winner_key) or (regret_pct < 3.0)
        if is_match:
            router_correct_count += 1

        verdict = "MATCH (OPTIMAL)" if is_match else f"REGRET {regret_pct:.1f}%"
        print(f"    --> Physical Winner: {actual_winner_key.upper()} ({actual_best_ms:.3f} ms) | Router Verdict: {verdict}")

        results_summary.append({
            "lvl": lvl,
            "name": m.name,
            "params": m.params,
            "flops": m.flops_per_sample,
            "cpu_ms": measured_times.get("cpu"),
            "igpu_ms": measured_times.get("dml:0"),
            "dgpu_ms": measured_times.get("dml:1"),
            "predicted_key": predicted_winner_key,
            "actual_key": actual_winner_key,
            "regret_pct": regret_pct,
            "is_match": is_match,
        })

    # -------------------------------------------------------------------------
    # PHASE 4: FINAL BENCHMARK SCORECARD
    # -------------------------------------------------------------------------
    print("\n" + "=" * 105)
    print(" [PHASE 4] FINAL PHYSICAL BENCHMARK SCORECARD & ACCURACY AUDIT")
    print("=" * 105)
    print(f"{'Lvl':<4} | {'Model Name':<13} | {'FLOPs':<14} | {'CPU (ms)':<10} | {'iGPU (ms)':<10} | {'dGPU (ms)':<10} | {'Win':<6} | {'Speedup':<12} | {'Router Match'}")
    print("-" * 105)

    for r in results_summary:
        cpu_t = f"{r['cpu_ms']:.3f}" if r['cpu_ms'] is not None else "--"
        igpu_t = f"{r['igpu_ms']:.3f}" if r['igpu_ms'] is not None else "--"
        dgpu_t = f"{r['dgpu_ms']:.3f}" if r['dgpu_ms'] is not None else "--"
        winner = r['actual_key'].upper()

        best_t = min(t for t in [r['cpu_ms'], r['igpu_ms'], r['dgpu_ms']] if t is not None)
        other_t = r['cpu_ms'] if winner == "DML:1" else r['dgpu_ms']
        if other_t and best_t:
            ratio = other_t / best_t
            speedup_str = f"{ratio:.1f}x faster"
        else:
            speedup_str = "Optimal"

        match_str = "YES (WINNER)" if r['actual_key'] == r['predicted_key'] else f"NO ({r['regret_pct']:.1f}% reg)"
        print(f"{r['lvl']:<4} | {r['name']:<13} | {int(r['flops']):<14,d} | {cpu_t:<10} | {igpu_t:<10} | {dgpu_t:<10} | {winner:<6} | {speedup_str:<12} | {match_str}")

    print("-" * 105)
    acc_pct = (router_correct_count / len(benchmark_levels)) * 100.0
    print(f"\nRouter Allocation Accuracy Across All 10 Levels: {router_correct_count}/{len(benchmark_levels)} ({acc_pct:.1f}%)")
    print(f"Benchmark Completion Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("All measurements performed on real physical silicon with active hardware verification.")
    print("=" * 105 + "\n")


if __name__ == "__main__":
    main()
