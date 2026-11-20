# Milestone 6 — Audit of the current Keel codebase

Date: 2026-11-20
Status: PLAN MODE — no implementation has been started.

## 1. Repository inventory (relevant surfaces)

- Python package: `keel/src/keel` (~12.4 kLOC). Entry points `keel` (CLI) and `keel fleet` / `keel serve`.
- Desktop: Electron app in `keel/desktop-app` (Node/Electron packaging only; the runtime is Python).
- Web mirror: `keel/site` (static, deployed to Vercel).
- Persistence: SQLite via `keel/src/keel/fleet/db.py` (schema v11), `~/.keel`.
- Tests: 34 Python test modules, ~450+ tests; CI on Windows/macOS/Linux.
- Release: `keel/src/keel/release` (Python-only, GitHub Releases).

## 2. Capability inventory (classified)

Status legend:
- **Verified** = implemented, tested, and evidenced.
- **Partial** = implemented but incomplete or not wired end to end.
- **Needs integration** = code exists but is not connected to the unified runtime/UI.
- **Missing** = not present.
- **Blocked** = cannot proceed without an external prerequisite.

### A. Agent runtime and execution

| Capability | Status | Evidence / location |
|---|---|---|
| Agent turn loop (model → tools → result) | Verified | `session.py` (`Session`, `SessionConfig`), `runner.py` |
| Streaming tokens over SSE | Verified | `events.py`, `fleet/provider_turn.py`, `compat.py` |
| Tool-call lifecycle (running/done/error) | Verified | `fleet/tools.py`, `toolresult.py`, SSE step rows |
| Permission gates (Tier-1/2 + F1 broker) | Verified | `permissions.py`, `safety.py`, `fleet/approvals.py` |
| Cancellation / interrupt | Verified | `/api/v2/sessions/:id/cancel`, `Session` stop |
| Context compaction | Verified | `context.py` (`CompactionState`, `THRESHOLD_NOTE`) |
| Usage tracking (provider-reported) | Verified | `fleet_usage` migration v11, `compat.py` |
| Background execution | Partial | detached shells exist (`fleet/shells.py`); no general background task queue |
| Multi-session concurrency | Partial | per-bot locks; no global scheduler beyond routines |
| Error recovery / retry | Partial | provider errors recorded; no automatic retry policy |

### B. Providers and models

| Capability | Status | Evidence |
|---|---|---|
| OpenRouter adapter | Verified (fake transport) | `providers/` |
| Google AI Studio adapter | Verified (fake transport) | `providers/` |
| NVIDIA adapter | Verified (fake transport) | `providers/` |
| Anthropic adapter (opt-in) | Partial | `providers/` |
| OpenAI-compatible adapter | Verified (fake transport) | `providers/` |
| Auto-chain / fallback | Verified | `providers/registry.py` |
| Live-provider end-to-end | Blocked | no API keys on host; `tests/test_live_smoke.py` skips |
| Model listing / rate-limit disable | Partial | OpenCode parity gap (Milestone 4) |

### C. Tools

| Capability | Status | Evidence |
|---|---|---|
| read_file / write_file / edit_file | Verified | `session.ALL_TOOLS`, `RealTools` |
| glob / grep | Verified | `session.py` |
| run_shell (with AST safety) | Verified | `shell_ast.py`, `safety.py` |
| Task (subagent delegation) | Verified | `session.py`, `subagent.py` |
| send_to_bot (agent-to-agent) | Verified | `fleet/delegation.py`, `fleet/tools.py` |
| create/update/list_task | Verified | `fleet/tasks.py` |
| save_file (Library) | Verified | `fleet/library.py` |
| ask_user | Verified | `fleet/asks.py` |
| File move/rename/delete/watch | Missing | not implemented |
| Apply patch / diff compare | Missing | not implemented |
| Git operations (status/log/diff/branch/commit) | Partial | Duet Review tab shells out; no dedicated tool |
| Web search / fetch | Missing | no web tools in runtime (only browser tool in OpenCode harness) |
| Browser automation | Missing | no browser tool in Keel runtime |
| Utility tools (calc, JSON, conversion) | Missing | not implemented |
| Tool registry with schemas/validation | Verified (Phase 2) | `keel/tools/registry.py` (`ToolRegistry`); `session.ALL_TOOLS`/`TOOL_SCHEMAS` now derived from `keel/tools/native.py`; runtime dispatch uses `self.tools.execute` |
| Permission levels per tool | Verified | `permissions.py` modes + F1 broker |

