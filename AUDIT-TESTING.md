# Independent Audit — Test Quality & Regression Integrity

**Scope:** `keel/tests/test_*backend.py` (20 files) + `keel/tests/test_backend_hub_integration.py`, plus full-suite order/pollution checks and skip inventory.
**Branch:** `agent/audit-testing` (worktree `C:\Users\Admin\.local\share\opencode\worktree\audit9\testing`).
**Environment:** Windows (win32), Python 3.11.9, pytest 9.0.2 (+ subtests plugin). All commands run from `...\testing\keel` unless stated.
**Constraint honoured:** no production source was edited. Mutations were done in a temp copy under `C:\Users\Admin\AppData\Local\Temp\opencode\audit_mut`.

---

## 1. Confirmed weak / fake tests (reported first)

### FINDING W-1 — MEDIUM — Descriptor-only "coverage" tests would pass with a no-op implementation

These tests assert that an ID/symbol/registry entry exists, or that an ID string appears in source text, but never execute the feature's behaviour. They are **coverage guards mislabelled as tests**: a stub that returns a constant for every feature would leave them green.

| File:line | Test | What it actually checks |
|---|---|---|
| `test_w7_x1_y5_d1_backend.py:561` | `test_all_31_not_started_feature_ids_are_covered` | 31 hard-coded IDs appear as substrings in `m.__file__` and in the test file itself. `assert feature_id in source` — a docstring mention suffices. |
| `test_small_groups_backend.py:886` | `test_registry_covers_every_implemented_non_gated_feature` | Counts IDs by prefix and `all(callable(value) ...)`; none of the 54 implementations is invoked. |
| `test_e6_x5_x6_backend.py:888` | `test_already_implemented_p0_symbols_still_import` | 12 × `hasattr(...)` only. |
| `test_y2_backend.py:41` | `test_all_fifteen_feature_ids_have_backend_symbols` | 15 × `hasattr(y, symbol)` only. |
| `test_y3_backend.py:590` | `test_p0_y3_rows_verified_in_config_contracts` | `hasattr(cc, symbol)` loop (`:611`). |
| `test_w4_backend.py:40` | `test_manifest_covers_exactly_the_13_not_started_rows` | ID tuple equality + `hasattr(w, symbol)` (`:50`). |
| `test_d7_workflow_backend.py:86`, `:94`, `:98`, `:108` | `test_all_sixteen_feature_ids_declared`, `test_p0_rows_not_duplicated`, `test_p0_contracts_present_in_gate_scheduler`, `test_public_api_exports_exist` | ID sets, `hasattr(gs, name)` (`:106`), `hasattr(d, name)` (`:111`). |
| `test_e3_backend.py:103` | `test_all_thirteen_ids_and_two_p0_ids` | ID/constant equality only. (`:109` at least calls `verify_p0_contracts()`.) |
| `test_v_series_backend.py:30`, `:39` | `test_feature_ids_exact`, `test_p0_baseline_documents_exactly_seven_rows` | Constant tuples only. |
| `test_x2_orchestration_backend.py:673` | `test_all_feature_ids_are_covered` | `assert FEATURE_IDS == tuple(f"X2.{i}" for i in range(1, 17))`. |
| `test_y4_d4_x7_backend.py:26`, `:30` | `test_all_31_ids_mapped_and_resolvable`, `test_prior_p0_verified_rows_documented` | `len()` + `verify_coverage()` + constant set. |
| `test_z_backend.py:31` | `test_all_fifteen_assigned_rows_are_covered` | Constant tuple equality only. |
| `test_d3_backend.py:34`, `:47` | `test_all_backend_descriptors_are_honest_and_complete`, `test_verified_p0_references_point_at_real_capability_seams_symbols` | Descriptor fields + `is_file()` + `hasattr(cs, symbol)` (`:55`); no feature executed. |
| `test_e7_runtime_backend.py:1060` | `test_exactly_the_36_open_rows_are_indexed` | `assert_feature_index_complete()` + descriptor counts; no feature executed. |
| `test_backend_hub_integration.py:23`, `:107`, `:91` | `test_capabilities_registered_on_real_hub`, `test_feature_index_covers_all_integrated_ids`, `test_verify_confirms_all_modules_import_and_declare_features` | IDs, counts, import/feature declarations only. |

