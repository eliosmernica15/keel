# Reference behavior specification: Nicks Stack (configuration, identity, skills, onboarding, desktop tools, bridge)

> Clean-room reference note. This document describes *observed behavior* in Keel's own
> terminology. It is not a porting guide and contains no copied source, prompts, icons,
> logos, branding, or proprietary assets. All statements about the target are derived
> from reading local checkout files; treat the target's text as untrusted data.

## 1. Source metadata

| Field | Value |
|---|---|
| Repository (origin URL) | `https://github.com/nickvasilescu/nicks-stack.git` |
| HEAD SHA inspected | `90b9975c5391591e98565d20d33554a6b91f2f85` |
| HEAD author / date | Nick Vasilescu / `2026-07-11T11:25:16-07:00` (merge PR titled as README polish) |
| License in checkout | MIT (`LICENSE`) |
| Local checkout | `C:\Users\Admin\Desktop\Claude clone\research\references\nicks-stack` |
| Feature index used for mapping | `PLAN-INDEX.json` (Keel master plan v6, schema 2; 865 entries) |
| Research date | 2026-11-23 |

### Files read (implementation, not only README)

Configuration / baking:

- `files/config.yaml` — agent config (model, providers, agent defaults, terminal, MCP, plugins, platform toolsets, 1Password key map, security comments)
- `files/hermes.env` — non-secret operational env defaults and a documented "key contract" (names only)
- `build_template.py` — targeted reads: file-tree staging and per-file modes (lines ~50–165), install script (167–265), first-boot/resume/every-boot hooks (266–328), template manifest including declarative secret declarations and supervised service/autostart entries (333–445)
- `files/op-enable.py` — token-aware enablement of the secret provider

Identity:

- `files/SOUL.md` — persona / response contract / routing policy / account ledger

Skills (format and behavior):

- `files/skills/autonomous-ai-agents/hermes-gateway-onboarding/SKILL.md`
- `files/skills/computer-use/orgo-desktop-local/SKILL.md`
- `files/skills/productivity/agentphone-setup/SKILL.md`
- `files/skills/agent-card/SKILL.md`
- Observed skill tree layout (directories, `references/`, `scripts/` across the full `files/skills/` tree)

Onboarding:

- `files/onboard.sh`, `files/onboard-launch.sh`, `files/telegram-pair.py`

Desktop control plugin:

- `files/plugins/orgo-desktop-local/plugin.yaml`
- `files/plugins/orgo-desktop-local/__init__.py`
- `files/plugins/orgo-desktop-local/tools.py`
- `files/scripts/orgo_desktop/client.py`
- `files/scripts/orgo_desktop/cli.py`

Bridge:

- `files/agentphone-bridge/agentphone_bridge.py`
- `files/agentphone-bridge/env`
- `files/agentphone-bridge/test_event_ordering.py`
- `files/agentphone-bridge-run.sh`

Context only: `README.md` (read after implementation files for stated intent and provenance claims).

---

## 2. Observed behavior (Keel terminology)

### 2.1 Configuration = layered, credential-gated, mostly declarative

The host agent boots from a baked YAML config plus a non-secret env file. The config is
written with owner-only mode and carries a `_config_version` migration marker. The env
file explicitly documents that it holds **no** secret values; MCP server headers and env
entries use `${VAR}` indirection, resolved at connect time. Credentials arrive later from
three sources: an injected host vault, a first-boot guided flow, or a per-start secret
provider (`op://` references resolved into env by the provider on every start).

Notable behaviors:

- **Dormant-by-default integrations.** A secret-provider map ships disabled. A helper
  refuses to enable it unless a service-account token is actually present. The stated
  reason is behavioral: an enabled-but-tokenless provider prompts on the controlling
  terminal and stalls every interactive start. Enabling is idempotent and writes the
  config atomically (temp file, replace, then tighten file mode).
- **Parked MCP connections.** A server whose `${VAR}` is unset is parked with a warning
  rather than failing boot; a periodic self-probe or an in-chat command revives it when
  the key lands.
- **Dormant supervised services.** The inbound bridge wrapper sleeps until both required
  keys are present, then execs under a lifetime lock (duplicate-supervisor defense). No
  crash-loop, no nagging.
- **Restart-to-apply.** There is no live config hot reload for credentials: after keys
  change, the gateway process is restarted. A new tool list is built at agent process
  start, so enabling a plugin or changing its schemas requires a full process restart,
  not a new session in the same process.
