
---
---

# Area #3 — Planning, Task Decomposition, Implementation, and Iterative Problem-Solving

**Investigator scope:** #3. **Product:** Claude Code 2.1.306 (native build, win32-x64, commit `01ae8327ca99`).
**Method:** public documentation at `code.claude.com/docs/en/...` plus black-box exercise of the published CLI's own help and inspection surfaces and headless (`-p`) runs. **No decompilation, no source extraction, no binary modification, no credential or keychain access.**

> **Environment caveat carried through every finding below.** This machine's Claude Code runs against a custom `ANTHROPIC_BASE_URL` (a third-party gateway serving a non-Anthropic model), not `api.anthropic.com`. `claude doctor` reports "Not connected to the Anthropic API", "Not signed in to claude.ai", and "Organization not resolved". Consequently **all subscription-gated behaviour is INFERRED from docs, not OBSERVED**, and the concrete runtime here is a different model. Where a finding depends on a subscription-only feature, that is stated explicitly.

## Area 3 Executive Summary

Claude Code exposes planning and decomposition as **four cooperating surfaces**, not one:

1. **A permission mode, not a command.** Plan mode is a session-level mode (`--permission-mode plan`, `Shift+Tab`, or `/plan`). In it the agent may read, search, and run exploratory shell commands, but edits to source are blocked. The agent is expected to emit a plan artifact and then request approval through a dedicated `ExitPlanMode` tool, which surfaces a three-way user choice. The plan is additionally written to a Markdown file on disk (observed: `~/.claude/plans/<slug>.md`), which makes it reviewable outside the TUI.
2. **A structured task list** (`TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate`, with `TodoWrite` as a legacy alternative) that models a *DAG*, not just a checklist: tasks carry `subject`, `description`, `activeForm`, `status`, and dependency edges (`addBlockedBy`). This is the machine-readable substrate for decomposition.
3. **A delegation tool** (`Agent`, formerly `Task`) that spawns a subagent in a **separate context window** with a tool allowlist, its own model/effort, a turn budget (`maxTurns`), and a fresh-vs-fork context choice. Six built-in subagent types ship: `Explore`, `Plan`, `general-purpose`, `claude`, `statusline-setup`, `claude-code-guide`.
4. **A goal/continuation loop** (`/goal`, dynamic workflows, `/batch`, agent teams) for work that must continue past one turn without the user prompting each step.

The unifying idea, stated in the docs and consistent with what I observed: **the plan lives outside the model.** It lives in a permission mode's blocked state, in a file, in a task table, in a script. That is the single most transferable design insight in this area, and it is the one an independent implementation should copy first.

**Most important clean-room conclusion:** you can reproduce the *entire user-visible function* of plan mode, task lists, and subagent delegation using four primitives that are all public and generic — (a) a permission gate on mutating tools, (b) a JSON-file task table with dependency edges, (c) a child-process/thread worker with a fresh context window and a tool allowlist, and (d) a Markdown plan artifact the user can open in an editor. None of that requires copying any Anthropic implementation.

## Area 3 Findings

### F3-1 — Plan mode is a permission mode with a blocked-mutation invariant

**Status: OBSERVED-DOC + OBSERVED-CLI**

Docs (`https://code.claude.com/docs/en/permission-modes.md`, section "Analyze before you edit with plan mode"):

> "Plan mode tells Claude to research and propose changes without making them. Claude reads files, runs shell commands to explore, and writes a plan, but does not edit your source. Except in interactive terminal sessions with bypass permissions available, edits stay blocked until you approve the plan."

Entry points, verbatim from docs and confirmed in the CLI help:

| Entry point | Exact form | Source |
| - | - | - |
| CLI flag | `claude --permission-mode plan` | OBSERVED-CLI (`claude --help` lists `--permission-mode <mode>` with choices `acceptEdits, auto, bypassPermissions, manual, dontAsk, plan`) |
| In-session key | `Shift+Tab` until the status bar shows `⏸ plan mode on` | OBSERVED-DOC |
| Slash command | `/plan [description]` — "Enter plan mode directly from the prompt. Pass an optional description to enter plan mode and immediately start with that task" | OBSERVED-DOC (`https://code.claude.com/docs/en/commands.md`) |
| Project default | `"defaultMode": "plan"` in `.claude/settings.json` (nested under `permissions`); VS Code equivalent is `claudeCode.initialPermissionMode` | OBSERVED-DOC |

Shift+Tab cycle order is documented precisely:

> "press `Shift+Tab` to cycle permission modes. From `auto`, the first press switches to `default`, and the cycle then runs `default` → `acceptEdits` → `plan`. Optional modes slot in after `plan`."

Status-bar strings, verbatim: `⏸ manual mode on` (for `default`), `⏵⏵ accept edits on`, `⏸ plan mode on`, `⏵⏵ auto mode on`, `⏵⏵ don't ask on`, `⏵⏵ bypass permissions on`.

**Direct observation (OBSERVED-CLI).** Two headless runs:

```
$ claude -p --permission-mode plan "Create a file called demo-plan.txt containing exactly the text: hello plan" --output-format=json
```

Result: the model wrote a plan to `C:\Users\Admin\.claude\plans\create-a-file-called-jaunty-shell.md` and reported "the plan is written and ready". `demo-plan.txt` was **not** created — verified by directory listing. `permission_denials` was `[]` (the block is a mode invariant, not a prompt denial). A second run produced the same outcome with a different slug (`create-a-file-called-groovy-sloth.md`).

Note the *side effect that matters*: the plan file **was** written even though the target file was not. The plan artifact path is outside the "no edits" invariant.

**Clean-room opportunity.** Implement plan mode as a *tool-gating flag*, not a special code path. Concretely: a session flag `editsBlocked` consulted by the dispatcher before any mutating tool (`Write`, `Edit`, `NotebookEdit`) executes; non-mutating tools (`Read`, `Grep`, `Glob`, `Bash` on a read-only allowlist) pass through. Approval = clearing the flag. This is ~30 lines and reproduces the entire observable behavior. The choice of where to put the plan artifact is yours; a Markdown file under a per-user directory is a reasonable independent design.

### F3-2 — The plan-approval decision is a three-way user choice, mediated by a dedicated `ExitPlanMode` tool

