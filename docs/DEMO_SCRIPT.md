# SiliconRoute v1.0 — Video Demonstration Script

**Duration:** Approximately 2.5 minutes (150 seconds)  
**Format:** Screen walkthrough with spoken narration  
**Source Grounding:** All metrics cited match `results/final/manifest.json` and the running dashboard.

---

## Visual & Spoken Walkthrough

### Part 1: Introduction & Live Telemetry (0:00 – 0:30)

**[Visual: Browser opens on `http://127.0.0.1:8000/` showing the Live Telemetry tab. Real-time 1 Hz line charts update for CPU/RAM, RTX Power & Temp, SM Clock & P-State, and Battery Discharge Rate.]**

**Narration:**
> "Welcome to SiliconRoute v1.0, an autonomous, local-first AI load balancer engineered for modern heterogeneous Windows laptops.
> 
> Modern laptops bundle multiple compute engines—a CPU, an integrated GPU, and a discrete GPU. But software runtime frameworks default to running everything on the GPU, ignoring setup overhead, wake latency, and energy cost. SiliconRoute solves this by measuring execution dynamics, fitting physics-based hardware models, and routing every AI inference to the optimal chip.
> 
> Here on the Live Telemetry tab, SiliconRoute samples hardware sensors at 1 Hz without external daemons:
> - The CPU and unified RAM utilization.
> - The NVIDIA GeForce RTX 5070 Laptop GPU via NVML, tracking temperature, power draw, P-state, and SM clock speed directly inside the dedicated RTX card.
> - The AMD Radeon 610M integrated GPU DirectML adapter.
> - Real-time battery discharge rate from the Windows WMI BatteryStatus interface.
> 
> Across our empirical evaluation, the SQLite WAL database records 480 total benchmark runs `[metric: total_runs]`: 265 sustained runs `[metric: runs_sustained]`, 159 verified sustained runs `[metric: runs_verify_sustained]`, 55 single cold-start runs `[metric: runs_single_cold]`, and 1 energy profile `[metric: runs_energy]`, backing 144 workload measurements `[metric: total_workload_measurements]` and 148 verified routing decisions `[metric: total_decisions]`."

---

### Part 2: Physics-Grounded Hardware Fits & Inspection (0:30 – 1:05)

