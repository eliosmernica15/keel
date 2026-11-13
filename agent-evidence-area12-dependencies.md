# Area 12 — Capability dependencies: network, account, model provider, external services

**Area:** #12 of the investigation plan — which capabilities require network
access, a supported account, a model provider, or external services.

**Product:** Claude Code 2.1.306 (native build, win32-x64, commit `01ae8327ca99`).
**Method:** public documentation at `code.claude.com/docs/en/...` + black-box
observation of the published CLI's own user-facing surfaces
(`--help`, `doctor`, `auth status`, `mcp`, `plugin`, `agents`, `auto-mode`).
**Compliance:** no decompilation, no source extraction, no credential reads.
See `../TERMS-NOTES.md`.

> **Machine caveat (materially affects this area).** This machine runs against
> a **custom `ANTHROPIC_BASE_URL`** — a third-party gateway serving
> `minimax/minimax-m3.1-flash:free` — not `api.anthropic.com`.
> `claude doctor` states plainly:
> *"Remote Control is only available when using Claude via api.anthropic.com.
> ANTHROPIC_BASE_URL is set and does not point at api.anthropic.com…"*
> and *"Not connected to the Anthropic API (api.anthropic.com)"*.
> `claude auth status --text` confirms:
> `Auth token: ANTHROPIC_AUTH_TOKEN` / `Anthropic base URL: https://openrouter.ai/api`.
> Every subscription-gated behaviour is therefore **INFERRED from docs**, not
> observed. This area is unusually dependent on that distinction, so each
> finding is labelled individually.

---

## 1. Executive summary

Claude Code is **not** a self-contained program. Even its most basic action —
one model turn — requires a resolved credential, a reachable model endpoint,
and a model that can tool-call. The dependency structure falls into four
distinct tiers, and the tiers are *not* all the same kind of dependency:

| Tier | What it needs | Failure mode |
|---|---|---|
| **Tier 0 — no dependency** | Local file/shell machinery, skills, CLAUDE.md, hooks (local), permissions, checkpointing, `--tools ""` | Fully works offline (with a model for the turn) |
| **Tier 1 — one model provider** | A chat/completions endpoint that speaks Anthropic's tool-use protocol | Total failure of the core loop; *everything* else still works |
| **Tier 2 — an Anthropic account** | claude.ai OAuth login, a plan, and `api.anthropic.com` | Those features are *removed*, not degraded — the tool is simply absent |
| **Tier 3 — an external service** | GitHub, an npm registry, a package registry, a cloud VM, a Datadog endpoint | Feature-specific failure; the rest of the product is unaffected |

The single most important architectural fact for an independent implementation
is that **Tier 2 features fail by subtraction, not by error**. The docs are
explicit that `WebFetch` "is withheld until it can confirm that your
organization allows it", and the tool table shows `RemoteTrigger` ("not
accessible from Amazon Bedrock…"), `PushNotification` ("not accessible from
Amazon Bedrock…"), `SendUserFile`, and `Artifact` ("Requires a Pro, Max, Team,
or Enterprise plan and `/login` authentication") are simply **absent** from
the model's tool set. An implementer must therefore model capability
availability as a **compile-time filter on the tool registry**, not as a runtime
error path.

The second key fact: **the provider abstraction is first-class but not
uniform.** The docs maintain a strict 3×N availability matrix, and the same
feature can be *fully available* on one provider, *partially available* on
another, and *absent* on a third. `WebSearch` is ✓ on Claude subscription, ✓ on
Console, ✗ on Bedrock, ✓ on Claude Platform on AWS, and model-gated on Vertex.
`Auto mode` is ✓ everywhere but only for Sonnet 5+ / Opus 4.7+ / Haiku 5.5 /
Fable on the third-party providers. An implementer should plan for a
**capability matrix keyed by (provider, model, plan)**, not a single boolean.

The third key fact, and the one with the widest blast radius: **`ANTHROPIC_BASE_URL`
pointing anywhere other than `api.anthropic.com` silently disables a whole
family of features.** From the feature-availability doc:

> "Whenever `ANTHROPIC_BASE_URL` points at a host other than
> `api.anthropic.com`, Claude Code turns off features such as Remote Control
> and server-managed settings, whatever the gateway forwards."

And from `claude doctor` on this very machine, the same mechanism produces
four separate disabled behaviours at once: Remote Control unavailable,
managed settings "not fetched", organization policy "not fetched", and
claude.ai subscription auth "not active". **A clean-room implementation must
treat the base URL as a first-class input that gates features**, not merely as
an endpoint override.

Fourth: **network dependencies are separable and individually disablable.**
There are at least 18 distinct hostnames the product may contact, and
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` collapses the optional ones. The
one check that is *not* covered by that flag is the **WebFetch domain safety
check**, which posts the target hostname to `api.anthropic.com` on every fetch
and is unaffected by the traffic flag, by `DISABLE_TELEMETRY`, by
`DISABLE_ERROR_REPORTING`, and by `DO_NOT_TRACK`. This is a hard dependency of
the WebFetch tool on the Anthropic API even when everything else runs on a
third-party gateway — a subtle and important coupling.

Fifth: **the model provider is not the only "model provider".** A second,
distinct provider dependency exists for the **auto-mode classifier** and the
**advisor tool**, which are separate model calls with their own env-var
selectors (`CLAUDE_CODE_AUTO_MODE_MODEL`, `CLAUDE_CODE_AUTO_MODE_SERVER=0`),
their own billing (`auto-mode-classifier-billing`), and their own provider
availability rows (Advisor is ✗ on all four third-party providers). A
subagent also runs on a *different* model than its parent — the built-in
Explore subagent "runs on Opus with a Claude subscription, an Anthropic
Console account, or an LLM gateway… On other providers… it runs on Fable."
Any faithful implementation needs a notion of **per-role model routing**, not
a single session model.

**Recommended scope:** implement Tier 0 and Tier 1 fully and make the
capability matrix a first-class data structure. Implement Tier 2 features as
*gated-absent* rather than as stubs. Treat Tier 3 (cloud sessions, ultrareview,
Remote Control, Code Review, Slack, Chrome) as out of scope for a
clean-room reimplementation — they require Anthropic-hosted infrastructure that
cannot be independently reproduced at all.

---

## 2. Findings

### F1 — The core loop has exactly one hard dependency: a reachable model endpoint

**Status: OBSERVED-DOC** (+ OBSERVED-CLI for the negative case)

**Claim.** Every Claude Code turn requires a model provider that can serve
tool-use. Nothing else is mandatory for local operation. The credentials may
come from a subscription OAuth token, an API key, an auth token, a helper
script, a federation profile, or a third-party cloud provider.

**Evidence.** The authentication doc's precedence list enumerates seven
credential sources and their headers:

| Rank | Source | How it is sent |
|---|---|---|
| 1 | `CLAUDE_CODE_USE_BEDROCK` / `_VERTEX` / `_FOUNDRY` | provider-specific |
| 2 | `ANTHROPIC_AUTH_TOKEN` | `Authorization: Bearer` |
| 3 | `ANTHROPIC_API_KEY` | `X-Api-Key` |
| 4 | `apiKeyHelper` | script output |
| 5 | `CLAUDE_CODE_OAUTH_TOKEN` | long-lived OAuth token |
| 6 | Anthropic profile / federation credentials | WIF exchange |
| 7 | Subscription OAuth from `/login` | default for Pro/Max/Team/Enterprise |

A gateway sign-in "sits outside this list: it is a provider selection… and it
outranks them."

**Observed on this machine** (`claude auth status --text`, saved to
`agent-reference-shots/area12-dependencies/auth-status.txt`):

```
Auth token: ANTHROPIC_AUTH_TOKEN
Anthropic base URL: https://openrouter.ai/api
```

and (`claude auth status --json`):

```json
{"loggedIn":true,"authMethod":"oauth_token","apiProvider":"firstParty",
 "analyticsDisabled":false,
 "projectsDirectory":"C:\\Users\\Admin\\.claude\\projects",
 "configDirectory":"C:\\Users\\Admin\\.claude"}
```

Note the tension: `authMethod` is `oauth_token` yet `apiProvider` is
`firstParty` — the provider classification reflects the *credential type*, not
the actual endpoint being called. This is a real trap for implementers: the
provider in use is determined by the base URL, not by the credential.

**Clean-room opportunity.** Design the provider layer as a small interface
(`complete(model, messages, tools) -> stream`) with pluggable
implementations (Anthropic-API, OpenAI-compatible, local), selected by
base-URL + credential, rather than hard-coding one vendor. Implement the
credential precedence list as an explicit, testable ordered resolution — the
order matters and is user-visible via `/status`.

---

### F2 — `ANTHROPIC_BASE_URL` is a capability gate, not just an endpoint override

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Claim.** Pointing the base URL at anything other than `api.anthropic.com`
turns off a specific, enumerated set of features regardless of what the
gateway forwards.

**Evidence (docs).** From the feature-availability doc:

> "If you authenticate through an LLM gateway, feature availability matches
> the underlying provider the gateway forwards to, except for the features
> Claude Code itself turns off. Whenever `ANTHROPIC_BASE_URL` points at a host
> other than `api.anthropic.com`, Claude Code turns off features such as
> Remote Control and server-managed settings, whatever the gateway forwards.
> Some Anthropic-only features such as the Advisor work only if the gateway
> forwards requests intact to the Anthropic API."

Remote Control's requirements page repeats it as a hard precondition: it "is
not available in any of these configurations: … You point `ANTHROPIC_BASE_URL`
at a host other than `api.anthropic.com`."

**Evidence (observed).** `claude doctor` on this machine, verbatim
(saved to `agent-reference-shots/area12-dependencies/claude-doctor.txt`):

```
Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL
Organization policy: not fetched with a custom ANTHROPIC_BASE_URL

