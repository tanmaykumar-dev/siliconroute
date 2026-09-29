# Verbatim Logs (always on)

- Every command whose output you report must save its output to
  results/logs/<phase>/<step>.txt, e.g.
  <command> 2>&1 | Tee-Object -FilePath results/logs/phase6/<step>.txt
- Reports may only show outputs by printing those log files (Get-Content). Never retype,
  summarize into tables, or write "verbatim" blocks from memory.
- Any list, table or number in a report that is not in a log file makes the phase FAIL.
