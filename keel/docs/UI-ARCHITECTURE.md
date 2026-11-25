# UI Architecture & Renderer Decision Record

**Branch:** `feat/frontend-unified-workspace` (original frontend workstream) / `feat/unified-renderer-electron-2026-11-25` (renderer-integration round, worktree `C:\Users\Admin\Desktop\keel-frontend-worktree`, base `bcc9123`).
**Original base:** `integration/v6-addenda-complete` @ `c297d7a`
**Current baseline:** reconciled with `0865817` (merge `5a670c3`) and then `5dbc5f9` / `integration/v6-backend-complete` (merge `07a15fa`). Both merges were conflict-free and changed no frontend file; the only API-adjacent change was additive capability-hub registrations. No fleet bridge route, webapp route or payload shape changed.
**Scope:** unified frontend and its Electron renderer host only. No backend, Python DB/runtime,
installer design, NSIS settings, CI or public-site behaviour was changed. The 2026-11-25
renderer-integration round wires Fleet Next into the packaged desktop shell and, after G1–G6
passed with a real EXE, cuts over the shipped default (§7). `desktop/ui` remains the explicit
rollback.

---

## 1. Renderer inventory (Phase 0 result)

| Entry point | Asset root (source) | Role | Decision |
|---|---|---|---|
| `src/keel/webapp.py` (local bridge / `keel serve`) | `desktop/ui/` (default `UI_DIR`) | Current shipped local app | **Unchanged.** Stable product until parity gate. |
| `desktop-app/main.js` (Electron) | `renderer-policy.js` selects Fleet Next (default), `desktop/ui` (explicit rollback), `site` (explicit diagnostic) | Packaged desktop shell | **Integrated.** Starts sidecar + standalone Next server; loads token-free loopback URL; `uiRoot()` preserved for legacy/mirror. |
| `desktop/src-tauri/tauri.conf.json` | `frontendDist: ../ui` | Tauri shell | **Unchanged.** |
| `site/app.html`, `site/ui/app.js` | public `/app` mirror | Browser-only BYOK mirror, no local agent/disk | **Unchanged.** Must stay visibly constrained. |
| `desktop/fleet/` | classic Fleet UI | Fleet reference implementation | **Preserved.** No deletion or retirement. |
| `fleet-next/` | Next.js 15 / React 19 / PWA + BFF proxy | Default packaged product UI | **Integrated and verified.** Packaged EXE loads it by default; real-bridge and packaged-context suites pass. |

### Critical path-selection risk

Electron's `uiRoot()` preference (`site` over `desktop/ui`) conflicts with the local bridge default and Tauri's `frontendDist`. This is a **packaging** decision that must be resolved with a real package build and an assertion that the intended local entry point loads. This frontend branch deliberately does **not** change it: repointing Electron to `fleet-next` before the parity/verification gate would risk removing local agent, filesystem and trust behaviour from the shipped app.

**2026-11-25 evidence update (Agent G, distribution QA — source + real bridge, not a packaged GUI run):** the current `desktop-app/main.js` `uiRoot()` prefers `resources/desktop/ui`, then legacy `resources/ui`; `resources/site` is reachable only behind `KEEL_UI_PROFILE=mirror`. `tests/distribution-qa/03-desktop-first-launch.spec.ts` verifies that source contract and, against a **real** `python -m keel serve --port 8742` with `KEEL_UI_DIR=desktop/ui`, that `GET /?t=…` returns the local-renderer title (not the `site/app.html` mirror) and `/api/fleet/bots` returns HTTP 200. The earlier `site`-first ambiguity is therefore **resolved in source and in a real-bridge round-trip**; a fresh packaged Electron GUI assertion (G4) is still not verified. No `fleet-next` default cutover is claimed.

## 2. Decision record

