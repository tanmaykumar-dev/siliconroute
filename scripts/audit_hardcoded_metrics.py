"""Audit scripts/metrics.py for hardcoded session_id, run id, decision_id."""

import ast
import re
from pathlib import Path

metrics_code = Path("scripts/metrics.py").read_text(encoding="utf-8")

# Find all functions
lines = metrics_code.splitlines()

hardcoded_funcs = []
current_func = None
func_lines = {}

for idx, line in enumerate(lines):
    m = re.match(r"^def\s+([a-zA-Z0-9_]+)\(", line)
    if m:
        current_func = m.group(1)
        func_lines[current_func] = []
    if current_func:
        func_lines[current_func].append((idx + 1, line))

for func_name, f_lines in func_lines.items():
    f_text = "\n".join(l[1] for l in f_lines)
    # Check for hardcoded session_id, run_id, decision_id
    matches = []
    for line_no, l_str in f_lines:
        if re.search(r'\b(session_id|decision_id|run_id|id)\s*(=|!=|IN|between)\s*(\d+)', l_str, re.IGNORECASE):
            matches.append((line_no, l_str.strip()))
        elif re.search(r'session_id\s*>=\s*\d+', l_str):
            matches.append((line_no, l_str.strip()))
    if matches:
        hardcoded_funcs.append((func_name, matches))

print(f"Found {len(hardcoded_funcs)} functions with hardcoded session/decision/run IDs:")
for f_name, m_list in hardcoded_funcs:
    print(f"\nFunction: {f_name}")
    for l_no, l_str in m_list:
        print(f"  Line {l_no}: {l_str}")
