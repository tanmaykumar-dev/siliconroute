# SiliconRoute — Overnight Build Run-Sheet

**What you're building:** a local web app (FastAPI backend + SQLite + browser
dashboard at http://127.0.0.1:8000) that measures every chip in your laptop,
learns a hardware model per chip, and routes each AI task to the best chip for
your goal, explaining and verifying every decision.

**Software or website?** The Unstop form asks for a title, a description
file, a GitHub link and a pitch deck (PDF + PPTX). There is no field for a
hosted website. So: a **local app with a browser dashboard on localhost**,
shared as a **GitHub repo** that anyone can run with `start.bat`. Never host
it in the cloud: a cloud server cannot see your laptop's chips.

**The kit (put all of it in your project folder):**
```
AGENTS.md                         core rules (Antigravity + Codex read it automatically)
docs/SPEC.md                      full technical spec (the agents build from this)
docs/DECISIONS.md                 why each design choice was made
.agents/rules/                    honesty, design, safety rules (always on)
.agents/workflows/                slash commands: /autopilot /phase /verify /explain /fix
                                  /honesty-audit /ui-check /collect-data
.agents/skills/windows-ai-hardware/SKILL.md   tested code patterns for the hard parts
requirements.txt  start.bat  benchmark_v1.py
```

---

## 1. Before you start (30 minutes)

1. Install **Python 3.12** (python.org, tick "Add Python to PATH"), **Git**,
   **Antigravity**, and **Codex** (CLI or IDE extension).
2. Laptop prep: charger plugged in · Armoury Crate → GPU mode **Standard** (so
   the NVIDIA GPU is visible) · close Chrome tabs (your RAM was at 91%) ·
   Windows power mode **Best performance**.
3. Create `C:\dev\siliconroute`, copy the kit in, then in a terminal:
   ```
   cd C:\dev\siliconroute
   git init
   git add -A
   git commit -m "kit: spec, rules, workflows, skill"
   ```
4. Open the folder in Antigravity as a workspace. Check Customizations:
   you should see AGENTS.md, 3 rules, 8 workflows, 1 skill.
   (Antigravity reads `.agents/`; if your version only shows `.agent/`,
   rename the folder.)
5. Antigravity settings:
   - **Planning mode ON** (it writes a plan before coding).
   - Terminal auto-execution: **Request review**. Workflow steps marked
     `// turbo` (tests, curl checks) will run automatically; everything else
     asks you first. Never approve delete commands outside data/ models/ results/.
   - Allow the browser agent on `127.0.0.1` (needed for /ui-check).
   - Models: strongest model for **planning and hard bugs**, a faster model
     for **implementing** approved plans. You can switch mid-task.

---

## 2. The golden loop (repeat for every phase)

1. **New conversation** in Antigravity → paste the phase prompt below.
2. **Read the plan artifact.** Comment directly on anything wrong. This is the
   cheapest moment to fix mistakes. Red flags are listed under each phase.
3. Approve → the agent implements and runs tests after each file.
4. It runs **/verify** → read the REAL outputs yourself.
5. Run **/explain** (5 minutes) → answer its 3 quiz questions.
6. **Codex review** (read-only, prompt in section 5) → if it finds a real bug,
   go back to Antigravity and use **/fix** with Codex's finding.
7. Commit: `git add -A` then `git commit -m "phase N: <what>"`.

Rule: **one writer at a time.** Codex reviews while Antigravity is idle.

---

## 2b. Autopilot: one prompt for the whole build

If you want to give ONE prompt and let it run, use the `/autopilot` workflow.
It still builds in 8 phases (one giant task makes agents drift and skip
checks), but it moves on by itself when a phase passes its gate, and stops only
when it needs you or when something fails twice.

Every phase gate requires: tests green, /verify with real responses from your
laptop, the phase's "Done when" criteria met with real measured data, and a
clean honesty audit. It pauses for you at the GPU identify step (phase 3), before
energy runs (phase 8), and for anything risky.

