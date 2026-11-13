# Interface Specification — Clean-Room Agentic Coding Harness

**Document status:** normative planning deliverable. No implementation exists yet; this document *is* the contract.
**Companion document:** `architecture.md` — the layer stack and design decisions this specification implements.
**Evidence base:** `agent-evidence.md`, `agent-reference-shots/PROTOCOL-NOTES.md`, `agent-reference-shots/stream-json-basic.jsonl`, `agent-reference-shots/tool-error-contract.json`, `agent-reference-shots/denied-tool-results.json`, `agent-reference-shots/tool-result-dual-representation.json`, `agent-reference-shots/print-mode-json-result.json`, `agent-reference-shots/cli-reference/*.json`, and `agent-reference-shots/docs-cache/*.md`.

---

## 1. Scope

This specification defines the **externally observable and internally normative interfaces** of the harness:

- The interfaces a **user or script** consumes: the CLI surface, the event stream, the terminal result envelope, the settings and permission-rule formats.
- The interfaces a **front end** consumes: the agent turn, the session store, the event stream, the tool registry.
- The interfaces an **extension author** consumes: tools, hooks, MCP servers, skills, commands, subagent definitions.

**Out of scope.** Internal function signatures that no extension or consumer can observe; the model weights; the provider's own wire protocol (we consume it through an adapter, and the adapter is specified here only at its boundary); and any text copied from the reference product.

### 1.1 Status markers

Every interface section carries one of two markers, and every individual field within it may carry a finer marker:

| Marker | Meaning |
| :- | :- |
| **OBSERVED-COMPATIBLE** | The shape was directly observed in captured output, or is documented in a captured official document. We reproduce it because a compatible consumer, script, rule file, or extension depends on it. |
| **ORIGINAL** | The evidence does not determine the shape. We designed it. It is our own interface, and it is free to differ from the reference. |

**ORIGINAL DESIGN DECISION** fields are additionally called out inline with a rationale and at least one alternative considered.

### 1.2 Normative language

`MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` are used in the RFC-2119 sense. A `MUST` in an **OBSERVED-COMPATIBLE** section is a compatibility obligation — violating it breaks a consumer we know exists. A `MUST` in an **ORIGINAL** section is an internal-consistency obligation.

---

## 2. Conventions

### 2.1 Naming

| Context | Convention | Example |
| :- | :- | :- |
| JSON / event field names | `snake_case` | `tool_use_id`, `session_id` |
| JSON / event field names in our own extensions | `snake_case` | `permission_decision` |
| TypeScript type and member names | `PascalCase` / `camelCase` | `ToolResult`, `toolUseResult` |
| CLI flags | `kebab-case`, long form preferred | `--output-format`, `--max-turns` |
| CLI short flags | single letter, lower case | `-p`, `-r`, `-c`, `-v`, `-w` |
| Settings keys | `snake_case` inside a `camelCase` object | `permissions.allow`, `cleanupPeriodDays` (a documented legacy key) |
| Environment variables | `SCREAMING_SNAKE_CASE` with a product prefix | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` |
| On-disk files | `kebab-case` for plans and memory topics, `UPPER_SNAKE` for the memory index | `plans/refactor-auth.md`, `MEMORY.md` |
| Tool names | `snake_case`, globally unique | `read_file`, `mcp__github__create_issue` |
| Rule identifiers | `Tool` / `Tool(spec)` / `Bash(prefix)` / `Read(path)` / `Edit(path)` / `Write(path)` / `WebFetch(domain:host)` | `Bash(git status)` |
| Event discriminators | `type` + optional `subtype`, both `snake_case` | `type: "system"`, `subtype: "compact_boundary"` |
| Subtype values | `snake_case` | `error_max_turns` |

**A note on the mixed case in the settings surface.** A small number of settings keys are `camelCase` rather than `snake_case` (for example `cleanupPeriodDays`). These are **compatibility keys**: they are read, honoured, and written back under their observed spelling, because a user's existing configuration file must keep working. We do not introduce new `camelCase` keys.

### 2.2 Versioning

| Surface | Versioning scheme | Notes |
| :- | :- | :- |
| The product | Semantic versioning (`MAJOR.MINOR.PATCH`) | A `MAJOR` bump is allowed to remove a CLI flag or change a default. |
| On-disk structures | A `proto` (or `version`) integer field in the file | On-disk formats are versioned **independently of the product**, because a state directory outlives any one binary. A reader that sees an unknown `proto` MUST refuse to write and MUST report the version. |
| The event stream | **Unversioned in-band.** | The stream is a single run's output; there is no negotiated version. Forward compatibility is handled by the *open set* rule (§2.2.1). |
| The settings schema | A `$schema` reference plus a schema version integer | A settings file with a newer schema version is read on a best-effort basis, and unknown keys are reported, not rejected. |
| The terminal result envelope | Additive-only within a `MAJOR` | Field removal is a `MAJOR` event. |
| MCP | The protocol's own version negotiation | We do not extend the MCP protocol; we extend the *namespace*. |

#### 2.2.1 The open-set rule

**OBSERVED-COMPATIBLE.** The event stream, the settings surface, the `capabilities` array, the tool set, the skill/agent registries, and the hook event set are all **open sets**. A consumer MUST ignore any `type`, `subtype`, `capabilities[]` entry, settings key, tool name, skill name, agent name, or hook event name it does not recognise, and MUST NOT treat the presence of an unrecognised value as an error.

The `capabilities` array in the init event is the mechanism by which a consumer learns what a given build offers. A capability string is an open identifier, not an enum. A consumer that hard-codes the list it saw in one build is broken by the next one.

#### 2.2.2 Compatibility targets

The harness targets compatibility with the *reference product's observable surfaces* wherever a consumer is likely to depend on them. It does **not** target bug-for-bug fidelity, and it does not target the reference's internal structures.

### 2.3 The error envelope

**ORIGINAL.** Every fallible interface in this specification reports failure with the same shape, so a consumer can handle failures generically.

```ts
type HarnessError = {
  code: string;              // stable, machine-parseable, dot-separated
  category: ErrorCategory;
  message: string;           // human-readable, one line
  details?: Record<string, unknown>;
  retryable: boolean;
  causedBy?: string;         // the code of the underlying error, if any
};
```

| `category` | Meaning | Retryable? |
| :- | :- | :- |
| `input_invalid` | The caller's input is malformed or violates the schema | No — the caller must fix it |
| `not_found` | The named entity does not exist | No |
| `permission_denied` | A policy or rule refused the operation | No |
| `conflict` | The operation is illegal in the current state | No |
| `precondition_failed` | A required prior step is missing | No |
| `resource_exhausted` | A limit was reached (turns, budget, concurrency, depth) | No — but the run may be retried with different limits |
| `transient` | A temporary failure (network, capacity) | Yes |
| `terminal_provider` | A provider failure that retrying cannot fix | No |
| `internal` | A defect in the harness | No |

**The `code` is the stable identifier; the `message` is not.** A consumer MUST branch on `code` or `category`, never on message text. Message wording is ours and will change.

**Error codes used in this specification:**

| Code | Category | Meaning |
| :- | :- | :- |
| `invalid_input` | `input_invalid` | Schema validation failed. |
| `unknown_tool` | `not_found` | No such tool in the registry. |
| `unknown_session` | `not_found` | No such session id or title. |
| `invalid_session_id` | `input_invalid` | The supplied session id is not a valid identifier. |
| `no_conversation_found` | `not_found` | The resume target does not resolve to a conversation. |
| `resume_requires_identifier` | `precondition_failed` | Resume requested without an id or title in a non-interactive session. |
| `rule_syntax_error` | `input_invalid` | A permission rule could not be parsed. |
| `rule_scope_unknown` | `input_invalid` | A rule referenced an unknown scope or sub-entity. |
| `denied_by_rule` | `permission_denied` | A Tier-1 deny rule matched. |
| `denied_by_mode` | `permission_denied` | The active permission mode forbids the call. |
| `denied_by_safety` | `permission_denied` | A Tier-2 safety check refused the call. |
| `consent_required` | `permission_denied` | The tool requires explicit human interaction and none was possible. |
| `workspace_untrusted` | `permission_denied` | The workspace has not been trusted. |
| `tool_execution_failed` | `internal` | The tool ran and failed; the command's own error is the payload. |
| `tool_input_invalid` | `input_invalid` | The tool's own input validation failed. |
| `output_too_large` | `resource_exhausted` | The output exceeded the hard ceiling. |
| `max_turns_reached` | `resource_exhausted` | The turn cap was reached. |
| `max_budget_exceeded` | `resource_exhausted` | The spend cap was reached. |
| `max_depth_exceeded` | `resource_exhausted` | The subagent spawn depth cap was reached. |
| `concurrency_limit` | `resource_exhausted` | The subagent concurrency cap was reached. |
| `subagent_no_tools` | `precondition_failed` | The spawn request produced an empty tool allowlist. |
| `stream_interrupted` | `transient` | The provider stream failed mid-response. |
| `provider_auth_failed` | `terminal_provider` | Authentication failed. |
| `provider_rate_limited` | `transient` | Rate limited. |
| `provider_overloaded` | `transient` | Capacity exhausted upstream. |
| `provider_invalid_request` | `terminal_provider` | The request was rejected as invalid. |
| `provider_model_not_found` | `terminal_provider` | The model id is unknown to the provider. |
| `context_overflow` | `resource_exhausted` | The request exceeded the context window. |
| `mcp_transport_error` | `transient` | An MCP server could not be reached. |
| `mcp_tool_error` | `internal` | An MCP server returned a tool error. |
| `hook_failed` | `internal` | A hook exited abnormally. |

### 2.4 Idempotency

| Operation | Idempotent? | Rule |
| :- | :- | :- |
| Tool execution | **No.** | A tool call is identified by `tool_use_id` and MUST NOT be executed twice for the same id, even if the same content is re-sent. The dispatcher MUST record executed ids for the life of the session. |
| Transcript append | **Yes.** | Appending the same entry id twice MUST be idempotent; a reader MUST skip a repeated entry id. |
| Session resume | **Yes** (read-only) | Resume MUST NOT mutate the original transcript. |
| Forked session | **No** | Forking writes to a new session id; the original is untouched. |
| Compaction | **No** | Compaction rewrites the model-visible history and appends a boundary. It is idempotent only in the sense that a second compaction of an already-compacted history is a no-op decision. |
| Hook invocation | **No** | A hook is invoked once per matching event. A hook that is not idempotent MUST document that. |
| Configuration resolution | **Yes** | Resolution is a pure function of (scopes, environment, argv). |
| Permission decision | **Yes** | A decision is a pure function of (call, context). A decision MUST NOT have side effects; recording it is a separate step. |
| Settings write | **No** | A write replaces the file atomically. A concurrent write is last-writer-wins. |
| MCP tool call | **No** | Forwarded to the server; the server's semantics apply. |

### 2.5 Deprecation

- A deprecated CLI flag MUST continue to work for at least two `MINOR` releases and MUST emit a diagnostic on **stderr**.
- A deprecated settings key MUST continue to be honoured, and the resolver MUST report the resolved value's provenance as `deprecated:<replacement>` so an `explain` command can surface the migration.
- A deprecated event `subtype` MUST continue to be emitted for at least two `MINOR` releases, alongside its replacement.
- A deprecated tool name MUST continue to be accepted as an alias for at least two `MINOR` releases, and MUST be recorded in the decision log as an alias resolution.
- **Removal of a compatibility surface requires a `MAJOR` release and a migration note.**

### 2.6 Redaction

Worked examples in this document are redacted where a value would identify a person, a machine, a repository, or a credential. The redaction markers are:

- `<uuid>` — a UUID-shaped identifier.
- `<abs-path>` — an absolute filesystem path.
- `<rel-path>` — a path relative to the working directory.
- `<model-id>` — a model identifier.
- `<provider>` — a provider identifier.
- `<redacted>` — a value deliberately withheld.

Redaction is applied to *examples only*. Field names, types, and requiredness are always literal.

---

## 3. Interface 1 — Agent turn

**Status: OBSERVED-COMPATIBLE (event shape) / ORIGINAL (turn API shape).**

The turn is the harness's central unit of work. Its *observable* form — the event sequence it produces — is compatibility-critical. Its *programmatic* form is our own.

### 3.1 Shape

```ts
type TurnRequest = {
  sessionId: string;
  prompt: UserInput;             // text | attachment | command
  mode: PermissionMode;
  model?: ModelSelection;        // resolved per role if omitted
  effort?: EffortLevel;
  maxTurns?: number;
  maxBudgetUsd?: number;
  tools?: ToolName[];            // restrict the model's tool set
  allowedTools?: ToolName[];
  disallowedTools?: ToolName[];
  resume?: { sessionId: string; fork?: boolean };
  structuredOutput?: JSONSchema;
  signal?: AbortSignal;
};

type TurnOutcome = {
  sessionId: string;
  result: TerminalEnvelope;
  events: Event[];               // the complete stream, including the terminal envelope
};
```

### 3.2 Field table — `TurnRequest`

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `sessionId` | `string` | Yes | The session to append to. | A valid UUID. If absent, the harness mints one and reports it in the init event. |
| `prompt` | `UserInput` | Yes | The user's input. | A slash command prefix is dispatched before the model sees it (§14.5). |
| `mode` | `PermissionMode` | Yes | The active permission mode. | `default` · `acceptEdits` · `plan` · `auto` · `dontAsk` · `bypassPermissions`. `manual` is accepted as an alias for `default` and normalised on input (§6.1). |
| `model` | `ModelSelection` | No | An explicit model for the `main` role. | Resolved through the chain in §11.5. |
| `effort` | `EffortLevel` | No | Reasoning effort for the `main` role. | `low` · `medium` · `high` · `xhigh` · `max`. An unrecognised value is ignored with a warning (§11.6). |
| `maxTurns` | `number` | No | Cap on the number of turns. | Positive integer. A cap of `0` is invalid. |
| `maxBudgetUsd` | `number` | No | Cap on session spend. | Non-negative. Checked after each response (§3.5). |
| `tools` | `ToolName[]` | No | An explicit allowlist of tools for the model. | Replaces the computed registry set. |
| `allowedTools` / `disallowedTools` | `ToolName[]` | No | Additive/subtractive tool adjustments. | `disallowedTools` is applied **after** `tools`. |
| `resume` | `object` | No | Resume an existing session. | `fork: true` mints a new session id; the original transcript is untouched. |
| `structuredOutput` | `JSONSchema` | No | Require the final response to validate against a schema. | Retries are bounded; exhaustion yields `error_max_structured_output_retries`. |
| `signal` | `AbortSignal` | No | Cancellation. | On abort, the turn ends without a result envelope; exit code `143`. |

### 3.3 Field table — `TurnOutcome`

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `sessionId` | `string` | Yes | The session that was written to. | Differs from the request's `sessionId` when `resume.fork` is set. |
| `result` | `TerminalEnvelope` | Yes | The terminal envelope. | See §15. |
| `events` | `Event[]` | Yes | Every event emitted during the turn, in order. | Includes the init event and the terminal envelope. |

### 3.4 Semantics

**MUST** — Turn definition. A turn is one evaluate/execute round trip: the model produced output containing tool calls, the harness executed them, and their results were fed back automatically. The final text-only assistant message is **not** a turn.

**MUST** — Single natural exit. The loop terminates naturally only when the model produces a response containing no tool calls. Every other exit is an injected limit or an error.

**MUST** — Non-yielding. The turn MUST NOT yield to the caller between tool calls. A caller that needs to interject uses the mid-turn input channel (§3.6).

**MUST** — Continuation. When the model produces tool calls, the harness MUST execute them, append their results, and re-issue a request **without** presenting the turn as finished. The terminal envelope is emitted only at the natural or injected exit.

**MUST** — Correlation. Every tool call carries a `tool_use_id`; every tool result carries the same id. Results MAY be delivered out of order relative to their requests.

**MUST** — Denial occupies a result slot. A denied or rejected call MUST produce a `user` event with a `tool_result` content block carrying `is_error: true`. A denial is data, never an exception out of the dispatcher.

**MUST** — Never re-send a partially delivered response. If a failure occurs after any content block of the current response has been committed, the request MUST NOT be re-sent. The committed output MUST be preserved, and the harness MUST report that the response may be incomplete. If the failure occurs before any content is committed, the request MAY be retried normally, a bounded number of times, with backoff.

> **ORIGINAL DESIGN DECISION (the never-resend rule).** *Rationale:* the hazard is a duplicated side effect, not a duplicated message. A retry after a committed tool-call block executes that tool again — a second delete, a second deploy. Alternative considered: (a) retry everything — rejected, it can duplicate side effects; (b) never retry — rejected, it wastes a recoverable failure; (c) retry only if the response contained no tool calls — rejected, a committed text block can also mislead the model about what has already been said.

**MUST** — Per-turn effort accounting. The harness MUST record the effort level active for each turn and surface the current value in the terminal envelope (`per_turn_effort_active`).

### 3.5 Stop conditions

| Condition | Terminal `subtype` | Counting rule |
| :- | :- | :- |
| Text-only model response | `success` | The response is **not** counted as a turn. |
| Turn cap reached | `error_max_turns` | Counted **after** the response arrives; the triggering response completes and is counted. |
| Spend cap reached | `error_max_budget_usd` | Counted **after** the response arrives; the overshoot is bounded by one response. |
| Execution error (cancel, provider failure) | `error_during_execution` | `stop_reason` is `null` when synthesised after a crash. |
| Structured-output validation exhausted | `error_max_structured_output_retries` | The retry counter is separate from the turn counter. |
| SIGTERM | *(no envelope)* | The turn is abandoned; exit code `143`. |

**MUST** — the budget accumulates across a turn-cap stop. A turn-cap stop resets the turn counter for the next turn but MUST NOT reset the session's accumulated spend. Only an explicit session clear resets it.

### 3.6 Mid-turn input

**OBSERVED-COMPATIBLE.** A user message arriving while the model is mid-tool-execution is queued and injected **between tool executions, within the same turn**. The queue depth is reported as `queued_turn_count` in the terminal envelope.

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `content` | `string` | Yes | The user's text. | — |
| `source` | `string` | No | `user` (default) or `queue` (a message moved from the pending queue). | — |
| `queued_turn_count` | `number` | No | The number of messages still queued. | Present on the terminal envelope. |

### 3.7 Error cases

| Situation | Behaviour |
| :- | :- |
| `maxTurns` is `0` or negative | Rejected before any model call. `input_invalid` / `invalid_input`. Exit `1`. |
| `maxBudgetUsd` is negative | Rejected before any model call. `input_invalid` / `invalid_input`. Exit `1`. |
| `sessionId` is not a valid UUID | Rejected. `input_invalid` / `invalid_session_id`. Exit `1`. |
| `resume.sessionId` does not exist | `not_found` / `no_conversation_found`. Exit `1`. |
| The provider fails before any content is committed | Retry per §3.4; on exhaustion, `error_during_execution` with `api_error_status` set. |
| The provider fails after content is committed | Never retried. `error_during_execution`, and the response is preserved with the incompleteness warning. |
| A tool's own execution throws | The exception is converted to a tool result with `is_error: true`; the turn continues. |
| The signal is aborted | The turn ends. No terminal envelope. Exit `143`. |

### 3.8 Worked example

A complete, minimal, redacted stream for a turn that read one file and then answered.

```jsonc
// 1. init
{"type":"system","subtype":"init","cwd":"<abs-path>","session_id":"<uuid>","uuid":"<uuid>",
 "model":"<model-id>","permissionMode":"default","tools":["read_file"],"capabilities":["tools"],
 "claude_code_version":"<version>","output_style":"default"}

// 2. assistant text block
{"type":"assistant","message":{"id":"msg_<uuid>","type":"message","role":"assistant",
 "content":[{"type":"text","text":"Reading the file."}],"model":"<model-id>","stop_reason":null,
 "usage":{"input_tokens":1204,"output_tokens":8}},
 "parent_tool_use_id":null,"session_id":"<uuid>","uuid":"<uuid>","timestamp":"<iso8601>","request_id":"req_<uuid>"}

// 3. assistant tool_use block (same message id as block 2)
{"type":"assistant","message":{"id":"msg_<uuid>","type":"message","role":"assistant",
 "content":[{"type":"tool_use","id":"call_<uuid>","name":"read_file","input":{"file_path":"<rel-path>"}}],
 "model":"<model-id>","stop_reason":null,"usage":{"input_tokens":1204,"output_tokens":8}},
 "parent_tool_use_id":null,"session_id":"<uuid>","uuid":"<uuid>","timestamp":"<iso8601>","request_id":"req_<uuid>"}

// 4. user tool_result
{"type":"user","message":{"role":"user","content":[
   {"tool_use_id":"call_<uuid>","type":"tool_result","content":"1\tdef greet(name):\n2\t    return f\"hi {name}\""}]},
 "parent_tool_use_id":null,"session_id":"<uuid>","uuid":"<uuid>","timestamp":"<iso8601>",
 "tool_use_result":{"type":"text","file":{"filePath":"<abs-path>","content":"def greet(name):\n    return f\"hi {name}\"",
   "numLines":2,"startLine":1,"totalLines":2}},
 "tool_result_meta":[{"id":"call_<uuid>","permission_decision":{"decision":"accept","source":"config","reason_type":"rule"}}]}

// 5. terminal envelope
{"type":"result","subtype":"success","is_error":false,"result":"It greets the caller.",
 "session_id":"<uuid>","uuid":"<uuid>","num_turns":1,"stop_reason":"end_turn","terminal_reason":"completed",
 "duration_ms":2410,"duration_api_ms":2380,"total_cost_usd":0.0041,
 "usage":{"input_tokens":2410,"output_tokens":42},"modelUsage":{"<model-id>":{"inputTokens":2410,"outputTokens":42,
   "cacheReadInputTokens":0,"cacheCreationInputTokens":0,"costUSD":0.0041,"contextWindow":200000,
   "maxOutputTokens":32000,"thinkingTokens":0,"canonicalModel":"<model-id>","provider":"<provider>","costBasis":"standard"}},
 "permission_denials":[],"safety_stops":0,"queued_turn_count":0,"result_index":0}
