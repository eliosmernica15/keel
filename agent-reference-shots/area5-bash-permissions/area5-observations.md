# Area 5 — Terminal command proposal, approval, execution, and reporting

**Product:** Claude Code 2.1.306 (native Windows build, `win32-x64`)
**Host:** Windows 11, Git Bash available, `pwsh.exe` present
**Method:** public docs at `code.claude.com/docs/en/*` + black-box runs of the published CLI only.
No decompilation, no bundle extraction, no source-map dumping (see `../TERMS-NOTES.md`).
**Model provider on this host:** a custom `ANTHROPIC_BASE_URL` gateway serving a non-Anthropic model.
`claude doctor` reports "Not connected to the Anthropic API (api.anthropic.com)", so any
subscription-gated Anthropic behaviour is **INFERRED from docs**, not observed.

## Status legend

| Tag | Meaning |
| :- | :- |
| `OBSERVED-DOC` | Stated in a public Anthropic document (URL given) |
| `OBSERVED-CLI` | I ran the published CLI and saw it (exact command + output given) |
| `INFERRED` | My conclusion from evidence; reasoning stated |
| `UNKNOWN` | The available evidence cannot establish it |

---

## F1 — The Bash tool's input contract is four named fields plus one sandbox flag

**Status:** `OBSERVED-CLI` + `OBSERVED-DOC`

Observed on the wire in a headless run. The assistant emits a `tool_use` block whose `input`
carries exactly:

```json
{"command":"sh -c 'echo out-line; echo err-line 1>&2; exit 0'",
 "description":"Print a line to stdout and stderr"}
```

and the harness keeps a parallel `wire_tool_inputs` map (the audit copy of what was actually sent):

```json
"wire_tool_inputs":{"call_function_gtxi815nvr8u_1":{
  "command":"sh -c 'echo out-line; echo err-line 1>&2; exit 0'",
  "description":"Print a line to stdout and stderr"}}
```

The PreToolUse hook input schema (public docs) shows the full set the harness can populate:

```json
"tool_name": "Bash",
"tool_input": {
  "command": "npm test",
  "description": "Run test suite",
  "timeout": 120000,
  "run_in_background": false
}
```

and the sandboxing docs add a fifth, `dangerouslyDisableSandbox` (boolean), which is set on the
retry that runs a command outside the sandbox.

Field semantics:
- `command` — the shell text. Required.
- `description` — an **agent-authored** human-readable label, shown in the permission prompt
  under the command. Not a claim of safety; it is the agent's own words.
- `timeout` — milliseconds. The model chooses it; the ceiling is enforced by the harness.
- `run_in_background` — boolean.
- `dangerouslyDisableSandbox` — boolean, only meaningful on the sandbox-retry path.

**INFERRED (reasoning):** the harness, not the model, is the security boundary. `description` is
model-generated text, so it must never be treated as an authorisation signal — the `command` field
is the only thing the permission matcher inspects. This is consistent with the docs' statement
that "Permission rules are enforced by Claude Code, not by the model."

**Clean-room opportunity:** define your own shell tool with an explicit, small input schema
(`command`, `description`, `timeout`, `run_in_background`) and treat `description` as pure
display metadata. Do not let the model supply any field that widens its own permissions —
keep sandbox/permission flags on the host side of the boundary.

**Source:** https://code.claude.com/docs/en/hooks ; https://code.claude.com/docs/en/sandboxing

---

## F2 — A successful command returns a typed payload; a failure returns in-band text

**Status:** `OBSERVED-CLI`

Success — `tool_use_result` is a structured object:

```json
{"stdout":"out-line\nerr-line","stderr":"","interrupted":false,
 "isImage":false,"noOutputExpected":false}
```

and the `tool_result` content block carries the plain merged text `"out-line\nerr-line"` with
`is_error:false`.

**Correction to an obvious assumption — the `stderr` field is always empty.** A second run writing
only to stderr confirmed it:

```json
{"stdout":"ONLY-ERR","stderr":"","interrupted":false,"isImage":false,"noOutputExpected":false}
```

The command wrote to fd 2 exclusively, yet the payload reports it in **`stdout`** and leaves
`stderr` empty. So the harness runs the child with **stdout and stderr merged into a single
stream** (one pipe), and reports the merged text in `stdout`. The `stderr` key exists in the
schema but is not populated on this path.

Failure — the payload collapses to a **string** and the exit status is embedded in the text:

```json
{"content":"Exit code 7\nout-line\nerr-line","is_error":true}
```

with `tool_use_result` = `"Error: Exit code 7\nout-line\nerr-line"`.

Verified by running (exit 7, one line on stdout, one on stderr):

```
claude -p "Run exactly this shell command and nothing else:
  sh -c 'echo out-line; echo err-line 1>&2; exit 7'"
  --output-format stream-json --verbose --permission-mode acceptEdits --allowedTools "Bash(sh *)"
```

Artifacts: `stream-success-payload.jsonl`, `stream-stderr-only.jsonl`, `stream-exit-nonzero.jsonl`.

**Key implementation detail:** stdout and stderr are **interleaved into one stream** in both the
success and failure paths — the harness does not keep them separate anywhere. The agent in the
exit-7 run correctly recovered all three facts (stdout line, stderr line, exit code 7) from the
merged blob.

**INFERRED (reasoning):** merging stdout/stderr is lossy but deliberate — it preserves interleaving
order, which is what matters when diagnosing a build or test failure, and it avoids a deadlock
when a child writes a lot to both streams. The cost is that a model cannot reliably tell "this line
is an error" from "this line is output" — it must infer from content. A clean-room implementation
should decide deliberately: keep `stdout`, `stderr`, and `exit_code` as separate fields *and*
additionally emit an interleaved transcript, so the model gets both order and attribution.

**Clean-room opportunity:** return `{stdout, stderr, exit_code, interrupted, duration_ms}` always
— never a pre-rendered string — and let the renderer compose the human-facing text. That is
strictly more useful to a model than a merged blob and is trivially implementable. If you merge
for ordering, merge *in addition to* separate streams, not *instead of* them.

**Source:** https://code.claude.com/docs/en/tools-reference

---

## F3 — Exit code 1 is only a failure for some commands

**Status:** `OBSERVED-DOC`

> "A command that exits 1 counts as a valid result for the Bash tool only when Claude Code
> recognizes exit code 1 as a benign outcome for that command: `grep`, `rg`, `egrep`, `fgrep`,
> `find`, `diff`, `test`, and `[`, plus `git diff` and `git grep`. Every other command that exits 1
> counts as a failure, even when exit 1 is a benign informational outcome: no matches for
> `pgrep` and `jq -e`, files that differ for `cmp`."

So `grep -q foo file` returning 1 (no match) is a **successful** tool result, while `pgrep foo`
returning 1 is a **failure**. The list is a fixed, built-in table of benign-exit-1 commands.

**Clean-room opportunity:** keep a small, explicit, user-visible table of "exit 1 is benign"
command patterns (or better, invert it — a table of "exit 1 is fatal"), and surface it in the
permission dialog so the user can see why a command was treated as a failure.

**Source:** https://code.claude.com/docs/en/tools-reference#output-limits

---

## F4 — Output truncation is a three-tier ladder, and the overflow notice is a parseable envelope

**Status:** `OBSERVED-CLI` + `OBSERVED-DOC`

Docs give the ladder:

| Result | What the model gets |
| :- | :- |
| Valid | Inline up to roughly **30,000** characters by default; past that, the path of a file saved to the session directory and truncated past 64 MiB, plus a preview of up to the first **2,000** characters |
| Failure | Inline up to roughly **10,000** characters; past that, a **head-and-tail excerpt** of that size cut from the read-back window, with **no file path** |

Observed end-to-end. A command emitting 2000 padded lines (~196 KB) produced this exact tool
result:

```
<persisted-output>
Output too large (196.2KB). Full output saved to: C:\Users\Admin\.claude\projects\<sanitized-cwd>\<session-id>\tool-results\bmmw375ck.txt

Preview (first 2KB):
LINEPAD-XXX...-1
LINEPAD-XXX...-2
...
</persisted-output>
```

Points worth copying:
- The overflow notice is wrapped in explicit `<persisted-output>` / `</persisted-output>` tags, so
  the model can recognise "there is more, here is where" without prose parsing.
- The overflow file lives **inside the session directory** (`~/.claude/projects/<sanitized-cwd>/
  <session-id>/tool-results/<id>.txt`), not in a temp dir, so it survives alongside the transcript
  and is addressable by the `Read` tool.
- The size is reported in KB with one decimal (`196.2KB`).
- There is a hard **5 GB** kill: "Claude Code streams a command's output to a working file as the
  command runs; a command whose output passes 5 GB is killed."

Related knobs (`OBSERVED-DOC`):
- `BASH_MAX_OUTPUT_LENGTH` — read-back window, default `30000`, hard ceiling `150000`.
- `bashOutputMaxChars` (settings) — sizes the *inline* ceiling and the read-back window together,
  up to `128000`, and then makes Claude Code **ignore** `BASH_MAX_OUTPUT_LENGTH`. Requires v2.1.261+.

**INFERRED (reasoning):** the overflow file plus a preview is strictly better than a hard cut
because the model can then `Read` or `Grep` the file — the truncation notice is an instruction to
the model to re-read with a targeted tool, not a dead end. The failure path's head-and-tail
excerpt has no file pointer, which is a real asymmetry: a failing command's overflow output is
unrecoverable except by re-running it.

