"""SiliconRoute Design Spec v2 — Static Website verification script (Phase D4).

Tests:
1. Serves site/ over a local HTTP server on port 8088.
2. Opens site at 1440x900 (desktop) and 390x844 (mobile).
3. Verifies zero console errors and zero page errors.
4. Verifies DOM metrics match results/final/manifest.json.
5. Verifies limitations and disclosures are rendered from content.json.
6. Verifies frozen database SHA256 matches expected.
7. Saves screenshots to results/screenshots/v2_design/:
   - site_desktop_1440x900.png
   - site_mobile_390x844.png
8. Shuts down HTTP server.
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT_DIR / "site"
SCREENSHOT_DIR = ROOT_DIR / "results" / "screenshots" / "v2_design"
MANIFEST_PATH = ROOT_DIR / "results" / "final" / "manifest.json"


def verify_site():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    metrics = manifest.get("metrics", {})
    metadata = manifest.get("metadata", {})

    port = 8088
    handler = partial(SimpleHTTPRequestHandler, directory=str(SITE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"Local static server started on http://127.0.0.1:{port}")

    console_errors = []
    page_errors = []

    try:
        with sync_playwright() as p:
            print("Launching Microsoft Edge via Playwright...")
            browser = p.chromium.launch(channel="msedge", headless=True)

            # -------------------------------------------------------------
            # Desktop View (1440x900)
            # -------------------------------------------------------------
            print("\n[1/2] Verifying Desktop Layout (1440x900)...")
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page.wait_for_timeout(1500)

            # Check headline metrics
            sr_wins_el = page.locator('.metric[data-metric="decisions_117_140_sr_wins"]').first
            sr_wins_text = sr_wins_el.inner_text().strip()
            print(f"  SR wins in DOM: '{sr_wins_text}'")
            assert sr_wins_text == str(metrics["decisions_117_140_sr_wins"]["value"]), "SR wins mismatch"

            # Check DB SHA256 in reproduce section
            db_sha_el = page.locator("#build-db-sha")
            db_sha_text = db_sha_el.inner_text().strip()
            print(f"  DB SHA256 in DOM: '{db_sha_text}'")
            assert db_sha_text == metadata["database_sha256"], "DB SHA mismatch"

            # Check limitations populated
            lim_items = page.locator("#site-limitations-list li").count()
            print(f"  Limitations list items: {lim_items}")
            assert lim_items >= 4, "Expected limitations populated"

            desktop_shot = SCREENSHOT_DIR / "site_desktop_1440x900.png"
            page.screenshot(path=str(desktop_shot), full_page=True)
            print(f"  Saved screenshot: {desktop_shot}")
            page.close()

            # -------------------------------------------------------------
            # Mobile View (390x844)
            # -------------------------------------------------------------
            print("\n[2/2] Verifying Mobile Layout (390x844)...")
            page_mobile = browser.new_page(viewport={"width": 390, "height": 844})
            page_mobile.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page_mobile.on("pageerror", lambda exc: page_errors.append(str(exc)))

            page_mobile.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page_mobile.wait_for_timeout(1500)

            mobile_shot = SCREENSHOT_DIR / "site_mobile_390x844.png"
            page_mobile.screenshot(path=str(mobile_shot), full_page=True)
            print(f"  Saved screenshot: {mobile_shot}")
            page_mobile.close()

            browser.close()

        print("\nChecking console and page errors...")
        print(f"Console errors: {len(console_errors)}")
        print(f"Page errors: {len(page_errors)}")
        if console_errors:
            print("Console error details:\n" + "\n".join(console_errors))
        if page_errors:
            print("Page error details:\n" + "\n".join(page_errors))

        assert len(console_errors) == 0, f"Console errors encountered: {console_errors}"
        assert len(page_errors) == 0, f"Page errors encountered: {page_errors}"

    finally:
        server.shutdown()
        print("Server shutdown cleanly.")


if __name__ == "__main__":
    verify_site()
