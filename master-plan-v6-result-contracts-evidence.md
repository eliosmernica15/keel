# Result contracts — implementation evidence (E3/E4 P0 assignment)

**Branch:** `agent/a9-e34` · **Baseline:** `f2c0fe6`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a9-e34`

## Scope and registry note

The assignment was to read the full text of the five `not_started` **P0**
rows `E3.3`, `E3.8`, `E4.5`, `E4.8` and `E4.15` in `PLAN-INDEX.json` and
implement the pure result/contract surface in three new files. Reading the
registry at the assigned baseline found exactly those five rows, all with
`implementation_tier: local_module`. Their full acceptance text is reproduced
here for traceability:

| ID | Full registry feature text | Detail | Milestone | Status |
| --- | --- | --- | --- | --- |
| E3.3 | Agent names: 1 to 32 lowercase letters/digits/hyphens starting with a letter, not lead; default agent-N; root is lead; full names are slash paths; names are model-facing references, session ids are the authority; resolve returns the id and grants no permission; a slash path with no match fails AGENT_NAME_NOT_FOUND. | Name rules + `resolve_name()`; authorization separate. | M12 | `not_started` / P0 |
| E3.8 | Result object: final output = last non-empty assistant message; optional structured value validated against the requested schema; diagnostic text limited to 4,096 bytes and free of tool inputs, file contents, env values, credentials, raw protocol payloads; stop reason enum (completed, aborted, error, max-tokens, refusal). Child failure resolves with error, not an exception. | `Result` dataclass + diagnostic sanitizer test. | M12 | `not_started` / P0 |
| E4.5 | Snapshot scenarios: parent/child session files with version in filename that must agree with header; `snapshot.yml` declares profile, header class, recording policy, workspace facts; typed tokens keep parent/child identity relations; mutating scenarios compare a full `workspace.expected/` tree that record/refresh never rewrite; modes record (needs key), refresh (replay input still valid), review every diff; CI read-only replay. | Keel snapshot harness (X9.2) with these rules. | M25 | `not_started` / P0 |
| E4.8 | Test-process isolation rules: forked workers share ports, paths, namespaces and children; each test owns every resource it acquires through teardown; a spec that passes only alone is a test defect; fork-exit diagnostics report PID, file, code, signal; flake-diagnosis workflow classifies probabilistic failures. | `tests/conftest.py` fixtures for ports/tmp dirs; xdist-style parallel run; flake report. | M25 | `not_started` / P0 |
| E4.15 | Every non-trivial model/protocol/human-visible change updates a keyless recorded-session scenario; new capability seams and lifecycle variants name every required test tier at plan time. | Plan-time "test tiers" field in `PLAN-INDEX.json`. | M0 | `not_started` / P0 |

These rows describe protocol, policy and testing behaviour spread across
addendum-7 sections 4 ("Subagents (DS-SUB)") and 5 ("Testing policy
(DS-TEST)"). The explicit deliverable — a stdlib-only, pure, fail-closed
**contract surface** — is unambiguous, so this change implements that surface
as the host-side module those runtimes and harnesses consume. `PLAN-INDEX.json`
and all other existing files were **not** edited; no row status was changed
here, and this evidence does not claim the full snapshot harness or runner was
shipped end-to-end.

## Files owned (only these were added)

* NEW `keel/src/keel/result_contracts.py` (1,691 lines)
* NEW `keel/tests/test_result_contracts.py` (60 tests, 799 lines)
* NEW `master-plan-v6-result-contracts-evidence.md` (this file)

## Required behaviour → implementation map

| Requirement | Contract surface in `keel.result_contracts` |
| --- | --- |
| E3.3 name grammar | `validate_agent_name`/`make_agent_name`: 1–32 chars, `^[a-z][a-z0-9-]{0,31}$`, first char a letter; `RESERVED_AGENT_NAMES = {'lead'}`; every invalid value raises `ContractValidationError` |
| E3.3 default + root + paths | `default_agent_name` (smallest unused `agent-N`), `ROOT_AGENT_NAME='lead'`, `validate_agent_path`/`make_agent_path` (slash paths rooted at `lead`, traversal/empty segments rejected), `parent_agent_path` |
| E3.3 names are references | `AgentRegistry`/`make_registry` map full names to authoritative session ids; `resolve_name` returns **only the id string**; aliases may share an id; no permission object exists anywhere in the API |
| E3.3 not-found failure | `AgentNameNotFoundError` with `code = AGENT_NAME_NOT_FOUND`; raised for unknown *and* malformed paths, and when a plain mapping is passed instead of a registry |
| E3.8 final output | `last_assistant_message` walks messages in order, accepts `str` or text-block content, ignores user/tool roles, whitespace-only and malformed messages, and returns the last non-empty assistant text (or `''`) |
| E3.8 structured output | `Result`/`build_result`; `normalize_schema` accepts a fail-closed JSON-Schema subset (type/required/properties/items/enum/const/boolean `additionalProperties`, length/range/pattern, no unknown keywords); `validate_structured`, `is_json_safe`; a requested schema with no value is rejected |
| E3.8 diagnostics | `sanitize_diagnostics` → `DIAGNOSTIC_BYTE_LIMIT = 4096`; strips PEM keys, fenced file contents, credential prefixes, bearer tokens, secret assignments, env values, tool-input/raw-payload markers and over-long file-dump lines, then truncates on a UTF-8 codepoint boundary; `assert_clean_diagnostics` proves idempotence and cleanliness |
| E3.8 stop reasons + children | `StopReason` closed enum (`completed`, `aborted`, `error`, `max-tokens`, `refusal`) with `parse_stop_reason`; `child_failure_to_result` and `resolve_child_outcome` always return an `ERROR` result, never raise (last-resort guard included) |
| E4.5 filename ↔ header | `parse_session_file` reads `parent-vN.*` / `child-vN.*` version; `validate_snapshot_pair` requires filename version == header version, matching roles/header class, distinct ids and `child.parent_id == parent.session_id` |
| E4.5 snapshot.yml | `SnapshotConfig`/`make_snapshot_config`: profile, header class, recording policy (`keyless`/`record-requires-key`/`replay-only`), keyless workspace facts, `mutating` flag; `validate_snapshot_config` fails closed on unknown values |
| E4.5 typed identity | `TokenKind`/`TypedToken`; `make_snapshot_pair` emits eight typed tokens binding parent/child ids, the child→parent link, file vs header versions and the header class; `verify_identity_tokens` rejects missing, duplicated, wrongly-owned or tampered tokens |
| E4.5 expected tree | `WorkspaceManifest`/`make_workspace_manifest` (SHA-256 digest manifest from caller mappings, lexical path safety, no filesystem access); `compare_workspace` → `WorkspaceDiff`; `assert_expected_immutable`; `snapshot_write_allowed`/`assert_snapshot_write_allowed` forbid writes under `workspace.expected` in **every** mode |
| E4.5 modes | `SnapshotMode` + `MODE_REQUIREMENTS`: record needs a key, refresh needs valid replay input, review needs a reviewed diff, CI replay is read-only; `can_run_mode`, `is_read_only_mode`, `review_all_diffs` (fails unless every changed path is reviewed) |
| E4.8 shared resources | `ResourceKind`/`ResourceLease`/`make_lease`; `validate_lease` requires a named owner, worker and teardown ownership; `detect_isolation_violations`/`assert_isolated` detect any port/path/namespace/child-process reused across workers |
| E4.8 fork diagnostics | `ForkExit`/`fork_exit_diagnostic`: always emits `pid=`, `file=`, `code=`, `signal=`; fails closed when PID/file are missing or both code and signal are absent |
| E4.8 flake workflow | `solo_only_is_defect` (solo-pass/suite-fail = defect), `FlakeClass`, `classify_flake` (isolation defect / probabilistic / deterministic pass/fail / order dependent / unknown), `flake_report` (deterministic, conflict-safe) |
| E4.15 keyless log | `ChangeRecord`/`ChangeLog`/`make_change_record`/`make_change_log`/`add_change`: no key-valued field exists; credential-looking summaries or scenario refs are rejected; `assert_keyless`, `assert_all_nontrivial_covered`, `validate_change_log` (unique ids) |
| E4.15 test tiers | `TestTier` mirrors the test-plan legend (U/C/I/G/P/E/A/S/D/F), `TEST_TIERS`, `parse_test_tier`; non-trivial visible changes must name a scenario **and** tiers; `new_capability_seam`/`lifecycle_variant` require `REQUIRED_TIERS_FOR_NEW_SURFACE` = `{unit, contract, integration, e2e, adversarial}` |
| Purity / fail-closed | stdlib-only imports (`__future__`, `hashlib`, `json`, `re`, `dataclasses`, `enum`, `typing`); no file, process, clock, chance or transport calls; unknown values and malformed payloads raise `ContractValidationError` |

## Verification

Both commands were run from the worktree root.

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_result_contracts.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
```

