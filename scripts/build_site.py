"""SiliconRoute Design Spec v3: Static Website Builder (Section 10.3).

Extracts data from README and manifest, vendors fonts and tokens, copies demo media,
generates Open Graph image, and prepares site/ for standalone static serving without any runtime dependencies.
Produces byte-for-byte deterministic output.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from PIL import Image, ImageDraw

import sys
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
SITE_DIR = ROOT_DIR / "site"
DATA_DIR = SITE_DIR / "data"
IMG_DIR = SITE_DIR / "img"
MEDIA_DIR = SITE_DIR / "media"
FONTS_DIR = SITE_DIR / "fonts"
CSS_DIR = SITE_DIR / "css"
JS_DIR = SITE_DIR / "js"

MANIFEST_SRC = ROOT_DIR / "results" / "final" / "manifest.json"
README_SRC = ROOT_DIR / "README.md"
DB_SRC = ROOT_DIR / "data" / "final" / "siliconroute_final.db"
DEMO_SRC = ROOT_DIR / "results" / "demo" / "siliconroute_demo.webm"


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
    """Generate deterministic 1200x630 Open Graph card using Red Bench light palette."""
    width, height = 1200, 630
    # Red Bench light background #F2F2F0
    img = Image.new("RGB", (width, height), color=(242, 242, 240))
    draw = ImageDraw.Draw(img)

    # Frame line #D6D6D2
    draw.rectangle([24, 24, width - 24, height - 24], outline=(214, 214, 210), width=2)
    draw.line([64, 140, width - 64, 140], fill=(214, 214, 210), width=1)

    # Top brand bar with solid red chip #E1461E
    draw.rectangle([64, 64, 88, 88], fill=(225, 70, 30))
    draw.text((104, 62), "SILICONROUTE", fill=(20, 20, 20))
    draw.text((104, 92), "Hardware AI Load Balancer for Laptops", fill=(117, 117, 117))

    # Hero headline
    draw.text((64, 180), "Every AI task, on the right chip.", fill=(20, 20, 20))
    draw.text(
        (64, 230),
        "Empirical measurement, hardware performance models, and verified execution.",
        fill=(74, 74, 74)
    )

    # Chips row with Red Bench marks (square, triangle, circle)
    chips = [
        ("CPU", "Host AMD Processor", (20, 20, 20)),
        ("iGPU", "AMD Radeon 610M", (138, 138, 138)),
        ("dGPU", "NVIDIA RTX 5070", (225, 70, 30)),
    ]

    x_start = 64
    for i, (label, name, col) in enumerate(chips):
        box_x = x_start + i * 360
        # Sheet background #FAFAF8 with 1px border #D6D6D2
        draw.rectangle([box_x, 320, box_x + 320, 460], fill=(250, 250, 248), outline=(214, 214, 210), width=1)
        # Top 4px color accent
        draw.rectangle([box_x, 320, box_x + 320, 324], fill=col)
        draw.text((box_x + 20, 345), label, fill=col)
        draw.text((box_x + 20, 380), name, fill=(20, 20, 20))
        draw.text((box_x + 20, 415), "Empirical Measurements", fill=(117, 117, 117))

    # Footer note
    draw.text((64, 550), "Local-First: SQLite WAL: Zero Cloud Dependency: MIT License", fill=(117, 117, 117))

    img.save(str(out_path), "PNG")


def build_site():
    print("Building SiliconRoute website (Red Bench)...")

    for d in [DATA_DIR, IMG_DIR, MEDIA_DIR, FONTS_DIR, CSS_DIR, JS_DIR]:
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

    # 6. Copy Screenshots & Media
    screens_src = ROOT_DIR / "results" / "screenshots" / "v3_design"
    if not screens_src.exists() or not list(screens_src.glob("*.png")):
        screens_src = ROOT_DIR / "results" / "screenshots" / "v2_design"
    if screens_src.exists():
        for s in screens_src.glob("*.png"):
            shutil.copyfile(s, IMG_DIR / s.name)
        print("  Copied screenshots to site/img/")

    # Hero screenshot
    overview_shot = ROOT_DIR / "results" / "screenshots" / "v3_design" / "01_overview_1440x900.png"
    if overview_shot.exists():
        shutil.copyfile(overview_shot, IMG_DIR / "hero_screenshot.png")

    if DEMO_SRC.exists():
        shutil.copyfile(DEMO_SRC, MEDIA_DIR / "siliconroute_demo.webm")
        print("  Copied demo video -> site/media/")

    # 7. Run media pipeline (responsive variants, hero crop OG image, favicon)
    try:
        from scripts.build_media import build_media
        build_media()
    except Exception as e:
        print(f"  Warning: build_media error: {e}")


    print("Site build complete.")


if __name__ == "__main__":
    build_site()
