# Keel Plan v5 Addendum 6: DeepSeek Harness Full Teardown (Architecture, Packages, UI/UX, Builder Rules, CI)

Adds only items **not already in** Master Plan and Addenda 1 to 5. Free-only. Milestones follow v5. Every row names its source. IDs: `D*` = derived from the DeepSeek Harness, `V*` = own ideas (builder protocol in Section 9).

## 0. Source keys and rules

| Tag | Meaning |
| --- | --- |
| `[T:key]` | Read this session (21 Nov 2026) in that file. Behavior is reimplemented clean-room in Python (X0.10). Never copy code, names, icons or prompts. |
| `[S]` | My suggestion, no repo behind it. |

DeepSeek Harness (`dsh`) keys, all under `github.com/deepseek-ai/deepseek-harness` (MIT, 273k stars, "everything is a plugin"):
- **DS-ARCH** `docs/architecture.md` · **DS-AGENTS** `AGENTS.md` · **DS-DEV** `docs/development.md` · **DS-SAFETY** `SAFETY.md` · **DS-GUIDE** `docs/user/guide/index.md` · **DS-BENCH** `BENCHMARK.md` · **DS-README** README/tree (Addendum 5).

**Important adaptation rule:** dsh is TypeScript on a framework called Cordis (Node ≥ 24.9, pnpm). Keel is **Python daemon + Electron renderer**. Nothing in dsh's stack is adopted; only behaviors and design rules.

## 1. Read status

**Read in full this pass:** DS-ARCH, DS-AGENTS, DS-DEV, DS-SAFETY, DS-GUIDE, DS-BENCH.
**Blocked this pass:** the GitHub `packages/` and `apps/` directory pages (robots block). The package map below comes from DS-AGENTS's own layout table, so it is accurate for names and one-line purposes, but **`apps/*` contents and each package's README are unread**.

**M0 reading list (DeepSeek):** `docs/cordis-primer.md`, `docs/subsystems/*` (session, tools, scope, core, llm-streaming, system-prompt, subagent, agent-team, conversation, working-directory), `docs/capability-seams.md`, `docs/tool-execution-pipeline.md`, `docs/agent-lifecycle.md`, `docs/event-producer-consumer.md`, `docs/cookbook/*` (adding a package, tool, LLM adapter, settings card; extension cookbook; reviewing persistence type changes), `docs/defensive-patterns/README.md`, `docs/testing.md`, `docs/config-catalog.md`, `docs/session-format-status.md`, `docs/user/guide/providers.md`, `python-sdk.md`, `docs/user/develop/basic/index.md`, `apps/cli/README.md`, `apps/desktop/README.md` and `packaging/`, `apps/web/tests/*`, `benchmarks/AGENTS.md`, `snapshots/AGENTS.md`, `vendor/README.md`, `packages/README.md`, `.agents/skills/*` (especially `dsh-client-ui-ux`, `dsh-error-handling`, `dsh-pre-push-checks`, `dsh-create-upgrade-guide`, `dsh-session-projection`, `dsh-pr-description`, `dsh-prose-standard`), `.agents/notes/implemented/*`, `scripts/run-gates.ts`.

## 2. Architecture and runtime model

