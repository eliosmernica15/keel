# STAB Workflow Authorization / API Hardening Evidence

Branch: `agent/stab-workflow` · base: `f60b080` · merged stabilization HEAD: `7fe7674`
(`origin/stabilization/post-promotion-production-2026-11-25`, added
`STAB-SECURITY-REVIEW.md` and `STAB-INTEGRATION-EVIDENCE.md`; no owned source file
changed in that merge).

Owned files changed:

- `keel/src/keel/backend_workflows.py`
- `keel/src/keel/capabilities.py`
- `keel/src/keel/policy_enforcement.py`
- `keel/src/keel/webapp.py`
- new `keel/tests/test_stab_workflow_auth.py`
- this evidence file

No frontend, no CLI/TUI, no `backend_hub.py`, no push.

---

## 1. Real probes — before vs after

| # | Probe (real boundary, no mocked gate) | Before | After | Verdict |
|---|---|---|---|---|
| H-1 | `prompt` rule on `backend.workflow`, direct `run_workflow` with no confirmation | `ok=True`, code `ok`, durable `approval-results.jsonl` written; `confirmation_required` branch unreachable | `ok=False`, `code=confirmation_required`, `http_status=409`, handler not called, one audit row | FIXED |
| H-1b | Base `forbidden` policy + `state_root=<trusted base>/project` | `ok=True`, workflow ledger written (policy bypass via sub-root) | `code=policy_denied`, `http_status=403`, no ledger, audit `ok=false` | FIXED |
| H-1c | Rule targeted at `["backend.workflow","approval"]` with a `request` call | impossible (workflow name absent from enforced command) | `request` executes, `approval` denied and handler not called | FIXED |
| M-1 | `bad_params`, `unknown_workflow`, `bad_state_root`, `policy_error`, handler exception, `lock_timeout`, success | three early branches produced **no** audit row; handler exception escaped as a raw `RuntimeError` | every branch produces exactly one `capability-audit.jsonl` row with redacted `error`, `ok=false` and its stable code | FIXED |
| M-1b | Successful workflow / honest MCP dry run response body | `http_status=500` for `code=ok` and `code=dry_run`; web returned HTTP 500 for the dry run | both advertise `http_status=200`; web returns HTTP 200 for both | FIXED |
| M-2 (red team) | `capabilities.invoke` omitted `allowed_permissions` | all three tiers granted to every caller | HTTP derives and passes a real tier set from its confirm decision; session-supplied `context["allowed_permissions"]` is authoritative; legacy in-process calls kept for compatibility | FIXED at the HTTP boundary, see residual |
| M-3 (red team) | Handler/policy exception containing `Authorization: Bearer sk-…` | echoed verbatim in `CapabilityError` | redacted with `keel.redaction.redact_text` before wrapping | FIXED |
| M-1 (integration) | 8 processes × 25 audit appends | 168/200 lines, 12 empty/invalid lines | 200/200 valid JSON lines | FIXED |
| M-2 (integration) | `record_audit` entry containing an API key | secret persisted verbatim | `[REDACTED]` persisted | FIXED |
| M-3 (integration) | brand-new process `keel capability describe backend.invoke` / `GET /api/capabilities` | `x-function-schemas = {}` (0) | 144 schemas at first discovery in both | FIXED |

## 2. Change inventory and why each is safe

`backend_workflows.py`

- `run_workflow(name, params, *, confirmed=False)` — no hardcoded `confirmed=True`.
  HTTP passes `confirmed=request.get("confirm") is True`; direct callers default
  to unconfirmed and fail closed.
- `_failure()` + single `_audit_workflow()` call at the end of `run_workflow`:
  every branch (including bad params, unknown name, rejected state root, corrupt
  policy, handler crash, lock timeout) returns the same canonical shape and is
  audited once. Audits fall back to `_trusted_state_base()` when no safe root can
  be resolved; `error` text is redacted.
- `enforce_workflow()` is called with both the caller-selected state root **and**
  the server-controlled base; the strictest decision wins. This removes the
  "point `state_root` at a policy-free sub-directory" bypass.
- `_http_status()` now maps success codes (`ok`, `dry_run`, `dry_run_descriptor`)
  to 200 and adds `403/404/409/400` entries for the typed denial codes.

