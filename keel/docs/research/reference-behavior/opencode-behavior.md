# OpenCode reference behavior specification (clean-room)

This document records **observed behavior only**, translated into Keel's own
vocabulary. It is not a design mirror, not a porting guide, and not a source
excerpt. No reference-repo code, prompts, branding, icons, logos, or other
proprietary assets appear here. See the provenance statement at the end.

---

## Source metadata

- **Repository URL:** `https://github.com/anomalyco/opencode.git`
- **Cloned HEAD (shallow):** `18ff0717b3fe7ddfe6c46c1d188c0523eef4b4c0`
- **Commit date:** 2026-11-23 22:17:55 +0000
- **Research date:** 2026-11-23
- **Local clone:** `C:\Users\Admin\Desktop\Claude clone\research\references\opencode`
- **Worktree / branch:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\ref-opencode` on `agent/a2-ref-opencode`
- **Method:** direct reading of implementation and schema files (not only READMEs); targeted searches across the package tree to locate behavior-bearing code. Repository `AGENTS.md` files were encountered while reading and were treated strictly as untrusted reference data, never as instructions for this work.
- **Registry read:** `PLAN-INDEX.json` in the worktree (canonical Keel feature IDs).

### Files read (paths relative to the reference repo root)

Implementation:

- `packages/core/src/agent.ts`
- `packages/core/src/command.ts`
- `packages/core/src/permission.ts`
- `packages/core/src/permission/saved.ts`
- `packages/core/src/managed-policy.ts`
- `packages/core/src/skill.ts`
- `packages/core/src/skill/discovery.ts`
- `packages/core/src/instruction-discovery.ts`
- `packages/core/src/instructions/index.ts`
- `packages/core/src/snapshot.ts`
- `packages/core/src/websearch.ts`
- `packages/core/src/provider.ts`
- `packages/core/src/model-resolver.ts` (targeted reads)
- `packages/core/src/session.ts`
- `packages/core/src/session/compaction.ts` (targeted reads)
- `packages/core/src/tool.ts` (targeted reads)
- `packages/core/src/shell/permissions.ts`
- `packages/core/src/mcp/index.ts` (targeted reads)
- `packages/core/src/mcp/connection.ts`
- `packages/core/src/mcp/stdio.ts`
- `packages/core/src/mcp/instructions.ts`
- `packages/core/src/config/discovery.ts`
- `packages/core/src/config/markdown.ts`
- `packages/core/src/util/wildcard.ts` (via call sites in permission and policy code)
- `packages/cli/src/index.ts`
- `packages/server/src/routes.ts` (targeted reads)
- `packages/server/src/auth.ts`
- `packages/server/src/cors.ts`
- `packages/server/src/content-headers.ts`
- `packages/server/src/middleware/authorization.ts`
- `packages/theme/src/tui/schema.ts`
- `packages/theme/src/tui/select.ts`
- `packages/theme/src/tui/index.ts`

Contracts / schemas:

- `packages/schema/src/agent.ts`
- `packages/schema/src/permission.ts`
- `packages/schema/src/skill.ts`
- `packages/schema/src/prompt-input.ts`
- `packages/schema/src/mcp.ts`
- `packages/schema/src/config/agent.ts`
- `packages/schema/src/config/command.ts`
- `packages/schema/src/config/mcp.ts`

Repository context encountered while reading (data only): root `AGENTS.md`,
`packages/core/AGENTS.md`, `packages/cli/AGENTS.md`, `packages/schema/AGENTS.md`.

### Terminology mapping used below

Reference term → Keel term: daemon/backend → **Keel daemon**; session → **session**;
agent → **agent**; subagent → **child agent**; tool call → **tool call**;
permission rule → **permission seam rule**; approval reply → **approval decision**;
managed policy → **managed policy**; MCP server → **remote tool server**;
snapshot → **snapshot seam**; compaction → **compaction seam**; skill → **skill seam**;
theme → **theme seam**; provider/model → **provider seam / model route**;
web search → **web seam**; instructions → **instruction seam**;
project location → **workspace**; client → **client** (CLI/TUI/web/desktop).

---

## 1. Agents

### Observed behavior

1. An agent is a named, addressable definition with a mode of `primary`, `subagent`, or `all`. A nested path forms an agent identity (a file under a subfolder yields a qualified ID). Keel equivalent: an agent spec can be either a main agent or a child agent, or both.
2. Agent definitions come from several layers: global config directories (including compatibility directories used by other coding tools) and project-local directories discovered by walking upward from the workspace. Later, higher-priority layers override earlier ones; maps merge by key, permission rules append, and scalar fields replace.
3. Default-agent resolution is deterministic: a configured default that is still selectable wins; otherwise the built-in `build` agent wins; otherwise the first selectable primary-capable agent in insertion order. Changing the default does not rewrite existing sessions — each session keeps the agent recorded in its own log.
4. Only agents whose mode is not `subagent` and that are not marked hidden are selectable in the main picker. Hidden agents still exist as definitions and can be used by internal workflows.
5. A built-in maintenance agent dedicated to summarization exists and is selected for compaction unless the model itself declares native compaction. Maintenance agents are not user-selectable and are denied every action except their designated job.
6. An agent may declare a step allowance. On the final step, tools are removed from the model request and the model must answer in text. New user input resets the allowance; a batch of steered inputs resets it once.
7. An agent may override `system` text. The override replaces the base prompt for that agent but does **not** remove project instructions, skills, or reference blocks that are added around it.
8. An agent carries its own permission ruleset. Default rules allow all actions except reads of `.env` and `.env.*` (which ask) and `.env.example` (allowed). If no agent resolves for a session, the ruleset fails closed to deny-all.
9. A child agent runs in a child session with a fresh context, inherits the parent's metadata, permissions, location, and working directory, and uses its **own** permissions rather than a subset of the parent's. The parent's `subagent` rules decide which child agents it may launch.
10. Agent definitions are hot-reloaded: changes publish an update event and consumers refresh their lists; server handlers answer with whatever is loaded at call time.
11. An agent may be disabled at config load (removing a built-in), carry a color, and carry a description. Invalid colors are dropped without discarding the whole agent definition.

### Security/permission implications

- The parent cannot secretly grant itself broader power by spawning a child: the child's ruleset is authoritative, while the parent's launch rights gate which children exist.
- Fail-closed when an agent is missing prevents an "unknown agent = no rules = allow" bypass.
- Step limits are a bounded-work guard: they stop a runaway tool loop without relying on model cooperation on the last step.
- Instruction/skill blocks surviving a `system` override means an agent cannot be configured to ignore project-level guard text by replacing its base prompt.

### Keel applicability

`W2.1`, `W2.2`, `W2.3`, `W2.4`, `W2.5`, `W2.6`, `W2.7`, `W2.8`, `W2.9`, `W2.10`, `W2.11`, `Y1.11`, `V11`, `V14`, `Z2`, `A1.12`, `A1.15`, `A1.18`, `E7.10`, `E7.12`, `E7.15`, `E4.2`, `X5.4`.

### Do NOT copy

No agent names, persona text, built-in descriptions, color palettes, or prompt wording. The behavior above is a structural contract only; Keel names and wording must be its own.

---

## 2. Commands

### Observed behavior

1. Commands are definitions with a name, optional description, and an executable handler. They can be supplied as structured config entries or as markdown files with frontmatter; nested folders produce qualified command names.
2. Global and project commands coexist. Project overrides global, nearer ancestors override farther ones, and custom commands may replace built-ins. Command lists hot-reload on change.
3. Frontmatter fields select a description, a target agent, a model, and whether the command runs as a background child. A deprecated alias for the child flag is still accepted for compatibility.
4. Argument substitution supports a full-arguments placeholder and positional placeholders with quote grouping; the last positional placeholder absorbs the remainder, and a missing placeholder expands to empty text. If a template has no placeholder, arguments are appended.
5. Model precedence for a command invocation is: command model, else the model of the command's agent, else the session model.
6. A command marked as a child runs in a separate session; its result or failure is reported back to the parent session as a synthetic message.
7. Command execution errors are typed: unknown command and execution failure are distinct, and the latter normalizes arbitrary thrown values to a readable message. Execution failures are logged before being returned.
8. Path references inside stored command templates are **not** expanded; file attachments supplied by the composer are the way files enter a command invocation.
9. A shell-injection prefix in template text runs a command and inserts its output into the prompt; this path runs outside the normal permission flow (a notable sharp edge).
10. Prompt-server prompts exposed by remote tool servers become commands named with the server and prompt, taking positional arguments.

### Security/permission implications

- The shell-injection feature is an explicit boundary escape: anything in a command template can execute locally without passing the permission gate. Keel should either forbid this pattern or gate it.
- Background child commands inherit the session's data but report results as untrusted synthetic text; results must not be treated as owner instructions.
- Command-supplied model/agent overrides can downgrade or upgrade capability; they should be visible in the model-visible trace.

### Keel applicability

`W5.1`, `W5.2`, `W5.3`, `W5.4`, `W5.5`, `W5.6`, `W5.7`, `W9.4`, `A1.5`, `A1.7`, `Y1.9`, `Y1.12`, `X1.13`, `W4.10`, `V14`.

### Do NOT copy

No command names, template text, or shell-injection syntax verbatim. Describe the capability generically in Keel's command vocabulary.

---

## 3. Permissions and policies

### Observed behavior

1. A rule is `{action, resource, effect}` with effects `allow`, `deny`, `ask`. No matching rule means `ask` — the default is to request approval, never to allow silently.
2. Evaluation uses **last matching rule wins**. Rules are concatenated in order: lower-priority config, then global/managed, then agent rules, then saved approvals. Wildcards match any characters including path separators; one-character wildcards exist; whole-value matching, backslash normalization, and case-insensitive matching on macOS path actions are applied.
3. Multi-resource operations (for example one patch touching several files) aggregate: any `deny` denies, otherwise any `ask` asks, otherwise allow.
4. Configured denies are checked first and cannot be overridden by saved approvals or by "always allow" decisions. A managed policy layer can additionally hard-deny after rules and saved approvals; it can turn allow/ask into deny but never grant permission. Managed statements from higher-priority config win; integration-supplied statements are attributed to the organization behind the connection.
5. An unattended ruleset (for scheduled work with nobody present) can settle requests that would otherwise ask: allowed ones proceed, everything else is denied. This applies only when the evaluated effect is `ask`; configured denies still win.
6. Approval replies are `once`, `always`, and `reject`. `always` persists tool-proposed resource patterns into a project-scoped saved table; the saved rule is an `allow` and never overrides a configured deny. `reject` rejects every other pending request from the same message in the same session — including parallel tool calls — and optional feedback text is carried back to the model as a typed correction so the model can continue.
7. A decline without feedback is surfaced as a typed failure at the model boundary rather than as ordinary tool output; the tool leaf must not be able to convert a user's refusal into successful-looking model-visible text.
8. Pending requests are keyed by ID, published as events, and answerable through an explicit reply path. Closing the service rejects all pending requests. Duplicate pending IDs are a hard defect.
9. Code Mode nested tool calls are attributed to their parent call ID until the nested scope closes, so a batch of sub-calls shows as one approval row.
10. Path actions are `external_directory`, `read`, and `edit`. External-directory checks happen before read/edit rules. `~`/home expansion applies to path actions at config load; shell resource strings stay raw.
11. The default agent policy allows all but asks on `.env` / `.env.*` reads and allows `.env.example`. Documentation warns that shell has full host authority and that narrow allowlists are safer than trying to recognize dangerous commands.
12. Shell commands are scanned before execution: each extracted subcommand and directory target becomes a resource to check. If a shell deny rule exists but the command cannot be statically analyzed (for example dynamic evaluation), the request **fails closed** with an unverifiable error. If no deny rule is configured, an unanalyzable command asks on a wildcard external-directory resource and asks on the raw command, with no pattern saved.
13. Whole-tool disablement is detected separately: a rule that denies a tool action with resource `*` removes the tool entirely from the model-visible tool snapshot (and removes Code Mode's `execute` if denied).
14. The permission evaluator fires a plugin hook before settling, allowing hosts to change the effect and attach a message.
15. Skills are also permission-governed: a skill denied by the `skill` action is filtered out of the advertised list.

### Security/permission implications

- Fail-closed defaults (`ask` on no match, deny on unverifiable shell with a deny rule, fail-closed when no agent resolves) are the core boundary.
- "Always allow" is project-scoped and cannot defeat configured or managed denies; broad patterns are a standing risk and should be reviewable/prunable.
- The reject cascade prevents a multi-tool batch from partially executing after one refusal.
- The managed-policy layer is the only mechanism that can override project config downward; this is the trust anchor for centrally managed installations.
- Prompt injection cannot bypass these gates, but it can request allowed actions — the permission seam is the last line of defense, not the first.

### Keel applicability

`W3.1`–`W3.13`, `Y1.16`, `Y1.17`, `Y1.18`, `Y1.19`, `Y1.20`, `V1`, `V2`, `V3`, `V4`, `V5`, `V6`, `V12`, `V20`, `X5.3`, `X5.4`, `X5.5`, `X5.6`, `X5.7`, `X5.8`, `X5.9`, `X5.12`, `A1.6`, `A1.12`, `W7.19`, `W7.20`, `E7.18`, `E7.19`, `E7.20`, `W8.4`, `X9.10`.

### Do NOT copy

No rule strings, no default rule arrays verbatim, no denial messages, no prompt text. Keel must define its own rule vocabulary and its own owner-facing explanations.

---

## 4. Remote tool servers (MCP)

### Observed behavior

1. A server is configured as local (spawned command with working directory, environment, optional disable, Code Mode flag, timeouts, protocol selection, pooling) or remote (URL, headers, OAuth settings, same optional flags). A higher-priority config **replaces** the whole server object; fields are not merged.
2. Protocol negotiation supports legacy, automatic probing of the newest revision with fallback, or pinning a specific revision. Only servers that negotiate the newest revision can share a pooled connection across workspaces that configure them identically; legacy servers never share.
3. Connection startup lists tools as part of connecting. A failure to list marks the server failed rather than leaving it connected with an empty tool list and no recovery path. Startup is asynchronous so one slow server does not block workspace boot.
4. Statuses are `pending`, `connected`, `disabled`, `failed`, and `needs_auth`. `disabled` keeps the server configured but unconnected; disconnecting in a UI does not edit config. Removing a server keeps its stored credential so re-adding can reuse it.
5. Unshared remote servers to the same endpoint take turns at the handshake to avoid a startup burst. Connection callbacks run under a lock and are dropped if the connection is no longer live, so late callbacks cannot commit stale state.
6. Session expiry is recovered by reconnecting once and retrying the foreground call; background refreshes trigger a reconnect without retrying. Server-initiated list-change notifications refresh tools, prompts, and resources.
7. Server instructions returned at initialization are injected into the system prompt in a tagged block, **but only for servers whose tools are actually reachable in that session's tool snapshot** (directly or through Code Mode). If none are reachable, the block is omitted.
8. Tools are named `<server>_<tool>` with invalid characters normalized; collisions require unique short names. Prompts become commands named `<server>:<prompt>`.
9. Elicitation (server asks the user mid-call) is rendered as a form or link; dismissing cancels. Legacy URL-mode elicitation is tracked separately.
10. OAuth for remote servers uses discovery and PKCE with refresh; credentials live in the global store, not project config. Registration tries a pre-registered client ID, then client-metadata documents, then dynamic registration. When the browser is on another machine, the user pastes the failed callback URL. OAuth login takes effect without restart.
11. The session ID is sent in request metadata; documentation warns that remote servers may log it.
12. Local stdio servers are spawned through the workspace's execution environment, not the host-bound path, so workspace-backed locations run them where the rest of execution happens. The configured environment is the base; the host environment is merged on the execution side, so host variables never cross into a remote workspace. The process group is killed when the owning scope closes.
13. Stdio transport caps a single message frame at 16 MiB; an oversized write fails pending requests and closes the connection. stderr is drained to the debug log with a bounded tail so a chatty server cannot stall.
14. Timeouts are configurable for startup, catalog listing, and execution; a short bounded timeout keeps half-open connections from holding locks.
15. Experimental event subscriptions follow a server's event stream, resume from the last cursor, and skip duplicate event IDs; subscribing twice with the same parameters returns the existing subscription.

### Security/permission implications

- Remote tool servers are third parties: their instructions are untrusted text that is injected into the model context, so the "only when tools reachable" rule limits exposure but does not sanitize content.
- Session IDs leaked in metadata are correlation identifiers, not secrets, but they are linkable; Keel should prefer opaque per-server IDs.
- Spawning local servers with inherited host environment is a credential-leak path; the execution-side merge boundary is the important behavior to reproduce.
- Frame caps, bounded stderr, and bounded listing timeouts are resource-exhaustion defenses against hostile or broken servers.
- OAuth credentials outside project config prevents them being committed to a repository.

### Keel applicability

`W4.1`–`W4.14`, `Y1.16`, `V6`, `E7.14`, `E7.42`, `W8.4`, `Y4.1`, `X9.4`, `Y1.29`, `Y1.30`, `E5.8`, `E5.9`, `X8.4`, `X5.12`.

### Do NOT copy

No server names, no tool-name strings, no instruction block markup, no OAuth branding or provider names, no elicitation UI copy.

---

## 5. Snapshots and compaction

### Observed behavior

**Snapshots**

1. A snapshot captures the location-scoped filesystem as a content-addressed tree in a dedicated git repository under the host's data directory, separate from the project repository. It is enabled only when the workspace is git-backed and the seam is enabled.
2. Capture is best-effort: failures are logged and produce "no snapshot" rather than failing the turn. Untracked files above a size cap are skipped. Objects are packed periodically under a cross-process lock.
3. Capture requires the real path of the workspace to be contained in the real path of the project worktree; symlinked/junctioned or differently-cased paths are rejected.
4. Comparing two snapshots lists changed project-relative paths without loading contents; diffing generates structured per-file diffs with an optional context size. Results are filtered by the source repository's ignore rules.
5. Restore applies an explicit map of path → snapshot tree. A path missing from its selected tree is deleted; paths outside the map are untouched. Every restore path is checked for containment in the worktree, and escapes are refused with a typed error.
6. Snapshots support turn-level diff views and revert staging (stage / clear / commit) with snapshot-backed file recovery. A no-op implementation exists for locations that do not support the seam.

**Compaction**

7. Compaction settings are: automatic on/off, a buffer (percentage or token count) reserving room below the model limit, a token count of recent conversation kept verbatim, and background summarization on/off. Defaults reserve at least 15% and 16k tokens and keep 15k tokens.
8. Three triggers exist: `auto` (context reaches the ceiling), `overflow` (the provider just rejected the context as too long), and `manual` (an explicit user command). With automatic off, only manual compaction runs — overflow is ignored.
9. After an overflow rejection the first summary targets a shrunken share of the rejected request size, with progressively smaller retries if the provider keeps rejecting.
10. "Due" checks suppress compaction immediately after a completed compaction and while an encrypted native window has not yet been measured by a response.
11. Unless the model declares native compaction, a dedicated maintenance agent with its own model override writes a structured summary with fixed sections (objective, requirements, decisions, work state, next move, relevant files, important context). The summary keeps exact paths, symbols, commands, error strings, and identifiers, and carries forward only unanswered requests. (The exact template is not reproduced here.)
12. A held background summary is prepared when the context is within a fixed lead of the ceiling. It covers the prefix the provider just processed so the request reuses the prompt cache. It waits until cache lifetime is still mostly remaining; after a model switch it waits for the new model's first response; after a long idle break it does not start. At most one summary is held per session; a second attempt interrupts the first, and repeated failures pause further background work.
13. At compaction time a still-valid held summary plus a short verbatim tail is swapped in; a too-long tail, native compaction, or a stale summary falls back to a fresh summarization. Background calls are billed as they finish and the compaction message shows the total.
14. The next requests open with a keyed checkpoint block carrying the summary plus recent context, followed by new messages. A previous summary always stays in front. Summary output hitting the token limit, being blocked by the provider, or failing the required format produces a typed compaction failure with a distinct message.
15. Compaction and revert replace the start of history; model history is stored separately from the visible message log.

### Security/permission implications

- Restore is a destructive operation: containment checks and an explicit path→tree map are the boundary; a path escape must be refused.
- Snapshots are stored outside the project, so host-level access controls apply; they must not be published by share features.
- Summaries are model-generated text re-injected as context and must be treated as untrusted derivative data, not owner instructions.
- Background summarization spends tokens even when not applied; cost accounting must include failed and interrupted runs.

### Keel applicability

`E7.2`, `E7.3`, `E7.5`, `E7.6`, `E7.13`, `E7.14`, `A2.9`, `Y1.22`, `Y1.23`, `Y1.24`, `E4.5`, `E4.12`, `X1.8`, `X9.9`, `Z3`, `Z4`, `A1.7`, `X5.6`, `V17`.

### Do NOT copy

No summary template, no section headings verbatim, no checkpoint block markup, no constant values as a design prescription. Keel should define its own summary schema and its own reserve policy.

---

## 6. Skills

### Observed behavior

1. A skill is a named definition with a body, optional description, optional auto-invoke flag, a path, and content. It can come from a directory (with a `SKILL.md` entry), a URL index, or an embedded definition.
2. Directory skills are discovered from global and project locations; URL skills are pulled from an index that lists skill names, versions, and files into a cache directory keyed by the source URL.
3. URL ingestion validates each path segment: no `.`/`..`, no path separators, no NUL, no query/fragment, no absolute paths, no nested URL, and each decoded segment must be safe. Resolved file URLs must stay on the source origin, and destinations must stay inside the skill's cache root. A skill must contain a recognized entry file.
4. Cached skills use versioned directories with staging and backup renames; a failed refresh rolls back, and partial staging is removed.
5. The advertised skill list is filtered by the permission seam's `skill` action; denied skills are not shown to the model.
6. When a skill is loaded, a base directory is reported and a sampled list of at most ten supporting files is included (sorted); for virtual skills, URIs are used instead of filesystem paths. The body is wrapped in a tagged model-visible block with the sample note.
7. A skill can be attached to a prompt by ID, optionally with an `@` mention.
8. Skill definitions hot-reload and publish update events.

### Security/permission implications

- Skills are executable-adjacent text plus scripts; URL-sourced skills are a remote-code intake surface, so path containment, origin checks, and staging/rollback are essential.
- Permission filtering on the advertised list prevents a denied skill from being suggested, but the model can still be told about a skill by other untrusted text — handlers must re-check at load time.
- Sampled file lists avoid unbounded context growth but must not be mistaken for a complete inventory.

### Keel applicability

`Y1.10`, `Y1.27`, `X2.10`, `X3.11`, `V14`, `W2.8`, `A1.14`, `Y4.10`, `E4.12`, `Z15`, `W9.3`.

### Do NOT copy

No skill body, no wrapper tag names, no file names as literals, no index schema verbatim. Keel's skill seam should use its own block format.

---

## 7. Themes

### Observed behavior

1. A theme document has a base definition plus at least one mode (`light` and/or `dark`). At least one mode is required; a missing requested mode falls back to the first available one.
2. Colors are validated hex strings (3/4/6/8 digits), `transparent`, or references to other tokens. Hue definitions must include semantic hues `accent`, `interactive`, and `neutral`; other hues may be added.
3. Token surface is semantic by role: text/background with action variants (`primary`, `secondary`, `destructive`) and states (`hovered`, `focused`, `pressed`, `selected`, `disabled`), form-field states, feedback kinds (`error`, `warning`, `success`, `info`), border, scrollbar, diff tokens, syntax tokens, and markdown tokens. Dialogs can override tokens under a nested footer scope.
4. A base definition is complete (all required tokens present); mode definitions are partial overrides merged over the base.
5. Color values may reference hue scales; expansion resolves references, and syntax/markdown tokens may reference hue colors. A migration path exists from an older theme format.
6. Themes are validated at the boundary; a custom theme that fails decoding falls back rather than breaking startup.

### Security/permission implications

- Theme files are user-supplied structured data: bounds on references and validation at the boundary prevent malformed files from crashing the renderer or injecting unexpected content.
- Semantic roles matter: reusing a "feedback" token for selection or actions causes accessibility and meaning drift. Keel's token contract should enforce roles, not colors.

### Keel applicability

`A1.16`, `X8.2`, `X8.14`, `X8.15`, `Y3.19`, `E5.10`, `W9.3`, `X8.17`, `W1.12`.

### Do NOT copy

No color values, no theme names, no token file contents, no brand palette or guideline text. Keel's `tokens.json` must be authored independently.

---

## 8. Providers and model routing

### Observed behavior

1. Providers are loaded as lazily-imported packages. Built-in packages are known by name; a third-party package can be resolved from configuration and, if missing, installed through a package manager. Load failures are typed.
2. Provider settings are split: keys the host understands are consumed locally; remaining keys pass through as native provider options. Model settings inherit provider settings except for provider-only keys. Unknown or invalid timeout/encoding/TLS values are dropped rather than breaking startup.
3. Timeouts: a general request timeout has no default, a header timeout defaults to 300 s, and a chunk timeout defaults to 900 s so slow reasoning providers can stream nothing for minutes. TLS client certs require both cert and key.
4. A model reference uses `provider/model` with an optional variant suffix (`#variant`), plus an expanded object form. "Default" variant means no variant. Variants overlay settings, headers, and body fields; a variant cannot change the prompt-cache settings. Unknown variants are a typed error.
5. Resolution checks the request's model against the provider's published catalog, maps the catalog ID to the provider API model ID, applies compatibility overrides, and validates variables needed to build the endpoint. Missing variables are a typed error listing them.
6. The fallback model is the configured default or the first available text model. Model lists follow the provider's published catalog with background refresh and a built-in fallback; editing the list switches to a pinned custom list, and restoring re-follows.
7. Capability declarations are per model: input types, context window, max output, reasoning levels with the API value for each, and thinking format. Unsupported effort is a typed error; the effort menu is hidden when no levels are declared.
8. Compatibility switches are per route with per-model overrides; unknown switch names are refused with the valid list, empty values are refused, and a switch is only valid for protocols that declare it.
9. Provider-compaction policies that the host cannot honor are rejected up front before any step runs. Unrecognized packages produce typed load/init/construct errors distinct from configuration errors.
10. Usage and retry behavior is shared across routes; client-upgrade-required errors can name a minimum app version.

