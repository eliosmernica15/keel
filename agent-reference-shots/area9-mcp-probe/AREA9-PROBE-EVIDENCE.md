# Area 9 — MCP: deep-probe evidence (runtime behaviour of a live MCP server)

**Product:** Claude Code 2.1.306 (native build, win32-x64)
**Host:** Windows 11 Pro 10.0.26300 · Node v24.11.0 available
**Method:** public Anthropic documentation + black-box observation of the published CLI
**Supplement to:** the Area 9 section of `agent-evidence.md`

---

## Why this addendum exists

The Area 9 section already in `agent-evidence.md` covers the *configuration surface* of MCP
(thinly, and largely `OBSERVED-DOC`). This addendum covers what happens **after a server
connects** — which the documentation describes but which nothing in the shared evidence file
had yet *executed*.

Method: I wrote a **zero-dependency MCP stdio server** (`probe-mcp-server.js`, 3 KB, plain
Node, no `npm install`) that speaks JSON-RPC 2.0 over stdin/stdout and serves
`initialize` / `tools/list` / `tools/call` / `resources/list` / `resources/read` /
`prompts/list` / `ping`. I then pointed the published CLI at it with `--mcp-config` and
observed. This is a **research instrument**, not application code, and it is the only way to
observe the runtime contract without touching the proprietary binary.

**Compliance:** no decompilation, disassembly, source-map extraction, binary modification,
credential-store access, or gateway reverse-engineering was performed. REA's decompilation and
binary-analysis facilities were deliberately **not** invoked against the Claude Code binary —
the terms prohibit it, and doing so would destroy the clean-room property this study needs.
All observations come from running the published CLI and reading its own output and its own
`--debug=mcp` log.

**Environment caveat:** this host runs against a custom `ANTHROPIC_BASE_URL` gateway serving a
non-Anthropic model. `claude doctor` reports *"Not connected to the Anthropic API
(api.anthropic.com)"*. Everything **local** (transports, tool naming, schema validation,
output limits, permission gating, resource/prompt exposure) is directly observed.
Everything **claude.ai-account-gated** (connectors, connector OAuth, Anthropic-hosted
connectors, managed settings, discovery cache rollout) is `OBSERVED-DOC` only.

---

## Claims (classification per claim)

### P1 — A single malformed tool schema kills the *entire* `tools/list` for that server

**Status:** OBSERVED-CLI
**Evidence:** `mcp-debug-probe.log`, lines around `18:08:05.559`

```
[MCP] MCP server "probe": tools/list failed (Invalid result for tools/list: tools.3.inputSchema.type: Invalid input: expected "object"); retrying in 250ms
[MCP] MCP server "probe": tools/list failed (Invalid result for tools/list: tools.3.inputSchema.type: Invalid input: expected "object"); retrying in 500ms
[MCP] MCP server "probe": tools/list failed (Invalid result for tools/list: tools.3.inputSchema.type: Invalid input: expected "object"); retrying in 1000ms
[ERROR] MCP server "probe" Failed to fetch tools: Invalid result for tools/list: tools.3.inputSchema.type: Invalid input: expected "object"
```

The server connected successfully first:

```
MCP server "probe": Successfully connected (transport: stdio) in 844ms
MCP server "probe": Connection established with capabilities: {"hasTools":true,"hasPrompts":true,"hasResources":true,"hasResourceSubscribe":false,"serverVersion":{"name":"probe-mcp","version":"0.0.1"},"protocolEra":"legacy","negotiatedProtocolVersion":"2025-11-25"}
```

`tools.3` was the 4th tool in my list — a tool whose `inputSchema` had a root-level `anyOf`
combinator and therefore no top-level `"type": "object"`. The MCP client library's *result
validator* rejected the whole `tools/list` response.

**Consequence observed:** the server was reported `connected` in `system/init`
(`{"name":"probe","status":"connected","source":"dynamic"}`) and its **resources were
fully usable** (`ListMcpResourcesTool` and `ReadMcpResourceTool` both worked), but **not one
of its tools was exposed to the model**. The model noticed the gap and said so in its own
reasoning: *"My function schema exposes only `mcp__rea__*` tools; `mcp__probe__echo_text` …
are absent, yet `ListMcpResourcesTool` proves a `probe` server is connected."*

**INFERRED (reasoning):** this is a *client-library-level* validation failure, occurring
**before** Anthropic's own per-tool schema checks (the ones documented under "Tools with
invalid input schemas" and "Tool input schemas with a root-level combinator"). The doc
describes Claude Code as excluding *one* offending tool and keeping the server's other tools
available. The observed behaviour is stricter at the transport layer and looser at the
policy layer: the transport rejects the *batch*, and the policy layer never gets a chance to
examine individual tools.

**This is the single most actionable finding in this addendum.** A clean-room implementation
can beat it: validate each tool's `inputSchema` **individually** at load time, exclude only
the offending tool, and surface both the excluded tool and the reason to the model — which is
precisely what the documentation already promises.

**Clean-room opportunity.** Do not let one server author's mistake silence a whole
integration. Per-tool validation, per-tool exclusion, and a model-facing "these N tools were
excluded and why" message are the observable contract the docs describe; the reference
implementation's transport layer visibly does not honour it in this case.