**[Visual: Click 'Analysis & Fits' tab. Roofline curves and parameter crossover charts appear. Scroll down to Physics Notes and click Run #28 to open the Raw Timing Samples Inspector modal.]**

**Narration:**
> "Under the 'Analysis & Fits' tab, SiliconRoute fits an explainable roofline performance model for each chip:
> $$\text{Latency} = t_0 + \frac{\text{FLOPs}}{\text{Compute Peak}} + \frac{\text{Bytes}}{\text{Memory Bandwidth}}$$
> 
> - **CPU (AMD Ryzen 7 7730U):** Base dispatch latency $t_0 = 0.0144\text{ ms}$ `[metric: fit_cpu_t0_ms]`, compute capacity $886.4\text{ GFLOP/s}$ `[metric: fit_cpu_compute_gflops]`, and SRAM cache bandwidth $393.4\text{ GB/s}$ `[metric: fit_cpu_sram_gb_s]`, with a leave-one-out cross-validation error of $18.89\%$ `[metric: fit_cpu_loo_mape_pct]`.
> - **iGPU (AMD Radeon 610M):** Dispatch latency $t_0 = 0.1113\text{ ms}$ `[metric: fit_dml:0_t0_ms]` and compute capacity $598.8\text{ GFLOP/s}$ `[metric: fit_dml:0_compute_gflops]`.
> - **dGPU (NVIDIA RTX 5070):** Dispatch latency $t_0 = 0.1511\text{ ms}$ `[metric: fit_dml:1_t0_ms]` and compute throughput $11,279.4\text{ GFLOP/s}$ `[metric: fit_dml:1_compute_gflops]`.
> 
> Across all chips and models, the predictive hardware fit achieves an overall Mean Absolute Percentage Error of $22.3\%$ `[metric: predictive_model_mape_pct]`.
> 
> Notice the analytical crossover points: for single-batch MLPs, the latency crossover between the CPU and the RTX 5070 occurs at $17,156,164\text{ parameters}$ `[metric: crossover_mlp_b1_cpu_vs_rtx_params]`. Below 17 million parameters, the CPU is physically faster because PCIe and DirectML driver launch overhead dominates GPU runtime.
> 
> Clicking into any profiled execution opens the Run Inspector modal. For example, Run #28 shows an inner-loop multiplier of $k = 53$ measuring 30 repeated samples to isolate sub-millisecond kernel execution from system jitter, recording a stable median latency of $0.019\text{ ms}$ with full bootstrap confidence bounds `[metric: bootstrap_ci_pct]`."

---

### Part 3: Dynamic Routing Decisions (1:05 – 1:40)

**[Visual: Close modal. Navigate to 'Router & Evaluation' tab. Ensure Epsilon Exploration is unchecked. Select `mlp-256w-4l`, batch 1, sustained, fastest. Then select `mlp-3072w-4l`, batch 1, sustained, fastest.]**

**Narration:**
> "Now let us observe dynamic routing under the 'Router & Evaluation' tab. Epsilon exploration is unchecked by default to enforce pure exploitation of learned hardware parameters.
> 
> First, we evaluate a small network: `mlp-256w-4l` at batch size 1 under a sustained workload with the Fastest latency goal.
> - The router queries the measured database and hardware fit models.
> - The CPU's measured latency is $0.017\text{ ms}$ `[metric: mlp_256_b1_cpu_latency_ms]` (Run #839 `[metric: mlp_256_b1_cpu_run_id]` from Session 225 `[metric: mlp_256_b1_comparison_session_id]`).
> - The RTX 5070 measures $0.142\text{ ms}$ `[metric: mlp_256_b1_rtx_latency_ms]` (Run #841 `[metric: mlp_256_b1_rtx_run_id]`).
> - The CPU achieves an **8.4x speedup** over the RTX 5070 `[metric: speedup_cpu_over_rtx_mlp_256_b1]`.
> - SiliconRoute routes the inference to the CPU, correctly avoiding the discrete GPU's launch penalty.
> 
> Next, we switch to a heavy network: `mlp-3072w-4l` at batch 1.
> - The CPU requires $4.2\text{ ms}$ `[metric: mlp_3072_b1_sustained_cpu_ms]` (Run #812 `[metric: mlp_3072_b1_sustained_cpu_run_id]`).
> - The RTX 5070 runs the layer in just $0.655\text{ ms}$ `[metric: mlp_3072_b1_sustained_rtx_ms]` (Run #814 `[metric: mlp_3072_b1_sustained_rtx_run_id]`).
> - The discrete GPU delivers a **6.4x speedup** over the CPU `[metric: speedup_rtx_over_cpu_mlp_3072_b1_sustained]`.
> - SiliconRoute immediately routes the task to the NVIDIA RTX GPU (`dml:1`), providing transparent plain-English justification for the decision."

---

### Part 4: Rigorous Hardware Evaluation & Baselines (1:40 – 2:15)

**[Visual: Scroll down to the Final Published Hardware Evaluation card, highlighting the Overall Table, Per-Workload Breakdown, and Cold-Start Rule verification.]**

**Narration:**
> "SiliconRoute's effectiveness is proven through empirical verification across 24 published routing decisions (Decisions 117 to 140 `[metric: decisions_117_140_total]`):
> 
> - **SiliconRoute:** Wins **22 out of 24** decisions `[metric: decisions_117_140_sr_wins]`, achieving **91.7% accuracy** `[metric: decisions_117_140_sr_accuracy_pct]`, with an average regret of only **1.75%** `[metric: decisions_117_140_sr_mean_regret_pct]` and **0.0% P90 regret** `[metric: decisions_117_140_sr_p90_regret_pct]`.
> - **Always-CPU Baseline:** Wins only 15 of 24 `[metric: decisions_117_140_always_cpu_wins]` (62.5% accuracy `[metric: decisions_117_140_always_cpu_accuracy_pct]`) with an average slowdown of **113.06%** `[metric: decisions_117_140_always_cpu_mean_regret_pct]`.
> - **Always-RTX Baseline:** Wins only 9 of 24 `[metric: decisions_117_140_always_rtx_wins]` (37.5% accuracy `[metric: decisions_117_140_always_rtx_accuracy_pct]`) with a massive **304.93% average slowdown** `[metric: decisions_117_140_always_rtx_mean_regret_pct]`.
> - **Fit-Only Router:** Wins 19 of 24 `[metric: decisions_117_140_fit_only_wins]` (79.2% accuracy `[metric: decisions_117_140_fit_only_accuracy_pct]`) with 31.42% regret `[metric: decisions_117_140_fit_only_mean_regret_pct]`.
> 
> Looking at the per-workload breakdown:
> - On **sustained workloads**, SiliconRoute is flawless: **8/8 wins (100%)** `[metric: workload_sustained_sr_wins]` and **0.0% regret** `[metric: workload_sustained_sr_mean_regret_pct]`.
> - On **idle-loaded workloads** where GPU wake latency occurs, SiliconRoute is also **8/8 (100%)** `[metric: workload_idle_loaded_sr_wins]` and **0.0% regret** `[metric: workload_idle_loaded_sr_mean_regret_pct]`.
> - On **cold-start workloads** (first model instantiation), SiliconRoute achieves **6/8 wins (75.0%)** `[metric: workload_cold_start_sr_wins]` with only 5.25% regret `[metric: workload_cold_start_sr_mean_regret_pct]`.
> 
> In the Cold-Start Rule verification below (Decisions 141 to 148 `[metric: cold_start_141_148_total]`), applying the 30% threshold preference for the CPU `[metric: cold_start_rule_threshold_pct]` achieves **6/8 wins** `[metric: cold_start_141_148_sr_wins]` and **3.0% regret** `[metric: cold_start_141_148_sr_mean_regret_pct]`, while an Always-RTX policy fails completely with 0/8 wins `[metric: cold_start_141_148_always_rtx_wins]` and **575.15% average regret** `[metric: cold_start_141_148_always_rtx_mean_regret_pct]`."

---

### Part 5: Architecture & Reproducibility (2:15 – 2:30)

**[Visual: Briefly show `README.md` and `results/final/manifest.json`.]**

**Narration:**
> "SiliconRoute operates entirely on your machine—no cloud telemetry, no proprietary dependencies.
> 
> Built on Python 3.12, FastAPI, ONNX Runtime DirectML, and SQLite with WAL mode, every metric shown today is reproducible from scratch via `scripts/make_final_results.py` and cryptographically tied to database SHA256 `98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5` `[metric: database_sha256]`.
> 
> Thank you for exploring SiliconRoute v1.0."
