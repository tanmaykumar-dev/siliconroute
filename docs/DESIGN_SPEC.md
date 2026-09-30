# SiliconRoute Design Spec (final, revision 2): "Field Report"

Save as `docs/DESIGN_SPEC.md`, replacing every earlier version. Single source of truth for the
website (`site/`) and the dashboard app (`frontend/`). Where an earlier spec disagrees, this file
wins; remove elements that only existed in earlier versions.

The idea: a finished, calm, editorial website that tells SiliconRoute's story as you scroll, opening
on a full-bleed red circuit-board photograph. Large confident type, lots of space, real figures with
captions, and footnotes that point at the exact measurement behind every number. The live telemetry
dashboard is a separate tab. Everything on screen is either information or a control that works.

---

## 0. Hard rules

1. Data integrity: never type a measured number into HTML, CSS, JS or copy. Numbers come from the
   API or `results/final/manifest.json` (website: `site/data/manifest.json`) through the `.metric`
   component. Missing value: "not published". Snapdragon values: "not yet measured".
2. Do not change measurement code, routing logic, fits, databases or README wording. The only
   backend change allowed is static routing (section 6). Frozen DB SHA256 must stay
   `98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5`.
3. Local-first: no runtime CDNs, no analytics, no cookies, no third-party requests.
4. Every button and link does something real (section 10). No placeholder or dead controls.
5. Original design. Do not copy the layout, imagery or branding of any existing website.
6. Photos: only the seven in `site/media/raw/` (from `media.json`), plus real screenshots and the
   real screen recording. Never generate, download or add other images. The seven photos are
   atmosphere only: never caption them as SiliconRoute hardware or the test laptop. Every photo is
   credited on `credits.html` exactly as in `CREDITS.md`.

---

## 1. The anti-vibecode list (enforced by tests, section 12)

| # | Never | Do instead |
|---|---|---|
| 1 | Gradients of any kind | Flat colour |
| 2 | Icon libraries (Lucide, Heroicons, etc.) | Words. Only icons allowed: menu, close, external-link, hand-drawn 1.5px inline SVG |
| 3 | Pure white `#FFFFFF` backgrounds | Paper `#F3F3EF` |
| 4 | Rainbow colouring | Ink, paper, signal red; chip colours only to identify chips |
| 5 | Drop shadows | 1px hairline rules |
| 6 | Three feature cards in a row | Stacked rows with hairlines, or numbered paragraphs with figures |
| 7 | Emojis | Words |
| 8 | Glass, blur, translucent overlays on photos | Solid panels placed next to or over photos |
| 9 | Em dashes in any copy | Colons, commas, full stops |
| 10 | Inter, Geist, Space Grotesk | IBM Plex Sans + IBM Plex Mono |
| 11 | Coloured left stripes on boxes | A small chip-colour square next to the chip name |
| 12 | Testimonials | Evidence footnotes |
| 13 | Bento grids | A 12-column editorial grid |
| 14 | Fake terminal windows | Plain code blocks with a "Copy" text button |
| 15 | "It's not X, it's Y" phrasing, hype words | Plain statements of fact |
| 16 | Checkmark bullets | Plain text or numbered lists |
| 17 | Pricing tiers | Nothing |
| 18 | No real product demo | The interactive decision figure, real screenshots, the real recording |
| 19 | Soft rounded corners | Radius 0; 2px on inputs and buttons only |
| 20 | Purple and black | Ink, paper and signal red |
| 21 | Blank screens while loading | Skeleton blocks in the final layout shape (dashboard) |
| 22 | Radial orbs, glows | Nothing |
| 23 | Dot grids | Nothing |
| 24 | Sparkle icons | Nothing |
| 25 | Animated arrows | Plain underlined text links |
| 26 | No terms | `site/terms.html` |
| 27 | No privacy policy | `site/privacy.html` |
| 28 | Hover animations | Colour or underline change only, instant |
| 29 | Neon colours | Printed-ink colours |
| 30 | Basic pastel colours | Ink, paper, signal red, chip colours |

