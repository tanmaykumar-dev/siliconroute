import json
import sqlite3
import numpy as np

con = sqlite3.connect("data/siliconroute.db")

print("Checking 5+ metrics from Phase 5.2 report not in claims file:\n")

# 1. Number of sustained decisions in 69-92 (Report: 8)
r1 = con.execute("""
    SELECT COUNT(*) FROM decision 
    WHERE id BETWEEN 69 AND 92 
    AND json_extract(context_json, '$.workload') = 'sustained';
""").fetchone()[0]
print(f"1. Count of sustained decisions in 69-92: Expected=8, Actual={r1} -> {'PASS' if r1 == 8 else 'FAIL'}")

# 2. Number of sustained wins by SiliconRoute (Report: 4, 50.0%)
r2 = con.execute("""
    SELECT COUNT(*) FROM decision 
    WHERE id BETWEEN 69 AND 92 
    AND json_extract(context_json, '$.workload') = 'sustained'
    AND was_best = 1;
""").fetchone()[0]
print(f"2. Sustained router wins: Expected=4, Actual={r2} -> {'PASS' if r2 == 4 else 'FAIL'}")

# 3. Sustained mean regret (Report: 348.53%)
r3 = con.execute("""
    SELECT ROUND(AVG(regret_pct), 2) FROM decision 
    WHERE id BETWEEN 69 AND 92 
    AND json_extract(context_json, '$.workload') = 'sustained';
""").fetchone()[0]
print(f"3. Sustained mean regret: Expected=348.53%, Actual={r3}% -> {'PASS' if abs(r3 - 348.53) < 0.1 else 'FAIL'}")

# 4. Always-CPU accuracy (Report: 66.7%)
# 16 / 24 * 100
r4 = round((16.0 / 24.0) * 100.0, 1)
print(f"4. Always-CPU accuracy: Expected=66.7%, Actual={r4}% -> {'PASS' if r4 == 66.7 else 'FAIL'}")

# 5. Always-CPU mean regret (Report: 90.07%)
# For each decision, calculate Always-CPU regret: ((t_cpu - t_best) / t_best) * 100
rows = con.execute("SELECT context_json FROM decision WHERE id BETWEEN 69 AND 92;").fetchall()
cpu_regrets = []
rtx_regrets = []
for (ctx_str,) in rows:
    ctx = json.loads(ctx_str)
    m = ctx.get("measured_times_ms", {})
    t_best = min(m.values())
    if "1" in m:
        t_cpu = m["1"]
        cpu_regrets.append(((t_cpu - t_best) / max(t_best, 1e-4)) * 100.0)
    if "3" in m:
        t_rtx = m["3"]
        rtx_regrets.append(((t_rtx - t_best) / max(t_best, 1e-4)) * 100.0)

mean_cpu_regret = round(float(np.mean(cpu_regrets)), 2)
print(f"5. Always-CPU mean regret: Expected=90.07%, Actual={mean_cpu_regret}% -> {'PASS' if abs(mean_cpu_regret - 90.07) < 0.1 else 'FAIL'}")

# 6. Always-RTX mean regret (Report: 421.52%)
mean_rtx_regret = round(float(np.mean(rtx_regrets)), 2)
print(f"6. Always-RTX mean regret: Expected=421.52%, Actual={mean_rtx_regret}% -> {'PASS' if abs(mean_rtx_regret - 421.52) < 0.1 else 'FAIL'}")

# 7. Fit-Only router accuracy (Report: 50.0%)
r7 = round((12.0 / 24.0) * 100.0, 1)
print(f"7. Fit-Only router accuracy: Expected=50.0%, Actual={r7}% -> {'PASS' if r7 == 50.0 else 'FAIL'}")
