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
| Example bare-`Bash` deny settings | `…\area8-permission-modes\deny-bash-settings-example.json` |
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

---

# Area 14 - Built-in slash commands and the command menu

**Assigned page:** `https://code.claude.com/docs/en/commands.md`
**Full detail (standalone):** `agent-evidence-area-commands.md`
**Artifacts:** `agent-reference-shots/area-commands/*.sanitized.jsonl`

# Claude Code — Area: Built-in Slash Commands and the Command Menu

**Assigned page:** `https://code.claude.com/docs/en/commands.md`
**Product:** Claude Code 2.1.306 (`native`, win32-x64) — the published CLI, observed on this host.
**Date:** 2026-10-21
**Classification key:** `OBSERVED-DOC` (stated in the cited Anthropic doc) · `OBSERVED-CLI` (directly observed in an authorized product interaction on this host) · `INFERRED` (conclusion with reasoning) · `UNKNOWN` (evidence cannot establish it).

**Compliance note.** No decompilation, disassembly, source extraction, source-map dumping, binary modification, or credential/licence/keychain access was performed. Evidence comes from (a) the public Markdown served at `code.claude.com/docs/en/*.md`, and (b) the published CLI's own help and headless (`-p`) surfaces, which are documented, intended-for-use entry points. Fetched web text was treated strictly as untrusted data; no directive found in any fetched page was executed or followed.

**Host caveat.** This host runs Claude Code against a custom `ANTHROPIC_BASE_URL`, not `api.anthropic.com`. Subscription-gated surfaces (claude.ai auth, Remote Control, cloud sessions, artifacts, `/desktop`, `/teleport`, `/schedule`, `/upgrade`, `/usage-credits`, `/privacy-settings`, `/passes`, `/remote-control`, `/mobile`) were therefore **not observable** and are marked `OBSERVED-DOC` only. `claude doctor` on this host states: *"Remote Control is only available when using Claude via api.anthropic.com. ANTHROPIC_BASE_URL is set and does not point at api.anthropic.com"* and *"Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL"*.

---

## 1. Executive summary

`commands.md` is a **command reference**, not a behavioral spec: a single table of ~110 rows, each row a command name (with an argument grammar in backticks) and a one-paragraph "Purpose". It is the densest single-page statement of the slash-command surface, but it deliberately encodes *availability conditions* rather than *implementation*. Roughly two-thirds of the rows carry a version gate ("Requires Claude Code v2.1.NNN or later"), a platform gate, a plan gate, or a provider gate.

Five structural facts dominate, and all five are the load-bearing parts for a reimplementation:

1. **A command is a prefix of the first user message, and everything after the name is its argument string.** The doc states: *"A command is only recognized at the start of your message. Text that follows the command name becomes its arguments."* There is no separate command channel — a slash command *is* a message.
2. **Commands are dispatched locally when they can be, and to the model when they cannot.** Verified live: `/context`, `/usage`, `/mcp`, `/config theme=dark`, `/rename mysession`, and `/model sonnet` all execute with **zero model turns and zero API time**, and the headless `result` event carries a machine-readable `"local_command"` field naming the handler (`"context"`, `"usage"`, `"mcp"`, `"config"`, `"rename"`, `"model"`). An unmatched name (`/zzzznotacommand`) instead **is sent to the model** as ordinary text, and the model answers in prose: *"`/zzzznotacommand` isn't a command available in this session, so nothing ran"*. This three-way split (local handler / model-delivered prompt / unavailable-in-this-environment) is the single most important thing to copy.
3. **The set of available commands is machine-readable at session start.** The `system`/`init` event of `--output-format stream-json --verbose` carries `slash_commands` (the union of skills and built-in commands), `terminal_slash_commands` (`["doctor","color","focus","reload-plugins"]` — handlers that render locally with no model call), `skills`, and `agents`. `--disable-slash-commands` empties `slash_commands` **and** `skills` and drops `terminal_slash_commands` from the event entirely — a clean, verifiable kill switch.
4. **The `/` menu is a fuzzy matcher with explicit alias semantics, not a prefix filter.** The doc specifies that highlighting matches *"a command's name or alias, from the start of the name or from a word within it, ignoring the `:`, `_`, and `-` separators"* — so `/adddir` highlights `/add-dir` and `/new` highlights `/clear` through its alias. A typo highlights nothing and yields `Unknown command: /hepl. Did you mean /help?`.
5. **Built-in commands and bundled skills are one namespace with two execution models.** The doc marks rows `**[Skill]**` (a prompt handed to Claude) and `**[Workflow]**` (a bundled dynamic workflow fanning out across subagents). Everything else is *"coded into the CLI"*. A reimplementation that treats skills as a special case of commands — same dispatcher, same menu, same alias rules — matches the reference's structure.

**Recommendation.** Implement the dispatcher and the menu first (Tier 1), because every other command surface — permissions, MCP, skills, subagents, session management — is reachable *through* it. The `local_command` field in the headless result event is the highest-leverage single decision: it makes the local/model split observable to any embedder and testable without a model.

---

## 2. Findings

### F1 — Command syntax: prefix-of-message, arguments are the remainder

**OBSERVED-DOC** (`https://code.claude.com/docs/en/commands.md`, intro paragraphs):

> "A command is only recognized at the start of your message. Text that follows the command name becomes its arguments. At the terminal prompt, you can start one message with several skills: typing `/skill-a /skill-b do XYZ` loads both skills and passes the trailing text to each as arguments. Up to six skills can be chained."

> "If you send a command while Claude is responding, Claude Code queues it and runs it after the current turn finishes. Claude Code runs some commands immediately without interrupting the response, such as `/status`, `/tasks`, and `/usage`. In fullscreen rendering, Claude Code also opens dialog commands such as `/theme` and `/help` immediately. Before v2.1.234, Claude Code queued those dialogs until the turn finished."

Argument grammar in the table is written as `<arg>` (required) and `[arg]` (optional): *"In the table below, `<arg>` indicates a required argument and `[arg]` indicates an optional one."*

**Corroboration (OBSERVED-CLI).** The `skills` doc for the stacking rule: *"Claude Code expands the first skill plus up to five more stacked after it"* — i.e. six total, matching the `commands.md` wording. (`https://code.claude.com/docs/en/skills.md`, §"Stack several skills in one message".)

**Reimplementation need: critical.** The grammar is: match the longest command name (or alias) at position 0; the remainder of the line is one opaque argument string. Sub-command grammars are shown inline in the command name itself, e.g.:

- `/advisor [model\|off]`
- `/code-review [low\|medium\|high\|xhigh\|max\|ultra] [--fix] [--comment] [--max-findings n\|all\|default] [pr#\|branch\|path]`
- `/mcp [reconnect (<server>\|all)\|enable\|disable [<server>\|all]]`
- `/import [codex\|gemini\|cursor] [--dry-run] [--yes]`
- `/effort [level\|auto\|status\|ultracode [on\|off]]`
- `/doctor [prompt-audit [path]]`
- `/tui [default\|fullscreen]`
- `/voice [hold\|tap\|off]`
- `/fast [on\|off]`

Note the `<arg>` / `[arg]` convention, the `|` alternation, and nested brackets — a small recursive-descent argument parser is enough; nothing here requires a shell-like grammar.

**Clean-room opportunity.** Implement a single dispatcher with a registry of `{name, aliases[], argSpec, handler, deliveryMode}`. Match at offset 0 with longest-prefix-wins over name+alias. Parse `argSpec` with a tiny recursive-descent parser that produces a positional list plus a flag map. `deliveryMode` is `local` (render locally), `model` (prepend the command's prompt and send), or `unavailable` (print the availability message). The argument grammar is fully described by the table and is trivially reimplementable; no proprietary code is required.

---

### F2 — The dispatch contract: three outcomes, and one of them is machine-readable

**OBSERVED-CLI.** Running the published CLI headlessly with `--verbose --output-format stream-json` on this host (Claude Code 2.1.306) produced these three distinct outcomes for the *same* input channel:

| Input | `local_command` in the `result` event | `num_turns` | `duration_api_ms` | Outcome |
| :- | :- | :- | :- | :- |
| `/context` | `"context"` | `0` | `0` | Handled locally; a context-usage grid was rendered |
| `/context all` | `"context"` | `0` | `0` | Handled locally; full per-item breakdown rendered |
| `/usage` | `"usage"` | `0` | `0` | Handled locally; cost/usage table rendered |
| `/mcp` | `"mcp"` | `0` | `0` | Handled locally; text summary printed (no list UI) |
| `/config theme=dark` | `"config"` | `0` | `0` | Handled locally; printed `Set Theme to dark` |
| `/rename mysession` | `"rename"` | `0` | `0` | Handled locally; printed `Session renamed to: mysession` |
| `/model sonnet` | `"model"` | `0` | `0` | Handled locally; printed ``Set model to `Sonnet 5.5` for this session only`` |
| `/zzzznotacommand` | *(absent)* | `1` | `3196` | **Sent to the model** as ordinary text |
| `/help` | *(absent)* | `0` | `0` | Printed ``/help isn't available in this environment.`` |
| `/permissions` | *(absent)* | `0` | `0` | Printed ``/permissions isn't available in this environment.`` |
| `/init` | *(absent)* | `35` | — | **Sent to the model** as a prompt (it is a skill) |

The `/mcp` output verbatim:

> `1 MCP server(s): 0 connected, 1 connecting, 0 not connected, 0 disabled. Use `/mcp` in the terminal for details.`

The `/usage` output verbatim:

> `Total cost:            $0.0000\nTotal duration (API):  0s\nTotal duration (wall): 3s\nTotal code changes:    0 lines added, 0 lines removed\nUsage:                 0 input, 0 output, 0 cache read, 0 cache write`

The `/context` output verbatim (head):

> `## Context Usage\n\n**Model:** <MODEL_ID>  \n**Tokens:** 22.9k / 200k (11%)\n\n### Estimated usage by category\n\n| Category | Tokens | Percentage |\n|----------|--------|------------|\n| System prompt | 2k | 1.0% |\n| System tools | 18.9k | 9.4% |\n| System tools (deferred) | 19.8k | 9.9% |\n| Skills | 2k | 1.0% |\n| Free space | 144.1k | 72.1% |\n| Autocompact buffer | 33k | 16.5% |`

The unmatched-command path, verbatim from the model's own reply:

> `` `/zzzznotacommand` isn't a command in this session, so nothing ran. Available slash commands include `/developing-with-streamlit`, `/reverse-engineer-anything`, `/dataviz`, `/code-review`, `/simplify`, `/run`, `/init`, `/security-review`, and others (33 more). ``

**Corroboration (OBSERVED-DOC).** `https://code.claude.com/docs/en/errors.md` §"Unknown command" states the rule for non-interactive sessions:

> "Claude Code answers an unmatched `/` name this way only in an interactive terminal session. In every other session, it sends the prompt to Claude as a normal message instead, with a note that the command didn't run and a list of commands Claude can run in the session. Those sessions include: `-p` runs, Agent SDK applications, Cloud sessions and cloud scheduled tasks."

> "For a built-in command that can't run in one of those sessions, Claude Code still answers that the command isn't available instead of sending it to Claude."

> "Claude Code doesn't treat every prompt that starts with `/` as a command. It sends the prompt to Claude as a normal message when the first word after the `/` starts with punctuation, such as the `/--` that opens a Lean doc comment, or is a path such as `/var/log/syslog`."

**INFERRED (high confidence).** The `result` event's `local_command` field is the reference's own contract for "this turn was handled by a local command handler, not by the model." Reasoning: it appears *only* on locally-handled commands, is absent on both the model-delivered path and the unavailable path, and is exactly the string of the matched command name. An embedder can therefore distinguish "the agent acted" from "the user asked the agent" without parsing prose. This is the single highest-value detail for a clean-room build because it turns an internal dispatch decision into a testable public signal.

**Reimplementation need: critical.** A reimplementation must decide, per command, whether it renders locally or is delivered to the model. The observed set that is local on this host — `context`, `usage`, `mcp`, `config`, `rename`, `model` — lines up exactly with the doc's own descriptions of commands that *print* rather than *ask*: `/usage` "Show session cost, plan usage limits, and activity stats"; `/config key=value` "Pass one or more `key=value` pairs to set a setting directly without opening the interface". Conversely `/init` (a skill) went to the model. The doc's own marker — `**[Skill]**` = "a prompt handed to Claude" vs. unmarked = "behavior is coded into the CLI" — is exactly this split, stated in prose. *(`https://code.claude.com/docs/en/commands.md`, §"All commands")*

**Clean-room opportunity.** Implement a `CommandRegistry` with an explicit `handler` per entry. If the entry has a local handler, run it and set `local_command: <name>` on the result envelope. If it has a prompt body, prepend it and dispatch to the model. If it is gated off, emit the availability message and set neither. The `key=value` form is worth special-casing: `/config theme=dark` set the theme *without* opening the UI and *without* a model call, so a settings store must be able to accept a `key=value` pair directly. The doc confirms this form works in non-interactive mode: *"The `key=value` form also works in non-interactive mode (`-p`) and from the Claude mobile app via Remote Control. The `key=value` form can't turn on a setting that needs your confirmation in the panel, such as `autoContinueAtUsageLimit`, though it can turn one off. Run `/config --help` to list the keys it accepts."*

---

### F3 — Availability is a per-command property, gated on platform / plan / provider / version

**OBSERVED-DOC.** The table is preceded by an explicit warning:

> "Not every command appears for every user. Availability depends on your platform, plan, and environment. For example, `/desktop` only shows on macOS and x64 Windows when signed in with a Claude subscription, and `/upgrade` doesn't show on Enterprise plans."

Concrete gates visible in the table:

| Gate type | Examples (exact wording) |
| :- | :- |
| Platform | "`/desktop` … Requires macOS or x64 Windows and a Claude subscription." |
| Plan | "`/privacy-settings` … Only available for Pro and Max plan subscribers." / "`/passes` … Only visible if your account is eligible." |
| Provider | "`/design` … Available on the Anthropic API. On Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, and Claude Platform on AWS, artifacts aren't available, so the command is unavailable there." |
| Version | "Requires Claude Code v2.1.269 or later" (`/output-style`); "Requires Claude Code v2.1.284 or later" (`/effort` `ultracode` on/off); "Requires Claude Code v2.1.252 or later and feature-flag fetching" (`/skill-doctor`) |
| Feature flag | "`/skill-doctor` … Requires Claude Code v2.1.252 or later and feature-flag fetching." |
| Environment variable | "`/setup-bedrock` … Hidden from the command menu until `CLAUDE_CODE_USE_BEDROCK=1` is set" |
| Organization policy | "Some commands also answer with a message of their own when your organization's policy disables them." |

**OBSERVED-CLI (partial).** `/help` and `/permissions` both returned `` isn't available in this environment.`` in the headless run on this host — a third distinct outcome, distinct from both "sent to model" and "handled locally", and distinct from the interactive-only `Unknown command: /hepl. Did you mean /help?` message.

**INFERRED.** The version gates are informational, not behavioral — they describe when a command *appeared*, so a reimplementation can ignore them. But the platform / plan / provider / policy gates are *live behavioral* and must be modeled as a per-command predicate evaluated at menu-render and dispatch time. Evidence: the doc says availability "depends on your platform, plan, and environment", and the observed headless run produced an availability *message* rather than a not-found error for gated commands, which means the gate is evaluated before dispatch and has its own message string.

**Reimplementation need: high.** Model availability as `available(cmd, ctx) -> bool | Reason`. Return a `Reason` (not just false) so the dispatcher can print the right message: not-found, needs-interactive, needs-subscription, needs-provider, disabled-by-policy.

**Clean-room opportunity.** A simple `Gate[]` per command — each gate a predicate over a context object `{platform, arch, plan, provider, orgPolicy, featureFlags, env}` — composes into one boolean. This is ordinary feature-flag machinery; the value lies in the *shape* (per-command predicate evaluated at both menu-render and dispatch), not in any proprietary logic.

---

### F4 — The command menu: fuzzy matching, aliases, hidden commands, and the no-match message

**OBSERVED-DOC** (`https://code.claude.com/docs/en/commands.md`, §"How the command menu matches what you type"). The four rules, quoted:

> "**Highlighting**: Claude Code highlights the top suggestion only when the letters after the `/` match a command's name or alias, from the start of the name or from a word within it, ignoring the `:`, `_`, and `-` separators. Typing `/adddir` highlights `/add-dir`, and typing `/new` highlights `/clear` through its alias. Press `Enter` to run the highlighted suggestion. These highlighting rules require Claude Code v2.1.236 or later."

> "**After a typo**: Claude Code highlights nothing. The close matches stay listed, and you can pick one with `Tab` or the arrow keys, but `Enter` submits your text as typed and reports Unknown command."

> "**Commands that aren't available to you**: Claude Code leaves them out of the menu. When nothing matches, Claude Code shows `No commands match "/name"`. Most unavailable commands return Unknown command when you submit them; a few, such as `/schedule` on a Console API key, answer with their own availability message instead. Some commands also answer with a message of their own when your organization's policy disables them."

> "**Hidden commands**: Claude Code keeps a few available commands, such as `/heapdump`, out of the menu by design. A partial name never brings a hidden command into the menu: if the partial matches nothing visible, Claude Code shows the same no-match message. Claude Code lists the command only once you've typed its full name, and submitting the full name runs it."

**Hidden commands named in the table** (each explicitly *"Hidden from the command menu"*): `/heapdump`, `/setup-bedrock`, `/setup-vertex`. `/setup-bedrock` is hidden *"until `CLAUDE_CODE_USE_BEDROCK=1` is set"* and `/setup-vertex` *"until `CLAUDE_CODE_USE_VERTEX=1` is set"*.

**Aliases** (exact pairs, all stated in the table): `/bg`→`/background`; `/share`→`/bug`; `/reset`,`/new`→`/clear`; `/settings`→`/config`; `/allowed-tools`→`/permissions`; `/checkup`→`/doctor`; `/cost`,`/stats`→`/usage`; `/routines`→`/schedule`; `/quit`→`/exit`; `/checkpoint`,`/undo`→`/rewind`; `/continue`→`/resume`; `/app`→`/desktop`; `/peers`→`/list-agents`; `/bashes`→`/tasks`; `/rc`→`/remote-control`; `/tp`→`/teleport`; `/proactive`→`/loop`; `/ios`,`/android`→`/mobile`; `/review`→`/code-review`; `/ultrareview`→alias of `/code-review ultra`; `/extra-usage` (former name of `/usage-credits`).

**Corroboration (OBSERVED-CLI).** The `system`/`init` event's `slash_commands` array contains `heapdump` — a command the doc says is hidden from the menu — proving hidden commands are still *dispatchable* and still enumerated in the machine-readable registry, just excluded from the menu.

**Corroboration (OBSERVED-DOC, `errors.md`).** The exact error string and its suggestion behavior:

> ```text
> Unknown command: /hepl. Did you mean /help?
> ```
> "Claude Code suggests the closest command name or alias that the menu lists in this session. When nothing is close, the message ends after the name."

And the historical note: *"Before v2.1.236, if you pressed `Enter` while the command menu listed a near match for the name you typed, Claude Code ran that match, so a typo such as `/hepl` ran `/help` instead of producing this message."*

**Reimplementation need: critical.** The matcher is the trickiest part of the whole surface. The rule decomposes as:
1. Normalize the typed fragment by removing `:`, `_`, `-`.
2. A command matches if the normalized fragment is a **prefix of the normalized name**, **or** matches a whole **word** within the name (word-bounded, so `adddir` ↔ `add-dir` matches; `dir` would match the word `dir` inside `add-dir`).
3. Aliases participate identically — `/new` highlights `/clear`.
4. Hidden commands are excluded from the *menu*, but a full-name match still executes.
5. If nothing matches, the menu shows `No commands match "/name"`.

**Clean-room opportunity.** Implement the matcher as: tokenize each command name into words on `[:_\-]`, keep the full normalized string and the word list, then score a candidate by (exact alias hit) > (prefix hit) > (word-substring hit) > (fuzzy edit distance). Rank by (score, name length, alphabetical) and take the top for highlighting. "Did you mean" is then the same scorer with an edit-distance threshold. This is a standard autocomplete problem — the reference's own rules are sufficient to reimplement it from scratch.

---

### F5 — Bundled skills and workflows share the command namespace

**OBSERVED-DOC.** The table marks two special row kinds:

> "**[Skill]**: a bundled skill. It works like skills you write yourself: a prompt handed to Claude. `/verify` runs only when you invoke it. Before v2.1.215, Claude could also run `/verify` on its own."

> "**[Workflow]**: a bundled dynamic workflow that fans work out across many subagents and runs in the background. `/deep-research` runs only when you invoke it. Before v2.1.218, Claude could also start it on its own."

> "Most are built-in commands whose behavior is coded into the CLI."

And: *"To add your own commands, see skills."*

**Corroboration (OBSERVED-CLI).** On this host the `system`/`init` event carried `slash_commands` = 53 names, of which the `skills` array was a strict 19-name subset. The `slash_commands` list includes names that are plainly *not* built-in CLI commands — `developing-with-streamlit`, `reverse-engineer-anything`, `dataviz`, `update-config`, `verify`, `debug`, `code-review`, `simplify`, `batch`, `fewer-permission-prompts`, `doctor`, `loop`, `claude-api`, `workflow-authoring`, `run`, `run-skill-generator`, `plugin-authoring`, `deep-research`, `design`, `design-sync` — i.e. skills (including two user-installed ones) are enumerated in the *same* array as built-in commands like `clear`, `compact`, `config`, `context`, `effort`, `fast`, `focus`, `init`, `mcp`, `model`, `rename`, `usage`.

**Corroboration (OBSERVED-CLI).** `--disable-slash-commands` emptied **both** `slash_commands` and `skills` to `[]` and removed `terminal_slash_commands` from the event — confirming one registry, one kill switch.

**Corroboration (OBSERVED-DOC, `skills.md`).** *"Custom commands have been merged into skills. A file at `.claude/commands/deploy.md` and a skill at `.claude/skills/deploy/SKILL.md` both create `/deploy` and work the same way. Your existing `.claude/commands/` files keep working."*

**INFERRED.** The command registry is a **single flat namespace** populated from at least four sources: built-in CLI handlers, bundled skills, user/project skills, and MCP-server prompts. The `slash_commands` array is that flat namespace. The `skills` array is a *subset view* marking which entries are skill-backed (i.e. model-delivered). This matches the doc's `**[Skill]**` / `**[Workflow]**` markers exactly.

**Corroboration (OBSERVED-DOC, `mcp.md` §"Use MCP prompts as commands").** *"MCP servers can expose prompts that become available as commands in Claude Code. … Claude Code lists each MCP prompt as `/servername:promptname (MCP)`. Typing `/mcp__servername__promptname` also runs it."* And: *"Prompts from a server named `anthropic-skills` don't appear, because Claude Code reserves that name for skills synced from claude.ai."* Argument handling: *"Many prompts accept arguments. Pass them space-separated after the command. Claude Code splits the arguments on whitespace, so each argument is a single token."*

**Reimplementation need: high.** A reimplementation needs one namespace with a source tag per entry (`builtin | bundled-skill | user-skill | project-skill | mcp-prompt | workflow`). The MCP-prompt naming rule is exact and cheap to implement: display form `/servername:promptname (MCP)`, executable form `/mcp__servername__promptname`, arguments split on whitespace only.

**Clean-room opportunity.** Treat "command" as a data type with a `source` discriminator rather than building two systems. The MCP bridging is then just: on connect, read `prompts/list`, synthesize a command entry per prompt, and support both spellings. The `anthropic-skills` reserved-name rule is a one-line filter.

---

### F6 — Mid-turn execution: some commands interrupt the turn, some queue

**OBSERVED-DOC.** From the intro:

> "If you send a command while Claude is responding, Claude Code queues it and runs it after the current turn finishes. Claude Code runs some commands immediately without interrupting the response, such as `/status`, `/tasks`, and `/usage`."

And the `/status` row:

> "Open the Settings interface on the Status tab, showing version, model, account, and connectivity. A `Session kind` row reads `background job · attached` or `background job · unattended` in a background session, depending on whether a terminal is attached, and `interactive` in any other session. … Works while Claude is responding."

Per-command notes that repeat the pattern:

- `/add-dir`: "When you run it while Claude is responding, Claude Code asks you to confirm the directory right away, and once you confirm, Claude's next tool call in the same turn can access it. Before v2.1.234, Claude Code queued the command until the turn finished"
- `/permissions`: "When you run it while Claude is responding, Claude Code opens the dialog immediately and applies your changes starting with Claude's next tool call in the same turn. Before v2.1.234, Claude Code queued the command until the turn finished."
- `/bug`: "When you run it while Claude is responding, Claude Code opens the dialog immediately. Before v2.1.232, Claude Code queued the command until the turn finished."
- `/effort`: "Run it while Claude is responding and, once you confirm the cache warning, if Claude Code shows one, Claude Code applies the new level to the next request in that turn."
- `/model`: "Once you confirm the switch, if Claude Code asks, Claude Code applies the change without waiting for the current response to finish."
- `/fast`: "Run it while Claude is responding and Claude Code toggles fast mode without waiting for the turn to end, though the running turn finishes at its original speed."
- `/usage` and `/tasks`: run immediately.

**INFERRED.** Each command carries a `midTurnBehavior` of roughly: `queue` (default), `immediate` (render now), or `immediate-confirm` (render now, and the change applies to the *next* request in the current turn rather than after the turn ends). The observable consequence is important and worth copying: **a command issued mid-turn can change the state of the turn that is still running** — the doc says `/add-dir` makes *"Claude's next tool call in the same turn"* able to access the new directory, and `/permissions` applies *"starting with Claude's next tool call in the same turn."* That is a live mutation of an in-flight turn, not a post-turn action.

**Reimplementation need: high.** A reimplementation needs a message queue in front of the dispatcher with a per-command "interrupt" policy, and the ability to apply a mid-turn mutation to the running turn's tool-permission context.

**Clean-room opportunity.** Model this as: the turn loop owns a `pendingInputQueue`; each command entry declares `whenBusy: 'queue' | 'immediate' | 'immediate+mutate-current-turn'`. `immediate+mutate-current-turn` handlers must be able to reach the live turn's context object. This is a concurrency/messaging design decision, entirely independent of any implementation.

---

### F7 — Session lifecycle commands and their exact argument semantics

**OBSERVED-DOC.** The table states these precisely:

> `/clear [name]` — "Start a new conversation with empty context. Pass a name to label the previous conversation in the `/resume` picker. To free up context while continuing the same conversation, use `/compact` instead. Resume the previous conversation with `/resume`, or, in the same Claude Code process, restore it from the rewind menu's previous-session entry. Aliases: `/reset`, `/new`"

> `/resume [session]` — "Resume a conversation by ID or name, or open the session picker. Background sessions appear in the picker marked with `bg`. Resuming one that is still running, from the picker or by ID or name, opens that session: your current conversation moves to the background and this terminal attaches to the running one. Press `←` on an empty prompt to return to agent view … Alias: `/continue`"

> `/branch [name]` — "Create a branch of the current conversation at this point … Switches you into the branch and preserves the original, which you can return to with `/resume`. To run a copy as a separate background session instead of switching into it, use `/fork`; to hand a side task to a subagent that reports back into this conversation, use `/subtask`"

> `/fork [prompt]` — "Copy the current conversation into a new background session and keep working here. Pass a prompt and the copy starts working on it immediately; without one it waits in agent view for its first prompt. Except when the copy edits in place, Claude Code instructs it to create a worktree of its own before making code changes"

> `/subtask <task>` — "Spawn a forked subagent: a background subagent that inherits the full conversation and works on the task while you keep working. Its result returns to this conversation when it finishes. … When agent view is turned off, `/subtask` isn't available and `/fork` spawns the forked subagent instead"

> `/rename [name]` — "Rename the current session and show the name on the prompt bar. Without a name, auto-generates one from conversation history. … Claude Code replaces control and invisible characters in the new name with spaces and caps the name at 200 characters. If the name is empty once invisible characters are removed, Claude Code rejects it and shows `That name is empty once invisible characters are removed. Usage: /rename <name>`."

> `/rewind` — "Rewind the conversation and/or code to a previous point, or summarize from a selected message. … Aliases: `/checkpoint`, `/undo`"

**OBSERVED-CLI.** `/rename mysession` printed exactly `Session renamed to: mysession` with `local_command: "rename"`, `num_turns: 0`, `duration_api_ms: 0`.

**INFERRED.** The doc distinguishes four *different* operations that a naive implementation would conflate into one "copy session": **branch** (switch into the copy, original preserved and reachable via `/resume`), **fork** (copy runs as a separate background session, you stay put), **subtask** (copy runs as a background subagent whose result returns into this conversation), and **clear** (new conversation, empty context, but *the same project memory* — "starts fresh on a new task while keeping project memory"). The `/clear` row in the workflow section is explicit: *"`/clear` starts fresh on a new task while keeping project memory."*

**Reimplementation need: high.** These four need distinct session-store semantics: branch = fork-with-same-foreground-pointer; fork = fork-as-background-agent; subtask = fork-as-subagent-with-result-injection; clear = new conversation retaining project-scoped memory.

**Clean-room opportunity.** A session store with `fork(sessionId, {mode: 'branch'|'background'|'subagent'})` covers all three fork variants with one primitive; `clear` is `startSession(keepProjectMemory: true)`. The 200-character cap and the invisible-character replacement in `/rename` are cheap, exactly-specified validation rules worth copying verbatim because they are user-visible error strings.

---

### F8 — Commands that change state without a model call, and the exact strings they print

**OBSERVED-CLI.** Five locally-handled commands and their verbatim outputs on this host:

| Command | Verbatim output |
| :- | :- |
| `/config theme=dark` | `Set Theme to dark` |
| `/rename mysession` | `Session renamed to: mysession` |
| `/model sonnet` | ``Set model to `Sonnet 5.5` for this session only`` |
| `/mcp` | `1 MCP server(s): 0 connected, 1 connecting, 0 not connected, 0 disabled. Use `/mcp` in the terminal for details.` |
| `/usage` | `Total cost: $0.0000 … Usage: 0 input, 0 output, 0 cache read, 0 cache write` |

**Corroboration (OBSERVED-DOC).** These match the doc's descriptions exactly, including the "for this session only" scoping the doc mentions for `/model`: *"Also available in non-interactive mode (`-p`) with a model argument instead of the picker, where it applies to the current session only and isn't saved as your default; requires Claude Code v2.1.205 or later."* And for `/mcp`: *"In non-interactive mode (`-p`), running it with no argument prints a text summary of server status instead of opening the list."* And for `/config`: *"Pass one or more `key=value` pairs to set a setting directly without opening the interface, for example `/config thinking=false`, `/config theme=dark`, or `/config model=sonnet`."*

**Reimplementation need: high.** These are the commands an embedder or a script will drive. Their contract is small and precise: parse `key=value`, mutate the settings store, print a one-line confirmation, no model call, no cost. The `/model` result also confirms the **scoping distinction** — `/model sonnet` changed the session but not the saved default, matching *"Switch the AI model and save it as your default for new sessions"* versus the print-mode variant which *"applies to the current session only and isn't saved as your default."*

**Clean-room opportunity.** A settings store keyed by the same key names the docs use (`theme`, `model`, `thinking`, `autoContinueAtUsageLimit`, …), a `key=value` parser, and a confirmation formatter. The one-line confirmation format `Set <Key> to <value>` is a trivially reproducible convention.

---

### F9 — `/context` is a context-usage dashboard with a fixed category taxonomy

**OBSERVED-CLI.** `/context` and `/context all` both rendered locally with zero model turns. `/context` printed a Markdown table with these exact categories:

```
| Category | Tokens | Percentage |
| System prompt | 2k | 1.0% |
| System tools | 18.9k | 9.4% |
| System tools (deferred) | 19.8k | 9.9% |
| Skills | 2k | 1.0% |
| Free space | 144.1k | 72.1% |
| Autocompact buffer | 33k | 16.5% |
```

followed by a `### Skills` table with columns `| Skill | Source | Tokens |` and source values `User` and `Built-in`.

**OBSERVED-DOC.** The row states the intent: *"Visualize current context usage as a colored grid. Shows optimization suggestions for context-heavy tools, memory bloat, and capacity warnings. When the conversation exceeds the context window, the output includes a warning showing how far over the limit you are and which command frees space. In fullscreen mode, `/context` collapses the per-item breakdown to keep the grid visible. Pass `all` to expand it."*

**INFERRED.** The token accounting is a *budget*, not just usage: the categories are drawn against the model's context window, and two of them are reserves — "Free space" (72.1%) and "Autocompact buffer" (16.5%) — summing with the consumed categories to the full window (22.9k used + 144.1k free + 33k buffer = 200k). The "Autocompact buffer" row corresponds to the auto-compact window set by `/autocompact`: *"`/autocompact [auto\|<tokens>]` … Set the auto-compact window: how full the context window gets before Claude Code compacts automatically."* The reference CLI help confirms the range: `--autocompact <auto|tokens>  Auto-compact window size (auto, or 100k–1M tokens)`.

**INFERRED.** "System tools (deferred)" (19.8k) is larger than "System tools" (18.9k) — deferred tools are tool *definitions* that are not loaded into the active tool set but are still counted against the budget, consistent with the reference's deferred-tool loading (visible in this host's `init` event as a separate tool-resolution mechanism). The reimplementation implication: a context dashboard is only meaningful if the implementation tracks *tool-definition tokens* and *deferred tool-definition tokens* separately from conversation tokens.