### D. Skills

| Capability | Status | Evidence |
|---|---|---|
| SKILL.md discovery (bundled/user/project) | Verified | `skills.py` |
| Frontmatter parsing + validation | Verified | `skills.py` |
| Injection scanning | Verified | `skills.py` |
| Scope trust (project untrusted) | Verified | `skills.py` |
| Skills API endpoint | Verified | `/api/skills` |
| Install/remove/enable/disable/update | Missing | no manager, no CLI |
| Versioning / dependencies | Missing | not implemented |
| Auto-load by task context | Missing | not implemented |
| Skills UI management | Partial | Cowork "Customize: Skills" lists discovered skills only |

### E. MCP

| Capability | Status | Evidence |
|---|---|---|
| stdio servers | Verified | `mcp.py` |
| Tool discovery + execution | Verified | `mcp.py`, v2/fleet wiring |
| Project-scope approval (hash) | Verified | `mcp.py` |
| Output cap | Verified | `MCP_OUTPUT_CAP` |
| HTTP transports | Missing | stdio only |
| Reconnection / health monitoring | Missing | no reconnect logic |
| Resource/prompt discovery | Missing | tools only |
| Server logs UI | Missing | no UI |
| Multiple server config management | Partial | settings.json + fleet connectors |

### F. Plugins and connectors

| Capability | Status | Evidence |
|---|---|---|
| MCP servers as connectors | Partial | fleet connectors UI + handshake |
| Plugin discovery/manifest/lifecycle | Missing | no plugin system |
| Credential storage (local) | Verified | `settings_store.py`, `~/.keel` |
| Connector authentication flows | Partial | settings-based; no OAuth flows |
| Plugin API for developers | Missing | not designed |

### G. Commands and workflows

| Capability | Status | Evidence |
|---|---|---|
| Built-in slash commands | Verified | fleet Duet slash palette (`/context`, `/model`, `/shell`, `/review`, `/open`, `/help`) |
| User/project/global commands | Missing | no command manager |
| Command templates / arguments | Missing | not implemented |
| Reusable workflows | Missing | not implemented |
| Command discovery UI | Missing | not implemented |

### H. Subagents and orchestration

| Capability | Status | Evidence |
|---|---|---|
| Task tool (subagent) | Verified | `session.py`, `subagent.py` |
| Agent-to-agent delegation (send_to_bot) | Verified | `fleet/delegation.py` |
| Hop cap (2) + cycle detection | Verified | `fleet/delegation.py` |
| Groups (2-3 members) | Verified | `fleet/groups.py` |
| Parallel execution | Missing | delegation is synchronous inline; no true parallel scheduler |
| Specialized agent roster (research/coding/debug/…) | Missing | no agent type system |
| Agent-specific instructions/tools/model | Partial | fleet bot config (provider/model/notes) |
| Agent-to-agent handoff structure | Partial | reply returned as tool result |

### I. Memory and project intelligence

| Capability | Status | Evidence |
|---|---|---|
| Session transcript persistence | Verified | `transcript.py`, SQLite rows |
| Agent notes (per bot) | Verified | fleet bots |
| Project registry + path containment | Verified | Duet projects (schema v7) |
| File tree listing | Verified | Duet |
| Automatic memory / retrieval | Missing | Fleet roadmap explicitly defers (F5) |
| Project indexing / symbols / deps | Missing | not implemented |
| Context compression / token budgeting | Partial | `context.py` compaction |
| Ignore rules | Missing | not implemented |

### J. Hooks and automation

