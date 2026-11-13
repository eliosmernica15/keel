# Area 8 — Permission modes, destructive-action safeguards, confirmations

Black-box observations from the published CLI, 2026-10-21. Claude Code 2.1.306 (native build, win32-x64).
No decompilation, no source extraction. See `../TERMS-NOTES.md` and `../PROTOCOL-NOTES.md`.

## 1. `claude --permission-mode` accepts six values; `manual` is an alias for `default`

Command (run from `C:\Users\Admin\Desktop`):

```
for m in dontAsk acceptEdits plan manual bypassPermissions; do
  claude -p "hi" --permission-mode "$m" --output-format stream-json --verbose | head -1
done
```

Observed `permissionMode` field of the `system`/`init` event:

| `--permission-mode` value | `permissionMode` in init event |
|---|---|
| `dontAsk` | `"dontAsk"` |
| `acceptEdits` | `"acceptEdits"` |
| `plan` | `"plan"` |
| `manual` | `"default"` |
| `bypassPermissions` | `"bypassPermissions"` |
| `auto` | `"auto"` |
| (no flag) | `"default"` |
| `--dangerously-skip-permissions` | `"bypassPermissions"` |

`claude --help` declares the choice set as:
`"acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"`.

`manual` normalises to `default` in the wire event — consistent with the docs'
"Manual mode appears under its config value, `default`".

The `system`/`init` event carries `permissionMode` as a top-level field:
`type, subtype, cwd, session_id, tools, mcp_servers, model, permissionMode,
slash_commands, terminal_slash_commands, apiKeySource, claude_code_version,
output_style, agents, skills, plugins, capabilities, analytics_disabled,
product_feedback_disabled, uuid, memory_paths, original_cwd,
additional_directories, messaging_socket_path, fast_mode_state,
fast_mode_disabled_reason, per_turn_effort_active, view_mode, powershell_path`.

## 2. `dontAsk` denies anything that would prompt; read-only Bash still runs

```
claude -p "List the files in the current directory using the Bash tool, then run
'echo done'. Then try to delete a file." \
  --permission-mode dontAsk --tools Bash
```

Observed: `ls -la` and `echo done` ran and returned output. Four mutating
attempts were all refused with the same message:

> "Permission to use Bash has been denied because Claude Code is running in
> don't ask mode."

Attempts refused: `printf '...' > .delete-check.tmp && ls && rm && echo`,
`printf '...' > .delete-check.tmp; ls`, `touch .delete-check.tmp`, and
`rm "C:/Users/Admin/Desktop/.delete-check.tmp"`. The file was never created;
the session's only filesystem interaction was read-only.

## 3. A `deny` rule blocks the command; other commands still run

```
claude -p "Run the bash command 'echo hello-denied-test' and then 'ls -la' ..." \
  --permission-mode default \
  --settings '{"permissions":{"deny":["Bash(echo *)"]}}' --tools Bash
```

Observed tool result for `echo hello-denied-test`:

> "Permission to use Bash with command echo hello-denied-test has been denied."

`ls -la` in the same turn ran normally and returned the directory listing.

## 4. An `ask` rule forces a prompt that cannot be answered in print mode

```
claude -p "Run 'echo ask-rule-test' using Bash." --permission-mode acceptEdits \
  --settings '{"permissions":{"ask":["Bash(echo *)"]}}' --tools Bash
```

Observed: the Bash call was blocked — the harness reported that Bash tool use
had not been granted, so the command did not run. The `ask` rule overrode
`acceptEdits`, which would otherwise have auto-approved a `mkdir/touch/rm/mv/cp/sed`-class
command.

## 5. `--permission-prompts none` denies prompts; read-only Bash still runs

```
claude -p "Run 'echo pp-none-test' ..." --permission-prompts none --tools Bash
```
→ command ran, output `pp-none-test`.

