# Addendum Y1.x P0 - MCP / plugin / config contracts: implementation evidence

Branch: `agent/a4-mcp` (worktree `.../worktree/addenda/mcp`)
Baseline: `fa062a4`
Source of requirements: `PLAN-INDEX.json` -> features
`Y1.2, Y1.3, Y1.4, Y1.5, Y1.6, Y1.7, Y1.8, Y1.9, Y1.16, Y1.17,
Y1.19, Y1.20, Y1.24, Y1.30` (all `P0`, source document
`Keel_Plan_v5_Addendum_4_Sourced_Features_and_Builder_Guide.md`, section
`### 2.1 opencode`).

This workstream is **additive**. No existing file was edited; in particular
`mcp.py`, `settings.py`, `config_schema.py` and all pre-existing tests are
untouched. The canonical implementation lives in one new module and is
exercised by one new permanent test file. Integration into the live runtime is
a separate lead decision (exact seams listed at the end).

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/mcp_contracts.py` | Canonical implementation of all 14 contracts (stdlib only, ~1,150 lines). |
| `keel/tests/test_mcp_contracts.py` | 57 permanent contract tests, one group per feature ID. |
| `master-plan-v6-mcp-contracts-evidence.md` | This document. |

## Feature coverage

| ID | Feature | Primary symbols | Tests |
| --- | --- | --- | --- |
| Y1.2 | Model-dependent tool exposure | `model_family`, `tools_for_model`, `ToolProfile`, `PATCH_FAMILIES` | `test_y102_*` (4) |
| Y1.3 | Patch multi-file format | `parse_patch`, `PatchDescriptor`, `FilePatch`, `PatchHunk` | `test_y103_*` (4) |
| Y1.4 | Read limits and paging | `page`, `PageResult`, `READ_MAX_LINES`, `READ_MAX_BYTES`, `MEDIA_MAX_BYTES` | `test_y104_*` (6) |
| Y1.5 | glob/grep defaults | `glob_defaults`, `grep_defaults`, `resolve_search_options`, `grep_permission_resource` | `test_y105_*` (3) |
| Y1.6 | edit unique match + formatter hook | `check_unique_match`, `validate_formatter_config`, `MatchValidation`, `FormatterSpec` | `test_y106_*` (3) |
| Y1.7 | Shell tool details | `shell_descriptor`, `ShellDescriptor` | `test_y107_*` (3) |
| Y1.8 | webfetch/websearch providers | `select_websearch_provider`, `webfetch_descriptor`, `validate_fetch_target`, `FREE_WEBSEARCH_PROVIDERS` | `test_y108_*` (4) |
| Y1.9 | question tool | `question_descriptor`, `QuestionDescriptor` | `test_y109_*` (3) |
| Y1.16 | MCP permission naming | `canonical_mcp_permission`, `mcp_permission_rule`, `mcp_timeout`, `mcp.<server>.<tool>` | `test_y1016_*` (2) |
| Y1.17 | Ordered rules + policies layer | `PermissionRule`, `evaluate_rules`, `evaluate_permissions`, `tool_use_rule`, `block_extension` | `test_y1017_*` (4) |
| Y1.19 | Config precedence | `merge_config_layers`, `effective_config`, `config_search_order`, `SCOPE_PRIORITY` | `test_y1019_*` (4) |
| Y1.20 | env/file substitution | `substitute_config`, `SubstitutionWarning`, `SubstitutionResult` | `test_y1020_*` (5) |
| Y1.24 | Compaction config | `validate_compaction_config`, `CompactionConfig.resolve` | `test_y1024_*` (3) |
| Y1.30 | Plugin enable/disable DSL | `parse_plugin_dsl`, `PluginSelection` (+ 7 parameterized rejection cases) | `test_y1030_*` (9) |

Total: **57 tests**, all passing.

## Design decisions worth the lead's attention

1. **Everything is a pure contract.** No function opens a socket, spawns a
   process, applies a patch or writes a file. The only byte-reading path,
   `{file:path}` substitution, receives an injected `file_reader` (default is a
   guarded `Path.read_text`) so the host retains full control. `webfetch` /
   `websearch` return descriptors and select among *free* providers only
   (`searxng`, `duckduckgo`, `wikipedia`, `local-index`); paid backends are
   rejected with `non_free_provider` before any I/O could occur.
2. **Deny wins, structurally.** `evaluate_rules` is order-independent for
   denials (a matching `deny` returns immediately), while the *last* matching
   allow wins among allows. `evaluate_permissions` adds a policies layer whose
   denies (including `block_extension` for MCP servers / skills / plugins)
   outrank config, but a config deny is never overridden by a policy allow.
   Permission lists in config layers are concatenated, never replaced, so a
   deny in any precedence layer survives the merge.
3. **Precedence is explicit and traceable.** `effective_config` merges
   `default < user < project < managed` and records dotted-path provenance for
   the layered config viewer (X6.8); `config_search_order` walks root -> cwd,
   direct file before `.keel/` file, user next, managed/system last.
4. **Substitution never logs secrets.** Warnings carry only `{kind, key}`.
   Missing env/file values become `""` and emit warnings; secret-looking
   variable names additionally emit `secret_reference` (name only). File paths
   are containment-checked against `base_dir`; `../` traversal raises
   `path_outside_base_dir` before the reader is called.
5. **DSL rejects code, not just typos.** `parse_plugin_dsl` rejects shell
   metacharacters, template/script brackets, quotes and code words as
   `unsafe_token`. Rules are specificity-ranked (exact > prefix wildcard > `*`)
   with later-entry-wins at equal specificity, which implements "later entry
   re-enables" without letting a broad `-*` defeat a specific `prefix.*`.
   Built-in policy plugins are always enabled.
6. **Paging is deterministic.** `page` enforces both the 2,000-line and
   50 KiB caps, truncates a genuinely over-long single line on a UTF-8
    boundary, and emits a stable marker carrying `omitted_lines`,
   `omitted_bytes` and the safe `next_offset`.
7. **Canonical naming is separate from invocation naming.** Permissions use
   `mcp.<server>.<tool>` (resource `*`, per-server timeout, global
   `mcp.timeout` fallback). The legacy `mcp__server__tool` tool-invocation name
   in `mcp.py` is intentionally left alone; the two layers are bridged by the
   host at the permission boundary.

## Test results

Command (from worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_mcp_contracts.py']))"
```

