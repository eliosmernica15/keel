# Electron Integration QA — independent verification (Agent G)

**Date:** 2026-11-25
**Branch / worktree:** `feat/unified-renderer-electron-2026-11-25` @ `bcc9123`,
`C:\Users\Admin\Desktop\keel-frontend-worktree`
**Ownership:** only `fleet-next/tests/packaged-qa/**` and this report were written by
this agent. No app/feature/source/config/Electron/Python/CI/other-doc edit, commit,
push or git-state change was made here. (The lead independently edited the QA spec's
array typing for `tsc`; no other owned file was changed by another agent.)

## Evidence categories (never conflated)

| Tag | Meaning |
|---|---|
| `[S]` | **Source assertion** — static read of source/config, no runtime. |
| `[B]` | **Browser test** — Chromium page, no Electron shell. |
| `[ED]` | **Electron development launch** — real `electron .` + CDP. |
| `[PE]` | **Packaged EXE launch** — real `dist/win-unpacked/Keel.exe` + CDP. |
| `[X]` | **Blocked / not run** — explicitly not a pass. |

Every `[PE]` claim below corresponds to an EXE process that was actually executed;
no packaged result is inferred from source.

---

## 0. Environment, artifacts and timeline

| Item | Value |
|---|---|
| OS / runtimes | Windows (`win32`), Node `v24.22.2`, Python `3.11.9`, Electron `42.11.18`, Next `15.5.29`, Playwright `1.65.1` |
| Final EXE (cutover build) | `dist/win-unpacked/Keel.exe`, mtime **16:21:45 local**, SHA-256 **`D52DB523BE65DE981320A175B9DA3C29B5B2F5925D3AED787CAA0F0254288B20`** |
| Final installer | `dist/Keel-Setup-0.1.1.exe`, mtime **16:23:05 local**, SHA-256 **`B25C0977DE6491DFF886A9AF4C747F96E7A0D27061FF525E1AC9A9412644BC58`** (lead-supplied value, independently hashed here) |
| Packaged policy default | `@electron/asar.extractFile(app.asar, 'renderer-policy.js')` → `DEFAULT_RENDERER = RENDERER_MODES.UNIFIED` (matches source) |
| Packaged resources | `fleet-next/{server.js,.next/static,public,node_modules}` — **1,994 files / 62.2 MB** traced Next runtime; plus `desktop/ui`, `site`, `keel/keel.exe`, `app.asar` |
| Other agents' gates (not run by me) | `assert-ui-entrypoints.js --resources …` 47/47; `verify:standalone` 21/21; root `tsc --noEmit` clean |

**Timeline (UTC stamps from the harness):**

- `14:35:55–14:38:25Z` — baseline `[PE]` + `[ED]` launches of the **pre-integration** build.
- `~14:39Z` — integration files appeared in the worktree (uncommitted).
- `14:40Z` — first source-contract run correctly failed against old `main.js`.
- `14:42–14:53Z` — unified `[ED]` launches, UI walk, token scans, lifecycle probes.
- `14:55:50Z` — unified `[ED]` retest against the **real** standalone build output.
- `15:01Z` — first packaged rebuild lands but omits traced `node_modules`; `15:10:50Z` `[PE]` unified launch fails honestly (D-G6).
- `15:07–15:14Z` — second rebuild; `15:14:55Z` `[PE]` unified launch succeeds (full UI walk).
- `15:16:25Z` — exact-command rerun was **discarded** (attached to a concurrent CDP listener; no child PIDs — see §3.2).
- `15:17:40Z` — G4 rerun on a unique CDP port: clean, self-owned pass.
- `15:18:38Z` — G6 explicit legacy `[PE]`; `15:19:23Z` explicit mirror `[PE]`.
- `15:20:50Z` — default (no env) packaged launch: still legacy because the packaged `app.asar` predates the source default cutover (D-G7).
- `15:22:23Z` — literal lead command rerun on a free CDP port: clean G4 pass.
- `15:24–15:26Z` — **final cutover build** (installer SHA `B25C0977…`): definitive
  default-unified, legacy-rollback, explicit-mirror and extended token/surface probes.

