# W4 backend evidence (13 remaining MCP rows, W4.1–W4.14)

**Branch:** `agent/b2-w4` **Baseline:** `982335d`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\backend\b2-w4`

## Scope

The authoritative registry (`plan-index.json` / `master-plan-v6-final-matrix.csv`)
has 14 `W4.*` rows. `W4.3` (OAuth PKCE, discovery, refresh, keychain storage)
is already `verified` in `keel.product_contracts.py` and is deliberately left
untouched. This change implements the **13 `not_started` rows**:

| ID | Registry feature (abridged) | Backend entry point |
| --- | --- | --- |
| W4.1 | `mcp add` / `list` / `auth` / `logout`; `/mcps` view model | `dispatch_mcp_command`, `mcps_panel`, `McpConfigStore` |
| W4.2 | `mcp.servers.<name>` shape; whole-object override, no field merge | `normalize_server_config`, `merge_config_layers` |
| W4.4 | Pre-registered `client_id` → CIMD → DCR registration order | `select_client_registration` |
| W4.5 | Paste the failed callback URL when the browser is remote | `extract_callback_url`, `parse_pasted_callback` |
| W4.6 | 30 s / 30 s / 12 h timeouts, global and per-server | `resolve_timeouts`, `call_progress` |
| W4.7 | Protocol selection (`legacy`, `auto` probe, pinned) + probe warning | `select_protocol` |
| W4.8 | Shared connections across project dirs with identical settings | `connection_identity`, `ConnectionPool` |
| W4.9 | Tool-name normalization and collision suffixes | `normalize_tool_name`, `normalize_tool_names` |
| W4.10 | Prompt catalog → `<server>:<prompt>` slash commands | `slash_commands_from_catalog`, `render_prompt_command` |
| W4.11 | Tagged, tainted server instructions in the system prompt | `build_system_prompt`, `server_tools_denied` |
| W4.12 | Elicitation form/link, validation, dismiss cancels | `render_elicitation`, `answer_elicitation` |
| W4.13 | Session id in request `_meta` with remote-log warning | `build_request_meta`, `correlation_id_for` |
| W4.14 | `disabled` keeps config; disconnect never edits config | `ConnectionState`, `connect_server`, `disconnect_server` |

## Files owned (only these were changed)

* NEW `keel/src/keel/w4_backend.py`
* NEW `keel/tests/test_w4_backend.py`
* NEW `master-plan-v6-w4-backend-evidence.md` (this file)

No other source, test, registry, plan or UI file was edited. There is **no
frontend code**: where the plan calls for a CLI or an in-app `/mcps` surface,
this module returns the structured command result / view model for that
surface to render.

## Real behavior, stdlib only

The module imports only the Python standard library (`base64`, `fnmatch`,
`hashlib`, `hmac`, `json`, `math`, `os`, `re`, `shlex`, `dataclasses`,
`typing`, `urllib.parse`, `xml.sax.saxutils`). It never opens a socket,
spawns a subprocess, reads a clock, reads a file or writes to disk. All state
(config documents, credentials, leases, runtime connections) is supplied by
and returned to the caller. Every observable decision is computed from the
inputs:

* **W4.1** — a small argv parser handles `--`, repeated `--env KEY=VALUE` and
  `--header "K: V"`, `--global`, and subcommands. `mcp add` produces a validated
  config object in the selected scope; `mcp list` resolves project-over-user
  precedence and reports connection/auth state; `mcp auth` derives a real S256
  PKCE challenge and an authorization URL (no discovery call); `mcp logout`
  clears credentials without touching config. Unknown flags/subcommands return
  a coded failure instead of exiting the process.
* **W4.2** — strict normalization of the documented 12 server fields; malformed
  objects fail closed with a code. `merge_config_layers` replaces a server
  object wholesale (never field-merges) and emits a warning listing fields that
  a higher-precedence layer dropped, as the registry requires.
* **W4.4** — a non-URL `client_id` selects a pre-registered client (catalog
  options filled in, explicit options win); an `https://` `client_id` selects a
  caller-hosted CIMD metadata URL; otherwise DCR uses the supplied metadata URL
  or derives it from the server URL. `oauth: false` yields method `none`.
  Secrets are redacted in every `to_dict()`.