Result: `57 passed in 1.09s`.

Commit: this document is part of the single commit on `agent/a4-mcp` that adds
all three owned files; the exact SHA is reported in the subagent's final
report (`git log -1 --oneline` from the worktree).

## Integration seams (lead decision, no code changed here)

| ID | Seam in the live runtime |
| --- | --- |
| Y1.2 | Call `tools_for_model(model, all_tools=registry.tools(), family_map=config.model.family_map, profile=agent.profile)` when composing a session's tool declaration; keep schema allowlisting in `tool_contracts`. |
| Y1.3 | In the patch tool handler, `parse_patch(text)` first; feed each `affected_paths` entry through `mcp_permission_rule` + `evaluate_rules` **before** any existing applier. The descriptor deliberately exposes no apply operation. |
| Y1.4 | Use `page(...)` in the read handler with `READ_MAX_LINES` / `READ_MAX_BYTES`; use `MEDIA_MAX_BYTES` as the image/PDF gate; return `PageResult.marker` to the model for continued paging. |
| Y1.5 | Load `glob_defaults()` / `grep_defaults()` into `settings`, validate overrides via `resolve_search_options`, and pass `grep_permission_resource(pattern)` as the permission resource. |
| Y1.6 | Call `check_unique_match` before any edit application; validate `formatter` via `validate_formatter_config` at config load; actual formatter execution stays with the host and runs only after a successful write/edit/patch. |
| Y1.7 | At tool dispatch, use `shell_descriptor`: set the process cwd from `workdir`, reject a command that contains `cd`, request one permission per `permission_resources` entry, route output through the managed-file/truncate policy, and notify the session on background completion. |
| Y1.8 | In the web tools adapter, call `validate_fetch_target` (with the policy callable from `policy_enforcement`), `webfetch_descriptor`, and `select_websearch_provider`; only the host transport performs the actual request. |
| Y1.9 | Pass `QuestionDescriptor.to_dict()` to clients; `mode == "text"` is the fallback for clients that declare no UI; `requires_approval` comes from the injected approval policy; blocking/answer handling stays in the `ask_user` flow. |
| Y1.16 / Y1.17 | Register canonical rules from `mcp_permission_rule` in the permission table and evaluate with `evaluate_permissions` (config rules + policies layer). Keep `mcp__server__tool` only for tool invocation. |
| Y1.19 | Drive the config loader walk with `config_search_order` and merge with `effective_config`; pass `provenance` to the layered config viewer (X6.8). |
| Y1.20 | Invoke `substitute_config` in the config loader with `base_dir` set to the config directory and an injected `file_reader`; surface `warnings` to the UI, never substituted values. |
| Y1.24 | Validate `compaction` settings with `validate_compaction_config` and select the active knobs with `CompactionConfig.resolve(model)` in the compaction engine; `summary` remains the default strategy. |
| Y1.30 | At plugin config load, call `parse_plugin_dsl(text, builtin_plugins=policy_registry.builtin_ids)` and use `PluginSelection.enabled(available)` to compute the active set; never execute plugin code from the DSL. |
