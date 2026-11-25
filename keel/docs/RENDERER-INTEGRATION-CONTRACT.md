# Unified Desktop Renderer — Implementation Architecture & Integration Contract

**Status:** architecture proposal, source-evidence based (READ-ONLY audit of worktree
`C:\Users\Admin\Desktop\keel-frontend-worktree`, branch
`feat/unified-renderer-electron-2026-11-25`, base `bcc9123`). No packaged GUI, native
build or live-provider turn was run for this audit. Every claim below is tied to a
file:line citation; anything not evidenced is labelled as a requirement, not a fact.

**Audience:** the agents that implement the Electron/Next integration. This document
is the contract they implement against. It does **not** change the renderer default
by itself (see `UI-ARCHITECTURE.md:83`: default cutover must be a separate coordinated
branch after G1–G6).

---

## 0. Decision summary

| Question | Decision |
|---|---|
| How to run Fleet Next in Electron | **Next standalone server**, not static export. Add `output: "standalone"` to `next.config.mjs`; ship `.next/standalone` + `.next/static` + `public`; spawn `server.js` with Electron-as-Node (`process.execPath` + `ELECTRON_RUN_AS_NODE=1`). |
| How the Python token reaches the Next server | Electron parses the token from the sidecar's printed URL and sets `KEEL_BRIDGE_URL` / `KEEL_BRIDGE_TOKEN` **in the Next child's env only**. Never a `NEXT_PUBLIC_*` var, never a renderer URL query param. BFF injects `x-keel-token` server-side. |
| Binding / port | `HOSTNAME=127.0.0.1` (standalone default is `0.0.0.0`), OS-chosen `PORT`, obtained by reserve-then-release on loopback; Python sidecar uses `--port 0` and reports its real bound port in its printed URL. |
| Ready signal | Python: existing stderr regex. Next: **HTTP poll** of `GET /` until 200 (standalone `server.js` has no stable ready line). Both with 30 s timeout and child-exit listeners. |
| Renderer choice | New pure module `desktop-app/renderer-policy.js`: `resolveRenderer({ resourcesPath, env }) -> { mode, uiDir, reason }`. `KEEL_RENDERER=unified\|legacy\|mirror`; `KEEL_UI_PROFILE=mirror` kept as diagnostic alias. Safe default `legacy` until gates pass; flip one constant for cutover. |
| Lifecycle | Single-instance lock unchanged; start sidecar → obtain URL/token → (unified) start Next → poll ready → load window. Central `stopSidecar()` mirrored by `stopRendererServer()` on every exit path. |

---

## 1. Running Fleet Next inside Electron

### 1.1 Standalone output is mandatory; static export is impossible

The BFF is a **server route**, not a static asset:

- `fleet-next/app/api/bridge/[...path]/route.ts:6-7` — `export const dynamic = "force-dynamic"; export const runtime = "nodejs";`
- `route.ts:9-10` — reads `KEEL_BRIDGE_URL` / `KEEL_BRIDGE_TOKEN` from server env at module load.
- `route.ts:34` — `headers.set("x-keel-token", BRIDGE_TOKEN)` is injected **server-side**.
- `route.ts:44-95` — SSE is proxied through raw `node:http`/`node:https` with `Readable.toWeb`; `fetch`/undici deliberately avoided because an upstream stream drop kills the Next server (`route.ts:38-43`).
- `route.ts:98-133` — generic proxy uses Node `fetch` with `redirect:"manual"`, `cache:"no-store"` and forwards upstream status/headers.

A `next export`/static build (a) cannot host a Node runtime route, (b) would expose the
token if it were moved into browser code, and (c) cannot hold a long-lived SSE pipe.
The repo's own assertion already records this: `desktop-app/scripts/assert-ui-entrypoints.js:184-188`
checks `fleet-next is NOT a static export (needs a Next server + BFF)`.

**Required build change:** add `output: "standalone"` to `fleet-next/next.config.mjs`
(the current config at `next.config.mjs:5-38` has no `output` key). Keep
`outputFileTracingRoot` at the fleet-next folder (`next.config.mjs:11-12`) so traced
dependencies stay local to this app.