Result: **60 tests passed in ~0.15 s** (stdlib-only runner).

```
set PYTHONPATH=keel/src
python -m pytest -q keel/tests/test_result_contracts.py
```

Result: **60 passed, 54 subtests passed in ~1.3 s** (no warnings).

## Adversarial coverage (all green)

* **Name validation** — empty, uppercase, leading digit/hyphen, underscores,
  spaces, Unicode, dotted names, 33-character names and the reserved `lead`
  are all rejected; trailing-hyphen forms accepted by the literal grammar are
  allowed. Path traversal (`lead/../x`), empty segments, backslashes, control
  characters and non-root roots are rejected; `resolve_name` returns a plain
  string id, and unknown/malformed paths raise `AGENT_NAME_NOT_FOUND`.
* **Diagnostics sanitizer** — literal `sk-`/`ghp_`/`xoxb-`/`AKIA` keys, bearer
  tokens, `api_key=...` assignments and `env:NAME=` values are removed (the
  variable name survives as `[env:NAME=REDACTED]`); JSON tool inputs lose their
  arguments, `<file>...</file>` blocks and PEM private keys are replaced,
  `base64_blob=...` payloads are scrubbed, 400-character file dumps are
  truncated, and 12,000-byte multibyte text is capped at 4,096 UTF-8 bytes on a
  codepoint boundary. Sanitization is idempotent and `assert_clean_diagnostics`
  rejects dirty text.
