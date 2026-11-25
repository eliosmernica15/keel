# FINAL RELEASE ACCEPTANCE — INDEPENDENT REVIEW

**VERDICT: BLOCK. Promotion of candidate `CANDIDATE_HEAD` to `main` is NOT authorized.**

Reviewer: independent final-acceptance subagent (`agent/prod-accept`). No candidate source was authored by this review; the only file added is this report.

| Field | Value |
|---|---|
| Candidate under review | `CANDIDATE_HEAD25a20290961332abc3a4e9b3c2dcb2cd4` (designated tip) |
| Baseline | `origin/main` = `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` (unchanged) |
| Worktree | `C:\Users\Admin\.local\share\opencode\worktree\production\accept` |
| Review date | 2026-11-24 |
| Overall | **BLOCK — 4 blocking findings (B1–B4) + 1 unresolved HIGH** |

**Provenance note.** On arrival the worktree branch `agent/prod-accept` pointed at `e6e7efc` (the single squashed promotion commit); the mission designates `CANDIDATE_HEAD`. `e6e7efc` is a direct ancestor of `CANDIDATE_HEAD`, and every document the mission asks to audit (`PROD-*.md`, `BACKEND-SECURITY-REVIEW.md`, `PRODUCTION-ARCHITECTURE-AUDIT.md`, `PRODUCTION-READINESS-MATRIX.md`, …) exists only at `CANDIDATE_HEAD`. I therefore fast-forwarded the branch with `git merge --ff-only CANDIDATE_HEAD` (clean tree, no commits lost) before reviewing. All results below are from the designated tip. `PRODUCTION-REQUIREMENT-RECONCILIATION.md:13-19` had already warned the lead that the audited commit and the candidate tip did not match; that mismatch is now larger than the two changes it described.

---

## Gate results at a glance

| Mandatory gate | Result | Exact evidence |
|---|---|---|
| 1. Manifest classification / no frontend import | **FAIL** | 69 of 424 changed paths unclassified; frontend site files imported; temp artifact committed; dual classification C2 unresolved |
| 2. Evidence claims honest / no false green | **FAIL (partly)** | Matrix is honest (0 `production_verified`), but `PRODUCTION-ARCHITECTURE-AUDIT.md` §5 "no unrelated frontend work" is false at this tip and all readiness evidence is attributed to stale SHA `CANDIDATE_HEAD` |
| 3. Audit findings have fix commits + regression tests | **PARTIAL FAIL** | 11 of 12 HIGH/MEDIUM findings fixed with named regression tests; architecture HIGH-1 has no fix commit; MEDIUM-6/7 only partially evidenced |
| 4. Re-run key gates | **PASS** | `verify_v6_audit.py` OK; `verify_backend_operation.py --strict` 421/421 OK; dependency graph FRESH; license gate OK; 8/8 YAML parsed |
| 5. No secrets/temp artifacts; clean tree | **FAIL** | `keel/_prod_suite_tmp.py` is tracked (temp runner with a hardcoded personal temp path); no real secrets found; tree clean |
| 6. `main` unmodified | **PASS** | `origin/main` = `ecba9d2…` before and after |
| 7. Final verdict | **BLOCK** | Matrix has **5 `unverified` + 2 `blocked`** mandatory gates; mission rule says these do not authorize promotion |

---

## B1 — BLOCKER: gate 1 classification and scope isolation fail at the designated tip

`promotion-classification.json` still contains **383** entries written for the earlier candidate; `git diff --name-only origin/main..HEAD` now has **424** paths.

