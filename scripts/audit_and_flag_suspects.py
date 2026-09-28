import sqlite3

con = sqlite3.connect("data/siliconroute.db")

print("=" * 80)
print("AUDITING RUNS FOR IDENTITY SUSPECT FLAGGING")
print("=" * 80)

rows = con.execute("""
    SELECT r.id, r.session_id, r.device_id, d.key, m.name, r.batch, r.median_ms,
           m.flops_per_sample, r.nvml_clock_sm_end_mhz
    FROM run r
    JOIN device d ON r.device_id = d.id
    JOIN aimodel m ON r.ai_model_id = m.id
    ORDER BY r.id;
""").fetchall()

suspect_ids = []

for rid, sid, did, dkey, mname, batch, med_ms, flops_sample, clk_end in rows:
    total_flops = (flops_sample or 0) * batch
    gflops = (total_flops / (med_ms * 1e6)) if med_ms > 0 else 0
    
    flag = False
    reason = ""
    
    # 1. Physics: dml:0 > 600 GFLOP/s
    if did == 2 or dkey == "dml:0":
        if gflops > 600.0:
            flag = True
            reason = f"dml:0 implied compute {gflops:.1f} GFLOP/s > 600 GFLOP/s peak"
            
    # 2. Inverted verification sessions
    if sid in (158, 167, 168, 170):
        if dkey in ("dml:0", "dml:1") or did in (2, 3):
            flag = True
            reason = f"recorded in inverted session {sid}"
            
    if flag:
        suspect_ids.append((rid, sid, dkey, mname, batch, med_ms, gflops, reason))

print(f"Found {len(suspect_ids)} suspect runs.")
print(f"{'Run ID':<8} | {'Sess':<6} | {'Dev':<6} | {'Model':<16} | {'B':<3} | {'Med ms':<8} | {'GFLOP/s':<8} | {'Reason'}")
print("-" * 95)
for s in suspect_ids:
    print(f"{s[0]:<8} | {s[1]:<6} | {s[2]:<6} | {s[3]:<16} | {s[4]:<3} | {s[5]:<8.3f} | {s[6]:<8.1f} | {s[7]}")

# Apply update
cur = con.cursor()
for s in suspect_ids:
    cur.execute("UPDATE run SET identity_suspect = 1 WHERE id = ?;", (s[0],))

con.commit()

# Verify count of flagged runs
flagged_count = con.execute("SELECT COUNT(*) FROM run WHERE identity_suspect = 1;").fetchone()[0]
print(f"\nTotal runs marked identity_suspect=1 in database: {flagged_count}")
con.close()
