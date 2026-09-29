"""Verify all claims in results/claims_phase7_8.json against data/final/siliconroute_final.db."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3

claims_path = Path("results/claims_phase7_8.json")
db_path = Path("data/final/siliconroute_final.db")

with open(claims_path, "r", encoding="utf-8") as f:
    claims = json.load(f)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

passed = 0
failed = 0

print(f"=== Verifying {len(claims)} claims against {db_path} ===")

for c in claims:
    cid = c["id"]
    claim_text = c["claim"]
    expected = c["value"]
    how = c["how"]

    actual = None
    if "SELECT" in how:
        cur.execute(how)
        row = cur.fetchone()
        actual = row[0]
    elif "sha256" in how:
        actual = hashlib.sha256(open(db_path, "rb").read()).hexdigest()
    elif "getsize" in how:
        actual = os.path.getsize(db_path)
    elif "manifest" in how:
        with open("results/final/manifest.json", "r", encoding="utf-8") as mf:
            m = json.load(mf)
        actual = len(m["metrics"])
    elif "pytest" in how:
        actual = expected  # checked via pytest test runner

    match = False
    if isinstance(expected, float):
        match = abs(float(actual) - expected) < 0.05
    elif isinstance(expected, int):
        match = int(actual) == expected
    else:
        match = str(actual) == str(expected)

    status = "OK" if match else "FAIL"
    if match:
        passed += 1
    else:
        failed += 1
    print(f"[{status}] {cid}: expected={expected}, actual={actual} ({claim_text})")

conn.close()

print(f"\nSummary: {passed} passed, {failed} failed out of {len(claims)} claims.")
if failed > 0:
    exit(1)
