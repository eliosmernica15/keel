# Claude Code — Area #9 Evidence: MCP Servers and External Tool Connection

**Investigated product:** Claude Code 2.1.306 (native build, win32-x64), `C:\Users\Admin\.local\bin\claude.exe`
**Investigated:** 2026-10-21
**Area owner scope:** MCP transports, `.mcp.json`, `claude mcp` command surface, OAuth, tool naming, resources/prompts, claude.ai connectors.

---

## 0. Method and compliance boundary (read first)

Claude Code is proprietary and closed source. Anthropic's Consumer ToS §3 and Commercial ToS §D.4 prohibit
decompiling, reverse engineering, or disassembling the Services, and the docs state "The Claude Code binary must
not be modified."

**Therefore the REA reverse-engineering toolset (which is available in this session as `mcp__rea__*`) was NOT
used against the Claude Code binary.** No binary was opened, no JavaScript bundle was extracted, no source map
was dumped, no credential store or keychain was read, and no private account data was accessed. REA remains
available and appropriate for artifacts where inspection is licensed; it is simply not authorized for this
target.

What was permitted and used:

| Source | Used | Classification tag |
| - | - | - |
| Public Anthropic documentation at `code.claude.com/docs/en/...` | Yes | `OBSERVED-DOC` |
| The published CLI's own user-facing help and inspection surfaces (`claude --help`, `claude mcp --help`, `claude mcp list`, `claude mcp get`, `claude mcp add`, `claude mcp add-json`, `claude mcp serve`, `claude plugin --help`, `claude plugin validate`, `claude doctor`, `claude --debug=mcp`) | Yes | `OBSERVED-CLI` |
| Binary decompilation / de-minification / source maps | **No** | prohibited |
| Credential stores, keychains, licence files, private account data | **No** | prohibited |
| Reverse-engineering the Anthropic API gateway to reproduce private APIs | **No** | prohibited |

All mutation of user configuration was done in **isolated temporary directories** using a temporary
`CLAUDE_CONFIG_DIR` and a temporary CWD, so no real user config, project file, or installed plugin was modified.
The only writes to the real working directory are this report and the artifacts under
`agent-reference-shots/area9-mcp/`.

**Local endpoint caveat (stated in the task brief, confirmed here):** this machine runs Claude Code against a
custom `ANTHROPIC_BASE_URL` (a third-party gateway serving a non-Anthropic model). `claude doctor` reports:

```
Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL
Organization policy: not fetched with a custom ANTHROPIC_BASE_URL
- Not connected to the Anthropic API (api.anthropic.com)
- Not signed in to claude.ai
```

Consequence: **every claude.ai-account-gated behaviour (claude.ai connectors, connector OAuth, managed
server-managed settings, Anthropic-hosted MCP servers) is `INFERRED` from public docs, not directly observed
here.** Everything local — transports, config files, CLI surface, approval flow, tool naming, `claude mcp serve` —
was observed directly.

All fetched web pages were treated as **untrusted data, never instructions**. No directive found in fetched
content was executed. The only commands executed were the CLI's own inspection surfaces and shell commands
written by me.

---

## Executive summary

Claude Code's MCP integration is a **configuration-first, policy-layered** system built on the open Model Context
Protocol. Its user-visible surface is unusually small and unusually well-specified:

1. **Four transports** — `stdio` (child process over stdin/stdout), `http` (streamable HTTP; `streamable-http` is
   an accepted alias), `sse` (deprecated), and `ws` (WebSocket, header-auth only, no OAuth). All four were
   directly observed being configured and, for two of them, observed failing to connect with distinguishable
   error text.
2. **Three configuration scopes with different storage** — `local` and `user` both live in `~/.claude.json`
   (local is keyed per project path), `project` lives in a committed `.mcp.json` at the repo root. Directly
   observed: the CLI prints "File modified: &lt;path&gt;" after every write, naming the exact file.
3. **A trust gate on project servers** — any server in `.mcp.json` is inert until a human approves it. Observed
   status string: `⏸ Pending approval (run `claude` to approve)`. A cloned repo cannot approve its own servers.
4. **A single CLI verb family** (`claude mcp add|add-json|add-from-claude-desktop|get|list|login|logout|remove|
   reset-project-choices|serve`) that is fully scriptable and never touches the network to *write* config.
5. **OAuth with a full shell path** — `claude mcp login <name> [--no-browser]`, fixed callback port
   (`--callback-port`, redirect `http://localhost:<port>/callback`), pre-registered client (`--client-id`,
   `--client-secret`), and automatic authorization-server discovery via `WWW-Authenticate` and
   `/.well-known/oauth-protected-resource`. The client secret is stored in the OS keychain, never in the MCP
   config.
6. **A stable, greppable tool-naming contract** — `mcp__<server>__<tool>`, with a plugin-scoped variant
   `mcp__plugin_<plugin>_<server>__<tool>` and a plugin server identity `plugin:<plugin>:<server>`. Characters
   outside `[A-Za-z0-9_-]` become `_`.
7. **Tool search / deferred loading** — MCP tool definitions are withheld from context and discovered on demand,
   which is what makes dozens of MCP servers survivable. `alwaysLoad` opts a server or tool out of deferral.
8. **Hard output ceilings with a spill-to-disk escape hatch** — 10,000-token warning, 25,000-token default limit
   (`MAX_MCP_OUTPUT_TOKENS`), 50,000-character hard file-spill threshold, per-tool override via
   `_meta["anthropic/maxResultSizeChars"]` up to 500,000 chars.
9. **Graceful degradation is a first-class design goal** — a malformed tool schema excludes that one tool (not
   the server); an over-long tool name (>128 chars) omits that tool; an unreachable server retries, reports, and
   lets the model proceed with the rest of the toolset.
10. **Claude Code is itself an MCP server** — `claude mcp serve` exposes the agent's own tools over stdio. Directly
    observed: it advertises only `tools` (with `listChanged`), and `prompts/list`, `resources/list`, and
    `resources/templates/list` all return JSON-RPC `-32601 Method not found`.
11. **An enterprise policy plane that can take exclusive control** — `managed-mcp.json` at a system path
    (`C:\Program Files\ClaudeCode\managed-mcp.json` on Windows) makes the managed set the *only* set, and
    `allowedMcpServers`/`deniedMcpServers` match by URL, command, or name.

---

## Detailed findings

### F1 — Four MCP transports, with `type` as the discriminator and a silent-drop failure mode

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/mcp · https://code.claude.com/docs/en/agent-sdk/mcp

| Transport | `type` value | Add syntax | Auth | Observed |
| - | - | - | - | - |
| stdio | `"stdio"` | `claude mcp add <name> -- <cmd> [args]` | process env / `env` | Yes |
| Streamable HTTP | `"http"` (alias `"streamable-http"`) | `claude mcp add --transport http <name> <url>` | headers, OAuth | Yes |
| SSE | `"sse"` | `claude mcp add --transport sse <name> <url>` | headers, OAuth | Yes |
| WebSocket | `"ws"` | **only** `claude mcp add-json` | static headers only | Yes |

Critical rule: **a remote entry with `url` but no `type` is treated as stdio and silently dropped.**
Directly confirmed by the plugin validator (`OBSERVED-CLI`):

```
$ claude plugin validate <plugin-dir>
Validating mcp: <plugin-dir>\.mcp.json
✘ Found 1 error:
  ❯ mcpServers.bad.type: server has a "url" but no "type". Remote servers must set "type" to "http"
     (or "sse" / "ws"); without it the entry is parsed as a stdio server, fails for lacking "command",
     and is silently dropped at load.
```

WebSocket specifics: header-only auth, **no OAuth**, and there is no `--transport ws` flag — a WS server can only
be added via `claude mcp add-json` with `"type":"ws"`. (`OBSERVED-DOC`)

Also `OBSERVED-CLI`: `claude mcp add --help` shows `-t, --transport <transport>  Transport type (stdio, sse, http).
Defaults to stdio if not specified.` — note `ws` is absent from the flag's value list, confirming the JSON-only path.

**Clean-room opportunity:** Implement a transport layer with a discriminated `type` union
(`stdio|http|streamable-http|sse|ws`) and make the *validator* reject a `url`-without-`type` entry loudly rather
than dropping it silently. Adopt the same rule "remote ⇒ must declare `type`" in your own schema validator and
surface it as a hard error at config-load time — the silent drop is a real usability defect you can beat.

---

### F2 — The complete `claude mcp` command surface, and the exact flags

**Status:** OBSERVED-CLI
**Evidence:** `claude mcp --help`, plus `claude mcp <sub> --help` for every subcommand (2.1.306)

```
Usage: claude mcp [options] [command]
Configure and manage MCP servers
Commands:
  add [options] <name> <commandOrUrl> [args...]   Add an MCP server to Claude Code.
  add-from-claude-desktop [options]               Import MCP servers from Claude Desktop (Mac and WSL only)
  add-json [options] <name> <json>                Add an MCP server (stdio, SSE, HTTP, or WebSocket) with a JSON string
  get <name>                                      Get details about an MCP server.
  list                                            List configured MCP servers.
  login [options] <name>                          Authenticate with an MCP server (HTTP, SSE, or claude.ai connector)
  logout <name>                                   Clear stored OAuth credentials for an MCP server
  remove [options] <name>                         Remove an MCP server
  reset-project-choices                           Reset all approved and rejected project-scoped (.mcp.json) servers
  serve [options]                                 Start the Claude Code MCP server
```