**Required build sequencing:** `npm ci && npm run build` in `keel/fleet-next` with
`KEEL_DIST_DIR` **unset**. `next.config.mjs:10` makes the output directory configurable;
QA builds use `.next-e2e` (`fleet-next/playwright.config.ts:53`) and many other
`.next-*` trees exist in the source tree — packaging must copy from the plain `.next`.
Assert the three source paths exist before electron-builder runs.

### 1.2 Files that must be shipped

| Source (after build) | Packaged destination | Why |
|---|---|---|
| `fleet-next/.next/standalone/**` | `<resources>/fleet-next/**` | Contains `server.js`, a traced `node_modules` subset, `package.json` and `.next/server`. This is the runnable server. |
| `fleet-next/.next/static/**` | `<resources>/fleet-next/.next/static/**` | Standalone output deliberately omits static chunks; without them pages 404. |
| `fleet-next/public/**` | `<resources>/fleet-next/public/**` | Manifest icons, `icon.svg`, `icon-192/512.png` referenced by `app/manifest.ts:13-17`. |

Copy order matters: copy standalone first, then overlay `.next/static` and `public`
into the destination. Do **not** ship `.env.local` (the file exists in the worktree;
`.env.example:1` explicitly warns never to commit the token) or any `tests/` tree.

### 1.3 Node runtime inside a packaged Electron app

There is no separate system Node in a packaged app (`desktop-app/package.json:115`
shows `dependencies: {}`; `npmRebuild: false` at `:110`). Two options:

1. **Recommended — reuse Electron as Node:** spawn `process.execPath` with
   `ELECTRON_RUN_AS_NODE=1` and args `[join(nextDir, "server.js")]`. `process.execPath`
   is the Electron binary in both `electron .` dev and packaged mode; the env var makes
   it a plain Node host. This avoids shipping and version-pinning a second runtime.
   Set the variable **only in the child env**, never in the main process.
2. Alternative — add a pinned `node.exe`/`node` binary as an extraResource and use it.
   Only choose this if G4 proves option 1 fails with the pinned Electron/Next versions.

Verify option 1 early in G4 with a one-line probe (run the packaged binary with
`ELECTRON_RUN_AS_NODE=1 -e "console.log(process.version)"`). Add an `error` listener to
the spawned child — `main.js:207-209` already demonstrates the pattern for the advisory
update child; an unhandled spawn `error` crashes the whole shell.

### 1.4 Loopback binding and dynamic port

- **Binding:** Next's generated standalone `server.js` binds `process.env.HOSTNAME`
  and defaults to `0.0.0.0`. The Next child env **must** set `HOSTNAME=127.0.0.1`.
  (If implementers choose `next start` instead of standalone, pass `-H 127.0.0.1`.)
  Evidence of the loopback-only product requirement: `webapp.py:20`,
  `fleet-next/README.md:98`, `desktop-app/main.js:266-280`.
- **Port selection:** acquire a free loopback port by opening
  `net.createServer().listen(0, "127.0.0.1")`, reading `address().port`, and closing.
  Pass it as `PORT` to the Next child. Do **not** use `PORT=0`: the standalone server
  would bind an ephemeral port without reporting it, so the Electron parent could
  never construct the load URL. Retry the reserve-and-spawn once on an early exit
  (port race) before failing. Optional explicit override for tests:
  `KEEL_RENDERER_PORT` (integer); default = OS-selected.
- **Python sidecar:** replace the random 8700–10700 guess at `main.js:136` with
  `--port 0`. `cli/main.py:138-148` accepts any integer, `webapp.py:468-469` documents
  `Port 0 = ephemeral`, and `webapp.py:1694-1697` prints the **bound** port in the URL,
  which `waitForSidecarUrl` already parses (`main.js:106-123`). This removes the
  choose-a-port / bind-a-port race.

### 1.5 Ready detection

