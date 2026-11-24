# PROD-AUTH-EVIDENCE — authentication / authorization production hardening

Candidate: `e6e7efc` (`agent/prod-auth` worktree `…\worktree\production\auth`).
Date: 2026-11-24. Platform: Windows 11, Python 3.11.9, pytest 9.0.2.

Owned files changed:

* `keel/src/keel/permissions.py`
* `keel/src/keel/permission_contracts.py`
* `keel/tests/test_prod_auth_hardening.py` (new)

`keel/src/keel/policy_enforcement.py` was audited only; no change was required.
No frontend files and no non-owned files were edited. Nothing was pushed.

---

## 1. Confirmed defects fixed

### PA-01 (HIGH) — config allow/ask rule widened a saved execution policy

`permissions.evaluate` returned an `allow` (or `ask`) verdict from the Tier-1
rule loop **before** calling `policy_enforcement.enforce`, even though the
comment in the same function and the module contract state that a saved
execution policy is binding and "cannot be widened by ask/allow rules or by
`bypassPermissions` mode".

Pre-fix reproduction (default policy forbids `git reset --hard` / host
`evil.test`, exact config allow rule present):

```
FORBIDDEN command with exact allow rule -> allow config allowed by rule 'run_shell(git reset --hard)'
FORBIDDEN egress with exact allow rule  -> allow config allowed by rule 'web_fetch(domain:evil.test)'
```

Pre-fix regression run of the new tests (`pytest -q keel/tests/test_prod_auth_hardening.py`):

```
test_config_allow_rule_cannot_widen_forbidden_exec_policy  ... AssertionError: 'allow' != 'deny'
test_config_allow_rule_cannot_widen_forbidden_egress_policy ... AssertionError: 'allow' != 'deny'
test_config_ask_rule_cannot_widen_forbidden_policy         ... AssertionError: 'ask' != 'deny'
3 failed, 14 passed
```

Fix: config deny rules remain the first hard floor (D-001); the saved policy is
then consulted **before** any config ask/allow grant or mode baseline. A policy
`deny`/`ask` verdict is returned immediately; only an explicit policy `allow`
falls through to config rules and finally overrides the mode baseline.

Regression tests (fail pre-fix, pass post-fix):

* `test_config_allow_rule_cannot_widen_forbidden_exec_policy`
* `test_config_allow_rule_cannot_widen_forbidden_egress_policy`
* `test_config_ask_rule_cannot_widen_forbidden_policy`

No-regression guarantees: `test_config_deny_rule_still_precedes_policy_floor`,
`test_policy_allow_still_overrides_mode_baseline`,
`test_policy_prompt_fails_closed_without_responder`.

### PA-02 (HIGH) — cross-process ApprovalStore write loss

Re-verification of the prior cross-instance locking operation showed real
loss. `_file_lock` caught only `FileExistsError`; Windows raises
`PermissionError` for the same `O_EXCL` create race, which propagated and
dropped the approval. `_write_atomic` could also fail on `os.replace` while a
concurrent reader held the file open, and a transient read error could be
mistaken for an empty store and clobber all earlier approvals.

Pre-fix probes (throwaway, not committed):

```
30-thread probe (corrected barrier): saved 30/30, no errors
multi-process probe (8 processes x 24 writes): saved 13/24, 11 missing
mp_diag2: procs=4 saved=29/32, 3 x "ApprovalStoreError: failed to persist approvals"
mp_cause: PermissionError [Errno 13] on …\<digest>.lock from os.open(O_CREAT|O_EXCL)
```

The committed regression test (`test_approval_store_30_processes_lossless`,
30 synchronized child processes) failed pre-fix with
`ApprovalStoreError: failed to persist approvals`.

Fix in `permission_contracts.py`:

* `_file_lock` treats **any** `OSError` from the `O_EXCL` open (including
  Windows `PermissionError`) as contention and retries to the deadline.
* `_write_atomic` retries `os.replace` on transient `OSError`.
* `_load(strict=True)` retries transient read errors for mutations and raises
  instead of returning an empty document — a transient sharing violation can
  no longer erase saved approvals. Read-only queries still fail closed to an
  empty view.
