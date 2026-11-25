# Frontend finalization — independent QA acceptance (Agent G)

**Date:** 2026-11-25
**Worktree:** `C:\Users\Admin\Desktop\keel-frontend-worktree`
**Branch / baseline:** `feat/frontend-finalization-2026-11-25` at `35fb2b8abfd784393b2b252e2b9e2927aba817dd` (`origin/main`)
**Ownership:** new specs under `keel/fleet-next/tests/acceptance-final/**` and this report only. No feature implementation, shared component, other agent's test, `site/**`, or git operation was modified by this agent.

## Independence statement

Every result below was produced by running the browser against the actual Next.js app with dedicated fixtures (`keel/fleet-next/tests/acceptance-final/fixtures.ts`). No claim from another agent's summary was accepted without re-execution. Bridge responses are explicitly labelled **FIXTURE** objects shaped like the Python bridge envelopes (`routes.py`/`service.py`); assertions are on the exact mutation payloads observed at the `/api/bridge/*` boundary (`{ from_seq: N }`, `{ rows: [...] }`, `POST tasks/:id/undo`) and on real response bytes/headers, not on optimistic UI text alone. The strict console gate (zero `pageerror` / `console.error`) is inherited from `tests/e2e/fixtures.ts` for all but the one test that deliberately makes a fixture return HTTP 502 (that test uses `testWithExpectedHttpError`, which excludes only the Chromium 502 resource message).

## Exact commands and results

| # | Check | Exact command (cwd `keel/fleet-next` unless noted) | Real result | Raw log |
|---|---|---|---|---|
| 1 | TypeScript | `npx tsc --noEmit --incremental false` | **pass**, `TSC_EXIT=0`, no output | `tests/acceptance-final/qa-tsc.log` |
| 2 | Own acceptance suite — first run | `npx playwright test --config tests/acceptance-final/playwright.config.ts --workers=1 --reporter=line` | 16 pass / 11 fail (11.1 m). All 11 failures were QA-harness assumptions (download-manager bypass of `page.route`, popup not inheriting `page.route`, `about:blank` base URL, expected 502 console noise, two alerts matching one locator, empty notice region); **zero app defects** | `qa-run-1.log` |
| 3 | Own acceptance suite — clean post-fix run | same command, 30 tests incl. screenshot evidence | **30 pass / 0 fail (3.5 m)**, exit 0 | `qa-run-3.log` |
| 4 | SW diagnostic (dev) | `npx playwright test --config tests/acceptance-final/playwright.config.ts --workers=1 --reporter=line --grep "service worker registers"` | initially failed on an over-strict "active worker" assertion; after correcting it the app was observed to auto-register `/sw.js` at scope `/`. Dev Chromium reports no active/installing/waiting worker; production manifest/launch is covered by item 8 | `qa-sw-debug.log`, `qa-sw-debug2.log`, `qa-sw-debug3.log` |
| 5 | Owner feature suites | `npm run test:features` | **120 pass / 0 fail** total: Cowork 36 (incl. 8 dictation), Code/Duet 30, Fleet 24 (incl. 4 transcript), Capabilities/Settings 17, Onboarding 13; exit 0 | `qa-features.log` |
| 6 | Accessibility suite | `npx playwright test --config tests/a11y/playwright.a11y.config.ts --workers=1 --reporter=line` | **12 pass / 0 fail (1.4 m)**; dark and light 0 violations (min 5.33:1 / 4.87:1), reduced motion 0.001 ms, 200 % zoom no overflow, keyboard walkthrough reaches all six destinations | `qa-a11y.log` |
| 7 | Fleet transcript owner suite | included in item 5 (`npm run test:features` runs the Fleet config) | **4/4 transcript tests pass** inside Fleet 24/24; no separate run needed | `qa-features.log` |
| 8 | PWA owner suite (production build) | `npx playwright test --config tests/pwa/playwright.config.ts --workers=1 --reporter=line` | first attempt: webServer timed out at 300 s while `next build` ran under concurrent load; direct `$env:KEEL_DIST_DIR='.next-pwa'; npx next build` → **exit 0, compiled successfully, 5/5 static pages**; re-run **5 pass / 0 fail (38.9 s)** | `qa-pwa.log`, `qa-pwa-build.log`, `qa-pwa-run2.log` |
| 9 | Download-entry owner suite | `npx playwright test --config tests/features/download-entry/playwright.config.ts --workers=1 --reporter=line` | **3 pass / 0 fail (38.0 s)** | `qa-download-entry.log` |
| 10 | Marketing integrity (git blobs) | included in item 3 (`07-marketing-integrity.spec.ts`, 3 tests) | **3 pass** — changed files outside allowlist `[]`, protected-file drift `[]`, untracked marketing pages `[]` | `qa-run-3.log`, `qa-run-final.log` |
| 11 | Code/Duet audit owner suite | `npx playwright test --config tests/features/code-duet-audit/playwright.config.ts --workers=1 --reporter=line` | **8 pass / 0 fail (1.1 m)** | `qa-code-duet-audit.log` |
| 12 | Final confirmation re-run after concurrent agent edits | same command as item 3 | **28 pass / 2 fail (43.4 m under heavy concurrent load)**; failures were dev HMR `ERR_NETWORK_IO_SUSPENDED` console noise and a 90 s test timeout, not functional assertions. Targeted re-run of exactly those two tests (`--grep "Escape cancels the rewind dialog\|application exposes exactly one Get Keel Desktop"`) → **2 pass / 0 fail (28.3 s)** | `qa-run-final.log`, `qa-run-final-targeted.log` |
| 13 | Code/Duet re-run after `workspace.tsx`/`state.tsx` edits | `npx playwright test --config tests/features/code-duet/playwright.config.ts --workers=1 --reporter=line` | **30 pass / 0 fail (3.7 m)** | `qa-code-duet-rerun.log` |