| ID | Feature | Source | Keel implementation (Python) | M | Pri |
| --- | --- | --- | --- | --- | --- |
| D1.1 | **Every part is a plugin, including model adapter, tool registry, session log and the agent loop itself**, each replaceable from configuration; "no privileged core to patch." | T:DS-ARCH | Keel core services (providers, tools, sessions, loop, memory, scheduler) register through the same plugin API (builds on W1.1/V1). **Exception:** Tier 2 safety services are plugins that **cannot be replaced or disabled** by profiles/patches. | M10 | P0 |
| D1.2 | **Registrations are reversible effects** that unwind when their plugin unloads. | T:DS-ARCH, T:DS-AGENTS | Required by V1: every `register()` returns a disposer attached to the scope. Add a leak detector test. | M10 | P0 |
| D1.3 | **Profiles and bundles:** a *profile* is a named composition (list of bundles, out-of-tree plugins, a user patch file); shipped templates `web`, `headless`, `sdk`, `sdk-minimal`, `acp`; a *bundle* is a distributable set of config rows + code. | T:DS-ARCH | `keel --profile web|headless|sdk|acp|desktop|minimal`; profiles live in the Keel home dir; bundles are signed packs (C8.5). | M10, M20 | P0 |
| D1.4 | **Layered composition order:** bundles in order, then profile patch, then home patch, then `--patch` overlays; a patch targets a row **by id** (replace whole config) or inserts new rows; a `preset` patch edits inside a declaration's plugin list. | T:DS-ARCH | Same layering for Keel config rows; `keel --patch file.yml`; every row has a stable id. | M2, M10 | P0 |
| D1.5 | **`--dump-config`:** prints the exact plugin tree the machine will boot; any printed row can be replaced by a patch. | T:DS-ARCH | `keel --profile web --dump-config` and a UI view "What is running"; ties into layered config viewer (X6.8). | M2, M19 | P0 |
| D1.6 | **Config-only HMR plugin** toggled per profile (on for web, off for headless/sdk/acp). | T:DS-ARCH | Hot-reload plugin enabled only for the interactive profiles. | M10 | P1 |
| D1.7 | **All supported apps launch only through named profiles;** package bins, demos and SDK argv escapes are forbidden, and a gate (`verify-application-entrypoints`) classifies every executable and rejects bypasses. | T:DS-ARCH, T:DS-AGENTS | One launcher; CI gate that scans `pyproject`/package.json scripts and fails if an entrypoint bypasses `keel --profile`. | M0, M25 | P1 |
| D1.8 | **SDK runtime wheel per platform** bundles the normal CLI; the client launches `--profile sdk` with an explicit home dir; minimal example uses `sdk-minimal`; persistent external plugins installed through the plugin command, not a private config carrier. | T:DS-ARCH | Python SDK ships a bundled-runtime wheel per OS/arch (verify license/size); client always passes an explicit data dir. | M20, M22 | P1 |
| D1.9 | **Plugin management command** reserved as `plugin` (not a profile name unless `--profile plugin`). | T:DS-ARCH | `keel plugin ...` reserved word. | M10 | P2 |
| D1.10 | **Desktop shell:** Electron ships the exact production runtime in **signed resources**, owns a reserved `desktop` profile, starts a **private Desktop Host** (Electron-as-Node), loads **packaged web assets immediately** and waits for **boot injections** before activating client plugins in the same document; **OS-assigned port**; Node IPC carries boot injections, readiness, fatal errors, shutdown; desktop and CLI **share product data but keep packages, activation and lockfiles separate**. | T:DS-ARCH | Keel: Electron main starts the Python daemon (PyInstaller/Nuitka) with an OS-assigned loopback port + per-launch token; renderer shows a splash from packaged assets and waits for a `ready` message; CLI and desktop share the data dir but separate plugin installs; structured fatal-error screen. | M19, M22 | P0 |
| D1.11 | **Shell-owned UI runs plugin install/update transactions** with the bundled package manager under normal user/profile config. | T:DS-ARCH | Plugin Manager UI runs pip/venv installs in an isolated per-profile environment with a visible transaction log and rollback. | M10, M19 | P1 |
| D1.12 | **Core package map** (session log, system-prompt assembly, tool registry + guarded pipeline, agent interface + live registry, agent loop driver, per-agent scope primitive, LLM vocabulary + adapter seam) each exposing one service key on the context. | T:DS-ARCH | Keel service registry keys: `sessions`, `system_prompt`, `tools`, `agents`, `agent_loop`, `llm`. | M7 | P0 |