**Reimplementation need: medium-high.** A context accounting model with these buckets, a per-skill token attribution, and a visible auto-compact reserve.

**Clean-room opportunity.** Compute the categories from data you already have: system-prompt tokens (measured), tool-definition tokens (measured per tool), skill tokens (measured per skill), conversation tokens (measured), reserve = `window * autocompactRatio`. The `Skills` sub-table with a `Source` column (`User` / `Built-in`) and a `Tokens` column (`~480`, `< 20`) is directly reimplementable and immediately useful to a user optimizing their setup.

---

### F10 — Command-specific flags, and the `--max-findings` / `--fix` / `--comment` contract

**OBSERVED-DOC.** The `/code-review` row gives the fullest flag grammar in the table:

> "`/code-review [low|medium|high|xhigh|max|ultra] [--fix] [--comment] [--max-findings n|all|default] [pr#|branch|path]` … Review the current diff, or a PR number, branch, or path you pass, for correctness bugs. Depending on your model and effort level, the review also covers cleanup opportunities. Pass `--fix` to have Claude apply the findings, `--comment` to post them on the GitHub PR or GitLab merge request, or `ultra` to run a deep cloud review. … With `ultra` on a `github.com` PR target, pass `--post` to preselect posting the finished findings to the PR in the launch dialog; `--post` requires Claude Code v2.1.227 or later. … Alias: `/review`"

Other exact flag semantics across the table:

- `/import [codex|gemini|cursor] [--dry-run] [--yes]` — "Add `--dry-run` to preview without writing anything, or `--yes` to skip the interactive picker."
- `/reload-plugins [--force]` — "Reports counts for each reloaded component and flags any load errors. When the reload would change which MCP tools are loaded and invalidate the prompt cache, the command warns and skips unless you pass `--force`."
- `/advisor [model|off]` — "Accepts `fable`, `opus`, `sonnet`, or a full model ID. `fable` requires Fable access. Without an argument, opens a picker. In a session without an interactive terminal, or over Remote Control, pass the model or `off` as an argument; with no argument there, the command prints the current advisor as text. These forms require Claude Code v2.1.260 or later"
- `/effort [level|auto|status|ultracode [on|off]]` — "Set the effort level: `low` to `xhigh`, `max`, or `auto`; `status` prints it. `ultracode` or `ultracode on` turns ultracode on for the session at the current level, and `ultracode off` turns it off; the `ultracode` key persists. `max` is session-only."
- `/copy [N]` — "Copy the last assistant response to clipboard. Pass a number `N` to copy the Nth-latest response: `/copy 2` copies the second-to-last. When code blocks or blockquotes are present, shows an interactive picker to select individual blocks or the full response. Press `w` in the picker to write the selection to a file instead of the clipboard, which is useful over SSH"
- `/color [color|default]` — "Available colors: `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan`. Use `default` to reset, or run with no argument to pick a random color. … Also available in non-interactive mode (`-p`)"
- `/tui [default|fullscreen]` — "Set the terminal UI renderer and relaunch into it with your conversation intact. `fullscreen` enables the flicker-free alt-screen renderer. With no argument, prints the active renderer"
- `/doctor [prompt-audit [path]]` — "Run a setup checkup that diagnoses installation, settings, extension, and `CLAUDE.md` problems and proposes fixes that Claude applies after you confirm."

**INFERRED.** The flag vocabulary is small and consistent: long-form `--flag` booleans, `--flag value` with a typed value, and a leading positional that is an *enum* (effort level, advisor model, color name). The `n|all|default` pattern for `--max-findings` is a tri-state enum. There is no `--flag=value` form documented, and no short flags.

**Reimplementation need: high.** Every command needs a working argument parser; getting the parser right for `--max-findings n|all|default` (where `all` and `default` are keywords, not numbers) and for nested optionals (`/doctor [prompt-audit [path]]`) is where naive parsers break.

**Clean-room opportunity.** A single flag parser supporting `--name` (boolean), `--name value` (value), and positionals, plus per-command enum validation with a list of accepted values (e.g. colors). The doc gives the accepted value sets explicitly, so validation messages can be exact.

---

### F11 — Review, diff, and verification commands as a coherent "before you ship" group

**OBSERVED-DOC.** The workflow section defines a ship-checklist grouping:

> "**Before you ship.** `/diff` shows what changed. `/code-review` checks the current diff for correctness bugs and can apply the findings with `--fix`; pass a PR number, such as `/code-review high 1234`, to review a pull request instead. `/review` is an alias. `/code-review ultra` runs a multi-agent review in the cloud. `/security-review` checks the diff for security vulnerabilities."

> "`/diff` | Review the changes in your working tree, including the edits Claude has made so far."

> "`/security-review` | Analyze the changes on your current branch for security vulnerabilities. Reviews the diff between your branch and origin's default branch, identifying risks like injection, auth issues, and data exposure. Needs an `origin` remote; if the review fails with an `ambiguous argument` error, see the error reference"

> "`/verify` | **[Skill].** Confirm a code change does what it should by building your project's app, running it, and observing the result, rather than relying on tests or type checks."

> "`/simplify [target]` | **[Skill].** Review the changed code for cleanup opportunities and apply the fixes. Four review agents run in parallel, covering reuse of existing helpers, simplification, efficiency, and whether the change is at the right level of abstraction. The review doesn't look for correctness bugs. Use `/code-review` to find bugs. Pass a path or PR reference to review a specific target"

**OBSERVED-DOC.** The division of labour is explicit and worth copying: `/code-review` finds **correctness bugs**; `/simplify` finds **cleanup opportunities** and explicitly does *not* look for correctness bugs; `/security-review` covers **security vulnerabilities**; `/verify` checks **runtime behavior** rather than tests or type checks.

**Reimplementation need: medium.** Four distinct verification surfaces with clearly separated concerns.

**Clean-room opportunity.** Map each to a distinct reviewer with a distinct prompt and a distinct output schema. The "doesn't look for correctness bugs" constraint on the cleanup reviewer is a *scope-limiting instruction* — easy to state, and it prevents the two reviewers from duplicating each other.

---

### F12 — Model, effort, and context-window control, and the persistence distinction

**OBSERVED-DOC.** Three commands govern the model's behavior:

> "`/model [model]` | Switch the AI model and save it as your default for new sessions. For models that support it, use left/right arrows to adjust effort level. With no argument, opens a picker; press `s` on a row to switch for the current session only. … Once you confirm the switch, if Claude Code asks, Claude Code applies the change without waiting for the current response to finish. … Also available in non-interactive mode (`-p`) with a model argument instead of the picker, where it applies to the current session only and isn't saved as your default"

> "`/effort [level|auto|status|ultracode [on|off]]` | Set the effort level: `low` to `xhigh`, `max`, or `auto`; `status` prints it. … `max` is session-only. … Works in `-p`"

> "`/autocompact [auto|<tokens>]` | Set the auto-compact window: how full the context window gets before Claude Code compacts automatically. Pass a size such as `500k`, or `auto` to return to the window tuned for your model. Claude Code saves the value to user settings and applies it to the current session. … Without an argument, opens a dialog that shows the current window. Requires Claude Code v2.1.221 or later"

**OBSERVED-DOC.** The reference CLI help corroborates the value domains:

> `--autocompact <auto|tokens>  Auto-compact window size (auto, or 100k–1M tokens)`
> `--effort <level>  Effort level for the current session (low, medium, high, xhigh, max)`
> `--model <model>  Model for the current session. Provide an alias for the latest model (e.g. 'fable', 'opus', or 'sonnet') or a model's full name.`

**OBSERVED-CLI.** `/model sonnet` printed ``Set model to `Sonnet 5.5` for this session only`` — confirming the alias→model resolution (`sonnet` → `Sonnet 5.5`) *and* the session-only scoping in print mode.

**INFERRED.** There are three separate persistence scopes, each with a distinct lifetime, and the commands differ in which they use:
- **session-only** — `/model` in `-p` mode; `/effort max` ("`max` is session-only").
- **session + user settings** — `/autocompact` ("saves the value to user settings and applies it to the current session"); `/effort ultracode` ("the `ultracode` key persists").
- **default for new sessions** — `/model` in interactive mode ("save it as your default for new sessions").

**Reimplementation need: high.** Getting these scopes right is what makes `/model` usable from a script without silently rewriting the user's global default.

**Clean-room opportunity.** Three named stores with explicit write targets: `sessionState`, `userSettings`, `defaultConfig`. Each command declares which it writes. The alias→concrete-model resolution table (`sonnet`, `opus`, `fable`, `haiku`) is a simple map plus a "latest alias" lookup.

---

### F13 — MCP server management from the command surface

**OBSERVED-DOC.**

> "`/mcp [reconnect (<server>|all)|enable|disable [<server>|all]]` | Manage MCP server connections and OAuth authentication. Run with no argument to open the interactive list, or pass `reconnect`, `enable`, or `disable` with a server name or `all` to change connection state without opening it. `reconnect all` retries every server that failed or needs authentication. In non-interactive mode (`-p`), running it with no argument prints a text summary of server status instead of opening the list"

**OBSERVED-CLI.** `/mcp` in `-p` mode printed, verbatim:

> `1 MCP server(s): 0 connected, 1 connecting, 0 not connected, 0 disabled. Use `/mcp` in the terminal for details.`

This is an exact four-bucket status vector: **connected / connecting / not connected / disabled**, plus a total. The `reconnect`/`enable`/`disable` verbs map to server *connection state*, not to server *configuration*.

**INFERRED.** The four buckets are a small state machine per server: `disabled` (user/managed off) → `not connected` (enabled but failed or unauthenticated) → `connecting` (in-flight) → `connected` (ready). `reconnect` resets a non-connected server to `connecting`; `enable`/`disable` toggle the `disabled` flag. `reconnect all` is a bulk operation over the same predicate.

**Reimplementation need: high.** A per-server status enum with those exact four values, plus bulk verbs.

**Clean-room opportunity.** Model server status as an enum `{disabled, notConnected, connecting, connected}` and expose the count vector in the summary line. The `all` bulk target is a one-word addition to every verb. The MCP-prompt-as-command bridging (F5) plugs into the same registry.

---

### F14 — `/skills` is an interactive registry with a visibility toggle

**OBSERVED-DOC.**

> "`/skills` | List available skills. Type to filter the list by name, description, or source. Press `t` to sort by token count, `Space` or `Enter` to cycle a skill's visibility to Claude and the `/` menu, and `Esc` to save and close. You can't cycle plugin skills, skills whose frontmatter sets `disable-model-invocation: true`, or skills with a `skillOverrides` entry in managed settings or the `--settings` flag"

> "`/reload-skills` | Re-scan skill and command directories so skills added or changed on disk during the session become available without restarting. Reports how many skills are available and how many were added or removed"

> "`/skill-doctor` | Show what each of your skills costs in context and how often it gets used, so you can find skills to turn off. Requires Claude Code v2.1.252 or later and feature-flag fetching"

**OBSERVED-DOC (corroboration).** The reference CLI help confirms the corresponding launch flag: `--disable-slash-commands  Disable all skills and commands`. And `skills.md`: *"To turn bundled skills off, use the `disableBundledSkills` setting."*

**OBSERVED-CLI.** `/reload-skills` and `/skill-doctor` are present in the `slash_commands` array on this host. `--disable-slash-commands` emptied `skills` and `slash_commands` entirely.

**INFERRED.** A skill's *visibility* to Claude and to the `/` menu is a separate axis from its *existence* — a skill can be present in the registry but hidden from one or both consumers. The three exclusions from cycling (`plugin` skills, `disable-model-invocation: true` skills, skills with a managed `skillOverrides` entry) are all cases where the visibility is decided by something other than the user. The `disable-model-invocation` exclusion is the notable one: that frontmatter field controls whether *Claude* may invoke the skill, and the `/` menu's cycle control is therefore not allowed to change it.

**Reimplementation need: medium-high.** Model visibility as a two-bit value (visible-to-model, visible-in-menu) plus a `visibilityLockedBy` reason.

**Clean-room opportunity.** A `SkillRegistry` with `{name, source, description, tokens, visibleToModel, visibleInMenu, visibilityLockedBy}`. The `/skills` UI is a filterable table over that registry; the `t` sort key is `tokens`; `Space`/`Enter` cycles visibility subject to the lock.

---

### F15 — `/config` exposes settings by key, and the settings key namespace

**OBSERVED-DOC.**

> "`/config [key=value ...]` | Open the Settings interface to adjust theme, model, output style, and other preferences. Pass one or more `key=value` pairs to set a setting directly without opening the interface, for example `/config thinking=false`, `/config theme=dark`, or `/config model=sonnet`. The `key=value` form also works in non-interactive mode (`-p`) and from the Claude mobile app via Remote Control. The `key=value` form can't turn on a setting that needs your confirmation in the panel, such as `autoContinueAtUsageLimit`, though it can turn one off. Run `/config --help` to list the keys it accepts. Alias: `/settings`"

**OBSERVED-CLI.** `/config theme=dark` printed `Set Theme to dark` with `local_command: "config"`, `num_turns: 0`.

**INFERRED.** The confirmation message `Set Theme to dark` shows the key `theme` is rendered as a title-cased label ("Theme"), i.e. the settings store holds display labels alongside keys. The doc's own example keys — `thinking`, `theme`, `model` — plus `autoContinueAtUsageLimit` and `ultracode` (referenced by `/effort`) and `viewMode` (referenced by `/focus`) establish the key style: **camelCase for multi-word settings keys** (`autoContinueAtUsageLimit`, `viewMode`), lowercase for single words (`theme`, `model`, `thinking`, `ultracode`).

**Reimplementation need: high.** A settings store with a canonical key namespace, a display-label mapping, a `needsConfirmation` flag per setting, and a `key=value` command form.

**Clean-room opportunity.** `settings.json` with camelCase keys, a per-setting `{label, value, needsConfirmation, scope}` descriptor table, and a `/config key=value` path that bypasses the UI but still honors `needsConfirmation` (refuse to turn *on* a confirmation-gated setting; allow turning it off — exactly as the doc specifies).

---

### F16 — The `/feedback` / `/bug` consent model and the local-archive fallback

**OBSERVED-DOC.**

> "`/bug [report]` | Report a bug or share your conversation. You choose how much session history to include and confirm on a consent screen before anything is sent. When you're signed in to Anthropic on a first-party connection, the report goes to Anthropic; on a third-party provider, or without Anthropic credentials, Claude Code writes the report to a local archive under `~/.claude/feedback-bundles/` that you forward yourself. In the VS Code extension, `/bug` opens the extension's own feedback dialog instead; requires Claude Code v2.1.229 or later. … Alias: `/share`. Before v2.1.212, `/bug` and `/share` were aliases of `/feedback`"

> "`/feedback [report]` | Send product feedback about Claude Code. Opens the same dialog as `/bug`, with the same consent step, sending rules, and mid-turn behavior. In sessions with Claude-drafted feedback, `/feedback` with no argument opens the drafts queue instead, where you review, edit, send, or discard the drafts Claude queued; the queue includes an option to write a new report in the dialog. With an argument, and for `/bug` always, the dialog opens directly"

**INFERRED.** Two things are notable for a clean-room build. First, **the consent screen is a hard gate before any network egress of user data** — "confirm on a consent screen before anything is sent", with the user choosing the scope of session history included. Second, the **local-archive fallback** is a deliberate privacy design: on a non-first-party provider the tool does not transmit at all, it writes to `~/.claude/feedback-bundles/` and the user forwards it manually. The path `~/.claude/feedback-bundles/` is an exact, reimplementable location.

**Reimplementation need: medium.** A consent-gated egress path with a local-archive fallback and a per-provider routing decision.

**Clean-room opportunity.** A `FeedbackReport` builder that (a) asks for a history scope, (b) requires explicit confirmation, (c) either POSTs to the first-party endpoint or writes a timestamped bundle under `~/.claude/feedback-bundles/`, and (d) never transmits without (b). The Claude-drafted-feedback queue is an optional extra.

---

### F17 — Documentation-surface commands, and `/help`'s own availability

**OBSERVED-DOC.**

> "`/help` | Show help and available commands"
> "`/release-notes` | View the changelog in an interactive version picker. Select a specific version to see its release notes, or choose to show all versions. The notes appear in your transcript without entering the conversation Claude sees"
> "`/export [filename]` | Export the current conversation as plain text. With a filename, writes directly to that file. Without, opens a dialog to copy to clipboard or save to a file"
> "`/status` | Open the Settings interface on the Status tab, showing version, model, account, and connectivity."

**OBSERVED-CLI.** `/help` in `-p` mode printed, verbatim: ``/help isn't available in this environment.``