| Child | Signal | Evidence / requirement |
|---|---|---|
| Python sidecar | stderr line `keel webapp running at <url>`; validate `http:`, hostname `127.0.0.1`, non-empty `t` param | printed at `webapp.py:1695-1700`; parsed and validated at `main.js:84-132` (reuse unchanged). |
| Next standalone | **HTTP poll** `GET http://127.0.0.1:<nextPort>/` until status 200, then optional BFF probe `GET /api/bridge/bots` (expect JSON body, any status — 502 means "server up, bridge env missing", 404 means wrong server) | `next start`/`next dev` print a Ready line; generated standalone `server.js` does not emit a stable one. Do not add a stdout-regex dependency. Poll every 100 ms with a 30 s deadline; reject if the child exits first. Reuse the log tee from `main.js:166-175` but give this child its own log stream to avoid interleaving. |

The window loads only after **both** children are ready. No `?t=` on the unified URL:
the Next origin is tokenless and the BFF holds the credential.

---

## 2. Token hand-off: Python sidecar → Next server (server-side only)

**Data flow (all on the Electron main process / loopback):**

1. Electron generates `sidecarToken = randomBytes(18).toString("base64url")` (`main.js:135`)
   and passes it to the sidecar as `KEEL_TOKEN` (`main.js:139`). The sidecar's `_TOKEN`
   is exactly that value (`webapp.py:80`).
2. The sidecar prints `http://127.0.0.1:<boundPort>/?t=<token>` (`webapp.py:1695-1697`).
   `waitForSidecarUrl` parses it and `whenReady` extracts port and token (`main.js:299-302`).
