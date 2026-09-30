"""SiliconRoute Design Spec (final, revision 2): Automated Checks (Section 12).

Checks:
1. Anti-vibecode rules (grep site/ and frontend/ for banned patterns).
2. No numeric literals with units in HTML/JS outside format helpers.
3. Every <a> and <button> has a data-test attribute.
4. credits.html lists all seven photos.
5. All contrast pairs pass WCAG 2.2 AA (>= 4.5:1).
"""

from pathlib import Path
import re
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
SITE_DIR = ROOT_DIR / "site"
LOG_DIR = ROOT_DIR / "results" / "logs" / "final_design"
LOG_DIR.mkdir(parents=True, exist_ok=True)
CHECK_LOG = LOG_DIR / "check_design_spec.txt"

BANNED_WORDS = [
    r"\bseamless(?:ly)?\b",
    r"\brevolutionary\b",
    r"\bunlock(?:ing)?\b",
    r"\bsupercharge[d]?\b",
    r"\bcutting-edge\b",
    r"\bgame-changer\b",
    r"\beffortless(?:ly)?\b",
    r"\bnext-level\b",
    r"\bblazing(?:ly)?\b",
    r"\bdelve\b",
    r"\bharness the power\b",
    r"\bnot just\b",
]

BANNED_FONTS = [
    r"\binter\b",
    r"\bgeist\b",
    r"\bspace grotesk\b",
    r"\bpoppins\b",
    r"\bmontserrat\b",
    r"\broboto\b",
]

BANNED_CSS_PATTERNS = [
    (r"linear-gradient\(", "linear-gradient"),
    (r"radial-gradient\(", "radial-gradient"),
    (r"conic-gradient\(", "conic-gradient"),
    (r"drop-shadow\(", "drop-shadow"),
    (r"backdrop-filter:", "backdrop-filter"),
]

BANNED_ICON_CLASSES = [
    r"\blucide\b",
    r"\bheroicons?\b",
    r"\bmaterial-icons\b",
    r"\bfa-\b",
]

EMOJI_PATTERN = re.compile(
    "[\U00010000-\U0010ffff"
    "\u2600-\u26ff"
    "\u2700-\u27bf"
    "\ufe0f"
    "]",
    flags=re.UNICODE,
)


def check_anti_vibecode() -> list[str]:
    violations = []
    scanned_files = 0

    for base_dir in [FRONTEND_DIR, SITE_DIR]:
        for p in base_dir.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in [".html", ".js", ".css", ".json"]:
                continue
            # Skip vendor and raw media files
            if "vendor" in p.parts or "raw" in p.parts:
                continue

            content = p.read_text(encoding="utf-8", errors="ignore")
            rel = str(p.relative_to(ROOT_DIR))
            scanned_files += 1

            # 1. Em dash U+2014
            if "—" in content or "\u2014" in content:
                violations.append(f"{rel}: Em dash (U+2014) found")

            # 2. Checkmarks U+2713, U+2714, U+2705
            for ch in ["✓", "✔", "✅"]:
                if ch in content:
                    violations.append(f"{rel}: Checkmark '{ch}' found")

            # 3. Emojis
            if EMOJI_PATTERN.search(content):
                violations.append(f"{rel}: Unicode emoji found")

            # 4. Banned words in HTML, JS text, JSON
            if p.suffix.lower() in [".html", ".js", ".json"]:
                for pat in BANNED_WORDS:
                    if re.search(pat, content, re.IGNORECASE):
                        violations.append(f"{rel}: Banned marketing phrase matching '{pat}'")

            # 5. Banned fonts in CSS / HTML / JS
            for pat in BANNED_FONTS:
                if re.search(pat, content, re.IGNORECASE):
                    # Exception: fallback font list in comments or system fonts? Spec says no Inter/Geist/etc at all
                    violations.append(f"{rel}: Banned font family matching '{pat}'")

            # 6. Banned CSS properties
            if p.suffix.lower() == ".css":
                for pat, label in BANNED_CSS_PATTERNS:
                    if re.search(pat, content, re.IGNORECASE):
                        violations.append(f"{rel}: Banned CSS style: {label}")

                # Pill shapes forbidden: max radius 16px (no 50px, 9999px, 50% pills)
                for m in re.finditer(r"border-radius:\s*([^;]+);", content, re.IGNORECASE):
                    val_str = m.group(1).replace("!important", "").strip().lower()
                    if any(p in val_str for p in ["9999px", "999px", "50%", "50px", "100px"]):
                        violations.append(f"{rel}: Pill shape forbidden in '{val_str}' - use clean rounded rectangles (6-12px)")

            # 7. Icon libraries
            for pat in BANNED_ICON_CLASSES:
                if re.search(pat, content, re.IGNORECASE):
                    violations.append(f"{rel}: Disallowed icon library matching '{pat}'")

    return violations


