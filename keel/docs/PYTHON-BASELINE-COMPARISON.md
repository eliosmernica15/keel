# Python failure baseline comparison — feature branch vs main

Agent B, Keel full-plan completion round. Read-only investigation: **this agent changed no backend source, no generated plan file, no git state, and made no commit or push.** All test-file edits described below were made by the lead or other agents working in the same shared worktree; this agent only observed and verified them.

## 1. Recorded SHAs

| Tree | Path | SHA | Notes |
|---|---|---|---|
| Feature branch (at test launch) | `C:\Users\Admin\Desktop\keel-frontend-worktree` | `e03855017f0bde5d75a964612f18ecf35d92680a` | branch `feat/frontend-completion-2026-11-24` |
| Feature branch (first recheck) | same | `3863a2b8f8d4ae7d411a0df553ee8edcf9192c8f` | `docs(plan)` commit; only `keel/docs/MASTER-PLAN-INVENTORY.md` changed |
| Feature branch (final recheck) | same | `dee01be02c088c0117295d0ffca1326ce81a36b8` | `fix(desktop)` commit; 6 desktop/packaging files, **no** `keel/src` or `keel/tests` delta |
| Baseline main | `C:\Users\Admin\Desktop\keel-baseline-main` | `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` | clean detached worktree at `origin/main` (requested SHA) |

None of the concurrent commits touched Python source or tests, so the Python results below apply to all three feature SHAs.

## 2. Exact commands and environment

Both full-suite commands were run from each worktree's `keel/` directory with the identical environment requested by the lead:

```powershell
# Feature worktree
cd C:\Users\Admin\Desktop\keel-frontend-worktree\keel
$env:PYTHONPATH='src'; python -m pytest -q

# Baseline main worktree
cd C:\Users\Admin\Desktop\keel-baseline-main\keel
$env:PYTHONPATH='src'; python -m pytest -q
```

Both were launched in the background with stdout/stderr merged and teed to files:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q 2>&1 | `
  Tee-Object -FilePath "C:\Users\Admin\AppData\Local\Temp\opencode\agentB-feature-pytest-full.txt"
$env:PYTHONPATH='src'; python -m pytest -q 2>&1 | `
  Tee-Object -FilePath "C:\Users\Admin\AppData\Local\Temp\opencode\agentB-main-pytest-full.txt"
