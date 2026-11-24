# UI ↔ Backend Contract (unified frontend)

**Status:** verified against source, not against a live bridge. Evidence: `src/keel/fleet/routes.py`, `src/keel/webapp.py`, `fleet-next/app/api/bridge/[...path]/route.ts`.
**Frontend:** `fleet-next`. **Backend authority:** the Python runtime. This document is the single source of truth for which endpoints the unified UI may call.

---

## 1. Transport and trust model

| Layer | Path | Notes |
|---|---|---|
| Browser (React) | `/api/bridge/<segments>` | same-origin only |
| Next.js BFF | `GET/POST/PUT/DELETE /api/bridge/[...path]` | injects `x-keel-token` server-side from `KEEL_BRIDGE_TOKEN` |
| Python bridge | `/api/fleet/<segments>` | binds `127.0.0.1`; Origin + token checked on every non-GET |
| SSE | `/api/bridge/events` | proxied through raw `node:http` (not `fetch`/undici) to survive bridge restarts |

Security properties (do not regress):

- The Keel token never reaches the browser. `sanitizeHeaders()` strips `host`, `connection`, `cookie`, `origin`, `referer`.
- Path traversal is rejected (`..` segments) in both BFF and bridge.
- Browser cookies are never forwarded upstream.
- Secrets are never returned to the browser. `providers/save` returns only a 4-character `hint`.
- Permissions, trust, approvals, secrets and execution stay in Python. The renderer never duplicates those decisions.

Configuration: `KEEL_BRIDGE_URL` and `KEEL_BRIDGE_TOKEN` on the Next.js server. Without them the BFF returns HTTP 502 `{error:"bridge_unavailable"}`. The frontend must show an honest "bridge not configured" state and a re-check action — never a fake "connected" badge.

---

## 2. Response envelope conventions

Most bridge endpoints wrap their payload; the frontend normalises with `body.<key> ?? []`:

| Endpoint family | Envelope |
|---|---|
| `bots` | `{bots:[...]}` |
| `bots/:id/rows` | `{bot_id, rows:[...]}` |
| `bots/:id/policies` | `{bot_id, policies:[...]}` |
| `bots/:id/audit` | `{bot_id, audit:[...]}` |
| `groups` | `{groups:[...]}` |
| `groups/:id` | `{group, rows:[...]}` |
| `tasks` | `{tasks:[...]}` |
| `routines` | `{routines:[...]}` |
| `library` | `{files:[...], usage_bytes?}` |
| `projects` | `{projects:[...]}` |
| `projects/:id/tree` | `{entries:[...]}` |
| `projects/:id/review` | `{is_git, status, log, diff_stat, error?}` |
| `skills` | `{skills:[...], error?}` |
| `skills/manage` | `{skills:[...]}` |
| `commands` | `{commands:[...]}` |
| `workflows` | `{workflows:[...]}` |
| `mcp/servers` | `{servers:[...]}` |
| `mcp/health` | `{health:[...]}` |
| `connectors` | connector_ops payload (list) |
| `shells` | `{shells:[...], running:n}` |
| `usage` | `{usage:{...}}` |
| `providers` | `{providers:[...], session_keys:[...]}` |
| `events` (SSE) | event frames with cursor/seq |

Errors are one of `{error, detail?}`, `{refused}`, `{raw}`, or an HTTP status. `lib/api.ts` normalises via `errMessage()` and `isBridgeUnavailable()`.

---

## 3. Endpoint catalogue (verified)

### 3.1 Agents / conversations

| Method | Path | Purpose | Request | Success |
|---|---|---|---|---|
| GET | `bots` | list agents | — | `{bots}` |
| POST | `bots` | create agent | `{name, role?, engine:"provider"\|"echo", notes?, avatar_hue?}` | `201 {bot}` |
| GET | `bots/:id/rows` | transcript | `?after=&limit=` (1–2000) | `{bot_id, rows}` |
| GET | `bots/:id/latest_seq` | stream cursor | — | `{bot_id, seq}` |
| POST | `bots/:id/messages` | send message | `{content (≤32000), mode:"build"\|"plan"\|"autopilot"\|"acceptEdits"}` | `202 {queued:true, seq}` or `409 {queued:false,busy:true}` |
| POST | `bots/:id/cancel` | stop active turn | — | `{cancelled}` |
| POST | `bots/:id/update` | edit agent | partial bot fields | `{bot}` |
| POST | `bots/:id/delete` | delete agent | — | `{deleted}` |
| POST | `bots/:id/fork` | fork transcript | `{name?, up_to_seq?}` | `201 {bot}` |
| POST | `bots/:id/rewind` | truncate transcript | `{from_seq>0}` | `{rows, deleted}` |
| POST | `bots/:id/restore` | restore rows | `{rows:[...]}` | `{restored}` |
| POST | `bots/:id/approvals/:id/decide` | approval | `{decision:"once"\|"always"\|"never"}` | `{approval, outcome}` |
| POST | `bots/:id/asks/:id/answer` | answer question | `{answer:string}` | `{ok}` |
| GET | `bots/:id/policies` | standing policies | — | `{policies}` |
| POST | `bots/:id/policies/revoke` | revoke policy | `{tool_name}` | `{revoked}` |
| GET | `bots/:id/audit` | decision history | `?limit=` (≤500) | `{audit}` |
| GET | `bots/:id/export.md` | Markdown transcript | — | `text/markdown` attachment |

