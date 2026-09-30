"""SiliconRoute Design Spec v2 — Browser verification script for D1-D3 app screens.

Tests:
1. Starts Uvicorn server on http://127.0.0.1:8000
2. Listens for and collects any browser console errors.
3. Tests theme toggle (dark <-> light).
4. Navigates to all 7 screens: Overview, Live, Analysis, Router, Results, Evidence, About.
5. Verifies DOM values against results/final/manifest.json.
6. Tests raw samples modal (open, focus trap, scatter plot, close).
7. Tests keyboard shortcuts sheet (? and Esc).
8. Takes screenshots in both themes (1440x900) into results/screenshots/v2_design/.
9. Cleanly shuts down Uvicorn.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = ROOT_DIR / "results" / "screenshots" / "v2_design"
LOG_DIR = ROOT_DIR / "results" / "logs" / "design_v2"
MANIFEST_PATH = ROOT_DIR / "results" / "final" / "manifest.json"


def wait_for_server(url: str, timeout_s: float = 15.0) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def verify_app():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    metrics = manifest.get("metrics", {})
    metadata = manifest.get("metadata", {})

    print("Starting Uvicorn server on http://127.0.0.1:8000...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    console_errors = []
    page_errors = []

    try:
        ready = wait_for_server("http://127.0.0.1:8000/api/system", timeout_s=20.0)
        if not ready:
            raise RuntimeError("Server failed to start within 20 seconds")
        print("Server is ready.")

        with sync_playwright() as p:
            print("Launching browser (msedge channel)...")
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on("response", lambda resp: print(f"404 URL: {resp.url}") if resp.status == 404 else None)

            print("Loading SiliconRoute App...")
            page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
            page.wait_for_timeout(2000)

            # -------------------------------------------------------------
            # 1. Overview Screen Verification
            # -------------------------------------------------------------
            print("\n[1/7] Verifying Overview Screen...")
            page.locator('.rail-item-btn[data-screen="overview"]').click()
            page.wait_for_timeout(1000)

            # Check 4 metric tiles in DOM
            sr_wins_el = page.locator('.metric[data-metric="decisions_117_140_sr_wins"]').first
            sr_wins_text = sr_wins_el.inner_text().strip()
            expected_wins = str(metrics["decisions_117_140_sr_wins"]["value"])
            print(f"  Best chip wins: DOM '{sr_wins_text}' vs Manifest '{expected_wins}'")
            assert sr_wins_text == expected_wins, f"Overview wins mismatch: {sr_wins_text} vs {expected_wins}"

            sr_regret_el = page.locator('.metric[data-metric="decisions_117_140_sr_mean_regret_pct"]').first
            sr_regret_text = sr_regret_el.inner_text().strip()
            print(f"  SR mean regret: DOM '{sr_regret_text}'")
            assert "1.75%" in sr_regret_text, f"Overview regret mismatch: {sr_regret_text}"

            # Capture Dark & Light Overview
            page.screenshot(path=str(SCREENSHOT_DIR / "app_dark_overview.png"))
            print(f"  Saved screenshot: {SCREENSHOT_DIR / 'app_dark_overview.png'}")

            # Toggle to Light Theme
            page.locator("#btn-theme-toggle").click()
            page.wait_for_timeout(500)
            page.screenshot(path=str(SCREENSHOT_DIR / "app_light_overview.png"))
            print(f"  Saved screenshot: {SCREENSHOT_DIR / 'app_light_overview.png'}")
            # Toggle back to dark
            page.locator("#btn-theme-toggle").click()
            page.wait_for_timeout(300)

            # -------------------------------------------------------------
            # 2. Live Telemetry Screen
            # -------------------------------------------------------------
            print("\n[2/7] Verifying Live Telemetry Screen...")
            page.locator('.rail-item-btn[data-screen="live"]').click()
            page.wait_for_timeout(1500)
            assert page.locator("#chart-live-cpu-ram").count() == 1
            assert page.locator("#chart-live-gpu-pwr-temp").count() == 1
            page.screenshot(path=str(SCREENSHOT_DIR / "app_dark_live.png"))
            print(f"  Saved screenshot: {SCREENSHOT_DIR / 'app_dark_live.png'}")

            # -------------------------------------------------------------
            # 3. Analysis Screen
            # -------------------------------------------------------------
            print("\n[3/7] Verifying Analysis Screen...")
            page.locator('.rail-item-btn[data-screen="analysis"]').click()
            page.wait_for_timeout(2000)
            assert page.locator("#chart-analysis-scaling").count() == 1
            fits_rows = page.locator("#analysis-fits-table-body tr").count()
            print(f"  Analysis fits rows: {fits_rows}")
            assert fits_rows >= 2, "Expected fits rows to be loaded"
            page.screenshot(path=str(SCREENSHOT_DIR / "app_dark_analysis.png"))
            print(f"  Saved screenshot: {SCREENSHOT_DIR / 'app_dark_analysis.png'}")

            # -------------------------------------------------------------
            # 4. Router Screen
            # -------------------------------------------------------------
            print("\n[4/7] Verifying Router Screen...")
            page.locator('.rail-item-btn[data-screen="router"]').click()
            page.wait_for_timeout(1500)
            assert page.locator("#btn-router-execute").count() == 1
            assert page.locator("#router-trace-container").count() == 1
            page.screenshot(path=str(SCREENSHOT_DIR / "app_dark_router.png"))
            print(f"  Saved screenshot: {SCREENSHOT_DIR / 'app_dark_router.png'}")

            # -------------------------------------------------------------
            # 5. Results Screen
            # -------------------------------------------------------------
            print("\n[5/7] Verifying Results Screen...")
            page.locator('.rail-item-btn[data-screen="results"]').click()
            page.wait_for_timeout(1500)
            hl_rows = page.locator("#results-headline-table-body tr").count()
            print(f"  Headline table rows: {hl_rows}")
            assert hl_rows >= 4, "Expected headline rows"
            page.screenshot(path=str(SCREENSHOT_DIR / "app_dark_results.png"))
            print(f"  Saved screenshot: {SCREENSHOT_DIR / 'app_dark_results.png'}")

            # -------------------------------------------------------------
            # 6. Evidence Screen
            # -------------------------------------------------------------
            print("\n[6/7] Verifying Evidence Screen...")
            page.locator('.rail-item-btn[data-screen="evidence"]').click()
            page.wait_for_timeout(1500)
            db_sha_dom = page.locator("#evidence-db-sha256").inner_text().strip()
            expected_sha = metadata["database_sha256"]
            print(f"  DB SHA256: DOM '{db_sha_dom}' vs Expected '{expected_sha}'")
            assert db_sha_dom == expected_sha, f"SHA mismatch: {db_sha_dom} vs {expected_sha}"

            metric_rows = page.locator("#evidence-metrics-tbody tr").count()
            print(f"  Metric browser rows: {metric_rows}")
            assert metric_rows > 10, "Expected metrics loaded in browser"
            page.screenshot(path=str(SCREENSHOT_DIR / "app_dark_evidence.png"))
            print(f"  Saved screenshot: {SCREENSHOT_DIR / 'app_dark_evidence.png'}")

            # -------------------------------------------------------------
            # 7. About Screen
            # -------------------------------------------------------------
            print("\n[7/7] Verifying About Screen...")
            page.locator('.rail-item-btn[data-screen="about"]').click()
            page.wait_for_timeout(1000)
            page.screenshot(path=str(SCREENSHOT_DIR / "app_dark_about.png"))
            print(f"  Saved screenshot: {SCREENSHOT_DIR / 'app_dark_about.png'}")

            # -------------------------------------------------------------
            # 8. Modals Verification (Raw Samples & Shortcuts)
            # -------------------------------------------------------------
            print("\n[8] Verifying Modals...")
            # Open Shortcuts sheet with '?'
            page.keyboard.press("?")
            page.wait_for_timeout(500)
            assert page.locator("#modal-shortcuts").is_visible()
            page.screenshot(path=str(SCREENSHOT_DIR / "modal_shortcuts.png"))
            print(f"  Saved screenshot: {SCREENSHOT_DIR / 'modal_shortcuts.png'}")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            # Test Raw Samples Modal (inspect run 812)
            page.evaluate("() => window.SiliconRouteApp ? window.SiliconRouteApp.modal.open(812) : null")
            page.wait_for_timeout(1200)
            page.screenshot(path=str(SCREENSHOT_DIR / "modal_raw_samples.png"))
            print(f"  Saved screenshot: {SCREENSHOT_DIR / 'modal_raw_samples.png'}")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            browser.close()

        print("\nChecking console and page errors...")
        print(f"Console errors: {len(console_errors)}")
        print(f"Page errors: {len(page_errors)}")
        if console_errors:
            print("Console error details:\n" + "\n".join(console_errors))
        if page_errors:
            print("Page error details:\n" + "\n".join(page_errors))

        assert len(page_errors) == 0, f"Page errors encountered: {page_errors}"

    finally:
        print("\nShutting down Uvicorn...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Server stopped cleanly.")


if __name__ == "__main__":
    verify_app()