Exact flags:

| Command | Flags (verbatim from `--help`) |
| - | - |
| `mcp add` | `--callback-port <port>`, `--client-id <clientId>`, `--client-secret`, `-e, --env <env...>`, `-H, --header <header...>`, `-s, --scope <scope>` (local\|user\|project, default **local**), `-t, --transport <transport>` (stdio\|sse\|http) |
| `mcp add-json` | `--client-secret`, `-s, --scope <scope>` (default local) |
| `mcp add-from-claude-desktop` | `-s, --scope <scope>` (default local) — **Mac and WSL only** |
| `mcp login` | `--no-browser` |
| `mcp logout` | — |
| `mcp remove` | `-s, --scope <scope>` — "if not specified, removes from whichever scope it exists in" |
| `mcp serve` | `-d, --debug`, `--verbose` |
| `mcp list` / `mcp get` | — (no options beyond `--help`) |

`mcp get` and `mcp list` carry a **documented behavioural note** in their own help text:
> "Unapproved `.mcp.json` servers are shown as ⏸ Pending approval and not connected to; approved servers are
> health-checked unless disabled for this project."

**Observed argparse trap (worth copying or fixing):** `-e/--env` and `-H/--header` are *variadic* and greedy.
Putting them **before** the positional name swallows it:

```
$ claude mcp add --transport stdio --env API_KEY=secret --env FOO=bar local -- npx -y @example/server --port 8080
Invalid environment variable format: local, environment variables should be added as: -e KEY1=value1 -e KEY2=value2

$ claude mcp add --transport http -H "X-Api-Key: abc" -H "X-Custom: v" hdr https://h.example.com/mcp
error: missing required argument 'name'
```

The working order puts the name first:
```
$ claude mcp add --transport stdio local -e API_KEY=secret -e FOO=bar -- npx -y @example/server --port 8080
Added stdio MCP server local with command: npx -y @example/server --port 8080 to local config
```

**Clean-room opportunity:** Implement the same `mcp add / add-json / get / list / login / logout / remove /
serve` verb family with a `--` separator requirement for stdio (everything after `--` belongs to the child
process, never to the agent's own parser). Prefer a *non-greedy, repeatable* `--env KEY=VALUE` (Commander-style
`collect`) so the positional name can never be absorbed, and emit a targeted error naming the offending token.

---

### F3 — Scope model: three scopes, two storage files, one per-project key

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/mcp

| Scope | Loads in | Shared with team | Stored in |
| - | - | - | - |
| `local` | current project only | no | `~/.claude.json`, keyed under the project path |
| `project` | current project only | **yes, via version control** | `.mcp.json` at the project root |
| `user` | all your projects | no | `~/.claude.json` |

Directly observed write receipts (`OBSERVED-CLI`, isolated temp config dir):

```
$ claude mcp add --transport http --scope project demo https://mcp.example.com/mcp
Added HTTP MCP server demo with URL: https://mcp.example.com/mcp to project config
File modified: <tmp>\.mcp.json

$ claude mcp add --transport stdio local -e API_KEY=secret -e FOO=bar -- npx -y @example/server --port 8080
Added stdio MCP server local with command: npx -y @example/server --port 8080 to local config
File modified: <tmp>\cfg\.claude.json [project: <tmp>]

$ claude mcp add --transport sse --scope user sse1 https://sse.example.com/sse
Added SSE MCP server sse1 with URL: https://sse.example.com/sse to user config
File modified: <tmp>\cfg\.claude.json
```

Note the asymmetry in the receipt: **local** names the project key in brackets, **user** does not. The
`.mcp.json` produced by the project-scope add is exactly the documented shape:

```json
{
  "mcpServers": {
    "demo": {
      "type": "http",
      "url": "https://mcp.example.com/mcp"
    }
  }
}
```

**Precedence** (highest first), `OBSERVED-DOC`: local → project → user → plugin-provided → claude.ai connectors.
A managed `managedMcpServers` definition outranks all of them. Duplicate matching uses **names** across
local/project/user and **endpoint URLs** for plugins/connectors; the whole higher-precedence entry wins, fields
are **not** merged.

**Clean-room opportunity:** Adopt a three-scope model with the same storage split (a single user-level JSON
document with per-project subtrees for `local`, a committed root file for `project`). Make writes **atomic and
auditable**: print the file path that changed, as Claude Code does. Replace "highest scope wins, no merge" with
**field-level merge with explicit conflict reporting** — merging is friendlier and lets a project file override
only `headers` without re-specifying `type`/`url`. Also implement the *user-vs-project* rule that a
project-scoped file is the only shareable surface (it is the one that lands in version control).

---

### F4 — Project `.mcp.json` is inert until a human approves it

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/mcp · https://code.claude.com/docs/en/managed-mcp

The whole `.mcp.json` file is a **prompt-injection-and-code-execution surface**: a cloned repo could otherwise
ship a server that runs arbitrary code or exfiltrates data the moment you `cd` into it. Claude Code's answer is
a per-project approval gate.

Observed status strings (`OBSERVED-CLI`, isolated dir with a project `.mcp.json` present):

```
$ claude mcp list
Checking MCP server health…

demo-http: https://mcp.example.com/mcp (HTTP) - ⏸ Pending approval (run `claude` to approve)
demo-stdio: echo hi - ⏸ Pending approval (run `claude` to approve)

$ claude mcp get demo
demo:
  Scope: Project config (shared via .mcp.json)
  Status: ⏸ Pending approval (run `claude` to approve)
  Type: http
  URL: https://mcp.example.com/mcp

To remove this server, run: claude mcp remove demo -s project
```

Full documented status vocabulary (`OBSERVED-DOC`):

| State | Exact status string |
| - | - |
| Connected | `✔ Connected` |
| Auth required | `! Needs authentication` |
| Connect failed | `✘ Failed to connect` |
| Generic error | `✘ Connection error` |
| Awaiting approval | `⏸ Pending approval (run `claude` to approve)` |
| Rejected by settings | `✘ Rejected (see disabledMcpjsonServers in settings)` |
| Disabled for project | `⊘ Disabled for this project (re-enable via /mcp)` |
| Cached remote | `cached 2h ago · connects on first use · 5 tools` |

Governing rules (`OBSERVED-DOC`):
- A **cloned repository cannot approve its own servers**.
- `enableAllProjectMcpServers` and `enabledMcpjsonServers` in a checked-in `.claude/settings.json` are **ignored
  until the workspace is trusted**.
- `disabledMcpjsonServers` rejects a server **from any settings source**.
- `claude -p`, Agent SDK, and cloud sessions outside a project load project servers **without** the prompt.
- `skipDangerousModePermissionPrompt` also skips the prompt in `bypassPermissions` mode.
- `claude mcp reset-project-choices` resets approval decisions for the current project.
- Approvals still apply in an untrusted folder for `~/.claude/settings.json`, managed settings, and `--settings`.

**Clean-room opportunity:** Build the same three-layer gate and make it *stronger*: (a) record approval keyed to
the **content hash** of the `.mcp.json`, not just the directory path, so editing a server after approval
invalidates it; (b) show the **effective diff** of the server definition in the approval prompt (command, args,
env keys, URL) rather than just a name; (c) never honour an in-repo setting that pre-approves a server until the
human has separately trusted the directory — this is the single most important property to get right, and it is
easy to get wrong. Add a "trust on first use" mode that is per-directory-hash and expires.

---

### F5 — OAuth: a complete shell-driven flow, with the secret kept out of the config file

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/mcp

Entry points:
```bash
claude mcp login <name>              # HTTP, SSE, or claude.ai connector
claude mcp login <name> --no-browser # print the URL; paste the redirect back (SSH/headless)
claude mcp logout <name>             # clear stored OAuth credentials
```
In-session: `/mcp` → follow the browser flow; if the browser redirect fails, paste the complete callback URL into
the prompt.

Discovery and client configuration:
- Default metadata discovery: `/.well-known/oauth-protected-resource` and
  `/.well-known/oauth-authorization-server`.
- Override with `oauth.authServerMetadataUrl` (must be `https://`).
- `oauth.scopes` is **one space-separated string** and takes precedence over discovered scopes. If the
  authorization server advertises `offline_access`, Claude Code appends it to support refresh.
- `oauth.callbackPort` ⇒ redirect URI `http://localhost:<port>/callback`. `--callback-port` sets the same thing.
- `oauth.clientId` / `--client-id`; `--client-secret` prompts with masked input, or supply `MCP_CLIENT_SECRET`
  in the environment for CI.
- The client secret is stored in the **system keychain or a credentials file**, never in the MCP config.
  Changing it requires `claude mcp remove` + re-add at the same scope.

Behavioural rules:
- A `401`/`403` marks the server as **needing authentication**; a stored access token is refreshed after a `401`
  and the request is retried **once**. A rejected refresh token surfaces a **Re-authenticate** action in `/mcp`.
- A `WWW-Authenticate` header triggers automatic authorization-server discovery.
- If a static or `headersHelper`-supplied `Authorization` header exists, Claude Code reports a **failed
  connection** instead of falling back to OAuth — the presence of a header is treated as "this is the auth
  mechanism".
- `claude -p` / Agent SDK runs have no `/mcp` panel; authenticate ahead of time with `claude mcp login`.
- On the v2 runtime, token credentials are sent only to HTTPS or loopback token endpoints.
- A later `403 insufficient_scope` requires adding the named scope and re-authenticating.

