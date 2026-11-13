### `SDKMessage`

Union type of all possible messages returned by the query.

```typescript theme={null}
type SDKMessage =
  | SDKAssistantMessage
  | SDKUserMessage
  | SDKUserMessageReplay
  | SDKResultMessage
  | SDKSystemMessage
  | SDKPartialAssistantMessage
  | SDKCompactBoundaryMessage
  | SDKStatusMessage
  | SDKLocalCommandOutputMessage
  | SDKHookStartedMessage
  | SDKHookProgressMessage
  | SDKHookResponseMessage
  | SDKPluginInstallMessage
  | SDKToolProgressMessage
  | SDKAuthStatusMessage
  | SDKTaskNotificationMessage
  | SDKTaskStartedMessage
  | SDKTaskProgressMessage
  | SDKTaskUpdatedMessage
  | SDKBackgroundTasksChangedMessage
  | SDKThinkingTokensMessage
  | SDKSessionStateChangedMessage
  | SDKWorkerShuttingDownMessage
  | SDKCommandsChangedMessage
  | SDKNotificationMessage
  | SDKFilesPersistedEvent
  | SDKToolUseSummaryMessage
  | SDKMemoryRecallMessage
  | SDKRateLimitEvent
  | SDKElicitationCompleteMessage
  | SDKPermissionDeniedMessage
  | SDKPromptSuggestionMessage
  | SDKAPIRetryMessage
  | SDKMirrorErrorMessage
  | SDKInformationalMessage
  | SDKConversationResetMessage;
```


### `SDKAssistantMessage`

Assistant response message.

```typescript theme={null}
type SDKAssistantMessage = {
  type: "assistant";
  uuid: UUID;
  session_id: string;
  message: BetaMessage; // From Anthropic SDK
  parent_tool_use_id: string | null;
  error?: SDKAssistantMessageError;
  aborted?: true;
  agent_id?: string;
  timestamp?: string;
  context_usage?: SDKContextUsage;
  usage_report?: SDKUsageReport;
  user_message_uuid?: string;
  user_message_uuids?: string[];
  resume_reason?: string;
};
```