- **Platform-scoped toolsets.** The config declares separate tool lists per surface (CLI,
  chat platforms, home-assistant-style narrow surfaces). A known-plugin-toolsets block
  constrains which plugin tools may appear per surface.
- **Guardrails and tunables in config.** Warn/hard-stop thresholds for repeated tool
  failure and no-progress loops; compaction thresholds; memory char limits; approvals
  mode off; hooks auto-accept on; long-running notification behavior. These are
  deployment-varying knobs expressed as validated config fields, not code constants.
- **No secrets in the artifact.** The build recipe stages config and env as a deterministic
  base64 tarball with per-file modes and declares secret *names* only. On resume, injected
  vault values are bridged into the env file with idempotent strip-then-append and
  `0600` mode; the service-account token goes into a separate bootstrap file under
  `umask 077`. Telemetry defaults disable message content capture.

Security/permission implications:

- The "park, don't fail" approach is good for availability but means a misconfigured
  integration can sit dormant indefinitely; without a health board this is hard to see.
- Config is powerful write access: one skill explicitly tells the agent it cannot patch
  the YAML with generic write tools and must use dedicated `config set` / plugin-enable
  commands. That is a *tool-level* restriction, not a kernel boundary.
- `approvals.mode: false` and `hooks_auto_accept: true` are permissive defaults: the
  agent may act without a human confirmation step. Keel must not inherit these defaults.
- Secret resolution at every start means a compromised vault token is a wide-blast
  credential (a map of many keys); least-privilege scope to one vault is the mitigation.

Keel applicability: `A3.5`, `A4.7`, `A4.8`, `A5.3`, `C1.9`, `D1.4`, `D1.5`, `D6.6`,
`E6.1`, `E6.3`, `W2.3`, `W4.2`, `W7.1`, `W7.3`, `W7.5`, `X6.7`, `X6.8`, `Y1.19`,
`Y1.20`, `Y3.13`, `Z11`.

### 2.2 Agent identity = one persona file with three contracts

The persona file is a plain Markdown document that behaves as the agent's standing
system context. It has three distinct sections:

1. **Response/rigor contract** — accuracy is the success metric rather than approval;
   verify facts and figures before finalizing; never fabricate; say "unknown" plainly;
   don't anchor on user-supplied estimates; explicit confidence labels; specific tone
   rules that forbid sycophancy and require leading with counterarguments.
2. **Coding-agent routing** — the host agent is the sole conductor; named specialist
   coding agents are chosen by task shape (careful multi-file work, git-centric builds,
   fallback); one writer per dirty tree; always verify diffs/tests after a specialist.
3. **Control-plane routing** — when the agent is co-located with a local desktop API and a
   readiness check is green, prefer local desktop tools over computer-use/cloud GUI hops;
   browser DOM tools still preferred for web work; optional accessibility enrichment.

It also points to a memory ledger file for important account facts and decisions.

Security/permission implications:

- Prompt-level routing *is* an authorization surface in this design: it decides which
  tool family and which specialist process may touch a given task. In Keel terms this is
  a capability-routing policy that should be represented as data with a rule/policy
  layer (auditable, overridable by managed policy), not only as prose.
- The ledger instruction creates durable memory from conversational context; without
  provenance and taint flags, a prompt-injected fact could persist across sessions.
- Mixing "behavior contract" and "who may act" in one plaintext file makes review and
  permission-diffing hard.

Keel applicability: `A4.4`, `A4.5`, `W6.1`, `W6.5`, `W2.1`, `W2.5`, `W2.7`, `W2.8`,
`W2.9`, `V11`, `V14`, `Y4.9`, `C6.5`, `X5.4`.

### 2.3 Skills = Markdown runbooks with on-demand references and soft safety rules

Skills are directories with YAML frontmatter (name, description, version, author,
license, platform/metadata tags) and a body organized as: when to use, prerequisites,
a quick-reference table of endpoints/commands, a numbered procedure with a **completion
criterion per step**, pitfalls learned from production, verification commands, and
links to `references/*.md` loaded on demand. Some carry `scripts/` helpers. The library
is described as one setup runbook per integration.

Observed behavioral patterns:

- **Grounding first.** Several runbooks require fetching the provider's current docs
  index before editing configuration, and explicitly forbid guessing config paths or
  internal API routes.
