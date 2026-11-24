# DECISIONS.md — Keel Master Plan v6 Addenda Conflict Decision Record

> **PRIVATE INTERNAL DOCUMENT — NOT FOR PUBLICATION.**
> This is the builder's decision log. It must not be shipped in any installer, website, docs bundle, or public repository, and must not be posted to a public issue tracker. It is separate from the ADRs and is the authoritative record for owner-level choices (D1–D7, G1–G7) per X10.3. Publication of any derivative is gated by G7.

- **Record date:** 2026-11-23
- **Baseline:** `4deb532` (Review snapshot of Keel Master Plan v6 final implementation)
- **Scope:** Resolution of every documented conflict surfaced by the eight plan documents/addenda and the base verification pass.
- **Doc ID scheme:** `D-nnn` are this record's decisions. Source IDs are preserved verbatim so each decision is traceable to its origin (`C-n`, `X0.n`, `G n`, `D n`, `Y n.n`, `E n.n`, section numbers).

---

## Summary index

| ID | Title | Owner approval? | Status |
|----|-------|-----------------|--------|
| D-001 | Permission rule ordering: first-match wins; Tier 2 always above | no | decided |
| D-002 | Tier 2 safety services never disabled or replaced | no | decided |
| D-003 | Plugin composability with a protected permission/safety core | no | decided |
| D-004 | Config is data-only; reject unsafe YAML tags/expressions | no | decided |
| D-005 | Duet: Live Pair + Review Pair; independent reviewer cannot modify builder's work (D4) | **yes** | awaiting owner |
| D-006 | Keep loopback HTTP/SSE runtime | no | decided |
| D-007 | Desktop UDS/named-pipe transport spike (V31 / C-19) | **yes** | awaiting owner |
| D-008 | Treat website/document/MCP/agent content as untrusted | no | decided |
| D-009 | DLP protects actual output values, not just rendered text | no | decided |
| D-010 | Live provider tests are opt-in with user keys | no | decided |
| D-011 | No paid/hosted required dependencies | no | decided |
| D-012 | No telemetry or product analytics | no | decided |
| D-013 | Priority re-ranking; cap P0 at ~25% | no | decided |
| D-014 | Milestone splits: M19a–f, M11/M17/M22 | no | decided |
| D-015 | Dependency graph and critical path in PLAN-INDEX.json | no | decided |
| D-016 | Store distribution policy under the no-source rule | no | decided |
| D-017 | Free-tier register (FREE-TIER-REGISTER.md) | no | decided |
| D-018 | Model & voice license registry + CI gate | no | decided |
| D-019 | Offline CI / zero-network smoke test | no | decided |
| D-020 | Risk register and per-milestone rollback | no | decided |
| D-021 | Clean-room protocol (spec → build, provenance) | no | decided |
| D-022 | Record deliberate differences from opencode | no | decided |
| D-023 | Server-side (not client-side) watch-mode enforcement | no | decided |
| D-024 | Trim M0 reading list for already-read opencode docs | no | decided |
| D-025 | MCP 2026-07-28 fields treated as [T] for opencode only | no | decided |
| D-026 | Graded CI coverage tiers (security-critical = 100%) | no | decided |
| D-027 | Honesty without weakening hard security requirements | no | decided |
| D-028 | Keep Linux support and its test lane | no | decided |
| D-029 | No paid EV signing / hosted update storage | no | decided |
| D-030 | Agent-authored plugins: P2, off by default, never auto-enabled | no | decided |
| D-031 | Addendum 4 Section 5 corrections (§5.1–§5.6) | no | decided |
| D-032 | SQLite WAL replaces Supabase Postgres (locked) | no | decided |
| D-033 | G7 private-source CLI default; free-only search; docs out of scope | no | decided |
| D-034 | Owner gates G1–G7 adopted as binding builder stop-list | **yes** | awaiting owner |
| D-035 | Remaining open owner decisions D1, D2, D6, D7 | **yes** | awaiting owner |
| D-036 | Y6.4 "repo visibility Public" conflicts with v5 §0.1 private-source requirement — REJECTED as written; repo stays private | **yes** | owner-gated (do not implement) |
| D-037 | W1.18 "MIT license" conflicts with proprietary all-rights-reserved requirement — THIRD_PARTY_NOTICES only, Keel code NOT MIT | **yes** | owner-gated (do not implement) |

**Totals:** 35 decisions recorded; **4 require owner approval** (D-005, D-007, D-034, D-035).

---

## A. Security and architecture core

### D-001 — Permission rule ordering: first-match wins; Tier 2 always above

- **ID:** D-001
- **Title:** Permission rule ordering — preserve existing Keel semantics (deny → ask → allow → mode, first match wins).
- **Conflicting requirements (source IDs):**
  - Master Plan §6: "first match wins" rule ordering.
  - opencode (reference): "last match wins" rules (addendum5 findings; C-1).
  - C-1 explicitly asks to "pick one, document everywhere, record in DECISIONS.md"; its recommendation is last-match-wins for Tier 1 with deny-aggregation and Tier 2 always above.
  - Base-verification requirement (BV §11/Tier model): "Two permission tiers. Tier 1: deny/ask/allow, first match wins, wildcards. Tier 2 (non-configurable)… No rule, hook, plugin, policy file or setting reaches Tier 2."
- **Alternatives considered:**
  1. Adopt opencode last-match-wins (with deny-aggregation for multi-resource ops).
  2. Adopt last-match-wins only for Tier 1 while keeping Tier 2 above.
  3. **Preserve Keel first-match-wins, deny→ask→allow→mode, Tier 2 always evaluated above Tier 1.** (chosen)
- **Security implications:** First-match with deny evaluated first is fail-closed and matches the shipped Keel mental model; switching to last-match risks an owner's broad `allow` silently overriding a scoped `deny` (permission-order confusion). Deny-aggregation for multi-resource operations is retained as a defensive strengthening, but never by changing the core ordering. Tier 2 remains outside the rule engine entirely.
- **Chosen resolution:** Keep first-match-wins. Rule evaluation order is `deny → ask → allow → mode`; the first matching rule decides Tier 1. Wildcards remain allowed within Tier 1. For multi-resource operations, deny-aggregation is layered on top (any deny denies the whole op) without altering first-match semantics. Tier 2 checks always run above and independent of Tier 1. Document this uniformly in the interface spec, config reference, and PLAN-INDEX.json "Deliberate differences". The C-1 recommendation to switch to last-match is formally rejected.
- **Owner approval required?** no
- **Status:** decided

### D-002 — Tier 2 safety services never disabled or replaced

- **ID:** D-002
- **Title:** Tier 2 safety services are non-configurable and never disabled, replaced, or patched out.
- **Conflicting requirements (source IDs):**
  - C-10: dsh makes plugins everything, including safety layers (replaceable by patches).
  - Addendum 4 §5.4 (Y1.17, Y1.30) [T:OC-CONFIG, OC-PLUGINS]: policy enforcement plugins cannot be disabled by project config; add policies layer to Master §6 rule 6.
  - D1.1 (referenced by C-10): Tier 2 non-replaceable.
  - Base-verification security controls 2 & 3: protected paths denied regardless of rules; destructive-command analyzer on the resolved command.
- **Alternatives considered:**
  1. Follow dsh: make safety layers first-class plugins that can be swapped or disabled.
  2. Allow project config to turn off policy enforcement for "trusted" projects.
  3. **Keep Tier 2 outside the plugin/config surface; non-replaceable and always on.** (chosen)
