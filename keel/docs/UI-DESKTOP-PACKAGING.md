# Desktop packaging — renderer resolution fixed and verified

**Branch/worktree:** `feat/frontend-completion-2026-11-24` @ `C:\Users\Admin\Desktop\keel-frontend-worktree`
**Owner:** Agent E (Electron / desktop packaging)
**Scope:** `desktop-app/**`, `desktop/src-tauri/**`, this document. No commits, no pushes. `fleet-next/**`, `src/keel/**`, generated plan files and other agents' work were not modified.

> **No fake claims.** Every VERIFIED line below is backed by a command actually run in this worktree on 2026-11-24. Tokens are redacted. The Electron app was built *and launched*; the Tauri app was **not** built (blocked, see §6). No live provider turn was attempted (no credentials).

---

## 1. Which UI the desktop product must load — and why

The decision is not a preference, it follows from the existing architecture contract:

| Evidence | What it says |
|---|---|
| `docs/UI-ARCHITECTURE.md:14,27-31` | `desktop/ui` is the current shipped local app and the stable fallback. `fleet-next` is an implementation target, **not** the shipped renderer. The renderer switch is gated on G1–G6. |
| `docs/UI-ARCHITECTURE.md:77-79` | G4 = "Electron and Tauri load the intended local build, asserted in packaging"; G6 = "rollback flag to `desktop/ui` retained". |
| `docs/UI-DESKTOP-RENDERING.md:14-19,21-31` | Electron's old `uiRoot()` preferred `resources/site`, which the bridge turns into `site/app.html` — the browser-only BYOK mirror. Tauri (`frontendDist: "../ui"`) and the frozen sidecar (`sidecar.spec:29`) both use `desktop/ui`. |
| `site/ui/app.js:231-233` | Mirror comment: "no local bridge exists … chat streams client-side to the provider you link (BYOK)". |
| `site/app.html:17` | `<div class="safe-mode-badge" hidden>SCREEN-SHARE SAFE MODE …</div>` — a marker unique to the restricted mirror. |
| `src/keel/webapp.py:71,332-344` | Bridge defaults to `<bundle>/desktop/ui`; at `/` it prefers `app.html`, then `index.html`. `desktop/ui` has no `app.html`, so the local UI is `index.html` and exposes `/api/run`, `/api/fs/list`, `/api/workdir`, `/api/capabilities/invoke`. |

**Conclusion:** the packaged desktop app must resolve `desktop/ui` (full local agent/filesystem/trust surface). The `site` tree is a reduced browser mirror and must never be the default Electron renderer. `fleet-next` remains unshipped (it needs a Next server + token-injecting BFF, not a static UI root).

### Root cause that was fixed

`electron-builder` always ships `../site` → `resources/site` (`package.json` `extraResources`). The old `uiRoot()` checked `site` first and gated on `index.html`, so the first candidate was always satisfied. `main.js` then set `KEEL_UI_DIR=<resources>/site`, and the bridge served `site/app.html`. The packaged app therefore rendered the restricted mirror even though the sidecar had the full UI bundled.

---

## 2. Minimal fix (and rollback)

### `desktop-app/main.js` — `uiRoot()`

- Local roots now win: `join(res, "desktop", "ui")`, then `join(res, "ui")`.
- `site` is **no longer a default candidate**. Returning `null` when no local root exists is intentional: production then leaves `KEEL_UI_DIR` unset and the frozen sidecar serves the `desktop/ui` it bundles itself (`sidecar.spec:29`).
- Rollback / diagnostic paths preserved:
  - `KEEL_UI_PROFILE=mirror` → forces `resources/site` (the exact legacy behaviour).
  - `KEEL_UI_DIR=<dir>` → explicit override, accepted only if `<dir>/index.html` exists.
  - Value comparison is case-insensitive.
- Everything else in `main.js` is unchanged: loopback URL load with the sidecar token, `did-finish-load`/splash handling, single-instance lock, sidecar teardown, update check.

### `desktop-app/package.json` — `extraResources`

Added one entry so the packaged layout contains an explicit, build-time local root:

```json
{ "from": "../desktop/ui", "to": "desktop/ui", "filter": ["**/*"] }
```

`../site → site` is still shipped (needed for the public site and as the rollback target); `../build/resources/keel → keel` is unchanged. No dependency was added to `dependencies` or `devDependencies`.

### Rollback procedure (operator)