## 3. Events, turn flow and the session log

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| D2.1 | **Three event domains:** *session events* (durable facts in the log, broadcast), *agent events* (`agent/*`, live, observe/intercept in-flight work), *capability events* (`fs/*`, `tools/*`, `telemetry/*`, policy/adapters on a seam). | T:DS-ARCH | Event bus with these domains and documented modes; extends Y2.1 and C5.5. | M8, M10 | P0 |
| D2.2 | **Waterfall vs serial listeners:** waterfall listeners must call `next()` to delegate (returning without it short-circuits); serial listeners have no `next()`. Waterfall hooks: pre-step, request, stream, three tool hooks. | T:DS-ARCH, T:DS-AGENTS | Hook runner with explicit mode per event (`waterfall`, `serial`, `parallel`); lint rule: waterfall handler that never calls `next` and does not declare `short_circuit=True` fails tests. | M8 | P0 |
| D2.3 | **Turn flow definition:** step = one model request + the tools it calls; turn = zero or more steps; sequence `turn/start` → claim input → snapshot model selection → assemble prompt + tool schemas → **pre-step hook (accept / rewrite / reject)** → `step/start` → prepare call → stream → assistant message or failed attempt → `tool/call` → **pre-execute → execute → post-execute** → `tool/result` → `step/end` → loop or **turn-stopping hook** → `turn/end`. | T:DS-ARCH | Implement this lifecycle verbatim as Keel's loop contract with a diagram in internal docs; each stage has a hook and a log event. | M7 | P0 |
| D2.4 | **Rejected or empty first claim closes the turn without a step.** | T:DS-ARCH | Same rule. | M7 | P1 |
| D2.5 | **One inbox per agent driver;** injected context (`agent.inject()`) waits for a waking message and lands in the next admitted request. | T:DS-ARCH | `agent.inject(text, source)` API; used by hooks/plugins; tainted by source. | M7 | P0 |
| D2.6 | **Request series** (`request/header`, `request/context`): the log marks when a new series of requests starts (surface replacement, image offload) so cache/context changes are explicit; retries do not repeat assembly. | T:DS-ARCH | Log `request_header` events; helps prefix-cache reuse (B1.4) and debugging. | M4, M7 | P1 |
| D2.7 | **System prompt travels as logged `system/message` history;** empty text clears it. | T:DS-ARCH | System prompt changes are log events (supports "model-visible = logged"). | M4, M7 | P0 |
| D2.8 | **Cancellation during prompt preparation commits nothing** (neither system nor user messages). | T:DS-ARCH | Atomic step admission: commit after prepare succeeds. | M4, M7 | P0 |
| D2.9 | **Failed steps record missing tool results** (synthetic). | T:DS-ARCH | Same as Y2.4; add acceptance test. | M4 | P0 |
| D2.10 | **Process-local live stream frames** (`assistant-stream` start/chunk/end) vs **durable settled message** that embeds the compact timed stream; `assistant/attempt` retains failed/retried/cancelled attempts **without adding model history**. | T:DS-ARCH | Streaming UI reads live frames; the log stores the settled message + attempt records; replays/transcripts use durable data only. A hard crash before settlement leaves no durable attempt (documented). | M4, M19 | P0 |
| D2.11 | **Model-visible ⇔ logged:** every model request must be reconstructable from the log; any new model-visible input requires a session event; plugins that alter message content register **pure message projections** (detached readers supply the same). | T:DS-ARCH, T:DS-AGENTS | Hard rule + test that replays a log and reproduces the exact request bytes (hash). | M4 | P0 |
| D2.12 | **Session projection seam:** registered units fold committed events; clients read selected views via `snapshot()`; domain services keep private handles and expose business methods. | T:DS-ARCH | `session_projections` registry for UI state (task list, plan, goals, cost) derived from events. | M4, M19 | P1 |
| D2.13 | **Session format versioning with adjacent migrations:** header-only `stat`/`list` pick the highest generation; read-open translates in memory; write-open **publishes a new version-named successor beside the unchanged source**; committed generations are **never renamed, overwritten or deleted**; each migration step is `vN → vN+1`; missing interrupted `turn/end` inserted only for a bounded released restart; compressed files (`.zstd`) supported. | T:DS-ARCH | Keel session export/import files use this scheme (`session.vN.jsonl.zst`); DB schema migrations stay SQLite-forward-only. Extends Master 10 with *export format* migrations. | M4 | P0 |
| D2.14 | **Persistence-provider interface** (`create`/`open`/`stat`/`list`/`export`) so session storage backends are swappable. | T:DS-ARCH | `SessionPersistence` protocol; SQLite default; JSONL export provider. | M4 | P1 |
| D2.15 | **Fork at a turn boundary** (seeded session with inherited event count; only agent-loop-published sessions persist). | T:DS-ARCH | `fork(session, at_turn)` API used by branches (Master 9.1). | M4 | P0 |
| D2.16 | **Working directories** supply user context and execution paths **without changing project identity, sandbox write roots, or existing process dirs.** | T:DS-ARCH | `working_dir` separated from `project_root` and `write_roots` in the data model. | M5, M11 | P0 |
| D2.17 | **Session title provider** (single registered provider) and **goals** service (same-session objective continued through agent events). | T:DS-ARCH | `title` role plugin; `goals` service (extends goal mode C3.3 with a same-session objective that survives compaction). | M7, M14 | P1 |

