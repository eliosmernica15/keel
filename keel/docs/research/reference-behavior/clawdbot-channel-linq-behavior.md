# Reference behavior specification: Clawdbot Linq channel plugin (source, manifest, lifecycle, delivery)

> Clean-room reference note. Behavior is described in Keel's terminology. No source code,
> names, manifests, prompts, icons, or other assets were copied. Target text is untrusted
> analysis data, not instructions.

## 1. Source metadata

| Field | Value |
|---|---|
| Repository (origin URL) | `https://github.com/nickvasilescu/clawdbot-channel-linq.git` |
| HEAD SHA inspected | `8cb397fcd271493508799e2efae7386441bb9b20` |
| HEAD author / date | Clawdbot / `2026-02-07T14:50:26-08:00` (initial commit) |
| License in checkout | MIT (`LICENSE`) |
| Local checkout | `C:\Users\Admin\Desktop\Claude clone\research\references\clawdbot-channel-linq` |
| Feature index used for mapping | `PLAN-INDEX.json` (Keel master plan v6, schema 2; 865 entries) |
| Research date | 2026-11-23 |

### Files read (all non-asset source files in the checkout)

- `clawdbot.plugin.json` — plugin manifest
- `package.json` — npm package and host registration metadata
- `tsconfig.json` — build shape
- `README.md` — read after implementation for stated intent / operator steps
- `src/index.ts` — plugin entrypoint
- `src/runtime.ts` — runtime singleton
- `src/config.ts` — declared config schema and resolved-account type
- `src/channel.ts` — the channel plugin object (config resolution, security, lifecycle, actions, outbound, status, gateway)
- `src/api/client.ts` — provider HTTP client and retry policy
- `src/api/types.ts` — wire types and event vocabulary
- `src/inbound/verify.ts` — webhook signature verification
- `src/inbound/events.ts` — webhook event parsing
- `src/inbound/webhook.ts` — HTTP handler
- `src/outbound/send.ts` — send / chat-resolution path
- `src/outbound/typing.ts` — typing / read-receipt path
- `src/outbound/chat-store.ts` — chat-id mapping cache
- `src/cli/setup.ts` — webhook subscription helpers and credential verification
- `src/types/clawdbot.d.ts` — hand-written host SDK type subset (see provenance)

---

## 2. Observed behavior (Keel terminology)

### 2.1 Plugin manifest and registration

There are two layers of declaration:

- A tiny manifest declares a plugin id, the channel ids it provides, and an empty config
  schema with `additionalProperties: false`.
- The package metadata declares an extension entrypoint and channel presentation fields
  (label, selection label, blurb, order, aliases, an icon name), plus an install spec.
  The runtime entrypoint's `register(api)` stores the host runtime in a module singleton
  and registers one channel via `api.registerChannel({ plugin })`.

The host SDK type declarations shipped in this checkout are hand-derived from the host's
compiled JavaScript because the SDK ships no `.d.ts`. They enumerate a large plugin surface:
config, pairing, capabilities, reload prefixes, security policy resolution, messaging
normalization, actions, setup, outbound (delivery mode / chunker / sendText / sendMedia),
status/probe, gateway start/logout, and generic registration helpers for channels,
providers, tools, hooks, HTTP routes, gateway methods, CLI, services, and commands.

Keel reading: this is a **single composable channel plugin**, not a special-cased core
channel. The declarative manifest is the install-time surface; the `register` object is
the runtime surface. Keel's `Y5.1` (plugin manifest and config namespace) plus `W1.1`
(everything is a plugin) are the direct analogues.

Security/permission implications:

- Manifest-level capability declarations are useful for review, but the empty config
  schema means the manifest itself validates nothing; the real schema is attached at
  runtime.
- The reverse-engineered typings are incomplete by construction. A plugin compiled
  against them can compile cleanly while calling host APIs whose real behavior is
  unverified. Keel should generate plugin-facing types from its own SDK surface.

Keel applicability: `Y5.1`, `W1.1`, `D1.1`, `D1.2`, `D1.5`, `V1`, `X6.6`, `D6.6`,
`E4.12`.

### 2.2 Config resolution = account inheritance with a validation gap

