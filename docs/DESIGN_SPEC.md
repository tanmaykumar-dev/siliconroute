# SiliconRoute Design Spec v2 — "Bench"

Place this file at `docs/DESIGN_SPEC.md`. It is the single source of truth for the look,
layout, behaviour and copy of both SiliconRoute surfaces:

1. **The app** — the local dashboard served by FastAPI at `http://127.0.0.1:8000` (`frontend/`).
2. **The website** — a static, public landing page (`site/`) that can be hosted on GitHub Pages.

Read sections 0–4 before touching any file. Build in the phase order of section 15.

---

## 0. Non-negotiable rules (read first)

- **Data integrity beats design.** Never type a measured number into HTML, CSS, JS or copy.
  Every number shown comes from the API or from `results/final/manifest.json`. If a value is
  missing, show the "not available" pill (section 7.9). This applies to the website too.
- **Do not change backend logic, the database, the frozen database, or any measurement code.**
  This is a presentation-layer project. The frozen DB SHA256 must stay
  `98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5`.
- **Local-first, offline-capable.** No runtime CDNs. Vendor Chart.js and fonts into the repo.
- **Plain HTML + CSS + JS modules.** No npm build step, no framework, no second server.
- **Original design.** Do not copy layouts, illustrations or branding from other products.
- Follow AGENTS.md and every rule in `.agents/rules/` (logs only, no pushing, no history rewrite).

---

## 1. Brief

**Product.** SiliconRoute measures every AI-capable chip in a Windows laptop (CPU, integrated
GPU, discrete GPU), learns each chip's behaviour, routes each AI task to the best chip for the
user's goal, explains why, and verifies the choice by measuring.

**Audience.** Hardware and ML engineers (e.g. at chip companies), professors, recruiters, and
technically curious students. They are sceptical and read numbers carefully.

**Primary jobs.**
- App: see live chip state, understand each chip's measured behaviour, ask "which chip should
  run this?", and trust the answer because the evidence is one click away.
- Website: understand the problem and the result in 30 seconds, then verify it in 3 minutes.

**Personality.** A precise lab instrument, not a marketing dashboard. Calm, exact, honest,
quietly confident. The evidence is the hero.

---

## 2. Design principles

1. **Evidence is one click away.** Every number can reveal where it came from (section 9).
2. **Chips have identities.** Each chip keeps one colour and one glyph everywhere (charts,
   tables, pills, the socket strip). Colour is never the only signal: always add the label.
3. **Hierarchy through layout, not decoration.** Primary content sits directly on the page
   with hairline structure; only secondary facts live in tiles. Avoid a wall of identical cards.
4. **One memorable moment per surface.** The routing trace (section 4). Everything else stays
   quiet and disciplined.
5. **Honest states.** Loading, empty, "not available", "hypothesis", and "fitted estimate" are
   first-class visual states, not afterthoughts.
6. **Readable numbers.** Tabular figures, units always shown, right-aligned in tables, consistent
   precision per metric type (section 3.2).

---

## 3. Design tokens

Implement all tokens as CSS custom properties in `frontend/css/tokens.css` and reuse the same
file in `site/`. Two themes: `light` (default for the website) and `dark` (default for the app),
switched with `data-theme` on `<html>`; respect `prefers-color-scheme` on first visit and
remember the user's choice in `localStorage` (key `sr-theme`).

### 3.1 Colour

Neutrals — the "bench" (cool, slightly blue-grey, like anodised aluminium and a scope screen):

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bench` | `#E9EDF0` | `#0E1317` | page background |
| `--plate` | `#F7F9FA` | `#141A1F` | primary panels |
| `--plate-raised` | `#FFFFFF` | `#1A2229` | tiles, popovers, drawers |
| `--line` | `#D3DAE0` | `#27323B` | hairlines, table rules |
| `--line-strong` | `#B7C1CA` | `#3A4752` | focus-adjacent borders, dividers |
| `--ink` | `#172026` | `#E6ECEF` | primary text |
| `--ink-2` | `#4E5A64` | `#A3AFB8` | secondary text |
| `--ink-3` | `#76828C` | `#77848E` | tertiary text, axis labels |

