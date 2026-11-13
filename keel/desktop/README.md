# Keel Desktop — website + PWA (primary) · Tauri shell (optional)

Two ways to run Keel Desktop:

## A. Website / PWA — this works TODAY, no toolchain needed

```
keel serve                  # serves on http://127.0.0.1:8739
# prints: keel webapp running at http://127.0.0.1:8739/?t=<token>
```

Open the printed URL in your browser. The app:

- serves the Keel UI (same `ui/` folder as the Tauri shell)
- `GET /api/health` → version; `GET /api/providers` → key status
- `POST /api/run` → `keel -p "<prompt>" --output-format stream-json` streamed
  straight into the transcript; bypass mode requires `accept_risk=true`
- **Installs as a PWA** (Chrome/Edge: install icon in the address bar, or
  ⋯ → "Install Keel"). Manifest: `manifest.webmanifest`; app-shell service
  worker: `sw.js` (cache-first, offline-capable shell — the shell opens with
  the built-in demo fixture when the bridge is unreachable; actual runs need
  the bridge running).

Security model (honest): binds **127.0.0.1 only**; a fresh URL token per launch
(no token → 403); non-GET requests with a mismatched `Origin` → 403; the app
shell is cached locally by the service worker; API calls go to the network
only. If you want a shell with zero cookie/query surface, use a private
browser profile and `nuke` the service worker between sessions.

Local only. There is no hosted version — a browser can not spawn processes,
so the "website" *is* your local bridge.

### Verified

- `keel serve` on 127.0.0.1:8739 — index loads with token, sets a
  `SameSite=Strict` `keel_token` cookie, `/api/health` → `{ok:true}`,
  `/api/providers` → live registry, `/api/run` streams real NDJSON events
  (init → assistant → result → `bridge done`).
- Cookie-only auth works after the first token visit (needed for installed PWA
  start URL).
- `tests/test_webapp.py` — 11 bridge tests pass (token enforcement, cookie
  fallback, origin check, path traversal blocked, `/api/run` streaming with
  both `done` marker and real keel event stream).

## B. Tauri native shell — on hold until Windows finishes the Restart

The Build Tools VCTools payload is pending the required reboot (winget said
"Restart your PC to finish installation"; `resume` completed without deploying
it, needs reboot to extract). After reboot:

```powershell
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
cd "C:\Users\Admin\Desktop\Claude clone\keel\desktop\src-tauri"
cargo run --release
```

That path spawns `keel -p … --provider … --output-format stream-json` and is
the "real" window. Do not attempt until the reboot lands.

## What the website is not

- Not a public, hosted product — the bridge *is* the product on your machine.
- Not a model — Keel itself still has no provider wired up by this repo; set
  your own keys (`KEEL_OPENROUTER_API_KEY`, etc.).
- Not offline-capable for real runs — the PWA caches the app shell only;
  `keel serve` must be running for any real work. Over http, if the bridge
  fails mid-run the UI shows a backend error, not a fake result (the
  fixture demo exists only for `file://` opens).

## Layout

```
desktop/
  ui/             vanilla HTML/CSS/JS app (shared by PWA and Tauri)
  ui/icons/       PWA icons (192/512)
  manifest.webmanifest
  sw.js           app-shell service worker
  src-tauri/      optional native shell (on hold for the reboot)
  README.md
```
