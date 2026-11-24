# V-series backend — implementation evidence (b1-v assignment)

**Branch:** `agent/b1-v`  **Baseline:** `982335d`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\backend\b1-v`

## 1. Scope and registry reading

`PLAN-INDEX.json` contains 31 `V*` rows: 7 `verified` (P0) and 24
`not_started` (22 P1, 2 P2). The assignment was to implement the 24
`not_started` rows as a stdlib-only, real-behavior backend, and to verify and
document the seven P0 rows already implemented in `keel.invariant_contracts`.

All 24 full registry rows were read in full before implementation (their
`feature`, `detail`, `acceptance_criteria`, `source_document` and `section`
fields). They are listed in §3 with their classification and the exact
contract surface that implements each one.

`PLAN-INDEX.json` and all existing files were **not** edited. No row status
was changed here. This evidence does not claim that UI buttons, real
containers/subprocesses, live CI wiring, real model evaluations or signed
release decisions were shipped; it claims a deterministic, fail-closed
descriptor/checker layer that those deliverables can consume.

## 2. Files owned (only these were added)

* NEW `keel/src/keel/v_series_backend.py` (2,630 lines, stdlib-only)
* NEW `keel/tests/test_v_series_backend.py` (84 adversarial tests)
* NEW `master-plan-v6-v-series-backend-evidence.md` (this file)

No other file in the worktree was created or modified.

### Design invariants

* No imports of `keel` modules, `socket`, `subprocess`, `os`, `pathlib`,
  `http`, `urllib`, `time`, `datetime`, `asyncio` or `random`; a source-AST
  test enforces this, and a second AST test forbids `open`/`exec`/`eval`/
  `__import__`/`compile` calls. There is no file I/O, network, process,
  wall clock or chance. Every input is caller-supplied.
* Fail closed: malformed/unknown values raise `ContractValidationError`
  (whose message is scrubbed through `redact_text`) or produce a failing
  result, never a silently permissive one.
* All fingerprints are canonical JSON (sorted keys, compact separators,
  UTF-8) hashed with SHA-256; credential-looking literals are redacted from
  errors, reasons, snapshots and no-retry instructions.

## 3. Classification and implementation map (24 owned rows)

Classification key:
**P** = pure backend contract (descriptor / checker / simulator / projection);
**UI/CI seam** = the product deliverable named in the plan (button, real
child process, CI job) is explicitly **not** claimed — the module provides
the deterministic layer it would call.

| ID | Pri | Registry feature (full text) | Class | Contract surface in `keel.v_series_backend` | Tests |
| --- | --- | --- | --- | --- | --- |
| V3 | P1 | Broadness scoring for saved "always" approvals: flag patterns like bare `*` or `rm *`, show last-used date, offer narrowing (e.g., command prefix to exact subcommand). Detail: score = wildcard coverage vs action risk table; surfaced in permission review screen (X5.7). | P + UI/CI seam | `ApprovalScore`, `score_approval`, `approval_review`, `KNOWN_BROAD_PATTERNS`: wildcard coverage over a caller-supplied `(action, resource)` universe × action-risk table → 0..100 score, `broad` flag, echoed `last_used`/staleness, concrete narrowing suggestions | `TestV3ApprovalBroadness` (5) |
| V4 | P1 | Reject-cascade UX: a "Reject all pending" button plus a per-request reject, mirroring W3.9; rejected reasons passed to the model as a no-retry instruction. Detail: UI + Y2.7 behavior. | P + UI seam | `PendingQueue.add/reject/reject_all/resolve/snapshot`, `RejectionRecord`, `no_retry_instruction`: deterministic per-request and cascade rejection, deduped/scrubbed model-facing no-retry text | `TestV4RejectCascade` (3) |
| V6 | P1 | Opaque per-server correlation IDs for MCP (instead of session ids): random value per (session, server), rotated per session, never reused across servers. Detail: generate on connect; store in memory only; send in `_meta` only if the server advertises support. | P | `CorrelationIdStore.rotate/rotate_session/current/is_retired`, `CorrelationId`, `build_mcp_meta`, `assert_no_session_id`, `CORRELATION_META_KEY`: opaque SHA-256 values namespaced by (session, server, generation, caller token), retired generations rejected, `_meta` emitted only on advertisement, session-id leakage fails closed | `TestV6CorrelationIds` (3) |
| V7 | P1 | Sycophancy/capitulation eval: scripted multi-turn tests where a fixture "user" pushes back without new evidence; pass = model keeps correct answer; plus a "new evidence" case where it should change. Detail: add to local eval harness; score per model. | P + eval seam | `SycophancyCase`, `make_case`, `evaluate_case`, `CaseResult`, `score_model`, `sycophancy_report`: evaluates the three supplied answers, detects capitulation/repeating an unsupported claim/failure to update on new evidence, per-model score | `TestV7SycophancyEval` (4) |
| V8 | P1 | External specialist adapters: delegate a task to a coding CLI the user already has installed (any tool with a headless mode) as a child agent, with "one writer per working tree" locking and mandatory diff/test verification after. Detail: generic adapter spec; adapters ship disabled; never bundle third-party CLIs; respect each tool's terms; run inside Keel worktree + permission gate. | P + process seam | `AdapterSpec`/`make_adapter_spec`/`validate_adapter` (disabled, unbundled, no shell metacharacters, PATH-only executable, worktree-relative paths), `WorktreeLock` (one writer, context-managed), `adapter_run_plan` (non-executing), `verification_gate` (diff inside allowed paths + tests must pass) | `TestV8SpecialistAdapters` (4) |
| V9 | P1 | Remote-initiated action confirmation: any task started from a channel (Telegram/email/webhook) that would run shell/edit/send actions requires a one-time code confirmation in the desktop app (or a pre-approved rule), per W7.17. Detail: pending-turn state with "needs local confirmation" status and a notification (X8.5). | P + UI seam | `ConfirmationGate`, `ConfirmationRule`, `make_confirmation_rule`, `ConfirmationRequest`, `needs_local_confirmation`, `confirmation_notification`: shell/edit/send only, pre-approved matcher short-circuit, one-time hashed code (replay rejected), notification payload | `TestV9RemoteConfirmation` (3) |
| V10 | P1 | Duplicate-code and dead-feature detector for the builder: CI reports duplicate blocks (W1.7) and any plan ID with code but no test/evidence. Detail: combine jscpd-style tool + `PLAN-INDEX.json` check script. | P + CI seam | `find_duplicate_blocks` (normalized N-line window hashing across/within sources), `find_dead_features` (code present but no test and/or no evidence), `DuplicateBlock`, `DeadFeature`, `builder_hygiene_report` | `TestV10BuilderHygiene` (3) |
| V11 | P1 | Per-agent "tool surface report": shows exactly which tools, MCP servers, skills and subagents an agent can reach after merges, with the rule that allowed each. Detail: computed from merged config + permission matcher; diff view when an extension update changes it (extends C8.5). | P + UI seam | `SurfaceRule`/`make_surface_rule`, `ToolSurface`, `compute_surface` (deny wins, default deny, first allow attributed), `SurfaceDiff`/`diff_surfaces` (added/removed/rule changed) | `TestV11ToolSurface` (3) |
| V12 | P1 | Config "doctor" for rule conflicts: detects rules that can never match (shadowed by a later rule), duplicate rules, and broad allows after specific denies. Detail: static analysis over ordered rules; run on save and in `keel doctor`. | P + CLI seam | `ConfigRule`/`make_config_rule`, `RuleDiagnostic`, `diagnose_rules` (exact match over a caller-supplied finite universe: duplicate, shadowed, broad-allow-after-deny), `doctor_report` | `TestV12RuleDoctor` (3) |
| V13 | P1 | Release provenance page in-app listing for the running build: version, commit-less build id, signing key fingerprint, manifest hash, SBOM link. Detail: reads embedded manifest; ties to C11.6. | P + UI seam | `ReleaseProvenance`/`make_provenance` (rejects git-SHA build ids, validates fingerprint/hash/link), `verify_provenance` (manifest hash re-computation), `provenance_page` (display projection) | `TestV13ReleaseProvenance` (2) |
| V14 | P1 | Prompt-assembly viewer for subagents/commands (what system prompt, instructions, skills and MCP instruction blocks a child actually received), with taint labels. Detail: extends the Context inspector; store assembled prompt hash per run. | P + UI seam | `PromptBlock`/`make_prompt_block` (kind + taint vocabularies), `assemble_prompt` (ordered text + canonical per-run hash), `taint_report` (external/plugin/tool-output taint injected into system/instruction/MCP blocks), `prompt_viewer_report` | `TestV14PromptAssembly` (3) |
| V15 | P1 | Local "plugin conformance kit": a checklist-runner that verifies a plugin cleans up on unload, respects permission denials, declares all network hosts, and survives safe-mode boot. Detail: uses V1 + the mock host (X6.1); required before a plugin is marked "verified" in the private index. | P + index seam | `_PLUGIN_CHECKS` (4 checks), `run_plugin_conformance`, `PluginConformanceReport`, `plugin_failing_observations` (one failing fixture per check), `plugin_verified_gate` (conformance + valid status transition) | `TestV15PluginConformance` (3) |
| V17 | P1 | Disposable-sandbox run mode: run the agent's tool execution in a container with a copy-on-write view of the project, then show a diff and apply only approved hunks back. Detail: Podman/Docker optional; overlay or copy; reuse diff review dock; falls back to a temp-copy mode without containers. Never required. | P + runtime seam | `SandboxMode`, `SandboxPlan`, `choose_sandbox_mode` (container+COW when a runtime is available, temp-copy fallback, rejects `required=True` with no runtime), `Hunk`/`diff_to_hunks`, `apply_approved_hunks` (approved-only whole-file content, unknown id fails closed), `sandbox_run_report` | `TestV17DisposableSandbox` (3) |
| V18 | P1 | Plugin static capability scan: before enabling a plugin, scan its Python/JS for subprocess, socket, ctypes, `eval/exec`, file writes outside its data dir, and compare with its declared permissions; mismatch blocks enabling. Detail: AST scan; show findings in install dialog; best-effort and labeled as such (not a sandbox). | P + install-dialog seam | `scan_python_source` (stdlib AST: imports, eval/exec/compile, process calls, write-mode `open`, write methods), `scan_javascript_source` (regex: child_process/net/eval/Function/fs writes), `writes_outside_data_dir`, `CapabilityFinding`, `CapabilityScanReport` (`best_effort=True`, `not_a_sandbox=True`), `compare_with_permissions` (parse errors and undeclared capabilities block) | `TestV18CapabilityScan` (3) |
| V19 | P1 | Executable docs: code fences in user and internal docs run in CI against the mock model; "paste of key types" verified against source. Detail: doc tool extracts fences tagged `keel-run` and `keel-type`; fail on drift. Mirrors D7.11 for Python. | P + CI seam | `Fence`/`parse_fences` (only `keel-run`/`keel-type`, `EXPECT:` line), `verify_doc_fences` (caller-supplied mock runner — doc code is never executed; `keel-type` normalized-text presence check; missing runner/expected/drift all fail) | `TestV19ExecutableDocs` (3) |
| V20 | P1 | Turn Replay Test builder: "save this turn as a test" button producing a snapshot fixture (recorded stream + expected log) for the builder's suite. Detail: export current turn's request/response stream with secrets scrubbed; stored under `tests/snapshots/`. | P + UI seam | `scrub_turn` (recursive redaction), `TurnSnapshot` (deterministic canonical render, `tests/snapshots/<slug>.json` path descriptor, SHA-256), `make_snapshot`, `verify_snapshot` | `TestV20TurnSnapshot` (2) |
| V21 | P1 | Contract generator for plugin events: generate docs and JSON Schemas for every event type from code annotations, and fail CI if an event lacks `mode` and payload docs (D6.3). Detail: Python `typing` + docstring parser; output into the private docs and plugin SDK. | P + CI seam | `EventSpec`/`parse_event_source` (AST parse of `class X(Event)` / `@event`, typed fields), `generate_json_schema`, `generate_event_docs`, `event_contract_gate` (fails on missing mode or payload docs) | `TestV21EventContracts` (2) |
| V22 | P2 | Seam checklist linter: verifies each registered seam has a definition, a default provider and at least one consumer, and flags single-role "seams" (D3.1). Detail: reads the service registry at test time. | P + test-time seam | `SeamRecord`/`make_seam`, `lint_seams` (definition, default provider membership, ≥1 consumer, ≥2 roles), `SeamIssue` | `TestV22SeamLinter` (3) |
| V23 | P1 | Run-in-isolation toggle for risky plugins: run plugin code in a separate subprocess with its own env, reachable only via the RPC bridge. Detail: same pattern as MCP workers (Master 11.9); default for unsigned plugins. | P + process seam | `PluginDescriptor`/`make_plugin_descriptor`, `requires_isolation` (unsigned/risky always isolated; only signed low-risk may opt out), `IsolationPlan`/`isolation_plan` (RPC-only, explicit env allowlist, no direct FS/net), `isolation_gate` | `TestV23IsolationToggle` (3) |
| V25 | P1 | Tool pipeline fuzzer: random args, random cancel points, injected failures; assert no hang, no leaked process/task, no orphan call without result, log stays replayable. Detail: Hypothesis-style + chaos tests with the fixture model server. | P + fuzz harness seam | `FuzzCase`/`make_fuzz_case` (caller-supplied deterministic corpus — no `random`), `simulate_pipeline` (validate/start/work/result → exactly one cleanup terminal), `FuzzEvent`, `check_fuzz_invariants` (hang, leaked process, orphan call, JSON round-trip replayability), `run_fuzz_corpus` | `TestV25PipelineFuzzer` (3) |
| V27 | P1 | Release publish verifier: before upload, cross-check manifest, sizes, SHA-256/512, signatures, version monotonicity, completion record; after upload, re-download and verify; metadata last. Detail: `keel-release verify` command used by CI and by the owner manually (E5.14/E5.15). | P + CLI seam | `Artifact`/`make_artifact`, `ReleaseBundle`/`make_release_bundle`, `verify_artifact_bytes`, `verify_before_upload` (optional caller-supplied signature verifier), `verify_after_upload`, `publish_steps` (metadata last), `release_publish_report` | `TestV27ReleaseVerifier` (3) |
| V28 | P1 | Error-code catalog generator: scan code for error constants, produce the troubleshooting pages and the typed-code list; fail CI if a raised code is undocumented. Detail: AST scan + template; ties to E1.14/E6.11. | P + CI seam | `ErrorCode`/`scan_error_codes` (AST: `E_*`/`ERR_*`/`ERROR_*`/`*_CODE`/`*_ERROR` string constants and raised string literals), `ErrorCatalog`/`generate_error_catalog` (markdown + typed list), `error_code_gate` (undocumented ⇒ fail) | `TestV28ErrorCatalog` (3) |
| V29 | P2 | Per-tool timeout and output-size budget table visible in the UI (and editable), with default values by tool class. Detail: config table; show countdown on running tool cards. | P + UI seam | `ToolClass` (5 classes), `DEFAULT_BUDGETS`, `BudgetOverride`/`make_budget_override` (hard caps), `BudgetTable.set/resolve/view`, `countdown` (caller-supplied elapsed time) | `TestV29BudgetTable` (2) |
| V30 | P1 | Postmortem template and counter: every escaped bug gets a numbered postmortem (cause, why tests missed it, new test) linked from the fixing commit. Detail: `docs/postmortem/NNNN-*.md` + CI check that a `fix:` commit tagged "escaped" references one (E4.9). | P + CI seam | `Postmortem`/`make_postmortem` (numbered path descriptor), `next_postmortem_number` (duplicate detection), `render_postmortem` (template), `check_fix_commit`, `postmortem_gate` (escaped fix without a valid reference fails) | `TestV30Postmortems` (2) |

## 4. P0 rows verified/documented (not reimplemented)

The seven P0 rows were implemented previously in `keel/src/keel/invariant_contracts.py`
and recorded in `master-plan-v6-invariant-contracts-evidence.md`. They are
carried here as `P0_BASELINE` documentation and re-verified by
`TestP0BaselineVerified` against their own module:

| ID | P0 surface | Verification in the new test suite |
| --- | --- | --- |
| V1 | `Scope`/`plugin_scope`/`register`/`Disposable`/`assert_no_leaks` | scope loads, disposes and leaves no live disposables |
| V2 | `Rule`/`Operation`/`simulate` winning-rule trace | Balanced preset denies `exec` with a non-empty denial reason |
| V5 | `Strictness`/`preset_rules` | preset construction and ordered evaluation |
| V16 | `GATE_CATALOG`/`check_gate`/`run_all_gates` | every gate rejects its own failing fixture |
| V24 | `CONFORMANCE_CHECKS`/`conformance_gate` | fully conformant metadata passes the gate |
| V26 | `reconstruct_request`/`verify_reconstruction` | fixture log rebuilds to its recorded hash and byte-matches the sent request |
| V31 | `TRANSPORT_CANDIDATES`/`spike_decision` | spike decision is complete |

## 5. Verification

Both commands were run from the worktree root with the required `sys.path`
insert.

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_v_series_backend.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
```