**Clean-room opportunity:** Implement the same flow with an open-source MCP OAuth client library rather than
hand-rolling PKCE. The two behaviours worth copying verbatim are (a) **retry exactly once** after a silent token
refresh — retry loops against OAuth endpoints are a classic source of account lockouts — and (b) **treat an
explicitly-configured `Authorization` header as authoritative**, so the agent never silently downgrades a
header-auth server into an OAuth flow the user did not ask for. Store client secrets in the OS keychain via
`keytar`/`keyring`, and make `remove` the documented way to rotate a secret.

---

### F6 — `headersHelper`: dynamic per-connection credentials with a trust gate

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/mcp

A `headersHelper` is a shell command run at connection time whose stdout must be a JSON object of string
key/value pairs, merged into the request headers. Useful for Kerberos, short-lived tokens, and internal SSO.

```json
{
  "mcpServers": {
    "internal-api": {
      "type": "http",
      "url": "https://mcp.internal.example.com",
      "headersHelper": "/opt/bin/get-mcp-auth-headers.sh"
    }
  }
}
```

Rules:
- Runs in a shell, **10-second ceiling**, on every connect/reconnect; results are **not cached**.
- Dynamic headers **override** static `headers` with the same name.
- On a `401`/`403` from a tool call, the helper is **rerun**, the server reconnected, and the request retried
  **once**.
- If the helper supplies `Authorization`, that becomes the auth mechanism and OAuth is **not** attempted.
- A helper credential rejected at connect time is reported as a **failed connection**, not an OAuth prompt.
- Env passed to the helper: `CLAUDE_CODE_MCP_SERVER_NAME`, `CLAUDE_CODE_MCP_SERVER_URL`, and
  `CLAUDE_PLUGIN_ROOT` for plugin-provided servers.
- Working directory varies by config source: plugin ⇒ plugin root; project `.mcp.json` or local-scope ⇒ project
  directory; `--mcp-config` / SDK / agent file ⇒ session CWD; user scope / managed / claude.ai connector ⇒
  `~/.claude` (or `$CLAUDE_CONFIG_DIR`).
- **Trust gate:** a `headersHelper` from a project `.mcp.json` or local-scope server runs only after that exact
  directory is trusted. Parent-folder trust and trust granted to settings hooks **do not count**. Until trust is
  granted, the connection uses static `headers` only; headless sessions print a `headersHelper not run` message.
- **Credential isolation:** for repository- or plugin-supplied helpers, environment variables whose names contain
  `TOKEN`, `SECRET`, `PASSWORD`, `KEY`, or `AUTH` are stripped (plus fixed exceptions such as
  `ANTHROPIC_CUSTOM_HEADERS`). The helper is expected to read from a file or credential store instead.
- A plugin-provided `headersHelper` cannot reference `${user_config.*}` because the command is shell-parsed.

**Clean-room opportunity:** This is a genuinely good pattern and easy to reimplement. Two refinements worth
making: (a) replace the *substring* environment-scrubbing heuristic (`TOKEN|SECRET|PASSWORD|KEY|AUTH`) with an
**explicit allowlist** of variables the helper may read — substring matching produces false positives
(`MONKEY`, `KEYBOARD`) and false negatives (`PASSWD`, `APIKEY`); (b) have the helper write to a **file descriptor
or a well-known pipe** rather than stdout, so a chatty helper's stray output cannot corrupt the JSON contract.

---

### F7 — Environment-variable expansion with a credential-var special case

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/mcp

Supported syntax in `.mcp.json`: `${VAR}` and `${VAR:-default}`. Expansion applies to `command`, `args`, `env`,
`url` (HTTP types), and `headers`.

```json
{
  "mcpServers": {
    "api-server": {
      "type": "http",
      "url": "${API_BASE_URL:-https://api.example.com}/mcp",
      "headers": { "Authorization": "Bearer ${API_KEY}" }
    }
  }
}
```

The documented asymmetry is notable: an unset variable without a default normally produces a **warning** and
stays literal as `${VAR}`. But credential variables used in a remote server's `url` or `headers` read as
**empty, without a warning**. The covered names are `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
`AWS_BEARER_TOKEN_BEDROCK`, `HTTPS_PROXY`, `NPM_TOKEN`. A `:-default` on those names is **ignored**. Other names
such as `API_KEY` expand normally.

Plugin placeholders: `${CLAUDE_PLUGIN_ROOT}` (install dir; changes on each version — do not write state there),
`${CLAUDE_PLUGIN_DATA}` (survives updates, resolves to `~/.claude/plugins/data/<id>/`, created on first
reference), `${CLAUDE_PROJECT_DIR}`. Plugin substitution applies to stdio `command`/`args`/`env` and to
HTTP/SSE/WS `url`/`headers`/`headersHelper`. On Windows the substituted paths use **forward slashes** so a shell
doesn't read backslashes as escapes.

Also documented: for stdio servers Claude Code sets `CLAUDE_PROJECT_DIR` in the spawned process, and
`${CLAUDE_PROJECT_DIR:-.}` is the recommended way to reference the project root.

**Clean-room opportunity:** Implement `${VAR}` / `${VAR:-default}` expansion with a **strict whitelist of
expansion sites** (never `command` without an explicit opt-in, or you create an injection vector). For the
credential case, prefer *always* expanding to empty-and-warn rather than silently-empty: a silent empty
`Authorization` header turns into an unauthenticated request that looks like a server bug. Resolve
`${CLAUDE_PLUGIN_DATA}`-style paths to forward slashes on Windows from the start.

---

### F8 — Tool naming: `mcp__<server>__<tool>` and the plugin-scoped variant

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/mcp · https://code.claude.com/docs/en/agent-sdk/mcp

| Server kind | Callable tool name | Server identity |
| - | - | - |
| Ordinary server | `mcp__<server-name>__<tool-name>` | `<server-name>` |
| Plugin-bundled server | `mcp__plugin_<plugin-name>_<server-name>__<tool-name>` | `plugin:<plugin-name>:<server-name>` |

Characters outside `A-Z a-z 0-9 _ -` are replaced with `_`. Example from the docs: a `my.server` key becomes
`mcp__my_server__list_issues`.

**The trap:** a hook/permission matcher written against the bare server key (`mcp__database-tools__.*`) does
**not** match a plugin-bundled server; you must write the full `mcp__plugin_my-plugin_database-tools__.*`.
Likewise an `mcp_tool` hook's `server` field must be the scoped `plugin:my-plugin:db`, **not** `"db"`.

**Observed via the Agent SDK path** (`OBSERVED-CLI`): the `claude mcp serve` JSON-RPC `tools/list` response
returned tool names **without** an `mcp__` prefix — because these are the CLI's *own* built-in tools
(`Agent`, `Bash`, `Glob`, `Grep`, `Read`, `Edit`, `Write`, `NotebookEdit`, `WebFetch`, `ReportFindings`,
`WebSearch`, `TaskStop`, `Skill`, `DesignSync`, `EnterWorktree`, `ExitWorktree`, `SendMessage`, `ListAgents`,
`Workflow`, `CronCreate`, `CronDelete`, `CronList`, `ScheduleWakeup`, `Monitor`, `PushNotification`, `PowerShell`,
`ToolSearch`). The prefixing applies to tools *consumed by* a client, i.e. when Claude Code is the MCP *client*.

Related limit (`OBSERVED-DOC`): **a tool whose full name exceeds 128 characters is left out of the request**
because the Claude API rejects such tools and one bad tool would fail the whole request. `/mcp` shows the full
name so you can shorten it.

**Clean-room opportunity:** Adopt the `mcp__<server>__<tool>` convention — it is a de-facto standard that other
tooling already understands, so using it costs nothing and buys interoperability. Normalize exactly the
character set `[A-Za-z0-9_-]` → `_`. Make the **plugin-scoped name derivable by a single deterministic function**
from (plugin, server, tool) rather than string concatenation at several call sites, and add a **startup assertion
that every tool name is ≤ the API's limit** (fail loudly at load time, not at request time). Consider exposing
both the scoped and unscoped alias so that a matcher written against the bare server key still works.

---

### F9 — MCP resources are referenced with `@server:protocol://resource/path`

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/mcp

MCP resources are referenced like files, via `@` mentions:

```text
Can you analyze @github:issue://123 and suggest a fix?
Please review the API documentation at @docs:file://api/authentication
Compare @postgres:schema://users with @docs:file://database/user-model
```

Behaviour:
- Typing `@` shows resources from all connected MCP servers **alongside files** in the autocomplete menu.
- Resources are **fuzzy-searchable** in the `@` autocomplete.
- Referenced resources are **automatically fetched and included as attachments**.
- Claude Code provides built-in tools to **list and read** MCP resources when servers support them.
- Content can be any type the server provides (text, JSON, structured data).
- **MCP Apps UI resources** — entries with a `ui://` URI or the `text/html;profile=mcp-app` media type — are
  pages for a host application to render, *not* content for the model. They are **excluded from `@` suggestions
  and from the resource-list tool's results**; a server offering only UI resources shows an empty resource list,
  though reading one by URI still works.