Remote Control
Remote Control is only available when using Claude via api.anthropic.com. ANTHROPIC_BASE_URL is set and does not point at api.anthropic.com, so this session is using a custom endpoint — unset it (or run in a shell without it) to use Remote Control.
- Not connected to the Anthropic API (api.anthropic.com)
- Not signed in to claude.ai
- claude.ai subscription auth not active
- Sign-in is missing the user:profile scope
- Organization not resolved
- Remote Control availability could not be verified (no server response this session)

No installation issues found.
```

This is the clearest single artifact in the whole investigation: one
environment variable produces **five** distinct disabled behaviours, each
reported with a specific reason.

**Clean-room opportunity.** Make provider identity a first-class value
(`ProviderKind` enum) computed once at startup from base URL + provider
env-vars, and have it drive a **capability filter** applied when building the
tool registry. Expose the reason per capability in a `doctor`-style
diagnostic — that is the single most useful debugging surface in the product
and is trivially reproducible.

---

### F3 — Tier 2 features fail by *subtraction*: the tool is absent from the registry

**Status: OBSERVED-DOC** (+ OBSERVED-CLI corroborating the mechanism)

**Claim.** Features requiring a claude.ai account are not disabled with an
error; they are removed from the model's tool set entirely, so the model
never attempts them and never explains their absence.

**Evidence.** From the tools reference table:

| Tool | Dependency stated in the doc |
|---|---|
| `Artifact` | "Requires a Pro, Max, Team, or Enterprise plan and `/login` authentication" |
| `RemoteTrigger` | "Cloud scheduled tasks live on claude.ai and require a Pro, Max, Team, or Enterprise plan. This tool is therefore not accessible from Amazon Bedrock, Claude Platform on AWS, Google Cloud's Agent Platform, or Microsoft Foundry" |
| `PushNotification` | "Push delivery runs through Anthropic-hosted infrastructure, which is not accessible from Amazon Bedrock, Claude Platform on AWS, Google Cloud's Agent Platform, or Microsoft Foundry" |
| `SendUserFile` | "Delivery runs through Anthropic-hosted infrastructure, so the tool is not available on Amazon Bedrock, Google Cloud's Agent Platform, or Microsoft Foundry" |
| `ShareOnboardingGuide` | "Available to claude.ai subscribers on Team and Enterprise plans" |
| `ListAgents` | "appears only in sessions where cross-session messaging is enabled" |

And from the WebFetch section — a particularly instructive case, because the
tool is present but *withheld*:

> "If WebFetch is missing from a session, run `/status` in the session. If its
> `Organization policy` line reports that the policy didn't load and names web
> fetch among the features that wait for it, Claude Code is withholding WebFetch
> until it can confirm that your organization allows it. Outside a session,
> `claude doctor` makes its own request and prints the same line. Once a policy
> that allows WebFetch loads, the tool returns without a restart."

**Corroborating mechanism (OBSERVED-CLI).** The `init` event's `tools` array
is the tool registry handed to the model. In the default run on this machine
it contained 27 tools; the `system`/`init` event also carries
`mcp_servers`, `plugins`, `agents`, `skills` — i.e. every available
capability is enumerated in one machine-readable object at session start.
That single event is the cleanest possible place to implement a capability
filter.

**Clean-room opportunity.** Emit a single `init`-equivalent event listing the
resolved tool registry, and compute that registry from a declarative
capability matrix at startup. Implement "withheld pending policy" as a
distinct third state (available / withheld-pending / absent) so the UI can
distinguish "not entitled" from "not yet known".

---

### F4 — The provider × feature matrix is genuinely non-uniform, and must be modelled as data

**Status: OBSERVED-DOC**

**Claim.** The same feature is fully available, partially available, or
absent depending on provider, and sometimes on the *model* within a provider.

**Evidence.** The feature-availability doc's "CLI capabilities that vary by
provider" table (✓ = available, ✗ = not available):

| Feature | Subscription | Console | Bedrock | Claude Platform on AWS | Vertex | Foundry |
|---|---|---|---|---|---|---|
| Web search | ✓ | ✓ | **✗** | ✓ | model-gated¹ | ✓ |
| Fast mode | ✓ | ✓ | **✗** | **✗** | **✗** | **✗** |
| Auto mode | ✓ | ✓ | partial² | ✓ | partial² | partial² |
| Advisor | ✓ | ✓ | **✗** | **✗** | **✗** | **✗** |
| Cross-session messaging | ✓ | ✓ | same-machine | same-machine | same-machine | same-machine |
| Channels | ✓ | ✓ | **✗** | **✗** | **✗** | **✗** |
| GitHub Actions | ✓ | ✓ | ✓ | **✗** | ✓ | ✓ |
| GitLab CI/CD | ✓ | ✓ | ✓ | ✓ | ✓ | **✗** |

¹ "On Google Cloud's Agent Platform, web search is available for Opus 4, Sonnet 4, Haiku 4.5, and later models."
² "On these providers, auto mode supports only Claude Sonnet 5 or later, Opus 4.7 or later, Haiku 5.5, and the Fable models."

Also provider-specific *within* features that are otherwise universal:
"connectors from claude.ai load only when your claude.ai subscription is the
active authentication method"; tool search "isn't supported on Microsoft
Foundry deployments hosted on Azure" and "isn't supported on models earlier
than Claude Opus 4.5, Claude Sonnet 4.5, and Claude Haiku 4.5" on Vertex.

**Clean-room opportunity.** Represent availability as
`Availability(provider, plan, model, feature) -> {full, partial, none}` with
an optional note, loaded from a data file. This makes the matrix auditable
and lets an implementer degrade gracefully (e.g. "web search unsupported on
this provider — use the WebFetch tool instead", which the doc itself
recommends as the Bedrock alternative).

---

### F5 — A second, independent model provider exists for the safety classifier and the advisor

**Status: OBSERVED-DOC**

**Claim.** The auto-mode classifier and the advisor tool are *separate model
calls* with their own model selector, their own server/local toggle, their own
billing, and their own provider availability. They are not the session model.

**Evidence.**

- `CLAUDE_CODE_AUTO_MODE_MODEL` — "Selects the model used for auto-mode
  classifier requests."
- `CLAUDE_CODE_AUTO_MODE_SERVER` — "Set to `0` to use local classifier
  requests instead of server review."
- The advisor tool is ✗ on Bedrock, Claude Platform on AWS, Vertex, and
  Foundry — available only on Claude subscription and Console.
- There is a dedicated docs page
  `/docs/en/auto-mode-classifier-billing` ("Auto mode classifier request
  charges"), confirming the classifier is metered separately.
- `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` — "Disables the advisor tool and
  `/advisor` command."

**Cross-check (OBSERVED-CLI).** The auto-mode rule set dumped by
`claude auto-mode defaults` is a large, hand-authored policy document
(hundreds of rules across `allow` / `soft_deny` / `hard_deny` / `environment`)
that reads like a rubric for a judge model, not like a deterministic matcher —
e.g. rules keyed on judgement ("Blocking requires one of these shapes…",
"Judge the change by what it sets running, not only by its bytes"). This is
consistent with a model-based classifier and inconsistent with a pure
regex engine.

**Clean-room opportunity.** Implement the safety classifier as a *separate
model call* behind its own interface, with its own model selection, its own
timeout/failure policy, and a deterministic-rule fast path for unambiguous
cases. Importantly: make the classifier's failure mode **fail-closed** (deny)
and make that choice explicit, because a classifier that silently fails open
is a safety hole.

---

### F6 — Subagents can run on a different model than their parent session

**Status: OBSERVED-DOC**

**Claim.** Model routing is per-role, not per-session. The built-in Explore
subagent runs on a different model depending on the provider.

**Evidence.** From the feature-availability doc, under "provider-specific
differences":

> "**Subagents**: when the main conversation runs Fable, the built-in Explore
> subagent runs on Opus with a Claude subscription, an Anthropic Console
> account, or an LLM gateway reached through `ANTHROPIC_BASE_URL`. On other
> providers, including Claude Platform on AWS, it runs on Fable."

Related env vars confirm the multi-model design:
`ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`,
`ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_DEFAULT_FABLE_MODEL`,
`ANTHROPIC_SMALL_FAST_MODEL` (deprecated) — the last being the
**background-task model**, i.e. a *third* distinct model role alongside the
session model and the classifier model.

**Clean-room opportunity.** Implement a model-resolution function
`resolve_model(role, session_model, provider) -> model_id` with roles
`{session, subagent, background_task, classifier, advisor}`. The CLI already
exposes the surface (`--model`, `--fallback-model`, `--effort`,
`--autocompact`), so a matching design is natural.

---

### F7 — The network allowlist is large, enumerated, and per-feature

**Status: OBSERVED-DOC**

**Claim.** The product documents 18+ distinct hostnames it may contact, each
mapped to the feature that needs it. This is the canonical dependency list for
a clean-room implementation.

**Evidence** — the "Network access requirements" table (abridged, with the
feature each host serves):

| Host | Required for |
|---|---|
| `api.anthropic.com` | API requests, **WebFetch domain safety check**, feature-flag fetches, telemetry |
| `claude.ai` | claude.ai account authentication |
| `claude.com` | claude.ai sign-in page redirect; pre-approved WebFetch doc lookups |
| `platform.claude.com` | Console auth; OAuth token exchange, refresh, revocation |
| `sso.claude.com` | SSO browser sign-in flow |
| `mcp-proxy.anthropic.com` | claude.ai MCP connectors |
| `downloads.claude.ai` | plugin downloads; native installer; auto-updater; update checks |
| `storage.googleapis.com` | plugin install counts/metadata; installer (pre-2.1.116) |
| `registry.npmjs.org` | plugin installs; npx-launched MCP servers; npm/bun installs of Claude Code itself |
| `bridge.claudeusercontent.com` | Claude in Chrome extension WebSocket bridge |
| `*.frame.claudeusercontent.com` | artifact content reads |
| `github.com` | cloning GitHub-hosted plugin marketplaces and plugins |
| `raw.githubusercontent.com` | changelog feed for `/release-notes` |
| `*-review.googlesource.com` | Gerrit change lookup (Desktop Code tab only) |
| `http-intake.logs.us5.datadoghq.com` | operational telemetry (Anthropic API only) |
| `browser-intake-us5-datadoghq.com` | operational error reports |
| `formulae.brew.sh` | update checks (Homebrew installs only) |
| `code.claude.com` | docs lookups by the built-in guide agent and pre-approved WebFetch |

The doc also states: "Claude Code never sends its WebSocket connections to
`localhost`, `::1`, or `127.0.0.0/8` through the proxy" and "Claude Code does
not support SOCKS proxies."

**Clean-room opportunity.** Publish an equivalent allowlist as machine-readable
data and — better than the reference product — make the *reason* each host is
required part of the data, so a user can compute the minimum allowlist for
the features they actually use. Add a `--print-network-requirements` style
diagnostic.

---

### F8 — The WebFetch domain safety check is an unavoidable Anthropic API call, exempt from every traffic opt-out

**Status: OBSERVED-DOC**

**Claim.** WebFetch posts the target hostname to `api.anthropic.com` for a
safety blocklist check before every fetch. This call is **not** covered by
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_TELEMETRY`,
`DISABLE_ERROR_REPORTING`, or `DO_NOT_TRACK`. The only escape is
`skipWebFetchPreflight: true` in settings.

