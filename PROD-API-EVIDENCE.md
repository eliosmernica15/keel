# Production hardening evidence — API and integration

**Branch:** `agent/prod-api` · **Candidate HEAD:** `e6e7efc` · **Date:** 2026-11-24

**Files owned / changed**

| File | Change |
|---|---|
| `keel/src/keel/webapp.py` | 7 confirmed defects fixed (auth, JSON parsing, status mapping, policy/confirm consistency, audit robustness) |
| `keel/tests/test_prod_api.py` | NEW — 22 real-HTTP tests against an in-process `ThreadingHTTPServer` |
| `PROD-API-EVIDENCE.md` | NEW — this document |

No other source file, no frontend file and no push. No backend/capability/policy function is
mocked: the real `backend_workflows`, `capabilities`, `policy_enforcement`, `exec_policy`,
`capability_registry` and fleet modules are exercised end to end. Only process state is
redirected (`HOME`, `USERPROFILE`, `KEEL_STATE_DIR`, ephemeral port) to pytest's temporary
directory. One timing constant (`backend_workflows._LOCK_TIMEOUT_SECONDS`) is shortened in a
single test so a deliberately stale on-disk lock produces a deterministic error in 0.2 s
instead of the production 15 s; the real lock path still executes.

---

## 1. Endpoint audit

The bridge exposes these real routes (all gated by `X-Keel-Token` / `?t=` / `keel_token`
cookie; all POST/DELETE also gated by the browser `Origin` check):

* **Read:** `/`, `/app`, `/ui/<file>`, `/manifest.webmanifest`, `/sw.js`, `/api/health`,
  `/api/providers`, `/api/model-catalog[/<provider>]`, `/api/settings/schema`,
  `/api/models/resolve`, `/api/docx/read`, `/api/xlsx/read`, `/api/fs/roots`,
  `/api/fs/list`, `/api/capabilities`, `/api/profiles`, `/api/gateway`, `/api/surfaces`,
  `/api/files/search`, `/api/workdir`, `/api/settings`, `/api/settings/export`,
  `/api/v2/sessions[/<sid>/...]`, plus the delegated `/fleet` and `/api/fleet/*` routes.
* **Mutating:** `POST /api/capabilities/invoke`, `POST /api/backend-workflows/<name>`,
  `POST /api/profiles/{create,activate,remove}`, `POST /api/sessions/{import,stats}`,
  `POST /api/backups/{create,restore}`, `POST /api/v2/sessions[/<sid>]*`,
  `POST /api/gateway/{start,stop}`, `POST /api/kill-switch`, `POST /api/surfaces/<name>`,
  `POST /api/settings`, `POST /api/settings/import`, `POST /api/workdir`,
  `POST /api/upload`, `POST /api/quick-ask`, `POST /api/run`, plus delegated fleet POSTs.
  `DELETE /api/v2/sessions/<sid>` is also a real route.

| Audit dimension | Result |
|---|---|
| Input schema validation | Body must be a JSON object (`_json_body`); route-specific checks (strict boolean `confirm`, non-empty prompt, base64 validation, image MIME/size allowlist). Fixed: non-finite constants and deep nesting now rejected at the boundary. |
| Authentication | Token from header/query/cookie with constant-time compare. **Fixed:** non-ASCII credentials no longer crash the gate. |
| Authorization | Token + Origin on every POST; strict `confirm` on capability/workflow routes; real permission and saved-policy evaluation in the backend. **Fixed:** HTTP now pre-flights saved `prompt` policies for read-tier capabilities, matching TUI. |
| Rate limiting | **Gap G1** (no per-client or per-route limiter) — documented below. |
| Error codes / bodies | Canonical `http_status_for_code` on capability errors; shared workflow status helper now also covers typed exceptions. Legacy `{"error": ...}` bodies preserved for backward compatibility. |
| Timeouts | `/api/quick-ask` child has `timeout=120`; policy/workflow lock has a 15 s budget. **Gap G2/G3** below. |
| Cancellation | `/api/kill-switch` cancels all turns and rotates the token; `/api/v2/sessions/<sid>/cancel` cancels one turn. Verified by real HTTP test. |
| Streaming | `/api/run` emits NDJSON plus a final `bridge/done` marker; verified with the real fake-script runtime. **Gap G3** below. |
| Payload / size limits | Per-route caps (16 KB…40 MB); `Content-Length` validated (non-numeric/negative → 400, over cap → 413). Verified by real HTTP tests. |
| Idempotency | Backend workflow idempotency key (params digest or explicit key) + cross-process lock; verified replay denial and 8-way concurrency with one winner. |
| Versioning | `GET /api/health` returns product `__version__`; error envelopes carry `api_contract_version` at the contract layer. No wire-format change was made. |
| Backward compatibility | All existing success bodies, legacy error bodies, token/cookie behaviour and confirm gates are unchanged. Only previously-crashing hostile inputs now receive a JSON 4xx/5xx. |

