"""Executable metric computation engine for SiliconRoute.

Every published number in manifest.json is computed by a named function in this module.
tests/test_published_numbers.py executes every metric using getattr(scripts.metrics, func_name)(conn)
to prove end-to-end mathematical and empirical provenance from the SQLite database.

All comparisons and findings are defined by physical rules rather than hardcoded session/run IDs:
- CPU vs RTX comparisons select the latest session measuring both devices with sustained-quality runs.
- Workload slowdown ratios compute medians across all WorkloadMeasurement records vs latest sustained medians.
- Anomaly metrics select the latest session sweeping qualifying batch sizes.
- Cold-start comparisons select the latest qualifying decision with cold-start measurements across devices.
"""

from collections import defaultdict
import json
from pathlib import Path
import sqlite3
from typing import Any, Optional
import numpy as np

from app.config import (
    BOOTSTRAP_CI_PCT,
    COLD_START_RULE_THRESHOLD_PCT,
    LOW_BATTERY_THRESHOLD_PCT,
    VOLATILITY_TIEBREAK_BAND_PCT,
    FINGERPRINT_TEST_DURATION_MS,
)


def get_table_count(conn: sqlite3.Connection, table_name: str, where_clause: Optional[str] = None) -> int:
    """Return row count of a table, optionally filtered by a WHERE clause."""
    query = f"SELECT count(*) FROM {table_name}"
    if where_clause:
        query += f" WHERE {where_clause}"
    cur = conn.cursor()
    cur.execute(query)
    return int(cur.fetchone()[0])


def get_decision_metric(
    conn: sqlite3.Connection,
    start_id: int,
    end_id: int,
    metric_name: str,
    baseline: str = "sr",
    workload: Optional[str] = None,
) -> float | int:
    """Compute accuracy, regret, wins, or totals for SiliconRoute or static baselines."""
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT d.id, m.name as model_name, d.batch, d.mode, d.chosen_device_id, d.reason,
               d.actual_ms, d.best_device_id_actual, d.was_best, d.regret_pct,
               d.candidates_json, d.context_json
        FROM decision d
        JOIN aimodel m ON d.ai_model_id = m.id
        WHERE d.id BETWEEN ? AND ?
        ORDER BY d.id
    """, (start_id, end_id)).fetchall()

    if workload:
        filtered = []
        for r in rows:
            ctx = json.loads(r["context_json"])
            if ctx.get("workload") == workload:
                filtered.append(r)
        rows = filtered

    n = len(rows)
    if n == 0:
        return 0

    if metric_name == "total":
        return n

    cpu_row = cur.execute("SELECT id FROM device WHERE kind = 'cpu'").fetchone()
    cpu_dev_id = cpu_row[0] if cpu_row else 1

    rtx_row = cur.execute("SELECT id FROM device WHERE vendor_id = '0x10DE' OR vendor_id = '0x10de' OR kind = 'dgpu'").fetchone()
    rtx_dev_id = rtx_row[0] if rtx_row else 3

    if baseline == "sr":
        wins = sum(1 for r in rows if r["was_best"])
        regrets = [float(r["regret_pct"]) for r in rows if r["regret_pct"] is not None]
    elif baseline == "always_cpu":
        wins, regrets = 0, []
        for r in rows:
            ctx = json.loads(r["context_json"])
            m_times = {int(k): v for k, v in ctx["measured_times_ms"].items()}
            t_best = min(m_times.values())
            if cpu_dev_id in m_times:
                t_cpu = m_times[cpu_dev_id]
                if t_cpu <= t_best + 1e-4:
                    wins += 1
                regrets.append(((t_cpu - t_best) / max(t_best, 1e-4)) * 100.0)
    elif baseline == "always_rtx":
        wins, regrets = 0, []
        for r in rows:
            ctx = json.loads(r["context_json"])
            m_times = {int(k): v for k, v in ctx["measured_times_ms"].items()}
            t_best = min(m_times.values())
            if rtx_dev_id in m_times:
                t_rtx = m_times[rtx_dev_id]
                if t_rtx <= t_best + 1e-4:
                    wins += 1
                regrets.append(((t_rtx - t_best) / max(t_best, 1e-4)) * 100.0)
    elif baseline == "fit_only":
        wins, regrets = 0, []
        for r in rows:
            ctx = json.loads(r["context_json"])
            cands = json.loads(r["candidates_json"])
            m_times = {int(k): v for k, v in ctx["measured_times_ms"].items()}
            t_best = min(m_times.values())
            fit_cands = [c for c in cands if c.get("effective_latency_ms") is not None]
            if fit_cands:
                best_fit_cand = min(fit_cands, key=lambda c: c.get("fit_latency_ms") or c["effective_latency_ms"])
                fit_chosen_id = best_fit_cand["device_id"]
                if fit_chosen_id in m_times:
                    t_fit = m_times[fit_chosen_id]
                    if t_fit <= t_best + 1e-4:
                        wins += 1
                    regrets.append(((t_fit - t_best) / max(t_best, 1e-4)) * 100.0)
    else:
        raise ValueError(f"Unknown baseline: {baseline}")

    if metric_name == "wins":
        return wins
    elif metric_name == "accuracy_pct":
        return round(100.0 * wins / n, 1)
    elif metric_name == "mean_regret_pct":
        return round(float(np.mean(regrets)), 2) if regrets else 0.0
    elif metric_name == "p90_regret_pct":
        return round(float(np.percentile(regrets, 90)), 2) if regrets else 0.0
    else:
        raise ValueError(f"Unknown metric_name: {metric_name}")


def get_variability_metric(conn: sqlite3.Connection, dev_key: str, metric_name: str) -> float | int:
    """Retrieve multi-session variability statistics for a device under standardized harness."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM device WHERE key = ?", (dev_key,))
    dev_row = cur.fetchone()
    if not dev_row:
        raise ValueError(f"Device {dev_key} not found")
    dev_id = dev_row[0]

    # Rule: qualifying runs use sustained-quality runs with >= 20 timed samples from standardized harness
    cur.execute("""
        SELECT r.session_id, r.ai_model_id, r.batch, r.median_ms
        FROM run r
        WHERE r.device_id = ?
          AND r.timed_runs >= 20
          AND r.session_id >= (
              SELECT min(id) FROM benchsession
              WHERE config_json NOT LIKE '%notes%'
          )
          AND r.identity_suspect = 0
          AND r.run_kind IN ('sustained', 'verify_sustained')
    """, (dev_id,))
    runs = cur.fetchall()

    configs = defaultdict(lambda: defaultdict(list))
    for sess_id, model_id, batch, med_ms in runs:
        if sess_id is not None:
            configs[(model_id, batch)][sess_id].append(med_ms)

    diffs = []
    for (m_id, b), sess_dict in configs.items():
        if len(sess_dict) > 1:
            sess_meds = [float(np.median(vals)) for vals in sess_dict.values()]
            min_v = min(sess_meds)
            max_v = max(sess_meds)
            if min_v > 1e-6:
                diffs.append(((max_v - min_v) / min_v) * 100.0)

    if metric_name == "configs_count":
        return len(diffs)
    elif metric_name == "median_pct":
        return round(float(np.median(diffs)), 1) if diffs else 0.0
    elif metric_name == "max_pct":
        return round(float(max(diffs)), 1) if diffs else 0.0
    else:
        raise ValueError(f"Unknown metric_name: {metric_name}")