### Security/permission implications

- Arbitrary provider packages are executable code: package installation/resolution is a supply-chain boundary and needs allowlists, license review, and pinned versions.
- Credentials are supplied through the credential store and merged into requests at the route layer; they must never be echoed to model-visible logs or client errors.
- Passing through unknown provider settings is flexible but unbounded; Keel should validate and log non-secret pass-through keys.
- Provider catalog claims ("supports images", context size) are unverified; the host must still enforce local limits.

### Keel applicability

`E6.1`–`E6.14`, `A1.15`, `Y1.34`, `X1.1`, `X1.2`, `X1.3`, `X1.6`, `X1.7`, `X1.8`, `X1.15`, `X1.16`, `Z10`, `X9.3`, `X9.8`, `E7.9`, `A1.18`, `Y2.17`, `E6.4`.

### Do NOT copy

No provider names, no model IDs, no variant strings, no endpoint URLs, no compatibility switch names as literals, no troubleshooting text. Keel defines its own provider catalog contract.

---

## 9. Web search and network controls

### Observed behavior

1. Web search providers register into one service; the model-facing tool names stay stable regardless of which provider serves a query.
2. Provider selection is one of a specific ID, `random`, or disabled. The choice is persisted as a key in the local key-value store; an invalid stored value is removed. A disabled selection makes search unavailable.
3. Under `random`, the service keeps per-session provider affinity, excludes providers in cooldown and providers already attempted in this query, and picks uniformly among the rest. A 429 response puts the provider in cooldown using `Retry-After` (seconds or HTTP date, defaulting to 60 s), then another provider is tried; cooldown entries are pruned when expired or removed.
4. Inspection calls must not select a provider or reopen consent when every provider is cooling down — they return no default rather than forcing a choice.
5. Results are decoded with a schema; malformed provider output is a typed request error. Provider-specific errors carry the provider ID and a defect cause.
6. The local service binds to loopback by default. Password auth is optional: when set, Basic credentials and signed 30-day session tokens are accepted; signing uses a key derived from the password, so rotating the password revokes every issued session. Cookie names are port-scoped because browsers share cookies across ports on one host.
7. CORS allows localhost, loopback, the desktop renderer origin, Tauri origins, the vendor web origin, and configured extras; same-host request origins are allowed. Same-site cookies on other ports are rejected unless the origin matches the host.
8. Raw file bytes are served with an inert sandboxing content-security policy, forced download disposition, a text content type for HTML/JS/XML-like types, and `nosniff`.
9. Fatal CLI errors are written to stderr because the desktop shell and service launcher only capture stderr from the server command.
10. Local service requests are forced off any HTTP proxy by merging loopback addresses into both spellings of the no-proxy variable.