```
# legacy restricted mirror, exactly the pre-fix behaviour
KEEL_UI_PROFILE=mirror Keel.exe

# or force an arbitrary local UI root (must contain index.html)
KEEL_UI_DIR="C:\path\to\desktop\ui" Keel.exe
```

To revert the code change: restore the previous `uiRoot()` body (site-first candidates) and remove the `../desktop/ui → desktop/ui` resource; the audit scripts will then report the old contract and fail the new assertions, as designed.

---

## 3. Files added / changed by this work

| File | Change |
|---|---|
| `desktop-app/main.js` | `uiRoot()` local-first + mirror/override rollback (above). |
| `desktop-app/package.json` | ship `../desktop/ui` as `resources/desktop/ui`. |
| `desktop-app/scripts/assert-ui-entrypoints.js` | Updated from 21 old-contract checks to **25 source checks**; with `--resources` **31 checks**. Now asserts local-first order, mirror gating, both resource entries, mirror-badge contrast, packaged `app.asar` main.js hash, Tauri/bridge/fleet contracts, and that no shipped config references `fleet-next`. |
| `desktop-app/scripts/test-ui-root.js` | **New.** Behavioural test: extracts the real `uiRoot()` source from `main.js` and executes it against a mocked fs/env. 8 cases, no Electron/network needed. |
| `desktop/src-tauri/Cargo.lock` | One-line version sync `0.1.0 → 0.1.1` (required by `Cargo.toml`; `--locked` refused to build before this). |
| `docs/UI-DESKTOP-PACKAGING.md` | This document. |

Generated artifacts (not source, not committed): `desktop-app/build/*` icons, `build/resources/keel/keel.exe`, `dist/keel-sidecar/keel.exe`, `dist/win-unpacked/**`, `dist/Keel-Setup-0.1.1.exe`, `desktop-app/node_modules/**`, Tauri `target/**`.

---

## 4. Build commands and real output

All commands run with CWD `keel/` unless noted.

### 4.1 Locked dependency install (no new deps)

```
cd desktop-app
npm ci
```

```
added 283 packages, and audited 284 packages in 57s
6 moderate severity vulnerabilities
EXIT=0
```

```
npx electron --version  -> v42.11.18
npx electron-builder --version -> 26.18.0
```

The npm audit findings are pre-existing transitive advisories; no `npm audit fix` was run (no new deps, no changed lockfile).

### 4.2 Sidecar (required input of `extraResources`)

```
python desktop-app/scripts/generate_assets.py
  -> icon.ico / icon.png / sidebar.bmp / header.bmp        EXIT=0

python -m PyInstaller desktop-app/sidecar.spec --noconfirm --distpath dist/keel-sidecar
  ...
  206742 INFO: Build complete! The results are available in: ...\dist\keel-sidecar
  PYINSTALLER_EXIT=0
  dist\keel-sidecar\keel.exe   31,160,346 bytes

New-Item -ItemType Directory -Force build\resources\keel
Copy-Item dist\keel-sidecar\keel.exe build\resources\keel\keel.exe
  build\resources\keel\keel.exe   31,160,346 bytes
```

### 4.3 Packaged Electron build (existing script)

```
cd desktop-app
npm run build:win
```

```
> keel-desktop@0.1.1 build:win
> electron-builder --win

  • electron-builder  version=26.18.0 os=10.0.26300
  • packaging       platform=win32 arch=x64 electron=42.11.18 appOutDir=...\keel\dist\win-unpacked
  • downloaded electron zip extracted successfully  output=...\dist\win-unpacked
  • no code signing certificate configured, signing is skipped
  • building        target=nsis file=...\dist\Keel-Setup-0.1.1.exe archs=x64 oneClick=false perMachine=false
  • building block map  blockMapFile=...\Keel-Setup-0.1.1.exe.blockmap
BUILD_EXIT=0

dist\Keel-Setup-0.1.1.exe            143,310,700 bytes
dist\win-unpacked\resources\          desktop/  keel/  site/  app.asar  elevate.exe
dist\win-unpacked\resources\desktop\ui\  fonts/ icons/ app.js  index.html  management.js  style.css
```

### 4.4 Static assertions (all real, all passing)