```

---

## 4. Interface 2 — Tool interface and tool-result envelope

**Status: OBSERVED-COMPATIBLE (envelope, dual representation, correlation) / ORIGINAL (tool definitions and names).**

### 4.1 Shape

```ts
type ToolDefinition = {
  name: string;
  description: string;
  inputSchema: JSONSchema;
  annotations: {
    readOnly: boolean;
    destructive: boolean;
    idempotent: boolean;
    openWorld: boolean;
    requiresUserInteraction?: boolean;
  };
  execute(ctx: ToolContext, input: unknown): Promise<ToolResult>;
};

type ToolResult = {
  isError: boolean;
  content: string;                 // the model's view
  toolUseResult: unknown;          // the operator/transcript view
  meta?: { permissionDecision?: PermissionDecision };
  nonExecutionKind?: 'user-rejected' | 'pre-parse-failure';
};
```

### 4.2 Field table — `ToolDefinition`

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `name` | `string` | Yes | The globally unique tool name. | `^[a-z][a-z0-9_]*$` for built-ins; MCP names use the `mcp__` convention (§6.4). |
| `description` | `string` | Yes | What the tool does and when to use it. | Our own prose. **MUST** state the observable side effects. |
| `inputSchema` | `JSONSchema` | Yes | The input contract. | `type: "object"`, `properties`, `required`, `additionalProperties: false`. |
| `annotations.readOnly` | `boolean` | Yes | The tool does not modify the world. | Drives the concurrency class (§8.6). |
| `annotations.destructive` | `boolean` | Yes | The tool can irreversibly destroy state. | Feeds the Tier-2 analyser. |
| `annotations.idempotent` | `boolean` | Yes | Repeating the call has the same effect as calling once. | — |
| `annotations.openWorld` | `boolean` | Yes | The tool reaches the network or an external system. | — |
| `annotations.requiresUserInteraction` | `boolean` | No | The tool requires explicit human interaction **every** time. | When `true`: no allow rule may bypass it; a non-interactive run denies it. |
| `execute` | `function` | Yes | The implementation. | MUST NOT perform a permission check; the gate is in the dispatcher. |
| `ctx` | `ToolContext` | Yes | The execution context. | Carries the working directory, the abort signal, the session id, the observed-paths accessor, and the output sink. |

### 4.3 Field table — `ToolResult`

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `isError` | `boolean` | Yes | The call did not succeed. | A non-zero exit is **not** automatically an error (§4.7). |
| `content` | `string` | Yes | What the model receives. | Always a string, even for structured results. |
| `toolUseResult` | `unknown` | Yes | The structured payload for operators and the transcript. | A typed object on success; the string `"Error: <message>"` on failure. |
| `meta.permissionDecision` | `PermissionDecision` | No | The decision that authorised the call. | Present when the call passed through the gate. |
| `nonExecutionKind` | `enum` | No | Why the tool did not run. | `user-rejected` · `pre-parse-failure`. |

### 4.4 The dual representation — normative

**OBSERVED-COMPATIBLE.** A tool result carries two renderings of the same execution, and both are part of the contract.

| Outcome | `toolUseResult` | `content` | `isError` |
| :- | :- | :- | :- |
| Success | A typed object (see below) | The flattened text form | `false` |
| Failure or denial | The string `"Error: <message>"` | `<message>` (no prefix) | `true` |

Worked pairs, observed:

```jsonc
// success — a shell command
{"outcome":"success",
 "tool_use_result":{"stdout":"A","stderr":"","interrupted":false,"isImage":false,"noOutputExpected":false},
 "tool_result_content":"A","is_error":false}

// failure or denial
{"outcome":"failure_or_denial",
 "tool_use_result":"Error: This command requires approval",
 "tool_result_content":"This command requires approval","is_error":true}
```

**MUST** — the `Error: ` prefix is present in `toolUseResult` and **absent** from `content`. The prefix is the audit copy; the content is the model's copy. This asymmetry is intentional and is the reason a model is not told it received an error by a string it might read as data.

**MUST** — the typed payload for each tool family:

| Tool family | `toolUseResult` shape |
| :- | :- |
| Shell command | `{ stdout, stderr, interrupted, isImage, noOutputExpected }` |
| File read | `{ type: "text", file: { filePath, content, numLines, startLine, totalLines } }` |
| File write | `{ type: "text", file: { filePath, content, numLines, startLine, totalLines, oldContent } }` |
| File edit | `{ type: "text", file: { filePath, content, numLines, startLine, totalLines, oldContent, newContent, structuredPatch } }` |
| Glob | `{ filenames[], durationMs, numFiles, truncated, totalMatches, countIsComplete }` |
| Grep | `{ filenames[], content, numFiles, truncated, totalMatches, countIsComplete }` |
| Delegation | `{ stdout, stderr, interrupted, isImage, noOutputExpected }` plus the worker report |

### 4.5 Correlation and ordering

**MUST** — every tool result MUST carry the `tool_use_id` of the call it answers.

**MUST** — results MAY be delivered out of order. A consumer MUST correlate by id and MUST NOT assume request order.

**MUST** — a `system/permission_denied` event MUST precede the `user` event carrying the corresponding denial result.

### 4.6 The output-size ladder

**OBSERVED-COMPATIBLE** (limits) with one deliberate extension.

| Path | Inline limit | On overflow |
| :- | :- | :- |
| Success | ~30,000 characters | A file path inside the session directory plus a ~2,000-character preview, wrapped in literal `<persisted-output>` tags. |
| Failure | ~10,000 characters | A head-and-tail excerpt of that size, **plus a file path**. |
| Absolute | — | A hard kill at 5 GB of streamed output. |

**MUST** — the overflow file lives inside the session directory (`<session-dir>/tool-results/<tool_use_id>.txt`) so it survives with the transcript and is addressable by the file-read tool.

**MUST** — the overflow notice is wrapped in the literal tags `<persisted-output>` and `</persisted-output>` so a consumer can locate it without parsing prose.

> **ORIGINAL DESIGN DECISION (the failure path also returns a file pointer).** *Rationale:* a failing build's output is exactly the output a developer needs, and an excerpt with no pointer makes it unrecoverable except by re-running the command. *Alternative considered:* (a) match the observed behaviour exactly — rejected, the recoverability loss is real; (b) return no excerpt at all — rejected, it defeats the purpose of the result.

**MUST** — the overflow result payload is:

```jsonc
{ "inline_preview": "…", "output_file_path": "<session-dir>/tool-results/<id>.txt",
  "total_bytes": 2621440, "truncated": true }
```

### 4.7 Error cases and exit-code semantics

**OBSERVED-COMPATIBLE.** A tool's non-zero exit code does **not** abort the turn.

| Situation | `isError` | `content` |
| :- | :- | :- |
| Schema validation failed | `true` | A machine-parseable error naming the offending field. |
| The command exited non-zero | `true` | `"Error: Exit code 7\n<interleaved output>"` |
| The command exited 1 but is a member of the benign set | `false` | The normal output. |
| The command could not be parsed | `true` | A parse diagnostic; `nonExecutionKind: "pre-parse-failure"`. |
| The user rejected the call | `true` | The rejection text; `nonExecutionKind: "user-rejected"`. |
| The call was denied by a rule | `true` | The denial text. |

**MUST** — a tool error MUST carry a machine-parseable marker so a consumer (and the model) can distinguish a tool fault from a policy refusal without parsing prose. Our marker is a `<tool_use_error>` prefix.

**MUST** — the *benign exit set* is a user-visible table. It lists the commands whose exit code `1` is a legitimate outcome (for example a search that finds nothing, or a diff that reports differences). A command in the table is treated as a success; a command outside it is treated as a failure. The table is configurable and is surfaced in the permission dialog so the human can see why a command would be treated as a failure.

### 4.8 The tool registry

**MUST** — the tool set is a **pure function** of `(provider capabilities, model capabilities, plan, configuration)`. A tool that is unavailable MUST be **absent from the model's schema**, not present-and-denied. A "present but denied" capability costs schema tokens on every request, produces denial events the model must interpret, and invites retry loops.

**MUST** — a `doctor`-style command MUST report every disabled tool and the reason.

### 4.9 Error cases

| Situation | Behaviour |
| :- | :- |
| The tool name is not in the registry | `not_found` / `unknown_tool`. The call never reaches a tool implementation. |
| The input fails the tool's JSON schema | `input_invalid` / `tool_input_invalid`. The result carries `is_error: true` and names the offending field. The turn continues. |
| The tool implementation throws | The exception is converted to a tool result with `is_error: true` and the error text. The turn continues. |
| The tool is aborted by the signal | `transient` / `stream_interrupted`. The result carries `is_error: true`. |
| The output exceeds 5 GB | The process is killed. `resource_exhausted` / `output_too_large`. |
| The write target is not UTF-8 | The write is refused with a model-directed message naming the two remedies (use a shell command that preserves the encoding, or ask the user about conversion). **Never write lossy.** |
| The edit's `old_string` is not found | `precondition_failed`. The message names both remedies: set `replace_all`, or provide more context. |
| The edit's `old_string` is not unique | `precondition_failed`. The message names the count and both remedies. |
| The edit target was not read first | `precondition_failed`. The message names the read-before-edit requirement. |
| The target path is protected | `permission_denied` / `denied_by_safety`. |
| The tool requires consent and none is possible | `permission_denied` / `consent_required`. |
| The same `tool_use_id` is dispatched twice | The second dispatch MUST be suppressed, and the recorded result returned unchanged. |

### 4.10 Worked example — a file edit

```jsonc
// the model's call
{"type":"assistant","message":{"role":"assistant","content":[
  {"type":"tool_use","id":"call_<uuid>","name":"edit_file",
   "input":{"file_path":"<rel-path>","old_string":"    return f\"hi {name}\"","new_string":"    return f\"hello {name}\""}}]},
 "uuid":"<uuid>","timestamp":"<iso8601>"}

// the result
{"type":"user","message":{"role":"user","content":[
  {"tool_use_id":"call_<uuid>","type":"tool_result","content":"The file <rel-path> has been updated."}]},
 "uuid":"<uuid>","timestamp":"<iso8601>",
 "tool_use_result":{"type":"text","file":{"filePath":"<abs-path>","content":"…","numLines":2,
   "startLine":1,"totalLines":2,"oldContent":"…","newContent":"…",
   "structuredPatch":[{"oldStart":2,"oldLines":1,"newStart":2,"newLines":1,
     "lines":[{"oldLine":2,"newLine":2,"content":"    return f\"hello {name}\"","op":"replace"}]}]}},
 "tool_result_meta":[{"id":"call_<uuid>","permission_decision":{"decision":"accept","source":"config","reason_type":"rule"}}]}
```

---

## 5. Interface 3 — Permission decision interface

**Status: OBSERVED-COMPATIBLE (decision vocabulary, the `permission_decision` record) / ORIGINAL (the query API shape).**

### 5.1 Shape

```ts
type PermissionQuery = {
  toolName: string;
  toolInput: unknown;             // already schema-validated
  sessionId: string;
  cwd: string;
  mode: PermissionMode;
  scope: PermissionScope;         // the scope of the rule set being consulted
  subagent?: { type: string; depth: number };
  isPlanMode?: boolean;
  trustState: 'trusted' | 'untrusted';
};

type PermissionDecision = {
  decision: 'allow' | 'deny' | 'ask';
  reason: string;                 // human-readable
  reasonType: PermissionReasonType;
  source: PermissionSource;
  scope?: PermissionScope;
  matchedRule?: string;           // the rule text that decided it
  behavior?: 'allow' | 'deny' | 'ask' | 'defer';
  updatedInput?: unknown;         // present when a hook rewrote the argument
};

type PermissionReasonType =
  | 'rule' | 'mode' | 'classifier' | 'subcommand' | 'consent_required'
  | 'safety_tier2' | 'policy';

type PermissionSource =
  | 'config' | 'session' | 'user' | 'project' | 'local'
  | 'managed' | 'builtin' | 'hook' | 'mode' | 'classifier';
```

### 5.2 Field table — `PermissionQuery`

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `toolName` | `string` | Yes | The tool being invoked. | Must be present in the model's schema; a call to an absent tool never reaches the gate. |
| `toolInput` | `unknown` | Yes | The resolved argument. | Schema-validated, then **normalised** (shell wrappers stripped, compound commands split, aliases canonicalised, paths resolved). The gate sees what will actually run. |
| `sessionId` | `string` | Yes | The session. | — |
| `cwd` | `string` | Yes | The working directory. | — |
| `mode` | `PermissionMode` | Yes | The active mode. | — |
| `scope` | `PermissionScope` | Yes | The scope whose rule set is being consulted. | `managed` · `user` · `project` · `local`. |
| `subagent` | `object` | No | Present when the call originates in a worker. | `type`, `depth`. |
| `isPlanMode` | `boolean` | No | Whether the session is in plan mode. | In plan mode, mutating tools are removed from the schema **and** the operation classifier marks mutating operations as disallowed. The schema filter is a steering device; the operation check is the guarantee. See §5.7. |
| `trustState` | `enum` | Yes | Whether the workspace is trusted. | Trust gates **grants**, not restrictions (§5.6). |

### 5.3 Field table — `PermissionDecision`

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `decision` | `enum` | Yes | The outcome. | `allow` · `deny` · `ask`. |
| `reason` | `string` | Yes | Why. | Human-readable; not a stable identifier. |
| `reasonType` | `enum` | Yes | The kind of ground. | See above. This is the stable field a consumer branches on. |
| `source` | `enum` | Yes | Who decided. | See above. |
| `scope` | `enum` | No | The scope of the deciding rule. | Present when a rule decided it. |
| `matchedRule` | `string` | No | The rule text. | Present when a rule decided it. |
| `behavior` | `enum` | No | A hook's verdict. | `allow` · `deny` · `ask` · `defer`. |
| `updatedInput` | `unknown` | No | A rewritten argument. | Present when a hook rewrote it; the rewritten value is what executes. |

### 5.4 The recorded decision

**OBSERVED-COMPATIBLE.** A decision that authorised a call is recorded on the result event:

```jsonc
"tool_result_meta": [
  { "id": "call_<uuid>",
    "permission_decision": { "decision": "accept", "source": "config", "reason_type": "rule" } }
]
```

Note the vocabulary difference between the recorded form and the query form: the recorded `decision` uses `accept`, while the query API uses `allow`. **MUST** — the recorded form MUST use the observed spelling (`accept`); the query API is ours and uses `allow`.

**MUST** — `decision`, `source`, and `reason_type` MUST all be present in a recorded decision, because together they answer "was it allowed, by whom, and on what grounds".

### 5.5 The evaluation order — normative

**OBSERVED-COMPATIBLE.** The order is fixed:

1. **Schema-level presence.** Is the tool in the model's schema at all? If not, the call is impossible.
2. **Input validation** against the tool's JSON schema. A failure is a tool error, not a permission decision.
3. **Operation classification** (§5.8). The normalised input is classified into an operation class. This step is **tool-independent** and is what makes mode constraints enforceable across tools.
4. **Tier 1 — the rule engine**: deny rules → ask rules → allow rules → mode policy. Mode policy is evaluated against the **operation class**, not the tool name.
5. **Tier 2 — the safety layer**: non-configurable, runs after Tier 1, and its verdict **overrides** a Tier-1 allow.

**MUST** — within a rule category, **first match wins**. There is **no specificity sorting**.

**MUST** — **scope does not affect precedence**. A deny rule in a user-scope file beats an allow rule in a project-scope file. Scope is metadata for reporting, not an ordering key.

**MUST** — Tier 2 MUST NOT be reachable from the settings resolver. There MUST be no configuration key that constructs, disables, weakens, or overrides a Tier-2 check.

**MUST** — operation classification MUST run **before** the rule engine, so that a mode's operation-class constraint is not shadowed by an allow rule for a specific tool. A rule that allows `Bash(git status *)` MUST NOT thereby permit a `Bash` command that writes.

### 5.6 Trust semantics

**MUST** — trust gates **grants**, not restrictions. An untrusted workspace MUST NOT be able to grant permission via its own settings, but its deny rules MUST still apply.

### 5.7 The two deny mechanisms

These are **distinct subsystems** and MUST NOT be conflated.

| Mechanism | Where it acts | Effect on the model's schema | Effect on an existing call |
| :- | :- | :- | :- |
| **Bare-name deny** (`Tool` with no specifier) | Capability removal | The tool is **removed** from the schema before the model ever sees it. | The call cannot be made. |
| **Scoped deny** (`Tool(spec)` / `Bash(prefix)` / `Read(path)`) | Call filter | The tool **remains** in the schema. | Matching calls are refused at dispatch time. |

**MUST** — a bare-name deny MUST remove the tool from the schema. **MUST** — a scoped deny MUST leave the tool in the schema and refuse matching calls at dispatch. Both are required: the first is a stronger guarantee, and the second is necessary for tools with both safe and unsafe uses.

### 5.8 The operation-classification layer — a third mechanism, and the one that is the actual security boundary

**This section was added 2026-10-21 after the third verification round. It is a change to the
design, not a clarification of it.**

Both mechanisms in §5.7 act on the **tool**. The evidence base records a case where a mode
blocked the `Write` tool and the same write was then performed through `Bash`
(`agent-reference-shots/area8-permission-modes/observed-behaviours.md` O6; recorded as
UNKNOWN for the reference in `claude-code-evidence.md` §9.4.2, because "the mode blocked
the tool" and "the model routed around the denial" cannot be separated by a single probe).

The conclusion we draw does not depend on which explanation is right: **a mechanism that acts
on the tool name cannot constrain what the tool does.** A tool-level filter is a steering
device. It reduces the chance the model picks a forbidden route. It does not make the
forbidden operation impossible.

**MUST** — every tool call MUST be classified into an **operation class** before dispatch,
independently of the tool that requested it. The classification is derived from the
*normalised* input (§5.2), not the raw input.

| Operation class | Examples | Plan mode | `dontAsk` | Notes |
| :- | :- | :- | :- | :- |
| `read` | read a file, list a directory, search | allowed | allowed | |
| `mutate_local` | write, edit, delete, rename a file | **denied** | denied unless allowed | The core of plan mode's guarantee. |
| `execute` | run a command | **conditional** | denied unless allowed | A command whose *effect* is a mutation is classified `mutate_local`, not `execute`. |
| `network` | fetch a URL, call an API | conditional | denied unless allowed | |
| `process_control` | start/stop a background job, change a setting | denied in plan mode | denied unless allowed | |
| `irreversible` | remove a directory, overwrite a protected path | **denied in every mode** | **denied in every mode** | Never approvable by a rule. Tier 2. |

**MUST** — a shell command MUST be classified by its **effect**, not by its verb. A command
that writes a file is `mutate_local` regardless of whether it is spelled `echo x > f`,
`Set-Content`, `tee`, `dd`, `cp`, `mv`, or `python -c "open('f','w')"`. The shell
front-end's canonical AST (§8) supplies the classification. **A command whose effect cannot
be determined MUST be classified as `mutate_local`** — the conservative direction.

**MUST** — plan mode MUST be enforced as an **operation-class constraint**, not as a
tool-removal flag. Removing the mutating tools from the schema is **also** required, and
remains required — but it is a consequence of the operation set, not the enforcement
mechanism. The rule is:

> The tool list in plan mode is derived from the operation classes the mode permits.
> It is never the primary enforcement.

**MUST** — the operation class MUST be computed from the **normalised primary content** only — the command, the resolved path, the URL. A **model-authored** field (notably `description`) MUST NOT be an input to the operation class, and MUST NOT be able to widen a permission decision.

**The reference is more permissive here, and this is a deliberate divergence.** The reference's rule matcher can key on a top-level scalar input parameter of any built-in tool via `Tool(param:value)`, and `description` is matchable — reproduced first-hand: `--disallowedTools 'Bash(description:*)'` was denied three times, while the control `--disallowedTools 'Bash(description:ZZZNOMATCH*)'` was allowed and ran (`claude-code-evidence.md` R1). Keel's position keeps the *capability* of the reference while tightening the *direction*:

| | Reference | Keel |
| :- | :- | :- |
| A rule keyed on `description` may **deny** a call | yes | **yes** — Keel does not become less expressive, because refusing this would cost expressiveness for no security benefit |
| A rule keyed on `description` may **allow** a call the engine would refuse | yes | **no** — a model-authored field may narrow a decision, never widen one |
| The operation class is computed from `description` | no | **no** — it is computed from the normalised primary content only |

**MUST** — a denial under plan mode MUST name the **operation class** and the **normalised
target** (the resolved path, the command's effect), not merely the tool name. A model that
is told "Write is denied" will try `Bash`; a model that is told "writing to
`/abs/path/f` is denied because this session is in plan mode" has the information it needs
to stop.

**Compatibility note.** This is a **deliberate divergence** from the reference product's
observable behaviour, and it belongs in the compatibility matrix with a rationale. The
reference's plan mode is, at minimum, observably able to be routed around via the shell; ours
is specified to be operation-level and therefore not.

**Test obligations** (added to the test plan's attack matrix):

- `test_plan_mode.py::test_mutation_via_shell_is_denied_in_plan_mode` — a `Bash` command
  whose effect is a file write, under plan mode, is denied **and** the file is not created.
- `test_plan_mode.py::test_every_mutating_tool_is_denied_in_plan_mode` — the property
  version: for every tool in the registry with a mutating operation class, a call in plan
  mode is denied.
- `test_plan_mode.py::test_plan_denial_names_the_operation_not_the_tool` — the message names
  the operation class and the normalised target.
- `test_capability_parity.py::test_denying_one_route_denies_the_capability` — for every
  capability with more than one route (filesystem write via `Write`, `Edit`, `Bash`, a
  plugin, a subagent, an MCP server), denying one route denies the capability. This is the
  generalisation of §9.4.1 in `claude-code-evidence.md`.

### 5.9 Consent-required tools

**OBSERVED-COMPATIBLE.** A tool may declare `requiresUserInteraction`. When it does:

- The tool MUST require explicit human interaction on **every** call.
- **No allow rule may bypass it.**
- There MUST be no "don't ask again" affordance.
- In a non-interactive run, the call MUST be **denied** with `reasonType: "consent_required"` — never auto-approved.

### 5.10 Error cases

| Situation | `decision` | `reasonType` |
| :- | :- | :- |
| A deny rule matched | `deny` | `rule` |
| The mode forbids the call | `deny` | `mode` |
| A Tier-2 safety check matched | `deny` | `safety_tier2` |
| The tool needs consent and none is possible | `deny` | `consent_required` |
| The workspace is untrusted and the call needs a grant | `ask` | `policy` |
| An ask rule matched | `ask` | `rule` |
| The mode requires a human | `ask` | `mode` |
| The classifier flagged it | `ask` | `classifier` |
| An allow rule matched | `allow` | `rule` |
| The mode auto-approves | `allow` | `mode` |
| A hook returned `allow` | `allow` | `policy` |
| A hook returned `deny` | `deny` | `policy` |

### 5.11 Worked example

```jsonc
// The gate query
{"toolName":"run_shell","toolInput":{"command":"git status"},
 "sessionId":"<uuid>","cwd":"<abs-path>","mode":"default","scope":"project",
 "trustState":"trusted"}

