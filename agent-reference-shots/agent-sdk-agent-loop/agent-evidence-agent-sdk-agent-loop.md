# Agent SDK — The Agent Loop: message types, stop reasons, tool dispatch, and the exact event stream

**Focus page:** <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>
**Corroborating pages fetched:** <https://code.claude.com/docs/en/agent-sdk/typescript.md>, <https://code.claude.com/docs/en/agent-sdk/python.md>, <https://code.claude.com/docs/en/how-claude-code-works.md>
**Product under study:** Claude Code 2.1.306 (native build, `win32-x64`, commit `01ae8327ca99`)
**Host:** Windows 11 Pro 10.0.26300
**Date:** 2026-10-21
**Classification:** `OBSERVED-DOC` (stated in a cited Anthropic doc, quoted verbatim) · `INFERRED` (conclusion, reasoning stated) · `UNKNOWN` (evidence cannot establish it)

> **Compliance boundary.** Claude Code is proprietary. Anthropic's Consumer ToS §3 and Commercial ToS §D.4 prohibit decompiling / reverse engineering / disassembling the Services, and the docs state "The Claude Code binary must not be modified." **No decompilation, source-map extraction, binary modification, or credential/licence-file access was performed for this chapter.** REA was deliberately **not** invoked against the Claude Code binary. The method here was: (a) fetching the public markdown documentation, (b) reading the published SDK type references, (c) cross-checking against a prior black-box CLI capture already saved in this evidence tree (`agent-reference-shots/area1-agent-loop/`). See `agent-reference-shots/TERMS-NOTES.md`.

> **Machine caveat.** This host runs Claude Code against a **custom `ANTHROPIC_BASE_URL`** (a third-party gateway serving a non-Anthropic model), not `api.anthropic.com`. Every claim below is therefore **documentation-derived** (`OBSERVED-DOC`) rather than locally re-observed, with the exception of the handful of claims explicitly cross-checked against the previously saved local CLI capture, which are marked `OBSERVED-CLI (prior capture)`.

> **Security note.** Fetched web text was treated as untrusted data. No directive found in any fetched page was executed or followed. The `.md` suffix on the docs URLs serves plain markdown; the raw files are cached at `agent-reference-shots/agent-sdk-agent-loop/` for independent re-reading.

---

## 1. Executive summary

This page is the **best single specification of the agent loop that Anthropic publishes**. It is unusually precise for documentation: it names the exact five message types, the exact `subtype` strings, the exact option keys in both snake_case (Python) and camelCase (TypeScript) spellings, the exact permission-mode vocabulary, and it distinguishes the five result-subtype outcomes in a table with a "is the `result` field available?" column. For a clean-room implementer, this page is close to a wire-contract document for the loop.

**The loop is a four-phase cycle with exactly one termination condition.** The contract, verbatim from `## The loop at a glance`: *"Receive prompt… Evaluate and respond… Execute tools… Repeat… Return result."* The loop terminates when *"Claude continues calling tools and processing results until it produces a response with no tool calls."* That is the *only* natural exit; every other exit is an injected limit (turn cap, budget cap, crash, structured-output retry exhaustion) or an error.

**The event stream has exactly five core message types, and the discriminators are `type` + `subtype`.** `SystemMessage`, `AssistantMessage`, `UserMessage`, `StreamEvent`, `ResultMessage`. Two details matter enormously for a reimplementation and are easy to miss:

1. **One `AssistantMessage` per content block, not per model response.** *"The SDK yields one or more `AssistantMessage` objects, one for each content block, such as a text block or a tool call request."* In TypeScript the blocks live at `message.message.content`, **not** `message.content` — a nesting asymmetry that will silently break a naive implementation. In Python they live at `message.content` as a `list[ContentBlock]`.
2. **`UserMessage` is overloaded: it carries tool results *and* mid-loop user input.** *"emitted after each tool execution with the tool result content sent back to Claude. Also emitted for any user inputs you stream mid-loop."* A consumer that assumes "user message == tool result" will mis-handle interactive turns.

**Stop reasons are a small, closed vocabulary on the final turn only.** `end_turn` (model finished normally), `max_tokens` (hit the output token limit), `refusal` (the model declined). The field is `string | null` in TypeScript and `str | None` in Python, and is `null` on the synthesised result that follows a session crash. `stop_reason` on the *result* carries the value from the last assistant response; `stop_reason` on an *AssistantMessage* carries the per-response API value (e.g. `end_turn`, `tool_use`).

**Tool dispatch has a documented concurrency rule keyed on a specific MCP annotation.** Read-only tools (`Read`, `Glob`, `Grep`, and MCP tools marked read-only) may run concurrently; state-changing tools (`Edit`, `Write`, `Bash`) run sequentially *"to avoid conflicts."* The opt-in for a custom tool is the MCP-standard annotation **`readOnlyHint`**, and the page explicitly says both SDKs use *"this field name from the MCP SDK"* — a reimplementation should reuse the MCP annotation vocabulary rather than inventing a parallel flag.

**The permission model is three orthogonal axes, not one.** `allowed_tools`/`allowedTools` (auto-approve), `disallowed_tools`/`disallowedTools` (block, *"regardless of other settings"*), and `permission_mode`/`permissionMode` (oversight level). The crucial subtlety is that allow-list membership is **not** a restriction: *"Tools not listed are still available, and calls to them that need approval fall through to the permission mode and `canUseTool`."* Six permission modes are named: `default`, `acceptEdits`, `plan`, `dontAsk`, `auto`, `bypassPermissions`.

**Context management is a first-class layer, not a side effect.** The page provides a *table of what consumes context* (system prompt, CLAUDE.md files, tool definitions, conversation history, skill descriptions) with *when it loads* and *impact*, plus a dedicated compaction section that specifies the observable event (`type: "system"`, `subtype: "compact_boundary"`) and three customisation hooks (CLAUDE.md summary instructions, the `PreCompact` hook, manual `/compact`).

**Result handling is the contract every CI gate will be written against.** Five subtypes — `success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries` — and the `result` field is **only** populated on `success`. All subtypes carry `total_cost_usd`, `usage`, `num_turns`, `session_id`. A single-shot `query()` call *"yields the final result message, then raises an error"* — the raise is intentional.

**Verdict on page density:** this page is **not thin**. It contains roughly 40 distinct, nameable contracts (message types, subtypes, option keys, mode names, effort levels, result subtypes, stop reasons, hook names, tool names). The claims below are selected for concreteness rather than padded to a count.

---

## 2. Claims

### C1 — The loop is a five-step cycle with exactly one natural termination condition