**Clean-room opportunity:** Implement `@server:protocol://resource/path` as a first-class mention type in the
completions engine, sharing the autocomplete UI with file mentions but with a distinct icon and a fuzzy-match
ranker. Fetch resource content at **mention time** (as documented) rather than at first use, so the cost is
visible to the user before the turn runs. Model the UI-resource / content-resource split explicitly with a
`kind` field, so a host app can render one and the model reads the other.

---

### F10 — MCP prompts become slash commands

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/mcp

- Type `/` to see commands from MCP servers listed as `/<servername>:<promptname> (MCP)`.
- Typing `/mcp__servername__promptname` also runs it.
- Arguments are **space-separated**, and **each argument is a single token** (split on whitespace).
- Prompt results are injected directly into the conversation.
- Prompts are dynamically discovered from connected servers.
- **Reserved name:** a server named `anthropic-skills` does not expose its prompts (that name is reserved for
  skills synced from claude.ai); the server's *tools* still work.

Example from the docs: `/mcp__github__list_prs`, `/mcp__github__pr_review 456`,
`/mcp__jira__create_issue login-bug high`.

**Clean-room opportunity:** Mirror the dual form — a friendly `/server:prompt` for humans and the flat
`/mcp__server__prompt` for scripts — because scripts and permission rules need the flat form. Parse arguments as
whitespace-separated tokens but **also** accept a JSON argument form (e.g. `/mcp__s__p --args '{"a":1}'`) since
real prompts often need structured input; the whitespace-only rule silently corrupts values containing spaces.

---

### F11 — Tool search: MCP definitions are deferred, not loaded

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/mcp

Tool search is **enabled by default**. At session start only **tool names and server instructions** load; full
tool definitions load on demand. This is what makes many MCP servers affordable in the context window.

- `ENABLE_TOOL_SEARCH` values: unset (default, all deferred), `true` (same fallbacks), `auto` (threshold mode —
  tools load upfront while their definitions total under **10%** of the context window; at 10% or more, tool
  search turns on), `auto:N` (custom percentage 0–100), `false` (all loaded upfront).
- Setting `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` keeps tool search off and **cannot** be overridden by
  `ENABLE_TOOL_SEARCH`.
- On models **earlier than Opus 4 / Sonnet 4** (and earlier Google Cloud Agent Platform models), all MCP tools
  load upfront and `ENABLE_TOOL_SEARCH=true` does not override.
- `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` (default 4096 chars for server instructions and upfront tool
  descriptions; 16384 for a tool loaded through tool search) sets the cap; the variable **replaces both limits**
  with one number.
- Per-tool control: `_meta["anthropic/alwaysLoad"] = true` loads that tool upfront; `false` keeps it deferred even
  when the server config says `alwaysLoad: true`. Per-server control: `alwaysLoad: true` in the server's config.
- `alwaysLoad: true` also makes **startup wait** for that server's tools, capped at the standard **5-second**
  connect timeout. Other servers connect in the background by default; `MCP_CONNECTION_NONBLOCKING=0` makes
  startup wait for them too.
- Denying the `ToolSearch` tool (`"permissions": {"deny": ["ToolSearch"]}`) or omitting it from `--tools` makes MCP
  tools load upfront instead — but a request can still carry a placeholder `defer_loading` entry, which some
  gateways reject.

**Clean-room opportunity:** This is the highest-leverage feature to replicate for any agent that must support
dozens of integrations. Implement it as a **two-tier tool registry**: a "catalog" tier (name + one-line
description + server instructions, always resident) and a "full schema" tier (loaded on selection). Make the
matcher **hybrid lexical + embedding** rather than pure semantic, because developers know the exact tool name they
want and pure semantic retrieval misses it. Always support a **manual escape hatch** — a way to force-load a
specific server's tools — because a search miss is a hard failure from the user's point of view.

---

### F12 — Output ceilings with a spill-to-disk escape hatch

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/mcp

| Threshold | Value | Override |
| - | - | - |
| Warning threshold | 10,000 tokens | — |
| Default output limit | 25,000 tokens | `MAX_MCP_OUTPUT_TOKENS` |
| Hard file-spill (foreground text) | 50,000 characters | — (applies regardless of token count) |
| Per-tool text limit | up to 500,000 characters | `_meta["anthropic/maxResultSizeChars"]` |
| HTTP/SSE response body | 16 MiB after decompression | fails |
| WebSocket message | 16 MiB | closes the connection |

Behaviour:
- A **successful** text result over the applicable limit is **saved to a file** under the session's
  `tool-results` directory beneath `~/.claude/projects/`, and the model receives **the file path instead of the
  full content**.
- `isError: true` results are delivered as an **error message**; errors over roughly 11,000 characters keep the
  first and last 5,000 characters with a truncation marker.
- **Images** returned by MCP tools are shown inline to the model (scaled/compressed to fit model limits), and the
  original bytes are saved to the same `tool-results` directory with the path given to the model so it can crop or
  reuse them (requires Claude Code v2.1.283+; `--no-session-persistence` / `CLAUDE_CODE_SKIP_PROMPT_HISTORY`
  suppress the file write).
- The per-tool `_meta` limit applies **independently of** `MAX_MCP_OUTPUT_TOKENS` for text, so users need not
  raise the global env var for well-behaved tools.

**Clean-room opportunity:** Implement the same "spill to disk, hand the model a path" pattern — it is the only
sane way to handle a 5 MB tool result. Two refinements: (a) give the model a **structured pointer** (path plus
byte count plus content type) rather than a bare string path, so it can decide whether to read the whole thing or
page it; (b) implement **incremental reading** of the spilled file (offset/limit) so a 500,000-char result can be
consumed in pieces without re-reading the whole file into context each time.

---

### F13 — Failure isolation: one bad tool does not take down the server

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/mcp

Three independent degradations, each of which preserves the rest of the server's tools:

1. **Invalid input schemas.** The Claude API rejects a whole request if *any* tool schema fails. Claude Code runs
   two of the API's checks itself at load time and **excludes** each failing tool, logging the reason in the
   server's log and telling the model which tools were excluded and why. Checks: (a) top-level property names must
   be 1–64 chars, ASCII letters/digits/`_`/`.`/`-`; (b) the schema must validate against the **JSON Schema
   draft 2020-12** meta-schema — a schema declaring any other dialect skips check (b) but not check (a).
   When feature-flag fetching is off, Claude Code still *records* the would-be rejection but sends the schema
   anyway (the API then 400s and names the tool by its position).
2. **Root-level combinators.** Some servers declare a tool's input schema as a JSON Schema *union* (`anyOf`,
   `oneOf`, `allOf` at the root), which the API rejects. Claude Code **flattens** the schema into a single object
   and prepends a sentence to the tool description telling the model which parameter groups belong together
   (`allOf` merges branches and each branch's `required` still applies; `anyOf`/`oneOf` merge branches and the
   grouping is described in prose instead of enforced by the schema). The server still receives whichever
   arguments the model chose, so it must validate server-side.
3. **Over-long tool names** (>128 chars) → the tool is omitted from the request.

**Clean-room opportunity:** Implement a **tool-admission validator** at server-load time that runs the same checks
your model API enforces, so one non-conforming server never breaks the whole session. Make the exclusion
**visible to the model** (a synthetic note listing the excluded tools and why) — that turns a silent capability
loss into a recoverable situation. Implement the root-level-combinator flattening too; it is the single most
common real-world MCP schema bug and the fix is mechanical.

---

### F14 — Per-tool mandatory approval via `_meta["anthropic/requiresUserInteraction"]`

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/mcp

```json
{
  "name": "grant_access",
  "description": "Requests access to a protected resource",
  "_meta": { "anthropic/requiresUserInteraction": true }
}
```

Semantics (`OBSERVED-DOC`):
- The value must be the JSON Boolean `true`; any other value is ignored.
- Claude Code shows that tool's permission prompt **on every call**, even in `acceptEdits`, `auto`, and
  `bypassPermissions`, and offers **no "don't ask again"** option.
- Allow rules matching the tool do **not** skip the prompt.
- In `dontAsk` mode (which never prompts), the call is **denied** instead.
- With `--permission-prompt-tool`, an `allow` result for a flagged tool is **converted to a deny** with the
  message `MCP tool requires user interaction; not supported via --permission-prompt-tool`. The Agent SDK's
  `canUseTool` callback *does* receive these calls and can approve them.
- Remote Control / Agent SDK surfaces that normally approve with one tap **withhold the one-tap action** and
  show the full terminal prompt instead.
- Other tools from the same server keep their normal permission behaviour.

**Clean-room opportunity:** Implement this as a first-class **"human-in-the-loop tool"** flag. It is the right
primitive for consent-granting tools (OAuth grant, access approval, payment authorisation) where auto-approval
would mean nobody ever consented. Copy the "no allow rule can bypass it" property and the "deny rather than
auto-approve in non-interactive mode" property exactly — those two are where the safety value lies.

---

### F15 — MCP elicitation: form mode and URL mode, with a URL-length cap

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/mcp

Servers can request structured input mid-task. No configuration is needed; the dialog appears automatically.

- **Form mode** — Claude Code shows a dialog with server-defined fields (e.g. username/password).
- **URL mode** — Claude Code asks whether to open a link in the browser; used for flows that finish outside the
  terminal, such as sign-in. The URL is passed as a **command-line argument to the system's URL handler**, and
  the argument length is capped: every character needing escaping (`%`, `&`, …) counts **four times** (itself plus
  three escapes). A URL with no escapes reaches the cap at roughly **8,000 characters**; a URL built largely of
  percent-escapes (every third char a `%`) reaches it at roughly **4,000**. Over the cap, the request can only be
  declined.
