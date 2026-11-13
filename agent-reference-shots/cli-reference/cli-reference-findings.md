# CLI reference — exact flags and subcommands

**Source page:** https://code.claude.com/docs/en/cli-reference.md
**Local copy:** `agent-reference-shots/cli-reference/doc-cli-reference.md` (47,884 bytes, fetched 2026-10-21)
**Product observed:** Claude Code 2.1.306 (native build, win32-x64, commit `01ae8327ca99`)
**Method:** public documentation + black-box observation of the published CLI's own help surfaces.
**Compliance:** no decompilation, no source extraction, no credential reads. See `../TERMS-NOTES.md`.

> **Machine caveat.** This host runs Claude Code 2.1.306 against a **custom
> `ANTHROPIC_BASE_URL`** (a third-party gateway), not `api.anthropic.com`.
> `claude doctor` explicitly reports: *"Managed settings (remote): not fetched —
> not available with a custom ANTHROPIC_BASE_URL"*. Subscription-gated and
> Anthropic-API-only features (`--cloud`, `--teleport`, `--advisor`, `--channels`,
> `--remote-control`, managed policy, org policy) are therefore **OBSERVED-DOC
> only** — I could not exercise them here.

---

## 1. Executive summary

The CLI reference page is a **dense, complete flag/command surface**, and it is
the highest-value single page for a clean-room reimplementation because it
defines the *entire* user-visible command contract in one place: 33 subcommands
and ~85 flags with exact names, exact accepted values, exact JSON keys, and
exact exit-code semantics.

Three structural facts matter most for reimplementation:

1. **The CLI has three independent invocation surfaces** — interactive TTY,
   print mode (`-p`) with `--output-format text|json|stream-json`, and
   background/daemon mode (`--bg`, `claude agents`, `claude daemon`). A
   clean-room implementation should model these as one core session engine with
   three front-ends, not three products.
2. **The reference is explicitly non-exhaustive on `--help`.** The page states:
   *"`claude --help` does not list every flag, so a flag's absence from `--help`
   does not mean it is unavailable."* I confirmed this empirically: `--advisor`,
   `--channels`, `--exec`, `--init`, `--init-only`, `--maintenance`,
   `--max-turns`, `--append-subagent-system-prompt`,
   `--append-subagent-system-prompt-file`, `--append-system-prompt-file`, and
   `--teammate-mode` are all documented but **absent from `claude --help` on
   2.1.306**. Conversely `--brief` and `--file <specs...>` appear in `--help`
   but are **absent from the doc page**. The doc and the binary are both
   partial and non-identical views of one another.
3. **The binary enforces a strict, machine-checkable contract**: enum flags
   reject invalid values with an `Allowed choices are ...` message and exit
   code 1; unknown subcommands print a *"Did you mean ...?"* suggestion and exit
   1 without starting a session; unknown options exit 1; UUID-typed flags
   validate format. These are all cheap to replicate and are what makes the
   CLI scriptable.

**The single highest-value clean-room takeaway:** the *print-mode JSON envelope*
is the integration contract. I observed 25 top-level keys
(`duration_api_ms`, `stop_reason`, `session_id`, `total_cost_usd`, `usage`,
`modelUsage`, `permission_denials`, `terminal_reason`, `fast_mode_state`,
`fast_mode_disabled_reason`, `subagent_stats`, `safety_stops`, `is_error`,
`num_turns`, `subtype`, `api_error_status`, `result`, `ttft_ms`, `type`,
`duration_ms`, `uuid`, `ttft_stream_ms`, `time_to_request_ms`,
`first_content_frame_ms`, `queued_turn_count`, `result_index`) plus the
`stream-json` `system` init event carrying `cwd`, `session_id`, `tools`,
`mcp_servers`, `model`, `permissionMode`. An independent agent that emits a
*different* JSON shape is not drop-in compatible even if it is otherwise
functionally equivalent.

---

## 2. CLI commands (exact subcommand surface)

Section heading: `## CLI commands` (line 9 of the local markdown copy).

The page's table defines these subcommands. I verified the subset that is
observable on this host against `claude <cmd> --help`:

| Subcommand | Doc wording (verbatim, condensed) | Observed on 2.1.306 |
| :- | :- | :- |
| `claude` | "Start interactive session" | yes |
| `claude "query"` | "Start interactive session with initial prompt" | yes |
| `claude -p "query"` | "Query via SDK, then exit" | yes |
| `claude -c` / `-c -p` | "Continue most recent conversation in current directory" | yes |
| `claude -r "<session>" "query"` | "Resume session by ID or name" | yes |
| `claude update` | "Update to latest version" | present; alias `upgrade` |
| `claude gateway` | "Start the self-hosted Claude apps gateway server … Requires `--config` pointing at a `gateway.yaml`" | present |
| `claude install [version]` | "Install or reinstall the native binary. Accepts a version like `2.1.118`, or `stable` or `latest`" | present |
| `claude auth login` | "Sign in to your Anthropic account. Use `--email` to pre-fill your email address, `--sso` to force SSO authentication, and `--console` to sign in with Anthropic Console" | present |
| `claude auth logout` | "Log out from your Anthropic account" | present |
| `claude auth status` | "Show authentication status as JSON. Use `--text` for human-readable output. Exits with code 0 if logged in, 1 if not." | present, exit 0 observed |
| `claude agents` | "Open agent view to monitor and dispatch parallel background sessions. Use `--cwd <path>` … or `--json` to print active sessions as a JSON array" | present, `--json` observed |
| `claude attach <id\|name>` | "Attach to a background session in this terminal." | present |
| `claude auto-mode defaults` | "Print the built-in auto mode classifier rules as JSON. … `--label <prefix>` prints only the rules whose label starts with that prefix, matched case-insensitively." | present, observed |
| `claude auto-mode reset` | "Restore the default auto mode configuration by removing the `autoMode` section from your user settings file. Prompts for confirmation before writing; pass `-y`/`--yes` to skip the prompt." | present, observed |
| `claude daemon logs` | "Follow the background-session supervisor's log file, `~/.claude/daemon.log`" | present (supervised by `claude daemon`) |
| `claude daemon run` | "Run the background-session supervisor in the foreground of this terminal, printing its log" | present |
| `claude daemon status` | "Print the background-session supervisor's state, version, socket directory, and worker count for diagnostics. Exits 1 if the supervisor isn't running" | present, **exit 1 observed** |
| `claude daemon stop --any` | "Stop the background-session supervisor and the sessions it hosts. Pass `--keep-workers` to leave background sessions running" | present |
| `claude doctor` | "Print read-only installation and settings diagnostics from the terminal without starting a session" | present, observed |
| `claude import [source]` | "Start an interactive session that runs `/import` to bring configuration from other coding agents into Claude Code. Accepts the same `--dry-run` and `--yes` options" | present, observed |
| `claude logs <id\|name>` | "Print recent output from a background session" | present |
| `claude mcp` | "Configure Model Context Protocol (MCP) servers" | present, observed |
| `claude mcp login <name>` | "Run a configured MCP server's OAuth flow without opening the interactive `/mcp` panel. Works for HTTP, SSE, and claude.ai connector servers. Add `--no-browser` over SSH" | present |
| `claude mcp logout <name>` | "Clear stored OAuth credentials for an MCP server" | present |
| `claude plugin` | "Manage Claude Code plugins. Alias: `claude plugins`." | present, alias confirmed |
| `claude purge [path]` | "Delete all local Claude Code state for a project: transcripts, task lists, debug logs, file-edit history, prompt history lines, and the project's entry in `~/.claude.json`." | present, observed |
| `claude remote-control` | "Start a Remote Control server to control Claude Code from Claude.ai or the Claude app." | present (blocked on this host) |
| `claude respawn <id>` | "Restart a background session, running or stopped, with its conversation intact. Use `--all` to restart every running session" | present |
| `claude rm <id>` | "Remove a background session from the list." | present |
| `claude self-hosted-runner` | "Start a runner process that registers this machine or container with a self-hosted environment" | present |
| `claude setup-token` | "Generate a long-lived OAuth token for CI and scripts. Prints the token to the terminal without saving it. Requires a Claude subscription." | present |
| `claude stop <id>` | "Stop a background session." (alias `claude kill`) | present, alias confirmed |
| `claude ultrareview [target]` | "Run ultrareview non-interactively. Prints findings to stdout and exits 0 on success or 1 on failure. Use `--json` for the raw payload and `--timeout <minutes>` to override the 45-minute default." | present, observed |

