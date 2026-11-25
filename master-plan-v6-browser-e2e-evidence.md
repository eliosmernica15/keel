# Master Plan v6 — Browser / HTTP Bridge E2E Evidence (Agent 44)

- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\final\browser-e2e`
- Branch: `agent/f-browser-e2e` — baseline `463481e`
- Environment: Python 3.11.9, Windows, pytest, `keel` 0.1.1
- Files owned/changed: `keel/src/keel/webapp.py` (HTTP routes/handlers only),
  `keel/tests/test_bridge_e2e_hardening.py` (new), this evidence file.

## How the bridge was exercised

`Bridge` in the new test module starts `webapp.make_server(0)` in a daemon
thread on an ephemeral loopback port, sets `webapp._TOKEN` to
`e2e-bridge-token-9f3c21`, binds `webapp._WORKDIR` to a pytest `tmp_path`, and
points `KEEL_STATE_DIR` / `settings_store.STATE_DIR` there. Every request below
is a real `urllib.request` / `http.client` call over TCP; no handler method was
invoked directly. `X-Keel-Token` was sent unless a test deliberately omitted or
spoofed it.

**Environment caveat (reported, not a code defect):** an editable install on
this machine maps `import keel` to `C:\Users\Admin\Desktop\Claude clone\keel`.
All validation commands therefore set
`PYTHONPATH=C:\Users\Admin\.local\share\opencode\worktree\final\browser-e2e\keel\src`
so the worktree copy under test is the one imported (verified via
`keel.webapp.__file__`). Without it, pytest silently exercises the other
checkout.

## Requests exercised and exact responses (post-fix)

Representative live traffic captured from the same `Bridge` client:

| # | Request | Status | Response (abridged only where noted) |
|---|---------|--------|--------------------------------------|
| 1 | `GET /api/health` (no token) | 403 | `{"error": "refused", "reason": "bad token or origin"}` |
| 2 | `GET /api/health` (token) | 200 | `{"ok": true, "version": "0.1.1"}` |
| 3 | `GET /api/health?t=e2e-bridge-token-9f3c21` | 200 | `{"ok": true, "version": "0.1.1"}` |
| 4 | `GET /api/capabilities` | 200 | 226 capabilities; Cowork, Code, Duet and Fleet all present; `?surface=fleet` → 16 entries, all `surface=fleet` |
| 5 | `POST /api/capabilities/invoke {"id":"core.hardware.detect","params":{}}` | 200 | `{"ok":true,"capability":"core.hardware.detect","result":{"os":"Windows","arch":"AMD64","cpu_count":16,"ram_gb":null,"python":"3.11.9"},"elapsed_ms":62.0}` |
| 6 | `POST /api/capabilities/invoke {"id":"cowork.doc.qa",...}` | 200 | `{"ok":true,...,"result":{"hits":[...]}}` |
| 7 | `POST /api/capabilities/invoke {"id":"code.sandbox.run","params":{"code":"print('bridge-e2e')","timeout_s":5}}` | 409 | `{"error":"confirmation_required","capability":"code.sandbox.run","permission":"execute"}` |
| 8 | same + `"confirm":true` | 200 | `{"ok":true,"capability":"code.sandbox.run","result":{"ok":true,"stdout":"bridge-e2e\r\n","stderr":"","exit_code":0,"timed_out":false},"elapsed_ms":281.0}` |
| 9 | `POST .../invoke` with `Origin: https://evil.test` | 403 | `{"error":"refused","reason":"bad token or origin"}` |
| 10 | `POST /api/workdir {"path":"C:\\...\\bridge-evidence-equb99z0"}` | 200 | `{"ok":true,"path":"C:\\Users\\Admin\\AppData\\Local\\Temp\\bridge-evidence-equb99z0"}` |
| 11 | `GET /api/workdir` | 200 | `{"path":"C:\\Users\\Admin\\AppData\\Local\\Temp\\bridge-evidence-equb99z0"}` |
| 12 | `POST /api/workdir {"path":null}` (reset) / bad path | 200 / 400 | `{"ok":true,"path":null}` / `{"error":"not a directory","path":...}`; bad path leaves workdir unchanged |
| 13 | `GET /api/fs/list?path=<workdir>` | 200 | `{"ok":true,"path":...,"parent":...,"roots":["C:\\"],"dirs":[{"name":"state"}],"truncated":false}` — directory names only |
| 14 | `GET /api/fs/list?path=<file>` / `?path=<.. traversal>` | 400 / 200 | `{"error":"not a directory",...}` / names only, never file contents; `TOP SECRET FILE CONTENT` absent in all cases |
| 15 | `GET /api/fs/list?path=C:\Users%00` | 400 | `{"error":"bad path"}` (was a dropped connection — defect 2) |
| 16 | `POST /api/upload {"name":"note.txt","contentB64":...}` | 200 | `{"ok":true,"path":"...\\state\\uploads\\...-note.txt","bytes":12}`; bytes round-trip |
| 17 | `POST /api/upload {"name":"../../evil.txt","contentB64":"cGF5bG9hZA=="}` | 200 | `{"ok":true,"path":"...\\state\\uploads\\20261123-194343-de5d7b-evil.txt","bytes":7}` — traversal stripped, file stays inside uploads. Same for `..\..\evil2.txt`, `C:\Windows\evil3.txt`, `..`, `....//evil4.txt` |
| 18 | `POST /api/upload` invalid base64 / missing fields / no token / bad origin | 400 / 400 / 403 / 403 | `{"error":"contentB64 is not valid base64"}` / `{"error":"name and contentB64 are required"}` / refused / refused |
| 19 | `POST /api/capabilities/invoke` with `Content-Length: abc` | 400 | `{"error":"invalid Content-Length"}` (was a dropped connection — defect 3) |
| 20 | same with `Content-Length: -1` | 400 | `{"error":"invalid Content-Length"}` (was an unbounded read / timeout — defect 3) |
| 21 | `POST /api/capabilities/invoke` body `["not","an","object"]` | 400 | `{"error":"body must be an object"}` |
| 22 | `GET /api/providers`, `/api/surfaces`, `/api/gateway`, `/api/v2/sessions`, `/api/settings`, `/api/fleet/bots` | 200 / 200 / 200 / 200 / 200 / 403 when no token | real payloads (5 providers, 4 surfaces incl. Cowork/Code/Duet/Fleet, gateway status, 6 sessions) |
| 23 | `POST /api/run {"prompt":"say hi","provider":"auto","permission_mode":"default"}` | 200 | NDJSON: `system`/`assistant`/`result` events then `{"type":"bridge","subtype":"done","exit_code":0}`; `init.cwd` equals the folder set via `/api/workdir`, proving workdir propagation |

