# SiliconRoute Design Spec v3: "Red Bench"

Save this file as `docs/DESIGN_SPEC.md` (it replaces v2 completely). It is the single source of
truth for the look, layout, behaviour and copy of both surfaces:

1. **The app**: the local dashboard served by FastAPI at `http://127.0.0.1:8000` (`frontend/`).
2. **The website**: the static public site in `site/` (GitHub Pages ready).

The visual language matches the SiliconRoute pitch deck: signal red, near-black ink, off-white
paper, sharp rectangles, bold type. Read sections 0, 3, 16 and 17 before touching any file.

---

## 0. Non-negotiable rules

1. **Data integrity beats design.** Never type a measured number into HTML, CSS, JS or copy.
   Every number comes from the API or `results/final/manifest.json` (and later the v2 manifest).
   Missing values show the "not available" tag. Example or placeholder numbers are forbidden.
2. **Presentation layer only.** Do not change measurement code, routing logic, fits, databases
   or README wording. The frozen v1.0 DB SHA256 must stay
   `98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5`.
3. **Every control works.** No decorative buttons, no dead links, no `href="#"`, no controls for
   features that do not exist (no "upgrade", no notifications, no avatar, no fake search). If a
   control has no real function, remove it. Enforced by section 17.
4. **Anti-generic checklist is mandatory.** Section 16, enforced by `scripts/ui_lint.py`.
5. **Light theme only**, red and white like the deck. Remove any theme toggle and dark styles.
6. **Local-first.** No runtime CDNs or external requests. Vendor Chart.js and fonts.
7. **Plain HTML + CSS + JS modules.** No framework, no build step, no second server.
8. **Original design.** Do not copy layouts, illustrations or branding from other products.

---

## 1. Brief

**Product.** SiliconRoute measures every AI-capable chip in a Windows laptop (CPU, integrated
GPU, discrete GPU, NPU), learns each chip's behaviour, routes each AI task to the best chip for
the user's goal, explains why, and verifies the choice by measuring.

**Audience.** Hardware and ML engineers (for example at chip companies), competition judges,
professors and recruiters. Sceptical, technical, short on time.

**Jobs.** App: see chip state, understand measured behaviour, ask "which chip should run this?"
and check the evidence. Website: understand the result in 30 seconds, verify it in 3 minutes.

**Personality.** Swiss engineering poster meets lab instrument. Confident, exact, plain-spoken.

---

## 2. Principles

1. **Evidence one click away.** Every number can show where it came from (section 9).
2. **Chips are told apart by shape and label, not colour.** Colour is almost only red and ink.
3. **Type and rules create hierarchy.** Big numbers, bold headings, 1px rules, solid blocks of
   red or ink. No cards floating on shadows, no soft boxes.
4. **Real product, real data.** Screenshots and recordings of the real app, never mock-ups.
5. **Honest states.** Loading, empty, "not available", "hypothesis", "fitted estimate", "not
   measured" are designed states.
6. **Quiet interface.** No decorative motion. Things change state instantly and clearly.

---

## 3. Tokens (`frontend/css/tokens.css`, reused by `site/`)

### 3.1 Colour (single light theme)

| Token | Hex | Use |
|---|---|---|
| `--paper` | `#F2F2F0` | page background (neutral off-white, never pure white) |
| `--sheet` | `#FAFAF8` | panels, tables, modal |
| `--ink` | `#141414` | text, rules, solid ink blocks |
| `--ink-2` | `#4A4A4A` | secondary text |
| `--ink-3` | `#757575` | tertiary text, axis labels |
| `--rule` | `#D6D6D2` | hairlines |
| `--red` | `#E1461E` | brand, primary buttons, chosen chip, key figures |
| `--red-deep` | `#B8330F` | pressed state, red text on paper when contrast needs it |
| `--red-wash` | `#F7E4DD` | background of the chosen row only (functional highlight) |
| `--grey-chip` | `#8A8A8A` | the second accelerator's series |

