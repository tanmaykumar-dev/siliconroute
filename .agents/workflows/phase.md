---
description: Build one phase from docs/SPEC.md with plan, tests, verification and walkthrough
---
1. Ask me which phase number (1-8) if I did not say it.
2. Read AGENTS.md, docs/SPEC.md section 12 (phase table) and every SPEC section the phase depends on. Read .agents/skills/windows-ai-hardware/SKILL.md if the phase touches ONNX Runtime, GPUs, NVML, WMI, SQLite or SSE.
3. Write an implementation plan artifact: files to create/change, functions with signatures, tests to add, and how you will verify. Keep the scope to THIS phase only. Wait for my approval or comments.
4. Implement in small steps. After each file, run `python -m pytest -q`.
5. Add or update tests for all new logic (tests may use fake numbers; app code may not).
6. Run the /verify workflow and paste real outputs.
7. Append 1-2 line entries to docs/DECISIONS.md for any design choice you made.
8. Write a walkthrough artifact: what was built, how it was verified (with outputs/screenshots), what is not done yet, and a suggested commit message.
