# Master Plan v6 — API & Integration Contracts Evidence (Agent 30)

- **Branch:** `agent/f-api-contracts`
- **Baseline:** `a9a040e3369c7e8fa2882b1720edb1bde30b8af4`
- **Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\final\api-contracts`
- **Scope:** request/response contracts, auth and error semantics, and version reporting across the web bridge (`keel/src/keel/webapp.py`), the capability hub (`keel/src/keel/capabilities.py`) and the CLI (`keel/src/keel/cli/main.py`).

> Constraint honored: I edited **only** the files I own — the new shared module
> `keel/src/keel/api_contracts.py`, the new test `keel/tests/test_api_contracts.py`,
> and this evidence file. `webapp.py`, `capabilities.py` and `cli/main.py` were
> read only. Every fix that requires changing those files is specified exactly
> in §5 for the lead.

---

## 1. Inconsistencies found

All formats below were observed live against `webapp.make_server(0)` at the
baseline (not inferred from source alone), plus direct source/CLI inspection.

### 1.1 Error envelopes are three different shapes

| Surface | Observed error body | Notes |
|---|---|---|
| Web bridge (generic) | `{"error": "bad path"}` | flat prose string, no code, no status |
| Web bridge (auth) | `{"error": "refused", "reason": "bad token or origin"}` | flat, code hidden in prose |
| Web bridge (capability error) | `{"error": "unknown capability: no.such.cap", "code": "not_found"}` | flat prose **plus** a separate `code` |
| Web bridge (confirmation) | `{"error": "confirmation_required", "capability": "core.flags.set", "permission": "write"}` | here `error` holds a **code**, not prose, and there is **no `code` field** |
| Capability hub | `CapabilityError(message, code=...)` | Python object with `.code`, no serializable envelope |
| CLI | raw stderr text `not_found: unknown capability: no.such.cap` (exit 1) | not JSON at all |

The same concept ("not found") is spelled three ways in the web bridge:
`"not_found"` (`webapp.py:368,566,827,884,1177,1182`), `"not found"`
(`webapp.py:203,970,980,988,1052,1066,1135,1154,1167`) and the prose
`"unknown capability: X"` (`webapp.py:625` via `capabilities.py:84`).

### 1.2 Capability error codes map to the wrong HTTP statuses

`webapp.py:621-623` maps:

```python
status = (HTTPStatus.NOT_FOUND if exc.code == "not_found"
          else HTTPStatus.FORBIDDEN if exc.code == "permission_denied"
          else HTTPStatus.BAD_REQUEST)
```

So **every other capability code falls through to 400**:

| `CapabilityError.code` (source) | Current web status | Canonical status | Match? |
|---|---|---|---|
| `not_found` (`capabilities.py:84`) | 404 | 404 | yes |
| `permission_denied` (`capabilities.py:93`) | 403 | 403 | yes |
| `bad_params` (`capabilities.py:87`) | 400 | 400 | yes |
| `policy_denied` (`capabilities.py:107`) | **400** | 403 | **no** |
| `handler_error` (`capabilities.py:119`) | **400** | 500 | **no** |

A genuine policy denial or handler crash is therefore indistinguishable from
a bad request to API clients.

### 1.3 Auth / origin handling is inconsistent and partly unreachable

- `webapp.py:574` refuses any POST where `not self._origin_ok() or not self._authorized()`, via
  `_refuse()` (`webapp.py:279-281`) → `{"error": "refused", ...}` with **403**.
- The dedicated "bad origin" branch at `webapp.py:579-581` that would return
  `{"error": "bad origin"}` is **unreachable** for POST routes, because the
  line 574 gate fires first. Live probe with a valid token and
  `Origin: https://evil.test` returned `403 {"error": "refused", ...}`, never
  `"bad origin"`.
- Canonical contract distinguishes `refused` (bad token) from `bad_origin`
  (origin mismatch), both 403. Today clients cannot tell them apart.

Auth *status* semantics are otherwise consistent: every `/api/*` route is
token-gated and returns **403** without a valid token (`webapp.py:379,385,391,495,508,520,527,534,547,553,559`, etc.).

### 1.4 CLI errors are not machine-readable

`cli/main.py:292-303` writes plain text to stderr and exits 1:

```python
sys.stderr.write(f"{exc.code}: {exc}\n")
```