No other colours. No green, purple, blue, pastel or neon. Success is shown with words
("verified", "best") in ink; errors in `--red-deep` with a clear message.

**Chip encoding (fixed everywhere: tables, charts, sockets, legends):**

| Chip | Mark | Colour |
|---|---|---|
| CPU | filled square | `--ink` |
| Integrated GPU (Radeon 610M / Adreno) | filled triangle | `--grey-chip` |
| Discrete GPU (RTX 5070 Laptop) | filled circle | `--red` |
| NPU (Hexagon) | filled diamond | `--red-deep` |

The mark always appears with the chip's name. Charts also differ by line style (solid/dashed).

Contrast: body text >= 4.5:1, large text and chart lines >= 3:1. Log computed ratios.

### 3.2 Type

- **Archivo** (variable, OFL, vendored woff2) for everything. Width axis: 100 body, 112 display,
  94 dense tables. Weights 400, 600, 800.
- **JetBrains Mono** (OFL, vendored) only for commands, hashes and IDs.
- Banned: Inter, Geist, Space Grotesk, Poppins, Montserrat, Roboto, system-ui as the main face.
- All numbers: `font-variant-numeric: tabular-nums lining-nums`.

| Role | px / line-height / weight |
|---|---|
| Display (website hero) | 72 / 0.98 / 800, `wdth 112` (mobile 44) |
| Figure (big numbers) | 64 / 1.0 / 800 |
| H1 | 36 / 1.1 / 800 |
| H2 | 24 / 1.2 / 700 |
| H3 | 18 / 1.3 / 700 |
| Body | 16 / 1.55 / 400, max 70ch |
| Small | 13 / 1.45 / 400 |
| Table | 14 / 1.4 / 400, `wdth 94` |

Precision: ms < 1 → 3 decimals; 1 to 100 ms → 2; > 100 ms → 1; percentages as published;
ratios 1 decimal + "×".

### 3.3 Space, shape, depth, motion

- Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64, 96, 128.
- **Corner radius: 0 everywhere.** Sharp rectangles like the deck. (Exception: none.)
- **No shadows anywhere.** Separation comes from 1px rules, solid fills and spacing.
- **No gradients, glass, blur, orbs, dot grids or textures.**
- **No hover animations.** Hover may change colour or underline instantly (no transition).
- No decorative motion at all. State changes are instant. The only timed element is the
  progress indicator while a real benchmark runs.
- **Skeleton loaders** for every async region: static blocks in `--rule`, no shimmer.
- Icons: none from icon libraries (no Lucide, Heroicons, Font Awesome). Use words. The only
  graphic marks are the four chip marks and a small set of hand-drawn SVG glyphs where a word
  cannot work (close, copy, external link), 1.5px stroke, square caps.

---

## 4. Signature element: the socket strip

A full-width strip under the top bar with one "socket" per available chip, laid out as columns
separated by 1px rules (not cards). Each socket shows: chip mark + name, identity status
("verified" / "unverified"), and live values from `/api/telemetry/stream` (load %, power W,
temperature °C, clock MHz, sleep state), each "not available" when missing.

When a routing decision is made, the chosen socket becomes a solid `--red` block with white text
showing "chosen" and the predicted time; the others show their predicted times in `--ink-2`.
Instant change, no animation, no arrows. It stays until the next decision.

---

## 5. App shell

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ SiliconRoute                        plugged in | battery 100% | live          │ top bar 56px, ink text on paper
├──────────────────────────────────────────────────────────────────────────────┤
│ ■ CPU          │ ▲ Radeon 610M        │ ● RTX 5070 Laptop                     │ socket strip 96px
├───────────┬──────────────────────────────────────────────────────────────────┤
│ Overview  │ H1 + one sentence                                                │
│ Live      │                                                                  │
│ Analysis  │ content on a 12-column grid, 24px gutters, max width 1440px     │
│ Router    │                                                                  │
│ Results   │                                                                  │
│ Evidence  │                                                                  │
│ About     │                                                                  │
└───────────┴──────────────────────────────────────────────────────────────────┘
 left rail 200px, text only; active item = red 4px underline under the label (not a left stripe)
