# Safety and version control

- Never run: rm -rf, del /s, Remove-Item -Recurse on project folders,
  git reset --hard, git clean -fd, git push --force, format/diskpart.
- Only delete files inside data/, models/, results/ and only when asked.
- Do not edit files outside this workspace. Do not change AGENTS.md,
  docs/SPEC.md or .agents/ unless I explicitly ask.
- One writer at a time: if I say Codex is working, do not edit files.
- At the end of every phase, suggest a commit message; I will commit.
- Never put secrets, tokens or personal paths into code or docs.
