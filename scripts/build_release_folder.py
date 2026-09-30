"""Build release/siliconroute-v1.0 package.

Follows Step 5 instructions:
- Copies git-tracked files excluding non-final dbs, backups, onnx models, review_package*, scratch files.
- Redacts absolute paths and personal information, logging to results/logs/release_v1/redactions.txt.
- Verifies no file exceeds 50 MB, logging file count and total size to results/logs/release_v1/release_size.txt.
- Adds LICENSE (MIT, Copyright (c) 2026 Tanmay) and PUBLISH.md.
- Runs python -m pytest -q in the release folder, logging output to results/logs/release_v1/pytest_release.txt.
"""

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
RELEASE_DIR = ROOT_DIR / "release" / "siliconroute-v1.0"
LOG_DIR = ROOT_DIR / "results" / "logs" / "release_v1"
FROZEN_DB_SHA = "98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5"


def should_exclude(rel_path: str) -> bool:
    posix_path = rel_path.replace("\\", "/")
    # Except any *.db other than data/final/siliconroute_final.db
    if posix_path.endswith(".db") and posix_path != "data/final/siliconroute_final.db":
        return True
    if posix_path.startswith("data/backups/"):
        return True
    if posix_path.startswith("models/") and posix_path.endswith(".onnx"):
        return True
    if "review_package" in posix_path:
        return True
    if "scratch" in posix_path:
        return True
    if posix_path.startswith("release/"):
        return True
    return False


def get_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_release():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if RELEASE_DIR.exists():
        print(f"Cleaning existing {RELEASE_DIR}...")
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Get git tracked files
    tracked_files = subprocess.check_output(["git", "ls-files"], cwd=str(ROOT_DIR), text=True).splitlines()
    print(f"Total git-tracked files: {len(tracked_files)}")

    copied_count = 0
    for rel_path in tracked_files:
        if should_exclude(rel_path):
            continue
        src = ROOT_DIR / rel_path
        dst = RELEASE_DIR / rel_path
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied_count += 1

    print(f"Copied {copied_count} files to {RELEASE_DIR}")

    # Verify frozen db presence and sha256
    rel_db = RELEASE_DIR / "data" / "final" / "siliconroute_final.db"
    assert rel_db.exists(), f"Frozen database missing from release folder: {rel_db}"
    db_sha = get_file_sha256(rel_db)
    print(f"Release frozen db SHA256: {db_sha}")
    assert db_sha == FROZEN_DB_SHA, f"Database sha mismatch: {db_sha} != {FROZEN_DB_SHA}"

    # 2. Add LICENSE
    license_text = """MIT License

Copyright (c) 2026 Tanmay

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
    with open(RELEASE_DIR / "LICENSE", "w", encoding="utf-8") as f:
        f.write(license_text)

    # 3. Add PUBLISH.md
    publish_md = """# Publishing SiliconRoute v1.0 to GitHub

Follow these steps to publish SiliconRoute v1.0 to a clean GitHub repository:

```bash
# 1. Initialize git repository
git init

# 2. Configure your committer identity
git config user.name "Tanmay"
git config user.email "tanmay@example.com"  # Set your public GitHub email

# 3. Stage and commit files
git add .
git commit -m "SiliconRoute v1.0"

# 4. Set default branch to main
git branch -M main

# 5. Add your GitHub remote repository
git remote add origin https://github.com/<your-username>/siliconroute.git

# 6. Push to GitHub
git push -u origin main
```
"""
    with open(RELEASE_DIR / "PUBLISH.md", "w", encoding="utf-8") as f:
        f.write(publish_md)

    # 4. Scan and redact personal data
    redactions = []
    text_extensions = {".py", ".md", ".txt", ".json", ".html", ".js", ".css", ".bat", ".sh", ".yml", ".yaml"}

    path_patterns = [
        (re.compile(r'e:[\\/]THE%20SNAP%20X%20HP', re.IGNORECASE), "."),
        (re.compile(r'e:[\\/]THE SNAP X HP', re.IGNORECASE), "."),
        (re.compile(r'e:\\[^\s\'"<>]+', re.IGNORECASE), lambda m: m.group(0).replace("E:\\THE SNAP X HP\\", "").replace("e:\\THE SNAP X HP\\", "")),
        (re.compile(r'c:[\\/]users[\\/][^\s\'"<>]+', re.IGNORECASE), "[REDACTED_USER_PATH]"),
    ]

    for p in RELEASE_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in text_extensions and p.name not in {"LICENSE", ".gitignore"}:
            continue

        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            continue

        modified = False
        new_lines = []
        for line_num, line in enumerate(content.splitlines(keepends=True), 1):
            original_line = line
            for pat, repl in path_patterns:
                if pat.search(line):
                    if callable(repl):
                        line = pat.sub(repl, line)
                    else:
                        line = pat.sub(repl, line)
                    redactions.append(f"{p.relative_to(RELEASE_DIR)}:{line_num}: Redacted path match '{pat.pattern}'")
                    modified = True

            new_lines.append(line)

        if modified:
            with open(p, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

    redaction_log = LOG_DIR / "redactions.txt"
    with open(redaction_log, "w", encoding="utf-8") as f:
        if redactions:
            f.write("\n".join(redactions) + "\n")
        else:
            f.write("No personal data or absolute paths found requiring redaction.\n")
    print(f"Logged {len(redactions)} redactions to {redaction_log}")

    # 5. Check file sizes (fail if > 50 MB)
    total_size = 0
    file_count = 0
    for p in RELEASE_DIR.rglob("*"):
        if p.is_file():
            file_count += 1
            sz = p.stat().st_size
            total_size += sz
            if sz > 50 * 1024 * 1024:
                raise RuntimeError(f"File exceeds 50 MB limit: {p} ({sz} bytes)")

    size_summary = (
        f"Release Folder: release/siliconroute-v1.0\n"
        f"Total File Count: {file_count}\n"
        f"Total Size Bytes: {total_size} ({total_size / (1024 * 1024):.2f} MB)\n"
        f"Max File Size Limit (50 MB): PASSED\n"
    )
    print(size_summary)
    with open(LOG_DIR / "release_size.txt", "w", encoding="utf-8") as f:
        f.write(size_summary)

    # 6. Run pytest inside the release folder
    print(f"Running pytest inside {RELEASE_DIR} using {sys.executable}...")
    pytest_proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(RELEASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    print(pytest_proc.stdout)
    if pytest_proc.stderr:
        print(pytest_proc.stderr)

    pytest_release_log = LOG_DIR / "pytest_release.txt"
    with open(pytest_release_log, "w", encoding="utf-8") as f:
        f.write(pytest_proc.stdout + "\n" + pytest_proc.stderr)

    print(f"Pytest return code: {pytest_proc.returncode}")
    assert pytest_proc.returncode == 0, f"Pytest failed in release folder! Code: {pytest_proc.returncode}"
    print("Release folder built and verified successfully!")


if __name__ == "__main__":
    build_release()
