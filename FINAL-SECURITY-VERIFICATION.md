# FINAL-SECURITY-VERIFICATION — independent adversarial review

- **Target:** current main-derived tree, worktree `C:\Users\Admin\.local\share\opencode\worktree\final\security`, branch `agent/final-security`, **HEAD `35fb2b8`** (`origin/main`).
- **Posture:** read-only. **No tracked source file was modified.** All probes live in `C:\Users\Admin\AppData\Local\Temp\opencode\final-sec-probe\`. This report is the only new file.
- **Runtime:** Python 3.11.9 (Windows), `PYTHONPATH=<worktree>\keel\src`, isolated `KEEL_STATE_DIR` per case, no network egress to untrusted hosts.
- **Date:** 2026-11-25.

## VERDICT: **PASS_WITH_LIMITATIONS**

No HIGH-severity finding is reproducible at `35fb2b8`. The four HIGH findings and five MEDIUM findings raised against the stabilization branch are all closed here (workflow confirmation/policy, approval possession/clock/TTL/8-process single-use, event-ledger HMAC, SSRF CGNAT, DLP, capability error redaction). One new **MEDIUM** integrity gap remains in the *workflow* JSONL ledger (empty-file truncation bypasses the head check), plus four documented lower-severity limitations. None of the remaining items blocks release on its own, but the ledger gap should be scheduled for fix if the tamper-evidence claim is treated as a hard guarantee.

---

## Findings by severity

### HIGH — none reproducible

All previously HIGH items were re-tested adversarially and fail closed:
- Saved `ask`/`prompt` policy no longer auto-approves (H-1 from `STAB-SECURITY-REVIEW.md`).
- Approval possession, trusted clock, TTL and cross-process single-use all hold (H1–H3 from `REVIEW-FINAL-SECURITY.md`).
- Event ledger appends are cross-process atomic and HMAC-authenticated (H4 / M-4).

### MEDIUM — M-1: workflow JSONL ledger truncation-to-empty evades the HMAC head check

- **Severity:** MEDIUM
- **File:line:** `keel/src/keel/backend_workflows.py:424-425` (`_read_jsonl` early-return on an all-whitespace/empty file, before `_verify_chain_head` at `:460`), contrasted with `_verify_chain_head` at `:351-371` and the design claim at `:324-327`. The equivalent `backend_events.py:1206-1209` handles the same case correctly (`head["count"] > len(records)` ⇒ `CorruptRecordError`).
- **Impact:** A principal who can write the ledger file but not the out-of-band HMAC key can truncate `request-results.jsonl` (or any workflow JSONL) to empty. `_read_jsonl` returns `[]` silently instead of raising `ledger_integrity`; the next append restarts `seq` at 1 and rewrites the HMAC-protected head over the old one, laundering the truncation. Records are permanently lost with no integrity signal. Generic idempotency keys become reusable (approval single-use is **not** affected — see below).
- **Repro** (`final-sec-probe/wf_ledger_trunc.py`):

```powershell
$env:PYTHONPATH = "C:\Users\Admin\AppData\Local\Temp\opencode\final-sec-probe"
cd "C:\Users\Admin\AppData\Local\Temp\opencode\final-sec-probe"
python wf_ledger_trunc.py
```

Output:
```
records before: [1, 2, 3]
head before: 3
READ AFTER TRUNCATION: accepted, records = 0
append seq: 1
head after: 1
final records: [1]
ORIGINAL 3 RECORDS LOST: True
```

Expected: `READ AFTER TRUNCATION: detected -> ledger_integrity`. Actual: silently accepted.
- **Suggested fix:** remove the early return at `:424-425` (or call `_verify_chain_head` before returning) so an empty file with a non-genesis head is rejected; mirror `backend_events._read`'s `head.count > len(records)` check.
- **Not a HIGH:** approval single-use survives this truncation because `_approval_resolve` requires the durable `request` event (`backend_workflows.py:1027-1030`); after truncation the resolve fails closed with `unknown_request` (verified: `resolve 1: ok`, `resolve 2 (replay): replay_denied`, truncate, `resolve 3 after truncation: unknown_request`).

---

## Area-by-area verification (exact commands and observations)

All probes were run with:
```powershell
$env:PYTHONPATH = "C:\Users\Admin\AppData\Local\Temp\opencode\final-sec-probe"
cd "C:\Users\Admin\AppData\Local\Temp\opencode\final-sec-probe"
python <probe>.py
```

### 1. Workflow authorization — PASS
Probe: `wf_auth_probe.py`. Saved policies via the real `ExecPolicyStore` (same code path as CLI/HTTP activation), then drove direct API, real CLI subprocess and real HTTP server (`webapp.make_server(0)`, `X-Keel-Token`).

```
forbidden_direct_confirmed/unconfirmed: policy_denied, ok=false, 403, handler_ran=false
forbidden_audit: 2/2 entries code=policy_denied
ask_direct_unconfirmed: confirmation_required, 409, handler_ran=false
ask_direct_confirmed: ok, 200, handler_ran=true
corrupt_direct: policy_error, 400, handler_ran=false (1 audit entry)
cli_forbidden_confirm: code=policy_denied, rc=1
cli_ask_noconfirm: "approval requires --confirm", rc=1
http_forbidden_confirm_true: 403 policy_denied
http_ask_confirm_false: 409 confirmation_required
http_ask_confirm_true: 200 ok (handler ran after confirmation)
http_bad_token: 403 "bad token or origin"
audit_cross_process: 8 records from 8 processes, all policy_denied
```
`run_workflow` takes `confirmed=False` by default and passes it to `enforce_workflow`, which keeps the strictest decision across roots and emits `confirmation_required` (409) for `ask`; handlers are dispatched only on allow/no-policy (`backend_workflows.py:1607-1683`, `policy_enforcement.py:169-201`). Permission defaults: an in-process `capabilities.invoke` with `allowed_permissions` omitted still grants `execute` (`omitted_allowed_runs_execute: true`); with `allowed_permissions={"read"}` it denies (`restricted_read_runs: false`). HTTP derives tiers from the authenticated caller's `confirm` (`webapp.py:893-898`), so the shipped HTTP surface is least-privilege. See limitation L-2.

### 2. Approval — PASS
Probe: `approval_probe.py`.

```
ttl_bounds: 0/-1/86401/"abc"/True -> bad_ttl; 1 -> ok
resolve_no_token / resolve_token_omitted -> missing_token
resolve_wrong_token / resolve_flipped_token -> invalid_token
clock_claim_now_in_window -> invalid_token   (params["now"] ignored)
clock_live_now_zero -> ok                    (params["now"]=0 ignored)
replay_fresh_key -> replay_denied
revoke_code -> ok; resolve_after_revoke -> revoked
race8_codes: 1x ok, 7x replay_denied; race8_ok_count: 1; race8_consume_events: 1
cross_process_resolve (fresh process, persisted token): {"code":"ok","ok":true}
```
`_now()` is module-level (`:97-104`); TTL bounded 1..86400; possession via SHA-256 of presented token vs `sealed_digest` with `hmac.compare_digest` (`:1035-1042`); consume/revoke under `O_EXCL` cross-process lock (`:1025`, `:1080`).

### 3. SSRF — PASS
Probe: `ssrf_probe.py`.

```
ip_allowed: all of 127.0.0.1, 127.1, 2130706433, 0x7f000001, 0177.0.0.1,
  10/8, 192.168/16, 172.16/12, 0.0.0.0, 169.254.169.254, 100.64.0.1,
  100.100.100.200, ::1, fe80::1%eth0, fc00::1, fd00:ec2::254,
  ::ffff:127.0.0.1, ::ffff:169.254.169.254, 64:ff9b::7f00:1 => false