Banned words in copy: "seamless", "revolutionary", "unlock", "supercharge", "cutting-edge",
"game-changer", "effortless", "next-level", "blazing", "delve", "harness the power", "not just".

---

## 2. Tokens (`frontend/css/tokens.css`, shared with `site/`)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--paper` | `#F3F3EF` | `#141413` | page |
| `--paper-2` | `#EAEAE4` | `#1C1C1A` | quiet fills, table headers, skeletons, code |
| `--ink` | `#121211` | `#EDEDE8` | text, primary buttons, dark sections |
| `--ink-2` | `#4A4A45` | `#B4B4AC` | secondary text |
| `--ink-3` | `#6E6E67` | `#8C8C84` | captions, axis labels |
| `--rule` | `#D6D6CE` | `#2E2E2B` | hairlines |
| `--signal` | `#9B2A3C` | `#E0707F` | sampled from the hero photo: link hover, selected states, focus accents, section numbers |
| `--cpu` | `#9C5A06` | `#D99A45` | CPU (ochre) |
| `--igpu` | `#0E6B60` | `#4FB3A4` | integrated GPU (teal) |
| `--dgpu` | `#23459F` | `#7F9CF0` | discrete GPU (cobalt) |
| `--npu` | `#5B6B12` | `#A9BC4C` | NPU (olive) |

Website: light theme only, with dark sections using `--ink` background and `--paper` text.
Dashboard: light and dark with a working toggle.

Type: IBM Plex Sans (400, 500, 600) and IBM Plex Mono (400, 500), vendored woff2. Mono only for
data values, IDs, hashes, commands, email address. Tabular numbers everywhere.

| Role | Desktop | Mobile | Weight | Leading |
|---|---|---|---|---|
| Display | 88px | 44px | 500 | 0.98, tracking -2% |
| Statement (vision, contact) | 56px | 32px | 400 | 1.08 |
| H2 | 40px | 30px | 500 | 1.1 |
| H3 | 22px | 20px | 600 | 1.25 |
| Body | 17px | 16px | 400 | 1.6, max 68ch |
| Small | 14px | 14px | 400 | 1.5 |
| Caption | 13px | 13px | 400 | 1.45, `--ink-3` |
| Big measured number | 120px | 64px | 500 | 0.9 |

Sentence case. No all-caps labels, no letter-spaced eyebrows. Section numbers ("01") in
`--signal`, same size as the H2, set before the title.

Space: 8px base. Sections separated by 160px (desktop) / 96px (mobile). Radius 0 (2px on buttons
and inputs). No shadows. Motion: smooth anchor scrolling only (off under reduced motion);
dashboard modal and menu fade 150ms. Focus: 2px solid `--ink` outline, 3px offset (`--paper` on
dark sections).

Grid: 12 columns, 24px gutters, max 1320px, outer margins 48px desktop, 20px mobile. Text starts
at column 1 and spans 6 to 7 columns; figures and photos take columns 7 to 12 or run full-bleed.

---

## 3. Photographs (`site/media/raw/`, described in `media.json`)

| File | Role | Where |
|---|---|---|
| `01_hero_red_pcb.jpg` | hero | Section 00, full-bleed, full viewport height |
| `02_vision_wafer_die.jpg` | vision | Section 01, columns 8 to 12, portrait |
| `06_chip_on_board.jpg` | problem | Section 02, full-bleed strip, 55vh, above the dark problem rows |
| `03_method_wafer_grid.jpg` | method opener | Section 04, full-bleed strip, 60vh |
| `04_findings_package.jpg` | findings opener | Section 06, full-bleed strip, 60vh |
| `05_memory_modules.jpg` | cache finding | Section 06, beside the CPU-cache finding |
| `07_board_detail.jpg` | contact | Section 11, full-bleed behind the contact panel |

