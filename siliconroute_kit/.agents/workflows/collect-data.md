---
description: Collect the real dataset for the results slide and README
---
1. Remind me to: close other apps and browser tabs, set Armoury Crate GPU mode to Standard, plug in the charger, and write the Armoury Crate power mode into the session notes.
2. Create the default synthetic ladders for mlp, conv and attn (docs/SPEC.md section 3).
3. Run a latency benchmark: all models x all devices x batches [1, 8, 32]. Show progress. If any device mismatches or gives wrong outputs, report it.
4. Fit latency models (POST /api/fit). Report per device: chosen form, LOO MAPE for all 3 forms, and physical parameters.
5. Run 20 route decisions with verify=true across families, sizes, batches and modes. Report accuracy, mean regret, and baselines.
6. Ask me whether to unplug the charger for energy runs. If yes: run energy jobs for 3 sizes per family on each device; refit energy; report.
7. Export runs.csv and decisions.csv into results/.
8. Update the README results table ONLY with numbers from the exported files, and state the date and hardware.
