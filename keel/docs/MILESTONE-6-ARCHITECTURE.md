# Milestone 6 — Architecture

Date: 2026-11-20
Status: PLAN MODE — design, no implementation.

## 1. Design principles

1. **Python is the backend.** No Node/Supabase/Firebase/Cloudflare/external DB.
2. **One execution engine.** `session.Session` (turn loop) is the only place model turns run; tools, MCP, subagents, hooks all plug into it.
3. **One permission engine.** `permissions.py` + `fleet/approvals.py` (F1 broker). UI never enforces.
4. **One persistence layer.** SQLite (`fleet/db.py`) + `~/.keel` files. Schema migrations are additive and idempotent.
5. **Local-first.** Optional connectors are user-configured; no mandatory cloud.
6. **Extensible by contract.** Stable Python APIs + manifests; no hardcoded integrations.

## 2. Unified agent runtime

### Core contracts (new module: `keel/agent/` or extend `session.py`)

- `Agent`: id, name, instructions, model, provider, tool allowlist, permission mode, memory scope.
- `Session`: existing `Session`/`SessionConfig`, extended with agent binding and project binding.
- `Message`: role, content, images, tool calls, tool results, usage, seq.
- `ToolCall`: id, name, input, status, result, approval_id.
- `Event`: typed SSE events (token, tool_call, tool_result, approval, usage, turn_end, notice).
- `ExecutionResult`: final text, usage, tool results, terminal_reason.

### Runtime flow

```
create_session(agent, project) -> Session
send_message(session, content, images) ->
  build context (project + memory + skills + instructions)
  -> Session.turn (model call)
     -> tool calls -> ToolRegistry.dispatch -> permission check -> hooks -> execute
     -> subagent delegation (Task/send_to_bot)
     -> MCP tools
  -> stream events -> persist rows -> usage
  -> turn_end
```

### Context management

- `context.py` (existing) + new `context_selector.py`: score files/symbols/memory by relevance; token budgeting; compaction.
- Ignore rules (`.keelignore` / gitignore) via new `ignore.py`.

### Cancellation

- Existing cancel endpoint; extend to cancel subagents and background tasks.

## 3. Tool system

### New module: `keel/tools/`

- `registry.py`: `Tool` dataclass (name, description, schema, handler, permission_level, category), registration, discovery, listing.
- `validation.py`: JSON-schema input validation (stdlib, no new deps).
- `executor.py`: dispatch, hooks (PreToolUse/PostToolUse), permission, timeout, result rendering.
- `categories/`: filesystem, terminal, dev, web, utility. Each a module registering tools.

### Filesystem tools
read_file, write_file, edit_file, delete_file, move_file, list_dir, glob, grep, apply_patch, diff, watch (optional).

### Terminal tools
run_shell, run_python, run_script, run_tests, run_build, install_deps, process_list, process_kill, background_shell.

### Dev tools
git_status, git_diff, git_log, git_branch, git_commit, symbol_search, diagnostics.

### Web tools
web_search, web_fetch, browser_navigate, browser_click, browser_fill, browser_screenshot (gated).

### Utility tools
time_now, calc, json_query, convert, project_summary.

### Permission levels
- `read` (auto), `write` (approval in manual mode), `execute` (approval), `network` (approval), `destructive` (always approval).

## 4. Skills

### Extend `keel/skills.py` into `keel/skills/`

- `discovery.py` (existing logic moved), `manager.py` (install/remove/enable/disable/update/validate/version).
- Storage: `~/.keel/skills` (user), `<project>/.keel/skills` (project), bundled `resources/default-skills`.
- Metadata: name, description, version, dependencies, trust.
- Auto-load: `skill_selector.py` picks relevant skills by task keywords/embeddings? Use keyword scoring (local, no embeddings dep) + explicit user selection.
- API: `/api/skills` (list), `/api/skills/install`, `/api/skills/remove`, `/api/skills/enable`, etc.
- UI: Skills Manager screen.

## 5. MCP

### Extend `keel/mcp.py`

- Transports: stdio (done) + HTTP (SSE/streamable). Add `HttpMcpClient`.
- Connection manager with reconnect, health checks, logs.
- Resource discovery (`resources/list`, `resources/read`), prompt discovery.
- Config: per-project + user scope; project-scope approval retained.
- Integrate into ToolRegistry (MCP tools registered dynamically).
- API: `/api/mcp/servers` CRUD, `/api/mcp/health`, logs.
- UI: MCP Servers screen.

## 6. Plugins and connectors

### New module: `keel/plugins/`

- `manifest.py`: plugin manifest schema (name, version, entrypoint, permissions, dependencies).
- `loader.py`: discover from `~/.keel/plugins` and `<project>/.keel/plugins`; load in isolated subprocess or in-process with error isolation.
- `registry.py`: enable/disable, config, lifecycle (init/shutdown).
- `api.py`: stable Python API for plugins (hooks, tools, commands, connectors).
- `connectors/`: connector base + credential storage; MCP servers are one connector type.

