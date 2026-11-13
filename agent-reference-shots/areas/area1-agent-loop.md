# Area 1 — The agent loop: observed event trace

**Subject:** Claude Code CLI v2.1.306 (Windows 11 Pro, win32-x64)
**Date:** 2026-10-21
**Method:** published CLI only (`claude -p ... --output-format stream-json --verbose`). No decompilation, no binary modification, no credential access.

## Command

```
claude -p "List the files in this directory, then read demo.py, then state what it prints. Use tools." \
       --output-format stream-json --verbose
```

Run in an isolated scratch directory containing only `demo.py` (3 lines) and the capture files.

## Sanitized trace

`sanitized-agent-loop.jsonl` — 49 events, one JSON object per line. Absolute paths replaced with
`<PROJECT_ROOT>`, the OS username with `<USER>`, the session UUID with `<UUID>`. No secrets present.

### Event census

| `_event` | Count |
|---|---|
| `system/init` | 1 |
| `assistant/text` | 4 |
| `assistant/thinking` | 10 |
| `assistant/tool_use` | 12 |
| `user/tool_result` | 12 |
| `system/permission_denied` | 7 |
| `system/task_started` | 1 |
| `system/task_notification` | 1 |
| `result` | 1 |

## What the trace establishes

1. **One `system/init` precedes everything.** It carries `cwd`, `session_id`, the full `tools` array
   (28 names), `mcp_servers` (name + `status: "pending"` + `source`), `model`, `permissionMode`,
   `claude_code_version`, `agents` (subagent registry), `output_style`, `additional_directories`,
   and `slash_commands`.

2. **The cycle is `assistant/tool_use` → `user/tool_result`, keyed by `tool_use_id`.**
   Every `tool_use` carries an `id`; the matching `tool_result` returns the same id in
   `tool_use_id`. This is the correlation key an implementer needs.

3. **Multiple tool calls can be emitted in one assistant message, and their results can arrive in a
   different order.** Observed at index 2-5: `PowerShell` (id `..._1`) and `Read` (id `..._2`)
   requested together; the `Read` result arrived *first* (`..._2`), the `PowerShell` result second
   (`..._1`). Same at index 12-15: `Read` `..._1` and `Read` `..._2` requested together, results
   returned in order. At index 24-26, `Glob` and `PowerShell` were requested together and the
   `PowerShell` denial arrived *before* the `Glob` success.

4. **A denied tool call still occupies a `tool_result` slot**, with `is_error: true` and the
   rejection message as the content. The model receives the rejection as data and continues.

5. **`system/permission_denied` is emitted *before* the corresponding `tool_result`.** Ordering in
   the trace: `permission_denied` (index 4) → `user/tool_result` (index 5).

6. **The `decision_reason_type` field discriminates the deciding component.** Observed values:
   `subcommandResults` (a per-subcommand permission check inside a compound command) and `other`
   (a generic "requires approval"). The SDK reference documents the wider set as `"rule"`,
   `"mode"`, `"classifier"`, `"asyncAgent"`.

7. **Failure messages are diagnostic, not generic.** Examples observed:
   - `"Command contains malformed syntax that cannot be parsed: pwsh exited with code 1: The command line is too long."`
   - `"ls in '<dir>' was blocked. For security, Claude Code may only list files in the allowed working directories for this session: ..."`
   - `"This Bash command contains multiple operations. The following parts require approval: python -I demo.py, echo \"exit=$?\""`
   - `"This command requires approval"`

8. **The model visibly course-corrects on tool failure.** The thinking blocks show a progression:
   PowerShell parse error → "Let me try Bash" → path-quoting failure → "The path quoting confused
   it. Let me use Glob instead" → Glob success. This is the observable form of the documented
   "gather context, take action, verify results" loop adapting.

9. **Read-only and state-changing calls can be requested in the same assistant message.** `Glob`
   (read) and `PowerShell` (execution) were requested together at index 24-25.

10. **The final `result` message is the loop terminator.** Observed fields: `subtype: "success"`,
    `stop_reason: "end_turn"`, `num_turns: 13`, `duration_api_ms`, `duration_ms`, `total_cost_usd`,
    `usage` (with `input_tokens`, `output_tokens`, `cache_read_input_tokens`,
    `output_tokens_details.thinking_tokens`, `cache_creation`), `permission_denials` (array of
    `{tool_name, tool_use_id, tool_input}`), `is_error: false`, `safety_stops: 0`,
    `subagent_stats` (spawned/requested/completed/failed/killed/refused counters), `modelUsage`
    (per-model breakdown with `contextWindow`, `maxOutputTokens`, `canonicalModel`).

11. **`num_turns` counts loop iterations, not model calls.** 13 turns produced 12 tool calls and
    roughly 14 assistant messages — the count reflects the evaluate/execute cycles.

12. **Long Bash commands are a separate execution surface.** `system/task_started` and
    `system/task_notification` bracket a background-capable Bash invocation, carrying `task_id`,
    `run_id`, `tool_use_id`, `description`, `task_type: "local_bash"`, and `is_backgrounded: false`.

13. **The final answer can explicitly report unverified work.** The result text ends with: *"One
    note on verification: I read the source rather than executing it... the \"3\" is from static
    reading of the three-line file, not from a captured run."* It also reports an unrelated
    failure: *"the `rea` MCP server failed to connect (30s timeout), so its tools are unavailable
    this session."*

## Observed tool-call input shapes

```json
{"type":"tool_use","id":"call_function_8h46i0zov6nv_1","name":"Glob","input":{"pattern":"*"}}
{"type":"tool_use","id":"call_function_8h46i0zov6nv_2","name":"Read","input":{"file_path":"<ABSOLUTE_PATH>"}}
{"type":"tool_use","id":"call_function_3nuq2r9n18na_1","name":"PowerShell",
 "input":{"command":"Get-ChildItem -Force | Select-Object Mode, Length, Name","description":"List files in working directory"}}
{"type":"tool_use","id":"call_function_4nnzvjw2lgxs_1","name":"Bash",
 "input":{"command":"python -I demo.py","description":"Run demo.py to verify output"}}
```

Note: `description` accompanies execution calls; `file_path` is absolute for `Read`; `Glob` accepts
`pattern` and optional `path`.

## Other observed artefacts (from the same session family)

- `~/.claude/projects/<path-with-non-alphanumerics-replaced-by-dashes>/<session-id>.jsonl` —
  per-project transcript directory. Observed project slugs, e.g.
  `C--Users-Admin-Desktop-Claude-clone-scratch-probe`.
- `~/.claude/file-history/<session-id>/` — per-session file snapshot directories (checkpoint
  storage).
- `~/.claude/plans/<slug>.md` — plan-mode files, named `<prompt-slug>-<adjective>-<noun>.md`,
  with a Markdown structure of `# Title`, `## Context`, `## Implementation`, `## Files`,
  `## Verification`.