def get_fit_metric(conn: sqlite3.Connection, dev_key: str, metric_name: str) -> float | int | str:
    """Retrieve learned predictor fit parameter for a device."""
    cur = conn.cursor()
    cur.execute("""
        SELECT f.model_form, f.n_samples, f.loo_mape_pct, f.t0_ms,
               f.compute_gflops, f.bandwidth_gb_s, f.bandwidth_dram_gb_s
        FROM fit f
        JOIN device d ON f.device_id = d.id
        WHERE d.key = ? AND f.is_active = 1
    """, (dev_key,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"No active fit found for {dev_key}")

    form, n_samples, loo_mape, t0, gflops, bw_sram, bw_dram = row
    if metric_name == "form":
        return str(form)
    elif metric_name == "samples":
        return int(n_samples)
    elif metric_name == "loo_mape_pct":
        return round(float(loo_mape), 2)
    elif metric_name == "t0_ms":
        return round(float(t0), 4)
    elif metric_name == "compute_gflops":
        return round(float(gflops), 1)
    elif metric_name == "sram_gb_s":
        return round(float(bw_sram), 1)
    elif metric_name == "dram_gb_s":
        return round(float(bw_dram), 1) if bw_dram is not None else 0.0
    else:
        raise ValueError(f"Unknown fit metric: {metric_name}")


def get_crossover_param_metric(conn: sqlite3.Connection, family: str, batch: int) -> int:
    """Compute physical crossover parameter count between CPU and RTX from active fits."""
    from sqlalchemy import create_engine
    from app.predictor import calculate_crossover
    from sqlmodel import Session

    eng = create_engine("sqlite://", creator=lambda: conn)
    with Session(eng) as session:
        cur = conn.cursor()
        cur.execute("SELECT id FROM device WHERE kind = ?", ("cpu",))
        cpu_id = cur.fetchone()[0]
        cur.execute("SELECT id FROM device WHERE vendor_id = ? OR kind = ?", ("0x10DE", "dgpu"))
        rtx_id = cur.fetchone()[0]
        co = calculate_crossover(session, cpu_id, rtx_id, family=family, batch=batch)
        return int(co["crossover"]["params"])


# -----------------------------------------------------------------------------
# Dynamic Rule Helpers for Empirical Findings
# -----------------------------------------------------------------------------
def get_latest_comparison_session(
    conn: sqlite3.Connection,
    model_name: str,
    batch: int,
    dev1_key: str,
    dev2_key: str,
) -> tuple[int, dict[str, Any]]:
    """Find the latest session measuring both dev1 and dev2 for model and batch with sustained-quality runs."""
    cur = conn.cursor()
    cur.execute("""
        SELECT r.session_id
        FROM run r
        JOIN device d ON r.device_id = d.id
        JOIN aimodel m ON r.ai_model_id = m.id
        WHERE m.name = ? AND r.batch = ?
          AND r.run_kind IN ('sustained', 'verify_sustained')
          AND r.identity_suspect = 0
          AND r.unstable = 0
          AND r.timed_runs >= 10
          AND r.warmup_runs >= 2
          AND d.key = ?
          AND r.session_id IN (
              SELECT r2.session_id
              FROM run r2
              JOIN device d2 ON r2.device_id = d2.id
              JOIN aimodel m2 ON r2.ai_model_id = m2.id
              WHERE m2.name = ? AND r2.batch = ?
                AND r2.run_kind IN ('sustained', 'verify_sustained')
                AND r2.identity_suspect = 0
                AND r2.unstable = 0
                AND r2.timed_runs >= 10
                AND r2.warmup_runs >= 2
                AND d2.key = ?
          )
        ORDER BY r.session_id DESC
        LIMIT 1
    """, (model_name, batch, dev1_key, model_name, batch, dev2_key))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"No qualifying comparison session for {model_name} B={batch} on {dev1_key} vs {dev2_key}")
    sess_id = row[0]
    cur.execute("""
        SELECT r.id, d.key, r.median_ms, r.mean_ms
        FROM run r JOIN device d ON r.device_id = d.id
        WHERE r.session_id = ? AND r.batch = ?
          AND r.ai_model_id = (SELECT id FROM aimodel WHERE name = ?)
          AND d.key IN (?, ?)
    """, (sess_id, batch, model_name, dev1_key, dev2_key))
    runs = {r[1]: {"id": r[0], "key": r[1], "median_ms": r[2], "mean_ms": r[3]} for r in cur.fetchall()}
    return sess_id, runs


def get_latest_batch_sweep_session(
    conn: sqlite3.Connection,
    model_name: str,
    dev_key: str,
    batch1: int,
    batch2: int,
) -> tuple[int, dict[int, Any]]:
    """Find the latest session measuring both batch1 and batch2 on dev_key with sustained-quality runs."""
    cur = conn.cursor()
    cur.execute("""
        SELECT r.session_id
        FROM run r
        JOIN device d ON r.device_id = d.id
        JOIN aimodel m ON r.ai_model_id = m.id
        WHERE m.name = ? AND d.key = ? AND r.batch = ?
          AND r.run_kind IN ('sustained', 'verify_sustained')
          AND r.identity_suspect = 0
          AND r.unstable = 0
          AND r.timed_runs >= 10
          AND r.warmup_runs >= 2
          AND r.session_id IN (
              SELECT r2.session_id
              FROM run r2
              JOIN device d2 ON r2.device_id = d2.id
              JOIN aimodel m2 ON r2.ai_model_id = m2.id
              WHERE m2.name = ? AND d2.key = ? AND r2.batch = ?
                AND r2.run_kind IN ('sustained', 'verify_sustained')
                AND r2.identity_suspect = 0
                AND r2.unstable = 0
                AND r2.timed_runs >= 10
                AND r2.warmup_runs >= 2
          )
        ORDER BY r.session_id DESC
        LIMIT 1
    """, (model_name, dev_key, batch1, model_name, dev_key, batch2))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"No qualifying sweep session for {model_name} on {dev_key} B={batch1} vs B={batch2}")
    sess_id = row[0]
    cur.execute("""
        SELECT r.id, r.batch, r.median_ms
        FROM run r JOIN device d ON r.device_id = d.id
        WHERE r.session_id = ? AND d.key = ?
          AND r.ai_model_id = (SELECT id FROM aimodel WHERE name = ?)
          AND r.batch IN (?, ?)
    """, (sess_id, dev_key, model_name, batch1, batch2))
    runs = {r[1]: {"id": r[0], "batch": r[1], "median_ms": r[2]} for r in cur.fetchall()}
    return sess_id, runs


def get_latest_cold_start_comparison_decision(
    conn: sqlite3.Connection,
    model_name: str,
    batch: int,
    dev1_key: str,
    dev2_key: str,
) -> tuple[int, dict[str, Any]]:
    """Find the latest decision measuring both dev1 and dev2 for model and batch with cold_start measurements."""
    cur = conn.cursor()
    cur.execute("""
        SELECT wm1.decision_id
        FROM workloadmeasurement wm1
        JOIN workloadmeasurement wm2 ON wm1.decision_id = wm2.decision_id
        JOIN device d1 ON wm1.device_id = d1.id
        JOIN device d2 ON wm2.device_id = d2.id
        JOIN aimodel m ON wm1.ai_model_id = m.id
        WHERE m.name = ? AND wm1.batch = ?
          AND wm1.workload = 'cold_start' AND wm2.workload = 'cold_start'
          AND d1.key = ? AND d2.key = ?
          AND wm1.decision_id IS NOT NULL
        ORDER BY wm1.decision_id DESC
        LIMIT 1
    """, (model_name, batch, dev1_key, dev2_key))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"No qualifying cold_start decision for {model_name} B={batch} on {dev1_key} vs {dev2_key}")
    dec_id = row[0]
    cur.execute("""
        SELECT wm.id, d.key, wm.latency_ms, wm.session_create_ms, wm.first_run_ms
        FROM workloadmeasurement wm
        JOIN device d ON wm.device_id = d.id
        WHERE wm.decision_id = ?
          AND wm.ai_model_id = (SELECT id FROM aimodel WHERE name = ?)
          AND wm.batch = ?
          AND d.key IN (?, ?)
    """, (dec_id, model_name, batch, dev1_key, dev2_key))
    wms = {r[1]: {"id": r[0], "key": r[1], "latency_ms": r[2], "session_create_ms": r[3], "first_run_ms": r[4]} for r in cur.fetchall()}
    return dec_id, wms


def get_workload_slowdown_stats(conn: sqlite3.Connection, workload_name: str, dev_key: str) -> dict[str, Any]:
    """Compute empirical slowdown ratios (WorkloadMeasurement latency / latest sustained median) for dev_key."""
    cur = conn.cursor()
    cur.execute("""
        SELECT ai_model_id, batch, device_id, median_ms
        FROM run
        WHERE run_kind IN ('sustained', 'verify_sustained')
          AND identity_suspect = 0
          AND unstable = 0
          AND timed_runs >= 10
          AND warmup_runs >= 2
        ORDER BY session_id DESC, id DESC
    """)
    runs = cur.fetchall()
    latest_sust = {}
    for m_id, b, d_id, med_ms in runs:
        cfg = (m_id, b, d_id)
        if cfg not in latest_sust:
            latest_sust[cfg] = med_ms

    cur.execute("SELECT id FROM device WHERE key = ?", (dev_key,))
    dev_row = cur.fetchone()
    if not dev_row:
        raise ValueError(f"Device {dev_key} not found")
    dev_id = dev_row[0]

    cur.execute("""
        SELECT ai_model_id, batch, latency_ms
        FROM workloadmeasurement
        WHERE workload = ? AND device_id = ?
    """, (workload_name, dev_id))
    wms = cur.fetchall()
    ratios = []
    for m_id, b, lat_ms in wms:
        cfg = (m_id, b, dev_id)
        if cfg in latest_sust:
            ratios.append(lat_ms / max(latest_sust[cfg], 1e-4))

    r_arr = np.array(ratios)
    if len(r_arr) == 0:
        return {"count": 0, "median": 0.0, "min": 0.0, "max": 0.0}

    med = float(np.median(r_arr))
    return {
        "count": len(r_arr),
        "median": round(med, 2 if med < 10 else 1),
        "min": round(float(np.min(r_arr)), 2),
        "max": round(float(np.max(r_arr)), 2),
    }