```

Environment: Windows; `python 3.11.9` (`C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe`); `pytest 9.0.2`; `keel/tests/conftest.py` sets `KEEL_TOKEN=tracetoken12345` and suppresses real MCP servers. A globally installed **editable** `keel` package points outside both worktrees (`C:\Users\Admin\Desktop\Claude clone\keel\src\keel\__init__.py`); HTTP tests spawn `python -m keel … --fake-script` children which can import that checkout if `PYTHONPATH` is relative. Up to 8 other agents' pytest processes ran concurrently, which materially slowed subprocess-heavy tests.

### Timing / edit-timing caveat (required by lead)

- A first full-suite attempt launched ~22:31 was killed by a 600 s client timeout before its summary (feature 73 %, main 81 % at SIGTERM, exit 143). It produced no final counts and is superseded below.
- The reported second attempts were launched at `22:41:19` with a 1800 s timeout; **pytest collected/imported the test modules at launch**.
- The lead applied uncommitted edits to `keel/tests/test_gap_closure.py` (`test_c411_visual_diff_and_capture` → `tmp_path`) and `keel/tests/test_plan_index.py` (CRLF-normalized hashing) **after that collection** (observed as ` M` at 22:45). Other agents restored the remaining skip guards later, also after collection. Therefore **both final full-suite runs executed the pre-edit test code**; the feature run's printed traceback for `test_integrity_cli_on_real_artifacts` even shows the post-collection guard source because pytest's formatter re-read the file at report time.
- All focused re-runs in §4.2-§4.4 reflect the **current** (post-edit) worktree. Do not read the full-suite counts below as the post-fix state.

## 3. Why the previously reported seven failures appeared

The prior "7 failed" report (`keel/docs/IMPLEMENTATION-PROGRESS.md:1244-1254`, `master-plan-v6-cli-surface-evidence.md:163-175`, `master-plan-v6-recovery-evidence.md:175-197`) was recorded on the feature line at `5dbc5f9`, **before** the Windows-safety fixes from `16977a3` reached the current baseline.

`git diff ecba9d2..e038550` showed that the feature branch had **reverted** those Windows-safety fixes for four test files:

| Test file | Main `ecba9d2` | Feature `e038550` at launch |
|---|---|---|
| `test_distribution_package.py` | `_require_release_artifacts()` skip guard (main lines 10-15), called at lines 28 and 38 | guard removed → hard `FileNotFoundError` |
| `test_gap_closure.py` | skip guards at main lines 26-27 and 41-42 | guards removed → hard `FileNotFoundError` |
| `test_release_integrity.py` | skip guard at main lines 62-65 | guard removed → hard `AssertionError` |
| `test_plan_index.py` | CRLF-normalized hashing at main line 68 | raw-byte hashing at line 67 → hash mismatch on a CRLF checkout |
| `test_gap_closure.py::test_c411_visual_diff_and_capture` | `tmp_path` fixture | hard-coded `/tmp/a.png`, `/tmp/b.png` (global shared paths) |

Commit `16977a3` ("Fix Windows-only test defects: temp paths and CRLF-normalized source hashes") is an ancestor of **both** trees; commit `4deb532` ("Review snapshot of Keel Master Plan v6 final implementation (tree of fbf0135)") is an ancestor of the **feature branch only** (not of main) and reverted them. `keel/release/` is absent in **both** worktrees, so the environment was identical — only the feature branch's test guards differed.

I verified the hash root cause directly: the three checked plan sources have CRLF line endings in both worktrees; SHA-256 of their **CRLF→LF normalized** bytes is `da1dd5dc81d7f85f…`, `e4e314a5a0c31f78…`, `b42219150271fa9e…` — exactly the prefixes asserted by `test_plan_index.py`. The mismatch was purely the removed normalization, not a stale fixture.

## 4. Real commands and output

### 4.1 Six deterministic cases — before any edits

```powershell
# Identical command in both worktrees, from keel/
$env:PYTHONPATH='src'; python -m pytest -q --tb=short `
  tests/test_distribution_package.py::test_release_manifest_has_policy_fields `
  tests/test_distribution_package.py::test_checksums_file_matches_manifest_artifacts `
  tests/test_gap_closure.py::test_c12_package_manager_manifests `
  tests/test_gap_closure.py::test_c122_airgap_bundle_and_verification `
  tests/test_release_integrity.py::test_integrity_cli_on_real_artifacts `
  tests/test_plan_index.py::test_authoritative_source_hashes_unchanged