**Clean-room opportunity:** always write stdout+stderr to a per-task file in a session-scoped
directory and return `{inline_preview, output_file_path, total_bytes, truncated}`. Return the file
path even on failure — that is the single highest-value improvement over the observed behaviour.

**Source:** https://code.claude.com/docs/en/tools-reference#output-limits ;
https://code.claude.com/docs/en/settings-reference ; https://code.claude.com/docs/en/env-vars

---

## F5 — Foreground timeout auto-promotes the command to the background

**Status:** `OBSERVED-DOC`

Rather than killing a command at its timeout, the harness **moves it to the background** and tells
the model so. The exact result text is documented:

> `Command did not complete within its 120s timeout and was moved to the background`

— "with the seconds matching the timeout that applied, followed by the task ID and the path of the
file the output is being written to."

Two further exact strings, worth copying verbatim because they prevent the model from acting on a
state change that did not happen:

> `Session cwd remains <dir>; directory changes made by the backgrounded command do not apply to subsequent commands.`

Exceptions and controls:
- A command starting with `sleep` is **stopped** at its timeout instead of being backgrounded.
- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, or `--bare`, disables auto-backgrounding; the command
  then simply stops.
- Timeouts: `BASH_DEFAULT_TIMEOUT_MS` = `120000` (2 min) default; `BASH_MAX_TIMEOUT_MS` =
  `600000` (10 min) default ceiling; "the effective ceiling is the larger of the two".

**Clean-room opportunity:** implement the timeout as a *state transition* (foreground → background)
rather than a kill, and emit a structured event (`{state:"backgrounded", reason:"timeout",
task_id, output_path, timeout_ms}`) instead of a prose sentence, so a client can render it.

**Source:** https://code.claude.com/docs/en/tools-reference#foreground-commands-that-move-to-the-background ;
https://code.claude.com/docs/en/env-vars

---

## F6 — Background execution has a fully specified three-party contract

**Status:** `OBSERVED-CLI`

Running a background command with `run_in_background: true` produced, in order:

**a. The tool call** —
```json
{"type":"assistant","message":{"content":[{"type":"tool_use",
  "id":"call_function_8qg29t9um0yl_1","caller":{"type":"direct"},"name":"Bash",
  "input":{"command":"sh -c 'for i in 1 2 3; do echo tick-$i; sleep 1; done'",
           "description":"Run loop echoing tick-1 through tick-3","run_in_background":true}}]}}
```

**b. A `background_tasks_changed` system event** listing the task —
```json
{"type":"system","subtype":"background_tasks_changed",
 "tasks":[{"task_id":"bzzuzyibe","run_id":"0mviemewu-87c1467f",
           "task_type":"local_bash","description":"Run loop echoing tick-1 through tick-3"}]}
```

**c. A `task_started` event** carrying `is_backgrounded:true`, `task_type:"local_bash"`, and the
originating `tool_use_id`:
```json
{"type":"system","subtype":"task_started","task_id":"bzzuzyibe",
 "run_id":"0mviemewu-87c1467f","tool_use_id":"call_function_8qg29t9um0yl_1",
 "description":"Run loop echoing tick-1 through tick-3","is_backgrounded":true,
 "task_type":"local_bash","uuid":"1b41ada1-097a-4fb1-9261-9fdda776cf50",
 "session_id":"df467381-a907-431d-a6a8-e8bcbd2c150d"}
```

**d. The immediate tool result** — the model is told the ID, the file, and that it will be
notified:
```
Command running in background with ID: bzzuzyibe. Output is being written to:
C:\Users\Admin\AppData\Local\Temp\claude\C--Users-Admin-Desktop-Claude-clone\
df467381-a907-431d-a6a8-e8bcbd2c150d\tasks\bzzuzyibe.output.
You will be notified when it completes. To check interim output, use Read on that file path.
```
with `tool_use_result` = `{"stdout":"","stderr":"","interrupted":false,"isImage":false,
"noOutputExpected":false,"backgroundTaskId":"bzzuzyibe"}`.

**e. Completion events** —
```json
{"type":"system","subtype":"task_updated","task_id":"bzzuzyibe",
 "run_id":"0mviemewu-87c1467f","patch":{"status":"completed","end_time":1792604817478},
 "uuid":"9674b3f5-eee4-4a79-a4ce-0f6fd9b3b9ac","session_id":"df467381-a907-431d-a6a8-e8bcbd2c150d"}
{"type":"system","subtype":"task_notification","task_id":"bzzuzyibe",
 "run_id":"0mviemewu-87c1467f","tool_use_id":"call_function_8qg29t9um0yl_1",
 "status":"completed","output_file":"...\\tasks\\bzzuzyibe.output",
 "summary":"Background command \"Run loop echoing tick-1 through tick-3\" completed (exit code 0)"}
```
followed by a `background_tasks_changed` event with an empty task list, and then a **new assistant
turn** — the model is re-invoked with the outcome rather than having to poll.

**Design points worth copying:**
- The background output file lives under a **per-session temp directory**
  (`%LOCALAPPDATA%\Temp\claude\<sanitized-cwd>\<session-id>\tasks\<task-id>.output`), unlike the
  foreground overflow file which lives in the session directory.
- The completion notification carries a **human-readable summary** with the exit code inlined:
  `Background command "<description>" completed (exit code 0)`. The `description` the model
  supplied at call time is what gets echoed back — so a good `description` is what makes the
  notification legible.
- The task id is a short opaque token (`b66s2c1p4`) distinct from the `tool_use_id`; both appear.
- `TaskOutput` was **removed in v2.1.277** — the model now reads the background task's output file
  with the ordinary `Read` tool instead of a dedicated retrieval tool.

**Clean-room opportunity:** emit task lifecycle as first-class typed events (`task_started`,
`task_progress`, `task_updated`, `task_notification`) on the same stream as the model messages, so
a UI can render a task panel and a client can resume without polling. Use a per-session temp
directory for live output and a per-session directory for retained artefacts.

**Source:** https://code.claude.com/docs/en/tools-reference#background-commands ;
https://code.claude.com/docs/en/interactive-mode#background-bash-commands

---

## F7 — Background commands have time limits in unattended sessions, and a fixed stop notice

**Status:** `OBSERVED-DOC`

> "In a session that runs unattended, such as a run with the `-p` flag, an Agent SDK application,
> a CI job, or a cloud session, background Bash and PowerShell commands have a time limit. A local
> session you work in from a terminal, the desktop app, or the VS Code extension has no time limit
> on background commands."

Limits, counted from the moment the command enters the background:
- Backgrounded at the model's request: **30 minutes**, or the `timeout` the model passed with
  `run_in_background`, to a maximum of **2 hours**.
- Moved from foreground by a timeout: **30 minutes** from the move.
- In a `-p` run whose prompt was passed as text (not `--input-format stream-json`): both defaults
  become **10 minutes** instead of 30, "because the run waits for background commands after its result".

Stop notice, exact text:
> `Background command "<description>" was stopped after reaching its background time limit`

Raising it: `BASH_DEFAULT_TIMEOUT_MS` above `1800000` replaces the 30-minute default;
`BASH_MAX_TIMEOUT_MS` above `7200000` raises the 2-hour maximum. Neither variable can *shorten* a
limit. Also `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` (default `600000`, `0` = wait forever) caps how
long a `-p` run idles waiting for background work.

**Clean-room opportunity:** make the "unattended" boundary explicit in your product — an
interactive session has no background cap, a headless/CI session does — and emit the stop reason as
a structured field rather than an English sentence, so a client can render it locally.

**Source:** https://code.claude.com/docs/en/tools-reference#time-limit-for-background-commands ;
https://code.claude.com/docs/en/headless#background-tasks-at-exit ; https://code.claude.com/docs/en/env-vars

---

## F8 — Permission rules: `Tool(specifier)`, evaluated deny → ask → allow, first match wins

**Status:** `OBSERVED-DOC`

Rule syntax: `Tool` or `Tool(specifier)`. "Parentheses inside the specifier are literal, so a
command or path that contains them needs no escaping."

Evaluation:
> "Rules are evaluated in order: deny, then ask, then allow. The first match in that order
> determines the outcome, and rule specificity doesn't change the order."

Consequences, all documented:
- A broad deny (`Bash(aws *)`) beats a narrower allow (`Bash(aws s3 ls)`). "An allow rule can't
  carve an exception out of a deny rule."
- An ask rule matches even when a more specific allow rule also matches.
- A **bare** tool name in `deny` (e.g. `"Bash"`, or `"Bash(*)"`) removes the tool from the model's
  context entirely — the model never sees it. A **scoped** rule (`Bash(rm *)`) leaves the tool
  present and blocks matching calls.
- Tool-name **globs** work in deny/ask: `"*"` matches every tool, `"mcp__*"` every MCP tool. Allow
  rules accept globs only after a literal `mcp__<server>__` prefix (`mcp__puppeteer__*`); an
  unanchored allow glob such as `"*"` or `"mcp__*"` is silently skipped.
- Settings precedence: **managed settings are highest and cannot be overridden by any CLI flag.**
  "If a tool is denied at any level, no other level can allow it."
- `permissions.disableBypassPermissionsMode` / `permissions.disableAutoMode: "disable"` can remove
  those modes entirely.

