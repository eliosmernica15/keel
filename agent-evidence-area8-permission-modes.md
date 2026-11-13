# Claude Code — Area 8: Permission Modes (evidence file)

**Product:** Claude Code 2.1.306 (native Windows build)
**Primary source page:** https://code.claude.com/docs/en/permission-modes.md
**Supplementary sources:** https://code.claude.com/docs/en/permissions.md,
https://code.claude.com/docs/en/settings-reference.md,
https://code.claude.com/docs/en/cli-reference.md,
https://code.claude.com/docs/en/env-vars.md,
https://code.claude.com/docs/en/agent-sdk/permissions.md
**Date:** 2026-10-21
**Scope of this file:** investigation area 8 — permission modes, destructive-action
safeguards, and user confirmations. Companion raw captures live in
`C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\area8-permission-modes\`.

---

## 1. Executive summary (one page)

Claude Code's permission system is a **layered baseline-plus-rules design**, and the
permission mode is the baseline. A session runs in exactly one of six modes
(`default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`), chosen at
launch by a flag or a settings key and changeable mid-session with `Shift+Tab`. On top
of the mode sit user/org-authored rules (`permissions.allow`, `permissions.ask`,
`permissions.deny`) and two guard rails that no rule can switch off: **protected
paths** (config and VCS directories and files) and **critical paths** (filesystem
roots, home directory, working directory and its parents).

Three ideas are the load-bearing ones for a reimplementation:

1. **The mode is a policy function, not a boolean.** Each mode answers the same
   question — "may this tool call run without a human?" — with a different answer per
   tool class. `dontAsk` is the interesting case: it is not "more permissive than
   manual", it is *fail-closed*. Anything that would prompt is **denied**, so the
   session never blocks waiting for input. That is what makes it usable in CI.

2. **Two layers cannot be talked out of.** `bypassPermissions` does not mean "skip
   everything". A documented residue still prompts or denies: tools matched by an
   explicit `ask` rule, `AskUserQuestion` and MCP tools marked
   `requiresUserInteraction`, removals targeting critical paths, and the
   cross-session messaging safeguards. The doc's own phrasing is "the actions no mode
   auto-approves".

3. **A safety net made of a second model.** `auto` mode replaces the human in the
   approval loop with a *classifier* — a separate model call that reviews the pending
   action against ~73 named rules (17 `allow`, 72 `soft_deny`, 1 `hard_deny`) before
   execution. Its denials are reported with a bracketed rule label
   (`[Code from External]`, `[Blind Apply]`, `[Data Exfiltration]`). This is the most
   distinctive and most copyable-without-copying feature in the whole permission
   design: it is a **policy engine whose policy is a versioned, inspectable JSON
   rule set** (`claude auto-mode defaults`).

I verified all of this against the running product. The `auto`-mode classifier is
**live on this host** despite the custom gateway — it blocked `curl … | bash` with
`[Code from External]` and `terraform destroy -auto-approve` with `[Blind Apply]`,
while allowing `curl -o file`, `python3 script.py`, and `date`. Every other mode was
verified by direct effect: `acceptEdits` wrote the file, `manual`/`default` denied it,
`dontAsk` denied all three write tools attempted, `plan` denied the `Write` tool,
`bypassPermissions` allowed it, and a `rmdir` on a parent of the working directory
was refused even in `bypassPermissions`.

**What this page is not:** it is not a source of internal behaviour. Everything below
is either a verbatim quote from Anthropic's published documentation, or a black-box
observation of the published CLI's externally visible behaviour.

---

## 2. Method and compliance boundary

This investigation established the boundary **before** any inspection, and it is
recorded in `C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\TERMS-NOTES.md`.

**Not performed (prohibited):** decompiling, disassembling, de-obfuscating or
extracting the bundled JavaScript; dumping source maps; modifying the binary;
reading credential stores, keychains, licence files, or account data; recovering
private APIs from the model gateway.

**Performed (permitted):** reading the published documentation; running the published
CLI's own help surfaces (`claude --help`, `claude auto-mode defaults`,
`claude auto-mode config`, `claude doctor`); running the published CLI as a user
would and recording what it prints and what it does to files; capturing its own
`--debug-file` log and its own `--output-format json` / `stream-json` output.

**Classification used throughout:**

| Label | Meaning |
| :- | :- |
| `OBSERVED-DOC` | Stated in a cited Anthropic doc; the doc sentence is quoted. |
| `OBSERVED-HERE` | Directly seen in an authorised interaction with the published CLI on this host; the observed artefact is named. |
| `INFERRED` | A conclusion of mine, with the reasoning shown. |
| `UNKNOWN` | The available evidence cannot establish it. |

Note on this host: it runs Claude Code 2.1.306 against a **custom
`ANTHROPIC_BASE_URL`**, not `api.anthropic.com`. Subscription-gated and
Anthropic-API-only features are therefore marked `OBSERVED-DOC`, not `OBSERVED-HERE`,
even where I could coax partial behaviour out of the CLI.

---

## 3. Detailed findings

### 3.1 The mode set and its exact identifiers

`OBSERVED-DOC` — "Available modes" section of
https://code.claude.com/docs/en/permission-modes.md:

> The mode that reviews every action is named **Manual** in the CLI, in `claude --help`,
> in the VS Code and JetBrains extensions, and in the desktop app. Its config value is
> `default`, which is what hooks and SDK integrations use. The CLI accepts `manual` as
> an alias wherever you type the value, for example `claude --permission-mode manual`
> or `"defaultMode": "manual"`.

The per-mode table from the same section:

| Mode | What runs without asking | Best for |
| :- | :- | :- |
| `default` | Reads only | Reviewing every action yourself, sensitive work |
| `acceptEdits` | Reads, file edits, and common filesystem commands (`mkdir`, `touch`, `mv`, `cp`, etc.) | Iterating on code you're reviewing |
| `plan` | Reads, plus classifier-approved commands when auto mode is available | Exploring a codebase before changing it |
| `auto` | Everything, with background safety checks | Long tasks, reducing prompt fatigue |
| `dontAsk` | File reads inside your working directories and pre-approved tools; anything that would prompt is denied | Locked-down CI and scripts |
| `bypassPermissions` | Everything | Isolated containers and VMs only |

`OBSERVED-HERE` — the CLI's own parser (from `claude --help` and an invalid-value
probe):

```
--permission-mode <mode>   Permission mode to use for the session
                           (choices: "acceptEdits", "auto", "bypassPermissions",
                           "manual", "dontAsk", "plan")