Rules: `object-fit: cover` with a sensible `object-position` per photo; no filters, no tints, no
overlays. Text never sits directly on a photo: it sits on a solid `--paper` or `--ink` panel that
overlaps the photo edge. `scripts/build_media.py` makes AVIF, WebP and JPEG at 640, 1280, 2000 and
2800px, writes `width`/`height`, preloads the hero, lazy-loads the rest. Alt text comes from
`media.json`.

---

## 4. Components

1. Button, primary: `--ink` fill, `--paper` text (inverse on dark sections), 2px radius, 48px tall.
2. Button, text: underlined label; hover turns `--signal`.
3. Segmented control: text buttons separated by 1px rules; selected = ink with paper text.
   Arrow keys move, `aria-pressed`.
4. Figure: content, then caption "Figure N." plus one sentence, then an evidence footnote
   (session, run or decision IDs) and a "Show data" text button revealing the same data as a table.
5. Table: hairline rows, header on `--paper-2`, numbers right-aligned mono, chip names with a 10px
   chip-colour square.
6. Metric: `<span class="metric" data-metric="key">`, formatted from the manifest, with a
   superscript footnote marker linking to the section's evidence list.
7. Code block: `--paper-2`, mono 14px, "Copy" text button; "Copied" for 2 seconds, or "Copy
   failed, select the text".
8. Menu overlay (below 960px): full-screen `--paper`, H2-size links, "Close", Esc, focus trap.
9. Skeleton (dashboard): `--paper-2` blocks in the content's shape, no shimmer.

---

## 5. Website: one long scrolling page (`site/index.html`)

Header: a solid `--paper` bar with a 1px bottom rule, sticky. Left: "SiliconRoute" (links to top).
Right: "Vision", "How it works", "Results", "Snapdragon", "Dashboard", "Contact", and "GitHub"
(external). Below 960px: "Menu".

- **00 Hero.** The red circuit-board photo fills the viewport under the header. A solid `--paper`
  panel (columns 1 to 6) overlaps the photo's bottom-left edge and holds: display line "Every AI
  task, on the right chip." and one sentence: "SiliconRoute measures every processor in a laptop
  and sends each AI task to the one that serves it best." Actions: primary "How it works" (scrolls
  to 03) and text button "View on GitHub". Nothing else on the first screen.
- **01 Vision.** Paper. Statement (56px): "Laptops now carry several kinds of processors. Software
  should use the right one for each task, and prove it." Then three numbered principles as short
  paragraphs: 1 Measure the real hardware. 2 Explain every decision. 3 Publish the evidence.
  Wafer portrait photo on the right.
- **02 The problem.** Photo strip (chip on board), then a dark `--ink` section with three stacked
  rows separated by rules. Each row: a big measured number (metric) on the left, one sentence on
  the right: CPU faster on a small model, RTX faster on a large model, cold GPU start slower than
  warm. Caption with the test laptop and evidence footnotes.
- **03 The decision.** Paper. The interactive figure: segmented control "Small model", "Large
  model", "Cold start"; one horizontal bar per chip on a log time axis from manifest values; the
  chosen chip labelled "chosen"; one generated sentence explaining the choice; caption; "Show data".
  Missing values show "not published" (add computed metrics in `scripts/metrics.py`, never typed).
- **04 How it works.** Photo strip (wafer grid), then four numbered steps (Measure, Learn, Decide,
  Verify) as paragraphs on the left, each with a small real figure on the right.
- **05 Results.** Dark section. Big measured statement "22 of 24" via metrics, one sentence, the
  strategy table (wins, accuracy, mean regret, p90, max regret), a mean-regret bar figure, and the
  caption "Evaluated on previously profiled configurations, one laptop."
- **06 Findings.** Photo strip (processor package), then four numbered findings, each a paragraph,
  a real figure and an evidence footnote. The CPU-cache finding sits beside the memory photo.
  Hypotheses are labelled "Hypothesis:".
