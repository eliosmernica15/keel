# Agent 29 — Web / PWA surface hardening evidence

Worktree: `C:\Users\Admin\.local\share\opencode\worktree\final\web-pwa`
Branch: `agent/f-web-pwa` · Baseline: `463481e`

## 0. What is actually served where

The packaged Electron app sets `KEEL_UI_DIR` to the bundled `site/` tree
(`keel/desktop-app/main.js:36-45,81`), and the Python sidecar serves it
(`keel/src/keel/webapp.py:71,294-307`). So `keel/site/app.html` +
`keel/site/ui/app.js` are **the real UI served by the real bridge**, not just
a static marketing mirror. The PWA assets served by that same bridge come
from `keel/desktop/` (`webapp.py:72,332-339`). This is why defects in the
`site/` UI and the `desktop/` SW are defects against the live backend.

## 1. Endpoint cross-check (app.js fetch/EventSource vs webapp.py)

Line numbers are from the baseline commit `463481e`.

| app.js line | Call / target | Method | Bridge route | Verdict |
|---|---|---|---|---|
| 161 | `/api/model-catalog/${name}` | GET | `webapp.py:379` `path.startswith("/api/model-catalog/")` | OK |
| 164 | `def.catalogUrl(key)` (OpenRouter/Google) | GET | external provider, by design | n/a |
| 212 | `/api/surfaces` | GET | `webapp.py:488` | OK |
| 283 | `def.chat(...).url` (provider stream) | POST | external provider, by design | n/a |
| 362 | `/api/health` | GET | `webapp.py:340` | OK |
| 376 | `/api/v2/sessions/${stored}` | GET | `webapp.py:289` → `_v2_sessions` `:1037` | OK |
| 389 | `/api/v2/sessions` | POST | `webapp.py:666,1002` | OK |
| 414 | `/api/v2/sessions/${id}/messages` | GET | `webapp.py:1056` | OK |
| 504 | `/api/v2/sessions/${id}/${decision}` (`approve`/`reject`) | POST | `webapp.py:1198` | OK |
| 530 | `/api/v2/sessions/${id}/pending` | GET | `webapp.py:1233` | OK |
| 544 | `/api/v2/sessions/${id}` | GET | `webapp.py:1037` | OK |
| 639 | `/api/v2/sessions/${id}/events?since=` (EventSource) | GET | `webapp.py:1139` | OK |
| 666 | `/api/v2/sessions/${id}/messages` | POST | `webapp.py:1056` | OK |
| 696 | `/api/v2/sessions/${id}/cancel` | POST | `webapp.py:1246` | OK |
| 1300 | `/api/files/search?query=&limit=` | GET | `webapp.py:495` | OK |
| 1872 | `mdef.verifyUrl(key)` (provider key check) | GET | external provider, by design | n/a |
| 2051 | `/api/health` | GET | `webapp.py:340` | OK |
| 2120 | `/api/fs/list${q}` | GET | `webapp.py:446` | OK |
| 2289 | `/api/workdir` | POST | `webapp.py:786` | OK |
| 2391 | `/api/kill-switch` | POST | `webapp.py:678` | OK |
| 2425 | `/api/quick-ask` | POST | `webapp.py:856` | OK |
| 2458-2459 | `/api/capabilities?surface=` | GET | `webapp.py:456` | OK |
| 2506, 2580, 2914, 3006, 3076 | `/api/capabilities/invoke` | POST | `webapp.py:540` | OK |
| 2964 | `/api/workdir` | GET | `webapp.py:508` | OK |

**Mismatches: none.** Every bridge-targeted call in `app.js` maps to a route
the bridge registers. The Developer pane's documented endpoints
(`app.html:535-549`) also all resolve (`fleet/routes.py:144,423,505,560,669,705`).
The defects were behavioural, not missing routes — see below.

Live probe (real `make_server(0)`, token-authenticated) confirmed the routes
answer 200 and also exposed the broken navigation target:

```
/                            -> 200
/app                         -> 200
/ui/app.js                   -> 200
/ui/management.js            -> 200
/manifest.webmanifest        -> 200
/sw.js                       -> 200
/api/health                  -> 200  {"ok": true, "version": "0.1.1"}
/api/surfaces                -> 200
/api/capabilities            -> 200
/api/model-catalog/google    -> 200
/api/files/search?query=x    -> 200
/api/fs/list                 -> 200
/api/workdir                 -> 200  {"path": null}
/download                    -> 404  {"error": "not_found"}   <-- dead link
```

## 2. Defects found and fixed

### D1 — Local-only controls gated on a permanently-false mock flag (disconnected controls)
`mkBridge()` (`app.js:332-340`) hard-codes `live: false`, but seven call sites
used `bridge.live` as "is the local bridge available?". The real probe is
`agent.ready`, set from `GET /api/health` (`app.js:360-368`). Consequences in
the installed app, with a live backend:

- `applyWorkdir()` (`:2284`) never POSTed `/api/workdir` — folder binding was inert.
- `openFsPicker()` / `loadFs()` (`:2106,:2116`) never opened `/api/fs/list`.
- `refreshAtMenu()` (`:1298`) never used `/api/files/search` (`@file` completion).
- `loadSurfaceConfig()` (`:210`) never fetched `/api/surfaces`.
- kill switch (`:2389`) never POSTed `/api/kill-switch`.
- legacy `bridge.listen(...)` block (`:2974-2983`) was unreachable.