Recommended: do **phase 1 manually** (to confirm Python, DirectML and the tools
work), commit, then start autopilot from phase 2:

```
/autopilot
Continue from phase 2. Follow @AGENTS.md, @docs/SPEC.md and @BUILD_PROMPTS.md exactly.
Real data only. At every gate paste the real outputs. Stop if a gate fails twice.
```

While it runs: glance at each walkthrough's pasted outputs (does the table
really come from your laptop?), and run the Codex review between phases.

---

## 3. Night timeline (about 8.5 hours)

| Time | Phase | You end up with |
|---|---|---|
| 22:00 | Setup (section 1) | kit committed, tools configured |
| 22:30 | 1 Foundation | DB + device detection + health/system API |
| 23:15 | 2 Benchmarks | real latency runs on CPU + every GPU, job queue |
| 00:30 | 3 Telemetry + power | live 1 Hz stream, NVML/battery, energy runs, GPU labels |
| 01:30 | Break (15 min) | |
| 01:45 | 4 Predictor | 3 formulas per chip, honest error, crossover |
| 02:30 | 5 Router | modes, rules, exploration, verified decisions, baselines |
| 03:15 | 6 Dashboard | 6 tabs with real charts |
| 04:45 | 7 Hardening | start.bat from fresh clone, README, honesty test |
| 05:30 | 8 Data collection | full dataset, CSV exports, results |
| 06:15 | Wrap-up | GitHub push, send results to Claude for the deck |

If you fall behind: skip energy runs in phase 3 and the ORT-policy baseline
in phase 5. A working router with honest latency data beats a half-finished
everything.

---

## 4. Phase prompts (copy-paste)

### Phase 1: Foundation
```
/phase 1
Build Phase 1 from @docs/SPEC.md (sections 1, 4, 8, 10, 12) following @AGENTS.md.
Scope only:
- app/config.py with every constant from SPEC section 10
- app/db.py: engine + pragmas exactly as in the windows-ai-hardware skill (section 1),
  and ALL SQLModel tables from SPEC section 4 (created now, used later)
- app/devices.py: detect CPU + every DirectML adapter (skill section 3); never guess GPU names
- app/main.py with lifespan; app/api/system.py and app/api/devices.py:
  GET /api/health, GET /api/system, POST /api/devices/detect, GET /api/devices, PATCH /api/devices/{id}
- frontend/index.html placeholder served at /
- tests: tests/test_db.py (assert journal_mode == wal) and the phase-1 part of tests/test_api.py
Do NOT build benchmarks, telemetry or UI yet. Finish with /verify and show the real
/api/devices output from this laptop.
```
Red flags in the plan: Postgres/MongoDB/Docker, React/Vite/npm, "mock devices",
missing pragmas, GPU names hardcoded.
Done when: `/api/devices` lists `cpu` and `dml:0` (and `dml:1` if the NVIDIA GPU is on).
Commit: `phase 1: db, devices, system api`

### Phase 2: Models + benchmark engine + job worker
```
/phase 2
Build Phase 2 from @docs/SPEC.md sections 2.1, 3, 4, 8 following @AGENTS.md.
Scope:
- app/models_gen.py: the three synthetic families (mlp, conv, attn) with EXACT params,
  flops_per_sample and weight_bytes; dynamic batch; opset 17; ir_version 8.
  Also POST /api/models/scan for real .onnx files in models/.
- app/benchmark.py: the latency method EXACTLY as SPEC 2.1 (session_create_ms,
  provider check, fixed-seed input, warm-up, 30 timed runs with perf_counter_ns,
  median/p10/p90/mean/min/max/stdev/cv, unstable flag, CPU reference output check,
  raw_ms_json, shuffled device order, cooldown, power scheme, notes).
- app/jobs.py: single worker thread from the skill (section 8); 409 when busy; cancel.
- API: GET/POST models, POST /api/benchmarks, GET /api/benchmarks/{id},
  POST /api/benchmarks/{id}/cancel, GET /api/runs, GET /api/export/runs.csv
- tests: test_models_gen.py, test_benchmark.py (tiny model, warmup=1, runs=3), API tests incl. 409.
Then run a small REAL benchmark through the API: mlp widths [256, 1024], every device,
batch [1, 8]. Show the stored rows (device, provider_used, median_ms, cv, output_matches_cpu).
```
Red flags: timing with `time.time()`, no warm-up, benchmarks inside the async route,
threads sharing one DB session, fake rows.
Done when: real rows exist for every device, and a second start while running returns 409.
Commit: `phase 2: models, benchmark engine, job worker`

