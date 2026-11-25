# STAB-SECURITY-REVIEW — independent adversarial red team

- **Target:** main-derived backend at stabilization HEAD `f60b080` (worktree `C:\Users\Admin\.local\share\opencode\worktree\stab\security`, branch `agent/stab-security`).
- **Posture:** read-only. No source files were modified. All probes live in `C:\Users\Admin\AppData\Local\Temp\opencode\stab-sec-probe\`.
- **Runtime:** Python 3.11.9 (Windows), `PYTHONPATH=<worktree>/keel/src`, isolated `KEEL_STATE_DIR`.

## VERDICT: **BLOCK**

One **HIGH** finding (saved `ask`/prompt execution policy is silently auto-approved on every workflow transport) blocks promotion. Five **MEDIUM** and one **LOW** finding are also recorded. All other probed controls passed.

---

## HIGH FINDINGS

### H-1 — Saved `ask`/prompt policy is bypassed on `run_workflow` (fail-open confirmation)

- **Severity:** HIGH
- **File:line:** `keel/src/keel/backend_workflows.py:1590-1593` (hardcoded `confirmed=True`), unreachable denial branch at `:1607-1613`; `keel/src/keel/policy_enforcement.py:116-128` (`prompt` + `confirmed=True` ⇒ `allow`).
- **Affected surfaces:** `backend_workflows.run_workflow`, HTTP `POST /api/backend-workflows/*` (`webapp.py:760-800`), CLI `keel backend-workflow` (`cli/main.py:314-339`). All three route through `run_workflow`.

**Root cause.** `run_workflow` calls the policy boundary with `confirmed=True` unconditionally:

```python
decision = _enforce(
    "backend.workflow",
    {"command": "backend.workflow", "workflow": str(name)},
    state_root=state_root, interactive=False, confirmed=True)   # <-- bug
```

`policy_enforcement.enforce()` maps `PROMPT` + `confirmed=True` to `_decision("allow", ...)` (lines 117-120). Consequently the `decision.decision == "ask"` branch at `backend_workflows.py:1607-1613` that would return `confirmation_required` (HTTP 409) is **unreachable**. An administrator who saves a `prompt` policy expecting interactive approval gets silent execution. With the transport `confirm` flag already satisfied (HTTP `confirm:true` / CLI `--confirm`), the saved policy provides no gate at all. A second, related weakness: the enforced command is the literal `"backend.workflow"`; the actual workflow name is never part of `COMMAND_FIELDS`, so per-workflow policy granularity is impossible.

**Repro (direct API).** Probe `wf_auth_probe.py`, case `ask`. Saved policy: `{"prefix_rules":[{"pattern":["backend.workflow"],"decision":"prompt","justification":"needs-approval"}]}`. A spy replaces `WORKFLOWS["approval"]` to record handler execution.

```
$ python wf_auth_probe.py
  "ask": { "code": "ok", "ok": true, "handler_ran": true, "error": null }
```

Expected: `code: confirmation_required`, `handler_ran: false`. Actual: workflow handler executed.

**Repro (real CLI, end-to-end).** Saved the same `prompt` policy into `KEEL_STATE_DIR/exec-policies/default.json`, then invoked the CLI with `--confirm`:

```
$ python cli_ask_driver.py     # keel backend-workflow approval --params <json> --confirm
{
  "workflow": "approval",
  "ok": true,
  "code": "ok",
  "result": { "request_id": "cli-ask-1", "token": "eyJleHAiOi...", ... }
}
```

Expected: `confirmation_required` / non-zero exit. Actual: approval token issued and durable state written (`approval-results.jsonl`, `sequence: 1`).

**Contrast (controls that do work):** `forbidden` policy ⇒ `code: policy_denied`, `handler_ran: false`; corrupt policy JSON ⇒ `code: policy_error`, `handler_ran: false`. Both are audited.

---

## MEDIUM FINDINGS

### M-1 — `run_workflow` does not audit bad-params, unknown-workflow and bad-state-root outcomes

- **Severity:** MEDIUM
- **File:line:** `backend_workflows.py:1570-1586` (`state_root` stays `None` on these branches) and `:1616`/`:1547-1559` (`_audit_workflow` returns immediately when `state_root is None`).
- **Contract violated:** docstring at `:1568` states "Every branch — including bad params, denials and policy failures — is audited."

**Repro.** `wf_auth_probe.py`, case `unaudited_branches`:

```
"unaudited_branches": {
  "badparams_code": "bad_params",
  "unknown_code": "unknown_workflow",
  "badroot_code": "bad_state_root",
  "audit_delta": 0
}
```

Three security-relevant outcomes (including a caller-chosen state root escaping the trusted base) leave no record in `capability-audit.jsonl`. Audited branches (ok / policy_denied / policy_error) do write records.

### M-2 — Capability permission gate fails open when `allowed_permissions` is omitted

- **Severity:** MEDIUM
- **File:line:** `capabilities.py:78-93`, specifically `:88-89`:

```python
allowed = allowed_permissions if allowed_permissions is not None else {
    "read", "write", "execute"}
```

**Repro.** `cap_probe.py` registers an `execute`/`mutates=True` capability with a marker handler:

```
"omitted_allowed":   { "ok": true, "handler_ran": true }                 # fail open
"restricted_read":   { "error": "permission_denied", "handler_ran": false }
"empty_set":         { "error": "permission_denied", "handler_ran": false }
```

Both shipped transports call `invoke()` **without** `allowed_permissions` (`cli/main.py:289-293`, `webapp.py:715-720`), so the declared permission tier is never enforced by the hub; those surfaces rely solely on their own `--confirm` / `confirm:true` checks. Any new transport that omits the argument silently gains `execute`. Policy pre-flight itself is sound (`forbidden` ⇒ `policy_denied`, corrupt ⇒ `policy_error`, handler never ran).

### M-3 — Capability handler errors echo secrets verbatim (no output redaction)

- **Severity:** MEDIUM
- **File:line:** `capabilities.py:132-134` (`CapabilityError(f"{type(exc).__name__}: {exc}"[:500])`). The CLI (`cli/main.py:299`) and HTTP (`webapp.py:730`) print `str(exc)` unchanged.

**Repro.** `secrets_probe.py`, a handler raises `RuntimeError("call failed; token=Authorization: Bearer acme-corp-prod-key-2026-XYZ789")` (the same string that `redact_text()` correctly reduces to `[REDACTED]`):

```
"capability_error": {
  "code": "handler_error",
  "leaked": true,
  "msg": "RuntimeError: call failed; token=Authorization: Bearer acme-corp-prod-key-2026-XYZ789"
}
```

By contrast, workflow generic exceptions are deep-redacted before return and persistence (`backend_workflows.py:571-575, 589-590`): `workflow_response.leaked: false`, `workflow_ledger.leaked: false`, audit entry contains only `capability/workflow/ok/code/surface`.

### M-4 — `backend_events` ledger is forgeable and truncation is undetectable (unkeyed digest chain)

- **Severity:** MEDIUM
- **File:line:** `backend_events.py:892-896` (`_record_digest` = plain SHA-256 over `seq/prev/data`, no secret), `:924-938` (`_write_head` = unkeyed `count`/`digest`), `:1023-1096` (verification accepts a self-consistent forged chain).

**Repro.** `forge_probe.py` clones a legitimate record's envelope, changes the nested `event_id` to `FORGED-2`, recomputes the public SHA-256 digest and rewrites the unkeyed `.head`:

```
FORGE RESULT: accepted= True  ids= ['REAL-1', 'FORGED-2']
```

`ledger_probe.py` also drops tail records, recomputes the head, and replay succeeds: `"events_truncation_forged_head": {"detected": false, "count": 7}`.

**Contrast:** the `backend_workflows` ledger uses an out-of-band HMAC key (`backend_workflows.py:322-391`) and correctly fails closed: `wf_forged_record → {"accepted": false, "code": "ledger_integrity"}`, `wf_truncation → {"detected": true, "code": "ledger_integrity"}`. The `capability-audit.jsonl` / `egress.jsonl` files are plain append-only JSONL with no chain at all (`capabilities.py:141-147`, `redaction.py:125-140`) — noted as a design limitation, not counted separately.

### M-5 — SSRF guard allows CGNAT shared address space, including Alibaba Cloud metadata

- **Severity:** MEDIUM (HIGH in Alibaba Cloud ECS deployments)
- **File:line:** `runner.py:63-74` (`_ssrf_ip_allowed` checks `is_private`/`is_loopback`/`is_link_local`/`is_reserved`/`is_multicast`/`is_unspecified` and only `_SSRF_METADATA_IPS` at `:51`).

**Repro.**

```
$ python -c "from keel.runner import _ssrf_ip_allowed as f; print(f('100.64.0.1'), f('100.100.100.200'))"
True True
```

Python 3.11 marks `100.64.0.0/10` (RFC 6598 CGNAT) as neither `is_private` nor `is_reserved`, and it is absent from `_SSRF_METADATA_IPS`. A hostname resolving to `100.100.100.200` (Alibaba ECS metadata) passes `_validate_fetch_url` and is pinned/connected. All other tested categories are correctly refused: loopback `127.0.0.1`, short/decimal/hex/octal `127.1` / `2130706433` / `0x7f000001` / `0177.0.0.1`, `::1`, `169.254.169.254`, `fe80::1%eth0`, `10/8`, `192.168/16`, `172.16/12`, `fc00::1`, `fd00:ec2::254`, multicast, `0.0.0.0`, IPv4-mapped IPv6 `::ffff:127.0.0.1` / `::ffff:169.254.169.254`, and NAT64 `64:ff9b::7f00:1` — all `false`.

### L-1 — Natural-language password disclosure evades output DLP

- **Severity:** LOW
- **File:line:** `redaction.py:42-50` (`inline_secret` requires a `[:=]` assignment; `bearer_token` at `:51-52` requires a `Bearer|Basic` prefix).

**Repro.** `secrets_probe.py`:

```
"password_is":    { "leaked": true,  "out": "The password is Harbor Seal42 Tango Mike", "kinds": [] }
"bare_multiword": { "leaked": true,  "out": "Harbor Seal42 Tango Mike", "kinds": [] }
```

`Authorization: Bearer …`, `api_key = '…'`, `{"secret": "…"}`, `AKIA…` and `Basic …` are all redacted correctly. A bare multi-word string with no key context is inherently undetectable by pattern DLP; "The password is <value>" is a realistic gap worth a heuristic.

---

## CONTROLS THAT PASSED (with actual observations)

1. **Workflow authorization — forbidden/corrupt policies.** `forbidden` ⇒ `policy_denied` (403), handler never executed; corrupt JSON ⇒ `policy_error`, handler never executed. Each is appended to `capability-audit.jsonl` with no secret-bearing fields. (See M-1 for the three un-audited branches and H-1 for `ask`.)

2. **Approval.** All checks passed in `approval_probe.py`:
   - TTL bounds: `ttl_seconds` of `0`, `-1`, `86401`, `"abc"`, `True` ⇒ `bad_ttl`; `1` accepted.
   - Possession/HMAC: wrong token ⇒ `invalid_token`; single-character HMAC flip ⇒ `invalid_token`.
   - Trusted clock: `params["now"]=0` on a live token does not alter the outcome; on a token expired via `ttl_seconds=1` + `sleep(2)`, resolve ⇒ `invalid_token`.
   - Single-use/replay: second resolve with a fresh idempotency key ⇒ `replay_denied`.
   - Revocation: `revoke` ⇒ `ok`, subsequent resolve ⇒ `revoked`.
   - Serialized-snapshot replay into a fresh state root ⇒ `ledger_integrity` (missing keyed chain head).
   - **8 real processes** racing the same token: exactly one `ok`, seven `replay_denied`.

3. **Filesystem confinement** (`fs_probe2.py`). Genuinely outside sibling root ⇒ `bad_state_root`; `..` traversal and absolute `C:\Windows\Temp` ⇒ `bad_state_root`; Windows junction to an outside directory ⇒ `bad_state_root` and `_confined_file` ⇒ `path_escape`. `_confined_dir`/`_confined_file` resolve once and reject anything not beneath the trusted root.

4. **SSRF core** (`ssrf_probe.py`). Redirect revalidation: a 302 to `http://127.0.0.1:<port>/secret` is rejected on hop 2 with `refusing to fetch local address: 127.0.0.1` (SECRET-BODY never returned). DNS rebinding: `_validate_fetch_url` pins the first resolution (`8.8.8.8`) and the built connection's `_create_connection` targets exactly `('8.8.8.8', 80)` even after a second resolution returns `10.0.0.1`. Redirects disabled in urllib, proxy handler disabled, max 5 hops. (Exception: M-5 address range.)

5. **HMAC workflow ledger.** 8-process concurrent append produced 8/8 records with a valid chain; forged record and tail truncation both detected (`ledger_integrity`). (Unkeyed `backend_events` ledger: see M-4.)

6. **Concurrency** (`concurrency_probe.py`):
   - 24 threads, one approval token: `ok: 1`, `replay_denied: 23`, no other outcomes.
   - 32 processes appending to the HMAC ledger: `count: 32`, sequence numbers `1..32` contiguous, no errors.
   - 32 threads on `AtomicSpendLedger` cap 5.0: `ok: 5`, `denied: 27`, `spent: 5.0` (no overspend).
   - 8 processes × 8 inserts into the fleet SQLite DB (WAL): `rows: 64`, no errors.

---

## LIMITATIONS / COVERAGE NOTES

- **Symlink escape (POSIX `symlink_to`)** could not be created on this Windows host (`WinError 1314`, SeCreateSymbolicLink not held). Windows **junctions** were used instead and were correctly rejected. POSIX symlink behaviour is covered by the same `Path.resolve()` containment logic but was not executed here.
- **TOCTOU** between `resolve()` and the subsequent `open()` was not deterministically reproducible. The code consistently uses the already-resolved absolute path; exploiting it requires an attacker who can already write the trusted state root (which also allows direct ledger tampering — see M-4).
- **HTTP `/api/backend-workflows/*`** was verified by source inspection to call `run_workflow`, and the identical policy behaviour was confirmed end-to-end through the real CLI (`keel backend-workflow`). A live HTTP request with a valid auth token was not driven, since the token/origin gate is outside this module.
- **Redaction of bare multi-word strings** with no key/Bearer context is out of scope for pattern-based DLP by design (L-1 covers the realistic "password is …" phrasing).
- `run_workflow` attaches `http_status: 500` to successful (`code: ok`) results because `_http_status("ok")` falls through to the default; the web layer overrides this to 200. Cosmetic, not a security finding.

## RECOMMENDATIONS (priority order)

1. Remove `confirmed=True` from `backend_workflows.py:1590-1593`; use `interactive=False, confirmed=False` so saved `prompt` policies deny non-interactive workflow routes (409 `confirmation_required`), and include the workflow name in the enforced command/resource so per-workflow rules are expressible.
2. Audit all `run_workflow` exit branches, including when `state_root` cannot be derived (use the trusted base as a fallback audit root).
3. Default `allowed_permissions` to the narrowest safe tier (e.g. `{"read"}`) and require callers to opt in to write/execute.
4. Pass handler exception text through `redact_text()` before constructing `CapabilityError` in `capabilities.invoke`.
5. Replace `backend_events`' plain SHA-256 chain/head with an out-of-band HMAC key (as in `backend_workflows`), or explicitly document that ledger tamper-evidence is not a security guarantee.
6. Block RFC 6598 (`100.64.0.0/10`) and add known cloud metadata literals (e.g. `100.100.100.200`) to `_SSRF_METADATA_IPS`.
7. Extend the DLP vocabulary to natural-language credential disclosures.