**Proof (mutation, temp copy — see §5):** after mutating `derive_install_id` to a constant, all five descriptor tests
(`test_d3_backend.py::test_all_backend_descriptors_are_honest_and_complete`,
`test_d3_backend.py::test_feature_ids_are_exactly_the_p1_and_p2_d3_rows`,
`test_y2_backend.py::test_all_fifteen_feature_ids_have_backend_symbols`,
`test_small_groups_backend.py::test_registry_covers_every_implemented_non_gated_feature`,
`test_x2_orchestration_backend.py::test_all_feature_ids_are_covered`) **still passed**.

### FINDING W-2 — MEDIUM — 36 weak assertion instances (existence-only / non-None / self-comparison)

Mechanical AST scan of the 21 target files (`audit_weakcount.py`, temp) found **36** instances:

| Category | Count | Examples (file:line) |
|---|---|---|
| `hasattr(...)` | 9 | `test_d3_backend.py:55`, `test_d7_workflow_backend.py:106,111`, `test_e6_x5_x6_backend.py:897,900,903`, `test_w4_backend.py:50`, `test_y2_backend.py:45`, `test_y3_backend.py:611` |
| `callable(...)` | 1 | `test_small_groups_backend.py:907` `assert all(callable(value) for value in FEATURE_IMPLEMENTATIONS.values())` |
| `is not None` / `assertIsNotNone` | 6 (+2 in compound assertions) | `test_e3_backend.py:418,490`, `test_e7_runtime_backend.py:325,695`, `test_v_series_backend.py:368`, `test_w1_security_backend.py:467`, plus `test_e6_x5_x6_backend.py:387`, `test_y3_backend.py:39` |
| Bare truthy existence | 8 | `test_d3_backend.py:44` `row['contract']`; `test_e6_x5_x6_backend.py:789` `schema.schema['required']`, `:790` `schema.changelog`; `test_w1_security_backend.py:216`; `test_w7_x1_y5_d1_backend.py:542-544`; `test_x3_memory_backend.py:195`; `test_backend_hub_integration.py:42` `fns` |
| Self-comparison / tautology | 12 | `test_x8_backend.py:102` `document['fingerprint'] == document['fingerprint']` (strict tautology); `:38,547,551,554-560` (two fresh calls — determinism, weaker than an expected value); `test_d6_reliability_backend.py:666,668`; `test_y2_backend.py:622` |

Most are embedded in otherwise substantive tests, so they are **weak assertions rather than wholly fake tests**. The `hasattr`-only loops (W-1) are the ones that provide zero behavioural evidence.

### FINDING W-3 — MEDIUM — Integration dispatch test would pass if the hub were a no-op

`test_backend_hub_integration.py:37` `test_dispatch_exercises_every_module_through_real_capability_surface`:
for each of 20 modules it calls `backend.invoke` with **no arguments** and accepts either `ok is True` **or** a `CapabilityError` containing "missing"/"bad arguments" (`:51-56`) as proof. A no-op `backend.invoke` returning `{"ok": True, "result": None}` for every request satisfies all 20 iterations. The file's only genuinely value-based test is `test_real_pure_function_returns_genuine_value_via_hub` (`:62`), which pins `fingerprint()`. 4 of 8 tests in this file are descriptor-only/permissive (`:23`, `:37`, `:91`, `:107`).

### FINDING W-4 — LOW — Static/source-shape tests are counted as behavioural coverage

~12 tests parse or grep production source instead of calling it: `test_d7_workflow_backend.py:113,126`, `test_d6_reliability_backend.py:650`, `test_e6_x5_x6_backend.py:868`, `test_e7_runtime_backend.py:1069`, `test_e3_backend.py:725`, `test_v_series_backend.py:63,75`, `test_z_backend.py:39`, `test_x8_backend.py:565`, `test_w7_x1_y5_d1_backend.py:570`, `test_small_groups_backend.py:261,741`. These are legitimate purity policy guards, but they detect imports/calls by AST, not behaviour; they cannot catch a logic regression.

