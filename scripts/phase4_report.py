"""SiliconRoute Phase 4.1 Ground-Truth Verification Report Generator.

Reads EXCLUSIVELY from:
1. data/siliconroute.db (SQLite)
2. app.api.system.get_system() (Host hardware telemetry)
3. Live idle-gap wake test measuring NVML hardware states directly.

Saves output verbatim to results/phase4_1_report.txt.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, os.path.abspath("."))

from app.api.system import get_system
from app.config import BASE_DIR, DATA_DIR, DB_PATH
RESULTS_DIR = BASE_DIR / "results"
from app.devices import make_session
from app.power import nvml_reader
from app.predictor import calculate_crossover
from sqlmodel import Session, select
from app.db import AIModel, BenchSession, Device, Fit, Run, engine


def build_report() -> str:
    lines: list[str] = []

    def p(text: str = ""):
        lines.append(text)

    p("=" * 100)
    p("SILICONROUTE PHASE 4.1 GROUND-TRUTH REPORT")
    p(f"Generated at: {datetime.now(timezone.utc).isoformat()}")
    p("=" * 100)

    # ---------------------------------------------------------
    # 1. System Hardware (from get_system())
    # ---------------------------------------------------------
    sys_info = get_system()
    p("\n[1] HOST HARDWARE IDENTIFICATION (from /api/system)")
    p("-" * 80)
    p(f"CPU Name:           {sys_info.get('cpu_name')}")
    p(f"Physical / Logical: {sys_info.get('physical_cores')} cores / {sys_info.get('logical_cores')} threads")
    p(f"Installed RAM:      {sys_info.get('ram_gb')} GB")
    p(f"Operating System:   {sys_info.get('os')}")
    p(f"ONNX Runtime:       v{sys_info.get('ort_version')} (Providers: {', '.join(sys_info.get('providers', []))})")
    nvml_info = sys_info.get("nvml", {})
    if nvml_info.get("available"):
        p(f"Discrete GPU(s):    {', '.join(nvml_info.get('devices', []))} (NVML available: Yes)")
    else:
        p(f"Discrete GPU(s):    None or NVML unavailable ({nvml_info.get('reason')})")

    # ---------------------------------------------------------
    # 2. Database Devices (from Device table)
    # ---------------------------------------------------------
    p("\n[2] DATABASE DEVICE REGISTRY (from SQLite device table)")
    p("-" * 80)
    p(f"{'ID':<4} {'Key':<10} {'Kind':<8} {'Provider':<24} {'Available':<10} {'Label / Unavailable Reason'}")
    p("-" * 80)
    with Session(engine) as s:
        devices = s.exec(select(Device).order_by(Device.id)).all()
        for d in devices:
            reason = f" [Unavailable: {d.unavailable_reason}]" if d.unavailable_reason else ""
            p(f"{d.id:<4} {d.key:<10} {d.kind:<8} {d.provider:<24} {str(d.is_available):<10} {d.label}{reason}")

    # ---------------------------------------------------------
    # 3. Model Inventory & Discrepancy Resolution
    # ---------------------------------------------------------
    p("\n[3] MODEL INVENTORY & SPECIFICATIONS (from SQLite aimodel table)")
    p("-" * 80)
    with Session(engine) as s:
        models = s.exec(select(AIModel).order_by(AIModel.id)).all()
        runs_all = s.exec(select(Run)).all()
        run_model_ids = {r.ai_model_id for r in runs_all}

        active_models = [m for m in models if m.id in run_model_ids]
        unreferenced_models = [m for m in models if m.id not in run_model_ids]

        p(f"Total entries in aimodel table: {len(models)}")
        p(f"Models with benchmark runs:      {len(active_models)} (all synthetic models)")
        p(f"Unreferenced scanned duplicates: {len(unreferenced_models)} (file-scanned copies with no runs)")
        p("")
        p(f"{'ID':<4} {'Name':<18} {'Family':<8} {'Source':<10} {'Params':<12} {'FLOPs/sample':<16} {'Weights (MB)':<12} {'Runs'}")
        p("-" * 95)
        for m in models:
            m_runs = sum(1 for r in runs_all if r.ai_model_id == m.id)
            flops_str = f"{m.flops_per_sample:,.0f}" if m.flops_per_sample is not None else "None"
            p(f"{m.id:<4} {m.name:<18} {m.family:<8} {m.source:<10} {m.params:<12,d} {flops_str:<16} {m.weight_bytes/(1024*1024):<12.3f} {m_runs}")

    # ---------------------------------------------------------
    # 4. Database Run Provenance
    # ---------------------------------------------------------
    p("\n[4] DATABASE RUN COUNTS & PROVENANCE (from SQLite run & benchsession tables)")
    p("-" * 80)
    with Session(engine) as s:
        total_runs = len(runs_all)
        p(f"Total benchmark runs in database: {total_runs}")

        # Group by device
        dev_map = {d.id: d.key for d in devices}
        p("\nRuns per device key:")
        from collections import Counter
        dev_counts = Counter(dev_map.get(r.device_id, "unknown") for r in runs_all)
        for k in sorted(dev_counts.keys()):
            p(f"  {k:<10}: {dev_counts[k]} runs")

        # Group by session
        p("\nRuns per benchmark session:")
        sessions = s.exec(select(BenchSession).order_by(BenchSession.id)).all()
        for sess in sessions:
            sess_runs = sum(1 for r in runs_all if r.session_id == sess.id)
            note_str = f" - {sess.notes}" if sess.notes else ""
            p(f"  Session {sess.id:<4} (status: {sess.status:<7}, kind: {sess.kind:<8}, runs: {sess_runs:<3}){note_str}")

    # ---------------------------------------------------------
    # 5. Physics Sanity Check: Implied Compute & Bandwidth
    # ---------------------------------------------------------
    p("\n[5] PHYSICS CHECK: FLOPs, PARAMS, IMPLIED GFLOP/s & GB/s PER RUN")
    p("-" * 105)
    p("Formulae from SPEC Section 3:")
    p("  MLP:  FLOPs = 2 * L * W^2, Params = L * W^2, Weights = Params * 4 bytes")
    p("  Conv: FLOPs = 2 * L * H * W * C^2 * 9 (H=W=64), Params = L * C^2 * 9, Weights = Params * 4 bytes")
    p("  Implied GFLOP/s = (flops_per_sample * batch) / (median_ms * 1e6)")
    p("  Implied Weight GB/s = (weight_bytes) / (median_ms * 1e6)")
    p("-" * 105)
    p(f"{'RunID':<6} {'Model':<16} {'Chip':<6} {'B':<3} {'Median(ms)':<11} {'FLOPs/spl':<14} {'GFLOP/s':<11} {'Weight GB/s':<12} {'Physical Note'}")
    p("-" * 105)

    with Session(engine) as s:
        # Show sample of runs across devices, specifically the conv models and large MLPs
        conv_and_large_runs = s.exec(
            select(Run)
            .where(Run.session_id.in_([85, 86]))
            .order_by(Run.ai_model_id, Run.batch, Run.device_id)
        ).all()

        for r in conv_and_large_runs:
            m = s.exec(select(AIModel).where(AIModel.id == r.ai_model_id)).first()
            d = s.exec(select(Device).where(Device.id == r.device_id)).first()
            if not m or not d or not m.flops_per_sample or not r.median_ms:
                continue

            total_flops = m.flops_per_sample * r.batch
            implied_gflops = total_flops / (r.median_ms * 1e6)
            implied_gb_s = m.weight_bytes / (r.median_ms * 1e6)

            # Physical commentary
            note = ""
            if d.key == "dml:0":
                # Radeon 610M peak is ~563 GFLOP/s
                pct_peak = (implied_gflops / 563.2) * 100
                note = f"{pct_peak:.0f}% of 610M peak (~563 GFLOP/s)"
            elif d.key == "dml:1":
                # RTX 5070 FP32 peak is ~15-20 TFLOP/s (boost), fitted ~3.7 TFLOP/s
                note = f"{implied_gflops/1000.0:.2f} TFLOP/s"
            elif d.key == "cpu":
                note = f"{implied_gflops:.1f} GFLOP/s CPU"

            p(f"{r.id:<6} {m.name:<16} {d.key:<6} {r.batch:<3} {r.median_ms:<11.3f} {m.flops_per_sample:<14.0f} {implied_gflops:<11.1f} {implied_gb_s:<12.2f} {note}")

    # ---------------------------------------------------------
    # 6. Real Extended Benchmark Table (Session 85)
    # ---------------------------------------------------------
    p("\n[6] EXTENDED BENCHMARK RUNS STORED IN DB (Session 85 - Real Measurements)")
    p("-" * 95)
    p(f"{'RunID':<6} {'Model':<16} {'B':<3} {'Chip':<6} {'Median(ms)':<12} {'P10-P90 (ms)':<16} {'CI rel':<8} {'First Run(ms)':<14} {'Thput(/s)'}")
    p("-" * 95)
    with Session(engine) as s:
        s85_runs = s.exec(select(Run).where(Run.session_id == 85).order_by(Run.id)).all()
        for r in s85_runs:
            m = s.exec(select(AIModel).where(AIModel.id == r.ai_model_id)).first()
            d = s.exec(select(Device).where(Device.id == r.device_id)).first()
            p10_p90 = f"{r.p10_ms:.3f}-{r.p90_ms:.3f}"
            first_ms = f"{r.first_run_ms:.3f}" if r.first_run_ms else "N/A"
            p(f"{r.id:<6} {m.name:<16} {r.batch:<3} {d.key:<6} {r.median_ms:<12.3f} {p10_p90:<16} {r.ci_rel or 0:<8.4f} {first_ms:<14} {r.throughput_per_s:<10.1f}")

    # ---------------------------------------------------------
    # 7. Live API Benchmark Runs (Session 86)
    # ---------------------------------------------------------
    p("\n[7] LIVE API RE-RUN ON mlp-3072w-4l B=1 (Session 86)")
    p("-" * 95)
    with Session(engine) as s:
        s86_runs = s.exec(select(Run).where(Run.session_id == 86).order_by(Run.id)).all()
        for r in s86_runs:
            m = s.exec(select(AIModel).where(AIModel.id == r.ai_model_id)).first()
            d = s.exec(select(Device).where(Device.id == r.device_id)).first()
            p(f"Run {r.id}: {m.name} on {d.key} ({d.label}) | Batch={r.batch} | Warmup={r.warmup_runs}, Runs={r.timed_runs}")
            p(f"  Median: {r.median_ms:.3f} ms | P10: {r.p10_ms:.3f} ms | P90: {r.p90_ms:.3f} ms | Spread: {r.spread:.4f} | CI_rel: {r.ci_rel:.4f}")
            p(f"  First Run: {r.first_run_ms:.3f} ms | Session Create: {r.session_create_ms:.1f} ms | Throughput: {r.throughput_per_s:.1f} /s")
            p(f"  Provider Used: {r.provider_used} (mismatch={r.provider_mismatch}) | Output Matches CPU: {r.output_matches_cpu}")
            if r.nvml_clock_sm_start_mhz is not None:
                p(f"  NVML SM Clock: {r.nvml_clock_sm_start_mhz} MHz -> {r.nvml_clock_sm_end_mhz} MHz | P-state: {r.nvml_pstate_start} -> {r.nvml_pstate_end}")

    # ---------------------------------------------------------
    # 8. Active Hardware Predictor Fits & Bootstrap 95% CIs
    # ---------------------------------------------------------
    p("\n[8] ACTIVE HARDWARE PREDICTOR FITS & 500-ROUND BOOTSTRAP CIs (from SQLite fit table)")
    p("-" * 95)
    with Session(engine) as s:
        fits = s.exec(select(Fit).where(Fit.is_active == True).order_by(Fit.device_id)).all()
        for f in fits:
            d = s.exec(select(Device).where(Device.id == f.device_id)).first()
            p(f"\nDevice: {d.key} ({d.label})")
            p(f"  Model Form:          {f.model_form}")
            p(f"  Trained On:          {f.n_samples} genuine runs (LOO MAPE = {f.loo_mape_pct:.2f}%, R2_log = {f.r2_log:.4f})")
            p(f"  Fitted t0:           {f.t0_ms:.4f} ms")
            p(f"  Fitted Compute:      {f.compute_gflops:.1f} GFLOP/s ({f.compute_gflops/1000.0:.2f} TFLOP/s)")
            p(f"  Fitted Bandwidth:    {f.bandwidth_gb_s:.2f} GB/s" if f.bandwidth_gb_s else "  Fitted Bandwidth:    None")
            if f.bandwidth_dram_gb_s:
                p(f"  Fitted DRAM BW:      {f.bandwidth_dram_gb_s:.2f} GB/s")

            # Parse bootstrap CIs from notes
            if f.notes:
                try:
                    notes_dict = json.loads(f.notes)
                    param_cis = notes_dict.get("parameter_cis", {})
                    p("  Bootstrap 95% Confidence Intervals (500 resamples):")
                    for p_name, p_data in param_cis.items():
                        rel_half = p_data.get("rel_half_width", 0) * 100
                        p(f"    - {p_name:<20}: [{p_data.get('ci_low')}, {p_data.get('ci_high')}] (Median: {p_data.get('median')}, +/-{rel_half:.1f}%) -> {p_data.get('status')}")
                except Exception:
                    p(f"  Notes: {f.notes}")

    # ---------------------------------------------------------
    # 9. Crossover Evaluation (CPU vs RTX 5070)
    # ---------------------------------------------------------
    p("\n[9] CROSSOVER EVALUATION: CPU vs NVIDIA RTX 5070 (from active fits)")
    p("-" * 80)
    with Session(engine) as s:
        dev_cpu = s.exec(select(Device).where(Device.key == "cpu")).first()
        dev_dml1 = s.exec(select(Device).where(Device.key == "dml:1")).first()

        for b in [1, 8, 32]:
            cross_mlp = calculate_crossover(s, dev_cpu.id, dev_dml1.id, "mlp", b)
            pt_mlp = cross_mlp.get("crossover")
            if pt_mlp:
                p(f"MLP Batch {b:2d}: Crossover at Width = {pt_mlp['width']:<5d} ({pt_mlp['params']:,d} params, {pt_mlp['params']*4/(1024*1024):.2f} MB)")
                p(f"              CPU pred: {pt_mlp['pred_a_ms']:.4f} ms vs RTX 5070 pred: {pt_mlp['pred_b_ms']:.4f} ms (Switched to {pt_mlp['switched_to']})")
            else:
                p(f"MLP Batch {b:2d}: {cross_mlp.get('summary')}")

            cross_conv = calculate_crossover(s, dev_cpu.id, dev_dml1.id, "conv", b)
            pt_conv = cross_conv.get("crossover")
            if pt_conv:
                p(f"Conv Batch {b:2d}: Crossover at Channels = {pt_conv['width']:<3d} ({pt_conv['params']:,d} params, {pt_conv['params']*4/(1024*1024):.3f} MB)")
                p(f"               CPU pred: {pt_conv['pred_a_ms']:.4f} ms vs RTX 5070 pred: {pt_conv['pred_b_ms']:.4f} ms (Switched to {pt_conv['switched_to']})")
            else:
                p(f"Conv Batch {b:2d}: {cross_conv.get('summary')}")

    # ---------------------------------------------------------
    # 10. Live Idle-Gap Wake Test
    # ---------------------------------------------------------
    p("\n[10] LIVE IDLE-GAP GPU WAKE TEST ON NVIDIA RTX 5070 (dml:1)")
    p("-" * 80)
    p("Testing cold/warm inference latencies across idle intervals measuring NVML clock and power.")
    with Session(engine) as s:
        # We test both mlp-1024w-4l and mlp-3072w-4l explicitly so there is ZERO ambiguity
        m1024 = s.exec(select(AIModel).where(AIModel.name == "mlp-1024w-4l")).first()
        m3072 = s.exec(select(AIModel).where(AIModel.name == "mlp-3072w-4l")).first()
        dev_dml1 = s.exec(select(Device).where(Device.key == "dml:1")).first()

        for model in [m1024, m3072]:
            p(f"\n--- Testing {model.name} (B=1) on {dev_dml1.label} ---")
            sess = make_session(model.path, "DmlExecutionProvider", device_id=1)
            from app.benchmark import prepare_input_tensor
            inp_name, inp_data = prepare_input_tensor(model, 1, sess)

            # Warmup
            for _ in range(50):
                sess.run(None, {inp_name: inp_data})

            # Steady-state warm median
            warm_timings = []
            for _ in range(20):
                t0 = time.perf_counter()
                sess.run(None, {inp_name: inp_data})
                warm_timings.append((time.perf_counter() - t0) * 1000.0)
            warm_median = float(sorted(warm_timings)[len(warm_timings)//2])

            p(f"Active Steady-State Median: {warm_median:.3f} ms")
            p(f"{'Idle Gap':<10} {'P-State':<9} {'Clock (MHz)':<13} {'Power (W)':<11} {'First Run (ms)':<16} {'Wake Penalty (ms)'}")
            p("-" * 75)

            for gap in [0.5, 2.0, 10.0]:
                time.sleep(gap)
                # Read NVML state right before executing
                metrics = nvml_reader.read_metrics()
                pstate = metrics.get("gpu_pstate")
                clock_mhz = metrics.get("gpu_clock_sm_mhz")
                power_w = metrics.get("gpu_power_w")

                t0 = time.perf_counter()
                sess.run(None, {inp_name: inp_data})
                t_first = (time.perf_counter() - t0) * 1000.0
                penalty = t_first - warm_median
                pstate_str = f"P{pstate}" if pstate is not None else "N/A"
                clock_str = f"{clock_mhz or 'N/A'}"
                power_str = f"{power_w:.1f}" if power_w is not None else "N/A"
                p(f"{gap:<10.1f} {pstate_str:<9} {clock_str:<13} {power_str:<11} {t_first:<16.3f} {penalty:+.3f} ms ({t_first/warm_median:.1f}x)")

    p("\n" + "=" * 100)
    p("END OF SILICONROUTE PHASE 4.1 GROUND-TRUTH REPORT")
    p("=" * 100)

    report_content = "\n".join(lines)
    return report_content


if __name__ == "__main__":
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / "phase4_1_report.txt"

    print("Generating Phase 4.1 ground-truth report...")
    content = build_report()
    out_file.write_text(content, encoding="utf-8")
    print(f"Report written to: {out_file.as_posix()}\n")
    print(content)