- **Security implications:** If safety can be disabled by a repo-local config or a plugin, a malicious repository or plugin could neutralize the entire protection model (privilege escalation via configuration). Keeping Tier 2 immutable is the root of trust: protected paths, destructive-command analysis, consent-required tools, and the dangerous-mode interlock cannot be reached by any rule, hook, plugin, policy file, or setting.
- **Chosen resolution:** Tier 2 stays non-configurable and non-replaceable. No plugin, profile, patch, project config, or hook may disable or substitute a Tier 2 service. A CI test fails if any protected-path table or Tier 2 control is changed. This overrides any reference-repo design to the contrary.
- **Owner approval required?** no
- **Status:** decided

### D-003 — Plugin composability with a protected permission/safety core

- **ID:** D-003
- **Title:** Plugins are composable and swappable, but the permission and safety core is protected.
- **Conflicting requirements (source IDs):**
  - C-10: dsh's "plugins everything" model vs Keel's need for a protected core.
  - C-21: dsh agent-authored plugins (E7.37) — high risk.
  - Addendum 4 §5.4 (Y1.17, Y1.30): policy enforcement plugins cannot be disabled by project config.
  - Addendum 4 G7 note: plugin CLI uses private-source-only default (Y1.29).
  - Base-verification security control 9: plugins/MCP out-of-process, declared permissions, scrubbed env, per-server allowlists, tool-description pinning.
- **Alternatives considered:**
  1. Full dsh-style composability including swappable safety (rejected by D-002).
  2. No plugin system at all (loses composability, contradicts many planned rows).
  3. **Composable capability plugins with a sealed permission/safety core.** (chosen)
- **Security implications:** Composability is valuable but any extension that can rewrite the gate is a confused-deputy and supply-chain risk. Constraining plugins to additive capability surfaces, running them out-of-process with declared permissions and scrubbed environments, prevents extension code from weakening the core while preserving the ecosystem goal.
- **Chosen resolution:** Plugins may add tools, providers, UI, and connectors, but may not modify, disable, or override Tier 1 permission evaluation or any Tier 2 service. Plugins run out-of-process with declared permissions, scrubbed environment, per-server allowlists, pinned tool descriptions. Plugin CLI/docs default to private-source-only (Y1.29, G7). Agent-authored plugins are handled separately in D-030.
- **Owner approval required?** no
- **Status:** decided

### D-004 — Config is data-only; reject unsafe YAML tags/expressions

- **ID:** D-004
- **Title:** Configuration files are data-only; unsafe YAML tags/expressions are rejected.
- **Conflicting requirements (source IDs):**
  - C-11: dsh's `!!js` config feature allows code in config files.
  - C-11 resolution: do not adopt; config stays data-only; conditional composition via overlays/profiles only.
  - Addendum 4 clean-room Y1.35: `config_edit` proposes a validated diff the user approves; never touches Tier-2 settings.
  - Addendum 4 §5.4: policies layer must not be disableable by config.
- **Alternatives considered:**
  1. Adopt `!!js`-style code expressions for flexible config.
  2. Allow expressions but sandbox them.
  3. **Data-only config; reject/strip unsafe tags and expressions; composition via overlays/profiles.** (chosen)
- **Security implications:** Code execution from config is a direct RCE vector, especially for config shipped inside a repository or plugin. Data-only parsing with a strict schema and rejected custom tags closes this. Validated-diff editing plus exclusion of Tier-2 keys keeps config changes reviewable and non-privilege-escalating.
- **Chosen resolution:** Use a safe YAML subset with a strict schema; reject custom/unsafe tags (including `!!js` and any Python-object tags) and any expression evaluation. Conditional composition is achieved only through explicit overlays/profiles. `config_edit` produces a validated diff for user approval and can never write Tier-2 settings.
- **Owner approval required?** no
- **Status:** decided

### D-005 — Duet: Live Pair + Review Pair; independent reviewer cannot modify builder's work (D4)

- **ID:** D-005
- **Title:** Ship Duet as one surface with two modes — Live Pair and Review Pair — with a read-only independent reviewer; owner confirms D4.
- **Conflicting requirements (source IDs):**
  - X0.4: "Duet defined three ways (Master D4 open, Addendum 1 B2.3 reviewer pair, Addendum 2 C2.3 live pairing)."
  - X0.4 fix: ship both as one surface with two modes: *Live Pair* (ghost-text, handoff) and *Review Pair* (builder + independent reviewer); owner confirms D4.
  - Base-verification: "Keel Duet default design: builder agent + independent reviewer agent with different model/prompt; reviewer can only comment" and "Keel Duet (assumed pair mode, confirm D4)".
  - Base-verification open-decision note: "D4 Duet definition … remain open owner decisions."
  - Addendum 6 D4.1–D4.13 (UI foundations rows) implement the surface.
- **Alternatives considered:**
  1. Ship only reviewer pair (Addendum 1 B2.3).
  2. Ship only live pairing (Addendum 2 C2.3).
  3. Leave D4 open indefinitely.
  4. **Ship both as two modes of one surface; reviewer has comment-only access and cannot modify builder's work; owner ratifies D4.** (chosen)
- **Security implications:** The independent-reviewer value is nullified if the reviewer can edit the builder's work — it would collapse into collusion or self-review and break the separation of duties that the mode exists to provide. Comment-only access, a different model/prompt, and enforced write-blocking preserve independent review; the reviewer's output must also be treated as untrusted content (D-008).
- **Chosen resolution:** Implement a single Duet surface with two modes:
  - **Live Pair** — ghost-text assistance and explicit handoff between builder and assistant.
  - **Review Pair** — builder agent plus an independent reviewer agent using a different model/prompt; the reviewer is strictly read-only (comment/suggest only) and technically cannot modify the builder's work.
  Implementation proceeds on the assumed default, **but final ratification of D4 is an explicit owner decision** and is recorded here as awaiting owner.
- **Owner approval required?** yes
- **Status:** awaiting owner

### D-006 — Keep loopback HTTP/SSE runtime

- **ID:** D-006
- **Title:** Retain the loopback HTTP/SSE daemon runtime with token and origin checks as the shipped transport.
- **Conflicting requirements (source IDs):**
  - C-19: "Master says renderer to daemon over loopback HTTP with bearer token; DS shows no-port option."
  - Base-verification: "renderer talks to Python daemon over HTTP+SSE on 127.0.0.1 with per-launch bearer token and Origin/Host checks"; "Per-launch bearer token, loopback bind, Origin/Host allowlist, no CORS wildcard"; "Offline mode: daemon-level egress block except loopback."
  - Addendum 6: Electron starts Python daemon with an OS-assigned loopback port + per-launch token.
- **Alternatives considered:**
  1. Replace loopback entirely with UDS/named pipes on all surfaces (dsh no-port option).
  2. Drop bearer token because the port is loopback-only.
  3. **Keep loopback HTTP/SSE with per-launch bearer token, Origin/Host allowlist, no CORS wildcard, and loopback-only egress in offline mode.** (chosen)
- **Security implications:** Removing the token or CORS/origin checks would expose the daemon to any local process or a malicious webpage (DNS rebinding / CSRF to localhost). The token + origin allowlist + no-CORS-wildcard combination is the current root of trust and must not be weakened. Loopback bind also integrates with the offline egress block.
- **Chosen resolution:** Loopback HTTP/SSE remains the shipped runtime for `keel web`, the CLI, and the desktop baseline. All existing controls stay: per-launch bearer token, loopback bind, Origin/Host allowlist, no CORS wildcard, and daemon-level non-loopback egress blocking in offline mode. Any transport change is handled only through D-007 and never by silently dropping these controls.
- **Owner approval required?** no
- **Status:** decided