**Status: `OBSERVED-DOC`**
**Section: `## The loop at a glance`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "1. **Receive prompt.** Claude receives your prompt, along with the system prompt, tool definitions, and conversation history. The SDK yields a [`SystemMessage`](#message-types) with subtype `"init"` containing session metadata.
> 2. **Evaluate and respond.** Claude evaluates the current state and determines how to proceed. It may respond with text, request one or more tool calls, or both. The SDK yields one or more [`AssistantMessage`](#message-types) objects, one for each content block, such as a text block or a tool call request.
> 3. **Execute tools.** The SDK runs each requested tool and collects the results. Each set of tool results feeds back to Claude for the next decision. You can use [hooks] to intercept, modify, or block tool calls before they run.
> 4. **Repeat.** Steps 2 and 3 repeat as a cycle. Each full cycle is one turn. Claude continues calling tools and processing results until it produces a response with no tool calls.
> 5. **Return result.** The SDK yields a final [`AssistantMessage`](#message-types) with the text response (no tool calls), followed by a [`ResultMessage`](#message-types) with the final text, token usage, cost, and session ID."

**Reimplementation relevance: foundational.** A turn is defined as *"one round trip inside the loop: Claude produces output that includes tool calls, the SDK executes those tools, and the results feed back to Claude automatically."* The invariant to reproduce: **the last assistant message before the result must contain no tool-use block**, and that is the only structural signal of completion.

---

### C2 — A turn is one round trip, and it does not yield control back to the caller

**Status: `OBSERVED-DOC`**
**Section: `## Turns and messages`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "A turn is one round trip inside the loop: Claude produces output that includes tool calls, the SDK executes those tools, and the results feed back to Claude automatically. This happens without yielding control back to your code. Turns continue until Claude produces output with no tool calls, at which point the loop ends and the final result is delivered."

**Reimplementation relevance: high.** The wording pins down an *asynchrony* property: tool execution is not a caller-visible step. A reimplementation that exposes tool execution as an explicit callback-driven phase will not match the documented turn accounting (`num_turns`), which counts evaluate/execute cycles.

---

### C3 — The five core message types, and that they "cover the full agent loop lifecycle"

**Status: `OBSERVED-DOC`**
**Section: `## Message types`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "As the loop runs, the SDK yields a stream of messages. Each message carries a type that tells you what stage of the loop it came from. The five core types are:
> * **`SystemMessage`:** session lifecycle events. The `subtype` field distinguishes them:
>   * `"init"`: session metadata for the run. When a `SessionStart` or `Setup` hook runs during session startup, its hook lifecycle messages arrive before the `init` message
>   * `"compact_boundary"`: fires after [compaction](#automatic-compaction)
>   * `"informational"`: plain-text status banners from the loop
>   * `"worker_shutting_down"`: the host is exiting or Remote Control disconnected
>   In TypeScript, each subtype other than `"init"` is its own type in the `SDKMessage` union rather than a subtype of `SDKSystemMessage`.
> * **`AssistantMessage`:** emitted for each content block in Claude's responses, including the final text-only one. Each carries a single content block, such as text or a tool call, and the messages from one response share a message ID.
> * **`UserMessage`:** emitted after each tool execution with the tool result content sent back to Claude. Also emitted for any user inputs you stream mid-loop.
> * **`StreamEvent`:** only emitted when partial messages are enabled. Contains raw API streaming events (text deltas, tool input chunks).
> * **`ResultMessage`:** marks the end of the agent loop. Contains the final text result, token usage, cost, and session ID."

And: *"These five types cover the full agent loop lifecycle. Both SDKs also yield observability events such as rate-limit status and task notifications that are not required to drive the loop."*

**Reimplementation relevance: foundational.** The `SystemMessage` subtype vocabulary is exactly four strings: `"init"`, `"compact_boundary"`, `"informational"`, `"worker_shutting_down"`. Note the trailing-event caveat in C8.

---

### C4 — One `AssistantMessage` per content block; blocks nested under `.message.content` in TypeScript

**Status: `OBSERVED-DOC`**
**Section: `## Message types` → `### Handle messages`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "**`AssistantMessage`:** emitted for each content block in Claude's responses, including the final text-only one. Each carries a single content block, such as text or a tool call, and the messages from one response share a message ID."

> "**TypeScript:** check the `type` string field (for example, `message.type === "result"`). `AssistantMessage` and `UserMessage` wrap the raw API message in a `.message` field, so content blocks are at `message.message.content`, not `message.content`."

> "**Python:** check message types with `isinstance()` against classes imported from `claude_agent_sdk` (for example, `isinstance(message, ResultMessage)`)."

**Reimplementation relevance: high.** The TypeScript shape is confirmed by the SDK reference (`agent-sdk-typescript.md`): `SDKAssistantMessage = { type: "assistant"; uuid; session_id; message: BetaMessage; parent_tool_use_id: string | null; error?; aborted?; agent_id?; timestamp?; context_usage?; usage_report?; user_message_uuid?; user_message_uuids?; resume_reason?; }`. The Python shape (`agent-sdk-python.md`) is `@dataclass class AssistantMessage: content: list[ContentBlock]; model: str; parent_tool_use_id: str | None = None; error; usage; message_id: str | None = None; stop_reason: str | None = None; session_id; uuid`. The Python doc states: *"API message ID. Multiple messages from one turn share the same ID."* — i.e. the shared-ID grouping is the documented way to reassemble the per-block messages back into one model response.

**Clean-room opportunity:** emit a discriminated event union. A single event type with `type` + optional `subtype` + an opaque `payload` mirrors the observable contract without copying any Anthropic type definition. The per-block fan-out is the contract; the specific class layout is not.

---

### C5 — `UserMessage` carries both tool results and mid-loop user input

**Status: `OBSERVED-DOC`**
**Section: `## Message types`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "**`UserMessage`:** emitted after each tool execution with the tool result content sent back to Claude. Also emitted for any user inputs you stream mid-loop."

Corroborated by the Python reference (`agent-sdk-python.md`), whose `UserMessage` dataclass carries `content`, `uuid`, `parent_tool_use_id`, `tool_use_result`, `origin`, and whose doc table says: *"`parent_tool_use_id` — Tool use ID if this message is a tool result response"*.

**Reimplementation relevance: high.** A reimplementation must have **one** user-event channel with a discriminator, not two. The discriminator that already exists in the observable contract is `parent_tool_use_id` (non-null ⇒ tool result) plus the presence of a `tool_result` content block.

---

### C6 — `StreamEvent` is opt-in and is disabled by default

**Status: `OBSERVED-DOC`**
**Section: `## Message types` → `### Handle messages`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "**`StreamEvent`:** only emitted when partial messages are enabled. Contains raw API streaming events (text deltas, tool input chunks)."

> "**Live streaming:** enable partial messages (`include_partial_messages` in Python, `includePartialMessages` in TypeScript) to get `StreamEvent` messages in real time."

Confirmed in the Python reference: `include_partial_messages: bool = False` — *"Include partial message streaming events. When enabled, [`StreamEvent`](#streamevent) messages are yielded"*.

**Reimplementation relevance: medium.** The TypeScript reference shows the concrete wire form: `SDKPartialAssistantMessage = { type: "stream_event"; event: BetaRawMessageStreamEvent; parent_tool_use_id: string | null; uuid; session_id; ttft_ms?; ... }` — note the `type` string is `"stream_event"`, **not** `"stream"`.

**Clean-room opportunity:** implement streaming as an *additional* event type on the same union, gated by a single boolean, rather than as a separate transport. This preserves the "one stream, many message kinds" property that the trailing-event caveat (C8) depends on.

---

### C7 — The result message may be followed by trailing system events; the consumer must not break on it

**Status: `OBSERVED-DOC`**
**Section: `## Message types`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "**`ResultMessage`:** marks the end of the agent loop. Contains the final text result, token usage, cost, and session ID. Check the `subtype` field to determine whether the task succeeded or hit a limit. **A small number of trailing system events, such as `prompt_suggestion`, can arrive after it, so iterate the stream to completion rather than breaking on the result.**"

**Reimplementation relevance: high.** This is a precise, testable behavioural claim. The consequence: a reimplementation that closes the stream on the result message will drop events. The Python reference corroborates the same idea from a different angle: *"a `session_state_changed` message can follow that result"* and *"Iterate with `receive_messages()` to read them: `receive_response()` stops at the `ResultMessage`."*

**Clean-room opportunity:** the result event should be a *terminal-state marker inside a continuing stream*, not a stream terminator. Implement `receive_all()` / `receive_response()` style helpers to mirror that distinction — it is a design pattern, not Anthropic code.

---

### C8 — The result `subtype` vocabulary and which subtypes carry a `result` field

**Status: `OBSERVED-DOC`**
**Section: `## Handle the result`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "The `subtype` field (available in both SDKs) is the primary way to check termination state.
>
> | Result subtype | What happened | `result` field available? |
> | :- | :- | :-: |
> | `success` | Claude finished the task normally | Yes |
> | `error_max_turns` | Hit the `maxTurns` limit before finishing | No |
> | `error_max_budget_usd` | Hit the `maxBudgetUsd` limit before finishing | No |
> | `error_during_execution` | An error interrupted the loop (for example, a cancelled request) | No |
> | `error_max_structured_output_retries` | No valid structured output was produced within the configured retry limit: every attempt failed validation, or a model fallback retracted the completed output with no successful retry | No |"

> "The `result` field holds the final text output and is only present on the `success` variant, so always check the subtype before reading it."

> "All result subtypes carry `total_cost_usd`, `usage`, `num_turns`, and `session_id` so you can track cost and resume even after errors."

**Reimplementation relevance: foundational.** The exact five strings — `success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries` — are the vocabulary a CI gate will match on. Note `error_max_structured_output_retries` has two documented causes: *"every attempt failed validation, or a model fallback retracted the completed output with no successful retry"*.

The TypeScript reference confirms the shape (`agent-sdk-typescript.md`): the success variant carries `result: string` plus `structured_output?: unknown`, `deferred_tool_use?: { id, name, input }`, `permission_denials: SDKPermissionDenial[]`, `modelUsage`, `total_cost_usd`, `usage: NonNullableUsage`, `num_turns`, `stop_reason`, `is_error`, `api_error_status?`, `terminal_reason?`, `origin?`; the error variant carries `errors: string[]` and `startup_failure_reason?` but **no** `result` field.

---

### C9 — `stop_reason` values, and the `null` on a crash-synthesised result

**Status: `OBSERVED-DOC`**
**Section: `## Handle the result`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "The result also includes a `stop_reason` field (`string | null` in TypeScript, `str | None` in Python) indicating why the model stopped generating on its final turn. Common values are `end_turn` (model finished normally), `max_tokens` (hit the output token limit), and `refusal` (the model declined the request). On error results that the loop produced, `stop_reason` carries the value from the last assistant response before the loop ended; the result Claude Code synthesizes after a session crash carries `null`."

> "To detect refusals, check `stop_reason === "refusal"` (TypeScript) or `stop_reason == "refusal"` (Python)."

> "After a session crash, the final result is an `error_during_execution` whose cost fields may be zeroed and whose `stop_reason` is `null`, and the process exits after emitting it."

**Reimplementation relevance: high.** Two distinct `stop_reason` carriers exist and they mean different things: the **per-message** `stop_reason` (API-level, e.g. `tool_use` — confirmed by the Python `AssistantMessage.stop_reason` doc: *"Stop reason from the API (for example, `end_turn`, `tool_use`)"*) and the **result-level** `stop_reason` (final-turn disposition: `end_turn` / `max_tokens` / `refusal` / `null`). The Python `AssistantMessage` doc separately says `message_id` is *"API message ID. Multiple messages from one turn share the same ID"*.

---

### C10 — A single-shot `query()` yields the error result and *then* raises

**Status: `OBSERVED-DOC`**
**Section: `## Handle the result` (NOTE callout)**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "When a query ends on an error result:
> * A single-shot `query()` call yields the final result message, then raises an error that includes the failure text, such as `Reached maximum number of turns`. The raise is intentional. Wrap the loop in a try block if your code needs to continue past it. The underlying Claude Code process also exits with a nonzero code.
> * A streaming input session stays alive, and you can keep sending messages, except after a session crash, which emits a final `error_during_execution` result and exits the process."

The same statement appears verbatim in both code examples on the page:

> "# A single-shot query() raises after yielding an error result. If the
> # failure was an error result, the error subtype branches above have
> # already run; connection or process failures yield no result message."

**Reimplementation relevance: high.** The distinction between *"the failure was an error result"* and *"connection or process failures yield no result message"* is a real, observable asymmetry that the docs call out twice. An implementation that only signals via exception would lose the error subtype, cost, and usage fields; an implementation that only signals via the event would need to replicate the deliberate raise.

**Clean-room opportunity:** model this as a *contract with two channels* — a terminal event carrying the outcome, plus a process-level failure signal. The idiomatic implementation is: emit the terminal outcome event, then raise a dedicated `TerminalOutcomeError` subtype carrying the same payload; use separate exception types for transport failures so callers can distinguish "the agent failed" from "the pipe broke". This is a standard two-phase-completion pattern.

---

### C11 — The exact tool roster, with `ToolSearch` as an explicit on-demand loader

**Status: `OBSERVED-DOC`**
**Section: `## Tool execution` → `### Built-in tools`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "| Category | Tools | What they do |
> | :- | :- | :- |
> | **File operations** | `Read`, `Edit`, `Write` | Read, modify, and create files |
> | **Search** | `Glob`, `Grep` | Find files by pattern, search content with regex |
> | **Execution** | `Bash` | Run shell commands, scripts, git operations |
> | **Web** | `WebSearch`, `WebFetch` | Search the web, fetch and parse pages |
> | **Discovery** | `ToolSearch` | Dynamically find and load tools on-demand instead of preloading all of them |
> | **Orchestration** | `Agent`, `Skill`, `AskUserQuestion`, `TaskCreate`, `TaskUpdate` | Spawn subagents, invoke skills, ask the user, track tasks |"

> "On the [models that don't get the task-tracking tools], Claude Code provides `TaskCreate` and `TaskUpdate` only when you opt in."

**Reimplementation relevance: high.** The page confirms the SDK tool surface is identical to the CLI's built-in tool surface, and that tool *loading* is itself a tool (`ToolSearch`) — a lazy-loading design that a from-scratch implementation should reproduce, because it is what keeps tool schemas out of the context window (see C14).

---

### C12 — Read-only tools run concurrently; state-changing tools run sequentially; custom tools opt in via `readOnlyHint`

**Status: `OBSERVED-DOC`**
**Section: `## Tool execution` → `### Parallel tool execution`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "When Claude requests multiple tool calls in a single turn, both SDKs can run them concurrently or sequentially depending on the tool. Read-only tools (like `Read`, `Glob`, `Grep`, and MCP tools marked as read-only) can run concurrently. Tools that modify state (like `Edit`, `Write`, and `Bash`) run sequentially to avoid conflicts."

> "Custom tools default to sequential execution. To enable parallel execution for a custom tool, set `readOnlyHint` in its annotations. Both the [TypeScript] and [Python] SDKs use this field name from the MCP SDK."

**Reimplementation relevance: high.** The concurrency key is the **MCP-standard** `readOnlyHint` annotation, not a bespoke flag. A reimplementation should adopt the MCP annotation vocabulary (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) wholesale rather than inventing a parallel schema.

**Note (cross-check against the prior local CLI capture, `OBSERVED-CLI (prior capture)`):** the capture in `agent-reference-shots/area1-agent-loop/sanitized-agent-loop.jsonl` shows `PowerShell` and `Read` requested together in one assistant message, and `Glob` + `PowerShell` requested together, with results arriving in request order. Whether the harness genuinely reorders results when read-only tools truly execute concurrently is **not** established by that capture and is not stated in the documentation — treat completion order as `UNKNOWN` and correlate by `tool_use_id`.

**Clean-room opportunity:** a per-tool *concurrency class* attribute (`readOnly` vs `mutating`) that the dispatcher groups by, with read-only groups run in a bounded thread pool and mutating tools serialised on a single lane. Annotate MCP-discovered tools from their `readOnlyHint` so third-party servers get the right behaviour for free.

---

### C13 — Three orthogonal permission axes; the allow-list is not a restriction

**Status: `OBSERVED-DOC`**
**Section: `## Tool execution` → `### Tool permissions`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "Three options work together to determine what runs:
> * **`allowed_tools` / `allowedTools`** auto-approves listed tools. A read-only agent with `["Read", "Glob", "Grep"]` in its allowed tools list runs those tools without prompting, apart from reads from network paths. **Tools not listed are still available, and calls to them that need approval fall through to the permission mode and `canUseTool`.**
> * **`disallowed_tools` / `disallowedTools`** blocks listed tools, regardless of other settings.
> * **`permission_mode` / `permissionMode`** controls how much human oversight you want."

> "You can also scope individual tools with rules like `"Bash(npm *)"` to allow only specific commands."

> "When a tool is denied, Claude receives a rejection message as the tool result and typically attempts a different approach or reports that it couldn't proceed."

**Reimplementation relevance: high.** The bolded sentence is the single most commonly mis-implemented piece of this contract: **allow-listing is an approval grant, not a capability filter**. The Python reference confirms: `allowed_tools: list[str] = field(default_factory=list)` — *"Tools to auto-approve without prompting… This does not restrict Claude to only these tools."* And `disallowed_tools` — *"Tools to deny. A bare name such as `"Bash"` removes the tool from Claude's context. A scoped rule such as `"Bash(rm *)"` leaves the tool available and denies matching calls in every permission mode, including `bypassPermissions`."*

The observable difference between a bare deny and a scoped deny — tool-removed-from-schema vs. blocked-at-dispatch — is the design a reimplementation must preserve.

**Clean-room opportunity:** implement permissions as a **three-stage evaluator** with an explicit documented order: (1) deny rules, (2) allow rules, (3) mode fallback, (4) human callback. And separate *schema filtering* (does the model see the tool?) from *dispatch gating* (may it run?) as two distinct subsystems, because the docs show they are.

---

### C14 — Context consumption table: five sources, with load time and impact

**Status: `OBSERVED-DOC`**
**Section: `## The context window` → `### What consumes context`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "| Source | When it loads | Impact |
> | :- | :- | :- |
> | **System prompt** | Every request | Small fixed cost, always present |
> | **CLAUDE.md files** | Session start, via `settingSources` | Full content in every request (but prompt-cached, so only the first request pays full cost) |
> | **Tool definitions** | Every request for core built-in tools such as Bash, Read, and Edit; on demand for MCP tools and other built-in tools, which tool search defers by default | Every schema loads upfront in the cases under Configure tool search |
> | **Conversation history** | Accumulates over turns | Grows with each turn: prompts, responses, tool inputs, tool outputs |
> | **Skill descriptions** | Session start, via setting sources | Short summaries; full content loads only when invoked |"

> "Content that stays the same across turns (system prompt, tool definitions, CLAUDE.md) is automatically prompt cached, which reduces cost and latency for repeated prefixes."

**Reimplementation relevance: high.** This table is effectively a *context-budget spec*. The load-time column encodes the two-tier skill/tool design: **descriptions at session start, full content on invocation**.

---

### C15 — Automatic compaction emits a `compact_boundary` event; three customisation routes

**Status: `OBSERVED-DOC`**
**Section: `## The context window` → `### Automatic compaction`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "When the context window approaches its limit, the SDK automatically compacts the conversation: it summarizes older history to free space, keeping your most recent exchanges and key decisions intact. **The SDK emits a message with `type: "system"` and `subtype: "compact_boundary"` in the stream when this happens** (in Python this is a `SystemMessage`; in TypeScript it is a separate `SDKCompactBoundaryMessage` type)."

> "Compaction replaces older messages with a summary, so specific instructions from early in the conversation may not be preserved. Persistent rules belong in CLAUDE.md (loaded via `settingSources`) rather than in the initial prompt, because CLAUDE.md content is re-injected on every request."

> "You can customize compaction behavior in several ways:
> * **Summarization instructions in CLAUDE.md:** the compactor reads your CLAUDE.md like any other context, so you can include a section telling it what to preserve. The compactor matches on intent, so the section header is free-form.
> * **`PreCompact` hook:** Run custom logic before compaction occurs, for example to archive the full transcript. The hook receives a `trigger` field (`manual` or `auto`).
> * **Manual compaction:** Send `/compact` as a prompt string to trigger compaction on demand. Commands sent this way are ordinary SDK inputs."

**Reimplementation relevance: high.** The exact wire form is `type: "system"` + `subtype: "compact_boundary"`. The `PreCompact` hook's `trigger` field has exactly two values: `manual` or `auto`. The stated consequence — *"specific instructions from early in the conversation may not be preserved"* — is the observable failure mode a user will hit, and it is the reason the docs steer persistent rules to CLAUDE.md.

---

### C16 — The `effort` option and its five levels

**Status: `OBSERVED-DOC`**
**Section: `## Control how the loop runs` → `### Effort level`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "The `effort` option controls how much reasoning Claude applies. Lower effort levels use fewer tokens per turn and reduce cost. Not all models support the effort parameter."

> "| Level | Behavior | Good for |
> | :- | :- | :- |
> | `"low"` | Minimal reasoning, fast responses | File lookups, listing directories |
> | `"medium"` | Balanced reasoning | Routine edits, standard tasks |
> | `"high"` | Thorough analysis | Refactors, debugging |
> | `"xhigh"` | Extended reasoning depth | Coding and agentic tasks on the models that support it |
> | `"max"` | Maximum reasoning depth | Multi-step problems requiring deep analysis |"

> "If you don't set `effort`, Claude Code resolves the effort level itself, in the order [Adjust effort level] describes."

> "`effort` trades latency and token cost for reasoning depth within each response. [Extended thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking) is a separate feature that produces `thinking` blocks in the output, and the `display` field on `ThinkingConfig` for [Python](/docs/en/agent-sdk/python#thinkingconfig) or [TypeScript](/docs/en/agent-sdk/typescript#thinkingconfig) controls whether you receive their text. They are independent: you can set `effort: "low"` with extended thinking enabled, or `effort: "max"` without it."

**Reimplementation relevance: medium-high.** Five exact level strings. The doc explicitly separates `effort` from extended thinking — a distinction a reimplementation should preserve, because they are two different knobs on the same request.

---

### C17 — Six permission modes with exact names and exact semantics

**Status: `OBSERVED-DOC`**
**Section: `## Control how the loop runs` → `### Permission mode`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

Exact mode strings: **`"default"`, `"acceptEdits"`, `"plan"`, `"dontAsk"`, `"auto"`, `"bypassPermissions"`**. Verbatim excerpts:

> `"default"` — "Tool calls that need approval and aren't covered by allow rules trigger your `canUseTool` callback; no callback means deny"

> `"acceptEdits"` — "Auto-approves file edits and common filesystem commands (`mkdir`, `touch`, `mv`, `cp`, etc.); other Bash commands follow default rules"

> `"plan"` — "Claude explores and plans without editing your source files; file edits are never auto-approved and prompt through your `canUseTool` callback"

> `"dontAsk"` — "Never prompts. Tools pre-approved by permission rules run, and so do calls that need no approval in `default` mode, such as file reads inside your working directories. Every call that would otherwise prompt is denied, though a mod you installed can still approve some of those calls. `AskUserQuestion`, connector tools your organization set to `ask`, MCP tools marked `requiresUserInteraction`, and reads from network paths are denied even if you've allowed them"

> `"auto"` — "Uses a model classifier to review actions such as shell commands and network requests, allowing or blocking each one it reviews."

> `"bypassPermissions"` — "Runs all allowed tools without asking, except tools matched by an explicit `ask` rule, connector tools your organization set to `ask`, and tools that require user interaction. The cross-session messaging safeguards still apply."

> "See [How permissions are evaluated](/docs/en/agent-sdk/permissions#how-permissions-are-evaluated) for the precedence order. In the TypeScript SDK, also requires `allowDangerouslySkipPermissions: true` in `options`. Can't be used when running as root on Unix. Use only in isolated environments where the agent's actions can't affect systems you care about"

**Reimplementation relevance: high.** The `dontAsk` mode's *deny list* is a precise, implementable set: `AskUserQuestion`, org-set-`ask` connector tools, MCP tools marked `requiresUserInteraction`, and network-path reads — denied *even if allowed*. The `bypassPermissions` guard requires a second explicit boolean (`allowDangerouslySkipPermissions: true`) — a two-key "dangerous" interlock, worth copying exactly as a pattern.

**Clean-room opportunity:** model permission modes as an **enum with a declarative capability matrix** (per-mode: auto-approve set, deny set, whether human callback is reachable, whether a second confirmation flag is required). The "second interlock boolean" is a cheap, high-value safety pattern: a mode that disables all prompts should not be reachable by a single string.

---

### C18 — Turn cap counts tool-use turns only; budget cap is checked *after* responses arrive

**Status: `OBSERVED-DOC`**
**Section: `## Control how the loop runs` → `### Turns and budget`, `#### Budget headroom`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "You can cap the loop with `max_turns` / `maxTurns`, which counts tool-use turns only. For example, `max_turns=2` in the loop above would have stopped before the edit step. You can also use `max_budget_usd` / `maxBudgetUsd` to cap turns based on a spend threshold."

> "| Max turns (`max_turns` / `maxTurns`) | Maximum tool-use round trips | No limit |
> | Max budget (`max_budget_usd` / `maxBudgetUsd`) | Estimated spend at which the loop stops | No limit |"

> "Claude Code compares spend with the `max_budget_usd` / `maxBudgetUsd` cap after model responses arrive, because each response's cost comes from the token usage the API returns with it. The response that reaches the cap still completes and counts toward `total_cost_usd`. **Spend can therefore pass the cap by up to the cost of that one response**, plus anything that subagents still running at that moment spend before they stop. Leave headroom for this when you set the cap."

> "The budget cap covers subagents: their spend counts toward the total. Once spend reaches the cap, spawning another subagent fails with `Budget limit reached`, and Claude Code stops any background subagents still running. The cap-enforcement behaviors require Claude Code v2.1.217 or later."

> "With streaming input, a message that is still queued when a turn ends at the max-turns limit stays queued. Claude Code doesn't add it to that turn's last model call. It starts a new turn for the message, and the max-turns count starts over for that turn. The budget total keeps accumulating across messages, and once spend reaches `maxBudgetUsd`, later messages in the same conversation end with the `error_max_budget_usd` result. A `/clear` starts the budget over."

**Reimplementation relevance: high.** Three separately implementable behaviours: (a) turn counting excludes the final text-only turn; (b) the budget is an **overshoot-tolerant** check performed post-response, so a hard ceiling is not achievable and the docs say so explicitly; (c) the turn counter **resets per queued message** while the budget total does not.

---

### C19 — Session identity: `ResultMessage.session_id`, and its location differs per SDK

**Status: `OBSERVED-DOC`**
**Section: `## Sessions and continuity`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "Each interaction with the SDK creates or continues a session. Capture the session ID from `ResultMessage.session_id` (available in both SDKs) to resume later. **The TypeScript SDK also exposes it as a direct field on the init `SystemMessage`; in Python it's nested in `SystemMessage.data`.**"

> "When you resume, the full context from previous turns is restored: files that were read, analysis that was performed, and actions that were taken. You can also fork a session to branch into a different approach without modifying the original."

> "To resume sessions across stateless containers or serverless hosts, pass a `session_store` / `sessionStore` adapter so the SDK mirrors transcripts to your own backend and another host can resume them. **The Claude Code subprocess still writes to local disk first.**"

**Reimplementation relevance: high.** The Python location asymmetry (`SystemMessage.data` vs. a direct field) is a concrete trap. The dual-write statement ("subprocess still writes to local disk first") is a precise architectural constraint.

---

### C20 — Hooks run outside the agent's context and can short-circuit the loop

**Status: `OBSERVED-DOC`**
**Section: `## Hooks`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "| Hook | When it fires | Common uses |
> | :- | :- | :- |
> | `PreToolUse` | Before a tool executes | Validate inputs, block dangerous commands |
> | `PostToolUse` | After a tool returns | Audit outputs, trigger side effects |
> | `UserPromptSubmit` | When a prompt is sent | Inject additional context into prompts |
> | `Stop` | When the agent finishes | Validate the result, save session state |
> | `SubagentStart` / `SubagentStop` | When a subagent spawns or completes | Track and aggregate parallel task results |
> | `PreCompact` | Before context compaction | Archive full transcript before summarizing |"

> "Hooks run in your application process, not inside the agent's context window, so they don't consume context. Hooks can also short-circuit the loop: a `PreToolUse` hook that rejects a tool call prevents it from executing, and Claude receives the rejection message instead."

**Reimplementation relevance: high.** The six exact hook names are the contract. Two properties are architecturally important and worth copying: hooks are **out-of-band** (do not consume model context), and `PreToolUse` can **reject** — the rejection becomes the tool result the model sees.

---

### C21 — The init message is a machine-readable manifest of the effective session

**Status: `OBSERVED-DOC`**
**Section: `## Message types`** (the `"init"` subtype), corroborated by the TypeScript reference
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>, <https://code.claude.com/docs/en/agent-sdk/typescript.md>**

The agent-loop page says only: *"`"init"`: session metadata for the run."*

The TypeScript reference (`agent-sdk-typescript.md`) gives the full shape:

> "type SDKSystemMessage = {
>   type: "system";
>   subtype: "init";
>   uuid: UUID;
>   session_id: string;
>   agents?: string[];
>   apiKeySource: ApiKeySource;
>   betas?: string[];
>   claude_code_version: string;
>   cwd: string;
>   tools: string[];
>   mcp_servers: { name: string; status: string; source?: string; }[];
>   model: string;
>   permissionMode: PermissionMode;
>   slash_commands: string[];
>   terminal_slash_commands?: string[];
>   output_style: string;
>   skills: string[];
>   plugins: { name: string; path: string; }[];
>   plugin_errors?: { plugin: string; type: string; message: string; path?: string; }[];
>   fast_mode_state?: FastModeState;
>   fast_mode_disabled_reason?: FastModeDisabledReason;
>   effort?: "low" | "medium" | "high" | "xhigh" | "max" | null;
>   capabilities?: string[];
> };"

> "The `capabilities` array names the protocol behaviors this CLI implements, so you can feature-detect instead of comparing `claude_code_version` strings. It is an open set: ignore values you don't recognize, and check for the specific capability whose behavior you rely on."

Named capabilities in the reference: `interrupt_receipt_v1`, `interrupt_cancel_queued_v1`, `sdk_mcp_manifests`, `sdk_mcp_tools_list_changed`.

**Reimplementation relevance: foundational.** This is the single most valuable clean-room artefact in the whole study: an **effective-configuration manifest emitted at runtime**. A reimplementation should emit an equivalent init event listing the resolved tools, MCP servers and their status, model, permission mode, skills, plugins, slash commands, and a capability list. The **capability-string feature-detection** pattern is directly adoptable: an open set of named strings, unknown values ignored.

**Cross-check (`OBSERVED-CLI (prior capture)`):** the earlier local capture in `agent-reference-shots/area1-agent-loop/` confirms the same fields are actually emitted by the CLI at runtime — `cwd`, `session_id`, a `tools` array, `mcp_servers` with `status: "pending"` and `source`, `model`, `permissionMode`, `claude_code_version`, `agents`, `output_style`, `additional_directories`, `slash_commands`. So the documentation and the running product agree.

---

### C22 — The init message is emitted *after* startup hook lifecycle messages

**Status: `OBSERVED-DOC`**
**Section: `## Message types`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "`"init"`: session metadata for the run. When a `SessionStart` or `Setup` hook runs during session startup, its hook lifecycle messages arrive before the `init` message"

**Reimplementation relevance: medium-high.** A subtle ordering guarantee: the manifest is *not* the first event. A reimplementation that emits init first and then runs startup hooks will produce a different observable ordering.

---

### C23 — `StreamEvent` carries raw API events; `includePartialMessages` is the switch

**Status: `OBSERVED-DOC`**
**Section: `### SDKPartialAssistantMessage` (TypeScript reference)**
**Source: <https://code.claude.com/docs/en/agent-sdk/typescript.md>**

Already covered by C6; the additional concrete detail from the TypeScript reference is the exact field name of the stream event type:

> "type SDKPartialAssistantMessage = {
>   type: "stream_event";
>   event: BetaRawMessageStreamEvent; // From Anthropic SDK
>   parent_tool_use_id: string | null;
>   uuid: UUID;
>   session_id: string;
>   ttft_ms?: number; // Time to first token in ms, present only on message_start events
>   user_message_uuid?: string;
>   user_message_uuids?: string[];
>   resume_reason?: string;
> };"

and: *"The `parent_tool_use_id` field is always `null`: stream events are emitted for the main session only."*

**Reimplementation relevance: medium.** The discriminator string is `"stream_event"`.

---

### C24 — `total_cost_usd` vs `modelUsage` / `model_usage`: whole-tree accounting requires the latter

**Status: `OBSERVED-DOC`**
**Section: `## Handle the result`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "The `usage` field covers only the main agent loop. Use `modelUsage`, or `model_usage` in Python, for whole-tree token and cost accounting."

**Reimplementation relevance: medium-high.** Two usage views with different scopes, and the naming differs per SDK (`modelUsage` camelCase vs `model_usage` snake_case). The Python `ResultMessage` dataclass lists `model_usage: dict[str, ModelUsage] | None = None` and `usage: dict[str, Any] | None = None` separately.

---

### C25 — Python `total_cost_usd`, `usage`, and `model_usage` are optional — a null-check hazard

**Status: `OBSERVED-DOC`**
**Section: `## Handle the result`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "In Python, `total_cost_usd`, `usage`, and `model_usage` are typed as optional, so check that they aren't `None` before you read them."

The Python reference confirms the dataclass fields: `total_cost_usd: float | None = None`, `usage: dict[str, Any] | None = None`, `model_usage: dict[str, ModelUsage] | None = None`.

**Reimplementation relevance: medium.** Cross-SDK parity hazard: the same field is non-optional in TypeScript (`total_cost_usd: number`, `usage: NonNullableUsage`) and optional in Python.

---

### C26 — Content-block shapes are identical across SDKs (`TextBlock`, `ToolUseBlock`, `ToolResultBlock`)

**Status: `OBSERVED-DOC`** (from the Python reference, cited for the exact field names)
**Section: `### TextBlock`, `### ToolUseBlock`, `### ToolResultBlock`**
**Source: <https://code.claude.com/docs/en/agent-sdk/python.md>**

> "```python
> @dataclass
> class TextBlock:
>     text: str
>
> @dataclass
> class ToolUseBlock:
>     id: str
>     name: str
>     input: dict[str, Any]
>
> @dataclass
> class ToolResultBlock:
>     tool_use_id: str
>     content: str | list[dict[str, Any]] | None = None
>     is_error: bool | None = None
> ```"

**Reimplementation relevance: foundational.** `ToolUseBlock.id` ↔ `ToolResultBlock.tool_use_id` is the correlation key between a request and its result. `ToolResultBlock.is_error` is the per-call failure flag, distinct from the run-level `is_error` on the result message.

**Cross-check (`OBSERVED-CLI (prior capture)`):** the earlier local capture confirms this key pairing in practice — every `tool_use` carries an `id`, the matching `tool_result` returns the same value in `tool_use_id`, and a denied call still occupies a `tool_result` slot with `is_error: true`.

---

### C27 — Tool denial is delivered to the model as a tool result, not as a loop error

**Status: `OBSERVED-DOC`**
**Section: `## Tool execution` → `### Tool permissions`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "When a tool is denied, Claude receives a rejection message as the tool result and typically attempts a different approach or reports that it couldn't proceed."

Corroborated in the hooks section: *"a `PreToolUse` hook that rejects a tool call prevents it from executing, and Claude receives the rejection message instead."*

**Reimplementation relevance: high.** A denial is a *data* event on the tool-result channel, not a control-flow exception. This matches the earlier local observation that a session in which every tool call was denied still reports `subtype: "success"`.

---

### C28 — `effort` is settable per session and per subagent

**Status: `OBSERVED-DOC`**
**Section: `## Control how the loop runs` → `### Effort level`**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "Set `effort` in the top-level `query()` options for the whole session, or per subagent with the `effort` field on `AgentDefinition` to override the session level."

**Reimplementation relevance: medium.** A per-agent override with session-level fallback. The `AgentDefinition` type is documented at `/docs/en/agent-sdk/subagents#agentdefinition-configuration` (not fetched in this pass — see §5).

---

### C29 — The SDK bundles a native Claude Code binary; the loop runs in a subprocess

**Status: `OBSERVED-DOC`**
**Section: (untitled preamble, before `## The loop at a glance`)**
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

> "Both the TypeScript and Python SDKs bundle a native Claude Code binary, so most installs need no separate Claude Code install."

Corroborated in the TypeScript reference: *"`claude_code_version` is the Claude Code version of the process that runs the session's turns."* And in the agent-loop page's budget section: *"The underlying Claude Code process also exits with a nonzero code."*

**Reimplementation relevance: high (architecturally).** The SDK is a **subprocess protocol**, not an in-process library. The observable consequence: the loop's event stream crosses a process boundary, which is why the event shape is a serialisable discriminated union rather than object references. A clean-room implementation can and should choose a different internal architecture — but if it wants SDK-compatibility of the *event contract*, it must emit the same serialisable shape.

---

### C30 — The TypeScript SDK surfaces additional event types beyond the five core ones

**Status: `OBSERVED-DOC`**
**Section: `### SDKMessage` (TypeScript reference)**
**Source: <https://code.claude.com/docs/en/agent-sdk/typescript.md>**

The documented union has **36 members** (verified by extracting every `SDK*` identifier from the union body — 37 unique names, minus the union type name `SDKMessage` itself):

> "type SDKMessage = | SDKAssistantMessage | SDKUserMessage | SDKUserMessageReplay | SDKResultMessage | SDKSystemMessage | SDKPartialAssistantMessage | SDKCompactBoundaryMessage | SDKStatusMessage | SDKLocalCommandOutputMessage | SDKHookStartedMessage | SDKHookProgressMessage | SDKHookResponseMessage | SDKPluginInstallMessage | SDKToolProgressMessage | SDKAuthStatusMessage | SDKTaskNotificationMessage | SDKTaskStartedMessage | SDKTaskProgressMessage | SDKTaskUpdatedMessage | SDKBackgroundTasksChangedMessage | SDKThinkingTokensMessage | SDKSessionStateChangedMessage | SDKWorkerShuttingDownMessage | SDKCommandsChangedMessage | SDKNotificationMessage | SDKFilesPersistedEvent | SDKToolUseSummaryMessage | SDKMemoryRecallMessage | SDKRateLimitEvent | SDKElicitationCompleteMessage | SDKPermissionDeniedMessage | SDKPromptSuggestionMessage | SDKAPIRetryMessage | SDKMirrorErrorMessage | SDKInformationalMessage | SDKConversationResetMessage;"

Note the exact type names that map to the agent-loop page's prose: `SDKCompactBoundaryMessage` (the `compact_boundary` subtype), `SDKWorkerShuttingDownMessage` (the `worker_shutting_down` subtype), `SDKInformationalMessage` (the `informational` subtype), `SDKPromptSuggestionMessage` (the trailing `prompt_suggestion` event), `SDKPermissionDeniedMessage`, `SDKAPIRetryMessage`.

**Reimplementation relevance: medium-high.** The five core types are the *minimum*; the documented union is 38. A reimplementation that emits only the five will still drive a loop correctly, but will not expose hook progress, task lifecycle, permission denials, API retries, or rate-limit events. Note the tension with the agent-loop page's own statement: *"These five types cover the full agent loop lifecycle. Both SDKs also yield observability events such as rate-limit status and task notifications that are not required to drive the loop."* — i.e. **five drive the loop; the rest are observability**.

**Cross-check (`OBSERVED-CLI (prior capture)`):** the local capture shows `system/permission_denied`, `system/task_started`, `system/task_notification` events in the CLI's own stream-json output, confirming the observability tier exists in the shipped product.

### C31 — The SDK's documented tool roster is a *subset* of the CLI's observed tool set

**Status: `OBSERVED-DOC` (the SDK roster) + `OBSERVED-CLI (prior capture)` (the CLI roster)**
**Section: `## Tool execution` → `### Built-in tools`**, cross-checked against the init event in `agent-reference-shots/area1-agent-loop/sanitized-agent-loop.jsonl`
**Source: <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>**

The agent-loop page lists 14 built-in tools:

> "| **File operations** | `Read`, `Edit`, `Write` | Read, modify, and create files |
> | **Search** | `Glob`, `Grep` | Find files by pattern, search content with regex |
> | **Execution** | `Bash` | Run shell commands, scripts, git operations |
> | **Web** | `WebSearch`, `WebFetch` | Search the web, fetch and parse pages |
> | **Discovery** | `ToolSearch` | Dynamically find and load tools on-demand instead of preloading all of them |
> | **Orchestration** | `Agent`, `Skill`, `AskUserQuestion`, `TaskCreate`, `TaskUpdate` | Spawn subagents, invoke skills, ask the user, track tasks |"

The `system/init` event captured from the local CLI on 2026-10-21 lists **27** tools (verified programmatically: `len(init.tools) == 27`, no truncation marker present; the same event records `slash_commands_count: 53`):

```
['Task', 'Bash', 'CronCreate', 'CronDelete', 'CronList', 'DesignSync', 'Edit',
 'EnterWorktree', 'ExitWorktree', 'Glob', 'Grep', 'ListAgents', 'Monitor',
 'NotebookEdit', 'PowerShell', 'PushNotification', 'Read', 'ReportFindings',
 'ScheduleWakeup', 'SendMessage', 'Skill', 'TaskStop', 'ToolSearch',
 'WebFetch', 'WebSearch', 'Workflow', 'Write']
```

Also captured from that same init event: `mcp_servers: [{'name': 'rea', 'status': 'pending', 'source': 'user'}]`, `permissionMode: 'default'`, plus `cwd`, `session_id`, `model`, `claude_code_version`, `agents`, `additional_directories`, `output_style`, and a `slash_commands` collection.

**Interpretation (`INFERRED`).** The two lists differ in *kind*, not in conflict. The SDK page enumerates the **categories** of tool the SDK exposes, with a representative per category; the CLI init event enumerates the **actual schema handed to the model** in this session. The CLI's set is a superset that adds platform- and product-specific tools (`PowerShell` on Windows, `Cron*`, `DesignSync`, `Monitor`, `NotebookEdit`, `PushNotification`, `ReportFindings`, `ScheduleWakeup`, `SendMessage`, `Task`, `TaskStop`, `Workflow`, `EnterWorktree`/`ExitWorktree`, `ListAgents`) and uses `Task` rather than the page's `TaskCreate`/`TaskUpdate`/`Agent`/`AskUserQuestion` names. Notably the **CLI list contains no `Agent` and no `AskUserQuestion`** in this session — those are documented SDK-surface names, and their absence from the observed schema is a real, unexplained difference (see U9/U13).

Reasoning: the page states the SDK *"includes the same tools that power Claude Code"*, and the observed CLI schema is the concrete realisation of that claim for this platform and configuration. The naming differences (`Agent` vs `Task`; `TaskCreate`/`TaskUpdate` vs. a single `Task`) are most plausibly SDK-facing aliases for the same underlying capability, since the page separately notes that *"Claude Code provides `TaskCreate` and `TaskUpdate` only when you opt in"* on models that lack native task tracking — i.e. the names are a presentation layer over a capability that may or may not be present.

**Reimplementation relevance: high.** The lesson is not the roster but the **shape**: the effective tool schema is determined at runtime and published in the init manifest. A reimplementation must therefore (a) decide its tool roster per platform, and (b) publish it in the init event so consumers can feature-detect rather than hard-code a list.

---

## 3. Capability table

| # | Capability | Contract (exact names) | Classification | Needed for a from-scratch loop? |
| :- | :- | :- | :- | :- |
| 1 | Turn cycle | prompt → evaluate → tool-execute → repeat; ends on a no-tool-call assistant message | `OBSERVED-DOC` | **Yes** |
| 2 | Core message types | `SystemMessage`, `AssistantMessage`, `UserMessage`, `StreamEvent`, `ResultMessage` | `OBSERVED-DOC` | **Yes** |
| 3 | System subtypes | `init`, `compact_boundary`, `informational`, `worker_shutting_down` | `OBSERVED-DOC` | **Yes** |
| 4 | Per-block assistant messages | one message per content block; shared message id within a response | `OBSERVED-DOC` | **Yes** |
| 5 | TS content nesting | blocks at `message.message.content`, not `message.content` | `OBSERVED-DOC` | Yes (TS only) |
| 6 | Py session id location | `SystemMessage.data` vs. TS direct field | `OBSERVED-DOC` | Yes (Py only) |
| 7 | Result subtypes | `success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries` | `OBSERVED-DOC` | **Yes** |
| 8 | `result` only on success | "always check the subtype before reading it" | `OBSERVED-DOC` | **Yes** |
| 9 | Stop reasons | `end_turn`, `max_tokens`, `refusal`, `null` on crash | `OBSERVED-DOC` | **Yes** |
| 10 | Dual signalling | single-shot `query()` yields result **then** raises; transport failures yield no result | `OBSERVED-DOC` | **Yes** |
| 11 | Tool roster | `Read` `Edit` `Write` `Glob` `Grep` `Bash` `WebSearch` `WebFetch` `ToolSearch` `Agent` `Skill` `AskUserQuestion` `TaskCreate` `TaskUpdate` | `OBSERVED-DOC` | **Yes** |
| 12 | Concurrency classes | read-only concurrent; `Edit`/`Write`/`Bash` sequential; custom tool opts in via `readOnlyHint` | `OBSERVED-DOC` | **Yes** |
| 13 | Correlation key | `ToolUseBlock.id` ↔ `ToolResultBlock.tool_use_id` | `OBSERVED-DOC` | **Yes** |
| 14 | Denial as data | rejection delivered as the tool result content | `OBSERVED-DOC` | **Yes** |
| 15 | Permission axes | `allowed_tools`/`allowedTools`, `disallowed_tools`/`disallowedTools`, `permission_mode`/`permissionMode` | `OBSERVED-DOC` | **Yes** |
| 16 | Allow ≠ restrict | unlisted tools still available; fall through to mode + `canUseTool` | `OBSERVED-DOC` | **Yes** |
| 17 | Scoped rules | `"Bash(npm *)"` | `OBSERVED-DOC` | Yes |
| 18 | Permission modes | `default` `acceptEdits` `plan` `dontAsk` `auto` `bypassPermissions` | `OBSERVED-DOC` | **Yes** |
| 19 | Dangerous interlock | `allowDangerouslySkipPermissions: true` required for `bypassPermissions` (TS) | `OBSERVED-DOC` | Yes (recommended) |
| 20 | `dontAsk` deny set | `AskUserQuestion`, org-`ask` connector tools, `requiresUserInteraction` MCP tools, network-path reads | `OBSERVED-DOC` | Yes |
| 21 | Turn cap | `max_turns`/`maxTurns` — counts tool-use turns only | `OBSERVED-DOC` | **Yes** |
| 22 | Budget cap | `max_budget_usd`/`maxBudgetUsd` — checked after responses; overshoot tolerated | `OBSERVED-DOC` | **Yes** |
| 23 | Budget covers subagents | subagent spend counts; spawn fails with `Budget limit reached` | `OBSERVED-DOC` | Yes |
| 24 | Budget reset | `/clear` starts the budget over | `OBSERVED-DOC` | Medium |
| 25 | Effort levels | `low` `medium` `high` `xhigh` `max` | `OBSERVED-DOC` | Medium |
| 26 | Effort override | per-subagent `effort` on `AgentDefinition` | `OBSERVED-DOC` | Medium |
| 27 | Context sources | system prompt, CLAUDE.md, tool definitions, conversation history, skill descriptions | `OBSERVED-DOC` | **Yes** |
| 28 | Compaction event | `type: "system"` + `subtype: "compact_boundary"` | `OBSERVED-DOC` | **Yes** |
| 29 | Compaction triggers | CLAUDE.md instructions, `PreCompact` hook (`trigger`: `manual`/`auto`), `/compact` | `OBSERVED-DOC` | Yes |
| 30 | Hook names | `PreToolUse` `PostToolUse` `UserPromptSubmit` `Stop` `SubagentStart`/`SubagentStop` `PreCompact` | `OBSERVED-DOC` | **Yes** |
| 31 | Hooks out-of-band | run in the app process; do not consume context | `OBSERVED-DOC` | Yes |
| 32 | Init manifest | `tools`, `mcp_servers`(+`status`,`source`), `model`, `permissionMode`, `skills`, `plugins`, `slash_commands`, `cwd`, `claude_code_version` | `OBSERVED-DOC` | **Yes** |
| 33 | Capability negotiation | `capabilities: string[]` open set, feature-detect not version-compare | `OBSERVED-DOC` | **Yes** (recommended) |
| 34 | Session id | `ResultMessage.session_id` (both); direct on TS init | `OBSERVED-DOC` | **Yes** |
| 35 | Session persistence | `session_store`/`sessionStore` adapter; local disk written first | `OBSERVED-DOC` | Yes |
| 36 | Fork | fork a session to branch without modifying the original | `OBSERVED-DOC` | Yes |
| 37 | Usage scopes | `usage` = main loop; `modelUsage`/`model_usage` = whole tree | `OBSERVED-DOC` | **Yes** |
| 38 | Python optionality | `total_cost_usd`, `usage`, `model_usage` may be `None` | `OBSERVED-DOC` | Yes (Py only) |
| 39 | Partial streaming | `include_partial_messages` / `includePartialMessages`; `type: "stream_event"` | `OBSERVED-DOC` | Medium |
| 40 | Trailing events | `prompt_suggestion` etc. may arrive after the result; iterate to completion | `OBSERVED-DOC` | **Yes** |
| 41 | Full event union | 36 documented TypeScript `SDKMessage` members | `OBSERVED-DOC` | Optional (observability) |
| 42 | Process boundary | SDK bundles a native Claude Code binary; loop runs in a subprocess | `OBSERVED-DOC` | Architecture note |
| 43 | `settingSources` | controls which filesystem settings load; `CLAUDE.md` at session start | `OBSERVED-DOC` | Yes |
| 44 | Effective tool schema | 27 tools published in the CLI's `system/init`; the SDK page names 14 categories | `OBSERVED-CLI (prior capture)` + `OBSERVED-DOC` | **Yes** |
| 45 | MCP server status in init | `mcp_servers: [{ name, status: "pending", source: "user" }]` | `OBSERVED-CLI (prior capture)` | Yes |

---

## 4. Dependencies

| Dependency | Needed for | Source of truth |
| :- | :- | :- |
| **A model provider** producing assistant turns with tool-use blocks | Every turn | Anthropic API or an Anthropic-compatible endpoint |
| **Token usage reported alongside each response** | `total_cost_usd`, budget enforcement, `usage` | The API's response usage object — the docs state the cap is checked *"after model responses arrive, because each response's cost comes from the token usage the API returns with it"* |
| **A filesystem** for `CLAUDE.md` discovery and transcript persistence | Context loading, session resume | Local disk (the CLI subprocess *"still writes to local disk first"*) |
| **Shell / process execution** | The `Bash` tool | OS; the CLI runs commands as child processes |
| **An MCP transport** for MCP tools | `mcp_servers` entries and `readOnlyHint`-annotated tools | MCP server(s) over stdio/HTTP |
| **Hook host** | `PreToolUse` etc. | The application process, not the model context |
| **An Anthropic SDK type package** (`BetaMessage`, `BetaRawMessageStreamEvent`) | Only if reproducing the TypeScript type shapes exactly | `@anthropic-ai/sdk` — **not** required for a behavioural reimplementation |

**No Anthropic account, subscription, or network access to `api.anthropic.com` is required to implement the loop itself** — only a model endpoint. This matches the observation elsewhere in this evidence tree that on a custom `ANTHROPIC_BASE_URL` the loop still runs and the event stream is fully populated.

---

## 5. Limitations and unresolved questions (UNKNOWN)

| # | Question | Why it is unresolved |
| :- | :- | :- |
| U1 | Does the harness ever *reorder* tool results relative to request order? | The docs state the concurrency *policy* (read-only concurrent, mutating sequential) but never specify result emission order. The local capture shows request order, but its read-only calls were effectively instantaneous, so it does not discriminate. **Correlate by `tool_use_id`, never by position.** |
| U2 | What exactly is in `SDKCompactBoundaryMessage` beyond the type and subtype? | The agent-loop page names it and the event shape; the full field list lives in the TypeScript reference's own section, which was not read in this pass. |
| U3 | The exact contents of the `SDKPermissionDeniedMessage` and `SDKAPIRetryMessage` payloads | Named in the union; field lists are in the TypeScript reference sections not read here. The prior local capture *did* observe `permission_denied` with `tool_name`, `tool_use_id`, `decision_reason_type`, `decision_reason`. |
| U4 | Whether `num_turns` counts assistant messages, tool-use rounds, or model calls | The page says `max_turns` *"counts tool-use turns only"* and a turn is *"one round trip inside the loop"*. The prior local capture saw `num_turns: 13` for 12 tool calls across ~14 assistant messages — consistent with, but not proof of, "evaluate/execute cycles". |
| U5 | `AgentDefinition` field list (for the per-subagent `effort` override) | Cited to `/docs/en/agent-sdk/subagents#agentdefinition-configuration`, not fetched in this pass. |
| U6 | The `canUseTool` callback signature and return contract | Referenced by name only; the shape lives in `/docs/en/agent-sdk/permissions`, not fetched here. |
| U7 | The `PermissionMode` enum's full member list on the Python side | The agent-loop page names six modes for the SDK; the Python reference may define additional aliases. |
| U8 | The full `tools` registry and per-tool JSON schemas | Not enumerated on this page; only the tool *names* and the read/search/execute/web/orchestration categories are given. |
| U9 | Whether `ToolSearch` is always available or gated by model/plan | The page describes it as a built-in Discovery tool; the CLI's observed init schema **does** contain `ToolSearch`, so availability is confirmed for that session — but whether it is model- or plan-gated is not documented on this page. |
| U13 | Why the CLI's observed tool schema has **no `Agent`** and **no `AskUserQuestion`**, and uses `Task` rather than `TaskCreate`/`TaskUpdate` | The SDK page names all four as built-in; the observed CLI schema names none of them in that form. The aliasing is a reasonable inference (C31) but is **not documented**. `Task` and `Skill` and `ToolSearch` do appear. |
| U10 | Behaviour of the loop when the *model* returns zero content blocks | Not documented. |
| U11 | Behaviour when the model emits a tool call for a tool that does not exist | Not documented on this page. |
| U12 | Whether the `informational` subtype's text has a structured payload | Described only as *"plain-text status banners from the loop."* |

---

## 6. Clean-room implementation opportunity

The observable contract of the agent loop is a **serialisable, discriminated event stream over a process boundary**, plus a **declarative set of control options**. Both halves are independently designable. Nothing below requires reading or reproducing any Anthropic code.

### 6.1 The event contract

Define your own event union with a small, stable discriminator set. The minimum that preserves every documented behaviour:

```
Event = SystemEvent | AssistantEvent | UserEvent | StreamEvent | ResultEvent
```

with:
- `SystemEvent { type: "system", subtype: "init" | "compact_boundary" | "informational" | "worker_shutting_down", … }`
- `AssistantEvent { …, content_block: TextBlock | ToolUseBlock | ThinkingBlock }` — **one per content block**, carrying a `response_id` shared across blocks of one model response.
- `UserEvent { …, tool_use_id?: string, tool_result?: ToolResultBlock }` — one channel for tool results *and* mid-loop user input; discriminate on `tool_use_id` / `tool_result` presence.
- `StreamEvent { type: "stream_event", raw: … }` — opt-in only.
- `ResultEvent { type: "result", subtype: <your five-state vocabulary>, result?: string, total_cost_usd, usage, num_turns, session_id, stop_reason }`.

**Non-negotiable properties to preserve** (all documented, all testable):
1. `result` is populated **only** on the success subtype; every other subtype omits it.
2. `total_cost_usd`, `usage`, `num_turns`, `session_id` are present on **every** result subtype.
3. The result event is **not** the end of the stream — trailing observability events may follow. Consumers must drain.
4. Per-block assistant events share a response identifier so a consumer can reassemble one model response.
5. The init manifest is emitted **after** any startup-hook lifecycle events.

### 6.2 The control options

Model options as a plain dataclass / config object with independent fields; nothing requires the SDK's exact naming (though matching the *snake_case ↔ camelCase* pairing convention is a cheap compatibility win if you ship two language bindings):

`max_turns` · `max_budget_usd` · `effort` · `permission_mode` · `allowed_tools` · `disallowed_tools` · `can_use_tool` (callback) · `include_partial_messages` · `setting_sources` · `session_store` · `model`.

### 6.3 The dispatcher

- **Concurrency classes.** Give every tool a `read_only: bool`. Group a turn's tool calls by class: run the read-only group concurrently in a bounded pool, run the mutating group serially on a single lane, and interleave the two groups so a mutating call does not start while a read-only call it might race with is still in flight. For MCP tools, derive `read_only` from the server's declared `readOnlyHint` annotation — adopting MCP's existing annotation vocabulary rather than inventing a parallel schema.
- **Correlation.** Every tool call gets an opaque id; the result carries the same id. Never correlate by array position.
- **Denials are data.** A denied call produces a *tool-result event* with `is_error: true` and an explanatory message, exactly like a failed call. It never raises out of the dispatcher. The model then sees the rejection as content and can adapt.

### 6.4 The permission evaluator

Implement as an explicit ordered evaluator, with the order written down and tested:

1. **Deny rules** — a bare-name deny removes the tool from the schema; a scoped deny (`Bash(rm *)`) keeps it visible but blocks matching calls in *every* mode.
2. **Allow rules** — `allowed_tools` membership and scoped allow patterns (`Bash(npm *)`) auto-approve. Membership is an approval grant, **not** a capability filter: unlisted tools remain available and fall through.
3. **Mode** — the active `permission_mode` supplies its own auto-approve set (e.g. `acceptEdits` auto-approves file edits and `mkdir`/`touch`/`mv`/`cp`), its own hard-deny set (e.g. `dontAsk` denies `AskUserQuestion`, org-`ask` connector tools, `requiresUserInteraction` MCP tools, network-path reads), and whether a human callback is reachable.
4. **Human callback** — if the mode and the rules do not decide, call `can_use_tool`. If no callback is registered, **deny** (this is the documented `"default"` behaviour: *"no callback means deny"*).
5. **Dangerous interlock** — a mode that disables all prompting should require a second, separate opt-in flag before it activates, and should refuse to activate as root on Unix.

### 6.5 Limits and budget

- Count a turn as one evaluate/execute round trip; **do not** count the final text-only response as a turn (the doc's example: `max_turns=2` stopped before the edit step).
- Evaluate the budget **after** each response arrives, using the usage the provider returned for that response; let the triggering response complete and count its cost; document that the cap can be overshot by one response. Surface a "budget headroom" note in your own docs.
- Include subagent spend in the same total; refuse new subagent spawns once the cap is reached and stop running background subagents.
- On a turn-cap stop in a queued-input session, keep the queued message queued, reset the turn counter for its new turn, and **keep accumulating** the budget total.

### 6.6 Context management

- Maintain an explicit budget accounting with per-source classification (system prompt / project instructions / tool schemas / history / skill summaries), since the documented table is effectively a spec.
- Load skill and tool *descriptions* at session start and *bodies* on invocation.
- Compact by replacing older turns with a summary while retaining recent exchanges, and emit the boundary event so observers can see it happen.
- Provide three compaction customisation routes: a project-instruction section the compactor reads, a pre-compaction hook with a `trigger` field distinguishing manual from automatic, and a manual compaction command.
- Keep persistent rules in a project-instruction file that is re-injected every request — the documented reason is that summary compaction loses early conversational instructions.

### 6.7 Init manifest + capability negotiation

Emit an init event listing the *effective* configuration: tools in the schema, external servers with a status and a source, model, permission mode, skills, plugins, slash commands, working directory, and a client version. Then add a **capabilities array of open-set strings** — feature-detect by capability name rather than by comparing version strings, and ignore unknown values. This is the single highest-leverage compatibility decision in the whole design, because it lets a client degrade gracefully against an older or newer engine.

### 6.8 Result semantics

- Emit a terminal result event carrying the five-way subtype vocabulary, cost, usage, turn count, session id, and stop reason.
- Then, in the single-shot mode, **raise** a dedicated terminal-outcome exception that carries the same payload, so a caller who ignores events still fails loudly; in the streaming mode, keep the session alive.
- Distinguish *agent failure* (a result event exists) from *transport failure* (no result event) with distinct exception types. This is the asymmetry the docs call out twice.

### 6.9 What NOT to copy

- The exact system-prompt text, the internal prompt-assembly sentinel names, the model-routing logic, the auto-mode classifier's rule text, or any part of the proprietary binary. These are **policy**, not **interface**.
- Anthropic's exact TypeScript/Python class layouts. Reproduce the *observable* field names and nesting where compatibility matters; otherwise design your own idiomatic shapes.
- The specific `SDK*` type names. They are Anthropic's namespace.

---

## 7. Evidence index

| Artefact | Path |
| :- | :- |
| Raw fetched focus page (39,741 bytes) | `agent-reference-shots/agent-sdk-agent-loop/agent-loop.md` |
| TypeScript SDK reference (296,465 bytes) | `agent-reference-shots/agent-sdk-agent-loop/agent-sdk-typescript.md` |
| Python SDK reference (160,194 bytes) | `agent-reference-shots/agent-sdk-agent-loop/agent-sdk-python.md` |
| This chapter | `agent-reference-shots/agent-sdk-agent-loop/agent-evidence-agent-sdk-agent-loop.md` |
| Prior local CLI event capture (sanitized) | `agent-reference-shots/area1-agent-loop/sanitized-agent-loop.jsonl` |
| Prior local CLI capture notes | `agent-reference-shots/area1-agent-loop/OBSERVATIONS.md` |
| Terms/compliance reasoning | `agent-reference-shots/TERMS-NOTES.md` |

**Public documentation consulted (exact URLs):**
- <https://code.claude.com/docs/en/agent-sdk/agent-loop.md>
- <https://code.claude.com/docs/en/agent-sdk/typescript.md>
- <https://code.claude.com/docs/en/agent-sdk/python.md>
- <https://code.claude.com/docs/en/how-claude-code-works.md>

**Not fetched in this pass (referenced but not read):**
`/docs/en/agent-sdk/permissions`, `/docs/en/agent-sdk/subagents`, `/docs/en/agent-sdk/hooks`, `/docs/en/agent-sdk/streaming-output`, `/docs/en/agent-sdk/sessions`, `/docs/en/agent-sdk/session-storage`, `/docs/en/agent-sdk/cost-tracking`, `/docs/en/agent-sdk/tool-search`, `/docs/en/agent-sdk/claude-code-features`, `/docs/en/model-config`, `/docs/en/permission-modes`.