**Status: OBSERVED-DOC (the UI); OBSERVED-CLI (the tool's absence in this environment)**

Docs, verbatim:

> "When the plan is ready, Claude presents it and asks how to proceed. From that prompt you can choose:
> * **Yes, and use auto mode**: approve and start in auto mode. If auto mode isn't available to your session ... this option reads **Yes, auto-accept edits**. If you started the session with bypass permissions enabled, the option reads **Yes, and switch to BYPASS PERMISSIONS (no further prompts) for this session** instead.
> * **Yes, manually approve edits**: approve and review each edit individually.
> * **No, keep planning**: stay in plan mode and tell Claude what to change."

Additional documented mechanics:
- "Approving a plan exits plan mode and switches the session to the permission mode each approve option describes, so Claude starts editing."
- "Press `Ctrl+G` to open the proposed plan in your default text editor and edit it directly before Claude proceeds."
- "When [`showClearContextOnPlanAccept`] is enabled, the list gains a first option that approves the plan and clears the planning context." (setting key default `false`; OBSERVED-DOC `https://code.claude.com/docs/en/settings-reference.md`)
- "Accepting a plan also gives the session a generated title based on the plan, unless you've already named the session."
- Plan-mode shell handling is three-tiered: with bypass permissions available nothing is checked; with auto mode available and `useAutoModeDuringPlan` on (default `true`), a classifier reviews commands; otherwise commands outside the read-only set prompt.

**Direct observation (OBSERVED-CLI).** In both headless plan-mode runs the model explicitly reported that `ExitPlanMode` and `AskUserQuestion` were **not in the session's tool list** and that `ToolSearch` (including `select:ExitPlanMode`) returned no match — so it could not formally request approval. This is a real, load-bearing observation: **the approval affordance is a tool, and a harness that omits it leaves the agent in a degraded, prose-only state** (it falls back to writing a plan file and narrating an approval request in text).

The tool set is discoverable at runtime via `ToolSearch` (a deferred-tool loader) — in this session's own tool list, `ToolSearch` is present alongside `TaskStop`, `Monitor`, `ScheduleWakeup`, `SendMessage`, `ListAgents`, `EnterWorktree`/`ExitWorktree`, `Workflow`, `ReportFindings`, `Artifact`-family and the `mcp__rea__*` set.

**Clean-room opportunity.** Ship an explicit `submit_plan` / `exit_plan_mode` tool whose schema carries the plan text, the files to be touched, and the proposed verification steps. The harness (not the model) should render the three-way choice, map the answer back onto the session's permission mode, and clear the edit gate. Also ship a `ask_user` tool for clarifying questions — a plan agent without one is materially less useful, as observed.

### F3-3 — Plans are written to a Markdown artifact on disk with a machine-generated slug

**Status: OBSERVED-CLI**

Both headless plan-mode runs wrote a plan file into `C:\Users\Admin\.claude\plans\`:

```
create-a-file-called-groovy-sloth.md   (1498 bytes)
create-a-file-called-jaunty-shell.md
```

The filename pattern is `<first-few-words-of-the-prompt>-<adjective>-<noun>.md` — a content-addressed-ish human-readable slug. The settings reference documents the location as configurable:

> `plansDirectory` | String path | Unset; effective default is `~/.claude/plans` | "Choose where plan mode writes plan files"

The observed file body is a well-structured Markdown plan with these sections (verbatim headings from `observed-plan-file.md`):

```markdown
# Plan: create `demo-plan.txt`

## Context
...
## Implementation
...
## Files
- **Created:** `demo-plan.txt` (new file, project root)
## Verification
1. Read `C:\Users\Admin\Desktop\Claude clone\demo-plan.txt` with the Read tool and confirm the content is exactly `hello plan`.
```

Note the plan is *self-verifying*: it names the exact verification step it will run after approval. This is a design pattern worth copying — a plan that declares its own acceptance check.

**Clean-room opportunity.** Write the plan to a per-project directory as Markdown with a stable, human-readable name; render it in the TUI with a "open in editor" affordance; and require the plan to include an explicit verification section. None of this is Anthropic-specific.

### F3-4 — Task decomposition is a real DAG with dependency edges, not a flat checklist

**Status: OBSERVED-DOC + OBSERVED-CLI**

The task-tracking tool family is documented at `https://code.claude.com/docs/en/tools-reference.md` and `https://code.claude.com/docs/en/agent-sdk/todo-tracking.md`:

- `TaskCreate` — "Creates a new task in the task list."
- `TaskGet` — "Retrieves full details for a specific task."
- `TaskList` — "Lists all tasks with their current status."
- `TaskUpdate` — "Updates task status, dependencies, details, or deletes tasks."
- `TodoWrite` — "Manages the session task checklist. Disabled by default in favor of `TaskCreate`, `TaskGet`, `TaskList`, and `TaskUpdate`. Set `CLAUDE_CODE_ENABLE_TASKS=0` to re-enable it."

Documented lifecycle, verbatim:

> 1. **Created**: Claude adds the todo as `pending` when it identifies a task
> 2. **Activated**: Claude sets the todo to `in_progress` when it starts the work
> 3. **Completed**: Claude marks it completed when the task finishes successfully
> 4. **Removed**: Claude deletes a todo it no longer needs by setting `status: "deleted"` in a `TaskUpdate` call

When the agent creates todos (verbatim): "Complex multi-step tasks requiring three or more distinct actions"; "User-provided task lists when multiple items are mentioned"; "Longer operations that benefit from progress tracking"; "Explicit requests when users ask for todo organization." And: "Claude may skip todos for very short or single-step requests."

Agent-teams docs add the dependency semantics (OBSERVED-DOC, `https://code.claude.com/docs/en/agent-teams.md`):

> "Tasks have three states: pending, in progress, and completed. Tasks can also depend on other tasks: a pending task with unresolved dependencies cannot be claimed until those dependencies are completed."
> "Task claiming uses file locking to prevent race conditions when multiple teammates try to claim the same task simultaneously."

**Direct observation (OBSERVED-CLI).** I ran a live session with the task tools enabled and captured the raw `tool_use` inputs. Verbatim excerpt (full file: `agent-reference-shots/area3-planning/observed-task-tool-calls.txt`):

```
TaskCreate {"subject":"Write todo-proof.txt","description":"Create the file todo-proof.txt in <WORKDIR> with simple content.","activeForm":"Writing todo-proof.txt"}
TaskCreate {"subject":"Read todo-proof.txt back","description":"...","activeForm":"Reading todo-proof.txt"}
TaskCreate {"subject":"Report results","description":"...","activeForm":"Reporting results"}
TaskUpdate {"taskId":"2","addBlockedBy":["1"]}
TaskUpdate {"taskId":"3","addBlockedBy":["2"]}
TaskUpdate {"taskId":"1","status":"in_progress"}
TaskList   {}
```

This confirms, first-hand: the field vocabulary is `subject` / `description` / `activeForm` / `status` / `taskId` / `addBlockedBy`; `TaskCreate` carries **no id in its input** (the id is assigned by the runtime and arrives in the `tool_result` payload as `tool_use_result.task.id`); and the agent spontaneously wired a linear dependency chain before executing anything.

**Clean-room opportunity.** Model the task list as a table with columns `{id, subject, description, activeForm, status, blockedBy, blocks}` persisted to a JSON file. Give the model a `create_task` / `update_task` / `list_tasks` tool triple. Support `blockedBy` edges and refuse to start a task with unresolved dependencies. This is a straightforward, entirely generic design — but note the *ergonomic* detail that pays off: `activeForm` (present-continuous, e.g. "Writing todo-proof.txt") is what the UI shows for the in-progress row, while `subject` (imperative, e.g. "Write todo-proof.txt") is what the list shows for a pending row. Using one string for both reads badly.

### F3-5 — Task-list rendering is a toggled, compact, persistent status widget

**Status: OBSERVED-DOC**

From `https://code.claude.com/docs/en/interactive-mode.md`, section "Task list" (verbatim):

> "The task list is Claude's to-do checklist: items Claude created to plan multi-step work, with indicators showing what's pending, in progress, or complete. It's separate from the background-task view. To see running shells and subagents, use `/tasks` instead."

Behavior:
- "Press `Ctrl+T` to toggle the task list view. The display shows up to five tasks at a time. When Claude hasn't created any checklist items yet, the toggle has no visible effect because there's nothing to display."
- "If you leave the list expanded, Claude Code restores the expanded view the next time you launch into a session that still has tasks, such as with `--resume` or `--continue`. When the task list is empty, Claude Code starts it collapsed."
- "To see all tasks or clear them, ask Claude directly: 'show me all tasks' or 'clear all tasks'."
- "Tasks persist across context compactions, helping Claude stay organized on larger projects."
- "To share a task list across sessions, set `CLAUDE_CODE_TASK_LIST_ID` to use a named directory in `~/.claude/tasks/`: `CLAUDE_CODE_TASK_LIST_ID=my-project claude`"

`Ctrl+T` is also documented in the general-controls table: "Toggle Claude's task checklist | Show or hide Claude's to-do checklist in the status area. This is not the background-task view; use `/tasks` to see running shells and subagents".

The SDK docs give the canonical rendering recipe an implementer can copy conceptually (verbatim from `https://code.claude.com/docs/en/agent-sdk/todo-tracking.md`):

> "The summary counts completed and in-progress tasks and shows each active item's `activeForm` label in place of its `subject`."

**Clean-room opportunity.** Render a collapsible widget above the prompt showing up to N tasks with per-status glyphs, persisting its expanded state in session metadata, and — importantly — persist the task table itself outside the context window so it survives compaction and resume. The `CLAUDE_CODE_TASK_LIST_ID` idea (a named task directory so a task list can be shared across sessions) is a clean, generic mechanism.

### F3-6 — Task-tracking tools are *gated by model*, and the gate is user-overridable

**Status: OBSERVED-CLI (verified directly) + OBSERVED-DOC**

This is the most surprising and most directly useful finding for an implementer.

Docs (`tools-reference.md`, "Task tool availability", and `agent-sdk/todo-tracking.md`):

> "The task-tracking tools, `TaskCreate`, `TaskGet`, `TaskUpdate`, `TaskList`, and `TodoWrite`, are available by default only on Opus 4.7, Sonnet 4.6, Haiku 4.5, and earlier models. Wherever the tools are available, you get the four Task tools, or `TodoWrite` instead when you set `CLAUDE_CODE_ENABLE_TASKS=0`."

> "Newer models track multi-step work without a written todo list, so on those you don't need anything on this page for Claude to work through multi-step tasks."

> "On a model that doesn't have the tools by default, unless you opt a session in, you see no `tool_use` blocks for them in the message stream."

**Direct verification (OBSERVED-CLI).** Two runs on this machine (non-Anthropic model via the custom gateway):

```
$ claude -p "Output ONLY the tool names available to you, one per line" --output-format=json
FOUND: ['Agent']                       # no TodoWrite / TaskCreate / TaskGet / TaskList / TaskUpdate

$ CLAUDE_CODE_ENABLE_TODO_TOOLS=1 claude -p "Output ONLY the tool names available to you ..." --output-format=json
FOUND: ['TaskCreate', 'TaskGet', 'TaskList', 'TaskUpdate', 'Agent']
```

The opt-in levers documented are: name one of the tools in `allowedTools` / `allowed_tools`; list them in the `tools` option; or set `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` in `env`.

**Interpretation (INFERRED).** The reasoning: on models with a strong native long-horizon planning ability, an explicit written task list is redundant and costs context; on weaker/older models it is a scaffold that measurably improves reliability. The task tools are therefore a *fallback scaffold*, exposed conditionally. An independent implementation should treat its own task list as always-on (or similarly gated) — but should be aware that a modern model may not use it, so the harness must not *depend* on it for correctness.

**Clean-room opportunity.** Expose the task tools unconditionally, or gate them behind a config flag rather than a model-identity check (model identity is a fragile gate for a third-party provider — this very session demonstrates the failure mode: an unrecognized model gets no task tools by default, which is exactly the case where a scaffold helps most).

### F3-7 — `Agent` (formerly `Task`) spawns a subagent in a separate context window with an enforced tool allowlist

**Status: OBSERVED-DOC + OBSERVED-CLI**

Docs (`https://code.claude.com/docs/en/sub-agents.md`):

> "In version 2.1.63, the Task tool was renamed to Agent. Existing `Task(...)` references in settings and agent definitions still work as aliases."

Invocation fields (verbatim table): `description`, `prompt`, `subagent_type`, `model`, `effort`, `resume`, `max_turns`, `run_in_background`, `name`, `isolation` (can request an isolated `worktree`).

Tool-resolution rules (verbatim, `tools-reference.md` "Agent tool behavior"):

> - **Neither field set**: the subagent inherits every tool available to subagents.
> - **`tools` only**: the subagent gets only the listed tools.
> - **`disallowedTools` only**: the subagent gets every parent tool except the listed ones.
> - **Both set**: `disallowedTools` takes precedence. A tool listed in both is removed.
>
> "In every case, the resolved set is limited to the tools available to subagents: a tool that isn't available to subagents is never granted, even when listed in `tools`."

> "If every entry in a subagent's `tools` list fails to match a usable tool, the Agent tool usually returns an error naming the entries instead of launching the subagent."

Subagent frontmatter (Markdown + YAML) — exact documented fields: `name` (required, ≤256 chars), `description` (required), `tools`, `disallowedTools`, `model` (`sonnet`/`opus`/`haiku`/`fable`/full model ID/`inherit`), `permissionMode` (`default`/`acceptEdits`/`auto`/`dontAsk`/`bypassPermissions`/`plan`/`manual`), `maxTurns`, `autoCompactWindow` (100000–1000000), `skills`, `mcpServers`, `hooks`, `memory` (`user`/`project`/`local`), `background`, `omitClaudeMd`, `effort` (`low`/`medium`/`high`/`xhigh`/`max`), `isolation` (`worktree`), `color`, `initialPrompt`, `experimental.cacheTtl` (`5m`/`1h`). "Unrecognized frontmatter fields are ignored without an error." The Markdown body becomes the system prompt. File locations, in precedence order: managed settings dir > `--agents` flag > `.claude/agents/` > `~/.claude/agents/` > plugin `agents/` dir.

**Direct observation (OBSERVED-CLI).** I asked a live session to delegate to the `Explore` subagent. The `subagent_stats` block in the `--output-format=json` result was:

```json
{"spawned":1,"requested":{"background":0,"foreground":0,"unset":1},
 "started_in_background":1,"max_depth":1,"spawned_by_subagents":0,
 "completed":1,"failed":0,
 "killed":{"parent":0,"user":0,"system":0},
 "refused":{"depth_limit":0,"concurrency_limit":0,"budget":0},
 "by_type":{"Explore":1}}
```

Two things this pins down precisely:
- `requested.unset = 1` with `started_in_background = 1` confirms the documented default: **"With nothing configured, a subagent that Claude spawns from the main conversation starts in the background."**
- The `subagent_stats` block is a *first-class observable* in the JSON output format — a machine-readable accounting of spawns, completions, failures, kills, and refusals (with `refused` broken out by `depth_limit` / `concurrency_limit` / `budget`). An independent implementation should emit an equivalent telemetry block; it is the only way a CI caller can tell "the agent delegated 3 times and all 3 succeeded" from "it delegated 0 times."

Model resolution order for subagents (verbatim): 1) per-invocation `model` → 2) subagent frontmatter `model` (`inherit` selects the main model) → 3) `CLAUDE_CODE_SUBAGENT_MODEL` → 4) main conversation's model. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` overrides definition and invocation models.