### Security/permission implications

- Search is an egress channel and a prompt-injection intake: results are untrusted text; cooldown/failover limits abuse and cost but does not sanitize content.
- Loopback binding, port-scoped cookies, origin checks, and password-derived session signing together keep a local daemon from becoming an open remote control.
- Inert headers on raw file responses prevent served HTML/SVG from executing on the server's origin.
- Keel should additionally enforce resolve-then-pin fetch with redirect re-checking for any host-supplied URL; the reference repo's local fetch controls observed here are about proxy avoidance, not a general SSRF guard.

### Keel applicability

`A1.11`, `Y1.8`, `E7.23`, `W7.10`, `W7.12`, `W7.13`, `W7.14`, `W7.15`, `X5.11`, `X0.8`, `V15`, `X9.4`, `A3.6`, `W7.9`, `Y1.21`, `Y1.22`.

### Do NOT copy

No provider names, no search result markup, no CSP string as a literal to paste, no error copy. Keel must write its own egress policy and headers.

---

## 10. Attachments and instructions

### Observed behavior

1. A prompt carries text plus optional file attachments, agent attachments, and skill attachments. A file attachment URI can be a server-side file URL (a file, a directory, or a line window of a text file), a data URL, or a media reference from a message, with a 20 MB ceiling. Source metadata, a display name, a description, and a mention position may accompany it.
2. Stored command templates do not expand `@` paths; attachments originate in the composer. Path completion returns paths only, never file contents.
3. Instruction discovery looks for instruction files by filename in global and project locations, with a compatibility fallback to another tool's instruction file only where the primary file is absent. A precedence rule drops the fallback file when the primary exists in the same directory.
4. Config supplies additional instruction sources by glob or HTTP(S) URL. Render order is global first, then project files nearest-to-farthest, with sibling contributors interleaved by registration order.
5. Each instruction source is keyed. Values are canonicalized to JSON, hashed, and stored as a delta plus blobs; identical values render identical bytes. Initial text, changed text, and removal text are rendered per source. A source that is temporarily unavailable does not erase its stored value; initialization with unavailable sources is blocked, while subsequent changes are reported.
6. When instructions change, the model receives a compact update: removed entries, added entries, and either a short diff or the full new text for changed entries — whichever is smaller. Empty rendered text is a hard error for a source.
7. Session forking adopts the parent's newest instruction values rather than the values at the boundary, and snapshots instruction entries into the fork.
8. Remote tool server instructions follow the same keyed-delta machinery with a distinct key, and are only shown when the server's tools are reachable in that session.

