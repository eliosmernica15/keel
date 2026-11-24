# D7 dev-workflow backend — implementation evidence (all 16 `not_started` P1/P2 rows)

**Branch:** `agent/b1-d7` · **Baseline:** `982335d`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\backend\b1-d7`

## Scope and registry note

The assignment was to implement backend functionality for **every**
`not_started` `D7.*` row in `PLAN-INDEX.json` at the assigned baseline. Reading
the registry found exactly 20 D7 rows: 4 already `verified` (the P0 rows
`D7.1`, `D7.9`, `D7.12`, `D7.19`) and **16 `not_started` rows**, all P1/P2 and
all tagged `implementation_tier: local_module`. The 16 rows are listed below
with their exact registry priority and milestone. All sit in section 8
("Dev workflow, build, CI and release") of
`Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md`.

`PLAN-INDEX.json`, `keel/src/keel/gate_scheduler.py` and every other existing
file were **not** edited. No row status was changed. Only the three owned
files were added.

### P0 rows — verified, not reimplemented

The four P0 rows were implemented earlier in `keel/src/keel/gate_scheduler.py`
(commit on branch `agent/a9-d7`). This change verifies them rather than
duplicating them:

* `test_p0_contracts_present_in_gate_scheduler` asserts
  `gate_scheduler.FEATURE_IDS == ("D7.1", "D7.9", "D7.12", "D7.19")` and the
  presence of `GateGraph`/`simulate_gates`/`parse_scheduler_env` (D7.1),
  `DependencyManifest`/`link_dependencies` (D7.9), `CILane`/
  `validate_ci_layout`/`partition_coverage` (D7.12) and `BenchmarkMethod`/
  `benchmark_dispatch`/`method_digest` (D7.19).
* `test_p0_rows_not_duplicated` asserts that `d7_workflow_backend.FEATURE_IDS`
  is disjoint from `P0_FEATURE_IDS`, and that `P0_FEATURE_IDS` equals the
  gate-scheduler set.
* `master-plan-v6-gate-scheduler-evidence.md` remains the implementation
  evidence for those four rows (77 tests there).

## Classification

Every one of the 16 rows is a workflow/build/CI/release *process* feature whose
registry detail is a script, workflow, gate or document. The honest boundary
for a stdlib-only module is the **host-side contract layer** those processes
consume. Classification used here:

* **C1 — executable contract** — the requirement is expressed as deterministic
  validation, resolution, comparison, planning or rendering with real logic
  (not a stub). Callers supply all data; no process is started.
* **C2 — contract plus rendered artifact** — same as C1, and the module also
  emits a concrete artifact (hook script, install paths, TS client source,
  notice text, required-reading list).
* **E — external/owner action remains** — the physical act (writing CI YAML,
  installing hooks into a real worktree, obtaining a certificate, provisioning
  a self-hosted runner, applying GitHub labels, publishing) is intentionally
  out of scope for this pure module and is recorded as a limitation.

Every row below is C1 or C2 for its contract portion and E for its physical
portion; no row is merely declared or stubbed.

| ID | Pri / MS | Registry requirement (abridged) | Class | Contract implemented | External action that remains (E) |
| --- | --- | --- | --- | --- | --- |
| D7.2 | P2 / M0 | Worker budgets differ locally vs CI; detect cgroup CPU quota; local cap defaults | C1 | `parse_cgroup_cpu_quota` (v2 `quota period`, `max`), `parse_cgroup_v1_cpu_quota` (`-1` = unlimited), `parse_cpu_count`, `parse_worker_env` (caller mapping only), `WorkerBudget`, `make_worker_budget`, `effective_workers` (local capped, cgroup floors both) | Setting the real env vars and mounting cgroup files in CI |
| D7.3 | P1 / M0 | Separate type-check programs for host and client; no combined program; gate verifies exactly one face per package | C1 | `Face`, `TypecheckProgram`, `make_typecheck_program`, `validate_face_programs`, `build_face_programs`, `face_for_package`, `DEFAULT_FACE_PROGRAMS` | Wiring two real `pyright`/`tsc` invocations in CI |
| D7.4 | P1 / M20 | Typed remote-call generation from decorated services; pydantic → JSON Schema → TS; CI drift check | C2 | `SchemaField`, `ServiceMethod`, `RemoteService`, `make_*`, JSON-Schema-subset `render_ts_type`, `render_typescript_client`, `contract_digest`, `check_contract_drift` | Persisting the generated `.ts` file and adding the CI drift step |
| D7.5 | P1 / M22 | Fixed build order; `build:check` verifies built output without rebuilding | C1 | `BUILD_STAGES`, `BuildStage`, `validate_build_order`, `build_build_plan`, `make_check_plan` (rejects build verbs, requires built-output targets), `CheckPlan` | Authoring the actual build scripts and CI job |
| D7.6 | P1 / M22 | Embedded identity (version + short commit + dirty); official omits dirty; gitignored record; packing rejects stale | C1 | `BuildIdentity`, `identity_label`, `BuildRecord`, `make_build_record`, `verify_build_record`, `release_pack_allowed`, `record_is_gitignored`, `BUILD_RECORD_PATH` | Embedding values in the real binary and adding the gitignore entry |
| D7.7 | P1 / unassigned | `--profile local` keeps version/commit/dirty and discards inherited branding | C1 | `BuildProfile`, `parse_profile_flag` (strict argv, both `--profile x` forms), `resolve_build_profile`, `ProfileResolution` | Adding the CLI flag to the real build entrypoint |
| D7.8 | P1 / M0 | Keep checkout and toolchain in one OS environment; separate deps; native Windows validation; separate Windows lane | C1 | `Environment`, `BuilderEnvironment`, `make_builder_environment`, `validate_builder_environment`, `check_builder_environment` | Writing the builder docs and the real Windows CI lane |
| D7.10 | P1 / M0 | Worktree-local hook install; pre-commit staged lint + fix + bounded retry + whitespace + metadata + vendor guard; pre-merge check; pre-push typecheck; no tests/builds; opt-in `check:all` | C2 | `HookName`, `HOOK_CHECKS`, `HookSpec`, `make_hook_spec`, `validate_hook_set`, `render_hook_script`, `HookInstall`, `hook_install_plan` (paths `.git/hooks/<hook>`, mode `0755`) | Running the installer against a real worktree and chmod-ing hooks |
| D7.11 | P1 / M0 / M23 | Doc-sync aggregate, doc fence typecheck, type-equiv against source, dead-link check, translation pairings with repair command | C2 | `DOC_GATES`, `DocGateSpec`, `validate_doc_gates`, `extract_code_fences`, `typecheck_code_fences` (real `compile`), `check_type_equivalence`, `check_dead_links`, `TranslationPair`, `make_translation_pair`, `validate_translation_pairs` | Building the docs site and adding gate commands to CI |
| D7.13 | P1 / M25 | Per-file 100% coverage gate separate from tests; 100% on security-critical modules, graded elsewhere | C1 | `SECURITY_CRITICAL_MODULES`, `CoveragePolicy`, `make_coverage_policy`, `evaluate_coverage`, `CoverageReport` (strict 100% for `permission_gate`/`analyzer`/`crypto`, graded threshold, separate `coverage:strict`) | Configuring the real coverage tool and the CI check |
| D7.14 | P1 / M25 | Real-API e2e self-skips without key; "expected" = owner-local; snapshot replay keyless with shipped profile, record mode needs key | C1 | `TestClass`, `TestCase`, `make_test_case`, `validate_test_taxonomy`, `test_disposition`, secret-reference-only key fields | Applying the taxonomy to actual pytest markers and CI lanes |
| D7.15 | P1 / M22 | Credential-free dependency-layout and pack rehearsals using the release recipe; self-host failover only for trusted PRs; manual publish hosted | C1 | `RehearsalKind`, `Rehearsal`, `make_rehearsal`, `validate_rehearsals`, `RunnerContext`, `select_runner` (fork/bot/non-PR/manual ⇒ hosted) | Creating the workflows and provisioning trusted self-hosted runners |
| D7.16 | P1 / M22 | `publint`-style entrypoint validation and clean consumer import; Python `twine check` + clean-venv smoke; TS consumer check | C1 | `PackageEcosystem`, `PackageArtifact`, `make_package_artifact`, `validate_entrypoints`, `consumer_check_plan`, `package_hygiene_report`, check constants | Running `twine`, creating the clean venv, adding the CI job |
| D7.17 | P2 / M22 | Windows signing docs as required reading; desktop packaging profile per signing mode; Keel ships unsigned | C2 | `SigningMode`, `SIGNING_PROFILES`, `PACKAGING_README`, `PackagingProfile`, `make_packaging_profile`, `validate_packaging_profile`, `required_reading`, `default_packaging_profile` | Writing the actual `packaging/README.md` and obtaining a certificate for signed modes |
| D7.18 | P1 / M22 / M19 | Release carries upgrade-guide entries since installed version; show "What changes for you" before install | C2 | `UpgradeEntry`, `build_breaking_notice` (strict semver, range filter, sorted), `render_breaking_notice`, `BreakingNotice` | Shipping the guide entries with the release and wiring the updater UI |
| D7.20 | P2 / M0 | Labels taxonomy and native stacked PRs; merge-forward vs rebase | C1 | `KIND_LABELS`, `AREA_PREFIX`, `STACK_POLICIES`, `validate_pr_labels`, `StackedPR`, `make_stacked_pr`, `validate_stacked_prs` (chain, cycle, policy and native-stack checks) | Creating labels in GitHub and configuring native stack settings |

## Files owned (only these were added)

* NEW `keel/src/keel/d7_workflow_backend.py` — 1,700+ lines, stdlib-only.
* NEW `keel/tests/test_d7_workflow_backend.py` — 79 tests, one class per feature
  plus registry/P0/purity checks.
* NEW `master-plan-v6-d7-backend-evidence.md` (this file).

## Verification

Both commands were run from the worktree root with the required `sys.path`
insert.

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_d7_workflow_backend.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1)"
```