Token-leak probe: error bodies from wrong token, missing capability, bad path,
bad base64, bad workdir and unknown route were all collected and asserted not
to contain `e2e-bridge-token-9f3c21`. Auth, Origin and CSP handling were left
intact (token in header, `?t=` query or `keel_token` cookie; non-GET Origin
must match Host; static files still send the same CSP + `nosniff`).

## Defects found and fixed (failing test written first)

### Defect 1 — confirmation bypass via truthy non-boolean (security)

Baseline reproduce, `POST /api/capabilities/invoke` with write capability
`core.flags.set`, `{"name":"x","enabled":true,"confirm":"false"}`:

```
status=200
{"ok": true, "capability": "core.flags.set",
 "result": {"enabled": true, "kill_switch": false}, "elapsed_ms": 15.0}
```

The same bypass worked with `"true"`, `1`, `["false"]` and `{"approved":False}`
for both write and execute capabilities. Failing test:
`test_confirm_must_be_a_real_boolean`:

```
E   AssertionError: confirm='false' bypassed the gate: {'ok': True, ...}
```

Fix (`webapp.py`, capabilities invoke route): require `request.get("confirm")
is not True` instead of testing truthiness. JSON `true` is the only accepted
value; the existing forwarding of `confirm` into `capabilities.invoke(...,
context={... "confirm": bool(request.get("confirm")), ...})` was preserved.
After fix all six variants return `409 confirmation_required`, real `true`
still returns `200` and actually executes the sandbox capability.

