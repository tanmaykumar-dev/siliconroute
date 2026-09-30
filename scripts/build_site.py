"""SiliconRoute Design Spec v2 — Static Website Builder (Section 10.2).

Extracts data from README and manifest, vendors fonts and tokens, generates OG image,
and prepares site/ for standalone static serving without any runtime dependencies.
Produces byte-for-byte deterministic output.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT_DIR / "site"
DATA_DIR = SITE_DIR / "data"
IMG_DIR = SITE_DIR / "img"
FONTS_DIR = SITE_DIR / "fonts"
CSS_DIR = SITE_DIR / "css"
JS_DIR = SITE_DIR / "js"

MANIFEST_SRC = ROOT_DIR / "results" / "final" / "manifest.json"
README_SRC = ROOT_DIR / "README.md"
DB_SRC = ROOT_DIR / "data" / "final" / "siliconroute_final.db"


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def extract_readme_sections(readme_text: str) -> dict:
    lim_start = readme_text.find("## 5. Limitations")
    lim_end = readme_text.find("## 6. How This Was Built")
    built_end = readme_text.find("## 7. Quick Start")

    lim_text = readme_text[lim_start:lim_end].strip() if lim_start != -1 else ""
    built_text = readme_text[lim_end:built_end].strip() if lim_end != -1 else ""

    # Parse bullet items in limitations
    limitations = []
    for line in lim_text.splitlines():
        line = line.strip()
        if line.startswith("- **"):
            # strip markdown comments <!-- ... -->
            clean = re.sub(r"<!--.*?-->", "", line).strip()
            limitations.append(clean.lstrip("- ").strip())

    # Parse how it was built paragraphs
    how_built = []
    for line in built_text.splitlines():
        line = line.strip()
        if line.startswith("- **"):
            clean = re.sub(r"<!--.*?-->", "", line).strip()
            how_built.append(clean.lstrip("- ").strip())

    return {
        "limitations": limitations,
        "how_this_was_built": how_built,
    }


def generate_og_image(out_path: Path):
    """Generate deterministic 1200x630 Open Graph card."""
    width, height = 1200, 630
    img = Image.new("RGB", (width, height), color=(14, 19, 23)) # dark bench palette
    draw = ImageDraw.Draw(img)

    # Frame & accent lines
    draw.rectangle([20, 20, width - 20, height - 20], outline=(40, 50, 60), width=2)
    draw.line([60, 150, width - 60, 150], fill=(40, 50, 60), width=1)

    # Title
    draw.text((60, 60), "SILICONROUTE", fill=(230, 236, 239))
    draw.text((60, 95), "Hardware AI Load Balancer for Laptops", fill=(138, 148, 156))

    # Hero statement
    draw.text((60, 200), "Every AI task, on the right chip.", fill=(255, 255, 255))
    draw.text(
        (60, 260),
        "Empirical measurement, hardware modeling, and physics-informed routing.",
        fill=(180, 190, 200)
    )

    # Chips visual row
    chips = [
        ("CPU", "AMD Ryzen 9", (227, 179, 65)),     # Amber
        ("iGPU", "Radeon 610M", (56, 189, 178)),    # Teal
        ("dGPU", "RTX 5070", (110, 156, 255)),     # Blue
    ]

    x_start = 60
    for i, (label, name, col) in enumerate(chips):
        box_x = x_start + i * 360
        draw.rectangle([box_x, 340, box_x + 320, 480], fill=(23, 32, 38), outline=col, width=2)
        draw.rectangle([box_x, 340, box_x + 8, 480], fill=col)
        draw.text((box_x + 24, 365), label, fill=col)
        draw.text((box_x + 24, 400), name, fill=(230, 236, 239))
        draw.text((box_x + 24, 435), "Empirical Envelope", fill=(138, 148, 156))

    # Footer note
    draw.text((60, 560), "Local-First • SQLite WAL • Zero Cloud Dependency • MIT License", fill=(100, 110, 120))

    img.save(str(out_path), "PNG")


def build_site():
    print("Building SiliconRoute website (Phase D4)...")

    for d in [DATA_DIR, IMG_DIR, FONTS_DIR, CSS_DIR, JS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Copy Manifest
    shutil.copyfile(MANIFEST_SRC, DATA_DIR / "manifest.json")
    print(f"  Copied {MANIFEST_SRC.name} -> site/data/manifest.json")

    # 2. Extract README content
    readme_text = README_SRC.read_text(encoding="utf-8")
    content_data = extract_readme_sections(readme_text)
    (DATA_DIR / "content.json").write_text(json.dumps(content_data, indent=2), encoding="utf-8")
    print("  Extracted README sections -> site/data/content.json")

    # 3. Build Metadata
    manifest_obj = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    db_sha = compute_sha256(DB_SRC)
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT_DIR)).decode().strip()
    except Exception:
        git_commit = manifest_obj.get("metadata", {}).get("git_commit", "unknown")

    build_info = {
        "git_commit": git_commit,
        "database_sha256": db_sha,
        "manifest_date": manifest_obj.get("metadata", {}).get("date", "2026-09-30T13:25:28Z"),
        "version": "1.0",
    }
    (DATA_DIR / "build.json").write_text(json.dumps(build_info, indent=2), encoding="utf-8")
    print("  Created site/data/build.json")

    # 4. Copy Fonts
    for font_file in (ROOT_DIR / "frontend" / "fonts").glob("*.woff2"):
        shutil.copyfile(font_file, FONTS_DIR / font_file.name)
        print(f"  Copied font {font_file.name} -> site/fonts/")

    # 5. Copy Tokens CSS
    shutil.copyfile(ROOT_DIR / "frontend" / "css" / "tokens.css", CSS_DIR / "tokens.css")
    print("  Copied tokens.css -> site/css/")

    # 6. Copy Screenshots
    screens_src = ROOT_DIR / "results" / "screenshots" / "v2_design"
    if screens_src.exists():
        for s in screens_src.glob("*.png"):
            shutil.copyfile(s, IMG_DIR / s.name)
        print("  Copied screenshots to site/img/")

    # 7. Generate OG Image
    og_path = IMG_DIR / "og_image.png"
    generate_og_image(og_path)
    print(f"  Generated Open Graph card -> {og_path}")

    print("Site build complete.")


if __name__ == "__main__":
    build_site()
