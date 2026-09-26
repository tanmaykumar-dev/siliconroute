# Dashboard design (overrides default "premium" styling)

- Clean, dark, information-first dashboard. Readability beats decoration.
- No glassmorphism, no blur, no gradient text, no heavy animations, no
  decorative stripes. Subtle 150 ms transitions at most.
- Colours: background #0E1116, cards #1A1F29, borders #232A37,
  accent copper #D98A3D, efficient/ok mint #3CCFA0, text #EDEFF3,
  muted #9AA3B2, warning #F5C542, error #F26D6D. Contrast ≥ 4.5:1.
- Numbers in a monospace font, right-aligned in tables, always with units.
- "not available" = small grey pill with a tooltip explaining why.
- Charts: Chart.js 4, one colour per device, consistent across all charts
  (CPU copper, GPU0 mint, GPU1 #6EA8FE, NPU #C77DFF). Log axes where sizes vary.
- Layout: top bar (name + status chips), left tab list, content area;
  works at 1280x720 and on a 1920x1080 laptop screen.
