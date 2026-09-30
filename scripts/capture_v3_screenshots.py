"""Capture the 9 required screenshots for Design Spec v3 Phase R5.
"""

from pathlib import Path
import time
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "results" / "screenshots" / "v3_design"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def capture_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)

        # 1. App Desktop (1440x900)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://127.0.0.1:8000/", timeout=15000)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        app_screens = [
            ("overview", "01_overview_1440x900.png"),
            ("live", "02_live_1440x900.png"),
            ("analysis", "03_analysis_1440x900.png"),
            ("router", "04_router_1440x900.png"),
            ("results", "05_results_1440x900.png"),
            ("evidence", "06_evidence_1440x900.png"),
            ("about", "07_about_1440x900.png"),
        ]

        for screen_name, filename in app_screens:
            tab_btn = page.query_selector(f"[data-screen='{screen_name}']")
            if tab_btn:
                tab_btn.click()
                time.sleep(0.6)
            page.screenshot(path=str(OUT_DIR / filename))
            print(f"Captured: {filename}")

        page.close()

        # 2. Website Desktop (1440x900)
        page_site = browser.new_page(viewport={"width": 1440, "height": 900})
        page_site.goto("http://127.0.0.1:8000/site/", timeout=15000)
        page_site.wait_for_load_state("networkidle")
        time.sleep(1)
        page_site.screenshot(path=str(OUT_DIR / "08_site_desktop_1440x900.png"))
        print("Captured: 08_site_desktop_1440x900.png")
        page_site.close()

        # 3. Website Mobile (390x844)
        page_mobile = browser.new_page(viewport={"width": 390, "height": 844})
        page_mobile.goto("http://127.0.0.1:8000/site/", timeout=15000)
        page_mobile.wait_for_load_state("networkidle")
        time.sleep(1)
        page_mobile.screenshot(path=str(OUT_DIR / "09_site_mobile_390x844.png"))
        print("Captured: 09_site_mobile_390x844.png")
        page_mobile.close()

        browser.close()

    print("All 9 screenshots captured successfully.")


if __name__ == "__main__":
    capture_all()
