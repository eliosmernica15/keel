# Y1.x remaining (P1/P2) backend implementation evidence

Worktree: `C:\Users\Admin\.local\share\opencode\worktree\backend\b1-y1`
Branch: `agent/b1-y1`
Baseline: `982335d`
Requirement source: `PLAN-INDEX.json` -> `features` where `id` starts with
`Y1.` and `status == "not_started"` (25 rows; all from
`Keel_Plan_v5_Addendum_4_Sourced_Features_and_Builder_Guide.md`,
section `### 2.1 opencode`).

This workstream is **additive**. The only files added are the three owned
files listed below; no existing module, registry, source file or test was
edited. The 14 `Y1.*` P0 rows are already `verified` and live in
`keel/src/keel/mcp_contracts.py` (see "Verified P0 mapping"); they were **not**
duplicated. Runtime integration remains a lead decision: every new function
returns a descriptor, decision, plan or diff and never performs I/O.

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/y1_config_backend.py` | Canonical implementation of the 25 remaining Y1 contracts (stdlib only). |
| `keel/tests/test_y1_config_backend.py` | 58 collected tests (54 test functions + 4 parametrized cases), one group per feature ID, including adversarial cases. |
| `master-plan-v6-y1-backend-evidence.md` | This document. |

## Per-ID classification

All 25 `not_started` rows are **implemented** in the new module and covered by
permanent tests. No row was excluded. External prerequisites named in the
plan (Playwright/CDP for Y1.14, a local diffusion provider for Y1.15, git
worktree manager X2.6 for Y1.13, error catalog C10.2 for Y1.36) are
represented as validated descriptors/plans: the host owns the actual runtime
operation, so no feature is blocked by a missing third-party dependency at
the contract layer.

| ID | Priority | Feature | Classification | Primary symbols | Tests |
| --- | --- | --- | --- | --- | --- |
| Y1.1 | P1 | Code Mode / `execute` tool | implemented | `code_mode_descriptor`, `validate_code_script`, `authorize_code_mode_call`, `code_mode_server_switches`, `CODE_MODE_ALLOWED_GLOBALS` | `test_y101_*` (6) |
| Y1.10 | P1 | skill loader advertised-list gate | implemented | `can_load_skill`, `require_skill`, `SkillLoadDecision` | `test_y1010_*` (2) |
| Y1.11 | P1 | Subagent semantics | implemented | `spawn_subagent`, `subagent_notification`, `subagent_followup`, `validate_subagent_depth`, `SubagentLaunch` | `test_y1011_*` (2) |
| Y1.12 | P2 | session utilities as tools | implemented | `session_rename_tool`, `session_move_tool`, `SessionMovePlan`, `SESSION_UTILITY_TOOLS` | `test_y1012_*` (2) |
| Y1.13 | P1 | worktree tools | implemented | `worktree_create`, `worktree_list`, `worktree_remove`, `worktree_strategy_registry`, `WorktreePlan` | `test_y1013_*` (3) |
| Y1.14 | P1 | browser tool namespace | implemented | `BROWSER_TOOLS`, `browser_tool_catalog`, `validate_browser_url`, `browser_page_content`, `validate_browser_transfer_size`, `lighthouse_descriptor` | `test_y1014_*` (3) |
| Y1.15 | P2 | `experimental_image_generate` | implemented | `image_generate_descriptor`, `LOCAL_IMAGE_PROVIDERS`, `ImageJobDescriptor` | `test_y1015_*` (2) |
| Y1.18 | P2 | managed config locations | implemented | `managed_config_locations`, `managed_value`, `MANAGED_LOCATIONS`, `MANAGED_PRECEDENCE` | `test_y1018_*` (2) |
| Y1.21 | P1 | update modes | implemented | `resolve_update_mode`, `update_plan`, `UpdatePlan`, `UPDATE_MODES` | `test_y1021_*` (1) |
| Y1.22 | P1 | snapshots toggle and `watcher.ignore` | implemented | `snapshots_enabled`, `validate_watcher_ignore`, `watcher_ignored` | `test_y1022_*` (2) |
| Y1.23 | P1 | `media.image` / `tool_output` limits | implemented | `resolve_media_limits`, `resolve_tool_output_limits`, `resize_dimensions`, `validate_base64_size`, `clip_tool_output` | `test_y1023_*` (2) |
| Y1.25 | P1 | cache warming | implemented | `cache_policy`, `warm_due`, `warming_plan`, `CachePolicy` | `test_y1025_*` (2) |
| Y1.26 | P1 | References | implemented | `parse_references`, `reference_by_name`, `search_references`, `Reference` | `test_y1026_*` (2) |
| Y1.27 | P2 | skills directories and URLs | implemented | `parse_skill_sources`, `skill_pack_signature_check`, `SkillSource` | `test_y1027_*` (2) |
| Y1.28 | P1 | instructions files/globs/URLs | implemented | `parse_instruction_sources`, `instruction_context`, `InstructionSource` | `test_y1028_*` (2) |
| Y1.29 | P1 | plugin management CLI | implemented | `plugin_command`, `parse_plugin_source`, `update_plugin_plan`, `PluginSource` | `test_y1029_*` (2) |
| Y1.31 | P1 | three plugin surfaces | implemented | `parse_plugin_manifest`, `tui_plugin_ids`, `extensions_page_state`, `hot_reload_plan`, `PluginManifest` | `test_y1031_*` (2) |
| Y1.32 | P1 | `location_idle_timeout` | implemented | `validate_idle_timeout`, `should_unload`, `unload_plan`, `IdleState` | `test_y1032_*` (2) |
| Y1.33 | P2 | `experimental.todo` flag | implemented | `todo_tool_exposure`, `TODOWRITE_TOOL`, `TODO_TOOL` | `test_y1033_*` (2) |
| Y1.34 | P1 | model overrides / transport | implemented | `apply_model_overrides`, `validate_transport`, `provider_transport` | `test_y1034_*` (2) |
| Y1.35 | P1 | `config_edit` tool | implemented | `propose_config_edit`, `ConfigEditProposal`, `TIER2_CONFIG_KEYS` | `test_y1035_*` (2) |
| Y1.36 | P2 | migrate/troubleshooting docs | implemented | `build_docs_pages`, `DOC_ROUTES`, `DocPage` | `test_y1036_*` (2) |
| Y1.37 | P1 | install script / channels | implemented | `install_plan`, `INSTALL_CHANNELS`, `STORE_FEASIBILITY`, `InstallPlan` | `test_y1037_*` (2) |
| Y1.38 | P1 | repo hygiene | implemented | `validate_gitleaks_allowlist`, `repo_hygiene_status`, `task_graph_order`, `AllowlistEntry` | `test_y1038_*` (2) |
| Y1.39 | P2 | non-affiliation notice | implemented | `non_affiliation_notice`, `validate_trademarks_doc` | `test_y1039_*` (2) |

## Verified P0 mapping (not duplicated, not edited)

The 14 `verified` P0 rows were re-run unchanged to confirm the mapping claimed
in the task; all 57 existing contract tests still pass on this baseline.

| ID | Feature | Existing canonical module / symbols |
| --- | --- | --- |
| Y1.2 | model-dependent tool exposure | `keel.mcp_contracts`: `model_family`, `tools_for_model`, `ToolProfile`, `PATCH_FAMILIES` |
| Y1.3 | patch multi-file format | `parse_patch`, `PatchDescriptor`, `FilePatch`, `PatchHunk` |
| Y1.4 | read limits and paging | `page`, `PageResult`, `READ_MAX_LINES`, `READ_MAX_BYTES` |
| Y1.5 | glob/grep defaults | `glob_defaults`, `grep_defaults`, `resolve_search_options` |
| Y1.6 | edit unique match + formatter hook | `check_unique_match`, `validate_formatter_config` |
| Y1.7 | Shell tool details | `shell_descriptor`, `ShellDescriptor` |
| Y1.8 | webfetch/websearch providers | `select_websearch_provider`, `webfetch_descriptor`, `validate_fetch_target` |
| Y1.9 | question tool | `question_descriptor`, `QuestionDescriptor` |
| Y1.16 | MCP permission naming | `canonical_mcp_permission`, `mcp_permission_rule`, `mcp_timeout` |
| Y1.17 | ordered rules + policies layer | `PermissionRule`, `evaluate_rules`, `evaluate_permissions` |
| Y1.19 | config precedence | `merge_config_layers`, `effective_config`, `config_search_order` |
| Y1.20 | `{env:VAR}` / `{file:path}` substitution | `substitute_config`, `SubstitutionWarning` |
| Y1.24 | compaction config | `validate_compaction_config`, `CompactionConfig.resolve` |
| Y1.30 | plugin enable/disable DSL | `parse_plugin_dsl`, `PluginSelection` |

## Design decisions and safety properties

1. **Pure contracts, no side effects.** No function opens a socket, spawns a
   process, reads `os.environ`, imports a third-party package, reads a secret
   or writes a file. The only "execution" seams are injected callables:
   `authorize_code_mode_call(permission_gate=...)` and
   `worktree_remove(permission_check=...)`. Both return descriptors
   (`executed: False`) or raise; neither calls a tool or git.
2. **Every nested Code Mode call is gated.** `validate_code_script` rejects
   imports, timers, dynamic evaluation, filesystem/process modules and unsafe
   markup before a descriptor is built; `code_mode_descriptor` honours a
   per-MCP-server `codemode: false` switch; a global denial empties the tool
   catalog and sets `fallback = "tool_list"`.
3. **Deny-by-default gates.** Skills load only when advertised or explicitly
   user-named; plugin sources require a private-source allowlist by default;
   URL sources require an explicit host allowlist; Lighthouse requires consent
   *and* licence acknowledgement; remote cache warming requires opt-in *and*
   disclosed cost.
4. **Traversal and unsafe tags are rejected at every path/name boundary.**
   `_safe_id`, `_relative_path`, `_rooted` and `_url` are shared by all
   path-bearing features. Traversal (`../`, absolute paths, percent-encoded
   separators), unsafe HTML/script tokens, shell metacharacters in plugin
   sources, SSRF-style literal/private IPs and credentials in URLs all raise
   typed errors with machine-readable codes.
5. **Text from untrusted sources is escaped, never interpreted.** Browser page
   text, error-catalog messages/remedies and trademark inputs are HTML-escaped
   before they appear in a descriptor or generated page; tool output is
   clipped by both line and byte caps with a stable truncation marker.
6. **Precedence conflicts are explicit.** Managed config outranks project/user
   values (`managed_value`); update mode is global-only and a project value is
   ignored (`resolve_update_mode`, marked `ignored_project_value`); TUI plugins
   are configured only through `tui_plugin_ids`; model overrides cannot raise
   output above context; `config_edit` refuses Tier-2 keys and ambiguous edits.
7. **No fake success.** Descriptors carry `applied_now=False`, `applies=False`,
   `executes=False`, `fetched=False`, `network_used=False` or
   `installed_version_unchanged=True` so a caller cannot mistake a plan for a
   completed operation. `script_preview` in Y1.37 is a comment-only preview.

## Adversarial cases exercised

* Path traversal: session move, worktree create/rename, image save path and
  references, skills directories, instructions, repo-hygiene files, plugin
  subdirectories, branches and hot-reload paths.
* Unsafe tags / injection: skill IDs, watcher globs, browser page text,
  Code Mode scripts, instructions URLs, plugin sources, install home paths,
  error-catalog text and trademark notices.
* Precedence conflicts: managed vs project config, project vs global update
  mode, allowlisted vs unlisted hosts, exact vs unpinned plugin versions,
  TUI-only vs GUI/server surfaces, Tier-2 vs editable config keys.
* Permission and consent denials: Code Mode nested gate, worktree edit
  permission, dirty-worktree `force`, Lighthouse consent/licence, remote cache
  warming opt-in/cost.

## Commands and results

Run from the worktree root (the required `sys.path.insert` invocation):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_y1_config_backend.py']))"
```

