# Design (always on)
- docs/DESIGN_SPEC.md (v3, "Red Bench") is the single source of truth for app and website design.
- Only tokens from frontend/css/tokens.css. Light theme only. Radius 0. No shadows, gradients,
  glass, orbs, dot grids, emojis, icon libraries, hover animations or decorative motion.
- Chips are identified by mark + name: CPU ink square, integrated GPU grey triangle, discrete GPU
  red circle, NPU deep-red diamond.
- Every number comes from the API or a manifest via .metric; never type measured numbers.
- Every control must work; remove anything without a real function.
- Copy: sentence case, no em dashes, no "it's not X, it's Y", no hype, no emojis.
- scripts/ui_lint.py and scripts/control_audit.py must pass before any commit.