### D-007 — Desktop UDS/named-pipe transport spike (V31 / C-19)

- **ID:** D-007
- **Title:** Authorize a V31 spike for desktop UDS/named-pipe transport; adopting it as the default is owner-gated and TCP+token remains the fallback.
- **Conflicting requirements (source IDs):**
  - C-19 resolution: "Run V31 spike; recommended desktop uses UDS/named pipe, keel web and CLI use loopback+token. Owner confirms."
  - Addendum 7: local-socket transport spike to prove Electron ↔ Python over named pipe/UDS with streaming and backpressure on all three OSes before committing; keep TCP+token as fallback (V31).
  - Addendum 7 finding: "Keel decision C-19 / V31: UDS/Windows named pipe for desktop, loopback+token for keel web and CLI."
- **Alternatives considered:**
  1. Adopt UDS/named pipe as desktop default immediately, dropping TCP.
  2. Never investigate; keep loopback everywhere permanently.
  3. **Run the V31 spike only; keep loopback+token as shipped default and fallback; any switch requires owner confirmation.** (chosen)
- **Security implications:** UDS/named pipes can reduce local TCP exposure but introduce OS-specific access-control and framing complexities; an unproven switch could regress streaming/backpressure or create weaker permissions than the token-protected loopback baseline. Keeping TCP+token as fallback and requiring owner sign-off avoids an unvalidated security downgrade.
- **Chosen resolution:** Run the V31 spike as an experiment. Do not change the shipped default: desktop, web, and CLI continue with loopback+token (D-006) until the owner explicitly approves a switch per C-19. If approved later, `keel web` and CLI still keep loopback+token; desktop may use UDS/named pipe only after the spike proves streaming and backpressure on all three OSes, with TCP+token retained as fallback.
- **Owner approval required?** yes
- **Status:** awaiting owner

### D-008 — Treat website/document/MCP/agent content as untrusted

- **ID:** D-008
- **Title:** All website, document, MCP, and agent/peer content is tainted and can never auto-approve actions or read secrets.
- **Conflicting requirements (source IDs):**
  - C-5: nicks-stack persona asks for no ethics/propriety disclaimers and aggressive behaviour; resolution: adopt rigor and anti-sycophancy only (W6.3), never remove safety behavior.
  - Addendum 4 clean-room Y1.14: page content treated as untrusted; browser catalog behind consent.
  - Addendum 4 clean-room Y1.28: URL instructions fetched through SSRF-safe client and marked tainted.
  - Base-verification privacy: "Taint tracking: content from web, MCP, files and channels is untrusted and cannot trigger Tier-1 allows or secret reads."
  - Base-verification security control 6: taint labels on untrusted content; tainted content cannot auto-approve or read secrets; injection canary tests.
- **Alternatives considered:**
  1. Trust fetched/agent content to streamline automation (as some reference personas imply).
  2. Remove safety disclaimers/behaviour to match the nicks-stack persona wholesale.
  3. **Keep all safety behavior; adopt only rigor and anti-sycophancy; taint all external content and block it from auto-approval and secret access.** (chosen)
- **Security implications:** Indirect prompt injection from web pages, documents, MCP tool output, or a peer/reviewer agent is a primary exfiltration and unauthorized-action vector. Taint labels plus a hard rule that tainted content cannot approve tool use or read secrets contain this. Removing safety behavior would directly enable manipulation.
- **Chosen resolution:** Tag all content originating from websites, documents, MCP servers, files, channels, and peer/reviewer agents as untrusted/tainted. Tainted content may be displayed but cannot auto-approve Tier-1 allows, cannot read secrets, and cannot disable Tier 2. Use an SSRF-safe fetch client, keep the browser catalog behind consent, and maintain injection canary tests. From C-5, adopt only rigor and anti-sycophancy (W6.3); never remove safety behavior or disclaimers.
- **Owner approval required?** no
- **Status:** decided

### D-009 — DLP protects actual output values, not just rendered text

- **ID:** D-009
- **Title:** DLP must block or replace the actual sensitive value in program/code-mode output, not merely mask rendered text.
- **Conflicting requirements (source IDs):**
  - C-13: "DS says content replacement is not confidentiality; Keel's DLP must block or replace the value, not just content."
  - C-13 resolution: E1.7 enforced; DLP tests assert the program/code-mode value is also hidden.
- **Alternatives considered:**
  1. Accept DS position that replacing displayed content is sufficient.
  2. Mask only the rendered UI text.
  3. **Enforce E1.7: redact/replace the underlying value returned to code/program mode as well as any rendered text.** (chosen)
- **Security implications:** If DLP only masks the display while the real value remains in the model/program output (e.g., code mode, tool result, agent-visible string), a secret can be exfiltrated by asking the model to echo or encode it. Redacting the actual value at the data boundary is the only meaningful confidentiality guarantee; log/trace redaction must match.
- **Chosen resolution:** Enforce E1.7. DLP operates on the actual output value at the program/code-mode boundary, not just rendered text. Tests must assert that the sensitive value is hidden in both rendered output and program/code-mode output, and in logs/traces/errors.
- **Owner approval required?** no
- **Status:** decided

### D-010 — Live provider tests are opt-in with user keys

- **ID:** D-010
- **Title:** Real-provider e2e tests are opt-in and use the user's own keys; CI stays local/mock.
- **Conflicting requirements (source IDs):**
  - C-14: "DS: inference is cheap, do not ration real-API tests; Keel must stay free for user and CI."
  - C-14 resolution: provider e2e opt-in with user keys; Keel CI uses local/mock models; no paid dependency.
  - Addendum 4 §5.2 / paid-search exclusion (Y1.8): free providers only, self-hosted SearXNG etc.
- **Alternatives considered:**
  1. Run real-provider tests unconditionally in CI using Keel-paid keys (cost + dependency).
  2. Skip provider tests entirely.
  3. **Opt-in real-provider e2e with user-supplied keys; CI uses local/mock models.** (chosen)
- **Security implications:** Bundled or Keel-held keys create cost abuse, data-egress, and supply-chain concerns; requiring keys also violates the zero-account/no-key boot guarantee. Opt-in user keys keep the product free and ensure no user code is sent to a Keel-operated server.
- **Chosen resolution:** Real-provider e2e tests are opt-in (`--live` or documented flag) and require the user's own key; they never run in default CI. CI and the default test suite use local/mock models. Provider contract tests (X9.3: streaming, cancel, tool call, usage, errors) run against mocks in CI and against real providers only when explicitly enabled by the owner/user.
- **Owner approval required?** no
- **Status:** decided

### D-011 — No paid/hosted required dependencies

- **ID:** D-011
- **Title:** Keel stays free, local-first, and offline-capable; no paid, hosted, subscription, license-key, or mandatory-account dependency is required.
- **Conflicting requirements (source IDs):**
  - C-14 / C-16: DS assumes paid inference/CI scale and paid signing/hosted storage; Keel must stay free.
  - G6: any paid service, payment, subscription, license-key enforcement, or mandatory account requires explicit owner approval.
  - Base-verification free-first rules: free path defaults (Ollama/llama.cpp, SQLite WAL, keyring, Playwright/Chromium, whisper.cpp/Piper/Kokoro); "Not taken (paid/hosted/unsafe)…"; no paid third-party service anywhere; optional user-key adapters only.
  - Addendum 4 paid-to-free replacements table (Orgo cloud, Composio, xAI/Grok, ElevenLabs, Supabase, 1Password/Latitude/Honcho, tunnels, X API, etc.).