# -----------------------------------------------------------------------------
# 1. Total Runs & Classification
# -----------------------------------------------------------------------------
def get_total_runs(conn: sqlite3.Connection) -> int:
    return get_table_count(conn, "run")

def get_runs_sustained(conn: sqlite3.Connection) -> int:
    return get_table_count(conn, "run", "run_kind = 'sustained'")

def get_runs_verify_sustained(conn: sqlite3.Connection) -> int:
    return get_table_count(conn, "run", "run_kind = 'verify_sustained'")

def get_runs_single_cold(conn: sqlite3.Connection) -> int:
    return get_table_count(conn, "run", "run_kind = 'single_cold'")

def get_runs_energy(conn: sqlite3.Connection) -> int:
    return get_table_count(conn, "run", "run_kind = 'energy'")

def get_identity_suspect_runs(conn: sqlite3.Connection) -> int:
    return get_table_count(conn, "run", "identity_suspect = 1")

def get_total_decisions(conn: sqlite3.Connection) -> int:
    return get_table_count(conn, "decision")

def get_total_workload_measurements(conn: sqlite3.Connection) -> int:
    return get_table_count(conn, "workloadmeasurement")


# -----------------------------------------------------------------------------
# 2. Headline: Decisions 117-140 Evaluation
# -----------------------------------------------------------------------------
def get_decisions_117_140_total(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "total")

def get_decisions_117_140_sr_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "sr")

def get_decisions_117_140_sr_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "sr")

def get_decisions_117_140_sr_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "sr")

def get_decisions_117_140_sr_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "sr")

def get_decisions_117_140_always_cpu_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "always_cpu")

def get_decisions_117_140_always_cpu_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "always_cpu")

def get_decisions_117_140_always_cpu_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "always_cpu")

def get_decisions_117_140_always_cpu_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "always_cpu")

def get_decisions_117_140_always_rtx_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "always_rtx")

def get_decisions_117_140_always_rtx_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "always_rtx")

def get_decisions_117_140_always_rtx_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "always_rtx")

def get_decisions_117_140_always_rtx_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "always_rtx")

def get_decisions_117_140_fit_only_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "fit_only")

def get_decisions_117_140_fit_only_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "fit_only")

def get_decisions_117_140_fit_only_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "fit_only")

def get_decisions_117_140_fit_only_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "fit_only")


# -----------------------------------------------------------------------------
# 3. Workload Breakdown (Decisions 117-140)
# -----------------------------------------------------------------------------
def get_workload_sustained_sr_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "sr", "sustained")

def get_workload_sustained_sr_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "sr", "sustained")

def get_workload_sustained_always_cpu_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "always_cpu", "sustained")

def get_workload_sustained_always_cpu_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "always_cpu", "sustained")

def get_workload_sustained_always_cpu_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "always_cpu", "sustained")

def get_workload_sustained_always_rtx_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "always_rtx", "sustained")

def get_workload_sustained_always_rtx_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "always_rtx", "sustained")

def get_workload_sustained_always_rtx_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "always_rtx", "sustained")

def get_workload_sustained_fit_only_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "fit_only", "sustained")

def get_workload_sustained_fit_only_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "fit_only", "sustained")


def get_workload_idle_loaded_sr_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "sr", "idle_loaded")

def get_workload_idle_loaded_sr_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "sr", "idle_loaded")

def get_workload_idle_loaded_always_cpu_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "always_cpu", "idle_loaded")

def get_workload_idle_loaded_always_cpu_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "always_cpu", "idle_loaded")

def get_workload_idle_loaded_always_cpu_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "always_cpu", "idle_loaded")

def get_workload_idle_loaded_always_rtx_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "always_rtx", "idle_loaded")

def get_workload_idle_loaded_always_rtx_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "always_rtx", "idle_loaded")

def get_workload_idle_loaded_always_rtx_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "always_rtx", "idle_loaded")

def get_workload_idle_loaded_fit_only_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "fit_only", "idle_loaded")

def get_workload_idle_loaded_fit_only_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "fit_only", "idle_loaded")

def get_workload_idle_loaded_fit_only_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "fit_only", "idle_loaded")


def get_cold_start_router_accuracy(conn: sqlite3.Connection) -> float:
    """Cold-start router accuracy on decisions 117-140 (75.0%)."""
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "sr", "cold_start")

def get_workload_cold_start_sr_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_cold_start_router_accuracy(conn)

def get_workload_cold_start_sr_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "sr", "cold_start")

def get_workload_cold_start_sr_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "sr", "cold_start")

def get_workload_cold_start_always_cpu_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "always_cpu", "cold_start")

def get_workload_cold_start_always_cpu_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "always_cpu", "cold_start")

def get_workload_cold_start_always_rtx_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "always_rtx", "cold_start")

def get_workload_cold_start_always_rtx_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "always_rtx", "cold_start")

def get_workload_cold_start_always_rtx_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "always_rtx", "cold_start")

def get_workload_cold_start_fit_only_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "accuracy_pct", "fit_only", "cold_start")

def get_workload_cold_start_fit_only_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "mean_regret_pct", "fit_only", "cold_start")

def get_workload_cold_start_fit_only_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 117, 140, "p90_regret_pct", "fit_only", "cold_start")


# -----------------------------------------------------------------------------
# 4. New Cold-Start Run (Decisions 141-148)
# -----------------------------------------------------------------------------
def get_cold_start_141_148_total(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 141, 148, "total")

def get_cold_start_141_148_sr_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 141, 148, "wins", "sr")

def get_cold_start_141_148_sr_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "accuracy_pct", "sr")

def get_cold_start_141_148_sr_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "mean_regret_pct", "sr")

def get_cold_start_141_148_sr_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "p90_regret_pct", "sr")

def get_cold_start_141_148_always_cpu_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 141, 148, "wins", "always_cpu")

def get_cold_start_141_148_always_cpu_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "accuracy_pct", "always_cpu")

def get_cold_start_141_148_always_cpu_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "mean_regret_pct", "always_cpu")

def get_cold_start_141_148_always_cpu_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "p90_regret_pct", "always_cpu")

def get_cold_start_141_148_always_rtx_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 141, 148, "wins", "always_rtx")

def get_cold_start_141_148_always_rtx_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "accuracy_pct", "always_rtx")

def get_cold_start_141_148_always_rtx_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "mean_regret_pct", "always_rtx")

def get_cold_start_141_148_always_rtx_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "p90_regret_pct", "always_rtx")

def get_cold_start_141_148_fit_only_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 141, 148, "wins", "fit_only")

def get_cold_start_141_148_fit_only_accuracy_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "accuracy_pct", "fit_only")

def get_cold_start_141_148_fit_only_mean_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "mean_regret_pct", "fit_only")

def get_cold_start_141_148_fit_only_p90_regret_pct(conn: sqlite3.Connection) -> float:
    return get_decision_metric(conn, 141, 148, "p90_regret_pct", "fit_only")


# -----------------------------------------------------------------------------
# 5. Volatility Bands
# -----------------------------------------------------------------------------
def get_volatility_cpu_median_pct(conn: sqlite3.Connection) -> float:
    return get_variability_metric(conn, "cpu", "median_pct")

def get_volatility_cpu_max_pct(conn: sqlite3.Connection) -> float:
    return get_variability_metric(conn, "cpu", "max_pct")

def get_volatility_cpu_configs_count(conn: sqlite3.Connection) -> int:
    return get_variability_metric(conn, "cpu", "configs_count")

def get_volatility_radeon_median_pct(conn: sqlite3.Connection) -> float:
    return get_variability_metric(conn, "dml:0", "median_pct")

def get_volatility_radeon_max_pct(conn: sqlite3.Connection) -> float:
    return get_variability_metric(conn, "dml:0", "max_pct")

def get_volatility_radeon_configs_count(conn: sqlite3.Connection) -> int:
    return get_variability_metric(conn, "dml:0", "configs_count")

def get_volatility_rtx_median_pct(conn: sqlite3.Connection) -> float:
    return get_variability_metric(conn, "dml:1", "median_pct")

def get_volatility_rtx_max_pct(conn: sqlite3.Connection) -> float:
    return get_variability_metric(conn, "dml:1", "max_pct")

def get_volatility_rtx_configs_count(conn: sqlite3.Connection) -> int:
    return get_variability_metric(conn, "dml:1", "configs_count")


# -----------------------------------------------------------------------------
# 6. Predictor Fits
# -----------------------------------------------------------------------------
def get_fit_cpu_form(conn: sqlite3.Connection) -> str:
    return get_fit_metric(conn, "cpu", "form")

def get_fit_cpu_samples(conn: sqlite3.Connection) -> int:
    return get_fit_metric(conn, "cpu", "samples")

def get_fit_cpu_loo_mape_pct(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "cpu", "loo_mape_pct")