---

## 1. Source assertions `[S]`

`npx playwright test --config tests/packaged-qa/playwright.config.ts` → **9 passed /
0 failed** (1.7 s). Detection record: `qa-logs/source-contract-detection.json`.

| Requirement | Evidence (file:line) | Result |
|---|---|---|
| Electron starts Python sidecar | `main.js:186-230` (`startSidecar`, `serve --port 0`, `KEEL_TOKEN`) | PASS |
| Starts packaged Next server | `main.js:232-444` (`fleetNextRuntimeDir`, `nodeExecutable`, `spawn(node,[script])`, `ELECTRON_RUN_AS_NODE=1` in **child** env only) | PASS |
| Passes real loopback URL + token server-side | `main.js:347-352,376-377` — `KEEL_BRIDGE_URL=http://127.0.0.1:<parsed.port>` (no `?t`), `KEEL_BRIDGE_TOKEN=token`; regex `^[A-Za-z0-9_-]+$`; log only length + 4-char prefix | PASS |
| BFF injects token server-side | `app/api/bridge/[...path]/route.ts:9-10,34,60` — `x-keel-token` header; no `NEXT_PUBLIC*` | PASS |
| Binds loopback | `main.js:243-253` OS-reserved `127.0.0.1` port, `:320-326` HTTP poll on `127.0.0.1`, `:380` `HOSTNAME=127.0.0.1` (not `HOST`); runtime sockets §2/§3 | PASS |
| Loads Fleet Next URL | `main.js:441` returns `http://127.0.0.1:<port>/`, `:672-679` unified branch, `:611` `createWindow(loadUrl)` | PASS |
| Shuts down both children | `main.js:50-96` (`stopChild`, `stopSidecar`, `stopUiServer`, `stopAllChildren`, `taskkill /PID … /T /F`); called on window `closed` `:613-616`, `before-quit` `:692-695`, startup catch `:682-687`, failure paths `:504-515` | PASS |
| Single instance | `main.js:635-645` lock + `second-instance` focus; runtime §2.5 | PASS |
| Failure screen | `main.js:452-526` branded `Keel could not start` + `dialog.showErrorBox` + `app.exit(1)`; runtime §2.4 and §3.2 | PASS |
| Legacy fallback / explicit-only mirror | `renderer-policy.js:190-243`; 30/30 unit cases; runtime G6 §3.4/§3.5/§3.7 | PASS |
| Packaging carries complete runtime | `desktop-app/package.json:27-79` (`renderer-policy.js` in `files`; three `fleet-next` `extraResources`; `!**/.env*`, `!**/*.map`, `!**/tests/**`); `next.config.mjs` `output:"standalone"` | PASS |
| Default renderer governance | `renderer-policy.js:46` now `DEFAULT_RENDERER = UNIFIED` — owner cutover **after** G1–G6. My spec accepts either pinned value and requires explicit rollback/mirror to keep working. | PASS (cutover recorded; packaged default verified §3.7) |

`node --test desktop-app/tests/renderer-policy.test.js` → **30 passed / 0 failed**
(178 ms) on the final tree, including “default is unified when G1–G6-passed runtime
is present”, “default degrades to legacy when the unified runtime is absent”,
“explicit `KEEL_RENDERER=legacy` is the packaged rollback”, “no silent fallback”,
“mirror with no assets fails”, “reason strings never contain credentials, env values
or absolute paths”. Root `npx tsc --noEmit -p fleet-next/tsconfig.json` → **clean**
(no output).

---

## 2. Actual Electron development launches `[ED]`

All runs used `--remote-debugging-port` + `chromium.connectOverCDP`; each JSON log
records window URL/title/text, child PIDs, netstat listeners and post-close cleanup.