### 2.1 The typo-suggestion contract (OBSERVED-DOC + OBSERVED)

Doc (section `## CLI commands`, immediately after the table):

> "If you mistype a subcommand, Claude Code suggests the closest match and exits
> without starting a session. For example, `claude udpate` prints `Did you mean
> claude update?`."

**Observed** on 2.1.306 — the message is written to **stderr**, not stdout, and
the process exits **1**:

```
✘ unknown command "udpate"
  └ Did you mean claude update?

Run claude --help to list commands, or claude -p "udpate" to send as a prompt.
```

(`claude udpate 2>/dev/null` produced no stdout; `claude udpate 2>&1 1>/dev/null`
produced the full block.)

Two things the doc does not say but the binary does:
- The error carries a **disambiguating escape hatch**: `claude -p "udpate"`
  treats the same token as a *prompt* instead of an error.
- The suggestion is emitted **before** any session start, so a typo never
  costs a model call.

### 2.2 The `daemon` routing rule (OBSERVED-DOC)

Doc, section `## CLI commands`:

> "`claude --dangerously-skip-permissions daemon <subcommand>` runs the
> `daemon` subcommand, so the subcommand works when `claude` is aliased to
> include the flag. Only a leading `--dangerously-skip-permissions` or
> `--allow-dangerously-skip-permissions` routes to `daemon` this way; with any
> other flag ahead of `daemon`, the subcommand doesn't run."

This is an unusual and precise argv-parsing rule: **only two** flags, and only
in leading position, cause a following `daemon` token to be treated as a
subcommand rather than as the prompt. I could not exercise it here because the
auto-mode classifier denied the `--dangerously-skip-permissions` invocation
(this host is running under the auto-mode classifier), but the doc states it
precisely enough to implement.

### 2.3 `claude auth status` — the JSON contract (OBSERVED-DOC + OBSERVED)

Doc:

> "Show authentication status as JSON. Use `--text` for human-readable output.
> Exits with code 0 if logged in, 1 if not. The JSON includes a
> `configDirectory` field naming the configuration directory the CLI uses. The
> field requires Claude Code v2.1.268 or later. The JSON's `authMethod` field is
> one of `none`, `claude.ai`, `oauth_token`, `api_key`, `api_key_helper`, or
> `third_party`"

**Observed** JSON keys on this host (values redacted except where non-secret):

```
loggedIn            = True
authMethod          = oauth_token
apiProvider         = firstParty
analyticsDisabled   = False
projectsDirectory   = <redacted>
configDirectory     = C:\Users\Admin\.claude
```

`authMethod` is exactly one of the six documented values — the enumeration is
real and closed. `--text` output observed:

```
Auth token: ANTHROPIC_AUTH_TOKEN
Anthropic base URL: https://openrouter.ai/api
```

`claude auth status` exited **0**.

### 2.4 `claude agents --json` — the session-registry contract (OBSERVED-DOC + OBSERVED)

Doc: "`--json` to print active sessions as a JSON array for scripting
(`--json --all` also includes completed background sessions)."

**Observed** — a JSON array whose element schema is stable and scriptable:

```json
[
  {
    "pid": 21488,
    "cwd": "C:\\Users\\Admin\\Desktop\\Claude clone",
    "kind": "interactive",
    "startedAt": 1792603034892,
    "sessionId": "ca6d0088-4426-4239-8884-8c2b9e5b1238",
    "name": "claude-clone-95",
    "status": "busy"
  }
]
```

Exact key names: `pid`, `cwd`, `kind`, `startedAt` (epoch **milliseconds**),
`sessionId` (UUID), `name`, `status`. `kind` was observed as `interactive`
(the other documented values are `interactive` and `background` per the
background-session docs). `status` was `busy`.

### 2.5 `claude purge` — the local-state deletion surface (OBSERVED-DOC + OBSERVED)

Doc: "Delete all local Claude Code state for a project: transcripts, task
lists, debug logs, file-edit history, prompt history lines, and the project's
entry in `~/.claude.json`. Omit `[path]` to pick from an interactive list.
Flags: `--dry-run` to preview, `-y`/`--yes` to skip confirmation,
`-i`/`--interactive` to confirm each item, `--all` for every project."

**Observed** `claude purge --help` — the six-item state list above is exactly
the `Delete all Claude Code state for a project (transcripts, tasks, file
history, config entry)` synopsis, and the four flags
(`--all`, `--dry-run`, `-i/--interactive`, `-y/--yes`) all exist, with
`--all` documented in the binary as "mutually exclusive with [path]".

**Observed**: `claude purge --dry-run` with no `[path]` opened an **interactive
picker** rather than erroring or defaulting — matching "Omit `[path]` to pick
from an interactive list." A non-interactive caller must therefore always pass
`[path]`.

### 2.6 `claude doctor` — the read-only diagnostics surface (OBSERVED-DOC + OBSERVED)

Doc: "Print read-only installation and settings diagnostics from the terminal
without starting a session, including install health, settings-file validation
errors, and Remote Control eligibility. For the in-session setup checkup that
can also apply fixes, run `/doctor`."

**Observed** output (abridged, nothing secret):

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
...
No installation issues found.

For a full setup checkup that can also fix issues, run /doctor in a Claude Code session.
```

**Observed**: the diagnostic explicitly **enumerates its own blind spots**
(managed settings, org policy, Remote Control eligibility) and explains *why*
each is unavailable. This "report what I could not check and why" behaviour is
a good contract to copy: a reimplementation should never silently report
"healthy" for subsystems it could not reach.

---

## 3. CLI flags

Section heading: `## CLI flags` (line 56 of the local markdown copy).