- **Alternatives considered:**
  1. Require a hosted backend/credits for parity with references.
  2. Bundle optional paid providers as defaults.
  3. **Free/local-only required path; optional user-owned adapters never required, bundled, or defaulted on.** (chosen)
- **Security implications:** Hosted dependencies create egress, data-egress, availability, and lock-in risks and contradict the offline guarantee. Requiring an account or payment also breaks privacy and free-first goals. Keeping the required path local removes these risks; any future paid feature is gated by G6 and requires owner sign-off.
- **Chosen resolution:** No paid/hosted service is a required dependency. Keel boots and completes a coding task offline with no network, account, or API key using a local model (CI-enforced). Adapters for services the user already has are optional, never required/bundled/defaulted. All paid-to-free replacements in addendum 4 are adopted. Any exception requires explicit owner approval under G6.
- **Owner approval required?** no
- **Status:** decided

### D-012 — No telemetry or product analytics

- **ID:** D-012
- **Title:** No product analytics or telemetry; traces and crash reports stay local.
- **Conflicting requirements (source IDs):**
  - C-17: DS has optional OTLP product analytics.
  - C-17 resolution: excluded — no telemetry (Master 6.18).
  - Base-verification design rule 18: no mandatory telemetry; crash reports and traces stay local; only unprompted network call is the disable-able update check.
- **Alternatives considered:**
  1. Adopt optional OTLP analytics.
  2. Opt-in telemetry.
  3. **Exclude all product telemetry; keep local OpenTelemetry-shaped spans only.** (chosen)
- **Security implications:** Any analytics endpoint is an exfiltration channel and a trust/privacy violation; optional does not mitigate risk of accidental enablement or data leakage. Local-only spans preserve debuggability without egress.
- **Chosen resolution:** No product analytics of any kind. Local OpenTelemetry-shaped spans remain allowed (data never leaves the device). The only unprompted network call is the disable-able update check, which is disabled in the offline CI job (D-019).
- **Owner approval required?** no
- **Status:** decided

---

## B. Plan-correction decisions (X0.x)

### D-013 — Priority re-ranking; cap P0 at ~25%

- **ID:** D-013
- **Title:** Re-rank all rows; P0 means "needed for a v1.0 that can ship safely" and is capped at roughly 25% of rows.
- **Conflicting requirements (source IDs):**
  - X0.1: "Priority inflation: most rows across the addenda are P0, so P0 no longer means anything."
  - X0.1 fix: P0 = v1.0 shippable safely; P1 = v1.x; P2 = later; cap P0 at ~25%; builder produces re-ranked list in PLAN-INDEX.json.
  - X0 (other requirements) restates X0.1.
  - Addendum 4 / 5 / 6 / 7 priority_order lists.
- **Alternatives considered:**
  1. Leave all rows P0 (rejected — meaningless priority).
  2. Cap P0 at 50%.
  3. **Cap P0 at ~25%; P1 = v1.x; P2 = later.** (chosen)
- **Security implications:** Focused P0 scope means security-critical work (Tier 2, sandbox, secrets, DLP) is explicitly in the first-ship bar rather than diluted among hundreds of "P0" cosmetic rows. Reduces the chance a safety row is deferred.
- **Chosen resolution:** Re-rank all registry rows into P0/P1/P2 with the ~25% P0 cap. Security-critical and "safety before power" rows (Master §7 sequence, X0.1) are prioritized within P0. Builder writes the re-ranked list into PLAN-INDEX.json.
- **Owner approval required?** no
- **Status:** decided

### D-014 — Milestone splits: M19a–f, M11/M17/M22

- **ID:** D-014
- **Title:** Split overloaded milestones into sub-milestones.
- **Conflicting requirements (source IDs):**
  - X0.2: M19 (desktop UI) overloaded; split into M19a shell/layout, M19b chat/composer, M19c review/diff/terminal docks, M19d fleet/board/memory views, M19e settings/forms/wizard, M19f polish/a11y/i18n.
  - X0.2b: split M11 into code-intel core vs engineering tools; M17 into voice vs documents vs meetings; M22 into packaging vs update feed vs stores.
  - milestone_decompositions (addendum3) enumerates the above.
- **Alternatives considered:**
  1. Keep the overloaded milestones as single blocks.
  2. Split only M19.
  3. **Apply all documented splits (M19a–f, M11 ×2, M17 ×3, M22 ×3).** (chosen)
- **Security implications:** Smaller milestones make review/dependency gating tractable, so security-sensitive UI (review/diff docks, settings/forms touching Tier-2-adjacent config, update feed) can be tested and accepted in isolation.
- **Chosen resolution:** Adopt the full decomposition from X0.2/X0.2b and milestone_decompositions. PLAN-INDEX.json and kickoff files use the sub-milestone IDs; dependency gating (D-015) applies at the sub-milestone level.
- **Owner approval required?** no
- **Status:** decided

### D-015 — Dependency graph and critical path in PLAN-INDEX.json

- **ID:** D-015
- **Title:** Generate a `deps` field and critical-path report; a row may not start until its dependencies are green.
- **Conflicting requirements (source IDs):**
  - X0.3: no dependency graph between milestones and rows; generate `deps` field in PLAN-INDEX.json and a critical-path report; builder may not start a row whose dependencies are not green.
- **Alternatives considered:**
  1. Rely on manual ordering.
  2. Generate deps but allow work to start anyway.
  3. **Generate deps + critical-path report and enforce the green-dependency rule.** (chosen)
- **Security implications:** Enforces "safety before power" and prevents security-critical rows from being skipped or built out of order (e.g., UI shipped before the permission gate it depends on). Provides auditable sequencing.
- **Chosen resolution:** Add `deps` to every row and emit a critical-path report. The builder must not start a row whose dependencies are not green. The rule is machine-checkable in CI.
- **Owner approval required?** no
- **Status:** decided

### D-016 — Store distribution policy under the no-source rule

- **ID:** D-016
- **Title:** Per-store distribution decision: accept only stores compatible with proprietary freeware and no public source/manifests; keep AUR binary and self-hosted APT/YUM.
- **Conflicting requirements (source IDs):**
  - X0.5: store distribution conflicts with "no source/no GitHub for users" (C1.2); Flathub requires public build manifests, some Linux stores expect open recipes.
  - X0.5 fix: per store record proprietary-freeware acceptance and public-manifest requirement; drop stores that fail; AUR binary package and self-hosted APT/YUM remain.
  - Base-verification source-protection control 13 and distribution rules.
- **Alternatives considered:**
  1. Publish source/manifests to enter all stores (violates owner requirement).
  2. Drop all third-party stores.
  3. **Record per-store attributes and drop stores requiring public source/manifests; keep AUR binary and self-hosted APT/YUM.** (chosen)
- **Security implications:** Publishing source or internal build manifests would expose private material and violate §0.1/§0.2. The filter prevents accidental source disclosure through distribution channels.
- **Chosen resolution:** Maintain a per-store register with two flags (accepts proprietary freeware? requires public manifest?). Drop any store that fails the no-source/no-GitHub rule. AUR binary package and self-hosted APT/YUM remain the Linux distribution path. First public binary release still requires G3 owner approval.
- **Owner approval required?** no
- **Status:** decided

