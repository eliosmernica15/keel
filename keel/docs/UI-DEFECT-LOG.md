# UI Defect Log — continuous QA, unified `fleet-next` workspace

**Maintained by:** continuous QA subagent (exclusive ownership: `fleet-next/tests/ui/**` and this file).
**Baseline:** branch `feat/frontend-unified-workspace`, worktree `C:\Users\Admin\Desktop\keel-frontend-worktree`.
**Last audit:** 2026-11-24 (after `5a670c3 chore(frontend): reconcile with latest shared backend baseline`, plus concurrent uncommitted work from other agents).
**Rule:** every row cites source actually read or a command actually run. "Open" means no fix observed at the cited line at the time of the check. Do not mark fixed without a re-test.

---

## 1. Defect table

| ID | Severity | File:line | Description | Owner workstream | Status |
|---|---|---|---|---|---|
| QA-001 | **High** | `fleet-next/lib/api.ts:153-159`; consumer `features/cowork/Cowork.tsx:178`; backend `src/keel/fleet/routes.py:1748` | `subscribeEvents()` registers only `es.onmessage`. The bridge emits **only named `event: row` SSE frames**, so `onmessage` never fires. Cowork's live stream text, `turn_end`, approval and ask updates are silently dropped; the UI keeps showing stale rows after a send. No error is surfaced because `onerror` does not fire. | Shared API (lead) + Cowork (B) | **open** |
| QA-002 | **Medium-High** | `fleet-next/lib/api.ts:102`; UI `features/code/workspace.tsx:885-890`; backend `src/keel/fleet/routes.py:528` | `clearFinishedShells()` issues **POST** `shells/clear/finished`, but the backend implements that route only in `dispatch_get`. `dispatch_post` has no handler and falls through (`routes.py:1696`), so the Terminal "Clear finished" button always fails. | Code & Duet (C) / Shared API | **open** |
| QA-003 | **Medium** | `features/settings/SecuritySettings.tsx:28-36`; `features/onboarding/progress.ts:158-165` + `Onboarding.tsx:429-434`; consumer now `features/cowork/Cowork.tsx` (mode hydrated from `keel-mode` and persisted through `changeMode`) | Permission mode used to be written to `keel-mode` and reported as a success while no Cowork/Composer source read it. Cowork now loads the persisted mode after mount and persists changes. | Settings (D) + Cowork (B) + Onboarding (E) | **fixed and re-tested (2026-11-24)** — `FAB-02` guard passes in `node tests/ui/verify-ui.mjs` → `{"info":1,"pass":14,"skipped":4}`; `EVT-01`/`API-03` also pass. See §6. |
| QA-004 | **Medium** | `features/capabilities/Capabilities.tsx:52` and `:55` | Unconditional user-facing claims "every status below comes from the connected bridge" and a `Live bridge data` badge. Individual panels show honest error states when the bridge is down, but the header still asserts a live connection. Misleading "connected" state (plan §9 functional quality). | Capabilities (D) | **open** |
| QA-005 | **Medium** | `features/fleet/Activity.tsx:60`; correct comparison `features/fleet/support.ts:220`, `features/cowork/Timeline.tsx:34-37`; backend `src/keel/fleet/tools.py:303-310` | `pendingAsks` filters **all** `ask` rows with no status check. The backend appends a second `ask` row with `status:"answered"` and the answer once a question is resolved. The Fleet agent panel therefore keeps rendering answered questions as "The agent is waiting for you" with an active Answer input, and allows re-answering. | Fleet (D) | **open** |
| QA-006 | **Medium** (a11y) | `app/page.tsx:68-85`, `:90-106` | Command palette declares `role="dialog" aria-modal="true"` but has **no Tab focus trap**. Arrow keys drive the selection while all ~40 command buttons remain in the tab sequence, so Tab moves focus into the background while the modal is open. Escape and focus restoration do work. Plan §9 requires expected Escape/focus behaviour for dialogs/menus. Static finding; headless confirmation was inconclusive (see §4). | Shell (lead) | **open** |
| QA-007 | **Low** | `features/fleet/support.ts:396-397` | `useFleetEvents` opens **two** `EventSource` connections to `/api/bridge/events`: one via `subscribeEvents` (dead for named frames, see QA-001) and a second direct one for `row` events. Doubles SSE connections and event-processing work per Fleet mount. | Fleet (D) | **open** |
| QA-008 | **Low / latent** | `lib/api.ts:142-145`; backend `src/keel/fleet/routes.py:772-774` | `keepAwake(enabled)` POSTs `{enabled}`, but the backend reads `payload.get("on")`. Calling it with `true` would always run `set_off()`. No visible control calls this method today, so it is a latent contract bug, not a live UI defect. | Shared API | **open (latent)** |