```

```
error: option '--permission-mode <mode>' argument 'bogusmode' is invalid.
Allowed choices are acceptEdits, auto, bypassPermissions, manual, dontAsk, plan.
```

`OBSERVED-HERE` — the value actually reported by the running session, from the
`system`/`init` event of `--output-format stream-json --verbose`, field
`permissionMode`:

| flag value | `permissionMode` reported |
| :- | :- |
| `default` | `default` |
| `manual` | `default` |
| `acceptEdits` | `acceptEdits` |
| `plan` | `plan` |
| `auto` | `auto` |
| `dontAsk` | `dontAsk` |
| `bypassPermissions` | `bypassPermissions` |

`INFERRED` — `manual` is a pure alias, not a seventh mode: the wire value for `manual`
is `default`, and `default` is the value that appears in the CLI's *choices* list
under the name `manual`. A reimplementation should accept both spellings on input and
emit exactly one canonical value. Reasoning: the observed mapping is identity for
`default`→`default` and `manual`→`default`, and the doc says the config value "is
what hooks and SDK integrations use", so `default` is the canonical wire form.

### 3.2 Where the starting mode comes from

`OBSERVED-DOC` — "Which mode a session starts in":

> When you start a new session in a terminal, Claude Code takes the permission mode
> from the first of these which applies:
> 1. The `--permission-mode` flag, or `--dangerously-skip-permissions`
> 2. `permissions.defaultMode` in a settings file
> 3. The built-in default

Same section, on the project-level trap:

> If you set `"auto"` in `.claude/settings.json` or `.claude/settings.local.json`, the
> value doesn't take effect, and Claude Code then uses the built-in default rather than
> a `defaultMode` from `~/.claude/settings.json`. If you set `"bypassPermissions"` in
> those two files, it doesn't take effect either, and the session starts in Manual
> mode. The other values apply from any settings file.

And the built-in default table:

| How you run Claude Code | Built-in starting permission mode |
| :- | :- |
| Any settings file sets `disableAutoMode` to `"disable"` | `default` |
| `claude -p` or the Agent SDK | `default` |
| Your organization has the HIPAA configuration applied … | `default` with Claude Code v2.1.285 or later; auto mode stays available to switch to |
| In a terminal or through the VS Code extension | `auto` with Claude Code v2.1.283 or later; on earlier versions, `auto` on Pro, Max, or Team plans …, and `default` otherwise |

`OBSERVED-DOC` — "Tool calls denied in `claude -p` and Agent SDK runs":

> In Claude Code v2.1.302 or later, `claude -p` and Agent SDK runs with no permission
> mode set start in Manual mode. This mode appears as `default` in SDK options and
> settings. Calls needing approval are denied unless you approve them with an allow
> rule, hook, `canUseTool` callback, or `--permission-prompt-tool`.

`OBSERVED-HERE` — the `-p` denial path works exactly as described. With
`--permission-mode manual` and no allow rule, the `Write` call appeared in the result
object's `permission_denials` array and the file was not created; with
`--allowedTools "Write"` added, `permission_denials` was `[]` and the file was
created.

`OBSERVED-HERE` — the settings-key object shape is exactly as documented, and the
`permissions.*` namespace is a single object. From
https://code.claude.com/docs/en/settings-reference.md:

> * **Type**: object with `allow`, `ask`, `deny`, `additionalDirectories`,
>   `blockReadsOutsideWorkingDirectories`, `defaultMode`, `disableBypassPermissionsMode`,
>   and `disableAutoMode`

### 3.3 Switching modes during a session

`OBSERVED-DOC` — "Switch permission modes" (CLI):

> **During a session**: press `Shift+Tab` to cycle permission modes. From `auto`, the
> first press switches to `default`, and the cycle then runs `default` → `acceptEdits`
> → `plan`. Optional modes slot in after `plan`. The status bar shows the active mode
> as a gray `⏸ manual mode on` for `default`, or as `⏵⏵ accept edits on`,
> `⏸ plan mode on`, `⏵⏵ auto mode on`, `⏵⏵ don't ask on`, or
> `⏵⏵ bypass permissions on`.

> Not every mode is in the default cycle:
> * `auto`: appears when auto mode is available; cycling to it switches permission modes without a confirmation prompt
> * `bypassPermissions`: appears after you start with `--permission-mode bypassPermissions`, `--dangerously-skip-permissions`, `--allow-dangerously-skip-permissions`, or `permissions.defaultMode: "bypassPermissions"` in user, `--settings`, or managed settings. The `--allow-` variant adds the permission mode to the cycle without activating it
> * `dontAsk`: never appears in the cycle; set it with `--permission-mode dontAsk`

> Enabled optional modes slot in after `plan`, with `bypassPermissions` first and
> `auto` last. If you have both enabled, you will cycle through `bypassPermissions`
> on the way to `auto`.

`OBSERVED-HERE` — one of those status strings was captured live. From the sanitized
background-session capture (`agent-reference-shots/tui-background-session-raw.txt`,
75 occurrences): `⏸ manual mode on`. The other five glyphs are `OBSERVED-DOC` only.

`OBSERVED-DOC` — the "yes and escalate" option on a Bash prompt:

> **From a Bash permission prompt**: in the Manual and `acceptEdits` permission modes,
> when auto mode is available, Claude Code adds **Yes, and switch to auto mode** to a
> Bash command's permission prompt. Select it to approve the command and switch the
> session to auto mode. [PowerShell tool](…) prompts don't offer the option.

> Claude Code doesn't add the option to prompts forced by one of your `ask` rules or by
> a hook, because auto mode still shows you those prompts, so switching wouldn't remove
> them.

### 3.4 `acceptEdits` — the enumerated auto-approve set

`OBSERVED-DOC` — "Auto-approve file edits with acceptEdits mode":

> `acceptEdits` mode lets Claude create and edit files in your working directory
> without prompting. The status bar shows `⏵⏵ accept edits on` while this mode is active.
>
> In addition to file edits, `acceptEdits` mode auto-approves common filesystem Bash
> commands: `mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, and `sed`. These commands are
> also auto-approved when prefixed with safe environment variables such as `LANG=C` or
> `NO_COLOR=1`, or process wrappers such as `timeout`, `nice`, or `nohup`. Like file
> edits, auto-approval applies only to paths inside your working directory or
> `additionalDirectories`.
>
> Each path also goes through the [symlink check](…), so a write that resolves outside
> that scope isn't auto-approved either.

`OBSERVED-DOC` — the PowerShell mirror:

> When the [PowerShell tool](…) is enabled, `acceptEdits` mode also auto-approves
> `Set-Content`, `Add-Content`, `Clear-Content`, and `Remove-Item` on in-scope paths,
> along with their common aliases. … A positional argument that contains a quote
> character, such as the apostrophe in `Set-Content .\notes.txt "It's done"`, still
> prompts even on in-scope paths, because Claude Code can't statically validate an
> argument whose quoted and unquoted readings differ. Pass the content through a named
> parameter such as `-Value` to avoid the prompt.

`INFERRED` — `acceptEdits` is best modelled as a **per-tool-class allow set with a
path-scope predicate**, not as "edits are allowed". The doc gives the exact set
(7 Bash commands, 4 PowerShell cmdlets), the exact scope predicate (working directory
or `additionalDirectories`), and an exact escape hatch (the symlink check). A
reimplementation should encode it as: `tool ∈ {Edit, Write} ∪ {Bash(mkdir|touch|rm|rmdir|mv|cp|sed)} ∪ {PowerShell(Set-Content|Add-Content|Clear-Content|Remove-Item)}` **and** `resolve(path) ∈ scope`.

`OBSERVED-HERE` — `acceptEdits` wrote the file (`permission_denials: []`,
file created with content `hello`), and a write to `…/permprobe/.claude/protected-test.txt`
under the same mode was **denied** for both the `Write` and the `Bash` attempt. That
confirms the protected-path carve-out is enforced above the mode's allow set.

### 3.5 `dontAsk` — the fail-closed mode

`OBSERVED-DOC` — "Allow only pre-approved tools with dontAsk mode":

> If you set `dontAsk` mode, Claude Code auto-denies every tool call that would
> otherwise prompt you, though a mod you installed can still approve some of those
> calls.
>
> Claude still runs actions that need no approval in Manual mode, such as file reads
> inside your working directories and read-only Bash commands. Actions matching your
> `permissions.allow` rules and calls approved by a `PreToolUse` hook run too. Use this
> mode for CI pipelines or restricted environments where you pre-define what Claude may
> do; the session never waits for input. The status bar shows `⏵⏵ don't ask on` in this mode.
>
> Claude Code denies calls matching your explicit `ask` rules rather than prompting. It
> also denies the built-in `AskUserQuestion` tool even if your allow rules match it …
> It denies MCP tools marked `_meta["anthropic/requiresUserInteraction"]` the same way,
> because their approval card needs an answer this mode never collects.
>
> `rm` and `rmdir` removals targeting a critical path, such as `rm -rf /` and `rm -rf ~`,
> are denied even when an allow rule matches them or a `PreToolUse` hook allows them.
> A read from a network path is denied the same way.