* **Result gating** — boolean/integer/enum/const/array-item/required/extra-key
  schema violations fail; unknown schema keywords, non-JSON values, a schema
  without a structured value, and secret-bearing structured values are
  refused. Child failures with exploding `__str__`, non-mapping inputs and
  malformed schemas still resolve to an `ERROR` result.
* **Snapshot consistency** — filename/header version mismatch, role mismatch,
  header-class mismatch, a child pointing at the wrong parent, identical parent
  and child ids, unknown profiles/policies, keyless workspace-fact violations,
  unsafe workspace paths, tampered/duplicated/missing/wrong-owner tokens and
  un-reviewed diffs all fail closed. `workspace.expected` is unwritable in
  record, refresh, review and CI replay; CI replay can write nothing.
* **Isolation** — leases without an owner/teardown and reused
  ports/namespaces/child pids across workers are detected; fork exits missing
  PID, file or both code+signal are refused while signal-only exits still
  report all four fields; solo-only passes classify as `ISOLATION_DEFECT`,
  intermittent runs as `PROBABILISTIC`, and conflicting flake reports are
  rejected.
* **Keylessness** — secret summaries/scenario refs are rejected without
  echoing the secret in the error; workspace manifests store only SHA-256
  digests; change records have no key/token/secret/password field; a directly
  constructed dirty `ChangeLog` fails `assert_keyless`.
* **Purity** — two AST-based tests assert the module imports only the permitted
  stdlib set and contains no `open`/`exec`/`eval`/`input`/`system`/`popen`/
  `spawn`/filesystem/clock/network calls.

## Design notes

* **Contract layer, not a harness.** Every function takes caller-owned data and
  returns frozen descriptors or plain data. There is no filesystem, clock,
  subprocess, transport or credential store, so the same input yields the same
  result in CI, in a forked worker and on every platform.
* **Identity without authority.** `resolve_name` deliberately returns a bare
  session-id string. There is no permission parameter, return field or
  dependency anywhere in E3.3, keeping "names are references" structurally
  true rather than a convention.
* **Defence in depth on diagnostics.** Redaction happens before line truncation
  and before the byte cap, so a secret cannot survive by straddling a cut; the
  replacement markers are chosen so re-sanitizing is a no-op, which makes the
  cleanliness check cheap and exact.
* **Typed relations are verifiable.** The eight E4.5 tokens encode not just ids
  but the child→parent link and file-vs-header versions, so a recorded scenario
  can be integrity-checked without re-reading its session files.
* **Immutability is a write rule.** `workspace.expected/` is refused by
  `snapshot_write_allowed` for all four modes rather than relying on record and
  refresh implementations to "be careful"; CI replay additionally refuses every
  write.
* **Test tiers come from the plan.** The ten `TestTier` values mirror the
  `test-plan.md` legend, and new capability seams/lifecycle variants must name
  the five core tiers at plan time, satisfying E4.15's "name every required
  test tier" clause.

## Integration seams for the lead (not made here — file ownership)

1. **Subagent runner (E3.3/E3.8)** — validate delegated agent names with
   `make_agent_name`, build `agent-N` defaults from the live registry, and call
   `resolve_name` only for model-facing references; build the user-visible
   result with `build_result` and surface `child_failure_to_result` for a failed
   child so the parent never receives an exception.
2. **Diagnostic logging (E3.8)** — pass every child diagnostic through
   `sanitize_diagnostics` before it reaches a log, event or UI; call
   `assert_clean_diagnostics` in the invariant gate (V16-style "no secret in
   logs").
3. **Snapshot harness (E4.5)** — use `make_snapshot_config`/`make_snapshot_pair`
   when loading a scenario, `verify_identity_tokens` on every replay,
   `compare_workspace` against the observed tree and `review_all_diffs` before
   marking a review complete; gate writes through `assert_snapshot_write_allowed`
   and keep CI in `SnapshotMode.CI_REPLAY`.
4. **Parallel test runner (E4.8)** — adapt `keel/tests/conftest.py` port/tmp-dir
   fixtures to mint `ResourceLease` objects and call `assert_isolated` at
   teardown; feed forked-worker exits through `fork_exit_diagnostic` and feed
   repeated-run data through `classify_flake`/`flake_report`.
5. **Plan/CI registry (E4.15)** — when a P0 row is marked verified, append a
   `ChangeRecord` naming its recorded scenario and test tiers; run
   `assert_all_nontrivial_covered` and `assert_keyless` as a pre-merge gate.