Result: **58 passed in 8.58s**.

Verified P0 regression command (unchanged module/tests):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_mcp_contracts.py']))"
```

Result: **57 passed in 3.59s**.

Combined command:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_y1_config_backend.py','keel/tests/test_mcp_contracts.py']))"
```

Result: **115 passed in 9.39s** (both files green together).

## Integration seams (lead decision, no code changed here)

| ID | Host seam |
| --- | --- |
| Y1.1 | Register `code_mode_descriptor(...).tools` as the `execute` script's catalog; wrap every generated call in `authorize_code_mode_call`; never run the script in this module. |
| Y1.10 | Have the `skill` tool call `require_skill(id, advertised, user_named)` before any skill body is read. |
| Y1.11 | Use `spawn_subagent` / `subagent_notification` / `subagent_followup` in the task graph in `keel/subagent.py`; pass `subagent_depth` from config. |
| Y1.12 | Expose `session_rename_tool` / `session_move_tool` through the tool registry; apply the move only when the session reaches a safe boundary. |
| Y1.13 | Feed `WorktreePlan.permission_resource` into the edit-permission gate; call a real git worktree manager only after `force`/permission checks pass. |
| Y1.14 | Mount `browser_tool_catalog()` in the browser tool namespace; drop the whole catalog when `browser` is denied; mark every page result untrusted. |
| Y1.15 | Advertise `image_generate_descriptor` only when a local diffusion provider exists (Y5.2); the host enqueues the job and notifies on completion. |
| Y1.18 | Walk `managed_config_locations(os, env)` in the config loader; feed values through `managed_value` so managed wins. |
| Y1.21 | `resolve_update_mode` at config load; `update_plan` in the updater, which must never restart a running server. |
| Y1.22 | `snapshots_enabled` in the checkpoint manager; `watcher_ignored` in the file watcher. |
| Y1.23 | `resolve_media_limits` / `resolve_tool_output_limits` when attaching images and formatting tool results. |
| Y1.25 | `cache_policy` / `warm_due` / `warming_plan` in the scheduler; remote warming only after opt-in and cost display. |
| Y1.26 | `parse_references` at config load; the host clones repositories read-only into `Reference.cache_path`. |
| Y1.27 | `parse_skill_sources` in the skill loader; only the host fetches a URL and verifies a signed pack. |
| Y1.28 | `parse_instruction_sources` in the instruction loader; fetch URL sources through the SSRF-safe client and keep `tainted=True`. |
| Y1.29 | Wire `plugin_command` argument parsing to the CLI; the host owns package installation and update checks. |
| Y1.31 | `parse_plugin_manifest` at plugin load; drive the Extensions settings page from `extensions_page_state` and hot-reload from `hot_reload_plan`. |
| Y1.32 | `should_unload` / `unload_plan` in the project lifecycle manager (A2.4). |
| Y1.33 | `todo_tool_exposure` when composing tool declarations; `todo` remains the P0 tool. |
| Y1.34 | `apply_model_overrides` over the offline catalog; `provider_transport` for provider settings. |
| Y1.35 | `propose_config_edit` produces the diff shown to the user; the host writes only after approval. |
| Y1.36 | Serve `build_docs_pages(...)` at `DOC_ROUTES`. |
| Y1.37 | `install_plan` supplies the per-user target and channel formulas; the host executes the real installer. |
| Y1.38 | `validate_gitleaks_allowlist` / `repo_hygiene_status` / `task_graph_order` in repo tooling. |
| Y1.39 | Render `non_affiliation_notice` into `TRADEMARKS.md`; `validate_trademarks_doc` guards changes. |

Commit: this document is part of the single commit on `agent/b1-y1` that adds
the three owned files. The exact SHA is reported in the subagent's final
report (`git log -1 --oneline` from the worktree).
