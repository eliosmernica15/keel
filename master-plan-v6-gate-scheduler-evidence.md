# Gate scheduler, strict linker, CI layout and benchmark method — implementation evidence (D7.x P0 assignment)

**Branch:** `agent/a9-d7` · **Baseline:** `f2c0fe6`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a9-d7`

## Scope and registry note

The assignment was to implement the `not_started` **P0** rows `D7.1`, `D7.9`,
`D7.12` and `D7.19` in `PLAN-INDEX.json` as stdlib-only pure contracts. Reading
the registry at the assigned baseline found exactly four such rows. Their full
text is reproduced here for traceability:

| ID | Full registry feature text | Detail | Milestone | Status |
| --- | --- | --- | --- | --- |
| D7.1 | Gate scheduler (`run-gates`): all gates as a dependency graph; bounded concurrency env var; fail-fast switch; a failure skips only its dependents so independent errors all report. | `scripts/run_gates.py` with `KEEL_GATE_CONCURRENCY`, `KEEL_GATE_FAIL_FAST`. | M0 | `not_started` / P0 |
| D7.9 | Strict dependency linker so undeclared deps fail; build scripts of dependencies explicitly allowlisted. | `pip-compile`/lockfile with hash pinning; Electron side uses a strict package manager config with an allowlist of postinstall scripts. | M0 | `not_started` / P0 |
| D7.12 | CI layout: broad lanes of independent gates, a smaller Node-version compatibility matrix, native Windows lane in a separate workflow, Python checks separate, required benchmarks on standard hosted Linux, real-API e2e in its own workflow, partitioned coverage using per-platform timing data. | CI lanes: gates, matrix (Python 3.11/3.12/3.13), Windows, macOS, benchmarks, provider-e2e (opt-in, self-skips without key). | M0 | `not_started` / P0 |
| D7.19 | Benchmark method: drive tasks through the SDK's minimal JSON-RPC agent variant with separate workspaces and session ids per independent task. | Keel benchmark runner uses the `sdk-minimal` profile and isolated workspaces (C13.1). | M21 | `not_started` / P0 |

All four rows are section 8 ("Dev workflow, build, CI and release") of
`Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md`; D7.19 references
C13.1. The explicit deliverable specification — a **stdlib-only, pure** gate
dependency graph with bounded-concurrency simulation, a strict dependency
linker, a CI lane layout descriptor and a benchmark method descriptor — is
unambiguous, so this change implements that specification as the host-side
contract layer a future `scripts/run_gates.py`, CI workflows and benchmark
runner would consume. `PLAN-INDEX.json` and every other existing file were
**not** edited; no row status was changed here. This evidence does not claim
that a real process scheduler, workflow files, a lockfile or an SDK runner were
shipped end-to-end.

## Files owned (only these were added)

* NEW `keel/src/keel/gate_scheduler.py`
* NEW `keel/tests/test_gate_scheduler.py`
* NEW `master-plan-v6-gate-scheduler-evidence.md` (this file)

## Requirement → implementation map

| Requirement | Contract surface in `keel.gate_scheduler` |
| --- | --- |
| D7.1 — all gates as a dependency graph | `GateSpec`, `make_gate`, `GateGraph`, `build_gate_graph`, `validate_gate_graph`, `find_cycle`, `topological_levels`, `transitive_dependents`: immutable, sorted, deterministic; rejects duplicate ids, unsafe ids, self/unknown dependencies and every cycle (including forged self-loops) |
| D7.1 — bounded concurrency env var | `CONCURRENCY_ENV = KEEL_GATE_CONCURRENCY`, `DEFAULT_CONCURRENCY = 4`, `MAX_CONCURRENCY = 64`, `SchedulerPolicy`, `parse_scheduler_env`, `_validate_policy`: parses only a caller-supplied mapping (never reads `os.environ`), rejects malformed/out-of-range values and unknown `KEEL_GATE_*` keys; `simulate_gates` never starts more than `concurrency` gates per round (`GateRun.max_in_flight`) |
| D7.1 — fail-fast switch | `FAIL_FAST_ENV = KEEL_GATE_FAIL_FAST` (strict boolean parsing: `1/0`, `true/false`, `yes/no`, `on/off`), `SchedulerPolicy.fail_fast`; on a failure, gates not yet started become `cancelled` while gates started in the same round keep their result |
| D7.1 — failure skips only dependents, all independent errors report | `simulate_gates` uses `propagate()` and the reverse graph: a failed gate marks only its transitive dependents `skipped`; all other runnable gates still execute, so independent failures are all recorded. `GateResult`/`GateRun` expose `passed`/`failed`/`skipped`/`cancelled` with written reasons |
| D7.9 — undeclared deps fail | `DependencyManifest.required` vs `LockEntry.package`, `undeclared_dependencies`, `validate_manifest`, `link_dependencies`: any required package missing from the lockfile fails the whole link; duplicates in either list fail too |
| D7.9 — hash pinning | `LockEntry(package, version, digest, scripts, ecosystem)`, `make_lock_entry`, `link_dependencies`, `lockfile_digest`: exact versions only (no `latest`, `*`, `^`, `~`, ranges), lowercase `sha256:`/64-hex or `sha512:`/128-hex digests only, python entries are pinned wheels without build scripts; canonical sha256 of the sorted lockfile |
| D7.9 — allowlisted dependency build scripts | `allowed_scripts` in `make_manifest`, exact `package:script` format, `is_script_allowed`, `strict_scripts`: no wildcards, no global script names, no implicit permission; an unapproved or forged script fails closed at construction *and* at the linker boundary |
| D7.12 — CI lane layout | `LaneKind`, `CILane`, `make_ci_lane`, `CI_LANES` (six lanes), `validate_ci_layout`, `ci_layout_dict`: broad gates lane, small Python matrix (`PYTHON_VERSIONS = 3.11/3.12/3.13`), separate native `windows-`/`macos-` workflows, hosted-Linux required benchmarks, and provider e2e in its own workflow |
| D7.12 — provider e2e opt-in/self-skip | `lane_enabled(lane, context)`: provider e2e requires *both* `opt_in is True` and `api_key_present is True`; a missing, string-typed or absent key self-skips. `key_ref` must be a secret reference (`env:`/`keyring:`/`secret:`/`file:`), never a literal key |
| D7.12 — partitioned coverage by per-platform timing | `PLATFORMS`, `CoveragePlan`, `partition_coverage`: largest-first, lightest-bin placement of shards with deterministic tie-breaks; rejects unknown platforms, bool/non-finite/zero/negative timings, unsafe shard ids and out-of-range partition counts |
| D7.19 — SDK minimal JSON-RPC method | `SDK_MINIMAL_PROFILE = "sdk-minimal"`, `JSONRPC_TRANSPORT = "json-rpc"`, `BenchmarkMethod`, `make_benchmark_method`, `validate_benchmark_method`: any other profile or transport is rejected |
| D7.19 — isolated workspaces and session ids | `BenchmarkTask`, `make_benchmark_task`, `_is_task_workspace`, `benchmark_dispatch`, `method_digest`, `is_isolated`: workspace must be exactly `workspaces/<task_id>` (no traversal, absolute/drive/UNC/encoded segments); task ids, workspaces and session ids must be unique and non-nested; dispatch is a pure plan sorted by task id |
| No host state / stdlib only | imports limited to `__future__`, `dataclasses`, `enum`, `hashlib`, `json`, `math`, `re`, `typing`; no process, file, network, clock, chance or environment reads. Two AST tests enforce this on the source itself |

## Verification

Both commands were run from the worktree root with the required `sys.path`
insert.

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_gate_scheduler.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
```

