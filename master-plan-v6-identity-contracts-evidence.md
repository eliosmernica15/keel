# Identity contracts — implementation evidence (Y4 P0 assignment)

**Branch:** `agent/a8-y4` · **Baseline:** `4e0b804`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a8-y4`

## Scope and registry confirmation

The assignment was to implement every `not_started` **P0** `Y4.*` row in
`PLAN-INDEX.json` as a stdlib-only, pure descriptor/policy module. A programmatic
read of the 14 `Y4.*` rows at the assigned baseline found **exactly three** with
`priority == "P0"` **and** `status == "not_started"`:

| ID | Priority | Original priority | Status | Full registry feature text | Acceptance criterion |
| --- | --- | --- | --- | --- | --- |
| Y4.3 | P0 | P0 | `not_started` | first-boot sign-in test-fire | Already Master 9.3; add "fail loudly with the exact provider error". (source detail: first-boot sign-in test-fire with a 1-token call so a zero-credit account fails loudly) |
| Y4.9 | P0 | P0 | `not_started` | Persona file with rigor contract + coding-agent routing + desktop control plane | `PERSONA.md` sections; routing table consumed by the router (X1.x / A4.5). (source detail: in one `SOUL.md`) |
| Y4.13 | P0 | P0 | `not_started` | version badge and zero-secrets release scan | Release script takes `VERSION`; scan on artifacts (A4.8). (source detail: `VERSION=x.y.z build` pattern; release scan proves zero secrets baked in) |

All 11 other `Y4.*` rows are P1/P2 at this baseline (Y4.1 has `original_priority`
P0 but its current `priority` is P1) and were **not** in scope.
`P0-BATCHES.md` section "Y4 — 3 features" lists the same three IDs.

These are `[T]` rows sourced from the nicks-stack README/tree. Addendum 4's
builder protocol says no `[T]` row may be implemented from copied code, and the
Addendum 5 persona deep-read explicitly says not to copy upstream persona
instructions. The implementation therefore uses original wording and Keel's own
vocabulary throughout; **no upstream prompt, asset or file content is embedded
in the new module**, and an originality gate refuses verbatim copies.

`PLAN-INDEX.json` and all other existing files were **not** edited; no row
status was changed here.

## Files owned (only these were added)

* NEW `keel/src/keel/identity_contracts.py`
* NEW `keel/tests/test_identity_contracts.py`
* NEW `master-plan-v6-identity-contracts-evidence.md` (this file)

## Requirement → implementation map

| Feature / requirement | Contract surface in `keel.identity_contracts` |
| --- | --- |
| Y4.9 — persona/SOUL descriptor, `PERSONA.md` sections, consumed by router | `SoulDescriptor`, `REQUIRED_SOUL_SECTIONS`, `SoulSection` (identity, rigor, routing, desktop_control, trust_boundary), `default_soul`, `render_soul`, `validate_soul`, `soul.resolve_route` |
| Y4.9 — rigor contract | `RigorRule`, `DEFAULT_RIGOR_RULES` (evidence before claims, never fabricate, unknown plainly, independent estimates/no user anchoring, anti-sycophancy with Keel's own safety limits kept) |
| Y4.9 — coding-agent routing + desktop control plane | `RoutingRule`, `RoutingTable`, `RouteDecision`, `RouteTarget`, `DEFAULT_ROUTING_RULES` (local desktop → browser DOM → single-writer coding specialist → conductor/general), `DEFAULT_DESKTOP_TOOLS` (11 local tools) |
| No copied prompts/assets | `PromptOrigin`, `PromptAsset`, `ORIGINAL_SOUL_TEMPLATE`, `is_verbatim_copy`, `assert_original`, `copied_prompt`/`verbatim_copy` validation codes, `IdentityContractError` |
| Y4.3 — 1-token first-boot test-fire | `PROBE_TOKEN_BUDGET = 1`, `SignInProbe`, `ProbeResponse`, `evaluate_probe`, `ProbeResult`, `budget_must_be_one`/`probe_budget_exceeded`/`budget_exceeded` checks |
| Y4.3 — zero-credit fails loudly with the exact provider error | `ProviderError` (exact code/message preserved), `ProbeResult.loud_message`, `is_zero_credit`, `ZERO_CREDIT_TOKENS`, `skipped_probe`, `BootDecision`, `first_boot_decision` (fail-closed) |
| Y4.13 — version badge + `VERSION=x.y.z build` | `VERSION_RE`, `parse_version`, `is_valid_version`, `build_command`, `parse_build_command`, `VersionBadge` (never claims `clean` without a passing scan) |
| Y4.13 — zero-secrets scan on artifacts (A4.8) | `Artifact`, `SecretPattern`, `SECRET_PATTERNS`, `scan_secrets`, `SecretFinding`, `ZeroSecretsScan`, `ReleaseVerification`, `verify_release`, `no_artifacts_scanned`/`secrets_found`/`manifest_version_mismatch` checks |
| No secret leakage | `redact_secrets`, `ProviderError.public_message`/`as_dict(reveal=False)`, findings record marker + line/column only, never the matched secret value |
| Deterministic validation | frozen dataclasses, immutable tuples, `ValidationIssue`, `_sort_issues`, `canonical_digest`, content-derived labels/sort keys independent of input order |
| No host state | stdlib-only imports (`dataclasses`, `enum`, `hashlib`, `json`, `re`, `typing`); no file, socket, process, clock or chance access; caller supplies every artifact, response and credential *reference* |

## Verification

Both targeted commands were run from the worktree root with the required
`sys.path` insert (the editable `keel` install points at the main workspace, so
the worktree path must be first).

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_identity_contracts.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
```

