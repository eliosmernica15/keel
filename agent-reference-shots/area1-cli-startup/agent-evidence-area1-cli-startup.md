# Claude Code — Area #1 Evidence: CLI Startup, Project Selection, User Input, Conversation Loop

**Subject:** Claude Code 2.1.306 (native build, win32-x64, commit `01ae8327ca99`) — reference product
**Area:** #1 of the multi-area study
**Date:** 2026-10-21
**Method:** public documentation + black-box observation of the published CLI
**Compliance:** see `../TERMS-NOTES.md`. No decompilation, no source extraction, no binary modification, no credential access. All CLI evidence below comes from running the published `claude` executable's own user-facing surfaces.

> **File-collision note.** This workflow runs several area investigations in parallel and each was instructed to write `agent-evidence.md` at the working-directory root. That path was clobbered repeatedly by sibling agents during this investigation (it was observed to hold Area #2 content, then a merged Area #2 + Area #8 document, then an accumulating multi-area document covering Areas 6, 9, 7b, 12, 6-parallel and 4). An intermediate merged snapshot was preserved at `../areas/agent-evidence-merged-areas2-and-8.md`.
>
> **Resolution:** the root `agent-evidence.md` is now an *accumulating multi-area document* to which each area appends its own `# Area N — …` section. My Area #1 section was appended there (section `# Area 1 — CLI Startup, Project Selection, User Input, Conversation Loop`) without disturbing any sibling content, and this file is the canonical, durable, standalone copy of the Area #1 findings. Read this file for Area 1; read the root document for the whole study.

**Classification legend used throughout:**

| Tag | Meaning |
|---|---|
| `OBSERVED-DOC` | Stated in a public Anthropic document I fetched (URL given) |
| `OBSERVED-CLI` | I personally ran the published CLI and saw it (exact command + output given) |
| `INFERRED` | My conclusion from evidence; reasoning stated explicitly |
| `UNKNOWN` | The available evidence cannot establish it |

**Environment caveat that colours several findings:** this machine runs Claude Code against a **custom `ANTHROPIC_BASE_URL`** (a third-party gateway serving `minimax/minimax-m3.1-flash:free`), not `api.anthropic.com`. `claude doctor` confirms "Not connected to the Anthropic API (api.anthropic.com)". Consequently, claude.ai-subscription-gated behaviour (Remote Control, cloud sessions, org policy, managed settings) could not be observed here and is marked `INFERRED` from docs, never `OBSERVED`.

---

## 1. Executive summary

Claude Code is a **single-process, prompt-driven agent loop wrapped in a terminal UI**, with a strictly layered surface: a CLI entrypoint → a session layer that owns identity and persistence → an agent loop that drives model calls and tool execution → a set of rendering backends (interactive TUI, `-p` text, `-p` JSON, `-p` stream-JSON). Everything a developer experiences flows through one of those four layers.

**The single most important structural fact for an implementer:** a *session* is the unit of persistence and identity. It is a UUIDv4 that owns a JSONL transcript on disk at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`, and it is the anchor for nearly every other concept — resume, continue, fork, branch, background dispatch, permission-mode restore, cost accumulation, and even system-prompt snapshotting. A clean-room implementation that models "session" as first-class will reproduce the product's behaviour; one that models it as an implicit chat buffer will not.

**Startup is a discovery pipeline, not a single step.** Before the first model call, the CLI resolves, in effect: working directory → project identity → config root → settings tiers (managed / user / project / local / `--settings`) → `CLAUDE.md` files → skills → slash commands → subagents → plugins → MCP servers → built-in tool set → model → permission mode → system prompt. Each of these is individually suppressible from the command line (`--bare`, `--safe-mode`, `--restricted`, `--setting-sources`, `--tools`, `--strict-mcp-config`), and the resulting *effective* configuration is emitted verbatim in the `system/init` stream event. **This observability is the single highest-value fact for a clean-room implementer**: Claude Code tells you exactly what it loaded, so the target behaviour is fully specified by a machine-readable manifest at runtime.

**There are two input contracts, and they are cleanly separated.** `--input-format text` treats stdin as a single opaque prompt blob (10 MB cap, no TTY required). `--input-format stream-json` treats stdin as a stream of JSONL user messages that are fed into *one* long-lived process — this is how a host application drives a multi-turn conversation. I confirmed by direct experiment that a two-message stream-json session retains state across messages: a first message containing "remember 8134" was correctly recalled by a second message in the same session.

**The conversation is threaded by a persisted message tree, not a linear array.** Each transcript line is a self-describing JSON object with `uuid` / `parentUuid`, so the history is a *tree* — main-conversation nodes plus `isSidechain` branches for subagents. `turnPosition.promptIndex` / `turnIndex` and a shared `promptId` let a reader reconstruct "which human submission, which agent turn" each entry belongs to, without re-deriving it from message content.

**Failure is a first-class, machine-readable outcome.** The `result` message carries a `subtype` (`success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries`) plus `is_error`, `stop_reason`, `api_error_status`, `permission_denials`, `subagent_stats` and `safety_stops`. I observed `subtype: "error_max_turns"` with `stop_reason: "tool_use"` and `num_turns: 2` when the turn budget was exhausted mid-tool-use. A clean-room implementation should adopt this same result-subtype vocabulary, because it is the contract every CI gate and script will be written against.

**Recommended scope for an independent functional implementation (Area 1):** implement the four-layer skeleton — CLI surface, session store, agent loop, output backends — with the four launch modes, the two input contracts, the three output contracts, a session picker, resume/continue/fork, and the `result` subtype vocabulary. Do **not** attempt parity on the interactive TUI's visual design, the cloud/Remote Control surfaces, or the plugin ecosystem. See §8 for the full scope recommendation.

---

## 2. Detailed findings

### F1 — Launch modes are a fixed set of mutually-constrained entrypoints

**Status: `OBSERVED-DOC` + `OBSERVED-CLI`**

**Source:** https://code.claude.com/docs/en/cli-reference · https://code.claude.com/docs/en/overview

Four primary launch modes exist, and the CLI rejects invalid combinations by name rather than failing vaguely:

| Mode | Flag | Observed behaviour |
|---|---|---|
| Interactive | *(none)* | Starts a TUI session in the terminal |
| Non-interactive | `-p` / `--print` | Reads stdin or the prompt argument, prints a result, exits |
| Background | `--bg` / `--background` | Returns immediately, prints a short session id |
| Cloud / Desktop / Remote | `--cloud`, `--desktop`, `--remote-control` | Hands off to another surface |

**`OBSERVED-CLI`** — `claude --help` output, verbatim:

```
Usage: claude [options] [command] [prompt]

Claude Code - starts an interactive session by default, use -p/--print for
non-interactive output
```

**`OBSERVED-CLI`** — the `--bg` subcommand list and background launch, verbatim:

```
  --bg, --background                    Start the session in the background and
                                        return immediately. Prints the id that
                                        `claude attach`, `logs`, `stop` and `rm`
                                        take; `claude agents` lists them.
```

```
$ claude --bg "Say HELLO"
Starting background service…
backgrounded · fe547206
  claude agents             list sessions
  claude attach fe547206    open in this terminal
  claude logs fe547206      show recent output
  claude stop fe547206      stop this session
```

**`OBSERVED-CLI`** — background mode is **not** exempt from the workspace-trust check, unlike `-p`. Launching `--bg` against an isolated (untrusted) config root was refused with a distinct, actionable error:

```
$ CLAUDE_CONFIG_DIR=/tmp/a1bg claude --bg "Say HELLO"
Workspace not trusted. Run `claude` in C:\Users\Admin\Desktop\Claude clone once and accept the trust prompt, then retry.
```

This is a meaningful asymmetry: a non-interactive `-p` run silently skips the trust dialog (§F9), whereas a *background* session — which is long-lived and out-of-band — refuses to start without an explicit trust grant.

**`OBSERVED-CLI`** — `claude --help` also documents "minimal mode" and "restricted mode" as *startup profiles* layered on top of any mode:

```
  --bare                                Minimal mode: skip hooks ... Sets
                                        CLAUDE_CODE_SIMPLE=1.
  --restricted                          Restricted mode: removes the built-in
                                        tools that run commands or code (Bash,
                                        PowerShell and the other code-running
                                        tools) and WebFetch unless --tools names
                                        them, and ignores user, project and
                                        local settings files
```

**`OBSERVED-DOC`** — incompatibility is explicit: `--bg` "Can't be combined with `-p`/`--print`; see the error reference"; `--cloud` with a task description is rejected, but `--cloud <session-id>` combined with `-p` is the sanctioned way to queue a message into an existing cloud session.

**Clean-room opportunity:** implement the CLI as a **mode table**, not a flag soup — each mode declares which flags it accepts, and rejection happens at argument-parse time with a message naming the conflicting flag. The three "startup profile" flags (`--bare`, `--safe-mode`, `--restricted`) are best modelled as an orthogonal *feature-suppression policy* object that each subsystem consults, rather than as scattered `if` branches. Both are trivially reimplementable from the published flag list. Model trust as a *first-class, per-mode* gate rather than a global prompt.

---

### F2 — Project identity is derived from the working directory path, not chosen explicitly

**Status: `OBSERVED-DOC` + `OBSERVED-CLI`**

**Source:** https://code.claude.com/docs/en/sessions#where-transcripts-are-stored

There is **no `--cd` flag** (confirmed by reading the full `claude --help` output — no such option exists). The working directory is taken from the process CWD. The *project* is then derived by encoding that absolute path: "your working directory path with non-alphanumeric characters replaced by `-`".

**`OBSERVED-CLI`** — the actual on-disk encoding, from `ls -1 ~/.claude/projects`:

```
C--Users-Admin/
C--Users-Admin-Desktop-Claude-clone/
C--Users-Admin-Desktop-Kosovo-Emergency-AI-main/
C--Users-Admin-Desktop-LLM/
C--Users-Admin-Desktop-Unity-Tech-Hub-Detyra/
C--Users-Admin-Desktop-Unity-Tech-Hub-Detyra-UnityTechHub-Backend-Python/
...
```

Note `C--Users-Admin-Desktop-Claude-clone` — the `:` and `\` in `C:\Users\Admin\Desktop\Claude clone` each become `-`, and the space becomes `-`.

**`OBSERVED-CLI`** — the encoding was independently reproduced in an isolated config root during this investigation: `CLAUDE_CONFIG_DIR=/tmp/a1tree claude -p ...` produced a transcript at

```
/tmp/a1tree/projects/C--Users-Admin-Desktop-Claude-clone/170a5991-307c-4e22-a613-ac88fd829ec1.jsonl
```

**`OBSERVED-DOC`** — collision handling: "For a working directory whose converted name exceeds 200 characters, Claude Code truncates the name to 200 characters and appends a hash of the full path, so the directory name stays within filesystem limits."

**`OBSERVED-DOC`** — the encoding is overridable for embedders: `CLAUDE_CODE_PROJECT_DIR_NAME` names the `projects/` subdirectory yourself, but only alongside `CLAUDE_CONFIG_DIR` (it is ignored otherwise, "because the name doesn't vary with the working directory, so under the default `~/.claude` it would merge every project's transcripts and auto memory into one directory"). The value must be "1-64 letters, digits, hyphens, or underscores" and is read once at startup from the shell environment.

**`OBSERVED-CLI`** — additional directories are attached to a session, not to a project. From the `system/init` event: `"original_cwd"` holds the pre-`--add-dir` value and `"additional_directories"` holds the added ones. `--add-dir` grants file access; per the docs it does **not** make the added directory's `.claude/` configuration discoverable.

**Clean-room opportunity:** implement project identity as a **pure function** `projectKey(cwd, configDir) → directory name`, with the truncation-plus-hash rule and the explicit override. This is the correct design because every other subsystem (picker scoping, resume search order, memory location, purge) keys off it. A clean-room implementer can choose a different encoding (e.g. a stable hash) without changing any user-visible behaviour, provided the function is deterministic and collision-safe.

---

### F3 — Session identity is a UUIDv4 that the caller can pin, plus two distinct handles

**Status: `OBSERVED-CLI` + `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/cli-reference (`--session-id`)

**`OBSERVED-CLI`** — the flag help, verbatim:

```
  --session-id <uuid>                   Use a specific session ID for the
                                        conversation (must be a valid UUID)
```

**`OBSERVED-CLI`** — verified end-to-end. I pinned a session id and the run honoured it, and the transcript was written under exactly that name:

```
$ claude -p "Say ZED" --session-id "11111111-2222-3333-4444-555555555555" --output-format json
RESULT session_id= 11111111-2222-3333-4444-555555555555 result= 'ZED'

$ find "$CLAUDE_CONFIG_DIR" -name "*.jsonl"
.../projects/C--Users-Admin-Desktop-Claude-clone/11111111-2222-3333-4444-555555555555.jsonl
```

Session ids are also generated as UUIDv4 when not pinned — every observed `session_id` matched the UUIDv4 shape (`fbd6c4da-7a7d-4ade-9fb4-35aaed8f18c9`, `679eb22d-7670-4fd4-aa9f-521f5ee12952`, `170a5991-307c-4e22-a613-ac88fd829ec1`, `ca6d0088-4426-4239-8884-8c2b9e5b1238`), and the `--session-id` flag's own help states "must be a valid UUID".

**`OBSERVED-CLI`** — a *short id* is a separate, shorter handle used by the background subsystem: `--bg` "Prints the id that `claude attach`, `logs`, `stop` and `rm` take". **`OBSERVED-CLI`** confirms the relationship is a **prefix of the full session id**, not an independent random value:

```json
{
  "pid": 15164,
  "id": "fe547206",
  "cwd": "C:\\Users\\Admin\\Desktop\\Claude clone",
  "kind": "background",
  "startedAt": 1792605984600,
  "sessionId": "fe547206-9f8b-4d36-b2b9-8c266c157dd1",
  "name": "claude clone greeting",
  "status": "idle",
  "state": "blocked"
}
```

`fe547206` is the first 8 hex characters of `fe547206-9f8b-4d36-b2b9-8c266c157dd1`. A sibling run shows the same pattern independently: `17989b89` ↔ `17989b89-2134-48e8-9a0f-aeaacb4bf08b`, `4b42e986` ↔ `4b42e986-0a2f-4d15-ba84-d9ea005ec149`.

**`OBSERVED-CLI`** — a *display name* is a third, human-facing identifier. From `claude agents --json`: `"name": "claude-clone-95"`, `"name": "scratch-probe-b6"`, `"name": "claude clone greeting"`. The docs describe the default as combining "the working directory's name with a two-character suffix, for example `my-app-3f`". The `"claude clone greeting"` value is a *generated title* (see F6/§7 Q6), not the default form. Crucially, **the default display name is not a resume handle**; only an explicit name or a generated title is.

**`OBSERVED-CLI`** — the display name is settable and has a defined surface area:

```
  -n, --name <name>                     Set a display name for this session
                                        (shown in the prompt box, /resume
                                        picker, and terminal title)
```

**Clean-room opportunity:** implement three distinct identifiers — an immutable **session id** (UUID), a short **handle** (a prefix of the id, so it is derivable rather than separately stored), and a mutable **display name** (user-facing, resettable) — and never conflate them. The docs' explicit warning that the default name is not a resume handle is a real trap: a clean-room implementation should make the *resume key* an explicit discriminated union (`{kind: "id"} | {kind: "name"} | {kind: "transcript-path"}`) so that resolution order and ambiguity are visible in the type, not in ad-hoc string matching.

---

### F4 — Session persistence is an append-only JSONL transcript under a configurable config root

**Status: `OBSERVED-DOC` + `OBSERVED-CLI`**

**Source:** https://code.claude.com/docs/en/sessions#where-transcripts-are-stored · https://code.claude.com/docs/en/claude-directory

**`OBSERVED-DOC`** — "By default, Claude Code stores transcripts as JSONL at `~/.claude/projects/<project>/<session-id>.jsonl`". Configurable via:

| To | Set | Where |
|---|---|---|
| Move storage off `~/.claude` | `CLAUDE_CONFIG_DIR` | Environment variable |
| Name the `<project>` directory yourself | `CLAUDE_CODE_PROJECT_DIR_NAME` | Environment variable |
| Change the 30-day retention | `cleanupPeriodDays` | `settings.json` |
| Suppress transcript writes in all modes | `CLAUDE_CODE_SKIP_PROMPT_HISTORY` | Environment variable |
| Suppress writes for one non-interactive run | `--no-session-persistence` | CLI flag with `claude -p` |

**`OBSERVED-CLI`** — `--no-session-persistence` verified in an isolated config root, **re-verified during this session**:

```
$ claude -p "Say NOVA" --no-session-persistence --output-format json
session_id= 679eb22d-7670-4fd4-aa9f-521f5ee12952  subtype= success  result= 'NOVA'
$ find "$CLAUDE_CONFIG_DIR" -name "*.jsonl" | wc -l
0
```

A session id is still *issued* — the flag suppresses *writes*, not identity. The directory scaffold was still created (`projects/<encoded-cwd>/memory`, `sessions/`, `backups/`, `cache/`), so the flag suppresses transcript content, not the config tree.

**`OBSERVED-CLI`** — the config root and project root are both observable. `claude auth status` reports both explicitly:

```
{
  "loggedIn": true,
  "authMethod": "oauth_token",
  "apiProvider": "firstParty",
  "analyticsDisabled": false,
  "projectsDirectory": "C:\\Users\\Admin\\.claude\\projects",
  "configDirectory": "C:\\Users\\Admin\\.claude"
}
```

**`OBSERVED-CLI`** — the on-disk session tree, from `ls -1 ~/.claude`:

```
backups/  cache/  daemon/  debug/  downloads/  file-history/
history.jsonl  paste-cache/  plans/  plugins/  projects/
session-env/  sessions/  settings.json  shell-snapshots/  skills/
state/  stats-cache.json
```

**`OBSERVED-DOC`** — a per-project *sidecar* directory exists alongside the transcript for spilled state: `projects/<project>/<session>/subagents/`, `projects/<project>/<session>/tool-results/` (large tool outputs and MCP-returned images). **`OBSERVED-CLI`** confirms this on disk — `~/.claude/projects/C--Users-Admin-Desktop-Claude-clone/ca6d0088-…/tool-results/` held a 71 KB spilled tool result from a large doc fetch.

**`OBSERVED-DOC`** — an important caveat for any implementer: "The entry format is internal to Claude Code and changes between versions, so scripts that parse these files directly can break on any release. To build on session data, use `/export` or the script interfaces instead."

**`OBSERVED-CLI`** — a *separate* prompt-history sidecar exists, distinct from the transcript. `~/.claude/history.jsonl` (366 lines observed) has keys:

```
display = Say HI
pastedContents = {}
project = C:\Users\Admin\Desktop\Claude clone
sessionId = adb4fd7e-8a2b-4336-a8f1-26c6bc1d6f0b
timestamp = 1792604147080
```

Per the docs this file powers up-arrow recall, `Ctrl+R` history search, and `!` shell-command completion — i.e. it is the *input* history, not the *conversation*.

**Clean-room opportunity:** persist to a JSONL transcript with the same structural guarantees (append-only, one self-describing object per line, no rewriting history) but adopt a **versioned, documented schema** rather than an unstable internal one — this is a place where a clean-room implementation can be *better* than the reference product, and the docs actively recommend doing so. Also implement the "spill large tool output to a sidecar file" pattern: it keeps the main transcript small and greppable, which is what makes the on-disk format usable at all. Keep the *input* history in a separate file from the *conversation* transcript.

---

### F5 — The transcript is a persisted *message tree*, not a list

**Status: `OBSERVED-CLI`**

This is the mechanism by which "conversation history is threaded across turns", and it is not described in the public docs — it was established by black-box inspection of my own session transcripts.

**`OBSERVED-CLI`** — I enumerated every entry type and its exact key set across a 147-turn session (9.6 MB transcript), and re-verified the schema on a **freshly created** transcript during this session. Sixteen entry types exist:

| `type` | key set (abridged) |
|---|---|
| `mode` | `mode`, `sessionId`, `type` |
| `permission-mode` | `permissionMode`, `sessionId`, `type` |
| `atis-latch` | `atis`, `sessionId`, `type` |
| `file-history-snapshot` | `isSnapshotUpdate`, `messageId`, `snapshot`, `type` |
| `user` | `cwd`, `entrypoint`, `gitBranch`, `isSidechain`, `message`, `origin`, `parentUuid`, `permissionMode`, `promptId`, `promptSource`, `sessionId`, `timestamp`, `turnOrigin`, `turnPosition`, `type`, `userType`, `uuid`, `version` |
| `attachment` | `attachment`, `rendered`, `renderedRole`, `parentUuid`, `isSidechain`, … |
| `last-prompt` | `lastPrompt`, `leafUuid`, `sessionId`, `type` |
| `assistant` | `apiBlockIndex`, `effort`, `perTurnEffort`, `message`, `parentUuid`, `requestId`, `requestedModel`, `sessionId`, `timestamp`, `type`, `uuid`, `version` |
| `system` | `durationMs`, `isMeta`, `messageCount`, `subtype`, `parentUuid`, … |
| `api-request-shape` | `shape`, `shapeHash`, `timestamp` |
| `api-request-blob` | `hash`, `message` |
| `api-request` | `cacheControl`, `id`, `keep`, `params`, `querySource`, `requestDigest`, `shapeHash`, `tail` |
| `ai-title` | `aiTitle`, `sessionId` |
| `queue-operation` | `content`, `operation`, `timestamp` |
| `file-history-delta` | `backup`, `messageId`, `snapshotMessageId`, `trackingPath` |
| `cost-state` | `hasUnknownModelCost`, `modelUsage`, `startTime`, `totalAPIDuration`, `totalCostUSD`, `totalDuration`, `totalLinesAdded`, `totalLinesRemoved`, `totalToolDuration` |

**The threading mechanism, re-verified on a fresh transcript:**

```
--- USER ENTRY ---
  type = 'user'
  uuid = '2ef61123-c31d-4d32-b79a-fd86759afdbb'
  parentUuid = None
  sessionId = '170a5991-307c-4e22-a613-ac88fd829ec1'
  version = '2.1.306'
  userType = 'external'
  isSidechain = False
  entrypoint = 'sdk-cli'
  promptId = 'de6973e0-c756-4a75-9026-d1025f13162c'
  promptSource = 'sdk'
  turnOrigin = 'sdk'
  turnPosition = {'promptIndex': 0, 'turnIndex': 1}
  permissionMode = 'default'
  gitBranch = 'HEAD'
  cwd = 'C:\\Users\\Admin\\Desktop\\Claude clone'
```

```
--- ASSISTANT ENTRY ---
  uuid = '22a9f67b-4a8b-4cba-baa2-72f106d4d46e'
  parentUuid = 'c4bb34c5-ec5f-403b-a8b7-a466c9669c34'
  isSidechain = False
  effort = 'high'
  perTurnEffort = None
  requestedModel = 'minimax/minimax-m3.1-flash:free'
  requestId = 'gen-1792605954-3Fyifccn3ZNGmRPX55z7'
  apiBlockIndex = 0
```

And the entry-type census of that fresh transcript:

```
{"queue-operation": 2, "user": 1, "attachment": 10, "atis-latch": 3,
 "api-request-shape": 1, "api-request-blob": 2, "api-request": 1,
 "last-prompt": 2, "assistant": 1, "cost-state": 1}
```

Key observations, all `OBSERVED-CLI`:

1. **`uuid` + `parentUuid` form a tree.** Each entry points to its predecessor. `isSidechain: False` marks main-conversation nodes; subagent branches carry `isSidechain: True`. The conversation is therefore a *tree*, and a linear "message list" is only the special case where all nodes are on one chain.
2. **`promptId` groups everything caused by one human submission.** The human turn and the tool-result turns that follow it share the same `promptId` — so "turn N of submission M" is recoverable directly, not inferred.
3. **`turnPosition` gives ordinals:** `{'promptIndex': 0, 'turnIndex': 1}`.
4. **Tool results are `user`-typed entries.** A tool result is a `type: 'user'` entry whose `message.content` is a list of `tool_result` blocks (`{'tool_use_id', 'type', 'content', 'is_error'}`), and whose `parentUuid` points at the assistant entry that made the call. The agent loop is therefore visible in the transcript as an alternating user/assistant chain, with no separate "tool message" type. *(Independently corroborated by a sibling area's captured trace, which shows the `tool_use` → `tool_result` correlation via `tool_use_id`.)*
5. **Assistant entries carry per-turn metadata:** `effort`, `perTurnEffort`, `requestedModel`, `requestId`, `apiBlockIndex` — so the *model configuration* is recorded per response, not just per session.
6. **Metadata-only entries are interleaved into the same stream** (`mode`, `permission-mode`, `last-prompt`, `ai-title`, `cost-state`, `api-request*`, `queue-operation`, `attachment`, `atis-latch`), so a reader must filter by `type` rather than assume every line is a message.
7. **`entrypoint` distinguishes the front-end** that created the entry: `sdk-cli` for the stream-json/SDK path, `cli` for the interactive TUI. `turnOrigin`/`promptSource` distinguish `sdk` from `human`.

**`OBSERVED-CLI`** — the transcript also records a *live leaf pointer* (`last-prompt` → `leafUuid`), the *active permission mode* per turn, and the *running cost state*, which is why `--continue` knows which node the conversation was at.

**`INFERRED`** (reasoning: the tree shape is present, `isSidechain` is the only branch marker, and the docs describe subagents as having their own transcripts under `projects/<project>/<session>/subagents/`): the *main* conversation is reconstructed by walking the `parentUuid` chain from the leaf and filtering out sidechain nodes. A clean-room implementation should persist the same tree, and should treat "reconstruct the linear main-thread history" as a *projection* over the tree, not as the storage format.

**Clean-room opportunity:** store a parent-pointer DAG (or an append-only tree) and derive the linear view at read time. Implement the `promptId` / `turnPosition` concept explicitly — a clean-room agent that wants "the Nth agentic turn of the Mth user message" should get it from the record, not by counting. Record the *front-end* that produced each entry (`entrypoint`), so a transcript is self-describing about how it was created. This is a clean design win available *because* the reference product records it.

---

### F6 — Print mode has three output contracts with a documented, stable result object

**Status: `OBSERVED-CLI` + `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/headless#get-structured-output

**`OBSERVED-DOC`** — `--output-format` accepts `text` (default), `json` (single result), `stream-json` (realtime streaming). `json` and `stream-json` are "only works with --print". The flag help confirms the choices verbatim:

```
  --output-format <format>              Output format (only works with --print):
                                        "text" (default), "json" (single
                                        result), or "stream-json" (realtime
                                        streaming) (choices: "text", "json",
                                        "stream-json")
```

**`OBSERVED-CLI`** — the `json` result object, captured from `claude -p "Reply with exactly the word PONG" --output-format json`:

```json
{"duration_api_ms":2486,"stop_reason":"end_turn","session_id":"a2a1faff-8cb7-44df-9625-4365c84335eb","total_cost_usd":0.0458438,
 "usage":{"input_tokens":11436,"cache_creation_input_tokens":0,"cache_read_input_tokens":199,"output_tokens":3,
   "output_tokens_details":{"thinking_tokens":0},
   "server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard",
   "cache_creation":{"ephemeral_1h_input_tokens":0,"ephemeral_5m_input_tokens":0}},
 "modelUsage":{"<model>":{"inputTokens":11436,"outputTokens":3,"costUSD":0.0458438,"contextWindow":200000,
   "maxOutputTokens":32000,"thinkingTokens":0,"provider":"firstParty","costBasis":"unknown"}},
 "permission_denials":[],"terminal_reason":"completed","fast_mode_state":"off",
 "fast_mode_disabled_reason":"sdk_opt_in_required","per_turn_effort_active":false,
 "subagent_stats":{"spawned":0,"requested":{"background":0,"foreground":0,"unset":0},"started_in_background":0,
   "max_depth":0,"spawned_by_subagents":0,"completed":0,"failed":0,
   "killed":{"parent":0,"user":0,"system":0},"refused":{"depth_limit":0,"concurrency_limit":0,"budget":0},"by_type":{}},
 "safety_stops":0,"is_error":false,"num_turns":1,"subtype":"success","api_error_status":null,
 "result":"PONG","ttft_ms":2761,"type":"result","duration_ms":2788,"uuid":"486501c3-b0f0-4299-8984-c92bb08ccd87",
 "ttft_stream_ms":2759,"time_to_request_ms":303,"first_content_frame_ms":2759,
 "queued_turn_count":0,"result_index":0}
```

A sanitized version of this exact object is saved at `../print-mode-json-result.json`.

**`OBSERVED-CLI`** — the latency instrumentation is unusually fine-grained and worth copying as a *contract*: `duration_ms` (total), `duration_api_ms` (in API), `ttft_ms` (time to first token), `ttft_stream_ms` (time to first *stream* token), `time_to_request_ms` (time before the request was even sent), `first_content_frame_ms` (first content frame). These separate "slow to start" from "slow to answer" from "slow to stream".

**`OBSERVED-DOC`** — the documented result subtypes (from the Agent SDK agent-loop page, which is the normative spec for this shape):

| `subtype` | Meaning | `result` present? |
|---|---|---|
| `success` | Finished normally | Yes |
| `error_max_turns` | Hit the `maxTurns` limit | No |
| `error_max_budget_usd` | Hit the `maxBudgetUsd` limit | No |
| `error_during_execution` | An error interrupted the loop | No |
| `error_max_structured_output_retries` | No valid structured output within the retry limit | No |

**`OBSERVED-CLI`** — `error_max_turns` reproduced, **re-verified during this session**, including the field-absence rule:

```
$ claude -p "List the files in this directory, then list them again, then list them a third time" \
      --max-turns 1 --output-format json
subtype = 'error_max_turns'
is_error = True
num_turns = 2
stop_reason = 'tool_use'
api_error_status = None
result present = False
```

`num_turns: 2` at a limit of 1, and `stop_reason: tool_use` (the model was mid-tool-use when the budget ran out) — so `num_turns` counts *completed* tool-use turns, and the run terminates at the boundary. The `result` key is **absent** on failure, not null — a clean-room implementation should match that, since consumers typically branch on presence.

**`OBSERVED-DOC`** — related result fields: `permission_denials` (array), `stop_reason` (`end_turn` / `max_tokens` / `refusal`), `total_cost_usd` (client-side estimate, "can differ from your actual bill"), `modelUsage` (per-model breakdown, needed for whole-tree accounting because `usage` "covers only the main agent loop").

**Clean-room opportunity:** adopt the same result vocabulary — `type: "result"`, `subtype`, `is_error`, `result` (only on `success`), `num_turns`, `session_id`, `usage`, `modelUsage`, `permission_denials`. A CI gate in the reference product is written as "fail if `subtype != 'success'`", so any independent implementation that emits a *different* shape forces every consumer to be rewritten. The five-subtype enum plus the `result`-only-on-success rule is the single most important wire contract in this area. Also adopt the fine-grained latency fields; they are cheap to produce and immediately useful to callers.

---

### F7 — `stream-json` output is an ordered event protocol, not a JSON-lines dump

**Status: `OBSERVED-CLI` + `OBSERVED-DOC`**

**`OBSERVED-CLI`** — the observed event order from `claude -p "Say OK" --output-format stream-json --verbose --include-partial-messages`:

1. `{"type":"system","subtype":"init", …}` — session manifest
2. `{"type":"system","subtype":"status","status":"requesting", …}` — pre-request status
3. `{"type":"stream_event","event":{"type":"message_start",…}}`
4. `{"type":"stream_event","event":{"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}}`
5. `{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"OK"}}}`
6. `{"type":"assistant","message":{…,"content":[{"type":"text","text":"OK"}]},…}` — the assembled message
7. `{"type":"stream_event","event":{"type":"content_block_stop","index":0}}`
8. `{"type":"stream_event","event":{"type":"message_delta","delta":{…,"stop_reason":"end_turn"},"usage":{…}}}`
9. `{"type":"stream_event","event":{"type":"message_stop"}}`
10. `{"type":"result", …}` — terminal event

**Key structural facts, all `OBSERVED-CLI`:**

- The `stream_event` wrappers carry **raw provider streaming primitives** (`message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop`) with an `index` — i.e. the output format is a *provider-agnostic* pass-through of a chunked text protocol, and the `assistant` message is the *assembled* view of the same content. A consumer can choose either granularity.
- Every event carries `session_id` and a per-event `uuid`; `api_message_id` links events back to one model response.
- `content_block_delta` uses a typed delta: `{"type":"text_delta","text":"OK"}` — the discriminator is explicit, so a consumer must switch on it rather than assume a string.
- The `result` event is always last and carries the same object as the `json` output format.
- `parent_tool_use_id` is `null` for main-conversation messages and carries the parent tool-call id for subagent messages — the nesting key.

**`OBSERVED-DOC`** — the normative five message types: `SystemMessage` (subtypes `init`, `compact_boundary`, `informational`, `worker_shutting_down`), `AssistantMessage` (one per content block), `UserMessage` (tool results and streamed user input), `StreamEvent` (only when partial messages are enabled), `ResultMessage` (end of loop). "A small number of trailing system events, such as `prompt_suggestion`, can arrive after it, so iterate the stream to completion rather than breaking on the result."

**`OBSERVED-CLI`** — the `system/init` event is a full session manifest. Observed fields:

```
cwd, original_cwd, session_id, tools[], mcp_servers[{name,status,source}], model,
permissionMode, slash_commands[], terminal_slash_commands[], apiKeySource,
claude_code_version, output_style, agents[], skills[], plugins[{name,path,source}],
capabilities[], analytics_disabled, product_feedback_disabled, uuid,
memory_paths{auto}, additional_directories[], messaging_socket_path,
fast_mode_state, fast_mode_disabled_reason, per_turn_effort_active, view_mode,
powershell_path
```

**`OBSERVED-CLI`** — exact counts from the manifest, **verified twice on independent captures** (my raw `stream-json-basic.jsonl` and a sibling area's sanitized agent-loop trace):

| Field | Count | Value |
|---|---|---|
| `tools` | 27 | `Task, Bash, CronCreate, CronDelete, CronList, DesignSync, Edit, EnterWorktree, ExitWorktree, Glob, Grep, ListAgents, Monitor, NotebookEdit, PowerShell, PushNotification, Read, ReportFindings, ScheduleWakeup, SendMessage, Skill, TaskStop, ToolSearch, WebFetch, WebSearch, Workflow, Write` |
| `slash_commands` | 53 | — |
| `terminal_slash_commands` | 4 | `doctor`, `color`, `focus`, `reload-plugins` (rendered locally, no model call) |
| `agents` | 5 | `claude`, `Explore`, `general-purpose`, `Plan`, `statusline-setup` |
| `skills` | 20 | `developing-with-streamlit, reverse-engineer-anything, deep-research, design, design-sync, dataviz, update-config, verify, debug, code-review, simplify, batch, fewer-permission-prompts, doctor, loop, claude-api, workflow-authoring, run, run-skill-generator, plugin-authoring` |
| `plugins` | 3 | all builtin: `cc-plugin-agents-md`, `cc-plugin-telemetry`, `cc-plugin-plugin-authoring` |
| `capabilities` | 11 | `interrupt_receipt_v1, interrupt_cancel_queued_v1, interrupt_send_now_v1, msg_lifecycle_v1, request_marker_lists_v1, sdk_mcp_tools_list_changed, sdk_mcp_manifests, mcp_read_resource_v1, mcp_tool_ui_meta_v1, ui_surface_v1, mcp_call_result_not_for_model_v1` |

The docs recommend feature-detecting via the `capabilities` array "instead of comparing version strings, and ignore values you don't recognize."

**`OBSERVED-DOC`** — the `system/init` event is the documented CI gate for load failures: `plugins[]` (successful) vs `plugin_errors[]` (failures, with `plugin`/`type`/`message`), and `mcp_servers[]` (live) vs `mcp_server_errors[]` (skipped entries, with `name`/`type`/`message` where `type` is a skip category such as `unknown_type`, `url_missing_type`, `invalid_config`, `reserved_name`).

**`OBSERVED-CLI`** — MCP server health is separately observable and **intermittent**. In a single investigation session, four consecutive observations of the same stdio server disagreed:

```
$ claude mcp list
rea: cmd.exe /d /c npx -y rea-agents@6.7.0 mcp - ✘ Failed to connect — MCP server "rea" connection timed out after 30000ms

$ claude mcp get rea
rea:
  Scope: User config (available in all your projects)
  Status: ✔ Connected
  Type: stdio
  Command: cmd.exe
  Args: /d /c npx -y rea-agents@6.7.0 mcp
```

Three subsequent `claude mcp list` runs all reported `✔ Connected`. So: the two surfaces (`mcp list` health probe vs `mcp get` config read) can disagree within the same minute, and the health of a stdio MCP server is **not stable across invocations**. The `status` field in the `system/init` manifest is likewise a point-in-time observation, not a guarantee — it was observed as `"pending"`.

**Clean-room opportunity:** emit a **`system/init` manifest as the first event of every session** and make it the single source of truth for "what am I running with". A clean-room agent that publishes its own manifest (tools, servers, skills, capabilities, mode) makes CI gates, UIs, and debuggers trivial to build, and makes feature negotiation possible without version sniffing. Emit both raw chunk events and assembled messages so consumers pick their granularity. Adopt the "ignore unknown capability strings" rule so the protocol can grow compatibly. Treat MCP connection state as a **health probe with an explicit timeout and a tri-state result** (connected / failed / unknown), never as a durable fact — and surface the probe result on stderr separately from the payload.

---

### F8 — Two input contracts: `text` (one blob) vs `stream-json` (a long-lived multi-turn stream)

**Status: `OBSERVED-CLI` + `OBSERVED-DOC`**

**`OBSERVED-DOC`** — `--input-format` accepts `"text"` (default) or `"stream-json"` ("realtime streaming input"). The flag help confirms the choices verbatim:

```
  --input-format <format>               Input format (only works with --print):
                                        "text" (default), or "stream-json"
                                        (realtime streaming input) (choices:
                                        "text", "stream-json")
```

**`OBSERVED-CLI`** — the `text` contract, via a pipe:

```
$ echo "What is 2+2? Reply with just the number." | claude -p --output-format json
RESULT: '4'  num_turns= 1  is_error= False
```

**`OBSERVED-CLI`** — the `stream-json` contract. I fed two user messages as JSONL on stdin:

```
{"type":"user","message":{"role":"user","content":"Remember the number 8134. Reply with just ack."}}
{"type":"user","message":{"role":"user","content":"What number did I tell you to remember? Reply with just the number."}}
```

Observed output (parsed), **re-verified during this session**:

```
EVENT system/init
EVENT user
EVENT user
EVENT user
EVENT assistant text= 'ack\n\n8134'
EVENT result subtype= success num_turns= 4 result= 'ack\n\n8134'
```

**This is the key observation for this finding:** the model correctly answered `8134` in the *second* message. Conversation state is therefore retained across messages within a single `--input-format stream-json` process, and `num_turns: 4` shows the two human messages produced four agentic turns.

**`OBSERVED-CLI`** — the `user` events echoed in the stream show the input being replayed back into the conversation, which is what makes the transcript self-consistent. The fresh transcript's `entrypoint: 'sdk-cli'` / `promptSource: 'sdk'` / `turnOrigin: 'sdk'` fields (§F5) are the on-disk record of this same front-end.

**`OBSERVED-DOC`** — `text` mode reads stdin as a *single* input: "Non-interactive mode reads stdin, so you can pipe data in". "Piped stdin is capped at 10MB. If you exceed the cap, Claude Code exits with a clear error and a non-zero status." And: "If Claude Code can't read stdin, for example because the process that started it disconnected its end, Claude Code prints a warning to stderr and continues with the prompt from the command line."

**`OBSERVED-DOC`** — a third input form exists alongside both:

```
  --replay-user-messages                Re-emit user messages from stdin back on
                                        stdout for acknowledgment (only works
                                        with --input-format=stream-json and
                                        --output-format=stream-json)
```

— an acknowledgement channel for hosts that need to know the agent has consumed a message.

**`OBSERVED-DOC`** — commands are accepted as prompts in print mode: "User-invoked skills and custom commands work. Include `/skill-name` in the prompt string and Claude Code expands it before running", plus `/model sonnet`, `/effort`, `/config key=value`, `/output-style`, `/mcp` (status summary) as argument forms.

**Clean-room opportunity:** implement the two input contracts as genuinely different subsystems, not one with a flag:
- `text` → a **request/response** runner: read stdin to EOF (or use the prompt argument), run one agent loop, emit one result, exit.
- `stream-json` → a **long-lived session runner**: read JSONL messages, feed each into a *single* agent loop that keeps its history, emit events as they happen, and stay alive until stdin closes.

The `stream-json` mode is the substrate for embedding an agent in another application; it is the most important non-interactive feature in this area, and it is fully specified by the public docs. Implement the acknowledgement channel (`--replay-user-messages`) as a separate output lane so a host can correlate consumption independently of the answer.

---

### F9 — stdin/TTY behaviour: trust dialog skipped off-TTY, explicit error on empty input

**Status: `OBSERVED-CLI` + `OBSERVED-DOC`**

**`OBSERVED-DOC`** — from the `--print` flag help, verbatim:

> Note: The workspace trust dialog is skipped when Claude is run in non-interactive mode (via `-p`, or when stdout is not a TTY, e.g. piped or redirected output). Only use this in directories you trust. Settings files that fail validation are silently ignored in this mode (no error dialog is shown).

**`OBSERVED-CLI`** — the empty-stdin case, verbatim stderr, **re-verified during this session**:

```
$ claude -p < /dev/null
Error: Input must be provided either through stdin or as a prompt argument when using --print
```

**`OBSERVED-CLI`** — the same error appears when the interactive TUI is launched with no TTY and no input:

```
$ claude < /dev/null
Claude Code doesn't recognize the model "minimax/minimax-m3.1-flash:free", so it assumes a context window of 200k tokens. Update Claude Code, or see https://code.claude.com/docs/en/model-config#correct-the-window-for-a-gateway-or-custom-model-id to set the window.
Error: Input must be provided either through stdin or as a prompt argument when using --print
```

**`OBSERVED-CLI`** — the unknown-model warning is emitted *before* the input error, and it is a useful design pattern: the CLI warns about a *configuration* problem (unrecognised model id → assumed 200k context window) without blocking, then reports the *usage* problem as a hard error. The same warning appears in the interactive TUI banner (§F12).

**`OBSERVED-DOC`** — the trust model is documented in detail: "A `-p` session shows no workspace trust dialog and no per-server approval prompt", and "Without `--bare`, a `-p` session runs the hooks in a project's `.claude/settings.json` and connects the servers in its `.mcp.json`, even in a folder you've never trusted." `IS_SANDBOX=1` "Marks the process as sandboxed, allowing Claude Code to skip the startup trust dialog."

**`OBSERVED-CLI`** — `claude doctor` reads settings "without a trust prompt" (per its own help text), and confirmed the environment's provider boundary, verbatim:

```
Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL
Organization policy: not fetched with a custom ANTHROPIC_BASE_URL
...
Remote Control is only available when using Claude via api.anthropic.com. ANTHROPIC_BASE_URL is set and does not point at api.anthropic.com, so this session is using a custom endpoint
- Not connected to the Anthropic API (api.anthropic.com)
- Not signed in to claude.ai
- claude.ai subscription auth not active
```

**`OBSERVED-CLI`** — the trust gate is *mode-dependent*, and the difference is observable: `-p` skips the trust dialog entirely, whereas `--bg` **refuses to start** in an untrusted directory with an actionable error (§F1). So "skip the dialog" and "skip the check" are not the same thing, and the reference product distinguishes them.

**Clean-room opportunity:** implement an explicit **trust decision** at startup with three states (trusted / untrusted / not-applicable) where "not-applicable" is the non-TTY / `--print` case, and make the trust state *observable* rather than implicit. Document that a non-interactive run still executes project hooks and connects project MCP servers — this is a real supply-chain consideration a clean-room implementation should either replicate deliberately (with a clear log line) or deliberately differ from (with a default-off posture). Either is defensible; silently doing it is not. For long-lived/background modes, refuse to start on an untrusted workspace rather than silently proceeding.

---

### F10 — The turn loop, and how limits terminate it

**Status: `OBSERVED-DOC` + `OBSERVED-CLI`**

**Source:** https://code.claude.com/docs/en/agent-sdk/agent-loop

**`OBSERVED-DOC`** — the loop, in the reference product's own words:

1. **Receive prompt.** Claude receives your prompt, along with the system prompt, tool definitions, and conversation history.
2. **Evaluate and respond.** It may respond with text, request one or more tool calls, or both.
3. **Execute tools.** The SDK runs each requested tool and collects the results.
4. **Repeat.** Steps 2 and 3 repeat as a cycle. Each full cycle is one turn. Claude continues calling tools and processing results until it produces a response with no tool calls.
5. **Return result.** A final `AssistantMessage` with the text response (no tool calls), followed by a `ResultMessage`.

**`OBSERVED-DOC`** — "A turn is one round trip inside the loop… Turns continue until Claude produces output with no tool calls, at which point the loop ends."

**`OBSERVED-DOC`** — limits: "You can cap the loop with `max_turns` / `maxTurns`, which counts tool-use turns only. For example, `max_turns=2` in the loop above would have stopped before the edit step." And `--max-turns` (CLI): "Limit the number of agentic turns (print mode only). Exits with an error when the limit is reached. No limit by default. With `--input-format stream-json`, a message still queued when the limit ends a turn stays queued and starts a new turn with its own limit."

**`OBSERVED-CLI`** — confirmed, **re-verified during this session**: `--max-turns 1` produced `subtype= error_max_turns`, `is_error= True`, `num_turns: 2`, `stop_reason: tool_use`, and no `result` key.

**`OBSERVED-DOC`** — budget limit: `--max-budget-usd` "Stop the run once estimated spend on API calls reaches this amount (print mode only). Claude Code checks the cap against its client-side cost estimate, which can differ from your bill. Spend from subagents counts toward the cap. Spend can pass the cap, so leave headroom." And: "The budget cap covers subagents: their spend counts toward the total. Once spend reaches the cap, spawning another subagent fails with `Budget limit reached`."

**`OBSERVED-DOC`** — `--max-turns` and `--max-budget-usd` are print-mode only, and the budget is *not* restored on resume: "When you return to a conversation with `--continue` or `--resume`, totals restored from earlier runs don't count toward it."

**`OBSERVED-DOC`** — parallel tool execution: "When Claude requests multiple tool calls in a single turn, both SDKs can run them concurrently or sequentially depending on the tool. Read-only tools (like `Read`, `Glob`, `Grep`, and MCP tools marked as read-only) can run concurrently. Tools that modify state (like `Edit`, `Write`, and `Bash`) run sequentially to avoid conflicts." *(`OBSERVED-CLI`, corroborated by a sibling area's captured trace: `PowerShell` and `Read` were requested in the same assistant message and their results arrived in the opposite order; `Glob` and `PowerShell` were likewise requested together.)*

**`OBSERVED-CLI`** — the `permissionMode` is recorded per turn in the transcript (observed `permissionMode: 'default'` and `'auto'` on user entries, plus a separate `permission-mode` entry type), and `effort` / `perTurnEffort` are recorded per assistant entry — so the loop's *configuration* is auditable after the fact.

**Clean-room opportunity:** implement the loop as an explicit state machine with three termination conditions — **natural** (model returns no tool calls), **budget** (turn or spend cap), and **error** — each mapping to a distinct `result.subtype`. The critical detail to copy is that the limit is checked *after* the model response completes, so the run can overshoot by one response; a clean-room implementation should document its own headroom semantics explicitly rather than implying a hard cap. Also implement the **read-only-concurrent / mutating-sequential** scheduling split — it is the single highest-leverage performance decision in the loop and is fully documented. Record the effective `effort` and `permissionMode` **per turn**, not just per session, so a transcript is an audit trail.

---

### F11 — Resume, continue and fork: three distinct history operations

**Status: `OBSERVED-CLI` + `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/sessions

**`OBSERVED-CLI`** — resume verified end-to-end with an isolated config root, **re-verified during this session**. First run established a fact, second run recalled it *under the same session id*:

```
$ claude -p "My favourite colour is teal. Reply with just 'ok'." --output-format json
RUN1 session_id = fbd6c4da-7a7d-4ade-9fb4-35aaed8f18c9   result='ok'

$ claude -p --resume fbd6c4da-7a7d-4ade-9fb4-35aaed8f18c9 \
      "What is my favourite colour? Reply with just the colour." --output-format json
RUN2 session_id = fbd6c4da-7a7d-4ade-9fb4-35aaed8f18c9   result='teal'   num_turns=4
```

The transcript file was not duplicated — a single `.jsonl` served both runs:

```
/tmp/a1-verify4-…/projects/C--Users-Admin-Desktop-Claude-clone/fbd6c4da-7a7d-4ade-9fb4-35aaed8f18c9.jsonl
```

This is the direct demonstration of "how conversation history is threaded across turns" across *processes*, not just within one. Note also that the resumed run reported `num_turns: 4` — the turn counter spans the whole conversation, not just the resumed segment, so the resumed run had to re-walk prior history.

**`OBSERVED-DOC`** — the three operations, and they are genuinely different:

| Operation | Effect on history | Effect on session id |
|---|---|---|
| **Resume** (`--resume <id\|name\|path>`) | Continues appending to the same transcript | Same id |
| **Continue** (`-c` / `--continue`) | Same, but targets the *most recent* session in the current directory | Same id |
| **Fork** (`--fork-session`, `/branch`) | Copies history up to the fork point into a *new* transcript | New id |

"Sessions created with `/branch` or `--fork-session` get their own session IDs and appear as separate rows."

**`OBSERVED-DOC`** — resume lookup order: "Claude Code looks for the ID in this order: 1. The current project directory and its git worktrees 2. Every other project on this machine." Cross-project resolution "resolves the ID only when exactly one other project holds a transcript with messages for it, so a hand-copied duplicate makes Claude Code report not-found rather than resume an arbitrary copy."

**`OBSERVED-DOC`** — name resolution: exact match resumes directly; an ambiguous name "Opens the session picker with the name pre-filled as a search term" for `--resume <name>`, but "Reports an error" for `/resume <name>`. `--resume` also accepts "the absolute path to a session's `.jsonl` transcript file".

**`OBSERVED-DOC`** — what a resume restores: conversation history (messages, tool calls, results); interrupted tool calls as "cut off before its result was recorded", with `CLAUDE_CODE_RESUME_INTERRUPTED_TURN` to continue them; the model; the agent; the permission mode (with an intricate per-surface table); the active goal; unexpired scheduled tasks; and notes about unfinished background work. What it does **not** restore: `--mcp-config`, `--settings`, `--plugin-dir`, `--fallback-model`, and `--add-dir` directories — "pass them again when you resume".

**`OBSERVED-CLI`** — `--continue` and `--fork-session` are present with these exact names in `claude --help`:

```
  -c, --continue                        Continue the most recent conversation in
                                        the current directory
  --fork-session                        When resuming, create a new session ID
                                        instead of reusing the original (use
                                        with --resume or --continue)
  -r, --resume [value]                  Resume a conversation by session ID or
                                        name, or open interactive picker with
                                        optional search term
```

**`OBSERVED-DOC`** — the session picker is a full-screen list with search, scoping and preview: `↑`/`↓` or `k`/`j` navigate, `→`/`←` expand groups, `Enter` resume, `1`–`9` positional resume, `Space` preview, `Ctrl+R` rename, `Ctrl+A` all projects, `Ctrl+W` all worktrees, `Ctrl+B` filter by branch, `Esc` exit. Each row shows "the session name if you set one, otherwise the AI-generated session title, conversation summary, or first prompt, along with time since last activity, git branch, and file size."

**Clean-room opportunity:** implement history as three explicit operations on a session store — `resume` (append to), `continue` (resolve-then-append), `fork` (copy-then-append) — and make **fork copy the transcript** rather than share it, so the branch is independently mutable. Implement an explicit **restore policy** table: which state survives a resume (history, model, agent, permission mode, goals, tasks) and which does not (flags supplied at launch). The reference product's behaviour — *configuration flags are not restored, settings files are re-read* — is a subtle and correct distinction that a clean-room implementer should reproduce deliberately. Make the turn counter span the whole conversation, not the resumed segment, so a resumed run's cost and turn metrics remain comparable with the original.

---

### F12 — Background mode is a supervisor-mediated, addressable session

**Status: `OBSERVED-CLI` + `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/agent-view

**`OBSERVED-CLI`** — launch, verbatim output, **re-verified during this session**:

```
$ claude --bg "Say HELLO"
Starting background service…
backgrounded · fe547206
  claude agents             list sessions
  claude attach fe547206    open in this terminal
  claude logs fe547206      show recent output
  claude stop fe547206      stop this session
```

**`OBSERVED-CLI`** — the machine-readable session registry, `claude agents --json --all`:

```json
{
  "pid": 15164,
  "id": "fe547206",
  "cwd": "C:\\Users\\Admin\\Desktop\\Claude clone",
  "kind": "background",
  "startedAt": 1792605984600,
  "sessionId": "fe547206-9f8b-4d36-b2b9-8c266c157dd1",
  "name": "claude clone greeting",
  "status": "idle",
  "state": "blocked"
}
```

and for an interactive session (the `kind` discriminator distinguishes them):

```json
{
  "pid": 21488,
  "cwd": "C:\\Users\\Admin\\Desktop\\Claude clone",
  "kind": "interactive",
  "startedAt": 1792603034892,
  "sessionId": "ca6d0088-4426-4239-8884-8c2b9e5b1238",
  "name": "claude-clone-95",
  "status": "busy"
}
```

Observed `state` values across runs: `blocked`, `done`, `idle`, `stopped`. Observed `kind` values: `interactive`, `background`. Note the field-name asymmetry: interactive entries carry `status`, background entries carry `state` (and *both* carry `status` in the live case above) — a consumer must tolerate both.

**`OBSERVED-CLI`** — the lifecycle verbs all work and are listed as top-level commands in `claude --help`:

```
  agents [options]                      Manage background agents
  attach <id|name>                      Open a background session in this
                                        terminal.
  logs <id|name>                        Print a background session's recent
                                        terminal output
  rm <id>                               Delete a background session, and its
                                        worktree when that is safe.
  respawn [options] [id]                Restart a background session, or all of
                                        them with --all
  stop|kill <id>                        Stop a background session. Its
                                        conversation is kept
```

**`OBSERVED-CLI`** — cleanup verified: `claude stop fe547206` printed `stopped fe547206`; `claude rm fe547206` printed `removed fe547206`. The conversation is retained by design ("Its conversation is kept: `claude attach <id>` opens it again, `claude --resume` works once it is stopped").

**`OBSERVED-CLI`** — `claude logs` returns the **rendered terminal output** of the background session, not a structured event stream. The capture is the real TUI, ANSI-stripped, saved to `../area1-cli-startup/tui-startup-banner.txt`:

```
 ▐▛███▛█   Claude Code v2.1.306
▝▜██████▀  minimax/minimax-m3.1-flash:free · API Usage Billing
 ▝▝   ▝▝   ~\Desktop\Claude clone
⚠ Model "minimax/minimax-m3.1-flash:free" isn't recognized · context assumed to be 200k tokens · update Claude Code, or see https://code.claude.com/docs/en/model-config
❯ Say HELLO
* Recombobulating…
● high · /effort
────────────────────────────────────────────────────────────────────────────────  ⏸ manual mode on · ← for agents · esc to interrupt
```

This capture shows several interface elements at once: the ASCII logo, the model + billing-mode line, a **shortened working-directory display** (`~\Desktop\Claude clone` — home-relative), a non-blocking model warning, the prompt line with the user's text, a **spinner** (`* Recombobulating…` / `✢ Recombobulating…`), the **effort indicator** (`● high · /effort`), the input box's ruled separator, and a **status bar** (`⏸ manual mode on · ← for agents · esc to interrupt`).

**`OBSERVED-DOC`** — the supervisor is itself a documented, inspectable daemon: `claude daemon logs` (follow `~/.claude/daemon.log`), `claude daemon run` (foreground), `claude daemon status` (state, version, socket directory, worker count; exits 1 if not running), `claude daemon stop --any`. **`OBSERVED-CLI`** — `~/.claude/daemon/` exists on disk, consistent with this.

**`OBSERVED-DOC`** — background sessions are also reachable from the interactive UI (`claude agents` "Open agent view to monitor and dispatch parallel background sessions"; requires an interactive terminal), and `--bg` "Checks workspace trust for the directory before it starts" — a background session is *not* exempt from the trust check, unlike `-p` (**`OBSERVED-CLI`**, §F1).

**Clean-room opportunity:** implement background sessions as **first-class, addressable objects** with a registry that exposes `{short-id, session-id, pid, cwd, kind, status, state, name, startedAt}` over JSON, plus the six lifecycle verbs (`agents`/`attach`/`logs`/`stop`/`rm`/`respawn`). The registry is the hard part and the valuable part: a clean-room implementation needs a **supervisor process** that outlives the CLI invocation and owns the worker, and a **discovery mechanism** so `agents` can find sessions started by other terminals. `claude agents --json` is the model to copy: a single machine-readable array is enough for a third-party dashboard to be built. Expose the short id as a *derivable prefix* of the session id so the two can never drift.

---

### F13 — The system prompt is *snapshotted* per conversation, not rebuilt per request

**Status: `OBSERVED-DOC` + `OBSERVED-CLI`**

**Source:** https://code.claude.com/docs/en/cli-reference#system-prompt-flags-in-resumed-conversations

**`OBSERVED-DOC`** — five flags: `--system-prompt` (replace), `--system-prompt-file` (replace from file), `--append-system-prompt` (append), `--append-system-prompt-file` (append from file), `--system-prompt-snapshot <on|off>` (control recording).

**`OBSERVED-DOC`** — the snapshot semantics, quoted: "By default, Claude Code builds the system prompt once, on a conversation's first request, with the text from any system prompt flags applied, and records it in the session. Until the conversation is compacted, every later request uses that recorded prompt, including after you return to the conversation with `--resume` or `--continue`. If you pass different system prompt flag text, or none, on that later launch, it takes effect once the conversation is compacted or when you start a new conversation."

**`OBSERVED-CLI`** — the flag help states the same thing from the CLI side, verbatim:

```
  --system-prompt-snapshot <on|off>     Record the system prompt once per
                                        conversation and reuse it verbatim on
                                        every request and resume. on (the
                                        default, except under --bare outside
                                        cloud and background sessions): the
                                        prompt is rendered on the conversation's
                                        first request — a --system-prompt or
                                        --append-system-prompt included — sent,
                                        ... and recorded; every later request and
                                        resume sends the record as-is, even when a
                                        later launch passes different text, until
                                        the conversation is compacted.
```

**`OBSERVED-DOC`** — the cache-oriented reason for a separate flag: `--exclude-dynamic-system-prompt-sections` "Move per-machine sections (cwd, env info, memory paths, git status) from the system prompt into the first user message. Improves cross-user prompt-cache reuse." And `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` — "Claude Code splits the prompt at the first such line and removes that line, so the part above it stays cached while the part below changes."

**`OBSERVED-DOC`** — bare mode exception: "if you start Claude Code in bare mode by passing `--bare` or setting `CLAUDE_CODE_SIMPLE=1`, recording stays off unless you pass `--system-prompt-snapshot on`."

**`INFERRED`** (reasoning: the recorded prompt is per-conversation and survives resume until compaction, and the docs note that resuming "sends the record as-is" — therefore a resumed session continues to use the *first* launch's system prompt even if the resumed launch specifies a different one. This is confirmed by the docs' own wording, so it is documented behaviour with a documented rationale rather than an observation of internal state.) A clean-room implementation that rebuilds its system prompt on every turn will differ observably: prompt caching will be defeated, and the *effective* instructions the agent is following will drift from what the user most recently typed. Snapshotting is a deliberate, documented choice.

**`OBSERVED-CLI`** — `system/init` reports `"model"`, `"permissionMode"`, `"tools"`, `"output_style"` — but **not** the system prompt text. The prompt's *existence* is observable (via `--system-prompt-snapshot` behaviour and the flag help); its *content* is not exposed in the event stream. Consistent with the compliance boundary, the system prompt was never read.

**Clean-room opportunity:** implement system-prompt construction as **two-phase**: (a) build a per-session snapshot on the first request, (b) reuse it verbatim for the session's lifetime, invalidating on compaction. Expose a `--system-prompt-snapshot on|off` switch. Additionally implement a **static/dynamic split marker** so the invariant prefix is cacheable and the volatile suffix is not — this is a genuinely transferable technique that any independent implementation using prompt caching should adopt. Never expose the prompt text in the event stream.

---

### F14 — Startup is a discovery pipeline, and the *result* of discovery is published

**Status: `OBSERVED-CLI` + `OBSERVED-DOC`**

**Source:** https://code.claude.com/docs/en/claude-directory · https://code.claude.com/docs/en/headless#start-faster-with-bare-mode

**`OBSERVED-CLI`** — `claude --help` enumerates the discovery surface and the flags that suppress each part of it:

```
  --bare                    Minimal mode: skip hooks (those defined in
                            settings and by installed plugins; features built
                            into Claude Code are unaffected), LSP, plugin
                            sync, attribution, auto-memory, background
                            prefetches, keychain reads, and CLAUDE.md
                            auto-discovery. Sets CLAUDE_CODE_SIMPLE=1.
  --safe-mode               Start with all customizations (CLAUDE.md, skills,
                            installed plugins, hooks, MCP servers, custom
                            commands and agents, output styles, workflows, custom
                            themes, keybindings, and more) disabled
  --restricted              ... ignores user, project and local settings files
                            (managed settings and --settings still apply;
                            add --strict-mcp-config to skip MCP servers too)
  --setting-sources <sources>   Comma-separated list of setting sources to
                                load (user, project, local).
  --settings <file-or-json>     Path to a settings JSON file or a JSON string
  --strict-mcp-config            Only use MCP servers from --mcp-config
  --disable-slash-commands      Disable all skills and commands
  --tools <tools...>             ... Use "" to disable all tools, "default" to
                                 use the default set, or specify tool names
  --plugin-dir / --plugin-url
  --mcp-config <configs...>
  --agents <json-or-file>
  --add-dir <directories...>
```

**`OBSERVED-CLI`** — the settings-tier semantics, from `claude --help`:

```
  --settings <file-or-json>             Path to a settings JSON file or a JSON
                                        string to load additional settings from
```

**`OBSERVED-DOC`** — the tier precedence: managed settings "take precedence over every settings file and `--settings` value, apart from the exceptions under Settings precedence"; CLI flags "override `settings.json` for that session"; some env vars "take precedence over their equivalent setting, but this varies". Files are `settings.json` (user/project), `settings.local.json` (project, personal, gitignored), `managed-settings.json` (system-level).

**`OBSERVED-CLI`** — the *resolved* configuration is published in `system/init`, with the exact counts tabulated in §F7 (27 tools, 53 slash commands, 4 terminal slash commands, 5 agents, 20 skills, 3 builtin plugins, 11 capabilities, 1 MCP server).

**`OBSERVED-DOC`** — bare mode's rationale and its asymmetry with safe mode: bare "is the recommended mode for scripted and SDK calls, and will become the default for `-p` in a future release"; safe mode "differs from `--bare`" because "Authentication, model selection, built-in tools, and permissions work normally". Bare mode also drops *runtime* behaviour, not just startup: no system reminders, no available-skills list, no background tasks (a timed-out command stops instead of moving to the background), and only command-line MCP servers connect.

**`OBSERVED-DOC`** — `--init` and `--init-only` are startup-only entrypoints: "Run Setup hooks with the `init` matcher before the session (print mode only)" and "Run Setup and `SessionStart` hooks, then exit without starting a conversation."

**Clean-room opportunity:** implement startup as an explicit **resolution pipeline** with a single ordered list of sources and a documented precedence, then **publish the resolved manifest** as the first event. This is the single most valuable design decision in this whole area: it makes the agent debuggable, makes CI gating possible, and makes the difference between two configurations a diffable object rather than an invisible behaviour. Suppress-then-publish is the right shape — each source contributes to a registry, each source can be individually disabled, and the registry is emitted.

---

### F15 — Interactive input: a rich line editor with quick-command prefixes

**Status: `OBSERVED-DOC`** (the interactive TUI is not reachable for scripted observation in this environment)

**Source:** https://code.claude.com/docs/en/interactive-mode

**`OBSERVED-DOC`** — the "quick command" prefixes, which are the primary input affordances:

| Shortcut | Meaning |
|---|---|
| `/` at start | Command or skill (menu of built-ins, bundled/user skills, plugin commands, MCP prompt commands) |
| `!` at start | Shell mode — "Run a command directly, add its output to the session, and have Claude respond to it" |
| `@` | File path mention — "Trigger file path autocomplete" |
| `:` | Emoji shortcode |
| `?` on empty input | Toggle the shortcut help panel |

**`OBSERVED-DOC`** — multiline input has five independent methods, which is a deliberate portability answer: `\` + `Enter` (works in all terminals), `Option+Enter` (macOS), `Shift+Enter` (iTerm2/WezTerm/Ghostty/Kitty/Warp/Apple Terminal/Windows Terminal), `Ctrl+J` ("works in any terminal without configuration"), and direct paste.

**`OBSERVED-DOC`** — command completion works mid-prompt: "type `/` after a space, then the first letters of a name, as in `run the tests, then /com`", and "Claude Code runs a command itself only when the command starts your message". Outside fullscreen rendering the top match appears as **ghost text** with a `+2` overflow count.

**`OBSERVED-DOC`** — the editing model follows readline conventions (v2.1.261+): `Ctrl+A`/`Ctrl+E` line ends, `Ctrl+K`/`Ctrl+U`/`Ctrl+W` delete (each storing the deleted text), `Ctrl+Y` paste deleted text, `Alt+Y` cycle paste history, `Alt+B`/`Alt+F`/`Alt+D` word motions, `Ctrl+_` undo. Word boundaries treat "a run of letters and digits" as a word (so `_`, `.`, `/` separate words), while `Ctrl+W` deletes back to previous whitespace ignoring punctuation.

**`OBSERVED-DOC`** — the interrupt/steer model, which is the most important interaction behaviour for a coding agent: "Press `Esc` to stop Claude immediately. The running tool call is canceled and Claude waits for your next instruction. If you have messages queued, Claude Code sends them next." Alternatively: "Type a correction and press `Enter` without stopping Claude. The message shows as queued in the conversation. If Claude is running tool calls, it reads the message as soon as those calls finish, within the same turn, and adjusts before its next step."

**`OBSERVED-DOC`** — the keybinding surface for control: `Ctrl+C` ("Interrupt, or clear input… If nothing is running, the first press clears the prompt input and a second press exits"), `Ctrl+D` ("The first press shows a confirmation hint and a second press within 800ms exits"), `Ctrl+O` (transcript viewer), `Ctrl+X Ctrl+K` (stop all running background subagents, with a 3-second double-press confirm).

**`OBSERVED-CLI`** — corroborating the interrupt affordance: the captured TUI status bar reads `⏸ manual mode on · ← for agents · esc to interrupt` — the "esc to interrupt" hint is surfaced in the interface itself. A later capture in the same session shows the shorter variant `⏸ manual mode on · ? for shortcuts`, i.e. the status bar is context-sensitive.

**`OBSERVED-CLI`** — the capture also shows a **live permission-mode indicator** in the status bar (`manual mode on`), an **effort indicator** (`● high · /effort`), and the **spinner** phase text (`Recombobulating…`). The `system/init` event reported `permissionMode: "default"` while the status bar showed `manual mode on` — the CLI's own help explains this: the `manual` mode is the label for the `default` mode ("The `manual` alias selects the permission mode the UI labels Manual").

**`INFERRED`** (reasoning: the `!` shell-mode prefix, the `/`-menu and the `Esc`-to-interrupt semantics are described in the docs, and the captured TUI shows a status bar and a live spinner; but no scripted observation of an interactive TTY session was possible in this environment) A clean-room implementation should treat the interactive TUI as *optional* — the reference product's own architecture puts the TUI in one of several interchangeable front-ends over a shared agent loop, and the stream-json output is the same loop without a TTY. Implement the TUI last.

**Clean-room opportunity:** implement a `LineEditor` abstraction with **pluggable multiline triggers** (the five-method answer is the observable requirement), a **ghost-text completion** widget, and — most valuably — the **queue-while-working** model: a message typed while the agent is busy is queued and delivered at the next tool-call boundary *within the same turn*, and `Esc` cancels the in-flight tool call without ending the session. This "steer without restarting" behaviour is what makes a coding agent feel collaborative, and it is fully specified in the public docs. The transcript's `queue-operation` entry type (§F5) is the on-disk record of the queue, so a clean-room implementation should persist queued messages as first-class entries too.

---

### F16 — Errors, mistyped commands, and unrecognised models are handled at the boundary

**Status: `OBSERVED-CLI`**

**`OBSERVED-CLI`** — a mistyped subcommand produces a suggestion and a helpful redirect, verbatim, **re-verified during this session**:

```
$ claude udpate
✘ unknown command "udpate"
  └ Did you mean claude update?

Run claude --help to list commands, or claude -p "udpate" to send as a prompt.
```

Note the three-part structure: the error marker (`✘`), the indented suggestion, and the escape hatch ("or `claude -p "udpate"` to send as a prompt"). **`OBSERVED-DOC`** confirms the intent: "If you mistype a subcommand, Claude Code suggests the closest match and exits without starting a session."

**`OBSERVED-CLI`** — an unrecognised model is a **non-blocking warning** with an actionable hint, emitted in both the TUI banner and the print-mode stderr:

```
⚠ Model "minimax/minimax-m3.1-flash:free" isn't recognized · context assumed to be 200k tokens · update Claude Code, or see https://code.claude.com/docs/en/model-config
```

and in print mode, structured:

```
[claude-code:unrecognized_model] {"model":"minimax/minimax-m3.1-flash:free","query_source":"sdk"}
```

Note this is a **machine-tagged diagnostic on stderr** (`[claude-code:<category>] {json}`) — a structured side-channel that does not contaminate the JSON on stdout. This is a good pattern: a host can parse the diagnostic separately from the payload.

**`OBSERVED-CLI`** — the empty-input error:

```
Error: Input must be provided either through stdin or as a prompt argument when using --print
```

**`OBSERVED-CLI`** — `claude doctor` is a read-only diagnostic that reports install health *and* provider/connectivity status, verbatim:

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

For a full setup checkup that can also apply fixes, run /doctor in a Claude Code session.
```

**`OBSERVED-CLI`** — `claude auth status` as a scriptable JSON health check (already quoted in F4). **`OBSERVED-DOC`** — its `authMethod` vocabulary: `none`, `claude.ai`, `oauth_token`, `api_key`, `api_key_helper`, `third_party`; the observed value here was `oauth_token` with `apiProvider: firstParty`.

**`OBSERVED-DOC`** — the API-retry event, which is a first-class observable: "When an API request fails with a retryable error, Claude Code emits a `system/api_retry` event before retrying", with fields `type: "system"`, `subtype: "api_retry"`, `attempt`, `max_retries`, `retry_delay_ms`, `error_status`, `error`, `uuid`, `session_id`, and an `error` vocabulary of `authentication_failed`, `oauth_org_not_allowed`, `account_on_hold`, `billing_error`, `rate_limit`, `overloaded`, `invalid_request`, `model_not_found`, `server_error`, `max_output_tokens`, `cloud_credential_error`, `unknown`.

**Clean-room opportunity:** implement a **diagnostic channel** distinct from the data channel — structured, tagged, on stderr (or a dedicated stream), never mixed into the payload. Implement the same three-way treatment of startup problems: *hard error* (no input → refuse to start), *non-blocking warning* (unrecognised model → proceed with a stated assumption), and *suggestion* (near-miss command → propose the correction, plus an escape hatch to reinterpret the input as a prompt). Implement a `doctor`-equivalent that reports install health, provider connectivity, and policy-fetch status in one read-only pass — it is the single most useful troubleshooting surface in the product and trivial to reimplement. Implement the `system/api_retry` event with a stable error vocabulary.

---

### F17 — Startup discovery touches a wide, well-documented configuration surface

**Status: `OBSERVED-DOC` + `OBSERVED-CLI`**

**Source:** https://code.claude.com/docs/en/claude-directory · https://code.claude.com/docs/en/env-vars

**`OBSERVED-DOC`** — the file inventory, with scope and commit status:

| File | Scope | Commit | Purpose |
|---|---|---|---|
| `CLAUDE.md` | project + global | ✓ | Instructions loaded every session |
| `rules/*.md` | project + global | ✓ | Topic-scoped, optionally path-gated instructions |
| `settings.json` | project + global | ✓ | Permissions, hooks, env vars, model defaults |
| `settings.local.json` | project only | | Personal overrides, gitignored |
| `.mcp.json` | project only | ✓ | Team-shared MCP servers |
| `skills/<name>/SKILL.md` | project + global | ✓ | Reusable prompts invoked with `/name` or auto-invoked |
| `commands/*.md` | project + global | ✓ | Single-file prompts; same mechanism as skills |
| `output-styles/*.md` | project + global | ✓ | Custom instruction sets |
| `agents/*.md` | project + global | ✓ | Subagent definitions |
| `workflows/*.js` | project + global | ✓ | Dynamic workflow scripts; each file becomes a `/<name>` command |
| `agent-memory/<name>/` | project + global | ✓ | Persistent memory for subagents |
| `~/.claude.json` | global only | | App state, OAuth, UI toggles, personal MCP servers |
| `~/.claude/keybindings.json` | global only | | Custom keyboard shortcuts |
| `~/.claude/themes/*.json` | global only | | Custom colour themes |

**`OBSERVED-CLI`** — `~/.claude.json` top-level key names (I read **key names only**, no values, and no credential files):

```
activeProviderProfileId, autoModeClassifierBillingNoticeAcknowledgedAt, autoModeEnvSetup,
autoUpdates, autoUpdatesProtectedForNative, cachedChromeExtensionInstalled,
cachedExperimentData, cachedExperimentFeatures, cachedGrowthBookFeatures,
cachedGrowthBookFeaturesAt, changelogLastFetched, closedIssuesLastChecked,
diffSidebarOpen, firstStartTime, githubRepoPaths, hasAvailableSubscription,
hasCompletedOnboarding, hasResetAutoModeOptInForDefaultOffer, hasSeenAutoDefaultNotice,
hasSeenAutoModeEntryWarning, hasSeenAutoModeOutsideReadPrompt, hasSeenTasksHint,
installMethod, lastClawdEntranceVersion, lastOnboardingVersion, lastPlanModeUse,
lastReleaseNotesSeen, machineID, mcpServers, migrationVersion, numStartups,
officialMarketplaceAutoInstallAttempted, officialMarketplaceAutoInstalled,
openaiAdditionalModelOptionsCache, opusProMigrationComplete, pluginUsage, projects,
promptQueueUseCount, providerProfiles, seenNotifications, skillUsage,
sonnet1m45MigrationComplete, subscriptionNoticeCount, tipLifetimeShownCounts,
tipsHistory, tipsHistoryByCommand, unpinFable5LaunchEffort, unpinOpus47LaunchEffort,
unpinOpus48LaunchEffort, userID
```

`projects` maps the **absolute cwd path** to per-project state; `mcpServers` holds personal MCP servers; `numStartups` and `firstStartTime` are lifecycle counters. The file is the **global, non-transcript** state store — distinct from `projects/` (per-project transcripts) and `history.jsonl` (input history).

**`OBSERVED-DOC`** — the env-var layer that participates in startup, with exact names (from the env-vars reference):

`CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_PROJECT_DIR_NAME`, `CLAUDE_CODE_SIMPLE`, `CLAUDE_CODE_SAFE_MODE`, `CLAUDE_CODE_SKIP_PROMPT_HISTORY`, `CLAUDE_CODE_RESUME_INTERRUPTED_TURN`, `CLAUDE_CODE_TMPDIR`, `CLAUDE_CODE_TRANSCRIPT_LOCAL_GC`, `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`, `CLAUDE_CODE_MAX_TURNS`, `CLAUDE_CODE_EFFORT_LEVEL`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, `CLAUDE_CODE_DISABLE_CLAUDE_MDS`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `CLAUDE_CODE_DISABLE_THINKING`, `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE`, `CLAUDE_CODE_EXIT_AFTER_STOP_DELAY`, `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_CODE_BRIDGE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_PROJECT_DIR`, `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`, `MCP_TIMEOUT`, `MCP_TOOL_TIMEOUT`, `MAX_THINKING_TOKENS`, `DISABLE_TELEMETRY`, `DO_NOT_TRACK`, `IS_SANDBOX`, `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`.

The most consequential for this area: `CLAUDE_CONFIG_DIR` (relocates all state), `CLAUDE_CODE_PROJECT_DIR_NAME` (names the project bucket), `CLAUDE_CODE_SKIP_PROMPT_HISTORY` (suppresses transcript + history writes in *all* modes — "The `CLAUDE_CODE_SKIP_PROMPT_HISTORY` environment variable does the same in any mode"), `IS_SANDBOX` (skips the trust dialog), and `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE` (forces persistence for sessions launched inside another Claude Code session — relevant to nesting).

**`OBSERVED-DOC`** — the security posture is explicit and worth copying: "Transcripts and history are not encrypted at rest. OS file permissions are the only protection. If a tool reads a `.env` file or a command prints a credential, that value is written to `projects/<project>/<session>.jsonl`." Recommended mitigations: lower `cleanupPeriodDays`, use `desktopSessionCleanupPeriodDays`, set `CLAUDE_CODE_SKIP_PROMPT_HISTORY` or `--no-session-persistence`, and "Use permission rules to deny reads of credential files."

**`INFERRED`** (reasoning: `CLAUDE_CONFIG_DIR` + `CLAUDE_CODE_PROJECT_DIR_NAME` together fully determine where a session's transcript lands, and both are read at startup; the docs explicitly say "Claude Code reads it once at startup from that environment, so an `env` block in a settings file can't set it") A clean-room implementation must likewise read these **once, at startup, from the process environment** — reading them per-request would let a later-mutated env change the storage location mid-session, which would break transcript continuity.

**Clean-room opportunity:** implement a **three-tier state model** — *global* (`~/.claude.json`-equivalent: app state, personal MCP servers, UI prefs), *per-project* (transcripts, memory, project settings), and *per-session* (transcript, sidecars, scratchpad) — with a single relocatable root. Implement the tier list as an explicit ordered table, and implement `IS_SANDBOX`-style sandbox detection. **Adopt the plaintext-transcript warning explicitly**: a clean-room agent should document that transcripts may contain secrets echoed by tools, and offer the same opt-outs.

---

### F18 — What the *whole* session looks like: a layered, three-plane architecture

**Status: `INFERRED` (synthesis across the above, with cited evidence)**

**Source:** https://code.claude.com/docs/en/how-claude-code-works · https://code.claude.com/docs/en/agent-sdk/agent-loop

**`OBSERVED-DOC`** — the reference product's own description of its layering: "The agentic loop, tools, and capabilities are the same everywhere you use Claude Code. What changes is where the code executes and how you interact with it." Execution environments: Local, Cloud, Remote Control. Interfaces: terminal, desktop app, IDE extensions, claude.ai/code, Remote Control, Slack, CI/CD.

**`OBSERVED-DOC`** — "Claude Code is the layer around the model that provides the tools and manages the context the model sees. This surrounding layer is what the term agentic harness refers to."

**`INFERRED`** — reasoning: the evidence above (four launch modes, four output backends, one `system/init` manifest, one `result` contract, one transcript format, one session store, one agent loop) supports a three-plane architecture that a clean-room implementation should reproduce:

| Plane | Responsibility | Evidence |
|---|---|---|
| **Front-ends** (terminal TUI, `-p` text, `-p` json, `-p` stream-json, IDE, desktop, web) | Input acquisition, rendering, user interaction. Interchangeable. | F1, F6, F7, F8, F15 |
| **Core** (session store, agent loop, tool runtime, permission engine, context manager, config resolver) | Everything that is independent of how the user talks to it. | F4, F5, F10, F13, F14, F17 |
| **Back-ends** (model provider, MCP servers, external services) | Where work actually happens. | F7, F12 |

The decisive evidence for this plane separation is that **`system/init` publishes the core's resolved state, and `result` publishes the core's terminal state, identically across front-ends**. A `--print` run and an interactive session emit the same `system/init`; the difference is only in what renders it.

**`OBSERVED-DOC`** — supporting this, the Agent SDK exists as a *separate distributable* that "gives you the same tools, agent loop, and context management that power Claude Code", and "Both the TypeScript and Python SDKs bundle a native Claude Code binary" — i.e. the core is packaged as a reusable component with the TUI as one consumer among several.

**Clean-room opportunity:** build the core as a **library** with the TUI, the print runner, and (eventually) any embedding SDK as thin adapters over it. Concretely: the core emits a **single ordered event stream**; every front-end is a consumer of that stream with a different renderer. This is the correct architecture and it is directly derivable from the observed public contract. A clean-room implementation that starts with a terminal app and then tries to add a programmatic API will be forced into a rewrite; one that starts with an event-emitting core will not.

---

## 3. Evidence references

### 3.1 Public documentation fetched (all `OBSERVED-DOC` sources)

| URL | Used for |
|---|---|
| https://code.claude.com/docs/en/overview | Product shape, install methods, surfaces, model/subscription requirements |
| https://code.claude.com/docs/en/cli-reference | Full flag/subcommand surface; system-prompt flags; resumed-conversation prompt semantics |
| https://code.claude.com/docs/en/sessions | Session identity, resume/continue/fork, picker, transcript location & encoding, restore policy |
| https://code.claude.com/docs/en/headless | `-p` semantics, `--bare`, output formats, stream-json events, `system/init`, `api_retry`, continue/resume |
| https://code.claude.com/docs/en/interactive-mode | Keybindings, multiline input, quick commands, queueing, transcript viewer, prompt suggestions |
| https://code.claude.com/docs/en/how-claude-code-works | Agentic loop phases, harness framing, environments & interfaces, checkpoints & permissions |
| https://code.claude.com/docs/en/agent-sdk/agent-loop | Turn definition, message types, result subtypes, context window, compaction, hooks, parallel tool execution |
| https://code.claude.com/docs/en/claude-directory | `~/.claude` layout, retention, scratchpad, plaintext-storage warning, purge |
| https://code.claude.com/docs/en/env-vars | Environment variable names and effects |
| https://www.anthropic.com/legal/consumer-terms | §3(3) reverse-engineering prohibition; §3(4) scraping; §3(7) automated access; §4 Materials/training |

### 3.2 Commands executed against the published CLI (all `OBSERVED-CLI`)

```
claude --version                        claude --help (full, 2 reads)
claude doctor                           claude auth status
claude auth --help                      claude agents --help
claude agents --json                    claude agents --json --all
claude mcp --help                       claude mcp list        (x4)
claude mcp get rea                      claude plugin --help
claude udpate            (typo-suggestion test)
claude --bg "Say HELLO"                 claude logs fe547206
claude stop fe547206                    claude rm fe547206
claude -p "…" --output-format json      claude -p "…" --output-format stream-json --verbose --include-partial-messages
claude -p --input-format stream-json --output-format stream-json --verbose  (2-message JSONL on stdin)
echo "…" | claude -p --output-format json
claude -p < /dev/null                   claude < /dev/null
claude -p "…" --session-id 1111…-5555 --output-format json
claude -p "…" --no-session-persistence --output-format json
claude -p "…" --max-turns 1 --output-format json
claude -p "…" --output-format json   then   claude -p --resume <sid> "…" --output-format json
```

`CLAUDE_CONFIG_DIR` was pointed at throwaway directories under `/tmp` for the persistence, resume, threading and tree-schema experiments, so the operator's real `~/.claude` was minimally written to; those temporary directories were deleted afterwards. The one background session created during the investigation (`fe547206`) was stopped and removed.

### 3.3 Artifacts saved

| Path | Contents |
|---|---|
| `../TERMS-NOTES.md` | The compliance boundary for this study (established before inspection) |
| `agent-evidence-area1-cli-startup.md` (this file) | Canonical Area #1 report |
| `../print-mode-json-result.json` | Sanitized `result` object from `--output-format json` |
| `../tui-startup-banner.txt` | ANSI-stripped capture of the real interactive TUI (logo, model line, cwd, warning, prompt, spinner, effort, status bar) |
| `claude-help-full.txt` | Complete `claude --help` output |
| `claude-doctor.txt` | `claude doctor` diagnostics |
| `claude-auth-status.json` | `claude auth status` JSON |
| `claude-agents-all.json` | `claude agents --json --all` session registry |
| `../stream-json-basic.jsonl` | Raw `stream-json` capture including the `system/init` manifest |
| `../sanitized-tool-stream.jsonl` | Sanitized tool-call/tool-result wire format |
| `../cli-help/` | `claude --help`, `claude doctor`, `claude mcp --help` output |
| `../area2-project-context/agent-evidence-area2-project-context.md` | Sibling Area #2 report, preserved after a path collision |
| `../areas/agent-evidence-merged-areas2-and-8.md` | The merged root document as it stood at the end of this investigation, preserved before this file was restored |

---

## 4. Capability table — Area 1

| # | Capability | Status | Surface | Notes |
|---|---|---|---|---|
| 1 | Interactive TUI session | `OBSERVED-CLI` (launch + render) / `OBSERVED-DOC` (behaviour) | `claude` | Rich line editor, quick commands, ghost-text completion, spinner, status bar |
| 2 | Non-interactive print mode | `OBSERVED-CLI` | `claude -p` | 3 output formats; stdin or prompt arg |
| 3 | Background session mode | `OBSERVED-CLI` | `claude --bg` | Supervisor-mediated, addressable, `agents`/`attach`/`logs`/`stop`/`rm`/`respawn` |
| 4 | Cloud / Desktop / Remote Control handoff | `OBSERVED-DOC` | `--cloud`, `--desktop`, `--remote-control` | Subscription-gated; **not observable** on this machine |
| 5 | Project identity from CWD | `OBSERVED-CLI` | automatic | Path → non-alphanumerics to `-`; 200-char truncation + hash |
| 6 | Additional working directories | `OBSERVED-CLI` | `--add-dir` | Grants file access, not config discovery |
| 7 | Session id (UUIDv4) | `OBSERVED-CLI` | generated / `--session-id` | Pinned id honoured exactly |
| 8 | Short handle for background dispatch | `OBSERVED-CLI` | `--bg` prints it | 8 hex chars; a **prefix** of the session id |
| 9 | Display name | `OBSERVED-CLI` | `-n` / `/rename` | Default `<dirname>-<2char>`; also AI-generated titles; not a resume handle |
| 10 | JSONL transcript persistence | `OBSERVED-CLI` | `~/.claude/projects/<proj>/<sid>.jsonl` | Append-only, tree-structured, 16 entry types |
| 11 | Config-root relocation | `OBSERVED-CLI` | `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_PROJECT_DIR_NAME` | Verified in isolated roots |
| 12 | Session persistence opt-out | `OBSERVED-CLI` | `--no-session-persistence`, `CLAUDE_CODE_SKIP_PROMPT_HISTORY` | 0 transcripts written when set; id still issued |
| 13 | Input history sidecar | `OBSERVED-CLI` | `~/.claude/history.jsonl` | `display`/`project`/`sessionId`/`timestamp` |
| 14 | Message-tree threading | `OBSERVED-CLI` | transcript | `uuid`/`parentUuid`/`isSidechain`/`promptId`/`turnPosition`/`entrypoint` |
| 15 | `text` output contract | `OBSERVED-CLI` | `--output-format text` | Plain response |
| 16 | `json` output contract | `OBSERVED-CLI` | `--output-format json` | Full result object, 30+ fields |
| 17 | `stream-json` output contract | `OBSERVED-CLI` | `--output-format stream-json` | Ordered events, raw + assembled |
| 18 | `system/init` manifest | `OBSERVED-CLI` | stream-json | Resolved tools/servers/skills/plugins/capabilities |
| 19 | `text` input contract | `OBSERVED-CLI` | `--input-format text` | stdin blob; 10 MB cap (doc) |
| 20 | `stream-json` input contract | `OBSERVED-CLI` | `--input-format stream-json` | Long-lived multi-turn; state retained (8134 test) |
| 21 | Resume by id / name / path | `OBSERVED-CLI` (id) / `OBSERVED-DOC` (name, path) | `--resume` | Same session id; history intact; `num_turns` spans whole conversation |
| 22 | Continue most recent | `OBSERVED-DOC` | `-c` / `--continue` | Most recent in CWD |
| 23 | Fork / branch | `OBSERVED-DOC` | `--fork-session`, `/branch` | New session id, copied history |
| 24 | Session picker | `OBSERVED-DOC` | `--resume` (no arg), `/resume` | Search, scope, preview, rename, branch filter |
| 25 | Turn loop with tool execution | `OBSERVED-DOC` | core | Ends when the model returns no tool calls |
| 26 | Turn limit | `OBSERVED-CLI` | `--max-turns` | `subtype: error_max_turns` observed; `result` key absent |
| 27 | Budget limit | `OBSERVED-DOC` | `--max-budget-usd` | `error_max_budget_usd`; headroom semantics documented |
| 28 | Result-subtype vocabulary | `OBSERVED-CLI` (2 of 5) / `OBSERVED-DOC` (all 5) | `result.subtype` | `success` / `error_max_turns` / `error_max_budget_usd` / `error_during_execution` / `error_max_structured_output_retries` |
| 29 | System-prompt snapshot | `OBSERVED-DOC` | `--system-prompt-snapshot on\|off` | Recorded on first request; survives resume until compaction |
| 30 | Startup config resolution | `OBSERVED-CLI` | `system/init` | 4 suppression flags, explicit tier precedence |
| 31 | Typos / unknown commands | `OBSERVED-CLI` | `claude udpate` | Suggestion + prompt-escape-hatch |
| 32 | Unknown model warning | `OBSERVED-CLI` | stderr + TUI banner | Non-blocking; tagged diagnostic channel |
| 33 | Installation/connectivity doctor | `OBSERVED-CLI` | `claude doctor` | Read-only, reports provider boundary |
| 34 | Auth status probe | `OBSERVED-CLI` | `claude auth status` | JSON; `authMethod` enum of 6 |
| 35 | Empty-input refusal | `OBSERVED-CLI` | `claude -p` | Explicit error, no silent no-op |
| 36 | Trust dialog skipped off-TTY | `OBSERVED-DOC` + `OBSERVED-CLI` | `-p` / non-TTY | `IS_SANDBOX` also skips it; `--bg` instead *refuses* |
| 37 | MCP server listing & health | `OBSERVED-CLI` | `claude mcp list`, `claude mcp get` | Health is **intermittent** across invocations; 30 s timeout observed |
| 38 | Agent/skill/plugin registry in manifest | `OBSERVED-CLI` | `system/init` | 27 tools, 5 agents, 20 skills, 3 builtin plugins, 53 slash commands, 11 capabilities |
| 39 | Interrupt (Esc) / queue-while-working | `OBSERVED-DOC` + `OBSERVED-CLI` | TUI | Queued message consumed at the next tool boundary; `queue-operation` transcript entry |
| 40 | Session-scoped scratchpad | `OBSERVED-DOC` | temp dir | `<tmp>/claude/<proj>/<sid>/scratchpad/` |

---

## 5. Dependencies

### 5.1 Requires network access
- **Model provider endpoint** — every turn is an HTTP request to the configured base URL. (`OBSERVED-CLI` — `ANTHROPIC_BASE_URL` was set; `claude doctor` reported "Not connected to the Anthropic API".)
- **MCP servers** — stdio servers are local subprocesses but `npx -y rea-agents@6.7.0 mcp` needed the npm registry to start; remote HTTP/SSE servers need the network. (`OBSERVED-CLI`)
- **Plugin marketplaces / `--plugin-url`** — network fetch of a `.zip`. (`OBSERVED-DOC`)
- **Cloud sessions, Remote Control, claude.ai/code, `claude update`, managed-settings fetch, changelog cache, telemetry** — all network. (`OBSERVED-DOC`; `claude doctor` observed the managed-settings fetch being *skipped* on a custom base URL.)

### 5.2 Requires a supported account
- **Anthropic account / Claude subscription** — for interactive login, cloud sessions, Remote Control, `claude setup-token`, `claude auth login`. (`OBSERVED-DOC`)
- **Anthropic Console API key** — for `--console` auth and API-key billing. (`OBSERVED-DOC`)
- **Organization admin** — for managed settings, SSO, the `claude gateway` server, org policy. (`OBSERVED-DOC`)
- **Not required for:** `--bare` runs with `ANTHROPIC_API_KEY` or an `apiKeyHelper`; third-party providers (Bedrock / Vertex / Foundry) with their own credentials; `--restricted`/`--safe-mode` runs; local MCP stdio servers. (`OBSERVED-DOC`)

### 5.3 Requires a model provider
- Every substantive capability requires a reachable model. `claude --bare` still has "Bash, file read, and file edit tools" but no model means no turns.
- `claude --model` accepts an alias (`fable`, `opus`, `sonnet`, `haiku`) or a full model id; `ANTHROPIC_MODEL` is the env fallback. (`OBSERVED-DOC`; `claude --help`.)
- **Provider-specific capabilities degrade** on non-first-party providers: `claude auto-mode` (a model classifier) and `claude channels` "Requires Anthropic authentication through claude.ai or a Console API key"; `--channels` is "not available on Amazon Bedrock, Google Cloud's Agent Platform, or Microsoft Foundry". (`OBSERVED-DOC`)
- **Observed locally:** the model id was not recognised, and the CLI fell back to "context assumed to be 200k tokens" — i.e. **the context window is a client-side assumption, not a server truth**, and an unrecognised model silently changes behaviour. (`OBSERVED-CLI`)

### 5.4 Requires external services
- **MCP servers** — external tools/data. (`OBSERVED-CLI`: one stdio server, `rea`, launched via `cmd.exe /d /c npx -y rea-agents@6.7.0 mcp`. Its health was observed to be **intermittent** — `✘ Failed to connect — connection timed out after 30000ms` on one `claude mcp list`, `✔ Connected` on a `claude mcp get` moments later, and `✔ Connected` on three subsequent `claude mcp list` runs. So stdio MCP startup is **not** guaranteed fast or reliable, a 30 s connection timeout is the observed bound, and a health probe result is point-in-time only.)
- **Git** — for worktrees, branch detection, and the git context in the system prompt. `gitBranch` was recorded as `HEAD` in a non-git directory. (`OBSERVED-CLI`)
- **A shell** — the Bash tool. On this Windows box the CLI resolved `PowerShell` to `C:\Users\Admin\AppData\Local\Microsoft\WindowsApps\…\pwsh.exe` and advertised both `Bash` and `PowerShell` tools; the docs note "If Git for Windows is not installed, Claude Code uses PowerShell as the shell tool instead." (`OBSERVED-CLI` + `OBSERVED-DOC`)
- **A terminal** — for the interactive TUI and for `claude agents` agent view ("Opening agent view requires an interactive terminal"). (`OBSERVED-DOC`)

### 5.5 Minimal viable dependency set for a clean-room Area-1 implementation
A model endpoint + a local filesystem + a shell + a JSONL store. Everything else (MCP, plugins, skills, subagents, cloud, remote control) is additive.

---

## 6. Limitations of this investigation

1. **Custom provider.** All `OBSERVED-CLI` evidence comes from a non-Anthropic gateway. Behaviour that depends on first-party endpoints — Remote Control, cloud sessions, org policy, managed settings, `claude setup-token`, subscription-gated features — was **not** observed and is marked `INFERRED` from docs. The `system/init` manifest reported `apiKeySource: "none"`, so the first-party auth paths were likewise unobserved.
2. **The interactive TUI was not driven.** I captured its rendered output (via `claude logs` on a background session) but never sent it keystrokes. All interactive *behaviour* claims are `OBSERVED-DOC`; only the *rendering* is `OBSERVED-CLI`.
3. **The transcript format is explicitly unstable.** The docs state the entry format "is internal to Claude Code and changes between versions". My 16 entry types are a snapshot of 2.1.306 and include several (`atis-latch`, `api-request-shape`, `api-request-blob`) whose purpose I did not determine. A clean-room implementation must not depend on them.
4. **The system prompt was never read.** It is not exposed in any event stream. Its *content* is `UNKNOWN`; only its *lifecycle* (snapshot on/off, replacement vs append) is documented.
5. **Permission enforcement was not measured.** `claude --permission-mode` and the permission-prompt surface belong to Area 8; the `--permission-mode default` → UI label `manual mode on` correspondence is the only permission fact observed here.
6. **No subagent nesting was exercised.** `isSidechain` was observed only as `False`. The sidechain *tree* shape is `INFERRED` from the field's name and the existence of `projects/<project>/<session>/subagents/`.
7. **`--restricted` / `--safe-mode` / `--bare` were not run**, so their tool-set deltas are `OBSERVED-DOC` only.
8. **The `attach` and `respawn` background verbs were not exercised**; only `agents`, `logs`, `stop` and `rm` were.
9. **Time-boxed.** ~20 minutes of investigation, per instruction. Deeper areas (context compaction mechanics, checkpointing, the `api-request` audit records) were observed in passing but not analysed.

---

## 7. Unresolved questions (`UNKNOWN`)

| # | Question | Why it could not be established |
|---|---|---|
| 1 | What exactly is in the default system prompt? | Not exposed in any event stream; reading it would require inspecting the proprietary binary, which the terms forbid. `UNKNOWN` by design. |
| 2 | What is `atis-latch`? | Appeared 147 times in one transcript (and 3 times in a fresh one) with an `atis` payload whose meaning is not documented. `UNKNOWN`. |
| 3 | What are `api-request-shape` / `api-request-blob` / `api-request` for? | They appear to be an audit record of wire requests (`params`, `cacheControl`, `requestDigest`, `shapeHash`). Their exact role is not documented. `INFERRED` as an audit/cache-control log; `UNKNOWN` in detail. |
| 4 | Is the `id` in `api-request` a provider request id? | It has the shape of a provider id and appears only for assistant entries, but it is undocumented. `UNKNOWN`. |
| 5 | What is the exact `shapeHash` / `requestDigest` algorithm? | Not documented; presumably a content hash. `INFERRED`; algorithm `UNKNOWN`. |
| 6 | How is the generated session title produced exactly? | Observed: a background session titled `"claude clone greeting"` and another `"ls git version"`. Documented as "written by a background request to the small/fast model, normally a Haiku-class model", but the prompt and post-processing are not published. `UNKNOWN`. |
| 7 | What is the `messaging_socket_path` protocol? | `\\.\pipe\LOCAL\cc-msg-…` is advertised for cross-session messaging, with `CLAUDE_CODE_MESSAGING_SOCKET` / `CLAUDE_CODE_MESSAGING_TOKEN` exported to subprocesses. The wire protocol is undocumented. `UNKNOWN` — relevant to Area 7 (session resumption / long sessions). |
| 8 | What is the `caller: {"type":"direct"}` field on tool_use blocks? | Observed in a sibling area's capture; not documented. `UNKNOWN`. |
| 9 | Why did `num_turns` report 2 for a `--max-turns 1` run? | The docs say `max_turns` "counts tool-use turns only" and the run ended `stop_reason: tool_use`. Whether the counter is inclusive of the interrupted turn is not stated. `INFERRED` that the count includes the turn that hit the limit. |
| 10 | Why did a 2-message stream-json run report `num_turns: 4`, and why did a resumed run report `num_turns: 4` for a single new prompt? | Two human messages should ideally be 2 turns. The count appears to reflect evaluate/execute cycles and, on resume, the whole conversation rather than the resumed segment. `UNKNOWN` in detail. |
| 11 | Is `--continue`'s "most recent" ordering by last activity, creation, or transcript mtime? | The docs say "most recent conversation in the current directory" without specifying. `UNKNOWN`. |
| 12 | Exact timeout values for the MCP startup wait and the background-work ceiling. | `MCP_TIMEOUT` is documented as "the timeout for starting and connecting to MCP servers" with "30 seconds by default"; `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` default is 10 minutes per the headless doc. The *interaction* of the two is not documented. `INFERRED`. |
| 13 | How the compaction boundary alters the message tree. | The docs state compaction replaces older messages with a summary and emits `system/compact_boundary`; the tree surgery (which nodes are retained, how `parentUuid` is re-rooted) is not documented. `UNKNOWN`. |
| 14 | Why does `claude mcp list` and `claude mcp get` disagree about the same server's status, and why is the status unstable across identical invocations? | Observed `✘ Failed to connect … timed out after 30000ms` then `✔ Connected` minutes later, then `✔ Connected` three times running. Whether this is a cold-vs-warm cache, an npx registry latency, or a genuine per-invocation spawn is not established. `UNKNOWN`. |
| 15 | Whether the `permissionMode` recorded per turn can differ from the session's launch mode. | Observed `permissionMode: 'default'` on a user entry while `system/init` reported `"permissionMode":"default"` and the status bar showed `manual mode on`; a sibling capture showed `'auto'`. The docs explain `manual` is the UI label for `default`, but a genuine divergence between init and per-turn values is not explained. `INFERRED` that the user entry reflects a mid-session mode change. |
| 16 | The exact ordering guarantee between `system/init` and `plugin_install` / hook events. | Documented: "The `system/init` event… is the first event in the stream unless startup events precede it" — the exact precedence rules are only partially specified. `INFERRED`. |
| 17 | Whether `claude --cloud` and `--desktop` are usable at all without a subscription. | Not observable here. `INFERRED` from docs. |
| 18 | Why did `--bg` refuse to start in an untrusted workspace while `-p` silently proceeds? | Both behaviours are `OBSERVED-CLI`; the *rationale* for the asymmetry is not documented. `UNKNOWN`. |

---

## 8. Recommended scope for an independent functional implementation (Area 1)

### 8.1 In scope — build these first (this is the whole product's skeleton)

| Priority | Component | Concrete requirement | Reference finding |
|---|---|---|---|
| P0 | **Session store** | JSONL, append-only, one self-describing object per line; config-root relocatable; project key = deterministic function of CWD; per-project + per-session buckets; a separate input-history sidecar; an opt-out that suppresses all writes | F2, F4, F17 |
| P0 | **Agent loop** | Request → model response → tool execution → results fed back → repeat; ends when the model returns no tool calls; three termination modes (natural / turn-cap / budget-cap) with distinct result subtypes; read-only tools concurrent, mutating tools sequential | F10 |
| P0 | **Result contract** | A single terminal `result` object with: `type`, `subtype` (5-value enum), `is_error`, `result` (only on `success`), `num_turns`, `session_id`, `usage`, `modelUsage`, `total_cost_usd`, `stop_reason`, `permission_denials`, `subagent_stats`, `safety_stops`, and the fine-grained latency fields | F6 |
| P0 | **`system/init` manifest** | First event of every session; publishes the resolved tools, servers, skills, commands, agents, plugins, model, permission mode, capabilities, memory paths, additional directories. The CI-gating surface | F7, F14 |
| P0 | **Two input contracts** | `text` (one stdin blob or prompt arg) and `stream-json` (long-lived JSONL message stream, state retained across messages within one process) | F8 |
| P0 | **Three output contracts** | `text`, `json`, `stream-json` (ordered event protocol: init → status → provider chunks → assembled assistant message → result) | F6, F7 |
| P1 | **Session identity & resume** | UUIDv4 session id (pinnable), short handle (a derivable prefix), mutable display name; resume by id/name/transcript-path with a documented lookup order; continue; fork (copy the transcript, new id); a session picker with search/scope/preview/rename | F3, F11 |
| P1 | **Startup config resolution** | An ordered, documented precedence chain (managed → user → project → local → `--settings` → CLI flags → env overrides); per-source suppression flags; publish the resolved manifest | F14, F17 |
| P1 | **System-prompt snapshot** | Build once on the first request, record it, reuse verbatim for the session's lifetime, invalidate on compaction; `--system-prompt-snapshot on\|off`; a static/dynamic boundary marker for prompt-cache reuse. Never expose the prompt text in the event stream | F13 |
| P1 | **Error & diagnostic surfaces** | A structured diagnostic channel distinct from the data channel; three-way startup-problem treatment (hard error / non-blocking warning / suggestion-with-escape-hatch); a read-only `doctor`; a scriptable `auth status` JSON; a `system/api_retry` event with a stable error vocabulary | F16 |
| P2 | **Background sessions** | A supervisor process owning workers; a JSON registry (`{short-id, session-id, pid, cwd, kind, status, state, name, startedAt}`); lifecycle verbs `agents`/`attach`/`logs`/`stop`/`rm`/`respawn`; trust enforced at start | F12, F1 |
| P2 | **Message-tree persistence** | Parent-pointer tree with `uuid`/`parentUuid`, an `isSidechain` branch marker, a `promptId` grouping and `turnPosition` ordinals, an `entrypoint` marker; derive the linear main-thread view as a projection; persist queued messages as first-class entries | F5, F15 |
| P2 | **Interactive TUI** | A line editor with pluggable multiline triggers, quick-command prefixes (`/`, `!`, `@`, `:`), ghost-text completion, a spinner, a status bar (mode + effort + interrupt hint), Esc-to-interrupt, and queue-while-working | F15 |
| P2 | **Trust decision** | Explicit trusted / untrusted / not-applicable (non-TTY) states, observable, with `IS_SANDBOX`-style detection; a clear log line when a non-interactive run still loads project hooks and MCP servers; refuse to start a long-lived background session in an untrusted workspace | F9, F1 |

### 8.2 Explicitly out of scope for a first implementation
- **Cloud sessions, Remote Control, Desktop handoff, `--teleport`, IDE extensions** — subscription-gated, provider-specific, and orthogonal to the core loop.
- **The plugin ecosystem and marketplaces** — large surface, low value relative to the core.
- **Subagents / agent teams / dynamic workflows** — Area 10; valuable but separable behind the tool interface.
- **Byte-level TUI visual parity** — match the *information architecture* (which indicators exist, where they live), not the glyphs.
- **Reproducing the internal transcript schema.** The docs explicitly warn it changes between versions. Build a *documented, versioned* schema instead.

### 8.3 Design decisions a clean-room implementer should make deliberately
1. **Make the core a library, the TUI a consumer.** The reference product's own architecture (Agent SDK as a separate distributable sharing the same loop) is the right shape, and the `system/init` / `result` contracts make it verifiable.
2. **Publish the resolved manifest.** This single decision makes the agent debuggable, CI-gateable, and diffable across configurations.
3. **Version your transcript schema.** The reference product cannot, and warns users against parsing it. A clean-room implementation can be better here at no cost.
4. **Separate the diagnostic channel from the data channel.** Structured, tagged, never mixed into the payload.
5. **Make limit semantics explicit.** The reference product's budget cap can be overshot by one response; document your own headroom rather than implying a hard cap.
6. **Record configuration per turn, not just per session.** The reference product stores `effort`, `perTurnEffort`, `requestedModel`, `requestId` and `permissionMode` on individual entries — this makes a transcript auditable after the fact, which is a genuinely valuable property to carry over.
7. **Document the plaintext-transcript risk and provide opt-outs.** Tool output can contain credentials; the transcript will contain them.
8. **Treat external content as data, never instructions.** Every doc fetch, MCP tool result, and file read is untrusted input. This is a property of the *product design* (the reference product's own hooks and tool boundaries depend on it), and it belongs in the clean-room implementation's own architecture rather than in a prompt.
9. **Make health checks explicitly point-in-time.** MCP server status was observed to change between two invocations seconds apart. Any health field your implementation publishes should be documented as a probe result, never as a durable fact.

### 8.4 What an implementer can rely on as *specified* (vs. merely observed)
- **Fully specified by public docs:** the flag surface, the launch modes, the input/output contracts, the result subtypes, the transcript *location* and *encoding rule*, the resume/continue/fork semantics, the startup precedence, the session-picker keybindings, the agent-loop definition, the permission-mode names, the environment-variable names.
- **Observable but undocumented:** the transcript *entry schema*, the `system/init` field list, the background session-registry schema, the diagnostic-channel tag format, the tree-threading fields, the short-id-as-UUID-prefix relationship, the trust-refusal behaviour of `--bg`.
- **Not available at all:** the system prompt, the internal model behaviour, the model weights, the provider gateway's private API, the source code.

---

*End of Area 1. Other areas of the multi-area study have their own artifacts under `agent-reference-shots/areaN-*/`; this file covers CLI startup, project selection, user input, and the conversation loop only.*