`OBSERVED-HERE` — three separate write tools were attempted in one `dontAsk` run and
all three were denied, with the full inputs recorded:

```json
"permission_denials":[
 {"tool_name":"Write","tool_use_id":"call_function_ef4cmq2xoym4_1",
  "tool_input":{"file_path":"…\\dontask-test4.txt","content":"hello\n"}},
 {"tool_name":"PowerShell","tool_use_id":"call_function_0ad4x5ec3xr7_1",
  "tool_input":{"command":"Set-Content -Path \"dontask-test4.txt\" -Value \"hello\"",…}},
 {"tool_name":"Bash","tool_use_id":"call_function_ueiwcxslmwi8_1",
  "tool_input":{"command":"echo hello > dontask-test4.txt && cat dontask-test4.txt",…}}]
```

The file was not created. `--allowedTools Write` restored the write in a separate
`dontAsk` run (`permission_denials: []`, file created).

`INFERRED` — `dontAsk` is best implemented as a **prompt resolver with one extra
terminal state**. Every other mode's resolver returns `{approve | prompt}`; `dontAsk`
returns `{approve | deny}` and *never* `prompt`. The one exception the docs carve out
(a `mod` handling `tool.check` can approve some calls) is a natural fit for a hook-like
extension point that runs *before* the mode resolver. A reimplementation should keep
the resolver's return type as a three-valued enum with `dontAsk` simply never
producing the third value.

### 3.6 `plan` — research without mutation, and the approval step

`OBSERVED-DOC` — "Analyze before you edit with plan mode":

> Plan mode tells Claude to research and propose changes without making them. Claude
> reads files, runs shell commands to explore, and writes a plan, but does not edit
> your source. Except in interactive terminal sessions with bypass permissions
> available, edits stay blocked until you approve the plan.

> What happens to a shell command during planning depends on the session, and the first
> of these cases that matches applies:
> * **Interactive terminal sessions with bypass permissions available**: neither the classifier nor a prompt applies to planning commands.
> * **Auto mode available and the `useAutoModeDuringPlan` setting on**, which it is by default: the classifier reviews shell commands other than critical-path removals instead of prompting you. Approved commands run, and rejected ones are blocked.
> * **Auto mode not available, or `useAutoModeDuringPlan` off**: commands outside the built-in read-only set prompt for approval …

`OBSERVED-DOC` — "Review and approve a plan":

> * **Yes, and use auto mode**: approve and start in auto mode. If auto mode isn't available to your session …, this option reads **Yes, auto-accept edits**. If you started the session with bypass permissions enabled, the option reads **Yes, and switch to BYPASS PERMISSIONS (no further prompts) for this session** instead.
> * **Yes, manually approve edits**: approve and review each edit individually.
> * **No, keep planning**: stay in plan mode and tell Claude what to change.

> Press `Ctrl+G` to open the proposed plan in your default text editor and edit it
> directly before Claude proceeds. When `showClearContextOnPlanAccept` is enabled, the
> list gains a first option that approves the plan and clears the planning context.

`OBSERVED-DOC` — the `/plan` entry and exit:

> Enter plan mode by pressing `Shift+Tab` or prefixing a single prompt with `/plan`. …
> Press `Shift+Tab` again to leave plan mode without approving a plan.

`OBSERVED-HERE` — in `plan` mode a forced `Write` call was denied and the file was not
created by it. The model's own explanation: "The `Write` tool call was rejected because
plan mode was active — it only permits writes to the designated plan file." A plan file
was written under `~/.claude/plans/`.

`UNKNOWN` — **whether plan mode's write block is sound.** In my probe the model, after
being denied the `Write` tool, wrote the same file via the `Bash` tool and the file
existed afterwards. I could not establish whether this is (a) a general hole in plan
mode's enforcement on this build, (b) a behaviour specific to this model/provider
combination (the session ran on a third-party gateway with a non-Anthropic model), or
(c) an artefact of how the model chose to respond. The doc's claim that edits "stay
blocked" is stated for the `Write`/`Edit` path; I did not find a doc statement that
covers a Bash-based write during planning. **Do not treat plan mode as a hard
sandbox on the strength of this document alone.**

### 3.7 `auto` — the classifier in the loop

`OBSERVED-DOC` — "Eliminate permission prompts with auto mode":

> Auto mode lets Claude execute without routine permission prompts. A separate
> classifier model reviews actions before they run, blocking anything that escalates
> beyond your request, targets unrecognized infrastructure, or appears driven by
> hostile content Claude read. Explicit `ask` rules still force a prompt.

Availability, verbatim:

> Auto mode is available only when your account meets all of these requirements:
> * **Plan**: All plans.
> * **Organization**: on Team and Enterprise, auto mode is available by default. Administrators can turn it off for the organization by setting `permissions.disableAutoMode` to `"disable"` in managed settings.
> * **Model**: on the Anthropic API and Claude Platform on AWS, Claude Opus 4.6 or later, Sonnet 4.6 or later, Haiku 5.5, or a Fable model. On Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, and signed-in Claude apps gateway sessions, only Claude Sonnet 5 or later, Opus 4.7 or later, Haiku 5.5, and the Fable models.
> * **Provider**: available by default on the Anthropic API, Claude Platform on AWS, Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, and signed-in Claude apps gateway sessions.

The classifier model selection:

> By default, classifier requests go to Claude Sonnet 5. If `/status` shows `Auto mode server` as `Enabled`, they're sent only for calls outside the server's review.
>
> | Your session | Classifier model |
> | - | - |
> | Has an Anthropic-configured classifier model | The configured model. |
> | Runs on Claude Sonnet 4.6 | Sonnet 4.6 |
> | Has `ANTHROPIC_DEFAULT_SONNET_MODEL` set | Its value, or Sonnet 5 if its value is Claude Sonnet 5.5 or Claude Opus 5.5 |

`OBSERVED-DOC` — override knob:

> With Claude Code v2.1.302 or later, set `CLAUDE_CODE_AUTO_MODE_MODEL` to a full model
> ID to run the classifier on a model other than the default. …

The decision order — the single most valuable block on this page for a
reimplementation, because it is a complete, ordered policy:

> 1. Actions matching your allow, ask, or deny rules resolve immediately, with these exceptions: …
> 2. Read-only actions and file edits in your working directory are auto-approved, except writes to protected paths and the first read outside the working directories, which prompts you
> 3. Everything else goes to the classifier, apart from critical-path removals under their default handling. The connector tools and `requiresUserInteraction` MCP tools that prompt you directly in step 1 never reach the classifier either
> 4. If the classifier blocks, Claude receives the reason. In most sessions the reason names the rule the classifier matched, such as `[Data Exfiltration]`, rather than giving a written explanation

