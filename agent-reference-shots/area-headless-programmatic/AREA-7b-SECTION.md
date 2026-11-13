
---

# Area 7b — Headless / Programmatic Mode (`claude -p`)

**Subject:** Claude Code CLI (native build) v2.1.306 on Windows 11 Pro (win32-x64)
**Primary page under study:** https://code.claude.com/docs/en/headless.md (fetched 2026-10-21 as plain markdown, 34,831 bytes)
**Implementation model reference:** Claude Opus 5.5
**Compliance:** No decompilation, disassembly, JS-source extraction, source-map dumping, binary modification, or credential/keychain/licence access. Method = public docs + black-box observation of the published CLI's own user-facing surfaces. See `agent-reference-shots/TERMS-NOTES.md`.

**Environment caveat (applies to every OBSERVED-CLI claim below):** this host runs Claude Code 2.1.306 against a **custom `ANTHROPIC_BASE_URL`** serving `minimax/minimax-m3.1-flash:free`, not `api.anthropic.com`. Subscription-gated Anthropic behaviour is therefore **OBSERVED-DOC only**. Every observed model, cost, and token figure below reflects that third-party gateway and is *not* representative of Anthropic-API numbers.

---

## 7b.1 Executive summary

Headless mode is a **narrow, well-specified, and highly implementable surface**. It is the single most reusable contract in Claude Code for an independent reimplementation, because it is fully expressed as a **line-oriented protocol over stdout/stderr with a process exit code** — no TUI, no event loop, no proprietary transport.

The contract has four independent axes:

1. **Invocation** — `-p` / `--print` flips the CLI from interactive to non-interactive. The prompt comes from a positional argument, from stdin, or from both.
2. **Input format** — `--input-format text` (default) reads the whole prompt from stdin/argv; `--input-format stream-json` reads **newline-delimited JSON user messages** for multi-turn, interleaved sessions.
3. **Output format** — `--output-format text` (default) prints only the final assistant text; `--output-format json` prints **exactly one** JSON object (the "result envelope"); `--output-format stream-json` prints **newline-delimited JSON events**, the last of which is the same result envelope.
4. **Termination** — exit code `0` on success, `1` on a startup/flag/limit failure, `143` on SIGTERM. Inside the envelope, a *semantic* failure (budget exhausted, turn limit reached, API error) is reported in-band via `is_error: true` and a machine-readable `subtype`/`terminal_reason`, **not** via the process exit code alone.

The result envelope is the highest-value artefact for a reimplementer. Its stable, documented, and observed fields are:

`type: "result"` · `subtype` (`"success"` | `"error_max_turns"` | `"error_max_budget_usd"` | `"error_during_execution"` | `"error_max_structured_output_retries"`) · `is_error` · `result` (the text) · `session_id` · `uuid` · `num_turns` · `stop_reason` · `terminal_reason` · `duration_ms` / `duration_api_ms` · `ttft_ms` / `ttft_stream_ms` · `usage` · `modelUsage` · `total_cost_usd` · `permission_denials[]` · `permission_denials[].tool_name|tool_use_id|tool_input` · `structured_output` (with `--json-schema`) · `errors[]` (on the error arm) · `result_index` · `queued_turn_count` · `fast_mode_state` / `fast_mode_disabled_reason`.

Two operational rules are easy to get wrong and worth calling out explicitly:

- **stdout carries the protocol; stderr carries diagnostics.** The "Waiting for background work to finish" notice and the MCP "server skipped" warning are deliberately suppressed when stdout is a JSON stream, so a script's JSON never carries them. Machine-readable equivalents live in the envelope (`mcp_server_errors`) or in `system/init`.
- **Flag combinations are validated at startup and rejected with exit code 1 before any model call.** Observed: `--input-format=stream-json` without `--output-format=stream-json`; `--output-format=stream-json` without `--verbose`; `--include-partial-messages` and `--forward-subagent-text` outside `--print` + `stream-json`. The `--json-schema` validator error is also a startup failure with exit 1.

---

## 7b.2 Classification key

- **OBSERVED-DOC** — stated in the cited public Anthropic doc; exact sentences quoted.
- **OBSERVED-CLI** — I ran the published CLI on this host; exact command and output recorded.
- **INFERRED** — my conclusion, with the reasoning stated.
- **UNKNOWN** — the available evidence cannot establish it.

---

## 7b.3 Findings

### H1 — `-p` / `--print` is the single switch from interactive to non-interactive

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/headless.md — § "Basic usage"

> "Add the `-p` (or `--print`) flag to any `claude` command to run it non-interactively. Not every [CLI option](/docs/en/cli-reference) combines with `-p`. Claude Code rejects `--bg`, and rejects `--cloud` with a task description, with an error naming the conflict; `--cloud` with a session ID and `-p` instead [queues a message into that cloud session](...) and exits."

> "Claude Code exits with code 0 on success and a non-zero code when the run fails, so your scripts can branch on the exit status. If you pass an invalid flag, Claude Code reports the error to stderr before the run starts. When a failure happens inside the run, such as missing authentication, Claude Code prints the failure as the result on stdout."

**CLI help (OBSERVED-CLI, `claude --help` v2.1.306):**
> `-p, --print  Print response and exit (useful for pipes). Note: The workspace trust dialog is skipped when Claude is run in non-interactive mode (via -p, or when stdout is not a TTY, e.g. piped or redirected output). Only use this in directories you trust. Settings files that fail validation are silently ignored in this mode (no error dialog is shown).`

**Reimplementation note:** the three-way split of *where* output goes is the contract to copy:
- *invalid flag / bad schema* → **stderr**, **exit 1**, before the run starts;
- *failure inside the run* → **stdout**, as the result (so `-p` callers always have something parseable on stdout);
- *success* → **stdout**, exit 0.

**UNKNOWN:** whether `-p` with no prompt and no stdin is a "flag error" or a "runtime error". The doc does not say; the CLI's behaviour (observed below) is exit 1 with a stderr message, which matches the "invalid flag" treatment.

---

### H2 — `--output-format` has exactly three values, and the flag is print-mode-only

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Get structured output"

> "Use `--output-format` to control how responses are returned:
> * `text` (default): plain text output
> * `json`: structured JSON with result, session ID, and metadata
> * `stream-json`: newline-delimited JSON for real-time streaming"

**Source:** https://code.claude.com/docs/en/cli-reference.md — CLI flags table

> `| --output-format | Specify output format for print mode (options: text, json, stream-json) | claude -p "query" --output-format json |`

**OBSERVED-CLI** (`claude --help`): `--output-format <format>  Output format (only works with --print): "text" (default), "json" (single result), or "stream-json" (realtime streaming) (choices: "text", "json", "stream-json")`

---

### H3 — The `json` output is a single JSON object: the result envelope

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Get structured output"

> "This example returns a project summary as JSON with session metadata, with the text result in the `result` field"
> "To get output conforming to a specific schema, use `--output-format json` with `--json-schema` and a [JSON Schema](https://json-schema.org/) definition. The response includes metadata about the request (session ID, usage, etc.) with the structured output in the `structured_output` field."

> "If a run ends without valid structured output, for example because Claude declined the request, the response has no `structured_output` field. Before your script uses `structured_output`, check that the field is present."

**OBSERVED-CLI** — `claude -p "Reply with exactly: PONG" --output-format json --max-turns 1`, exit code 0, stdout (single line, keys shown in observed order):

```json
{"duration_api_ms":1776,"stop_reason":"end_turn","session_id":"0b72056b-f431-4ce1-9255-76f0378bcd47","total_cost_usd":0.057247799999999995,"usage":{"input_tokens":14287,"cache_creation_input_tokens":0,"cache_read_input_tokens":199,"output_tokens":3,"output_tokens_details":{"thinking_tokens":0},"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":0,"ephemeral_5m_input_tokens":0},"inference_geo":"","iterations":[],"speed":"standard","fallback_credit":null},"modelUsage":{"minimax/minimax-m3.1-flash:free":{"inputTokens":14287,"outputTokens":3,"cacheReadInputTokens":199,"cacheCreationInputTokens":0,"webSearchRequests":0,"costUSD":0.057247799999999995,"contextWindow":200000,"maxOutputTokens":32000,"thinkingTokens":0,"canonicalModel":"minimax/minimax-m3.1-flash:free","provider":"firstParty","costBasis":"unknown"}},"permission_denials":[],"terminal_reason":"completed","fast_mode_state":"off","fast_mode_disabled_reason":"sdk_opt_in_required","subagent_stats":{"spawned":0,"requested":{"background":0,"foreground":0,"unset":0},"started_in_background":0,"max_depth":0,"spawned_by_subagents":0,"completed":0,"failed":0,"killed":{"parent":0,"user":0,"system":0},"refused":{"depth_limit":0,"concurrency_limit":0,"budget":0},"by_type":{}},"safety_stops":0,"is_error":false,"num_turns":1,"subtype":"success","api_error_status":null,"result":"PONG","ttft_ms":2010,"type":"result","duration_ms":2064,"uuid":"53be7524-aa26-4dc8-a71c-75962d59fe16","ttft_stream_ms":2005,"time_to_request_ms":281,"first_content_frame_ms":2006,"queued_turn_count":0,"result_index":0}
```