`qa-*.log` paths are relative to `keel/fleet-next/tests/acceptance-final/`. Run-2 (`qa-run-2.log`, 26 pass / 1 fail) is retained as the intermediate state before the SW assertion was corrected.

## Requirement-by-requirement evidence (final run)

### 1. Fleet Markdown export, rewind and undo (`01-fleet-recovery.spec.ts`, 6 tests)
- **Export**: the Activity/History drawer shows exactly one `Download Markdown transcript (.md)` link with `href="/api/bridge/bots/b_alpha/export.md"` and `download="Alpha.md"`. An intercepted in-page `fetch` of that URL returned HTTP 200, `content-type: text/markdown`, `content-disposition: attachment`, and body **byte-equal** to the labelled Markdown fixture. Clicking the link fires a real download with suggested filename `Alpha.md`. A non-Markdown fixture response produces `Markdown export unavailable — the bridge did not return a downloadable file` and **no** link.
- **Rewind**: choosing seq 2 in `Rewind from sequence` posts exactly `{"from_seq": 2}` to `bots/b_alpha/rewind`. The bridge fixture returns `{ rows: [seq2, seq3], deleted: 2 }`; the UI reports `Deleted 2 transcript row(s) from sequence 2` and offers `Restore rows` only then.
- **Restore**: clicking `Restore rows` posts exactly `{"rows": [<the exact two rows returned by rewind>]}` to `bots/b_alpha/restore`, then states the bridge re-appends rows with new sequence numbers. An empty rewind response (`rows: []`) yields an alert `nothing was rewound; there is nothing to restore`, no `Restore rows` control, and **no** restore POST.
- **Undo**: the delete dialog states only one previous state is kept; delete posts `POST tasks/t1/delete`, `Undo delete` posts `POST tasks/t1/undo`, and the restored-task notice appears.
- **Keyboard**: Escape cancels the rewind dialog without closing the enclosing drawer, and focus returns to the rewind trigger.

### 2. Application "Get Keel Desktop" link (`02-desktop-link.spec.ts`, 2 tests)
- Exactly **one** control in the unified shell targets `/download` (searched all anchors by pathname and by accessible name); the "Get Keel Desktop" control is a native `<a>` (no duplicate `<button>`).
- `href="https://keel-desktop.vercel.app/download"`, `target="_blank"`, `rel` = exactly `["noopener","noreferrer"]`.
- Keyboard-only `focus()` + `Enter` opens a popup at the approved URL (external host intercepted by a context-level route; no real outbound request).

