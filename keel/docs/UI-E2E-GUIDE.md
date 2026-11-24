# UI E2E & visual verification guide (fleet-next / Playwright)

Owner: Playwright E2E & visual verification subagent (Quality & integration workstream).
Worktree: `keel-frontend-worktree`, branch `feat/frontend-unified-workspace`.
Generated: 2026-11-24.

## 1. What was added

| File | Purpose |
|---|---|
| `fleet-next/package.json`, `fleet-next/package-lock.json` | `@playwright/test@1.65.1` as a **devDependency** (no new runtime deps). |
| `fleet-next/playwright.config.ts` | Chromium project, dedicated webServer, trace/screenshot/reporter settings. |
| `fleet-next/tests/e2e/fixtures.ts` | Shared fixture: fails every test on any `pageerror`/`console.error`; navigation helpers; trust-request recorder. |
| `fleet-next/tests/e2e/01-launch-onboarding.spec.ts` | Initial launch, first-run overlay, choice/skip/resume/Escape, persistence. |
| `fleet-next/tests/e2e/02-navigation.spec.ts` | Four work surfaces via top bar; all six via sidebar; surface reload persistence. (The top bar intentionally exposes only Cowork/Code/Duet/Fleet.) |
| `fleet-next/tests/e2e/03-theme.spec.ts` | Dark / light / system, live OS-scheme change, reload persistence, top-bar toggle. |
| `fleet-next/tests/e2e/04-command-shortcuts.spec.ts` | Ctrl+K palette open/filter/execute/Escape/no-match; 1–4, `[`, `\`; typing suppression. |
| `fleet-next/tests/e2e/05-surfaces.spec.ts` | Cowork empty state + composer; Fleet **real bridge** agents/tasks; Code/Duet empty states; explicit trust gates, zero auto-trust requests. |
| `fleet-next/tests/e2e/06-console-errors.spec.ts` | Visits all six destinations with the strict console gate. |
| `fleet-next/tests/e2e/07-responsive.spec.ts` | 6 viewports × 6 destinations = 36 screenshots plus `document.documentElement.scrollWidth <= window.innerWidth`. |
| `keel/docs/UI-E2E-GUIDE.md` | This document. |

Screenshots: `fleet-next/tests/e2e/screenshots/<WxH>/<destination>.png`.
HTML report: `fleet-next/tests/e2e/report/`. Traces/failure screenshots: `fleet-next/tests/e2e/test-results/` (gitignored by the lead).

## 2. How to run

Prerequisites: `node_modules` installed; a Python bridge listening on `http://127.0.0.1:8739`; Chromium installed via `npx playwright install chromium`. Start that bridge with any **throwaway local token** (e.g. `KEEL_TOKEN=local-e2e-bridge-token`) and set `KEEL_E2E_BRIDGE_TOKEN` to the same value if you use a different one. This is a test-only bridge token — never a provider key or production credential, and no such value is stored in the browser.

```powershell
cd keel/fleet-next
npx playwright install chromium          # once
npx playwright test                      # full suite (131 tests after QA added stress/theme/network/tour specs)
npm run test:features                    # five feature suites (Cowork, Code+Duet, Fleet, Capabilities+Settings, Onboarding)
npx playwright test tests/e2e/07-responsive.spec.ts
npx playwright show-report tests/e2e/report
npx tsc --noEmit --incremental false    # tests type-check cleanly
```

`webServer` starts `npx next dev -H 127.0.0.1 -p 3300` with `reuseExistingServer: false` and explicit
`KEEL_BRIDGE_URL`, `KEEL_BRIDGE_TOKEN`, `KEEL_DIST_DIR=.next-e2e`, so the production `.next` build
used by the lead's `:3200` preview is not touched. `baseURL` is `http://127.0.0.1:3300`.

One **test-only** environment workaround remains (it changes no app code): Chromium 159's Local
Network Access check can block Next's dev HMR WebSocket on loopback, so the test browser is launched
with `--disable-features=LocalNetworkAccessChecks`. The former CSP header workaround was removed
after the lead's dev-only `'unsafe-eval'` fix (D-E2E-002). No `waitUntil: 'networkidle'` is used;
all waits are explicit locator assertions, and the SSE route is no longer aborted (aborting it
produced `console.error: ERR_FAILED` and tripped the strict console gate).

## 3. Coverage detail

- **Real data**: Fleet counts and names are read from the app's own BFF (`/api/bridge/bots`,
  `/api/bridge/tasks`) and compared against rendered cards/tab badges. No fixture data is used for
  this check.
- **Trust gate**: no test mutates the bridge. The tests record every `POST /api/bridge/projects/*/trust`
  request (expecting zero) and compare the projects JSON before/after visiting Code and Duet. A
  second, clearly-labelled read-only UI fixture injects one untrusted project via `page.route` to
  assert the explicit Code/Duet gate copy and buttons appear without any trust request.
- **Console gate**: `fixtures.ts` attaches `pageerror` and `console` (`error`) listeners before any
  navigation and asserts the collected array is empty in fixture teardown. A dedicated spec also
  asserts it explicitly after visiting all destinations.
- **Responsive**: exact viewports 360×800, 390×844, 768×1024, 1024×768, 1280×800, 1440×900;
  screenshot plus DOM overflow assertion per destination.

## 4. Results (real command output)

