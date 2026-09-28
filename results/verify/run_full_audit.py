import json
import sqlite3
import numpy as np
from pathlib import Path

con = sqlite3.connect("data/siliconroute.db")

print("=" * 100)
print("1. RUN COUNTS PER DEVICE AND BENCHMARK SESSION")
print("=" * 100)
rows = con.execute("""
    SELECT s.id, COALESCE(s.notes, s.kind), d.id, d.key, d.label, COUNT(r.id)
    FROM benchsession s
    JOIN run r ON r.session_id = s.id
    JOIN device d ON r.device_id = d.id
    GROUP BY s.id, d.id
    ORDER BY s.id, d.id;
""").fetchall()

print(f"{'Session ID':<12} | {'Description':<35} | {'Dev ID':<7} | {'Dev Key':<8} | {'Runs':<6}")
print("-" * 80)
total_session_runs = 0
for sid, desc, did, dkey, dlabel, count in rows:
    total_session_runs += count
    desc_str = (desc[:32] + "...") if desc and len(desc) > 35 else (desc or "")
    print(f"{sid:<12} | {desc_str:<35} | {did:<7} | {dkey:<8} | {count:<6}")
print("-" * 80)
print(f"Total session runs: {total_session_runs}")

total_runs_db = con.execute("SELECT COUNT(*) FROM run;").fetchone()[0]
print(f"Total rows in Run table: {total_runs_db}")
assert total_session_runs == total_runs_db, "Mismatch between session runs and total runs!"

null_session_runs = con.execute("SELECT COUNT(*) FROM run WHERE session_id IS NULL;").fetchone()[0]
print(f"Runs with NULL session_id: {null_session_runs}")
assert null_session_runs == 0

print("\n" + "=" * 100)
print("2. PER-WORKLOAD INDEPENDENT EVALUATION: DECISIONS 69 TO 92")
print("=" * 100)

dec_rows = con.execute("""
    SELECT d.id, d.ai_model_id, m.name, d.batch, d.chosen_device_id, d.was_best, d.regret_pct, d.context_json, d.candidates_json
    FROM decision d
    JOIN aimodel m ON d.ai_model_id = m.id
    WHERE d.id BETWEEN 69 AND 92
    ORDER BY d.id;
""").fetchall()

workloads = ["sustained", "idle_loaded", "cold_start"]
stats = {w: {
    "count": 0,
    "router": {"wins": 0, "regrets": []},
    "cpu": {"wins": 0, "regrets": []},
    "rtx": {"wins": 0, "regrets": []},
    "fit": {"wins": 0, "regrets": []},
} for w in workloads}

overall = {
    "count": 0,
    "router": {"wins": 0, "regrets": []},
    "cpu": {"wins": 0, "regrets": []},
    "rtx": {"wins": 0, "regrets": []},
    "fit": {"wins": 0, "regrets": []},
}

wrong_decisions = []

for did, mid, mname, batch, chosen_dev, was_best, regret_pct, ctx_json, cands_json in dec_rows:
    ctx = json.loads(ctx_json)
    cands = json.loads(cands_json) if cands_json else []
    wl = ctx.get("workload", "sustained")
    m_times = {int(k): float(v) for k, v in ctx["measured_times_ms"].items()}
    best_time = min(m_times.values())
    best_dev = [k for k, v in m_times.items() if abs(v - best_time) <= 1e-4][0]
    
    # 1. Router
    chosen_time = m_times[chosen_dev]
    r_is_best = chosen_time <= best_time + 1e-4
    r_regret = ((chosen_time - best_time) / max(best_time, 1e-4)) * 100.0
    
    stats[wl]["count"] += 1
    overall["count"] += 1
    if r_is_best:
        stats[wl]["router"]["wins"] += 1
        overall["router"]["wins"] += 1
    stats[wl]["router"]["regrets"].append(r_regret)
    overall["router"]["regrets"].append(r_regret)
    
    # Record if wrong
    if not r_is_best:
        pred_times = {c["device_id"]: c.get("effective_latency_ms", c.get("predicted_latency_ms")) for c in cands}
        wrong_decisions.append({
            "id": did,
            "model": mname,
            "batch": batch,
            "workload": wl,
            "chosen_dev": chosen_dev,
            "best_dev": best_dev,
            "chosen_time": chosen_time,
            "best_time": best_time,
            "regret_pct": r_regret,
            "measured_times": m_times,
            "pred_times": pred_times,
            "reason": ctx.get("reason", "")
        })
        
    # 2. Always-CPU (Dev 1)
    if 1 in m_times:
        t_cpu = m_times[1]
        cpu_best = t_cpu <= best_time + 1e-4
        cpu_reg = ((t_cpu - best_time) / max(best_time, 1e-4)) * 100.0
        if cpu_best:
            stats[wl]["cpu"]["wins"] += 1
            overall["cpu"]["wins"] += 1
        stats[wl]["cpu"]["regrets"].append(cpu_reg)
        overall["cpu"]["regrets"].append(cpu_reg)
        
    # 3. Always-RTX (Dev 3)
    if 3 in m_times:
        t_rtx = m_times[3]
        rtx_best = t_rtx <= best_time + 1e-4
        rtx_reg = ((t_rtx - best_time) / max(best_time, 1e-4)) * 100.0
        if rtx_best:
            stats[wl]["rtx"]["wins"] += 1
            overall["rtx"]["wins"] += 1
        stats[wl]["rtx"]["regrets"].append(rtx_reg)
        overall["rtx"]["regrets"].append(rtx_reg)
        
    # 4. Fit-Only
    valid_cands = [c for c in cands if c.get("fit_latency_ms") is not None]
    if valid_cands:
        fit_choice = min(valid_cands, key=lambda c: c["fit_latency_ms"])["device_id"]
        t_fit = m_times.get(fit_choice, 999999.0)
        fit_best = t_fit <= best_time + 1e-4
        fit_reg = ((t_fit - best_time) / max(best_time, 1e-4)) * 100.0
        if fit_best:
            stats[wl]["fit"]["wins"] += 1
            overall["fit"]["wins"] += 1
        stats[wl]["fit"]["regrets"].append(fit_reg)
        overall["fit"]["regrets"].append(fit_reg)

