import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_FONTS = ROOT / "frontend" / "fonts"
SITE_FONTS = ROOT / "site" / "fonts"

url = "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req) as resp:
    css = resp.read().decode('utf-8')

print("CSS fetched, length:", len(css))
# Find all @font-face blocks and extract font-family, font-weight, and url
blocks = css.split("@font-face")
for b in blocks:
    if "src:" in b and "latin" in b:
        # Check family and weight
        fam_match = re.search(r"font-family:\s*['\"]([^'\"]+)['\"]", b)
        weight_match = re.search(r"font-weight:\s*(\d+)", b)
        url_match = re.search(r"url\((https://[^)]+)\)", b)
        if fam_match and weight_match and url_match:
            fam = fam_match.group(1).lower().replace(" ", "-")
            weight = weight_match.group(1)
            furl = url_match.group(1)
            filename = f"{fam}-{weight}.woff2"
            print(f"Fetching {filename} from {furl}...")
            f_req = urllib.request.Request(furl, headers=headers)
            with urllib.request.urlopen(f_req) as f_resp:
                fdata = f_resp.read()
                (FRONTEND_FONTS / filename).write_bytes(fdata)
                (SITE_FONTS / filename).write_bytes(fdata)
                print(f"Saved {filename} ({len(fdata)} bytes)")