`OBSERVED-DOC` — the mode's own rule-dropping behaviour:

> On entering auto mode, broad allow rules that grant arbitrary code execution are dropped:
> * Blanket `Bash(*)` or `PowerShell(*)`
> * Wildcarded interpreters like `Bash(python*)`
> * Package-manager run commands
> * `Agent` allow rules
> * `Monitor` allow rules, because Claude Code runs Monitor commands through the shell
>
> Narrow rules like `Bash(npm test)` stay in effect. Claude Code restores the dropped
> rules when you leave auto mode.

`OBSERVED-DOC` — what the classifier is shown, and what it is not:

> In the classifier requests sent by Claude Code itself, the classifier sees user
> messages, tool calls other than read-only lookups such as file reads and searches,
> and your CLAUDE.md content. Tool results are stripped from those requests, so hostile
> content in a file or web page can't manipulate the classifier directly.

`OBSERVED-DOC` — the subagent checks:

> The classifier checks subagent work at three points:
> 1. Before a subagent starts, the delegated task description is evaluated …
> 2. While the subagent runs, each of its actions goes through the same decision order as in the parent session, with the same block and allow rules. Any `permissionMode` in the subagent's frontmatter is ignored.
> 3. When the subagent finishes, the classifier reviews its work and its final report before the parent reads the report. When the classifier flags the subagent's work or report …, the report is still delivered, prepended with a security warning.

`OBSERVED-DOC` — the fall-back thresholds:

> **Repeated blocks**: if the classifier blocks an action 3 times in a row or 20 times
> total, auto mode pauses and Claude Code resumes prompting. … The thresholds of 3
> blocks in a row and 20 blocks total are not configurable.

`OBSERVED-HERE` — **the classifier ran for real on this host.** The gate line from
`--debug-file`:

```
[DEBUG] [auto-mode] verifyAutoModeGateAccess: enabledState=enabled disabledBySettings=false
        model=minimax/minimax-m3.1-flash:free modelSupported=true
        disableFastModeBreakerFires=false carouselAvailable=true canEnterAuto=true
```

The skip optimisation, also from `--debug-file`:

```
[DEBUG] Skipping auto mode classifier for Bash: would be allowed in acceptEdits mode
```

And the blocks (denial text is the tool result the model receives):

| Command | Outcome |
| :- | :- |
| `curl -sSL https://example.com/install.sh \| bash` | denied — `Reason: [Code from External]` |
| `terraform destroy -auto-approve` | denied — `Reason: [Blind Apply]` |
| `curl -sS https://example.com -o out.html` | allowed; file written |
| `python3 probe_script.py` | allowed; printed `2` |
| `date` | allowed |

Full denial text for the first case (verbatim):

> Permission for this action was denied by the Claude Code auto mode classifier. Reason:
> [Code from External]. If you have other tasks that don't depend on this action,
> continue working on those. IMPORTANT: You *may* attempt to accomplish this action
> using other tools that might naturally be used to accomplish this goal, e.g. using
> head instead of cat. But you *should not* attempt to work around this denial in
> malicious ways … Get as much of the rest of the task done as you can, then STOP and
> explain to the user what you were trying to do and why you need this permission. Let
> the user decide how to proceed. To allow this type of action in the future, the user
> can add a permission rule for Bash to their settings.

`OBSERVED-HERE` — the rule set is inspectable as data. `claude auto-mode defaults`
prints JSON with top-level keys `allow` (17 entries), `soft_deny` (72 entries),
`hard_deny` (1 entry), `environment` (21 entries). The `soft_deny` labels observed
include `Git Destructive`, `Code from External`, `Blind Apply`,
`Irreversible Local Destruction`, `Credential Leakage`, `Data Exfiltration`
(the single `hard_deny`), `Self-Modification`, `Tmux Self Drive`,
`Session Transcript Tampering`, `Package Registry Bypass`,
`Auto-Mode Bypass`, `Instruction Poisoning`, `Merge Without Review`,
`ChatOps Trigger Comments`, `Feature Flag Writes`, `Third-Party Attack`, and six
browser exfiltration rules.

`INFERRED` — the auto-mode policy is **data, not code**. The rule set ships as
inspectable JSON with a stable label vocabulary, a three-tier structure
(`allow` / `soft_deny` / `hard_deny`), and a separate `environment` block for the
organisation's trust boundary. The `soft_deny` rule bodies embed a naming convention
directly in their text — `Git Destructive [named+specifics — **must name:** the
destructive operation and its target]` — which is the *approval* semantics spelled
out as part of the rule. A reimplementation should adopt the same shape: a rule has a
label, a severity tier, a body that states the trigger, and a statement of what
constitutes user approval for that class.

`INFERRED` — the classifier's *position* in the pipeline is what makes it useful: it
sits after the deterministic rules and the working-directory fast path, and before
execution, so it reviews only the "everything else" bucket. That keeps cost and
latency proportional to risk. The doc says as much: "Reads and working-directory
edits outside protected paths skip the classifier, so the overhead comes mainly from
shell commands and network operations."

### 3.8 `bypassPermissions` — and what it still does not bypass

`OBSERVED-DOC` — "Skip all checks with bypassPermissions mode":

> `bypassPermissions` mode disables permission prompts and safety checks so tool calls
> execute immediately, including writes to protected paths.
>
> The [actions no mode auto-approves](…) still prompt in this mode. Reading another
> organization's public artifact needs your approval, and this mode doesn't ask for
> it, so Claude can't read one. The [Remove-Item in PowerShell](…) denies also apply in
> this mode.

The residue list ("Actions no mode auto-approves"), verbatim:

> Claude Code doesn't auto-approve the following in any mode, including
> `bypassPermissions`.
> * Tools matched by an explicit `ask` rule
> * Connector tools your organization set to `ask`, in sessions where that setting reaches Claude Code
> * Tools that require user interaction: the built-in `AskUserQuestion` tool and MCP tools marked `requiresUserInteraction`
> * `rm` and `rmdir` removals targeting a critical path, which no allow rule or `PreToolUse` hook `"allow"` approves
> * The cross-session messaging safeguards
> * Reads outside the working directories while `permissions.blockReadsOutsideWorkingDirectories` is on …

`OBSERVED-DOC` — the entry gate:

> You can't enter `bypassPermissions` from a session you started without it enabled.
> Enable it at launch with `permissions.defaultMode: "bypassPermissions"` or with an
> enabling flag …
> The `--dangerously-skip-permissions` flag is equivalent.
>
> Claude Code refuses `bypassPermissions` in a session you start with `--restricted`. …

> The first time you start an interactive session with this mode enabled, Claude Code
> shows a warning dialog asking you to accept responsibility for actions taken without
> permission checks:
> * **If you accept**: Claude Code sets `skipDangerousModePermissionPrompt` to `true` in `~/.claude/settings.json`, so later sessions skip the dialog.
> * **If you decline**: Claude Code exits.

`OBSERVED-DOC` — the root guard:

> On Linux and macOS, Claude Code refuses to start in `bypassPermissions` mode when
> running as root or under `sudo`:
> ```text
> --dangerously-skip-permissions cannot be used with root/sudo privileges for security reasons
> ```

`OBSERVED-DOC` — the `bypassPermissions` variant that only adds to the cycle:

> `--allow-dangerously-skip-permissions` | Add `bypassPermissions` to the `Shift+Tab`
> mode cycle without starting in it. Lets you begin in a different mode like `plan` and
> switch to `bypassPermissions` later.