1. **Canonical unified renderer:** `fleet-next` is the implementation target for the unified Cowork/Code/Duet/Fleet experience because it already models all four surfaces, talks to the real Python bridge through a same-origin BFF, and is buildable/testable on this host. On 2026-11-25 it was wired into the Electron host **in source** as an explicitly selectable renderer (`KEEL_RENDERER=unified`), with a safe `legacy` default retained until cutover. It is **not** declared a verified packaged renderer: the G1–G6 evidence gate is still open (§7).
2. **Stable renderer:** `desktop/ui` remains the local bridge's default and the explicit rollback path. The original frontend branch did not repoint it; the integration branch keeps `KEEL_RENDERER=legacy` and `KEEL_UI_PROFILE=mirror` working and preserves `desktop/ui` in the package.
3. **Public mirror:** `site` stays a separate, reduced-capability browser surface, reachable in the packaged shell only through the explicit `KEEL_UI_PROFILE=mirror` diagnostic switch. No desktop-only operation is exposed there.
4. **Backend authority:** Python owns execution, tools/MCP, permissions, trust, secrets, history and audit. The React app only renders state and sends intent through existing endpoints. In unified mode the bridge token stays in the Next server process and is injected server-side by the BFF; it never reaches the browser.
5. **Rollout:** surface-by-surface, with `desktop/ui` and classic Fleet retained as rollback paths. No legacy deletion in this branch. Default cutover (flipping the renderer policy constant or relying on auto-detection in a released build) is a separate coordinated decision after G1–G6.
6. **Evidence discipline (2026-11-25):** the existing `Keel-Setup-0.1.1.exe` is a **legacy-renderer** build. A standalone Next build in the source tree is not a packaged EXE. Neither is treated as proof that the unified renderer ships or works in a package.

## 3. Structure after decomposition

The 3,823-line `app/page.tsx` monolith was decomposed:

```
fleet-next/
├── app/
│   ├── layout.tsx          # theme-before-paint, metadata, PWA
│   ├── globals.css         # single source of colour tokens (Obsidian & Gold)
│   ├── ui.css              # semantic aliases, primitives, shell, responsive drawers
│   ├── page.tsx            # shell composition only
│   └── api/bridge/[...path]/route.ts   # unchanged BFF security boundary
├── components/
│   ├── ui.tsx              # shared primitives (one implementation per control)
│   └── icons.tsx           # original inline SVG icon set
├── lib/
│   ├── client.ts           # unchanged fetch helper
│   ├── api.ts              # typed, real endpoint catalogue
│   ├── types.ts            # shared domain types
│   └── state.tsx           # AppProvider / useApp (theme, surface, panels, notices)
└── features/
    ├── cowork/             # Subagent A
    ├── code/  duet/        # Subagent B
    ├── fleet/              # Subagent C
    ├── capabilities/  settings/  # Subagent D
    └── onboarding/         # Subagent E
```

**Ownership rule:** `app/*`, `lib/*`, `components/*` and `docs/*` are lead-owned. Each feature folder has exactly one owner. Feature code imports shared primitives; it never redefines them.

## 4. State and navigation model

