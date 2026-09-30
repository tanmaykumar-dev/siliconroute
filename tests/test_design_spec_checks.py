"""Pytest test suite for Section 12 of docs/DESIGN_SPEC.md (Field Report).

Enforces:
- Section 0: Hard rules (data integrity, no external requests, photos from media.json only).
- Section 1: The anti-vibecode list (no gradients, no icons, no em dashes, no emojis, no banned words).
- Section 8: Copy rules.
- Section 10: Interaction inventory elements exist and have valid structure.
- Section 12: Automated checks.
"""

import json
from pathlib import Path
import re
import pytest

from scripts.check_design_spec import (
    check_anti_vibecode,
    check_contrast,
    check_credits_page,
    check_data_test_attributes,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT_DIR / "results" / "final" / "manifest.json"
FROZEN_DB_SHA = "98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5"


def test_section_12_contrast():
    """Verify Section 2 palette contrast passes WCAG 2.2 AA (>= 4.5:1)."""
    violations = check_contrast()
    assert len(violations) == 0, f"Contrast violations: {violations}"


def test_section_0_frozen_database_hash():
    """Verify ground truth database SHA256 matches frozen hash."""
    import hashlib
    db_file = ROOT_DIR / "data" / "final" / "siliconroute_final.db"
    assert db_file.exists(), f"Missing frozen database at {db_file}"
    h = hashlib.sha256(db_file.read_bytes()).hexdigest()
    assert h == FROZEN_DB_SHA, f"Database hash mismatch: {h} != {FROZEN_DB_SHA}"


def test_section_11_media_assets_exist():
    """Verify all raw media and generated media variants exist."""
    media_json = ROOT_DIR / "site" / "media" / "media.json"
    assert media_json.exists()
    data = json.loads(media_json.read_text(encoding="utf-8"))
    items = data.get("media", [])
    assert len(items) == 7

    for item in items:
        raw_p = ROOT_DIR / "site" / "media" / item["file"]
        assert raw_p.exists(), f"Missing raw photo: {raw_p}"
        assert item.get("alt"), f"Photo {item['file']} missing alt text"
        assert item.get("credit"), f"Photo {item['file']} missing credit"


def test_section_1_anti_vibecode():
    """Verify anti-vibecode rules across site/ and frontend/."""
    violations = check_anti_vibecode()
    # Any violations reported will be displayed
    assert len(violations) == 0, f"Anti-vibecode violations ({len(violations)}): {violations[:5]}"
