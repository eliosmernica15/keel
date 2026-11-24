# Addendum 2 agents — implementation evidence (W2.1, W2.2, W2.3, W2.4, W2.6, W2.8, W2.9, W2.11)

**Branch:** `agent/a4-agents` · **Baseline:** `fa062a4`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\agents`

## Scope

Implemented the eight assigned P0 rows from the reconciled 865-row registry
(`PLAN-INDEX.json`). Feature text was read from that registry; no other
registry file was modified.

| ID | Registry feature | Implementation in `keel.agent_contracts` |
| --- | --- | --- |
| W2.1 | Markdown agent files with YAML frontmatter; nested path -> agent ID; global + project locations; body is the system prompt | `parse_agent_markdown`, `agent_id_from_path`, `discover_agent_files`, `load_agents`, `_split_frontmatter_safe` (strict stdlib subset parser, unsafe tags/expressions rejected) |
| W2.2 | Modes `primary`/`subagent`/`all`; subagents in child sessions with fresh context | `MODES`, `normalize_mode`, `can_be_primary`, `can_be_subagent`, `LifecycleContract`, `SubagentLaunch`, `build_subagent_launch` (parent history deliberately discarded) |
| W2.3 | Built-ins build, plan, general (no further subagents), explore (read-only incl. web); hidden maintenance agents | `builtin_agents`, `BUILTIN_IDS`, `HIDDEN_BUILTIN_IDS`, `BUILTIN_ROLE_MAP`, `is_hidden`, `is_user_selectable`, `model_role` |
| W2.4 | `steps` limit; final step removes tools and forces a text summary; new user input resets | `StepTracker`, `StepDirective`, `step_directive`, `FINAL_STEP_INSTRUCTION` |
| W2.6 | Parent `subagent` rules control launches; deny cannot be overridden; child keeps its own permissions | `PermissionRule`, `parse_permission`, `decide_launch` (deny -> ask -> allow -> default ask), `can_launch` |
| W2.8 | `system` replaces provider base prompt; project instructions/skills/references remain | `compose_system_prompt`, `ComposedPrompt`, `PROMPT_ORDER` |
| W2.9 | Later scalars replace, maps merge by key, permission rules append; global before agent rules | `merge_configs`, `merge_descriptors`, `AgentDescriptor.to_config`, `load_agents` ordering |
| W2.11 | Plan agent writes only plan files in a dedicated folder; shell stays permission-controlled | `PlanPolicy`, `PLAN_AGENT_POLICY`, `PLAN_DIR`, `permits_write`, `permission_config`, `shell_rules` |

## Files owned (only these were added)

* NEW `keel/src/keel/agent_contracts.py`
* NEW `keel/tests/test_agent_contracts.py`
* NEW `master-plan-v6-agent-contracts-evidence.md` (this file)

`subagent.py`, `agent_roles.py`, `agent_profiles.py`, `session.py`, existing
tests and `PLAN-INDEX.json` were **not** edited.

## Verification

Command (run from the worktree root, exactly as specified):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_agent_contracts.py']))"
```

Result: **35 passed in 0.81 s**. Stdlib only — no model call, subprocess or
network access anywhere in the module or tests.

## Required test coverage

The six mandated cases are all present and green:

* nested IDs — `agent_id_from_path` (`team/reviewer`) and nested discovery/loading
* unsafe YAML rejection — `!!python/...`, custom `!tags`, `${...}`, `$(...)`,
  backticks, `{{...}}`, anchors/aliases (7 parametrised cases)
* steps boundary — single-step and three-step budgets, tools removed and
  summary required on the final step, reset on new user input
* launch permission monotonicity — deny after allow still denies; global rules
  appended before agent rules; default-ask baseline
* prompt composition preserving skills — custom system replaces the provider
  base while project instructions, skills, references and lifecycle remain in a
  documented order
* merge semantics and plan-folder containment — scalar replace/map merge/rule
  append, plus traversal, absolute-path and wrong-extension write rejections

## TDD evidence

`test_agent_contracts.py` was written first and executed before the module
existed; collection failed with `ModuleNotFoundError: No module named
'keel.agent_contracts'`. After implementation the suite went through five
diagnosed failures (closing frontmatter fence consumed by the parser, nested-ID
glob mismatch in one fixture, an incorrect selectability assumption for the
subagent-only `explore` built-in, and unset scalars in `to_config()` overriding
earlier layers) before reaching the green result above.

## Design notes

* The frontmatter parser is a deliberately narrow, indentation-based subset:
  scalars, inline/block lists and nested maps. It never evaluates values; it
  refuses files containing YAML tags, template/interpolation syntax, command
  substitution, backticks, anchors or aliases.
* Permission rules use the registry's W3.1 shape `{action, resource, effect}`
  with effects `allow`/`deny`/`ask`. `decide_launch` implements the monotonic
  deny-first order, so an appended allow can never re-enable a denied launch.
  A child session receives its **own** permission rules unchanged — the parent
  rules only decide whether the launch happens.
* Built-ins are returned as fresh descriptors on every call (no shared mutable
  state). Hidden maintenance agents map to model roles `summarizer`/`title`;
  `hidden` is documented as visibility only, not a security boundary.
* The plan policy is a **pure descriptor**: it allows write/edit/create only
  under `.keel/plans/**` and returns no shell rules, leaving shell authority
  with the existing permission evaluator. Containment is checked with a
  normalized path guard that rejects `..` segments and wrong file extensions.

## Integration seams needed by the lead (not made here — file ownership)

1. **W2.1 / W2.9 agent loading.** Call `load_agents(global_root, project_root)`
   where agent configuration is assembled (near
   `keel/src/keel/agent_profiles.py` / config loading), then feed the resulting
   descriptors to the role/profile layer. Global rules are merged before
   project rules by construction.
2. **W2.2 / W2.6 subagent launch.** In `keel/src/keel/subagent.py`, before
   building the child `SessionConfig`, call
   `build_subagent_launch(parent_descriptor, child_descriptor, prompt=...)` and
   enforce `launch.allowed` (or route an `ask` decision to the approval gate).
   Construct the child's fresh context from `launch.build_context(...)`; the
   existing `SessionConfig(bare=True, ...)` already avoids parent-history
   injection. Do **not** intersect the child's permission rules with the
   parent's.
3. **W2.4 step budget.** Drive `StepTracker(agent.steps)` alongside the turn
   loop in `keel/src/keel/session.py`. On `directive.is_final`, remove tools from
   the request manifest and append `directive.instruction`; call `reset()` when
   a new user message starts a turn (this also feeds C3.2 doom-loop breaking).
4. **W2.8 prompt assembly.** Replace the provider base prompt with
   `compose_system_prompt(agent, provider_base_prompt=..., project_instructions=
   instructions.build_attachment(...), skills=rendered_skills, ...)` at the
   system-message construction site, preserving the `PROMPT_ORDER` section order
   for golden tests (X1.15).
5. **W2.11 plan policy.** When resolving an agent's effective permissions,
   `dict(plan.permission)` adds the scoped plan-write allow rules; keep calling
   the existing `keel.permissions.evaluate` for shell calls — `shell_rules()`
   is empty on purpose.