* The per-path in-process lock now covers `add_pending` and `reject_pending`
  as well as `decide`.

### PA-03 (MEDIUM, latent) — durable approval state depended on thread order

An explicit `always` reply whose proposed pattern was covered by an earlier
broader saved pattern (e.g. `cmd1*` covering resource `cmd10`) returned early
and never recorded the exact pattern. The existing
`test_w39_concurrent_approval_writes_are_lossless` is flaky on pristine HEAD
(verified: one run passed, the next failed), and became deterministic once
PA-02 stopped aborting writes.

Fix: an explicit `always` reply with a non-empty proposed pattern is now always
recorded (after the configured-deny hard-floor check on that pattern), even if
a saved approval already covers the request. `once` / `reject` /
non-interactive semantics are unchanged, and the deduplication key remains
`(action, exact pattern)`.

---

## 2. Guarantees and their tests

| # | Guarantee | Test(s) | Result |
|---|---|---|---|
| G1 | Config deny wins over everything, including a policy allow and bypass mode | `test_config_deny_rule_still_precedes_policy_floor`, `test_permission_contracts.py::test_w32_live_permissions_evaluator_still_first_match` | pass |
| G2 | Saved policy forbids cannot be widened by allow/ask rules | `test_config_allow_rule_cannot_widen_*`, `test_config_ask_rule_cannot_widen_forbidden_policy` | pass (fail pre-fix) |
| G3 | Missing responder fails closed; `prompt` denies non-interactively | `test_policy_prompt_fails_closed_without_responder`, `test_approval_store_noninteractive_never_auto_grants`, `test_permission_contracts.py::test_w312_*` | pass |
| G4 | `confirm` only records a real approval | `test_policy_confirm_semantics_in_enforce`, `test_security_validation.py::test_mutating_confirmation_required` | pass |
| G5 | Concurrent policy change is observed on the next evaluation (no stale cache) | `test_concurrent_policy_change_is_observed_without_stale_cache` | pass |
| G6 | Alternate transports (argv/cmd/code/prompt/endpoint/URL) cannot bypass policy | `test_alternate_command_and_url_fields_cannot_bypass_policy`, `test_policy_enforcement.py::test_alternate_command_fields_and_inline_shell` | pass |
| G7 | `allowed_permissions` separation on capability invoke | `test_capability_allowed_permissions_separation`, `test_security_validation.py::test_capability_read_write_execute_separation` | pass |
| G8 | Missing/invalid bridge credentials and origin refused | `test_security_validation.py::test_token_and_origin_validation`, `test_local_api_bound_to_loopback` | pass |
| G9 | Project isolation of saved approvals | `test_approval_store_project_isolation`, `test_permission_contracts.py::test_w39_different_project_scopes_are_isolated` | pass |
| G10 | Session isolation of pending requests and feedback (cross-session denial) | `test_approval_store_pending_isolation_across_sessions` | pass |
| G11 | Configured deny is a hard floor approvals cannot grant | `test_approval_store_configured_deny_is_a_hard_floor`, `test_permission_contracts.py::test_w39_configured_deny_can_never_be_overridden_by_always` | pass |
| G12 | Revoked approval is not reused | `test_approval_store_revoked_pattern_is_not_reused` | pass |
| G13 | Corrupt/tampered approval file fails closed | `test_approval_store_corrupt_or_tampered_file_fails_closed`, `test_permission_contracts.py::test_w39_corrupt_store_fails_closed` | pass |
| G14 | 30-thread cross-instance writes lossless | `test_approval_store_30_threads_lossless` | pass |
| G15 | 30-process cross-instance writes lossless | `test_approval_store_30_processes_lossless` | pass (fail pre-fix) |

---

## 3. Commands and results