```

- **Feature:** `FFFFFF` → `6 failed in 5.79s`
- **Main:** `sssss.` → `1 passed, 5 skipped in 3.45s`

Exact feature errors (pre-edit):

1. `tests/test_distribution_package.py:21` — `FileNotFoundError: …\keel\release\RELEASE-MANIFEST.json`
2. `tests/test_distribution_package.py:30` — `FileNotFoundError: …\keel\release\RELEASE-SHA256SUMS.txt`
3. `tests/test_gap_closure.py:25` → `src/keel/release_gaps.py:24` — `FileNotFoundError: …\keel\release\RELEASE-MANIFEST.json`
4. `tests/test_gap_closure.py:37` → `src/keel/release_gaps.py:156` → `:24` — same `FileNotFoundError`
5. `tests/test_release_integrity.py:65` — `AssertionError: [FAIL] checksums … [FAIL] manifest … [FAIL] latest_yml … [FAIL] sidecar_version … [FAIL] dependency_inventory … integrity: 2/7 passed`, returncode 1
6. `tests/test_plan_index.py:67` — `AssertionError: Keel_Master_Plan_v5.md changed: 47b346bc9b7ee26a51e5fe2576e9a9fa5cc6e75e339ab554e90aa2bfd79c1f13` (expected `da1dd5dc81d7f85f…`)

### 4.2 Full-suite summary — baseline main (completed)

```
$env:PYTHONPATH='src'; python -m pytest -q
2 failed, 1289 passed, 37 skipped in 750.05s (0:12:30)
```

1. `tests/test_quick_ask.py::test_quick_ask_endpoint_uses_real_runtime` — `TimeoutError: timed out` at `tests/test_quick_ask.py:47` → `_post()` line 26 (`urlopen(req, timeout=30)`).
2. `tests/test_webapp.py::test_run_streams_events_and_done_marker` — `TimeoutError: timed out` at `tests/test_webapp.py:174` → `_post()` line 52 (`resp.read()`), with a benign `ConnectionAbortedError: [WinError 10053]` in the server thread.

The five release-artifact cases are **skipped** on main and the CRLF-normalized hash case **passes** — establishing rows 1-6 of §5 as feature-branch-introduced rather than baseline failures.

### 4.3 Full-suite summary — feature branch (completed, pre-edit code)

```
$env:PYTHONPATH='src'; python -m pytest -q
9 failed, 4020 passed, 48 skipped, 3621 subtests passed in 991.91s (0:16:31)
```

Pre-edit failure list, with short messages:

1. `tests/test_distribution_package.py::test_release_manifest_has_policy_fields` — `FileNotFoundError: …\keel\release\RELEASE-MANIFEST.json`
2. `tests/test_distribution_package.py::test_checksums_file_matches_manifest_artifacts` — `FileNotFoundError: …\keel\release\RELEASE-SHA256SUMS.txt`
3. `tests/test_gap_closure.py::test_c12_package_manager_manifests` — `FileNotFoundError` via `src/keel/release_gaps.py:24`
4. `tests/test_gap_closure.py::test_c122_airgap_bundle_and_verification` — `FileNotFoundError` via `src/keel/release_gaps.py:156`/`:24`
5. `tests/test_permission_contracts.py::test_w39_concurrent_approval_writes_are_lossless` — `AssertionError: assert 10 == 12` at `tests/test_permission_contracts.py:526` (two of twelve concurrent approval writes lost)
6. `tests/test_plan_index.py::test_authoritative_source_hashes_unchanged` — hash mismatch `47b346bc…` vs `da1dd5dc…`
7. `tests/test_quick_ask.py::test_quick_ask_endpoint_uses_real_runtime` — `TimeoutError` at 30 s client ceiling
8. `tests/test_release_integrity.py::test_integrity_cli_on_real_artifacts` — `AssertionError`, returncode 1, missing artifacts
9. `tests/test_webapp.py::test_run_streams_events_and_done_marker` — `TimeoutError` in `resp.read()`

Failures 1-4, 6 and 8 are the deterministic regressions of §5. Failures 5, 7 and 9 are discussed below.

### 4.4 Verifications against the current (post-edit) worktree

Lead's exact command:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q `
  tests/test_gap_closure.py::test_c411_visual_diff_and_capture `
  tests/test_plan_index.py::test_authoritative_source_hashes_unchanged
```

→ **`2 passed in 2.43s`** (lead reported `2 passed in 7.12s`; difference due to concurrent load).

Immediately after the lead's edit I re-ran the six deterministic cases and got **`FFFFF.` / `5 failed, 1 passed in 3.77s`** — only the hash case was fixed at that moment, because the missing-artifact skip guards had not yet been restored. **This discrepancy was reported to the lead.**

Subsequently, other agents restored all remaining guards in `test_distribution_package.py`, `test_gap_closure.py` (both `c12*` cases) and `test_release_integrity.py`. The final verification of the same six-case command is:

```
sssss.                                                                   [100%]
1 passed, 5 skipped in 1.69s
```

This matches main's pre-edit behavior exactly. **All six deterministic regressions are now resolved in the working tree** (the fixes are still uncommitted ` M` changes at final check).

### 4.5 The environment-dependent / flaky cases

- `test_quick_ask_endpoint_uses_real_runtime`: isolated runs fail **identically** on both trees (`1 failed in 34.34s` feature, `1 failed in 33.55s` main) with `TimeoutError` at `tests/test_quick_ask.py:47`/`:26`. A direct probe of `python -m keel -p hi --output-format json --provider auto --seed 0 --fake-script …` took **25.4 s** to exit 0 under the same load — right at the 30 s client ceiling. Making `PYTHONPATH` absolute did not change the result. Test files are byte-identical between branches.
- `test_run_streams_events_and_done_marker`: same failure class on both trees in the full suites; a spawned `--fake-script` child stalls under load.
- `test_w39_concurrent_approval_writes_are_lossless`: the file `tests/test_permission_contracts.py` **does not exist on main** (added on feature in `3872b22 feat(W3.x): permission contracts with authoritative first-match evaluator`). It failed once in the feature full suite under peak concurrent load (`assert 10 == 12`), but passed in **four** isolated runs (`1 passed in 2.09s`, `1.46s`, `0.98s`, `1.13s`). Classification: **flaky, newly exposed on a feature-only test**, load-sensitive; not a regression of a baseline test. The one failure does indicate a real concurrency weakness in `ApprovalStore`'s cross-instance file locking under heavy load and deserves a separate owner-tracked issue.

