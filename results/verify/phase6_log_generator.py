"""Phase 6 Verbatim Log Generator.

Generates ground-truth log files in results/logs/phase6/ directly from
data/siliconroute.db, live API queries, and filesystem verification.
"""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import urllib.request

LOGS_DIR = Path("results/logs/phase6")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path("data/siliconroute.db")


def step1_db_runs_and_suspects():
    log_file = LOGS_DIR / "db_runs_and_suspects.txt"
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("SELECT count(*) FROM run")
    total_runs = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM run WHERE identity_suspect = 1")
    suspect_runs = cur.fetchone()[0]

    cur.execute("SELECT id, device_id, physics_note, identity_suspect FROM run WHERE id IN (777, 783)")
    notes_777_783 = cur.fetchall()

    cur.execute("SELECT DISTINCT aimodel.name, count(run.id) FROM run JOIN aimodel ON run.ai_model_id = aimodel.id GROUP BY aimodel.name")
    runs_by_model = cur.fetchall()

    cur.execute("SELECT count(*) FROM run JOIN aimodel ON run.ai_model_id = aimodel.id WHERE aimodel.name IN ('mlp-32w-2l', 'mlp-64w-2l')")
    test_leftover_runs = cur.fetchone()[0]

    lines = [
        f"TOTAL_RUNS_COUNT: {total_runs}",
        f"IDENTITY_SUSPECT_RUNS_COUNT: {suspect_runs}",
        f"RUN_777_783_NOTES: {notes_777_783}",
        f"TEST_LEFTOVERS_RUNS_COUNT: {test_leftover_runs}",
        "RUNS_BY_MODEL_BREAKDOWN:",
    ]
    for m, c in sorted(runs_by_model):
        lines.append(f"  {m}: {c}")

    text = "\n".join(lines) + "\n"
    log_file.write_text(text, encoding="utf-8")
    print(f"Generated {log_file}")


def step2_volatility_bands():
    log_file = LOGS_DIR / "volatility_bands.txt"
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Query all models measured in multiple sessions
    query = """
    SELECT dev.key, dev.label, aim.name, r.batch, count(DISTINCT r.session_id) as sess_cnt,
           min(r.median_ms) as min_med, max(r.median_ms) as max_med
    FROM run r
    JOIN device dev ON r.device_id = dev.id
    JOIN aimodel aim ON r.ai_model_id = aim.id
    WHERE r.identity_suspect = 0 AND r.median_ms IS NOT NULL AND r.session_id IS NOT NULL
    GROUP BY dev.key, dev.label, aim.name, r.batch
    HAVING sess_cnt > 1
    """
    cur.execute(query)
    rows = cur.fetchall()

    dev_diffs: dict[str, list[float]] = {}
    lines = ["MULTI_SESSION_CONFIGS_VARIABILITY:"]
    for d_key, d_label, m_name, batch, sc, min_m, max_m in rows:
        pct = ((max_m - min_m) / min_m) * 100.0 if min_m > 0 else 0.0
        dev_diffs.setdefault(d_key, []).append(pct)
        lines.append(f"  [{d_key}] {m_name} B={batch} (sessions={sc}): min={min_m:.3f}ms, max={max_m:.3f}ms, diff={pct:.1f}%")

    lines.append("\nVOLATILITY_BANDS_PER_DEVICE (mean percentage session spread):")
    for d_key, diffs in dev_diffs.items():
        band = sum(diffs) / len(diffs)
        lines.append(f"  {d_key}: +/-{band:.1f}% across {len(diffs)} multi-session configs")

    text = "\n".join(lines) + "\n"
    log_file.write_text(text, encoding="utf-8")
    print(f"Generated {log_file}")