### 2.1 Pre-integration baseline (`14:35:55Z`, `qa-logs/electron-dev-2026-11-25T14-35-55-816Z.json`)

Window `http://127.0.0.1:10097/?t=…`, title **`Keel — Desktop & Code`**; token in URL
and `sessionStorage.keel_token`; sidecar PID 41860 (parent = Electron) gone after
close; no Next child. Historical leak, fixed by D-G4.

### 2.2 Unified mode (`14:47:19Z`, `qa-logs/electron-dev-2026-11-25T14-47-19-249Z.json`)

```
node tests/packaged-qa/electron-probe.mjs dev \
  KEEL_RENDERER=unified \
  KEEL_RENDERER_UNIFIED_DIR=<fleet-next/tests/packaged-qa/tmp/unified-runtime> \
  KEEL_RENDERER_READY_TIMEOUT_MS=45000 KEEL_QA_UI_CHECK=1
```

- Window: **`http://127.0.0.1:51402/`** — no `?t=`; title **`Keel — Unified Workspace`**.
- Children: `python -m keel serve --port 0` PID 47828; Electron-as-Node
  `<runtime>/server.js` PID 17112 (parent = Electron 40468). Both absent after close.
- Sockets (`14:53:06Z` run): `TCP 127.0.0.1:51401 … 47828`, `TCP 127.0.0.1:51402 … 17112`;
  `nonLoopbackListeners: []`.
- BFF inside Electron: `fetch('/api/bridge/bots')` → **HTTP 200**, real bot JSON,
  `tokenInBody: false`.
- Surfaces walked: **Cowork, Code, Duet, Fleet, Capabilities, Settings** — all in one
  window; Fleet shows real bridge roster, “Bridge online”, “Keel · local build”.
- Theme: `keel-theme-v2="dark"` + reload → `data-theme=dark`, `colorScheme=dark`.
- External link: “Get Keel Desktop” → `https://keel-desktop.vercel.app/download`;
  clicking produced **no new Electron target** (CDP pages 1 → 1).
- Token scan: real token from `%APPDATA%\keel-desktop\sidecar.log` (length 24, prefix
  `V0NB…`) scanned over `/` HTML + 7 production JS chunks → **0 leaks**; renderer
  `localStorage` only layout keys, `sessionStorage` empty, HTML token regex false.
  Production emitted no `sourceMappingURL`, so no maps existed to scan `[X]`.
- Real-build retest (`14:55:50Z`, `qa-logs/electron-dev-2026-11-25T14-55-50-964Z.json`):
  same result with `KEEL_RENDERER_UNIFIED_DIR=<fleet-next>/.next/standalone` — closes D-G2.

### 2.3 Legacy fallback after integration (`14:51:39Z`)

`KEEL_RENDERER=legacy` → `http://127.0.0.1:64722/?t=…`, old title, no Next child.

### 2.4 Failure screen (`14:50:42Z`, `qa-logs/lifecycle-failure-2026-11-25T14-50-42-320Z.json`)

Missing unified runtime → branded `startup-failure.html`, title `Keel — could not start`,
text “… no silent fallback”; `childrenAfterFailure` empty. Screenshot
`evidence/electron-failure-screen-2026-11-25T14-50-42-320Z.png`.

### 2.5 Single instance / restart (`14:51:06Z`, `qa-logs/lifecycle-single-2026-11-25T14-51-06-400Z.json`)

Second launch with same userData → **exit code 0**, no second window, sidecar PID 46352
and Next PID 36752 unchanged after 12 s. Repeated launches also cover clean restart.

---

## 3. Actual packaged EXE launches `[PE]`

### 3.1 Legacy build on disk before the rebuild (`14:36:57Z`, `14:37:53Z`)