- **07 Snapdragon X2 Elite.** `--paper-2` band. A status line from
  `site/data/snapdragon_status.json` ("In progress" until results exist) and what is being
  measured. When `site/data/manifest_v2.json` exists, the section-03 figure appears here with
  Snapdragon data. Never example numbers.
- **08 Dashboard.** Paper. One sentence: "The live dashboard shows telemetry, the chip models and
  the router, and runs on your own laptop." The real screen recording (poster frame, plays on click,
  no autoplay) and two real screenshots. Button "Open the dashboard" (behaviour in section 6).
- **09 Reproduce.** Numbered steps with code blocks (clone, start, reproduce, test), the frozen DB
  SHA256 with "Copy", link to the repository.
- **10 How this was built.** Author, AI assistance disclosure and integrity protocol, copied from
  README section 6 at build time.
- **11 Contact.** The board-detail photo full-bleed with a solid `--ink` panel over its left half:
  statement "Questions, feedback or hardware to test on? Write to me." Email address in mono with
  two controls: "Send email" (`mailto:`) and "Copy". GitHub profile and repository links. Values
  from `site/data/contact.json`: email `tanmayjha54321@gmail.com`, GitHub profile
  `https://github.com/tanmaykumar-dev`, repository `https://github.com/tanmaykumar-dev/siliconroute`.
- **Footer.** "SiliconRoute", version, build date and commit (`site/data/build.json`); links:
  Privacy, Terms, Credits, Licence (MIT), GitHub. One line: "Not affiliated with Qualcomm, AMD or
  NVIDIA. Product names are trademarks of their owners."