**Fix:** all gates now use `agent.ready`; the legacy mock listener block was
removed. The `+ → Select folder as workspace…` and footer `Open folder…`
controls now route to the bridge's real directory browser when it is live,
and keep the honest browser-only binding otherwise.

### D2 — Surface badge never populated (mock-only state)
`loadSurfaceConfig()` keyed `surfaceConfig` by backend `s.id`
(`cowork`/`code`/`duet`/`fleet`) while `applySurfaceBadge()` looks up
`state.surface` (`chat`/`code`) — so `.surface-agent-badge` stayed blank even
after D1 was fixed. Verified real payload: `[(cowork, chat), (code, code),
(duet, code), (fleet, chat)]`.
**Fix:** index by `s.view` with first-entry-wins, so `chat → Keel Cowork` and
`code → Keel Code`.

### D3 — Auth failure after global stop (stale token)
`fsToken()` (`app.js:170-175`) prefers `?t=` from the URL over `sessionStorage`.
`/api/kill-switch` rotates the server token; the handler stored the new token
in `sessionStorage` only, so every subsequent request kept sending the revoked
`?t=` and got 403. `keel/site/ui/management.js:13-16` has the same preference,
so it broke too.
**Fix:** after rotation, rewrite the launch URL with
`history.replaceState(..., ?t=<new token>)`, keeping both readers in sync.

### D4 — Stale / incomplete PWA shell cache
`keel/desktop/sw.js` was still `keel-shell-v5`, although at least eight commits
after the v5 bump changed shell assets (tutorial, accessibility, admin,
policy, management integration). Installed PWAs kept serving the v5
`app.js`/`style.css`. The precache list also omitted `/ui/management.js`
(loaded by `app.html:699`) and the two larger manifest icons.
**Fix:** `VERSION = "keel-shell-v6"`; added `/ui/management.js`,
`icon-512.png`, `icon.png` to `SHELL`. Verified every SHELL path resolves in
both source and packaged UI trees; `/api/` still bypasses the cache.

### D5 — Broken navigation
`nav-download` (`app.html:125`) points at `/download`, which the bridge does
not register (live 404 above) — inside the installed app it renders raw JSON.
`nav-back`/`nav-forward` called `history.back()/forward()` in a single-window
app shell with no history, so they were permanent no-ops.
**Fix:** hide the Download link when `agent.ready`; track a nav cursor and
disable Back/Forward when there is nothing to traverse (with matching
`:disabled` styling in `keel/site/ui/style.css`).

## 3. Files changed (owned files only)

- `keel/site/ui/app.js` — D1, D2, D3, D5
- `keel/site/ui/style.css` — disabled toolbar-button styling (D5)
- `keel/desktop/sw.js` — D4
- `keel/tests/test_web_surface_hardening.py` — new, 8 regression tests
- `master-plan-v6-web-pwa-evidence.md` — this file

No backend, packaging or routing files were edited. No new features were added.

On "fake success text": a full sweep of the owned files found no hardcoded
status string that claims success without a real response — status text is
already conditional on `res.ok` / saved state (e.g. `save-instructions`, key
verification, policy activation, admin overview). Nothing was invented or
removed there; the misleading text found in the UI was the *unavailable*
claim in `applyWorkdir()`/`openFsPicker()`, which fired in the installed app
because of D1 and was corrected above.

## 4. Commands and results

```
$ node --check keel/site/ui/app.js
$ node --check keel/desktop/sw.js
JS SYNTAX OK

$ python -m pytest keel/tests/test_web_surface_hardening.py -q
........                                                                 [100%]
8 passed in 3.37s

$ python -m pytest keel/tests/test_security_validation.py \
    keel/tests/test_document_endpoints.py keel/tests/test_admin_page.py \
    keel/tests/test_web_surface_hardening.py keel/tests/test_capability_ui.py \
    keel/tests/test_quick_ask.py keel/tests/test_kill_switch.py \
    keel/tests/test_tutorial_ui.py keel/tests/test_policy_ui.py \
    keel/tests/test_website_download_only.py keel/tests/test_desktop_management.py -q
........................................................................ [ 98%]
.                                                                        [100%]
73 passed in 45.39s

$ python -m pytest keel/tests/test_webapp.py -q
...............                                                          [100%]
15 passed in 32.24s
```

Note: one earlier run of `test_webapp.py::test_run_streams_events_and_done_marker`
timed out while the machine was under load; the isolated rerun above passed
15/15. No source change was made to the bridge.

Regression test coverage (8 tests): AST-extracts the routes registered by
`webapp.py` and asserts every `/api/...` literal in `app.js` is one of them;
asserts fetch literals are API routes or external provider URLs; asserts no
dead `bridge.live` gates remain and the workdir/fs/kill controls probe the
real bridge; asserts the rotated token is written back to `?t=`; asserts no
dead Download link and working nav-state logic; asserts manifest + SW assets
exist, the SW version is >= 6, every cached asset and manifest icon resolves,
and the manifest theme matches the shell; asserts Node syntax; and probes the
referenced GET endpoints against a real bridge instance.
