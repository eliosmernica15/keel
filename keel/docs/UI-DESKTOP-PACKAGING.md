# Desktop packaging — renderer resolution fixed and verified

**Branch/worktree:** `feat/frontend-completion-2026-11-24` @ `C:\Users\Admin\Desktop\keel-frontend-worktree`
**Owner:** Agent E (Electron / desktop packaging)
**Scope:** `desktop-app/**`, `desktop/src-tauri/**`, `src/keel/release/**`, `.github/workflows/build-desktop.yml`, release acceptance tests/scripts, this document. No commits, no pushes. `site/**`, other agents' docs and generated plan files were not modified.

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

---

## 8. Production distribution round (2026-11-25) — native installers, release pipeline, security fixes

This section is the evidence for the second, production-distribution round. All commands below were run in `C:\Users\Admin\Desktop\keel-frontend-worktree\keel` with `PYTHONPATH` pointed at this worktree's `src` (the global Python editable install points at a *different* checkout, so `PYTHONPATH` must be set explicitly). Tokens are redacted. **No macOS or Linux installer was built on this Windows host; that is an explicit external gate, not a claim.**

### 8.1 Native target configuration (what changed and why)

| File | Change |
|---|---|
| `desktop-app/package.json` | `mac.target` is now `[{target: "pkg", arch: ["arm64","x64"]}]` (was DMG+ZIP). Added `pkg.installLocation = /Applications`, `isRelocatable`, `isVersionChecked`, `overwriteAction: upgrade`. `linux.target` is now `["deb","rpm"]` — **AppImage removed**. `win`/`nsis` left intact: per-user NSIS, branded welcome/finish BMPs, Desktop + Start Menu shortcuts, `deleteAppDataOnUninstall:false`. |
| `desktop-app/scripts/generate_assets.py` | Generates `build/icon.icns` (valid PNG-chunk ICNS container, no macOS host needed) and `build/icons/{16,32,48,64,128,256,512}x*.png` for the DEB/RPM desktop entry and icon. NSIS BMP/ICO generation unchanged. |
| `src/keel/release/common.py` | `CHANNELS`: Windows `.exe`; macOS primary `Keel-{version}-macos-arm64.pkg` with `Keel-{version}-macos-x64.pkg` as the Intel alternative; Linux primary `Keel-{version}-linux-amd64.deb` with `Keel-{version}-linux-x86_64.rpm` as the alternative. Added `arch_for_artifact()` (an Intel PKG is no longer labelled arm64), accurate install/notes strings, and `build_fallback_download_manifest()`. |
| `src/keel/release/build.py` | Linux electron-builder invocation now `deb rpm` only; `npm ci` when a lockfile is present; generates icon assets, then runs `check_packaging_config()` **before** electron-builder and `check_built_inventory()` after it. |
| `src/keel/release/packaging.py` (new) | Host-independent static acceptance: package identity, NSIS branding/shortcuts/data preservation, PKG arches + `/Applications` destination, DEB/RPM targets + desktop/icon deps, channel contract, built-artifact inventory, and Windows installer byte inspection. |
| `src/keel/release/cli.py` | New commands `check-packaging` and `fallback`. |
| `.github/workflows/build-desktop.yml` | Independent `build-*` → `verify-*` stages per OS; native runners; static checks on each runner; optional OS signing/notarization credentials; truthful OS-signature status; fail-closed signing gate and publish unchanged in intent. |
| `.github/workflows/verify-install.yml` | macOS job expands/validates the PKG `Distribution` + BOM instead of mounting a DMG; Linux job validates DEB/RPM desktop entry instead of extracting AppImage. |

### 8.2 Sidecar staleness (Agent C finding) — rebuilt, evidence

The previous sidecar predated the reconciliation merge. Confirmed and corrected:

