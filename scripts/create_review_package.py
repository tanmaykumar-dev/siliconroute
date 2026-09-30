"""Assemble review_package directory, compute SHA256 checksums, and generate review_package.zip."""

import hashlib
import os
from pathlib import Path
import shutil
import zipfile

ROOT = Path(".").resolve()
PKG_DIR = ROOT / "review_package"
ZIP_PATH = ROOT / "review_package.zip"

if PKG_DIR.exists():
    shutil.rmtree(PKG_DIR)
if ZIP_PATH.exists():
    ZIP_PATH.unlink()

PKG_DIR.mkdir(parents=True, exist_ok=True)

# List of files to copy: (source_rel, dest_rel)
files_to_copy: list[Path] = [
    Path("data/snapshot_for_review.db"),
    Path("data/final/siliconroute_final.db"),
    Path("README.md"),
    Path("results/final/results.md"),
    Path("results/final/manifest.json"),
    Path("results/claims_phase7_8.json"),
    Path("app/benchmark.py"),
    Path("app/router.py"),
    Path("app/predictor.py"),
    Path("app/db.py"),
    Path("tests/test_published_numbers.py"),
    Path("scripts/make_final_results.py"),
    Path("scripts/reproduce.py"),
    Path("scripts/metrics.py"),
    Path("docs/DEMO_SCRIPT.md"),
]

# Add all CSV files in results/final/
if (ROOT / "results/final").exists():
    for p in (ROOT / "results/final").glob("*.csv"):
        files_to_copy.append(p.relative_to(ROOT))

# Add every file in results/logs/phase7_8/
if (ROOT / "results/logs/phase7_8").exists():
    for p in (ROOT / "results/logs/phase7_8").iterdir():
        if p.is_file():
            files_to_copy.append(p.relative_to(ROOT))

# Add every file in results/logs/release_v1/
if (ROOT / "results/logs/release_v1").exists():
    for p in (ROOT / "results/logs/release_v1").iterdir():
        if p.is_file():
            files_to_copy.append(p.relative_to(ROOT))

# Add every file in results/logs/design_v2/
if (ROOT / "results/logs/design_v2").exists():
    for p in (ROOT / "results/logs/design_v2").iterdir():
        if p.is_file():
            files_to_copy.append(p.relative_to(ROOT))

# Add all screenshots in results/screenshots/v1_0/
if (ROOT / "results/screenshots/v1_0").exists():
    for p in (ROOT / "results/screenshots/v1_0").glob("*.png"):
        files_to_copy.append(p.relative_to(ROOT))

# Add all screenshots in results/screenshots/v2_design/
if (ROOT / "results/screenshots/v2_design").exists():
    for p in (ROOT / "results/screenshots/v2_design").glob("*.png"):
        files_to_copy.append(p.relative_to(ROOT))

if (ROOT / "docs/DESIGN_SPEC.md").exists():
    files_to_copy.append(Path("docs/DESIGN_SPEC.md"))

# Add demo video if exists
demo_vid = ROOT / "results/demo/siliconroute_demo.webm"
if demo_vid.exists():
    files_to_copy.append(demo_vid.relative_to(ROOT))

# Deduplicate
files_to_copy = sorted(list(set(files_to_copy)))

print(f"Copying {len(files_to_copy)} files to {PKG_DIR}...")
for rel_path in files_to_copy:
    src = ROOT / rel_path
    dst = PKG_DIR / rel_path
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

# Generate FILES.txt with size and SHA256 for each file inside review_package/
manifest_lines = []
for p in sorted(PKG_DIR.rglob("*")):
    if p.is_file() and p.name != "FILES.txt":
        rel = p.relative_to(PKG_DIR).as_posix()
        size = p.stat().st_size
        sha256 = hashlib.sha256(p.read_bytes()).hexdigest()
        manifest_lines.append(f"{sha256}  {size:>10} bytes  {rel}")

files_txt_path = PKG_DIR / "FILES.txt"
with open(files_txt_path, "w", encoding="utf-8") as f:
    f.write("\n".join(manifest_lines) + "\n")

print(f"Wrote {len(manifest_lines)} entries to {files_txt_path}")

# Create review_package.zip
print(f"Creating {ZIP_PATH}...")
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
    for p in sorted(PKG_DIR.rglob("*")):
        if p.is_file():
            arcname = p.relative_to(ROOT).as_posix()
            zf.write(p, arcname)

zip_size = ZIP_PATH.stat().st_size
print(f"REVIEW_PACKAGE_ZIP_PATH: {ZIP_PATH}")
print(f"REVIEW_PACKAGE_ZIP_SIZE: {zip_size} bytes")