**Observed top-level key set (OBSERVED-CLI, sorted):**
`api_error_status, duration_api_ms, duration_ms, fast_mode_disabled_reason, fast_mode_state, first_content_frame_ms, is_error, modelUsage, num_turns, permission_denials, queued_turn_count, result, result_index, safety_stops, session_id, stop_reason, subagent_stats, subtype, terminal_reason, time_to_request_ms, total_cost_usd, ttft_ms, ttft_stream_ms, type, usage, uuid`

Observed `usage` sub-keys: `cache_creation, cache_creation_input_tokens, cache_read_input_tokens, fallback_credit, inference_geo, input_tokens, iterations, output_tokens, output_tokens_details, server_tool_use, service_tier, speed`

Observed `modelUsage[<model>]` sub-keys: `cacheCreationInputTokens, cacheReadInputTokens, canonicalModel, contextWindow, costBasis, costUSD, inputTokens, maxOutputTokens, outputTokens, provider, thinkingTokens, webSearchRequests`

**Note the deliberate naming asymmetry:** `usage` uses snake_case (`input_tokens`, `cache_read_input_tokens`) while `modelUsage` entries use camelCase (`inputTokens`, `cacheReadInputTokens`). Both are reproduced exactly as observed.

**Typed contract (OBSERVED-DOC)** — https://code.claude.com/docs/en/agent-sdk/typescript.md, § `SDKResultMessage`:

> ```typescript
> type SDKResultMessage =
>   | {
>       type: "result";
>       subtype: "success";
>       uuid: UUID;
>       session_id: string;
>       duration_ms: number;
>       duration_api_ms: number;
>       is_error: boolean;
>       api_error_status?: number | null;
>       num_turns: number;
>       result: string;
>       stop_reason: string | null;
>       ...
>       total_cost_usd: number;
>       usage: NonNullableUsage;
>       modelUsage: { [modelName: string]: ModelUsage };
>       permission_denials: SDKPermissionDenial[];
>       ...
>       structured_output?: unknown;
>       deferred_tool_use?: { id: string; name: string; input: Record<string, unknown> };
>       terminal_reason?: TerminalReason;
>       result_index?: number;
>       fast_mode_state?: FastModeState;
>       fast_mode_disabled_reason?: FastModeDisabledReason;
>     }
>   | {
>       type: "result";
>       subtype:
>         | "error_max_turns"
>         | "error_during_execution"
>         | "error_max_budget_usd"
>         | "error_max_structured_output_retries";
>       ...
>       errors: string[];
>       ...
>     };
> ```

> `type SDKPermissionDenial = { tool_name: string; tool_use_id: string; tool_input: Record<string, unknown>; };`

> `type ModelUsage = { inputTokens: number; outputTokens: number; thinkingTokens?: number; cacheReadInputTokens: number; cacheCreationInputTokens: number; webSearchRequests: number; costUSD: number; contextWindow: number; maxOutputTokens: number; canonicalModel?: string; provider?: string; costBasis?: 'list' | 'managed' | 'unknown'; };`

> `terminal_reason`: why the loop ended. One of `"completed"`, `"max_turns"`, `"tool_deferred"`, `"aborted_streaming"`, `"aborted_tools"`, `"hook_stopped"`, `"stop_hook_prevented"`, `"background_requested"`, `"blocking_limit"`, `"rapid_refill_breaker"`, `"prompt_too_long"`, `"image_error"`, `"model_error"`, `"api_error"`, `"malformed_tool_use_exhausted"`, `"budget_exhausted"`, `"structured_output_retry_exhausted"`, `"tool_deferred_unavailable"`, or `"turn_setup_failed"`.

**Reimplementation note:** the field *set* is stable and the field *names* are snake_case, but note the deliberate asymmetry: `usage` uses snake_case API-ish names (`input_tokens`, `cache_read_input_tokens`) while `modelUsage` entries use camelCase (`inputTokens`, `cacheReadInputTokens`). A reimplementer should reproduce both conventions exactly — consumers written against this contract key off them.

---

### H4 — `stream-json` is newline-delimited JSON; the last line is the result envelope

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Stream responses"

> "Use `--output-format stream-json` with `--verbose` and `--include-partial-messages` to receive tokens as they're generated. Each line is a JSON object representing an event"
> "The last line of the stream is a `result` message with the final response text, cost, and session metadata."
> "If your consumer reads the stream slowly, Claude Code waits for the queued output to drain before exiting, scaling the wait with how much is still queued, capped at 30 seconds."

**OBSERVED-CLI** — `claude -p "Say the single word: HELLO" --output-format stream-json --verbose --include-partial-messages` (exit 0). Observed line types in order:

| # | `type` | `subtype` | Notes |
|---|---|---|---|
| 0 | `system` | `init` | session metadata (see H5) |
| 1 | `system` | `status` | `{"status":"requesting","session_id":…,"uuid":…}` |
| 2–4 | `stream_event` | — | raw provider stream events |
| 5 | `assistant` | — | full assistant message, `content: [{"type":"text","text":"HELLO","citations":[]}]` |
| 6–8 | `stream_event` | — | more raw stream events |
| 9 | `result` | `success` | the same envelope as `--output-format json` |

Observed `stream_event` shape:
```json
{"type":"stream_event","event":{"type":"message_start","message":{…}},"api_message_id":"…","parent_tool_use_id":null,"session_id":"…","thinking_display":"…","ttft_ms":…,"uuid":"…"}
```
and a text delta:
```json
{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"HELLO"}}, …}
```

**Reimplementation note:** `stream-json` is the natural transport for a UI. The three message classes an implementer must distinguish are `system` (control/metadata), `assistant`/`user` (conversation turns, optionally carrying `parent_tool_use_id` for subagent nesting), and `result` (terminal summary). `stream_event` is the raw provider frame passthrough — a reimplementation may substitute its own event shape here, since it is provider-coupled, but it should keep the `type`/`event` envelope shape so the documented `jq` filter keeps working:

> ```bash
> claude -p "Write a poem" --output-format stream-json --verbose --include-partial-messages | \
>   jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'
> ```

---

### H5 — `system/init` is the first event and carries the whole session manifest

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Read session metadata"

> "The `system/init` event reports session metadata including the model, tools, MCP servers, and loaded plugins. It is the first event in the stream unless startup events precede it:
> * `plugin_install` events, when [`CLAUDE_CODE_SYNC_PLUGIN_INSTALL`] is set.
> * `hook_started`, `hook_progress`, and `hook_response` events, while a configured [`SessionStart`] or [`Setup`] hook runs. These stream as the hook produces them."

> "The event also carries an optional `capabilities` array of strings naming the protocol behaviors this Claude Code version implements, such as `interrupt_receipt_v1` or `interrupt_cancel_queued_v1`. Check it to feature-detect instead of comparing version strings, and ignore values you don't recognize."

**OBSERVED-CLI** — observed `system/init` fields (abridged to the headless-relevant subset):
```json
{"type":"system","subtype":"init","cwd":"…","session_id":"…","tools":["Task","Bash",…,"Write"],
 "mcp_servers":[{"name":"rea","status":"pending","source":"user"}],
 "model":"minimax/minimax-m3.1-flash:free","permissionMode":"default",
 "slash_commands":[…], "terminal_slash_commands":["doctor","color","focus","reload-plugins"],
 "apiKeySource":"none","claude_code_version":"2.1.306","output_style":"default",
 "agents":["claude","Explore","general-purpose","Plan","statusline-setup"],
 "skills":[…], "plugins":[{"name":"…","path":"builtin","source":"…"}],
 "capabilities":["interrupt_receipt_v1","interrupt_cancel_queued_v1","interrupt_send_now_v1","msg_lifecycle_v1","request_marker_lists_v1","sdk_mcp_tools_list_changed","sdk_mcp_manifests","mcp_read_resource_v1","mcp_tool_ui_meta_v1","ui_surface_v1","mcp_call_result_not_for_model_v1"],
 "analytics_disabled":false,"product_feedback_disabled":false,"uuid":"…"}
```

**Reimplementation note:** `capabilities` is a **feature-detection array, not a version string**. A reimplementer that wants Claude-Code-compatible consumers to work should emit a capabilities array and let consumers branch on it. This is a genuinely good design to copy.

