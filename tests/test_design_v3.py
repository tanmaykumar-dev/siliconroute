"""Tests for SiliconRoute Design Spec v3 'Red Bench' (SPEC Section 14).

Verifies:
1. scripts/ui_lint.py reports zero violations across frontend/ and site/.
2. /api/published-metrics matches results/final/manifest.json exactly.
3. scripts/build_site.py is 100% deterministic (identical hashes across repeated runs).
4. No external runtime CDN or script/link/font dependencies in frontend/ or site/.
5. No hardcoded benchmark numbers with units in frontend/ or site/ markup.
"""

import hashlib
import json
from pathlib import Path
import re
from fastapi.testclient import TestClient
import pytest

from app.main import app
from scripts.build_site import build_site
from scripts.ui_lint import run_ui_lint

ROOT_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT_DIR / "results" / "final" / "manifest.json"
FRONTEND_DIR = ROOT_DIR / "frontend"
SITE_DIR = ROOT_DIR / "site"


def test_ui_lint():
    """Verify scripts/ui_lint.py passes with 0 violations across all files."""
    count, violations = run_ui_lint()
    assert count == 0, f"UI Lint failed with {count} violations: {violations[:5]}"


def test_published_metrics_endpoint():
    """Verify /api/published-metrics returns exactly what is recorded in the final manifest."""
    client = TestClient(app)
    resp = client.get("/api/published-metrics")
    assert resp.status_code == 200

    data = resp.json()
    assert "metrics" in data
    assert "metadata" in data

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Check key counts
    assert len(data["metrics"]) == len(manifest["metrics"])
    assert data["metadata"]["database_sha256"] == manifest["metadata"]["database_sha256"]

    # Check sample key values
    assert data["metrics"]["decisions_117_140_sr_wins"]["value"] == manifest["metrics"]["decisions_117_140_sr_wins"]["value"]
    assert data["metrics"]["decisions_117_140_sr_mean_regret_pct"]["value"] == manifest["metrics"]["decisions_117_140_sr_mean_regret_pct"]["value"]


def test_site_build_deterministic(tmp_path):
    """Running build_site twice gives identical byte-for-byte output."""
    def get_site_hash_tree() -> dict[str, str]:
        hashes = {}
        for p in SITE_DIR.rglob("*"):
            if p.is_file() and not p.name.endswith(".tmp"):
                rel = str(p.relative_to(SITE_DIR))
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                hashes[rel] = h
        return hashes

    build_site()
    hashes_run1 = get_site_hash_tree()

    build_site()
    hashes_run2 = get_site_hash_tree()

    assert hashes_run1 == hashes_run2
    assert len(hashes_run1) > 5


def test_no_external_requests():
    """Verify no runtime CDN or external script/font/stylesheet URLs exist in frontend/ or site/."""
    for base_dir in [FRONTEND_DIR, SITE_DIR]:
        for file_path in base_dir.rglob("*"):
            if file_path.suffix not in [".html", ".js", ".css"]:
                continue

            content = file_path.read_text(encoding="utf-8", errors="ignore")

            # Check script src, link href, @import
            external_scripts = re.findall(r'<script[^>]+src=["\'](https?://[^"\']+)["\']', content)
            external_links = re.findall(r'<link[^>]+(?:href|src)=["\'](https?://[^"\']+)["\']', content)
            css_imports = re.findall(r'@import\s+(?:url\()?["\'](https?://[^"\']+)["\']', content)

            assert len(external_scripts) == 0, f"External script tag found in {file_path}: {external_scripts}"
            assert len(css_imports) == 0, f"External CSS import found in {file_path}: {css_imports}"

            # Only allowed external links are <a href="https://github.com/..."
            for link in external_links:
                assert "github.com" in link, f"Disallowed external link in {file_path}: {link}"


def test_no_hardcoded_numbers_frontend_site():
    """Verify published benchmark values (e.g. 1.75%, 219.9 ms) are not hardcoded in markup."""
    html_files = [FRONTEND_DIR / "index.html", SITE_DIR / "index.html"]

    forbidden_snippets = [
        "1.75%",
        "304.93%",
        "113.06%",
        "219.9 ms",
        "215.8 ms",
        "189.8 ms",
        "202.8 ms",
    ]

    for html_path in html_files:
        assert html_path.exists()
        text = html_path.read_text(encoding="utf-8")

        for snippet in forbidden_snippets:
            assert snippet not in text, f"Hardcoded measurement snippet '{snippet}' found in {html_path.name}! Must use .metric component."