---

## 2. Confirmed defects and fixes (failing → passing)

All six regressions below were first demonstrated as failures of
`keel/tests/test_prod_api.py` against unmodified `e6e7efc`, then fixed and re-run green.

### D1 (HIGH) — non-ASCII credential crashes the auth boundary
`secrets.compare_digest(str, str)` raises `TypeError` for non-ASCII input. A request with
`X-Keel-Token: ää` produced **no HTTP response** (`RemoteDisconnected`) instead of a clean
403 — an unauthenticated, one-line denial-of-service on every gated route.
**Fix:** `_authorized()` UTF-8 encodes both sides and compares bytes; any encoding/type
error returns `False` (fail closed). Evidence: `test_hostile_nonascii_token_is_refused_not_a_dropped_socket`,
`test_missing_and_invalid_token_refused`.

### D2 (MEDIUM) — deeply nested JSON drops the connection
`json.loads` raises `RecursionError` (not `JSONDecodeError`) for ~3000 nested arrays; the
exception escaped `_json_body` and closed the socket. **Fix:** catch `ValueError` and
`RecursionError`, return `400 {"error":"invalid json"}`. Evidence:
`test_deeply_nested_json_is_400_not_a_dropped_connection`.

### D3 (MEDIUM) — non-finite JSON constants accepted and echoed
`NaN` / `Infinity` are accepted by Python's `json` by default. `POST /api/settings
{"ui":{"bad":NaN}}` returned **HTTP 200 with a literal `NaN`** in the body — invalid JSON
for strict clients and a persistable non-standard value. **Fix:** `parse_constant` rejects
these at `_json_body`; `_send_json` uses `allow_nan=False` with a safe 500 fallback so no
route can emit invalid JSON. Evidence: `test_non_finite_json_constants_are_rejected`.

### D4 (MEDIUM) — typed workflow exceptions escaped the HTTP route
A stale/contended `request-results.jsonl.lock` makes `run_workflow` raise
`WorkflowError("lock_timeout")` before a result dict exists; the web handler did not catch
it, so the client got a dropped socket and no audit/status information. **Fix:** catch any
exception from `run_workflow`, emit a structured body with `code`, `error`, `ok:false`,
`http_status`, using the shared status helper (`lock_timeout → 400`). The old partial inline
status table was replaced by `_workflow_http_status()`, which honours the backend's
`http_status` hint first and falls back to the canonical code table (policy/permission
denials → 403, bad input → 400, unknown → 500). Evidence:
`test_workflow_lock_timeout_is_structured_json`, `test_workflow_bad_params_400_unknown_workflow_404`,
`test_workflow_permission_denial_maps_403`.

### D5 (MEDIUM) — corrupt saved policy dropped the socket on HTTP but was clean on CLI
`policy_enforcement.enforce()` raises `ValueError` when `exec-policies/default.json` is
malformed. `cli/main.py` catches this as `policy_error`; the web route did not, so the
capability was never run but the client got a dropped connection and **no audit record**.
**Fix:** explicit `except (OSError, ValueError)` → `400 {"code":"policy_error"}`, audit
`ok:false, code:policy_error, surface:web`; plus a generic exception fallback → `500
internal_error`. Audit writes are now best-effort (`_safe_record_audit`) so a full or
unwritable state directory cannot turn a completed call into a dropped socket.
Evidence: `test_malformed_saved_policy_is_json_error_and_audited`,
`test_cli_policy_error_matches_http_rule`.

### D6 (MEDIUM) — saved `prompt` policy not enforced on HTTP read-tier capabilities
TUI pre-flights a saved policy and prompts for consent even for a read-tier capability
whose params carry a command/URL. HTTP (and the CLI) executed it directly because
`capabilities.invoke` only denies `decision == "deny"` and ignores `"ask"`. Reproduced over
HTTP: `POST /api/capabilities/invoke {"id":"core.ci.kickoff","params":{"prompt":"cp a b"}}`
with a `prompt` rule for `cp` returned **200** and ran the handler.
**Fix:** the HTTP route now performs the same `policy_enforcement.enforce(...)` pre-flight
as TUI; an `ask` verdict requires a real `confirm:true` (409 otherwise). A corrupt policy
is left to `invoke()` so it is reported as `policy_error` rather than masked as a prompt.
Evidence: `test_read_capability_needs_confirm_when_policy_prompts`.

**Preserved behaviour:** token/cookie/query auth, Origin gate, strict boolean confirm gates,
unknown-workflow 404, all legacy response bodies, 256 KB workflow body cap, the 2 MB
capability body cap, and the existing streaming/kill-switch contracts. Full file diff is
limited to `webapp.py`.

---

## 3. Tests added (`keel/tests/test_prod_api.py`, 22 tests)

Real in-process HTTP server (`ThreadingHTTPServer(("127.0.0.1", 0), Handler)`), real
backend, `http.client` / raw sockets. Coverage:

* **Auth / authorization:** missing token, wrong token, hostile non-ASCII token, Origin
  mismatch and valid-Origin pass-through, strict boolean `confirm` for both mutating routes
  (`None/False/1/0/"true"/"false"/[]` all rejected with 409 and no ledger write), saved
  `prompt` policy confirmation, real saved-policy `policy_denied → 403`.
* **Hostile payloads:** malformed JSON, JSON array/scalar, deep nesting, `NaN`/`±Infinity`,
  invalid/negative `Content-Length` (hand-crafted request), 400 KB payload → 413.
* **Status mapping:** workflow `permission_denied → 403`, `bad_params → 400`,
  `unknown_workflow → 404`, `lock_timeout → 400` structured JSON, corrupt policy →
  `400 policy_error` with audit record.
* **Idempotency / concurrency:** replay denial with a single ledger record; 8 simultaneous
  identical POSTs → exactly 1 success, 7 `replay_denied`, 1 ledger record.
* **Cancellation:** `/api/kill-switch` cancels turns, rotates the token, old token → 403,
  new token → 200.
* **Streaming:** `/api/run` bypass without `accept_risk` → 403; real fake-script run emits
  a final `bridge/done` event.
* **Versioning / compatibility:** `/api/health` version and legacy `refused` 403 body.
* **Cross-surface:** CLI subprocess on a corrupt policy reports `policy_error`, matching HTTP.

---

## 4. CLI / TUI / HTTP consistency

| Rule | HTTP (this branch) | CLI (`cli/main.py`) | TUI (`tui.py`) |
|---|---|---|---|
| Capability confirm for write/execute/mutates | strict `confirm is True` → 409 | `--confirm` required → exit 1 | interactive `[y/N]` prompt |
| Read-tier capability under saved `prompt` policy | **now** pre-flight → 409 until confirmed (D6) | not pre-flighted (**gap G4**, outside owned files) | pre-flighted → prompt |
| Corrupt saved policy | `400 policy_error` + audit (D5) | exit 1 `policy_error` + audit | `runtime_error` + audit |
| Workflow confirm | strict `confirm is True` → 409 | `--confirm` required | no workflow command |
| Workflow params type | JSON object enforced by `_json_body` + backend `bad_params → 400` | explicit dict check | n/a |
| Policy/permission denial status | 403 (canonical) | exit 1 with stable code | `[error] <code>` |

G4 is the only remaining cross-surface divergence; fixing it requires editing
`cli/main.py`, which is not an owned file.

---

## 5. Gaps not fixable in the owned files

* **G1 — Rate limiting (MEDIUM).** No per-token/per-IP limiter on any route. A caller with
  a valid token can spam expensive routes (`/api/backend-workflows/*`, `/api/run`,
  `/api/quick-ask`). The token is 192-bit random and Origin/cookie gates limit browser
  abuse, so this is availability, not authentication bypass. A limiter belongs in front of
  the whole bridge (reverse proxy) or in shared state, not in one handler file.
* **G2 — No socket read timeout (MEDIUM).** `BaseHTTPRequestHandler` has no per-connection
  deadline; a client can declare a legal `Content-Length` and trickle bytes. Adding a
  blanket `settimeout()` in `setup()` would break the long-lived `/api/v2/sessions/<id>/events`
  SSE stream, so this needs a route-aware timeout design.
* **G3 — Streaming subprocess lifetime / cancellation (MEDIUM).** `/api/run` streams
  real NDJSON but has no timeout on `proc.wait()`, no per-run handle, and does not register
  into `_CURRENT_RUN`; a hung child holds the connection open. `/api/kill-switch` cancels
  fleet turns, not an individual `keel -p` subprocess. Needs a run-registry change.
* **G4 — CLI read-tier `prompt` policy pre-flight (MEDIUM).** CLI does not mirror the TUI/HTTP
  `ask` pre-flight in `cli/main.py:280-285`; requires a non-owned source change.
* **G5 — `/api/kill-switch` has no confirm gate (LOW/by design).** It cancels all turns and
  rotates the token with an empty body, unlike every other mutating route. It is an
  emergency one-click control and no shipped UI/CLI calls it with a body; adding a gate
  would break its documented contract. It still requires the token and a valid Origin,
  and the cookie is `SameSite=Strict`.
* **G6 — Chunked request bodies (LOW).** `_json_body` relies on `Content-Length`;
  `Transfer-Encoding: chunked` bodies are treated as `{}` and rejected by the confirm gate.
  Compatible clients already send `Content-Length`.
* **G7 — Workflow `state_root` is caller-selectable (LOW/accepted).** Per prior security
  review (`REVIEW-FINAL-SECURITY.md` L5) it is the trust anchor for path confinement, not a
  cross-boundary escape. Confining it to server config would break the documented HTTP/CLI
  contract.
* **G8 — Workflow `headers`/`expected_origin` CSRF params are caller-supplied (LOW/accepted).**
  Independent HTTP Origin gate covers the HTTP surface; not an independent control.
* **G9 — Legacy flat error envelopes (LOW/backward compatibility).** Most GET/legacy routes
  still return `{"error": "..."}` rather than `api_contracts.error_envelope()`. Converting
  them would break many existing clients and tests; capability errors already use the
  canonical status table and both shapes coexist.
* **G10 — Out-of-scope baseline failures (informational).** Full-suite collection is blocked
  by a pre-existing `VERSION MISMATCH` (`desktop/src-tauri/Cargo.toml` 0.1.0 vs 0.1.1);
  with `test_signing_gate.py` ignored, 4191 tests pass. The 31 remaining failures are
  pre-existing frontend/accessibility/release-artifact assertions and one
  order-dependent compat test that passes in isolation. None touch `webapp.py`.

---

## 6. Verification evidence

Clean HOME (`HOME`/`USERPROFILE` = fresh temp dir), required command:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_prod_api.py','keel/tests/test_webapp.py','keel/tests/test_api_contracts.py','keel/tests/test_backend_workflows.py']))"
```

```
76 passed in 45.24s
```

Before the fixes, the same command with only `test_prod_api.py` gave
`6 failed, 15 passed` (D1, D2, D3, D5, D4 plus one corrected test expectation); after
adding D6, `1 failed, 21 passed`; after all fixes, `22 passed`.

Additional regression runs in clean HOME:

* 24 web/API/CLI/contract test files: `4 failed, 150 passed, 10 skipped` — the 4 failures
  are pre-existing `test_web_surface_hardening.py` assertions about frontend files
  (`desktop/ui/app.js`, `desktop/sw.js`), which were not touched.
* Full suite excluding the pre-existing version-gate collection error:
  `31 failed, 4191 passed, 51 skipped, 3707 subtests passed`; all 31 are the pre-existing
  frontend/accessibility/release-artifact issues and the order-dependent compat test
  noted in G10; `test_compat_runtime.py::test_tool_requires_approval_then_approved_runs`
  passes in isolation.

**Final commit:** HEAD of `agent/prod-api` (candidate HEAD `e6e7efc` → final commit,
3 files changed, no push; SHA reported by the completing agent).