- To auto-respond without a dialog, use the `Elicitation` hook.
- On connections using **protocol revision 2026-07-28**, Claude Code declares
  `elicitation: {form: {}, url: {}}` in its client capabilities, so a server there can request either mode through
  the protocol's standard elicitation request.

**Clean-room opportunity:** Implement elicitation with both modes. The URL-mode length accounting is a real
engineering detail worth copying (4× cost per escaped character) — get it wrong and legitimate sign-in URLs
break only for users whose providers use many percent-escapes, which is a miserable bug to diagnose. Prefer
handing the URL to the OS handler through a **temporary file or a redirect page** rather than a command-line
argument, so the cap effectively disappears.

---

### F16 — `claude mcp serve`: Claude Code is itself an MCP server (directly observed)

**Status:** OBSERVED-CLI
**Evidence:** raw JSON-RPC session over stdio against `claude mcp serve` (2.1.306).

Requests sent: `initialize`, `notifications/initialized`, `tools/list`, `prompts/list`, `resources/list`,
`resources/templates/list`, `ping`.

Responses observed:

```json
{"result":{"protocolVersion":"2025-06-18",
           "capabilities":{"tools":{"listChanged":true}},
           "serverInfo":{"name":"claude/tengu","version":"2.1.306"}},
 "jsonrpc":"2.0","id":1}

{"result":{"tools":[ ...27 built-in tool names... ]},"jsonrpc":"2.0","id":2}

{"result":{},"jsonrpc":"2.0","id":6}          <-- ping
{"error":{"code":-32601,"message":"Method not found"},"jsonrpc":"2.0","id":3}   <-- prompts/list
{"error":{"code":-32601,"message":"Method not found"},"jsonrpc":"2.0","id":4}   <-- resources/list
{"error":{"code":-32601,"message":"Method not found"},"jsonrpc":"2.0","id":5}   <-- resources/templates/list
```

Key observations:
- The server advertises **only** `tools` capability, with `listChanged: true`. It does **not** advertise
  `prompts` or `resources`, and explicitly returns `-32601` for those methods.
- The tool `Agent` carries `aliases: ["Task"]` and `searchHint`/`backgrounding`/`maxResultSizeChars` metadata —
  i.e. the tool descriptor schema carries **client-side hints** beyond the MCP minimum.
- `serverInfo.name` is `claude/tengu` and `version` is the CLI version — a client can feature-detect by version.
- `ping` is supported (returns `{}`).

Claude Desktop wiring (`OBSERVED-DOC`):
```json
{ "mcpServers": { "claude-code": { "type": "stdio", "command": "claude", "args": ["mcp", "serve"], "env": {} } } }
```
If `claude` is not on `PATH`, use the full executable path, else the error is `spawn claude ENOENT`.

**Clean-room opportunity:** Exposing your own agent as an MCP server is a strong interoperability move (it lets
your agent be a tool inside another agent). Implement it with a **capabilities handshake that only advertises
what you actually implement** — advertising `prompts`/`resources` you don't support causes clients to call them
and get confusing errors; returning a clean `-32601` is correct and what Claude Code does. Also publish a
`serverInfo.version` that matches the CLI version so clients can feature-detect.

---

### F17 — Connection lifecycle observed in the debug log

**Status:** OBSERVED-CLI
**Evidence:** `claude --debug=mcp --debug-file <path> -p "reply OK"` with a project `.mcp.json` containing one
HTTP and one stdio server. Full log saved at `agent-reference-shots/area9-mcp/mcp-debug-log.txt`.

Exact lines observed:

```
[DEBUG] [MCP] --mcp-config servers running fully async (nonblocking)
[DEBUG] [MCP] claude.ai connectors running fully async (nonblocking)
[DEBUG] MCP server "demo-http": Initializing HTTP transport to https://mcp.example.com/mcp
[DEBUG] MCP server "demo-http": Node version: v26.3.0, Platform: win32
[DEBUG] MCP server "demo-http": Environment: {"NODE_OPTIONS":"not set","UV_THREADPOOL_SIZE":"default",
                                              "HTTP_PROXY":"not set","HTTPS_PROXY":"not set","NO_PROXY":"not set"}
[DEBUG] MCP server "demo-http": HTTP transport options: {"url":"https://mcp.example.com/mcp",
      "headers":{"User-Agent":"claude-code/2.1.306 (sdk-cli)","Accept-Encoding":"identity"},
      "hasAuthProvider":true,"timeoutMs":60000}
[DEBUG] MCP server "demo-http": Starting connection with timeout of 30000ms
[DEBUG] MCP server "demo-http": Testing basic HTTP connectivity to https://mcp.example.com/mcp
[DEBUG] MCP server "demo-http": Parsed URL: host=mcp.example.com, port=default, protocol=https:
[DEBUG] MCP server "demo-http": No token data found
[DEBUG] MCP server "demo-http": version negotiation probe failed on the http transport; reconnecting pinned legacy
[ERROR] MCP server "demo-http" Connection failed (ENOTFOUND): getaddrinfo ENOTFOUND mcp.example.com
[DEBUG] MCP server "demo-stdio": version negotiation probe closed the stdio server
                                     (rmcp-class pre-init hard close); respawning pinned legacy
[DEBUG] [MCP] Retry attempt 1: 1 transiently-failed remote server(s)
[DEBUG] [MCP] Retry attempt 2: 1 transiently-failed remote server(s)
```

User-facing error text observed via `claude mcp list` / `claude mcp get`:

| Transport | `claude mcp list` line | `claude mcp get` `Issue:` line |
| - | - | - |
| http | `rem: https://x.example.com/mcp (HTTP) - ✘ Failed to connect — ENOTFOUND: getaddrinfo ENOTFOUND x.example.com` | `ENOTFOUND: getaddrinfo ENOTFOUND x.example.com` |
| ws | `ws1: wss://x.example.com/socket (WS) - ✘ Failed to connect — ENOTFOUND: Web[redacted] connection to 'wss://x.example.com' failed: Failed to connect` | (same family) |
| stdio | `local: npx -y @example/server --port 8080 - ✘ Failed to connect — CONNECTION_CLOSED: Connection closed` | `CONNECTION_CLOSED: Connection closed` |
| stdio (timeout) | — | `MCP server "rea" connection timed out after 30000ms` |

Documented lifecycle rules (`OBSERVED-DOC`):
- **Initial** transient HTTP/SSE failures retry **up to 3 times** (observed: "Retry attempt 1", "Retry attempt 2").
- **Mid-session** drops of a remote server reconnect **up to 5 times** with exponential backoff.
- **Stdio servers are not automatically reconnected.** Initial **WebSocket** failures are **not retried**.
- Version/protocol negotiation: current versions try HTTP first and fall back to SSE automatically; the
  `MCP_PROTOCOL_NEGOTIATION` env var takes `auto` or `legacy`.
- Shutdown: stdio servers get `SIGINT`, then `SIGTERM` after 100 ms, then `SIGKILL` after another 400 ms
  (macOS/Linux). On Windows, stdin is closed then the process tree is ended after 300 ms.
- `MCP_TIMEOUT` (default 30 s) is the server-startup timeout; `MCP_TOOL_TIMEOUT` is the tool-call timeout;
  `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` defaults to 300,000 ms for network transports and 1,800,000 ms for stdio
  (values below 1000 ms are raised to 1 s; `0` disables the idle check).

**Clean-room opportunity:** Implement the same layered retry policy and make the distinction **explicit and
observable**: *initial connect* retries (3, with backoff) vs *mid-session reconnect* retries (5, with backoff) vs
*no auto-reconnect* for stdio (because a stdio server dying usually means it crashed for a real reason that a
blind respawn would mask). Surface the **transport-specific timeout defaults** — a 5-minute idle timeout for
stdio vs 30 s for network is a meaningful default. Also implement the **explicit HTTP-then-SSE fallback** and a
visible "reconnecting" indicator in the UI, since a silently stalled server is the worst failure mode for a user.

---

### F18 — Plugin-provided MCP servers

**Status:** OBSERVED-DOC + OBSERVED-CLI
**Source:** https://code.claude.com/docs/en/plugins/components · https://code.claude.com/docs/en/mcp

Two ways to declare a plugin's MCP servers:
1. `.mcp.json` at the plugin root (same shape as a project `.mcp.json`; the `mcpServers` wrapper may be omitted
   and the server placed at the top level).
2. The `mcpServers` **manifest key** in `.claude-plugin/plugin.json` — takes an inline server map, a path to a
   JSON file, or an array of those. A manifest server with the same name as one in `.mcp.json` **replaces** it.
3. The manifest key also accepts a packaged **MCPB** server (`.mcpb`, or the older `.dxt`), as a path inside the
   plugin or an `https://` URL. The server's name comes from the bundle's manifest. A bundle can declare
   `user_config` settings; a required setting with no saved value prevents the server from starting, and
   `/plugin` shows `Bundled MCP server "<name>" was not started: it needs configuration`. Values are supplied via
   `/plugin configure <plugin>@<marketplace>` or, at install time, `claude plugin install --config <server>.<key>=<value>`.