* **69 changed paths are not classified at all** — all 10 `PROD-*-EVIDENCE.md`, 6 new `BACKEND-*.md`, 5 new `PRODUCTION-*.md`, `PROMOTION-PATH-INVENTORY.txt`, the two manifest files themselves, `keel/requirements.lock.txt` / `requirements-sbom.json`, 12 new `test_prod_*.py` files, `keel/_prod_suite_tmp.py`, 5 new backend source files (`fleet/service.py`, `permissions.py`, `provider_catalog.py`, `runner.py`, `safety.py`), 22 `perf-harness/*` files, and 4 site assets. The manifest's claim "Documented here so the promotion contains no unexplained path" is false at this tip.
* **Frontend work was imported.** The exact check used by `PRODUCTION-ARCHITECTURE-AUDIT.md` §5 now returns content:

  ```
  $ git diff --name-only origin/main -- keel/site keel/desktop keel/desktop-app
  keel/desktop/src-tauri/Cargo.toml
  keel/site/assets/img/qr-download.svg
  keel/site/download.html
  keel/site/ui/download-clone.css
  keel/site/ui/download-clone.js
  ```

  `download.html` (+701 lines), `download-clone.css` (+1,682), `download-clone.js` (+699) come from commit `6970867 feat(site): rebuild /download as Claude-style Keel download page`. The mission permits exactly one exception — the one-line `Cargo.toml` version constant — not a UI rebuild. The audit's "no unrelated frontend/desktop work" statement is a **stale false green** (it was true at `e6e7efc`, not at `CANDIDATE_HEAD`).
* **Two paths are classified `UNRELATED_EXCLUDED` yet present**: `keel/desktop/src-tauri/Cargo.toml` (documented one-line `0.1.0`→`0.1.1` exception — acceptable) **and** `keel/scripts/check_version_sync.py` (an 8-line functional change adding the Cargo.toml source to the version gate — not the documented exception). The manifest tail calls it `REQUIRED_BACKEND_DEPENDENCY`, but both the path table (line 102) and `promotion-classification.json` line 77 still say `UNRELATED_EXCLUDED`. This is finding **C2** of `PRODUCTION-REQUIREMENT-RECONCILIATION.md`, still uncorrected at the candidate tip.
* Four frontend-only test files classified `BACKEND_TEST_OR_CI` were deleted from the candidate (`test_accessibility_hardening.py`, `test_desktop_hardening.py`, `test_web_surface_hardening.py`, `test_validation_script.py`). The manifest documents this as deliberate; it is not itself a blocker, but it makes the classification JSON internally inconsistent.

## B2 — BLOCKER: gate 5 — a temp artifact is committed

`keel/_prod_suite_tmp.py` is tracked at the candidate tip:

```python
import os, sys, pytest
home = r"C:\Users\Admin\AppData\Local\Temp\opencode\prodhome"
...
sys.path.insert(0, "src")
raise SystemExit(pytest.main(["-q", "-o", "faulthandler_timeout=120"]))
```

This is a local test-runner scratch file with a hardcoded personal temp path, not a production artifact. Conversely, no real credential was found: the secret-pattern sweep over changed text files produced only synthetic fixtures (`sk-abcdefghijklmnopqrstuvwxyz`, `AKIAIOSFODNN7EXAMPLE`, sample JWTs), consistent with `PROD-SUPPLY-CHAIN-EVIDENCE.md` §7's own caveat that a full-history gitleaks run was not done locally. Working tree is clean (`git status --short --branch` → `## agent/prod-accept` only).

## B3 — BLOCKER: gate 7 — the mandated matrix itself forbids promotion

`PRODUCTION-READINESS-MATRIX.md` (20 gates, PR-01…PR-20) and `PRODUCTION-READINESS-REPORT.md` state:

| Classification | Count | IDs |
|---|---|---|
| pass | 13 | PR-01, 02, 03, 04, 05, 07, 08, 10, 11, 12, 13, 15, 18 |
| **unverified** | **5** | PR-06 (live providers), PR-09 (rollback drill), PR-14 (credential purge / live revoke), PR-16 (clean-checkout reproducibility), PR-17 (clean-VM upgrade/recovery) |
| **blocked** | **2** | PR-19 (native Linux/macOS), PR-20 (signing, live providers, owner authorization) |
| production_verified | 0 | none |

The mission's rule is explicit: a gate marked `external_validation_pending` / `unverified` / `blocked` means promotion to `main` is NOT authorized. Five `unverified` and two `blocked` gates remain open. These statuses are honestly reported (no false green here): no deployment, no signed/published installer, no clean-VM checks, no native macOS run, no live provider call.