```
node --check desktop-app/main.js                       -> EXIT=0
node desktop-app/scripts/test-ui-root.js
  PASS  packaged: local desktop/ui wins over site — R\desktop\ui
  PASS  mirror-only layout: default is null, never site — null
  PASS  KEEL_UI_PROFILE=mirror: rollback to site — R\site
  PASS  KEEL_UI_PROFILE is case-insensitive — R\site
  PASS  explicit KEEL_UI_DIR overrides local root — C\custom-ui
  PASS  bogus KEEL_UI_DIR is ignored (no index.html) — R\desktop\ui
  PASS  legacy resources/ui still resolves — R\ui
  PASS  no resources: null (dev branch uses repo desktop/ui) — null
  SUMMARY: 8/8 uiRoot() cases passed                    EXIT=0

node desktop-app/scripts/assert-ui-entrypoints.js
  SUMMARY: 25/25 checks passed                          EXIT=0

node desktop-app/scripts/assert-ui-entrypoints.js --resources "...\dist\win-unpacked\resources"
  PASS  packaged resources/desktop/ui/index.html present
  PASS  packaged resources/site/app.html present (rollback target)
  PASS  packaged default uiRoot() resolves to desktop/ui, not site — ...\resources\desktop\ui
  PASS  packaged default root is the full local UI (no mirror badge)
  PASS  packaged app.asar main.js matches source main.js — e60eba8bc5ee vs e60eba8bc5ee
  SUMMARY: 31/31 checks passed                          EXIT=0
```

---

## 5. Runtime verification — which renderer actually loads

### 5.1 Packaged sidecar over loopback (exact Electron env)

The bundled `resources/keel/keel.exe` was spawned with `KEEL_TOKEN=<random>`, `KEEL_NO_BANNER=1` and the same `KEEL_UI_DIR` that `main.js` injects. HTTP `GET /?t=<token>` body hashes were compared with the packaged source files. (Probe script lived in the OS temp folder; it is not part of the deliverable.)

**Default local root (`KEEL_UI_DIR=<resources>/desktop/ui`) — what the fixed Electron app sets:**

```
sidecar URL = http://127.0.0.1:<port>
GET /?t=<token> -> 200; bytes=47816 sha256=e6f53616a28b1270145e4ce797b271dbe873a2200ed4b613ba8a2a5efe760101
PASS  renderer body matches desktop/ui/index.html
PASS  bad token -> 403 ; /api/health without token -> 403
PASS  /api/health        -> 200 {"ok": true, "version": "0.1.1"}
PASS  /api/fs/roots      -> 200 {"roots": ["C:\\"]}
PASS  /api/workdir       -> 200 {"path": null}
PASS  /api/capabilities  -> 200 {"capabilities": [{"id": "backend.describe", ...}]}
PASS  /api/surfaces      -> 200 {"surfaces": [{"name": "Keel Cowork", ...}]}
PASS  /api/providers     -> 200 {"providers": [{"name": "openrouter", "configured": false, ...}]}
PASS  /api/fs/list       -> 200 {"ok": true, ... "dirs": [...]}
GET /ui/app.js -> 200; bytes=100581 sha256=d647a2dfef1e7ba408d404029ae376237f04661629605dc2df599470c12c5d70
PASS  served app.js matches expected UI
PASS  SCENARIO default local
```

**Rollback mirror (`KEEL_UI_DIR=<resources>/site`):**

```
GET /?t=<token> -> 200; bytes=51798 sha256=c4bf90bf4b0c1be7b907e3ec1573eeab02c915797228cd670bab5efea7d84aa0
PASS  mirror body matches site/app.html (safe-mode-badge present)
GET /ui/app.js -> 200; bytes=143146 sha256=13d0fb46a3b448460023d953b36c5b062d383437ec161c7b7f4cd252df7c3900
PASS  served app.js matches expected UI
PASS  SCENARIO mirror rollback
```

**No override (frozen sidecar default):**

```
GET /?t=<token> -> 200; bytes=47816 sha256=e6f53616a28b1270145e4ce797b271dbe873a2200ed4b613ba8a2a5efe760101
PASS  renderer body matches desktop/ui/index.html
PASS  SCENARIO no override
```

All three scenarios passed the token-auth and desktop-capability checks. Every spawned process tree was terminated with `taskkill /PID <pid> /T /F`.

### 5.2 The packaged Electron GUI itself (CDP)

The built `dist/win-unpacked/Keel.exe` was launched with `--remote-debugging-port`, and the loaded page was inspected over the Chrome DevTools Protocol. This is a real GUI launch, not a static inference.