| Capability | Status | Evidence |
|---|---|---|
| Hook bus with 33 events | Partial | `hooks.py` defines `KNOWN_EVENTS`; only PreToolUse/PostToolUse wired |
| Command handlers (exit 0/2 protocol) | Verified | `hooks.py` |
| Enable/disable controls | Missing | settings-based; no UI manager |
| Execution logs | Missing | no audit log for hooks |

### K. Browser and computer interaction

| Capability | Status | Evidence |
|---|---|---|
| Sandboxed iframe preview (dev servers) | Partial | Duet Browser tab |
| Browser automation (open/navigate/click/fill) | Missing | no tool |
| Screenshots | Missing | not implemented |

### L. Desktop and UI

| Capability | Status | Evidence |
|---|---|---|
| Electron shell + Python sidecar | Verified | `desktop-app/` |
| Four surfaces (Cowork/Code/Duet/Fleet) | Verified | site + fleet UI |
| Settings (providers, general) | Verified | `site/app.html` |
| Unified management UI (tools/skills/MCP/plugins/etc.) | Missing | no such screens |
| Responsive / PWA | Verified | `sw.js` |

### M. Security and permissions

| Capability | Status | Evidence |
|---|---|---|
| Centralized permission enforcement (backend) | Verified | `permissions.py`, `safety.py`, F1 broker |
| Workspace path containment | Verified | Duet project tools |
| Credential storage (local) | Verified | `settings_store.py` |
| Audit logs | Partial | `fleet_audit` (fingerprint only) |
| Path traversal protection | Verified | Duet |
| Plugin/MCP trust boundaries | Partial | MCP project-scope approval; no plugin boundary |

### N. Release and distribution

| Capability | Status | Evidence |
|---|---|---|
| Python release manager (build/publish/verify) | Verified | `keel/release` |
| GitHub Releases hosting | Verified | v0.1.1 published, verified |
| CI builds all platforms | Verified | workflow |
| Signed installers | Blocked | no certificates |

## 3. Top gaps vs. OpenCode

1. **No central tool registry/discovery** — tools are hardcoded in `session.ALL_TOOLS`; MCP tools are ad-hoc. Need a registry with schemas, permission levels, discovery.
2. **No skills management lifecycle** — discovery only; no install/remove/version/enable/disable/auto-load.
3. **MCP is stdio-only** — no HTTP transport, no reconnect/health, no resource/prompt discovery.
4. **No plugin system** — nothing exists; needs manifest + lifecycle + API.
5. **No commands manager / workflows** — only a fixed slash palette.
6. **No specialized agent types / true parallel orchestration** — delegation is inline synchronous.
7. **No automatic memory or project intelligence** — indexing, symbols, deps, ignore rules missing; context compaction exists.
8. **Hooks only PreToolUse/PostToolUse wired** — 33 events declared, 2 wired.
9. **No web/browser tools** in the runtime.
10. **No unified management UI** for the new capabilities.

## 4. Reuse guidance

- Reuse `fleet/db.py` SQLite and `settings_store.py` for all new persistence.
- Reuse `permissions.py` + `fleet/approvals.py` as the single permission engine.
- Reuse `hooks.py` bus for all lifecycle events.
- Reuse `mcp.py` client as the base for expanded transports.
- Reuse `skills.py` parser for skill discovery.
- Reuse `session.py` turn loop as the single execution engine (extend, don't duplicate).
- Reuse `compat.py` `/api/v2` as the public API surface; extend it.
- Reuse Electron + Python sidecar; do not introduce Node backend.

## 5. Risks

- Scope is very large; must be phased.
- Parallel execution must be real (async/threaded), not simulated.
- Security boundary must remain in Python; UI only reflects.
- Backward compatibility for `fleet.db` schema and `/api/v2`.
- Test burden: every new capability needs real tests.
- Avoid duplicating OpenCode's full surface; prioritize high-value capabilities.

## 6. Recommended next step

Proceed to BUILD MODE only after reviewing the architecture and roadmap docs. Start with Phase 1 (audit already done) and Phase 2 (unified runtime + tool registry).
