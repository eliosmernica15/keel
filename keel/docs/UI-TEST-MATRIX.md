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

## Final completion round — re-runs (2026-11-24, Agent F, concurrent owners)

| Check | Command | Status | Evidence |
|---|---|---|---|
| UI contract checks (re-run) | `node tests/ui/verify-ui.mjs` | **pass (14)** / 4 skipped | `{"info":1,"pass":14,"skipped":4}`, exit 0, twice (before and after concurrent edits) |
| TypeScript | `npx tsc --noEmit --incremental false` | **pass** | no output, `TSC_EXIT=0` |
| Production E2E (baseline, pre-new-feature build) | `npx playwright test --config tests/e2e/playwright.prod.config.ts --workers=2 --reporter=line` | **129 pass / 2 fail** | 3.2 min; failures: `07-responsive settings@1440` (three `/api/bridge/*` 504s, QA-F-003) and `11-tour-command` palette not visible (QA-F-012). |
| New-requirement E2E (first run) | `npx playwright test tests/e2e/12-new-requirements.spec.ts --workers=1 --reporter=line` | **1 pass / 5 fail** | 5.3 min. Five downstream failures caused by QA-F-009 (`GET / 500` from a non-pure CSS Module selector); the pass was "Fleet board columns are the bridge's real task statuses". Spec assertions corrected/expanded after reading the owners' landed components. |
| Production build (blocker confirmation) | `$env:KEEL_DIST_DIR='.next-qa-build'; npx next build` | **FAIL** | `Failed to compile. ./features/cowork/cowork.module.css:285:1 — Selector "[data-match-active=\"true\"]" is not pure`, `BUILD_EXIT=1`. Release blocker QA-F-009. |
| CSS Module purity scan | grep `^\[...=` in `**/*.module.css` | 5 matches | Only `cowork.module.css:285` is impure; `code.module.css:33-34` and `duet.module.css:63-64` include local `.drawer` classes and are valid. |

## Final verification after all owners landed (Agent F, 2026-11-24 evening)

Environment: QA bridge on `:8739` (`tests/ui/start_bridge.py`, real `~/.keel`, throwaway token),
QA-owned production servers on `:3300`/`:3302` from a verified `.next-e2e` build.
`node tests/ui/verify-ui.mjs` → `{"info":1,"pass":14,"skipped":4}`, exit 0.
`$env:KEEL_DIST_DIR='.next-e2e'; npx next build` → **compiled successfully, 5/5 pages, exit 0, 90.7 s**.