> "Customize Claude Code's behavior with these command-line flags. `claude
> --help` does not list every flag, so a flag's absence from `--help` does not
> mean it is unavailable."

### 3.1 Session lifecycle and resumption

**`--continue`, `-c`** (OBSERVED-DOC):
> "Load the most recent conversation in the current directory, including a
> background session that has finished; opening finished background sessions
> requires Claude Code v2.1.257 or later. Skips sessions created with `claude
> -p` or the Agent SDK, and sessions whose first prompt was `/loop`. `claude -p
> --continue` includes `-p`, SDK, and `/loop` sessions. Includes sessions that
> added this directory with `/add-dir`"

The asymmetry — interactive `-c` *excludes* `-p`/SDK/`/loop` sessions, while
`-p --continue` *includes* them — is a precise, testable rule.

**`--resume`, `-r`** (OBSERVED-DOC):
> "Resume a specific session by ID or name, or show an interactive picker to
> choose a session. In place of an ID, you can pass the absolute path to a
> session's `.jsonl` transcript file. The picker and name search include
> sessions that added this directory with `/add-dir`. When you pass a session
> ID, Claude Code searches the current project directory and its git worktrees,
> then every other project on this machine. Before v2.1.223, the ID search
> covered only the current project directory and its git worktrees. Background
> sessions appear in the picker marked with `bg`."

Three resumable identifiers are therefore supported: **session ID**, **display
name**, and **absolute `.jsonl` transcript path**. The picker marks background
sessions with a literal `bg` tag.

**`--fork-session`** (OBSERVED-DOC):
> "When resuming, create a new session ID instead of reusing the original (use
> with `--resume` or `--continue`)"

**`--session-id`** (OBSERVED-DOC + OBSERVED):
> "Use a specific session ID for the conversation (must be a valid UUID)"

Observed: `--session-id 550e8400-e29b-41d4-a716-446655440000` → the print-mode
JSON envelope reported `session_id = 550e8400-e29b-41d4-a716-446655440000`
exactly. Observed validation: `--session-id not-a-uuid` →
`Error: Invalid session ID. Must be a valid UUID.`

**`--name`, `-n`** (OBSERVED-DOC):
> "Set a display name for the session, shown in `/resume` and the terminal
> title. You can resume a named session with `claude --resume <name>`."
(`/rename` "changes the name mid-session and also shows it on the prompt bar.")

Observed in `claude agents --json`: sessions carry a `name` field and a
`--name`-derived name is the `claude-<dirname>-<n>` shape.

### 3.2 Permission-mode and tool-surface flags

**`--permission-mode`** (OBSERVED-DOC + OBSERVED):
> "Begin in a specified permission mode. Accepts `default`, `acceptEdits`,
> `plan`, `auto`, `dontAsk`, `bypassPermissions`, or `manual` as an alias for
> `default`. The `manual` alias selects the permission mode the UI labels Manual
> and requires Claude Code v2.1.200 or later; `claude --help` lists it in place
> of `default`, and both values work. Overrides `defaultMode` from settings
> files."

Observed on 2.1.306 — `--help` lists the choices as
`acceptEdits, auto, bypassPermissions, manual, dontAsk, plan` (six; `default`
is **not** in the list), but `--permission-mode default` still works at runtime
and the `stream-json` `system` init event reported `permissionMode = default`.
Invalid values produce:

```
error: option '--permission-mode <mode>' argument 'nonsense' is invalid.
Allowed choices are acceptEdits, auto, bypassPermissions, manual, dontAsk, plan.
```
exit code **1**.

**`--tools`** (OBSERVED-DOC + OBSERVED):
> "Restrict which built-in tools Claude can use. Use `""` to disable all,
> `"default"` for the default set, or tool names like `"Bash,Edit,Read"`. On
> macOS, Linux, and WSL, the default set leaves out `Glob` and `Grep` … The
> flag doesn't affect MCP tools; to deny those too, use `--disallowedTools
> "mcp__*"`. A list that omits `EndConversation` doesn't remove it; `""` removes
> it only when no MCP tools remain"

Observed on **win32** (so the macOS/Linux/WSL Glob/Grep exclusion does *not*
apply here — confirmed: both `Glob` and `Grep` are present). The observed
default set was:

```
Task, Bash, CronCreate, CronDelete, CronList, DesignSync, Edit, EnterWorktree,
ExitWorktree, Glob, Grep, ListAgents, Monitor, NotebookEdit, PowerShell,
PushNotification, Read, ReportFindings, ScheduleWakeup, SendMessage, Skill,
TaskStop, ToolSearch, WebFetch, WebSearch, Workflow, Write
```
(27 built-ins.) `--tools ""` → `tools = []` in the `system` init event.

**`--allowedTools`, `--allowed-tools`** (OBSERVED-DOC):
> "Tools that execute without prompting for permission, apart from reads from
> network paths. … To restrict which tools are available, use `--tools`
> instead."

**`--disallowedTools`, `--disallowed-tools`** (OBSERVED-DOC):
> "Deny rules. A bare tool name removes the matching tools from Claude's
> context: `"Edit"` removes Edit, `"*"` removes every tool, and `"mcp__*"`
> removes every MCP tool. A scoped rule such as `Bash(rm *)` leaves the tool
> available and denies only calls that match as written."

The bare-name-vs-scoped-rule distinction is the key architectural idea: a
bare name is a **tool-availability** decision (removes it from the model's
context), a scoped rule is a **call-time authorisation** decision (tool stays
listed, matching calls are denied).

**`--permission-prompt-tool`** (OBSERVED-DOC):
> "Specify an MCP tool to handle permission prompts in non-interactive mode.
> Pass the full name, such as `mcp__<server>__<tool>`, of a tool on an MCP
> server that the run loads. … The prompt tool can't approve an MCP tool marked
> as requiring user interaction: Claude Code converts an `allow` result for one
> to a deny."

**`--permission-prompts`** (OBSERVED-DOC + OBSERVED):
> "Set who answers permission prompts in print mode. With the default `host`,
> Claude Code sends them to the Agent SDK host or the `--permission-prompt-tool`
> tool. Pass `none` when nobody can answer, and Claude Code denies them
> instead."

Observed `--help` confirms choices `host` (default) and `none`.

**`--dangerously-skip-permissions`** (OBSERVED-DOC):
> "Skip permission prompts. Equivalent to `--permission-mode
> bypassPermissions`."

**`--allow-dangerously-skip-permissions`** (OBSERVED-DOC):
> "Add `bypassPermissions` to the `Shift+Tab` mode cycle without starting in
> it. Lets you begin in a different mode like `plan` and switch to
> `bypassPermissions` later."

### 3.3 Prompt and system-prompt control

Section heading: `### System prompt flags` (line 143). The page describes
exactly five flags: "Claude Code provides five flags for customizing the system
prompt. Four set its text, and with `--system-prompt-snapshot` you control
whether a conversation keeps the text it started with. All five work in both
interactive and non-interactive modes."

| Flag | Behaviour (doc) |
| :- | :- |
| `--system-prompt` | "Replaces the entire default prompt" |
| `--system-prompt-file` | "Replaces with file contents" |
| `--append-system-prompt` | "Appends to the default prompt" |
| `--append-system-prompt-file` | "Appends file contents to the default prompt" |
| `--system-prompt-snapshot` | "With `off`, rebuilds the prompt on every request. With `on`, the default, reuses a recorded prompt where recording applies" |

Combination rule (doc):
> "You can combine these flags. To replace the default prompt and still append
> your own text, pass `--append-system-prompt` or `--append-system-prompt-file`
> together with `--system-prompt` or `--system-prompt-file`. With Claude Code
> v2.1.283 or later, you can also pass a flag together with its own file form,
> such as `--append-system-prompt` with `--append-system-prompt-file`, and
> Claude Code uses both."

Precedence rule (doc):
> "The file's contents come first even if you pass `--append-system-prompt`
> before `--append-system-prompt-file`."

**The `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` marker** (doc) is a notable,
directly-copyable contract:
> "When the replacement text combines instructions that are the same on every
> run with context that changes per run, add a line containing only
> `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` between the instructions and the
> context. Claude Code splits the prompt at the first such line and removes
> that line, so the part above it stays cached while the part below changes.
> Requires Claude Code v2.1.275 or later."

This is a prompt-cache-partitioning primitive: a single sentinel line that
splits the assembled prompt into a stable prefix and a volatile suffix.