3. For unified mode, build the Next child env as:

   ```js
   {
     ...process.env,
     HOSTNAME: "127.0.0.1",
     PORT: String(nextPort),
     KEEL_BRIDGE_URL: `http://127.0.0.1:${sidecarPort}`, // base only — no ?t=
     KEEL_BRIDGE_TOKEN: sidecarToken,                    // bare token, decoded
     NODE_ENV: "production",
     NEXT_TELEMETRY_DISABLED: "1",
     ELECTRON_RUN_AS_NODE: "1",
   }
   ```

4. The BFF reads these at module load (`route.ts:9-10`), checks both are non-empty
   (`route.ts:12-14`, else HTTP 502 `bridge_unavailable` at `:137-142`), appends
   `/api/fleet/<path>` (`route.ts:98-101`), and injects `x-keel-token` server-side
   (`route.ts:34` for normal requests, `:59-62` for SSE).

**Non-negotiables:**

- Never define `NEXT_PUBLIC_KEEL_BRIDGE_URL` / `NEXT_PUBLIC_KEEL_BRIDGE_TOKEN`: any
  `NEXT_PUBLIC_*` value is inlined into the browser bundle by Next.
- Never put the bridge token in the `BrowserWindow.loadURL` for unified mode; put it
  only in the child process env. Legacy/mirror mode keeps `?t=<token>` because there
  the browser talks directly to Python (`main.js:260`, `webapp.py:601-613`).
- Validate the parsed token against `^[A-Za-z0-9_-]+$` before injecting, and log only
  its length/first 4 characters (sanitised), never the value.
- Do not forward browser cookies or Origin upstream. BFF already deletes `cookie`,
  `origin`, `referer` (`route.ts:23-33`); Python's origin gate treats a missing Origin
  as allowed (`webapp.py:493-499`), which is correct for a server-to-server hop.
  If a future edit forwards Origin, all non-GET BFF calls will be refused.
- The Python token can be rotated at runtime (`webapp.py:450-454`, invoked at `:1096`).
  Because BFF env is read once (`route.ts:9-10`), a rotation makes the Next child's
  token stale. Contract: **do not rotate from Electron**; if a rotation is detected
  (repeated 403 from BFF), surface the honest "bridge not configured/restart needed"
  state and offer a renderer restart. Never silently retry with a guessed token.

---

## 3. Startup / shutdown lifecycle

**Startup (all inside the existing `app.whenReady()` at `main.js:295-314`):**

1. `app.requestSingleInstanceLock()` stays as-is (`main.js:290-293`); the `second-instance`
   handler only focuses the window (`:283-288`). A second instance must never spawn
   a second sidecar or Next server.
2. Create splash (`:296-297`).
3. `const policy = resolveRenderer({ resourcesPath: process.resourcesPath, env: process.env })`.
   Log `policy.mode` + `policy.reason` (no secrets) to the userData log.
4. `const sidecarUrl = await startSidecar()` (`:134-177`, with the `--port 0` change).
5. If `mode === "unified"`: start Next child with §2 env, wait for HTTP ready (§1.5),
   then `mainWindow.loadURL(\`http://127.0.0.1:${nextPort}/\`)`.
   If `mode === "legacy" | "mirror"`: keep the existing
   `loadURL(\`http://127.0.0.1:${sidecarPort}/?t=${sidecarToken}\`)` (`main.js:260`).
6. `checkForUpdates()` (`:185-223`) and `splash.close()` (`:305`) unchanged.

**Shutdown:**

- Generalise `stopSidecar()` (`main.js:24-47`) into a single stop function used for both
  children, keeping the Windows `taskkill /PID <pid> /T /F` tree kill (`:33-40`) and
  POSIX `SIGTERM` (`:42`). Next standalone is a plain Node process, so `proc.kill()`
  works on all platforms, but using the same helper gives one code path and the same
  pid-nulling/guard semantics (`:29-31`).
- Every exit path must stop **both** children: window `closed` (`:261-264`),
  `window-all-closed`/`before-quit` (`:316-320`), and the startup-failure branch
  which calls `app.exit(1)` and therefore bypasses `before-quit` (`:306-313`).
  Order: close window → stop Next child → stop sidecar.
- Keep `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`,
  `preload: undefined` (`main.js:252-257`) and the `setWindowOpenHandler` loopback
  allow / external-open / non-http deny policy (`main.js:266-280`). The Next window
  opens no `file:`/`javascript:`/`data:` URLs.

**Failure handling:**

- Spawn `error`, child `exit` before ready, and ready-timeout all reject the same
  startup promise; catch at `:306-313` → close splash → stop both children →
  `dialog.showErrorBox("Keel failed to start", …)` → `app.exit(1)`.
- If the Next child exits *after* the window is loaded, log the exit, show one
  error dialog, and do not silently switch renderers. A mode change is a deliberate
  startup policy decision (§4), not an invisible runtime fallback.
- BFF 502/504 is reported honestly by the UI (`UI-BACKEND-CONTRACT.md:25`,
  `lib/client.ts:52-66`); the Electron shell must not manufacture a "connected" state.

---

## 4. Renderer selection contract

### 4.1 New module

Create `keel/desktop-app/renderer-policy.js` — a **pure Node module** (only `path` and
`fs.existsSync`; no `electron` import) so it can be unit-tested exactly like
`desktop-app/scripts/test-ui-root.js:21-46` extracts and exercises `uiRoot()`.

```
resolveRenderer({ resourcesPath, env }) -> { mode: "unified" | "legacy" | "mirror",
                                             uiDir: string | null,
                                             reason: string }
```

Semantics of `uiDir`: for `unified` it is the **standalone Next root** (the directory
containing `server.js`, with `.next/static` and `public` beneath it); for `legacy` /
`mirror` it is the static UI root containing `index.html`; `null` means "no local
asset root — let the frozen sidecar serve its bundled `desktop/ui`"
(`main.js:66-67,81`; `sidecar.spec:26-31`). Consumers must interpret `uiDir` by `mode`.

### 4.2 Environment variables and defaults

| Variable | Values | Default | Notes |
|---|---|---|---|
| `KEEL_RENDERER` | `unified`, `legacy`, `mirror` (case-insensitive, trimmed) | **`legacy`** in this integration branch; one constant `DEFAULT_RENDERER` flips to `unified` in the cutover | Explicit operator choice always wins. Invalid value → safe `legacy` + reason string; log a warning. |
| `KEEL_UI_PROFILE` | `mirror` | unset | Existing diagnostic alias (`main.js:64,72`). If `KEEL_RENDERER` is set, it wins and the reason notes the conflict. |
| `KEEL_UI_DIR` | absolute path with `index.html` | unset | Existing explicit static override (`main.js:70-71`). Honoured for `legacy`/`mirror`; **ignored for `unified`** so a static legacy dir cannot silently replace the Next app. |
| `KEEL_RENDERER_UNIFIED_DIR` | absolute path to standalone root | `<resourcesPath>/fleet-next` | Dev/packaging-test override, analogous to `KEEL_UI_DIR`; must contain `server.js`, `.next/static`, `public`. |
| `KEEL_RENDERER_PORT` | integer | OS-selected loopback port | Test/diagnostic override only (§1.4). |
| `KEEL_RENDERER_READY_TIMEOUT_MS` | integer | `30000` | Bounds both ready waits. |

**Why the default is `legacy`:** `UI-ARCHITECTURE.md:29-33,83` and
`UI-BACKEND-CONTRACT.md:150` state that `desktop/ui` remains the shipped renderer until
the parity/packaging gates pass and that no default cutover happens in this branch.
The integration is therefore implemented and *exercised* with `KEEL_RENDERER=unified`
during G4; flipping `DEFAULT_RENDERER` is a separate coordinated commit.

### 4.3 Resolution rules (precedence order; first match wins)

1. Explicit `KEEL_RENDERER` value in `{unified, legacy, mirror}` → that mode.
2. `KEEL_UI_PROFILE=mirror` (case-insensitive) → `mirror`, reason
   `"KEEL_UI_PROFILE=mirror diagnostic override"` (preserves `main.js:72-75`).
3. Otherwise `DEFAULT_RENDERER` (currently `legacy`), reason
   `"default renderer <mode>; set KEEL_RENDERER=unified to opt in"`.

Then apply the mode-specific asset check:

- `unified`: `uiDir = env.KEEL_RENDERER_UNIFIED_DIR || join(resourcesPath, "fleet-next")`.
  Accept only if `existsSync(uiDir/server.js) && existsSync(uiDir/.next/static) &&
  existsSync(uiDir/public)`; otherwise fall back to `legacy` with reason
  `"unified build incomplete at <uiDir>; using legacy"`. (If no legacy root exists
  either, return `legacy` with `uiDir: null` and explain that the sidecar's bundled
  UI will be used.)
- `legacy`: `uiDir = env.KEEL_UI_DIR` if it has `index.html`, else first existing of
  `join(resourcesPath, "desktop", "ui")`, `join(resourcesPath, "ui")`
  (`main.js:76-80`), else `null`. Reason names the chosen path or "sidecar-bundled".
- `mirror`: `uiDir = env.KEEL_UI_DIR` if it has `index.html`, else
  `join(resourcesPath, "site")` only if it has `index.html`; otherwise fall back to
  `legacy` with reason `"mirror assets missing; using legacy"`.

`main.js` must delegate all path selection to this function and then feed only
`legacy`/`mirror` roots into the sidecar as `KEEL_UI_DIR` (`main.js:147,152,161`).
A unified-mode `KEEL_UI_DIR` override from the user may be forwarded verbatim for
diagnostics but must not be derived from `policy.uiDir`.

---

## 5. Packaging resource mapping

Add to `desktop-app/package.json` `build.extraResources` (currently only `site`,
`desktop/ui`, `keel` at `:32-54`):

```json
{ "from": "../fleet-next/.next/standalone", "to": "fleet-next" },
{ "from": "../fleet-next/.next/static",     "to": "fleet-next/.next/static" },
{ "from": "../fleet-next/public",           "to": "fleet-next/public" }
```

Also add `renderer-policy.js` to `build.files` (currently `package.json`, `main.js`,
`splash.html` only at `:27-31`), otherwise the packaged shell cannot import it.

Notes / concerns:

- All Next assets go to `extraResources`, i.e. outside `app.asar`, so no ASAR unpack
  rules are needed and `process.resourcesPath` is stable (`main.js:50,69`).
- Keep the three existing entries unchanged: `desktop/ui` is the G6 rollback target,
  `site` the G5 mirror target, `keel` the PyInstaller sidecar.
- Ensure the packaging build step runs `npm ci && npm run build` in `fleet-next` with
  `KEEL_DIST_DIR` unset (§1.1) **before** electron-builder; otherwise `extraResources`
  silently copies stale/missing output.
- Native modules: `npmRebuild: false` (`package.json:110`) means electron-builder will
  not rebuild anything. Next 15's optional `sharp` native binaries appear in
  `fleet-next/package-lock.json` (many `@img/sharp-*`/`@img/sharp-libvips-*` platform
  packages). Output file tracing (`next.config.mjs:11-12`) is expected to place the
  correct platform subset in `.next/standalone/node_modules`, but G4 must assert the
  packaged tree contains a `sharp` binary for the target OS/arch (or prove it is not
  needed — no `next/image` usage was found in the TS/TSX sources). Do not ship
  `.env.local`, `tests/`, or dev-only build artifacts.
- Electron 42 is pinned at `desktop-app/package.json:117`; the Electron-as-Node
  runtime version therefore follows Electron, so Next/React must be validated against
  it in G4 (Next 15.1.6 / React 19 from `fleet-next/package.json:15-17`).
- Tauri is **out of scope**: `desktop/src-tauri/tauri.conf.json` `frontendDist` remains
  `../ui` (`assert-ui-entrypoints.js:151-159`). The unified renderer is Electron-only.

---

## 6. Gate-by-gate plan (G1–G6)

Gate definitions are from `UI-ARCHITECTURE.md:72-83`; current status from `:85-101`.
"Evidence" below is what the implementing agents must produce — not claims made here.

| Gate | Requirement for unified renderer | Evidence needed |
|---|---|---|
| **G1** — four surfaces in one shell | All four surfaces (Cowork, Code, Duet, Fleet) reachable from the Electron window, not only a standalone browser. | Existing browser E2E baseline (144 passed, `UI-ARCHITECTURE.md:92`) plus a packaged-Electron assertion: window load URL is the Next origin, each surface button leads to its real content (screenshots or CDP assertions). |
| **G2** — fleet parity vs classic | Re-run the parity matrix in unified mode; do not close documented gaps by assertion alone. | `UI-FEATURE-PARITY.md` reconciliation, `tests/features/fleet/` 20 passed baseline (`:93`); explicit note that rewind/export remain gaps. |
| **G3** — real bridge round-trip | End-to-end through **unified** mode: real sidecar + Next BFF, server-side token injection, SSE. | Spin up real `keel serve --port 0` with a generated token; assert `GET /api/bridge/bots` 200 with real data, unauthenticated direct Python `/api/fleet/bots` 403 (`webapp.py:501-519`), `GET /api/bridge/events` yields named `row` frames (`UI-BACKEND-CONTRACT.md:123-125`), token absent from browser bundle/network requests and from window URL. Live model turn remains blocked without provider credentials (`:147`) — keep it labelled. |
| **G4** — packaged entry assertion | Build the real package with fleet-next resources and launch it. | `node desktop-app/scripts/assert-ui-entrypoints.js --resources <unpacked-resources>` **after updating that script for the unified path**; packaged EXE launched; both child processes alive; `loadURL` is `http://127.0.0.1:<nextPort>/`; `netstat`/socket check shows **only** loopback binds; renderer-policy.js unit cases pass; Electron-as-Node probe passes; token absent from renderer. Current status is "not verified / external gate" (`UI-ARCHITECTURE.md:95`). |
| **G5** — public `/app` browser-only | No site/desktop-only capability leaks after the packaging change. | Re-run `tests/distribution-qa/02-pwa-journey.spec.ts` and `04-landing-regression.spec.ts`; `site/app.html` still carries the mirror badge (`assert-ui-entrypoints.js:106-107`); no `/app* → /download` rewrite. |
| **G6** — rollback retained | `KEEL_RENDERER=legacy` (and `KEEL_UI_PROFILE=mirror`) work in the packaged build. | Packaged launch with each env var → window loads sidecar URL with `?t=`, local-renderer title (not mirror), `/api/fleet/bots` 200, no Next child spawned; assertions updated in `assert-ui-entrypoints.js:179-190` so the new wiring is validated rather than forbidden. |

**Cutover:** only after G1–G6 are evidenced, flip `DEFAULT_RENDERER` in
`renderer-policy.js` in a separate coordinated branch, per `UI-ARCHITECTURE.md:83`.

---

## 7. Risks and blockers (with file:line evidence)

| # | Risk / blocker | Evidence | Mitigation |
|---|---|---|---|
| R1 | No standalone build exists yet; `next.config.mjs` has no `output` key, so there is no runnable server artifact to ship. | `fleet-next/next.config.mjs:5-38` | Add `output: "standalone"` (implementer task) and assert the three output dirs in the build step. |
| R2 | Static export is not an option — BFF needs a Node runtime, server-side token injection and a raw-HTTP SSE pipe. | `route.ts:6-10,34,44-95,98-133`; `assert-ui-entrypoints.js:184-188` | Standalone server; never move the token into client code. |
| R3 | BFF reads env once at module load; a Python token rotation silently invalidates the Next child. | `route.ts:9-10`; `webapp.py:450-454,1096` | No Electron-side rotation; detect repeated 403/502 and offer a diagnostic restart. |
| R4 | Standalone `server.js` binds `0.0.0.0` unless `HOSTNAME` is set — loopback-only guarantee would be lost. | Product rule at `webapp.py:20`, `fleet-next/README.md:98`, `main.js:266-280` | Set `HOSTNAME=127.0.0.1` in Next child env; assert in G4. |
| R5 | Existing port guess is racy; no dynamic Next port mechanism exists. | `main.js:136` (8700–10700 random); no standalone launcher in tree | `--port 0` for Python (accepted at `cli/main.py:138-148`; bound port printed at `webapp.py:1694-1697`), reserve-then-release for Next; retry once. |
| R6 | No stable stdout "ready" line for standalone server; waiting on logs would hang. | `main.js:84-132` relies on the Python stderr line only | HTTP poll of `/` + child-exit listeners + timeout. |
| R7 | Startup-failure path stops only the sidecar; a spawned Next child would be orphaned. | `main.js:24-47` (`stopSidecar`), `:306-313` (`app.exit(1)`) | One stop helper for both children on all exit paths. |
| R8 | A spawn `error` on the new child is fatal if unhandled. | `main.js:207-209` shows the established error-listener pattern | Attach `error`/`exit` handlers to the Next child. |
| R9 | Packaging `files` list omits any new `renderer-policy.js`, and `extraResources` omits fleet-next. | `desktop-app/package.json:27-54` | Add entries per §5; G4 asserts packaged paths. |
| R10 | Existing read-only QA scripts explicitly forbid fleet-next wiring and will fail after implementation. | `assert-ui-entrypoints.js:179-190` (`main.js` must not reference fleet-next, build config must not ship it); `test-ui-root.js:21-90` extracts `uiRoot()` from `main.js` | These must be **updated** in the implementing branch (G4/G6), not bypassed or deleted. Until then they are a blocking red gate. |
| R11 | Current `uiRoot()` / loadURL is legacy-only; unified mode needs a real branch before window creation. | `main.js:68-82,147,260` | Delegate to `resolveRenderer`; keep legacy branch byte-compatible. |
| R12 | Native `sharp` platform binaries may be missing from standalone trace under `npmRebuild:false`. | `package.json:110`; `package-lock.json` `@img/sharp-*` entries; `next.config.mjs:11-12` | G4 packaged-tree assertion; no `next/image` usage found in TS/TSX sources. |
| R13 | Browser Origin forwarded upstream would break all non-GET BFF calls. | `route.ts:30-33` (deletes origin); `webapp.py:493-499` (`_origin_ok`) | Keep the deletion; regression test in G3. |
| R14 | README references `.env.example`, which exists but is not shipped; docs drift could mislead packaging. | `fleet-next/README.md:16-17`, `.env.example:1-4` | Packaging never copies `.env*`; G4 asserts no token file in resources. |
| R15 | Live provider turn still unverified (no credentials); packaged GUI not yet run (no native build tools). | `UI-BACKEND-CONTRACT.md:147`; `UI-ARCHITECTURE.md:95` | Keep the honest blocked label; G3/G4 are explicit owner gates, not prose claims. |

---

## 8. Implementation checklist (for the implementing agents)

1. `next.config.mjs`: add `output: "standalone"`; keep `distDir`/`outputFileTracingRoot`.
2. New `desktop-app/renderer-policy.js` with the exact `resolveRenderer` signature; add
   unit tests mirroring `scripts/test-ui-root.js`.
3. `main.js`: branch startup on `policy.mode`; add `startRendererServer()`,
   `waitForRendererReady()`, `stopRendererServer()`; use `--port 0` for Python; keep
   all existing security window settings and single-instance logic.
4. `desktop-app/package.json`: add `renderer-policy.js` to `files`; add the three
   fleet-next `extraResources` entries; leave existing entries intact.
5. Update `scripts/assert-ui-entrypoints.js` and the distribution QA source-contract
   spec (`fleet-next/tests/distribution-qa/03-desktop-first-launch.spec.ts:61-76`) to
   assert the **new** contract rather than forbidding fleet-next.
6. Run G1–G6 with real evidence; do not flip `DEFAULT_RENDERER` until they pass.

No source, config, package, other doc, commit or push was made by this audit; the only
file created is this document.

---

## 9. Reconciliation log — concurrent in-flight implementation (observed after this audit)

While this contract was being written, other agents began implementing in the same
worktree. The following **observed divergences** must be reconciled before G4; they are
recorded here so the contract stays authoritative and no agent silently inherits a bug.

| Observed in-flight code | Contract expectation | Severity |
|---|---|---|
| `main.js` Next child env sets `HOST: "127.0.0.1"` (observed `main.js:371`) | Must set **`HOSTNAME=127.0.0.1`**. The generated standalone `server.js` literally contains `const hostname = process.env.HOSTNAME \|\| '0.0.0.0'` — see `fleet-next/node_modules/next/dist/build/utils.js:1316`. `HOST` is ignored by standalone output, so the child binds `0.0.0.0` and breaks the loopback-only guarantee. | **Critical — fix before G4** |
| `renderer-policy.js:228-246` defaults to `unified` whenever a runtime exists | Contract §4.2 defaults to `legacy` until G1–G6 pass (`UI-ARCHITECTURE.md:83`). Either change the policy default or record an owner-approved cutover. | High (governance) |
| `renderer-policy.js:146-152` lets `KEEL_UI_DIR` (with `index.html`) force `legacy` even when unified is requested | Contract §4.2: `KEEL_UI_DIR` is honoured only for `legacy`/`mirror`; it must not override `KEEL_RENDERER=unified`. | Medium |
| `renderer-policy.js:172-177` refuses `KEEL_RENDERER=mirror`; mirror only via `KEEL_UI_PROFILE=mirror` | Stricter than contract §4.1. Acceptable if documented, but §4.2 lists `mirror` as a valid `KEEL_RENDERER` value — pick one and align both places. | Low |
| `main.js:269-284` `nodeExecutable()` falls back to `"node"` on PATH; no `ELECTRON_RUN_AS_NODE=1` reuse of `process.execPath` | Contract §1.3 recommends Electron-as-Node so packaged apps work without a system Node. If a private Node runtime is shipped, it must be added to `extraResources` and version-pinned. | High (packaged runtime) |
| Env names `KEEL_FLEET_NEXT_DIR`, `KEEL_NODE`, `KEEL_RENDERER_FALLBACK` in flight | Contract §4.2 defines `KEEL_RENDERER_UNIFIED_DIR`; no `KEEL_NODE`/fallback var was specified. Align names in code and docs, or update §4.2 by owner decision. | Medium |
| `main.js:307-316` readiness probe accepts any HTTP response, including 404 | Contract §1.5 requires status 200 on `/` (then BFF probe). Accepting 404 can mask a missing `.next/static` / `public` overlay. | Low–Medium |