**Clean-room opportunity.** A subagent is: a fresh context window + a system prompt from a file + a tool allowlist + a model choice + a turn budget + a result channel back to the parent. Implement it as a worker that receives a `Context` object (fresh transcript, own token budget, filtered tool registry) and returns a single structured report. Emit per-run telemetry (spawned/completed/failed/refused-by-reason). Do not expose the parent's conversation to the child except via an explicit "fork" mode.

### F3-8 — Built-in subagent types are a fixed, documented set; `Explore` and `Plan` are read-only and one-shot

**Status: OBSERVED-CLI (the set) + OBSERVED-DOC (the semantics)**

Docs list exactly six built-in types: `Explore`, `Plan`, `general-purpose`, `claude`, `statusline-setup`, `claude-code-guide`. "`Explore` and `Plan` are read-only: `Write` and `Edit` are denied."

**Direct observation (OBSERVED-CLI).** I asked a live session to list its built-in subagent types. It answered with exactly:

```
Agent
claude
Explore
general-purpose
Plan
statusline-setup
fork
ListAgents
SendMessage
TaskStop
Monitor
ScheduleWakeup
```

This matches the documented set plus `fork` (a mode of the Agent tool), and confirms the built-ins are exposed to the model as `subagent_type` values without the model needing to know file paths.

