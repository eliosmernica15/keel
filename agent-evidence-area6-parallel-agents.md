# Area 6 — Running Agents in Parallel: Spawning, Coordination, and Merging

> **Naming note.** This section covers *parallel agents* (the workflow's "Area 6"). It is **not** the same as the "Area #6 — Tests, Build Errors, Runtime Errors, and Failed Tool Calls" section at the top of this file, which uses the user's own area numbering. Where this section says "Area 6", it means *parallel agents*.

**Investigation date:** 2026-10-21
**Subject:** Claude Code 2.1.306 (native Windows build, `win32-x64`)
**Primary page under study:** `https://code.claude.com/docs/en/agents.md` ("Run agents in parallel")
**Supporting public pages:** `/docs/en/sub-agents`, `/docs/en/agent-view`, `/docs/en/agent-teams`, `/docs/en/workflows`, `/docs/en/worktrees`, `/docs/en/cross-session-messaging`, `/docs/en/tools-reference`, `/docs/en/commands`, `/docs/en/agent-sdk/typescript`
**Compliance boundary:** see section 0 of this file. No decompilation, no source extraction, no binary modification, no credential/account access. All evidence is public documentation plus black-box observation of the published CLI's own help and listing surfaces.

---

## 6.0 Executive summary (one page)

**The page under study is a router, not a specification.** `agents.md` is 68 lines of Markdown: an intro sentence, a five-row comparison table, three "supporting tools" bullets, a "not a way to run agents" disambiguation list, a three-question decision guide, a "check on running work" command list, and a "learn more" link list. It contains **no flags, no JSON field names, no file paths, and no API contracts** beyond the command names `claude agents`, `/agents`, `/tasks`, `/workflows`, `/subtask`, `/fork`, `/batch` and the environment variable `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` (the latter appears only on the linked `/docs/en/agent-teams` page, not on `agents.md` itself). **Anyone reimplementing this feature from `agents.md` alone would build the wrong thing.** The actual contract lives in the six linked pages, which were fetched and mined as part of this area.

**What the product actually is.** Claude Code implements parallelism as **five distinct mechanisms with different coordination models**, differing on *who holds the plan* and *whether workers can talk to each other*:

| Mechanism | Who coordinates | Worker-to-worker messaging | Where it runs |
| :- | :- | :- | :- |
| **Subagents** | The parent agent delegates and collects | No — results return to the spawning conversation | In-process, inside one session |
| **Agent view** (`claude agents`) | The human dispatches and checks back | No — results report to the human only | Local machine, under a supervisor daemon |
| **Agent teams** | A lead agent plans, assigns, supervises | Yes — direct mailbox messages + shared task list | In-process teammates, or tmux/iTerm2 split panes |
| **Dynamic workflows** | A JavaScript script holds the plan | No — agents report to the script | Isolated runtime, session-scoped |
| **Projects** | Claude coordinates cloud threads | Not documented here | Cloud / Remote Control |

The three *supporting* primitives are **git worktrees** (per-worker file isolation), **cross-session messaging** (worker-to-worker findings passing between independent sessions), and **`/batch`** (a packaged skill that fans one change into 5–30 worktree-isolated subagents).

**The observable contract a reimplementation must honour**, gathered below, is essentially:
1. **One spawn primitive with three modes.** A single `Agent` tool call spawns a subagent, a teammate (if `name` is present and teams are enabled), or a fork. Its input schema is `description`, `prompt`, `subagent_type`, `model`, `effort`, `run_in_background`, `name`, `isolation` (`"worktree" | "remote"`), plus deprecated `mode`/`team_name` that are ignored.
2. **Results merge in exactly one place: the parent conversation.** The parent never sees the child's intermediate tool calls or outputs — only its final result. Forks differ only in that they inherit the parent's context.
3. **Isolation is a filesystem concern, not a process concern.** Parallel workers that edit files are separated by **git worktrees**, with a four-check enforcement layer (file-edit path, command cwd, git redirects, command shape) that cannot be turned off.
4. **Coordination between workers is a first-class, file-backed protocol.** Agent teams use a shared task list (`~/.claude/tasks/{team-name}/{n}.json`, with `id`/`subject`/`description`/`status`/`blocks`/`blockedBy` and a `.lock` file) plus per-agent mailboxes (`~/.claude/teams/{team-name}/inboxes/{agent-name}.json`).
5. **Every parallel surface has a "watch it" view.** `/tasks` (session-local background work), `/workflows` (workflow runs), `claude agents` (a TUI list of all sessions), and `claude agents --json` (the same data, machine-readable, documented as *the* supported scripting interface).
6. **Concurrency is capped and the caps are documented, named, and overridable.** 20 concurrent subagents (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`), depth 3 (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`), 16 concurrent workflow agents (`CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`, 1–256), 4,096 items per `parallel()`/`pipeline()`, 1,000 agents per run, 15,000 tokens of combined subagent descriptions.

**Most important single insight for a clean-room build:** the reference product's parallel machinery is *not* a scheduler abstraction. It is a **file-based, restart-tolerant, human-inspectable state machine**. Sessions live in `~/.claude/jobs/<id>/` with `state.json` + `timeline.jsonl` + `tmp/`; the supervisor's roster is `~/.claude/daemon/roster.json`; a background session's short id *is* its directory name. Everything is plain JSON on disk that a human can read, a script can poll, and a crash can be recovered from. That is the design pattern to copy — not the code.

**What was directly observed on this host** (Windows 11, Claude Code 2.1.306, running against a custom `ANTHROPIC_BASE_URL`):
- `claude agents --json` returns a JSON array; observed field set across 9 live sessions: `cwd`, `id`, `kind`, `name`, `pid`, `sessionId`, `startedAt`, `state`, `status`. Interactive entries carry `kind: "interactive"` + `status` (`busy`/`idle`/`waiting`); background entries carry `id` + `state` (`working`/`blocked`/`done`/`failed`/`stopped`).
- `~/.claude/jobs/<id>/` contains `state.json`, `timeline.jsonl`, `tmp/` — matching the documented layout exactly.
- `~/.claude/daemon/roster.json` exists with `{"proto": 1, "supervisorPid": …, "updatedAt": …, "workers": {}}`.
- `~/.claude/tasks/<session-uuid>/` contains `.lock` plus `<n>.json` task items with `id`/`subject`/`description`/`activeForm`/`status`/`blocks`/`blockedBy` — matching the documented task-list contract, including the `.lock` that the docs say is used for claiming.
- `claude daemon status` prints a fixed, greppable status block (socket dir `\\.\pipe\cc-daemon-*`, roster freshness, daemon.log path).

**Recommendation in one line:** build a **file-backed job registry with a documented JSON listing contract, a single spawn tool with a mode flag, worktree-based edit isolation, and a task-list + mailbox pair for worker-to-worker coordination** — the observable surface is small and well-specified; the hard parts are the enforcement layers (worktree isolation checks, permission prompt routing into the parent session, crash/restart semantics), not the API shape.

---

## 6.1 Findings — 17 concrete claims

Each claim is classified **OBSERVED-DOC** (stated in the cited public Anthropic documentation, quoted verbatim), **OBSERVED-CLI** (directly observed on this host by running the published CLI's own surfaces), **INFERRED** (my conclusion from evidence, reasoning given), or **UNKNOWN** (the evidence cannot establish it).

---

### P1 — `agents.md` enumerates exactly five parallel mechanisms and nothing else

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/agents.md`, intro paragraph and comparison table
**Section:** "Run agents in parallel" (intro)

> "Claude Code has five ways to work on several tasks at once: [subagents](/docs/en/sub-agents), [agent view](/docs/en/agent-view), [agent teams](/docs/en/agent-teams), [dynamic workflows](/docs/en/workflows), and [projects](/docs/en/claude-projects). They differ in how involved you stay, from steering each conversation yourself to letting Claude coordinate a group of workers, and in whether the work runs on your machine or in the cloud."

**Table (verbatim rows, condensed to the two load-bearing columns):**

> | [Subagents](/docs/en/sub-agents) | Delegated workers inside one session that do a side task in their own context and return a summary | A side task would flood your main conversation with search results, logs, or file contents you won't reference again |
> | [Agent view](/docs/en/agent-view) | One screen to dispatch and monitor sessions running in the background, opened with `claude agents`. Research preview | You have several independent tasks and want to hand them off, check status at a glance, and step in only when one needs you |
> | [Agent teams](/docs/en/agent-teams) | Multiple coordinated sessions with a shared task list and inter-agent messaging, managed by a lead. Experimental and disabled by default | You want Claude to split a project into pieces, assign them, and keep the workers in sync |
> | [Projects](/docs/en/claude-projects) | One ongoing conversation at claude.ai/code or in the desktop app. Claude starts parallel sessions called threads, in the cloud or, when you ask, on your computer through Remote Control, gives each one the project's instructions, and shows you which ones need you. Public beta on Pro and Max | The work spans many tasks over days or weeks, should keep running when your machine is off, and you'd rather describe it once than dispatch and track each session |
> | [Dynamic workflows](/docs/en/workflows) | A script that runs many subagents and cross-checks their results, for work too big to coordinate one turn at a time or that needs more than a single pass | A job outgrows a handful of subagents, or you want findings verified against each other: a codebase-wide audit, a 500-file migration, cross-checked research, or a plan drafted from several angles |

**Needs for a reimplementation:** yes — this is the top-level taxonomy the UI, docs, and configuration must all agree on. Getting the *boundaries* right matters more than any individual mechanism: a user asking "run these in parallel" must be routed to the right one based on whether they want to supervise, whether workers must talk, and whether files collide.

---

### P2 — `agents.md` itself carries three supporting tools and three explicit non-mechanisms

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/agents.md`
**Section:** intro, after the table ("Three more tools support this work without being a way to run agents themselves:" and "A few other features run Claude without you driving each step, but they solve a different problem than splitting work across agents:")

> "* [Worktrees](/docs/en/worktrees) give each session a separate git checkout, so parallel sessions each edit their own copy of the files. Use them for sessions you run yourself. A session you dispatch from agent view [moves into a worktree of its own before it edits files](/docs/en/agent-view#how-file-edits-are-isolated), and subagents you spawn can each get one too."

> "* [Cross-session messaging](/docs/en/cross-session-messaging) lets Claude list and message your other Claude Code sessions on this machine, on another machine, or [in the cloud](/docs/en/claude-code-on-the-web), so sessions you run yourself can pass findings and status between themselves."

> "* [`/batch`](/docs/en/commands) is a [skill](/docs/en/skills) that has Claude split one large change into 5 to 30 worktree-isolated subagents. It's a packaged use of subagents and worktrees, not a separate coordination style."

The three explicit non-mechanisms:

> "* A [background bash command](/docs/en/interactive-mode#background-bash-commands) runs one shell command without blocking the conversation. It doesn't spawn an agent."

> "* A [forked subagent](/docs/en/sub-agents#fork-the-current-conversation) is a subagent that inherits your full conversation context instead of starting fresh. It's a way to spawn a subagent, not a separate surface. Start one with `/subtask`. Claude also spawns one itself where [fork mode](/docs/en/sub-agents#turn-fork-mode-on-or-off) is on. To copy the whole session into a new [background session](/docs/en/agent-view#from-inside-a-session) that runs alongside it, use `/fork`. With [agent view turned off](/docs/en/agent-view#turn-off-agent-view), the forked-subagent command is `/fork` instead and `/subtask` isn't available."

> "* A [cloud scheduled task](/docs/en/routines) runs a session on a schedule in the cloud, not in parallel on your machine."

**Needs for a reimplementation:** yes — the disambiguations are the *user-facing* contract. A reimplementation that lacks a background-bash concept will have users try to use a subagent for it; one that lacks a fork concept will have users re-explain context.

---

### P3 — The decision guide is three orthogonal questions, and the third one's answer is "use worktrees, except for teams"

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/agents.md`
**Section:** "Choose an approach"

> "* **Who coordinates the work?**
>   * Claude delegates and collects results inside one conversation: [subagents](/docs/en/sub-agents)
>   * You hand off independent tasks and check back later: [agent view](/docs/en/agent-view)
>   * Claude plans, assigns, and supervises a group of workers: [agent teams](/docs/en/agent-teams), experimental and disabled by default
>   * A script holds the plan instead of Claude's turn-by-turn judgment: [dynamic workflows](/docs/en/workflows). See [how workflows compare to subagents and skills](/docs/en/workflows#when-to-use-a-workflow)"

> "* **Do the workers need to talk to each other?** Claude can pass findings with [cross-session messaging](/docs/en/cross-session-messaging) between sessions you run yourself, including the sessions you dispatch from agent view. Subagents report results back to the conversation that spawned them, and agent view sessions report results only to you. Teammates in an agent team message each other directly and, when they [have the Task tools](/docs/en/tools-reference#task-tool-availability), share a task list."

> "* **Do the tasks touch the same files?** Isolate the work with [worktrees](/docs/en/worktrees). Subagents and sessions you run yourself can each use a separate worktree. **Agent teams don't isolate teammates in worktrees, so [partition the work](/docs/en/agent-teams#avoid-file-conflicts) so each teammate owns a different set of files.**"

**Needs for a reimplementation:** yes. The third bullet contains the single most consequential asymmetry: **agent teams deliberately do not get worktree isolation**, so teams require the *user or the lead* to partition files. A reimplementation that isolates teams by default is not a superset — it changes the coordination contract (teammates would stop being able to see each other's edits, which is often the point of a team).

---

### P4 — Every parallel mechanism has a distinct "check on running work" command, and `/agents` ≠ `claude agents`

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/agents.md`
**Section:** "Check on running work"

> "* For background sessions, `claude agents` opens [agent view](/docs/en/agent-view): one screen showing every session, its state, and which ones need your input."

> "* For subagents in the current session, named background subagents appear in the @-mention typeahead with their status. The `/agents` command prints a notice pointing to the subagent file locations. To [create and edit custom subagents](/docs/en/sub-agents#configure-subagents), ask Claude or edit the files directly. **Despite the similar name, `/agents` is separate from `claude agents`.**"

> "* For anything running in the background of the current session, `/tasks` lists each item and lets you check on, attach to, or stop it. The list also includes subagents that have finished."

> "* For dynamic workflows, `/workflows` lists running and completed runs, the phase each is in, and how many agents have finished."

Cross-checked against `/docs/en/commands`:
- `| /tasks | View and manage background work in the current session, including subagents that have finished. Also available as /bashes |`
- `| /workflows | Open the [workflow](/docs/en/workflows#watch-the-run) progress view to watch, pause, resume, or save running and completed workflows |`
- `| /subtask <task> | Spawn a [forked subagent](/docs/en/sub-agents#fork-the-current-conversation): a background subagent that inherits the full conversation and works on the task while you keep working. Its result returns to this conversation when it finishes. To copy the conversation into a separate background session instead, use /fork. When [agent view is turned off](/docs/en/agent-view#turn-off-agent-view), /subtask isn't available and /fork spawns the forked subagent instead |`
- `| /agents | Print a reminder to ask Claude to create or manage [subagents](/docs/en/sub-agents), or to edit .claude/agents/ or ~/.claude/agents/ directly. On v2.1.197 and earlier, opens an interactive interface for creating and managing subagent configurations |`
- `| /list-agents | List the subagents, [agent team](/docs/en/agent-teams) teammates, and other Claude Code sessions Claude can message, with the name to use for each. … Also available as /peers. … Available only in sessions where [cross-session messaging is enabled] |`

**Needs for a reimplementation:** yes, and note the naming trap explicitly: `claude agents` (a subcommand that opens a TUI) vs `/agents` (a slash command that prints a hint) vs `/list-agents` (a slash command that lists messageable peers). A reimplementation that collapses these will confuse users.

---

### P5 — One tool spawns all three worker kinds; the mode is selected by the call's own fields

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/tools-reference`, section "Agent tool behavior"; corroborated by `https://code.claude.com/docs/en/agent-sdk/typescript` (AgentInput type) and `https://code.claude.com/docs/en/agent-teams`, section "How Claude starts agent teams"

> "The Agent tool spawns a subagent in a separate context window. The subagent works through its task autonomously, then returns its result to the parent conversation. **The parent doesn't see the subagent's intermediate tool calls or outputs, only that final result.** The same tool can also launch a teammate or a fork"

> "* **Teammate**: with [agent teams](/docs/en/agent-teams) enabled, a call that carries a `name` can launch a [teammate](/docs/en/agent-teams#how-claude-starts-agent-teams) instead, which reports back through team messages rather than by returning a result
> * **Fork**: wherever [fork mode](/docs/en/sub-agents#turn-fork-mode-on-or-off) is on, the tool can launch a [forked subagent](/docs/en/sub-agents#fork-the-current-conversation), which inherits the full parent conversation instead of starting fresh"

> "To start a team, ask Claude for teammates. Claude launches a teammate when it calls the [Agent tool](/docs/en/tools-reference) with a [`name`](/docs/en/sub-agents#subagent-names) while agent teams are enabled, **unless the call is a [fork](/docs/en/sub-agents#fork-the-current-conversation) or passes `isolation` on the call itself.** Claude Code doesn't ask you to confirm the launch."

Exact input schema (from `/docs/en/agent-sdk/typescript`, `AgentInput`):

```typescript
type AgentInput = {
  description: string;
  prompt: string;
  subagent_type?: string;
  model?: "sonnet" | "opus" | "haiku" | "fable";
  effort?: "low" | "medium" | "high" | "xhigh" | "max";
  run_in_background?: boolean;
  name?: string;
  team_name?: string; // Deprecated; ignored
  mode?: "acceptEdits" | "auto" | "bypassPermissions" | "default" | "dontAsk" | "plan"; // Deprecated; ignored.
  isolation?: "worktree" | "remote";
};
```

**Needs for a reimplementation:** yes — this is the core spawn contract. The deprecation notes are load-bearing: `mode` and `team_name` are accepted and ignored, and permission mode is decided by inheritance rules, not the call. A reimplementation that honours `mode` would be implementing a *different* product.

---

### P6 — Spawning does not prompt for permission, but the child's tool calls do; foreground and background route prompts differently

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/tools-reference`, section "Agent tool behavior"

> "Launching the subagent doesn't itself prompt for permission. Claude Code checks the subagent's own tool calls against your permission rules as it runs."

> "Where you see a subagent's permission prompts depends on whether it runs in the foreground or the background. Claude Code runs subagents in the background by default, apart from the [cases that run in the foreground](...).

> * **Foreground subagents** show the same permission prompts you would see in the main conversation, at the moment each tool call happens.
> * **Background subagents** surface permission prompts in your main session. The prompt names which subagent is asking, and pressing Esc denies that one tool call without stopping the subagent."

And from `/docs/en/sub-agents`, section "Run subagents in foreground or background":

> "* **Background subagents** run concurrently while you continue working. When a background subagent reaches a tool call that needs permission, Claude Code surfaces the prompt in your main session and names the subagent that is asking. Approve to let the subagent continue, or press Esc to deny that one tool call without stopping the subagent."

> "When you answer one of those prompts with a choice that lasts beyond that one tool call, such as a grant that lasts for the rest of the session, Claude Code applies your answer to the whole session, including your main conversation."

**Needs for a reimplementation:** yes, and this is the hardest part to get right. The contract is: **permission prompts from any worker surface in the one place the human is looking**, name the worker, and make "deny one call" not kill the worker. Any implementation that gives each subagent its own prompt queue will deadlock unattended runs.

---

### P7 — Results merge in exactly one place; the parent sees only the final result

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/tools-reference`; `/docs/en/sub-agents` section "Tools, permissions, and results of background subagents"; `/docs/en/sub-agents` section "Fork the current conversation"

> "The parent doesn't see the subagent's intermediate tool calls or outputs, only that final result." (`/docs/en/tools-reference`)

> "A background subagent's results reach Claude as a completion notification in a later turn. Claude waits for that notification before reporting the subagent's results, and if you ask about progress first, it reports that the subagent is still running." (`/docs/en/sub-agents`)

> "The fork's own tool calls still stay out of your conversation and only its final result comes back, so your main context window stays clean." (`/docs/en/sub-agents`)

> "Each subagent starts with a fresh, isolated context window. It doesn't see your conversation history, the skills you've already invoked, or the files Claude has already read. Claude composes a delegation message that summarizes the task, and the subagent works from there. The exception is a [fork](...), which inherits the parent conversation instead of starting fresh." (`/docs/en/sub-agents`, "What loads at startup")

Fork vs non-fork table (`/docs/en/sub-agents`):

> | | Fork | Non-fork subagent |
> | **Context** | Full conversation history | Fresh context with the prompt you pass |
> | **System prompt and tools** | Same as main session | From the subagent's [definition file](...), [filtered for background runs] |
> | **Model** | Same as main session | From the subagent's `model` field |
> | **Prompt cache** | Shared with main session | Separate cache |

**Needs for a reimplementation:** yes. The merge rule is simple and load-bearing: **workers are context-isolated; the parent gets one summary**. A reimplementation that streams worker tool output into the parent will destroy the parent's context — which is the entire reason the feature exists (as `agents.md` says: "A side task would flood your main conversation with search results, logs, or file contents you won't reference again").

---

### P8 — Worktree isolation is enforced by four checks, and the fourth cannot be turned off

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/worktrees`, section "How Claude Code enforces isolation"

> "While a session is isolated in a worktree, Claude Code blocks the tool calls the checks below define. The same rules apply whether you started the session with `--worktree`, Claude entered a worktree with `EnterWorktree`, or you resumed a worktree session."

> "The same enforcement covers every subagent Claude spawns from the isolated session. It applies whether the session is interactive or runs in the [background](...). [Subagents that run in their own worktree](#isolate-subagents-with-worktrees) carry the same checks."

> "Claude Code applies four checks:
> * **File edits**: Claude Code blocks an `Edit`, `Write`, or `NotebookEdit` that targets a path in the main checkout.
> * **Command working directory**: Claude Code blocks a Bash, PowerShell, or Monitor command whose working directory resolves to the main checkout, or whose working directory it can't verify stays outside it.
> * **Git redirects**: Claude Code blocks a Bash or Monitor command that redirects git into the main checkout. The redirect can come through `git -C`, `--git-dir`, a `GIT_DIR` or `GIT_WORK_TREE` variable, or a `cd` into the main checkout before running git.
> * **Command shape**: Claude Code blocks a Bash or Monitor command when it can't verify from the command text that any git the command runs stays inside the worktree. That happens, for example, when the command name is computed at runtime, when the syntax can't be parsed, or when an expansion such as `${!name}` or `${ command; }` could run a command the text doesn't spell out. Claude Code tells Claude how to rewrite the refused command, such as splitting it into plain, separate commands. **You can't turn this check off.**"

> "These checks read the path an edit targets, the directory a command runs in, and the text of the command. None of them tracks which files a shell command writes, so a command that writes into the main checkout without running git there, such as `cp` or a shell redirect, isn't refused by them."

> "Claude sees each refusal as a tool error that names the worktree and says how to proceed."

**Needs for a reimplementation:** yes — this is the *correctness* core of parallel file editing. Three things to copy: (a) the four-check decomposition (path / cwd / redirect / command shape); (b) **fail closed** — "or whose working directory it can't verify stays outside it"; (c) **the refusal is a tool error with actionable guidance**, not a hard error, so the model can rewrite and retry. The documented limitation (shell commands can still write into the main checkout) is honest and worth reproducing verbatim in your own docs.

---

### P9 — Agent teams use a file-backed mailbox and a shared task list with a lock, on disk, under `~/.claude`

**Status:** OBSERVED-DOC (paths and fields) + OBSERVED-CLI (task-list file shape on this host)
**Source:** `https://code.claude.com/docs/en/agent-teams`, section "Architecture"

> "An agent team consists of:
> | Component | Role |
> | **Team lead** | The main Claude Code session that spawns teammates and coordinates work |
> | **Teammates** | Separate Claude Code instances that each work on assigned tasks |
> | **Task list** | Shared list of work items that teammates claim and complete |
> | **Mailbox** | Messaging system for communication between agents |"

> "Each agent's mailbox is a JSON file at `~/.claude/teams/{team-name}/inboxes/{agent-name}.json`. Claude Code validates every entry when it reads a mailbox file. Entries that don't match the message format are reported as errors and removed from the file; the valid messages are still delivered."

> "Claude Code reports a message as sent only when the write to the recipient's mailbox file succeeds, whether the message is plain text or a structured protocol message such as a plan approval or shutdown request. When the write fails, for example because the disk is full or the mailbox directory isn't writable, the sending agent receives an error and nothing is sent."

> "Claude Code manages task dependencies automatically: when a teammate completes a task that other tasks depend on, it unblocks the dependent tasks without any action from you."

> "Teams and tasks are stored locally under a session-derived name. The name is `session-` followed by the first eight characters of the session ID:
> * **Team config**: `~/.claude/teams/{team-name}/config.json`. Claude Code removes the team config directory when the session ends.
> * **Task list**: `~/.claude/tasks/{team-name}/`. This directory stays on disk after the session ends. To change [how long Claude Code keeps it](...), set [`cleanupPeriodDays`](...)."

> "The team config holds runtime state such as session IDs and tmux pane IDs, so don't edit it by hand or pre-author it: your changes are overwritten on the next state update."

> "The team config contains a `members` array with each member's name and agent ID. The lead's entry always carries the agent type `team-lead`. A teammate's entry carries whatever agent type the lead named when spawning it, whether a [built-in type](...) or a [subagent definition](...), and omits the field when the lead named none. Teammates can read this file to discover other team members."

> "There is no project-level equivalent of the team config. A file like `.claude/teams/teams.json` in your project directory is not recognized as configuration; Claude treats it as an ordinary file."

Task claiming (`/docs/en/agent-teams`, "Assign and claim tasks"):

> "Tasks have three states: pending, in progress, and completed. Tasks can also depend on other tasks: a pending task with unresolved dependencies cannot be claimed until those dependencies are completed."

> "**Task claiming uses file locking to prevent race conditions when multiple teammates try to claim the same task simultaneously.**"

**OBSERVED-CLI on this host** (Claude Code 2.1.306, Windows): `~/.claude/tasks/` contained two session-UUID-named directories, each holding a zero-byte `.lock` file plus `<n>.json` items. A sampled item:
```json
{"id": "2", "subject": "Read todo-proof.txt back", "description": "Read the contents of todo-proof.txt to verify it was written correctly.", "activeForm": "Reading todo-proof.txt", "status": "pending", "blocks": ["3"], "blockedBy": ["1"]}
```
The `id`/`subject`/`description`/`activeForm`/`status`/`blocks`/`blockedBy` field set and the `.lock` file match the documented contract exactly. `~/.claude/teams/` did not exist on this host (agent teams were never enabled), so the mailbox and `config.json` layout remains **OBSERVED-DOC only**.

**Needs for a reimplementation:** yes — this is the most reusable pattern in the whole area. The contract is: **a directory of one-JSON-file-per-item, plus a lock file, plus a dependency graph encoded as `blocks`/`blockedBy` id arrays.** That is trivially implementable in any language and gives crash-safe, human-inspectable, agent-writable coordination. Copy the "write succeeds = sent" delivery semantics too: a messaging system that reports success on a failed write is worse than useless in a multi-worker system.

---

### P10 — Agent teams are experimental, off by default, and change ordinary delegation when enabled

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/agent-teams`, sections "Enable agent teams" and "How Claude starts agent teams"; also the page's front-matter note

> "Agent teams are experimental and disabled by default. Enable them by setting `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in your [settings.json](/docs/en/settings) or environment. Without that variable, no team is set up at session start, no team directories are written, and Claude does not spawn or propose teammates." (front-matter note)

> "Enabling agent teams also changes ordinary delegation. Claude may [name a subagent](...) on its own, and while agent teams are enabled, a subagent that Claude names launches as a teammate, so teams can form even when you didn't ask for one." ("Enable agent teams")

> "Spawning teammates also requires an interactive session. In [non-interactive mode](/docs/en/headless) with the `-p` flag, including Agent SDK sessions, Claude doesn't spawn teammates, and a subagent that Claude names runs as an ordinary [subagent](...) even with agent teams enabled."

> "The lead's entry always carries the agent type `team-lead`." ("Architecture")

**Needs for a reimplementation:** yes, and this is a trap worth naming: **a feature flag that changes unrelated behaviour is a compatibility hazard.** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` silently converts named subagents into teammates, which changes the result-delivery channel (a teammate "reports back through team messages rather than by returning a result", per P5). A reimplementation should either keep the flag purely additive or document the interception loudly.

---

### P11 — Concurrency is capped by four separate, named, overridable limits

**Status:** OBSERVED-DOC
**Sources:** `/docs/en/sub-agents` ("Concurrent subagent limit", "Let subagents spawn their own subagents"); `/docs/en/workflows` ("Behavior and limits"); `/docs/en/sub-agents` ("Understand automatic delegation")

> "By default, when 20 subagents are running in a session, spawning another with the Agent tool fails with `Concurrent subagent limit reached`, and the error tells Claude not to retry. Spawning succeeds again when the running count drops below the limit. To change the limit, set [`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`] to any positive whole number. Sessions with [ultracode](...) active are exempt: the limit isn't enforced there. Requires Claude Code v2.1.217 or later." (`/docs/en/sub-agents`)

> "The limit blocks only subagents Claude spawns with the Agent tool, but other runs occupy the same slots:
> * An in-session fork you start with [`/subtask`](#fork-the-current-conversation) takes a slot while it runs and is never blocked by the limit.
> * [Resuming a subagent](#resume-subagents) that already finished takes a fresh slot without checking the limit, so resumes can push the running count past it.
> Agents that other features run, such as [workflow](/docs/en/workflows) agents and [agent team](/docs/en/agent-teams) teammates, follow their own limits instead." (`/docs/en/sub-agents`)

> "By default, a subagent can spawn subagents of its own, up to three layers below the main conversation. At the depth limit, Claude Code withholds the `Agent` tool from every subagent except a [fork](...), so a subagent at the limit does its delegated work itself and returns one summary. A fork at the limit keeps `Agent` in its inherited tool list, but the tool returns an error instead of spawning. … To change the limit, set `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` to the number of subagent layers you want below your main conversation." (`/docs/en/sub-agents`)

> "| Up to 16 concurrent agents by default, fewer when Claude Code has fewer CPUs available, including inside a CPU-limited container. To change the limit, set [`CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`] to a value from 1 to 256, which requires Claude Code v2.1.269 or later | Bounds local resource use |
> | Up to 4,096 items in a single `parallel()` or `pipeline()` call: the runtime rejects a longer list with an error | A silent cap would drop part of the workload without telling the script |
> | 1,000 agents total per run | Prevents runaway loops |" (`/docs/en/workflows`, "Behavior and limits")

> "Keep descriptions brief: Claude Code shows a startup warning when your subagents' combined descriptions pass [the 15,000-token limit](...), and still loads every subagent." (`/docs/en/sub-agents`)

**Needs for a reimplementation:** yes, and the *shape* of the limits is the lesson, not the numbers: (a) a **count-based** concurrency cap that fails the spawn with a specific error string; (b) a **depth** cap implemented by *withholding the tool* rather than by erroring; (c) a **batch-size** cap that errors rather than truncating ("A silent cap would drop part of the workload without telling the script"); (d) a **total** cap to stop runaway loops; (e) a **context-budget** cap on descriptions with a warning rather than a rejection. Note also that the concurrency slot is *shared* across spawn mechanisms but the *enforcement* is per-mechanism, and that "resumes take a fresh slot without checking the limit, so resumes can push the running count past it" — a documented leak, reproduced faithfully here because it is a real observable behaviour.

---

### P12 — Dynamic workflows are a sandboxed JavaScript runtime with four primitives and a deterministic-replay rule

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/workflows`, sections "What the saved script looks like", "How a workflow runs", "Edit a saved script"

> "The body is plain JavaScript with top-level `await`. `agent()` spawns one subagent, `pipeline()` runs one per item in a list, and `parallel()` runs a set of agent tasks at the same time and waits for all of them."

> "An `agent()` call resolves to `null` if you stop it mid-run or it hits an unrecoverable API error. `pipeline()` keeps each `null` in the results array, which is why the example ends with `.filter(Boolean)` to drop those entries."

> "If you pass a `schema` on an `agent()` call, that subagent returns JSON matching the shape instead of prose. Claude Code checks the schema before starting the subagent: when it can prove the schema contradicts itself, the call fails with an error naming the contradiction, and the subagent never starts. One contradiction it can prove is a `required` key that `additionalProperties: false` rules out."

> "If the subagent's output still fails validation after five attempts, the call fails with an error that includes the last validation failure. To change the attempt count, set [`MAX_STRUCTURED_OUTPUT_RETRIES`]."

> "**Timestamps and randomness**: Claude Code makes `Date.now()`, `Math.random()`, and a no-argument `new Date()` throw inside the script, so that a [relaunched run](#resume-after-a-pause) repeats the same `agent()` calls. Pass a timestamp in through `args` instead."

> "No module loading: a script that contains `import()` fails before the run starts | The script body is plain JavaScript. Put work that needs a library in an agent's task" (`/docs/en/workflows`, "Behavior and limits")

> "The workflow runtime executes the script in an isolated environment, separate from your conversation. Intermediate results stay in script variables instead of landing in Claude's context."

> "Every run writes its script to a file under your session's directory in `~/.claude/projects/`. Claude receives the path when the run starts, so you can ask for it. You can open that file to read the orchestration Claude wrote, diff it against a previous run's script, or edit it and ask Claude to relaunch from the edited version."

> "Claude can start a workflow only from a script file the session is already allowed to read. To run a script kept outside your working directory, add its directory with [`/add-dir`] or a Read allow rule first."

**Needs for a reimplementation:** yes — the workflow model is the cleanest "merge" mechanism in the product because **the script is the merge point**: intermediate results live in script variables, and only the returned value reaches the conversation. The `Date.now()`/`Math.random()` ban is a genuinely clever, copyable idea: it makes a run **deterministically replayable**, which is what makes resume-from-cache possible. Any reimplementation offering scriptable fan-out should consider the same determinism rule.

---

### P13 — Workflow resume is defined by *which agents run again*, and a mid-run failure reruns everything after it

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/workflows`, section "Which agents run again"

> "Claude Code replays the run in the order agents start, and each agent either returns its saved result or runs again:
> * **Completed**: returns its saved result. The first agent whose prompt differs from the previous run, because you edited the script or an earlier agent returned something different, runs again, and so does every agent after it, even ones that completed.
> * **Still running when you stopped**: starts over. Stopping the whole run doesn't count any agent as failed.
> * **Failed**: runs again, and so does every agent the script starts after it, even ones that completed. Stopping one agent alone, by selecting it in [`/workflows`](#watch-the-run) and pressing `x`, counts as failing."

> "That last case means a failure in the middle of a fan-out reruns work that already finished. If a script starts A, B, C, and D in that order and B fails, relaunching returns A from cache and runs B, C, and D again."

> "In local and cloud sessions alike, when Claude relaunches an earlier run and Claude Code can't find that run's saved results at all, the relaunch fails with a `nothing to resume` error instead of starting the run over on its own."

**Needs for a reimplementation:** yes — this is the observable contract of *idempotent replay*, and it is a specific policy: **replay in start order; the first divergence invalidates everything downstream.** Any reimplementation with a resume feature needs an explicit answer to "does a mid-run failure re-execute completed siblings?" The reference product's answer (yes) is conservative and worth copying because it avoids stale-cache inconsistencies.

---

### P14 — Background sessions are hosted by a supervisor daemon with a documented, machine-readable state layout

**Status:** OBSERVED-DOC (paths, fields, lifecycle) + OBSERVED-CLI (layout and JSON on this host)
**Source:** `https://code.claude.com/docs/en/agent-view`, sections "The supervisor process", "Where state is stored", "List sessions as JSON"

> "The supervisor is a background service that runs your background sessions so they keep working after you close agent view or your terminal. Claude Code starts it the first time you background a session or open agent view, and you don't need to manage it yourself."

> "Each session is its own Claude Code process under the supervisor, and what happens to that process depends on the session's state:
> * **Working, paused on a permission prompt or other dialog, or attached**: the process keeps running. …
> * **Finished or waiting for your next message, and unattached for about an hour**: the supervisor stops the process to free resources. … Pin a session with `Ctrl+T` to keep its process running.
> * **Exited unexpectedly while the supervisor is running**: the supervisor restarts the process. …
> * **After an auto-update**: the supervisor restarts itself onto the new version and moves idle sessions over in the background. …
> * **The supervisor itself stops** … on macOS and Linux, your sessions stop unless a new supervisor connects within about a minute."

Documented on-disk layout:

> | Path | Contents |
> | `~/.claude/daemon.log` | Supervisor log |
> | `~/.claude/daemon/roster.json` | List of running background sessions, used to reconnect after a restart |
> | `~/.claude/jobs/<id>/state.json` | Per-session state shown in agent view. Read it through [`claude agents --json`](#read-session-state-from-a-script) instead of parsing the file |
> | `~/.claude/jobs/<id>/tmp/` | Per-session scratch directory. Claude's `Write` and `Edit` calls here don't prompt for permission. Removed when the session is deleted |

> "Each background session has the `CLAUDE_JOB_DIR` environment variable set to its `~/.claude/jobs/<id>` directory, so shell commands the session runs can write temporary files to `$CLAUDE_JOB_DIR/tmp` without colliding with parallel sessions."

> "The files under `~/.claude/jobs/<id>/` are not a stable interface. Values that a session or another program writes to `state`, `detail`, `tempo`, or `needs` are replaced on the next update."

Documented JSON listing contract:

> "`claude agents --json` prints active sessions as a JSON array and exits: every live session, plus background sessions that are still working or blocked even when their process has exited. Add `--all` to also include completed background sessions, and `--cwd <path>` to limit the list to sessions started under that directory."

> | Field | Present | Description |
> | `cwd`, `kind`, `startedAt` | Always | The working directory, `interactive` or `background`, and the start time in Unix milliseconds |
> | `id` | Background sessions | Short ID, usable with `claude attach`, `claude logs`, and `claude stop` |
> | `state` | Background sessions | One of `working`, `blocked`, `done`, `failed`, or `stopped`. |
> | `pid`, `status` | While the process is alive | Process ID and one of `busy`, `waiting`, or `idle` |
> | `waitingFor` | When `status` is `waiting` | What the session is blocked on: `permission prompt` for an approval, `input needed` for a question from Claude or an MCP server's input request, `sandbox request`, `worker request`, or `dialog open` |
> | `sessionId`, `name` | When set | `sessionId` is the full session UUID, usable with [`claude --resume`] |

> "`claude agents --json` is the supported way to read session state from outside Claude Code, for example from a status bar, a scheduler, or another Claude session that supervises background work."

> "**The files under `~/.claude/jobs/<id>/` are not a stable interface.**" (i.e. `state.json` is explicitly *not* the public interface; the JSON CLI is)

**OBSERVED-CLI on this host** (Claude Code 2.1.306, Windows):
- `claude agents --json` returned a 9-element array. The union of keys across all entries was exactly: `cwd`, `id`, `kind`, `name`, `pid`, `sessionId`, `startedAt`, `state`, `status`. Interactive entries had `kind: "interactive"` and `status: "busy"`; background entries had `kind: "background"`, an 8-hex `id`, and `state: "stopped"` / `"blocked"`.
- `~/.claude/jobs/17989b89/` contained exactly `state.json`, `timeline.jsonl`, `tmp/` — matching the documented layout.
- `state.json` top-level keys observed: `backend, children, cliVersion, createdAt, cwd, daemonShort, detail, firstTerminalAt, inFlight, intent, lastTerminalAt, linkScanOffset, linkScanPath, name, nameSource, output, providerEnv, respawnFlags, resumeSessionId, sessionId, state, tempo, tokens, updatedAt`. `state.json` also contained an `inFlight` object with `{tasks, queued, kinds, drainableMonitors}`.
- `timeline.jsonl` contained one JSON object per line with keys `at`, `state`, `detail`, `text` — a compact per-step event log.
- `~/.claude/daemon/roster.json` contained `{"proto": 1, "supervisorPid": …, "updatedAt": …, "workers": {}}`.
- `claude daemon status` printed: `not running` / `bg sessions:` / `sock dir:     \\.\pipe\cc-daemon-*` / `control.sock: unreachable (connect ENOENT …)` / `bg workers:   0 in roster.json (control unreachable)` / `roster.json:  updated 745s ago` / `daemon.log:   2.7KB at <HOME>\.claude\daemon.log`.
- `claude logs 17989b89` returned: `Couldn't read logs for 17989b89 — job not found — it may have already exited`.
- `~/.claude/jobs/pins.json` existed with content `[]` (the pin list backing `Ctrl+T`).

**Needs for a reimplementation:** yes, emphatically. The most transferable decision here: **publish one machine-readable listing command and declare the on-disk files private.** The reference product says so in writing ("not a stable interface") and tells integrators to use `claude agents --json`. Copying that discipline — a stable JSON CLI, an unstable private directory — is the difference between a feature others can build on and a feature nobody can integrate with.

---

### P15 — Cross-session messaging is the only documented way for independent sessions to exchange findings

**Status:** OBSERVED-DOC
**Source:** `https://code.claude.com/docs/en/cross-session-messaging`, sections "Message another session", "Message delivery", "Message sessions on other machines"

> "Claude discovers the target with `ListAgents` and sends with `SendMessage`, so you never call either tool yourself."

> "The receiving Claude reads the message between tool calls during an active turn, so a running tool is never interrupted. When the receiving session is idle, Claude Code starts a new turn with the message."

> "Claude Code refuses a message in the following cases:
> * The message is [over the size cap](#limitations). Claude Code refuses it in the sending session, before it leaves.
> * A rapid burst to a session on this machine has reached [what that session's inbox accepts](#limitations). Claude Code refuses further messages to that session.
> * A session beyond this machine is [listed as unable to receive cross-session messages](...). Claude Code refuses the message in the sending session, before it leaves this machine.
> * The reply target on this machine fails a safety check, such as a symlinked target."

Inbound outcomes:

> "The receiving session checks each arriving message against its own [inbound controls](#control-inbound-messages), and the check ends in one of three outcomes:
> * **Delivered**: Claude Code passes the message to the receiving Claude.
> * **Held**: Claude Code sets the message aside undelivered. A held message reaches Claude only when you approve it or a later mode or settings change allows it.
> * **Refused**: Claude Code drops the message without delivering it."

Transport by target location:

> | Where the other session runs | How the message travels |
> | On this machine | Over a per-session socket on macOS and Linux, or a per-session named pipe on native Windows, never through Anthropic servers |
> | On another of your machines | Through Anthropic servers, arriving over that machine's [Remote Control](...) connection |
> | In the [cloud](...) | Through Anthropic servers, straight to the cloud session |

Permission boundary across sessions:

> "Permission boundaries stay per-session. Claude is instructed never to ask another session for an action that was denied or blocked in its own session, or that its own permission settings would block, and to route that work back to you instead."

Team-message variant (`/docs/en/agent-teams`, "Messages between agents"):

> "When one agent sends another a message over `SendMessage`, Claude Code tells the receiving agent the message came from another Claude session, not from you. A teammate can't approve a permission prompt or supply consent on your behalf, and a teammate that was denied an action can't relay it to another teammate to bypass the check."

**Needs for a reimplementation:** yes, and the three-outcome delivery model (**Delivered / Held / Refused**) is the right shape for any agent-to-agent message bus — it gives the user a veto that is neither a hard failure nor a silent drop. The "never through Anthropic servers" local transport (Unix socket / Windows named pipe) is also a clean privacy property worth adopting.

---

### P16 — The full user-facing shell surface for background work

**Status:** OBSERVED-DOC (command list) + OBSERVED-CLI (flag help text captured verbatim on this host)
**Source:** `/docs/en/agent-view` ("Manage sessions from the shell"); `claude --help` and `claude agents --help` run on this host

Documented command table (`/docs/en/agent-view`):

> | `claude agents` | Open agent view |
> | `claude agents --cwd <path>` | Open agent view scoped to sessions started under `<path>` |
> | `claude agents --json` | Print sessions as a JSON array and exit. |
> | `claude attach <id\|name>` | Attach to a session in this terminal |
> | `claude logs <id\|name>` | Print the session's recent output |
> | `claude stop <id>` | Stop a session. Also accepts `claude kill` |
> | `claude respawn <id>` | Restart a session, running or stopped, for example to pick up an updated Claude Code binary. A session that has a saved conversation resumes it |
> | `claude respawn --all` | Restart every running session, e.g. to move all sessions onto an updated Claude Code binary at once |
> | `claude rm <id>` | Remove a session from the list, along with a worktree Claude created for it when that's safe to delete; the conversation transcript stays on your local machine and remains available through `claude --resume` |
> | `claude rm <id> --discard-unpushed <commit>@<worktree-id>` | Delete a session whose delete was refused over unpushed commits, discarding the worktree along with its branch and commits. … Requires v2.1.260 or later |
> | `claude rm <id> --force-remove-worktree <worktree-id>` | Delete a session whose delete was refused because git or the `WorktreeRemove` hook couldn't remove its worktree, deleting the worktree directory anyway and leaving its branch in the repository. … Requires v2.1.268 or later |
> | `claude daemon status` | Print the [supervisor's](#the-supervisor-process) state, version, socket directory, and worker count |
> | `claude daemon logs` | Follow the supervisor's log file, [`~/.claude/daemon.log`](#where-state-is-stored), printing new lines as they arrive until you press `Ctrl+C` |
> | `claude daemon stop --any` | Stop the supervisor process and the background sessions it hosts. Pass `--keep-workers` to leave background sessions running for the next supervisor to reconnect to. The next `claude agents` or `claude --bg` starts a fresh supervisor |

**OBSERVED-CLI** — `claude --help` (2.1.306) on this host, verbatim excerpts:

> `--bg, --background                    Start the session in the background and return immediately. Prints the id that `claude attach`, `logs`, `stop` and `rm` take; `claude agents` lists them. With --resume <session-id>, continues that session in the background under the same ID, or starts a copy and says so when the session is already running`

> `-w, --worktree [name]                 Create a new git worktree for this session (optionally specify a name)`

> `--tmux                                Create a tmux session for the worktree (requires --worktree). Uses iTerm2 native panes when available; use --tmux=classic for traditional tmux.`

> `--forward-subagent-text               Forward subagent text and thinking blocks as assistant/user messages with parent_tool_use_id set (only works with --print and --output-format=stream-json)`

> `--agents <json-or-file>               JSON object defining custom agents, or with --print the path to a file that holds one (e.g. '{"reviewer": {"description": "Reviews code", "prompt": "You are a code reviewer"}}')`

> `--agent <agent>                       Agent for the current session. Overrides the 'agent' setting.`

Subcommand list from `claude --help`:

> `  agents [options]                      Manage background agents`
> `  attach <id|name>                      Open a background session in this terminal. <id> is the short id that `claude --bg` prints and `claude agents` lists. Part of the session name works too`
> `  logs <id|name>                        Print a background session's recent terminal output`
> `  respawn [options] [id]                Restart a background session, or all of them with --all, so it runs the current Claude Code version`
> `  rm <id>                               Delete a background session, and its worktree when that is safe. Works on sessions that have already exited`
> `  stop|kill <id>                        Stop a background session. Its conversation is kept: `claude attach <id>` opens it again, `claude --resume` works once it is stopped`

`claude agents --help` on this host, verbatim excerpts:

> `--all                                 With --json: also include completed background sessions`
> `--cwd <path>                          Show only background sessions started under <path>`
> `--json                                Print active sessions (interactive and background) as a JSON array and exit (for scripting; does not require a TTY)`
> `--agent <agent>                       Default agent for sessions dispatched from agent view. Overrides the 'agent' setting.`
> `--effort <level>                      Default effort level for sessions dispatched from agent view`
> `--model <model>                       Default model for sessions dispatched from agent view`
> `--permission-mode <mode>              Default permission mode for sessions dispatched from agent view`
> `--add-dir <directory>                 Additional directory to allow tool access to in dispatched sessions (repeatable)`
> `--mcp-config <config>                 MCP server configuration to apply to dispatched sessions (repeatable)`
> `--plugin-dir <path>                   Load plugins from specified directory for the agent view and dispatched sessions; a folder of plugins loads each child (repeatable)`
> `--restricted                          Start dispatched sessions in restricted mode`
> `--setting-sources <sources>           Comma-separated list of setting sources to load (user, project, local).`
> `--settings <file-or-json>             Settings file or JSON string to apply to the agent view and dispatched sessions`
> `--strict-mcp-config                   Only use MCP servers from --mcp-config in dispatched sessions`

**Needs for a reimplementation:** yes — this is the entire scripting surface. Note that **`claude agents` carries a full parallel set of dispatch defaults** (model, effort, permission-mode, agent, settings, mcp-config, plugin-dir, add-dir, restricted, setting-sources) distinct from the main `claude` launch flags. A reimplementation that only has a "list" command will not be scriptable; the dispatch defaults are what let a status bar, a scheduler, or a supervisor spawn correctly-configured workers.

---

### P17 — `claude --bg` and `/batch` define the two blessed "spawn a bunch of workers" entry points

**Status:** OBSERVED-DOC
**Sources:** `/docs/en/agent-view` ("Dispatch an agent from your shell"); `/docs/en/commands` (`/batch` row); `/docs/en/agent-view` ("Send or copy a session to the background", "Copy the session with /fork")

> "Pass `--bg` or its long form `--background` to start a session that goes straight to the background:
> ```bash
> claude --bg "investigate the flaky SettingsChangeDetector test"
> ```
> The prompt is the positional argument, not a `-p` value. Claude Code rejects `--bg` combined with `-p` or `--print` before any session is created, because `--print` never starts the interactive session that `claude agents` attaches to." (`/docs/en/agent-view`)

> "| `/batch <instruction>` | **[Skill](/docs/en/skills#bundled-skills).** Orchestrate large-scale changes across a codebase in parallel. Researches the codebase, decomposes the work into 5 to 30 independent units, and presents a plan. Once approved, spawns one [background subagent](/docs/en/sub-agents#run-subagents-in-foreground-or-background) per unit in an isolated [worktree](/docs/en/worktrees). Each subagent implements its unit, runs tests, and publishes its change. Requires a git repository or a [`WorktreeCreate` hook](/docs/en/hooks#non-git-version-control) that creates the worktrees. Outside a git repository, `/batch` requires Claude Code v2.1.281 or later. |" (`/docs/en/commands`)

> "Run `/background` or its alias `/bg` to move the current conversation into a background session. Pass a prompt such as `/bg run the test suite and fix any failures` to give one more instruction first. If Claude is responding when you run `/bg`, the response continues in the background session." (`/docs/en/agent-view`)

> "Run `/fork` to copy the current conversation into a new background session while the original keeps running. The copy starts with everything in the conversation up to that point… It also carries over the model, permission mode, effort level, and any directories or "don't ask again" permission grants you added during the session. The copy appears as its own row in agent view." (`/docs/en/agent-view`)

> "After the fork, the two conversations are independent: nothing the copy does enters the original conversation on its own, though in sessions where [cross-session messaging](...) is enabled, either session's Claude can explicitly message the other." (`/docs/en/agent-view`)

> "Exiting a session that still has background work running, such as subagents, background shell commands, workflows, or [monitors](...), shows a `Background work is running` dialog instead of quitting immediately. Choose `Move to background and exit` … The option isn't shown when [agent view is turned off](#turn-off-agent-view)." (`/docs/en/agent-view`)

> "When a [dynamic workflow](/docs/en/workflows) still has subagents running, Claude Code asks before backgrounding with the `Background this session?` dialog, which says how many subagents would restart. Choose `Stay` to let them finish first. If you confirm, Claude Code replays the run in the background session: subagents that were still running start over from the beginning, so the tokens they used so far are spent again." (`/docs/en/agent-view`)

**Needs for a reimplementation:** yes. `/batch` is the most directly copyable *product-shaped* feature: **research → decompose into N units → present a plan for approval → spawn one isolated worker per unit → each worker implements, tests, and publishes its change.** That five-step shape is a complete, self-contained "parallel implementation" workflow with a human gate in the middle.

---

## 6.2 Capability table

| # | Capability | Mechanism | Observable contract | Classification | Needed for reimpl. |
| :- | :- | :- | :- | :- | :- |
| C1 | Spawn an isolated worker | Subagent | `Agent` tool, input `{description, prompt, subagent_type?, model?, effort?, run_in_background?, name?, isolation?}`; result returns to parent | OBSERVED-DOC | **Yes** |
| C2 | Spawn a context-inheriting worker | Fork | `/subtask <task>`; inherits full parent context; result returns to parent | OBSERVED-DOC | Yes |
| C3 | Copy a session into a parallel session | `/fork`, `claude --bg` | New background session row; carries model, permission mode, effort, dirs, grants | OBSERVED-DOC | Yes |
| C4 | Worker result isolation | Subagent/fork | Parent sees only final result, never intermediate tool calls | OBSERVED-DOC | **Yes** |
| C5 | Worker-to-worker messaging | Agent team | `~/.claude/teams/{team-name}/inboxes/{agent-name}.json`; write-succeeds = sent | OBSERVED-DOC | Yes |
| C6 | Shared work list | Agent team / Task tools | `~/.claude/tasks/{team-name}/{n}.json` with `id/subject/description/status/blocks/blockedBy`; `.lock` for claiming | OBSERVED-DOC + OBSERVED-CLI | **Yes** |
| C7 | File-edit isolation | Worktree | `isolation: "worktree"` frontmatter/param; four enforcement checks; fourth not disableable | OBSERVED-DOC | **Yes** |
| C8 | Human dispatch of background sessions | Agent view | `claude agents` TUI; `claude --bg "<prompt>"`; rejects `--bg` with `-p` | OBSERVED-DOC + OBSERVED-CLI | Yes |
| C9 | Machine-readable session listing | Agent view | `claude agents --json [--all] [--cwd <path>]`; fields `cwd,kind,startedAt,id,state,pid,status,waitingFor,sessionId,name` | OBSERVED-DOC + OBSERVED-CLI | **Yes** |
| C10 | Session lifecycle from shell | Agent view | `claude attach/logs/stop/kill/respawn/rm`; `rm` refuses on unpushed commits / locked worktrees | OBSERVED-DOC + OBSERVED-CLI | Yes |
| C11 | Supervisor daemon | Agent view | `~/.claude/daemon/roster.json` (`proto`, `supervisorPid`, `updatedAt`, `workers`); `claude daemon status/logs/stop --any` | OBSERVED-DOC + OBSERVED-CLI | Yes |
| C12 | Per-session scratch dir | Agent view | `~/.claude/jobs/<id>/tmp/`, exposed as `$CLAUDE_JOB_DIR/tmp`; writes there don't prompt | OBSERVED-DOC + OBSERVED-CLI | Yes |
| C13 | Scriptable fan-out with merge | Workflow | `agent()`, `pipeline()`, `parallel()`; `phase()`, `log()`, `args`; results in script vars, not conversation | OBSERVED-DOC | **Yes** |
| C14 | Deterministic replay | Workflow | `Date.now()`, `Math.random()`, `new Date()` throw inside the script | OBSERVED-DOC | Yes |
| C15 | Resumable runs | Workflow | Replay in start order; first divergence invalidates downstream agents | OBSERVED-DOC | Yes |
| C16 | Structured agent output | Workflow | `schema` on `agent()`; validated before spawn; 5 retries via `MAX_STRUCTURED_OUTPUT_RETRIES` | OBSERVED-DOC | Yes |
| C17 | Cross-session finding exchange | Cross-session messaging | `ListAgents` + `SendMessage`; Delivered / Held / Refused; local transport never hits Anthropic servers | OBSERVED-DOC | Yes |
| C18 | Packaged parallel change | `/batch` skill | 5–30 units, plan approval gate, one worktree-isolated background subagent per unit | OBSERVED-DOC | **Yes** |
| C19 | Concurrency caps | All | 20 subagents, depth 3, 16 workflow agents (1–256), 4,096 items/call, 1,000 agents/run, 15,000-token description budget | OBSERVED-DOC | **Yes** |
| C20 | Background work panel | UI | `/tasks` lists, attaches to, and stops background items; finished subagents included | OBSERVED-DOC | Yes |
| C21 | Workflow progress view | UI | `/workflows`; keys `↑↓ Enter ←→ Esc j k f p x r s` | OBSERVED-DOC | Yes |
| C22 | Agent-team display modes | Agent team | `in-process` (default), `auto`, `tmux`, `iterm2`; `teammateMode` setting; `--teammate-mode` flag (not in `--help`) | OBSERVED-DOC | Optional |
| C23 | Team shutdown protocol | Agent team | `shutdown_request` / `plan_approval_response` structured messages over `SendMessage` | OBSERVED-DOC | Optional |
| C24 | Team lead metadata | Agent team | `~/.claude/teams/{team-name}/config.json` with `members[]`; lead's agent type is `team-lead` | OBSERVED-DOC | Optional |

---

## 6.3 Dependencies

### 6.3.1 Network / account / provider dependencies

| Dependency | Required by | Evidence |
| :- | :- | :- |
| A model provider (Anthropic API, Bedrock, Vertex, Foundry, or a gateway) | Every worker | Each worker is a full Claude session |
| Anthropic account / subscription (for subscription-gated surfaces) | Agent view (research preview), Projects (public beta on Pro and Max), cloud sessions, Remote Control | `agents.md` table: "Public beta on Pro and Max"; "Research preview" for agent view |
| Anthropic servers | Cross-machine and cloud cross-session messaging | "Through Anthropic servers, arriving over that machine's Remote Control connection" |
| Git | Worktree isolation, `/batch` | `/batch`: "Requires a git repository or a `WorktreeCreate` hook" |
| tmux or iTerm2 (+ `it2` CLI) | Agent-team split-pane mode | "Split-pane mode requires either tmux or iTerm2 with the `it2` CLI" |
| WebSearch tool | `/deep-research` bundled workflow | "Requires the WebSearch tool to be available" |
| Local daemon supervisor | Background sessions | `claude agents` starts it; `claude daemon status` reports it |

**On this host:** the environment uses a custom `ANTHROPIC_BASE_URL` serving a non-Anthropic model. Per the workflow's own constraint, subscription-gated surfaces (agent view's dispatch of *new* sessions, Projects/threads, cloud sessions, Remote Control, `ultrareview`) could not be exercised end-to-end. Everything listed above for those surfaces is **OBSERVED-DOC**, not OBSERVED.

### 6.3.2 Local filesystem dependencies (all observed on this host)

| Path | Role |
| :- | :- |
| `~/.claude/jobs/<id>/state.json` | Per-session state (explicitly *not* a stable interface) |
| `~/.claude/jobs/<id>/timeline.jsonl` | Per-step event log |
| `~/.claude/jobs/<id>/tmp/` | Per-session scratch, exposed as `$CLAUDE_JOB_DIR/tmp` |
| `~/.claude/jobs/pins.json` | Pinned sessions |
| `~/.claude/daemon/roster.json` | Supervisor roster |
| `~/.claude/daemon.log` | Supervisor log |
| `~/.claude/tasks/<team-or-session>/` | Shared task lists + `.lock` |
| `~/.claude/teams/<team-name>/config.json` | Team runtime state + `members[]` (not present on this host) |
| `~/.claude/teams/<team-name>/inboxes/<agent>.json` | Per-agent mailboxes (not present on this host) |
| `~/.claude/projects/<session>/` | Workflow scripts and saved results |
| `.claude/workflows/` | Saved workflow scripts (project-scoped, shareable) |
| `~/.claude/workflows/` | Saved workflow scripts (user-scoped) |
| `.claude/worktrees/` | Claude-created worktrees for background sessions and subagents |
| `~/.claude/agents/`, `.claude/agents/` | Custom subagent definitions |

### 6.3.3 Configuration surface (exact keys and env vars)

| Key / env var | Effect | Source |
| :- | :- | :- |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` | Enables agent teams; also converts named subagents to teammates | `/docs/en/agent-teams` |
| `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | Concurrent subagent cap (default 20) | `/docs/en/sub-agents` |
| `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` | Nesting depth (default 3) | `/docs/en/sub-agents` |
| `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` | Workflow concurrency (default 16, range 1–256) | `/docs/en/workflows` |
| `CLAUDE_CODE_WORKFLOW_PREFIX_STAGGER_MS` | Fan-out cache-stagger hold (default 5000; `0` disables) | `/docs/en/workflows` |
| `CLAUDE_CODE_FORK_SUBAGENT=0` | Turns off fork mode; also lets Claude *wait* for subagents in interactive sessions | `/docs/en/sub-agents` |
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` | Claude waits for every subagent; background tasks off, Ctrl+B off | `/docs/en/sub-agents` |
| `CLAUDE_CODE_DISABLE_AGENT_VIEW` / `disableAgentView: true` | Turns off background agents and agent view entirely | `/docs/en/agent-view` |
| `CLAUDE_CODE_DISABLE_WORKFLOWS=1` / `"disableWorkflows": true` | Turns off dynamic workflows | `/docs/en/workflows` |
| `CLAUDE_CODE_DISABLE_BG_EXIT_HANDOFF=1` | Stop background work with the process instead of handing it off | `/docs/en/agent-view` |
| `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` | Model selection for spawned workers | `/docs/en/agent-teams` |
| `MAX_STRUCTURED_OUTPUT_RETRIES` | Structured-output validation retry count (default 5) | `/docs/en/workflows` |
| `worktree.bgIsolation: "none"` | Disable worktree isolation for background sessions in a repo | `/docs/en/agent-view` |
| `worktree.baseRef: "head"` | Base the worktree branch on `HEAD` instead of the default branch | `/docs/en/worktrees` |
| `teammateMode` (`"in-process"` / `"auto"` / `"tmux"` / `"iterm2"`) | Agent-team display mode | `/docs/en/agent-teams` |
| `subagentPromptCacheTtl: "1h"` | 1-hour prompt cache for subagent/teammate/workflow requests | `/docs/en/agent-teams`, `/docs/en/workflows` |
| `cleanupPeriodDays` | Retention for task lists and worktree sweep | `/docs/en/agent-teams`, `/docs/en/worktrees` |
| `workflowSizeGuideline` (`unrestricted`/`small`/`medium`/`large`) | Advises Claude how many agents to aim for (default `medium`) | `/docs/en/workflows` |
| `ultracode` | Auto-plan a workflow for every substantive task | `/docs/en/workflows` |
| `isolation: worktree` (subagent frontmatter) | Run this subagent in its own worktree | `/docs/en/sub-agents` |
| `background: true` (subagent frontmatter) | Keep this subagent in the background even when Claude asks to wait | `/docs/en/sub-agents` |
| `maxTurns` (subagent frontmatter) | Cap turns; output marked partial at the limit | `/docs/en/sub-agents` |

---

## 6.4 Limitations of this investigation

1. **The assigned page is thin.** `agents.md` is 68 lines and contains no flags, JSON keys, or file paths. Roughly 85% of the concrete claims in this area come from the six pages it links to, plus `tools-reference` and `commands`. A reader who only reads `agents.md` will implement a taxonomy, not a system.
2. **No decompilation was performed** — prohibited by the Anthropic ToS and the docs' "The Claude Code binary must not be modified." All internal behaviour is inferred from public docs plus black-box CLI observation.
3. **The host runs against a custom `ANTHROPIC_BASE_URL`**, not `api.anthropic.com`. Subscription-gated surfaces could not be exercised: agent-view *dispatch* of a new session, Projects/cloud threads, Remote Control, `claude ultrareview`, `claude daemon` with a live supervisor, and the agent-team mailbox were not directly observed. Those are marked OBSERVED-DOC.
4. **Windows-only host.** The transport details differ by platform — "Over a per-session socket on macOS and Linux, or a per-session named pipe on native Windows, never through Anthropic servers" — and this host confirmed the Windows named-pipe form (`\\.\pipe\cc-daemon-*`).
5. **The supervisor was not running** during observation (`claude daemon status` → `not running`, `0 in roster.json`). The restart/idle-eviction lifecycle rules are therefore documentation-only.
6. **No agent team was ever created**, so `~/.claude/teams/` was absent and the mailbox/`config.json` formats remain unverified in the wild.
7. **The `state.json` schema is explicitly unstable** ("The files under `~/.claude/jobs/<id>/` are not a stable interface"), so the observed key list is a snapshot, not a contract.
8. **Workflow runtime internals were not observed** — no workflow was executed, so `parallel()`/`pipeline()` behaviour, cache-stagger timing, and replay semantics are documentation-only.
9. **Fetches are untrusted data.** No fetched page contained instructions directed at the agent; nothing from fetched content was executed. All commands run were the published CLI's own `--help` surfaces and read-only listing commands.

---

## 6.5 Unresolved questions (UNKNOWN)

| # | Question | Why the evidence cannot establish it |
| :- | :- | :- |
| U1 | The exact mailbox JSON message schema (`shutdown_request`, `plan_approval_response`, plain text) | The doc describes the *file path* and the *semantics* ("a structured protocol message such as a plan approval or shutdown request") but never shows the JSON. No team was created to observe it. |
| U2 | The `team_name` parameter's history and whether any client still sends it | Only documented as "Deprecated; ignored". |
| U3 | The `isolation: "remote"` value in `AgentInput` | The schema lists it; no public page in this study describes remote isolation. `remote` appears nowhere in the parallel-agent docs. |
| U4 | `SubagentHandback` in auto mode | Described in `tools-reference` as delivering "a subagent's final report to whichever conversation receives that subagent's result" with classifier review; the classifier is not observable on this host. |
| U5 | The exact threshold of the 15,000-token combined-description limit and how it is computed | Only the limit and the warning behaviour are documented. |
| U6 | The cross-session message size cap and inbox burst limit | Both are referenced as "over the size cap" / "what that session's inbox accepts" with the values on the `#limitations` section, which was not fetched in this study. |
| U7 | Whether `claude agents` can be driven non-interactively for dispatch (only `--json` is documented as TTY-free) | The docs say `--json` "does not require a TTY"; no documented non-interactive dispatch exists. |
| U8 | Supervisor restart-after-crash ordering guarantees | Documented as behaviour, not as a protocol. |
| U9 | Whether `parallel()` and `pipeline()` differ in scheduling (concurrency vs. sequential-per-item) | The doc says "`pipeline()` runs one per item in a list, and `parallel()` runs a set of agent tasks at the same time" but does not say pipeline items run concurrently. |
| U10 | `workflowSizeGuideline` mapping to actual agent counts | Documented as "advice, not a cap"; the realised count is model-dependent. |
| U11 | How `Team lead` differs from a plain subagent at the protocol level | Only the `agent type: "team-lead"` marker in `config.json` is documented. |
| U12 | Whether `claude --bg` sessions can be resumed with `--resume` under the same ID after a stop | The `--bg` help text says yes ("With --resume <session-id>, continues that session in the background under the same ID"), and `claude stop` help says "`claude --resume` works once it is stopped" — but this was not exercised end-to-end on this host. |

---

## 6.6 Clean-room implementation opportunities

For each major feature: the **observable contract** (what a user or an integrator can see) and the **idiomatic way to build it**, with no Anthropic code copied.

### 6.6.1 A single spawn tool with mode selection

**Observable contract:** one tool call with `{description, prompt, subagent_type?, model?, effort?, run_in_background?, name?, isolation?}`; the parent receives exactly one final result; the parent's context never receives intermediate worker tool output; a call that carries `name` (under team mode) or a fork flag behaves as a different worker kind.

**Idiomatic build:** implement workers as **coroutines/async tasks in the same process** (Rust `tokio::task`, Go goroutines, TypeScript `Promise`), each with its own message buffer and its own tool registry. Route every worker tool call through the **parent's** permission broker, tagged with the worker's id, so the human sees one prompt stream. Deliver the child's transcript to a separate store, not to the parent's context. Add a `TaskKind` enum (`Subagent | Fork | Teammate`) and dispatch on it. Reject unknown enum values and ignore deprecated fields, exactly as the reference does with `mode`/`team_name`.

**Why it is a clean-room opportunity:** the contract is entirely observable from `--help`, the SDK type, and the docs. The reference implementation's internals (process model, context objects) are irrelevant to matching it.

### 6.6.2 File-backed job registry with a stable JSON listing command

**Observable contract:** `claude agents --json` prints a JSON array with fields `cwd, kind, startedAt, id, state, pid, status, waitingFor, sessionId, name`; `state ∈ {working, blocked, done, failed, stopped}`; `status ∈ {busy, waiting, idle}`; `kind ∈ {interactive, background}`; `waitingFor ∈ {permission prompt, input needed, sandbox request, worker request, dialog open}`; `--all` includes completed; `--cwd <path>` filters. The on-disk files are explicitly *not* a stable interface.

**Idiomatic build:** a supervisor daemon that owns a directory `~/.myagent/jobs/<id>/` containing `state.json`, `events.jsonl`, and `tmp/`; each job's short id is its directory name; a `roster.json` maps ids to live workers; the daemon evicts idle-unattached workers after a timeout and restarts crashed ones. Expose the listing as `myagent agents --json` and treat the JSON as the **only** public contract. Give each job a `MYAGENT_JOB_DIR` env var pointing at its directory so parallel workers can write scratch files without colliding.

**Why it is a clean-room opportunity:** the observable surface is a handful of field names and five state values, all published. The file layout is a design choice, not a copied asset — and the reference explicitly disclaims it as an interface, so reimplementing it differently is not copying.

### 6.6.3 Worktree-based edit isolation with a four-check enforcement layer

**Observable contract:** a worker in an isolated checkout cannot (1) `Edit`/`Write`/`NotebookEdit` a path in the main checkout, (2) run a command whose cwd resolves into the main checkout or can't be verified outside it, (3) redirect git into the main checkout via `git -C`, `--git-dir`, `GIT_DIR`, `GIT_WORK_TREE`, or a `cd` first, (4) run a command whose text cannot be verified to keep git inside the worktree. Refusals arrive as **tool errors naming the worktree and telling the model how to proceed**; the fourth check cannot be disabled. Shell commands that write into the main checkout without invoking git are *not* refused — and this limitation is documented.

**Idiomatic build:** `git worktree add` per worker; record the main-checkout root; at tool-call time, canonicalise the target path (resolve symlinks) and compare against the allowed root set; for shell commands, parse the command with a shell AST library, extract the `cd` chain and any `GIT_DIR`/`GIT_WORK_TREE`/`git -C`/`--git-dir` assignments, and **fail closed** if the resulting cwd or git target cannot be determined. Return a structured error object `{code: "WORKTREE_ISOLATION", main_checkout, allowed_root, remediation}` that the model can act on. Keep a `WorktreeCreate`/`WorktreeRemove` hook interface for non-git VCS.

**Why it is a clean-room opportunity:** the *checks* are a described policy; the implementation is standard path-canonicalisation plus shell parsing, both standard library/tooling territory. The one thing worth copying verbatim is the **fail-closed default and the actionable error**.

### 6.6.4 Shared task list with dependency graph and file-lock claiming

**Observable contract:** one JSON file per item under `~/.myagent/tasks/<team>/<n>.json` with fields `id, subject, description, activeForm, status, blocks, blockedBy`; `status ∈ {pending, in_progress, completed}`; a task with unresolved `blockedBy` cannot be claimed; claiming uses a lock file to prevent two workers claiming the same task.

**Idiomatic build:** an **atomic rename** (`os.replace` / `rename(2)`) or an exclusive lock file (`O_CREAT|O_EXCL`, `flock`, `msvcrt.locking`) as the claim primitive — both are standard, and both are crash-safe (a stale lock can be broken by mtime + pid liveness). Store `blocks`/`blockedBy` as id arrays and compute readiness by graph traversal. Auto-unblock dependents on completion, as the reference does.

**Why it is a clean-room opportunity:** the format is a handful of JSON keys. The interesting engineering (atomic claim, dependency resolution) is generic concurrent-systems work with well-known idioms, not Anthropic-specific.

### 6.6.5 Agent-to-agent mailbox with three-state delivery

**Observable contract:** a per-agent JSON file mailbox; a message is "sent" only when the write succeeds; the receiving side classifies each message as **Delivered**, **Held** (awaiting user approval), or **Refused**; a refused message never reaches the recipient; a message delivered to a worker is labelled as coming from another session, never as coming from the user; a worker can never supply consent for a permission prompt on the user's behalf.

**Idiomatic build:** mailbox directory per team with one file per recipient; the sender writes atomically (write-temp + rename) and treats a failed write as a hard error, not a soft one. The receiver's inbound policy is a three-way enum, with "Held" persisted in a quarantine queue the user can approve from. Label provenance explicitly in the envelope (`from_kind: "agent" | "session" | "user"`) and **never** let `agent` provenance satisfy a permission gate. For local-only transport, use a Unix domain socket on macOS/Linux and a named pipe on Windows, so the messages never leave the machine.

**Why it is a clean-room opportunity:** the three-outcome model and the provenance labelling are policy you can design yourself; the transport is a standard IPC primitive.

### 6.6.6 Scriptable fan-out with a deterministic replay rule

**Observable contract:** a plain-JavaScript (no `import()`) body with top-level `await` and four primitives — `agent(prompt, {schema?, label?})` (one worker), `pipeline(items, fn)` (one worker per item), `parallel(tasks)` (concurrent, awaits all), plus `phase(title)`, `log(msg)`, and the `args` global. Intermediate results live in script variables; only the returned value reaches the conversation. `Date.now()`, `Math.random()`, and `new Date()` **throw** inside the script so a relaunch repeats the same calls. Caps: 4,096 items per `parallel()`/`pipeline()` call (error, not truncation), 1,000 agents per run, 16 concurrent agents by default (1–256 configurable). Replay semantics: replay in start order; the first agent whose prompt differs runs again, and so does every agent after it; a failed agent reruns everything after it. A relaunch with no saved results fails with `nothing to resume` rather than silently starting over.

**Idiomatic build:** run the script in a **restricted JS runtime** (QuickJS, `isolated-vm`, Deno's permissions API, or a wasm sandbox) with `Date`, `Math.random`, and `Date.now` replaced by throwing stubs, and no module loader. Expose `agent`/`pipeline`/`parallel`/`phase`/`log` as injected host functions that call your own worker-spawn function. Persist each agent's prompt, output, and status to a per-run directory; on relaunch, walk the script's agent-start order and reuse a saved result when the recorded prompt matches the current one, else re-execute and invalidate everything downstream. Validate a `schema` *before* spawning (so a self-contradictory schema costs nothing) and retry output validation up to N times, reporting the last failure.

**Why it is a clean-room opportunity:** the whole value of the feature is the *replay contract*, and that contract is published in prose. The runtime sandboxing and the deterministic stubs are standard techniques.

### 6.6.7 Human-facing "watch the workers" surfaces

**Observable contract:** four distinct views — `/tasks` (session-local background items: list, check, attach, stop; includes finished subagents), `/workflows` (runs, phases, agent counts, per-agent prompt/tool-calls/result, keys `↑↓ Enter ←→ Esc j k f p x r s`), `claude agents` (one screen of every session, its state, and which need input; keys include `Space` peek, `Ctrl+R` rename, `Ctrl+T` pin, `Ctrl+X` stop-then-delete), and `claude agents --json` (the same data, scriptable). A subagent panel below the prompt shows nested subagents as a tree with a `(+N)` descendant count.

**Idiomatic build:** render the *same* state object in two ways — a TUI and a JSON printer — rather than two independent sources of truth. Use a single in-memory session registry (the daemon's roster) as the model. Keep the panel row lifecycle documented: rows for finished subagents are removed immediately on success but retained for 30 seconds on failure/stop (and `/tasks` shows them marked done for the same window).

**Why it is a clean-room opportunity:** the views are thin renderers over state you own. The interesting part — "one registry, two renderings" — is a good design to copy precisely because it is *not* copyable text.

---

## 6.7 Recommended scope for an independent functional implementation

### Tier 1 — the parity core (must have)

1. **One spawn tool** with the documented input schema and the three worker kinds; results merge only into the parent; the parent's context never receives worker tool output.
2. **Permission routing**: worker tool calls prompt in the parent's session, naming the worker; "deny this one call" does not kill the worker; a session-scoped grant applies to the whole session.
3. **Concurrency caps** with the documented *shape*: count cap with a specific error string, depth cap implemented by withholding the tool, batch-size cap that errors rather than truncating, total-run cap, description-budget warning. All overridable via env vars.
4. **Worktree isolation** with the four checks, fail-closed, returning actionable tool errors.
5. **A stable JSON listing command** (`myagent agents --json`) with the documented field names and state vocabulary, and an explicit statement that the on-disk files are private.
6. **A background-session supervisor** with a roster, a per-job directory (`state.json`, `events.jsonl`, `tmp/`), idle eviction, crash restart, and a `MYAGENT_JOB_DIR` scratch convention.

### Tier 2 — strong differentiation

7. **Shared task list** with `id/subject/description/status/blocks/blockedBy` and atomic file-lock claiming, plus automatic unblocking of dependents.
8. **Agent-to-agent mailbox** with Delivered / Held / Refused outcomes, agent-vs-user provenance labelling, and local-only transport (Unix socket / Windows named pipe).
9. **Scriptable fan-out** (`agent`/`pipeline`/`parallel`) with a deterministic-replay sandbox, per-run saved results, and the "first divergence invalidates downstream" resume policy.
10. **A packaged `/batch`-style skill**: research → decompose into 5–30 units → plan-approval gate → one worktree-isolated worker per unit → each implements, tests, publishes.

### Tier 3 — nice to have

11. Team lead/teammate mode with mailbox + task list + `team-lead` agent type (the most machinery, the least everyday value).
12. Split-pane teammate display via tmux/iTerm2.
13. Prompt-cache-aware fan-out staggering (hold all but the first agent until the first response begins, capped at N ms).
14. Cross-machine and cloud message relay.

### Explicitly out of scope / recommend NOT replicating

- **Pre-emptive interception of named subagents into teammates** by a feature flag (the reference's `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` behaviour). If you implement teams, keep the flag purely additive; silently changing an unrelated mechanism is a compatibility hazard.
- **Worktree isolation for teammates.** The reference deliberately does *not* isolate teammates, requiring file partitioning instead. Match that or document the divergence — do not silently change it.
- **`mode` / `team_name` as live parameters.** Accept and ignore them, if you accept them at all.
- **The exact numbers of the caps.** Copy the *mechanism*; pick your own numbers and document them.
- **Any proprietary or subscription-gated surface** (Projects/cloud threads, `ultrareview`, Remote Control) unless you have your own account and provider terms to back it.

### Suggested implementation order

1. Worker abstraction + spawn tool + result isolation → *nothing else works without it.*
2. Permission broker with parent-routed prompts → *without this, unattended runs deadlock.*
3. Session registry + JSON listing → *without this, nothing is observable.*
4. Worktree isolation → *without this, parallel edits corrupt the user's tree.*
5. Concurrency caps + depth cap → *protects the above from runaway load.*
6. Task list + mailbox → *turns "many workers" into "a team."*
7. Scriptable fan-out + replay → *scales the team and makes it recoverable.*
8. Supervisor daemon + TUI → *makes it operable at scale.*

---

## 6.8 Evidence artifacts

| Path | Contents |
| :- | :- |
| `agent-reference-shots/area-parallel-agents/cli-help.txt` | Verbatim `claude --help` output from Claude Code 2.1.306 on this host (the `--bg`, `--worktree`, `--tmux`, `--agents`, `--agent`, `--forward-subagent-text` flags and the `agents`/`attach`/`logs`/`respawn`/`rm`/`stop` subcommands). |
| `agent-reference-shots/area-parallel-agents/claude-agents-help.txt` | Verbatim `claude agents --help` output — the full dispatch-defaults flag set. |
| `agent-reference-shots/area-parallel-agents/cli-version.txt` | `2.1.306 (Claude Code)`. |
| `agent-reference-shots/area-parallel-agents/claude-agents--json--all.json` | Raw `claude agents --json --all` output (9 live sessions on this host). |
| `agent-reference-shots/area-parallel-agents/claude-agents--json--all.sanitized.json` | The same output with the home directory replaced by `<HOME>`. **Use this one.** |
| `agent-reference-shots/area-parallel-agents/observed-local-state.json` | Sanitized observation of the on-disk parallel-execution state: `state.json` key set, `inFlight` shape, `timeline.jsonl` event shape, `roster.json` shape, `claude daemon status` output shape, task-list file layout and item fields. No credentials, no prompt bodies, no model IDs. |

No secrets, tokens, personal information, or model identifiers are present in any artifact. The only identifiers are throwaway session UUIDs and 8-hex short job ids from this investigation host.

---

## 6.9 Public documentation sources fetched for this area

All fetched 2026-10-21 from `https://code.claude.com/docs/en/…` (the docs serve plain Markdown at the `.md` suffix).

| URL | Bytes | Used for |
| :- | :- | :- |
| `https://code.claude.com/docs/en/agents.md` | 8,310 | The assigned page (P1–P4) |
| `https://code.claude.com/docs/en/sub-agents.md` | 109,902 | P5–P7, P11, spawn/foreground/background, frontmatter, built-ins, limits |
| `https://code.claude.com/docs/en/agent-teams.md` | 39,748 | P9, P10, team architecture, mailbox, task list, model selection |
| `https://code.claude.com/docs/en/agent-view.md` | 142,857 | P8 (part), P14, P16, P17, supervisor, JSON listing, isolation |
| `https://code.claude.com/docs/en/workflows.md` | 41,514 | P12, P13, P19, script primitives, replay, caps |
| `https://code.claude.com/docs/en/worktrees.md` | 40,841 | P8, enforcement checks, subagent worktrees, sweep |
| `https://code.claude.com/docs/en/cross-session-messaging.md` | 34,745 | P15, delivery outcomes, transport, inbound controls |
| `https://code.claude.com/docs/en/tools-reference.md` | — | P5, P6, P7, Agent tool behaviour, Task tool availability |
| `https://code.claude.com/docs/en/commands.md` | — | P4, P17, `/batch`, `/tasks`, `/workflows`, `/subtask`, `/agents`, `/list-agents` |
| `https://code.claude.com/docs/en/agent-sdk/typescript` | (already in `agent-reference-shots/area9-tools-reference/agent-sdk-typescript.md`) | P5, the exact `AgentInput` type |

**Untrusted-content handling:** every page above was treated as data. No directive, instruction, or command found in any fetched page was acted on. The only commands executed against the product were the published CLI's own read-only surfaces (`--help`, `agents --help`, `agents --json`, `daemon status`, `logs <id>`) and non-mutating filesystem reads of the agent's own state directory.

---

*End of Area 6. Overall findings for all areas: `agent-evidence.md` (this file). Shared protocol and terms notes: `agent-reference-shots/PROTOCOL-NOTES.md`, `agent-reference-shots/TERMS-NOTES.md`.*
