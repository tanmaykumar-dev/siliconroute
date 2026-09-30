"""Record silent walkthrough video of SiliconRoute v1.0 using Playwright.

Records video to results/demo/siliconroute_demo.webm following docs/DEMO_SCRIPT.md.
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


def record_video():
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    # Clean old recordings in DEMO_DIR if any
    for old_file in DEMO_DIR.glob("*.webm"):
        try:
            old_file.unlink()
        except Exception:
            pass

    print("Starting Uvicorn server on http://127.0.0.1:8000...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        ready = wait_for_server("http://127.0.0.1:8000/api/system", timeout_s=20.0)
        if not ready:
            raise RuntimeError("Server failed to start within 20 seconds")
        print("Server is ready.")

        with sync_playwright() as p:
            print("Launching Microsoft Edge with video recording enabled...")
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                record_video_dir=str(DEMO_DIR),
                record_video_size={"width": 1280, "height": 720},
            )
            page = context.new_page()

            # Part 1: Live Telemetry
            print("Video: Live Telemetry...")
            page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
            page.wait_for_timeout(4000)

            # Part 2: Analysis & Fits
            print("Video: Analysis & Fits...")
            page.locator('.nav-tab[data-tab="analysis"]').click()
            page.wait_for_timeout(3000)

            # Open run inspector modal
            print("Video: Open Run Inspector modal...")
            page.evaluate("window.__app.openRunInspector(28)")
            page.wait_for_selector("#modal-run-inspector.open", timeout=5000)
            page.wait_for_timeout(4000)

            # Close modal
            page.locator("#modal-close-btn").click()
            page.wait_for_timeout(2000)

            # Part 3: Router Tab
            print("Video: Router Tab...")
            page.locator('.nav-tab[data-tab="router"]').click()
            page.wait_for_timeout(2000)

            # Verify exploration is unchecked
            chk = page.locator("#router-explore-check")
            if chk.is_checked():
                chk.uncheck()

            # 1. mlp-256w-4l, B=1, sustained, fastest
            print("Video: Select mlp-256w-4l...")
            mlp256_val = page.locator('#router-model-select option:has-text("mlp-256w-4l")').get_attribute("value")
            page.locator("#router-model-select").select_option(mlp256_val)
            page.locator("#router-batch-select").select_option("1")
            page.locator("#router-workload-select").select_option("sustained")
            page.locator("#router-mode-select").select_option("fastest")
            page.wait_for_timeout(4000)

            # 2. mlp-3072w-4l, B=1, sustained, fastest
            print("Video: Select mlp-3072w-4l...")
            mlp3072_val = page.locator('#router-model-select option:has-text("mlp-3072w-4l")').get_attribute("value")
            page.locator("#router-model-select").select_option(mlp3072_val)
            page.locator("#router-batch-select").select_option("1")
            page.locator("#router-workload-select").select_option("sustained")
            page.locator("#router-mode-select").select_option("fastest")
            page.wait_for_timeout(4000)

            # Part 4: Final Evaluation Table
            print("Video: Final Evaluation Table...")
            eval_card = page.locator(".card:has(#eval-headline-title)")
            eval_card.scroll_into_view_if_needed()
            page.wait_for_timeout(6000)

            # Close page & context to save video
            video_path_obj = page.video.path()
            page.close()
            context.close()
            browser.close()

            # Rename to siliconroute_demo.webm
            final_target = DEMO_DIR / "siliconroute_demo.webm"
            if video_path_obj and Path(video_path_obj).exists():
                shutil.move(str(video_path_obj), str(final_target))
                print(f"Video saved to {final_target} ({final_target.stat().st_size} bytes)")
            else:
                # Find any webm in DEMO_DIR
                webms = list(DEMO_DIR.glob("*.webm"))
                if webms:
                    shutil.move(str(webms[0]), str(final_target))
                    print(f"Video saved to {final_target} ({final_target.stat().st_size} bytes)")

    finally:
        print("Stopping Uvicorn server...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Uvicorn stopped.")


if __name__ == "__main__":
    record_video()