// The decision
{"decision":"allow","reason":"Matched allow rule Bash(git status)",
 "reasonType":"rule","source":"project","scope":"project","matchedRule":"Bash(git status)"}

// Recorded on the result event
"tool_result_meta":[{"id":"call_<uuid>",
  "permission_decision":{"decision":"accept","source":"config","reason_type":"rule"}}]
```

---

## 6. Interface 4 — Rule and rule-set model

**Status: OBSERVED-COMPATIBLE (syntax and semantics).**

### 6.1 Shape

```ts
type RuleSet = {
  allow: string[];
  ask: string[];
  deny: string[];
};

type PermissionScope = 'managed' | 'user' | 'project' | 'local';
```

**The permission-mode vocabulary.** `PermissionMode` is referenced in §3.1, §3.2, §5.1 and §5.2
but was never given a declaration. It is declared here, because a mode name that appears in a
type signature without a definition is exactly the kind of hole the interface spec is meant to
close.

```ts
type PermissionMode =
  | 'default'        // UI label: "Manual"
  | 'acceptEdits'
  | 'plan'
  | 'auto'
  | 'dontAsk'
  | 'bypassPermissions';
```

**Correction (2026-10-21).** The enum previously omitted `auto` at all three sites that spelled
it out (§3.2, §6.3 `permissions.defaultMode`, §14 `cli.md --permission-mode`), while §5.3's
`PermissionReasonType` and `PermissionSource` both carried a `'classifier'` member — an
unreachable value in a product with no `auto` mode. `auto` is not an optional mode in the
reference: it is a second model that reviews actions in place of the human, and it is the
reference's **built-in starting permission mode** for interactive terminal and VS Code sessions
from v2.1.283 (`agent-reference-shots/docs-cache/permission-modes.md`, "Available modes" and
"Which mode a session starts in"). Omitting it was not a simplification; it removed a whole
decision path.

**The `manual` alias.** The reference's UI labels the `default` mode "Manual", and the CLI
accepts `manual` **as an alias** for `default` wherever the value can be typed —
`claude --permission-mode manual`, `"defaultMode": "manual"` — while the config value that hooks
and SDK integrations see is `default`. Keel therefore accepts `manual` on input and **normalises
it to `default` on the way in**, so that every downstream comparison, every hook payload's
`permission_mode` field, and every transcript record carries the same canonical string. The
`permission_mode` field in the hook payload (§7.3) MUST carry the normalised value.

**MUST** — a mode name that is not in the enum MUST be rejected at parse time with a diagnostic
listing the accepted values. It MUST NOT be silently coerced to `default`, because a
typo'd `"auto"`-adjacent value that silently becomes `default` is a *tightening* (safe) while
one that silently becomes `bypassPermissions` is a *loosening* (unsafe); rejecting is the only
behaviour that is correct for both.

**MUST** — the mode is a **baseline**, not a decision. Deny and ask rules apply on top of it in
every mode including `bypassPermissions`; allow rules have no effect in `bypassPermissions`
(`agent-reference-shots/docs-cache/permission-modes.md`, "Available modes"). Keel's mode handling
MUST preserve that ordering, and the operation-class layer (§5.8) is evaluated *after* the mode
and *before* the rules, so that a mode can never widen a rule.

**MUST** — the three categories are separate lists in the settings file:

```jsonc
{
  "permissions": {
    "allow": ["Bash(git status)", "Read(<rel-path>/**)", "Tool(mcp__github__*)"],
    "ask":    ["Bash(git push *)"],
    "deny":   ["Read(./.env)", "Bash(rm -rf *)"]
  }
}
```

### 6.2 Rule syntax

| Form | Meaning | Match subject | Constraints |
| :- | :- | :- | :- |
| `Tool` | Any call to that tool | The tool name | Bare name only. No specifier. |
| `Tool(specifier)` | A named sub-entity | The tool plus the entity | The entity is an MCP server name, an agent type, or a plugin-provided namespace. |
| `Tool(pattern)` | A glob over the entity's name | The tool plus the entity | Standard glob. |
| `Bash(cmd prefix)` | The command starts with the prefix | The resolved command | Matched after normalisation. |
| `Read(path)` | A path glob | The read path | Gitignore-style globbing. |
| `Edit(path)` | A path glob | The edited path | Gitignore-style globbing. |
| `Write(path)` | A path glob | The written path | Gitignore-style globbing. |
| `WebFetch(domain:host)` | A domain glob | The target host | — |

### 6.3 Field table — rule-set and rule forms

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `permissions.allow` | `string[]` | No | Rules that permit a call without asking. | The rule syntax of §6.4. |
| `permissions.ask` | `string[]` | No | Rules that require a human decision. | The rule syntax of §6.4. |
| `permissions.deny` | `string[]` | No | Rules that refuse a call. | The rule syntax of §6.4. Evaluated first; a deny shadows an allow in any scope. |
| `permissions.defaultMode` | `enum` | No | The mode used when the session does not select one. | `default` · `acceptEdits` · `plan` · `auto` · `dontAsk` · `bypassPermissions`. `manual` is accepted as an alias for `default`. |
| `permissions.additionalDirectories` | `string[]` | No | Extra directories the session may read and write. | Absolute paths. |
| `permissions.disableBypassPermissionsMode` | `string[]` | No | Scopes in which the bypass mode is refused. | An **administrator-owned** setting; a lower-precedence scope MUST NOT be able to remove an entry from it. |

**The rule forms themselves:**

| Form | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `Tool` | string | Yes | A bare tool name. | Matches every call to that tool. Removal from the schema. |
| `Tool(specifier)` | string | Yes | A tool plus a named entity. | The entity is an MCP server name, an agent type, or a plugin namespace. |
| `Tool(pattern)` | string | Yes | A glob over the entity name. | Standard glob. |
| `Bash(prefix)` | string | Yes | A command prefix. | Matched after normalisation. |
| `Read(path)` / `Edit(path)` / `Write(path)` | string | Yes | A path glob. | Gitignore-style. |
| `WebFetch(domain:host)` | string | Yes | A domain glob. | The host only. |


### 6.4 Semantics — normative

**MUST** — **evaluation order is deny → ask → allow**, and the first matching rule *within* a category wins.

**MUST** — **no specificity sorting**. A broader rule that appears earlier in the same category shadows a narrower one. `Bash(aws *)` denies before `Bash(aws s3 ls)` allows.

**MUST** — **scope does not influence precedence**. The order is determined by the category, not by which file the rule came from.

**MUST** — **normalisation precedes matching**:
- Shell wrappers are stripped: `env`, `sudo`, `nice`, `time`, `xargs`, `bash -c`, `sh -c`, `cmd /c`.
- Leading `VAR=value` assignments are stripped: `FOO=1 git status` matches `Bash(git status)`.
- A compound command is **split**, and **every part** must independently be allowed. `git status && rm -rf /` requires both to be allowed.
- Aliases are canonicalised per shell.

**MUST** — the normalisation is applied to the *command the model wrote*, after wrapper stripping. It does **not** resolve absolute paths or indirect invocation.

**Documented limitation.** A `Bash(...)` deny rule matches the command as written. It does not stop an absolute-path invocation (`/usr/bin/curl`), an indirect invocation (`sh -c 'curl …'`), or a subprocess. The documentation MUST point the operator at the OS sandbox for those cases. This is an honest limitation, not an implementation gap to be papered over.

> **ORIGINAL DESIGN DECISION (Windows shell matching is AST-based; POSIX uses a shell-aware tokenizer).** *Rationale:* on Windows, `rm` and `Remove-Item` are the same operation, and a string matcher is a security hole; `sh -c 'rm -rf /'` is likewise invisible to a prefix matcher. *Alternative considered:* (a) string matching everywhere — rejected, it is a real bypass on the platforms we run on; (b) a full AST on every platform including POSIX — rejected as the immediate target, because POSIX shells have no first-party parser in the runtime; the POSIX front-end normalises to a command/argument structure with a shell-aware tokenizer, which is the strongest available approximation.

### 6.5 The `dontAsk` subtraction

**OBSERVED-COMPATIBLE.** In the `dontAsk` mode, tools whose permission would require a human are **subtracted from the model's schema**. They are not present-and-denied.

**MUST** — the subtraction happens at schema-construction time. The model never sees a tool it cannot use.

**MUST** — this mode fails **by subtraction**, not by error. A run in this mode MUST still start; it simply has fewer tools.

### 6.6 Monotonic keys

**OBSERVED-COMPATIBLE.** Certain configuration keys resolve on a **monotonic lattice** rather than by precedence: the most restrictive value across the consulted scopes wins, and a lower-precedence scope can only ever *restrict* a higher-precedence one, never loosen it.

**MUST** — a key marked monotonic MUST resolve to the most restrictive value among the scopes, and MUST NOT be loosened by a lower-precedence scope.

**MUST** — the resolver MUST record the provenance of a monotonic key's resolved value, so `explain` can show which scope won and which scopes were overridden.

### 6.7 Rule-set resolution across scopes

**MUST** — the three lists from all consulted scopes are concatenated **per category**, in scope order, and then evaluated by the fixed order in §5.5.

**MUST** — the resolved rule set MUST be reportable: a command MUST be able to print every rule that would apply, with its scope and category. This is the operator's only way to debug an unexpected allow or deny.

### 6.8 Error cases

| Situation | Behaviour |
| :- | :- |
| A rule cannot be parsed | `rule_syntax_error` / `input_invalid`. The rule is **ignored**, and a diagnostic naming the rule and the position is emitted on stderr. |
| A rule references an unknown scope or entity | `rule_scope_unknown` / `input_invalid`. The rule is ignored, with a diagnostic. |
| An unknown key inside `permissions` | Ignored, with a diagnostic. The unknown-key rule is the open-set rule (§2.2.1). |
| A rule set is not an array of strings | `input_invalid`. The whole key is ignored, with a diagnostic. |

**MUST** — an invalid rule MUST NOT silently disable enforcement. The diagnostic MUST be emitted even in headless mode, where the reference fails open silently. This is a deliberate divergence (§ "Divergences" in `architecture.md` §1.2).

### 6.9 Worked example

```jsonc
{
  "permissions": {
    "allow": ["Bash(git status)", "Read(**/*.ts)"],
    "ask":    ["Bash(git commit *)"],
    "deny":   ["Read(**/.env)", "Bash(curl *)"]
  }
}
```

Resolution against `run_shell` with `{"command":"git status"}`:

| Step | Outcome |
| :- | :- |
| Schema presence | `run_shell` is present. |
| Validation | Valid. |
| Normalisation | No wrapper, no assignment, no compound. Command = `git status`. |
| Deny rules | `Read(**/.env)` — tool mismatch. `Bash(curl *)` — prefix mismatch. No match. |
| Ask rules | `Bash(git commit *)` — prefix mismatch. No match. |
| Allow rules | `Bash(git status)` — **match**. |
| Tier 2 | Not a protected path; not a destructive command; no consent requirement. |
| Decision | `allow`, `reasonType: "rule"`, `source: "project"`, `matchedRule: "Bash(git status)"`. |

Resolution against `run_shell` with `{"command":"git status && curl https://example.com"}`:

| Step | Outcome |
| :- | :- |
| Normalisation | Compound → two commands: `git status`, `curl https://example.com`. |
| Deny rules | `Bash(curl *)` matches the **second** part. |
| Decision | `deny`, `reasonType: "rule"`, `matchedRule: "Bash(curl *)"`. The whole call is refused; the allowed first part does not save it. |

---

## 7. Interface 5 — Hook interface

**Status: OBSERVED-COMPATIBLE (event names, handler types, exit-code verdict protocol, decision combination).**

### 7.1 Shape

A hook is an external process (or an HTTP endpoint, or an MCP tool, or a prompt) bound to an event name. The harness writes a JSON payload to the hook's stdin and reads the verdict from its exit code and stdout.

```ts
type HookDefinition = {
  event: HookEvent;
  matcher?: string;               // a tool-name or command-name filter
  type: 'command' | 'http' | 'mcp_tool' | 'prompt' | 'agent';
  command?: string;               // for type = command
  url?: string;                   // for type = http
  timeout?: number;               // seconds; a default applies per type
  blocking?: boolean;
};

type HookEvent =
  // The reference's 33 event names, verbatim, in the reference's table order.
  | 'SessionStart' | 'Setup'
  | 'UserPromptSubmit' | 'UserPromptExpansion'
  | 'PreToolUse' | 'PermissionRequest' | 'PermissionDenied'
  | 'PostToolUse' | 'PostToolUseFailure' | 'PostToolBatch'
  | 'Notification' | 'MessageDisplay'
  | 'SubagentStart' | 'SubagentStop'
  | 'TaskCreated' | 'TaskCompleted'
  | 'Stop' | 'StopFailure' | 'TeammateIdle'
  | 'InstructionsLoaded' | 'ConfigChange'
  | 'CwdChanged' | 'DirectoryAdded' | 'FileChanged'
  | 'WorktreeCreate' | 'WorktreeRemove'
  | 'PreCompact' | 'PostCompact'
  | 'PreModelSwitch' | 'PostModelSwitch'
  | 'Elicitation' | 'ElicitationResult'
  | 'SessionEnd';
```

**Evidence.** The 33 names above are the reference's **complete** hook-event set, taken from the
summary table of `agent-reference-shots/area8-auto-mode/docs/hooks.md` (269,866 bytes), which
enumerates 33 rows. The same page carries **33 event-level `###` sections**, and the two sets are
**equal** — no name appears in one and not the other. Both were re-derived mechanically from the
raw file; see `claude-code-evidence.md` R5.

**Correction (2026-10-21).** This union previously carried five names that **do not exist in the
reference at all** — `PromptDispatch`, `PreCompactManual`, `ElicitationResponse`, `SkillLoaded`,
`CommandLoaded` — and omitted fourteen real events (`Setup`, `UserPromptExpansion`,
`MessageDisplay`, `PermissionDenied`, `PostToolBatch`, `SubagentStart`, `StopFailure`,
`InstructionsLoaded`, `CwdChanged`, `DirectoryAdded`, `FileChanged`, `PostCompact`,
`PreModelSwitch`, `PostModelSwitch`). A grep for the five invented names across
`agent-reference-shots/` returns **zero hits in every file**; they were an invention of this
specification, not an observation. The interface spec exists to stop exactly this failure, so
the correction is recorded here rather than applied silently.

**MUST** — the hook event set is an **open set**. A harness MUST ignore a configured event it does not recognise rather than failing to start.

### 7.2 Handler types

| Type | Input | Output | Notes |
| :- | :- | :- | :- |
| `command` | JSON on stdin | Exit code + optional JSON on stdout | The default. |
| `http` | JSON POST body | HTTP response; the body is treated like the stdout JSON | — |
| `mcp_tool` | JSON on stdin | The MCP tool's result | — |
| `prompt` | JSON on stdin | A model-generated response | Used for a judgement that needs a model. |
| `agent` | JSON on stdin | A model's structured output | A more capable judge than `prompt`. |

### 7.3 The input payload

```jsonc
{
  "session_id": "<uuid>",
  "cwd": "<abs-path>",
  "hook_event_name": "PreToolUse",
  "tool_name": "run_shell",
  "tool_input": { "command": "git status" },
  "tool_use_id": "call_<uuid>",
  "permission_mode": "default",
  "stop_hook_active": false,
  "transcript_path": "<abs-path>"
}
```

| Field | Type | Required | Meaning |
| :- | :- | :- | :- |
| `session_id` | `string` | Yes | The session. |
| `cwd` | `string` | Yes | The working directory. |
| `hook_event_name` | `string` | Yes | Which event fired. |
| `tool_name` | `string` | Event-dependent | The tool for tool events. |
| `tool_input` | `object` | Event-dependent | The tool's argument. |
| `tool_use_id` | `string` | Event-dependent | The call id. |
| `permission_mode` | `string` | Yes | The active mode. |
| `stop_hook_active` | `boolean` | Yes | `true` when the hook is re-entered because of its own decision. Prevents an infinite loop. |
| `transcript_path` | `string` | Yes | The transcript file, so a hook can read the conversation. |

### 7.4 The verdict protocol

**OBSERVED-COMPATIBLE.** The verdict is carried by the **exit code**:

| Exit code | Meaning |
| :- | :- |
| `0` | Proceed through the normal permission flow. |
| `2` | Block. stderr is the reason, shown to the model. |
| Any other | Proceed, but the hook's stderr is reported to the user. |

**MUST** — exit code `2` MUST block the operation, and the hook's stderr MUST be passed to the model as the reason.

**MUST** — a hook that exits with a code other than `0` or `2` MUST NOT block the operation, and its first line of stderr MUST be reported to the user.

**MUST** — a hook that times out or crashes MUST be treated as the "other" case: proceed, and report. A broken hook MUST NOT silently deny every operation.

**MUST** — on stdout, a hook MAY emit a JSON object with additional control fields. The recognised fields are:

| Field | Type | Meaning |
| :- | :- | :- |
| `decision` | `enum` | `allow` · `deny` · `ask` · `defer`. |
| `reason` | `string` | The human-readable reason. |
| `hookSpecificOutput.additionalContext` | `string` | Extra context injected into the model's context. Used by `UserPromptSubmit`. |
| `hookSpecificOutput.updatedInput` | `object` | A rewritten tool argument. |
| `systemMessage` | `string` | A message shown to the user, not the model. |
| `continue` | `boolean` | `false` stops the operation. |
| `stopReason` | `string` | The reason shown to the user. |

### 7.5 Semantics — normative

**MUST** — a hook MUST be invoked **once** per matching event, for every registered hook whose matcher matches. A hook that does not match MUST NOT be invoked.

**MUST** — a hook MUST be invoked **before** the operation it guards takes effect. For `PreToolUse` this means before the tool executes; for `UserPromptSubmit` it means before the prompt reaches the model.

**MUST** — the `matcher` MUST be applied to the event's subject: the tool name for tool events, the command name for command events, and the source name for load events. An absent matcher MUST match everything.

**MUST** — the hook's input MUST be the payload in §7.3, with the event-specific fields populated for the event being fired. A hook MUST be able to rely on `session_id`, `cwd`, and `hook_event_name` always being present.

**MUST** — hook execution MUST NOT consume the model's context window. The hook's output reaches the model only via `additionalContext` (an explicit injection) or via a block with exit code `2`.

**MUST** — a hook MUST NOT be able to modify the transcript, the settings, or the session state, except through the documented output fields in §7.4.

**MUST** — a `PreToolUse` hook that rewrites the argument MUST cause the **rewritten** argument to be re-validated against the tool's schema and re-checked by the permission gate. A hook MUST NOT be able to bypass the gate by rewriting an argument.

### 7.6 Combining verdicts — normative

**OBSERVED-COMPATIBLE.** When multiple hooks match the same event, the **most restrictive** verdict applies. The precedence is:

```
deny  >  defer  >  ask  >  allow
```

**MUST** — a `deny` from any matching hook MUST block, regardless of any other hook's `allow`.

**MUST** — a `defer` MUST NOT be treated as an `allow`. It means "this hook has no opinion; continue to the next decision-maker". A `defer` combined only with `allow`s resolves to `allow`.

**MUST** — `ask` MUST resolve to an interactive prompt when the session is interactive, and to a **deny** when it is not. It MUST never auto-approve.

### 7.7 Out-of-band execution

**MUST** — hooks MUST execute **out of band**: they do not consume the model's context window. A hook's output reaches the model only when the hook explicitly injects `additionalContext` or blocks with exit code `2`.

**MUST** — hooks MUST NOT be able to mutate the transcript, the settings, or the session state except through the documented output fields.

### 7.8 Error cases

| Situation | Behaviour |
| :- | :- |
| The hook binary is missing | Treated as the "other" case: proceed, and report that the hook could not be run. |
| The hook times out | Same as above. |
| The hook writes invalid JSON to stdout | The exit code still governs; the invalid JSON is ignored, with a diagnostic. |
| The hook writes to stdout with exit code `0` and no JSON | The hook has no opinion; proceed. |
| The hook exits `2` with empty stderr | Block, with a generic reason. |

### 7.9 Worked example

A `PreToolUse` hook that refuses a destructive command:

```jsonc
// harness → hook (stdin)
{"session_id":"<uuid>","cwd":"<abs-path>","hook_event_name":"PreToolUse",
 "tool_name":"run_shell","tool_input":{"command":"rm -rf build"},"tool_use_id":"call_<uuid>",
 "permission_mode":"default","stop_hook_active":false,"transcript_path":"<abs-path>"}

// hook → harness (stderr, exit 2)
Refusing recursive deletion outside the workspace.
```

The harness blocks the call, passes that stderr to the model as the reason, and emits a denial result.

---

## 8. Interface 6 — MCP client interface

**Status: OBSERVED-COMPATIBLE (transports, scopes, naming convention, metadata keys).**

### 8.1 Shape

```ts
type McpServerConfig = {
  name: string;
  transport: 'stdio' | 'http' | 'sse' | 'ws';
  command?: string;             // stdio
  args?: string[];
  env?: Record<string, string>;
  url?: string;                 // http | sse | ws
  headers?: Record<string, string>;
  scope?: 'local' | 'project' | 'user';
};

type McpTool = {
  name: string;                 // already namespaced
  description: string;
  inputSchema: JSONSchema;
  annotations?: {
    readOnlyHint?: boolean;     // the MCP-standard concurrency key
    destructiveHint?: boolean;
    idempotentHint?: boolean;
    openWorldHint?: boolean;
  };
  _meta?: Record<string, unknown>;
};
```