Chip identities (fixed across the whole product; never reuse these for anything else):

| Token | Light | Dark | Chip | Glyph |
|---|---|---|---|---|
| `--chip-cpu` | `#B86E12` | `#E59A3A` | CPU | square |
| `--chip-igpu` | `#138472` | `#3CC4AC` | integrated GPU (Radeon) | triangle |
| `--chip-dgpu` | `#2A5FD0` | `#6E9CFF` | discrete GPU (RTX) | circle |
| `--chip-npu` | `#7A4BD6` | `#A988F0` | NPU (future) | diamond |

State colours:

| Token | Light | Dark | Use |
|---|---|---|---|
| `--ok` | `#1E8A4C` | `#4CC787` | verified, best choice, tests pass |
| `--warn` | `#A86E00` | `#E3B341` | volatile, hypothesis, fitted estimate |
| `--bad` | `#C23B32` | `#F07167` | error, wrong choice, regression |
| `--na` | `#8A949C` | `#6B7780` | "not available" |

Contrast: body text ≥ 4.5:1 on its background in both themes; large text and chart strokes
≥ 3:1. Verify with a script and log the ratios.

### 3.2 Typography

- **Archivo** (variable, OFL) for all UI and headlines. Use its width axis: `wdth 100` for body,
  `wdth 112` for display headlines on the website, `wdth 94` for dense tables.
- **JetBrains Mono** (OFL) only for code, commands, hashes and IDs (run 839, SHA256). Never for
  labels or regular numbers.
- Vendor both as `woff2` in `frontend/fonts/` (and copy to `site/fonts/`), with a
  `system-ui, "Segoe UI", sans-serif` fallback.
- All numbers use `font-variant-numeric: tabular-nums lining-nums`.

Type scale (px / line-height / weight):

| Role | Size | LH | Weight | Notes |
|---|---|---|---|---|
| Display (website hero) | 56 (mobile 38) | 1.05 | 650 | `wdth 112`, tight tracking −1% |
| H1 | 32 | 1.15 | 620 | sentence case |
| H2 | 24 | 1.2 | 600 | |
| H3 | 18 | 1.3 | 600 | |
| Body | 15 | 1.55 | 420 | max line length 72ch |
| Small | 13 | 1.45 | 450 | secondary info |
| Metric (large) | 40 | 1.0 | 600 | tabular |
| Metric (medium) | 24 | 1.1 | 600 | tabular |
| Table | 13.5 | 1.4 | 450 | `wdth 94`, tabular |

Number precision: milliseconds < 1 → 3 decimals; 1–100 ms → 2 decimals; > 100 ms → 1 decimal;
percentages → 1 decimal except regret (2 decimals, as published); ratios → 1 decimal + "×".

Copy rules for type: sentence case everywhere, no all-caps labels, no letter-spaced eyebrow text
above headings, no single highlighted word inside headlines.

### 3.3 Space, shape, depth, motion

- Spacing: 4-pt scale — `4, 8, 12, 16, 24, 32, 48, 64, 96`.
- Radius is hierarchical: controls `6px`, tiles `10px`, panels `14px`, pills `999px`. Tables
  and charts inside panels have no radius of their own.
- Depth: prefer hairlines (`--line`) over shadows. Only popovers, drawers and the modal get a
  shadow: light `0 12px 32px rgba(23,32,38,.14)`, dark `0 12px 32px rgba(0,0,0,.45)`.
- Motion: durations `120ms` (hover/focus), `200ms` (open/close), `600ms` (the routing trace
  only). Easing `cubic-bezier(.2,.7,.2,1)`. With `prefers-reduced-motion: reduce`, disable the
  trace animation and use instant state changes.
