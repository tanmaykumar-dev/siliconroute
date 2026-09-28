import sqlite3
import json

con = sqlite3.connect("data/siliconroute.db")

print("=" * 90)
print("AUDITING HISTORICAL GPU RUNS FOR DEVICE IDENTITY INVERSION")
print("=" * 90)

runs = con.execute("""
    SELECT r.id, r.session_id, r.device_id, d.key, d.label, m.name, m.family, r.batch,
           m.flops_per_sample, r.median_ms, r.first_run_ms,
           r.nvml_pstate_start, r.nvml_pstate_end, r.nvml_clock_sm_start_mhz, r.nvml_clock_sm_end_mhz
    FROM run r
    JOIN device d ON r.device_id = d.id
    JOIN aimodel m ON r.ai_model_id = m.id
    WHERE d.kind IN ('igpu', 'dgpu')
    ORDER BY r.id;
""").fetchall()

suspect_runs = []

for r in runs:
    rid, sid, did, dkey, dlabel, mname, mfam, batch, flops_sample, med_ms, first_ms, p_start, p_end, clk_start, clk_end = r
    
    total_flops = (flops_sample or 0) * batch
    implied_gflops = (total_flops / (med_ms * 1e6)) if med_ms > 0 else 0
    
    is_suspect = False
    reasons = []
    
    # 1. Physics check on AMD Radeon 610M (device_id=2 or key='dml:0')
    if did == 2 or dkey == "dml:0":
        if implied_gflops > 600.0:
            is_suspect = True
            reasons.append(f"Implied compute {implied_gflops:.1f} GFLOP/s > 600 GFLOP/s (Radeon peak 563)")
        if clk_end and clk_end > 1200:
            # NVIDIA GPU was active during dml:0 run
            reasons.append(f"NVIDIA clock was {clk_end} MHz during dml:0 run")
            if implied_gflops > 500.0:
                is_suspect = True
                
    # 2. Inversion check on NVIDIA RTX 5070 (device_id=3 or key='dml:1')
    if did == 3 or dkey == "dml:1":
        # Known inverted sessions or unphysically slow RTX runs matching Radeon baseline
        if sid in (158, 167, 168, 170):
            is_suspect = True
            reasons.append(f"Recorded in inverted verification session {sid}")
            
    if is_suspect:
        suspect_runs.append((rid, sid, did, dkey, mname, batch, med_ms, implied_gflops, reasons))

print(f"Total GPU runs audited: {len(runs)}")
print(f"Total suspect runs identified: {len(suspect_runs)}\n")
print(f"{'Run ID':<8} | {'Sess':<6} | {'Dev':<7} | {'Model':<18} | {'B':<3} | {'Med ms':<8} | {'GFLOP/s':<8} | {'Reasons'}")
print("-" * 110)
for s in suspect_runs:
    reason_str = "; ".join(s[8])
    print(f"{s[0]:<8} | {s[1]:<6} | {s[3]:<7} | {s[4]:<18} | {s[5]:<3} | {s[6]:<8.3f} | {s[7]:<8.1f} | {reason_str}")
