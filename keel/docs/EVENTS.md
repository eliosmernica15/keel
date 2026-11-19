# Keel `/api/v2` event serialization

Stable, documented format for the v2 sessions surface. Events are emitted as
Server-Sent Events; each frame is one line of the form:

```
data: {"type": "...", "sessionID": "...", ...}\n\n
```

Comments (`: ping\n\n`) are emitted every 15 s on idle connections. The
connection stays open; clients stop reading after `done`.

## Event types

| `type` | Source (row kind) | Fields |
|---|---|---|
| `user` | `message` (role=user) | `sessionID`, `text`, `seq`, `ts`, optional `workdir` |
| `assistant` | `message` (role=assistant) | `sessionID`, `text`, `seq`, `ts`, `engine`, `model` |
| `token` | ephemeral *stream* frame | `sessionID`, `text`, `seq`: null |
| `tool` | `step` | `sessionID`, `name`, `status` (`running`/`done`/`error`), `detail`, `seq`, `ts` |
| `notice` | `notice` | `sessionID`, `level`, `text`, `seq`, `ts` |
| `usage` | `usage` | `sessionID`, `provider`, `model`, `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `thinking_tokens`, `cost_basis` (`unknown` — no provider-reported cost), `seq`, `ts` |
| `approval` | `approval` | `sessionID`, `approval_id`, `tool_name`, `status` (`pending`/`approved`/`denied`/`expired`), `decision`, `summary`, `explanation`, `expires_at`, `seq`, `ts` |
| `done` | `turn_end` | `sessionID`, `terminal_reason`, `duration_ms`, `num_turns`, `usage`, `seq`, `ts` |

`seq` is the monotonically increasing row id in the SQLite `rows` table; use
it as the `?since=` cursor. `token` frames are live-only and carry `seq: null`.

## Guarantees

- **Ordering**: `seq` strictly increases; replay always emits in `seq` order,
  and live frames never carry a `seq` lower than an already-emitted one.
- **Replay + live, one connection**: `GET /api/v2/sessions/:id/events?since=N`
  first returns persisted rows with `seq > N` (bounded to 10,000), then streams
  new rows and token frames. Rows arriving during the hand-off are
  de-duplicated by `seq`.
- **Approval binding**: approvals carry `approval_id` and are decided with
  `POST .../approve` or `POST .../reject` (optional `{"approval_id": "..."}`;
  with no id and exactly one pending approval, it is resolved). Deciding with
  a wrong id returns `404`; several pending approvals returns `409` and lists
  ids. `reject` denies only this call — no standing policy is created;
  `approve` allows once. Standing policies exist only via the Fleet UI/API
  (`once`/`always`/`never`).
- **MCP tools**: `mcp__server__tool` names appear in `tool` and `approval`
  events. Approval explanation says which server/tool runs. Sensitive MCP
  tools are Tier-1-gated by the same F1 broker — no MCP-only bypass exists.
  Configured servers start per turn; startup failures degrade to `notice`
  events (`mcp` icon), never a crashed turn.
- **Images**: `POST .../messages` accepts `images: [{mime, data (base64),
  name}]` — `image/png|jpeg|gif|webp`, ≤ 4 MB each, ≤ 8 images, total body
  ≤ 32 MB. Image parts are forwarded to vision-capable providers; on the
  agent path the desktop UI sends them automatically when attached.
- **Not implemented (deliberately)**: OpenCode's schema layer, plugins,
  PTY/computer use, multi-message parts, reasoning blocks over the wire.
