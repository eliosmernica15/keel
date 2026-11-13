# Black-box protocol observations — Claude Code 2.1.306

All observations below are from running the **published** CLI on this machine.
No decompilation, no source extraction. See `TERMS-NOTES.md`.

## 1. Session bootstrap — `system` / `init` message

The first event on the stream in `--output-format stream-json --verbose` mode.
Observed fields:

| Field | Example value | Notes |
|---|---|---|
| `type` | `"system"` | |
| `subtype` | `"init"` | |
| `cwd` | `C:\...\scratch-probe` | resolved working dir |
| `original_cwd` | same | pre-`--add-dir` value |
| `session_id` | `fd925683-…` | UUIDv4 |
| `tools` | `["Task","Bash",…,"Write"]` | full built-in set, see §2 |
| `mcp_servers` | `[{"name":"rea","status":"pending","source":"user"}]` | |
| `model` | `minimax/minimax-m3.1-flash:free` | |
| `permissionMode` | `"default"` | |
| `slash_commands` | 60+ names | skills + built-in commands |
| `terminal_slash_commands` | `["doctor","color","focus","reload-plugins"]` | render locally, no model call |
| `apiKeySource` | `"none"` | how auth was resolved |
| `claude_code_version` | `"2.1.306"` | |
| `output_style` | `"default"` | |
| `agents` | `["claude","Explore","general-purpose","Plan","statusline-setup"]` | subagent registry |
| `skills` | 18 names | resolved skill registry |
| `plugins` | 3 builtin entries | `cc-plugin-agents-md`, `cc-plugin-telemetry`, `cc-plugin-plugin-authoring` |
| `capabilities` | `["interrupt_receipt_v1",…,"mcp_call_result_not_for_model_v1"]` | protocol feature flags |
| `analytics_disabled` / `product_feedback_disabled` | `false` | |
| `memory_paths` | `{"auto":"…/memory/"}` | per-project memory dir |
| `additional_directories` | `[]` | from `--add-dir` |
| `messaging_socket_path` | `\\.\pipe\LOCAL\cc-msg-…` | local IPC for control messages |
| `fast_mode_state` / `fast_mode_disabled_reason` | `"off"` / `"sdk_opt_in_required"` | |
| `per_turn_effort_active` | `false` | |
| `view_mode` | `"default"` | |
| `powershell_path` | full path to `pwsh.exe` | on Windows, both `Bash` and `PowerShell` tools exist |
| `uuid` | distinct from `session_id` | per-process run id |

## 2. Built-in tool set (default, unrestricted)

`Task, Bash, CronCreate, CronDelete, CronList, DesignSync, Edit, EnterWorktree,
ExitWorktree, Glob, Grep, ListAgents, Monitor, NotebookEdit, PowerShell,
PushNotification, Read, ReportFindings, ScheduleWakeup, SendMessage, Skill,
TaskStop, ToolSearch, WebFetch, WebSearch, Workflow, Write`

### Tool-set mutation is observable at `init`

| Invocation | `tools` in init |
|---|---|
| (default) | all 28 |
| `--tools ""` | `[]` |
| `--bare` | `Bash, Edit, PowerShell, Read` — and `mcp_servers: []` |
| `--restricted` | 21 tools: all above **minus** `Bash`, `PowerShell`, `WebFetch`, `Monitor`; `mcp_servers: []`; `slash_commands` pruned to the non-customisation set |

`--restricted` is the documented "read-mostly" mode: code execution and
web fetching removed, file tools confined to working dirs, and
`bypassPermissions` refused.

## 3. Tool call / result wire format

**Assistant → tool call** (`type: "assistant"`, content block `type: "tool_use"`):

```json
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"call_function_…_1",
  "caller":{"type":"direct"},"name":"Read",
  "input":{"file_path":"…"}}]},
 "parent_tool_use_id":null,"session_id":"…","uuid":"…",
 "timestamp":"2026-10-21T17:34:18.449Z","request_id":"gen-…"}
```

Note `wire_tool_inputs` — a parallel map of tool_use id → the exact JSON
sent on the wire, separate from `input`. This is the audit copy.

**Tool → result** (`type: "user"`, content block `type: "tool_result"`):

```json
{"type":"user","message":{"role":"user","content":[
  {"tool_use_id":"call_function_…_1","type":"tool_result","content":"1\tdef greet(n):…"}]},
 "tool_use_result":{ …typed payload… },
 "tool_result_meta":[{"id":"…","permission_decision":{
   "decision":"accept","source":"config","reason_type":"rule"}}]}
```

Results are delivered as **`user`**-role messages, not a separate result type.
`tool_result_meta[].permission_decision` records why the call was permitted:
`decision` ∈ `accept`/`reject`/`ask`; `source` ∈ `config`/`user`/`…`;
`reason_type` ∈ `rule`/`mode`/`subcommandResults`.

