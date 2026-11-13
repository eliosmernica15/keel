
---

# Area 9b — MCP runtime behaviour: a live stdio server, probed end to end

**Product:** Claude Code 2.1.306 (native build, win32-x64)
**Investigated:** 2026-10-21
**Standalone report with all evidence tables:** `agent-reference-shots/area9-mcp-probe/AREA9-PROBE-EVIDENCE.md`

## Area 9b Executive summary

The Area 9 section above documents the MCP **configuration surface**. This section documents
the **runtime surface** — what the product does *after* a server connects — which was
exercised by writing a zero-dependency MCP stdio server (3 KB of plain Node, no
`npm install`) and pointing the published CLI at it with `--mcp-config`.

**Three findings change what an implementer would build.**

1. **A single malformed tool schema silences an entire server's toolset.** A server whose
   4th tool had a root-level `anyOf` combinator (and therefore no top-level
   `"type": "object"`) connected fine, served resources fine, was reported
   `{"status":"connected"}` in `system/init` — and exposed **zero** tools. The client's own
   log shows the transport rejecting the whole `tools/list` batch three times (250/500/1000 ms
   ladder) and then giving up on the tool list. The documented behaviour — exclude *one* tool,
   keep the server's others — is a *policy-layer* promise that the *transport layer* can
   pre-empt. **A clean-room implementation should validate each tool individually at load
   time; this is where it can genuinely beat the reference.**
2. **The `requiresUserInteraction` flag beats an explicit allow rule, and the refusal is
   typed.** With `permissions.allow: ["mcp__probe__always_ask"]` and the tool marked
   `_meta["anthropic/requiresUserInteraction"] = true`, the call was still refused — with the
   distinct result `MCPTool requires permission.`, paired with a `tool_reference` content
   block that still tells the model the tool *exists*. The generic denial for a non-flagged
   tool reads differently: `Claude requested permissions to use <tool>, but you haven't
   granted it yet.` Two distinct refusal shapes, and the flagged one is a *capability*
   enforced above the rule matcher.