Old EXE (no `resources/fleet-next`): window `http://127.0.0.1:10692/?t=…` and
`:9797/?t=…`, title `Keel — Desktop & Code`; bundled sidecar bootloader + socket
child PIDs 36836/43688 and 36476/43364. `afterCloseChildren.bundledKeel: []` — the
whole PyInstaller tree was terminated.

### 3.2 First unified package attempt — FAILED (`15:10:50Z`, `qa-logs/electron-exe-2026-11-25T15-10-50-821Z.json`)

Branded failure screen with:
`the Keel UI server exited before it was ready (code 1): … Error: Cannot find module 'next'`
(`ui-server.log` tail confirms `MODULE_NOT_FOUND` twice, i.e. the one retry also failed).
Packaged `resources/fleet-next/node_modules` was missing at that moment. Recorded as
D-G6. Screenshot `evidence/electron-exe-2026-11-25T15-10-50-821Z.png`.

### 3.3 G4 — unified packaged EXE — PASS (`15:14:55Z`, full UI walk; `15:17:40Z`, exact command)

Full walk (`qa-logs/electron-exe-2026-11-25T15-14-55-042Z.json`, command used the lead's
exact invocation **plus** `KEEL_QA_UI_CHECK=1`):

- Window: **`http://127.0.0.1:57613/`**, title **`Keel — Unified Workspace`** — token-free URL.
- Real children: bundled sidecar `resources/keel/keel.exe serve --port 0` PIDs
  45568 → 16244; packaged Next `Keel.exe resources/fleet-next/server.js` PID 47092
  (parent = Electron 45708). Both trees absent after close.
- Socket: `TCP 127.0.0.1:57613 … LISTENING 47092`; `nonLoopbackListeners: []`.
- BFF: HTTP 200 with real bot JSON; `tokenInBody: false`.
- Surfaces: Cowork, Code, Duet, Fleet, Capabilities, Settings (screenshots below).
- Branding: “Keel setup / Welcome to Keel”, tabs Cowork/Code/Duet/Fleet,
  “Get Keel Desktop”, status “Bridge online”, “Keel · local build” — **not** old
  `desktop/ui`, **not** the mirror.
- Token scan: real token (prefix `bbEj…`) not found in `/` HTML or 7 JS chunks;
  renderer `localStorage` layout keys only, `sessionStorage` empty; `anyLeak: false`.
- External link: href `https://keel-desktop.vercel.app/download`; CDP pages 1 → 1.
- Theme: `keel-theme-v2="dark"` persisted and applied after reload (`data-theme=dark`).
- Success screenshot: `evidence/electron-exe-2026-11-25T15-14-55-042Z.png`;
  per-surface: `electron-exe-surface-{cowork,code,duet,fleet,capabilities,settings}-2026-11-25T15-14-55-042Z.png`.

Clean re-run of the lead's exact command on a unique CDP port
(`15:17:40Z`, `qa-logs/electron-exe-2026-11-25T15-17-40-859Z.json`):
`node tests/packaged-qa/electron-probe.mjs exe KEEL_RENDERER=unified KEEL_QA_CDP_PORT=9345`
→ window `http://127.0.0.1:57831/`, title `Keel — Unified Workspace`; Next PID 26384
(parent 30020) listening `127.0.0.1:57831`; sidecar PID 24972; both gone after close;
`nonLoopbackListeners: []`; `errors: []`. Screenshot
`evidence/electron-exe-2026-11-25T15-17-40-859Z.png`.

**Literal lead command, final clean run (`15:22:23Z`,
`qa-logs/electron-exe-2026-11-25T15-22-23-946Z.json`):**
`node tests/packaged-qa/electron-probe.mjs exe KEEL_RENDERER=unified` → window
`http://127.0.0.1:56024/`, title `Keel — Unified Workspace`; Next PID 3168 (parent
28056) listening `127.0.0.1:56024`; bundled sidecar PID 41144 (parent 28056); both
trees absent after close; `errors: []`. Screenshot
`evidence/electron-exe-2026-11-25T15-22-23-946Z.png`.