The package declares a Zod config schema covering: enabled flag, API token, token-file
path, from-number (E.164 regex), webhook secret, webhook path (defaulted), preferred
delivery service (enum), DM policy, group policy, allow lists, name, and an accounts map.
The channel then resolves configuration imperatively:

- Account ids come from the accounts map; if none exist, a default account id is used.
- Non-default accounts are resolved by shallow-spreading top-level config then the
  account entry, so account values override defaults.
- Enabled state requires both the top-level and the account-level flag to be non-false.
- Token resolution order is: per-account `apiToken`, then an environment token, then
  "none". There is a declared `tokenFile` field, but the resolution code never reads the
  file — a declared-but-inert credential source.
- The declared schema is *attached* to the channel (`buildChannelConfigSchema`) but the
  resolution path does not parse through it. Consequently the E.164 regex and enum
  constraints are documentation, not runtime enforcement.
- DM policy resolution defaults to pairing and produces a policy path, allow-from path,
  and an approval hint. Group policy defaults to allowlist via a warning collector; an
  "open" group policy produces a human-readable warning rather than a denial.
- Account deletion clears base fields (token, token file, from-number, webhook secret,
  name); logout deletes token/token-file/webhook-secret from config and writes it back.

Security/permission implications:

- Config-driven credentials stored inline are plaintext; the safer alternatives (token
  file, env var) are only partially implemented (env works, file does not).
- Defaults are fail-closed for DMs (pairing) and warn-only for groups. That is a reasonable
  posture, but a warning is not a policy: managed policy should be able to hard-deny.
- Resolved `fromNumber` is used without validating against the declared E.164 regex.
  Misconfiguration fails late (at first API call) instead of at load.

Keel applicability: `A5.3`, `D6.6`, `X6.7`, `E6.1`, `W7.3`, `W7.4`, `W3.10`, `W7.17`,
`Y5.1`.

### 2.3 Channel lifecycle = start / probe / register route / stop

`gateway.startAccount`:

1. Requires API token and from-number; throws on absence.
2. Resets the in-memory chat-id cache.
3. Records running state and start timestamp.
4. Probes the provider by listing chats. Failure is logged as a warning, **not** fatal —
   the account still starts.
5. Builds the inbound message handler (see 2.5).
6. Creates a webhook HTTP handler with the configured secret (empty string if absent) and
   registers it at the configured path through a host helper that scopes it by plugin id
   and account id.
7. Registers an abort listener that unregisters the route and records stop state; returns
   a `stop()` that does the same.

Status surfaces: default runtime, collected issues (unconfigured account, last error),
channel summary, account snapshot (configured, token source, running, last start/stop/error,
mode `"webhook"`, probe result, last inbound/outbound timestamps).

Lifecycle gaps observed:

- The webhook subscription helpers (create/list/delete subscription, credential check) are
  exported from a CLI/setup module but are **not called by the start path**. The operator
  must register the webhook and rotate/copy the signing secret manually.
- Underlying tunnel/public-URL provisioning is also external to the plugin (README shows
  a third-party tunnel with a changing URL), so route registration and provider
  registration can drift apart.

Security/permission implications:

- A warn-only probe means an account can appear "running" while credentials are invalid.
  Status must distinguish transport-up from credential-valid.
- No secret-rotation or subscription-lifecycle management; a stale secret silently
  rejects all inbound traffic (documented as a failure mode in the sibling repo).
