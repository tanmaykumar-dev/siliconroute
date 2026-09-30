"""SiliconRoute Design Spec v3: WCAG 2.2 Contrast Ratio Calculator (Section 12).

Calculates exact relative luminance and contrast ratios between text/UI colors
and background surfaces (Paper #F2F2F0, Sheet #FAFAF8, Red #E1461E).
Writes verification table to results/logs/design_v3/contrast.txt.
"""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "results" / "logs" / "design_v3"
LOG_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = LOG_DIR / "contrast.txt"

TOKENS = {
    "paper": "#F2F2F0",
    "sheet": "#FAFAF8",
    "ink": "#141414",
    "ink-2": "#4A4A4A",
    "ink-3": "#757575",
    "rule": "#D6D6D2",
    "red": "#E1461E",
    "red-deep": "#B8330F",
    "red-wash": "#F7E4DD",
    "grey-chip": "#8A8A8A",
    "white": "#FFFFFF",
}


def hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return r, g, b


def channel_luminance(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_str: str) -> float:
    r, g, b = hex_to_rgb(hex_str)
    rl = channel_luminance(r)
    gl = channel_luminance(g)
    bl = channel_luminance(b)
    return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl


def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = relative_luminance(hex1)
    l2 = relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def run_contrast_audit():
    pairs = [
        # (Foreground, Background, Purpose, Required)
        ("ink", "paper", "Body text on paper", 4.5),
        ("ink", "sheet", "Card / table text on sheet", 4.5),
        ("ink-2", "paper", "Secondary text on paper", 4.5),
        ("ink-2", "sheet", "Secondary text on sheet", 4.5),
        ("ink-3", "paper", "Metadata / caption text on paper", 3.0),
        ("ink-3", "sheet", "Metadata / caption text on sheet", 3.0),
        ("white", "red", "Primary button text on red fill", 4.0),
        ("white", "red-deep", "Primary button active text", 4.5),
        ("red", "paper", "Red accent / links on paper", 3.0),
        ("red-deep", "paper", "Deep red tags / headings on paper", 4.5),
        ("red-deep", "red-wash", "Chosen row text on wash", 4.5),
        ("ink", "red-wash", "Table body text on wash", 4.5),
        ("rule", "paper", "1px structural borders on paper", 1.2),
        ("ink", "white", "High-contrast inverted elements", 7.0),
    ]

    lines = []
    lines.append(f"{'Foreground':<12} | {'Background':<12} | {'Ratio':<8} | {'Req':<6} | {'Status':<6} | Role / Usage")
    lines.append("-" * 80)

    all_passed = True
    for fg_name, bg_name, usage, req in pairs:
        fg_hex = TOKENS[fg_name]
        bg_hex = TOKENS[bg_name]
        ratio = contrast_ratio(fg_hex, bg_hex)
        passed = ratio >= req
        if not passed:
            all_passed = False
        status = "PASS" if passed else "FAIL"
        lines.append(f"{f'{fg_name} ({fg_hex})':<12} | {f'{bg_name} ({bg_hex})':<12} | {ratio:>5.2f}:1  | {req:>4.1f}:1 | {status:<6} | {usage}")

    report = "\n".join(lines)
    OUT_FILE.write_text(report, encoding="utf-8")
    print(f"Contrast audit completed. Written to {OUT_FILE}")
    print(f"All pairs meeting criteria: {all_passed}")
    return all_passed


if __name__ == "__main__":
    run_contrast_audit()