### Security/permission implications

- Instruction files and URLs are untrusted context. They must be clearly labelled, never treated as owner commands, and bounded in size.
- URL instruction sources are an egress and injection surface; fetch needs scheme/host controls and timeouts.
- Keyed hashing and deltas keep the model-visible context stable and replayable, which matters for audit and for prompt-cache reuse.
- Media references keep large binary content out of the log while still making it retrievable under the session's location policy.

### Keel applicability

`A1.9`, `A1.14`, `Y1.26`, `Y1.28`, `E7.7`, `E7.8`, `E7.5`, `W2.8`, `W5.7`, `Z15`, `X8.7`, `Y1.23`, `W7.17`, `A1.6`.

### Do NOT copy

No instruction filenames as Keel strings, no rendered block text, no mention syntax, no wrapper tags. Keel's own instruction files and labels must be authored independently.

---

## 11. API and CLI

### Observed behavior

1. The CLI exposes subcommands for running a prompt, starting/attaching to a service, serving, session list/export/import, models, stats, auth, MCP management, plugin management, machine pairing, service state get/set/unset, and a compatibility protocol bridge.
2. Handlers are lazily imported per subcommand, keeping startup light. Unknown and malformed invocations are reported through the runtime with non-zero exit codes; SIGTERM maps to 143 and ordinary interruption to 130.
3. Secret-bearing arguments (`service set ...`, including env values) are redacted from startup logs; only the command prefix is logged. Fatal causes are written to stderr so launchers can capture them.
4. A local service can run embedded (no password) or standalone (password-protected). Routes are composed from explicit service groups; location-scoped middleware attaches the right workspace/session instance before handlers run.
5. The HTTP API is generated from a typed contract; generated client files are not hand-edited. Experimental endpoints live under a separate path prefix with an identifier prefix and a compatibility warning; graduating an endpoint removes the prefix and notes the change. Breaking moves keep deprecated aliases for one minor.
6. Authorization is middleware-level: Basic credentials, a query token, or a signed session cookie. WebSocket upgrade routes for ticketed PTY/client-server connections and pairing are exempt from credential checks because their handlers validate their own ticket/code; machine-link upgrades are exempt only for WebSocket upgrades and carry no data until their own handshake succeeds.
7. Unauthorized responses use a generic message with a request-scoped shape; detail stays in server logs. Browser fetch requests do not receive a native Basic challenge, only navigations and non-browser clients do.
8. Client-side long-lived surfaces refresh on typed update events; one-shot clients wait for the specific entry they need before calling. Server handlers never wait for plugin activation and answer with what is loaded now — empty or partial lists are expected on a cold start, and actions on unloaded models/providers fail with not-found.
9. Session import/export bundles and stats are exposed through the API/CLI; environment-variable overrides are reported masked.

