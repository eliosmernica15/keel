# Addendum 7 — Tool-pipeline contracts: implementation evidence

Branch: `agent/a2-tool-contracts` (worktree `.../worktree/addenda/tool-contracts`)
Baseline: `4deb532` (full implementation tree of `fbf0135`), read-only.
Source of requirements: `plan-extract/addendum7.json` →
`metadata.tool_contracts` (20 named contracts), plus evidence rows E1.1–E1.21,
E2.1–E2.5, E4.1/E4.2/E4.9–E4.12 and V24–V28.

This workstream is **additive**. No existing file was edited. The canonical
implementation lives in a new module and is exercised by a new, permanent
contract-regression test file. Integration into the live runtime is a separate
lead decision (exact changes listed at the end).

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/tool_contracts.py` | Canonical implementation of all 20 contracts (stdlib only). |
| `keel/tests/test_tool_contracts.py` | 60 permanent contract tests, one group per named contract. |
| `master-plan-v6-tool-contracts-evidence.md` | This document. |

## Contracts implemented

| # | Named contract | Primary symbols | Tests |
| --- | --- | --- | --- |
| 1 | `canonical_output_and_pure_renderer` | `ToolSpec.output_schema`, `ToolSpec.renderer`, `ToolRegistry.register` (registration gate), `success_result`, `safe_render` | `test_contract1_*` (3) |
| 2 | `model_facing_schema_field_restrictions` | `ToolRegistry.schemas()` — allowlist `{name, description, input_schema}`, deep copies | `test_contract2_*` (2) |
| 3 | `single_schema_vocabulary_and_unsupported_keyword_rejection` | `ALLOWED_SCHEMA_KEYWORDS`, `validate_schema_definition`, `validate_value`, `infer_schema_type`, `to_jsonable` | `test_contract3_*` (5) |
| 4 | `argument_snapshotting_and_immutability` | `ArgsSnapshot`, `deep_freeze`, `snapshot_args`, `MappingProxyType`/tuple freeze | `test_contract4_*` (3) |
| 5 | `pre_execute_decision_model` | `Decision`, `DecisionKind`, `resolve_pre_decision`, `pre_decision_to_error` | `test_contract5_*` (3) |
| 6 | `monotonic_guards_deny_cannot_become_allow` | `combine_decisions`, `apply_guards` (severity-ranked, order-independent fold) | `test_contract6_*` (2) |
| 7 | `post_execute_decisions_dlp_value_vs_display` | `PostDecision`, `PostAction`, `apply_post_hooks`, `dlp_replace_value`, `dlp_block`, `replace` | `test_contract7_*` (5) |
| 8 | `around_dispatch_timeout_and_cancellation_propagation` | `CancelSignal`, `FusedCancelSignal`, `fuse`, `apply_wrappers`, `execute_tool` timeout loop | `test_contract8_*` (4) |
| 9 | `concurrency_classification_barriers_and_bounded_parallel_execution` | `ConcurrencyClass`, `classify`, `execute_batch`, bounded pool + exclusive barriers | `test_contract9_*` (4) |
| 10 | `deterministic_ordering_and_executor_contract` | `execute_batch` (indexed outcomes, drain-on-settle), `ToolBatchExecutionError`, `ABORTED_BEFORE_DISPATCH` | `test_contract10_*` (2) |
| 11 | `per_agent_restriction_intersection` | `ToolRestriction`, `intersect_restrictions`, `tool_admitted`, `admission_decision` (shared by schemas + execution), `ToolSpec.scoped` | `test_contract11_*` (3) |
| 12 | `conditional_tool_activation` | `ToolActivation`, `StepAdmission` (`when` once per step, `dispose` blocks late results) | `test_contract12_*` (1) |
| 13 | `stable_error_codes` | `ToolErrorCode`, `MANDATORY_ERROR_CODES`, `ToolError`, `failure_display`, `ToolResult.error_info` | `test_contract13_*` (2) |
| 14 | `typed_expected_failures` | `ToolError` (typed) vs domain values returned as `ok=True` | `test_contract14_*` (1) |
| 15 | `turn_completion_and_deferred_context` | `ToolContext.conclude_turn`, `defer_context`, `forward_conclude_turn` | `test_contract15_*` (2) |
| 16 | `typed_source_kind_for_injected_context` | `SourceKind`, `InjectedMessage`, `admit_injection`, `ToolContext.inject` | `test_contract16_*` (2) |
| 17 | `long_running_background_lifecycle` | `BackgroundHandle`, `BackgroundJob` (sync `cancel`, non-rejecting `done` after cleanup, `output_source`), `JobManager`, `call_cancel_stops_waiting_not_work` | `test_contract17_*` (2) |
| 18 | `programmatic_tool_call_mode` | `PTCExecutor`, `_ToolProxy` (`await tools.name(args)`), `PTCError` (limited: name/tool/message), reserved `run_code`, `PTCDispatchLog`, executor-owned prompt sections | `test_contract18_*` (5) |
| 19 | `ui_presentation_purity_and_card_contract` | `Card`, `CardKind`, `IconKind`, `present_call`, `present_result`, `presentation_meta`, generic fallback | `test_contract19_*` (4) |
| 20 | `contract_tests_and_verification` | `ToolRegistry.dispose` (HMR-safe), `conformance_check`, `fuzz_tool`, `request_reconstruction_byte_compare` | `test_contract20_*` (4) |

Total: **60 tests**, all passing.

## Design decisions worth the lead's attention

1. **Monotonicity is structural.** `combine_decisions` ranks
   `ALLOW < ASK < CANCEL < DENY` and always keeps the more restrictive decision;
   `apply_guards` additionally strips `allow_once` from any guard result when
   the base is already restrictive. Listener order cannot turn a denial into an
   allow (E1.6).
2. **ASK resolution is fail-closed.** Only an explicit `Decision.allow(...)` with
   `allow_once=True` from the approval responder upgrades ASK. A missing
   responder → `APPROVAL_UNAVAILABLE`; an agentless call (`agent_id=None`) →
   `TOOL_CONTEXT_UNAVAILABLE` (E1.5 / W3.12 / E7.19).
3. **Content replacement is never confidentiality.** `replace_content` changes
   only `ToolResult.display`; `replace_value` and `block` change the actual
   `value` that both the renderer and programmatic callers see. DLP helpers use
   the latter, satisfying conflict C-13.
4. **Cancellation cannot be removed.** `apply_wrappers` re-fuses the caller's
   signal with any wrapper-provided signal *and* with the timeout signal; a
   wrapper that returns a fresh never-cancelled signal cannot drop a caller
   cancel. Handlers are cooperative (`ctx.cancel`) and the executor context
   manager drains all started work before returning (E1.8/E1.9/E1.11).
5. **Schema vocabulary is an explicit allowlist.** Unknown JSON Schema keywords
   (`$ref`, `allOf`, `format`, callbacks, internal metadata fields, ...) raise
   `SchemaError` at registration. Object nodes must declare
   `additionalProperties` explicitly. `oneOf` requires exactly one matching
   branch at runtime.
6. **Stable codes are enum-owned.** The 11 mandated codes plus 5 additional
   stable codes needed for infra conditions (`BATCH_EXECUTION_ERROR`,
   `TOOL_EXECUTION_ERROR`, `MODEL_DIRECT_CALL_DENIED`, `RESERVED_TOOL_NAME`,
   `INJECTION_REJECTED`) are all members of `ToolErrorCode`. Raw reasons are
   stored only in `ToolResult.durable_reason`/`ToolError.reason`, never in
   model-facing `display`.
7. **Admission decision is shared.** `admission_decision(spec, restriction)` is
   called by both `ToolRegistry.schemas()` and `execute_tool()`, so a tool
   hidden from the declaration is also denied when invoked directly; scoped
   registrations (`ToolSpec.scoped=True`) are exempt in both paths.

## Test results

Command (from worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_tool_contracts.py']))"
```

