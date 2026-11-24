# Independent backend review — Group 1 (D6 / D7 / E3 / E7 / V-series)

**Reviewer:** independent subagent (did not implement any of the reviewed code)
**Branch reviewed:** `integration/v6-backend-complete` (HEAD `1ffffb2`), review committed on `agent/review-g1`
**Date:** 2026-11-24
**Method:** static review of all 10 target files (≈452 KB of source + ≈205 KB of tests), plus each
module's own test file only (no full suite, per instruction), plus small targeted Python probes for
suspected defects. All five target test files pass:

| module | test result |
| --- | --- |
| `test_d6_reliability_backend.py` | 35 passed |
| `test_d7_workflow_backend.py` | 79 passed, 1044 subtests passed |
| `test_e3_backend.py` | 60 passed, 22 subtests passed |
| `test_e7_runtime_backend.py` | 79 passed |
| `test_v_series_backend.py` | 84 passed, 49 subtests passed |

## Cross-cutting findings

1. **All five modules contain real, observable behavior** — data structures with invariants,
   state machines, validators, deterministic algorithms and fail-closed policies. None is a
   descriptor/catalog-only stub. There are descriptor helpers and feature-ID registries in each
   (e.g. `E7.FEATURE_SURFACES` 3079-3116, `V.P0_BASELINE` 68-76, `D6.DOCSTRING_WORD_BUDGETS`
   1205-1207), but they are a small minority of the public surface and are backed by executable
   logic. Verdict for every module: **GENUINE_BACKEND**.

2. **Test quality is substantive.** Assertions cover exact outputs, typed errors/codes, state
   transitions, byte-identical digests, adversarial malformed inputs and security properties
   (redaction, taint, path traversal, CAS, role checks). The only existence-only assertions are
   narrow registry/purity guards (e.g. `test_d7_workflow_backend.py:86-111` and
   `test_e7_runtime_backend.py:1039-1047`), not the bulk of any suite.

3. **Runtime wiring is minimal.** Only `e3_backend.py:94-103` imports real Keel runtime code
   (`keel.result_contracts`: `Result`, `StopReason`, `build_result`, `child_failure_to_result`,
   `make_agent_name`, `parse_stop_reason`, `validate_agent_name`, `ContractValidationError`).
   D6, D7, E7 and V are stdlib-only and import no `keel.*` module at all. None of the five is
   imported by the authoritative runtime as committed on this branch. (There is uncommitted,
   untracked hub wiring in the shared worktree — `backend_hub.py`, `capabilities.py` — which is
   outside the reviewed commit and was not modified by this review.)

4. **No dangerous dynamic execution or ambient I/O.** No `eval`, no `os.system`, no `subprocess`,
   no `open`, no network, no clock/random, no `yaml.load`, no credential storage. The two
   `compile()` calls (`d7_workflow_backend.py:1152`, plus regex/scan uses of the word) are
   syntax-only checks on caller-supplied doc fences — the code is never executed. Path-like
   inputs are generally constrained to relative, traversal-free forms (`d7._paths` 111-121,
   `e7.WorkspaceSnapshot` 391-399, `e7.path_completions` 499-516, `e3.resolve_child_cwd` 522-534,
   `d6.classify_path` 1059-1069). Hook scripts are rendered only from a fixed command allowlist
   (`d7._HOOK_COMMANDS` 979-989).

5. **No locks anywhere.** All mutable state is in-memory per-instance and intended for a single
   caller/thread; concurrent use of check-then-act paths (capacity checks, CAS, flow begin, token
   rotation, lock acquire) could race. This is a documented architectural limitation rather than
   a tested contract; no module claims thread-safety.

---

## 1. `d6_reliability_backend.py` + `test_d6_reliability_backend.py`

**1. Real behavior?** Yes. Genuine engines throughout:
- `KeelError` hierarchy + `all_error_codes()` (78-202) with stable codes and `to_dict()`;
- `ApiChangeRecorder.record/validate/upgrade_guide_missing` (306-346) computes missing consumers
  and unrecorded breaking changes; `SchemaVersion.next`/`assert_monotonic` (357-378);
- `EventCatalog.validate/dispatch` (466-515) with closed/extensible union semantics and
  `render_mode`/`assert_never` exhaustive dispatch (518-532);
