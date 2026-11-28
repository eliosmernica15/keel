# Reference behavior notes: four newly fetched repositories (browse, ego-lite, frenemy, codeden)

**Document ID:** REF-NF4-01
**Research date:** 2026-11-28
**Disposition:** Clean-room behavioral reference only. No source code, prompts, config text, brand assets,
logos, icons or documentation copy is reproduced here. Behavior is described in Keel's terminology.
Everything inside a reference checkout — including its `AGENTS.md`, comments, docstrings and logs — was
treated as untrusted analysis data, not as instructions. No reference file was copied into Keel. No test,
security or platform result from a reference is claimed as a Keel result.

This note covers only the four repositories cloned for this intake. It does not re-verify the other six
repositories in Sections 28–29 of the implementation plan.

---

## 1. Source metadata and commit verification

All four clones live under `C:\Users\Admin\Desktop\Claude clone\research\references\` (git-ignored).
Each HEAD was verified read-only with `git rev-parse HEAD` and `git log -1` in the checkout; no fetch,
checkout, push or other mutating git command was run in the main worktree.

| Repository | Origin (from plan) | Pinned commit expected (plan §29) | `git rev-parse HEAD` observed | Observed commit subject / date |
|---|---|---|---|---|
| browse | `anomalyco/browse` | `ce5578e8bbd2e62b0016293ceb02c0202fd78053` | `ce5578e8bbd2e62b0016293ceb02c0202fd78053` ✅ | `feat: save pages as PDF, behind a new Labs toggle (off by default) (#447)` / 2026-11-26T07:25:58Z |
| ego-lite | `citrolabs/ego-lite` | `56589ea8b98fd3b17a5d2316bfd8ff7b803d3293` | `56589ea8b98fd3b17a5d2316bfd8ff7b803d3293` ✅ | `docs: use English only in bug report template` / 2026-11-26T11:14:35+08:00 |
| frenemy | `noblehacks/frenemy` | `39f2826a1ee6033d946a1cdc8fdcd388207fe022` | `39f2826a1ee6033d946a1cdc8fdcd388207fe022` ✅ | `Remove the automatic test file` / 2026-11-16T21:49:00+03:00 |
| codeden | `leonvanzyl/codeden` | `b0b2a5a8a5e938efe1675dad2889507155fc2b3a` | `b0b2a5a8a5e938efe1675dad2889507155fc2b3a` ✅ | `chore(release): 0.7.10` / 2026-11-25T13:51:25Z |

**All four pins match.** A future transplant must still resolve each candidate file's blob SHA and re-check
notices at the exact pinned commit (plan §29/§30 Batch 0); a matching HEAD alone is not a license review.

Plan sections consulted: §28.2 D (frenemy), §28.2 E (browse), §28.2 C (codeden), §28.3 F (ego-lite),
§28.4/§28.5 (architecture decisions and non-adoption), §29 (pins), §30 (reuse batches 1–3). No new
feature ID is asserted here: where the plan's addenda use IDs (W/E/D/V), those are source-map references,
not Keel `PLAN-INDEX.json` IDs. This note maps to plan sections and batches instead.

---

## 2. Browse — browser MCP, structured snapshots, human handoff

### 2.1 License, notices and provenance

* Root `LICENSE` only: **MIT, Copyright (c) 2025 opencode**. `package.json` declares `license: MIT`.
* A recursive scan of the checkout for `LICENSE*`, `NOTICE*`, `*NOTICES*` and `COPYING*` (excluding
  `.git` and dependencies) found **no nested license or notice file**. That does **not** clear vendored
  dependencies, generated assets, extension store assets or transitive packages for reuse; each candidate
  blob still needs its own notice review before any copy.
* Asset directories (`assets/`, `public/`, `store/`) contain branding and screenshots — excluded from
  any Keel reuse.

### 2.2 Files inspected (exact paths, relative to checkout root)

`README.md`; `package.json`; `LICENSE`; `cli/src/mcp.ts`; `cli/src/mcp/registry.ts`;
`cli/src/session-manager.ts`; `cli/src/session-manager/admission.ts`;
`cli/src/snapshot/aria-snapshot.ts`; `cli/src/auth/domain-policy.ts`.
Directory inventory also taken of `cli/src/mcp/`, `cli/src/snapshot/`, `cli/src/session-manager/`,
`cli/src/relay/`, `cli/src/setup/`, `src/background/` and `rust/crates/`.

Note an important correction to a naive reading of the plan: the README states `cli/` is the *earlier
TypeScript implementation kept as a reference*; the current implementation is the Rust workspace under
`rust/` (`rust/crates/browse/src/mcp.rs`, `relay.rs`, `serve.rs`, `session.rs`, `setup.rs` among others).
The plan's concrete paths point at the TypeScript reference code, which is still readable behavior
evidence but is **not** the shipping path at this commit.

### 2.3 Dependency / platform requirements

* Root `package.json`: private package, ESM, Bun `1.4.4` as package manager; dev deps include Vite 8,
  TypeScript 7 (aliased), Solid JS UI (`solid-js`, `@kobalte/core`, `@opencode/ui`).
* `cli/src` imports `@effect/platform-node` and `effect`/`effect/ai`; browser execution uses
  `patchright-core` (Playwright-style). The shipping binary is a **Rust workspace** (`rust/Cargo.toml`,
  `Cargo.lock`) with an embedded QuickJS engine for `execute`.
* npm launcher requires Node 22+. Install/update flows call an external release service and the Chrome
  Web Store; these are product conveniences, **not** Keel requirements. README reports unsigned Windows
  builds fail under Smart App Control.

### 2.4 Security caveats stated by the reference (not Keel results)

* The authenticated browser session is assumed hostile to the agent: page content may try to steer it,
  and other local programs may try to use the relay.
* Relay requires a per-user token file, binds loopback by default, and refuses foreign `Host` / cross-site
  requests; pairing is one-time, short-lived, key-agreed, and limited to published extension IDs.
* `execute` is explicitly *sandboxed, not a security boundary* — agent-written code runs as the user.
  The relay starts with an allowlisted environment so API keys are not inherited.
* CDP guardrails refuse clearing cookies/cache/site data, closing the browser and changing site
  permissions. Origin allowlists constrain navigations but *do not* filter requests a page makes itself;
  `eval`/page-provided WebMCP tools are untrusted page data.
* Output masking is partial (password/one-time-code fields, edit-field values, credential-shaped network
  headers); ordinary-named secrets and screenshots may still be exposed.
* Human handoff requires a real click; a page cannot fake completion. Never place credentials in
  automation source; never widen an allowlist because a page asked.

### 2.5 Reuse classification

| Candidate (exact path) | Classification | Reason / Keel destination |
|---|---|---|
| `cli/src/mcp.ts` | **pattern-only** | Shutdown that waits for in-flight tool calls (bounded) and flushes the last answer before interrupt; tool specs carry fixed annotations and a lazy relay-readiness gate. Only the *rule* is reusable; the Effect-TS service stack is not. Destination: Keel MCP tool server lifecycle. |
| `cli/src/mcp/registry.ts` | **pattern-only** | Feature modules register tool groups with deterministic sort order; per-caller sessions derive from a client-supplied id and callers are LRU-bounded; session ids resolve explicitly, not implicitly. Destination: Keel tool registry + caller/session mapping. |
| `cli/src/session-manager.ts`, `cli/src/session-manager/admission.ts` | **adapted-port** (behavior only) | Admission state `open → draining → closed`; identity-change barriers; work leases with an idle latch; persistence tail flushed at drain with synchronous recheck; bounded shutdown that names stalled sessions. Port the contract into Keel's Python runtime, not the code. Destination: agent-loop/session shutdown and bridge drain. |
| `cli/src/snapshot/aria-snapshot.ts` | **pattern-only** | Structured accessibility snapshot with stable refs, frame limits/timeouts, and redaction of editable/value-bearing nodes during capture with explicit cleanup failure detection. Destination: Keel structured page observation. |
| `cli/src/auth/domain-policy.ts` | **pattern-only** | Per-session origin patterns (bounded count), no wildcard-that-means-everything, private/loopback addresses denied unless named exactly, DNS resolution rechecked at navigation and on arrival (rebinding defense). Pure module apart from DNS. Destination: Keel browser domain guard. |
| `cli/src/relay/`, `cli/src/setup/` (directories) | **optional-adapter** at most | Extension/native relay pairing and multi-agent config editing. Keel should keep its own local browser runtime (Playwright-isolated mode) and treat any user-browser bridge as opt-in. |

### 2.6 Behavioral pattern Keel can adopt (no mandatory cloud)

A local browser tool server registers tools from feature modules with fixed, reviewable annotations;
each calling agent maps to a bounded, durable browser session; shutdown stops admitting work, waits a
bounded time for already-accepted calls, flushes their answers, and reports what it dropped; pages are
observed as structured snapshots with stable refs, and navigation is limited by a per-session origin
allowlist that rejects private addresses and re-checks resolution. Login/2FA/payment steps require a
human handoff that only a real user click completes. All of this runs against a loopback relay or an
isolated local browser — no hosted service, account or extension is required for core operation.

---

## 3. Ego Lite — versioned browser skill and multi-host plugin packaging

### 3.1 License, notices and provenance

* Root `LICENSE`: **MIT, Copyright (c) 2026 CitroLabs**.
* Nested `plugins/ego/LICENSE`: **MIT, Copyright (c) 2026 CitroLabs** (same holder).
* No `NOTICE`/`THIRD_PARTY_NOTICES.md` found in the checkout.
* Brand assets (`docs/assets/`, `skills/ego-browser/assets/`) and per-site `learnings/` content are
  excluded from reuse; the README's benchmark graphic and store badges are third-party/product assets.

### 3.2 Files inspected (exact paths)

`README.md`; `LICENSE`; `plugins/ego/LICENSE`; `skills/ego-browser/SKILL.md`;
`plugins/ego/index.js`; `plugins/ego/README.md`.
Directory inventory also taken of `skills/ego-browser/` (including `references/`, `scripts/`,
`learnings/`), `plugins/ego/` and `plugins/scripts/`.

### 3.3 Dependency / platform requirements

* The repository is the **open harness and skill package, not the browser**. Its own `AGENTS.md` states
  the `ego lite` app is closed source and ships its own `ego-browser` binary; the runtime harness sits
  under `package/ego-browser/src/` and depends on `globalThis.ego` bindings provided by that app.
* Node 22+, ESM. Packaging requires Node/npm plus `zip` and `unzip`.
* README at this commit: macOS and Windows only; Linux on the roadmap. Keel must not inherit that
  platform matrix, and must not assume a portable browser engine exists here.
* Ten host distributions (Claude Code, Codex, Cursor, Copilot, Grok Build, WorkBuddy, QwenWork,
  OpenCode, DeepSeek Harness, Pi) are packaging targets, not runtime dependencies for Keel.

### 3.4 Security caveats stated by the reference

* README says browsing data, cookies and browser state stay on the device, with deliberately narrow
  product telemetry; first launch offers to migrate existing Chrome data (cookies/extensions/logins) —
  an opt-in action with broad reach.
* The entry skill explicitly instructs the agent to re-read the version-matched usage guide after an
  upgrade, and to read a dedicated reference *before* clearing cookies/cache/storage because some
  clears reach the whole browser profile.
* The packaging guide states its checks do **not** establish end-to-end compatibility in all ten hosts;
  it is a payload/manifest verification, not a certification.

### 3.5 Reuse classification

| Candidate (exact path) | Classification | Reason / Keel destination |
|---|---|---|
| `skills/ego-browser/SKILL.md` | **adapted-port** (data/contract, not text) | A *thin, versioned* entry skill whose only durable instruction is to fetch the runtime-matched guide and re-read it after upgrade, with links to install/clearing references. Keel should implement the versioned-skill bootstrap pattern with its own content, not copy the skill text. Destination: Keel skill seam / versioned skill authoring. |
| `plugins/ego/index.js` | **pattern-only** | One default export serves two incompatible host plugin APIs: one adds a skills directory to configured paths, the other adds a single skill through a transform that lets a user-installed skill win. Additive, non-clobbering registration. Destination: Keel plugin/skill compatibility adapters. |
| `plugins/ego/README.md`, `plugins/scripts/` (directory) | **pattern-only** | One canonical skill fanned out to many host artifacts, with a commit-hook sync of a checked-in copy, index-based equality checks, and failed-batch handling that leaves prior artifacts intact. Destination: Keel packaging/docs validation pattern. |
| `skills/ego-browser/learnings/`, `skills/ego-browser/assets/` | **rejected** for reuse | Site-specific scripts and brand marks; third-party/site data, not portable Keel capability. |
| Closed-source browser engine (not present as portable source) | **rejected** | Cannot be inspected or transplanted; plan §28.5 non-adoption list applies. |

### 3.6 Behavioral pattern Keel can adopt (no mandatory cloud)

Keep one canonical, versioned skill body; make the published entry point small and instruct the agent to
obtain the guide matching the *installed* runtime and to re-read it after upgrade. Register skills
additively so an existing user skill wins, and generate per-host bundles from the single canonical source
with equality checks that fail when the copy drifts. Keel keeps its own local browser runtime; no host
marketplace, browser download service or closed-source engine is required for core behavior.

---

## 4. Frenemy — worker staging, exact-file ownership, process guards, install safety

### 4.1 License, notices and provenance

* Root `LICENSE`: **MIT, Copyright (c) 2026 Zakariya Syed** (with public profile links in the notice).
* Nested `snitch/extension/LICENSE`: same MIT text and same holder.
* `THIRD-PARTY-NOTICES.md` present: states Claude/Codex/OpenAI/Google/Kimi/VS Code are third-party
  products named only for identification; provider software is not bundled; the bridge/extension use
  the Node standard library and VS Code extension API with no bundled npm runtime deps; small brand
  marks and app logos remain their owners' property.
* `snitch/`, `images/` and brand marks excluded from reuse.

### 4.2 Files inspected (exact paths)

`LICENSE`; `THIRD-PARTY-NOTICES.md`; `notes/WORKER-SAFEGUARDS.md`; `RELEASE-STATUS.md`;
`INSTALL.md`; `tools/worker-workspace.mjs`; `tools/worker-guard.mjs`;
`tools/ask-codex-mcp.mjs`; `tools/relay-core.mjs`; `tools/wrapper-common.mjs`.

### 4.3 Dependency / platform requirements

* Node.js 18+ at install, Node alone at run time; **no Python, no shell scripts at run time, no WSL**.
  Release notes record Node 22.17.0 on the author's Mac.
* Requires at least two of four provider CLIs installed and signed in; VS Code only for the optional
  panel. Windows/macOS/Linux installers present.
* Node built-in modules only for the guard/relay/wrapper code; an advisory shared directory lock from
  the extension library is imported by the staging tool.

### 4.4 Security caveats stated by the reference

* **The safeguards document and the staging tool both say explicitly that the lock is advisory and the
  protections are cooperative conflict prevention, not an OS sandbox against same-user processes.**
  Keel must not treat this as an isolation boundary.
* Every write tool requires an absolute working directory and an exact relative allowed-file list;
  overlapping claims (including a file versus a path below it) are rejected; the worker never applies
  its own job.
* Apply validates the *whole staged tree* against its baseline (out-of-scope edits/deletes/permission
  changes reject) and checks *only owned originals* against their baselines (stale-source refusal), so
  unrelated legitimate merges elsewhere do not block a job. Symlinks are rejected; originals are backed
  up before replacement; an interrupted apply holds the project until explicit recovery.
* A seat may be handed off only after its old worker is confirmed stopped; time alone never releases
  ownership. Watchdogs are bounded (wrapper minutes, relay backstop slightly longer); a zero watchdog
  disables the wrapper's own timer but not provider ceilings.
* Consult lanes are read-only and their model output is explicitly treated as data that may be wrong,
  never as instructions.
* `RELEASE-STATUS.md` (2026-11-16) says real AI apps were exercised only on the author's Mac; Windows
  and Linux CI used stand-in apps. It says the release is not certified for production, includes no
  account credentials or machine configuration, and lists items not re-tested. Keel must independently
  validate real harness CLI integrations per supported OS.

### 4.5 Reuse classification

| Candidate (exact path) | Classification | Reason / Keel destination |
|---|---|---|
| `tools/worker-workspace.mjs` | **adapted-port** (non-Git fallback) | Non-Git staging copy excluding VCS/dependency/state dirs without following symlinks; exact relative-path ownership with hashes and permission bits; validate-everything-before-write; backups, per-file atomic replace, journal, rollback and interrupted-state recovery. Keel should prefer worktrees for Git projects and port this *contract* as the non-Git fallback. |
| `tools/worker-guard.mjs`, `notes/WORKER-SAFEGUARDS.md` | **pattern-only** | Mandatory scope on every write tool, driver-owned apply/recovery, and "old worker confirmed stopped" handoff. Keel worker/fleet handoff contract plus adversarial tests. |
| `tools/relay-core.mjs`, `tools/platform.mjs` | **pattern-only** | Terminate a process snapshot/ownership tree with SIGTERM then bounded SIGKILL escalation; never signal guessed identities when a snapshot is unavailable; bounded relays and a backstop. Keel process supervisor edge cases. |
| `tools/wrapper-common.mjs` | **pattern-only** | Prompt/output caps, watchdog, process-group stop on Unix / tree stop on Windows, and scratch files preserved or moved aside on every exit path. Keel CLI wrapper design. |
| `tools/ask-codex-mcp.mjs` | **pattern-only** | Separated read-only consult lane and authorized write lane; external model reply framed as untrusted data. Keel's consult-vs-worker tool split. |
| `INSTALL.md` | **pattern-only** | Back up a settings file before modification, add/refresh only own entries, read back and verify, restore on partial failure, refuse files that cannot be read with certainty, repeatable install. Keel setup acceptance criteria. |
| Advisory lock as a sandbox | **rejected** | Explicitly not an isolation boundary; plan §28.5 non-adoption list. |

### 4.6 Behavioral pattern Keel can adopt (no mandatory cloud)

For a non-Git project, claim exact relative files, copy all project context into a private staging area
without following symlinks, record hashes and permission bits, and let the worker edit only the copy.
The driver reviews and applies: validate the entire staged tree and the owned originals *before* any
write, reject out-of-scope and stale changes, back up originals, replace atomically, journal, and roll
back on ordinary failure. An interrupted apply blocks further work until explicit recovery, and a
replacement worker is admitted only after the old process is confirmed stopped. No lock or service is
treated as a security boundary; Keel backs it with its own OS-level sandbox/permissions.

---

## 5. CodeDen — provider adapters, approval broker, local runner/session host, worktrees

### 5.1 License, notices and provenance

* Root `LICENSE`: **MIT, Copyright (c) 2026 Leon van Zyl**.
* Nested `apps/cli/LICENSE`: same MIT text and same holder.
* No root `THIRD_PARTY_NOTICES.md`. There is a generator script `apps/cli/scripts/third-party-notices.mjs`
  and source files whose names include "notices" (e.g. `apps/server/src/services/orchestration/notices.ts`,
  `packages/providers/src/claude/notices.ts`) — these are product features, **not** a blanket license
  clearance. Vendored/generated assets and transitive dependencies still require file-level review.
* `SECURITY.md` and `docs/security.md` describe in-scope/out-of-scope vulnerability reporting; do not
  mistake them for an audit certification.

### 5.2 Files inspected (exact paths)

`LICENSE`; `apps/cli/LICENSE`; `SECURITY.md`; `README.md`; `docs/security.md`; `package.json`;
`packages/providers/src/adapter.ts`; `packages/providers/src/registry.ts`;
`packages/providers/src/approvals.ts`; `apps/runner/src/runner.ts`;
`apps/runner/src/session-host.ts`; `apps/runner/src/workspace/worktree.ts`;
`apps/server/src/security.ts`.
Directory inventory also taken of `packages/providers/src/` (including per-provider adapter and policy
modules) and `apps/runner/src/` (including `workspace/`, `process/`, `browser/`, `git/`).

### 5.3 Dependency / platform requirements

* Monorepo `package.json`: **Node >=24**, pnpm `10.12.1`; plain strict TypeScript ESM (explicitly no
  Effect), Biome, Vitest.
* Stack from its own guide and imports: Hono + `@hono/node-server` + `ws` for the runner/server,
  Drizzle + SQLite for the event log/projections, React 19 + Vite + Tailwind + shadcn for the web UI,
  Electron + electron-builder for desktop, Chromium driven over a private pipe by the runner.
* The provider package includes generated protocol modules for one provider's v2 wire format; those are
  generated code and are not reuse candidates.
* Local folders work without external accounts; GitHub is required only for issues, pull requests and
  the factory features (README). Those factory/dark-factory modes are labeled experimental.

### 5.4 Security caveats stated by the reference

* Default server and runner bind `127.0.0.1` only; a random 256-bit install token is required on every
  HTTP/WebSocket/MCP request and compared in constant time; the token is exchanged for an HttpOnly,
  SameSite cookie; `Host` must be loopback and `Origin`, when present, must be the product's own —
  explicit DNS-rebinding and cross-origin defenses.
* Network access is opt-in with a password, salted hash, throttled sign-in and remote-session tokens;
  `/mcp`, the runner and its browser relay are never remotely reachable. Forwarding headers are never
  trusted for access decisions; a proxied request is always treated as remote.
* Agent-visible Markdown/images are untrusted: remote images are held until an explicit user click,
  fetched once through a single-use id, restricted to public addresses with redirects re-checked, and
  served under a strict CSP. Links are shown before opening.
* Per-session MCP tokens are role-scoped, hashed at rest and revoked on session end; tokens are not
  accepted on the wrong surface, don't go on command lines, and are never logged into transcripts.
  Agent environments strip the product's own internal variables.
* Permission levels map to provider-native enforcement; the orchestrator and PMs are read-only; agent
  allow-list files are guarded at every level. Factory/dark-factory automation is experimental and the
  README advises a test repository, a budget, trusted authors, limited areas and a stop button.
* `SECURITY.md` scope notes out-of-scope items: what an agent does with granted permissions, upstream
  CLI vulnerabilities, and already-compromised accounts. These are statements about the reference, not
  guarantees for Keel.

### 5.5 Reuse classification

| Candidate (exact path) | Classification | Reason / Keel destination |
|---|---|---|
| `packages/providers/src/adapter.ts` | **adapted-port** (primary contract reference) | One adapter instance per provider opens many sessions; `detect()` reports install/login problems without throwing; capability flags must be honest; model lists can refresh with a max-age guard and keep a last-good list on failure; optional capabilities are present exactly when advertised; fork copies a conversation (including a fork point) and refuses rather than silently opening without history; errors classify refused opens so new work is not retried. Destination: Keel provider/agent seam. |
| `packages/providers/src/registry.ts` | **adapted-port** (direct-reuse candidate after contract adaptation) | Duplicate-safe registration keyed by id, model refresh that never throws and skips recent lists, change listeners notified independently so one failure cannot starve others. Destination: Keel provider registry. |
| `packages/providers/src/approvals.ts` | **direct-reuse candidate** after adapting Keel's event/data contracts | Pending approvals/questions keyed by request id; invalid answers reject and leave the request pending; abort resolves to cancel; declined answers are distinguished; policy-decided approvals are recorded without waiting; cancel-all on stop. Destination: Keel approval seam. |
| `apps/runner/src/runner.ts`, `apps/runner/src/session-host.ts` | **pattern-only** (primary execution-plane reference) | Runner is a separable local process on loopback with a lock file carrying port/token/pid, a durable event journal, a delta batcher that preserves order, single-instance takeover detection, and bounded drain/close. Session host runs many long-lived provider sessions concurrently, refuses a second open of the same session, journals normalized events, writes turn checkpoints for Git worktrees, and treats missing cwd as a typed failure. Destination: Keel local execution plane / bridge. |
| `apps/runner/src/workspace/worktree.ts` | **adapted-port** (Git session isolation) | One worktree per session on a unique branch, base refresh with offline fallback (a local branch ahead of origin is preserved as the user's work), orphan cleanup that stops processes first, and fork worktree restoration that rolls back the worktree/branch on failure. Destination: Keel Git worktree seam. |
| `apps/server/src/security.ts` | **pattern-only** | Loopback-first listener, install token, Host/Origin allowlists, proxy headers never used for access decisions, remote paths explicitly excluded. Destination: Keel loopback web bridge / optional remote adapter boundary. |
| `packages/providers/src/codex/protocol/v2/`, factory/dark-factory automation | **rejected** for reuse | Generated wire-format types and experimental automation with external service coupling; see plan §28.5. |

### 5.6 Behavioral pattern Keel can adopt (no mandatory cloud)

Expose one normalized provider contract covering both direct model APIs and locally installed agent CLIs,
with honest capability flags, non-throwing detection, last-good model lists, and typed refused opens.
Keep long-lived sessions in a separable local execution process that journals normalized events, refuses
duplicate opens and writes per-turn checkpoints inside a worktree per session. Route every approval
through one broker where invalid answers stay pending, abort cancels, and policy decisions are recorded
without waiting. Bind local services to loopback behind a per-install token with Host/Origin checks.
Nothing in this pattern requires GitHub, a cloud VM or an account; those remain opt-in adapters.

---

## 6. Highest-value patterns for Keel (top 3)

1. **In-flight-work drain with identity barriers and bounded shutdown** (browse `session-manager.ts` +
   `admission.ts`; codeden runner) — Keel's agent loop and bridge can stop admitting work, let accepted
   calls settle, flush their answers and *name* anything dropped, instead of losing work at a session or
   relay boundary.
2. **Driver-owned exact-file staging with validate-before-write, backups and interruption recovery**
   (frenemy `worker-workspace.mjs` + safeguard contract), paired with **worktree-per-session checkpoints**
   (codeden `workspace/worktree.ts`) — gives Keel a safe parallel-edit story for both Git and non-Git
   projects with an explicit trust boundary between worker output and project state.
3. **One honest provider adapter + registry + approval broker, behind a loopback/token service boundary**
   (codeden `adapter.ts`, `registry.ts`, `approvals.ts`, `security.ts`) — unifies local CLIs and API
   providers, keeps invented capabilities and leaked credentials out of the core, and stays local-first
   with no mandatory hosted service.

Pattern-only observations worth a later ADR but not in the top three: structured page snapshots with
redaction plus a real human handoff for sensitive actions (browse), and a thin versioned skill that
re-reads a runtime-matched guide with additive, non-clobbering host registration (ego-lite).

---

## 7. Exclusions and status

* No source files, prompts, error strings, config text, schemas, UI copy, logos or icons were copied into
  Keel from any of these repositories.
* No upstream test result, benchmark, security claim or platform-support claim is adopted as Keel's; Keel
  verification requires its own tests and real-runtime checks.
* This document is a behavior spec only. Its presence is **not** evidence that any Keel feature is
  implemented or verified. Reuse remains unapproved until a source-provenance record, pinned blob SHAs,
  license review, Keel-native contract tests and security review pass (plan §1 rules 12–15, §30 Batch 0).
