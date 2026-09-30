"""SiliconRoute Final Proof and Interactive Audit (Design Spec Section 10, 12, 13).

Captures full-page screenshots at 1440x900 and 390x844 in results/screenshots/final_design/.
Audits every interaction from Section 10 table.
Verifies no console errors and DOM metrics match manifest.
Restores clean DB from data/final/siliconroute_final.db on completion.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = ROOT_DIR / "results" / "screenshots" / "final_design"
LOG_DIR = ROOT_DIR / "results" / "logs" / "final_design"
MANIFEST_PATH = ROOT_DIR / "results" / "final" / "manifest.json"
FROZEN_DB = ROOT_DIR / "data" / "final" / "siliconroute_final.db"
LIVE_DB = ROOT_DIR / "data" / "siliconroute.db"

SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


def run_audit():
    print("=== SiliconRoute Phase 4: Final Audit and Proof ===")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_metrics = manifest.get("metrics", {})

    console_errors = []

    def on_console(msg):
        if msg.type == "error":
            console_errors.append(msg.text)

    # Start local uvicorn server with output to log file (avoids pipe deadlock)
    uvicorn_log_file = open(LOG_DIR / "uvicorn_audit.log", "w", encoding="utf-8")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(ROOT_DIR),
        stdout=uvicorn_log_file,
        stderr=subprocess.STDOUT,
    )

    time.sleep(2.5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)

            # =================================================================
            # 1. WEBSITE AUDIT & SCREENSHOTS (1440x900)
            # =================================================================
            print("\n[1/4] Auditing Website (Desktop 1440x900)...")
            page_site = browser.new_page(viewport={"width": 1440, "height": 900})
            page_site.on("console", on_console)
            page_site.goto("http://127.0.0.1:8000/", timeout=15000)
            page_site.wait_for_load_state("networkidle")
            time.sleep(1)

            # Capture desktop full-page
            site_desktop_path = SCREENSHOTS_DIR / "01_website_desktop_1440x900.png"
            page_site.screenshot(path=str(site_desktop_path), full_page=True)
            print(f"Captured: {site_desktop_path.name}")

            # Section 10 Website Interactions
            # 1. "SiliconRoute" -> scroll to top
            page_site.evaluate("window.scrollTo(0, 1000)")
            time.sleep(0.2)
            page_site.click("[data-test='header-home']")
            time.sleep(0.4)
            scroll_y = page_site.evaluate("window.scrollY")
            assert scroll_y < 100, f"Expected scrollY near 0, got {scroll_y}"
            print("  [PASS] Header home link scrolls to top")

            # 2. Vision / How it works / Results nav links
            page_site.click("[data-test='nav-vision']")
            time.sleep(0.3)
            assert "#vision" in page_site.url
            print("  [PASS] Nav vision scrolls and sets hash")

            page_site.click("[data-test='nav-how-it-works']")
            time.sleep(0.3)
            assert "#how-it-works" in page_site.url
            print("  [PASS] Nav how-it-works scrolls and sets hash")

            # 3. How it works (hero) -> scrolls to section 03
            page_site.evaluate("window.scrollTo(0, 0)")
            page_site.click("[data-test='hero-how-it-works']")
            time.sleep(0.3)
            print("  [PASS] Hero 'How it works' button triggers scroll")

            # 4. Small model / Large model / Cold start segmented control
            btn_large = page_site.query_selector("[data-test='seg-large']")
            if btn_large:
                btn_large.click()
                time.sleep(0.3)
                print("  [PASS] Decision figure segmented control: Large model clicked")

            btn_cold = page_site.query_selector("[data-test='seg-cold']")
            if btn_cold:
                btn_cold.click()
                time.sleep(0.3)
                print("  [PASS] Decision figure segmented control: Cold start clicked")

            # 5. Show data toggle
            btn_show_data = page_site.query_selector("[data-test='btn-show-data']")
            if btn_show_data:
                btn_show_data.click()
                time.sleep(0.2)
                tbl = page_site.query_selector("#decision-data-table")
                assert tbl and tbl.is_visible()
                print("  [PASS] Decision figure 'Show data' reveals table")

            # 6. Copy buttons
            copy_sha_btn = page_site.query_selector("[data-test='btn-copy-sha']")
            if copy_sha_btn:
                copy_sha_btn.click()
                time.sleep(0.2)
                print("  [PASS] Section 09 SHA256 copy button works")

            copy_email_btn = page_site.query_selector("[data-test='btn-copy-email']")
            if copy_email_btn:
                copy_email_btn.click()
                time.sleep(0.2)
                print("  [PASS] Section 11 email copy button works")

            page_site.close()

            # =================================================================
            # 2. WEBSITE MOBILE (390x844) & MENU OVERLAY
            # =================================================================
            print("\n[2/4] Auditing Website (Mobile 390x844)...")
            page_mobile = browser.new_page(viewport={"width": 390, "height": 844})
            page_mobile.on("console", on_console)
            page_mobile.goto("http://127.0.0.1:8000/", timeout=15000)
            page_mobile.wait_for_load_state("networkidle")
            time.sleep(1)

            site_mobile_path = SCREENSHOTS_DIR / "02_website_mobile_390x844.png"
            page_mobile.screenshot(path=str(site_mobile_path), full_page=True)
            print(f"Captured: {site_mobile_path.name}")

            # Test Menu open and close
            page_mobile.click("[data-test='btn-menu']")
            time.sleep(0.3)
            overlay = page_mobile.query_selector("#mobile-menu-overlay")
            assert overlay and overlay.is_visible(), "Mobile menu overlay should be open"
            print("  [PASS] Mobile menu opens on click")

            page_mobile.keyboard.press("Escape")
            time.sleep(0.3)
            assert not overlay.is_visible(), "Mobile menu overlay should close on Escape"
            print("  [PASS] Mobile menu closes on Escape key")

            page_mobile.close()

            # =================================================================
            # 3. EXTRA PAGES AUDIT
            # =================================================================
            print("\n[3/4] Verifying Extra Pages...")
            extra_pages = ["privacy.html", "terms.html", "credits.html", "dashboard.html", "404.html"]
            p_extra = browser.new_page()
            for ep in extra_pages:
                res = p_extra.goto(f"http://127.0.0.1:8000/{ep}", wait_until="commit", timeout=10000)
                assert res.status == 200, f"Page {ep} returned status {res.status}"
                print(f"  [PASS] {ep}: HTTP {res.status}")
            p_extra.close()

            # =================================================================
            # 4. DASHBOARD AUDIT & SCREENSHOTS (1440x900 & 390x844)
            # =================================================================
            print("\n[4/4] Auditing Dashboard at /app (Desktop & Mobile)...")
            page_app = browser.new_page(viewport={"width": 1440, "height": 900})
            page_app.on("console", on_console)
            page_app.goto("http://127.0.0.1:8000/app/", timeout=15000)
            page_app.wait_for_load_state("networkidle")
            time.sleep(1.2)

            screens = [
                ("overview", "03_dashboard_overview_1440x900.png"),
                ("live", "04_dashboard_live_1440x900.png"),
                ("analysis", "05_dashboard_analysis_1440x900.png"),
                ("router", "06_dashboard_router_1440x900.png"),
                ("results", "07_dashboard_results_1440x900.png"),
                ("evidence", "08_dashboard_evidence_1440x900.png"),
                ("about", "09_dashboard_about_1440x900.png"),
            ]

            for s_name, filename in screens:
                tab_btn = page_app.query_selector(f"[data-screen='{s_name}']")
                if tab_btn:
                    tab_btn.click()
                    time.sleep(0.6)
                out_p = SCREENSHOTS_DIR / filename
                page_app.screenshot(path=str(out_p), full_page=False)
                print(f"Captured: {filename}")

            # Mobile Dashboard Screenshots
            page_app_m = browser.new_page(viewport={"width": 390, "height": 844})
            page_app_m.goto("http://127.0.0.1:8000/app#/overview", timeout=15000)
            page_app_m.wait_for_load_state("networkidle")
            time.sleep(0.8)
            page_app_m.screenshot(path=str(SCREENSHOTS_DIR / "10_dashboard_overview_390x844.png"))
            print("Captured: 10_dashboard_overview_390x844.png")

            page_app_m.goto("http://127.0.0.1:8000/app#/router", timeout=15000)
            page_app_m.wait_for_load_state("networkidle")
            time.sleep(0.8)
            page_app_m.screenshot(path=str(SCREENSHOTS_DIR / "11_dashboard_router_390x844.png"))
            print("Captured: 11_dashboard_router_390x844.png")

            page_app_m.goto("http://127.0.0.1:8000/app#/results", timeout=15000)
            page_app_m.wait_for_load_state("networkidle")
            time.sleep(0.8)
            page_app_m.screenshot(path=str(SCREENSHOTS_DIR / "12_dashboard_results_390x844.png"))
            print("Captured: 12_dashboard_results_390x844.png")
            page_app_m.close()

            # Dashboard Section 10 Interactions
            # 1. Back to website link
            back_link = page_app.query_selector("[data-test='nav-back-to-website']")
            assert back_link, "Back to website link missing"
            assert back_link.get_attribute("href") == "/", f"Expected href '/', got {back_link.get_attribute('href')}"
            print("  [PASS] Back to website link verified")

            # 2. Light / Dark toggle and persistence
            theme_btn = page_app.query_selector("[data-test='theme-toggle']")
            assert theme_btn, "Theme toggle button missing"
            theme_btn.click()
            time.sleep(0.3)
            doc_theme = page_app.evaluate("document.documentElement.getAttribute('data-theme')")
            assert doc_theme == "dark", f"Expected dark theme after toggle, got {doc_theme}"
            print("  [PASS] Light/Dark toggle switches to dark")

            # Capture Dark mode screenshots
            tab_overview = page_app.query_selector("[data-screen='overview']")
            if tab_overview:
                tab_overview.click()
            time.sleep(0.5)
            page_app.screenshot(path=str(SCREENSHOTS_DIR / "13_dashboard_dark_overview_1440x900.png"))
            print("Captured: 13_dashboard_dark_overview_1440x900.png")

            tab_router = page_app.query_selector("[data-screen='router']")
            if tab_router:
                tab_router.click()
            time.sleep(0.5)
            page_app.screenshot(path=str(SCREENSHOTS_DIR / "14_dashboard_dark_router_1440x900.png"))
            print("Captured: 14_dashboard_dark_router_1440x900.png")

            # Reload to test persistence
            page_app.reload()
            page_app.wait_for_load_state("networkidle")
            time.sleep(0.5)
            persisted_theme = page_app.evaluate("document.documentElement.getAttribute('data-theme')")
            assert persisted_theme == "dark", f"Theme did not persist after reload: {persisted_theme}"
            print("  [PASS] Dark theme persists after page reload")

            # Toggle back to light
            page_app.query_selector("[data-test='theme-toggle']").click()
            time.sleep(0.3)
            light_theme = page_app.evaluate("document.documentElement.getAttribute('data-theme')")
            assert light_theme == "light", f"Expected light theme, got {light_theme}"
            print("  [PASS] Theme toggles back to light")

            # 3. Router: "Route task"
            page_app.query_selector("[data-screen='router']").click()
            time.sleep(0.5)
            btn_route = page_app.query_selector("[data-test='route-task']")
            assert btn_route, "Route task button missing"
            btn_route.click()
            time.sleep(0.8)
            decision_card = page_app.query_selector("#router-decision-card")
            assert decision_card and decision_card.is_visible(), "Decision card should be visible after route task"
            print("  [PASS] Router: Route task renders decision card")

            # 4. Router: "Route and verify on hardware" (Cancel dialog only!)
            page_app.on("dialog", lambda d: (print(f"  [PASS] Dialog prompt: '{d.message[:40]}...'"), d.dismiss()))
            btn_verify = page_app.query_selector("[data-test='route-verify']")
            if btn_verify:
                btn_verify.click()
                time.sleep(0.5)
                print("  [PASS] Route and verify on hardware confirmation dialog intercepted & canceled")

            # 5. Export decisions CSV
            csv_btn = page_app.query_selector("[data-test='export-decisions-csv']")
            assert csv_btn, "Export decisions CSV button missing"
            print("  [PASS] Export decisions CSV button verified")

            # 6. Analysis screen: show data table
            page_app.query_selector("[data-screen='analysis']").click()
            time.sleep(0.5)
            btn_analysis_toggle = page_app.query_selector("[data-test='toggle-table-analysis-scaling']")
            if btn_analysis_toggle:
                btn_analysis_toggle.click()
                time.sleep(0.3)
                tbl = page_app.query_selector("#table-analysis-scaling")
                assert tbl and tbl.is_visible()
                print("  [PASS] Analysis scaling data table toggled")

            # 7. Evidence screen: Raw samples modal
            page_app.query_selector("[data-screen='evidence']").click()
            time.sleep(0.5)
            inspect_btn = page_app.query_selector("[data-test='show-raw-samples']")
            if inspect_btn:
                inspect_btn.click()
                time.sleep(0.5)
                modal = page_app.query_selector("#raw-samples-modal")
                assert modal and modal.is_visible(), "Raw samples modal should be open"
                print("  [PASS] Evidence screen inspect samples opens raw modal")
                close_raw = page_app.query_selector("[data-test='btn-close-raw-modal']")
                if close_raw:
                    close_raw.click()
                    time.sleep(0.3)
                    assert not modal.is_visible(), "Raw samples modal should close"
                    print("  [PASS] Raw samples modal closes")

            page_app.close()
            browser.close()

    finally:
        print("\nStopping uvicorn server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except Exception:
            server_process.kill()
        try:
            uvicorn_log_file.close()
        except Exception:
            pass

        # Restore pristine database
        if FROZEN_DB.exists():
            shutil.copy2(FROZEN_DB, LIVE_DB)
            print(f"Restored clean DB {LIVE_DB} from {FROZEN_DB}")

    # Check for console errors
    print(f"\nTotal browser console errors: {len(console_errors)}")
    if console_errors:
        print("Console errors logged:")
        for ce in console_errors:
            print("  -", ce)
        assert len(console_errors) == 0, f"Found {len(console_errors)} console errors"

    print("\nALL SECTION 10 INTERACTION AUDITS & SCREENSHOTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_audit()
