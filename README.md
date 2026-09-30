# SiliconRoute

**A local-first, self-learning AI load balancer for heterogeneous Windows laptops.**

SiliconRoute benchmarks ONNX models on every compute chip in a Windows laptop (CPU, integrated GPU, discrete GPU, and NPU), stores every measurement in SQLite, fits hardware performance models (command overhead, cache and DRAM bandwidth, compute throughput), and routes each inference task to the best chip for the user's goal. The **Fastest** goal is evaluated below across three workload types (sustained, idle, cold start); the **Battery**, **Balanced** and **Cool** goals are implemented but not yet evaluated.

> [!IMPORTANT]
> ### Primary Strategic Goal: ARM Architecture & Snapdragon X2
> While baseline evaluation was conducted on hybrid x86 hardware, SiliconRoute's **primary development focus is ARM-based Copilot+ systems**. Active hardware benchmarking and profiling is currently underway on the **Qualcomm Snapdragon X platform (including Snapdragon X Elite and upcoming Snapdragon X2 systems)**, evaluating heterogeneous execution across Qualcomm Oryon ARM CPU cores, DirectML GPU acceleration, and dedicated Qualcomm Hexagon NPU offload via ONNX Runtime's `QNNExecutionProvider`.

---

## 1. Problem

Modern laptops are heterogeneous systems with multiple compute devices: multi-core CPUs with large L3 caches, integrated GPUs (iGPUs) sharing system memory, and high-power discrete GPUs (dGPUs) with dedicated VRAM.

Standard AI deployment frameworks make static assumptions:
- "Always run on the discrete GPU" — slow for small models and cold starts. Even with the GPU warm, a tiny model (`mlp-256w-4l`, batch 1) takes 0.142 ms <!-- metric: mlp_256_b1_rtx_latency_ms --> per call on the RTX 5070 but only 0.017 ms <!-- metric: mlp_256_b1_cpu_latency_ms --> on the Ryzen CPU, so the CPU is 8.4x <!-- metric: speedup_cpu_over_rtx_mlp_256_b1 --> faster. After an idle period or on a cold start, the GPU's disadvantage grows (see Method).
- "Always run on the CPU" — misses large speedups on big sustained workloads: on the largest MLP tested (`mlp-3072w-4l`, batch 1) the RTX is 6.4x <!-- metric: speedup_rtx_over_cpu_mlp_3072_b1_sustained --> faster than the CPU.
- "Software controls power" — software cannot control how power is delivered inside a laptop; hardware and firmware do. What software *can* control is **which chip does the work**. SiliconRoute's energy- and heat-aware goals use that lever, but their effect has not been measured yet.

---

## 2. Method

SiliconRoute operates in four phases:
1. **Empirical Measurement**: Times real ONNX inference workloads on each hardware provider (`CPUExecutionProvider`, `DmlExecutionProvider` per DirectML adapter). Collects live system telemetry (NVML dGPU power, clocks, P-states, temperatures; WMI battery discharge rates; psutil memory and CPU utilization). Stores raw sample timings, bootstrap 95% <!-- metric: bootstrap_ci_pct --> confidence intervals, and inter-session stability.
   - **Measurement Conditions**: All benchmarks were conducted with the laptop plugged into AC power under the high-performance Windows 'Turbo' power scheme (preventing clock throttling), with NVIDIA driver 616.56 and ONNX Runtime 1.24.4.
   - **Inference Timing Scope**: Timings are end-to-end execution times including host-to-device and device-to-host CPU-GPU tensor copies (default ORT `RunOptions`), reflecting true application response times rather than isolated compute kernel duration.