## 4. Capability seams and the package map (what Keel should have)

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| D3.1 | **Capability seam = Service Definition + Service Provider + Consumer;** one role alone is not a seam; adding a capability means designing all three. | T:DS-ARCH, T:DS-AGENTS | Seam checklist in the builder guide; each Keel seam has an interface (Protocol), a default provider and a consumer tool. | M0, M7 | P0 |
| D3.2 | **One provider swap changes the whole product:** filesystem and subprocess providers share one execution world, so pointing them at a **remote sandbox moves bash, PTY and LSP together**. | T:DS-ARCH | `fs` and `subprocess` providers selected by an "execution world" setting: local, container, SSH (C4.10), WSL. Tools never import OS APIs directly. | M5, M11, M20 | P0 |
| D3.3 | **Subagent providers** behind one interface: from a fresh child agent to a **delegated turn in another product**. | T:DS-ARCH | Provider interface supports V8 external specialist adapters. | M12 | P1 |
| D3.4 | **Agent Teams:** when enabled for a root session, adds task policy and a **shared task board**; subagent controls own identity, messaging, discovery, interruption, inbox waiting. | T:DS-ARCH | Fleet board (Master 9) backed by this service; enabling it is per root session. | M12 | P1 |
| D3.5 | **Agent presets** compose a different capability set for one session; a service row inside a preset needs an **`isolate` realm**. | T:DS-ARCH | Preset = list of plugins scoped to an agent; isolated services get their own instance. | M7, M12 | P1 |
| D3.6 | **Human commands** registered on a commands service **dispatch without a model turn**. | T:DS-ARCH | Slash commands that are pure code (e.g., `/undo`, `/compact`) never call the model. Add as explicit category (A1.7). | M7 | P0 |
| D3.7 | **Background jobs service** with `job_*` tools to read/stop jobs. | T:DS-ARCH | Jobs registry (Y1.7 background shell) exposes list/read/stop tools. | M5, M14 | P0 |
| D3.8 | **Webhook runtime:** a *trusted rule* starts a session from an external webhook; provider adapters mount beside it. | T:DS-ARCH | Channel/webhook starts sessions only via explicit trusted rules (extends Y5.4, V9). | M15 | P0 |
| D3.9 | **Shell backend, terminals backend, sandbox backend** as separate services; **sandbox wraps argv before spawning**. | T:DS-ARCH | `shell`, `terminals`, `sandbox` seams; sandbox providers: bubblewrap, Job Objects, optional container. | M5, M3 | P0 |
| D3.10 | **Filesystem policy through `fs/*` events** on top of providers. | T:DS-ARCH | `fs/before_read|write` events let policy/plugins veto (Tier 2 listens first). | M3, M5 | P0 |
| D3.11 | **Packages Keel is missing or underspecified** (from the 60+ dsh package groups): `deliverables` (turn deliverables), `spill` (output spill), `attachment`, `guard` (loop/tool guards), `extensions` (runtime self-modification), `feedback` (human feedback), `identity` (anonymous identity), `workspace` (workspace entities), `plan` (logged planning), `schedule` (scheduled follow-ups), `ptc-runtime` (programmatic tool-call execution, meaning to be verified), `session-query` (browse/search/export), `typert` (type graph for RPC), `liveshare`, `inspector`, `experimental` quarantine. | T:DS-AGENTS | Map to Keel rows below (D3.12 to D3.20). | M7 to M21 | P0 |
| D3.12 | **`deliverables`:** each turn can attach named deliverables (files, summaries) shown as a result card. | T:DS-AGENTS | Turn Deliverables panel: files changed, reports produced, with open/export. | M7, M19 | P1 |
| D3.13 | **`spill`:** large tool output spills to a file with a preview (matches Master rule 5). | T:DS-AGENTS | Already planned; add the shared service name and UI "open full output". | M5 | P0 |
| D3.14 | **`guard`:** loop and tool guards as their own plugin group. | T:DS-AGENTS | Doom-loop (C3.2), mass-change (X5.5), step limit (W2.4) live here. | M4, M3 | P0 |
| D3.15 | **`extensions` (runtime self-modification)** group. | T:DS-AGENTS | Agent proposes new skills/commands/agents as diffs for approval (C3.7); never auto-installs. | M9 | P1 |
| D3.16 | **`feedback` (human feedback)** group. | T:DS-AGENTS | Thumbs up/down + note on any message, stored locally, feeding evals (C13.2, V7). | M19, M21 | P1 |
| D3.17 | **`identity` (anonymous identity)** group. | T:DS-AGENTS | Random local install id used only for local keys; never sent anywhere (no mandatory telemetry). | M3 | P1 |
| D3.18 | **`workspace` entities + `session-query` (browse/search/export).** | T:DS-AGENTS | Workspace list, session search (FTS5) and export UI (B4.4). | M4, M19 | P0 |
| D3.19 | **`plan` (logged planning)** and **`schedule` (scheduled follow-ups)**. | T:DS-AGENTS | Plan as log events (checklist survives restart); "follow up in N hours" scheduled task (M14). | M7, M14 | P1 |
| D3.20 | **`experimental/` quarantine:** capabilities under evaluation with **no product-support commitment**, independent of optional delivery; non-experimental packages need product use or explicit classification (policy file). | T:DS-AGENTS | `keel/experimental/` namespace + `product-package-policy` file; X6.10 flags enforced by it. | M0, M10 | P1 |
| D3.21 | **`llm-pi-ai` generated provider metadata** with a check that rejects stale generated data without rewriting files. | T:DS-DEV | Offline provider catalog (Master M2) generated by a script and verified in pre-commit (read-only check). | M2 | P1 |
| D3.22 | **Inspector (DevTools-style frontend)** compiled locally from a pinned source package; no network or browser download at build; published packages contain the built frontend. | T:DS-DEV | Keel "Inspector" dock: event log, prompt assembly, tool timing (B4.7, X8.x); built from pinned local deps. | M21 | P1 |
| D3.23 | **Live Share (experimental):** viewer carrier in the browser + node wire codecs. | T:DS-DEV | Read-only live session viewer on LAN (B4.8) as experimental; no cloud relay. | M20 | P2 |