Related ad-hoc CLI errors: `unknown capability: X` (`:255`,`:274`),
`--params must be valid JSON` (`:270`), `X requires --confirm (write)`
(`:279-281`), `policy_error: ...` (`:302`). The CLI's *success* output is
pretty-printed JSON on stdout (`:304`), so a client cannot parse errors and
successes with one decoder. Positive note: the audit records are consistent
across surfaces — both write
`{"capability": ..., "ok": ..., "code": ..., "surface": "web"|"cli"}`
(`webapp.py:614-620`, `cli/main.py:290-301`).

### 1.5 Version reporting: values agree, product labels differ

Numeric version is **consistent everywhere** (see §4). The only divergence is
cosmetic: `/api/health` emits the bare string `"0.1.1"`, CLI prints
`keel 0.1.1`, and the `Server` header reports `keel-webapp/0.1.1`. I recommend
the numeric token stay the single source of truth (`keel.__version__`) and the
contract schema carry its own explicit `api_contract_version` (implemented in
the shared module as `"1.0"`).

---

## 2. Contract comparison table

Legend — **Adopt? Y** = surface must change to reach canonical form.

| Endpoint / path | Surface | Current format (observed) | HTTP / exit | Canonical format | Adopt? |
|---|---|---|---|---|---|
| `GET /api/health` (success) | web | `{"ok": true, "version": "0.1.1"}` | 200 | success body (unchanged); optional `api_contract_version` | N |
| any `/api/*` unauthenticated | web | `{"error":"refused","reason":"bad token or origin"}` | 403 | `{"ok":false,"error":{"code":"refused","message":...,"status":403},"api_contract_version":"1.0"}` | **Y** |
| `POST /api/capabilities/invoke` success | web | `{"ok":true,"capability":...,"result":...,"elapsed_ms":...}` | 200 | success body (unchanged) | N |
| `…/invoke` → `not_found` | web | `{"error":"unknown capability: X","code":"not_found"}` | 404 | canonical, `code=not_found`, `details.capability=X` | **Y** |
| `…/invoke` → `permission_denied` | web | `{"error":<prose>,"code":"permission_denied"}` | 403 | canonical, `code=permission_denied` | **Y** |
| `…/invoke` → `policy_denied` | web | `{"error":<prose>,"code":"policy_denied"}` | **400** | canonical, `code=policy_denied`, **status 403** | **Y + status fix** |
| `…/invoke` → `bad_params` | web | `{"error":<prose>,"code":"bad_params"}` | 400 | canonical, `code=bad_params` | **Y** |
| `…/invoke` → `handler_error` | web | `{"error":<prose>,"code":"handler_error"}` | **400** | canonical, `code=handler_error`, **status 500** | **Y + status fix** |
| `…/invoke` → missing `confirm` | web | `{"error":"confirmation_required","capability":...,"permission":...}` | 409 | canonical, `code=confirmation_required`, details keep capability/permission | **Y** |
| `…/invoke` → bad Origin | web | `{"error":"refused",...}` (inner `"bad origin"` dead) | 403 | canonical `code=bad_origin` (or deliberate `refused`), status 403 | **Y** |
| `POST` invalid/oversized JSON body | web | `{"error":"invalid json"}` / `{"error":too_large}` | 400 / 413 | canonical `bad_request` / `payload_too_large` | **Y** |
| generic 404 / 405 routes | web | `{"error":"not_found"}` / `{"error":"method not allowed"}` | 404 / 405 | canonical `not_found` / `method_not_allowed` | **Y** |
| path / validation errors | web | `{"error":"path outside workspace"}` etc. | 400 | canonical `bad_request` | **Y** |
| `CapabilityError` raised by hub | hub | object `.code` + message | n/a | no change needed if boundaries call `from_capability_error()` | N (boundary) |
| `keel capability invoke` error | cli | raw stderr `<code>: <message>`, exit 1 | 1 | canonical JSON envelope on stderr, exit 1 | **Y** |
| `keel capability describe/invoke` unknown id | cli | raw stderr `unknown capability: X` | 1 | canonical `not_found` | **Y** |
| `keel capability invoke` bad `--params` | cli | raw stderr `--params must be valid JSON` | 1 | canonical `bad_params` | **Y** |
| `keel capability invoke` needs `--confirm` | cli | raw stderr `X requires --confirm (write)` | 1 | canonical `confirmation_required` | **Y** |
| `keel --version` | cli | stdout `keel 0.1.1` | 0 | unchanged (numeric version already canonical) | N |
| `Server` HTTP header | web | `keel-webapp/0.1.1 Python/3.11.9` | n/a | unchanged (label only) | N |