```
claude -p "Run 'touch .pp-none-probe.tmp' ..." --permission-prompts none --tools Bash
```
→ denied; verified the file did not exist afterwards (`ls` → "No such file or
directory"). The `ls` verification read itself was allowed.

## 6. A bare `Read` deny rule blocks the read

```
claude -p "Use the Read tool to read 'C:/Users/Admin/Desktop/API key KOSOVA.txt' ..." \
  --settings '{"permissions":{"deny":["Read(//c/Users/Admin/Desktop/API key KOSOVA.txt)"]}}' \
  --tools Read
```

Observed error, verbatim:

> "File is in a directory that is denied by your permission settings."

Both the forward-slash and backslash spellings failed identically. No file
content was returned.

## 7. Protected-path write is blocked even in `acceptEdits` mode

Setup: created `C:\Users\Admin\Desktop\perm-probe\.git\config` containing `x`.

```
cd perm-probe && claude -p "Write the text 'probe' to the file .git/config using
the Write tool. Report the exact result." --permission-mode acceptEdits --tools Write,Read
```

Observed harness message:

> "Claude requested permissions to edit C:\Users\Admin\Desktop\perm-probe\.git\config
> which is a sensitive file."

The follow-up read reported "file unchanged since your last Read", and the
on-disk content was still `x` after the run. `.git` is a protected directory in
every mode except `bypassPermissions`.

## 8. A bare tool-name deny removes the tool from the model's context

```
claude -p "List which tools you have available. Do not call any tools." \
  --settings '{"permissions":{"deny":["Bash"]}}'
```

Observed: the model reported that `Bash` was **not** in its function list, and
that "the environment mentions a Bash tool, but it isn't in my function list".
Contrast with a scoped deny such as `Bash(echo *)`, which leaves the tool
present and blocks only matching calls (see §3).

## 9. `--restricted` removes the code-running tools

```
claude -p "List which tools you have available. Do not call any tools." --restricted
```

Observed available tools: `Agent, Edit, Glob, Grep, Read, Write, Skill,
ToolSearch, ReportFindings, ScheduleWakeup, ListAgents, SendMessage` (plus
deferred `CronDelete, CronList, DesignSync, EnterWorktree, ExitWorktree,
NotebookEdit, PushNotification, SendMessage, TaskStop, WebSearch`).

No `Bash`, no `PowerShell`, no `WebFetch`. The model noted: "no `Bash` tool is
loaded in this session". `--restricted` also ignores user/project/local
settings files and refuses `bypassPermissions`.

## 10. `claude doctor` output (this machine, custom `ANTHROPIC_BASE_URL`)

```
Claude Code doctor

Running: native (2.1.306)
Commit: 01ae8327ca99
Platform: win32-x64
Path: C:\Users\Admin\.local\bin\claude.exe
Config install method: native
Search: OK (bundled)
Auto-updates: enabled
Auto-update channel: latest
Last update attempt: success → 2.1.306 (2026-10-21)
Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL
Organization policy: not fetched with a custom ANTHROPIC_BASE_URL

Remote Control
Remote Control is only available when using Claude via api.anthropic.com. ANTHROPIC_BASE_URL is set
and does not point at api.anthropic.com, so this session is using a custom endpoint — unset it
(or run in a shell without it) to use Remote Control.
- Not connected to the Anthropic API (api.anthropic.com)
- Not signed in to claude.ai
- claude.ai subscription auth not active
- Sign-in is missing the user:profile scope
- Organization not resolved
- Remote Control availability could not be verified (no server response this session)

No installation issues found.
```

## 11. `claude auto-mode defaults` — the classifier rule corpus is inspectable

`claude auto-mode --help`:

```
Usage: claude auto-mode [options] [command]
Inspect or reset auto mode classifier configuration
Options:
  -h, --help          Display help for command
Commands:
  config              Print the effective auto mode config as JSON: your settings where set, defaults otherwise
  critique [options]  Get AI feedback on your custom auto mode rules
  defaults [options]  Print the default auto mode environment, allow, soft_deny, and hard_deny rules as JSON
  help [command]      display help for command
  reset [options]     Reset auto mode configuration to the shipped defaults by removing the autoMode section from your user settings file
```

`claude auto-mode defaults` emits JSON with exactly four top-level keys:

```
allow       17 entries
soft_deny   72 entries
hard_deny    1 entry
environment  list of named environment slots
```

`allow` entries are exception rules that name a concept, e.g. `"Transient Retry:
Retrying the same or a reformulated action after a transient failure ... is NOT
Auto-Mode Bypass."`, `"Security Discussion: Reading, discussing, reviewing, or
writing security-related code ... is not in itself Credential Exploration"`,
`"Git Push Destination: Pushing to any branch of the session's repo is ordinary"`.

`soft_deny` entries carry a structured tag: `"<Rule Name> [named+specifics —
**must name:** <what must be named>]"`, e.g. `"Git Destructive"`, `"Production
Deploy"`, `"Unverifiable Deletion Target"`, `"Credential Leakage"`, `"Exfil
Scouting"`, `"Self-Modification"`, `"Instruction Poisoning"`, `"Auto-Mode
Bypass"`, `"Session Transcript Tampering"`.

`hard_deny` has one entry: `"Data Exfiltration: Sensitive data crossing the
trust boundary (the trusted repos, domains, and buckets listed in Environment)
as a result of the agent's action"`.

`environment` is a list of named configuration slots, each currently
"None configured": `**Organization**`, `**Primary use of Claude Code**`,
`**Cloud provider(s)**`, `**Repository visibility**`, `**Internal sharing /
snippet hosting**`, `**Org-specific CLIs**`, `**Secrets management**`,
`**CI/CD deploy targets**`, `**Network posture**`, `**Host containment**`,
`**Protected deployment namespaces / environments**`, `**Data retention /
declassification**`, `**Trusted ...**` (truncated).

`claude auto-mode config` prints the *effective* config (user settings where
set, defaults otherwise) and, on this machine, matched `defaults` exactly.

## 12. Live classifier denials observed

The auto-mode classifier fired twice during this investigation, both against
destructive-probe commands I issued deliberately:

```
claude -p "Run the bash command 'rm -rf $HOME/some-nonexistent-probe-dir' ..." \
  --permission-mode bypassPermissions --tools Bash
```

> "Permission for this action was denied by the Claude Code auto mode classifier.
> Reason: [Unverifiable Deletion Target]. ... IMPORTANT: You *may* attempt to
> accomplish this action using other tools that might naturally be used to
> accomplish this goal, e.g. using head instead of cat. But you *should not*
> attempt to work around this denial in malicious ways ... Get as much of the
> rest of the task done as you can, then STOP and explain to the user what you
> were trying to do and why you need this permission. Let the user decide how
> to proceed."

and

```
claude -p "Run 'echo bypass-active-test' with Bash." --dangerously-skip-permissions --tools Bash
```

> "Permission for this action was denied by the Claude Code auto mode
> classifier. Reason: [Safety Bypass Flag]. ..."

Note the second: `--dangerously-skip-permissions` set `permissionMode` to
`"bypassPermissions"` in the init event, but the classifier still refused the
call. This is a *server-side* classifier refusal on a custom gateway, not the
local permission layer.

## 13. Default-mode denial of a path outside the working directories

```
claude -p "Run the bash command 'rm -rf /tmp/nonexistent-probe-x' ..." \
  --permission-mode default --permission-prompts none --tools Bash
```

Observed error:

> "Permission for this tool use was denied. It requires approval, and this
> session has no approval surface — nobody can answer a permission prompt here —
> so it was denied automatically. The action was NOT performed; do not claim it
> succeeded, and do not retry it ... What required approval: rm in
> '/tmp/nonexistent-probe-x' needs approval. The path is outside the working
> directories for this session ('C:\Users\Admin\Desktop',
> 'C:/Users\Admin/Desktop'). Allowing runs the command as written."

A compound form `rm -rf /tmp/nonexistent-probe-x; echo "exit code: $?"` was
also denied, with the reason split per subcommand.

## 14. Workspace-trust key observed in the live config

`~/.claude.json` → `projects` map. Each project entry carries
`hasTrustDialogAccepted` alongside `allowedTools`, `mcpServers`,
`enabledMcpjsonServers`, `disabledMcpjsonServers`,
`hasClaudeMdExternalIncludesApproved`,
`hasClaudeMdExternalIncludesWarningShown`. Observed values:

```
'C:\\Users\\Admin\\OneDrive\\Desktop\\VOICE ASSISTANT CURSOR' -> hasTrustDialogAccepted = False
'C:/Users/Admin'                                             -> hasTrustDialogAccepted = False
'C:/Users/Admin/OneDrive/Desktop/students-app'               -> hasTrustDialogAccepted = True
'C:/Users/Admin/OneDrive/Desktop/MULTIPLATFORM-EM-main'      -> hasTrustDialogAccepted = False
'C:/Users/Admin/Desktop/MULTIPLATFORM-EM-main-2'             -> hasTrustDialogAccepted = True
```

The trust key is stored in the *global* `~/.claude.json`, not in a settings
file — there is no `workspaceTrust` or `hasTrustDialogAccepted` entry in the
published settings-reference.

## 14b. `permission_denials` and `safety_stops` are machine-readable in `--output-format json`

`claude -p "..." --output-format json` returns a top-level object with these
keys (observed):

```
duration_api_ms, stop_reason, session_id, total_cost_usd, usage, modelUsage,
permission_denials, terminal_reason, fast_mode_state, fast_mode_disabled_reason,
subagent_stats, safety_stops, is_error, num_turns, subtype, api_error_status,
result, ttft_ms, type, duration_ms, uuid, ttft_stream_ms, time_to_request_ms,
first_content_frame_ms, queued_turn_count, result_index
```

`permission_denials` is an array of the *local* permission-layer refusals, each
with `tool_name`, `tool_use_id`, and the full `tool_input`:

```
claude -p "Run 'touch .denial-probe.tmp' with Bash ..." \
  --permission-mode default --permission-prompts none --tools Bash --output-format json
```

```json
"permission_denials": [
  {
    "tool_name": "Bash",
    "tool_use_id": "call_01a15f98733773b696981393",
    "tool_input": {
      "command": "touch .denial-probe.tmp && ls -la .denial-probe.tmp",
      "description": "Create and list .denial-probe.tmp"
    }
  }
]
```

`safety_stops` was `0` and `is_error` was `false` in the same run — a denied
tool call is recorded but does not fail the turn.

By contrast, an **auto-mode classifier** refusal is a *process-level* refusal:
the CLI prints the "Permission for this action was denied by the Claude Code
auto mode classifier" notice to stderr and exits without producing the JSON
document at all. On this machine (custom `ANTHROPIC_BASE_URL`) that is a
server-side decision, not the local permission layer.

## 15. MCP server approval surface

```
claude mcp list
→ Checking MCP server health…
   rea: cmd.exe /d /c npx -y rea-agents@6.7.0 mcp - ✔ Connected

claude mcp get rea
→ rea:
    Scope: User config (available in all your projects)
    Status: ✔ Connected
    Type: stdio
    Command: cmd.exe
    Args: /d /c npx -y rea-agents@6.7.0 mcp
    Environment:
```

`claude mcp --help` documents that unapproved `.mcp.json` servers are shown as
"⏸ Pending approval and not connected to".

## 16. `claude plugin list`

```
No plugins installed. Use `claude plugin install` to install a plugin.
```

No plugin/moderation surfaces were exercisable on this machine, so the
mod-based `tool.check` approval path is doc-only (see §"unverifiable" in the
report).