```
git log -1 --format="%H %cI %s" c80c2e1
  c80c2e1da4dd5c583b85b20433cf055b77442224 2026-11-25T01:59:56+01:00 chore: reconcile feature branch with latest origin/main

BEFORE: dist/keel-sidecar/keel.exe  31,160,346 bytes  LastWriteTimeUtc 2026-11-24T21:38:20Z
        SHA256 9E8B67307E850CF7D32BC4EE8AA7714119A8B33F86E08F02336BAF0A968A09F2

python -m PyInstaller desktop-app/sidecar.spec --noconfirm --distpath dist/keel-sidecar
  ... 103527 INFO: Build complete! The results are available in: ...\dist\keel-sidecar
  PYINSTALLER_EXIT=0
Copy-Item dist\keel-sidecar\keel.exe build\resources\keel\keel.exe -Force

AFTER:  dist/keel-sidecar/keel.exe  31,436,836 bytes  LastWriteTimeUtc 2026-11-25T01:20:28Z
        build/resources/keel/keel.exe  same bytes / same timestamp
        SHA256 B091538D9E2E1284DAD3F85AC0B31DC532073331D140777B2FFA282EBD8431FF
```

The rebuild timestamp is **after** the merge (00:59:56Z vs 01:20:28Z), and the size changed, so the packaged sidecar now contains the reconciled trust/permission/security code.

### 8.3 Windows installer rebuilt and re-verified

```
cd desktop-app && npm run build:win
  • electron-builder version=26.18.0 os=10.0.26300
  • packaging platform=win32 arch=x64 electron=42.11.18 appOutDir=...\dist\win-unpacked
  • no code signing certificate configured, signing is skipped
  • building target=nsis file=...\dist\Keel-Setup-0.1.1.exe archs=x64 oneClick=false perMachine=false
  • building block map blockMapFile=...\Keel-Setup-0.1.1.exe.blockmap
  BUILD_EXIT=0

dist\Keel-Setup-0.1.1.exe                 143,931,562 bytes  2026-11-25T01:22:45Z
  SHA256 F6CAE185A6A2AA53D61572E4C9930B3750CE418FC9AAF38BD788CCC6E63743BB
dist\win-unpacked\resources\keel\keel.exe  31,436,836 bytes
  SHA256 B091538D...8431FF   (byte-identical to the freshly rebuilt sidecar)
```

Packaged layout / asset inventory (re-checked after the rebuild):

```
dist\win-unpacked\resources\
  desktop\   keel\   site\   app.asar (14,866)   elevate.exe (107,520)
dist\win-unpacked\resources\desktop\ui\
  fonts\ icons\ app.js (100,581) index.html (47,816)
  management.js (11,090) style.css (58,727)
dist\keel-sidecar\keel.exe --version  ->  keel 0.1.1
```

### 8.4 Packaged assertions (all re-run on the rebuilt installer)

```
node --check desktop-app/main.js                              NODE_CHECK=0
node desktop-app/scripts/test-ui-root.js
  SUMMARY: 8/8 uiRoot() cases passed
node desktop-app/scripts/assert-ui-entrypoints.js
  SUMMARY: 25/25 checks passed
node desktop-app/scripts/assert-ui-entrypoints.js --resources "...\dist\win-unpacked\resources"
  PASS  packaged resources/desktop/ui/index.html present
  PASS  packaged resources/site/app.html present (rollback target)
  PASS  packaged default uiRoot() resolves to desktop/ui, not site
  PASS  packaged default root is the full local UI (no mirror badge)
  PASS  packaged app.asar main.js matches source main.js — 0ce776a28ba2 vs 0ce776a28ba2
  SUMMARY: 31/31 checks passed
python -m keel.release check-packaging --installer "dist\Keel-Setup-0.1.1.exe" --dist dist --platform windows
  packaging checks: PASS (config, installer, inventory)
```

The `main.js` asar hash changed from `e60eba8b…` to `0ce776a2…` because of the SEC-F-06 guard added in §8.7; source and packaged copy still match exactly. The full-local-UI renderer and the `KEEL_UI_PROFILE=mirror` / `KEEL_UI_DIR` rollback profile are unchanged and still pass. The Windows installer static check confirms the NSIS `NullsoftInst` marker and the UTF‑16LE `Keel` brand; the branded welcome/finish wording is asserted against `build/nsis-keel.nsh` because NSIS script strings are stored in a compressed data block and are not directly searchable in the binary.

Live loopback probe of the rebuilt sidecar (temp script, not part of the deliverable):