**Evidence.** From the data-usage doc:

> "Before fetching a URL, the WebFetch tool sends the requested hostname to
> `api.anthropic.com` to check it against a safety blocklist maintained by
> Anthropic. Only the hostname is sent, not the full URL, path, or page
> contents. Claude Code caches a hostname that passes the check for five
> minutes, and re-checks a blocked or failed hostname on the next request.
>
> This check runs regardless of which model provider you use and is not
> affected by `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`. If your network
> blocks `api.anthropic.com`, WebFetch requests fail until you either
> allowlist the domain or set `skipWebFetchPreflight: true`."

And the per-provider defaults table confirms the check is "Default on" for
**all five** providers, unlike metrics/error reports which default off on the
third-party providers.

The network-config doc adds the twist: on Bedrock/Vertex/Foundry/gateway
sessions, "The WebFetch tool still calls `api.anthropic.com` for its domain
safety check unless you set `skipWebFetchPreflight: true`."

**Clean-room opportunity.** This is a coupling most implementers would
miss. A clean-room agent that routes everything through one provider would
inadvertently send every fetch target to that provider. Decide deliberately:
either implement a local blocklist (no external call), or replicate the
behaviour but make it **off by default** with a clear, documented opt-in —
a design improvement over the reference product, which hard-wires it on.

---

### F9 — Telemetry is a separate, per-provider, per-service dependency with four independent opt-outs

**Status: OBSERVED-DOC**

**Claim.** Two operational telemetry services (metrics and error reports)
plus `/feedback` and the session-quality survey each have their own default
state per provider and their own opt-out variable.

**Evidence.** From the data-usage doc's "Default behaviors by API provider"
table:

| Service | Claude API | Vertex | Bedrock | Foundry | Claude Platform on AWS |
|---|---|---|---|---|---|
| Metrics | on | off¹ | off¹ | off¹ | off¹ |
| Error reports | on (Pro/Max, v2.1.198+) | off¹ | off¹ | off¹ | off¹ |
| `/feedback` reports | on | off¹ | off¹ | off¹ | off¹ |
| Session quality surveys | on | **on** | **on** | **on** | **on** |
| WebFetch domain safety check | on | on | on | on | on |

¹ "must be 1" (i.e. the provider env var must be set).

Opt-out variables: `DISABLE_TELEMETRY`, `DISABLE_ERROR_REPORTING`,
`DISABLE_FEEDBACK_COMMAND`, `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY`,
`DO_NOT_TRACK`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`.

Crucially, the doc notes the blast radius of the aggregate flag:
"`DISABLE_TELEMETRY` or `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` also
disables feature-flag evaluation, which can make Remote Control unavailable;
`DISABLE_ERROR_REPORTING` doesn't." And: "This variable doesn't affect the
WebFetch check or official plugin marketplace auto-install; each has its own
opt-out."

**Observed corroboration.** `claude auth status --json` reports
`"analyticsDisabled": false` on this machine, and the `init` event carries
both `analytics_disabled: false` and `product_feedback_disabled: false` —
i.e. both telemetry states are surfaced as first-class session metadata.

**Clean-room opportunity.** Emit the same two booleans in the session
metadata, and implement telemetry as **four independent sinks** each with its
own default and opt-out — never a single global "tracking" switch. A
clean-room agent that promises "no telemetry" should be able to prove it
per-sink.

---

### F10 — MCP has two transport classes with completely different network models, plus a hard OAuth constraint

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Claim.** MCP servers split into **local child processes** (stdio — no
network, no account) and **remote servers** (HTTP/SSE/WebSocket — network +
auth). The remote path has specific constraints and specific failure
semantics.

**Evidence (docs).** Transport table:

| Transport | Setup | Network/host | Authentication |
|---|---|---|---|
| HTTP | `claude mcp add --transport http <name> <url>` | Remote URL | OAuth 2.0, static `--header`, or `headersHelper` |
| SSE | `claude mcp add --transport sse <name> <url>` | Remote SSE endpoint | OAuth credential flags; SSE is deprecated |
| stdio | `claude mcp add --transport stdio <name> -- <command> [args...]` | **Local child process; no remote host required** | env vars via `--env`; no OAuth flow |
| WebSocket | `claude mcp add-json <name> '{"type":"ws","url":"wss://...","headers":{...}}'` | Remote, persistent | **Header-only; no OAuth** |

Hard constraints: "OAuth token endpoints must use **HTTPS**, or be at
`localhost`, `127.0.0.1`, or `::1`." "OAuth callback format:
`http://localhost:PORT/callback`." "`claude -p` and Agent SDK runs cannot start
the OAuth flow; authenticate in an interactive session first." Note
`--transport ws` is **not supported** — WebSocket must be added via
`add-json`.

Failure semantics: `claude mcp list` reports `✔ Connected` / `! Needs
authentication` / `✘ Failed to connect`. "First HTTP/SSE transient connection
failure: retried up to **three times**, then marked failed." "Mid-session
remote drop: up to **five reconnect attempts** with exponential backoff. In
headless/SDK runs, transient HTTP/SSE failures continue retrying in the
background for about **30 minutes**." "A first WebSocket connection failure is
**not** automatically retried."

**Evidence (observed).** `claude mcp get rea` on this machine (saved to
`mcp-status.txt`):

```
rea:
  Scope: User config (available in all your projects)
  Status: ✘ Failed to connect
  Issue: MCP server "rea" connection timed out after 30000ms
  Type: stdio
  Command: cmd.exe
  Args: /d /c npx -y rea-agents@6.7.0 mcp
  Environment:
```

This single observation reveals a **three-layer dependency chain**: the
`rea` server is a *stdio* server (no remote host), but it is launched via
`npx -y rea-agents@6.7.0`, which requires (a) the `npx` binary, (b) **network
access to `registry.npmjs.org`** to fetch the package, and (c) a 30-second
connection timeout. So "stdio" does not mean "offline" — the *launcher* may
have its own network dependency. The `init` event correspondingly reported
`mcp_servers: [{"name":"rea","status":"pending","source":"user"}]` — the
server is **pending**, not failed, at session start, because MCP connects
asynchronously relative to session start.

**Clean-room opportunity.** Implement MCP with a clear transport abstraction
where stdio servers declare a `requires_network_launcher` hint. Make the
connect state machine explicit (`pending` → `connected` / `failed` /
`needs_auth`) and expose it in the session metadata, matching what the
reference product does in its `init` event. Implement the documented retry
policy (3 initial retries, 5 reconnects with backoff, 30-minute headless
retry window) as configuration.

---

### F11 — The sandbox is an OS-level dependency, absent on native Windows, and it is the only layer that makes network denial enforceable

**Status: OBSERVED-DOC**

**Claim.** The sandbox requires OS primitives that are not universally
available, and its network isolation is enforced by an **in-process proxy
that the sandboxed command talks to** — not by a firewall. That design has
concrete consequences for which tools work.

**Evidence.** From the sandboxing doc:

> "The sandbox runs on macOS, Linux, and WSL2. **On native Windows, Claude Code
> runs commands unsandboxed.** To use the sandbox on a Windows machine, run
> Claude Code inside a WSL2 distribution."