### Credential storage

- Reuse `settings_store.py`; add encrypted-at-rest option? Use OS keyring if available, fallback to file with warning. No new mandatory deps (keyring optional).

## 7. Commands and workflows

### New module: `keel/commands/`

- `registry.py`: built-in + user + project commands.
- `parser.py`: slash command parsing with args.
- `executor.py`: invoke agents/tools/workflows.
- `templates.py`: command templates.
- Workflows: `keel/workflows/` with YAML/JSON definitions (stdlib yaml? avoid new dep; use JSON or simple parser). Prefer JSON to avoid deps; optional yaml if installed.

## 8. Subagents and orchestration

### Extend `session.py` / `fleet/`

- Agent type system: `AgentSpec` with role, instructions, tool subset, model, permissions.
- Built-in specialized agents: research, coding, debugging, testing, docs, security, architecture, browser.
- Orchestrator: task graph, parallel execution via thread pool/asyncio, shared context, structured results, progress, cancellation, failure recovery.
- `fleet/delegation.py` becomes the orchestrator's delegation primitive.

### Parallel execution

- Use Python `concurrent.futures` or `asyncio`. Keep GIL in mind; subprocess-based tools release GIL. Provide real parallelism where safe (independent tool calls).

## 9. Memory and project intelligence

### New module: `keel/memory/`

- `store.py`: SQLite tables for memories (project/user/agent scope), notes, decisions, conventions.
- `retrieval.py`: keyword search + scoring; inject only relevant subset.
- `project_index.py`: file discovery, symbol extraction (regex-based, no heavy parser dep), dependency analysis (imports), incremental indexing with mtime.
- `context_budget.py`: token budgeting and compression.

### User controls

- API + UI to inspect/add/delete memories.

## 10. Hooks

- Reuse `hooks.py`. Wire all 33 events into runner/session/fleet at appropriate points.
- Add Python handler support (not just command) via `keel/hooks/handlers.py` importing callables.
- Enable/disable + logs in settings/UI.

## 11. Browser/computer interaction

### New module: `keel/browser/`

- Optional dependency on Playwright? The rule says no new third-party backend deps; Playwright is a Python package but requires browser binaries. Make it optional: if installed, enable browser tools; otherwise tools report "not available".
- Tools: open, navigate, read, click, fill, screenshot, download.
- Approval required for sensitive actions.

## 12. UI

- Extend existing desktop/site UI with management screens: Agents, Tools, Skills, MCP, Plugins, Connectors, Commands, Workflows, Memory, Hooks, Project Context, Background Tasks, Execution History, Permissions.
- Each screen binds to real backend APIs; no demo pages.
- Keep Keel brand/design.

## 13. Security

- Centralized permission engine (done) remains authoritative.
- Add audit log table (who/what/when/result).
- Plugin sandbox: subprocess isolation preferred; in-process plugins must declare permissions.
- Path traversal protection reused.
- Credential isolation: `~/.keel/credentials/` with restrictive perms.

## 14. API and extensibility

- Extend `/api/v2` with new endpoints; keep backward compat.
- Document contracts in `docs/API.md`.

## 15. Testing

- Unit + integration + API + permission + tool + MCP + plugin + skills + orchestration + memory + workflow + desktop integration.
- Fake providers for determinism; real integrations when keys available.
- Cross-platform CI (already).

## 16. Documentation

- Create/update the docs listed in the milestone.

## 17. Data model (SQLite additions)

- `agents`, `agent_runs`, `memories`, `project_index`, `plugins`, `commands`, `workflows`, `audit_log`, `background_tasks`, `mcp_servers` (if not in settings), `skills_state`.
- All migrations additive and idempotent.

## 18. Module layout (proposed)

```
keel/src/keel/
  agent/          # runtime contracts, orchestrator
  tools/          # registry + categories
  skills/         # manager (refactor from skills.py)
  mcp/            # expanded client (refactor from mcp.py)
  plugins/        # plugin system
  commands/       # command system
  workflows/      # workflow engine
  memory/         # memory + project intelligence
  browser/        # optional browser automation
  (existing modules retained)
```

Keep backward-compatible imports (re-export from old modules).

## 19. Compatibility

- Keep `/api/v2/sessions*` working.
- Keep `fleet.db` v11 migration path.
- Keep CLI commands.
- Keep release pipeline.

## 20. Risks

- Large scope; phase carefully.
- Real parallelism complexity.
- Security review for plugins.
- Performance on large projects (incremental indexing).
- Test matrix growth.
- Avoiding OpenCode's full surface (focus on high value).
