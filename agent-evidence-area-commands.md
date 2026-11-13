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