**`--system-prompt-snapshot` semantics in resumed conversations** (section
`#### System prompt flags in resumed conversations`):
> "By default, Claude Code builds the system prompt once, on a conversation's
> first request, with the text from any system prompt flags applied, and
> records it in the session. Until the conversation is compacted, every later
> request uses that recorded prompt, including after you return to the
> conversation with `--resume` or `--continue`. If you pass different system
> prompt flag text, or none, on that later launch, it takes effect once the
> conversation is compacted or when you start a new conversation."

And the bare-mode exception:
> "Outside of cloud sessions, if you start Claude Code in bare mode by passing
> `--bare` or setting `CLAUDE_CODE_SIMPLE=1`, recording stays off unless you
> pass `--system-prompt-snapshot on`."

**`--exclude-dynamic-system-prompt-sections`** (doc):
> "Move per-user context, such as the auto memory location, out of the system
> prompt and into the first user message. Improves prompt-cache reuse across
> different users and machines running the same task. Only applies with the
> default system prompt; ignored when `--system-prompt` or `--system-prompt-file`
> is set."

**`--append-subagent-system-prompt`** / **`--append-subagent-system-prompt-file`** (doc):
> "Append custom text to the end of every subagent's system prompt, nested
> subagents included, apart from a forked subagent, which reuses the
> conversation's own prompt. Only applies in non-interactive mode with `-p`."

### 3.4 Model and effort selection

**`--model`** (OBSERVED-DOC + OBSERVED):
> "Sets the model for the current session with a model alias such as `sonnet`,
> `opus`, `haiku`, or `fable`, or a model's full name. Overrides the `model`
> setting and `ANTHROPIC_MODEL`."

Observed: the `stream-json` `system` init event reports the resolved `model`
string verbatim — on this host `minimax/minimax-m3.1-flash:free`, the custom
gateway's model id. Observed on an unrecognised model id, the CLI prints a
warning and falls back to a 200k context assumption:
`Claude Code doesn't recognize the model "<id>", so it assumes a context window
of 200k tokens.` plus a structured log line
`[claude-code:unrecognized_model] {"model":"<id>","query_source":"sdk"}`.

**`--effort`** (OBSERVED-DOC + OBSERVED):
> "Set the effort level for the current session. Options: `low`, `medium`,
> `high`, `xhigh`, `max`, or `ultracode`. Available levels depend on the model.
> `ultracode` requests `xhigh` effort with `ultracode` turned on … Overrides the
> `modelSettings` and `effortLevel` settings for this session and does not
> persist"

Observed on 2.1.306: `--help` lists only `low, medium, high, xhigh, max`
(five — `ultracode` is absent from `--help` but documented). An invalid value
is a **warning, not an error**:
`Warning: Unknown --effort value 'bogus' — ignoring it and using the default
effort. Valid values: low, medium, high, xhigh, max.` — the run continued.

This is a meaningful contract difference vs. `--permission-mode` (hard error,
exit 1) and `--output-format` (hard error, exit 1): **effort degrades
softly; enums that change program semantics fail hard.**

**`--fallback-model`** (OBSERVED-DOC):
> "Enable automatic fallback to the specified model(s) when the primary model is
> overloaded or not available, for example a retired model. Accepts a
> comma-separated list tried in order. … To persist a chain across sessions,
> use the `fallbackModel` setting, which this flag overrides"

**`--advisor <model>`** (OBSERVED-DOC, not exercisable here): enables a
server-side advisor tool for the session, taking precedence over the
`advisorModel` setting.

### 3.5 Configuration sourcing

**`--settings`** (OBSERVED-DOC + OBSERVED):
> "Path to a settings JSON file or an inline JSON string. Values you set here
> override the same keys in your `settings.json` files for this session. Keys
> you omit keep their file-based values. The file must be a regular file no
> larger than 2 MiB."

**Observed**: `--settings '{"model":"sonnet"}'` (inline JSON, not a path) was
accepted and the session started normally — the "path or inline JSON" dual
form is real.

**`--setting-sources`** (OBSERVED-DOC):
> "Comma-separated list of setting sources to load (`user`, `project`,
> `local`)."

**`--add-dir`** (OBSERVED-DOC + OBSERVED):
> "Add additional working directories for Claude to read and edit files. Grants
> file access; Claude Code doesn't discover most `.claude/` configuration from
> these directories. Validates that each path exists as a directory. You can't
> add most network paths, such as `\\server\share`. To persist these
> directories across sessions, set `permissions.additionalDirectories` in
> settings"

**Observed** validation, with a helpful suggestion:
```
agent-evidence.md is not a directory. Did you mean to add the parent directory C:\Users\Admin\Desktop\Claude clone?
```
A **nonexistent** path (`/no/such/dir`) did **not** error — the run continued
(though a separate stdin quirk swallowed the prompt; see §4.2). So the
"validates that each path exists as a directory" claim is only partially
honoured in the observed build: *not-a-directory* is rejected with a message,
*does-not-exist* is not rejected at all.

### 3.6 MCP and plugins

**`--mcp-config`** (OBSERVED-DOC):
> "Load MCP servers from JSON files or strings (space-separated). When you pass
> this flag with `-p`, Claude Code waits for still-pending servers to connect
> before running the first turn, up to the `MCP_TIMEOUT` startup timeout, 30
> seconds by default; a server with a cached tool list skips the wait and
> connects on first use."

**Observed** (default, no `--strict-mcp-config`): the `system` init event
reported `mcp_servers = [{'name': 'rea', 'status': 'pending', 'source': 'user'}]`
— exact key names `name`, `status`, `source`. `status` value `pending` is
observed; `source` value `user` denotes user-scoped configuration.

**`--strict-mcp-config`** (OBSERVED-DOC + OBSERVED):
> "Only use MCP servers from `--mcp-config`, ignoring all other MCP
> configurations."

**Observed**: with `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`,
the init event reported `mcp_servers = []` while `tools count = 27` — i.e. the
user-scoped `rea` server was dropped and the built-in tool set was unchanged.
This cleanly separates *built-in tool surface* from *MCP tool surface*.

**`--plugin-dir`** / **`--plugin-url`** (OBSERVED-DOC): load a plugin from a
directory, `.zip`, or URL for this session only; the flags are repeatable and
accept space-separated values.

### 3.7 Print-mode / headless contract

**`--output-format`** (OBSERVED-DOC + OBSERVED):
> "Specify output format for print mode (options: `text`, `json`,
> `stream-json`)"

Observed invalid value →
`error: option '--output-format <format>' argument 'nonsense' is invalid.
Allowed choices are text, json, stream-json.` (exit 1).

**`--input-format`** (OBSERVED-DOC): "Specify input format for print mode
(options: `text`, `stream-json`)". Observed `--help` confirms
`(choices: "text", "stream-json")`.

**`--print`, `-p`** (OBSERVED-DOC + OBSERVED):
> "Print response without interactive mode (see Agent SDK documentation for
> programmatic usage details)."

Observed `--help` adds two operational details the doc omits:
> "Note: The workspace trust dialog is skipped when Claude is run in
> non-interactive mode (via `-p`, or when stdout is not a TTY, e.g. piped or
> redirected output). Only use this in directories you trust. Settings files
> that fail validation are silently ignored in this mode (no error dialog is
> shown)."

**`--json-schema`** (OBSERVED-DOC + OBSERVED):
> "Get validated JSON output matching a JSON Schema after the agent completes
> its workflow (print mode only). … Claude Code exits with an error on an
> invalid schema and accepts the `format` keyword as an annotation without
> client-side validation"

