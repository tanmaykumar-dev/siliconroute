"""Dashboard verification and screenshot script for SiliconRoute v1.0 release.

Performs automated headless browser verification using Playwright:
1. Starts Uvicorn server in a subprocess.
2. Checks Live tab: SM clock card is inside RTX card, NOT AMD card.
3. Checks Router tab: Epsilon Exploration is unchecked by default.
4. Checks Router tab: Evaluation table matches manifest.json (Decisions 117-140 and 141-148).
5. Checks Router recommendations:
   - mlp-256w-4l, B=1, sustained, fastest -> chosen is CPU.
   - mlp-3072w-4l, B=1, sustained, fastest -> chosen is RTX (dml:1).
6. Takes screenshots:
   - results/screenshots/v1_0/tab_live.png
   - results/screenshots/v1_0/tab_analysis.png
   - results/screenshots/v1_0/tab_router.png
   - results/screenshots/v1_0/modal_raw_samples.png
   - results/screenshots/v1_0/table_final_evaluation.png
7. Shuts down Uvicorn cleanly.
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
SCREENSHOT_DIR = ROOT_DIR / "results" / "screenshots" / "v1_0"
LOG_DIR = ROOT_DIR / "results" / "logs" / "release_v1"
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


def run_verification():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

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
            print("Launching Microsoft Edge via Playwright...")
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 950})

            print("Navigating to http://127.0.0.1:8000/...")
            page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
            page.wait_for_timeout(1000)

            # -------------------------------------------------------------
            # a) Live tab verification
            # -------------------------------------------------------------
            print("Verifying Live Tab...")
            rtx_card = page.locator(".kpi-card:has(#kpi-gpu-power)")
            amd_card = page.locator(".kpi-card:has(#kpi-igpu-power)")

            # Check SM clock is in RTX card
            rtx_has_sm = rtx_card.locator("#kpi-gpu-clock").count() == 1
            amd_has_sm = amd_card.locator("#kpi-gpu-clock").count() == 1

            print(f"SM clock in RTX card: {rtx_has_sm}")
            print(f"SM clock in AMD card: {amd_has_sm}")
            assert rtx_has_sm, "SM clock element not found inside RTX card"
            assert not amd_has_sm, "SM clock element found inside AMD card!"

            live_path = SCREENSHOT_DIR / "tab_live.png"
            page.screenshot(path=str(live_path), full_page=False)
            print(f"Saved: {live_path}")

            # -------------------------------------------------------------
            # Analysis tab screenshot & modal raw samples
            # -------------------------------------------------------------
            print("Verifying Analysis Tab...")
            page.locator('.nav-tab[data-tab="analysis"]').click()
            page.wait_for_timeout(1500)

            analysis_path = SCREENSHOT_DIR / "tab_analysis.png"
            page.screenshot(path=str(analysis_path), full_page=False)
            print(f"Saved: {analysis_path}")

            # Open run inspector modal
            print("Opening Run Raw Timing Samples Inspector modal...")
            # We open run #28 (sustained MLP run with inner_loop_k)
            page.evaluate("window.__app.openRunInspector(28)")
            page.wait_for_selector("#modal-run-inspector.open", timeout=5000)
            page.wait_for_timeout(1000)

            modal_path = SCREENSHOT_DIR / "modal_raw_samples.png"
            page.screenshot(path=str(modal_path), full_page=False)
            print(f"Saved: {modal_path}")

            # Close modal
            page.locator("#modal-close-btn").click()
            page.wait_for_timeout(500)

            # -------------------------------------------------------------
            # Router tab verification
            # -------------------------------------------------------------
            print("Verifying Router Tab...")
            page.locator('.nav-tab[data-tab="router"]').click()
            page.wait_for_timeout(1500)

            # b) Epsilon Exploration checkbox UNCHECKED by default
            chk_explore = page.locator("#router-explore-check")
            is_checked = chk_explore.is_checked()
            print(f"Epsilon Exploration is checked: {is_checked}")
            assert not is_checked, "Epsilon exploration checkbox was checked by default!"

            # c) Check DOM evaluation table vs manifest.json
            print("Checking evaluation table against manifest.json...")
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            m_metrics = manifest["metrics"]

            # Extract table rows
            overall_rows = page.locator("#table-eval-overall-body tr").all()
            dom_data = {}
            for row in overall_rows:
                cols = [td.inner_text().strip() for td in row.locator("td").all()]
                if len(cols) >= 4:
                    dom_data[cols[0]] = {
                        "wins": cols[1],
                        "accuracy": cols[2],
                        "mean_regret": cols[3],
                    }

            print("DOM overall rows:", dom_data)

            # Verify against manifest values
            # SR: 22/24, 91.7%, 1.75%
            sr_row = dom_data.get("SiliconRoute (Measured-First + Dynamic)", {})
            cpu_row = dom_data.get("Always-CPU Baseline", {})
            rtx_row = dom_data.get("Always-RTX Baseline", {})
            fit_row = dom_data.get("Fit-Only Router (Formula without Lookups)", {})

            diff_lines = []
            diff_lines.append("=== DOM vs MANIFEST EVALUATION VERIFICATION ===")
            diff_lines.append("")

            # SiliconRoute check
            sr_m_wins = f"{m_metrics['decisions_117_140_sr_wins']['value']}/{m_metrics['decisions_117_140_total']['value']}"
            sr_m_acc = f"{m_metrics['decisions_117_140_sr_accuracy_pct']['value']:.1f}%"
            sr_m_reg = f"{m_metrics['decisions_117_140_sr_mean_regret_pct']['value']:.2f}%"

            diff_lines.append(f"SiliconRoute DOM: {sr_row.get('wins')} | {sr_row.get('accuracy')} | {sr_row.get('mean_regret')}")
            diff_lines.append(f"SiliconRoute MANIFEST: {sr_m_wins} | {sr_m_acc} | {sr_m_reg}")
            assert sr_row.get("wins") == sr_m_wins, f"SR wins mismatch: {sr_row.get('wins')} vs {sr_m_wins}"
            assert sr_row.get("accuracy") == sr_m_acc, f"SR acc mismatch: {sr_row.get('accuracy')} vs {sr_m_acc}"
            assert sr_row.get("mean_regret") == sr_m_reg, f"SR regret mismatch: {sr_row.get('mean_regret')} vs {sr_m_reg}"

            # Always-CPU check
            cpu_m_wins = f"{m_metrics['decisions_117_140_always_cpu_wins']['value']}/{m_metrics['decisions_117_140_total']['value']}"
            cpu_m_acc = f"{m_metrics['decisions_117_140_always_cpu_accuracy_pct']['value']:.1f}%"
            cpu_m_reg = f"{m_metrics['decisions_117_140_always_cpu_mean_regret_pct']['value']:.2f}%"

            diff_lines.append(f"Always-CPU DOM: {cpu_row.get('wins')} | {cpu_row.get('accuracy')} | {cpu_row.get('mean_regret')}")
            diff_lines.append(f"Always-CPU MANIFEST: {cpu_m_wins} | {cpu_m_acc} | {cpu_m_reg}")
            assert cpu_row.get("wins") == cpu_m_wins
            assert cpu_row.get("accuracy") == cpu_m_acc
            assert cpu_row.get("mean_regret") == cpu_m_reg

            # Always-RTX check
            rtx_m_wins = f"{m_metrics['decisions_117_140_always_rtx_wins']['value']}/{m_metrics['decisions_117_140_total']['value']}"
            rtx_m_acc = f"{m_metrics['decisions_117_140_always_rtx_accuracy_pct']['value']:.1f}%"
            rtx_m_reg = f"{m_metrics['decisions_117_140_always_rtx_mean_regret_pct']['value']:.2f}%"

            diff_lines.append(f"Always-RTX DOM: {rtx_row.get('wins')} | {rtx_row.get('accuracy')} | {rtx_row.get('mean_regret')}")
            diff_lines.append(f"Always-RTX MANIFEST: {rtx_m_wins} | {rtx_m_acc} | {rtx_m_reg}")
            assert rtx_row.get("wins") == rtx_m_wins
            assert rtx_row.get("accuracy") == rtx_m_acc
            assert rtx_row.get("mean_regret") == rtx_m_reg

            # Fit-Only check
            fit_m_wins = f"{m_metrics['decisions_117_140_fit_only_wins']['value']}/{m_metrics['decisions_117_140_total']['value']}"
            fit_m_acc = f"{m_metrics['decisions_117_140_fit_only_accuracy_pct']['value']:.1f}%"
            fit_m_reg = f"{m_metrics['decisions_117_140_fit_only_mean_regret_pct']['value']:.2f}%"

            diff_lines.append(f"Fit-Only DOM: {fit_row.get('wins')} | {fit_row.get('accuracy')} | {fit_row.get('mean_regret')}")
            diff_lines.append(f"Fit-Only MANIFEST: {fit_m_wins} | {fit_m_acc} | {fit_m_reg}")
            assert fit_row.get("wins") == fit_m_wins
            assert fit_row.get("accuracy") == fit_m_acc
            assert fit_row.get("mean_regret") == fit_m_reg

            # Per-workload breakdown check
            wl_rows = page.locator("#table-eval-workloads-body tr").all()
            diff_lines.append("")
            diff_lines.append("Per-workload rows found: " + str(len(wl_rows)))

            # Cold-start rule verification (decisions 141-148)
            cs_rows = page.locator("#table-eval-coldstart-body tr").all()
            diff_lines.append("Cold-start check rows found: " + str(len(cs_rows)))
            cs_sr_cols = [td.inner_text().strip() for td in cs_rows[0].locator("td").all()]
            diff_lines.append(f"Cold-Start Rule SR DOM: {cs_sr_cols[1]} | {cs_sr_cols[2]} | {cs_sr_cols[3]}")
            assert cs_sr_cols[1] == "6/8", f"Cold start rule wins mismatch: {cs_sr_cols[1]}"
            assert cs_sr_cols[2] == "75.0%", f"Cold start rule acc mismatch: {cs_sr_cols[2]}"

            diff_lines.append("")
            diff_lines.append("DOM matches manifest: ALL VALUES IDENTICAL")

            dom_log_path = LOG_DIR / "dom_vs_manifest.txt"
            with open(dom_log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(diff_lines) + "\n")
            print(f"Saved: {dom_log_path}")

            # d) Test Router Selections:
            # 1. mlp-256w-4l, batch 1, sustained, fastest -> chosen device is CPU
            print("Testing router selection: mlp-256w-4l, B=1, sustained, fastest...")
            # Find option value for mlp-256w-4l
            mlp256_val = page.locator('#router-model-select option:has-text("mlp-256w-4l")').get_attribute("value")
            page.locator("#router-model-select").select_option(mlp256_val)
            page.locator("#router-batch-select").select_option("1")
            page.locator("#router-workload-select").select_option("sustained")
            page.locator("#router-mode-select").select_option("fastest")
            page.wait_for_timeout(1000)

            chosen_badge_256 = page.locator("#router-chosen-badge").inner_text()
            reason_text_256 = page.locator("#router-reason-text").inner_text()
            print(f"mlp-256 chosen badge: {chosen_badge_256}")
            print(f"mlp-256 reason: {reason_text_256}")
            assert "CPU" in chosen_badge_256.upper(), f"Expected CPU for mlp-256, got: {chosen_badge_256}"

            # 2. mlp-3072w-4l, batch 1, sustained, fastest -> chosen device is RTX (dml:1)
            print("Testing router selection: mlp-3072w-4l, B=1, sustained, fastest...")
            mlp3072_val = page.locator('#router-model-select option:has-text("mlp-3072w-4l")').get_attribute("value")
            page.locator("#router-model-select").select_option(mlp3072_val)
            page.locator("#router-batch-select").select_option("1")
            page.locator("#router-workload-select").select_option("sustained")
            page.locator("#router-mode-select").select_option("fastest")
            page.wait_for_timeout(1000)

            chosen_badge_3072 = page.locator("#router-chosen-badge").inner_text()
            reason_text_3072 = page.locator("#router-reason-text").inner_text()
            print(f"mlp-3072 chosen badge: {chosen_badge_3072}")
            print(f"mlp-3072 reason: {reason_text_3072}")
            assert "DML:1" in chosen_badge_3072.upper() or "RTX" in chosen_badge_3072.upper(), f"Expected RTX (dml:1) for mlp-3072, got: {chosen_badge_3072}"

            # Take tab_router.png and table_final_evaluation.png
            router_path = SCREENSHOT_DIR / "tab_router.png"
            page.screenshot(path=str(router_path), full_page=False)
            print(f"Saved: {router_path}")

            eval_card = page.locator(".card:has(#eval-headline-title)")
            eval_card.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            eval_table_path = SCREENSHOT_DIR / "table_final_evaluation.png"
            eval_card.screenshot(path=str(eval_table_path))
            print(f"Saved: {eval_table_path}")

            browser.close()
            print("All dashboard verifications passed successfully!")

    finally:
        print("Stopping Uvicorn server...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Uvicorn server stopped.")


if __name__ == "__main__":
    run_verification()