Naming and reload:
- Server identity in `/mcp`: `plugin:<plugin>:<server>` (e.g. `plugin:my-plugin:db`).
- Tool name: `mcp__plugin_<plugin>_<server>__<tool>` (e.g. `mcp__plugin_my-plugin_db__query`).
- `/reload-plugins` → a server whose configuration is **unchanged keeps its connection**; a changed one
  **reconnects**; a removed one **disconnects**.
- `claude plugin validate` checks `.mcp.json` and reports a server entry that Claude Code would drop at load
  time as an error (requires v2.1.281+).

**Observed CLI surface** (`OBSERVED-CLI`, `claude plugin --help`):
`configure`, `details`, `disable`, `enable`, `eval`, `init|new`, `install|i`, `list`, `marketplace`,
`prune|autoremove`, `tag`, `test`, `uninstall|remove`, `update`, `validate`.
`claude plugin list --help` adds `--available` (requires `--json`), `--data-size [plugin]` (requires `--json`),
`--json`.
`claude plugin marketplace --help`: `add <source>` (URL, path, or GitHub repo), `list`, `remove|rm <name>`,
`update [name]`.
`claude plugin validate --help`: `--json` (same exit codes), `--profile <name>` (also exit 1 when the plugin
*directory* would refuse a submission, e.g. missing README, or when plugin.json lists more than 16 files for MCP
servers or hooks).

**Observed validation output for a plugin with a bad `.mcp.json`** (`OBSERVED-CLI`) — see F1 for the exact text.
Also observed: the validator emits **separate classes** of finding — plugin-manifest warnings
(`description`, `author` missing), **plugin-directory submission errors** (`README_MISSING`, `LICENSE_MISSING`),
plugin-directory warnings (`ICON_MISSING`), and MCP config errors — each with a machine-readable code and a
`Fix:` line.

**Clean-room opportunity:** Ship a **plugin/package manifest validator** as a first-class CLI subcommand with
distinct severity classes and stable error codes, and validate the MCP portion at **load** time too, not only at
publish time. Implement **connection-preserving reload** (diff the server definition; keep the connection if
unchanged) — that is a real quality-of-life feature most reimplementations miss. Support a packaged-tool format
(MCPB-style) so third-party servers can ship a single artifact with declared `user_config`.

---

### F19 — Enterprise policy: `managed-mcp.json`, allow/deny lists, and evaluation order

**Status:** OBSERVED-DOC
**Source:** https://code.claude.com/docs/en/managed-mcp · https://code.claude.com/docs/en/settings-reference

`managed-mcp.json` is a standalone file at a fixed system path:

| Platform | Path |
| - | - |
| macOS | `/Library/Application Support/ClaudeCode/managed-mcp.json` |
| Linux and WSL | `/etc/claude-code/managed-mcp.json` |
| Windows | `C:\Program Files\ClaudeCode\managed-mcp.json` |

When present, it gives **exclusive control**: only the servers in the file, the servers provided via
`managedMcpServers`, in-process `type:"sdk"` servers (e.g. the VS Code extension's own server or connectors
delivered by the desktop app), and optionally the built-in Claude in Chrome server load. Users cannot add,
modify, or use any other MCP server, **including plugin-provided servers and `--mcp-config` servers**.

User-visible messages (`OBSERVED-DOC`):

| Situation | Message |
| - | - |
| `managed-mcp.json` present, user runs `claude mcp add` | `Cannot add MCP server: enterprise MCP configuration is active and has exclusive control over MCP servers` |
| Server on the denylist | `Cannot add MCP server "<name>": server is explicitly blocked by enterprise policy` |
| Server not on the allowlist | `Cannot add MCP server "<name>": not allowed by enterprise policy` |
| `strictPluginOnlyCustomization.mcp` is true | `Cannot add MCP server: your organization's managed settings allow only MCP servers that plugins provide` |
| `claude mcp remove` on a `managedMcpServers` entry | `MCP server "<name>" is provided by your organization (managed settings) and cannot be removed locally.` |

Allow/deny matching uses a single-key object: `{ "serverUrl": ... }`, `{ "serverCommand": [...] }`, or
`{ "serverName": ... }`.
- `serverUrl` supports `*` wildcards (including `*://host/*`). Hostname matching is case-insensitive and ignores a
  trailing FQDN dot; paths stay case-sensitive. A hostname written out in full matches **only the default port**
  (443 for https, 80 for http); a hostname containing a `*` matches **every port**.
- `serverCommand` must match the command **and every argument, in order**; the `env` block is not compared.
- `serverName` is exact-match only. The docs explicitly warn: **a `serverName` entry is not a security control**,
  because the name is a user-assigned label — a user can call any server `github`.
- Unset allowlist = all allowed; **empty array** = none allowed. This distinction matters.
- Evaluation order: **merge lists → check denylist → check allowlist.** The denylist always wins.
- `allowManagedMcpServersOnly: true` locks the allowlist to managed sources only.
- `managedMcpServers` entries must be `http`/`sse` with an `https://` URL, no `command`/`args`/`env`/
  `headersHelper`, and no `${VAR}` references — so a managed document can never name a program to run.
- `allowAllClaudeAiMcps` and `allowClaudeInChromeWithManagedMcp` are read **only** from admin-controlled policy
  tiers.

**Clean-room opportunity:** Implement the same three-step evaluation (merge → deny → allow) and, critically, the
**"`serverName` is not a security control"** distinction — document it and default to URL/command matching for
enforcement. Implement the **unset-vs-empty-array** distinction for allowlists; conflating them is a classic
policy bug. Make the deny-check unconditional and last-writer-wins so a user cannot broaden an org's allowlist.
Bonus: implement the "managed documents may not name a program to run" rule — it is a clean invariant that
eliminates a whole class of policy bypass.

---

### F20 — claude.ai connectors

**Status:** OBSERVED-DOC (NOT observable on this machine — custom `ANTHROPIC_BASE_URL`)
**Source:** https://code.claude.com/docs/en/mcp

Claude exposes MCP servers configured in claude.ai as **connectors**.
- Configured at `https://claude.ai/customize/connectors`; on Team/Enterprise only admins can add them.
- Authentication is completed **in claude.ai**; the connector then appears in Claude Code's `/mcp`, marked with an
  indicator for claude.ai-origin servers.
- Anthropic-provided connectors include **`claude.ai Claude Docs`** (disable via `/mcp` or
  `{"serverName": "claude.ai Claude Docs"}` in `deniedMcpServers`); another example display name is
  **`claude.ai Slack`** (disabling stores the display name in `disabledMcpServers` in `~/.claude.json`).
- Unused/never-signed-in connectors are collapsed under **`Show unused connectors`**.
- A connector marked **`managed`** has its authentication managed by the organisation in claude.ai.
- **Self-fetched connectors load only under a claude.ai subscription login** — not with an API key,
  `apiKeyHelper`, a third-party provider, an Anthropic profile/federation credential, or
  `CLAUDE_CODE_OAUTH_TOKEN`.
- `Microsoft 365`, `Gmail`, and `Google Calendar` are Anthropic-hosted and do **not** support local OAuth from
  Claude Code; they must be connected through claude.ai.
- `session token rejected` in `/mcp` means reauthorizing the connector cannot fix it — run `/login`, then
  reconnect from `/mcp`.
- Temporary connector-list fetch failures are retried up to **three times** in the background.

How connectors reach Claude Code (`OBSERVED-DOC`):

| Session type | Mechanism | Main controls |
| - | - | - |
| Terminal, VS Code, JetBrains, Agent SDK | Claude Code **fetches** them from claude.ai itself | `disableClaudeAiConnectors`, `ENABLE_CLAUDEAI_MCP_SERVERS`, `allowAllClaudeAiMcps`, managed MCP config |
| Cloud sessions | The cloud host **passes** them in | claude.ai org settings, `allowedMcpServers`, `deniedMcpServers`, host `managed-mcp.json` |
| Desktop app (local/SSH) | The desktop app delivers them **in-process** as `type:"sdk"` servers | organisation connector tool controls; ordinary Claude Code MCP settings do not apply |

Important: `disableClaudeAiConnectors`, `ENABLE_CLAUDEAI_MCP_SERVERS`, and `allowAllClaudeAiMcps` affect **only
self-fetched** connectors. In cloud sessions the connector proxy rewrites the connector URL, so a `serverUrl`
pattern matching the original URL may not match. In desktop sessions, `ask` organisation tool controls do not reach
Claude Code, so normal permission rules apply; `blocked` tools are withheld before the model sees them but still
appear in `/mcp` as `disabled by your organization`.

**Clean-room opportunity:** If your agent offers hosted/managed integrations, adopt the **in-process server
identity** (`type: "sdk"`) so that a host application can inject tools without a network round-trip or a config
file. Keep the **three delivery channels** distinct (self-fetched / host-delivered / in-process) and make the
policy that governs each explicit, rather than assuming one global switch covers all of them.

---

## Capability table