```
BODY_BYTES 47816 EXPECTED_BYTES 47816
BODY_SHA256 e6f53616a28b1270145e4ce797b271dbe873a2200ed4b613ba8a2a5efe760101
EXPECTED_SHA256 e6f53616a28b1270145e4ce797b271dbe873a2200ed4b613ba8a2a5efe760101
BYTE_EXACT_MATCH True
FULL_LOCAL_UI_MARKER True
NOAUTH_STATUS 403
PROCESS_TREE_TERMINATED 6000
```

### 8.5 Fallback `download.json` generator — output for Agent A (lead to copy)

```
python -m keel.release fallback --out release/download.fallback.json
  output: C:\Users\Admin\Desktop\keel-frontend-worktree\keel\release\download.fallback.json
  windows: Keel-Setup-0.1.1.exe          available:false verified:false url:null
  macos:   Keel-0.1.1-macos-arm64.pkg    available:false verified:false url:null
           alt Keel-0.1.1-macos-x64.pkg (arch x64)
  linux:   Keel-0.1.1-linux-amd64.deb    available:false verified:false url:null
           alt Keel-0.1.1-linux-x86_64.rpm (arch x86_64)
```

Shape: `{name, version, tag, generated:"fallback", published_at:null, verified_at:null, base_url:null, release_manifest_url:null, channels:{windows,macos,linux}}`; every channel has `size:null`, `sha256:null`, `url:null`, `available:false`, `verified:false`, `verified_at:null`. **I did not write `site/download.json`** — that remains Agent A's file. Generated asset list above is the exact replacement payload.

### 8.6 Release pipeline and CI gates

The existing release manager is reused unchanged in intent: `build → verify → checksum → manifest → publish only verified assets → download-back verify → verify signatures`. `build-desktop.yml` now runs independent `validate-versions → build-{windows,macos,linux} → verify-{windows,macos,linux} → verify-release-signatures → publish` stages. Each `build-*` runs static packaging/UI checks on its native runner before electron-builder; each `verify-*` checks the artifact inventory, runs `dry-run`, and inspects the native package structure (`Get-AuthenticodeSignature`, `pkgutil --expand` + `xmllint` + `lsbom`, `dpkg-deb -c/-f` + `rpm -qpl`). Publication still requires the Ed25519 signing gate and only uploads `download.json` after public HTTPS download-back verification; availability is never fabricated.

### 8.7 Routed security findings (Agent B / Agent F) — fixed

- **Agent B `load_manifest` scheme gap and SEC-F-03**: added a positive allowlist `_url_allowed()` (HTTPS only; loopback HTTP only with `allow_http=True`). `file://`, `ftp://`, `data:`, protocol-relative and plaintext public HTTP are rejected in `fetch_bytes`, `load_manifest`, `verify_manifest`, `verify_release_manifest` and the download alternatives loop. `_looks_like_url()` keeps Windows drive paths working as local files.
- **SEC-F-07**: `_ValidatingRedirectHandler` + `_open_url()` re-validate every redirect hop as HTTPS (or explicit loopback HTTP), with a 2-hop limit, replacing bare `urllib.request.urlopen` in both `fetch_bytes` and `load_manifest`.
- **SEC-F-06**: `checkForUpdates()` in `main.js` now fails closed (`if (!manifest || !key) return;`). `UpdatePlan` carries `signature_verified`, and the CLI emits an explicit `signatureVerified` boolean in the advisory JSON. No unsigned plan is presented as verified.
- Regression tests added: `tests/test_release_verify_url_policy.py` (8 tests: scheme rejection, redirect hop validation/limit, signature flag) and `tests/test_packaging_config.py` (7 static-packaging tests).
- Agent F's `tests/verify_distribution_security_pipeline.py` (xfail markers since removed by Agent F) now passes in full:

```
python -m pytest -q tests/verify_distribution_security_pipeline.py
  18 passed in 1.95s
```

### 8.8 Tests run (exact commands and results)