Result: **69 tests passed in 0.047 s** (stdlib-only runner).

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_identity_contracts.py']))"
```

Result: **69 passed, 31 subtests passed in 1.10 s**.

A full-suite run with `PYTHONPATH` pinned to this worktree's `keel/src`
(`python -m pytest -q keel/tests`) reported **2441 passed, 51 skipped, 92
subtests passed, 21 failed in ~7m40s**. None of the 21 failures imports or
exercises `identity_contracts`; they are pre-existing baseline/environment
failures in unrelated areas (e.g. `test_release_manifest_has_policy_fields`,
`test_c12_package_manager_manifests`, `test_plan_index.py::test_authoritative_source_hashes_unchanged`,
`test_tool_registry::test_create_native_registry`, `test_webapp::test_upload_roundtrip`
using `C:\Users\Admin\.keel\uploads`, and a known `test_compat_runtime` timing
flake). Several are already documented as baseline limitations in other
evidence documents. The three files added here do not change any existing
module, test or registry data.

## Adversarial coverage (all green)

* **No copied prompts/assets** — a verbatim copy of the canonical persona text
  is detected by n-gram overlap and rejected by `PromptAsset.validate`,
  `assert_original` and `validate_soul` (`copied_prompt`); short overlaps are
  allowed; attributed adaptations must name their source.
* **Rigor contract** — required sections are enforced (missing sections,
  empty/duplicate rigor rules, empty agent id all fail); rendered `SOUL.md` is
  byte-for-byte deterministic and contains identity, rigor, routing, desktop
  control and trust-boundary sections.
* **Routing** — local desktop is preferred only when healthy (fallback when
  not), DOM work prefers browser then local desktop, multi-file code requires
  both `coding_specialist_available` and `single_writer` (else conductor),
  unknown intents default to the general agent, duplicate intents are invalid,
  and resolution is independent of rule input order.
* **One token only** — `token_budget` must equal 1; a crafted budget of 7 is
  rejected; an HTTP 200 response consuming 5 tokens still fails with
  `probe_budget_exceeded`.
* **Fail loudly, exact error** — a 402/insufficient-quota response keeps the
  provider's exact code and message; the loud failure includes provider, code,
  the unmodified diagnostic and a zero-credit remediation; generic text never
  replaces the provider message; synthesis is explicit and evidenced when the
  provider omits an error body; failed results with no error, or passing
  results carrying an error, are invalid.
* **Secret hygiene** — `sk-`, `ghp_`, `AKIA`, `AIza`, `xox`, JWT and PEM private
  key markers are detected; findings contain marker name and line/column but
  never the secret; provider errors are redacted for display and serialized
  output while the exact raw message stays available for trusted local logs;
  a secret value in `credential_ref` is refused.
* **Fail-closed gates** — empty probe lists block first boot; explicit skips
  need `allow_unverified=True`; empty artifact lists never produce a `clean`
  badge or a passing release; manifest version mismatches and invalid versions
  block release.
* **Purity/determinism** — an AST test asserts only stdlib imports and no
  host-I/O calls; result collections are frozen dataclasses in tuples; all
  validation outputs are sorted; digests and decisions reproduce exactly.

## TDD evidence

`test_identity_contracts.py` was written and run before the module existed;
collection failed with
`ModuleNotFoundError: No module named 'keel.identity_contracts'`. After adding
the module, three failures were diagnosed: first-boot reason labels used the
result index (input-order dependent) and were replaced with provider/model
content-derived labels; two test fixtures used a wrong field name (`id` vs
`rule_id`) and an empty-text case with non-empty text. The suite then reached
69/69 green under both unittest and pytest.

## Integration seams for the lead (not made here — file ownership)

1. **Persona** — load `default_soul()` (or a user-supplied `SoulDescriptor`
   validated with `validate_soul`) and render it with `render_soul()` into
   `PERSONA.md`/`SOUL.md`; validate before activating a persona.
2. **Router** — call `soul.resolve_route(intent, capabilities=...)` (X1.x/A4.5)
   so the persona table is the single source of routing truth; local desktop
   health, browser availability and single-writer status are supplied by the
   caller as capabilities.
3. **First boot / onboarding** — build a `SignInProbe` with a credential
   *reference*, pass the real provider reply in as a `ProbeResponse` to
   `evaluate_probe`, and gate boot with `first_boot_decision`; render
   `ProbeResult.loud_message()` on failure.
4. **Release** — from `VERSION=x.y.z build`, use `parse_build_command`, feed
   artifact bodies to `verify_release`, publish `ReleaseVerification.badge.text()`
   only when `ok`, and surface `scan.findings` (never raw secrets) in logs.