**Discarded run (transparency):** the first exact-command rerun at `15:16:25Z`
(`qa-logs/electron-exe-2026-11-25T15-16-25-646Z.json`) showed a plausible window but
**no child PIDs and empty listeners**, and the child exited `code=0`. It had attached
to a concurrent agent's CDP listener on port 9334, not to its own process. It is
**not** counted as evidence; a unique CDP port (`KEEL_QA_CDP_PORT`) was added to the
probe to prevent collisions. The `15:22:23Z` rerun above is the clean literal pass.

### 3.4 G6 — explicit legacy fallback in packaged EXE — PASS (`15:18:38Z`, `qa-logs/electron-exe-2026-11-25T15-18-38-727Z.json`)

`KEEL_RENDERER=legacy` → `http://127.0.0.1:55367/?t=…`, title `Keel — Desktop & Code`,
renderer text “KEEL DESKTOP · YOUR AGENTS, YOUR FILES, YOUR MACHINE /
LOCAL · 127.0.0.1 · NO CLOUD RELAY”; **no Next child**; bundled sidecar PID 28112
gone after close. Screenshot `evidence/electron-exe-2026-11-25T15-18-38-727Z.png`.

### 3.5 Explicit mirror in packaged EXE — PASS (`15:19:23Z`, `qa-logs/electron-exe-2026-11-25T15-19-23-069Z.json`)

`KEEL_UI_PROFILE=mirror` → token-bearing sidecar URL (legacy transport), but renderer
text is **“KEEL MIRROR · THE SHAPE OF THE LOCAL APP, IN YOUR BROWSER” /
“PUBLIC MIRROR · NO BACKEND”** — visibly distinct from legacy. Both HTML titles are
identically `Keel — Desktop & Code`, so the mirror badge text is the discriminator.
No Next child. Screenshot `evidence/electron-exe-2026-11-25T15-19-23-069Z.png`.

### 3.6 Default launch — source/EXE mismatch (`15:20:50Z`, `qa-logs/electron-exe-2026-11-25T15-20-50-500Z.json`)

With **no** env override the EXE loaded legacy (`http://127.0.0.1:49998/?t=…`,
`Keel — Desktop & Code`). Verified cause:
`@electron/asar.extractFile(app.asar,'renderer-policy.js')` contains
`DEFAULT_RENDERER = RENDERER_MODES.LEGACY`, while the source now contains
`DEFAULT_RENDERER = RENDERER_MODES.UNIFIED`. The EXE was built before the owner's
cutover. Explicit `KEEL_RENDERER=unified` still works in that EXE (§3.3). D-G7.
Screenshot `evidence/electron-exe-2026-11-25T15-20-50-500Z.png`.

### 3.7 Final definitive probes on the rebuilt cutover EXE (`15:24–15:26Z`) `[PE]`

Build under test: installer SHA-256
`B25C0977DE6491DFF886A9AF4C747F96E7A0D27061FF525E1AC9A9412644BC58`;
`app.asar` policy constant verified as `DEFAULT_RENDERER = RENDERER_MODES.UNIFIED`.

**1. Default launch, no renderer override — PASS**
```
cd keel/fleet-next
node tests/packaged-qa/electron-probe.mjs exe
```
`qa-logs/electron-exe-2026-11-25T15-24-07-079Z.json`:
window **`http://127.0.0.1:58530/`** (no `?t=`), title **`Keel — Unified Workspace`**.
Packaged Next child PID 48484 (parent 18076) running
`Keel.exe …resources\fleet-next\server.js` and listening **only**
`TCP 127.0.0.1:58530`; bundled sidecar PID 17300 (parent 18076).
`afterCloseChildren` for both PIDs: `[]`; `nonLoopbackListeners: []`; `errors: []`.
Screenshot `evidence/electron-exe-2026-11-25T15-24-07-079Z.png`.