- Abort handling unregisters the route, which is a good reversible-registration pattern
  (Keel's plugin scope tree).

Keel applicability: `A5.1`, `A5.7`, `Y5.1`, `Y5.3`, `Y5.6`, `Y5.7`, `Z11`, `D1.2`,
`V1`, `V15`, `E6.11`.

### 2.4 Inbound verification and parsing = signed, time-windowed, reply-first

The webhook HTTP handler:

- Answers `GET` with a health string; other methods than POST get 405.
- Reads the raw body as bytes/string and verifies `X-Webhook-Signature` and
  `X-Webhook-Timestamp` with HMAC-SHA256 over `${timestamp}.${rawBody}`.
- Replay protection rejects timestamps older than five minutes and timestamps more than
  five minutes in the future; supports an optional `sha256=` prefix; uses a constant-time
  comparison after a length check; rejects malformed hex.
- Returns 401 with a reason on failure. The README claims that without a configured
  secret all deliveries are rejected, but the verifier itself has **no empty-secret
  guard**: with no secret it computes an HMAC under an empty key. Honest providers cannot
  match, but a party that knows the secret is unset can forge a valid signature. So the
  behavior is "rejects honest traffic" rather than cryptographically fail-closed; Keel's
  inbound rules must explicitly refuse when no secret is configured (`Y5.4`).
- Sends HTTP 200 *before* parsing JSON or doing any work, then processes asynchronously;
  unhandled event types and bad JSON are logged and dropped.

Event parsing maps the provider's vocabulary into four kinds: inbound message (text parts
joined, media parts collected), status (delivered/read/failed), reaction (added/removed),
typing (started/stopped). Only message events are dispatched to the agent; the other three
are logged only.

Security/permission implications:

- Good: raw-body signing, constant-time compare, symmetric 5-minute window, fast 200
  acknowledgement, 401 with a reason on rejection.
- Missing: no explicit no-secret rejection (see 2.4), so an unset secret is forgeable.
- Missing: no de-duplication of event ids or provider idempotency keys, so retries can
  produce duplicate agent turns. No message-time watermark to reject out-of-order
  deliveries. A valid 200 does not mean the work succeeded (fire-and-forget).
- The signed-secret check is the only inbound gate before agent routing; sender
  authorization is a separate policy layer (see 2.5).

Keel applicability: `W7.17`, `Y5.4`, `D3.8`, `E7.39`, `A5.5`, `A5.6`, `Y5.3`, `X6.6`.

### 2.5 Inbound delivery into the agent = envelope, media, ack, typing, dispatch

For an accepted message the handler:

1. Records last-inbound time and caches the phone → chat-id mapping for later sends.
2. Loads config and resolves an agent route with a peer of kind `dm` (even though
   capabilities advertise group support).
3. Downloads media attachments through host media helpers with a 10 MB cap; download
   failures are logged and skipped, not fatal.
4. Formats an inbound envelope (channel label, sender, timestamp, previous timestamp) and
   finalizes an inbound context containing normalized From/To identifiers, session key,
   account id, chat type, message id, and media paths/urls/types.
5. Records session metadata from the inbound context, marks the chat read, optionally adds
   an acknowledgement reaction (emoji mapped to a provider reaction type, gated by an
   acknowledgement-reaction resolver and scope), and starts a typing indicator.
6. Dispatches through a buffered-block reply dispatcher; the `deliver` callback sends
   text first, then each media URL as a separate message, and records last-outbound time.
   The typing indicator is stopped in `finally`.

Outbound text is chunked with a host chunker at a configured limit (~10k characters) and
delivery mode is `direct`. The send path finds a cached chat id or creates a chat, strips a
prefix from the recipient identifier, filters empty text parts, and returns a message id.
Media sends prepend an optional caption part. The provider client retries HTTP 429/5xx and
network errors up to three times with fixed-base exponential backoff (no jitter, no
`Retry-After`), and includes the raw error body in error messages.

Security/permission implications:

- Group capability is advertised but inbound routing hard-codes DM; a group message would
  be treated as a direct conversation. Keel should keep chat type, mention policy, and
  tool policy consistent across capability declarations and routing.
- The `send` and `react` actions accept a caller-supplied recipient/message id and execute
  it directly. There is no allowlist check on the outbound action path even though inbound
  DM policy is fail-closed. A model-controlled `send` action can therefore message an
  arbitrary destination — the exact case Keel's remote-initiated confirmation covers.
- Reaction and acknowledgement hints are injected into the agent prompt as text. They
  influence behavior but do not constitute permission.
- Chat-id cache is written to a file under the user's home credentials directory with
  best-effort persistence and default file permissions, and an in-memory cache that is
  only reset on account start. No atomic write or owner-only mode.
- API errors embed response bodies, which may echo sensitive data into logs.

