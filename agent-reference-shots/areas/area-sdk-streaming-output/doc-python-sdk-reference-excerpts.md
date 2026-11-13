### `Message`

Union type of all possible messages.

```python theme={null}
Message = (
    UserMessage
    | AssistantMessage
    | SystemMessage
    | ResultMessage
    | StreamEvent
    | RateLimitEvent
    | ConversationResetMessage
)
```


### `AssistantMessage`

Assistant response message with content blocks.

```python theme={null}
@dataclass
class AssistantMessage:
    content: list[ContentBlock]
    model: str
    parent_tool_use_id: str | None = None
    error: AssistantMessageError | None = None
    usage: dict[str, Any] | None = None
    message_id: str | None = None
    stop_reason: str | None = None
    session_id: str | None = None
    uuid: str | None = None
```

| Field | Type | Description |
| :- | :- | :- |
| `content` | `list[ContentBlock]` | List of content blocks in the response |
| `model` | `str` | Model that generated the response |
| `parent_tool_use_id` | `str \| None` | Tool use ID if this is a nested response |
| `error` | [`AssistantMessageError`](#assistantmessageerror) ` \| None` | Error type if the response encountered an error |
| `usage` | `dict[str, Any] \| None` | Per-message token usage (same keys as [`ResultMessage.usage`](#resultmessage)) |
| `message_id` | `str \| None` | API message ID. Multiple messages from one turn share the same ID |
| `stop_reason` | `str \| None` | Stop reason from the API (for example, `end_turn`, `tool_use`) |
| `session_id` | `str \| None` | ID of the session this message belongs to |
| `uuid` | `str \| None` | Unique message identifier within the session transcript |


### `SystemMessage`

System message with metadata.

```python theme={null}
@dataclass
class SystemMessage:
    subtype: str
    data: dict[str, Any]
```

Subtypes that have no dataclass of their own arrive as `SystemMessage`. To follow the session between turns, set [`CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS=1`](/docs/en/env-vars#variables) and read `message.data["state"]` on each message whose `subtype` is `session_state_changed`. [`SDKSessionStateChangedMessage`](/docs/en/agent-sdk/typescript#sdksessionstatechangedmessage) lists the states it can carry. Iterate with `receive_messages()` to read them: `receive_response()` stops at the `ResultMessage`, and a `session_state_changed` message can follow that result.


### `ResultMessage`

Final result message with cost and usage information.

```python theme={null}
@dataclass
class ResultMessage:
    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    stop_reason: str | None = None
    total_cost_usd: float | None = None
    usage: dict[str, Any] | None = None
    result: str | None = None
    structured_output: Any = None
    model_usage: dict[str, ModelUsage] | None = None
    permission_denials: list[Any] | None = None
    deferred_tool_use: DeferredToolUse | None = None
    errors: list[str] | None = None
    api_error_status: int | None = None
    uuid: str | None = None
    terminal_reason: str | None = None
    origin: MessageOrigin | None = None
```

The `subtype` field determines which other fields are populated. It is one of `"success"`, `"error_during_execution"`, `"error_max_turns"`, `"error_max_budget_usd"`, or `"error_max_structured_output_retries"`. The Python dataclass flattens all variants into one shape, so fields that don't apply to the returned subtype are `None`.

Several fields carry diagnostic detail about how the conversation ended:

* `is_error`: `True` when the conversation ended in an error state. Always `True` on the `error_*` subtypes. On `subtype="success"` it is `True` in three cases. Check `stop_reason` to tell them apart:
  * `"refusal"`: the model declined to respond. Read the refusal text in `result`, or in the preceding `AssistantMessage` when `result` is empty.
  * `"tool_deferred_unavailable"`: the [deferred tool](/docs/en/hooks#defer-a-tool-call-for-later) was no longer available when you resumed the session, for example because its MCP server wasn't connected. In the two cases below, a prompt you send after resuming counts the same as one passed with the resume:
    * No prompt: the call is still pending. Make the tool available and resume again without a prompt, and the call runs first.
    * A prompt: Claude Code answers it without the tool's result, and the deferred call is gone. Send a new prompt if you still need the tool called.
  * Any other value: the turn ended on an error that Claude Code reported in place of a model response, such as an API error. Read `terminal_reason` for the cause, `result` for the message, and `api_error_status` for the HTTP status when the API returned one.
* `api_error_status`: the HTTP status code of the terminating API error. `None` when the turn ended without one. Populated only on `subtype="success"`.
* `result`: text of the final assistant message on `subtype="success"`, or `None` on the `error_*` subtypes. When `subtype="success"` and `is_error=True`, this holds the API error string if one is available but can be empty, so check `api_error_status` and the preceding `AssistantMessage` content for detail.
* `errors`: loop-level error strings such as the max-turns message. Populated only on the `error_*` subtypes.
* `terminal_reason`: why the query loop ended, such as `"completed"`, `"max_turns"`, `"api_error"`, `"aborted_streaming"`, or `"aborted_tools"`. A value of `"aborted_streaming"` or `"aborted_tools"` means the turn was aborted before completing. Common causes are [`interrupt()`](#claudesdkclient) and a permission callback returning [`PermissionResultDeny`](#permissionresultdeny) with `interrupt=True`. `None` on CLI versions that predate the field, on results from local commands such as `/voice` or `/usage`, which bypass the query loop, or on synthesized error results emitted when the session fails fatally. Mirrors the TypeScript SDK's [`SDKResultMessage.terminal_reason`](/docs/en/agent-sdk/typescript#sdkresultmessage), which lists the full set of values.
* `origin`: origin of the user message that triggered this turn. In [streaming input mode](/docs/en/agent-sdk/streaming-vs-single-mode), check this to tell the result of your own prompt, where `origin` is `None` or `{"kind": "human"}`, from the result of an injected turn such as a background-task notification. Requires Python Agent SDK 0.2.137 or later.

When several background tasks finish close together, Claude Code can answer their notifications in one turn rather than one turn each. You still receive one `ResultMessage` per notification, in order, each with an `origin` whose `kind` is `"task-notification"`. All but the last have `num_turns` set to `0` and an empty `result`, and the last one carries the turn that answers them all.

The `usage` dict covers the main agent loop only and excludes subagent and other nested or auxiliary model calls. In [streaming input mode](/docs/en/agent-sdk/streaming-vs-single-mode), the values are per-turn. Prefer `model_usage` for token and cost accounting. The `usage` dict contains the following keys when present:

| Key | Type | Description |
| - | - | - |
| `input_tokens` | `int` | Input tokens consumed by the top-level agent loop. [Subagent tokens aren't included](/docs/en/agent-sdk/cost-tracking#get-the-total-cost-of-a-query); use `model_usage` for whole-tree accounting. |
| `output_tokens` | `int` | Output tokens generated by the top-level agent loop. Subagent tokens aren't included. |
| `cache_creation_input_tokens` | `int` | Tokens used to create new cache entries. |
| `cache_read_input_tokens` | `int` | Tokens read from existing cache entries. |

The `model_usage` dict maps model names to per-model usage. It covers every model call made through the query pipeline: the main loop, subagents, and internal calls such as compaction and Workflow agents. Helper calls outside that pipeline, such as the permission classifier and token-counting requests, are excluded from `model_usage`. Treat `model_usage` as an estimate, not a billing statement.

In [streaming input mode](/docs/en/agent-sdk/streaming-vs-single-mode), `model_usage` and `total_cost_usd` are cumulative across turns, so read the latest result rather than summing across results. A call that resumes a session also counts the [totals restored from the session's earlier calls](/docs/en/agent-sdk/cost-tracking#accumulate-costs-across-multiple-calls). See [Track costs in streaming input mode](/docs/en/agent-sdk/cost-tracking#track-costs-in-streaming-input-mode) for resets and [Recover totals after a session crash](/docs/en/agent-sdk/cost-tracking#recover-totals-after-a-session-crash) for zeroed results.

Each value in `model_usage` is a `ModelUsage` TypedDict, imported via `from claude_agent_sdk.types import ModelUsage`. Its keys use camelCase because the SDK passes the value through unmodified from the underlying CLI process, matching the TypeScript [`ModelUsage`](/docs/en/agent-sdk/typescript#modelusage) type:

| Key | Type | Description |
| - | - | - |
| `inputTokens` | `int` | Input tokens for this model. |
| `outputTokens` | `int` | Output tokens for this model. |
| `cacheReadInputTokens` | `int` | Cache read tokens for this model. |
| `cacheCreationInputTokens` | `int` | Cache creation tokens for this model. |
| `webSearchRequests` | `int` | Web search requests made by this model. |
| `thinkingTokens` | `int` | Thinking tokens generated by this model, already counted in `outputTokens`. Absent until a turn runs on a Claude Code version that records it, and not declared on the TypedDict, so read it with `.get()`. Requires Python Agent SDK 0.2.150 or later, whose bundled CLI records it. |
| `costUSD` | `float` | Estimated cost in USD for this model, computed client-side. See [Track cost and usage](/docs/en/agent-sdk/cost-tracking) for billing caveats. |
| `contextWindow` | `int` | Context window size for this model. |
| `maxOutputTokens` | `int` | Maximum output token limit for this model. |
| `canonicalModel` | `str` | Canonical model ID used for the pricing lookup. May differ from the raw model string the entry is keyed by, such as a provider-specific ID or alias. Not always present. |
| `provider` | `str` | API provider that served this model, such as `firstParty`, `bedrock`, `vertex`, `foundry`, `anthropicAws`, `mantle`, or `gateway`. Not always present. |
| `costBasis` | `str` | Price table that priced this model's latest request: `list` for list price, `managed` for a [`modelPricing`](/docs/en/settings-reference#modelpricing) table, or `unknown` when neither matched the model ID. Not always present, and not declared on the TypedDict, so read it with `.get()`. Requires Claude Code v2.1.246 or later. |


### `StreamEvent`

Stream event for partial message updates during streaming. Only received when `include_partial_messages=True` in `ClaudeAgentOptions`. Import via `from claude_agent_sdk.types import StreamEvent`.

```python theme={null}
@dataclass
class StreamEvent:
    uuid: str
    session_id: str
    event: dict[str, Any]  # The raw Claude API stream event
    parent_tool_use_id: str | None = None
```

| Field | Type | Description |
| :- | :- | :- |
| `uuid` | `str` | Unique identifier for this event |
| `session_id` | `str` | Session identifier |
| `event` | `dict[str, Any]` | The raw Claude API stream event data |
| `parent_tool_use_id` | `str \| None` | Always `None`. Stream events are emitted for the main session only. For subagent attribution, use complete messages such as [`AssistantMessage`](#assistantmessage) |