**INFERRED.** `/help` is a **terminal-only** command: it is not merely gated by plan or version, it requires an interactive terminal, and in a headless run it reports availability rather than dumping the command list as text. Contrast `/mcp`, which the doc explicitly says degrades to a text summary in `-p` mode. So the reference distinguishes *degradable* commands (`/mcp`, `/model`, `/config`, `/color`, `/rename`) from *terminal-only* commands (`/help`, `/permissions`, `/theme`, `/hooks`, `/ide`, `/keybindings`). The observed `terminal_slash_commands` array — `["doctor","color","focus","reload-plugins"]` — names four that "render locally, no model call" (per this host's own PROTOCOL-NOTES), which is a *different* axis again: local-render vs. needs-a-TTY.

**Reimplementation need: medium.** Three distinct non-delivery reasons must be representable: terminal-only, gated-unavailable, and unknown-command. Each has its own message shape.

**Clean-room opportunity.** Give each command entry a `requiresTTY` flag alongside the `Gate[]` predicates, and produce distinct messages for "needs an interactive terminal", "not available in this environment/plan", and "unknown command with a suggestion".

---

### F18 — The whole table is version-gated, and the gates are informative only

**OBSERVED-DOC.** The table is dense with version gates — among them: `/artifacts` "Requires Claude Code v2.1.208 or later; attaching with `Enter` requires v2.1.216"; `/artifact-diagramming` "Requires Claude Code v2.1.221 or later"; `/output-style` "Requires Claude Code v2.1.269 or later"; `/design` and `/slides` "Requires Claude Code v2.1.265 or later"; `/import` from Cursor "requires v2.1.265 or later"; `/list-agents` "Requires Claude Code v2.1.224 or later"; `/list-agents` teammate rows "require v2.1.239 or later"; `/design-sync` "requires Claude Code v2.1.248 or later" for `/workflow-authoring`; `/plugin-authoring` "Requires Claude Code v2.1.287 or later"; `/doctor prompt-audit` "requires Claude Code v2.1.283 or later"; `/effort ultracode on|off` "require Claude Code v2.1.284 or later".

The doc also records *behavioral* historical changes, which are more useful than the gates themselves:

> "`/review` … Before v2.1.223, `/review` was a separate command that ran a single-pass, read-only review of a GitHub pull request by number … from v2.1.186 through v2.1.201, it ran the same multi-agent engine as `/code-review medium`"

> "`/code-review` … Before v2.1.215, Claude could also run `/verify` on its own."

> "`/deep-research` … Before v2.1.218, Claude could also start it on its own."

> "`/vim` | Removed in v2.1.92." · "`/pr-comments [PR]` | Removed in v2.1.91." · "`/ultraplan <prompt>` | Removed. Use plan mode instead."

**INFERRED.** Version gates describe *release history*, not required behavior — a reimplementation should ignore them entirely except where a gate encodes a genuine dependency (a provider, a plan, a feature flag, an environment variable). The removed-command entries (`/vim`, `/pr-comments`, `/ultraplan`) show the reference keeps tombstones for removed commands rather than deleting the rows; a reimplementation that keeps its own changelog of retired commands is following a good precedent but is optional.

**Reimplementation need: low** for the gates themselves; **medium** for the *removed*-command tombstones if you want good error messages for users upgrading.

---

## 3. Capability table

Legend: **Doc** = stated in `commands.md`; **CLI** = observed on this host (Claude Code 2.1.306, headless `-p`); **—** = not applicable / not established.

| # | Capability | Evidence | Class | Needed for reimplementation |
| :- | :- | :- | :- | :- |
| 1 | Command recognized only at start of message; remainder = arguments | `commands.md` intro | Doc | Yes |
| 2 | Up to 6 skills chainable in one message at the terminal | `commands.md` intro; `skills.md` | Doc | Yes |
| 3 | Commands queued while Claude is responding; some run immediately | `commands.md` intro; `/status`,`/tasks`,`/usage` | Doc | Yes |
| 4 | `/` menu fuzzy-matches name or alias, ignoring `:` `_` `-` | `commands.md` §"How the command menu matches" | Doc | Yes |
| 5 | Typo → `Unknown command: /hepl. Did you mean /help?` | `errors.md` §"Unknown command" | Doc | Yes |
| 6 | `No commands match "/name"` when nothing matches | `commands.md` §"How the command menu matches" | Doc | Yes |
| 7 | Hidden commands excluded from menu but full name still executes | `commands.md`; `/heapdump`, `/setup-bedrock`, `/setup-vertex` | Doc | Yes |
| 8 | Availability gates: platform / plan / provider / version / policy / env | `commands.md` §"All commands" note | Doc | Yes |
| 9 | `local_command` field on headless `result` event names the local handler | this host, `--output-format stream-json --verbose` | **CLI** | **Yes (highest value)** |
| 10 | Locally-handled commands run with `num_turns: 0`, `duration_api_ms: 0` | `/context`, `/usage`, `/mcp`, `/config`, `/rename`, `/model` | **CLI** | Yes |
| 11 | Unmatched `/` name in headless mode is sent to the model as text | this host, `/zzzznotacommand` → `num_turns: 1` | **CLI** | Yes |
| 12 | Unavailable command in headless mode prints "isn't available in this environment." | this host, `/help`, `/permissions` | **CLI** | Yes |
| 13 | `system`/`init` carries `slash_commands`, `terminal_slash_commands`, `skills`, `agents` | this host | **CLI** | Yes |
| 14 | `--disable-slash-commands` empties `slash_commands` + `skills`, drops `terminal_slash_commands` | this host | **CLI** | Yes |
| 15 | `/context` renders a token-budget table with fixed categories | this host (`/context`, `/context all`) | **CLI** | Yes |
| 16 | `/mcp` in `-p` prints connected/connecting/not-connected/disabled counts | this host | **CLI** | Yes |
| 17 | `/config key=value` sets a setting with no model call | this host (`Set Theme to dark`) | **CLI** | Yes |
| 18 | `/model <alias>` in `-p` = session-only, not saved as default | this host (`Set model to \`Sonnet 5.5\` for this session only`) | **CLI** | Yes |
| 19 | `/rename` sanitizes invisible chars, caps at 200 chars | `commands.md` `/rename` | Doc | Yes |
| 20 | `/clear` keeps project memory | `commands.md` workflow section | Doc | Yes |
| 21 | branch / fork / subtask are three distinct conversation-copy operations | `commands.md` `/branch`, `/fork`, `/subtask` | Doc | Yes |
| 22 | `/rewind` = conversation and/or code checkpoint rollback | `commands.md` `/rewind` | Doc | Yes |
| 23 | Skills and workflows share the command namespace, marked in the table | `commands.md` §"All commands" | Doc | Yes |
| 24 | MCP prompts appear as `/servername:promptname (MCP)`; `/mcp__server__prompt` also runs | `mcp.md` §"Use MCP prompts as commands" | Doc | Yes |
| 25 | MCP prompt arguments split on whitespace only | `mcp.md` | Doc | Yes |
| 26 | Server name `anthropic-skills` reserved; its prompts hidden | `mcp.md` | Doc | Yes |
| 27 | Custom commands = skills; `.claude/commands/x.md` → `/x`; subdir → `/dir:name` | `skills.md` | Doc | Yes |
| 28 | `/code-review` flags `--fix`, `--comment`, `--max-findings n\|all\|default` | `commands.md` | Doc | Yes |
| 29 | Effort levels `low`…`xhigh`, `max`, `auto`, `status` | `commands.md`; `--effort` help | Doc + CLI | Yes |
| 30 | Autocompact window `auto` or 100k–1M tokens | `--autocompact` help | CLI | Yes |
| 31 | `/skills` cycles visibility; lock reasons listed | `commands.md` | Doc | Medium |
| 32 | `/skill-doctor` reports per-skill context cost and usage | `commands.md` | Doc | Medium |
| 33 | `/reload-skills` re-scans on disk without restart | `commands.md` | Doc | Medium |
| 34 | Feedback requires consent screen before any send | `commands.md` `/bug`, `/feedback` | Doc | Medium |
| 35 | Feedback falls back to `~/.claude/feedback-bundles/` off first-party | `commands.md` `/bug` | Doc | Medium |
| 36 | `/code-review` finds bugs; `/simplify` finds cleanup only; `/security-review` finds vulns; `/verify` checks runtime | `commands.md` workflow section | Doc | Medium |
| 37 | `/permissions` dialog: rules by scope, add/remove, working dirs, auto-mode denials | `commands.md` `/permissions` | Doc | Yes (covered by area 8) |
| 38 | `/add-dir` grants access from the next tool call in the same turn | `commands.md` `/add-dir` | Doc | Yes |
| 39 | `/cd` moves the session's working directory, keeping the conversation | `commands.md` `/cd` | Doc | Yes |
| 40 | `/export` writes plain-text transcript; `/copy N` copies Nth-latest response | `commands.md` | Doc | Low |
| 41 | `/release-notes` shows notes in the transcript without entering the model's conversation | `commands.md` | Doc | Low |
| 42 | Version gates | `commands.md` | Doc | No |
| 43 | Subscription-gated surfaces (`/desktop`, `/teleport`, `/schedule`, `/upgrade`, `/usage-credits`, `/privacy-settings`, `/passes`, `/remote-control`, `/mobile`, `/web-setup`, `/artifacts`, `/design`, `/slides`) | `commands.md` | Doc (not observable here) | No |
| 44 | Cloud/agent surfaces (`/background`, `/fork`, `/batch`, `/tasks`, `/subtask`, `/workflows`, `/ultrareview`) | `commands.md` | Doc | Medium |
| 45 | Removed commands kept as tombstones (`/vim`, `/pr-comments`, `/ultraplan`) | `commands.md` | Doc | Low |

---

## 4. Dependencies

### 4.1 Required for the command layer

| Dependency | Why | Evidence |
| :- | :- | :- |
| A model provider | Commands that deliver a prompt to the model need one | `commands.md` §"All commands" — bundled skills are "a prompt handed to Claude" |
| A terminal (TTY) | Some commands need an interactive terminal | OBSERVED-CLI: `/help`, `/permissions` → "isn't available in this environment" |
| A settings store | `/config key=value`, `/theme`, `/model`, `/autocompact` | OBSERVED-CLI: `/config theme=dark` |
| A session store | `/clear`, `/resume`, `/branch`, `/fork`, `/rename`, `/rewind` | `commands.md` rows for each |
| An MCP client | `/mcp` verbs; MCP prompts as commands | `commands.md` `/mcp`; `mcp.md` |
| A git working tree | `/diff`, `/code-review`, `/security-review`, `/batch` (worktrees) | `commands.md` rows for each |
| A skill registry (filesystem scan) | `/skills`, `/reload-skills`, `/skill-doctor` | `commands.md` rows; `skills.md` |

### 4.2 Network / account / provider dependencies of this surface

| Command | Requires |
| :- | :- |
| `/bug`, `/feedback` | First-party Anthropic auth to transmit; otherwise local archive only |
| `/desktop` | macOS or x64 Windows **and** a Claude subscription |
| `/teleport`, `/remote-control`, `/web-setup` | claude.ai subscription |
| `/schedule`, `/usage-credits`, `/privacy-settings`, `/passes`, `/upgrade` | claude.ai subscription / specific plan |
| `/artifacts`, `/design`, `/slides`, `/design-sync`, `/artifact-capabilities`, `/artifact-diagramming` | Anthropic API only — *"On Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, and Claude Platform on AWS, artifacts aren't available"* |
| `/import` | Not available on Bedrock / Vertex / Foundry / AWS, or through a Claude apps gateway; also unavailable when feature-flag fetching is off |
| `/ultrareview`, `/code-review ultra`, `/autofix-pr` | Cloud sessions (claude.ai) |
| `/install-github-app`, `/install-slack-app` | github.com / Slack OAuth |
| `/skill-doctor` | Feature-flag fetching (i.e. Anthropic connectivity) |
| `/setup-bedrock`, `/setup-vertex` | `CLAUDE_CODE_USE_BEDROCK=1` / `CLAUDE_CODE_USE_VERTEX=1` respectively |
| `/voice` | A Claude.ai account |
| `/chrome`, `/claude-in-chrome` | Chrome integration enabled (`claude --chrome`) |

### 4.3 Host limitation that shaped this investigation

This host runs against a custom `ANTHROPIC_BASE_URL` (OpenRouter), so `api.anthropic.com` is never contacted and no claude.ai subscription is active. `claude doctor` on this host confirms: *"Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL"* and *"Not signed in to claude.ai"*. Consequently **every claude.ai-gated command is `OBSERVED-DOC` only.** The version of the CLI here (2.1.306) is *older* than several gates in the doc (e.g. `/plugin-authoring` requires v2.1.287, `/effort ultracode on|off` requires v2.1.284) — 2.1.306 satisfies those, but `/doctor prompt-audit` (v2.1.283) and others were not individually exercised.

---

## 5. Limitations of this investigation

1. **No interactive-TTY observation.** All command dispatch observations came from `-p` headless mode. The interactive menu, its highlighting, the `Tab`/arrow-key selection, the `Space`/`Enter` visibility cycle in `/skills`, and the `w` key in the `/copy` picker are documented but **not observed here**. A future investigation should drive the TUI (the reference's own `tui-startup-banner.txt` capture shows a TUI harness is feasible on this host).
2. **This host's `claude` is a child session** (`CLAUDE_CODE_CHILD_SESSION=1`, `CLAUDECODE=1`), and the parent session's `ANTHROPIC_BASE_URL` is inherited. Some surfaces may differ from a fresh standalone run.
3. **Shell quoting corrupted my first three probes.** Git Bash rewrote the leading-slash argument into an absolute path (`/context` → `C:/Program Files/Git/context`), so the model received a *path* rather than a command. This produced a false early conclusion that headless mode does not dispatch commands locally. The corrected probes used PowerShell and showed local dispatch. **Anyone repeating this investigation on Windows must invoke the CLI from a shell that does not perform MSYS path conversion on arguments** (`MSYS_NO_PATHCONV=1` in Git Bash, or use PowerShell). This is a methodological trap worth recording.
4. **MCP prompts-as-commands was not exercised.** The `rea` MCP server was present but `pending`/failing to connect in these probes, so no `/server:prompt` command could be observed. The claim rests on `mcp.md` plus the `slash_commands` array design.
5. **Plan/provider-gated commands were not observable** (§4.3).
6. **The full ~110-row table was not transcribed row by row.** This report extracts the structurally load-bearing rows. The complete table is at the cited URL and is the authoritative source for per-command wording.

---

## 6. Unresolved questions (UNKNOWN)

| # | Question | Why it could not be established |
| :- | :- | :- |
| U1 | What is the exact "note that the command didn't run and a list of commands Claude can run" text injected into the headless unmatched-command prompt? | The note is injected *before* the request; the `--replay-user-messages` attempt errored, and the injected text is not visible in the `stream-json` event stream. The model's reply paraphrases it: *"isn't a command available in this session, so nothing ran — and there's no task text accompanying it for me to act on"* and *"Current session commands include things like …"*. The literal string is unknown. |
| U2 | Does the interactive TUI show the same `slash_commands` set as the headless `init` event? | Headless and TUI are different surfaces; only headless was observed. The doc's "Not every command appears for every user" note implies the TUI menu can differ. |
| U3 | What determines the *ordering* of commands in the `/` menu? | The doc describes matching and highlighting but never ordering. The `init` array's order (skills first, then built-ins) may or may not reflect menu order. |
| U4 | What is the `local_command` field's full set of possible values, and does it appear for skill-backed commands that happen to be handled locally? | Only seven values were observed: `context`, `usage`, `mcp`, `config`, `rename`, `model` (plus absence). Whether e.g. `/clear` sets it was not tested. |
| U5 | Are `slash_commands` and `terminal_slash_commands` documented anywhere publicly? | They appear in the `init` event but were not found in any fetched doc page. They may be an undocumented-but-stable protocol field. |
| U6 | What is the exact set of `Gate` predicates for each of the ~110 commands? | The table states gates in prose per command; the underlying predicate (e.g. exactly what "Enterprise plan" means for `/upgrade`) is not specified. |
| U7 | Does `/plan` differ from plan mode entered by other means? | `/plan` is documented as "Enter plan mode directly from the prompt"; the mechanics of the transition are not described on this page. |
| U8 | How is `skillOverrides` structured? | Referenced by `/skills` and `skills.md`; the exact JSON shape was not fetched on this page's scope. |
| U9 | Do bundled skills behave identically to user skills from the model's perspective? | `skills.md` says bundled skills are "prompt-based" and that `/verify` "runs only when you invoke it"; the invocation plumbing is not described on this page. |
| U10 | Is the `/` menu's `Did you mean` threshold distance-based? | The doc says "the closest command name or alias"; no metric is specified. |
| U11 | Does `/heapdump` write to `~/Desktop` on Windows too? | Doc says "Write a JavaScript heap snapshot and a memory breakdown to `~/Desktop`, or your home directory on Linux without a Desktop folder". Windows behavior is not stated. |
| U12 | What is the exact wording of the `No commands match "/name"` prompt's surrounding UI? | Only the inner string is given. |

---

## 7. Clean-room implementation notes

### 7.1 The one design decision that matters most

**Make the local/model split observable.** The reference exposes it as `"local_command": "<name>"` on the headless `result` event, and it is absent for model-delivered and unavailable commands. A reimplementation should adopt an equivalent, because it:
- lets an embedder tell "the agent did this" from "the user asked the agent" without heuristics;
- makes the split **testable without a model** (assert `num_turns == 0` and `duration_api_ms == 0`);
- gives the whole command layer a single, machine-readable assertion surface.

### 7.2 Data model

```
CommandEntry {
  name            : string          // canonical, e.g. "code-review"
  aliases         : string[]        // ["review"]
  argSpec         : ArgSpec         // positional/flag grammar
  source          : 'builtin' | 'bundled-skill' | 'user-skill' | 'project-skill'
                   | 'mcp-prompt' | 'workflow'
  delivery        : 'local' | 'model'
  handler         : (ctx, args) => LocalResult     // when delivery == 'local'
  prompt          : string                          // when delivery == 'model'
  gates           : Gate[]                          // platform/plan/provider/policy/env
  requiresTTY     : boolean
  whenBusy        : 'queue' | 'immediate' | 'immediate+mutate-current-turn'
  hiddenFromMenu  : boolean
  visibilityLock  : null | 'plugin' | 'disable-model-invocation' | 'managed-override'
}
```

### 7.3 Dispatch algorithm

1. Take the raw message. If it does not begin with `/`, treat it as an ordinary prompt.
2. If the first token after `/` starts with punctuation or looks like a filesystem path, treat it as an ordinary prompt (this is the documented `/var/log/syslog` and `/--` case).
3. Otherwise, look up the longest matching command name or alias among entries whose gates all pass.
4. If a match is found and `requiresTTY` is false → run the local handler; emit a result with `local_command` set; **never call the model**.
5. If a match is found but `requiresTTY` is true and there is no TTY → emit the availability message; do not call the model.
6. If a match is found and `delivery == 'model'` → prepend the command's prompt and dispatch to the model, exactly as an ordinary message.
7. If no match → dispatch to the model as an ordinary message, with a note that the command did not run and a list of the session's available commands (the exact note text is U1 — choose your own wording, but keep the two facts the reference guarantees: that nothing ran, and what commands *are* available).
8. In an interactive TTY, steps 4–7 additionally consult the menu's fuzzy matcher (§2 F4) and the "Did you mean" suggestion.

### 7.4 Tiered scope

**Tier 1 — the parity core (build first; everything else depends on it)**
1. Command registry + argument parser + dispatcher with the three-way delivery split and the `local_command` result field.
2. The `/` menu: fuzzy matcher over names+aliases, separator-insensitive, word-substring aware; hidden commands excluded but executable; `No commands match "/name"`.
3. `Unknown command: /x. Did you mean /y?` with edit-distance suggestion.
4. Local, no-model commands: `/context`, `/usage`, `/cost`, `/stats`, `/mcp` (summary), `/config key=value`, `/rename`, `/model`, `/clear`, `/help`, `/compact`, `/init` (skill).
5. `system`/`init`-equivalent event exposing the command registry, so embedders can enumerate.

**Tier 2 — strong differentiation**
6. Session lifecycle: `/clear` (keep project memory), `/resume`, `/branch`, `/fork`, `/subtask`, `/rewind`, `/rename`, `/export`.
7. Skills registry: skill discovery from `.claude/skills/*/SKILL.md` and `.claude/commands/*.md`, frontmatter (`name`, `description`, `argument-hint`, `allowed-tools`, `disable-model-invocation`), visibility cycling with lock reasons, `/skill-doctor` token accounting, `/reload-skills` live rescan.
8. MCP integration: `/mcp` verbs (`reconnect`/`enable`/`disable`, bulk `all`), four-bucket status, and MCP prompts registered as commands (`/server:prompt` and `/mcp__server__prompt`).
9. Permission surface: `/permissions` dialog, `/add-dir`, `/cd`.
10. Mid-turn queueing with per-command `whenBusy` policy and current-turn mutation.

**Tier 3 — nice to have**
11. `/diff`, `/code-review` (+ `--fix`/`--comment`/`--max-findings`), `/simplify`, `/security-review`, `/verify`, `/doctor`.
12. `/context` full breakdown, `/rewind` code rollback.
13. `/skills` interactive TUI, `/theme`, `/tui`, `/status`, `/usage-credits`.

**Explicitly out of scope — do not replicate**
- Claude.ai subscription surfaces (`/desktop`, `/teleport`, `/remote-control`, `/schedule`, `/upgrade`, `/usage-credits`, `/privacy-settings`, `/passes`, `/mobile`, `/web-setup`) — these are account-bound, not design-bound. Reimplement the *mechanism* (a gate that produces an availability message) with your own account/provider, not Anthropic's.
- Cloud multi-agent review (`/code-review ultra`, `/ultrareview`, `/autofix-pr`) — same.
- Artifacts / Design / Slides surfaces — provider-gated and orthogonal to the command layer.
- The exact version-gate strings — informational, not behavioral.
- The reference's internal prompt text for bundled skills — write your own.

### 7.5 Implementation order

1. **Dispatcher + registry + `local_command` envelope** — nothing else is testable without it.
2. **Argument parser** — every command depends on it; the `<arg>`/`[arg]`/`|` grammar is small and fully specified.
3. **Menu matcher + suggestion** — the user-visible quality bar for the whole feature.
4. **Session store + `/clear` `/resume` `/branch` `/fork`** — the command layer's only real state.
5. **Settings store + `/config key=value`** — the mechanism embedders will script against.
6. **Skill registry + MCP-prompt registration** — populates the namespace from outside the binary.
7. **Mid-turn queue** — only once the basic path is stable.

---

## 8. Evidence artifacts

| Path | Contents |
| :- | :- |
| `agent-reference-shots/area-commands/probe-ctx.sanitized.jsonl` | `system`/`init` + `result` for `/context` — the observed `slash_commands`, `terminal_slash_commands`, `skills`, `agents` arrays, and `local_command: "context"`, `num_turns: 0`, `duration_api_ms: 0`, with the full context-usage table. |
| `agent-reference-shots/area-commands/probe-ctxall.sanitized.jsonl` | Same for `/context all` — `local_command: "context"`, expanded per-item breakdown. |
| `agent-reference-shots/area-commands/probe-mcp.sanitized.jsonl` | `/mcp` — `local_command: "mcp"`, `num_turns: 0`, and the four-bucket server-status summary. |
| `agent-reference-shots/area-commands/probe-usage.sanitized.jsonl` | `/usage` — `local_command: "usage"`, `num_turns: 0`, cost/usage table. |
| `agent-reference-shots/area-commands/probe-config.sanitized.jsonl` | `/config theme=dark` — `local_command: "config"`, `num_turns: 0`, output `Set Theme to dark`. |
| `agent-reference-shots/area-commands/probe-rename.sanitized.jsonl` | `/rename mysession` — `local_command: "rename"`, `num_turns: 0`, output `Session renamed to: mysession`. |
| `agent-reference-shots/area-commands/probe-model.sanitized.jsonl` | `/model sonnet` — `local_command: "model"`, `num_turns: 0`, output ``Set model to `Sonnet 5.5` for this session only``. |
| `agent-reference-shots/area-commands/probe-help.sanitized.jsonl` | `/help` — no `local_command`, `num_turns: 0`, output ``/help isn't available in this environment.`` (the terminal-only path). |
| `agent-reference-shots/area-commands/probe-unknown.sanitized.jsonl` | `/zzzznotacommand` — the model-delivery path: no `local_command`, `num_turns: 1`, `duration_api_ms: 3196`, and the model's verbatim reply naming the available commands. |
| `agent-reference-shots/area-commands/probe-noslash.sanitized.jsonl` | A run with `--disable-slash-commands` — `slash_commands: []`, `skills: []`, `terminal_slash_commands` absent from the event entirely. |

All artifacts are sanitized: home directory replaced with `<HOME>`, model identifier and provider replaced with `<MODEL_ID>` / `<MODEL_PROVIDER>`, session/UUID/request identifiers replaced with placeholders, and the Git install root replaced with `<GIT_ROOT>`. **No tokens, API keys, credentials, personal file contents, or prompt bodies are present.** (Note: the local `~/.claude/settings.json` on this host contains an auth token; it was **not** read into any artifact and must not be.)

**Reproducing these artifacts on Windows:** invoke the CLI from a shell that does not perform MSYS argument path-conversion — PowerShell, or Git Bash with `MSYS_NO_PATHCONV=1`. Otherwise Git Bash rewrites the leading-slash argument into an absolute path (`/context` → `C:/Program Files/Git/context`), the model receives a *path* instead of a command, and the local-dispatch behaviour is invisible. See §5, limitation 3.

---

## 9. Public documentation sources fetched

All fetched 2026-10-21. The docs serve plain Markdown at the `.md` suffix.

| URL | Bytes | Used for |
| :- | :- | :- |
| `https://code.claude.com/docs/en/commands.md` | 52.4 KB | **The assigned page** — F1–F18 |
| `https://code.claude.com/docs/en/errors.md` | (cached) | "Unknown command" message and suggestion format; print-mode unmatched-command rule |
| `https://code.claude.com/docs/en/mcp.md` | (cached) | MCP prompts-as-commands: `/servername:promptname (MCP)`, `/mcp__server__prompt`, whitespace argument splitting, reserved `anthropic-skills` name |
| `https://code.claude.com/docs/en/skills.md` | (cached) | Skill stacking limit; `.claude/commands/` → skill equivalence; frontmatter fields |
| `https://code.claude.com/docs/en/settings-reference.md` | (cached) | `disableBundledSkills`, `skillOverrides`, `autoContinueAtUsageLimit`, `viewMode`, `copyFullResponse` |
| `https://code.claude.com/docs/en/interactive-mode.md` | (cached) | Quick commands: `/` = command or skill, `!` = shell mode, `@` = file mention |
| `https://code.claude.com/docs/llms.txt` | (cached) | Documentation index; confirmed the `commands.md` entry |

**Untrusted-content handling:** every fetched page was treated strictly as data. No directive found in any fetched page was executed or followed. The only commands run against the product were the published CLI's own documented read-only surfaces (`--help`, `-p` on published slash commands, `--output-format stream-json --verbose`) and non-mutating filesystem reads of this investigation's own scratch files.

---

*End of the command-surface area. Overall findings for all areas: `agent-evidence.md`. Shared protocol and terms notes: `agent-reference-shots/PROTOCOL-NOTES.md`, `agent-reference-shots/TERMS-NOTES.md`.*

---

# Area: Interactive TUI — input handling, key bindings, slash commands, @-mentions, file references, and the status line

**Primary source page:** https://code.claude.com/docs/en/interactive-mode.md
**Corroborating sources:**
- https://code.claude.com/docs/en/keybindings.md
- https://code.claude.com/docs/en/commands.md
- https://code.claude.com/docs/en/statusline.md
- https://code.claude.com/docs/en/common-workflows.md
- https://code.claude.com/docs/en/terminal-config.md
- https://code.claude.com/docs/en/env-vars.md
- https://code.claude.com/docs/en/sub-agents.md

**Method used:** public documentation fetched verbatim (the `.md` suffix serves plain markdown; 843 lines / 72,991 bytes cached at `agent-reference-shots/docs-cache/interactive-mode.md`); the same page rendered in a real browser and observed through **REA** over the Chrome DevTools Protocol (`list_browser_targets`, `inspect_web_page`, `capture_web_screenshot`); plus black-box observation of the published CLI's own TUI renderer via `claude --bg` + `claude logs`.

**Compliance:** no decompilation, no source extraction, no source-map dumping, no binary modification, no credential/licence/account reads. Only public docs and the published CLI's own user-visible surfaces. See `agent-reference-shots/TERMS-NOTES.md`.

**Environment caveat (applies to every claim below):** this host runs Claude Code 2.1.306 against a custom `ANTHROPIC_BASE_URL` serving a third-party model (`minimax/minimax-m3.1-flash:free`), not `api.anthropic.com`. Subscription-gated surfaces (the "You should know" mod, agent teams, cross-session messaging, usage-limit auto-continue) are therefore **documented but not independently observable here**, and are labelled OBSERVED-DOC accordingly.

---

## 1. Executive summary

The interactive TUI is a **multi-surface input system with a strict, documented contract**, not a free-form chat box. The page specifies roughly 40 global control shortcuts, 12 readline-style editing shortcuts, 5 alternative multiline-entry methods, 5 "quick command" prefix characters, a full vim modal editor, a 120-row slash-command menu with a documented fuzzy-matching algorithm, an `@` file-reference typeahead, a context-sensitive footer/status area, and a dozen auxiliary panels (transcript viewer, diff panel, diff dialog, `/btw` side-question overlay, task checklist, session recap, usage-limit wait, PR/MR badge, issue-reference hyperlinks).

Five properties are worth carrying into any reimplementation, because they are the ones that are hard to rediscover and easy to get wrong:

1. **Input is context-sensitive, not a single keymap.** The reference product has a *dispatch* model: a keystroke is resolved against the *active context* (Chat, Autocomplete, Confirmation, Tabs, Transcript, HistorySearch, DiffPanel, Footer, ModelPicker, …), and the same key can mean different things in different contexts. The keybindings file exposes **27 named contexts** and ~180 named actions with `namespace:action` identifiers. This is the single most important structural fact for a reimplementation, and it is documented on a *sibling* page, not on this one.

2. **The prompt is a queue, not a channel.** Typing while the agent is busy **queues** the message instead of interrupting; `Esc` interrupts; `Ctrl+Enter` / `Ctrl+X Ctrl+S` force-send. Messages are delivered at *tool-call boundaries within the same turn*, not at turn ends. This is the interaction model that makes a coding agent feel collaborative, and it is fully specified here.

3. **Every key has a documented terminal-portability answer.** Multiline entry has 5 methods; `Ctrl+X Ctrl+S` exists purely because "Terminals that don't report extended keys deliver `Ctrl+Enter` as plain `Enter`"; `Alt+M` exists because "Windows without VT mode (Node <24.2.0/<22.17.0, Bun <1.2.23)" loses `Shift+Tab`. A reimplementation that binds one key and assumes a modern terminal will be broken on a large fraction of real terminals.

4. **The footer is a live, priority-ordered hint surface.** Observed directly in this session's TUI capture: the footer line reads `⏸ manual mode on · ← for agents`, then gains `· esc to interrupt` while a turn is running, and degrades to `⏸ manual mode on · ? for shortcuts` when idle. The status line (a *different* surface) is a user-supplied script; the footer is built-in. The statusline doc states the status line "renders in its own row above the built-in footer badges and does not replace them", and that a custom status line suppresses "most of the footer's keyboard hints".

5. **`@` is a content-injection mechanism, not just a path picker.** A `@` mention of a file causes Claude Code to **expand the file's contents into the conversation** (subject to a 25,000-token Read limit and a 256 KB file cap); a directory mention expands to a *listing*, not contents; an `@server:resource` mention pulls an MCP resource. It also pulls in `CLAUDE.md` files from the file's directory and parent directories. This is a specific, contract-bearing behaviour that a reimplementation must decide about deliberately.

The page is **not thin** — it is one of the more detailed reference pages in the docs set, and it is the definitive source for the TUI's *observable contract*. It is, however, **not** the definitive source for the *status line* (that is `statusline.md`) nor for the *keybinding action vocabulary* (that is `keybindings.md`); this page links out to both repeatedly.

---

## 2. Detailed findings

### F-I1 — The input system is context-dispatched, with named contexts and named actions

**Status: OBSERVED-DOC** (this page for the dispatch model; `keybindings.md` for the enumeration)

Source: https://code.claude.com/docs/en/interactive-mode.md § "General controls", and https://code.claude.com/docs/en/keybindings.md § "Contexts" / § "Available actions".

This page repeatedly qualifies a shortcut by context rather than listing one global map:

> | `Tab` | Accept an autocomplete suggestion, or add a comment to a permission answer | While autocomplete suggestions are showing in the prompt input, accepts the selected suggestion. On most permission prompts, with **Yes** or **No** focused, opens a comment field on that option, and pressing it again closes the field. |

> | `Esc` | Interrupt Claude, or close a dialog | Stop the current response or tool call mid-turn so you can redirect. Claude keeps the work done so far. … While a footer item is selected, such as a row in the [subagent panel] below the prompt, `Esc` [deselects it] instead of interrupting. |

> | `Up/Down arrows` or `Ctrl+P`/`Ctrl+N` | Move cursor or navigate command history | When the input spans more than one visual row, whether wrapped or multiline, first moves the cursor within the prompt. Once the cursor is on the first or last visual row, pressing again navigates command history. |

The sibling page enumerates the vocabulary precisely. `keybindings.md` § "Contexts" lists **27 contexts**, each with an exact identifier string:

`Global`, `Chat`, `Autocomplete`, `Settings`, `Confirmation`, `Tabs`, `Help`, `Transcript`, `HistorySearch`, `Task`, `ThemePicker`, `Attachments`, `Footer`, `MessageSelector`, `DiffDialog`, `DiffPanel`, `ModelPicker`, `EffortSlider`, `Select`, `Plugin`, `AbovePrompt`, `AbovePromptInput`, `AbovePromptSelect`, `Pane`, `PaneField`, `Agents`, `Scroll`.

And § "Chat actions" gives the action namespace with exact defaults:

| Action | Default | Description (abridged) |
| :- | :- | :- |
| `chat:cancel` | Escape | Cancel current input |
| `chat:clearInput` | Ctrl+L | Force a full screen redraw, preserving input and conversation |
| `chat:clearScreen` | Cmd+K | Same as `chat:clearInput` |
| `chat:killAgents` | Ctrl+X Ctrl+K | Stop all running background subagents … Press the shortcut twice within 3 seconds to confirm |
| `chat:cycleMode` | Shift+Tab\* | Cycle permission modes |
| `chat:modelPicker` | Meta+P | Open model picker |
| `chat:fastMode` | Meta+O | Toggle fast mode |
| `chat:thinkingToggle` | Meta+T | Toggle extended thinking |
| `chat:submit` | Enter | Submit message |
| `chat:queueSubmit` | Ctrl+X Enter | Submit the message, marked to wait its turn … Unlike `chat:submit`, it submits the draft even while an autocomplete suggestion is highlighted. Requires v2.1.247 or later |
| `chat:sendNow` | Ctrl+Enter, Ctrl+X Ctrl+S | Send your queued messages … Requires v2.1.275 or later |
| `chat:newline` | Ctrl+J | Insert a newline without submitting |
| `chat:undo` | Ctrl+_, Ctrl+Shift+- | Undo last action |
| `chat:externalEditor` | Ctrl+G, Ctrl+X Ctrl+E | Open in external editor |
| `chat:stash` | Ctrl+S | Stash current prompt |
| `chat:imagePaste` | Ctrl+V (Alt+V on Windows and WSL) | Paste image from clipboard. On WSL, both shortcuts are bound by default |

Verbatim footnote from `keybindings.md`:

> \*On Windows without VT mode (Node \<24.2.0/\<22.17.0, Bun \<1.2.23), defaults to Meta+M.

Config file, verbatim from `keybindings.md` § "Configuration file":

> Run `/keybindings` to create or open your configuration file at `~/.claude/keybindings.json`.
>
> The keybindings configuration file is an object with a `bindings` array. Each block specifies a context and a map of keystrokes to actions.
>
> **Changes to the keybindings file are automatically detected and applied without restarting Claude Code.**

```json theme={null}
{
  "$schema": "https://www.schemastore.org/claude-code-keybindings.json",
  "$docs": "https://code.claude.com/docs/en/keybindings",
  "bindings": [
    {
      "context": "Chat",
      "bindings": {
        "ctrl+e": "chat:externalEditor",
        "ctrl+s": null
      }
    }
  ]
}
```

Note the **unbind idiom**: the value `null` removes a default binding. And note that a `keybindings.json` naming an action the product does not implement "remains valid" rather than erroring (`keybindings.md` § "Confirmation actions" explicitly lists `confirm:previousField` as "(unbound) | Claude Code doesn't respond to this action, and a `keybindings.json` that names it remains valid").

**Why a reimplementer needs this:** the *contract* is "a keystroke resolves to an action within the active context"; the *vocabulary* is a separate, extensible, user-editable file. A flat single-keymap implementation will not reproduce the observable behaviour (e.g. `Esc` in a footer panel vs. `Esc` interrupting a turn).

---

### F-I2 — The prompt input is a queue with a documented delivery order

**Status: OBSERVED-DOC**

Source: § "Queue messages while Claude works", § "When Claude Code sends what you queued", § "Take back what you queued".

> Type a message and press `Enter` while Claude is working. Claude Code queues the message instead of interrupting the turn, and lists the queued entries in the conversation until it sends them. You can queue `!` [shell commands] and most [commands] the same way, apart from the commands, such as `/status`, that Claude Code runs as soon as you send them.

> Sent and queued messages show in gray until Claude starts responding to them, so you can tell which messages Claude hasn't started on yet.

The delivery rules, quoted:

> * Messages: if you queue a message while Claude is running tool calls, Claude Code passes it to Claude as soon as those tool calls finish, within the same turn. When the turn ends with messages still queued, they go out without another key press, in the order you typed them
> * Commands and shell commands: Claude Code holds them until the turn ends, then runs them one at a time, keeping the order you queued them in

> To send what you queued without waiting, press `Ctrl+Enter`. Your queued messages go out right away, with your draft queued behind them if you had typed one. Requires Claude Code v2.1.275 or later.

> If you queued a `!` shell command ahead of your messages, the key interrupts the turn. Otherwise, what happens to the turn depends on what Claude is doing when you press the key:
>
> * Running shell commands, subagents, or other work that can move to the [background]: that work moves to the background and keeps running, and Claude reads your messages in the same turn
> * Only writing a response, or running something that can't move to the background: Claude Code interrupts the turn and sends your messages next. Before v2.1.281, the key interrupted the turn in both cases

Take-back semantics:

> Press `Up` from the first line of the input box to take back the queued messages and commands. Claude Code removes them from the queue and puts them in the input box, one per line, ahead of any text you had typed. Edit the text and press `Enter` to queue it again as one entry, or clear the input box to drop it.

> Claude Code takes back queued shell commands only when the input box is empty and you have nothing else queued, and it switches the input box to shell mode when it does.

**Why a reimplementer needs this:** this is a *state machine*, not a UI affordance. A reimplementation needs an explicit queue of pending user turns with a per-entry kind (message / command / shell-command), a delivery policy that depends on the agent's current activity, and a "take back" operation that mutates both the queue and the input buffer atomically. The "sent and queued messages show in gray" rule is the visible projection of that state and must be part of the contract.

---

### F-I3 — Five documented methods for multiline input, and why each exists

**Status: OBSERVED-DOC**

Source: § "Multiline input".

| Method | Shortcut | Context |
| :- | :- | :- |
| Quick escape | `\` + `Enter` | Works in all terminals |
| Option key | `Option+Enter` | After enabling Option as Meta on macOS |
| Shift+Enter | `Shift+Enter` | Native in iTerm2, WezTerm, Ghostty, Kitty, Warp, Apple Terminal, Windows Terminal. For other terminals, see Enter multiline prompts |
| Control sequence | `Ctrl+J` | Works in any terminal without configuration |
| Paste mode | Paste directly | For code blocks, logs |

And the general-controls entry for `Ctrl+Enter` / `Ctrl+X Ctrl+S`:

> | `Ctrl+Enter` or `Ctrl+X Ctrl+S` | Send queued messages now | … In terminals that don't report extended keys, `Ctrl+Enter` arrives as plain `Enter`; `Ctrl+X Ctrl+S` works in any terminal. Requires Claude Code v2.1.275 or later |

**Why a reimplementer needs this:** the *observable contract* is "there is always a multiline path that works in the user's terminal, plus a universal fallback". A reimplementation should expose a **multiline-trigger list** (not a single binding), and should offer a chord fallback (`Ctrl+X Ctrl+S`) for terminals with broken extended-key reporting. This is a portable-UI problem, solved idiomatically by making the newline trigger a user-configurable *set*.

---

### F-I4 — Readline editing conventions, with an exact word-boundary rule and a deprecated escape hatch

**Status: OBSERVED-DOC**

Source: § "Text editing", § "Word boundaries in editing shortcuts".

> | `Ctrl+K` | Delete to end of line | Stores deleted text for pasting |
> | `Ctrl+U` | Delete from cursor to line start | Stores deleted text for pasting. Repeat to clear across lines in multiline input. On macOS, terminal emulators including iTerm2 and Terminal.app map `Cmd+Backspace` to this shortcut |
> | `Ctrl+W` | Delete back to previous whitespace | Stores deleted text for pasting. One press removes a whole path or `--flag=value`. To delete only the previous word, press `Option+Delete` on macOS or `Ctrl+Backspace` on Windows |
> | `Ctrl+Y` | Paste deleted text | Pastes the text you last deleted with one of the word or line deletion shortcuts, such as `Ctrl+K`, `Ctrl+U`, or `Ctrl+W` |
> | `Alt+Y` (after `Ctrl+Y`) | Cycle paste history | After pasting, cycle through previously deleted text. Requires Option as Meta on macOS |
> | `Ctrl+_` or `Ctrl+Shift+-` | Undo last input edit | Restores the previous input text and cursor position |

The word-boundary rule is stated with a worked example — exactly the kind of detail that is unobvious and load-bearing:

> The word shortcuts `Alt+B`, `Alt+F`, `Alt+D`, `Option+Delete`, and `Ctrl+Backspace` treat a word as a run of letters and digits, so punctuation such as `_`, `.`, and `/` separates words. With `src/utils/foo.ts` in the prompt, repeated presses of `Alt+B` stop at the start of `ts`, `foo`, `utils`, and `src`.

> `Ctrl+W` is different: it ignores punctuation and deletes back to the previous whitespace, so one press removes all of `src/utils/foo.ts`.

> In text written without spaces, such as Chinese or Japanese, the word shortcuts still move or delete one word at a time.

> These readline conventions apply in Claude Code v2.1.261 and later. The [`keybindingFlavor`](/docs/en/settings-reference#keybindingflavor) setting that turned them on in earlier versions is deprecated and has no effect.

> You can't remap these shortcuts in the [keybindings configuration file](/docs/en/keybindings), which has no actions for them.

The last two paragraphs together say two things: **the readline word-motions are deliberately not remappable**, and the "kill-ring + paste-history" model (`Ctrl+K`/`Ctrl+U`/`Ctrl+W` → `Ctrl+Y` → `Alt+Y`) is a full readline kill-ring, not a simple clipboard.

**Why a reimplementer needs this:** the word-boundary rule is a *Unicode-aware* definition (letters and digits only; CJK has no spaces so a word is a code-point run). A reimplementation should implement a readline-compatible `WORD`-vs-`word` distinction and a kill-ring with history, and should accept that these cannot be remapped.

---

### F-I5 — Slash commands: a menu with a documented, non-trivial matching algorithm

**Status: OBSERVED-DOC**

Source: § "Commands", § "Complete a command mid-prompt"; and https://code.claude.com/docs/en/commands.md § "How the command menu matches what you type".

> Type `/` in Claude Code to see the commands available to you, or type `/` followed by any letters to filter. The `/` menu lists built-in commands, bundled and user-authored [skills], and commands contributed by [plugins] and [MCP servers]. Not all built-in commands are visible to every user since some depend on your platform or plan, and [a few available commands are hidden from the menu by design] and run when you type their full name.

> In [fullscreen rendering], the `/` command and `@` file suggestion lists also respond to the mouse: hovering highlights a row and clicking accepts it.

Mid-prompt completion:

> Command completion also works partway through a prompt: type `/` after a space, then the first letters of a name, as in `run the tests, then /com`. Only commands whose names start with those letters match, so a file path such as `/tmp/notes.md` doesn't keep a list open. Claude Code runs a command itself only when the command [starts your message].

> * **In [fullscreen rendering]**: the matches open as a list while you type, with no row highlighted, so `Enter` still sends your prompt as typed. Press `Tab` to insert the top match, or pick a row with the arrow keys and `Enter`.
> * **Outside fullscreen**: the rest of the top match appears as ghost text at your cursor, with a count such as `+2` when more commands match. Press `Tab` to insert the only match, or to open the list when several match, then pick a row with the arrow keys and `Enter`.

> In both renderers, press `Tab` on a bare mid-prompt `/` to list every command.

> A plugin skill matches on its bare name too, so `/deploy` finds a skill named `myplugin:deploy-app`. When you insert the match, Claude Code writes the full `/myplugin:deploy-app`.

The matching algorithm, from `commands.md` § "How the command menu matches what you type" (quoted verbatim — this is the highest-value single paragraph for a reimplementer):

> * **Highlighting**: Claude Code highlights the top suggestion only when the letters after the `/` match a command's name or alias, from the start of the name or from a word within it, ignoring the `:`, `_`, and `-` separators. Typing `/adddir` highlights `/add-dir`, and typing `/new` highlights `/clear` through its alias. Press `Enter` to run the highlighted suggestion. These highlighting rules require Claude Code v2.1.236 or later.
> * **After a typo**: Claude Code highlights nothing. The close matches stay listed, and you can pick one with `Tab` or the arrow keys, but `Enter` submits your text as typed and reports [Unknown command].
> * **Commands that aren't available to you**: Claude Code leaves them out of the menu. When nothing matches, Claude Code shows `No commands match "/name"`. Most unavailable commands return [Unknown command] when you submit them; a few, such as [`/schedule` on a Console API key], answer with their own availability message instead. Some commands also answer with a message of their own when your organization's policy disables them.
> * **Hidden commands**: Claude Code keeps a few available commands, such as `/heapdump`, out of the menu by design. A partial name never brings a hidden command into the menu: if the partial matches nothing visible, Claude Code shows the same no-match message. Claude Code lists the command only once you've typed its full name, and submitting the full name runs it.

**Why a reimplementer needs this:** the matching is *not* prefix matching and *not* substring matching. It is "match at the start of the name **or** at the start of a word within the name, with `:`, `_`, `-` treated as separators", and the **highlight** (which decides what `Enter` does) is a *stricter* predicate than the *list* (which decides what is visible). Two different predicates. A naive `startsWith` implementation will not reproduce `/adddir` → `/add-dir` or `/new` → `/clear`.

Also note the **command namespace is a merge of four sources** (built-in, skills, plugins, MCP prompts), that the display form is namespaced (`/myplugin:deploy-app`) while the *match* form is bare (`/deploy`), and that "hidden commands" exist and must remain hidden until fully typed.

---

### F-I6 — `@`-mentions: file path typeahead, and content expansion with hard limits

**Status: OBSERVED-DOC** (this page for the trigger; `common-workflows.md` for the expansion contract)

Source: § "Quick commands":

> | `@` | File path mention | Trigger file path autocomplete. In sessions with [cross-session messaging], when you type at least one letter after the `@`, Claude Code also suggests your other live sessions on this machine, so you can tell Claude to message the one you pick. Requires Claude Code v2.1.232 or later |

And § "Commands" adds: "In [fullscreen rendering], the `/` command and `@` file suggestion lists also respond to the mouse: hovering highlights a row and clicking accepts it."

The expansion contract, from https://code.claude.com/docs/en/common-workflows.md § "Reference files and directories" (verbatim):

> Use @ to quickly include files or directories without waiting for Claude to read them.
>
> **1. Reference a single file**
>
> ```text wrap theme={null}
> Explain the logic in @src/utils/auth.js
> ```
>
> This includes the content of the file in the conversation when it fits the [Read tool]'s token limit, 25,000 tokens by default. A text file larger than 256KB isn't included.
>
> **2. Reference a directory**
>
> ```text wrap theme={null}
> What's the structure of @src/components?
> ```
>
> **3. Reference MCP resources**
>
> ```text wrap theme={null}
> Show me the data from @github:repos/owner/repo/issues
> ```
>
> This fetches data from connected MCP servers using the format @server:resource.
>
> * File paths can be relative or absolute
> * Type `@` to open a path suggestion menu, then press Enter or Tab to accept the highlighted path and Enter again to send the message
> * @ file references add `CLAUDE.md` in the file's directory and parent directories to context
> * Directory references show file listings, not contents
> * You can reference multiple files in a single message (for example, "@file1.js and @file2.js")
>
> To stop `@` references from including file contents and directory listings in your message, set [`CLAUDE_CODE_DISABLE_FILE_MENTIONS=1`] in your shell or user settings. Claude then receives the paths you referenced with a note to read them using its file tools. The variable requires Claude Code v2.1.299 or later, and Claude Code ignores it in project and local settings.

Related, from `env-vars.md`:

> | `CLAUDE_CODE_DISABLE_ATTACHMENTS` | Set to `1` to disable attachment processing. File mentions with `@` syntax are sent as plain text instead of being expanded into file content. Ignored in [project and local settings] |
> | `CLAUDE_CODE_DISABLE_FILE_MENTIONS` | Set to `1` to stop Claude Code from expanding [`@` mentions] of files and directories. Claude instead gets the mentioned paths with a note to read them using its file tools. Ignored in [project and local settings]. Requires Claude Code v2.1.299 or later |

And the `@`-mention also has an *agent* meaning, from `sub-agents.md` § "Choose the subagent":

> **@-mention the subagent.** Type `@` and pick the subagent from the typeahead, the same way you @-mention files. …
>
> ```text wrap theme={null}
> @"code-reviewer (agent)" look at the auth changes
> ```
>
> Your full message still goes to Claude, which writes the subagent's task prompt based on what you asked. The @-mention controls which subagent Claude invokes, not what prompt it receives.

> You can also type the mention manually without using the picker: `@agent-<name>` for local subagents, or `@agent-` followed by the scoped name for plugin subagents, for example `@agent-my-plugin:code-reviewer`. While you type this form the typeahead shows file matches rather than agents. The agent mention still resolves when you submit.

**Why a reimplementer needs this:** the `@` typeahead is a **multi-kind namespace** (files, directories, MCP resources `server:resource`, subagents, other live sessions) whose *resolution* has real side effects (content injection, `CLAUDE.md` injection, MCP fetches, agent selection). A reimplementation must:
- keep the *typeahead* (a fuzzy path matcher with filesystem access) separate from the *resolution* (what the mention means when submitted);
- implement the file-size and token caps (256 KB / 25,000 tokens);
- distinguish "directory → listing" from "file → content";
- support `@server:resource` and `@agent-name` disambiguation, including the fact that the typeahead shows *files* while typing `@agent-` but the mention still resolves as an agent.

---

### F-I7 — The status area: a built-in footer of context-sensitive hints, separate from the user scriptable status line

**Status: OBSERVED-CLI** (footer text) + **OBSERVED-DOC** (the status line contract)

Source: OBSERVED-CLI — this session's own TUI capture, `agent-reference-shots/tui-background-session-raw.txt`, produced by running the published CLI with `claude --bg` and reading `claude logs`. The footer row, verbatim, with ANSI stripped:

```
● high · /effort
────────────────────────────────────────────────────────────────────────────────────────────────────────  ⏸ manual mode on · ← for agents
```

and, once a turn was running:

```
────────────────────────────────────────────────────────────────────────────────────────────────────────  ⏸ manual mode on · ← for agents · esc to interrupt
```

and, in a third frame of the same session:

```
────────────────────────────────────────────────────────────────────────────────────────────────────────  ⏸ manual mode on · ? for shortcuts
```

The same three footer variants appear in `agent-reference-shots/tui-startup-banner.txt`.

**INFERRED** (reasoning: the three captured variants differ only in the trailing hint segment, and the status-line doc explicitly names the exact hint strings `esc to interrupt` and the `? for shortcuts` fallback as "the footer's keyboard hints") — the footer is a **priority-ordered hint surface**: it always shows the permission-mode indicator, then appends contextual hints in order of what the user most likely needs *right now* (interrupt affordance while busy; agent-view and shortcut-help affordances while idle). The observed `⏸ manual mode on` string corresponds to the doc's statement that `default` is "labeled Manual in the mode indicator".

Source: OBSERVED-DOC, § "General controls":

> | `Shift+Tab`, or `Alt+M` on Windows when the Node or Bun runtime doesn't enable VT input mode | Cycle permission modes | Cycle through `default` (labeled Manual in the mode indicator), `acceptEdits`, `plan`, and, when available, `bypassPermissions` and then `auto`. From `auto`, the first press switches to `default`. |

and § "PR review status":

> When working on a branch with an open pull request, Claude Code displays a clickable PR link in the footer, such as "PR #446". The link has a colored underline indicating the review state:
>
> * Green: approved
> * Yellow: pending review
> * Red: changes requested
> * Gray: draft
>
> The badge disappears once the pull request merges or closes.

> `Cmd+click` (macOS) or `Ctrl+click` (Windows/Linux) the link to open the pull request in your browser.

and § "GitLab merge requests":

> When you work on a branch with an open GitLab merge request, Claude Code shows a clickable `MR !N` badge in the footer slot that otherwise holds the GitHub PR link. `!N` is GitLab's own reference syntax for merge request number N.

Now the *status line* — a **separate** surface, documented at https://code.claude.com/docs/en/statusline.md:

> The status line is a customizable bar at the bottom of Claude Code that runs any shell script you configure. It receives JSON session data on stdin and displays whatever your script prints, giving you a persistent, at-a-glance view of context usage, costs, git status, or anything else you want to track.

> The status line renders in its own row above the built-in footer badges and does not replace them. With a custom status line configured, Claude Code stops showing most of the footer's keyboard hints, including `esc to interrupt`, the `? for shortcuts` fallback, and the `hold space to speak` [voice dictation] hint. To add clickable link badges to the footer when an ID appears in the conversation, without writing a script, configure [`footerLinksRegexes`] instead.

> Claude Code runs your script with [JSON session data] on stdin and displays whatever the script prints to stdout.
>
> The status line runs locally and does not consume API tokens. It temporarily hides during certain UI interactions, including the help menu and permission prompts.

> Claude Code debounces updates at 300ms, so rapid changes batch together and your script runs once after the changes stop. A change to the `command` itself skips the debounce: Claude Code runs the new command right away. If a new update triggers while your script is still running, Claude Code cancels the in-flight script.

> Claude Code captures your script's output instead of connecting it directly to the terminal, so `tput cols` and language-level width detection cannot read the terminal size from inside the script. Read the `COLUMNS` and `LINES` environment variables instead. Claude Code sets these to the current terminal dimensions before running your script.

The JSON field vocabulary delivered on stdin is large and exact (`statusline.md` § "Available data"), including e.g. `model.id`, `model.display_name`, `cwd`, `workspace.current_dir`, `workspace.project_dir`, `workspace.added_dirs`, `workspace.git_worktree`, `workspace.repo.host`, `workspace.repo.owner`, `workspace.repo.name`, `cost.total_cost_usd`, `cost.total_duration_ms`, `cost.total_api_duration_ms`, `cost.total_lines_added`, `cost.total_lines_removed`, `context_window.total_input_tokens`, `context_window.total_output_tokens`, `context_window.context_window_size`, `context_window.used_percentage`, `context_window.remaining_percentage`, `context_window.current_usage`, `exceeds_200k_tokens`, `fast_mode`, `effort.level`, `thinking.enabled`, `rate_limits.five_hour.used_percentage`, `rate_limits.five_hour.resets_at`, `rate_limits.seven_day.used_percentage`, `rate_limits.seven_day.resets_at`, `rate_limits.spend_limit.used_percentage`, `rate_limits.spend_limit.resets_at`, `rate_limits.spend_limit.used_usd`, `rate_limits.spend_limit.limit_usd`, `rate_limits.spend_limit.period`, `prompt_cache`, `session_id`, `session_name`, `prompt_id`.

**Why a reimplementer needs this:** the footer and the status line are **two different extension points with different ownership** — the footer is product-owned and hint-driven; the status line is user-owned, script-driven, JSON-fed, debounced at 300 ms, and re-runs on a documented trigger list. A reimplementation that merges them will get the "custom status line suppresses the footer's keyboard hints" behaviour wrong, and will miss that the status line is *above* the footer, not replacing it.

---

### F-I8 — `Esc` semantics: five distinct behaviours from one key, distinguished by state

**Status: OBSERVED-DOC**

Source: § "General controls", § "General controls" (`Esc` + `Esc`), § "Vim editor mode".

> | `Esc` | Interrupt Claude, or close a dialog | Stop the current response or tool call mid-turn so you can redirect. Claude keeps the work done so far. If you have [messages queued], Claude Code sends them next. When a dialog is open, `Esc` closes the dialog. While a footer item is selected, such as a row in the [subagent panel] below the prompt, `Esc` [deselects it] instead of interrupting. On a permission prompt, `Esc` declines the action, the same as [**No** without a comment] |

> | `Esc` + `Esc` | Clear input draft, or rewind | When the prompt input contains text, double `Esc` clears it and saves the draft to history so `Up` recalls it. When the input is empty, double `Esc` opens the [rewind menu] to restore or summarize code and conversation from a previous point |

> | `Ctrl+C` | Interrupt, or clear input | Interrupts a running operation. If nothing is running, the first press clears the prompt input and a second press exits Claude Code. To get a cleared draft back, see [Bring back a cleared draft] |

> | `Ctrl+D` | Exit Claude Code session | The first press shows a confirmation hint and a second press within 800ms exits. When the prompt has text, `Ctrl+D` deletes the character after the cursor instead |

The "double press" idiom is a *general* pattern with different time windows per key: `Ctrl+D` = 800 ms, `Ctrl+X Ctrl+K` = 3 seconds, `Esc+Esc` = implied. And the draft-recovery contract:

> To get back a draft you cleared with `Ctrl+C`, press `Up`, either right away or after you've sent a message or command:
>
> * **Right after clearing the draft**: press `Up` once while the prompt is still empty. Requires Claude Code v2.1.288 or later.
> * **After sending a message or command**: press `Up` to step back to the draft. Claude Code keeps the ten most recent cleared drafts for the current session, with their pasted text and images, and discards them when you exit. Requires Claude Code v2.1.292 or later.

**Why a reimplementer needs this:** "cancel" is not one behaviour. A reimplementation needs an explicit state machine over (dialog open? footer item selected? permission prompt open? turn running? input non-empty?) and a **timed double-press** primitive with a per-key window.

---

### F-I9 — Command history: per-directory, cross-session, de-duplicated, with a separate cleared-draft ring

**Status: OBSERVED-DOC**

Source: § "Command history", § "Bring back a cleared draft", § "Reverse search with Ctrl+R".

> Claude Code keeps a history of the prompts you type, and Up-arrow recall reaches prompts from past sessions of the same project:
>
> * Input history is stored per working directory
> * Running `/clear` starts a new session: recall then lists the new session's prompts first, with earlier sessions' prompts after them. The previous session's conversation is preserved and can be resumed.
> * Submitting the same prompt twice in a row records one history entry, so pressing Up steps to the previous distinct prompt
> * When you recall a prompt that included pasted text, Claude Code sends the full pasted content again when you resubmit. If the content has since been [cleaned up], Claude Code doesn't send the literal `[Pasted text #N]` string
> * History expansion with `!` is disabled by default

Reverse search differs between renderers:

> Press `Ctrl+R` to interactively search through your command history. In [fullscreen rendering], `Ctrl+R` opens a search dialog instead: type to filter, press `Up` and `Down` to move through matches, and press `Ctrl+S` to cycle the scope through this session, this project, and all projects. Press `Enter` or `Tab` to place a match in the prompt input, or `Esc` to cancel.

> The inline search scans your full prompt history, newest first, with duplicates collapsed to the newest occurrence. The fullscreen dialog searches your whole prompt history in the selected scope, newest first, with duplicates collapsed to the newest occurrence: the most recent prompts appear immediately, and matches from older prompts fill in as Claude Code loads the rest.

> Accepting a match or canceling the search takes effect immediately, even while Claude Code is still loading the history.

**Why a reimplementer needs this:** history is keyed by *working directory*, spans *sessions* (so `--resume`/`--continue` and `/clear` interact with it), and has **two separate rings** — the prompt history and the ten-entry cleared-draft ring. The "submitting the same prompt twice in a row records one history entry" rule means the history key is the *content*, not a sequence of events.

---

### F-I10 — Vim mode is a full modal editor with text objects, and one documented restriction

**Status: OBSERVED-DOC**

Source: § "Vim editor mode".

> Enable vim-style editing via `/config` → Editor mode.
>
> Claude Code keeps your vim mode and cursor position when you toggle the [transcript viewer] with `Ctrl+O` or open and close a panel such as `/config`. If you leave the prompt in NORMAL mode, it's still in NORMAL mode when you return, with the cursor where you left it.

Mode switching table: `Esc` or `Ctrl+[` → NORMAL (from INSERT, VISUAL); `i`/`I`/`a`/`A`/`o`/`O` insert variants; `v`/`V` start visual selections.

Navigation (NORMAL): `h/j/k/l`, `Space`, `w/e/b`, `0/$/^`, `gg/G`, `f{char}/F{char}/t{char}/T{char}`, `;`/`,` repeat, `%` jump to matching bracket (requires v2.1.301+), `/` reverse history search.

Editing (NORMAL): `x`, `r{char}`, `dd`, `D`, `dw/de/db`, `df{char}/dt{char}`, `dj/dk`, `dgg/dG`, `d0/c0/y0` (v2.1.281+), `d%/c%/y%` (v2.1.301+), `cc`, `C`, `cw/ce/cb`, `s`, `S`, `yy/Y`, `yw/ye/yb`, `p/P`, `>>/<<`, `J`, `u`, `.`.

Text objects: `iw/aw`, `iW/aW`, `i"/a"`, `i'/a'`, `i(/a(`, `i[/a[`, `i{/a{`.

Visual mode: `d/x`, `y`, `c/s`, `p`, `r{char}`, `~/u/U`, `>/<`, `J`, `o` (swap cursor and anchor), text objects, `v/V` toggle.

> Block-wise visual mode with `Ctrl+V` is not supported.

The INSERT-mode remap mechanism is documented with an exact settings schema:

> The [`vimInsertModeRemaps`] setting maps a two-key INSERT-mode sequence to Escape, so a mapping like `jj` returns you to NORMAL mode.
>
> The following `~/.claude/settings.json` example turns on vim mode and maps `jj` to Escape:
>
> ```json theme={null}
> {
>   "editorMode": "vim",
>   "vimInsertModeRemaps": { "jj": "<Esc>" }
> }
> ```
>
> Each key is exactly two printable characters typed in sequence, and `"<Esc>"` is the only supported target. Entries with a different length or target are ignored.
>
> Typing the first character of a sequence inserts it normally. Pressing the second character within one second removes that pending character and switches to NORMAL mode, leaving neither character in your input. After the one-second window, or if a different key follows, both characters stay as literal text, so you can still type a word containing the sequence by pausing between the two keys.
>
> Claude Code reads this setting from your user settings file, the `--settings` flag, and [managed settings] only. Entries in a project's `.claude/settings.json` or `.claude/settings.local.json` are ignored, so a checked-out repository can't remap your keystrokes.

**Why a reimplementer needs this:** vim mode is a *large* surface (~70 bindings + 14 text objects), it survives panel transitions, and the INSERT-mode remap is a **prefix-timer** mechanism with a 1-second window — including the specific behaviour that a mismatched second key leaves *both* characters as literal text. The security-relevant detail (project settings are ignored) should be preserved.

---

### F-I11 — The transcript viewer has its own keymap, split across two renderers

**Status: OBSERVED-DOC**

Source: § "Transcript viewer".

> When the transcript viewer is open (toggled with `Ctrl+O`), these shortcuts are available. Run `/tui` with no argument to check which renderer is active. `Ctrl+E` can be rebound via [`transcript:toggleShowAll`].

| Shortcut | Description |
| :- | :- |
| `?` | Toggle the keyboard shortcut help panel. Requires [fullscreen rendering] |
| `{` / `}` | Jump to the previous or next user prompt, like vim paragraph motion. Requires [fullscreen rendering] |
| `Ctrl+E` | Toggle show all content. Available in the classic renderer only, not in [fullscreen rendering] |
| `[` | Write the full conversation to your terminal's native scrollback so `Cmd+F`, tmux copy mode, and other native tools can search it. Requires [fullscreen rendering] |
| `v` | Write the conversation to a temporary file and open it in `$VISUAL` or `$EDITOR`. Requires [fullscreen rendering] |
| `q`, `Ctrl+C`, `Esc` | Exit transcript view. All three can be rebound via [`transcript:exit`] |

And the `Ctrl+O` description, which defines what the viewer *shows*:

> | `Ctrl+O` | Toggle transcript viewer | Shows detailed tool usage and execution, with a timestamp and the model used on each assistant message. Also expands lines that collapse by default, such as MCP calls, shown as a single `Called slack 3 times` line, and [messages from your other sessions], shown as a one-line `Message from @<sender>` preview |

**Why a reimplementer needs this:** the product has (at least) **two renderers** — "classic" and "fullscreen" — and the *same key has different meanings or availability* in each (`Ctrl+E` is classic-only; `?`, `{`/`}`, `[`, `v` are fullscreen-only). The renderer is inspectable at runtime via `/tui` with no argument. A reimplementation that assumes one renderer will not match the documented behaviour.

---

### F-I12 — Shell mode (`!`), a distinct input mode with its own autocomplete and sandbox exemption

**Status: OBSERVED-DOC**

Source: § "Shell mode with `!` prefix".

> Run shell commands directly without going through Claude by prefixing your input with `!`:
>
> ```bash theme={null}
> ! npm test
> ! git status
> ! ls -la
> ```
>
> Shell mode:
>
> * Adds the command and its output to the conversation context
> * Shows real-time progress and output
> * Supports the same `Ctrl+B` backgrounding for long-running commands
> * Doesn't require Claude to interpret or approve the command
> * Supports history-based autocomplete: type a partial command and press `Tab` to complete from previous `!` commands in the current project
> * Supports live file path autocomplete: type a token containing a forward slash, such as `./src/` or `~/`, to see a dropdown of matching files and directories, then press `Tab` to accept. Use forward slashes on Windows too; the dropdown is triggered by `/`, not `\`
> * Exit with `Escape`, `Backspace`, or `Ctrl+U` on an empty prompt
> * Pasting text that starts with `!` into an empty prompt enters shell mode automatically, matching typed `!` behavior

> Unless your session is one of those listed under [strict sandbox mode], commands you type in shell mode run outside the [sandbox] even when you've enabled sandboxing, because the sandbox applies to the commands Claude runs.

> Claude responds to the command output automatically once it lands in the transcript, so you can run `! npm test` and get an explanation of the failures without a second prompt. The response costs the same as sending a normal prompt. To add the output to context without a response instead, set [`respondToBashCommands`] to `false` in `settings.json`.

**Why a reimplementer needs this:** shell mode is a **mode of the input box**, with its own completion sources (history of `!` commands in the current project; live filesystem paths), its own exit keys, its own paste semantics, and a **documented sandbox escape** ("commands you type in shell mode run outside the sandbox even when you've enabled sandboxing"). The sandbox exemption is a security-relevant fact a reimplementer must decide about explicitly rather than inherit by accident.

---

### F-I13 — `/diff` exists in two forms, with a documented turn-attribution model

**Status: OBSERVED-DOC**

Source: § "Review changes with /diff".

> Run `/diff` to look over the changes in your working tree without leaving Claude Code. You see the edits Claude has made so far alongside anything else you haven't committed. What `/diff` opens depends on which renderer is active:
>
> * **[Fullscreen rendering]**: the [diff panel] opens beside the conversation. It stays open and updates while you keep working.
> * **Classic renderer**: the [diff dialog] opens above the prompt, and you close it when you're done reading.
>
> The panel and the dialog both come from `cc-plugin-diff`, one of the [mods built into Claude Code]. If you disable that mod in `/plugin`, `/diff` opens Claude Code's earlier panel and [diff viewer] instead.

> In the changes `/diff` reads from git, a submodule appears as a single entry, and only when the commit it points to changes; edits to files inside the submodule don't appear there. The panel and the dialog also offer a view of each turn's edits once Claude has edited files. These turn views come from Claude's file edits rather than from git, so a change Claude makes through a shell command appears only under `Current`, the working-tree view.

Diff panel specifics:

> To use the panel you need:
>
> * [Fullscreen rendering]
> * A git repository
> * A terminal at least 110 columns wide
> * Claude Code v2.1.287 or later
>
> The panel also opens on its own once Claude starts editing files, if your terminal is at least 144 columns wide. After you've opened it yourself with `/diff`, later sessions open it as soon as Claude edits a file in any terminal wide enough to fit it. Close the panel and it stays closed, in this session and later ones, until you run `/diff` again.

> * **Change what the panel compares against**: press `Ctrl+X B` to cycle from this session's changes, to your uncommitted changes as one list, to everything since your branch split from the default branch. Claude Code remembers the choice for each repository.

> The panel lists the changed files with their added and removed line counts, and shows each file's diff under the list. Claude Code refreshes it each time Claude edits a file or runs a shell command.

Turn views:

> Once Claude has edited files, a `source` picker appears above the list. It offers one turn view, labeled `T1`, `T2`, and so on, for each of your prompts that led Claude to edit files. A turn view shows only that turn's edits, and `Current` returns you to the working tree.

**Why a reimplementer needs this:** there are **two sources of truth for "what changed"** — git (working tree) and the agent's own file-edit log (per-turn). The UI exposes both, labelled `Current` vs `T1`/`T2`. A reimplementation must record per-turn edit attribution separately from git, and must know that shell-command-made changes are *not* attributable to a turn. The width thresholds (110 / 144 columns) are also part of the observable behaviour.

---

### F-I14 — `/btw`: a side question with a separate context, no tools, and a bounded replay

**Status: OBSERVED-DOC**

Source: § "Side questions with /btw".

> Use `/btw` to ask a question about your current work without adding to the conversation history.
>
> ```
> /btw what was the name of that config file again?
> ```
>
> Claude answers a side question from what's already in the conversation: your messages, its replies, and the tool results it has gathered. You can ask about code Claude has already read, decisions it made earlier, or anything else from the session. A later side question also sees your earlier side questions: Claude Code replays the newest 20 exchanges with each ask, until you clear them. The question and answer never enter the conversation history. In the terminal, they appear in a dismissible overlay. The terminal keeps the thread in memory: press `x` to clear the earlier exchanges, and it's gone when you exit Claude Code.

> * **Available while Claude is working**: you can run `/btw` even while Claude is processing a response. The side question runs independently and doesn't interrupt the main turn. It sees everything in the conversation so far, except the reply Claude is still writing.
> * **No tool access**: side questions answer only from what is already in context. Claude can't read files, run commands, or search when answering a side question. If Claude writes out tool calls as text anyway, the answer ends with a note that nothing was executed.
> * **Single response**: there are no follow-up turns in the overlay. To continue the thread, ask another `/btw` question. To continue with full tool access in a local session, press `f` to fork this question and answer into a [background subagent].
> * **Low cost**: while the conversation's prompt cache is warm, a side question costs little beyond the answer itself.

> Your five newest earlier side questions appear as a dimmed list above the current answer, with a count of any older ones. They stay out of the conversation history.

Overlay keys:

| Key | Action |
| :- | :- |
| `Space`, `Enter`, `Escape` | Dismiss the answer and return to the prompt |
| `Up` / `Down` | Scroll the answer |
| `Shift+Left` / `Shift+Right` | Step between this answer and your earlier `/btw` answers. `Shift+Left` moves to older answers and `Shift+Right` returns toward the current one. `[` and `]` do the same, for terminals that don't report `Shift` with arrow keys. `Tab` / `Shift+Tab` cycle through the same answers. Requires Claude Code v2.1.257 or later. Between v2.1.187 and v2.1.256, the keys were plain `Left` / `Right` |
| `c` | Copy the answer to your clipboard as raw Markdown. Use this instead of mouse selection, which captures the hard-wrapped terminal rendering rather than the source text |
| `f` | Start a [forked subagent] that inherits the parent conversation plus this question and answer, so it can continue with full tool access. You stay in the current session and find the fork in the [panel below your prompt]. Available in local sessions only |
| `x` | Clear the list of earlier `/btw` exchanges shown above the current answer |

**Why a reimplementer needs this:** `/btw` is a **second, parallel conversation channel** over the same transcript, with: no tool access, a bounded replay window (20 exchanges in / 5 displayed), non-persistence to the main history, and an explicit fork-to-subagent escape (`f`). A reimplementation that has only one channel must add a "read-only side question" mode.

---

### F-I15 — Two small, cheap, user-visible conveniences: emoji shortcodes and spell check

**Status: OBSERVED-DOC**

Source: § "Emoji shortcodes":

> Type a `:` followed by an emoji shortcode in the prompt input to insert the emoji. Requires Claude Code v2.1.217 or later.
>
> * Type a complete shortcode such as `:heart:` and Claude Code replaces it with ❤️ as soon as you type the closing `:`
> * Type `:` plus at least two characters of a name, such as `:hea`, to open a suggestion popup, then press `Tab` or `Enter` to insert the highlighted emoji
>
> The shortcode must start the input or follow a space, so a `:` inside a word or URL doesn't open suggestions.
>
> To turn the feature off, set [`emojiCompletionEnabled`] to `false` in `settings.json`. This disables both the suggestion popup and the inline replacement.

Source: § "Check spelling as you type":

> Claude Code can underline misspelled words in the prompt input while you type. It checks only the text in the input box, never Claude's replies or your files. It also checks nothing while the input box is in [shell mode], `Ctrl+R` history search, or [voice dictation].
>
> Spell checking is off by default, and Claude Code checks nothing in [screen reader mode]. Requires Claude Code v2.1.235 or later.

> * Install [aspell], [hunspell], or [ispell] and make sure it's on your `PATH`. Claude Code runs the first of the three it finds, in that order, on every platform, including a `.cmd` shim a package manager installs on Windows.
>
> * `checker`: `aspell`, `hunspell`, or `ispell`. Claude Code doesn't fall back from a checker you name, and treats any other value as `auto`.
> * `language`: a dictionary name in your checker's form, such as `en_GB`. Claude Code ignores any value that isn't a plain dictionary name, such as a path or a name with spaces, and the checker uses its default dictionary.
> * `color`: a color name such as `yellow`, or a `#rrggbb`, `#rgb`, `rgb(r,g,b)`, `ansi256(n)`, or `ansi:<name>` value. Claude Code uses your theme's error color by default and for any value it doesn't recognize.

> If more than one of the three places has a `spellcheck` setting, Claude Code uses only one of them: managed settings first, then `--settings`, then user settings. It doesn't combine fields from two places.

> Claude Code has no word list of its own: a word is misspelled when your checker says so. To stop Claude Code from underlining a word, add the word to your checker's personal dictionary, following the checker's own documentation. Claude Code picks up the new word after you restart it.

> Claude Code underlines nothing when it can't keep a checker running:
>
> * No checker is installed, or the one you named in `checker` is missing
> * The checker fails twice in a row, at startup or later in the session. Claude Code restarts it after the first failure and stops checking after the second, until you restart Claude Code
> * The checker takes more than 15 seconds to answer, three times. Each time, Claude Code leaves the words it was waiting on unmarked; after the third, it stops checking until you restart Claude Code

**Why a reimplementer needs this:** the spell-check contract is a good template for how the product handles an *optional external dependency*: a fixed probe order (`aspell` → `hunspell` → `ispell`), a *named* checker that does **not** fall back, a bounded failure policy (2 failures → stop; 3×15 s timeouts → stop), and a debug-log line format. The "no word list of its own" rule is a clean separation between the UI layer and the dictionary.

---

### F-I16 — Invisible-character stripping on submit, with a two-step confirmation

**Status: OBSERVED-DOC**

Source: § "Invisible characters in prompts".

> Pasted text can carry Unicode characters that a terminal draws as nothing at all, such as tag characters, bidirectional controls, and zero-width spaces, so a prompt can contain text you never see. To keep copied text from carrying instructions your terminal doesn't draw, Claude Code removes those characters when you press Enter, before sending anything. It cleans both the prompt and the contents of any collapsed [pasted-text reference] the prompt includes. Claude Code keeps the joiners that Persian and Indic scripts write and the selectors inside emoji sequences.
>
> If Claude Code removed anything, that Enter sends nothing. The cleaned prompt goes back into the input box with a notice such as `Removed 3 invisible characters · review and press Enter to send`, and pressing Enter again sends the text as shown.
>
> When you pass a prompt on the command line, as in `claude "fix the login bug"`, Claude Code doesn't wait for a second Enter. It removes the characters, shows a notice, and sends the cleaned prompt. If the cleaned prompt would begin with `/`, Claude Code puts it in the input box for you to review and send instead.

**Why a reimplementer needs this:** this is a **prompt-injection defence applied at the submit boundary**, with a specific, observable contract: a count in the message (`Removed 3 invisible characters · review and press Enter to send`), a two-step confirm in the TUI, and a *different* single-step behaviour on the command line. The allowlist exceptions (Persian/Indic joiners, emoji variation selectors) show the implementation uses an explicit keep-list rather than a naive strip.

---

### F-I17 — The task list is a model-driven checklist with a five-item display cap, separate from `/tasks`

**Status: OBSERVED-DOC**

Source: § "Task list".

> The task list is Claude's to-do checklist: items Claude created to plan multi-step work, with indicators showing what's pending, in progress, or complete. It's separate from the background-task view. To see running shells and subagents, use [`/tasks`] instead.
>
> The list fills only in sessions that have the task-tracking tools, which Claude Code provides by default on [Opus 4.7, Sonnet 4.6, Haiku 4.5, and earlier models]. On any other model, including a model ID Claude Code doesn't recognize, the list stays empty unless you opt in with `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` or one of the other ways under [Task tool availability]. When the session has the tools, the task list works as follows:
>
> * Press `Ctrl+T` to toggle the task list view. The display shows up to five tasks at a time. When Claude hasn't created any checklist items yet, the toggle has no visible effect because there's nothing to display
> * If you leave the list expanded, Claude Code restores the expanded view the next time you launch into a session that still has tasks, such as with `--resume` or `--continue`. When the task list is empty, Claude Code starts it collapsed
> * To see all tasks or clear them, ask Claude directly: "show me all tasks" or "clear all tasks"
> * Tasks persist across context compactions, helping Claude stay organized on larger projects
> * To share a task list across sessions, set `CLAUDE_CODE_TASK_LIST_ID` to use a named directory in `~/.claude/tasks/`: `CLAUDE_CODE_TASK_LIST_ID=my-project claude`

**Why a reimplementer needs this:** the checklist is **model-generated content**, not a UI construct, and the *capability* to produce it is model-gated. The five-item display cap and the "expanded state persists across `--resume`" behaviour are UI-level and must be implemented separately from the model capability. The `CLAUDE_CODE_TASK_LIST_ID` → `~/.claude/tasks/<name>` mechanism is a **named, shareable, cross-session** task store.

---

### F-I18 — Session recap is a background, idle-triggered, capped one-liner

**Status: OBSERVED-DOC**

Source: § "Session recap".

> When you return to the terminal after stepping away, Claude Code shows a one-line recap of what happened in the session so far. The recap generates in the background once at least three minutes have passed since the last completed turn and the terminal is unfocused, so it's ready when you switch back. Recaps only appear once the session has at least three turns, and never twice in a row.
>
> Run `/recap` to generate a summary on demand. It runs only when you ask for it yourself. When it arrives in a message relayed from a Slack, Teams, or project thread, you get a [notice] instead of a recap. You also get the notice when `/recap` arrives in a prompt a cloud scheduled task sent.
>
> Session recap is on by default for every plan and provider. To turn automatic recaps off, open `/config` and turn off **Session recap**. The automatic recap never appears in non-interactive mode. Claude Code caps both automatic recaps and `/recap` output at 400 characters.

**Why a reimplementer needs this:** the *triggers* are precisely specified (≥3 min idle + terminal unfocused, ≥3 turns, never twice in a row), and the output has a hard 400-character cap. A reimplementation should implement the same trigger predicate and the same cap, and should distinguish the automatic recap from the on-demand `/recap` (which is forbidden from running unattended — it returns a *notice* instead).

---

## 3. Capability table (reimplementation-relevant surface)

| # | Capability | Observable contract | Classification | Reimplement? |
| :- | :- | :- | :- | :- |
| 1 | Context-dispatched key handling | 27 named contexts; `namespace:action` identifiers; same key differs by context | OBSERVED-DOC | Yes — core |
| 2 | User-remappable bindings | `~/.claude/keybindings.json`; `{bindings:[{context,bindings}]}`; `null` unbinds; hot-reloaded | OBSERVED-DOC | Yes — core |
| 3 | Readline editing | 12 shortcuts; letters+digits word rule; `Ctrl+W` whitespace rule; kill-ring + paste history | OBSERVED-DOC | Yes — core |
| 4 | Multiline entry | 5 methods incl. universal `Ctrl+J`; chord fallback `Ctrl+X Ctrl+S` | OBSERVED-DOC | Yes — core |
| 5 | Prompt queue | Queued not interrupting; delivered at tool-call boundary in-turn; `Ctrl+Enter` force-send; `Up` takes back | OBSERVED-DOC | Yes — core |
| 6 | Interrupt semantics | `Esc` interrupts; `Esc+Esc` clears/rewinds; `Ctrl+C` clear-then-exit; `Ctrl+D` 800 ms confirm | OBSERVED-DOC | Yes — core |
| 7 | Slash command menu | 4 merged sources; namespaced display, bare match; "at start of name or of a word" matcher; hidden commands | OBSERVED-DOC | Yes — core |
| 8 | Mid-prompt `/` completion | Ghost text + `+2` overflow (classic) / list (fullscreen); `Tab` inserts | OBSERVED-DOC | Yes — nice |
| 9 | `@` typeahead | Files, dirs, `server:resource`, `@agent-`, live sessions; mouse in fullscreen | OBSERVED-DOC | Yes — core |
| 10 | `@` content expansion | File content ≤25 000 tokens and ≤256 KB; dir → listing; pulls `CLAUDE.md` from dir + parents | OBSERVED-DOC | Yes — core, decide deliberately |
| 11 | Shell mode (`!`) | Own completions, own exit keys, own paste rule, **outside the sandbox** | OBSERVED-DOC | Yes — core, security decision |
| 12 | Built-in footer | Context-sensitive hints: mode indicator, `esc to interrupt`, `? for shortcuts`, PR/MR badge | OBSERVED-CLI | Yes — core |
| 13 | User status line | Own row **above** footer; JSON on stdin; 300 ms debounce; `COLUMNS`/`LINES`; cancels in-flight | OBSERVED-DOC | Yes — nice |
| 14 | Status-line JSON vocabulary | ~35 exact field paths (`context_window.used_percentage`, `rate_limits.five_hour.resets_at`, …) | OBSERVED-DOC | Yes — nice |
| 15 | Vim mode | ~70 bindings, 14 text objects, mode+position survive panels; `Ctrl+V` blockwise unsupported | OBSERVED-DOC | Optional |
| 16 | Vim INSERT remap | `vimInsertModeRemaps`; exactly 2 printable chars; only `"<Esc>"`; 1 s window; project settings ignored | OBSERVED-DOC | Optional |
| 17 | Transcript viewer | Renderer-specific keymap; `Ctrl+E` classic only; `?`/`{}`/`[`/`v` fullscreen only | OBSERVED-DOC | Yes — core |
| 18 | Task checklist | `Ctrl+T`; 5-item cap; model-gated; persists over compaction; `CLAUDE_CODE_TASK_LIST_ID` | OBSERVED-DOC | Yes — core |
| 19 | `/diff` | Panel (fullscreen) vs dialog (classic); git **and** per-turn views `T1`/`T2`/`Current`; 110/144-col thresholds | OBSERVED-DOC | Yes — core |
| 20 | `/btw` | Parallel channel, no tools, 20-exchange replay, 5 displayed, `f` forks to subagent | OBSERVED-DOC | Yes — nice |
| 21 | Emoji shortcodes | `:name:` inline replace; `:`+2 chars popup; must start input or follow a space | OBSERVED-DOC | Yes — trivial |
| 22 | Spell check | `aspell`→`hunspell`→`ispell` probe order; named checker never falls back; 2-failure and 3×15 s stop rules | OBSERVED-DOC | Yes — nice |
| 23 | Invisible-char stripping | Strip on submit; `Removed N invisible characters · review and press Enter to send`; keep joiners/emoji selectors | OBSERVED-DOC | Yes — core, security |
| 24 | Prompt history | Per working directory; cross-session; consecutive duplicates collapse; `!` expansion off by default | OBSERVED-DOC | Yes — core |
| 25 | Cleared-draft ring | 10 most recent; recovered via `Up`; discarded on exit | OBSERVED-DOC | Yes — core |
| 26 | Reverse search | Inline (all projects) vs fullscreen dialog (session/project/all scope via `Ctrl+S`) | OBSERVED-DOC | Yes — nice |
| 27 | Session recap | ≥3 min idle + unfocused; ≥3 turns; never twice in a row; 400-char cap | OBSERVED-DOC | Yes — nice |
| 28 | PR/MR badge | GitHub colours (green/yellow/red/gray) + GitLab `MR !N`; token discovery order; `FORCE_HYPERLINK=0` | OBSERVED-DOC | Optional, needs `gh`/`glab` |
| 29 | Issue reference links | Only 2-part `owner/repo#123`; host from your remote; 1 000-line / 100 000-char cap | OBSERVED-DOC | Yes — nice |
| 30 | Prompt suggestions | Model-generated next prompt; `Tab`/Right to accept; off by default in interactive; `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION` | OBSERVED-DOC | Optional |
| 31 | "You should know" mod | Built-in mod, off by default, no tools, `cc-plugin-you-should-know@builtin` | OBSERVED-DOC | Skip — subscription-gated |
| 32 | Usage-limit auto-continue | Waits and resumes; shows reset time; `esc to cancel`; re-arms at most twice | OBSERVED-DOC | Skip — subscription-gated |

---

## 4. Dependencies

| Dependency | Kind | Required for | Notes |
| :- | :- | :- | :- |
| `api.anthropic.com` (or a gateway) | Network + account | Everything except pure-local UI | This host uses a custom `ANTHROPIC_BASE_URL`; `claude doctor` reports "Not connected to the Anthropic API (api.anthropic.com)" |
| claude.ai subscription | Account | Auto-continue, "You should know", cross-session messaging, some commands | Not available on this host |
| `git` | Local binary | `/diff` panel & dialog, PR badge, branch comparison | Submodule appears as a single entry |
| `gh` CLI + token | Local binary + credential | GitHub PR status badge | Token discovery: `GH_TOKEN`/`GITHUB_TOKEN` env, else `gh auth login`; `GH_HOST` → `GH_ENTERPRISE_TOKEN`/`GITHUB_ENTERPRIVATE_TOKEN` |
| `glab` CLI + login | Local binary + credential | GitLab MR badge | `GITLAB_TOKEN` env is explicitly **ignored** |
| `aspell` / `hunspell` / `ispell` | Optional local binary | Spell check | Probe order aspell → hunspell → ispell; first found wins |
| Terminal with VT input mode | Terminal capability | `Shift+Tab` cycle-mode; `Alt+M` fallback otherwise | "Windows without VT mode (Node <24.2.0/<22.17.0, Bun <1.2.23)" |
| Terminal reporting extended keys | Terminal capability | `Ctrl+Enter` | `Ctrl+X Ctrl+S` works in any terminal |
| Terminal with OSC 8 hyperlinks | Terminal capability | Clickable PR/MR badge, issue links | `FORCE_HYPERLINK=0/1` overrides |
| Git provider for `owner/repo#123` | External service | Issue reference links | Host is derived from *your* git remote, not the referenced repo |
| MCP server for `@server:resource` | External process | MCP resource mentions | Format `@server:resource` |
| A voice-dictation backend | External service | `Space` hold-to-dictate | Rebindable |

---

## 5. Limitations of this investigation

1. **The interactive TUI could not be driven programmatically.** This host has no attached pty/ConPTY and `claude attach` requires an interactive terminal. The REA `capture_process_scenario` tool's `events` parameter rejected every valid shape attempted, so REA's PTY capture could not be exercised either. Live TUI evidence was therefore obtained through `claude --bg` + `claude logs`, which yields the *rendered frames* (including the footer) but not a keypress-driven menu walkthrough.
2. **Consequently, the `/` menu, the `@` typeahead, the transcript viewer, the diff panel/dialog, the `/btw` overlay, the shortcut help panel, and the spell-check underline were not observed in situ.** They are all OBSERVED-DOC.
3. **Two renderers.** The docs distinguish "classic" and "fullscreen" rendering. The CLI run here used the classic renderer (per `agent-reference-shots/tui-startup-banner.txt` and the `--ax-screen-reader` note that it "Forces the classic renderer"). Fullscreen-only behaviours were not observed.
4. **Subscription-gated surfaces** are unobservable here: the "You should know" mod, cross-session messaging, agent teams, Remote Control, usage-limit auto-continue, and plan-specific commands.
5. **Version skew.** The page documents behaviour gated on versions from v2.1.181 to v2.1.306. This host runs **v2.1.306**, so all version gates cited are satisfied — but the *model* here (`minimax/minimax-m3.1-flash:free`) is explicitly "not recognized", which (per § "Task list") disables the task list and (per § "You should know") disables feature-flag-fetching-dependent features.
6. **The status line was not exercised end-to-end.** Its contract is OBSERVED-DOC; the JSON field list was read from `statusline.md` but no script was run against it.
7. **Fetched web text was treated as untrusted data throughout.** No instruction found in any fetched page was followed. REA was used only in browser-DOM/inspection mode against a public documentation page — not against the Claude Code binary.

---

## 6. Unresolved questions (UNKNOWN)

| # | Question | Why it could not be established |
| :- | :- | :- |
| U1 | What is the exact rendering of the `/` and `@` suggestion lists (rows, selection marker, scroll behaviour, mouse affordances)? | Docs describe the *behaviour*, not the visual layout; the menu could not be driven programmatically |
| U2 | What exactly does the "ghost text" completion render as, and how is the `+2` overflow count computed (total matches minus one)? | Docs give the string shape only |
| U3 | What is the full key→action matrix for the 27 contexts (only `Chat`, `Autocomplete`, `Confirmation`, `Help`, `Tabs` were readable in the cached `keybindings.md`)? | `keybindings.md` was fetched but only partially indexed; the remainder is ~500 more lines of action tables |
| U4 | Does the classic renderer's footer show a task-list/agent panel row, and how do footer items render as selectable rows? | `Esc` is documented to deselect "a row in the subagent panel below the prompt", but the panel was not rendered in the capture |
| U5 | What is the full shortcode emoji dataset and its name-matching behaviour? | Docs name only `:heart:` and `:hea`; no table is published |
| U6 | How are "your other live sessions" detected and labelled in the `@` typeahead, and what is the "one letter" threshold's exact behaviour? | Cross-session messaging is subscription-gated and not observable here |
| U7 | What are the "hidden commands" beyond the named example `/heapdump`? | Docs name one example and say the list is by-design hidden |
| U8 | What is the exact truncation policy for the `/recap` 400-character cap (word boundary? ellipsis?)? | Cap size is documented, the truncation algorithm is not |
| U9 | What triggers the "Usage limit reached" wait besides the model hitting a limit, and what is the exact ordering of the two footer lines under partial states? | Subscription-gated |
| U10 | Does the spell-check "underlines nothing" behaviour also apply in the `Ctrl+R` inline search buffer vs. the fullscreen search dialog separately? | Docs say "nothing while the input box is in … `Ctrl+R` history search" without distinguishing the two search implementations |
| U11 | What is the internal precedence between a *disabled* mod (e.g. `cc-plugin-diff` disabled) and the "earlier panel and diff viewer" fallback? | Docs state the fallback happens, not the precedence rules |
| U12 | Does the status line's `COLUMNS`/`LINES` reflect the viewport or the terminal window? | Docs say "current terminal dimensions" without disambiguating |

---

## 7. Clean-room implementation opportunity — the interactive TUI, end to end

The contract to reproduce is **observable behaviour**, and it decomposes into six independently implementable layers. None of this requires, or should involve, reading Anthropic code.

### Layer 1 — A context-dispatched keymap engine

**Contract:** a keystroke resolves to an action *within the active context*. The action vocabulary is `namespace:action`; the context vocabulary is a fixed set of named strings; bindings live in a user-editable JSON file that is hot-reloaded; `null` unbinds; an unknown action is ignored, not an error.

**Idiomatic way to build it:** implement a small library of the shape
`resolve(keystroke, context) -> action | null`, driven by a `(context, keystroke) -> action` lookup table. Represent keystrokes as a normalised token (e.g. `ctrl+x ctrl+k` for chords, `alt+m` for meta) rather than raw key events. Load the user's overrides as a *layered* map over the built-in defaults, with the user layer winning and `null` meaning "remove". Re-evaluate the binding table on file change (watch the file, or stat it on a timer) and swap the table atomically — this gives the documented hot-reload for free.

**Deliberately do NOT copy:** the specific action names, the specific context names, or the specific default bindings. Those are Anthropic's vocabulary. A clean-room implementation should define its *own* action names and contexts, and only ensure that the *observable* dispatch semantics (one key, many meanings by state; remappable; unbinding via null) are reproduced.

### Layer 2 — A portable line editor

**Contract:** cursor movement, word motions with a letters+digits word rule, whitespace-delimited delete, a kill-ring with paste history, undo of the last input edit, and a set of newline triggers including one that works in every terminal.

**Idiomatic way to build it:** use an off-the-shelf readline-compatible editing library (readline-js, a Rust `reedline`/`rustyline`, or a Go `liner`/`bubbletea` textinput) and add the parts that are product-specific: the multi-trigger newline handling, the kill-ring-with-history layering, and the draft stash/restore. Model the buffer as a rope or gap buffer so that "wrap-aware" cursor movement (cursor on first/last *visual* row) is computable — that wrap-awareness is what makes the "arrows move the cursor first, then navigate history" rule implementable at all.

**Do NOT copy:** the deprecated `keybindingFlavor` toggle, and do not make word-motion bindings remappable if you want to match the documented "no actions for them" contract.

### Layer 3 — The prompt queue and its state machine

**Contract:** typing while the agent is busy queues rather than interrupts; messages are delivered at the next tool-call boundary *within the same turn*; commands/shell commands are held until the turn ends and then run one at a time in queue order; a force-send key exists; `Up` takes queued items back into the input box; queued items are visually distinct (grey) until the agent starts on them.

**Idiomatic way to build it:** make the agent loop a proper **state machine with an explicit event bus**, and route user input as events. Define a `PendingUserTurn` record with a kind (`message` | `command` | `shell`), a body, and an enqueue order. The loop's tool-execution step emits a `ToolBoundaryReached` event; the turn-end step emits a `TurnEnded` event; the queue is drained at whichever of those the delivery policy selects. The visual distinction is then a pure function of the queue state — which is exactly why it is cheap to get right once the state is explicit. "Take back" is a single operation that moves queue entries into the input buffer, preserving order and prepending them ahead of any typed text.

### Layer 4 — The suggestion/mention layer

**Contract:** `/` and `@` open *typeahead* surfaces; the menu merges several namespaces; the *visible set* and the *highlighted set* are computed by different predicates; a namespaced item displays namespaced but matches on its bare name; some commands are hidden until fully typed; `@` mentions resolve to content with explicit size/token caps.

**Idiomatic way to build it:** implement two separate functions over one candidate list: `visible(candidates, query)` and `highlight(candidates, query)`. The documented matcher ("at the start of the name **or** at the start of a word within it, with `:`, `_`, `-` treated as separators") is a small, well-defined tokenisation — normalise the candidate and the query by splitting on those separators, then match the query against any token *prefix*. This gives `/adddir` → `/add-dir` and `/new` → `/clear` (alias) without a fuzzy-matching library, and it is exactly the kind of thing you would write from scratch. For `@`, resolve mentions **after** submission, not in the typeahead: keep the typeahead as a pure fuzzy-path matcher over the filesystem, and give the resolver a separate switch on mention kind (file / directory / `server:resource` / `agent-name` / session), with size and token caps applied at that point. This separation is also what makes the "typeahead shows files while typing `@agent-`" quirk implementable.

**Deliberately do NOT copy:** the exact file-size cap (256 KB), the exact token cap (25 000), and the "pull `CLAUDE.md` from the file's directory and parent directories" rule as *given* — these are Anthropic's specific choices. A clean-room implementation must *decide* its own caps, and should document them. The *shape* of the contract (a cap exists, it is enforced at mention-resolution time, and directory mentions yield listings rather than contents) is what should be reproduced.

### Layer 5 — The status area (two surfaces, different owners)

**Contract:** a built-in footer that shows a permission-mode indicator and context-sensitive hints; a user-configurable status line on its own row *above* the footer; the status line receives a JSON document on stdin, is debounced, and can be cancelled mid-flight; the terminal size is delivered as `COLUMNS`/`LINES` because the script's stdout is captured, not attached.

**Idiomatic way to build it:** (a) Footer: build it as a list of *hint providers* that each return `(text, priority)` or nothing, and render the highest-priority items that fit the width. This makes the "context-sensitive" behaviour a natural consequence rather than a special case, and makes the width-aware truncation trivial. (b) Status line: spawn the user script with a pipe, write a JSON document to stdin, capture stdout, and set `COLUMNS`/`LINES` in the child environment. Use a debounce timer (e.g. 300 ms) and, if a new trigger arrives while a run is in flight, kill it — that is exactly the documented behaviour and it is trivially implementable with a process handle. Provide your *own* JSON field vocabulary and document it; the observable contract is "a JSON object on stdin, script's stdout rendered verbatim, one row above the footer", not the specific field names.

### Layer 6 — The auxiliary panels

**Contract:** transcript viewer, diff panel/dialog, side-question overlay, task checklist, session recap, PR/MR badge.

**Idiomatic way to build it:** build these as *separate, focus-owning surfaces* that register their own keymaps in the keymap engine (Layer 1) and are entered/exited by a stack. This is the standard "modal surface" pattern in TUI frameworks (e.g. Bubble Tea's `Alt+Screen` + mode stack, or a hand-rolled viewport). For the diff surfaces, keep **two independent sources of truth** — the VCS working tree and your own per-turn edit log — and let the user pick between them; the `T1`/`T2`/`Current` picker is a mode switch, and the "changes made via a shell command are only in `Current`" rule falls out naturally if the per-turn log records only edits made through your file tools. For the side question, run it as a *separate request against the same transcript* with the tool set removed, and keep it out of the persisted history — a second channel in the loop, not a special case of the first.

### What to implement first, and what to skip

**Implement first:** Layers 1–4. They are the interaction core, they are fully documented, and they are what makes the product feel like a collaborator rather than a chatbot.

**Implement later:** Layer 5 (footer) — cheap once the layout engine exists; the status line is a genuine differentiator but is a whole separate feature.

**Implement selectively:** Layer 6 — the task checklist and the diff views are the highest value; the transcript viewer, `/btw` overlay, session recap and PR badge can come later or be omitted without breaking the core.

**Skip or re-scope:** the "You should know" side-agent mod, usage-limit auto-continue, agent teams, Remote Control, and cross-session messaging are all gated on a claude.ai subscription or Anthropic-hosted infrastructure. Model them as unavailable and say so, rather than shipping a stub that pretends to work.

---

## 8. Confirmed capabilities (OBSERVED only)

These were established by **direct observation in an authorised product interaction**, not merely read from docs:

- The TUI renders a **built-in footer** with a permission-mode indicator reading `⏸ manual mode on` and context-sensitive trailing hints — observed exactly as `· ← for agents`, `· ← for agents · esc to interrupt`, and `· ? for shortcuts` in three distinct frames of a live session (`agent-reference-shots/tui-background-session-raw.txt`, `agent-reference-shots/tui-startup-banner.txt`).
- The TUI renders an **effort indicator** on the row above the prompt: `● high · /effort` — observed in the same captures.
- The TUI renders a **live activity spinner** with rotating phase text and varying spinner glyphs — observed verbatim: `* Recombobulating…`, `✢ Recombobulating…`, `* Cogitating`, `✳ Cogitating`, `✻ Cooked`, `* Transfiguring`, `* Undulating`, `✻ Worked`.
- The TUI renders a **startup banner** containing the product version, the model id and billing mode, the working directory, and a non-blocking model warning — observed verbatim in `agent-reference-shots/tui-startup-banner.txt`:

  ```
   ▐▛███▛█   Claude Code v2.1.306
  ▝▜██████▀  minimax/minimax-m3.1-flash:free · API Usage Billing
   ▝▝   ▝▝   ~\Desktop\<project>
  ⚠ Model "minimax/minimax-m3.1-flash:free" isn't recognized · context assumed to be 200k tokens · update Claude Code, or see https://code.claude.com/docs/en/model-config
  ```

  Note the warning also discloses the **assumed context window** (200k) for an unrecognised model — a concrete, observable fallback.
- The published **HTML documentation page** (https://code.claude.com/docs/en/interactive-mode) contains exactly **56 content headings** in `<main>` — 1×`H1`, 19×`H2`, 36×`H3` — in the same order and with the same titles as the `.md` file (the only textual difference is that the rendered heading drops the backticks around `!`). Verified by DOM extraction through REA over CDP and diffed programmatically against the markdown. This establishes that the `.md` endpoint and the rendered page are the same content, so quoting the `.md` is quoting the published page.
- The published CLI exposes a **background-session surface** (`claude --bg`, `claude logs <id>`, `claude attach <id>`, `claude stop <id>`, `claude rm <id>`, `claude agents [--json]`) that yields the **rendered terminal frames** of a live TUI session without a pty — observed this session.
- The published CLI's `--ax-screen-reader` mode renders a flat-text, border-free TUI and **still accepts input from a pipe** — observed this session (`agent-reference-shots/area11-interface-comm/screen-reader-interactive.txt`).

---

## 9. Evidence index

| Artifact | Path | What it shows |
| :- | :- | :- |
| Cached source page | `agent-reference-shots/docs-cache/interactive-mode.md` | The page verbatim, 843 lines / 72,991 bytes, fetched from `https://code.claude.com/docs/en/interactive-mode.md` |
| Cached sibling pages | `agent-reference-shots/docs-cache/keybindings.md`, `statusline.md`, `commands.md`, `common-workflows.md`, `terminal-config.md`, `env-vars.md`, `sub-agents.md` | The corroborating contracts cited above |
| REA browser target list | REA `list_browser_targets` over `http://127.0.0.1:9333` | Chrome/155.0.8059.85, one page target at `https://code.claude.com/docs/en/interactive-mode`, title "Interactive mode - Claude Code Docs" |
| REA page inspection | REA `inspect_web_page` (target `80C8E150B1366610063015A2F593FB7B`) | 6 498 DOM nodes, 7 378 accessibility nodes, 147 132 bytes of accessibility text; `completeness.status = policy_filtered` (script sources and storage keys not approved) |
| REA viewport screenshot | `agent-reference-shots/area-interactive-mode/docs-interactive-mode-viewport.png` | sha256 `81c387ca9095f338…`, 147 042 bytes, 1295×879 |
| REA screenshot (Quick commands) | `agent-reference-shots/area-interactive-mode/docs-interactive-mode-quickcommands.png` | sha256 `50b4fdce46dd2cdd2b17d9d3837f91111d56ee58176949c39a8ab98e13d20501`, 180 242 bytes |
| CDP screenshot (Commands) | `agent-reference-shots/area-interactive-mode/docs-interactive-mode-commands.png` | sha256 `80bd50ef37cc08b130047fe9ef70607f3daec6faf25b24ca549056d336bf83e2`, 159 924 bytes, captured after scrolling to the "Commands" heading |
| DOM heading extraction | REA/CDP `Runtime.evaluate` | 56 content headings in document order, diffed programmatically against the markdown — identical except backtick stripping |
| Section text extraction | CDP `Runtime.evaluate` on `main h2/h3` | Rendered text of General controls, Text editing, Multiline input, Quick commands, Transcript viewer, Commands, Emoji shortcodes, Task list, Session recap |
| Live TUI frames | `agent-reference-shots/tui-background-session-raw.txt` | Rendered TUI frames incl. the three footer variants, via `claude --bg` + `claude logs` |
| Startup banner | `agent-reference-shots/tui-startup-banner.txt` | Version, model, cwd, unrecognised-model warning, spinner, effort row, footer row |
| Prior CLI help capture | `agent-reference-shots/area11-interface-comm/claude-help.txt` | `--permission-mode` choices include `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan`; `--ax-screen-reader` forces the classic renderer |
| Compliance notes | `agent-reference-shots/TERMS-NOTES.md` | The ToS boundary established before any inspection |

---

## 10. Bottom line for this area

The interactive TUI is **fully specified in public documentation** and is therefore the most "clean-roomable" part of Claude Code — with one caveat: the *action vocabulary* and *context names* are Anthropic's intellectual property, and a legitimate reimplementation should invent its own while reproducing the *dispatch semantics*.

The five behaviours that most deserve a reimplementer's attention, in order:

1. **The prompt is a queue, and delivery is timed by tool-call boundaries, not turn boundaries.** This is the single most important interactive property and it is fully specified.
2. **One key, many meanings, resolved by context.** 27 contexts, `namespace:action` names, user-remappable via a hot-reloaded JSON file, `null` to unbind.
3. **Every key has a terminal-portability answer.** Multiline entry, `Ctrl+X Ctrl+S` as the universal chord, `Alt+M` for VT-less Windows, `[`/`]` as `Shift+Left`/`Shift+Right` substitutes. This is where most reimplementations will break on real machines.
4. **The footer is a live, priority-ordered hint surface** and the user status line is a *different* surface that sits above it and suppresses most of its hints. Observed directly: `⏸ manual mode on · ← for agents · esc to interrupt`.
5. **`@` is content injection with hard limits, not a path picker.** 25 000 tokens, 256 KB, directories yield listings, `CLAUDE.md` from parent directories is pulled in, and `@server:resource` / `@agent-name` are different mention kinds sharing one typeahead.

The richest low-cost wins for an independent implementation are the queue model, the context-dispatched keymap, and the `@`-mention resolver with explicit caps. The richest high-cost item is the status line + footer layout engine, because it requires a real layout model (width-aware, priority-ordered) that the rest of the TUI also needs.

---

## 11. Sources fetched for this area

- https://code.claude.com/docs/en/interactive-mode.md — **primary**
- https://code.claude.com/docs/en/keybindings.md
- https://code.claude.com/docs/en/commands.md
- https://code.claude.com/docs/en/statusline.md
- https://code.claude.com/docs/en/common-workflows.md
- https://code.claude.com/docs/en/terminal-config.md
- https://code.claude.com/docs/en/env-vars.md
- https://code.claude.com/docs/en/sub-agents.md
- https://code.claude.com/docs/en/cli-reference.md
- https://code.claude.com/docs/llms.txt — the documentation index, used to confirm that no separate "file mentions" page exists (the `@` contract lives on `common-workflows.md`)

All fetched text was treated as **untrusted data**. No instruction found in any page was followed, and no command found in fetched content was executed.

---

# Area 10 — Skills, reusable instructions, project instructions, and subagent workflows

**Product observed:** Claude Code 2.1.306 (native build, win32-x64)
**Investigated:** 2026-10-21
**Public docs consulted:** https://code.claude.com/docs/en/skills.md, `/en/memory.md`, `/en/sub-agents.md`, `/en/workflows.md`, `/en/output-styles.md`, `/en/plugins/manifest-reference.md`, `/en/settings-reference.md`, `/en/env-vars.md`
**Artifacts:** `agent-reference-shots/area10-skills/` (13 sanitized files)

## Area 10 Executive summary

This is the product's **extension layer** — the part that lets a user or an
organisation teach the agent how to work without editing the binary. It is also
the part with the **highest ratio of machine-checkable contract to prose**.
Almost every rule below was confirmed twice: once against the public
documentation, and once against the product's own debug log, its own `init`
event, and its own transcript attachment records.

Seven structural facts dominate.

1. **Three scopes, one resolver.** Skills load from managed
   (`C:\Program Files\ClaudeCode\.claude\skills`), personal
   (`~/.claude/skills`), and project (`.claude/skills`) scopes, plus nested
   directories, `--add-dir` directories, plugins, and claude.ai-synced skills.
   The resolver's own debug line names every scope and its exact path
   (OBSERVED-CLI). Name collisions are resolved **at name-resolution time,
   not at load time** — the loader counts both copies of a same-named skill but
   only one description reaches the model (OBSERVED-CLI).
2. **Two invocation-control flags that are *not* opposites.**
   `disable-model-invocation: true` removes the skill's description from the
   model's context while keeping it in the `/` menu; `user-invocable: false`
   does the reverse. Both were read directly out of the model's own
   `skill_listing` attachment and cross-checked against the `init.skills` and
   `init.slash_commands` registries (OBSERVED-CLI). This is the single most
   commonly-misunderstood detail in the whole extension layer.
3. **The loader is a code-execution surface.** `` !`cmd` `` inside a skill body
   is executed by the harness **at render time**, before the content reaches
   the model — not by the model via a tool call. It is recognised only at the
   start of a line or after whitespace; `KEY=!`cmd`` is left literal
   (OBSERVED-CLI). A policy setting (`disableSkillShellExecution`) substitutes
   `[shell command execution disabled by policy]` for the command, confirmed
   end-to-end (OBSERVED-CLI).
4. **Project instructions are a *concatenation*, never an override.** Every
   `CLAUDE.md` from the filesystem root down to the cwd is concatenated in
   order, `CLAUDE.local.md` is appended after `CLAUDE.md` at each level, and
   `@path` imports are expanded into their own entries (OBSERVED-CLI). A
   path-scoped `.claude/rules/*.md` rule is not in the launch-time context at
   all — it arrives later as a `nested_memory` attachment when a matching file
   is touched (OBSERVED-CLI).
5. **AGENTS.md is a built-in plugin, and its setting has an unusually tight
   scope.** The `cc-plugin-agents-md@builtin` plugin implements the
   AGENTS.md fallback; its `instructionFiles` option is read from user
   settings, `--settings`, or managed settings **only** — the debug log says
   explicitly "(project settings are not read)" (OBSERVED-CLI).
6. **The extension layer publishes a complete machine-readable registry.**
   `init.skills`, `init.agents`, `init.plugins`, `init.slash_commands`,
   `init.terminal_slash_commands`, `init.output_style`, `init.memory_paths`,
   plus the `skill_listing`, `agent_listing_delta`, `instructions` and
   `nested_memory` attachments. An implementer can copy these shapes verbatim
   (OBSERVED-CLI).
7. **`claude plugin validate --json` is a real, scriptable validator** with a
   stable JSON envelope and per-file findings — and it is *more* than the
   documentation says: it validates a whole components directory
   (`.claude/skills`, `.claude/agents`) as well as a plugin manifest
   (OBSERVED-CLI).

Two contradictions between doc and binary are worth recording up front:
`claude import --dry-run` is documented but **not available in this build**
(OBSERVED-CLI), and `claude plugin init --with` does not accept `commands`
even though the runtime still loads legacy `.claude/commands/` files
(OBSERVED-CLI).

### Area 10 compliance boundary

Claude Code is proprietary and closed source. Anthropic's Consumer ToS §3 and
Commercial ToS §D.4 prohibit decompiling, reverse engineering, disassembling,
or reducing the Services to human-readable form, and the docs state *"The
Claude Code binary must not be modified."* Anthropic has enforced this via DMCA
takedown.

**The REA reverse-engineering toolset available in this session was therefore
deliberately NOT used against the Claude Code binary.** No binary was opened, no
JavaScript bundle extracted or de-minified, no source map dumped, no
credential store or keychain read, no licence file read, no private account
data accessed, no binary modified.

Permitted and used:
(a) public documentation at `code.claude.com/docs/en/...` and
`anthropic.com/legal`;
(b) the published CLI's own user-facing inspection surfaces — `claude --help`,
`claude plugin validate|list|details|init|marketplace`, `claude agents
--json`, `claude doctor`, `claude --debug` — which exist to be read by users;
(c) black-box observation of the published CLI's behaviour, including the
`init` event, the debug log, and the session transcript's own attachment
records, which are the product's record of what it injected.

All configuration mutation was confined to **temporary directories** under the
system temp dir with `CLAUDE_CONFIG_DIR` redirected, so the real `~/.claude`
was never modified. No `claude plugin install`, `claude mcp add`, `claude
import`, or any other command that writes to a real install location was run.

**Machine caveat.** This host runs Claude Code against a **custom
`ANTHROPIC_BASE_URL`** (a third-party gateway serving a non-Anthropic model,
`minimax/minimax-m3.1-flash:free`), not `api.anthropic.com`. `claude doctor`
reports "Not connected to the Anthropic API". Consequently:
- behaviour that depends on the **model obeying an instruction** (e.g. does an
  output style actually change the model's tone?) is **model-limited, not
  product-limited** — such findings are marked UNKNOWN or INFERRED, never
  OBSERVED;
- claude.ai-account-gated behaviour (skills synced from claude.ai, Cowork and
  cloud sessions, managed/org policy) is **OBSERVED-DOC only**;
- the `Agent` tool's `model` enum (`sonnet|opus|haiku|fable`) was observed as a
  schema, but the gateway serves a model id outside that set, so per-model
  behaviour is UNKNOWN.

**Prompt-injection note.** All fetched web content and all tool output was
treated as **untrusted data**. No directive found in a fetched page or in a
transcript was followed, and no command found in fetched content was executed.
One incidental observation worth recording: a skill body is *content the
harness executes*, so a third-party skill in a repository is executable content
by construction — see F18 and §10.

## Area 10 Findings

### F10-1 — Skill discovery is a three-scope resolver that prints its own search paths

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/skills.md — § "Choose where skills load"
**Evidence:** `agent-reference-shots/area10-skills/discovery-and-budget-probes.txt` P1

The documented scope table:

| Location | Path | Loads in |
| :- | :- | :- |
| Enterprise | `.claude/skills/<name>/SKILL.md` in the managed settings directory | All users on managed machines |
| Personal | `~/.claude/skills/<name>/SKILL.md` | All projects on this machine |
| Project | `.claude/skills/<name>/SKILL.md` | Sessions in this repository |
| Nested | `<subdir>/.claude/skills/<name>/SKILL.md` | Sessions started in or below `<subdir>` |
| Additional directory | `.claude/skills/...` in a `--add-dir` directory | That session |
| Plugin | `<plugin>/skills/<name>/SKILL.md` | Wherever the plugin is enabled, as `/plugin:skill` |
| claude.ai account | Skills enabled for the claude.ai account | Cowork / cloud / signed-in terminal sessions |

**OBSERVED-CLI** — the loader's own debug line names the scopes and their exact
paths, and counts what it found:

```
[DEBUG] Loading skills from: managed=C:\Program Files\ClaudeCode\.claude\skills,
        user=<SCRATCH_CFG>\skills,
        project=[<PROJ>\.claude\skills]
[DEBUG] Loaded 4 unique skills (4 unconditional, 0 conditional, managed: 0,
        user: 2, project: 2, additional: 0, legacy commands: 0)
[DEBUG] Loaded 1 skills-as-plugins
[DEBUG] getPluginSkills: Processing 4 enabled plugins
[DEBUG] Checking plugin probe-scaffold: skillsPath=exists, skillsPaths=0 paths
[DEBUG] Attempting to load skills from plugin probe-scaffold default skillsPath:
        <SCRATCH_CFG>\skills\probe-scaffold\skills
[DEBUG] Loaded 1 skills from plugin probe-scaffold default directory
[DEBUG] Total plugin skills loaded: 1 (0 duplicate/user-owned entries skipped)
[DEBUG] getSkills returning: 4 skill dir commands, 1 plugin skills,
        38 bundled skills, 1 builtin plugin skills
[DEBUG] Watching for changes in skill/command directories: ...
```

Three contract details worth copying:
- the counts are **per-scope** (`managed/user/project/additional`) and
  `legacy commands` is counted **separately** from skills, even though both
  surface in the same `/` command list;
- the final line splits the result into four populations: skill-directory
  commands, plugin skills, bundled skills, and builtin-plugin skills;
- the loader **watches** the skill and command directories for live changes
  (`Watching for changes in skill/command directories: ...`).

**Clean-room opportunity.** Implement discovery as an ordered list of
`(scope, path)` roots with a per-scope counter and a single
`getSkills()`-equivalent that returns the four populations separately. Emit
the same one-line-per-scope diagnostic; it is the cheapest possible
support tool and it makes every precedence question answerable without
guessing.

### F10-2 — Scope precedence is applied at name resolution, not at load time

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Resolve skills that share a name"
**Evidence:** `discovery-and-budget-probes.txt` P2

Fixture: skill name `precedence-test` present in **both** the user scope and the
project scope, with different descriptions.

The loader counted both: `Loaded 4 unique skills (... user: 2, project: 2 ...)`.
The `skill_listing` attachment the model received contained:

```
- precedence-test: PERSONAL scope version of the precedence probe skill.
```

So the **user-scope** description is the one that reaches the model; the
project-scope copy is shadowed. This matches the documented precedence
("Enterprise over personal, and personal over project").

The non-obvious part is the *timing*: the loader's counter says four skills
were loaded, but only one of the two same-named skills survives into the
listing. A reimplementation that resolves collisions during the scan (rather
than after) will produce a different counter and different diagnostics. The
product's behaviour — load everything, resolve at naming time — is the one to
copy, because it lets `project` skills exist without being clobbered by
`personal` ones at the file level.

**Clean-room opportunity.** Separate *loading* (collect every candidate with
its scope tag) from *resolution* (choose a winner per command name, with
enterprise > personal > project). Keep both: the loaded set drives `/doctor`
and the resolved set drives the model listing. Document the precedence table
as data, not as code.

### F10-3 — Nested `.claude/skills/` is a *startup* scope only when the session starts inside it

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Load skills in monorepos and subdirectories"
**Evidence:** `discovery-and-budget-probes.txt` P3

The same project tree, two working directories:

```
# session started at <PROJ>
[DEBUG] project=[<PROJ>\.claude\skills]
[DEBUG] Loaded 4 unique skills (4 unconditional, 0 conditional, managed: 0,
        user: 2, project: 2, additional: 0, legacy commands: 0)

# session started at <PROJ>/sub
[DEBUG] project=[<PROJ>\sub\.claude\skills, <PROJ>\.claude\skills]
[DEBUG] Loaded 5 unique skills (5 unconditional, 0 conditional, managed: 0,
        user: 2, project: 3, additional: 0, legacy commands: 0)
```

The scope list is an **ordered array of directories**, nearest-first, and the
parent's `.claude/skills` is still searched. The nested skill `deep-skill`
appeared only in the sub-directory session.

The doc adds the completion of the rule: a `.claude/skills/` directory
**below** the start directory does not load at startup — it loads the first
time Claude reads or edits a file in that subdirectory, and does not appear in
the `/` menu until then (`/add-dir` with the subdirectory path forces it to
load sooner).

**Clean-room opportunity.** Model the project scope as a list, not a single
path, and add a `conditional` bucket for skills whose activation depends on
file access. The debug line already distinguishes `N unconditional, M
conditional` — copy that vocabulary.

### F10-4 — `paths:` frontmatter creates a *conditional* skill, held in a separate store

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — frontmatter table, `paths` row
**Evidence:** `discovery-and-budget-probes.txt` P4

Fixture: `<PROJ>/.claude/skills/pathscond/SKILL.md` with `paths: "**/*.ts"`.

```
[DEBUG] [skills] 1 conditional skills stored (activated when matching files are touched)
[DEBUG] Loaded 2 unique skills (1 unconditional, 1 conditional, managed: 0,
        user: 1, project: 1, additional: 0, legacy commands: 0)
```

A path-scoped skill is stored **outside** the unconditional listing and
activates when a matching file is touched. `paths` accepts a comma-separated
string or a YAML list, uses the same glob format as path-specific rules, and
supports brace expansion (`src/**/*.{ts,tsx}`) with a shared budget of 1,000
expanded patterns and 4 MiB per rule.

**Clean-room opportunity.** Implement path-conditioned skills as a distinct
lifecycle: *registered → dormant → active on matching file access*. This is a
genuine context-saving feature that most agents lack, and it is cheap to build
once the glob matcher exists.

### F10-5 — The two invocation-control flags are **not** opposites

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Control who invokes a skill"
**Evidence:** `agent-reference-shots/area10-skills/skill-rendering-probes.txt` P3; `invocation-control-and-instruction-probes.txt` P1

Documented table:

| Frontmatter | You can invoke | Claude can invoke | When loaded into context |
| :- | :- | :- | :- |
| (default) | Yes | Yes | Description always in context, full skill on invoke |
| `disable-model-invocation: true` | Yes | Not on its own | **Description not in context**, full skill on invoke |
| `user-invocable: false` | No | Yes | Description always in context, full skill on invoke |

**OBSERVED-CLI** — read directly out of the model's own `skill_listing`
attachment against the `init.skills` and `init.slash_commands` registries:

| Skill | in `init.skills` | in `/` menu | in model listing |
| :- | :- | :- | :- |
| `dmi` (`disable-model-invocation: true`) | **yes** | **yes** | **no** |
| `uif` (`user-invocable: false`) | **no** | **no** | **yes** |
| `plain` (neither) | yes | yes | yes |

So `disable-model-invocation` removes the **description** (so the model cannot
choose the skill) but keeps the command available to the user;
`user-invocable: false` keeps the **description** (so the model can use it as
background knowledge) but removes the command from the user's menu.

The typed error returned when the model tries the first one:

```
<tool_use_error>Skill dmi cannot be used with Skill tool due to
disable-model-invocation. Ask the user to run /dmi themselves - it cannot be
invoked via the Skill tool. Do not replicate this skill's workflow by other
means - it is reserved for explicit user invocation.</tool_use_error>
```

The error text is a **policy instruction to the model**, not just a failure
message — it explicitly tells the model not to achieve the same effect another
way. That is a design pattern worth copying verbatim in spirit.

**Clean-room opportunity.** Expose two independent booleans
(`model_may_invoke`, `user_may_invoke`) rather than one enum, derive the three
surfaces (listing visibility, menu visibility, tool-call permission) from
them, and make the refusal error carry an explicit "do not work around this"
directive. Most agent frameworks conflate these into one flag and get the
semantics wrong.

### F10-6 — `skillOverrides` has four states that affect three different surfaces

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/settings-reference.md — `skillOverrides`
**Evidence:** `invocation-control-and-instruction-probes.txt` P1

Fixture: three project skills with
`{"ovr-one":"name-only","ovr-two":"user-invocable-only","ovr-three":"off"}`.

| State | `init.skills` | `/` menu | model listing |
| :- | :- | :- | :- |
| `on` (default) | yes | yes | name + description |
| `name-only` | yes | yes | **name only** |
| `user-invocable-only` | yes | yes | **hidden from the model** |
| `off` | **no** | **no** | hidden |

Observed `init.skills` = `['ovr-one','ovr-two']`; observed `init.slash_commands`
= `['ovr-one','ovr-two']`; the listing contained exactly `- ovr-one` for these
three.

The naming is counter-intuitive: `user-invocable-only` is the state that
**hides the skill from the model** and leaves it in the user's menu. The
`/skills` menu labels that state `user-only`.

Two further documented facts: a skill absent from `skillOverrides` is treated
as `"on"`; and plugin skills are **not** affected by `skillOverrides` at all.

**Clean-room opportunity.** Implement overrides as a four-state enum applied
*after* frontmatter resolution, applied uniformly to all three surfaces, and
expose a one-command "cost and usage report" (`/skill-doctor`) so the user can
see which skills are costing context. The doc notes `/doctor` reports the
listing's context cost and its biggest contributors.

### F10-7 — The skill listing is a plain-text attachment with a hard character budget

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Skill descriptions are cut short"; https://code.claude.com/docs/en/settings-reference.md — `skillListingBudgetFraction`, `skillListingMaxDescChars`; https://code.claude.com/docs/en/env-vars.md — `SLASH_COMMAND_TOOL_CHAR_BUDGET`
**Evidence:** `discovery-and-budget-probes.txt` P5, P6; `registry-and-tool-contracts.txt` § 4

**OBSERVED-CLI** — the loader warns on overflow and names both remedies:

```
[DEBUG] Sending 17 skills via attachment (initial)
[WARN] Skill listing over budget: 17 skills, 6484 chars > 6000 budget
        - descriptions will be truncated. Run /skills to disable some, or
        raise skillListingBudgetFraction in settings.
```

The attachment itself:

```json
{ "type": "skill_listing",
  "content": "- precedence-test: PERSONAL scope version of the precedence probe skill.\n- probe-scaffold\n- nested-only: A skill that lives only in the project root .claude/skills.\n...",
  "skillCount": 17, "isInitial": true,
  "names":  ["precedence-test","probe-scaffold", ...],
  "digests": ["24709798e5b55fc0","0e2f2269d902ca43", ...] }
```

Format: `- <name>: <description>`, or `- <name>` alone when the description was
dropped. **Names are never dropped** — only descriptions — so the model can
still invoke a skill it can no longer match.

The documented budget: 1% of the context window, with an 8,000-character
fallback, overridable by `SLASH_COMMAND_TOOL_CHAR_BUDGET` (legacy name) or
`skillListingBudgetFraction` (default `0.01`); per-entry cap
`skillListingMaxDescChars` (default 1536, applied to `description` +
`when_to_use` combined). Overflow drops descriptions **starting with the
least-used skills**, so frequently-used skills keep their text.

The parallel `names` / `digests` arrays (16 hex chars per skill) are a
content-hash per entry — evidently used to detect that a rendered description
changed and to decide whether a re-invocation is a repeat of one already in
context.

**Clean-room opportunity.** Implement the listing as a **budgeted, ordered,
always-name-inclusive** channel, with per-entry caps, a usage-ranked
truncation policy, and a machine-readable `names`+`digests` sidecar so the
listing can be diffed and resent incrementally. This is one of the few places
where a naive implementation ("just concatenate all descriptions") will
blow up a context window, and the product's design here is directly
copyable.

### F10-8 — `SKILL.md` frontmatter is a fixed, hyphen-cased field set with three distinct failure modes

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Frontmatter reference"
**Evidence:** `agent-reference-shots/area10-skills/plugin-validate-probes.json`, `plugin-cli-probes.txt` P5

Field names use lowercase words separated by hyphens, except `when_to_use`.
Recognised fields: `name`, `description`, `when_to_use`, `argument-hint`,
`arguments`, `disable-model-invocation`, `user-invocable`, `allowed-tools`,
`disallowed-tools`, `model`, `effort`, `context`, `agent`, `background`,
`hooks`, `paths`, `shell`, `metadata`, `license`, `compatibility`.

Three distinct failure modes, all observed:

1. **Unknown field** → silently ignored, no error. Observed: a skill with
   `descripton:` produced no validator finding at all.
2. **Missing frontmatter block** → the file loads with **no fields set**; the
   validator emits a *warning*:
   `"No frontmatter block found. Add YAML frontmatter between --- delimiters at the top of the file to set description and other metadata."`
3. **Unparseable YAML** → the skill still loads, but with **all frontmatter
   fields silently dropped**. The validator emits an *error*:
   `"YAML frontmatter failed to parse: YAML Parse error: Unexpected EOF. At runtime this skill loads with empty metadata (all frontmatter fields silently dropped)."`

Other observed contract points: the opening `---` must be the file's **first
line**, otherwise the whole file (markers included) is treated as body text;
boolean fields accept `yes/no/on/off/1/0` in any case as well as `true/false`;
an omitted `description` falls back to the first non-empty line of the body.

Outside Claude Code (claude.ai uploads, the Skills API, `package_skill.py`),
only six fields are allowed — `name`, `description`, `license`,
`compatibility`, `metadata`, `allowed-tools` — and an extra field is a **hard
error**: `Unexpected key(s) in SKILL.md frontmatter: argument-hint. Allowed
properties are: allowed-tools, compatibility, description, license, metadata, name`.

**Clean-room opportunity.** Implement a two-tier frontmatter schema: a
superset for the agent runtime and a strict subset for a packaging/upload
path, with an explicit error listing the allowed keys. Make the parse-failure
path **non-fatal but loud** (drop fields, report the error) exactly as the
reference does — a skill that fails to parse should still be usable, and the
author should be told why it is not behaving.

### F10-9 — The skill body is a template language: `$ARGUMENTS`, `$N`, `$name`, and `${CLAUDE_*}` variables

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Available string substitutions", § "Pass arguments to skills"
**Evidence:** `skill-rendering-probes.txt` P1

Substitution table:

| Variable | Meaning |
| :- | :- |
| `$ARGUMENTS` | all arguments as typed; if no placeholder consumes one, `ARGUMENTS: <value>` is appended |
| `$ARGUMENTS[N]` / `$N` | argument by 0-based index |
| `$name` | named argument declared in the `arguments:` frontmatter list |
| `${CLAUDE_SESSION_ID}` | current session id |
| `${CLAUDE_EFFORT}` | current effort level |
| `${CLAUDE_SKILL_DIR}` | directory containing the skill's `SKILL.md` |
| `${CLAUDE_PROJECT_DIR}` | project root |
| `${CLAUDE_PLUGIN_ROOT}` | plugin install dir (plugin skills only) |
| `${CLAUDE_PLUGIN_DATA}` | plugin data dir (plugin skills only) |

**OBSERVED-CLI** — skill body `ARGS=[$ARGUMENTS] IDX0=[$0] NAMED=[$thing]
SID=[${CLAUDE_SESSION_ID}]`, invoked as `/argtest hello world`:

```
ARGS=[hello world] IDX0=[hello] NAMED=[$thing] SID=[afeba6c6-0ceb-4520-bf05-a1cb3e49607a]
```

and the harness additionally prepended a `Base directory for this skill: <path>`
line and appended an `ARGUMENTS: <value>` line.

`$thing` was **not** expanded because the skill declared no `arguments:`
frontmatter — an unknown named placeholder is left literal. Documented
behaviours not re-probed here: an indexed placeholder with no corresponding
argument stays literal; a named placeholder with no matching argument expands
to the empty string; an argument value containing `$1` is inserted literally
(not re-expanded); a backslash escapes a literal `$` before a digit,
`ARGUMENTS`, or a declared name.

`${CLAUDE_SKILL_DIR}` and `${CLAUDE_PROJECT_DIR}` are substituted in **two**
places: the skill's markdown body **and** the Bash rules inside its
`allowed-tools` frontmatter — which is the trick that lets a skill
pre-approve its own bundled script without a permission prompt.

**Clean-room opportunity.** Implement substitution as an explicit, ordered
expansion pass with a documented precedence (`$ARGUMENTS`/`$N`/`$name` first,
then `${CLAUDE_*}`), applied to *both* the body and the tool-allow rules so a
skill can pre-approve a script it references by an absolute path. Document
the "argument values are never re-scanned" rule — it is a security property,
not an implementation detail.

### F10-10 — The loader executes `` !`cmd` `` inside a skill body itself — a code-execution surface

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Inject dynamic context", § "How injected commands run", § "Permission checks on injected commands"
**Evidence:** `skill-rendering-probes.txt` P2; `invocation-control-and-instruction-probes.txt` P2

Skill body:

```
Start of line:
!`echo INJECTED_INLINE_OK`
After whitespace:
VALUE !`echo INJECTED_WS_OK`
```

Rendered content delivered to the model:

```
Start of line:
INJECTED_INLINE_OK
After whitespace:
VALUE INJECTED_WS_OK
```

**The harness ran both shell commands at skill-render time.** No tool call was
made by the model; the substitution happened in the loader, before the content
reached the model. In the same probe series, `INJECTED=!"echo INJECTED_OK"`
was left **literal**, because the `!` was preceded by `=`.

The documented rules, all consistent with the observation:
- the inline form is recognised only when `!` is at the start of a line or
  immediately after whitespace;
- multi-line commands use a fenced block opened with ```` ```! ````;
- substitution runs **once** over the original file, so command output is not
  re-scanned for further placeholders — "a command cannot emit a placeholder
  for a later pass to expand";
- a **failed** command aborts the entire skill invocation (not just its own
  placeholder): `Shell command failed for pattern "..."`, with output under
  `[stderr]`; exit code 1 from search/comparison commands is a carveout, exit
  ≥2 always fails;
- a command denied by a permission rule aborts with `Shell command permission
  check failed for pattern "..."`;
- injected commands never prompt, but they *are* permission-checked.

**Policy control, OBSERVED-CLI** — with
`{"disableSkillShellExecution": true}` in project settings, the rendered body
was:

```
START [shell command execution disabled by policy] END
```

The command did not run and no shell was spawned. Documented scope: the setting
applies to skills and commands from user, project, plugin, and
additional-directory sources; **bundled and managed skills are unaffected**; it
is intended for managed settings where users cannot override it.

**Clean-room opportunity.** This is the highest-risk surface in the whole
extension layer and the one most worth getting right. A clean-room
implementation should: (a) make injection execution explicit and auditable —
log every executed command with its resolved pattern; (b) default to a
**prompt** (or deny) for injected commands unless the skill is trusted, rather
than running them silently; (c) implement the `disableSkillShellExecution`
policy and make it settable from *managed* configuration so an organisation can
switch it off globally; (d) never re-scan injected output. The reference
implementation's silent-execute default is the thing to beat.

### F10-11 — `context: fork` runs a skill in an isolated subagent, and is not counted as a spawned subagent

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Run skills in a subagent"
**Evidence:** `skill-rendering-probes.txt` P4

Fixture: skill with `context: fork` and `agent: Explore`, body "Reply with
exactly the token FORKED_OK."

`claude -p ... --output-format json` returned:

```
"result": "FORKED_OK"
```

with `subagent_stats: {"spawned": 0, ...}` and `"num_turns": 7`.

So the skill body ran in an isolated context and only its final text came back
to the caller — but the harness's own accounting does **not** count a
`context: fork` skill as a spawned subagent (`spawned: 0`). An implementer
building a cost or concurrency ledger must decide whether a forked skill
counts; the reference says no, which is arguably an accounting bug worth
flagging rather than copying.

Documented semantics: the forked subagent gets the agent type's system prompt
plus the skill content as its task; it does **not** see the conversation
history; `Explore` and `Plan` start without CLAUDE.md and git status; the fork
runs in the background by default unless `background: false`; and Claude Code
waits for the result anyway in `-p`/SDK mode, when
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, when the same skill is already
running, and when a scheduled task fires it.

**Clean-room opportunity.** Implement `context: fork` as a first-class
execution mode of the skill runner — isolated context, agent-type system
prompt, result-only return — and **count it in the subagent ledger**. Making
the accounting honest is a differentiator, not a copy.

### F10-12 — Subagent definitions are a camelCase frontmatter schema with a documented "skip" list

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/sub-agents.md — § "Frontmatter reference", § "Subagent files Claude Code skips"
**Evidence:** `registry-and-tool-contracts.txt` § 3; `invocation-control-and-instruction-probes.txt` P3

Subagent files live in `.claude/agents/*.md` (project), `~/.claude/agents/`
(user), a plugin's `agents/`, or the managed directory, and may also be
supplied via a `--agents` JSON flag. Field names use **camelCase** (unlike
skills, which use hyphens) and must match exactly.

Documented fields: `name` (required), `description` (required), `tools`,
`disallowedTools`, `model`, `permissionMode`, `maxTurns`, `autoCompactWindow`,
`skills`, `mcpServers`, `hooks`, `memory`, `background`, `omitClaudeMd`,
`effort`, `isolation`, `color`, `initialPrompt`, `experimental`.

The documented **skip list** — a file is treated as documentation, not an
agent, when the frontmatter has any of these problems: no `name`; an opening
`---` that isn't the file's first line; a `name` that starts with `-`, contains
`:`, or is longer than 256 characters; a `name` but no `description`; or YAML
that does not parse. Each skip is written to the debug log.

**OBSERVED-CLI** — `claude plugin validate <PROJ>/.claude/agents` validates an
agents directory and reports `✔ Validation passed`; the same command is
documented as the way to find agents-directory files whose frontmatter does
not parse.

**Clean-room opportunity.** Adopt the same discipline: a strict, documented
schema with camelCase (or hyphen-case — but pick one and enforce it), a
machine-checkable skip list, and a **validator that can be pointed at a
directory** rather than only at a manifest. The "invalid file becomes
documentation, not an error" rule is a good one: it degrades gracefully
instead of blocking the session.

### F10-13 — A subagent's `skills:` field preloads the **entire `SKILL.md`, frontmatter included**

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/sub-agents.md — § "Preload skills into subagents"; https://code.claude.com/docs/en/skills.md — § "Run skills in a subagent"
**Evidence:** `invocation-control-and-instruction-probes.txt` P3

Documented: *"The full skill content is injected, not only the description."*

**OBSERVED-CLI** — a subagent with `skills: [preload-me]` reported the content
it received:

```
---
name: preload-me
description: A skill whose full body should be preloaded into a subagent.
---
PRELOAD_TOKEN_ZZZ first line of the skill body.
Second line.
```

The **YAML frontmatter is included**, not stripped. That is a difference from
the normal listing (`- <name>: <description>`) and from the `.claude/rules/`
loader (which removes the frontmatter before injecting the rule).

The run's own ledger is a useful shape for an implementer:

```json
"subagent_stats": { "spawned": 1,
  "requested": { "background": 0, "foreground": 1, "unset": 0 },
  "started_in_background": 0, "max_depth": 1, "spawned_by_subagents": 0,
  "completed": 1, "failed": 0,
  "killed": { "parent": 0, "user": 0, "system": 0 },
  "refused": { "depth_limit": 0, "concurrency_limit": 0, "budget": 0 },
  "by_type": { "preload-agent": 1 } }
```

Note the `refused` sub-object (depth/concurrency/budget) — refusals are
recorded as first-class outcomes rather than as errors.

The documented inverse direction is a skill with `context: fork`: the skill
supplies the *task* and the agent type supplies the *system prompt*; a
subagent supplies the *system prompt* and the delegation message, and
`skills:` supplies the reference material.

**Clean-room opportunity.** Implement the two directions as one composition
matrix and document it (skill→task / agent→prompt; agent→prompt /
skill→reference). Include the frontmatter in the preload (it is cheap and
lets the subagent see the skill's own metadata), and keep a per-agent-type
ledger with a `by_type` breakdown and explicit refusal reasons.

### F10-14 — The delegation tool is `Task` in the harness registry and `Agent` in the model's schema

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Evidence:** `invocation-control-and-instruction-probes.txt` P4; `registry-and-tool-contracts.txt` § 2

`init.tools` for the observed session:

```
["Task","Bash","CronCreate","CronDelete","CronList","DesignSync","Edit",
 "EnterWorktree","ExitWorktree","Glob","Grep","ListAgents","NotebookEdit",
 "Read","ReportFindings","ScheduleWakeup","SendMessage","Skill","TaskStop",
 "ToolSearch","WebFetch","WebSearch","Workflow","Write"]
```

`Task` is present; `Agent` is **not**. But the tool definition actually sent to
the model (captured from the API request shape) is named **`Agent`**:

```json
{ "name": "Agent",
  "input_schema": { "type": "object", "properties": {
    "description": {...}, "prompt": {...}, "subagent_type": {...},
    "model": { "enum": ["sonnet","opus","haiku","fable"] },
    "effort": { "enum": ["low","medium","high","xhigh","max"] },
    "run_in_background": { "type": "boolean" },
    "isolation": { "enum": ["worktree","remote"] } },
  "required": ["description","prompt"], "additionalProperties": false } }
```

The model-facing description also states the fork semantics: `"fork"` forks
the current conversation (inheriting full context, ignoring a `model`
override); any other type starts a fresh agent, `general-purpose` by default.

**Clean-room opportunity.** Pick one canonical tool name and be consistent
across the registry, the schema, and the transcripts. If transcript
compatibility matters, note that `init.tools` uses `Task` while the API request
uses `Agent` — a reimplementation that must read Claude Code transcripts should
tolerate both.

### F10-15 — The agent registry the model sees is a structured, incremental attachment

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Evidence:** `registry-and-tool-contracts.txt` § 3; `invocation-control-and-instruction-probes.txt` P5

```json
{ "type": "agent_listing_delta",
  "addedTypes": ["claude","Explore","general-purpose","Plan","preload-agent",
                 "probe-scaffold:example","statusline-setup"],
  "addedLines": [
    "- claude: Catch-all for any task ... (Tools: *)",
    "- Explore: Read-only search agent ... (Tools: All tools except Agent, Artifact, ArtifactComments, ArtifactData, ArtifactCheck, ExitPlanMode, Edit, Write, NotebookEdit)",
    "- preload-agent: A probe agent that preloads one skill ... (Tools: Read, Grep)"],
  "builtInTypes": ["claude","Explore","general-purpose","Plan","statusline-setup"],
  "builtInPluginTypes": [], "removedTypes": [],
  "isInitial": true, "showConcurrencyNote": true }
```

Each line is `- <type>: <description> (Tools: <list>)`. The tool list is
rendered as an **explicit exclusion list** when the agent inherits most tools
("All tools except Agent, Artifact, … Edit, Write, NotebookEdit") and as an
inclusion list when it is restricted ("(Tools: Read, Grep)"). `builtInTypes`
separates built-ins from plugin/user/project agents; `removedTypes` supports
removing an agent mid-session; `isInitial` distinguishes the first payload
from an incremental delta.

**Clean-room opportunity.** Publish the agent registry as a **delta
attachment** with a stable line format, an explicit built-in/user/project
split, and removal support. The exclusion-list rendering is a nice touch: it
keeps the line short for the common "inherits everything" case while still
being unambiguous.

### F10-16 — Project instructions are concatenated in a defined order, and `@path` imports become separate entries

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/memory.md — § "How CLAUDE.md files load", § "Import additional files"
**Evidence:** `agent-reference-shots/area10-skills/instructions-attachment-probe.txt` A, B, C

Documented loading rules:
- `CLAUDE.md` and `CLAUDE.local.md` load from the cwd **and every directory
  above it**;
- all discovered files are **concatenated, not overridden**;
- across the tree, content is ordered **from the filesystem root down to the
  working directory**, so instructions closer to the launch point are read
  last;
- within each directory, `CLAUDE.local.md` is appended **after** `CLAUDE.md`;
- subdirectory files load **lazily**, on first read/write/edit of a file
  there, not at launch;
- block-level HTML comments are stripped before injection (comments inside code
  blocks are preserved);
- a CLAUDE.md may exceed 4 MiB — the file is then skipped;
- `claudeMdExcludes` skips specific files.

**OBSERVED-CLI** — the product's own `instructions` attachment records each
file separately with its path, a `type` (`Project`), and its content:

```json
{ "type": "instructions", "files": [
  { "path": "...\\proj\\CLAUDE.md", "type": "Project", "content": "..." } ] }
```

With a `CLAUDE.md` containing `@sub/CLAUDE.md`, the attachment had **two**
entries — the import became its own file entry rather than being inlined into
the parent's content:

```json
{ "type": "instructions", "files": [
  { "path": "...\\proj5\\CLAUDE.md", "type": "Project",
    "content": "# Project instructions\nBase instructions. Import the sub guide with @sub/CLAUDE.md" },
  { "path": "...\\proj5\\sub\\CLAUDE.md", "type": "Project",
    "content": "# Sub instructions\nSub-directory instructions." } ] }
```

Documented import rules: relative and absolute paths both allowed; relative
paths resolve **relative to the file containing the import**, not the working
directory; imports may nest to a **maximum depth of four hops**; a path with
spaces needs a backslash before each space; a **quoted** path is not imported
at all; import parsing skips Markdown code spans and fenced code blocks; and a
path wrapped in backticks stays literal.

Security rule worth copying: an import in a project-level file whose path
resolves **outside the working directory** is "external" and triggers a
one-time approval dialog listing the files; declining keeps them disabled
permanently.

**Clean-room opportunity.** Implement instruction loading as an ordered list of
`(path, type, content)` records with an explicit precedence order
(managed → user → root→cwd concatenation, `CLAUDE.local.md` after
`CLAUDE.md` per level), a separate import-resolution pass with a 4-hop depth
cap and cycle detection, and a per-project "external import" approval record.
Keeping the *file identity* of each instruction (rather than concatenating to
one blob) makes the context auditable — the user can see exactly which files
shaped the session.

### F10-17 — `.claude/rules/` gives a path-scoped instruction channel that is injected on file access, not at launch

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/memory.md — § "Organize rules with `.claude/rules/`", § "Path-specific rules"
**Evidence:** `instructions-attachment-probe.txt` D, E

Rules live in `.claude/rules/*.md` and are discovered **recursively**. A rule
with no `paths` frontmatter loads **unconditionally at launch**, with the same
priority as `.claude/CLAUDE.md`. A rule **with** `paths` loads only when
Claude uses Read, Write, or Edit on a matching file (or views it with a Bash
command that counts as a read).

**OBSERVED-CLI** — the unconditional rule was in the launch-time
`instructions` attachment:

```json
{ "type": "instructions", "files": [
  { "path": "...\\proj8\\.claude\\rules\\plain-rule.md", "type": "Project",
    "content": "# Plain rule\nAlways answer with the token RULE_PLAIN_LOADED." } ] }
```

The path-scoped rule was **not** there. It arrived later, as a
`nested_memory` attachment, when the session read `sample.ts`:

```json
{ "type": "attachment",
  "attachment": {
    "type": "nested_memory",
    "path": "<PROJ>/.claude/rules/ts-rule.md",
    "content": { "type": "Project",
      "content": "# TS rule\nAlways answer with the token RULE_TS_LOADED.\n",
      "globs": ["**/*.ts"],
      "contentDiffersFromDisk": true,
      "rawContent": "---\npaths:\n  - \"**/*.ts\"\n---\n# TS rule\n...",
      "displayPath": ".claude\\rules\\ts-rule.md" },
    "rendered": [ { "content": "<system-reminder>\nContents of <PROJ>/.claude/rules/ts-rule.md:\n\n# TS rule\n...\n\n</system-reminder>" } ],
    "renderedRole": "system" } }
```

The attachment is richly structured: `globs` (the patterns), `rawContent`
(the file **with** frontmatter), `content` (frontmatter stripped), and
`rendered` (the actual system-reminder text, with `renderedRole: "system"`).

Documented rule frontmatter: `paths` is the **only** field read; anything else
is ignored without error; if the YAML does not parse, the frontmatter is
ignored and the rule loads as if it had no `paths`; the frontmatter is removed
before the rule enters context. Pattern budget: a rule's whole `paths` list
shares one budget of 1,000 expanded patterns and 4 MiB; patterns without
braces do not count against it; a pattern that would exceed the budget is used
**unexpanded** (and its literal braces then match nothing).

**Clean-room opportunity.** Implement a rules directory as a first-class
*conditional instruction channel* with glob scoping, brace expansion under a
shared budget, frontmatter stripping, and a documented rule for what happens
when a pattern set is too large. The `nested_memory` attachment shape — with
`globs`, `rawContent`, `content`, and `rendered` — is a good, auditable design
to copy.

### F10-18 — AGENTS.md is a built-in plugin, and its switch is readable only from user/`--settings`/managed scopes

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/memory.md — § "AGENTS.md", § "Choose which instruction files load"
**Evidence:** `instructions-attachment-probe.txt` A, B; `invocation-control-and-instruction-probes.txt` P7

Documented default table:

| Your repository has | Claude reads |
| :- | :- |
| `AGENTS.md`, no `CLAUDE.md`/`CLAUDE.local.md` in cwd or above | your `AGENTS.md` |
| `AGENTS.md` **and** a `CLAUDE.md`/`CLAUDE.local.md` in cwd or above | your `CLAUDE.md` files only |
| `CLAUDE.md` that imports `AGENTS.md` | your `CLAUDE.md`, with `AGENTS.md` included through the import |

Files that **count** (and therefore suppress `AGENTS.md`): `CLAUDE.md`,
`.claude/CLAUDE.md`, `CLAUDE.local.md` in the cwd or above. Files that **do
not** count: `~/.claude/CLAUDE.md`, the managed `CLAUDE.md`, and `.claude/rules/`.

**OBSERVED-CLI** — with both files present, only `CLAUDE.md` was in the
`instructions` attachment; with only `AGENTS.md` present, `AGENTS.md` was.

The switch is `pluginConfigs["cc-plugin-agents-md@builtin"].options.instructionFiles`
with values `claude-md-or-agents-md` (default), `claude-md-and-agents-md`,
`claude-md`, `managed-only`.

**OBSERVED-CLI** — passing it via `--settings` produced an attachment with
**both** files:

```json
[ { "path": "...\\proj\\CLAUDE.md", "type": "Project", "content": "# Project instructions..." },
  { "path": "...\\proj\\AGENTS.md",   "type": "Project", "content": "# Agents instructions..." } ]
```

But writing the **same** JSON into the project's `.claude/settings.json` did
**nothing**, and the debug log says why:

```
[DEBUG] plugin cc-plugin-agents-md: no pluginConfigs["agents-md@builtin" or
        "cc-plugin-agents-md@builtin"].options in user, --settings or managed
        settings (project settings are not read); every option is its default
```

The same log line also shows the **legacy plugin ID** still being accepted:
`agents-md@builtin` or `cc-plugin-agents-md@builtin` (the ID changed in
v2.1.285).

**Clean-room opportunity.** Implement `AGENTS.md` as an *optional* alternative
instruction file with an explicit four-value mode, and — importantly — make
the mode itself readable from every settings scope the user might plausibly
use. The reference's project-scope exclusion is a usability trap: a user who
commits the setting to a repo gets silently ignored behaviour. A clean-room
implementation should either honour it everywhere or **warn loudly** when it
is set in a scope that will not be read.

### F10-19 — `skillOverrides`, `disableSkillShellExecution`, `disableBundledSkills`, `disableWorkflows` and `pluginConfigs` form one settings surface

**Status:** OBSERVED-DOC (+ OBSERVED-CLI where noted)
**Source:** https://code.claude.com/docs/en/settings-reference.md, `/en/skills.md`, `/en/workflows.md`
**Evidence:** `invocation-control-and-instruction-probes.txt` P1, P2, P7

| Setting | Scope | Effect |
| :- | :- | :- |
| `skillOverrides` | any file | four-state visibility override (F10-6) |
| `skillListingBudgetFraction` | any file | fraction of the context window for the skill listing (default 0.01) |
| `skillListingMaxDescChars` | any file | per-entry description cap (default 1536) |
| `disableSkillShellExecution` | any file | replaces injected commands with `[shell command execution disabled by policy]` (F10-10, OBSERVED-CLI) |
| `disableBundledSkills` | — | removes bundled skills from the listing |
| `disableWorkflows` / `CLAUDE_CODE_DISABLE_WORKFLOWS=1` | — | disables dynamic workflows |
| `pluginConfigs` | user, `--settings`, managed | per-plugin options, incl. the AGENTS.md mode (F10-18, OBSERVED-CLI) |

**Clean-room opportunity.** Put all extension-layer knobs in one typed
settings schema with an explicit scope table, and make the scope table part of
the documentation *and* of the runtime — a setting that is read in one scope
and ignored in another should produce a diagnostic, not silence.

### F10-20 — Dynamic workflows are a sandboxed, deterministic script layer over subagents

**Status:** OBSERVED-DOC (the runtime was not executed — the gateway build has workflows behind a paid-plan/feature-flag gate that could not be exercised)
**Source:** https://code.claude.com/docs/en/workflows.md

A workflow is a JavaScript file at `.claude/workflows/*.js` or
`~/.claude/workflows/*.js` whose first statement is a pure-literal metadata
block:

```javascript
export const meta = {
  name: 'audit-routes',
  description: 'Audit every route handler for missing auth checks',
}

const found = await agent('List every .ts file under src/routes/.', {
  schema: { type: 'object', required: ['files'], properties: { files: { type: 'array', items: { type: 'string' } } } },
})

const audits = await pipeline(found.files, file =>
  agent(`Audit ${file} for missing authentication checks.`, { label: file })
)
```

Runtime surface: top-level `await`; `agent()`, `pipeline()`, `parallel()`,
`phase()`, `log()`, and a global `args`. The body is plain JavaScript with
**no module loading** — a script containing `import()` fails before the run
starts.

Determinism is enforced by *prohibition*: `Date.now()`, `Math.random()`, and a
no-argument `new Date()` **throw** inside the script, so a relaunched run
repeats the same `agent()` calls; a timestamp must be passed in through `args`.
`meta` must be a plain object literal — if it contains a variable, a function
call, or a spread, `/<name>` is dropped from autocomplete.

Documented limits:

| Limit | Value |
| :- | :- |
| Concurrent agents | 16 by default (fewer on fewer CPUs); `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` 1–256 |
| Items per `parallel()`/`pipeline()` | 4,096 — a longer list is **rejected**, not silently truncated |
| Agents per run | 1,000 |
| Fan-out prefix stagger | up to 5,000 ms (`CLAUDE_CODE_WORKFLOW_PREFIX_STAGGER_MS`) so shared prompt-cache prefixes are reused |
| Agent restarts | at most five; the sixth stalled attempt fails the `agent()` call |
| Per-agent stall | `stallMs` option on the `agent()` call |
| Mid-run user input | none — a run pauses only for agent permission prompts and usage-limit waits |

`agent()` resolves to `null` if stopped or on an unrecoverable API error, and
`pipeline()` keeps the `null` in the results array. A `schema` on an `agent()`
call makes the subagent return JSON of that shape; the schema is checked
**before** the subagent starts, and a provably self-contradictory schema fails
the call without starting the agent.

Bundled: `/deep-research`. The `ultracode` keyword in a prompt makes Claude
write a workflow; `/effort ultracode` makes it plan one for every substantive
task. `/workflows` opens a progress view with phase/agent drill-down and the
keys `j/k` scroll, `f` filter by status, `p` pause/resume, `x` stop, `r`
restart an agent, `s` save the run's script as a reusable command.

**Clean-room opportunity.** This is the most copyable "many-agent" design in
the product, because it is a *script* rather than a model-driven loop: the plan
lives in code, the intermediate results live in script variables, and the
agent's context holds only the final answer. Copy the whole shape — the
pure-literal `meta`, the banned non-determinism, the hard limits with **rejection
rather than silent truncation**, the `null`-on-failure convention, and the
schema pre-flight. Do not copy the exact plan templates; those are content.

### F10-21 — Output styles are a named, switchable instruction bundle with an exact settings key

**Status:** OBSERVED-DOC + OBSERVED-CLI (registration only)
**Source:** https://code.claude.com/docs/en/output-styles.md
**Evidence:** `agent-reference-shots/area10-skills/init-registries.txt` (proj3)

A custom output style is a Markdown file with frontmatter, at
`~/.claude/output-styles/`, `.claude/output-styles/`, or the managed
directory's `.claude/output-styles/`. Frontmatter fields: `name`,
`description`, `keep-coding-instructions`, `force-for-plugin`.

Built-ins: **Default** (no style selected), **Proactive**, **Concise**,
**Explanatory**, **Learning**. Each built-in *keeps* the standard instructions
and adds its own; `Concise` additionally exempts "anything you need in order to
act safely" (error reports, failing test output, security warnings,
destructive-action confirmations) from being shortened.

Selection: `/output-style <style>`, `/config` → Output style, or the
`outputStyle` settings key. The value is **case-sensitive** (`"Explanatory"`,
not `"explanatory"`); a value that does not match a style name exactly falls
back to Default, while the `/output-style` command ignores case. The command
and both menus save to `.claude/settings.local.json` (local project level).

Scope: an output style applies to the **main conversation and to a fork**
(which inherits the parent's conversation and system prompt). Other subagents
run their own system prompt, so styles do not change how they respond. On the
full system prompt, a custom style leaves out Claude Code's built-in software
engineering instructions unless `keep-coding-instructions: true`; on the
shorter prompt that field has no effect.

**OBSERVED-CLI** — the registry reports the resolved style name: with a custom
style installed and `"outputStyle": "Probe Style"` in settings, `init.output_style`
was `"Probe Style"`; in every other probe project it was `"default"`.
Registration and resolution are therefore observed. **Whether the style
actually changes the model's output is model-limited, not product-limited** —
this host serves a non-Anthropic model through a custom gateway, and the
behavioural probe returned an answer rather than an adherence signal. That
half remains **UNKNOWN**.

**Clean-room opportunity.** Implement output styles as a named registry with
exactly the documented selection semantics (case-sensitive key, exact-match
fallback to default, case-insensitive interactive command) and an explicit
"applies to forks, not to subagents" rule. Also implement the
`keep-coding-instructions` switch — it is the only documented way to keep a
persona from degrading the agent's engineering behaviour, and it is easy to
miss.

### F10-22 — `claude plugin validate --json` is a real validator with a stable envelope, and it validates *directories* too

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/plugins/manifest-reference.md — § "Validate the manifest"
**Evidence:** `agent-reference-shots/area10-skills/plugin-cli-probes.txt` P3–P6; `plugin-validate-probes.json`

The JSON envelope:

```json
{ "success": true, "strict": false, "target": "<path>",
  "manifest": { "file": ..., "type": "plugin",
                "errors": [], "warnings": [], "notes": [], "gatingHooks": [] },
  "contents": [],
  "advice": [],
  "directory": { "profile": null, "findings": [], "undecided": [],
                 "incomplete": false, "failure": null, "notes": [] } }
```

`contents` entries are per-file records
(`{file, type, errors[], warnings[], notes[], gatingHooks[]}`, each finding
carrying `path`, `message`, `code`). `directory.findings` entries carry
`{code, title, severity, blocking, hold, file, field, message, fix}`; observed
codes: `README_MISSING`, `LICENSE_MISSING`, `ICON_MISSING`.

Results are tiered exactly as the doc describes:
- `Validation passed` — the manifest loads;
- `Validation passed with warnings` — it loads, but something should be fixed
  (an unknown top-level field that will be stripped, a non-kebab-case `name`, a
  missing `version`/`description`/`author`); `--strict` turns warnings into
  failures in CI;
- `Validation failed` — a type mismatch, a path that is missing or escapes the
  plugin root, or an unknown key inside a strict object.

**OBSERVED-CLI — the command also validates a components directory**, which
the documentation mentions only for `.claude/agents`:

```
$ claude plugin validate <PROJ>/.claude/skills
Validating components in: <PROJ>\.claude\skills
✔ Validation passed

$ claude plugin validate <PROJ>/.claude/commands
✘ Found 1 error:
  ❯ directory: No manifest found in directory. Expected
    .claude-plugin/marketplace.json or .claude-plugin/plugin.json
✘ Validation failed
```

**OBSERVED-CLI — the validator does not enforce the directory-submission
findings**, and says so explicitly:

```
✘ Found 1 problem the plugin directory refuses a submission for:
  ❯ README.md: README missing (README_MISSING). ...
    Fix: Add a README.md to the plugin folder describing what the plugin
    does, how to use it, and any setup it needs, in at least 40 words. ...
⚠ Found 1 plugin directory warning:
  ❯ .claude-plugin/plugin.json icon: No icon (ICON_MISSING). ...
These plugin directory checks do not change the result below. To fail on
problems the directory refuses a submission for, run this command with
--profile directory.
The directory also runs a safety scan and a policy review that this command
does not.
✔ Validation passed
```

**Clean-room opportunity.** Build the validator first, as a standalone tool
with a stable JSON envelope, and point it at **both** manifests and component
directories. Adopt the reference's three-tier result model (passed / passed
with warnings / failed), give every finding a `fix` string, and — better than
the reference — make the submission-profile findings *blocking* under a flag
rather than merely reported. A machine-readable `fix` per finding is what
makes a validator usable from CI.

### F10-23 — A skill folder with a `.claude-plugin/plugin.json` becomes a plugin with id `<name>@skills-dir`

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Where skills live"; https://code.claude.com/docs/en/plugins/manifest-reference.md — § "Standard layout"
**Evidence:** `agent-reference-shots/area10-skills/plugin-cli-probes.txt` P1, P2

**OBSERVED-CLI** — `claude plugin list --json`:

```json
[ { "id": "probe-scaffold@skills-dir", "version": "0.1.0", "scope": "user",
    "enabled": true,
    "installPath": "<SCRATCH_CFG>\\skills\\probe-scaffold" } ]
```

`claude plugin details probe-scaffold@skills-dir` produced a component
inventory and a **token-cost projection**:

```
Component inventory
  Skills (1)  example
  Agents (1)  example
  Hooks (0)
  MCP servers (0)
  LSP servers (0)

Projected token cost
  Always-on:   ~69 tok   added to every session

Per-component (rounded)
  component  always-on  on-invoke
  example          ~50       < 20
  example         < 20       < 20
  On-invoke cost is paid each time a skill or agent fires.
  Token counts are estimates and may differ from actual usage.
```

So the product distinguishes the **always-on** cost (the description the model
sees every turn) from the **on-invoke** cost (the body). This is the same
distinction F10-7's budget enforces, surfaced as a number.

Documented plugin surface: the manifest lives at `.claude-plugin/plugin.json`
and `name` is the only required key. Standard layout: `skills/`, `commands/`,
`agents/`, `hooks/hooks.json`, `.mcp.json`, `.lsp.json`, `output-styles/`,
`workflows/`, `themes/`, `monitors/monitors.json`, `bin/` (added to the Bash
tool's `PATH` while the plugin is enabled), `settings.json` (only `agent` and
`subagentStatusLine` take effect).

Path rules: every component path is relative to the plugin root and must
start with `./`; it must resolve **inside** the plugin root and must **exist**;
a path containing `..` is reported as `Path contains ".." which could be a
path traversal attempt`. Component keys either **replace** their default
location (`commands`, `agents`, `outputStyles`, `workflows`,
`experimental.themes`, `experimental.monitors`), **add** to it (`skills`), or
**merge** with it (`hooks`, `mcpServers`, `lspServers`).

Plugin-name rules: `claude-`, `anthropic-`, `anthropics-` and `cc-plugin-`
prefixes are errors; `claude`, `anthropic`, `anthropics`, `claude-code`,
`claude-mods` are errors; `official` beside `claude`/`anthropic` is an error;
`claude`/`anthropic`/`anthropics` as a whole word elsewhere is a warning. The
error text is `Plugin name "<name>" is reserved: it passes as one of
Anthropic's own`.

Environment variables: `${CLAUDE_PLUGIN_ROOT}` (the installed version),
`${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/<id>/`, survives updates),
`${CLAUDE_PROJECT_DIR}`. They resolve inline in hook commands, MCP `command`/
`args`/`env`, LSP configs, and **skill, command, and agent Markdown bodies**.

**Clean-room opportunity.** Implement plugins as a packaging layer over the
same skill/agent/hook registries, with a strict path-containment check
(`./`-prefixed, inside the root, exists) and a **reserved-name check** so a
third-party plugin cannot be confused with a first-party one. Expose the
always-on vs on-invoke token projection as a first-class command — it is the
best UX idea in this area and it falls straight out of the budget model.

### F10-24 — `claude agents` is a background-session registry, and `claude import` is unavailable in this build

**Status:** OBSERVED-CLI
**Evidence:** `agent-reference-shots/area10-skills/plugin-cli-probes.txt` P9, P10

**OBSERVED-CLI** — `claude agents --json` returned `[]`, and its own help
describes it as:

```
Usage: claude agents [options]
Manage background agents
  --json   Print active sessions (interactive and background) as a JSON array
           and exit (for scripting; does not require a TTY)
```

So `claude agents` lists **background sessions**, not subagent *definitions*.
Subagent definitions live in `init.agents` and in the `agent_listing_delta`
attachment. The naming collision is real and cost me time: an implementer
reading "agents" will look in the wrong place.

**OBSERVED-CLI** — `claude import --dry-run <spec>`:

```
`claude import` is not yet available in this build.
```

This contradicts the published CLI reference's description of the command. The
command exists in the docs but is gated out of this binary. Recorded as an
OBSERVED-CLI fact about *this build*; the doc remains the specification of the
intended behaviour.

**Clean-room opportunity.** Name the two registries distinctly in your own
design (`sessions` vs `agent definitions`) and expose both in JSON from the
start. For the "import an agent/command from another tool" capability, note
that the reference does not ship it here — so there is an **empty space** in
the reference product for an importer that converts a competitor's agent
definitions into your own format.

### F10-25 — Auto memory is an index-plus-topics directory with an enforced read cap

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/memory.md — § "Auto memory"

Auto memory is on by default in local sessions (off by default in self-hosted
environments). Each project gets `~/.claude/projects/<project>/memory/`, with
`<project>` derived from the git repository, so worktrees and subdirectories of
one repo share a directory. The layout:

```
~/.claude/projects/<project>/memory/
├── MEMORY.md           # Index, one line per memory, loaded into every session
├── user_role.md        # One memory
├── feedback_testing.md # One memory
└── ...                 # Any other topic files Claude creates
```

The **first 200 lines of `MEMORY.md`, or the first 25 KB, whichever comes
first, are loaded at session start**; content beyond that is not loaded. If
`MEMORY.md` is over the limit, the write still succeeds but the harness returns
an error telling the model to rewrite the index, "because everything past the
limit is dropped on the next load". The limit applies only to `MEMORY.md` — a
`CLAUDE.md` up to 4 MiB is loaded in full and a larger file is skipped.

Four note types are recorded as a `type` frontmatter field: `user`, `feedback`,
`project`, `reference`. The model is told to keep derivable facts (architecture,
file paths, debugging fixes) out of memory and to skip anything the CLAUDE.md
files already say. Writes to a memory file that begins with YAML frontmatter
get a `modified` frontmatter field with an ISO-8601 timestamp.

The main conversation's auto memory is **not** loaded into subagents; a
subagent's own memory is enabled with the subagent `memory` frontmatter field
(`user`/`project`/`local`) and lives in a separate directory. A *fork* of the
conversation inherits the parent's memory, because it inherits the parent
conversation.

**Clean-room opportunity.** Implement memory as an index-plus-topics layout
with an enforced read cap and an explicit "the index is over its limit" error,
give each subagent a separate memory scope, and stamp writes with a
machine-readable `modified` field. The "the write succeeds but the index must
be rewritten" contract is a good, explicit one to copy — it makes the failure
mode legible to the model instead of silently truncating memory.

### F10-26 — Legacy `.claude/commands/*.md` still load, and are counted separately from skills

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/skills.md — § "Where skills live"
**Evidence:** `agent-reference-shots/area10-skills/skill-rendering-probes.txt` P5

Fixtures: `<PROJ>/.claude/commands/deploy.md` and
`<PROJ>/.claude/commands/frontend/component.md`.

`init.slash_commands` for that session included `"deploy"` and
`"frontend:component"`, and the debug log recorded:

```
[DEBUG] Loaded 3 unique skills (3 unconditional, 0 conditional, managed: 0,
        user: 1, project: 0, additional: 0, legacy commands: 2)
```

So legacy command files are **counted separately** from skills but surface in
the same `/` command list. A nested command file's name is the subdirectory
path relative to `commands/` with each `/` replaced by `:`, plus the file name
without its extension. Command files accept the same frontmatter as a skill
**except `name` and `paths`**.

**OBSERVED-CLI** — the command-name table is confirmed by the registry:
`.claude/commands/deploy.md` → `/deploy`;
`.claude/commands/frontend/component.md` → `/frontend:component`.

**Clean-room opportunity.** Support the legacy command format as a
first-class alias of a skill with no `name`/`paths` fields, count it in a
separate bucket in the diagnostics, and apply the same `:`-namespacing rule.
Implementing the legacy path is cheap and removes a whole class of "why doesn't
my old command work" support questions.

## Area 10 capability table

| Capability | Status | Evidence | Notes |
| :- | :- | :- | :- |
| Three skill scopes + nested + `--add-dir` + plugin + synced | OBSERVED-DOC + OBSERVED-CLI | F10-1, F10-3 | Loader prints its own scope paths and per-scope counts |
| Scope precedence (enterprise > personal > project) | OBSERVED-CLI + OBSERVED-DOC | F10-2 | Resolved at name-resolution time, not load time |
| Nested `.claude/skills/` startup scope | OBSERVED-CLI | F10-3 | Ordered list of project directories, nearest first |
| `paths:`-conditioned skills | OBSERVED-CLI + OBSERVED-DOC | F10-4 | Stored in a separate "conditional" bucket |
| `disable-model-invocation` hides the description | OBSERVED-CLI | F10-5 | Typed error names the field and forbids a workaround |
| `user-invocable: false` hides the command | OBSERVED-CLI | F10-5 | Opposite of the intuitive reading |
| `skillOverrides` four states | OBSERVED-CLI + OBSERVED-DOC | F10-6 | Affects registry, menu, and model listing |
| Skill-listing character budget + overflow warning | OBSERVED-CLI + OBSERVED-DOC | F10-7 | 1% of context window; observed 6000 chars on this host |
| `skill_listing` attachment with `names` + `digests` | OBSERVED-CLI | F10-7 | Names never dropped; only descriptions |
| `SKILL.md` frontmatter field set + 3 failure modes | OBSERVED-CLI + OBSERVED-DOC | F10-8 | Unknown field ignored; bad YAML drops all fields |
| Argument substitution `$ARGUMENTS` / `$N` / `$name` | OBSERVED-CLI + OBSERVED-DOC | F10-9 | Also applied to `allowed-tools` Bash rules |
| `${CLAUDE_*}` variables | OBSERVED-CLI + OBSERVED-DOC | F10-9 | 7 variables; plugin ones plugin-only |
| Loader-side `` !`cmd` `` execution | OBSERVED-CLI + OBSERVED-DOC | F10-10 | Recognised at line start or after whitespace only |
| `disableSkillShellExecution` policy | OBSERVED-CLI + OBSERVED-DOC | F10-10 | Replaces the command with a literal marker |
| `context: fork` skill execution | OBSERVED-CLI + OBSERVED-DOC | F10-11 | Isolated context; not counted as a spawned subagent |
| Subagent frontmatter schema + skip list | OBSERVED-DOC + OBSERVED-CLI | F10-12 | camelCase; `claude plugin validate` checks a directory |
| Subagent `skills:` preloads the whole file | OBSERVED-CLI + OBSERVED-DOC | F10-13 | Frontmatter included |
| `Agent`/`Task` tool naming split | OBSERVED-CLI | F10-14 | `init.tools` says `Task`; the API request says `Agent` |
| `agent_listing_delta` incremental registry | OBSERVED-CLI | F10-15 | Built-ins vs user types separated; removal supported |
| CLAUDE.md concatenation + `@path` imports | OBSERVED-CLI + OBSERVED-DOC | F10-16 | Imports become their own attachment entries |
| `.claude/rules/` conditional injection | OBSERVED-CLI + OBSERVED-DOC | F10-17 | `nested_memory` attachment with `globs`/`rawContent` |
| AGENTS.md fallback + 4-value mode | OBSERVED-CLI + OBSERVED-DOC | F10-18 | Mode readable only from user/`--settings`/managed |
| Dynamic workflows (`agent`/`pipeline`/`parallel`) | OBSERVED-DOC | F10-20 | Not executed — feature-gated on this host |
| Output styles | OBSERVED-DOC + OBSERVED-CLI (registration) | F10-21 | Adherence UNKNOWN (non-Anthropic model) |
| Plugin manifest + validator JSON envelope | OBSERVED-CLI + OBSERVED-DOC | F10-22 | Validates directories as well as manifests |
| Plugin ids `@skills-dir` / `@builtin` / `@marketplace` | OBSERVED-CLI + OBSERVED-DOC | F10-23 | `plugin details` projects always-on vs on-invoke tokens |
| `claude agents` = background sessions | OBSERVED-CLI | F10-24 | Not the agent-definition registry |
| `claude import` | OBSERVED-CLI (unavailable) | F10-24 | Documented but gated out of this build |
| Auto memory (`~/.claude/projects/<project>/memory/`) | OBSERVED-DOC | F10-25 below | 200 lines / 25 KB index cap |
| Legacy `.claude/commands/*.md` | OBSERVED-CLI | F10-26 below | Counted separately, same `/` menu |
| Synced-from-claude.ai skills | OBSERVED-DOC only | — | Requires a claude.ai account |

## Area 10 dependencies

| Surface | Network | Account | Model provider | External service |
| :- | :- | :- | :- | :- |
| Skill / rule / subagent discovery | no | no | no | — |
| Skill rendering (substitution, injection) | **yes** for injected commands only | no | no | the skill's own command |
| `claude plugin validate` | no | no | no | — |
| `claude plugin list` / `details` | no | no | no | — |
| `claude plugin install` / `marketplace add` | yes | Anthropic account for the directory | no | the marketplace host |
| Synced skills (`~/.claude/skills/synced/`) | yes | claude.ai | no | claude.ai |
| Managed skills / managed rules | no (deployed by the org) | enterprise | no | — |
| Dynamic workflows | yes | paid plan or Anthropic API access (per doc) | yes | — |
| Output styles | no | no | yes (affects the model's answers) | — |
| AGENTS.md mode | no | no | no | — |

## Area 10 limitations of this investigation

- **Model-limited behaviour.** This host serves `minimax/minimax-m3.1-flash:free`
  through a custom `ANTHROPIC_BASE_URL`. Anything that requires the model to
  *obey* an instruction — does the output style change the tone, does the
  model choose the right skill from its listing — could not be measured as
  product behaviour. Only harness behaviour (parsing, substitution, injection,
  registration, error text) was treated as observed.
- **Workflows were not executed.** The `/deep-research` workflow and the
  workflow runtime are behind a plan/feature-flag gate that a custom-gateway
  build does not satisfy, so F10-20 is OBSERVED-DOC only.
- **claude.ai-synced skills were not observed** (no claude.ai account, and the
  host is not connected to the Anthropic API). The `~/.claude/skills/synced/`
  location, the reserved `synced` and `anthropic-skills` names, and the
  `anthropic-skills:` command prefix are documented only.
- **Enterprise/managed scope was not exercised.** The managed directory
  `C:\Program Files\ClaudeCode\.claude\skills` was observed as a search path in
  the debug log but is empty on this machine, so the enterprise-wins
  precedence was not observed in practice (only the personal-over-project
  case was).
- **Only `personal` vs `project` precedence was observed**, not
  enterprise-over-personal, because there was no enterprise skill to shadow.
- **The `disallowed-tools` / `allowed-tools` semantics were not probed
  behaviourally** — the grant-clears-next-message rule and the
  `allowManagedPermissionRulesOnly` interaction are documented but were not
  exercised, because doing so would have required running a model turn with a
  modified permission state.
- **One host-specific number**: the observed listing budget was 6,000
  characters for 17 skills. That is a function of this host's context window
  and skill mix; the documented rule (1% of the context window, 8,000-char
  fallback) is the portable statement.
- **No decompilation, no source extraction, no binary modification, no
  credential or licence-file access.** REA's decompilation facilities were
  deliberately not invoked for this target; the reverse-engineering toolset was
  used for nothing in this area.

## Area 10 unknowns

- Whether the model’s **skill-selection quality** is affected by the listing
  budget’s least-used-first truncation in a way an implementer should try to
  improve (UNKNOWN — model-limited on this host).
- The exact algorithm behind the "least-used skills" ordering: the reference
  tracks usage per skill, but the usage signal's source and decay are not
  observable from outside.
- The `digests` values in the `skill_listing` attachment: 16 hex chars, almost
  certainly a content hash, but the hash function and the comparison rule are
  not observable.
- Whether `contentDiffersFromDisk` on a `nested_memory` attachment means the
  in-memory rule differs from the file (an edit-during-session case) or is
  simply always true for rules (whose frontmatter is stripped). One probe
  cannot distinguish the two.
- The exact byte budget of the `allowed-tools` grant and whether a
  `disallowed-tools` entry can remove `EndConversation` in this build.
- Whether the `Task` → `Agent` tool rename has a compatibility shim for old
  transcripts, or whether `Task` is simply the internal name.
- Whether `claude import` is gated by plan, by build, or by feature flag, and
  what its import format is.
- The behaviour of `skillOverrides` when a skill's name changes, and of the
  `alias` mapping (the doc says an entry under an alias in *managed* settings
  applies to the skill behind the alias, but not in user/project/local
  settings — only the managed case was documented, not probed).
- The exact semantics of `force-for-plugin` when two enabled plugins both set
  it ("the first one loaded" — which plugin loads first is not observable
  without two conflicting plugins).
- Whether the workflow runtime's `agent()` schema pre-flight can reject a
  schema that is contradictory but not provably so (documented only for the
  provable case).
- The claude.ai-synced skill behaviour in every mode (terminal, Cowork, cloud,
  desktop), and the exact rule for when a synced skill's body is stripped of
  `` !`cmd` ``.

## Area 10 clean-room implementation opportunity

Recommended scope for an independent functional implementation of the
extension layer. Tier 1 is the parity core; Tier 2 is where an independent
implementation can be *better*; Tier 3 is optional.

### Tier 1 — parity core (must have)

1. **A unified extension registry.** One resolver over an ordered list of
   `(scope, path)` roots producing (a) a *loaded* set tagged by scope, (b) a
   *resolved* set keyed by command name, (c) two slash-command lists (user
   menu and terminal-only), and (d) a model-facing listing. Copy the reference's
   per-scope counters and the "skill-directory commands vs plugin skills vs
   bundled skills" split. Emit a one-line diagnostic naming every scope and
   its path — this is the single highest-value diagnostic in the whole
   product.
2. **A `SKILL.md` loader with a declared schema.** Hyphen-cased fields (or
   camelCase — pick one, enforce it), documented booleans accepting
   `yes/no/on/off/1/0`, unknown fields ignored, frontmatter stripped from the
   body, frontmatter parse failure → load with empty metadata + a loud
   diagnostic, and a machine-readable validator (`validate` subcommand,
   JSON envelope, per-file findings with `path`/`message`/`code`/`fix`).
   Support a **strict subset** profile for a packaging/upload path that hard-errors
   on unknown keys.
3. **Invocation control as two independent booleans** —
   `model_may_invoke` and `user_may_invoke` — derived into three surfaces
   (model listing, user menu, tool permission), plus a `skillOverrides`-style
   four-state override applied after frontmatter. Make the refusal error carry
   an explicit "do not achieve this another way" directive to the model.
4. **A budgeted model-facing listing.** Names always present, descriptions
   budgeted (fraction-of-context, with a fixed-char override), per-entry cap,
   least-used-first truncation, a debug warning that names the measured size,
   the budget, and the two remedies, and a `names`+`digests` sidecar for
   incremental re-sending.
5. **A template language for skill and agent bodies.** `$ARGUMENTS`, `$N`,
   `$ARGUMENTS[N]`, declared `$name`, and `${CLAUDE_SESSION_ID}` /
   `${CLAUDE_EFFORT}` / `${CLAUDE_SKILL_DIR}` / `${CLAUDE_PROJECT_DIR}` /
   `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}`. Substitute in **both**
   the body and the tool-allow rules. Never re-scan substituted values.
6. **Project instructions as an ordered, auditable list.** Managed → user →
   root-to-cwd concatenation, `CLAUDE.local.md` after `CLAUDE.md` per level,
   lazy subdirectory loading, HTML-comment stripping, `@path` imports with a
   4-hop cap and cycle detection, backtick suppression, and a per-project
   approval record for imports outside the working directory. Keep each
   instruction file's identity in the context record.
7. **A conditional instruction channel.** `.claude/rules/*.md` with `paths`
   glob scoping, brace expansion under a shared budget, frontmatter stripping,
   and injection on matching file access — emitted as a distinct attachment
   type, not concatenated into the main instruction blob.
8. **Subagents as a first-class registry.** A declared frontmatter schema, a
   documented skip list (invalid → documentation, not an error), a per-agent
   system prompt, tool allow/deny lists, model/effort/permission overrides, a
   `skills:` preload that injects the **whole** `SKILL.md`, and a `context:
   fork` mode that runs a skill in an isolated context.
9. **A delegation tool with a machine-readable ledger.** One canonical name,
   an input schema with `description`/`prompt`/`subagent_type`/`model`/
   `effort`/`run_in_background`/`isolation`, and a `subagent_stats` block with
   `spawned`, `by_type`, `completed`, `failed`, and explicit `refused`
   sub-counters for depth, concurrency, and budget.
10. **A plugin/packaging layer.** `.claude-plugin/plugin.json` with `name`
    required, the standard component layout, strict path rules (`./`-prefixed,
    inside the root, exists, no `..`), the replace/add/merge semantics per
    component key, reserved-name checks, and `<name>@<source>` ids.
11. **A validator that runs in CI.** Stable JSON envelope, three-tier result
    model, per-finding `fix` strings, and the ability to point it at a
    *components directory* as well as a manifest.

### Tier 2 — strong differentiation (do these deliberately)

12. **Make injected shell commands safe by default.** The reference executes
    `` !`cmd` `` in a skill body silently at render time. A clean-room
    implementation should default to **prompting** (or denying) for injected
    commands from untrusted sources, log every execution with its resolved
    pattern, and make the policy settable from managed configuration so an
    organisation can disable it globally. This is the single largest
    defensible improvement available in this area.
13. **Count forked skills honestly.** The reference's `subagent_stats.spawned`
    is `0` for a `context: fork` skill that demonstrably ran. Report forked
    skills in the ledger with their own counter.
14. **Make the settings scope table explicit and enforced.** The reference
    silently ignores `pluginConfigs` set in project settings. A clean-room
    implementation should either honour it everywhere or emit a
    machine-greppable warning naming the ignored scope.
15. **Ship an importer.** `claude import` is documented but unavailable in the
    reference build. Converting a competitor's agent/command definitions into
    your own format is open space.
16. **Make the always-on/on-invoke token projection first-class.** The
    reference surfaces it in `claude plugin details`; make it a per-session
    `/cost`-style view for *all* skills, with a "turn this one off" action
    wired to the override mechanism.
17. **Give the rules channel a richer match model.** Support `paths` on skills
    *and* rules with one glob implementation, one brace-expansion budget, and
    a preview command that shows which rules a given file would pull in.

### Tier 3 — nice to have

18. **Dynamic workflows.** The script-over-subagents model (pure-literal
    `meta`, banned non-determinism, hard limits that *reject* rather than
    truncate, `null` on failure, schema pre-flight) is fully specified in
    public docs and is the most copyable many-agent design available.
19. **Output styles** with the exact documented selection semantics, the
    `keep-coding-instructions` switch, and the "applies to forks, not to
    subagents" rule.
20. **Auto memory** with the `MEMORY.md` index + topic files layout, the
    200-line/25 KB cap with a "rewrite the index" error, per-scope
    (`user`/`project`/`local`) subagent memory, and a `modified` ISO-8601
    frontmatter stamp on writes.

### Explicitly not to copy

- Anthropic's bundled-skill *content* (`dataviz`, `claude-api`,
  `plugin-authoring`, …) — that is product content, not interface.
- The exact system-prompt text, internal model routing, or the proprietary
  binary.
- The reserved-name list (`claude-`, `anthropic-`, `anthropics-`,
  `cc-plugin-`) as a *legal* device; copy the mechanism (a namespace
  reservation check) but choose your own names.
- The Anthropic plugin-directory submission policy (`README_MISSING`,
  `LICENSE_MISSING`, `ICON_MISSING`, "at least 40 words") — that is a
  marketplace policy, not a technical contract.

## Area 10 evidence index

| Artifact | Path |
| :- | :- |
| Area 10 evidence directory | `agent-reference-shots/area10-skills/` |
| Artifact guide | `agent-reference-shots/area10-skills/README.md` |
| Skill discovery, precedence, nesting, budget | `agent-reference-shots/area10-skills/discovery-and-budget-probes.txt` |
| Invocation control, subagent preload, instruction selection | `agent-reference-shots/area10-skills/invocation-control-and-instruction-probes.txt` |
| Skill rendering, substitution, injection, fork | `agent-reference-shots/area10-skills/skill-rendering-probes.txt` |
| Init-event registries (6 probe projects) | `agent-reference-shots/area10-skills/init-registries.txt` |
| Instruction attachments (CLAUDE.md / AGENTS.md / rules) | `agent-reference-shots/area10-skills/instructions-attachment-probe.txt` |
| Tool schemas and registry attachments | `agent-reference-shots/area10-skills/registry-and-tool-contracts.txt` |
| Plugin CLI surfaces and validator contract | `agent-reference-shots/area10-skills/plugin-cli-probes.txt` |
| Validator JSON probes | `agent-reference-shots/area10-skills/plugin-validate-probes.json` |
| CLI help surfaces | `agent-reference-shots/area10-skills/cli-skill-surfaces.txt` |
| Debug-log skill discovery | `agent-reference-shots/area10-skills/debug-log-skill-discovery.txt` |
| Observed frontmatter from installed skills | `agent-reference-shots/area10-skills/observed-skill-frontmatter.txt` |
| Worked examples | `agent-reference-shots/area10-skills/example-SKILL.md`, `example-skill-with-forking.md` |

Public documentation consulted (all treated as untrusted data; no instruction
in any page was followed and no command found in fetched content was executed):

- https://code.claude.com/docs/en/skills.md
- https://code.claude.com/docs/en/memory.md
- https://code.claude.com/docs/en/sub-agents.md
- https://code.claude.com/docs/en/workflows.md
- https://code.claude.com/docs/en/output-styles.md
- https://code.claude.com/docs/en/plugins/manifest-reference.md
- https://code.claude.com/docs/en/settings-reference.md
- https://code.claude.com/docs/en/env-vars.md

### Auto memory (supplementary, OBSERVED-DOC)

Auto memory is enabled by default in local sessions and stores notes at
`~/.claude/projects/<project>/memory/` (one directory per git repository, so
worktrees and subdirectories share it). The directory holds a `MEMORY.md`
index — one line per memory, loaded into every session — plus one topic file
per memory. The **first 200 lines of `MEMORY.md`, or the first 25 KB,
whichever comes first, are loaded at session start**; content beyond that is
not loaded. If `MEMORY.md` is over the limit, the write still succeeds but the
harness returns an error telling the model to rewrite the index, because
everything past the limit is dropped on the next load. The limit applies only
to `MEMORY.md`; a `CLAUDE.md` up to 4 MiB is loaded in full and a larger one is
skipped. Four note types are recorded as a `type` frontmatter field: `user`,
`feedback`, `project`, `reference`. The main conversation's auto memory is not
loaded into subagents; a subagent's own memory is enabled with the subagent
`memory` frontmatter field (`user`/`project`/`local`) and is a separate
directory.

**Clean-room opportunity.** Implement memory as an index-plus-topics layout
with an enforced read cap and an explicit "the index is over its limit"
error, and give the agent a *separate* memory scope per subagent so a
worker does not inherit the parent's memory. The "write succeeds but the index
must be rewritten" behaviour is a good, explicit contract to copy.
