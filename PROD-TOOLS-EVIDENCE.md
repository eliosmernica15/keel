# PROD-TOOLS-EVIDENCE — tool execution & bounded delegation

- Branch: `agent/prod-tools`
- Candidate HEAD audited: `e6e7efc` (backend-only production candidate)
- Owned files changed: `keel/src/keel/tool_contracts.py`, `keel/tests/test_prod_tools.py` (new), this evidence file.
- No frontend changes, no other files touched, no push.

## 1. Tool lifecycle audit

| Stage | Before | After / evidence |
|---|---|---|
| Registration | Schema vocabulary, mandatory output schema, permission enum, timeout and duplicate/reserved-name checks present. `replace=True` could **widen** a tool's permission class. | Added `PERMISSION_RANK` monotonic registration gate; replacement may only keep or narrow the class. `test_replace_cannot_widen_permission_class`. |
| Discovery | `ToolRegistry.schemas()` projected name/description/input_schema and used `admission_decision` directly. | Now calls the same `ToolRegistry.authorize()` choke point as execution, with `agent_id`/`scope`, so discovery and permission agree. `test_authorization_governs_discovery_and_execution`. |
| Schema validation | Allowlisted keywords; objects must declare `additionalProperties`. | Unchanged, plus `const`/`enum` now require JSON type identity (Python `True == 1` no longer satisfies `const: 1`). `test_const_and_enum_do_not_confuse_bool_with_integer`. |
| Input validation | Deep-copy via `to_jsonable`, then `validate_value`. | Bounded copy: depth 32 / 10 000 nodes / 100 000 string chars; hostile nesting and oversized payloads settle as typed `ARGS_RESOURCE_LIMIT` instead of `RecursionError`/OOM escaping the pipeline. `test_deeply_nested_args_cannot_escape_typed_pipeline`, `test_oversized_string_and_array_are_typed_failures`. |
| Permission checks | `spec.permission` was **decorative**: `base = Decision.allow(...)` regardless of the agent's grants. | `PermissionPolicy` is the centralized authority (unknown agent ⇒ no permissions); `ToolRegistry.authorize()` is the single choke point for discovery, direct calls, batches, PTC and delegation. `test_permission_class_is_enforced_by_central_policy`. |
| Approval | `Decision.allow(allow_once=True)` from a responder upgraded ASK every time — unlimited replay for identical args. | `ApprovalLedger` (per registry) consumes plain allow-once decisions; `ApprovalGrant` is an explicit single-use ticket bound to name + canonical args + agent. Replay ⇒ `APPROVAL_REPLAY_REJECTED`. Cancelled calls no longer consume tickets. `test_approval_is_single_use_and_bound_to_args`, `test_explicit_grant_binds_agent_and_args`. |
| Timeout / cancellation | Cooperative timeout/cancel with fused signals and a pre-dispatch gate. | Preserved; added an early cancel gate before approval so an aborted call cannot consume an approval. `test_timeout_is_typed_and_handler_observes_cancellation`, `test_cancelled_batch_and_ptc_never_dispatch`. |
| Output validation | Canonical value validated against output schema; renderers pure. | Unchanged; still typed `INVALID_TOOL_OUTPUT`. |
| Error classification | Stable codes incl. the 11 mandated Addendum 7 codes. | Added `PERMISSION_DENIED`, `APPROVAL_REPLAY_REJECTED`, `ARGS_RESOURCE_LIMIT`, `DELEGATION_DEPTH_EXCEEDED`, `DELEGATION_LIMIT_EXCEEDED`. Durable reasons remain out of model-facing display. |
| Audit event / persistence | `ToolResult.audit` existed, but early failures had no audit and post-hook BLOCK discarded the trail; no registry-level record. | `execute_tool` is now a thin audited wrapper: every outcome emits exactly one durable `AuditEvent(name, agent_id, ok, code, reasons)` into `ToolRegistry.audit_log`, cleared on `dispose()`. BLOCK scrub context/meta/child results and preserves audit. `test_every_outcome_emits_exactly_one_audit_event`, `test_blocked_result_scrubs_context_and_keeps_audit`. |

## 2. Delegation audit

| Property | Before | After / evidence |
|---|---|---|
| Bounded subagents | No delegation primitive in `tool_contracts`. | `DelegationPolicy(max_depth, max_children, max_concurrent)` + `AgentScope` + `DelegationManager`. |
| Parent/child permission inheritance | n/a | `AgentScope.child()` only accepts a subset of parent permissions; misses → `PERMISSION_DENIED`. Child `authorize()` ignores `ToolSpec.scoped` self-exemption. `test_child_cannot_gain_privileges`. |
| Recursion prevention | n/a | Depth cap and lineage/cycle check; violations become typed `DELEGATION_DEPTH_EXCEEDED` results (also inside nested batches). `test_recursive_delegation_cap`. |
| Concurrency limits | n/a | One bounded pool per delegation batch; observed handler concurrency never exceeds `max_concurrent`. `test_concurrent_children_are_bounded`. |
| Child count cap | n/a | Excess tasks get typed `DELEGATION_LIMIT_EXCEEDED` outcomes instead of being run. `test_child_count_cap_produces_typed_failures`. |
| Result aggregation | n/a | `DelegationReport` preserves input order, one typed outcome per task, plus `failures` and checkpoint id; nested outcomes attached via `ToolResult.child_results`. |
| Failure propagation | n/a | Child exceptions become `TOOL_EXECUTION_ERROR` with the raw reason durable-only; partial failures don't discard sibling successes. `test_partial_failure_aggregation_and_failure_propagation`. |
| Checkpoint / recovery | n/a | Deterministic checkpoint keys; replay returns recorded outcomes without re-executing; `force + resume_failed` retries only failed children. `test_checkpoint_recovery_does_not_reexecute`, `test_resume_retries_only_failed_children`. |