Observed: `--json-schema '{"type":"not-a-type"}'` →
`Error: --json-schema is not a valid JSON Schema: data/type must be equal to one
of the allowed values, data/type must be array, data/type must match a schema in
anyOf` (exit 1). The error text is a JSON-Schema-validator message — a
reimplementation should use a real JSON Schema validator, not a hand-rolled
check, to match this shape.

**`--max-turns`** (OBSERVED-DOC): "Limit the number of agentic turns (print mode
only). Exits with an error when the limit is reached. No limit by default. With
`--input-format stream-json`, a message still queued when the limit ends a turn
stays queued and starts a new turn with its own limit."

**`--max-budget-usd`** (OBSERVED-DOC):
> "Stop the run once estimated spend on API calls reaches this amount (print
> mode only). Claude Code checks the cap against its client-side cost estimate,
> which can differ from your bill. Spend from subagents counts toward the cap.
> Spend can pass the cap, so leave headroom. … Once spend reaches the cap,
> spawning another subagent fails with `Budget limit reached`, and Claude Code
> stops background subagents that are still running"

**`--no-session-persistence`** (OBSERVED-DOC): "Disable session persistence so
sessions are not saved to disk and cannot be resumed. Print mode only."

**`--include-partial-messages`** (OBSERVED-DOC): "Include partial streaming
events in output. Requires `--print` and `--output-format stream-json`."

**`--include-hook-events`** (OBSERVED-DOC):
> "Include hook lifecycle events in the output stream. `SessionStart` and
> `Setup` hook events are always included and don't need this flag. Some hook
> events, such as `Notification`, `SessionEnd`, `PreCompact`, and `PostCompact`,
> never produce a `hook_started` event, even with this flag. For those events,
> Claude Code still emits `hook_progress` while a command hook that runs for
> more than a second produces output, and emits `hook_response` only when a
> hook that runs in the background finishes."

**`--replay-user-messages`** (OBSERVED-DOC + OBSERVED):
> "Re-emit user messages from stdin back on stdout for acknowledgment. Requires
> `--input-format stream-json` and `--output-format stream-json`."

**Observed** — piping one `{"type":"user","message":{...}}` line produced this
stream order:

```
system init → user → assistant → result success
```

The echoed `user` event carried `message.content = "say OK"`. This gives a
reimplementation a well-defined acknowledgement contract for stdin-driven
runs.

**`--forward-subagent-text`** (OBSERVED-DOC):
> "Emit subagent text and thinking blocks in the output stream as `assistant`
> and `user` messages with `parent_tool_use_id` set, so you can reconstruct each
> subagent's transcript. Without this flag, Claude Code omits the text and
> thinking blocks of a subagent that runs in the foreground. Requires
> `--print` and `--output-format stream-json`."

The exact JSON field `parent_tool_use_id` is the reattachment key — a
reimplementation should use the same field name if it wants the same
subagent-transcript reconstruction tooling to work.

**`--prompt-suggestions`** (OBSERVED-DOC): "Emit a `prompt_suggestion` message
with a predicted next user prompt after each turn that generates one; very
short conversations can produce none. Requires `--print`,
`--output-format stream-json`, and `--verbose`." The exact event type string
is `prompt_suggestion`.

### 3.8 Startup-profile flags (bare / safe-mode / restricted)

These three are the CLI's "environment isolation" dials and are the most
important for anyone embedding the tool.

**`--bare`** (OBSERVED-DOC + OBSERVED):
> "Minimal mode: skip auto-discovery of hooks, skills, custom commands,
> subagents, installed plugins, MCP servers, auto memory, and CLAUDE.md so
> scripted calls start faster. Skills in a directory you pass with `--add-dir`
> still load. Claude has access to Bash, file read, and file edit tools. Sets
> `CLAUDE_CODE_SIMPLE`."

**Observed**: with `--bare --output-format stream-json --verbose`, the `system`
init event had keys `['type','subtype','event','uuid','session_id']` — i.e. the
init event **omits** `tools`, `mcp_servers`, `model`, `permissionMode`, and
`cwd` entirely. The init event shape is itself profile-dependent.

**`--safe-mode`** (OBSERVED-DOC):
> "Start with all customizations disabled to troubleshoot a broken
> configuration: CLAUDE.md, skills, plugins, hooks, MCP servers, custom commands
> and agents, output styles, workflows, custom themes, custom keybindings,
> status line and file-suggestion commands, LSP servers, and auto memory do not
> load. Authentication, model selection, built-in tools, and permissions work
> normally, which differs from `--bare`. Managed settings policy still applies,
> including policy-configured hooks, status line, and file-suggestion commands;
> managed plugins, managed skills, managed CLAUDE.md, and policy-configured MCP
> servers do not. … Sets `CLAUDE_CODE_SAFE_MODE`"

The explicit `--bare` vs `--safe-mode` contrast ("which differs from `--bare`")
is architecturally important: **`--bare` is a performance profile (skip
discovery), `--safe-mode` is a diagnostic profile (neutralise every
customisation while keeping auth/model/tools/permissions).**

**`--restricted`** (OBSERVED-DOC + OBSERVED):
> "Start in restricted mode. Use it when an evaluation harness drives `claude`
> on a shared machine and Claude Code must not run commands or read that
> machine's user and project settings. Claude Code removes the built-in tools
> that run commands or code, and WebFetch, unless you name them individually in
> `--tools`, not through the `default` preset. It also confines the built-in
> file tools to the working directories, loads only managed settings and
> `--settings`, refuses `bypassPermissions`, and refuses to create cloud
> sessions."

The `system` init event's `permissionMode` key and the `tools` array are the
observable proxy for the whole restricted profile.

**`--disable-slash-commands`** (OBSERVED-DOC): "Disable all skills and commands
for this session" — one flag disabling the *entire* skills/commands surface.

**`--init` / `--init-only` / `--maintenance`** (OBSERVED-DOC): run `Setup`
hooks with the `init` / `maintenance` matcher; `--init-only` runs `Setup` and
`SessionStart` hooks then exits without starting a conversation.

### 3.9 Background, worktree and remote surfaces

**`--bg`, `--background`** (OBSERVED-DOC):
> "Start the session as a background agent and return immediately. Prints the
> session ID and management commands. Combine with `--exec` to run a shell
> command as a background job instead of a Claude session, or with `--agent` to
> run a specific subagent. Checks workspace trust for the directory before it
> starts. Can't be combined with `-p`/`--print`."

**`--worktree`, `-w`** (OBSERVED-DOC):
> "Start Claude in an isolated git worktree at `<repo>/.claude/worktrees/<name>`.
> If you don't give a name, Claude Code generates one. Pass `#<number>`, a
> GitHub pull request URL, or a GitLab merge request URL to fetch that PR or MR
> from `origin` and branch the worktree from it."

**`--tmux`** (OBSERVED-DOC): "Create a tmux session for the worktree. Requires
`--worktree`. Uses iTerm2 native panes when available; pass `--tmux=classic` for
traditional tmux."

**`--teammate-mode`** (OBSERVED-DOC, absent from `--help`): "Set how agent team
teammates display: `in-process` (default), `auto`, `tmux`, or `iterm2`."

**`--cloud`** (OBSERVED-DOC): "With a task description, create a new cloud
session. With a session ID (`session_...` or `cse_...`) or a claude.ai/code URL,
queue a message into that existing session instead, with `-p`." — the
`session_` / `cse_` id prefixes are the concrete observable contract.

### 3.10 Diagnostics

**`--debug`** (OBSERVED-DOC):
> "Enable debug mode with optional category filtering, such as
> `--debug='mcp,startup'` or `--debug='!mcp'`. The filter binds only in the `=`
> form; a space-separated filter enables debug mode without filtering"