> "**macOS**: sandboxing uses the built-in Seatbelt framework…
> **Linux and WSL2**: the sandbox relies on `bubblewrap` and `socat`."

Network isolation mechanics:

> "**Linux and WSL2**: the command runs in a separate network namespace that
> has no connection to your network. **macOS**: the Seatbelt sandbox framework
> by default blocks connections other than the one to the sandbox proxy.
> Claude Code runs the sandbox proxy on your machine, outside the sandbox, and
> directs commands to it with `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and
> related environment variables. The proxy checks the hostname of each
> connection against your allowed and denied domains."

And the crucial limitation:

> "**Tools that read the proxy variables**: `curl`, `npm`, `git` over HTTPS…
> **Tools that ignore the proxy variables**: plain `ssh`, most database
> drivers, and similar tools can't connect, even to an allowed host.
> **Anything that isn't TCP**: UDP, HTTP/3 over QUIC, and ICMP tools such as
> `ping` can't leave the sandbox."

Escape hatches from the sandbox: Read/Edit/Write/WebFetch/WebSearch follow
permission rules **instead**; hooks, local MCP servers, plugin monitors, LSP
servers, the statusline command and `apiKeyHelper` "run with your full
access"; commands the *user* types at the `!` prompt run unsandboxed "in most
sessions"; `excludedCommands` run unsandboxed; and Claude can "ask to run a
command unsandboxed."

Access levels for hosts outside the allowlist are permission-mode-dependent:
allowed without prompt in `bypassPermissions`; prompted in Manual /
`acceptEdits` / plan; **refused** in `auto` mode unless the command listed the
host and the classifier approved it; **refused** in `dontAsk` mode. With
`strictAllowlist` or `allowManagedDomainsOnly`, the proxy refuses in every
mode.

**Machine note.** This machine is **native Windows** (`win32-x64`), so the
sandbox is unavailable here — an independent implementation targeting Windows
must plan its own mechanism (Job Objects, AppContainer, or a WSL/container
route) or explicitly accept that shell commands are unconfined.

**Clean-room opportunity.** Build the sandbox as a **pluggable backend
interface** (`sandbox_backend`), with implementations for Linux (namespaces +
seccomp), macOS (Seatbelt), and Windows (Job Objects / restricted token),
and a `null` backend that is *explicitly reported* to the user rather than
silently applied. Do not rely on proxy-env-var conventions alone to enforce
network policy — enforce at the socket layer where possible, because
proxy-env-var enforcement is trivially bypassed by any tool that ignores
those variables (as the reference product's own doc concedes).

---

### F12 — Cloud sessions require a full stack: plan, account, GitHub, and an Anthropic-hosted VM

**Status: OBSERVED-DOC**

**Claim.** A cloud session is the most dependency-heavy feature in the
product. It needs: a claude.ai account on an eligible plan, a GitHub
connection (GitHub App or `gh` token via `/web-setup`), a cloud environment
with a network access level, and Anthropic-provisioned infrastructure.

**Evidence.** From the cloud-sessions doc:

- Plan: "Cloud sessions are available on Pro, Max, and Team plans, and for
  Enterprise users with premium seats or Chat + Claude Code seats."
- Provider: "`--cloud` requires an Anthropic account. It's not available when
  Claude Code is configured for Amazon Bedrock, Google Cloud's Agent Platform,
  or another third-party provider. An LLM gateway configured only through
  `ANTHROPIC_BASE_URL` doesn't count as a third-party provider for this
  check, but you still need to sign in with `claude auth login`."
- Policy: "Your organization's `allow_remote_sessions` policy must also be
  enabled."
- GitHub: two connection methods — the **Claude GitHub App** (authorised
  during web onboarding) or **`/web-setup`** (sends the local `gh` CLI token
  to your Claude account).
- Repo hosting: "repository cloning and pull request creation require
  GitHub." GitLab/Bitbucket need a bundle upload with
  `CCR_FORCE_BUNDLE=1`, and then "the session can't push results back to that
  remote."
- Uploading a local repo instead of cloning: 100 MB limit, git ≥ 2.31 on
  macOS/Linux/WSL, and a list of unsupported checkout layouts (submodule,
  `--separate-git-dir`, `--shared`, `--reference`, `core.worktree`, reftable
  refs, sparse checkout).
- **Platform divergence in secret handling:** "On macOS, Linux, and WSL,
  Claude Code leaves uncommitted changes to files named like credentials or
  keys out of the upload… **Native Windows**: uncommitted changes to tracked
  files upload as they are, whatever the file's name."
- Network access levels per environment: **None** / **Trusted** / **Full** /
  **Custom**. "Whichever level you pick, sessions can still reach… the
  Anthropic API, for Claude Code's own requests, even at **None**."
- Cloud environment expiry: "cloud sessions stop after a period of inactivity
  and the session's VM is reclaimed"; a reopened session restores
  "conversation history" but not "background work… Shell commands…
  Subagents… Session-scoped scheduled tasks."

**Clean-room opportunity.** Cloud execution is *not* independently
reproducible without equivalent hosted infrastructure. A clean-room agent
should implement the **local equivalents** instead: (a) a local `--bg`
background session with a supervisor process (which the reference product
*does* have — see F13), (b) a "bundle the repo" upload path with the same
size/layout checks but with **uniform secret-exclusion across all
platforms** (fixing the Windows divergence), and (c) an explicit
"session can be restored but background work cannot" contract in the resume
path.

---

### F13 — Background agents need a local supervisor daemon, not just the CLI

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Claim.** Background sessions are hosted by a **per-user supervisor process**
that outlives the shell that started it. This is a local OS dependency with
non-obvious consequences for configuration and for credential handling.

**Evidence (docs).** From the network-config doc:

> "Background agents don't run inside the terminal that dispatched them. A
> per-user supervisor process starts on demand, outlives your shell, and hosts
> every `claude agents`, `--bg`, and `/background` session… The supervisor is
> one process shared by every terminal. **It inherits the environment of
> whichever shell starts it first.** If you export a proxy, CA path, or mTLS
> variable only in your shell, it reaches background agents when that shell
> happened to cold-start the supervisor, and silently doesn't when a different
> shell did."

> "The supervisor and its workers start Claude Code from a fixed path rather
> than by looking up `claude` on `PATH`, so every background agent bypasses a
> wrapper you place earlier on `PATH`."

> "An already-running supervisor keeps the launch configuration it started
> with. After deploying the launcher setting, run `claude daemon stop --any`
> so the next `claude agents` or `--bg` starts a supervisor that honors it."

**Evidence (observed).** `claude agents --json` on this machine (saved to
`agents-json.txt`) returned a live session list including this very session:

```json
[{"pid":21488,"cwd":"C:\\Users\\Admin\\Desktop\\Claude clone","kind":"interactive",
  "startedAt":1792603034892,"sessionId":"ca6d0088-4426-4239-8884-8c2b9e5b1238",
  "name":"claude-clone-95","status":"busy"},
 {"pid":10472,"cwd":"C:\\Users\\Admin\\REA-Test","kind":"interactive",
  "startedAt":1792604140104,"sessionId":"96b5c88f-3cb8-4d8f-b8d5-2a5df0a0c6f4",
  "name":"rea-test-f8","status":"idle"}]
```

The existence of `kind: "interactive"` entries confirms the supervisor tracks
*all* sessions on the machine, not just background ones — a machine-wide
session registry with a stable `sessionId` and a human-readable `name`.

**Clean-room opportunity.** Implement a supervisor with the same shape, but
fix the two documented footguns: (a) read configuration from a *file* that
every session can see, not from the environment of whichever shell won the
race; (b) make the launch path configurable so a wrapper is not bypassed.
Also: make the registry machine-wide and name-addressable, since
`claude attach <id|name>` and `claude logs <id|name>` both accept a partial
name — a nice, simple UX contract to copy.

---

### F14 — Skills, CLAUDE.md, and local hooks have **zero** mandatory network or account dependency

**Status: OBSERVED-DOC + OBSERVED-CLI** *(substantially rewritten 2026-10-21 — the previous version of this entry carried fabricated quotations; see the correction below)*

**Claim.** The entire "reusable instructions" layer is offline-capable. This
is the clearest contrast in the product: the same session that cannot reach
Remote Control can still run a fully-featured local skill.

> **CORRECTION (2026-10-21).** The previous version of this entry quoted a
> "Network and account requirements" section of the skills documentation and
> four sentences about hook network/account requirements. **None of them
> exist.** A grep of `agent-reference-shots/docs-cache/skills.md` (110,497
> bytes) returns **0 hits** for the word `network` in any case, and **0 hits**
> for `Network and account requirements`, `no mandatory network`, `account
> requirement`, `supply credentials`, `does not require network`, and `expires
> on your next message`. The hooks page returns **0 hits** for `does not
> require network`, `separate hook account`, `There is no separate hook
> credential system`, `Require a reachable endpoint`, and `receives event JSON
> on`. The heading "Network and account requirements" does not exist either.
> This is the same failure the project recorded in `claude-code-evidence.md`
> R2: a quotation that reads plausibly and was never grepped. The entry has
> been rebuilt from sentences that were checked.

**Evidence (skills — verified sentences only).** The skills documentation
states, of the `allowed-tools` frontmatter field:

> "Tools Claude can use without asking permission during the turn that invokes
> this skill. The grant clears when you send your next message."

And, on the skill content lifecycle:

> "When you or Claude invoke a skill, the rendered `SKILL.md` content enters
> the conversation as a single message and stays there across later turns.
> This persistence applies to the skill's instructions, not its permissions: an
> `allowed-tools` grant clears when you send your next message."

Two further verified sentences establish the *locality* of the grant, and are
the real basis for the offline-capability claim:

> "Workspace trust doesn't gate this field. Claude Code applies a project
> skill's `allowed-tools` even in a `-p` run in a folder you've never trusted."

> "A skill can grant itself broad tool access, so review the `allowed-tools`
> of skills checked into a repository before you run Claude Code there."

The second of these is the **security-relevant** half and was omitted from the
original entry: the same grant that makes a skill offline-capable also makes
an *untrusted* repository able to pre-approve tools for itself.

**Evidence (hooks — verified sentences only).** The hooks documentation
describes the HTTP handler's fields, including an environment-variable
allowlist:

> "Additional HTTP headers as key-value pairs. Values support environment
> variable interpolation using `$VAR_NAME` or `${VAR_NAME}` syntax. Only
> variables listed in `allowedEnvVars` are resolved."

> "List of environment variable names that may be interpolated into header
> values. References to unlisted variables are replaced with empty strings.
> Required for any env var interpolation to work"

And the documented example points at `http://localhost:8080/hooks/pre-tool-use`
— a **localhost** endpoint. The page's eight occurrences of "network" are all
about *sandboxed commands' network requests* and *network paths*, not about
hook connectivity. **No documented sentence asserts that a command hook needs
no network**; that claim is **not** supported by the documentation and has been
removed rather than restated more weakly.