Keel applicability: `A5.5`, `A5.2`, `A5.3`, `A5.4`, `A5.6`, `Y5.6`, `Y5.8`, `V9`,
`E1.5`, `W3.2`, `W3.10`, `W7.4`, `D2.5`, `E1.17`, `C6.5`, `E7.43`.

### 2.6 Capabilities and extensibility surface

Declared capabilities: direct and group chats, reactions, threads, media, no native
commands, and block streaming. Additional surfaces: pairing id label and approval
notification, config reload prefixes, message-tool hints for reactions, an action list
(`send`, `react`), setup hooks for applying account config, outbound send hooks, status
and probe hooks, gateway start/logout, and a type declaration surface for SDK helpers.

Security/permission implications:

- Each registration is a capability grant. Keel's plugin scope tree should record channel,
  route, action, and hook registrations so unload/disable truly unwinds them.
- The plugin contributes prompt text to the agent (reaction hints). That is prompt assembly
  from a plugin and should be visible in Keel's prompt-assembly viewer with taint labels.

Keel applicability: `V1`, `D1.1`, `D1.2`, `V11`, `V14`, `X6.6`, `C5.5`, `E7.31`, `Y1.31`.

---

## 3. Security / permission implications (cross-cutting)

| Area | Observed | Risk / Keel stance |
|---|---|---|
| Credentials | Inline token supported; token-file declared but unused; env fallback works | Store only references; actually read file-based secrets with `0600`; write-only UI; scoped capability tokens |
| Config validation | Schema declared but not parsed at resolution; regex/enums not enforced | Validate at load, fail loud, never silently skip a missing referent |
| Inbound authenticity | HMAC raw-body, constant-time, symmetric 5-minute window; no explicit no-secret rejection | Adopt as generic inbound rule; reject when no secret is configured, add dedupe and message-time watermark |
| Replay / ordering | No event-id dedupe, no watermark | Duplicate or stale agent turns; local signed fixtures can test both |
| Lifecycle | Start probes warn-only; route unregistered on abort; no subscription management | Distinguish "transport up" from "credential valid"; manage webhook subscription lifecycle |
| Outbound actions | `send`/`react` use caller-supplied target with no allowlist | Require remote-initiated one-time confirmation and policy hard-deny |
| Chat store | Plain JSON under home, best-effort write, in-memory cache | Atomic owner-only writes; treat mapping as sensitive routing metadata |
| Capability honesty | Group advertised, DM-only routing; prompt hints as soft policy | Keep declarations, routing, and policy coherent; show assembled prompts |
| Type safety | SDK types reverse-engineered from compiled JS | Generate plugin-facing types from Keel's own SDK surface |

---

## 4. Keel applicability summary (feature IDs)

- **Plugin/manifest/lifecycle:** `Y5.1`, `W1.1`, `D1.1`, `D1.2`, `D1.5`, `V1`, `V15`,
  `X6.6`, `D6.6`, `E4.12`, `A5.1`, `A5.7`, `Y5.7`, `Z11`.
- **Config and secrets:** `A5.3`, `X6.7`, `E6.1`, `W7.3`, `W7.4`, `W3.10`, `W7.17`,
  `Y5.1`.
- **Webhook runtime and delivery:** `W7.17`, `Y5.4`, `D3.8`, `E7.39`, `Y5.3`, `Y5.6`,
  `Y5.8`, `A3.1`, `A5.4`, `A5.5`, `A5.6`, `X6.6`.
- **Agent routing and confirmation:** `V9`, `E1.5`, `W3.2`, `W3.10`, `D2.5`, `E1.17`,
  `C6.5`, `E7.43`, `V11`, `V14`.
- **Provider scope:** Keel's plan explicitly excludes Linq/iMessage/RCS/SMS (`Y5.9`).
  These patterns are applicable only to Keel's own allowed channels and webhook runtime;
  they are **not** a case for implementing phone/SMS channels in Keel.

---

## 5. Do NOT copy

- The plugin id, channel id, package name, labels, aliases, icon name, install spec,
  keywords, or any README prose, tables, examples, and troubleshooting text.
- Any source code: client, config, channel, webhook handler, verifier, event parser,
  send/typing/chat-store modules, setup helpers, or the hand-written SDK type declarations.