- `resolve()` (573-603) applies and records defaults, `run()` (606-611) refuses unresolved
  requests, AST scanners `scan_schema_version`/`find_hidden_defaults`/`lint_plugin_source`/
  `audit_id_annotations` (381-395, 614-627, 691-724, 821-840);
- `ReferenceRegistry`/`load_with_references` (740-787) recursive `$ref` resolution that fails
  closed on unknown names; `BoundaryRegistry.validate` (899-946) with type/shape checks;
- `CastBaseline.check` (1003-1013), `ImportGate.resolve` (1112-1124), `SnapshotRegistry.replay`
  with **exact** output comparison (1486-1492), `validate_projection` (1563-1583),
  `VendorManifest.check_tree_sha` (1691-1701), `GateRegistry.probe_all`/`top_level_gate`
  (1945-1960) which executes each gate's valid/invalid case.

**2. Tests exercise behavior?** Yes — 35 tests assert outputs/errors/state, e.g.
`test_api_change_recorder_checks_consumers_and_upgrade_note` (28-65) asserts exact
`missing_consumers` maps and duplicate rejection; `test_snapshot_registry_replays_exactly`
(434-451) asserts drift detection; `test_gate_registry_requires_each_gate_to_reject_its_invalid_case`
(605-629) probes a deliberately broken gate; `test_module_is_stdlib_only_deterministic_and_side_effect_free`
(637-659) AST-checks purity. No existence-only test filler.

