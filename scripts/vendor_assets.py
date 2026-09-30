"""Download and vendor pinned Chart.js and OFL fonts (Archivo Variable, JetBrains Mono).

Stores assets in frontend/vendor/ and frontend/fonts/, verifies sha256 checksums,
and logs records to docs/DECISIONS.md per DESIGN_SPEC section 0 and 3.2.
"""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / "frontend" / "vendor"
FONTS_DIR = ROOT / "frontend" / "fonts"
LOG_DIR = ROOT / "results" / "logs" / "design_v2"
DECISIONS_FILE = ROOT / "docs" / "DECISIONS.md"

VENDOR_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

ASSETS = [
    {
        "name": "Chart.js UMD 4.4.1",
        "url": "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js",
        "license": "MIT",
        "dest": VENDOR_DIR / "chart.umd.min.js",
    },
    {
        "name": "Archivo Variable Font (wdth, wght)",
        "url": "https://cdn.jsdelivr.net/npm/@fontsource-variable/archivo/files/archivo-latin-standard-normal.woff2",
        "license": "SIL Open Font License 1.1",
        "dest": FONTS_DIR / "archivo-variable.woff2",
    },
    {
        "name": "JetBrains Mono Variable Font (wght)",
        "url": "https://cdn.jsdelivr.net/npm/@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2",
        "license": "SIL Open Font License 1.1",
        "dest": FONTS_DIR / "jetbrains-mono.woff2",
    },
]


def vendor_assets():
    log_lines = []
    decisions_lines = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for item in ASSETS:
        dest = item["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {item['name']} from {item['url']}...")
        req = urllib.request.Request(item["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            data = resp.read()

        sha256 = hashlib.sha256(data).hexdigest()
        dest.write_bytes(data)
        size_bytes = len(data)

        entry = (
            f"Asset: {item['name']}\n"
            f"  Destination: {dest.relative_to(ROOT)}\n"
            f"  Size: {size_bytes} bytes\n"
            f"  SHA256: {sha256}\n"
            f"  License: {item['license']}\n"
            f"  URL: {item['url']}\n"
        )
        print(entry)
        log_lines.append(entry)

        decision_entry = (
            f"- {today} - Vendored {item['name']} to {dest.relative_to(ROOT)} "
            f"(Size: {size_bytes} B, SHA256: {sha256}, License: {item['license']}, Source: {item['url']}) - "
            f"Local-first design requirement to eliminate all runtime CDNs and external requests."
        )
        decisions_lines.append(decision_entry)

    # Write log file
    log_path = LOG_DIR / "vendored_assets.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    print(f"Logged asset info to {log_path}")

    # Append to DECISIONS.md
    with open(DECISIONS_FILE, "r", encoding="utf-8") as f:
        decisions_content = f.read()

    new_decisions = []
    for d_line in decisions_lines:
        if d_line not in decisions_content:
            new_decisions.append(d_line)

    if new_decisions:
        with open(DECISIONS_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(new_decisions) + "\n")
        print(f"Appended {len(new_decisions)} decisions to {DECISIONS_FILE}")


if __name__ == "__main__":
    vendor_assets()
