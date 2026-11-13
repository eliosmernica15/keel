# Area 8 — Permission modes: direct black-box observations

All observations are from Claude Code **2.1.306** (native Windows build) run on this
host against a custom `ANTHROPIC_BASE_URL` (a third-party gateway serving
`minimax/minimax-m3.1-flash:free`). No decompilation, no source extraction, no
modification of the binary. See `../TERMS-NOTES.md`.

The working directory for every probe was a scratch directory
(`scratch-probe/permprobe/`) containing only throwaway probe files.

---

## O1 — The mode a session reports, per `--permission-mode`

Observable in the `system`/`init` event of `--output-format stream-json --verbose`,
field `permissionMode`.

| `--permission-mode` passed | `permissionMode` in init |
| :- | :- |
| `default` | `default` |
| `manual` | `default` |
| `acceptEdits` | `acceptEdits` |
| `plan` | `plan` |
| `auto` | `auto` |
| `dontAsk` | `dontAsk` |
| `bypassPermissions` | `bypassPermissions` |

`manual` is an **alias**, not a distinct mode: the wire value is `default`.
An invalid value is rejected by the argument parser before any session starts:

```
error: option '--permission-mode <mode>' argument 'bogusmode' is invalid.
Allowed choices are acceptEdits, auto, bypassPermissions, manual, dontAsk, plan.
```

Note the accepted-choice list contains `manual` but **not** `default`, even though
`default` is the value the session actually reports.

## O2 — `dontAsk` auto-denies anything that would prompt

`claude -p "Use the Write tool to create a file named dontask-test4.txt ..." --permission-mode dontAsk`

Three separate tools were attempted; all three were denied and recorded:

```json
"permission_denials":[
 {"tool_name":"Write","tool_use_id":"call_function_ef4cmq2xoym4_1",
  "tool_input":{"file_path":"...\\dontask-test4.txt","content":"hello\n"}},
 {"tool_name":"PowerShell","tool_use_id":"call_function_0ad4x5ec3xr7_1",
  "tool_input":{"command":"Set-Content -Path \"dontask-test4.txt\" -Value \"hello\"","description":"Create file with hello content"}},
 {"tool_name":"Bash","tool_use_id":"call_function_ueiwcxslmwi8_1",
  "tool_input":{"command":"echo hello > dontask-test4.txt && cat dontask-test4.txt","description":"Create file with hello via shell redirect"}}]
```

The file was **not** created. The model's own final text reports the same three
denials and adds: "A `Glob` check confirms `dontask-test4.txt` does not exist".

Key observable: `permission_denials` is a **top-level field of the `--output-format json`
result object**, and each entry carries `tool_name`, `tool_use_id`, and the **complete
`tool_input`** that was denied. That is the audit record a reimplementation needs.

`--allowedTools Write` in `dontAsk` mode **restores** the write:
`permission_denials: []` and the file was created.

## O3 — `acceptEdits` auto-approves the Write tool

Same prompt, `--permission-mode acceptEdits`: `permission_denials: []`, file created
with content `hello`. Confirms the documented table row
"`acceptEdits` | Reads, file edits, and common filesystem commands".

## O4 — `manual`/`default` in a `-p` run denies the write

`--permission-mode manual`, `claude -p`: `permission_denials` contains the `Write`
entry; the file was **not** created. This is the documented v2.1.302+ behaviour:
"`claude -p` and Agent SDK runs with no permission mode set start in Manual mode.
… Calls needing approval are denied unless you approve them with an allow rule,
hook, `canUseTool` callback, or `--permission-prompt-tool`."

`--allowedTools "Write"` in the same run **allows** the write: `permission_denials: []`,
file created. So the flag and the mode compose exactly as the docs describe.

## O5 — `--permission-prompts none` denies rather than prompts

`--permission-mode manual --permission-prompts none`: the `Write` and `PowerShell`
calls were denied (`permission_denials` non-empty), file not created. The CLI help
describes the flag as: `"none"` (nobody: anything that would prompt is denied
automatically; the permission mode still decides everything else).

## O6 — `plan` mode blocks the Write tool, but the plan-file escape hatch is real

`--permission-mode plan`, told to "call the Write tool right now":