Extra pages (same header and footer, plain text): `privacy.html` (no cookies, no analytics, no
third-party requests; the app stores measurements only on the user's machine; contact email),
`terms.html` (MIT licence, no warranty, results describe one test laptop, no vendor affiliation),
`credits.html` (every photo credit from `CREDITS.md`, fonts, Chart.js), `dashboard.html` (section 6),
`404.html` (one sentence and a link home).

Meta: title "SiliconRoute: every AI task, on the right chip", description, Open Graph image made
from a crop of the hero photo with the wordmark on a solid panel, favicon (a small solid
`--signal` square with an ink "S").

---

## 6. The dashboard is a separate tab

- When run locally (`start.bat`), FastAPI serves the website at `/` and the dashboard at `/app`.
  Only static file routing changes; all API routes stay as they are.
- "Dashboard" in the header and "Open the dashboard" in section 08 run one check: a request to
  `/api/system` with an 800ms timeout. If it answers, open `/app` in a new tab. If not (the
  website on GitHub Pages), go to `dashboard.html`, which explains in two steps how to run it
  locally, shows the recording and screenshots, and links to the README quick start.
- The dashboard (`frontend/`): text-only left navigation: Overview, Live telemetry, Analysis,
  Router, Results, Evidence, About; a working Light/Dark toggle; a "Back to website" link. All
  existing functions kept and restyled with these tokens, no icons, no shadows, no rounded panels,
  skeleton loading. Router keeps "Route task" and "Route and verify on hardware" (confirmation
  dialog). Add "Export decisions CSV" (downloads from the API).

---

## 7. Charts

Chart.js vendored. Flat token colours, 1.5px lines, no area fills, no gradients. Axis labels
`--ink-3` 12px, gridlines `--rule`, sentence-case titles with units. Log axes when values span more
than 1.5 decades, plain tick labels. Every chart has "Show data". Tooltips: `--paper` box, 1px
`--rule` border, no shadow.

## 8. Copy rules

Short sentences. Facts before claims. Every number through `.metric`. No em dashes, no
exclamation marks, no rhetorical questions, no "not X, it's Y", no banned words. Buttons say what
happens: "How it works", "View on GitHub", "Show data", "Copy", "Send email", "Open the dashboard".

## 9. Performance and finish

Hero image preloaded and under 400 KB at 1280px (AVIF/WebP). Total first load under 1.2 MB
excluding the video. No layout shift. Works without JavaScript for reading (figures show their
data tables). Keyboard reachable end to end. Print stylesheet hides navigation and photos.

---

## 10. Interaction inventory (every control is listed here and tested)

| Surface | Control | Real function | Test asserts |
|---|---|---|---|
| Site | "SiliconRoute" | Scroll to top | scrollY is 0 |
| Site | Vision / How it works / Results / Snapdragon / Contact | Scroll to section, set hash | section in view, hash set |
| Site | Dashboard (header) and Open the dashboard | Local: open `/app` in new tab. Pages: go to `dashboard.html` | correct target in both modes (mock the API) |
| Site | GitHub, View on GitHub | Open repository in new tab | href is repo URL, `rel=noopener` |
| Site | Menu / Close | Open and close overlay, Esc, focus trap | visible/hidden, focus returns |
| Site | How it works (hero) | Scroll to section 03 | section in view |
| Site | Small model / Large model / Cold start | Switch figure data and sentence | bars equal manifest values |
| Site | Show data | Toggle data table | table visible, values equal manifest |
| Site | Play recording | Play the video | video playing |
| Site | Copy (code blocks, SHA, email) | Copy text, show "Copied" | clipboard equals text |
| Site | Send email | Open mail client | href is `mailto:` + contact email |
| Site | Footnote markers | Jump to evidence item | target visible |
| Site | Privacy / Terms / Credits / Licence | Open page | HTTP 200 |
| Dashboard | Nav items, Back to website | Switch screen / return to `/` | heading visible / URL is `/` |
| Dashboard | Light / Dark | Toggle and persist | `data-theme` persists after reload |
| Dashboard | Route task | Call router API, render decision | decision rendered, no console error |
| Dashboard | Route and verify on hardware | Confirm dialog, then verify | dialog shown; test clicks Cancel only |
| Dashboard | Show raw samples | Modal with samples | sample count equals API |
| Dashboard | Filters and selectors | Re-render | request made, figure updated |
| Dashboard | Export decisions CSV | Download CSV | row count equals API |
| Dashboard | Copy (hash, commands) | Copy text | clipboard equals text |

Any interactive element not in this table gets a real function added here, or is removed.

## 11. Media processing

`scripts/build_media.py`: reads `site/media/raw/` and `media.json`, strips metadata, writes the
responsive variants to `site/media/`, generates the Open Graph image, and fails if any photo lacks
alt text or a credit.

## 12. Automated checks (pytest + browser script; a phase fails if any check fails)

- Grep `site/` and `frontend/` (HTML, CSS, JS, copy JSON) and fail on: U+2014 em dash, emoji code
  points, `linear-gradient`, `radial-gradient`, `box-shadow`, `backdrop-filter`, `opacity` on photo
  overlays, `border-radius` above 2px, `Inter`, `Geist`, `Space Grotesk`, `lucide`, `#fff`/`#ffffff`
  backgrounds, banned words, U+2713/U+2714, `:hover` rules with `transform` or non-colour
  `transition`.
- No numeric literals with units in HTML/JS outside the format helpers.
- Every `<a>` and `<button>` has a `data-test` attribute that the interaction test uses.
- Browser test at 1440x900 and 390x844: every row of section 10, no console errors, every metric
  in the DOM equals the manifest, full-page screenshots saved.
- Every internal link and asset returns HTTP 200 from a local static server; `credits.html` lists
  all seven photos.
- Contrast: every text/background pair at least 4.5:1, including text panels next to photos.

## 13. Build phases (pytest + browser checks + NEW commit after each)

1. Tokens, fonts, Chart.js vendored; media pipeline; anti-vibecode checks written first.
2. Website sections 00 to 11, extra pages, dashboard-link logic, contact.
3. Dashboard restyle at `/app`, skeletons, theme toggle, CSV export, back link.
4. Proof: all checks green, full-page screenshots of the website and every dashboard screen at both
   sizes in `results/screenshots/final_design/`, final report, rebuild release folder, recreate
   review_package.zip.
