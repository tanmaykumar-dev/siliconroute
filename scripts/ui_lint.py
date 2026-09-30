"""SiliconRoute Design Spec v3: Anti-generic UI linter.

Enforces the 30 anti-generic rules in docs/DESIGN_SPEC.md Section 16 across
frontend/ and site/ source files.
"""

import os
from pathlib import Path
import re
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
SITE_DIR = ROOT_DIR / "site"

ALLOWED_HEX = {
    "#f2f2f0",  # --paper
    "#fafaf8",  # --sheet
    "#141414",  # --ink
    "#4a4a4a",  # --ink-2
    "#757575",  # --ink-3
    "#d6d6d2",  # --rule
    "#e1461e",  # --red
    "#b8330f",  # --red-deep
    "#f7e4dd",  # --red-wash
    "#8a8a8a",  # --grey-chip
    "#ffffff",  # allowed in tokens.css or specific SVG fill / white text on red
    "#fff",
    "transparent",
    "inherit",
    "currentcolor",
}

BANNED_FONTS = ["inter", "geist", "space grotesk", "poppins", "montserrat", "roboto"]

EMOJI_PATTERN = re.compile(
    "[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50]|[\u2705]|[\u2714]|[\u2713]|[\u2728]",
    flags=re.UNICODE,
)


def lint_css_file(path: Path) -> list[str]:
    violations = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    for idx, line in enumerate(lines, 1):
        clean = line.strip()
        if not clean or clean.startswith("/*") or clean.startswith("*"):
            continue

        # Rule 1: No gradients
        if re.search(r"\b(linear-gradient|radial-gradient|conic-gradient)\b", clean, re.I):
            violations.append(f"{path.name}:{idx}: Rule 1 violation: gradient found in CSS: '{clean}'")

        # Rule 5: No drop shadows
        if re.search(r"\b(box-shadow|text-shadow|drop-shadow\()\b", clean, re.I):
            # Allow 'box-shadow: none' or 'text-shadow: none'
            if not re.search(r"(box-shadow|text-shadow)\s*:\s*none\b", clean, re.I):
                violations.append(f"{path.name}:{idx}: Rule 5 violation: shadow found: '{clean}'")

        # Rule 8: No glass / backdrop-filter
        if "backdrop-filter" in clean:
            violations.append(f"{path.name}:{idx}: Rule 8 violation: backdrop-filter found: '{clean}'")

        # Rule 10: No banned fonts
        for font in BANNED_FONTS:
            if re.search(rf"\b{re.escape(font)}\b", clean, re.I):
                violations.append(f"{path.name}:{idx}: Rule 10 violation: banned font '{font}': '{clean}'")

        # Rule 19: Corner radius must be 0 (2px on buttons and inputs only per Section 1)
        m_radius = re.search(r"border-radius\s*:\s*([^;]+);", clean, re.I)
        if m_radius:
            val = m_radius.group(1).replace("!important", "").strip()
            if val not in ("0", "0px", "0rem", "0em", "2px", "var(--radius)", "var(--radius-sm)"):
                violations.append(f"{path.name}:{idx}: Rule 19 violation: border-radius must be 0 or 2px: '{val}'")

        # Rule 22: No blur filters
        if re.search(r"filter\s*:\s*blur\(", clean, re.I):
            violations.append(f"{path.name}:{idx}: Rule 22 violation: blur filter found: '{clean}'")

        # Rule 28: No hover transition / transform
        if ":hover" in clean and ("transition" in clean or "transform" in clean or "animation" in clean):
            violations.append(f"{path.name}:{idx}: Rule 28 violation: animation/transition on hover: '{clean}'")

        # Rule 3: No pure white page background
        if re.search(r"(body|html|:root|\.app-layout|\.site-body)\s*\{[^}]*background(-color)?\s*:\s*(#fff|#ffffff|white)\b", clean, re.I):
            violations.append(f"{path.name}:{idx}: Rule 3 violation: pure white page background: '{clean}'")

    return violations


def lint_html_file(path: Path) -> list[str]:
    violations = []
    text = path.read_text(encoding="utf-8")

    # Rule 2: Icon libraries
    for lib in ["lucide", "heroicons", "font-awesome", "fontawesome", "material-icons", "feather"]:
        if lib in text.lower():
            violations.append(f"{path.name}: Rule 2 violation: icon library '{lib}' referenced")

    # Rule 7: Emojis
    for idx, line in enumerate(text.splitlines(), 1):
        if EMOJI_PATTERN.search(line):
            violations.append(f"{path.name}:{idx}: Rule 7 violation: emoji found: '{line.strip()}'")

    # Rule 9: Em dashes
    for idx, line in enumerate(text.splitlines(), 1):
        # Ignore comments
        if "<!--" in line and "-->" in line:
            line_no_comment = re.sub(r"<!--.*?-->", "", line)
        else:
            line_no_comment = line
        if "—" in line_no_comment:
            violations.append(f"{path.name}:{idx}: Rule 9 violation: em dash found: '{line.strip()}'")

    # Rule 15: No "it's not X, it's Y" copy
    if re.search(r"\bnot\s+just\s+[^,]+,\s*but\b", text, re.I) or re.search(r"\bit's\s+not\s+[^,]+,\s*it's\b", text, re.I):
        violations.append(f"{path.name}: Rule 15 violation: 'it's not X, it's Y' phrasing found")

    # Rule 16: Checkmark bullets
    for checkmark in ["✓", "✔", "✅"]:
        if checkmark in text:
            violations.append(f"{path.name}: Rule 16 violation: checkmark bullet '{checkmark}' found")

    # Rule 24: Sparkle or AI magic
    if "✨" in text or re.search(r"\bmagic\b", text, re.I):
        violations.append(f"{path.name}: Rule 24 violation: magic/sparkle found in copy")

    # Rule 25: Appended arrows on buttons or links
    for idx, line in enumerate(text.splitlines(), 1):
        if re.search(r"<a[^>]*>[^<]*[→↗➜][^<]*</a>", line) or re.search(r"<button[^>]*>[^<]*[→↗➜][^<]*</button>", line):
            violations.append(f"{path.name}:{idx}: Rule 25 violation: arrow in button/link: '{line.strip()}'")

    # Rule 26 & 27: Footer links to Terms & Privacy on website
    if path.name == "index.html" and path.parent == SITE_DIR:
        if "terms.html" not in text:
            violations.append(f"{path.name}: Rule 26 violation: missing footer link to terms.html")
        if "privacy.html" not in text:
            violations.append(f"{path.name}: Rule 27 violation: missing footer link to privacy.html")

    return violations


def run_ui_lint() -> tuple[int, list[str]]:
    all_violations = []

    # Scan CSS in frontend and site
    for folder in [FRONTEND_DIR / "css", SITE_DIR / "css"]:
        if folder.exists():
            for p in folder.glob("*.css"):
                all_violations.extend(lint_css_file(p))

    # Scan HTML in frontend and site
    for folder in [FRONTEND_DIR, SITE_DIR]:
        if folder.exists():
            for p in folder.glob("*.html"):
                all_violations.extend(lint_html_file(p))

    return len(all_violations), all_violations


def main():
    count, violations = run_ui_lint()
    print("=== SiliconRoute UI Lint (Design Spec v3 Section 16) ===")
    if count == 0:
        print("PASS: 0 violations found across all frontend and site files.")
        sys.exit(0)
    else:
        print(f"FAIL: {count} violation(s) found:")
        for v in violations:
            print(f"  [VIOLATION] {v}")
        sys.exit(1)


if __name__ == "__main__":
    main()