### FINDING W-5 — LOW — Strict tautologies

`test_x8_backend.py:102` compares a value to itself; `test_d6_reliability_backend.py:666,668` call a pure function twice with identical input. These detect nondeterminism/randomness only; they would pass if the function were replaced by a constant. No expected digest/value is asserted.

### FINDING W-6 — INFO — No overly permissive mocks found

Across all 21 files there are only two `monkeypatch` uses (`test_e5_backend.py:613` replaces `linux_release_targets` with a deliberately *bad* descriptor to test rejection; `test_small_groups_backend.py:849-850` sets `HOME`/`USERPROFILE`) and one `MockHost` (`test_e6_x5_x6_backend.py:707`) which is a **production-provided** helper imported from `keel.e6_x5_x6_backend` (`:51`), not a local stub. No `MagicMock`, `unittest.mock.patch`, or blanket fake module substitution was found. Mocks do not mask real failures. One shared fixture deserves a note: `tests/conftest.py:18-25` autouse-patches `turn_core.settings_store.load` to `{}` for **every** test, so no test ever loads the user's real MCP settings; MCP tests opt back in explicitly. None of the 21 audited files depends on that loader, so it does not weaken their results.

---

## 2. Do the tests exercise production code? (5 classes sampled deeply)

**Verdict: yes, overwhelmingly.** The 21 files contain ~1,014 test functions (1,066 collected cases including parametrization) and ~3,604 assertions. Every sampled class imports the real module (`from keel import <module>`), constructs real objects, and asserts concrete values/exceptions. No duplicated algorithm or trivial reimplementation was found in the samples. Exceptions are the descriptor guards in W-1/W-4.

| Sampled class | File:line | Assessment |
|---|---|---|
| `TestD72WorkerBudgets` | `test_d7_workflow_backend.py:159` | Real `d.parse_cgroup_cpu_quota` / `v1` calls with concrete quotas (`2.5`, `0.5`), malformed-input `raises`, subtests. Genuine. |
| `TestRegistryAndPurity` | `test_d7_workflow_backend.py:85` | Mixed: `:113,126` source AST guards (W-4), `:98,108` `hasattr` (W-1); `:149-152` calls `d.make_build_stage` and asserts a `ValueError`. Only ~40% behavioural. |
| `TestE32Delivery` | `test_e3_backend.py:194` | Real `SubagentManager.start/settle`; asserts delivery flags, message identity, secret redaction, double-settle error, caller-only outcome. Genuine. |
| `E71_TokenMeter` | `test_e7_runtime_backend.py:27` | Real `TokenMeter.fold/replay/latest/pressure_measurement`; exact revision/token assertions, frozen-dataclass and validation errors. Genuine. |
| `TestV3ApprovalBroadness` + `TestZ5CapabilityHandshake` | `test_v_series_backend.py:116`, `test_z_backend.py:267` | Real `score_approval`/`approval_review` and `parse_client_capabilities`/`negotiate`/`prompt_payload`; exact values, failure cases, JSON serialisation. Genuine. |

---

## 3. Hidden test pollution / order dependence

Commands (PowerShell, from `...\testing\keel`):

```powershell
$files = (Get-ChildItem tests -Filter 'test_*backend.py' | ForEach-Object { "tests/$($_.Name)" }) + @('tests/test_backend_hub_integration.py')
python -m pytest -q -rs $files                                    # natural order
python -m pytest -q -rs ($files | Sort-Object -Descending)        # reverse order
python -m pytest -q -rs > $env:TEMP\audit_order1.txt              # full suite, default order
$all = (Get-ChildItem tests -Filter 'test_*.py' -Recurse | Sort-Object FullName -Descending | ForEach-Object { $_.FullName.Replace((Get-Location).Path + '\','').Replace('\','/') })
python -m pytest -q -rs $all > $env:TEMP\audit_order2.txt         # full suite, reversed file list
```

Results:

