# Page evidence — Feature availability

**Source page:** https://code.claude.com/docs/en/feature-availability.md
**Raw cached copy:** `agent-reference-shots/docs-cache/feature-availability.md` (21,335 bytes, fetched 2026-10-21)
**Local mirror:** `agent-reference-shots/page-feature-availability/feature-availability.md`
**Focus:** Which features require which plan, account, provider, or surface — the dependency matrix.

**Compliance record.** Public Anthropic documentation only. No decompilation, no binary
inspection, no source-map extraction, no modification of the binary, no credential or
licence-file reads. REA was **not** applied here because the assigned page is a public
documentation page, not a binary artifact — the page's content is the object of study, and
fetching its `.md` form is the authorised method. Local CLI observation was limited to the
published CLI's own help/diagnostic surfaces (`claude auth status`, `claude doctor`), which
the task explicitly permits.

**Classification.** Every claim below is `OBSERVED-DOC` unless marked otherwise. Local CLI
corroboration is marked `OBSERVED-CLI`.

**Host caveat (binds every local observation).** This host runs Claude Code **2.1.306**
against a custom `ANTHROPIC_BASE_URL` (`https://openrouter.ai/api`), not
`api.anthropic.com`. Subscription-gated features are therefore **not** observable here and
are recorded as `OBSERVED-DOC` only.

---

## 1. Executive summary

This page is the product's **capability-negotiation contract**. It does not describe how a
feature works; it states, in machine-readable-ish form, *which features exist at all* under a
given (provider, plan, model, OS) combination. For a reimplementation, this page is
arguably the highest-value single document in the docs set, because it defines the
**degradation surface**: what a user loses when they move off the first-party subscription,
and what the product is willing to substitute instead.

**Key structural findings:**

1. **Availability is a four-dimensional function, not a boolean.** `Availability(provider,
   plan, model, OS) -> {full, partial, none}`. The page demonstrates all four dimensions:
   provider columns, plan columns, model gating inside footnotes 1 and 2, and OS gating
   inside footnote 5.
2. **The local core is provider-invariant.** CLI, Agent SDK, IDE extensions, subagents,
   hooks, commands, skills, CLAUDE.md, plugins, MCP, checkpoints, sandboxing, workflows,
   OpenTelemetry metrics and the managed settings file are stated to work on *every*
   provider. The provider axis therefore only bites at the *edges* (cloud features,
   org admin, model-specific tooling).
3. **There is a hard cliff, not a gradient, at the subscription boundary.** Twelve named
   features are "not reachable with an Anthropic Console API key or from a third-party
   provider" — including Cloud sessions, Desktop, Remote Control, Chrome extension,
   Computer use, Artifacts, Voice dictation, Ultrareview, Code Review, Slack, and
   `/schedule`.
4. **The base URL is a first-class capability gate.** A single condition —
   `ANTHROPIC_BASE_URL` pointing at anything other than `api.anthropic.com` — disables
   Remote Control and server-managed settings *regardless of what the gateway forwards*.
   This is the one provider-availability fact that is enforced client-side and therefore
   directly observable.
5. **The page documents substitutions, not just removals.** Each provider tab ends with
   an "Alternatives" line naming a concrete replacement (`/loop` for `/schedule`,
   `WebFetch` for web search, GitHub Actions / GitLab CI/CD for cloud sessions).
   A reimplementation should treat "name the substitute" as part of the availability
   contract.

**Is the page thin?** No. It is dense, structured, and unusually specific — it names
environment variables, version floors, model floors, plan tiers, and per-feature
substitutions. It is, however, a *matrix* page: it is authoritative about **which**
features exist under **which** condition, and silent about **how** they work. An
implementer must pair it with the per-feature pages (linked from every cell).

---

## 2. Claim ledger

### C1 — Provider selection is driven by five named environment variables

**Status: OBSERVED-DOC**
**Section:** "Availability by model provider"

