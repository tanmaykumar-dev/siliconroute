# SiliconRoute

**A local-first, self-learning AI load balancer for heterogeneous Windows laptops.**

SiliconRoute benchmarks ONNX models across all available local compute silicon (Host CPU, integrated GPU, and discrete GPU), stores every empirical measurement in SQLite, fits physics-grounded hardware performance models (command overhead, cache bandwidth, DRAM bandwidth, and compute throughput), and routes inference tasks to the optimal chip based on user goals: **Fastest**, **Battery**, **Balanced**, or **Cool**.

---

## 1. Problem

Modern laptops are heterogeneous systems with multiple compute devices: multi-core CPUs with large L3 caches, integrated GPUs (iGPUs) sharing system memory, and high-power discrete GPUs (dGPUs) with dedicated VRAM.

Standard AI deployment frameworks make static assumptions:
- "Always run on the discrete GPU" — disastrous on small models and cold starts. Launching a tiny model on an idle RTX 5070 takes milliseconds of dispatch and wake overhead, while an AMD Ryzen CPU finishes in 17 microseconds (CPU is 8.6x faster).
- "Always run on the CPU" — leaves massive hardware throughput on the table for large sustained matrix operations where the RTX delivers over 11 TFLOP/s.
- "Software controls power" — software cannot directly control hardware power delivery. Power delivery is governed by hardware voltage regulators and Windows firmware policies. SiliconRoute achieves energy and thermal efficiency by **controlling which chip does the work**.

---

## 2. Method

SiliconRoute operates in four phases:
1. **Empirical Measurement**: Times real ONNX inference workloads on each hardware provider (`CPUExecutionProvider`, `DmlExecutionProvider` per DirectML adapter). Collects live system telemetry (NVML dGPU power, clocks, P-states, temperatures; WMI battery discharge rates; psutil memory and CPU utilization). Stores raw sample timings, bootstrap 95% confidence intervals, and inter-session stability.
2. **Physical Hardware Modeling**: Fits multiple analytical scaling equations ($F_1$ Classic Roofline, $F_2$ Two-Level Cache Roofline, $F_3$ Log-Linear, $F_4$ Family-Specific Roofline) using Non-Negative Least Squares (NNLS) with $1/t$ relative weighting. Selects the optimal model per device via Leave-One-Out (LOO) Mean Absolute Percentage Error (MAPE).
3. **Multi-Objective Routing**:
   - Uses empirical measurements first for previously profiled configurations.
   - Falls back to hardware model predictions for novel models or batch sizes.
   - Applies live hardware context rules:
     - **Low Battery**: When unplugged and battery is under 30%, forces battery optimization mode.
     - **GPU Sleep / Wake Penalty**: Dynamic idle-gap wake penalties based on NVML P-state (P8 sleep vs P0/P2 active).
     - **Cold-Start Rule**: For cold starts (session creation + first inference), defaults to CPU unless an accelerator is predicted >30% lower latency, preventing ORT DirectML session initialization stalls.
     - **Session Volatility Bands**: 15% volatility band tie-breaking favoring chips with lower session-to-session variance.
4. **Verification & Self-Audit**: Verifies decisions on physical hardware, computing exact regret vs optimal.

---

## 3. Results (Published Benchmark)

*All numbers sourced from `results/final/manifest.json` and generated from `data/final/siliconroute_final.db`.*

### 24-Decision Hardware Evaluation (Decisions 117–140)
Evaluated across 8 sustained, 8 idle-loaded, and 8 cold-start tasks on real laptop hardware (AMD Ryzen 9 8940HX, AMD Radeon 610M, NVIDIA GeForce RTX 5070 Laptop GPU):

| Strategy | Decisions Won | Total Decisions | Accuracy (%) | Mean Regret (%) | P90 Regret (%) |
|---|---|---|---|---|---|
| **SiliconRoute** | **22** | **24** | **91.7%** | **1.75%** | **0.00%** |
| Always-CPU | 15 | 24 | 62.5% | 113.06% | 420.56% |
| Always-RTX | 9 | 24 | 37.5% | 304.93% | 784.34% |
| Fit-Only Router | 19 | 24 | 79.2% | 31.42% | 12.50% |

- **SiliconRoute achieved 91.7% decision accuracy**, reducing average slowdown vs optimal to **1.75%**.
- **Always-RTX suffered 304.93% mean regret**, because small models and idle wake delays severely degrade discrete GPU responsiveness.
- **Always-CPU suffered 113.06% mean regret**, failing on large sustained matrix multiplications where RTX delivers 11+ TFLOP/s.

