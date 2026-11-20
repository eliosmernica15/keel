# Milestone 6 — Checklist (living)

Status: PLAN MODE — no implementation yet.

## Phase 1 — Audit, architecture, contracts, plan
- [ ] MILESTONE-6-AUDIT.md written
- [ ] MILESTONE-6-ARCHITECTURE.md written
- [ ] MILESTONE-6-ROADMAP.md written
- [ ] MILESTONE-6-PARITY.md written
- [ ] MILESTONE-6-CHECKLIST.md written
- [ ] Plan reviewed and approved by user

## Phase 2 — Unified runtime and tool registry
- [x] `keel/tools/registry.py` (Tool + ToolRegistry)
- [x] `keel/tools/native.py` (native tool definitions migrated from `session.TOOL_SCHEMAS`)
- [x] `keel/tools/__init__.py`
- [x] Refactor `session.ALL_TOOLS` to derive from registry
- [x] `session.TOOL_SCHEMAS` now aliases native registry schemas
- [x] Runtime uses registry for discovery and dispatch (`session.run`)
- [x] Input validation in registry
- [x] MCP tools registered into the same registry per turn
- [x] Tests: `tests/test_tool_registry.py` (17 tests) plus full suite 479 passed
- [x] Backward compatibility preserved (`ALL_TOOLS`, `TOOL_SCHEMAS`, `RealTools.invoke`)

## Milestone 6B — Advanced agent capabilities
- [x] Advanced native tools: delete_file, move_file, list_dir, apply_patch, diff_files, copy_file, make_dir, file_info, search_files
- [x] Terminal/process: run_python, run_tests, run_build, install_deps, background_shell, process_list, process_output, process_wait, process_kill
- [x] Git: git_status, git_diff, git_log, git_branch_list, git_add, git_commit, git_checkout
- [x] Dev intelligence: project_summary, symbol_search
- [x] Web: web_fetch, web_search
- [x] Agent-facing: list_skills, load_skill, run_workflow
- [x] Skills manager: discover/install/remove/enable-disable/update/validate/select
- [x] Workflow engine: JSON discovery, execution (tool/command/shell steps)
- [x] MCP HTTP transport + health/reconnect/resources/prompts
- [x] Skills/commands/workflows/MCP API endpoints
- [x] Safety tier-2 coverage for all new tools
- [x] Ignore rules in search
- [x] MCP resource/prompt integration into agent context (HTTP servers)
- [x] Process cleanup on shutdown (atexit)
- [x] Security audit document: docs/MILESTONE-6-SECURITY-AUDIT.md
- [x] Full test suite: 479 passed, 10 skipped
- [ ] Desktop UI management screens (API-only in this milestone)
- [ ] Ignore rules in all filesystem operations (partial)
- [ ] MCP resource/prompt use in stdio agent context (deferred to avoid blocking)
- [ ] Process cleanup tested in CI (registered but not tested)

## Phase 3 — Complete tool execution
- [ ] Missing filesystem tools
- [ ] Terminal tools
- [ ] Dev/git tools
- [ ] Web tools
- [ ] Utility tools
- [ ] Hook wiring beyond 2 events
- [ ] Tests

## Phase 4 — Skills, commands, workflows
- [ ] Skills manager lifecycle
- [ ] Auto-load by context
- [ ] Commands manager
- [ ] Workflows engine
- [ ] Tests

## Phase 5 — MCP
- [ ] HTTP transport
- [ ] Reconnect/health/logs
- [ ] Resource/prompt discovery
- [ ] Per-project config
- [ ] Tests

## Phase 6 — Plugins and connectors
- [ ] Manifest + loader + registry + lifecycle
- [ ] Plugin API
- [ ] Credential storage
- [ ] Connector base
- [ ] Tests

## Phase 7 — Subagents and orchestration
- [ ] Agent type system
- [ ] Specialized agents
- [ ] Real parallel execution
- [ ] Structured results/progress/cancellation
- [ ] Tests

## Phase 8 — Memory and project intelligence
- [ ] Memory store + retrieval
- [ ] Project indexing (incremental)
- [ ] Symbols/deps/ignore rules
- [ ] Context budgeting
- [ ] User controls
- [ ] Tests

## Phase 9 — Hooks and automation
- [ ] Wire all 33 events
- [ ] Python handlers
- [ ] Enable/disable + logs
- [ ] Tests

## Phase 10 — Browser and computer interaction
- [ ] Optional browser tools
- [ ] Approval gating
- [ ] Tests

## Phase 11 — Unified desktop UI
- [ ] Management screens bound to real APIs
- [ ] Keep brand/design
- [ ] API-level tests

## Phase 12 — Security audit, testing, docs, release
- [ ] Security review + audit logs
- [ ] Full test matrix
- [ ] Docs update
- [ ] Release

## Definition of Done (verification)
- [ ] Open project
- [ ] Create agent session
- [ ] Inspect project
- [ ] Discover skills
- [ ] Execute tools with approval
- [ ] Execute commands
- [ ] Delegate to subagent
- [ ] Use MCP
- [ ] Preserve memory
- [ ] Execute workflow
- [ ] Stream progress
- [ ] Restore session after restart
- [ ] Verification report produced
