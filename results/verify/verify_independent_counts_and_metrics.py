import json
import sqlite3
import numpy as np

con = sqlite3.connect("data/siliconroute.db")

print("=" * 80)
print("INDEPENDENT RECOMPUTATION: RUN COUNTS PER DEVICE AND SESSION")
print("=" * 80)

# Run counts per device and session
rows = con.execute("""
    SELECT s.id, s.name, d.id, d.key, d.name, COUNT(r.id)
    FROM benchmarksession s
    JOIN run r ON r.session_id = s.id
    JOIN device d ON r.device_id = d.id
    GROUP BY s.id, d.id
    ORDER BY s.id, d.id;
""").fetchall()

print(f"{'Session ID':<12} | {'Session Name':<28} | {'Dev ID':<7} | {'Dev Key':<8} | {'Runs':<6}")
print("-" * 75)
total_runs = 0
for sid, sname, did, dkey, dname, count in rows:
    total_runs += count
    print(f"{sid:<12} | {sname:<28} | {did:<7} | {dkey:<8} | {count:<6}")
print("-" * 75)
print(f"Total runs across all sessions: {total_runs}")

# Total runs check
all_runs_count = con.execute("SELECT COUNT(*) FROM run;").fetchone()[0]
print(f"Total runs in Run table: {all_runs_count} -> {'MATCH' if all_runs_count == total_runs else 'MISMATCH'}\n")

print("=" * 80)
print("INDEPENDENT RECOMPUTATION: DECISIONS 69 TO 92 ACCURACY AND REGRETS")
print("=" * 80)

# Fetch decisions 69-92
dec_rows = con.execute("""
    SELECT id, chosen_device_id, was_best, regret_pct, context_json
    FROM decision
    WHERE id BETWEEN 69 AND 92
    ORDER BY id;
""").fetchall()

n = len(dec_rows)
assert n == 24, f"Expected 24 decisions, got {n}"

router_wins = 0
router_regrets = []

cpu_wins = 0
cpu_regrets = []

rtx_wins = 0
rtx_regrets = []

fit_wins = 0
fit_regrets = []

for did, chosen_dev_id, was_best, regret_pct, ctx_json in dec_rows:
    ctx = json.loads(ctx_json)
    m_times = {int(k): float(v) for k, v in ctx["measured_times_ms"].items()}
    best_time = min(m_times.values())
    
    # 1. Router
    # was_best should be 1 if measured time of chosen_device_id is within 1e-4 of best_time
    chosen_measured = m_times[chosen_dev_id]
    r_is_best = chosen_measured <= best_time + 1e-4
    r_regret = ((chosen_measured - best_time) / max(best_time, 1e-4)) * 100.0
    
    # Sanity check against stored values
    assert (was_best == 1) == r_is_best, f"Mismatch in was_best for dec {did}"
    assert abs(regret_pct - r_regret) < 0.05, f"Mismatch in regret for dec {did}: stored={regret_pct}, calc={r_regret}"
    
    if r_is_best:
        router_wins += 1
    router_regrets.append(r_regret)
    
    # 2. Always-CPU (Device 1)
    if 1 in m_times:
        t_cpu = m_times[1]
        is_cpu_best = t_cpu <= best_time + 1e-4
        cpu_reg = ((t_cpu - best_time) / max(best_time, 1e-4)) * 100.0
        if is_cpu_best:
            cpu_wins += 1
        cpu_regrets.append(cpu_reg)
        
    # 3. Always-RTX (Device 3)
    if 3 in m_times:
        t_rtx = m_times[3]
        is_rtx_best = t_rtx <= best_time + 1e-4
        rtx_reg = ((t_rtx - best_time) / max(best_time, 1e-4)) * 100.0
        if is_rtx_best:
            rtx_wins += 1
        rtx_regrets.append(rtx_reg)
        
    # 4. Fit-Only Router
    # Choose candidate with minimum fit_latency_ms
    cands = ctx.get("candidates", [])
    valid_cands = [c for c in cands if c.get("fit_latency_ms") is not None]
    if valid_cands:
        best_fit_cand = min(valid_cands, key=lambda c: c["fit_latency_ms"])
        fit_chosen_dev = best_fit_cand["device_id"]
        t_fit = m_times.get(fit_chosen_dev, 999999.0)
        is_fit_best = t_fit <= best_time + 1e-4
        fit_reg = ((t_fit - best_time) / max(best_time, 1e-4)) * 100.0
        if is_fit_best:
            fit_wins += 1
        fit_regrets.append(fit_reg)

def pct(k, total):
    return round((k / total) * 100.0, 1)

print(f"{'Strategy':<18} | {'Wins':<6} | {'Total':<6} | {'Calc %':<8} | {'Reported %':<11} | {'Mean Regret %':<14} | {'P90 Regret %':<14}")
print("-" * 90)

# Router
r_pct = pct(router_wins, n)
r_mean = round(float(np.mean(router_regrets)), 2)
r_p90 = round(float(np.percentile(router_regrets, 90)), 2)
print(f"{'SiliconRoute':<18} | {router_wins:<6} | {n:<6} | {r_pct:<8} | {'70.8%':<11} | {r_mean:<14} | {r_p90:<14}")
assert r_pct == 70.8
assert router_wins == 17

# Always-CPU
cpu_pct = pct(cpu_wins, n)
cpu_mean = round(float(np.mean(cpu_regrets)), 2)
cpu_p90 = round(float(np.percentile(cpu_regrets, 90)), 2)
print(f"{'Always-CPU':<18} | {cpu_wins:<6} | {n:<6} | {cpu_pct:<8} | {'66.7%':<11} | {cpu_mean:<14} | {cpu_p90:<14}")
assert cpu_pct == 66.7
assert cpu_wins == 16

# Always-RTX
rtx_pct = pct(rtx_wins, n)
rtx_mean = round(float(np.mean(rtx_regrets)), 2)
rtx_p90 = round(float(np.percentile(rtx_regrets, 90)), 2)
print(f"{'Always-RTX':<18} | {rtx_wins:<6} | {n:<6} | {rtx_pct:<8} | {'0.0%':<11} | {rtx_mean:<14} | {rtx_p90:<14}")
assert rtx_pct == 0.0
assert rtx_wins == 0

# Fit-Only
fit_pct = pct(fit_wins, n)
fit_mean = round(float(np.mean(fit_regrets)), 2)
fit_p90 = round(float(np.percentile(fit_regrets, 90)), 2)
print(f"{'Fit-Only Router':<18} | {fit_wins:<6} | {n:<6} | {fit_pct:<8} | {'50.0%':<11} | {fit_mean:<14} | {fit_p90:<14}")
assert fit_pct == 50.0
assert fit_wins == 12

print("\nALL RATIOS (k/n) AND PERCENTAGES MATCH EXACTLY!")