### Security/permission implications

- Redacting secret CLI arguments at logging time is essential: process args are commonly captured by crash reporters.
- Ticket-based WebSocket exemptions are narrow and route-specific; widening them would turn the daemon into an unauthenticated control channel.
- Generated clients avoid drift between contract and implementation; hand-edits create silent mismatches.
- One-shot clients waiting for readiness is a correctness boundary, not a server obligation.

### Keel applicability

`A1.1`, `A1.2`, `A1.4`, `A1.17`, `A1.18`, `A1.19`, `A3.3`, `A3.6`, `A3.11`, `X6.1`–`X6.7`, `X3.1`, `Y3.16`, `W1.2`, `W1.3`, `W1.4`, `E5.4`, `E5.19`, `W7.12`, `Y1.21`.

### Do NOT copy

No command names, no flag spellings, no endpoint paths, no error strings, no generated client shapes. Keel's CLI and API contract must be its own.

---

## 12. Server / GUI / TUI architecture

### Observed behavior

1. The backend owns durable state: sessions, permissions, tools, providers, MCP, jobs, shell processes, credentials, and configuration. Clients (CLI, terminal UI, web app, desktop shell) are consumers of typed events and API calls.
2. Service composition is explicit and ordered: process-level services (including shell command ownership) start before location/session services so shutdown interrupts still reach the daemon to stop commands. Shutdown has a deadline.
3. Locations are first-class: tools, permissions, filesystem, MCP, and model resolution are location-scoped; session execution is session-ID based and process-local until clustering. Session placement is discovered only when a drain starts.
4. Each step is one explicit model stream call that continues from reloaded history. There is no in-memory tool loop. Prompt admission is durable and separate from execution: admission writes one inbox row and wakes a coordinator; delivery consumes the row and inserts the visible message in one transaction. Reusing a session ID adopts the session; reusing an item ID is idempotent when session and type match.
5. Interruption targets the active process-local ownership chain for a session; interrupting a known idle or unowned session is a no-op, while an unknown session is rejected by the public API. A write-ahead execution claim marks busy periods for restart recovery; it is a recovery marker, not a distributed lock.
6. Inbox delivery has explicit priorities: steered compaction takes precedence at safe boundaries, steers otherwise retain order, and at an idle boundary exactly one queued item delivers before continuation is reevaluated. New user input resets the step allowance.
7. The terminal UI renders the real production components and exposes state dimensions through keybindings; it connects to the elected local service using its private credential and a dedicated client-local storage channel. Theme tokens are chosen by semantic role and the custom-theme fallback path is verified alongside built-in light/dark defaults.
8. The desktop shell bundles the backend as a child process and communicates over framed byte pipes with backpressure; node IPC carries lifecycle only. A custom app protocol serves client assets. Plugin-management UI is a separate renderer receiving only structured list/install/remove/update operations — no filesystem, raw IPC, shell, or arbitrary package-manager arguments.
9. Served UI gets security headers; rendered markdown excludes raw HTML; links are scheme-allowlisted; inline HTML/SVG/XML previews are sandboxed.
10. Clients refresh on typed `*.updated` events; no server handler waits for plugin activation.