The `message` field is a [`BetaMessage`](https://platform.claude.com/docs/en/api/messages/create) from the Anthropic SDK. It includes fields like `id`, `content`, `model`, `stop_reason`, and `usage`.

`SDKAssistantMessageError` is one of: `'authentication_failed'`, `'oauth_org_not_allowed'`, `'account_on_hold'`, `'billing_error'`, `'rate_limit'`, `'overloaded'`, `'invalid_request'`, `'model_not_found'`, `'server_error'`, `'max_output_tokens'`, `'cloud_credential_error'`, or `'unknown'`. Four of these values mean more than their names say:

* `'model_not_found'`: the selected model doesn't exist or isn't available to your account or deployment
* `'overloaded'`: the API returned a 529 because the server is at capacity, as opposed to `'rate_limit'`, which is a 429 against your quota
* `'account_on_hold'`: [your account is on hold](/docs/en/errors#your-account-is-on-hold)
* `'cloud_credential_error'`: Claude Code couldn't obtain usable AWS or Google Cloud credentials on the machine it runs on, so no request reached the cloud provider. The usual cause is a cloud sign-in that expired or was never completed on that machine, though a briefly unreachable credential service reports the same value. See [Could not load AWS or Google Cloud credentials](/docs/en/errors#could-not-load-aws-or-google-cloud-credentials). Requires TypeScript Agent SDK v0.3.267 or later, which bundles Claude Code v2.1.267

`aborted` is `true` when an interrupt or abort truncated the assistant message before the stream completed: the message has no `stop_reason` and the content may end mid-word. The field is absent on normally completed messages. It requires Agent SDK v0.3.214 or later.

`agent_id` identifies the subagent that produced the message and is absent on main-thread messages. The value equals the `task_id` on that subagent's [`task_started`](#sdktaskstartedmessage) and other task events, and is unchanged when the subagent is [resumed](/docs/en/agent-sdk/subagents#resume-subagents). The field requires Agent SDK v0.3.292 or later.

Match a subagent's messages to its task events on `agent_id` rather than pairing a message's `parent_tool_use_id` with a task event's `tool_use_id`. When a tool call resumes the subagent, the task events carry that call's `tool_use_id`, while the messages keep the `parent_tool_use_id` of the tool call that first started the subagent, so the two no longer match.

Claude Code sets `user_message_uuid` and `user_message_uuids` on the turn's first assistant message, under the conditions in [`user_message_uuid`](#user_message_uuid). When the turn continues one that a restart interrupted, the assistant messages that carry those fields also carry [`resume_reason`](#resume_reason).

`timestamp` is the ISO 8601 time when the message's content finished generating on the process that produced it. The value comes from that machine's clock, so use it for display only and don't order messages by it. One API turn can produce several assistant messages that share a `message.id`, each with its own `timestamp`. When the field is absent, fall back to the time you received the message.

`context_usage` is a structured copy of the `/context` report, typed as [`SDKContextUsage`](#sdkcontextusage), and requires Agent SDK v0.3.232 or later. When you send `/context` as a prompt, Claude Code delivers the report as an assistant message whose `message.content` holds the markdown table, and attaches `context_usage` to that same message. Claude Code doesn't set the field on any other assistant message, and earlier versions deliver the `/context` table without it, so read the breakdown from the field when it's present and fall back to the markdown text when it isn't.

`usage_report` is a structured copy of the `/usage` report, typed as [`SDKUsageReport`](#sdkusagereport), and requires Agent SDK v0.3.273 or later. When you send `/usage` as a prompt, Claude Code delivers the report as an assistant message whose `message.content` holds the text. It attaches `usage_report` to that same message only when the session meets all of these conditions:

* The session authenticates with a claude.ai credential
* The credential shows a known plan type or carries the `user:profile` scope
* The account isn't on usage-based billing

A `claude setup-token` token passed as `CLAUDE_CODE_OAUTH_TOKEN` doesn't qualify by default, because it carries only the `user:inference` scope. Other sessions, such as API-key sessions, deliver the text without the field, and so do earlier versions. Read the report from the field when it's present and fall back to the text when it isn't.


### `SDKUserMessage`

User input message.

```typescript theme={null}
type SDKUserMessage = {
  type: "user";
  uuid?: UUID;
  session_id?: string;
  agent_id?: string;
  message: MessageParam; // From Anthropic SDK
  pasted_content?: MessageParam["content"][];
  parent_tool_use_id: string | null;
  isSynthetic?: boolean;
  shouldQuery?: boolean;
  client_composed?: true;
  tool_use_result?: unknown;
  priority?: "now" | "next" | "later";
  origin?: SDKMessageOrigin;
  inline_pastes?: string[];
};
```

Set `pasted_content` to send content the user pasted into your prompt UI rather than typed, one entry per paste, each a string or an array of content blocks. Claude Code appends each entry's text after the typed text, in order, and may wrap each paste in `<pasted_content>` tags. Blocks other than text are ignored, so send images and documents in `message.content`. Requires Agent SDK v0.3.277 or later.

Set `inline_pastes` to tell Claude Code which parts of `message.content` the user pasted rather than typed, one string per paste. The prompt text stays where the user put it. Claude Code may wrap each listed paste in `<pasted_content>` tags where it stands, so Claude can tell pasted material from the user's own words. Only pastes in the prompt's last text block are wrapped. Requires TypeScript Agent SDK v0.3.280 or later.

Each paste field has a size limit:

* `pasted_content`: if the entries plus the content blocks inside them number more than 1,000, Claude Code ignores the whole field.
* `inline_pastes`: Claude Code uses the first 100 entries that aren't blank and ignores the rest.

Set `shouldQuery`, `client_composed`, or `priority` to change how Claude Code handles a message you send:

* `shouldQuery`: set it to `false` to append the message to the transcript without triggering an assistant turn. The message is held and merged into the next user message that does trigger a turn. Use this to inject context, such as the output of a command you ran out of band, without spending a model call on it.
* `client_composed`: set it to `true` to have Claude Code deliver the message text as written. Claude Code then doesn't expand `@path` or [`@server:resource`](/docs/en/mcp#use-mcp-resources) mentions, and doesn't run text that starts with `/` as a command. While the [`verbatimPrompts`](#options) option is on, the SDK sets the field on every message. Requires TypeScript Agent SDK v0.3.280 or later and Claude Code v2.1.248 or later.
* `priority`: controls when a message you send during a running turn reaches Claude:
  * `'next'`, or no `priority` field: Claude reads the message in the same turn, as soon as the tool calls it is running finish. If the turn ends first, the message starts the next turn.
  * `'later'`: Claude Code holds the message until the turn ends and sends it as a new turn.
  * `'now'` with [`origin: { kind: "human" }`](#sdkmessageorigin): on Claude Code v2.1.286 or later, work that can continue in the background moves there, and Claude reads the message in the same turn. Work that can move includes shell commands, subagents, and MCP tool calls. On v2.1.287 or later it also includes WebFetch and WebSearch calls. When Claude is only writing a response, or the work it is running can't move, Claude Code interrupts the turn instead and Claude reads the message next.
  * `'now'` without that origin: Claude Code interrupts the turn and Claude reads the message next.

This message, sent while a turn is running, asks Claude to change course without losing a shell command that is still running:

```typescript theme={null}
const message: SDKUserMessage = {
  type: "user",
  message: { role: "user", content: "Skip the integration tests and summarize what you have so far" },
  parent_tool_use_id: null,
  priority: "now",
  origin: { kind: "human" },
};
```

A user message that a subagent produces, such as the `tool_result` for one of its own tool calls, carries `agent_id`. See [`SDKAssistantMessage`](#sdkassistantmessage), which defines the field and its version requirement.

On a message that carries a `tool_result` block, `tool_use_result` is the tool's structured output object rather than the text sent to the model. Its shape depends on the tool named by the matching `tool_use` block, so the field is typed `unknown`; the built-in shapes are listed under [Tool Output Types](#tool-output-types). These results need handling beyond their listed shape:

* The `Agent` tool: `tool_use_result` is [`AgentOutput`](#agent-2). Render from it rather than parsing the `tool_result` text. A `completed` result's `content` holds the subagent's report, or, for a subagent whose report goes through a `SubagentHandback` tool call, a short note about that hand-back in place of the report. In [auto mode](/docs/en/permission-modes#eliminate-prompts-with-auto-mode) on Claude Code v2.1.271 or later, every subagent that produces a `completed` result reports that way unless it is a [fork](/docs/en/sub-agents#fork-the-current-conversation), and Claude receives the report as a separate message from the subagent.
* A WebFetch or WebSearch call that Claude Code moved to the background to deliver a `'now'` message: the user message carrying that call's `tool_result` has `tool_use_result` set to `{ detachedToolCall: true }`. The call is still running, and Claude receives its result once it finishes. No second `tool_result` for that `tool_use_id` follows, so if your application draws a row for each tool call, mark this row as moved to the background when this message arrives. Requires Claude Code v2.1.287 or later.
* An MCP tool whose result contains `resource_link` blocks: `tool_use_result` is an object with a `resourceLinks` array of [`SDKMcpResourceLink`](#sdkmcpresourcelink) entries. Claude receives each link as a line of text in the `tool_result` block, so read `resourceLinks` to render the files the server returned instead of parsing that text. Claude Code omits `resourceLinks` when the result has no links and on results from subagents, keeps at most 50 links per result, and stops adding links once the array reaches 64 KiB of serialized JSON. `resourceLinks` requires Agent SDK v0.3.257 or later.
* An MCP tool that returns [`structuredContent`](#calltoolresult): `tool_use_result` is an object whose `structuredContent` member holds what the server sent and whose `content` member holds the [`McpOutput`](#mcpoutput) value. Results from subagents don't carry `structuredContent`.
* An MCP tool whose `structuredContent` serializes to more than 1,048,576 characters of JSON: Claude Code leaves `structuredContent` off `tool_use_result` and sets `structuredContentOmitted: true` in its place, so your application can tell a dropped object from a tool that sent none. The other members, such as `content` and `resourceLinks`, stay, and what Claude receives doesn't change. Claude Code v2.1.287 or later applies this cap. Two kinds of tool differ:
  * Tools from [in-process SDK servers](/docs/en/agent-sdk/custom-tools) are exempt and deliver the object whole.
  * A tool whose `tools/list` entry declares an [MCP Apps `ui://` resource](#mcpserverstatus) has a limit of 8,388,608 characters on Claude Code v2.1.295 or later, and versions before v2.1.295 exempt it.


### `SDKResultMessage`

Final result message.

```typescript theme={null}
type SDKResultMessage =
  | {
      type: "result";
      subtype: "success";
      uuid: UUID;
      session_id: string;
      duration_ms: number;
      duration_api_ms: number;
      is_error: boolean;
      api_error_status?: number | null;
      num_turns: number;
      result: string;
      stop_reason: string | null;
      ttft_ms?: number;
      ttft_stream_ms?: number;
      user_message_uuid?: string;
      user_message_uuids?: string[];
      resume_reason?: string;
      local_command?: string;
      request_sent_wall_ms?: number;
      first_content_frame_ms?: number;
      first_stream_post_ms?: number;
      first_stream_post_ack_ms?: number;
      first_stream_post_queue_wait_ms?: number;
      first_stream_post_queued_behind?: "durable_post" | "ephemeral_post" | "retry_backoff" | "hold" | "none";
      first_stream_post_wall_ms?: number;
      first_text_post_ms?: number;
      first_text_post_queue_wait_ms?: number;
      first_text_post_queued_behind?: "durable_post" | "ephemeral_post" | "retry_backoff" | "hold" | "none";
      first_text_post_wall_ms?: number;
      total_cost_usd: number;
      usage: NonNullableUsage;
      modelUsage: { [modelName: string]: ModelUsage };
      permission_denials: SDKPermissionDenial[];
      queued_turn_count?: number;
      structured_output?: unknown;
      deferred_tool_use?: { id: string; name: string; input: Record<string, unknown> };
      terminal_reason?: TerminalReason;
      result_index?: number;
      fast_mode_state?: FastModeState;
      fast_mode_disabled_reason?: FastModeDisabledReason;
      origin?: SDKMessageOrigin;
    }
  | {
      type: "result";
      subtype:
        | "error_max_turns"
        | "error_during_execution"
        | "error_max_budget_usd"
        | "error_max_structured_output_retries";
      uuid: UUID;
      session_id: string;
      duration_ms: number;
      duration_api_ms: number;
      is_error: boolean;
      num_turns: number;
      stop_reason: string | null;
      total_cost_usd: number;
      usage: NonNullableUsage;
      modelUsage: { [modelName: string]: ModelUsage };
      permission_denials: SDKPermissionDenial[];
      queued_turn_count?: number;
      errors: string[];
      startup_failure_reason?: SDKStartupFailureReason;
      user_message_uuid?: string;
      user_message_uuids?: string[];
      resume_reason?: string;
      terminal_reason?: TerminalReason;
      result_index?: number;
      fast_mode_state?: FastModeState;
      fast_mode_disabled_reason?: FastModeDisabledReason;
      origin?: SDKMessageOrigin;
    };
```

Several fields on the result carry diagnostic detail beyond `subtype`:

* `api_error_status`: the HTTP status code of the API error that terminated the conversation. Absent or `null` when the turn ended without an API error.
* `ttft_ms`: time to first token in milliseconds, measured when the first complete assistant message arrives. Present on the success arm only.
* `ttft_stream_ms`: time in milliseconds until the first `message_start` stream event, when the response stream opens. Lower than `ttft_ms`; the gap between the two is time spent streaming the first message. Present on the success arm only.
* `user_message_uuid`: the `uuid` of the message you sent that this turn answered. See [`user_message_uuid`](#user_message_uuid) for which results carry it.
* `user_message_uuids`: the `uuid`s of every message you sent that Claude Code answered in this turn. See [`user_message_uuids`](#user_message_uuids).
* `resume_reason`: why this turn continues one that a restart interrupted. Present on both arms. See [`resume_reason`](#resume_reason).
* `local_command`: the name of the command the turn dispatched, on the success result of a turn that a command completed without entering the agent loop, such as `/compact`. The name is folded to lowercase letters and underscores, so `/reload-plugins` reports `reload_plugins`. A command that an MCP server provides, and the built-in `/mcp`, report `mcp`. A command you defined yourself reports `custom`. The arguments are never included. Absent on every turn that entered the agent loop and on sends that ran no command. Requires Agent SDK v0.3.268 or later.
* `request_sent_wall_ms`: epoch milliseconds at which Claude Code dispatched the API request, for joins against server-side timestamps. Present only together with [`user_message_uuid`](#user_message_uuid), on a success result with `is_error` false whose turn sent an API request.
* `first_content_frame_ms`: time in milliseconds until the first `content_block_start` or `content_block_delta` stream event, counting thinking blocks as content. Present on the success arm only, when `is_error` is false. Requires Agent SDK v0.3.260 or later.
* `first_stream_post_ms`, `first_stream_post_ack_ms`, `first_stream_post_wall_ms`: timings for uploading the turn's first stream event. Claude Code records them only in sessions it streams to claude.ai, such as [cloud sessions](/docs/en/claude-code-on-the-web), and the results `query()` yields don't carry them. Requires Agent SDK v0.3.260 or later.
* `usage`: main agent loop only. Excludes subagent and auxiliary model calls, and is per-turn in streaming-input sessions. Prefer `modelUsage` for token/cost accounting.
* `modelUsage`: per-model totals for every model call made through the query pipeline during this `query()` call, including the main loop, subagents, and internal calls such as compaction and Workflow agents. Helper calls outside that pipeline, such as the permission classifier and token-counting requests, are excluded. A call that resumes a session also counts the [per-model totals restored from the session's earlier calls](/docs/en/agent-sdk/cost-tracking#accumulate-costs-across-multiple-calls). In streaming-input sessions the totals are cumulative across turns, so read the latest result rather than summing across results. See [Track costs in streaming input mode](/docs/en/agent-sdk/cost-tracking#track-costs-in-streaming-input-mode) for resets and [Recover totals after a session crash](/docs/en/agent-sdk/cost-tracking#recover-totals-after-a-session-crash) for zeroed results.
* `total_cost_usd`: cumulative estimated cost in USD, covering the same calls as `modelUsage` and reset at the same points. A call that resumes a session also counts the [totals restored from the session's earlier calls](/docs/en/agent-sdk/cost-tracking#accumulate-costs-across-multiple-calls). It is an estimate, not a billing statement. See [Track cost and usage](/docs/en/agent-sdk/cost-tracking) for accuracy caveats.
* `queued_turn_count`: the number of messages you sent with `origin: { kind: "human" }` that are still waiting when Claude Code produced the result. See [`queued_turn_count`](#queued_turn_count) for what `0` and an absent field tell you.
* `result_index`: where this result falls in the run's delivery order, counting from 0 across every result the process writes. Present on both arms. A result whose write fails still consumes its number, so a gap in the sequence means a result was lost. Requires Agent SDK v0.3.268 or later.
* `startup_failure_reason`: why Claude Code refused to start, on the `error_during_execution` result it writes before exiting on a known startup failure. See [`startup_failure_reason`](#startup_failure_reason) for the values and which failures carry it. Requires Agent SDK v0.3.274 or later.
* `terminal_reason`: why the loop ended. One of `"completed"`, `"max_turns"`, `"tool_deferred"`, `"aborted_streaming"`, `"aborted_tools"`, `"hook_stopped"`, `"stop_hook_prevented"`, `"background_requested"`, `"blocking_limit"`, `"rapid_refill_breaker"`, `"prompt_too_long"`, `"image_error"`, `"model_error"`, `"api_error"`, `"malformed_tool_use_exhausted"`, `"budget_exhausted"`, `"structured_output_retry_exhausted"`, `"tool_deferred_unavailable"`, or `"turn_setup_failed"`.
* `fast_mode_state`: one of `"on"`, `"off"`, or `"cooldown"`.
* `fast_mode_disabled_reason`: why [fast mode](/docs/en/fast-mode) isn't available right now. Absent when nothing blocks fast mode, though a request may still run at standard speed. During the cooldown after a fast mode rate limit, Claude Code reports `fast_mode_state: "cooldown"` with no reason code and re-enables fast mode when the cooldown expires. Requires Claude Code v2.1.219 or later.

Use the reason code to explain why fast mode is off in your own UI instead of re-deriving availability. Each code names the check that blocked fast mode:

| Reason code | Meaning |
| - | - |
| `free` | The account doesn't have the paid subscription or usage credits fast mode requires |
| `preference` | The organization has disabled fast mode |
| `extra_usage_disabled` | Usage credits are turned off for the account |
| `network_error` | The [availability check](/docs/en/fast-mode#use-fast-mode-behind-proxies-and-llm-gateways) couldn't reach `api.anthropic.com` |
| `unknown` | Claude Code couldn't determine availability |
| `not_first_party` | The session uses a provider other than the Anthropic API |
| `disabled_by_env` | [`CLAUDE_CODE_DISABLE_FAST_MODE`](/docs/en/env-vars) is set |
| `model_not_allowed` | The fast mode Opus model isn't in the organization's [`availableModels`](/docs/en/model-config#restrict-model-selection) allowlist |
| `sdk_opt_in_required` | The session hasn't opted in to fast mode: pass `fastMode: true` in the [`settings`](#options) option or through [`applyFlagSettings()`](#applyflagsettings) |
| `pending` | The availability check hasn't completed yet |

The same pair of fields appears on [`SDKSystemMessage`](#sdksystemmessage) and on the [`SDKControlInitializeResponse`](#sdkcontrolinitializeresponse), so you can read the fast mode state before the first turn.

The `origin` field forwards the [`SDKMessageOrigin`](#sdkmessageorigin) of the user message that triggered this result. Results that carry `origin: { kind: "task-notification" }` include:

* **Synthetic follow-up turns**: when the SDK injects a synthetic follow-up turn, such as for a finished background task, the resulting `SDKResultMessage` carries this kind
* **Fired scheduled tasks and messages from other sessions**: cloud scheduled tasks whose trigger fired and server-verified messages from your other sessions arrive with this kind too, each with the `subkind` described in [Task-notification subkinds](#task-notification-subkinds)

Check `kind` to distinguish results that answer your prompt from injected follow-ups before routing or suppressing them. If your application [declares scheduled runs](#declare-a-scheduled-run), their results carry `kind: "task-notification"` too, so don't suppress on `kind` alone.

When several background-task completions are queued together, Claude Code can answer them in one turn rather than one turn each. Each completion still produces its own result with this origin. All but the last of the completions Claude Code answers together produce empty results with `num_turns: 0`, in order, and the last one's result carries the turn that answers them all.

The field is absent for results emitted before any user turn, such as startup errors.

When a `PreToolUse` hook returns `permissionDecision: "defer"`, the result has `stop_reason: "tool_deferred"` and `deferred_tool_use` carries the pending tool's `id`, `name`, and `input`. Read this field to surface the request in your own UI, then resume with the same `session_id` to continue. See [Defer a tool call for later](/docs/en/hooks#defer-a-tool-call-for-later) for the full round trip.

#### `user_message_uuid`

The `uuid` of the [`SDKUserMessage`](#sdkusermessage) the turn is answering, echoed so you can match Claude Code's reply to the message you sent. Claude Code echoes a `uuid` only if you set one on the message. The field is optional on `SDKUserMessage`, and a string prompt passed to `query()` carries none.

Which of your messages a turn answers depends on how the turn started:

* **A regular message you sent**, meaning one without `isSynthetic: true`: the turn answers that message for its whole run. When you send several messages close together, Claude Code can merge them into one turn, and the field then carries only the last message's `uuid`. To match the reply to any of the merged messages, use [`user_message_uuids`](#user_message_uuids).
* **A message you sent with `isSynthetic: true`**: the turn answers that message at first. If Claude Code picks up a regular message of yours between tool calls, the turn answers the picked-up message from then on. Echoing a synthetic message's `uuid` requires Agent SDK v0.3.265 or later; earlier versions echo nothing on synthetic turns.
* **The prompt Claude Code generates to continue an interrupted turn under [`CLAUDE_CODE_RESUME_INTERRUPTED_TURN`](/docs/en/env-vars)**: when the interrupted turn's last prompt is a regular message you sent, whether it opened the turn or Claude Code picked it up during the turn, the continued turn answers that message at first. [`resume_reason`](#resume_reason) tells the continued turn's frames from the interrupted attempt's. When the last prompt isn't a regular message of yours, the continued turn answers no message of yours at first. If Claude Code picks up a regular message of yours between tool calls, the turn answers the picked-up message from then on. Echoing the interrupted turn's prompt requires Agent SDK v0.3.268 or later.
* **Any other prompt Claude Code generated itself**: the turn answers no message of yours at first and its frames carry no echo. If Claude Code picks up a regular message of yours between tool calls, the turn answers that message from then on. The pickup echo requires Agent SDK v0.3.265 or later; earlier versions echo nothing on these turns.

Claude Code echoes the answered message's `uuid` on three kinds of frame:

* **The result**: every result of a turn that answered a message you sent. Every such result carries it on Agent SDK v0.3.265 or later. Before v0.3.265, the success result of a turn that a regular message started lacked it when the turn sent no API request or ended with a deferred tool call. Before v0.3.246, error results lacked it too, and before v0.3.216 every result did.
* **The turn's first reply**: the first [assistant message](#sdkassistantmessage), and with `includePartialMessages` also the first [stream event](#sdkpartialassistantmessage) whose `event.type` isn't `ping`, so you can bind the reply before the result arrives. The first-reply echo requires Agent SDK v0.3.246 or later. Before v0.3.269, with `includePartialMessages`, Claude Code set it on that first stream event only, or on the first assistant message when the turn streamed nothing. When the message the turn is answering changes mid-turn, the first reply after the change carries the field too, on Agent SDK v0.3.265 or later; earlier versions set it on one reply frame per turn.
* **Every [`thinking_tokens`](#sdkthinkingtokensmessage) frame of the turn**: so you can attribute thinking progress to the message you sent without waiting for the turn's first reply. Requires Agent SDK v0.3.260 or later.

Claude Code omits the field in these cases:

* Reply frames other than those first replies
* Subagent frames
* Turns that answer no message of yours, or answer a message you sent without a `uuid`
* Results that answer no message you sent, such as the zeroed result after a crashed worker process

#### `user_message_uuids`

The `uuid`s of every message you sent that Claude Code answered in this turn. When you send several messages close together, Claude Code can merge them into one turn, and `user_message_uuid` then names only the last of them. To match the reply to any of the merged messages, look for that message's `uuid` anywhere in this list. Requires Agent SDK v0.3.259 or later.

Claude Code sets the list together with `user_message_uuid` on each reply frame that carries that field and on the result. For the full set of turn frames that echo the answered message's `uuid`, and the version each requires, see [`user_message_uuid`](#user_message_uuid). The list always contains `user_message_uuid` and holds at most 64 entries.

When Claude Code picks up a regular message you sent while a turn was running, it adds that message's `uuid` to the result's list.

When a first reply or result carries `user_message_uuid` without the list, it came from an earlier Claude Code version, so fall back to the single field.

#### `resume_reason`

Why this turn continues one that a restart interrupted. Claude Code sets this field on a turn that continues an interrupted one under [`CLAUDE_CODE_RESUME_INTERRUPTED_TURN`](/docs/en/env-vars), so you can tell the continued turn's reply and result from the interrupted attempt's. Requires Agent SDK v0.3.268 or later.

Claude Code sets the field on two kinds of frame:

* **The continued turn's result**: on the success and error arms alike, whether or not the result carries `user_message_uuid`.
* **The continued turn's reply frames**: those that carry [`user_message_uuid`](#user_message_uuid).

The value is a short lowercase token, such as `interrupted_turn`.

#### `queued_turn_count`

The number of messages you sent with [`origin: { kind: "human" }`](#sdkmessageorigin) that are still waiting in the command queue when Claude Code produced the result. Requires Agent SDK v0.3.242 or later.

What `0` and an absent field tell you:

* **`0`**: Claude Code doesn't count messages you sent without that `origin`, and doesn't count task notifications, so a turn can still follow.
* **Absent**: the final result that Claude Code emits after a crash or fatal startup error omits the field, and [may carry zeroed totals](/docs/en/agent-sdk/cost-tracking#recover-totals-after-a-session-crash).

#### `startup_failure_reason`

Why Claude Code refused to start, so your application can offer the fix instead of a retry. Claude Code sets it on the `error_during_execution` result it writes before exiting on a known startup failure. That result carries zeroed totals, and its `errors` array carries the same text as stderr. The field is absent on every other result. Requires Agent SDK v0.3.274 or later.

Set `CLAUDE_CODE_STARTUP_FAILURE_RESULTS` to `1` in [`env`](#options) to receive this result for every `SDKStartupFailureReason` value. Without that variable, Claude Code writes the result only for these failures, and the rest end with stderr output, a non-zero exit, and no result message:

* A resume that Claude Code stops because it [can't return the session to its worktree](/docs/en/worktrees#the-session-resumes-outside-its-worktree), with `worktree_unverified` or `worktree_resume_refused`. That section says which error carries which value.
* A refused [`continue`](#options) of a conversation that a background session holds, with `session_held_by_background`. For a refused [`resume`](#options) of such a conversation, Claude Code writes the result only when the variable is set.

```typescript theme={null}
type SDKStartupFailureReason =
  | "org_pin_api_key_conflict"
  | "provider_not_allowed"
  | "org_verify_failed"
  | "org_pin_mismatch"
  | "managed_settings_invalid"
  | "remote_settings_required_unavailable"
  | "gateway_signin_required"
  | "gateway_access_denied"
  | "proxy_invalid"
  | "temp_dir_unusable"
  | "cwd_unavailable"
  | "shell_tool_missing"
  | "session_held_by_background"
  | "worktree_resume_refused"
  | "worktree_unverified"
  | "cli_version_too_old"
  | "bypass_root"
  | "org_config_required_unavailable"
  | "org_config_refused";
```

Each value names one refusal:

| Value | What stopped the session |
| :- | :- |
| `org_pin_api_key_conflict` | Managed settings [require a first-party or Cloud gateway sign-in](/docs/en/authentication#restrict-login-to-your-organization), and an Anthropic API key, auth token, or `apiKeyHelper` is configured instead |
| `provider_not_allowed` | Managed settings [list the API providers this machine may use](/docs/en/settings-reference#allowedproviders), and the session is set up for a provider that isn't listed, or for an endpoint the settings don't pin. Requires Claude Code v2.1.285 or later |
| `org_verify_failed` | The sign-in's organization couldn't be verified against the pin, for example because of a network failure or a revoked token |
| `org_pin_mismatch` | The sign-in belongs to an organization the pin doesn't allow |
| `managed_settings_invalid` | Managed policy settings couldn't be read, the pin names no organization, or [managed model restrictions](/docs/en/errors#managed-settings-block-the-default-model) leave no permitted model for the Default option |
| `remote_settings_required_unavailable` | Managed settings that the organization requires couldn't be loaded |
| `gateway_signin_required` | The [Cloud gateway](/docs/en/claude-apps-gateway) ended this sign-in |
| `gateway_access_denied` | The managed settings request to the Cloud gateway came back with a 403, which the gateway's [troubleshooting table](/docs/en/claude-apps-gateway-deploy#troubleshooting) covers |
| `proxy_invalid` | A proxy setting isn't a complete URL |
| `temp_dir_unusable` | The per-user temporary directory is unsafe or couldn't be created |
| `cwd_unavailable` | The working directory was deleted, moved, or can't be read |
| `shell_tool_missing` | On Windows, no shell tool is available: Git Bash is missing, and PowerShell is missing or turned off with `CLAUDE_CODE_USE_POWERSHELL_TOOL` |
| `session_held_by_background` | The conversation to resume or continue is running as a [background session](/docs/en/agent-view) |
| `worktree_resume_refused` | The session's worktree failed its safety checks, or the resume was launched from inside it. `errors` says whether running the same resume again continues without the worktree |
| `worktree_unverified` | The session's worktree couldn't be verified right now, and retrying may succeed |
| `cli_version_too_old` | This Claude Code version is below the minimum Anthropic requires |
| `bypass_root` | Bypass permissions mode was requested while running as root |
| `org_config_required_unavailable` | The session needs the organization's policies and managed settings before it can start, and they couldn't be loaded, for example because of a network failure or an Anthropic server error. Requires Agent SDK v0.3.293 or later |
| `org_config_refused` | Anthropic refused to provide the organization's policies and managed settings for this sign-in, for example because the sign-in expired or was revoked, or the organization doesn't allow Claude Code for this account. Requires Agent SDK v0.3.293 or later |


### `SDKSystemMessage`

System initialization message.

```typescript theme={null}
type SDKSystemMessage = {
  type: "system";
  subtype: "init";
  uuid: UUID;
  session_id: string;
  agents?: string[];
  apiKeySource: ApiKeySource;
  betas?: string[];
  claude_code_version: string;
  cwd: string;
  tools: string[];
  mcp_servers: {
    name: string;
    status: string;
    source?: string;
  }[];
  model: string;
  permissionMode: PermissionMode;
  slash_commands: string[];
  terminal_slash_commands?: string[];
  output_style: string;
  skills: string[];
  plugins: { name: string; path: string }[];
  plugin_errors?: {
    plugin: string;
    type: string;
    message: string;
    path?: string;
  }[];
  fast_mode_state?: FastModeState;
  fast_mode_disabled_reason?: FastModeDisabledReason;
  effort?: "low" | "medium" | "high" | "xhigh" | "max" | null;
  capabilities?: string[];
};
```

`fast_mode_state` reports the session's [fast mode](/docs/en/fast-mode) state. When something blocks fast mode, `fast_mode_disabled_reason` names the check that blocked it; the field requires Claude Code v2.1.219 or later. For the reason codes and their meanings, see [`fast_mode_disabled_reason`](#sdkresultmessage) on the result message.

`terminal_slash_commands` names the entries in `slash_commands` whose interface is bound to the local terminal, such as `exit`. You can send them like any other entry in `slash_commands`; the field exists so a remote or mobile client can hide them from its command menus. The field is present only when non-empty, and requires Agent SDK v0.3.229 or later.

* `source` on each `mcp_servers` entry: where the server's definition came from, with the same values as [`McpServerStatus`](#mcpserverstatus)'s `source`. Requires Agent SDK v0.3.274 or later.
* `effort`: the [effort level](/docs/en/model-config#adjust-effort-level) Claude Code sends on the session's next request, or `null` when it sends none. Claude Code sets the field only on the init message it sends to [Remote Control](/docs/en/remote-control) clients, and omits it from the init message your application reads. Requires Agent SDK v0.3.234 or later.

The `capabilities` array names the protocol behaviors this CLI implements, so you can feature-detect instead of comparing `claude_code_version` strings. It is an open set: ignore values you don't recognize, and check for the specific capability whose behavior you rely on. The field requires Claude Code v2.1.205 or later and is absent on earlier CLIs.

| Capability | Meaning |
| - | - |
| `interrupt_receipt_v1` | [`interrupt()`](#query-object) resolves with an [`SDKControlInterruptResponse`](#sdkcontrolinterruptresponse) receipt listing the messages that were pending when the interrupt arrived |
| `interrupt_cancel_queued_v1` | The `interrupt` control request honors `cancel_queued: true`, cancelling the messages the receipt would otherwise list under `still_queued` and listing them under `cancelled` instead. See [`SDKControlInterruptResponse`](#sdkcontrolinterruptresponse). Requires Claude Code v2.1.219 or later |
| `sdk_mcp_manifests` | The `initialize` control request accepts `sdkMcpServerManifests`, MCP handshake results captured from your in-process [SDK MCP servers](/docs/en/agent-sdk/custom-tools). Claude Code advertises this capability in v2.1.286 or later |
| `sdk_mcp_tools_list_changed` | A `tools/list_changed` notification from an [SDK MCP server](/docs/en/agent-sdk/custom-tools) makes Claude Code list that server's tools again, so a tool the server adds mid-session reaches Claude. Claude Code advertises this capability in v2.1.286 or later |

The `plugin_errors` array lists plugin load failures. An entry describes either a plugin that didn't load and is absent from `plugins`, or a plugin that loaded without one of its parts, such as its hooks file. The key is omitted when nothing failed. `SDKSystemMessage` declares `plugin_errors` in Agent SDK v0.3.283 or later.

When a directory or archive from your [`plugins` option](#options) itself fails to load, the entry's `plugin` field holds a positional tag such as `inline[0]` instead of a plugin name. This happens, for example, when the path doesn't exist or the manifest is invalid. Match such an entry to your option by its `path` field.

The table below lists the fields of each `plugin_errors` entry.

| Field | Type | Description |
| - | - | - |
| `plugin` | `string` | The failing plugin's ID, or a positional tag such as `inline[0]` when the plugin directory or archive itself failed to load |
| `type` | `string` | Error category from an open set, such as `path-not-found` or `manifest-validation-error`. Treat a value you don't recognize as a generic failure |
| `message` | `string` | Display text describing the failure |
| `path` | `string` | Present only when the plugin directory or archive itself failed to load. Its absolute path, with a relative path from your `plugins` option resolved against the [`cwd`](#options) option |


### `SDKPartialAssistantMessage`

Streaming partial message (only when `includePartialMessages` is true).

The `parent_tool_use_id` field is always `null`: stream events are emitted for the main session only. For subagent attribution, use complete messages, which carry [`agent_id`](#sdkassistantmessage) and `parent_tool_use_id`, or enable [`forwardSubagentText`](#options) to receive subagent text and thinking as complete messages.

```typescript theme={null}
type SDKPartialAssistantMessage = {
  type: "stream_event";
  event: BetaRawMessageStreamEvent; // From Anthropic SDK
  parent_tool_use_id: string | null;
  uuid: UUID;
  session_id: string;
  ttft_ms?: number; // Time to first token in ms, present only on message_start events
  user_message_uuid?: string;
  user_message_uuids?: string[];
  resume_reason?: string;
};
```

Claude Code sets `user_message_uuid` and `user_message_uuids` on the turn's first non-ping stream event, and again when the message that the turn is answering changes, under the conditions in [`user_message_uuid`](#user_message_uuid). When the turn continues one that a restart interrupted, the stream events that carry those fields also carry [`resume_reason`](#resume_reason).


### `SDKCompactBoundaryMessage`

Message indicating a conversation compaction boundary.

```typescript theme={null}
type SDKCompactBoundaryMessage = {
  type: "system";
  subtype: "compact_boundary";
  uuid: UUID;
  session_id: string;
  compact_metadata: {
    trigger: "manual" | "auto";
    pre_tokens: number;
  };
};
```