Setting keys and defaults (`OBSERVED-DOC`): `permissions.allow`, `permissions.ask`,
`permissions.deny` (arrays of rule strings, unset by default); `permissions.defaultMode`
(string, default `"default"`); `permissions.additionalDirectories`; `permissions.
blockReadsOutsideWorkingDirectories` (boolean, default `false`); `permissions.disableBypass-
PermissionsMode` (boolean, default `false`); `permissions.disableAutoMode` (string `"disable"`).

CLI equivalents: `--allowedTools` / `--allowed-tools` and `--disallowedTools` / `--disallowed-tools`,
both accepting the same `Tool(specifier)` grammar; `--tools` restricts the tool *set*; `--permission-mode`
selects the baseline mode.

**INFERRED (reasoning):** deny-first evaluation with scope-independent ordering is a deliberately
conservative design: it means a user who writes `deny: ["Bash(git push *)"]` can be certain that
no *other* rule in *any* file silently re-allows it. The corollary is that specificity is not a
priority — an implementer who ranks "most specific wins" would build a materially weaker
boundary.

**Clean-room opportunity:** implement rule evaluation as a strict three-pass scan
(deny → ask → allow) with first-match-wins inside each pass, and treat bare-name deny rules as
*tool removal from the model's tool list* rather than as a call-time block. Both behaviours are
observable to a user and easy to get wrong.

**Source:** https://code.claude.com/docs/en/permissions ;
https://code.claude.com/docs/en/settings-reference ; https://code.claude.com/docs/en/cli-reference

---

## F9 — Bash wildcard semantics have sharp edges that are documented with worked examples

**Status:** `OBSERVED-DOC`

The `*` in a Bash rule "matches any text, including spaces". The documented matching table:

| You write | Matches | Doesn't match |
| :- | :- | :- |
| `Bash(npm run build)` | `npm run build` | `npm run build --watch` |
| `Bash(npm run *)` | `npm run build`, `npm run test --watch`, `npm run` | `npm install` |
| `Bash(git log * main)` | `git log --oneline main`, `git log -5 main`, `git log --output=<file> main` | `git log main`, `git push origin main` |
| `Bash(git * main)` | `git merge main`, `git push origin main`, `git -c core.fsmonitor=<script> diff main` | `git log` |
| `Bash(* --version)` | `node --version`, `bash -c 'echo hi' --version` | `node -v` |
| `Bash(ls *)` | `ls -la`, `ls` | `lsof` |
| `Bash(ls*)` | `ls -la`, `lsof` | |

Three rules explain the table:
1. `*` stands in for whatever text is in its place — including subcommands and options.
2. A trailing ` *` (space before the star) **also matches the bare command**: `Bash(ls *)` matches
   `ls`. This holds "only when the trailing `*` is the rule's only wildcard": `Bash(* --help *)`
   matches `npm --help x` but not `npm --help`.
3. **The space before a trailing `*` is part of the rule.** `Bash(ls *)` requires a space after
   `ls`, so `lsof` does not match; `Bash(ls*)` has no space, so it matches `lsof` too.

`Bash(ls:*)` is an equivalent spelling of a trailing wildcard. The `:*` form is "only recognized
at the end of a pattern" — in `Bash(git:* push)` the colon is literal.

The permission dialog "writes the space-separated form when you select 'Yes, and don't ask again'".

Warning, quoted: "Put the `*` after the subcommand." A wildcard *before* the subcommand
(`Bash(git * main)`) matches every git subcommand and every option before it — including `-c`,
which makes git run an arbitrary program. The CLI warns at startup about an allow rule with a `*`
before the subcommand, such as `Bash(git * main)`.

**Clean-room opportunity:** implement the matcher with exactly these three rules (bare star,
trailing-star-with-space, trailing-star-without-space) and expose a `Bash(rule)` → "will match /
will not match" preview in the permission dialog. A rule-preview is the single feature that makes
this class of rule comprehensible to users.

**Source:** https://code.claude.com/docs/en/permissions#wildcard-patterns

---

## F10 — Compound commands are split and each subcommand must be independently allowed

**Status:** `OBSERVED-DOC`

> "Claude Code is aware of shell operators, so a rule like `Bash(safe-cmd *)` won't give it
> permission to run the command `safe-cmd && other-cmd`. The recognized command separators are
> `&&`, `||`, `;`, `|`, `|&`, `&`, and newlines. A rule must match each subcommand independently."

- Deny/ask rules apply when **any** subcommand matches, including a command nested in a subshell,
  a command substitution, or a control-flow body such as a `for` loop. An ask rule like
  `Bash(git clean *)` still prompts for `cd /tmp && git clean -f` or `echo "$(git clean -f)"`.
- A trailing `&&`/`||` with nothing after it makes the command **unparseable**: the harness does not
  split it, so `Bash(npm *)` does not approve `npm test &&`.
- When a compound command is approved with "Yes, and don't ask again", Claude Code **saves a
  separate rule per subcommand** that needed approval — approving `git status && npm test` saves a
  rule for `npm test`, "so future `npm test` invocations are recognized regardless of what precedes
  the `&&`." **Up to 5 rules** may be saved for one compound command.
- `cd` into a directory outside the working directories generates its own `Read` rule for that path.

**Clean-room opportunity:** write a real shell tokenizer (not a regex) that yields a segment list
with operators, and evaluate rules per segment. Persist per-segment rules, not per-compound-string
rules, so a prefix rule keeps working when the command is later composed differently.

**Source:** https://code.claude.com/docs/en/permissions#compound-commands

---

## F11 — Wrapper stripping and env-assignment stripping happen before rule matching

**Status:** `OBSERVED-DOC`

Before matching, the harness strips a fixed, non-configurable set of wrappers:
`timeout`, `time`, `nice`, `nohup`, `stdbuf`, plus the shell builtins `command` and `builtin`, and
zsh's `noglob`. So `Bash(npm test *)` matches `timeout 30 npm test`. **Not** stripped: the query
form `command -v`, and zsh's `nocorrect`.

It also strips a leading assignment of **known-safe** environment variables, so
`Bash(npm test *)` matches `NODE_ENV=test npm test`. An **allow** rule will not match past an
assignment of any other variable; a **deny or ask** rule matches past any leading assignment, so
`Bash(rm *)` in deny still matches `FOO=bar rm -rf tmp/`.

Bare `xargs` is stripped too, so `Bash(grep *)` matches `xargs grep pattern` — but only when
`xargs` has no flags; `xargs -n1 grep pattern` is matched as an `xargs` command.

Development environment runners (`direnv exec`, `devbox run`, `mise exec`, `npx`, `docker exec`)
are **not** in the list. Because those runners execute their argument as a command,
`Bash(devbox run *)` matches whatever comes after `run`, including `devbox run rm -rf .`. The
documented mitigation: write a rule naming both the runner and the inner command, e.g.
`Bash(devbox run npm test)`.

**INFERRED (reasoning):** this is a *defensive* wrapper list — it strips only wrappers whose whole
purpose is to run a command, so the rule sees the real command. The explicit exclusion of
environment runners is a known limitation the docs state plainly, and the docs recommend naming the
inner command rather than trying to make a prefix rule safe.

**Clean-room opportunity:** implement wrapper stripping as a documented, versioned, overridable list
in the same shape (a wrapper rewrites the command to its inner form before matching), and warn the
user when a matched command contains a known runner that is *not* in the list — the "your prefix
rule also approves `devbox run <anything>`" case is a real, documented footgun.

**Source:** https://code.claude.com/docs/en/permissions#wrappers

---

## F12 — A built-in read-only command set runs without a prompt, with a documented list of exceptions

**Status:** `OBSERVED-DOC`

The set "is not configurable" and includes `ls`, `cat`, `echo`, `pwd`, `head`, `tail`, `grep`,
`find`, `wc`, `which`, `diff`, `stat`, `du`, `cd`, and read-only forms of `git`.

In Manual mode these still prompt in specific cases:
- **Unquoted globs** for commands with write-capable flags (`find`, `sort`, `sed`, `git`) — "because
  the glob could expand to a flag like `-delete`."