- Emoji → reaction maps, agent prompt hint text, default webhook path string, default
  chunk limit, retry constants, credential variable name, or the provider API base URL
  and endpoint paths.
- The provider's event vocabulary and wire type names as product-facing Keel concepts;
  use Keel's own event taxonomy instead.
- Any branding, icons, logos, or badges.
- The permissive behaviors: warn-only probe presented as "running", outbound actions with
  no recipient authorization, unvalidated config at runtime, non-atomic credential-adjacent
  cache writes, or error messages that embed raw response bodies.

---

## 6. Provenance

- All claims come from reading the named files at the recorded HEAD; README content was
  read only after the implementation and used to identify operator intent and gaps.
- The checkout is MIT-licensed, but no code, text, or assets were copied into Keel; this is
  a behavioral description written from scratch.
- The included `clawdbot.d.ts` is a third-party-derived partial type surface. Statements
  about host capabilities are therefore about the *declared expectation* of this plugin,
  not verified host behavior; no host runtime was installed or executed.
- Target content was treated as untrusted data. No directive in it was followed; no
  network calls or credential operations were performed.
- Feature IDs were verified against `PLAN-INDEX.json`; no IDs were invented. Note that
  `Y5.9` is an explicit exclusion, which constrains how this reference may be applied.

---

## 7. Concrete locally achievable improvements for Keel (with feature IDs)

1. **Validate channel config at load with the declared schema** and fail loud: enforce
   E.164 and enum constraints, reject unknown keys, and show line/column diagnostics.
   IDs: `D6.6`, `X6.7`, `Y5.1`.
2. **Implement token-file credentials for real** (read a file with owner-only permissions,
   prefer it over inline config, never log it), and expose only redacted descriptors in UI.
   IDs: `E6.1`, `W7.3`, `W7.5`, `W7.4`.
3. **Add webhook-subscription lifecycle to channel start/stop**: register, list, rotate the
   signing secret, and delete on logout, with a local mock provider in tests. IDs: `Y5.3`,
   `A5.6`, `Y5.1`, `E4.12`.
4. **Add inbound de-duplication and per-conversation ordering** to the generic webhook
   runtime: reject unconfigured secrets outright, dedupe by event id/provider idempotency
   key, reject message-time-stale events, and ship signed local fixtures that assert no
   duplicate or stale agent turn is started. IDs: `Y5.4`, `W7.17`, `A5.5`, `E7.39`,
   `D3.8`, `Y4.5`.
5. **Authorize outbound actions independently of inbound policy**: the `send`-style action
   must honor pairing/allowlist rules and require a one-time confirmation on the desktop
   when the action originates from a remote channel. IDs: `V9`, `E1.5`, `W3.10`, `W7.17`,
   `C1.12`.
6. **Separate "transport up" from "credential valid"** in channel status, and surface the
   precise failure reason in a per-channel troubleshooting card and an operator health
   board for dormant/unconfigured accounts. IDs: `A5.1`, `A5.7`, `E6.11`, `Y5.8`, `Z11`.
7. **Make chat-id/mapping caches durable and safe**: atomic writes, owner-only mode, and
   explicit invalidation on account change; treat mapping data as routing metadata.
   IDs: `W7.3`, `Y5.6`, `A5.5`.
8. **Keep capability declarations, routing, and policy coherent**: if a channel declares
   group chats, route groups as groups with mention and tool policy, not as DMs; add a
   conformance check that fails when declarations and routing disagree. IDs: `V15`,
   `E4.12`, `X6.2`, `W7.17`.
9. **Show plugin-contributed prompt text in the prompt-assembly viewer** with taint labels,
   and record channel/route/action/hook registrations in the plugin scope tree so disable
   truly unwinds them. IDs: `V14`, `V11`, `V1`, `D1.2`, `C5.5`.
10. **Generate plugin-facing SDK types from Keel's own declarations** instead of letting
    plugin authors reverse-engineer compiled JS; fail CI when a plugin references an
    undeclared host API. IDs: `X6.6`, `D6.3`, `D7.11`, `E4.12`.
