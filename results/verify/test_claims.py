import json
import subprocess
import sys

with open("results/claims_phase5_3.json", "r") as f:
    claims = json.load(f)

for c in claims:
    cmd = c["how"]
    if cmd.startswith("python "):
        cmd = f'"{sys.executable}" ' + cmd[7:]
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    val_str = res.stdout.strip()
    exp_str = str(c["value"])
    # Match check (exact or float 1%)
    try:
        val_f = float(val_str)
        exp_f = float(c["value"])
        if abs(exp_f) < 1e-6:
            match = abs(val_f - exp_f) < 1e-4
        else:
            match = abs(val_f - exp_f) / abs(exp_f) <= 0.01
    except ValueError:
        match = (val_str == exp_str)
    print(f"{c['id']} | expected: {c['value']} | got: {val_str} | match: {match}")