**Hook environment variables.** The hooks page documents
`CLAUDE_PROJECT_DIR` (29 occurrences), `CLAUDE_PLUGIN_ROOT` (9),
`CLAUDE_PLUGIN_DATA` (4), `CLAUDE_ENV_FILE` (14), `CLAUDE_EFFORT` (1),
`CLAUDE_CODE_REMOTE` (1), `CLAUDE_CODE_BRIDGE_SESSION_ID` (1) and
`CLAUDE_PLUGIN_OPTION_<KEY>` (2). The `CLAUDE_ENV_FILE` mechanism is
documented verbatim:

> "SessionStart hooks have access to the `CLAUDE_ENV_FILE` environment
> variable, which provides a file path where you can persist environment
> variables for the shell commands Claude runs later in the session. To set
> individual environment variables, write `export` statements to
> `CLAUDE_ENV_FILE`. Use append (`>>`) to preserve variables set by other
> hooks."

**Note on the six `${CLAUDE_*}` count.** The hooks page names **eight**
`CLAUDE_*` variables, but six of them are *substitution* variables documented
on the skills page (`${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}`,
`${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_PLUGIN_ROOT}`,
`${CLAUDE_PLUGIN_DATA}`); `CLAUDE_ENV_FILE`, `CLAUDE_CODE_REMOTE`,
`CLAUDE_CODE_BRIDGE_SESSION_ID` and `CLAUDE_PLUGIN_OPTION_<KEY>` are
**environment variables passed to the hook process**, not template variables.
The count of six is a count of the *substitution* vocabulary, not of every
`CLAUDE_*` identifier in the product. `CLAUDE_SESSION_ID` does not appear on
the hooks page at all — it comes from the skills page's substitution table.
Stating the two vocabularies separately avoids a future reader merging them
and concluding the count is wrong.

**The `OTEL_*` / HIPAA environment claim was removed.** The previous version of
this entry stated that hooks inherit the parent environment "except: `OTEL_*`
exporter variables are removed… HIPAA configuration removes Anthropic
credentials." That quotation is **not** in the hooks page and was not
re-verified; it has been removed rather than restated.

**Hook events.** The reference documents **33** events, not 37 (corrected;
`claude-code-evidence.md` R5, and see `claude-code-evidence.md` R16 for the
same correction applied to our own interface specification): `SessionStart`,
`Setup`, `UserPromptSubmit`, `UserPromptExpansion`, `PreToolUse`,
`PermissionRequest`, `PermissionDenied`, `PostToolUse`, `PostToolUseFailure`,
`PostToolBatch`, `Notification`, `MessageDisplay`, `SubagentStart`,
`SubagentStop`, `TaskCreated`, `TaskCompleted`, `Stop`, `StopFailure`,
`TeammateIdle`, `InstructionsLoaded`, `ConfigChange`, `CwdChanged`,
`DirectoryAdded`, `FileChanged`, `WorktreeCreate`, `WorktreeRemove`,
`PreCompact`, `PostCompact`, `PreModelSwitch`, `PostModelSwitch`,
`Elicitation`, `ElicitationResult`, `SessionEnd`.

**Observed corroboration.** The `init` event on this machine reported
`skills: [len=20]` and `plugins:` with three **builtin** entries
(`cc-plugin-agents-md`, `cc-plugin-telemetry`, `cc-plugin-plugin-authoring`)
— i.e. bundled skills and plugins load with no marketplace fetch.

**Clean-room opportunity.** Implement skills as plain Markdown+YAML in
`SKILL.md` with `allowed-tools` as a *transient* permission grant scoped to
the invoking turn (expiring on the next user message) — that expiry is a
deliberate, documented safety property worth copying exactly. Implement hooks
as local processes receiving JSON on stdin, with `CLAUDE_ENV_FILE` for
persisting environment changes.

**And one thing the reference does *not* do, which Keel should:** the
reference applies a project skill's `allowed-tools` **even in an untrusted
folder** ("Workspace trust doesn't gate this field"). That is a deliberate
reference behaviour, and it means an untrusted repository can pre-approve
tools for itself. Keel treats workspace trust as gating **grants**
(`security-plan.md` C-37), so Keel will **narrow** this: a repository
contributed skill's `allowed-tools` grant is inert until the folder is
trusted. This is a deliberate divergence and belongs in the compatibility
matrix.

---

### F15 — Plugins depend on a marketplace host (GitHub) plus an npm registry; `--plugin-dir` is the offline path

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Claim.** A plugin is a local directory of components, but *obtaining* one
usually requires a marketplace fetch and a package-registry fetch. There is a
fully offline path.

**Evidence (docs).** "A plugin marketplace isn't Claude Marketplace. Claude
Marketplace is the website at claude.com/marketplace… A plugin marketplace is
a repository or directory with a `.claude-plugin/marketplace.json` file that
lists plugins and where to fetch each one. It's a catalog, not a hosted store."

Network requirements (from the network-config table): `downloads.claude.ai` for
plugin executable downloads; `storage.googleapis.com` for plugin install
counts and metadata; `registry.npmjs.org` for "plugin installs (fetching
npm-source plugin packages and installing plugins' Node.js package
dependencies)"; `github.com` for "cloning GitHub-hosted plugin marketplaces
and plugins, including the official Anthropic marketplace, over HTTPS or SSH."