- **`docker`** pointed at another daemon (`-H`, `--context`, Podman's `--url`/`--connection`).
- **`file`** with `-m`/`--magic-file` or `-f`/`--files-from` — those flags make `file` open the
  paths named in the flag's value.
- **`ps`** when an argument could act as the `e` option (`ps auxe`, `ps aux -e`) — that option
  prints process environment variables. `ps aux` and `ps -ef` do not prompt. (Requires v2.1.290+.)
- **Network paths on Windows** — a command whose arguments include a UNC path (`\\server\share\file`)
  prompts, "because accessing a network path can send your Windows credentials to the host it names."
- **Writes to special shell variables** — setting/unsetting/looping over `PATH` or `IFS` prompts.
- **Unparseable commands** — if the command cannot be fully parsed it asks for approval rather than
  treating it as read-only. **Commands longer than 10,000 characters always prompt.**

Also: `cd` into a path inside the working directory is read-only, and `cd packages/api && ls` runs
without a prompt when each part qualifies on its own. But `cd` **with** `git` prompts when the `cd`
changes directory (new-directory git hooks can execute), and `cd` **with** a redirect prompts when
the redirect target's resolution depends on the new directory.

**INFERRED (reasoning):** the read-only set is a *heuristic*, not a sandbox — the doc is explicit
that it exists for convenience, and lists the ways it can be wrong. The important design property
is that the set is conservative in the ambiguous cases (unknown parse → prompt; glob that could
expand to a flag → prompt). A clean-room implementation should mirror that bias.

**Clean-room opportunity:** implement a read-only command classifier that is **allow-by-default for
explicitly listed read-only commands only**, and that escalates to a prompt on any unparseable
input, any unquoted glob against a write-capable command, and any argument that looks like a
credential-leaking flag (`ps ...e`, `file -f`, docker context flags). The 10,000-character ceiling
is a cheap, effective guard.

**Source:** https://code.claude.com/docs/en/permissions#read-only-commands

---

## F13 — The interactive permission prompt: exact layout, options, and bindings

**Status:** `OBSERVED-CLI` + `OBSERVED-DOC`

Captured live from a Claude Code background session's TUI (`claude logs <id>`, ANSI stripped) —
saved at `agent-reference-shots/area5-bash-permissions/tui-permission-prompt.txt`:

```
● Running 2 shell commands…
  ⎿  $ git --version
────────────────────────────────────── PowerShell command
 List directory contents
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ Get-ChildItem -Force | Format-Table Mode, Length, LastWriteTime, Name -AutoSize
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ │ Command contains malformed syntax that cannot be parsed: pwsh exited with code 1: The command line is too long.
 Do you want to proceed?
 ❯ 1. Yes
   2. No
 Esc to cancel · Tab to amend
```

Structure: a title bar naming the **tool** (`PowerShell command` / `Bash command`), then the agent's
`description`, then the exact command text, with a right-hand `│` gutter carrying the
reason/parse error, then numbered options with `❯` on the selected one, then the key bindings.

Documented option set for a Bash prompt (docs describe a 4-option prompt):
> "Yes; Yes, and don't ask again for: `npm test *`; Yes, and switch to auto mode; and No."

with the footer "Esc to cancel and Tab to amend." The "switch to auto mode" option appears only
when auto mode is available, only in Manual and `acceptEdits` modes, and **not** on PowerShell
prompts (requires v2.1.247+).

**Comment attachment on the prompt** (`OBSERVED-DOC`): on most prompts — including Bash, PowerShell,
file and MCP — moving to **Yes** or **No** and pressing `Tab` opens a comment field on that option.
`Enter` submits with the comment, `Tab` closes the field without answering, `Shift+Tab` closes it
on a file prompt. On **Yes**, the comment is delivered to the model *after* the result; on **No**, it
is delivered *as the reason for the denial* and the model continues.

**Persistence of an approval** (`OBSERVED-DOC`): choosing "Yes, and don't ask again" for a Bash
command saves the rule to `.claude/settings.local.json` at the **root of the git repository**,
resolved through worktrees to the main checkout. "The rule applies to future sessions anywhere in
that repository, including sessions started in subdirectories and in worktrees." A **file-modification
approval is not saved** — it lasts until the session ends.

**Clean-room opportunity:** render the prompt as title / description / exact-command / reason
gutter / numbered options / binding hints, and support a per-answer comment that is delivered to the
model either as post-hoc context (approval) or as the denial reason (refusal). Let the user amend
the command before approving.

**Source:** https://code.claude.com/docs/en/permissions ; https://code.claude.com/docs/en/interactive-mode

---

## F14 — Permission decisions are reported in structured metadata, and denials carry the full tool input

**Status:** `OBSERVED-CLI`

Every tool result carries a `tool_result_meta` array with the permission decision:

```json
"tool_result_meta":[{"id":"call_function_gtxi815nvr8u_1",
  "permission_decision":{"decision":"accept","source":"config","reason_type":"subcommandResults"}}]
```

Observed values:
| `decision` | `source` | `reason_type` | When |
| :- | :- | :- | :- |
| `accept` | `config` | `subcommandResults` | An allow rule matched the command's subcommands |
| `reject` | `config` | `subcommandResults` | A deny rule matched |
| `reject` | `config` | (absent) | Rejected before execution (e.g. parse failure) |

Rejected calls additionally carry a `non_execution_kind` discriminator. Observed values:
- `"permission-rule"` — a deny rule blocked it.
- `"user-rejected"` — the command could not be parsed / was rejected at the prompt.

The **denial message** itself names the tool and the command:
```
Permission to use Bash with command echo denied-test has been denied.
```
delivered as `{"content":"Permission to use Bash with command echo denied-test has been denied.",
"is_error":true}`.

The final `result` envelope aggregates denials:
```json
"permission_denials":[{"tool_name":"Bash","tool_use_id":"call_49b77dede2e44285a7e7ce1f",
  "tool_input":{"command":"echo denied-test","description":"Echo test string"}}]
```
— the **full tool input** is retained, so a caller can audit exactly what was refused.

A second observed rejection shape, when the command could not be parsed and the model then tried
the sandbox override:
```
"This command requires approval"
```
with `non_execution_kind:"user-rejected"`. Both attempts appear in `permission_denials`, the
second carrying `"dangerouslyDisableSandbox":true` in its `tool_input`.

**INFERRED (reasoning):** exposing `decision / source / reason_type` per call is what makes an
agent's permission behaviour auditable after the fact, and `reason_type:"subcommandResults"` tells
the auditor the decision came from a per-subcommand rule evaluation rather than a whole-tool
allow. A clean-room implementation should record the same three axes.

**Clean-room opportunity:** emit a structured decision record with every tool result
(`{decision, source, reason_type, non_execution_kind}`), include the full tool input in any
denial summary, and make the denial message name the tool and the command.

**Source:** this is a direct observation; the equivalent surface is also visible in the
`stream-json` output documented at https://code.claude.com/docs/en/headless

---

## F15 — PreToolUse hooks are the programmable extension point: schema, decisions, exit codes

**Status:** `OBSERVED-DOC`

Hook input (exact shape from the docs):
```json
{
  "session_id": "abc123",
  "prompt_id": "550e8400-e29b-41d4-a716-446655440000",
  "transcript_path": "/home/user/.claude/projects/.../transcript.jsonl",
  "cwd": "/home/user/my-project",
  "scratchpad_dir": "/tmp/claude-1000/-home-user-my-project/abc123/scratchpad",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {"command":"npm test","description":"Run test suite",
                 "timeout":120000,"run_in_background":false},
  "tool_use_id": "toolu_01ABC123..."
}
```

Hook output:
```json
{"hookSpecificOutput":{
  "hookEventName":"PreToolUse",
  "permissionDecision":"deny",
  "permissionDecisionReason":"Database writes are not allowed"}}
```
Decisions: `"allow"` | `"deny"` | `"ask"` | `"defer"`. `updatedInput` under `hookSpecificOutput`
replaces the tool's arguments before it runs.

Exit-code semantics:

| Exit code | Effect |
| :- | :- |
| `0` | Success; valid JSON fields applied. No output = no decision, tool proceeds normally. |
| `2` | Blocking error; the call is blocked and **stderr is the reason**. Valid JSON is read but cannot override the block. |
| other | Non-blocking error, tool continues — **unless** stdout contains valid JSON, in which case the JSON is applied regardless of the nonstandard exit code. Use `"onFailure":"block"` to make failures block. |

The docs warn: "Exit code 1 without valid JSON output is a non-blocking error … If your hook is
meant to enforce a policy, use `exit 2`."

**Precedence** — hooks do **not** override rules:
> "Claude Code evaluates deny and ask rules regardless of what a PreToolUse hook returns: a matching
> deny rule blocks the call, and a matching ask rule still prompts even when the hook returned
> `"allow"` or `"ask"`."

And a blocking hook beats allow rules: "A hook that exits with code 2 stops the tool call before
permission rules are evaluated."

Matching: the `matcher` field filters by **bare tool name** (not the parenthesised rule format); the
handler's `if` field holds **exactly one** permission rule. On Windows you need matcher
`Bash|PowerShell` with a separate handler per tool. The `if` filter is explicitly "best-effort" —
"use the permission system rather than a hook to enforce a hard allow or deny."

**Clean-room opportunity:** implement the same hook protocol — a pre-execution hook that receives
the full tool input and can return `allow`/`deny`/`ask`/`defer` plus a rewritten input, with
`exit 2` meaning "block, and here is why". Keep rule evaluation strictly above hooks so a hook
cannot widen access.

**Source:** https://code.claude.com/docs/en/hooks ; https://code.claude.com/docs/en/permissions#extend-permissions-with-hooks

---

## F16 — Sandbox: OS-level isolation, auto-allow mode, and an explicit unsandboxed escape hatch

**Status:** `OBSERVED-DOC`

The sandbox "is a boundary that the operating system enforces around the shell commands Claude
Code runs on your machine", and it applies to Bash, PowerShell and Monitor commands **and their
child processes**. It does not cover Claude's file tools, MCP servers, or hooks. It runs on macOS,
Linux and WSL2; **on native Windows Claude Code runs commands unsandboxed** (this host is native
Windows, so the sandbox is not directly observable here — flagged as INFERRED for this host).

Two modes:
- **Auto-allow mode** — "Claude Code approves a command automatically, with no prompt, when the
  command runs inside the sandbox." `sandbox.autoAllowBashIfSandboxed` (default `false` in the
  settings reference; the docs note it "still defaults to `true`" in a different context — see
  the note in F17). Even in auto-allow mode: a `Bash` deny rule still blocks; `rm`/`rmdir` against
  a **critical path** still goes through the normal flow; content-scoped ask rules like
  `Bash(git push *)` still force a prompt; a **bare `Bash` ask rule is skipped** for sandboxed
  commands (but not in plan mode); Monitor commands are **not** auto-approved.
- **Regular permissions mode** — all Bash commands go through the normal flow.