### Defect 2 — malformed folder-picker path dropped the HTTP connection

Baseline `GET /api/fs/list?path=C:\Users%00` produced a handler traceback
(`ValueError: stat: embedded null character in path` in `Path.resolve()`) and:

```
http.client.RemoteDisconnected: Remote end closed connection without response
```

Fix (`_fs_list_payload`): catch `OSError`/`RuntimeError`/`ValueError` around
`expanduser`, `resolve`, `exists`, `is_dir` and `iterdir`, and return a generic
JSON `400 {"error":"bad path"}` that does not echo attacker-controlled input.
After fix: `400 {"error": "bad path"}`.

### Defect 3 — malformed POST bodies crashed or hung request threads

Baseline evidence on `POST /api/capabilities/invoke`:

```
Content-Length: abc   -> ValueError in int(...) -> RemoteDisconnected
Content-Length: -1    -> rfile.read(-1) blocks until client timeout (TimeoutError)
JSON array body       -> AttributeError on request.get(...)
```

Fix: added one bounded `Handler._json_body(limit, too_large=...)` helper that
validates Content-Length (non-numeric/negative → `400 invalid Content-Length`,
over-limit → existing `413` messages), rejects non-object JSON with
`400 body must be an object`, and kept the existing `invalid json` response.
All POST routes now use it (capabilities, profiles, sessions, backups,
surfaces, settings + import, workdir, upload, quick-ask, run, v2 session
create/messages/approve). Existing size caps and error strings are preserved.
After fix: all three cases return normal JSON 4xx responses.

No defect was found in upload filename sanitization, path traversal on
`/api/fs/list` (names only, token-gated, as documented), token leakage in
error bodies, or the required GET/POST auth + Origin checks.

## Test results

All commands run from `<worktree>/keel` with the PYTHONPATH above.

Baseline, new suite (failures that motivated the fixes):

```
python -m pytest tests/test_bridge_e2e_hardening.py -q --tb=line
5 failed, 8 passed in 31.53s
FAILED ...::test_confirm_must_be_a_real_boolean
FAILED ...::test_fs_list_malformed_path_returns_json_error
FAILED ...::test_post_body_malformed_length_and_shape
FAILED ...::test_product_routes_require_token_and_run_streams   # 20s read timeout, raised to 90s for the slow fake CLI run
FAILED ...::test_error_responses_never_contain_token
```

After fixes, required suites plus the pre-existing webapp suite:

```
python -m pytest tests/test_bridge_e2e_hardening.py \
  tests/test_security_validation.py \
  tests/test_capabilities_integration.py \
  tests/test_webapp.py -q --tb=short
40 passed in 75.15s (0:01:15)
```

New suite alone: `13 passed in 35.46s`.

Additional regression spot-check (HTTP/session/settings/Fleet surfaces):

```
python -m pytest tests/test_endpoint_hardening.py tests/test_session_export.py \
  tests/test_settings.py tests/test_live_smoke.py tests/test_e2e_local.py \
  tests/test_start_health.py tests/test_admin_page.py \
  tests/test_fleet_approvals.py tests/test_fleet_duet_bridge.py \
  -q --tb=short
54 passed, 10 skipped in 25.22s
```

Implementation commit: `c224c9e` ("E2E harden bridge: strict confirm, bounded
JSON bodies, safe fs path errors"). A follow-up commit records this SHA in the
evidence file itself; no push was performed.