## 5. Web UI, Desktop, chat nodes and UX

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| D4.1 | **Model setup in Settings → Models:** enter key, save, route usable **immediately without restarting**. | T:DS-GUIDE | Provider form hot-applies (Master 9.3); show a test result inline. | M19 | P0 |
| D4.2 | **Custom OpenAI-compatible endpoints** documented as a first-class path. | T:DS-GUIDE | Provider type "OpenAI-compatible" (local servers, LAN). | M2 | P0 |
| D4.3 | **Workspace required:** "Choose workspace" flow; **composer is unavailable until a workspace is selected**; fresh UI has none selected even though the process has a default directory. | T:DS-GUIDE | Same gate; empty state explains why; Chat mode without workspace still allowed in Cowork (optional). | M19 | P0 |
| D4.4 | **In-page directory picker** vs native picker; an overlay config pins the in-page picker for automated browser tests/GIF recording. | T:DS-AGENTS | Renderer has an in-app folder browser (works over SSH/headless web) and a test override. | M19, M25 | P1 |
| D4.5 | **Web client Chat nodes:** extensible `ConversationNodeDefinition` + keyed renderer so plugins add new message/node types. | T:DS-ARCH | Renderer registry for transcript row kinds (Y2.9); plugins register a node type + renderer + persisted shape. | M19, M10 | P0 |
| D4.6 | **Settings cards contributed by plugins** (cookbook "adding a settings card"). | T:DS-ARCH | Plugin manifest can add a settings card with schema-driven form. | M10, M19 | P1 |
| D4.7 | **Tool UI presentation designed up front:** host presenters are pure; web cards derive from **raw events and persisted result metadata**. | T:DS-AGENTS | Each tool ships a presenter (summary, icon, expanded view) as a pure function over events. | M5, M19 | P0 |
| D4.8 | **Client UI copy is locale-owned:** product text only through typed dictionaries/`t()`; a gate rejects hardcoded copy; English copy and plugin titles use **sentence case**. | T:DS-AGENTS | Lint gate for the renderer + plugin manifests (`verify_ui_copy`). | M19, M25 | P0 |
| D4.9 | **Official plugin artwork** policy: bundled plugins use a consistent icon set; new glyphs need designer approval. | T:DS-AGENTS | Icon guidelines in `tokens.json` docs; owner approves new icons. | M19 | P2 |
| D4.10 | **UI design/review entry point** as a reusable skill file (design principles + references loaded on demand). | T:DS-AGENTS | `UI-UX-GUIDE.md` (private) the builder must load before any UI change. | M0, M19 | P1 |
| D4.11 | **Plugin Manager UI** in the base bundle for Web and agents. | T:DS-ARCH | Extensions page (Y1.31) also usable by agents with approval. | M10, M19 | P0 |
| D4.12 | **Desktop window loads packaged assets immediately** and activates client plugins after readiness. | T:DS-ARCH | Fast first paint; skeleton + "starting daemon" state (X8.x). | M19 | P0 |
| D4.13 | **Port selection:** web UI default fixed port, desktop OS-assigned, overridable by profile config. | T:DS-README, T:DS-ARCH | Same defaults; port conflict handling with clear message. | M20 | P1 |

## 6. Safety, trust and responsible-use copy

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| D5.1 | **Plain statement that the software executes model-generated code/commands, loads third-party plugins, and accesses network, processes, credentials and files; defects, misconfiguration, malicious input or untrusted plugins can damage the host.** | T:DS-SAFETY | First-run Safety notice + EULA summary (W1.10). | M19 | P0 |
| D5.2 | **"Sandboxing, approvals and permissions reduce risk but do not guarantee isolation"; do not rely on it as the sole control for untrusted workloads.** | T:DS-SAFETY | Same wording in the Known-limits page (W7.19). | M19, M23 | P0 |
| D5.3 | **Responsible-use list:** least privilege; disposable VM/container; keep backups; don't expose sensitive credentials; review plugins, config and proposed commands. | T:DS-SAFETY | Onboarding checklist item for each point; wizard offers "Run in disposable container" (V17) and "Create backup before first agent run". | M19 | P0 |
| D5.4 | **No warranty / no liability** paragraph referencing the license. | T:DS-SAFETY | Goes into EULA/DISCLAIMER via lawyer review (G5). | M1 | P0 |
| D5.5 | **Host sandbox failures rule (builder):** if a required command fails because the dev sandbox blocks credentials/network/IPC, retry unchanged with the narrowest escalation, require evidence of the sandbox cause, and **never bypass test failures or the product sandbox**. | T:DS-AGENTS | Add to builder stop-list (X10.4). | M0 | P0 |

## 7. Builder constitution (rules to give the AI builder, from DS-AGENTS)

Each rule becomes a line in the private `AGENTS.md` and, where marked, a CI gate. Adapt wording to Python.