Result: **77 tests passed in 0.077 s** (stdlib-only runner).

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_gate_scheduler.py']))"
```

Result: **77 passed, 698 subtests passed in 1.44 s** (pytest 9.0.2).

Full-suite regression run:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests']))"
```

Result: **did not finish within the 5-minute foreground window** (the run was
moved to the background and left there; it exercises 269 pre-existing test
files, some of which start local servers and take minutes). No failure output
was produced before that point. A fast related-regression subset covering CI,
signing gates, composition, responsible use and this new suite:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_ci_helpers.py','keel/tests/test_signing_gate.py','keel/tests/test_composition_contracts.py','keel/tests/test_responsible_use.py','keel/tests/test_gate_scheduler.py']))"
```

Result: **166 passed, 1689 subtests passed in 3.44 s**. The change is purely
additive (three untracked new files, no existing file edited), so it cannot
alter the behaviour of the other suites.

## Adversarial coverage (all green)

* **Graph integrity** — duplicate gate ids, unsafe identifiers, self- and
  duplicate dependencies, unknown prerequisites and two-node/three-node/self
  cycles are all rejected; cycle detection is deterministic; topological levels
  and graph serialization are byte-identical under reversed input order;
  transitive dependents are computed from the reverse graph.
* **Scheduler policy** — `KEEL_GATE_CONCURRENCY` rejects empty/zero/negative/
  decimal/exponent/whitespace/injected/boolean/oversized values; an unknown
  `KEEL_GATE_*` key is rejected rather than ignored; fail-fast accepts only
  strict boolean flags.
* **Simulation** — bounded concurrency verified for 1/2/3/7 slots over 10
  gates; a failing gate skips only its dependents (verified transitively)
  while independent gates still fail independently; fail-fast keeps in-flight
  results and cancels only unstarted gates (dependents remain `skipped`, not
  `cancelled`); unknown, missing and non-boolean outcomes fail closed; empty
  graphs and forged invalid policies are handled without host effects.
* **Linker** — undeclared imports, floating versions, missing/malformed/
  uppercase digests, duplicate pins, unsafe package names, unknown ecosystems,
  python build scripts and unapproved/forged/wildcard script entries are all
  rejected; a valid scoped Node package with an exact allowlisted postinstall
  passes; the lockfile digest is deterministic and order independent.
* **CI layout** — every lane kind must appear exactly once; literal API keys
  in `key_ref` are rejected; Windows/macOS/benchmark/e2e must use workflows
  distinct from the gates lane; provider e2e requires both opt-in and a proven
  key; coverage partitioning rejects NaN, infinity, zero, negative, boolean
  and string timings, unsafe shard ids, unknown platforms and out-of-range
  partition counts.
* **Benchmark method** — non-`sdk-minimal` profiles, non-`json-rpc` transports,
  empty task sets, duplicate task ids, shared workspaces, reused session ids,
  traversal (`../`, encoded `%2e%2e`, absolute, drive-letter, nested) and
  mismatched `workspace != workspaces/<task_id>` are rejected; a forged method
  with duplicate tasks fails validation and dispatch; the method digest changes
  when a session id changes.
* **Purity** — AST tests assert the module imports only the permitted stdlib
  set and contains no `open`/`system`/`popen`/`spawn`/`fork`/`exec`/`sleep`/
  `random`/network calls and no process/filesystem/clock modules.

## TDD evidence

`test_gate_scheduler.py` was written first and run before the module existed;
collection failed with
`ModuleNotFoundError: No module named 'keel.gate_scheduler'`. After the module
was added the suite exposed one real implementation defect and three test-harness
mistakes:

1. **Real defect:** skipped and cancelled gates were tracked internally but
   never emitted as `GateResult` rows, so callers could not see why a gate did
   not run. Fixed by emitting `skipped` (`reason="dependency failed"`) and
   `cancelled` (`reason="fail-fast: cancelled before start"`) results — not by
   weakening the assertions.
2. The CI workflow test keyed its map by workflow file name but looked up the
   gates lane by lane id — corrected to key by lane id.
3. The duplicate-lane test expected `validate_ci_layout` to raise, but that
   validator consistently returns an error tuple (the `ci_layout_dict` builder
   raises) — corrected to assert both behaviours.
4. The python-scripts test expected the error at manifest construction, while
   the stricter contract rejects at `make_lock_entry`; corrected to assert both
   the construction-time rejection and the forged-entry linker-time rejection.

Final result: 77/77 tests pass under both runners.