### Workload Accuracy Breakdown (Decisions 117–140)
- **Sustained (Warm Runs)**: SiliconRoute 8/8 (100.0%, 0.00% regret), Always-CPU 4/8 (50.0%), Always-RTX 4/8 (50.0%), Fit-Only 8/8 (100.0%).
- **Idle-Loaded (Warm Session, 10s Idle Gap)**: SiliconRoute 8/8 (100.0%, 0.00% regret), Always-CPU 3/8 (37.5%), Always-RTX 5/8 (62.5%), Fit-Only 7/8 (87.5%).
- **Cold-Start (Fresh Session + 1st Inference)**: SiliconRoute 6/8 (75.0%, 5.25% regret), Always-CPU 8/8 (100.0%), Always-RTX 0/8 (0.0%, 522.22% regret), Fit-Only 4/8 (50.0%).

### Cold-Start Rule Verification (Decisions 141–148)
*With the Cold-Start Rule active (choose CPU unless another chip is predicted >30% lower latency):*
- **SiliconRoute**: 6/8 wins (75.0% accuracy), **3.00% mean regret**, 11.38% p90 regret.
- **Always-CPU**: 6/8 wins (75.0% accuracy), 3.00% mean regret.
- **Always-RTX**: 0/8 wins (0.0% accuracy), 575.15% mean regret.
- **Fit-Only Router**: 4/8 wins (50.0% accuracy), 109.26% mean regret.

---

## 4. Key Findings

1. **CPU Beats RTX on Small Tasks**: For lightweight models (e.g. `mlp-256w-4l` at batch 1), the CPU executes in **0.017 ms**, while the RTX 5070 takes **0.146 ms** due to DirectML command queue dispatch overhead. The CPU is **8.6x faster**.
2. **GPU Identity Swaps on Hybrid Laptops**: On Windows 11 laptops with NVIDIA Optimus / Advanced Optimus, DirectML adapter enumeration order is dynamic: DXGI adapter index 0 and 1 swap depending on whether the discrete GPU is in D3cold sleep or active render mode. SiliconRoute solves this via in-process DXGI enumeration (`dxgi.dll` ctypes) verifying PCI Vendor IDs (`0x10DE` vs `0x1002`) and LUIDs, backed by a 300 ms NVML load fingerprint test.
3. **Batch-8 DirectML Anomaly**: On DirectML GPUs, latency does not scale monotonically with batch size; convolution models exhibit kernel selection anomalies around batch 8 (e.g. `conv-96c-4l` takes 13.5 ms at B=8 vs 2.4 ms at B=4 on RTX 5070). SiliconRoute captures this via empirical lookup rather than relying purely on linear roofline fits.
4. **Loading Time Dominates Cold Starts**: For large models (e.g. `mlp-3072w-4l`), sustained RTX inference takes **0.673 ms**, but cold-start execution takes **202.8 ms** (>300x overhead) due to ONNX Runtime session compilation and DirectML weight buffer allocation. The CPU completes cold start in **189.8 ms**, winning the cold-start race.

---

## 5. Limitations

- **FP32 Only**: All synthetic and profiled models currently use float32 precision. FP16 and INT8 tensor core acceleration are not yet profiled.
- **DirectML Only on Windows**: GPU execution uses `DmlExecutionProvider` across both AMD and NVIDIA GPUs; native CUDA or TensorRT execution providers are not used.
- **Synthetic Model Families**: Benchmarks utilize parameterized MLP and Convolution architectures; real-world Transformer and LLM attention topologies are planned.
- **Profiled Configurations**: Empirical lookup guarantees optimal routing on previously characterized configs; novel configs rely on analytical fits with ~20% MAPE.
- **Session Variability**: DirectML GPU runtimes exhibit up to 139.9% inter-session variance under background OS scheduling, requiring volatility bands.
- **Energy Telemetry**: Whole-system energy is available via WMI battery discharge rate when unplugged, and GPU package energy is available via NVML on NVIDIA. CPU package power (RAPL) and AMD iGPU power are not accessible via standard unprivileged Windows APIs.

---

## 6. How This Was Built

- **AI-Assisted Engineering**: Built using Google DeepMind's Antigravity agentic coding system. All architectural concepts, analytical models, and code modifications were directed, reviewed, and tested step-by-step.
- **Strict Data-Integrity Protocol**: App code contains **zero hardcoded, estimated, or mock measurements**. Every figure traces directly to a real hardware execution stored in SQLite.
- **Independent Verification**: Evaluated by an automated, read-only verifier agent generating reports exclusively via deterministic scripts and verbatim log outputs (`.agents/rules/05-verbatim-logs.md`).

---

## 7. Quick Start & Reproduction

### One-Click Start (Windows)
Double-click `start.bat` or run:
```cmd
start.bat
```
This automatically initializes the Python 3.12 virtual environment, installs dependencies, launches the FastAPI server at `http://127.0.0.1:8000`, and opens the dark-mode dashboard in your browser.

### How to Reproduce
Run the automated 15-minute reproduction script:
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

- **Frozen Database**: [`data/final/siliconroute_final.db`](file:///e:/THE%20SNAP%20X%20HP/data/final/siliconroute_final.db)
- **Size**: 1,044,480 bytes
- **SHA256**: `98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5`
- **Published Results & Manifest**: Located in [`results/final/`](file:///e:/THE%20SNAP%20X%20HP/results/final/).