2. **Physical Hardware Modeling**: Fits multiple analytical scaling equations ($F_1$ Classic Roofline, $F_2$ Two-Level Cache Roofline, $F_3$ Log-Linear, $F_4$ Family-Specific Roofline) using Non-Negative Least Squares (NNLS) with $1/t$ relative weighting. Selects the optimal model per device via Leave-One-Out (LOO) Mean Absolute Percentage Error (MAPE).
3. **Multi-Objective Routing**:
   - Uses empirical measurements first for previously profiled configurations (`WorkloadMeasurement` records).
   - Falls back to measured family slowdown ratios or hardware model predictions for novel models or batch sizes.
   - Applies live hardware context rules:
     - **Low Battery**: When unplugged and battery is under 30% <!-- metric: low_battery_threshold_pct -->, switches to the Battery goal (implemented; not yet tested on battery).
     - **Empirical Wake & Cold-Start Slowdowns**: Wake penalties and cold-start slowdowns are measured empirically across workloads (vs latest sustained median):
       - `idle_loaded`: CPU 1.76x <!-- metric: workload_idle_loaded_cpu_ratio_median --> [0.71x <!-- metric: workload_idle_loaded_cpu_ratio_min -->–14.42x <!-- metric: workload_idle_loaded_cpu_ratio_max -->, n=20 <!-- metric: workload_idle_loaded_cpu_sample_count -->], AMD Radeon 610M 1.62x <!-- metric: workload_idle_loaded_radeon_ratio_median --> [0.98x <!-- metric: workload_idle_loaded_radeon_ratio_min -->–11.96x <!-- metric: workload_idle_loaded_radeon_ratio_max -->, n=20 <!-- metric: workload_idle_loaded_radeon_sample_count -->], NVIDIA RTX 5070 2.14x <!-- metric: workload_idle_loaded_rtx_ratio_median --> [0.51x <!-- metric: workload_idle_loaded_rtx_ratio_min -->–12.22x <!-- metric: workload_idle_loaded_rtx_ratio_max -->, n=20 <!-- metric: workload_idle_loaded_rtx_sample_count -->]
       - `cold_start`: CPU 41.7x <!-- metric: workload_cold_start_cpu_ratio_median --> [0.93x <!-- metric: workload_cold_start_cpu_ratio_min -->–357.94x <!-- metric: workload_cold_start_cpu_ratio_max -->, n=28 <!-- metric: workload_cold_start_cpu_sample_count -->], AMD Radeon 610M 27.9x <!-- metric: workload_cold_start_radeon_ratio_median --> [1.40x <!-- metric: workload_cold_start_radeon_ratio_min -->–447.51x <!-- metric: workload_cold_start_radeon_ratio_max -->, n=28 <!-- metric: workload_cold_start_radeon_sample_count -->], NVIDIA RTX 5070 230.5x <!-- metric: workload_cold_start_rtx_ratio_median --> [2.40x <!-- metric: workload_cold_start_rtx_ratio_min -->–580.13x <!-- metric: workload_cold_start_rtx_ratio_max -->, n=28 <!-- metric: workload_cold_start_rtx_sample_count -->]
     - **Cold-Start Rule**: For cold starts (session creation + first inference), defaults to CPU unless an accelerator is predicted >30% <!-- metric: cold_start_rule_threshold_pct --> lower latency, because in our measurements accelerators were rarely faster on cold starts.
     - **Session Volatility Bands**: when the top two chips score within 15% <!-- metric: volatility_tiebreak_band_pct --> of each other, prefers the chip with lower measured session-to-session variability.
4. **Verification & Self-Audit**: Verifies decisions on physical hardware, computing exact regret vs optimal.

---

## 3. Results (Published Benchmark)

*All numbers sourced from `results/final/manifest.json` and generated from `data/final/siliconroute_final.db`.*

### 24-Decision Hardware Evaluation (Decisions 117–140)
Evaluated across 8 sustained, 8 idle-loaded, and 8 cold-start tasks on real laptop hardware (AMD Ryzen 9 8940HX, AMD Radeon 610M, NVIDIA GeForce RTX 5070 Laptop GPU):