**`--debug-file <path>`** (OBSERVED-DOC): "Write debug logs to a specific file
path. Implicitly enables debug mode. Takes precedence over
`CLAUDE_CODE_DEBUG_LOGS_DIR`."

**`--verbose`** (OBSERVED-DOC): "Enable verbose logging, shows full turn-by-turn
output. Overrides the `viewMode` setting for this session."

---

## 4. The observable print-mode contract (highest-value for reimplementation)

### 4.1 Print-mode JSON envelope

**Observed** (`claude -p --output-format json "reply with the single word OK"`).
Top-level keys, in the order emitted:

```
duration_api_ms, stop_reason, session_id, total_cost_usd, usage, modelUsage,
permission_denials, terminal_reason, fast_mode_state, fast_mode_disabled_reason,
subagent_stats, safety_stops, is_error, num_turns, subtype, api_error_status,
result, ttft_ms, type, duration_ms, uuid, ttft_stream_ms, time_to_request_ms,
first_content_frame_ms, queued_turn_count, result_index
```

Values observed: `stop_reason = end_turn`, `terminal_reason = completed`,
`subtype = success`, `type = result`, `is_error = False`,
`num_turns = 1`, `result = "OK"`, `api_error_status = None`,
`permission_denials = []`, `safety_stops = 0`, `fast_mode_state = off`,
`fast_mode_disabled_reason = sdk_opt_in_required`, `total_cost_usd = 0.0563442`,
`usage` and `modelUsage` are objects (`usage` had 12 keys, `modelUsage` 1),
`subagent_stats` an object with 10 keys.

**INFERRED**: the envelope is deliberately *self-describing about failure*.
`stop_reason` (protocol-level), `terminal_reason` (session-level),
`subtype` (`success` vs other), `is_error`, `api_error_status`,
`permission_denials`, `safety_stops` and `fast_mode_disabled_reason` are
redundant in a naive design; together they let a caller distinguish "the model
finished normally" from "we stopped because of a budget cap", "a tool was
denied", "a safety classifier intervened", and "the request was routed
elsewhere". A reimplementation should emit an equivalent multi-axis status
surface rather than a single `ok: boolean`.

### 4.2 `stream-json` event types

**Observed** event types: `system` (subtype `init`), `assistant`, `user`,
`result`.

The `system`/`init` event keys observed with the default profile:
`type, subtype, cwd, session_id, tools, mcp_servers, model, permissionMode`.
With `--bare`: `type, subtype, event, uuid, session_id`.

`assistant` event keys observed: `type, message, parent_tool_use_id, session_id,
uuid, timestamp, request_id`.

**INFERRED**: `parent_tool_use_id` is present on *every* assistant event (null
for top-level turns) so that a consumer can attribute a message to a specific
subagent call without a separate side channel. This is the field `--forward-
subagent-text` populates to reconstruct nested transcripts.

### 4.3 Variadic options swallow the positional prompt — a real, reproducible footgun

**Observed** on 2.1.306:

```
$ claude -p --tools "" "say OK"
Error: Input must be provided either through stdin or as a prompt argument when using --print
```
```
$ claude -p --allowedTools "Read" "say OK"
Error: Input must be provided either through stdin or as a prompt argument when using --print
```
```
$ claude -p --tools "" --verbose "say OK"
OK                       # works
```

`--tools`, `--allowedTools`, `--disallowedTools`, `--add-dir`, `--betas`,
`--plugin-dir`, `--plugin-url`, `--mcp-config` are all variadic
(`<tools...>` in the help output). In commander-style parsing, a variadic option
consumes **all** following non-option tokens, so `"say OK"` is absorbed as
another value and the CLI ends up with no positional prompt.

**INFERRED**: a reimplementation that uses a different argument parser (e.g.
one that stops variadic collection at the first non-matching token) would
*accept* `claude -p --tools "" "say OK"` where Claude Code errors. That is a
behavioural difference a user would notice. The clean-room implementation
should either replicate the absorption semantics deliberately (and document
them) or adopt a strictly more forgiving rule — but it should be a *choice*,
not an accident.

---

## 5. Capability table

| Capability | Flag / command | Status | Notes for reimplementation |
| :- | :- | :- | :- |
| Interactive session | `claude` | OBSERVED-DOC + OBSERVED | TTY front-end |
| Initial prompt | `claude "query"` | OBSERVED-DOC | Positional |
| Non-interactive run | `-p` / `--print` | OBSERVED-DOC + OBSERVED | Skips workspace-trust dialog |
| Piped stdin | `cat f \| claude -p "q"` | OBSERVED-DOC | |
| Output formats | `--output-format text\|json\|stream-json` | OBSERVED-DOC + OBSERVED | Enum validated, exit 1 on bad value |
| Input formats | `--input-format text\|stream-json` | OBSERVED-DOC + OBSERVED | Enum validated |
| JSON Schema output | `--json-schema` | OBSERVED-DOC + OBSERVED | Real validator, exit 1 on invalid |
| Turn cap | `--max-turns` | OBSERVED-DOC | Print mode only |
| Spend cap | `--max-budget-usd` | OBSERVED-DOC | Client-side estimate, not billing |
| Continue | `-c` / `--continue` | OBSERVED-DOC | Excludes `-p`/SDK/`/loop` sessions |
| Resume by ID/name/path | `-r` / `--resume` | OBSERVED-DOC | Also accepts `.jsonl` transcript path |
| Fork on resume | `--fork-session` | OBSERVED-DOC | New session ID |
| Fixed session UUID | `--session-id` | OBSERVED-DOC + OBSERVED | UUID validated |
| Session display name | `-n` / `--name` | OBSERVED-DOC + OBSERVED | |
| Model select | `--model` | OBSERVED-DOC + OBSERVED | Alias or full id; init event echoes resolved id |
| Effort level | `--effort` | OBSERVED-DOC + OBSERVED | Invalid → warning, run continues |
| Fallback chain | `--fallback-model` | OBSERVED-DOC | Comma-separated, ordered |
| Advisor tool | `--advisor` | OBSERVED-DOC | Not exercisable on this host |
| Permission mode | `--permission-mode` | OBSERVED-DOC + OBSERVED | 7 accepted values (incl. `default`/`manual` alias) |
| Skip all checks | `--dangerously-skip-permissions` | OBSERVED-DOC | ≡ `bypassPermissions` |
| Allow skip w/o starting in it | `--allow-dangerously-skip-permissions` | OBSERVED-DOC | Adds to Shift+Tab cycle |
| Tool allow-list | `--allowedTools` / `--allowed-tools` | OBSERVED-DOC | Variadic; bare name = availability |
| Tool deny-list | `--disallowedTools` / `--disallowed-tools` | OBSERVED-DOC | Variadic |
| Tool surface restrict | `--tools` | OBSERVED-DOC + OBSERVED | `""` / `"default"` / names |
| Prompt-tool approver | `--permission-prompt-tool` | OBSERVED-DOC | `mcp__<server>__<tool>` |
| Unattended prompts | `--permission-prompts host\|none` | OBSERVED-DOC + OBSERVED | `none` ⇒ auto-deny |
| Extra directories | `--add-dir` | OBSERVED-DOC + OBSERVED | Directory validated; not-a-dir → helpful message |
| Settings file/inline | `--settings` | OBSERVED-DOC + OBSERVED | ≤ 2 MiB file; inline JSON accepted |
| Settings sources | `--setting-sources user,project,local` | OBSERVED-DOC | |
| MCP config | `--mcp-config` | OBSERVED-DOC + OBSERVED | `{"mcpServers":{}}` shape |
| MCP isolation | `--strict-mcp-config` | OBSERVED-DOC + OBSERVED | Dropped the user-scoped server |
| Plugins | `--plugin-dir`, `--plugin-url` | OBSERVED-DOC | Session-only |
| MCP login/logout | `claude mcp login/logout <name>` | OBSERVED-DOC | OAuth |
| System prompt control | 5 flags (§3.3) | OBSERVED-DOC | + `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` |
| Bare profile | `--bare` | OBSERVED-DOC + OBSERVED | Slimmed `system init` event |
| Safe profile | `--safe-mode` | OBSERVED-DOC | All customisations off, core on |
| Restricted profile | `--restricted` | OBSERVED-DOC + OBSERVED | Eval-harness profile |
| Disable skills/commands | `--disable-slash-commands` | OBSERVED-DOC | |
| Hook lifecycle in stream | `--include-hook-events` | OBSERVED-DOC | `hook_started`/`hook_progress`/`hook_response` |
| Partial streaming | `--include-partial-messages` | OBSERVED-DOC | |
| Subagent text forwarding | `--forward-subagent-text` | OBSERVED-DOC | `parent_tool_use_id` |
| Prompt suggestions | `--prompt-suggestions` | OBSERVED-DOC | `prompt_suggestion` event |
| User-message echo | `--replay-user-messages` | OBSERVED-DOC + OBSERVED | Echoed `user` event confirmed |
| Background session | `--bg` / `--background` | OBSERVED-DOC | Not with `-p` |
| Background registry | `claude agents --json` | OBSERVED-DOC + OBSERVED | `pid,cwd,kind,startedAt,sessionId,name,status` |
| Background control | `attach/logs/stop/rm/respawn` | OBSERVED-DOC | `stop`≡`kill` |
| Supervisor | `claude daemon run/status/logs/stop` | OBSERVED-DOC + OBSERVED | `daemon status` exit 1 when down |
| Install/upgrade | `claude install`, `claude update` | OBSERVED-DOC | `stable`/`latest`/version |
| Auth | `claude auth login/logout/status` | OBSERVED-DOC + OBSERVED | `authMethod` enum of 6 |
| Diagnostics | `claude doctor` | OBSERVED-DOC + OBSERVED | Reports its own blind spots |
| Local-state purge | `claude purge` | OBSERVED-DOC + OBSERVED | Interactive picker w/o path |
| Cloud session | `--cloud` | OBSERVED-DOC | `session_`/`cse_` id prefixes |
| Worktree isolation | `-w` / `--worktree` | OBSERVED-DOC | `<repo>/.claude/worktrees/<name>` |
| Plugin manager | `claude plugin` (`claude plugins`) | OBSERVED-DOC + OBSERVED | Alias confirmed |
| Import from other agents | `claude import codex\|gemini\|cursor` | OBSERVED-DOC + OBSERVED | `--dry-run`, `--yes` |
| Ultrareview | `claude ultrareview` | OBSERVED-DOC + OBSERVED | `--json`, `--timeout`, `--post` |
| Typo suggestion | any mistyped subcommand | OBSERVED-DOC + OBSERVED | stderr, exit 1, "Did you mean …?" |