public 8.8.8.8 / 1.1.1.1 / 2606:4700::1111 => true
hostname_private_resolution: rejected: refusing to fetch private/internal address: 10.0.0.1
pinned_ip: 8.8.8.8
connection_targets_after_rebind: [["8.8.8.8", 80]]   (2nd resolution ignored)
redirect_to_local: rejected: refusing to fetch local address: 127.0.0.1
urls_validated_per_hop: ["http://redirect.test/start", "http://127.0.0.1:9999/secret"]
```
CGNAT (`100.64.0.0/10`) and Alibaba metadata are explicitly blocked (`runner.py:51-85,97-109`); every redirect hop is re-validated (`runner.py:955-977`); connection pins the validated literal IP (`runner.py:141-180`).

### 4. Filesystem — PASS
Probe: `fs_probe.py`.

```
state_root_confinement: dotdot/absolute_outside/C:\Windows\Temp -> bad_state_root
confined_checks: file_dotdot/file_absolute/dir_dotdot/dir_absolute -> path_escape
junction_created: true; junction_escape -> path_escape
request_project_root_escape -> path_escape
request_file_path_escape -> path_escape
request_inside: code=ok, plaintext_leaked=false
recovery_folder_escape -> path_escape; marker_written_outside=false
```
`_confined_dir`/`_confined_file` (`backend_workflows.py:664-692`) resolve once and enforce containment; caller ask/allow rules are ignored and mode pinned to `default` (`:784-798`); recovery folder is confined before writing (`:1455`). TOCTOU: the resolved absolute path is used for the open — no second caller-controlled resolution (see limitation L-3).

### 5. Secrets — PASS
Probe: `secrets_probe.py`.

```
bearer / api_key / json_secret / aws / github / openai / jwt -> [REDACTED], leaked=false
password_is "The password is Harbor Seal42 Tango Mike" -> "The password is [REDACTED]", natural_secret
capability_error msg: "RuntimeError: call failed; [REDACTED]", leaked=false
observability_log: no plaintext bearer/password, has_redacted=true
workflow: response_leaked=false, ledger_leaked=false
audit: leaked=false, has_redacted=true
artifacts: public_view_hint="cdef", public_view_leaked=false,
           export_view_leaked=false, settings_plaintext=false
