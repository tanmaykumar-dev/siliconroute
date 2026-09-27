"""Inspect all ONNX files in models/ and compare with aimodel table."""

from datetime import datetime
import hashlib
import os
from pathlib import Path
import sqlite3
import sys

conn = sqlite3.connect("data/siliconroute.db")
c = conn.cursor()
c.execute("SELECT id, name, family, source, sha256 FROM aimodel")
db_models_by_sha = {}
for r in c.fetchall():
    db_models_by_sha.setdefault(r[4], []).append(r)

p = Path("models")
files = sorted(p.glob("*.onnx"))
print(f"Total .onnx files in models/: {len(files)}")
print(f"{'File Name':<28} {'Size KB':<10} {'Created Time':<20} {'SHA256':<16} {'DB Matches'}")
print("-" * 110)

test_files = []
synthetic_files = []

for f in files:
    h = hashlib.sha256(f.read_bytes()).hexdigest()
    stat = f.stat()
    ctime = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
    matches = db_models_by_sha.get(h, [])
    match_desc = ", ".join(f"[{m[0]}:{m[1]}({m[3]})]" for m in matches) if matches else "NONE"

    # Identify if file is test artifact vs synthetic model
    # Synthetic models follow naming like mlp_32w_2l, conv_8c_64hw_4l, attn_...
    # Let's inspect
    print(f"{f.name:<28} {stat.st_size/1024:<10.1f} {ctime:<20} {h[:14]:<16} {match_desc}")

conn.close()