### D-017 — Free-tier register (FREE-TIER-REGISTER.md)

- **ID:** D-017
- **Title:** Add and maintain FREE-TIER-REGISTER.md to track free-tier terms and exit plans.
- **Conflicting requirements (source IDs):**
  - X0.6: free-tier trap list incomplete (Vercel Hobby non-commercial, VirusTotal public API non-commercial, limited free private GitHub repos, Docker Desktop commercial terms).
  - X0.6 fix: FREE-TIER-REGISTER.md with service, term used, date verified, exit plan; re-verify at each gate.
  - Base-verification §3.2: re-verify any third-party price/free-tier/license claim at selection time and record the date.
- **Alternatives considered:**
  1. Rely on ad-hoc knowledge of free tiers.
  2. Assume all "free" tiers permit commercial redistribution.
  3. **Maintain a dated register with an exit plan and re-verify at each gate.** (chosen)
- **Security implications:** Using a non-commercial-tier service in a commercial-ready product is a legal/supply-chain risk; a dated register with exit plans avoids silent lock-in and non-compliant use.
- **Chosen resolution:** Create FREE-TIER-REGISTER.md recording service, exact term used, date verified, and exit plan for every free-tier dependency. Re-verify at each owner gate and whenever a dependency is selected. Non-commercial-only services are used only where their terms permit the intended use, with an exit plan documented.
- **Owner approval required?** no
- **Status:** decided

### D-018 — Model & voice license registry + CI gate

- **ID:** D-018
- **Title:** Enforce model/voice licensing with MODEL-AND-VOICE-LICENSES.json consumed by the UI license display and a CI gate.
- **Conflicting requirements (source IDs):**
  - X0.7: voice/ML licensing stated as "check" but nothing enforces it.
  - X0.7 fix: MODEL-AND-VOICE-LICENSES.json consumed by UI license display and CI gate; watch items: Piper (license changed between versions), Whisper model weights, Kokoro voices, diarization models (gated/non-commercial), ffmpeg build flags (GPL vs LGPL).
  - Addendum 4 paid-to-free replacements reference X0.7 license check.
- **Alternatives considered:**
  1. Manual license check at release time only.
  2. Trust upstream README license badges.
  3. **Machine-readable license registry enforced by CI and surfaced in UI.** (chosen)
- **Security implications:** Non-commercial or gated model/voice weights would taint a "free, commercial-ready" product; CI enforcement prevents an unreviewed license from entering a release. README badges are explicitly unreliable (Section Q: license file text, not README badge).
- **Chosen resolution:** Create MODEL-AND-VOICE-LICENSES.json as the single source of truth for model/voice/weight/build-flag licenses. A CI gate fails on unknown, gated, or non-commercial terms for anything bundled or required. The UI license display reads the same file. Watch items listed in X0.7 are explicitly tracked.
- **Owner approval required?** no
- **Status:** decided

### D-019 — Offline CI / zero-network smoke test

- **ID:** D-019
- **Title:** CI job runs the full smoke suite with the network namespace removed and fails on any outbound attempt.
- **Conflicting requirements (source IDs):**
  - X0.8: "Zero network without account" asserted but no test list.
  - X0.8 fix: CI job runs full smoke suite with network namespace removed; fails on any outbound attempt; update check disabled in that job.
  - Base-verification free-first: boots and completes a coding task with no network, no account, no API key (CI-enforced).
- **Alternatives considered:**
  1. Document the offline claim without a test.
  2. Test only a minimal subset offline.
  3. **Full smoke suite offline, fail on any outbound attempt, update check disabled in that job.** (chosen)
- **Security implications:** Verifies the no-egress guarantee that underpins privacy and offline safety; catches accidental telemetry, update checks, or provider calls. Directly supports D-011/D-012.
- **Chosen resolution:** Add an offline CI lane that removes the network namespace, disables the update check, and runs the full smoke suite. Any outbound connection attempt fails the job. This is the enforcement behind the "zero network without account" claim.
- **Owner approval required?** no
- **Status:** decided

### D-020 — Risk register and per-milestone rollback

- **ID:** D-020
- **Title:** Maintain RISKS.md and a revert plan line in every milestone kickoff file.
- **Conflicting requirements (source IDs):**
  - X0.9: no risk register or rollback plan per milestone.
  - X0.9 fix: RISKS.md (likelihood, impact, owner, mitigation) plus a "revert plan" line in every milestone kickoff file.
  - X10.1 definition-of-done includes a rollback note per row.
- **Alternatives considered:**
  1. Track risks informally.
  2. Register risks but no rollback.
  3. **RISKS.md + mandatory revert plan per milestone and rollback note per row.** (chosen)
- **Security implications:** A documented rollback path limits exposure window when a security-relevant change regresses (e.g., update integrity, gate changes). Assigning an owner and mitigation prevents orphaned risks.
- **Chosen resolution:** Create RISKS.md with likelihood, impact, owner, and mitigation for each risk. Every milestone kickoff file includes a "revert plan" line and every row's definition-of-done includes a rollback note (X10.1).
- **Owner approval required?** no
- **Status:** decided

### D-021 — Clean-room protocol (spec → build, provenance)

- **ID:** D-021
- **Title:** Reimplement all reference behavior via a two-step clean-room protocol with provenance logging.
- **Conflicting requirements (source IDs):**
  - X0.10: "Plan says 'reimplement from behavior' but gives no clean-room procedure."
  - X0.10 fix: two-step process — (1) analyst pass writes a behavior spec with no code pasted; (2) builder implements from the spec only; log which spec each module came from in the provenance file.
  - Section Q (addendum3): private teardown artifacts (inventory, behavior spec, screen spec, feature matrix, diff); none may ship; screen spec forbids visual styling and maps components to Keel tokens.
  - X10.2: provenance file per module (spec source, copied snippets with license, reviewer).
  - Addendum 4 clean-room: "[T:<src>] means source read this session, but implementation must still be reimplemented from behavior"; no copying; no [T] row implemented from copied code; no [S] row skips §6.
  - Addendum 7 ground rules: reimplement clean-room in Python; never copy code, names, icons, prompts, or text.
  - Base-verification: provenance/capture material must never enter an installer, website, or docs bundle.
- **Alternatives considered:**
  1. Copy reference code directly under "behavior reimplementation".
  2. Analyst writes spec that includes pasted code/prompts.
  3. **Analyst writes no-code behavior spec; builder implements from spec only; provenance logged; private artifacts never ship.** (chosen)
- **Security implications:** Prevents license contamination, buried prompts, and hidden backdoors from reference code; keeps capture/analysis material out of shipped artifacts (source-protection control 13). The no-paste rule is enforceable and auditable.
- **Chosen resolution:** Adopt the two-step protocol. Step 1 (analyst): produce private behavior/screen specs with no code, prompts, or visual styling pasted; map components to existing Keel tokens/components. Step 2 (builder): implement from the spec only. Record the source spec for every module in the provenance file (X10.2). All teardown artifacts stay private and never ship. [T] rows still require clean-room reimplementation; [S] rows follow §9.
- **Owner approval required?** no
- **Status:** decided

---

## C. Conflict-resolution decisions (C-n)

### D-022 — Record deliberate differences from opencode