| Strategy | Decisions Won | Total Decisions | Accuracy (%) | Mean Regret (%) | P90 Regret (%) |
|---|---|---|---|---|---|
| **SiliconRoute** | **22** <!-- metric: decisions_117_140_sr_wins --> | **24** <!-- metric: decisions_117_140_total --> | **91.7%** <!-- metric: decisions_117_140_sr_accuracy_pct --> | **1.75%** <!-- metric: decisions_117_140_sr_mean_regret_pct --> | **0.00%** <!-- metric: decisions_117_140_sr_p90_regret_pct --> |
| Always-CPU | 15 <!-- metric: decisions_117_140_always_cpu_wins --> | 24 <!-- metric: decisions_117_140_total --> | 62.5% <!-- metric: decisions_117_140_always_cpu_accuracy_pct --> | 113.06% <!-- metric: decisions_117_140_always_cpu_mean_regret_pct --> | 420.56% <!-- metric: decisions_117_140_always_cpu_p90_regret_pct --> |
| Always-RTX | 9 <!-- metric: decisions_117_140_always_rtx_wins --> | 24 <!-- metric: decisions_117_140_total --> | 37.5% <!-- metric: decisions_117_140_always_rtx_accuracy_pct --> | 304.93% <!-- metric: decisions_117_140_always_rtx_mean_regret_pct --> | 784.34% <!-- metric: decisions_117_140_always_rtx_p90_regret_pct --> |
| Fit-Only Router | 19 <!-- metric: decisions_117_140_fit_only_wins --> | 24 <!-- metric: decisions_117_140_total --> | 79.2% <!-- metric: decisions_117_140_fit_only_accuracy_pct --> | 31.42% <!-- metric: decisions_117_140_fit_only_mean_regret_pct --> | 12.50% <!-- metric: decisions_117_140_fit_only_p90_regret_pct --> |

- **SiliconRoute achieved 91.7% <!-- metric: decisions_117_140_sr_accuracy_pct --> decision accuracy**, reducing average slowdown vs optimal to **1.75%** <!-- metric: decisions_117_140_sr_mean_regret_pct -->.
- **Always-RTX suffered 304.93% <!-- metric: decisions_117_140_always_rtx_mean_regret_pct --> mean regret**, because the RTX loses badly on small models and cold starts.
- **Always-CPU suffered 113.06% <!-- metric: decisions_117_140_always_cpu_mean_regret_pct --> mean regret**, because it misses the RTX's large speedups on big sustained workloads.
- The p90 regret of 0.00% <!-- metric: decisions_117_140_sr_p90_regret_pct --> reflects that 22 <!-- metric: decisions_117_140_sr_wins --> of 24 <!-- metric: decisions_117_140_total --> choices had zero regret; both misses were cold starts of the largest model, where all chips were close.

<details>
<summary><b>Detailed Workload Breakdown (Sustained, Idle-Loaded, Cold-Start)</b></summary>