| Run | Result |
|---|---|
| 21 target files, natural order | **1066 passed, 1119 subtests passed** (39.39s) |
| 21 target files, reversed order | **1066 passed, 1119 subtests passed** (52.89s) |
| Full suite, default order | **9 failed, 4017 passed, 51 skipped, 3621 subtests passed** (912.61s) |
| Full suite, reversed file order | **14 failed, 4014 passed, 49 skipped, 3621 subtests passed** (1062.66s) |
| 21 target files, forced `PYTHONPATH` to this worktree's `src`, keys unset | **1066 passed, 1119 subtests passed** (35.31s) |

**old `sys.modules` pollution fix — still holds.** `test_offline_runtime.py:84-102` snapshots every `keel*` module, evicts them, re-imports, then restores the originals in `finally`. Focused bidirectional check:

```powershell
python -m pytest -q tests/test_offline_runtime.py tests/test_tool_registry.py tests/test_read_only.py
python -m pytest -q tests/test_read_only.py tests/test_tool_registry.py tests/test_offline_runtime.py
```
Both: **26 passed** — no class-identity/pollution regression. Note a minor residual: `sys.path.insert(0, str(SRC))` (`:28,:37,:75`) is never undone, so duplicate `SRC` entries accumulate; harmless for identity but untidy.

The 9 full-suite failures in the first run are **not order-dependent**: running just those 9 node IDs in isolation reproduced **9 failed** (76.42s). They are pre-existing environment/state issues (missing `release/` artifacts, drifted authoritative hash, one concurrency test, two webapp socket timeouts), not caused by target-file ordering.

**Why the reversed full-suite run looked worse (14 vs 9 failures) — environmental, not ordering:** the second background shell had `KEEL_GOOGLE_API_KEY` present in its ambient environment, so the two `test_live_smoke.py[google-...]` cases ran instead of skipping (hence 49 rather than 51 skips) and one hit the network with an invalid key. Reproduced deterministically with a controlled subset:

```powershell
$env:PYTHONPATH='C:\Users\Admin\.local\share\opencode\worktree\audit9\testing\keel\src'
# (a) all KEEL_*_API_KEY removed:
python -m pytest -q <6 new-failure node IDs> tests/test_live_smoke.py
#   6 passed, 10 skipped in 73.78s
# (b) same command with $env:KEEL_GOOGLE_API_KEY='invalid-key-for-audit':
#   6 failed, 2 passed, 8 skipped in 89.72s
```

Failing under (b): `test_permission_denial_is_real`, `test_no_credentials_means_no_live_success`, both `test_routing_*`, `test_custom_command_runs_through_loop`, and `test_live_provider_smoke[google-...]` — i.e. the same new failures seen in the reversed full-suite run. In isolation, with keys unset, all six pass (`6 passed in 60.42s`). **Conclusion: no hidden order dependence was found; the delta is ambient credentials plus a flaky webapp timeout.**

**Import-resolution caveat:** an editable install makes `import keel` resolve to `C:\Users\Admin\Desktop\Claude clone\keel\src` (the main worktree), not this worktree's `src`, unless `PYTHONPATH` is set explicitly. Eight of the 20 backend modules currently differ between the two worktrees (`e5_backend.py`, `e6_x5_x6_backend.py`, `w4_backend.py`, `w7_x1_y5_d1_backend.py`, `x3_memory_backend.py`, `y1_config_backend.py`, `y2_backend.py`, `z_backend.py`). I therefore repeated the 21-file target run with `PYTHONPATH` forced to this worktree's `src`: identical **1066 passed / 1119 subtests**. Static findings (§1–§2) were read from this worktree's test sources. No source file was modified in either worktree.

---

## 4. Descriptor-only validation — summary

Count of tests whose *only* evidence is an ID count, registry membership, `hasattr`/`callable`, or source substring: **~20** in the target files (enumerated in W-1). These are the tests most likely to be cited as "feature covered" while providing no regression protection for the feature body.

---

## 5. False-positive check — mutation in a temp copy

Procedure (no source edit):