- **ID:** D-022
- **Title:** Record intentional divergences from opencode (stricter permission model, shell command semantics, session-id handling) in PLAN-INDEX.json.
- **Conflicting requirements (source IDs):**
  - C-2: opencode allows everything including `external_directory`; Keel is intentionally stricter (W3.6) — list in PLAN-INDEX.json under "Deliberate differences".
  - C-3: opencode `` ! ``cmd`` runs outside permission flow and sends session id to remote MCP servers; Keel does neither (W5.4, W4.13) — intentional.
  - Addendum 5 findings: last-match-wins rules, default-ask exceptions, external_directory default allow, shell scanner refusing on parse failure, prompt commands with `!` shell injection outside permission flow, session ID in `_meta`.
- **Alternatives considered:**
  1. Match opencode behavior exactly for "parity".
  2. Silently diverge.
  3. **Keep Keel stricter and document each divergence as intentional in a "Deliberate differences" section.** (chosen)
- **Security implications:** Keel's stricter behavior (no blanket `external_directory` allow, no shell escape hatch outside the permission flow, no session-id leakage to remote MCP) is a security feature, not a gap. Documenting prevents future "parity" changes from weakening it.
- **Chosen resolution:** Maintain a "Deliberate differences" section in PLAN-INDEX.json listing at minimum: stricter default permissions vs W3.6, no `!` shell injection outside the permission flow (W5.4), and no session-id sent to remote MCP servers (W4.13). These are intentional and must not be "fixed" toward opencode behavior.
- **Owner approval required?** no
- **Status:** decided

### D-023 — Server-side (not client-side) watch-mode enforcement

- **ID:** D-023
- **Title:** Enforce watch-only/read-only mode on the server, not only in the client UI.
- **Conflicting requirements (source IDs):**
  - C-4: openman watch-only is client-side only; orgo-teammates enforces on server; Keel chooses server-side (Y2.14, W7.19).
  - Addendum 4 §5.5: orgo-teammates relay drops input in watch mode server-side (Y2.14) — add to M16 acceptance test.
- **Alternatives considered:**
  1. Client-side-only watch mode (trust the UI).
  2. Server-side enforcement (chosen).
- **Security implications:** Client-side-only restrictions are trivially bypassed by a modified client or direct API call. Server-side enforcement is the only real boundary; a bypass here could let a "watcher" mutate the builder's session.
- **Chosen resolution:** Enforce watch-only mode server-side (daemon/relay drops input in watch mode). Add the server-side drop behavior to the M16 acceptance test. This also reinforces the Duet reviewer-is-read-only rule (D-005).
- **Owner approval required?** no
- **Status:** decided

### D-024 — Trim M0 reading list for already-read opencode docs

- **ID:** D-024
- **Title:** Remove already-read opencode docs from the M0 reading list.
- **Conflicting requirements (source IDs):**
  - C-6: opencode agents/permissions/mcp-servers/commands docs are now read; remove from M0 list.
- **Alternatives considered:**
  1. Keep them in M0 anyway.
  2. **Remove them from M0; keep the [T] tag and clean-room requirement (D-021).** (chosen)
- **Security implications:** None negative; reading them is already complete. The clean-room rule still prevents copying. Avoids wasted M0 time that could be spent on unread security material.
- **Chosen resolution:** Remove the listed opencode docs from the M0 reading list. Their content remains as [T] behavior evidence only and is still subject to clean-room reimplementation (D-021).
- **Owner approval required?** no
- **Status:** decided

### D-025 — MCP 2026-07-28 fields treated as [T] for opencode only

- **ID:** D-025
- **Title:** Treat opencode-specific MCP pool/protocol fields referencing the 2026-07-28 revision as [T] for opencode only and verify against the official MCP spec in M0.
- **Conflicting requirements (source IDs):**
  - C-7: opencode MCP pool/protocol fields refer to a 2026-07-28 MCP revision; treat as [T] for opencode only and verify against official MCP spec in M0.
- **Alternatives considered:**
  1. Adopt the 2026-07-28 fields as authoritative.
  2. Discard them entirely.
  3. **Treat as [T] opencode-only and verify against the official spec in M0.** (chosen)
- **Security implications:** Implementing against an unverified/possibly private protocol revision risks interoperability bugs and unknown security properties. Verifying against the official spec before implementation is the safe path.
- **Chosen resolution:** Mark those MCP fields [T] for opencode only. Do not bake them into Keel's MCP implementation until M0 verifies the behavior against the official MCP specification. Hostile-server conformance tests (X9.4) still apply.
- **Owner approval required?** no
- **Status:** decided

### D-026 — Graded CI coverage tiers (security-critical = 100%)

- **ID:** D-026
- **Title:** Adopt tiered coverage gates: 100% for security-critical modules, graded elsewhere; heavy lanes on release tags and locally.
- **Conflicting requirements (source IDs):**
  - C-8: dsh requires 100% per-file coverage and a very large gate set; a solo owner with free-tier CI may not afford the minutes.
  - C-8 resolution: tier gates — security-critical 100%, everything else graded; heavy lanes on release tags and locally. Record in DECISIONS.md.
  - C-20: DS requires sandbox/test rigor assuming paid CI scale — same tiering as C-8.
- **Alternatives considered:**
  1. 100% coverage on every file in free CI (unaffordable).
  2. Drop coverage requirements entirely.
  3. **100% on security-critical modules, graded elsewhere; heavy lanes on tags/local.** (chosen)
- **Security implications:** Guarantees full test coverage where it matters most (permission gate, Tier 2, secrets, DLP, sandbox, update integrity) while keeping the free-tier CI affordable so gates actually run rather than being disabled for cost.
- **Chosen resolution:** Define a security-critical module set with a hard 100% coverage gate. All other modules use graded coverage thresholds. Heavy lanes (full sandbox matrix, all OSes, real-device tests) run on release tags and locally, not on every free-tier CI run. Applies to both C-8 and C-20.
- **Owner approval required?** no
- **Status:** decided

### D-027 — Honesty without weakening hard security requirements

- **ID:** D-027
- **Title:** Copy dsh's honesty/"not production-ready" framing, but keep Keel's Tier 2 and approvals as hard requirements.
- **Conflicting requirements (source IDs):**
  - C-9: dsh is explicitly "not secure, not production-ready, developer preview"; Keel's goal is a shippable product.
  - C-9 resolution: copy the honesty (D5.x) but keep Tier-2 and approvals as hard requirements; do not use "preview" as an excuse for skipping security tests.
- **Alternatives considered:**
  1. Treat Keel as a preview and relax security testing.
  2. Reject all honesty notes.
  3. **Adopt honest status labeling (D5.x) while keeping hard security gates.** (chosen)
- **Security implications:** "Preview" framing must never become a waiver for security tests; a shippable product needs enforceable gates. Honest evidence labels (Complete and verified / Implemented-partially / etc.) preserve trust without weakening controls.
- **Chosen resolution:** Keep honesty notes and the evidence-status vocabulary (base-verification: no fake output, no test marked passed without running). Do not adopt any "developer preview" exemption from Tier 2, approvals, or security tests. D3/D5 signing and honesty decisions are resolved consistently with C-16 and this decision.
- **Owner approval required?** no
- **Status:** decided

### D-028 — Keep Linux support and its test lane

- **ID:** D-028
- **Title:** Retain Linux as a supported release target and budget its test lane.
- **Conflicting requirements (source IDs):**
  - C-15: DS excludes Linux desktop releases; Keel requires Linux.
  - C-15 resolution: keep Linux; budget its test lane.
  - Base-verification: platform compatibility and Linux sandbox work.