```
python -m pytest -q tests/test_release_manager.py tests/test_platform_targets.py \
  tests/test_packaging_config.py tests/test_release_controls.py tests/test_release_signing.py \
  tests/test_signing_gate.py tests/test_release_hardening.py tests/test_release_integrity.py
  64 passed, 1 skipped in 42.16s

python -m pytest -q -rxX tests/test_release_verify_url_policy.py \
  tests/verify_distribution_security_pipeline.py tests/verify_distribution_security_desktop.py
  40 passed, 3 xpassed in 10.04s      # xpasses were SEC-F-03, SEC-F-07, SEC-F-06

python -m pytest -q tests/verify_distribution_security_pipeline.py tests/verify_distribution_security_desktop.py \
  tests/test_packaging_config.py tests/test_release_manager.py tests/test_platform_targets.py \
  tests/test_release_verify_url_policy.py tests/test_updater.py
  72 passed in 15.89s

python -m pytest -q <all verify_distribution_*.py>
  97 passed, 2 failed -> after updating the redirect-aware monkeypatch target and a
  flaky bridge test re-run: 25 passed in 10.75s for the two affected files.
```

An earlier full `python -m pytest -q` run (mid-round, 697s) reported `4473 passed, 52 skipped, 3707 subtests passed, 8 failed`. One of those failures (`test_updater.py::test_electron_update_check_is_opt_in`) was caused by my SEC-F-06 guard and was fixed by updating that assertion. **Final full-suite run after all fixes:**

```
python -m pytest -q
  5 failed, 4489 passed, 53 skipped, 3707 subtests passed in 497.75s (0:08:17)
  FULL_SUITE_EXIT=1
  FAILED tests/test_accessibility_hardening.py::test_form_controls_have_labels_or_aria_names
  FAILED tests/test_accessibility_hardening.py::test_landmarks_language_and_skip_link
  FAILED tests/test_accessibility_hardening.py::test_no_duplicate_ids_or_attributes
  FAILED tests/test_accessibility_hardening.py::test_controls_are_keyboard_operable
  FAILED tests/test_accessibility_hardening.py::test_dialogs_and_popups_have_accessible_names
```

All five remaining failures are in `tests/test_accessibility_hardening.py` (Agent A/G's site-UI area, e.g. `chip-env` has `aria-haspopup="true"` where the test expects `"dialog"`). They reproduce when that file is run alone and predate this round; none are in `desktop-app/**`, `src/keel/release/**`, packaging acceptance, or the release workflows. The earlier `test_os_sandbox::test_concurrent_confinement` and `test_quick_ask::test_quick_ask_endpoint_uses_real_runtime` failures did not recur.

### 8.9 External gates / blockers (truthful)

1. **macOS PKG: NOT BUILT HERE.** This host is Windows; `pkgbuild`/`productbuild`/`codesign`/`notarytool` and a macOS SDK are unavailable. `build-desktop.yml` and `verify-install.yml` configure `macos-latest` runners and the exact commands, but no `.pkg` was produced locally. No Apple signing or notarization is claimed.
2. **Linux DEB/RPM: NOT BUILT HERE.** No dpkg/rpm toolchain on this host. Native `ubuntu-latest` jobs are configured; no `.deb`/`.rpm` was produced locally. No distro package signing is configured.
3. **OS signing: UNCONFIGURED.** electron-builder explicitly logged "no code signing certificate configured, signing is skipped". The Windows EXE is unsigned. Optional secret wiring exists for Windows Authenticode, Apple Developer ID + notarization, but no credential was present, so no OS signature or notarization is fabricated. Keel's Ed25519 release signing remains a separate, owner-supplied key gate.
4. **Public availability: NOT PUBLISHED.** No release was created, no manifest published, no URL verified. All channels in the generated fallback are `available:false`, `verified:false`, URL/size/SHA-256 null.
5. **Tauri** remains blocked by the missing MSVC `link.exe` (§6); no Tauri build is claimed.
6. No commits or pushes were made. Agent A's `site/**` and other agents' docs were left untouched; only their tests whose assertions directly contradicted the new native-installer/security contract were minimally updated (`test_platform_targets.py`, `test_release_manager.py`, `test_updater.py`, and Agent F's untracked desktop distribution-security test `.pkg` allowlist + redirect monkeypatch target).