**1b. Extended default launch (token/surface/BFF audit) — PASS**
```
node tests/packaged-qa/electron-probe.mjs exe KEEL_QA_UI_CHECK=1 KEEL_QA_CDP_PORT=9349
```
`qa-logs/electron-exe-2026-11-25T15-25-40-221Z.json`: window
`http://127.0.0.1:58454/`, title `Keel — Unified Workspace`;
BFF `/api/bridge/bots` → **HTTP 200** real bot JSON, `tokenInBody: false`;
surfaces Cowork, Code, Duet, Fleet, Capabilities, Settings;
token scan over `/` HTML + 7 JS chunks (real sidecar token) → `anyLeak: false`;
renderer `localStorage` only layout keys (`keel-sidebar-width`,
`keel-right-width`, `keel-sidebar-open`), `sessionStorage` `{}`,
HTML token regex false; Next child PID 28016 (parent 43912) present while running,
absent after close. Screenshots
`evidence/electron-exe-2026-11-25T15-25-40-221Z.png` and
`electron-exe-surface-*‑2026-11-25T15-25-40-221Z.png`.

**2. Explicit legacy rollback — PASS**
```
node tests/packaged-qa/electron-probe.mjs exe KEEL_RENDERER=legacy KEEL_QA_CDP_PORT=9346
```
`qa-logs/electron-exe-2026-11-25T15-24-38-876Z.json`: window
`http://127.0.0.1:51505/?t=…`, title **`Keel — Desktop & Code`**,
Next child list empty; bundled sidecar tree absent after close.
Screenshot `evidence/electron-exe-2026-11-25T15-24-38-876Z.png`.

**2b. G5 explicit mirror remains explicit-only — PASS**
```
node tests/packaged-qa/electron-probe.mjs exe KEEL_UI_PROFILE=mirror KEEL_QA_CDP_PORT=9347
```
`qa-logs/electron-exe-2026-11-25T15-25-09-938Z.json`: renderer text contains
**“PUBLIC MIRROR · NO BACKEND”** and “KEEL MIRROR · THE SHAPE OF THE LOCAL APP,
IN YOUR BROWSER”; no Next child; not reachable without the switch (default is
unified, legacy needs explicit `KEEL_RENDERER=legacy`).
Screenshot `evidence/electron-exe-2026-11-25T15-25-09-938Z.png`.

**3. Source suites on the final tree — PASS**
`node --test ../desktop-app/tests/renderer-policy.test.js` → 30/30;
`npx playwright test --config tests/packaged-qa/playwright.config.ts` → 9/9;
`npx tsc --noEmit -p tsconfig.json` → clean.

---

## 4. Browser tests `[B]`

The BFF and token-leak checks in §2.2/§3.3 ran inside the Electron renderer over CDP
against the real Next server and real Python bridge — stronger for this task than a
standalone browser run. I did **not** independently re-run the repository's other
browser E2E suites; those results belong to other agents.

---

## 5. Blocked / not run `[X]`

| Check | Why |
|---|---|
| Signed installer / Authenticode + updater signature path | Only the unsigned-built installer artifact was hashed and unpacked EXE launched; no signing certificate or trust-store verification was performed. |
| OS-level PWA install | No installed PWA window on a real OS; browser-only site tests belong to another agent. |
| Live provider turn | No provider credentials; setup checklist still shows “Connect a provider”. Read-only BFF round-trip verified; no model turn. |
| Source-map token scan | Production chunks contain no `sourceMappingURL`; nothing to scan. Packaging excludes `*.map` and `.env*`. |
| `shell.openExternal` actually launching the OS browser | CDP proves no new Electron target; the external process launch was not intercepted. Source uses `shell.openExternal` (`main.js:628`). |
| Tauri | Out of scope (`frontendDist: ../ui`). |
| macOS / Linux packaged GUI | No artifacts on this host. |

---

## 6. Defect log and retest status