def fmt_stat(wins, total, regrets):
    acc = round((wins / total) * 100.0, 1) if total > 0 else 0.0
    mean_reg = round(float(np.mean(regrets)), 2) if regrets else 0.0
    p90_reg = round(float(np.percentile(regrets, 90)), 2) if regrets else 0.0
    return f"{wins}/{total} ({acc}%)", f"{mean_reg}%", f"{p90_reg}%"

print(f"{'Workload':<14} | {'Policy':<16} | {'Accuracy (k/n)':<18} | {'Mean Regret':<14} | {'P90 Regret':<14}")
print("-" * 85)

for wl in workloads:
    wdata = stats[wl]
    cnt = wdata["count"]
    for pol_name, pkey in [("SiliconRoute", "router"), ("Always-CPU", "cpu"), ("Always-RTX", "rtx"), ("Fit-Only", "fit")]:
        acc_str, mean_str, p90_str = fmt_stat(wdata[pkey]["wins"], cnt, wdata[pkey]["regrets"])
        print(f"{wl:<14} | {pol_name:<16} | {acc_str:<18} | {mean_str:<14} | {p90_str:<14}")
    print("-" * 85)

# Overall
print("OVERALL (ALL 24 DECISIONS):")
for pol_name, pkey in [("SiliconRoute", "router"), ("Always-CPU", "cpu"), ("Always-RTX", "rtx"), ("Fit-Only", "fit")]:
    acc_str, mean_str, p90_str = fmt_stat(overall[pkey]["wins"], overall["count"], overall[pkey]["regrets"])
    print(f"{'overall':<14} | {pol_name:<16} | {acc_str:<18} | {mean_str:<14} | {p90_str:<14}")
print("-" * 85)

print("\n" + "=" * 100)
print(f"3. DECISIONS SILICONROUTE GOT WRONG ({len(wrong_decisions)} total)")
print("=" * 100)

dev_names = {1: "CPU", 2: "Radeon 610M (dml:0)", 3: "RTX 5070 (dml:1)"}

for wd in wrong_decisions:
    print(f"\nDecision #{wd['id']}: Model={wd['model']}, Batch={wd['batch']}, Workload={wd['workload']}")
    print(f"  Chosen: Device {wd['chosen_dev']} ({dev_names.get(wd['chosen_dev'])}) -> Measured: {wd['chosen_time']:.4f} ms")
    print(f"  Best:   Device {wd['best_dev']} ({dev_names.get(wd['best_dev'])}) -> Measured: {wd['best_time']:.4f} ms")
    print(f"  Regret: {wd['regret_pct']:.2f}%")
    print("  All Measured Times:")
    for did, tm in sorted(wd["measured_times"].items()):
        print(f"    - Dev {did} ({dev_names.get(did)}): {tm:.4f} ms")
    print("  Predicted Times:")
    for did, tm in sorted(wd["pred_times"].items()):
        val_str = f"{tm:.4f} ms" if tm is not None else "None"
        print(f"    - Dev {did} ({dev_names.get(did)}): {val_str}")

print("\n" + "=" * 100)
print("4. PHYSICS SANITY: IMPLIED GFLOP/s AND GB/s ACROSS ALL RUNS")
print("=" * 100)