## 5. Classification of the seven reported failures

| # | Test | Feature at launch | Main | Classification | Current status |
|---|---|---|---|---|---|
| 1 | `test_distribution_package.py::test_release_manifest_has_policy_fields` | FAIL `FileNotFoundError` | SKIP (guard) | **introduced by feature branch** (guard reverted by `4deb532`) | **fixed** — guard restored by another agent; `1 passed, 5 skipped` |
| 2 | `test_distribution_package.py::test_checksums_file_matches_manifest_artifacts` | FAIL `FileNotFoundError` | SKIP (guard) | **introduced by feature branch** | **fixed** — guard restored |
| 3 | `test_gap_closure.py::test_c12_package_manager_manifests` | FAIL `FileNotFoundError` | SKIP (guard) | **introduced by feature branch** | **fixed** — guard restored |
| 4 | `test_gap_closure.py::test_c122_airgap_bundle_and_verification` | FAIL `FileNotFoundError` | SKIP (guard) | **introduced by feature branch** | **fixed** — guard restored |
| 5 | `test_release_integrity.py::test_integrity_cli_on_real_artifacts` | FAIL `AssertionError` (2/7) | SKIP (guard) | **introduced by feature branch** | **fixed** — guard restored |
| 6 | `test_plan_index.py::test_authoritative_source_hashes_unchanged` | FAIL hash mismatch | PASS (CRLF-normalized) | **introduced by feature branch** (normalization reverted) | **regression fixed by lead** — `2 passed` evidence in §4.4 |
| 7 | `test_quick_ask.py::test_quick_ask_endpoint_uses_real_runtime` | FAIL 30 s timeout | FAIL 30 s timeout (full suite **and** isolated) | **environment-dependent / load-sensitive, pre-existing on main** | open on both trees; quarantine or timeout fix |

Extra cases discovered during this round:

| Test | Feature at launch | Main | Classification | Current status |
|---|---|---|---|---|
| `test_gap_closure.py::test_c411_visual_diff_and_capture` | hard-coded `/tmp/a.png`, `/tmp/b.png` shared paths | `tmp_path` fixture | **introduced by feature branch** | **regression fixed by lead** — `2 passed` evidence in §4.4 |
| `test_webapp.py::test_run_streams_events_and_done_marker` | FAIL timeout | FAIL timeout | **environment-dependent, pre-existing on main** | open on both trees |
| `test_permission_contracts.py::test_w39_concurrent_approval_writes_are_lossless` | FAIL once under load | test does not exist on main | **flaky / newly exposed**, load-sensitive | passes in isolation (4/4); investigate `ApprovalStore` locking separately |

## 6. Canonical-plan compliance (read-only `PLAN-INDEX.json`)

`PLAN-INDEX.json` was read from both trees (never edited). Relevant entries are identical for IDs present on main; the feature file additionally contains later backend IDs (e.g. V27), which is generated-file work owned by the lead.

| Plan ID | Requirement (abbreviated) | Test reference | Status / criterion | Compliance finding |
|---|---|---|---|---|
| `B7.6` | Machine-readable task index `PLAN-INDEX.json` | `tests/test_plan_index.py` | `verified`; "Automated test coverage exists and passes" | Pre-fix hash case **violated** this criterion in this checkout; now passes → compliant. |
| `C12.2` | Air-gapped install/update: offline bundle, signed sideload verification | `tests/test_gap_closure.py` | `verified`; same criterion | The two failing `c12*` cases violated it while guards were absent; now restored/skipped, so the suite no longer fails, though those assertions again only run in artifact-producing CI (see below). |
| `C12.1` | Manifest fields: `min_version`, `blocked_versions`, advisories, staged rollout | `tests/test_release_hardening.py` | `verified`; same criterion | Manifest assertions in `test_distribution_package.py` are not a listed reference, but cover the same contract; the pre-fix failures were inconsistent with the plan's verification evidence. |
| `B4.1` | Global quick-ask hotkey overlay | `tests/test_quick_ask.py` | `verified`; same criterion | The failing case is in the referenced file, so the criterion is literally unmet in this environment on **both** trees; cause is environmental, not a feature-code defect. |
| `B7.5` | Flaky-test quarantine with owner and expiry | `tests/test_ci_helpers.py`; `FlakyQuarantine` at `src/keel/ci_helpers.py:10-36` (`add(test, owner, days=14)`, `is_quarantined`) | `verified`; same criterion | Neither the load-sensitive quick-ask/webapp cases nor the new `w39` case are quarantined on the feature tree → genuine shared plan gap, not attributable to the frontend workstream alone. |