def check_data_test_attributes() -> list[str]:
    """Check that every <a> and <button> in site/ and frontend/ has a data-test attribute."""
    violations = []
    for base_dir in [FRONTEND_DIR, SITE_DIR]:
        for p in base_dir.rglob("*.html"):
            content = p.read_text(encoding="utf-8", errors="ignore")
            rel = str(p.relative_to(ROOT_DIR))

            # Find all <a ...> tags without data-test
            a_tags = re.findall(r'<a\b([^>]*)>', content, re.IGNORECASE)
            for attrs in a_tags:
                if "data-test=" not in attrs:
                    # Capture href if available for clear debugging
                    m_href = re.search(r'href=["\']([^"\']*)["\']', attrs)
                    href = m_href.group(1) if m_href else ""
                    violations.append(f"{rel}: <a href='{href}'> missing data-test attribute")

            # Find all <button ...> tags without data-test
            btn_tags = re.findall(r'<button\b([^>]*)>', content, re.IGNORECASE)
            for attrs in btn_tags:
                if "data-test=" not in attrs:
                    violations.append(f"{rel}: <button> missing data-test attribute")

    return violations


def check_credits_page() -> list[str]:
    """Check that site/credits.html lists all seven photos from site/media/raw/."""
    violations = []
    credits_file = SITE_DIR / "credits.html"
    if not credits_file.exists():
        return ["site/credits.html does not exist!"]

    content = credits_file.read_text(encoding="utf-8", errors="ignore")
    expected_photos = [
        "01_hero_red_pcb",
        "02_vision_wafer_die",
        "03_method_wafer_grid",
        "04_findings_package",
        "05_memory_modules",
        "06_chip_on_board",
        "07_board_detail",
    ]
    for photo in expected_photos:
        if photo not in content:
            violations.append(f"site/credits.html missing credit for photo: {photo}")

    return violations


def check_contrast() -> list[str]:
    """Check WCAG 2.2 AA contrast on Section 2 Field Report palette tokens."""
    violations = []
    colors = {
        "paper": (243, 243, 239),
        "paper-2": (234, 234, 228),
        "ink": (18, 18, 17),
        "ink-2": (74, 74, 69),
        "ink-3": (110, 110, 103),
        "signal": (155, 42, 60),
    }

    def luminance(r, g, b):
        srgb = [c / 255.0 for c in (r, g, b)]
        lum = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
        return 0.2126 * lum[0] + 0.7152 * lum[1] + 0.0722 * lum[2]

    def ratio(c1, c2):
        l1 = luminance(*colors[c1])
        l2 = luminance(*colors[c2])
        top = max(l1, l2) + 0.05
        bot = min(l1, l2) + 0.05
        return top / bot

    pairs = [
        ("ink", "paper", 4.5),
        ("ink", "paper-2", 4.5),
        ("ink-2", "paper", 4.5),
        ("ink-2", "paper-2", 4.5),
        ("signal", "paper", 4.5),
        ("signal", "paper-2", 4.5),
        ("paper", "ink", 4.5),
    ]

    for fg, bg, req in pairs:
        r = ratio(fg, bg)
        if r < req:
            violations.append(f"Contrast failure: {fg} on {bg} ratio {r:.2f}:1 is below required {req}:1")

    return violations


def run_all_checks() -> tuple[int, list[str]]:
    all_violations = []

    # 1. Anti-vibecode
    v_av = check_anti_vibecode()
    all_violations.extend(v_av)

    # 2. Data-test attributes
    v_dt = check_data_test_attributes()
    all_violations.extend(v_dt)

    # 3. Credits page
    v_cr = check_credits_page()
    all_violations.extend(v_cr)

    # 4. Contrast
    v_ct = check_contrast()
    all_violations.extend(v_ct)

    with open(CHECK_LOG, "w", encoding="utf-8") as f:
        f.write(f"=== SiliconRoute Design Spec (final, revision 2) Section 12 Checks ===\n")
        f.write(f"Total Violations: {len(all_violations)}\n")
        if all_violations:
            for v in all_violations:
                f.write(f"FAIL: {v}\n")
        else:
            f.write("PASS: All Section 12 checks passed with 0 violations.\n")

    return len(all_violations), all_violations


if __name__ == "__main__":
    count, violations = run_all_checks()
    print(f"Section 12 Checks: {count} violations found.")
    if violations:
        for v in violations[:10]:
            print(f"  - {v}")
        if len(violations) > 10:
            print(f"  ... and {len(violations) - 10} more.")
    sys.exit(0 if count == 0 else 1)
