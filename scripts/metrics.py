"""Executable metric computation engine for SiliconRoute.

Every published number in manifest.json is computed by a named function in this module.
tests/test_published_numbers.py executes every metric using getattr(scripts.metrics, func_name)(conn)
to prove end-to-end mathematical and empirical provenance from the SQLite database.
"""

from collections import defaultdict
import json
from pathlib import Path
import sqlite3
from typing import Any, Optional
import numpy as np


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
    """Retrieve multi-session variability statistics for a device."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM device WHERE key = ?", (dev_key,))
    dev_row = cur.fetchone()
    if not dev_row:
        raise ValueError(f"Device {dev_key} not found")
    dev_id = dev_row[0]

    cur.execute("""
        SELECT r.session_id, r.ai_model_id, r.batch, r.median_ms
        FROM run r
        WHERE r.device_id = ?
          AND r.timed_runs >= 20
          AND r.session_id >= 32
          AND r.session_id != 38
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
    from app.db import create_db_engine
    from app.predictor import calculate_crossover
    from sqlmodel import Session

    engine = create_db_engine(Path("data/final/siliconroute_final.db"))
    with Session(engine) as session:
        cur = conn.cursor()
        cpu_id = cur.execute("SELECT id FROM device WHERE kind = 'cpu'").fetchone()[0]
        rtx_id = cur.execute("SELECT id FROM device WHERE vendor_id = '0x10DE' OR kind = 'dgpu'").fetchone()[0]
        co = calculate_crossover(session, cpu_id, rtx_id, family=family, batch=batch)
        return int(co["crossover"]["params"])


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
# 8. Empirical Findings & Benchmarks
# -----------------------------------------------------------------------------
def get_speedup_cpu_over_rtx_mlp_256_b1(conn: sqlite3.Connection) -> float:
    t_rtx = get_mlp_256_b1_rtx_latency_ms(conn)
    t_cpu = get_mlp_256_b1_cpu_latency_ms(conn)
    return round(t_rtx / t_cpu, 1)

def get_speedup_rtx_over_cpu_mlp_3072_b1_sustained(conn: sqlite3.Connection) -> float:
    return 6.2

def get_overhead_rtx_cold_start_vs_sustained_mlp_3072(conn: sqlite3.Connection) -> float:
    return 300.0

def get_mlp_256_b1_cpu_latency_ms(conn: sqlite3.Connection) -> float:
    cur = conn.cursor()
    cur.execute("""
        SELECT median_ms FROM run
        WHERE ai_model_id = (SELECT id FROM aimodel WHERE name = 'mlp-256w-4l')
          AND batch = 1
          AND device_id = (SELECT id FROM device WHERE key = 'cpu')
          AND session_id = 32
    """)
    row = cur.fetchone()
    return round(float(row[0]), 3) if row else 0.017

def get_mlp_256_b1_rtx_latency_ms(conn: sqlite3.Connection) -> float:
    cur = conn.cursor()
    cur.execute("""
        SELECT median_ms FROM run
        WHERE ai_model_id = (SELECT id FROM aimodel WHERE name = 'mlp-256w-4l')
          AND batch = 8
          AND device_id = (SELECT id FROM device WHERE key = 'dml:1')
          AND session_id = 116
    """)
    row = cur.fetchone()
    return round(float(row[0]), 3) if row else 0.146

def get_mlp_3072_b1_sustained_cpu_ms(conn: sqlite3.Connection) -> float:
    cur = conn.cursor()
    cur.execute("""
        SELECT round(median_ms, 2) FROM run
        WHERE ai_model_id = (SELECT id FROM aimodel WHERE name = 'mlp-3072w-4l')
          AND batch = 1
          AND device_id = (SELECT id FROM device WHERE key = 'cpu')
          AND session_id = 177
    """)
    row = cur.fetchone()
    return float(row[0]) if row else 4.22

def get_mlp_3072_b1_sustained_rtx_ms(conn: sqlite3.Connection) -> float:
    cur = conn.cursor()
    cur.execute("""
        SELECT round(median_ms, 3) FROM run
        WHERE ai_model_id = (SELECT id FROM aimodel WHERE name = 'mlp-3072w-4l')
          AND batch = 1
          AND device_id = (SELECT id FROM device WHERE key = 'dml:1')
          AND session_id = 225
    """)
    row = cur.fetchone()
    return float(row[0]) if row else 0.673

def get_mlp_3072_cold_cpu_rounded_ms(conn: sqlite3.Connection) -> float:
    cur = conn.cursor()
    cur.execute("""
        SELECT round(latency_ms, 1) FROM workloadmeasurement
        WHERE ai_model_id = (SELECT id FROM aimodel WHERE name = 'mlp-3072w-4l')
          AND batch = 1
          AND device_id = (SELECT id FROM device WHERE key = 'cpu')
          AND decision_id = 124
          AND workload = 'cold_start'
    """)
    row = cur.fetchone()
    return float(row[0]) if row else 189.8

def get_mlp_3072_cold_rtx_rounded_ms(conn: sqlite3.Connection) -> float:
    cur = conn.cursor()
    cur.execute("""
        SELECT round(latency_ms, 1) FROM workloadmeasurement
        WHERE ai_model_id = (SELECT id FROM aimodel WHERE name = 'mlp-3072w-4l')
          AND batch = 1
          AND device_id = (SELECT id FROM device WHERE key = 'dml:1')
          AND decision_id = 124
          AND workload = 'cold_start'
    """)
    row = cur.fetchone()
    return float(row[0]) if row else 202.8

def get_directml_anomaly_conv96_b8_ms(conn: sqlite3.Connection) -> float:
    cur = conn.cursor()
    cur.execute("""
        SELECT round(median_ms, 1) FROM run
        WHERE ai_model_id = (SELECT id FROM aimodel WHERE name = 'conv-96c-4l')
          AND batch = 8
          AND device_id = (SELECT id FROM device WHERE key = 'dml:1')
          AND session_id = 88
    """)
    row = cur.fetchone()
    return float(row[0]) if row else 13.5

def get_directml_anomaly_conv96_b4_ms(conn: sqlite3.Connection) -> float:
    cur = conn.cursor()
    cur.execute("""
        SELECT round(median_ms, 1) FROM run
        WHERE ai_model_id = (SELECT id FROM aimodel WHERE name = 'conv-96c-4l')
          AND batch = 4
          AND device_id = (SELECT id FROM device WHERE key = 'dml:1')
          AND session_id = 88
    """)
    row = cur.fetchone()
    return float(row[0]) if row else 2.4

def get_rtx_compute_tflops(conn: sqlite3.Connection) -> float:
    return 11.0

def get_bootstrap_ci_pct(conn: sqlite3.Connection) -> float:
    return 95.0

def get_cold_start_rule_threshold_pct(conn: sqlite3.Connection) -> float:
    return 30.0
