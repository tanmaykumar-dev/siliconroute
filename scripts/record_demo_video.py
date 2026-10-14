"""Record walkthrough video of SiliconRoute live telemetry dashboard and model profiler using Playwright.

Records video to results/demo/siliconroute_demo.webm and copies to site/media/siliconroute_demo.webm.
"""

from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT_DIR / "results" / "demo"
SITE_MEDIA_DIR = ROOT_DIR / "site" / "media"


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


def is_server_running() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/system", timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def record_video():
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    SITE_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    # Clean old temp webms in DEMO_DIR
    for old_file in DEMO_DIR.glob("*.webm"):
        try:
            old_file.unlink()
        except Exception:
            pass

    proc = None
    if not is_server_running():
        print("Starting Uvicorn server on http://127.0.0.1:8000...")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ready = wait_for_server("http://127.0.0.1:8000/api/system", timeout_s=20.0)
        if not ready:
            raise RuntimeError("Server failed to start within 20 seconds")
        print("Server is ready.")
    else:
        print("Uvicorn server is already active on http://127.0.0.1:8000.")

    try:
        with sync_playwright() as p:
            print("Launching Microsoft Edge with 1280x720 video recording enabled...")
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                record_video_dir=str(DEMO_DIR),
                record_video_size={"width": 1280, "height": 720},
            )
            page = context.new_page()

            # Part 1: Model-to-Silicon Profiler & Multi-Chip Arena (Overview screen)
            print("Video: Overview - Model-to-Silicon Profiler & Power Dial...")
            page.goto("http://127.0.0.1:8000/app/", wait_until="networkidle")
            page.wait_for_timeout(3500)

            # Interact with model selector: select mlp-256w-4l
            model_sel = page.locator("#profile-model-select")
            if model_sel.count() > 0:
                print("Video: Select mlp-256w-4l (Small, memory-bound model)...")
                opts = page.locator('#profile-model-select option')
                for i in range(opts.count()):
                    txt = opts.nth(i).inner_text()
                    if "256" in txt:
                        val = opts.nth(i).get_attribute("value")
                        model_sel.select_option(val)
                        break
                page.wait_for_timeout(2500)

            # Demonstrate Power Budget Dial
            print("Video: Adjust power budget dial to 20W (Preserve battery)...")
            btn_20w = page.locator('.power-level-item[data-watts="20"]')
            if btn_20w.count() > 0:
                btn_20w.click()
                page.wait_for_timeout(2500)

            print("Video: Restore power budget dial to 50W (Standard envelope)...")
            btn_50w = page.locator('.power-level-item[data-watts="50"]')
            if btn_50w.count() > 0:
                btn_50w.click()
                page.wait_for_timeout(2500)

            # Switch to a compute-bound model: mlp-3072w-4l
            if model_sel.count() > 0:
                print("Video: Select mlp-3072w-4l (Large compute-heavy model)...")
                opts = page.locator('#profile-model-select option')
                for i in range(opts.count()):
                    txt = opts.nth(i).inner_text()
                    if "3072" in txt:
                        val = opts.nth(i).get_attribute("value")
                        model_sel.select_option(val)
                        break
                page.wait_for_timeout(3000)

            # Scroll down to Silicon Arena scorecard
            arena = page.locator(".silicon-arena-card")
            if arena.count() > 0:
                arena.scroll_into_view_if_needed()
                page.wait_for_timeout(3500)

            # Part 2: Live Telemetry screen
            print("Video: Navigating to Live Telemetry screen...")
            page.evaluate("window.scrollTo(0, 0)")
            tab_live = page.locator('[data-screen="live"]')
            if tab_live.count() > 0:
                tab_live.click()
                print("Video: Live telemetry 1Hz streaming across CPU, iGPU, dGPU...")
                page.wait_for_timeout(5000)

            # Part 3: Analysis & Fits screen
            print("Video: Navigating to Analysis & Fits screen...")
            tab_analysis = page.locator('[data-screen="analysis"]')
            if tab_analysis.count() > 0:
                tab_analysis.click()
                page.wait_for_timeout(4000)

            # Part 4: Workload Router screen
            print("Video: Navigating to Workload Router screen...")
            tab_router = page.locator('[data-screen="router"]')
            if tab_router.count() > 0:
                tab_router.click()
                page.wait_for_timeout(4000)

            # Return to Overview
            print("Video: Returning to Overview screen...")
            tab_overview = page.locator('[data-screen="overview"]')
            if tab_overview.count() > 0:
                tab_overview.click()
                page.wait_for_timeout(3000)

            # Close page & context to finalize video encoding
            video_path_obj = page.video.path()
            page.close()
            context.close()
            browser.close()

            # Rename and copy to destination
            final_target = DEMO_DIR / "siliconroute_demo.webm"
            site_target = SITE_MEDIA_DIR / "siliconroute_demo.webm"

            src_file = None
            if video_path_obj and Path(video_path_obj).exists():
                src_file = Path(video_path_obj)
            else:
                webms = list(DEMO_DIR.glob("*.webm"))
                if webms:
                    src_file = webms[0]

            if src_file:
                shutil.move(str(src_file), str(final_target))
                shutil.copy2(str(final_target), str(site_target))
                print(f"Video saved successfully to {final_target} ({final_target.stat().st_size} bytes)")
                print(f"Synced video to {site_target}")
            else:
                print("Warning: No video file was generated by Playwright.")

    finally:
        if proc:
            print("Stopping spawned Uvicorn server...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("Uvicorn stopped.")


if __name__ == "__main__":
    record_video()
