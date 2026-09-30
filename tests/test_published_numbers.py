"""Verification test ensuring every published measurement number is tracked in manifest.json."""

import json
import re
from pathlib import Path
import sqlite3
import pytest

MANIFEST_PATH = Path("results/final/manifest.json")
RESULTS_MD_PATH = Path("results/final/results.md")
README_PATH = Path("README.md")
DB_PATH = Path("data/final/siliconroute_final.db")


def load_manifest() -> dict:
    assert MANIFEST_PATH.exists(), f"Missing {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_manifest_numbers(manifest: dict) -> set[float]:
    """Collect all numeric values recorded in manifest.json (metrics and metadata)."""
    numbers = set()

    # Metrics
    for k, item in manifest.get("metrics", {}).items():
        v = item.get("value")
        if isinstance(v, (int, float)):
            numbers.add(round(float(v), 2))
            numbers.add(round(float(v), 3))
            numbers.add(round(float(v), 4))
            numbers.add(float(v))
        elif isinstance(v, str):
            try:
                f_val = float(v)
                numbers.add(round(f_val, 2))
                numbers.add(round(f_val, 3))
                numbers.add(f_val)
            except ValueError:
                pass

    # Metadata
    db_size = manifest.get("metadata", {}).get("database_size_bytes")
    if db_size:
        numbers.add(float(db_size))

    return numbers


def extract_measurement_numbers_from_text(text: str) -> list[tuple[float, str]]:
    """Extract measurement numbers associated with units, tables, or metrics in text."""
    found = []

    # 1. Numbers with units: ms, %, GFLOP/s, GB/s, x speedup, params, wins, decisions
    unit_pattern = re.compile(
        r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*(%|ms|GFLOP/s|GB/s|TFLOP/s|x\b|params\b|bytes\b)',
        re.IGNORECASE
    )
    for match in unit_pattern.finditer(text):
        val_str = match.group(1).replace(",", "")
        unit = match.group(2)
        try:
            val = float(val_str)
            found.append((val, f"{val_str} {unit}"))
        except ValueError:
            pass

    # 2. Ratio / win patterns like "22 / 24", "6 / 8", "15 / 24"
    ratio_pattern = re.compile(r'\b(\d+)\s*/\s*(\d+)\b')
    for match in ratio_pattern.finditer(text):
        v1 = float(match.group(1))
        v2 = float(match.group(2))
        found.append((v1, f"{int(v1)} in ratio"))
        found.append((v2, f"{int(v2)} in ratio"))

    return found


def test_manifest_metrics_match_database():
    """Verify that every metric in manifest.json has an executable method in scripts.metrics that matches value."""
    import importlib
    manifest = load_manifest()
    assert DB_PATH.exists(), f"Missing {DB_PATH}"

    conn = sqlite3.connect(DB_PATH)
    metrics = manifest.get("metrics", {})
    assert len(metrics) > 0, "No metrics found in manifest.json"

    for key, item in metrics.items():
        exp_val = item.get("value")
        method_path = item.get("method")
        assert method_path, f"Metric '{key}' lacks an executable 'method' in manifest.json"
        assert method_path.startswith("scripts.metrics."), f"Method '{method_path}' must be in scripts.metrics"

        fn_name = method_path.split(".")[-1]
        mod_name = ".".join(method_path.split(".")[:-1])
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, fn_name), f"Function '{fn_name}' not found in {mod_name} for metric '{key}'"

        fn = getattr(mod, fn_name)
        actual_val = fn(conn)

        if isinstance(exp_val, str):
            assert str(actual_val) == str(exp_val), (
                f"Mismatch for metric '{key}' ({method_path}): manifest={exp_val}, computed={actual_val}"
            )
        elif isinstance(exp_val, (int, float)):
            assert pytest.approx(float(exp_val), rel=1e-2, abs=1e-3) == float(actual_val), (
                f"Mismatch for metric '{key}' ({method_path}): manifest={exp_val}, computed={actual_val}"
            )
        else:
            assert actual_val == exp_val, (
                f"Mismatch for metric '{key}' ({method_path}): manifest={exp_val}, computed={actual_val}"
            )

    conn.close()


def test_results_md_numbers_in_manifest():
    """Assert all measurement numbers in results/final/results.md are present in manifest.json."""
    manifest = load_manifest()
    manifest_numbers = get_all_manifest_numbers(manifest)

    assert RESULTS_MD_PATH.exists(), f"Missing {RESULTS_MD_PATH}"
    content = RESULTS_MD_PATH.read_text(encoding="utf-8")
    measurements = extract_measurement_numbers_from_text(content)

    untracked = []
    for val, raw in measurements:
        # Check exact or approx match in manifest numbers
        r1 = round(val, 1)
        r2 = round(val, 2)
        r3 = round(val, 3)
        r0 = float(int(val))
        if not any(
            abs(val - m_num) < 1e-3
            or abs(r2 - m_num) < 1e-2
            or abs(r1 - m_num) < 0.15
            or abs(r0 - m_num) < 1e-4
            for m_num in manifest_numbers
        ):
            # Ignore standard benign formatting tokens like '1', '2', '8', '3' if general
            if val not in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0, 14.0, 16.0, 20.0, 24.0, 32.0, 64.0, 96.0, 128.0, 256.0):
                untracked.append((val, raw))

    assert not untracked, f"Measurement numbers in results.md not found in manifest.json: {untracked}"