* **W4.5** — extracts a URL from prose/code fences, enforces loopback host,
  exact `state` (`hmac.compare_digest`), single `code`, redirect match and OAuth
  `error` responses.
* **W4.6** — defaults 30 s startup / 30 s catalog / 43 200 s execution;
  per-server overrides global overrides defaults; NaN/inf, booleans and
  non-positive values are rejected. `call_progress` drives the long-running
  indicator and cancel affordance.
* **W4.7** — conservative `legacy` default; `auto` reports a probe requirement
  and the extra-round-trip cost warning, or resolves a supplied probe result;
  failures fall back to legacy; pinned revisions are validated.
* **W4.8** — a SHA-256 fingerprint over canonical JSON of every
  connection-affecting field (secret values are hashed, never exposed);
  `disabled` and `pool` are layout hints and do not alter identity. The pool
  reference-counts leases by owner and closes a connection when the last lease
  is released.
* **W4.9** — `<server>_<tool>` with invalid characters folded to `_`; exact
  pair-derived 8-hex collision suffixes and a numeric tie-break keep names
  unique, short and deterministic.
* **W4.10** — validates `server:prompt` names, binds positional argv to
  `{{name}}` / `${name}` placeholders, rejects unresolved placeholders and
  argument-count mismatches, and imports a whole prompt catalog.
* **W4.11** — XML-escapes instruction text so a server cannot close the tag;
  blocks are marked `trusted="false" priority="below_user"`; a server is
  omitted when at least one tool exists and all its tools are denied (an
  empty tool set is not treated as "all denied").
* **W4.12** — validates the supported JSON-schema subset (types, enum,
  required, defaults, length, pattern, min/max) and returns structured errors;
  dismiss/cancel/decline always end the request.
* **W4.13** — Keel sends **no session id by default**. Opt-in adds
  `opencode.sessionId` to `_meta` and, for remote servers, a warning that they
  may log it. `correlation_id_for` provides the opaque per-server alternative.
* **W4.14** — disabled servers stay in config but cannot connect; runtime
  disconnect maintains a separate set and returns `config_unchanged: True`;
  reconnect clears the runtime disconnect.

## Verification

Focused command (from the worktree root, exactly as the other backend
evidence files use):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_w4_backend.py']))"
```

Result: **53 passed** (0 failed, 0 skipped).

Full-suite regression command:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests']))"
```

Result: see the commit message / parent session report. The new module is
additive: no existing module imports it and no existing test file changed.

## Edge cases explicitly covered

* config JSON round-trip and malformed JSON; unknown fields; bad server type;
  local-with-url / remote-with-command; dropped-field warnings on override
* secret-bearing header values never appear in error text; client secret
  redacted in registration results
* callback state mismatch, non-loopback host, OAuth `error` response, redirect
  mismatch, URL buried in prose and code fences
* boolean / zero / negative / NaN / infinite timeout values
* protocol probe failure, unknown revision, disabled probe
* pool identity stability, secret hashing, descriptor mismatch, refcount close
* name collisions (including two spellings converging on one base name) and
  duplicate source tools
* quoted slash-command arguments, unresolved placeholders, bad prompt names
* instruction text attempting to close the tagged block; deny-all vs partial
  allow; empty tool set
* elicitation required/unknown/enum/type/range/pattern failures, defaults,
  all three dismissal paths, unsupported schema type
* no-session-by-default, remote warning, opaque correlation id
* disabled connect refusal and byte-identical config across disconnect

## Notes on plan tensions

* `W4.13` describes opencode's observed behavior of sending the session id,
  while the registry detail states Keel sends none by default and uses the
  opaque per-server id from `V6`. This module implements the Keel stance:
  no session id unless explicitly opted in, with the documented remote-log
  warning when opted in.
* `W4.4` notes CIMD must not require a Keel-operated service. The CIMD
  branch therefore only uses a caller-supplied `https://` metadata URL and
  falls back to DCR when that is unavailable.
