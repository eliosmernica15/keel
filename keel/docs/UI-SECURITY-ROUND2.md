# UI Security — Round 2 verification (release gate)

**Status:** verification report, not a source-change log. No backend source was
modified; no commits or pushes were made. Evidence is the exact pytest output
reproduced at the end of this document.

Scope: workspace trust, permission tiers and approval broker, secrets,
filesystem boundaries, bridge auth/origin and the public mirror, audit accuracy
and redaction. Tests live in `keel/tests/verify_security_round2_*.py` and are
owned exclusively by this verification round.

## Findings requiring lead attention

| ID | Severity | Defect | Location | Evidence / test |
| --- | --- | --- | --- | --- |
| F-01 | **High** | The workspace-trust flag is written but **never enforced**. `read_project_file`, `write_project_file` and `list_project_tree` return/accept project data even when `trusted = 0`; their HTTP routes do not check it either. Revocation is therefore cosmetic and "no reads before trust" is false. | `keel/src/keel/fleet/service.py:411-423`, `:440-452`, `:377-409`; `keel/src/keel/fleet/routes.py:368-374`, `:405-414`, `:948-960`. Writer: `service.py:342-348`, `routes.py:920-929`. A repo-wide search finds `trusted` referenced only in the DB migration (`fleet/db.py:337`), the skills list (`routes.py:436`) and the setter — never in an enforcement branch. | `verify_security_round2_trust.py::test_untrusted_project_file_read_is_refused`, `::test_untrusted_project_tree_is_refused`, `::test_untrusted_project_write_is_refused` (all `xfail`, documented). |
| F-02 | **Medium** | A mode-table `deny` is promoted to `ask` when `interactive=True`. In `evaluate`, after the deny/ask/allow rule loop, `verdict == "deny"` falls through the `if verdict == "allow"` branch, skips the non-interactive deny branch and returns the generic `ask` decision. Real Fleet sessions use `interactive=False` (`session.py:60`), so exposure is limited to interactive callers, but the permission contract is violated. | `keel/src/keel/permissions.py:281-295`. Pre-existing failing test: `keel/tests/audit_agent_execution_lifecycle.py:179-192`. | `verify_security_round2_permissions.py::test_dont_ask_mode_never_promotes_deny_to_ask` (`xfail`). Direct reproduction also run: that pre-existing test fails with `assert 'ask' == 'deny'`. |
| F-03 | **Medium** | Approval-card summaries are built from raw tool input and returned to the browser without redaction. A shell command or delegated prompt containing a credential is exposed through the card. The *audit* table is safe (fingerprints only); the card is not. `redaction.redact_text` exists but is not applied on this path. | `keel/src/keel/fleet/approvals.py:57-101` (`args_summary`), exposed by `keel/src/keel/compat.py:340-347` and served at `keel/src/keel/webapp.py:1145-1155`. | `verify_security_round2_secrets.py::test_approval_card_summary_redacts_a_secret_in_shell_command` (`xfail`). |
| F-04 | **Low / hardening** | The Origin check is built from the **request-supplied `Host` header** (`expected = f"http://{host}"`), so a DNS-rebound name whose Origin matches its own Host passes the check. A valid token is still required and the cookie is `SameSite=Strict`, so this is not a standalone bypass — but the check should be pinned to the loopback address and bound port. | `keel/src/keel/webapp.py:257-259`. | `verify_security_round2_bridge.py::test_origin_is_pinned_to_loopback_not_the_request_host` (`xfail`). |
| F-05 | **Low / doc divergence** | The returned key hint is always the last four characters (and the whole key when shorter than four), while plan item E6.1 requires all-dots unless at least eight middle characters remain hidden. The UI contract only promises a four-character hint, so this is a plan/contract mismatch rather than a broken control. | `keel/src/keel/settings_store.py:174`, `keel/src/keel/fleet/routes.py:699`. | Not xfailed: current behaviour matches `UI-BACKEND-CONTRACT.md`. Flagged for a decision on which rule wins. |

## Controls verified as working

1. **Permission tiers** — deny → ask → allow → mode order, deny wins regardless of
   allow order, ask becomes deny without an interactive callback, bare-name deny
   removes the tool from the manifest, unknown tool/mode fails closed.