| ID | Severity | Owner | File:line / artifact | Finding | Status |
|---|---|---|---|---|---|
| D-G1 | High (was G4 blocker) | Agent B/C packaging | `dist/win-unpacked/{Keel.exe,resources/fleet-next}` | No unified package existed; only legacy EXE. | **VERIFIED FIXED** — §3.3/§3.4 packaged launches. |
| D-G2 | Medium (was build ordering) | Agent C | `fleet-next/.next/standalone/{.next/static,public}`, consumed by `main.js:360-364` | Plain standalone lacked static/public overlay → “runtime is incomplete”. | **VERIFIED FIXED** — overlay + inventory exist; `[ED]` retest `14:55:50Z` against real standalone passed. |
| D-G3 | Low (doc drift) | Agent F / docs owner | `docs/UNIFIED-DESKTOP-INTEGRATION.md:106` | Says `KEEL_UI_DIR` “currently overrides even unified selection”; code (`renderer-policy.js:205-220`) ignores it; 30/30 unit cases pass. | **OPEN** - documentation only. |
| D-G4 | High (was) | Agent F (fix landed) | old `main.js:260` / `desktop/ui/app.js:75-84`; fixed at `main.js:441,672-676` | Baseline token in renderer URL + `sessionStorage`. | **VERIFIED FIXED** in `[ED]` and `[PE]`: token-free URL, empty sessionStorage, 0 leaks across HTML + 7 JS chunks. Legacy/mirror intentionally keep `?t=`. |
| D-G5 | Info (stale audit table) | Agent A / docs owner | `docs/RENDERER-INTEGRATION-CONTRACT.md:382-396` | §9 “observed divergences” were all fixed in the code tested. | **CLOSED as stale** — not current defects. |
| D-G6 | **Critical in first package** | Agent B/C packaging | `dist/win-unpacked/resources/fleet-next/node_modules` (absent at 15:10Z) | Packaged server failed `Cannot find module 'next'`; branded failure screen; one automatic retry also failed. | **VERIFIED FIXED** — second rebuild shipped 1,994 traced files; §3.3 packaged BFF 200. |
| D-G7 | Medium (was release consistency) | Lead / packaging owner | `app.asar` → `renderer-policy.js:46`; source `renderer-policy.js:46` | An intermediate EXE defaulted to legacy after the source cutover. | **VERIFIED FIXED** — final cutover EXE (`D52DB523…`, installer `B25C0977…`) has packaged `DEFAULT_RENDERER = UNIFIED` and the default launch in §3.7 loads the token-free unified window. |

---

## 7. Exact commands and results index