Defects DF-001…DF-004 from the previous QA cycle remain **fixed and verified** in `QA-REPORT.md`; they are not repeated here.

---

## 2. Checks run and real results

| Check | Command / method | Result |
|---|---|---|
| Static contract + a11y + placeholder harness | `cd keel/fleet-next && node tests/ui/verify-ui.mjs` | `{"info":1,"pass":11,"fail":3,"skipped":4}` — the three hard failures are the new regression guards `API-03`, `EVT-01`, `FAB-02` (QA-002, QA-001, QA-003). Exit code 1. |
| Original harness checks | same run | `API-01`, `API-02`, `FAB-01`, `A11Y-01..05`, `RESP-01`, `LIVE-01` all pass. `INV-01` is informational. |
| Backend route source | read `src/keel/fleet/routes.py:528, 772-774, 1035-1114, 1117-1135, 1205-1271, 1336-1416, 1675-1696, 1727-1755`; `src/keel/fleet/tools.py:296-316`; `src/keel/fleet/asks.py:28-71`; `src/keel/fleet/library.py:18` | Method/path mismatch QA-002; SSE frame name QA-001; answered-ask rows QA-005; payload mismatch QA-008. |
| Read-through of all feature components | `features/**` (43 files), `app/page.tsx`, `components/ui.tsx`, `lib/{api,client,state,types}.ts*` | QA-003…QA-007; no `onClick={() => {}}`, `alert()`, fabricated providers/models/audit rows or localStorage-stored secrets found. Credential inputs are cleared after submit (`ProvidersSettings.tsx:216`) and only a 4-char hint is displayed (`:209`). |
| Read-only HTTP probes | `webfetch http://127.0.0.1:3200/` and `/api/bridge/providers`, `/api/bridge/bots` | App shell rendered; both endpoints returned real JSON, HTTP 200, no secrets. No POST/PUT/DELETE was issued. |
| Read-only bridge GET probe (harness) | `tests/ui/probe_bridge.py` via harness `LIVE-01` | 11 safe GET endpoints probed over real HTTP; 0 anomalous. |
| Viewport measurement (provisional) | `node tests/ui/verify-viewports.mjs http://127.0.0.1:3300/` | One successful run (pre-hardened script) reported 6 viewports, 32 surface/viewport measurements, **0 `scrollWidth > innerWidth`**. The script was then hardened and re-run twice, but the dev server was refusing connections, so `viewport-results.json` currently holds the **failed re-run** (0 surfaces), not the successful measurement. See §3. |
| In-app browser walkthrough | `tools.browser.tabs.open` | **not run** — `[browser.disconnected] No desktop browser is connected to this session`. |

---

## 3. Responsive coverage — what is and is not pixel-verified

| Viewport | Result |
|---|---|
| 360×800 | Provisional: 0 overflow measured at `:3300` (Cowork/Code/Duet/Fleet; Capabilities/Settings not reached in that run). Not confirmed with hydration assertion. |
| 390×844 | Same provisional result. |
| 768×1024, 1024×768, 1280×800, 1440×900 | Same provisional result; all six surfaces reached at the larger sizes. |

`tests/ui/verify-viewports.mjs` was hardened after that run to (a) wait for a mount-time effect before clicking, and (b) assert that each click actually switched surfaces before measuring. **Re-run against a live `fleet-next` server is still required** before treating these as verified. Static CSS review (`RESP-01`) remains the only unconditional responsive evidence.