2. **Approval broker** — `once` approves without a standing policy; `always` and
   `never` persist per-agent policies; `reject` is a one-off denial; invalid
   decisions are refused; decisions are scoped to the requesting agent; a
   decided or expired card cannot be re-decided (guarded `pending → decided`
   SQL transition at `fleet/service.py:740-766`).
3. **No frontend bypass** — the session consults the Fleet decider only for a
   `consent_required` verdict (`session.py:991-1007`); deny rules, hooks and Tier 2
   stay authoritative. Tier-2 checks run only on the allow path
   (`session.py:1087-1097`), after Tier 1, and cannot be widened by a card.
4. **Secrets** — AES-256-GCM with a fresh 12-byte nonce per value, ciphertext
   bears no plaintext, tampering fails closed, 0600 creation for the key file,
   deterministic keyring/passphrase/file fallback. `public_view` and
   `export_view` expose no key material; imported plaintext keys are encrypted
   on write.
5. **Filesystem boundaries** — upload names reduce to a safe basename; workspace
   read paths refuse `..` and symlink escape; the directory picker returns only
   directory names; project file helpers refuse traversal and symlink escape;
   Tier 2 refuses catastrophic commands, secret-bearing paths and unparseable
   commands.
6. **Bridge auth / mirror** — loopback-only bind, token via header/query/cookie
   with constant-time compare, rotation revokes old credentials, non-GET Origin
   check, CSP/nosniff/referrer headers. The Next.js BFF strips `host`,
   `connection`, `cookie`, `origin` and `referer`, injects the token server-side
   and rejects `..` segments. The public mirror contains no `/api/fleet/`,
   `providers/save` or `providers/credential` calls.
7. **Audit history** — requested and decided events are recorded in order with
   accurate `granted`/`refused` outcomes, including `once`, `never`, `timeout`
   and `restart`; only 16-hex fingerprints are stored, never raw arguments;
   limits are clamped to 500 and audit bundles detect tampering.

## Test inventory

| File | Tests |
| --- | --- |
| `verify_security_round2_trust.py` | 8 (3 xfail — F-01) |
| `verify_security_round2_permissions.py` | 18 (1 xfail — F-02) |
| `verify_security_round2_secrets.py` | 8 (1 xfail — F-03) |
| `verify_security_round2_paths.py` | 22 (2 skipped: symlinks unavailable on this Windows host) |
| `verify_security_round2_bridge.py` | 8 (1 xfail — F-04) |
| `verify_security_round2_audit.py` | 7 |

`xfail(strict=False)` is used deliberately: a known defect stays visible as an
expected failure while the suite remains green, and flips to XPASS as soon as
the backend is fixed. No security control was weakened and no backend source
was changed.

## Exact test output (round-2 suite)

Command (from `keel/`):

```
python -m pytest tests/verify_security_round2_trust.py tests/verify_security_round2_permissions.py tests/verify_security_round2_secrets.py tests/verify_security_round2_paths.py tests/verify_security_round2_bridge.py tests/verify_security_round2_audit.py -q
```

Output:

```
....xxx....x.....................x.......s...s............x............  [100%]
63 passed, 2 skipped, 6 xfailed in 13.96s
```

Direct reproduction of the pre-existing F-02 failure (from `keel/`):

```
python -m pytest tests/audit_agent_execution_lifecycle.py::test_plan_mode_is_read_only_while_default_mode_requires_consent -q
F                                                                        [100%]
FAILED tests/audit_agent_execution_lifecycle.py::test_plan_mode_is_read_only_while_default_mode_requires_consent
1 failed in 1.35s
```

Direct mode probe (`dontAsk`, write, no rules):

```
interactive=True : ask
interactive=False: deny
```

## Full-suite baseline (informational, outside this round's ownership)

`python -m pytest -q` from `keel/` did **not** finish within a 600 s client
deadline; it reached 41 % and was terminated (exit 143). It showed failures
before any round-2 test file could be implicated. A fail-fast run identified
the first one:

```
python -m pytest -q -x --tb=no
1 failed, 116 passed in 31.49s
FAILED tests/test_backend_hub_integration.py::test_verify_confirms_all_modules_import_and_declare_features
```

Detail: `d3_backend` reports 12 undeclared registry features (`D3.1`, `D3.2`,
…) at `tests/test_backend_hub_integration.py:104`. This is a pre-existing
backend-registry issue, not caused by this verification round. The full suite
is therefore not currently green independently of the round-2 tests.