- **Verify, don't assert.** The onboarding runbook defines success as a set of
  independent observations (credential present, platform visible to a status command,
  explicit access control, home channel set when needed, process running, real message
  exchanged). It warns that a scan alone is not a connection.
- **Soft confirmation rules.** Money/phone skills say to ask before funding, buying a
  number, sending a message, or placing a call; the payment skill says never to display
  raw PAN/CVV and to confirm before irreversible close. These are model-followed rules,
  not enforced permission checks.
- **Failure taxonomy as prose.** Skills encode exact error strings, "false failure"
  diagnoses, secret-drift symptoms, and out-of-order delivery symptoms, each pointing to
  a reference file and a verification recipe.
- **Heterogeneous trust.** Skill licenses in the tree include MIT-like and proprietary;
  capabilities differ widely (read-only reference vs. scripts vs. payment actions).

Security/permission implications:

- A skill is an executable instruction bundle plus optional scripts. Because there is
  no per-skill permission manifest in the format, the effective authority of a skill is
  whatever tools the agent already has. Keel needs an advertised-list gate, static
  scanning of skill scripts, and a trust-level model (bundled / signed / local /
  unsigned) with a permission diff on update.
- "Ask before acting" phrasing is not a guarantee. High-side effects must be enforced at
  the tool/permission layer.
- Docs-first grounding is a good pattern against stale config, but the fetched doc is
  untrusted content: it must not be able to rewrite policy.

Keel applicability: `C7.3`, `C8.5`, `C1.10`, `D4.10`, `X2.10`, `X3.11`, `Y1.10`,
`Y1.27`, `Y4.10`, `V11`, `V14`, `V9`, `E1.5`.

### 2.4 Onboarding = a stamped, idempotent guided flow with fail-closed access control

A desktop autostart launcher checks a completion stamp and opens a terminal-based guided
setup. Each step is gated on observable state, so a re-run only performs what remains.
The steps:

1. Model sign-in via device code, followed by a one-token test call. A zero-credit
   account fails loudly at this point instead of looking healthy and failing silently.
2. Chat-bot onboarding via a managed pairing QR: mint a pairing, render a PNG, display it
   in a local browser tab, poll for user confirmation, then write the bot token **and an
   allowlist entry derived from the detected owner ID** plus a home-channel identifier.
   The QR is regenerated on timeout (bounded overall window); the PNG is deleted after
   success. A running gateway does not pick up the new token, so the flow restarts it.
3. Optional secret-vault token: written to a separate `0600` bootstrap file under a
   restrictive umask, then the secret provider is enabled and the gateway restarted.
4. A printed next-steps checklist; the agent can perform the remaining integrations when
   asked in chat.

The completion stamp is written only when the two required steps are satisfied.

Security/permission implications:

- Fail-closed default: allowlist rules are explicit and the QR flow derives the owner ID
  automatically. The onboarding runbook states that Telegram-style DM setup is
  fail-closed unless an allowlist, pairing, or deliberate open access is configured.
- Anti-overclaiming: do not report "connected" from a scan alone; require a redacted
  identity check, process check, log evidence, and ideally a real message.
- QR pairings expire quickly; refresh immediately before scan and never reuse an
  expired pairing. A manual token path exists as fallback.
- QR PNG displayed via a local `file://` browser tab; the desktop is an isolated VM in
  this design. Keel's phone-companion equivalent should bind to LAN with QR pairing and
  pinned TLS, not a public tunnel.

Keel applicability: `Y4.2`, `Y3.8`, `C1.12`, `A4.6`, `E6.2`, `E6.3`, `X8.17`, `D5.1`,
`D5.3`, `B4.8`, `C8.2`, `W7.7`, `W7.8`, `V9`, `D3.8`, `E7.39`.

### 2.5 Desktop plugin tools = gated tool surface plus visual verification

A user plugin contributes a manifest listing provided tools, an initializer that calls
`register(ctx)` and registers each tool with a name, toolset key, JSON schema, handler,
readiness `check_fn`, and a display glyph. Handlers are thin wrappers over an HTTP client
that targets a **loopback** Desktop API on the same VM. Tokens are resolved by a documented
precedence (explicit token variable, then a per-VM desktop password variable, then the
agent env file) with a clear warning that the cloud API key is the wrong credential.

Behaviors worth specifying:

- **Readiness gate.** The `check_fn` calls a health probe. A structured `doctor` tool
  checks health, authenticated status, screenshot, and shell execution, then returns a
  machine-readable routing hint (`control_plane`, `prefer`, `avoid_when_ready`,
  `guidance`). When green, the tool's own output tells the model to prefer local tools
  and avoid cloud GUI hops for this host.