| Command | Result |
|---|---|
| `npx playwright test --config tests/packaged-qa/playwright.config.ts` | first run 5/4 against pre-integration source; final **9 passed / 0 failed** (1.7 s) |
| `node tests/packaged-qa/prepare-unified-runtime.mjs` | `…/tests/packaged-qa/tmp/unified-runtime` |
| `node tests/packaged-qa/electron-probe.mjs dev` | `http://127.0.0.1:10097/?t=…`, `Keel — Desktop & Code` |
| `node tests/packaged-qa/electron-probe.mjs exe` (pre-rebuild ×2) | old title, bundled sidecar trees killed |
| `node tests/packaged-qa/electron-probe.mjs exe KEEL_RENDERER=unified KEEL_QA_UI_CHECK=1` | `http://127.0.0.1:57613/`, `Keel — Unified Workspace`, BFF 200, 6 surfaces, 0 leaks, loopback-only, both children stopped |
| `node tests/packaged-qa/electron-probe.mjs exe KEEL_RENDERER=unified KEEL_QA_CDP_PORT=9345` | unique CDP port: `http://127.0.0.1:57831/`, clean pass |
| `node tests/packaged-qa/electron-probe.mjs exe KEEL_RENDERER=unified` (literal, `15:22:23Z`) | `http://127.0.0.1:56024/`, `Keel — Unified Workspace`, Next PID 3168 + sidecar PID 41144, both stopped on close |
| `node tests/packaged-qa/electron-probe.mjs exe KEEL_RENDERER=legacy KEEL_QA_CDP_PORT=9346` | `http://127.0.0.1:55367/?t=…`, old renderer, no Next child |
| `node tests/packaged-qa/electron-probe.mjs exe KEEL_UI_PROFILE=mirror KEEL_QA_CDP_PORT=9347` | mirror badge text, no Next child |
| `node tests/packaged-qa/electron-probe.mjs exe` (default, :9348) | legacy URL — packaged `app.asar` still has LEGACY default (D-G7) |
| `node tests/packaged-qa/lifecycle-probe.mjs failure` / `single` | branded failure; second instance exit 0, children unchanged |
| `node tests/packaged-qa/electron-probe.mjs exe` (final EXE, no override) | `http://127.0.0.1:58530/`, `Keel — Unified Workspace`, Next PID 48484 + sidecar PID 17300, both stopped, loopback-only |
| `node tests/packaged-qa/electron-probe.mjs exe KEEL_QA_UI_CHECK=1 KEEL_QA_CDP_PORT=9349` | BFF 200, 6 surfaces, 0 token leaks, empty sessionStorage, child stopped |
| `node tests/packaged-qa/electron-probe.mjs exe KEEL_RENDERER=legacy KEEL_QA_CDP_PORT=9346` (final EXE) | `http://127.0.0.1:51505/?t=…`, old renderer, no Next child |
| `node tests/packaged-qa/electron-probe.mjs exe KEEL_UI_PROFILE=mirror KEEL_QA_CDP_PORT=9347` (final EXE) | “PUBLIC MIRROR · NO BACKEND” badge, no Next child |
| `node --test ../desktop-app/tests/renderer-policy.test.js` | **30 passed / 0 failed** |
| `npx playwright test --config tests/packaged-qa/playwright.config.ts` (final) | **9 passed / 0 failed** (1.5 s) |
| `npx tsc --noEmit -p tsconfig.json` | clean (no output) |

Raw JSON logs and screenshots: `fleet-next/tests/packaged-qa/{qa-logs,evidence}/`.

---

## 8. Final verdict

- **Source integration `[S]`:** **PASS** — 9/9 packaged-qa static contracts,
  30/30 renderer-policy units, root `tsc --noEmit` clean.
- **Electron development `[ED]`:** **PASS** — real Python bridge + real Next BFF,
  token-free unified renderer, six destinations, both children stopped, single
  instance, branded failure screen, loopback-only binds.
- **G4 packaged EXE `[PE]`:** **VERIFIED** on the final cutover build
  (`Keel.exe D52DB523…`, installer `B25C0977…`). Default launch loads the token-free
  `http://127.0.0.1:<port>/` unified Fleet Next shell; packaged Next child runs on
  loopback and is killed with the Python sidecar on close; no bridge token in
  HTML/JS/localStorage/sessionStorage; BFF returns real bridge data.
- **G6 rollback `[PE]`:** **VERIFIED** — explicit `KEEL_RENDERER=legacy` loads the old
  full `desktop/ui` renderer with no Next child.
- **G5 mirror `[PE]`:** **VERIFIED** — `KEEL_UI_PROFILE=mirror` still shows the
  visibly constrained mirror badge and remains explicit-only.
- **Retested and closed:** D-G1, D-G2, D-G4, D-G6, D-G7. **Still open:** D-G3
  (documentation drift only: `docs/UNIFIED-DESKTOP-INTEGRATION.md:106` wrongly says
  `KEEL_UI_DIR` overrides unified).
- **Not tested `[X]`:** signed-installer/Authenticode trust path, live provider turn
  (no credentials), OS-level PWA install, Tauri, macOS/Linux GUI, external browser
  process launch itself, source maps (none emitted). No production-readiness claim
  beyond the evidenced gates.