**The unsandboxed retry escape hatch:** when a command fails inside the sandbox, Claude Code names
the denied host in the result, the model analyses it, and may retry with
`dangerouslyDisableSandbox: true`. The retry runs **unsandboxed** and is approved differently by
mode: `bypassPermissions` → no prompt; Manual/`acceptEdits` → a prompt titled **"Bash command
(unsandboxed)"**; auto → a separate classifier; `dontAsk` → denied; plan mode → gated.
An ask rule for the parameter itself (`Bash(dangerouslyDisableSandbox:true)`) forces the prompt in
every mode and **takes precedence over a matching allow rule**.

`"allowUnsandboxedCommands": false` disables the retry (the `/sandbox` **Overrides** tab calls this
**Strict sandbox mode**); `failIfUnavailable: true` refuses to start rather than running unsandboxed.

**Network isolation:** "No direct route out. Connections go through a proxy on your machine that
checks each host against your allowed domains, which start empty." Keys: `sandbox.network.
allowedDomains`, `sandbox.network.deniedDomains` (denied takes precedence over allowed wildcards),
`network.allowUnixSockets`, `network.allowLocalBinding`, `network.httpProxyPort`,
`network.socksProxyPort`, `network.strictAllowlist`. Filesystem: `sandbox.filesystem.allowWrite`,
plus a per-user writable temp dir and `$TMPDIR` set for sandboxed commands.

**Clean-room opportunity:** implement the sandbox as a genuinely separate layer from permissions
(OS-enforced, covering child processes), keep the sandbox→unsandboxed retry as an explicit,
separately-approved step with its own prompt title, and expose a "strict sandbox" switch that
ignores the model's request to disable isolation. Never let a broad allow rule imply a broad
sandbox bypass.

**Source:** https://code.claude.com/docs/en/sandboxing

---

## F17 — Protected paths and critical paths are two separate, non-overridable guard rails

**Status:** `OBSERVED-DOC`

**Protected paths** — writes are never auto-approved except in `bypassPermissions` mode (and plan
mode with bypass available). Per-mode outcome:

| Mode | Protected-path writes |
| :- | :- |
| `default`, `acceptEdits` | Prompted |
| `plan` | Allowed only in interactive terminal sessions with bypass available; otherwise routed to the classifier (auto mode) or prompted |
| `auto` | Routed to the classifier |
| `dontAsk` | Denied |
| `bypassPermissions` | Allowed |

**`permissions.allow` rules do not pre-approve protected-path writes** — "The safety check runs
before Claude Code evaluates allow rules from settings." Protected directories include `.git`,
`.config/git`, `.vscode`, `.idea`, `.husky`, `.cargo`, `.devcontainer`, `.yarn`, `.mvn`, `.claude`
(with exceptions such as `.claude/worktrees/`, `~/.claude/plans/`, and a background session's own
`~/.claude/jobs/<id>/tmp/`). Protected files include `.gitconfig`, `.bashrc`/`.zshrc`/`.profile`,
`.npmrc`, `.bazelrc`, `.pre-commit-config.yaml`, `gradle-wrapper.properties`, `.mcp.json`,
`.claude.json`.

**Critical paths** — a separate guard on `rm`/`rmdir`:
> "Claude Code never lets a `permissions.allow` rule or a `PreToolUse` hook that returns `"allow"`
> approve an `rm` or `rmdir` command that targets a critical path, even in modes that skip other
> prompts. This circuit breaker guards against model error."

Critical = filesystem root; top-level directories (`/usr`, `/etc`, `/data`); your home directory
(including the Windows 8.3 short name `C:\Users\LONGNA~1`); Windows drive roots and their
top-level directories (`C:\`, `C:\Windows`, plus the `\\?\C:\` and `\\localhost\C$` spellings);
your working directory and its parents; your additional working directories and their parents
(only when the removal is a glob under them). Additional targets that count: a glob directly under
a shell variable (`rm -rf "$DIR"/*`), a glob under an unset positional parameter, a variable
followed by a common top-level directory name, a value assigned from `$(pwd)` or
`$(git rev-parse --show-toplevel)`, a target that is only command-substitution output, a trailing
command substitution after a critical path, a target that is only backslashes, a Windows volume
GUID path, and some targets ending in `/*` or `/*/`.

`CLAUDE_CODE_DISABLE_SUBSTITUTION_RM_PROMPT=1` turns off only the command-substitution case.

**INFERRED (reasoning):** these two guard rails deliberately sit *above* both allow rules and
hooks. That ordering is the whole point — they exist because the model, having been authorised to
run `rm`, may still generate a catastrophic target. Any clean-room implementation that lets a
user rule or a hook waive them has lost the property that makes them useful.

**Clean-room opportunity:** implement two non-waivable checks evaluated before allow rules and
hooks: (a) protected-path writes routed by mode, (b) a destructive-target circuit breaker with an
explicit critical-path set and variable-expansion analysis. Both are cheap to implement relative to
the damage they prevent.

**Source:** https://code.claude.com/docs/en/permission-modes#protected-paths ;
https://code.claude.com/docs/en/permission-modes#critical-paths

---

## F18 — Auto mode replaces the human prompt with a second, model-based classifier

**Status:** `OBSERVED-DOC` (rule set observed via CLI)

Auto mode "runs without routine prompts; before actions such as shell commands and network requests
run, a background **classifier** checks that they align with your request."

The classifier's decision order is documented as a fixed four-step procedure:
1. Allow/ask/deny rules resolve immediately — **with exceptions**: protected-path writes route to
   the classifier even when an allow rule matches; no allow rule approves `rm`/`rmdir` against a
   critical path; MCP tools marked `requiresUserInteraction` prompt directly; a shell command
   carrying per-command allowed domains routes to the classifier; content-scoped ask rules fall
   back to a prompt; a write whose symlink resolves to a protected path prompts; a read from a
   network path prompts.
2. Read-only actions and file edits in the working directory are auto-approved — except protected
   paths and the **first read outside the working directories**, which prompts.
3. Everything else goes to the classifier.
4. If the classifier blocks, "Claude receives the reason … the reason names the rule the classifier
   matched, such as `[Data Exfiltration]`".

On entering auto mode, **broad allow rules are dropped**: blanket `Bash(*)` / `PowerShell(*)`, wildcarded
interpreters like `Bash(python*)`, package-manager run commands, `Agent` allow rules, and `Monitor`
allow rules. Narrow rules like `Bash(npm test)` stay. "Claude Code restores the dropped rules when
you leave auto mode."

The classifier's view is deliberately narrow: it sees user messages, non-read-only tool calls, and
CLAUDE.md content — **tool results are stripped**, "so hostile content in a file or web page can't
manipulate the classifier directly." A separate server-side probe scans incoming tool results.

The shipped rule set is inspectable from the CLI:

```
claude auto-mode defaults      # the built-in rule set as JSON
claude auto-mode config        # effective config (settings override defaults)
claude auto-mode defaults --label 'Git Destructive'   # filter by rule label
```

`claude auto-mode defaults` was run on this host and returns four groups — `allow`, `soft_deny`,
`hard_deny`, `environment` — of natural-language rules, each a prose policy with a named concept
(e.g. `Security Discussion`, `Transient Retry`, `Local Operations` in `allow`; `Git Destructive`,
`Code That Leaks When Run`, `Production Deploy`, `Sensitive Remote Exec`, `Safety Bypass Flag` in
`soft_deny`). Saved to `agent-reference-shots/area5-bash-permissions/auto-mode-defaults.json`.

Note on the CLI's `soft_deny` semantics: many soft-deny rules carry an explicit consent bar —
"[named+specifics — **must name:** the destructive operation and its target]" — meaning the rule
requires the *user's own words* to name the operation before it is allowed.

**INFERRED (reasoning):** auto mode is a fundamentally different architecture from rule-based
permissions: the authority for a decision moves from a deterministic matcher to a probabilistic
judge reading the transcript. The rule set's own framing (consent bars, "must name", "HARD evaluates
first") shows the designers treating that judge as needing explicit, auditable policy text rather
than a prompt. A clean-room implementation wanting this capability should expect to spend most of
its effort on the *policy corpus*, not the plumbing.

**Clean-room opportunity:** implement a two-layer permission system — deterministic rules first,
then an optional semantic reviewer that sees the transcript but **not tool results**, and whose
reason codes are stable identifiers (`[Code That Leaks When Run]`) so denials are auditable and
tunable. Expose the reviewer's policy as editable JSON so an organisation can tune it.

**Source:** https://code.claude.com/docs/en/permission-modes ;
https://code.claude.com/docs/en/auto-mode-config ; CLI: `claude auto-mode defaults`,
`claude auto-mode config`

---

## F19 — Headless mode: who answers the prompt, and what happens when nobody can

**Status:** `OBSERVED-CLI` + `OBSERVED-DOC`

`--permission-prompts <target>` (choices `host`, `none`; default `host`):
> "Set who answers permission prompts in print mode. With the default `host`, Claude Code sends
> them to the Agent SDK host or the `--permission-prompt-tool` tool. Pass `none` when nobody can
> answer, and Claude Code denies them instead."

With `none`: "your run doesn't consult the host or wait on it. Anything that would prompt is denied
unless a `PermissionRequest` hook allows it, **Claude is told that nobody can approve the request
and not to retry it**, and the run continues."

`--permission-prompt-tool <mcp__server__tool>` routes prompts to an MCP tool; the docs note "The
prompt tool can't approve an MCP tool marked as requiring user interaction: Claude Code converts an
`allow` result for one to a deny."

Observed on this host (v2.1.306): a `claude -p` run with `--disallowedTools "Bash(echo *)"` produced
the denial message and a `permission_denials` array (F14), and the model **did not retry** — it
reported the block and offered alternatives. A run with `--allowedTools "Bash(sh *)"` produced
`permission_decision:{decision:"accept",source:"config",reason_type:"subcommandResults"}`.

A `-p` run also **skips the workspace-trust dialog** and shows no per-server MCP approval prompt
(observed: `claude -p` ran fine in a directory with no trust prompt). And "With Claude Code v2.1.302
or later, `claude -p` runs start in Manual mode when nothing sets a permission mode."

**Clean-room opportunity:** make the "who answers the prompt" question a first-class, explicit
configuration with exactly two answers — *an interactive human* and *nobody*. In the nobody case,
deny, tell the model not to retry, and keep going; do not block the run. Provide a pluggable
"prompt handler" interface so a program can answer prompts programmatically (the SDK `canUseTool`
callback is the equivalent surface).

**Source:** https://code.claude.com/docs/en/headless ;
https://code.claude.com/docs/en/cli-reference ; observed on this host

---

## F20 — The PowerShell tool mirrors Bash with AST-based matching and alias canonicalisation

**Status:** `OBSERVED-DOC` + `OBSERVED-CLI`

Availability: "Windows without Git Bash: the tool is enabled automatically. Windows with Git Bash
installed: the tool is on by default for claude.ai and Console accounts" — on this host both tools
are present, and `init` reported `powershell_path:
C:\Users\Admin\AppData\Local\Microsoft\WindowsApps\Microsoft.PowerShell_...\pwsh.exe`. (Confirmed
in the sibling capture `agent-reference-shots/PROTOCOL-NOTES.md` §16.)

Rule semantics:
- Same shape as Bash rules. `PowerShell` or `PowerShell(*)` matches every command.
- "Common aliases are canonicalized before matching. A rule written for the cmdlet name also matches
  its aliases, so `PowerShell(Get-ChildItem *)` matches `gci`, `ls`, and `dir` as well. Matching is
  case-insensitive."
- "Claude Code parses the **PowerShell AST** and checks each command in a compound command
  independently. Pipeline operators `|`, statement separators `;`, and on PowerShell 7+ the chain
  operators `&&` and `||` split a compound command into subcommands. A rule must match every
  subcommand for the compound command to be allowed."

Process launch: "Claude Code spawns PowerShell with `-ExecutionPolicy Bypass` at process scope only,
so `.ps1` scripts and module imports work on default Windows installs without changing the machine's
policy. Process-scope bypass doesn't override Group Policy `MachinePolicy` or `UserPolicy`." Set
`CLAUDE_CODE_POWERSHELL_RESPECT_EXECUTION_POLICY=1` to respect the machine policy instead.

**Bash deny rules also turn off the PowerShell tool** — a deny rule naming the whole `Bash` tool
disables `PowerShell` too. The docs record the error string: "Denying Bash also turns off the
PowerShell tool, so Claude has neither."

`acceptEdits` mode auto-approves `Set-Content`, `Add-Content`, `Clear-Content` and `Remove-Item`
on in-scope paths, with the same protected-path rules; `Remove-Item` has its own check. A
positional argument containing a quote character still prompts, "because Claude Code can't statically
validate an argument whose quoted and unquoted readings differ."

**Observed:** the interactive TUI renders the PowerShell prompt with the title "PowerShell command"
(the tool name), confirming the two tools present distinct prompts (F13).

**INFERRED (reasoning):** matching a real AST rather than a regex is materially safer for
PowerShell, because PowerShell's syntax admits many ways to reach the same cmdlet. Doing the same
for Bash would be the natural extension, but Bash's grammar is more permissive; the documented
approach for Bash is operator-aware splitting plus wrapper stripping (F10, F11).

**Clean-room opportunity:** on Windows, implement the shell tool over a real parser (AST for
PowerShell, POSIX-shell tokenisation for Bash) and canonicalise command aliases before matching.
Launch PowerShell with a process-scoped execution-policy bypass so a restrictive default policy
does not break legitimate script execution.

**Source:** https://code.claude.com/docs/en/tools-reference#powershell-tool ;
https://code.claude.com/docs/en/permissions#powershell ; https://code.claude.com/docs/en/errors

---

## F21 — The Monitor tool is a distinct execution mode: line-streaming background watch

**Status:** `OBSERVED-DOC`

`Monitor` "runs a command in the background and feeds each output line back to Claude, so it can
react to log entries, file changes, or polled status mid-conversation."

- Every watch has a deadline: **5 minutes by default, at most 30 minutes**, and at most **10
  minutes** in a non-interactive `-p` run. "At the deadline the watch ends. Claude gets one notice,
  so it can start the watch again if it's still needed."
- "When Monitor runs a command, it uses the **same permission rules as Bash**, so `allow` and
  `deny` patterns you have set for Bash apply here too." But: "While auto mode is active, Claude Code sets
  aside allow rules that name `Monitor` itself … so the classifier reviews Monitor commands the
  same way it reviews Bash commands." And in sandbox auto-allow mode, "Monitor tool commands aren't
  approved automatically, though they still run in the sandbox."
- A **WebSocket source** takes a `ws` input (`url` required, `protocols` optional) in place of
  `command`; a single call cannot combine the two. Text messages become one event each; binary
  frames are **not** passed through — Claude receives a placeholder like `[binary frame, 512 bytes]`;
  messages larger than **1 MiB** end the watch; a socket close ends the watch and Claude receives the
  close code. `timeout_ms` applies to WebSocket watches too, and `TaskStop` cancels early.
- Private/link-local/cloud-metadata addresses are denied, as are hosts in
  `sandbox.network.deniedDomains`.
- Not available on Bedrock, Agent Platform or Foundry; not available when `DISABLE_TELEMETRY` or
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` is set; on Windows only when Git Bash is installed.

