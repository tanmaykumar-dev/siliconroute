# Autonomy (always on)
This overrides any "ask me first" or "wait for my OK" wording in rule 03 or earlier prompts,
except for the hard stops listed at the end.
- Do not ask for approval of plans, file edits, test runs, benchmarks, or installing packages
  already in requirements.txt. Decide, act, and log each non-obvious decision in
  docs/DECISIONS.md (one line: what + why).
- If something is unclear, pick the option most consistent with AGENTS.md and docs/SPEC.md,
  state your assumption in the walkthrough, and continue.
- If a step fails, fix it yourself (find the cause first, make the smallest fix, add a
  regression test). After 3 failed attempts on the same problem, record it as "unresolved"
  in the report and continue with the rest.
- Deleting or changing database rows is allowed ONLY for test, debug or stray rows (never rows
  from real benchmark sessions), and ONLY after copying data/siliconroute.db to
  data/backups/<phase>_<time>.db. List every deleted or changed row in the report.
- New libraries not in requirements.txt: allowed if small and necessary. Add them to
  requirements.txt and log why.
- All AGENTS.md hard rules and honesty rules still apply: real data only, script-printed
  outputs, no fake numbers, dry_run for experiments, no --amend, never push.

Hard stops (the ONLY times you may stop and ask me):
1. A physical action is needed (e.g. unplug the charger, watch Task Manager).
2. Something would delete or change data from real benchmark sessions, or files outside
   this project.
3. Anything that would publish or upload (git push, sharing, network uploads).
4. The phase is complete: stop with "READY FOR INDEPENDENT VERIFICATION" as in our gate.