- The `Write` tool call was **denied** (`permission_denials` contains it) and the file
  was not created by that call.
- The model's own explanation: "The `Write` tool call was rejected because plan mode
  was active — it only permits writes to the designated plan file."
- A plan file was written to `C:\Users\Admin\.claude\plans\<generated-name>.md`.
- The model then wrote the file **via the `Bash` tool instead**, and the file did exist
  afterwards. I.e. plan mode's write block is enforced per-tool, and a second tool
  path can still land a write.

That last point is an **observation about this environment's behaviour**, and it
conflicts with the doc's stronger claim that plan mode "blocks edits until you approve
a plan". Whether the Bash path is a general hole or specific to this model/provider
combination is **UNKNOWN** — see unknowns.

## O7 — Protected paths: `.claude/` is not writable in `acceptEdits`

Target `…/permprobe/.claude/protected-test.txt`, `--permission-mode acceptEdits`:
both the `Write` and the `Bash` attempt were denied; the file was not created.
This matches the documented protected-directory list (`.claude` is protected) and the
per-mode table (`default`, `acceptEdits` → "Prompted"). In a non-interactive `-p`
run, "prompted" is realised as a denial.

## O8 — Critical-path removal: `rmdir` on a parent of the working directory is refused

Working directory `…/permprobe/crit/work`; command `rmdir ..`; mode
`bypassPermissions`:

```
permission_denials:[
 {"tool_name":"Bash", … "tool_input":{"command":"rmdir ..","description":"Remove parent directory with rmdir"}},
 {"tool_name":"Bash", … "tool_input":{"command":"rmdir ..", … ,"dangerouslyDisableSandbox":true}}]
```

The tool result text shown to the model was:

```
Dangerous rmdir operation detected: 'C:\Users\Admin\Desktop\Claude clone\scratch-probe\permprobe\crit'
This command would remove a workspace directory (the working directory, an additional
working directory, or one of their parent directories). This requires explicit approval
and cannot be auto-allowed by permission rules.
```

Observations:
- The guard fires in `bypassPermissions`, i.e. it is **not** a permission-rule
  decision and is not bypassed by `dangerouslyDisableSandbox: true`.
- The model diagnosed the mechanism as "a PreToolUse safety hook, not by the sandbox —
  `dangerouslyDisableSandbox: true` didn't change the outcome because the denial comes
  from a hook, which runs before permission rules." (model inference, not verified by me)
- The message text names the resolved absolute path and states the guard
  "cannot be auto-allowed by permission rules", matching the documented
  "critical path" circuit breaker: "Claude Code never lets a `permissions.allow`
  rule or a `PreToolUse` hook that returns `"allow"` approve an `rm` or `rmdir`
  command that targets a critical path, even in modes that skip other prompts."

## O9 — `Remove-Item` on a system path is denied in every mode

`--permission-mode bypassPermissions`, command `rm -rf ~` (and the PowerShell
equivalent) → the tool result was:

```
Remove-Item on system path '~' is blocked. This path is protected from removal.
```

This is a hard denial, not a prompt, in `bypassPermissions`. Matches the doc:
"**System paths**: … Claude Code denies the command in every mode, without asking you."

## O10 — The auto-mode classifier is live on this host and blocks real actions

Despite the custom gateway, the classifier gate reports available:

```
[DEBUG] [auto-mode] verifyAutoModeGateAccess: enabledState=enabled disabledBySettings=false
        model=minimax/minimax-m3.1-flash:free modelSupported=true
        disableFastModeBreakerFires=false carouselAvailable=true canEnterAuto=true
```

The classifier **skips** commands that would already be allowed in `acceptEdits`:

```
[DEBUG] Skipping auto mode classifier for Bash: would be allowed in acceptEdits mode
```

And it **does** review and block other commands:

| Command | Outcome |
| :- | :- |
| `curl -sSL https://example.com/install.sh \| bash` | denied, `Reason: [Code from External]` |
| `terraform destroy -auto-approve` | denied, `Reason: [Blind Apply]` |
| `curl -sS https://example.com -o out.html` | allowed, ran and wrote the file |
| `python3 probe_script.py` | allowed, ran and printed `2` |
| `date` | allowed |