**INFERRED (reasoning):** Monitor is a *streaming* execution mode, distinct from
`run_in_background: true` (which returns a task ID and a file). The distinguishing behaviour is
that the harness pushes lines into the conversation and re-invokes the model, so the agent can react
mid-flight — a genuinely different interaction primitive from "run and report at the end".

**Clean-room opportunity:** offer both a "background job" (returns a handle; read output later) and
a "watch" (streams events into the conversation) primitive. The watch needs its own deadline, its
own cancellation handle, and its own size limits (the 1 MiB frame cap and the binary-frame
placeholder are good defaults).

**Source:** https://code.claude.com/docs/en/tools-reference#monitor-tool

---

## F22 — `acceptEdits` auto-approves a specific, enumerated set of filesystem commands

**Status:** `OBSERVED-DOC`

> "In addition to file edits, `acceptEdits` mode auto-approves common filesystem Bash commands:
> `mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, and `sed`. These commands are also auto-approved
> when prefixed with safe environment variables such as `LANG=C` or `NO_COLOR=1`, or process
> wrappers such as `timeout`, `nice`, or `nohup`. Like file edits, auto-approval applies only to
> paths inside your working directory or `additionalDirectories`."

Even in `acceptEdits`:
- Each path goes through the symlink check, "so a write that resolves outside that scope isn't
  auto-approved either."
- Paths outside the scope, writes to protected paths, `rm`/`rmdir` removals targeting a critical
  path, and all other Bash commands except the built-in read-only set **still prompt**.
- On Windows, `acceptEdits` also auto-approves `Set-Content`, `Add-Content`, `Clear-Content` and
  `Remove-Item` on in-scope paths (with aliases), and `Remove-Item` has its own check.

**INFERRED (reasoning):** the auto-approve list is deliberately small and *path-scoped*. Note that
`rm` appears in it — the mode does not treat removal as inherently dangerous, but the path scope
and the critical-path breaker (F17) constrain it. That combination is the interesting design:
enumerate the operation, then constrain the target.

**Clean-room opportunity:** implement "accept edits" as a small, enumerated operation list plus a
path-scope predicate plus a destructive-target breaker, rather than as a blanket "trust the agent"
switch. Make the enumeration user-visible so the trust surface is legible.

**Source:** https://code.claude.com/docs/en/permission-modes#auto-approve-file-edits-with-acceptedits-mode

---

## F23 — Environment and state that persist between commands

**Status:** `OBSERVED-DOC`

- **Working directory persists** (main session only): "When Claude runs `cd` in the main session,
  the new working directory carries over to later Bash commands as long as it stays inside the
  project directory or an additional working directory." "Subagent sessions never carry over working
  directory changes." If `cd` lands outside, "Claude Code resets to the project directory and appends
  `Shell cwd was reset to <dir>` to the tool result."
  `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` disables the carry-over.
- **Environment variables do not persist**: "An `export` in one command won't be available in the
  next." (This is a deliberate difference from an interactive shell and is worth copying: it keeps
  the model from building an invisible dependency chain across calls.)
- **Aliases and shell functions are available**: at session start Claude Code sources `~/.zshrc`,
  `~/.bashrc` or `~/.profile` depending on the shell, captures the resulting aliases, functions and
  shell options, and applies them to every Bash command.
- `CLAUDE_ENV_FILE` — point at a shell script to make environment variables persist across Bash
  commands; a SessionStart hook can populate it dynamically.
- **Memory limit**: `CLAUDE_CODE_TOOL_MEMORY_LIMIT` (e.g. `4G`) caps the memory that Bash,
  PowerShell and Monitor commands can use on Linux/WSL. "Claude Code counts all of a session's Bash,
  PowerShell, and Monitor commands against the one cap, not each command on its own." Applied with a
  memory cgroup; when the cap is exceeded "the kernel kills a command, and **nothing in its result
  names the cap**." `CLAUDE_CODE_TOOL_MEMORY_CGROUP_EXCLUDE` exempts kinds by name: `mcp`, `lsp`,
  `hooks`, `plugin`, `helper`, `agent`. Permission-gating hooks and the MCP servers they call are
  always excluded, "so the kernel killing a permission-gating hook can't allow the action it was
  blocking."

**Clean-room opportunity:** mirror the cwd-persists / env-does-not-persist split — it is a
deliberate trade that keeps command calls reproducible. Expose a session-wide memory cap for tool
subprocesses with an exemption list that always protects policy-enforcing processes.

**Source:** https://code.claude.com/docs/en/tools-reference#what-persists-between-commands ;
https://code.claude.com/docs/en/env-vars

---

## F24 — Windows-specific shell behaviour is a distinct, documented surface

**Status:** `OBSERVED-CLI` + `OBSERVED-DOC`

This host is native Windows, which surfaces several Windows-only behaviours:

- **Both** `Bash` (Git Bash) and `PowerShell` tools are present by default; `init` reports
  `powershell_path`.
- The sandbox does **not** run on native Windows ("On native Windows, Claude Code runs commands
  unsandboxed"); WSL2 is required.
- **UNC / network paths** are a first-class concern: "on Windows, a UNC path such as
  `\\server\share\file`" makes a read "get its own permission check" because "on Windows that
  contact can send the host your credentials". A read-only Bash or PowerShell command whose
  arguments include a UNC path **still prompts in Manual mode**. Since v2.1.292, a network-path
  read "leaves the prompt in place" — allow rules, PreToolUse hooks returning `"allow"`, and the
  auto-mode classifier **do not** remove it; in `dontAsk` mode it is denied; in `bypassPermissions`
  it runs without the prompt.
- **Paths are normalised to POSIX form before matching**: "`C:\Users\alice` becomes `/c/Users/alice`,
  so use `//c/**/.env` to match `.env` files anywhere on that drive. To match across all drives, use
  `//**/.env`."