---

### P2 — The 128-character tool-name limit is enforced, with the exact count in the log

**Status:** OBSERVED-CLI
**Evidence:** `mcp-debug-probe.log`, line `18:12:08.980`

```
[ERROR] MCP server "probe" Tool "mcp__probe__xxxxx…(150 x's)" is not sent to Claude: its name has 162 characters and the API accepts at most 128
```

**Why 162:** my tool name was 150 `x` characters; the full wire name is
`mcp__` (5) + `probe` (5) + `__` (2) + 150 = **162**. The client therefore rejects on the
**full** name, not the server-side name.

**Observed:** the offending tool is simply **absent** from the model's tool list; the other
three tools from the same server loaded normally. The `init` `tools` array contained
exactly `['mcp__probe__always_ask', 'mcp__probe__big_output', 'mcp__probe__echo_text']` — the
150-character one was silently dropped, and the server's other tools were unaffected.

**This confirms the documented behaviour** ("Tools with names longer than 128 characters" →
"leaves that tool out of the tools it sends to Claude") with the exact arithmetic, and
confirms the graceful-degradation property at the *policy* layer (unlike P1, which happens at
the transport layer).

**Clean-room opportunity.** Apply the length check to the *fully-qualified* wire name at
registration time, and **tell the model** which tool was dropped and why — a silently missing
tool is indistinguishable from a capability that does not exist. The reference implementation
logs it but does not surface it to the model.

---

### P3 — `requiresUserInteraction` beats an explicit allow rule, and the deny is a *typed* tool result

**Status:** OBSERVED-CLI (behaviour) — the contract is `OBSERVED-DOC`
**Docs:** https://code.claude.com/docs/en/mcp — § "Require approval for a specific tool"

The doc states that a tool marked `_meta["anthropic/requiresUserInteraction"] = true` prompts
on every call "even in `acceptEdits`, `auto`, and `bypassPermissions` permission modes, and
doesn't offer a 'don't ask again' option for it. Allow rules that match the tool don't skip
the prompt either."

**Observed** (probe tool `always_ask`, allow rule `mcp__probe__always_ask` supplied via
`--settings`):

```
RESULT: [{'type': 'tool_reference', 'tool_name': 'mcp__probe__always_ask'}]
RESULT: MCPTool requires permission.
```

Two things are established that the docs do **not** state:

1. **The allow rule is ignored** — I explicitly allowed `mcp__probe__always_ask` and the call
   was still refused. This confirms the doc's "Allow rules that match the tool don't skip the
   prompt either" as a live, testable property, not just prose.
2. **The refusal arrives as a `tool_reference` content block plus a distinct error string.**
   The `tool_reference` block is the *deferred-tool reference* shape (the same shape the
   tool-search path uses) — it is how the client tells the model "this tool exists, see
   reference" without inlining the schema. The second result is the literal string
   `MCPTool requires permission.` — distinct from the generic permission-denied text
   (`Claude requested permissions to use <tool>, but you haven't granted it yet.`) that the
   *non-flagged* probe tools produced when I ran without allow rules.

**Observed contrast** — same server, same session, tools **not** flagged, allow rules
`["mcp__probe__echo_text","mcp__probe__big_output"]` present:

```
TOOL_USE: mcp__probe__echo_text {"text": "hello"}
RESULT: [{'type': 'text', 'text': 'ECHO:{"text":"hello"}'}]
```

and with **no** allow rule at all:

```
RESULT: Claude requested permissions to use mcp__probe__echo_text, but you haven't granted it yet.
```

**INFERRED (reasoning):** the `requiresUserInteraction` flag is enforced by a layer *above*
the permission-rule matcher, because an allow rule that would otherwise short-circuit the
prompt is discarded for that tool only. Other tools from the same server are unaffected — the
doc says so and the observation is consistent.

**Clean-room opportunity.** Model this as a per-tool *capability* (`alwaysRequiresHuman`)
evaluated before the rule matcher, with a terminal outcome set: `allow` from a rule becomes
`deny` in unattended modes. The `tool_reference` + typed-error pairing is a good design to
copy: the model needs to know the tool *exists* even when the call is refused, otherwise it
will conclude the capability is missing.

---

### P4 — A tool result over the character threshold is persisted to disk and replaced with a path

**Status:** OBSERVED-CLI
**Docs:** https://code.claude.com/docs/en/mcp — § "MCP output limits and warnings"

**Observed** (probe tool `big_output` returning 60,000 `X` characters; no
`anthropic/maxResultSizeChars` annotation):

```
RESULT: <persisted-output>
Output too large (58.6KB). Full output saved to: <HOME>/.claude/projects/<slug>/<session-uuid>/tool-results/call_function_<id>_2.json

Preview (first 2KB):
[
  {
    "type": "text",
    "text": "XXXXXXXX…
```

and in the client's own debug log:

```
[DEBUG] Persisted tool result to <HOME>/.claude/projects/<slug>/<session-uuid>/tool-results/call_function_<id>_2.json (58.6KB)
```