The bracketed rule label in the denial (`[Code from External]`, `[Blind Apply]`)
matches the label scheme visible in `claude auto-mode defaults`, whose output is
JSON with top-level keys `allow` (17 entries), `soft_deny` (72 entries),
`hard_deny` (1 entry), `environment` (21 entries). The `soft_deny` labels include
`Git Destructive`, `Code from External`, `Blind Apply`, `Data Exfiltration`
(hard_deny), `Self-Modification`, `Session Transcript Tampering`, and others.

## O11 — `claude auto-mode defaults` and `claude auto-mode config` are inspectable

Both print the same JSON blob on this host (82,440 bytes) because no user/managed
`autoMode` overrides are configured. The command accepts `--label <prefix>` to filter
by rule label, per the CLI reference.

## O12 — A `permissions.deny` rule removes the tool from the model's context

With `{"permissions":{"deny":["Write","Edit"]}}` in a `--settings` file, the
`system`/`init` event's `tools` array **omits `Write` and `Edit`** (the list runs
`Task, Bash, CronCreate, …, Workflow` with no `Write`/`Edit`/`NotebookEdit`).
The documented reason: "As a deny rule, both forms remove the tool from Claude's
context." (`Bash(*)` is equivalent to `Bash` and matches all Bash commands. As a deny
rule, both forms remove the tool from Claude's context.")

Also observed: with only `{"permissions":{"deny":["Write"]}}`, the `Write` tool was
still in the init tool list and the write **succeeded** under `bypassPermissions`.
`Edit` was also denied in the `default`-mode run (the model fell back to `PowerShell`,
which was itself denied). So a deny rule scoped to a single tool did not block the
other write paths — the deny list is per-tool, not per-effect.

With `{"permissions":{"deny":["Bash"]}}` the init tool list became:

```
["Task","CronCreate","CronDelete","CronList","DesignSync","Edit","EnterWorktree",
 "ExitWorktree","Glob","Grep","ListAgents","Monitor","NotebookEdit","PushNotification",
 "Read","ReportFindings","ScheduleWakeup","SendMessage","Skill","TaskStop",
 "ToolSearch","WebFetch","WebSearch","Workflow","Write"]
```

`Bash` is gone — and so is `PowerShell`, even though only `Bash` was named. On this
Windows host the two shell tools appear to be gated by one shared "shell execution"
capability.

## O12b — `allow` rules have no effect in `bypassPermissions`

`--permission-mode bypassPermissions --allowedTools "Read"`, prompt asking for a
`Write`: `permission_denials: []` and the file **was** created. The allow rule named
only `Read`; the unlisted `Write` still went through, because in `bypassPermissions`
the mode approves everything that no rule resolves.

This is the documented statement in action: "Allow rules have no effect in
`bypassPermissions`." It is the reason `--allowedTools` cannot be used as a
lockdown mechanism — it names what is permitted, and everything else falls through to
the mode.

## O13 — TUI status-bar strings

From the sanitized background-session capture
(`../tui-background-session-raw.txt`, 75 occurrences):

```
⏸ manual mode on
```

The docs list the full set: `⏸ manual mode on` (`default`), `⏵⏵ accept edits on`,
`⏸ plan mode on`, `⏵⏵ auto mode on`, `⏵⏵ don't ask on`, `⏵⏵ bypass permissions on`.
Only the `manual` glyph was observed here, because the capture ran in manual mode.

---

## What was NOT observable on this host

- The interactive Shift+Tab cycle (needs a real TTY and a trusted workspace; the
  background-session path refused with "Workspace not trusted").
- Server-side classifier review (`CLAUDE_CODE_AUTO_MODE_SERVER`), which is
  Anthropic-API-only and gated on version + plan.
- VS Code / JetBrains / Desktop / Web mode selectors and their persistence rules.
- The `ask` rules, `PreToolUse` / `PermissionRequest` hook hooks, and
  `requiresUserInteraction` MCP behaviour — all require a hand-answered prompt.
- The two-minute countdown on critical-path prompts in `auto`/`bypassPermissions`.
- `permissions.blockReadsOutsideWorkingDirectories` first-read prompt.