Additional honesty defect: the matrix and report are labelled **candidate `CANDIDATE_HEAD` / worktree `agent/prod-ops`** and their line references point to that commit, while the designated candidate is `CANDIDATE_HEAD` (44 further commits, 97 changed files, 2,068 new lines). The evidence is therefore not evidence for the artifact being promoted. `PROD-PERFORMANCE-EVIDENCE.md` §6.1–6.3 still labels three issues "BLOCKING" even though `80061d9` fixed them with `test_prod_perffix.py` — stale, not a false green.

## B4 — BLOCKER: unresolved HIGH from the architecture audit (no fix commit)

`PRODUCTION-ARCHITECTURE-AUDIT.md` HIGH-1 — "Workflow call path bypasses the capability hub and its boundaries" — **remains unfixed at `CANDIDATE_HEAD`**. Direct code inspection of `webapp.py`:

```
/api/backend-workflows/<name>:
  capabilities.invoke      -> False
  policy_enforcement       -> False
  enforce(                 -> False
  record_audit             -> False
  allowed_permissions      -> False
  run_workflow             -> True
```

`backend_workflows.py` has zero references to `policy_enforcement`, `allowed_permissions` or `record_audit`; `capabilities.py` registers no workflow capability. The route adds a broad `try/except` (fixing HIGH-2's crash symptom) and accurate HTTP status mapping, but the two paths still have divergent enforcement/audit semantics. No commit in `e6e7efc..CANDIDATE_HEAD` addresses HIGH-1 and no regression test for single-path enforcement exists. This alone blocks per the "any HIGH blocks" rule used by `BACKEND-SECURITY-REVIEW.md:9`.

---

## Gates re-run by this reviewer (exact results)

All commands run from the candidate worktree at `CANDIDATE_HEAD`.

| Command | Result | Exit |
|---|---|---|
| `python scripts/verify_v6_audit.py` | `registry rows: 865` … `matrix rows: 865` … **`CONSISTENCY OK`** | 0 |
| `python scripts/verify_backend_operation.py --strict` | `865` features (854 verified / 9 not_started / 2 blocked); 20 modules, 421 attributed IDs; `=== EVIDENCE-BASED GATE (ENFORCED) ===`; `attributed IDs audited: 421`, `passing all checks: 421`, `failing: 0`; **`BACKEND OPERATION VERIFICATION OK`** | 0 |
| `python keel/scripts/build_dependency_graph.py --check` | **`FRESH`** | 0 |
| `python scripts/check_model_licenses.py` | `license registry: 11 entries, 0 bundled`; **`LICENSE GATE OK`** | 0 |
| YAML parse of `.github/workflows/*.yml` | 8 files, all `yaml.safe_load` OK (build-desktop, lifecycle, offline-license, provider-validation, python-tests, secret-scan, signing-readiness, verify-install) | 0 |
| `python -m pytest -q keel/tests/test_prod_secfix.py keel/tests/test_prod_cap_gate.py keel/tests/test_prod_api.py` (with `PYTHONPATH=keel/src`) | **`52 passed in 24.83s`** | 0 |
| `git rev-parse origin/main` | `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` (unchanged) | — |
| `git status --short --branch` | `## agent/prod-accept` (clean before this report) | — |

## Independent-audit finding → fix → regression-test verification

| Report / finding | Fix commit | Regression test | Spot-check |
|---|---|---|---|
| Security H-1 redirect SSRF | `15828f5` (merge of `5a8b6ca`) | `test_prod_secfix.py::test_h1_redirect_to_loopback_is_refused`, `::test_h1_redirect_chain_is_bounded`, `::test_h1_non_http_redirect_is_refused` | ran file → pass |
| Security H-2 DNS-rebind TOCTOU | `15828f5` | `::test_h2_rebinding_resolver_is_called_once_and_connection_is_pinned`, `::test_h2_ssrf_ip_filter_*` | ran file → pass |
| Security H-3 junction/symlink Tier-2 bypass | `15828f5` | `::test_h3_tier2_classifies_resolved_target`, `::test_h3_read_file_through_junction_is_blocked`, `::test_h3_safe_path_rejects_symlink_escape_outside_root` | ran file → pass |
| Security M-1 share redaction | `15828f5` | `::test_m4_share_view_redacts_shared_secret_vocabulary` | ran file → pass |
| Security M-2 caller-chosen state_root | `15828f5` | `::test_m5_caller_cannot_choose_an_outside_state_root`, `::test_m5_subdirectory_of_trusted_base_is_allowed` | ran file → pass |
| Security M-3 ledger integrity | `15828f5` | `::test_m6_records_carry_a_hash_chain`, `::test_m6_forged_append_is_rejected`, `::test_m6_modified_and_truncated_records_are_rejected`, `::test_m6_legacy_plaintext_ledger_is_rejected` | ran file → pass |
| Architecture HIGH-2 raw exception escape | `9ec612c` / `c0cf661` | `test_prod_api.py::test_workflow_bad_params_400_unknown_workflow_404`, `::test_malformed_saved_policy_is_json_error_and_audited`, `::test_workflow_lock_timeout_is_structured_json` | ran file → pass |
| Architecture HIGH-3 malformed policy escapes boundary | `CANDIDATE_HEAD` | `test_prod_cap_gate.py::test_corrupt_saved_policy_is_typed_policy_error` | ran file → pass |
| Architecture MEDIUM-4 permission tiers not enforced | `CANDIDATE_HEAD` | `::test_ask_policy_without_confirmation_fails_closed`; `test_prod_api.py::test_workflow_permission_denial_maps_403`, `::test_read_capability_needs_confirm_when_policy_prompts` | ran files → pass |
| Architecture MEDIUM-5 eager import / false "lazy" claim | `80061d9` | `test_prod_perffix.py::test_import_capabilities_does_not_import_all_backends`, `::test_first_invoke_validates_dispatch_before_running_a_function` | fix + named tests exist (not run in the 3-file spot check) |
| Architecture MEDIUM-6 orphan observability/event modules | `d0a9b6b` hardens the modules but does **not** wire them | no runtime consumer found (`import keel.backend_events` / `backend_observability` occurs nowhere under `src/keel` outside tests) | **not closed** (MEDIUM) |
| Architecture MEDIUM-7 import-order schema publication | `80061d9` removes `_publish_schemas_on_import` and makes `sync_capability_schemas()` on-demand | `test_prod_perffix.py` has no explicit two-import-order regression test | fix present; dedicated regression test not found |
| **Architecture HIGH-1 workflow path bypass** | **none** | **none** | **OPEN HIGH — see B4** |

`REVIEW-*`, `master-plan-v6-high-findings-fix.md`, `master-plan-v6-independent-acceptance.md` and the other plan-era review documents were also checked for unresolved HIGH/MEDIUM items; their quantitative claims (865 IDs, 854/9/2, 421 attribution, strict gate) reproduce correctly, and no additional open HIGH was found there beyond B4.

---

## Required before a new acceptance review

1. Rebuild the promotion manifest/classification at the actual candidate tip: classify all 69 new paths; remove the 4 site assets and `keel/_prod_suite_tmp.py`; reconcile the dual `Cargo.toml` classification (C2) and the `check_version_sync.py` classification; update or retract the architecture audit's §5 "no frontend" claim.
2. Delete `keel/_prod_suite_tmp.py` from the candidate tree.
3. Fix architecture HIGH-1 (route workflows through `capabilities.invoke()` or explicitly apply `policy_enforcement.enforce()`, `allowed_permissions` and `record_audit()` to the workflow path) and add a regression test asserting one enforcement/audit path.
4. Either close or formally descope architecture MEDIUM-6 and add the missing import-order regression test for MEDIUM-7.
5. Re-issue `PRODUCTION-READINESS-MATRIX.md` / `PRODUCTION-READINESS-REPORT.md` against the final candidate SHA, and close the 5 `unverified` + 2 `blocked` gates with owner/external evidence. Until then, promotion remains unauthorized.

**Final verdict: BLOCK.** Candidate `CANDIDATE_HEAD` must not be promoted to `main`.