### 3. PWA download shortcut and launch/start URL (`03-pwa-launch.spec.ts`, 4 tests)
- Manifest: `name`/`short_name` `Keel`, `display: standalone`, `start_url: "/"`, design-system theme tokens, **exactly one** shortcut named `Get Keel Desktop` → `https://keel-desktop.vercel.app/download`.
- Launching `start_url` opens the real workspace (`.keel-app` visible, title matches `Keel`, no `download` in title/path).
- Document has one `<link rel="manifest" href="/manifest.webmanifest">` (`MANIFEST_LINK_COUNT=1`).
- The app auto-registers `/sw.js` at scope `/` after hydration (`SW_DIAGNOSTICS=[{"scope":"http://127.0.0.1:3351/","active":null,...}] AUTO_REGISTERED=true`). Dev Chromium leaves no active worker; the owner PWA suite verifies the production manifest, shortcut, start URL and launch (5/5), but no longer contains an "active service worker" assertion. Active/offline worker state therefore remains **not verified** in this workstream (see Limitations).

### 4. Cowork dictation (`04-cowork-dictation.spec.ts`, 5 tests)
- A deterministic `SpeechRecognition` double is installed before navigation; every `start`/`stop` call is recorded. No microphone or speech service is used.
- Final transcript inserts at the caret captured on click: `"hello| world"` + `"brave"` → `"hello brave world"`; a selected span is replaced (`"alpha [beta]" + "gamma"` → `"alpha gamma"`).
- **No auto-send**: no `POST .../messages` in any dictation test, and the status explicitly says `Nothing was sent`.
- `Stop dictation` invokes `recognition.stop()`, inserts no transcript, and reports `no transcript was inserted`.
- `not-allowed` error yields a `role=alert`, `aria-live=assertive` message about microphone permission; a later `onend` cannot overwrite it with false success.
- With both speech constructors deleted, the composer shows `Dictation unavailable in this browser.` and a disabled control.

### 5. Regression (`05-regression.spec.ts`, 2 tests; plus `npm run test:features` in item 5)
- All six destinations render with labelled fixtures and correct surface status; unavailable bridge is reported honestly with no placeholder agents.
- Owner feature suites independently confirm the same surfaces: 120 pass / 0 fail (36 Cowork including all 8 dictation cases; 30 Code/Duet; 24 Fleet including all 4 transcript cases; 17 Capabilities/Settings; 13 Onboarding).

### 6. Accessibility and keyboard/focus (`06-a11y-keyboard.spec.ts`, 5 tests; plus accessibility suite in item 6)
- Skip link is the first tab stop with a computed visible focus ring; command palette traps Tab/Shift+Tab, Escape closes and restores the trigger focus; 1–4 shortcuts switch surfaces; all six destinations expose top bar, main, status bar and Surfaces nav; the Fleet rewind dialog restores focus on Escape.
- The independent full audit (item 6) confirms 0 computed contrast violations in both themes (dark min 5.33:1, light min 4.87:1), reduced-motion worst animation/transition 0.001 ms, 200 % zoom without horizontal overflow, and a keyboard-only walkthrough reaching all six destinations.

### 7. Marketing-page integrity (`07-marketing-integrity.spec.ts`, 3 tests)
- Baseline = `35fb2b8abfd784393b2b252e2b9e2927aba817dd`. Allowlist = distribution/PWA files (`download.html`, `download.json`, `manifest.webmanifest`, `sw.js`, `vercel.json`, `app.html` contextual-link line, `api/download-manifest.js`, `ui/download.js`, `ui/download-ux.css`) plus `site/tests/**`.
- `git diff --name-only <baseline> -- keel/site` → no changed path outside the allowlist.
- Every protected tracked site file compared with `git hash-object --path` against `git rev-parse <baseline>:<path>` → identical (no drift, no deletions).
- No untracked marketing HTML under `keel/site`.

## Defect table

