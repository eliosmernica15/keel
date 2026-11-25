# STAB-PROVIDER-EVIDENCE

Provider / credential / MCP stabilization evidence for branch `agent/stab-provider`.
All tests are offline and deterministic. Credentials are synthetic fixtures in
disposable state directories; no network call, no paid usage, no real
credential, no push.

## Git state and environment

| Item | Value |
|---|---|
| Worktree | `C:\Users\Admin\.local\share\opencode\worktree\stab\provider` |
| Branch | `agent/stab-provider` |
| Stabilization HEAD merged | local `stabilization/post-promotion-production-2026-11-25` @ `f74743a9e2769082baf76a0e67d057b0d1914ef3` (fetched `origin` @ `9c3e994117f852763d05c10b32979ecd82febf5d`) |
| Merge commit | `8dd4278dcf7de5e83e65b5334f0eafa9fc81fdb6` |
| Provider fixes commit | `1809cac736188bf1e2d7ff478ce4e780740cf043` |
| M-5 / L-1 remediation commit | this commit (`HEAD`) |
| Python / pytest | 3.11.9 / 9.0.2 |
| Import path | `PYTHONPATH=<worktree>/keel/src` is **required**; without it `keel` resolves to the main checkout at `C:\Users\Admin\Desktop\Claude clone\keel\src` and the worktree code is not exercised |
| Clean HOME / state | `C:\Users\Admin\AppData\Local\Temp\opencode\stab_clean_home` and `...\stab_clean_state` (both empty before the run; `HOME`, `USERPROFILE`, `KEEL_STATE_DIR` redirected) |

## Verification results (exact)

Required set, clean HOME, worktree source:

```
python -m pytest tests/test_stab_provider.py tests/test_provider_validation_ready.py \
  tests/test_prod_provider.py tests/test_redaction.py tests/test_prod_revocation.py \
  tests/test_secret_storage.py -q
128 passed in 7.64s
```

Pre-fix control (same four required modules plus the new regression tests,
temporary source tree rebuilt from pre-fix HEAD blobs):

```
117 passed, 7 failed in 4.07s
FAILED test_m5_special_ranges_are_refused_by_ip_filter[100.64.0.1]
FAILED test_m5_special_ranges_are_refused_by_ip_filter[100.100.100.200]
FAILED test_m5_special_ranges_are_refused_by_ip_filter[192.0.0.9]
FAILED test_m5_dns_pinning_seam_refuses_hostile_resolution[100.64.0.1]
FAILED test_m5_dns_pinning_seam_refuses_hostile_resolution[100.100.100.200]
FAILED test_m5_dns_pinning_seam_refuses_hostile_resolution[192.0.0.9]
FAILED test_l1_natural_language_password_is_redacted_in_validation_report
```

## Full-suite context (informational)

A full `python -m pytest tests -q` run (started before the follow-up edits and
spanning the merge) reported **7 failed, 4459 passed, 51 skipped, 3707 subtests
passed in 569 s**. The failures are unrelated to provider work: six are the
known release-artifact-dependent cases (`test_distribution_package` ×2,
`test_gap_closure` ×2, `test_release_integrity` ×1 — no
`RELEASE-MANIFEST.json`/`RELEASE-SHA256SUMS.txt` in the worktree) plus
`test_release_controls::test_gitleaks_config_is_present_and_narrowly_scoped`
(which expects 10 allowlists but the merged stabilization commit `101fcec`
ships 25). `test_fleet_delegation::test_delegation_timeout_returns_error_to_caller`
was timing-sensitive in that loaded run and passes in isolation (`1 passed in
13.65 s`) in the clean-HOME environment. None of these files were edited by
this branch.

>>>>>>> agent/stab-provider
## 1. Provider validation workflow

Verified in `keel/tests/test_stab_provider.py` (24 original + 3 follow-up tests)
and `test_provider_validation_ready.py`.