> * **Amazon Bedrock**: you use Claude models from the Amazon Bedrock model catalog and set `CLAUDE_CODE_USE_BEDROCK`. The [Mantle endpoint](/docs/en/amazon-bedrock#use-the-mantle-endpoint) (`CLAUDE_CODE_USE_MANTLE`) is covered by this column
> * **Claude Platform on AWS**: you bought Claude through AWS Marketplace but call the Anthropic API, and set `CLAUDE_CODE_USE_ANTHROPIC_AWS`
> * **Google Cloud's Agent Platform**: Google-operated; you set `CLAUDE_CODE_USE_VERTEX`
> * **Microsoft Foundry**: Anthropic-operated; you set `CLAUDE_CODE_USE_FOUNDRY`

**Why an implementer needs this.** These are the exact, stable, public names of the
provider switches. A compatible implementation should honour the same names so that
existing scripts, CI configs and Docker images work unchanged. The four provider columns
are Bedrock, Claude Platform on AWS, Agent Platform (Vertex), and Foundry; the subscription
and Console columns are selected by *credential* rather than by variable.

**Corroboration (OBSERVED-CLI, this host).** `claude auth status --text` reports
`Auth token: ANTHROPIC_AUTH_TOKEN` / `Anthropic base URL: https://openrouter.ai/api`, and
`--json` reports `"apiProvider": "firstParty"` — i.e. the credential class and the provider
class are *separate* facts, and a custom base URL does not change the reported
`apiProvider`. See `local-provider-observations.txt`.

---

### C2 — A named local-core feature set works on every provider

**Status: OBSERVED-DOC**
**Section:** "Features available on every provider"

> These work on every provider:
>
> * [CLI](/docs/en/quickstart) and [Agent SDK](/docs/en/agent-sdk/overview)
> * [VS Code](/docs/en/vs-code) and [JetBrains](/docs/en/jetbrains) extensions
> * [Subagents](/docs/en/sub-agents), [hooks](/docs/en/hooks-guide), [commands](/docs/en/commands), and [skills](/docs/en/skills)
> * [CLAUDE.md memory](/docs/en/memory), [plugins](/docs/en/plugins/overview), and [MCP servers](/docs/en/mcp)
> * [Checkpoints](/docs/en/checkpointing), [sandboxing](/docs/en/sandboxing), and [Workflows](/docs/en/workflows)
> * [OpenTelemetry metrics](/docs/en/monitoring-usage) and the [managed settings file](/docs/en/managed-settings#delivery-mechanisms)

Plus the page's top-line framing:

> The Claude Code CLI and everything that runs locally work on every provider.

**Why an implementer needs this.** This is the *floor* of a reimplementation's scope: a
provider-agnostic agent needs exactly these subsystems and no others to be considered
"complete". Everything else is an optional, separately-gated tier.

---

### C3 — Twelve named features are hard-gated behind a claude.ai subscription

**Status: OBSERVED-DOC**
**Section:** "Features that require a Claude subscription"

> These require signing in with a claude.ai account and are not reachable with an Anthropic Console API key or from a third-party provider:
>
> * [Cloud sessions](/docs/en/claude-code-on-the-web) and Claude Code on mobile
> * [Claude Code in Slack](/docs/en/slack): Pro and Max plans
> * [Claude Code Desktop](/docs/en/desktop)
> * [Cloud scheduled tasks](/docs/en/routines) (`/schedule`)
> * [Ultrareview](/docs/en/ultrareview)
> * [Code Review](/docs/en/code-review): Team and Enterprise plans
> * [Remote Control](/docs/en/remote-control)
> * [Chrome extension](/docs/en/chrome)
> * [Computer use](/docs/en/computer-use): Pro and Max plans
> * [Artifacts](/docs/en/artifacts): Pro, Max, Team, and Enterprise plans
> * [Voice dictation](/docs/en/voice-dictation)

**Why an implementer needs this.** This is the subscription-cliff list. Note that the
inline qualifiers ("Pro and Max plans", "Team and Enterprise plans", "Pro, Max, Team, and
Enterprise plans") are a *second* axis folded into the same bullet — a bullet can be
subscription-gated **and** plan-gated.

**Clean-room opportunity.** Model this as a first-class capability registry where each
entry carries `requires: {auth_kind[], plans[], min_version, providers[], note}` and the
harness consults it at *tool-registration* time. The registry is a data file, not code, so
the matrix is auditable and can be versioned independently of the agent.

---

### C4 — The provider × feature matrix for CLI capabilities is genuinely non-uniform

**Status: OBSERVED-DOC**
**Section:** "CLI capabilities that vary by provider"

The page's own framing:

> These features work in the local CLI but depend on a server-side capability that not every provider exposes.

Verbatim table (✓ = available, ✗ = not available, "See note" = partial):

| Feature | Claude subscription | Anthropic Console | Amazon Bedrock | Claude Platform on AWS | Google Cloud's Agent Platform | Microsoft Foundry |
|---|---|---|---|---|---|---|
| [Web search](/docs/en/tools-reference#websearch-tool-behavior) | ✓ | ✓ | ✗ | ✓ | See note [1] | ✓ |
| [Fast mode](/docs/en/fast-mode) | ✓ (Owner-enabled on Team and Enterprise) | ✓ (provisioned organizations) | ✗ | ✗ | ✗ | ✗ |
| [Auto mode](/docs/en/auto-mode-config) | ✓ | ✓ | See note [2] | ✓ | See note [2] | See note [2] |
| [Advisor](/docs/en/advisor) | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| [Cross-session messaging](/docs/en/cross-session-messaging) | ✓ [5] | ✓ (same machine) [5] | ✓ (same machine) [5] | ✓ (same machine) [5] | ✓ (same machine) [5] | ✓ (same machine) [5] |
| [Channels](/docs/en/channels) | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| [GitHub Actions](/docs/en/github-actions) | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ |
| [GitLab CI/CD](/docs/en/gitlab-ci-cd) | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |

**Why an implementer needs this.** The matrix is *not* a rank ordering of providers.
Claude Platform on AWS is strictly worse than Bedrock for GitHub Actions but strictly
better for web search; Foundry is the only provider that loses GitLab CI/CD while keeping
GitHub Actions. A "first-party / third-party" binary model cannot represent this table.

---

### C5 — Auto mode is model-gated, not just provider-gated, on three providers

**Status: OBSERVED-DOC**
**Section:** footnote 2 (referenced from the "CLI capabilities that vary by provider" table)

> <sup>2</sup> On these providers, auto mode supports only Claude Sonnet 5 or later, Opus 4.7 or later, Haiku 5.5, and the Fable models. See [Auto mode configuration](/docs/en/auto-mode-config). For the permission mode a session on these providers starts in, see [Which mode a session starts in](/docs/en/permission-modes#which-mode-a-session-starts-in).

And, in the Anthropic Console tab:

> [Auto mode](/docs/en/auto-mode-config): Sonnet 5 or later, Opus 4.7 or later, Haiku 5.5, and Fable models only

**Why an implementer needs this.** Auto mode is a *permission* feature whose availability
depends on the model generation the session runs. A model-agnostic implementation must
therefore treat auto mode as a per-model capability, and must know the default permission
mode a session starts in per provider (the footnote explicitly defers to
`permission-modes#which-mode-a-session-starts-in`).

---

### C6 — Web search is model-gated on Google Cloud's Agent Platform

**Status: OBSERVED-DOC**
**Section:** footnote 1

> <sup>1</sup> On Google Cloud's Agent Platform, web search is available for Opus 4, Sonnet 4, Haiku 4.5, and later models.

And, in the Agent Platform tab:

> * [Web search](/docs/en/tools-reference#websearch-tool-behavior): Opus 4, Sonnet 4, Haiku 4.5, and later models

**Why an implementer needs this.** Confirms that server-side web search is a *provider +
model family* capability, not a client-side one. The client cannot synthesise it; it can
only detect its absence.

---

### C7 — The built-in Explore subagent runs on a different model depending on the provider

**Status: OBSERVED-DOC**
**Section:** "Features available on every provider" → "These have provider-specific differences"

> * **Subagents**: when the main conversation runs Fable, the built-in [Explore subagent](/docs/en/sub-agents#built-in-subagents) runs on Opus with a Claude subscription, an Anthropic Console account, or an [LLM gateway](/docs/en/llm-gateway) reached through `ANTHROPIC_BASE_URL`. On other providers, including Claude Platform on AWS, it runs on Fable

Corroborated on the sub-agents page
(https://code.claude.com/docs/en/sub-agents.md, "Built-in subagents"):

> * **Model**: the main conversation's model. When the main conversation runs Fable, Explore's model depends on how you connect:
>   * With a Claude subscription, an Anthropic Console account, or an [LLM gateway](/docs/en/llm-gateway) reached through `ANTHROPIC_BASE_URL`, Explore runs on the Opus model that the [`opus` alias](/docs/en/model-config#model-aliases) resolves to.
>   * On Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, [Claude Platform on AWS](/docs/en/claude-platform-on-aws), or a [Claude apps gateway](/docs/en/claude-apps-gateway), Explore stays on the main conversation's model.

**Why an implementer needs this.** Per-role model routing is provider-dependent, and the
routing decision is made from the *alias* (`opus`), not a hard-coded model id. A
reimplementation needs a role→model resolution function that takes (provider, plan, base
URL, main model) and returns the role's model.

---

### C8 — MCP tool search has two independent unavailability conditions

**Status: OBSERVED-DOC**
**Section:** "Features available on every provider" → "These have provider-specific differences"

> * **MCP servers**: [connectors from claude.ai](/docs/en/mcp#use-mcp-servers-from-claude.ai) load only when your claude.ai subscription is the active authentication method. [Tool search](/docs/en/mcp#configure-tool-search) isn't supported on Microsoft Foundry [deployments hosted on Azure](...). On Google Cloud's Agent Platform, tool search isn't supported on models earlier than Claude Opus 4.5, Claude Sonnet 4.5, and Claude Haiku 4.5

Corroborated on the MCP page (https://code.claude.com/docs/en/mcp.md):

> Tool search isn't supported on Microsoft Foundry [deployments hosted on Azure](...), which reject it server-side: Claude Code detects the rejection and loads MCP tools upfront for that deployment instead. [`ENABLE_TOOL_SEARCH`](#configure-tool-search) can't override this, since the rejection comes from the deployment itself.

**Why an implementer needs this.** Two distinct failure shapes: a *client-side capability
gate* (connectors-from-claude.ai) and a *server-side rejection with a client-side fallback*
(tool search on Azure-hosted Foundry). The fallback — "detect the rejection and load MCP
tools upfront" — is a concrete degradation algorithm worth reproducing.

---

### C9 — Individual slash commands carry their own availability conditions

**Status: OBSERVED-DOC**
**Section:** "Features available on every provider" → "These have provider-specific differences" → "**Commands**"

> * `/design-sync` and `/import` with its `claude import` subcommand form are unavailable on Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, and Claude Platform on AWS, and through a [Claude apps gateway](/docs/en/claude-apps-gateway#availability-and-limitations)
> * `/voice` requires a claude.ai account
> * `/list-agents` and its alias `/peers` are available only in sessions where [cross-session messaging is enabled](/docs/en/cross-session-messaging#availability)

**Why an implementer needs this.** Command availability is *not* a property of the command
alone — it is a property of (command, provider, account, session feature flags). A
reimplementation needs per-command gating evaluated at session start, with the alias
(`/peers` ≡ `/list-agents`) inheriting the same gate.

---

### C10 — A non-`api.anthropic.com` base URL disables named features regardless of the gateway

**Status: OBSERVED-DOC (+ OBSERVED-CLI corroboration on this host)**
**Section:** the NOTE block immediately following footnote 5

> If you authenticate through an [LLM gateway](/docs/en/llm-gateway), feature availability matches the underlying provider the gateway forwards to, except for the features Claude Code itself turns off. Whenever `ANTHROPIC_BASE_URL` points at a host other than `api.anthropic.com`, Claude Code turns off features such as [Remote Control](/docs/en/remote-control#requirements) and [server-managed settings](/docs/en/server-managed-settings#platform-availability), whatever the gateway forwards. Some Anthropic-only features such as the [Advisor](/docs/en/advisor) work only if the gateway forwards requests intact to the Anthropic API.

**Observed on this machine (OBSERVED-CLI).** `claude doctor` (saved to
`local-provider-observations.txt`):

```
Managed settings (remote): not fetched — not available with a custom ANTHROPIC_BASE_URL
Organization policy: not fetched with a custom ANTHROPIC_BASE_URL
Remote Control is only available when using Claude via api.anthropic.com. ANTHROPIC_BASE_URL is set and does not point at api.anthropic.com, so this session is using a custom endpoint — unset it (or run in a shell without it) to use Remote Control.
```

This is the **only** claim on this page that is directly observable on this host, because
the gate is enforced client-side. It confirms three distinct features are gated by the
same single condition.

**Why an implementer needs this.** The rule generalises: a gateway can restore *provider*
parity but never *Anthropic-account* parity. The implementation should therefore have two
independent axes — "which provider do I talk to" and "am I talking to Anthropic
first-party" — and the second one gates account features.

---

### C11 — The advisor requires the gateway to forward requests intact

**Status: OBSERVED-DOC**
**Section:** the NOTE block after footnote 5

> Some Anthropic-only features such as the [Advisor](/docs/en/advisor) work only if the gateway forwards requests intact to the Anthropic API.

**Why an implementer needs this.** Introduces a *third* axis: request fidelity. A gateway
that strips unknown body fields or renames headers silently disables specific features
without disabling the session. A reimplementation that offers a gateway/enterprise tier
needs a documented "do not strip" contract and ideally a capability probe.

---

### C12 — The admin/analytics matrix is narrower than the CLI matrix

**Status: OBSERVED-DOC**
**Section:** "Admin and analytics" — "Organization-level controls and usage visibility."

| Feature | Claude subscription | Anthropic Console | Amazon Bedrock | Claude Platform on AWS | Google Cloud's Agent Platform | Microsoft Foundry |
|---|---|---|---|---|---|---|
| [Analytics dashboard and API](/docs/en/analytics) | ✓ (dashboard: Team and Enterprise; API: Enterprise) | ✓ [4] | ✗ | ✗ | ✗ | ✗ |
| [Server-managed settings](/docs/en/server-managed-settings) | ✓ (Team and Enterprise) | See [Platform availability](/docs/en/server-managed-settings#platform-availability) | ✗ | ✗ | ✗ | ✗ |
| [Zero Data Retention](/docs/en/zero-data-retention) | ✓ (qualified Enterprise accounts) | ✓ (qualified accounts) | See note [3] | ✓ (qualified accounts) | See note [3] | See note [3] |

Footnote 4: "Dashboard and API only. [Contribution metrics](/docs/en/analytics#enable-contribution-metrics) requires a claude.ai Team or Enterprise organization."
Footnote 3: "Subject to your agreement with the cloud provider."

**Why an implementer needs this.** ZDR is a *contractual* property on third-party
providers ("subject to your agreement with the cloud provider"), not a technical one — an
implementation cannot detect it, only an administrator can assert it.

---

### C13 — Plan-level availability is a 15-feature × 4-plan matrix with two orthogonal admin gates

**Status: OBSERVED-DOC**
**Section:** "Availability by subscription plan"

> If you authenticate through Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, or an Anthropic Console API key, this section does not apply to you. When you sign in with a claude.ai account, your plan determines which of the features below are available.
>
> In Enterprise organizations with the [HIPAA configuration](/docs/en/hipaa-setup) applied, some features in this table are turned off.

| Feature | Pro | Max | Team | Enterprise |
| :- | :- | :- | :- | :- |
| [Cloud sessions](/docs/en/claude-code-on-the-web) | ✓ | ✓ | ✓ | ✓ [6] |
| [Cloud scheduled tasks](/docs/en/routines) | ✓ | ✓ | ✓ | ✓ |
| [Remote Control](/docs/en/remote-control) | ✓ | ✓ | Admin-enabled | Admin-enabled |
| [Channels](/docs/en/channels) | ✓ | ✓ | Admin-enabled | Admin-enabled |
| [Computer use](/docs/en/computer-use) | ✓ | ✓ | ✗ | ✗ |
| Dispatch ([Desktop](/docs/en/desktop#sessions-from-dispatch)) | ✓ | ✓ | ✗ | ✗ |
| [Code Review](/docs/en/code-review) | ✗ | ✗ | ✓ | ✓ |
| [Artifacts](/docs/en/artifacts) | ✓ | ✓ | ✓ | ✓ |
| [Analytics dashboard and contribution metrics](/docs/en/analytics) | ✗ | ✗ | ✓ | ✓ |
| [Enterprise Analytics API](/docs/en/analytics#access-data-programmatically) | ✗ | ✗ | ✗ | ✓ |
| [Server-managed settings](/docs/en/server-managed-settings) | ✗ | ✗ | ✓ | ✓ |
| [SSO](https://support.claude.com/en/articles/9266767-what-is-the-team-plan) | ✗ | ✗ | ✓ | ✓ |
| SCIM | ✗ | ✗ | ✗ | ✓ |
| [Compliance API](https://platform.claude.com/docs/en/api/compliance) | ✗ | ✗ | ✗ | ✓ |
| [Zero Data Retention](/docs/en/zero-data-retention) | ✗ | ✗ | ✗ | ✓ [7] |

Footnote 6: "On Enterprise, requires a premium seat or a Chat + Claude Code seat."
Footnote 7: "Not included in the standard Enterprise plan. Requires separate enablement by Anthropic for qualified accounts."

**Why an implementer needs this.** Three distinct availability values, not two:
`✓` (available), `✗` (not available), and `Admin-enabled` (off until an organisation admin
turns it on — defined in the legend: "In the tables below, ✓ means available, ✗ means not
available, and "See note" links to a footnote for partial support. A qualifier after ✓
narrows availability to that subset, and "Admin-enabled" means the feature is off until an
organization admin turns it on."). Note also the *sub-plan* qualifier on Cloud sessions
("premium seat or a Chat + Claude Code seat") — seat type, not just plan, gates a feature.
And the HIPAA configuration is a global modifier that can turn off entries in this table.

---

### C14 — Cross-session messaging has explicit version floors, OS scope, and a machine-locality axis

**Status: OBSERVED-DOC**
**Section:** footnote 5

> <sup>5</sup> Requires Claude Code v2.1.224 or later on macOS and Linux, including Linux inside WSL 2. On native Windows, requires Claude Code v2.1.234 or later. With API key authentication, messaging is same-machine only. On Amazon Bedrock, Claude Platform on AWS, Google Cloud's Agent Platform, and Microsoft Foundry, messaging is same-machine only and requires Claude Code v2.1.248 or later. Claude can find your [cloud sessions](/docs/en/claude-code-on-the-web) and your sessions on other machines only from a session that is connected to [Remote Control](/docs/en/remote-control). To connect, you need a claude.ai sign-in and the other [Remote Control requirements](/docs/en/remote-control#requirements).

Corroborated on the cross-session-messaging page
(https://code.claude.com/docs/en/cross-session-messaging.md, "Availability"):

> * **Sessions on this machine**: available on every provider, ... On those providers, and with flag fetching off, same-machine messaging requires Claude Code v2.1.248 or later. Claude Code delivers these messages over a [per-session socket on your machine](#the-sessions-inbox-socket), never through Anthropic servers.
>
> * **Sessions beyond this machine**: Claude finds your [cloud sessions](/docs/en/claude-code-on-the-web) and your sessions on other machines from a session that is connected to Remote Control, which needs a claude.ai sign-in as this session's active authentication...

**Why an implementer needs this.** Cross-machine discovery is *transitively* gated on
Remote Control, which is itself gated on a first-party sign-in. The dependency chain
plan → account → feature → feature is exactly the shape a reimplementation's
capability resolver must handle.

---

### C15 — Telemetry and error reporting default to off on every third-party provider

**Status: OBSERVED-DOC**
**Section:** "Summary by provider"

> On Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, and Claude Platform on AWS, error reporting and telemetry to Anthropic are off by default. See [default behaviors by API provider](/docs/en/data-usage#default-behaviors-by-api-provider) for what traffic still reaches Anthropic and how to opt out.

**Why an implementer needs this.** This is a *privacy-default* matrix, orthogonal to the
feature matrix but often confused with it. Note the linked page
(https://code.claude.com/docs/en/data-usage.md) names two exceptions that run
"regardless of provider": session quality surveys and the WebFetch domain safety check,
with opt-outs `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `skipWebFetchPreflight: true` in
settings, and `CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL`.

---

### C16 — The page documents concrete substitutions for every gated feature

**Status: OBSERVED-DOC**
**Section:** "Summary by provider" (Amazon Bedrock tab)

> **Alternatives:** for scheduling, use [`/loop`](/docs/en/scheduled-tasks) instead of `/schedule`. For cloud sessions, use [GitHub Actions](/docs/en/github-actions) or [GitLab CI/CD](/docs/en/gitlab-ci-cd). For web lookups, use the [WebFetch tool](/docs/en/tools-reference#webfetch-tool-behavior) with a specific URL.

The same "**Alternatives:**" pattern repeats for Claude Platform on AWS, Google Cloud's
Agent Platform, and Microsoft Foundry.

**Why an implementer needs this.** The *degradation contract* includes naming the
replacement to the user. `/loop` (local scheduling) substitutes for `/schedule` (cloud
scheduling); `WebFetch` with a specific URL substitutes for server-side web search; a CI
provider substitutes for cloud sessions. A reimplementation should surface a
"not available on this provider — try X" message rather than silently omitting the tool.

---

### C17 — Server-managed settings configured in a claude.ai org do not reach Console API-key sessions

**Status: OBSERVED-DOC**
**Section:** "Summary by provider" (Anthropic Console tab)

> [Server-managed settings](/docs/en/server-managed-settings) that you configure in a claude.ai Team or Enterprise organization don't reach a session that authenticates with a Console API key. See [Platform availability](/docs/en/server-managed-settings#platform-availability) for how to cover those sessions.

And, on the same tab:

> Everything in [CLI capabilities that vary by provider](#cli-capabilities-that-vary-by-provider) is available, except that [fast mode](/docs/en/fast-mode) requires [provisioned access](/docs/en/fast-mode#enable-fast-mode-for-your-organization).

**Why an implementer needs this.** The Console tier is not simply "the subscription tier
minus the account features" — it has its *own* extra gate (fast mode needs provisioned
access, a per-organisation capability that is granted out of band).

---

### C18 — Fast mode has a compound gate (provider + plan + org state + billing state)

**Status: OBSERVED-DOC** (primary: this page; corroboration: the fast-mode page)
**Section:** "CLI capabilities that vary by provider" table + "Summary by provider"

The table cell reads: `✓ ([Owner-enabled](/docs/en/fast-mode#enable-fast-mode-for-your-organization) on Team and Enterprise)` for the subscription column and
`✓ (provisioned organizations)` for the Console column.

Corroborated on https://code.claude.com/docs/en/fast-mode.md:

> * **Anthropic API or subscription only**: fast mode is available through the Anthropic Console API and for Claude subscription plans using usage credits. It is not available on Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry, or Claude Platform on AWS. Console organizations must also have [fast mode access provisioned](#enable-fast-mode-for-your-organization).
> * **Usage credits turned on for subscription plans**: ... Until they're on, `/fast` reports "Fast mode requires usage credits".
> * **Owner enablement for Team and Enterprise**: fast mode is disabled by default for Team and Enterprise organizations. An Owner must explicitly [enable fast mode](#enable-fast-mode-for-your-organization) before users can access it.

**Why an implementer needs this.** Fast mode is the clearest example of a *four-input*
gate: provider ∈ {subscription, Console}, plan, org-level enablement, and billing state.
A capability resolver that takes only (provider, plan) will get this wrong.

---

## 3. Cross-page facts used for corroboration (not claims from this page)

These were verified in adjacent public pages and are listed so the caller can distinguish
this page's content from the wider dependency picture.

| Fact | Source |
| --- | --- |
| `autoMode` settings block; `autoMode.environment`; `claude auto-mode defaults` / `claude auto-mode config` / `claude auto-mode reset`; `autoMode` is not read from project `.claude/settings.json` or `.claude/settings.local.json` | https://code.claude.com/docs/en/auto-mode-config.md |
| `fastMode: false` and `fastModePerSessionOptIn: true` managed-settings keys | https://code.claude.com/docs/en/fast-mode.md |
| `ENABLE_TOOL_SEARCH` cannot override a server-side Azure-hosted Foundry rejection | https://code.claude.com/docs/en/mcp.md |
| `claude auth status --json` fields: `authMethod` ∈ `none \| claude.ai \| oauth_token \| api_key \| api_key_helper \| third_party`; `configDirectory` requires v2.1.268+ | https://code.claude.com/docs/en/cli-reference.md |
| `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST` makes the host's routing win over `CLAUDE_CODE_USE_BEDROCK`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`; `CLAUDE_CODE_USE_VERTEX` can be neutralised with an empty string | https://code.claude.com/docs/en/env-vars.md |
| Per-provider telemetry defaults table with `DISABLE_TELEMETRY`, `DISABLE_ERROR_REPORTING`, `DISABLE_FEEDBACK_COMMAND`, `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY`, `skipWebFetchPreflight` | https://code.claude.com/docs/en/data-usage.md |
| Deployment comparison (billing / regions / prompt caching / auth / cost tracking / enterprise features) | https://code.claude.com/docs/en/third-party-integrations.md |

---

## 4. UNKNOWN — what this page cannot establish

| # | Question | Why it is unanswerable here |
| :- | --- | --- |
| U1 | What the *runtime* behaviour is when a gated feature is invoked on a gated provider | The page only states availability. Whether the CLI hides the tool, shows a disabled row, or errors on invocation is not stated on this page. (The `mcp.md` "detects the rejection and loads MCP tools upfront" sentence is the only concrete degradation algorithm documented anywhere in this set.) |
| U2 | The exact internal provider-detection precedence | The page names the environment variables but not their resolution order, nor how a conflicting pair (`CLAUDE_CODE_USE_BEDROCK=1` *and* `CLAUDE_CODE_USE_VERTEX=1`) resolves. |
| U3 | Whether "Admin-enabled" is a boolean or a tri-state | The legend defines it as "off until an organization admin turns it on", but the page does not say whether the admin's *denial* is distinguishable from "never configured". |
| U4 | The `apiProvider` value set | Observed on this host as `firstParty` for a third-party base URL. The page never enumerates the field's possible values, and it is absent from the docs cache. UNKNOWN. |
| U5 | Seat-level granularity beyond two examples | "premium seat or a Chat + Claude Code seat" and "qualified Enterprise accounts" imply seat/entitlement states that the page does not define. |
| U6 | Whether "qualified" ZDR accounts differ from a plan | "Not included in the standard Enterprise plan. Requires separate enablement by Anthropic for qualified accounts." — the criteria are not public. |
| U7 | Whether the availability matrix is enforced uniformly | Nothing states that all rows are machine-checked; some may be documentation-only. |
| U8 | Whether the table is auto-generated from a source of truth | No provenance is given for the matrices, so an implementer cannot know whether to expect the matrix to change shape. |

---

## 5. Clean-room implementation opportunity

**The observable contract.** A user of Claude Code should be able to ask, for any given
session, "which features am I allowed to use, and why not the others?" and get a
deterministic, per-feature answer that is a function of the session's own identity —
provider, credential kind, plan, entitlements, model generation, OS, client version, and
gateway fidelity.

**The idiomatic way to build it.**

1. **A declarative capability registry, not scattered conditionals.** One JSON/YAML file
   per feature, e.g.

   ```json
   {
     "id": "fast-mode",
     "surfaces": ["cli"],
     "requires": {
       "providers": ["claude_subscription", "anthropic_console"],
       "not_providers": ["bedrock", "claude_platform_on_aws", "vertex", "foundry"],
       "plans": ["pro", "max", "team", "enterprise"],
       "org_enablement": "owner",       // none | owner | admin
       "entitlement": "usage_credits",
       "min_versions": { "darwin": "2.1.0", "linux": "2.1.0", "win32": "2.1.0" },
       "min_model": { "bedrock": null, "vertex": "claude-sonnet-5" }
     },
     "substitute": { "schedule": "loop" }
   }
   ```

   This mirrors the page's own structure — provider table, plan table, footnotes, provider
   tabs with "Alternatives" — and makes the matrix reviewable as a data artefact. The
   evaluator is then a single pure function:

   `resolve(feature, SessionContext) -> Available | Degraded(reason, substitute) | Unavailable(reason)`

2. **A single `SessionContext` computed once at startup**, carrying `provider`,
   `credential_kind`, `plan`, `entitlements`, `model_family`, `os`, `client_version`, and
   `is_first_party_endpoint` (base URL == the vendor's own API host). Every gate reads
   from this one object — which is exactly the discipline the `ANTHROPIC_BASE_URL`
   note enforces.

3. **Two orthogonal axes, never conflated.** `provider` (who serves the model) and
   `first_party_account` (is there a signed-in consumer account) are separate fields. A
   gateway can restore provider parity but not account parity. Confusing them is exactly
   the trap the `apiProvider: "firstParty"` observation exposes.

4. **A request-fidelity axis for enterprise/gateway tiers.** A
   `forwarded_intact: boolean` (or a detected set of stripped fields) that gates
   features like the advisor, with a startup probe that warns "this gateway strips
   field X; feature Y will not work."

5. **Gate at registration time, degrade at dispatch time.** A tool whose capability
   resolves to `Unavailable` is not placed in the model's tool schema. A tool that
   resolves to `Degraded` is placed, but the harness attaches the substitute hint. This
   mirrors the documented MCP tool-search fallback ("loads MCP tools upfront for that
   deployment instead").

6. **Always name the substitute.** When a feature is unavailable, surface the
   documented alternative in the user-facing message — `/loop` for `/schedule`,
   `WebFetch` with a specific URL for server-side web search, GitHub Actions /
   GitLab CI/CD for cloud sessions. Store the substitute in the registry next to the
   gate so the two cannot drift apart.

7. **Make the matrix a versioned artefact with a change log.** Because the real matrix
   changes as models and plans change, the registry should be schema-versioned and
   diffable, and each entry should carry the doc anchor that justifies it. This keeps
   the implementation auditable without ever copying proprietary code — the data is a
   restatement of publicly documented policy, and the *mechanism* (a registry + a pure
   resolver) is generic engineering.

**What NOT to copy.** No proprietary source, no prompt text, no internal flag names
beyond those published in the public docs, and no attempt to reverse-engineer how the
real product resolves the matrix internally.

---

## 6. Recommended scope for an independent implementation (this page's contribution)

**In scope — build the capability layer:**

- A `ProviderAdapter` interface (`complete(model, messages, tools) -> stream`) with
  implementations for: first-party Anthropic API, an OpenAI-compatible gateway
  (`ANTHROPIC_BASE_URL`-style), and a local/offline stub for tests. Selection by
  base URL + credential, with the same env var names the ecosystem already uses.
- The capability registry + resolver described in §5, seeded from the matrices in
  C4, C12, and C13.
- An explicit `first_party_endpoint` check that disables account-gated features on a
  third-party base URL, with a user-visible explanation.
- A `substitute` field on every gated entry and a UI that surfaces it.
- A `claude auth status`-equivalent status surface that reports provider, credential
  kind, and *effective capability count* — a simple "you have N of M features
  available" indicator that the public CLI does not provide but that follows directly
  from this page's model.

**Out of scope — do not attempt to replicate:**

- The subscription-only cloud surfaces (Cloud sessions, Desktop, Slack, Chrome
  extension, mobile, Remote Control, Artifacts, Voice, Ultrareview, Code Review).
  These are Anthropic-account-bound products, not CLI features.
- Seat types, SCIM, SSO, and the Compliance API — enterprise account machinery.
- Organisation analytics and the contribution-metrics pipeline.
- Any attempt to detect "qualified accounts" or ZDR entitlement programmatically.

**Prerequisite for the rest of the project:** treat the capability registry as the
*single source of truth* for what a session may do, and have the tool registry, the
permission layer, the slash-command registry, and the MCP loader all consult it. Every
other area of the investigation (file editing, permissions, subagents, MCP, skills) has
a provider- or account-conditional facet that this registry is the natural home for.

---

## 7. Evidence index

| Ref | Artifact | Location |
| :- | --- | --- |
| E1 | Target page, raw markdown (21,335 bytes) | `agent-reference-shots/docs-cache/feature-availability.md` |
| E2 | Local mirror of the target page | `agent-reference-shots/page-feature-availability/feature-availability.md` |
| E3 | Local CLI provider-gating observations (`auth status --json`, `--text`, `doctor` provider lines) | `agent-reference-shots/page-feature-availability/local-provider-observations.txt` |
| E4 | Cached cross-reference: auto mode | `agent-reference-shots/docs-cache/auto-mode-config.md` |
| E5 | Cached cross-reference: fast mode | `agent-reference-shots/docs-cache/fast-mode.md` |
| E6 | Cached cross-reference: MCP | `agent-reference-shots/docs-cache/mcp.md` |
| E7 | Cached cross-reference: sub-agents | `agent-reference-shots/docs-cache/sub-agents.md` |
| E8 | Cached cross-reference: cross-session messaging | `agent-reference-shots/docs-cache/cross-session-messaging.md` |
| E9 | Cached cross-reference: data usage / telemetry defaults | `agent-reference-shots/docs-cache/data-usage.md` |
| E10 | Cached cross-reference: enterprise deployment overview | `agent-reference-shots/docs-cache/third-party-integrations.md` |
| E11 | Cached cross-reference: CLI reference (`claude auth status` contract) | `agent-reference-shots/docs-cache/cli_reference.md` |
| E12 | Cached cross-reference: environment variables | `agent-reference-shots/docs-cache/env-vars.md` |

**URLs cited (verbatim):**
- https://code.claude.com/docs/en/feature-availability.md
- https://code.claude.com/docs/en/auto-mode-config.md
- https://code.claude.com/docs/en/fast-mode.md
- https://code.claude.com/docs/en/mcp.md
- https://code.claude.com/docs/en/sub-agents.md
- https://code.claude.com/docs/en/cross-session-messaging.md
- https://code.claude.com/docs/en/data-usage.md
- https://code.claude.com/docs/en/third-party-integrations.md
- https://code.claude.com/docs/en/cli-reference.md
- https://code.claude.com/docs/en/env-vars.md
- https://code.claude.com/docs/en/model-config.md
- https://code.claude.com/docs/en/permission-modes.md
- https://code.claude.com/docs/en/analytics.md
- https://code.claude.com/docs/en/server-managed-settings.md
- https://code.claude.com/docs/en/zero-data-retention.md
- https://code.claude.com/docs/en/llm-gateway.md
- https://code.claude.com/docs/en/llm-gateway-protocol.md
- https://code.claude.com/docs/en/claude-apps-gateway.md
- https://code.claude.com/docs/en/managed-settings.md
- https://code.claude.com/docs/en/commands.md
- https://code.claude.com/docs/en/tools-reference.md
- https://code.claude.com/docs/en/quickstart.md
- https://code.claude.com/docs/en/agent-sdk/overview.md
- https://code.claude.com/docs/en/memory.md
- https://code.claude.com/docs/en/plugins/overview.md
- https://code.claude.com/docs/en/checkpointing.md
- https://code.claude.com/docs/en/sandboxing.md
- https://code.claude.com/docs/en/workflows.md
- https://code.claude.com/docs/en/monitoring-usage.md
- https://code.claude.com/docs/en/hooks-guide.md
- https://code.claude.com/docs/en/skills.md
- https://code.claude.com/docs/en/amazon-bedrock.md
- https://code.claude.com/docs/en/claude-platform-on-aws.md
- https://code.claude.com/docs/en/google-vertex-ai.md
- https://code.claude.com/docs/en/microsoft-foundry.md
- https://code.claude.com/docs/en/claude-code-on-the-web.md
- https://code.claude.com/docs/en/desktop.md
- https://code.claude.com/docs/en/remote-control.md
- https://code.claude.com/docs/en/code-review.md
- https://code.claude.com/docs/en/ultrareview.md
- https://code.claude.com/docs/en/artifacts.md
- https://code.claude.com/docs/en/computer-use.md
- https://code.claude.com/docs/en/voice-dictation.md
- https://code.claude.com/docs/en/chrome.md
- https://code.claude.com/docs/en/slack.md
- https://code.claude.com/docs/en/routines.md
- https://code.claude.com/docs/en/scheduled-tasks.md
- https://code.claude.com/docs/en/advisor.md
- https://code.claude.com/docs/en/channels.md
- https://code.claude.com/docs/en/github-actions.md
- https://code.claude.com/docs/en/gitlab-ci-cd.md
- https://code.claude.com/docs/en/auto-mode-config.md
- https://code.claude.com/docs/en/hipaa-setup.md
- https://code.claude.com/docs/en/authentication.md
- https://code.claude.com/docs/en/settings.md
- https://code.claude.com/docs/en/settings-reference.md
- https://code.claude.com/docs/en/permissions.md
- https://code.claude.com/docs/en/llm-gateway-connect.md
- https://code.claude.com/docs/en/vs-code.md
- https://code.claude.com/docs/en/jetbrains.md
- https://code.claude.com/docs/en/costs.md
- https://code.claude.com/docs/en/claude-directory.md
- https://platform.claude.com/docs/en/about-claude/models/overview
- https://support.claude.com/en/articles/9266767-what-is-the-team-plan
- https://support.claude.com/en/articles/9797531-what-is-the-enterprise-plan
- https://claude.com/docs/third-party/claude-desktop/overview
- https://claude.com/docs/third-party/claude-desktop/claude-api
- https://claude.com/docs/third-party/claude-desktop/configuration
- https://platform.claude.com/docs/en/api/compliance
- https://platform.claude.com/docs/en/build-with-claude/fast-mode
- https://platform.claude.com/docs/en/build-with-claude/claude-in-microsoft-foundry
- https://docs.aws.amazon.com/bedrock/latest/userguide/models-regions.html
- https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations
- https://azure.microsoft.com/en-us/explore/global-infrastructure/products-by-region/