**Discrepancy worth recording (INFERRED):** the observed `permissionMode` was the string `"default"`, while the `--permission-mode` flag's documented choices are `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan`, and the headless doc says "With Claude Code v2.1.302 or later, `claude -p` runs start in Manual mode when nothing sets a permission mode". The most likely reading is that `"default"` is the wire-level name for the unset/manual baseline, and `manual` is the user-facing spelling of the same policy. Reasoning: the observed run had *no* `--permission-mode` and no allow rules, and a `Write` call under `--permission-mode dontAsk` was denied — i.e. the default behaviour is "deny what would prompt". This is a naming inconsistency a reimplementer must pick a side on.

---

### H6 — `--input-format stream-json` accepts newline-delimited user messages

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/cli-reference.md — CLI flags table

> `| --input-format | Specify input format for print mode (options: text, stream-json) | claude -p --output-format json --input-format stream-json |`

**Source:** https://code.claude.com/docs/en/agent-sdk/typescript.md — § `SDKUserMessage`

> ```typescript
> type SDKUserMessage = {
>   type: "user";
>   uuid?: UUID;
>   session_id?: string;
>   agent_id?: string;
>   message: MessageParam; // From Anthropic SDK
>   pasted_content?: MessageParam["content"][];
>   parent_tool_use_id: string | null;
>   isSynthetic?: boolean;
>   shouldQuery?: boolean;
>   client_composed?: true;
>   tool_use_result?: unknown;
>   priority?: "now" | "next" | "later";
>   origin?: SDKMessageOrigin;
>   inline_pastes?: string[];
> };
> ```
> "`priority`: set it to `"now"` to have Claude Code deliver the message text as written. … `shouldQuery`: set it to `false` to append the message to the transcript without triggering an assistant turn. The message is held and merged into the next user message that does trigger a turn. Use this to inject context, such as the output of a command you ran out of band, without spending a model call on it."

**OBSERVED-CLI** — piped one line of JSON into `claude -p --input-format stream-json --output-format stream-json --verbose`; exit 0; observed output stream began `system init`, then `assistant`, then `result success`:
```
$ printf '{"type":"user","message":{"role":"user","content":"Reply with exactly: STREAMIN"}}\n' | claude -p --input-format stream-json --output-format stream-json --verbose
```
The assistant message's content was `[{"type":"text","text":"STREAMIN", …}]`.

**OBSERVED-CLI — `--replay-user-messages`:** with the same stdin plus `--replay-user-messages`, the observed stream contained a `user` message echoing the input back, with keys `['isReplay','message','parent_tool_use_id','session_id','timestamp','type','uuid']`, `isReplay: true`, `message: {"role":"user","content":"Say ONCE"}`. This is the acknowledgement channel a multi-turn host needs.

**Reimplementation note:** the input protocol is the Messages API's own user-message shape wrapped in a small envelope (`type`, `message`, optional `uuid`, `parent_tool_use_id`, `priority`, `shouldQuery`, `origin`). An independent implementation can adopt this shape directly because it is an interchange format, not Anthropic code.

---

### H7 — Flag-combination validation is strict, happens before any model call, and exits 1

**Status:** OBSERVED-CLI
**Evidence (all on this host, v2.1.306):**

| Invocation | stderr | exit |
|---|---|---|
| `claude -p "hi" --nonexistent-flag` | `error: unknown option '--nonexistent-flag'` | 1 |
| `claude -p "hi" --json-schema '{"type":"not-a-type"}' --output-format json` | `Error: --json-schema is not a valid JSON Schema: data/type must be equal to one of the allowed values, data/type must be array, data/type must match a schema in anyOf` | 1 |
| `claude -p "x" --input-format stream-json --output-format text` (stdin piped) | `Error: --input-format=stream-json requires output-format=stream-json.` | 1 |
| `claude -p "x" --output-format stream-json` (no `--verbose`) | `Error: When using --print, --output-format=stream-json requires --verbose` | 1 |
| `claude -p "x" --output-format json --include-partial-messages` | `Error: --include-partial-messages requires --print and --output-format=stream-json.` | 1 |
| `claude -p "x" --output-format json --forward-subagent-text` | `Error: --forward-subagent-text requires --print and --output-format=stream-json.` | 1 |
| `claude -p < /dev/null` | `Error: Input must be provided either through stdin or as a prompt argument when using --print` | 1 |
| `claude -p "   "` | `Warning: no stdin data received in 3s, proceeding without it. …` then `Error: Input contained only whitespace. Provide a prompt with text through stdin or as a prompt argument when using --print` | 1 |
| `claude -p "x" --output-format json --include-hook-events` | *(accepted — no error)* | 0 |

**DOC corroboration** — https://code.claude.com/docs/en/errors.md, § "Invalid `--json-schema`":
> "The schema you passed to [`--json-schema`] in [non-interactive mode](/docs/en/headless#get-structured-output) failed JSON Schema compilation, so `claude` exits with code 1 instead of running the prompt. Before v2.1.205, an invalid schema produced unstructured output with no error, and any schema that used the `format` keyword was treated as invalid."

**DOC corroboration** — https://code.claude.com/docs/en/headless.md, § "Get structured output":
> "If the value isn't a valid JSON Schema, `claude` exits with `Error: --json-schema is not a valid JSON Schema` followed by the validator's diagnostic. Claude Code accepts schemas that use the `format` keyword, such as `"format": "email"`, but treats `format` as an annotation and doesn't enforce it."

**Reimplementation note:** the validation is a **declarative flag-compatibility matrix** checked before any work begins. The error strings are stable and greppable; a compatible implementation should use the same wording and the same exit code. Note the deliberate ordering: `--include-partial-messages` and `--forward-subagent-text` are *hard errors* outside `stream-json`, but `--include-hook-events` outside `stream-json` is *silently accepted* (observed exit 0) — an inconsistency worth noting, and possibly worth matching exactly for consumer compatibility.

---

### H8 — `--json-schema` yields `structured_output`; the field is **optional** and may be absent

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Get structured output"

> "To get output conforming to a specific schema, use `--output-format json` with `--json-schema` and a [JSON Schema](https://json-schema.org/) definition. The response includes metadata about the request (session ID, usage, etc.) with the structured output in the `structured_output` field."
> "If a run ends without valid structured output, for example because Claude declined the request, the response has no `structured_output` field. Before your script uses `structured_output`, check that the field is present."

**OBSERVED-CLI** — `claude -p "Reply with a JSON object with key functions whose value is the array [\"alpha\",\"beta\"]" --output-format json --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}},"required":["functions"]}'`, exit 0:
- top-level keys included `structured_output`
- `structured_output` = `{"functions": ["alpha","beta"]}`
- `result` = `'{"functions":["alpha","beta"]}'` (the same content as text)

**Reimplementation note:** `structured_output` is a **sibling of** `result`, not a replacement — `result` still carries the text. Consumers must null-check `structured_output`. The `format` keyword is accepted but not enforced, matching JSON Schema's own annotation semantics.

---

### H9 — Semantic failures are reported *in-band*; the exit code stays 0 for some of them

**Status:** OBSERVED-CLI + OBSERVED-DOC

**OBSERVED-CLI — turn limit.** `claude -p "Do something that requires tools" --max-turns 1 --output-format json --allowedTools "Bash"`:
```json
{"type":"result","subtype":"error_max_turns","is_error":true,"terminal_reason":"max_turns",
 "stop_reason":"tool_use","num_turns":2,"errors":["Reached maximum number of turns (1)"], …}
```
**Process exit code: 1.** The envelope was still written to stdout.

**OBSERVED-CLI — budget cap.** `claude -p "Write a long essay about the sea" --output-format json --max-budget-usd 0.0001`:
```json
{"type":"result","subtype":"error_max_budget_usd","is_error":true,"terminal_reason":"budget_exhausted",
 "stop_reason":null,"num_turns":1,"result":null,"duration_api_ms":0,
 "total_cost_usd":0.061847799999999994,"errors":["Reached maximum budget ($0.0001)"], …}
```
**Process exit code: 1.**

**OBSERVED-CLI — API error inside the run.** `claude -p … --continue --output-format json`:
```json
{"type":"result","subtype":"error_during_execution","is_error":true,"result":"API Error: 400 Invalid Anthropic Messages API request", …}
```
**Process exit code: 1.** (The earlier plain `--resume <id>` case exited 0 with `subtype:"success"`.)

**DOC corroboration** — https://code.claude.com/docs/en/headless.md, § "Basic usage":
> "Claude Code exits with code 0 on success and a non-zero code when the run fails, so your scripts can branch on the exit status. … When a failure happens inside the run, such as missing authentication, Claude Code prints the failure as the result on stdout."