### 3.2 Groups

| Method | Path | Request | Success |
|---|---|---|---|
| GET | `groups` | — | `{groups}` |
| POST | `groups` | `{name, bot_ids:[...]}` | `201 {group}` |
| GET | `groups/:id` | — | `{group, rows}` |
| GET | `groups/:id/rows` | `?after=` | `{group_id, rows}` |
| POST | `groups/:id/messages` | `{content (≤32000)}` | `202 {queued:true,seq}` or `409 {busy:true}` |
| POST | `groups/:id/delete` | — | `{deleted}` |

The backend owns duplicate/recursive trigger prevention; the UI must disable input when a round is busy and show the real 409.

### 3.3 Tasks / routines / library

Verified routes: `tasks` GET/POST, `tasks/:id` GET, `tasks/:id/events`, `tasks/reorder`, `tasks/:id/{update,assign,cancel,delete,undo}`; `routines` GET/POST, `routines/:id` GET, `routines/:id/runs`, `routines/:id/{update,enable,disable,pause,resume,run,delete}`; `library` GET/POST (upload, base64, ≤6 MB body, quota-enforced), `library/:id` GET, `library/:id/{download,preview}`, `library/:id/delete`.

Routine `run` returns `202 {queued:true}`; paused/disabled/already-running returns 409 with an explicit error.

### 3.4 Code / projects

Verified routes: `projects` GET/POST, `projects/:id/{tree,review,chat,open,remove,trust,model}` and `projects/:id/file/{read,write}`, `projects/:id/terminal/exec`, `shells`, `shells/:id/output`, `shells/:id/kill`, `shells/clear/finished`.

- Trust is **per project**, explicit, revocable. The UI must show an absolute path and exact scopes before calling `trust` — never auto-trust.
- Reviews are **read-only** git text (`status`, `log`, `diff_stat`). No apply/revert/file-diff route exists; do not build those controls.
- Terminal exec returns a **handle**; outputs are fetched by polling `shells/:id/output` only while `running`.
- There is **no browser-preview route**. Do not render a fake browser.

### 3.5 Capabilities

Verified routes: `skills`, `skills/manage`, `skills/{install,remove,enable}`; `commands`, `commands/execute`; `workflows`, `workflows/execute`; `mcp/servers`, `mcp/health`; `connectors`, `connectors/{add,test,remove}`; `providers`, `providers/catalog`, `providers/{credential,credential/clear,save,remove}`.

- Workflows and commands are **discoverable and executable**, with real results. There is no node-schema/builder API — expose a runner, not a fake builder.
- `mcp/health` starts servers, checks them, then shuts them down — a real connection check, not a cached status.
- Credentials: `credential` = session-only validation, `save` = encrypted local persistence, `remove` = delete stored key, `credential/clear` = clear session key. Only a 4-char hint is ever returned.

### 3.6 Streaming

`GET /api/fleet/events` is SSE. The bridge emits **named** `event: row\ndata: <row>\n\n` frames (`routes.py:1748`) plus `: ping` keep-alives. Named frames do **not** reach `EventSource.onmessage`, so `lib/api.ts subscribeEvents` registers both an `addEventListener("row", …)` listener and a generic `onmessage` handler, delivering each frame exactly once. Frames carry `seq` cursors. Never re-render the whole application per frame; batch updates with rAF and append only new sequence numbers.

Two method/payload details corrected during the continuation round:
- `shells/clear/finished` is a **GET** route (`routes.py:528`). The frontend previously POSTed and silently failed.
- `keep-awake` reads `{"on": true|false}` (`routes.py:773`), not `{"enabled": …}`.

---

## 4. Frontend-owned state (NOT backend state)

Persisted in `localStorage` only: theme (`keel-theme-v2`), active surface (`keel-surface`), sidebar/right-panel open state and widths (`keel-*`), active Duet tabs/layout (`keel-duet:*`), per-bot draft text (`keel-draft:<botId>`), onboarding completion/step (`keel-onboarding:*`).

Never persisted in the browser: provider keys, agent transcripts, approval decisions, audit records, file contents, trust grants.

---

## 5. Known contract gaps / dependencies

| Need | Status | Action |
|---|---|---|
| Live model round-trip | Blocked on host: no provider credentials | UI supports session/saved keys; verification can't be exercised here. Document, don't fake. |
| Browser preview server | No bridge route | UI shows honest unavailable state. |
| File-level diff / apply / revert | No bridge route beyond `review` text | Read-only review only. |
| Host-visible Electron/Tauri UI root assertion | Packaging work is a separate workstream | See UI-ARCHITECTURE.md decision record; no legacy renderer was repointed in this branch. |

No backend code was changed by the frontend workstream. If the backend workstream adds endpoints, update this document and `lib/api.ts` together.
