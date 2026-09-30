"""Compute and audit WCAG 2.2 AA contrast ratios for design tokens."""

import math
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_LOG = ROOT_DIR / "results" / "logs" / "design_v2" / "contrast.txt"

DARK_TOKENS = {
    "bench": "#0E1317",
    "plate": "#141A1F",
    "plate_raised": "#1A2229",
    "line": "#27323B",
    "line_strong": "#3A4752",
    "ink": "#E6ECEF",
    "ink_2": "#A3AFB8",
    "ink_3": "#77848E",
    "chip_cpu": "#E59A3A",
    "chip_igpu": "#3CC4AC",
    "chip_dgpu": "#6E9CFF",
    "chip_npu": "#A988F0",
    "ok": "#4CC787",
    "warn": "#E3B341",
    "bad": "#F07167",
    "na": "#6B7780",
}

LIGHT_TOKENS = {
    "bench": "#E9EDF0",
    "plate": "#F7F9FA",
    "plate_raised": "#FFFFFF",
    "line": "#D3DAE0",
    "line_strong": "#B7C1CA",
    "ink": "#172026",
    "ink_2": "#4E5A64",
    "ink_3": "#76828C",
    "chip_cpu": "#B86E12",
    "chip_igpu": "#138472",
    "chip_dgpu": "#2A5FD0",
    "chip_npu": "#7A4BD6",
    "ok": "#1E8A4C",
    "warn": "#A86E00",
    "bad": "#C23B32",
    "na": "#8A949C",
}


def hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    hex_clean = hex_str.lstrip("#")
    r = int(hex_clean[0:2], 16) / 255.0
    g = int(hex_clean[2:4], 16) / 255.0
    b = int(hex_clean[4:6], 16) / 255.0
    return r, g, b


def channel_luminance(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else math.pow((c + 0.055) / 1.055, 2.4)


def relative_luminance(hex_str: str) -> float:
    r, g, b = hex_to_rgb(hex_str)
    return 0.2126 * channel_luminance(r) + 0.7152 * channel_luminance(g) + 0.0722 * channel_luminance(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = relative_luminance(hex1)
    l2 = relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def run_audit():
    OUTPUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("=" * 80)
    lines.append("SILICONROUTE DESIGN v2 — WCAG 2.2 CONTRAST AUDIT")
    lines.append("Criteria: WCAG AA normal text >= 4.5:1, UI components / large text >= 3.0:1")
    lines.append("=" * 80)

    for theme_name, tokens in [("DARK THEME (App Default)", DARK_TOKENS), ("LIGHT THEME (Website Default)", LIGHT_TOKENS)]:
        lines.append(f"\n{theme_name}")
        lines.append("-" * 80)
        lines.append(f"{'Foreground Token':<20} {'Background Token':<20} {'Ratio':<10} {'AA Norm (4.5)':<15} {'AA UI (3.0)':<12}")
        lines.append("-" * 80)

        bg_tokens = ["plate", "bench", "plate_raised"]
        fg_tokens = ["ink", "ink_2", "ink_3", "chip_cpu", "chip_igpu", "chip_dgpu", "chip_npu", "ok", "warn", "bad"]

        for bg in bg_tokens:
            for fg in fg_tokens:
                ratio = contrast_ratio(tokens[fg], tokens[bg])
                pass_norm = "PASS" if ratio >= 4.5 else "FAIL"
                pass_ui = "PASS" if ratio >= 3.0 else "FAIL"
                lines.append(f"--{fg:<18} on --{bg:<17} {ratio:5.2f}:1    {pass_norm:<15} {pass_ui:<12}")

    log_content = "\n".join(lines) + "\n"
    OUTPUT_LOG.write_text(log_content, encoding="utf-8")
    print(f"Audit saved to {OUTPUT_LOG}")
    print(log_content[:1500])


if __name__ == "__main__":
    run_audit()