### Phase 3: Telemetry, power, energy, identify
```
/phase 3
Build Phase 3 from @docs/SPEC.md sections 2.2, 2.3, 7, 8 following @AGENTS.md.
Use the windows-ai-hardware skill sections 4-7 for NVML, WMI battery, psutil,
power scheme and SSE. Scope:
- app/power.py: readers that return None when unavailable (never raise).
- app/telemetry.py: 1 Hz sampler thread, ring buffer (3600), DB flush every 10 s,
  SSE publish from the thread (skill section 7). Start/stop in lifespan.
- app/energy.py: energy job (idle 15 s, load 30 s, settle 5 s) with battery_delta and
  nvml_counter / nvml_power methods; store idle_w, load_w, energy_mj_per_inf, energy_method.
- POST /api/devices/{id}/identify (8 s heavy load on one device).
- API: /api/telemetry/latest, /api/telemetry?seconds=, /api/telemetry/stream (SSE).
- tests for readers' None handling and the energy formula (fake numbers only in tests).
Then show 10 real telemetry samples and list which metrics are NULL on this laptop and why.
Then run identify on each GPU one by one and wait for me to tell you which Task Manager
graph jumped, and PATCH the labels.
```
Red flags: estimating CPU or AMD iGPU power ("≈ 15 W"), WMI created in one thread and
used in another, SSE that blocks the event loop.
Done when: the SSE stream shows real samples; GPUs are labelled correctly by you.
Commit: `phase 3: telemetry, power readers, energy jobs, identify`

### Phase 4: Predictor (the hardware model)
```
/phase 4
First run a latency benchmark for the full mlp and conv ladders from @docs/SPEC.md section 3
(all devices, batches [1, 8, 32]) and wait for it to finish.
Then build Phase 4 from @docs/SPEC.md section 5 following @AGENTS.md and the skill section 9:
- app/predictor.py: forms F1 roofline, F2 roofline+cache (cache_mb per device from config,
  editable), F3 log-linear; weighted NNLS for F1/F2; OLS for F3; leave-one-out MAPE for all
  three; choose the lowest per device; store model_form, loo_mape_all_json, coef_json, r2_log,
  n_samples; physical params (t0 ms, GFLOP/s, GB/s) when F1/F2 win; "not separable" note.
- crossover endpoint (section 5.4) with the 2x extrapolation limit.
- refit policy (section 5.5); POST/GET /api/fit; GET /api/analysis/crossover
- tests: recover known params from synthetic data; form selection; <6 samples -> 409.
Show a table from REAL data: device, chosen form, LOO MAPE of all 3 forms, t0, GFLOP/s, GB/s,
and the mlp crossover at batch 1 and 32. Explain in 3 sentences what these numbers mean
about my hardware.
```
Red flags: fitting on runs with provider_mismatch or unstable, extrapolating silently,
R² reported without LOO.
Done when: every device has a fit and you understand its overhead vs throughput.
Commit: `phase 4: predictor with model selection and crossover`

