---
description: Fix an error properly - cause first, minimal change, regression test
---
1. Ask me to paste the full error and what I was doing, if I did not.
2. Explain the root cause in 1-3 sentences BEFORE changing anything. If unsure, add logging or run a small experiment to confirm the cause.
3. Make the smallest change that fixes the cause (not the symptom). Do not refactor unrelated code.
4. Add a regression test that fails before the fix and passes after, when possible.
5. Run `python -m pytest -q` and the relevant part of /verify. Paste real output.
6. If the same error survives 2 attempts, stop and tell me what you learned and what you would try next.