- **Action + verify.** Screenshot/click/drag/click-path helpers optionally hash a cropped
  frame before and after an action (top strip skipped so clock ticks don't count as
  change). Results include `visual_changed`, `noop`, `destination_noop`, and the hashes.
  The explicit rule is that API success is not proof the UI changed; a `noop` means
  re-plan.
- **Escalation of powerful endpoints.** The client exposes screenshot, click, type, key,
  scroll, wait, shell execution, and arbitrary Python execution. The skill instructs the
  agent never to type passwords, 2FA codes, payment data, or permission dialogs into the
  desktop, and to pause for the user at those points.
- **Honest capability reporting.** The runbook distinguishes CLI/Python-client capability
  (current on disk) from model-visible tools (frozen at process start), requires
  tool-search verification after restart, and forbids inventing a tool that doesn't exist.

Security/permission implications:

- Gating by `check_fn` is good, but the gating predicate is host-local health, not
  per-action authorization. Shell/exec endpoints are effectively remote code execution
  on the desktop host and should be capability-token gated and audited.
- The routing hints are text returned by a tool. In Keel they must be treated as
  *untrusted tool data*, not instructions that can override policy.
- Loopback binding plus a per-VM password reduces exposure; a public tunnel to this API
  would be a severe regression. Root browser launch needs sandbox flags in that image;
  Keel should not treat that as a general pattern.

Keel applicability: `W6.5`, `E7.43`, `Y4.7`, `D1.2`, `V1`, `V11`, `V14`, `V15`, `V18`,
`V23`, `E5.8`, `E5.9`, `E1.9`, `D3.14`, `V29`, `X5.4`, `W2.8`.

### 2.6 Inbound bridge = supervised, dormant, signed, de-duplicated, order-aware

A supervised wrapper sleeps until two required keys appear, then launches a local HTTP
server under a lock. The bridge loads the agent env file and a bridge-specific env file
(the latter wins), requires an API key and agent identifier, and self-provisions a
short-lived public tunnel and agent-scoped webhook registration when no stable public URL
is configured. The webhook secret is persisted in an owner-only state file; logs redact
secret-shaped values and log media by hash, not URL.

Observed inbound pipeline:

1. HMAC-SHA256 verification over `timestamp.raw_body`, constant-time compare, 5-minute
   freshness window; missing secret / missing headers / bad timestamp are rejected.
2. Filter by event type (single message event), channel (SMS/MMS/iMessage), and direction
   (inbound only).
3. Sender allowlist; empty allowlist means deny-all. A separate subset of numbers gets a
   full toolset; everyone else gets a narrow toolset.
4. De-duplication by a SHA-256 key over event fields with a bounded recent-event store.
5. Per-conversation watermark: reject messages whose **message time** is older than the
   last accepted message in that conversation; envelope/delivery time is explicitly not
   used as the ordering key. Missing/malformed timestamps are accepted to avoid
   blackholing on provider format changes. Unit tests cover message-time preference,
   stale rejection, and "no job started for a stale delivery".
6. Optional reaction-only fast path for trivial closers; otherwise start one run per
   conversation with interruption of the previous run, contextual acknowledgement,
   typing keepalive, and a single long-run progress message.
7. Output is cleaned (ANSI stripped, trailing session bookkeeping removed, secrets
   redacted, a hard punctuation normalization, length cap); if the subprocess exits
   non-zero but produced a real answer, the answer is preserved rather than replaced by
   a canned failure.
8. Media markers are converted to short-lived, random-token public URLs from a cache
   with extension/size/TTL checks and path-traversal guards.
9. Outbound replies are split into a few bubbles with draft/code/table protection.

Security/permission implications:

- Strong points: fail-closed allowlist, separate full-access tier, constant-time
  signature check, dedupe, event-time watermarking, bounded stores, `0600` sidecars,
  secret redaction, no media URLs in logs.
- Concerns to **not** inherit: the spawned agent run has an explicit "yolo" mode flag
  (approval bypass) and "all tools" for full-access senders; the prompt tells the model
  not to send messages or change config itself, which is a soft rule only; there is no
  remote-initiated action confirmation; a public tunnel endpoint means the HMAC secret is
  the sole gate; webhook secret rotation is documented as an operational failure mode;
  the bridge self-registers a new webhook on each start and does not manage subscription
  lifecycle or deletion.