| ID | Rule | Gate? | M |
| --- | --- | --- | --- |
| D6.1 | **Pre-stable APIs:** update every consumer when a public API changes; record each externally perceptible breaking change **immediately** in an upgrade guide; SQLite uses a monotonic `SCHEMA_VERSION`. | Check: PR touching public API must touch `UPGRADE.md` | M0 |
| D6.2 | **Plugins, not loop changes:** new behavior attaches to documented extension points; changing the loop requires updating the architecture doc. | Doc-sync gate | M0 |
| D6.3 | **Typed events** with documented mode and payload fields; closed unions end in an exhaustive check (`assert_never`); extensible unions use a documented default. | Type check + lint | M8 |
| D6.4 | **Explicit over implicit at package boundaries:** defaults are applied in an explicit `resolve(request) -> Spec` step, never a hidden `or default` inside `run()`. | Review rule | M0 |
| D6.5 | **No hardcoded tunables in plugins:** deployment-varying choices are validated config fields; constants stay for protocol, external specs and security invariants. | Lint for magic numbers in plugin dirs (allowlist) | M2 |
| D6.6 | **Misconfiguration fails loud** at load (or earliest resolvable point); never silently skip a missing referent. | Test per plugin | M2 |
| D6.7 | **Opaque cross-boundary ids are branded types** (`NewType`), never bare `str`. | mypy/pyright | M0 |
| D6.8 | **Trust types inside the process; validate at boundaries** (parser/config, queued messages, model/tool JSON, durable files, worker/process/wire). Don't add hostile-input tests for values the static interface already requires. | Review rule | M0 |
| D6.9 | **No new casts to `Any`/`object`** beyond the recorded baseline; replace with typed values or validation. | Baseline-count gate | M0 |
| D6.10 | **Source plane vs artifact plane never mixed:** tests/gates resolve imports to source and pass on a clean tree; gates that need built output declare that dependency. | Gate declaration | M0, M22 |
| D6.11 | **Structured, typed errors** (`KeelError` with code); stop dependent work and visibly report untrusted state or unknown outcomes; empty `except` blocks must name the error and why and contain one statement. | Gate for empty-except | M0 |
| D6.12 | **Comments:** local and non-restating; document behavior, failure, timing, ownership, safe use; every public export has a docstring with params/returns; word budgets for docs. | Docstring gate + budget gate | M0 |
| D6.13 | **Docs accompany code:** update README/docstrings in the same change. | doc-sync | M0 |
| D6.14 | **Tests describe behavior, not "correctness"**; change obsolete behavior together with its tests and explain why. | Review | M0 |
| D6.15 | **Every non-trivial model- or user-visible change updates a keyless recorded-session snapshot;** fixtures replay on macOS and Linux (and Windows); **fix fixtures, not normalizers.** | Snapshot gate | M25 |
| D6.16 | **Both SDKs project the loop:** loop/session-lifecycle/event-map changes update the Python and TypeScript SDK expected outputs in the same change. | Gate | M20 |
| D6.17 | **Agent Notes** (ADR-like) only for durable decision rationale; archived notes frozen, never edited or treated as current authority. | Convention | M0 |
| D6.18 | **Prefer maintained dependencies over hand-rolling** when they delete owned code and tests. | Review | M0 |
| D6.19 | **Vendoring policy:** vendored packages are pinned source copies with a manifest of upstream SHAs; changes require a manifest update (pre-commit guard); local modifications are logged and re-applied or retired on sync. | Pre-commit guard | M0, M1 |
| D6.20 | **Run only relevant checks locally:** match evidence to the change (focused tests, snapshots, doc-sync, built smokes, real-provider e2e); CI owns exhaustive coverage; don't repeat a passing check for commit/push. | Builder rule | M0 |
| D6.21 | **PR hygiene:** one `kind/*` and all material `area/*` labels; rewrites use force-with-lease only; PR description template. | Template | M0 |
| D6.22 | **TODO markers by urgency:** `FIXME` (blocks release), `TODO` (soon), `XXX` (someday). | Gate: release fails on open FIXME | M22 |
| D6.23 | **Defensive-patterns doc** read before touching package surfaces, remote services, client state, conversation/session behavior, lifecycle/concurrency/subprocess/teardown code. | Doc | M0 |
| D6.24 | **Strict typing everywhere;** any remaining dynamic type explains why. | pyright strict | M0 |
| D6.25 | **Machine-checkable invariants wired into an executed top-level gate and each gate proven to reject an invalid case;** narrow justified exceptions instead of disabling rules globally. | Meta-test for gates | M0, M25 |