---

## 6. Dependencies (what each surface needs)

| Surface | Network | Account | Model provider | External service |
| :- | :- | :- | :- | :- |
| Interactive / print session | yes | Anthropic OAuth or API key | yes (Anthropic API, or a custom `ANTHROPIC_BASE_URL` gateway) | — |
| `--bare` | yes (model call) | API key strictly, per observed `--help` | yes | — |
| `--safe-mode` | yes | yes | yes | — |
| `--restricted` | yes | yes | yes | — |
| `claude auth status` | no | — | — | — |
| `claude doctor` | partly (managed settings, org policy, Remote Control) | — | — | — |
| `claude agents --json` | no (local IPC/registry) | — | — | local supervisor |
| `claude daemon status/logs` | no | — | — | local supervisor process |
| `claude auto-mode defaults` | no | — | — | — |
| `claude mcp list` | yes (health-checks approved servers) | — | — | MCP servers |
| `claude --cloud` / `--teleport` / `--remote-control` | yes | Anthropic subscription / claude.ai | yes | Claude cloud |
| `claude install` / `update` | yes | — | — | Anthropic release channel |
| `claude setup-token` | yes | Claude **subscription** required | — | — |
| `claude ultrareview` | yes | — | yes | cloud-hosted review service |

**Observed** local paths referenced by the CLI:
`~/.claude/daemon.log` (`claude daemon logs`), `~/.claude/daemon.json`
(`claude daemon --json-path`), `~/.claude.json` (per-project entry removed by
`claude purge`), `~/.claude/` (the `configDirectory` reported by
`claude auth status`), `<repo>/.claude/worktrees/<name>` (`--worktree`),
`~/.claude/skills/<name>/` (`claude plugin init` scaffolds here and auto-loads
as `<name>@skills-dir`).

---

## 7. Limitations of this investigation

- **The doc and the binary disagree in both directions.** Documented-but-not-in-
  `--help`: `--advisor`, `--channels`, `--exec`, `--init`, `--init-only`,
  `--maintenance`, `--max-turns`, `--append-subagent-system-prompt`,
  `--append-subagent-system-prompt-file`, `--append-system-prompt-file`,
  `--teammate-mode`. In-`--help`-but-not-documented: `--brief`, `--file <specs...>`.
  A reimplementation targetting the *documented* surface would omit `--brief`
  and `--file`; a reimplementation targetting *`--help`* would omit `--max-turns`
  and `--exec`. Neither is a superset of the other.
- **`claude --help` is truncated relative to the real parser.** The binary's
  help output did not show `--max-turns`, `--exec`, `--init`, `--init-only`,
  `--maintenance`, `--advisor`, `--channels`, `--append-system-prompt-file`,
  `--append-subagent-system-prompt*`, or `--teammate-mode` — yet `--max-turns`
  was accepted at runtime (no error). The doc's explicit warning on this point
  is accurate and important.
- **Model-dependent behaviour could not be exercised.** This host serves a
  non-Anthropic model id, so `--model`, `--effort` level availability,
  `--advisor`, `--autocompact` token windows, and context-window maths were
  observed only in their *rejected/accepted* form, not in their effect.
- **Anthropic-API-only features were unrunnable.** `claude doctor` states it
  plainly: managed settings, organization policy, and Remote Control were
  "not fetched". `--cloud`, `--teleport`, `--remote-control`, `--channels`,
  `--advisor` are therefore OBSERVED-DOC only.
- **No decompilation, no source extraction, no binary modification.** Only the
  published `--help` surfaces and the documented flag semantics were used.
- **Subcommand behaviour was probed via `--help` only.** I did not run
  `claude update`, `claude install`, `claude logout`, `claude mcp login`,
  `claude purge` (without `--dry-run`), or anything that mutates global state.

---

## 8. Unknowns (evidence cannot establish)

- The **exact algorithm** behind "Did you mean claude update?" — edit distance?
  Levenshtein? Jaro-Winkler? A curated alias table? (`claude udpate` → `update`
  is one transposition; `claude udpate` also plausibly matches a prefix/fuzzy
  matcher.) Not establishable from one sample.
- Whether `--help` output is generated from the same source as the doc page
  (it is not — they disagree), and whether there is a canonical machine-readable
  flag manifest (e.g. a JSON schema for flags) somewhere in the product.