# Hardware Datasheet Limits
# CPU (Ryzen 9 8940HX): FP32 peak ~1400 GFLOP/s (datasheet, not measured); DRAM peak ~83.2 GB/s (datasheet, not measured)
# Radeon 610M (dml:0): FP32 peak ~563 GFLOP/s (datasheet, not measured); DRAM peak ~83.2 GB/s (datasheet, not measured)
# RTX 5070 Laptop (dml:1): FP32 peak ~25000 GFLOP/s (datasheet, not measured); VRAM peak ~320 GB/s (datasheet, not measured)

all_runs = con.execute("""
    SELECT r.id, r.session_id, d.id, d.key, d.label, m.name, m.family, r.batch,
           m.flops_per_sample, m.weight_bytes, r.median_ms
    FROM run r
    JOIN device d ON r.device_id = d.id
    JOIN aimodel m ON r.ai_model_id = m.id
    ORDER BY r.id;
""").fetchall()

exceeding_runs = []
device_peaks = {
    1: {"name": "CPU (Ryzen 9 8940HX)", "peak_gflops": 1400.0, "peak_gb_s": 83.2},
    2: {"name": "iGPU (Radeon 610M)", "peak_gflops": 563.0, "peak_gb_s": 83.2},
    3: {"name": "dGPU (RTX 5070)", "peak_gflops": 25000.0, "peak_gb_s": 320.0},
}

max_measured = {did: {"max_gflops": 0.0, "max_gb_s": 0.0, "gflops_run": None, "gb_s_run": None} for did in device_peaks}

for rid, sid, did, dkey, dlabel, mname, mfam, batch, flops_sample, weight_bytes, med_ms in all_runs:
    if med_ms <= 0:
        continue
    total_flops = flops_sample * batch
    implied_gflops = total_flops / (med_ms * 1e6)
    implied_gb_s = weight_bytes / (med_ms * 1e6)
    
    dp = device_peaks.get(did)
    if dp:
        if implied_gflops > max_measured[did]["max_gflops"]:
            max_measured[did]["max_gflops"] = implied_gflops
            max_measured[did]["gflops_run"] = (rid, mname, batch, med_ms)
        if implied_gb_s > max_measured[did]["max_gb_s"]:
            max_measured[did]["max_gb_s"] = implied_gb_s
            max_measured[did]["gb_s_run"] = (rid, mname, batch, med_ms)
            
        if implied_gflops > dp["peak_gflops"]:
            exceeding_runs.append((rid, sid, dp["name"], mname, batch, "GFLOP/s", implied_gflops, dp["peak_gflops"]))
        if implied_gb_s > dp["peak_gb_s"]:
            # Note: weight_bytes / t_ms can exceed external DRAM bandwidth if weights reside in on-chip SRAM/L2/L3 cache!
            exceeding_runs.append((rid, sid, dp["name"], mname, batch, "GB/s (Cache hit hypothesis)", implied_gb_s, dp["peak_gb_s"]))

print("MAX MEASURED THROUGHPUT PER CHIP:")
for did, dp in device_peaks.items():
    mm = max_measured[did]
    print(f"Device {did} ({dp['name']}):")
    print(f"  Max Implied Compute: {mm['max_gflops']:.2f} GFLOP/s (Datasheet Peak: {dp['peak_gflops']} GFLOP/s [datasheet, not measured])")
    print(f"    at Run #{mm['gflops_run'][0]}: {mm['gflops_run'][1]} B={mm['gflops_run'][2]} ({mm['gflops_run'][3]:.4f} ms)")
    print(f"  Max Implied Memory:  {mm['max_gb_s']:.2f} GB/s (Datasheet Peak DRAM: {dp['peak_gb_s']} GB/s [datasheet, not measured])")
    print(f"    at Run #{mm['gb_s_run'][0]}: {mm['gb_s_run'][1]} B={mm['gb_s_run'][2]} ({mm['gb_s_run'][3]:.4f} ms)")

print(f"\nRuns exceeding datasheet compute peaks: {len([e for e in exceeding_runs if 'GFLOP/s' in e[5]])}")
for e in [e for e in exceeding_runs if 'GFLOP/s' in e[5]]:
    print(f"  Run #{e[0]} (Session {e[1]}): {e[2]} on {e[3]} B={e[4]} reached {e[6]:.2f} GFLOP/s > peak {e[7]}")

cache_runs = [e for e in exceeding_runs if "GB/s" in e[5]]
print(f"Runs exceeding DRAM bandwidth (Cache/SRAM hits): {len(cache_runs)}")
if cache_runs:
    print(f"  Sample cache-hit runs: {cache_runs[:3]}")
    print("  Hypothesis: Small models fit entirely inside on-chip cache (CPU 32MB L3, RTX 32MB L2), so effective bandwidth reflects ultra-fast cache rather than external DRAM bus.")
