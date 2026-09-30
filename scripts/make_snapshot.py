"""Create data/snapshot_for_review.db from data/siliconroute.db using sqlite3 backup API."""
import hashlib
import os
from pathlib import Path
import sqlite3

src_path = Path("data/siliconroute.db")
dst_path = Path("data/snapshot_for_review.db")

src = sqlite3.connect(src_path)
dst = sqlite3.connect(dst_path)
with dst:
    src.backup(dst)
dst.close()
src.close()

size = os.path.getsize(dst_path)
sha256 = hashlib.sha256(open(dst_path, "rb").read()).hexdigest()

print(f"SNAPSHOT_PATH: {dst_path}")
print(f"SNAPSHOT_SIZE: {size} bytes")
print(f"SNAPSHOT_SHA256: {sha256}")
