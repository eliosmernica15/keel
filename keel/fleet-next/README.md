# fleet-next — Keel Fleet, NextJS + PWA

Next.js (App Router, TypeScript) frontend for Keel Fleet. The existing Python
bridge (`keel fleet`) remains the backend — this app is a thin browser client
plus a same-origin BFF proxy. The classic vanilla UI in `desktop/fleet/` is
untouched and remains the reference implementation.

## Run it

```powershell
# 1. Start the bridge if it isn't running (default port 8739)
cd "C:\Users\Admin\Desktop\Claude clone\keel"
$env:PYTHONPATH='src'; python -m keel fleet

# 2. Point this app at it — copy the bridge token printed by step 1
copy .env.example .env.local
notepad .env.local   # set KEEL_BRIDGE_TOKEN to the current token

# 3. Serve
npm install
npm run build
npm start            # http://127.0.0.1:3000  (binds 127.0.0.1 only)
```

**Token rotation:** the bridge token changes every time `keel fleet` restarts.
Update `.env.local` and restart this app after any bridge restart.

## Install as an app (PWA)

Open `http://127.0.0.1:3000/` in Chrome or Edge → install icon in the address
bar (or menu → “Cast, save, and share → Install page as app…”). Standalone
window, manifest + service worker included. The service worker caches only
the app shell — **API traffic is never cached**.

## What it does / what it doesn't

Done: agent rail + create (provider or Echo), live chat with SSE streaming,
steps fold, inline approval cards (Allow once / Always allow / Don't allow),
ENGINE tab (provider/model save, session-key validation + model catalog via
the bridge's `/api/fleet/providers/credential*` endpoints — keys never touch
disk or this process's storage, gone on restart), NOTES tab, Tasks (list /
create), Library (list / download), Routines (list / Run now).

**Four surfaces in the top bar** (2026-11-13):

- **Keel Cowork** — the desktop app, for everything that isn't a code session.
  Hero home ("You're here.") with a big composer and quick-start idea cards;
  sidebar pages: **Projects** (create/trust/remove folders, open in Code),
  **Artifacts** (Keel's library across all agents, inline preview/download,
  "What needs my attention"), **Scheduled** (Keel routines: create from
  templates or scratch, run-now/pause/delete, and a real Keep-awake switch
  backed by a `SetThreadExecutionState` process on Windows), **Customize**
  (Skills from the bundled library and your `~/.keel/skills` with injection-
  flag counts, MCP **Connectors** resolved from settings, and an honest
  "no plugin system yet" page).
- **Keel Code** — the coding session. Same agent engine and transcript;
  right rail with **Environment** (This computer + folder, "Save" pins it as
  the default workspace), **Context** (real tokens recorded by the bridge;
  % of the model's context window when the catalog exposes it), and
  **Connectors**. Permission dropdown: Build / Accept edits / Plan / Autopilot.
- **Keel Duet** — project coding with tabs (Review / Terminal / Open file /
  Browser / file tabs) — unchanged.
- **Fleet** — agents, tasks, library, routines management — unchanged.

**Trust gate**: picking a folder for the first time shows "Trust this
workspace?" — Keel only reads/writes a folder you've explicitly trusted.
Trust is stored per folder, revocable from Projects.

Composer `+` menu (all surfaces): Add files or photos (Ctrl+U), Add folder,
Slash commands, Manage connectors.
 Left rail = project registry (paste an absolute folder path to
pick any folder on your computer; add/remove never deletes files) + collapsible
file tree (4,000-entry cap, VCS/deps skipped). Right pane = tabs: **Review**
(git status/log/diffstat, read-only), **Terminal** (detached commands, streamed
output, project cwd), **Open file** (quick path), **Browser** (sandboxed iframe
preview of dev servers — not a general browser), plus per-file tabs with edit
+ save (text ≤ 1.5 MB; images preview; other binaries say so). The paperclip
accepts every file type. `/` opens the slash palette (`/context`, `/model`,
`/shell`, `/review`, `/open`, `/help`). Sub-agents (`Task`) stay automatic —
the model delegates when a job warrants it. Background shells pill + Ctrl+B
works in both surfaces.

Not yet (use the classic UI for these): Groups, routine creation, library
upload/deletion, library previews, per-agent permission policy management,
audit log view. Offline use of the API is not supported (shell only).

## Security notes

- Token lives only in `.env.local` on this machine and is injected
  server-side by the BFF (`/api/bridge/[...path]`); it never reaches the browser.
- BFF binds same-origin, `127.0.0.1`-only; path traversal is rejected
  (`..` segments); browser cookies are not forwarded upstream.
- CSP: `default-src 'self'`; `script-src 'self' 'unsafe-inline'` is required
  by stock NextJS bootstrap chunks (the classic `/fleet` keeps its stricter
  `script-src 'self'`).
- No provider keys are stored anywhere. Session keys flow through the bridge,
  live in its process memory only, and die with it.
- This is **not** a production deployment: localhost, your token, your bridge.
- `fleet.db` is shared with the classic UI — they see the same data.

## Honest status

The harness behind it (Python, F1–F4) is browser- and test-verified
(414 tests); the live model round-trip remains **blocked on this host** —
no provider credentials. Nothing here is a production-readiness claim.
