# SiliconRoute Design Spec (final, revision 2): "Field Report" Final Proof & Report

## 1. Executive Summary
The SiliconRoute website (`site/`) and local live dashboard (`frontend/`) have been rebuilt and styled strictly to `docs/DESIGN_SPEC.md` ("Field Report").

- **Design Philosophy**: Editorial field report aesthetics. Large confident typography (IBM Plex Sans & IBM Plex Mono), 12-column grid, flat colors (`#F3F3EF` paper, `#121211` ink, `#9B2A3C` signal red), hairline rules (1px `#D6D6CE`), zero gradients, zero rounded corners (0px / 2px on buttons/inputs), zero icons, no banned words.
- **Backend Constraints Preserved**: Static routing only (website at `/`, dashboard at `/app` with legacy aliases preserved). No measurement logic, routing algorithms, fits, or database records modified.
- **Frozen Database Integrity**:
  - Expected SHA256: `98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5`
  - Workspace DB: `98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5` (VERIFIED)
  - Release Folder DB: `98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5` (VERIFIED)
  - Review Package DB: `98542cffb7264eee537d218e1863ccbbc174495e0bf13eb244ee22cd6f034cf5` (VERIFIED)

---

## 2. Automated Check Results (Section 12)
1. **Section 1 Anti-Vibecode Grep**:
   - `scripts/check_design_spec.py`: **0 violations**.
   - `scripts/ui_lint.py`: **0 violations**.
   - Grep checks verified: no em dashes (U+2014), no emojis, no `linear-gradient`, `radial-gradient`, `box-shadow`, `backdrop-filter`, no `border-radius > 2px`, no banned fonts (`Inter`, `Geist`, `Space Grotesk`), no banned words, no checkmarks (`✓`, `✔`), no hover transforms.
2. **Data-Test Attributes**:
   - Every `<a>` and `<button>` across `site/` and `frontend/` contains a valid `data-test` attribute.
3. **Contrast Verification**:
   - All token contrast pairs pass WCAG 2.2 AA (>= 4.5:1).
4. **Photo Provenance**:
   - All 7 raw photos in `site/media/raw/` accounted for and credited on `credits.html`. Responsive AVIF/WebP/JPEG variants generated under 400 KB budget.

---

## 3. Section 10 Interaction Inventory Audit (Browser Edge Audit)
Audited via Playwright on Microsoft Edge at `1440x900` (desktop) and `390x844` (mobile):

| Surface | Control | Action Tested | Result |
|---|---|---|---|
| Site | Wordmark "SiliconRoute" | Scroll to top | PASS (`scrollY == 0`) |
| Site | Navigation links (Vision, How it works, Results, Snapdragon, Contact) | Scroll to section and set URL hash | PASS |
| Site | Hero "How it works" button | Scroll to section 03 | PASS |
| Site | Decision figure segmented control | Switch between "Small model", "Large model", "Cold start" | PASS |
| Site | Decision figure "Show data" | Toggle data table | PASS |
| Site | Mobile menu toggle and Esc key | Open mobile menu, close on Esc | PASS |
| Site | Copy buttons (SHA256, reproduction command, email) | Copy text to clipboard | PASS |
| Site | Extra pages (`privacy.html`, `terms.html`, `credits.html`, `dashboard.html`, `404.html`) | Fetch HTTP status | PASS (All HTTP 200) |
| Dashboard | Navigation rail | Switch between Overview, Live, Analysis, Router, Results, Evidence, About | PASS |
| Dashboard | Back to website link | Navigates to `/` | PASS |
| Dashboard | Light / Dark toggle | Switches `data-theme` between "dark" and "light" | PASS |
| Dashboard | Theme persistence | Persists `data-theme="dark"` after reload from `localStorage` | PASS |
| Dashboard | Router: Route task | Calls API, renders decision card and candidate breakdown | PASS |
| Dashboard | Router: Route and verify on hardware | Shows confirmation dialog, test clicks Cancel only | PASS |
| Dashboard | Router: Export decisions CSV | Generates CSV file download from API | PASS |
| Dashboard | Analysis: Show data table | Toggles model scaling data table | PASS |
| Dashboard | Evidence: Inspect samples | Opens modal displaying raw samples | PASS |
| Dashboard | Browser console | Zero errors logged | PASS (0 errors) |

---

## 4. Screenshot Evidence
All 14 required screenshots captured and saved to `results/screenshots/final_design/`:
1. `01_website_desktop_1440x900.png` (Full-page website desktop)
2. `02_website_mobile_390x844.png` (Full-page website mobile)
3. `03_dashboard_overview_1440x900.png`
4. `04_dashboard_live_1440x900.png`
5. `05_dashboard_analysis_1440x900.png`
6. `06_dashboard_router_1440x900.png`
7. `07_dashboard_results_1440x900.png`
8. `08_dashboard_evidence_1440x900.png`
9. `09_dashboard_about_1440x900.png`
10. `10_dashboard_overview_390x844.png` (Mobile overview)
11. `11_dashboard_router_390x844.png` (Mobile router)
12. `12_dashboard_results_390x844.png` (Mobile results)
13. `13_dashboard_dark_overview_1440x900.png` (Dark theme overview)
14. `14_dashboard_dark_router_1440x900.png` (Dark theme router)

---

## 5. Artifacts & Deliverables
- **Release Directory**: `release/siliconroute-v1.0/` (479 files, 55.06 MB, passes pytest 74/74).
- **Review Package**: `review_package.zip` (148 files, 13.80 MB, includes all code, docs, final design logs, and screenshots).
- **Git Commit**: Clean commits for each phase without modifying history. No remote pushes.
