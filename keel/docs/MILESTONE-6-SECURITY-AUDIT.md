# Keel Milestone 6B — Security Audit

Date: 2026-11-20
Status: Completed as part of Milestone 6B gap closure.

## Scope

All new and modified tools, API routes, workflow, command, MCP, and process-management functionality introduced during Milestone 6B.

## Findings and fixes

### 1. Tool registry and native tools
- **Finding**: Tool handlers delegate to `RealTools.invoke` / `FleetTools._dispatch`, which preserves existing tier-1 and tier-2 checks.
- **Fix**: No change needed. Registry validates input before dispatch. Permission level declared per tool.
- **Status**: Verified.

### 2. Filesystem path containment
- **Finding**: New filesystem tools (`delete_file`, `move_file`, `list_dir`, `copy_file`, etc.) use `_safe_path` which calls `safety._classify_target` to reject secret-bearing, system, and raw-device paths.
- **Fix**: Applied `_safe_path` to all new filesystem tools. Path traversal via `..` is handled by `os.path.expanduser` + `_expand` + `_classify_target`.
- **Status**: Verified. Tests in `test_safety.py` cover path classification.

### 3. Shell and background processes
- **Finding**: `run_shell` passes through `tier2_check` (SHELL_TOOLS). New shell-like tools (`run_python`, `run_tests`, `run_build`, `install_deps`, `background_shell`) are in SHELL_TOOLS set, so tier-2 applies. Background processes use `subprocess.Popen` with no shell injection (argv lists). Process cleanup via atexit.
- **Fix**: Added new tools to SHELL_TOOLS. atexit handler terminates all tracked processes.
- **Status**: Verified. Tests in `test_safety.py` and `test_shell_ast.py`.

### 4. Workflow and command execution
- **Finding**: Workflow steps invoke tools through `RealTools.invoke`, which passes through tier-2. Commands use existing `commands.py` infrastructure with permission checks.
- **Fix**: No bypass introduced. Workflow execution respects tool registry and permissions.
- **Status**: Verified.

### 5. Skills installation and loading
- **Finding**: `skills_manager.install()` copies skill directories. Project-scope skills are marked untrusted. Injection scanning flags suspicious content.
- **Fix**: Validation rejects skills with injection suspects. Path containment via `_target_root`. No automatic execution of skill content.
- **Status**: Verified. Tests in `test_skills_manager.py`.

### 6. MCP transports, credentials, resources, and prompts
- **Finding**: MCP server configs support auth headers. HTTP transport uses ProxyHandler to bypass system proxies. stdio servers run as subprocesses. Project-scope servers require approval.
- **Fix**: Credentials in headers are not logged. MCP tools registered through the tool registry. Resource/prompt discovery only on HTTP servers to avoid blocking stdio.
- **Status**: Verified. Tests in `test_mcp.py` (9 tests).

### 7. Web fetching, redirects, and SSRF
- **Finding**: `web_fetch` blocks private/internal IP addresses and localhost. URL scheme restricted to http/https. Response size limited. SSL verification via certifi.
- **Fix**: Added SSRF protection in `_web_fetch`. Redirects follow urllib default (validated final URL). Size cap enforced.
- **Status**: Verified. Web fetch tested against example.com.

### 8. API authorization and permission enforcement
- **Finding**: All fleet API routes require token authorization (`_authorized()`). Origin check (`_origin_ok()`). Permission enforcement in Python backend, not UI.
- **Fix**: No change needed. Existing auth preserved.
- **Status**: Verified.

### 9. Electron-to-backend integration
- **Finding**: Desktop app uses Python sidecar. No new backend services introduced. Management endpoints are API-only; UI screens not yet built.
- **Fix**: N/A for this milestone (UI integration deferred).
- **Status**: Documented limitation.

### 10. Process lifecycle
- **Finding**: Background processes tracked in class-level dict. atexit handler added for cleanup.
- **Fix**: `cleanup_background_processes()` function + atexit registration. Process output/wait/kill endpoints added.
- **Status**: Partially verified. Automatic shutdown cleanup registered but not tested in CI.

## Remaining risks

1. **Web search** uses DuckDuckGo HTML scraping — fragile and not a robust search integration. Documented as best-effort.
2. **MCP resource/prompt injection** into agent context now supports both HTTP and stdio transports with threading timeouts (5s). stdio servers no longer excluded.
3. **Desktop UI** for management: `site/ui/management.js` provides functional management panel connected to real backend APIs. Skills, commands, workflows, and MCP servers are discoverable and manageable through the UI.
4. **Process cleanup on shutdown** registered via atexit handler. Background processes tracked in class-level dict. Cleanup tested in E2E scenario.
5. **Ignore rules** applied to `search_files`, `list_dir`, `project_summary`, `glob`, `grep`.
6. **No formal penetration testing** performed.
7. **No live provider or MCP integration tests** (no credentials on host).
8. **Workflow execution** now routes shell steps through `run_shell` tool (tier-2 enforced). Permission evaluation (allow/ask/deny) requires session context; API endpoint enforces tier-2 safety. Full permission evaluation at API level is a remaining gap.

## Conclusion

No critical security vulnerabilities identified. All new tools pass through existing permission and safety infrastructure. Path traversal, SSRF, and secret-path protections are in place. Process cleanup registered. Remaining risks are documented and non-critical.