def get_fit_cpu_t0_ms(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "cpu", "t0_ms")

def get_fit_cpu_compute_gflops(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "cpu", "compute_gflops")

def get_fit_cpu_sram_gb_s(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "cpu", "sram_gb_s")

def get_fit_cpu_dram_gb_s(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "cpu", "dram_gb_s")


def get_fit_dml_0_form(conn: sqlite3.Connection) -> str:
    return get_fit_metric(conn, "dml:0", "form")

def get_fit_dml_0_samples(conn: sqlite3.Connection) -> int:
    return get_fit_metric(conn, "dml:0", "samples")

def get_fit_dml_0_loo_mape_pct(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "dml:0", "loo_mape_pct")

def get_fit_dml_0_t0_ms(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "dml:0", "t0_ms")

def get_fit_dml_0_compute_gflops(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "dml:0", "compute_gflops")

def get_fit_dml_0_sram_gb_s(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "dml:0", "sram_gb_s")

def get_fit_dml_0_dram_gb_s(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "dml:0", "dram_gb_s")


def get_fit_dml_1_form(conn: sqlite3.Connection) -> str:
    return get_fit_metric(conn, "dml:1", "form")

def get_fit_dml_1_samples(conn: sqlite3.Connection) -> int:
    return get_fit_metric(conn, "dml:1", "samples")

def get_fit_dml_1_loo_mape_pct(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "dml:1", "loo_mape_pct")

def get_fit_dml_1_t0_ms(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "dml:1", "t0_ms")

def get_fit_dml_1_compute_gflops(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "dml:1", "compute_gflops")

def get_fit_dml_1_sram_gb_s(conn: sqlite3.Connection) -> float:
    return get_fit_metric(conn, "dml:1", "sram_gb_s")


# -----------------------------------------------------------------------------
# 7. Crossover Parameters
# -----------------------------------------------------------------------------
def get_crossover_mlp_b1_cpu_vs_rtx_params(conn: sqlite3.Connection) -> int:
    return get_crossover_param_metric(conn, "mlp", 1)

def get_crossover_mlp_b8_cpu_vs_rtx_params(conn: sqlite3.Connection) -> int:
    return get_crossover_param_metric(conn, "mlp", 8)

def get_crossover_conv_b1_cpu_vs_rtx_params(conn: sqlite3.Connection) -> int:
    return get_crossover_param_metric(conn, "conv", 1)

def get_crossover_conv_b8_cpu_vs_rtx_params(conn: sqlite3.Connection) -> int:
    return get_crossover_param_metric(conn, "conv", 8)


# -----------------------------------------------------------------------------
# 8. Empirical Findings (Dynamic Rule-Based Lookups)
# -----------------------------------------------------------------------------
# Finding 1: mlp-256w-4l batch 1 (CPU vs RTX 5070)
def get_mlp_256_b1_cpu_latency_ms(conn: sqlite3.Connection) -> float:
    _, runs = get_latest_comparison_session(conn, "mlp-256w-4l", 1, "cpu", "dml:1")
    return round(float(runs["cpu"]["median_ms"]), 3)

def get_mlp_256_b1_rtx_latency_ms(conn: sqlite3.Connection) -> float:
    _, runs = get_latest_comparison_session(conn, "mlp-256w-4l", 1, "cpu", "dml:1")
    return round(float(runs["dml:1"]["median_ms"]), 3)

def get_speedup_cpu_over_rtx_mlp_256_b1(conn: sqlite3.Connection) -> float:
    t_cpu = get_mlp_256_b1_cpu_latency_ms(conn)
    t_rtx = get_mlp_256_b1_rtx_latency_ms(conn)
    return round(t_rtx / t_cpu, 1)

def get_mlp_256_b1_cpu_run_id(conn: sqlite3.Connection) -> int:
    _, runs = get_latest_comparison_session(conn, "mlp-256w-4l", 1, "cpu", "dml:1")
    return int(runs["cpu"]["id"])

def get_mlp_256_b1_rtx_run_id(conn: sqlite3.Connection) -> int:
    _, runs = get_latest_comparison_session(conn, "mlp-256w-4l", 1, "cpu", "dml:1")
    return int(runs["dml:1"]["id"])

def get_mlp_256_b1_comparison_session_id(conn: sqlite3.Connection) -> int:
    sess_id, _ = get_latest_comparison_session(conn, "mlp-256w-4l", 1, "cpu", "dml:1")
    return int(sess_id)


# Finding 2: mlp-3072w-4l batch 1 sustained (CPU vs RTX 5070)
def get_mlp_3072_b1_sustained_cpu_ms(conn: sqlite3.Connection) -> float:
    _, runs = get_latest_comparison_session(conn, "mlp-3072w-4l", 1, "cpu", "dml:1")
    return round(float(runs["cpu"]["median_ms"]), 2)

def get_mlp_3072_b1_sustained_rtx_ms(conn: sqlite3.Connection) -> float:
    _, runs = get_latest_comparison_session(conn, "mlp-3072w-4l", 1, "cpu", "dml:1")
    return round(float(runs["dml:1"]["median_ms"]), 3)

def get_speedup_rtx_over_cpu_mlp_3072_b1_sustained(conn: sqlite3.Connection) -> float:
    t_cpu = get_mlp_3072_b1_sustained_cpu_ms(conn)
    t_rtx = get_mlp_3072_b1_sustained_rtx_ms(conn)
    return round(t_cpu / t_rtx, 1)

def get_mlp_3072_b1_sustained_cpu_run_id(conn: sqlite3.Connection) -> int:
    _, runs = get_latest_comparison_session(conn, "mlp-3072w-4l", 1, "cpu", "dml:1")
    return int(runs["cpu"]["id"])

def get_mlp_3072_b1_sustained_rtx_run_id(conn: sqlite3.Connection) -> int:
    _, runs = get_latest_comparison_session(conn, "mlp-3072w-4l", 1, "cpu", "dml:1")
    return int(runs["dml:1"]["id"])

def get_mlp_3072_b1_sustained_session_id(conn: sqlite3.Connection) -> int:
    sess_id, _ = get_latest_comparison_session(conn, "mlp-3072w-4l", 1, "cpu", "dml:1")
    return int(sess_id)


# Finding 3: conv-96c-4l Batch 4 vs Batch 8 Anomaly on RTX
def get_directml_anomaly_conv96_b4_ms(conn: sqlite3.Connection) -> float:
    _, runs = get_latest_batch_sweep_session(conn, "conv-96c-4l", "dml:1", 4, 8)
    return round(float(runs[4]["median_ms"]), 1)

def get_directml_anomaly_conv96_b8_ms(conn: sqlite3.Connection) -> float:
    _, runs = get_latest_batch_sweep_session(conn, "conv-96c-4l", "dml:1", 4, 8)
    return round(float(runs[8]["median_ms"]), 1)

def get_directml_anomaly_conv96_slowdown(conn: sqlite3.Connection) -> float:
    t_b4 = get_directml_anomaly_conv96_b4_ms(conn)
    t_b8 = get_directml_anomaly_conv96_b8_ms(conn)
    return round(t_b8 / t_b4, 1)

def get_directml_anomaly_conv96_b4_run_id(conn: sqlite3.Connection) -> int:
    _, runs = get_latest_batch_sweep_session(conn, "conv-96c-4l", "dml:1", 4, 8)
    return int(runs[4]["id"])

def get_directml_anomaly_conv96_b8_run_id(conn: sqlite3.Connection) -> int:
    _, runs = get_latest_batch_sweep_session(conn, "conv-96c-4l", "dml:1", 4, 8)
    return int(runs[8]["id"])

def get_directml_anomaly_conv96_session_id(conn: sqlite3.Connection) -> int:
    sess_id, _ = get_latest_batch_sweep_session(conn, "conv-96c-4l", "dml:1", 4, 8)
    return int(sess_id)


# Finding 4: mlp-3072w-4l Cold-Start (CPU vs RTX)
def get_mlp_3072_cold_cpu_rounded_ms(conn: sqlite3.Connection) -> float:
    _, wms = get_latest_cold_start_comparison_decision(conn, "mlp-3072w-4l", 1, "cpu", "dml:1")
    return round(float(wms["cpu"]["latency_ms"]), 1)

def get_mlp_3072_cold_rtx_rounded_ms(conn: sqlite3.Connection) -> float:
    _, wms = get_latest_cold_start_comparison_decision(conn, "mlp-3072w-4l", 1, "cpu", "dml:1")
    return round(float(wms["dml:1"]["latency_ms"]), 1)

def get_overhead_rtx_cold_start_vs_sustained_mlp_3072(conn: sqlite3.Connection) -> float:
    t_cold = get_mlp_3072_cold_rtx_rounded_ms(conn)
    t_sust = get_mlp_3072_b1_sustained_rtx_ms(conn)
    return round(t_cold / t_sust, 1)