- **Critical-path spellings** include the Windows 8.3 short name (`C:\Users\LONGNA~1`), `\\?\C:\`,
  `\\localhost\C$`, and volume GUID paths — all treated as the drive root.
- **`rm -rf "\\"`** is treated as a critical-path removal "on every platform", because Git Bash reads
  a lone backslash as the current drive's root.

**Observed, first-hand:** the interactive TUI showed a PowerShell command that failed at parse time
with `Command contains malformed syntax that cannot be parsed: pwsh exited with code 1: The command
line is too long.` — a pre-execution parse failure surfaced as a *permission-style prompt* with the
reason in the right-hand gutter, and the tool result marked it
`non_execution_kind: "user-rejected"`. This confirms that a command which cannot be parsed is
never executed and never silently trusted.

**Clean-room opportunity:** on Windows, normalise paths to a single canonical form before matching
(`/c/Users/...`), treat UNC paths as requiring an explicit approval that allow rules cannot
waive, and refuse to execute any command the parser cannot fully understand.

**Source:** https://code.claude.com/docs/en/permissions#network-paths ;
https://code.claude.com/docs/en/permission-modes#which-paths-are-critical ;
https://code.claude.com/docs/en/tools-reference#powershell-tool

---

## Capability table

| Capability | Status | Evidence | Notes |
| :- | :- | :- | :- |
| Bash tool input = `command`/`description`/`timeout`/`run_in_background` (+`dangerouslyDisableSandbox`) | OBSERVED-CLI + OBSERVED-DOC | F1 | `description` is agent-authored; not an auth signal |
| PowerShell tool with the same shape | OBSERVED-DOC + OBSERVED-CLI | F20, F24 | AST-based rule matching; alias canonicalisation |
| Separate process per command | OBSERVED-DOC | F23 | cwd persists (main session), env does not |
| Success payload `{stdout, stderr, interrupted, isImage, noOutputExpected}` | OBSERVED-CLI | F2 | Typed, not a pre-rendered string |
| stdout and stderr are **merged into one pipe**; the `stderr` field is always empty | OBSERVED-CLI | F2 | Confirmed by a stderr-only run: text appears in `stdout` |
| Failure payload = in-band text `"Exit code N\n…"` with `is_error:true` | OBSERVED-CLI | F2 | stdout/stderr merged on the failure path |
| Benign exit-1 command table | OBSERVED-DOC | F3 | grep/rg/egrep/fgrep/find/diff/test/[/git diff/git grep |
| Inline output ~30,000 chars (valid) / ~10,000 (failure) | OBSERVED-DOC | F4 | |
| Overflow → session-dir file path + 2,000-char preview in `<persisted-output>` tags | OBSERVED-CLI | F4 | 5 GB hard kill |
| `BASH_MAX_OUTPUT_LENGTH` (30k/150k) and `bashOutputMaxChars` (→128k, overrides the env var) | OBSERVED-DOC | F4 | |
| Timeout 120s default / 600s ceiling; effective ceiling = max of the two env vars | OBSERVED-DOC | F5 | |
| Timeout auto-promotes foreground → background (except `sleep`) | OBSERVED-DOC | F5 | Exact result text documented |
| Background task: id + output file + "you will be notified" | OBSERVED-CLI | F6 | `backgroundTaskId` in the payload |
| Background lifecycle events on the stream | OBSERVED-CLI | F6 | `background_tasks_changed`, `task_started`, `task_updated`, `task_notification` |
| Background completion summary with exit code | OBSERVED-CLI | F6 | `Background command "<desc>" completed (exit code 0)" |
| `TaskOutput` removed in v2.1.277 — read the output file with `Read` | OBSERVED-DOC | F6 | |
| Background time limits 30 min / 2 h max (10 min in `-p`) | OBSERVED-DOC | F7 | No limit in interactive sessions |
| Rule grammar `Tool(specifier)`; deny → ask → allow, first match wins | OBSERVED-DOC | F8 | Bare-name deny removes the tool from the model's context |
| Tool-name globs in deny/ask (`*`, `mcp__*`) | OBSERVED-DOC | F8 | Allow globs only after a literal `mcp__<server>__` |
| Managed settings cannot be overridden by any flag | OBSERVED-DOC | F8 | |
| Bash wildcard semantics (bare / trailing-with-space / trailing-without-space) | OBSERVED-DOC | F9 | `:*` == trailing ` *` |
| Compound-command splitting on `&& \|\| ; \| \|& &` and newline | OBSERVED-DOC | F10 | Per-subcommand rules; max 5 saved per approval |
| Wrapper stripping (timeout/time/nice/nohup/stdbuf/command/builtin/noglob/xargs) | OBSERVED-DOC | F11 | Known-safe env-assignment stripping too |
| Read-only command set + the cases that still prompt | OBSERVED-DOC | F12 | Unparseable or >10,000 chars always prompts |
| Interactive prompt: tool title / description / command / options / bindings | OBSERVED-CLI + OBSERVED-DOC | F13 | "Yes, and don't ask again", "Yes, and switch to auto mode" |
| Per-answer comment field (Tab) delivered to the model | OBSERVED-DOC | F13 | Comment = denial reason on No |
| "Don't ask again" persists to `.claude/settings.local.json` at the git root | OBSERVED-DOC | F13 | Edit approvals are session-only |
| Structured permission decision metadata on every result | OBSERVED-CLI | F14 | `decision`/`source`/`reason_type`/`non_execution_kind` |
| Denial message names tool + command; `permission_denials[]` keeps full tool input | OBSERVED-CLI | F14 | |
| PreToolUse hook input/output schema; exit 0/2/other semantics | OBSERVED-DOC | F15 | `allow`/`deny`/`ask`/`defer` + `updatedInput` |
| Hooks cannot override deny/ask rules; exit 2 beats allow rules | OBSERVED-DOC | F15 | |
| OS-level sandbox with auto-allow mode and per-command domain allowlist | OBSERVED-DOC | F16 | Not available on native Windows |
| `dangerouslyDisableSandbox` retry with its own prompt title | OBSERVED-DOC + OBSERVED-CLI | F16 | Ask rule `Bash(dangerouslyDisableSandbox:true)` forces it |
| Strict sandbox mode (`allowUnsandboxedCommands:false`) | OBSERVED-DOC | F16 | |
| Protected paths, per-mode outcome, not waivable by allow rules | OBSERVED-DOC | F17 | |
| Critical-path `rm`/`rmdir` circuit breaker | OBSERVED-DOC | F17 | Not waivable by allow rules **or** hooks |
| Auto mode: model-based classifier with a fixed 4-step decision order | OBSERVED-DOC | F18 | Broad allow rules dropped on entry |
| Classifier sees the transcript but not tool results | OBSERVED-DOC | F18 | |
| Shipped classifier rules inspectable as JSON | OBSERVED-CLI | F18 | `claude auto-mode defaults` / `config` |
| Headless: `--permission-prompts host\|none`, `--permission-prompt-tool` | OBSERVED-CLI + OBSERVED-DOC | F19 | `none` → deny + "don't retry" |
| `-p` skips the workspace-trust dialog | OBSERVED-DOC + OBSERVED-CLI | F19 | |
| `acceptEdits` auto-approves an enumerated command list, path-scoped | OBSERVED-DOC | F22 | `mkdir touch rm rmdir mv cp sed` (+ PS equivalents) |
| Monitor tool: line-streaming watch with 5/30/10-min deadlines | OBSERVED-DOC | F21 | Shares Bash permission rules |
| Monitor WebSocket source; 1 MiB frame cap; binary frames placeholdered | OBSERVED-DOC | F21 | |
| Windows: UNC paths prompt even with an allow rule | OBSERVED-DOC + OBSERVED-CLI | F24 | Requires v2.1.292+ |
| Windows: paths normalised to `/c/...` before matching | OBSERVED-DOC | F24 | |
| Unparseable command → prompt, never executed | OBSERVED-CLI | F24 | Observed as `pwsh ... command line is too long` |