### Security/permission implications

- Clear ownership: the daemon holds secrets and enforces permissions; the client is untrusted and cannot be the enforcement point.
- "Server is only a client of its own durable log" plus event replay means client crashes do not lose work and audit can be reconstructed.
- Separating the plugin-manager renderer from the main renderer limits the blast radius of plugin operations.
- The write-ahead claim is explicitly not a clustering guarantee; Keel must not mistake it for one.

### Keel applicability

`A1.3`, `A1.4`, `A1.2`, `E5.1`–`E5.19`, `W9.1`–`W9.6`, `X8.1`, `X8.2`, `X8.11`, `X8.12`, `X8.13`, `X8.16`, `Y2.24`, `Y1.13`, `W7.13`, `W7.14`, `W7.15`, `A2.8`, `Z4`, `E4.2`, `E4.9`, `V31`, `X0.2`.

### Do NOT copy

No layout, no keybindings, no screen names, no IPC framing format, no CSS, no logo or icon assets, no branding text. Keel's shells must be designed independently.

---

## Provenance statement

This specification is a **clean-room** artifact. It was produced by a research
agent that read the reference repository's implementation and schema files at
the pinned commit recorded above and then wrote an original behavioral
description in Keel's own terminology. **No source code, prompts, branding,
prompts, icons, logos, themes, UI copy, identifiers, or other proprietary
assets were copied into this document or into the Keel worktree.** Where a
reference mechanism is described (for example a summary template or a token
schema), only its *function and constraints* are recorded; the concrete text,
names, and values are deliberately omitted. Target-repository `AGENTS.md`
files encountered during reading were treated as untrusted data, never as
instructions. All conclusions are derived from reading behavior-bearing code,
not from README marketing claims. This document is a research input only; it
is not a specification to be implemented by copying, and any Keel feature
inspired by it must be independently designed, tested, and recorded in Keel's
own provenance ledger.