def step3_decisions_eval_tables():
    log_file = LOGS_DIR / "decisions_eval_tables.txt"
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
    SELECT id, chosen_device_id, best_device_id_actual, was_best, regret_pct, context_json
    FROM decision
    WHERE id BETWEEN 93 AND 116
    ORDER BY id ASC
    """)
    rows = cur.fetchall()

    total = len(rows)
    wins = sum(1 for r in rows if r[3] == 1)
    acc = (wins / total * 100.0) if total > 0 else 0.0
    regrets = [r[4] for r in rows if r[4] is not None]
    mean_regret = sum(regrets) / len(regrets) if regrets else 0.0

    # Sort regrets for p90
    sorted_regrets = sorted(regrets)
    idx_p90 = int(round(0.90 * (len(sorted_regrets) - 1))) if sorted_regrets else 0
    p90_regret = sorted_regrets[idx_p90] if sorted_regrets else 0.0

    # Per workload breakdown
    wl_stats: dict[str, list[tuple[int, float]]] = {}
    for r in rows:
        ctx = json.loads(r[5]) if r[5] else {}
        wl = ctx.get("workload", "sustained")
        wl_stats.setdefault(wl, []).append((r[3], r[4]))

    lines = [
        f"DECISIONS_93_116_OVERALL: count={total}, wins={wins}, accuracy={acc:.1f}%, mean_regret={mean_regret:.2f}%, p90_regret={p90_regret:.2f}%",
        "\nPER_WORKLOAD_BREAKDOWN:"
    ]

    for wl, decs in wl_stats.items():
        w_total = len(decs)
        w_wins = sum(1 for is_win, _ in decs if is_win == 1)
        w_acc = (w_wins / w_total * 100.0) if w_total > 0 else 0.0
        w_regs = [reg for _, reg in decs if reg is not None]
        w_mean_reg = sum(w_regs) / len(w_regs) if w_regs else 0.0
        w_sorted_regs = sorted(w_regs)
        w_p90_idx = int(round(0.90 * (len(w_sorted_regs) - 1))) if w_sorted_regs else 0
        w_p90_reg = w_sorted_regs[w_p90_idx] if w_sorted_regs else 0.0
        lines.append(f"  {wl.upper()}: count={w_total}, wins={w_wins}/{w_total}, accuracy={w_acc:.1f}%, mean_regret={w_mean_reg:.2f}%, p90_regret={w_p90_reg:.2f}%")

    text = "\n".join(lines) + "\n"
    log_file.write_text(text, encoding="utf-8")
    print(f"Generated {log_file}")


def step4_screenshot_files():
    log_file = LOGS_DIR / "screenshot_files.txt"
    ss_dir = Path("results/screenshots")
    lines = ["SCREENSHOT_FILES_LIST:"]
    for p in sorted(ss_dir.glob("*.png")):
        stat = p.stat()
        lines.append(f"  {p.name}: {stat.st_size} bytes")
    text = "\n".join(lines) + "\n"
    log_file.write_text(text, encoding="utf-8")
    print(f"Generated {log_file}")


def step5_snapshot_backup():
    log_file = LOGS_DIR / "snapshot_backup.txt"
    src_path = "data/siliconroute.db"
    dst_path = "data/snapshot_for_review.db"

    # Wal checkpoint and backup
    src = sqlite3.connect(src_path)
    src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    dst = sqlite3.connect(dst_path)
    src.backup(dst)
    dst.close()
    src.close()

    size = os.path.getsize(dst_path)
    with open(dst_path, "rb") as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()

    lines = [
        f"SNAPSHOT_PATH: {dst_path}",
        f"SNAPSHOT_SIZE: {size} bytes",
        f"SNAPSHOT_SHA256: {sha256}",
    ]
    text = "\n".join(lines) + "\n"
    log_file.write_text(text, encoding="utf-8")
    print(f"Generated {log_file}")


if __name__ == "__main__":
    step1_db_runs_and_suspects()
    step2_volatility_bands()
    step3_decisions_eval_tables()
    step4_screenshot_files()
    step5_snapshot_backup()