## 3. Centralized authorization — bypasses found and fixed

Before this change, **four alternate transports** could evade a caller's `ToolRestriction`, and none consulted a permission policy:

| Transport | Bypass before | Fix |
|---|---|---|
| `execute_tool` (direct) | `base` allowed every permission class; restriction was a caller-owned optional arg. | Fold `registry.authorize(spec, agent_id, restriction, scope)` into the monotonic pre-decision. |
| `execute_batch` | No `restriction`/`scope` parameter at all; submitted calls dropped them. | Added `restriction`/`scope` params and forwards them to `execute_tool`. |
| `PTCExecutor.call` / `tools.name(...)` | Used bare `execute_tool(registry, name, args)`; ignored restriction, cancel, scope and approval. | All PTC paths use `_dispatch()`, which forwards restriction/scope/cancel/approval to `execute_tool`. |
| `PTCExecutor.model_direct_call` | Same bypass when `selected=False`. | Uses `_dispatch()`; when `selected=True` it still returns `MODEL_DIRECT_CALL_DENIED` before dispatch. |
| `StepAdmission` | `enforce()` was manual; a direct/batch/PTC call could skip it. | Added `StepAdmission.guard()` + `attach(registry)` registering it as a monotonic registry guard. |
| `ToolSpec.scoped=True` | Tool self-declared exemption from any deny list. | Under a `PermissionPolicy`, scoped exemption requires explicit `trust_scoped=True`; `AgentScope` never trusts it. |

Tests: `test_ptc_proxy_cannot_bypass_policy`, `test_ptc_cannot_bypass_call_restriction`, `test_execute_batch_honours_restriction_and_policy`, `test_step_admission_guard_blocks_every_transport`, `test_scoped_flag_cannot_self_exempt_under_policy`.

## 4. Confirmed defects fixed (high/medium)

1. **HIGH** — no permission-class enforcement (central policy missing). Fixed with `PermissionPolicy` + `ToolRegistry.authorize`.
2. **HIGH** — unlimited approval replay across calls/transports. Fixed with `ApprovalLedger` + `ApprovalGrant` single-use tickets.
3. **HIGH** — four alternate transports dropped restrictions; step admission was voluntary. Fixed as listed in §3.
4. **MEDIUM/HIGH** — `scoped=True` self-exemption from deny lists. Fixed under policy and child scopes.
5. **MEDIUM** — unbounded argument snapshot could raise `RecursionError` outside the typed pipeline and accept multi-megabyte payloads. Fixed with bounded `to_jsonable` and typed `ARGS_RESOURCE_LIMIT`.
6. **MEDIUM** — `const`/`enum` bool/int type confusion. Fixed with JSON type identity.
7. **MEDIUM** — post-hook BLOCK discarded the audit trail and retained attached context built from the blocked value. Fixed (audit preserved, context/meta/child results scrubbed).
8. **MEDIUM** — permission widening via `register(replace=True)`. Fixed with rank monotonicity.
9. **MEDIUM** — no registry-level durable audit event for early failures. Fixed with audited `execute_tool` wrapper + `AuditEvent`.

## 5. Known limitations (documented, not silent)

- Timeouts are **cooperative**. A handler that ignores `ctx.cancel` cannot be forcibly killed in-process; `conformance_check` requires declared-timeout handlers to quiesce within 0.5 s after cancel. This was already true before this change.
- Legacy registries without `set_policy()` keep the additive Addendum 7 admission behaviour for compatibility (`test_tool_contracts.py` depends on it). Production scopes must install a `PermissionPolicy` (fail closed for unknown agents) to get permission-class enforcement.
- `trust_scoped=True` is an explicit opt-in for legacy scoped registrations; it must not be enabled for untrusted tool registrations.

## 6. Verification

Required command (`test_fleet_agents.py` is absent in this candidate, so it is skipped):

```
python -c "import sys,pytest,pathlib; sys.path.insert(0,'keel/src'); names=['keel/tests/test_prod_tools.py','keel/tests/test_tool_contracts.py','keel/tests/test_fleet_agents.py']; names=[n for n in names if pathlib.Path(n).exists()]; raise SystemExit(pytest.main(['-q']+names))"
```

Result: **91 passed** (25 new `test_prod_tools.py` specs + 66 existing `test_tool_contracts.py` specs; 1 collection-free skip of the absent fleet file).

Additional regression: `test_tool_contracts_bridge.py`, `test_tool_registry.py`, `test_subagent.py`, `test_trust_tools.py`, `test_fleet.py` — **40 passed**.

All new specs were first run against candidate `e6e7efc` and failed (21 failures covering the defects above), then passed after the fixes.
