import hashlib
import os
from pathlib import Path
import sqlite3
import zipfile

src_path = Path("data/siliconroute.db")
dst_path = Path("data/snapshot_for_review.db")
zip_path = Path("data/snapshot_for_review.zip")

src = sqlite3.connect(src_path)
src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
dst = sqlite3.connect(dst_path)
src.backup(dst)
dst.close()
src.close()

sz = os.path.getsize(dst_path)
with open(dst_path, "rb") as f:
    sha = hashlib.sha256(f.read()).hexdigest()

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(dst_path, arcname="snapshot_for_review.db")

zip_sz = os.path.getsize(zip_path)

print(f"SNAPSHOT_PATH: {dst_path}")
print(f"SNAPSHOT_SIZE: {sz} bytes")
print(f"SNAPSHOT_SHA256: {sha}")
print(f"SNAPSHOT_ZIP_PATH: {zip_path}")
print(f"SNAPSHOT_ZIP_SIZE: {zip_sz} bytes")
