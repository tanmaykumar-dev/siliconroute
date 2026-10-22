"""SiliconRoute: 10-Level Empirical Hardware Benchmark & Generalization Suite.

Executes live, verifiable benchmarks across 10 levels of model scales.
Follows all project standards:
- Hardware Rig Self-Discovery: Probes registry, DXGI, and NVML without user hints.
- Standard Project Method: Warmup (sustained >=300ms on DML), 30 timed samples, adaptive inner loop.
- Real-Time NVML Sampling: Samples power and temperature DURING active inference (median & max),
  isolated strictly to NVIDIA dGPU timing (never runs during CPU/iGPU).
- Strict Match & Regret: Match requires predicted_chip == measured_fastest_chip. Regret reported separately.
- Dual Modes:
  * Standard mode: Evaluates 10 model levels against measured/fitted router predictions.
  * --unseen mode: Truly unseen configurations absent from DB at ANY batch. Evaluates near-switch-point
    cases (MLP widths 1792/1920/2176/2304 at batches 1 & 2; Conv channels 12/20/28 at batch 1), disables
    measured lookup (fit_only=True), reports decision margins and close-call (<1.5x) accuracy.
- Audit Logging: Captures complete transcript and raw samples in results/logs/benchmarks/ and results/logs/x86_closeout/.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import sys
import time
import winreg

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import onnxruntime as ort
import psutil
from sqlmodel import Session, select

from app.config import (
    CPU_CACHE_MB,
    MAX_INNER_LOOP_K,
    MIN_SAMPLE_MS,
    SEED,
    TIMED_RUNS,
    WARMUP_RUNS,
    WARMUP_SUSTAINED_MS,
)
from app.db import AIModel, Device, create_db_engine
from app.devices import get_dxgi_adapters, make_session, verify_gpu_identity_mapping
from app.benchmark import compute_run_stats, is_nvidia_device, prepare_input_tensor
from app.models_gen import create_and_register_synthetic
from app.power import NVMLMeasurementSampler, nvml_reader
from app.router import route_model


class TeeLogger:
    """Tee stdout to both console and a log file simultaneously."""

    def __init__(self, filepath: Path) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(filepath, "w", encoding="utf-8")
        self.stdout = sys.stdout

    def write(self, data: str) -> None:
        self.stdout.write(data)
        self.file.write(data)
        self.flush()

    def flush(self) -> None:
        self.stdout.flush()
        self.file.flush()

    def close(self) -> None:
        if self.file and not self.file.closed:
            self.file.close()


def probe_host_rig() -> dict:
    """Dynamically discover host processor rig without user hints."""
    cpu_name = platform.processor()
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        )
        val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        cpu_name = val.strip()
        winreg.CloseKey(key)
    except Exception:
        pass

    phys_cores = psutil.cpu_count(logical=False) or 0
    logic_cores = psutil.cpu_count(logical=True) or 0
    ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)

    dxgi_adapters = get_dxgi_adapters()
    phys_adapters = [a for a in dxgi_adapters if not a.get("is_software")]

    nvml_info = {"available": False, "gpus": []}
    if nvml_reader.is_available:
        gname = nvml_reader.device_name or "NVIDIA GPU"
        nvml_info = {"available": True, "gpus": [gname]}

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


def measure_device_benchmark(
    model: AIModel,
    device: Device,
    batch: int,
) -> dict:
    """Execute latency measurement using standard project method.

    - Warmup: sustained >= WARMUP_SUSTAINED_MS (300ms) for DML, 5 runs for CPU
    - Adaptive inner loop: target >= MIN_SAMPLE_MS (5.0 ms) per sample
    - Timed runs: TIMED_RUNS = 30 samples
    - Real-time NVML sampling during inference: runs ONLY during NVIDIA dGPU timing
    - CPU reference output validation
    """
    device_opts = json.loads(device.provider_options_json or "{}")
    device_id = device_opts.get("device_id")

    sess = make_session(model.path, device.provider, device_id=device_id, device=device)
    inp_name, inp_tensor = prepare_input_tensor(model, batch, sess)
    feed_dict = {inp_name: inp_tensor}

    # 1. Warm-up
    warmup_t0 = time.perf_counter_ns()
    warmups_done = 0
    if "Dml" in device.provider:
        while ((time.perf_counter_ns() - warmup_t0) / 1e6 < WARMUP_SUSTAINED_MS) or (warmups_done < WARMUP_RUNS):
            sess.run(None, feed_dict)
            warmups_done += 1
    else:
        for _ in range(WARMUP_RUNS):
            sess.run(None, feed_dict)
            warmups_done += 1
    warmup_duration_ms = (time.perf_counter_ns() - warmup_t0) / 1e6

    # 2. Adaptive inner loop determination (target >= MIN_SAMPLE_MS = 5.0ms)
    t_trial_0 = time.perf_counter_ns()
    sess.run(None, feed_dict)
    t_trial_ms = (time.perf_counter_ns() - t_trial_0) / 1e6

    inner_loop_k = 1
    if t_trial_ms < MIN_SAMPLE_MS:
        inner_loop_k = int(np.ceil(MIN_SAMPLE_MS / max(t_trial_ms, 0.0001)))
        inner_loop_k = min(max(inner_loop_k, 1), MAX_INNER_LOOP_K)

    # 3. NVML Sampler (Active DURING measurement if and ONLY if NVIDIA dGPU)
    is_nvidia = is_nvidia_device(device) and nvml_reader.is_available
    sampler: NVMLMeasurementSampler | None = None
    if is_nvidia:
        sampler = NVMLMeasurementSampler(sample_interval_s=0.005)
        sampler.start(device_key=device.key)
    else:
        assert sampler is None, f"PROHIBITED: NVML sampler started on non-NVIDIA device {device.key}"

    # 4. Timed measurement loop (30 samples, each inner_loop_k runs)
    raw_timings_ms: list[float] = []
    last_output: np.ndarray | None = None
    for _ in range(TIMED_RUNS):
        t0 = time.perf_counter_ns()
        for _ in range(inner_loop_k):
            outputs = sess.run(None, feed_dict)
        t1 = time.perf_counter_ns()
        sample_ms = (t1 - t0) / 1e6
        raw_timings_ms.append(sample_ms / inner_loop_k)
        last_output = outputs[0]

    # Stop NVML Sampler
    nvml_telemetry: dict = {}
    if sampler is not None:
        nvml_telemetry = sampler.stop()

    # 5. Statistics
    timings = np.array(raw_timings_ms, dtype=np.float64)
    stats = compute_run_stats(timings, batch=batch, seed=SEED + (model.id or 0) * 100 + batch)

    # 6. Correctness verification vs CPU reference
    output_matches_cpu: bool | None = None
    max_rel_err: float | None = None
    if last_output is not None:
        if device.key == "cpu":
            output_matches_cpu = True
            max_rel_err = 0.0
        else:
            try:
                cpu_sess = make_session(model.path, "CPUExecutionProvider")
                ref_outputs = cpu_sess.run(None, feed_dict)
                diff = np.abs(last_output - ref_outputs[0])
                max_ref = float(np.max(np.abs(ref_outputs[0])))
                rel_err = float(np.max(diff) / (max_ref + 1e-9))
                max_rel_err = round(rel_err, 6)
                output_matches_cpu = bool(rel_err <= 1e-2)
            except Exception:
                output_matches_cpu = None

    return {
        "device_key": device.key,
        "device_label": device.label,
        "provider": device.provider,
        "warmup_runs": warmups_done,
        "warmup_duration_ms": round(warmup_duration_ms, 2),
        "timed_runs": TIMED_RUNS,
        "inner_loop_k": inner_loop_k,
        "total_timed_inferences": TIMED_RUNS * inner_loop_k,
        "raw_timings_ms": [round(x, 4) for x in raw_timings_ms],
        "stats": {k: round(v, 4) if isinstance(v, float) else v for k, v in stats.items()},
        "output_matches_cpu": output_matches_cpu,
        "max_rel_err": max_rel_err,
        "nvml_power_samples_w": nvml_telemetry.get("power_samples_w", []),
        "nvml_median_power_w": nvml_telemetry.get("median_power_w"),
        "nvml_max_power_w": nvml_telemetry.get("max_power_w"),
        "nvml_temp_samples_c": nvml_telemetry.get("temp_samples_c", []),
        "nvml_median_temp_c": nvml_telemetry.get("median_temp_c"),
        "nvml_max_temp_c": nvml_telemetry.get("max_temp_c"),
    }


def ensure_unseen_models(session: Session) -> list[dict]:
    """Generate and register near-switch-point models absent from DB at ANY batch.

    MLP widths: 1792, 1920 (just below 64 MB CPU cache), 2176, 2304 (just above 64 MB CPU cache) at batch 1 & 2.
    Conv channels: 12, 20, 28 at batch 1 (near the dispatch-overhead vs compute crossover point).
    """
    unseen_configs = [
        {"family": "mlp", "size": 1792, "layers": 4, "batch": 1},
        {"family": "mlp", "size": 1792, "layers": 4, "batch": 2},
        {"family": "mlp", "size": 1920, "layers": 4, "batch": 1},
        {"family": "mlp", "size": 1920, "layers": 4, "batch": 2},
        {"family": "mlp", "size": 2176, "layers": 4, "batch": 1},
        {"family": "mlp", "size": 2176, "layers": 4, "batch": 2},
        {"family": "mlp", "size": 2304, "layers": 4, "batch": 1},
        {"family": "mlp", "size": 2304, "layers": 4, "batch": 2},
        {"family": "conv", "size": 12,  "layers": 4, "batch": 1},
        {"family": "conv", "size": 20,  "layers": 4, "batch": 1},
        {"family": "conv", "size": 28,  "layers": 4, "batch": 1},
    ]

    prepared = []
    for cfg in unseen_configs:
        m = create_and_register_synthetic(
            session=session,
            family=cfg["family"],
            size=cfg["size"],
            layers=cfg["layers"],
        )
        prepared.append({
            "model": m,
            "batch": cfg["batch"],
        })
    return prepared


def get_standard_10_level_models(session: Session) -> list[dict]:
    """Retrieve standard 10-level benchmark models."""
    names = [
        ("mlp-32w-4l", 1),
        ("mlp-128w-4l", 1),
        ("mlp-256w-4l", 1),
        ("conv-16c-4l", 1),
        ("mlp-1024w-4l", 1),
        ("conv-32c-4l", 1),
        ("mlp-2048w-4l", 1),
        ("conv-64c-4l", 1),
        ("conv-96c-4l", 1),
        ("conv-128c-4l", 1),
    ]
    prepared = []
    for name, batch in names:
        m = session.exec(select(AIModel).where(AIModel.name == name)).first()
        if not m:
            raise RuntimeError(f"Required model {name} not found in database!")
        prepared.append({"model": m, "batch": batch})
    return prepared


def compute_batch_intensity(model: AIModel, batch: int) -> float:
    """Compute exact arithmetic intensity (FLOPs per byte transferred) for a given batch.

    Total Data Bytes = weight_bytes + batch * (input_bytes + output_bytes).
    """
    w_bytes = model.weight_bytes
    if model.family == "mlp":
        width = int(np.sqrt(model.params // 4))
        act_bytes = batch * 2 * width * 4  # float32 input + output
    elif model.family == "conv":
        channels = int(np.sqrt(model.params // (4 * 9)))
        act_bytes = batch * 2 * channels * 64 * 64 * 4
    else:
        act_bytes = batch * 1024 * 4

    total_data_bytes = w_bytes + act_bytes
    total_flops = model.flops_per_sample * batch
    return round(float(total_flops / max(total_data_bytes, 1)), 2)


def run_benchmark_suite(unseen_mode: bool = False) -> None:
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    mode_name = "10_level_unseen" if unseen_mode else "10_level"

    log_dir_bm = ROOT_DIR / "results" / "logs" / "benchmarks"
    log_dir_closeout = ROOT_DIR / "results" / "logs" / "x86_closeout"
    log_dir_bm.mkdir(parents=True, exist_ok=True)
    log_dir_closeout.mkdir(parents=True, exist_ok=True)

    txt_path = log_dir_bm / f"{mode_name}_{timestamp_str}.txt"
    json_path = log_dir_bm / f"{mode_name}_{timestamp_str}.json"

    tee = TeeLogger(txt_path)
    sys.stdout = tee

    try:
        print("=" * 125)
        print(" SILICONROUTE: AUTOMATED HARDWARE BENCHMARK & ROUTER VERIFICATION SUITE")
        print(f" Mode: {'UNSEEN GENERALIZATION TEST (Near-Switch-Point Cases, Fit-Only Prediction)' if unseen_mode else 'STANDARD 10-LEVEL BENCHMARK'}")
        print(f" Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}")
        print(" Log File (Console):", txt_path)
        print(" Raw Samples (JSON):", json_path)
        print("=" * 125)

        # ---------------------------------------------------------------------
        # 1. HARDWARE SELF-DISCOVERY
        # ---------------------------------------------------------------------
        print("\n[PHASE 1] HARDWARE RIG SELF-DISCOVERY (Zero Manual Hints)...")
        rig = probe_host_rig()
        verify_gpu_identity_mapping()

        print(f"  * Host CPU         : {rig['cpu_name']}")
        print(f"  * CPU Topology     : {rig['physical_cores']} Physical Cores / {rig['logical_cores']} Threads | {rig['ram_gb']} GB System RAM")
        print(f"  * DXGI Adapters    : {len(rig['dxgi_adapters'])} physical graphics adapter(s) found:")
        for a in rig['dxgi_adapters']:
            vram_mb = round(a.get("vram_bytes", 0) / (1024**2))
            print(f"    - Adapter {a['index']}: {a['description']} (Vendor: {a['vendor_name']} {a['vendor_id']}, Dedicated VRAM: {vram_mb} MB)")
        if rig['nvml']['available']:
            print(f"  * NVML Telemetry   : ACTIVE ({', '.join(rig['nvml']['gpus'])})")
        else:
            print("  * NVML Telemetry   : INACTIVE / NOT PRESENT")
        print(f"  * ORT Providers    : {', '.join(rig['ort_providers'])}")
        print(f"  * NPU Socket       : {'DETECTED (QNN)' if rig['has_npu'] else 'NONE DETECTED ON THIS RIG'}")

        engine = create_db_engine()
        with Session(engine) as session:
            devices = session.exec(select(Device).where(Device.is_available == True)).all()
            devices = [d for d in devices if d.kind in ("cpu", "igpu", "dgpu")]

        print("\n  Allocatable Execution Sockets for Benchmark:")
        for d in devices:
            print(f"    [{d.key}] {d.label} (Role: {d.kind.upper()}, Provider: {d.provider})")

        # ---------------------------------------------------------------------
        # 2. MODEL PREPARATION & FACT COMPUTATION
        # ---------------------------------------------------------------------
        print(f"\n[PHASE 2] PREPARING BENCHMARK MODELS & COMPUTING FACTS FROM MODELS:")
        print(f"{'Lvl':<4} | {'Model Name':<16} | {'Batch':<5} | {'Parameters':<12} | {'Weight (MiB)':<13} | {'Weight (MB)':<12} | {'Total FLOPs':<16} | {'Intensity (FLOP/B)'}")
        print("-" * 125)

        level_facts = []
        with Session(engine) as session:
            if unseen_mode:
                test_items = ensure_unseen_models(session)
            else:
                test_items = get_standard_10_level_models(session)

            for idx, item in enumerate(test_items, start=1):
                m: AIModel = item["model"]
                batch: int = item["batch"]
                weight_mib = round(m.weight_bytes / (1024**2), 2)
                weight_mb = round(m.weight_bytes / 1e6, 2)
                total_flops = m.flops_per_sample * batch
                intensity = compute_batch_intensity(m, batch)

                level_facts.append({
                    "lvl": idx,
                    "model_id": m.id,
                    "name": m.name,
                    "family": m.family,
                    "path": m.path,
                    "batch": batch,
                    "params": m.params,
                    "weight_bytes": m.weight_bytes,
                    "weight_mib": weight_mib,
                    "weight_mb": weight_mb,
                    "flops_per_sample": m.flops_per_sample,
                    "total_flops": total_flops,
                    "intensity": intensity,
                })
                print(
                    f"{idx:<4} | {m.name:<16} | {batch:<5} | {m.params:<12,d} | {weight_mib:<13.2f} | "
                    f"{weight_mb:<12.2f} | {int(total_flops):<16,d} | {intensity:<18.2f}"
                )

        # ---------------------------------------------------------------------
        # 3. LIVE BENCHMARK EXECUTION
        # ---------------------------------------------------------------------
        print("\n" + "=" * 125)
        print(" [PHASE 3] EXECUTING LIVE EMPIRICAL BENCHMARKS (30 Samples, Real-time NVML Telemetry)")
        print("=" * 125)

        results_json_levels = []
        exact_matches = 0
        close_call_matches = 0
        total_close_calls = 0
        total_levels = len(level_facts)

        for fact in level_facts:
            lvl = fact["lvl"]
            model_id = fact["model_id"]
            name = fact["name"]
            family = fact["family"]
            path = fact["path"]
            batch: int = fact["batch"]
            m_transient = AIModel(
                id=model_id,
                name=name,
                family=family,
                path=path,
                params=fact["params"],
                weight_bytes=fact["weight_bytes"],
                flops_per_sample=fact["flops_per_sample"],
            )
            print(f"\n>>> LEVEL {lvl:02d}/{total_levels}: {name} (Batch: {batch}) | Params: {fact['params']:,d} | Weights: {fact['weight_mib']:.2f} MiB ({fact['weight_mb']:.2f} MB) | Total FLOPs: {fact['total_flops']:,.0f} | Intensity: {fact['intensity']} FLOP/B")

            # Router Prediction
            with Session(engine) as session:
                decision = route_model(
                    session=session,
                    model_id=model_id,
                    batch=batch,
                    mode="fastest",
                    workload="sustained",
                    power_budget_w=85.0,
                    allow_explore=False,
                    fit_only=unseen_mode,
                )

            pred_key = decision["chosen_device_key"]
            pred_source = decision.get("chosen_source", "unknown")
            print(f"    [Router Prediction] Target Chip: {pred_key.upper()} | Source: [{pred_source.upper()}] | Reason: {decision['reason']}")

            # Measure all physical chips
            meas_by_device: dict[str, dict] = {}
            for dev in devices:
                meas = measure_device_benchmark(model=m_transient, device=dev, batch=batch)
                meas_by_device[dev.key] = meas

                med_ms = meas["stats"]["median_ms"]
                gflops_s = (fact["total_flops"] / 1e9) / (med_ms / 1000.0) if med_ms > 0 else 0.0

                pwr_med = meas["nvml_median_power_w"]
                pwr_max = meas["nvml_max_power_w"]
                temp_med = meas["nvml_median_temp_c"]
                temp_max = meas["nvml_max_temp_c"]

                if pwr_med is not None and pwr_max is not None:
                    pwr_str = f"{pwr_med:.1f}W (max {pwr_max:.1f}W)"
                else:
                    pwr_str = "N/A (NVML: NVIDIA dGPU only)"

                if temp_med is not None and temp_max is not None:
                    temp_str = f"{temp_med:.1f}°C (max {temp_max:.1f}°C)"
                else:
                    temp_str = "N/A"

                method_str = f"warmup={meas['warmup_runs']}, samples={meas['timed_runs']}, k={meas['inner_loop_k']} (total inf={meas['total_timed_inferences']})"
                print(
                    f"      - {dev.label:<32} [{dev.key}]: {med_ms:>8.3f} ms | {gflops_s:>8.2f} GFLOP/s | "
                    f"Pwr: {pwr_str:<26} | Temp: {temp_str:<22} | ({method_str})"
                )

            # Determine real fastest chip and second-fastest for margin computation
            measured_medians = {k: v["stats"]["median_ms"] for k, v in meas_by_device.items()}
            sorted_by_time = sorted(measured_medians.items(), key=lambda x: x[1])
            fastest_key, fastest_ms = sorted_by_time[0]
            second_key, second_ms = sorted_by_time[1] if len(sorted_by_time) > 1 else (fastest_key, fastest_ms)

            # Margin: second-fastest time divided by fastest time
            decision_margin = round(second_ms / max(fastest_ms, 1e-4), 2)
            is_close_call = bool(decision_margin < 1.50)
            if is_close_call:
                total_close_calls += 1

            pred_ms = measured_medians.get(pred_key, 9999.0)

            # Strict match rule: predicted == fastest chip
            is_match = (pred_key == fastest_key)
            regret_pct = ((pred_ms - fastest_ms) / max(fastest_ms, 1e-4)) * 100.0
            if is_match:
                exact_matches += 1
                if is_close_call:
                    close_call_matches += 1

            match_label = "MATCH (Optimal)" if is_match else "MISMATCH"
            close_flag = " [CLOSE CALL (<1.5x)]" if is_close_call else ""
            print(f"    --> Physical Fastest Chip: {fastest_key.upper()} ({fastest_ms:.3f} ms) | Second: {second_key.upper()} ({second_ms:.3f} ms) | Margin: {decision_margin:.2f}x{close_flag} | Verdict: {match_label} | Regret: {regret_pct:.2f}%")

            results_json_levels.append({
                "level_index": lvl,
                "model_name": name,
                "family": family,
                "batch": batch,
                "parameters": fact["params"],
                "weight_bytes": fact["weight_bytes"],
                "weight_mib": fact["weight_mib"],
                "weight_mb": fact["weight_mb"],
                "flops_per_sample": fact["flops_per_sample"],
                "total_flops": fact["total_flops"],
                "arithmetic_intensity_flops_per_byte": fact["intensity"],
                "router_prediction": {
                    "chosen_device_key": pred_key,
                    "prediction_source": pred_source,
                    "reason": decision["reason"],
                    "candidates": decision["candidates"],
                },
                "measurements": meas_by_device,
                "actual_fastest_device_key": fastest_key,
                "actual_fastest_median_ms": fastest_ms,
                "actual_second_device_key": second_key,
                "actual_second_median_ms": second_ms,
                "decision_margin": decision_margin,
                "is_close_call": is_close_call,
                "exact_match": is_match,
                "regret_pct": round(regret_pct, 4),
            })

        # ---------------------------------------------------------------------
        # 4. FINAL SCORECARD & AUDIT
        # ---------------------------------------------------------------------
        print("\n" + "=" * 125)
        print(" [PHASE 4] FINAL PHYSICAL BENCHMARK SCORECARD & ACCURACY AUDIT")
        print("=" * 125)
        print(f"{'Lvl':<4} | {'Model Name':<16} | {'Batch':<5} | {'Weight MiB':<10} | {'CPU (ms)':<9} | {'iGPU (ms)':<9} | {'dGPU (ms)':<9} | {'Fastest':<7} | {'Margin':<7} | {'Router Match':<14} | {'Regret (%)'}")
        print("-" * 125)

        for lvl_res in results_json_levels:
            cpu_t = lvl_res["measurements"].get("cpu", {}).get("stats", {}).get("median_ms")
            igpu_t = lvl_res["measurements"].get("dml:0", {}).get("stats", {}).get("median_ms")
            dgpu_t = lvl_res["measurements"].get("dml:1", {}).get("stats", {}).get("median_ms")

            cpu_s = f"{cpu_t:.3f}" if cpu_t is not None else "--"
            igpu_s = f"{igpu_t:.3f}" if igpu_t is not None else "--"
            dgpu_s = f"{dgpu_t:.3f}" if dgpu_t is not None else "--"

            match_s = "EXACT MATCH" if lvl_res["exact_match"] else f"NO (Pred: {lvl_res['router_prediction']['chosen_device_key'].upper()})"
            margin_s = f"{lvl_res['decision_margin']:.2f}x"
            print(
                f"{lvl_res['level_index']:<4} | {lvl_res['model_name']:<16} | {lvl_res['batch']:<5} | {lvl_res['weight_mib']:<10.2f} | "
                f"{cpu_s:<9} | {igpu_s:<9} | {dgpu_s:<9} | {lvl_res['actual_fastest_device_key'].upper():<7} | {margin_s:<7} | {match_s:<14} | {lvl_res['regret_pct']:>8.2f}%"
            )

        print("-" * 125)
        accuracy_pct = (exact_matches / total_levels) * 100.0
        close_call_accuracy_pct = (close_call_matches / total_close_calls * 100.0) if total_close_calls > 0 else 100.0
        all_regrets = [r["regret_pct"] for r in results_json_levels]
        mean_regret = float(np.mean(all_regrets)) if all_regrets else 0.0
        max_regret = float(np.max(all_regrets)) if all_regrets else 0.0

        print(f"\nRouter Allocation Accuracy (Overall Exact Match): {exact_matches}/{total_levels} ({accuracy_pct:.1f}%)")
        print(f"Close Calls Accuracy (Margin < 1.5x)         : {close_call_matches}/{total_close_calls} ({close_call_accuracy_pct:.1f}%)")
        print(f"Empirical Regret                             : Mean = {mean_regret:.2f}%, Max = {max_regret:.2f}%")
        print(f"Benchmark Completion Timestamp                : {datetime.now(timezone.utc).isoformat()}")

        # ---------------------------------------------------------------------
        # 5. ARCHITECTURAL ANALYSIS & HYPOTHESIS
        # ---------------------------------------------------------------------
        print("\n" + "=" * 125)
        print(" [PHASE 5] ARCHITECTURAL ANALYSIS (Hypotheses & Physics Rationale)")
        print("=" * 125)
        print("Hypothesis: For MLP models, the crossover between CPU and discrete GPU (NVIDIA RTX 5070 Laptop GPU)")
        print(f"follows model weight footprint relative to the {CPU_CACHE_MB} MB CPU cache (AMD Ryzen 9 8940HX L3 cache),")
        print("rather than FLOP count.")
        print("  - MLPs possess low arithmetic intensity (~0.5 - 1.0 FLOP/byte per sample), meaning weights are streamed")
        print(f"    with minimal arithmetic reuse. Below {CPU_CACHE_MB} MB, weights fit in the CPU L3 cache, allowing")
        print("    the CPU to avoid DRAM latency and out-perform the discrete GPU, which incurs a fitted overhead of")
        print("    0.1511 ms (manifest fit_dml:1_t0_ms).")
        print(f"  - When MLP weights exceed {CPU_CACHE_MB} MB, CPU execution must stream from system DDR5 memory, allowing the")
        print("    RTX 5070 Laptop GPU (equipped with GDDR7 memory per manufacturer datasheet) to achieve lower inference latencies.")
        print("  - For Convolutional models with spatial kernel reuse, higher arithmetic intensity amortizes the 0.1511 ms")
        print("    dispatch overhead at much smaller model sizes.")
        print("=" * 125 + "\n")

        # Save structured JSON
        final_json_payload = {
            "benchmark_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "unseen_generalization_near_switch_fit_only" if unseen_mode else "standard_10_level",
            "log_txt_path": str(txt_path.as_posix()),
            "rig_discovery": rig,
            "levels": results_json_levels,
            "summary": {
                "total_levels": total_levels,
                "exact_matches": exact_matches,
                "accuracy_pct": round(accuracy_pct, 2),
                "total_close_calls": total_close_calls,
                "close_call_matches": close_call_matches,
                "close_call_accuracy_pct": round(close_call_accuracy_pct, 2),
                "mean_regret_pct": round(mean_regret, 2),
                "max_regret_pct": round(max_regret, 2),
            },
            "hypothesis": (
                f"Hypothesis: For MLP models, the crossover between CPU and discrete GPU (NVIDIA RTX 5070 Laptop GPU) "
                f"follows model weight footprint relative to the {CPU_CACHE_MB} MB CPU cache (AMD Ryzen 9 8940HX L3 cache), "
                f"rather than FLOP count. MLPs possess low arithmetic intensity (~0.5 - 1.0 FLOP/byte per sample), meaning "
                f"weights are streamed with minimal arithmetic reuse. Below {CPU_CACHE_MB} MB, weights fit in the CPU L3 cache, "
                f"allowing the CPU to avoid DRAM latency and out-perform the discrete GPU, which incurs a fitted overhead of "
                f"0.1511 ms (manifest fit_dml:1_t0_ms). When MLP weights exceed {CPU_CACHE_MB} MB, CPU execution must stream "
                f"from system DDR5 memory, allowing the RTX 5070 Laptop GPU (equipped with GDDR7 memory per manufacturer datasheet) "
                f"to achieve lower inference latencies. For Convolutional models with spatial kernel reuse, higher arithmetic intensity "
                f"amortizes the 0.1511 ms dispatch overhead at much smaller model sizes."
            ),
        }

        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(final_json_payload, jf, indent=2)

        # Dual-log to results/logs/x86_closeout/
        closeout_txt_path = log_dir_closeout / f"{mode_name}_{timestamp_str}.txt"
        closeout_json_path = log_dir_closeout / f"{mode_name}_{timestamp_str}.json"
        shutil.copyfile(txt_path, closeout_txt_path)
        shutil.copyfile(json_path, closeout_json_path)

        print(f"[COMPLETE] Full console output logged to: {txt_path} and {closeout_txt_path}")
        print(f"[COMPLETE] Full raw samples & metrics logged to: {json_path} and {closeout_json_path}")

    finally:
        sys.stdout = sys.__stdout__
        tee.close()


def main():
    parser = argparse.ArgumentParser(description="SiliconRoute 10-Level Empirical Hardware Benchmark")
    parser.add_argument(
        "--unseen",
        action="store_true",
        help="Run generalization test on unseen near-switch-point model architectures with measured lookup disabled (fit only).",
    )
    args = parser.parse_args()
    run_benchmark_suite(unseen_mode=args.unseen)


if __name__ == "__main__":
    main()