`tests/test_distribution_package.py` and `tests/test_release_integrity.py` are not named in any `test_references` array in `PLAN-INDEX.json` (verified by grep/JSON query); their subject matter maps to `C12.1`/`C12.2`, feature-only V27 (`Release publish verifier`) and C11.6 (`Verified official build`). Their failures were caused by missing generated artifacts, not by an implementation defect in the plan's features.

**Caveat on skipping vs plan compliance:** restoring the guards returns parity with main and makes the suite green in a source checkout, but the affected assertions again only execute where release artifacts are generated (CI packaging job). A stronger, non-minimal compliance improvement is to generate `keel/release/RELEASE-MANIFEST.json`, `RELEASE-SHA256SUMS.txt`, `latest.yml` and the dist/sidecar artifacts before the Python suite so those tests genuinely pass instead of skipping.

## 7. Minimal fixes (applied by lead/other agents, not by this agent)

The restorations now present in the shared worktree, and which produced `1 passed, 5 skipped`:

1. `keel/tests/test_distribution_package.py` — `import pytest` plus `_require_release_artifacts()` helper, called at the start of both release tests.
2. `keel/tests/test_gap_closure.py` — `import pytest` plus the `RELEASE-MANIFEST.json` existence guard in `test_c12_package_manager_manifests` and `test_c122_airgap_bundle_and_verification`; `tmp_path` fixture in `test_c411_visual_diff_and_capture`.
3. `keel/tests/test_release_integrity.py` — `import pytest` plus the manifest/sidecar guard in `test_integrity_cli_on_real_artifacts`.
4. `keel/tests/test_plan_index.py` — CRLF-normalized hashing: `(DOWNLOADS / name).read_bytes().replace(b"\r\n", b"\n")`.

Remaining recommended actions (none applied by this agent):

5. Per `B7.5`, quarantine or fix the environment-dependent quick-ask/webapp HTTP timeout cases with an owner and expiry, or make spawned children deterministic (absolute `PYTHONPATH`, avoid the global editable install shadowing, raise the 30 s client ceiling toward the child's 120 s timeout). Applies to **both** trees.
6. Open a separate owner-tracked issue for `ApprovalStore` losing 2/12 concurrent writes under heavy load (`tests/test_permission_contracts.py:504-526`); the `w39` test is feature-only, so this is newly exposed, not a baseline regression.

## 8. Recommended actions / bottom line

1. **All six original deterministic failures are resolved in the current working tree** (`1 passed, 5 skipped`), with the hash case and `c411` specifically verified as **"regression fixed by lead"** (`2 passed`).
2. Rows 1-6 were feature-branch regressions caused by `4deb532` reverting `16977a3`'s Windows fixes; main `ecba9d2` never had them. The fixes are **uncommitted** at final check and should be committed by the owning agents.
3. Row 7 is environment-dependent and pre-existing on main; do not attribute it to the frontend workstream. The same applies to the new `test_run_streams_events_and_done_marker` timeout.
4. `test_w39_concurrent_approval_writes_are_lossless` is a flaky feature-only test that passed 4/4 in isolation; investigate the underlying locking defect separately rather than counting it as a baseline regression.
5. Full-suite baselines for the record: main `2 failed, 1289 passed, 37 skipped in 750.05s`; feature (pre-edit code) `9 failed, 4020 passed, 48 skipped, 3621 subtests passed in 991.91s`. Re-run the full suite after the restorations are committed and concurrent agent load subsides to obtain a clean post-fix count.
6. No test was weakened by this agent; no source file, generated plan file, or git state was changed by this agent.