```
The `natural_secret` pattern (`redaction.py:53-57`) closes the prior "password is …" gap. Secrets are redacted before workflow persistence/return (`backend_workflows._redact :240-253`), capability errors (`capabilities.py:158`), audit (`capabilities.py:264-278`) and observability events. See limitation L-1.

### 6. Event ledger — PASS with M-1 (workflow ledger only)
Probe: `ledger_probe.py` + `wf_ledger_trunc.py` + `approval_truncate_replay.py`.

```
events_read: REAL-1, REAL-2, REAL-3
forged_record: accepted=false (CorruptRecordError: record HMAC mismatch)
truncation_honest_head: detected=true (CorruptRecordError)
events_race: count=8, ids E-0..E-7, errors=[]
wf_forged: accepted=false, code=ledger_integrity
wf_truncation (empty-file): detected=false   <-- M-1 above
```
`backend_events` uses keyed chain MACs and a MAC-protected head (`backend_events.py:961-979,1020-1065,1148-1221`); forged records, truncation with recomputed head, and partial appends all fail closed; 8 concurrent processes produced a valid 8-record chain. The workflow ledger's forge detection works; only the empty-file truncation edge case (M-1) is open.

### 7. Signing — PASS
Existing tests (read-only, no source edits):
```powershell
$wt = "C:\Users\Admin\.local\share\opencode\worktree\final\security\keel"
$env:PYTHONPATH = "$wt\src"; cd $wt
python -m pytest -q tests/test_release_signing.py tests/test_signing_gate.py tests/test_release_no_secrets.py
```
`18 passed in 5.34s`.

Focused probe `signing_probe.py` (throwaway Ed25519 keypair):
```
valid -> errors=[] (accepted)
missing_artifact_sig / missing_manifest / missing_public_key / no_public_key -> fail_closed=true
tampered_artifact -> "Ed25519 artifact signature is invalid" + "SHA-256 does not match signed manifest"
mismatched_sha256_in_manifest / wrong_public_key / forged_manifest_signature -> fail_closed=true
```
`verify_signed_release` (`release/signing.py:133-206`) returns errors rather than raising and never accepts a missing/invalid/mismatched signature. "Expired" signature is not applicable: no expiry/not_before field exists in the release manifest schema (`release/*.py` has no expiry logic).

### 8. Credential revocation — PASS
Probe: `revoke_probe.py`.

```
after_save: env_matches=true, disk_plaintext=false, enc_marker=true,
            hint="cdef", stored_key_roundtrip=true
after_remove: removed=true, env_cleared=true, entry_gone=true, plaintext_anywhere=false
same_process_reapply: applied=[], env_reappeared=false
restart_apply (fresh process): env=KEY, applied=["openrouter"]
restart_remove (fresh process): removed=true, env=null
after_restart_revoke_reapply (third process): env=null, applied=[]
shell_key_preserved=true
```
Disk holds AES-256-GCM ciphertext (`secret_store.py:111-127`); `remove_provider_key` pops the env var only if this process applied it (`settings_store.py:185-198`); `apply_stored_keys` never overrides a shell key (`:211-230`). Revocation survives process restarts and cannot be reapplied. See limitation L-4 (Y3 descriptor bookkeeping).

---

## Corroborating existing test runs (read-only)

| Command (from `keel/`, `PYTHONPATH=<worktree>\keel\src`) | Result |
|---|---|
| `pytest -q tests/test_backend_workflows.py tests/test_stab_workflow_auth.py tests/test_prod_workflow_audit.py tests/test_capabilities_integration.py tests/test_permission_contracts.py` | 109 passed |
| `pytest -q tests/test_backend_events.py tests/test_event_bus_persistence.py tests/test_stab_events_integration.py` | 78 passed |
| `pytest -q tests/test_prod_revocation.py tests/test_secret_storage.py tests/test_redaction.py tests/test_secrets_policy_hardening.py` | 34 passed |
| `pytest -q tests/test_security_contracts.py tests/test_security_remediation.py tests/test_security_validation.py tests/test_webhook_security.py` | 152 passed, 1 skipped |
| `pytest -q tests/test_release_signing.py tests/test_signing_gate.py tests/test_release_no_secrets.py` | 18 passed |
| `pytest -q tests/test_policy_bypass_regression.py` | 2 passed |

Total corroborating: **393 passed, 1 skipped**, no failures attributable to the review.

---

## Limitations / lower-severity observations

- **L-1 (LOW, inherent):** A bare multi-word secret with no key/Bearer context ("Harbor Seal42 Tango Mike") is not redacted (`redaction.py:18-58`). The realistic "password is …" phrasing is covered. Pattern DLP cannot detect context-free secrets by design.
- **L-2 (MEDIUM-by-design, not a transport flaw):** `capabilities.invoke` with `allowed_permissions=None` still defaults to `{"read","write","execute"}`, so a *new* in-process caller that omits the argument gains execute. The shipped HTTP transport passes explicit derived tiers and CLI/TUI require `--confirm`. Treat the hub default as permissive for legacy compatibility, not as a security boundary. Source: `capabilities.py:128-138`, `webapp.py:893-898`.
- **L-3 (coverage limitation):** POSIX `symlink_to` could not be created on this Windows host (SeCreateSymbolicLink not held); Windows junctions were used and rejected. A deterministic TOCTOU exploit between `resolve()` and `open()` was not reproducible — the code uses the already-resolved path. Exploitation would require an attacker who can already write the trusted state root.
- **L-4 (MEDIUM, known gap):** Y3 `config_contracts` revocation descriptors are bookkeeping only. An `ALL_CLIENTS` descriptor reports `credentials_deleted: true` / `clients_signed_out: true`, yet the real stored provider key and its env var remain (`revoke_probe.py`: `actual_stored_key_still_present: true`). Do not treat `build_revocation`/`RevocationLedger.apply` as credential deletion; use `settings_store.remove_provider_key` / `pairing.PairingStore.revoke`.
- **L-5 (N/A):** Signing has no time-bound signature concept; "expired" was verified as not applicable rather than silently assumed.

## Repro assets

`C:\Users\Admin\AppData\Local\Temp\opencode\final-sec-probe\`:
`pcommon.py`, `wf_auth_probe.py`, `approval_probe.py`, `ssrf_probe.py`,
`fs_probe.py`, `secrets_probe.py`, `ledger_probe.py`, `wf_ledger_trunc.py`,
`approval_truncate_replay.py`, `signing_probe.py`, `revoke_probe.py`,
and captured outputs `wf_auth_out.json`, `ssrf_out.json`.

**Final verdict: PASS_WITH_LIMITATIONS.** M-1 (workflow ledger empty-file truncation) is the only actionable code defect found; L-2 and L-4 are documented design gaps, and L-1/L-3/L-5 are inherent or coverage limitations. No HIGH finding blocks release at `35fb2b8`.