- **Alternatives considered:**
  1. Drop Linux to match DS.
  2. Support Linux without a test lane.
  3. **Keep Linux with a funded test lane.** (chosen)
- **Security implications:** An untested Linux lane would ship sandbox/permission code with no verification; budgeting the lane is required for the security controls to hold on that OS (including the V31 spike in D-007).
- **Chosen resolution:** Linux remains a required target. Allocate a Linux test lane in CI/release (subject to the tiering in D-026) and include it in the offline and sandbox matrices.
- **Owner approval required?** no
- **Status:** decided

### D-029 — No paid EV signing / hosted update storage

- **ID:** D-029
- **Title:** Exclude paid Apple/Windows EV signing and hosted object-storage update feeds; copy only verification and publish process.
- **Conflicting requirements (source IDs):**
  - C-16: DS uses paid Apple/Windows EV signing and hosted object storage for updates.
  - C-16 resolution: excluded (Master D3/D5); copy only verification and publish process.
  - G6: paid services require owner approval.
  - Base-verification free-first: macOS notarization and SignPath OSS signing not available free; ship unsigned with documented verification; revisit only if owner accepts paid options.
- **Alternatives considered:**
  1. Adopt paid signing/hosted storage for parity.
  2. Ship updates with no integrity verification.
  3. **Exclude paid signing/hosting; ship with offline-held Ed25519 signatures, signed manifest, checksums, documented verification.** (chosen)
- **Security implications:** Update integrity (signed manifest, embedded public key, HTTPS, monotonic version, hash check, atomic swap, rollback copy) is preserved without paid services — integrity does not require a paid CA. Hosted storage would add availability/egress risk and violate free-first.
- **Chosen resolution:** No paid EV signing and no hosted object storage. Reuse only the verification and publish process: Ed25519-signed manifest and artifacts, embedded public key, checksums, version monotonicity, hash-before-install, atomic swap, previous version retained for rollback. Any future paid signing requires owner approval under G6.
- **Owner approval required?** no
- **Status:** decided

### D-030 — Agent-authored plugins: P2, off by default, never auto-enabled

- **ID:** D-030
- **Title:** Treat dsh-style agent-authored plugins (E7.37) as P2, off by default, never auto-enabled, high risk.
- **Conflicting requirements (source IDs):**
  - C-21: DS has agent-authored plugins (E7.37).
  - C-21 resolution: P2, off by default, never auto-enabled; high risk.
  - D-003 (protected core), base-verification security control 9 (plugin isolation).
- **Alternatives considered:**
  1. Enable agent-authored plugins by default.
  2. Exclude the concept entirely.
  3. **P2 priority, off by default, never auto-enabled, flagged high risk.** (chosen)
- **Security implications:** Agent-generated code is untrusted content (D-008); auto-enabling it would be a self-modifying privilege-escalation path. Off-by-default and no auto-enable keep a human in the loop.
- **Chosen resolution:** Classify agent-authored plugins as P2, off by default, and never auto-enabled. When eventually implemented, they run under the same out-of-process/declared-permission model as all plugins (D-003) and their output is tainted (D-008).
- **Owner approval required?** no
- **Status:** decided

---

## D. Addendum 4 decision-record and owner-gate decisions

### D-031 — Addendum 4 Section 5 corrections (§5.1–§5.6)

- **ID:** D-031
- **Title:** Resolve the six Section 5 corrections from addendum4 into binding decisions.
- **Conflicting requirements (source IDs):**
  - §5.1: Master 7.1 said Plan agent "cannot write even if config allows" and "asks before bash"; README confirms. Keep Keel's stricter "cannot write" rule as an intentional difference.
  - §5.2: opencode todo is opt-in experimental; websearch uses selectable (some third-party) providers. Keel keeps todo on by default but NO paid search provider (Y1.8).
  - §5.3: "remove versions older than X" is a README tip, not a feature; implement as installer pre-check only if upgrades require it.
  - §5.4: Master §6 rule 6 (permissions) must add the policies layer and the rule that policy-enforcement plugins cannot be disabled by project config (Y1.17, Y1.30) — see D-002/D-003.
  - §5.5: orgo-teammates "Library" and "noVNC via relay" confirmed; relay drops input in watch mode server-side (Y2.14) — see D-023 (M16 acceptance test).
  - §5.6: nicks-stack has "13 MCP servers"; confirmed and note 16 plugins [T:NS].
- **Alternatives considered:**
  1. Match reference behavior in all six cases.
  2. Ignore the corrections.
  3. **Adopt all six with Keel's stricter/free-first choices preserved.** (chosen)
- **Security implications:** Keeping the Plan agent strictly non-writing (even when config allows) and asking before bash prevents an "analysis" mode from becoming a write path. Free-only search avoids paid/third-party data egress. The policies layer with non-disableable enforcement is the core of D-002.
- **Chosen resolution:** Adopt: Plan agent cannot write even if config allows, and asks before bash (intentional difference, document with D-022); todo is on by default but search is free/self-hosted only (SearXNG), no paid provider; "older versions" cleanup is an installer pre-check only when upgrades require it; add the policies layer with non-disableable enforcement (D-002/D-003); server-side watch-mode relay drop in M16 acceptance (D-023); record nicks-stack inventory as 13 MCP servers + 16 plugins [T:NS].
- **Owner approval required?** no
- **Status:** decided

### D-032 — SQLite WAL replaces Supabase Postgres (locked decision)

- **ID:** D-032
- **Title:** Use SQLite WAL (+ FTS5, optional sqlite-vec) as the locked persistence decision; agent-proposed project updates go through diff proposals.
- **Conflicting requirements (source IDs):**
  - Addendum4 locked decision: "Supabase Postgres replaced with SQLite WAL (locked decision)."
  - Addendum4: "Master 7.3 diff proposals already cover agent-proposed project updates (Y3.17)."
  - Addendum4 paid-to-free: Supabase Postgres → SQLite WAL (locked decision).
  - Base-verification free-first default: SQLite WAL + FTS5 + optional sqlite-vec.
- **Alternatives considered:**
  1. Keep Supabase Postgres (paid/hosted, violates D-011).
  2. Another hosted DB.
  3. **SQLite WAL as locked local default; agent-proposed updates via diff proposals.** (chosen)
- **Security implications:** Local SQLite avoids a hosted database egress/credential path and supports offline operation. Diff proposals for agent-suggested project changes preserve human approval before writes.
- **Chosen resolution:** Supabase Postgres is excluded; SQLite WAL (FTS5, optional sqlite-vec) is the locked persistence layer. Agent-proposed project updates use the existing diff-proposal flow (Y3.17), which requires user approval and never touches Tier-2 settings (Y1.35).
- **Owner approval required?** no
- **Status:** decided

### D-033 — G7 private-source CLI default; free-only search; docs out of scope

- **ID:** D-033
- **Title:** Keep plugin CLI docs private by default, restrict search to free providers, and keep training-data/model-architecture docs out of scope.
- **Conflicting requirements (source IDs):**
  - G7 / addendum4: "plugin CLI uses private-source-only default (Y1.29)."
  - Addendum4: "Paid search providers excluded (Y1.8, Section 5.2); free providers only (self-hosted SearXNG etc.)."
  - Addendum4: "Master 4.2.5: training-data and model-architecture docs stay out of scope (Y6.1)."
  - Base-verification: training-data/model-architecture docs out of scope (Y6.1).