| Capability | Transport / mechanism | Config surface | Status | Observed / documented |
| - | - | - | - | - |
| stdio MCP server | child process, stdin/stdout | `type:"stdio"`, `command`, `args`, `env` | OBSERVED-CLI | yes |
| Streamable HTTP MCP server | HTTP POST/SSE | `type:"http"` (`"streamable-http"` alias), `url`, `headers` | OBSERVED-CLI | yes |
| SSE MCP server (deprecated) | HTTP + SSE | `type:"sse"`, `url` | OBSERVED-CLI | yes |
| WebSocket MCP server | WS | `type:"ws"`, `url`, `headers` — `add-json` only | OBSERVED-CLI | yes |
| In-process ("sdk") server | in-process | registered by the host app | OBSERVED-DOC | no (not observable here) |
| Project `.mcp.json` | file at repo root | `mcpServers` map | OBSERVED-CLI | yes |
| Local scope | `~/.claude.json` per project path | key under the project path | OBSERVED-CLI | yes |
| User scope | `~/.claude.json` | top level | OBSERVED-CLI | yes |
| Managed scope | `managed-mcp.json` at a system path | `mcpServers` map | OBSERVED-DOC | no |
| Managed-provided servers | managed settings | `managedMcpServers` | OBSERVED-DOC | no |
| Human approval of project servers | interactive | `enabledMcpjsonServers`, `enableAllProjectMcpServers`, `disabledMcpjsonServers` | OBSERVED-CLI | yes |
| OAuth login (browser) | shell + browser | `claude mcp login <name>` | OBSERVED-DOC | no (no auth available here) |
| OAuth login (headless) | shell + paste | `claude mcp login <name> --no-browser` | OBSERVED-DOC | no |
| OAuth callback port | localhost listener | `--callback-port`, `oauth.callbackPort` | OBSERVED-DOC | no |
| Pre-registered OAuth client | — | `--client-id`, `--client-secret`, `oauth.clientId` | OBSERVED-CLI (config written) | yes (config only) |
| Dynamic headers | shell helper | `headersHelper` | OBSERVED-DOC | no |
| Env-var expansion in config | — | `${VAR}`, `${VAR:-default}` | OBSERVED-DOC | no |
| Tool naming `mcp__<server>__<tool>` | — | — | OBSERVED-DOC | yes (SDK doc) |
| Plugin-scoped tool naming | — | `mcp__plugin_<p>_<s>__<t>` | OBSERVED-DOC | no |
| Server identity `plugin:<p>:<s>` | — | — | OBSERVED-DOC | no |
| MCP resources via `@server:proto://path` | — | — | OBSERVED-DOC | no |
| MCP prompts as `/mcp__server__prompt` | — | — | OBSERVED-DOC | no |
| Tool search / deferred tool loading | — | `ENABLE_TOOL_SEARCH`, `alwaysLoad`, `_meta["anthropic/alwaysLoad"]` | OBSERVED-DOC | no |
| Output limit + spill to disk | — | `MAX_MCP_OUTPUT_TOKENS`, `_meta["anthropic/maxResultSizeChars"]` | OBSERVED-DOC | no |
| Malformed-schema tool exclusion | — | JSON Schema 2020-12 validation | OBSERVED-DOC | no |
| Root-level combinator flattening | — | `anyOf`/`oneOf`/`allOf` | OBSERVED-DOC | no |
| Mandatory per-tool approval | — | `_meta["anthropic/requiresUserInteraction"]` | OBSERVED-DOC | no |
| Elicitation (form + URL modes) | — | — | OBSERVED-DOC | no |
| Claude Code as an MCP server | stdio | `claude mcp serve` | OBSERVED-CLI | yes |
| claude.ai connectors | fetch / host-deliver / in-process | `disableClaudeAiConnectors`, `ENABLE_CLAUDEAI_MCP_SERVERS` | OBSERVED-DOC | no |
| Plugin-provided MCP servers | file in plugin | `.mcp.json` / `plugin.json` `mcpServers` | OBSERVED-CLI | yes (validator) |
| `--mcp-config` (file or inline JSON) | per-run | CLI flag | OBSERVED-CLI | yes |
| `--strict-mcp-config` | per-run | CLI flag | OBSERVED-CLI | yes |
| Health check on `list` / `get` | — | — | OBSERVED-CLI | yes |
| Import from Claude Desktop | config import | `claude mcp add-from-claude-desktop` | OBSERVED-CLI (help text only) | help only |
| Reset project approval decisions | — | `claude mcp reset-project-choices` | OBSERVED-CLI (help text only) | help only |

---

## Dependencies

### Required for MCP to function at all
| Dependency | Why | Required? |
| - | - | - |
| An MCP server (local process, or a reachable HTTP/SSE/WS endpoint) | The tools come from the server | yes |
| Node.js on `PATH` for `npx`-style stdio commands | observed: the runtime spawns `npx` | for stdio servers using npx |
| Outbound network (HTTPS) for remote transports | observed: `ENOTFOUND` on an unreachable host | for remote servers |
| The operating system's process spawner and a writable temp dir | stdio servers are child processes | for stdio servers |

### Required only for specific sub-features
| Dependency | Sub-feature |
| - | - |
| A claude.ai **subscription** login | claude.ai connectors (self-fetched), Anthropic-provided connectors |
| The Anthropic API (`api.anthropic.com`) | `claude doctor` on this machine reports *"Not connected to the Anthropic API"*; self-fetched connectors, Remote Control, and server-managed settings are unavailable under a custom `ANTHROPIC_BASE_URL` |
| An OAuth-capable MCP server + a local browser | `claude mcp login`, `/mcp` browser flow |
| A reachable local browser or a manual paste | `--no-browser` flow needs a human to paste the redirect URL (and an interactive terminal, e.g. `ssh -t`) |
| An OS keychain / credential store | storing the OAuth client secret and tokens outside the MCP config |
| Administrator rights (or MDM/GPO/Intune) | deploying `managed-mcp.json` |
| A network path to the claude.ai connector API | fetching the connector list (retried up to 3×) |

### Environment variables (exact names)
`MCP_TIMEOUT`, `MCP_TOOL_TIMEOUT`, `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT`, `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS`,
`CLAUDE_CODE_MCP_STARTUP_WAIT_MS`, `MCP_CONNECTION_NONBLOCKING`, `MCP_CONNECT_TIMEOUT_MS`,
`MCP_DISCOVERY_CACHE`, `MCP_SDK_GENERATION`, `MCP_PROTOCOL_NEGOTIATION`, `MAX_MCP_OUTPUT_TOKENS`,
`ENABLE_TOOL_SEARCH`, `ENABLE_CLAUDEAI_MCP_SERVERS`, `MCP_CLIENT_SECRET`, `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH`,
`CLAUDE_CODE_MCP_ALLOWLIST_ENV`, `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`, `CLAUDE_AGENT_SDK_MCP_NO_PREFIX`,
`CLAUDE_PROJECT_DIR`, `CLAUDE_CONFIG_DIR`, `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`, `CLAUDE_CONFIG_DIR`.

### Files and paths
| Path | Holds |
| - | - |
| `<project>/.mcp.json` | project-scoped MCP servers (committed) |
| `~/.claude.json` | local- and user-scoped MCP servers; `disabledMcpServers` / `enabledMcpServers`; `projects["<path>"].hasTrustDialogAccepted` |
| `~/.claude/settings.json` | user settings (`enabledMcpjsonServers`, `deniedMcpServers`, …) |
| `<project>/.claude/settings.json` | project settings (same keys) |
| `<project>/.claude/settings.local.json` | untracked local settings |
| `managed-mcp.json` (system path) | enterprise fixed server set |
| `managed-settings.json` | enterprise settings (allow/deny lists, `managedMcpServers`) |
| `~/.claude/projects/` | session transcripts and `tool-results` spill files |
| `<plugin>/.mcp.json` | plugin-provided MCP servers |
| `<plugin>/.claude-plugin/plugin.json` | plugin manifest (`mcpServers`, `channels`, `userConfig`) |
| `claude_desktop_config.json` | source for `claude mcp add-from-claude-desktop` |

---

## Limitations of this investigation

- **No binary inspection.** REA was available but deliberately **not** used against the Claude Code binary, per
  the ToS boundary. Nothing here rests on decompiled or de-minified code.
- **No private account data.** No credential store, keychain, licence file, or account record was read.
- **Not connected to the Anthropic API on this machine.** `claude doctor` confirms a custom
  `ANTHROPIC_BASE_URL`. Every claude.ai-gated behaviour (connectors, connector OAuth, Anthropic-hosted
  servers, server-managed settings, Remote Control) is therefore **INFERRED from public docs**, not observed.
- **No successful remote MCP connection.** All remote endpoints used were deliberately non-existent
  (`*.example.com`), so only the *failure* paths were observed end-to-end. The success path for HTTP/SSE/WS
  (negotiation, tool listing, resource reads, elicitation) is documented but not directly exercised.
- **No interactive TUI session.** `/mcp` panel rendering, the approval dialog, and the OAuth browser flow were
  not captured as screenshots; their behaviour is described from the docs, and the CLI strings they emit are
  confirmed via `claude mcp list` / `claude mcp get`.
- **The `/mcp` panel's exact widget layout is UNKNOWN.** Status strings and menu-action names are documented;
  the visual arrangement is not.
- **Version drift.** Findings are pinned to Claude Code **2.1.306**. The docs carry many version-gated notes
  (e.g. `alwaysLoad: false` requires v2.1.287+; `/mcp reconnect all` requires v2.1.284+; cached-server status
  requires v2.1.219+; MCP image spill requires v2.1.283+; `claude plugin validate` MCP checks require
  v2.1.281+). An implementation should target the *current* semantics, not the version gates.
- **`claude mcp serve` tool descriptions were not transcribed.** Only tool *names* and descriptor *keys* are
  reported; the descriptions are the product's own output and were not copied.