- The **complete set of valid `--permission-mode` values** across versions.
  Observed 6 in `--help` (including `manual`, excluding `default`), and the
  doc lists 7 (`default` plus `manual` as its alias). Whether `default` is a
  deprecated-but-live alias or a distinct code path is not determinable.
- Whether `--effort` accepts additional values in the Anthropic backend that
  the gateway path does not expose ("Available levels depend on the model").
- Whether `--brief` (SendUserMessage tool) and `--file <specs...>` (startup
  file download, `file_id:relative_path`) are documented on a different page or
  are undocumented/experimental.
- The **full list of `--tools` default built-ins** on macOS/Linux/WSL, where
  the doc says `Glob` and `Grep` are excluded. Only the win32 set was observed.
- The precise semantics of `usage` (12 keys) and `subagent_stats` (10 keys)
  sub-objects — observed only as opaque objects.
- Whether `claude daemon` uses a Unix socket on POSIX and what the Windows
  equivalent is beyond the observed `\\.\pipe\cc-daemon-*` naming.

---

## 9. Clean-room implementation opportunity — CLI reference

The observable contract of this page is fully re-derivable from the public
documentation plus the help output, and none of it requires reading Anthropic
code. The following is the recommended scope for an independent implementation.

### 9.1 Argument parsing layer

Build a `commander`-style parser (the widely-used idiom: `Option`/`Command`
objects, `--flag value`, `--flag=value`, variadic `<values...>`) and expose:

- **A declared flag registry** with, per flag: name(s), aliases, arity
  (boolean / single / variadic), value domain (free string / closed enum /
  integer / USD / JSON), default, and scope (`interactive` / `print` / `both`).
  Every one of the ~85 documented flags is a row in this table; nothing about
  the *behaviour* behind a flag is copied, only its *surface*.
- **Enum validation with an exact error shape.** Observed contract:
  `error: option '--output-format <format>' argument 'nonsense' is invalid. Allowed choices are text, json, stream-json.` on stderr with exit code 1. Use the same
  pattern for `--permission-mode`, `--input-format`, `--permission-prompts`,
  `--system-prompt-snapshot`, `--prompt-suggestions`.
- **Soft-fail vs hard-fail policy.** Reproduce the observed distinction:
  `--permission-mode`/`--output-format` fail hard (exit 1); `--effort` warns
  and continues. This is a real user-facing difference and is trivially
  reproducible from the documented text.
- **Variadic absorption semantics** — decide deliberately and document it (§4.3).
- **Subcommand dispatch with fuzzy suggestion.** Implement a
  Levenshtein-distance suggestion over the known subcommand set, emit
  `✘ unknown command "<x>"` / `  └ Did you mean claude <y>?` on **stderr**, exit
  **1**, and offer the `claude -p "<x>"` escape hatch.
- **A `--help` that is a *subset* view** is fine, but if you target
  compatibility, ship the documented-but-hidden flags too; the doc explicitly
  warns users that absence from `--help` ≠ unavailability.

### 9.2 Three front-ends over one engine

One session engine (`Session`, `Turn`, `ToolCall`, `Transcript`), three
front-ends:

1. **Interactive TUI** — readline-style input, streaming render, `Shift+Tab`
   mode cycle, `/commands`.
2. **Print mode** — `-p`, with the three output formats.
3. **Background/daemon** — `--bg`, a local registry, `claude agents --json`,
   `attach/logs/stop/rm/respawn`, and a supervisor with a `~/.claude/daemon.log`
   and a socket directory.

### 9.3 The print-mode JSON envelope — treat it as an API

Emit a stable, versioned envelope with the observed key names
(`type`, `subtype`, `result`, `is_error`, `stop_reason`, `terminal_reason`,
`session_id`, `uuid`, `num_turns`, `duration_ms`, `duration_api_ms`,
`total_cost_usd`, `usage`, `modelUsage`, `permission_denials`, `safety_stops`,
`api_error_status`, `ttft_ms`, `ttft_stream_ms`, `time_to_request_ms`,
`first_content_frame_ms`, `queued_turn_count`, `result_index`,
`fast_mode_state`, `fast_mode_disabled_reason`, `subagent_stats`). Provide a
`stream-json` mode emitting `system`/`init`, `assistant`, `user`, `result`,
`hook_started`/`hook_progress`/`hook_response`, `prompt_suggestion` events,
with `parent_tool_use_id` on assistant messages.

### 9.4 Configuration layering

Implement a settings resolver with the documented semantics:
`--settings` (file **or** inline JSON, ≤ 2 MiB) overrides the same keys in
`settings.json`; keys you omit keep file-based values; `--setting-sources`
selects which of `user`/`project`/`local` load; managed settings (policy) layer
above all of them. Support the three isolation profiles as **distinct profiles,
not flags on one path**: `--bare` (performance: skip discovery), `--safe-mode`
(diagnostic: neutralise customisations, keep auth/model/tools/permissions),
`--restricted` (evaluation: strip command-execution and network tools, confine
file tools to working directories, refuse `bypassPermissions`).

### 9.5 System-prompt assembly

Build an assembler with four text operations (replace / replace-from-file /
append / append-from-file), the documented combination rules
(replace+append compose; file form precedes inline form), the
`__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` sentinel (split at the first occurrence,
drop the line, keep the prefix cacheable), and the **snapshot** semantics
(build once at the conversation's first request, record, reuse verbatim on
later requests and resumes until compaction; `--system-prompt-snapshot off`
disables). The snapshot behaviour is the single most valuable detail here: it
is what makes prompt-cache hit rates stable across a long session, and it is
specified precisely enough to reimplement from the prose alone.

### 9.6 Resume / session identity

Persist transcripts as newline-delimited JSON (`.jsonl`) and support resumption
by **UUID**, **display name**, and **absolute `.jsonl` path**; support
`--fork-session` (new ID, same conversation); support `--session-id` with UUID
validation; support `--no-session-persistence`; implement `claude purge`'s
six-item state list (transcripts, task lists, debug logs, file-edit history,
prompt history lines, project entry) with `--dry-run` / `--yes` /
`--interactive` / `--all`.

### 9.7 What *not* to copy

Do not copy Anthropic's *behaviour* behind these flags: the specific default
auto-mode classifier rule text (observable as JSON, but it is Anthropic's
policy content, not an interface contract), the exact system-prompt text, the
internal model routing, or the proprietary binary. Build the interface, not
the policy.

---

## 10. Evidence index

| Artifact | Path |
| :- | :- |
| Raw fetched doc page | `agent-reference-shots/cli-reference/doc-cli-reference.md` |
| `claude --help` (full, 313 lines) | `agent-reference-shots/cli-reference/claude-help-full.txt` |
| Subcommand `--help` dumps (10 commands) | `agent-reference-shots/cli-reference/subcommand-help.txt` |
| This findings file | `agent-reference-shots/cli-reference/cli-reference-findings.md` |
| Print-mode JSON envelope (observed) | `agent-reference-shots/cli-reference/print-mode-json-envelope.json` |
| `stream-json` init event (observed) | `agent-reference-shots/cli-reference/stream-json-init-event.json` |
| `claude agents --json` (observed) | `agent-reference-shots/cli-reference/agents-json.json` |
| `claude auth status` (redacted) | `agent-reference-shots/cli-reference/auth-status-redacted.json` |
| `claude doctor` output | `agent-reference-shots/cli-reference/doctor-output.txt` |
| `claude auto-mode defaults --label` | `agent-reference-shots/cli-reference/auto-mode-defaults-label.json` |

Public doc consulted: <https://code.claude.com/docs/en/cli-reference.md>
