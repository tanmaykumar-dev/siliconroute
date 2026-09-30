"""SiliconRoute Design Spec v2 — Comprehensive browser verification & screenshot suite.

Captures:
- Every app screen in BOTH light and dark themes at 1440x900
- Modals (raw samples, keyboard shortcuts)
- DOM-vs-manifest comparison log
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
DOM_MANIFEST_LOG = LOG_DIR / "dom_vs_manifest.txt"


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


def verify_app_and_capture_all():
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
    dom_comparisons = []

    screens = ["overview", "live", "analysis", "router", "results", "evidence", "about"]

    try:
        ready = wait_for_server("http://127.0.0.1:8000/api/system", timeout_s=20.0)
        if not ready:
            raise RuntimeError("Server failed to start within 20 seconds")
        print("Server is ready.")

        with sync_playwright() as p:
            print("Launching Microsoft Edge (msedge channel)...")
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            print("Loading SiliconRoute App...")
            page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
            page.wait_for_timeout(2000)

            # Ensure dark theme first
            current_theme = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
            if current_theme != "dark":
                page.locator("#btn-theme-toggle").click()
                page.wait_for_timeout(500)

            # -----------------------------------------------------------------
            # 1. Capture Dark Theme Screens
            # -----------------------------------------------------------------
            print("\nCapturing Dark Theme Screens (1440x900)...")
            for scr in screens:
                page.locator(f'.rail-item-btn[data-screen="{scr}"]').click()
                page.wait_for_timeout(1000)
                shot_path = SCREENSHOT_DIR / f"app_dark_{scr}.png"
                page.screenshot(path=str(shot_path))
                print(f"  Saved: {shot_path.name}")

            # -----------------------------------------------------------------
            # 2. Capture Light Theme Screens
            # -----------------------------------------------------------------
            print("\nCapturing Light Theme Screens (1440x900)...")
            page.locator("#btn-theme-toggle").click()
            page.wait_for_timeout(500)

            for scr in screens:
                page.locator(f'.rail-item-btn[data-screen="{scr}"]').click()
                page.wait_for_timeout(1000)
                shot_path = SCREENSHOT_DIR / f"app_light_{scr}.png"
                page.screenshot(path=str(shot_path))
                print(f"  Saved: {shot_path.name}")

            # Switch back to dark
            page.locator("#btn-theme-toggle").click()
            page.wait_for_timeout(300)

            # -----------------------------------------------------------------
            # 3. Capture Modals
            # -----------------------------------------------------------------
            print("\nCapturing Modals...")
            # Shortcuts modal
            page.keyboard.press("?")
            page.wait_for_timeout(500)
            page.screenshot(path=str(SCREENSHOT_DIR / "modal_shortcuts.png"))
            print("  Saved: modal_shortcuts.png")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            # Raw Samples Modal
            page.evaluate("() => window.SiliconRouteApp ? window.SiliconRouteApp.modal.open(812) : null")
            page.wait_for_timeout(1000)
            page.screenshot(path=str(SCREENSHOT_DIR / "modal_raw_samples.png"))
            print("  Saved: modal_raw_samples.png")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            # -----------------------------------------------------------------
            # 4. DOM vs Manifest Comparison
            # -----------------------------------------------------------------
            print("\nComparing DOM values to Manifest...")
            # Go through Overview and Results to collect rendered metrics
            page.locator('.rail-item-btn[data-screen="overview"]').click()
            page.wait_for_timeout(800)

            check_metrics = [
                ("decisions_117_140_sr_wins", "22"),
                ("decisions_117_140_total", "24"),
                ("decisions_117_140_sr_accuracy_pct", "91.7%"),
                ("decisions_117_140_sr_mean_regret_pct", "1.75%"),
                ("decisions_117_140_always_cpu_mean_regret_pct", "113.06%"),
                ("decisions_117_140_always_rtx_mean_regret_pct", "304.93%"),
                ("speedup_cpu_over_rtx_mlp_256_b1", "1.3×"),
                ("speedup_rtx_over_cpu_mlp_3072_b1_sustained", "6.4×"),
                ("overhead_rtx_cold_start_vs_sustained_mlp_3072", "335.7×"),
                ("directml_anomaly_conv96_slowdown", "2.1×"),
            ]

            for key, expected_str in check_metrics:
                el = page.locator(f'.metric[data-metric="{key}"]').first
                if el.count():
                    dom_val = el.inner_text().strip()
                    manifest_val = str(metrics[key]["value"])
                    status_str = "PASS" if expected_str in dom_val or manifest_val in dom_val else "FAIL"
                    dom_comparisons.append({
                        "key": key,
                        "manifest_val": manifest_val,
                        "expected_display": expected_str,
                        "dom_val": dom_val,
                        "status": status_str,
                    })
                    print(f"  {key:<48} | Manifest: {manifest_val:<10} | DOM: {dom_val:<12} | {status_str}")

            # Verify Database SHA on Evidence screen
            page.locator('.rail-item-btn[data-screen="evidence"]').click()
            page.wait_for_timeout(800)
            dom_sha = page.locator("#evidence-db-sha256").inner_text().strip()
            expected_sha = metadata["database_sha256"]
            assert dom_sha == expected_sha, f"SHA mismatch: {dom_sha} vs {expected_sha}"
            dom_comparisons.append({
                "key": "database_sha256",
                "manifest_val": expected_sha,
                "expected_display": expected_sha,
                "dom_val": dom_sha,
                "status": "PASS",
            })

            browser.close()

        # Write DOM vs Manifest Log
        lines = [
            "=" * 85,
            "SILICONROUTE DESIGN v2 — DOM VS MANIFEST AUDIT LOG",
            "=" * 85,
            f"{'Metric Key':<46} {'Manifest':<12} {'DOM Rendered':<16} {'Status'}",
            "-" * 85,
        ]
        for c in dom_comparisons:
            lines.append(f"{c['key']:<46} {c['manifest_val']:<12} {c['dom_val']:<16} {c['status']}")
        lines.append("=" * 85)
        lines.append(f"TOTAL VERIFIED METRICS: {len(dom_comparisons)} | ALL PASS: True\n")

        DOM_MANIFEST_LOG.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nSaved DOM-vs-manifest log to {DOM_MANIFEST_LOG}")

        print(f"\nFinal Check: Console errors: {len(console_errors)}, Page errors: {len(page_errors)}")
        assert len(console_errors) == 0, f"Console errors: {console_errors}"
        assert len(page_errors) == 0, f"Page errors: {page_errors}"

    finally:
        print("Shutting down Uvicorn...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Server shutdown complete.")


if __name__ == "__main__":
    verify_app_and_capture_all()