### Workload Accuracy Breakdown (Decisions 117–140)
- **Sustained (Warm Runs)**: SiliconRoute 8 <!-- metric: workload_sustained_sr_wins --> / 8 <!-- metric: workload_sustained_total --> (100.0% <!-- metric: workload_sustained_sr_accuracy_pct -->, 0.00% <!-- metric: workload_sustained_sr_mean_regret_pct --> regret), Always-CPU 4 <!-- metric: workload_sustained_always_cpu_wins --> / 8 <!-- metric: workload_sustained_total --> (50.0% <!-- metric: workload_sustained_always_cpu_accuracy_pct -->, 195.52% <!-- metric: workload_sustained_always_cpu_mean_regret_pct --> regret), Always-RTX 4 <!-- metric: workload_sustained_always_rtx_wins --> / 8 <!-- metric: workload_sustained_total --> (50.0% <!-- metric: workload_sustained_always_rtx_accuracy_pct -->, 177.37% <!-- metric: workload_sustained_always_rtx_mean_regret_pct --> regret), Fit-Only 8 <!-- metric: workload_sustained_fit_only_wins --> / 8 <!-- metric: workload_sustained_total --> (100.0% <!-- metric: workload_sustained_fit_only_accuracy_pct -->, 0.00% <!-- metric: workload_sustained_fit_only_mean_regret_pct --> regret).
- **Idle-Loaded (Warm Session, 10s Idle Gap)**: SiliconRoute 8 <!-- metric: workload_idle_loaded_sr_wins --> / 8 <!-- metric: workload_idle_loaded_total --> (100.0% <!-- metric: workload_idle_loaded_sr_accuracy_pct -->, 0.00% <!-- metric: workload_idle_loaded_sr_mean_regret_pct --> regret), Always-CPU 3 <!-- metric: workload_idle_loaded_always_cpu_wins --> / 8 <!-- metric: workload_idle_loaded_total --> (37.5% <!-- metric: workload_idle_loaded_always_cpu_accuracy_pct -->, 143.65% <!-- metric: workload_idle_loaded_always_cpu_mean_regret_pct --> regret), Always-RTX 5 <!-- metric: workload_idle_loaded_always_rtx_wins --> / 8 <!-- metric: workload_idle_loaded_total --> (62.5% <!-- metric: workload_idle_loaded_always_rtx_accuracy_pct -->, 215.22% <!-- metric: workload_idle_loaded_always_rtx_mean_regret_pct --> regret), Fit-Only 7 <!-- metric: workload_idle_loaded_fit_only_wins --> / 8 <!-- metric: workload_idle_loaded_total --> (87.5% <!-- metric: workload_idle_loaded_fit_only_accuracy_pct -->, 1.86% <!-- metric: workload_idle_loaded_fit_only_mean_regret_pct --> regret).
- **Cold-Start (Fresh Session + 1st Inference)**: SiliconRoute 6 <!-- metric: workload_cold_start_sr_wins --> / 8 <!-- metric: workload_cold_start_total --> (75.0% <!-- metric: workload_cold_start_sr_accuracy_pct -->, 5.25% <!-- metric: workload_cold_start_sr_mean_regret_pct --> regret), Always-CPU 8 <!-- metric: workload_cold_start_always_cpu_wins --> / 8 <!-- metric: workload_cold_start_total --> (100.0% <!-- metric: workload_cold_start_always_cpu_accuracy_pct -->, 0.00% <!-- metric: workload_cold_start_always_cpu_mean_regret_pct --> regret), Always-RTX 0 <!-- metric: workload_cold_start_always_rtx_wins --> / 8 <!-- metric: workload_cold_start_total --> (0.0% <!-- metric: workload_cold_start_always_rtx_accuracy_pct -->, 522.22% <!-- metric: workload_cold_start_always_rtx_mean_regret_pct --> regret), Fit-Only 4 <!-- metric: workload_cold_start_fit_only_wins --> / 8 <!-- metric: workload_cold_start_total --> (50.0% <!-- metric: workload_cold_start_fit_only_accuracy_pct -->, 92.41% <!-- metric: workload_cold_start_fit_only_mean_regret_pct --> regret).

### Cold-Start Rule Verification (Decisions 141–148)
*With the Cold-Start Rule active (choose CPU unless another chip is predicted >30% <!-- metric: cold_start_rule_threshold_pct --> lower latency):*
- **SiliconRoute**: 6 <!-- metric: cold_start_141_148_sr_wins --> / 8 <!-- metric: cold_start_141_148_total --> wins (75.0% <!-- metric: cold_start_141_148_sr_accuracy_pct --> accuracy), **3.00%** <!-- metric: cold_start_141_148_sr_mean_regret_pct --> mean regret, 11.38% <!-- metric: cold_start_141_148_sr_p90_regret_pct --> p90 regret.
- **Always-CPU**: 6 <!-- metric: cold_start_141_148_always_cpu_wins --> / 8 <!-- metric: cold_start_141_148_total --> wins (75.0% <!-- metric: cold_start_141_148_always_cpu_accuracy_pct --> accuracy), 3.00% <!-- metric: cold_start_141_148_always_cpu_mean_regret_pct --> mean regret.
- **Always-RTX**: 0 <!-- metric: cold_start_141_148_always_rtx_wins --> / 8 <!-- metric: cold_start_141_148_total --> wins (0.0% <!-- metric: cold_start_141_148_always_rtx_accuracy_pct --> accuracy), 575.15% <!-- metric: cold_start_141_148_always_rtx_mean_regret_pct --> mean regret.
- **Fit-Only Router**: 4 <!-- metric: cold_start_141_148_fit_only_wins --> / 8 <!-- metric: cold_start_141_148_total --> wins (50.0% <!-- metric: cold_start_141_148_fit_only_accuracy_pct --> accuracy), 109.26% <!-- metric: cold_start_141_148_fit_only_mean_regret_pct --> mean regret.
- With the rule active, SiliconRoute chose the CPU in all 8 <!-- metric: cold_start_141_148_total --> decisions, so it matched the always-CPU baseline exactly. Both misses were cold starts of the largest model, where the Radeon 610M was narrowly fastest.