### Read result payload
`tool_use_result` = `{type:"text", file:{filePath, content, numLines, startLine, totalLines}}`

### Glob result payload
`tool_use_result` = `{filenames:[…], durationMs, numFiles, truncated, totalMatches, countIsComplete}`
— note `truncated` and `countIsComplete` flags: truncation is *declared*, not silent.

### Grep result payload
Not directly observed, but Glob's sibling shape implies
`{filenames, content, durationMs, …}`.

### Edit result payload
```json
{"filePath":"…","oldString":"…","newString":"…","originalFile":"…",
 "structuredPatch":[{"oldStart":1,"oldLines":5,"newStart":1,"newLines":5,
   "lines":[" def greet(n):","-    return f'Hello, {n}!'","+    return f'Goodbye, {n}!'"," "," print(greet('world'))"," "]}]},
 "userModified":false,"replaceAll":false}
```
`structuredPatch` is a **unified-diff-shaped** structure with ` ` / `-` / `+` line
prefixes — this is what the UI renders as the diff. `userModified:false` flags
that the file changed on disk since it was last read (i.e. a concurrent-edit
guard). `replaceAll` echoes the request.

### Write result payload
```json
{"type":"create","filePath":"…","content":"alpha\n","structuredPatch":[],
 "originalFile":null,"userModified":false}
```
`type` is `"create"`; `originalFile:null` distinguishes create from overwrite.

### Bash result payload — success
```json
{"stdout":"Python 3.11.9","stderr":"","interrupted":false,
 "isImage":false,"noOutputExpected":false}
```

### Bash result payload — failure
The `tool_result` content block carries `"is_error":true` and the text
`"Exit code 1\ncat: nonexistent-file-xyz.txt: No such file or directory"`,
while `tool_use_result` is the string
`"Error: Exit code 1\ncat: nonexistent-file-xyz.txt: No such file or directory"`.
**Exit code is surfaced in-band in the tool result**, not only in a separate field.

### Unknown tool / skill error
`{"content":"<tool_use_error>Unknown skill: demo-skill</tool_use_error>","is_error":true}`
and `tool_use_result` = `"Error: Unknown skill: demo-skill"`.
Tool errors are returned to the model as `is_error: true` results — the turn
continues, the agent retries.

### Command-too-long / pre-parse failure
```json
{"content":"Command contains malformed syntax that cannot be parsed: pwsh exited with code 1: The command line is too long.",
 "is_error":true}
{"non_execution_kind":"user-rejected","permission_decision":{"decision":"reject","source":"config"}}
```
A pre-execution parse failure is annotated with `non_execution_kind` — the
command never ran.

## 4. Permission denials

Headless (`-p`) with `--permission-prompts none`:

```json
"permission_denials":[{"tool_name":"Write",
  "tool_use_id":"call_function_…_1",
  "tool_input":{"file_path":"…\\denied.txt","content":"x"}}]
```
and the file is **not** created. The agent's own summary:
> "the write was blocked by the permission system … this session has no
> approval surface, so the request was auto-denied."

Deny-rule matching observed: `"deny": ["Bash(git push*)"]` blocked both
`git push origin main` and the `cd … && git push origin main` variant — i.e.
the matcher inspects the command, not just the leading token. The blocked
call is reported in `permission_denials` with the **full** `tool_input`, and
the agent then continued, investigated the repo state, and explained what
would be needed — it did not retry the denied action.

Allow-rule matching observed: `"allow": ["Bash(git status)"]` →
`permission_decision: {decision:"accept", source:"config", reason_type:"rule"}`.

## 5. Subagent delegation wire format

Spawn: `tool_use` with `name:"Agent"`, input
`{description, subagent_type, prompt, run_in_background}`.

Lifecycle events on the same stream:

```json
{"type":"system","subtype":"task_started","task_id":"af3b4f1234a010130",
 "run_id":"0mvieaclu-eb2216e2","tool_use_id":"call_function_…_1",
 "description":"…","subagent_type":"Explore","is_backgrounded":false,
 "spawn_depth":1,"task_type":"local_agent","prompt":"…"}

{"type":"system","subtype":"task_progress","task_id":"…",
 "description":"Reading hello.py","usage":{"total_tokens":4,"tool_uses":1,"duration_ms":1870},
 "last_tool_name":"Read"}
```

Subagent activity is attributed with **`parent_tool_use_id`** on every nested
message, plus `agent_id`, `subagent_type`, `task_description`. The subagent's
own assistant/tool messages are emitted on the *parent* stream — so a single
JSONL is a complete transcript of the whole tree.