---

## 3. Shared helpers added — `keel/src/keel/api_contracts.py`

Dependency-free (stdlib only), additive, importable by all three surfaces
without creating circular imports.

| Symbol | Purpose |
|---|---|
| `CANONICAL_VERSION = "1.0"` | Schema version, emitted automatically as `api_contract_version` in every envelope |
| `CAPABILITY_ERROR_CODES` | The five hub codes: `not_found`, `permission_denied`, `policy_denied`, `bad_params`, `handler_error` |
| `ERROR_STATUS` / `DEFAULT_ERROR_STATUS` | Single code→HTTP-status table (fixes the 400 fall-through, adds `refused`, `bad_origin`, `confirmation_required`, `method_not_allowed`, `payload_too_large`, …) |
| `http_status_for_code(code, *, default=400)` | Status lookup |
| `error_envelope(code, message="", *, status=None, details=None, **extra)` | Builds a canonical envelope; coerces code/message to `str`, validates status 100–599, accepts optional `details` and additive top-level keys |
| `is_canonical_envelope(obj)` | Strict about `ok:false` + nested `error.{code,message,status}`, permissive about extra top-level keys |
| `from_capability_error(exc, *, status=None, details=None, surface=None)` | Adapter for any `CapabilityError`-like object (uses `.code`); no import of `keel.capabilities` |
| `classify_envelope(obj)` | `canonical` / `success` / `legacy_flat` / `legacy_other` / `unknown`, for conformance audits |

Canonical shape produced:

```json
{
  "ok": false,
  "error": {"code": "policy_denied", "message": "execution policy denied cap: reason", "status": 403, "details": {"capability": "cap.id"}},
  "api_contract_version": "1.0",
  "surface": "web"
}
```

---

## 4. Version values (exact, verified at runtime)

| Source | Exact value |
|---|---|
| `keel/src/keel/__init__.py` | `__version__ = "0.1.1"` |
| `GET /api/health` body | `{"ok": true, "version": "0.1.1"}` |
| `keel --version` stdout | `keel 0.1.1` |
| `pyproject.toml` `[project].version` | `0.1.1` |
| `keel/site/download.json` | `0.1.1` |
| `Server` header | `keel-webapp/0.1.1 Python/3.11.9` |
| `release.common.validate_version()` | `0.1.1` |
| `keel.api_contracts.CANONICAL_VERSION` (new) | `1.0` (schema version, deliberately separate) |

All release sources agree; `test_version_sync.py` passes. No version change is
required by this work.

---

## 5. Exact changes the lead must make (I could not edit these files)

### 5.1 `webapp.py` — add one helper and a shared import

After `from . import __version__` (`webapp.py:57`):

```python
from .api_contracts import error_envelope, from_capability_error
```

Inside `Handler` (near `_send_json`, `webapp.py:241`) add a single adapter so
the body's status and the HTTP status can never disagree — **important**,
because `_send_json` defaults to `HTTPStatus.OK`, so passing a canonical
envelope alone would otherwise answer HTTP 200 with `"status": 403` inside:

```python
def _send_error(self, code, message, *, details=None, status=None, **extra):
    env = error_envelope(code, message, status=status,
                         details=details, **extra)
    self._send_json(env, status=env["error"]["status"])
```

### 5.2 `webapp.py` — replace the ad-hoc error sites

- `_refuse()` (`:279-281`) →
  `self._send_error("refused", "bad token or origin")`.
- Capability error handler (`:617-625`) → drop the hand-rolled `status = …`
  ternary entirely:

  ```python
  except CapabilityError as exc:
      record_audit(state_root, {"capability": cap_id, "ok": False,
                                "code": exc.code, "surface": "web"})
      env = from_capability_error(exc, details={"capability": cap_id},
                                  surface="web")
      self._send_json(env, status=env["error"]["status"])
  ```

  This simultaneously fixes `policy_denied` (400→403) and `handler_error`
  (400→500) without any new branching.