**Reimplementation note (important and easy to get wrong):** a reimplementer must decide *one* rule and document it. Claude Code's observed rule is: **an `is_error: true` result ⇒ process exit != 0**. A script that only checks the exit code works; a script that only parses `is_error` also works. A script that checks only `subtype == "success"` works. What does *not* work is checking `result != null` — on the budget-exhausted arm, `result` was `null` while `errors` carried the reason.

Also note: on the error arm the field `result` is the **text of the failure** for some subtypes (`"API Error: 400 …"`) and `null` for others (`error_max_budget_usd`). The `errors[]` array is the reliable, uniform reason channel on the error arm.

---

### H10 — Permission denials are recorded in-band on the result envelope

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Turn off permission prompts in unattended runs"

> "With `--output-format stream-json`, denials appear as `permission_denied` system messages, and the final result message lists them in `permission_denials`."

**OBSERVED-CLI** — `claude -p "Create a file named probe_deny.txt containing the word hello using the Write tool" --output-format json --max-turns 3 --permission-mode dontAsk`, exit 0:
```json
"permission_denials": [
  {
    "tool_name": "Write",
    "tool_use_id": "call_function_h0vm078wby1b_1",
    "tool_input": {
      "file_path": "C:\\Users\\Admin\\Desktop\\Claude clone\\scratch-probe\\probe_deny.txt",
      "content": "hello\n"
    }
  }
]
```
`is_error` was `false`, `subtype` was `"success"`, `terminal_reason` was `"completed"`, `num_turns` was 2 — and **the file was not created** (confirmed by `ls`).

**Reimplementation note:** a denial is **not** a run failure. The run succeeds; the denial is a structured record with the tool name, the tool_use id, and the *full attempted tool input* (including the file path and content). That last part is a privacy consideration for a reimplementation: the envelope echoes arguments the user never approved. A clean-room implementation should redact or gate this field, or at minimum document that it is on the wire.

---

### H11 — Session identity and continuation: `--continue`, `--resume`, `--session-id`, `--no-session-persistence`

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Continue conversations"

> "Use `--continue` to continue the most recent conversation, or `--resume` with a session ID to continue a specific conversation. On Claude Code v2.1.257 or later, when you pass `--continue`, Claude Code opens a [background session] that has finished, but not one that is still running."
> "If you're running multiple conversations, capture the session ID to resume a specific one:
> ```bash
> session_id=$(claude -p "Start a review" --output-format json | jq -r '.session_id')
> claude -p "Continue that review" --resume "$session_id"
> ```
> You can run the two commands from different directories: Claude Code [finds the session by its ID] in any project on this machine."
> "In place of the session ID, you can pass `--resume` the absolute path to a session's `.jsonl` [transcript file], and Claude Code continues the conversation stored in that file."

**Source:** https://code.claude.com/docs/en/cli-reference.md — CLI flags table
> `| --no-session-persistence | Disable session persistence so sessions are not saved to disk and cannot be resumed. Print mode only. The CLAUDE_CODE_SKIP_PROMPT_HISTORY environment variable does the same in any mode | claude -p --no-session-persistence "query" |`
> `| --session-id | Use a specific session ID for the conversation (must be a valid UUID) | claude --session-id "550e8400-e29b-41d4-a716-446655440000" |`

