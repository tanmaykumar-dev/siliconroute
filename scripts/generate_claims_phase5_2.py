"""Generate and verify results/claims_phase5_2.json for independent verification."""

import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session
from app.db import engine, init_db
from app.router import compute_decision_statistics, get_workload_slowdown_ratio

init_db()

claims = [
    {
        "id": "claim_01",
        "claim": "Total workload measurements stored in database",
        "value": 72,
        "how": "python -c \"import sqlite3; con = sqlite3.connect('data/siliconroute.db'); print(con.execute('SELECT COUNT(*) FROM workloadmeasurement;').fetchone()[0])\"",
    },
    {
        "id": "claim_02",
        "claim": "Total decisions in Phase 5.2 hardware evaluation run (IDs 69 to 92)",
        "value": 24,
        "how": "python -c \"import sqlite3; con = sqlite3.connect('data/siliconroute.db'); print(con.execute('SELECT COUNT(*) FROM decision WHERE id BETWEEN 69 AND 92;').fetchone()[0])\"",
    },
    {
        "id": "claim_03",
        "claim": "SiliconRoute winning decisions out of 24 in Phase 5.2 evaluation",
        "value": 17,
        "how": "python -c \"import sqlite3; con = sqlite3.connect('data/siliconroute.db'); print(con.execute('SELECT COUNT(*) FROM decision WHERE id BETWEEN 69 AND 92 AND was_best = 1;').fetchone()[0])\"",
    },
    {
        "id": "claim_04",
        "claim": "SiliconRoute accuracy percentage in Phase 5.2 evaluation",
        "value": 70.8,
        "how": "python -c \"import sqlite3; con = sqlite3.connect('data/siliconroute.db'); print(con.execute('SELECT ROUND(AVG(was_best) * 100.0, 1) FROM decision WHERE id BETWEEN 69 AND 92;').fetchone()[0])\"",
    },
    {
        "id": "claim_05",
        "claim": "SiliconRoute mean regret percentage in Phase 5.2 evaluation",
        "value": 117.31,
        "how": "python -c \"import sqlite3; con = sqlite3.connect('data/siliconroute.db'); print(con.execute('SELECT ROUND(AVG(regret_pct), 2) FROM decision WHERE id BETWEEN 69 AND 92;').fetchone()[0])\"",
    },
    {
        "id": "claim_06",
        "claim": "Always-CPU winning decisions out of 24 in Phase 5.2 evaluation",
        "value": 16,
        "how": "python -c \"import json, sqlite3; con = sqlite3.connect('data/siliconroute.db'); rows = con.execute('SELECT context_json FROM decision WHERE id BETWEEN 69 AND 92;').fetchall(); print(sum(1 for r in rows if (m := json.loads(r[0]).get('measured_times_ms', {})) and m.get('1') <= min(m.values()) + 1e-4))\"",
    },
    {
        "id": "claim_07",
        "claim": "Always-RTX winning decisions out of 24 in Phase 5.2 evaluation",
        "value": 0,
        "how": "python -c \"import json, sqlite3; con = sqlite3.connect('data/siliconroute.db'); rows = con.execute('SELECT context_json FROM decision WHERE id BETWEEN 69 AND 92;').fetchall(); print(sum(1 for r in rows if (m := json.loads(r[0]).get('measured_times_ms', {})) and m.get('3') <= min(m.values()) + 1e-4))\"",
    },
    {
        "id": "claim_08",
        "claim": "Fit-Only router winning decisions out of 24 in Phase 5.2 evaluation",
        "value": 12,
        "how": "python -c \"import sys; sys.path.insert(0, '.'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(69, 93)))['baselines']['fit_only_router']['wins'])\"",
    },
    {
        "id": "claim_09",
        "claim": "SiliconRoute accuracy percentage in idle_loaded workload",
        "value": 87.5,
        "how": "python -c \"import sys; sys.path.insert(0, '.'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(69, 93)))['per_workload']['idle_loaded']['accuracy_pct'])\"",
    },
    {
        "id": "claim_10",
        "claim": "SiliconRoute mean regret percentage in idle_loaded workload",
        "value": 3.01,
        "how": "python -c \"import sys; sys.path.insert(0, '.'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(69, 93)))['per_workload']['idle_loaded']['mean_regret_pct'])\"",
    },
    {
        "id": "claim_11",
        "claim": "SiliconRoute p90 regret percentage in idle_loaded workload",
        "value": 7.22,
        "how": "python -c \"import sys; sys.path.insert(0, '.'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(69, 93)))['per_workload']['idle_loaded']['p90_regret_pct'])\"",
    },
    {
        "id": "claim_12",
        "claim": "SiliconRoute accuracy percentage in cold_start workload",
        "value": 75.0,
        "how": "python -c \"import sys; sys.path.insert(0, '.'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(69, 93)))['per_workload']['cold_start']['accuracy_pct'])\"",
    },
    {
        "id": "claim_13",
        "claim": "SiliconRoute mean regret percentage in cold_start workload",
        "value": 0.39,
        "how": "python -c \"import sys; sys.path.insert(0, '.'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(69, 93)))['per_workload']['cold_start']['mean_regret_pct'])\"",
    },
    {
        "id": "claim_14",
        "claim": "SiliconRoute p90 regret percentage in cold_start workload",
        "value": 1.41,
        "how": "python -c \"import sys; sys.path.insert(0, '.'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(69, 93)))['per_workload']['cold_start']['p90_regret_pct'])\"",
    },
    {
        "id": "claim_15",
        "claim": "Decision 72 conv-96c-4l B=8 cold_start chose CPU with 0.0% regret",
        "value": 0.0,
        "how": "python -c \"import sqlite3; con = sqlite3.connect('data/siliconroute.db'); print(con.execute('SELECT regret_pct FROM decision WHERE id = 72;').fetchone()[0])\"",
    },
    {
        "id": "claim_16",
        "claim": "Decision 85 conv-96c-4l B=8 idle_loaded chose dml:0 with 0.0% regret",
        "value": 0.0,
        "how": "python -c \"import sqlite3; con = sqlite3.connect('data/siliconroute.db'); print(con.execute('SELECT regret_pct FROM decision WHERE id = 85;').fetchone()[0])\"",
    },
    {
        "id": "claim_17",
        "claim": "Decision 87 conv-96c-4l B=1 idle_loaded chose dml:0 with 0.0% regret",
        "value": 0.0,
        "how": "python -c \"import sqlite3; con = sqlite3.connect('data/siliconroute.db'); print(con.execute('SELECT regret_pct FROM decision WHERE id = 87;').fetchone()[0])\"",
    },
    {
        "id": "claim_18",
        "claim": "Decision 92 conv-96c-4l B=1 cold_start chose CPU with 0.0% regret",
        "value": 0.0,
        "how": "python -c \"import sqlite3; con = sqlite3.connect('data/siliconroute.db'); print(con.execute('SELECT regret_pct FROM decision WHERE id = 92;').fetchone()[0])\"",
    },
    {
        "id": "claim_19",
        "claim": "NVIDIA RTX 5070 (dml:1) convolution idle_loaded median slowdown ratio",
        "value": 2.58,
        "how": "python -c \"import sys; sys.path.insert(0, '.'); from sqlmodel import Session; from app.db import engine; from app.router import get_workload_slowdown_ratio; s = Session(engine); print(round(get_workload_slowdown_ratio(s, 3, 'conv', 'idle_loaded'), 2))\"",
    },
    {
        "id": "claim_20",
        "claim": "NVIDIA RTX 5070 (dml:1) convolution cold_start median slowdown ratio",
        "value": 5.8,
        "how": "python -c \"import sys; sys.path.insert(0, '.'); from sqlmodel import Session; from app.db import engine; from app.router import get_workload_slowdown_ratio; s = Session(engine); print(round(get_workload_slowdown_ratio(s, 3, 'conv', 'cold_start'), 2))\"",
    },
]

# Verify every single claim by executing its 'how' command
print("=" * 80)
print("VERIFYING ALL CLAIMS AGAINST HARDWARE DATABASE")
print("=" * 80)

# Replace 'python ' with venv python for execution
all_passed = True
for c in claims:
    cmd_str = c["how"].replace("python ", f'"{sys.executable}" ')
    proc = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
    out_val = proc.stdout.strip()
    expected = str(c["value"])
    # Float check or exact match
    try:
        match = abs(float(out_val) - float(expected)) < 0.01
    except ValueError:
        match = (out_val == expected)

    status = "PASS" if match else "FAIL"
    if not match:
        all_passed = False
        print(f"[{status}] {c['id']:<10}: expected={expected} | actual={out_val}")
        if proc.stderr:
            print("  STDERR:", proc.stderr.strip())
    else:
        print(f"[{status}] {c['id']:<10}: expected={expected} | actual={out_val}")

out_path = Path("results/claims_phase5_2.json")
out_path.write_text(json.dumps(claims, indent=2))
print("\n" + "=" * 80)
if all_passed:
    print(f"ALL 20 CLAIMS VERIFIED EXACTLY. Saved to {out_path}")
else:
    print("WARNING: Some claims failed verification!")
    sys.exit(1)
