# Packaged-context frontend compatibility suite

## What this verifies

A **production** Next app (`next build` + `next start`) is served on a
deliberately non-3000 loopback port (`127.0.0.1:3471` by default) with the
bridge credential held only by the server process — the same shape the unified
Electron renderer uses. Every bridge response is **FIXTURE** data served by
`fixture-bridge.mjs` on `127.0.0.1:3472`; the browser reaches it only through
the real same-origin `/api/bridge/*` BFF. No Python runtime, credentials or
external network calls are involved.

Covered: all seven unified surfaces, production CSP/assets, first-paint theme
for dark/light/system, persistence across reload, voice dictation (mocked
`SpeechRecognition`), Fleet transcript export/rewind/restore and task undo,
Get Keel Desktop entry, PWA manifest/shortcut/start URL/service worker, and the
token boundary at the BFF.

Specs whose name starts with `FIXTURE:` (or whose header says so) use a
deterministic stand-in for a browser/backend capability; all other cases run
against the real production build and BFF.

## Commands

From `keel/fleet-next`:

```powershell
npx tsc --noEmit
npx playwright test --config tests/packaged-compat/playwright.config.ts --workers=1 --reporter=list
```

The config builds into the isolated `.next-packaged-compat` directory and starts
both servers itself; no manually started preview is required. Ports can be
overridden with `KEEL_COMPAT_APP_PORT` / `KEEL_COMPAT_BRIDGE_PORT`.

## Scope

Owned files: `features/**` and this directory. No app shell, build config,
package, Python, docs or desktop-shell file is modified by this suite.