> This section is updated from actual command output only. No result is claimed without a run.

| Run | Command | Result |
|---|---|---|
| Install | `npm install --save-dev @playwright/test` | `added 3 packages, and audited 32 packages in 7s` |
| Browser | `npx playwright install chromium` | Chrome for Testing 159.0.8154.6 / Playwright chromium v1255 + headless shell downloaded |
| Type check | `npx tsc --noEmit --incremental false` | no output, exit 0 |
| Onboarding spec, dev (D-E2E-006 recheck) | `npx playwright test tests/e2e/01-launch-onboarding.spec.ts --workers=2` | **3 passed / 0 failed / 0 skipped** (20.9 s), including the reload-after-onboarding case under the strict console gate. |
| Onboarding spec, prod (D-E2E-006 recheck) | `npx playwright test --config tests/e2e/playwright.prod.config.ts tests/e2e/01-launch-onboarding.spec.ts --workers=2` | **3 passed / 0 failed / 0 skipped** (39.7 s). |
| Dev-mode suite (earlier stable run) | `npx playwright test --workers=2` | **52 passed / 0 failed / 0 skipped** (52 tests, 1.8 min). With QA's later stress/theme/network/tour specs the suite grew to 131 tests; under extreme parallel agent load one dev run was 127/131 with four environment flakes, all four passing on targeted re-run. |
| Production-mode suite (final, QA) | `npx playwright test --config tests/e2e/playwright.prod.config.ts --workers=2` | **131 passed / 0 failed** (4.4 min), strict console gate. |
| Feature suites (final) | `npm run test:features` | Cowork 18, Code+Duet 16, Fleet 8, Capabilities+Settings 14, Onboarding 8 — all passed (owners' real runs). |
| Accessibility suite (contrast re-test) | `npx playwright test --config tests/a11y/playwright.a11y.config.ts tests/a11y/01-contrast.spec.ts --workers=1` | **2 passed** after lead fixed light-theme tokens; 0 computed AA violations in both themes. |
| Production build (rebuild after lead's fixes) | `$env:KEEL_DIST_DIR='.next-e2e'; npx next build` | compiled successfully; 5/5 static pages generated; `/` 91.4 kB / 194 kB First Load JS |

A second, optional config `tests/e2e/playwright.prod.config.ts` uses the same port/env/console gate
with a fresh production build in `.next-e2e`; it is kept for release-style verification. The primary
dev config now runs cleanly after the lead's D-E2E-001/002 fixes (only D-E2E-006 remains). An early
`--workers=3` run saw transient bridge `504` responses during the bridge restart; the final runs
above used `--workers=2` against a healthy bridge (HTTP 200 probed).

Screenshots: all **36** required viewports × destinations were produced under
`tests/e2e/screenshots/` plus `onboarding/first-run.png`. The 360×800/390×844 captures show the
narrow-screen drawers closed on first load (lead's `lib/state.tsx` fix), with the workspace visible.

## 5. Defects found (reported to lead, not modified by this workstream)

| ID | Severity | Status | Evidence / resolution |
|---|---|---|---|
| D-E2E-001 | Blocker | **FIXED (lead)** | Runtime stack had `registerCommands` (`lib/state.tsx`) called from `Shell.useEffect` (`app/page.tsx`), caused by `goto` depending on the whole `app` object. Lead changed `goto` to depend on stable setters and made `registerCommands` bail out when unchanged. Final dev/prod runs show no `Maximum update depth exceeded`. |
| D-E2E-002 | Medium | **FIXED (lead)** | `next.config.mjs` now adds `'unsafe-eval'` to `script-src` only when `NODE_ENV !== 'production'`. Test-only CSP header rewrite was removed; dev hydrates normally. |
| D-E2E-003 | Low | **ACKNOWLEDGED (lead)** | `next dev` auto-added `.next-e2e/types/**/*.ts` to `tsconfig.json` `include`. No manual edit by this workstream; harmless since `tsc --noEmit` passes. |
| D-E2E-004 | Medium | **FIXED (lead)** | Palette effect now depends only on `[open]`. The `test.fixme` was removed and filter/no-match assertions re-enabled in `04-command-shortcuts.spec.ts`; both pass in final dev/prod runs. |
| D-E2E-005 | Medium | **FIXED (lead)** | Drawer breakpoint moved 900→1100 px so both drawers start closed at 1024×768. Previously measured Code/Duet `main` width was 0; final runs pass at all six viewports, including 1024×768, and screenshots were regenerated. |
| D-E2E-006 | Medium | **FIXED (lead)** | Previously the `SetupChecklist` badge rendered `+1 / -0` because `useChecklist()` initialised from `readChecklist()` (localStorage) during the first client render. Lead changed it to initialise with `freshChecklist()` and sync from storage in the mount effect. Re-enabled reload test passes in both configs (3/3 each), and both full suites are 52/52 under the strict console gate. |

## 6. Not verified

- Live model turn / streaming with real provider credentials (none on this host).
- Electron/Tauri packaged renderer paths (out of scope).
- Computed contrast ratios and screen-reader announcements (static/visual evidence only).
- All E2E defects found by this workstream (D-E2E-001 … D-E2E-006) are now fixed and re-verified.
  No test is skipped or `fixme`'d; the final production suite is 131/131 with the strict console gate.
