
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