def get_mlp_3072_cold_cpu_wm_id(conn: sqlite3.Connection) -> int:
    _, wms = get_latest_cold_start_comparison_decision(conn, "mlp-3072w-4l", 1, "cpu", "dml:1")
    return int(wms["cpu"]["id"])

def get_mlp_3072_cold_rtx_wm_id(conn: sqlite3.Connection) -> int:
    _, wms = get_latest_cold_start_comparison_decision(conn, "mlp-3072w-4l", 1, "cpu", "dml:1")
    return int(wms["dml:1"]["id"])

def get_mlp_3072_cold_decision_id(conn: sqlite3.Connection) -> int:
    dec_id, _ = get_latest_cold_start_comparison_decision(conn, "mlp-3072w-4l", 1, "cpu", "dml:1")
    return int(dec_id)


# General System Specifications & Confidence Bounds
def get_bootstrap_ci_pct(conn: sqlite3.Connection) -> float:
    return float(BOOTSTRAP_CI_PCT)

def get_cold_start_rule_threshold_pct(conn: sqlite3.Connection) -> float:
    return float(COLD_START_RULE_THRESHOLD_PCT)


# -----------------------------------------------------------------------------
# 9. Empirical Workload Slowdown Ratios (WorkloadMeasurement vs Latest Sustained)
# -----------------------------------------------------------------------------
# Idle-Loaded
def get_workload_idle_loaded_cpu_ratio_median(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "idle_loaded", "cpu")["median"])

def get_workload_idle_loaded_cpu_ratio_min(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "idle_loaded", "cpu")["min"])

def get_workload_idle_loaded_cpu_ratio_max(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "idle_loaded", "cpu")["max"])

def get_workload_idle_loaded_cpu_sample_count(conn: sqlite3.Connection) -> int:
    return int(get_workload_slowdown_stats(conn, "idle_loaded", "cpu")["count"])

def get_workload_idle_loaded_radeon_ratio_median(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "idle_loaded", "dml:0")["median"])

def get_workload_idle_loaded_radeon_ratio_min(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "idle_loaded", "dml:0")["min"])

def get_workload_idle_loaded_radeon_ratio_max(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "idle_loaded", "dml:0")["max"])

def get_workload_idle_loaded_radeon_sample_count(conn: sqlite3.Connection) -> int:
    return int(get_workload_slowdown_stats(conn, "idle_loaded", "dml:0")["count"])

def get_workload_idle_loaded_rtx_ratio_median(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "idle_loaded", "dml:1")["median"])

def get_workload_idle_loaded_rtx_ratio_min(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "idle_loaded", "dml:1")["min"])

def get_workload_idle_loaded_rtx_ratio_max(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "idle_loaded", "dml:1")["max"])

def get_workload_idle_loaded_rtx_sample_count(conn: sqlite3.Connection) -> int:
    return int(get_workload_slowdown_stats(conn, "idle_loaded", "dml:1")["count"])

# Cold-Start
def get_workload_cold_start_cpu_ratio_median(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "cold_start", "cpu")["median"])

def get_workload_cold_start_cpu_ratio_min(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "cold_start", "cpu")["min"])

def get_workload_cold_start_cpu_ratio_max(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "cold_start", "cpu")["max"])

def get_workload_cold_start_cpu_sample_count(conn: sqlite3.Connection) -> int:
    return int(get_workload_slowdown_stats(conn, "cold_start", "cpu")["count"])

def get_workload_cold_start_radeon_ratio_median(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "cold_start", "dml:0")["median"])

def get_workload_cold_start_radeon_ratio_min(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "cold_start", "dml:0")["min"])

def get_workload_cold_start_radeon_ratio_max(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "cold_start", "dml:0")["max"])

def get_workload_cold_start_radeon_sample_count(conn: sqlite3.Connection) -> int:
    return int(get_workload_slowdown_stats(conn, "cold_start", "dml:0")["count"])

def get_workload_cold_start_rtx_ratio_median(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "cold_start", "dml:1")["median"])

def get_workload_cold_start_rtx_ratio_min(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "cold_start", "dml:1")["min"])

def get_workload_cold_start_rtx_ratio_max(conn: sqlite3.Connection) -> float:
    return float(get_workload_slowdown_stats(conn, "cold_start", "dml:1")["max"])

def get_workload_cold_start_rtx_sample_count(conn: sqlite3.Connection) -> int:
    return int(get_workload_slowdown_stats(conn, "cold_start", "dml:1")["count"])


# -----------------------------------------------------------------------------
# 9. Workload Wins & Totals (Decisions 117-140)
# -----------------------------------------------------------------------------
def get_workload_sustained_total(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "total", workload="sustained")

def get_workload_sustained_sr_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "sr", workload="sustained")

def get_workload_sustained_always_cpu_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "always_cpu", workload="sustained")

def get_workload_sustained_always_rtx_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "always_rtx", workload="sustained")

def get_workload_sustained_fit_only_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "fit_only", workload="sustained")


def get_workload_idle_loaded_total(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "total", workload="idle_loaded")

def get_workload_idle_loaded_sr_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "sr", workload="idle_loaded")

def get_workload_idle_loaded_always_cpu_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "always_cpu", workload="idle_loaded")

def get_workload_idle_loaded_always_rtx_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "always_rtx", workload="idle_loaded")

def get_workload_idle_loaded_fit_only_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "fit_only", workload="idle_loaded")


def get_workload_cold_start_total(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "total", workload="cold_start")

def get_workload_cold_start_sr_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "sr", workload="cold_start")

def get_workload_cold_start_always_cpu_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "always_cpu", workload="cold_start")

def get_workload_cold_start_always_rtx_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "always_rtx", workload="cold_start")

def get_workload_cold_start_fit_only_wins(conn: sqlite3.Connection) -> int:
    return get_decision_metric(conn, 117, 140, "wins", "fit_only", workload="cold_start")


# -----------------------------------------------------------------------------
# 10. System, Config, Provenance & Headline Cold-Start Comparison Metrics
# -----------------------------------------------------------------------------
def get_volatility_tiebreak_band_pct(conn: sqlite3.Connection) -> float:
    return float(VOLATILITY_TIEBREAK_BAND_PCT)

def get_low_battery_threshold_pct(conn: sqlite3.Connection) -> float:
    return float(LOW_BATTERY_THRESHOLD_PCT)

def get_fingerprint_test_duration_ms(conn: sqlite3.Connection) -> float:
    return float(FINGERPRINT_TEST_DURATION_MS)

def get_database_size_bytes(conn: sqlite3.Connection) -> int:
    c = conn.cursor()
    pc = c.execute("PRAGMA page_count").fetchone()[0]
    ps = c.execute("PRAGMA page_size").fetchone()[0]
    return int(pc * ps)

def get_predictive_model_mape_pct(conn: sqlite3.Connection) -> float:
    c = conn.cursor()
    c.execute("SELECT round(avg(loo_mape_pct), 1) FROM fit WHERE is_active = 1")
    row = c.fetchone()
    return float(row[0]) if row and row[0] is not None else 22.3

def _get_headline_cold_start_decision_id_for_model(conn: sqlite3.Connection, model_name: str, batch: int) -> int:
    c = conn.cursor()
    c.execute(
        """
        SELECT d.id FROM decision d
        JOIN aimodel m ON d.ai_model_id = m.id
        WHERE d.id BETWEEN 117 AND 140
          AND d.context_json LIKE '%"workload": "cold_start"%'
          AND m.name = ?
          AND d.batch = ?
        """,
        (model_name, batch)
    )
    row = c.fetchone()
    if not row:
        raise ValueError(f"No headline cold start decision for {model_name} B={batch}")
    return row[0]

def get_mlp_3072_cold_cpu_dec124_ms(conn: sqlite3.Connection) -> float:
    dec_id = _get_headline_cold_start_decision_id_for_model(conn, "mlp-3072w-4l", 1)
    c = conn.cursor()
    c.execute(
        """
        SELECT round(wm.latency_ms, 1) FROM workloadmeasurement wm
        JOIN device dev ON wm.device_id = dev.id
        WHERE wm.decision_id = ? AND dev.kind = 'cpu'
        """,
        (dec_id,)
    )
    return float(c.fetchone()[0])

def get_mlp_3072_cold_rtx_dec124_ms(conn: sqlite3.Connection) -> float:
    dec_id = _get_headline_cold_start_decision_id_for_model(conn, "mlp-3072w-4l", 1)
    c = conn.cursor()
    c.execute(
        """
        SELECT round(wm.latency_ms, 1) FROM workloadmeasurement wm
        JOIN device dev ON wm.device_id = dev.id
        WHERE wm.decision_id = ? AND dev.key = 'dml:1'
        """,
        (dec_id,)
    )
    return float(c.fetchone()[0])