| Check | Command | Real result |
|---|---|---|
| Full production E2E (140 tests incl. QA's 9 new) | `npx playwright test --config tests/e2e/playwright.prod-reuse.config.ts --workers=2 --reporter=line` | **132 pass / 8 fail (5.0 min)**. 7 failures are bridge-504 console-gate noise under parallel load (QA-F-011); 1 is the real QA-F-013 Escape defect. `NETWORK failed=[] httpErrors=[]`; 13/13 read-only BFF routes HTTP 200. |
| 504-noise re-run (single worker) | same config, `--workers=1 tests/e2e/09-theme-viewports.spec.ts` | **72 pass / 0 fail (2.5 min)** — all 6 viewports × 6 destinations × 2 themes re-captured |
| Other 504-noise failures re-run | same config, `--workers=1 --grep "number shortcuts do not fire\|Cowork home shows an empty state\|no pageerror or console.error while visiting"` | **3 pass / 0 fail (11.4 s)** |
| Accessibility (fresh production build) | `$env:KEEL_A11Y_REUSE=1; npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1 --reporter=line` | **12 pass / 0 fail (46.9 s)**. Dark: 0 violations, min 5.33:1 (Fleet 247 nodes); light: 0 violations, min 4.87:1 (Fleet 247, Capabilities 212). Reduced motion 0.001 ms; 200% zoom no overflow; keyboard walkthrough reaches all six. |
| New-requirement suite | `npx playwright test tests/e2e/12-new-requirements.spec.ts --workers=2 --reporter=line` | **8 pass / 1 fail** — sole failure is QA-F-013. |
| Owner feature suites | `npm run test:features` (stops at Cowork), then each config separately | Cowork **25 pass / 3 fail**; Code+Duet **30 pass**; Fleet **20 pass**; Capabilities+Settings **17 pass**; Onboarding **12 pass / 1 fail**. Failures are owner test-fixture drift (QA-F-016/017/018). |
| Visual inspection | `python tests/ui/make_contact_sheets.py`, all 12 sheets opened | 72/72 screenshots present; no horizontal overflow or whitespace-only surface; drawers closed at 360–1024 px, open at 1280–1440 px; Fleet's new tabs and Settings' "Agent models" section visible in both themes. |

> Lead's `lib/client.ts` now retries **idempotent GETs only** on 502/504 (writes never retried). This
> does not remove the browser's `console.error` for the first failed GET, so the strict console gate
> still fails when the shared bridge returns 504 under load; the 13-endpoint route probe and all
> functional assertions pass. QA-F-011 remains an environmental/backend finding.

> The new E2E spec `tests/e2e/12-new-requirements.spec.ts` is owned by QA and covers Fleet Board/Delegation map/Live wall/Cost (incl. honest states), board status columns, Cowork search/export/windowing/import honesty, onboarding Help & troubleshooting, and Duet review-pair identity + comment-only.


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

## Agent G — independent full-plan re-run (2026-11-24, post-integration)

Whole-plan detail, registry sample and defect table are in `FULL-PLAN-QA.md`. Raw command output is in `fleet-next/tests/ui/qa-logs/` (git-ignored). Integration commits present: `dee01be`, `7a5cd22`, `ea3f20b`, `e76aed0`. QA-owned bridge `:8739`, production build `.next-e2e` on `:3300`, a11y dev server `:3302`; lead's `:3200`/`:3000` untouched.

| Check | Exact command | Real result |
|---|---|---|
| TypeScript | `npx tsc --noEmit --incremental false` | exit 0, no output |
| Static harness | `node tests/ui/verify-ui.mjs` | `{"info":1,"pass":14,"skipped":4}`, exit 0 (twice) |
| Production E2E (final, 144 tests) | `npx playwright test --config tests/e2e/playwright.prod.config.ts --workers=2 --reporter=line` | **142 pass / 2 fail (3.4 min)**; both are QA-F-003/011 bridge-504 console-gate noise. Single-worker re-runs: `1 passed` (Fleet panels) + `2 passed` (dark/light 1440×900 cowork). Earlier mid-integration run was 131/144 (11 504 failures + 2 QA-control races, all re-run green). |
| Accessibility (full 12) | `npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1 --reporter=line` | first run **8 pass / 4 fail**; targeted re-run **2 pass / 2 fail**; final post-integration **12 pass / 0 fail (1.2 min)** → QA-G-002 is a fixture flake (hydration gate), not an app defect. Dark/light contrast 0 violations (min 5.33 / 4.87). |
| Feature suites | `npm run test:features` | Cowork 28 + Code/Duet 30 + Fleet 20 + Capabilities/Settings 17 + Onboarding 13 = **108 pass / 0 fail** (QA-F-016/017/018 fixed by owners). |
| QA hydration control (new) | `npx playwright test tests/e2e/13-qa-hydration-gate.spec.ts --workers=1` and same with `--config tests/e2e/playwright.prod-reuse.config.ts` | **4 pass** in dev and **4 pass** in production — palette/New-agent focus traps, 200 % zoom sidebar and 1–4 shortcuts work with the robust hydration gate. |
| Registry sample (24 IDs, 5 domains) | `python -m pytest -q` on 18 cited test files (`$env:PYTHONPATH='src'`) | **418 passed / 639 subtests**, exit 0 (plus 5 TUI tests and two earlier subsets). All 24 sampled `verified` claims had cited tests present and passing. |
| Generated-file discipline | `git hash-object` vs `git rev-parse HEAD:<path>` | `PLAN-INDEX.json`, `parity.json`, `Keel_Master_Plan_v6.md`, `keel/docs/parity.json` all byte-identical to HEAD; no change since `3863a2b`. |
| Secret / artifact scan | `git grep -E <secret-marker regex>` + `keel.dev_tools.security_scan` | 0 secret markers in tracked files; scanner's 128 flagged lines are all synthetic redaction fixtures. No generated build/test output in the last 25 commits; tracked `results.json` / `viewport-results.json` remain a hygiene exception (QA-G-004). |

New QA defects: QA-G-001 (transient prod-build block from an in-flight `tests/zoom-a11y/helpers.ts`, fixed by owner, verified), QA-G-002 (a11y fixture flake, open), QA-G-003 (bridge 504 console noise, open/environmental), QA-G-004 (tracked generated harness outputs, open). Retested and fixed: QA-F-013, QA-F-016/017/018.

## Frontend finalization round (2026-11-25) — evidence ledger

Sources: Agent G's `DISTRIBUTION-QA.md` (distribution journey, 2026-11-25) and the lead's
reconciled suites recorded in `UI-REQUIREMENTS-MATRIX.md`, `master-plan-v6-test-evidence.md`
and `FINAL-STABILIZATION-ACCEPTANCE.md`. Every row below is a **recorded command result**;
`not run` / `pending` rows are not passes.

| Check | Exact command / source | Real result |
|---|---|---|
| Distribution QA (Agent G) | `npx playwright test --config tests/distribution-qa/playwright.config.ts --reporter=list` (with `KEEL_E2E_BRIDGE_TOKEN`) | **42 passed / 0 failed (33.6 s)**, `PW_EXIT=0`; `npx tsc --noEmit --incremental false` exit 0. Raw log `qa-logs/final-acceptance-run.txt` |
| Production E2E after integration | `npx playwright test --config tests/e2e/playwright.prod.config.ts --workers=2 --reporter=line` | **144 passed / 0 failed (3.1 m)**; no 504 console noise reproduced this round |
| Accessibility | `npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1 --reporter=line` | **12 passed / 0 failed (1.2 m)**; dark 0 violations (min 5.33:1), light 0 violations (min 4.87:1), reduced-motion 0.001 ms, 200 % zoom no overflow |
| Feature suites | `npm run test:features` | Cowork 28 + Code/Duet 30 + Fleet 20 + Capabilities/Settings 17 + Onboarding 13 = **108 passed / 0 failed** |
| Site download logic | `node --test keel/site/tests/*.test.mjs` | **20 passed / 0 failed** |
| Distribution/release Python subset | `python -m pytest -q tests/verify_distribution_release.py tests/test_platform_targets.py tests/test_packaging_config.py tests/test_updater.py tests/test_release_verify_url_policy.py` | **45 passed in 9.13 s**, exit 0 |
| Whole-repo regression (lead) | `python -m pytest -q -o faulthandler_timeout=120` from `keel/`, clean HOME | **4610 passed / 54 skipped / 3707 subtests / 0 failed (474.31 s)** — definitive stabilization result; not a frontend-criterion count |

### Focus items from the finalization brief

| Item | Passed evidence | Honest status |
|---|---|---|
| Fleet transcript rewind / restore rows | real routes + `lib/api.ts` helpers; uncommitted UI in `AgentDetails.tsx` and specs `tests/acceptance-final/01-fleet-recovery.spec.ts` / `tests/features/fleet/fleet-transcript.spec.ts`; no passing run recorded by 11:24 | **implemented, unverified** |
| Fleet Markdown transcript export | real `bots/:id/export.md` + uncommitted `bridge.exportUrl()` probe in `AgentDetails.tsx`; no passing run recorded | **implemented, unverified** |
| Fleet task undo delete | Fleet feature suite 20 passed, payload captured at browser boundary | **verified** |
| In-app download entry | Agent G `02-pwa-journey.spec.ts` + `06-a11y.spec.ts`; one keyboard-reachable `#nav-download` link in `site/app.html` (QA-G-D07 accepted). In-flight `tests/features/download-entry/` (3 specs) `.last-run.json` status `passed` at 11:19; exact count awaits lead report | **verified on `site`**; `fleet-next` suite **reported passed**, count pending |
| PWA shortcut / start URL | Agent G `02-pwa-journey.spec.ts`: `/app` opens app, never `/download`; routing clean; offline shell/SW PASS. `site/manifest.webmanifest` `start_url /app` + shortcut. Uncommitted `fleet-next/app/manifest.ts` shortcut/identity + `tests/pwa/01-identity-and-launch.spec.ts` (6 specs) exist, but no recorded pass by 11:24 | **verified on `site`**; `fleet-next` **implemented, unverified** |
| Dictation | legacy `desktop/ui` SpeechRecognition code (`M6 Batch 18`, Python voice suite 13 passed); uncommitted control in `features/cowork/Composer.tsx` + `tests/features/cowork/13-dictation.spec.ts` (8 specs); the 11:23 cowork run recorded 3 failures, no pass by 11:24 | **not verified** |
| Code / Duet | Code+Duet feature suite 30 passed; prod E2E 144/144; a11y 12/12 | **verified for tested flows** |
| a11y / responsive | a11y 12/12; 72/72 viewport re-run (6 sizes × 6 destinations × 2 themes); distribution a11y 5/5 | **verified for automated checks**; native zoom gesture and screen-reader hardware remain manual/blocked |

> In-flight 2026-11-25 working-tree changes (Fleet rewind/export UI, dictation control,
> `fleet-next` PWA shortcut, download-entry/PWA/acceptance-final specs) are recorded at their
> observed state between 11:19 and 11:24. Only a passing suite result can move them to
> `verified`; the cowork run at 11:23 recorded 3 failures and the PWA run had no recorded pass.

> No production-readiness claim: `FINAL-STABILIZATION-ACCEPTANCE.md` verdict is
> `PASS_WITH_EXTERNAL_LIMITATIONS` with 18 `external_validation_pending`, 1 `owner_gated` and
> 1 `blocked` gate; packaged Electron/Tauri, live provider turn, real screen reader and public
> installer are still outside the passed evidence.

## Unified renderer integration round (2026-11-25) — `feat/unified-renderer-electron-2026-11-25`

Branch base `bcc9123`. Contract: `docs/RENDERER-INTEGRATION-CONTRACT.md` (Agent A, source audit
only). Every row below records an actually observed command output or an existing cited artifact.
`pending` / `not run` / `fail` rows are **not** passes. In particular, a `next build` producing
`.next/standalone` is **not** a packaged-EXE result.

| Check | Exact command / source | Real result | Status |
|---|---|---|---|
| Contract availability | read `keel/docs/RENDERER-INTEGRATION-CONTRACT.md` | file present, 378 lines; explicitly a read-only architecture proposal, no packaged GUI/native build/live turn run | source evidence only |
| Main-process syntax (Agent B source) | `node --check desktop-app/main.js` (in `keel/`) | no output, `MAIN_CHECK=0` | pass |
| Renderer-policy syntax (Agent B source) | `node --check desktop-app/renderer-policy.js` (in `keel/`) | no output, `POLICY_CHECK=0` | pass |
| Renderer-policy behaviour (Agent B/F test) | `node --test desktop-app/tests/renderer-policy.test.js` (in `keel/`) | first recorded run **25 pass / 0 fail** (421 ms); after the contract-reconciliation edits, re-run **29 pass / 0 fail**, `TEST=0`, 474 ms; covers default `legacy`, unified asset triad (`server.js` + `.next/static` + `public`), no silent fallback, explicit `KEEL_RENDERER=legacy` rollback, reason hygiene | pass (unit) |
| Node test glob note | `node --test desktop-app/tests/` (same cwd, Node v24.22.2) | `Cannot find module ...\desktop-app\tests`, tests 1 / fail 1 — use the explicit `.js` path above | fail (harness invocation only, not a code defect) |
| Entry-point source assertions | `node desktop-app/scripts/assert-ui-entrypoints.js` (in `keel/`) | first recorded run 23/25 pass, `ASSERT_EXIT=1`; after the reconciled main.js + new packaging entries, re-run **21/25 passed, `ASSERT_EXIT=1`**. Failures: `Electron feeds uiRoot() into the sidecar as KEEL_UI_DIR`, `Electron loads the sidecar over 127.0.0.1 (not a static file root)`, `Electron build config does not ship/repoint to fleet-next`, `Electron main.js does not reference fleet-next`. The old script asserts the pre-integration contract and must be updated, not bypassed. | **FAIL — blocking red gate (R10)** |
| Standalone build artifacts | `Test-Path fleet-next/.next/standalone/server.js`; `.next/static`; `public`; `standalone/.next/static`; `standalone/public` | `server.js` present (6,507 B, 2026-11-25 15:36 local); `.next/static` present; `public/` present (`fonts/`, `icon-192.png`, `icon-512.png`, `icon.svg`, `sw.js`); `standalone/.next/static` **absent**; `standalone/public` **absent**; `standalone/node_modules/sharp` present | source build present; overlay/packaging not proved |
| Reproducible standalone build script | `fleet-next/package.json` scripts `build:standalone` / `start:standalone` / `verify:standalone`; `fleet-next/docs/standalone-build.log` (Agent C) | script files present; one recorded build attempt compiled in 12.3 s but **failed** at type-check: `File '.../.next-bridge-int-mock/types/app/api/bridge/[...path]/route.ts' not found` (stale `tsconfig.json` include from a parallel isolated build). `docs/standalone-asset-inventory.json` **absent** — no successful script run recorded | **FAIL — build blocker, re-run required** |
| Packaging entries | `git diff -- desktop-app/package.json` | `renderer-policy.js` added to `build.files`; three `extraResources` entries added for `.next/standalone` (filter excludes `.env*`, `tests/`, `*.map`), `.next/static`, `public`; existing `site`, `desktop/ui`, `keel` entries intact | source implemented; **no package built after the change** |
| Loopback binding of Next child | read `fleet-next/.next/standalone/server.js:9` vs current `desktop-app/main.js` child env | server reads `process.env.HOSTNAME || '0.0.0.0'`. Earlier source revision set `HOST` (documented defect); current source sets `HOSTNAME: "127.0.0.1"`, `ELECTRON_RUN_AS_NODE=1`, `PORT`, and uses `serve --port 0` for Python | source reconciled; **socket assertion in G4 still pending** |
| Agent G Electron dev probe | `node tests/packaged-qa/electron-probe.mjs dev` → `qa-logs/electron-dev-2026-11-25T14-35-55-816Z.json` | CDP ok; window `http://127.0.0.1:10097/?t=…`, title `Keel - Desktop & Code`; `sessionStorage.keel_token` present; `hasBridgeTokenInHtml:false`; no Next child; sidecar child disappeared after close | pass for **legacy-only** dev launch; not unified evidence |
| Agent G Electron EXE probes | `node tests/packaged-qa/electron-probe.mjs exe` → `qa-logs/electron-exe-2026-11-25T14-36-57-215Z.json` and `...14-37-53-540Z.json` | both CDP ok; windows `http://127.0.0.1:10692/?t=…` and `http://127.0.0.1:9797/?t=…`, legacy renderer body both times; `bundledKeel` = two `resources/keel/keel.exe serve --port <port>` processes (parent+child), gone after close; `nextServer` / `nextServerAlt` empty; `errors:[]` | pass for **legacy packaged EXE**; **no unified EXE verification** |
| Existing packaged installer evidence (Agent E) | `docs/UI-DESKTOP-PACKAGING.md` §4–5, §8.3–8.4; `Get-FileHash dist\Keel-Setup-0.1.1.exe -Algorithm SHA256` | `F6CAE185A6A2AA53D61572E4C9930B3750CE418FC9AAF38BD788CCC6E63743BB`; built before the integration source edits; resources = `desktop/`, `keel/`, `site/`, `app.asar`, no `fleet-next/`; CDP confirmed the full local (`desktop/ui`) renderer and `KEEL_UI_PROFILE=mirror` rollback | verified for legacy renderer only |
| Agent G bridge-integration harness | `fleet-next/tests/bridge-integration/playwright.config.ts` + `helpers.ts` + `01-bff-security.spec.ts`, `02-agents-cowork.spec.ts`, `03-code-projects.spec.ts`, `04-fleet-capabilities.spec.ts` | real bridge `:8797`, mock `:8798`, Next BFF `:3311`/`:3312`/`:3313`; four specs present; **no `test-results/.last-run.json` and no recorded pass** at time of writing | **not run / pending** |
| Agent G packaged source-contract spec | `fleet-next/tests/packaged-qa/01-source-contract.spec.ts` → `test-results/.last-run.json` | `{"status":"failed","failedTests":[5 IDs]}`; `qa-logs/source-contract-detection.json` records `integrationDetected: true` and the captured main.js. No passing run recorded. | **FAIL — spec under reconciliation; not a pass** |
| G3 unified round-trip (sidecar → Next BFF → Python) | contract §6 + harness config | flow specified and harness scaffolded; no passing unified spec, no SSE named-row assertion recorded | **pending** |
| G4 packaged unified launch | requires package build with `fleet-next` resources + `electron-probe.mjs exe` | no such package built; EXE probe shows legacy renderer | **not verified / external gate** |
| G6 packaged rollback (`KEEL_RENDERER=legacy`, `KEEL_UI_PROFILE=mirror`) | policy unit tests pass; packaged re-run pending | unit evidence only | **not verified in package** |

### Agent report arrival status (this round)

| Agent | Integration artefacts observed in the worktree | Written integration report |
|---|---|---|
| A — contract | `keel/docs/RENDERER-INTEGRATION-CONTRACT.md` (378 lines, source audit) | yes (contract document) |
| B — renderer/electron source | `desktop-app/main.js`, `renderer-policy.js`, `tests/renderer-policy.test.js` (now 29 cases), `fleet-next/next.config.mjs` (`output: "standalone"`), `fleet-next/tsconfig.json` | no separate report doc; source + 29/29 unit run |
| C — standalone build scripts | `fleet-next/package.json` gained `build:standalone`, `start:standalone`, `verify:standalone`; `fleet-next/scripts/{build,start,verify}-standalone.mjs`; `docs/standalone-build.log` records one failed type-check | scripts landed; **no successful build/inventory recorded** |
| D | no new integration artefacts observed in this worktree at time of writing | none yet |
| E — packaging | no new edits in this round; prior `UI-DESKTOP-PACKAGING.md` legacy evidence retained | prior doc only |
| F — build/packaging | `desktop-app/package.json` now has `renderer-policy.js` in `files` and three `fleet-next` `extraResources` entries; main.js reconciled with contract (`HOSTNAME`, `--port 0`, `ELECTRON_RUN_AS_NODE`, asset triad) | `docs/RENDERER-FALLBACK-POLICY.md` (policy/default/env/rollback, 29-test output with command-shape caveat); **no package build recorded** |
| G — QA | `tests/packaged-qa/electron-probe.mjs` + dev/2× EXE probe JSON/log/PNGs + `01-source-contract.spec.ts` (last run failed); `tests/bridge-integration/` with 4 specs, no run | probe artifacts only; no written report yet |

> Rule applied: a row moves to `pass` only on a recorded command result or an existing cited
> artifact. No browser-only, unit-only or source-only result is promoted to a packaged claim.
> As further agent reports land, append their exact commands and results here rather than
> upgrading a row on expectation.

---

## Download page & installer QA — additions (2026-11-25, Agent E)

Commands and results cited below are from Agent G's runs; each `pass` is tied to a recorded run.

| Check | Command / evidence | Status | Notes |
|---|---|---|---|
| Device detection — Windows x64 / ARM64 | `npx playwright test --config tests/distribution-qa/playwright.config.ts` — `01-download-journey.spec.ts` "architecture fallback: UA hints hide, UA string still detects Windows x64" | **pass** | UA fallback verified; platform matrix rows `PLATFORMS` in `fixtures.ts` (Win x64, Win ARM64, macOS ARM64/x64, Linux, iOS, Android) |
| Device detection — macOS / Linux choice | same suite, "architecture fallback: Intel Mac gets an explicit Apple Silicon / Intel choice", "Linux offers an explicit DEB vs RPM choice" | **pass** | no silent wrong-arch pick; package family never guessed from the UA |
| Button enabled per OS | same suite, "primary action uses the exact verified manifest URL" + "dishonest manifest (size 0 / short sha / http URL) enables no download" | **pass** | one enabled CTA carries the exact manifest URL; disabled states use `aria-disabled` buttons, not links |
| SHA-256 / size verification | `node --test keel/site/tests/*.test.mjs` (from repo root) — `download-core.test.mjs:64-90` "availability requires verified_at, size, SHA-256 and a public HTTPS URL"; distribution suite `01-download-journey.spec.ts:198` | **pass** | 20/20 site tests; honest-gate tests (size 0, short sha, http) never enable a link |
| Installer publishing (artifacts) | `Get-FileHash -Algorithm SHA256 -Path keel\dist\win-unpacked\Keel.exe, keel\dist\Keel-Setup-0.1.1.exe` (run twice, identical) | **pass** | `Keel.exe` 235,419,136 B / `D52DB523…288B20`; `Keel-Setup-0.1.1.exe` 158,152,373 B / `170F1361…1667BC`; sidecar `keel.exe` 31,436,836 B / `B091538D…431FF` |
| Installer publishing (public URLs) | `DISTRIBUTION-QA.md` §2.5, `DISTRIBUTION-SMART-DOWNLOAD.md` §5, `keel/src/keel/release/build.py:163`, `RELEASE-2026-11-25.md` | **recorded** | GitHub base `https://github.com/eliosmernica15/keel/releases/download`; site `https://keel-desktop.vercel.app/download`; proxy `/api/download-manifest` (503 until configured) |
| Public installer availability | `keel/site/download.json` read-back + `DISTRIBUTION-QA.md` §2.5, QA-G-D03 | **not run / blocked** | all channels `available:false` — owner-gated publication |
| Packaged EXE launch (default, unified) | Agent G `qa-logs/electron-exe-2026-11-25T15-14-55-042Z.json`, `15-22-23-946Z`, `15-25-40-221Z` | **pass** | window `http://127.0.0.1:57613/`, title `Keel — Unified Workspace`, BFF `GET /api/bridge/bots` → 200, both children alive, `nonLoopbackListeners: []`, 0 token leaks |
| Packaged EXE rollback (`KEEL_RENDERER=legacy`) | Agent G `qa-logs/electron-exe-2026-11-25T15-24-38-876Z.json` | **pass** | window `http://127.0.0.1:51505/?t=…`, title `Keel — Desktop & Code`, no Next child, sidecar gone after close |
| Packaged EXE mirror (`KEEL_UI_PROFILE=mirror`) | Agent G `qa-logs/electron-exe-2026-11-25T15-19-23-069Z.json` | **pass** | token-bearing sidecar URL, "PUBLIC MIRROR · NO BACKEND" copy, title still `Keel — Desktop & Code` |
| Cutover state (source default) | `node -e 'const src=require("fs").readFileSync("desktop-app/renderer-policy.js","utf8"); …'` (Agent E, 2026-11-25) | **pass** | `DEFAULT_RENDERER = RENDERER_MODES.UNIFIED` (renderer-policy.js:46); 30/30 policy unit cases (Agent G §3.7) |

## Kanban drag fix result (2026-11-25)

| Check | Status | Evidence |
|---|---|---|
| Fleet kanban drag | **fixed & re-verified** (QA-F-010) | `UI-DEFECT-LOG.md:160` — new E2E "Fleet kanban… no dead controls" passes; all four new Fleet tabs (Board / Delegation map / Live wall / Cost) render their real panels; dead controls fixed in `fleet-next/features/fleet/Fleet.tsx` (`:27-39` → `:99-120` `case "board"/"org"/"live"/"cost"`). Drag is implemented in `features/fleet/Board.tsx` (`draggable`, `onDragStart`/`onDrop`) with `fleet.module.css` drop indicators. |
| Board drag in E2E | not recorded as a dedicated passing run | `fleet-next/tests/features/fleet/debug-drag.spec.ts` exists as a diagnostic ("TEMPORARY debug spec") |
