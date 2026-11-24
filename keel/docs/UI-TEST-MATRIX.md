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
| Playwright E2E suite (dev) | `npx playwright test --workers=2` | **pass** | 52 passed / 0 failed / 0 skipped |
| Playwright E2E suite (production) | `npx playwright test --config tests/e2e/playwright.prod.config.ts --workers=2` | **pass** | 52 passed / 0 failed / 0 skipped; full details in `UI-E2E-GUIDE.md` |
| Live bridge GET probe | harness-invoked `probe_bridge.py` | **pass** | 11 read-only endpoints → HTTP 200 |
| Browser walkthrough | in-app Chromium against `next start` on :3200 | **pass** | all 6 surfaces render, 0 console errors, no horizontal overflow at 912×670; theme + palette + surface persistence verified |

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
| 360×800 | pending | pending | pending | pending | pending | pending |
| 390×844 | pending | pending | pending | pending | pending | pending |
| 768×1024 | pending | pending | pending | pending | pending | pending |
| 1024×768 | pending | pending | pending | pending | pending | pending |
| 1280×800 | pending | pending | pending | pending | pending | pending |
| 1440×900 | pending | pending | pending | pending | pending | pending |

## Theme & accessibility

| Check | Status | Evidence |
|---|---|---|
| Dark theme | pass (browser) | onboarding + shell screenshots |
| Light theme | pass (browser) | Fleet surface screenshot |
| System theme | implemented (unverified) | `app/layout.tsx` + `lib/state.tsx` media query |
| No first-paint flash | implemented (unverified) | `app/layout.tsx` inline script |
| Keyboard nav (1–4, `[`, `\`, Ctrl/⌘K) | partial | Ctrl/⌘K verified in browser; other chords implemented, not individually exercised |
| Dialog focus trap + Escape | implemented (unverified) | `components/ui.tsx` Dialog (source-level); Escape on command palette verified |
| Reduced motion | implemented (unverified) | `app/ui.css`, `lib/state.tsx`, OS media query |
| Screen-reader notices | implemented (unverified) | `aria-live` in shell |
| Contrast audit | not run | static checks only; no automated contrast computation |

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