---

## Dependencies

| Dependency | Needed for | Notes |
| :- | :- | :- |
| A model provider reachable over HTTP | every turn | This host uses a **custom** `ANTHROPIC_BASE_URL` gateway; `claude doctor` reports "Not connected to the Anthropic API (api.anthropic.com)". Anthropic subscription-gated behaviour is therefore **INFERRED**, not observed. |
| `api.anthropic.com` / Anthropic credentials | auto-mode server-side classifier review; Remote Control; cloud sessions; org policy fetch | `claude doctor`: "Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL". |
| A POSIX shell (Git Bash on Windows) | the `Bash` tool | Monitor is Windows-available "only when Git Bash is installed". |
| `pwsh.exe` (PowerShell 7+) | the `PowerShell` tool on Windows | Auto-detected; falls back to `powershell.exe` (5.1). |
| OS sandbox support (macOS / Linux / WSL2) | the Bash sandbox | **Not** available on native Windows. |
| A local MCP server process | MCP tools | Observed: `rea: cmd.exe /d /c npx -y rea-agents@6.7.0 mcp - ✔ Connected`. MCP servers connect **asynchronously** — `init` reported `{"name":"rea","status":"pending"}` — and their tools are **deferred**, resolved on demand via `ToolSearch`. |
| `git` on PATH | repo-aware behaviour | `claude doctor` also runs `git` to decide whether `.claude/settings.local.json` is tracked. |
| Disk space in the temp filesystem | background + overflow output | Error strings exist for full disk (`ENOSPC`, `EDQUOT`) and out-of-inodes. |

---

## Limitations of this investigation

1. **The interactive TUI could not be driven directly.** The captures come from
   `claude logs <background-session-id>`, which replays the rendered terminal stream. I could not
   press keys, so the *appearance* of a permission prompt is observed but the *behaviour of the
   options* is not.
2. **No interactive prompt was answered.** Every interactive capture ended on an unanswered prompt.
   The behaviour of "Yes, and don't ask again" (rule persistence to
   `.claude/settings.local.json`) is therefore **OBSERVED-DOC**, not observed on this host.
3. **Auto mode was not exercised end-to-end.** The shipped rule set was read from the CLI, but no
   action was routed through the classifier on this host — the classifier appears to require
   Anthropic-hosted inference, which this host's gateway does not provide.
4. **The sandbox could not be exercised.** Native Windows runs unsandboxed; WSL2 was not available.
   All sandbox findings are OBSERVED-DOC.
5. **Subscription-gated surfaces are unverified.** Remote Control, cloud sessions, the server-side
   classifier, and Anthropic-plan-specific defaults are documented but not observable here.
6. **The model on this host is not an Anthropic model.** `claude -p` emits
   `[claude-code:unrecognized_model] {"model":"minimax/minimax-m3.1-flash:free","query_source":"sdk"}`
   to stderr. Behaviour that depends on Anthropic-model behaviour (e.g. the "read-before-edit"
   relaxation for newer models) is **INFERRED**.
7. **The permission *prompt UI* was captured for the PowerShell tool and a parse-failure case**,
   not for a successful Bash approval — the exact Bash-prompt wording comes from the docs.
8. **Version drift.** The docs describe behaviour across many releases (v2.1.172 → v2.1.302). The
   host runs **2.1.306**, so most documented behaviour should be current, but several doc statements
   are explicitly version-gated and were not individually re-verified.

---

## Unresolved questions

1. What exactly does the Bash permission prompt look like for a **successful** approval (option
   wording, the "Yes, and don't ask again for: `npm test *`" line, and the "Yes, and switch to auto
   mode" line)? Only the docs describe it; the observed prompt was a PowerShell parse failure.
2. Is the `reason_type` vocabulary closed? Observed: `subcommandResults`. The sibling capture
   records `rule` and `mode` as well. Is there a canonical list?
3. What is the exact schema of the `PermissionRequest` hook event, and of the `--permission-prompt-tool`
   MCP tool's input/output? Only referenced, never shown, in the docs I fetched.
4. What is the full behaviour of `sandbox.autoAllowBashIfSandboxed`? The sandboxing doc says it
   "still defaults to `true`" in one place; the settings reference gives the default as `false`.
5. How does the classifier decide between `soft_deny` and `hard_deny`? The shipped rules mention
   "HARD evaluates first and ignores exceptions", but the escalation rule is not documented.
6. What is the exact byte-level format of the failure head-and-tail excerpt (the markers between
   head and tail)? The docs say "a head-and-tail excerpt of that size"; the separator is not shown.
7. Does the `BASH_MAX_OUTPUT_LENGTH` ceiling (150,000) apply to the *inline* ceiling as well, or
   only to the read-back window? The docs say it "doesn't raise the inline ceilings" but do not give
   the inline hard ceiling.
8. What is the exact behaviour of `Ctrl+B` backgrounding on Windows terminals without VT input?
   The `Shift+Tab` entry notes an `Alt+M` fallback for the Node/Bun runtime; `Ctrl+B` has no
   documented Windows fallback.
9. Is the `Monitor` tool's 5-minute default deadline affected by `run_in_background`? The docs
   describe Monitor's own deadline but do not cross-reference the background command time limits.

---

## Clean-room implementation opportunity — Area 5, end to end

Build a shell-execution subsystem with the same **user-visible function**, written independently:

**Layer 1 — Command intake.**
A `shell` tool with a fixed schema `{command, description, timeout_ms, background}` where
`description` is display-only and never consulted by policy. Parse with a real tokenizer
(POSIX-shell tokeniser for Bash; PowerShell AST for Windows), never a regex.

**Layer 2 — Rule evaluation.**
Three passes — deny, ask, allow — first match wins, specificity ignored. Implement the documented
wildcard semantics exactly (bare `*`; trailing ` *` also matches the bare command; the space before
a trailing `*` is significant; `:*` as an alternative spelling). Compound commands split on
`&& || ; | |& &` and newline; each subcommand is evaluated independently; a trailing operator
makes the command unparseable and therefore prompt-worthy. Strip a fixed wrapper list before
matching. Rules are stored in settings files with a managed tier that no flag can override.

**Layer 3 — Non-waivable guards, evaluated before rules and hooks.**
(a) protected-path writes, routed by mode; (b) a destructive-target circuit breaker for `rm`/`rmdir`
against critical paths (root, top-level dirs, home dir incl. Windows 8.3, drive roots, cwd and its
parents, variable-expansion cases), unapprovable by any allow rule or hook.

**Layer 4 — Prompting.**
An interactive panel: tool title, agent description, exact command, reason gutter, numbered options,
binding hints. Support a per-answer comment delivered to the model (post-hoc on approval, as the
denial reason on refusal). Persist a Bash approval as a per-subcommand rule in the project's
local settings file; keep file-edit approvals session-scoped. In headless mode, offer exactly two
prompt policies — *a human answers* and *nobody answers* — and in the latter case deny and tell the
model not to retry.

**Layer 5 — Execution.**
One process per command, with a persistent cwd (main session only) and a non-persistent
environment. Enforce a timeout that **promotes to background** rather than killing (except `sleep`),
with a hard output cap and a per-session memory cap. Run inside an OS-level sandbox covering child
processes; on failure, allow exactly one explicitly-flagged unsandboxed retry that gets its own
approval step, and make the retry disableable ("strict mode").

**Layer 6 — Reporting.**
Return `{stdout, stderr, exit_code, interrupted, duration_ms}` — always structured, never
pre-rendered. On failure also emit an interleaved transcript. On overflow, write the full output to
a per-session file, return the path plus a bounded preview inside explicit `<persisted-output>` tags,
and **return the path on failure too**. Emit a permission-decision record on every call
(`decision`, `source`, `reason_type`, `non_execution_kind`) and aggregate denials in the final
result envelope with the full tool input retained.

**Layer 7 — Background jobs and watches.**
Two distinct primitives: a background *job* (returns a task id and an output file path, emits
`task_started`/`task_updated`/`task_notification` events on the same stream, re-invokes the model
on completion with a summary containing the exit code, and has a time limit in unattended sessions),
and a background *watch* (streams output lines into the conversation with a deadline and a
cancellation handle).

**Layer 8 — Optional semantic layer.**
Above the deterministic rules, an optional transcript-reading reviewer that sees user messages and
tool calls but **not tool results**, returns stable reason codes (`[Code That Leaks When Run]`),
and whose policy corpus is editable JSON. On entering that mode, drop broad allow rules; restore
them on exit.

*Nothing in this design copies an Anthropic implementation.* The observable behaviours — the wire
shapes, the exact strings, the numeric limits, the rule semantics — are the specification. The
engineering is yours.
