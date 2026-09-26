---
description: Run tests, start the server, and check the API endpoints with real output
---
1. Activate the venv if it is not active: `venv\Scripts\activate`.
// turbo
2. Run the test suite: `python -m pytest -q`. If anything fails, stop and fix it first (explain the cause in one sentence before fixing).
3. Start the server in a separate terminal: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Wait until it says "Application startup complete".
// turbo
4. Check health: `curl.exe -s http://127.0.0.1:8000/api/health`
// turbo
5. Check system and devices: `curl.exe -s http://127.0.0.1:8000/api/system` and `curl.exe -s http://127.0.0.1:8000/api/devices`
6. Check every endpoint that the current phase added (see docs/SPEC.md section 8). Paste the real responses.
7. Stop the server.
8. Report: tests passed/failed, endpoint outputs (real), anything that still returns "not available" and why.
