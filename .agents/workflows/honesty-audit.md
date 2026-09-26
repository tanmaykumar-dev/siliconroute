---
description: Check the codebase for fake, hardcoded or unverified numbers
---
// turbo
1. Run `python -m pytest -q tests/test_honesty.py`.
2. Search app/ and frontend/ for numeric literals with units (ms, W, mJ, GFLOP, GB/s, °C) outside app/config.py and list each file:line.
3. Search for words like mock, fake, dummy, placeholder, example, simulate, random.uniform in app/ and frontend/ and list each hit.
4. Check that every place that displays a metric handles NULL with "not available".
5. Check that provider_used is stored for every run and that mismatched runs are excluded from fits.
6. Report findings as a table (file, line, problem, fix). Do not change code until I approve.
