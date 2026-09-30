"""SiliconRoute Design Spec (final, revision 2): Media Processing Pipeline (Section 11).

Reads site/media/raw/ and site/media/media.json, strips metadata, generates responsive
variants (AVIF, WebP, JPEG at 640, 1280, 2000, 2800px), generates Open Graph image,
generates favicon, and enforces strict validation (fails if any photo lacks alt or credit).
"""

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = ROOT_DIR / "site" / "media"
RAW_DIR = MEDIA_DIR / "raw"
MEDIA_JSON = MEDIA_DIR / "media.json"
IMG_DIR = ROOT_DIR / "site" / "img"
IMG_DIR.mkdir(parents=True, exist_ok=True)

TARGET_WIDTHS = [640, 1280, 2000, 2800]


def build_media():
    if not MEDIA_JSON.exists():
        raise FileNotFoundError(f"Missing media.json at {MEDIA_JSON}")

    with open(MEDIA_JSON, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    items = manifest.get("media", [])
    if not items:
        raise ValueError("media.json has no media items!")

    print(f"Loaded {len(items)} media items from {MEDIA_JSON}")

    # Validate alt and credit first
    for item in items:
        raw_file = item.get("file", "")
        alt = item.get("alt", "").strip()
        credit = item.get("credit", "").strip()
        if not alt:
            raise ValueError(f"Photo '{raw_file}' lacks required 'alt' text!")
        if not credit:
            raise ValueError(f"Photo '{raw_file}' lacks required 'credit' text!")

    generated_files = []

    for item in items:
        rel_path = item["file"]
        # Source can be in site/media/ or site/media/raw/
        src_path = MEDIA_DIR / rel_path
        if not src_path.exists():
            src_path = RAW_DIR / Path(rel_path).name
        if not src_path.exists():
            raise FileNotFoundError(f"Raw image file not found: {src_path}")

        basename = src_path.stem
        with Image.open(src_path) as im:
            # Strip EXIF / metadata by creating clean RGB copy
            im_clean = Image.new("RGB", im.size)
            im_clean.paste(im.convert("RGB"))
            orig_w, orig_h = im_clean.size

            # Generate responsive variants
            for target_w in TARGET_WIDTHS:
                if target_w > orig_w and target_w != TARGET_WIDTHS[0]:
                    continue
                w = min(target_w, orig_w)
                h = int(orig_h * (w / orig_w))
                resized = im_clean.resize((w, h), Image.Resampling.LANCZOS)

                # Save WebP
                webp_out = MEDIA_DIR / f"{basename}_{w}.webp"
                resized.save(webp_out, "WEBP", quality=82)
                generated_files.append(webp_out)

                # Save JPEG
                jpg_out = MEDIA_DIR / f"{basename}_{w}.jpg"
                resized.save(jpg_out, "JPEG", quality=85, optimize=True)
                generated_files.append(jpg_out)

                # Save AVIF
                try:
                    avif_out = MEDIA_DIR / f"{basename}_{w}.avif"
                    resized.save(avif_out, "AVIF", quality=75)
                    generated_files.append(avif_out)
                except Exception as e:
                    print(f"AVIF save skipped for {basename}_{w}: {e}")

                # Check hero 1280px size constraint (< 400 KB)
                if "01_hero" in basename and w == 1280:
                    hero_sz = webp_out.stat().st_size
                    print(f"Hero WebP at 1280px size: {hero_sz} bytes ({hero_sz / 1024:.1f} KB)")
                    if hero_sz > 400 * 1024:
                        raise ValueError(f"Hero image exceeds 400 KB limit at 1280px: {hero_sz} bytes")

    # Generate Open Graph image (1200x630)
    # "Open Graph image made from a crop of the hero photo with the wordmark on a solid panel"
    hero_src = RAW_DIR / "01_hero_red_pcb.jpg"
    if hero_src.exists():
        with Image.open(hero_src) as hero_im:
            hero_rgb = hero_im.convert("RGB")
            og_w, og_h = 1200, 630
            # Center crop to 1200x630
            orig_aspect = hero_rgb.width / hero_rgb.height
            target_aspect = og_w / og_h
            if orig_aspect > target_aspect:
                new_w = int(hero_rgb.height * target_aspect)
                left = (hero_rgb.width - new_w) // 2
                hero_crop = hero_rgb.crop((left, 0, left + new_w, hero_rgb.height)).resize((og_w, og_h), Image.Resampling.LANCZOS)
            else:
                new_h = int(hero_rgb.width / target_aspect)
                top = (hero_rgb.height - new_h) // 2
                hero_crop = hero_rgb.crop((0, top, hero_rgb.width, top + new_h)).resize((og_w, og_h), Image.Resampling.LANCZOS)

            # Draw solid --ink panel over left side
            draw = ImageDraw.Draw(hero_crop)
            # Panel from x=48 to x=680, y=80 to y=550
            draw.rectangle([48, 80, 680, 550], fill="#121211")

            # Wordmark and subhead
            # Simple clean typography
            draw.text((80, 140), "SiliconRoute", fill="#EDEDE8")
            draw.text((80, 220), "Every AI task,\non the right chip.", fill="#EDEDE8")
            draw.text((80, 380), "Local-first load balancing for PC silicon", fill="#9B2A3C")
            draw.text((80, 440), "CPU  |  iGPU  |  dGPU  |  NPU", fill="#8C8C84")

            og_path = IMG_DIR / "og_image.png"
            hero_crop.save(og_path, "PNG")
            # Also save in site/media/
            hero_crop.save(MEDIA_DIR / "og_image.png", "PNG")
            print(f"Generated Open Graph image at {og_path}")

    # Generate Favicon: small solid --signal square with an ink "S"
    fav_size = 64
    fav_im = Image.new("RGBA", (fav_size, fav_size), "#9B2A3C")
    fav_draw = ImageDraw.Draw(fav_im)
    fav_draw.text((22, 16), "S", fill="#121211")
    fav_png = IMG_DIR / "favicon.png"
    fav_im.save(fav_png, "PNG")
    fav_ico = ROOT_DIR / "site" / "favicon.ico"
    fav_im.save(fav_ico, format="ICO")
    print(f"Generated favicon at {fav_png} and {fav_ico}")

    print(f"Media processing complete. Total files processed/generated: {len(generated_files) + 3}")


if __name__ == "__main__":
    build_media()