Required verification (run from the worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_prod_auth_hardening.py','keel/tests/test_permission_contracts.py','keel/tests/test_security_validation.py']))"
```

Result: **94 passed in 16.31s**; repeated three more times — 94 passed in
37.73s, 26.14s, 27.25s (no flakes).

Adjacent backend suites:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_policy_enforcement.py','keel/tests/test_policy_bypass_regression.py','keel/tests/test_secrets_policy_hardening.py','keel/tests/test_webapp.py','keel/tests/test_cli_surface_hardening.py']))"
```
Result: **51 passed**.

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_security_contracts.py','keel/tests/test_security_remediation.py','keel/tests/test_runtime_defects.py','keel/tests/test_cli_surface_hardening.py','keel/tests/test_web_surface_hardening.py']))"
```
Result: 143 passed, 1 skipped, **4 failed** — all four are
`test_web_surface_hardening.py` frontend JS/PWA assertions. The same four fail
on pristine `e6e7efc` (verified via a detached worktree), so they are
pre-existing and outside this backend-only scope (no frontend edits allowed).

---

## 4. Entry-point verification (read-only)

* **`capabilities.invoke`** — `allowed_permissions` defaults to
  `{read, write, execute}` when the caller omits it; a capability whose
  permission is not in the supplied set raises `permission_denied`.
  `confirm` is forwarded as `bool(context.get("confirm"))` and only a `deny`
  policy verdict aborts the call. See limitation L1.
* **Webapp** — `/api/capabilities/invoke` requires token + origin and requires
  `request.get("confirm") is not True` (strict boolean) for write/execute or
  `mutates` capabilities; it passes `interactive=True`. Read-tier capabilities
  are not pre-probed for policy prompts (L1).
* **TUI** — for read-tier capabilities it explicitly calls
  `policy_enforcement.enforce(..., interactive=True, confirmed=False)` and
  prompts when the verdict is `ask`; it fails closed on an unreadable policy.
  Mutating capabilities prompt unconditionally. This path is safe against L1.
* **CLI** — `keel capability invoke` requires `--confirm` for write/execute and
  passes `interactive=False`, so a policy `prompt` becomes `deny` at the
  boundary. Safe against L1.

---

## 5. Accepted limitations and rationale

* **L1 — `capabilities.invoke` ignores an `ask` policy verdict** (webapp,
  read-tier capabilities carrying a command/URL). `enforce` returns `ask` in
  interactive mode and `invoke` aborts only on `deny`, so the handler can run
  without a recorded confirmation. Fixing this requires changing
  `keel/capabilities.py` and/or `keel/webapp.py`, which are explicitly
  read-only for this operation. Recommended follow-up: treat every non-`allow`
  enforce verdict as a hard stop (or hand-off to an approval workflow) in
  `invoke`, and pre-probe read-tier capabilities in the webapp as the TUI does.
  The strict-boolean confirm gate on mutating entry points is unaffected.
* **L2 — `allowed_permissions` is not narrowed per user/role** by the webapp,
  TUI or CLI; the local bridge is a trusted single-user surface. Callers that
  need least privilege must pass the set explicitly (verified in G7).
* **L3 — approval persistence trusts the local filesystem.** There is no
  cryptographic signature on `permission-approvals/<hash>.json`; a local
  privileged process can edit saved patterns. Configured deny rules remain a
  hard floor (G11), and corrupt data fails closed (G13). Signing is out of
  scope for these stdlib-only additive contracts.
* **L4 — stale-lock stealing at 30 s.** A holder stalled longer than
  `_LOCK_STALE_S` can have its lock stolen, which is inherent in lock files
  used for crash recovery. Risk is reduced by the per-path in-process lock,
  bounded IO retries and strict reads; it is accepted because removing
  stealing would permanently wedge the store after a crash.
* **L5 — revocation is out-of-band.** There is no atomic revoke API in the
  owned modules; revocation is performed by removing the persisted pattern.
  The sequential guarantee is proven (G12); a revoke racing a decision is not
  linearizable because the saved-allow check is a separate read. A future
  revoke API should take the same path lock.
* **L6 — four pre-existing frontend test failures** (see §3) are documented
  but not fixed: no frontend changes are permitted in this operation.
