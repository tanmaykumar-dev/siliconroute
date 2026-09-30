# Design (always on)
- docs/DESIGN_SPEC.md is the single source of truth for UI and website design. Follow it exactly.
- Use only the tokens in frontend/css/tokens.css. No new colours, fonts, radii or shadows.
- Every displayed number comes from the API or results/final/manifest.json via the .metric
  component or a labelled live source. Never type measured numbers into HTML/JS/CSS or copy.
- Chip colours and glyphs are fixed: CPU amber square, integrated GPU teal triangle, discrete GPU
  blue circle, NPU violet diamond. Never use colour alone; always show the label.
- Sentence case, no all-caps labels, no eyebrow labels, no trailing arrows on buttons.
- Only one non-user-triggered animation per surface (the routing trace). Respect reduced motion.
- No runtime CDNs or external requests; vendor all assets.
- Visible focus, AA contrast, data-table alternatives for every chart.
