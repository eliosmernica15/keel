# UI test & verification matrix

This matrix records what was actually run. Status: `pass`, `fail`, `skip (reason)`, `not run`.
No result is marked `pass` without recorded command output.

## Commands

| Check | Command | Status | Evidence |
|---|---|---|---|
| TypeScript check | `npx tsc --noEmit` (in `keel/fleet-next`) | **pass** | no output, exit 0 (final run after all subagents landed) |
| Production build | `npm run build` (in `keel/fleet-next`) | **pass** | compiled in 3.5–14 s; 5/5 static pages generated; `/` 90 kB, 193 kB First Load JS |
| Python suite (regression guard) | `python -m pytest -q` (in `keel/`) | see progress doc | started; no Python files were changed by this workstream |
| UI contract checks | `node tests/ui/verify-ui.mjs` | **pass (14)** / 4 skipped | `{"info":1,"pass":14,"skipped":4}` after fixing QA-001…QA-008; evidence `tests/ui/results.json` |
| Read-only six-viewport probe | `node tests/ui/verify-viewports.mjs` | **pass (one full run)** | 6 viewports × surfaces, 0 horizontal overflow; hardened re-runs were flaky because the dev server refused connections |
| Desktop entry-point assertions | `node desktop-app/scripts/assert-ui-entrypoints.js [--resources …]` | **pass** | 21/21 source checks; 26/26 with a real unpacked Electron layout |
| Playwright E2E suite (dev) | `npx playwright test --workers=2 --reporter=line` | **127 pass / 4 fail in the single loaded run; all 4 pass on re-run** | 131 tests total (52 existing + 79 new). The 4 failures were 1 sidebar click before drawer animation, 1 `ERR_NETWORK_IO_SUSPENDED` console noise, and 2 test timeouts under heavy parallel load; after the fixture hardening and a targeted `--grep` re-run all 4 pass (4/4). No app-code change was made for them. |
| Playwright E2E suite (production) | `npx playwright test --config tests/e2e/playwright.prod.config.ts --workers=2 --reporter=line` | **pass (131/131)** | 4.4 min, 0 failed / 0 skipped; production build in isolated `.next-e2e`; full details in `UI-E2E-GUIDE.md` |
| Live bridge GET probe | harness-invoked `probe_bridge.py` | **pass** | 11 read-only endpoints → HTTP 200 |
| Browser walkthrough | in-app Chromium against `next start` on :3200 | **pass** | all 6 surfaces render, 0 console errors, no horizontal overflow at 912×670; theme + palette + surface persistence verified |
| Accessibility suite (new) | `KEEL_A11Y_REUSE=1 npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1 --reporter=line` | **9 pass / 3 fail** | focus, traps, Escape, restoration, ARIA, reduced motion, keyboard walkthrough pass; 2 failures are the light-theme contrast defect QA-F-002, 1 is a 200%-zoom light-theme contrast assertion. See `UI-ACCESSIBILITY-AUDIT.md` |
| Stress: long transcript / large agent list / large file tree | `npx playwright test tests/e2e/08-stress.spec.ts --workers=2 --reporter=line` | **pass (3/3)** | 0 idle DOM mutations in all three cases; 23 130 / 12 380 / 12 577 DOM nodes; script 9 / 11 / 1 ms over a 1.5 s idle window |
| Network + broken routes | `npx playwright test tests/e2e/10-network-routes.spec.ts --workers=2` | **pass (3/3)** on re-run | 0 failed requests (SSE teardown aborts excluded), 0 HTTP errors, 13/13 BFF GETs 200, unknown route 404 |
| Tour-command regression | `npx playwright test tests/e2e/11-tour-command.spec.ts --workers=2` | **pass (1/1)** | storage order `keel-onboarding:step="tour"` before `keel-onboarding-done=false` |
| 6 viewports × 6 destinations × 2 themes | `npx playwright test tests/e2e/09-theme-viewports.spec.ts --workers=2` | **72/72 captured; 70 pass + 2 re-run pass** | 72 PNGs in `tests/e2e/screenshots/themes/`; the two console-gate failures were QA-F-003 504 noise and passed on a 4-test targeted re-run (4/4). All 12 contact sheets visually inspected |

> Note: `next dev` for the isolated E2E/a11y builds auto-added `.next-e2e*/types/**/*.ts` entries to the
> lead-owned `fleet-next/tsconfig.json`. No QA agent edited that file; `npx tsc --noEmit --incremental false`
> passes with those entries present (D-E2E-003 remains acknowledged).

## Route / surface matrix

