import json
import subprocess
import sys
from pathlib import Path

claims_path = Path("results/claims_phase5_2.json")
claims = json.loads(claims_path.read_text())

results = []
all_ok = True

print(f"Loaded {len(claims)} claims from {claims_path}\n")

for c in claims:
    cid = c["id"]
    claim_text = c["claim"]
    expected_val = c["value"]
    how_cmd = c["how"]
    
    # Run the exact command using the current python executable
    cmd_exec = how_cmd.replace("python ", f'"{sys.executable}" ')
    proc = subprocess.run(cmd_exec, shell=True, capture_output=True, text=True)
    actual_raw = proc.stdout.strip()
    
    # Evaluate match
    is_exact_type = isinstance(expected_val, int)
    match = False
    actual_num = None
    try:
        actual_num = float(actual_raw)
        if is_exact_type:
            match = (int(actual_num) == expected_val)
        else:
            diff = abs(actual_num - float(expected_val))
            denom = max(abs(float(expected_val)), 1e-6)
            pct_err = (diff / denom) * 100.0
            match = pct_err <= 1.0  # 1% tolerance
    except ValueError:
        match = (actual_raw == str(expected_val))
    
    status = "PASS" if match else "FAIL"
    if not match:
        all_ok = False
        
    print(f"[{status}] {cid}: expected={expected_val}, actual={actual_raw}")
    if not match and proc.stderr:
        print(f"       stderr: {proc.stderr.strip()}")
        
    results.append({
        "id": cid,
        "claim": claim_text,
        "expected": expected_val,
        "actual": actual_raw,
        "status": status,
        "how": how_cmd
    })

print(f"\nOverall claims verification: {'ALL PASS' if all_ok else 'SOME FAILED'}")