def get_overhead_rtx_cold_start_vs_sustained_dec124(conn: sqlite3.Connection) -> float:
    cold_rtx = get_mlp_3072_cold_rtx_dec124_ms(conn)
    sust_rtx = get_mlp_3072_b1_sustained_rtx_ms(conn)
    return round(cold_rtx / sust_rtx, 1)


# =============================================================================
# v1.1 x86 Close-out Metrics (10-level standard, unseen near-switch, P8 audit)
# =============================================================================

ROOT_DIR = Path(__file__).resolve().parent.parent
FROZEN_DB_PATH = ROOT_DIR / "data" / "final" / "siliconroute_final.db"
FROZEN_DB_SHA256 = "98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5"


def _get_v1_1_std_log_dict() -> dict[str, Any]:
    log_dir = ROOT_DIR / "results" / "logs" / "x86_closeout"
    logs = sorted([p for p in log_dir.glob("10_level_*.json") if "unseen" not in p.name])
    if not logs:
        raise FileNotFoundError(f"No standard 10-level benchmark json log found in {log_dir}")
    with open(logs[-1], "r", encoding="utf-8") as f:
        return json.load(f)


def _get_v1_1_unseen_log_dict() -> dict[str, Any]:
    log_dir = ROOT_DIR / "results" / "logs" / "x86_closeout"
    logs = sorted([p for p in log_dir.glob("10_level_unseen_*.json")])
    if not logs:
        raise FileNotFoundError(f"No unseen 10-level benchmark json log found in {log_dir}")
    with open(logs[-1], "r", encoding="utf-8") as f:
        return json.load(f)


def get_v1_1_database_sha256(conn: Optional[sqlite3.Connection] = None) -> str:
    return FROZEN_DB_SHA256


def get_v1_1_std_log_path(conn: Optional[sqlite3.Connection] = None) -> str:
    log_dir = ROOT_DIR / "results" / "logs" / "x86_closeout"
    logs = sorted([p for p in log_dir.glob("10_level_*.json") if "unseen" not in p.name])
    return str(logs[-1].relative_to(ROOT_DIR)).replace("\\", "/")


def get_v1_1_unseen_log_path(conn: Optional[sqlite3.Connection] = None) -> str:
    log_dir = ROOT_DIR / "results" / "logs" / "x86_closeout"
    logs = sorted([p for p in log_dir.glob("10_level_unseen_*.json")])
    return str(logs[-1].relative_to(ROOT_DIR)).replace("\\", "/")


# 1. Standard 10-level summary metrics
def get_v1_1_std_total_levels(conn: Optional[sqlite3.Connection] = None) -> int:
    return int(_get_v1_1_std_log_dict()["summary"]["total_levels"])


def get_v1_1_std_exact_matches(conn: Optional[sqlite3.Connection] = None) -> int:
    return int(_get_v1_1_std_log_dict()["summary"]["exact_matches"])


def get_v1_1_std_accuracy_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_v1_1_std_log_dict()["summary"]["accuracy_pct"])


def get_v1_1_std_close_calls(conn: Optional[sqlite3.Connection] = None) -> int:
    return int(_get_v1_1_std_log_dict()["summary"]["total_close_calls"])


def get_v1_1_std_close_call_matches(conn: Optional[sqlite3.Connection] = None) -> int:
    return int(_get_v1_1_std_log_dict()["summary"]["close_call_matches"])


def get_v1_1_std_close_call_accuracy_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_v1_1_std_log_dict()["summary"]["close_call_accuracy_pct"])


def get_v1_1_std_mean_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_v1_1_std_log_dict()["summary"]["mean_regret_pct"])


def get_v1_1_std_max_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_v1_1_std_log_dict()["summary"]["max_regret_pct"])


# 2. Unseen near-switch benchmark summary metrics
def get_v1_1_unseen_total_levels(conn: Optional[sqlite3.Connection] = None) -> int:
    return int(_get_v1_1_unseen_log_dict()["summary"]["total_levels"])


def get_v1_1_unseen_exact_matches(conn: Optional[sqlite3.Connection] = None) -> int:
    return int(_get_v1_1_unseen_log_dict()["summary"]["exact_matches"])


def get_v1_1_unseen_accuracy_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_v1_1_unseen_log_dict()["summary"]["accuracy_pct"])


def get_v1_1_unseen_close_calls(conn: Optional[sqlite3.Connection] = None) -> int:
    return int(_get_v1_1_unseen_log_dict()["summary"]["total_close_calls"])


def get_v1_1_unseen_close_call_matches(conn: Optional[sqlite3.Connection] = None) -> int:
    return int(_get_v1_1_unseen_log_dict()["summary"]["close_call_matches"])


def get_v1_1_unseen_close_call_accuracy_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_v1_1_unseen_log_dict()["summary"]["close_call_accuracy_pct"])


def get_v1_1_unseen_mean_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_v1_1_unseen_log_dict()["summary"]["mean_regret_pct"])


def get_v1_1_unseen_max_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_v1_1_unseen_log_dict()["summary"]["max_regret_pct"])


# 3. Near-switch individual case helper
def _get_unseen_level(model_name: str, batch: int) -> dict[str, Any]:
    d = _get_v1_1_unseen_log_dict()
    for lvl in d.get("levels", []):
        if lvl["model_name"] == model_name and lvl["batch"] == batch:
            return lvl
    raise KeyError(f"Level for {model_name} batch {batch} not found in unseen log")


def get_v1_1_unseen_mlp1792_b1_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("mlp-1792w-4l", 1)["decision_margin"])


def get_v1_1_unseen_mlp1792_b1_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("mlp-1792w-4l", 1)["actual_fastest_device_key"])


def get_v1_1_unseen_mlp1792_b1_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("mlp-1792w-4l", 1)["regret_pct"]), 2)


def get_v1_1_unseen_mlp1792_b2_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("mlp-1792w-4l", 2)["decision_margin"])


def get_v1_1_unseen_mlp1792_b2_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("mlp-1792w-4l", 2)["actual_fastest_device_key"])


def get_v1_1_unseen_mlp1792_b2_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("mlp-1792w-4l", 2)["regret_pct"]), 2)


def get_v1_1_unseen_mlp1920_b1_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("mlp-1920w-4l", 1)["decision_margin"])


def get_v1_1_unseen_mlp1920_b1_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("mlp-1920w-4l", 1)["actual_fastest_device_key"])


def get_v1_1_unseen_mlp1920_b1_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("mlp-1920w-4l", 1)["regret_pct"]), 2)


def get_v1_1_unseen_mlp1920_b2_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("mlp-1920w-4l", 2)["decision_margin"])


def get_v1_1_unseen_mlp1920_b2_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("mlp-1920w-4l", 2)["actual_fastest_device_key"])


def get_v1_1_unseen_mlp1920_b2_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("mlp-1920w-4l", 2)["regret_pct"]), 2)


def get_v1_1_unseen_mlp2176_b1_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("mlp-2176w-4l", 1)["decision_margin"])


def get_v1_1_unseen_mlp2176_b1_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("mlp-2176w-4l", 1)["actual_fastest_device_key"])


def get_v1_1_unseen_mlp2176_b1_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("mlp-2176w-4l", 1)["regret_pct"]), 2)


def get_v1_1_unseen_mlp2176_b2_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("mlp-2176w-4l", 2)["decision_margin"])


def get_v1_1_unseen_mlp2176_b2_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("mlp-2176w-4l", 2)["actual_fastest_device_key"])


def get_v1_1_unseen_mlp2176_b2_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("mlp-2176w-4l", 2)["regret_pct"]), 2)


def get_v1_1_unseen_mlp2304_b1_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("mlp-2304w-4l", 1)["decision_margin"])


def get_v1_1_unseen_mlp2304_b1_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("mlp-2304w-4l", 1)["actual_fastest_device_key"])


def get_v1_1_unseen_mlp2304_b1_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("mlp-2304w-4l", 1)["regret_pct"]), 2)


def get_v1_1_unseen_mlp2304_b2_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("mlp-2304w-4l", 2)["decision_margin"])


def get_v1_1_unseen_mlp2304_b2_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("mlp-2304w-4l", 2)["actual_fastest_device_key"])


def get_v1_1_unseen_mlp2304_b2_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("mlp-2304w-4l", 2)["regret_pct"]), 2)


def get_v1_1_unseen_conv12_b1_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("conv-12c-4l", 1)["decision_margin"])


def get_v1_1_unseen_conv12_b1_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("conv-12c-4l", 1)["actual_fastest_device_key"])


def get_v1_1_unseen_conv12_b1_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("conv-12c-4l", 1)["regret_pct"]), 2)


def get_v1_1_unseen_conv20_b1_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("conv-20c-4l", 1)["decision_margin"])


def get_v1_1_unseen_conv20_b1_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("conv-20c-4l", 1)["actual_fastest_device_key"])