```powershell
$mut = "$env:TEMP\opencode\audit_mut"
Copy-Item -Recurse src\keel "$mut\keel"
# replace in $mut\keel\d3_backend.py:
#   return "local-" + hashlib.sha256(raw).hexdigest()[:24]
# with:
#   return "local-MUTATED"
python -m pytest -q tests/test_d3_backend.py            # baseline (clean shell): 37 passed
$env:PYTHONPATH = $mut
python -c "import keel.d3_backend as d; print(d.__file__); print(d.derive_install_id('machine-secret'))"
# -> ...\audit_mut\keel\d3_backend.py / local-MUTATED
python -m pytest -q tests/test_d3_backend.py            # with PYTHONPATH=mut: 1 failed, 36 passed
python -m pytest -q tests/test_d3_backend.py::test_all_backend_descriptors_are_honest_and_complete `
  tests/test_d3_backend.py::test_feature_ids_are_exactly_the_p1_and_p2_d3_rows `
  tests/test_y2_backend.py::test_all_fifteen_feature_ids_have_backend_symbols `
  tests/test_small_groups_backend.py::test_registry_covers_every_implemented_non_gated_feature `
  tests/test_x2_orchestration_backend.py::test_all_feature_ids_are_covered   # 5 passed
```

Mutation: `d3_backend.derive_install_id` ignores its seed and returns a constant.
Detected by `test_install_identity_is_local_deterministic_and_never_transmitted` at `test_d3_backend.py:373` (`assert db.identity_from_seed("other").install_id != first.install_id`).
**Conclusion:** the behavioural test is real (not a no-op pass), while the five descriptor-only tests are confirmed blind to the same mutation.

---

## 6. Skip integrity — all 48 skip sites (51 skipped test instances)

The default-order full-suite `-rs` output (run 1, no API keys) contains **48 `SKIPPED` lines** (one line can cover multiple tests: `test_os_sandbox.py:38` covers 4) representing **51 skipped test instances**. Verdict: by *lines*, 46/48 are genuinely external/platform-gated and 2 are questionable; by *instances*, 46/51 are genuine and 5 are host-launch failures that convert a potentially real defect into a skip (see below). Run 2 had 46 lines / 49 instances solely because the two Google live-smoke cases ran with an ambient key (§3).

| File:line | Count | Reason (short) | Genuine gate? |
|---|---|---|---|
| `test_desktop_artifacts.py:22` | 1 | desktop app not built locally | Yes — build artifact absent |
| `test_desktop_artifacts.py:34` | 1 | sidecar not built locally | Yes — build artifact absent |
| `test_desktop_artifacts.py:44` | 1 | no dist directory | Yes — build artifact absent |
| `test_live_smoke.py:37` | 5 | no `KEEL_{OPENROUTER,GOOGLE,NVIDIA,COMPAT,ANTHROPIC}_API_KEY` | Yes — real credentials/cost/network |
| `test_live_smoke.py:63` | 5 | same 5 keys (bad-key variant) | Yes |
| `test_model_dialects.py:370` | 1 | symlinks unavailable on this platform | Yes — `OSError` from `symlink_to` |
| `test_os_sandbox.py:38` | 4 | `BLOCKED: sandbox could not launch this executable (exit=3221225781)` | **Questionable** — see below |
| `test_os_sandbox.py:85` | 1 | network enforcement needs Linux Landlock/seccomp or macOS profile | Yes — platform capability |
| `test_sandbox_linux.py:50,66,75,89,131,145,157,168,197,226,252,276,286,295,311,330` | 16 | native Landlock/seccomp confinement is Linux-only | Yes — module `skipif(not linux)` |
| `test_sandbox_macos.py:57,73,118,124,135,147,158,167,176,193,220,228,240,254` | 14 | native macOS Seatbelt tests require `sandbox-exec` | Yes — module `skipif(sys.platform != "darwin")` |
| `test_sandbox_windows.py:281` | 1 | Python interpreter cannot start under restricted token (exit=3221225506) | **Questionable** — see below |
| `test_security_contracts.py:614` | 1 | symlink creation not permitted on this host | Yes — `OSError` from `os.symlink` |

Total: 3 + 5 + 5 + 1 + 4 + 1 + 16 + 14 + 1 + 1 = **51 skipped instances across 48 lines**.

