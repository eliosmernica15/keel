# Desktop / web UI renderer pathing — verified evidence

**Branch:** `feat/frontend-unified-workspace` (worktree `C:\Users\Admin\Desktop\keel-frontend-worktree`)
**Scope:** read-only investigation of renderer entry points plus one new assertion script. No shipped renderer was repointed. No backend Python, `fleet-next`, `site/`, root package metadata, tests or git state were changed.

> **No fake claims.** Everything marked VERIFIED below came from a file read or a command actually run during this investigation. Nothing was built by this investigation. A pre-existing packaged Electron artifact was *inspected and its bundled sidecar was executed*; the Electron GUI itself was **not** launched, no Tauri binary was available, and `fleet-next` was **not** rebuilt. Do not read this document as "a packaged build passed" — it did not.

---

## 1. Verified path table

| Surface | Where the decision is made | Source/dev resolution | Packaged/served resolution | Capability actually delivered |
|---|---|---|---|---|
| **Electron (`keel.exe`)** | `desktop-app/main.js:61-70` `uiRoot()`; injected at `main.js:135` (`env.KEEL_UI_DIR = uiRoot() \|\| undefined`), `main.js:149` dev fallback | No `process.resourcesPath/site` in a source checkout → `uiRoot()` returns `null`; dev path uses `<repo>/desktop/ui` (`main.js:143-152`) | `resources/site` wins (has `index.html`) → `KEEL_UI_DIR=<resources>/site`. `main.js:246` loads `http://127.0.0.1:<port>/?t=<token>` — Electron renders **whatever the Python bridge serves**, not a static file root | Bridge at `/` prefers `UI_DIR/app.html` (`webapp.py:338-344`) → **`site/app.html`**, the browser-only BYOK mirror. Local agent / filesystem / trust controls are **not** in this file. |
| **`keel serve` / local bridge** | `src/keel/webapp.py:62-72` | `UI_DIR = Path(os.environ.get("KEEL_UI_DIR") or _BUNDLE_ROOT/"desktop"/"ui")` → `<repo>/desktop/ui` | With no `KEEL_UI_DIR`, the frozen sidecar uses `_MEIPASS/desktop/ui`, bundled by `desktop-app/sidecar.spec:26-31` | Bridge at `/` → `app.html` if present, else `index.html`. `desktop/ui` has **no** `app.html`, so it serves `desktop/ui/index.html` — full local UI (`/api/run`, `/api/fs/list`, `/api/workdir`, `/api/capabilities/invoke`). |
| **Tauri** | `desktop/src-tauri/tauri.conf.json:6-10` `build.frontendDist = "../ui"` | Resolves to `<repo>/desktop/ui` | Static asset root `desktop/ui`; no Python bridge involved. `desktop/src-tauri/src/main.rs:36-92` spawns the `keel` CLI over stdio and emits `keel:event` | Classic local UI + Tauri IPC agent path. Unchanged. |
| **Classic `/fleet`** | `src/keel/webapp.py:320-324` delegates to `_fleet_routes.dispatch_get`; `src/keel/fleet/routes.py:27,107-126` | `FLEET_UI_DIR = <repo>/desktop/fleet`; `/fleet` → `desktop/fleet/index.html` | Same path in the frozen sidecar (the route derives from `routes.py`'s own location) | Classic Fleet reference UI. Preserved, not retired. |
| **Public `/app` mirror** | `site/README.md:7-14`, `site/app.html`, `site/ui/app.js` | Static Vercel site: `/` = `site/index.html` (marketing), `/app` = `site/app.html` (BYOK mirror) | Also shipped into Electron as `resources/site` by `desktop-app/package.json:32-42` | `site/ui/app.js:231-233`: "mirror build - no local bridge exists. Chat streams client-side to the provider you linked … (BYOK)." |
| **`fleet-next` (candidate)** | `fleet-next/README.md:8-23`, `fleet-next/next.config.mjs`, `fleet-next/app/api/bridge/[...path]/route.ts` | Needs `npm run build` + `npm start` (Next server on `127.0.0.1:3000`) and a same-origin BFF that injects the bridge token server-side | **No path in this repository points any shipped renderer at it.** It is not a static export (`next.config.mjs` has no `output: "export"`), so it cannot be used as `KEEL_UI_DIR`, `frontendDist` or a `/fleet` static root | Unified Cowork/Code/Duet/Fleet UI. Implemented and browser-verified on its own server; not shipped by Electron or Tauri. |

### The ambiguity, stated precisely

Electron's `uiRoot()` preference (`site` → `desktop/ui` → `ui`, gated on `index.html` at `main.js:68`) conflicts with:

- the local bridge default (`webapp.py:71` → `desktop/ui`),
- Tauri's `frontendDist` (`tauri.conf.json:7` → `../ui` = `desktop/ui`), and
- the sidecar's own bundled canonical UI (`sidecar.spec:29` → `desktop/ui`).

`electron-builder` ships `../site` into `resources/site` (`package.json:33-42`), so the **first** `uiRoot()` candidate is always satisfied in a packaged Electron build. The comment at `main.js:64` even labels it "mirror build (shipped in production)". This matches `docs/UI-ARCHITECTURE.md:20-22`, which records the conflict as a packaging workstream gate, and `docs/IMPLEMENTATION-PROGRESS.md:1203`, which says the rendering switch remains gated.

This was **not changed**: repointing Electron at `fleet-next` without a verified build path and parity gate would remove local-agent/filesystem/trust behaviour from whatever the shipped app renders; changing the preference order would itself alter shipped behaviour. Both are packaging decisions, not safe frontend-only edits.

---

## 2. Evidence and commands actually run

All commands were run with the worktree as CWD unless noted. Output is quoted verbatim (tokens redacted where they were ephemeral random values).

### 2.1 Source reads (file:line)

| File:line | What it proves |
|---|---|
| `keel/desktop-app/main.js:61-70` | `uiRoot()` candidate order and `index.html` gate. |
| `keel/desktop-app/main.js:135,140,149` | `KEEL_UI_DIR` injection in production, `KEEL_SIDE_CAR` path, and dev fallback. |
| `keel/desktop-app/main.js:246` | Electron loads the loopback bridge URL; the bridge chooses the UI file. |
| `keel/desktop-app/package.json:32-46` | `extraResources`: `../site → site`, `../build/resources/keel → keel`. |
| `keel/desktop-app/sidecar.spec:22-32` | Frozen sidecar bundles `desktop/ui`, `manifest.webmanifest`, `sw.js`. |
| `keel/src/keel/webapp.py:62-72` | `UI_DIR` env override and source/bundle default. |
| `keel/src/keel/webapp.py:332-369` | `/`, `/app` (app.html-then-index.html) and `/ui/` static handling. |
| `keel/src/keel/fleet/routes.py:27,107-126` | Classic `/fleet` root and static file dispatch. |
| `keel/desktop/src-tauri/tauri.conf.json:6-10` | `frontendDist: "../ui"`. |
| `keel/desktop/src-tauri/src/main.rs:36-92` | Tauri agent path is CLI stdio IPC, not the Python bridge. |
| `keel/site/README.md:7-14,26-54` | Public routes and explicit "no agent, no disk" mirror boundary. |
| `keel/site/ui/app.js:231-233` | Mirror comment: no local bridge; BYOK client-side chat. |
| `keel/fleet-next/README.md:8-23,105-112` | Next server/BFF run model; not a production deployment. |
| `keel/fleet-next/next.config.mjs` | No `output: "export"` → cannot be a static UI root. |
| `keel/docs/UI-ARCHITECTURE.md:9-30,69-80` | Phase 0 renderer inventory and gates G4/G6. |
| `keel/docs/IMPLEMENTATION-PROGRESS.md:1151,1197-1203` | "Renderer target = fleet-next"; rendering switch and mirror boundary remain gated. |

### 2.2 Pre-existing packaged artifact inspection (not built here)

A packaged Electron build exists in the *other* worktree at
`C:\Users\Admin\Desktop\Claude clone\keel\dist\win-unpacked\` (`Keel.exe`, installer `Keel-Setup-0.1.1.exe`). It was **not created by this investigation**.

```
Get-ChildItem "C:\Users\Admin\Desktop\Claude clone\keel\dist\win-unpacked\resources"
Name
----
keel
site
app.asar
elevate.exe

Get-Item "...\resources\site\index.html","...\resources\site\app.html" | Select FullName,Length
20817
51798

Get-ChildItem "...\resources\desktop\ui" -File   # no output: directory absent
Get-ChildItem "...\resources\keel" -File
keel.exe  29281431
```

So in the shipped layout only `resources/site` can satisfy `uiRoot()`: `resources/desktop/ui` and `resources/ui` do not exist. The `app.asar` was parsed with Node built-ins (asar header → `files["main.js"]`) and the shipped `main.js` matched the worktree source byte-for-byte:

```
PASS  packaged app.asar main.js matches source main.js — dbbe93c20d92 vs dbbe93c20d92
```

The extracted `uiRoot()` from `app.asar` was identical to `desktop-app/main.js:61-70`.

### 2.3 Runtime probe of the packaged sidecar (executed)

The bundled `resources/keel/keel.exe` was spawned with `serve --port <random>`, `KEEL_TOKEN=<random>`, `KEEL_NO_BANNER=1`, and HTTP `GET /?t=<token>` was issued. The probe script lived in the OS temp folder; it is **not** part of the deliverable.

Run A — reproduce Electron's production env (`KEEL_UI_DIR=<resources>/site`):

```
KEEL_UI_DIR: C:\Users\Admin\Desktop\Claude clone\keel\dist\win-unpacked\resources\site
SIDECAR URL: http://127.0.0.1:9424/?t=<redacted>
HTTP STATUS: 200
MARKER public-mirror safe-mode-badge: true
MARKER public-mirror OpenRouter browser BYOK: true
MARKER local-bridge /api/run: true
MARKER local-bridge /api/fs/list: true
BODY BYTES: 51626
TITLE: Keel — Desktop &amp; Code
```

Run B — no override (frozen-bundle default, i.e. `desktop/ui`):

```
KEEL_UI_DIR: (unset -> frozen bundle default)
SIDECAR URL: http://127.0.0.1:9186/?t=<redacted>
HTTP STATUS: 200
MARKER public-mirror safe-mode-badge: false
MARKER public-mirror OpenRouter browser BYOK: true
MARKER local-bridge /api/run: true
MARKER local-bridge /api/fs/list: true
BODY BYTES: 47660
TITLE: Keel — Desktop &amp; Code
```

Interpretation: the only difference is Electron's `KEEL_UI_DIR` override. With it, the bridge serves `site/app.html` (the `safe-mode-badge` is unique to that file at `site/app.html:17`). Without it, the bridge serves the bundled `desktop/ui/index.html`. The `/api/run`, `/api/fs/list` and `OpenRouter` marker strings inside `site/app.html` are help text and provider names (`site/app.html:539-540,373-374`), **not** a local agent implementation — `site/ui/app.js:231-233` states the mirror has no local bridge. Both child processes were terminated with `taskkill /T /F` after the probe.

### 2.4 Tauri / fleet-next availability

```
Get-ChildItem "C:\Users\Admin\Desktop\Claude clone\keel\desktop\src-tauri\target" -Directory
Name
----
debug
# Get-ChildItem -Recurse -File -Include *.exe,*.msi ... -> no output
```

No Tauri executable or installer was available; Tauri was **not** run. The worktree `fleet-next/.next/BUILD_ID` exists (`b0ZPsV_Efwe9t5TjycsJY`) from a previous, unobserved build; **no `npm run build` was executed here**. `fleet-next/node_modules` exists; `desktop-app/node_modules` does not exist in the worktree, so no Electron build was attempted either.

---

## 3. What changed, and why

| Change | Reason |
|---|---|
| Added `keel/desktop-app/scripts/assert-ui-entrypoints.js` (new, read-only, Node built-ins only) | Makes the intended entry-point contract executable. It asserts the `uiRoot()` order, the `KEEL_UI_DIR` injection, the `electron-builder` `site` resource, Tauri's `frontendDist`, the bridge's `UI_DIR`/route fallbacks, the classic `/fleet` root, and — as a guard — that **no shipped config references `fleet-next`**. With `--resources <dir>` it additionally verifies a real unpacked Electron layout and the `app.asar` main.js hash. |
| Added this document | Records the evidence, the path table, the blockers and the no-fake-claims caveat required by the continuation plan. |
| **No renderer path was changed.** `desktop-app/main.js`, `desktop-app/package.json`, `desktop/src-tauri/**`, `src/**`, `site/**` and `fleet-next/**` are untouched. | Electron/Tauri repointing is gated on a verified build path and parity gate (G4/G6 in `UI-ARCHITECTURE.md:76-80`). Changing `uiRoot()` order would alter shipped behaviour. The safe answer is "leave as-is and document". |

### Assertion script — real results

```
cd C:\Users\Admin\Desktop\keel-frontend-worktree\keel
node desktop-app/scripts/assert-ui-entrypoints.js
...
SUMMARY: 21/21 checks passed
All current entry-point assertions hold. No shipped renderer was changed.
EXIT=0

node desktop-app/scripts/assert-ui-entrypoints.js --resources "C:\Users\Admin\Desktop\Claude clone\keel\dist\win-unpacked\resources"
...
PASS  packaged uiRoot() resolves to resources/site — C:\Users\Admin\Desktop\Claude clone\keel\dist\win-unpacked\resources\site
PASS  packaged app.asar main.js matches source main.js — dbbe93c20d92 vs dbbe93c20d92
...
SUMMARY: 26/26 checks passed
All current entry-point assertions hold. No shipped renderer was changed.
EXIT=0
```

The first version of the script had a bug — its `join(res, …)` regex also matched `bundledSidecar()` and reported 20/21. It was fixed by scoping the regex to the `uiRoot()` function body; the passing runs above are the final version.

---

## 4. What remains blocked

1. **G4 — packaged renderer assertion.** The intended local renderer is not loaded by the shipped Electron build: `KEEL_UI_DIR` redirects the bridge to `site/app.html`. Resolving this requires a packaging-owner decision (is the mirror intentional, or should the local UI win?), a fresh package build, and a GUI parity check. This subagent deliberately did not make that decision.
2. **G6 — rollback flag to `desktop/ui`.** No such flag exists in `main.js` or `tauri.conf.json`; adding one is a packaging change.
3. **`fleet-next` cannot be dropped into any existing static UI root.** It is a Next server app with a token-injecting BFF (`fleet-next/app/api/bridge/[...path]/route.ts`), not a static export. Making it shippable needs a build/packaging workstream (Node runtime in the package or a static export plus a different auth model) and the parity gate — out of scope here.
4. **Tauri binary unavailable.** Only a `target/debug` directory with no executable was found; no Tauri runtime check was possible.
5. **Live model turn remains unverified** — no provider credentials on this host (same caveat as `fleet-next/README.md:108-112` and `docs/IMPLEMENTATION-PROGRESS.md:1199`).
6. **Full Python suite was not run** in this investigation; no Python files were changed.

## 5. Legacy behaviour preserved

- Electron still resolves `resources/site` first and still serves `site/app.html` in the packaged layout (no behaviour change).
- `keel serve` still defaults to `desktop/ui` and still prefers `app.html` then `index.html`.
- Tauri still uses `desktop/ui` via `frontendDist: "../ui"`.
- Classic `/fleet` still serves `desktop/fleet/index.html` via `keel.fleet.routes`.
- The public `/app` mirror still serves `site/app.html` with no local agent, disk or trust surface.
- `fleet-next` remains the implementation target only, exactly as recorded in `UI-ARCHITECTURE.md:26`.