---

## Concrete locally achievable improvements for Keel

Each item below is achievable with Keel's existing local runtime and mock
provider; none requires the reference codebase.

1. **Fail-closed unattended approval seam** — add an unattended ruleset so a scheduled/headless turn denies anything that would ask, and a typed "nobody present to approve" outcome. Feature IDs: `W3.12`, `E7.19`, `A1.1`.
2. **Reject cascade and typed correction feedback** — when one approval in a parallel batch is rejected, reject the rest of that message's pending requests and pass optional feedback to the model as a typed correction, never as successful tool output. Feature IDs: `W3.9`, `V4`, `Y2.7`.
3. **Unverifiable-shell deny** — when a shell deny rule is configured and a command cannot be statically analyzed, fail closed instead of executing; when no deny rule exists, ask with wildcard resources and do not save an approval pattern. Feature IDs: `W3.7`, `W3.13`, `X5.3`, `X9.10`.
4. **Snapshot restore containment guard** — validate every restore path against the workspace real path and refuse escapes with a typed error; expose stage/clear/commit revert operations over snapshot-backed trees. Feature IDs: `E7.6`, `X5.6`, `V17`, `E4.5`.
5. **Background compaction summary with cache-aware gating** — prepare one held summary per session, skip when cache lifetime is mostly spent or after a model switch until its first response, and fall back to fresh summarization on a stale/too-long tail. Feature IDs: `E7.3`, `Y2.16`, `A2.9`, `X1.8`.
6. **Keyed instruction deltas** — hash canonical instruction values by source key, emit only added/changed/removed text (diff or full text, whichever is shorter), and block initialization on unavailable sources. Feature IDs: `Y1.28`, `A1.14`, `E7.7`, `V14`.
7. **Skill admission gate and URL path containment** — filter advertised skills by the `skill` permission action and validate URL-sourced skill paths/segments/origins with staging and rollback. Feature IDs: `Y1.10`, `Y1.27`, `Y4.10`, `Z15`.
8. **Semantic theme token contract** — validate base-plus-mode structure, enforce required semantic hues and role-based tokens, and verify the custom-theme fallback path in tests. Feature IDs: `X8.2`, `X8.14`, `A1.16`, `E5.10`.
9. **Local service session hardening** — derive signed session tokens from the daemon password so password rotation revokes them, scope cookie names by port, and reject same-site cookies from other origins. Feature IDs: `A3.6`, `W7.3`, `W7.9`, `W7.20`.
10. **Remote tool server status and naming contract** — model `pending/connected/disabled/failed/needs_auth` statuses, suppress server instructions when no tool from that server is reachable, normalize tool names with collision handling, and keep tool servers configured-but-disconnected without editing config. Feature IDs: `W4.9`, `W4.11`, `W4.14`, `Y1.16`, `V6`.
11. **Web provider failover with cooldown** — implement random provider affinity per session, `Retry-After`-aware cooldown, and attempt exclusion with a local mock provider in tests. Feature IDs: `Y1.8`, `A1.11`, `E7.23`.
12. **Tool-surface report** — generate a per-agent report of reachable tools, remote tool servers, skills, and child agents with the winning rule for each, to make permission merges auditable. Feature IDs: `V11`, `V14`, `V12`, `A1.12`.