## 8. Dev workflow, build, CI and release (new items)

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| D7.1 | **Gate scheduler** (`run-gates`): all gates as a dependency graph; bounded concurrency env var; fail-fast switch; a failure skips only its dependents so independent errors all report. | T:DS-DEV | `scripts/run_gates.py` with `KEEL_GATE_CONCURRENCY`, `KEEL_GATE_FAIL_FAST`. | M0 | P0 |
| D7.2 | **Worker budgets** differ locally vs CI (local capped because container CPU counts mislead). | T:DS-DEV | Detect cgroup CPU quota; local cap defaults. | M0 | P2 |
| D7.3 | **Separate type-check programs for two faces** (host and client) because both declare the same keys with different services and would collide in one program. | T:DS-DEV | Keel analog: separate `pyright`/`tsc` projects for daemon, renderer/main and SDKs; never a combined program; gate verifies each package belongs to exactly one face. | M0, M19 | P1 |
| D7.4 | **Typed remote-call contract generation:** services declare callable methods with a decorator; the build generates client-side types and runtime contributions. | T:DS-DEV | Generate TypeScript client types from the Python API (pydantic → OpenAPI/JSON Schema → TS), checked in CI for drift. | M20 | P0 |
| D7.5 | **Build order:** native addon → contract generation → compile host → bundle → compile client → bundle client → web; `build:check` verifies tests/scripts against the already-built output and does not rebuild. | T:DS-DEV | Documented build pipeline with explicit stages; separate `check` stage. | M22 | P1 |
| D7.6 | **Embedded build identity:** version + short commit + dirty marker; `official` build omits the dirty marker; a gitignored **build record binds exact public values to the output** and release packing rejects a missing/stale record. | T:DS-DEV | Build record file validated by release job; About screen shows it (V13). | M22 | P0 |
| D7.7 | **Local vs official build profiles** (`--profile local` keeps version/commit/dirty, discards inherited branding overrides). | T:DS-DEV | `--profile local|official` build flag. | M22 | P1 |
| D7.8 | **Windows and WSL guidance:** keep checkout and toolchain in the same OS environment; install deps separately per environment; Windows behavior needs native validation. | T:DS-DEV | Builder docs + CI Windows lane separate from Linux. | M0, M25 | P1 |
| D7.9 | **Strict dependency linker** so undeclared deps fail; build scripts of dependencies explicitly allowlisted. | T:DS-DEV | `pip-compile`/lockfile with hash pinning; Electron side uses a strict package manager config with an allowlist of postinstall scripts. | M0 | P0 |
| D7.10 | **Hooks:** worktree-local git hooks installed by a script; pre-commit = staged lint profile with fix + bounded retry, whitespace check, generated-metadata check, vendor manifest guard; pre-merge-commit check; pre-push = typecheck. Hooks deliberately **don't** run tests/builds; opt-in `check:all`. | T:DS-DEV | Same hook set via lefthook or pre-commit. | M0 | P1 |
| D7.11 | **Doc gates:** doc-sync aggregate, doc typecheck (compiles code fences), **type-equiv** (documented type declarations pasted into docs are verified against source by a gate), docs site build doubles as dead-link check, translation pairing records with merge-conflict repair command. | T:DS-DEV | Python: docs code fences executed/type-checked; verified paste of key types (V19). | M0, M23 | P1 |
| D7.12 | **CI layout:** broad lanes of independent gates, a smaller **Node-version compatibility matrix**, native Windows lane in a separate workflow, Python checks separate, **required benchmarks on standard hosted Linux**, real-API e2e in its own workflow, partitioned coverage using per-platform timing data. | T:DS-DEV | CI lanes: gates, matrix (Python 3.11/3.12/3.13), Windows, macOS, benchmarks, provider-e2e (opt-in, self-skips without key). | M0, M25 | P0 |
| D7.13 | **Per-file 100% coverage gate** on package sources in CI (separate from the normal test command). | T:DS-AGENTS | Start with 100% on security-critical modules (permission gate, analyzer, crypto); others graded. | M25 | P1 |
| D7.14 | **Test taxonomy rules:** real-API e2e **self-skip without key**; "expected" tests are owner-local process expectations; **snapshot tests replay recorded sessions through shipped profiles without a key**, with a `record` mode that needs a key. | T:DS-AGENTS | Same three-way split (W1.5, X9.1/9.2). | M25 | P0 |
| D7.15 | **Release rehearsals:** dependency-layout rehearsal and pack rehearsals (build packages exactly as release does) run credential-free; **self-hosted runner failover** only for trusted events (non-fork, non-bot PRs); manual publish stays hosted. | T:DS-DEV | `release --dry-run` (C12.6) + documented failover to owner's free self-hosted runners with trust rules. | M22 | P1 |
| D7.16 | **Package hygiene checks:** `publint`-style entrypoint validation and a clean "consumer" import check against built declarations. | T:DS-DEV | Python: `twine check`, import smoke test in a clean venv; TS SDK: consumer check. | M22 | P1 |
| D7.17 | **Windows signing docs** as required reading for packaging; desktop packaging profile per signing mode. | T:DS-AGENTS, T:DS-DEV | Keel ships unsigned (D3 in Master); keep a `packaging/README` with modes ready for the day a certificate exists. | M22 | P2 |
| D7.18 | **Update-time breaking-change notice:** release carries the upgrade guide entries since the installed version. | T:DS-AGENTS (upgrade guides) | Updater shows "What changes for you" before install (S+DS). | M22, M19 | P1 |
| D7.19 | **Benchmark method:** drive tasks through the SDK's minimal JSON-RPC agent variant with **separate workspaces and session ids per independent task**. | T:DS-BENCH | Keel benchmark runner uses the `sdk-minimal` profile and isolated workspaces (C13.1). | M21 | P0 |
| D7.20 | **Labels taxonomy and stacked PRs** (native stacks, merge-forward vs rebase). | T:DS-AGENTS | Private repo practice; optional. | M0 | P2 |

## 9. Builder protocol for own ideas `[S]`

For every `V` row below (and any `[S]` row anywhere): (1) one-paragraph why + 2 similar products/standards by category; (2) free/license check with date; (3) spec in Keel's words; (4) smallest slice behind an `experimental` flag; (5) negative tests first if security-relevant; (6) end-to-end evidence incl. offline run; (7) owner review before default-on if it stores new personal data, uses network, or changes approvals.

