# Safety and version control

- Never run: rm -rf, del /s, Remove-Item -Recurse on project folders,
  git reset --hard, git clean -fd, git push --force, format/diskpart.
- Only delete files inside data/, models/, results/ and only when asked.
- Do not edit files outside this workspace. Do not change AGENTS.md,
  docs/SPEC.md or .agents/ unless I explicitly ask.
- One writer at a time: if I say Codex is working, do not edit files.
- Local commits are allowed at the end of each phase (`git add -A`, `git commit`).
  Never push, never rewrite history.
- Never put secrets, tokens or personal paths into code or docs.