The nested permission decision uses `reason_type:"mode"` (subagent inherits
the parent's mode) rather than `"rule"`.

## 6. Plan mode

`--permission-mode plan`:
- The file was **not** created (`Test-Path plan-test.txt` → `False`).
- A plan document was written to `C:\Users\Admin\.claude\plans\<slug>.md`,
  where the slug is a generated kebab-case name (`create-a-file-named-vivid-toucan.md`).
- Plan document structure (observed):
  `# <Title>` / `## Context` / `## Implementation` (numbered steps) /
  `## Files` (New: / Modified:) / `## Verification`.
- The agent explicitly noted it could not call `ExitPlanMode` because that
  tool was not in the session's tool set (it was deferred), and therefore
  **presented the plan inline for review** rather than silently proceeding.

## 7. Result envelope (`--output-format json`)

```json
{"type":"result","subtype":"success","is_error":false,"result":"…",
 "session_id":"…","uuid":"…","duration_ms":1755,"duration_api_ms":1644,
 "num_turns":1,"stop_reason":"end_turn","terminal_reason":"completed",
 "total_cost_usd":0.0053802,
 "usage":{"input_tokens":1310,"cache_read_input_tokens":201,"output_tokens":5,
   "output_tokens_details":{"thinking_tokens":0},
   "server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},
   "cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":0},
   "service_tier":"standard","speed":"standard","fallback_credit":null},
 "modelUsage":{"<model>":{"inputTokens":…,"outputTokens":…,"cacheReadInputTokens":…,
   "contextWindow":200000,"maxOutputTokens":32000,"thinkingTokens":0,
   "canonicalModel":"…","provider":"firstParty","costBasis":"unknown"}},
 "permission_denials":[],"safety_stops":0,
 "subagent_stats":{"spawned":0,"requested":{…},"started_in_background":0,
   "max_depth":0,"spawned_by_subagents":0,"completed":0,"failed":0,
   "killed":{…},"refused":{"depth_limit":0,"concurrency_limit":0,"budget":0}},
 "fast_mode_state":"off","fast_mode_disabled_reason":"sdk_opt_in_required",
 "ttft_ms":1734,"ttft_stream_ms":1733,"time_to_request_ms":112,
 "first_content_frame_ms":1733,"queued_turn_count":0,"result_index":0}
```

Structured output: with `--json-schema`, the result carries an extra
`"structured_output":{"colors":["blue","green"]}` field alongside the
stringified `result`, and `stop_reason` becomes `"tool_use"`.

`--json-schema` example from `--help`:
`{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}`

## 8. Session persistence and resume

- Transcripts are **JSONL** at
  `C:\Users\Admin\.claude\projects\<sanitized-cwd>\<session-id>.jsonl`
- The cwd is sanitised into a directory name: `C--Users-Admin-Desktop-Claude-clone-scratch-probe`
  (spaces → `-`; path separators → `-`).
- `--resume <session-id>` restores conversation state.
  Verified: session told the model "4242"; a *separate* process, given only
  `--resume <id>`, answered `4242` with `num_turns: 1`.
- `--continue` / `-c` resumes the most recent conversation in the current dir.
- `--fork-session` creates a new session id instead of reusing the original.
- `--no-session-persistence` disables saving (print mode only).
- Per-project `memory/` directory sits alongside the transcripts.

## 9. Background sessions

`claude --bg "<prompt>"` prints:
```
Starting background service…
backgrounded · 12e409f5
  claude agents             list sessions
  claude attach 12e409f5    open in this terminal
  claude logs 12e409f5      show recent output
  claude stop 12e409f5      stop this session
```

`claude agents --json` returns a JSON array of sessions with
`pid, cwd, kind (interactive|background), startedAt, sessionId, name, status`
and, for background sessions, `id` and `state` (`"working"`).

`claude logs <id>` prints the **raw ANSI terminal stream** of the background
session — i.e. the TUI, not a summarised transcript.

## 10. TUI rendering (captured from `claude logs`)

```
 ▐▛███▛█   Claude Code v2.1.306
▝▜██████▀  minimax/minimax-m3.1-flash:free · API Usage Billing
 ▝▝   ▝▝   ~\Desktop\Claude clone

⚠ Model "minimax/minimax-m3.1-flash:free" isn't recognized · context assumed to be 200k tokens · update Claude Code, or see https://code.claude.com/docs/en/model-config

❯ List the files in the current directory and report them.

· Undulating…
● high · /effort
────────────────────────────
❯
────────────────────────────
  ⏸ manual mode on · ← for agents
```

Layout: block-character ASCII banner → model + billing tier → cwd (with `~`
home-relative shortening) → warning banner → prompt line with `❯` →
spinner ("Undulating…") → status bar showing **effort level** (`● high`) and
current slash command (`/effort`) → input box → footer showing
**permission mode** (`⏸ manual mode on`) and an agents hint (`← for agents`).

## 11. MCP behaviour

- Servers come from user config, project `.mcp.json`, or `--mcp-config`.
- `claude mcp list` health-checks: `rea: cmd.exe /d /c npx -y rea-agents@6.7.0 mcp - √ Connected`
- `claude mcp get <name>` shows scope, status, type, command, args, environment.
- **MCP tools are NOT in the `init` tool list.** They are *deferred* and
  resolved on demand via the `ToolSearch` tool.
- `ToolSearch` result shape:
  `{"matches":["CronCreate"],"query":"rea list_documents","total_deferred_tools":13}`
  or, when a server is still connecting:
  `{"matches":[],"query":"…","total_deferred_tools":13,"pending_mcp_servers":["rea"]}`
- The tool-result content for a miss is a *human-readable guidance string*:
  > "No matching deferred tools found. Some MCP servers are still connecting:
  > rea. Their tools will become available shortly — try searching again. If
  > you're looking for a capability rather than a specific tool name, try
  > keywords that might match the server's purpose (e.g., 'slack message',
  > 'calendar event'). Once you find a matching tool, call it directly — do
  > not stop after searching."