The offline path: "While you are developing a plugin, you don't need a
marketplace: load it straight from its folder with `--plugin-dir`." The CLI
confirms `--plugin-dir <path>` — "Load a plugin from a directory or .zip for
this session only; a folder of plugins loads each child (repeatable:
`--plugin-dir A --plugin-dir B.zip)" — plus `--plugin-url <url>` to fetch a
`.zip`.

Context cost is a real dependency-shaped cost: "for each skill, agent, and
command that Claude can invoke on its own, the name and description are in
Claude's context on every turn… Those tokens count toward your usage."

**Evidence (observed).** `claude plugin marketplace list` (saved to
`plugin-status.txt`):

```
Configured marketplaces:

  ❯ anthropic-plugin-directory
    Source: Built in (Anthropic Directory)

  ❯ claude-plugins-official
    Source: GitHub (anthropics/claude-plugins-official)
```

and `claude plugin list` → "No plugins installed." So two marketplaces are
pre-registered (one built-in, one a GitHub clone) even though nothing is
installed and the machine is not on `api.anthropic.com` — meaning marketplace
registration is a *local* git clone, not an API call.

**Clean-room opportunity.** Implement marketplaces as **git repositories
containing a JSON index** (a git remote is a natural, offline-friendly
distribution channel) with a documented index schema; support `--plugin-dir`
and `--plugin-url` as first-class offline paths; and **surface a projected
token cost per plugin** (the reference product does this via `claude plugin
details`, "projected token cost") — a genuinely useful, independently
implementable feature.

---

### F16 — `ultrareview` and Code Review are cloud-only, subscription-only, and have a hard diff-size ceiling

**Status: OBSERVED-DOC** (+ OBSERVED-CLI for the flag surface)

**Claim.** The deep-review feature runs entirely in Anthropic's cloud
sandbox, requires a claude.ai account, and refuses inputs above documented
thresholds. It falls back to a local review when ineligible.

**Evidence.** From the ultrareview doc:

- "Ultrareview is a deep code review that runs as a **cloud session** on
  Anthropic's infrastructure."
- "Ultrareview requires authentication with a claude.ai account because it runs
  as a cloud session… Ultrareview is not available when using Claude Code with
  Amazon Bedrock, Google Cloud's Agent Platform, or Microsoft Foundry, and it
  is not available to organizations that have enabled Zero Data Retention or
  have the HIPAA configuration applied. **In these cases, `/code-review ultra`
  runs a local review in your session instead.**" Also unavailable with CMEK.
- Data movement: "For a branch review, Claude Code bundles the repository
  state and uploads it to a cloud sandbox… **When you review a pull request,
  Claude Code uploads nothing from your machine.**" In PR mode "the cloud
  sandbox clones the pull request from `github.com` instead of uploading your
  working tree. It uses the GitHub account connected to your Claude account, so
  that account needs read access to the repository."
- Hard limits: "a branch review can include up to **500 changed files and
  8,000 changed lines** by default." Also handled: "Nothing to review",
  "First commit" (reviewed whole only after confirmation), "No merge base"
  (reviews every tracked file instead).
- Posting: "Claude Code doesn't post from your machine. It sends the review's
  session ID to the Anthropic API, which posts the review's stored findings as
  the comment through the GitHub account you've connected to Claude."
- Billing: separate from plan usage — 3 free runs (Pro/Max), then "typically
  $5 to $25 in usage credits"; "your account or organization must have usage
  credits turned on before you can launch a paid review. If usage credits
  aren't turned on, Claude Code blocks the launch."

**Observed (OBSERVED-CLI).** `claude ultrareview --help` (saved in
`cli-help-full.txt`) confirms the non-interactive surface:

```
Usage: claude ultrareview [options] [target]
Run a cloud-hosted multi-agent code review of the current branch (or a PR number / base branch) and print the findings
  --json               Print the raw bugs.json payload instead of formatted findings
  --no-post            Do not post the findings to the PR (the default...)
  --post               Post the finished review's findings to the PR as you (PR targets only; one plain comment, not a review)
  --timeout <minutes>  Maximum minutes to wait for the review to finish (default: 45)
```

Exit codes: `0` completed, `1` failed/stopped/timeout, `130` interrupted.
"Progress messages go to stderr so stdout stays parseable."

**Clean-room opportunity.** A cloud-hosted multi-agent review is not
independently reproducible without hosted infrastructure. The **independently
implementable** parts are: (a) a local multi-reviewer fan-out (the product
does this too, locally, in `/code-review`); (b) the **diff-size and
edge-case preflight** — 500 files / 8,000 lines, empty-diff, first-commit,
no-merge-base — as a *user-visible* preflight that refuses clearly and
suggests a remedy; (c) the `bugs.json` machine-readable output schema;
(d) the stdout/stderr separation and the three exit codes; (e) the
"uploads nothing from your machine" guarantee for PR mode, which is a
meaningful privacy property worth reproducing.

---

### F17 — Remote Control requires a *narrower* set of conditions than cloud sessions, and is hard-disabled by base URL and traffic flags

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Claim.** Remote Control is the most aggressively gated feature: it needs a
claude.ai subscription, the Anthropic API endpoint specifically, feature-flag
evaluation enabled, and workspace trust.

**Evidence.** From the Remote Control doc, "Requirements":

- **Subscription**: "available on Pro, Max, Team, and Enterprise plans. **API
  keys are not supported.** On Team and Enterprise, an Owner must first enable
  the Remote Control toggle in Claude Code admin settings."
- **Authentication**: "run `claude` and use `/login` to sign in through
  claude.ai… Without an eligible login, `claude remote-control` exits with an
  error."
- **API endpoint**: unavailable on Bedrock/Vertex/Foundry; unavailable when
  `ANTHROPIC_BASE_URL` points anywhere but `api.anthropic.com`; unavailable
  through an enterprise Claude apps gateway.
- **Feature-flag evaluation**: "`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` or
  `DISABLE_GROWTHBOOK` → Remote Control is unavailable." But "`DISABLE_TELEMETRY`
  or `DO_NOT_TRACK` → Remote Control stays available unless your organization
  requires Trusted Devices." (Requires v2.1.283+ / Desktop v2.1.304+.)
- **Workspace trust**: a non-TTY invocation "can't ask and exits with a
  `Workspace not trusted` error."

**Observed.** `claude doctor` on this machine reports the whole chain at
once: base URL wrong → Remote Control unavailable → not connected to
api.anthropic.com → not signed in to claude.ai → subscription auth not
active → missing `user:profile` scope → organization not resolved → "Remote
Control availability could not be verified (no server response this session)".

The missing `user:profile` scope is a fine-grained OAuth scope — a *third*
distinct auth dimension beyond "which credential" and "which plan".

**Clean-room opportunity.** A clean-room agent that wants a
phone-continues-desktop experience needs its own signalling channel. The
minimum viable design: a long-lived session-scoped token (the docs mention
`CLAUDE_CODE_MESSAGING_TOKEN` for "the per-session token for authenticating
inbox-socket messages"), a relay service, and a strict entitlement check.
Document the *scoping* explicitly — the reference product's "the connection
token is short-lived and scoped to your account" is a good property to copy.

---

### F18 — IDE integrations need a *bundled* CLI, and ship their own account surface

**Status: OBSERVED-DOC**

**Claim.** The VS Code extension bundles its own private copy of the CLI and
requires an account; the JetBrains plugin requires the standalone CLI
installed separately. The extension is a separate dependency surface from the
terminal.

**Evidence.** From the VS Code doc:

- "**Prerequisites**: VS Code 1.94.0 or later. An Anthropic account: any paid
  Claude subscription (Pro, Max, Team, or Enterprise) or a Claude Console
  account works, and **no API key is required**."
- "**The extension bundles its own copy of the CLI** (command-line interface)
  for the chat panel. To run `claude` in VS Code's integrated terminal, you
  also need the **standalone CLI install**."
- "Installing the extension does not put `claude` on your shell PATH."
- `disableLoginPrompt` — "Skip authentication prompts (for third-party
  provider setups)."
- "On a third-party provider, the extension doesn't offer features that
  require a claude.ai account, such as plan usage bars, voice dictation, and
  the Web tab for cloud sessions."
- "The plugin requires the Claude Code CLI, installed separately" (JetBrains,
  from the overview doc).

**Clean-room opportunity.** Ship the agent core as a **library + thin
launchers** so the IDE extension, the terminal, and any headless runner all
embed the same engine — rather than bundling a second copy of a binary. Make
the IDE extension able to run **fully offline against a local model provider**,
which the reference product's account requirement prevents.

---

### F19 — The CLI exposes a large, *documented* environment-variable surface — the best available spec for a provider-agnostic design

**Status: OBSERVED-DOC + OBSERVED-CLI**

**Claim.** The env-var reference is effectively a published interface
contract for provider selection, auth, base URLs, and feature toggles. It is
the most valuable single artifact for a clean-room implementation.

**Evidence.** Grouped from the env-vars doc:

**Provider and model selection** — `CLAUDE_CODE_USE_BEDROCK`,
`CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_USE_FOUNDRY`,
`CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST`, `ANTHROPIC_MODEL`,
`ANTHROPIC_DEFAULT_MODEL`, `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL`,
`ANTHROPIC_CUSTOM_MODEL_OPTION`, `ANTHROPIC_SMALL_FAST_MODEL`,
`ANTHROPIC_VERTEX_PROJECT_ID`, `ANTHROPIC_FOUNDRY_RESOURCE`,
`ANTHROPIC_AWS_WORKSPACE_ID`, `CLAUDE_CODE_AUTO_MODE_MODEL`,
`CLAUDE_CODE_MAX_CONTEXT_TOKENS`.

**Authentication** — `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
`ANTHROPIC_AWS_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`,
`ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_AUTH_TOKEN`,
`ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`,
`ANTHROPIC_WORKSPACE_ID`, `ANTHROPIC_PROFILE`, `CLAUDE_CODE_OAUTH_TOKEN`,
`CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `CLAUDE_CODE_OAUTH_SCOPES`,
`CLAUDE_CODE_CLIENT_CERT`, `CLAUDE_CODE_CLIENT_KEY`,
`CLAUDE_CODE_CLIENT_KEY_PASSPHRASE`, `CLAUDE_CODE_CERT_STORE`,
`ANTHROPIC_CUSTOM_HEADERS`, `CLAUDE_CODE_MESSAGING_TOKEN`.

**API base URLs** — `ANTHROPIC_BASE_URL`, `ANTHROPIC_AWS_BASE_URL`,
`ANTHROPIC_BEDROCK_BASE_URL`, `ANTHROPIC_BEDROCK_MANTLE_BASE_URL`,
`ANTHROPIC_FOUNDRY_BASE_URL`, `ANTHROPIC_VERTEX_BASE_URL`.

**Notable feature toggles** — `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`
(even `0` disables it), `DISABLE_TELEMETRY`, `DISABLE_ERROR_REPORTING`,
`DO_NOT_TRACK`, `CLAUDE_CODE_ENABLE_TELEMETRY` (OpenTelemetry),
`CLAUDE_CODE_DISABLE_ARTIFACT`, `CLAUDE_CODE_DISABLE_WEB_FETCH`,
`CLAUDE_CODE_DISABLE_AGENT_VIEW`, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`,
`CLAUDE_CODE_DISABLE_CRON`, `CLAUDE_CODE_DISABLE_BUNDLED_SKILLS`,
`CLAUDE_CODE_DISABLE_CLAUDE_MDS`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY`,
`CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING`, `CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK`,
`CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY` ("Populates the model picker from
a gateway's `/v1/models` endpoint"), `CLAUDE_CODE_GATEWAY_HINT_HEADERS`,
`CLAUDE_CODE_DISABLE_FAST_MODE`, `CLAUDE_CODE_DISABLE_ADVISOR_TOOL`,
`CLAUDE_CODE_AUTO_MODE_SERVER`, `CLAUDE_CODE_PROCESS_WRAPPER`.

**Proxy/TLS** — `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY` (first set wins in the
order `https_proxy`, `HTTPS_PROXY`, `http_proxy`, `HTTP_PROXY`; lowercase
works; SOCKS unsupported), `NODE_EXTRA_CA_CERTS`, `CLAUDE_CODE_CERT_STORE`
(`bundled` | `system` | `bundled,system` default),
`CLAUDE_CODE_GZIP_REQUEST_BODIES=0`, `CLAUDE_CODE_CLIENT_CERT`/`_KEY`/`_KEY_PASSPHRASE`.

**Streaming watchdogs** — `CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS` (default
180 s direct / 300 s elsewhere, plus 1 s per 32 KB of request body),
`CLAUDE_STREAM_IDLE_TIMEOUT_MS` (floor 5 min, cap 30 min for the byte
watchdog), `CLAUDE_BYTE_STREAM_IDLE_TIMEOUT_MS` (clamped 10 s–30 min),
`API_TIMEOUT_MS`, `API_FORCE_IDLE_TIMEOUT`, `CLAUDE_ENABLE_STREAM_WATCHDOG`,
`CLAUDE_ENABLE_BYTE_WATCHDOG`, `CLAUDE_ENABLE_BYTE_WATCHDOG_BEDROCK`.

**Observed corroboration.** `claude --help` (saved to `cli-help-full.txt`)
documents the same provider surface in its own words: `--bare` sets
`CLAUDE_CODE_SIMPLE=1` and makes "Anthropic auth … strictly `ANTHROPIC_API_KEY`
or `apiKeyHelper` via `--settings` (OAuth and keychain are never read). 3P
providers (Bedrock/Vertex/Foundry) use their own credentials." It also
documents `--betas <betas...>` — "Beta headers to include in API requests (**API
key users only**)" — which is itself a provider-dependency detail.

**Clean-room opportunity.** Adopt a similarly complete, documented env-var
contract as the *public* configuration surface of a clean-room agent, and
**ship the resolution order as a documented precedence list** so users can
predict which credential wins. Consider going further: publish a
`--print-capabilities` mode that dumps the resolved provider/plan/model
capability matrix as JSON — the reference product approximates this with
`claude doctor` prose, but a machine-readable form is strictly better and
directly reusable by an implementer.

---

### F20 — "Offline" is not a mode the product supports; it is a *continuum* of per-feature degradation

**Status: INFERRED** (from the pattern across F1–F19)

**Claim.** There is no single offline mode. The product degrades feature by
feature along a fixed hierarchy, and the hierarchy is *documented and
consistent*:

```
fully local  →  provider-scoped  →  account-scoped  →  Anthropic-hosted
skills/CLAUDE.md/local hooks   WebSearch, fast mode,   cloud sessions,
file tools, local MCP, git     Advisor, Channels       ultrareview, Remote Control,
sandbox, permissions          (3P providers)          Slack, Chrome, Code Review
```

**Reasoning.** This is the conclusion that the per-feature findings
independently converge on: F3 (Tier 2 removes tools rather than erroring),
F4 (matrix is per-provider and per-model), F2 (base URL gates a family of
features), F8 (one tool keeps a hard API call even under every opt-out),
F12/F16/F17 (cloud features are wholly out of reach), and F14 (the
instruction layer is entirely local). No feature is documented as "works
offline" except the local-only ones in Tier 0; nothing degrades to a local
equivalent except the two documented fallbacks (ultrareview → local review;
Bedrock → WebFetch instead of WebSearch).

**Clean-room opportunity.** Do not ship an "offline mode" toggle. Instead,
ship the **capability matrix** (F4) plus a `doctor`-equivalent that prints,
per feature, one of: `available`, `degraded (reason)`, `unavailable
(reason)`, `unknown (could not verify)`. The "unknown" state is important and
the reference product models it well — `claude doctor` printed "Remote
Control availability could not be verified (no server response this session)",
which is a genuinely distinct and useful state.

---

## 3. Dependency matrix

Legend: **✔** available · **~** partial / degraded · **✗** unavailable ·
**?** depends on plan or policy.

| Feature | Network | Account | Model provider | External service | Breaks without |
|---|---|---|---|---|---|
| **Auth** (`/login`, `claude auth`) | ✔ | ✔ (claude.ai / Console / provider) | — | browser OAuth, `platform.claude.com` | No credential → every request fails |
| **Chat / core loop** | ✔ | ✔ | ✔ (any Anthropic-API-compatible) | — | **Total failure** of the turn; local machinery still fine |
| **File tools** (Read/Edit/Write/Glob/Grep) | ✗ | ✗ | ✗ | ✗ | Nothing — fully local |
| **Bash / PowerShell** | ~ (sandbox proxy) | ✗ | ✗ | shell, git, toolchain | Without a shell, file-only work |
| **Permissions** | ✗ | ✗ | ✗ | ✗ | Nothing — local |
| **Sandbox** | ✔ (proxy) | ✗ | ✗ | Seatbelt / bubblewrap+socat | **Native Windows: no sandbox at all** |
| **Skills / CLAUDE.md** | ✗ | ✗ | ✗ | ✗ | Nothing — local |
| **Local hooks** (command type) | ✗ | ✗ | ✗ | ✗ | Nothing — local |
| **HTTP hooks** | ✔ | ✗ | ✗ | reachable endpoint | Hook skipped/failed |
| **MCP — stdio** | ~ (launcher) | ✗ | ✗ | local process; npm if npx | Server tools absent |
| **MCP — HTTP/SSE/WS** | ✔ | ~ (OAuth) | ✗ | remote server | `✘ Failed to connect` / `! Needs authentication` |
| **MCP — claude.ai connectors** | ✔ | ✔ | ✗ | `mcp-proxy.anthropic.com` | Connectors absent |
| **Plugins** | ✔ | ✗ | ✗ | GitHub, npm, `downloads.claude.ai` | `--plugin-dir` remains |
| **Subagents** | ✔ | ✗ | ✔ (**different model**) | ✗ | Falls back to parent model |
| **WebFetch** | ✔ | ~ (policy) | ✗ | target host **+ `api.anthropic.com` preflight** | Fetches fail without preflight opt-out |
| **WebSearch** | ✔ | ✗ | ✔ (**server-side tool**) | Anthropic search backend | ✗ on Bedrock; model-gated on Vertex |
| **Auto mode (classifier)** | ✔ | ~ | ✔ (**separate model**) | Anthropic review service | ✗ on 3P providers w/ older models |
| **Advisor** | ✔ | ✗ | ✔ (separate) | Anthropic | ✗ on all 3P providers |
| **Background sessions** | ✔ | ✔ | ✔ | local supervisor daemon | Supervisor won't start |
| **Cloud sessions** | ✔ | ✔ (Pro/Max/Team/Ent-seat) | ✗ (Anthropic-hosted) | Anthropic VM + GitHub | ✗ on 3P providers |
| **Remote Control** | ✔ | ✔ (sub only, no API key) | ✗ | Anthropic relay + mobile app | ✗ on base URL ≠ api.anthropic.com |
| **ultrareview** | ✔ | ✔ | ✗ | Anthropic cloud sandbox + GitHub | Falls back to local review |
| **Code Review (GitHub)** | ✔ | ✔ (Team/Ent) | ✗ | GitHub App | ✗ on subscription alone |
| **Hooks → HTTP** | ✔ | ✗ | ✗ | your endpoint | Non-blocking failure |
| **IDE integration** | ✔ | ✔ | ✗ | IDE + bundled CLI | Extension unusable |
| **Artifacts** | ✔ | ✔ (Pro/Max/Team/Ent) | ✗ | `*.frame.claudeusercontent.com` | Tool absent |
| **Scheduled tasks (`/schedule`)** | ✔ | ✔ | ✗ | claude.ai | Tool absent |
| **PushNotification / SendUserFile** | ✔ | ✔ | ✗ | Anthropic infra | Tool absent |
| **Channels / Slack** | ✔ | ✔ (Pro/Max; Team/Ent admin) | ✗ | Slack + Anthropic | ✗ on 3P providers |
| **Chrome integration** | ✔ | ✔ | ✗ | `bridge.claudeusercontent.com` | Disabled |
| **CI (GitHub Actions / GitLab)** | ✔ | ✔ | ✔ | CI platform | Varies by provider |
| **Telemetry** | ✔ | ✗ | ✗ | Datadog intake | Off by default on 3P providers |

---

## 4. Evidence index

| Artifact | Path |
|---|---|
| This report | `agent-reference-shots/area12-dependencies/AREA-12-REPORT.md` |
| `claude --help` full output (2.1.306) | `agent-reference-shots/area12-dependencies/cli-help-full.txt` |
| `claude doctor` output | `agent-reference-shots/area12-dependencies/claude-doctor.txt` |
| `claude auth status` (text + JSON) | `agent-reference-shots/area12-dependencies/auth-status.txt` |
| `claude mcp list` / `claude mcp get rea` | `agent-reference-shots/area12-dependencies/mcp-status.txt` |
| `claude plugin list` / `plugin marketplace list` | `agent-reference-shots/area12-dependencies/plugin-status.txt` |
| `claude agents --json` (live session registry) | `agent-reference-shots/area12-dependencies/agents-json.txt` |
| Shared protocol notes (session bootstrap, tool set) | `agent-reference-shots/PROTOCOL-NOTES.md` |
| Compliance boundary | `agent-reference-shots/TERMS-NOTES.md` |

Public documentation fetched during this investigation:
`https://code.claude.com/docs/en/overview`,
`https://code.claude.com/docs/llms.txt`,
`https://code.claude.com/docs/en/authentication`,
`https://code.claude.com/docs/en/feature-availability`,
`https://code.claude.com/docs/en/network-config`,
`https://code.claude.com/docs/en/env-vars`,
`https://code.claude.com/docs/en/mcp`,
`https://code.claude.com/docs/en/sandboxing`,
`https://code.claude.com/docs/en/tools-reference`,
`https://code.claude.com/docs/en/skills`,
`https://code.claude.com/docs/en/hooks`,
`https://code.claude.com/docs/en/data-usage`,
`https://code.claude.com/docs/en/remote-control`,
`https://code.claude.com/docs/en/ultrareview`,
`https://code.claude.com/docs/en/claude-code-on-the-web`,
`https://code.claude.com/docs/en/cloud-environments`,
`https://code.claude.com/docs/en/plugins/overview`,
`https://code.claude.com/docs/en/vs-code`.

---

## 5. Limitations of this investigation

1. **No Anthropic-API-path observation.** This machine's base URL is a
   third-party gateway, so nothing about `api.anthropic.com` behaviour was
   directly observed. Every claim about subscription-gated features is
   **INFERRED from documentation**, and is labelled as such above.
2. **No credential inspection.** `env | grep ANTHROPIC…` and a settings-file
   key-name scan were both **refused by the product's own auto-mode
   classifier** ("[Credential Exploration]"). That refusal is itself
   evidence (see F5) and no credential was read. Credential *names* are taken
   from public documentation.
3. **Provider-specific behaviour was not exercised.** Bedrock, Vertex,
   Foundry, Claude Platform on AWS, and the Claude apps gateway were never
   active; all claims about them are documentary.
4. **One environment variable could not be overridden.** Setting
   `ANTHROPIC_BASE_URL` to an unreachable address in a subshell did **not**
   break the request, so the effective base URL is evidently pinned by a
   higher-precedence source (managed/server-managed settings or a settings
   `env` block) that was not readable without a credential-adjacent read.
   The failure-mode observation for "provider unreachable" is therefore
   **not** established, and is listed as UNKNOWN.
5. **Cloud features were not exercised.** No cloud session, Remote Control
   session, ultrareview run, or GitHub review was launched, so all their
   runtime behaviour is documentary.
6. **The auto-mode rule dump is not the classifier's implementation.** The
   JSON from `claude auto-mode defaults` is the *policy*, not the mechanism.

---

## 6. Unresolved questions (UNKNOWN)

1. What is the exact failure message and exit code when the model provider
   is unreachable at the transport level (connection refused / DNS failure /
   TLS failure)? Not established — the base-URL override did not take
   effect (Limitation 4).
2. Does the product distinguish "provider unreachable" from "provider
   returned 401" from "provider returned 5xx" in its user-facing errors, or
   are they collapsed? The docs have an error reference
   (`/docs/en/errors`) that was not fetched in detail.
3. What is the retry/timeout budget for a *model* request (as opposed to the
   WebFetch deadline and the stream watchdogs)? The watchdogs are documented
   (F19) but the overall request retry policy is not stated in the pages
   fetched.
4. Does the model-provider requirement apply to `--bare` mode identically, or
   does bare mode have a different (e.g. no-tools, no-streaming) request
   shape? Observed that `--bare` still performed a model turn; the request
   shape was not captured.
5. Is the WebFetch domain-safety blocklist identical for all providers, or
   provider-specific? The docs say it "runs regardless of which model
   provider you use" but do not say whether the blocklist itself is shared.
6. What are the exact OAuth scopes required by each account-gated feature?
   `user:profile` was observed in the `claude doctor` output for Remote
   Control, but the per-feature scope map is not published.
7. Does the auto-mode classifier fall back to a local/deterministic path when
   the classifier endpoint is unreachable, and is that fallback
   fail-open or fail-closed? `CLAUDE_CODE_AUTO_MODE_SERVER=0` implies a local
   path exists, but the default remote path's failure behaviour is not
   documented in the pages fetched.
8. Do cloud sessions respect an organisation IP allowlist? Documented as
   *breaking* ("every Anthropic-hosted cloud session fails with an
   authentication error"), but the detection mechanism is unknown.
9. What is the exact MCP-server startup timeout (observed at 30 s) and is it
   configurable? Not documented in the pages fetched.
10. Is the plugin marketplace index schema published? The manifest and
    marketplace reference pages exist in the doc index but were not fetched
    for this area.

---

## 7. Recommended scope for an independent functional implementation

### Tier 0 — the local core (no account, no network beyond the model)

Implement fully. This is the parity core and it is achievable with no
Anthropic-hosted infrastructure.

- CLI startup, project/cwd anchoring, `CLAUDE.md` + `AGENTS.md` discovery and
  injection, `@`-mentions.
- File tools (Read/Edit/Write/Glob/Grep/NotebookEdit) with the same
  read-before-edit and concurrent-edit (`userModified`) guards.
- Shell tool + permission rules + permission modes (deny → ask → allow) +
  hardcoded protected-path circuits.
- Skills (`SKILL.md`, `allowed-tools` as a **turn-scoped** grant,
  `disable-model-invocation`), local hooks (command type, JSON on stdin,
  `CLAUDE_ENV_FILE`).
- Local MCP (stdio) with an explicit `pending → connected/failed` state
  machine and a configurable startup timeout.
- Session persistence + resume + compaction + checkpointing.
- A **sandbox backend interface** with a Linux implementation and an honest
  "unavailable" report on unsupported platforms (Windows). Prefer socket-level
  enforcement over proxy-env-var enforcement.

### Tier 1 — the provider layer (one model provider, no Anthropic account)

Implement fully. This is where an independent implementation can be
*better* than the reference product.

- A **provider interface** with at least two backends: Anthropic-API and
  OpenAI-compatible (so a local Ollama/vLLM/llama.cpp endpoint works with
  tool-calling).
- A **capability matrix** as data: `Availability(provider, plan, model,
  feature) → {full, partial, none, unknown}`.
- A **credential resolution order** implemented explicitly and reported by a
  `doctor`-equivalent — including a machine-readable `--print-capabilities`.
- **Per-role model routing**: session / subagent / background-task /
  classifier / advisor.
- **Telemetry as four independent sinks**, each with its own default and
  opt-out, surfaced as session metadata.
- **A local WebFetch safety policy** — this is a deliberate improvement over
  the reference product, which unconditionally phones home with every
  target hostname (F8). Make the external preflight opt-in, defaulting to a
  local blocklist, and document the difference.

### Tier 2 — account-gated features

Implement as **gated-absent**, not as stubs. The important thing is the
*mechanism*: a capability filter applied to the tool registry, plus a
per-feature reason surfaced to the user. The specific Anthropic-account
features (Remote Control, cloud sessions, ultrareview, Slack, Chrome) are
**not** independently reproducible; model them as unavailable and say so.

### Tier 3 — external services

Out of scope, except for the local substitutes the reference product itself
provides:

- GitHub integration → substitute with generic `gh` CLI usage (the product
  documents `gh pr diff` as a skill example), and implement the **PR-mode
  "uploads nothing from your machine"** property.
- Local background sessions → **implement** (a supervisor daemon is local
  infrastructure, fully reproducible).
- Cloud sessions → implement the *bundle-and-upload* path with a documented
  size/layout policy, and **fix the Windows secret-leak divergence** by
  excluding credential-like files on every platform.
- Multi-agent review → implement the **local** fan-out plus the diff-size
  preflight (500 files / 8,000 lines) and the `bugs.json` schema.

### Explicitly recommend NOT replicating

- The `api.anthropic.com` WebFetch preflight as a mandatory call.
- The Datadog telemetry hosts and the `DO_NOT_TRACK` / `DISABLE_*` env-var
  zoo; prefer a small, documented, single-purpose configuration surface
  (a `config.toml`/JSON file plus a handful of env vars) over ~100 toggles.
- The multi-provider OAuth/credential precedence (7 ranks) — support two or
  three providers cleanly rather than six partially.
- Anthropic-hosted infrastructure (cloud VMs, Remote Control relay, the
  marketplace directory, Slack integration).

### Implementation order

1. Provider interface + credential resolution + capability matrix + doctor.
2. Tool registry and permission system (with the capability filter applied
   at registry-build time).
3. File tools + Bash + local sandbox backend.
4. Skills + hooks + CLAUDE.md.
5. MCP (stdio first, then HTTP with OAuth).
6. Session persistence, resume, compaction, background supervisor.
7. WebFetch/WebSearch with the local-first safety policy.
8. Multi-agent review (local) + the preflight/refusal UX.

---

## 8. Summary for the caller

**Confirmed capabilities (evidence-backed):** 20 findings, F1–F20, each with a
status and an evidence pointer.

**Top unknowns:** 10, listed in §6 — chiefly the unreachable-provider
failure mode (blocked by a read restriction), the model-request retry budget,
the auto-mode classifier's fail-open/fail-closed behaviour under endpoint
failure, and the per-feature OAuth scope map.

**Recommended scope:** Tiers 0 and 1 in full, Tier 2 as gated-absent, Tier 3
only via local substitutes (background sessions, local multi-agent review,
the bundle-upload path with uniform secret exclusion). Do not replicate the
mandatory Anthropic preflight for WebFetch, the ~100 env-var toggle surface,
or the 7-rank credential precedence.