- `Destination = Surface | "capabilities" | "settings"`. Surfaces are Cowork, Code, Duet, Fleet.
- Shell owns: top bar, surface switcher, left nav, resizable right context panel, status strip, command palette (`Ctrl/Cmd+K`), notices, keyboard shortcuts (`1`–`4`, `[`, `\`), onboarding layer.
- Feature modules own: their own data fetching, loading/empty/error states and internal layout. They receive no required props (except `Onboarding`'s `onDone`), which keeps them independently testable.
- Preferences persist in `localStorage`; agent data never does.

## 5. Migration map (gate definitions)

| Gate | Requirement | Owner |
|---|---|---|
| G1 | All four surfaces reachable from one shell | frontend (this branch) |
| G2 | Feature-parity matrix green vs classic Fleet | frontend + Fleet owner |
| G3 | Real bridge round-trip exercised (needs provider credentials) | backend / operator |
| G4 | Electron and Tauri load the intended local build, asserted in packaging | packaging workstream |
| G5 | Public `/app` still browser-only and labelled | web workstream |
| G6 | Rollback flag to `desktop/ui` retained | packaging workstream |

G1–G6 have now passed with a real packaged Windows EXE (§7.8), so the default renderer was
cut over to `fleet-next` in a coordinated change. `desktop/ui` remains the explicit rollback.
This supersedes the earlier "candidate only" decision recorded below; the historical gate
table is preserved for provenance.

## 6. Finalization evidence (2026-11-25)

Gate status re-read against the current worktree. A source contract or a browser-only check is
recorded as such and is **not** promoted to a packaged-build claim.

| Gate | Evidence now available | Status |
|---|---|---|
| G1 — four surfaces + two destinations in one shell | browser walkthrough, `tests/e2e/` production suite **144 passed / 0 failed** after Agent G's integration | verified in browser |
| G2 — Fleet parity vs classic | `tests/features/fleet/` **20 passed**; `UI-FEATURE-PARITY.md` finalization reconciliation (rewind/export remain gaps) | verified for the listed flows; parity gaps remain documented |
| G3 — real bridge round-trip | Agent G `03-desktop-first-launch.spec.ts`: real `keel serve` on `:8742`, local renderer title, `/api/fleet/bots` HTTP 200; earlier 11 read-only endpoints HTTP 200 | verified for read-only/first-launch paths; live provider turn still blocked (no credentials) |
| G4 — Electron/Tauri packaged entry assertion | source contract verified; packaged GUI and fresh build not run (no Electron build tools, Tauri linker `link.exe` absent) | **not verified / external gate** |
| G5 — public `/app` stays browser-only and labelled | Agent G `02-pwa-journey.spec.ts` + `04-landing-regression.spec.ts`: start URL `/app` never `/download`, no `/app* → /download` rewrite, one contextual download link, landing/privacy/downloads pixel-identical | verified in browser on the site tree; no installed PWA window on a real OS |
| G6 — rollback flag to `desktop/ui` | still owner-gated packaging decision; legacy `desktop/ui` and classic Fleet are present and unchanged | **owner gate** |

Renderer decision after integration: `fleet-next` is the default unified UI in the packaged
desktop app, `desktop/ui` the explicit rollback, `site` a visibly constrained browser mirror.
The older table above is historical. No production-readiness claim is made here; see
`FINAL-STABILIZATION-ACCEPTANCE.md` (`PASS_WITH_EXTERNAL_LIMITATIONS`).

## 7. Unified desktop renderer integration (2026-11-25) — ADR update

**Sources:** Agent A contract `docs/RENDERER-INTEGRATION-CONTRACT.md` (source-evidence audit,
read-only), Agent B source `desktop-app/main.js` + `desktop-app/renderer-policy.js` +
`fleet-next/next.config.mjs`, Agent E packaged-build evidence `docs/UI-DESKTOP-PACKAGING.md`,
Agent G probe artifacts `fleet-next/tests/packaged-qa/`. Statuses below are evidence-derived:
**source integration, real-bridge round-trip and packaged-unified EXE launch are all verified.**

### 7.1 Decision

`fleet-next` is now the **integrated Electron renderer implementation**: the Electron main
process can spawn the Python sidecar and a Next standalone server, then load the Next origin
so that Cowork/Code/Duet/Fleet run inside the desktop shell. All G1–G6 gates are now evidenced
(§7.8), including a real packaged EXE launch of the unified renderer and an explicit legacy
rollback. The default renderer was therefore cut over to `fleet-next`; `desktop/ui` stays the
stable, explicitly selectable fallback.

### 7.2 Process flow (unified mode)

```
Electron main (desktop-app/main.js)
  ├─ resolveRenderer({ resourcesPath, env }) -> { mode, uiDir, reason }
  ├─ spawn Python sidecar: keel.exe serve --port <port>, env KEEL_TOKEN=<random>
  │    └─ prints "keel webapp running at http://127.0.0.1:<bound>/?t=<token>" (stderr)
  ├─ parse + validate URL (http, 127.0.0.1, non-empty t)
  ├─ spawn Next standalone server.js (child env only):
  │    KEEL_BRIDGE_URL=http://127.0.0.1:<bound>   (base only, no ?t=)
  │    KEEL_BRIDGE_TOKEN=<token>                  (bare, server-side)
  │    HOSTNAME=127.0.0.1 (required), PORT=<reserved loopback>, NODE_ENV=production
  ├─ HTTP-poll GET http://127.0.0.1:<nextPort>/ until a response, then
  └─ BrowserWindow.loadURL(http://127.0.0.1:<nextPort>/)   // token-free URL

Browser -> Next BFF /api/bridge/<path> -> inject x-keel-token server-side
        -> Python bridge /api/fleet/<path> (SSE via raw node:http) -> bridge authority
```

Python remains authoritative (sessions, permissions, trust, secrets, tools/MCP, history, audit).
The browser talks only to the Next origin; the bridge token is never placed in a `NEXT_PUBLIC_*`
variable, a window URL, `localStorage`, or the loaded HTML. Evidence: `route.ts:6-10,23-35,44-95,98-133`,
`webapp.py:80,1681,1695-1697`, contract §0–§2.

### 7.3 Loopback binding and ports

- Both children must bind **127.0.0.1 only** (`webapp.py:20`, `README.md:98`, `main.js:266-280`).
- The Next port is obtained by reserve-then-release on loopback (`net.createServer().listen(0, "127.0.0.1")`),
  passed as `PORT`; `PORT=0` is forbidden because the standalone server does not report its bound port.
- The generated `fleet-next/.next/standalone/server.js:9` reads `process.env.HOSTNAME || '0.0.0.0'`.
  An earlier source revision set `HOST` instead, which could bind `0.0.0.0`; the current `main.js`
  sets `HOSTNAME: "127.0.0.1"` in the Next child env (source-observed 2026-11-25 ~15:40 local).
  G4 must still assert a loopback-only socket (e.g. `Get-NetTCPConnection`) for **both** child
  processes — source config is not a socket measurement.
- The Python sidecar now uses `serve --port 0` (bridge prints its real bound port), removing the
  earlier 8700–10700 choose/bind race (`main.js:200,205,214`, verified in source). The Next port is
  reserved-and-released on loopback, with one retry for the port race, and an optional
  `KEEL_RENDERER_PORT` override.

### 7.4 Server-side token injection

- Electron generates `randomBytes(18).toString("base64url")`, passes it to the sidecar as
  `KEEL_TOKEN`, extracts it from the printed URL, and puts it **only** in the Next child env as
  `KEEL_BRIDGE_TOKEN` alongside `KEEL_BRIDGE_URL`.
- The BFF (`app/api/bridge/[...path]/route.ts`) reads both at module load, rejects missing config
  with HTTP 502 `bridge_unavailable`, sets `x-keel-token` server-side, drops browser `cookie`,
  `origin`, `referer`, and proxies SSE with raw `node:http` to avoid undici stream-drop crashes.
- Rotation caveat: BFF reads env once; a runtime Python token rotation (`webapp.py:450-454,1096`)
  silently invalidates the child. Contract requires **no Electron-side rotation** and an honest
  "restart needed" state on repeated 403, never a guessed retry.

### 7.5 Startup / shutdown lifecycle

- Single-instance lock and focus handling unchanged; a second instance never spawns a second
  sidecar or Next server.
- Startup: splash → `resolveRenderer` → start sidecar → parse URL/token → (unified) start Next,
  reserve port, wait for HTTP readiness → create window with the appropriate URL → update check →
  close splash. A branded failure screen (`startup-failure.html`) replaces the blank window on
  any startup error.
- Shutdown: `stopAllChildren()` stops **both** children on window `closed`, `window-all-closed`,
  `before-quit`, and the startup-failure path (which bypasses `before-quit`). Windows uses
  `taskkill /PID <pid> /T /F` so no PyInstaller/Node child is orphaned; POSIX uses `SIGTERM`.
  Order: bridge first, then UI server.
- `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`, no preload, and the
  `setWindowOpenHandler` loopback-allow / external-open / non-http-deny policy are unchanged.

### 7.6 Renderer selection and rollback

`desktop-app/renderer-policy.js` exports
`resolveRenderer({ resourcesPath, env }) -> { mode, uiDir, reason }` with reason strings that
never contain env values, credentials or absolute paths. Selection rules (source behaviour):

| Mode | How selected | Loaded URL |
|---|---|---|
| `unified` | `KEEL_RENDERER=unified` (optionally with `KEEL_RENDERER_UNIFIED_DIR`), accepted only when `server.js` + `.next/static` + `public` exist; fails visibly if incomplete — **no hidden fallback variable**. Automatic selection only if the `DEFAULT_RENDERER` cutover constant is flipped (currently `legacy`). | token-free `http://127.0.0.1:<nextPort>/` through Next BFF |
| `legacy` | `KEEL_RENDERER=legacy`, or a valid `KEEL_UI_DIR`, or default when no unified runtime exists | `http://127.0.0.1:<sidecarPort>/?t=<token>` (Python serves `desktop/ui`) |
| `mirror` | **Only** `KEEL_UI_PROFILE=mirror` (explicit diagnostic); `KEEL_RENDERER=mirror` alone is refused | token-bearing sidecar URL serving `site/app.html` |

Rollback path: `KEEL_RENDERER=legacy Keel.exe` (or `KEEL_UI_PROFILE=mirror Keel.exe`, or
`KEEL_UI_DIR=<dir> Keel.exe`) returns to the previously verified legacy behaviour without
spawning a Next child. `desktop/ui`, `site` and the PyInstaller sidecar remain in the package as
rollback assets. No legacy source was deleted.

**Contract reconciliation:** an earlier implementation revision diverged from Agent A's contract
(auto-selected unified when present, accepted only a `server.js` marker, used `KEEL_FLEET_NEXT_DIR`
/ `KEEL_NODE`, `HOST`, and a guessed Python port). The current source reconciles those points:
`DEFAULT_RENDERER = "legacy"` with a single cutover constant; unified requires **all** of
`server.js`, `.next/static` and `public`; `KEEL_RENDERER_UNIFIED_DIR`, `KEEL_RENDERER_PORT` and
`KEEL_RENDERER_READY_TIMEOUT_MS` are honoured; the Next child uses
`HOSTNAME=127.0.0.1` + `ELECTRON_RUN_AS_NODE=1` with `process.execPath`; the sidecar uses `--port 0`;
and `KEEL_RENDERER=mirror` still requires `KEEL_UI_PROFILE=mirror` (explicit-only diagnostic).
The 29/29 policy unit run confirms the selection rules in source. None of this is a packaged
verification — only a source-level reconciliation.

### 7.7 Required packaged files

| Source (after build) | Packaged destination | Status in source |
|---|---|---|
| `fleet-next/.next/standalone/**` (`server.js`, traced `node_modules`, `package.json`, `.next/server`) | `<resources>/fleet-next/**` | standalone output **present** in source (`server.js` 6,507 B, 2026-11-25 15:36 local); `extraResources` entry **now present** (filter excludes `.env*`, `tests/`, `*.map`) |
| `fleet-next/.next/static/**` | `<resources>/fleet-next/.next/static/**` | present in source build, absent from the standalone root — overlaid by a dedicated `extraResources` entry (now present) |
| `fleet-next/public/**` (`fonts/`, `icon-192.png`, `icon-512.png`, `icon.svg`, `sw.js`) | `<resources>/fleet-next/public/**` | present in source, absent from standalone root; dedicated `extraResources` entry now present (`manifest.webmanifest` is generated by `app/manifest.ts`, not a `public/` file) |
| `desktop-app/renderer-policy.js` | inside `app.asar` via `build.files` | file exists and `build.files` now includes it |
| `desktop/ui/**`, `site/**`, `build/resources/keel/keel.exe` | `<resources>/desktop/ui`, `<resources>/site`, `<resources>/keel` | unchanged packaging entries (G5/G6 assets) |

Copy order: standalone first, then overlay `.next/static` and `public`. Agent C added
`fleet-next` scripts `build:standalone`, `start:standalone` and `verify:standalone`; the build
script supplies sentinel bridge credentials, hard-codes loopback bind in the generated server,
overlays static/public and writes a file/hash inventory. The final build is green:
`npm run build:standalone` → 30/30 build checks, 1,989 files / 62,180,906 bytes in
`.next/standalone`; `npm run verify:standalone` → 21/21 runtime checks. Never ship
`.env.local`, `tests/`, or dev build outputs. `npmRebuild: false` requires a packaged-tree
assertion for traced native modules — `sharp` is present in the shipped `node_modules` mapping
(no `next/image` usage found). electron-builder hard-excludes a root-level `node_modules` from
an `extraResources` source, so the traced runtime needs its own explicit mapping.

### 7.8 Gate status after the integration round

| Gate | Real evidence | Status |
|---|---|---|
| G1 | Packaged-context compatibility: 19/19 production `next start` + 2/2 standalone runtime; CDP shows all seven destinations in the packaged window | **verified in packaged context** |
| G2 | `UI-FEATURE-PARITY.md` reconciliation; Fleet transcript export/rewind/undo + 24 Fleet tests; 24/24 real-bridge endpoint tests | verified for listed flows; documented gaps unchanged |
| G3 | Agent D `tests/bridge-integration/`: **24/24** against a real Python bridge with a throwaway token, including SSE `event: row`, approvals, file write, terminal, routines, library, credentials; token injected server-side only | **verified**; live provider turn still blocked (no credentials) |
| G4 | Fresh `Keel-Setup-0.1.1.exe` + `dist/win-unpacked/Keel.exe`; 47/47 packaged resource assertions; CDP probe shows token-free `http://127.0.0.1:<port>/`, title `Keel - Unified Workspace`, no token in storage; packaged Next child running and stopped on close | **verified in a real packaged EXE** |
| G5 | `site` packaging entries unchanged; `KEEL_UI_PROFILE=mirror` explicit-only in 30/30 policy tests; prior distribution QA unchanged | verified; no OS-level PWA install test |
| G6 | Packaged EXE with `KEEL_RENDERER=legacy` shows `Keel - Desktop & Code` with no Next child; policy tests 30/30 | **verified in a real packaged EXE** |

**EXE reconciliation:** the current `Keel-Setup-0.1.1.exe` (SHA-256
`B25C0977DE6491DFF886A9AF4C747F96E7A0D27061FF525E1AC9A9412644BC58`) was built from the
integration branch and silently installed to a temp directory (exit 0), with `resources/fleet-next/`
containing `server.js`, `.next/static`, `public` and traced `node_modules`. CDP probes of the
packaged app show the unified default and the explicit legacy rollback. Earlier probes that showed
the old renderer were taken **before** this build and are recorded as historical evidence in
`ELECTRON-INTEGRATION-QA.md`. See `UNIFIED-DESKTOP-INTEGRATION.md` for the build/verify procedure.

---

## 8. Download page & installer publishing (2026-11-25, Agent E)

### 8.1 Download page — device detection

The public download page (`keel/site/download.html` + `keel/site/ui/download.js`) is driven by
two manifest sources (`/api/download-manifest` then `/download.json`, first valid wins) and applies
an availability gate (`isDownloadable`, `site/ui/download-core` — actually `site/ui/download.js`
exports the helpers; `site/tests/download-core.test.mjs:64-90` asserts the rule: `available`,
`verified`, `verified_at`, positive `size`, 64-hex `sha256`, HTTPS-only `url`).

| OS/arch | Detection | Verified status |
|---|---|---|
| Windows x64 | `navigator.userAgentData.getHighEntropyValues` + `Win64`/`x64`/`WOW64` UA fallback | **pass** — Agent G `01-download-journey.spec.ts`, `qa-logs/final-acceptance-run.txt` |
| Windows ARM64 | high-entropy hints (`arch: arm/arm64/aarch64`); honest "not published / x64 under emulation" note | **pass** — same suite |
| macOS ARM64 / x64 | explicit Apple Silicon / Intel choice (`arch-confirm` state, no silent wrong pick) | **pass** — same suite (`Linux offers an explicit DEB vs RPM choice` is a separate passing test) |
| Linux x64 | manifest-derived DEB/RPM variants, no UA guessing | **pass** — same suite |
| iOS / Android | honest unsupported note, no installer offered | **pass** — same suite |

Commands run by Agent G: `cd keel/fleet-next; npx playwright test --config tests/distribution-qa/playwright.config.ts --reporter=list` →
**42 passed / 0 failed, `PW_EXIT=0`**; `npx tsc --noEmit --incremental false` exit 0.
Site logic additionally verified by `node --test keel/site/tests/*.test.mjs` → **20 passed / 0 failed**.

### 8.2 Installer publishing — artifacts, SHA-256, public URLs

Measured in this worktree (`Get-FileHash -Algorithm SHA256`, run twice with identical results):

| Artifact | Path | Size | SHA-256 |
|---|---|---|---|
| Packaged app (NSIS) | `keel/dist/win-unpacked/Keel.exe` | 235,419,136 bytes | `D52DB523BE65DE981320A175B9DA3C29B5B2F5925D3AED787CAA0F0254288B20` |
| Windows installer | `keel/dist/Keel-Setup-0.1.1.exe` | 158,152,373 bytes | `170F1361C786D80DC8B6ECCE5C5561592D6C42A5BFE2FB2010D98C0C491667BC` |
| Python sidecar | `keel/dist/keel-sidecar/keel.exe` (bundled as `keel/build/resources/keel/keel.exe`) | 31,436,836 bytes | `B091538D9E2E1284DAD3F85AC0B31DC532073331D140777B2FFA282EBD8431FF` |

Public download URLs (configured pipeline; see `RELEASE-2026-11-25.md` for the release notes):

- GitHub Releases base: `https://github.com/eliosmernica15/keel/releases/download`
  (`keel/src/keel/release/build.py:163`, `publish.py:122`, `common.py:31`).
- Public site: `https://keel-desktop.vercel.app/download`; manifest proxy `GET /api/download-manifest`
  (503 until `KEEL_DOWNLOAD_MANIFEST_URL` is set).
- Hash reconciliation: older docs record `Keel-Setup-0.1.1.exe` = `F6CAE185A6A2AA53D61572E4C9930B3750CE418FC9AAF38BD788CCC6E63743BB` (143,931,562 bytes); the worktree file measures 158,152,373 bytes / `170F1361…` — **pending** verification of which build is current.

### 8.3 Packaged EXE verification status (G4 / G6)

| Gate | Status (as of 2026-11-25, this worktree) | Evidence |
|---|---|---|
| G4 — packaged entry assertion | **verified in a real packaged EXE** | Agent G: `qa-logs/electron-exe-2026-11-25T15-14-55-042Z.json` (default unified, `Keel.exe` 235,419,136 B, `D52DB523…`), `15-22-23-946Z`, `15-25-40-221Z` (token scan over `/` HTML + 7 JS chunks → 0 leaks); `assert-ui-entrypoints.js --resources …/dist/win-unpacked/resources` → 47/47 |
| G6 — rollback (`KEEL_RENDERER=legacy`) | **verified in a real packaged EXE** | Agent G: `qa-logs/electron-exe-2026-11-25T15-24-38-876Z.json` — window `http://127.0.0.1:51505/?t=…`, title `Keel - Desktop & Code`, no Next child; 30/30 policy unit cases |
| G5 — `/app` public mirror | verified (browser + source) | `DISTRIBUTION-QA.md` §2.2, `02-pwa-journey.spec.ts` |

Note the honest status split: `ELECTRON-INTEGRATION-QA.md` §3.3/§3.6 records that the packaged default
became unified **only in the cutover build** and records the earlier legacy-default build as a
pre-cutover artifact; `UI-TEST-MATRIX.md` records legacy-renderer evidence as historical.

### 8.4 Cutover state (2026-11-25)

- **Source default is unified:** `desktop-app/renderer-policy.js:46` — `export const DEFAULT_RENDERER = RENDERER_MODES.UNIFIED;` (verified by reading the file).
- Policy units: 30/30 renderer-policy unit cases pass (Agent G, §3.7 `ELECTRON-INTEGRATION-QA.md`).
- Source-level cutover is recorded; the installed EXE evidence above is the packaged-side verification.
- No new claim here is a *production publication* (see `RELEASE-2026-11-25.md` — Agent C has not confirmed production publication, see `DISTRIBUTION-AGENT-AUDIT.md` F-2).