- `init` reported `{"name":"rea","status":"pending"}` — MCP connects
  **asynchronously** relative to session start, and the model is told to retry.
- Naming convention observed for MCP tool names: `mcp__<server>__<tool>`.

## 12. Skills

- Project skills live at `<project>/.claude/skills/<name>/SKILL.md`; user
  skills at `~/.claude/skills/<name>/SKILL.md`.
- A project skill with frontmatter
  `---\nname: demo-skill\ndescription: …\n---` was **auto-discovered**: it
  appeared in `init.skills` and in `init.slash_commands` without any config.
- `Skill` tool input is `{skill: "<name>"}`.
- Unknown skill → `is_error: true`, content
  `<tool_use_error>Unknown skill: demo-skill</tool_use_error>`.

## 13. CLAUDE.md

- A `CLAUDE.md` at the project root was **auto-discovered and injected**.
  Verified behaviourally: with
  `CLAUDE.md` = "Always greet the user with 'PROBE-GREETING'",
  an unprompted question ("Introduce yourself in one sentence.") was answered
  `"PROBE-GREETING — I'm Claude Code, …"`. The instruction reached the model
  and changed its output.
- `--bare` disables CLAUDE.md auto-discovery entirely (documented).

## 14. Workspace trust

`claude --bg` in an untrusted directory refused:
> "Workspace not trusted. Run `claude` in <dir> once and accept the trust
> prompt, then retry."

Print mode (`-p`) **skips** the trust dialog (documented in `--help`).

## 15. `auto-mode` — a built-in safety classifier

`claude auto-mode defaults` dumps the shipped rule set as JSON, with four
rule groups: `allow`, `soft_deny`, `hard_deny`, `environment`. Observed rule
names include:

- *Allow* — "Security Discussion", "Transient Retry", "Test Artifacts",
  "Local Operations"
- *Deny* — "Irreversible Local Destruction", "Sensitive-Source Provenance"
- Concepts — "Credential Exploration", "Exfil Scouting", "Auto-Mode Bypass",
  "User Intent Rule #2" (scope escalation)

This classifier is a **second, model-based safety layer above the rule-based
permission system**, and it fires on the agent's *behaviour*, not just on the
tool call. Observed rejections in this session:

| Trigger | Reason label |
|---|---|
| `--dangerously-skip-permissions` on a tool call | `[Safety Bypass Flag]` |
| Writing to the harness's own `.claude/settings.local.json` | `[Self-Modification]` |
| Writing `CLAUDE.md` into the project root via shell | `[Self-Modification]` |

The denial message explicitly offers a sanctioned alternative rather than
only refusing.

## 16. Known quirks observed on this host

- `claude -p` emits a line to **stderr**:
  `[claude-code:unrecognized_model] {"model":"…","query_source":"sdk"}`
  when the model string is not one the build recognises. Scripts parsing
  stdout as JSON must tolerate a non-JSON prefix.
- `apiKeySource:"none"` while `ANTHROPIC_BASE_URL` points at a third-party
  gateway; `claude doctor` reports
  "Not connected to the Anthropic API (api.anthropic.com)".
- On Windows the harness exposes **both** `Bash` (Git Bash) and `PowerShell`
  (`pwsh.exe`) tools, and reports the resolved `powershell_path` in `init`.
- `PowerShell` tool errors can be triggered by an over-long command line
  ("The command line is too long"), which surfaces as a *parse* failure
  with `non_execution_kind: "user-rejected"` rather than a runtime error.