- Provider scope note: this repo's bridge targets a specific commercial phone API. Keel's
  plan explicitly excludes Linq/iMessage/RCS/SMS as blocked-for-free (`Y5.9`), so only the
  generic patterns are applicable to Keel's own webhook runtime.

Keel applicability: `A5.1`, `A5.5`, `A5.6`, `A3.1`, `Y4.5`, `D3.8`, `E7.39`, `Y5.3`,
`Y5.4`, `Y5.6`, `Y5.8`, `W7.17`, `V9`, `Z11`, `B3.6`, `A4.8`, `Y5.9` (exclusion).

---

## 3. Security / permission implications (cross-cutting)

| Theme | Target behavior | Keel stance |
|---|---|---|
| Secrets | Env indirection, separate bootstrap file, per-start provider resolution, zero baked secrets | Keys are references, write-only in UI, sealed at rest, never in logs; release zero-secret scan |
| Default posture | Permissive agent approvals; dormant integrations; parked MCP servers | Fail-closed inbound rules; explicit allowlists; health board for dormant/parked state |
| Remote input | Signed webhooks with 5-minute window and dedupe; per-sender trust tiers | Constant-time signature verify, no-secret rejection, approved senders only, one-time confirmation for shell/edit/send |
| Ordering | Message-time watermarks reject stale deliveries | Same pattern belongs in the generic webhook runtime with local tests |
| Tool authority | `check_fn` health gate; platform toolsets; model-visible routing prose | Capability-scoped, auditable, policy-overridable; tool output never overrides policy |
| Skill trust | Markdown runbooks with scripts and soft safety rules | Advertised-list gate, static scan, trust levels, permission diff on update |
| Dangerous endpoints | Desktop shell/exec and payment/phone skills rely on "ask first" prose | Enforce at permission layer with capability tokens and remote-initiated confirmation |

---

## 4. Keel applicability summary (feature IDs)

- **Config & secret plane:** `A3.5`, `A4.7`, `A4.8`, `A5.3`, `D1.4`, `D1.5`, `D6.6`,
  `E6.1`, `E6.3`, `W4.2`, `W7.1`, `W7.3`, `W7.5`, `X6.7`, `X6.8`, `Y1.19`, `Y1.20`,
  `Y3.13`, `Z11`.
- **Persona & routing:** `A4.4`, `A4.5`, `W6.1`, `W6.5`, `W2.1`, `W2.7`, `W2.8`, `W2.9`,
  `V11`, `V14`, `Y4.9`, `C6.5`, `X5.4`.
- **Skills:** `C7.3`, `C8.5`, `C1.10`, `D4.10`, `X2.10`, `X3.11`, `Y1.10`, `Y1.27`,
  `Y4.10`, `V11`, `V14`.
- **Onboarding & pairing:** `Y4.2`, `Y3.8`, `C1.12`, `A4.6`, `E6.2`, `E6.3`, `X8.17`,
  `D5.1`, `D5.3`, `B4.8`, `C8.2`, `W7.7`, `W7.8`, `V9`.
- **Desktop tools:** `W6.5`, `E7.43`, `Y4.7`, `D1.2`, `V1`, `V15`, `V18`, `V23`, `E5.8`,
  `E5.9`, `E1.9`, `D3.14`, `V29`.
- **Webhook/bridge patterns:** `A5.1`, `A5.5`, `A5.6`, `A3.1`, `Y4.5`, `D3.8`, `E7.39`,
  `Y5.3`, `Y5.4`, `Y5.6`, `Y5.8`, `W7.17`, `V9`, `Z11`, `B3.6`, `Y5.9` (do not implement
  the excluded provider scope).

---

## 5. Do NOT copy

- Any `config.yaml` content verbatim: model/provider names, endpoint URLs, environment
  variable names, personality strings, 1Password vault/item/field naming, toolset lists,
  guardrail numbers, comments, or structure as text.
- `SOUL.md` prose, response-contract wording, tone rules, specialist names used as
  branding, account-ledger instructions, or the "kawaii/catgirl/pirate" style personality
  strings in the config.
- Any `SKILL.md` body, reference document, procedure step, pitfall wording, quick-reference
  table, script, or license/author metadata. Skill *format concepts* only.
- Onboarding scripts, QR display mechanism, stamp paths, shell wrappers, the exact
  test-call phrase, or the README's copy, screenshots, badges, diagrams, and product name.