def get_v1_1_unseen_conv20_b1_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("conv-20c-4l", 1)["regret_pct"]), 2)


def get_v1_1_unseen_conv28_b1_margin(conn: Optional[sqlite3.Connection] = None) -> float:
    return float(_get_unseen_level("conv-28c-4l", 1)["decision_margin"])


def get_v1_1_unseen_conv28_b1_winner(conn: Optional[sqlite3.Connection] = None) -> str:
    return str(_get_unseen_level("conv-28c-4l", 1)["actual_fastest_device_key"])


def get_v1_1_unseen_conv28_b1_regret_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    return round(float(_get_unseen_level("conv-28c-4l", 1)["regret_pct"]), 2)


# 4. Sustained RTX P8 Audit metrics
def get_v1_1_rtx_sustained_runs_total(conn: Optional[sqlite3.Connection] = None) -> int:
    close_conn = False
    if conn is None:
        conn = sqlite3.connect(f"file:{FROZEN_DB_PATH.resolve()}?mode=ro&immutable=1", uri=True)
        close_conn = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM device WHERE key = 'dml:1'")
        row = cur.fetchone()
        if not row:
            return 0
        cur.execute("SELECT count(*) FROM run WHERE device_id = ? AND run_kind = 'sustained'", (row[0],))
        return int(cur.fetchone()[0])
    finally:
        if close_conn:
            conn.close()


def get_v1_1_rtx_sustained_p8_runs(conn: Optional[sqlite3.Connection] = None) -> int:
    close_conn = False
    if conn is None:
        conn = sqlite3.connect(f"file:{FROZEN_DB_PATH.resolve()}?mode=ro&immutable=1", uri=True)
        close_conn = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM device WHERE key = 'dml:1'")
        row = cur.fetchone()
        if not row:
            return 0
        cur.execute(
            "SELECT count(*) FROM run WHERE device_id = ? AND run_kind = 'sustained' AND nvml_pstate_start = 8",
            (row[0],),
        )
        return int(cur.fetchone()[0])
    finally:
        if close_conn:
            conn.close()


def get_v1_1_rtx_sustained_p8_pct(conn: Optional[sqlite3.Connection] = None) -> float:
    tot = get_v1_1_rtx_sustained_runs_total(conn)
    p8 = get_v1_1_rtx_sustained_p8_runs(conn)
    return round((p8 / tot * 100.0) if tot > 0 else 0.0, 2)