Additional documented semantics (OBSERVED-DOC, `sub-agents.md`):
- "An Agent tool call that omits `subagent_type` fails with `subagent_type is required` when the session has no `general-purpose` subagent to fall back on."
- Per-subagent denial: `"permissions": {"deny": ["Agent(Explore)", "Agent(my-custom-agent)"]}` or `claude --disallowedTools "Agent(Explore)"`.
- Allowlisting which subagents an agent may spawn: `tools: Agent(worker, researcher), Read, Bash`.
- "By default, subagents may nest up to three layers below the main conversation" (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3; set `1` to turn nesting off).
- "The built-in Explore and Plan agents are one-shot and return no agent ID, so Claude can't resume them." (Other agents are resumable via `SendMessage` with the agent's ID or name.)
- A subagent does **not** receive: "the main conversation's history, previously invoked skills, previously read files, output style, or main conversation's auto-memory." It *does* receive: its own system prompt, the delegation message, the applicable `CLAUDE.md` hierarchy, a Git-status snapshot, listed skills, and a sibling-agent roster.
- Model resolution: `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` forces a single model for every subagent.

**Clean-room opportunity.** Ship two read-only built-in roles from day one — a **scout/explorer** (search + read only, returns a summary) and a **planner** (read-only, returns a plan) — plus one generalist. This is the minimal set that covers the observed use cases, and the read-only role is a safety property worth copying exactly: a child that cannot write cannot corrupt the parent's work.

### F3-9 — Concurrency and nesting are bounded, with documented failure signals

**Status: OBSERVED-DOC**

From `sub-agents.md` ("Limits"):

> "By default, when 20 subagents are running in a session, spawning another with the Agent tool fails with `Concurrent subagent limit reached`"
> "To change the limit, set `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` to any positive whole number."
> "There's no limit on the total number of subagents Claude can spawn over a session."

Nesting: "By default, a subagent can spawn subagents of its own, up to three layers below the main conversation." (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3.)

Resume subtlety (verbatim): "Resuming a subagent that already finished takes a fresh slot without checking the limit, so resumes can push the running count past it."

Dynamic workflows add a separate, tighter budget (OBSERVED-DOC, `https://code.claude.com/docs/en/workflows.md`): "Up to 16 concurrent agents by default, fewer when Claude Code has fewer CPUs available" (`CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`, 1–256); "Up to 4,096 items in a single `parallel()` or `pipeline()` call"; "1,000 agents total per run"; and a "Large workflow" advisory warning at ">25 agents" or ">1.5 million" projected tokens.

**Clean-room opportunity.** Bound concurrency with a semaphore, and — importantly — make the refusal *legible*: the observed `subagent_stats.refused` object breaks refusals out by `depth_limit` / `concurrency_limit` / `budget`. A refusal that returns only a generic error teaches the model nothing; a refusal that names the limit teaches it to wait or to do the work inline.

### F3-10 — Fork mode: a subagent that inherits the parent conversation, and the default

**Status: OBSERVED-DOC**

> "Fork mode is on by default. To turn it off: `{"env": {"CLAUDE_CODE_FORK_SUBAGENT": "0"}}`"
> "Claude can start a fork on its own while fork mode is on, as it is by default."
> "a fork sees the same system prompt, tools, model, and message history as the main session"
> "The fork's own tool calls still stay out of your conversation and only its final result comes back"

User-facing command: `/subtask <task>` — "Spawn a forked subagent: a background subagent that inherits the full conversation and works on the task while you keep working. Its result returns to this conversation when it finishes." (`/fork` is the separate command for copying the conversation into a background *session*.)

**Clean-room opportunity.** Two spawn modes, one parameter: `context: "fresh" | "fork"`. Fresh = empty transcript, only the delegation prompt. Fork = copy of the parent transcript. The fork mode is the more useful default for "research this while I keep working" tasks; the fresh mode is the right default for "review this independently" tasks. Note the copy-on-write requirement: the fork must not write into the parent's history.

### F3-11 — The agent's iterative loop is the documented *gather context → take action → verify results* cycle

**Status: OBSERVED-DOC**

From `https://code.claude.com/docs/en/how-claude-code-works.md`:

> "When you give Claude a task, it works through three phases: **gather context**, **take action**, and **verify results**. These phases blend together."

The canonical worked example (verbatim):

> "1. Run the test suite to see what's failing
> 2. Read the error output
> 3. Search for the relevant source files
> 4. Read those files to understand the code
> 5. Edit the files to fix the issue
> 6. Run the tests again to verify"

And the verification principle from `https://code.claude.com/docs/en/best-practices.md`:

> "Claude stops when the work looks done. Without a check it can run, 'looks done' is the only signal available, and you become the verification loop... Give Claude something that produces a pass or fail, and the loop closes on its own."
>
> "Have Claude show evidence rather than asserting success: the test output, the command it ran and what it returned, or a screenshot of the result."

And the recommended four-phase user workflow (verbatim headings): "**1. Explore**" → "**2. Plan**" → "**3. Implement**" → "**4. Commit**", with "Press `Ctrl+G` to open the plan in your text editor for direct editing before Claude proceeds" as the plan-editing affordance.

Interruption and steering (verbatim): "Press `Esc` to stop Claude immediately. The running tool call is canceled and Claude waits for your next instruction." / "Type a correction and press `Enter` without stopping Claude. The message shows as queued in the conversation. If Claude is running tool calls, it reads the message as soon as those calls finish, within the same turn, and adjusts before its next step."

**Clean-room opportunity.** The harness must (a) close the tool-result loop — every tool call must produce a result the model can read, including failures, and (b) provide a deterministic stop. The "verify loop" idea is generic: expose a `run_check` affordance, and let the model loop until it passes. The steering mechanism (queue a message; the harness delivers it at the next tool boundary, mid-turn) is a small, high-value feature: it converts a frustrating "stop and retype" into a smooth correction.

### F3-12 — Failure handling is *recorded in the task list*, not just narrated

**Status: OBSERVED-CLI (the most concrete failure-recovery evidence I gathered)**

In the live task-tool run, the agent hit a real blocker: the file write was waiting on an unapproved permission, and the PowerShell route failed with "command line is too long". The agent's response was to **update the task's description in place** to record the blocker, then **create a new task** for the unblocking action:

```
TaskUpdate {"taskId":"1","description":"Create todo-proof.txt in <WORKDIR> with simple content.
            BLOCKED: the Write tool and all shell routes (PowerShell tool is erroring with
            \"command line is too long\"; Bash redirect and touch need approval) are pending a
            permission grant that has not been approved. Retry once permission is granted.",
            "taskId":"1"}
TaskCreate {"subject":"Approve write permission for todo-proof.txt",
            "description":"Grant the pending file-creation permission for <WORKDIR>\\todo-proof.txt
                           so task #1 can complete. Blocked until the user approves the write prompt.",
            "activeForm":"Waiting on write-permission approval"}
```

**Interpretation (INFERRED).** The task list doubles as the agent's *working memory of obstacles*. Because the list is persisted outside the context window and survives compaction, recording "why this step is stuck" there is a durable, machine-readable form of the failure state. This is why a task list is a *dependency* of reliable long-horizon work rather than a nicety. The reasoning: a narrative sentence in the transcript competes for attention with dozens of other transcript tokens; a task description does not, and the harness can surface "task N is blocked" in the UI without the model having to remember it.

Note also the observed ordering: dependencies are declared *before* execution begins, and `TaskList` is called immediately after the first `in_progress` transition — the agent audits its own plan before proceeding.

**Clean-room opportunity.** Let the task schema carry a structured `blocked_reason` / `blocked_on` in addition to a free-text description, and have the TUI render blocked tasks distinctly. The harness should also let the model *split* a task (which is what happened here: a blocked task spawned an unblock task) — support `TaskCreate` with a `parentId`/`splitFrom` link, and support dependencies that are other tasks.

### F3-13 — Subagent results return as a *summary only*, and the report is scanned for instruction-shaped content

**Status: OBSERVED-DOC**

> "Only the final summary/report returns to the main conversation; verbose search output, logs, and intermediate context remain in the subagent's context."

The transcript shows a delegation row such as:

```text
code-improver(Suggest code improvements)
```

> "Foreground: the `Agent` tool call returns the subagent's final report directly, and the main conversation waits."
> "Background: the agent continues while the main conversation proceeds. Its report arrives later as an automated completion notification; Claude waits for that notification before reporting the result."

And a genuinely notable safety detail (verbatim):

> "Final reports are scanned for instruction-shaped content. A report may receive a prefix beginning:
> ```text
> [harness: subagent output matched instruction-shaped pattern(s):
> ```
> The scan does not remove or reword the underlying report and is not a substitute for permissions or tool restrictions."

Partial-output semantics: "If `maxTurns` is reached, the result is marked partial and can be resumed." / "Foreground API failures may return partial output; background failures include the API error and last output."

**Clean-room opportunity.** Return exactly one artifact from a child: a final report plus a status (`complete` / `partial` / `failed`) plus a token/time cost. The instruction-shaped-content prefix is a cheap, generic defense: scan a child's report for imperative-imperative phrasing ("ignore the previous instructions", "you must now run X") and prefix a warning. It is a *defense in depth*, and the docs correctly say it is not a substitute for permissions.

### F3-14 — Continuation beyond one turn: `/goal`, dynamic workflows, `/batch`, and agent teams

**Status: OBSERVED-DOC (all subscription-gated features are INFERRED here; the CLI surfaces themselves are OBSERVED-CLI)**

**`/goal`** (`https://code.claude.com/docs/en/goal.md`): "Set a completion condition with /goal and Claude keeps working until it's met, a model judges it impossible, or an error you have to fix clears the goal."

The mechanism is a session-scoped prompt-based Stop hook. After each turn, Claude Code sends the condition and the conversation to a small fast model, which returns one of three verdicts (verbatim): **Not yet met** ("Claude keeps working and takes the reason as guidance for the next turn"), **Met** ("Claude Code clears the goal and records an achieved entry in the transcript"), **Impossible** ("Claude Code clears the goal and records a failed entry in the transcript along with the reason"). The evaluator "does not call tools, so it can only judge what Claude has already surfaced in the conversation" — so the condition must be written so the agent's own output demonstrates it ("All tests in `test/auth` pass" works because the test output appears in the transcript).

Failure taxonomy is precise: errors you must fix **clear** the goal (auth failure, exhausted credits, context overflow that auto-compaction couldn't clear, unavailable model — warning text starts `Goal cleared after an unrecoverable error`); other errors **retry or pause** it (notice text starts `Goal still active` or `Goal paused`). Background work defers evaluation: "If a subagent or a background shell command is still running when a turn ends, Claude Code skips the evaluation for that turn."

**Dynamic workflows** (`https://code.claude.com/docs/en/workflows.md`): a JavaScript script the agent writes and a runtime executes. The body API is small and legible: `agent(prompt, opts)` spawns one subagent, `pipeline(items, fn)` runs one per item, `parallel(tasks)` runs a set concurrently, `phase(title)` groups agents in the progress view, `log(msg)`, plus a `meta` block (`name`, `description`, optional `phases`) and a global `args`. Constraints (verbatim): "No mid-run user input"; "No direct filesystem or shell access from the workflow itself"; "No module loading: a script that contains `import()` fails before the run starts"; `Date.now()`, `Math.random()`, and `new Date()` **throw** so a relaunched run is deterministic.

**`/batch <instruction>`** (OBSERVED-DOC, `commands.md`): "Researches the codebase, decomposes the work into 5 to 30 independent units, and presents a plan. Once approved, spawns one background subagent per unit in an isolated worktree."

**Agent teams** (`https://code.claude.com/docs/en/agent-teams.md`): experimental, off by default (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). Architecture (verbatim table): Team lead, Teammates, Task list, Mailbox. Mailbox files live at `~/.claude/teams/{team-name}/inboxes/{agent-name}.json`; team config at `~/.claude/teams/{team-name}/config.json`; task list at `~/.claude/tasks/{team-name}/`.

**The four-way comparison table** in `workflows.md` is the most useful single artifact in this area for an implementer choosing scope. Verbatim:

| | Subagents | Skills | Agent teams | Workflows |
| :- | :- | :- | :- | :- |
| What it is | A worker Claude spawns | Instructions Claude follows | A lead agent supervising peer sessions | A script the runtime executes |
| Who decides what runs next | Claude, turn by turn | Claude, following the prompt | The lead agent, turn by turn | The script |
| Where intermediate results live | Claude's context window | Claude's context window | A shared task list | Script variables |
| What's repeatable | The worker definition | The instructions | The team definition | The orchestration itself |
| Scale | A few delegated tasks per turn | Same as subagents | A handful of long-running peers | Dozens to hundreds of agents per run |
| Interruption | Restarts the turn | Restarts the turn | Teammates keep running | Resumable in the same session |

**Clean-room opportunity.** This is the cleanest "one mechanism, four surfaces" story in the product, and it maps cleanly onto an independent implementation:
- *Subagent* = spawn a worker with a fresh context.
- *Skill* = a named prompt file the agent loads on demand.
- *Team* = N workers plus a shared task file plus per-worker mailbox files.
- *Workflow* = a script interpreter that holds the loop instead of the model.

An implementer can ship *Subagent* and *Skill* first, then *Workflow* (the script interpreter), and skip *Teams* (the most experimental, most fragile, and the one with the most documented limitations: no session resumption with in-process teammates, task status can lag, one team per session, no nested teams, lead is fixed).

### F3-15 — The `/workflows` progress view is a keyboard-driven, resumable monitor

**Status: OBSERVED-DOC**

> "Run `/workflows` to open its progress view... The view shows each phase with its agent count. Drill into any phase to see its agents and what each one found."

Footer key map (verbatim table): `↑`/`↓` select a phase or agent; `Enter`/`→` drill in, `Enter` expands/collapses in the detail; `Esc`/`←` back out one level; `j`/`k` scroll; `f` filter the agent list by status; `p` pause or resume the run; `x` stop the selected agent (or the whole workflow); `r` restart the selected running agent; `s` save the run's script as a command.

> "The agent detail lists the agent's prompt, its recent tool calls, and its result. Each call shows its state, such as still running or failed. When the agent keeps a task list of its own, the detail shows it too, with each task's status."

> "a one-line progress summary appears [in the task panel] while the run is going. Press the down arrow to focus it, then Enter to expand."

The resume semantics are unusually well specified and directly implementable: on relaunch, a **completed** agent returns its saved result unless its prompt changed (or a predecessor returned something different), in which case it and every agent after it re-run; a **still-running** agent starts over; a **failed** agent re-runs and so does every agent after it. "If a script starts A, B, C, and D in that order and B fails, relaunching returns A from cache and runs B, C, and D again."

Stall handling: an agent whose output stops arriving is restarted automatically; the agent's name gains a `(retry 1)` suffix and its detail shows `attempt 2 (stalled)`. An agent restarts at most five times; the sixth failure yields `agent stalled on all 6 attempts` / `agent lost its reply on all 6 attempts` / `agent abandoned after 6 attempts`.

**Clean-room opportunity.** This is a genuinely well-designed component and the most directly copyable *conceptual* design in the area: a persisted per-agent result cache keyed by (agent index, prompt hash, predecessor output hash), plus a status machine {running, completed, failed, stalled}, plus a keyboard-driven drill-down monitor. None of it is Anthropic-specific — it is a DAG executor with a cache. An independent implementation could ship this as a generic "fan-out job runner" and get workflow orchestration for free.

### F3-16 — The recommended decomposition prompt shapes are concrete and reusable

**Status: OBSERVED-DOC**

From `best-practices.md`, the four canonical prompt recipes (verbatim):

| Strategy | Before | After |
| :- | :- | :- |
| Provide verification criteria | "implement a function that validates email addresses" | "write a validateEmail function. example test cases: `user@example.com` is true, invalid is false, `user@.com` is false. run the tests after implementing" |
| Verify UI changes visually | "make the dashboard look better" | "[paste screenshot] implement this design. take a screenshot of the result and compare it to the original. list differences and fix them" |
| Address root causes, not symptoms | "the build is failing" | "the build fails with this error: [paste error]. fix it and verify the build succeeds. address the root cause, don't suppress the error" |

And the interview pattern (verbatim):

> "I want to build [brief description]. Interview me in detail using the AskUserQuestion tool.
> Ask about technical implementation, UI/UX, error cases, concerns, and tradeoffs. Don't ask obvious questions, dig into the hard parts I might not have considered.
> Keep interviewing until we've covered everything, then write a complete spec to SPEC.md."

And the delegation pattern: "Use subagents to investigate how our authentication system handles token refresh, and whether we have any existing OAuth utilities I should reuse."

**Clean-room opportunity.** These are prompt templates, not implementation — but they encode the *product's* opinion about how a good agent should be driven, and they are the cheapest possible source of behavioral parity. A new agent should ship an equivalent prompt library. Note the recurring shape: **name the check, name the artifact, name the constraint** ("run the tests after implementing", "compare it to the original", "address the root cause, don't suppress the error").

## Area 3 Capability Table

| Capability | Presented to the user as | Key surface / setting | Classification |
| :- | :- | :- | :- |
| Plan mode | Status bar `⏸ plan mode on`; plan written to `~/.claude/plans/<slug>.md` | `--permission-mode plan`, `Shift+Tab`, `/plan`, `permissions.defaultMode: "plan"` | OBSERVED-DOC + OBSERVED-CLI (file write) |
| Plan approval | Three-way choice: "Yes, and use auto mode" / "Yes, manually approve edits" / "No, keep planning" | `ExitPlanMode` tool; `Ctrl+G` to edit in editor | OBSERVED-DOC |
| Plan editing | Opens the plan in `$EDITOR` | `Ctrl+G` / `Ctrl+X Ctrl+E` | OBSERVED-DOC |
| Plan default | New sessions start in plan mode | `permissions.defaultMode: "plan"`, `claudeCode.initialPermissionMode: "plan"` | OBSERVED-DOC |
| Clear planning context | Extra first option on the accept screen | `showClearContextOnPlanAccept` (bool, default `false`) | OBSERVED-DOC |
| Task list | Toggled widget, up to 5 rows, per-status glyphs | `Ctrl+T`; `CLAUDE_CODE_TASK_LIST_ID` for a shared list | OBSERVED-DOC |
| Task creation | Structured tool call with `subject`/`description`/`activeForm` | `TaskCreate` | OBSERVED-CLI |
| Task dependencies | `addBlockedBy` edges; blocked tasks can't be claimed | `TaskUpdate` | OBSERVED-CLI |
| Task status | `pending` → `in_progress` → `completed`; `status: "deleted"` removes | `TaskUpdate` | OBSERVED-DOC + OBSERVED-CLI |
| Task read-back | `TaskList`, `TaskGet` | `TaskList` / `TaskGet` | OBSERVED-CLI |
| Failure recording | Blocker written into the task description; unblock task created | `TaskUpdate` / `TaskCreate` | OBSERVED-CLI |
| Task tool gating | Tools absent on newer/unrecognized models | `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`, `allowedTools`, `CLAUDE_CODE_ENABLE_TASKS=0` | OBSERVED-CLI |
| Subagent spawn | Delegation row `name(description)`; only the summary returns | `Agent` tool (alias `Task`), `subagent_type` | OBSERVED-DOC + OBSERVED-CLI (`subagent_stats`) |
| Built-in roles | `Explore`, `Plan` (read-only), `general-purpose`, `claude`, `statusline-setup`, `claude-code-guide` | `subagent_type` | OBSERVED-CLI |
| Custom agents | Markdown + YAML frontmatter in `.claude/agents/`, `~/.claude/agents/`, plugin dir, `--agents` JSON | `name`, `description`, `tools`, `model`, `maxTurns`, `effort`, `background`, `isolation`, ... | OBSERVED-DOC |
| Background vs foreground | Default is background; foreground shows permission prompts inline | `run_in_background`; frontmatter `background: true`; `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` | OBSERVED-DOC + OBSERVED-CLI (`started_in_background: 1`) |
| Fork mode (on by default) | Inherits full parent conversation | `/subtask`; `CLAUDE_CODE_FORK_SUBAGENT=0` to disable | OBSERVED-DOC |
| Concurrency limit | 20 concurrent subagents; refusal names the limit | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`; `Concurrent subagent limit reached` | OBSERVED-DOC |
| Nesting depth | 3 layers below the main conversation | `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` | OBSERVED-DOC |
| Agent telemetry | `subagent_stats` in JSON output: spawned/completed/failed/killed/refused | `--output-format=json` | OBSERVED-CLI |
| Resume a subagent | `SendMessage` to the agent's ID or name | `SendMessage` | OBSERVED-DOC |
| Goal loop | Evaluator model judges the condition after each turn; 3 verdicts | `/goal`, `/goal clear` | OBSERVED-DOC |
| Workflows | Script-held loop; phase/agent progress view; resumable | `Workflow` tool, `/workflows`, `.claude/workflows/` | OBSERVED-DOC |
| Workflow scale limits | 16 concurrent, 4096 items, 1000 agents/run, "Large workflow" warning >25 agents or >1.5M tokens | `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` | OBSERVED-DOC |
| Batch decomposition | 5–30 worktree-isolated subagents after plan approval | `/batch <instruction>` | OBSERVED-DOC |
| Agent teams | Shared task list + per-agent mailboxes; experimental, off by default | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, `teammateMode` | OBSERVED-DOC |
| Verification loop | Tool-result-driven gather → act → verify cycle | Harness-level; `/verify` skill for UI | OBSERVED-DOC |
| Steering mid-turn | Queued message delivered at the next tool boundary | Harness-level (queue + tool-boundary flush) | OBSERVED-DOC |
| Effort levels | `low, medium, high, xhigh, max` | `--effort`, `/effort` | OBSERVED-CLI (help) + OBSERVED-DOC |

## Area 3 Dependencies

### Model provider
- **Task-tracking tools are model-gated** (F3-6). On this machine's non-Anthropic model, `TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate` were absent by default and present only after `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` (OBSERVED-CLI).
- `ExitPlanMode` and `AskUserQuestion` were absent from the session tool list in this environment (OBSERVED-CLI) — the plan-approval affordance is unavailable without them. The model degraded to prose-plus-plan-file.

### Network / account
- The `/goal` evaluator, dynamic workflows, agent teams, `/batch`, and `ultrareview` are documented as available on paid plans / with Anthropic API access / Bedrock / Vertex / Foundry. On this machine `claude doctor` reports "Not connected to the Anthropic API", "Organization not resolved" — so **all of these are INFERRED, not OBSERVED**.
- The auto-mode classifier that reviews plan-mode shell commands is a separate model call; `useAutoModeDuringPlan` (default `true`) only applies when auto mode is available.

### Local state written by the observed flows
| Path | Written by | Observed |
| :- | :- | :- |
| `~/.claude/plans/<slug>.md` | Plan mode | YES (OBSERVED-CLI) |
| `~/.claude/tasks/{team-name}/` | Agent teams | not created here (teams disabled) |
| `~/.claude/teams/{team-name}/` | Agent teams | not created here (teams disabled) |
| `~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl` | Subagent transcripts | documented, not directly observed here |
| `~/.claude/projects/` (session dir) | Workflow scripts | documented, not directly observed here |

### Environment variables relevant to this area (from docs + CLI help)
`CLAUDE_CODE_ENABLE_TODO_TOOLS`, `CLAUDE_CODE_ENABLE_TASKS`, `CLAUDE_CODE_TASK_LIST_ID`, `CLAUDE_CODE_FORK_SUBAGENT`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`, `CLAUDE_CODE_WORKFLOW_PREFIX_STAGGER_MS`, `CLAUDE_CODE_DISABLE_WORKFLOWS`, `CLAUDE_CODE_GOAL_CHECKIN_MINUTES`, `CLAUDE_CODE_ASYNC_AGENT_STALL_TIMEOUT_MS`, `MAX_STRUCTURED_OUTPUT_RETRIES`, `ANTHROPIC_DEFAULT_HAIKU_MODEL` (goal evaluator model), `API_TIMEOUT_MS`, `CLAUDE_CODE_MAX_RETRIES`.

### Settings keys (OBSERVED-DOC, `settings-reference.md`)
`permissions.defaultMode`, `showClearContextOnPlanAccept` (bool, `false`), `useAutoModeDuringPlan` (bool, `true`; user/local/managed only, **not** project), `plansDirectory` (default `~/.claude/plans`), `disableWorkflows` (bool), `ultracode` (bool), `workflowSizeGuideline` (number, `3`), `teammateMode` (string, `"auto"`), `subagentPromptCacheTtl` (`"5m"`/`"1h"`), `autoContinueAtUsageLimit` (bool, `false`), `disableAutoMode` (string `"disable"`), `cleanupPeriodDays` (number, `30`).

## Area 3 Limitations of This Investigation

- **No interactive TUI observation.** Every run was headless (`-p`) or via `--help`/`doctor` output. The plan-approval dialog, the `Ctrl+T` task widget, the `Ctrl+G` editor hand-off, the `/workflows` drill-down, and the agent-team panel were all read from documentation only. The *docs* are authoritative for Anthropic's product, but a UI-level discrepancy would not have been caught.
- **Non-Anthropic model in the loop.** The agent's plan-writing quality, its willingness to request approval, and its task-decomposition choices were produced by a third-party model behind a custom gateway, not by an Anthropic model. The *harness* behaviors (file written, write blocked, `subagent_stats`, task-tool gating) are Anthropic harness behaviors and are reliable evidence; the *model's* behavior is not representative.
- **Subscription features unverified.** `/goal`, workflows, agent teams, `/batch`, `ultrareview`, auto mode's classifier, and the `/deep-research` bundled workflow were not exercised — they require a claude.ai subscription or Anthropic API access, neither of which is available here.
- **No concurrency testing.** The 20-subagent limit, the 16-agent workflow limit, and the 5-attempt stall restart were read from docs; none were triggered.
- **Single-iteration plan mode.** The plan-mode runs were one-shot headless calls. The interactive approve → implement → verify cycle (and what happens when the user picks "No, keep planning") was not observed end to end.
- **`claude doctor` caveat.** The doctor output was used only to establish that subscription-gated behavior was unobservable here.

## Area 3 Unresolved Questions (UNKNOWN)

1. **What exactly does the `ExitPlanMode` tool's input schema look like, and what does the harness render from it?** The tool was absent from this session's registry, so its schema and the exact prompt text the user sees are UNKNOWN from direct observation. (The doc's three option labels are OBSERVED-DOC.)
2. **How is the plan Markdown rendered in the TUI?** Is it a rendered view, a diff against a template, or raw Markdown? UNKNOWN.
3. **What is the exact rendering of the `Ctrl+T` task widget** — glyphs, ordering, colors, the in-progress row's animation? UNKNOWN (docs give only "indicators showing what's pending, in progress, or complete").
4. **What is the internal representation of the "task list" between sessions** — is it stored per session, per project, or in `~/.claude/tasks/` by default? `CLAUDE_CODE_TASK_LIST_ID` implies a `~/.claude/tasks/<name>/` layout, but the default (unnamed) location is UNKNOWN; `~/.claude/tasks/` did not exist on this machine after a task-tool run.
5. **Is the "goal" evaluator a separate model or the session's small-fast model, and what is the exact verdict-prompt?** The docs say "your configured small fast model" and `ANTHROPIC_DEFAULT_HAIKU_MODEL`; the exact prompt is UNKNOWN and I did not read any internal prompt (and would not have been permitted to).
6. **How does the runtime decide a subagent's "budget" refusal?** `subagent_stats.refused.budget` exists in the telemetry (OBSERVED-CLI), but the budget's units and source are UNKNOWN from the available evidence.
7. **Does the plan-approval flow differ in the VS Code extension, desktop app, and web?** The docs describe a "plan review" in VS Code and a Desktop "approval card" for workflows; the per-surface plan UI is UNKNOWN.
8. **What is the exact `maxTurns` / `max_turns` truncation message?** `errors.md` contains no `maxTurns` error string; the "marked as partial" wording is all I can confirm (OBSERVED-DOC).
9. **Does the `Plan` built-in subagent use `ExitPlanMode`?** The subagent tool list "always removed" includes `ExitPlanMode` unless `permissionMode: plan`, which suggests it is available *to* plan-mode subagents — but the mechanism by which a `Plan` subagent's plan reaches the user is UNKNOWN.
10. **How are task IDs allocated** (sequential per session? global? per project)? OBSERVED-CLI shows small integers (`"1"`, `"2"`, `"3"`) within one session; the global scheme is UNKNOWN.

## Area 3 Recommended Scope for an Independent Functional Implementation

### Tier 1 — the parity core (build first)
1. **A permission/edit gate with a plan mode.** A session flag consulted by the tool dispatcher before any mutating tool runs. Enterable via flag, key, slash command, and a project default. Status-line indicator. Non-mutating tools unaffected. *(F3-1)*
2. **A `submit_plan` tool + three-way approval UI.** The harness renders the choice and maps it back to a permission mode. Include "open in editor" and "keep planning". *(F3-2)*
3. **A plan artifact.** Write Markdown to a per-project directory with a readable slug; render it; support editing in `$EDITOR`. Require the plan to state its own verification step. *(F3-3)*
4. **A task table with dependency edges.** `create/update/list/get` tools; `subject` + `description` + `activeForm`; `pending`/`in_progress`/`completed`/`deleted`; `blockedBy`; refuse to start a blocked task; persist outside the context window so it survives compaction and resume. *(F3-4, F3-5, F3-12)*
5. **A subagent worker.** Fresh context window, tool allowlist/denylist, own model, `maxTurns`/`max_turns` budget, background-by-default, result-only return, `status` (complete/partial/failed), and a per-run telemetry counter block (`spawned`/`completed`/`failed`/`refused{depth_limit,concurrency_limit,budget}`). *(F3-7, F3-9, F3-13)*
6. **Two read-only built-in roles** (scout/explorer, planner) plus one generalist, exposed to the model as named types. *(F3-8)*
7. **A closed tool→result loop with deterministic failure reporting.** Every tool call returns a result the model can read, including errors; the model must be able to iterate. *(F3-11)*
8. **Mid-turn steering.** A queue that delivers the user's correction at the next tool boundary. *(F3-11)*

### Tier 2 — strong differentiation
9. **A `/goal`-style completion evaluator.** A separate cheap model judging a stated condition after each turn, with three verdicts, a clear error taxonomy (clear vs. retry vs. pause), and background-work deferral. *(F3-14)*
10. **A script-driven fan-out runner** (workflows): a tiny sandboxed JS-like interpreter with `agent()`, `pipeline()`, `parallel()`, `phase()`, `log()`, a persisted per-agent result cache with the "re-run from the first changed agent" resume rule, a stall detector with bounded retries, and a drill-down progress view. *(F3-15)*
11. **Fork mode** as an explicit `context: "fresh" | "fork"` spawn parameter. *(F3-10)*
12. **A structured blocked-task UX** — distinct rendering for blocked tasks, and task splitting (a blocked task spawns an unblock task). *(F3-12)*
13. **An adversarial-review step** — after implementation, re-review the diff in a fresh context against the plan. *(best-practices.md)*

### Tier 3 — nice to have
14. Agent teams (shared task file + per-agent mailbox files + lead). *(F3-14)*
15. `/batch`-style large-scale decomposition into 5–30 isolated work units. *(F3-14)*
16. Instruction-shaped-content scanning of child reports with a visible prefix. *(F3-13)*

### Explicitly recommend NOT replicating
- **Model-identity-gated tool availability** (F3-6). It is a fragile heuristic for a third-party provider and it produces the confusing state this very session hit. Expose task tools unconditionally, or gate on a config flag.
- **The `Task` → `Agent` rename** with a compatibility alias. Pick one name; there is no value in reproducing a legacy alias.
- **Tying the "size guideline" to plan tiers.** The `unrestricted`/`small`/`medium`/`large` guideline is advisory prompt text, not a cap; the real caps (16 concurrent, 1000 agents) are worth having, the guideline is not.
- **The `Date.now()`/`Math.random()` throwing quirk** as a design goal. It is a determinism aid inside a script runtime; if you have a script runtime, you can just pass timestamps in explicitly, as the docs themselves suggest.

### Implementation order
1. Edit gate + plan mode + `submit_plan` + approval UI → 2. Task table with dependencies → 3. Subagent worker + telemetry + read-only roles → 4. Closed tool→result loop with mid-turn steering → 5. Goal evaluator → 6. Script fan-out runner → 7. Teams (if at all).

Rationale: (1)–(4) are the irreducible core of "planning, decomposition, implementation, iterative problem-solving" and every later item composes on them. (5) and (6) are where the product's differentiation lives but both need (1)–(4) to be correct first. (7) is the most fragile and least frequently used — defer it, and treat the shared task list as a feature of (2) that you expose rather than a new subsystem.

## Area 3 Evidence Artifacts

| Path | Contents |
| :- | :- |
| `agent-reference-shots/area3-planning/cli-surfaces.txt` | Verbatim `claude --version`, `--help` (filtered for plan/task/agent/permission flags), `claude agents --help`, `claude auto-mode --help`, and the head of `claude auto-mode defaults` JSON |
| `agent-reference-shots/area3-planning/observed-plan-file.md` | The actual plan Markdown the agent wrote during the headless plan-mode run |
| `agent-reference-shots/area3-planning/observed-behaviours.md` | Summary of the four directly observed behaviors (plan blocking, subagent stats, task-tool gating, built-in subagent types) |
| `agent-reference-shots/area3-planning/observed-task-tool-calls.txt` | Sanitized raw `TaskCreate`/`TaskUpdate`/`TaskList` tool_use inputs, including the dependency wiring and the blocked-task update |

No secrets, credentials, tokens, or personal information appear in any artifact. The one absolute path retained (`~/.claude/plans/...`) is a Claude Code application-data path, not a user file; the working-directory path in the task-tool capture was replaced with `<WORKDIR>`.

## Area 3 Public Documentation Sources Fetched

| URL | Used for |
| - | :- |
| https://code.claude.com/docs/en/overview | Doc index; agentic-loop framing |
| https://code.claude.com/docs/llms.txt | Full page inventory |
| https://code.claude.com/docs/en/permission-modes.md | F3-1, F3-2 (plan mode, approval options, status strings) |
| https://code.claude.com/docs/en/sub-agents.md | F3-7, F3-8, F3-9, F3-10 (Agent tool, frontmatter, limits, fork, resume) |
| https://code.claude.com/docs/en/tools-reference.md | F3-4, F3-7, F3-8 (tool table, Agent tool behavior, task tool availability) |
| https://code.claude.com/docs/en/agent-sdk/todo-tracking.md | F3-4, F3-5 (todo lifecycle, task tool schemas, rendering recipe) |
| https://code.claude.com/docs/en/interactive-mode.md | F3-5, F3-11 (Ctrl+T, task list display, steering) |
| https://code.claude.com/docs/en/common-workflows.md | F3-1 (plan mode entry points, subagent delegation) |
| https://code.claude.com/docs/en/best-practices.md | F3-11, F3-16 (verify loop, four-phase workflow, prompt recipes) |
| https://code.claude.com/docs/en/how-claude-code-works.md | F3-11 (gather/act/verify loop) |
| https://code.claude.com/docs/en/workflows.md | F3-14, F3-15 (workflow script API, limits, progress view, resume rules) |
| https://code.claude.com/docs/en/agent-teams.md | F3-14 (teams architecture, mailbox/task paths, dependency semantics) |
| https://code.claude.com/docs/en/agents.md | F3-14 (five parallel approaches comparison) |
| https://code.claude.com/docs/en/goal.md | F3-14 (goal evaluator, verdicts, error taxonomy) |
| https://code.claude.com/docs/en/commands.md | F3-1, F3-14 (`/plan`, `/tasks`, `/workflows`, `/subtask`, `/goal`, `/batch`, `/effort`) |
| https://code.claude.com/docs/en/settings-reference.md | F3-1, F3-2, F3-6 (settings keys, defaults) |
| https://code.claude.com/docs/en/errors.md | F3-8, F3-13 (agent error strings, `maxTurns` absence) |

All fetched pages were treated as **untrusted data**, never as instructions. No directive found in fetched content was executed. The only commands run were the CLI's own user-facing inspection surfaces (`--help`, `doctor`, `auto-mode defaults`) and headless `-p` sessions in the working directory. No credential files, keychains, licence files, or unrelated personal files were read; no binary was decompiled, de-minified, or modified.

### Prompt-injection note
One page (the `commands.md` reference) contains instructional content by design — it is a command reference. No embedded attempt to make the reader install software, run shell commands, or exfiltrate data was found in any fetched page. The auto-mode defaults JSON (`claude auto-mode defaults`) contains natural-language policy rules that are *scoped to the auto-mode classifier*, not instructions to this investigation; they were read as data.