| ID | Severity | Owner | File:line / area | Finding | Status |
|---|---|---|---|---|---|
| QA-AG-001 | Info (environmental) | QA harness | `tests/acceptance-final/03-pwa-launch.spec.ts:73` | `next dev` Chromium auto-registers `/sw.js` at scope `/` but reports `active/installing/waiting = null`. Not a product defect; the initial over-strict "active worker" assertion was a QA error. Production manifest/launch verified in item 8; active-worker state not asserted there. | Documented as a test-coverage limitation |
| QA-AG-002 | Low (hygiene, not reproduced in final state) | Lead / Agent A | `keel/fleet-next/app/layout.tsx:46` + `app/manifest.ts` | During concurrent edits the explicit manifest `<link>` was removed (0 links) and briefly duplicated (2 identical links). Final run reports exactly 1 link to `/manifest.webmanifest`; no installability impact. | Not reproducible at final state; monitor in production build |
| QA-AG-003 | Info (QA harness) | QA harness | `tests/acceptance-final/01-fleet-recovery.spec.ts:28` | Chromium's download manager bypasses `page.route`; download **bytes** are therefore asserted through an intercepted in-page fetch, and the click only proves a download event with the correct suggested filename. | Documented; assertion adjusted |
| QA-AG-004 | Info (environmental) | QA harness / CI capacity | `qa-run-final.log` | Under concurrent agent suites the dev server's HMR WebSocket and chunk fetches produced `ERR_NETWORK_IO_SUSPENDED` console errors, tripping the strict gate on one test; another test hit the 90 s timeout. Both pass on an isolated targeted re-run (2/2). Known class: QA-F-003/QA-G-003. | Retested, **pass**; no app change |
| — | — | — | — | **No open product defect** was found in the seven acceptance areas at the final run. | — |

Previously reported owner defects (`QA-F-003`/`QA-G-003` bridge-504 console noise, `QA-F-013` Escape, `QA-F-016/017/018` fixture drift) were not re-created by this workstream; where relevant, their fixed paths were re-exercised here (Escape restoration, strict console gate, honest 502 state).

## Screenshots

All captured by `08-evidence-shots.spec.ts` at 1440×900, dark theme, fixture bridge:

| File | What it shows |
|---|---|
| `tests/acceptance-final/screenshots/fleet-transcript-controls.png` | Fleet agent drawer → Activity/History: Transcript panel with `Download Markdown transcript (.md)` and `Rewind transcript…` |
| `tests/acceptance-final/screenshots/fleet-rewind-dialog.png` | Rewind confirmation dialog with the real sequence selector |
| `tests/acceptance-final/screenshots/desktop-link.png` | Single `Get Keel Desktop` control in the sidebar |
| `tests/acceptance-final/screenshots/cowork-dictation-listening.png` | Cowork composer with the listening status and active mic control |

Failure screenshots/traces from runs 1–2 are under `tests/acceptance-final/test-results/` (harness artifacts, not product evidence).

## Final acceptance checklist

| Requirement | Verdict |
|---|---|
| 1. Fleet export / rewind / restore / undo with real payloads | **PASS** (6/6 own tests) |
| 2. Single, safe in-app desktop link | **PASS** (2/2 own tests) |
| 3. PWA shortcut + start URL + launch | **PASS** (4/4 own tests + 5/5 production owner tests; active SW state not verified — limitation) |
| 4. Cowork dictation (caret, no auto-send, stop, errors) | **PASS** (5/5 own tests) |
| 5. Cowork / Code+Duet / Fleet / Settings+Capabilities regression | **PASS** (own smoke + item 5) |
| 6. Accessibility + keyboard/focus | **PASS** (own 5/5 + item 6) |
| 7. Marketing pages byte-identical to `35fb2b8` outside allowlist | **PASS** (3/3 own tests) |
| Overall finalization acceptance | **PASS** — clean run 30/30; post-edit full run 28/30 with two load-induced failures re-run 2/2 green; owner suites all green. Information-only caveats QA-AG-001/003/004 (no product defect). |

## Limitations

- No live provider credentials: no real model turn was exercised; all bridge data is labelled fixture data.
- No OS-level PWA install/standalone-window launch; Chromium can assert manifest, scope, start URL and registration only. Active/offline service-worker state is not asserted by the current owner PWA suite (its former SW test was removed) and dev Chromium reports no active worker; not claimed as verified.
- No screen-reader hardware/NVDA/JAWS/VoiceOver audit.
- Native browser 200 % zoom gesture and packaged Electron/Tauri GUI remain outside this workstream (see `UI-TEST-MATRIX.md`).