| ID | Idea | Approach for the builder | M | Pri |
| --- | --- | --- | --- | --- |
| V16 | **Keel invariant-gate catalog:** a list of gates specific to Keel: Tier-2 table hash unchanged; no outbound network in offline suite; no secret in logs; every tool has a presenter; every plugin manifest declares permissions; no hardcoded UI copy; migration compat matrix; no `Any` baseline growth. | Create `gates/` with one script per invariant; each gate has a failing-fixture test proving it rejects bad input (D6.25). | M0, M25 | P0 |
| V17 | **Disposable-sandbox run mode:** run the agent's tool execution in a container with a copy-on-write view of the project, then show a diff and apply only approved hunks back. | Podman/Docker optional; overlay or copy; reuse diff review dock; falls back to a temp-copy mode without containers. Never required. | M5, M19 | P1 |
| V18 | **Plugin static capability scan:** before enabling a plugin, scan its Python/JS for subprocess, socket, ctypes, `eval/exec`, file writes outside its data dir, and compare with its declared permissions; mismatch blocks enabling. | AST scan; show findings in install dialog; best-effort and labeled as such (not a sandbox). | M10 | P1 |
| V19 | **Executable docs:** code fences in user and internal docs run in CI against the mock model; "paste of key types" verified against source. | Doc tool extracts fences tagged `keel-run` and `keel-type`; fail on drift. Mirrors D7.11 for Python. | M23, M25 | P1 |
| V20 | **Turn Replay Test builder:** "save this turn as a test" button producing a snapshot fixture (recorded stream + expected log) for the builder's suite. | Export current turn's request/response stream with secrets scrubbed; stored under `tests/snapshots/`. | M21, M25 | P1 |
| V21 | **Contract generator for plugin events:** generate docs and JSON Schemas for every event type from code annotations, and fail CI if an event lacks `mode` and payload docs (D6.3). | Python `typing` + docstring parser; output into the private docs and plugin SDK. | M8, M10 | P1 |
| V22 | **Seam checklist linter:** verifies each registered seam has a definition, a default provider and at least one consumer, and flags single-role "seams" (D3.1). | Reads the service registry at test time. | M7 | P2 |
| V23 | **Run-in-isolation toggle for risky plugins:** run plugin code in a separate subprocess with its own env, reachable only via the RPC bridge. | Same pattern as MCP workers (Master 11.9); default for unsigned plugins. | M10 | P1 |

## 10. UI/UX screens added from DeepSeek (use Keel tokens only)

- Settings → Models (instant apply, endpoint type includes OpenAI-compatible, test result inline) `T:DS-GUIDE`
- Choose workspace (in-page folder browser + native; gate on composer) `T:DS-GUIDE, DS-AGENTS`
- Plugin Manager (install/update transactions with log; reload; enable/disable; permissions diff) `T:DS-ARCH`
- "What is running" (dump-config view with row ids and which layer set them) `T:DS-ARCH`
- Chat transcript with **plugin-contributed node types** and tool cards derived from raw events `T:DS-ARCH, DS-AGENTS`
- Settings cards contributed by plugins `T:DS-ARCH`
- Inspector dock (event log, prompt assembly, timings) `T:DS-DEV`
- First-run Safety notice and Known-limits page `T:DS-SAFETY`
- Desktop splash/"starting daemon" and fatal-error screen `T:DS-ARCH`
- Turn Deliverables card and Plan/Goal panels `T:DS-AGENTS`

## 11. Conflicts and decisions to record

| ID | Issue | Resolution |
| --- | --- | --- |
| C-8 | dsh requires 100% per-file coverage and a very large gate set; a solo owner with a free-tier CI may not afford the minutes (Master Section 8, CI row). | Adopt gates in tiers: security-critical modules 100%, everything else graded; run heavy lanes on release tags and locally. Record in `DECISIONS.md`. |
| C-9 | dsh is explicitly "not secure, not production-ready, developer preview"; Keel's goal is a shippable product. | Copy the honesty (D5.x) but keep Keel's Tier-2 and approvals as hard requirements; do not use "preview" as an excuse for skipping security tests. |
| C-10 | dsh makes plugins everything, including the safety layers (replaceable by patches). | Keel keeps Tier 2 non-replaceable (D1.1). |
| C-11 | dsh's `!!js` config feature allows code in config files. | **Do not adopt:** config stays data-only; conditional composition via overlays/profiles only. |
| C-12 | `apps/*` and each package README remain unread. | Treat all DS package-level claims as `[T:DS-AGENTS]` summaries only until M0 reads them. |

## 12. Priority order

1. **Core model:** D1.1 to D1.5, D1.10, D2.1 to D2.3, D2.7 to D2.11, D2.13, D2.16, D3.1, D3.2, D3.9, D3.10.
2. **Builder constitution and gates:** D6.1 to D6.12, D6.15, D6.16, D6.25, D7.1, D7.12, V16.
3. **UI foundations:** D4.1 to D4.8, D4.11, D4.12.
4. **Safety copy and onboarding:** D5.1 to D5.5, V17.
5. **Everything else** at its milestone; P2 after the v1.0 candidate is green. All rows enter `PLAN-INDEX.json` with their source tag.