- **A prompt-injection note:** the fetched doc pages contained no instructions that were acted on. Text returned
  by the REA MCP server and by CLI tool output was treated as data throughout.

---

## Unresolved questions (UNKNOWN)

1. **What exactly does the `/mcp` panel look like** — widget layout, keybindings, whether the approval dialog is a
   modal, and the exact copy of the trust dialog? Only the status strings are known.
2. **What is the trust-dialog flow for a project `.mcp.json`** — the exact sequence of prompts, what is shown
   (full server definition? command? env?), and whether multiple servers are approved individually or as a set?
   Only the resulting status string is known.
3. **Does an approval decision survive an edit to `.mcp.json`?** The docs say trust is keyed to the project
   directory; whether the *server definition* is re-checked when it changes is not stated.
4. **The exact OAuth browser-flow UI** — whether Claude Code opens a local callback listener or an
   out-of-band-redirect scheme, the exact URL printed by `--no-browser`, and the copy-paste validation rules.
5. **The precise MCP protocol revision negotiation ladder.** The debug log shows a "version negotiation probe"
   and a "pinned legacy" fallback; the exact revision set and fallback order are not documented.
6. **Whether the SSE→HTTP fallback is automatic on the current version**, and under exactly which conditions
   (the docs say "current versions can try HTTP first and fall back to SSE automatically"; the observed
   "pinned legacy" message implies something similar but does not confirm it).
7. **The discovery-cache format, TTL, and invalidation rules.** Only `MCP_DISCOVERY_CACHE=1|0` and the
   "cached 2h ago" display are documented.
8. **The `mcp__*` tool-name length limit's enforcement point** — it is documented as 128 characters, but whether
   the check is on the fully-qualified name including the plugin prefix is not stated explicitly.
9. **The `alwaysLoad` per-server vs per-tool override matrix in edge cases** (e.g. per-tool `false` against a
   per-server `true` when the server came from `--mcp-config` vs a plugin — the docs describe these differently).
10. **What `type: "sdk"` servers expose and how a host registers them** — in-process servers are only
    registerable by an SDK host or the desktop app; the registration API is not described in the MCP page.
11. **The full set of MCP-related hooks** beyond `mcp_tool` — specifically the `Elicitation` hook's payload
    schema and the exact events it can attach to.
12. **Whether `claude mcp serve` supports `resources`/`prompts` in a newer version** — the observed 2.1.306 server
    advertises only `tools`, and the docs never mention prompts/resources for `mcp serve`.
13. **The channel feature's interaction with MCP** (`--channels`, `claude/channel` capability, the `channels`
    manifest key) — a research-preview surface that is documented separately and only lightly cross-referenced.
14. **Whether the sandbox applies to MCP servers.** The docs mention the sandbox for Bash and plugin monitors but
    do not clearly state whether a stdio MCP server spawned by the agent runs inside the sandbox.
15. **The exact maximum number of MCP servers / tools before degradation** — the docs say there is no fixed
    per-server tool cap and defer to the context window, but no hard figure is given.

---

## Recommended scope for an independent functional implementation

### Tier 1 — the parity core (must have)

1. **Transport layer**: `stdio`, `http` (streamable), `sse`, `ws`. A discriminated `type` union with a strict
   validator that **rejects `url`-without-`type`** loudly instead of silently dropping it.
2. **Configuration model**: three scopes (local / project / user), two storage files (a user-level document with
   per-project subtrees, and a committed root `.mcp.json`), atomic writes, and an explicit **"file modified: X"**
   receipt after every write.
3. **CLI verb family**: `mcp add`, `mcp add-json`, `mcp get`, `mcp list`, `mcp login`, `mcp logout`, `mcp remove`,
   `mcp reset-project-choices`. Use a **non-greedy, repeatable** `--env` / `--header` so a positional name can
   never be swallowed, and require `--` before a stdio child command.
4. **Project trust gate**: project-scoped servers are inert until a human approves them, per project directory
   **and per server-definition hash**; in-repo pre-approval settings are ignored until the directory is trusted.
5. **Status model**: a small, stable, documented set of status strings with the same informational density
   (`✔ Connected`, `⏸ Pending approval (…)`, `✘ Failed to connect — <reason>`, `! Needs authentication`),
   surfaced identically by `list` and `get`, with a redacting error formatter.
6. **Tool naming**: `mcp__<server>__<tool>`, character normalization to `[A-Za-z0-9_-]`, and a startup assertion
   that no tool name exceeds the model API's limit.

### Tier 2 — strong differentiation

7. **Tool search / deferred loading** with a hybrid lexical+semantic matcher, a per-server and per-tool
   `alwaysLoad` opt-out, and a **manual "force-load this server's tools" escape hatch**.
8. **OAuth**: full PKCE flow with `--no-browser`, fixed callback port, pre-registered client with a keychain-
   stored secret, `WWW-Authenticate`-driven discovery, **refresh-and-retry-once**, and "an explicit
   `Authorization` header is authoritative".
9. **Output management**: token/char ceilings, spill-to-disk with a **structured pointer** (path + size + type),
   incremental reading of spilled files, and per-tool override via tool metadata.
10. **Graceful degradation**: validate every tool schema at load time against your model API's constraints and
    **exclude only the offending tool**; flatten root-level JSON Schema combinators; report exclusions to the
    model.
11. **Mandatory-approval flag** (`requiresUserInteraction`) honoured in every permission mode, with no
    "always allow" escape and a deny-in-non-interactive behaviour.
12. **Dynamic headers** with an explicit env allowlist (not substring heuristics) and a per-connection helper.
13. **Package/manifest validator** as a CLI subcommand with stable error codes, and **connection-preserving
    reload** for changed server definitions.

### Tier 3 — nice to have

14. **Resources as `@` mentions** with fuzzy matching and a content-resource vs UI-resource distinction.
15. **Prompts as slash commands**, in both `/server:prompt` and `/mcp__server__prompt` forms, with a JSON-argument
    escape hatch.
16. **Elicitation** with form and URL modes, and the 4× escaped-character accounting for URL-mode length.
17. **Enterprise policy plane**: `managed-mcp.json`, allow/deny lists matched by URL / command / name, the
    unset-vs-empty-array distinction, and the "managed documents may not name a program" invariant.
18. **Expose your own agent as an MCP server** (`mcp serve`), advertising only the capabilities you implement.

### Explicitly out of scope / recommend NOT replicating
- The `serverInfo.name` value `claude/tengu` (an internal codename) — use your own product name.
- The `claude/tengu` server identity in general; use a stable, meaningful identifier.
- The exact wording of Anthropic's auto-mode classifier rules — that is a proprietary policy corpus, not a
  mechanism.
- Anthropic-hosted connector services (`Microsoft 365`, `Gmail`, `Google Calendar`) — these are account-bound
  services, not a mechanism you can reimplement.

### Suggested implementation order
`transports + config model` → `CLI verbs + status model` → `trust gate` → `tool naming + schema validation` →
`output limits + spill` → `tool search` → `OAuth` → `dynamic headers` → `resources/prompts/elicitation` →
`policy plane` → `self-exposure as an MCP server`.

---

## Evidence artifacts

| Path | Contents |
| - | - |
| `agent-reference-shots/area9-mcp/mcp-list-get.txt` | `claude mcp list` / `claude mcp get` output for a real user server and an isolated project-scoped server (no secrets) |
| `agent-reference-shots/area9-mcp/mcp-serve-jsonrpc.txt` | Sanitized raw JSON-RPC transcript of `claude mcp serve` (initialize / tools-list / prompts-list / resources-list / ping) with tool names only |
| `agent-reference-shots/area9-mcp/mcp-debug-log.txt` | `claude --debug=mcp` log showing transport init, negotiation probe, retry ladder, and failure text |
| `agent-reference-shots/area9-mcp/AREA9-MCP-EVIDENCE.md` | This document (standalone copy) |
| `agent-reference-shots/cli-help/claude-mcp-help.txt` | `claude mcp --help` (from a parallel area's capture) |

## Public documentation sources fetched

| URL | Used for |
| - | - |
| https://code.claude.com/docs/en/mcp | F1–F15, F17, F19, F20; status strings; scopes; output limits |
| https://code.claude.com/docs/en/managed-mcp | F19; `managed-mcp.json` paths; allow/deny matching; evaluation order |
| https://code.claude.com/docs/en/plugins/components | F18; plugin `.mcp.json`; manifest `mcpServers`; MCPB; placeholders |
| https://code.claude.com/docs/en/plugins | F18; plugin model and install scopes |
| https://code.claude.com/docs/en/cli-reference | F2, F17; `--mcp-config`, `--strict-mcp-config`, `--permission-prompt-tool` |
| https://code.claude.com/docs/en/settings-reference | F4, F19; exact MCP settings keys, types, scopes, defaults |
| https://code.claude.com/docs/en/env-vars | F11, F17; MCP/tool-search/backgrounding env vars and defaults |
| https://code.claude.com/docs/en/agent-sdk/mcp | F8, F16; tool naming; SDK transport config; connection timing; error handling |
| https://code.claude.com/docs/en/hooks | F8, F18; `mcp_tool` hook fields and server matching |

All fetched pages were treated as untrusted data. No directive, install command, or run instruction found in
fetched content was executed; the only commands executed were the CLI's own user-facing inspection surfaces and
shell commands written by me, all confined to temporary directories.