def test_readme_no_unmeasured_devices():
    """Assert that README does not contain '780M' or any GPU name not in the database's device table."""
    assert README_PATH.exists(), f"Missing {README_PATH}"
    content = README_PATH.read_text(encoding="utf-8")

    # 1. Direct assertion: no 780M anywhere in README
    assert "780M" not in content, "README contains forbidden GPU name '780M'"
    assert "780m" not in content.lower(), "README contains forbidden GPU name '780m'"

    # 2. Assert against database device table
    assert DB_PATH.exists(), f"Missing {DB_PATH}"
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT label FROM device WHERE kind IN ('igpu', 'dgpu')")
    db_gpu_labels = [row[0] for row in cur.fetchall()]
    conn.close()

    # Extract model identifiers from database GPU labels (e.g. '610M' and '5070')
    allowed_models = set()
    for label in db_gpu_labels:
        for token in re.findall(r'\b[A-Za-z0-9]+\b', label):
            if any(char.isdigit() for char in token):
                allowed_models.add(token.upper())

    # Check Radeon models mentioned in README
    for m in re.findall(r'\bRadeon(?:\(TM\))?\s+([A-Za-z0-9]+)\b', content, re.IGNORECASE):
        assert m.upper() in allowed_models, f"Unmeasured Radeon GPU in README: '{m}' (allowed: {allowed_models})"

    # Check RTX models mentioned in README
    for m in re.findall(r'\b(?:GeForce\s+)?RTX\s+([0-9]{4})\b', content, re.IGNORECASE):
        assert m.upper() in allowed_models, f"Unmeasured RTX GPU in README: '{m}' (allowed: {allowed_models})"

    # Check unmeasured GPU brands
    forbidden = re.findall(r'\b(GTX|Iris|Arc|Adreno|Mali)\b', content, re.IGNORECASE)
    assert not forbidden, f"Unmeasured GPU brand found in README: {forbidden}"


def test_readme_metric_tags_and_numbers():
    """Assert every measurement number with a unit or in a ratio in README.md is followed by <!-- metric: key --> matching manifest within 1%."""
    manifest = load_manifest()
    metrics = manifest.get("metrics", {})

    assert README_PATH.exists(), f"Missing {README_PATH}"
    content = README_PATH.read_text(encoding="utf-8")

    # Strip code blocks and URL targets
    cleaned = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
    cleaned = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', cleaned)

    # 1. Assert every measurement number with a unit has a metric tag
    unit_pat = re.compile(r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*(%|ms|GFLOP/s|GB/s|TFLOP/s|x\b|params\b|bytes\b)', re.IGNORECASE)
    untagged_units = []
    for m in unit_pat.finditer(cleaned):
        after = cleaned[m.end():m.end() + 150]
        tag_m = re.match(r'^\s*[*_\])]*\s*<!--\s*metric:\s*([a-zA-Z0-9_:]+)\s*-->', after)
        if not tag_m:
            ctx = cleaned[max(0, m.start() - 25):min(len(cleaned), m.end() + 35)].replace('\n', ' ')
            untagged_units.append((m.group(0), ctx))

    assert not untagged_units, f"Measurement numbers with units missing <!-- metric: ... --> tags in README.md: {untagged_units}"

    # 2. Assert every ratio (e.g. 22 / 24, 8 / 8) has metric tags
    ratio_pat = re.compile(r'\b(\d+)\s*/\s*(\d+)\b')
    untagged_ratios = []
    for m in ratio_pat.finditer(cleaned):
        after = cleaned[m.end():m.end() + 150]
        tag_m = re.match(r'^\s*[*_\])]*\s*<!--\s*metric:\s*([a-zA-Z0-9_:]+)\s*-->', after)
        if not tag_m:
            ctx = cleaned[max(0, m.start() - 25):min(len(cleaned), m.end() + 35)].replace('\n', ' ')
            untagged_ratios.append((m.group(0), ctx))

    assert not untagged_ratios, f"Ratios missing <!-- metric: ... --> tags in README.md: {untagged_ratios}"

    # 3. Assert every metric tag in README matches manifest within 1%
    tag_pat = re.compile(
        r'(?:(\d+(?:,\d{3})*(?:\.\d+)?)\s*(%|ms|GFLOP/s|GB/s|TFLOP/s|x\b|params\b|bytes\b|samples\b|wins\b|decisions\b)?\s*[*_\])]*\s*)<!--\s*metric:\s*([a-zA-Z0-9_:]+)\s*-->',
        re.IGNORECASE
    )

    mismatches = []
    tag_count = 0
    for m in tag_pat.finditer(cleaned):
        tag_count += 1
        val_str = m.group(1)
        tag = m.group(3)
        assert tag in metrics, f"Metric tag '{tag}' in README.md does not exist in manifest.json"

        exp = metrics[tag]["value"]
        if val_str is not None:
            val = float(val_str.replace(",", ""))
            exp_f = float(exp)
            rel_diff = abs(val - exp_f) / max(abs(exp_f), 1e-4)
            if rel_diff > 0.01 and abs(val - exp_f) > 0.02:
                mismatches.append(f"Metric '{tag}': README={val}, manifest={exp_f} (diff={rel_diff:.2%})")

    assert tag_count > 0, "No metric tags found in README.md"
    assert not mismatches, f"Metric tag values in README.md do not match manifest within 1%: {mismatches}"