- Confirmation branch (`:598-603`) →
  `self._send_error("confirmation_required", f"{cap_id} requires confirm=true (permission={cap.permission})", details={"capability": cap_id, "permission": cap.permission if cap else None})`;
  keep the existing 409 (now derived from the table).
- Origin handling (`:574-582`): move the origin check ahead of the combined
  gate so `bad_origin` is reachable, then delete the dead inner branch:

  ```python
  if not self._origin_ok():
      self._send_error("bad_origin", "origin mismatch")
      return
  if not self._authorized():
      self._refuse()
      return
  ```

  HTTP status stays 403 for both cases, so existing tests that only assert
  403 continue to pass.
- Generic 4xx sites (list in §1.1 / comparison table): replace each
  `self._send_json({"error": <prose>}, STATUS)` with
  `self._send_error(<mapped code>, <prose>)` using:
  `invalid Content-Length` / `invalid json` / `body must be an object` /
  `doc must be an object` / `prompt must not be empty` → `bad_request`;
  `too_large` / `file too large (24 MB cap)` → `payload_too_large`;
  `"not_found"` / `"not found"` → `not_found`;
  `"method not allowed"` → `method_not_allowed`;
  `path outside workspace` / `bad path` → `bad_request`.

### 5.3 `cli/main.py` — one helper, replace raw stderr writes

Import `error_envelope` (and optionally `from_capability_error`) from
`..api_contracts`, then add near `_capability_cmd` (`:228`):

```python
def _cli_error(code, message, **extra):
    env = error_envelope(code, message, surface="cli", **extra)
    sys.stderr.write(json.dumps(env) + "\n")
    return 1  # keep exit code 1 for all errors
```

Replace: `:255` and `:274` → `_cli_error("not_found", f"unknown capability: {id}")`;
`:270` → `_cli_error("bad_params", "--params must be valid JSON")`;
`:279-281` → `_cli_error("confirmation_required", f"{cap_id} requires --confirm ({cap.permission})")`;
`:292-295` → build from `from_capability_error(exc, surface="cli")` and write
`json.dumps(env)` to stderr, keeping `return 1`;
`:297-302` → `_cli_error("policy_error", f"{type(exc).__name__}: {exc}")`
(add `"policy_error": 400` to `ERROR_STATUS` if the lead wants that code
canonical too).

### 5.4 `capabilities.py` — optional, no behavioral change required

No change is needed if web/CLI use `from_capability_error`. If a self-serve
API is desired, add an additive method:

```python
def to_envelope(self, *, surface=None):
    from .api_contracts import from_capability_error
    return from_capability_error(self, surface=surface)
```

### 5.5 Backward-compatibility note

Migration is response-shape-breaking for clients that currently read the flat
`error` string. Mitigate by keeping the message text identical (the helpers
place it at `error.message`) and, if the lead wants a transition window,
temporarily also echo `error` as the message string via `**extra`. The status
codes above remain HTTP-compatible except the two deliberate fixes
(`policy_denied` 400→403, `handler_error` 400→500).

---

## 6. Tests and results

Added: `keel/tests/test_api_contracts.py` (19 tests). It (a) unit-tests every
helper, (b) probes the real HTTP bridge and CLI to pin current formats and
version values, and (c) contains `ADOPTION_NEEDED` +
`test_conformance_audit_confirms_current_nonconformance`, which asserts the
observed non-canonical shapes so any silent drift is caught.

Commands (run from worktree root with `PYTHONPATH` pointed at this worktree's
`keel/src`, because the base environment has an editable install that
otherwise resolves `keel` from the main checkout):

```
python -m pytest keel/tests/test_api_contracts.py -q
python -m pytest keel/tests/test_security_validation.py keel/tests/test_capabilities_integration.py keel/tests/test_version_sync.py keel/tests/test_webapp.py -q
```

Results:

```
test_api_contracts.py ...................                          [100%]  19 passed in 6.61s
security_validation + capabilities_integration + version_sync + webapp
                      ..............................               [100%]  30 passed in 41.72s
combined run (all five files above) .................................................
                                                                  [100%]  49 passed in 42.68s
```

No tools failed; no tests were skipped or xfailed. Commit SHA is reported in
the agent's final message (no push performed).