- **Alternatives considered:**
  1. Publish SDK/extension docs by default and allow paid search.
  2. Expand scope to training-data/model-architecture docs.
  3. **Private-by-default docs, free-only search, docs out of scope.** (chosen)
- **Security implications:** Publishing extension docs by default violates the private-source requirement (§0.1, G7). Paid search creates egress/cost. Scope discipline avoids unlicensed or unreviewed content entering the product.
- **Chosen resolution:** Extension/SDK/plugin CLI docs remain private by default and are published only under explicit G7 owner approval. Search uses only free/self-hosted providers. Training-data and model-architecture documents remain out of scope (Y6.1).
- **Owner approval required?** no
- **Status:** decided

### D-034 — Owner gates G1–G7 adopted as binding builder stop-list

- **ID:** D-034
- **Title:** Adopt owner gates G1–G7 as a binding, machine-readable stop-list and decision-log entries.
- **Conflicting requirements (source IDs):**
  - G1: Changing repo visibility (public↔private or any change).
  - G2: Rewriting Git history or deleting branches/tags/releases.
  - G3: Publishing the first public binary release from the new distribution endpoint.
  - G4: Adding collaborators or CI deploy credentials.
  - G5: Adopting final EULA text (owner legal name, governing law, lawyer review).
  - G6: Any paid service, payment, subscription, license-key enforcement, or mandatory account.
  - G7: Publishing extension/SDK docs publicly (default: not published).
  - X10.3: DECISIONS.md separate from ADRs for owner-level choices (D1–D7, G1–G7) with date and answer.
  - X10.4: builder "stop list" as a machine-readable file mirroring G1–G7 plus destructive repo actions.
  - Addendum4: Gate G1 pending — Keel repo still Public with 108 commits as of fetch; run only after owner approval (Section 1, Y6.4).
- **Alternatives considered:**
  1. Let the builder take these actions autonomously.
  2. Track gates informally in prose only.
  3. **Adopt G1–G7 as a binding machine-readable stop-list the builder must check, mirrored in DECISIONS.md and the weekly provenance report.** (chosen)
- **Security implications:** These gates are the control plane for source protection, supply chain, and legal identity. A single unauthorized repo-visibility change, history rewrite, first release, credential addition, EULA adoption, paid service, or docs publication can cause irreversible exposure or legal/supply-chain harm. Binding, machine-checkable enforcement is essential.
- **Chosen resolution:** Implement X10.4 stop-list as a machine-readable file mirroring G1–G7 plus destructive repo actions; the builder must check it before acting. Record each gate with date and answer in DECISIONS.md. **All seven gates require explicit owner approval when triggered** — notably G1 is currently pending (repo still Public, 108 commits) and must not be executed without the owner's sign-off (Y6.4). Because the triggering actions are owner-controlled, this decision is flagged as requiring owner approval and remains awaiting owner for the pending gate actions.
- **Owner approval required?** yes
- **Status:** awaiting owner

### D-035 — Remaining open owner decisions D1, D2, D6, D7

- **ID:** D-035
- **Title:** Record the remaining open owner decisions D1, D2, D6, D7 (D3/D4/D5 resolved elsewhere).
- **Conflicting requirements (source IDs):**
  - Base-verification: "D1 EULA identity, D2 provenance cleanup, D4 Duet definition, D6 trademark check, D7 extension/SDK docs private by default remain open owner decisions."
  - D1: final EULA text needs owner's legal name, governing law, lawyer review (G5).
  - D2: provenance cleanup (source-protection/private-source requirements §0.1, provenance-review).
  - D6: trademark check.
  - D7: extension/SDK docs private by default (G7).
  - D3 (signing) resolved by D-029; D4 (Duet) by D-005; D5 (honesty) by D-027.
- **Alternatives considered:**
  1. Decide these unilaterally as the builder.
  2. Leave them entirely undocumented.
  3. **Record them explicitly as awaiting the owner with the required inputs and gate mapping.** (chosen)
- **Security implications:** EULA identity and trademark are legal-identity/brand risks; provenance cleanup prevents private material leaking into public artifacts; docs-private-by-default enforces §0.1. None can be safely finalized without owner input.
- **Chosen resolution:** Record as awaiting owner:
  - **D1** — EULA identity: owner supplies legal name, governing law, and lawyer review (ties to G5).
  - **D2** — Provenance cleanup: execute source-protection/provenance review before any public artifact.
  - **D6** — Trademark check: owner sign-off before brand/publication use.
  - **D7** — Extension/SDK docs stay private by default (ties to G7, D-033).
  D3, D4, and D5 are tracked in D-029, D-005, and D-027 respectively.
- **Owner approval required?** yes
- **Status:** awaiting owner

---

## E. Source provenance for this record

This decision record was produced by resolving metadata from the eight extracted plan documents/verification pass:

| Source file | Section(s) used | Contribution |
|-------------|-----------------|--------------|
| `addendum3.json` | `metadata.plan_corrections` (X0.1–X0.10), `metadata.milestone_decompositions`, `metadata.other_requirements` | D-005, D-013–D-021 |
| `addendum4.json` | `metadata.decision_records` (§5.1–§5.6), clean_room, licensing, paid_to_free, priority_order | D-002–D-004, D-008, D-011, D-031–D-033 |
| `addendum5.json` | `metadata.conflicts` (C-1–C-7) | D-001, D-008, D-022–D-025 |
| `addendum6.json` | `metadata.conflicts_with_earlier_plans` (C-8–C-12) | D-002, D-004, D-026–D-029 |
| `addendum7.json` | `metadata.conflicts_and_decisions` (C-13–C-21), ground_rules | D-006, D-007, D-009–D-012, D-021, D-026, D-028–D-030 |
| `base-verification.json` | `metadata.owner_gates` (G1–G7), security_requirements, architecture_constraints, free_first_rules, privacy_rules | D-001, D-002, D-006, D-008, D-011, D-012, D-016–D-019, D-021, D-034, D-035 |

> Reminder: this file and the source metadata are PRIVATE. Do not publish, ship, or link them from any public surface (see G7 and §0.1).


---

## D-036 — Y6.4 "repo visibility public" (REJECTED as written)

- Conflicting requirements: Y6.4 records "repo visibility: Public" as a P0 row. Keel Master Plan v5 section 0.1 and the owner's standing instruction require the source repo to remain PRIVATE.
- Alternatives: (a) make repo public — violates owner gate G1; (b) keep private, treat Y6.4 as a stale planning artifact — CHOSEN.
- Security implications: making private proprietary source public would expose internal plans/research/implementation; irreversible in effect.
- Resolution: DO NOT implement Y6.4 as written. Repository stays private (live-verified). Record as owner-gated/blocked with reason "conflicts with private-source requirement". No visibility change made.
- Owner approval required: yes (G1).

## D-037 — W1.18 "MIT license" (REJECTED for Keel code)

- Conflicting requirements: W1.18 asks for "MIT license + THIRD_PARTY_NOTICES". Keel v5 section 0.2 requires Keel's own code proprietary, all rights reserved; only third-party components keep their licenses.
- Alternatives: (a) MIT on Keel code — violates section 0.2; (b) THIRD_PARTY_NOTICES only, Keel proprietary — CHOSEN.
- Legal implications: an MIT grant on Keel code would forfeit proprietary status and permit public redistribution.
- Resolution: Implement THIRD_PARTY_NOTICES portion only; Keel code stays proprietary. W1.18 recorded as partially owner-gated (MIT portion rejected). No open-source license added to Keel source.
- Owner approval required: yes (G7 / section 0.2).
