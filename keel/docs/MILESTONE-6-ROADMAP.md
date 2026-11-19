# Milestone 6 — Roadmap

Date: 2026-11-20
Status: PLAN MODE — awaiting approval before BUILD MODE.

## Phases

### Phase 1 — Audit, architecture, contracts, plan (this document set)
Deliverables: MILESTONE-6-AUDIT.md, MILESTONE-6-ARCHITECTURE.md, MILESTONE-6-ROADMAP.md, MILESTONE-6-PARITY.md, MILESTONE-6-CHECKLIST.md.
No code changes.

### Phase 2 — Unified Python runtime and tool registry
- Introduce `keel/tools/registry.py` and refactor `session.ALL_TOOLS` to register through it.
- Add input validation and permission levels.
- Keep `/api/v2` working.
- Tests: tool registry, dispatch, validation.

### Phase 3 — Complete tool execution and permission integration
- Add missing filesystem tools (delete/move/list/patch/diff).
- Add terminal tools (python, tests, build, deps, process management).
- Add dev tools (git operations).
- Wire hooks (PreToolUse/PostToolUse already; add more).
- Tests: each tool, permission denial, approval flow.

### Phase 4 — Skills, commands, workflows
- Skills manager (install/remove/enable/disable/update/version/deps).
- Auto-load by context.
- Commands manager (built-in/user/project/global, slash, args, templates).
- Workflows engine (JSON definitions, execution).
- Tests.

### Phase 5 — MCP integration
- HTTP transport.
- Reconnect + health + logs.
- Resource/prompt discovery.
- Per-project config + approval.
- Tests (including HTTP MCP fake server).

### Phase 6 — Plugin and connector architecture
- Manifest, loader, registry, lifecycle, API.
- Credential storage.
- Connector base + MCP as connector.
- Tests.

### Phase 7 — Subagents and multi-agent orchestration
- Agent type system + specialized agents.
- Real parallel execution (thread pool/async).
- Structured results, progress, cancellation, recovery.
- Tests.

### Phase 8 — Persistent memory and project intelligence
- Memory store + retrieval.
- Project indexing (incremental), symbols, deps, ignore rules.
- Context budgeting/compression.
- User controls.
- Tests.

### Phase 9 — Hooks and automation
- Wire all 33 events.
- Python handlers.
- Enable/disable + logs.
- Tests.

### Phase 10 — Browser and computer interaction
- Optional Playwright-backed tools.
- Approval gating.
- Tests (skip if not installed).

### Phase 11 — Unified desktop UI integration
- Management screens bound to real APIs.
- Keep brand/design.
- Tests (API-level; UI smoke).

### Phase 12 — Security audit, testing, docs, release readiness
- Security review, audit logs.
- Full test matrix.
- Docs update.
- Release.

## Dependencies

- Phase 2 before 3, 4, 5, 7 (tools needed).
- Phase 4 (skills/commands) before workflows.
- Phase 5 (MCP) before plugins (connectors build on MCP).
- Phase 7 (orchestration) after tools.
- Phase 8 (memory) can run parallel with 5/6.
- Phase 11 (UI) after backend APIs exist.
- Phase 12 last.

## Risks and mitigations

- Scope creep: keep each phase independently testable and shippable.
- Parallelism complexity: start with independent tool calls only; add orchestration later.
- Security: Python backend enforces; UI is view only.
- Performance: incremental indexing; token budgeting.
- Backward compat: additive SQLite migrations; keep `/api/v2`.
- Test burden: require tests per phase before merge.

## Milestone exit criteria

See Definition of Done in the milestone spec: end-to-end workflow verified and reported.
