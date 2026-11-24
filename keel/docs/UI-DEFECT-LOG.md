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
| QA-003 | **Medium** | `features/settings/SecuritySettings.tsx:28-36`; `features/onboarding/progress.ts:158-165` + `Onboarding.tsx:429-434`; consumer absent in `features/cowork/Cowork.tsx:73` | Permission mode is written to `keel-mode` and reported as a success ("Permission mode set to …", Onboarding: "The composer reads this preference at startup; reload if a session was already open"). **No Cowork/Composer source reads `keel-mode`** — `Cowork` initialises `mode` to `"build"` from local state. The control has no effect; the success message is false. | Settings (D) + Cowork (B) + Onboarding (E) | **open** |
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
