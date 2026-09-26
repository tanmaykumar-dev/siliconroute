# SiliconRoute — agent instructions (read FIRST, every task)

Read by Antigravity (workspace rules) and Codex. The full technical spec is
`docs/SPEC.md`. Read the SPEC section for your current phase before planning.

## Mission
SiliconRoute is a local-first, self-learning AI load balancer for laptops.
It MEASURES how AI models run on every chip (CPU, iGPU, dGPU, NPU when present),
STORES every measurement in SQLite, LEARNS a hardware model per chip
(time = overhead + FLOPs/compute + bytes/bandwidth), and ROUTES each AI task
to the best chip for the user's goal: Fastest, Battery, Balanced, Cool,
optionally under a power budget. It explains every decision and verifies it.

Software cannot control power delivery (hardware + Windows do). SiliconRoute
controls WHICH CHIP DOES THE WORK. That choice drives speed, energy and heat.

## Developer profile
First-semester engineering student, Python beginner, aiming for semiconductors.
- Simple, readable code. Plain functions and small modules. No clever tricks.
- Comment WHY, not what. Type hints on every function.
- After each change: explain in plain English what changed and why.
- Small steps. Never rewrite a working file unless asked.
- Before adding a library, say which one and why.

## Hard rules (never break)
1. NEVER invent, estimate, hardcode or "mock" measurements in app code.
   Every number shown comes from a real run stored in the DB. Missing metric
   -> store NULL, show "not available". Fake data is allowed ONLY in tests/.
2. Never claim a chip ran a model unless `session.get_providers()[0]`
   confirms it. Always store `provider_used`.
3. Local only: no cloud APIs, no external DB servers, no telemetry upload.
4. One benchmark at a time (single worker thread + lock). Return HTTP 409
   if a job is already running.
5. Never delete data or files outside `data/`, `models/`, `results/` without
   asking. Never run `rm -rf`, `git reset --hard`, or `git push --force`.
6. After every phase run `/verify` (tests + server start + endpoint checks)
   and show REAL output. If a step fails, fix it before moving on.
7. When unsure about a hardware API, read
   `.agents/skills/windows-ai-hardware/SKILL.md` instead of guessing.

## Stack (fixed — ask before changing)
- Windows 11, Python 3.12, venv in `./venv`
- FastAPI >= 0.135 (native SSE via `fastapi.sse.EventSourceResponse`),
  Uvicorn, one process, http://127.0.0.1:8000
- SQLite at `data/siliconroute.db` via SQLModel. On EVERY connection:
  `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`,
  `foreign_keys=ON`. One Session per thread. Short write transactions.
- onnxruntime-directml (CPU + one DmlExecutionProvider per GPU `device_id`),
  onnx, numpy, scipy (nnls), scikit-learn (leave-one-out validation)
- Telemetry: psutil; nvidia-ml-py (NVML) if NVIDIA present; WMI `root\wmi`
  BatteryStatus (DischargeRate in mW) via `wmi` + `pywin32`
- Frontend: static HTML + vanilla JS + Chart.js 4 (cdnjs), served by FastAPI
  from `frontend/`. No build step, no second server, no CORS.
- Tests: pytest + FastAPI TestClient (httpx)

## Commands
- Setup: `py -3.12 -m venv venv` then `venv\Scripts\activate`
  then `pip install -r requirements.txt`
- Run: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- One-click: `start.bat`
- Test: `python -m pytest -q`

## Folder layout
```
AGENTS.md  requirements.txt  start.bat  README.md  benchmark_v1.py
docs/SPEC.md  docs/DECISIONS.md (log every design decision, 1-2 lines)
app/
  main.py        FastAPI app, lifespan, routers, static frontend
  config.py      all tunable constants (runs, thresholds, epsilon...)
  db.py          engine, pragmas, SQLModel tables, session helper
  devices.py     detect CPU / each DirectML GPU / NPU; identify (blink) test
  models_gen.py  synthetic ONNX families (mlp, conv, attn) + FLOPs/bytes
  benchmark.py   latency runs, stats, output check vs CPU reference
  energy.py      idle baseline + load window energy runs
  jobs.py        single worker thread, job queue, progress, cancel
  telemetry.py   1 Hz sampler thread, ring buffer, SSE fan-out
  power.py       NVML + battery readers; each returns None if unavailable
  predictor.py   hardware-model fits per chip, LOO error, crossover
  router.py      scoring, context rules, exploration, explanations
  api/           route modules: system, devices, models, benchmarks,
                 telemetry, fits, router, decisions, export
frontend/  index.html  app.js  charts.js  style.css
data/  models/  results/  tests/
```

## Definition of done (every phase)
- Code matches docs/SPEC.md for that phase; decisions logged in
  docs/DECISIONS.md.
- `python -m pytest -q` passes; new logic has tests.
- Server starts; the phase's endpoints return real data (show output).
- No hardcoded measurements anywhere in `app/` or `frontend/`.
- Walkthrough: what was built, how verified, what is still missing.

## Style
- Python: small functions (< 40 lines), f-strings, `pathlib`, `logging`
  (not print) in app code, pydantic models for request/response bodies.
- Errors: never swallow silently; log and return `{"detail": "..."}`.
- Units in every name: `_ms`, `_w`, `_mj`, `_mb`, `_pct`, `_c`.