</details>

---

## 4. Key Findings

1. **CPU Beats RTX on Small Tasks**: For lightweight models (e.g. `mlp-256w-4l` at batch 1), in session 225, the CPU executes in **0.017 ms** <!-- metric: mlp_256_b1_cpu_latency_ms --> (run 839), while the RTX 5070 takes **0.142 ms** <!-- metric: mlp_256_b1_rtx_latency_ms --> (run 841) (hypothesis: per-call DirectML dispatch and host-device transfer overhead dominates for tiny models). The CPU is **8.4x** <!-- metric: speedup_cpu_over_rtx_mlp_256_b1 --> faster.
2. **GPU Identity Swaps on Hybrid Laptops**: DirectML adapter numbering was not stable on this laptop: in 12 <!-- metric: identity_suspect_runs --> runs, adapter indices 0 and 1 were swapped (the "Radeon" ran at RTX speed and vice versa). Hypothesis: the enumeration order depends on the discrete GPU's power state. SiliconRoute now identifies GPUs in-process via DXGI (PCI vendor IDs `0x10DE` / `0x1002` and LUIDs), confirmed by a 300 ms <!-- metric: fingerprint_test_duration_ms --> NVML load fingerprint; the swapped runs are flagged and excluded.
3. **Batch-8 DirectML Anomaly**: On DirectML GPUs, latency does not scale smoothly with batch size around batch 8 (hypothesis: the driver switches kernels or algorithms). In session 87, `conv-96c-4l` takes 13.5 ms <!-- metric: directml_anomaly_conv96_b8_ms --> at B=8 (run 622) vs 2.4 ms <!-- metric: directml_anomaly_conv96_b4_ms --> at B=4 (run 621) on RTX 5070 (a 5.6x <!-- metric: directml_anomaly_conv96_slowdown --> slowdown). SiliconRoute captures this via empirical lookup rather than relying purely on linear roofline fits.
4. **Loading Time Dominates Cold Starts**: In session 194, sustained RTX inference on `mlp-3072w-4l` takes **0.655 ms** <!-- metric: mlp_3072_b1_sustained_rtx_ms --> (run 814) vs CPU **4.20 ms** <!-- metric: mlp_3072_b1_sustained_cpu_ms --> (run 812). But under cold start, in Decision 144, the RTX cold start (session creation + first inference) takes **219.9 ms** <!-- metric: mlp_3072_cold_rtx_rounded_ms --> (WorkloadMeasurement 132, a 335.7x <!-- metric: overhead_rtx_cold_start_vs_sustained_mlp_3072 --> overhead vs sustained), while CPU completes in **215.8 ms** <!-- metric: mlp_3072_cold_cpu_rounded_ms --> (WorkloadMeasurement 130); the Radeon 610M was fastest in that decision, so the cold-start winner varies. Similarly, in headline Decision 124, CPU cold start completes in 189.8 ms <!-- metric: mlp_3072_cold_cpu_dec124_ms --> vs RTX 202.8 ms <!-- metric: mlp_3072_cold_rtx_dec124_ms --> (a 309.6x <!-- metric: overhead_rtx_cold_start_vs_sustained_dec124 --> overhead).

---

## 5. Limitations