```
Keel.exe --remote-debugging-port=9222
DevTools listening on ws://127.0.0.1:9222/devtools/browser/...
CDP: {"Browser":"Chrome/148.0.7778.280", ... "keel-desktop/0.1.1 ... Electron/42.11.18"}
PAGE: {"title":"Keel — Desktop &amp; Code","url":"http://127.0.0.1:10017/?t=<redacted>"}
DATA: {"hasMirrorBadge":false,"hasManagementScript":true,
       "healthStatus":200,"fsRootsStatus":200,
       "bodyStart":"New session\nCustomize Keel\nTake the tour\nPINNED\nRECENTS\n..."}
PASS packaged Electron renderer is the full local UI
```

**Rollback profile in the packaged GUI** (`KEEL_UI_PROFILE=mirror Keel.exe --remote-debugging-port=9223`):

```
PAGE: {"title":"Keel — Desktop &amp; Code","url":"http://127.0.0.1:10055/?t=<redacted>"}
DATA: {"hasMirrorBadge":true,"healthStatus":200,"fsRootsStatus":200,
       "bodyStart":"Skip to main content\nNew session\n..."}
PASS packaged Electron renderer is the rollback mirror
```

Bridge token auth was verified both from the raw sidecar (§5.1) and from inside the loaded renderer (`/api/health` and `/api/fs/roots` returned 200 with the renderer's token/cookie, 403 without). Desktop-only capabilities (`fs roots`, `fs list`, `workdir`, `capabilities`, `surfaces`) answer on the packaged bridge; the public mirror remains a separate static site. Both Electron process trees were terminated after inspection.

---

## 6. Tauri — inspected and prepared, **not** built

`desktop/src-tauri/tauri.conf.json` verified by `assert-ui-entrypoints.js`:

- `build.frontendDist = "../ui"` → `<repo>/desktop/ui` (the same full local UI Electron now uses). No Python bridge in this path; `src/main.rs` spawns the `keel` CLI over stdio and emits `keel:event`.
- `beforeDevCommand`/`beforeBuildCommand` are empty; `bundle.targets = [nsis, msi, app]`; CSP is `default-src 'self' …`.
- No `fleet-next` reference anywhere in the config.

Build environment: `rustc 1.99.1`, `cargo 1.99.1` are present. Build preparation and exact blockers:

```
cd desktop/src-tauri
cargo check --locked
error: cannot update the lock file ...\Cargo.lock because --locked was passed to prevent this
help: to generate the lock file without accessing the network, remove the --locked flag and use --offline instead.
EXIT=101

# fixed the one-line version drift in Cargo.lock (0.1.0 -> 0.1.1), then:
cargo check
error: linker `link.exe` not found
note: program not found
note: the msvc targets depend on the msvc linker but `link.exe` was not found
note: please ensure that Visual Studio 2017 or later, or Build Tools for Visual Studio were installed with the Visual C++ option
error: could not compile `icu_properties_data` (build script) due to 1 previous error
...
EXIT=101
```

This matches `desktop/README.md:52-64` ("Tauri native shell — on hold until Windows finishes the Restart … Build Tools VCTools payload pending reboot"). **No Tauri binary or installer was produced. No native Tauri build is claimed.** Once the MSVC linker is available, the prepared command is `cargo check` then `cargo build --release` (or `cargo tauri build` from `desktop/` if the Tauri CLI is installed); `frontendDist` already points at the correct UI.

---

## 7. Remaining gates / honest caveats

1. **G4 (packaged renderer assertion): PASS** — Electron was built, launched and inspected; the full local UI loads by default and the mirror only via explicit rollback. G6 (rollback flag to desktop/ui) is PASS via `KEEL_UI_PROFILE` / `KEEL_UI_DIR`.
2. **Live model turn: UNVERIFIED** — no provider credentials on this host. Capability endpoints and bridge auth are verified; an actual agent turn was not run.
3. **Tauri: BLOCKED** by missing MSVC `link.exe` (§6). No native build claimed.
4. **Code signing: not configured** — electron-builder skipped signing; installer is unsigned. No certificate was requested.
5. **npm audit:** 6 moderate advisory findings from the locked tree; no dependency changes were made.
6. **Visual/GUI parity** was not exhaustively reviewed screen-by-screen; CDP confirms the renderer identity, badge state, management script and bridge responses, not a full UX audit.
7. `fleet-next` is still the implementation target only; it is not shipped by Electron or Tauri and no generated plan file was touched.
8. No commits or pushes were made; other agents' concurrent changes in the worktree were left untouched.