```

- Left-aligned everything. Rail collapses to a top menu button under 1100px.
- Keyboard: Tab order follows reading order; `g` + letter jumps to screens; `?` opens shortcuts.

---

## 6. App screens

Each screen: H1, one plain sentence, then content. Data only from existing API endpoints or new
read-only endpoints that read existing functions or manifests.

### 6.1 Overview (default)
- A statement block, not tiles: "22 of 24 decisions picked the fastest chip" style sentence built
  from `.metric` values, with "Show evidence". Under it, a compact comparison table of strategies
  (SiliconRoute, always CPU, always GPU, always NPU when measured, fit only): wins, accuracy, mean
  regret, p90 regret.
- "Route a task" form (model, batch, workload, goal) with a primary "Route task" button that
  calls the real router and updates the socket strip.
- Recent decisions table (from `/api/decisions`), empty state when none.
- Findings as a numbered list (they are a real ordered set from the README), each with evidence.

### 6.2 Live
Stacked full-width charts sharing one time axis: utilisation, power, temperature, clock and
sleep state, battery discharge. Each chart: "Show data table" toggle. Unavailable series show
the "not available" tag with the API's reason.

### 6.3 Analysis
Scaling chart (log-log) with family/batch selectors; measured points use chip marks, fitted
curves dashed. Clicking a point opens the raw-samples modal. Crossover markers labelled "fitted
estimate" with the measured neighbours listed. Chip model table ("effective" compute, "n/a"
where a form has no term). Variability and wake/cold ratios with median, range and n.

### 6.4 Router
Form + "Route task" + "Route and verify on hardware" (confirmation dialog first: "This runs a
short benchmark on every chip, about 10 to 30 seconds. Continue?"). Result: chosen chip,
predicted time with source, plain-English reason, rules applied, candidates table (chip,
predicted, source, penalty, score, eligibility with reason). Exploration checkbox off by default.

### 6.5 Results
Published evaluation exactly as `results/final/` (overall + per workload), cold-start rule check,
regret bar chart (log scale; SiliconRoute bar red, others ink/grey), collapsed earlier evaluation.
A "Snapdragon X2 Elite" section that shows the v2 results when they exist, otherwise the empty
state "Snapdragon results not yet recorded".

### 6.6 Evidence
Frozen DB path, size, SHA256; manifest date and commit; searchable metric browser (key, value,
unit, description, method); raw samples browser; identity audit (flagged runs); reproduction
commands in plain code blocks with a working "Copy" button each.

### 6.7 About
What it is, limitations (read from README at build or via API), how it was built (disclosure),
licence, version, links to Privacy and Terms.

---

## 7. Components

1. **Buttons**: primary = solid `--red`, white text; secondary = 1px ink border, ink text;
   text button = underlined ink. Heights 36/44. Pressed = `--red-deep`. Disabled = grey with a
   visible reason next to it. Labels say exactly what happens.
2. **Selects and segmented controls**: sharp, 1px ink border; selected segment = ink fill.
3. **Tables**: the main layout device. Sticky header, 1px rules, numeric columns right-aligned,
   sortable headers with `aria-sort`, chosen/best row uses `--red-wash`.
4. **Tags**: rectangular, 1px border, 12px text: "verified", "hypothesis", "fitted estimate",
   "volatile", "not available", "not measured". No pills, no dots.
5. **Figures**: big number (Figure style) + one-line label under it + evidence link.
6. **Raw-samples modal**: sharp sheet with 1px ink border, stats row, sample plot, text list
   toggle, focus trap, Esc closes, focus returns.
7. **Evidence popover**: opens on click/Enter; shows value, unit, description, method, SQL,
   run/decision IDs.
8. **Toasts**: bottom-left, ink block, white text, verb matches the action ("Copied",
   "Task routed"), 4 seconds, dismissible.
9. **Skeletons**: static `--rule` blocks with the final layout's size.
10. **Empty and error states**: say what happened and what to do, with a working action.

---

## 8. Charts (Chart.js, vendored and pinned)

- Colours only from tokens; series by chip encoding; fitted lines dashed.
- Gridlines `--rule`, axis text `--ink-3`, titles in sentence case with units.
- Log axes when values span more than 1.5 decades; plain tick labels.
- Tooltips: chip name, value with unit, source ("measured, run 839" / "fitted").
- No area fills, no gradients, no animation (`animation: false`).
- Every chart has a working "Show data table" toggle.

---

## 9. Evidence pattern

Every published number renders through
`<span class="metric" data-metric="<manifest key>"></span>`, filled by `frontend/js/metrics.js`
from `/api/published-metrics` (read-only endpoint returning the manifest metrics). Key numbers
carry "Show evidence", which opens the popover. Live values show their source ("live",
"measured", "fitted estimate"). The website uses the same component with
`site/data/manifest.json` generated at build time. A number without a source is a bug.

---

## 10. Website (`site/`)

Pages: `index.html`, `privacy.html`, `terms.html`. Light theme, responsive from 360px.

### 10.1 Home, in order
1. **Hero**: left, display headline "Every AI task, on the right chip." and one sentence:
   "SiliconRoute measures the processors in your laptop, sends each AI task to the fastest one
   and shows the evidence." Buttons: "View the code" (GitHub) and "Run it on your laptop"
   (jumps to the reproduce section). Right: a **real screenshot of the app** (Router screen with
   a real decision) from `results/screenshots/`, with a caption naming the date and hardware.
2. **Real demo**: the recorded walkthrough video from `results/demo/` (with captions track),
   poster frame = real screenshot, working play/pause controls (native `<video controls>`).
3. **The problem**: a numbered list of three measured facts, each as one row: big figure on the
   left (via `.metric`), one sentence on the right. Rows separated by 1px rules. Not cards.
4. **How it works**: a numbered sequence (Measure, Learn, Decide, Verify) as rows with one
   sentence each.
5. **Results**: the evaluation table and the regret chart, with the note "evaluated on previously
   profiled configurations"; link to the results folder on GitHub.
6. **Findings**: numbered list with evidence links; hypotheses tagged "hypothesis".
7. **Snapdragon X2 Elite**: what is being measured next; results appear only when recorded;
   otherwise "Snapdragon results not yet recorded".
8. **Limitations**: copied from README section 5 at build time.
9. **Reproduce it**: commands in plain code blocks (no fake terminal window), each with "Copy".
10. **How it was built**: README section 6 copied at build time.
11. **Footer**: GitHub, Privacy, Terms, MIT licence, version, "Built by Tanmay".

### 10.2 Privacy and Terms (real, short)
- `privacy.html`: the app runs locally and sends no data anywhere; the website has no analytics,
  cookies or trackers and makes no external requests; contact via GitHub issues.
- `terms.html`: MIT licence summary, provided "as is" without warranty, benchmark results are
  specific to the listed hardware and conditions, links to LICENSE.

### 10.3 Build
`scripts/build_site.py` copies the manifest(s), selected real screenshots, the demo video and
README sections into `site/data`, `site/img`, `site/media`; writes `site/data/build.json` (commit,
date, DB SHA256); deterministic. Meta title "SiliconRoute: every AI task on the right chip",
description, Open Graph image = a real app screenshot crop.

---

## 11. Voice and microcopy

- Plain verbs, sentence case, short sentences.
- **No em dashes** in any UI or website copy. Use commas, colons or full stops.
- No "it's not X, it's Y" or "not just X, but Y" constructions.
- No hype ("revolutionary", "blazing", "seamless", "supercharge", "unlock", "effortless").
- No emojis, no sparkles, no exclamation marks.

| Situation | Copy |
|---|---|
| Route button | Route task |
| Verify button | Route and verify on hardware |
| Verify confirm | This runs a short benchmark on every chip, about 10 to 30 seconds. Continue? |
| After routing | Task routed to {chip}. |
| Missing sensor | not available: Windows does not expose {metric} for this chip |
| Fitted value | fitted estimate, not a direct measurement |
| Hypothesis | hypothesis, not yet confirmed by a dedicated test |
| Not measured | not measured on this device |
| Empty decisions | No decisions yet. Route a task to see it here. |
| Server down | The server stopped responding. Check that start.bat is running, then reload. |
| Evidence link | Show evidence |

---

## 12. Accessibility

WCAG 2.2 AA contrast; visible focus (2px ink outline, 2px offset) on every control; data-table
alternative for every chart; labelled form controls; modal focus trap; keyboard access to every
function; text readable at 200% zoom; `prefers-reduced-motion` irrelevant because there is no
decorative motion, but keep it respected.

---

## 13. File layout

```
frontend/  index.html  css/{tokens,base,layout,components,screens}.css
           js/{app,nav,api,metrics,telemetry}.js  js/components/*  js/charts/*  js/screens/*
           vendor/chart.umd.min.js   fonts/{archivo,jetbrains-mono}.woff2
site/      index.html  privacy.html  terms.html  css/  js/  data/  img/  media/  fonts/
scripts/   build_site.py  ui_lint.py  control_audit.py
```

---

## 14. Tests (never touch `data/siliconroute.db`)

- `test_ui_lint`: runs `scripts/ui_lint.py` over `frontend/` and `site/`; zero violations.
- `test_control_audit`: runs `scripts/control_audit.py` (Playwright) against the app and the
  built site; every control passes (section 17).
- `test_no_hardcoded_numbers_frontend_site`: no numeric literals with units in HTML/JS copy.
- `test_no_external_requests`: no external script/style/font/image URLs (links to GitHub allowed).
- `test_published_metrics_endpoint`: endpoint equals manifest.
- DOM-vs-manifest check on Overview, Results and the website.

---

## 15. Build phases (each: pytest logged, lint + audit logged, screenshots, NEW commit)

- **R1 Tokens, fonts, shell, socket strip** (remove dark theme and old styles).
- **R2 Components + evidence system + ui_lint.py + control_audit.py.**
- **R3 App screens** (all seven).
- **R4 Website + Privacy + Terms + build_site.py.**
- **R5 Proof**: screenshots of every app screen (1440×900) and the website (1440×900 and
  390×844) into `results/screenshots/v3_design/`; lint log; control audit log; contrast log;
  DOM-vs-manifest log; rebuild release folder; recreate review_package.zip; final report.

---

## 16. Anti-generic checklist (enforced by `scripts/ui_lint.py`)

Each rule below must be checked automatically where possible (pattern in brackets) and
manually confirmed in the final report.

1. No gradients of any kind [`linear-gradient`, `radial-gradient`, `conic-gradient`].
2. No icon libraries [`lucide`, `heroicons`, `feather`, `font-awesome`, `material-icons`].
3. No pure white page background [`#fff`, `#ffffff`, `white` as body/page background].
4. No rainbow or multi-hue palettes: only the tokens in 3.1 [any hex not in tokens.css].
5. No drop shadows [`box-shadow` other than `none`; `drop-shadow(`; `text-shadow`].
6. No rows of three identical feature cards; use lists and tables.
7. No emojis [Unicode emoji ranges, including in alt text and titles].
8. No glass effects [`backdrop-filter`, translucent panels over content].
9. No em dashes in visible copy [`—` in HTML text, JS strings, generated content].
10. No Inter, Geist, Space Grotesk (or Poppins, Montserrat, Roboto) [font-family values].
11. No colored left stripes on boxes [`border-left` wider than 1px or coloured].
12. No testimonials or quotes from people.
13. No bento grids (mosaics of mixed-size cards).
14. No fake terminal windows (window chrome, traffic-light dots) around code.
15. No "it's not X, it's Y" / "not just X, but Y" copy [regex on text].
16. No checkmark bullets [`✓`, `✔`, `✅`, check SVGs used as list markers].
17. No pricing tiers or pricing sections.
18. Real product demo required: real screenshots and the real recording (checked by build).
19. No soft corner radius [`border-radius` other than `0`].
20. No purple, and no purple-and-black scheme [hues 250 to 320 degrees].
21. Skeleton loaders present for every async region (checked by control audit).
22. No radial orbs, glows or blurred blobs [`filter: blur`, large circular decorative elements].
23. No dot-grid or grid-paper backgrounds [`background-image` patterns].
24. No sparkle or "AI magic" icons [`✨`, sparkle SVGs, the word "magic"].
25. No animated arrows; no arrows appended to button or link text [`→`, `↗`, `➜` in labels].
26. Terms page exists and is linked in the footer.
27. Privacy page exists and is linked in the footer.
28. No hover animations [`transition` or `animation` inside `:hover` rules; no transforms on hover].
29. No neon colours [high-saturation, high-lightness hex values outside the tokens].
30. No pastel palettes [light, low-saturation hues outside `--red-wash`].

---

## 17. Every control works (enforced by `scripts/control_audit.py`)

The audit opens every app screen and every website page in a real browser and, for every
button, link, select, checkbox, segmented control, tab and chart toggle:

- **Links**: target exists (internal route or file resolves with HTTP 200; external links only
  to github.com). No `href="#"`, no `javascript:void(0)`, no empty `href`.
- **Buttons and toggles**: activating them produces an observable result: navigation, a DOM
  change, a dialog, a copied value (clipboard read back), a download, or a request to a real API
  endpoint that returns 2xx. The audit records which.
- **Forms**: submitting with valid values calls the real endpoint; invalid values show a message.
- **Exception**: "Route and verify on hardware" is audited only up to its confirmation dialog
  (Cancel must close it); it is never confirmed during audits.
- Any control that cannot pass is **removed**, not hidden. The audit writes a table (screen,
  control label, type, result, evidence) to `results/logs/design_v3/control_audit.txt`.

---

## Appendix A: replacement text for `.agents/rules/02-design.md`

```
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
```

## Appendix B: manifest metrics used on Overview and the website

Verify each key exists in `results/final/manifest.json`; if a needed value is missing, add a
computed function to `scripts/metrics.py` and regenerate. Never type the number.

- Evaluation: `decisions_117_140_sr_wins`, `decisions_117_140_total`,
  `decisions_117_140_sr_accuracy_pct`, `decisions_117_140_sr_mean_regret_pct`,
  `decisions_117_140_sr_p90_regret_pct`, `decisions_117_140_always_cpu_mean_regret_pct`,
  `decisions_117_140_always_rtx_mean_regret_pct`, `decisions_117_140_fit_only_mean_regret_pct`,
  and the matching wins/accuracy keys for each strategy.
- Findings: `mlp_256_b1_cpu_latency_ms`, `mlp_256_b1_rtx_latency_ms`,
  `speedup_cpu_over_rtx_mlp_256_b1`, `mlp_3072_b1_sustained_cpu_ms`,
  `mlp_3072_b1_sustained_rtx_ms`, `speedup_rtx_over_cpu_mlp_3072_b1_sustained`,
  `overhead_rtx_cold_start_vs_sustained_mlp_3072`, `directml_anomaly_conv96_slowdown`,
  `identity_suspect_runs`.
- Cold-start rule: `cold_start_141_148_sr_wins`, `cold_start_141_148_total`,
  `cold_start_141_148_sr_mean_regret_pct`, `cold_start_141_148_always_cpu_mean_regret_pct`.
- Evidence: `total_runs`, `total_decisions`, `predictive_model_mape_pct`,
  `volatility_rtx_max_pct`, `database_size_bytes`.