- **FP32 Only**: All synthetic and profiled models currently use float32 precision. FP16 and INT8 tensor core acceleration are not yet profiled.
- **DirectML Only on Windows**: GPU execution uses `DmlExecutionProvider` across both AMD and NVIDIA GPUs; native CUDA or TensorRT execution providers are not used.
- **Synthetic Model Families**: Benchmarks utilize parameterized MLP and Convolution architectures; real-world Transformer and LLM attention topologies are planned.
- **Profiled Configurations**: The evaluation used only previously profiled configurations; for new models or batch sizes the router relies on the fitted models, whose average LOO MAPE is ~22.3% <!-- metric: predictive_model_mape_pct -->.
- **Session Variability**: The same configuration can differ between sessions by up to 139.9% <!-- metric: volatility_rtx_max_pct --> (RTX); the cause has not been established.
- **Energy Telemetry**: Whole-system energy is available via WMI battery discharge rate when unplugged, and GPU package energy is available via NVML on NVIDIA. CPU package power (RAPL) and AMD iGPU power are not accessible via standard unprivileged Windows APIs.
- **Energy Goals Not Evaluated**: Only one GPU energy measurement exists, so the Battery and Balanced goals currently fall back to latency, and the Cool goal (GPU temperature penalty) is untested. CPU and Radeon 610M energy require battery-drain measurements (planned).
- **Single Laptop**: All results come from one laptop (AMD Ryzen 9 8940HX, AMD Radeon 610M, NVIDIA GeForce RTX 5070 Laptop GPU).
- **Real AI Models**: MobileNet, ResNet and a small transformer are planned for v1.1.
- **ARM Architecture & Snapdragon X Testing**: Active hardware benchmarking and profiling is currently underway on the Qualcomm Snapdragon X platform (including Snapdragon X Elite and upcoming Snapdragon X2 systems). Heterogeneous load balancing across ARM CPU cores, DirectML GPU, and the Qualcomm Hexagon NPU via QNN Execution Provider is our primary development focus.

---

## 6. How This Was Built

- **Author**: Tanmay — defined the problem, the measurement method and the project rules, and reviewed every development phase.
- **AI Assistance**: Most code was written with Google Antigravity (an AI coding agent). Planning, specifications and independent audits of the database were done with Anthropic's Claude.
- **Integrity Protocol**: Early in development, an AI-generated report contained fabricated benchmark numbers; a physics sanity check caught it. Since then, every published number is computed from the frozen database by `scripts/metrics.py` and checked by `tests/test_published_numbers.py`, agent reports are printed from logs only, and the database has been audited independently (raw samples vs. stored statistics, recomputed results, provenance of every headline number). Thresholds such as the cold-start rule are configuration settings, not measurements.

---

## 7. Quick Start & Reproduction

### One-Click Start (Windows)
Double-click `start.bat` or run:
```cmd
start.bat
```
This automatically initializes the Python 3.12 virtual environment, installs dependencies, launches the FastAPI server at `http://127.0.0.1:8000`, and opens the dark-mode dashboard in your browser.

### How to Reproduce
Run the reproduction script (about a minute on the reference laptop):
```powershell
python scripts/reproduce.py
```
This benchmarks CPU vs RTX on small and large MLPs at batch 1 and 32, measures sustained vs cold-start latency, and prints reproduced numbers side-by-side with published values with percentage differences.

### Run All Tests
```powershell
python -m pytest -q
```

---

## 8. Database Provenance

- **Frozen Database**: [data/final/siliconroute_final.db](data/final/siliconroute_final.db)
- **Size**: 1,044,480 bytes <!-- metric: database_size_bytes -->
- **SHA256**: `98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5`
- **Published Results & Manifest**: Located in [results/final/](results/final/).

---

## 9. Primary Focus & Future Roadmap: ARM & Snapdragon X2

SiliconRoute's primary long-term strategic objective is heterogeneous AI load balancing on **ARM-based Windows laptops (Copilot+ PCs)**, with active hardware benchmarking currently underway on **Qualcomm Snapdragon X series** silicon:

- **Active Snapdragon Hardware Testing**: We are actively profiling and evaluating execution behavior on Qualcomm Snapdragon hardware (including Snapdragon X Elite and upcoming Snapdragon X2 systems). Testing covers Qualcomm Oryon ARM CPU cores, DirectML GPU acceleration, and dedicated Hexagon NPU offload via ONNX Runtime's `QNNExecutionProvider`.
- **Primary Goal — Tri-Silicon Load Balancing**: On modern ARM laptops, the dedicated NPU provides massive energy efficiency for neural inference, but can incur model loading and compilation overhead. SiliconRoute is expanding its physical roofline models to dynamically predict the optimal execution path across Oryon CPU cores, DirectML GPU, and Hexagon NPU under dynamic thermal and battery constraints.
- **Battery-First Real-World Workloads**: ARM laptops prioritize battery endurance. Intelligent routing prevents power-hungry GPU wake-ups when the NPU or CPU can complete the inference with minimal energy consumption.