Result: **79 tests passed in 0.25 s** (stdlib-only runner).

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_d7_workflow_backend.py']))"
```

Result: **79 passed, 1,044 subtests passed in 4.27 s** (pytest 9.0.2).

The change is purely additive (three untracked files), so no existing test can
be altered by it. `test_no_host_effects_in_source` and
`test_imports_are_stdlib_only` parse this module's AST and enforce:

* imports limited to `__future__`, `dataclasses`, `enum`, `fnmatch`, `hashlib`,
  `json`, `math`, `re`, `typing`;
* no calls to `open`/`system`/`popen`/`spawn`/`fork`/`exec`/`sleep`/`random`/
  network APIs and no process/filesystem/clock/random modules.

`render_ts_type`, `check_type_equivalence`, `check_dead_links` and
`check_contract_drift` are genuine computations over caller-supplied strings
and schemas; `typecheck_code_fences` uses the built-in `compile` on fenced code
supplied by the caller. Nothing is read from disk or the host environment.

## Adversarial coverage (all green)

* **D7.2** — cgroup v2 `max`/malformed/zero period, v1 `-1`/negative/zero,
  local cap vs CI, fractional cgroup quota floored at 1, unknown `KEEL_WORKER_*`
  key, non-boolean `CI`, non-integer cap.
* **D7.3** — `combined`/`None` faces, duplicate packages across faces, missing
  face program, unknown package, duplicate ids, order-independent serialization.
* **D7.4** — TS rendering of scalars/arrays/enums/optional object fields,
  undefined `$ref`, malformed schemas, duplicate params/methods, digest drift
  when a parameter type changes, uppercase/non-hex recorded digest rejected.
* **D7.5** — canonical stage order, reversed input rejected, dependency on a
  later stage, missing/duplicate/unknown stages, empty output, traversal path,
  `build`/`compile`/`bundle` commands in check stage rejected, check command
  must name built output.
* **D7.6** — official dirty marker omitted while the dirty flag is retained,
  missing/malformed/stale/identity-mismatched/output-mismatched records, strict
  versions, short/lowercase hex commits, uppercase digests, gitignore patterns.
* **D7.7** — both `--profile` flag forms, missing/duplicate flags, local keeps
  dirty and drops branding, official applies sorted branding, malformed
  branding keys/values.
* **D7.8** — cross-environment checkout/toolchain, shared dependency roots,
  missing root, Windows without native validation or separate lane, unknown
  environments, traversal paths.
* **D7.10** — all three hooks exactly once, install paths/mode, bounded retry
  in rendered script, test/build checks rejected, `check:all` requires both the
  opt-in flag and `check_all_enabled`, traversal `git_dir`, unknown hook.
* **D7.11** — all five doc gates and aggregate bundles, fence extraction and
  real compile failure, type-equivalence mismatch, dead link detection,
  duplicate/forged translation records.
* **D7.13** — 100% strict on three security-critical modules, graded threshold,
  missing data, out-of-range/bool/string/NaN/inf coverage, gate must differ
  from the test command.
* **D7.14** — literal API key rejected, missing key refs reported, keyless
  replay needs shipped profile, record mode needs key, expected tests must be
  owner-local, duplicate ids.
* **D7.15** — literal and secret-ref credentials rejected in rehearsals,
  publish commands rejected, release recipe required, both kinds exactly once,
  fork/bot/non-PR/manual-publish forced to hosted.
* **D7.16** — Python vs Node entrypoint suffixes, missing files, clean-venv
  and consumer check plans, scoped Node package name, traversal path.
* **D7.17** — Keel unsigned default, signed modes need reference and docs,
  forged profile id, unsigned with cert reference, unknown signing mode.
* **D7.18** — version range filtering, ascending order, non-breaking entries
  excluded, no-break message, downgrade/equal/malformed versions.
* **D7.20** — exactly one `kind/*` and at least one `area/*`, unknown labels,
  base chain, cycles, mixed merge policies, non-native stacks, duplicate ids.

## TDD and defects found

The test suite was written against the contract first and exposed four real
implementation defects, which were fixed in the module rather than by
weakening assertions:

1. `_digest` lowercased its input before the regex check, so an uppercase
   SHA-256 was accepted even though the contract promises lowercase-only; the
   normalizing call was removed.
2. `parse_cgroup_v1_cpu_quota` rejected cgroup v1's `-1` ("no limit") value;
   it now returns `None` for `-1` and `0` while still rejecting values below
   `-1`.
3. Strict identifier validation rejected legitimate separator-bearing names
   (`kind/bug`, `@keel/client`, `docs/a.md`); a dedicated `_LOOSE_NAME_RE`
   was added for those fields, keeping strict validation everywhere else.
4. `render_hook_script` originally filtered the opt-in error out of a shared
   validator result, which could render `check:all` without opt-in; the
   renderer now validates the opt-in and retry bound itself.

Several test-harness corrections were also needed: the module deliberately
uses two failure styles — builders raise `ContractValidationError` while
`validate_*` functions return a tuple of written reasons — and a handful of
tests initially asserted a raise for the tuple-returning validators. They now
assert the written reason, matching the documented contract.

No registry status was changed: all 16 rows remain `not_started` in
`PLAN-INDEX.json`. This evidence claims the pure backend contract layer only;
it does not claim that CI workflow files, installed hooks, a generated TS file
checked into the repo, a signing certificate or a published release were
shipped end-to-end.