### 8.2 Transports

**OBSERVED-COMPATIBLE.** Four transports: `stdio`, `http`, `sse`, `ws`.

**MUST** — a server's transport is declared in its configuration; the harness MUST NOT silently fall back to another transport.

### 8.3 Scopes and configuration files

**OBSERVED-COMPATIBLE.** MCP servers are configured at three scopes, backed by two files:

| Scope | File | Location |
| :- | :- | :- |
| `local` | `.mcp.json` | The project root. Committed to the repository. **Inert until approved.** |
| `project` | `.mcp.json` | The project root. Committed. Applies to the project. |
| `user` | The user-scope settings | The user directory. Applies everywhere for that user. |

**MUST** — a server declared in a repository-committed file MUST be **inert until the operator approves it**. The approval MUST be recorded, and the approval state MUST be per-project, so that cloning the repository into a different directory does not inherit an approval.

### 8.4 The tool-naming convention

**OBSERVED-COMPATIBLE.** An MCP tool's exposed name is namespaced:

```
mcp__<server-name>__<tool-name>
```

For a server provided by a plugin:

```
mcp__plugin_<plugin-name>_<server-name>__<tool-name>
```

**MUST** — any character outside `[A-Za-z0-9_-]` in a plugin or server name MUST be replaced with `_`.

**MUST** — a tool name longer than **128 characters** MUST be **omitted** from the tool schema, with a diagnostic. This is a hard limit imposed by the model's tool-name field.

**MUST** — an MCP **prompt** is exposed as a command named `mcp__<server-name>__<prompt-name>`, not as a tool.

### 8.5 The consent metadata key

**OBSERVED-COMPATIBLE.** An MCP server may mark a tool as requiring user interaction through a metadata key:

```jsonc
"_meta": { "anthropic/requiresUserInteraction": true }
```

**MUST** — a tool carrying this key MUST be treated exactly like a built-in consent-required tool (§5.8): it requires explicit human interaction on every call, no allow rule may bypass it, and a non-interactive run MUST deny it.

**MUST** — the namespace prefix in this metadata key is preserved verbatim as an interface fact. It identifies the *semantics*, not the implementation.

### 8.6 Concurrency classes

**OBSERVED-COMPATIBLE.** The `readOnlyHint` annotation is the MCP-standard concurrency key. A tool annotated `readOnlyHint: true` MAY be executed concurrently with other read-only tools.

**MUST** — the harness MUST NOT run two mutating tools concurrently against the same working directory. Read-only tools MAY be parallelised.

### 8.7 Deferred loading

**OBSERVED-COMPATIBLE.** A large MCP server's tools are not all loaded eagerly. The tool set is exposed through a **tool-search** surface: the model asks for a tool by name or keyword, and the matching tool is loaded on demand.

**MUST** — the deferred tools MUST still be discoverable by keyword, and the search MUST be scoped to the servers that are actually connected.

### 8.8 Host-as-MCP-server

**OBSERVED-COMPATIBLE.** The harness can expose its own tools over MCP, letting an external agent drive it.

**MUST** — the MCP surface MUST be a **projection** of the same tool registry the model uses, so a tool exposed externally has the same schema and the same permission behaviour.

**MUST** — the permission gate MUST apply to externally-initiated calls exactly as it applies to model-initiated ones.

### 8.9 Failure isolation

**MUST** — a server that fails to connect MUST NOT prevent the other servers from working.

**MUST** — a connection failure MUST be reported through three channels (§ "Error taxonomy" in `architecture.md` §10.5): the per-server status in the init event, a typed entry in `mcp_server_errors[]`, and a tool-result text that tells the model explicitly that this is a **connection failure** and that the capability may still be present.

**MUST** — a server configuration that is invalid MUST be **skipped with a typed error**, not fatal. The skip categories are: `unknown_type` · `url_missing_type` · `invalid_config` · `reserved_name`.

### 8.10 Semantics — normative

**MUST** — a server's tools MUST be projected into the tool registry under the namespaced name (§8.4), with the server's schema unchanged apart from the name.

**MUST** — the host MUST complete the MCP handshake before projecting a server's tools, and MUST NOT project a server that has not completed it. A projected tool MUST always be executable.

**MUST** — the host MUST NOT apply a permission rule to an MCP tool unless the rule names the namespaced tool. A rule of the form `Tool(mcp__github__*)` MUST match by glob over the namespaced name.

**MUST** — an MCP tool call MUST pass through the same permission gate as a built-in tool. The consent metadata key (§8.5) is the only MCP-specific behaviour.


### 8.11 Field table — `mcp_server_errors[]`

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `name` | `string` | Yes | The server's name. | — |
| `type` | `enum` | Yes | The category. | `unknown_type` · `url_missing_type` · `invalid_config` · `reserved_name` · `connect_failed`. |
| `message` | `string` | Yes | The human-readable detail. | — |

### 8.12 Error cases

| Situation | Behaviour |
| :- | :- |
| The server's configuration names an unknown transport | The server is skipped. `mcp_server_errors[].type = "unknown_type"`. |
| An HTTP/SSE/WS server has no `url` | The server is skipped. `type = "url_missing_type"`. |
| The configuration is malformed | The server is skipped. `type = "invalid_config"`. |
| The server name is reserved | The server is skipped. `type = "reserved_name"`. |
| The connection fails or times out | The server's status is `failed`. The other servers continue to work. The failure is reported through the three channels (§8.9). |
| The tool's input fails the server's schema | `input_invalid`. The error is returned as the tool result with `is_error: true`. |
| The server returns a tool error | `internal` / `mcp_tool_error`. The error text is returned as the tool result. The server stays connected. |
| The server crashes mid-call | `transient` / `mcp_transport_error`. The tool result explicitly states that this is a connection failure and that the capability may still be present. |
| The exposed tool name exceeds 128 characters | The tool is omitted from the schema, with a diagnostic. |
| A server from a committed project file has not been approved | The server is not connected. Its status is `pending`. |
| The host-as-MCP-server surface is invoked externally | The permission gate applies exactly as for a model-initiated call. |


### 8.13 Worked example

```jsonc
// init event
"mcp_servers": [
  { "name": "github", "status": "pending", "source": "user" },
  { "name": "local_tools", "status": "connected", "source": "project" }
],
"mcp_server_errors": [
  { "name": "broken", "type": "invalid_config", "message": "Missing 'url' for transport 'http'." }
]
```

```jsonc
// the tool as the model sees it
{"name":"mcp__github__create_issue",
 "description":"Create an issue in a repository.",
 "inputSchema":{"type":"object","properties":{"repo":{"type":"string"},"title":{"type":"string"}},
   "required":["repo","title"],"additionalProperties":false},
 "annotations":{"readOnlyHint":false}}
```

---

## 9. Interface 7 — Skill and slash-command registration

