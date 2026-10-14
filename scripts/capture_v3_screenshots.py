"""Capture the 9 required screenshots for Design Spec v3 Phase R5.
Captures live dashboard at http://127.0.0.1:8000/app/ and marketing site at http://127.0.0.1:8000/.
"""

from pathlib import Path
import shutil
import time
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "results" / "screenshots" / "v3_design"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SITE_IMG_DIR = ROOT_DIR / "site" / "img"
SITE_IMG_DIR.mkdir(parents=True, exist_ok=True)


def capture_all():
    with sync_playwright() as p:
        print("Launching browser to capture live dashboard and site screenshots...")
        browser = p.chromium.launch(channel="msedge", headless=True)

        # 1. App Desktop (1440x900) at /app/
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://127.0.0.1:8000/app/", timeout=20000)
        page.wait_for_load_state("networkidle")
        time.sleep(2.5)

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
                if screen_name == "live":
                    time.sleep(4.5)  # Wait for live telemetry SSE stream samples to plot
                else:
                    time.sleep(1.2)
            dest1 = OUT_DIR / filename
            dest2 = SITE_IMG_DIR / filename
            page.screenshot(path=str(dest1))
            shutil.copy2(dest1, dest2)
            print(f"Captured: {filename}")

        # Update hero_screenshot.png from live overview screen
        page.query_selector("[data-screen='overview']").click()
        time.sleep(1.0)
        hero_dest1 = OUT_DIR / "hero_screenshot.png"
        hero_dest2 = SITE_IMG_DIR / "hero_screenshot.png"
        page.screenshot(path=str(hero_dest1))
        shutil.copy2(hero_dest1, hero_dest2)
        print("Captured: hero_screenshot.png")

        page.close()

        # 2. Website Desktop (1440x900) at /
        page_site = browser.new_page(viewport={"width": 1440, "height": 900})
        page_site.goto("http://127.0.0.1:8000/", timeout=20000)
        page_site.wait_for_load_state("networkidle")
        time.sleep(1.5)
        site_d1 = OUT_DIR / "08_site_desktop_1440x900.png"
        site_d2 = SITE_IMG_DIR / "08_site_desktop_1440x900.png"
        page_site.screenshot(path=str(site_d1))
        shutil.copy2(site_d1, site_d2)
        print("Captured: 08_site_desktop_1440x900.png")
        page_site.close()

        # 3. Website Mobile (390x844) at /
        page_mobile = browser.new_page(viewport={"width": 390, "height": 844})
        page_mobile.goto("http://127.0.0.1:8000/", timeout=20000)
        page_mobile.wait_for_load_state("networkidle")
        time.sleep(1.5)
        site_m1 = OUT_DIR / "09_site_mobile_390x844.png"
        site_m2 = SITE_IMG_DIR / "09_site_mobile_390x844.png"
        page_mobile.screenshot(path=str(site_m1))
        shutil.copy2(site_m1, site_m2)
        print("Captured: 09_site_mobile_390x844.png")
        page_mobile.close()

        browser.close()

    print("All 9 screenshots captured and synced to site/img/ successfully.")


if __name__ == "__main__":
    capture_all()