**3. Real defects:**
- LOW — `audit_docstrings` (d6:1242-1244): `check_doc(tree, "module", ...)` already appends a
  `missing_docstring` finding, then `if not module_doc.strip()` appends an identical one.
  Probe: `audit_docstrings('def public():\n    pass\n','p.py')` returns three findings
  (`missing_docstring` ×2 plus the function's), not two. Cosmetic but a real duplicate.
- LOW — `load_with_references` (d6:772-787): `trail` is constructed and threaded through `walk`
  but never read; no cycle/alias accounting exists. Harmless today because referents are returned
  by value and not re-walked.
- LOW — `assert_keyless` (d6:1393-1416): `_UNIX_ABS_RE` only matches `/Users|home|root|tmp`, so
  volatile absolute values like `/opt/run/...` are not flagged. Heuristic gap in a fail-closed gate.

No security hole, mutable default, unhandled exception or race found. All mutable defaults are
tuples or `default_factory` (552, 684, 720 etc.).

**4. Runtime import?** None. Stdlib only (`ast`, `fnmatch`, `hashlib`, `io`, `json`, `re`,
`tokenize`, `dataclasses`, `enum`, `typing`). Fully isolated/additive.

**5. Verdict: GENUINE_BACKEND.**
Top 3: (1) LOW duplicate module docstring findings `d6_reliability_backend.py:1242-1244`;
(2) LOW unused `trail` / no cycle tracking `d6_reliability_backend.py:772-787`;
(3) LOW incomplete absolute-path heuristic `d6_reliability_backend.py:1397,1413-1416`.
No high- or medium-severity defects.

---

## 2. `d7_workflow_backend.py` + `test_d7_workflow_backend.py`

**1. Real behavior?** Yes. Algorithms/validators with invariants:
- `parse_cgroup_cpu_quota`/`parse_cgroup_v1_cpu_quota`/`parse_cpu_count` (215-265) parse real
  cgroup text with fail-closed checks; `make_worker_budget`/`effective_workers` (282-328) implement
  CI-vs-local-vs-cgroup capping; `parse_worker_env` (294-316) rejects unknown `KEEL_WORKER_*` keys;
- `validate_face_programs`/`build_face_programs` (371-407) enforce two faces, unique owners and
  package exclusivity; `make_service`/`render_ts_type`/`render_typescript_client`/`contract_digest`
  (541-605) validate a JSON-Schema subset and deterministically render TypeScript + SHA-256 digest;
- `validate_build_order` (661-690) enforces the seven documented stages and dependency order;
  `make_check_plan` (711-730) rejects rebuilding commands; `verify_build_record` (789-811) checks
  identity, digest and output list; `resolve_build_profile` (872-889) applies branding only to
  official builds; `check_builder_environment` (930-957); `validate_hook_set`/`render_hook_script`/
  `hook_install_plan` (1015-1087); `extract_code_fences`/`typecheck_code_fences`/`check_dead_links`
  (1137-1183); `evaluate_coverage` (1282-1304); `test_disposition` (1373-1385);
  `build_breaking_notice` (1646-1660) filters by semantic version range;
  `validate_stacked_prs` (1722-1749) detects base cycles.

**2. Tests exercise behavior?** Yes — 79 tests + 1044 subtests. Examples: `test_cgroup_v2_parsing`
and `test_cgroup_v2_rejects_malformed` (160-171) assert numeric values and adversarial rejection;
`test_local_cap_and_quota` (181-188) asserts worker-count outcomes; TS contract generation tests
assert rendered text/digests; `type_equiv`/dead-links/doc-gate tests assert concrete results.
Only `test_all_sixteen_feature_ids_declared`, `test_p0_rows_not_duplicated`,
`test_public_api_exports_exist` (86-111) are registry/existence guards.

**3. Real defects:**
- LOW — `make_check_plan` (d7:711-730): the "check command targets built output" rule uses
  substring matching, `if not any(output in command for output in outputs)`. A short output name
  (e.g. `a`) is satisfied by any command containing that character, so the gate is spuriously
  passable. Should use path-aware token matching.
- LOW — `typecheck_code_fences` (d7:1145-1156): despite the name, it only calls
  `compile(..., "exec")` for syntax validation and never checks types or executes code. Safe, but
  the contract name overstates the guarantee; callers treating it as type checking would be misled.
- LOW — `check_dead_links` (d7:1171-1183): `available_targets` is constrained by `_loose_names`
  (`_LOOSE_NAME_RE`, 71), so legitimate relative doc links containing `..` or spaces are rejected
  as malformed targets instead of being compared. Narrower than the feature description implies.

No I/O, injection or mutable-default issues. Hook command rendering uses only the fixed
`_HOOK_COMMANDS` allowlist with an integer `{retries}` substitution (1066-1069).

**4. Runtime import?** None. Stdlib only (`fnmatch`, `hashlib`, `json`, `math`, `re`,
`dataclasses`, `enum`, `typing`). Fully isolated/additive; the test imports `keel.gate_scheduler`
only to verify the four P0 rows it deliberately does not duplicate (test:30, 94-106).

**5. Verdict: GENUINE_BACKEND.**
Top 3: (1) LOW weak substring output check `d7_workflow_backend.py:726`;
(2) LOW mislabeled syntax-only "typecheck" `d7_workflow_backend.py:1145-1156`;
(3) LOW over-restrictive link-target validator `d7_workflow_backend.py:1171-1175`.
No high- or medium-severity defects.

---

## 3. `e3_backend.py` + `test_e3_backend.py`

**1. Real behavior?** Yes — the strongest in-memory state machine of the batch:
- `SubagentManager` (821-1334) owns nodes, activations, providers, messages, events and a live
  route allowlist; `start()` (996-1061) validates capabilities, route, external-execution flag,
  fork seed, parent existence, "already live" and capacity **before** mutating state; `_cold_resume`
  (1063-1088) reuses logged cwd, refuses one-shot follow-ups and drops the old output schema;
- `send_message` (1092-1143) rechecks sender identity, validates attachments/timezone, steers a
  live target or cold-resumes an absent one, and never retracts accepted messages;
  `settle` (1163-1210) builds a sanitized `Result` via the real runtime contract, emits lifecycle
  events and applies parent/caller/offline delivery policy; `interrupt` (1214-1235) authorizes only
  `user` or an exact live ancestor and preserves inbox/descendants; `drain_tree`/`dispose_tree`
  (1239-1274) settle child-first; `list_descendants` (1278-1334) projects membership with
  per-branch diagnostics and no execution-status field;
- Real algorithms: `compute_fork_prefix` (573-597) rejects gaps, loss and unbalanced groups;
  `resolve_child_cwd` (522-534) does POSIX-normpath resolution with absolute-path handling;
  `parse_model_route`/`check_route` (452-495) enforce a default-off live allowlist;
  `verify_p0_contracts` (1351-1374) actually executes the E3.3/E3.8 contract checks.

**2. Tests exercise behavior?** Yes — 60 tests + 22 subtests assert state transitions and
security properties: no state created on rejected start (145-149), settled notices are untitled
and secret-free (177-183), input closed after structured output (262-277), one-shot no-follow-up
(359), interrupt preserves inbox/descendants (456-469), child-first dispose order (284),
route allowlist codes (578-605), image rejection with no message accepted (627-628),
redaction of `sk-...` (116). Registry/purity guards exist but are a minority.

**3. Real defects:**
- **MEDIUM** — `register_provider` (e3:971-978): overwrites `self.providers[id]` with no duplicate
  check. Probe: after `m.register_provider(ProviderCapabilities('local', frozenset(),
  accepts_images=False))`, the built-in `local` provider loses `E3_1_CAPABILITIES` and `IMAGES`;
  later starts with agent options and image messages fail. Any caller (including a plugin-facing
  bridge) can silently downgrade or replace a provider mid-tree. Should reject duplicate IDs.
- LOW — `settle` (e3:1177-1180): `stop_reason=StopReason.ERROR` with `error=None` calls
  `child_failure_to_result(None)`; probe yields `final_output=''`, `diagnostics='child failure: '`
  instead of a typed error. Silent low-quality diagnostic rather than fail-closed rejection.
- LOW — no synchronization on `SubagentManager` (capacity check at 1027-1029 followed by
  activation creation at 1049-1061 is a check-then-act sequence); concurrent callers could exceed
  `capacity`. The class is not documented as thread-safe, so this is a documented-scope limitation.

No path traversal (`_ABSOLUTE_PATH_RE` 129, `_normalize_path` 517-519), no eval/exec, no secret
storage (attachments are opaque refs, 605-626).

**4. Runtime import?** **Yes — wired to real Keel runtime.** `e3_backend.py:94-103` imports
`Result`, `StopReason`, `ContractValidationError`, `build_result`, `child_failure_to_result`,
`make_agent_name`, `parse_stop_reason`, `validate_agent_name` from `keel.result_contracts`.
This is the only one of the five with a real runtime dependency; it reuses rather than duplicates
the P0 contracts.

**5. Verdict: GENUINE_BACKEND.**
Top 3: (1) MEDIUM silent provider overwrite `e3_backend.py:971-978`;
(2) LOW empty error diagnostic on `settle(ERROR, error=None)` `e3_backend.py:1177-1180`;
(3) LOW unsynchronized capacity check `e3_backend.py:1025-1029,1049-1061`.

---

## 4. `e7_runtime_backend.py` + `test_e7_runtime_backend.py`

**1. Real behavior?** Yes, extensively — 36 feature surfaces with concrete logic:
- `TokenMeter.fold/replay/pressure_measurement` (197-239) per-session isolated folds with
  revisioned immutable measurements; `compaction_decision` (278-290) a real pressure-state
  decision table with rejection of model-requested compaction; `assert_no_compact_tool` (298-302);
- `SessionStatusStore` with monotonic acks (325-361), `WorkspaceChangeFeed.begin/end` diffing
  snapshots by session+seq (427-466), `path_completions`/`parse_at_paths` (499-538),
  `resolve_session_reference` with bounded, redacted, delimiter-escaped tainted context
  (578-592), `SessionQueryService.search` (696-731) with ranked FTS-style scoring and
  generation/identity-bound base64 cursors (636-656);
- `TitleService.fold/title_for` (796-827) with deterministic fallback on provider failure,
  `PlanModeService.fold/flush/exit` (896-945) with stable exit schema,
  `parse_preset_yaml` (967-1004) a strict hand-rolled parser (no `yaml.load`),
  `PresetRegistry.publish/retire/bind/release` (1007-1062) with revision GC,
  `ProjectionCache.checkpoint` with throttling + mandatory reasons (1087-1120),
  `reconcile`/`McpManager.apply` (1165-1222), `SchedulerStore.due` (1285-1295),
  `SshSeam` descriptor lifecycle (1346-1382), `ShellEnvRegistry` with unsafe-char filtering and
  one trusted snapshot per effect (1430-1464), `LspService.dispatch` with escape-hatch rejection
  (1507-1538), `SpeechToTextService` draft-only submission (1585-1615), `OfficeKit.select`
  (1679-1687), `UploadService` incremental SHA-256 with session binding (1717-1769),
  `ForgeService` URL/ref/poll-loop handling (1815-1878), `RolePolicy` authorization + filtered
  lists (1921-1952), `AuthRegistry` first-live-peer with trace (1993-2035),
  `AuthFlowRegistry` one-attempt-per-key (2067-2120), `CardRegistry.invoke` (2178-2192),
  `RecommendationPolicy`, `fastest_valid_mirror`, `parse_market_index`, `FeedbackLog` CAS,
  `HookBridgeRegistry`, `AgentPluginPolicy`, `LoopUntilDone.tick`, `WebhookRuntime.deliver`,
  `InspectorService.query/trace` with cycle detection, `StorageSeam` with JSON-safe copies,
  `McpResourcesService.read` agent scoping, `ProviderSeams` consent/runtimes.
- Descriptor content exists at the end (`FEATURE_SURFACES` 3079-3116 and `feature_descriptors`
  3132-3133), but it is a completeness index, not the substance.

**2. Tests exercise behavior?** Yes — 79 tests assert exact outputs/errors/transitions across all
36 features, e.g. token replay equality (33-45), compaction decision table (64-74),
workspace diff (119-127), secret redaction + truncation (169-181), cursor paging (208-216),
mandatory checkpoints (325-332), MCP reconcile (353-369), upload chunk hashing/session binding
(544-565), role filtering and snapshot digests (605-625), verifier trace and first-live-peer
(642-657), webhook signature/confirmation failure modes (919-931), plugin-tree cycle detection
(957-963), deep-copy isolation (971-975). Only `test_exactly_the_36_open_rows_are_indexed`
(1039-1047) is a registry guard.

**3. Real defects:**
- **MEDIUM** — `Workflow.__post_init__` (e7:2623-2632): computes
  `ids = [n.node_id for n in self.nodes]` (2625) and checks `n.node_id == n.target` (2628)
  *before* the `isinstance(node, WorkflowNode)` validation at 2630-2632. A malformed node (e.g.
  a string) raises `AttributeError: 'str' object has no attribute 'node_id'` instead of the
  module's fail-closed `ValidationError`. Probe confirmed. `test_workflow_validation`
  (test:887-896) covers duplicate IDs/fanout/self-ref but not this case.
- LOW — `AuthFlowRegistry.complete` (e7:2096-2105): rejects only `_SECRET_RE` token patterns
  (`sk-`, `ghp_`, ...). Probe: `complete('k', 'api_key=supersecretvalue')` stores the literal,
  contradicting the class docstring "Only opaque credential references are stored, never
  credential values" (2068). The sibling `_SECRET_ASSIGN_RE` (79-82) exists but is not reused here.
- LOW — mutable in-memory managers have no locks (`FeedbackLog` CAS 2423-2432, `AuthFlowRegistry`
  begin/complete 2084-2105, `TokenMeter.fold` 203-210); concurrent callers can interleave
  check-then-act sequences. Not claimed thread-safe; no threading tests.

No path traversal (workspace paths reject `..`/absolute/backslash 398-399), no eval/exec, no
unsafe YAML, no dynamic execution of hook definitions (adapters are callers' code, exceptions are
caught and re-typed at 2495-2500).

**4. Runtime import?** None. Stdlib only (`base64`, `hashlib`, `json`, `re`, `dataclasses`,
`enum`, `typing`). Fully isolated/additive.

**5. Verdict: GENUINE_BACKEND.**
Top 3: (1) MEDIUM wrong exception type on malformed workflow node `e7_runtime_backend.py:2625-2632`;
(2) LOW incomplete credential-reference check `e7_runtime_backend.py:2096-2105`;
(3) LOW unsynchronized CAS/flow state `e7_runtime_backend.py:2423-2432,2084-2105`.

---

## 5. `v_series_backend.py` + `test_v_series_backend.py`

**1. Real behavior?** Yes — 24 feature surfaces with real algorithms:
- `score_approval`/`approval_review` (252-317) compute wildcard coverage, max risk, broadness and
  narrowing suggestions; `PendingQueue` + `no_retry_instruction` (334-403) are a real
  reject-cascade state machine with redacted, deduplicated model-facing output;
- `CorrelationIdStore.rotate/rotate_session` (426-465) generates opaque, namespaced, rotating IDs;
  `build_mcp_meta` (468-483) emits `_meta` only for advertising servers and never a session ID;
- `evaluate_case`/`score_model` (536-574) implement the 3-answer sycophancy evaluation;
- `validate_adapter`/`WorktreeLock`/`adapter_run_plan`/`verification_gate` (625-724) implement
  adapter policy, a one-writer lock and mandatory diff+test verification;
- `ConfirmationRule.matches`/`ConfirmationGate` (734-832) with one-time codes and pre-approved
  rules; `find_duplicate_blocks` with normalized-line n-gram hashing (872-895), `find_dead_features`
  (912-939); `compute_surface` with deny-wins/default-deny (1011-1029), `diff_surfaces`
  (1052-1062); `diagnose_rules` with match-set shadowing/duplicate/broad-allow analysis (1107-1144);
  `make_provenance`/`verify_provenance` (1173-1210); `assemble_prompt`/`taint_report` (1272-1303);
  `run_plugin_conformance`/`plugin_verified_gate` (1382-1405); `diff_to_hunks`/`apply_approved_hunks`
  (1476-1525); AST/JS capability scanners (1587-1645); `verify_doc_fences` with a caller-supplied
  mock runner (1747-1788); `make_snapshot`/`verify_snapshot` with recursive scrubbing (1812-1839);
  `parse_event_source`/`generate_json_schema` (1865-1907); `lint_seams` (1980-2002);
  `requires_isolation`/`isolation_plan`/`isolation_gate` (2030-2086); deterministic
  `simulate_pipeline`/`check_fuzz_invariants` (2136-2209); `verify_before_upload`/
  `verify_after_upload`/`release_publish_report` (2284-2358); `BudgetTable`/`countdown` (2488-2530);
  `check_fix_commit`/`postmortem_gate` (2596-2630).

**2. Tests exercise behavior?** Yes — 84 tests + 49 subtests. Examples: secret redaction and
canonical hashing (45-60), approval scoring/known-broad patterns (116-146), reject cascade +
no-retry text (160-194), correlation rotation/retirement (197-225), sycophancy violation reasons
(237-274), adapter policy and lock ownership (296-319), rule diagnostics kinds (435-458),
taint injection detection (494-514), hunk approval (557-579), capability scan findings (586-611),
fuzz invariants (notably 621+), publish verifier, budget table, postmortem gate. P0 baseline rows
are verified against real `keel.invariant_contracts` in `test_v_series_backend.py:82-114`.

**3. Real defects:**
- **MEDIUM** — `WorktreeLock.release` (v:659-664): the `token` parameter is validated as a string
  but **never compared** with the stored owner/token. Probe: after `tok = acquire('wt','agent-a')`,
  `release('wt','totally-wrong-token')` succeeds and clears the lock. The `locked()` context
  manager (666-673) likewise releases unconditionally in `finally`, so a re-entrant/concurrent
  holder can free a re-acquired lock. This breaks the documented "one-writer-per-worktree" invariant.
- LOW — `redact_text` (v:110-118, pattern at 100): the `api_key|token|secret|password` assignment
  pattern uses `\S+`, so multi-word values are only partially redacted. Probe:
  `redact_text('token=super secret value here')` → `'token=[REDACTED] secret value here'`.
  Same weakness class flagged for other groups; affects every error message routed through
  `ContractValidationError` (91-93).
- LOW — `CorrelationIdStore._retired` (v:431, 441) grows without bound; long-lived sessions with
  frequent rotations accumulate retired IDs in memory. No eviction/TTL exists.

No eval/exec (scanners only inspect AST/text), no filesystem/network, no mutable-default bugs
(all defaults are tuples or `()`).

**4. Runtime import?** None. Stdlib only (`ast`, `contextlib`, `fnmatch`, `hashlib`, `json`, `re`,
`dataclasses`, `enum`, `typing`). Fully isolated/additive; the test imports
`keel.invariant_contracts` and `keel.Event` only for P0 baseline verification (test:23, 692).

**5. Verdict: GENUINE_BACKEND.**
Top 3: (1) MEDIUM token ignored on lock release `v_series_backend.py:659-664`;
(2) LOW partial multi-word secret redaction `v_series_backend.py:100,110-118`;
(3) LOW unbounded retired-correlation-ID set `v_series_backend.py:431,441`.

---

## Recommended follow-ups for the lead

1. Fix the two MEDIUM defects before claiming these rows `verified`:
   `v_series_backend.WorktreeLock.release` token check, `e3_backend.SubagentManager.register_provider`
   duplicate guard, and `e7_runtime_backend.Workflow.__post_init__` validation order.
2. Standardize secret redaction across groups: replace `\S+` assignment values with a pattern that
   consumes the rest of the line/value (affects `v_series_backend.py:100` and the equivalents in
   other groups already flagged by Group 4).
3. Decide centrally whether additive backends should be wired into the runtime; as committed, only
   E3 touches real runtime contracts, and the others are standalone libraries with their own tests.