**Status: OBSERVED-COMPATIBLE (frontmatter field names, the two-flag matrix, the scope resolver's loaded-vs-resolved split) / ORIGINAL (template language details).**

### 9.1 Shape

A skill is a directory or file with a frontmatter block and a Markdown body:

```markdown
---
name: review-changes
description: Review the working tree's changes for correctness.
argument-hint: "[<path>]"
disable-model-invocation: false
user-invocable: true
allowed-tools: read_file, search_text
model: <model-id>
context: fork
agent: reviewer
paths:
  - "src/**"
---

Review the changes under $ARGUMENTS.
```

### 9.2 Field table — skill frontmatter

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `name` | `string` | Yes | The skill's name. | Lowercase, `-` separated. Must be unique across the **resolved** set. |
| `description` | `string` | Yes | What it does and when to use it. | This is the only text loaded at session start (§9.6). |
| `argument-hint` | `string` | No | A usage hint shown in the command menu. | Display only. |
| `disable-model-invocation` | `boolean` | No | The model may not invoke this skill. | Hides the **description** from the model. See the matrix in §9.3. |
| `user-invocable` | `boolean` | No | The user may invoke this skill. | Hides the **command**. Defaults to `true`. See the matrix in §9.3. |
| `allowed-tools` | `string` | Yes | The tools the skill may use. | Comma-separated. Expanded with the invocation's arguments before evaluation. |
| `model` | `string` | No | The model for the skill's context. | — |
| `context` | `enum` | No | How the skill's context is created. | `fork` runs the skill in a subagent with a forked conversation. |
| `agent` | `string` | No | The agent type to run the skill under. | Must name a registered agent. |
| `paths` | `string[]` | No | A conditional activation pattern. | The skill is only offered when the session touches a matching path. |

### 9.3 The invocation matrix — normative

**OBSERVED-COMPATIBLE.** Two independent booleans control who may invoke a skill, and they are **not opposites**.

| `disable-model-invocation` | `user-invocable` | Model may invoke | User may invoke | What is hidden from the model |
| :- | :- | :- | :- | :- |
| `false` | `true` | Yes | Yes | Nothing. |
| `true` | `true` | No | Yes | The **description**. The model does not know the skill exists. |
| `false` | `false` | Yes | No | The **command**. The model sees the description but there is no `/name` command. |
| `true` | `false` | No | No | Both. The skill is invisible to both audiences. |

**MUST** — `disable-model-invocation` MUST hide the description from the model and MUST NOT affect the command's presence in the menu. `user-invocable: false` MUST remove the command and MUST NOT affect the description.

**MUST** — a four-state override MAY be layered on top by configuration, and it MUST affect the listing, the menu, and the tool permission **uniformly**.

### 9.4 Scope resolution — normative

**OBSERVED-COMPATIBLE.** The **loaded** set and the **resolved** set are different sets.

| Set | Contents |
| :- | :- |
| Loaded | Every candidate discovered across every scope, each tagged with its scope. Two skills with the same name in different scopes are **two loaded entries**. |
| Resolved | Exactly one winner per name. |

**MUST** — the resolved set MUST be computed by a scope precedence. **MUST** — the diagnostics MUST report the **loaded** set (so a user can see a shadowed skill) while the model sees the **resolved** set (so the model sees one description per name).

### 9.5 Semantics — normative

**MUST** — a skill MUST be resolved to exactly one definition before invocation (§9.4). The resolution MUST be by name, and the winning definition's scope MUST be recorded.

**MUST** — an invocation MUST establish an invocation context that carries the resolved arguments, the resolved tool allowlist, the resolved agent type, and the resolved context mode, and that context MUST be the sole source of the expansion inputs.

**MUST** — the tool allowlist MUST be applied to the invocation's context. A skill MUST NOT be able to widen its own allowlist through the arguments it was given.

**MUST** — an invocation that resolves to no skill MUST be handled by the dispatcher's "not a command" outcome (§9.8), not by an error.


### 9.6 The body template language

**ORIGINAL.** The body supports these substitutions:

| Token | Expands to |
| :- | :- |
| `$ARGUMENTS` | All arguments, verbatim, space-joined. |
| `$ARGUMENTS[N]` | The *N*-th argument, one-based. |
| `$ARGUMENTS[N,M]` | The arguments from *N* through *M*, inclusive. |
| `$1`, `$2`, … | Declared named arguments. |
| `${SKILL_DIR}` | The skill's directory. |
| `${SESSION_ID}` | The current session id. |

**MUST** — substitution runs in the body **and** in the `allowed-tools` patterns. **MUST** — substituted values MUST NOT be re-scanned for further substitutions. A substituted value containing `$ARGUMENTS` MUST be emitted literally.

**MUST** — an injected shell command (a fenced block whose command is preceded by the render-time execution marker) MUST be evaluated by the injected-command policy (§9.7), not executed unconditionally.

### 9.7 The two-tier loading

**MUST** — at session start, the harness MUST load only each skill's **name and description**, not its body. **MUST** — the body MUST be loaded only at invocation.

**MUST** — the listing MUST be budgeted. Names MUST always be kept. Descriptions MUST be truncated to fit the budget, and truncation MUST be **least-used-first**, so a rarely used skill loses its description before a frequently used one does. A digest sidecar MUST record the full, untruncated set.

### 9.8 The injected-command policy

**ORIGINAL DESIGN DECISION (deny by default for untrusted skill sources; always log).**

**MUST** — a skill body MAY embed shell commands that the loader executes at render time. The harness MUST classify the skill's source by trust:

| Source trust | Default behaviour |
| :- | :- |
| `trusted` (user scope, or explicitly trusted) | Execute, and log. |
| `untrusted` (project scope, plugin scope) | **Deny** by default, or prompt in an interactive session. |

**MUST** — every execution MUST be logged with the resolved command pattern. **MUST** — the policy MUST be settable from managed configuration. **MUST** — a denied or failed injected command MUST **abort the invocation**, not produce a partially rendered body.

*Rationale:* a skill in a repository is code the repository ships. Executing it silently at render time is remote code execution by repository. *Alternative considered:* (a) match the observed silent default — rejected; (b) prompt on every injection — rejected, it makes the feature unusable headless and creates a prompt storm; (c) deny only for project scope — rejected, a user-scope skill can be planted by a malicious plugin; trust is classified by **source trust**, which is a managed setting.

### 9.9 Slash-command registration

**OBSERVED-COMPATIBLE.** A slash command is a **prefix of the first user message** — there is no separate command channel.

**MUST** — the dispatcher MUST recognise at most **six** skill chains in one message.

**MUST** — the dispatch MUST have exactly three outcomes, and the outcome MUST be observable in the terminal envelope:

| Outcome | Condition | Envelope field | Model turns |
| :- | :- | :- | :- |
| Local handler | The command can be satisfied without the model | `local_command: "<handler>"` | 0 |
| Model-delivered prompt | The command expands to a prompt | The expanded prompt is sent | ≥ 1 |
| Not a command | Nothing matches in this session | The text is sent; the model explains it is not a command | ≥ 1 |

**MUST** — a command's `allowed-tools` MUST be applied for the turn the command produces, and the expansion MUST be applied to the tools as well as the body.

### 9.10 The command menu

**OBSERVED-COMPATIBLE.** The menu is a **fuzzy matcher** over names and aliases.

**MUST** — the matcher MUST match from the start of a name **or** from a word within it. **MUST** — the `:`, `_`, and `-` separators MUST be ignored for matching, so `/adddir` matches `/add-dir`. **MUST** — a match on an alias MUST resolve to the canonical name.

**MUST** — a non-matching input MUST highlight nothing and MUST produce a "did you mean" suggestion.

### 9.11 Error cases

| Situation | Behaviour |
| :- | :- |
| The frontmatter is missing or unparseable | The skill is skipped, with a diagnostic. |
| `name` collides with a higher-precedence scope's skill | The lower-precedence one is shadowed. The diagnostic names both. |
| `allowed-tools` names an unknown tool | The unknown tool is dropped, with a diagnostic. The invocation proceeds. |
| `agent` names an unknown agent type | The skill is skipped, with a diagnostic. |
| `context: fork` but no agent type is resolvable | The invocation runs in the main context, with a diagnostic. |
| An injected command is denied | The invocation is aborted; the model receives the denial reason. |

### 9.12 Worked example

```yaml
---
name: review-changes
description: Review the working tree's changes for correctness and report findings.
argument-hint: "[<path>]"
disable-model-invocation: false
user-invocable: true
allowed-tools: read_file, search_text
context: fork
agent: reviewer
---
```

Invocation: `/review-changes src/api`

The harness resolves the command, substitutes `$ARGUMENTS` → `src/api` in the body and in the `allowed-tools` patterns, forks a `reviewer` agent with a copy of the conversation so far, restricts that agent's tool set to exactly `{read_file, search_text}`, and returns the agent's report as the command's result.

---

## 10. Interface 8 — Subagent spawn and join

**Status: OBSERVED-COMPATIBLE (spawn fields, the event set, the caps, the ledger) / ORIGINAL (the exact spawn API shape).**

### 10.1 Shape

```ts
type SpawnRequest = {
  description: string;           // a short label, 3–5 words
  prompt: string;                // the task
  subagentType: string;          // a registered agent type
  model?: ModelSelection;
  effort?: EffortLevel;
  runInBackground?: boolean;
  name?: string;                 // when teams are enabled
  isolation?: 'worktree' | 'remote';
  forkContext?: boolean;
};

type SpawnResult = {
  taskId: string;
  runId: string;
  toolUseId: string;
  status: 'completed' | 'failed' | 'killed' | 'refused' | 'partial';
  report: string;                // the summary the parent receives
  refusal?: 'depth_limit' | 'concurrency_limit' | 'budget' | 'no_tools';
  spawnDepth: number;
  isBackgrounded: boolean;
};
```

### 10.2 Field table — `SpawnRequest`

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `description` | `string` | Yes | A short label. | 3–5 words. |
| `prompt` | `string` | Yes | The task. | The worker's sole instruction. |
| `subagentType` | `string` | Yes | The agent type. | Must be registered. An unknown type is refused with `subagent_no_tools` or an unknown-type error. |
| `model` | `ModelSelection` | No | The worker's model. | Resolved per role; a worker's `main` role is separate from the parent's. |
| `effort` | `EffortLevel` | No | The worker's effort. | — |
| `runInBackground` | `boolean` | No | Run without blocking the parent. | The parent continues; the result arrives as a task notification. |
| `name` | `string` | No | The worker's name in a team. | Required when teams are enabled. |
| `isolation` | `enum` | No | The filesystem isolation mode. | `worktree` · `remote`. |
| `forkContext` | `boolean` | No | Copy the parent's conversation so far. | Defaults to `true` when the parent has context worth inheriting. |

### 10.3 Semantics — normative

**MUST** — the worker's tool set is an **exact allowlist**, not a hint. A worker declared with `tools: Read, Grep` has exactly those two tools and no others.

**MUST** — the parent's view of a worker is the worker's **final report only**. The parent MUST NOT see the worker's intermediate tool calls or their outputs.

**MUST** — the worker's report MUST be **scanned for instruction-shaped content** before it is handed to the parent. A subagent is a trust boundary; its output is untrusted input.

**MUST** — the merge happens in exactly **one** place: the parent's next tool result.

**MUST** — a partial result (the worker hit its turn cap) MUST be preserved and marked partial, with a continuation handle. Partial output MUST NOT be discarded.

### 10.4 The caps

**OBSERVED-COMPATIBLE.**

| Cap | Default | Env override | Behaviour on breach |
| :- | :- | :- | :- |
| Concurrent subagents per session | 20 | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | **Refused**, not queued. `refusal: "concurrency_limit"`. |
| Spawn depth below the main conversation | 3 | `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` | **Refused**. `refusal: "depth_limit"`. |
| Concurrent workflow agents per run | 16 (range 1–256) | `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` | **Refused**. |
| Combined subagent description tokens | 15,000 | — | The listing is truncated. |

**MUST** — a refusal MUST be a distinct outcome from a failure, and MUST be counted separately in the ledger (`refused` vs `failed`).

### 10.5 The event set

**OBSERVED-COMPATIBLE.**

```jsonc
// system/task_started
{"type":"system","subtype":"task_started",
 "task_id":"task_<uuid>","run_id":"run_<uuid>","tool_use_id":"call_<uuid>",
 "description":"Review the auth module","subagent_type":"reviewer","is_backgrounded":false,
 "spawn_depth":1,"task_type":"local","prompt":"Review <rel-path> for correctness."}

// system/task_progress
{"type":"system","subtype":"task_progress","task_id":"task_<uuid>",
 "description":"Review the auth module",
 "usage":{"total_tokens":18422,"tool_uses":11,"duration_ms":41203},"last_tool_name":"read_file"}

// system/task_notification
{"type":"system","subtype":"task_notification","task_id":"task_<uuid>","status":"completed",
 "result":"Reviewed 3 files; found one issue."}
```

### 10.6 The ledger

**OBSERVED-COMPATIBLE.** The terminal envelope carries the whole-tree subagent statistics.

```jsonc
"subagent_stats": {
  "spawned": 3,
  "requested": { "background": 1, "foreground": 2, "unset": 0 },
  "started_in_background": 1,
  "max_depth": 2,
  "spawned_by_subagents": 1,
  "completed": 2,
  "failed": 0,
  "killed": { "parent": 0, "user": 0, "system": 0 },
  "refused": { "depth_limit": 0, "concurrency_limit": 0, "budget": 0 },
  "by_type": { "reviewer": 2, "explorer": 1 }
}
```

**MUST** — `killed`, `failed`, and `refused` MUST be distinct counters. A refusal is a policy outcome, not a failure.

> **ORIGINAL DESIGN DECISION (a forked skill counts in the ledger).** *Rationale:* a forked skill runs a real inference loop with real tokens; excluding it understates actual spend. *Alternative considered:* (a) match the observed behaviour — rejected, it miscounts spend; (b) count it but report it separately — rejected, it adds a category for the same thing.

### 10.7 The agent registry

**OBSERVED-COMPATIBLE.** The registry is an **incremental attachment**: added types, removed types, built-in types, and user/project/plugin types. The first payload is distinguishable from a delta.

```jsonc
"agents": [
  { "type": "general-purpose", "description": "General agent for research and multi-step tasks.",
    "tools": ["read_file","search_text","run_shell"], "model": "<model-id>" }
]
```

**MUST** — a removal MUST take effect mid-session.

**MUST** — the model-visible rendering of a restricted agent MUST be an explicit **exclusion** list, and of an inheriting agent an **inclusion** list. It MUST be unambiguous either way.

### 10.8 The job registry

**OBSERVED-COMPATIBLE.** Background work is a file-backed state machine.

```
<state-root>/jobs/<short-id>/
├── state.json
├── timeline.jsonl
└── tmp/
```

`state.json` MUST persist the **intent** (a natural-language statement of the job's purpose) separately from the mechanical command, so a roster is readable by a human without parsing a command line. It MUST also persist the launch-time model selection and the provider environment so a restarted job can be relaunched onto the same model, and both the current session id and the resume session id so a restarted job links back to its original transcript.

### 10.9 The roster

**OBSERVED-COMPATIBLE.**

```jsonc
{ "proto": 1, "supervisorPid": 4821, "updatedAt": "<iso8601>", "workers": { } }
```

**MUST** — the roster MUST carry a `proto` version field. A reader MUST refuse to write a roster whose `proto` it does not understand.

### 10.10 The agent roster output

**OBSERVED-COMPATIBLE.** The scripting interface.

```jsonc
[
  { "pid": 4821, "cwd": "<abs-path>", "kind": "interactive",
    "startedAt": 1761000000000, "sessionId": "<uuid>", "name": "main",
    "status": "busy" },
  { "pid": 4830, "cwd": "<abs-path>", "kind": "background",
    "startedAt": 1761000001000, "sessionId": "<uuid>", "name": "worker-1",
    "status": "waiting", "id": "task_<uuid>", "state": "working" }
]
```

| Field | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `pid` | `number` | Yes | The process id. | — |
| `cwd` | `string` | Yes | The working directory. | — |
| `kind` | `enum` | Yes | The session kind. | `interactive` · `background`. |
| `startedAt` | `number` | Yes | The start time. | Unix milliseconds. |
| `sessionId` | `string` | Yes | The session. | — |
| `name` | `string` | Yes | The session's name. | — |
| `status` | `enum` | Yes | The session's activity. | `busy` · `waiting` · `idle`. |
| `id` | `string` | Background only | The job id. | — |
| `state` | `enum` | Background only | The job's state. | `working` · `blocked` · `done` · `failed` · `stopped`. |

### 10.11 Worker coordination

**OBSERVED-COMPATIBLE.**

```jsonc
// <state-root>/tasks/<team>/<n>.json
{"id":3,"subject":"Refactor the parser","description":"Split the tokenizer out.",
 "status":"in_progress","blocks":[4],"blockedBy":[2]}

// <state-root>/teams/<team>/inboxes/<agent>.json
{"messages":[{"from":"lead","to":"explorer","content":"Focus on the tokenizer.","ts":"<iso8601>"}]}
```

**MUST** — the task model MUST be a DAG: `blocks` and `blockedBy` express ordering, which a flat checklist cannot.

**MUST** — a `.lock` file MUST be the claiming primitive, and a stale-lock sweep MUST release locks orphaned by a crash.

### 10.12 Worktree isolation

**OBSERVED-COMPATIBLE.** Isolation is a **filesystem** concern, enforced at four points: the file-edit path, the command working directory, git redirects, and command shape. It is **not optional**.

**MUST** — the isolation layer MUST have no configuration path that disables it.

### 10.13 Error cases

| Situation | Behaviour |
| :- | :- |
| The spawn depth exceeds the cap | Refused. `refusal: "depth_limit"`. No worker is created. |
| The concurrency cap is reached | Refused. `refusal: "concurrency_limit"`. No worker is created. |
| The budget cap is reached | Refused. `refusal: "budget"`. |
| The resolved tool allowlist is empty | Refused. `refusal: "no_tools"`. |
| `subagentType` is unknown | Refused with `unknown_tool`. |
| The worker errors | `status: "failed"`. The parent's turn continues. |
| The worker is killed by the parent | `status: "killed"`, `killed.parent` incremented. |
| The worker exceeds its turn cap | `status: "partial"` with a continuation handle. Partial output is preserved. |
| The worktree cannot be created | The spawn fails with the underlying git error; the parent continues. |

---

### 10.14 Worked example

A spawn and its completion, as the parent sees it:

```jsonc
// the parent's call
{"type":"assistant","message":{"role":"assistant","content":[
  {"type":"tool_use","id":"call_<uuid>","name":"delegate",
   "input":{"description":"Review the auth module","prompt":"Review <rel-path> for correctness.",
            "subagent_type":"reviewer"}}]},
 "session_id":"<uuid>","uuid":"<uuid>","timestamp":"<iso8601>"}

// the spawn is announced
{"type":"system","subtype":"task_started","task_id":"task_<uuid>","run_id":"run_<uuid>",
 "tool_use_id":"call_<uuid>","description":"Review the auth module","subagent_type":"reviewer",
 "is_backgrounded":false,"spawn_depth":1,"task_type":"local",
 "prompt":"Review <rel-path> for correctness."}

// progress while the worker runs
{"type":"system","subtype":"task_progress","task_id":"task_<uuid>",
 "description":"Review the auth module",
 "usage":{"total_tokens":18422,"tool_uses":11,"duration_ms":41203},"last_tool_name":"read_file"}

// the merge — the parent's tool result carries only the worker's report
{"type":"user","message":{"role":"user","content":[
  {"tool_use_id":"call_<uuid>","type":"tool_result",
   "content":"Reviewed 3 files; found one issue in the token refresh path."}]},
 "parent_tool_use_id":null,"session_id":"<uuid>","uuid":"<uuid>","timestamp":"<iso8601>",
 "tool_use_result":{"stdout":"Reviewed 3 files; found one issue in the token refresh path.",
   "stderr":"","interrupted":false,"isImage":false,"noOutputExpected":false}}
```

The parent's stream shows the spawn, the progress, and the merged report. The worker's eleven intermediate tool calls are **not** in the parent's stream; they appear in the worker's own transcript, attributed with `parent_tool_use_id: "call_<uuid>"`.


## 11. Interface 9 — Session and state interface

**Status: OBSERVED-COMPATIBLE (the transcript layout, the entry types, the resume semantics, the path convention).**

### 11.1 Shape

```ts
type SessionStore = {
  create(opts: CreateSessionOptions): SessionHandle;
  append(sessionId: string, entry: TranscriptEntry): void;
  read(sessionId: string): TranscriptEntry[];
  compact(sessionId: string, trigger: 'auto' | 'manual'): CompactBoundary;
  resume(sessionId: string, opts?: ResumeOptions): ResumedSession;
  list(filter?: SessionFilter): SessionSummary[];
  fork(sessionId: string): SessionHandle;
  clear(sessionId: string): void;
};
```

### 11.2 Semantics — normative

**MUST** — the transcript MUST be the **source of truth** for the session. The model-visible history, the cost ledger, the permission mode, and the checkpoint store MUST all be reconstructable from it alone.

**MUST** — the transcript MUST be **append-only** during a session. A compaction MUST NOT rewrite the entries it replaced; it MUST append a boundary that records what survived.

**MUST** — every entry MUST carry a `uuid`, and conversation entries MUST carry a `parentUuid` linking to the preceding entry, **except** at a compaction boundary, where `parentUuid` is `null` and `logicalParentUuid` carries the link.

**MUST** — the store MUST be **session-scoped**. A session MUST NOT read another session's entries, even in the same project directory.

**MUST** — a read MUST tolerate a truncated final line (a partial write from a crash) by skipping it, and MUST report the truncation.


### 11.3 The transcript format

**OBSERVED-COMPATIBLE.** The transcript is **newline-delimited JSON**: one typed JSON object per line.

**MUST** — the path is `<state-root>/projects/<sanitised-cwd>/<session-id>.jsonl`, where the sanitised cwd replaces every non-alphanumeric character with `-`.

**MUST** — the transcript MUST be **append-only**. A reader MUST tolerate a truncated final line (a partial write from a crash) by skipping it.

### 11.4 Transcript entry types

| Type | Purpose |
| :- | :- |
| `user` | A user message or a mid-turn injection. |
| `assistant` | An assistant message. |
| `attachment` | A labelled environment or instruction attachment. |
| `system` | A system event (compaction boundary, and others). |
| `mode` | A permission-mode change. |
| `permission-mode` | The recorded permission mode. |
| `last-prompt` | The most recent user prompt. |
| `title` | The session's generated title. |
| `cost-state` | A cost-ledger snapshot. |
| `queue-operation` | A queued-message operation. |
| `file-history-snapshot` | A checkpoint snapshot record. |
| `file-history-delta` | A checkpoint delta record. |
| `request-shape` | The shape of a provider request, for debugging. |
| `request-blob` | The full request body. |
| `request` | The provider request reference. |
| `mode-latch` | A latched mode. |

**MUST** — metadata entries MUST be interleaved with the conversation entries, so a reader can reconstruct the session state by a single pass.

### 11.5 The cost ledger

**OBSERVED-COMPATIBLE.** The ledger is a session-lifetime accumulator persisted in the transcript:

| Field | Meaning |
| :- | :- |
| `totalCostUsd` | The accumulated cost. |
| `totalDurationMs` | The wall-clock duration. |
| `totalApiDurationMs` | The time spent waiting on the provider. |
| `totalToolDurationMs` | The time spent executing tools. |
| `linesAdded` / `linesRemoved` | The lines of code changed. |
| `modelUsage` | The per-model token and cost breakdown. |

**MUST** — the ledger MUST be the source of truth for the session's cost, and the terminal envelope's `total_cost_usd` MUST agree with it.

**MUST** — `linesAdded` and `linesRemoved` MUST be tracked. The session is measured in both money and lines changed.

### 11.6 The resume interface

**OBSERVED-COMPATIBLE.**

```ts
type ResumeOptions = {
  fork?: boolean;            // mint a new session id; the original is untouched
  resumeInterrupted?: boolean;// resume the interrupted turn, if any
};
```

**MUST** — the resume target MUST resolve from a session id, a session title, or a transcript path.

**MUST** — resume MUST reconstruct the model-visible history across compaction boundaries, using the boundary's `preservedMessages.uuids` and its `logicalParentUuid`. A resume that follows only `parentUuid` MUST NOT be used — it loses the connection across a boundary.

**MUST** — resume MUST restore the **observed-paths set**, so a read-before-edit gate stays satisfied across a restart.

**MUST** — resume MUST NOT mutate the original transcript.

**MUST** — resume MUST emit a fresh init event with a **new** `uuid` and the **same** `session_id`.

**MUST** — a forked session MUST mint a new session id and MUST leave the original transcript byte-identical.

### 11.7 The compaction interface

```ts
type CompactBoundary = {
  content: string;            // "Conversation compacted"
  level: 'info' | 'warn';
  trigger: 'auto' | 'manual';
  preTokens: number;
  postTokens: number;
  cumulativeDroppedTokens: number;
  durationMs: number;
  preCompactDiscoveredTools: string[];
  preservedSegment: { headUuid: string; anchorUuid: string; tailUuid: string };
  preservedMessages: { anchorUuid: string; uuids: string[] };
  parentUuid: null;
  logicalParentUuid: string;
};
```

| Field | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `content` | `string` | Yes | The banner text. | — |
| `level` | `enum` | Yes | The severity. | `info` · `warn`. |
| `trigger` | `enum` | Yes | What caused it. | `auto` · `manual`. |
| `preTokens` | `number` | Yes | The token count before compaction. | — |
| `postTokens` | `number` | Yes | The token count after. | Must be less than `preTokens`. |
| `cumulativeDroppedTokens` | `number` | Yes | The session-lifetime total dropped. | Monotonically non-decreasing. |
| `durationMs` | `number` | Yes | How long the compaction took. | — |
| `preCompactDiscoveredTools` | `string[]` | Yes | The tool surface known at compaction time. | — |
| `preservedSegment` | `object` | Yes | The head/anchor/tail triple. | All three UUIDs. |
| `preservedMessages` | `object` | Yes | The surviving message ids. | `anchorUuid` plus the `uuids` list. |
| `parentUuid` | `null` | Yes | Always null at a boundary. | The ordinary parent chain is deliberately broken. |
| `logicalParentUuid` | `string` | Yes | The tail of the preserved segment. | The substitute link. |

**MUST** — the boundary MUST be a **structured, addressable record**, not a summary blob. **MUST** — `cumulativeDroppedTokens` MUST be monotonic across the session.

### 11.8 Memory

**OBSERVED-COMPATIBLE.** The memory directory is derived from the repository, so that worktrees and subdirectories of one repository share it.

```
<state-root>/projects/<project-slug>/memory/
├── MEMORY.md
├── <topic-1>.md
└── <topic-2>.md
```

**MUST** — the index MUST be loaded at session start, truncated at whichever of **200 lines or 25 KB** comes first. Content past the limit MUST NOT be loaded.

**MUST** — the memory subtree MUST be **excluded from the transcript retention sweep**. It persists until it is edited or deleted.

**MUST** — after the model writes to the index, the harness MUST measure it against the limits. At a near limit, the harness MUST prompt the model to shorten it. Over a limit, the write MUST succeed but the harness MUST return an error telling the model to rewrite, because everything past the limit is dropped on the next load.

**MUST** — the 200-line/25 KB limit applies **only** to the memory index. Instruction files are loaded in full up to a much larger cap (4 MiB observed); a larger file MUST be skipped with a diagnostic.

### 11.9 Checkpoints

**OBSERVED-COMPATIBLE.**

**MUST** — a checkpoint MUST be created per turn. **MUST** — the retention window MUST be 100 checkpoints per session. **MUST** — checkpoints MUST cover only changes made by the file-editing tools — **not** changes made by shell commands — and MUST skip symlinked and hard-linked files.

**MUST** — the recovery affordances MUST be: restore code and conversation · restore conversation only · restore code only · summarise from here · summarise up to here.

**MUST** — the UI MUST state that remote side effects are not undoable.

### 11.10 The on-disk layout

**OBSERVED-COMPATIBLE.**

| Path | Format | Owner | Lifecycle |
| :- | :- | :- | :- |
| `<root>/projects/<cwd-slug>/<session-id>.jsonl` | JSONL | Session store | Append-only; swept by the retention policy. |
| `<root>/projects/<project-slug>/memory/MEMORY.md` | Markdown | Memory | Excluded from the sweep. |
| `<root>/projects/<project-slug>/memory/<topic>.md` | Markdown | Memory | Excluded from the sweep. |
| `<root>/file-history/<session-id>/<16-hex>@v<N>` | Raw snapshot | Checkpoint store | Bounded to 100 recent checkpoints. |
| `<root>/tasks/<team>/<n>.json` + `.lock` | JSON | Job supervisor | Per-team; stale-lock sweep. |
| `<root>/teams/<team>/inboxes/<agent>.json` | JSON | Job supervisor | Per-team. |
| `<root>/jobs/<id>/state.json` | JSON | Job supervisor | Per-job; updated live. |
| `<root>/jobs/<id>/timeline.jsonl` | JSONL | Job supervisor | Append-only. |
| `<root>/jobs/<id>/tmp/` | mixed | Job supervisor | Working files. |
| `<root>/daemon/roster.json` | JSON with `proto` | Supervisor | Replaced atomically. |
| `<root>/plans/<slug>.md` | Markdown | Planning | Retained after acceptance or abandonment. |
| `<root>/tool-results/<id>.txt` | Text | Output persistence | Per overflow. |
| `<root>/settings.json` | JSON | Config | User scope. |
| `<root>/settings.local.json` | JSON | Config | Project-local scope. |
| `<root>/.mcp.json` | JSON | Config | Project scope; inert until approved. |

**MUST** — every on-disk format MUST be plain JSON or JSONL. **MUST** — every non-trivial on-disk structure MUST carry a format version.

### 11.11 Error cases

| Situation | Behaviour |
| :- | :- |
| The session id is not a valid UUID | `invalid_session_id` / `input_invalid`. Exit `1`. |
| No such session | `no_conversation_found` / `not_found`. Exit `1`. |
| Resume with no id in a non-interactive session | `resume_requires_identifier` / `precondition_failed`. Exit `1`. |
| The transcript's final line is truncated | The line is skipped; the rest of the session loads. |
| The transcript contains an unknown entry type | The entry is skipped, with a diagnostic. |
| The state root does not exist | It is created. |
| The state root is not writable | `conflict`. Exit `1`. |
| Disk full during an append | `conflict`, with the class distinguished: the write never started · it started and the data was lost · the temp directory was refused on an ownership check. |

---

### 11.12 Worked example

```jsonc
// <state-root>/projects/-Users-dev-repo/<session-id>.jsonl
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Fix the failing test."}]},"uuid":"<uuid>","timestamp":"<iso8601>","sessionId":"<uuid>"}
{"type":"assistant","message":{"id":"msg_<uuid>","role":"assistant","content":[{"type":"text","text":"On it."}],"model":"<model-id>","stop_reason":null,"usage":{"input_tokens":100,"output_tokens":4}},"uuid":"<uuid>","timestamp":"<iso8601>","parentUuid":"<uuid>","sessionId":"<uuid>"}
{"type":"mode","mode":"default","uuid":"<uuid>","timestamp":"<iso8601>"}
{"type":"cost-state","totalCostUsd":0.0142,"totalDurationMs":8420,"totalApiDurationMs":8010,"totalToolDurationMs":410,"linesAdded":12,"linesRemoved":3,"modelUsage":{"<model-id>":{"inputTokens":2410,"outputTokens":120,"costUSD":0.0142}},"uuid":"<uuid>","timestamp":"<iso8601>"}
{"type":"title","title":"Fix the failing test","uuid":"<uuid>","timestamp":"<iso8601>"}
```

Note the `parentUuid` chain on the assistant entry: it links to the preceding entry's `uuid`. A `compact_boundary` entry deliberately sets `parentUuid` to `null` and supplies `logicalParentUuid` instead — a resume that follows only `parentUuid` loses the chain at that point.


## 12. Interface 10 — Model adapter interface

**Status: ORIGINAL (the adapter boundary) with OBSERVED-COMPATIBLE vocabulary for the effort levels, the error categories, and the role names.**

### 12.1 Shape

```ts
type ProviderRequest = {
  model: string;
  messages: ProviderNeutralMessage[];
  tools: ToolSchema[];
  maxOutputTokens: number;
  effort?: EffortLevel;
  reasoning?: { enabled: boolean; display: 'hidden' | 'summarized' | 'full' };
  stopSequences?: string[];
  metadata?: Record<string, string>;
};

type ProviderResponse = {
  responseId: string;
  blocks: ResponseBlock[];
  stopReason: 'end_turn' | 'tool_use' | 'max_tokens' | 'refusal' | 'other';
  usage: Usage;
  modelId: string;
  provider: string;
};

interface ModelAdapter {
  readonly id: string;
  readonly capabilities: AdapterCapabilities;
  complete(req: ProviderRequest, signal: AbortSignal): Promise<ProviderResponse>;
  stream(req: ProviderRequest, signal: AbortSignal): AsyncIterable<StreamChunk>;
}

type AdapterCapabilities = {
  toolCalling: boolean;
  thinking: boolean;
  effortControl: boolean;
  streaming: boolean;
  structuredOutput: boolean;
  promptCaching: boolean;
  contextWindow: number;         // the default when the model is unrecognised
  maxOutputTokens: number;
  costTable?: CostTable;         // absent → costBasis = "unknown"
};
```

### 12.2 Field table — `ProviderRequest`

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `model` | `string` | Yes | The model id. | An unrecognised id MUST NOT crash; the harness assumes a 200,000-token window and emits a diagnostic. |
| `messages` | `ProviderNeutralMessage[]` | Yes | The conversation. | Provider-neutral: `user` · `assistant` roles with typed content blocks. |
| `tools` | `ToolSchema[]` | Yes | The tools offered to the model. | Only tools present in the registry. |
| `maxOutputTokens` | `number` | Yes | The output cap. | — |
| `effort` | `EffortLevel` | No | The reasoning effort. | `low` · `medium` · `high` · `xhigh` · `max`. |
| `reasoning.display` | `enum` | No | How reasoning is surfaced. | `hidden` · `summarized` · `full`. |
| `stopSequences` | `string[]` | No | Provider stop sequences. | — |
| `metadata` | `object` | No | Opaque pass-through. | The harness MUST NOT read it. |

### 12.3 Field table — `ProviderResponse`

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `responseId` | `string` | Yes | The provider's response id. | Recorded as `request_id` on the assistant event. |
| `blocks` | `ResponseBlock[]` | Yes | The content blocks. | `text` · `thinking` · `tool_use`. |
| `stopReason` | `enum` | Yes | Why the provider stopped. | Mapped into the event's `stop_reason`. |
| `usage` | `Usage` | Yes | The token accounting. | Provider-neutral. |
| `modelId` | `string` | Yes | The model that served it. | — |
| `provider` | `string` | Yes | The provider. | Recorded on the assistant event. |

### 12.4 Semantics — normative

**MUST** — an adapter is a **pure translation layer**. It MUST NOT decide what the model should do, MUST NOT repair a malformed tool call, and MUST NOT synthesise a capability the provider lacks.

**MUST** — the harness MUST NOT require any provider capability. A provider supporting none of {tool calling, thinking, effort, streaming} still yields a working harness: no tools → a text-only agent; no streaming → a buffered agent.

**MUST** — the adapter MUST own: endpoints, authentication, transport, retries, streaming-fragment translation, token accounting, and the mapping of provider errors into the provider-independent category enum (§12.7).

**MUST** — no provider-specific type may appear above the adapter boundary. A lint rule MUST enforce this.

### 12.5 The model-resolution chain

**OBSERVED-COMPATIBLE** (the chain and the governance keys).

| Level | Source | Notes |
| :- | :- | :- |
| 1 | The CLI `--model` flag | Highest user-level precedence. |
| 2 | A per-role override map | Fields: model, effort, fast mode, fallback model. |
| 3 | The environment variable | Each key has an explicit env binding. |
| 4 | The settings file's top-level `model` key | An initial selection, not enforcement. |
| 5 | The default | The newest alias the build knows. |

**MUST** — resolution MUST be **per role**. The roles MUST include at least: `main` · `summariser` (compaction) · `title` · `classifier` · `advisor`.

### 12.6 The governance keys

**OBSERVED-COMPATIBLE.**

| Key | Type | Effect | Monotonic? |
| :- | :- | :- | :- |
| `availableModels` | `string[]` | Restricts which models may be named or offered. | No. |
| `enforceAvailableModels` | `boolean` | Extends the allowlist to the default resolution. | No. |
| `deniedModels` | `string[]` | Blocks specific model ids or versions. | **Yes** — restrictive. |
| `modelOverrides` | `object` | Per-role model, effort, fast mode, fallback model. | No. |
| `modelPicker` | `object` | Configures or removes the picker. | No. |
| `fallbackModel` | `string[]` | The automatic fallback chain. | No. **At most three entries.** |
| `maxEffortLevel` | `enum` | Caps the effort slider. | **Yes** — restrictive. |

### 12.7 The effort levels and the error categories

**OBSERVED-COMPATIBLE.** Effort levels: `low` · `medium` · `high` · `xhigh` · `max`.

**MUST** — an unrecognised effort value MUST produce a **warning and be ignored**; the run continues at the current effort. An unknown effort has a safe default.

**MUST** — by contrast, an invalid auto-compact window MUST be a **hard error**, because it has no safe default and mis-sizing the context budget is worse than refusing to start.

**Provider-independent error categories** (the harness branches on meaning, not on provider):

| Category | Retryable | Typical cause |
| :- | :- | :- |
| `authentication_failed` | No | Missing or invalid credentials. |
| `organization_not_allowed` | No | The account may not use the model. |
| `account_on_hold` | No | An account-state condition. |
| `billing_error` | No | An account-state condition. |
| `rate_limit` | Yes | Throttling. |
| `overloaded` | Yes | Capacity exhausted upstream. |
| `invalid_request` | No | The request was rejected. |
| `model_not_found` | No | The model id is unknown. |
| `server_error` | Yes | A transient upstream failure. |
| `max_output_tokens` | No | The output cap was hit. |
| `credential_error` | No | A credential was rejected. |
| `unknown` | Depends | Anything unrecognised. |

**MUST** — the HTTP status MUST be carried **separately** from the category. **MUST** — the indefinite-retry watchdog MUST be scoped to the capacity classes only (`rate_limit`, `overloaded`, `server_error`); the account-state categories MUST NOT be retried indefinitely.

### 12.8 The self-hosted adapter

**ORIGINAL.**

| Concern | Requirement |
| :- | :- |
| Endpoint | A configurable base URL, including loopback and private ranges. TLS verification configurable, defaulting to on. |
| Authentication | A local token file, or a helper command invoked per connection, with a documented cache TTL. |
| Model identity | A locally assigned id. The harness MUST accept an id it does not recognise, assume the default window, and emit a diagnostic. |
| Cost | **No price table.** `costBasis` becomes `"unknown"` and `costUSD` is `0`. |
| Capabilities | Declared at registration time in `capabilities`. |

**MUST** — the cost ledger MUST remain meaningful when `costBasis` is `"unknown"`: token counts stay authoritative, and a monetary budget cap MUST fall back to a token-denominated cap with an explicit note that the monetary cap is not enforceable.

**MUST** — the `contextWindow` override MUST be honoured: `CLAUDE_CODE_MAX_CONTEXT_TOKENS` overrides the assumed window for an unrecognised model.

### 12.9 Error cases

| Situation | Behaviour |
| :- | :- |
| The provider returns a retryable category | The adapter retries with backoff and emits `system/api_retry`. The category and the HTTP status are carried separately. |
| The provider returns a terminal category | The adapter MUST NOT retry. The turn fails with `error_during_execution`. |
| The failure occurs after content was committed | The adapter MUST NOT re-send the request. The committed content is preserved and the incompleteness warning is issued. |
| The failure occurs before any content was committed | The adapter MAY retry, a bounded number of times, quickly. |
| The model id is not recognised | The harness assumes a 200,000-token window and emits a diagnostic. The run continues. |
| `CLAUDE_CODE_MAX_CONTEXT_TOKENS` is set | It overrides the assumed window. |
| The effort value is not recognised | A warning is emitted and the value is ignored. The current effort is retained. |
| The provider does not support tool calling | The registry MUST contain no tools. The harness runs as a text-only agent. |
| The provider does not support streaming | The adapter buffers the response and emits it as a single complete block. |
| The provider has no price table | `costBasis` MUST be `"unknown"` and `costUSD` MUST be `0`. A monetary budget cap MUST fall back to a token-denominated cap, with a note that the monetary cap is not enforceable. |
| The `fallbackModel` chain has more than three entries | The configuration is invalid. The excess entries are ignored, with a diagnostic. |


### 12.10 Worked example

```ts
const adapter: ModelAdapter = {
  id: 'local',
  capabilities: {
    toolCalling: true, thinking: true, effortControl: true, streaming: true,
    structuredOutput: true, promptCaching: false,
    contextWindow: 200000, maxOutputTokens: 32000,
    // costTable intentionally absent → costBasis = "unknown"
  },
  async complete(req, signal) { /* … */ },
  async *stream(req, signal) { /* … */ },
};
```

---

## 13. Interface 11 — Config and settings interface

**Status: OBSERVED-COMPATIBLE (scope names, the settings file names, the merge semantics, the managed-source merge modes).**

### 13.1 Shape

```ts
type SettingsScopes = {
  managed: JsonObject;        // OS-anchored, administrator-owned
  user: JsonObject;           // <root>/settings.json
  project: JsonObject;        // <root>/.claude/settings.json in the project
  local: JsonObject;          // <root>/.claude/settings.local.json in the project
  flags: JsonObject;          // parsed from argv
  env: JsonObject;            // the environment's explicit bindings
};

type ResolvedSettings = {
  value: JsonObject;          // the flattened result
  provenance: Record<string, { scope: string; key: string }>;  // per resolved key
  diagnostics: SettingsDiagnostic[];
};
```

### 13.2 The scope order

**OBSERVED-COMPATIBLE.** Precedence, highest first:

1. **Managed** (administrator policy)
2. **Command-line flags**
3. **Local** (project-local, git-ignored)
4. **Project** (committed to the repository)
5. **User**
6. **Environment**
7. **Defaults**

**MUST** — the resolver MUST be a **generic fold over the scopes** that consults a typed registry entry for each key. The resolver MUST NOT contain per-key special cases.

### 13.3 The registry entry

```ts
type SettingsEntry = {
  key: string;
  type: 'string' | 'number' | 'boolean' | 'string[]' | 'object';
  scopes: Scope[];              // which scopes may set it
  default?: unknown;
  merge: 'replace' | 'union' | 'deep' | 'monotonic-restrict';
  monotonic?: boolean;          // restrictive lattice
  envVar?: string;              // the explicit environment binding
  deprecated?: string;          // the replacement key
};
```

**MUST** — a key marked `monotonic` MUST resolve to the most restrictive value among the scopes and MUST NOT be loosened by a lower-precedence scope.

**MUST** — the resolver MUST record the **provenance** of every resolved key, so an `explain` command can print where a value came from.

### 13.4 Field table — scope and registry

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `key` | `string` | Yes | The dotted settings key. | Unique across the registry. |
| `type` | `enum` | Yes | The value type. | `string` · `number` · `boolean` · `string[]` · `object`. |
| `scopes` | `Scope[]` | Yes | Which scopes may set it. | `managed` · `user` · `project` · `local` · `flags` · `env`. |
| `default` | `unknown` | No | The value used when no scope sets it. | MUST match `type`. |
| `merge` | `enum` | Yes | How multiple scopes combine. | `replace` · `union` · `deep` · `monotonic-restrict`. |
| `monotonic` | `boolean` | No | The key resolves on a restrictive lattice. | When `true`, `merge` MUST be `monotonic-restrict`. |
| `envVar` | `string` | No | The environment variable bound to the key. | Exactly one per key. |
| `deprecated` | `string` | No | The replacement key. | The old key is still honoured. |

**The scope order** (highest precedence first) is: `managed` · `flags` · `local` · `project` · `user` · `env` · `defaults`.


### 13.5 The managed-source merge modes

**OBSERVED-COMPATIBLE.** An administrator's configuration file may specify how it combines with other sources:

| Mode | Behaviour |
| :- | :- |
| `merge` | The managed values are combined with the others by the normal rules. |
| `locks` | The managed values **replace** the others for the keys they set, and the others may not override them. |
| `highest-priority-only` | Only the managed source is consulted for the keys it sets. |

### 13.6 Scope semantics

**MUST** — the **project** scope MUST be excluded from the auto-mode rule resolution. A repository may not configure the auto-mode policy.

**MUST** — the `"$defaults"` splice: a value of the literal string `"$defaults"` in a rule list is replaced by the corresponding default list. **MUST** — the splice MUST apply at merge time, not at parse time, so that a later override of the defaults is reflected.

### 13.7 The settings files

**OBSERVED-COMPATIBLE.**

| File | Scope | Notes |
| :- | :- | :- |
| `<root>/settings.json` | User | — |
| `<root>/.claude/settings.json` | Project | Committed to the repository. |
| `<root>/.claude/settings.local.json` | Local | Git-ignored by convention. |
| `<root>/.claude/.mcp.json` | Project (MCP) | Inert until approved. |
| `<root>/config.json` | Global | A small set of global keys. |

### 13.8 Unknown keys

**MUST** — an unknown settings key MUST be **ignored**, and MUST be reported as a diagnostic. It MUST NOT cause the file to be rejected.

**MUST** — an invalid **value** for a known key MUST be reported as a diagnostic and the key MUST fall back to its default. **MUST** — in headless mode the diagnostic MUST still be emitted on stderr. This is a deliberate divergence from the observed behaviour, which fails open silently.

**MUST** — the settings registry MUST be publishable as a **JSON Schema**, and there MUST be a validator that can be pointed at a *directory* of settings files and emits a stable JSON envelope.

### 13.9 Error cases

| Situation | Behaviour |
| :- | :- |
| A settings file is not valid JSON | The file is ignored, with a diagnostic naming the file and the parse position. The other scopes still resolve. |
| A key is unknown | Ignored, with a diagnostic. The file is **not** rejected. |
| A value has the wrong type | The key falls back to its default, with a diagnostic. |
| A monotonic key resolves to a less restrictive value in a lower-precedence scope | The more restrictive value wins. The provenance records the scope that won and the scopes that were overridden. |
| A scope is not permitted for a key | The scope's value for that key is ignored, with a diagnostic. |
| A deprecated key is present | The key is honoured, and the resolved provenance is `deprecated:<replacement>`. |
| A managed source declares `locks` | Its values replace the others for the keys it sets, and the others may not override them. |
| A managed source declares `highest-priority-only` | Only the managed source is consulted for the keys it sets. |
| The `"$defaults"` splice is used in a project-scope rule list | The splice is applied at merge time. The project scope is excluded from auto-mode rule resolution. |
| The settings root is not writable | `conflict`. The run fails with exit code `1`. |
| An environment variable bound to a key holds an unparseable value | The key falls back to its default, with a diagnostic on stderr. |


### 13.10 Worked example

```jsonc
// <root>/settings.json  (user scope)
{
  "model": "<model-id>",
  "permissions": {
    "allow": ["Bash(git status)", "Read(**/*.ts)"],
    "ask": ["Bash(git push *)"],
    "deny": ["Read(**/.env)"]
  },
  "cleanupPeriodDays": 30,
  "env": { "NODE_ENV": "development" }
}
```

```jsonc
// resolved provenance
{
  "model":      { "scope": "user",    "key": "model" },
  "permissions.allow": { "scope": "user", "key": "permissions.allow" },
  "cleanupPeriodDays": { "scope": "user", "key": "cleanupPeriodDays" },
  "cleanupPeriodDays.deprecated": "cleanupPeriodDaysLegacy"
}
```

---

## 14. Interface 12 — Context-compaction interface

**Status: OBSERVED-COMPATIBLE (the boundary record) / ORIGINAL (the trigger policy).**

### 14.1 Shape

```ts
type CompactionService = {
  shouldCompact(ctx: ContextState): boolean;
  compact(ctx: ContextState, trigger: 'auto' | 'manual'): Promise<CompactBoundary>;
  estimateTokens(messages: ProviderNeutralMessage[]): number;
  describe(ctx: ContextState): ContextReport;
};
```

### 14.2 The trigger

**OBSERVED-COMPATIBLE.** The auto-compact window is configurable and MUST be in the range **100,000 – 1,000,000** tokens, with `k` and `M` suffixes accepted.

**MUST** — an auto-compact window outside that range MUST be a **hard error** at startup, not a warning.

**MUST** — an unrecognised model id MUST default to a **200,000**-token window, and `CLAUDE_CODE_MAX_CONTEXT_TOKENS` MUST override the assumed window.

### 14.3 Field table — compaction inputs

| Name | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `window` | `number` | Yes | The effective context window in tokens. | The model's window, or the 200,000 default for an unrecognised model, overridden by `CLAUDE_CODE_MAX_CONTEXT_TOKENS`. |
| `autoCompactWindow` | `number` | Yes | The threshold at which auto-compaction triggers. | 100,000–1,000,000. Outside the range is a **hard error**. |
| `messages` | `ProviderNeutralMessage[]` | Yes | The current model-visible history. | — |
| `preserveHeadTokens` | `number` | Yes | The tokens kept verbatim at the head. | — |
| `preserveTailTokens` | `number` | Yes | The tokens kept verbatim at the tail. | — |
| `summariserRole` | `string` | Yes | The role that produces the summary. | `summariser`. Resolved independently of the `main` role. |
| `trigger` | `enum` | Yes | What caused the compaction. | `auto` · `manual`. |
| `projectInstructions` | `string` | No | The project section the compactor reads. | Optional customisation. |


### 14.4 The context report

```ts
type ContextReport = {
  totalTokens: number;
  window: number;
  breakdown: {
    systemPrompt: number;
    toolDefinitions: number;
    attachments: number;
    history: number;
    skills: number;
  };
  projectedAfterTools: number;
  wouldCompact: boolean;
};
```

**MUST** — the breakdown MUST be available to a diagnostic command. An operator who cannot see where the tokens went cannot tune the window.

### 14.5 The compaction algorithm

**MUST** — the window MUST be selected as: a head segment, an anchor message, and a tail segment. **MUST** — the middle MUST be replaced by a summary written as a **user-role message**. **MUST** — the boundary MUST be appended to the transcript with `parentUuid: null` and a `logicalParentUuid` pointing at the tail of the preserved segment.

**MUST** — the summary MUST be produced by the `summariser` role, so it can use a cheaper model than the main loop.

**MUST** — three customisation routes MUST exist: a project-instruction section the compactor reads, a pre-compaction hook with a `trigger` field distinguishing `manual` from `auto`, and a manual compaction command.

### 14.6 The thrash detector

**MUST** — the harness MUST detect the pattern "compaction succeeded, then the window was immediately refilled" repeating several times in a row, and MUST **stop and report** rather than continuing to spend on a loop that makes no progress.

### 14.7 The context-overflow ladder

**MUST** — on a context overflow, the harness MUST attempt, in order:

1. Reduce the output cap and retry.
2. Compact, when no smaller output cap can fit.
3. Fail with a diagnostic naming **which part of the request dominates**: the conversation's own content, versus the system prompt, tool definitions, and attachments.

**MUST** — a single-exchange conversation MUST NOT be described as "compacted" when there is nothing to summarise; it MUST take the third branch.

### 14.8 Semantics — normative

**MUST** — compaction MUST be invoked by the context manager between turns, never mid-tool-execution.

**MUST** — the compaction summary MUST be written as a **user-role message**, so that the model's request assembly treats it uniformly with any other user content.

**MUST** — the boundary MUST be appended to the transcript as a typed entry, and the model-visible history MUST be reconstructed from it. A compaction that does not leave a boundary record MUST NOT be considered complete.

**MUST** — the boundary MUST be emitted as a `system/compact_boundary` event in the observable stream.


### 14.9 Error cases

| Situation | Behaviour |
| :- | :- |
| The auto-compact window is outside 100,000–1,000,000 | A **hard error** at startup. Exit `1`. The run does not start. |
| The auto-compact window has an unparseable suffix | A hard error. Only `k` and `M` suffixes are accepted. |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` is invalid | The same hard error. An invalid window has no safe default, so the run MUST refuse to start. |
| The model id is unrecognised | The window defaults to 200,000 tokens, with a diagnostic. |
| The summariser role's model is unavailable | The main model is used as the summariser, with a diagnostic. |
| The summariser call fails | The compaction is abandoned; the history is unchanged; the run continues with the full history and will hit the overflow ladder. |
| The summary does not reduce the token count | The compaction is abandoned, with a diagnostic. A boundary MUST NOT be written for a no-op. |
| The boundary would produce `postTokens` greater than `preTokens` | The compaction is abandoned, with a diagnostic. |
| Compaction is immediately followed by a refill, repeatedly | The thrash detector stops the run and reports it. |
| The request exceeds the window and cannot be compacted | The overflow ladder (§14.6) applies: reduce the output cap → compact → fail with a diagnostic naming the dominant part. |
| A single-exchange conversation overflows | There is nothing to summarise, so the third branch applies. It MUST NOT be reported as a compaction. |


### 14.10 Worked example

```jsonc
{"type":"system","subtype":"compact_boundary","content":"Conversation compacted","level":"info",
 "compactMetadata":{
   "trigger":"auto","preTokens":207387,"postTokens":18950,"cumulativeDroppedTokens":188437,
   "durationMs":40314,"preCompactDiscoveredTools":["web_fetch","search_text"],
   "preservedSegment":{"headUuid":"<uuid>","anchorUuid":"<uuid>","tailUuid":"<uuid>"},
   "preservedMessages":{"anchorUuid":"<uuid>","uuids":["<uuid>","<uuid>","<uuid>"]}},
 "parentUuid":null,"logicalParentUuid":"<uuid>"}
```

---

## 15. Interface 13 — Event-stream interface

**Status: OBSERVED-COMPATIBLE (the whole taxonomy) with one deliberate extension (`structured_output`).**

### 15.1 The framing

**OBSERVED-COMPATIBLE.** The stream is **newline-delimited JSON**. Each line is one event object.

**MUST** — every event MUST carry a `type`. **MUST** — the discriminator is the `type`/`subtype` pair; there is no third tag.

**MUST** — the stream MUST NOT end at the terminal result event. Consumers MUST drain it.

### 15.2 The event union

| `type` | `subtype` | Payload |
| :- | :- | :- |
| `system` | `init` | The session descriptor (§15.3). |
| `system` | `hook_started` | `hook_event_name`, `hook_name`, `status`. |
| `system` | `hook_response` | `hook_event_name`, `hook_name`, `status`, `duration_ms`. |
| `system` | `permission_denied` | `tool_name`, `tool_use_id`, `tool_input`, `decision_reason_type`, `decision_reason`. |
| `system` | `task_started` | `task_id`, `run_id`, `tool_use_id`, `description`, `subagent_type`, `is_backgrounded`, `spawn_depth`, `task_type`, `prompt`. |
| `system` | `task_progress` | `task_id`, `description`, `usage{total_tokens, tool_uses, duration_ms}`, `last_tool_name`. |
| `system` | `task_notification` | `task_id`, `status`, `result`. |
| `system` | `compact_boundary` | The boundary record (§14.7). |
| `system` | `turn_duration` | `duration_ms`, `messageCount`, `entrypoint`, `cwd`, `gitBranch`, `slug`. |
| `system` | `api_retry` | `attempt`, `max_retries`, `retry_delay_ms`, `error_status`, `error`, `uuid`, `session_id`, optional `no_response{waited_ms, retry_wait_ms}`. |
| `system` | `thinking_tokens` | `estimated_tokens`, `estimated_tokens_delta`, `session_id`, `uuid`. |
| `system` | `informational` | A banner string. |
| `system` | `worker_shutting_down` | A reason string. |
| `system` | `plugin_install` | The plugin name and its status. |
| `assistant` | — | `message{...}`, `parent_tool_use_id`, `session_id`, `uuid`, `timestamp`, `request_id`, optional `wire_tool_inputs`, optional `thinking_duration_ms`, `thinking_display`. |
| `user` | — | `message{...}`, `parent_tool_use_id`, `session_id`, `uuid`, `timestamp`, optional `tool_use_result`, optional `tool_result_meta[]`. |
| `result` | — | The terminal envelope (§16). |

### 15.3 The init descriptor

**OBSERVED-COMPATIBLE.**

| Field | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `type` | `string` | Yes | `system`. | — |
| `subtype` | `string` | Yes | `init`. | — |
| `cwd` | `string` | Yes | The working directory. | — |
| `original_cwd` | `string` | Yes | The directory the session started in. | Differs from `cwd` after a `cd`. |
| `additional_directories` | `string[]` | Yes | Extra permitted directories. | — |
| `session_id` | `string` | Yes | The session id. | — |
| `uuid` | `string` | Yes | The event id. | — |
| `tools` | `string[]` | Yes | The tools offered to the model. | — |
| `mcp_servers` | `object[]` | Yes | Per-server status. | `{name, status, source}`. `status` ∈ `pending` \| `connected` \| `failed`. |
| `model` | `string` | Yes | The resolved model. | — |
| `permissionMode` | `string` | Yes | The active mode. | — |
| `slash_commands` | `string[]` | Yes | The available commands. | — |
| `terminal_slash_commands` | `string[]` | Yes | The commands that act on the terminal. | — |
| `agents` | `object[]` | Yes | The agent registry. | — |
| `skills` | `object[]` | Yes | The skill registry (descriptions only). | — |
| `plugins` | `object[]` | Yes | The loaded plugins. | `{name, path, source}`. |
| `capabilities` | `string[]` | Yes | The open-set feature advertisement. | **Open set.** A consumer MUST ignore unknown entries. |
| `output_style` | `string` | Yes | The active output style. | — |
| `memory_paths` | `object` | Yes | The memory locations. | — |
| `apiKeySource` | `string` | Yes | Where the credential came from. | — |
| `claude_code_version` | `string` | Yes | The product version. | — |
| `analytics_disabled` | `boolean` | Yes | Whether analytics are off. | — |
| `product_feedback_disabled` | `boolean` | Yes | Whether feedback prompts are off. | — |
| `fast_mode_state` | `string` | Yes | The fast-mode state. | `off` \| `on` \| … |
| `fast_mode_disabled_reason` | `string` | No | Why fast mode is unavailable. | — |
| `per_turn_effort_active` | `boolean` | Yes | Whether per-turn effort is in effect. | — |
| `view_mode` | `string` | Yes | The output style's view mode. | — |
| `messaging_socket_path` | `string` | No | The messaging socket. | — |
| `powershell_path` | `string` | No | The resolved PowerShell. | Windows only. |

**MUST** — the init event MUST be emitted **after** any startup-hook lifecycle events.

### 15.4 The assistant event

**OBSERVED-COMPATIBLE.** One assistant event is emitted **per content block**. Blocks belonging to one model response share the same `message.id` and `request_id`.

```jsonc
{"type":"assistant",
 "message":{"id":"msg_<uuid>","type":"message","role":"assistant",
   "content":[{"type":"tool_use","id":"call_<uuid>","name":"list_files","input":{"pattern":"*"}}],
   "model":"<model-id>","stop_reason":null,
   "usage":{"input_tokens":1204,"output_tokens":8},
   "provider":"<provider>","context_management":null},
 "parent_tool_use_id":null,"session_id":"<uuid>","uuid":"<uuid>",
 "timestamp":"<iso8601>","request_id":"req_<uuid>",
 "wire_tool_inputs":{"call_<uuid>":{"pattern":"*"}}}
```

| Field | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `message.content[]` | `object[]` | Yes | The block(s). | `text` · `thinking` · `tool_use`. |
| `message.stop_reason` | `string` | Yes | Why the provider stopped. | `null` while a tool call is pending. |
| `message.usage` | `object` | Yes | The token accounting. | — |
| `message.provider` | `string` | Yes | The serving provider. | — |
| `message.context_management` | `object` | No | Provider-side context edits. | — |
| `parent_tool_use_id` | `string` | No | The call id of the spawning tool, for a nested message. | `null` at the top level. |
| `uuid` | `string` | Yes | The event id. | — |
| `timestamp` | `string` | Yes | The event time. | ISO-8601, UTC. |
| `request_id` | `string` | Yes | The provider request id. | Shared across the blocks of one response. |
| `wire_tool_inputs` | `object` | No | The raw arguments as the provider sent them. | Keyed by `tool_use_id`. |
| `thinking_duration_ms` | `number` | No | The thinking duration. | — |
| `thinking_display` | `string` | No | How thinking is displayed. | — |

### 15.5 The user event

**OBSERVED-COMPATIBLE.**

```jsonc
{"type":"user",
 "message":{"role":"user","content":[
   {"tool_use_id":"call_<uuid>","type":"tool_result","content":"…"}]},
 "parent_tool_use_id":null,"session_id":"<uuid>","uuid":"<uuid>","timestamp":"<iso8601>",
 "tool_use_result":{"type":"text","file":{"filePath":"<abs-path>","content":"…",
   "numLines":6,"startLine":1,"totalLines":6}},
 "tool_result_meta":[{"id":"call_<uuid>",
   "permission_decision":{"decision":"accept","source":"config","reason_type":"rule"}}]}
```

| Field | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `message.content[]` | `object[]` | Yes | The blocks. | `tool_result` · `text` · `attachment`. |
| `tool_use_result` | `unknown` | No | The structured payload. | The dual-representation contract (§4.4). |
| `tool_result_meta` | `object[]` | No | The decision records. | Keyed by `tool_use_id`. |
| `isCompactSummary` | `boolean` | No | Marks a compaction summary. | Present on the summary message. |

### 15.6 The invariants — normative

1. One assistant event per content block, with a shared `message.id` across the blocks of one response.
2. Correlation is by `tool_use_id`, never by position. Results MAY arrive out of order.
3. A denied call still occupies a `tool_result` slot, with `is_error: true`.
4. `system/permission_denied` precedes the corresponding `user/tool_result`.
5. The `result` event does not end the stream; consumers MUST drain it.
6. `result.result` is populated only on the `success` subtype.
7. Cost, usage, turn count, and session id are present on **every** result subtype.
8. The init manifest is emitted after any startup-hook lifecycle events.
9. Diagnostics go to stderr, never to stdout.
10. Subagent activity is attributed with `parent_tool_use_id` on every nested message, plus `agent_id`, `subagent_type`, and `task_description`.

### 15.7 Semantics — normative

**MUST** — the event stream MUST be the **single source of truth** for every observable behaviour. The transcript, the terminal envelope, the TUI render, and the MCP projection MUST all be derivable from it.

**MUST** — the stream MUST be **line-delimited** and each line MUST be independently parseable, so a consumer can process events as they arrive and can recover from a truncated final line.

**MUST** — the event union MUST be **closed on the producer side and open on the consumer side**. A producer emits only known `type`/`subtype` pairs; a consumer ignores what it does not recognise.

**MUST** — the init event MUST be the **first** event of a session, and MUST describe the session completely enough that a consumer can render the session's capabilities without another query.

**MUST** — every event MUST carry a `uuid` and a `timestamp`. Events that belong to one model response MUST share a `request_id`.


### 15.8 Error cases

| Situation | Behaviour |
| :- | :- |
| A line in the stream is not valid JSON | The consumer skips it and reports the line number. A producer MUST NOT emit one. |
| The stream contains an unknown `type` | Ignored, per the open-set rule. |
| The stream contains an unknown `subtype` for a known `type` | Ignored. |
| The terminal envelope is missing | The consumer MUST treat the stream as incomplete. |
| The terminal envelope's `subtype` is unknown | Treated as a failure with an unknown outcome. The `is_error` flag remains authoritative. |
| Two events share a `uuid` | The second is a duplicate; the consumer MUST ignore it. |
| A `tool_result` references an unknown `tool_use_id` | The consumer MUST report an orphan and continue. |
| A `tool_result` arrives before its `tool_use` | The consumer MUST buffer it until the call is seen, or report an orphan after a bounded wait. |
| `system/permission_denied` is absent but the result is `is_error` | The consumer MUST NOT assume a denial; the error may be a tool fault. |
| The `result` event is followed by more events | The consumer MUST drain them. |
| `usage` and `modelUsage` disagree | `modelUsage` is authoritative for whole-tree spend. |


### 15.9 Worked example — a complete minimal stream

```jsonc
{"type":"system","subtype":"init","session_id":"<uuid>","uuid":"<uuid>","cwd":"<abs-path>",
 "model":"<model-id>","permissionMode":"default","tools":["list_files"],
 "capabilities":["tools"],"claude_code_version":"<version>"}
{"type":"assistant","message":{"id":"msg_<uuid>","role":"assistant",
 "content":[{"type":"text","text":"Listing files."}],"model":"<model-id>","stop_reason":null,
 "usage":{"input_tokens":10,"output_tokens":5}},
 "session_id":"<uuid>","uuid":"<uuid>","timestamp":"<iso8601>","request_id":"req_<uuid>"}
{"type":"assistant","message":{"id":"msg_<uuid>","role":"assistant",
 "content":[{"type":"tool_use","id":"call_<uuid>","name":"list_files","input":{"pattern":"*"}}],
 "model":"<model-id>","stop_reason":null,"usage":{"input_tokens":10,"output_tokens":5}},
 "session_id":"<uuid>","uuid":"<uuid>","timestamp":"<iso8601>","request_id":"req_<uuid>",
 "wire_tool_inputs":{"call_<uuid>":{"pattern":"*"}}}
{"type":"user","message":{"role":"user","content":[
   {"tool_use_id":"call_<uuid>","type":"tool_result","content":"a.ts\nb.ts"}]},
 "session_id":"<uuid>","uuid":"<uuid>","timestamp":"<iso8601>",
 "tool_use_result":{"filenames":["a.ts","b.ts"],"durationMs":4,"numFiles":2,
   "truncated":false,"totalMatches":2,"countIsComplete":true},
 "tool_result_meta":[{"id":"call_<uuid>",
   "permission_decision":{"decision":"accept","source":"config","reason_type":"rule"}}]}
{"type":"result","subtype":"success","is_error":false,"result":"Two files.","session_id":"<uuid>",
 "uuid":"<uuid>","num_turns":1,"stop_reason":"end_turn","total_cost_usd":0.0012,
 "usage":{"input_tokens":20,"output_tokens":10},"modelUsage":{},"permission_denials":[],
 "safety_stops":0,"queued_turn_count":0,"result_index":0}
```

---

## 16. Interface 14 — CLI surface

**Status: OBSERVED-COMPATIBLE (flag names, output modes, exit codes, the headless semantics).**

### 16.1 Output modes

**OBSERVED-COMPATIBLE.**

| Mode | stdout | Exit |
| :- | :- | :- |
| `text` (default) | The final assistant text. | 0 on success. |
| `json` | **Exactly one** JSON object — the terminal envelope. | 0 on success; non-zero on failure. |
| `stream-json` | Newline-delimited JSON events; the last is the terminal envelope. | 0 on success; non-zero on failure. |

**MUST** — the `json` mode MUST emit exactly one object and nothing else on stdout.

**MUST** — diagnostics MUST go to stderr in every mode. **MUST** — the diagnostic format MUST be a stable `[harness:<event>]` prefix followed by a JSON payload.

### 16.2 Exit codes

**OBSERVED-COMPATIBLE.**

| Code | Meaning |
| :- | :- |
| `0` | Success. **A run in which every tool call was denied still exits `0`** — a denial is a policy outcome, not a failure. |
| `1` | Startup, flag, or limit failure: an unknown option, an invalid flag combination, an invalid session id, no such session, a limit reached. |
| `143` | Terminated by SIGTERM. The in-progress turn is left unfinished and records no result. Session-end hooks still run. |

**MUST** — a semantic failure MUST be reported **in-band**: `is_error: true` plus a machine-readable `subtype`. The exit code is a coarse signal.

**MUST** — a consumer MUST NOT test `result != null` to detect failure. On the budget-exhausted path, `result` is absent while `errors[]` carries the reason. The `subtype` is the authoritative discriminator.

### 16.3 The flag surface

**OBSERVED-COMPATIBLE.** The flags below are the compatibility surface.

**Run shape**

| Flag | Type | Meaning |
| :- | :- | :- |
| `--print`, `-p` | boolean | Headless mode. Read from stdin when no prompt argument is given. |
| `--output-format` | `text` \| `json` \| `stream-json` | The stdout format. |
| `--input-format` | `text` \| `stream-json` | The stdin format for a streamed headless run. |
| `--verbose` | boolean | Include the full assistant messages, not just the final text. |
| `--include-partial-messages` | boolean | Emit partial (streamed) assistant messages. |
| `--include-hook-events` | boolean | Emit hook events in the stream. |
| `--forward-subagent-text` | boolean | Forward subagent text to the parent stream. |
| `--bare` | boolean | The determinism profile (§16.5). |
| `--restricted` | boolean | The restricted profile (§16.5). |
| `--safe-mode` | boolean | No writes, no execution, no network. |
| `--system-prompt-snapshot` | `string` | A path to a recorded system prompt. |
| `--append-system-prompt` | `string` | Text appended to the system prompt. |

**Tools and permissions**

| Flag | Type | Meaning |
| :- | :- | :- |
| `--tools` | `string` | An explicit tool list. |
| `--allowedTools`, `--allowed-tools` | `string` | Additive allowlist. |
| `--disallowedTools`, `--disallowed-tools` | `string` | Subtractive list. |
| `--permission-mode` | `enum` | `default` \| `acceptEdits` \| `plan` \| `auto` \| `dontAsk` \| `bypassPermissions` (plus `manual` as an alias for `default`). |
| `--permission-prompts` | `boolean` | Whether to prompt. |
| `--permission-prompt-tool` | `string` | An MCP tool used to ask the permission question. |
| `--dangerously-skip-permissions` | boolean | The bypass mode. Requires a second opt-in. |
| `--allow-dangerously-skip-permissions` | boolean | The second opt-in for the bypass mode. |

**Model**

| Flag | Type | Meaning |
| :- | :- | :- |
| `--model` | `string` | The model alias or id. |
| `--effort` | `enum` | `low` \| `medium` \| `high` \| `xhigh` \| `max`. |
| `--fallback-model` | `string` | The fallback chain (at most three). |
| `--autocompact` | `boolean` | Enable or disable auto-compaction. |

**Limits and output shape**

| Flag | Type | Meaning |
| :- | :- | :- |
| `--max-turns` | `number` | The turn cap. |
| `--max-budget-usd` | `number` | The spend cap. |
| `--json-schema` | `string` | Require the final response to match a schema. |
| `--session-id` | `string` | The session id to use. |
| `--resume`, `-r` | `string` | Resume by id, title, or transcript path. |
| `--continue`, `-c` | boolean | Resume the most recent session. |
| `--fork-session` | boolean | Fork on resume. |
| `--no-session-persistence` | boolean | Do not write a transcript. |
| `--add-dir` | `string` | Add a permitted directory. |
| `--worktree`, `-w` | `boolean` | Run in a worktree. |

**Configuration and extensions**

| Flag | Type | Meaning |
| :- | :- | :- |
| `--settings` | `string` | A settings file to load. |
| `--setting-sources` | `string` | Which scopes to load. |
| `--mcp-config` | `string` | An MCP configuration file. |
| `--strict-mcp-config` | `boolean` | Ignore the discovered MCP configuration. |
| `--plugin-dir` | `string` | A local plugin directory. |
| `--plugin-url` | `string` | A plugin source. |
| `--agents` | `string` | An agent definition file. |
| `--agent` | `string` | The agent type to use. |
| `--disable-slash-commands` | `string` | Disable named commands. |

**Diagnostics and background**

| Flag | Type | Meaning |
| :- | :- | :- |
| `--debug` | `boolean` | Debug logging. |
| `--debug-file` | `string` | The debug log path. |
| `--version`, `-v` | boolean | Print the version. |
| `--init-only` | `boolean` | Initialise and exit. |
| `--bg` | `boolean` | Run in the background. |
| `--cloud` | `boolean` | Run in the cloud environment. |
| `--exec` | `string` | Execute a command in the session. |

### 16.4 Semantics — normative

**MUST** — the CLI MUST be a **thin front end**. It MUST own argument parsing, flag-combination validation, output-mode selection, and the exit code, and nothing else. All session behaviour MUST come from the core.

**MUST** — the CLI MUST validate its flags **before** any model call, and MUST NOT spend a token on an invocation it will reject.

**MUST** — stdout MUST carry **only** the selected output format's payload. Every diagnostic, warning, and progress message MUST go to stderr, in every mode and every profile.

**MUST** — the exit code MUST be derived from the run's terminal outcome: `0` for success, `1` for a startup, flag, or limit failure, `143` for SIGTERM.

**MUST** — the CLI MUST NOT require a terminal. Every flag MUST work identically with a piped stdin, a redirected stdout, and no TTY at all.


### 16.5 Flag-combination validation

**MUST** — the CLI MUST validate flag combinations **before any model call**, and MUST reject an invalid combination with a non-zero exit and a diagnostic on stderr, so a bad invocation never reaches the model and never costs a token.

Known-invalid combinations:

| Combination | Reason |
| :- | :- |
| `--dangerously-skip-permissions` without `--allow-dangerously-skip-permissions` | The bypass mode requires two opt-ins. |
| `--dangerously-skip-permissions` while running as a superuser | Refused. |
| `--dangerously-skip-permissions` in an untrusted workspace | Refused. |
| `--json-schema` with `--output-format text` | The schema has no output channel. |
| `--resume` and `--session-id` together | Ambiguous target. |
| `--output-format json` with `--include-partial-messages` | `json` emits exactly one object. |

### 16.6 Execution profiles

**OBSERVED-COMPATIBLE.**

| Profile | Ambient state read | Write tools | Execution | Network |
| :- | :- | :- | :- | :- |
| `bare` | **None.** | No | No | No |
| `normal` | Everything. | Yes | Yes | Yes |
| `restricted` | Read-only ambient state. | No | No | No |

**MUST** — `bare` MUST skip: hooks, skills, custom commands, subagents, plugins, MCP servers, auto memory, and instruction files. **MUST** — `bare` MUST NOT read a credential store, MUST NOT start background work, and MUST NOT emit system reminders.

**MUST** — `restricted` MUST remove write-capable tools from the schema and MUST disable execution and network access.

**MUST** — `bare` MUST be the recommended profile for scripted and SDK use, because "the same result on every machine" requires that no ambient state be read. The trade-off is explicit: `bare` skips the trust dialog, so it MUST also skip *loading* the content the trust dialog would have gated.

### 16.7 The headless lifecycle

**OBSERVED-COMPATIBLE.**

**MUST** — on SIGTERM, the in-progress turn MUST be left unfinished, no result MUST be recorded, the exit code MUST be `143`, and session-end hooks MUST still run.

**MUST** — a background run's wait ceiling MUST be **10 minutes**, configurable via `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`.

**MUST** — when the working directory has been deleted, the harness MUST warn and continue (or fail with a clear message) rather than crashing.

**MUST** — an MCP server with an invalid configuration MUST be skipped with a typed error, and the run MUST continue.

### 16.8 The command dispatcher

**MUST** — the dispatcher MUST have exactly three outcomes (§9.8), and the local-handler outcome MUST be observable in the terminal envelope via `local_command`.

**MUST** — the fuzzy command menu MUST ignore `:`, `_`, and `-` as separators, MUST match from the start of a name or from a word within it, and MUST resolve aliases to the canonical name.

### 16.9 Subcommands

**OBSERVED-COMPATIBLE.** The operator surfaces:

| Subcommand | Purpose |
| :- | :- |
| `mcp` | Manage MCP servers. |
| `plugin` | Manage plugins. |
| `agents` | List the agent roster (with `--json`). |
| `doctor` | Diagnose the installation and the disabled features. |
| `config` | Manage configuration. |
| `setup-token` | Configure a token. |
| `auth` | Manage authentication. |
| `resume` / `continue` / `fork` / `list` | Session management. |
| `update` | Update the product. |
| `model` | Show the model defaults and the resolution. |
| `serve` | Run as a self-hosted server. |

**MUST** — every subcommand that has a machine-readable form MUST offer it, and the machine-readable form MUST emit a single JSON object on stdout.

### 16.10 Error cases

| Situation | Behaviour |
| :- | :- |
| An unknown flag | Exit `1`, diagnostic on stderr. |
| An invalid flag combination | Exit `1`, diagnostic on stderr, before any model call. |
| The prompt is empty in headless mode and stdin is empty | Exit `1`. |
| stdin is not valid `stream-json` | Exit `1`, with the offending line number. |
| The session id is invalid | Exit `1`, `invalid_session_id`. |
| The turn cap is reached | Exit `1`, with an `error_max_turns` envelope. |
| The budget cap is reached | Exit `1`, with an `error_max_budget_usd` envelope. |
| SIGTERM | Exit `143`, no envelope. |

---

### 16.11 Worked example

```bash
# A headless run that emits a JSON envelope and gates on the result.
harness -p "Fix the failing test in <rel-path>" \
         --output-format json \
         --max-turns 12 \
         --max-budget-usd 2.00 \
         --allowedTools "read_file,edit_file" \
         --disallowedTools "run_shell" \
         --model "<model-id>" \
         > result.json
```

```bash
# A streamed run, for a consumer that wants progress.
harness -p "Fix the failing test in <rel-path>" \
         --output-format stream-json \
         --include-hook-events \
         --include-partial-messages \
         | while read -r line; do
             printf '%s\n' "$line" >> events.jsonl
           done
```

```bash
# A bare run: no ambient state is read, so the result is reproducible.
harness -p "Summarise this repository" --bare --output-format json
```


## 17. Interface 15 — Headless structured output envelope

**Status: OBSERVED-COMPATIBLE (the field set) with two deliberate extensions (`structured_output`, `errors[]`).**

### 17.1 Shape

The `json` output mode emits exactly one object: the terminal envelope. The `stream-json` output mode emits the event stream, whose last event is the same envelope.

### 17.2 Field table

| Field | Type | Required | Meaning | Constraints |
| :- | :- | :- | :- | :- |
| `type` | `string` | Yes | `result`. | — |
| `subtype` | `enum` | Yes | The outcome. | `success` · `error_max_turns` · `error_max_budget_usd` · `error_during_execution` · `error_max_structured_output_retries`. |
| `is_error` | `boolean` | Yes | Whether the run failed. | — |
| `result` | `string` | **On `success` only** | The final assistant text. | **MUST** be omitted on every other subtype. |
| `session_id` | `string` | Yes | The session. | — |
| `uuid` | `string` | Yes | The event id. | — |
| `num_turns` | `number` | Yes | The turns used. | — |
| `duration_ms` | `number` | Yes | The wall-clock duration. | — |
| `duration_api_ms` | `number` | Yes | The time spent on the provider. | — |
| `ttft_ms` | `number` | Yes | Time to first token. | — |
| `ttft_stream_ms` | `number` | Yes | Time to the first streamed token. | — |
| `time_to_request_ms` | `number` | Yes | Time from the start to the request. | — |
| `first_content_frame_ms` | `number` | Yes | Time to the first content frame. | — |
| `stop_reason` | `string` | Yes | Why the provider stopped. | `end_turn` · `max_tokens` · `refusal` · `null`. |
| `terminal_reason` | `string` | Yes | Why the run ended. | — |
| `api_error_status` | `number` | No | The provider's HTTP status, on a failure. | `null` otherwise. |
| `total_cost_usd` | `number` | Yes | The accumulated cost. | `0` when the cost basis is unknown. |
| `usage` | `object` | Yes | The main-loop token accounting. | See §17.3. |
| `modelUsage` | `object` | Yes | The whole-tree accounting, keyed by model. | See §17.3. |
| `permission_denials` | `object[]` | Yes | Every denial in the run. | `{tool_name, tool_use_id, tool_input}`. |
| `safety_stops` | `number` | Yes | How many times a Tier-2 check stopped the run. | — |
| `queued_turn_count` | `number` | Yes | Messages still queued at the end. | — |
| `result_index` | `number` | Yes | The index of this result within the session. | — |
| `subagent_stats` | `object` | Yes | The whole-tree subagent ledger. | §10.6. |
| `fast_mode_state` | `string` | Yes | The fast-mode state. | — |
| `fast_mode_disabled_reason` | `string` | No | Why fast mode is unavailable. | — |
| `per_turn_effort_active` | `boolean` | Yes | Whether per-turn effort was in effect. | — |
| `structured_output` | `object` | No | The validated structured output. | Present when `--json-schema` was supplied. |
| `errors` | `object[]` | No | The structured error list. | Present on a failure subtype. |
| `local_command` | `string` | No | The local command handler that ran, if any. | §9.8. |

### 17.3 The usage structures

```jsonc
"usage": {
  "input_tokens": 0,
  "output_tokens": 0,
  "cache_creation_input_tokens": 0,
  "cache_read_input_tokens": 0,
  "output_tokens_details": { "thinking_tokens": 0 },
  "server_tool_use": { "web_search_requests": 0, "web_fetch_requests": 0 },
  "cache_creation": { "ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 0 }
}
```

```jsonc
"modelUsage": {
  "<model-id>": {
    "inputTokens": 0, "outputTokens": 0,
    "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
    "webSearchRequests": 0,
    "costUSD": 0.0,
    "contextWindow": 200000, "maxOutputTokens": 32000,
    "thinkingTokens": 0,
    "canonicalModel": "<model-id>", "provider": "<provider>",
    "costBasis": "standard"
  }
}
```

**MUST** — `usage` MUST account for the main loop only, and `modelUsage` MUST account for the whole tree. **MUST** — a consumer that needs total spend MUST read `modelUsage`, because a consumer that reads `usage` will under-report whenever a subagent ran.

**MUST** — `costBasis` MUST be `unknown` when the adapter has no price table, and `costUSD` MUST then be `0`.

### 17.4 The subtype enum — normative

| Subtype | `is_error` | `result` present? | Exit code |
| :- | :- | :- | :- |
| `success` | `false` | Yes | `0` |
| `error_max_turns` | `true` | No | `1` |
| `error_max_budget_usd` | `true` | No | `1` |
| `error_during_execution` | `true` | No | `1` |
| `error_max_structured_output_retries` | `true` | No | `1` |

**MUST** — the `subtype` enum is the **authoritative** failure discriminator. **MUST** — `result` MUST be absent on every non-`success` subtype.

### 17.5 Semantics — normative

**MUST** — the envelope MUST be emitted exactly once per terminal outcome, whether the run succeeded, hit a limit, or failed.

**MUST** — the envelope MUST be the **last** event of a `stream-json` run, but it MUST NOT terminate the stream. A consumer MUST drain.

**MUST** — the envelope MUST carry enough information to bill and to resume: `session_id`, `num_turns`, `total_cost_usd`, `usage`, and `modelUsage` MUST be present on **every** subtype, including failures.

**MUST** — `result` MUST be present **only** on the `success` subtype. A consumer MUST NOT rely on its presence to detect success.


### 17.6 Error cases

| Situation | Behaviour |
| :- | :- |
| The run succeeded | `subtype: "success"`, `is_error: false`, `result` present. Exit `0`. |
| Every tool call was denied | `subtype: "success"`, `is_error: false`, `result` present, `permission_denials` non-empty. Exit `0`. A CI gate MUST inspect `permission_denials`, not the exit code. |
| The turn cap was reached | `subtype: "error_max_turns"`, `is_error: true`, `result` absent. Exit `1`. |
| The spend cap was reached | `subtype: "error_max_budget_usd"`, `is_error: true`, `result` absent, `errors[]` populated. Exit `1`. |
| The provider failed | `subtype: "error_during_execution"`, `is_error: true`, `api_error_status` set when the failure carried one. Exit `1`. |
| The structured-output retries were exhausted | `subtype: "error_max_structured_output_retries"`, `is_error: true`. Exit `1`. |
| The process was terminated by SIGTERM | **No envelope.** Exit `143`. The turn is left unfinished. |
| The model id is unrecognised | The run proceeds. `modelUsage` carries the id as given, and the context window is the assumed default. |
| The provider has no price table | `total_cost_usd` is `0` and every `costBasis` is `"unknown"`. Token counts remain authoritative. |
| A subagent ran | `usage` reflects the main loop only; `modelUsage` reflects the whole tree. |
| `json` mode was requested but the run produced no envelope | The consumer MUST treat the output as invalid. |


## 18. Compatibility matrix

### 17.7 Worked example

```jsonc
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "result": "All three tests pass.",
  "session_id": "<uuid>",
  "uuid": "<uuid>",
  "num_turns": 5,
  "stop_reason": "end_turn",
  "terminal_reason": "completed",
  "duration_ms": 5902,
  "duration_api_ms": 5902,
  "ttft_ms": 412,
  "ttft_stream_ms": 380,
  "time_to_request_ms": 44,
  "first_content_frame_ms": 512,
  "api_error_status": null,
  "total_cost_usd": 0.0193,
  "usage": {
    "input_tokens": 18422, "output_tokens": 1204,
    "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
    "output_tokens_details": { "thinking_tokens": 0 },
    "server_tool_use": { "web_search_requests": 0, "web_fetch_requests": 0 },
    "cache_creation": { "ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 0 }
  },
  "modelUsage": {
    "<model-id>": {
      "inputTokens": 18422, "outputTokens": 1204,
      "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
      "webSearchRequests": 0, "costUSD": 0.0193,
      "contextWindow": 200000, "maxOutputTokens": 32000,
      "thinkingTokens": 0, "canonicalModel": "<model-id>",
      "provider": "<provider>", "costBasis": "standard"
    }
  },
  "permission_denials": [],
  "safety_stops": 0,
  "queued_turn_count": 0,
  "result_index": 0,
  "subagent_stats": {
    "spawned": 0, "requested": { "background": 0, "foreground": 0, "unset": 0 },
    "started_in_background": 0, "max_depth": 0, "spawned_by_subagents": 0,
    "completed": 0, "failed": 0,
    "killed": { "parent": 0, "user": 0, "system": 0 },
    "refused": { "depth_limit": 0, "concurrency_limit": 0, "budget": 0 },
    "by_type": {}
  },
  "fast_mode_state": "off",
  "fast_mode_disabled_reason": "sdk_opt_in_required",
  "per_turn_effort_active": false
}
```

A budget-exhausted run:

```jsonc
{
  "type": "result",
  "subtype": "error_max_budget_usd",
  "is_error": true,
  "session_id": "<uuid>",
  "uuid": "<uuid>",
  "num_turns": 11,
  "stop_reason": null,
  "terminal_reason": "budget_exceeded",
  "api_error_status": null,
  "total_cost_usd": 5.02,
  "usage": { "input_tokens": 400000, "output_tokens": 21000 },
  "modelUsage": { "<model-id>": { "inputTokens": 400000, "outputTokens": 21000,
    "costUSD": 5.02, "contextWindow": 200000, "maxOutputTokens": 32000,
    "canonicalModel": "<model-id>", "provider": "<provider>", "costBasis": "standard" } },
  "permission_denials": [],
  "safety_stops": 0,
  "queued_turn_count": 1,
  "result_index": 0,
  "subagent_stats": { "spawned": 0, "requested": { "background": 0, "foreground": 0, "unset": 0 },
    "started_in_background": 0, "max_depth": 0, "spawned_by_subagents": 0, "completed": 0,
    "failed": 0, "killed": { "parent": 0, "user": 0, "system": 0 },
    "refused": { "depth_limit": 0, "concurrency_limit": 0, "budget": 0 }, "by_type": {} },
  "fast_mode_state": "off",
  "per_turn_effort_active": false,
  "errors": [ { "code": "max_budget_exceeded", "category": "resource_exhausted",
    "message": "The spend cap of 5.00 USD was reached.", "retryable": false } ]
}
```

Note that `result` is **absent** — a consumer that checks `result != null` will misread this run as a success.

---

### 18.1 Interface-level status

| # | Interface | Our status | Evidence reference | Notes |
| :- | :- | :- | :- | :- |
| 1 | Agent turn | **OBSERVED-COMPATIBLE** (event shape) / **ORIGINAL** (API shape) | `stream-json-basic.jsonl`; `PROTOCOL-NOTES.md` §§ on the result envelope; `agent-evidence.md` Area 1 | The event sequence, the turn definition, and the never-resend rule are compatibility-relevant. The programmatic `TurnRequest`/`TurnOutcome` types are ours. |
| 2 | Tool interface and tool-result envelope | **OBSERVED-COMPATIBLE** (envelope) / **ORIGINAL** (tool definitions) | `tool-result-dual-representation.json`; `tool-error-contract.json`; `denied-tool-results.json`; `stream-json-basic.jsonl`; `PROTOCOL-NOTES.md` | The dual representation, the `tool_use_id` correlation, and the size ladder are reproduced exactly. The tool set and its names are ours (with aliases accepted on ingest). |
| 3 | Permission decision interface | **OBSERVED-COMPATIBLE** | `stream-json-basic.jsonl` (`tool_result_meta[].permission_decision`); `denied-tool-results.json`; `settings-reference.md`; `agent-evidence.md` Areas 5, 8 | The decision vocabulary, the `permission_decision` record, the two deny mechanisms, and the two-tier model are reproduced. The query API is ours. |
| 4 | Rule and rule-set model | **OBSERVED-COMPATIBLE** | `settings-reference.md` §§ on `permissions.allow/ask/deny`; `agent-evidence.md` Area 8 | The syntax and the deny → ask → allow, first-match, scope-independent semantics are reproduced. The AST-based Windows matching is our improvement. |
| 5 | Hook interface | **OBSERVED-COMPATIBLE** | `hooks-guide.md` (the event table, the handler types, the exit-code protocol, the combination rule) | The event names, the stdin payload, the exit-code verdicts, and the most-restrictive-wins rule are reproduced. The injected-command policy is ours. |
| 6 | MCP client interface | **OBSERVED-COMPATIBLE** | `mcp.md` (the naming convention, the 128-char limit, the plugin namespace); `PROTOCOL-NOTES.md` MCP section; `cli-reference/agents-json.json` | The transports, the scopes, the naming, the consent metadata key, and the `readOnlyHint` concurrency key are reproduced. |
| 7 | Skill and slash-command registration | **OBSERVED-COMPATIBLE** (frontmatter, matrix, resolution) / **ORIGINAL** (template details, injection policy) | `skills.md` (the frontmatter table); `agent-evidence.md` Areas 9–10 | The frontmatter field names, the two-flag matrix, the loaded-vs-resolved split, and the two-tier loading are reproduced. The template language and the deny-by-default injection policy are ours. |
| 8 | Subagent spawn and join | **OBSERVED-COMPATIBLE** | `area1-agent-loop.md` (`system/task_started`); `sub-agents.md` (the frontmatter table); `PROTOCOL-NOTES.md` (the subagent task events, the roster); `env-vars.md` (the caps); `print-mode-json-result.json` (`subagent_stats`) | The spawn fields, the event set, the caps, the ledger, the file-backed job registry, and the roster output are reproduced. The exact spawn API shape is ours. |
| 9 | Session and state interface | **OBSERVED-COMPATIBLE** | `PROTOCOL-NOTES.md` (session persistence); `print-mode-json-result.json`; `checkpointing.md`; `memory.md`; `agent-evidence.md` Areas 7, 10 | The transcript layout, the entry types, the resume semantics, the compaction boundary, the memory limits, and the checkpoint scope are reproduced. |
| 10 | Model adapter interface | **ORIGINAL** (the boundary) with **OBSERVED-COMPATIBLE** vocabulary | `model-config.md` (the governance keys, the 200k default, `CLAUDE_CODE_MAX_CONTEXT_TOKENS`); `headless_raw.md` (the retry categories) | The adapter boundary, the role names, the effort levels, the five-level chain, the governance keys, and the 12-value error enum are reproduced. The interface shape is ours. |
| 11 | Config and settings interface | **OBSERVED-COMPATIBLE** | `settings-reference.md` (the scopes, the merge modes, the `"$defaults"` splice); `cli_reference.md` (`--settings`, `--setting-sources`) | The scope names, the file names, the merge semantics, and the monotone-lattice keys are reproduced. The registry-driven resolver is ours. |
| 12 | Context-compaction interface | **OBSERVED-COMPATIBLE** (the boundary record) / **ORIGINAL** (the trigger policy) | `area7-model-context-sessions.md` (F11, the compaction event); `model-config.md` (the window range) | The boundary record is reproduced field-for-field. The trigger thresholds, the ladder, and the thrash detector are ours. |
| 13 | Event-stream interface | **OBSERVED-COMPATIBLE** | `stream-json-basic.jsonl`; `cli-reference/stream-json-init-event.json`; `PROTOCOL-NOTES.md`; `area1-agent-loop.md` (the 49-event census) | The full taxonomy, the init manifest, and the assistant/user event shapes are reproduced. The open-set rule and the `structured_output` extension are ours. |
| 14 | CLI surface | **OBSERVED-COMPATIBLE** | `cli_reference.md` (the flags and subcommands); `headless_raw.md` (the bare profile, the SIGTERM behaviour, the wait ceiling) | The flag names, the output modes, the exit codes, and the headless lifecycle are reproduced. The combination-validation table and the profile table are ours. |
| 15 | Headless structured output envelope | **OBSERVED-COMPATIBLE** | `print-mode-json-result.json`; `cli-reference/print-mode-json-envelope.json` | The full field set is reproduced. The `structured_output` and `errors[]` extensions are ours. |

### 18.2 Counts

| Measure | Count | Interfaces |
| :- | :- | :- |
| Interfaces specified | **15** | — |
| Fully OBSERVED-COMPATIBLE | **8** | #4 (rule/rule-set model), #5 (hook interface), #6 (MCP client), #9 (session/state), #11 (config/settings), #13 (event stream), #14 (CLI surface), #15 (headless envelope) |
| Mixed (OBSERVED-COMPATIBLE core + ORIGINAL extensions) | **6** | #1 (agent turn), #2 (tool/result envelope), #3 (permission decision), #7 (skill/command), #8 (subagent), #12 (compaction) |
| Fully ORIGINAL | **1** | #10 (model adapter interface) — and its *vocabulary* (the effort levels, the governance keys, the 12-value error enum, the role names) is observed |

**OBSERVED-COMPATIBLE in whole or in part: 14 of 15. Fully ORIGINAL: 1 of 15** — and that one is the provider boundary, whose vocabulary is observed even though its interface shape is ours.

**Field-level:** of the 23 field-level compatibility surfaces enumerated in §18.3, **20 are OBSERVED-COMPATIBLE** and **3 are ORIGINAL** (our own tool names, the injected-command policy, and the two added envelope fields).

### 18.3 Field-level compatibility surfaces

| Surface | Status | Where it is pinned |
| :- | :- | :- |
| Event `type`/`subtype` vocabulary | OBSERVED-COMPATIBLE | §15.2 |
| Terminal envelope field names and the `subtype` enum | OBSERVED-COMPATIBLE | §17.2, §17.4 |
| `tool_use` / `tool_result` correlation via `tool_use_id` | OBSERVED-COMPATIBLE | §4.5 |
| The dual representation of a tool result | OBSERVED-COMPATIBLE | §4.4 |
| The `permission_decision` record and its three fields | OBSERVED-COMPATIBLE | §5.4 |
| The permission rule syntax | OBSERVED-COMPATIBLE | §6.2 |
| The settings key names and the scope names | OBSERVED-COMPATIBLE | §13.2, §13.6 |
| The JSONL transcript layout and the per-project directory slug | OBSERVED-COMPATIBLE | §11.2 |
| The exit codes | OBSERVED-COMPATIBLE | §16.2 |
| The `text` / `json` / `stream-json` output-mode names | OBSERVED-COMPATIBLE | §16.1 |
| The skill and agent frontmatter field names | OBSERVED-COMPATIBLE | §9.2, §10.7 |
| The MCP tool-naming convention | OBSERVED-COMPATIBLE | §8.4 |
| The hook event names and the stdin/stdout protocol | OBSERVED-COMPATIBLE | §7.1, §7.3, §7.4 |
| The compaction boundary's field names | OBSERVED-COMPATIBLE | §11.6 |
| The subagent ledger's field names | OBSERVED-COMPATIBLE | §10.6 |
| The agent-roster output's field names | OBSERVED-COMPATIBLE | §10.10 |
| The effort levels and the error-category enum | OBSERVED-COMPATIBLE | §12.6, §12.7 |
| The governance keys | OBSERVED-COMPATIBLE | §12.6 |
| The console-menu state | ORIGINAL | — |
| The prompt-assembly order | ORIGINAL | — |
| Our own tool names | ORIGINAL | — |
| The injected-command policy | ORIGINAL | — |
| The `structured_output` and `errors[]` envelope fields | ORIGINAL | — |

### 18.4 Deliberate divergences from the observed behaviour

Each divergence is a *deliberate* difference, not an accident. The reasoning and the alternatives considered are recorded in `architecture.md` §1.2 and at each point in this document.

| # | Divergence | Direction | Reason |
| :- | :- | :- | :- |
| 1 | The failure path returns an output file pointer, not just an excerpt. | Improvement | A failing build's output was otherwise unrecoverable except by re-running. |
| 2 | An invalid settings value in headless mode is ignored **and** reported on stderr. | Improvement | The observed behaviour fails open silently, so a typo in a permission rule silently leaves it unenforced. |
| 3 | A forked skill counts in the subagent ledger. | Improvement | A forked skill spends real tokens; excluding it understates spend. |
| 4 | An injected shell command in a skill body is gated by an explicit policy that defaults to deny for untrusted sources, and is always logged. | Improvement | Silent render-time execution is remote code execution by repository. |
| 5 | `submit_plan` and `ask_user` are always present. | Improvement | The observed behaviour omits them in some configurations, leaving the agent in a prose-only degraded state. |
| 6 | An `AGENTS.md` is merged with a `CLAUDE.md` rather than suppressed by it. | Improvement | The observed presence-based switch silently drops instructions the user believed were active. |
| 7 | Windows shell matching is AST-based. | Improvement | A string matcher is a real bypass on the platform we run on. |
| 8 | The protected-path table is a compiled artefact with a test that fails when a path is added. | Improvement | A list maintained only in documentation drifts out of sync with the code. |
| 9 | Diagnostics are prefixed `[harness:<event>]` and always carry a JSON payload. | Improvement | The observed diagnostics have no stable machine-readable form. |
| 10 | A budget cap on an unpriced model falls back to a token-denominated cap with a note. | Improvement | A purely monetary cap is unenforceable against a self-hosted model; silently ignoring it is worse. |
| 11 | The tool set uses our own names; the reference's names are accepted as aliases. | Neutral | Our names are part of our own product surface; rule migration must not break. |
| 12 | A session's `linesAdded`/`linesRemoved` are tracked in the ledger. | Neutral | It is a metric a user actually judges the session by; it is additive to the observed set. |
| 13 | A plugin's `bin/` directory is **not** prepended to the Bash tool's `PATH` in v1. | Omission | The observed behaviour adds `bin/` to the Bash tool's `PATH` while the plugin is enabled (`agent-evidence.md` F10.23, `OBSERVED-DOC`). We omit it deliberately, because a `PATH` prepend is a **code-execution surface with no review step**: any file placed in a plugin's `bin/` becomes resolvable by name for every Bash call in the session, so a plugin could shadow a real command (`git`, `python`, `npm`) and the agent would run the plugin's version without the operator ever seeing a path change. We reproduce the plugin's *content* surfaces (skills, commands, agents, hooks, MCP, LSP) and record this one as an omission. **The omission is visible to the user**, not silent: the plugin's manifest names a `bin/` directory that Keel ignores, and the plugin-load diagnostic says so. If it is later implemented, it must go through the same approval gate as every other extension surface (SC-9) and be recorded here as a reversal. |

---

## 19. Appendix — Evidence index

| Evidence artefact | What it pins |
| :- | :- |
| `agent-reference-shots/stream-json-basic.jsonl` | The assistant and user event shapes; the init manifest; the `tool_result_meta[].permission_decision` record; the `wire_tool_inputs` field; a non-JSON line in the stream (a parse error, skipped). |
| `agent-reference-shots/tool-result-dual-representation.json` | The success and failure/denial result pairs. |
| `agent-reference-shots/tool-error-contract.json` | The tool-error contract and the exit-code semantics. |
| `agent-reference-shots/denied-tool-results.json` | The denial result shape and the `permission_denials` entries. |
| `agent-reference-shots/print-mode-json-result.json` | The terminal envelope's full field set. |
| `agent-reference-shots/cli-reference/print-mode-json-envelope.json` | The envelope's field set, independently. |
| `agent-reference-shots/cli-reference/stream-json-init-event.json` | The init manifest's full field list: 27 tools, 53 slash commands, 5 agents, 20 skills, 3 plugins, 11 capabilities. |
| `agent-reference-shots/cli-reference/agents-json.json` | The agent-roster output. |
| `agent-reference-shots/PROTOCOL-NOTES.md` | The black-box wire observations: the init fields, the tool wire format, the read/glob/edit/write/bash result payloads, the permission denials, the subagent task events, the plan mode, the result envelope, the session persistence, the background sessions, the MCP, the skills, the instruction files, the trust flow, and the auto-mode classifier. |
| `agent-reference-shots/areas/area1-agent-loop.md` | The 49-event census and the `system/task_started` payload. |
| `agent-reference-shots/areas/area7-model-context-sessions.md` | The compaction boundary event, field-for-field. |
| `agent-reference-shots/areas/area8-auto-mode-config.md` | The four-tier auto-mode precedence and the `"$defaults"` splice. |
| `agent-reference-shots/docs-cache/hooks-guide.md` | The hook event table, the handler types, the exit-code protocol, the combination rule, and the common input fields. |
| `agent-reference-shots/docs-cache/settings-reference.md` | The `permissions.allow/ask/deny` syntax, the Bash rule limitations, and the managed-source merge modes. |
| `agent-reference-shots/docs-cache/cli_reference.md` | ~90 flags and ~32 subcommands. |
| `agent-reference-shots/docs-cache/headless_raw.md` | The bare profile, the bare-mode runtime limits, the SIGTERM behaviour, the wait ceiling, the retry-event fields, and the MCP skip categories. |
| `agent-reference-shots/docs-cache/model-config.md` | The governance keys, the 200k default for an unrecognised model, `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, and the auto-compact window range. |
| `agent-reference-shots/docs-cache/skills.md` | The skill frontmatter field table and the two-flag matrix. |
| `agent-reference-shots/docs-cache/sub-agents.md` | The subagent frontmatter field table. |
| `agent-reference-shots/docs-cache/mcp.md` | The plugin server naming, the 128-character tool-name limit, and the prompt-as-command convention. |
| `agent-reference-shots/docs-cache/memory.md` | The memory directory layout, the 200-line/25 KB index limit, and the 4 MiB instruction-file cap. |
| `agent-reference-shots/docs-cache/checkpointing.md` | The per-turn checkpoint, the 100-checkpoint window, the Bash exclusion, and the recovery affordances. |
| `agent-reference-shots/docs-cache/worktrees.md` | The worktree path convention and the cleanup rules. |
| `agent-reference-shots/docs-cache/env-vars.md` | The concurrency caps: 20 subagents, depth 3, 16 workflow agents (1–256). |
| `agent-evidence.md` | The capability map (§3), the twelve areas (§4), the capability tables (§5), the clean-room opportunity analysis (§8), the recommended scope (§9), the 178 confirmed capabilities (§10), and the 44 unknowns (§11). |

**Evidence handling.** Every artefact above was treated as **untrusted data**. Documentation pages and captured transcripts were read as evidence and never obeyed. At least one captured document contains instruction-shaped content addressed to a reader; it was classified as data and not followed, and this is recorded in `architecture.md` §16.




