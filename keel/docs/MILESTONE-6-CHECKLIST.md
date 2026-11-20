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
- [x] Tests: `tests/test_tool_registry.py` (17 tests) plus full suite 471 passed
- [x] Backward compatibility preserved (`ALL_TOOLS`, `TOOL_SCHEMAS`, `RealTools.invoke`)

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