Result: **84 tests passed in ~0.40 s** (stdlib-only runner).

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_v_series_backend.py']))"
```

Result: **84 passed, 49 subtests passed in 5.71 s**.

### Adversarial coverage highlights

* **V3** bare `*` / `rm *` flagged, narrow approval unflagged, stale date shown,
  suggestions derived from the matched universe, four malformed inputs rejected.
* **V4** per-request reject and cascade reject, no-retry text deduped and
  credential-redacted, double reject / unknown id / duplicate add rejected.
* **V6** same token on two servers yields different opaque IDs; rotation
  retires the previous ID; no `_meta` without advertisement; no current ID
  yields empty `_meta`; session-id leakage raises; bad rotation inputs raise.
* **V7** punctuation-tolerant correct answer holds under unsupported pushback
  then updates on new evidence; capitulation and "no update" are both
  detected; wrong answer count/types and empty case fail closed.
* **V8** adapters ship disabled/unbundled; five policy violations are detected;
  worktree lock rejects a second writer and releases cleanly; the verification
  gate rejects no-diff, failing tests and out-of-scope changes.
* **V9** one-time code is single-use; pre-approved rule short-circuits;
  non-confirmable action, invalid rule action and duplicate rule ids fail closed.
* **V10** three overlapping duplicate windows found across two sources; code
  without test/evidence reported; non-mapping input rejected.
* **V11** deny wins and default-deny excludes unlisted items; first allow is
  attributed; diff reports added/removed/rule-changed; unknown kind rejected.
* **V12** duplicate, shadowed and broad-allow-after-deny diagnostics all fire;
  a clean rule set passes; malformed rules and universe fail closed.
* **V13** manifest hash re-computation passes/fails on tamper; git-SHA build
  id, non-hex fingerprint/hash and unsafe SBOM link are rejected.
* **V14** external taint injected into an MCP instruction block fails the
  viewer while the hash still matches; a clean prompt passes; wrong hash and
  unknown taint/kind fail closed.
* **V15** clean observations pass; each of the four checks has a failing
  fixture; a missing observation fails; the index gate rejects an invalid
  status transition.
* **V17** no-runtime fallback and required-runtime rejection; only the
  approved hunk is applied; unknown hunk id fails closed.
* **V18** all five capability families found in Python/JS; undeclared
  capabilities and writes outside the data dir block; a syntax error is a
  blocking `parse_error` finding; report is explicitly labeled best-effort.
* **V19** only tagged fences are parsed; a mock runner validates `keel-run`,
  normalized source presence validates `keel-type`; drift, missing runner and
  no fences all fail.
* **V20** secrets are recursively scrubbed from the snapshot render; the hash
  verifies and detects a one-byte change.
* **V21** typed fields become JSON Schema properties; a missing mode/payload
  doc fails CI; a syntax error fails closed.
* **V22** a valid seam passes; missing definition/default-provider membership/
  consumers and a single-role seam all produce issues.
* **V23** unsigned and risky plugins require isolation; the RPC-only plan with
  env allowlist passes; an in-process plan for an isolated plugin is rejected.
* **V25** normal, cancelled and injected-failure cases satisfy all invariants;
  a crafted orphan/leaked log is rejected; secret args and an empty corpus
  fail closed.
* **V27** pre- and post-upload verification pass on identical bytes; version
  regression, byte tamper, missing signature and missing completion record all
  fail; the signature hook is exercised; metadata is last in publish order.
* **V28** constants and raised literals are all catalogued; undocumented codes
  fail CI; a syntax error fails closed.
* **V29** class defaults, override precedence and sorted view; hard-cap and
  unknown-class inputs rejected; countdown expiry verified.
* **V30** numbering/template/render; escaped fixes with a missing or unknown
  postmortem reference fail; duplicate numbers rejected.

## 6. Limitations / integration seams

* Every feature is a descriptor, checker, simulator or projection over
  caller-supplied data. Real deliverables named in the plan — UI buttons and
  views, a real `keel doctor` / `keel-release verify` command, CI job wiring,
  actual containers or child processes, live channel notifications, real model
  evaluations and a private plugin index — are not implemented here.
* V25 accepts a caller-supplied deterministic corpus instead of a random
  generator so the suite stays reproducible and free of `random`/`time`;
  a Hypothesis-style generator can feed the same `make_fuzz_case` API.
* V19 never executes doc code: a caller-supplied mock runner decides pass/fail.
* V18 is explicitly labeled best-effort and not a sandbox; V23 describes an
  isolation plan but starts no subprocess.
* V13/V20/V30 produce filesystem-style path descriptors only; no file is
  created or read.
* No registry row status was changed; promoting these rows to `verified` is a
  lead/owner decision that must also account for the product seams above.
