"""Generate and self-verify claims_phase5_3.json for SiliconRoute Phase 5.3."""

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session
from app.db import engine
from app.router import compute_decision_statistics

DB_PATH = Path("data/siliconroute.db")


def main():
    con = sqlite3.connect(DB_PATH)

    # 1. Total workload measurements
    wl_count = con.execute("SELECT COUNT(*) FROM workloadmeasurement;").fetchone()[0]

    # 2. Total decisions in Phase 5.3 evaluation run (IDs 93 to 116)
    dec_ids = list(range(93, 117))
    dec_count = con.execute("SELECT COUNT(*) FROM decision WHERE id BETWEEN 93 AND 116;").fetchone()[0]

    with Session(engine) as session:
        stats = compute_decision_statistics(session, decision_ids=dec_ids)

    sr = stats["siliconroute"]
    base_cpu = stats["baselines"]["always_cpu"]
    base_rtx = stats["baselines"]["always_rtx"]
    base_fit = stats["baselines"]["fit_only_router"]
    wl_stats = stats["per_workload"]

    total_runs = con.execute("SELECT COUNT(*) FROM run;").fetchone()[0]
    suspect_runs = con.execute("SELECT COUNT(*) FROM run WHERE identity_suspect = 1;").fetchone()[0]

    claims = [
        {
            "id": "claim_01",
            "claim": "Total workload measurements stored in database",
            "value": wl_count,
            "how": 'python -c "import sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); print(con.execute(\'SELECT COUNT(*) FROM workloadmeasurement;\').fetchone()[0])"',
        },
        {
            "id": "claim_02",
            "claim": "Total decisions in Phase 5.3 hardware evaluation run (IDs 93 to 116)",
            "value": dec_count,
            "how": 'python -c "import sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); print(con.execute(\'SELECT COUNT(*) FROM decision WHERE id BETWEEN 93 AND 116;\').fetchone()[0])"',
        },
        {
            "id": "claim_03",
            "claim": "SiliconRoute winning decisions out of 24 in Phase 5.3 evaluation",
            "value": sr["wins"],
            "how": 'python -c "import sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); print(con.execute(\'SELECT COUNT(*) FROM decision WHERE id BETWEEN 93 AND 116 AND was_best = 1;\').fetchone()[0])"',
        },
        {
            "id": "claim_04",
            "claim": "SiliconRoute accuracy percentage in Phase 5.3 evaluation",
            "value": sr["accuracy_pct"],
            "how": 'python -c "import sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); print(con.execute(\'SELECT ROUND(AVG(was_best) * 100.0, 1) FROM decision WHERE id BETWEEN 93 AND 116;\').fetchone()[0])"',
        },
        {
            "id": "claim_05",
            "claim": "SiliconRoute mean regret percentage in Phase 5.3 evaluation",
            "value": sr["mean_regret_pct"],
            "how": 'python -c "import sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); print(con.execute(\'SELECT ROUND(AVG(regret_pct), 2) FROM decision WHERE id BETWEEN 93 AND 116;\').fetchone()[0])"',
        },
        {
            "id": "claim_06",
            "claim": "SiliconRoute p90 regret percentage in Phase 5.3 evaluation",
            "value": sr["p90_regret_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'siliconroute\'][\'p90_regret_pct\'])"',
        },
        {
            "id": "claim_07",
            "claim": "Always-CPU winning decisions out of 24 in Phase 5.3 evaluation",
            "value": base_cpu["wins"],
            "how": 'python -c "import json, sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); rows = con.execute(\'SELECT context_json FROM decision WHERE id BETWEEN 93 AND 116;\').fetchall(); print(sum(1 for r in rows if (m := json.loads(r[0]).get(\'measured_times_ms\', {})) and m.get(\'1\') <= min(m.values()) + 1e-4))"',
        },
        {
            "id": "claim_08",
            "claim": "Always-CPU accuracy percentage in Phase 5.3 evaluation",
            "value": base_cpu["accuracy_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'baselines\'][\'always_cpu\'][\'accuracy_pct\'])"',
        },
        {
            "id": "claim_09",
            "claim": "Always-CPU mean regret percentage in Phase 5.3 evaluation",
            "value": base_cpu["mean_regret_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'baselines\'][\'always_cpu\'][\'mean_regret_pct\'])"',
        },
        {
            "id": "claim_10",
            "claim": "Always-RTX winning decisions out of 24 in Phase 5.3 evaluation",
            "value": base_rtx["wins"],
            "how": 'python -c "import json, sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); rows = con.execute(\'SELECT context_json FROM decision WHERE id BETWEEN 93 AND 116;\').fetchall(); print(sum(1 for r in rows if (m := json.loads(r[0]).get(\'measured_times_ms\', {})) and m.get(\'3\') <= min(m.values()) + 1e-4))"',
        },
        {
            "id": "claim_11",
            "claim": "Always-RTX accuracy percentage in Phase 5.3 evaluation",
            "value": base_rtx["accuracy_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'baselines\'][\'always_rtx\'][\'accuracy_pct\'])"',
        },
        {
            "id": "claim_12",
            "claim": "Always-RTX mean regret percentage in Phase 5.3 evaluation",
            "value": base_rtx["mean_regret_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'baselines\'][\'always_rtx\'][\'mean_regret_pct\'])"',
        },
        {
            "id": "claim_13",
            "claim": "Fit-Only router winning decisions out of 24 in Phase 5.3 evaluation",
            "value": base_fit["wins"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'baselines\'][\'fit_only_router\'][\'wins\'])"',
        },
        {
            "id": "claim_14",
            "claim": "Fit-Only router accuracy percentage in Phase 5.3 evaluation",
            "value": base_fit["accuracy_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'baselines\'][\'fit_only_router\'][\'accuracy_pct\'])"',
        },
        {
            "id": "claim_15",
            "claim": "Fit-Only router mean regret percentage in Phase 5.3 evaluation",
            "value": base_fit["mean_regret_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'baselines\'][\'fit_only_router\'][\'mean_regret_pct\'])"',
        },
        {
            "id": "claim_16",
            "claim": "SiliconRoute accuracy percentage in idle_loaded workload",
            "value": wl_stats["idle_loaded"]["accuracy_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'per_workload\'][\'idle_loaded\'][\'accuracy_pct\'])"',
        },
        {
            "id": "claim_17",
            "claim": "SiliconRoute mean regret percentage in idle_loaded workload",
            "value": wl_stats["idle_loaded"]["mean_regret_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'per_workload\'][\'idle_loaded\'][\'mean_regret_pct\'])"',
        },
        {
            "id": "claim_18",
            "claim": "SiliconRoute accuracy percentage in cold_start workload",
            "value": wl_stats["cold_start"]["accuracy_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'per_workload\'][\'cold_start\'][\'accuracy_pct\'])"',
        },
        {
            "id": "claim_19",
            "claim": "SiliconRoute mean regret percentage in cold_start workload",
            "value": wl_stats["cold_start"]["mean_regret_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'per_workload\'][\'cold_start\'][\'mean_regret_pct\'])"',
        },
        {
            "id": "claim_20",
            "claim": "SiliconRoute accuracy percentage in sustained workload",
            "value": wl_stats["sustained"]["accuracy_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'per_workload\'][\'sustained\'][\'accuracy_pct\'])"',
        },
        {
            "id": "claim_21",
            "claim": "SiliconRoute mean regret percentage in sustained workload",
            "value": wl_stats["sustained"]["mean_regret_pct"],
            "how": 'python -c "import sys; sys.path.insert(0, \'.\'); from sqlmodel import Session; from app.db import engine; from app.router import compute_decision_statistics; s = Session(engine); print(compute_decision_statistics(s, decision_ids=list(range(93, 117)))[\'per_workload\'][\'sustained\'][\'mean_regret_pct\'])"',
        },
        {
            "id": "claim_22",
            "claim": "Total historical runs stored in database (0 runs deleted)",
            "value": total_runs,
            "how": 'python -c "import sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); print(con.execute(\'SELECT COUNT(*) FROM run;\').fetchone()[0])"',
        },
        {
            "id": "claim_23",
            "claim": "Historical runs flagged as identity_suspect",
            "value": suspect_runs,
            "how": 'python -c "import sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); print(con.execute(\'SELECT COUNT(*) FROM run WHERE identity_suspect = 1;\').fetchone()[0])"',
        },
        {
            "id": "claim_24",
            "claim": "Physical DXGI VendorId for NVIDIA GeForce RTX 5070 Laptop GPU (dml:1)",
            "value": "0x10DE",
            "how": 'python -c "import sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); print(con.execute(\\"SELECT vendor_id FROM device WHERE key = \'dml:1\';\\").fetchone()[0])"',
        },
        {
            "id": "claim_25",
            "claim": "Physical DXGI VendorId for AMD Radeon 610M (dml:0)",
            "value": "0x1002",
            "how": 'python -c "import sqlite3; con = sqlite3.connect(\'data/siliconroute.db\'); print(con.execute(\\"SELECT vendor_id FROM device WHERE key = \'dml:0\';\\").fetchone()[0])"',
        },
    ]

    out_file = Path("results/claims_phase5_3.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(claims, indent=2), encoding="utf-8")
    print(f"Wrote {len(claims)} claims to {out_file.resolve()}")

    # Self-verify each claim by running 'how'
    print("\nSelf-verifying each claim via its exact command:")
    all_passed = True
    for c in claims:
        cmd = c["how"]
        expected = c["value"]
        test_cmd = cmd.replace("python -c", f'"{sys.executable}" -c')
        res = subprocess.run(test_cmd, shell=True, capture_output=True, text=True)
        raw_val = res.stdout.strip()
        try:
            actual = type(expected)(raw_val) if type(expected) is int else float(raw_val)
        except Exception:
            actual = raw_val

        if isinstance(expected, (int, str)):
            match = (actual == expected)
        else:
            match = abs(actual - expected) < 1e-3
        status = "OK" if match else "MISMATCH"
        print(f"  [{c['id']}] {c['claim'][:50]:<50} Expected={expected!r} Actual={actual!r} -> {status}")
        if not match:
            all_passed = False

    if all_passed:
        print("\nALL CLAIMS SELF-VERIFIED 100% GREEN.")
    else:
        print("\nWARNING: Some claims failed self-verification.")
        sys.exit(1)


if __name__ == "__main__":
    main()