| Behaviour | Result | Evidence |
|---|---|---|
| Missing optional credential | truthful `SKIP` | `auth_present=SKIP`, `credential_format=SKIP`, `live_provider=SKIP`, `configured=[]`; no PASS for `auth_present`/`streaming_response` |
| Blank/whitespace credential | truthful `SKIP` (was fake `PASS`) | `configured_providers()` uses `.strip()`; detail says `not set or blank` |
| Malformed configured credential | `FAIL`, no live call | `credential_format=FAIL`, `live_provider=FAIL`, injected `build_adapter` records **zero** calls |
| Real provider error | `FAIL`, redacted | `ProviderError(401)` → `streaming_response=FAIL`, category retained, synthetic key absent from JSON |
| Cancellation | not a success | `TurnCancelled` → `streaming_response=SKIP` (was `PASS` "cancelled cleanly") |
| Timeout budget | enforced | `timeout_s=0.02` against a 0.4 s adapter → `live_timeout=FAIL`, no streaming PASS (parameter was previously unused) |
| No `--live` | no calls | recording adapter factory called zero times; `live_provider=SKIP` |
| Mock adapter matrix | honest PASS | `streaming_response=PASS`, `usage_tracking=PASS` |

## 2. Provider contracts (`provider_contracts.py`)

Verified by `test_prod_provider.py` plus new tests: auth failure and invalid
credentials are non-retryable and non-fallback; timeout/429 use bounded
deterministic backoff (`[0.0, 1.0]` with `max_backoff_seconds=1.0`); HTTP
normalization and malformed bodies never echo the synthetic secret; nested
stream error frames are now classified instead of `unknown`; a streamed cancel
event after content is a normal `cancelled` stop with partial text preserved;
partial failure does not retry or fall back; fallback occurs only when
explicitly configured. Catalog copies are isolated and schema/counts validated.

Fixes committed in `1809cac`:
- `sanitize_event`: wrap a nested `{"error": {...}}` frame before classification and redact its message;
- `execute_stream`: check `CATEGORY_CANCELLED` before the `partial_failed` branch.

## 3. Credential lifecycle

| Behaviour | Evidence |
|---|---|
| Encrypted at rest | `settings.json` contains `enc: aes256gcm-v1`, no plaintext; `stored_key()` round-trips |
| Applied to env | `save_provider_key()` → `KEEL_GOOGLE_API_KEY` equals the synthetic key |
| Removed from env **and** store | `remove_provider_key()` → env var absent, `stored_key() is None`, `apply_stored_keys() == []`, no plaintext in any state file |
| No re-apply after restart | two fresh interpreters with clean `HOME`/`USERPROFILE` and the same state dir: writer saves then removes; reader asserts no stored key, no env var, provider not listed as configured |
| Redaction | `SecretStoreError` from a wrong master key contains no secret and no `__cause__`; validation reports redact the credential in error details |
| Secret providers | `ProviderChain.resolve(reveal=False)` reports presence/length but `value=None`; no secret in `describe()` or saved provider config |

Residual: `settings.json.bak` still retains the old **encrypted** blob (rolling
backup, no secure delete). No plaintext was found in any file after removal.

## 4. MCP / revocation

- Removed MCP connector: `parse_servers()` returns `[]`; `McpManager.tool_schemas() == []`; `call()` returns `ok=False, "not connected"`.
- Project approval: `approve()` → `is_approved() True`; `revoke()` → fresh on-disk read `{}`, `is_approved() False`, activation allow-list empty.
- Pairing: `PairingStore` fresh instance after `revoke()` reports `is_paired() False`; `revoked: true` persisted.
- HTTP MCP error bodies are redacted before reaching logs/errors (`test_http_mcp_error_body_is_redacted`).

## 5. M-5 — SSRF guard (MEDIUM, fixed)

`keel/src/keel/runner.py`: `_ssrf_ip_allowed()` relied on stdlib flags; Python
3.11 reports `100.64.0.0/10` as neither private nor reserved, so both CGNAT and
Alibaba ECS metadata `100.100.100.200` were allowed.