3. **The overflow escape hatch lands outside the session's allowed working directories.**
   A 60,000-character tool result was persisted and replaced with
   `<persisted-output> Output too large (58.6KB). Full output saved to: …/tool-results/…</persisted-output>`.
   A shell `ls` of that directory was then **refused** ("Claude Code may only list files in
   the allowed working directories for this session"); only a direct `Read` of the exact path
   worked. The persisted file is the **raw MCP `content` array**, not a bare string.

Beyond those, the probe established the observable contracts for **resource tools**
(`ListMcpResourcesTool` / `ReadMcpResourceTool` / `ReadMcpResourceDirTool`, present only when a
resource-capable server is connected; reads take `{server, uri}` and return the MCP envelope
verbatim), **prompts as slash commands** (`mcp__probe__hello` appeared in the `init`
`slash_commands` array), the **`system/init` load report** (`mcp_servers[]` with
`source ∈ {user, dynamic, sdk}` and `status ∈ {pending, connected, failed}`; a separate
`mcp_server_errors[]` with categorical `type ∈ {url_missing_type, reserved_name,
invalid_config}`; the key is **omitted** when empty and a skipped server is **absent** from
`mcp_servers`), the **128-character tool-name limit** (enforced on the *fully-qualified* name —
a 150-character server-side tool name produced a 162-character wire name and was dropped with
`its name has 162 characters and the API accepts at most 128`), the **retry ladder**
(250/500/1000 ms on `tools/list`), the **negotiation "legacy peer" memo**, and the
**`WaitForMcpServers` status taxonomy** (`connected= cached= failed= pending= needsAuth=
disabled= unconfigured= unknown=`).

Two findings refine the earlier Area 9 material:

- A **`"type":"sdk"` entry is not skipped** on this host, contrary to the doc's prediction. With
  a missing `name` field it was rejected as `invalid_config` — with a *schema* error about
  `name`, not about the `sdk` type — and with a valid `name` field it **loaded** and appeared
  as `{"name":"sdksrv2","status":"failed","source":"sdk"}`. The doc says the CLI skips `sdk`
  entries; the observed behaviour is that they pass config validation and fail at the
  *connection* layer, where no in-process registration exists.
- **`ENABLE_TOOL_SEARCH` off raised the observed tool count from 28 to 236** — one additional
  server with 205 tools cost ~208 tool schemas, an ~8× growth in the schema portion of the
  request. That is the concrete motivation for deferral, and the reason a from-scratch
  implementation should make deferral the default.

## Area 9b Findings

### F9b-1 — Per-tool schema validation at load time (the highest-value clean-room target)

**Status:** OBSERVED-CLI
**Evidence:** `agent-reference-shots/area9-mcp-probe/mcp-debug-probe.log`

```
MCP server "probe": Successfully connected (transport: stdio) in 844ms
MCP server "probe": Connection established with capabilities: {"hasTools":true,"hasPrompts":true,
  "hasResources":true,"hasResourceSubscribe":false,"serverVersion":{"name":"probe-mcp","version":"0.0.1"},
  "protocolEra":"legacy","negotiatedProtocolVersion":"2025-11-25"}
MCP server "probe": tools/list failed (Invalid result for tools/list: tools.3.inputSchema.type:
  Invalid input: expected "object"); retrying in 250ms
MCP server "probe": tools/list failed (…); retrying in 500ms
MCP server "probe": tools/list failed (…); retrying in 1000ms
[ERROR] MCP server "probe" Failed to fetch tools: Invalid result for tools/list: tools.3.inputSchema.type: Invalid input: expected "object"
```

**Observed consequence:** the server reported `{"name":"probe","status":"connected","source":"dynamic"}`
in `system/init`; `ListMcpResourcesTool` and `ReadMcpResourceTool` both worked against it; and
**not one** of its tools was exposed to the model. The model diagnosed the gap itself: *"My
function schema exposes only `mcp__rea__*` tools; `mcp__probe__echo_text` … are absent, yet
`ListMcpResourcesTool` proves a `probe` server is connected."*

**INFERRED (reasoning):** the rejection happened in the MCP *client library's* result
validator, **before** Anthropic's own per-tool schema checks (documented under "Tools with
invalid input schemas" and "Tool input schemas with a root-level combinator"). The doc
describes excluding one tool and keeping the server's others; the observed transport-layer
behaviour excludes the *batch*. The doc's promise holds at the policy layer and is unreachable
in this case.

**Clean-room opportunity.** Validate each tool's `inputSchema` **individually** at load time;
exclude only the offending tool; flatten root-level `anyOf`/`oneOf`/`allOf`; and surface both
the excluded tool and the reason to the model. A server author's one bad schema should not
silence a whole integration — that is a concrete, demonstrable improvement over the reference.

### F9b-2 — Per-tool mandatory approval survives an allow rule, and returns a typed refusal

**Status:** OBSERVED-CLI (behaviour) + OBSERVED-DOC (contract)
**Docs:** https://code.claude.com/docs/en/mcp — § "Require approval for a specific tool"

Tool `always_ask` marked `_meta["anthropic/requiresUserInteraction"] = true`; allow rule
`mcp__probe__always_ask` supplied via `--settings`:

```
RESULT: [{'type': 'tool_reference', 'tool_name': 'mcp__probe__always_ask'}]
RESULT: MCPTool requires permission.
```

For comparison, a **non-flagged** tool with the same allow rule:

```
TOOL_USE: mcp__probe__echo_text {"text": "hello"}
RESULT: [{'type': 'text', 'text': 'ECHO:{"text":"hello"}'}]
```

and a non-flagged tool with **no** allow rule:

```
RESULT: Claude requested permissions to use mcp__probe__echo_text, but you haven't granted it yet.
```

**Established by observation:** (a) the allow rule is **ignored** for a flagged tool;
(b) the refusal arrives as a `tool_reference` block **plus** the distinct string
`MCPTool requires permission.`; (c) the generic denial text is a different string, so the two
refusal kinds are distinguishable by the model.

**INFERRED (reasoning):** the flag is enforced by a layer above the permission-rule matcher,
since an allow rule that would otherwise short-circuit the prompt is discarded for that tool
only; other tools from the same server are unaffected.

**Clean-room opportunity.** Model this as a per-tool *capability* (`alwaysRequiresHuman`)
evaluated before the rule matcher, with a terminal outcome set — `allow` becomes `deny` in
unattended modes. Copy the `tool_reference` + typed-error pairing: the model must learn the
tool *exists* even when the call is refused, or it will conclude the capability is missing.

### F9b-3 — MCP resources are exposed through three built-in tools, added only when a server supports them

**Status:** OBSERVED-CLI
**Docs:** https://code.claude.com/docs/en/mcp — § "Use MCP resources"

`system/init` `tools` array, with a resource-capable server connected:

```
"ListMcpResourcesTool", "ReadMcpResourceTool", "ReadMcpResourceDirTool"
```

(These three names are **absent** from the `init` `tools` array of a run with no
resource-capable server.)

```
TOOL_USE: ListMcpResourcesTool {}
RESULT: [{"name":"readme","uri":"probe://file/readme.md","mimeType":"text/markdown","server":"probe"}]

TOOL_USE: ReadMcpResourceTool {"server": "probe", "uri": "probe://file/readme.md"}
RESULT: {"contents":[{"uri":"probe://file/readme.md","mimeType":"text/markdown","text":"# Probe readme\nsanitized content"}]}
```

**Established:** `ListMcpResourcesTool` takes no arguments and returns
`{name, uri, mimeType, server}` — the `server` field disambiguates resources across servers.
`ReadMcpResourceTool` takes `{server, uri}` and returns the MCP `resources/read` envelope
**verbatim** (`{"contents":[…]}`), not re-wrapped. `ReadMcpResourceDirTool` was present but
never called — its contract is **UNKNOWN**.

**Clean-room opportunity.** A `server`-keyed read that preserves the raw MCP envelope is
minimal and interoperable; the separate directory-read tool is the tree-navigation entry point
`ListMcpResourcesTool` alone cannot provide.

### F9b-4 — MCP prompts are registered as slash commands in the `mcp__server__prompt` form

**Status:** OBSERVED-CLI
**Docs:** https://code.claude.com/docs/en/mcp — § "Use MCP prompts as commands"

```
"slash_commands": [ …, "mcp", "mcp__probe__hello" ]
```

The probe server advertised one prompt (`hello`) via `prompts/list`; it appeared as the slash
command `mcp__probe__hello` — the **full** form the doc names as its second spelling. Whether
the `/server:prompt` short form is also registered is **UNKNOWN** (not visible in `init`).

**Clean-room opportunity.** Adopting the *same* `mcp__server__prompt` spelling as the tool
prefix means one sanitisation rule covers tools, prompts, permission rules, and hook matchers.
Use the identical rule — anything outside `[A-Za-z0-9_-]` becomes `_` — everywhere.

### F9b-5 — The `system/init` event is the machine-readable MCP load report

**Status:** OBSERVED-CLI
**Docs:** https://code.claude.com/docs/en/headless — § "stream responses"

```json
"mcp_servers": [
  {"name":"rea",  "status":"pending",  "source":"user"},
  {"name":"probe","status":"connected","source":"dynamic"}
]
```

`source` observed: **`user`** (`~/.claude.json`), **`dynamic`** (`--mcp-config`), **`sdk`**.
`status` observed: `pending`, `connected`, `failed`.

`mcp_server_errors[]`, with the exact categories and messages:

| `type` | Observed message |
| - | - |
| `url_missing_type` | `Skipped — MCP server "badurl" has a "url" but no "type"; add "type": "http" (or "sse" / "ws") to this entry` |
| `reserved_name` | `"workspace" is a reserved MCP server name and was not loaded` |
| `invalid_config` | `Skipped — invalid MCP server config for "sdksrv": name: expected string, received undefined` |

**Confirmed by observation:** a skipped entry is **absent from `mcp_servers`**; the process
still **exits 0**; and the `mcp_server_errors` key is **omitted entirely** when there are no
errors.

**Refinement to the earlier Area 9 material:** a `"type":"sdk"` entry is **not** skipped on
this host. With a missing `name` field it was rejected as `invalid_config` — with a *schema*
error about `name`, not about the `sdk` type — and with a valid `name` field it **loaded** and
appeared as `{"name":"sdksrv2","status":"failed","source":"sdk"}`. The doc predicts a skip; the
observed behaviour is that `sdk` passes config validation and fails at the *connection* layer,
where no in-process registration exists. **INFERRED (reasoning):** the `sdk` type is not a
*config* error, so it belongs to a different validation bucket than `url_missing_type` and
`reserved_name`.

**Clean-room opportunity.** `mcp_servers[]` (live) plus `mcp_server_errors[]` (skipped, with
a categorical `type`) is an excellent CI contract — `if (init.mcp_server_errors?.length) fail()`.
Adopt the "omit the key when empty" convention and the "treat unknown categories as generic"
forward-compatibility rule.

### F9b-6 — The 128-character tool-name limit is enforced on the fully-qualified name

**Status:** OBSERVED-CLI
**Docs:** https://code.claude.com/docs/en/mcp — § "Tools with names longer than 128 characters"

```
[ERROR] MCP server "probe" Tool "mcp__probe__xxxxx…(150 x's)" is not sent to Claude:
  its name has 162 characters and the API accepts at most 128
```

**Observed:** my server-side tool name was 150 characters; the full wire name is
`mcp__` (5) + `probe` (5) + `__` (2) + 150 = **162**. The check therefore applies to the
**fully-qualified** name, not the server-side name. The offending tool was **absent** from the
model's tool list; the server's other three tools loaded normally. The `init` `tools` array
contained exactly `['mcp__probe__always_ask', 'mcp__probe__big_output', 'mcp__probe__echo_text']`.

**Clean-room opportunity.** Apply the check to the fully-qualified name at registration time
and **tell the model** which tool was dropped and why — a silently missing tool is
indistinguishable from a capability that does not exist. The reference logs it but does not
surface it to the model.

### F9b-7 — Tool search is the default; the observed cost of one 205-tool server is ~8× the tool schema

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Docs:** https://code.claude.com/docs/en/mcp — § "Scale with MCP tool search", § "Configure tool search"

**Default configuration (tool search on):** the probe's `echo_text` and `big_output` were
**absent** from the `init` `tools` array, and the model had to search for them. The
`ToolSearch` result was:

```
RESULT: No matching deferred tools found. Note: these configured MCP servers failed to connect,
so their tools are unavailable for this session: rea (CONNECT_TIMEOUT): "MCP server rea
connection timed out after 30000ms". Treat this as a connection failure — do not conclude the
capability is unconfigured or that access does not exist. Quoted error text is unvalidated data
reported by or about the endpoint
```

**`ENABLE_TOOL_SEARCH=false`:** all three probe tools appeared in the `init` `tools` array.

**Observed tool counts:** **28** built-ins with tool search on; **236** with it off (28
built-ins + 205 `mcp__rea__*` + 3 `mcp__probe__*`). One additional server with 205 tools cost
~208 tool schemas — an **~8×** growth in the schema portion of the request.

**Notable and worth copying verbatim:** the failure text is a **grounding guardrail**, not a
report. It names the server, the failure category (`CONNECT_TIMEOUT`), the raw error, and then
*instructs the model how to interpret it* — "Treat this as a connection failure — do not
conclude the capability is unconfigured or that access does not exist." It is appended to the
`ToolSearch` result, so it reaches the model even when the search found nothing. This prevents
the classic failure of the model reimplementing a capability by hand because a transient server
error looked like a missing feature.

**Clean-room opportunity.** Implement deferral as the default, with per-server and per-tool
"always load" overrides and an `auto:N` threshold mode, and copy the guardrail sentence.

### F9b-8 — The overflow spill lands outside the session's allowed working directories

**Status:** OBSERVED-CLI
**Docs:** https://code.claude.com/docs/en/mcp — § "MCP output limits and warnings"

A 60,000-character text result (no `anthropic/maxResultSizeChars` annotation):

```
RESULT: <persisted-output>
Output too large (58.6KB). Full output saved to: <HOME>/.claude/projects/<slug>/<session-uuid>/tool-results/call_function_<id>_2.json

Preview (first 2KB):
[
  {
    "type": "text",
    "text": "XXXXX…
```

Client debug log: `[DEBUG] Persisted tool result to …/tool-results/…json (58.6KB)`.

**Observed follow-on — the escape hatch is awkward:**

```
RESULT: ls in '…/tool-results/' was blocked. For security, Claude Code may only list files in
the allowed working directories for this session: 'C:\…\scratch-probe', 'C:/…/scratch-probe'
```

A direct `Read` of the exact path the notice gave **did** work. So the only workable route is
a direct read of a path the model must have copied from the notice.

**Observed format detail:** the persisted file is the **raw MCP `content` array**
(`[{"type":"text","text":"…"}]`), not a bare string — the model must parse a JSON array to
recover the text.

**INFERRED (reasoning):** the persist threshold is applied to the *text content* before
serialisation: 60,000 characters of `X` is ≈15k tokens, under the 25,000-token default
`MAX_MCP_OUTPUT_TOKENS` but over the 50,000-character persist threshold — so the character
threshold bites first, exactly as the doc states.

**Clean-room opportunity.** Put the spill file somewhere the session is *allowed* to read (a
per-session scratch directory inside the working tree, or grant the `tool-results` directory),
and persist in a **documented, stable** format — a bare string or `{text: …}` is easier to
consume than a raw MCP content array. Keep the absolute path in the notice; make the notice a
first-class tool-result type rather than a `<persisted-output>` tag inside prose.

### F9b-9 — The MCP client logs a retry ladder, a negotiation era, and a status taxonomy

**Status:** OBSERVED-CLI
**Evidence:** `agent-reference-shots/area9-mcp-probe/mcp-debug-probe.log`

```
MCP server "rea": remembered as a legacy peer from an earlier connect (its server/discover
  probe was answered method-not-found or not at all); skipping the probe
MCP server "probe": Starting connection with timeout of 30000ms
MCP server "probe": Successfully connected (transport: stdio) in 1498ms
MCP server "probe": Connection established with capabilities: {"hasTools":true,"hasPrompts":true,
  "hasResources":true,"hasResourceSubscribe":false,"serverVersion":{…},"protocolEra":"legacy",
  "negotiatedProtocolVersion":"2025-11-25"}
[MCP] Server "probe" connected with subscribe=false
[DEBUG] [WaitForMcpServers] waited=0ms connected=probe cached= failed= pending= needsAuth= disabled= unconfigured= unknown=
[DEBUG] MCP server "probe": Calling MCP tool: echo_text
[DEBUG] MCP server "probe": Tool 'echo_text' completed successfully in 63ms
[DEBUG] MCP server "probe": Closing MCP server stdin
[DEBUG] MCP server "probe": STDIO connection closed after 85s (cleanly)
```

**Established:** the `tools/list` retry ladder is **250 ms → 500 ms → 1000 ms**, then failure.
A **negotiation probe** is sent to an unseen server; a server answering `method-not-found` is
remembered as a **"legacy peer"** and the probe is skipped on later connects. The
`WaitForMcpServers` line enumerates every server bucketed by state — `connected= cached=
failed= pending= needsAuth= disabled= unconfigured= unknown=` — which is the internal
counterpart of the user-facing statuses (`✔ Connected`, `✘ Failed to connect`, `! Needs
authentication`, `⏸ Pending approval`, `⊘ Disabled for this project`). Shutdown is **graceful**:
stdin is closed first, then the process is reaped, then the connection cache is cleared.
Per-call duration is logged.

**INFERRED (reasoning):** the "legacy peer" memo is a per-server optimisation — a server that
cannot answer the newer-revision discovery probe is pinned to the older handshake for the
process lifetime. The `WaitForMcpServers` bucket names explain how the user-facing list can
print `⏸ Pending approval` *without* attempting a connection: approval is a separate bucket
from connection state.

**Clean-room opportunity.** Bucket servers by a single status enum rendered both for humans
and for machines; log connect timing, negotiated protocol version, and per-call duration; pin
a server's handshake once known. The difference between "MCP is broken" and "server X
timed out handshaking on 401" is worth the logging.

### F9b-10 — The project-scope trust gate, the exact status string, and the scope labels

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Docs:** https://code.claude.com/docs/en/mcp — § "Project scope", § "Server status"

A server added with `--scope project` is written to `.mcp.json` immediately but is **inert**:

```
$ claude mcp get probe-srv
probe-srv:
  Scope: Project config (shared via .mcp.json)
  Status: ⏸ Pending approval (run `claude` to approve)
```

Observed scope labels: `Local config (private to you in this project)`,
`Project config (shared via .mcp.json)`, `User config (available in all your projects)`.

**Observed:** the health check is **skipped** for a pending server and **performed** for an
approved one — the `rea` server (user scope, approved) was health-checked on both `list` and
`get` and consumed the full 30 s `MCP_TIMEOUT` before reporting
`✘ Failed to connect — MCP server "rea" connection timed out after 30000ms`. The `Issue:` line
in the detail view carried the same transport error text.

**INFERRED (reasoning):** the gate is deliberately not satisfiable by an automated run — a
repository cannot approve its own servers, which is why the status text names the exact
command a human must run.

**Clean-room opportunity.** Make the state machine explicit and machine-readable
(`pending_approval` / `connected` / `failed` / `needs_auth` / `disabled` / `rejected` /
`not_configured`) and expose it in the init event so CI can assert on it. Copy the
`list` (summary line) / `get` (detail view with `Scope:` / `Status:` / `Issue:` / `Type:`)
split exactly — it is a clean, greppable contract.

### F9b-11 — Reserved names, the invalid-config message, and the `streamable-http` alias

**Status:** OBSERVED-CLI + OBSERVED-DOC

```
$ claude mcp add --transport http workspace https://x.example.com/mcp
Cannot add MCP server "workspace": this name is reserved.

$ claude mcp add-json notype '{"url":"https://x.example.com/mcp"}' -s local
Invalid configuration: : Invalid input

$ claude mcp add-json badjson '{not json}' -s local
Invalid configuration: : Invalid input
```

**Observed:** `"streamable-http"` is accepted as an alias and **normalised to `"http"`** in
the stored config (`claude mcp get` reported `Type: http`). Removing the last project-scoped
server leaves `{"mcpServers": {}}` behind — the file is **not** deleted. A reserved name in a
loaded config becomes a `reserved_name` skip (F9b-5); the reserved set is `workspace`,
`claude-in-chrome`, `computer-use`, `Claude Preview`, `Claude Browser`.

**Observed weakness:** the invalid-config message is a Zod-style summary with an **empty
path** and a **generic** "Invalid input" — no indication of which field or what was
expected.

**Clean-room opportunity.** Report the failing path and the expected shape, e.g.
`Invalid configuration at mcpServers.foo.type: expected one of "stdio" | "http" | "sse" | "ws"`.
Validate reserved names at add time *and* list the reserved names in the error. Better still,
namespace built-in servers behind a prefix (e.g. `builtin:`) so a user-chosen legitimate name
never collides.

## Area 9b Dependency surface

| Dependency | Required for | Evidence |
| - | - | - |
| **Node.js / any host runtime** | stdio servers only — the client spawns the command | observed (the probe ran under `node`) |
| **Network egress** | `http` / `sse` / `ws` servers; OAuth discovery; `claude mcp login` | observed (`ENOTFOUND`, `CONNECT_TIMEOUT`) |
| **A model provider** | the agent loop; the model selects which MCP tool to call | observed (a non-Anthropic gateway on this host) |
| **A claude.ai account** | claude.ai connectors, Anthropic-hosted connectors, connector OAuth | **OBSERVED-DOC only** — not observable here |
| **Anthropic API access** | discovery-cache rollout, feature flags, `MCP_DISCOVERY_CACHE` default | **OBSERVED-DOC only** |
| **A local HTTP callback port** | OAuth flows (`http://localhost:PORT/callback`) | OBSERVED-DOC |
| **OS keychain / credentials file** | storing the OAuth client secret | OBSERVED-DOC |
| **A writable `~/.claude.json`** | local and user scope | observed (`File modified:` line) |

## Area 9b Limitations

- **The model on this host is not an Anthropic model.** It still chose and called MCP tools
  correctly, and tool execution is entirely client-side, so the *harness* observations hold.
  Model-side behaviour is not representative of Claude Opus 5.5 and is not claimed.
- **The probe server is a stub** — happy path only: no `list_changed`, no pagination, no
  `roots/list`, no `elicitation`, no subscriptions, no OAuth, no image content. Those paths
  are **not observed**; they remain `OBSERVED-DOC`.
- **Only the `stdio` transport was exercised end-to-end.** `http`, `sse`, and `ws` were
  configured and observed *failing* (which confirms the error surface) but never carried a
  session.
- **No interactive TTY session was used for MCP.** The `/mcp` panel, its menus, the approval
  dialog, and the `cached` / `⊘ Disabled` / `✘ Rejected` statuses are **OBSERVED-DOC** only.
- **The interactive approval dialog was not exercised** — only its non-interactive
  manifestation (`⏸ Pending approval`).
- **No subagent-scoped MCP server was configured**, so the subagent `tools` field interaction
  with MCP is **UNKNOWN**.

## Area 9b Unresolved questions (UNKNOWN)

1. The exact **`/mcp` panel layout** — rows, icons, and the contents of a server's menu. Only
   the status vocabulary is observed.
2. What the **approval dialog** looks like, and exactly what it writes on approval
   (`enabledMcpjsonServers` vs `enableAllProjectMcpServers`).
3. Whether the **`/server:prompt` short form** of an MCP prompt is registered, or only
   `/mcp__server__prompt`. Only the latter was visible in `init`.
4. The contract of **`ReadMcpResourceDirTool`** — present in the tool list, never called.
5. Whether the documented **root-level-combinator flattening** actually happens on this build:
   the transport rejected the `anyOf` schema outright (F9b-1) before the policy layer could
   flatten it, so the flattening was never exercised.
6. Whether the **persisted-file format** (raw MCP `content` array) is a guaranteed contract or
   incidental.
7. The exact interaction between **`_meta["anthropic/alwaysLoad"]`** and a server-level
   `alwaysLoad: false`.
8. Whether a **`list_changed` notification** in an interactive terminal re-sends the tool list
   in the *same* turn.
9. Where the **discovery cache** is stored and how it is keyed on disk.
10. Whether the **first-connection retry count** for HTTP (documented as three) uses the same
    250/500/1000 ms ladder observed for `tools/list`.

## Area 9b Recommended scope for an independent implementation

### Tier 1 — the parity core

1. **A transport layer** with a discriminated union `stdio | http | streamable-http | sse | ws`;
   validate `type` loudly and reject a `url`-without-`type` entry with a message naming the
   fix. (F9b-11)
2. **A config model** with three scopes and two storage files matching the reference (local +
   user in `~/.claude.json`, user keyed by project path; project in `.mcp.json`), and the same
   precedence order. (F9b-10)
3. **The `claude mcp` CLI family** with the same flag names and the `Added … / File modified:
   <path>` output pair, including the scope context that disambiguates the two scopes sharing
   `~/.claude.json`. (F9b-10, F9b-11)
4. **A trust gate** on project-scoped servers with an explicit status enum and a
   machine-readable `system/init` report. (F9b-5, F9b-10)
5. **Tool naming** with one sanitisation rule (`mcp__<server>__<tool>`, non-`[A-Za-z0-9_-]` →
   `_`) used everywhere; enforce the 128-character limit on the fully-qualified name and tell
   the model what was dropped. (F9b-4, F9b-6)
6. **Per-tool schema validation at load time** — validate each tool individually, exclude only
   the offender, flatten root-level combinators, report exclusions to the model. **This is
   where a clean-room implementation can genuinely beat the reference.** (F9b-1)
7. **Output limits with a spill escape hatch** — a token cap, a character cap, a per-tool
   override, and a persisted file the model is *allowed* to read. (F9b-8)
8. **Tool search (deferral) as the default**, with per-server and per-tool "always load"
   overrides, an `auto:N` threshold mode, and the grounding-guardrail failure text. (F9b-7)

### Tier 2 — the differentiating layer

9. **A mandatory-approval per-tool capability** evaluated *above* the rule matcher, with a
   typed refusal that still tells the model the tool exists. (F9b-2)
10. **Resources as first-class tools** — list / read / read-directory, raw MCP envelope
    preserved, owning server attached. (F9b-3)
11. **Prompts as slash commands**, reusing the tool-name prefix and sanitisation rule. (F9b-4)
12. **Observable MCP state** — a status enum rendered for humans and machines, plus debug
    logging of connect timing, negotiated protocol version, per-call duration, and the
    negotiation "legacy peer" memo. (F9b-9)
13. **A timeout taxonomy** with named, individually-tunable timers and the
    `max(60 s, tool timeout, MCP_TIMEOUT)` per-request floor. (F9b-13 in the Area 9 section)

### Tier 3 — nice to have

14. **OAuth** with dynamic client registration, `--callback-port`, pre-registered client
    id/secret, RFC 9728 → RFC 8414 discovery, `authServerMetadataUrl`, `oauth.scopes` pinning.
15. **Dynamic headers** (`headersHelper`) with an explicit credential-variable allowlist (not
    substring heuristics) and a per-connection re-run.
16. **Elicitation** in form and URL modes.
17. **The enterprise policy plane** — `managed-mcp.json`, allow/deny lists matched by URL /
    command / name.

## Area 9b Evidence artifacts

| Path | Contents |
| - | - |
| `agent-reference-shots/area9-mcp-probe/AREA9-PROBE-EVIDENCE.md` | Standalone full report for this section |
| `agent-reference-shots/area9-mcp-probe/observed-cli-commands.txt` | Full `claude mcp` help text, config-write transcripts, error paths, `system/init` skip report |
| `agent-reference-shots/area9-mcp-probe/observed-init-mcp-servers.json` | Sanitised `system/init` with `mcp_servers[]`, `mcp_server_errors[]`, the `mcp__probe__*` tools, and the MCP-derived slash commands |
| `agent-reference-shots/area9-mcp-probe/observed-probe-tool-calls.jsonl` | Sanitised `tool_use` / `tool_result` pairs: a normal call, the persist-to-disk overflow, the `requiresUserInteraction` refusal |
| `agent-reference-shots/area9-mcp-probe/mcp-debug-probe.log` | The client's own `--debug=mcp` log: connect timing, negotiation era, the `tools/list` retry ladder, the 128-char exclusion, the persist event, graceful shutdown |
| `agent-reference-shots/area9-mcp-probe/probe-mcp-server.js` | The zero-dependency MCP stdio probe server (research instrument) |
| `agent-reference-shots/area9-mcp-probe/probe-mcp-config.json` | The `--mcp-config` that points the CLI at the probe server |
| `agent-reference-shots/area9-mcp-probe/probe-allow-rules.json` | The `permissions.allow` rules used to observe the approval behaviour |

No secrets, tokens, credentials, or personal data appear in any artifact. Session UUIDs, the
IPC pipe path, the home directory, and the `pwsh` path are redacted.

**Compliance note.** No decompilation, disassembly, source-map extraction, binary
modification, credential-store access, or gateway reverse-engineering was performed. REA's
decompilation and binary-analysis facilities were deliberately **not** invoked against the
Claude Code binary — the Anthropic terms prohibit it, and doing so would destroy the
clean-room property this study requires. Every fact above comes from a public Anthropic
document, from the published CLI's own output, or from the product's own `--debug=mcp` log.