### Phase 5: Router (the decision engine)
```
/phase 5
Build Phase 5 from @docs/SPEC.md section 6 following @AGENTS.md.
- app/router.py: candidates + excluded reasons, predictions, normalisation, the 4 mode scores,
  context rules (low battery, busy GPU, power budget), exploration with a seeded RNG,
  plain-English reason with real predicted numbers only.
- verify job: measure chosen + all candidates (VERIFY_RUNS), store runs, set actual_ms,
  best_device_id_actual, was_best, regret_pct.
- GET /api/decisions, GET /api/decisions/stats with baselines always-CPU and always-fastest-GPU.
  Stretch: ORT policy baseline via hasattr(ort.SessionOptions, "set_provider_selection_policy");
  if missing or failing, report "not available on this ORT build". Do not fake it.
- tests from SPEC section 11 (test_router.py).
Then run 12 verified decisions: mlp and conv, small/medium/large sizes, batch 1 and 32,
modes fastest and balanced. Show accuracy, mean regret, and the baselines.
```
Red flags: reason text with numbers not taken from predictions, battery mode silently
using speed without saying so, exploration without the explored flag.
Commit: `phase 5: router, verification, stats and baselines`

### Phase 6: Dashboard
```
/phase 6
Build the dashboard from @docs/SPEC.md section 9 following @AGENTS.md and
.agents/rules/02-design.md. Plain HTML + JS modules + Chart.js 4 from cdnjs (pinned).
Tabs: Live (SSE charts), Benchmark (start/progress/results + identify + label editor),
Analysis (log-log scatter with fitted curves, physical params table with all 3 LOO scores,
predicted-vs-actual with y=x, energy-vs-time Pareto, crossover table),
Router (decision card + candidates table + Run & verify), History (decisions, accuracy and
regret vs baselines, regret histogram), About (method, honesty rule, hardware).
Every number must come from the API; show "not available" pills for NULLs.
When done, run /ui-check and attach final screenshots.
```
Red flags: glassmorphism/animations (the design rule forbids them), numbers typed
into HTML, a second dev server, npm.
Commit: `phase 6: dashboard`

### Phase 7: Hardening
```
/phase 7
Harden the project following @AGENTS.md:
- Graceful behaviour with no NVIDIA GPU, no battery, no DirectML, empty database
  (clear empty states, no crashes). Add tests for each.
- tests/test_honesty.py from @docs/SPEC.md section 11. Then run /honesty-audit.
- README.md: problem, how it works (4 parts, with the Mermaid diagram from SPEC section 1),
  install + start.bat, screenshots from /ui-check, method (warm-up, median, verification),
  limitations (DirectML maintenance mode, no CPU/iGPU power sensors, energy only when
  unplugged), roadmap (Snapdragon NPU via QNNExecutionProvider, Windows ML, per-layer
  splitting), and an EMPTY results table that phase 8 will fill from exported CSVs.
- Fresh-clone test: git clone . ..\sr-test, run start.bat there, confirm the app opens.
Paste real outputs.
```
Commit: `phase 7: hardening, readme, honesty test`

### Phase 8: Real data collection
```
/collect-data
```
Then send Claude `results/runs.csv` and `results/decisions.csv` (or screenshots of the
Analysis and History tabs) to fill the pitch deck's results slide and the description.
Commit: `phase 8: real dataset and results`

---

## 5. Codex: reviewer and test-writer

Codex reads `AGENTS.md` automatically.

**After every phase (read-only review):**
```
Read AGENTS.md and docs/SPEC.md. Review the last commit (git show --stat HEAD, then the diff).
Do NOT edit files. Report a table: severity (bug / spec violation / test gap / style),
file:line, problem, suggested fix. Check especially: fake or hardcoded numbers, missing
provider_used checks, DB sessions shared between threads, blocking calls inside async routes,
missing NULL handling, WMI used across threads, and tests that assert nothing.
```

