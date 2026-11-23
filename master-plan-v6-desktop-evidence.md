# Master Plan v6 — Electron desktop hardening evidence

**Agent:** 28 (Electron desktop specialist)
**Branch:** `agent/f-desktop`
**Baseline:** `463481edb0f325e9250d9dd5bf559ff5f138a55d`
**Date:** 2026-11-23
**Environment:** Windows 10 AMD64, Node v24.22.2, Python 3.11.9, pytest

## Scope

Validated the Electron main process, sidecar lifecycle, token parsing, window
lifecycle, navigation/IPC surface, packaged resource paths and exit cleanup.
Only the owned files were edited. No new dependencies; no packaging behavior
that already works was changed.

## Defects found and fixed

| # | Severity | Location (baseline → fixed) | Defect | Fix |
|---|----------|------------------------------|--------|-----|
| D1 | High | `main.js:224-229` → `main.js:289-298` | Startup failure path calls `app.exit(1)`, which does **not** emit `before-quit`/`window-all-closed`, so the spawned sidecar survived as an orphan. This is the mechanism behind the two `keel.exe serve --port 8896/8897` orphans recorded in `master-plan-v6-release-acceptance-addendum.md:19` that held `dist\keel-sidecar\keel.exe` open and broke a build. | `stopSidecar()` is called before `app.exit(1)` in the error path. |
| D2 | High | `main.js:233-238` → `main.js:27-47, 303-306` | `sidecar.kill("SIGTERM")` on Windows maps to `TerminateProcess` on the PyInstaller one-file bootloader only. The child it spawns (which owns the listening socket / open EXE) was left running. Cleanup existed only in `before-quit`. | Added one `stopSidecar()` helper: on Windows `taskkill /PID <pid> /T /F` reaps the whole tree (fallback `proc.kill()`), elsewhere `SIGTERM`; it is invoked from `before-quit`, from the main window's `closed` handler, and from the failure path. The helper nulls the handle before killing, so cleanup is idempotent. |
| D3 | Medium | `main.js:53` → `main.js:94-110` | Token parsing used a brittle regex fixed to `[A-Za-z0-9_-]+`; any token containing `=`, `.` or other URL-safe characters was silently truncated, producing an invalid `?t=`. | Match the URL with `\S+`, then validate it with the WHATWG `URL` API (`http:` + `127.0.0.1` + non-empty `t`), and resolve the exact matched string so the token is preserved byte-for-byte. The caller also parses with `new URL()` instead of a second regex (`main.js:286-288`). |
| D4 | Medium | `main.js:56-57` → `main.js:78-87` | On a successful match, `removeAllListeners("data")` also detached the `stdout.pipe(log)` / `stderr.pipe(log)` streams installed in `startSidecar()`, silently ending the diagnostic log at startup. | Remove only the parser's own listeners (`removeListener("data", onData)`, plus `error`/`exit`), guarded by a `settled` flag so late events cannot reject an already-resolved promise. |
| D5 | Medium | `main.js:193-199` → `main.js:249-265` | `setWindowOpenHandler` allowed any non-http(s) scheme (`file:`, `javascript:`, `data:`) to load inside the renderer, and its loopback check was a raw `startsWith`. | Parse with `URL`; loopback stays in the shell, other web links go to `shell.openExternal`, every other scheme is denied. Renderer already had `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`, `preload: undefined` — preserved. |
| D6 | Low | `main.js:138` → `main.js:192-196` | `checkForUpdates()` spawned a child with no `error` listener; when the update manifest is configured and the binary is missing, Node emits an unhandled `error` and crashes the whole shell over an advisory check. | Added a no-op `error` listener (startup remains best-effort; malformed output was already swallowed). |

### Reviewed, no defect / no change

- `keel/desktop-app/launcher.py` — correct absolute import (`keel.cli.main:main`)
  and `raise SystemExit(main())`; no change.
- `keel/desktop-app/sidecar.spec` — one-file EXE with `console=True` (required so
  the bridge's URL line reaches stderr), `bootloader_ignore_signals=False`, and
  the UI data layout matching `uiRoot()`; no change. The one-file child process
  is exactly why the D2 tree-kill is needed.
- `keel/desktop-app/build/nsis-keel.nsh` — per-user install, no elevation, user
  data preserved; no change.
- **IPC:** the shell imports no `ipcMain` and defines no IPC handlers. The
  renderer has no preload and no node integration, so there is no unrestricted
  `fs` IPC surface to fix in this version. Access to local files is mediated by
  the authenticated loopback bridge (`?t=<token>` cookie/header), not IPC.
- Packaged paths: `bundledSidecar()` and `uiRoot()` resolve from
  `process.resourcesPath` into `keel/keel.exe` and `site`/`desktop/ui`, which
  matches the extraResources layout verified by the release addendum. `__dirname`
  is used only for files that ship beside `main.js` (`splash.html`, `build/icon.ico`)
  and is correct in both dev and packaged layouts. No change.

## Regression tests

New file: `keel/tests/test_desktop_hardening.py` (14 tests). It asserts the
source-level lifecycle contracts above, runs `node --check main.js` when Node is
available, launches the real bridge on an ephemeral port and verifies the stderr
URL contract with a token containing `.` and `=` (which the old regex truncated),
and — on Windows — demonstrates that `taskkill /PID <parent> /T /F` reaps a
grandchild, i.e. the exact invariant the orphan fix depends on. The launch test
uses a plain `python -m keel` process, so it creates no new orphans.

Baseline detection was verified by temporarily restoring the baseline `main.js`
and rerunning the suite: **8 failed, 4 passed**. With the fix applied: all pass.

## Commands and results

```
cd keel/desktop-app && node --check main.js
NODE_CHECK_EXIT=0

cd keel && python -m pytest tests/test_desktop_hardening.py \
  tests/test_desktop_management.py tests/test_desktop_artifacts.py \
  tests/test_installer_smoke.py -q
32 passed, 3 skipped in 12.14s
```

Baseline (temporary swap, restored immediately afterwards):

```
cd keel && python -m pytest tests/test_desktop_hardening.py -q
8 failed, 4 passed in 4.49s
```

No packaging behavior was altered and no dependency was added.