| Surface | Route in shell | Empty | Loading | Error | Reload state | Status |
|---|---|---|---|---|---|---|
| Cowork | `destination="cowork"` | verified | verified | verified | drafts + surface | pass (browser) |
| Code | `destination="code"` | verified | verified | verified | surface/tree | pass (browser) |
| Duet | `destination="duet"` | verified | verified | verified | `keel-duet:*` | pass (browser) |
| Fleet | `destination="fleet"` | verified | verified | verified | surface | pass (browser, 7 real agents / 2 tasks) |
| Capabilities | `destination="capabilities"` | verified | verified | verified | — | pass (browser) |
| Settings | `destination="settings"` | verified | verified | verified | theme/panels | pass (browser) |
| Onboarding | full-screen layer | verified | verified | verified | `keel-onboarding:*` | pass (browser screenshot) |

## Viewport matrix (no horizontal overflow)

The in-app browser has no viewport emulation and `window.resizeTo` is blocked. Coverage now comes from (a) a real 912×670 walkthrough, (b) a read-only Playwright probe of all six required viewports (`tests/ui/verify-viewports.mjs`), and (c) Playwright screenshots at all six sizes (`tests/e2e/screenshots/`). A 360px screenshot exposed a real defect — both drawers opened over the workspace on first load — now fixed by defaulting drawers closed below 900 px.

| Viewport | Cowork | Code | Duet | Fleet | Settings | Onboarding |
|---|---|---|---|---|---|---|
| 360×800 | pass (dark+light) | pass | pass | pass | pass | pass |
| 390×844 | pass (dark+light) | pass | pass | pass | pass | pass |
| 768×1024 | pass (dark+light) | pass | pass | pass | pass | pass |
| 1024×768 | pass (dark+light) | pass | pass | pass | pass | pass |
| 1280×800 | pass (dark+light) | pass | pass | pass | pass | pass |
| 1440×900 | pass (dark+light) | pass | pass | pass | pass | pass |

`pass` here means: screenshot captured, `documentElement.scrollWidth <= innerWidth`, correct `data-theme`,
destination visible, and the 12 contact sheets visually inspected. Onboarding's first-run screenshot is at
`tests/e2e/screenshots/onboarding/first-run.png`.

## Theme & accessibility

| Check | Status | Evidence |
|---|---|---|
| Dark theme | pass (browser) | onboarding + shell screenshots |
| Light theme | pass (browser) | Fleet surface screenshot |
| System theme | implemented (unverified) | `app/layout.tsx` + `lib/state.tsx` media query |
| No first-paint flash | implemented (unverified) | `app/layout.tsx` inline script |
| Keyboard nav (1–4, `[`, `\`, Ctrl/⌘K) | **pass (browser)** | keyboard-only walkthrough reached all six destinations in `tests/a11y/04-zoom-keyboard-walkthrough.spec.ts` |
| Dialog focus trap + Escape | **pass (browser)** | palette: 60 Tab + 12 Shift+Tab inside dialog, Escape + focus restoration; shared `Dialog` (Fleet New agent): 24 Tabs, Escape + restoration |
| Reduced motion | **pass (browser)** | `emulateMedia({reducedMotion:'reduce'})` → `data-reduced-motion=true`, 0.001 ms worst animation/transition, status bar notice, `scrollBehavior:auto`; restore path passes |
| Screen-reader notices | **partial** | `aria-live="polite"` region and ARIA roles/names/states verified in browser; no NVDA/JAWS/VoiceOver run |
| Contrast audit | **dark pass / light fail** | computed WCAG AA: dark 0 violations (min 5.33:1), light 338 violations (min 3.31:1) — QA-F-002; method and limits in `UI-ACCESSIBILITY-AUDIT.md` |
| 200% zoom | **pass (no overflow)** | 720×450 CSS viewport proxy, all six destinations; light-theme contrast still fails at zoom |

## Runtime checks

| Check | Status | Reason / Evidence |
|---|---|---|
| Live bridge round-trip (read + UI render) | pass | BFF `/api/bridge/*` → bridge HTTP 200; 7 real endpoints observed in browser network log |
| Live model turn / streaming | blocked | no provider credentials on this host |
| Browser E2E (full Playwright suite) | pass | @playwright/test 1.65.1 installed as devDependency; 52/52 tests in both dev and production configs; 36 viewport × surface screenshots regenerated |
| Electron packaged build | not in scope | packaging workstream; see `UI-ARCHITECTURE.md` G4 |
| Tauri packaged build | not in scope | packaging workstream |
| Public `/app` mirror | unchanged | separate surface |
| PWA shell freshness | pass | fixed cache-first `/` staleness in `public/sw.js`; verified cache v2 → v3 migration in browser |
