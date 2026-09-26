---
description: Build all phases 1-8 in order with a real-data verification gate after each; pause only for hardware steps, risky changes or repeated failures
---
1. Read AGENTS.md, docs/SPEC.md, BUILD_PROMPTS.md (sections 2-4) and .agents/skills/windows-ai-hardware/SKILL.md.
2. Create a task-list artifact: phases 1-8, each with its scope and its "Done when" criteria from BUILD_PROMPTS.md section 4. Ask me which phase to start from if I did not say.
3. For each phase, in order:
   a. Post a short implementation plan (files, functions, tests). Continue without waiting UNLESS the plan changes the stack, changes AGENTS.md/SPEC.md, deletes files, or needs a library not in requirements.txt. In those cases wait for my approval.
   b. Implement in small steps. Run `python -m pytest -q` after each file.
   c. GATE - every item must pass before the next phase:
      - `python -m pytest -q` is green (paste the summary line);
      - the /verify steps pass with REAL responses from this laptop pasted;
      - the phase's "Done when" criteria are met with real measured data;
      - the /honesty-audit checks find no fake, hardcoded or unverified numbers.
   d. If the gate fails, fix it the /fix way (cause first, smallest change, regression test). If the same gate item fails twice, STOP and report what you tried and what you think is wrong.
   e. Append decisions to docs/DECISIONS.md. Commit locally: `git add -A` then `git commit -m "phase N: <summary>"`. Never push.
   f. Post a walkthrough artifact: what was built, the gate evidence (real outputs), what is not done.
4. PAUSE and wait for me at these points:
   - phase 3 identify step: I tell you which Task Manager GPU graph jumped, then you set the labels;
   - phase 8 before energy runs: ask whether I will unplug the charger;
   - any command that needs admin rights, touches files outside this workspace, or would delete data.
5. After phase 8, write a final report artifact: number of tests, all endpoints, the per-device fit table (form, LOO MAPE of all 3 forms, t0, GFLOP/s, GB/s), router accuracy and regret vs every baseline, which metrics are "not available" on this laptop and why, and every place you were unsure or took a shortcut.