`policy_enforcement.py`

- New `enforce_workflow()` is the single authoritative workflow gate. The enforced
  command is `backend.workflow <name>` so both umbrella and per-workflow rules
  are expressible. `interactive=True` makes an unconfirmed `prompt` reach the
  reachable `ask` → `confirmation_required` outcome (409), not a generic denial.

`capabilities.py`

- `get()` and `list_capabilities()` call a one-shot, recursion-guarded
  `_ensure_backend_schemas()`; `backend_hub` is imported only on first discovery,
  not at startup. The hub's `sync_capability_schemas()` calls `capabilities.get`,
  which is safe because the `busy` flag short-circuits the re-entry.
- `invoke()` honours `context["allowed_permissions"]` (session-derived tiers) as
  well as the explicit argument. For backward compatibility, legacy in-process
  callers that omit both keep all tiers; **webapp now supplies real tiers**.
- Policy/handler errors pass through `_safe_error()` (`redact_text`) before
  becoming `CapabilityError`.
- `record_audit()` writes one atomically-locked, redacted JSONL line, using an
  exclusive `O_EXCL` lock file with stale-lock recovery and an `O_APPEND`
  single-writer section.

`webapp.py`

- Workflow POST route: audits its own strict `confirm` gate and unknown-workflow
  early return with the canonical `code`/`ok` body, and audits any uncaught
  dispatch exception. It forwards `confirmed` to `run_workflow`.
- `_workflow_http_status()` accepts 2xx hints as well as 4xx/5xx so a dry run is
  not misreported as HTTP 500.
- Capability POST route derives `allowed_permissions` from the authenticated
  caller's confirm decision and passes it to `invoke()`.

## 3. Verification

Clean-HOME command (HOME/USERPROFILE redirected to an empty temp directory):

```
python -c "import sys,os,pytest; sys.path.insert(0,'keel/src'); \
  raise SystemExit(pytest.main(['-q', \
  'keel/tests/test_stab_workflow_auth.py', \
  'keel/tests/test_prod_workflow_audit.py', \
  'keel/tests/test_prod_cap_gate.py', \
  'keel/tests/test_prod_api.py', \
  'keel/tests/test_backend_workflows.py', \
  'keel/tests/test_capabilities_integration.py', \
  '-p','no:cacheprovider']))"
```

Result: **66 passed** (17 new regression tests + 49 existing).

Regression sweep over every previously affected capability/exec-path/product test
file: **124 passed, 5 failed**. The 5 failures are the pre-existing artifact-only
ones recorded at stabilization baseline (`RELEASE-MANIFEST.json`,
`RELEASE-SHA256SUMS.txt`, sidecar/dist artifacts absent from this worktree) and
are unrelated to these files.

New regression tests (`keel/tests/test_stab_workflow_auth.py`) are real probes:
real saved policy JSON, real in-process HTTP server, real CLI and fresh Python
subprocesses, real cross-process audit writes. No authorization function is
mocked; only the workflow handler is replaced with a marker to prove "no handler
ran after denial".

## 4. Residual gaps / follow-ups outside this worktree

1. `keel/src/keel/cli/main.py` (not owned) parses `--confirm` but still calls
   `run_workflow(name, params)` without `confirmed=...`. A saved `prompt` policy
   therefore fails closed on CLI even with `--confirm` (proved by
   `test_cli_prompt_policy_confirm_is_the_explicit_approval`): safe, but less
   usable than HTTP. Required one-line CLI change:
   `run_workflow(name, params, confirmed="--confirm" in argv)`.
2. CLI and TUI (not owned) still omit `allowed_permissions`. Their own strict
   confirm gates protect write/execute tiers and are honoured by `invoke()`;
   passing a real session tier set there would complete tier separation.
3. Legacy in-process callers that omit both `allowed_permissions` and
   `context["allowed_permissions"]` keep the historical all-tiers behaviour to
   preserve existing capability calls. New transports should pass the tier set,
   as the HTTP bridge now does.
4. Lazy schema publication is deliberately on discovery (`get` /
   `list_capabilities`), not at module import, so startup stays cheap.