Result: `60 passed` (repeated 5× — stable, no timing flake). Python 3.11.9,
pytest 9.0.2.

## Exact integration changes needed by the lead

This module is deliberately not wired into `keel/session.py`,
`keel/tools/registry.py`, `keel/runner.py` or `keel/permissions.py`. To adopt it,
the lead should make these changes (none are required for the tests above to
pass):

1. **`keel/tools/registry.py`** — either replace `Tool`/`ToolRegistry` with
   `ToolSpec`/`ToolRegistry` from `keel.tool_contracts`, or add an adapter:
   - `Tool` gains `output_schema`, `renderer`, `concurrency`, `timeout_s`,
     `scoped` and a default output schema for legacy tools;
   - `ToolRegistry.register()` calls `validate_schema_definition` on both
     schemas and rejects duplicate/reserved names;
   - `ToolRegistry.schemas()` keeps the 3-key allowlist (already true today) and
     accepts `restriction=`.
2. **`keel/session.py` / dispatch path** — route tool calls through
   `execute_tool(registry, name, args, agent_id=..., cancel=...,
   approval_responder=..., restriction=...)` instead of calling the handler
   directly. Feed `result.value` into `render_success`/`render_failure` in
   `keel/toolresult.py` and `result.display` into model-facing content. Use
   `result.durable_reason` only in durable logs.
3. **`keel/permissions.py`** — reuse `Decision`/`resolve_pre_decision` as the
   pre-execute gate (or adapt `permissions.Decision` into the 4-kind model), and
   register the existing Tier-2 checks as monotonic `guards` via
   `ToolRegistry.add_guard`. The existing `ask` path must provide an
   `approval_responder`, otherwise calls fail closed with
   `APPROVAL_UNAVAILABLE`.
4. **Agent frontmatter (`tools.allow` / `tools.deny`)** — build a
   `ToolRestriction` per scope, intersect with `intersect_restrictions`, and pass
   the result to both `schemas(restriction=...)` and `execute_tool(...)`.
5. **Parallel tool-call scheduler** — replace ad-hoc parallel dispatch with
   `execute_batch` and set `max_parallel` from `maxParallelToolCalls`.
6. **PTC / Code Mode** — instantiate `PTCExecutor` where `run_code` is exposed,
   register the `ptc-dispatch-log` hook for durable log shortening, and call
   `dispose()` with the executor's lifetime.
7. **Registries lifecycle** — call `ToolRegistry.dispose()` (and `JobManager.dispose()`)
   on scope unload/HMR to satisfy the per-registry unload test (E4.1).

No change to `keel/tool_json.py` is required: the new module has its own strict
schema vocabulary and leaves the tolerant local-model repair path untouched.
