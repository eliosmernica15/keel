---

# Area 7c — Agent SDK Streaming Output Protocol (`includePartialMessages` / `include_partial_messages`)

**Subject:** Claude Code CLI v2.1.306 on Windows 11 Pro (win32-x64) + Claude Agent SDK (TypeScript / Python)
**Primary page under study:** https://code.claude.com/docs/en/agent-sdk/streaming-output.md (fetched 2026-10-21 as plain markdown, 14,456 bytes, HTTP 200)
**Implementation model reference:** Claude Opus 5.5
**Compliance:** No decompilation, disassembly, JS-source extraction, source-map dumping, binary modification, or credential/keychain/licence access. Method = public docs at `code.claude.com/docs` + `platform.claude.com/docs`, plus black-box observation of the published CLI's own `--output-format stream-json` surface. See `agent-reference-shots/TERMS-NOTES.md`.

**Environment caveat (applies to every OBSERVED-CLI claim below):** this host runs Claude Code 2.1.306 against a **custom `ANTHROPIC_BASE_URL`** serving `minimax/minimax-m3.1-flash:free`, not `api.anthropic.com`. Subscription-gated Anthropic behaviour is therefore **OBSERVED-DOC only**. The observed model is a third-party gateway model, so observed token shapes, provider fields, and timings are *not* representative of Anthropic-API behaviour.

**Page thinness assessment:** the primary page is **not thin**. It is a focused, ~330-line protocol page with a normative event-type table, an explicit message-ordering diagram, two complete code samples per section (Python + TypeScript), a cut-stream failure-mode section with version floors, and a known-limitations section. It specifies *event types* and *ordering* in detail, but it does **not** specify the field-level shape of the wrapper object in prose — that lives on the two SDK reference pages (`/agent-sdk/typescript`, `/agent-sdk/python`), which this section also draws on and cites. The raw event payload schema is inherited from the Claude API streaming reference (`platform.claude.com/docs/en/build-with-claude/streaming`), also cited.

---

## 7c.1 Executive summary

The Agent SDK's streaming-output surface is a **two-layer protocol** that a reimplementer can adopt wholesale:

**Layer 1 — a thin, uniform wrapper envelope.** Every streamed item is one of a fixed set of *message* objects, each discriminated by a `type` string. Partial (token-level) events arrive as a single message type whose `event` field holds a **raw, provider-level streaming event** verbatim. The SDK does not translate, reshape, or buffer it.

**Layer 2 — the raw provider stream itself.** Six event names carry the payload: `message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop`, plus `ping` and `error`. Content-block deltas are themselves typed (`text_delta`, `input_json_delta`, `thinking_delta`, `signature_delta`), so a consumer must switch on a discriminator rather than assume a string.

The **critical, non-obvious contract** is the interleaving rule, which the page states exactly:

> "Claude Code emits an `AssistantMessage` as each non-empty content block completes, so a response with a text block and a tool call yields two `AssistantMessage` objects."

> "With partial messages enabled, each `AssistantMessage` arrives **before** that block's `content_block_stop` event"

So the stream is **not** "deltas then a final assembled message" — it is *interleaved*: raw deltas for block 0, then the assembled message for block 0, *then* the block's `content_block_stop`, then block 1's deltas, and so on. A consumer that buffers deltas and only renders on `content_block_stop` will render late; a consumer that renders the assembled message *and* the deltas will double-render unless it reconciles them.

Three further points that a naive implementation gets wrong:

1. **Partial messages are opt-in and off by default.** `include_partial_messages` (Python) / `includePartialMessages` (TypeScript) default to `false`. With the default, you get complete messages only; the `StreamEvent` type never appears.
2. **The SDK does not accumulate for you.** "Both contain raw Claude API events, not accumulated text. You need to extract and accumulate text deltas yourself." The SDK is a pass-through, not a convenience layer.
3. **Subagent token deltas are never forwarded.** `parent_tool_use_id` is *always* `None` (Python) / `null` (TypeScript) on stream events. Subagent attribution requires the complete-message path.

A **fourth** point is a well-documented failure mode rather than a feature: a **cut stream** (interrupt, dropped connection) still delivers `message_stop` for the message, and a cut text/thinking block still gets its `content_block_stop` — but **a cut tool call does not**. So "`message_stop` arrived while a tool block is still open" is the documented signal that a tool call's input is incomplete. The page even names the historical bug and the version floors that fix it.

**Clean-room verdict:** this is one of the most implementable contracts in the product, because it is *pure data*. An independent implementation needs no proprietary code — only a documented event vocabulary, a strict ordering rule, and a discriminated-union envelope. The one genuinely hard part is the ordering rule, which the reference product itself had to fix twice.

---

## 7c.2 Classification key

- **OBSERVED-DOC** — stated in the cited public Anthropic doc; exact sentences quoted.
- **OBSERVED-CLI** — I ran the published CLI on this host; exact command and output recorded.
- **INFERRED** — my conclusion, with the reasoning stated.
- **UNKNOWN** — the available evidence cannot establish it.

---

## 7c.3 Findings

### S1 — Partial streaming is opt-in; the option name differs per SDK and defaults to `false`

**Status: OBSERVED-DOC**

Primary page, section **"Enable streaming output"**:

> "To enable streaming, set `include_partial_messages` (Python) or `includePartialMessages` (TypeScript) to `true` in your options. This causes the SDK to yield `StreamEvent` messages containing raw API events as they arrive, in addition to the usual `AssistantMessage` and `ResultMessage`."

Corroborated by the two SDK reference pages. TypeScript reference (`/docs/en/agent-sdk/typescript`), **Options** table:

> "| `includePartialMessages` | `boolean` | `false` | Include partial message events |"

Python reference (`/docs/en/agent-sdk/python`), **Options** table:

> "| `include_partial_messages` | `bool` | `False` | Include partial message streaming events. When enabled, [`StreamEvent`](#streamevent) messages are yielded |"

And in the Python `ClaudeAgentOptions` dataclass literal:

> `include_partial_messages: bool = False`

**Clean-room opportunity:** expose a single boolean, `includePartialMessages` (TS) / `include_partial_messages` (Python), defaulting to `false`, and gate the partial-message message type behind it. The idiomatic implementation is a *push filter at the transport boundary*: the agent loop already receives raw provider events; when the flag is off, drop them; when on, wrap each one in the envelope and emit it. This keeps the default path allocation-free and means partial streaming is purely additive to the core loop. Note the deliberate asymmetry: the option is *snake_case* in Python and *camelCase* in TypeScript, matching each language's convention — an independent implementation should mirror that rather than impose one name on both.

---

### S2 — The SDK's consumption recipe is a three-level nested type check

**Status: OBSERVED-DOC**

Primary page, section **"Enable streaming output"** — the page spells out the algorithm in prose before showing it in code:

> "1. Check each message's type to distinguish `StreamEvent` from other message types
> 2. For `StreamEvent`, extract the `event` field and check its `type`
> 3. Look for `content_block_delta` events where `delta.type` is `text_delta`, which contain the actual text chunks"

> "The example below enables streaming and prints text chunks as they arrive. Notice the nested type checks: first for `StreamEvent`, then for `content_block_delta`, then for `text_delta`:"

The TypeScript form of that check, verbatim from the page:

```typescript
for await (const message of query({
  prompt: "List the files in my project",
  options: {
    includePartialMessages: true,
    allowedTools: ["Bash", "Read"]
  }
})) {
  if (message.type === "stream_event") {
    const event = message.event;
    if (event.type === "content_block_delta") {
      if (event.delta.type === "text_delta") {
        process.stdout.write(event.delta.text);
      }
    }
  }
}
```

The Python form, verbatim:

```python
async for message in query(prompt="List the files in my project", options=options):
    if isinstance(message, StreamEvent):
        event = message.event
        if event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                print(delta.get("text", ""), end="", flush=True)
```

**Clean-room opportunity:** the observable contract is a **three-level discriminated union** — envelope type → provider event type → delta type. The idiomatic implementation in a typed language is a nested `switch`/`match` on literal discriminators, which gives the compiler exhaustiveness checking for free; in a dynamically-typed language, a dispatch table keyed on `(event.type, delta.type)`. Crucially, the *inner* level is a **string** in Python (`event.get("type")`) but a **typed literal** in TypeScript (`event.type === "content_block_delta"`), so a clean-room Python implementation must not assume the key is present — the reference docs consistently use `.get(...)` with a default for every nested lookup. Adopt defensive `.get()` access in dynamic languages, and treat a missing `delta` key as "not a text delta, skip".

---

### S3 — The wrapper type is named differently per SDK; both are one message type

**Status: OBSERVED-DOC**

Primary page, section **"StreamEvent reference"**:

> "When partial messages are enabled, you receive raw Claude API streaming events wrapped in an object. The type has different names in each SDK:
>
> * **Python**: [`StreamEvent`](/docs/en/agent-sdk/python#streamevent) (import from `claude_agent_sdk.types`)
> * **TypeScript**: [`SDKPartialAssistantMessage`](/docs/en/agent-sdk/typescript#sdkpartialassistantmessage) with `type: 'stream_event'`"

**"Both contain raw Claude API events, not accumulated text. You need to extract and accumulate text deltas yourself."**

**Clean-room opportunity:** pick one internal name per language and publish an **alias** so both idioms work (`StreamEvent` in Python, `SDKPartialAssistantMessage` in TypeScript, both with `type: "stream_event"`). The stable, cross-language contract is the **wire discriminant** `type: "stream_event"`, not the class name. A reimplementer should treat the discriminant as the compatibility surface and the class name as a convenience. Note the asymmetry in the reference product itself: Python exposes a runtime-checkable class (`isinstance(message, StreamEvent)`) while TypeScript requires a discriminant check (`message.type === "stream_event"`) — a clean-room design should give both languages the ergonomics the reference product gives each.

---

### S4 — Exact field shape of the wrapper: TypeScript `SDKPartialAssistantMessage`

**Status: OBSERVED-DOC**

TypeScript reference, section **`SDKPartialAssistantMessage`** — the complete type, verbatim:

```typescript
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

TypeScript reference, section **`SDKPartialAssistantMessage`** — the accompanying prose:

> "Streaming partial message (only when `includePartialMessages` is true)."

> "Claude Code sets `user_message_uuid` and `user_message_uuids` on the turn's first non-ping stream event, and again when the message that the turn is answering changes, under the conditions in [`user_message_uuid`](#user_message_uuid). When the turn continues one that a restart interrupted, the stream events that carry those fields also carry [`resume_reason`](#resume_reason)."

**Clean-room opportunity:** the field set is small and every field has a clear role: a discriminant (`type`), the payload (`event`), a **nesting key** (`parent_tool_use_id`), a **per-frame identity** (`uuid`), a **session identity** (`session_id`), and three **optional correlation/telemetry** fields. The `ttft_ms` comment is a load-bearing contract — "present only on `message_start` events" — so an implementation that stamps latency on every frame breaks a consumer's expectation that it reads it once. A clean-room implementation should emit `ttft_ms` **only** on the `message_start` frame, and should make `uuid` unique per frame so a consumer can deduplicate or trace a specific frame.

---

### S5 — Exact field shape of the wrapper: Python `StreamEvent`

**Status: OBSERVED-DOC**

Python reference, section **`StreamEvent`** — the complete dataclass, verbatim:

```python
@dataclass
class StreamEvent:
    uuid: str
    session_id: str
    event: dict[str, Any]  # The raw Claude API stream event
    parent_tool_use_id: str | None = None
```

Python reference, **`StreamEvent`** field table, verbatim:

> | Field | Type | Description |
> | :- | :- | :- |
> | `uuid` | `str` | Unique identifier for this event |
> | `session_id` | `str` | Session identifier |
> | `event` | `dict[str, Any]` | The raw Claude API stream event data |
> | `parent_tool_use_id` | `str \| None` | Always `None`. Stream events are emitted for the main session only. For subagent attribution, use complete messages such as [`AssistantMessage`](#assistantmessage) |

And the import path, from the section's opening line:

> "Stream event for partial message updates during streaming. Only received when `include_partial_messages=True` in `ClaudeAgentOptions`. Import via `from claude_agent_sdk.types import StreamEvent`."

**Clean-room opportunity:** the Python shape is a dataclass with **four** fields — three required, one defaulted. The type of `event` is `dict[str, Any]`, i.e. the raw event is deliberately **untyped** in the dynamic language. A clean-room Python implementation should mirror this: a frozen dataclass with `uuid: str`, `session_id: str`, `event: dict[str, Any]`, `parent_tool_use_id: str | None = None`, exported from a `types` module. The "untyped payload, typed envelope" split is the right design here — it is what lets the SDK forward a provider's *new* event types without an SDK release.

---

### S6 — Subagent token deltas are never forwarded; `parent_tool_use_id` is always null on stream events

**Status: OBSERVED-DOC**

Primary page, section **"StreamEvent reference"**:

> "The `parent_tool_use_id` field is always `None` in Python and `null` in TypeScript. Stream events are emitted for the main session only; token-level deltas from subagents aren't forwarded. To attribute output to a subagent, use complete messages, which carry `parent_tool_use_id`. See [Detect subagent invocation](/docs/en/agent-sdk/subagents#detect-subagent-invocation)."

TypeScript reference, section **`SDKPartialAssistantMessage`**, corroborating:

> "The `parent_tool_use_id` field is always `null`: stream events are emitted for the main session only. For subagent attribution, use complete messages, which carry [`agent_id`](#sdkassistantmessage) and `parent_tool_use_id`, or enable [`forwardSubagentText`](#options) to receive subagent text and thinking as complete messages."

**INFERRED:** the reference product makes a deliberate **two-tier** guarantee — token granularity for the main conversation only, message granularity for everything (including subagents). *Reasoning:* the field is documented as invariantly `null` rather than conditionally null, and the doc directs the reader to a *different message type* for subagent attribution. A "sometimes non-null" field would be unusable; an invariantly-null field is a clean contract. The `forwardSubagentText` option (TypeScript reference, **Options** table) confirms the design: subagent text is forwarded as *complete* messages, not as deltas.

**Clean-room opportunity:** adopt the same two-tier split. Reserve the nesting key on the envelope but document it as *always null for partial frames*; expose subagent content through the complete-message channel. This avoids a classic reimplementation trap — a consumer that tries to reconstruct a nested transcript from token deltas will find the subagent's output simply absent, with no error. A clean-room product should either mirror the documented split, or (if it wants to be better) forward subagent deltas under a *distinct* envelope type (`type: "stream_event"` with a populated `parent_tool_use_id`) so the two channels are never confused. Either way, the invariant must be documented, because a consumer written against one behaviour silently breaks on the other.

---

### S7 — `user_message_uuid` correlates a streamed turn back to the user's message; Python's `StreamEvent` omits it

**Status: OBSERVED-DOC**

Primary page, section **"StreamEvent reference"**:

> "Claude Code sets `user_message_uuid` on the turn's first non-ping stream event, and again when the message the turn is answering changes, under the conditions in [`user_message_uuid`](/docs/en/agent-sdk/typescript#user_message_uuid). **The Python `StreamEvent` doesn't expose this field.**"

TypeScript reference, section **`user_message_uuid`** — the full rule set, verbatim:

> "The `uuid` of the [`SDKUserMessage`](#sdkusermessage) the turn is answering, echoed so you can match Claude Code's reply to the message you sent. Claude Code echoes a `uuid` only if you set one on the message. The field is optional on `SDKUserMessage`, and a string prompt passed to `query()` carries none."

> "Claude Code echoes the answered message's `uuid` on three kinds of frame:
>
> * **The result**: every result of a turn that answered a message you sent. Every such result carries it on Agent SDK v0.3.265 or later. ...
> * **The turn's first reply**: the first [assistant message](#sdkassistantmessage), and with `includePartialMessages` also the first [stream event](#sdkpartialassistantmessage) whose `event.type` isn't `ping`, so you can bind the reply before the result arrives. The first-reply echo requires Agent SDK v0.3.246 or later. Before v0.3.269, with `includePartialMessages`, Claude Code set it on that first stream event only, or on the first assistant message when the turn streamed nothing. When the message the turn is answering changes mid-turn, the first reply after the change carries the field too, on Agent SDK v0.3.265 or later; earlier versions set it on one reply frame per turn.
> * **Every [`thinking_tokens`](#sdkthinkingtokensmessage) frame of the turn**: so you can attribute thinking progress to the message you sent without waiting for the turn's first reply. Requires Agent SDK v0.3.260 or later."

And the omission list, verbatim:

> "Claude Code omits the field in these cases:
>
> * Reply frames other than those first replies
> * Subagent frames
> * Turns that answer no message of yours, or answer a message you sent without a `uuid`
> * Results that answer no message you sent, such as the zeroed result after a crashed worker process"

**INFERRED:** the "first reply echo" exists so a client can **bind an in-flight turn to the request that started it before the result arrives**. *Reasoning:* the doc states the purpose explicitly ("so you can bind the reply before the result arrives") and identifies the *first non-`ping`* stream event as the anchor — `ping` frames are excluded precisely because they can be the very first frame and carry no turn identity. The `user_message_uuids` companion (plural) exists because "When you send several messages close together, Claude Code can merge them into one turn, and the field then carries only the last message's `uuid`."

**Clean-room opportunity:** a reimplementer that multiplexes several user messages over one session **must** have a turn-correlation key on the stream, or a client cannot tell which of its in-flight requests a given token belongs to. The idiomatic design is exactly this: a per-message `uuid` assigned by the client, echoed by the server on the first frame of the answering turn, plus a list form to handle merged turns. A clean-room implementation should (a) accept an optional client-supplied `uuid` on inbound user messages, (b) echo it on the first non-`ping` frame of the answering turn, and (c) never echo it on subagent frames. The reference product's *Python* omission of the field is a real inconsistency; a clean-room implementation should expose it in **both** languages rather than repeat the asymmetry.

---

### S8 — The `event` field carries raw provider events; six common event types

**Status: OBSERVED-DOC**

Primary page, section **"StreamEvent reference"** — the normative event-type table, verbatim:

> "The `event` field contains the raw streaming event from the [Claude API](https://platform.claude.com/docs/en/build-with-claude/streaming#event-types). Common event types include:
>
> | Event Type | Description |
> | :- | :- |
> | `message_start` | Start of a new message |
> | `content_block_start` | Start of a new content block (text or tool use) |
> | `content_block_delta` | Incremental update to content |
> | `content_block_stop` | End of a content block |
> | `message_delta` | Message-level updates (stop reason, usage) |
> | `message_stop` | End of the message |"

The Claude API streaming reference (https://platform.claude.com/docs/en/build-with-claude/streaming), section **"Event types"**, adds the normative flow:

> "Each stream uses the following event flow:
>
> 1. `message_start`: contains a `Message` object with empty `content`. ...
> 2. A series of content blocks, each of which has a `content_block_start`, one or more `content_block_delta` events, and a `content_block_stop` event. Each content block has an `index` that corresponds to its index in the final Message `content` array. One exception: during [server-side fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback#server-side-fallback) responses, a `fallback` content block arrives at each model boundary as a `content_block_start` and `content_block_stop` pair with no deltas in between.
> 3. One or more `message_delta` events, indicating top-level changes to the final `Message` object.
> 4. A final `message_stop` event."

And the delta taxonomy, from the same page, section **"Content block delta types"**:

> "Each `content_block_delta` event contains a `delta` of a type that updates the `content` block at a given `index`."

The four delta types documented there, with their exact payload keys:

| Delta `type` | Payload key | Verbatim source example |
|---|---|---|
| `text_delta` | `text` | `{"type": "content_block_delta","index": 0,"delta": {"type": "text_delta", "text": "ello frien"}}` |
| `input_json_delta` | `partial_json` | `{"type": "content_block_delta","index": 1,"delta": {"type": "input_json_delta", "partial_json": "{\"location\": \"San Fra"}}` |
| `thinking_delta` | `thinking` | `{"type": "content_block_delta","index": 0,"delta": {"type": "thinking_delta", "thinking": "I need to find the GCD of 1071 and 462 using the Euclidean algorithm.\n\n1071 = 2 × 462 + 147"}}` |
| `signature_delta` | `signature` | `{"type": "content_block_delta","index": 0,"delta": {"type": "signature_delta", "signature": "EqQBCgIYAhIM1gbcDa9GJwZA2b3hGgxBdjrkzLoky3dl1pkiMOYds..."}}` |

The API page also documents two event types **absent** from the Agent SDK page's table:

> "Event streams may also include any number of `ping` events." (section **"Ping events"**)

> "The API may occasionally send [errors](https://platform.claude.com/docs/en/api/errors) in the event stream. For example, during periods of high usage, you may receive an `overloaded_error`, which would normally correspond to an HTTP 529 in a non-streaming context: `event: error` / `data: {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}`" (section **"Error events"**)

And the forward-compatibility rule, verbatim:

> "In accordance with the [versioning policy](https://platform.claude.com/docs/en/api/versioning), new event types may be added, and your code should handle unknown event types gracefully."

**INFERRED:** the `event` payload is deliberately **untranslated** so that the Agent SDK adds no latency and no re-encoding cost between the provider socket and the consumer. *Reasoning:* the TypeScript type literally reuses the Anthropic SDK's own `BetaRawMessageStreamEvent`, and the field is named `event` with the comment "From Anthropic SDK"; the Python type is `dict[str, Any]`. The `index` field is the join key: "Each content block has an `index` that corresponds to its index in the final Message `content` array."

**Clean-room opportunity:** a clean-room agent should adopt a **raw-passthrough** design: the transport layer emits provider-native events, and the SDK layer wraps them in a uniform envelope without re-shaping the payload. The idiomatic implementation is a `RawMessageStreamEvent` union mirroring the provider's event grammar, plus an `index`-keyed accumulator that reassembles `content` blocks. Two rules are non-negotiable for compatibility: (1) **handle unknown event types gracefully** — a `default:` branch that ignores them, because the provider explicitly reserves the right to add types; (2) **treat `index` as the join key** for concurrent blocks. A clean-room implementation that renames `partial_json` or flattens the delta payload would break every consumer that accumulates tool arguments, so the delta grammar should be treated as a wire contract, not an internal detail.

---

### S9 — Default behaviour: one complete `AssistantMessage` per non-empty content block, sharing one message ID

**Status: OBSERVED-DOC**

Primary page, opening paragraph:

> "By default, the Agent SDK yields a complete `AssistantMessage` for each non-empty content block, such as a text block or a tool call, after Claude finishes generating that block."

Primary page, section **"Message flow"**:

> "Claude Code emits an `AssistantMessage` as each non-empty content block completes, so a response with a text block and a tool call yields two `AssistantMessage` objects. Each one carries only its own content block, and both share the same message ID, which you read as `message.message.id` in TypeScript and `message.message_id` in Python."

The two access paths are confirmed by the SDK reference pages. TypeScript, section **`SDKAssistantMessage`**:

```typescript
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

Python, section **`AssistantMessage`**:

```python
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

Python, **`AssistantMessage`** field table, verbatim:

> "| `message_id` | `str \| None` | API message ID. Multiple messages from one turn share the same ID |"

**INFERRED:** the per-block message granularity is a **consumer-choice** design, not a transport requirement. *Reasoning:* the doc's stated purpose is that a consumer can pick granularity — "a consumer can choose either granularity" is the framing used in the sibling area's capture of this protocol. Splitting by content block means a UI can render a tool call the instant it completes, without waiting for a trailing text block that the model may not emit until much later. The shared `message_id` is the reassembly key: concatenating the `content` arrays of all messages sharing one `message_id` reconstructs the provider's single assistant message.

**Clean-room opportunity:** the reference product's shape is directly adoptable: emit **one complete message object per non-empty content block**, all blocks of a turn sharing a `message_id`, each carrying only its own block. The idiomatic implementation is a small state machine in the block accumulator — on `content_block_stop`, if the block is non-empty, emit a complete-message frame and reset the accumulator for the next `index`. This is what makes "the assistant answered with text *and* a tool call" render as two separately-timestamped UI events rather than one blob, and it is a materially better UX than buffering the whole turn. A clean-room implementation should also expose the same `message_id` under the same *semantic* name in both languages, accepting that the accessor path differs (`message.message.id` vs `message.message_id`) exactly as the reference product does.

---

### S10 — The exact message-ordering contract (interleaved, not batched)

**Status: OBSERVED-DOC + OBSERVED-CLI**

Primary page, section **"Message flow"** — the normative ordering diagram, verbatim:

```text
StreamEvent (message_start)
StreamEvent (content_block_start) - text block
StreamEvent (content_block_delta) - text chunks...
AssistantMessage - complete text block
StreamEvent (content_block_stop)
StreamEvent (content_block_start) - tool_use block
StreamEvent (content_block_delta) - tool input chunks...
AssistantMessage - complete tool_use block
StreamEvent (content_block_stop)
StreamEvent (message_delta)
StreamEvent (message_stop)
... tool executes ...
... more streaming events for next turn ...
ResultMessage - final result
```

And the rule that makes this non-obvious, verbatim:

> "With partial messages enabled, each `AssistantMessage` arrives **before** that block's `content_block_stop` event, and you receive messages in this order:"

**OBSERVED-CLI** — I verified this ordering against a real capture on this host. The capture was made with the published CLI's own surface:

```
claude -p "Say the single word: HELLO" --output-format stream-json --verbose --include-partial-messages
```

Sanitized and reduced to type + discriminator, the observed order was:

```
0  system         (init)
1  system         (status)
2  stream_event   message_start          ttft_ms=2673
3  stream_event   content_block_start    index=0  content_block.type=text
4  stream_event   content_block_delta    index=0  delta.type=text_delta  text="HELLO"
5  assistant      message_id=msg_9mWXpq94OdxFctGCzjVx  content_block_types=["text"]
6  stream_event   content_block_stop     index=0
7  stream_event   message_delta
8  stream_event   message_stop
9  result         subtype=success
```

This **matches the documented diagram exactly**, including the two subtle points: the `assistant` frame at position 5 arrives **before** the `content_block_stop` at position 6, and the `assistant` frame's `message_id` equals the `api_message_id` carried on the surrounding stream frames (i.e. the raw events and the assembled message refer to one provider message). Full artifact: `observed-stream-event-sequence.jsonl` in this directory.

**INFERRED:** the ordering exists to support **two independent consumers without buffering**. *Reasoning:* the assembled `AssistantMessage` is emitted at the moment its block closes (before `content_block_stop`) so that a consumer that only wants complete messages does not have to wait for the block's terminator; a consumer that wants tokens renders them as they arrive. Neither consumer is forced to buffer the other. The `message_delta`/`message_stop` pair then closes the provider message, and `ResultMessage` closes the *turn* — a two-level closure (message → turn), with tool execution happening between turns.

**Clean-room opportunity:** this ordering is a public contract and can be adopted exactly. The idiomatic implementation is a single-pass state machine over the provider event stream with an explicit "block open" flag: emit deltas immediately; on block close, emit the assembled message **first** and the `content_block_stop` **second**; on `message_stop`, emit the turn result. A clean-room implementer should write the ordering as an **executable assertion** (a test that feeds a synthetic event sequence and asserts the emitted frame sequence) rather than trusting prose — the reference product's own history here, in S12, shows the termination ordering was once wrong and had to be fixed in a shipped release.

---

### S11 — Without partial messages, the message-type set changes but the envelope set is unchanged

**Status: OBSERVED-DOC**

Primary page, section **"Message flow"**:

> "Without partial messages enabled, you receive all message types except `StreamEvent`. Common types include `SystemMessage` (session initialization), `AssistantMessage` (complete content blocks), `ResultMessage` (final result), and a compact boundary message indicating when conversation history was compacted (`SDKCompactBoundaryMessage` in TypeScript; `SystemMessage` with subtype `"compact_boundary"` in Python)."

The full Python message union, from the Python reference, section **`Message`**:

```python
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

The TypeScript union, from the TypeScript reference, section **`SDKMessage`**, is considerably longer — it enumerates 30 variants including `SDKPartialAssistantMessage`, `SDKCompactBoundaryMessage`, `SDKStatusMessage`, `SDKLocalCommandOutputMessage`, `SDKHookStartedMessage`, `SDKHookProgressMessage`, `SDKHookResponseMessage`, `SDKPluginInstallMessage`, `SDKToolProgressMessage`, `SDKAuthStatusMessage`, `SDKTaskNotificationMessage`, `SDKTaskStartedMessage`, `SDKTaskProgressMessage`, `SDKTaskUpdatedMessage`, `SDKBackgroundTasksChangedMessage`, `SDKThinkingTokensMessage`, `SDKSessionStateChangedMessage`, `SDKWorkerShuttingDownMessage`, `SDKCommandsChangedMessage`, `SDKNotificationMessage`, `SDKFilesPersistedEvent`, `SDKToolUseSummaryMessage`, `SDKMemoryRecallMessage`, `SDKRateLimitEvent`, `SDKElicitationCompleteMessage`, `SDKPermissionDeniedMessage`, `SDKPromptSuggestionMessage`, `SDKAPIRetryMessage`, `SDKMirrorErrorMessage`, `SDKInformationalMessage`, and `SDKConversationResetMessage`.

The compaction-boundary shape, TypeScript reference, section **`SDKCompactBoundaryMessage`**:

```typescript
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

**INFERRED:** `StreamEvent` is the *only* member of the union that is conditional on an option; everything else is always available. *Reasoning:* the doc says "you receive all message types **except** `StreamEvent`", and the option is the sole switch. This means a consumer's type-narrowing logic must handle exactly one optional variant, and the rest of the union is unconditional — a favourable property for a reimplementer. Note also the **cross-language asymmetry**: the compaction boundary is a *distinct type* in TypeScript but a *subtype* of `SystemMessage` in Python. That is a real difference in the reference product, and a clean-room implementation should pick one model and be consistent.

**Clean-room opportunity:** adopt a **single closed union of message types**, each discriminated by `type`, with exactly one variant (`stream_event`) gated behind an option. The Python idiom (one dataclass per variant, plus a `Message` union alias) and the TypeScript idiom (one object type per variant, plus a `SDKMessage` union alias) are both directly implementable. A clean-room implementation should also adopt the *additive* growth rule the reference product states for its own type, quoted from the TypeScript reference:

> "Claude Code evolves the type additively, adding new data as optional fields rather than reshaping existing ones. Read the fields you know and ignore any you don't recognize."

That single sentence is the compatibility policy a reimplementer should adopt verbatim in spirit: **never remove or repurpose a field; add new ones optionally; require consumers to tolerate unknown keys.**

---

### S12 — Cut streams: `message_stop` still arrives, but a cut tool call loses its `content_block_stop`

**Status: OBSERVED-DOC**

Primary page, section **"Handle a stream that's cut off"** — the entire section, verbatim:

> "If a stream is cut off mid-message, such as when you interrupt the turn or the connection drops, you still receive that message's `message_stop` before the turn ends. A cut text or thinking block also gets its `content_block_stop`. A cut tool call doesn't, so if `message_stop` arrives while a tool call's block is still open, treat that call's input as incomplete."

> "Before Claude Code v2.1.290, a cut stream could end the turn without `message_stop`, so a reply you render from stream events could stay shown as in progress. The TypeScript Agent SDK bundles Claude Code v2.1.290 or later from v0.3.290, and the Python Agent SDK from v0.2.164. If a reply stays shown as in progress after the turn ends, update the SDK."

**INFERRED:** the documented "still open" test is the *only* reliable way to detect a truncated tool call. *Reasoning:* the doc gives an explicit decision procedure — "`message_stop` arrives while a tool call's block is still open" → the call's input is incomplete. The asymmetry between text/thinking (which get their `content_block_stop`) and tool calls (which don't) is stated without further justification, so the *mechanism* is UNKNOWN; the *rule* is fully specified. The version note also reveals a **UI-level** consequence: a consumer that derives "reply in progress" purely from stream events will show a permanently-spinning reply if `message_stop` never arrives — hence the fix in v2.1.290 and the SDK version floors (TypeScript v0.3.290, Python v0.2.164).

**Clean-room opportunity:** a reimplementer should adopt both halves of this contract deliberately, because they are cheap and they are the difference between a UI that recovers and one that hangs. (1) **Always emit `message_stop` on turn termination, including on interrupt and on transport error** — the reference product had to fix this, so an implementation that gets it right the first time is strictly better. (2) **Never emit `content_block_stop` for a block that did not complete**, and expose the "block still open at `message_stop`" condition as an explicit, documented signal. The idiomatic implementation is a per-block `open` flag in the accumulator, checked at `message_stop`; the consumer rule is then one line: *if a tool block is open when `message_stop` arrives, mark its input incomplete and do not execute it*. A clean-room product should additionally emit an explicit terminal frame (e.g. a `result` with an `aborted`/`interrupted` subtype) so the consumer does not have to infer the outcome — which is what the reference product's own `SDKAssistantMessage.aborted?: true` and `terminal_reason: "aborted_streaming"` / `"aborted_tools"` fields point toward.

---

### S13 — Tool calls stream incrementally through three event types, with `partial_json` as the accumulator key

**Status: OBSERVED-DOC**

Primary page, section **"Stream tool calls"**:

> "Tool calls also stream incrementally. You can track when tools start, receive their input as it's generated, and see when they complete. The example below tracks the current tool being called and accumulates the JSON input as it streams in. It uses three event types:
>
> * `content_block_start`: tool begins
> * `content_block_delta` with `input_json_delta`: input chunks arrive
> * `content_block_stop`: tool call complete"

The Python accumulation pattern, verbatim from the page:

```python
current_tool = None
tool_input = ""

async for message in query(prompt="Read the README.md file", options=options):
    if isinstance(message, StreamEvent):
        event = message.event
        event_type = event.get("type")

        if event_type == "content_block_start":
            # New tool call is starting
            content_block = event.get("content_block", {})
            if content_block.get("type") == "tool_use":
                current_tool = content_block.get("name")
                tool_input = ""
                print(f"Starting tool: {current_tool}")

        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "input_json_delta":
                # Accumulate JSON input as it streams in
                chunk = delta.get("partial_json", "")
                tool_input += chunk
                print(f"  Input chunk: {chunk}")

        elif event_type == "content_block_stop":
            # Tool call complete - show final input
            if current_tool:
                print(f"Tool {current_tool} called with: {tool_input}")
                current_tool = None
```

The API reference confirms the `tool_use` block shape at `content_block_start`, verbatim:

> `data: {"type": "content_block_start", "index":1,"content_block":{"type": "tool_use", "id": "toolu_01T1x1fJ34qAmk2tNTrN7Up6", "name": "get_weather", "input": {}}}`

and the immediately following delta:

> `data: {"type": "content_block_delta", "index":1,"delta":{"type": "input_json_delta", "partial_json":""}}`

The API reference also notes the practical consequence of this grammar:

> "Note: Current models only support emitting one complete key and value property from `input` at a time. As such, when using tools, there may be delays between streaming events while the model is working. Once an `input` key and value are accumulated, they are emitted as multiple `content_block_delta` events with chunked partial JSON so that the format can automatically support finer granularity in future models."

and the recommended parse point:

> "You can accumulate the string deltas and parse the JSON once you receive a `content_block_stop` event, by using a library like [Pydantic](https://docs.pydantic.dev/latest/concepts/json/#partial-json-parsing) to do partial JSON parsing, or by using the SDK's [streaming helpers](https://platform.claude.com/docs/en/build-with-claude/streaming#streaming-with-sdks). In the Python and TypeScript SDKs, these helpers also give you access to the parsed `input` incrementally, as it streams."

**INFERRED:** the tool-call grammar is designed so a client can render *and* show progress on a tool call's arguments while they arrive, without ever having to execute on partial JSON. *Reasoning:* `partial_json` is a **string** fragment, not a JSON value, so the only correct consumption is string concatenation followed by a single parse at block close — a design that makes it structurally impossible to accidentally execute a half-built argument object. The `content_block_start` carries `id`, `name`, and an empty `input: {}`, so the tool identity is known before any argument arrives.

**Clean-room opportunity:** this is the single most reusable mechanism in the page for an independent implementation, because a tool-calling agent needs it regardless of which model provider it uses. The observable contract is: a tool call arrives as a `content_block_start` with `{type: "tool_use", id, name, input: {}}`, then a run of `content_block_delta` frames with `delta.type == "input_json_delta"` carrying string fragments in `delta.partial_json`, then `content_block_stop`. The idiomatic implementation is (a) a per-`index` string accumulator, (b) a **single** `json.loads` at block close, (c) a schema validation step *after* parsing, and (d) an explicit "incomplete" path when `message_stop` arrives with the block still open. A clean-room implementation should also provide a **partial-JSON parser** so a UI can show "the agent is filling in `path`…" — that is what the reference product's own `partial-json-parsing` recommendation points at, and it is a genuine UX differentiator. The contract that must be preserved verbatim is the key name `partial_json` and the rule that the payload is a *fragment*.

---

### S14 — Known limitation: structured output streams as unvalidated partial JSON

**Status: OBSERVED-DOC**

Primary page, section **"Known limitations"** — the complete section, verbatim:

> "* **Structured output**: with partial messages enabled, the JSON streams as a tool call's unvalidated `input_json_delta` chunks, and only the validated result reaches the final `ResultMessage.structured_output`. [Recognize the StructuredOutput tool call](/docs/en/agent-sdk/structured-outputs#recognize-the-structuredoutput-tool-call) covers how that call appears in your stream."

The linked page (`/docs/en/agent-sdk/structured-outputs`, section **"Recognize the StructuredOutput tool call"**) explains the mechanism:

> "When you set `outputFormat` in TypeScript or `output_format` in Python, your message stream carries a tool call named `StructuredOutput` that you never defined. Claude Code adds this tool to the session, and the agent calls it to return its answer. The [system init message](/docs/en/agent-sdk/typescript#sdksystemmessage) lists it in the `tools` array, and each call arrives as two blocks:
>
> * A `tool_use` block named `StructuredOutput`, whose input is the object the agent produced for your schema
> * A `tool_result` block reading `Structured output provided successfully`"

> "When that object doesn't match your schema, the `tool_result` carries `is_error: true` instead and the agent calls `StructuredOutput` again, so your stream can hold several calls for one query. Read the validated data from `structured_output` on the result message rather than from a `tool_use` block"

> "If your application shows or logs tool calls, skip the ones named `StructuredOutput` so the mechanism doesn't appear as a step the agent chose. A `tool_result` block carries no tool name, only the `tool_use_id` of the call it answers, so match that against the `id` of each call you skipped."

The `structured_output` field itself is on the result message — Python reference, `ResultMessage`:

> `structured_output: Any = None`

**INFERRED:** the "unvalidated" qualifier is the whole point of the limitation. *Reasoning:* the streamed `input_json_delta` chunks are the model's raw output and may not satisfy the declared schema; the schema is enforced only at the end, and the validated artifact is delivered in the *result* message. A consumer that renders the streamed chunks as the final answer will show invalid JSON in the failure case. The multi-call retry behaviour ("your stream can hold several calls for one query") makes this worse: a naive consumer sees several `tool_use` blocks named `StructuredOutput` and cannot tell which one succeeded without reading `is_error` on the paired `tool_result`.

**Clean-room opportunity:** a clean-room implementation that offers schema-constrained output should (a) **never** present the streamed JSON as final — present it as provisional, (b) deliver the validated artifact only on the terminal result message, and (c) if it uses a synthetic tool-call mechanism, give that tool a **reserved, documented name** and instruct consumers to filter it, because the mechanism is otherwise indistinguishable from an agent-chosen step. The reference product's own advice — "skip the ones named `StructuredOutput`" — is a reasonable default, but a clean-room implementation can do better by using a distinct message type or a `meta` flag on the tool-call frame so consumers do not have to filter by *name* at all. Independently, a clean-room implementation should support a **retry loop** for schema validation (the reference product retries via repeated tool calls) and should surface the failure reason in the result's `errors` list, as the structured-outputs page describes for distinguishing validation failure from model-fallback retraction.

---

### S15 — `ping` frames are liveness signals, not errors — and the gateway case matters

**Status: OBSERVED-DOC**

TypeScript reference, **Options** section (the same paragraph appears verbatim in the Python reference, with `include_partial_messages`):

> "While the watchdog waits out a response that a gateway behind `ANTHROPIC_BASE_URL` holds open with keep-alive pings, a host that sets `includePartialMessages` keeps receiving `ping` [stream events](#sdkpartialassistantmessage), so read those frames as liveness rather than timing the session out on silence. Before v2.1.257, the frames stopped 5 minutes after the last real stream event."

TypeScript reference, section **`user_message_uuid`**, on why `ping` is excluded from the first-reply anchor:

> "the first [stream event](#sdkpartialassistantmessage) whose `event.type` isn't `ping`, so you can bind the reply before the result arrives"

The API reference states the frame is part of the grammar, verbatim: "Event streams may also include any number of `ping` events." and the SSE example `event: ping` / `data: {"type": "ping"}`.

**INFERRED:** `ping` is a **heartbeat**, and the documented guidance is that a client with an inactivity timeout must treat a `ping` as proof of life. *Reasoning:* the doc says to "read those frames as liveness rather than timing the session out on silence" — that is, a timeout policy must be *reset* by a `ping`, not merely ignored. The exclusion of `ping` from the first-reply anchor is consistent: a `ping` carries no turn identity, so it cannot bind a turn to a request. The "Before v2.1.257, the frames stopped 5 minutes after the last real stream event" note indicates the heartbeat was previously delivered only in a burst, then changed to continue for the life of the connection.

**Clean-room opportunity:** an implementation that connects to a model provider through a proxy or gateway will hit exactly this case. The observable contract is: a `ping`-typed frame with payload `{"type": "ping"}` may appear at any point; it carries no content; it must not be rendered, must not be counted as a delta, and **must reset the client's inactivity timer**. A clean-room implementation should also exclude `ping` from any "first frame of the turn" logic, for the same reason the reference product does. The idiomatic implementation is a keep-alive handler at the transport layer that touches a `last_activity` timestamp and is invisible to the message layer.

---

### S16 — The CLI exposes the same capability as `--include-partial-messages`, restricted to `--print` + `stream-json`

**Status: OBSERVED-DOC + OBSERVED-CLI**

The headless reference (`/docs/en/headless`, section **"Stream responses"**) states:

> "Use `--output-format stream-json` with `--verbose` and `--include-partial-messages` to receive tokens as they're generated. Each line is a JSON object representing an event:"

> "The last line of the stream is a `result` message with the final response text, cost, and session metadata."

> "If your consumer reads the stream slowly, Claude Code waits for the queued output to drain before exiting, scaling the wait with how much is still queued, capped at 30 seconds."

The CLI reference table (`/docs/en/cli-reference`) gives the flag's own description:

> "| `--include-partial-messages` | Include partial streaming events in output. Requires `--print` and `--output-format stream-json` | `claude -p --output-format stream-json --verbose --include-partial-messages "query"` |"

**OBSERVED-CLI** — the published CLI's own `--help` text on this host, verbatim:

```
  --include-partial-messages            Include partial message chunks as they
                                        arrive (only works with --print and
                                        --output-format=stream-json)
```

**OBSERVED-CLI** — the documented `jq` filter for text deltas, which is a compact, machine-checkable statement of the wire shape:

```bash
claude -p "Write a poem" --output-format stream-json --verbose --include-partial-messages | \
  jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'
```

**INFERRED:** the CLI's `stream-json` output is the *same envelope family* as the SDK's, flattened to newline-delimited JSON on stdout. *Reasoning:* the `jq` filter selects on `.type == "stream_event"` and then `.event.delta.type? == "text_delta"` — the identical three-level discriminant structure documented for the SDK (S2), with the same `type`/`event`/`delta` key names. The only difference is transport: the SDK yields objects from an async iterator; the CLI writes one JSON object per line. That makes the CLI surface an *executable specification* of the envelope, and the SDK surface an *ergonomic wrapper* over the same thing.

**Clean-room opportunity:** the two surfaces should be implemented from one shared core. The idiomatic design: a single internal event-stream generator that produces envelope objects; a CLI writer that JSON-serialises each object as one line to stdout; an SDK layer that yields the same objects from an async iterator. The CLI's *flag validation* is worth copying exactly — the reference product rejects `--include-partial-messages` outside `--print` + `stream-json` with exit code 1, before any model call, rather than silently ignoring it. The "slow consumer" rule is also worth adopting: a bounded drain wait (the reference caps at 30 seconds) prevents a truncated final line when the consumer is slow.

---

### S17 — The TypeScript union's `stream_event` frame carries fields the CLI surface does not show

**Status: OBSERVED-CLI + INFERRED**

**OBSERVED-CLI** — the actual `stream_event` frames captured on this host carry these top-level keys, verbatim from the capture:

```json
{"type":"stream_event","event":{...},"session_id":"718fc7cb-...","parent_tool_use_id":null,
 "uuid":"4142985e-4bd0-4475-8043-a71870ed6493","ttft_ms":2673,
 "thinking_display":"updates","api_message_id":"msg_9mWXpq94OdxFctGCzjVx"}
```

**OBSERVED-CLI** — the `assistant` frame in the same capture:

```json
{"type":"assistant","message":{"id":"msg_9mWXpq94OdxFctGCzjVx", ... },
 "parent_tool_use_id":null,"session_id":"718fc7cb-...",
 "uuid":"95aa4ae9-e95a-44c2-8791-b4b21f569423",
 "timestamp":"2026-10-21T17:48:39.467Z","request_id":"gen-1792604917-9mWXpq94OdxFctGCzjVx"}
```

**INFERRED:** the CLI's `stream-json` frame is a **superset** of the SDK's documented `SDKPartialAssistantMessage`, carrying at least two extra fields (`thinking_display`, `api_message_id`) that the published SDK type does not declare, and the `assistant` frame carries `request_id` and `timestamp` beyond the documented `SDKAssistantMessage`. *Reasoning:* the documented SDK type lists exactly ten fields (`type`, `event`, `parent_tool_use_id`, `uuid`, `session_id`, `ttft_ms`, `user_message_uuid`, `user_message_uuids`, `resume_reason`); the observed frame has `type`, `event`, `session_id`, `parent_tool_use_id`, `uuid`, `ttft_ms`, `thinking_display`, `api_message_id` — two extra, and the three documented correlation fields (`user_message_uuid`, `user_message_uuids`, `resume_reason`) absent. The absence is *expected*, per S7: the CLI's own synthetic user turn carries no `uuid`, and the doc says Claude Code omits the field for "Turns that answer no message of yours, or answer a message you sent without a `uuid`". The two *extra* fields are not documented on the SDK type at all.

**UNKNOWN:** whether `thinking_display` and `api_message_id` are part of a stable, documented CLI contract, or internal/incidental fields of this particular build. The cited public pages for this area do not define them, and the CLI reference for `--output-format stream-json` does not enumerate the frame schema field-by-field.

**Clean-room opportunity:** this is the strongest practical argument for the *additive, tolerate-unknown-keys* rule stated in S11. A clean-room implementation should publish its full frame schema, but must build consumers that **ignore unrecognised fields** — because the reference product's own CLI surface already carries fields its SDK type does not declare. A clean-room implementation that hard-fails on unknown keys would break against the real product. The two extra observed fields are, in themselves, good design worth adopting: `api_message_id` (or an equivalent) is the *join key* that ties a raw stream frame to the assembled message, and a thinking-display mode is a **UI policy flag** the consumer can honour without parsing thinking content. A clean-room implementation should adopt the same principle: put *presentation* hints on the frame as a declared enum, so the consumer does not have to infer a policy from content.

---

### S18 — The terminal frame is a two-arm discriminated union: `subtype: "success"` vs. four error subtypes

**Status: OBSERVED-DOC + OBSERVED-CLI**

TypeScript reference, section **`SDKResultMessage`** — the union is discriminated on `subtype`, with a `success` arm and a second arm covering all four error subtypes, verbatim:

```typescript
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
      ...
  | {
      type: "result";
      subtype:
        | "error_max_turns"
        | "error_during_execution"
        | "error_max_budget_usd"
        | "error_max_structured_output_retries";
      ...
      errors: string[];
      startup_failure_reason?: SDKStartupFailureReason;
      ...
```

The Python reference states the same five-value enum, verbatim:

> "The `subtype` field determines which other fields are populated. It is one of `"success"`, `"error_during_execution"`, `"error_max_turns"`, `"error_max_budget_usd"`, or `"error_max_structured_output_retries"`. The Python dataclass flattens all variants into one shape, so fields that don't apply to the returned subtype are `None`."

**OBSERVED-CLI** — the observed `result` frame on this host carried `subtype: "success"` and these top-level keys: `api_error_status`, `duration_api_ms`, `duration_ms`, `fast_mode_disabled_reason`, `fast_mode_state`, `first_content_frame_ms`, `is_error`, `modelUsage`, `num_turns`, `permission_denials`, `queued_turn_count`, `result`, `result_index`, `safety_stops`, `session_id`, `stop_reason`, `subagent_stats`, `subtype`, `terminal_reason`, `time_to_request_ms`, `total_cost_usd`, `ttft_ms`, `ttft_stream_ms`, `type`, `usage`, `uuid`. Note `structured_output` is **absent** (no `output_format` was requested on that run) — presence-gated, not null-padded, in the CLI surface.

**INFERRED:** the success arm and the error arm carry *different* field sets, and the error arm adds `errors: string[]` and `startup_failure_reason`. *Reasoning:* the TypeScript type is a two-arm union, so a consumer narrowing on `subtype === "success"` gets `result: string` (always present) while the error arm does not have a `result` field at all. The Python side flattens this into one dataclass with `None` defaults, which the doc explicitly calls out — a known ergonomic cost of the flat design. The observed absence of `structured_output` when unused is consistent with the page's own S14 rule that "only the validated result reaches the final `ResultMessage.structured_output`": the field appears when there is a validated artifact to carry.

**Clean-room opportunity:** the terminal frame should be a **discriminated union on `subtype`**, not a flat bag of nullable fields. The idiomatic implementation is a tagged union where the success arm and the error arm have genuinely different shapes — this makes it *impossible* for a consumer to read `result` on an error frame and get a silent `undefined`, and it removes the "which fields are `None` here?" question the Python flat dataclass forces on every consumer. A clean-room implementation should also carry a human-readable `errors: string[]` on every non-success arm, so a client never has to parse a status code to learn what went wrong.

---

### S19 — Partial messages are not a separate transport; they are an additive layer over the same pipeline

**Status: INFERRED**

**Reasoning.** The page's framing — "This causes the SDK to yield `StreamEvent` messages containing raw API events as they arrive, **in addition to** the usual `AssistantMessage` and `ResultMessage`" — together with the S10 ordering diagram, establishes that partial messages are a *second view* of one pipeline, not a second pipeline. Three pieces of evidence converge:

1. The same `AssistantMessage` objects appear in both modes (S9), and with partial messages enabled they are *interleaved* with the raw events rather than replacing them (S10).
2. The `ResultMessage` is the terminal frame in both modes (S11, S16).
3. The `event` payload is a raw pass-through (S8), so enabling partial messages adds no new upstream work — it only starts *forwarding* events that were already arriving.

The practical consequence is that partial streaming is a **pure superset**: a consumer that ignores `stream_event` frames entirely sees exactly the default-mode message stream. The reference product's own headless guidance is consistent with this, since the `jq` filter is an *optional* narrowing of the same stream.

**UNKNOWN:** whether the raw provider events are buffered and replayed on demand, or genuinely intercepted at the socket. The page's phrasing ("as they arrive") suggests interception, but the docs do not state the internal mechanism, and this is not observable from the public surface. A consumer cannot distinguish the two, which is the point — but an implementer should not assume it matters.

**Clean-room opportunity:** design the core agent loop to emit **one ordered event sequence**, and derive both views from it. The idiomatic architecture is a single "event bus" carrying provider-native events, with two subscribers: an *assembler* (which produces the complete-message view) and a *passthrough* (which produces the partial-message view, gated on the option). This makes the default path free and the partial path a one-line subscription. It also makes the ordering rule (S10) *structurally* correct rather than hand-maintained: if there is one emitter, the interleaving falls out of the accumulator's control flow instead of being patched in. A clean-room implementation should also make the *assembled* view the source of truth and the *partial* view advisory, so that a consumer which ignores partial frames still renders correctly — the reference product's design makes exactly this guarantee.

---

## 7c.4 Capability table

| Capability | Observable contract | Status | Clean-room adopt? |
|---|---|---|---|
| Opt-in partial streaming | `include_partial_messages` (Py) / `includePartialMessages` (TS), default `false` | OBSERVED-DOC | Yes — trivial |
| Partial-frame envelope | `type: "stream_event"` + `event` (raw) + `uuid` + `session_id` + `parent_tool_use_id` (always null) | OBSERVED-DOC + OBSERVED-CLI | Yes — data only |
| Text token streaming | `content_block_delta` → `delta.type == "text_delta"` → `delta.text` | OBSERVED-DOC + OBSERVED-CLI | Yes |
| Tool-argument streaming | `content_block_start`(`type:"tool_use"`, `id`, `name`, `input:{}`) → `input_json_delta`/`partial_json` → `content_block_stop` | OBSERVED-DOC | Yes |
| Thinking streaming | `delta.type == "thinking_delta"` → `delta.thinking`; `signature_delta` → `delta.signature` | OBSERVED-DOC | Yes |
| Per-block assembled messages | one `AssistantMessage` per non-empty content block; shared `message_id`; emitted **before** `content_block_stop` | OBSERVED-DOC + OBSERVED-CLI | Yes |
| Message ID accessors | `message.message.id` (TS) / `message.message_id` (Py) | OBSERVED-DOC | Yes |
| Turn/result closure | `message_delta` → `message_stop` → `ResultMessage` (`subtype`, `is_error`, `structured_output`, `usage`, `modelUsage`) | OBSERVED-DOC + OBSERVED-CLI | Yes |
| Terminal-frame discrimination | `subtype: "success"` ∣ `"error_max_turns"` ∣ `"error_during_execution"` ∣ `"error_max_budget_usd"` ∣ `"error_max_structured_output_retries"`; error arm adds `errors[]` | OBSERVED-DOC + OBSERVED-CLI | Yes — use a tagged union, not a flat nullable bag |
| Heartbeat frames | `ping` — liveness only; must reset inactivity timer; excluded from first-reply anchor | OBSERVED-DOC | Yes |
| In-band errors | `{"type":"error","error":{"type":"overloaded_error","message":"..."}}` inside the event stream | OBSERVED-DOC | Yes |
| Unknown-event tolerance | "your code should handle unknown event types gracefully" | OBSERVED-DOC | Yes — required |
| Turn correlation | `user_message_uuid` (TS only) on first non-`ping` frame; `user_message_uuids` (plural) for merged turns | OBSERVED-DOC | Yes — expose in both languages |
| Latency telemetry | `ttft_ms` on `message_start` only (frame); `ttft_stream_ms` / `first_content_frame_ms` on the result | OBSERVED-DOC + OBSERVED-CLI | Yes |
| Cut-stream detection | `message_stop` arrives with a tool block still open → input incomplete | OBSERVED-DOC | Yes |
| Compaction boundary | `SDKCompactBoundaryMessage` (TS) / `SystemMessage` `subtype:"compact_boundary"` (Py), `compact_metadata.{trigger,pre_tokens}` | OBSERVED-DOC | Yes — pick one model |
| Structured output via stream | streamed JSON is **unvalidated** `input_json_delta`; validated value only in `ResultMessage.structured_output` | OBSERVED-DOC | Yes — with better framing |
| Subagent token forwarding | **Not** forwarded; `parent_tool_use_id` always null on partial frames | OBSERVED-DOC | Yes (or better, via distinct type) |
| CLI parity | `--include-partial-messages` (requires `--print` + `--output-format stream-json`); NDJSON on stdout | OBSERVED-DOC + OBSERVED-CLI | Yes |
| Message-type union | 7 variants (Py) / 30 variants (TS) | OBSERVED-DOC | Yes — closed union, additive growth |
| Type-shape stability | "evolves the type additively… Read the fields you know and ignore any you don't recognize" | OBSERVED-DOC | Yes — adopt verbatim in spirit |

---

## 7c.5 Dependencies

| Dependency | Why the streaming protocol needs it | Status |
|---|---|---|
| A streaming-capable model provider (SSE or equivalent) | The event grammar (`message_start` … `message_stop`) is the provider's, passed through unwrapped | OBSERVED-DOC |
| Network transport with keep-alive | `ping` heartbeats exist because gateways hold connections open; the SDK watchdog waits them out | OBSERVED-DOC |
| JSON-lines stdout writer | The CLI's `stream-json` format is one JSON object per line on stdout | OBSERVED-DOC + OBSERVED-CLI |
| A JSON parser (for tool args) | `partial_json` fragments must be concatenated and parsed **once** at `content_block_stop` | OBSERVED-DOC |
| Optional partial-JSON parser | To show structured progress on in-flight tool arguments | OBSERVED-DOC (recommended by Anthropic) |
| A monotonic clock | `ttft_ms`, `duration_ms`, `duration_api_ms`, `first_content_frame_ms` are wall-clock measurements | OBSERVED-DOC |
| A `uuid` generator | Every frame carries a unique `uuid` | OBSERVED-DOC + OBSERVED-CLI |
| **No** account / subscription | Not required by the protocol itself | INFERRED |
| **No** Claude Code binary internals | The protocol is fully specified in public docs | OBSERVED-DOC |

---

## 7c.6 Limitations of this investigation

1. **The primary page is an Agent SDK page, not a CLI page.** It documents the SDK's programmatic surface. The CLI's `stream-json` surface is documented elsewhere and is only partially covered by the citations here.
2. **The SDK type shapes are cited from sibling reference pages**, not from the page under study. The page under study links to them by anchor (`/docs/en/agent-sdk/typescript#sdkpartialassistantmessage`, `/docs/en/agent-sdk/python#streamevent`) but does not inline the type definitions. I fetched and cited both to establish the exact field sets.
3. **The API-level event grammar is cited from `platform.claude.com/docs`**, not from `code.claude.com/docs`. The Agent SDK page delegates to it ("The `event` field contains the raw streaming event from the [Claude API]") and includes only a six-row summary table. The full grammar (`ping`, `error`, delta subtypes, `index` semantics) is on the API page.
4. **Subscription-gated behaviour is not observable on this host** (custom `ANTHROPIC_BASE_URL`, third-party model). All Anthropic-API-specific behaviour — real token shapes, real usage numbers, real `ping` cadence against `api.anthropic.com` — is **OBSERVED-DOC only**.
5. **The observed capture is a single short, single-block turn.** It confirms the ordering for a text-only response. It does **not** independently confirm the tool-call branch of the ordering diagram (text block *and* tool call in one turn), nor the multi-turn "... more streaming events for next turn ..." continuation.
6. **I did not observe a cut stream.** The cut-stream rules in S12 are OBSERVED-DOC only; interrupting a live turn to force one was outside this area's scope.

---

## 7c.7 Unresolved questions (UNKNOWN)

1. **What exactly is `thinking_display`?** Observed on this host's `stream_event` frames with the value `"updates"`; not defined on the cited SDK types or on the CLI reference. Its value space, its default, and whether it is contractual are all unknown.
2. **Is `api_message_id` a stable contract?** It is the observed join key between a raw stream frame and its assembled message, and it appears on both frame types — but it is absent from the documented `SDKPartialAssistantMessage` and `SDKAssistantMessage` types. Whether it is public, internal, or deprecated is unknown.
3. **What is the full `stream-json` frame schema?** The CLI reference documents the *flag*, not a per-field schema for the frame objects. The `type`/`event`/`session_id`/`uuid`/`parent_tool_use_id` core is documented; the remainder of the observed field set is not.
4. **Why does a cut tool call get no `content_block_stop`, while cut text/thinking blocks do?** The rule is specified; the mechanism is not stated anywhere in the cited docs.
5. **Is the raw provider event buffered or intercepted?** The docs say events arrive "as they arrive" but never describe the internal mechanism (S19). Not observable from the public surface.
6. **Does the `ping` cadence differ against `api.anthropic.com` vs. a gateway?** The docs mention gateway keep-alives specifically, and note the pre-v2.1.257 behaviour ("the frames stopped 5 minutes after the last real stream event"), but no current cadence is documented.
7. **Is the `user_message_uuid` omission in the Python `StreamEvent` a deliberate simplification or an oversight?** The doc states the fact flatly ("The Python `StreamEvent` doesn't expose this field") without rationale. Given the TypeScript type carries it, it reads as an oversight — but that is an inference, not a documented statement.
8. **What is the exact `ResultMessage` frame's field set on the `stream_event` path?** The `SDKResultMessage` TypeScript type is a discriminated union on `subtype` with many arms; the CLI's observed `result` frame was not diffed field-by-field against it in this area.

---

## 7c.8 Clean-room implementation opportunity — per major feature

**The whole area, in one line:** implement a **closed, discriminated union of message envelopes**, one of which is a **raw pass-through** of provider streaming events, over a **single event pipeline** that also produces the assembled-message view — and get the **interleaving order** right, because that is the one thing the reference product itself got wrong twice.

**What an independently-written implementation must get right, in priority order:**

1. **The envelope.** A `type`-discriminated object per frame. The partial-frame variant carries `type: "stream_event"`, the raw `event`, a `uuid`, a `session_id`, and a `parent_tool_use_id` that is *documented as always null*. Ten fields at most; the reference product's own published type is the template.
2. **The nesting key.** `parent_tool_use_id` on complete messages; `null` on partial frames. This is how a consumer rebuilds a subagent tree.
3. **The delta grammar.** `delta.type` discriminates `text_delta` (`text`), `input_json_delta` (`partial_json`), `thinking_delta` (`thinking`), `signature_delta` (`signature`). Preserve the key names exactly — they are the wire contract, and a consumer accumulates `partial_json` as a *string fragment*.
4. **The ordering.** Per block: `content_block_start` → `content_block_delta`\* → **assembled message** → `content_block_stop`. Per turn: `message_start` → blocks → `message_delta` → `message_stop` → (tool execution) → next turn → `ResultMessage`. Encode this as an executable test over a synthetic event sequence, not as prose.
5. **The completion semantics.** Emit `message_stop` on *every* turn termination, including interrupts and transport errors. Never emit `content_block_stop` for a block that did not complete. Expose "block open at `message_stop`" as the documented incomplete-tool-call signal. (The reference product needed a bug fix to get the first half right; the second half is a rule most implementations will get wrong by default, because a naive "always close the block" cleanup handler will emit a `content_block_stop` for a truncated tool call.)
6. **Heartbeats.** Treat `ping` as liveness: reset the inactivity timer, render nothing, count nothing, exclude from first-frame logic. Handle `error` frames in-band.
7. **Forward compatibility.** Ignore unknown `event.type` and unknown `delta.type`. Ignore unknown envelope fields. Never remove or repurpose a field. This is stated policy in the reference product and is provably necessary — its own CLI surface carries fields its published type omits (S17).
8. **Turn correlation.** Accept an optional client-supplied `uuid` on inbound user messages; echo it on the first non-`ping` frame of the answering turn; also provide a list form for merged turns. Expose it in *both* languages, fixing the reference product's Python/TypeScript asymmetry.
9. **One pipeline, two views.** Derive the partial view and the assembled view from a single emitter, so the default path costs nothing and the interleaving is structural rather than hand-maintained.
10. **A tagged terminal frame.** Model the result as a discriminated union on `subtype` — a `success` arm and an error arm — rather than one flat object of nullable fields. The success arm's `result` string should not exist on the error arm at all, and the error arm should always carry `errors: string[]` (S18).
11. **CLI parity from the same core.** The same envelope objects, serialised one-per-line to stdout under `--output-format stream-json`, with the same flag-compatibility validation (reject `--include-partial-messages` outside `--print` + `stream-json`, with exit code 1, before any model call) and a bounded drain wait for slow consumers.

**What is *not* worth replicating:** the exact field-set asymmetry between the Python and TypeScript SDKs (Python lacks `user_message_uuid`; Python models the compaction boundary as a `SystemMessage` subtype while TypeScript gives it its own type; TypeScript's union has 30 variants against Python's 7). Pick one consistent model. Also not worth replicating: the historical `message_stop` bug and its version floors — just get it right from the start.

**What a clean-room implementation could do *better* than the reference product, at low cost:**
- Expose the turn-correlation fields in every language and every frame type, not just TypeScript.
- Mark the synthetic structured-output tool call with a metadata flag, so consumers filter on a flag rather than on a magic tool *name* (the reference product's own doc tells consumers to filter by name — a fragile convention).
- Emit an explicit terminal frame for an interrupted turn, so a consumer need not infer "incomplete" from a missing `content_block_stop`.
- Emit `structured_output` progressively with a validity indicator, so a UI can show "building JSON…" and "validated" as distinct states, rather than only revealing the answer at the end.
- Publish a **machine-readable schema** (JSON Schema) for the frame envelope. The reference product documents the frame shape only in prose and in a TypeScript type, and the CLI's `stream-json` shape is not enumerated field-by-field at all.

---

## 7c.9 Evidence artifacts

All paths relative to `agent-reference-shots/areas/area-sdk-streaming-output/`.

| File | What it is | Provenance |
|---|---|---|
| `doc-streaming-output.md` | The primary page, verbatim as served at the `.md` suffix | Fetched 2026-10-21, `https://code.claude.com/docs/en/agent-sdk/streaming-output.md`, HTTP 200, 14,456 bytes |
| `doc-typescript-sdk-reference-excerpts.md` | Extracted sections from the TypeScript SDK reference: `SDKMessage`, `SDKAssistantMessage`, `SDKUserMessage`, `SDKResultMessage`, `SDKSystemMessage`, `SDKPartialAssistantMessage`, `SDKCompactBoundaryMessage`, `user_message_uuid`, `user_message_uuids` | Fetched 2026-10-21, `https://code.claude.com/docs/en/agent-sdk/typescript.md`, HTTP 200, 296,465 bytes |
| `doc-python-sdk-reference-excerpts.md` | Extracted sections from the Python SDK reference: `Message`, `AssistantMessage`, `SystemMessage`, `ResultMessage`, `StreamEvent` | Fetched 2026-10-21, `https://code.claude.com/docs/en/agent-sdk/python.md`, HTTP 200, 160,194 bytes |
| `observed-stream-event-sequence.jsonl` | The reduced, sanitized observed frame sequence (10 records) proving the S10 ordering | Derived from `agent-reference-shots/area-headless-programmatic/stream-json-events.jsonl` |

### Public documentation sources fetched

| URL | HTTP | Bytes | Used for |
|---|---|---|---|
| `https://code.claude.com/docs/en/agent-sdk/streaming-output.md` | 200 | 14,456 | Primary page — S1–S14, S19 |
| `https://code.claude.com/docs/en/agent-sdk/typescript.md` | 200 | 296,465 | S4, S6, S7, S11, S15, S16, S18 — exact TS type shapes |
| `https://code.claude.com/docs/en/agent-sdk/python.md` | 200 | 160,194 | S1, S5, S9, S11, S14, S18 — exact Python type shapes |
| `https://platform.claude.com/docs/en/build-with-claude/streaming.md` | 200 | 51,103 | S8, S13, S15 — the raw event grammar the SDK passes through |
| `https://code.claude.com/docs/en/agent-sdk/structured-outputs.md` | 200 | 21,394 | S14 — the `StructuredOutput` tool-call mechanism |
| `https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode.md` | 200 | 9,141 | Context — the *input*-mode counterpart, explicitly distinguished by the primary page |
| `https://code.claude.com/docs/llms.txt` | 200 | — | Index — confirms the canonical URL for the primary page |

**Canonical URL confirmation.** `llms.txt` line 467: `- [Stream responses in real-time](https://code.claude.com/docs/en/agent-sdk/streaming-output.md): Get real-time responses from the Agent SDK as text and tool calls stream in`.

### CLI observations

| Command | What it establishes |
|---|---|
| `claude -p "Say the single word: HELLO" --output-format stream-json --verbose --include-partial-messages` | The S10 ordering, observed frame-for-frame |
| `claude --help` | The exact `--include-partial-messages` help text (S16) |

**Sanitization note.** The observed artifact contains no secrets, no credentials, and no personal data. It retains a session UUID, a provider message ID, and a local project path in the source capture; the reduced artifact in this directory keeps the session and message identifiers (they are needed to demonstrate the `message_id` ↔ `api_message_id` join) but the source capture lives outside the report directory. No account information, no licence data, and no keychain material was accessed at any point.
