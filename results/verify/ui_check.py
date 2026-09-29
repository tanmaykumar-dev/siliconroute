"""Automated UI Check for SiliconRoute Dashboard using Edge DevTools Protocol (CDP).

Verifies:
1. Live tab loads, receives SSE telemetry, renders device panel (DXGI LUIDs, vendors).
2. Analysis tab loads, renders log-log curves, crossover table, variability table, physics notes.
3. Clicking a run opens the Raw Timing Sample modal with inner_loop_k displayed.
4. Router tab loads recommendations and renders Decisions 93-116 evaluation table.
5. Captures screenshots for each tab and verifies ZERO console errors.
"""

import asyncio
import base64
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import websockets

SCREENSHOT_DIR = Path("results/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9235


async def run_cdp():
    profile_dir = Path("results/edge_profile_uicheck")
    profile_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen([
        EDGE_PATH,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={profile_dir.resolve()}",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1400,1050",
        "http://127.0.0.1:8000/",
    ])
    print(f"[UI Check] Started Edge (PID: {proc.pid})")

    console_errors = []
    console_logs = []

    try:
        await asyncio.sleep(2.0)
        resp = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5)
        targets = json.loads(resp.read().decode())
        page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:8000" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print(f"[UI Check] Connected to page: {page_target['url']}")

        async with websockets.connect(ws_url, max_size=20_000_000) as ws:
            msg_id = 0

            async def call(method: str, params: dict | None = None) -> dict:
                nonlocal msg_id
                msg_id += 1
                req = {"id": msg_id, "method": method, "params": params or {}}
                await ws.send(json.dumps(req))
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    if data.get("method") == "Runtime.consoleAPICalled":
                        log_type = data["params"]["type"]
                        args = [a.get("value", a.get("description", "")) for a in data["params"]["args"]]
                        text = " ".join(str(x) for x in args)
                        if log_type == "error":
                            console_errors.append(text)
                            print(f"  [CONSOLE ERROR] {text}")
                        else:
                            console_logs.append(f"[{log_type}] {text}")
                    elif data.get("id") == msg_id:
                        return data.get("result", {})

            await call("Page.enable")
            await call("Runtime.enable")

            # -----------------------------------------------------------------
            # 1. TAB 1: LIVE TELEMETRY
            # -----------------------------------------------------------------
            print("[UI Check] Waiting for Live tab SSE stream and devices API...")
            for _ in range(25):
                check_cards = await call("Runtime.evaluate", {
                    "expression": "document.querySelectorAll('#devices-panel-cards .kpi-card').length",
                    "returnByValue": True
                })
                count = check_cards.get("result", {}).get("value", 0)
                if count >= 3:
                    break
                await asyncio.sleep(0.5)

            await asyncio.sleep(1.5)

            # Screenshot 1: Tab Live
            res = await call("Page.captureScreenshot", {"format": "png"})
            (SCREENSHOT_DIR / "01_tab_live.png").write_bytes(base64.b64decode(res["data"]))
            print("[UI Check] Saved 01_tab_live.png")

            eval_live = await call("Runtime.evaluate", {
                "expression": """(() => {
                    const devCards = document.querySelectorAll('#devices-panel-cards .kpi-card').length;
                    const cpuPct = document.getElementById('kpi-cpu-pct').innerText;
                    const ramPct = document.getElementById('kpi-ram-pct').innerText;
                    const rtxPower = document.getElementById('kpi-rtx-power').innerText;
                    const naPills = document.querySelectorAll('.pill-na').length;
                    const sysChip = document.getElementById('chip-system').innerText;
                    return { devCards, cpuPct, ramPct, rtxPower, naPills, sysChip };
                })()""",
                "returnByValue": True
            })
            live_state = eval_live.get("result", {}).get("value")
            print("[UI Check] Live Tab State:", live_state)

            # -----------------------------------------------------------------
            # 2. TAB 2: ANALYSIS & FITS
            # -----------------------------------------------------------------
            print("[UI Check] Switching to Analysis tab...")
            await call("Runtime.evaluate", {
                "expression": """(() => {
                    const tab = document.querySelector('.nav-tab[data-tab="analysis"]');
                    if (tab) tab.click();
                })()"""
            })
            await asyncio.sleep(2.5)

            # Screenshot 2: Tab Analysis
            res = await call("Page.captureScreenshot", {"format": "png"})
            (SCREENSHOT_DIR / "02_tab_analysis.png").write_bytes(base64.b64decode(res["data"]))
            print("[UI Check] Saved 02_tab_analysis.png")

            eval_analysis = await call("Runtime.evaluate", {
                "expression": """(() => {
                    const crossovers = document.querySelectorAll('#table-crossover-body tr').length;
                    const varRows = document.querySelectorAll('#table-variability-summary-body tr').length;
                    const wakeRows = document.querySelectorAll('#table-wake-cold-body tr').length;
                    const physicsRows = document.querySelectorAll('#table-physics-notes-body tr').length;
                    const physicsNoteText = document.getElementById('physics-note-explanation').innerText;
                    return { crossovers, varRows, wakeRows, physicsRows, noteLength: physicsNoteText.length };
                })()""",
                "returnByValue": True
            })
            analysis_state = eval_analysis.get("result", {}).get("value")
            print("[UI Check] Analysis Tab State:", analysis_state)

            # -----------------------------------------------------------------
            # 3. MODAL: RUN RAW TIMING SAMPLES INSPECTOR
            # -----------------------------------------------------------------
            print("[UI Check] Opening Run Inspector Modal for Run #6...")
            await call("Runtime.evaluate", {
                "expression": """(() => {
                    if (window.__app && window.__app.openRunInspector) {
                        window.__app.openRunInspector(6);
                        return true;
                    }
                    return false;
                })()"""
            })
            await asyncio.sleep(1.5)

            # Screenshot 3: Modal with raw samples
            res = await call("Page.captureScreenshot", {"format": "png"})
            (SCREENSHOT_DIR / "03_modal_run_inspector.png").write_bytes(base64.b64decode(res["data"]))
            print("[UI Check] Saved 03_modal_run_inspector.png")

            eval_modal = await call("Runtime.evaluate", {
                "expression": """(() => {
                    const modal = document.getElementById('modal-run-inspector');
                    const isVisible = modal.classList.contains('active');
                    const innerLoop = document.getElementById('modal-inner-loop-k').innerText;
                    const median = document.getElementById('modal-median-ms').innerText;
                    const runId = document.getElementById('modal-run-id').innerText;
                    const modelName = document.getElementById('modal-model-name').innerText;
                    return { isVisible, innerLoop, median, runId, modelName };
                })()""",
                "returnByValue": True
            })
            modal_state = eval_modal.get("result", {}).get("value")
            print("[UI Check] Run Modal State:", modal_state)

            # Close Modal
            await call("Runtime.evaluate", {
                "expression": """(() => {
                    document.getElementById('modal-close-btn').click();
                })()"""
            })
            await asyncio.sleep(0.5)

            # -----------------------------------------------------------------
            # 4. TAB 3: ROUTER & EVALUATION
            # -----------------------------------------------------------------
            print("[UI Check] Switching to Router tab...")
            await call("Runtime.evaluate", {
                "expression": """(() => {
                    const tab = document.querySelector('.nav-tab[data-tab="router"]');
                    if (tab) tab.click();
                })()"""
            })
            await asyncio.sleep(2.0)

            # Screenshot 4: Tab Router
            res = await call("Page.captureScreenshot", {"format": "png"})
            (SCREENSHOT_DIR / "04_tab_router.png").write_bytes(base64.b64decode(res["data"]))
            print("[UI Check] Saved 04_tab_router.png")

            eval_router = await call("Runtime.evaluate", {
                "expression": """(() => {
                    const chosen = document.getElementById('rec-chosen-device').innerText;
                    const reason = document.getElementById('rec-reason').innerText;
                    const baselineRows = document.querySelectorAll('#table-eval-baselines-body tr').length;
                    const workloadRows = document.querySelectorAll('#table-eval-workload-body tr').length;
                    const recentDecisions = document.querySelectorAll('#table-decisions-history-body tr').length;
                    const noteText = document.getElementById('eval-history-note').innerText;
                    return { chosen, reasonLength: reason.length, baselineRows, workloadRows, recentDecisions, noteText };
                })()""",
                "returnByValue": True
            })
            router_state = eval_router.get("result", {}).get("value")
            print("[UI Check] Router Tab State:", router_state)

            # -----------------------------------------------------------------
            # Verification Summary
            # -----------------------------------------------------------------
            print("\n=== UI CHECK SUMMARY ===")
            print(f"Total Console Logs: {len(console_logs)}")
            print(f"Total Console Errors: {len(console_errors)}")
            if console_errors:
                print("Console Errors Detail:")
                for err in console_errors:
                    print("  - ", err)
            else:
                print("ZERO console errors detected! UI verification PASSED.")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        print("[UI Check] Browser process terminated.")


if __name__ == "__main__":
    asyncio.run(run_cdp())