**Extra tests (only while Antigravity is idle):**
```
Write additional pytest tests ONLY inside tests/ for the modules changed in the last commit.
Target edge cases: empty DB, single device, NULL power data, cancelled job, 409 on double start,
fewer than 6 samples for a fit. Run python -m pytest -q and show the output. Do not modify app/.
```

**Second opinion on a stubborn bug:**
```
Here is an error and the relevant file. Explain the most likely root cause and the smallest fix.
Do not edit anything. <paste error> <@file>
```

---

## 6. Rescue prompts

- **Agent loops on the same bug:** start a new conversation, then
  `/fix` + paste the full error + `@app/<file>.py`.
- **"database is locked":** "Check that every connection sets the pragmas from the skill
  section 1, that each thread uses its own Session, and that no transaction stays open during a
  benchmark. Show me where each Session is created."
- **DirectML import/provider errors:**
  `pip uninstall -y onnxruntime onnxruntime-directml` then
  `pip install onnxruntime-directml`, then run
  `python -c "import onnxruntime as o; print(o.get_available_providers())"` (must list DmlExecutionProvider).
- **NVIDIA GPU missing:** Armoury Crate → GPU mode Standard/Ultimate, plug in, then
  `nvidia-smi` in a terminal should show the GPU.
- **Agent invented numbers:** "Where did this number come from? Show the exact command and its
  output. If you can't, remove it and show 'not available'."
- **Agent went out of scope:** "Stop. List every file you changed that is outside this phase's
  scope and restore each one with `git checkout -- <path>`." Then restate the scope.
- **UI broken:** take a screenshot, paste it (Ctrl+V) into the chat, run `/ui-check`.
- **pip install fails on a package:** "Show the full error; suggest a pinned version that
  supports Python 3.12 on Windows; do not switch Python versions without asking."

---

## 7. Morning checklist

- [ ] `python -m pytest -q` all green
- [ ] Fresh clone + `start.bat` works
- [ ] `/collect-data` done, CSVs in `results/`
- [ ] README results table filled ONLY from the CSVs, plus screenshots
- [ ] Push to GitHub:
  ```
  git remote add origin https://github.com/YOUR-USERNAME/siliconroute.git
  git branch -M main
  git push -u origin main
  ```
- [ ] Send results to Claude → deck slide 7 + description section 5 filled, PDFs regenerated
- [ ] Record a 2-3 minute demo video (script below)
- [ ] Answer the 10 questions below without help

## 8. Demo video script (about 2.5 minutes)

| Time | Show | Say |
|---|---|---|
| 0:00 | Title / About tab | "Laptops have several AI chips, apps use one, and never check if it was right." |
| 0:20 | Live tab | "Everything runs locally; this is real CPU, GPU and battery data." |
| 0:40 | Benchmark tab | "It measures each model on every chip: warm-up, 30 runs, median, output check." |
| 1:10 | Analysis tab | "It learns each chip's overhead and throughput. Here's where the GPU starts beating the CPU." |
| 1:40 | Router tab | "I pick a goal; it picks a chip, explains why, then verifies by measuring." |
| 2:10 | History tab | "It chose the best chip X% of the time, vs Y% for always-GPU." (real numbers only) |
| 2:30 | GitHub README | "Open source, one-click start. Next step: the Snapdragon NPU." |

## 9. Ten questions you must be able to answer

1. Why is the CPU often faster for tiny models?
2. What does `t0` mean physically?
3. Why warm up before timing, and why report the median, not the mean?
4. Why does the biggest model slow down more than expected on the CPU? (cache vs DRAM)
5. Why SQLite in WAL mode instead of PostgreSQL for this app?
6. Software can't control power delivery. What does SiliconRoute control, and why does it matter?
7. How is energy per inference measured, and why only when unplugged (or via NVML)?
8. What's the difference between LOO MAPE and decision accuracy? Which matters more for a router?
9. Why does the router sometimes pick a chip it thinks is slightly worse?
10. What would you change to support the Snapdragon NPU?