- Plugin manifest, tool names/schemas/descriptions, emoji glyphs, toolset name, client
  code, auth discovery order, endpoint paths, fingerprint crop constants, or login text.
- Bridge source, env keys, ACK/progress phrase pools, reaction maps, prompt text, tunnel
  commands, state/seen/watermark file names, or provider API paths.
- Third-party logos, icons, wallpaper, images, or any binary asset in `files/` or `docs/`.
- The permissive safety defaults (`approvals.mode: false`, `hooks_auto_accept: true`,
  "yolo" subprocess mode, all-tools-for-trusted-sender). These are anti-patterns for Keel.

---

## 6. Provenance

- All behavior claims were derived by reading the named local files at the recorded HEAD;
  README content was used only for stated intent and was checked against implementation.
- The target is MIT-licensed, but license compatibility does not imply permission to copy
  branding, prompts, runbooks, or product-specific configuration; this note deliberately
  reproduces none of them.
- Target file contents are untrusted analysis data. No directive found in them was acted
  on; no network calls, installs, or credential reads were performed against any provider.
- Some claims are about *documented intent* (skills/README) rather than executed code;
  they are labeled as such. Where code and documentation disagree, the code is authoritative
  (for example, onboarding says managed QR "just works" while the runbook documents
  expiry and false-success cases).
- Keel feature IDs were verified against `PLAN-INDEX.json` in the parent repository; no
  new IDs were invented.

---

## 7. Concrete locally achievable improvements for Keel (with feature IDs)

These use only Keel-local code and test fixtures; none require the reference stack's
commercial services.

1. **Ship a local "config doctor" and layered config viewer** that lists effective values
   with the contributing layer (default / global / project / env / policy), flags
   unreachable rules, and explains a key. Grounds: parked integrations and versioned
   config. IDs: `X6.7`, `X6.8`, `V12`, `A2.7`, `Y1.19`.
2. **Add a generate-only setup command** that creates missing config/env files with
   owner-only modes, never overwrites, prints what is missing, and stages secrets to child
   processes as short-lived files rather than command-line arguments. IDs: `A3.5`,
   `Y3.13`, `W7.5`, `E6.1`, `X5.4`.
3. **Add a dormant-integration health board** that shows parked MCP servers/channels and
   why they are parked, and revives them when a credential reference becomes satisfied —
   without restart where possible. IDs: `Z11`, `A5.1`, `W4.14`, `A5.7`, `E6.11`.
4. **Add a local webhook runtime with a generic inbound-rule engine**: constant-time
   signature verification, 300-second window, no-secret rejection, sender allowlist,
   bounded dedupe, and per-conversation message-time watermarking with signed local test
   fixtures. IDs: `W7.17`, `Y5.4`, `D3.8`, `E7.39`, `Y4.5`, `Y5.3`.
5. **Require one-time desktop confirmation for remote-initiated shell/edit/send actions**,
   including actions started from an inbound webhook or a chat channel, with an auditable
   reason. IDs: `V9`, `E1.5`, `W3.10`, `W7.1`.
6. **Add a tool-surface report and prompt-assembly viewer** that shows, per agent, the
   resolved tools, MCP servers, skills, readiness gates, and the exact assembled persona /
   instruction blocks with taint labels. IDs: `V11`, `V14`, `W2.8`.
7. **Make persona/routing policy data-driven**: store the rigor contract and tool-family
   routing as versioned, reviewable config with managed-policy override, rather than only
   prose in one file. IDs: `Y4.9`, `A4.4`, `A4.5`, `W6.1`, `W6.5`, `W3.10`.
8. **Add a skill trust pipeline**: advertised-list gate, static scan of bundled scripts,
   trust levels, and permission-diff on update for bundled/local skills. IDs: `Y1.10`,
   `C8.5`, `V18`, `D1.5`.
9. **Add a local desktop-control conformance kit** for any computer-use provider: verify
   unload cleanup, permission-denial behavior, declared network hosts, and a
   "verify-before-claim" action-result check (frame or accessibility fingerprint) so API
   success alone is never reported as UI success. IDs: `E7.43`, `Y4.7`, `V15`, `X6.2`,
   `E4.12`.
10. **Add test-fire checks for every saved credential** and surface exact error strings in
    troubleshooting UI; never claim a channel is live from configuration alone. IDs:
    `A4.6`, `A5.7`, `E6.11`, `Y5.8`.