**OBSERVED-CLI**
- `claude -p "Now say RESUMED" --resume <sid> --output-format json` → exit 0, `session_id` **equals** the resumed id, `result` = `"RESUMED"`, and the usage showed `input_tokens: 3046` with `cache_read_input_tokens: 11776` — i.e. the prior conversation was re-supplied and largely served from cache.
- `claude -p "Say NSP" --no-session-persistence --output-format json` → exit 0, `result` = `"NSP"`, `session_id` still emitted (a UUID) even though the session is not saved.
- `claude --bare -p "Reply with exactly: BAREOK" --session-id <fresh-uuid> --output-format json` → exit 0, `session_id` **equalled the supplied UUID exactly**, `total_cost_usd` = 0.005376 (vs ~0.057 in non-bare runs on this gateway — bare mode's smaller context is visible in the cost).
- `claude --bare -p … --session-id 11111111-2222-3333-4444-555555555555` (a UUID already in use) → exit 1, stderr: `Error: Session ID 11111111-2222-3333-4444-555555555555 is already in use.`

**Reimplementation note:** the **session-id-as-a-first-class-caller-supplied-value** pattern is worth copying: the caller can own the identity, so the caller can key its own persistence, correlation, and idempotency on it. The "already in use" collision check is also a good, cheap safety property.

---

### H12 — `--bare`: deterministic, credential-free, project-content-free non-interactive runs

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Start faster with bare mode"

> "Add `--bare` to reduce startup time by skipping auto-discovery of hooks, skills, custom commands, [subagents], installed plugins, MCP servers, auto memory, and CLAUDE.md. Without it, `claude -p` discovers and loads them as an interactive session would, including anything configured in the working directory or `~/.claude`."
> "In bare mode, Claude Code never reads OAuth credentials or the system keychain. For the Anthropic API, set `ANTHROPIC_API_KEY` in the environment, with a key created in the [Claude Console], or supply an `apiKeyHelper` in the `--settings` JSON. Amazon Bedrock, Google Cloud's Agent Platform, and Microsoft Foundry continue to read their own provider credentials as usual."
> "In bare mode Claude has access to the Bash, file read, and file edit tools. Pass any context you need with a flag:"
> (table: `--append-system-prompt`, `--append-system-prompt-file`, `--settings <file-or-json>`, `--mcp-config <file-or-json>`, `--agents <file-or-json>`, `--plugin-dir <path>`, `--plugin-url <url>`)

> "`--bare` is the recommended mode for scripted and SDK calls, and will become the default for `-p` in a future release."

**DOC — trust bypass** (same page, § "Start faster with bare mode"):
> "Without `--bare`, a `-p` session runs the hooks in a project's `.claude/settings.json` and connects the servers in its `.mcp.json`, even in a folder you've never trusted. A `-p` session shows no workspace trust dialog and no per-server approval prompt."

**DOC — bare-mode runtime limits** (same page):
> "* **MCP servers**: only servers supplied on the command line connect, for example with `--mcp-config`. In an interactive session, Claude Code also skips the automatic IDE connection unless you pass `--ide`.
> * **System reminders**: Claude gets your prompts and the tool results without the [system reminders] Claude Code would add alongside them. For example, Claude isn't told when a file it read earlier changes on disk, and it doesn't get the list of available skills, including skills from an `--add-dir` folder.
> * **Background tasks**: none run. A command that reaches its [timeout] stops instead of [moving to the background]."

**OBSERVED-CLI** — `claude --bare -p "Reply with exactly: BAREOK" --session-id <uuid> --output-format json`: exit 0, `session_id` echoed exactly, `total_cost_usd` 0.005376 vs 0.0572478 for the equivalent non-bare run — a 10x reduction in input tokens on this gateway, consistent with bare mode skipping the tool-set/system-prompt bulk.

**Reimplementation note:** `--bare` is the **determinism contract**. "Same result on every machine" requires that *no* ambient state is read: no user-level config, no project config, no credentials beyond an explicit env var or `apiKeyHelper`. An independent implementation should adopt an explicit "profile" concept (`--bare` / normal / `--safe-mode` / `--restricted`) with the same determinism guarantee, because it is the difference between a CI-usable agent and a non-reproducible one.

---

### H13 — stdin is the prompt channel; 10 MB cap; warning on unreadable stdin

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Pipe data through Claude"

> "Non-interactive mode reads stdin, so you can pipe data in and redirect the response out like any other command-line tool."
> "Piped stdin is capped at 10MB. If you exceed the cap, Claude Code exits with a clear error and a non-zero status. To work with larger inputs, write the content to a file and reference the file path in your prompt instead of piping it."
> "If Claude Code can't read stdin, for example because the process that started it disconnected its end, Claude Code prints a warning to stderr and continues with the prompt from the command line."

**OBSERVED-CLI**
- `printf 'Reply with exactly: PIPED\n' | claude -p --output-format text` → exit 0, stdout exactly `PIPED`.
- `claude -p "   "` → stderr `Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin explicitly: < /dev/null to skip, or wait longer.` then `Error: Input contained only whitespace. …`, exit 1.

**Reimplementation note:** the 3-second stdin grace period with a *specific, actionable* warning message is a small but real usability detail — it distinguishes "no stdin" from "stdin closed by the parent".

---

### H14 — Background work at exit: the wait, the 10-minute ceiling, and the env-var override

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/headless.md — § "Background tasks at exit"

> "After Claude finishes its turn and stdin has closed, a `claude -p` run can stay open to wait for background work that Claude started."
> "Unless a background command that the main conversation started is still running, Claude Code stops whatever is still running after 10 minutes of continuous idle waiting by default and drops its partial result. To change the 10-minute cap, set [`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`], or set it to `0` to wait without one."
> "The run waits for background work such as background commands, subagents and workflows, Monitor watches, and pending `/loop` wakeups"
> "When stderr is a terminal and the run has waited five seconds, Claude Code prints a line to stderr that starts with `Waiting for background work to finish` and names the work. With [`json` or `stream-json` output](#get-structured-output), the line prints only when stdout isn't a terminal, so the JSON your script reads never carries it."
> "If the run reaches its [`--max-budget-usd`] cap, Claude Code stops the remaining background work instead of waiting."
> "When background work starts another turn, the run prints each turn's result with the default `text` output and the last turn's result with `json` output."

**Reimplementation note:** "the JSON your script reads never carries it" is a strong, explicit design rule — **the machine channel is never polluted by human-oriented notices**. A reimplementer should adopt that rule as a hard invariant and route all human notices to stderr.

**UNKNOWN:** the exact set of "background work kinds" and the ordering guarantees between their completion messages and the final result. The doc names the categories but not a formal ordering contract.

---

### H15 — SIGTERM ⇒ exit 143; SIGINT is the graceful interrupt

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/headless.md — § "Stop a run with SIGTERM"

> "If you stop a `claude -p` run with SIGTERM, for example with `kill` or from a process supervisor, Claude Code exits with code 143. Claude Code leaves the turn that was in progress unfinished and records no result for it. To end the turn instead, send SIGINT, or call the Agent SDK's `interrupt()`, before you stop the process."
> "On SIGTERM, Claude Code terminates the process tree of any Bash command that is still running. Claude Code then runs [`SessionEnd` hooks] and exits. While exiting, Claude Code starts no new tool call, sends no new model request, and runs no hook other than `SessionEnd`."
> "* **Running a command**: Claude Code records the command as killed in the session.
> * **Waiting for an answer to a permission prompt**: if you send SIGTERM to the process, Claude Code leaves the prompt unanswered. If your program closes the session through the Agent SDK, the SDK ends Claude Code's input before sending any signal, and Claude Code cancels the prompt as soon as the input ends."
> "When you [resume the session], Claude Code leaves the interrupted turn as it is, and your next prompt drives the conversation. To have Claude Code continue the interrupted turn on resume instead, set [`CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1`]."

**Reimplementation note:** 143 = 128 + 15 (SIGTERM), which is the conventional shell encoding — worth matching exactly so supervisors behave identically.

---

### H16 — Auto-approve and permission flags usable in `-p`

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Auto-approve tools"

> "Use `--allowedTools` to let Claude use certain tools without prompting. Listing `Read` and `Edit` lets Claude read and edit files without asking for permission, apart from reads from [network paths]. Listing `Bash` does the same for shell commands, except in a run that starts in [auto mode], where Claude Code drops a bare `Bash` entry as a broad allow rule and auto mode evaluates each command instead."
> "Calls to tools you didn't list run if they need no approval. In a [Manual mode] `claude -p` run, a call that needs approval is denied unless something approves it, such as a [`PermissionRequest` hook] or a [`--permission-prompt-tool`]. With Claude Code v2.1.302 or later, `claude -p` runs start in Manual mode when [nothing sets a permission mode]."

> "To set a baseline for the whole session instead of listing individual tools, pass a [permission mode] with `--permission-mode`, such as `auto`, `dontAsk`, or `acceptEdits`"

**Source:** § "Turn off permission prompts in unattended runs"
> "Pass `--permission-prompts none` when nobody is available to answer permission prompts, for example in a scheduled job. … With the flag, your run doesn't consult the host or wait on it. Anything that would prompt is denied unless a `PermissionRequest` hook allows it, Claude is told that nobody can approve the request and not to retry it, and the run continues."
> "With `--permission-prompts none`, Claude Code removes the tools that need an answer from a person, such as [`AskUserQuestion`], so Claude can't call them."

**Source:** § "Create a commit" — permission rule syntax
> "The `--allowedTools` flag uses [permission rule syntax]. The trailing ` *` enables prefix matching, so `Bash(git diff *)` allows any command starting with `git diff`. The space before `*` is important: without it, `Bash(git diff*)` would also match `git diff-index`."

**OBSERVED-CLI**
- `--permission-mode dontAsk` + a `Write` request → the write was **denied**, the run still reported `subtype:"success"`, `is_error:false`, and the denial appeared in `permission_denials` (see H10). The file was not created.
- `--permission-prompts none` + a `Bash` request → the run completed with `subtype:"success"`, `permission_denials: []`, and the result text reported the command output.

**Reimplementation note:** the mode taxonomy (`manual` / `acceptEdits` / `dontAsk` / `auto` / `bypassPermissions` / `plan`) and the three `--allowedTools`/allow-rule/hook precedence layers are the transferable design; the detailed semantics belong to the Area-8 permission report already in this file.

---

### H17 — Command support differs in `-p`; slash commands take an argument

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/headless.md — § "Create a commit" (NOTE block)

> "* User-invoked [skills] and custom commands work. Include `/skill-name` in the prompt string and Claude Code expands it before running.
> * Built-in commands that only run in the terminal interface, such as `/login`, aren't available.
> * `/model`, `/effort`, `/fast`, `/color`, and `/rename` accept the value as an argument, for example `/model sonnet`, and `/mcp` with no argument prints a text summary of server status. These forms follow each command's [availability notes].
> * To change a setting, pass `key=value` to `/config`, for example `/config thinking=false`.
> * `/output-style <style>` switches [output styles] and `/output-style` alone lists them. Requires Claude Code v2.1.269 or later."

**Reimplementation note:** the "`/cmd value`" argument form and the "`/config key=value`" form are both trivially implementable and are the mechanism by which a headless caller changes model/effort/output-style without a second process.

---

### H18 — MCP and plugin load failures are machine-checkable via `system/init`

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Fail CI when a plugin or MCP server doesn't load"

> "Use the plugin fields in the `system/init` event to catch a plugin that didn't load:"
> `| plugins | array | plugins that loaded successfully, each with name and path |`
> `| plugin_errors | array | plugin load-time errors, each with plugin, type, and message. Includes unsatisfied dependency versions and --plugin-dir load failures such as a missing path or invalid archive. A plugin that didn't load is absent from plugins. The key is omitted when there are no errors |`

> `| mcp_servers | array | MCP servers in the session, each with name and status |`
> `| mcp_server_errors | array | --mcp-config entries skipped by config validation, each with name, type, and message. type is a skip category such as unknown_type, url_missing_type, invalid_config, or reserved_name; treat values you don't recognize as a generic skip. Affected servers are absent from mcp_servers. The key is omitted when there are no errors, so a CI gate can fail on a non-empty array. Requires Claude Code v2.1.219 or later |`

> "When you pass [`--mcp-config`] with `-p`, Claude Code waits for still-pending servers before running the first turn, up to the [`MCP_TIMEOUT`] startup timeout, 30 seconds by default. A remote server with a [cached tool list] skips the wait, shows `pending` in `system/init`, and connects on its first tool call."

> "When you run the command by hand in a terminal, Claude Code also prints a startup warning to stderr, such as `Warning: 1 MCP server skipped due to invalid config:`, followed by the reason for each skipped entry. When you redirect stderr, or when a program such as a CI runner or an SDK host captures it, Claude Code prints no warning and reports the skipped entries only in the `mcp_server_errors` field."

**OBSERVED-CLI** — the observed `system/init` carried `"mcp_servers":[{"name":"rea","status":"pending","source":"user"}]`, and a later `-p` run's result text reported: *"Note: the `rea` MCP server failed to connect (timeout after 30s), but it wasn't needed for this command."* — confirming the 30-second `MCP_TIMEOUT` default and that a failed server does **not** fail the run.

**Reimplementation note:** the `mcp_servers` / `mcp_server_errors` split, with the *"key is omitted when there are no errors"* convention, is a clean contract for a CI gate: `if (init.mcp_server_errors?.length) fail()`. The "treat values you don't recognize as a generic skip" instruction for `type` is a forward-compatibility rule worth copying verbatim.

---

### H19 — Retry and error events are exposed to the stream

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/headless.md — § "Handle API retries"

> "When an API request fails with a retryable error, Claude Code emits a `system/api_retry` event before retrying. On v2.1.246 or later, when a `401` or `403` rejects an [`apiKeyHelper`] credential, Claude Code makes the first two retries quietly with no event, then emits the event as usual from the third consecutive retry onward. The quiet retries still count toward `attempt`."

> `| type | "system" | message type |`
> `| subtype | "api_retry" | identifies this as a retry event |`
> `| attempt | integer | current attempt number, starting at 1 |`
> `| max_retries | integer | total retries permitted for this failure's cause |`
> `| retry_delay_ms | integer | milliseconds until the next attempt |`
> `| error_status | integer or null | HTTP status code of the failed attempt, or null when the attempt got no HTTP response from the API |`
> `| no_response | object, optional | present only when the failed attempt got no response headers in time. waited_ms is how long that attempt waited and retry_wait_ms is how long the retry will wait. Requires Claude Code v2.1.261 or later |`
> `| error | string | error category: authentication_failed, oauth_org_not_allowed, account_on_hold, billing_error, rate_limit, overloaded, invalid_request, model_not_found, server_error, max_output_tokens, cloud_credential_error, or unknown |`
> `| uuid | string | unique event identifier |`
> `| session_id | string | session the event belongs to |`

**Related (OBSERVED-DOC)** — https://code.claude.com/docs/en/errors.md, § "Automatic retries":
> "Claude Code retries transient failures up to 10 times with exponential backoff before showing you an error."
> `| CLAUDE_CODE_MAX_RETRIES | 10 | Number of retry attempts. Capped at 15 as of v2.1.186 … |`
> `| API_TIMEOUT_MS | 600000 | Time in milliseconds that each request attempt has to receive its response headers. It doesn't limit how long a streaming response runs after that. |`

**Reimplementation note:** the `error` category enum is a **stable, machine-actionable vocabulary** (`authentication_failed`, `rate_limit`, `overloaded`, `invalid_request`, `model_not_found`, `server_error`, …). A reimplementer should adopt exactly these strings, because automation written against them is the point of having them.

---

### H20 — Cost accounting is client-side and per-model

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Pipe data through Claude"

> "With `--output-format json`, the response payload includes `total_cost_usd` and a per-model cost breakdown, so scripted callers can track spend without consulting the [usage dashboard]. When you continue an earlier conversation with `--continue` or `--resume`, the run reports the conversation's whole total, [earlier runs' spend included]. Both figures are [client-side estimates] and can differ from your actual bill."

**Source:** https://code.claude.com/docs/en/agent-sdk/typescript.md
> "`total_cost_usd`: cumulative estimated cost in USD, covering the same calls as `modelUsage` and reset at the same points. … It is an estimate, not a billing statement."
> "`usage`: main agent loop only. Excludes subagent and auxiliary model calls, and is per-turn in streaming-input sessions. Prefer `modelUsage` for token/cost accounting."
> "`modelUsage`: per-model totals for every model call made through the query pipeline during this `query()` call, including the main loop, subagents, and internal calls such as compaction and Workflow agents. Helper calls outside that pipeline, such as the permission classifier and token-counting requests, are excluded."

**OBSERVED-CLI** — the observed envelope's `modelUsage` had one key, the gateway model string, with `costBasis: "unknown"` (the gateway's price table was not in Claude Code's list). `usage` reported `input_tokens: 14287` while `modelUsage[…].inputTokens` also reported 14287 and `cache_read_input_tokens: 199` vs `cacheReadInputTokens: 199` — confirming that `usage` and `modelUsage` are two views of the same ledger in the single-model case, with `modelUsage` being the authoritative per-model view.

---

### H21 — System prompt control: `--append-system-prompt` vs `--system-prompt`

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/headless.md — § "Customize the system prompt"

> "Use `--append-system-prompt` to add instructions while keeping Claude Code's default behavior."
> "See [system prompt flags] for more options including `--system-prompt` to fully replace the default prompt. If you replace it, the run also starts without the [git status snapshot]."

**Reimplementation note:** the *observable* consequence of full replacement (loss of the git-status snapshot) is a non-obvious, high-value detail — it tells an implementer that "replace the system prompt" also silently drops a repository-context injection. An independent implementation should make the same coupling explicit and documented.

---

### H22 — Working directory deleted mid-session

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/headless.md — § "If the working directory is deleted"

> "If the working directory of a `claude -p` or Agent SDK session is deleted mid-session, the session keeps running. When a turn starts while the directory is missing, Claude Code emits a [warning message] in `stream-json` output, and shell commands fail until the directory exists again."

---

### H23 — `--prompt-suggestions` and `--replay-user-messages` are stream-json-only affordances

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/cli-reference.md
> `| --prompt-suggestions | Emit a prompt_suggestion message with a predicted next user prompt after each turn that generates one; very short conversations can produce none. Requires --print, --output-format stream-json, and --verbose. |`
> `| --replay-user-messages | Re-emit user messages from stdin back on stdout for acknowledgment. Requires --input-format stream-json and --output-format stream-json |`

**OBSERVED-CLI** — `--replay-user-messages` produced a `user` message with `isReplay: true` and the original `message` payload (see H6).

---

### H24 — Print mode bypasses the workspace trust dialog

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/headless.md — § "Start faster with bare mode"
> "A `-p` session shows no workspace trust dialog and no per-server approval prompt."

**Source:** `claude --help` (OBSERVED-CLI)
> "The workspace trust dialog is skipped when Claude is run in non-interactive mode (via -p, or when stdout is not a TTY, e.g. piped or redirected output). Only use this in directories you trust. Settings files that fail validation are silently ignored in this mode (no error dialog is shown)."

**Reimplementation note (a real risk to flag):** print mode executes project-local configuration — hooks from `.claude/settings.json`, MCP servers from `.mcp.json`, skills, CLAUDE.md — **without a trust prompt**, in any directory, including one the user has never approved. Claude Code's mitigation is `--bare`. A clean-room implementation should make the *secure default* the opposite of Claude Code's: require an explicit opt-in for ambient project configuration in non-interactive mode, or at minimum print a loud, machine-greppable warning naming what was loaded from the working directory.

---

### H25 — `--max-turns` and `--max-budget-usd` are print-mode-only caps

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/cli-reference.md
> `| --max-turns | Limit the number of agentic turns (print mode only). Exits with an error when the limit is reached. No limit by default. With --input-format stream-json, a message still queued when the limit ends a turn stays queued and starts a new turn with its own limit |`
> `| --max-budget-usd <amount> | Maximum dollar amount to spend on API calls (only works with --print) |`

**OBSERVED-CLI** — `--max-turns 1` → `subtype:"error_max_turns"`, `terminal_reason:"max_turns"`, `errors:["Reached maximum number of turns (1)"]`, exit 1. `--max-budget-usd 0.0001` → `subtype:"error_max_budget_usd"`, `terminal_reason:"budget_exhausted"`, `errors:["Reached maximum budget ($0.0001)"]`, `result:null`, exit 1.

**Reimplementation note:** the budget cap is evaluated *after* the turn that crosses it (the observed run still billed $0.0618 while the cap was $0.0001) — the cap stops *subsequent* work, it is not a pre-flight reservation. An implementer should either match this (and document it) or implement a strict pre-flight check; consumers must not assume the cap is a hard ceiling on spend.

---

## 7b.4 Capability table

| Capability | Flags / env | Status | Evidence |
|---|---|---|---|
| Non-interactive run | `-p` / `--print` | OBSERVED-DOC + OBSERVED-CLI | H1 |
| Plain-text output (default) | `--output-format text` | OBSERVED-DOC + OBSERVED-CLI | H2, H13 |
| Single-object JSON output | `--output-format json` | OBSERVED-DOC + OBSERVED-CLI | H3 |
| Newline-delimited JSON events | `--output-format stream-json --verbose` | OBSERVED-DOC + OBSERVED-CLI | H4 |
| Token-level streaming | `--include-partial-messages` (stream-json only) | OBSERVED-DOC + OBSERVED-CLI | H4, H7 |
| Structured output via JSON Schema | `--json-schema` | OBSERVED-DOC + OBSERVED-CLI | H8 |
| Schema validation failure ⇒ exit 1 | `--json-schema` | OBSERVED-CLI | H7 |
| Multi-turn input over stdin | `--input-format stream-json` | OBSERVED-DOC + OBSERVED-CLI | H6 |
| Input acknowledgement | `--replay-user-messages` | OBSERVED-DOC + OBSERVED-CLI | H6, H23 |
| Prompt from stdin (text) | `-p` + pipe | OBSERVED-DOC + OBSERVED-CLI | H13 |
| 10 MB stdin cap | — | OBSERVED-DOC | H13 |
| Session id in the envelope | `session_id` field | OBSERVED-DOC + OBSERVED-CLI | H3 |
| Caller-supplied session id | `--session-id <uuid>` | OBSERVED-DOC + OBSERVED-CLI | H11 |
| Continue most-recent session | `--continue` | OBSERVED-DOC + OBSERVED-CLI | H11 |
| Resume a specific session | `--resume <id>` or `<path>.jsonl` | OBSERVED-DOC + OBSERVED-CLI | H11 |
| Opt out of persistence | `--no-session-persistence` | OBSERVED-DOC + OBSERVED-CLI | H11 |
| Deterministic / credential-free mode | `--bare` | OBSERVED-DOC + OBSERVED-CLI | H12 |
| Auto-approve tools | `--allowedTools` | OBSERVED-DOC + OBSERVED-CLI | H16 |
| Baseline permission mode | `--permission-mode` | OBSERVED-DOC + OBSERVED-CLI | H16 |
| Unattended permission denial | `--permission-prompts none` | OBSERVED-DOC + OBSERVED-CLI | H16 |
| Turn cap | `--max-turns` | OBSERVED-DOC + OBSERVED-CLI | H25 |
| Spend cap | `--max-budget-usd` | OBSERVED-DOC + OBSERVED-CLI | H25 |
| Session manifest on the wire | `system/init` | OBSERVED-DOC + OBSERVED-CLI | H5 |
| Capability feature-detection | `capabilities[]` | OBSERVED-DOC + OBSERVED-CLI | H5 |
| Retry progress events | `system/api_retry` | OBSERVED-DOC | H19 |
| Plugin / MCP load health | `plugins[]`, `plugin_errors[]`, `mcp_servers[]`, `mcp_server_errors[]` | OBSERVED-DOC + OBSERVED-CLI | H18 |
| Subagent transcript nesting | `parent_tool_use_id` + `--forward-subagent-text` | OBSERVED-DOC | § "Follow subagent messages" |
| Prompt prediction | `--prompt-suggestions` | OBSERVED-DOC | H23 |
| Graceful stop | SIGINT / SDK `interrupt()` | OBSERVED-DOC | H15 |
| Hard stop | SIGTERM ⇒ exit 143 | OBSERVED-DOC | H15 |
| Continue an interrupted turn on resume | `CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1` | OBSERVED-DOC | H15 |
| Background-wait ceiling | `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` | OBSERVED-DOC | H14 |
| Retry tuning | `CLAUDE_CODE_MAX_RETRIES`, `API_TIMEOUT_MS`, `CLAUDE_CODE_RETRY_WATCHDOG` | OBSERVED-DOC | H19 |
| Custom system prompt | `--append-system-prompt`, `--system-prompt` | OBSERVED-DOC | H21 |
| MCP servers for one run | `--mcp-config` | OBSERVED-DOC | H12, H18 |
| Custom agents for one run | `--agents` | OBSERVED-DOC | H12 |
| Plugin for one run | `--plugin-dir`, `--plugin-url` | OBSERVED-DOC | H12 |
| Settings for one run | `--settings` | OBSERVED-DOC | H12 |
| Git status snapshot | implicit; dropped by `--system-prompt` | OBSERVED-DOC | H21 |

---

## 7b.5 Dependencies

### Requires network
Every headless run requires a reachable model endpoint. On this host that was a custom `ANTHROPIC_BASE_URL` gateway, not `api.anthropic.com`.

### Requires an account or a credential
- Normal mode: a Claude subscription login (OAuth) **or** an API key.
- `--bare`: **no OAuth, no keychain** — `ANTHROPIC_API_KEY` or an `apiKeyHelper` in `--settings`. Third-party providers (Bedrock / Google Cloud Agent Platform / Microsoft Foundry) read their own credentials.
- `--betas` is documented in the CLI help as "(API key users only)".

### Requires a model provider
Any model the provider serves. The CLI help documents `--model` as: *"Model for the current session. Provide an alias for the latest model (e.g. 'fable', 'opus', or 'sonnet') or a model's full name."*

### External services (optional)
- MCP servers (`--mcp-config` / `.mcp.json`) — network/process dependencies; the 30-second `MCP_TIMEOUT` default was observed as a real failure mode on this host.
- Plugin marketplaces (`--plugin-url`, `CLAUDE_CODE_SYNC_PLUGIN_INSTALL`).
- Model gateways (`ANTHROPIC_BASE_URL`) — observed to trigger an explicit stderr warning when the model string is unrecognized:
  `Claude Code doesn't recognize the model "minimax/minimax-m3.1-flash:free", so it assumes a context window of 200k tokens. …`
  plus a structured stderr line `[claude-code:unrecognized_model] {"model":"…","query_source":"sdk"}`.

### Local only
`--help`, `--version`, flag validation, `--json-schema` validation, and exit codes all work with no network at all.

---

## 7b.6 Limitations of this investigation

1. **The provider was not Anthropic.** Every observed cost, token count, and context window reflects a third-party gateway. `contextWindow: 200000` and `maxOutputTokens: 32000` in the observed `modelUsage` are the CLI's *fallbacks* for an unrecognized model, not Anthropic values. The *shape* of the envelope is reliable; the *numbers* are not representative.
2. **Subscription-gated features are doc-only here:** `/cloud`, cloud sessions, Remote Control, artifacts, org policy, `claude.ai` login, Anthropic-API fast mode, and the Anthropic-specific retry/backoff tuning were **not** observable. They are marked OBSERVED-DOC.
3. **No TUI observation.** This area covers `-p` only. Interactive rendering, the spinner, the transcript viewer, and `/doctor`'s interactive variant were out of scope.
4. **No deep inspection.** Per the compliance boundary, the binary was not decompiled, its bundled JS was not extracted, no source maps were dumped, and no credential store or licence file was read. Every claim rests on the published docs or on running the published CLI.
5. **Version drift.** The docs carry many `v2.1.xxx` minimum-version notes; this host is 2.1.306, so most recent features were available, but the *minimum* version for each feature matters to a reimplementer targeting older baselines.
6. **The `--continue` failure** observed on this host (`API Error: 400 Invalid Anthropic Messages API request`) is attributed to the gateway/model combination, not to Claude Code. It is not treated as a Claude Code defect.
7. **Some observed behaviour came from a model that ignored the intended constraint.** In one `--permission-prompts none` run the model volunteered a note about an unrelated MCP server failing. The *envelope* behaviour is reliable; the model's narration is not part of the contract.

---

## 7b.7 Unresolved questions (UNKNOWN)

1. **Exact ordering guarantees** between `system/init`, `hook_started`, `plugin_install`, `assistant`/`user` messages, and `result` in a `stream-json` run when several startup sources race. The doc says `system/init` "is the first event in the stream **unless** startup events precede it" but does not enumerate the precedence.
2. **The complete `type`/`subtype` vocabulary of the `system` channel.** Observed and documented: `init`, `status`, `thinking_tokens`, `api_retry`, `plugin_install`, `permission_denied`, `compact_boundary`, `informational`, `worker_shutting_down`, `hook_started`, `hook_progress`, `hook_response`, `task_started`, `task_progress`, `task_updated`, `task_notification`, `background_tasks_changed`, `session_state_changed`, `files_persisted`, `local_command_output`, `commands_changed`. The full list and the semantics of each were not fully enumerated for this page.
3. **The precise `terminal_reason` → exit-code mapping.** Observed: `max_turns` ⇒ 1, `budget_exhausted` ⇒ 1, `error_during_execution` ⇒ 1, `completed` ⇒ 0. Whether *every* non-`completed` `terminal_reason` maps to 1 was not established (e.g. `tool_deferred`, `hook_stopped`, `aborted_streaming`).
4. **The `usage` vs `modelUsage` reset semantics** in `--input-format stream-json` sessions ("the totals are cumulative across turns, so read the latest result rather than summing across results" — doc states it, but the boundary between "per-turn" and "cumulative" was not empirically mapped).
5. **Whether `--output-format json` writes exactly one object or can write more than one** when a run produces several turns. Observed: one object for a single-prompt run; the doc says "the last turn's result with `json` output" (§ "Background tasks at exit"), implying **one** result per run — but the exact behaviour for multi-turn background work was not reproduced on this host.
6. **The `deferred_tool_use` round trip** (`stop_reason: "tool_deferred"`) was not exercised — it requires a `PreToolUse` hook returning `permissionDecision: "defer"`.
7. **Exact `stderr` text for every failure class.** Only the ones listed in H7 were captured; the full catalogue lives in the errors reference and was not exhausted.
8. **Whether the 10 MB stdin cap applies to `--input-format stream-json` too**, or only to `--input-format text`. The doc states the cap under "Pipe data through Claude", which is the text path.
9. **The `system/init` `tools[]` list under `--bare`**: the shared protocol notes record `Bash, Edit, PowerShell, Read`; this page's text says "the Bash, file read, and file edit tools". The exact list and whether it is platform-dependent was not re-verified here.

---

## 7b.8 Recommended scope for an independent functional implementation

### Tier 1 — the parity core (implement this first)

1. **A one-object result envelope with the documented field set.** `type`, `subtype`, `is_error`, `result`, `session_id`, `uuid`, `num_turns`, `stop_reason`, `terminal_reason`, `duration_ms`, `duration_api_ms`, `ttft_ms`, `ttft_stream_ms`, `usage`, `modelUsage`, `total_cost_usd`, `permission_denials`, `errors`, `structured_output`, `result_index`, `queued_turn_count`, `fast_mode_state`, `fast_mode_disabled_reason`. Use a **stable field order** and always emit the same keys (null rather than omitting) except where the doc explicitly says the key is omitted.
   *How:* define the envelope as a versioned JSON Schema in your own repo and generate the TypeScript/Python types from it. Emit one object per line in `stream-json` and one object total in `json` mode.
2. **Three output modes + two input modes**, with the exact flag names `-p`, `--print`, `--output-format`, `--input-format`, `--verbose`, `--include-partial-messages`, `--json-schema`, `--replay-user-messages`, `--forward-subagent-text`, `--include-hook-events`.
3. **A pre-flight flag-compatibility validator** that rejects invalid combinations with exit 1 and the documented message wording, before any model call. Implement it as a declarative matrix (`{flag, requires, conflicts}`) so it stays maintainable.
4. **The exit-code discipline**: 0 on success, 1 on any failure (flag, startup, semantic), 143 on SIGTERM. Keep stdout parseable in every failure case: a *run* failure prints a `result` object on stdout; a *startup* failure prints a plain error on stderr.
5. **In-band failure reporting** via `subtype` + `terminal_reason` + `errors[]`, with the same subtype vocabulary (`success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries`) and the same terminal-reason vocabulary.
6. **A `--strict` / `--bare` profile** that guarantees no ambient state is read: no user config, no project config, no CLAUDE.md, no hooks, no plugins, no MCP servers unless explicitly passed, and credentials only from an explicit env var or a configured credential helper.
7. **`session_id` as a first-class, caller-suppliable value**, with a collision check and an opt-out from persistence.

### Tier 2 — strong differentiation

8. **A `system/init` manifest** carrying `cwd`, `session_id`, `tools[]`, `mcp_servers[]`, `model`, `permissionMode`, `skills[]`, `agents[]`, `plugins[]`, `capabilities[]` — and a **capabilities array** rather than version gating. Emit `mcp_server_errors[]` / `plugin_errors[]` only when non-empty, matching the "key is omitted when there are no errors" convention.
9. **An `api_retry` system event** with `attempt`, `max_retries`, `retry_delay_ms`, `error_status`, `error`, `uuid`, `session_id`, and the stable error-category vocabulary (`authentication_failed`, `rate_limit`, `overloaded`, `invalid_request`, `model_not_found`, `server_error`, …). This is what lets a CI UI show retry progress instead of hanging.
10. **A `permission_denials[]` record with `tool_name`, `tool_use_id`, `tool_input`** — but **redact or gate `tool_input`** (Claude Code echoes the full attempted input, including file contents, into a machine channel).
11. **Deterministic and quiet channels**: stdout carries only the protocol; every human-facing notice goes to stderr; never let a notice into a JSON stream.
12. **Turn and spend caps** (`--max-turns`, `--max-budget-usd`) with the same in-band error reporting. Document explicitly that the budget cap is a *stop*, not a pre-flight reservation.
13. **`--json-schema` structured output** with an optional `structured_output` field next to `result`, and `format` accepted as an annotation (not enforced).

### Tier 3 — nice to have

14. `--forward-subagent-text` and `parent_tool_use_id` nesting so a host can rebuild a subagent tree.
15. `--include-hook-events` and the hook lifecycle events.
16. `--prompt-suggestions`.
17. `--replay-user-messages` acknowledgements.
18. A `deferred_tool_use` round trip.

### Explicitly out of scope — recommend NOT replicating

19. **Do not replicate the trust bypass.** Claude Code's print mode runs project-local hooks, MCP servers, skills, and CLAUDE.md with **no trust prompt** in any directory. An independent implementation should invert this: require an explicit opt-in for ambient project configuration in non-interactive mode, and emit a greppable warning naming what was loaded from the working directory. This is a defensible, user-visible difference.
20. **Do not replicate the `format` keyword being ignored** if you can enforce it — JSON Schema's `format` is advisory by spec, but a stricter implementation is a net improvement; just document the divergence.
21. **Do not replicate the exact cost figures.** They are client-side estimates that depend on Anthropic's price table; a reimplementation should compute cost from its own price table and label it an estimate.

---

## 7b.9 Clean-room implementation opportunity (headless mode)

**The observable contract** (all public, all reproduced from the docs and from black-box observation):

- A CLI that, given `-p`, reads a prompt from argv and/or stdin, runs one agent loop, and terminates.
- stdout carries a protocol: one text blob, one JSON object, or a newline-delimited JSON event stream whose last line is that same JSON object.
- stderr carries human-facing diagnostics only.
- The process exit code encodes success/failure (0 / 1 / 143).
- The JSON object is a fixed-shape envelope with a documented field set and machine-readable enums.

**How to build the same function independently, without copying Anthropic code:**

- **Define the envelope as data, not code.** Write a JSON Schema (or a TS/Python type file) in *your* repo describing the result envelope; generate the serializers from it. The field names and the enum values are a **published interface** (documented at code.claude.com/docs), so using the same names is interface compatibility, not code copying.
- **Emit the protocol from a single writer.** Have the agent loop produce typed internal events, and one adapter serialize them to `text` / `json` / `stream-json`. This makes "the JSON your script reads never carries a notice" an architectural property rather than a convention.
- **Separate the failure channels explicitly.** Three sinks: `protocol` (stdout), `diagnostics` (stderr), `exit code`. Write a single `finish(run)` function that decides which of the three carries a given failure class — this is the invariant that makes the CLI scriptable.
- **Validate flags before doing work.** A small declarative compatibility matrix, evaluated at argument-parse time, with the exact error strings from the docs.
- **Make the ambient-state boundary a first-class concept.** Implement `--bare` (and equivalents) as "do not read user/project/plugin/MCP/credential state", and additionally implement the trust gate that Claude Code omits in print mode.
- **Use your own provider abstraction.** The envelope's `usage`/`modelUsage`/`total_cost_usd` fields are provider-neutral; fill them from your own tokenizer/price table and mark them as estimates.
- **Test the contract, not the implementation.** Golden-file tests over the emitted envelopes: one per `subtype`, one per `terminal_reason`, one for the denial shape, one for the structured-output shape, one for each rejected flag combination with its exact stderr text and exit code.

**Legality/clean-room note:** the artefacts reproduced here are (a) public documentation text, (b) observable CLI output, and (c) interface shapes. No Anthropic source was read, decompiled, or de-obfuscated; no binary was modified; no credential was accessed. Building to the same *published interface* is the standard clean-room pattern.

---

## 7b.10 Evidence index

| Artifact | Path |
|---|---|
| This report | `agent-evidence.md` § "Area 7b — Headless / Programmatic Mode" |
| Primary doc as fetched | `agent-reference-shots/area-headless-programmatic/doc-headless.md` (from `https://code.claude.com/docs/en/headless.md`) |
| CLI reference as fetched | `agent-reference-shots/area-headless-programmatic/doc-cli-reference.md` (from `https://code.claude.com/docs/en/cli-reference.md`) |
| Observed `--output-format json` envelope | `agent-reference-shots/area-headless-programmatic/print-json-result.json` |
| Observed `stream-json` event sequence | `agent-reference-shots/area-headless-programmatic/stream-json-events.jsonl` |
| Observed `--json-schema` structured output | `agent-reference-shots/area-headless-programmatic/structured-output-json-schema.json` |
| Observed `--max-turns` failure | `agent-reference-shots/area-headless-programmatic/max-turns-error.txt` |
| Observed `--max-budget-usd` failure | `agent-reference-shots/area-headless-programmatic/max-budget-usd-error.json` |
| Observed `dontAsk` permission denials | `agent-reference-shots/area-headless-programmatic/dontask-permission-denials.json` |
| Observed `--bare` run | `agent-reference-shots/area-headless-programmatic/bare-mode-result.json` |
| This section, standalone | `agent-reference-shots/area-headless-programmatic/AREA-7b-SECTION.md` |
| Shared black-box protocol notes | `agent-reference-shots/PROTOCOL-NOTES.md` |
| Compliance boundary | `agent-reference-shots/TERMS-NOTES.md` |

### Public documentation fetched during this investigation
- `https://code.claude.com/docs/en/headless.md` (primary page)
- `https://code.claude.com/docs/en/cli-reference.md`
- `https://code.claude.com/docs/en/errors.md`
- `https://code.claude.com/docs/en/agent-sdk/typescript.md` (typed contract for the result envelope)
- `https://code.claude.com/docs/llms.txt` (documentation index)