**Notable and not in the docs:** the file is written **in the tool-result JSON envelope
form** — the persisted file is `[{"type":"text","text":"…"}]`, i.e. the raw MCP `content`
array — **not** a bare string. The model must therefore parse a JSON array to recover the
text. The inline replacement names the file and shows a 2 KB preview, which is the
instruction to go read it.

**INFERRED (reasoning):** the persist threshold is applied to the *text content* before
serialisation, since 60,000 characters (≈15k tokens for `X`) is under the 25,000-token
default `MAX_MCP_OUTPUT_TOKENS` but over the 50,000-character persist threshold. The
character threshold therefore bites first for a single large text block — which is exactly
what the doc says ("successful text results longer than 50,000 characters are saved to a
file regardless of this variable").

**Observed follow-on:** the model tried to read the persisted file and hit a **working-
directory restriction**, because the `tool-results` directory lives under `~/.claude/projects/`,
outside the session's allowed working directories:

```
RESULT: ls in '…/tool-results/' was blocked. For security, Claude Code may only list files in
the allowed working directories for this session: 'C:\…\scratch-probe', 'C:/…/scratch-probe'
```

Reading the file by absolute path with the `Read` tool *did* work. So the escape hatch is
real but awkward: a shell `ls` of the directory is refused, and the only workable route is a
direct `Read` of the exact path the notice gave.

**Clean-room opportunity.** Put the spill file somewhere the session is *allowed* to read
(a per-session scratch directory inside the working tree, or grant the `tool-results`
directory), and keep the persisted payload in a **documented, stable format** — a bare string
or a `{text: …}` object is easier to consume than a raw MCP content array. Also state the
absolute path plainly in the notice (it does) and make the notice a first-class tool-result
type rather than a `<persisted-output>` tag inside prose.

---

### P5 — MCP **resources** are exposed through three dedicated built-in tools, with the server name attached

**Status:** OBSERVED-CLI
**Docs:** https://code.claude.com/docs/en/mcp — § "Use MCP resources"

The doc describes resources as `@`-mentionable (`@server:protocol://resource/path`) and says
"Claude Code automatically provides tools to list and read MCP resources when servers support
them".

**Observed** — three new built-in tools appear in the `system/init` `tools` array **only when
an MCP server that supports resources is connected**:

```
"ListMcpResourcesTool", "ReadMcpResourceTool", "ReadMcpResourceDirTool"
```

(Compare the baseline `init` from a run with **no** resource-capable server: those three
names are absent.)

Their wire behaviour:

```
TOOL_USE: ListMcpResourcesTool {}
RESULT: [{"name":"readme","uri":"probe://file/readme.md","mimeType":"text/markdown","server":"probe"}]

TOOL_USE: ReadMcpResourceTool {"server": "probe", "uri": "probe://file/readme.md"}
RESULT: {"contents":[{"uri":"probe://file/readme.md","mimeType":"text/markdown","text":"# Probe readme\nsanitized content"}]}
```

**Established by observation:**
- `ListMcpResourcesTool` takes **no arguments** and returns a flat array of
  `{name, uri, mimeType, server}` — the `server` field identifies the owning server, which
  is how one server's resource is disambiguated from another's.
- `ReadMcpResourceTool` takes `{server, uri}` and returns the MCP `resources/read` result
  envelope **verbatim** (`{"contents":[…]}`) — Claude Code does not re-wrap it.
- `ReadMcpResourceDirTool` was present in the tool list but was not exercised in this
  session; its contract is **UNKNOWN**.

**INFERRED (reasoning):** because these tools are *built-in* rather than per-server tools,
the client must translate a resource read into the model's normal tool-call flow. Reusing the
raw MCP envelope keeps the client simple and makes the server's `mimeType` meaningful to the
model.

**Clean-room opportunity.** The three-tool split (list / read / read-directory) is a good
idiomatic design — a `server`-keyed read that keeps the raw MCP envelope is minimal and
interoperable. The `ReadMcpResourceDirTool` is worth copying as the tree-navigation entry
point that `ListMcpResourcesTool` alone cannot provide.

---

### P6 — MCP **prompts** are registered as slash commands, with the full `mcp__server__prompt` form

**Status:** OBSERVED-CLI
**Docs:** https://code.claude.com/docs/en/mcp — § "Use MCP prompts as commands"

The doc states that Claude Code lists each MCP prompt as `/servername:promptname (MCP)` and
that typing `/mcp__servername__promptname` also runs it.

**Observed** — in the `system/init` `slash_commands` array, alongside the built-in `mcp`
command:

```
"slash_commands": [ … "mcp", "mcp__probe__hello" ]
```

The probe server advertised one prompt (`hello`) via `prompts/list`, and it appeared as the
slash command `mcp__probe__hello` — the **full form**, exactly as the doc's second spelling.
(The `/server:prompt` short form was not separately visible in `slash_commands`; the
colon-spelled alias is therefore **UNKNOWN** from this run.)

**Clean-room opportunity.** Registering prompts as slash commands is a clean, discoverable
surface, and adopting the *same* `mcp__server__prompt` spelling as the tool-name prefix means
one sanitisation rule covers tools, prompts, permission rules, and hook matchers. Adopt the
identical rule — anything outside `[A-Za-z0-9_-]` becomes `_` — and use it everywhere.

---

### P7 — The `system/init` event is a machine-readable MCP load report, with an `mcp_server_errors` array

**Status:** OBSERVED-CLI
**Docs:** https://code.claude.com/docs/en/headless — § "stream responses"

**Observed** in `system/init`:

```json
"mcp_servers": [
  {"name":"rea",  "status":"pending",  "source":"user"},
  {"name":"probe","status":"connected","source":"dynamic"}
]
```

`source` values observed: **`user`** (from `~/.claude.json`), **`dynamic`** (from
`--mcp-config`), **`sdk`** (an in-process `type:"sdk"` entry). The `status` values observed:
`pending`, `connected`, `failed`.

**Observed** error array (the skipped-config channel), with the exact skip categories and
messages reproduced in `observed-cli-commands.txt`:

| `type` | Observed message |
| - | - |
| `url_missing_type` | `Skipped — MCP server "badurl" has a "url" but no "type"; add "type": "http" (or "sse" / "ws") to this entry` |
| `reserved_name` | `"workspace" is a reserved MCP server name and was not loaded` |
| `invalid_config` | `Skipped — invalid MCP server config for "sdksrv": name: expected string, received undefined` |

**Key property confirmed by observation:** a skipped entry is **absent from `mcp_servers`**,
and the process still **exits 0**. The `mcp_server_errors` key is **omitted entirely** when
there are no errors.

**Notable, and NOT in the docs:** a `"type":"sdk"` entry is **not** rejected for being an
SDK type. With a missing `name` field it was rejected as `invalid_config` (with a *schema*
error about `name`, not about the `sdk` type). With a valid `name` field it **loaded** and
appeared as `{"name":"sdksrv2","status":"failed","source":"sdk"}`. So on this host the
documented rule — "Only an SDK host application … can register an in-process `type: "sdk"`
server. Claude Code skips a `"type": "sdk"` entry" — did **not** manifest; the entry was
accepted into the session and then failed to connect as an SDK in-process server.

**INFERRED (reasoning):** the `sdk` type is not a *config* error, so it passes config
validation and fails at the *connection* layer, where no in-process registration exists.
This is consistent with the doc's intent (the CLI is not an SDK host) but differs in the
mechanism: the doc predicts a skip, the observed behaviour is a failed connect. On a host
that *is* an SDK host, the entry would presumably connect.

**Clean-room opportunity.** A `system/init` event carrying both `mcp_servers[]` (live) and
`mcp_server_errors[]` (skipped, with a categorical `type`) is an excellent CI contract —
`if (init.mcp_server_errors?.length) fail()`. Adopt the "omit the key when empty" convention
so a clean run has no noise. Adopt the categorical `type` with a documented
"treat unknown categories as generic" rule for forward compatibility.

---

### P8 — The MCP client logs a **retry ladder** and a **negotiation era** at DEBUG level

**Status:** OBSERVED-CLI
**Evidence:** `mcp-debug-probe.log`

```
MCP server "rea": remembered as a legacy peer from an earlier connect (its server/discover
  probe was answered method-not-found or not at all); skipping the probe
MCP server "probe": Starting connection with timeout of 30000ms
MCP server "probe": Successfully connected (transport: stdio) in 1498ms
MCP server "probe": Connection established with capabilities: {"hasTools":true,"hasPrompts":true,
  "hasResources":true,"hasResourceSubscribe":false,"serverVersion":{"name":"probe-mcp","version":"0.0.1"},
  "protocolEra":"legacy","negotiatedProtocolVersion":"2025-11-25"}
[MCP] Server "probe" connected with subscribe=false
[DEBUG] [WaitForMcpServers] waited=0ms connected=probe cached= failed= pending= needsAuth= disabled= unconfigured= unknown=
[DEBUG] MCP server "probe": Calling MCP tool: echo_text
[DEBUG] MCP server "probe": Tool 'echo_text' completed successfully in 63ms
[DEBUG] MCP server "probe": Closing MCP server stdin
[DEBUG] MCP server "probe": STDIO connection closed after 85s (cleanly)
[DEBUG] MCP server "probe": Cleared connection cache for reconnection
```

**Established by observation:**
- The **`tools/list` retry ladder is 250 ms → 500 ms → 1000 ms**, then failure. (See P1.)
- A **negotiation probe** is sent to a server the client has not seen before, and a server
  that answers `method-not-found` (or not at all) is remembered as a **"legacy peer"** and
  the probe is skipped for it on later connections. The negotiated protocol version and the
  "era" (`legacy`) are both logged.
- A **`WaitForMcpServers` summary line** enumerates the session's servers bucketed by state:
  `connected=`, `cached=`, `failed=`, `pending=`, `needsAuth=`, `disabled=`,
  `unconfigured=`, `unknown=`. This is the internal status taxonomy, and it *is* the
  observable surface behind the user-facing statuses (`✔ Connected`, `✘ Failed to connect`,
  `! Needs authentication`, `⏸ Pending approval`, `⊘ Disabled for this project`).
- Shutdown is **graceful**: stdin is closed first, then the process is reaped
  ("STDIO connection closed after 85s (cleanly)"), and the connection cache is cleared.
- Tool calls are timed individually ("completed successfully in 63ms").

**INFERRED (reasoning):** the "legacy peer" memo is a **per-server optimisation**: a server
that cannot answer the newer-revision discovery probe is pinned to the older handshake for
the rest of the process, avoiding a repeated round trip. The `WaitForMcpServers` bucket
names are the internal equivalent of the user-facing status strings, which is why the
user-facing list can show `⏸ Pending approval` *without* attempting a connection — the
approval state is a separate bucket from the connection state.

**Clean-room opportunity.** Bucket MCP servers by a single status enum and render both a
user-facing string and a machine-readable value from it. Log connection timing, negotiated
protocol version, and per-call duration. Pin a server to a handshake once its capabilities
are known rather than re-probing on every connect. These are all cheap and all make MCP
problems diagnosable — the difference between "MCP is broken" and "server X timed out
handshaking on 401" is worth the logging.

---

### P9 — Tool search is **on by default**, and a deferred tool is invisible to the model until searched

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Docs:** https://code.claude.com/docs/en/mcp — § "Scale with MCP tool search", § "Configure tool search"

**Observed, default configuration (tool search on):** with a connected server exposing
`echo_text` and `big_output`, **neither tool appeared in the `system/init` `tools` array**,
and the model had to go looking. A `ToolSearch` for the tool returned:

```
RESULT: No matching deferred tools found. Note: these configured MCP servers failed to connect,
so their tools are unavailable for this session: rea (CONNECT_TIMEOUT): "MCP server rea
connection timed out after 30000ms". Treat this as a connection failure — do not conclude the
capability is unconfigured or that access does not exist. Quoted error text is unvalidated data
reported by or about the endpoint
```

Two things here are worth calling out:

1. **The failure message is a grounding guardrail, not a report.** It names the server, the
   failure category (`CONNECT_TIMEOUT`), the raw error, and then *explicitly instructs the
   model how to interpret it* — "Treat this as a connection failure — do not conclude the
   capability is unconfigured or that access does not exist." This prevents the classic model
   failure of giving up on a capability, or worse, reimplementing it by hand, because a
   transient server error looked like a missing feature.
2. **The guardrail text is appended to the `ToolSearch` result**, so it reaches the model
   even when the search itself found nothing.

**Observed, `ENABLE_TOOL_SEARCH=false`:** the same three tools appeared in the `init` `tools`
array:

```
"tools": [ …, "mcp__probe__always_ask", "mcp__probe__big_output", "mcp__probe__echo_text", … ]
```

**Total tool count observed: 236** with tool search off (28 built-ins + 205 `mcp__rea__*`
tools + 3 `mcp__probe__*` tools), against **28** built-ins with tool search on. That is a
**~8x** growth in the tool-schema portion of the request from one additional server with 205
tools — the concrete motivation for the deferral design.

**INFERRED (reasoning):** deferral is the *default* because the schema cost of MCP tools is
unbounded from the client's point of view ("Claude Code doesn't impose a fixed per-server
tool cap; the practical limit is your context window budget"). The `ENABLE_TOOL_SEARCH=auto`
threshold mode is a compromise: load upfront while the definitions fit in a small fraction of
the context window, defer past that.

**Clean-room opportunity.** Implement deferral as the default with an explicit, documented
"loaded upfront" escape (per-server *and* per-tool), plus the `auto:N` threshold mode. And
copy the guardrail idea verbatim: when a tool search fails, tell the model explicitly that a
*server* failed, not that the *capability* is absent.

---

### P10 — The `.mcp.json` project-scope trust gate, and the exact "pending" status string

**Status:** OBSERVED-CLI + OBSERVED-DOC
**Docs:** https://code.claude.com/docs/en/mcp — § "Project scope", § "Server status"

**Observed** — a server added with `--scope project` is written to `.mcp.json` immediately but
is **inert**:

```
$ claude mcp get probe-srv
probe-srv:
  Scope: Project config (shared via .mcp.json)
  Status: ⏸ Pending approval (run `claude` to approve)
```

The same status is rendered in `claude mcp list` (the `list` and `get` help text both state:
*"Unapproved .mcp.json servers are shown as ⏸ Pending approval and not connected to; approved
servers are health-checked unless disabled for this project."*).

**Observed scope strings:** `Local config (private to you in this project)`,
`Project config (shared via .mcp.json)`, `User config (available in all your projects)`.

**Observed** — the health check is *skipped* for a pending server, and performed for an
approved one. The `rea` server (user scope, approved) was health-checked on both `list` and
`get` and took the full 30-second `MCP_TIMEOUT` before reporting
`✘ Failed to connect — MCP server "rea" connection timed out after 30000ms`.

**INFERRED (reasoning):** the approval gate is deliberately *not* a permission prompt that
could be satisfied by an automated run. A repository cannot approve its own servers — the
approval must come from a human in an interactive session, which is why the docs tie it to
workspace trust and why the status text names the exact command to run.

**Clean-room opportunity.** Keep the gate, but make the state machine explicit and
machine-readable (`pending_approval` / `connected` / `failed` / `needs_auth` / `disabled` /
`rejected` / `not_configured`) and expose it in the init event so CI can assert on it. The
`claude mcp list` / `claude mcp get` split — a summary line versus a detail view with
`Scope:` / `Status:` / `Issue:` / `Type:` fields — is a clean, greppable contract worth
copying exactly.

---

### P11 — The full `claude mcp` command surface, with exact flag names

**Status:** OBSERVED-CLI
**Evidence:** `observed-cli-commands.txt` (full help text captured)

| Command | Purpose | Notable flags |
| - | - | - |
| `claude mcp add <name> <commandOrUrl> [args...]` | add a server | `-t/--transport` (stdio\|sse\|http — **no `ws`**), `-e/--env`, `-H/--header`, `-s/--scope` (local\|user\|project, default `local`), `--client-id`, `--client-secret`, `--callback-port` |
| `claude mcp add-json <name> <json>` | add from a JSON string | `-s/--scope`, `--client-secret` |
| `claude mcp add-from-claude-desktop` | import from Claude Desktop | `--scope user` (Mac and WSL only) |
| `claude mcp get <name>` | detail view | — |
| `claude mcp list` | summary + health check | — |
| `claude mcp login <name>` | run the OAuth flow | `--no-browser` |
| `claude mcp logout <name>` | clear stored OAuth credentials | — |
| `claude mcp remove <name>` | remove a server | `-s/--scope` |
| `claude mcp reset-project-choices` | clear `.mcp.json` approvals | — |
| `claude mcp serve` | run Claude Code *as* an MCP server | `-d/--debug`, `--verbose` |

**Observed** — every mutating command prints a human line and then a `File modified:` line
naming the exact file it wrote:

```
Added stdio MCP server probe-srv with command: node -e 0 to project config
File modified: <CWD>/.mcp.json
```

```
Added HTTP MCP server aliasprobe with URL: https://x.example.com/mcp to local config
File modified: <HOME>/.claude.json [project: <CWD>]
```

**Observed** — the `File modified:` line names the *scope context* too
(`[project: <CWD>]` for a local-scope write), which disambiguates the two scopes that share
the `~/.claude.json` file.

**Clean-room opportunity.** The `Added … / File modified: <path>` pair is a good machine- and
human-readable convention; add the scope context as the reference does, because local and
user scope write the *same file* and would otherwise be indistinguishable.

---

### P12 — Reserved names, and the invalid-`type` config error message

**Status:** OBSERVED-CLI + OBSERVED-DOC

**Observed** — the CLI rejects a reserved name at *add* time:

```
$ claude mcp add --transport http workspace https://x.example.com/mcp
Cannot add MCP server "workspace": this name is reserved.
```

**Observed** — the reserved names documented are `workspace`, `claude-in-chrome`,
`computer-use`, `Claude Preview`, `Claude Browser`; a config using one is **skipped at load
time** with `type: "reserved_name"` (P7).

**Observed** — a JSON entry with a `url` and no `type` is a **hard config error** at add
time (not a silent skip):

```
$ claude mcp add-json notype '{"url":"https://x.example.com/mcp"}' -s local
Invalid configuration: : Invalid input
```

and at *load* time it becomes the `url_missing_type` skip (P7) with the actionable message
`add "type": "http" (or "sse" / "ws") to this entry`.

**Observed** — malformed JSON at add time: `Invalid configuration: : Invalid input`. The
message is a Zod-style validation summary with an **empty path** and a **generic** "Invalid
input" — a real usability weakness, and an easy thing to beat.

**Observed** — `"streamable-http"` is accepted as an alias and **normalised to `"http"`** in
the stored config (`claude mcp get` showed `Type: http`).

**Clean-room opportunity.** Report the failing JSON path and the expected shape, e.g.
`Invalid configuration at mcpServers.foo.type: expected one of "stdio" | "http" | "sse" | "ws"`.
Also validate reserved names at add time with the *list* of reserved names, and — better —
namespace built-in servers (e.g. reserve a `builtin:` prefix) so the check never fires on a
user-chosen legitimate name.

---

### P13 — The MCP timeout ladder, from the doc plus the observed 30-second connect timeout

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Docs:** https://code.claude.com/docs/en/mcp — § "Managing your servers" (Tips), § "MCP output limits and warnings"
**Env vars:** https://code.claude.com/docs/en/env-vars

| Timer | Env var / field | Default | Observed |
| - | - | - | :- |
| Server startup (connect) | `MCP_TIMEOUT` | 30 000 ms | **yes** — "connection timed out after 30000ms" |
| Tool execution (wall clock) | `MCP_TOOL_TIMEOUT` | 100 000 000 ms (~28 h) | not exercised |
| Per-server tool timeout | `timeout` in the server entry (ms) | overrides the env var; values < 1000 ignored | not exercised |
| Per-request timer (HTTP/SSE/connector only) | greatest of 60 s, the tool timeout, and `MCP_TIMEOUT` | 60 s | not exercised |
| Idle timeout (no response, no progress) | `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` | 300 000 ms network / 1 800 000 ms stdio | not exercised |
| Auto-background threshold | `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS` | 120 000 ms (2 min) | not exercised |
| Output warning | — | 10 000 tokens | not exercised |
| Output limit | `MAX_MCP_OUTPUT_TOKENS` | 25 000 tokens | not exercised |
| Persist-to-disk threshold | — | 50 000 characters | **yes** (P4) |
| Per-tool override | `_meta["anthropic/maxResultSizeChars"]` | ceiling 500 000 chars | not exercised |
| Startup batch wait | `MCP_CONNECT_TIMEOUT_MS` | 5 000 ms | not exercised |
| Blocking startup | `MCP_CONNECTION_NONBLOCKING` | non-blocking (0 = wait) | not exercised |

**Observed** — the *default* connect timeout is confirmed twice, from two different surfaces:
the `claude mcp list` health check and the `claude mcp get` detail view both reported
`connection timed out after 30000ms`, and the debug log recorded
`Starting connection with timeout of 30000ms`.

**Clean-room opportunity.** A single timeout *taxonomy* with named, individually-tunable
timers, each documented with its default and its scope (global / per-server / per-request),
is the observable contract. Note the subtlety worth copying: the per-request timer for
remote transports is `max(60 s, tool timeout, MCP_TIMEOUT)` — a floor, not a ceiling — and
the 28-hour default deliberately does *not* participate in that comparison.

---

## Dependency surface

| Dependency | Required for | Evidence |
| - | - | - |
| **Node.js (or any runtime)** on the host | stdio servers only — Claude Code spawns the command | observed (the probe server ran under `node`) |
| **Network egress** | `http` / `sse` / `ws` servers; OAuth discovery; `claude mcp login` | observed (connect attempts, `ENOTFOUND`) |
| **A model provider** | the agent loop; the model chooses which MCP tool to call | observed (this host used a non-Anthropic gateway) |
| **A claude.ai account** | claude.ai connectors, Anthropic-hosted connectors, connector OAuth | **OBSERVED-DOC only** — not observable here |
| **Anthropic API access** | discovery-cache rollout, feature flags, `MCP_DISCOVERY_CACHE` default | **OBSERVED-DOC only** |
| **A local HTTP callback port** | OAuth flows | OBSERVED-DOC (`http://localhost:PORT/callback`) |
| **OS keychain / credentials file** | storing the OAuth client secret | OBSERVED-DOC |
| **A writable `~/.claude.json`** | local and user scope | observed (the `File modified:` line) |

---

## Limitations of this investigation

- **The model on this host is not an Anthropic model.** The model still chose and called MCP
  tools correctly, and the tool-execution path is entirely client-side, so the *harness*
  observations hold. But model-side behaviour (which tool the model picks, how it reacts to a
  failure) is not representative of Claude Opus 5.5 and is not claimed.
- **The probe server is a stub.** It implements the happy path only: no `list_changed`
  notifications, no pagination, no `roots/list`, no `elicitation`, no resources with
  subscriptions, no OAuth, no image content. Those paths are **not observed** here; they
  remain `OBSERVED-DOC`.
- **Only the `stdio` transport was exercised end-to-end.** `http`, `sse`, and `ws` were
  configured and observed *failing to connect* (which confirms the error surface) but never
  carried a real session.
- **No interactive TTY session was used for MCP.** The `/mcp` panel, its menus, the approval
  dialog, and the `cached` / `⊘ Disabled` / `✘ Rejected` statuses are **OBSERVED-DOC** only.
- **The interactive approval prompt for `.mcp.json` servers was not exercised** — only its
  non-interactive manifestation (`⏸ Pending approval`).
- **No subagent-scoped MCP server was configured**, so the subagent `tools` field interaction
  with MCP is **UNKNOWN**.

---

## Unresolved questions (UNKNOWN)

1. What is the exact **`/mcp` panel layout** — which rows, which icons, what the server menu
   contains? Only its status vocabulary is observed.
2. What does the **approval dialog** for a project-scoped `.mcp.json` server look like, and
   what exactly does it write on approval (`enabledMcpjsonServers` vs `enableAllProjectMcpServers`)?
3. Is the `/server:prompt` **short form** of an MCP prompt actually registered, or only
   `/mcp__server__prompt`? Only the latter was observed in `init`.
4. What is the contract of **`ReadMcpResourceDirTool`**? Present in the tool list, never called.
5. Does the **root-level-combinator flattening** the docs describe actually happen on this
   build, or is the doc aspirational? The reference client's *transport* rejected my
   `anyOf` schema outright (P1) before the policy layer could flatten it — so the flattening
   was never exercised.
6. What is the exact **persisted-file format** contract — is the raw MCP `content` array
   guaranteed, or incidental? (P4 observed it as a raw array.)
7. How does **`_meta["anthropic/alwaysLoad"]`** interact with a server-level
   `alwaysLoad: false` in practice? The doc states the server-level setting can override the
   tool-level one, but that override is a `false` value, not an override *of* a tool's `true`.
8. What happens on a **`list_changed` notification** in an interactive terminal, exactly — is
   the tool list re-sent in the *same* turn?
9. How is **`MCP_DISCOVERY_CACHE`** storage keyed and where does it live on disk? Only the
   `cached` status string and the `MCP_DISCOVERY_CACHE*` env vars are documented.
10. What is the exact **retry count and backoff** for a *first* HTTP connection (the doc says
    three retries) versus the `tools/list` ladder I observed (250/500/1000 ms)? Are they the
    same ladder?

---

## Recommended scope for an independent implementation (Area 9)

### Tier 1 — the parity core (build these first)

1. **A transport layer** with a discriminated union: `stdio | http | streamable-http | sse | ws`.
   Validate `type` loudly; **reject a `url`-without-`type` entry with a message that names
   the fix** rather than dropping it. (P1, P12)
2. **A config model** with three scopes and two storage files, matching the reference:
   local + user in `~/.claude.json` (user keyed by project path), project in `.mcp.json`.
   Expose the same precedence order. (P10, P11)
3. **The `claude mcp` CLI family** — `add`, `add-json`, `get`, `list`, `login`, `logout`,
   `remove`, `reset-project-choices`, `serve`, `add-from-claude-desktop` — with the same flag
   names, and the `Added … / File modified: <path>` output pair. (P11)
4. **A trust gate** on project-scoped servers with the status vocabulary
   (`pending_approval`, `connected`, `failed`, `needs_auth`, `disabled`, `rejected`,
   `not_configured`) and a machine-readable `system/init` report. (P7, P10)
5. **Tool naming** with one sanitisation rule used everywhere: `mcp__<server>__<tool>`,
   non-`[A-Za-z0-9_-]` → `_`. Enforce the 128-character limit on the **fully-qualified** name
   and **tell the model** what was dropped. (P2, P6)
6. **Per-tool schema validation at load time** — validate each tool individually against your
   model API's constraints, exclude only the offending tool, flatten root-level
   `anyOf`/`oneOf`/`allOf`, and report exclusions to the model. **This is where the reference
   implementation is weakest and a clean-room build can genuinely beat it.** (P1)
7. **Output limits with a spill escape hatch** — a token cap, a character cap, a per-tool
   override, and a persisted file the model is *allowed* to read. (P4)
8. **Tool search (deferral) as the default**, with a per-server and per-tool "always load"
   override, an `auto:N` threshold mode, and — importantly — the **grounding guardrail text**
   on failure that says "the server failed, not the capability". (P9)

### Tier 2 — the differentiating layer

9. **A mandatory-approval per-tool capability** (`alwaysRequiresHuman`) evaluated *above* the
   rule matcher, with a typed refusal that still tells the model the tool exists. (P3)
10. **Resources as first-class tools** — list / read / read-directory, with the raw MCP
    envelope preserved and the owning server attached. (P5)
11. **Prompts as slash commands**, reusing the tool-name prefix and the same sanitisation
    rule. (P6)
12. **Observable MCP state** — a status enum rendered both for humans and for machines; debug
    logging of connect timing, negotiated protocol version, per-call duration, and the
    negotiation "legacy peer" memo. (P8)
13. **A timeout taxonomy** with named, individually-tunable timers, and the
    `max(60 s, tool timeout, MCP_TIMEOUT)` per-request floor. (P13)

### Tier 3 — nice to have

14. **OAuth** with dynamic client registration, `--callback-port` /
    `http://localhost:PORT/callback`, pre-registered client id/secret, RFC 9728 →
    RFC 8414 discovery, `authServerMetadataUrl` override, and `oauth.scopes` pinning.
15. **Dynamic headers** (`headersHelper`) with an explicit credential-variable allowlist
    (not substring heuristics) and a per-connection re-run.
16. **Elicitation** in form and URL modes.
17. **The enterprise policy plane** — `managed-mcp.json`, allow/deny lists matched by URL /
    command / name, and the "managed document may not name a program" invariant.

---

## Evidence artifacts

| Path | Contents |
| - | - |
| `agent-reference-shots/area9-mcp-probe/observed-cli-commands.txt` | Full `claude mcp` help text, config-write transcripts, error paths, `system/init` skip report |
| `agent-reference-shots/area9-mcp-probe/observed-init-mcp-servers.json` | Sanitised `system/init` with `mcp_servers[]`, `mcp_server_errors[]`, the `mcp__probe__*` tools, and the MCP-derived slash commands |
| `agent-reference-shots/area9-mcp-probe/observed-probe-tool-calls.jsonl` | Sanitised `tool_use` / `tool_result` pairs: a normal call, the persist-to-disk overflow, and the `requiresUserInteraction` refusal |
| `agent-reference-shots/area9-mcp-probe/mcp-debug-probe.log` | The client's own `--debug=mcp` log: connect timing, negotiation era, the `tools/list` retry ladder, the 128-char exclusion, the persist event, graceful shutdown |
| `agent-reference-shots/area9-mcp-probe/probe-mcp-server.js` | The zero-dependency MCP stdio probe server (research instrument) |
| `agent-reference-shots/area9-mcp-probe/probe-mcp-config.json` | The `--mcp-config` that points the CLI at the probe server |
| `agent-reference-shots/area9-mcp-probe/probe-allow-rules.json` | The `permissions.allow` rules used to observe the approval behaviour |

No secrets, tokens, credentials, or personal data appear in any artifact. Session UUIDs, the
IPC pipe path, the home directory, and the `pwsh` path are redacted.