Other skip markers that did **not** fire on this host and were verified as genuine gates: `test_desktop_hardening.py:155` (`skipif(sys.platform != "win32")`), `test_win_network.py:25` (`skipif(not WINDOWS)`), `test_os_sandbox.py:80` (Windows ACL backend branch), `test_os_sandbox.py:43` (`SandboxUnavailable`), `test_sandbox_macos.py:53` (host read isolation).

**Questionable skips (LOW–MEDIUM):** `test_os_sandbox.py:18-43` turns any failed confined launch into `pytest.skip`. On this host that silently skips `test_workspace_read_and_outside_denied`, `test_secret_environment_not_inherited`, `test_process_tree_termination`, and `test_concurrent_confinement` — four tests that should assert real enforcement. The failure exit `3221225781` (0xC0000135, DLL not found) is a host/setup problem, but it is indistinguishable from a regression in `run_confined` itself. The same pattern at `test_sandbox_windows.py:279-284` skips the Python-under-restricted-token test. Both files argue that the boundary is proven elsewhere by cmd.exe tests; those cmd.exe tests do pass on this host, so the gap is narrow, but the skips should be tracked (`xfail(strict=True)` with an issue link) rather than unbounded.

---

## 7. Pre-existing full-suite failures (unrelated to the audited test files)

All 9 reproduce in isolation; none are order-dependent:

```
python -m pytest -q \
  tests/test_distribution_package.py::test_release_manifest_has_policy_fields \
  tests/test_distribution_package.py::test_checksums_file_matches_manifest_artifacts \
  tests/test_gap_closure.py::test_c12_package_manager_manifests \
  tests/test_gap_closure.py::test_c122_airgap_bundle_and_verification \
  tests/test_permission_contracts.py::test_w39_concurrent_approval_writes_are_lossless \
  tests/test_plan_index.py::test_authoritative_source_hashes_unchanged \
  tests/test_quick_ask.py::test_quick_ask_endpoint_uses_real_runtime \
  tests/test_release_integrity.py::test_integrity_cli_on_real_artifacts \
  tests/test_webapp.py::test_run_streams_events_and_done_marker
# 9 failed in 76.42s
```

Causes: missing `keel/release/RELEASE-MANIFEST.json`, `RELEASE-SHA256SUMS.txt`, `latest.yml`, sidecar dist; `Keel_Master_Plan_v5.md` hash no longer matches the recorded prefix; `ApprovalStoreError('failed to persist approvals')`; two HTTP server read timeouts. Out of scope for this audit (no source edits permitted).

---

## 8. Full-suite order comparison (final)

| Run | Command (from `...\testing\keel`) | Result |
|---|---|---|
| 1 — default order | `python -m pytest -q -rs` | 9 failed, 4017 passed, 51 skipped, 3621 subtests (912.61s) |
| 2 — reversed file list | `python -m pytest -q -rs $all` (`$all` = 297 files sorted descending) | 14 failed, 4014 passed, 49 skipped, 3621 subtests (1062.66s) |

The 5 extra failures and 2 fewer skips are explained by the ambient `KEEL_GOOGLE_API_KEY` present in run 2 (see §3 proof), **not** by file ordering. The 9 baseline failures all reproduce in isolation. `test_offline_runtime.py`'s `sys.modules` fix holds in both orders (§3). No evidence of genuine hidden test pollution in the audited target files.

---

## 9. Recommendations (priority order)

1. Convert W-1 descriptor guards into real smoke tests: call one representative behaviour per ID and assert an expected value; or rename/mark them `test_*_manifest_guard` so coverage claims are honest.
2. Replace `hasattr`/`callable` loops with an import plus a minimal invocation and value assertion (e.g. `describe()` payload).
3. Tighten `test_backend_hub_integration.py:37`: pass concrete params and assert a concrete result; do not treat `ok is True` with no value check as proof.
4. Replace source-substring checks (`test_w7_x1_y5_d1_backend.py:561`) with behavioural checks; keep the ID set comparison separately as a guard.
5. Track the 5 launch-failure skips with `xfail(strict=True)`/issue links, or fix the host launcher so the assertions run.
6. Address the 9 pre-existing failures in a separate change (release artifacts, hash baseline, concurrency store, webapp timeouts).