| Probe | Before | After |
|---|---|---|
| `_ssrf_ip_allowed("100.64.0.1")` | `True` | `False` |
| `_ssrf_ip_allowed("100.100.100.200")` | `True` | `False` |
| `_ssrf_ip_allowed("8.8.8.8")` / `("93.184.216.34")` | `True` | `True` (no over-block) |

Fix: `_SSRF_METADATA_IPS` gains `100.100.100.200`, and a new
`_SSRF_BLOCKED_NETWORKS` tuple explicitly blocks `0.0.0.0/8`, `100.64.0.0/10`,
`169.254.0.0/16`, `192.0.0.0/24`, `192.88.99.0/24`, `198.18.0.0/15`,
`198.51.100.0/24`, `203.0.113.0/24`, `224.0.0.0/4`, `240.0.0.0/4`,
`255.255.255.255/32`, plus IPv6 special prefixes (`::/128`, `::1/128`,
`::/96`, `::ffff:0:0/96`, NAT64, 6to4, documentation, ULA, link-local,
multicast). Matching is version-aware. Regression tests exercise each listed
range both directly and through the DNS-pinning seam
(`monkeypatch runner._ssrf_getaddrinfo` + `_validate_fetch_url`), proving the
hostile address is refused **before** any connect, while a public IP still
passes and is pinned.

Note: `security_contracts.classify_address()` already classified CGNAT as
`RESERVED` and refused it; the gap was the `runner.web_fetch` guard.

## 6. L-1 — natural-language password disclosure (LOW, local mitigation)

`keel/src/keel/redaction.py` is **not owned by this agent and was not edited**.
Before (pre-fix probe):

```
redaction.check_output_dlp("The password is Harbor Seal42 Tango Mike") -> []
redact_text(...) output still contains "Harbor Seal42 Tango Mike"  (leaked = True)
```

Local defence added in owned `provider_validation.py`: `_NATURAL_SECRET_RE`
matches `password|passphrase|secret|api[-_ ]key|access[-_ ]token|token` followed
by `is <value>` and replaces the value with `[REDACTED]`; it is applied both in
`_safe_error()` and recursively to the entire `run_validation()` report.

```
after: "Harbor Seal42 Tango Mike" not in json.dumps(report) -> True
       "[REDACTED]" in json.dumps(report) -> True
```

**Exact change required in `redaction.py` (for the lead / owning agent):**

1. In `_PATTERNS` (after `inline_secret`, before `bearer_token`), add:
   ```python
   ("spoken_secret", re.compile(
       r"(?i)\b(?:password|passphrase|secret|api[ _-]?key|"
       r"access[ _-]?token|token)\s+(?:is|are|was|equals)\s+"
       r"[^\r\n.!?]{3,160}")),
   ```
   Plain `pattern.sub("[REDACTED]", ...)` replaces the whole phrase including
   the label, which is acceptable; preserving the label requires a callable
   replacement in `redact_text()` and a named group.
2. Add to `keel/tests/test_redaction.py`:
   ```python
   def test_natural_language_password_is_redacted():
       text = "The password is Harbor Seal42 Tango Mike"
       redacted, counts = redact_text(text)
       assert "Harbor Seal42 Tango Mike" not in redacted
       assert "spoken_secret" in counts
       assert check_output_dlp(text)
   ```
   A bare multi-word string with no key context remains undetectable by
   pattern DLP by design and is out of scope.

## Pending / residual gaps

- **Live-provider validation is explicitly pending.** No real credential was
  used and no real provider call was made. All PASS results come from injected
  deterministic adapters; real authentication/quota/billing behaviour is
  unverified.
- `redaction.py` authoritative fix (above) is pending lead action; this branch
  only hardens the validation-report boundary.
- `core.providers.validate` is registered as a `read` capability in
  `capability_registry.py` while `live=True` performs network calls; consider
  an execution-tier gate (file not owned here).
- Y3.9 revocation descriptor/ledger records intent only; it does not delete
  credentials or invalidate sessions (documented negative evidence in
  `test_prod_revocation.py`).