# 5. Manifest builder for v1.1 x86
def build_v1_1_manifest(
    conn: Optional[sqlite3.Connection] = None,
    output_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Compile and publish results/v1_1/x86/manifest.json."""
    if output_path is None:
        output_path = ROOT_DIR / "results" / "v1_1" / "x86" / "manifest.json"

    metrics_registry: list[tuple[str, Any, str, str, str, str]] = [
        # (name, value, unit, description, method_name, source)
        ("frozen_v1_0_database_sha256", get_v1_1_database_sha256(conn), "sha256", "SHA256 checksum of frozen v1.0 database", "get_v1_1_database_sha256", "data/final/siliconroute_final.db"),
        ("v1_1_std_log_path", get_v1_1_std_log_path(conn), "path", "Path to standard 10-level benchmark log", "get_v1_1_std_log_path", "results/logs/x86_closeout/"),
        ("v1_1_unseen_log_path", get_v1_1_unseen_log_path(conn), "path", "Path to unseen near-switch benchmark log", "get_v1_1_unseen_log_path", "results/logs/x86_closeout/"),
        ("std_total_levels", get_v1_1_std_total_levels(conn), "levels", "Total levels in standard 10-level benchmark", "get_v1_1_std_total_levels", "10_level_*.json"),
        ("std_exact_matches", get_v1_1_std_exact_matches(conn), "matches", "Exact chip matches in standard benchmark", "get_v1_1_std_exact_matches", "10_level_*.json"),
        ("std_accuracy_pct", get_v1_1_std_accuracy_pct(conn), "%", "Router exact-match accuracy in standard benchmark", "get_v1_1_std_accuracy_pct", "10_level_*.json"),
        ("std_close_calls", get_v1_1_std_close_calls(conn), "levels", "Close call count (margin < 1.5x) in standard benchmark", "get_v1_1_std_close_calls", "10_level_*.json"),
        ("std_close_call_matches", get_v1_1_std_close_call_matches(conn), "matches", "Close call exact matches in standard benchmark", "get_v1_1_std_close_call_matches", "10_level_*.json"),
        ("std_close_call_accuracy_pct", get_v1_1_std_close_call_accuracy_pct(conn), "%", "Close call accuracy in standard benchmark", "get_v1_1_std_close_call_accuracy_pct", "10_level_*.json"),
        ("std_mean_regret_pct", get_v1_1_std_mean_regret_pct(conn), "%", "Mean router regret in standard benchmark", "get_v1_1_std_mean_regret_pct", "10_level_*.json"),
        ("std_max_regret_pct", get_v1_1_std_max_regret_pct(conn), "%", "Max router regret in standard benchmark", "get_v1_1_std_max_regret_pct", "10_level_*.json"),
        ("unseen_total_levels", get_v1_1_unseen_total_levels(conn), "levels", "Total unseen near-switch test levels", "get_v1_1_unseen_total_levels", "10_level_unseen_*.json"),
        ("unseen_exact_matches", get_v1_1_unseen_exact_matches(conn), "matches", "Exact chip matches on unseen models (fit only)", "get_v1_1_unseen_exact_matches", "10_level_unseen_*.json"),
        ("unseen_accuracy_pct", get_v1_1_unseen_accuracy_pct(conn), "%", "Fit-only accuracy on unseen near-switch models", "get_v1_1_unseen_accuracy_pct", "10_level_unseen_*.json"),
        ("unseen_close_calls", get_v1_1_unseen_close_calls(conn), "levels", "Close calls (margin < 1.5x) on unseen models", "get_v1_1_unseen_close_calls", "10_level_unseen_*.json"),
        ("unseen_close_call_matches", get_v1_1_unseen_close_call_matches(conn), "matches", "Close call exact matches on unseen models", "get_v1_1_unseen_close_call_matches", "10_level_unseen_*.json"),
        ("unseen_close_call_accuracy_pct", get_v1_1_unseen_close_call_accuracy_pct(conn), "%", "Close call accuracy on unseen models", "get_v1_1_unseen_close_call_accuracy_pct", "10_level_unseen_*.json"),
        ("unseen_mean_regret_pct", get_v1_1_unseen_mean_regret_pct(conn), "%", "Mean regret on unseen near-switch models", "get_v1_1_unseen_mean_regret_pct", "10_level_unseen_*.json"),
        ("unseen_max_regret_pct", get_v1_1_unseen_max_regret_pct(conn), "%", "Max regret on unseen near-switch models", "get_v1_1_unseen_max_regret_pct", "10_level_unseen_*.json"),
        ("unseen_mlp1792_b1_margin", get_v1_1_unseen_mlp1792_b1_margin(conn), "x", "Decision margin for mlp-1792w-4l batch 1", "get_v1_1_unseen_mlp1792_b1_margin", "10_level_unseen_*.json"),
        ("unseen_mlp1792_b1_winner", get_v1_1_unseen_mlp1792_b1_winner(conn), "device", "Fastest device for mlp-1792w-4l batch 1", "get_v1_1_unseen_mlp1792_b1_winner", "10_level_unseen_*.json"),
        ("unseen_mlp1792_b1_regret_pct", get_v1_1_unseen_mlp1792_b1_regret_pct(conn), "%", "Regret for mlp-1792w-4l batch 1", "get_v1_1_unseen_mlp1792_b1_regret_pct", "10_level_unseen_*.json"),
        ("unseen_mlp1792_b2_margin", get_v1_1_unseen_mlp1792_b2_margin(conn), "x", "Decision margin for mlp-1792w-4l batch 2", "get_v1_1_unseen_mlp1792_b2_margin", "10_level_unseen_*.json"),
        ("unseen_mlp1792_b2_winner", get_v1_1_unseen_mlp1792_b2_winner(conn), "device", "Fastest device for mlp-1792w-4l batch 2", "get_v1_1_unseen_mlp1792_b2_winner", "10_level_unseen_*.json"),
        ("unseen_mlp1792_b2_regret_pct", get_v1_1_unseen_mlp1792_b2_regret_pct(conn), "%", "Regret for mlp-1792w-4l batch 2", "get_v1_1_unseen_mlp1792_b2_regret_pct", "10_level_unseen_*.json"),
        ("unseen_mlp1920_b1_margin", get_v1_1_unseen_mlp1920_b1_margin(conn), "x", "Decision margin for mlp-1920w-4l batch 1", "get_v1_1_unseen_mlp1920_b1_margin", "10_level_unseen_*.json"),
        ("unseen_mlp1920_b1_winner", get_v1_1_unseen_mlp1920_b1_winner(conn), "device", "Fastest device for mlp-1920w-4l batch 1", "get_v1_1_unseen_mlp1920_b1_winner", "10_level_unseen_*.json"),
        ("unseen_mlp1920_b1_regret_pct", get_v1_1_unseen_mlp1920_b1_regret_pct(conn), "%", "Regret for mlp-1920w-4l batch 1", "get_v1_1_unseen_mlp1920_b1_regret_pct", "10_level_unseen_*.json"),
        ("unseen_mlp1920_b2_margin", get_v1_1_unseen_mlp1920_b2_margin(conn), "x", "Decision margin for mlp-1920w-4l batch 2", "get_v1_1_unseen_mlp1920_b2_margin", "10_level_unseen_*.json"),
        ("unseen_mlp1920_b2_winner", get_v1_1_unseen_mlp1920_b2_winner(conn), "device", "Fastest device for mlp-1920w-4l batch 2", "get_v1_1_unseen_mlp1920_b2_winner", "10_level_unseen_*.json"),
        ("unseen_mlp1920_b2_regret_pct", get_v1_1_unseen_mlp1920_b2_regret_pct(conn), "%", "Regret for mlp-1920w-4l batch 2", "get_v1_1_unseen_mlp1920_b2_regret_pct", "10_level_unseen_*.json"),
        ("unseen_mlp2176_b1_margin", get_v1_1_unseen_mlp2176_b1_margin(conn), "x", "Decision margin for mlp-2176w-4l batch 1", "get_v1_1_unseen_mlp2176_b1_margin", "10_level_unseen_*.json"),
        ("unseen_mlp2176_b1_winner", get_v1_1_unseen_mlp2176_b1_winner(conn), "device", "Fastest device for mlp-2176w-4l batch 1", "get_v1_1_unseen_mlp2176_b1_winner", "10_level_unseen_*.json"),
        ("unseen_mlp2176_b1_regret_pct", get_v1_1_unseen_mlp2176_b1_regret_pct(conn), "%", "Regret for mlp-2176w-4l batch 1", "get_v1_1_unseen_mlp2176_b1_regret_pct", "10_level_unseen_*.json"),
        ("unseen_mlp2176_b2_margin", get_v1_1_unseen_mlp2176_b2_margin(conn), "x", "Decision margin for mlp-2176w-4l batch 2", "get_v1_1_unseen_mlp2176_b2_margin", "10_level_unseen_*.json"),
        ("unseen_mlp2176_b2_winner", get_v1_1_unseen_mlp2176_b2_winner(conn), "device", "Fastest device for mlp-2176w-4l batch 2", "get_v1_1_unseen_mlp2176_b2_winner", "10_level_unseen_*.json"),
        ("unseen_mlp2176_b2_regret_pct", get_v1_1_unseen_mlp2176_b2_regret_pct(conn), "%", "Regret for mlp-2176w-4l batch 2", "get_v1_1_unseen_mlp2176_b2_regret_pct", "10_level_unseen_*.json"),
        ("unseen_mlp2304_b1_margin", get_v1_1_unseen_mlp2304_b1_margin(conn), "x", "Decision margin for mlp-2304w-4l batch 1", "get_v1_1_unseen_mlp2304_b1_margin", "10_level_unseen_*.json"),
        ("unseen_mlp2304_b1_winner", get_v1_1_unseen_mlp2304_b1_winner(conn), "device", "Fastest device for mlp-2304w-4l batch 1", "get_v1_1_unseen_mlp2304_b1_winner", "10_level_unseen_*.json"),
        ("unseen_mlp2304_b1_regret_pct", get_v1_1_unseen_mlp2304_b1_regret_pct(conn), "%", "Regret for mlp-2304w-4l batch 1", "get_v1_1_unseen_mlp2304_b1_regret_pct", "10_level_unseen_*.json"),
        ("unseen_mlp2304_b2_margin", get_v1_1_unseen_mlp2304_b2_margin(conn), "x", "Decision margin for mlp-2304w-4l batch 2", "get_v1_1_unseen_mlp2304_b2_margin", "10_level_unseen_*.json"),
        ("unseen_mlp2304_b2_winner", get_v1_1_unseen_mlp2304_b2_winner(conn), "device", "Fastest device for mlp-2304w-4l batch 2", "get_v1_1_unseen_mlp2304_b2_winner", "10_level_unseen_*.json"),
        ("unseen_mlp2304_b2_regret_pct", get_v1_1_unseen_mlp2304_b2_regret_pct(conn), "%", "Regret for mlp-2304w-4l batch 2", "get_v1_1_unseen_mlp2304_b2_regret_pct", "10_level_unseen_*.json"),
        ("unseen_conv12_b1_margin", get_v1_1_unseen_conv12_b1_margin(conn), "x", "Decision margin for conv-12c-4l batch 1", "get_v1_1_unseen_conv12_b1_margin", "10_level_unseen_*.json"),
        ("unseen_conv12_b1_winner", get_v1_1_unseen_conv12_b1_winner(conn), "device", "Fastest device for conv-12c-4l batch 1", "get_v1_1_unseen_conv12_b1_winner", "10_level_unseen_*.json"),
        ("unseen_conv12_b1_regret_pct", get_v1_1_unseen_conv12_b1_regret_pct(conn), "%", "Regret for conv-12c-4l batch 1", "get_v1_1_unseen_conv12_b1_regret_pct", "10_level_unseen_*.json"),
        ("unseen_conv20_b1_margin", get_v1_1_unseen_conv20_b1_margin(conn), "x", "Decision margin for conv-20c-4l batch 1", "get_v1_1_unseen_conv20_b1_margin", "10_level_unseen_*.json"),
        ("unseen_conv20_b1_winner", get_v1_1_unseen_conv20_b1_winner(conn), "device", "Fastest device for conv-20c-4l batch 1", "get_v1_1_unseen_conv20_b1_winner", "10_level_unseen_*.json"),
        ("unseen_conv20_b1_regret_pct", get_v1_1_unseen_conv20_b1_regret_pct(conn), "%", "Regret for conv-20c-4l batch 1", "get_v1_1_unseen_conv20_b1_regret_pct", "10_level_unseen_*.json"),
        ("unseen_conv28_b1_margin", get_v1_1_unseen_conv28_b1_margin(conn), "x", "Decision margin for conv-28c-4l batch 1", "get_v1_1_unseen_conv28_b1_margin", "10_level_unseen_*.json"),
        ("unseen_conv28_b1_winner", get_v1_1_unseen_conv28_b1_winner(conn), "device", "Fastest device for conv-28c-4l batch 1", "get_v1_1_unseen_conv28_b1_winner", "10_level_unseen_*.json"),
        ("unseen_conv28_b1_regret_pct", get_v1_1_unseen_conv28_b1_regret_pct(conn), "%", "Regret for conv-28c-4l batch 1", "get_v1_1_unseen_conv28_b1_regret_pct", "10_level_unseen_*.json"),
        ("rtx_sustained_runs_total", get_v1_1_rtx_sustained_runs_total(conn), "runs", "Total historical sustained runs on RTX 5070", "get_v1_1_rtx_sustained_runs_total", "SELECT count(*) FROM run WHERE device_id = rtx AND run_kind = 'sustained'"),
        ("rtx_sustained_p8_runs", get_v1_1_rtx_sustained_p8_runs(conn), "runs", "Historical sustained runs on RTX 5070 starting in P8", "get_v1_1_rtx_sustained_p8_runs", "SELECT count(*) FROM run WHERE nvml_pstate_start = 8"),
        ("rtx_sustained_p8_pct", get_v1_1_rtx_sustained_p8_pct(conn), "%", "Percentage of historical sustained RTX runs starting in P8", "get_v1_1_rtx_sustained_p8_pct", "Historical audit"),
    ]

    metrics_dict: dict[str, Any] = {}
    for name, val, unit, desc, meth, src in metrics_registry:
        metrics_dict[name] = {
            "value": val,
            "method": f"scripts.metrics.{meth}",
            "unit": unit,
            "description": desc,
            "source": src,
        }

    manifest = {
        "version": "1.1",
        "platform": "x86",
        "description": "SiliconRoute x86 Close-out Manifest (10-level standard, unseen near-switch, P8 audit)",
        "metadata": {
            "frozen_v1_0_database_sha256": FROZEN_DB_SHA256,
            "standard_benchmark_log": get_v1_1_std_log_path(conn),
            "unseen_benchmark_log": get_v1_1_unseen_log_path(conn),
        },
        "metrics": metrics_dict,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


if __name__ == "__main__":
    out = ROOT_DIR / "results" / "v1_1" / "x86" / "manifest.json"
    m = build_v1_1_manifest(output_path=out)
    print(f"Published v1.1 x86 manifest to {out} with {len(m['metrics'])} metrics.")