The headless run also logged `pageerror: EvalError: Evaluating a string as JavaScript violates … 'unsafe-eval' is not an allowed source … script-src 'self' 'unsafe-inline'` on the Next **dev** server (`:3300`). This is a dev-overlay/CSP artifact, not a production finding; it was not reproduced against a production build because `:3200` is not reachable from this shell (see §4).

---

## 4. What could not be verified, and the exact reason

1. **In-app browser walkthrough / screenshots / focus order** — `tools.browser.tabs.open` returned `[browser.disconnected] No desktop browser is connected to this session`.
2. **`:3200` from this shell** — `webfetch` could reach `http://127.0.0.1:3200/`, but `curl.exe` and headless Chromium from the shell both got `ERR_CONNECTION_REFUSED` / HTTP `000`. The two tools have different network contexts. The `:3200` preview was read via `webfetch` only (GET).
3. **Hardened viewport re-run** — the `:3300` dev server stopped mid-probe (`ERR_CONNECTION_REFUSED` on a subsequent launch). I did not start a server I do not own.
4. **Command-palette focus trap in a real browser** — the headless probe could not open the palette; the most likely cause is clicking before React hydration (`waitForFunction` was added afterwards) or the dev-server CSP error. Static source evidence for QA-006 stands; browser confirmation is outstanding.
5. **POST endpoint behaviour** — deliberately not probed: no POST that creates/deletes agents, tasks, providers or library files was issued. QA-002 is established from method-to-dispatcher source comparison, not a live failing request.
6. **Live model turn / streaming** — no provider credentials on this host (`providers` GET reports `configured:false` for all five providers). The SSE listener defect QA-001 is proven from the event name in source, not by observing a dropped token.
7. **Runtime virtualization / contrast / screen-reader walkthrough** — no browser connected; static analysis only.

---

## 5. Re-test procedure for owners

1. Fix at the cited line, then run `cd keel/fleet-next && node tests/ui/verify-ui.mjs`. A fix for QA-001/002/003 must make `EVT-01`/`API-03`/`FAB-02` pass. `API-03` derives the expected method from the dispatcher, so either changing the client to GET **or** adding a real POST handler is accepted.
2. For QA-004/005/006, update this log row to `fixed` only after the cited code no longer contains the pattern **and** a read-only review (or browser probe where available) confirms the new behaviour.
3. Re-run `node tests/ui/verify-viewports.mjs http://127.0.0.1:<port>/` against a server you own; all six viewports and all six surfaces should report `overflow:false` and non-null palette focus results.
4. Add a regression assertion rather than deleting a failing check. Never silence a check to make the harness green.


---

## 6. Lead re-test — all eight defects fixed (2026-11-24)

| ID | Status | Fix evidence | Re-test evidence |
|---|---|---|---|
| QA-001 | **fixed** | `lib/api.ts subscribeEvents()` now registers `addEventListener("row", …)` and `onmessage`, plus `onOpen` | `EVT-01` passes; Fleet `useFleetEvents` reduced to one subscription (QA-007) |
| QA-002 | **fixed** | `clearFinishedShells()` now issues GET | `API-03` passes |
| QA-003 | **fixed** | `Cowork.tsx` loads `keel-mode` after mount and persists changes via `changeMode` | `FAB-02` passes |
| QA-004 | **fixed** | `Capabilities.tsx` header no longer claims a live connection | read-back of `Capabilities.tsx:52,55` |
| QA-005 | **fixed** | `Activity.tsx` excludes ask ids that have a `status:"answered"` row | read-back of `Activity.tsx` |
| QA-006 | **fixed** | command palette uses real buttons in `role="group"` plus a document-level Tab trap | browser check: no `[role=listbox]`, palette focus stays inside; `tsc` clean |
| QA-007 | **fixed** | `useFleetEvents` opens exactly one SSE connection | read-back of `support.ts` |
| QA-008 | **fixed** | `keepAwake` sends `{on: enabled}` | `API` contract guard passes |