`OBSERVED-HERE` — `bypassPermissions` behaved as documented: with
`--permission-mode bypassPermissions`, a `Write` to a plain path in the working
directory **succeeded**. But the `Remove-Item` system-path deny still fired:

```
Remove-Item on system path '~' is blocked. This path is protected from removal.
```

### 3.9 Protected paths

`OBSERVED-DOC` — "Protected paths":

> Writes to a small set of paths are never auto-approved, except in `bypassPermissions`
> mode and in interactive terminal sessions in plan mode with bypass permissions
> available. This prevents accidental corruption of repository state and Claude's own
> configuration.

| Mode | Protected-path writes |
| :- | :- |
| `default`, `acceptEdits` | Prompted |
| `plan` | Allowed in interactive terminal sessions with bypass permissions available. Otherwise, routed to the classifier when auto mode is available during planning, and prompted when it isn't |
| `auto` | Routed to the classifier |
| `dontAsk` | Denied |
| `bypassPermissions` | Allowed |

`OBSERVED-DOC` — the rules cannot pre-approve them:

> `permissions.allow` rules in settings files do not pre-approve protected-path writes.
> The safety check runs before Claude Code evaluates allow rules from settings, so an
> entry such as `Edit(.claude/**)` in `~/.claude/settings.json` or `.claude/settings.json`
> does not change the per-mode outcome in the table above.

Protected directories (exact list): `.git`, `.config/git`, `.vscode`, `.idea`,
`.husky`, `.cargo`, `.devcontainer`, `.yarn`, `.mvn`, `.claude` (with exceptions:
`.claude/worktrees/`, `~/.claude/plans/`, `~/.claude/jobs/<id>/tmp/`, auto-memory and
subagent-memory markdown).

Protected files (exact list): `.gitconfig`, `.gitmodules`, `.bashrc`,
`.bash_profile`, `.bash_login`, `.bash_aliases`, `.bash_logout`, `.zshrc`, `.zprofile`,
`.zshenv`, `.zlogin`, `.zlogout`, `.profile`, `.envrc`, `.npmrc`, `.yarnrc`,
`.yarnrc.yml`, `.pnp.cjs`, `.pnp.loader.mjs`, `.pnpmfile.cjs`, `bunfig.toml`,
`.bunfig.toml`, `.bazelrc`, `.bazelversion`, `.bazeliskrc`,
`.pre-commit-config.yaml`, `lefthook.yml`, `lefthook.yaml`, `.lefthook.yml`,
`.lefthook.yaml`, `gradle-wrapper.properties`, `maven-wrapper.properties`,
`.devcontainer.json`, `.ripgreprc`, `pyrightconfig.json`, `.mcp.json`, `.claude.json`.

`OBSERVED-HERE` — a write to `…/permprobe/.claude/protected-test.txt` under
`acceptEdits` was denied for both the `Write` and the `Bash` attempt, and the file was
not created. This matches the `default`/`acceptEdits` row ("Prompted", realised as a
denial in a non-interactive run).

### 3.10 Critical paths

`OBSERVED-DOC` — "Critical paths":

> Critical paths are the directories Claude Code protects from `rm` and `rmdir`
> commands, such as the filesystem root, your home directory, and your working directory.
>
> Claude Code never lets a `permissions.allow` rule or a `PreToolUse` hook that returns
> `"allow"` approve an `rm` or `rmdir` command that targets a critical path, even in
> modes that skip other prompts. This circuit breaker guards against model error.

The exact critical-path set:

> * The filesystem root
> * Top-level directories, meaning any direct child of the root, such as `/usr`, `/etc`, or `/data`
> * Your home directory. On Windows, its 8.3 short name counts too, such as `C:\Users\LONGNA~1`
> * Windows drive roots and their top-level directories, such as `C:\` and `C:\Windows`. Spellings such as `\\?\C:\` and `\\localhost\C$` count as `C:\`
> * Your working directory and its parents
> * Your additional working directories and their parents, but only when the removal is a glob under one of them, such as `rm -rf <dir>/*`

Plus the "other targets" table (glob under a shell variable, positional parameter,
`$TMPDIR/mnt`, `$(pwd)`-assigned variable, command-substitution-only target,
trailing substitution after a critical path, a target that is only backslashes, a
volume-by-GUID path, and some targets ending in `/*` or `/*/`).

`OBSERVED-DOC` — per-mode outcome:

| Mode | Outcome |
| :- | :- |
| `default`, `acceptEdits` | Asks you to approve it |
| `plan` | Asks you to approve it. When the classifier reviews commands during planning and no bypass permissions are available, handles it as in `auto` mode |
| `auto` | Asks you to approve it in the terminal, with a time limit. Elsewhere, denies it |
| `dontAsk` | Denies it |
| `bypassPermissions` | Asks you to approve it, with a time limit in the terminal |

`OBSERVED-DOC` — the countdown:

> In `auto` and `bypassPermissions` modes, the terminal prompt for a critical-path
> removal shows a two-minute countdown:
> * If the countdown runs out before you answer, Claude Code denies the command …
> * Press any key while the prompt is open to stop the countdown …
> * After three of these prompts run out unanswered in a session, Claude Code stops showing them and denies further critical-path removals immediately. Sending a new message starts the count over.

`OBSERVED-HERE` — the guard fired in `bypassPermissions` on a parent of the working
directory, with the exact message shape:

```
Dangerous rmdir operation detected: 'C:\Users\Admin\Desktop\Claude clone\scratch-probe\permprobe\crit'
This command would remove a workspace directory (the working directory, an additional
working directory, or one of their parent directories). This requires explicit approval
and cannot be auto-allowed by permission rules.
```

Both the plain `rmdir ..` call and the `rmdir ..` call carrying
`dangerouslyDisableSandbox: true` were denied. The message states the property the
docs promise — "cannot be auto-allowed by permission rules".

### 3.11 The PowerShell `Remove-Item` deny

`OBSERVED-DOC` — "Remove-Item in PowerShell":

> For `Remove-Item`, the outcome depends on the target, and the first matching case applies:
> * **System paths**: the filesystem root and its top-level directories, drive roots and their top-level directories, and your home directory. Claude Code denies the command in every mode, without asking you.
> * **Wildcards**: a bare `*`, or any target ending in `/*` or `\*`, including a glob under a shell variable such as `$dir/*`. Claude Code denies the command in every mode, without asking you, before the classifier sees it.
> * **Your working directory or one of its parents, with `-Recurse`**: Claude Code treats the command like any other that needs approval in your permission mode … `bypassPermissions` mode skips this check.

`OBSERVED-HERE` — confirmed in `bypassPermissions`: `Remove-Item on system path '~' is
blocked. This path is protected from removal.`

### 3.12 Rules, hooks, and precedence

`OBSERVED-DOC` — from the same page:

> Modes set the baseline. Layer permission rules on top to pre-approve or block
> specific tools. Deny rules block in every mode, including `bypassPermissions`. Deny
> and ask rules don't apply to `EndConversation` as long as Claude still has at least
> one other tool it can call. Allow rules have no effect in `bypassPermissions`.

`OBSERVED-DOC` — from https://code.claude.com/docs/en/permissions.md:

> Permission rules follow the format `Tool` or `Tool(specifier)`. Parentheses inside
> the specifier are literal, so a command or path that contains them needs no escaping.

> `Bash(*)` is equivalent to `Bash` and matches all Bash commands. As a deny rule, both
> forms remove the tool from Claude's context.

> Deny and ask rules can match a top-level input parameter on any built-in tool with
> `Tool(param:value)`. … You can't match a tool's primary content field this way:
> `command` for Bash and PowerShell, `file_path` for Read, Edit, and Write, `path` for
> Grep and Glob, `notebook_path` for NotebookEdit, and `url` for WebFetch. A rule like
> `Bash(command:rm *)` would be bypassable by a compound command, so Claude Code
> ignores it and emits a startup warning.

`OBSERVED-HERE` — the deny-removes-the-tool behaviour is real. With
`{"permissions":{"deny":["Write","Edit"]}}` supplied via `--settings`, the
`system`/`init` event's `tools` array omitted `Write` and `Edit` entirely. This is a
meaningful design detail: a deny rule is not a runtime check, it is a **context
pruning** — the model never sees the tool, so it cannot request it.

`OBSERVED-HERE` — with only `{"permissions":{"deny":["Write"]}}`, the `Write` tool was
still present in the tool list and the write **succeeded** under `bypassPermissions`.
So a deny rule scoped to one tool name does not block the same *effect* reached through
a different tool (`PowerShell`, `Bash`).

`OBSERVED-HERE` — a **bare** deny rule prunes the tool. With
`{"permissions":{"deny":["Bash"]}}`, the init `tools` array was:

```
["Task","CronCreate","CronDelete","CronList","DesignSync","Edit","EnterWorktree",
 "ExitWorktree","Glob","Grep","ListAgents","Monitor","NotebookEdit","PushNotification",
 "Read","ReportFindings","ScheduleWakeup","SendMessage","Skill","TaskStop",
 "ToolSearch","WebFetch","WebSearch","Workflow","Write"]
```

`Bash` is gone — and so is `PowerShell`, even though only `Bash` was named. On this
Windows host the two shell tools appear to be gated together: denying one removes the
shell-execution surface from the model's context. `INFERRED` — the tool list is likely
built from a single "shell execution" capability that both `Bash` and `PowerShell`
project from. Reasoning: the removal is broader than the named rule, and both tools
are the only shell-execution entries in the list.

`OBSERVED-HERE` — `--allowedTools` is an **allow** rule, not a restriction. Under
`--permission-mode bypassPermissions --allowedTools "Read"`, a `Write` call still
**succeeded** (`permission_denials: []`, file created). This is direct evidence for
the doc's "Allow rules have no effect in `bypassPermissions`". It also shows the
asymmetry that makes `allowedTools` unsafe as a lockdown mechanism: it names what is
*permitted*, and everything else falls through to the mode, which in `bypassPermissions`
means "permitted".

`INFERRED` — the rule engine's ordering is `deny` → `ask` → `allow`, first match
wins, and the mode is the fallback when no rule matches. The doc states deny/ask beat
allow and that deny beats every mode; the observed "deny removes the tool from
context" behaviour means deny is evaluated *before* the model is even given the tool.
For a reimplementation the important consequence is that **deny is not a filter, it is
a capability restriction**, and it should be enforced by pruning the tool list rather
than by checking at call time.

### 3.13 Environment variables that switch specific checks off

`OBSERVED-DOC` — from https://code.claude.com/docs/en/env-vars.md:

| Variable | Effect |
| :- | :- |
| `CLAUDE_CODE_AUTO_MODE_MODEL` | Sets the model for the classifier requests Claude Code sends in auto mode. |
| `CLAUDE_CODE_AUTO_MODE_SERVER` | Controls whether Claude Code asks the server to review auto mode actions. Set to `0` to use Claude Code's own classifier requests instead. |
| `CLAUDE_CODE_DISABLE_DANGEROUS_RM_TIMEOUT` | Set to `1` to turn off the time limit on critical-path removal prompts. |
| `CLAUDE_CODE_DISABLE_INLINE_SHELL_RM_PROMPT` | Set to `1` to stop Claude Code from reading scripts passed to a shell with `-c`. |
| `CLAUDE_CODE_DISABLE_MOUNTED_DRIVE_RM_PROMPT` | Set to `1` to turn off the mounted drive prompt. |
| `CLAUDE_CODE_DISABLE_POWERSHELL_CMD_RM_DENY` | Set to `1` to turn off the PowerShell tool check that denies the `cmd` built-ins. |
| `CLAUDE_CODE_DISABLE_SUBSTITUTION_RM_PROMPT` | Set to `1` to turn off the critical-path check for a recursive `rm` whose target is entirely the output of a command substitution. |

Every one of these is documented as: "Set it in the environment that launches Claude
Code, since Claude Code ignores a copy delivered through a settings `env` block."

`INFERRED` — this is a **deliberate "break-glass" design**: each safety check has a
named, per-check kill switch rather than one global "disable safety" flag. It lets an
operator relieve exactly the check that is producing false positives without
weakening the rest. A reimplementation should expose the same shape: one env var per
check, read from the process environment at launch, never from a settings file's `env`
block (which is itself a defence, because a project-supplied settings file could
otherwise ship a kill switch to a user's machine).

---

## 4. Capability table

| # | Capability | Mode(s) | Status | Evidence |
| :- | :- | :- | :- | :- |
| 1 | Six named modes with stable config values | all | OBSERVED-DOC | permission-modes.md § Available modes |
| 2 | `manual` accepted as an alias for `default` | all | OBSERVED-DOC + OBSERVED-HERE | doc § Available modes; `permissionMode` init field |
| 3 | Launch flag `--permission-mode <mode>` | all | OBSERVED-HERE | `claude --help`; init `permissionMode` |
| 4 | `permissions.defaultMode` settings key | all | OBSERVED-DOC | settings-reference.md § `permissions.defaultMode` |
| 5 | `auto`/`bypassPermissions` ignored from project/local settings | all | OBSERVED-DOC | permission-modes.md § Which mode a session starts in |
| 6 | `Shift+Tab` cycle `default → acceptEdits → plan` (+optional) | interactive | OBSERVED-DOC | § Switch permission modes |
| 7 | `dontAsk` never in the cycle | — | OBSERVED-DOC | § Switch permission modes |
| 8 | Status-bar glyphs per mode | interactive | OBSERVED-DOC (6) / OBSERVED-HERE (1: `⏸ manual mode on`) | § Switch permission modes; `tui-background-session-raw.txt` |
| 9 | `acceptEdits` auto-approves Edit/Write + 7 Bash cmds + 4 PS cmdlets | `acceptEdits` | OBSERVED-DOC; Write path OBSERVED-HERE | § Auto-approve file edits with acceptEdits mode |
| 10 | `dontAsk` denies everything that would prompt | `dontAsk` | OBSERVED-DOC + OBSERVED-HERE (3 tools denied) | § Allow only pre-approved tools with dontAsk mode; `dontask-write-denied.json` |
| 11 | `plan` blocks edits until plan approval | `plan` | OBSERVED-DOC; Write path OBSERVED-HERE | § Analyze before you edit with plan mode |
| 12 | `bypassPermissions` skips prompts and safety checks | `bypassPermissions` | OBSERVED-DOC + OBSERVED-HERE (write succeeded) | § Skip all checks with bypassPermissions mode |
| 13 | Residue that no mode auto-approves | all | OBSERVED-DOC | § Actions no mode auto-approves |
| 14 | Protected paths (dirs + files, exact lists) | all but `bypassPermissions` | OBSERVED-DOC + OBSERVED-HERE (`.claude/` denied) | § Protected paths |
| 15 | Critical paths (exact set) | all | OBSERVED-DOC + OBSERVED-HERE (parent-dir `rmdir` denied in `bypassPermissions`) | § Critical paths |
| 16 | PowerShell `Remove-Item` system-path deny, every mode | all | OBSERVED-DOC + OBSERVED-HERE | § Remove-Item in PowerShell |
| 17 | Auto-mode classifier reviews actions | `auto` | OBSERVED-DOC + OBSERVED-HERE (2 blocks, 3 allows) | § Eliminate permission prompts with auto mode; `auto-mode-debug-gate.log` |
| 18 | Classifier rule set is inspectable JSON (`allow`/`soft_deny`/`hard_deny`/`environment`) | `auto` | OBSERVED-HERE | `claude auto-mode defaults` output |
| 19 | Auto-mode decision order (4 steps, first match wins) | `auto` | OBSERVED-DOC | § How auto mode evaluates actions |
| 20 | Deny removes the tool from the model's context | all | OBSERVED-HERE (init `tools` array; bare `Bash` deny also removed `PowerShell`) | init event; permissions.md § Permission rule syntax |
| 21 | `permission_denials` audit array with full tool inputs | headless | OBSERVED-HERE | `--output-format json` result object |
| 22 | Repeated-block fall-back (3 consecutive / 20 total) | `auto` | OBSERVED-DOC | § Repeated-block thresholds |
| 23 | Two-minute countdown on critical-path prompts | `auto`, `bypassPermissions` | OBSERVED-DOC | § Time limits and denials in auto and bypassPermissions modes |
| 24 | Per-check kill-switch environment variables | all | OBSERVED-DOC | env-vars.md |
| 25 | Server-side classifier review | `auto` | OBSERVED-DOC only (Anthropic-API-only) | § Server-side classifier review |
| 26 | Mod `tool.check` can approve in `dontAsk` | `dontAsk` | OBSERVED-DOC only | § Actions no mode auto-approves; § Allow only pre-approved tools with dontAsk mode |
| 27 | `allow` rules have no effect in `bypassPermissions` | `bypassPermissions` | OBSERVED-DOC + OBSERVED-HERE | § Available modes; `--allowedTools "Read"` still allowed a `Write` |
| 28 | A bare deny rule on one shell tool removes both shell tools from context | all | OBSERVED-HERE | init `tools` array with `{"permissions":{"deny":["Bash"]}}` |

---

## 5. Dependencies

**Hard dependencies of the feature itself**

| Dependency | Required for | Notes |
| :- | :- | :- |
| A model provider reachable over the Messages API | every mode | The mode resolver itself is local; the *classifier* and the model under supervision are not. |
| A second, distinct model for the classifier | `auto` | `auto` is unavailable otherwise; the CLI reports `canEnterAuto=false` / `modelSupported=false`. |
| Anthropic API endpoint (not a generic gateway) for server-side review | `auto` (optional variant) | `CLAUDE_CODE_AUTO_MODE_SERVER=0` forces the local-classifier path. |
| A filesystem to protect | protected paths, critical paths | Both are path predicates over the real FS. |
| A shell / shell parser | Bash and PowerShell rules | Rules match against *parsed* commands, not raw strings (compound splitting, wrapper stripping). |
| Process environment at launch | the kill-switch variables | Settings-file `env` blocks are explicitly ignored for these. |

**Dependencies of the *product*, not of a reimplementation** — Anthropic account,
plan tier, managed-settings policy, and organisation-level controls
(`permissions.disableAutoMode`, `permissions.disableBypassPermissionsMode`) all gate
what a user can reach. A third-party build with none of these can implement the same
*observable contract* locally.

**What a reimplementation can drop entirely:** the account/plan/provider gating, the
feature-flag fetch, the managed-settings policy hierarchy, and the server-side review
variant. None of those are needed to reproduce the user-visible behaviour.

---

## 6. Limitations of this investigation

1. **Non-Anthropic gateway.** This host runs a custom `ANTHROPIC_BASE_URL`. The
   classifier gate still reports `canEnterAuto=true` and the classifier demonstrably
   blocks, but the classifier is a *local* request path here, not the server-side
   review variant. Anything about server-side review (`CLAUDE_CODE_AUTO_MODE_SERVER`)
   is `OBSERVED-DOC` only.
2. **Headless bias.** Most probes were `-p` runs, where a "prompt" is realised as a
   denial because nobody is there to answer. Interactive prompt *layout*, the
   `Shift+Tab` cycle, and the two-minute countdown were therefore not observed
   directly; the one interactive artefact available was a background-session log.
3. **The workspace was not trusted**, so `--bg` sessions were refused
   ("Workspace not trusted. Run `claude` in … once and accept the trust prompt"),
   which limited interactive capture.
4. **Model behaviour differs.** The supervising model was
   `minimax/minimax-m3.1-flash:free`, not Claude. Its willingness to attempt a `Write`
   in plan mode and then route around it via `Bash` may not reflect Claude's
   behaviour; plan-mode enforcement may be sound with a different model.
5. **No decompilation was performed**, by design. Therefore every statement about
   *internal* structure — the classifier's prompt, the exact matching algorithm behind
   `Bash(npm test)`, the shape of the mode resolver — is inference from observable
   behaviour, not verification.
6. **Only one rule syntax was exercised at runtime** (`permissions.deny` on `Write`/
   `Edit`, and `--allowedTools`). Wildcard matching, wrapper stripping, compound
   splitting, and symlink resolution are `OBSERVED-DOC` only.

---

## 7. Unresolved questions

1. Is plan mode's write block sound in general, or was the Bash-route-around an
   artefact of this model? **UNKNOWN.**
2. Does `bypassPermissions` really consult `permissions.allow` at all? **RESOLVED —
   it does not.** The doc says "Allow rules have no effect in `bypassPermissions`", and
   I confirmed it: `--permission-mode bypassPermissions --allowedTools "Read"` still
   allowed an unlisted `Write` to succeed. The remaining open question is narrower:
   whether `permissions.allow` in a settings file behaves the same as `--allowedTools`
   in this respect (`UNKNOWable` here because the doc treats them as one concept and
   the observable already answers the substance).
3. What is the exact behaviour of the `ask` rule and `AskUserQuestion` in `bypassPermissions`
   — prompt or deny? The page says these "still prompt in this mode" but a headless run
   has no one to prompt, and the observed residue list and the "actions no mode
   auto-approves" wording pull in different directions. **UNKNOWN.**
4. Does the two-minute critical-path countdown actually deny on expiry, and does the
   "three unanswered" rule reset on a new message as documented? **UNKNOWN.**
5. What exactly does `permissions.blockReadsOutsideWorkingDirectories` do to the
   *first* read prompt in each mode, and does the "Yes, and keep allowing" answer
   persist where? **UNKNOWN.**
6. Is the `EndConversation` carve-out ("Deny and ask rules don't apply to
   `EndConversation` as long as Claude still has at least one other tool it can call")
   enforced by a live capability check? **UNKNOWN.**
7. How is the `defaultMode` precedence between *multiple* settings files computed for
   the starting mode specifically (as opposed to the general settings precedence)?
   **UNKNOWN.**
8. What are the classifier's exact stop conditions and its rule-matching semantics
   beyond the observable label? The rule bodies are visible as text via
   `claude auto-mode defaults`, but the matching procedure is not. **UNKNOWN.**
9. Does the VS Code `claudeCode.initialPermissionMode` setting accept `auto`?
   The doc says it does not. **UNKNOWN** (not observable here).
10. Are the mode-specific Windows behaviours (8.3 short names, `\\?\C:\`,
    `\\localhost\C$`, volume GUIDs) present in this build? The doc says they need
    v2.1.292+; this build is 2.1.306, so they should be, but I did not construct a
    test that would distinguish them. **UNKNOWN** (untested, not untestable).

---

## 8. Clean-room implementation opportunity

**Observable contract to reproduce.** A permission system with:
(a) a session-scoped mode that is one of six values, chosen by flag or settings key,
changeable at runtime, and rendered as a fixed status-bar string; (b) a rule layer of
`allow`/`ask`/`deny` with a `Tool(specifier)` syntax that is evaluated
deny → ask → allow with first-match-wins and with deny removing the tool from the
model's context entirely; (c) two non-overridable guard rails (protected paths,
critical paths) that sit *above* the rule layer; (d) a fail-closed mode that converts
every prompt into a denial; (e) a classifier-in-the-loop mode backed by an inspectable
JSON rule set; (f) a machine-readable denial record carrying the full attempted tool
input.

**How to build it idiomatically, without any Anthropic code.**

- **Mode as an enum + a mode table, not scattered conditionals.** Define
  `enum Mode { Default, AcceptEdits, Plan, Auto, DontAsk, BypassPermissions }` with
  `Manual` as an *input alias* for `Default`, canonicalised at the CLI/SDK boundary.
  Then define one table, `mode -> (autoApprovedToolClasses, promptPolicy, denyPolicy)`.
  The whole feature becomes data, which is both easier to test and easier to extend
  with new modes.

- **One resolver, three outcomes.** The idiomatic shape is
  `resolve(call, ctx) -> Approve | Prompt | Deny(reason)`, evaluated in a fixed order:
  1. deny rules (and the deny-tool-from-context effect),
  2. ask rules,
  3. protected-path check (never auto-approve),
  4. critical-path check (never allow),
  5. mode's auto-approve set (scope + symlink-resolved path predicate),
  6. classifier (auto mode) / prompt (manual) / deny (dontAsk).
  `DontAsk` is then literally "the resolver never returns `Prompt`". That single
  invariant gives you the whole fail-closed property for free, and it makes the
  headless case correct by construction rather than by special-casing.

- **Command matching: parse, then match.** Do not match raw command strings. Split
  compound commands on the shell's operators, strip safe env prefixes and process
  wrappers, canonicalise PowerShell aliases, and match each fragment independently.
  This is the standard approach for shell-policy engines and it is what the observed
  behaviour implies: `touch` prompted in `default` mode while `echo one` did not,
  because the read-only set is a fixed enumeration, not a heuristic.

- **Guard rails as path predicates over resolved paths.** Implement protected and
  critical paths as two predicates over `resolve(path)`:
  `isProtected(p)` = prefix match against the protected dir/file list, after symlink
  resolution; `isCritical(p)` = exact/prefix match against {root, root children,
  home, working dir, working dir parents}. The "never allow, always prompt-or-deny"
  property then falls out of the evaluation order rather than being special-cased in
  each mode. This is the part of the design most worth copying: it is what makes
  `bypassPermissions` safe to ship.

- **Classifier as a policy engine over inspectable JSON.** Ship the rule set as data
  in the same shape Anthropic uses — `allow`, `soft_deny`, `hard_deny`,
  `environment` — with a stable label vocabulary, and expose a CLI command that
  prints it. Then the "policy" is versionable, reviewable, diffable, and testable
  without a model. The review step itself is then just: build a small request
  containing the pending action plus the user message and the project's instruction
  file (not tool results), call a model, and map the reply to a rule label. If the
  model cannot decide, **deny** — the doc's "no verdict → deny" behaviour is the safe
  default and is trivially implemented.

- **Denials as a first-class audit record.** Emit a structured denial object with
  `tool_name`, a call id, and the complete attempted input. Anthropic's
  `permission_denials` array is exactly this and it is the right design: it is what
  makes a headless run auditable, and it is what a UI needs to render "you declined
  X".

- **Per-check kill switches.** Give each guard rail its own environment variable
  (`AGENT_DISABLE_<CHECK>`), read from the launch environment only — never from a
  project-supplied settings file — so that a checked-in config cannot disable a
  user's safety. That is a small detail with a large consequence, and it costs
  nothing to implement.

- **Scope recommendation.** Implement, in priority order: the mode enum and resolver;
  the rule syntax and evaluation order; protected and critical paths; `dontAsk` and
  `acceptEdits`; the plan-mode block; `bypassPermissions` with its residue list; the
  deny-prunes-tool-from-context behaviour; the machine-readable denial record; and
  finally the classifier mode with an inspectable JSON rule set. The classifier is
  the largest and most model-dependent piece, and it is the least necessary for a
  functional reimplementation — the rest of the system is what makes a tool-using
  agent safe to hand to a user.

---

## 9. Evidence index

| Artefact | Path |
| :- | :- |
| Primary page (fetched plain markdown) | `C:\Users\Admin\Desktop\Claude clone\scratch-probe\permission-modes.md` |
| Permissions page | `C:\Users\Admin\Desktop\Claude clone\scratch-probe\permissions.md` |
| Settings reference | `C:\Users\Admin\Desktop\Claude clone\scratch-probe\settings-reference.md` |
| CLI reference | `C:\Users\Admin\Desktop\Claude clone\scratch-probe\cli_reference.md` |
| Env vars page | `C:\Users\Admin\Desktop\Claude clone\scratch-probe\env-vars.md` |
| Agent SDK permissions page | `C:\Users\Admin\Desktop\Claude clone\scratch-probe\agent-sdk-perms.md` |
| Area 8 observations | `C:\Users\Admin\Desktop\Claude clone\agent-reference-shots\area8-permission-modes\observed-behaviours.md` |
| `dontAsk` denial record | `…\area8-permission-modes\dontask-write-denied.json` |
| Auto-mode gate debug log | `…\area8-permission-modes\auto-mode-debug-gate.log` |
| Auto-mode classifier-skip log | `…\area8-permission-modes\auto-mode-debug-acceptEdits-skip.log` |
| Classifier block `[Blind Apply]` | `…\area8-permission-modes\auto-mode-classifier-blocked-blindapply.json` |
| Classifier block `[Code from External]` | `…\area8-permission-modes\auto-mode-classifier-blocked-codefromexternal.txt` |
| Example deny settings | `…\area8-permission-modes\deny-settings-example.json` |
| Prior TUI capture (mode status bar) | `…\agent-reference-shots\tui-background-session-raw.txt` |
| Prior TUI permission prompt capture | `…\agent-reference-shots\area5-bash-permissions\tui-permission-prompt.txt` |
| Compliance boundary | `…\agent-reference-shots\TERMS-NOTES.md` |
| Black-box protocol notes | `…\agent-reference-shots\PROTOCOL-NOTES.md` |

**Documentation URLs cited**

- https://code.claude.com/docs/en/permission-modes.md (primary)
- https://code.claude.com/docs/en/permissions.md
- https://code.claude.com/docs/en/settings-reference.md
- https://code.claude.com/docs/en/cli-reference.md
- https://code.claude.com/docs/en/env-vars.md
- https://code.claude.com/docs/en/agent-sdk/permissions.md
- https://code.claude.com/docs/en/legal-and-compliance (terms boundary)