- Icons: inline SVG, 20px, 1.5px stroke, `currentColor`. No icon fonts.

---

## 4. Signature element: the socket strip and the routing trace

This is the one memorable thing. Everything else stays quiet.

**Socket strip (app).** A slim horizontal strip at the top of the app, below the top bar, showing
one "socket" per available chip, left to right: CPU, integrated GPU, discrete GPU (NPU when one
exists). Each socket is a 10px-radius tile with a 3px left edge in the chip colour, containing:

- chip glyph + short name ("CPU", "Radeon 610M", "RTX 5070 Laptop") from the device API;
- identity status: "verified" (vendor ID + LUID) or "unverified", as a small pill;
- live values from `/api/telemetry/stream`: load %, power W, temperature °C, clock MHz,
  P-state, each as "not available" when missing;
- a thin sparkline of the last 60 seconds of load.

**Routing trace.** When the router makes a decision (Router screen or Overview "ask" box), draw
an SVG path from the task card to the chosen socket over `600ms`; the chosen socket's edge
brightens and shows "chosen" plus the predicted time; other sockets show their predicted times
dimmed. The trace stays until the next decision. Reduced motion: no animation, just the final
state.

**Website hero version.** A static-first SVG diagram: two task cards ("small model, batch 1" and
"large model, batch 1") routed to different chips, labelled with the measured times from the
manifest (section 10.2). Animate the traces once on load (the page's only non-user motion).

```
 ┌ task: mlp-256, batch 1 ┐                ┌─ CPU ────────── 0.017 ms ─ chosen ┐
 │  small model           │━━━━━━━━━━━━━━━▶│ ■ load 12%  28 W?  not available   │
 └────────────────────────┘                └────────────────────────────────────┘
                                           ┌─ Radeon 610M ───── 0.138 ms ──────┐
                                           └────────────────────────────────────┘
                                           ┌─ RTX 5070 ──────── 0.142 ms ──────┐
                                           └────────────────────────────────────┘
(values above are examples of layout only; real values come from the API/manifest)
```

---

## 5. App shell and layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ SiliconRoute   [plugged in] [battery 100%] [live]              [theme] [help]  │ top bar 56px
├───────────┬──────────────────────────────────────────────────────────────────┤
│ Overview  │ [socket: CPU ] [socket: Radeon 610M ] [socket: RTX 5070 ]         │ socket strip 88px
│ Live      ├──────────────────────────────────────────────────────────────────┤
│ Analysis  │                                                                    │
│ Router    │   page content: 12-column grid, 24px gutters, max width 1440px     │
│ Results   │                                                                    │
│ Evidence  │                                                                    │
│ About     │                                                                    │
│           │                                                                    │
│ v1.0      │                                                                    │
└───────────┴──────────────────────────────────────────────────────────────────┘
 rail 224px (collapses to 64px icon rail below 1180px; labels become tooltips)
```

- Left-aligned content everywhere. Page title (H1) + one-sentence description at the top of
  every screen, then content.
- Breakpoints: ≥1440 (full), 1180–1439 (full, tighter), 960–1179 (icon rail, socket strip
  scrolls horizontally), <960 (show a notice: "SiliconRoute's dashboard is designed for laptop
  screens. Widen the window for the full view." but keep it usable).
- Keyboard: rail items reachable by Tab, arrow keys move within the rail, `g` then a letter
  jumps to a screen (g o, g l, g a, g r, g s, g e), `?` opens the shortcuts sheet.

---

## 6. App screens

Each screen lists purpose, layout, data sources (existing API — do not change its logic; you may
add read-only endpoints that call existing functions or read the manifest), and states.

### 6.1 Overview (new, default screen)

Purpose: the 20-second answer to "is this working and what has it found?"

```
H1 Overview
"SiliconRoute measures every chip in this laptop and routes each AI task to the best one."

[ Ask SiliconRoute: model ▾  batch ▾  workload ▾  goal ▾   (Route task) ]  ← routing trace

Final evaluation (decisions 117–140, previously profiled configurations)
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Best chip     │ Avg slowdown │ Always CPU    │ Always RTX    │  metric tiles (4)
│ 22 of 24      │ 1.75%        │ 113.06%       │ 304.93%       │  (values from manifest)
└──────────────┴──────────────┴──────────────┴──────────────┘
Key findings  (4 short rows, each with its evidence link)
Recent decisions (last 8, from /api/decisions): time, model, batch, workload, chosen chip, result
```
The four tiles are the only tiles on the page; findings and decisions are plain rows.

### 6.2 Live

Purpose: watch each chip right now.
Layout: one full-width chart per chip family (utilisation %, power W, temperature °C, clock/P-state
for the RTX; battery discharge W), sharing a 120-second time axis, stacked vertically so time
aligns. Each chart has a "data table" toggle for accessibility. Unavailable series show the
"not available" pill with the reason (e.g. "Windows does not expose CPU frequency").

### 6.3 Analysis

Purpose: understand each chip's behaviour.
- Scaling chart: latency vs model size (log-log), family and batch selectors, measured points
  (chip glyphs) + fitted curves (dashed). Clicking a point opens the raw-samples modal (7.7).
- Crossover: shown as a labelled vertical marker per chip pair, tagged "fitted estimate" (warn
  colour), with the measured neighbours listed underneath ("measured: CPU faster at width X,
  RTX faster at width Y" from the database).
- Chip models table: form, overhead, compute (effective), DRAM, cache/VRAM, LOO MAPE. Show
  "n/a" where the form has no such term; label compute as "effective".
- Session variability table and wake/cold-start ratios (median, range, n).
- Physics notes (Winograd hypothesis) as "hypothesis" callouts.

### 6.4 Router

Purpose: ask which chip should run a task and see why.
```
[model ▾] [batch ▾] [workload: sustained | idle_loaded | cold_start] [goal ▾] [power budget W]
[ ] Exploration (off by default)            (Route task)   (Route and verify on hardware)

Decision ───────────────────────────────────────────────  (routing trace into socket strip)
 Chosen: RTX 5070 Laptop    Predicted 0.673 ms (measured)     ← example layout only
 Reason: plain-English sentence from the API
 Rules applied: list
Candidates table: chip, predicted ms, source (measured / fitted / measured cold start),
                  wake or cold penalty, score, eligibility (with reason)
```
"Route and verify on hardware" asks for confirmation first: "This runs a short benchmark on all
chips (about 10–30 seconds). Continue?" Show progress, then actual vs predicted and regret.

### 6.5 Results

Purpose: the published evaluation, exactly as in `results/final/`.
- Final evaluation 117–140: overall table (wins k/n, accuracy, mean regret, p90 regret) and the
  per-workload breakdown; note "evaluated on previously profiled configurations".
- Cold-start rule check 141–148 with the note that SiliconRoute matched always-CPU exactly.
- A bar chart of mean regret per strategy (log scale, strategy colours neutral grey except
  SiliconRoute in `--ok`).
- Collapsed "Earlier evaluation (decisions 93–116)".
All values from the manifest via an endpoint; the page must pass the DOM-vs-manifest check.

### 6.6 Evidence (new)

Purpose: let a sceptic verify.
- Frozen database: path, size, SHA256 (JetBrains Mono), manifest date and git commit.
- Metric browser: searchable list of every manifest metric (key, value, unit, description,
  method, SQL where present).
- Raw samples browser: pick model, chip, batch → list of runs → raw samples plot.
- Identity audit: the flagged swapped runs with their evidence.
- "Reproduce on your laptop": the commands from the README with copy buttons.

### 6.7 About

What SiliconRoute is, limitations (from the README), how it was built (AI assistance disclosure),
licence, version.

---

## 7. Component library

Build these once in `frontend/js/components/` and `frontend/css/components.css`.

1. **Button**: primary (filled ink), secondary (outline), quiet (text). Heights 32/40. Labels
   say exactly what happens ("Route task", "Copy command"). No trailing arrows.
2. **Select / segmented control**: segmented for ≤4 options (workload), select otherwise.
3. **Metric tile** (Overview only): label (small, ink-2), value (metric large), comparison line,
   evidence icon. Loading skeleton, "not available" state.
4. **Table**: sticky header, hairline rows, numeric columns right-aligned with tabular figures,
   sortable headers with `aria-sort`, chip cells show glyph + name.
5. **Chip label**: glyph + short name in chip colour; never colour alone.
6. **Pill**: states `ok`, `warn`, `bad`, `na`, `info`; text always present ("verified",
   "hypothesis", "fitted estimate", "volatile", "not available").
7. **Raw-samples modal**: title (model, batch, chip, run ID), stats row (median, p10/p90,
   min–max spread, CV, inner_loop_k), scatter of every sample in sequence, and a text list toggle.
   Focus trap, Esc closes, returns focus.
8. **Evidence popover**: see section 9. Opens on click/Enter, not hover-only.
9. **Not available pill**: grey `--na`, text "not available", tooltip with the reason from the API.
10. **Drawer** (decision details on narrow screens) and **toast** (verbs match the action: "Route
    task" → "Task routed", "Copy command" → "Copied").
11. **Empty state**: says what to do ("No decisions yet. Route a task to see it here." + button).
12. **Error state**: says what happened and how to fix it ("The server stopped responding. Check
    that start.bat is still running, then reload.") — no apologies, no vague text.
13. **Skeletons**: neutral blocks matching the final layout; no shimmer animation.

---

## 8. Charts (Chart.js, vendored)

- Vendor a pinned Chart.js UMD build at `frontend/vendor/chart.umd.min.js` (record the version
  and SHA256 in `docs/DECISIONS.md`). Remove any CDN script tags.
- One shared `frontend/js/charts/theme.js` reading colours from CSS tokens, re-applied on theme
  change.
- Series colours = chip tokens; point styles = chip glyphs (rect, triangle, circle, rectRot).
- Gridlines `--line` at 60% opacity, axis labels `--ink-3`, titles in sentence case with units
  ("Median latency (ms, log scale)").
- Log axes wherever values span more than 1.5 decades; tick labels in plain numbers (no 1e3).
- Tooltips: chip name, value with unit and correct precision, source ("measured, run 839" or
  "fitted"), and "Show raw samples" when applicable.
- Fitted curves dashed; measured points solid. Annotations (crossover marker) via a small local
  plugin, not an external package.
- Every chart has a "Show data table" toggle rendering the same data as an accessible table.

---

## 9. Evidence pattern (the honesty UI)

Every published or computed number is rendered through one component:

```html
<span class="metric" data-metric="decisions_117_140_sr_mean_regret_pct"></span>
```

`frontend/js/metrics.js` fetches `/api/published-metrics` (a new read-only endpoint that returns
`results/final/manifest.json` metrics) and fills each `.metric` with the formatted value + unit.
A small evidence icon next to key numbers opens a popover showing: value, unit, description,
method (`scripts.metrics.<fn>`), SQL if present, and run/decision IDs when the metric has them.
Live values (telemetry, router predictions) show their source label instead ("live", "measured",
"fitted estimate"). A number without a source is a bug.

The website uses the same component, reading `site/data/manifest.json` copied at build time.

---

## 10. Website (`site/`)

A single static page, light theme by default, responsive from 360px to 1600px, left-aligned text
columns (max 72ch) with the hero diagram on the right on wide screens.

### 10.1 Sections (in order)

1. **Hero.** Headline (display, one line on desktop): "Every AI task, on the right chip."
   Sub-line: "SiliconRoute measures the CPU and GPUs in your laptop, routes each AI task to the
   best one, and shows the evidence." Buttons: "View on GitHub", "Run it locally". Right side:
   the routing-trace diagram (section 4) with real manifest values.
2. **The problem.** Three short rows, each a misconception and what the measurements showed:
   "Always use the GPU" (small-model result), "Always use the CPU" (large-model result),
   "The fastest chip is fixed" (cold starts and wake-up change the answer). Values via `.metric`.
3. **How it works.** A true four-step sequence (numbering allowed here): Measure → Learn →
   Decide → Verify, each with one sentence and a tiny inline SVG.
4. **Results.** The final evaluation table (117–140) and the regret bar chart; the note
   "evaluated on previously profiled configurations"; link to the full results file.
5. **Findings.** Four findings from the README, each with its evidence link (run or decision IDs
   rendered via metrics where available). Label hypotheses as hypotheses.
6. **Limitations.** Plainly listed, copied from README section 5 at build time (not retyped).
7. **Reproduce it.** The commands (JetBrains Mono, copy buttons) and the frozen database SHA256.
8. **How it was built.** The disclosure from README section 6 (author, AI assistance, integrity
   protocol), copied at build time.
9. **Footer.** GitHub link, MIT licence, version, "Built by Tanmay".

### 10.2 Build and data

- `scripts/build_site.py`: copies `results/final/manifest.json` to `site/data/manifest.json`,
  copies selected screenshots from `results/screenshots/v1_0/` to `site/img/`, extracts the
  README limitations and "How this was built" sections into `site/data/content.json`, and
  writes `site/data/build.json` (git commit, date, DB SHA256). Deterministic output.
- `site/index.html`, `site/css/` (reusing `tokens.css`), `site/js/` (metrics.js shared logic).
- Meta: title "SiliconRoute — every AI task, on the right chip", description, Open Graph image
  generated as a PNG from the hero diagram (no text-heavy stock images), favicon from the chip
  glyphs.
- No trackers, no analytics, no external requests at runtime (fonts and scripts local).

---

## 11. Voice and microcopy

Plain verbs, sentence case, no filler, no hype words ("revolutionary", "blazing"). Describe what
something does. Numbers only via `.metric`.

| Situation | Copy |
|---|---|
| Route button | Route task |
| Verify button | Route and verify on hardware |
| Verify confirm | This runs a short benchmark on all chips (about 10–30 seconds). Continue? |
| After routing | Task routed to {chip}. |
| Missing sensor | not available — Windows does not expose {metric} for this chip |
| Fitted value | fitted estimate — not a direct measurement |
| Hypothesis | hypothesis — not yet confirmed by a dedicated test |
| Empty decisions | No decisions yet. Route a task to see it here. |
| Server down | The server stopped responding. Check that start.bat is still running, then reload. |
| Evidence link | Show evidence |

---

## 12. Accessibility and quality floor

- WCAG 2.2 AA contrast (log computed ratios for every text/background token pair).
- Visible focus ring: 2px `--chip-dgpu` outline + 2px offset, on every interactive element.
- All charts have data-table alternatives; all icons have labels or `aria-hidden`.
- Modal and popover: focus trap, Esc to close, focus returns to the trigger.
- `prefers-reduced-motion` respected; `prefers-color-scheme` respected on first load.
- No layout shift when data loads (reserve space with skeletons).
- Website Lighthouse-style targets checked with a local script where possible: no console
  errors, images sized, text readable at 200% zoom.

---

## 13. Implementation constraints and file layout

```
frontend/
  index.html
  css/ tokens.css  base.css  layout.css  components.css  screens.css
  js/  app.js  router.js (client routing)  api.js  metrics.js  telemetry.js  theme.js
       components/ *.js    charts/ theme.js  scaling.js  live.js  results.js
       screens/ overview.js live.js analysis.js router.js results.js evidence.js about.js
  vendor/ chart.umd.min.js
  fonts/  archivo-variable.woff2  jetbrains-mono.woff2
site/
  index.html  css/  js/  data/ (generated)  img/ (generated)  fonts/
scripts/build_site.py
```

- Keep existing API routes working; add only read-only endpoints (e.g. `/api/published-metrics`).
- The dashboard must keep passing the existing DOM-vs-manifest verification.

---

## 14. Tests and verification

Extend the test suite (tests must never touch `data/siliconroute.db`):
- `test_no_hardcoded_numbers_frontend_site`: no numeric literals with units in `frontend/**/*.html|js`
  or `site/**/*.html|js` outside the tokens/format helpers.
- `test_site_build_deterministic`: running `build_site.py` twice gives identical output.
- `test_published_metrics_endpoint`: `/api/published-metrics` equals the manifest.
- `test_no_external_requests`: no `http(s)://` script/link/font URLs in `frontend/` or `site/`
  except links (`<a href>`) to GitHub.
- Browser verification script: open every app screen in both themes and the website at 1440×900
  and 390×844; read displayed metric values from the DOM and compare to the manifest; check the
  console for errors; save screenshots.

---

## 15. Build phases (each ends with pytest + logged verification + a NEW commit)

- **D1 Tokens and shell**: tokens.css (both themes), fonts and Chart.js vendored, app shell
  (top bar, rail, socket strip with live data), theme toggle, keyboard navigation.
- **D2 Components**: the full library of section 7, the evidence popover, the `.metric` system
  and `/api/published-metrics`.
- **D3 Screens**: Overview, Live, Analysis, Router (with routing trace), Results, Evidence, About.
- **D4 Website**: `site/` + `scripts/build_site.py` + hero diagram + OG image.
- **D5 Quality**: accessibility checks, contrast log, reduced motion, responsive checks, tests of
  section 14.
- **D6 Proof**: screenshots of every app screen (light and dark, 1440×900) and the website
  (1440×900 and 390×844) into `results/screenshots/v2_design/`; DOM-vs-manifest log; update
  README screenshots only by file (no wording changes to README); rebuild the release folder;
  recreate review_package.zip; final report.

---

## Appendix A — replacement text for `.agents/rules/02-design.md`

```
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
```

## Appendix B — manifest metrics used on Overview and the website

Verify each key exists in `results/final/manifest.json`. If a needed value is missing, add a
computed function to `scripts/metrics.py` and regenerate — never type the number.

- Final evaluation: `decisions_117_140_sr_wins`, `decisions_117_140_total`,
  `decisions_117_140_sr_accuracy_pct`, `decisions_117_140_sr_mean_regret_pct`,
  `decisions_117_140_sr_p90_regret_pct`, `decisions_117_140_always_cpu_mean_regret_pct`,
  `decisions_117_140_always_rtx_mean_regret_pct`, `decisions_117_140_fit_only_mean_regret_pct`
  (plus the matching wins/accuracy keys for each strategy).
- Findings: `mlp_256_b1_cpu_latency_ms`, `mlp_256_b1_rtx_latency_ms`,
  `speedup_cpu_over_rtx_mlp_256_b1`, `mlp_3072_b1_sustained_cpu_ms`,
  `mlp_3072_b1_sustained_rtx_ms`, `speedup_rtx_over_cpu_mlp_3072_b1_sustained`,
  `overhead_rtx_cold_start_vs_sustained_mlp_3072`, `directml_anomaly_conv96_slowdown`,
  `identity_suspect_runs`.
- Cold-start rule: `cold_start_141_148_sr_wins`, `cold_start_141_148_total`,
  `cold_start_141_148_sr_mean_regret_pct`, `cold_start_141_148_always_cpu_mean_regret_pct`.
- Evidence: `total_runs`, `total_decisions`, `predictive_model_mape_pct`,
  `volatility_rtx_max_pct`, `database_size_bytes`.
