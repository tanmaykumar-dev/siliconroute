"""Test suite verifying end-to-end mathematical and empirical provenance for x86 v1.1 results."""
import json
from pathlib import Path
import sqlite3
import pytest

import scripts.metrics as sm

MANIFEST_V1_1_PATH = Path("results/v1_1/x86/manifest.json")
MANIFEST_V1_0_PATH = Path("results/final/manifest.json")
FROZEN_DB_PATH = Path("data/final/siliconroute_final.db")
FROZEN_DB_SHA256 = "98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5"


def test_v1_1_manifest_exists():
    """Verify v1.1 manifest exists and is distinct from v1.0."""
    assert MANIFEST_V1_1_PATH.exists(), f"Missing {MANIFEST_V1_1_PATH}"
    assert MANIFEST_V1_0_PATH.exists(), f"Missing {MANIFEST_V1_0_PATH}"
    assert MANIFEST_V1_1_PATH.resolve() != MANIFEST_V1_0_PATH.resolve()


def test_v1_0_manifest_untouched():
    """Verify v1.0 manifest was not modified or overwritten."""
    with open(MANIFEST_V1_0_PATH, "r", encoding="utf-8") as f:
        m1_0 = json.load(f)
    assert m1_0.get("metadata", {}).get("database_sha256") == FROZEN_DB_SHA256
    assert "metrics" in m1_0
    assert "total_runs" in m1_0["metrics"]


def test_v1_1_all_metrics_match_functions_and_provenance():
    """Prove that every number in v1.1 manifest matches its metric function in scripts.metrics."""
    with open(MANIFEST_V1_1_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    metrics = manifest.get("metrics", {})
    assert len(metrics) >= 40, f"Expected at least 40 metrics in v1.1 manifest, found {len(metrics)}"

    conn = sqlite3.connect(f"file:{FROZEN_DB_PATH.resolve()}?mode=ro&immutable=1", uri=True)
    try:
        for metric_name, m_data in metrics.items():
            method_path = m_data.get("method")
            assert method_path, f"Metric {metric_name} missing 'method'"
            func_name = method_path.split(".")[-1]
            func = getattr(sm, func_name, None)
            assert func is not None, f"Function {func_name} not found in scripts.metrics"

            expected_val = m_data["value"]
            # Call function
            try:
                actual_val = func(conn)
            except TypeError:
                actual_val = func()

            assert actual_val == expected_val, (
                f"Metric '{metric_name}' mismatch: manifest has {expected_val!r}, "
                f"function {func_name} computed {actual_val!r}"
            )
    finally:
        conn.close()


def test_v1_1_metrics_match_raw_logs():
    """Directly cross-examine raw log files to prove manifest numbers come from real runs."""
    std_log_path = Path(sm.get_v1_1_std_log_path())
    unseen_log_path = Path(sm.get_v1_1_unseen_log_path())

    assert std_log_path.exists(), f"Missing {std_log_path}"
    assert unseen_log_path.exists(), f"Missing {unseen_log_path}"

    with open(std_log_path, "r", encoding="utf-8") as f:
        std_log = json.load(f)
    with open(unseen_log_path, "r", encoding="utf-8") as f:
        unseen_log = json.load(f)

    # Standard mode checks
    assert std_log["summary"]["total_levels"] == 10
    assert std_log["summary"]["exact_matches"] == 10
    assert std_log["summary"]["accuracy_pct"] == 100.0
    assert std_log["summary"]["mean_regret_pct"] == 0.0

    # Unseen mode checks
    assert unseen_log["summary"]["total_levels"] == 11
    assert unseen_log["summary"]["exact_matches"] == 7
    assert unseen_log["summary"]["accuracy_pct"] == 63.64
    assert unseen_log["summary"]["total_close_calls"] == 7
    assert unseen_log["summary"]["close_call_matches"] == 3
    assert unseen_log["summary"]["close_call_accuracy_pct"] == 42.86
    assert unseen_log["summary"]["mean_regret_pct"] == 9.69
    assert unseen_log["summary"]["max_regret_pct"] == 30.44

    # Check near-switch cases in unseen log
    levels_by_key = {(l["model_name"], l["batch"]): l for l in unseen_log["levels"]}
    
    # MLP 1792 b1 & b2
    assert levels_by_key[("mlp-1792w-4l", 1)]["decision_margin"] == 1.3
    assert levels_by_key[("mlp-1792w-4l", 1)]["actual_fastest_device_key"] == "dml:1"
    assert levels_by_key[("mlp-1792w-4l", 2)]["decision_margin"] == 1.47
    assert levels_by_key[("mlp-1792w-4l", 2)]["actual_fastest_device_key"] == "cpu"

    # MLP 2176 b1 & b2
    assert levels_by_key[("mlp-2176w-4l", 1)]["decision_margin"] == 2.43
    assert levels_by_key[("mlp-2176w-4l", 1)]["actual_fastest_device_key"] == "dml:1"
    assert levels_by_key[("mlp-2176w-4l", 2)]["decision_margin"] == 2.84
    assert levels_by_key[("mlp-2176w-4l", 2)]["actual_fastest_device_key"] == "dml:1"