`node tests/ui/verify-ui.mjs` after the fixes: `{"info":1,"pass":14,"fail":0,"skipped":4}`.
`npx tsc --noEmit`: exit 0. `npm run build`: pass. No result above is claimed without a command actually run.

---

## 7. Continuous QA round — independent browser verification (2026-11-24, Agent F)

This section is written from commands actually executed against the worktree while other agents were still landing changes. Counts below are real command output; anything not re-run is labelled as such.

| ID | Severity | File:line | Description | Owner workstream | Status |
|---|---|---|---|---|---|
| QA-F-001 | **Blocker (observed, transient)** | `fleet-next/features/cowork/Timeline.tsx:63` | During the first dev Playwright run, `answered ?? textOf(...) \|\| "..."` is a JS syntax error (mixing `??` and `\|\|` without parentheses). Next returned `GET / 500`, so every surface failed. Observed failures included tests 11–39; the run was stopped rather than treating downstream failures as independent defects. | Cowork (B) | **fixed by concurrent owner; re-tested** — read-back shows `{(answered ?? textOf(row.body.answer)) \|\| "Your answer was sent."}`. Final production suite **131/131 pass**; dev suite 127/131 with the 4 re-run passes of QA-F-007/008. |
| QA-F-002 | **FIXED & re-verified** (was High a11y) | `fleet-next/app/globals.css:28-33`, `:45` (light-theme `--muted:#7f7973`, `--accent:#c2530a`, `--warn:#a8750a`, `--text:#141414` on accent) | Computed WCAG AA contrast fails in the **light** theme on all six surfaces: 338 violations in one measured pass (cowork 61, code 50, duet 50, fleet 57, capabilities 59, settings 61). Examples: muted text `rgb(127,121,115)` on `rgb(233,233,231)` = **3.54:1** (needs 4.5); accent on accent-soft = **3.91:1**; primary button text on accent = **4.01:1**; warning text = **3.31:1**. Dark theme: 0 violations, minimum 5.33:1. | Lead / design tokens | **fixed and re-verified** — light tokens now `--muted:#5f5952`, `--accent:#8a5a07` (the plan's light accent), `--warn:#7a5200`, `--ok:#1b6b47`, `--danger:#a8382a`, `--info:#294a9c`; primary button and skip link use white text in light theme. Re-run of `npx playwright test --config tests/a11y/playwright.a11y.config.ts tests/a11y/01-contrast.spec.ts --workers=1` → **2 passed**, `CONTRAST light:` 0 violations on all six surfaces, min 4.87:1. |
| QA-F-003 | **Medium (reliability, environment/backend)** | `fleet-next/app/api/bridge/[...path]/route.ts:149-154` (504 on any proxy exception); bridge `ThreadingHTTPServer` SSE connections | Intermittent `GET /api/bridge/* 504 Gateway Timeout` appeared in three separate browser runs while several agents' Playwright suites shared one local bridge. This trips the strict console gate in `tests/e2e/fixtures.ts:20-32` even when all functional assertions inside a test pass. Bridge process stayed alive; its log shows `ConnectionAbortedError: [WinError 10053]`. | Backend / lead (outside frontend scope) | **open / environmental** — re-runs with one worker reduced but did not eliminate it. Not claimed as a frontend code defect. |
| QA-F-004 | **Low (transient)** | no app line identified | One a11y run reported `pageerror: Invalid or unexpected token` while other agents were actively writing app source. Not reproduced in subsequent full-suite runs with identical configuration. | concurrent edits | **not reproducible** — recorded, not assigned as a standing defect. |
| QA-F-005 | **Medium (fixed, lead-requested guard)** | `fleet-next/app/page.tsx:199`; `features/onboarding/progress.ts:140` | Palette "Take the product tour" previously called only `restartOnboarding()`, so the flow resumed at the stored step instead of the tour. Lead changed the command to call `restartAtStep("tour")` first. | Shell (lead) | **fixed by lead; E2E guard added and re-tested** — `tests/e2e/11-tour-command.spec.ts` asserts the real localStorage write order and the tour copy. |
| QA-F-006 | **Medium (test harness, fixed)** | `tests/ui/verify-ui.mjs` walk/IGNORE_DIRS | After my a11y config created `.next-a11y`, the static harness scanned generated bundles and reported a false `API-01` failure (73 endpoints) plus a `FAB-01` warning (417 TODO matches in Next chunks). | QA (self) | **fixed and re-tested** — walker now skips every `^\.next(?:[-_.]|$)` distDir; re-run `{"info":1,"pass":14,"skipped":4}`, exit 0 |
| QA-F-007 | **Medium (test fixture, fixed)** | `tests/e2e/fixtures.ts:62-64`, `:78-91` | `openApp` waited only for SSR markup; a forced surface click before React hydration was dropped (screenshot showed Cowork still active after clicking Code). Sidebar drawer animation also made a forced click report "outside of viewport". | QA (self) | **fixed and re-tested** — `page.goto(..., waitUntil:'domcontentloaded')`, wait for `html[data-reduced-motion]` (set by the mount effect), and 250 ms drawer settle; the 4 previously failing responsive tests pass 4/4 on re-run |
| QA-F-008 | **Medium (environmental)** | shared local bridge / Chromium under parallel agent load | Full dev run (131 tests, 1.2 h) had 4 failures: `ERR_NETWORK_IO_SUSPENDED` console noise and three timeouts/`page.goto` timeouts with no app-code change. The same suite in the production config passed **131/131 in 4.4 min**. | environment / lead | **not an app defect** — recorded; production config is the clean evidence |

### Commands and real results behind §7

| Command | Result |
|---|---|
| `node tests/ui/verify-ui.mjs` (worktree, first action) | `{"info":1,"pass":14,"skipped":4}`, exit 0; `tests/ui/results.json` written |
| `node desktop-app/scripts/assert-ui-entrypoints.js` | `SUMMARY: 21/21 checks passed`, exit 0 |
| `node desktop-app/scripts/assert-ui-entrypoints.js --resources "C:\Users\Admin\Desktop\Claude clone\keel\dist\win-unpacked\resources"` | `SUMMARY: 26/26 checks passed`, exit 0 |
| `npx playwright test --workers=2` (dev config, first attempt) | aborted after observing repeated `GET / 500` from QA-F-001; failures through test 39 were caused by that syntax error, not counted as independent results |
| `npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=2` | 9 passed / 3 failed; failures: light contrast (real defect QA-F-002), two 200%-zoom tests whose **internal assertions passed** but whose fixture teardown caught QA-F-003 504s |
| `npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1 --reporter=line` | 9 passed / 3 failed: light contrast, one QA-F-004 transient pageerror, light contrast in the 200% zoom test. Zoom overflow test **passed** this time. Dark contrast: 0 violations across all six surfaces. |
| `KEEL_A11Y_REUSE=1 npx playwright test --config tests/a11y/... --workers=1` | same 9/3 split; stable reproduction of QA-F-002 |
| `node tests/ui/verify-ui.mjs` re-run after the QA-F-006 walker fix | `{"info":1,"pass":14,"skipped":4}`, exit 0 |
| `npx playwright test tests/e2e/08-stress.spec.ts --workers=2 --reporter=line` | **3 passed**; 0 idle mutations in all three large-data cases |
| `npx playwright test tests/e2e/10-network-routes.spec.ts tests/e2e/11-tour-command.spec.ts --workers=2` | **4 passed** (SSE teardown aborts excluded from the failed-request gate) |
| `npx playwright test tests/e2e/09-theme-viewports.spec.ts --workers=2` | 70 passed / 2 failed (504 console noise), 72 PNGs written; targeted re-run of the two + their theme twins: **4 passed** |
| `npx playwright test --workers=2 --reporter=line` (full dev suite) | 127 passed / 4 failed in 1.2 h under heavy parallel load; targeted re-run of the 4 after QA-F-007 fixture hardening: **4 passed** |
| `npx playwright test --config tests/e2e/playwright.prod.config.ts --workers=2 --reporter=line` | **131 passed / 0 failed (4.4 min)** — clean end-to-end result |

