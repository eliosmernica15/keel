# Keel Master Plan v6

**Status:** canonical expanded roadmap. Supersedes v5 for planning purposes while preserving v5 as the historical baseline.

## Source documents (preserved unchanged)

All eight uploaded specification documents are preserved verbatim in `keel/docs/plan-sources/`.

- `Keel_Master_Plan_v5.md`
- `Keel_Plan_v5_Addendum_Missed_Features.md`
- `Keel_Plan_v5_Addendum_2_More_Features.md`
- `Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md`
- `Keel_Plan_v5_Addendum_4_Sourced_Features_and_Builder_Guide.md`
- `Keel_Plan_v5_Addendum_5_DeepSeek_Harness_and_Deep_Reads.md`
- `Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md`
- `Keel_Plan_v5_Addendum_7_DeepSeek_Deep_Reads.md`

**Registry:** 865 features (priority counts: {'P1': 524, 'P0': 240, 'P2': 101}).

## Known source gap

The supplied v5 copy ends during Section 11. Sections 12–16, the Section 13 milestone mapping, complete M0–M26 definitions, and Appendices A–D were not supplied and are **not reconstructed**. The addenda provide explicit feature-level authorization for the expanded scope below.

## Expanded product vision

Keel is a local-first AI workstation with four surfaces: **Keel Cowork** (knowledge work), **Keel Code** (engineering), **Keel Duet** (live pairing), and **Keel Fleet** (multi-agent organization). Electron is the desktop shell, Python is the authoritative runtime, and SQLite is the canonical local database. A loopback web UI, CLI and TUI share the same token-authenticated Python runtime.

## Architecture constraints

- Python authoritative backend/runtime; Electron desktop shell; SQLite canonical DB.
- Local-first, offline-capable, free to use; no mandatory account, hosted backend, paid service or telemetry.
- Preserve existing permission tiers, approval broker, session/event model, and DB migrations.
- Python enforces all permissions. Plugins, skills and MCP remain gated and observable.
- New dependencies require license, security, maintenance and packaging review; optional local tools preferred.

## Feature traceability

Machine-readable registry: `PLAN-INDEX.json` (canonical) and `parity.json` (synchronized projection generated from it). Every addendum feature ID is preserved; no feature is silently omitted.

| ID | Feature | Milestone | Priority | Status |
| --- | --- | --- | --- | --- |
| A1.1 | Non-interactive run mode (`keel run "prompt"`, pipes, JSON output, exit codes) for scripts and CI | M20 | P1 | verified |
| A1.10 | `todo` tool (agent keeps a visible task checklist), separate from the plan | M5 | P0 | verified |
| A1.11 | `webfetch` tool and `websearch` tool with **free** backends | M5 | P0 | verified |
| A1.12 | Per-agent tool enable/disable and per-agent permission overrides | M7 | P0 | verified |
| A1.13 | Custom tools as code files dropped in `.keel/tools/` (Python) | M10 | P1 | verified |
| A1.14 | `instructions` config: extra instruction files by glob or URL | M7 | P1 | verified |
| A1.15 | `small_model` for titles/summaries (already a role) plus per-agent model override | M2 | P1 | verified |
| A1.16 | Configurable leader-key keybinds, custom theme JSON files | M19 | P1 | verified |
| A1.17 | Session import/export commands and `keel stats` (usage by model/day) | M21 | P1 | verified |
| A1.18 | `keel agent create` wizard, `keel models`, `keel auth` subcommands | M20 | P1 | verified |
| A1.19 | **GitHub Actions mode**: run Keel headless in the user's own CI to answer issues/PR comments | M20 | P2 | verified |
| A1.2 | Attach a CLI/TUI/IDE client to an already-running daemon (`keel attach`) | M20 | P1 | verified |
| A1.20 | Watcher ignore list, auto-update toggle, env-var overrides (`KEEL_*`) | M2 | P1 | verified |
| A1.21 | Remove versions older than X before install notice | M22 | P2 | verified |
| A1.22 | `AGENTS.md` for the builder itself (internal) describing layout and conventions | M0 | P0 | verified |
| A1.3 | **Terminal UI front-end** (full TUI, not only Electron) | M20 | P1 | verified |
| A1.4 | **Local web UI** served on loopback (`keel web`) for browser access | M20 | P1 | verified |
| A1.5 | `/init` command: scan repo and generate `AGENTS.md` | M7 | P0 | verified |
| A1.6 | Inline shell via `!cmd` prefix in composer (goes through permission gate) | M19 | P1 | verified |
| A1.7 | Slash commands: `/undo /redo /compact /export /models /themes /details /editor /share-local` | M7 | P0 | verified |
| A1.8 | Open file/diff in user's `$EDITOR` / VS Code | M19 | P1 | verified |
| A1.9 | Image paste/drag into composer, fuzzy `@file` search | M19 | P1 | verified |
| A2.1 | **Voice-to-task handoff**: a voice session hands work to the same agent loop and reads results back | M17 | P1 | verified |
| A2.2 | System-wide push-to-talk dictation hotkey (types into any app) | M17 | P1 | verified |
| A2.3 | Per-agent **persistent browser profile** and per-agent workspace folder | M16 | P1 | verified |
| A2.4 | Idle suspend/wake of heavy resources (browser, container desktop, LSP) | M16 | P1 | verified |
| A2.5 | Group-chat loop guards (agents @mentioning each other endlessly) | M12 | P1 | verified |
| A2.6 | Primary-agent daily check-in/digest at chosen times | M14 | P1 | verified |
| A2.7 | Documented `.env.example`-style config reference for every setting | M2 | P1 | verified |
| A2.8 | Local Playwright E2E that exercises real flows (chat, tools, viewer, search, connections, voice, groups, settings) | M25 | P1 | verified |
| A2.9 | Memory-consolidation and history-compaction **tunable knobs** surfaced in settings | M13 | P1 | verified |
| A3.1 | **Outgoing signed webhooks** with retry/backoff and delivery log | M14 | P1 | verified |
| A3.10 | Per-vendor **cost caps with daily and monthly windows** | M21 | P1 | verified |
| A3.11 | Deploy/operations docs for headless mode (`keel serve` on a home server) | M20 | P1 | verified |
| A3.2 | Idle task-workspace garbage collection (temp folders) | M14 | P1 | verified |
| A3.3 | **Mock/scripted agent** for UI development and tests (deterministic scripted runs) | M19 | P1 | verified |
| A3.4 | Interactive **questions** from agent mid-task with timeout and default answer | M5 | P0 | verified |
| A3.5 | Setup script that generates local secrets idempotently and prints what is missing (`keel setup`) | M3 | P1 | verified |
| A3.6 | "Sign out everywhere / disconnect" equivalent: **revoke all client tokens** and reset daemon key | M3 | P0 | verified |
| A3.7 | Honest "Project status" page listing what is proven end-to-end vs built-but-unproven | M26 | P1 | verified |
| A3.8 | Site tools: secrets manager, DB browser, scheduled jobs, analytics, element editor for generated sites | M18 | P2 | verified |
| A3.9 | Operator-style **Admin page** (limits, alerts, health, background job table) | M21 | P1 | verified |
| A4.1 | **OS service supervision**: daemon as systemd user unit / launchd agent / Windows scheduled task, watchdog, crash-loop backoff | M14 | P1 | verified |
| A4.2 | Deterministic, reproducible template/package build (stable tarball, pinned versions) | M22 | P1 | verified |
| A4.3 | MCP presets catalog limited to free/self-hosted servers (filesystem, git, fetch, SQLite, time, memory, Playwright, sequential-thinking, etc.), one-click add, dormant until configured | M6 | P1 | verified |
| A4.4 | Rigor contract in persona (verify before claiming done, cite evidence) as default agent preamble | M7 | P0 | verified |
| A4.5 | Coding-agent routing rules (which sub-agent/model for which task type) in the persona | M12 | P1 | verified |
| A4.6 | "Test-fire" check for every integration after saving credentials | M15 | P0 | verified |
| A4.7 | Secret providers beyond keychain as user choice: env file, command (`pass`, `bw` CLI the user already owns) | M3 | P2 | verified |
| A4.8 | Release scan proving **zero secrets in artifacts** on every release | M22 | P0 | verified |
| A5.1 | **Gateway** process concept with `status`, start/stop, and a list of running channels | M15 | P1 | verified |
| A5.2 | Install a channel/plugin from a git URL or local link for development (`install --link`) | M10 | P1 | verified |
| A5.3 | **Account-level config inheritance** (account overrides channel defaults) | M15 | P1 | verified |
| A5.4 | **Delivery fallback chain** (preferred service, then fallback) | M15 | P1 | verified |
| A5.5 | Outbound message state machine: queued, sent, delivered, read, failed with retries and dedupe by message id | M15 | P1 | verified |
| A5.6 | Webhook subscription helper (register, list, rotate secret) as a CLI command | M15 | P1 | verified |
| A5.7 | Per-channel troubleshooting checklist surfaced in UI when a channel fails | M15 | P1 | verified |
| B1.1 | **Grammar/JSON-schema constrained decoding** for tool calls | M2 | P0 | verified |
| B1.10 | Speculative/draft decoding toggle where the runtime supports it | M2 | P2 | verified |
| B1.2 | Tolerant tool-call parser + **repair loop** | M2 | P0 | verified |
| B1.3 | Difficulty-based **model router** | M2 | P1 | verified |
| B1.4 | Prefix/KV-cache reuse | M2 | P1 | verified |
| B1.5 | Smart context management | M4 | P0 | verified |
| B1.6 | **Model download manager** | M2 | P0 | verified |
| B1.7 | Hardware detector and quantization advisor | M2 | P1 | verified |
| B1.8 | Local embedding + reranker models | M11 | P1 | verified |
| B1.9 | **Compare mode (arena)** | M19 | P1 | verified |
| B2.1 | **Verification loop**: auto-detect test/lint/type commands, run after edits, feed failures back, stop at "definition of done" checklist | M7 | P0 | verified |
| B2.10 | HTTP/API tester with saved collections | M15 | P2 | verified |
| B2.11 | Diagram tools: Mermaid and Graphviz rendering offline | M17 | P1 | verified |
| B2.12 | OCR and document parsing (Tesseract, PDF text/tables) with license check | M17 | P1 | verified |
| B2.13 | Optional local image generation (user-installed ComfyUI/diffusers, model licenses shown) | M17 | P2 | verified |
| B2.14 | Prompt library with variables, snippets, "improve my prompt" helper | M19 | P1 | verified |
| B2.15 | Macro/workflow recorder from chat history into a reusable workflow | M8 | P1 | verified |
| B2.16 | Workflow and team template **gallery** (bundled, offline) | M12 | P1 | verified |
| B2.2 | Spec-driven mode: spec, task breakdown, implement, verify, with approvals between stages | M7 | P1 | verified |
| B2.3 | **Keel Duet default design**: builder agent + independent reviewer agent with different model/prompt; reviewer can only comment | M12 | P1 | verified |
| B2.4 | Specialist agents shipped as bundled markdown: code reviewer, security reviewer, test writer, refactorer, docs writer, dependency upgrader, merge-conflict resolver, bisect helper, changelog and PR-description writer | M7 | P1 | verified |
| B2.5 | Deep-research mode with citations, local files plus web, saved as a report | M17 | P1 | verified |
| B2.6 | Local **RAG knowledge bases** over folders, PDFs, docs; file watcher; citations with file and line | M13 | P1 | verified |
| B2.7 | Offline documentation packs (language/library docs) the agent can search | M13 | P2 | verified |
| B2.8 | Notebook/REPL tool for data analysis with inline charts | M5 | P1 | verified |
| B2.9 | Read-only **database explorer** tool (SQLite, Postgres, MySQL via user's own connection), write needs approval | M15 | P1 | verified |
| B3.1 | **WASM/Pyodide sandbox** for running untrusted generated code with no Docker | M5 | P1 | verified |
| B3.10 | Optional app-lock passphrase and auto-lock on idle | M3 | P2 | verified |
| B3.11 | Provider **circuit breaker**, retry/backoff, health score, automatic failover | M2 | P0 | verified |
| B3.12 | Immutable, exportable audit bundle with verification tool | M3 | P1 | verified |
| B3.2 | Container sandbox with CPU, memory, time and network limits (optional Podman) | M5 | P1 | verified |
| B3.3 | **Dry-run mode**: agent plans and shows every side effect, executes none | M7 | P0 | verified |
| B3.4 | Read-only session mode and per-project **network egress allowlist** per tool | M3 | P0 | verified |
| B3.5 | **Egress log / privacy dashboard**: exactly what was sent to which provider and when | M21 | P0 | verified |
| B3.6 | PII/secret **redaction before sending to any remote provider** (regex + small local classifier), with preview | M3 | P0 | verified |
| B3.7 | Local prompt-injection classifier and canary tokens in fetched content | M3 | P1 | verified |
| B3.8 | Output DLP: block agent from writing secrets into files, commits or messages | M3 | P0 | verified |
| B3.9 | **Global kill switch** (hotkey and tray): stop all agents, revoke tokens, freeze scheduler | M14 | P0 | verified |
| B4.1 | Global quick-ask hotkey overlay (spotlight style) | M19 | P1 | verified |
| B4.10 | Portable mode, multiple profiles (work/personal data dirs), relocatable data dir | M22 | P1 | verified |
| B4.11 | Scheduled **encrypted backups** with restore wizard; optional E2EE folder sync of settings/memory via the user's own synced folder | M14 | P1 | verified |
| B4.12 | `keel doctor --bundle`: redacted diagnostics zip the user can send to support | M21 | P0 | verified |
| B4.13 | Auto-rollback if a new version fails to start 3 times | M22 | P1 | verified |
| B4.14 | Delta updates and optional beta channel (opt-in) | M22 | P2 | verified |
| B4.2 | `keel://` deep links, `keel .` to open a folder, "Open with Keel" shell integration, shell completions | M19 | P1 | verified |
| B4.3 | Multi-window, detachable and split panels, saved workspace layouts | M19 | P1 | verified |
| B4.4 | Message edit/regenerate, pin, bookmark, tags/folders, semantic conversation search | M19 | P1 | verified |
| B4.5 | Rich rendering: Markdown, Mermaid, LaTeX, image/PDF preview, copy and apply buttons on code blocks | M19 | P1 | verified |
| B4.6 | Fleet views: kanban task board, agent org chart, cost per agent, live "agent wall" | M12 | P1 | verified |
| B4.7 | Observability views: token waterfall, flame graph, prompt diff between turns, slow-tool detector | M21 | P1 | verified |
| B4.8 | Phone companion: **LAN web app with QR pairing** and pinned self-signed TLS (control and approvals from phone, no cloud) | M20 | P2 | verified |
| B4.9 | Optional vim keybindings in composer; dyslexia-friendly font option (OFL fonts, notices) | M19 | P2 | verified |
| B5.1 | Download page with OS and CPU auto-detect, file size, SHA-256, "how to verify" guide for Windows/macOS/Linux | M23 | P1 | verified |
| B5.2 | `latest.json` plus release-notes RSS/JSON feed and version history | M23 | P1 | verified |
| B5.3 | System requirements, model-size guide, first-run guide for unsigned installers (SmartScreen, Gatekeeper) | M23 | P1 | verified |
| B5.4 | Offline-capable docs search (static index) and versioned docs | M23 | P1 | verified |
| B5.5 | Privacy page ("what Keel does not collect"), EULA page, third-party notices page, SBOM download | M23 | P1 | verified |
| B5.6 | Auto-generated screenshot gallery from E2E runs; short recorded demo replays | M23 | P1 | verified |
| B5.7 | Curated public roadmap and FAQ, comparison page, press kit, `mailto` support (no third-party form service) | M23 | P2 | verified |
| B5.8 | Localized website using the same string catalogs | M25 | P2 | verified |
| B5.9 | Static status page for update feed and mirrors | M23 | P2 | verified |
| B6.1 | Reserved offline **signed license token** format and verifier module, disabled and unused | M24 | P2 | verified |
| B6.2 | Edition/channel field in manifest and About screen (value "standard") | M24 | P2 | verified |
| B6.3 | Enterprise: silent-install flags for MSI/pkg/deb/rpm, Windows Group Policy templates (ADMX), macOS managed-preferences plist | M24 | P2 | verified |
| B6.4 | Private org **update mirror** (signed manifests, custom feed URL) and private extension registry | M24 | P2 | verified |
| B6.5 | Compliance pack: security whitepaper, accessibility conformance report, data-flow diagram, SBOM export, DPA/EULA templates (lawyer review) | M24 | P2 | verified |
| B6.6 | Per-organization audit export format and retention settings | M24 | P2 | verified |
| B7.1 | Property-based and fuzz tests for path containment and the command analyzer; mutation testing on the permission gate | M25 | P0 | verified |
| B7.2 | Golden-file tests for prompt assembly; chaos tests (kill daemon mid-turn, disk full, DB locked); soak tests | M25 | P1 | verified |
| B7.3 | Accessibility audit (axe) and visual regression in CI | M25 | P1 | verified |
| B7.4 | Performance budgets: cold start, idle memory, installer size, time to first token overhead | M21 | P0 | verified |
| B7.5 | Flaky-test quarantine with owner and expiry | M25 | P1 | verified |
| B7.6 | Machine-readable task index (`PLAN-INDEX.json`): one entry per feature ID with status, evidence path, test path | M0 | P0 | verified |
| B7.7 | Architecture Decision Records (ADRs), commit convention, pre-commit hooks, devcontainer-free dev setup script | M0 | P1 | verified |
| B7.8 | Feature-flag registry with kill-switch config for risky features | M3 | P1 | verified |
| B7.9 | Per-milestone kickoff prompt file for the AI builder with explicit "stop and ask" points | M0 | P1 | verified |
| C1.1 | Repo hygiene stack seen in opencode: pre-commit hooks, editorconfig, linters, lockfiles, dependency **patch** folder, changelog file, release scripts folder | M0 | P0 | verified |
| C1.10 | Draft-only social/content skills (posts, threads, SEO notes); nothing posts without approval | M9 | P2 | verified |
| C1.11 | Local task executor inside the container desktop for faster desktop actions (orgo "planned") | M16 | P2 | verified |
| C1.12 | Client pairing allowlist for LAN/headless access (analog of orgo's `ALLOWED_EMAILS`) | M20 | P0 | verified |
| C1.2 | More package-manager distribution: Scoop, Chocolatey, Flatpak, Snap, AUR (binary PKGBUILD), Nix flake (opencode ships several) | M22 | P1 | verified |
| C1.3 | Dev-container-free contributor setup script and `AGENTS.md` for AI builders | M0 | P1 | verified |
| C1.4 | **Screen-share/recording safe mode** (orgo-teammates warns never to show `.env`/dashboards on screen): mask secrets, emails, paths and tokens in UI while on | M19 | P0 | verified |
| C1.5 | Per-integration **builder/operator guides** (orgo ships separate integration guides) | M15 | P1 | verified |
| C1.6 | Agent "looks": avatar, color, voice per agent, voice preview and speed | M12 | P1 | verified |
| C1.7 | Meeting recorder: capture system/mic audio, local transcript, **speaker labels** (optional), summary, action items, link to project | M17 | P1 | verified |
| C1.8 | Notes vault extras: backlinks, graph view, daily notes, templates (nicks-stack uses an Obsidian vault) | M13 | P1 | verified |
| C1.9 | Plugin **presets bundle** (nicks-stack ships a 16-plugin config) | M10 | P1 | verified |
| C10.1 | Interactive tutorial with a sample project, guided tours, tips, "what's new" modal | M19 | P1 | verified |
| C10.2 | Error catalog with stable codes and fix pages (offline) | M23 | P1 | verified |
| C10.3 | Contextual help linking to offline docs | M19 | P1 | verified |
| C10.4 | In-app feedback saved locally, exported as a redacted bundle for email | M21 | P1 | verified |
| C10.5 | Voice control and spoken responses for accessibility; live-region announcements for streaming text | M17 | P1 | verified |
| C11.1 | **Source-hosting caveats to decide (verify current terms):** on GitHub's free plan, private repos may lack branch protection and advanced code/secret scanning; GitHub Pages for private repos may need a paid plan. Options: accept and use local pre-push hooks + gitleaks + signed commits; host the primary private repo on a free forge with protected branches (e.g. GitLab free tier or self-hosted Forgejo/Gitea) and mirror to GitHub; or consciously pay later (gate G6) | M1 | P0 | blocked |
| C11.2 | Security hygiene for the private repo: mandatory 2FA, signed commits, least-privilege tokens, Actions pinned by commit SHA, restricted Actions on forks (forks disabled), environment secrets with required reviewer for release publishing, access review checklist | M1 | P0 | blocked |
| C11.3 | **Source-leak incident runbook**: rotate keys, revoke tokens, take-down notices, history review, canary strings in source to trace leaks | M1 | P1 | verified |
| C11.4 | **REUSE-style licensing metadata** (SPDX headers incl. a custom `LicenseRef-Keel-Proprietary`), auto-generated `THIRD_PARTY_NOTICES` from lockfiles, license allowlist policy file in CI | M1 | P0 | verified |
| C11.5 | EULA acceptance stored locally with version; re-prompt when the EULA changes; EULA viewable in-app and on the website | M1 | P0 | verified |
| C11.6 | "Verified official build" indicator in About (app verifies its own hash/signature against the signed manifest); website page explaining how to recognize official downloads; typosquat/fake-site guidance | M22 | P1 | verified |
| C11.7 | Trademark usage guidelines page; takedown/abuse contact; export-control and privacy notes (lawyer review) | M23 | P2 | verified |
| C11.8 | Obfuscation depth (deterrent only): Nuitka-compiled core, bytecode-compiled Electron main, asar integrity, string encryption for sensitive constants, per-build canary identifiers | M22 | P1 | verified |
| C12.1 | Manifest fields for **blocked versions**, `min_version`, security advisories, and **staged rollout** (deterministic client bucket) with no server logic | M22 | P1 | verified |
| C12.2 | **Air-gapped install and update**: offline installer bundle, sideload update file verified by signature, model import from USB/folder | M22 | P1 | verified |
| C12.3 | Self-hosted APT and YUM repositories (static files, signed) | M22 | P1 | verified |
| C12.4 | Mirror list with automatic failover and signature check on every mirror | M22 | P1 | verified |
| C12.5 | Portable zip builds for Windows and Linux | M22 | P2 | verified |
| C12.6 | Release dry-run command that builds everything and runs the artifact allowlist and secret scans without publishing | M22 | P0 | verified |
| C13.1 | Local SWE-task benchmark suite (small repos with failing tests) with per-model leaderboard | M21 | P1 | verified |
| C13.2 | LLM-as-judge with a local judge model plus trajectory scoring (steps, wasted calls, cost) | M21 | P1 | verified |
| C13.3 | Prompt regression tests across model versions; golden transcripts | M25 | P1 | verified |
| C13.4 | Installer smoke tests in clean VMs per OS and architecture, including upgrade from every prior release and rollback | M22 | P1 | verified |
| C13.5 | Startup, memory and install-size trend charts stored per release | M21 | P1 | verified |
| C2.1 | **Keel Cowork** (knowledge work) | M15 | P1 | verified |
| C2.2 | **Keel Code** | M11 | P1 | verified |
| C2.3 | **Keel Duet** (assumed pair mode, confirm D4) | M12 | P1 | verified |
| C2.4 | **Fleet** | M12 | P1 | verified |
| C2.5 | Surface switcher with per-surface default agents, tools and permissions | M19 | P0 | verified |
| C3.1 | **Best-of-N with test selection** | M7 | P0 | verified |
| C3.10 | Uncertainty policy | M7 | P1 | verified |
| C3.11 | Style learning | M11 | P2 | verified |
| C3.12 | Context packs and a **context budget UI** | M19 | P1 | verified |
| C3.2 | **Doom-loop and stuck detector** | M4 | P0 | verified |
| C3.3 | **Goal mode / overnight mode** | M14 | P1 | verified |
| C3.4 | Think-harder slider | M19 | P1 | verified |
| C3.5 | Planner / critic / executor roles | M7 | P1 | verified |
| C3.6 | Map-reduce refactors | M12 | P1 | verified |
| C3.7 | **Reflection with approval** | M13 | P1 | verified |
| C3.8 | Failure postmortems stored per project | M13 | P2 | verified |
| C3.9 | Cost and time **estimate before run**, with confidence | M21 | P1 | verified |
| C4.1 | **Debugger integration via DAP**: breakpoints, step, inspect, so the agent can debug for real | M11 | P1 | verified |
| C4.10 | **Remote targets**: run on the user's SSH servers, WSL, devcontainers; remote daemon over SSH tunnel | M20 | P1 | verified |
| C4.11 | Browser devtools tools (console, network, performance) and **visual diff** of UI before/after; screenshot-to-code | M16 | P1 | verified |
| C4.12 | Terminal session recording and replay | M21 | P2 | verified |
| C4.13 | Issue-to-change pipeline from a markdown backlog or the user's own tracker token | M15 | P2 | verified |
| C4.14 | Auto-generated architecture docs and diagrams kept in sync with code | M11 | P2 | verified |
| C4.2 | Symbol, call and dependency **graph** with impact analysis ("what breaks if I change X") | M11 | P1 | verified |
| C4.3 | Change-risk score and impacted-test selection | M11 | P2 | verified |
| C4.4 | Structural search and codemods | M11 | P1 | verified |
| C4.5 | Static analysis ingestion (SARIF in/out) | M11 | P1 | verified |
| C4.6 | **Project security scans for the user**: secrets (gitleaks), dependency CVEs (OSV), SBOM of the user's project, license-compliance report | M11 | P1 | verified |
| C4.7 | Profiling and benchmark agent | M11 | P2 | verified |
| C4.8 | Log/process/port inspector, docker-compose helper, service health probes | M5 | P1 | verified |
| C4.9 | Git extras: stacked commits, hunk staging, conflict resolver, blame-aware context, submodule and monorepo awareness, signed commits with the user's own key | M11 | P1 | verified |
| C5.1 | Deterministic (no-LLM) nodes, loop/map nodes, sub-workflows, typed inputs/outputs with JSON Schema | M8 | P1 | verified |
| C5.2 | Human-task node (wait for approval/answer, timeout and default) | M8 | P0 | verified |
| C5.3 | Workflow versioning, diff, test mode with mocked tools, run history and replay | M8 | P1 | verified |
| C5.4 | Triggers: file-watcher, folder "inbox" (drop files to process), git hook, email, clipboard, schedule | M14 | P1 | verified |
| C5.5 | Internal event bus exposed to plugins and hooks | M10 | P1 | verified |
| C5.6 | Notification rules: quiet hours, digests, per-channel routing; optional free push through a self-hosted or public ntfy-style service the user chooses | M14 | P1 | verified |
| C6.1 | Separate **episodic, semantic, procedural** memory | M13 | P1 | verified |
| C6.2 | Entity/relation knowledge graph alongside flat items | M13 | P1 | verified |
| C6.3 | Importance scoring and decay; "dreaming" consolidation job; per-agent vs shared scopes | M13 | P1 | verified |
| C6.4 | User profile page the person can read and edit | M13 | P1 | verified |
| C6.5 | Memory provenance (which session/tool produced it) and tainted-source flag | M13 | P1 | verified |
| C7.1 | Read other tools' instruction files as sources (`CLAUDE.md`, `.cursorrules`, Copilot instructions, `GEMINI.md`) with merge diagnostics; add a "not affiliated" note | M7 | P0 | verified |
| C7.2 | **Importers/exporters**: MCP configs from other apps, settings, rules, sessions where formats are documented | M20 | P1 | verified |
| C7.3 | Skill format compatible with the open `SKILL.md` convention; command format compatible with opencode-style markdown | M9 | P1 | verified |
| C7.4 | OpenAPI-to-tools generator (point at a spec, get tools, dormant until approved) | M15 | P1 | verified |
| C7.5 | Standards checklist: AGENTS.md, MCP, ACP, LSP, DAP, OpenTelemetry GenAI conventions, SARIF, CycloneDX, SPDX, OpenAPI, JSON Schema, ICS | M25 | P1 | verified |
| C8.1 | **Recoverable trash**: every agent delete goes to a Keel trash for N days; automatic git/stash snapshot before bulk operations | M5 | P0 | verified |
| C8.2 | Delayed destructive ops with undo window; **approve from phone** for dangerous actions | M20 | P1 | verified |
| C8.3 | Behavior anomaly detection (sudden mass file reads, unusual network, repeated denials) pauses the agent | M3 | P1 | verified |
| C8.4 | Honeypot/canary files that should never be read; alert if touched | M3 | P2 | verified |
| C8.5 | Plugin/skill supply chain: capability review UI with **permission diff on update**, trust levels (bundled, signed, local, unsigned), static scan of skill scripts, signed **revocation list** delivered via the update feed | M10 | P0 | verified |
| C8.6 | Content-addressable artifact store with dedupe and integrity checks | M4 | P1 | verified |
| C8.7 | DB resilience: scheduled integrity check, `VACUUM INTO` backups, **rebuild projections from the events log** after corruption, retention policies, optional SQLCipher encryption at rest (verify license/packaging) | M4 | P1 | verified |
| C8.8 | Local red-team suite (prompt injection, exfiltration, tool-abuse scenarios) run per model | M21 | P0 | verified |
| C9.1 | **Model manager**: load/unload idle models, VRAM/RAM budget, queue concurrent requests, warm-up | M2 | P0 | verified |
| C9.2 | Virtualized lists, incremental rendering, streaming backpressure, startup prewarm, memory-leak watchdog | M19 | P1 | verified |
| C9.3 | Incremental repo indexing with file watching; low-power/battery mode | M11 | P1 | verified |
| C9.4 | Per-feature resource caps (browser, LSP, container) with visible meters | M16 | P1 | verified |
| D1.1 | Every part is a plugin, including model adapter, tool registry, session log and the agent loop itself, each replaceable from configuration; "no privileged core to patch." | M10 | P0 | verified |
| D1.10 | Desktop shell: Electron ships the exact production runtime in signed resources, owns a reserved `desktop` profile, starts a private Desktop Host (Electron-as-Node), loads packaged web assets immediately and waits for boot injections before activating client plugins in the same document; OS-assigned port; Node IPC carries boot injections, readiness, fatal errors, shutdown; desktop and CLI share product data but keep packages, activation and lockfiles separate. | M19 | P0 | verified |
| D1.11 | Shell-owned UI runs plugin install/update transactions with the bundled package manager under normal user/profile config. | M10 | P1 | not_started |
| D1.12 | Core package map (session log, system-prompt assembly, tool registry + guarded pipeline, agent interface + live registry, agent loop driver, per-agent scope primitive, LLM vocabulary + adapter seam) each exposing one service key on the context. | M7 | P0 | verified |
| D1.2 | Registrations are reversible effects that unwind when their plugin unloads. | M10 | P1 | not_started |
| D1.3 | Profiles and bundles: a *profile* is a named composition (list of bundles, out-of-tree plugins, a user patch file); shipped templates `web`, `headless`, `sdk`, `sdk-minimal`, `acp`; a *bundle* is a distributable set of config rows + code. | unassigned | P1 | not_started |
| D1.4 | Layered composition order: bundles in order, then profile patch, then home patch, then `--patch` overlays; a patch targets a row by id (replace whole config) or inserts new rows; a `preset` patch edits inside a declaration's plugin list. | M2 | P0 | verified |
| D1.5 | `--dump-config`: prints the exact plugin tree the machine will boot; any printed row can be replaced by a patch. | M2 | P0 | verified |
| D1.6 | Config-only HMR plugin toggled per profile (on for web, off for headless/sdk/acp). | M10 | P1 | not_started |
| D1.7 | All supported apps launch only through named profiles; package bins, demos and SDK argv escapes are forbidden, and a gate (`verify-application-entrypoints`) classifies every executable and rejects bypasses. | M0 | P1 | not_started |
| D1.8 | SDK runtime wheel per platform bundles the normal CLI; the client launches `--profile sdk` with an explicit home dir; minimal example uses `sdk-minimal`; persistent external plugins installed through the plugin command, not a private config carrier. | M20 | P1 | not_started |
| D1.9 | Plugin management command reserved as `plugin` (not a profile name unless `--profile plugin`). | M10 | P2 | not_started |
| D2.1 | Three event domains: *session events* (durable facts in the log, broadcast), *agent events* (`agent/*`, live, observe/intercept in-flight work), *capability events* (`fs/*`, `tools/*`, `telemetry/*`, policy/adapters on a seam). | M8 | P0 | verified |
| D2.10 | Process-local live stream frames (`assistant-stream` start/chunk/end) vs durable settled message that embeds the compact timed stream; `assistant/attempt` retains failed/retried/cancelled attempts without adding model history. | M4 | P0 | verified |
| D2.11 | Model-visible ⇔ logged: every model request must be reconstructable from the log; any new model-visible input requires a session event; plugins that alter message content register pure message projections (detached readers supply the same). | M4 | P0 | verified |
| D2.12 | Session projection seam: registered units fold committed events; clients read selected views via `snapshot()`; domain services keep private handles and expose business methods. | M4 | P1 | not_started |
| D2.13 | Session format versioning with adjacent migrations: header-only `stat`/`list` pick the highest generation; read-open translates in memory; write-open publishes a new version-named successor beside the unchanged source; committed generations are never renamed, overwritten or deleted; each migration step is `vN → vN+1`; missing interrupted `turn/end` inserted only for a bounded released restart; compressed files (`.zstd`) supported. | M4 | P0 | verified |
| D2.14 | Persistence-provider interface (`create`/`open`/`stat`/`list`/`export`) so session storage backends are swappable. | M4 | P1 | not_started |
| D2.15 | Fork at a turn boundary (seeded session with inherited event count; only agent-loop-published sessions persist). | M4 | P0 | verified |
| D2.16 | Working directories supply user context and execution paths without changing project identity, sandbox write roots, or existing process dirs. | M5 | P0 | verified |
| D2.17 | Session title provider (single registered provider) and goals service (same-session objective continued through agent events). | M7 | P1 | not_started |
| D2.2 | Waterfall vs serial listeners: waterfall listeners must call `next()` to delegate (returning without it short-circuits); serial listeners have no `next()`. Waterfall hooks: pre-step, request, stream, three tool hooks. | M8 | P1 | not_started |
| D2.3 | Turn flow definition: step = one model request + the tools it calls; turn = zero or more steps; sequence `turn/start` → claim input → snapshot model selection → assemble prompt + tool schemas → pre-step hook (accept / rewrite / reject) → `step/start` → prepare call → stream → assistant message or failed attempt → `tool/call` → pre-execute → execute → post-execute → `tool/result` → `step/end` → loop or turn-stopping hook → `turn/end`. | M7 | P0 | verified |
| D2.4 | Rejected or empty first claim closes the turn without a step. | M7 | P1 | not_started |
| D2.5 | One inbox per agent driver; injected context (`agent.inject()`) waits for a waking message and lands in the next admitted request. | M7 | P0 | verified |
| D2.6 | Request series (`request/header`, `request/context`): the log marks when a new series of requests starts (surface replacement, image offload) so cache/context changes are explicit; retries do not repeat assembly. | M4 | P1 | not_started |
| D2.7 | System prompt travels as logged `system/message` history; empty text clears it. | M4 | P0 | verified |
| D2.8 | Cancellation during prompt preparation commits nothing (neither system nor user messages). | M4 | P0 | verified |
| D2.9 | Failed steps record missing tool results (synthetic). | M4 | P0 | verified |
| D3.1 | Capability seam = Service Definition + Service Provider + Consumer; one role alone is not a seam; adding a capability means designing all three. | M0 | P0 | verified |
| D3.10 | Filesystem policy through `fs/*` events on top of providers. | unassigned | P1 | not_started |
| D3.11 | Packages Keel is missing or underspecified (from the 60+ dsh package groups): `deliverables` (turn deliverables), `spill` (output spill), `attachment`, `guard` (loop/tool guards), `extensions` (runtime self-modification), `feedback` (human feedback), `identity` (anonymous identity), `workspace` (workspace entities), `plan` (logged planning), `schedule` (scheduled follow-ups), `ptc-runtime` (programmatic tool-call execution, meaning to be verified), `session-query` (browse/search/export), `typert` (type graph for RPC), `liveshare`, `inspector`, `experimental` quarantine. | M7 | P0 | verified |
| D3.12 | `deliverables`: each turn can attach named deliverables (files, summaries) shown as a result card. | M7 | P1 | not_started |
| D3.13 | `spill`: large tool output spills to a file with a preview (matches Master rule 5). | M5 | P0 | verified |
| D3.14 | `guard`: loop and tool guards as their own plugin group. | M4 | P0 | verified |
| D3.15 | `extensions` (runtime self-modification) group. | M9 | P1 | not_started |
| D3.16 | `feedback` (human feedback) group. | M19 | P1 | not_started |
| D3.17 | `identity` (anonymous identity) group. | M3 | P1 | not_started |
| D3.18 | `workspace` entities + `session-query` (browse/search/export). | M4 | P0 | verified |
| D3.19 | `plan` (logged planning) and `schedule` (scheduled follow-ups). | M7 | P1 | not_started |
| D3.2 | One provider swap changes the whole product: filesystem and subprocess providers share one execution world, so pointing them at a remote sandbox moves bash, PTY and LSP together. | M5 | P0 | verified |
| D3.20 | `experimental/` quarantine: capabilities under evaluation with no product-support commitment, independent of optional delivery; non-experimental packages need product use or explicit classification (policy file). | M0 | P1 | not_started |
| D3.21 | `llm-pi-ai` generated provider metadata with a check that rejects stale generated data without rewriting files. | M2 | P1 | not_started |
| D3.22 | Inspector (DevTools-style frontend) compiled locally from a pinned source package; no network or browser download at build; published packages contain the built frontend. | M21 | P1 | not_started |
| D3.23 | Live Share (experimental): viewer carrier in the browser + node wire codecs. | M20 | P2 | not_started |
| D3.3 | Subagent providers behind one interface: from a fresh child agent to a delegated turn in another product. | M12 | P1 | not_started |
| D3.4 | Agent Teams: when enabled for a root session, adds task policy and a shared task board; subagent controls own identity, messaging, discovery, interruption, inbox waiting. | M12 | P1 | not_started |
| D3.5 | Agent presets compose a different capability set for one session; a service row inside a preset needs an `isolate` realm. | M7 | P1 | not_started |
| D3.6 | Human commands registered on a commands service dispatch without a model turn. | M7 | P0 | verified |
| D3.7 | Background jobs service with `job_*` tools to read/stop jobs. | M5 | P0 | verified |
| D3.8 | Webhook runtime: a *trusted rule* starts a session from an external webhook; provider adapters mount beside it. | M15 | P0 | verified |
| D3.9 | Shell backend, terminals backend, sandbox backend as separate services; sandbox wraps argv before spawning. | M5 | P0 | verified |
| D4.1 | Model setup in Settings → Models: enter key, save, route usable immediately without restarting. | M19 | P1 | not_started |
| D4.10 | UI design/review entry point as a reusable skill file (design principles + references loaded on demand). | M0 | P1 | not_started |
| D4.11 | Plugin Manager UI in the base bundle for Web and agents. | M10 | P0 | verified |
| D4.12 | Desktop window loads packaged assets immediately and activates client plugins after readiness. | M19 | P1 | not_started |
| D4.13 | Port selection: web UI default fixed port, desktop OS-assigned, overridable by profile config. | M20 | P1 | not_started |
| D4.2 | Custom OpenAI-compatible endpoints documented as a first-class path. | M2 | P0 | verified |
| D4.3 | Workspace required: "Choose workspace" flow; composer is unavailable until a workspace is selected; fresh UI has none selected even though the process has a default directory. | M19 | P1 | not_started |
| D4.4 | In-page directory picker vs native picker; an overlay config pins the in-page picker for automated browser tests/GIF recording. | M19 | P1 | not_started |
| D4.5 | Web client Chat nodes: extensible `ConversationNodeDefinition` + keyed renderer so plugins add new message/node types. | M19 | P1 | not_started |
| D4.6 | Settings cards contributed by plugins (cookbook "adding a settings card"). | M10 | P1 | not_started |
| D4.7 | Tool UI presentation designed up front: host presenters are pure; web cards derive from raw events and persisted result metadata. | M5 | P0 | verified |
| D4.8 | Client UI copy is locale-owned: product text only through typed dictionaries/`t()`; a gate rejects hardcoded copy; English copy and plugin titles use sentence case. | M19 | P1 | not_started |
| D4.9 | Official plugin artwork policy: bundled plugins use a consistent icon set; new glyphs need designer approval. | M19 | P2 | not_started |
| D5.1 | Plain statement that the software executes model-generated code/commands, loads third-party plugins, and accesses network, processes, credentials and files; defects, misconfiguration, malicious input or untrusted plugins can damage the host. | M19 | P0 | verified |
| D5.2 | "Sandboxing, approvals and permissions reduce risk but do not guarantee isolation"; do not rely on it as the sole control for untrusted workloads. | M19 | P0 | verified |
| D5.3 | Responsible-use list: least privilege; disposable VM/container; keep backups; don't expose sensitive credentials; review plugins, config and proposed commands. | M19 | P0 | verified |
| D5.4 | No warranty / no liability paragraph referencing the license. | M1 | P0 | verified |
| D5.5 | Host sandbox failures rule (builder): if a required command fails because the dev sandbox blocks credentials/network/IPC, retry unchanged with the narrowest escalation, require evidence of the sandbox cause, and never bypass test failures or the product sandbox. | M0 | P0 | verified |
| D6.1 | Pre-stable APIs: update every consumer when a public API changes; record each externally perceptible breaking change immediately in an upgrade guide; SQLite uses a monotonic `SCHEMA_VERSION`. | M0 | P1 | not_started |
| D6.10 | Source plane vs artifact plane never mixed: tests/gates resolve imports to source and pass on a clean tree; gates that need built output declare that dependency. | M0 | P1 | not_started |
| D6.11 | Structured, typed errors (`KeelError` with code); stop dependent work and visibly report untrusted state or unknown outcomes; empty `except` blocks must name the error and why and contain one statement. | M0 | P1 | not_started |
| D6.12 | Comments: local and non-restating; document behavior, failure, timing, ownership, safe use; every public export has a docstring with params/returns; word budgets for docs. | M0 | P1 | not_started |
| D6.13 | Docs accompany code: update README/docstrings in the same change. | M0 | P1 | not_started |
| D6.14 | Tests describe behavior, not "correctness"; change obsolete behavior together with its tests and explain why. | M0 | P1 | not_started |
| D6.15 | Every non-trivial model- or user-visible change updates a keyless recorded-session snapshot; fixtures replay on macOS and Linux (and Windows); fix fixtures, not normalizers. | M25 | P1 | not_started |
| D6.16 | Both SDKs project the loop: loop/session-lifecycle/event-map changes update the Python and TypeScript SDK expected outputs in the same change. | M20 | P1 | not_started |
| D6.17 | Agent Notes (ADR-like) only for durable decision rationale; archived notes frozen, never edited or treated as current authority. | M0 | P1 | not_started |
| D6.18 | Prefer maintained dependencies over hand-rolling when they delete owned code and tests. | M0 | P1 | not_started |
| D6.19 | Vendoring policy: vendored packages are pinned source copies with a manifest of upstream SHAs; changes require a manifest update (pre-commit guard); local modifications are logged and re-applied or retired on sync. | M0 | P1 | not_started |
| D6.2 | Plugins, not loop changes: new behavior attaches to documented extension points; changing the loop requires updating the architecture doc. | M0 | P1 | not_started |
| D6.20 | Run only relevant checks locally: match evidence to the change (focused tests, snapshots, doc-sync, built smokes, real-provider e2e); CI owns exhaustive coverage; don't repeat a passing check for commit/push. | M0 | P1 | not_started |
| D6.21 | PR hygiene: one `kind/*` and all material `area/*` labels; rewrites use force-with-lease only; PR description template. | M0 | P1 | not_started |
| D6.22 | TODO markers by urgency: `FIXME` (blocks release), `TODO` (soon), `XXX` (someday). | M22 | P1 | not_started |
| D6.23 | Defensive-patterns doc read before touching package surfaces, remote services, client state, conversation/session behavior, lifecycle/concurrency/subprocess/teardown code. | M0 | P1 | not_started |
| D6.24 | Strict typing everywhere; any remaining dynamic type explains why. | M0 | P1 | not_started |
| D6.25 | Machine-checkable invariants wired into an executed top-level gate and each gate proven to reject an invalid case; narrow justified exceptions instead of disabling rules globally. | M0 | P1 | not_started |
| D6.3 | Typed events with documented mode and payload fields; closed unions end in an exhaustive check (`assert_never`); extensible unions use a documented default. | M8 | P1 | not_started |
| D6.4 | Explicit over implicit at package boundaries: defaults are applied in an explicit `resolve(request) -> Spec` step, never a hidden `or default` inside `run()`. | M0 | P1 | not_started |
| D6.5 | No hardcoded tunables in plugins: deployment-varying choices are validated config fields; constants stay for protocol, external specs and security invariants. | M2 | P1 | not_started |
| D6.6 | Misconfiguration fails loud at load (or earliest resolvable point); never silently skip a missing referent. | M2 | P1 | not_started |
| D6.7 | Opaque cross-boundary ids are branded types (`NewType`), never bare `str`. | M0 | P1 | not_started |
| D6.8 | Trust types inside the process; validate at boundaries (parser/config, queued messages, model/tool JSON, durable files, worker/process/wire). Don't add hostile-input tests for values the static interface already requires. | M0 | P1 | not_started |
| D6.9 | No new casts to `Any`/`object` beyond the recorded baseline; replace with typed values or validation. | M0 | P1 | not_started |
| D7.1 | Gate scheduler (`run-gates`): all gates as a dependency graph; bounded concurrency env var; fail-fast switch; a failure skips only its dependents so independent errors all report. | M0 | P0 | not_started |
| D7.10 | Hooks: worktree-local git hooks installed by a script; pre-commit = staged lint profile with fix + bounded retry, whitespace check, generated-metadata check, vendor manifest guard; pre-merge-commit check; pre-push = typecheck. Hooks deliberately don't run tests/builds; opt-in `check:all`. | M0 | P1 | not_started |
| D7.11 | Doc gates: doc-sync aggregate, doc typecheck (compiles code fences), type-equiv (documented type declarations pasted into docs are verified against source by a gate), docs site build doubles as dead-link check, translation pairing records with merge-conflict repair command. | M0 | P1 | not_started |
| D7.12 | CI layout: broad lanes of independent gates, a smaller Node-version compatibility matrix, native Windows lane in a separate workflow, Python checks separate, required benchmarks on standard hosted Linux, real-API e2e in its own workflow, partitioned coverage using per-platform timing data. | M0 | P0 | not_started |
| D7.13 | Per-file 100% coverage gate on package sources in CI (separate from the normal test command). | M25 | P1 | not_started |
| D7.14 | Test taxonomy rules: real-API e2e self-skip without key; "expected" tests are owner-local process expectations; snapshot tests replay recorded sessions through shipped profiles without a key, with a `record` mode that needs a key. | M25 | P1 | not_started |
| D7.15 | Release rehearsals: dependency-layout rehearsal and pack rehearsals (build packages exactly as release does) run credential-free; self-hosted runner failover only for trusted events (non-fork, non-bot PRs); manual publish stays hosted. | M22 | P1 | not_started |
| D7.16 | Package hygiene checks: `publint`-style entrypoint validation and a clean "consumer" import check against built declarations. | M22 | P1 | not_started |
| D7.17 | Windows signing docs as required reading for packaging; desktop packaging profile per signing mode. | M22 | P2 | not_started |
| D7.18 | Update-time breaking-change notice: release carries the upgrade guide entries since the installed version. | M22 | P1 | not_started |
| D7.19 | Benchmark method: drive tasks through the SDK's minimal JSON-RPC agent variant with separate workspaces and session ids per independent task. | M21 | P0 | not_started |
| D7.2 | Worker budgets differ locally vs CI (local capped because container CPU counts mislead). | M0 | P2 | not_started |
| D7.20 | Labels taxonomy and stacked PRs (native stacks, merge-forward vs rebase). | M0 | P2 | not_started |
| D7.3 | Separate type-check programs for two faces (host and client) because both declare the same keys with different services and would collide in one program. | M0 | P1 | not_started |
| D7.4 | Typed remote-call contract generation: services declare callable methods with a decorator; the build generates client-side types and runtime contributions. | M20 | P1 | not_started |
| D7.5 | Build order: native addon → contract generation → compile host → bundle → compile client → bundle client → web; `build:check` verifies tests/scripts against the already-built output and does not rebuild. | M22 | P1 | not_started |
| D7.6 | Embedded build identity: version + short commit + dirty marker; `official` build omits the dirty marker; a gitignored build record binds exact public values to the output and release packing rejects a missing/stale record. | M22 | P1 | not_started |
| D7.7 | Local vs official build profiles (`--profile local` keeps version/commit/dirty, discards inherited branding overrides). | unassigned | P1 | not_started |
| D7.8 | Windows and WSL guidance: keep checkout and toolchain in the same OS environment; install deps separately per environment; Windows behavior needs native validation. | M0 | P1 | not_started |
| D7.9 | Strict dependency linker so undeclared deps fail; build scripts of dependencies explicitly allowlisted. | M0 | P0 | not_started |
| E1.1 | Every tool declares a mandatory canonical output (JSON schema), returns one lossless JSON value, and a pure render(args, value) produces the model-facing content. Callers never parse prose for ids. | M5 | P0 | verified |
| E1.10 | Concurrency classifier isConcurrencySafe(args): pure, only true opts in; anything else (omission, exception, invalid) is exclusive; loop forms exclusive barriers and rolling-pool parallel runs; batch override maxParallelToolCalls. | M5 | P0 | verified |
| E1.11 | Executor contract: one outcome per input call in input order (skipped calls on abort included); never settles while started work still runs; internal failure drains then rejects with a typed batch error preserving committed outcomes. | M5 | P0 | verified |
| E1.12 | Per-scope tool restriction (allow / deny lists) that intersect; scoped registrations stay exempt; deny-only admits later tools, allow-list excludes them. | M7 | P0 | verified |
| E1.13 | Conditional tool activation (when) evaluated once per step with the captured model selection; the resulting admitted set governs declarations *and* every call in that step; disposed after the batch; late results cannot restore removed tools. | M5 | P1 | verified |
| E1.14 | Stable error vocabulary: INVALID_ARGS, INVALID_TOOL_OUTPUT, UNKNOWN_TOOL, ABORTED, ABORTED_BEFORE_DISPATCH, TOOL_TIMEOUT, APPROVAL_REJECTED/CANCELLED/UNAVAILABLE, TOOL_CONTEXT_UNAVAILABLE; error info = name + code + optional raw reason that is kept durably but never in model-facing content. | M5 | P0 | verified |
| E1.15 | Expected failures are typed errors with stable codes; successful domain outcomes (e.g., non-zero exit) are values, not exceptions. | M5 | P1 | verified |
| E1.16 | conclude_turn() marker lets a successful tool end the turn; composites forward it only from authoritative nested success. defer_context() attaches context to a result that the loop appends only after the result. | M5 | P1 | verified |
| E1.17 | agent.inject() messages carry a typed source kind; old untyped wrappers rejected at admission. | M7 | P1 | verified |
| E1.18 | Long-running work: background start returns a typed handle ({kind:'background', job_id}); job spec has synchronous cancel, non-rejecting done that settles after cleanup, and output source; after publishing the id, use a task-owned cancel signal, not the call's; cancellation of the call stops waiting but does not kill published work; job_kill/owner disposal/teardown own that lifetime. | M5 | P0 | verified |
| E1.19 | Programmatic tool-call (PTC) mode: every visible tool callable as await tools.name(args); generated arg/output type maps; calls re-enter the normal pipeline; success returns the canonical value after policy; failure rejects with a limited error (name, tool name, message only). Intermediate values are execution-local, not persisted; only the outer run_code call crosses the output cap and spill pipeline; model-direct calls to native names are denied while PTC executor is selected; run_code is a reserved name. | M5 | P1 | verified |
| E1.2 | Model-facing schema built by explicit allowlist (name, description, parameters only); execution, timeout, presenters, concurrency flags never leak into a request. | M5 | P0 | verified |
| E1.20 | ptc-dispatch-log hook lets spill policy shorten only the durable log copy of a sub-call result (program already got the full value). Sub-call start/settle events store only ids, name, normalized args. | M5 | P2 | verified |
| E1.21 | Executor-owned prompt sections: guidance registered and disposed with the executor. | M7 | P1 | verified |
| E1.3 | One schema vocabulary for params and outputs (scalars, arrays, objects with explicit additionalProperties, exact-one oneOf, enum/const), with inferred types; mismatch → INVALID_ARGS; invalid output → INVALID_TOOL_OUTPUT. Unsupported JSON Schema keywords are rejected, never silently ignored. | M5 | P0 | verified |
| E1.4 | Args are deep-frozen and snapshotted as lossless JSON before policy runs; args cannot be rewritten later because history, audit, UI and execution must agree. | M5 | P0 | verified |
| E1.5 | Pre-execute decisions: allow, deny (reason + optional structured error id), cancel, ask (audited reason + optional localized display reason); only allowed-once proceeds; missing approval channel or agentless call = denial. | M3 | P0 | verified |
| E1.6 | Guards are monotonic: a final guard can only deny, never allow, so listener order cannot turn a denial into permission. | M3 | P0 | verified |
| E1.7 | Post-execute decisions: accept, replace *content* or replace *value* (never both), attach context for the next request, or block with corrective feedback. Content replacement is presentation, not confidentiality; confidentiality needs block/replace-value. | M3 | P0 | verified |
| E1.8 | Around-dispatch wrapper for timeout/retry/metrics may replace but not remove the cancellation signal; the registry re-fuses the caller's signal. | M5 | P0 | verified |
| E1.9 | Cooperative per-tool timeout (timeoutMs): declaring it asserts the tool forwards the cancel signal and reaches quiescence; never sent to the model; result error code TOOL_TIMEOUT. | M5 | P0 | verified |
| E2.1 | Presenters are pure (present_call(args), present_result(args, result)), run on live stream and log replay, no I/O/clock/session state; malformed or old args fall back to a generic card and display must never crash a replay. | M5 | P0 | verified |
| E2.2 | Card kinds: generic (title, icon kind: read/edit/delete/move/search/execute/fetch/other, file locations), terminal (command; result adds raw output, exit code, signal), diff (path, old text or null for new file, new text), search (matches grouped by file or flat paths, with truncated/total so partial results are never shown as complete), read (path, 1-based offset, numbered lines, total lines, language hint), web (search sources/answer/truncated; fetch url/status/truncated). Completed view replaces pending; search/read/web have no call-time card. | M19 | P1 | verified |
| E2.3 | Durable presentation metadata (presentation_meta(args, value)) stored on the result so replay shows hunks/search facts without persisting the canonical value; skipped for nested code-mode calls. | M4 | P0 | verified |
| E2.4 | UI-only formatting stays out of model-visible output (fenced console blocks, relativized paths, diffs). | M5 | P1 | verified |
| E2.5 | Web client derives tool cards from raw events via a keyed slot per tool name, validates wire values locally and falls back to the generic row; no separate presenter registry; no host code imported into the browser bundle. | M19 | P1 | verified |
| E3.1 | One activation API for local children and external executions; provider capability flags (agent_options, agent_preset, output_schema, depth_limit) validate start options before anything starts. | M12 | P1 | not_started |
| E3.10 | Interrupt authority: only the user or an exact live ancestor; fire-and-return; preserves unclaimed inbox, the activation and descendants; claimed work not requeued; absent target is a no-op. | M12 | P1 | not_started |
| E3.11 | Whole-tree drain and wait-for-tree-work (idle members with parked input stay resident without delaying host completion). | M12 | P1 | not_started |
| E3.12 | Parent-owned subagent catalog projection (membership at creation, no execution status); recursive list_descendants with parent id, depth, path and per-branch diagnostics (unsupported, corrupt, unavailable); cycles/repeats skipped; unreadable branch stops only that branch; historical children with unavailable descriptors listed as unknown mode with no continuation rights. | M12 | P1 | not_started |
| E3.13 | Subagent model-route setting: default-off allowlist of provider/model routes the agent may choose for children; reads live on each delegation; malformed/duplicate routes error. | M12 | P1 | not_started |
| E3.14 | User-authored message to a child from the UI with attachments (image parts admitted via attachment store; model must accept images) and client time zone; cold resume at capacity rejects with a typed delivery-unavailable. | M12 | P1 | not_started |
| E3.15 | Lifecycle events subagent/start, subagent/end (scoped to tree root), provider added/removed. | M8 | P1 | not_started |
| E3.2 | Result delivery policy: parent (notifies the model) vs caller (only returns result, e.g., workflows/code mode). | M12 | P1 | not_started |
| E3.3 | Agent names: 1 to 32 lowercase letters/digits/hyphens starting with a letter, not lead; default agent-N; root is lead; full names are slash paths; names are model-facing references, session ids are the authority; resolve returns the id and grants no permission; a slash path with no match fails AGENT_NAME_NOT_FOUND. | M12 | P0 | not_started |
| E3.4 | Child working directory chosen at admission (relative resolves against the parent's current dir); local child keeps the parent's original project; resumed child retains logged directory state. | M12 | P1 | not_started |
| E3.5 | Local child = durable session with at most one live activation; manager owns identity/capacity reservation, input admission, cold resume, child-first disposal; structured-output capture closes input for that activation; resume does not inherit the schema. | M12 | P1 | not_started |
| E3.6 | Spawn vs Fork: fork seeds the child with the parent's completed-turn prefix (contiguous, lossless, balanced steps), spawn starts fresh; inherits_parent_context is descriptive for wording only. | M12 | P1 | not_started |
| E3.7 | External backends as providers (separate coding CLIs or protocol agents): one execution, no follow-ups, results to creator only while online. | M12 | P1 | not_started |
| E3.8 | Result object: final output = last non-empty assistant message; optional structured value validated against the requested schema; diagnostic text limited to 4,096 bytes and free of tool inputs, file contents, env values, credentials, raw protocol payloads; stop reason enum (completed, aborted, error, max-tokens, refusal). Child failure resolves with error, not an exception. | M12 | P0 | not_started |
| E3.9 | Messaging within one tree: running target gets *steer*, absent target cold-resumes, sender identity rechecked, accepted messages never retracted. Two distinct message source kinds: agent-message (relay: words the sender chose) vs subagent-settled (runtime notice about how a child ended) so a child is never credited with words it didn't write. | M12 | P1 | not_started |
| E4.1 | HMR-safety test for every registry: dispose the contributing scope, assert cleanup. | M10 | P0 | verified |
| E4.10 | Mock only the expensive/non-deterministic boundary (model, network, clock); keep the real tool registry, pipeline and persistence behind the scripted mock; recovery tests separate pre-chunk vs post-chunk failures and prove failed chunks derive no message or tool side effect; cover exhaustion, cancellation, policy composition, persistence, status, wire counts, transport-closing idle timeouts, and shipping loader composition. | M25 | P0 | verified |
| E4.11 | Verify the world, not the agent's self-report: re-run the command or re-read files externally; assert untouched files are byte-identical; e2e tests create and dispose their own resources even on failure; shared fixtures live in plain helper modules, never in another test file. | M21 | P1 | verified |
| E4.12 | Real-composition tests for product-visible plugins: boot a test-only config through the real loader, mock only external services, assert model-visible request/log, durable state or user-visible output; prove each guard fails when the regression is introduced (red-green-revert). | M10 | P0 | verified |
| E4.13 | Test the published artifact entry path: run built entrypoints under the plain runtime; assert a genuinely missing config exits non-zero; singleton modules shared across bundles get a built-scope test. | M22 | P1 | not_started |
| E4.14 | Test resolution: tests resolve imports to source; built artifacts used only by explicit built-mode tests; subprocess tests run built output through one shared launcher. | M25 | P1 | not_started |
| E4.15 | Every non-trivial model/protocol/human-visible change updates a keyless recorded-session scenario; new capability seams and lifecycle variants name every required test tier at plan time. | M0 | P0 | not_started |
| E4.2 | Permanent contract-regression specs for the agent loop. | M25 | P0 | verified |
| E4.3 | Coverage gate philosophy: an uncovered line is often dead code to delete; line coverage is necessary, never sufficient; environment-dependent files exempted locally but enforced on CI that has the tool. | M25 | P1 | not_started |
| E4.4 | Performance benchmark gates as required PR checks: timed code runs on the plain runtime (never a transpiler); synthetic inputs enforce time, heap and scaling budgets; package-local perf files are diagnostic only. | M21 | P1 | not_started |
| E4.5 | Snapshot scenarios: parent/child session files with version in filename that must agree with header; snapshot.yml declares profile, header class, recording policy, workspace facts; typed tokens keep parent/child identity relations; mutating scenarios compare a full workspace.expected/ tree that record/refresh never rewrite; modes record (needs key), refresh (replay input still valid), review every diff; CI read-only replay. | M25 | P0 | not_started |
| E4.6 | Fixtures omit sequence/time envelopes (replay synthesizes them); historical fixtures keep released representation with explicit format owners for migration coverage. | M25 | P1 | not_started |
| E4.7 | Browser snapshot lane: UI output compared in Chromium, with the model picker also in WebKit; replay-only in CI. | M25 | P1 | not_started |
| E4.8 | Test-process isolation rules: forked workers share ports, paths, namespaces and children; each test owns every resource it acquires through teardown; a spec that passes only alone is a test defect; fork-exit diagnostics report PID, file, code, signal; flake-diagnosis workflow classifies probabilistic failures. | M25 | P0 | not_started |
| E4.9 | Smoke tests boot the shipped profile, send one prompt, and check the world (catches "green unit tests, broken product"); postmortems are documented (postmortem/0001-*). | M25 | P1 | verified |
| E5.1 | No listening port in the desktop app: the backend runs as a bundled child; framed byte pipes carry requests and streaming responses with backpressure, Node IPC carries only lifecycle control, a custom app:// protocol serves client assets. | M19 | P0 | verified |
| E5.10 | Shell copy localized from app locale (menus, native dialogs, plugin window share one locale payload; falls back to English); i18n gate also checks desktop shell sources. | M19 | P1 | not_started |
| E5.11 | Isolated development home (data, project and browser data under a disposable folder); debug ports configurable by env; DevTools auto-open toggle; dev overrides ignored by the packaged app. | M19 | P1 | not_started |
| E5.12 | Per-target build isolation: each target owns its inputs, prepared runtime, seed and artifacts under targets/<target>/; shared download cache verified by name+hash; a target never consumes another's mutable state. | M22 | P0 | verified |
| E5.13 | Release prerequisite env validation (app id format; reject malformed identity values; incomplete credential sets). | M22 | P1 | not_started |
| E5.14 | Packaging never receives upload credentials (stripped from subprocesses); a target completion record is written only after every build/sign step succeeds. | M22 | P0 | verified |
| E5.15 | Upload guard: uploader requires the completion record to match environment, target, public URL and version, and checks artifact names, sizes, SHA-512 before it reads credentials; uploads immutable versioned artifacts first, channel metadata last with no-cache; never deletes historical objects. Stable vs prerelease channel files. | M22 | P0 | verified |
| E5.16 | Test vs production update environments with distinct origins. | M22 | P1 | not_started |
| E5.17 | Signing/notarization steps: hardened runtime + timestamp on every embedded executable; deep strict signature check rejecting unexpected authorities; DMG notarized and stapled by an artifact hook; Windows hardware-token EV signing with PIN never persisted and diagnostics redacted. | M22 | P2 | not_started |
| E5.18 | Linux is not a supported desktop release target in dsh; Keel supports it (AppImage/DEB/RPM). | M22 | P1 | not_started |
| E5.19 | Known-limitations section in the desktop README (features disabled in desktop because they need a server; shared vs separate state; release qualification needs production environment). | M26 | P1 | not_started |
| E5.2 | Release identity: shell and backend always carry the same exact version; a backend upgrade is a desktop release; no independent versions. | M22 | P1 | not_started |
| E5.3 | Bundled runtime, never system runtime or package-manager state (and never the shell's own runtime for the backend). | M22 | P1 | not_started |
| E5.4 | Process-lifetime single-instance lock acquired before any profile access; the desktop app exclusively owns its profile directory; CLI and desktop share product data (sessions, settings, credentials, workspaces) but never executable packages, plugin activation, lockfiles or site-packages. | M19 | P0 | verified |
| E5.5 | Transactional activation: install in staging → boot a full backend health check → replace the active profile only after success; journal + one rollback profile; recovery combines the journal with the actual directories; a transaction lock records the current owner (including an orphaned worker) so a live worker isn't treated as stale. | M10 | P1 | not_started |
| E5.6 | Seed store packaging: offline seed archive of dependencies in 16 deterministic uncompressed shards so the outer installer compresses them and differential updates reuse unchanged shards; verified by an offline install before shipping; seed extraction on first run (measure disk use separately from installer download size). | M22 | P1 | not_started |
| E5.7 | Update unit: shell + matching backend seed + runtime form one signed update unit; update check 10 seconds after the main window opens plus a manual "Check for updates…" menu item; native confirmation dialog; waits for an in-flight check; verifies, stops backend, installs; next launch reconciles. | M22 | P1 | not_started |
| E5.8 | Plugin management window is a separate renderer receiving only structured list/install/remove/update operations: no filesystem, raw IPC, shell, or arbitrary package-manager arguments. | M10 | P1 | not_started |
| E5.9 | Plugins with install-time lifecycle scripts are rejected unless in a reviewed allowlist. | M10 | P0 | verified |
| E6.1 | Keys are write-only: the UI receives a redacted descriptor, never the secret; settings store only a credential reference; masked preview rule (identifier prefix, 5 leading and 4 trailing characters only when at least 8 middle characters remain hidden, else all dots; Unicode code points). | M3 | P0 | verified |
| E6.10 | Request-compatibility switches (supports_developer_role, max_tokens_field, thinking_format, ...) at route level with per-model field-by-field override; empty value refused, unknown name refused with the list of valid names; each switch valid only for protocols that declare it. | M2 | P0 | verified |
| E6.11 | Troubleshooting keyed by error code/symptom (missing credential, unknown model, 401 on discovery, gateway refuses every request, only reasoning models fail, Effort menu absent, off doesn't stop thinking, image refused vs provider rejects image, stale image stays in session log until a new session). | M23 | P1 | not_started |
| E6.12 | "Open configuration file" button next to settings for advanced fields, adapters re-read config on the next request (no restart). | M2 | P1 | not_started |
| E6.13 | Client-upgrade-required error naming the version to install when a model needs a newer app. | M2 | P2 | not_started |
| E6.14 | Config generated reference (config-catalog.md) derived from source so it can't drift; links from the UI to field docs. | M23 | P1 | not_started |
| E6.2 | Saved key edit rules: no reveal/copy/partial edit; typing replaces the whole key; Backspace/Delete stages whole-key removal, applied only on Apply; Cancel preserves; if deletion succeeds but settings fail, show a warning that deletion cannot be undone and offer retry; clearing a shared credential warns that it affects every feature using the reference. | M19 | P1 | not_started |
| E6.3 | Environment-credential hints: green = env var detected, yellow = none detected, "unconfirmed" = status read failed; detection never validates the credential; provider-managed credential files are outside the check. | M19 | P1 | not_started |
| E6.4 | Model list follows the provider's published list (loads on first need, refreshes in the background about every 10 minutes while in use, falls back to built-in); editing the list switches to a pinned custom list; "Restore defaults" re-follows. | M2 | P1 | not_started |
| E6.5 | Third-party provider picker from an installed catalog (endpoint, protocol, models) vs Custom model API form: permanent lowercase provider ID, base URL, protocol, credential, models; four protocols (OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, Gemini API); one protocol per provider (a gateway that serves two needs two providers); renaming = add new + delete old. | M2 | P0 | verified |
| E6.6 | Model discovery: GET /models with a searchable picker (existing models pre-ticked; tick to add, untick to remove; "Update list"); configured models the endpoint doesn't list stay; nothing saved until Save; failures fall back to manual entry; built-in provider always answered from the catalog. | M2 | P1 | not_started |
| E6.7 | Model picker behavior: selecting also sets the default for new sessions; a session keeps the model recorded in its own log; drag-to-reorder with keyboard up/down alternative; deleted default provider → composer shows "Select model" and blocks input. | M19 | P1 | not_started |
| E6.8 | Per-model capability fields: input types (text, image), context window, max output tokens; route-level defaultInput fallback (never removes images the catalog knows), per-model override; "claims about your endpoint are not verified" warning; image-capable list clears image limits when image is removed. | M2 | P0 | verified |
| E6.9 | Reasoning-effort declarations per model: levels with the API value sent for each (off may be empty = send nothing), route default, picker choice saved with model as default; thinking-format switch for models that think unless told not to; models can drop levels; unsupported effort refused as UNSUPPORTED_REASONING_EFFORT; Effort menu hidden when no levels declared. | M2 | P0 | verified |
| E7.1 | tokenMeter: isolated per-session replay folds; pressure consumers share immutable revisioned measurements. | M4 | P1 | not_started |
| E7.10 | sessionTitle seam: deterministic fallback title, latest-title fold, one optional async provider (first-prompt vs all-prompts variants). | M4 | P2 | not_started |
| E7.11 | planMode: plan/mode state folded from the log; user selections flushed at turn boundaries; guidance rendering; /plan; stable plan-exit schema. | M7 | P1 | not_started |
| E7.12 | agentPresets with revisions: YAML-declared preset revisions; retired revisions kept until their last user releases them. | M7 | P1 | not_started |
| E7.13 | sessionProjectionCache: durable checkpoints of projection state (throttled, mandatory at turn end/detach) to accelerate hydration. | M4 | P1 | not_started |
| E7.14 | mcpManager: reconciles MCP client instances against settings, aggregates statuses, serves restart/probe to management surfaces. | M6 | P1 | not_started |
| E7.15 | schedule independent of session activation: tasks stored separately; due messages queued into the target session. | M14 | P1 | not_started |
| E7.16 | ssh seam: one authenticated OpenSSH connection, installed helper identity, independent program streams, disconnect cleanup; paired fs/subprocess/sandbox providers for the remote world. | M20 | P1 | not_started |
| E7.17 | shellEnv: plugins declare effect-scoped KEEL_* environment facts; each shell tool collects one trusted snapshot per execution. | M5 | P1 | not_started |
| E7.18 | sandboxPolicy: the single home for default sandbox mode and workspace root so bash and fs can't confine to different roots; consumers hand over the exact argv; backend reports enforcement. | M3 | P0 | verified |
| E7.19 | approval seam fails closed: absence of an answerer yields unavailable. | M3 | P0 | verified |
| E7.2 | toolResultPruner: model-free pruning of oversized *current* tool results through replayable surface replacements before summary compaction. | M4 | P0 | verified |
| E7.20 | permissionPresets: user-facing presets bundling sandbox mode + approval policy; switching writes one logged permission/preset event that updates both knobs. | M3 | P0 | verified |
| E7.21 | fs-observation-policy: observed-state checks (read-before-edit, stale-file detection) contributed through the fs/* event gate. | M5 | P0 | verified |
| E7.22 | lsp seam with exactly four normalized operations and no protocol escape hatch. | M11 | P1 | not_started |
| E7.23 | web seam: search and fetch providers register into one service; tool names stay stable. | M5 | P0 | verified |
| E7.24 | speechToText seam with local recognizers; browser uses an authenticated remote; transcripts stay in the draft until submission. | M17 | P1 | not_started |
| E7.25 | officeKit: render Office files to PDF/images, convert, recalculate on the host using a native engine or a WASM fallback; document preview sidebar. | M17 | P1 | not_started |
| E7.26 | fileUploads: streaming intake, durable storage, staged receipts bound to accepted submissions. | M4 | P1 | not_started |
| E7.27 | Forge seam (code-host change requests): providers map remote URLs to change requests, look up by head branch, read status in batches; watchers share one polling loop; session projection binds change requests found in shell push output; a panel shows Git inspection and status. | M11 | P2 | not_started |
| E7.28 | remoteAccess role policies: non-owner peers get role-based access to specific methods; list results filtered; each peer's access snapshot streamed. | M20 | P1 | not_started |
| E7.29 | Connection authentication as a registry of credential verifiers tried in registration order; first live peer wins; source policy and business authorization stay separate. | M20 | P1 | not_started |
| E7.3 | Compaction via pressure events: compaction reacts to post-step pressure and request-error recovery; no model-facing "compact" tool. | M4 | P1 | not_started |
| E7.30 | authorization flow registry: a plugin that knows how to obtain a credential registers a flow keyed by the record it writes; one attempt per key at a time. | M2 | P1 | not_started |
| E7.31 | Action cards: optional cards with user actions and status notices; card kinds register their actions and handlers. | M19 | P2 | not_started |
| E7.32 | Plugin recommendations on explicit need only; enabling goes through the plugin manager after a click. | M10 | P2 | not_started |
| E7.33 | Plugin registry probe: race several registry mirrors and pick the fastest valid one. | M22 | P2 | not_started |
| E7.34 | Plugin market reader for user-configured index sources, validated; install through the manager. | M10 | P1 | not_started |
| E7.35 | Message feedback in the canonical log with per-item compare-and-set; session-level /feedback as a log-only event. | M4 | P1 | not_started |
| E7.36 | Hooks bridges: the reference ships adapters that run hooks defined in other agent tools' formats. | M8 | P2 | not_started |
| E7.37 | Agent-authored plugins: a tool lets the agent define plugin code whose host half runs in a sandboxed VM and whose client half is served to the page. | M10 | P2 | not_started |
| E7.38 | Workflow engine (script engine) plus a fixed loop-until-done workflow consumer that fans out subagents. | M8 | P1 | not_started |
| E7.39 | Webhook runtime where trusted rules turn authenticated deliveries into ordinary sessions; provider adapters (e.g., code host events). | M15 | P2 | not_started |
| E7.4 | sessionStatus: reading acknowledgements and manual unread marks stored outside session history. | M4 | P1 | not_started |
| E7.40 | Inspector service: worker-hosted debug target + query API over the live plugin tree. | M21 | P1 | not_started |
| E7.41 | Storage seam with multiple backends (json, sqlite) and a typed "domain" form for non-session state. | M4 | P2 | not_started |
| E7.42 | mcpResources seam (connection-owned providers serve shared resource tools). | M6 | P2 | not_started |
| E7.43 | Browser-use and computer-use as provider seams (several interchangeable providers; each provider owns its tools and per-session resources; no shared action API; per-application consent with cancellation; retained run-code runtime per agent). | M16 | P1 | not_started |
| E7.5 | workspaceChanges: per-turn changed-file summaries with turn-start vs turn-end comparison, served by session and event sequence; the log carries only the turn. | M11 | P1 | not_started |
| E7.6 | workspaceFiles: stat, paged text, byte windows, directory listings and a change feed confined by lstat, containment and a stat re-check. | M5 | P0 | verified |
| E7.7 | fileReferences: @ path completion returns paths only, never contents. | M19 | P1 | not_started |
| E7.8 | sessionReferenceResolver: an @session mention embeds a bounded snapshot of another session as untrusted message context. | M4 | P1 | not_started |
| E7.9 | sessionQuery seam: exact reads, filters, traces; backend adds full-text reconciliation, ranking, snippets and cursor generations. | M4 | P1 | not_started |
| V1 | Plugin scope tree (lifecycle-safe plugins): every plugin runs in a scope that records what it registered (tools, hooks, routes, UI panels, timers, subprocesses); unload/reload disposes all of it automatically; child scopes inherit parent permissions only down, never up. | M10 | P0 | verified |
| V10 | Duplicate-code and dead-feature detector for the builder: CI reports duplicate blocks (W1.7) and any plan ID with code but no test/evidence. | M0 | P1 | not_started |
| V11 | Per-agent "tool surface report": shows exactly which tools, MCP servers, skills and subagents an agent can reach after merges, with the rule that allowed each. | M7 | P1 | not_started |
| V12 | Config "doctor" for rule conflicts: detects rules that can never match (shadowed by a later rule), duplicate rules, and broad allows after specific denies. | M3 | P1 | not_started |
| V13 | Release provenance page in-app listing for the running build: version, commit-less build id, signing key fingerprint, manifest hash, SBOM link. | M22 | P1 | not_started |
| V14 | Prompt-assembly viewer for subagents/commands (what system prompt, instructions, skills and MCP instruction blocks a child actually received), with taint labels. | M7 | P1 | not_started |
| V15 | Local "plugin conformance kit": a checklist-runner that verifies a plugin cleans up on unload, respects permission denials, declares all network hosts, and survives safe-mode boot. | M10 | P1 | not_started |
| V16 | Keel invariant-gate catalog: a list of gates specific to Keel: Tier-2 table hash unchanged; no outbound network in offline suite; no secret in logs; every tool has a presenter; every plugin manifest declares permissions; no hardcoded UI copy; migration compat matrix; no `Any` baseline growth. | M0 | P0 | verified |
| V17 | Disposable-sandbox run mode: run the agent's tool execution in a container with a copy-on-write view of the project, then show a diff and apply only approved hunks back. | M5 | P1 | not_started |
| V18 | Plugin static capability scan: before enabling a plugin, scan its Python/JS for subprocess, socket, ctypes, `eval/exec`, file writes outside its data dir, and compare with its declared permissions; mismatch blocks enabling. | M10 | P1 | not_started |
| V19 | Executable docs: code fences in user and internal docs run in CI against the mock model; "paste of key types" verified against source. | M23 | P1 | not_started |
| V2 | Policy simulator with "winning rule" trace: shows ordered rules, which matched, which won, why a multi-resource op was denied, and the Tier-2 verdict. | M3 | P0 | verified |
| V20 | Turn Replay Test builder: "save this turn as a test" button producing a snapshot fixture (recorded stream + expected log) for the builder's suite. | M21 | P1 | not_started |
| V21 | Contract generator for plugin events: generate docs and JSON Schemas for every event type from code annotations, and fail CI if an event lacks `mode` and payload docs (D6.3). | M8 | P1 | not_started |
| V22 | Seam checklist linter: verifies each registered seam has a definition, a default provider and at least one consumer, and flags single-role "seams" (D3.1). | M7 | P2 | not_started |
| V23 | Run-in-isolation toggle for risky plugins: run plugin code in a separate subprocess with its own env, reachable only via the RPC bridge. | M10 | P1 | not_started |
| V24 | Tool conformance kit: one automated suite every tool must pass: output schema declared, presenter pure on replay, cancel honored within N ms, no leaked fields in schemas(), concurrency flag only on read-only tools, timeout cooperative, errors typed. | M5 | P0 | verified |
| V25 | Tool pipeline fuzzer: random args, random cancel points, injected failures; assert no hang, no leaked process/task, no orphan call without result, log stays replayable. | M25 | P1 | not_started |
| V26 | Request-reconstruction test: replay a session log and rebuild the exact provider request; byte-compare with what was actually sent (hash) to prove "model-visible = logged" (D2.11). | M4 | P0 | verified |
| V27 | Release publish verifier: before upload, cross-check manifest, sizes, SHA-256/512, signatures, version monotonicity, completion record; after upload, re-download and verify; metadata last. | M22 | P1 | not_started |
| V28 | Error-code catalog generator: scan code for error constants, produce the troubleshooting pages and the typed-code list; fail CI if a raised code is undocumented. | M23 | P1 | not_started |
| V29 | Per-tool timeout and output-size budget table visible in the UI (and editable), with default values by tool class. | M5 | P2 | not_started |
| V3 | Broadness scoring for saved "always" approvals: flag patterns like bare `*` or `rm *`, show last-used date, offer narrowing (e.g., command prefix to exact subcommand). | M3 | P1 | not_started |
| V30 | Postmortem template and counter: every escaped bug gets a numbered postmortem (cause, why tests missed it, new test) linked from the fixing commit. | M0 | P1 | not_started |
| V31 | Local-socket transport spike: prove Electron ↔ Python over named pipe/UDS with streaming and backpressure on all three OSes before committing (C-19); keep TCP+token as fallback. | M19 | P0 | verified |
| V4 | Reject-cascade UX: a "Reject all pending" button plus a per-request reject, mirroring W3.9; rejected reasons passed to the model as no-retry instruction. | M19 | P1 | not_started |
| V5 | Strictness presets as rule sets: Cautious / Balanced / Trusted compiled into ordered rule arrays, diffable and exportable, never able to touch Tier 2. | M3 | P0 | verified |
| V6 | Opaque per-server correlation IDs for MCP (instead of session ids): random value per (session, server), rotated per session, never reused across servers. | M6 | P1 | not_started |
| V7 | Sycophancy/capitulation eval: scripted multi-turn tests where a fixture "user" pushes back without new evidence; pass = model keeps correct answer; plus a "new evidence" case where it should change. | M21 | P1 | not_started |
| V8 | External specialist adapters: Keel can delegate a task to a coding CLI the user already has installed (any tool with a headless mode) as a child agent, with "one writer per working tree" locking and mandatory diff/test verification after. | M12 | P1 | not_started |
| V9 | Remote-initiated action confirmation: any task started from a channel (Telegram/email/webhook) that would run shell/edit/send actions requires a one-time code confirmation in the desktop app (or a pre-approved rule), per W7.17. | M15 | P1 | not_started |
| W1.1 | "Everything is a plugin" architecture: core features themselves are plugins on a composable runtime (built on Cordis; paper cited in README). | M10 | P1 | not_started |
| W1.10 | `SAFETY.md` surfaced as a first-run notice ("review the safety notice before running"). | M19 | P0 | not_started |
| W1.11 | Developer-preview banner: explicit "compatibility-breaking changes will happen". | M19 | P1 | not_started |
| W1.12 | `BRAND_GUIDELINES` file (also localized). | M23 | P2 | not_started |
| W1.13 | Builder instruction files for multiple AI tools: `AGENTS.md`, `CLAUDE.md`, `.agents/`, `.claude/`. | M0 | P1 | not_started |
| W1.14 | Plugin discoverability via a repository topic (`dsh-plugin`). | M10 | P2 | not_started |
| W1.15 | `python/` package in a TS monorepo (language bindings or SDK). | M20 | P1 | not_started |
| W1.16 | `patches/` and `vendor/` folders for patched/vendored dependencies. | M0 | P1 | not_started |
| W1.17 | Discussions-only feedback (no Issues tab visible), Discord, citation block, docs site, website folder in repo. | M23 | P2 | not_started |
| W1.18 | MIT license + `THIRD_PARTY_NOTICES.md`. | M0 | P0 | not_started |
| W1.2 | Single command web launch (`npx @deepseek-ai/dsh web`) serving a Web UI at `127.0.0.1:3080`, auto-opening the browser locally. | M20 | P1 | not_started |
| W1.3 | SSH-aware launch: over SSH only print the host URL (client or editor owns the forwarded address). | M20 | P1 | not_started |
| W1.4 | `--no-open` flag; Web and Desktop targets from one codebase (`apps/`, `native/`, Makefile targets for both). | M19 | P1 | not_started |
| W1.5 | Test suite taxonomy by config: unit, bench, e2e, expected (golden expected outputs), snapshot, web, web-stress, web-perf as separate runner configs; plus Python tests (`pytest.ini`). | M25 | P1 | not_started |
| W1.6 | `benchmarks/` + `BENCHMARK.md` at repo root, and `snapshots/` folder. | M21 | P1 | not_started |
| W1.7 | Staged-only lint config (`.oxlintrc.staged.json`), `lefthook.yml` git hooks, `.jscpd.json` duplicate-code detector, `.rgignore` (files ripgrep should skip), `.gitattributes`, `.editorconfig`. | M0 | P1 | not_started |
| W1.8 | Dual CI config (`.github` and `.gitlab-ci.yml`) in one repo. | M1 | P1 | not_started |
| W1.9 | `i18n.yaml` single-source docs: `README.i18n.yaml`, `CONTRIBUTING.i18n.yaml`, `SAFETY.i18n.yaml`, `BRAND_GUIDELINES.i18n.yaml` alongside `.md` and `.zh.md`. | M25 | P1 | not_started |
| W2.1 | Markdown agent files with YAML frontmatter; nested path becomes agent ID (`team/reviewer`); global + project locations; same fields as config entries; body is the system prompt. | M7 | P0 | verified |
| W2.10 | Model reference format `provider/model#variant` and an expanded object form. | M2 | P1 | not_started |
| W2.11 | Plan agent may write only plan files in a dedicated plan folder; shell stays permission-controlled. | M7 | P0 | verified |
| W2.2 | Modes `primary` / `subagent` / `all`; subagents run in child sessions with fresh context. | M7 | P0 | verified |
| W2.3 | Built-ins: build, plan, general (no further subagents), explore (read-only incl. web); hidden maintenance agents (`compaction`, `title`, `summary`) that are not user-selectable and have all actions denied except their job. | M7 | P0 | verified |
| W2.4 | `steps` limit: max model steps per turn; on the final step tools are removed and the model must summarize in text; new user input resets. | M7 | P0 | verified |
| W2.5 | `hidden`, `color`, `disabled` agent fields; `disabled` removes a built-in at config load. | M7 | P1 | not_started |
| W2.6 | Subagent launch permissions: parent's `subagent` rules control which agents it may launch (e.g., deny `*`, allow `reviewer`); child uses its own permissions, not a subset of parent's. | M12 | P0 | verified |
| W2.7 | Default agent resolution chain: configured default, else `build`, else first visible primary-capable; changing default does not alter existing sessions. | M7 | P1 | not_started |
| W2.8 | `system` replaces the provider base prompt for that agent, but project instructions, skills, references still get added. | M7 | P0 | verified |
| W2.9 | Agent merge semantics: later scalars replace, maps merge by key, permission rules append; global rules apply before agent rules. | M2 | P0 | verified |
| W3.1 | Rule = `{action, resource, effect}`; effects `allow/deny/ask`; no match means ask. | M3 | P0 | verified |
| W3.10 | Policies layer can hard-deny after rules and saved approvals; turns allow/ask into deny, never grants; global/managed policies override project config. | M3 | P0 | verified |
| W3.11 | Permission actions for MCP resources: `list_mcp_resources` (resource = server) and `read_mcp_resource` (resource = `<server>:<uri>`); MCP tools as `<server>_<tool>`. | M6 | P1 | not_started |
| W3.12 | Non-interactive clients must decide approval behavior; configured deny always enforced. | M20 | P0 | verified |
| W3.13 | Docs warning: shell has full host authority; prefer narrow allowlists over trying to recognize every dangerous command. | M3 | P0 | verified |
| W3.2 | Last matching rule wins (broad first, exceptions after); rules combine in order: lower-priority config, global, then agent. | M3 | P0 | verified |
| W3.3 | Wildcards: `*` matches any characters including `/`; `?` one character; whole-value match; backslashes normalized; case-insensitive on Windows; shell pattern ending ` *` also matches the bare command. | M3 | P0 | verified |
| W3.4 | Multi-resource operations: any `deny` denies; else any `ask` asks; else allow (e.g., a patch touching several files). | M3 | P0 | verified |
| W3.5 | `~` / `$HOME` expansion at config load for path actions only; shell resources stay raw text. | M3 | P1 | not_started |
| W3.6 | `external_directory` action: paths outside the project/worktree are checked before read/edit rules. opencode's default is allow. | M3 | P0 | verified |
| W3.7 | Shell scanner for Bash, Zsh, POSIX sh and PowerShell: each extracted subcommand and `cd` target is checked; malformed or dynamically evaluated commands return a scanner error instead of running. | M3 | P0 | verified |
| W3.8 | Base default policy: allow all, but ask on `.env` / `.env.*` reads except `.env.example`. | M3 | P0 | verified |
| W3.9 | Approval replies: `once`, `always` (saves tool-proposed patterns, project-scoped, never overrides a configured deny), `reject` (rejects every other pending request in that session; optional feedback text to the model). | M3 | P0 | verified |
| W4.1 | CLI: `mcp add` (remote `--url`, local `-- cmd`, `--env`, `--header`, `--global`), `mcp list`, `mcp auth`, `mcp logout`; in-app `/mcps` to view/connect/disconnect/authenticate. | M6 | P1 | not_started |
| W4.10 | MCP prompts become slash commands named `<server>:<prompt>` with positional args. | M6 | P1 | not_started |
| W4.11 | Server instructions returned at init are injected into the system prompt in a tagged block; omitted when the agent's permissions deny all that server's tools. | M6 | P1 | not_started |
| W4.12 | Elicitation (server asks the user for input mid-call) rendered as a form or a link; dismiss cancels. | M6 | P1 | not_started |
| W4.13 | opencode sends the session ID in request `_meta`; docs warn remote servers may log it. | M6 | P1 | not_started |
| W4.14 | `disabled` flag keeps a server configured but unconnected; disconnect in UI does not edit config. | M6 | P1 | not_started |
| W4.2 | Config shape: `mcp.servers.<name>` with `type local\|remote`, `command`, `cwd`, `environment`, `url`, `headers`, `oauth`, `disabled`, `codemode`, `timeout`, `protocol`, `pool`. A higher-precedence config replaces the whole server object (no field merge). | M6 | P1 | not_started |
| W4.3 | OAuth for remote servers: PKCE, discovery, refresh; credentials stored outside project config; `oauth:false` for header-key servers. | M6 | P0 | not_started |
| W4.4 | Client registration order: pre-registered `client_id` first, then Client ID Metadata Documents (CIMD), then Dynamic Client Registration (DCR); options `client_secret`, `scope`, `callback_port`, `redirect_uri`, `auth_server_metadata_url`. | M6 | P1 | not_started |
| W4.5 | OAuth when the browser is on another machine (SSH/container): user pastes the failed callback URL into a prompt. | M6 | P1 | not_started |
| W4.6 | Timeouts: startup 30 s, catalog 30 s, execution 12 h defaults; global and per-server. | M6 | P1 | not_started |
| W4.7 | Protocol version selection (`legacy`, `auto` probe, pinned newest revision) with probe cost warning. | M6 | P2 | not_started |
| W4.8 | Pooled shared connections across project directories when everything that changes the connection matches. | M6 | P2 | not_started |
| W4.9 | Tool naming normalization (`<server>_<tool>`, invalid chars to `_`, collisions need unique short names). | M6 | P1 | not_started |
| W5.1 | Markdown or JSON commands; nested folders become `/team/review`; global vs project; project overrides global; nearer overrides ancestor; custom may replace built-in; hot reload. | M7 | P0 | verified |
| W5.2 | Frontmatter: `description`, `agent`, `model`, `subagent` (true/false/omit rules); legacy alias `subtask`. | M7 | P0 | verified |
| W5.3 | Arguments: `$ARGUMENTS`, positional `$1..$n` with quote grouping (last placeholder takes the rest, missing = empty); fallback appends args when no placeholder. | M7 | P0 | verified |
| W5.4 | Shell injection `!` + backtick command: output inserted into the prompt; opencode notes it runs outside the agent permission flow. | M7 | P0 | verified |
| W5.5 | Model precedence: command model, else command agent's model, else session model. | M7 | P1 | not_started |
| W5.6 | Background child commands (`subagent: true`): result or failure reported back to parent. | M7 | P1 | not_started |
| W5.7 | `@path` is not expanded in stored templates; attachments come from the composer. | M7 | P1 | not_started |
| W6.1 | Accuracy-over-approval response contract: verify facts/figures/citations before finalizing; never fabricate; say unknown plainly; do not anchor on user-supplied numbers; independent estimates. | M7 | P0 | not_started |
| W6.2 | Explicit confidence labels (high / moderate / low / unknown) on judgments. | M7 | P1 | not_started |
| W6.3 | Anti-sycophancy rules: no praise of questions, say immediately if the user is wrong, strongest counterargument first, do not capitulate under pushback without new evidence. | M7 | P0 | not_started |
| W6.4 | Conductor + specialists routing: one conductor agent; external coding agents as optional specialists for multi-file work; one writer per dirty tree; always verify diffs/tests after a specialist. | M12 | P1 | not_started |
| W6.5 | Control-plane routing: prefer local desktop tool over cloud tools when local is healthy; accessibility-tree enrichment optional; DOM work prefers browser tools. | M16 | P1 | not_started |
| W6.6 | Running ledger of important account facts/decisions in a memory file. | M13 | P1 | not_started |
| W7.1 | Explicit trust boundary list (client untrusted, daemon holds secrets, agent environment powerful, third parties). | M1 | P0 | verified |
| W7.10 | SSRF safe fetch details: http(s) only, resolve then pin the checked address, re-check every redirect, cap time and size. | M3 | P0 | verified |
| W7.11 | Streaming body-size enforcement (not just Content-Length), bounded multipart uploads, capped recordings. | M20 | P1 | not_started |
| W7.12 | Generic client errors + request id, details only in server log. | M20 | P1 | not_started |
| W7.13 | Security headers for any served UI: CSP, `X-Frame-Options: DENY`, HSTS (when HTTPS), `nosniff`, strict referrer policy, COOP, permissions policy (microphone only inside the app). | M20 | P0 | verified |
| W7.14 | Rendering safety: Markdown rendered without raw HTML; link scheme allow-list; no `dangerouslySetInnerHTML`; inline-served HTML/SVG/XML get a sandboxing CSP; generated-site previews in a sandboxed iframe. | M19 | P0 | verified |
| W7.15 | Share tokens with 144 bits of randomness; public share pages show redacted text and short tool previews, never owner identity or instructions. | M4 | P1 | not_started |
| W7.16 | Publishing copies only from the site's own folder; never hidden files or symlink targets outside. | M18 | P0 | verified |
| W7.17 | Inbound channel rules: signature verified with constant-time compare, 300 s window, de-duplication, refuse when no secret configured; only approved senders can start work; voice/phone-initiated tasks require a confirmation code; email triggers accept only clean mail and by default only from the owner's address. | M15 | P0 | verified |
| W7.18 | Spending caps enforced atomically in the database before each vendor call. | M21 | P1 | not_started |
| W7.19 | Honest "known limitations" list: prompt injection can still misuse granted power; "watch only" enforced only in client in openman (orgo-teammates enforces on server); one shared sign-in budget; self-hosting is only as safe as setup. | M26 | P0 | verified |
| W7.2 | Live-view URL given only to the owner with `Cache-Control: no-store`. | M16 | P1 | not_started |
| W7.20 | Deployment hygiene from orgo-teammates: narrowest-scope keys, never show keys on screen/recordings, set provider spend limits, be careful with "Always allow", private vulnerability reporting, only latest branch supported, best-effort fixes. | M23 | P1 | not_started |
| W7.3 | Secrets sealed with AES-256-GCM, random 12-byte IV per value + auth tag; session cookie sealed with its own key and additional authenticated data, HttpOnly, SameSite=Lax, Secure when HTTPS, 30-day life, checked against a revocations table. | M3 | P0 | verified |
| W7.4 | API keys: prefixed random token, stored only as SHA-256, shown once; per-key rate limit; per-user idempotency keys. | M3 | P0 | verified |
| W7.5 | Secrets reach child processes as a staged file read-and-deleted by the setup script, never on a command line. | M3 | P0 | verified |
| W7.6 | Log redaction plus keyed hash of user ids instead of ids. | M3 | P0 | verified |
| W7.7 | Sign-in bound to the browser that started it by a sealed SameSite=Strict cookie, so a forwarded link can't be completed by someone else. | M20 | P1 | not_started |
| W7.8 | Sign-in/pairing attempts rate limited per client address and globally; use trusted-proxy hop count for address detection; only same-origin relative return paths honored. | M20 | P0 | verified |
| W7.9 | CSRF origin check for cookie-bearing state-changing requests; bearer routes exempt. | M20 | P1 | not_started |
| W8.1 | orgo-teammates `ALLOWED_EMAILS` supports `@domain` entries → paired-client allowlist should support patterns (e.g., device label prefixes), not only exact entries. | M20 | P2 | not_started |
| W8.2 | openman: recordings and screenshots capped in the database. | M4 | P1 | not_started |
| W8.3 | openman: computers named in a request are checked against the user's own listing; changes to the home computer through the API are refused. | M16 | P1 | not_started |
| W8.4 | opencode `question` and MCP elicitation share one UI form. | M19 | P1 | not_started |
| W9.1 | MCP panel (`/mcps`) | M19 | P1 | not_started |
| W9.2 | Approval card with three actions | M19 | P1 | not_started |
| W9.3 | Agent picker and agent editor | M19 | P1 | not_started |
| W9.4 | Command palette entries generated from commands | M19 | P1 | not_started |
| W9.5 | First-run Safety notice | M19 | P1 | not_started |
| W9.6 | Web UI served on loopback with SSH hint banner showing the forwarded URL instructions. | M20 | P1 | not_started |
| X0.1 | Priority inflation | M0 | P0 | verified |
| X0.10 | Plan says "reimplement from behavior" but gives no clean-room procedure | M0 | P0 | verified |
| X0.2 | M19 (desktop UI) is overloaded | M19 | P0 | verified |
| X0.2b | Same for M11, M17, M22 | M11 | P1 | not_started |
| X0.3 | No dependency graph | M0 | P0 | verified |
| X0.4 | Duet defined three ways | M12 | P0 | verified |
| X0.5 | Store distribution conflicts with "no source/no GitHub for users" | M22 | P1 | not_started |
| X0.6 | Free-tier trap list is incomplete | M0 | P0 | verified |
| X0.7 | Voice/ML licensing is stated as "check" | M2 | P0 | verified |
| X0.8 | "Zero network without account" is asserted but there is no test list | M25 | P0 | verified |
| X0.9 | No risk register or rollback plan per milestone | M0 | P1 | not_started |
| X1.1 | Tool-call dialect adapters | M2 | P0 | verified |
| X1.10 | Self-consistency voting for hard steps | M7 | P2 | not_started |
| X1.11 | Streaming partial-JSON tool-argument parser | M2 | P1 | not_started |
| X1.12 | Parallel tool calls with dependency check | M5 | P1 | not_started |
| X1.13 | Steering and interrupt | M4 | P0 | verified |
| X1.14 | Model switch mid-session | M2 | P1 | not_started |
| X1.15 | Per-model prompt profiles | M7 | P1 | not_started |
| X1.16 | Model "health check" on load | M2 | P1 | not_started |
| X1.2 | Chat-template handling | M2 | P0 | verified |
| X1.3 | Reasoning-model output handling | M2 | P0 | verified |
| X1.4 | Selectable edit formats per model | M5 | P0 | verified |
| X1.5 | Fuzzy patch application | M5 | P0 | verified |
| X1.6 | Apply-model role | M2 | P2 | not_started |
| X1.7 | Repo map ranking | M11 | P0 | verified |
| X1.8 | Accurate token counting | M2 | P0 | verified |
| X1.9 | Few-shot tool exemplars | M2 | P1 | not_started |
| X10.1 | Definition-of-done template | M0 | P0 | not_started |
| X10.2 | Provenance file | M0 | P0 | not_started |
| X10.3 | Decision log (`DECISIONS.md`) separate from ADRs for owner-level choices (D1 to D7, G1 to G7) with date and answer | M0 | P1 | not_started |
| X10.4 | Builder "stop list": actions that always pause for the owner, mirrored from gates G1 to G7 plus destructive repo actions, as a machine-readable file the builder must check | M0 | P0 | not_started |
| X10.5 | Weekly "what is proven" report generated from `PLAN-INDEX.json` (counts by status, stale evidence, failing rows) | M0 | P1 | not_started |
| X10.6 | Scope-creep guard: any new feature idea goes to `INBOX.md` with a proposed milestone instead of being built inline | M0 | P1 | not_started |
| X2.1 | Diagnostics feedback after every edit | M11 | P1 | not_started |
| X2.10 | Migration assistants (framework/library version upgrades) as bundled skills with verification steps | M9 | P2 | not_started |
| X2.11 | Notebook-aware editing (`.ipynb` cell diff, run cell, outputs stored outside the notebook diff) | M5 | P2 | not_started |
| X2.12 | Commit hygiene: conventional-commit suggestions from project history, secret scan on staged diff, hook-aware (respect existing pre-commit) | M11 | P1 | not_started |
| X2.13 | Monorepo task graph awareness (workspaces, package boundaries) so edits and tests are scoped to affected packages | M11 | P1 | not_started |
| X2.14 | "Explain this change" and "explain this file" with symbol-level citations | M11 | P2 | not_started |
| X2.15 | Language packs: bundled guidance + tool wiring for Python, TypeScript, Go, Rust, Java, C/C++, C#, PHP, Ruby, shell. Each pack lists install hints for compilers/LSP and test command detection | M11 | P1 | not_started |
| X2.16 | Long-running process supervisor in the terminal: named background jobs, tail/stop/restart, auto-surface crash output to the agent | M5 | P1 | not_started |
| X2.2 | Rename/extract/move via LSP code actions instead of text edits when available | M11 | P1 | not_started |
| X2.3 | TDD mode: write failing test first, confirm red, implement, confirm green, record both runs as evidence | M7 | P1 | not_started |
| X2.4 | Bug-repro mode: agent must produce a failing reproduction before changing code | M7 | P1 | not_started |
| X2.5 | Code review mode on any diff or branch (style, bugs, security, test gaps) producing inline comments the user can accept as tasks | M7 | P1 | not_started |
| X2.6 | Per-task git worktree **merge queue** with conflict preview and "land when green" button | M11 | P1 | not_started |
| X2.7 | Test-runner adapters (pytest, unittest, jest/vitest, go test, cargo test, JUnit-style output parsing) with failure summaries instead of raw logs | M11 | P1 | not_started |
| X2.8 | Coverage-guided hints: show which lines the change leaves untested | M11 | P2 | not_started |
| X2.9 | Dependency upgrade assistant: read changelogs offline from the package cache, upgrade one at a time, run tests, roll back on failure | M11 | P2 | not_started |
| X3.1 | Local **desktop search** across user-approved folders (FTS5 + optional embeddings), exposed as a tool and a palette | M13 | P1 | not_started |
| X3.10 | Flashcards and spaced repetition generated from notes or documents, stored locally | M13 | P2 | not_started |
| X3.11 | Study/tutor mode (Socratic, quiz, explain-back) as a bundled persona + skills | M9 | P2 | not_started |
| X3.12 | Writing coach with local grammar/style checking; check any third-party checker's license before bundling | M17 | P2 | not_started |
| X3.13 | Personal CRM/contacts notes in the vault with follow-up reminders | M13 | P2 | not_started |
| X3.14 | Local finance CSV import and categorization (no bank connections) | M17 | P2 | not_started |
| X3.15 | Clipboard history tool (opt-in, encrypted, auto-expire) the agent can query with consent | M19 | P2 | not_started |
| X3.16 | Screenshot region capture with OCR and "ask about this" action | M16 | P1 | not_started |
| X3.2 | Document redaction tool (names, emails, IDs) with preview and verified-redacted PDF output | M17 | P1 | not_started |
| X3.3 | Receipt/invoice extractor to a local CSV/SQLite table (OCR + field parser) with review UI | M17 | P2 | not_started |
| X3.4 | Contract/document comparison: clause diff and plain-language summary with page citations | M17 | P2 | not_started |
| X3.5 | Spreadsheet helper: explain formulas, find errors, build pivots, produce charts; write results to a copy, never in place by default | M17 | P1 | not_started |
| X3.6 | File organizer rules engine (by type, date, EXIF, name patterns) with dry-run, preview, undo journal | M5 | P1 | not_started |
| X3.7 | Duplicate finder (hash + perceptual hash for images) with safe-delete to Keel trash | M5 | P2 | not_started |
| X3.8 | Web clipper and read-later queue (save page as Markdown into the vault) | M13 | P2 | not_started |
| X3.9 | RSS/Atom digest agent (user feeds only) with scheduled summary | M14 | P2 | not_started |
| X4.1 | Barge-in: user speech interrupts TTS immediately; half-duplex fallback on weak hardware | M17 | P1 | not_started |
| X4.2 | Streaming TTS sentence by sentence while the model is still generating | M17 | P1 | not_started |
| X4.3 | Optional wake word (verify engine license) with visible mic indicator and hard mute | M17 | P2 | not_started |
| X4.4 | Local vision-language model tool for screenshots/diagrams (user-installed model, license shown) | M16 | P1 | not_started |
| X4.5 | Video tooling via user-installed ffmpeg: frame extraction, audio extraction, subtitle generation from local STT | M17 | P2 | not_started |
| X4.6 | Voice command grammar for app control ("approve", "deny", "stop everything") separate from free dictation; always requires a spoken confirmation for risky actions | M17 | P1 | not_started |
| X4.7 | Audio privacy rules: no recording stored by default, visible recording state, per-meeting consent reminder text | M17 | P1 | not_started |
| X5.1 | Sensitive-project mode | M3 | P0 | verified |
| X5.10 | Encrypted session/memory export bundles with passphrase, verified on import (signature + schema version) | M4 | P1 | not_started |
| X5.11 | Provider data-handling card: for each configured remote provider, show what Keel sends (from the egress log) and a link to the user's own account settings; never claim anything about the provider's retention | M21 | P1 | not_started |
| X5.12 | Dependency and model **allow/deny lists** in managed policy (specific MCP servers, plugin IDs, model files by hash) | M24 | P2 | not_started |
| X5.13 | Safe-paste detector: warns when the user pastes text containing a key/token pattern into chat | M3 | P1 | not_started |
| X5.2 | Data-classification labels on files and memories (public / internal / secret) that feed redaction and egress decisions | M3 | P1 | not_started |
| X5.3 | Time-boxed and just-in-time permissions | M3 | P1 | not_started |
| X5.4 | Capability tokens for subagents and plugins: short-lived, scoped, revocable, logged | M3 | P1 | not_started |
| X5.5 | Mass-change guard | M3 | P0 | verified |
| X5.6 | Filesystem change journal per task so every touched path can be reviewed and reverted as a set | M5 | P0 | verified |
| X5.7 | Permission review screen: every standing allow rule with last-used date, one-click prune of unused rules | M3 | P1 | not_started |
| X5.8 | Per-tool sandbox profiles (read-only FS, no network, temp-only write) selectable in agent frontmatter | M5 | P1 | not_started |
| X5.9 | Clipboard and screen guard: tools that read clipboard/screen always ask, and tainted-source rules apply to captured content | M3 | P1 | verified |
| X6.1 | `keel dev` plugin scaffold generator, hot reload, and a **mock host** so plugins can be tested without the full app | M10 | P1 | not_started |
| X6.10 | Feature-lifecycle labels (experimental / beta / stable) in UI and config, with experimental off by default | M3 | P1 | not_started |
| X6.2 | Plugin test harness with golden event streams and permission-denial tests | M10 | P1 | not_started |
| X6.3 | Typed SDKs generated from the API schema (Python and TypeScript), version-pinned to the daemon | M20 | P1 | not_started |
| X6.4 | API versioning policy: deprecation headers, sunset dates, compatibility tests against the previous minor | M20 | P1 | not_started |
| X6.5 | In-app interactive API explorer for the local API (loopback, token-protected); docs stay private unless G7 | M20 | P2 | not_started |
| X6.6 | Event schema registry: every internal event type has a JSON Schema and a changelog; plugins subscribe by type | M8 | P1 | not_started |
| X6.7 | Config validation with "did you mean" suggestions, line/column errors for JSONC, and `keel config explain <key>` | M2 | P0 | not_started |
| X6.8 | Layered config viewer: shows which layer (default, global, project, env, policy) set each value | M2 | P1 | not_started |
| X6.9 | Settings search, diff against defaults, per-section reset, import/export | M19 | P1 | not_started |
| X7.1 | ARM64 builds for Windows and Linux; macOS universal or separate arm64/x64 with verified native deps | M22 | P1 | not_started |
| X7.10 | Disk-usage manager: models, caches, sessions, trash, with sizes, safe-clean, and per-category caps | M19 | P1 | not_started |
| X7.2 | Per-user vs per-machine install option on Windows; no admin rights required for per-user | M22 | P1 | not_started |
| X7.3 | Uninstall options | M22 | P1 | not_started |
| X7.4 | File associations and URL protocol registration (`keel://`) with clean removal on uninstall | M22 | P1 | not_started |
| X7.5 | Linux specifics: Wayland and X11 tests, tray fallback where no tray exists, AppImage desktop integration, sandbox flag guidance | M22 | P1 | not_started |
| X7.6 | Antivirus false-positive playbook | M22 | P1 | not_started |
| X7.7 | Installer languages for the major UI locales; installer text from the same string catalogs | M22 | P2 | not_started |
| X7.8 | Download-integrity helper inside the app ("verify a file I downloaded") for users who want to check an installer before running it | M23 | P2 | not_started |
| X7.9 | First-run import wizard from other tools' folders (documented formats only), dry-run first | M19 | P2 | not_started |
| X8.1 | Local component catalog | M19 | P0 | not_started |
| X8.10 | Citation chips with hover preview of the source file/page/line | M19 | P1 | not_started |
| X8.11 | Inline diff and file preview inside chat with "open in dock" action | M19 | P1 | not_started |
| X8.12 | Error boundary and crash-recovery UI: renderer crash restores the session view without losing the draft composer text | M19 | P1 | not_started |
| X8.13 | Undo toast pattern for every destructive UI action (archive, delete, revoke) | M19 | P1 | not_started |
| X8.14 | Live theme editor (tokens only), contrast checker, import/export theme JSON | M19 | P2 | not_started |
| X8.15 | Optional sound cues (off by default), reduced-motion honoring everywhere | M19 | P2 | not_started |
| X8.16 | Multi-monitor awareness: remember window positions per display, detach docks to other screens | M19 | P2 | not_started |
| X8.17 | Empty-state and onboarding copy deck written once (Keel's own words) and reused across screens | M19 | P1 | not_started |
| X8.2 | Design-token contract file (`tokens.json`) as the only source of color, type, spacing, radius, motion; lint rule rejects hard-coded values | M19 | P0 | not_started |
| X8.3 | Density modes (compact / comfortable), per-pane zoom, and saved layouts | M19 | P1 | not_started |
| X8.4 | Notification center and activity feed (approvals, job results, errors) with filters | M19 | P1 | not_started |
| X8.5 | Actionable OS notifications | M19 | P1 | not_started |
| X8.6 | Tray / menu-bar mini window: running agents, pending approvals, quick ask, kill switch | M19 | P1 | not_started |
| X8.7 | Selection actions: select text anywhere in Keel and "ask about this", "add to context", "save to vault" | M19 | P1 | not_started |
| X8.8 | Thread tools: outline/minimap, pinned messages, jump-to-tool-call, timeline scrubber for long sessions | M19 | P1 | not_started |
| X8.9 | Side-by-side **session compare** (two models, two branches, before/after) | M19 | P1 | not_started |
| X9.1 | Fixture model server | M2 | P0 | verified |
| X9.10 | Mutation testing report published into the private dashboard for the permission gate and command analyzer | M25 | P1 | not_started |
| X9.2 | Record/replay (VCR-style) of real provider traffic with secrets scrubbed, for contract tests | M2 | P1 | not_started |
| X9.3 | Provider contract tests: each adapter must pass the same behavior suite (streaming, cancel, tool call, usage, errors) | M2 | P0 | verified |
| X9.4 | MCP conformance tests against bundled sample servers (stdio and HTTP) including hostile servers (huge output, hanging, bad schema) | M6 | P1 | not_started |
| X9.5 | Cross-platform path/permission matrix tests (Windows reserved names, ADS, long paths, case-insensitive FS, symlinks/junctions) | M3 | P0 | verified |
| X9.6 | Pseudo-localization build and RTL smoke test in CI | M25 | P1 | not_started |
| X9.7 | Migration matrix: every released schema version upgraded to current, with data checksums | M4 | P0 | verified |
| X9.8 | Token-accounting accuracy test (estimated vs runtime-reported usage within tolerance) | M21 | P1 | not_started |
| X9.9 | Long-session soak (thousands of events) watching memory, DB size, UI frame time | M25 | P1 | not_started |
| Y1.1 | Code Mode / execute tool | M5 | P1 | not_started |
| Y1.10 | skill loader advertised-list gate | M9 | P1 | not_started |
| Y1.11 | Subagent semantics | M12 | P1 | not_started |
| Y1.12 | Session utilities as tools | M4 | P2 | not_started |
| Y1.13 | Worktree tools | M11 | P1 | not_started |
| Y1.14 | Browser tool namespace | M16 | P1 | not_started |
| Y1.15 | experimental_image_generate | M17 | P2 | not_started |
| Y1.16 | MCP permission naming | M6 | P0 | verified |
| Y1.17 | Ordered rule list permissions | M3 | P0 | verified |
| Y1.18 | Managed config locations | M24 | P2 | not_started |
| Y1.19 | Config precedence algorithm | M2 | P0 | verified |
| Y1.2 | Model-dependent tool exposure | M5 | P0 | verified |
| Y1.20 | {env:VAR} and {file:path} config substitution | M2 | P0 | verified |
| Y1.21 | update modes (disable / notify / auto) | M22 | P1 | not_started |
| Y1.22 | snapshots toggle and watcher.ignore | M4 | P1 | not_started |
| Y1.23 | media.image and tool_output limits | M5 | P1 | not_started |
| Y1.24 | Compaction config | M4 | P0 | verified |
| Y1.25 | Cache warming | M2 | P1 | not_started |
| Y1.26 | References | M11 | P1 | not_started |
| Y1.27 | skills config directories and URLs | M9 | P2 | not_started |
| Y1.28 | instructions files, globs and HTTP(S) URLs | M7 | P1 | not_started |
| Y1.29 | Plugin management CLI | M10 | P1 | not_started |
| Y1.3 | patch multi-file format | M5 | P0 | verified |
| Y1.30 | Plugin enable/disable DSL | M10 | P0 | verified |
| Y1.31 | Three plugin surfaces | M10 | P1 | not_started |
| Y1.32 | location_idle_timeout | M16 | P1 | not_started |
| Y1.33 | experimental.todo flag | M5 | P2 | not_started |
| Y1.34 | model overrides and provider transport | M2 | P1 | not_started |
| Y1.35 | agent updates config file (config_edit) | M2 | P1 | not_started |
| Y1.36 | Migrate-from-V1 and Troubleshooting docs | M23 | P2 | not_started |
| Y1.37 | install script and release channels | M22 | P1 | not_started |
| Y1.38 | repo hygiene | M0 | P1 | not_started |
| Y1.39 | 'Building on X' non-affiliation notice | M1 | P2 | not_started |
| Y1.4 | read limits and paging | M5 | P0 | verified |
| Y1.5 | glob/grep defaults | M5 | P0 | verified |
| Y1.6 | edit unique-match requirement and formatter hook | M5 | P0 | verified |
| Y1.7 | Shell tool details | M5 | P0 | verified |
| Y1.8 | webfetch and websearch provider selection | M5 | P0 | verified |
| Y1.9 | question tool | M5 | P0 | verified |
| Y2.1 | Transcript row model | M4 | P0 | verified |
| Y2.10 | stay_silent and request_app_connection tools | M5 | P1 | not_started |
| Y2.11 | send_to_bot, hidden subagents and group rooms | M12 | P1 | not_started |
| Y2.12 | Screen leasing | M16 | P1 | not_started |
| Y2.13 | Idle suspend knobs | M16 | P1 | not_started |
| Y2.14 | VNC relay that hides credentials from the browser | M16 | P0 | verified |
| Y2.15 | rate-limit awareness and in-VM executor | M16 | P1 | not_started |
| Y2.16 | Compaction knobs | M13 | P1 | not_started |
| Y2.17 | Prompt cache key per agent+generation | M2 | P1 | not_started |
| Y2.18 | NO_SCHEDULER flag | M14 | P1 | not_started |
| Y2.19 | Backward-compatible rename path | M4 | P1 | not_started |
| Y2.2 | Model history stored separately | M4 | P0 | verified |
| Y2.20 | Exposure defaults | M3 | P0 | verified |
| Y2.21 | Honest "Project status" section | M26 | P1 | not_started |
| Y2.22 | voice: realtime secrets, hand_off_task, TTS/STT | M17 | P1 | not_started |
| Y2.23 | E2E script with prepared-audio fixture | M25 | P1 | not_started |
| Y2.24 | per-user SSE stream | M20 | P1 | not_started |
| Y2.25 | routines: cron, event triggers, check-ins | M14 | P1 | not_started |
| Y2.3 | last N screenshots inline (N=3) | M4 | P0 | verified |
| Y2.4 | Orphaned tool-call repair | M4 | P0 | verified |
| Y2.5 | Per-agent serial queue | M4 | P0 | verified |
| Y2.6 | Pending-turn persistence | M3 | P0 | verified |
| Y2.7 | approval buttons: Allow / Always allow / Don't allow | M3 | P0 | verified |
| Y2.8 | Auto-classification of read-only tools by slug | M15 | P0 | verified |
| Y2.9 | card and event row kinds | M19 | P1 | not_started |
| Y3.1 | 'offer only what works' principle | M19 | P1 | not_started |
| Y3.10 | Local-only sign-in | M3 | P0 | verified |
| Y3.11 | Mock agent | M2 | P0 | verified |
| Y3.12 | Invite gate | M20 | P1 | not_started |
| Y3.13 | setup script: generate-only, never overwrite | M3 | P0 | verified |
| Y3.14 | First-run screen offers existing resources first | M19 | P1 | not_started |
| Y3.15 | settings structure | M19 | P1 | not_started |
| Y3.16 | public API, webhooks, operator page | M20 | P1 | not_started |
| Y3.17 | project update proposals need approval | M13 | P1 | not_started |
| Y3.18 | large task files on compute side; local cache | M4 | P1 | not_started |
| Y3.19 | brand strings and assets in one place | M19 | P1 | not_started |
| Y3.2 | 'reuse before building' / 'server is only DB client' | M4 | P0 | verified |
| Y3.20 | docs set incl. security-model | M1 | P1 | not_started |
| Y3.21 | agent runs as administrator warning | M19 | P1 | not_started |
| Y3.3 | Versioned, idempotent, resumable provisioning steps | M19 | P1 | not_started |
| Y3.4 | Relay stores every run event | M4 | P0 | verified |
| Y3.5 | per-user concurrency limit and queue | M4 | P1 | not_started |
| Y3.6 | table ideas / schema additions | M4 | P0 | verified |
| Y3.7 | Scheduler tick duties | M14 | P1 | not_started |
| Y3.8 | Device-approval pairing flow | M20 | P1 | not_started |
| Y3.9 | Sign out / Sign out everywhere / Disconnect | M3 | P0 | verified |
| Y4.1 | /mcp chat command revives dormant servers instantly | M6 | P1 | not_started |
| Y4.10 | Skill library = one setup runbook per integration (21 units). | M9 | P1 | not_started |
| Y4.11 | config.yaml provider switch in two lines | M2 | P1 | not_started |
| Y4.12 | Deterministic template build | M22 | P1 | not_started |
| Y4.13 | version badge and zero-secrets release scan | M22 | P0 | verified |
| Y4.14 | 16-plugin / 13-MCP preset | M6 | P1 | not_started |
| Y4.2 | Chat-based onboarding via QR | M15 | P1 | not_started |
| Y4.3 | first-boot sign-in test-fire | M19 | P0 | verified |
| Y4.4 | Secret provider map | M3 | P2 | not_started |
| Y4.5 | supervised webhook bridge | M15 | P1 | not_started |
| Y4.6 | Telemetry plugin + chat-side trace query MCP | M21 | P1 | not_started |
| Y4.7 | Desktop-control plugin with 11 key-less tools | M16 | P1 | not_started |
| Y4.8 | Obsidian vault | M13 | P1 | not_started |
| Y4.9 | Persona file with rigor contract + coding-agent routing + desktop control plane | M7 | P0 | verified |
| Y5.1 | plugin.json manifest and config namespace | M10 | P1 | not_started |
| Y5.2 | Install from git URL one-liner | M10 | P1 | not_started |
| Y5.3 | Webhook subscription lifecycle | M15 | P1 | not_started |
| Y5.4 | webhook signature headers and no-secret rejection | M3 | P0 | not_started |
| Y5.5 | Reaction mapping table | M15 | P2 | not_started |
| Y5.6 | chat-id mapping cache | M15 | P1 | not_started |
| Y5.7 | status and gateway commands | M15 | P1 | not_started |
| Y5.8 | troubleshooting by exact error strings | M15 | P1 | not_started |
| Y5.9 | Linq API/iMessage/RCS/SMS excluded (Blocked for free) | M15 | P1 | not_started |
| Y6.1 | repo evidence docs cross-walk | M0 | P0 | not_started |
| Y6.2 | .verify-* and .build artifacts | M0 | P0 | not_started |
| Y6.3 | four surfaces: Cowork, Code, Duet, Fleet | M19 | P1 | not_started |
| Y6.4 | repo visibility: Public, 0 stars/forks | M1 | P0 | not_started |
| Z1 | Project environment lockfile | M9 | P1 | not_started |
| Z10 | Provider/model drift detector | M21 | P1 | not_started |
| Z11 | Dormant-integration health board | M15 | P1 | not_started |
| Z12 | Offline signed catalog updates | M22 | P1 | not_started |
| Z13 | "Why can't I do X?" explainer | M19 | P1 | not_started |
| Z14 | Pre-flight installer report | M22 | P2 | not_started |
| Z15 | Prompt-injection regression corpus | M3 | P1 | not_started |
| Z16 | Per-project cost budgets and "stop at budget" with summary | M21 | P1 | not_started |
| Z2 | Agent contract tests | M9 | P1 | not_started |
| Z3 | Redacted replay export | M4 | P1 | not_started |
| Z4 | Crash-safe turn journal | M4 | P0 | not_started |
| Z5 | Capability negotiation handshake | M20 | P1 | not_started |
| Z6 | Local-first sync via the user's own folder | M14 | P2 | not_started |
| Z7 | Household/OS-user separation | M22 | P2 | not_started |
| Z8 | Energy and cost estimator for local runs | M21 | P2 | not_started |
| Z9 | Natural-language policy editor | M3 | P1 | not_started |

## Acceptance framework

A feature is `verified` only when its acceptance criteria, automated tests, and real-runtime evidence pass. `implemented` means code exists with tests but end-to-end evidence remains. `blocked` is reserved for genuine owner-approval or missing-source dependencies. Source gap notes are not a blanket blocker.

## Prioritized build order

1. Security, trust, release, destructive-operation and repository-protection P0 items.
2. Local-model reliability and agent verification (B1.x, C3.x, C9.x).
3. Product surfaces, especially Cowork and Duet.
4. Engineering tools, workflows, memory, connectors, channels, Fleet.
5. Desktop, distribution, observability and documentation.
6. Remaining P1, then P2 features; P2 means later, never exclusion.

---

# Appendix V5 — Original Master Plan v5 (preserved)

# Keel Master Plan v5

Python + Electron + SQLite. Free-only. Proprietary, privately developed, publicly distributed through the official Keel website.
Prepared 20 November 2026 for an AI builder. Supersedes v4 (which recommended an Apache-2.0 public repo) and everything before it.

**How to use this file:** it is the single source of truth for the builder. Read Section 0 first, then work M0, then M1, then in order. Never skip the evidence rules (Section 3) or the approval gates (Section 0.3).

---

## 0. Non-negotiable owner requirements (override everything below)

Keel is the owner's **privately owned, proprietary software product**. These rules beat any conflicting text in this file, in earlier plans, or in any reference repo.

### 0.1 Private source
- The GitHub source repository must be **private**. Only the owner and explicitly authorized collaborators may access it.
- No public forks, public contributions, public source archives, public development artifacts, public internal docs, research, plans, or internal tooling.
- No `CONTRIBUTING.md` inviting outside contributions, no "open source" wording anywhere, no public issue tracker for source.
- **Never change repository visibility automatically.** The builder prepares the runbook (Appendix B) and **stops to ask the owner for explicit approval**. Same rule for history rewrites, force-pushes, repo deletion, collaborator changes and secret rotation.

### 0.2 Proprietary license
- Keel's original code is **proprietary, all rights reserved**. No MIT, Apache-2.0, GPL, or any open-source license on Keel's own code.
- Users receive permission to **install and use** the binary under an end-user license (EULA). They receive no right to the source and no right to redistribute.
- Proprietary status does **not** remove third-party obligations: every dependency, font, icon, model, voice, asset and reference-repo snippet keeps its own license, notices and attribution (Section 15).

### 0.3 Approval gates (builder must stop and ask)
| Gate | Action requiring explicit owner approval |
| --- | --- |
| G1 | Changing repo visibility (public to private, or any other change) |
| G2 | Rewriting Git history or deleting branches/tags/releases |
| G3 | Publishing the first public binary release from the new distribution endpoint |
| G4 | Adding collaborators or CI deploy credentials |
| G5 | Adopting final EULA text (needs the owner's legal name, governing law, lawyer review) |
| G6 | Any paid service, payment, subscription, license-key enforcement or mandatory account |
| G7 | Publishing extension/SDK docs publicly (default: not published) |

### 0.4 Public website and distribution
- The website is the public face: product info, capabilities, screenshots, downloads, install instructions, user docs, latest version, update/release notes.
- It must **not** expose: the source repo link, private dev docs, internal research, credentials, internal build artifacts, implementation details.
- Users download and install **without ever touching GitHub or the source repository**.
- Platforms: Windows installer; macOS Apple Silicon; macOS Intel; Linux AppImage, DEB, RPM.
- Every release has: version, SHA-256 checksums, release manifest, integrity verification, update checks, secure update download, rollback, install and upgrade instructions.
- The private repo may do development, CI/CD and release automation. Pipelines publish **only approved, allowlisted artifacts**. No private repo credentials, source archives or CI secrets ever leave it.

### 0.5 Free-first, local-first, commercial-ready (not commercial-now)
- Keel stays **free to use, local-first, offline-capable**: it boots and completes a coding task with no network, no account, no API key, using a local model (CI-enforced).
- The architecture must be **ready for later** free distribution by choice, optional paid plans, premium features, commercial licensing, enterprise and private organizational deployment (Milestone M24).
- Do **not** implement payments, subscriptions, license-key enforcement, feature locks or mandatory accounts unless the owner explicitly asks (gate G6).
- No paid third-party service anywhere in the plan. Optional adapters for services the **user** already has are allowed, never required, never bundled, never defaulted on.

---

## 1. Summary

- Keel (repo `eliosmernica15/keel`, site `keel-desktop.vercel.app`) is a "local-first multi-agent AI workstation (Keel Cowork, Keel Code, Keel Duet, Fleet)".
- Goal: a complete, free-to-use AI harness that takes the strongest ideas from five reference repos (opencode, orgo-teammates, openman, nicks-stack, clawdbot-channel-linq), keeps Keel's Python backend, Electron shell, theme and security model, and ships as a **closed-source product distributed from its own website**.
- **27 milestones (M0 to M26).** Each has deliverables, dependencies, acceptance tests. Section 13 maps v4 to v5 and the owner's original 27.
- New in v5: proprietary lockdown (M1), local site/app builder (M18), IDE bridges, voice, i18n, commercial-readiness seams (M24), a rebuilt distribution architecture (M22/M23) that works with a private repo.

## 2. What changed from v4 (conflict resolution log)

| v4 section | Conflict | v5 resolution |
| --- | --- | --- |
| 1 Summary, "public repo" | Described Keel as public | Keel is private and proprietary (0.1, 0.2) |
| 3.2 item 2 and D1 | Recommended Apache-2.0 / MIT | **Removed.** D1 is now "proprietary EULA text" (needs owner legal name, G5) |
| 3.2 item 3 and D2 | "Move captures out of the public repo (or into a private one)" | Repo becomes private, but captures still must not ship in any artifact and provenance is still reviewed (M0/M1) |
| 4.1 "repo visibility unchanged without owner approval" | Kept, but implied staying public | Kept as gate G1; target state is private |
| D3 Signing | SignPath Foundation (free for OSS only) | **Not eligible for proprietary software.** See 4.3 D3 |
| 6 "MIT repos, reuse" | Assumed open ecosystem | Reimplement from behavior; any copied MIT code keeps notices inside proprietary notices (Section 15) |
| 7 Docs "public docs site, extension author guides" | Exposed too much | User docs public; extension/SDK docs private by default (G7) |
| 11 M20 Distribution | Assumed GitHub Releases as public source | New private-repo-safe pipeline (M22) |
| 11 M21 docs, `CONTRIBUTING`-style items | Open contribution | Removed. Internal contribution guide stays private |
| 13 Licensing and attribution | Public license + notices | Rewritten as Section 15 |
| 14 Packaging and release | Release gate on public tag | Rewritten as Section 16 and Appendix C/D |
| 5 Architecture | No entitlement or policy seam | Added entitlement and managed-policy seams (Section 5, M24) |

## 3. Evidence rules and what has been verified

### 3.1 What was read in this session (20 Nov 2026) and its limits

| Source | Status |
| --- | --- |
| `github.com/eliosmernica15/keel` front page | Read. Shows **Public**, `main`, 108 commits, 0 stars, 0 forks, homepage `keel-desktop.vercel.app`. Root has `.build`, `.github/workflows`, `.verify-*` folders, `agent-reference-shots`, `keel/`, and many planning docs (`architecture.md`, `security-plan.md`, `licensing-and-provenance-review.md`, `training-data-plan.md`, `claude-code-evidence.md`, etc.). Listing was truncated ("View all files"), so a missing LICENSE file cannot be asserted from this page alone. |
| `keel/` source, tests, Electron renderer, folder pages | **Not readable by automated tools.** Every "already built" claim stays *claimed, not verified* until M0. |
| opencode (MIT, 226k stars) | README read: Build + Plan agents (Tab), `@general` subagent, desktop beta (dmg arm64/x64, win exe, deb/rpm/AppImage), install script, `.opencode/`, `sdks/vscode`, `.zed`, `specs/v2`, `nix`, 22 translated READMEs. Source not read. |
| orgo-teammates (MIT) | README read: Bots with role/look/effort/skills/memory, computer use, approval on write actions, delegation and group chats with @mentions, routines, memory + compaction, realtime voice with push-to-talk, Library, noVNC viewer via relay, safe-by-default server binding. |
| openman (MIT, name/logo trademarked) | README read: Agent/Chat/Plan tasks, follow-ups, branches, side chats, approvals/questions, projects with shared instructions and files, skills, custom MCP, automations, websites build/preview/publish, slides/docs/charts/audio, meeting notes (Whisper), task sharing, public API, operator page with usage caps, AES-256-GCM secrets, SSRF-safe fetch, signed webhooks, account export/delete, plus `NOTICE`, `TRADEMARKS`, `DISCLAIMER`, `THIRD_PARTY_NOTICES`. |
| nicks-stack (MIT) | README read: 13 MCP servers, SOUL.md persona, 21-skill runbook library, key-less/dormant integrations that revive within minutes, Obsidian vault notes, first-boot guided setup with QR pairing, webhook bridge, trace everything, secrets from a vault, **zero secrets in repo**. |
| clawdbot-channel-linq (MIT) | README read: channel plugin manifest, config reference, multi-account, DM `open/pairing/allowlist`, group `open/allowlist`, HMAC-SHA256 over `timestamp.rawBody`, 5-minute replay window, reactions/tapbacks, typing and read receipts, attachments, `tokenFile`/env token, chat-id cache. |

**Not done and must be done in M0:** read reference **source code, UI components and screens** locally; verify each LICENSE file (not just the README badge); inspect dependency licenses. Statements about reference UIs below describe **documented behavior**, not copied code.

**UI rule:** reference apps are Next.js/React/Bun-TypeScript; their components cannot drop into Keel's Electron renderer, and copying branded assets is a legal risk in a proprietary product. Take **structure, flows, states, forms and behavior**; take colors, type, spacing, icons and copy only from Keel's theme tokens.

### 3.2 Evidence rules for the builder
1. Statuses only: Complete and verified / Implemented, partially verified / Partially implemented / Not implemented / Blocked / Intentionally excluded.
2. Every row records source path, test path, end-to-end run. No evidence, no "complete".
3. Never fake provider output; never mark a test passed without running it; never publish an installer without verification.
4. Root planning docs describe a *planned* harness. They are specs, not proof.
5. No schema change without a migration. No secret in logs, ever.
6. Any statement about a third party's price, free tier or license in this plan is from general knowledge: **re-verify when selecting the dependency** and record the date.

## 4. Where Keel stands

### 4.1 Claimed done (verify in M0)
| Area | Claim | Verdict until M0 |
| --- | --- | --- |
| Python bridge/runtime, SQLite, sessions, SSE | Built | Unverified |
| Electron shell, Windows installer, cross-platform workflows | Built | Release reported; per-OS install untested |
| Provider adapters, local credential config | Built | Unverified |
| Permission/approval broker | Built | Unverified; non-configurable tier unconfirmed |
| Filesystem tools, terminal | Built | Depth unknown (PTY, process manager, LSP likely absent) |
| Fleet, MCP plumbing, skills infrastructure | Built | Likely partial |
| `/api/v2/` OpenCode-shaped layer | Built | Unverified |
| Release automation, manifest, SHA-256 | Built | Download page reportedly stale (v0.1.0 vs v0.1.1) |
| Tests | 454 passed, 10 skipped | Re-run |

### 4.2 Findings needing action now
1. **Repo is public today.** Per 0.1 the target is private; execute Appendix B only after owner approval (G1).
2. **Order of operations matters.** Existing installers may update from GitHub Releases. Flipping the repo private before a new feed exists breaks old clients and the download page. See Appendix B.
3. **Exposure window.** The repo has been public with 108 commits. Treat history as possibly cloned or cached: scan full history with gitleaks, rotate anything that ever looked like a secret, and ask about a history rewrite (G2). Making a repo private does not recall copies.
4. **Provenance risk.** `agent-reference-shots/`, `claude-code-evidence.md`, `agent-evidence*.md`, `prompt-pattern-analysis.md` look like captures/analysis of a third-party product. Not a legal judgment. Act on `licensing-and-provenance-review.md`. These must **never** enter an installer, website or docs bundle, and should leave the repo or move to a restricted archive.
5. **Root clutter:** `.verify-*`, `_check_*.py`, `_wf-findings-raw.json`, `FINAL-APPROVAL-GATE.md`, `_corrections-ledger.md`, model-training docs. Move to `docs/archive/` (private) or `.gitignore`. Training your own model remains out of scope.
6. **No license text** is confirmed in the repo, so today the default is all-rights-reserved but undocumented. M1 adds the explicit proprietary LICENSE and EULA.
7. **Planning docs are not implementation.**

## 5. Decisions

### 5.1 Locked
Python authoritative runtime; Electron shell and existing renderer; SQLite; Python enforces all permissions; local-first; no Supabase, Firebase, Postgres, Redis, Tauri, Node/Bun backend, PGlite or hosted vector DB; no hosted backend of any kind required to run Keel; existing data preserved via migrations; **private repo, proprietary license (Section 0)**.

### 5.2 Corrections to earlier plans
| Earlier said | Now |
| --- | --- |
| Public repo, Apache-2.0/MIT | Private repo, proprietary EULA |
| GitHub Releases on the source repo as the download source | Separate **binaries-only public endpoint** fronted by the Keel website (M22) |
| SignPath Foundation (OSS-only) | Not available; see D3 |
| GitHub artifact attestations as the provenance story | Verify availability for private repos on the free plan (believed limited); use owner-held **Ed25519 signatures** (minisign-style) as the primary integrity chain |
| Tauri, Node/Bun/Hono, PGlite, ngrok | Electron, Python, SQLite WAL, outbound-only connections |
| Docker Desktop sandbox | Optional Podman/Docker Engine, never required |
| JSONL as canonical store | SQLite canonical; append-only `events` table; JSONL export/import |
| macOS notarization in a free plan | Impossible without paid Apple membership; D3 |

### 5.3 Open decisions for the owner
- **D1 EULA identity (G5):** legal name or business name of the licensor, governing law and venue, contact email for legal/security notices. Builder drafts from Appendix A; a lawyer should review before release.
- **D2 Provenance:** after review, delete or restrict the third-party capture material; confirm none is in artifacts (automated scan, M1).
- **D3 Signing (free reality):**
  - Windows: free code-signing for proprietary software is **not** available through SignPath Foundation (OSS only). Cheap/paid options exist but are excluded here. Plan: ship unsigned with documented SmartScreen steps, SHA-256 + Ed25519 verification, and winget/Scoop manifests; revisit if the owner later accepts a paid certificate.
  - macOS: Developer ID + notarization requires a paid Apple membership. Plan: unsigned/ad-hoc, documented first-run (right-click Open / `xattr`), Homebrew **custom tap** cask. Revisit later.
  - Linux: Ed25519/GPG-signed artifacts and a signed APT/RPM repo (self-hosted static files).
- **D4 Parity target and "Keel Duet":** opencode sets product shape; please define what Keel Duet is (assumed: two-agent pair mode, e.g. builder + reviewer). See M12.
- **D5 Distribution host:** primary = Keel website domain rewriting to a **public binaries-only repository** (default name `keel-releases`, contains only installers, manifest, checksums, signatures, release notes). Alternatives: GitHub Pages from that public repo, Codeberg, SourceForge, a self-hosted static server. Re-verify free-tier terms, size limits and **commercial-use terms** (e.g. Vercel's free Hobby tier is for non-commercial use; migrate the site before charging anyone).
- **D6 Name check:** run a basic trademark conflict search for "Keel" in your target markets before wide distribution (not legal advice).
- **D7 Extension/SDK docs:** default private (G7).

## 6. Target architecture

```
Electron shell (existing renderer, Keel theme)
  main: secret prompt, notifications, tray, autostart, updater (verifies manifest + signature)
  renderer --HTTP+SSE on 127.0.0.1, per-launch bearer token, Origin/Host checks--+
                                                                                 v
Python daemon (authoritative)
  API (/api/v2 compatible + /api/keel/v1)
  Agent loop · tool registry · permission gate (Tier 1 rules, Tier 2 safety)
  Providers/model registry · MCP client+server · skills · plugins · hooks · commands
  Sessions+events · checkpoints · memory · scheduler/queue · channels · connectors
  Entitlement seam (always-allow now) · Managed-policy seam (optional file) · Traces/audit · cost ledger
     | separate processes only: Playwright, LSP servers, whisper.cpp, Ollama/llama.cpp,
     | plugin workers, optional container desktop
     v
  SQLite (WAL) + files under the Keel data dir; OS keychain holds master key
```

### Design rules (clean-room; Keel's own `architecture.md` is the reference)
1. Core is front-end agnostic: Electron, CLI, SDK, IDE bridges and an MCP-server surface drive the same loop.
2. Providers are leaves: one provider-neutral message/tool/usage model; tool calling, streaming, thinking, effort are optional capabilities. A model with none still works as a text agent.
3. **Never re-send a partially delivered response.** Preserve output, warn, do not retry.
4. Tool results have two renderings (model string, typed UI/audit payload). Errors and denials are data, not exceptions.
5. Output-size ladder: large outputs go to a session file with inline preview, on success and failure.
6. Two permission tiers. Tier 1: deny/ask/allow, first match wins, wildcards. Tier 2, non-configurable: protected-path table (test fails if it changes), destructive-command analyzer on the resolved command, consent-required tools, dangerous-mode interlock. No rule, hook, plugin, policy file or setting reaches Tier 2.
7. Compaction is a structured record with thrash detector and a three-rung overflow ladder.
8. Model roles: `main`, `summarizer`, `title`, `classifier`.
9. Dollar caps degrade to token caps for local models, never to unlimited.
10. Subagents are a trust boundary: exact tool allowlist, worktree isolation, depth/concurrency caps, reports scanned for instruction-shaped text.
11. MCP failures reach three audiences: operator status, typed errors, model note.
12. Instruction files merge, never suppress (`AGENTS.md` + Keel's own), with a diagnostic naming sources; subdirectory rules lazy-load.
13. Read-before-edit via observed-paths set restored on resume; edits are exact-match, UTF-8 safe.
14. Daemon authenticates even on localhost and rejects foreign Origin/Host.
15. **Dormant-until-configured** integrations (nicks-stack pattern): an unset key parks the integration quietly, it revives on hot-reload (`/reload` or a settings save), nothing crash-loops.
16. **Entitlement seam (proprietary-ready):** every feature that could ever be gated asks `entitlements.has("feature.id")`. The only provider today is `AllowAllEntitlements`. No license keys, no network checks, no feature locks (gate G6).
17. **Managed-policy seam:** optional admin file (`keel-policy.json`, signed or OS-protected path) can *tighten* settings (disable providers, force offline, pin update server, restrict connectors). It can never loosen Tier 2.
18. **No mandatory accounts, no mandatory telemetry.** Crash reports and traces stay local; the only network call Keel makes unprompted is the (disable-able) update check.

## 7. Capability harvest from the five references

All five show MIT on their pages. Verify each LICENSE file and dependency license in M0. **Default: reimplement from behavior.** If code is ever copied, keep its copyright and license text and list it in `THIRD_PARTY_NOTICES` (allowed inside a proprietary product, but the notice duty is mandatory). Names, logos, prompts and screenshots of the references are never used.

### 7.1 opencode (coding agent shape)
| Take | Free Keel implementation | M |
| --- | --- | --- |
| Headless server + thin clients + SDK | Python daemon; Electron, CLI, SDK, IDE bridges are clients | M20 |
| Build (full access) and Plan (read-only, asks before bash) agents, Tab toggle; `@general` subagent via @-mention | Same behavior; Plan cannot write even if config allows | M7, M12 |
| Agents/commands/skills as markdown+YAML, global + project merge, `.opencode/`-style project folder | `.keel/` project folder, same formats | M7, M9 |
| JSON-with-comments config + schema, `provider/model` naming, 75+ providers via a model catalog | JSONC + schema; bundled **offline** provider catalog file updated with releases | M2 |
| MCP stdio + remote, OAuth, `list/auth/logout/debug` | MCP client, OAuth PKCE | M6 |
| LSP tool, formatters, references | LSP manager, formatter hooks, reference store | M11 |
| Themes, keybinds, plugins | Keel theme tokens, keymap, plugin SDK | M10, M19 |
| VS Code SDK, Zed config, desktop app, install script, brew/pacman/nix/mise/winget style distribution | Keel VS Code extension and an Agent-Client-Protocol-style stdio bridge (verify protocol terms), Homebrew custom tap, winget/Scoop manifests, Nix flake optional | M20, M22 |
| 22 translated READMEs | UI + user docs i18n (en first; es, de, fr, sq, ja, zh-CN, ko, pt-BR, ru, tr planned) | M25 |
| Share links, hosted infra (sst, `infra/`) | **Excluded** (hosted). Replace with local read-only HTML/Markdown session export | M4 |

### 7.2 orgo-teammates (teammates)
| Take | Free Keel implementation | M |
| --- | --- | --- |
| Bots with name, look, role, instructions, thinking effort, skills, memory; one primary contact | Fleet agent profiles + avatar/color, effort setting, own memory | M12 |
| Computer use with live view, take over, Library of saved work | Browser/desktop viewer with Take over, Library panel | M16, M19 |
| Read actions auto-run; write actions pause; "remember my choice" | Approval cards with explicit scopes | M3, M19 |
| Delegation, subagents, group chats with @mentions | Task graph + group threads | M12 |
| Routines, event reactions, primary-bot check-ins at chosen times | Scheduler + digest/check-in automation | M14 |
| Durable memory, recall, compaction, idle consolidation, idle suspend | Memory system + idle consolidation job | M13, M14 |
| Realtime voice calls, voice choice/speed/preview, push-to-talk dictation | **Local** pipeline: VAD (silero, MIT) + whisper.cpp + Piper/Kokoro, push-to-talk | M17 |
| Safe defaults: bind 127.0.0.1, ignore dev-login off-localhost, refuse open sign-ups | Daemon defaults, `--listen` requires auth + explicit flag | M3 |
| Four desktops at once on a VM; cloud VM per user | **Excluded** (paid cloud). Local container desktop, 1 to N sessions | M16 |
| Planned: file-based skills, task recording, local companion, meetings | Skills (M9), record-a-skill (M9), local companion = the app itself, meeting notes (M17) | |

### 7.3 openman (agent workspace)
| Take | Free Keel implementation | M |
| --- | --- | --- |
| Tasks with Agent/Chat/Plan modes, follow-ups, branches, side chats, approvals AND questions, attachments, queue under load | Task model on sessions; `ask_user` tool with typed question cards | M4, M19 |
| Projects with shared instructions + reference files; agent-proposed project updates need approval | Project entity; proposals as diffs | M13 |
| Project sharing (members, editors) | **Local-only reinterpretation:** export/import signed project bundles; no multi-user server | M13 |
| Skills library, custom MCP connectors, automations on schedule/trigger | Same, local | M9, M6, M14 |
| Websites: build, preview, publish, full-stack site with DB, secrets, scheduled jobs, analytics, custom domain, element editor | **Local Sites builder:** static + local SQLite app scaffolds, live preview, element inspector, export; optional publish to the user's own free static host | M18 |
| Slides, documents, charts, speech/sound effects, meeting notes (Whisper) | python-pptx/docx/openpyxl/matplotlib; Piper TTS; whisper.cpp | M17 |
| Task sharing and collaboration | Export read-only HTML/Markdown transcript + signed bundle | M4 |
| Record a skill by demonstration | Record tool-call/UI trace to a draft skill | M9 |
| Public API, operator page, per-user caps, usage limits, health alerts | Local API (M20), "Admin" settings page, local caps and alerts | M14, M21 |
| Always-on worker, idempotent per-minute tick, signed webhooks, SSRF-safe fetch, AES-256-GCM secrets, security suites, account export/deletion | Same inside the daemon; **Data export and "erase everything"** tools | M14, M3, M21 |
| NOTICE, TRADEMARKS, DISCLAIMER, THIRD_PARTY_NOTICES, SECURITY.md (private reports), AGENTS.md, OPERATIONS/deploy docs | Proprietary equivalents: `EULA`, `NOTICE`, `TRADEMARKS`, `DISCLAIMER`, `THIRD_PARTY_NOTICES`, private security contact, internal `AGENTS.md` | M1 |
| Agent email address and phone number (paid vendors), Supabase, Orgo sign-in, Orgo/Claude credits | **Excluded.** Own IMAP/SMTP mailbox instead | M15 |

### 7.4 nicks-stack (agent template)
| Take | Free Keel implementation | M |
| --- | --- | --- |
| First-boot guided setup (model sign-in test fire, pairing QR, optional secret vault) | Wizard: detect runtime, probe model with a 1-token call, pair a channel by QR/code, optional connectors | M19 |
| Persona file (SOUL.md), rigor contract, routing rules | `PERSONA.md` per agent, merged with `AGENTS.md` | M7 |
| 21-skill runbook library, one runbook per integration | Bundled setup-runbook skills per connector/channel | M9 |
| 13 MCP servers, key-less dormant until configured, revive without restart | MCP presets catalog (all free/self-hosted), dormant state, hot-reload | M6, M15 |
| Obsidian-compatible markdown vault the agent reads and writes | Notes vault (plain Markdown folder, wikilinks), works with or without Obsidian | M13 |
| Everything traced and queryable in chat | Local traces + "show me what you did" tool | M21 |
| Desktop-control plugin (11 tools, key-less) | Desktop tool set behind consent | M16 |
| Template build and versioned publish | **Team Templates:** export/import signed agent-team packs (profiles, skills, MCP presets, persona) | M12 |
| Webhook bridge with auto tunnel; vault-secret resolution | Prefer **outbound** channels (long polling/socket) so no tunnel is needed; optional user-provided tunnel for inbound webhooks. Secrets via OS keychain; optional `file`/`env` providers | M15, M3 |
| Giving the agent a key in chat | **Avoid.** Out-of-band prompt only | M3 |
| Zero secrets in repo, verified by scan per release | gitleaks in CI + release gate | M1, M21 |
| Paid pieces (1Password, AgentMail, AgentPhone, AgentCard, Latitude, Honcho, Composio) | **Excluded** (see 7.6) | |

### 7.5 clawdbot-channel-linq (channels)
| Take | Free Keel implementation | M |
| --- | --- | --- |
| Plugin manifest + config schema per channel | `channel.json` manifest, validated | M15 |
| Multi-account per channel | Same | M15 |
| `dmPolicy` open/pairing/allowlist, `groupPolicy` open/allowlist, `allowFrom` lists | Same policies, default **pairing** and **allowlist** | M15 |
| HMAC-SHA256 over `timestamp.rawBody`, 5-minute window, constant-time compare | Same, plus replay cache | M3, M15 |
| Media attachments, reactions (emoji-to-reaction map), typing indicators, read receipts | Channel **capability matrix**; map emoji to each channel's native reactions | M15 |
| Token from file or env var instead of config | `tokenFile` / env / keychain reference | M3 |
| Chat-id cache with reset instructions, troubleshooting section | `keel channels doctor` | M15 |
| iMessage/RCS/SMS via the paid Linq API | **Excluded.** Free alternatives: Telegram, Discord, Matrix, Slack, email; SMS/iMessage marked Blocked-for-free | |

### 7.6 Not taken (paid, hosted, or unsafe)
Orgo (cloud computers, credits), Composio, AgentMail, AgentPhone, Linq, ElevenLabs, Latitude, 1Password, AgentCard, Honcho, Supabase, ngrok accounts, hosted share/inference services, xAI/Grok/OpenAI/Anthropic as **required** dependencies (optional user-key adapters only). **Excluded on purpose:** agent-controlled payments, unofficial WhatsApp libraries, any feature that sends user code to a Keel-operated server.

### 7.7 Additions beyond the references (all free)
- `keel doctor` (runtimes, models, keychain, ports, writable dirs, update feed reachability, fix hints).
- Record/replay of model sessions for deterministic tests.
- Per-task git worktree, diff review, commit/PR-draft text; no remote push without approval.
- tree-sitter repo map, ripgrep, optional sqlite-vec semantic search.
- Taint tracking: content from web, MCP, files, channels is untrusted and cannot trigger Tier-1 allows or secret reads.
- Local eval harness with a tool-call reliability score per model in the model picker.
- Hash-chained audit log; session export/import; signed skill/plugin/template packs.
- Offline switch blocking all non-loopback egress at the daemon.
- Prompt-based tool mode for models without native tool calling.
- Checkpoint/undo per turn; "explain this denial"; "why did the agent do that"; time-travel replay.
- Local **model advisor**: suggests models that fit the machine's RAM/VRAM (never auto-downloads without consent).
- **Context inspector:** shows exactly what is in the prompt, token counts per source.
- **Policy simulator:** test any command/path against the rules and Tier 2 before saving.
- **Local-only usage dashboard** (tokens, time saved estimates, tool failures).
- **Safe mode** launch flag (`--safe`): no plugins, no hooks, no connectors, to recover from a bad extension.

## 8. Free-only implementation choices

Verify licenses and terms at selection time (rule 3.2.6). "Offline" = works without internet after install.

| Need | Free path | Offline | Caveat |
| --- | --- | --- | --- |
| Models | Ollama, llama.cpp, any OpenAI-compatible local server | Yes | ~8 GB RAM for small models; weak models fail tool calls, hence capability probe + prompt tool mode. Show each model's license; never bundle weights |
| Database | SQLite WAL, FTS5, optional sqlite-vec | Yes | Existing |
| Secrets | `keyring` master key, AES-256-GCM (`cryptography`) | Yes | Linux without keyring needs passphrase fallback |
| Browser | Playwright + Chromium | Yes | One-time binary download; Chromium notices must ship |
| Desktop control | Optional Podman/Docker Engine container with noVNC | Yes | Windows needs WSL2; optional. Docker Desktop has commercial-use terms: do not require it |
| Code intelligence | pyright, typescript-language-server, gopls, rust-analyzer, tree-sitter | Yes | Detect and guide install; do not bundle |
| Speech | whisper.cpp / faster-whisper (STT); Piper / Kokoro (TTS); silero-vad | Yes | Check each engine, voice and model license before bundling; many voices have their own terms |
| Email | IMAP/SMTP of the user's mailbox | No | Own account |
| Chat channels | Telegram (long polling), Discord (gateway), Slack (Socket Mode), Matrix, email | Partly | Own bot tokens; `signal-cli` is GPL: separate user-installed process only |
| GitHub, GitLab, Jira, Linear, Notion, Google | Direct connectors or open MCP servers with the user's own OAuth app/token | No | Free tiers and OAuth verification rules change; never promise "free forever" |
| Scheduler | Own idempotent tick | Yes | |
| Tracing | OpenTelemetry-shaped spans in SQLite + built-in viewer | Yes | Optional export to self-hosted Jaeger |
| Sandbox | bubblewrap (Linux), Job Objects/restricted tokens (Windows), `sandbox-exec` (macOS, deprecated) | Yes | Best effort; rules are not a sandbox; docs must say so |
| Secret scanning | gitleaks | Yes | CI + pre-commit |
| Docs generation | python-pptx, python-docx, openpyxl, matplotlib | Yes | |
| Packaging | Electron + electron-builder (NSIS/MSI, dmg, AppImage, deb, rpm); Python via PyInstaller or Nuitka | Yes | Verify each license; see Section 14 |
| CI | GitHub Actions on the **private** repo | n/a | Free private-repo minutes are limited and macOS/Windows runners use multiplied minutes (verify current numbers). Mitigate: heavy matrix on release tags only, caching, optional free self-hosted runners on the owner's machines |
| Update feed hosting | Public binaries-only repo behind the website rewrite; mirrors list | n/a | D5 |
| Website hosting | Static site on the current host now; migrate if its free tier forbids commercial use | n/a | D5 |
| Obfuscation / hardening | Nuitka compile (Python), V8 bytecode (Electron main), asar integrity, no source maps | Yes | Deterrent only, see Section 14 |

## 9. UI/UX plan (reference structure, Keel theme)

M0 must capture real reference screens locally and Keel's current screens; M19 implements. **All visuals use Keel theme tokens** (read `keel/` theme file in M0; never hard-code colors, radii, spacing, fonts). Reference logos, wording and icons never appear.

### 9.1 Unified workspace layout
- **Left rail:** Projects; Sessions/Tasks (search, archive, fork tree, status dots); Fleet roster (agent avatars, state: idle/working/waiting/failed); Library shortcut; Settings.
- **Center:** thread with **mode switch Build / Plan / Chat** (Tab toggles Build/Plan; Agent/Chat/Plan wording available per openman), follow-ups, **branch from any message**, side chat, queued messages, attachments, `@` mentions (agents, files, MCP resources), `/` slash menu, composer with model + effort + agent selector chips.
- **Right dock (tabs):** Diff review · Files · Terminal · Browser/Desktop viewer (watch live, **Take over**) · Tool timeline · Trace · Library · Memory · Context inspector.
- **Top bar:** project/branch chip, model chip with reliability badge, cost/token meter, offline indicator, approval inbox count.
- **Command palette** (Ctrl/Cmd+K): commands, sessions, files, settings, models, agents, skills.
- **Status bar:** daemon health, update available, background jobs, connected channels.

### 9.2 Components to build (each with states: default, hover, focus, disabled, loading, error, empty)
Message bubble (user/assistant/tool/system), streaming text with stop button, reasoning/thinking collapsible, tool-call card (collapsed summary, expanded args/result, duration, retry), **approval card**, **question card** (single/multi-choice, free text), diff viewer (unified/split, per-hunk accept/reject), terminal pane (tabs, kill, resize), file tree, code viewer, task list with plan checklist, fork/branch graph, agent card, fleet timeline, memory row editor, skill card, plugin card, connector card (dormant/connecting/active/error), channel card, schedule row, workflow step editor, toast, modal, drawer, tabs, tooltip, empty states, skeleton loaders, banner (offline, update, safe mode), keyboard-shortcut overlay.

### 9.3 Forms (fields and validation)
| Form | Fields | Validation / behavior |
| --- | --- | --- |
| First-boot wizard | Runtime detect (Ollama/llama.cpp), model pick/pull, project folder, permission preset (Cautious / Balanced / Trusted), optional connectors, theme | Probe model with 1-token call; show specific failure; **no account step**; skip allowed |
| Provider | Type, base URL, key (out-of-band entry), default model, roles map | Test button runs capability probe; key never shown after save |
| Model | Context size, temperature, effort, tool mode (native/prompt/off) | Warn if probe disagrees |
| Permission rule | Tool, pattern, action (deny/ask/allow), scope (project/global) | Policy simulator; Tier-2 conflicts rejected with reason |
| Approval decision | Allow once / this task / this project / always for exact pattern / Deny + reason | Tier-2 items show no "always"; show resolved command and risk reason |
| MCP server | Name, transport (stdio/http), command or URL, env (secret refs), allowlist | Connect test; shows 3-audience errors |
| Skill install | Source (folder/git URL/zip), signature status | Preview manifest and permissions before install |
| Plugin install | Source, requested permissions | Consent per permission; incompatible version refused with reason |
| Connector | Provider, auth (OAuth/token), scopes | Dormant until configured; Revoke button |
| Channel | Type, token ref, policies (DM/group), allowFrom, webhook path | HMAC secret required for webhooks; pairing code flow |
| Agent profile | Name, avatar, role, instructions, effort, tools allowlist, skills, memory scope, model | Allowlist diff preview |
| Automation | Trigger (cron/interval/event), workflow/agent, caps, notify | Dry-run next 5 fire times |
| Project | Name, root(s), instructions, reference files, default agent | Path containment check |
| Memory item | Type, text, scope, source, pinned | Contradiction flag; delete removes from all indexes |
| Update settings | Check on/off, channel, mirror override | Shows last check and verification status |
| Data & privacy | Export all, erase everything, telemetry (local only) | Typed confirmation for erase |

### 9.3.1 Accessibility and i18n
Keyboard-complete, screen-reader labels, reduced motion, high-contrast theme, scalable text, RTL-ready layout, string catalog from day one (en baseline).

## 10. Database and migration plan
- Keep the existing SQLite file. Add `schema_migrations(version, applied_at, checksum)`; forward-only numbered migrations in `keel/db/migrations/`.
- **Before every migration:** automatic backup (`keel.db.bak-<version>`), integrity check; CI dry-runs migrations on copies of v0.1.0 and v0.1.1 databases.
- Rollback = restore backup; the updater refuses to downgrade across a schema version without it.
- Additive tables (reconcile with the real schema in M0): `events` (append-only, hash-chained), `tasks`, `task_edges`, `checkpoints`, `memory_items` (+FTS5, optional vec), `projects`, `agent_profiles`, `agent_runs`, `skills_installed`, `plugins_installed`, `mcp_servers`, `connectors`, `channels`, `hooks`, `workflows`, `workflow_runs`, `schedules`, `jobs`, `usage_ledger`, `audit_log` (hash-chained), `permission_rules`, `secrets_meta` (ciphertext only), `traces`, `sites`, `entitlement_state` (empty, reserved), `update_state`.
- WAL, `busy_timeout`, single writer queue, `PRAGMA foreign_keys=ON`.
- Export/import bundle (zip: DB snapshot + JSONL events), encrypted with a user passphrase option.

## 11. Security plan and gap analysis
**Gaps to verify in M0:** Tier-2 enforcement, daemon auth and Origin/Host checks, secret storage and log redaction, path containment vs symlinks/`..`, Windows reserved names/ADS, command analyzer coverage, prompt-injection handling, subagent allowlists, plugin isolation, update integrity, and **whether the shipped installer contains anything from the private repo that should not ship**.

**Controls (M3 onward):**
1. Per-launch bearer token, loopback bind, Origin/Host allowlist, no CORS wildcard.
2. Protected paths (`.git`, shell rc files, keychains, `~/.ssh`, Keel data dir, config) denied for write regardless of rules.
3. Destructive-command analyzer on the *resolved* command (aliases, `$()`, pipes, `sudo`, `rm -rf` variants, PowerShell equivalents).
4. Filesystem containment: canonicalize + realpath, deny symlink escape, project root plus explicit extra roots.
5. Secrets: OS keychain master key, AES-256-GCM at rest, redaction in logs/traces/errors, out-of-band entry, gitleaks in CI.
6. Taint labels on untrusted content; tainted content cannot auto-approve or read secrets; injection canary tests.
7. SSRF-safe fetch: block private/link-local/metadata ranges, re-check after redirects and DNS resolution.
8. Webhooks: HMAC-SHA256 over `timestamp.rawBody`, 5-minute window, constant-time compare, replay cache.
9. Plugins/MCP: out-of-process workers, declared permissions, scrubbed env, per-server allowlists, tool-description pinning.
10. Hash-chained audit log + tamper check command.
11. Supply chain: pinned/locked deps, `pip-audit`/OSV scan, SBOM (CycloneDX), reproducible builds where possible, **Ed25519 signatures on every release artifact and manifest**.
12. Offline mode: daemon-level egress block except loopback.
13. **Source-protection controls (new):** private repo hardening (Section 14.1), artifact allowlist scanner, no source maps, no dev docs in installers, secret scan of the built artifacts, license-header check.
14. **Update security:** manifest signed with an offline-held Ed25519 key; public key embedded in the app; HTTPS only; version monotonic (no downgrade without rollback flow); hash check before install; atomic swap; keep previous version for rollback.
15. **Private vulnerability reporting:** security contact by email (no public issue tracker for security).


---

# Appendix A1 — Addendum: Missed Features (preserved)

# Keel Plan v5 Addendum: Features and Tools Missed

Contains **only** items that are not already in `Keel_Master_Plan_v5.md`. Everything is free to use; nothing paid is required. Milestone numbers use the v5 numbering (M2 providers, M3 security, M4 sessions, M5 tools, M6 MCP, M7 agents, M8 hooks/workflows, M9 skills, M10 plugins, M11 code intel, M12 fleet, M13 memory, M14 scheduler, M15 connectors/channels, M16 browser/computer, M17 multimodal/voice, M18 sites, M19 desktop UI, M20 API/SDK, M21 observability, M22 distribution, M23 website, M24 commercial seams, M25 hardening/i18n, M26 v1.0).

**Evidence tags:** `[R]` = seen in a reference README this session. `[K]` = from general knowledge of that product; verify against its source/docs in M0 before relying on it. `[S]` = my suggestion, not from a reference. **Licensing rule still applies:** reimplement from behavior; keep notices for anything copied; no reference names, logos, prompts or screenshots.

**Priority:** P0 = needed for a strong v1.0, P1 = high value, P2 = later.

---

## A. Missed from the five references

### A1. opencode

| ID | Feature | Free implementation | M | Pri | Tag |
| --- | --- | --- | --- | --- | --- |
| A1.1 | Non-interactive run mode (`keel run "prompt"`, pipes, JSON output, exit codes) for scripts and CI | CLI client over local API | M20 | P0 | K |
| A1.2 | Attach a CLI/TUI/IDE client to an already-running daemon (`keel attach`) | Same bearer-token API | M20 | P0 | K |
| A1.3 | **Terminal UI front-end** (full TUI, not only Electron) | Textual or prompt_toolkit client | M20 | P1 | R |
| A1.4 | **Local web UI** served on loopback (`keel web`) for browser access | Renderer built as web bundle, same auth | M20 | P1 | K |
| A1.5 | `/init` command: scan repo and generate `AGENTS.md` | Repo map + summarizer role | M7 | P0 | K |
| A1.6 | Inline shell via `!cmd` prefix in composer (goes through permission gate) | Composer parser | M19 | P1 | K |
| A1.7 | Slash commands: `/undo /redo /compact /export /models /themes /details /editor /share-local` | Command registry | M7 | P0 | K |
| A1.8 | Open file/diff in user's `$EDITOR` / VS Code | Spawn editor | M19 | P1 | K |
| A1.9 | Image paste/drag into composer, fuzzy `@file` search | Renderer + ripgrep | M19 | P0 | K |
| A1.10 | `todo` tool (agent keeps a visible task checklist), separate from the plan | Tool + UI pane | M5 | P0 | K |
| A1.11 | `webfetch` tool and `websearch` tool with **free** backends | Direct fetch (SSRF-safe); self-hosted SearXNG as optional separate process; no paid search API | M5 | P0 | K |
| A1.12 | Per-agent tool enable/disable and per-agent permission overrides | Agent frontmatter | M7 | P0 | K |
| A1.13 | Custom tools as code files dropped in `.keel/tools/` (Python) | Tool loader under permission gate | M5, M10 | P0 | K |
| A1.14 | `instructions` config: extra instruction files by glob or URL | Instruction merger | M7 | P1 | K |
| A1.15 | `small_model` for titles/summaries (already a role) plus per-agent model override | Model roles | M2 | P1 | K |
| A1.16 | Configurable leader-key keybinds, custom theme JSON files | Keymap + theme loader | M19 | P1 | K |
| A1.17 | Session import/export commands and `keel stats` (usage by model/day) | Ledger queries | M4, M21 | P1 | K |
| A1.18 | `keel agent create` wizard, `keel models`, `keel auth` subcommands | CLI | M20 | P1 | K |
| A1.19 | **GitHub Actions mode**: run Keel headless in the user's own CI to answer issues/PR comments | `keel run` + example workflow (user's own repo) | M20 | P2 | K |
| A1.20 | Watcher ignore list, auto-update toggle, env-var overrides (`KEEL_*`) | Config | M2, M22 | P1 | K |
| A1.21 | Remove versions older than X before install notice | Installer pre-check | M22 | P2 | R |
| A1.22 | `AGENTS.md` for the builder itself (internal) describing layout and conventions | Private doc | M0 | P0 | R |

### A2. orgo-teammates

| ID | Feature | Free implementation | M | Pri | Tag |
| --- | --- | --- | --- | --- | --- |
| A2.1 | **Voice-to-task handoff**: a voice session hands work to the same agent loop and reads results back | Local VAD + STT + TTS bridging to the loop | M17 | P1 | R |
| A2.2 | System-wide push-to-talk dictation hotkey (types into any app) | Electron global shortcut + local STT | M17 | P1 | R |
| A2.3 | Per-agent **persistent browser profile** and per-agent workspace folder | Playwright persistent contexts | M16 | P0 | R |
| A2.4 | Idle suspend/wake of heavy resources (browser, container desktop, LSP) | Resource manager | M16 | P1 | R |
| A2.5 | Group-chat loop guards (agents @mentioning each other endlessly) | Hop limit, cooldown, cost cap | M12 | P0 | S |
| A2.6 | Primary-agent daily check-in/digest at chosen times | Scheduler automation template | M14 | P1 | R |
| A2.7 | Documented `.env.example`-style config reference for every setting | Generated from config schema | M2 | P1 | R |
| A2.8 | Local Playwright E2E that exercises real flows (chat, tools, viewer, search, connections, voice, groups, settings) | Extend test suite | M25 | P0 | R |
| A2.9 | Memory-consolidation and history-compaction **tunable knobs** surfaced in settings | Config + UI | M13 | P1 | R |

### A3. openman

| ID | Feature | Free implementation | M | Pri | Tag |
| --- | --- | --- | --- | --- | --- |
| A3.1 | **Outgoing signed webhooks** with retry/backoff and delivery log | Outbox table + worker | M14 | P1 | R |
| A3.2 | Idle task-workspace garbage collection (temp folders) | Scheduler job with dry-run | M14 | P1 | R |
| A3.3 | **Mock/scripted agent** for UI development and tests (deterministic scripted runs) | Fake provider driven by fixtures | M2, M19 | P0 | R |
| A3.4 | Interactive **questions** from agent mid-task with timeout and default answer | `ask_user` tool (partly in v5) + timeout policy | M5 | P0 | R |
| A3.5 | Setup script that generates local secrets idempotently and prints what is missing (`keel setup`) | CLI | M3 | P1 | R |
| A3.6 | "Sign out everywhere / disconnect" equivalent: **revoke all client tokens** and reset daemon key | Token table + UI | M3 | P0 | R |
| A3.7 | Honest "Project status" page listing what is proven end-to-end vs built-but-unproven | Generated from `parity.json` into the app's About screen | M26 | P1 | R |
| A3.8 | Site tools: secrets manager, DB browser, scheduled jobs, analytics, element editor for generated sites | Inside M18 builder, local only | M18 | P2 | R |
| A3.9 | Operator-style **Admin page** (limits, alerts, health, background job table) | Settings > Admin | M21 | P1 | R |
| A3.10 | Per-vendor **cost caps with daily and monthly windows** | Ledger + enforcement | M21 | P0 | R |
| A3.11 | Deploy/operations docs for headless mode (`keel serve` on a home server) | Docs + systemd unit | M20, M23 | P1 | R |

### A4. nicks-stack

| ID | Feature | Free implementation | M | Pri | Tag |
| --- | --- | --- | --- | --- | --- |
| A4.1 | **OS service supervision**: daemon as systemd user unit / launchd agent / Windows scheduled task, watchdog, crash-loop backoff | Installer option + `keel service install` | M14, M22 | P1 | R |
| A4.2 | Deterministic, reproducible template/package build (stable tarball, pinned versions) | Reproducible build flags | M22 | P1 | R |
| A4.3 | MCP presets catalog limited to free/self-hosted servers (filesystem, git, fetch, SQLite, time, memory, Playwright, sequential-thinking, etc.), one-click add, dormant until configured | Bundled JSON catalog | M6 | P0 | R |
| A4.4 | Rigor contract in persona (verify before claiming done, cite evidence) as default agent preamble | Persona file | M7 | P0 | R |
| A4.5 | Coding-agent routing rules (which sub-agent/model for which task type) in the persona | Router config | M12 | P1 | R |
| A4.6 | "Test-fire" check for every integration after saving credentials | Generic `probe()` in connector SDK | M15 | P0 | R |
| A4.7 | Secret providers beyond keychain as user choice: env file, command (`pass`, `bw` CLI the user already owns) | Provider interface, never bundled | M3 | P2 | R |
| A4.8 | Release scan proving **zero secrets in artifacts** on every release | gitleaks on built installers | M22 | P0 | R |

### A5. clawdbot-channel-linq

| ID | Feature | Free implementation | M | Pri | Tag |
| --- | --- | --- | --- | --- | --- |
| A5.1 | **Gateway** process concept with `status`, start/stop, and a list of running channels | `keel gateway` | M15 | P0 | R |
| A5.2 | Install a channel/plugin from a git URL or local link for development (`install --link`) | Dev-link mode in plugin manager (private/local sources only unless G7) | M10 | P1 | R |
| A5.3 | **Account-level config inheritance** (account overrides channel defaults) | Config resolver | M15 | P0 | R |
| A5.4 | **Delivery fallback chain** (preferred service, then fallback) | Channel delivery policy | M15 | P1 | R |
| A5.5 | Outbound message state machine: queued, sent, delivered, read, failed with retries and dedupe by message id | Table + worker | M15 | P0 | R |
| A5.6 | Webhook subscription helper (register, list, rotate secret) as a CLI command | `keel channels webhook` | M15 | P1 | R |
| A5.7 | Per-channel troubleshooting checklist surfaced in UI when a channel fails | Rules table | M15, M19 | P1 | R |

---

## B. My suggestions to make Keel far more advanced (all free)

### B1. Making weak local models reliable (biggest free advantage)
| ID | Feature | Detail | M | Pri |
| --- | --- | --- | --- | --- |
| B1.1 | **Grammar/JSON-schema constrained decoding** for tool calls | Use llama.cpp grammars / Ollama structured output so even small models emit valid tool calls | M2 | P0 |
| B1.2 | Tolerant tool-call parser + **repair loop** | Fix trailing commas, wrong quotes, missing fields; re-ask once with the error | M2 | P0 |
| B1.3 | Difficulty-based **model router** | Small model first, escalate on failure/low confidence; optional remote only if the user enabled it | M2 | P1 |
| B1.4 | Prefix/KV-cache reuse | Keep stable prompt prefix to speed up local inference | M2 | P1 |
| B1.5 | Smart context management | Tool-output pruning, duplicate-file dedupe, sliding window, per-source token budgets | M4 | P0 |
| B1.6 | **Model download manager** | Resume, SHA-256 verify, disk-space check, license display, delete/GC | M2 | P0 |
| B1.7 | Hardware detector and quantization advisor | RAM/VRAM/CPU, suggests model size and quant; GPU backend hints | M2 | P1 |
| B1.8 | Local embedding + reranker models | For semantic search without any hosted API | M11, M13 | P1 |
| B1.9 | **Compare mode (arena)** | Same prompt on N models side-by-side, ratings saved to the local eval set | M19, M21 | P1 |
| B1.10 | Speculative/draft decoding toggle where the runtime supports it | Config passthrough | M2 | P2 |

### B2. Agent workflows and engineering skills
| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| B2.1 | **Verification loop**: auto-detect test/lint/type commands, run after edits, feed failures back, stop at "definition of done" checklist | M7 | P0 |
| B2.2 | Spec-driven mode: spec, task breakdown, implement, verify, with approvals between stages | M7 | P1 |
| B2.3 | **Keel Duet default design**: builder agent + independent reviewer agent with different model/prompt; reviewer can only comment | M12 | P0 |
| B2.4 | Specialist agents shipped as bundled markdown: code reviewer, security reviewer, test writer, refactorer, docs writer, dependency upgrader, merge-conflict resolver, bisect helper, changelog and PR-description writer | M7, M9 | P1 |
| B2.5 | Deep-research mode with citations, local files plus web, saved as a report | M17 | P1 |
| B2.6 | Local **RAG knowledge bases** over folders, PDFs, docs; file watcher; citations with file and line | M13 | P0 |
| B2.7 | Offline documentation packs (language/library docs) the agent can search | M13 | P2 |
| B2.8 | Notebook/REPL tool for data analysis with inline charts | M5 | P1 |
| B2.9 | Read-only **database explorer** tool (SQLite, Postgres, MySQL via user's own connection), write needs approval | M15 | P1 |
| B2.10 | HTTP/API tester with saved collections | M15 | P2 |
| B2.11 | Diagram tools: Mermaid and Graphviz rendering offline | M17 | P1 |
| B2.12 | OCR and document parsing (Tesseract, PDF text/tables) with license check | M17 | P1 |
| B2.13 | Optional local image generation (user-installed ComfyUI/diffusers, model licenses shown) | M17 | P2 |
| B2.14 | Prompt library with variables, snippets, "improve my prompt" helper | M19 | P1 |
| B2.15 | Macro/workflow recorder from chat history into a reusable workflow | M8 | P1 |
| B2.16 | Workflow and team template **gallery** (bundled, offline) | M8, M12 | P1 |

### B3. Sandboxing and safety beyond v5
| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| B3.1 | **WASM/Pyodide sandbox** for running untrusted generated code with no Docker | M5 | P1 |
| B3.2 | Container sandbox with CPU, memory, time and network limits (optional Podman) | M5 | P1 |
| B3.3 | **Dry-run mode**: agent plans and shows every side effect, executes none | M7 | P0 |
| B3.4 | Read-only session mode and per-project **network egress allowlist** per tool | M3 | P0 |
| B3.5 | **Egress log / privacy dashboard**: exactly what was sent to which provider and when | M21 | P0 |
| B3.6 | PII/secret **redaction before sending to any remote provider** (regex + small local classifier), with preview | M3 | P0 |
| B3.7 | Local prompt-injection classifier and canary tokens in fetched content | M3 | P1 |
| B3.8 | Output DLP: block agent from writing secrets into files, commits or messages | M3 | P0 |
| B3.9 | **Global kill switch** (hotkey and tray): stop all agents, revoke tokens, freeze scheduler | M3, M14 | P0 |
| B3.10 | Optional app-lock passphrase and auto-lock on idle | M3 | P2 |
| B3.11 | Provider **circuit breaker**, retry/backoff, health score, automatic failover | M2 | P0 |
| B3.12 | Immutable, exportable audit bundle with verification tool | M3 | P1 |

### B4. Desktop experience
| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| B4.1 | Global quick-ask hotkey overlay (spotlight style) | M19 | P1 |
| B4.2 | `keel://` deep links, `keel .` to open a folder, "Open with Keel" shell integration, shell completions | M19, M22 | P1 |
| B4.3 | Multi-window, detachable and split panels, saved workspace layouts | M19 | P1 |
| B4.4 | Message edit/regenerate, pin, bookmark, tags/folders, semantic conversation search | M4, M19 | P1 |
| B4.5 | Rich rendering: Markdown, Mermaid, LaTeX, image/PDF preview, copy and apply buttons on code blocks | M19 | P0 |
| B4.6 | Fleet views: kanban task board, agent org chart, cost per agent, live "agent wall" | M12, M19 | P1 |
| B4.7 | Observability views: token waterfall, flame graph, prompt diff between turns, slow-tool detector | M21 | P1 |
| B4.8 | Phone companion: **LAN web app with QR pairing** and pinned self-signed TLS (control and approvals from phone, no cloud) | M20 | P2 |
| B4.9 | Optional vim keybindings in composer; dyslexia-friendly font option (OFL fonts, notices) | M19 | P2 |
| B4.10 | Portable mode, multiple profiles (work/personal data dirs), relocatable data dir | M22 | P1 |
| B4.11 | Scheduled **encrypted backups** with restore wizard; optional E2EE folder sync of settings/memory via the user's own synced folder | M14, M22 | P1 |
| B4.12 | `keel doctor --bundle`: redacted diagnostics zip the user can send to support | M21 | P0 |
| B4.13 | Auto-rollback if a new version fails to start 3 times | M22 | P0 |
| B4.14 | Delta updates and optional beta channel (opt-in) | M22 | P2 |

### B5. Website, docs and trust (public, no source exposure)
| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| B5.1 | Download page with OS and CPU auto-detect, file size, SHA-256, "how to verify" guide for Windows/macOS/Linux | M23 | P0 |
| B5.2 | `latest.json` plus release-notes RSS/JSON feed and version history | M23 | P0 |
| B5.3 | System requirements, model-size guide, first-run guide for unsigned installers (SmartScreen, Gatekeeper) | M23 | P0 |
| B5.4 | Offline-capable docs search (static index) and versioned docs | M23 | P1 |
| B5.5 | Privacy page ("what Keel does not collect"), EULA page, third-party notices page, SBOM download | M23 | P0 |
| B5.6 | Auto-generated screenshot gallery from E2E runs; short recorded demo replays | M23 | P1 |
| B5.7 | Curated public roadmap and FAQ, comparison page, press kit, `mailto` support (no third-party form service) | M23 | P2 |
| B5.8 | Localized website using the same string catalogs | M25 | P2 |
| B5.9 | Static status page for update feed and mirrors | M23 | P2 |

### B6. Commercial-readiness extras (design only, nothing enforced; gate G6)
| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| B6.1 | Reserved offline **signed license token** format and verifier module, disabled and unused | M24 | P2 |
| B6.2 | Edition/channel field in manifest and About screen (value "standard") | M24 | P2 |
| B6.3 | Enterprise: silent-install flags for MSI/pkg/deb/rpm, Windows Group Policy templates (ADMX), macOS managed-preferences plist | M24 | P2 |
| B6.4 | Private org **update mirror** (signed manifests, custom feed URL) and private extension registry | M24 | P2 |
| B6.5 | Compliance pack: security whitepaper, accessibility conformance report, data-flow diagram, SBOM export, DPA/EULA templates (lawyer review) | M24 | P2 |
| B6.6 | Per-organization audit export format and retention settings | M24 | P2 |

### B7. Quality engineering and builder workflow
| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| B7.1 | Property-based and fuzz tests for path containment and the command analyzer; mutation testing on the permission gate | M3, M25 | P0 |
| B7.2 | Golden-file tests for prompt assembly; chaos tests (kill daemon mid-turn, disk full, DB locked); soak tests | M25 | P0 |
| B7.3 | Accessibility audit (axe) and visual regression in CI | M25 | P1 |
| B7.4 | Performance budgets: cold start, idle memory, installer size, time to first token overhead | M21, M25 | P0 |
| B7.5 | Flaky-test quarantine with owner and expiry | M25 | P1 |
| B7.6 | Machine-readable task index (`PLAN-INDEX.json`): one entry per feature ID with status, evidence path, test path | M0 | P0 |
| B7.7 | Architecture Decision Records (ADRs), commit convention, pre-commit hooks, devcontainer-free dev setup script | M0 | P1 |
| B7.8 | Feature-flag registry with kill-switch config for risky features | M3 | P1 |
| B7.9 | Per-milestone kickoff prompt file for the AI builder with explicit "stop and ask" points | M0 | P1 |

---

## C. Suggested build order for this addendum
1. **P0 first, early:** B1.1, B1.2, B1.5, B1.6, B3.3 to B3.9, B3.11, A3.3, A3.6, A3.10, B7.6.
2. **With the matching milestone:** every other P0 in the milestone named in its row.
3. **After v1.0 candidate is green:** all P2 rows.
4. Every row gets an ID in `parity.json` with status and evidence; no row is "complete" without a test.


---

# Appendix A2 — Addendum: More Features (preserved)

# Keel Plan v5 Addendum 2: Even More Features and Tools

Contains **only** items not already in `Keel_Master_Plan_v5.md` or `Keel_Plan_v5_Addendum_Missed_Features.md`. Everything is free to use; nothing paid is required. Milestone numbers follow the v5 numbering.

**Tags:** `[T]` = visible in a reference repo's file tree or README this session; `[K]` = general knowledge, verify in M0; `[S]` = my suggestion. A deeper fetch of reference docs (e.g. `docs/ARCHITECTURE.md`) was blocked by the tool this session, so source-level details still need M0. **Priority:** P0 / P1 / P2. Licensing rule unchanged: reimplement from behavior, keep notices for anything copied, never use reference names or assets.

---

## A. Still missed from the references (tree and README level)

| ID | Feature | Free implementation | M | Pri | Tag |
| --- | --- | --- | --- | --- | --- |
| C1.1 | Repo hygiene stack seen in opencode: pre-commit hooks, editorconfig, linters, lockfiles, dependency **patch** folder, changelog file, release scripts folder | ruff, pyright/mypy, eslint/oxlint, pre-commit, `patches/` policy, generated CHANGELOG | M0 | P0 | T |
| C1.2 | More package-manager distribution: Scoop, Chocolatey, Flatpak, Snap, AUR (binary PKGBUILD), Nix flake (opencode ships several) | Manifests generated by the release job; verify each store accepts proprietary freeware | M22 | P1 | T |
| C1.3 | Dev-container-free contributor setup script and `AGENTS.md` for AI builders | Private doc + `make setup` | M0 | P1 | T |
| C1.4 | **Screen-share/recording safe mode** (orgo-teammates warns never to show `.env`/dashboards on screen): mask secrets, emails, paths and tokens in UI while on | Renderer mask layer + hotkey | M19 | P0 | T |
| C1.5 | Per-integration **builder/operator guides** (orgo ships separate integration guides) | One short doc per connector/channel, shown in-app | M15, M23 | P1 | T |
| C1.6 | Agent "looks": avatar, color, voice per agent, voice preview and speed | Avatar picker + Piper voice list | M12, M17 | P1 | T |
| C1.7 | Meeting recorder: capture system/mic audio, local transcript, **speaker labels** (optional), summary, action items, link to project | whisper.cpp + local diarization where license allows | M17 | P1 | T |
| C1.8 | Notes vault extras: backlinks, graph view, daily notes, templates (nicks-stack uses an Obsidian vault) | Markdown index + graph pane | M13 | P1 | T |
| C1.9 | Plugin **presets bundle** (nicks-stack ships a 16-plugin config) | Preset = signed bundle of plugins + MCP + skills | M10 | P1 | T |
| C1.10 | Draft-only social/content skills (posts, threads, SEO notes); nothing posts without approval | Skills; no write to external accounts by default | M9 | P2 | T |
| C1.11 | Local task executor inside the container desktop for faster desktop actions (orgo "planned") | Small agent-side executor process | M16 | P2 | T |
| C1.12 | Client pairing allowlist for LAN/headless access (analog of orgo's `ALLOWED_EMAILS`) | Paired-client table, revoke per client | M20 | P0 | T |

---

## B. Product surfaces (Cowork, Code, Duet, Fleet)

The repo name lists four surfaces but v5 is mostly the Code side. Make each explicit so the builder does not under-build the others.

| ID | Surface | Definition and features | M | Pri |
| --- | --- | --- | --- | --- |
| C2.1 | **Keel Cowork** (knowledge work) | Folder-scoped assistant for non-coding work: file organizer with preview and undo, batch rename, PDF/Office read and write, spreadsheet cleanup and analysis, document Q&A with citations, email drafting and inbox triage via IMAP, local calendar (ICS/CalDAV), meeting prep, scheduled reports, form filling, translation, writing with a saved style profile | M17, M15 | P0 |
| C2.2 | **Keel Code** | Everything coding (the v5 core) | M5 to M11 | P0 |
| C2.3 | **Keel Duet** (assumed pair mode, confirm D4) | Live pairing: inline ghost-text completion from a local FIM-capable model, follow-the-cursor context, "you drive / agent drives" handoff, reviewer agent comments in the editor | M12, M20 | P1 |
| C2.4 | **Fleet** | Many agents, board, org chart, budgets, timelines | M12 | P0 |
| C2.5 | Surface switcher with per-surface default agents, tools and permissions | UI + config | M19 | P0 |

---

## C. Agent intelligence and autonomy

| ID | Feature | Detail | M | Pri |
| --- | --- | --- | --- | --- |
| C3.1 | **Best-of-N with test selection** | Generate N candidate patches, run tests, keep the passing/smallest one; great for weak local models | M7 | P0 |
| C3.2 | **Doom-loop and stuck detector** | Repeated identical tool calls or no-progress turns trigger a break, a hint, then escalation | M4 | P0 |
| C3.3 | **Goal mode / overnight mode** | Long autonomous run with budget, checkpoints, approval gates and a morning report | M14 | P1 |
| C3.4 | Think-harder slider | Maps to effort, sampling count, critic pass, token budget | M2, M19 | P1 |
| C3.5 | Planner / critic / executor roles | Separate prompts, optionally separate models | M7 | P1 |
| C3.6 | Map-reduce refactors | Subagents per file group, merge, conflict handling | M12 | P1 |
| C3.7 | **Reflection with approval** | After a task, propose memory/skill updates and a short lessons-learned entry; user approves | M13 | P1 |
| C3.8 | Failure postmortems stored per project | Auto-written, searchable | M13 | P2 |
| C3.9 | Cost and time **estimate before run**, with confidence | From history | M21 | P1 |
| C3.10 | Uncertainty policy | Agent flags low confidence; factual web claims require citations | M7 | P1 |
| C3.11 | Style learning | Extract a project style guide from linter configs and sample files | M11 | P2 |
| C3.12 | Context packs and a **context budget UI** | Attach curated doc bundles; slider per source | M19 | P1 |

## D. Code intelligence and engineering tools

| ID | Feature | Free implementation | M | Pri |
| --- | --- | --- | --- | --- |
| C4.1 | **Debugger integration via DAP**: breakpoints, step, inspect, so the agent can debug for real | debugpy, node inspector, delve etc. (user-installed) | M11 | P1 |
| C4.2 | Symbol, call and dependency **graph** with impact analysis ("what breaks if I change X") | tree-sitter + SQLite graph | M11 | P1 |
| C4.3 | Change-risk score and impacted-test selection | Graph + coverage data | M11 | P2 |
| C4.4 | Structural search and codemods | ast-grep, libcst (verify licenses) | M11 | P1 |
| C4.5 | Static analysis ingestion (SARIF in/out) | ruff, bandit, eslint; note semgrep rules may carry non-commercial terms, so prefer own rules | M11 | P1 |
| C4.6 | **Project security scans for the user**: secrets (gitleaks), dependency CVEs (OSV), SBOM of the user's project, license-compliance report | Offline OSV DB mirror optional | M11 | P1 |
| C4.7 | Profiling and benchmark agent | py-spy, cProfile, hyperfine-style runner | M11 | P2 |
| C4.8 | Log/process/port inspector, docker-compose helper, service health probes | Tools behind permission gate | M5 | P1 |
| C4.9 | Git extras: stacked commits, hunk staging, conflict resolver, blame-aware context, submodule and monorepo awareness, signed commits with the user's own key | git CLI | M11 | P1 |
| C4.10 | **Remote targets**: run on the user's SSH servers, WSL, devcontainers; remote daemon over SSH tunnel | OpenSSH | M20 | P1 |
| C4.11 | Browser devtools tools (console, network, performance) and **visual diff** of UI before/after; screenshot-to-code | Playwright | M16 | P1 |
| C4.12 | Terminal session recording and replay | pty log + player | M5, M21 | P2 |
| C4.13 | Issue-to-change pipeline from a markdown backlog or the user's own tracker token | Connectors | M15 | P2 |
| C4.14 | Auto-generated architecture docs and diagrams kept in sync with code | Mermaid | M11 | P2 |

## E. Workflows and automation (extra depth)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| C5.1 | Deterministic (no-LLM) nodes, loop/map nodes, sub-workflows, typed inputs/outputs with JSON Schema | M8 | P0 |
| C5.2 | Human-task node (wait for approval/answer, timeout and default) | M8 | P0 |
| C5.3 | Workflow versioning, diff, test mode with mocked tools, run history and replay | M8 | P1 |
| C5.4 | Triggers: file-watcher, folder "inbox" (drop files to process), git hook, email, clipboard, schedule | M14 | P1 |
| C5.5 | Internal event bus exposed to plugins and hooks | M8, M10 | P1 |
| C5.6 | Notification rules: quiet hours, digests, per-channel routing; optional free push through a self-hosted or public ntfy-style service the user chooses | M14 | P1 |

## F. Memory (richer model)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| C6.1 | Separate **episodic, semantic, procedural** memory | M13 | P1 |
| C6.2 | Entity/relation knowledge graph alongside flat items | M13 | P1 |
| C6.3 | Importance scoring and decay; "dreaming" consolidation job; per-agent vs shared scopes | M13 | P1 |
| C6.4 | User profile page the person can read and edit | M13 | P1 |
| C6.5 | Memory provenance (which session/tool produced it) and tainted-source flag | M13 | P0 |

## G. Interoperability and standards

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| C7.1 | Read other tools' instruction files as sources (`CLAUDE.md`, `.cursorrules`, Copilot instructions, `GEMINI.md`) with merge diagnostics; add a "not affiliated" note | M7 | P0 |
| C7.2 | **Importers/exporters**: MCP configs from other apps, settings, rules, sessions where formats are documented | M20 | P1 |
| C7.3 | Skill format compatible with the open `SKILL.md` convention; command format compatible with opencode-style markdown | M9 | P0 |
| C7.4 | OpenAPI-to-tools generator (point at a spec, get tools, dormant until approved) | M15 | P1 |
| C7.5 | Standards checklist: AGENTS.md, MCP, ACP, LSP, DAP, OpenTelemetry GenAI conventions, SARIF, CycloneDX, SPDX, OpenAPI, JSON Schema, ICS | M25 | P1 |

## H. Security and trust (extra layers)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| C8.1 | **Recoverable trash**: every agent delete goes to a Keel trash for N days; automatic git/stash snapshot before bulk operations | M5 | P0 |
| C8.2 | Delayed destructive ops with undo window; **approve from phone** for dangerous actions | M3, M20 | P1 |
| C8.3 | Behavior anomaly detection (sudden mass file reads, unusual network, repeated denials) pauses the agent | M3 | P1 |
| C8.4 | Honeypot/canary files that should never be read; alert if touched | M3 | P2 |
| C8.5 | Plugin/skill supply chain: capability review UI with **permission diff on update**, trust levels (bundled, signed, local, unsigned), static scan of skill scripts, signed **revocation list** delivered via the update feed | M9, M10 | P0 |
| C8.6 | Content-addressable artifact store with dedupe and integrity checks | M4 | P1 |
| C8.7 | DB resilience: scheduled integrity check, `VACUUM INTO` backups, **rebuild projections from the events log** after corruption, retention policies, optional SQLCipher encryption at rest (verify license/packaging) | M4 | P1 |
| C8.8 | Local red-team suite (prompt injection, exfiltration, tool-abuse scenarios) run per model | M21 | P0 |

## I. Performance and resource management

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| C9.1 | **Model manager**: load/unload idle models, VRAM/RAM budget, queue concurrent requests, warm-up | M2 | P0 |
| C9.2 | Virtualized lists, incremental rendering, streaming backpressure, startup prewarm, memory-leak watchdog | M19 | P0 |
| C9.3 | Incremental repo indexing with file watching; low-power/battery mode | M11 | P1 |
| C9.4 | Per-feature resource caps (browser, LSP, container) with visible meters | M16, M21 | P1 |

## J. Onboarding, help and support

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| C10.1 | Interactive tutorial with a sample project, guided tours, tips, "what's new" modal | M19 | P1 |
| C10.2 | Error catalog with stable codes and fix pages (offline) | M23 | P1 |
| C10.3 | Contextual help linking to offline docs | M19, M23 | P1 |
| C10.4 | In-app feedback saved locally, exported as a redacted bundle for email | M21 | P1 |
| C10.5 | Voice control and spoken responses for accessibility; live-region announcements for streaming text | M17, M25 | P1 |

## K. Proprietary protection, legal and brand (extra)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| C11.1 | **Source-hosting caveats to decide (verify current terms):** on GitHub's free plan, private repos may lack branch protection and advanced code/secret scanning; GitHub Pages for private repos may need a paid plan. Options: accept and use local pre-push hooks + gitleaks + signed commits; host the primary private repo on a free forge with protected branches (e.g. GitLab free tier or self-hosted Forgejo/Gitea) and mirror to GitHub; or consciously pay later (gate G6) | M1 | P0 |
| C11.2 | Security hygiene for the private repo: mandatory 2FA, signed commits, least-privilege tokens, Actions pinned by commit SHA, restricted Actions on forks (forks disabled), environment secrets with required reviewer for release publishing, access review checklist | M1 | P0 |
| C11.3 | **Source-leak incident runbook**: rotate keys, revoke tokens, take-down notices, history review, canary strings in source to trace leaks | M1 | P1 |
| C11.4 | **REUSE-style licensing metadata** (SPDX headers incl. a custom `LicenseRef-Keel-Proprietary`), auto-generated `THIRD_PARTY_NOTICES` from lockfiles, license allowlist policy file in CI | M1 | P0 |
| C11.5 | EULA acceptance stored locally with version; re-prompt when the EULA changes; EULA viewable in-app and on the website | M1, M19 | P0 |
| C11.6 | "Verified official build" indicator in About (app verifies its own hash/signature against the signed manifest); website page explaining how to recognize official downloads; typosquat/fake-site guidance | M22, M23 | P1 |
| C11.7 | Trademark usage guidelines page; takedown/abuse contact; export-control and privacy notes (lawyer review) | M23 | P2 |
| C11.8 | Obfuscation depth (deterrent only): Nuitka-compiled core, bytecode-compiled Electron main, asar integrity, string encryption for sensitive constants, per-build canary identifiers | M22 | P1 |

## L. Distribution and updates (extra)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| C12.1 | Manifest fields for **blocked versions**, `min_version`, security advisories, and **staged rollout** (deterministic client bucket) with no server logic | M22 | P0 |
| C12.2 | **Air-gapped install and update**: offline installer bundle, sideload update file verified by signature, model import from USB/folder | M22 | P1 |
| C12.3 | Self-hosted APT and YUM repositories (static files, signed) | M22 | P1 |
| C12.4 | Mirror list with automatic failover and signature check on every mirror | M22 | P0 |
| C12.5 | Portable zip builds for Windows and Linux | M22 | P2 |
| C12.6 | Release dry-run command that builds everything and runs the artifact allowlist and secret scans without publishing | M22 | P0 |

## M. Evaluation and quality (extra)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| C13.1 | Local SWE-task benchmark suite (small repos with failing tests) with per-model leaderboard | M21 | P0 |
| C13.2 | LLM-as-judge with a local judge model plus trajectory scoring (steps, wasted calls, cost) | M21 | P1 |
| C13.3 | Prompt regression tests across model versions; golden transcripts | M25 | P1 |
| C13.4 | Installer smoke tests in clean VMs per OS and architecture, including upgrade from every prior release and rollback | M22, M25 | P0 |
| C13.5 | Startup, memory and install-size trend charts stored per release | M21 | P1 |

---

## N. Suggested priority order
1. Before anything ships: C11.1, C11.2, C11.4, C11.5, C12.1, C12.4, C12.6, C8.1, C8.5, C1.4, C1.12.
2. Make weak local models work: C3.1, C3.2, C9.1 (plus B1.x from Addendum 1).
3. Fill the product surfaces: C2.1 (Cowork) and C2.3 (Duet) so Keel is more than a coding tool.
4. Everything else with its milestone; P2 rows after the v1.0 candidate is green.


---

# Appendix A3 — Addendum: Gaps and Advanced Features (preserved)

# Keel Plan v5 Addendum 3: Gaps, Plan Fixes and Advanced Features

Contains **only** items not already in `Keel_Master_Plan_v5.md`, `Addendum_Missed_Features.md` (A1 to B7) or `Addendum_2_More_Features.md` (C1 to C13). Free-only. Milestone numbers follow v5. IDs use prefix `X` to avoid collisions.

**Tags:** `[K]` general knowledge, verify in M0 · `[S]` my suggestion · `[P]` problem found in the existing plans. **Priority:** P0 / P1 / P2.
**Honesty note:** this addendum was built from the three plan files plus general knowledge of these product categories. The reference repos' source code and UI components were **not** re-read for this file (earlier sessions only reached README/tree level). Section Q defines the M0 teardown that must close that gap before anything is marked "copied from reference".

---

## P. Problems found inside the three plans (fix before building)

| ID | Problem | Fix | M | Pri |
| --- | --- | --- | --- | --- |
| X0.1 | **Priority inflation:** most rows across the addenda are P0, so P0 no longer means anything. | Re-rank: P0 = needed for a v1.0 that can ship safely; P1 = v1.x; P2 = later. Cap P0 at roughly 25% of rows. Builder produces the re-ranked list in `PLAN-INDEX.json`. | M0 | P0 |
| X0.2 | **M19 (desktop UI) is overloaded**: it receives rows from all three docs. | Split into M19a shell/layout, M19b chat/composer, M19c review/diff/terminal docks, M19d fleet/board/memory views, M19e settings/forms/wizard, M19f polish/a11y/i18n. | M19 | P0 |
| X0.2b | Same for M11, M17, M22. | Split M11 into code-intel core vs engineering tools; M17 into voice vs documents vs meetings; M22 into packaging vs update feed vs stores. | M11, M17, M22 | P1 |
| X0.3 | **No dependency graph** between milestones and rows. | Generate `deps` field in `PLAN-INDEX.json` and a critical-path report; builder may not start a row whose dependencies are not green. | M0 | P0 |
| X0.4 | **Duet defined three ways** (Master D4 open, Addendum 1 B2.3 reviewer pair, Addendum 2 C2.3 live pairing). | Ship both as one surface with two modes: *Live Pair* (ghost-text, handoff) and *Review Pair* (builder + independent reviewer). Owner confirms D4. | M12 | P0 |
| X0.5 | **Store distribution conflicts with "no source/no GitHub for users"** (C1.2): Flathub requires public build manifests, some Linux stores expect open recipes. | Per store, record: accepts proprietary freeware? needs public manifest? Drop stores that fail the rule; AUR binary package and self-hosted APT/YUM remain. | M22 | P1 |
| X0.6 | **Free-tier trap list is incomplete:** Vercel Hobby non-commercial, VirusTotal public API non-commercial, some GitHub features limited on private free repos, Docker Desktop commercial terms. | Add `FREE-TIER-REGISTER.md`: service, term used, date verified, exit plan. Re-verify at each gate. | M0, M1 | P0 |
| X0.7 | **Voice/ML licensing is stated as "check"** but nothing enforces it. | `MODEL-AND-VOICE-LICENSES.json` consumed by the UI license display and a CI gate; known watch items: Piper (license changed between versions), Whisper model weights, Kokoro voices, any diarization model (many carry gated or non-commercial terms), ffmpeg build flags (GPL vs LGPL). | M2, M17 | P0 |
| X0.8 | **"Zero network without account" is asserted but there is no test list.** | CI job runs the full smoke suite with network namespace removed; fails on any outbound attempt (update check disabled in that job). | M25 | P0 |
| X0.9 | **No risk register or rollback plan per milestone.** | `RISKS.md` (likelihood, impact, owner, mitigation) and a "revert plan" line in every milestone kickoff file. | M0 | P1 |
| X0.10 | **Plan says "reimplement from behavior" but gives no clean-room procedure.** | Two-step process: (1) analyst pass writes a behavior spec with no code pasted; (2) builder implements from the spec only. Log which spec each module came from in the provenance file. | M0 | P0 |

---

## A. Model dialects and local-model reliability (beyond B1.x and C3.x)

| ID | Feature | Detail | M | Pri | Tag |
| --- | --- | --- | --- | --- | --- |
| X1.1 | **Tool-call dialect adapters** | Parse and emit the formats local model families use (JSON function calls, XML-tagged calls, Hermes-style, Llama/Mistral/Qwen/DeepSeek variants, plain "ReAct" text). Auto-select per model from probe results. | M2 | P0 | K |
| X1.2 | Chat-template handling | Read the model's own chat template; warn on mismatch; per-model override file in the offline catalog. | M2 | P0 | K |
| X1.3 | Reasoning-model output handling | Strip/collapse `<think>`-style blocks, never feed them back as history by default, show them in a collapsible, count them in budgets. | M2 | P0 | K |
| X1.4 | **Selectable edit formats per model** | Whole-file, search/replace blocks, unified diff, line-range edit. Router picks the format the model is most reliable with (from local eval). | M5, M21 | P0 | K |
| X1.5 | **Fuzzy patch application** | Whitespace-tolerant, indentation-aware matching with a similarity threshold; on failure return a precise error and nearest-match snippet to the model. | M5 | P0 | K |
| X1.6 | Apply-model role | Optional small model that merges a "sketch" edit into the file; verify with diff size guard. | M2, M5 | P2 | K |
| X1.7 | **Repo map ranking** | Symbol graph ranked by reference centrality (PageRank-style) and recency, trimmed to a token budget per turn. | M11 | P0 | K |
| X1.8 | Accurate token counting | Use the runtime's tokenizer endpoint where available; fallback estimator with calibration against real usage. | M2, M4 | P0 | S |
| X1.9 | Few-shot tool exemplars | Inject 1 to 2 compact examples only for models whose probe score is low; remove for strong models. | M2 | P1 | S |
| X1.10 | Self-consistency voting for hard steps | N short samples, majority/judge pick; only on user-enabled "think harder" levels. | M7 | P2 | K |
| X1.11 | Streaming partial-JSON tool-argument parser | Show tool args as they stream; execute only after the call is complete and validated. | M2, M19 | P1 | S |
| X1.12 | Parallel tool calls with dependency check | Run independent read-only calls concurrently, serialize writes. | M5 | P1 | K |
| X1.13 | Steering and interrupt | Send a message mid-turn: queue, steer at next tool boundary, or abort-and-resume with partial output preserved. | M4, M19 | P0 | S |
| X1.14 | Model switch mid-session | Switch model with automatic history re-rendering to the new dialect and a context-fit warning. | M2 | P1 | S |
| X1.15 | Per-model prompt profiles | System-prompt variants by model family/size, versioned, covered by golden tests. | M7 | P1 | S |
| X1.16 | Model "health check" on load | Tiny canned task after load verifies tool calling, JSON validity, long-context sanity; result drives the reliability badge. | M2, M21 | P1 | S |

## B. Coding workflow extras

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| X2.1 | **Diagnostics feedback after every edit:** LSP errors/warnings for touched files are appended to the tool result; agent must resolve or justify. | M11 | P0 |
| X2.2 | Rename/extract/move via LSP code actions instead of text edits when available. | M11 | P1 |
| X2.3 | TDD mode: write failing test first, confirm red, implement, confirm green, record both runs as evidence. | M7 | P1 |
| X2.4 | Bug-repro mode: agent must produce a failing reproduction before changing code. | M7 | P1 |
| X2.5 | Code review mode on any diff or branch (style, bugs, security, test gaps) producing inline comments the user can accept as tasks. | M7 | P1 |
| X2.6 | Per-task git worktree **merge queue** with conflict preview and "land when green" button. | M11, M12 | P1 |
| X2.7 | Test-runner adapters (pytest, unittest, jest/vitest, go test, cargo test, JUnit-style output parsing) with failure summaries instead of raw logs. | M11 | P0 |
| X2.8 | Coverage-guided hints: show which lines the change leaves untested. | M11 | P2 |
| X2.9 | Dependency upgrade assistant: read changelogs offline from the package cache, upgrade one at a time, run tests, roll back on failure. | M11 | P2 |
| X2.10 | Migration assistants (framework/library version upgrades) as bundled skills with verification steps. | M9 | P2 |
| X2.11 | Notebook-aware editing (`.ipynb` cell diff, run cell, outputs stored outside the notebook diff). | M5, M11 | P2 |
| X2.12 | Commit hygiene: conventional-commit suggestions from project history, secret scan on staged diff, hook-aware (respect existing pre-commit). | M11 | P1 |
| X2.13 | Monorepo task graph awareness (workspaces, package boundaries) so edits and tests are scoped to affected packages. | M11 | P1 |
| X2.14 | "Explain this change" and "explain this file" with symbol-level citations. | M11 | P2 |
| X2.15 | Language packs: bundled guidance + tool wiring for Python, TypeScript, Go, Rust, Java, C/C++, C#, PHP, Ruby, shell. Each pack lists install hints for compilers/LSP and test command detection. | M11 | P1 |
| X2.16 | Long-running process supervisor in the terminal: named background jobs, tail/stop/restart, auto-surface crash output to the agent. | M5 | P1 |

## C. Cowork and personal-productivity extras (beyond C2.1)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| X3.1 | Local **desktop search** across user-approved folders (FTS5 + optional embeddings), exposed as a tool and a palette. | M13 | P1 |
| X3.2 | Document redaction tool (names, emails, IDs) with preview and verified-redacted PDF output. | M17 | P1 |
| X3.3 | Receipt/invoice extractor to a local CSV/SQLite table (OCR + field parser) with review UI. | M17 | P2 |
| X3.4 | Contract/document comparison: clause diff and plain-language summary with page citations. | M17 | P2 |
| X3.5 | Spreadsheet helper: explain formulas, find errors, build pivots, produce charts; write results to a copy, never in place by default. | M17 | P1 |
| X3.6 | File organizer rules engine (by type, date, EXIF, name patterns) with dry-run, preview, undo journal. | M5 | P1 |
| X3.7 | Duplicate finder (hash + perceptual hash for images) with safe-delete to Keel trash. | M5 | P2 |
| X3.8 | Web clipper and read-later queue (save page as Markdown into the vault). | M13 | P2 |
| X3.9 | RSS/Atom digest agent (user feeds only) with scheduled summary. | M14 | P2 |
| X3.10 | Flashcards and spaced repetition generated from notes or documents, stored locally. | M13 | P2 |
| X3.11 | Study/tutor mode (Socratic, quiz, explain-back) as a bundled persona + skills. | M9 | P2 |
| X3.12 | Writing coach with local grammar/style checking; check any third-party checker's license before bundling. | M17 | P2 |
| X3.13 | Personal CRM/contacts notes in the vault with follow-up reminders. | M13, M14 | P2 |
| X3.14 | Local finance CSV import and categorization (no bank connections). | M17 | P2 |
| X3.15 | Clipboard history tool (opt-in, encrypted, auto-expire) the agent can query with consent. | M19 | P2 |
| X3.16 | Screenshot region capture with OCR and "ask about this" action. | M16, M19 | P1 |

## D. Voice and multimodal extras

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| X4.1 | Barge-in: user speech interrupts TTS immediately; half-duplex fallback on weak hardware. | M17 | P1 |
| X4.2 | Streaming TTS sentence by sentence while the model is still generating. | M17 | P1 |
| X4.3 | Optional wake word (verify engine license) with visible mic indicator and hard mute. | M17 | P2 |
| X4.4 | Local vision-language model tool for screenshots/diagrams (user-installed model, license shown). | M16, M17 | P1 |
| X4.5 | Video tooling via user-installed ffmpeg: frame extraction, audio extraction, subtitle generation from local STT. | M17 | P2 |
| X4.6 | Voice command grammar for app control ("approve", "deny", "stop everything") separate from free dictation; always requires a spoken confirmation for risky actions. | M17 | P1 |
| X4.7 | Audio privacy rules: no recording stored by default, visible recording state, per-meeting consent reminder text. | M17 | P0 |

## E. Security and privacy extras (beyond B3.x, C8.x)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| X5.1 | **Sensitive-project mode:** project flag that hard-blocks any remote provider/connector for that project, shown with a lock badge. | M3 | P0 |
| X5.2 | Data-classification labels on files and memories (public / internal / secret) that feed redaction and egress decisions. | M3, M13 | P1 |
| X5.3 | **Time-boxed and just-in-time permissions** ("allow for 30 minutes"), auto-expire, visible countdown. | M3 | P1 |
| X5.4 | Capability tokens for subagents and plugins: short-lived, scoped, revocable, logged. | M3, M12 | P1 |
| X5.5 | **Mass-change guard** (anti-ransomware style): rate limit on files modified/deleted per minute; breach pauses the agent and snapshots. | M3, M5 | P0 |
| X5.6 | Filesystem change journal per task so every touched path can be reviewed and reverted as a set. | M5 | P0 |
| X5.7 | Permission review screen: every standing allow rule with last-used date, one-click prune of unused rules. | M3, M19 | P1 |
| X5.8 | Per-tool sandbox profiles (read-only FS, no network, temp-only write) selectable in agent frontmatter. | M5 | P1 |
| X5.9 | Clipboard and screen guard: tools that read clipboard/screen always ask, and tainted-source rules apply to captured content. | M3, M16 | P1 |
| X5.10 | Encrypted session/memory export bundles with passphrase, verified on import (signature + schema version). | M4, M13 | P1 |
| X5.11 | Provider data-handling card: for each configured remote provider, show what Keel sends (from the egress log) and a link to the user's own account settings; never claim anything about the provider's retention. | M21 | P1 |
| X5.12 | Dependency and model **allow/deny lists** in managed policy (specific MCP servers, plugin IDs, model files by hash). | M24 | P2 |
| X5.13 | Safe-paste detector: warns when the user pastes text containing a key/token pattern into chat. | M3, M19 | P1 |

## F. Developer platform (plugins, SDK, API)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| X6.1 | `keel dev` plugin scaffold generator, hot reload, and a **mock host** so plugins can be tested without the full app. | M10 | P1 |
| X6.2 | Plugin test harness with golden event streams and permission-denial tests. | M10 | P1 |
| X6.3 | Typed SDKs generated from the API schema (Python and TypeScript), version-pinned to the daemon. | M20 | P1 |
| X6.4 | API versioning policy: deprecation headers, sunset dates, compatibility tests against the previous minor. | M20 | P1 |
| X6.5 | In-app interactive API explorer for the local API (loopback, token-protected); docs stay private unless G7. | M20 | P2 |
| X6.6 | Event schema registry: every internal event type has a JSON Schema and a changelog; plugins subscribe by type. | M8, M10 | P1 |
| X6.7 | Config validation with "did you mean" suggestions, line/column errors for JSONC, and `keel config explain <key>`. | M2 | P0 |
| X6.8 | Layered config viewer: shows which layer (default, global, project, env, policy) set each value. | M2, M19 | P1 |
| X6.9 | Settings search, diff against defaults, per-section reset, import/export. | M19 | P1 |
| X6.10 | Feature-lifecycle labels (experimental / beta / stable) in UI and config, with experimental off by default. | M3 | P1 |

## G. Distribution, install and platform support (beyond C12.x)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| X7.1 | ARM64 builds for Windows and Linux; macOS universal or separate arm64/x64 with verified native deps. | M22 | P1 |
| X7.2 | Per-user vs per-machine install option on Windows; no admin rights required for per-user. | M22 | P0 |
| X7.3 | **Uninstall options:** keep data, remove data, remove data and models; list what will be deleted first. | M22 | P0 |
| X7.4 | File associations and URL protocol registration (`keel://`) with clean removal on uninstall. | M22 | P1 |
| X7.5 | Linux specifics: Wayland and X11 tests, tray fallback where no tray exists, AppImage desktop integration, sandbox flag guidance. | M22, M25 | P1 |
| X7.6 | **Antivirus false-positive playbook:** keep builds deterministic, document how to submit samples to vendors' free review channels, publish checksums so users can compare. | M22, M23 | P1 |
| X7.7 | Installer languages for the major UI locales; installer text from the same string catalogs. | M22, M25 | P2 |
| X7.8 | Download-integrity helper inside the app ("verify a file I downloaded") for users who want to check an installer before running it. | M23 | P2 |
| X7.9 | First-run import wizard from other tools' folders (documented formats only), dry-run first. | M19, M20 | P2 |
| X7.10 | Disk-usage manager: models, caches, sessions, trash, with sizes, safe-clean, and per-category caps. | M19 | P1 |

## H. UI/UX depth (use Keel theme tokens only)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| X8.1 | **Local component catalog** (free tool such as Storybook or Ladle; verify license) showing every component in every state against Keel tokens; used for visual regression. | M19 | P0 |
| X8.2 | Design-token contract file (`tokens.json`) as the only source of color, type, spacing, radius, motion; lint rule rejects hard-coded values. | M19 | P0 |
| X8.3 | Density modes (compact / comfortable), per-pane zoom, and saved layouts. | M19 | P1 |
| X8.4 | Notification center and activity feed (approvals, job results, errors) with filters. | M19 | P1 |
| X8.5 | **Actionable OS notifications:** approve/deny or open task straight from the notification where the OS supports it. | M19, M20 | P1 |
| X8.6 | Tray / menu-bar mini window: running agents, pending approvals, quick ask, kill switch. | M19 | P1 |
| X8.7 | Selection actions: select text anywhere in Keel and "ask about this", "add to context", "save to vault". | M19 | P1 |
| X8.8 | Thread tools: outline/minimap, pinned messages, jump-to-tool-call, timeline scrubber for long sessions. | M19 | P1 |
| X8.9 | Side-by-side **session compare** (two models, two branches, before/after). | M19 | P1 |
| X8.10 | Citation chips with hover preview of the source file/page/line. | M19 | P1 |
| X8.11 | Inline diff and file preview inside chat with "open in dock" action. | M19 | P0 |
| X8.12 | Error boundary and crash-recovery UI: renderer crash restores the session view without losing the draft composer text. | M19 | P0 |
| X8.13 | Undo toast pattern for every destructive UI action (archive, delete, revoke). | M19 | P1 |
| X8.14 | Live theme editor (tokens only), contrast checker, import/export theme JSON. | M19 | P2 |
| X8.15 | Optional sound cues (off by default), reduced-motion honoring everywhere. | M19, M25 | P2 |
| X8.16 | Multi-monitor awareness: remember window positions per display, detach docks to other screens. | M19 | P2 |
| X8.17 | Empty-state and onboarding copy deck written once (Keel's own words) and reused across screens. | M19 | P1 |

## I. Testing and quality (beyond B7, C13)

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| X9.1 | **Fixture model server:** a local OpenAI-compatible mock that replays scripted tool calls, malformed JSON, partial streams, slow tokens and errors; used by every provider and agent test. | M2, M25 | P0 |
| X9.2 | Record/replay (VCR-style) of real provider traffic with secrets scrubbed, for contract tests. | M2, M25 | P1 |
| X9.3 | Provider contract tests: each adapter must pass the same behavior suite (streaming, cancel, tool call, usage, errors). | M2 | P0 |
| X9.4 | MCP conformance tests against bundled sample servers (stdio and HTTP) including hostile servers (huge output, hanging, bad schema). | M6 | P0 |
| X9.5 | Cross-platform path/permission matrix tests (Windows reserved names, ADS, long paths, case-insensitive FS, symlinks/junctions). | M3, M25 | P0 |
| X9.6 | Pseudo-localization build and RTL smoke test in CI. | M25 | P1 |
| X9.7 | Migration matrix: every released schema version upgraded to current, with data checksums. | M4, M25 | P0 |
| X9.8 | Token-accounting accuracy test (estimated vs runtime-reported usage within tolerance). | M21 | P1 |
| X9.9 | Long-session soak (thousands of events) watching memory, DB size, UI frame time. | M25 | P1 |
| X9.10 | Mutation testing report published into the private dashboard for the permission gate and command analyzer. | M25 | P1 |

## J. Process and builder control

| ID | Feature | M | Pri |
| --- | --- | --- | --- |
| X10.1 | **Definition-of-done template** per row: code path, test path, e2e run id, docs updated, license/notice check, rollback note. | M0 | P0 |
| X10.2 | **Provenance file** per module: spec source, any copied snippet with its license, reviewer. | M0, M1 | P0 |
| X10.3 | Decision log (`DECISIONS.md`) separate from ADRs for owner-level choices (D1 to D7, G1 to G7) with date and answer. | M0 | P1 |
| X10.4 | Builder "stop list": actions that always pause for the owner, mirrored from gates G1 to G7 plus destructive repo actions, as a machine-readable file the builder must check. | M0 | P0 |
| X10.5 | Weekly "what is proven" report generated from `PLAN-INDEX.json` (counts by status, stale evidence, failing rows). | M0, M26 | P1 |
| X10.6 | Scope-creep guard: any new feature idea goes to `INBOX.md` with a proposed milestone instead of being built inline. | M0 | P1 |

---

## Q. Reference teardown (M0 addition: do this before building from the five repos)

The builder must produce, for each of the five repos, the following **private** artifacts. None may ship.

1. **Inventory:** tree, license file text (not README badge), dependency list with licenses, entry points, config files.
2. **Behavior spec:** one page per feature, written in Keel's words (what the user does, what happens, edge cases, error states). No code or prompts pasted.
3. **Screen spec (UI/UX):** for every screen or panel seen in the running app or README: purpose, regions/layout, component list, states (default, empty, loading, error, disabled), form fields with validation rules, keyboard behavior, navigation. Visual styling is **not** recorded; each component is mapped to a Keel token set and an existing Keel component where one exists.
4. **Feature matrix:** feature ID, source repo(s), Keel milestone, free-implementation choice, license risk, status.
5. **Diff against plan:** anything found in the repo that no plan row covers becomes a new row in `PLAN-INDEX.json`.

Screen-spec template per screen:

```
screen_id / name
purpose (1 line)
entry points
layout regions (left/center/right/top/bottom)
components -> Keel component or "NEW"
states: default | empty | loading | error | disabled | offline
forms: field, type, required, validation, default, help text (Keel copy)
actions and shortcuts
permission/approval interactions
a11y notes (focus order, labels)
tokens used (from tokens.json only)
test: e2e path
```

## R. Suggested sequencing for this addendum

1. **Fix the plan first:** X0.1 to X0.10, X10.1 to X10.4.
2. **Reliability core:** X1.1 to X1.5, X1.8, X1.13, X9.1, X9.3.
3. **Safety before power:** X5.1, X5.5, X5.6, X7.2, X7.3.
4. **UI foundations:** X8.1, X8.2, X8.11, X8.12.
5. **Everything else** at its milestone; all P2 rows only after the v1.0 candidate is green.


---

# Appendix A4 — Addendum: Sourced Features and Builder Guide (preserved)

# Keel Plan v5 Addendum 4: Sourced Features, Reference Map and Builder Guide for Own Ideas

Adds only items **not already in** the Master Plan, Addendum 1 (A/B), Addendum 2 (C), Addendum 3 (X). Free-only. Milestones follow v5. Every row says **where it came from**.

## 0. How to read the source tags

| Tag | Meaning |
| --- | --- |
| `[T:<src>]` | Read in the source named, **this session (21 Nov 2026)**. Still reimplement from behavior (clean-room, X0.10). |
| `[K]` | General knowledge of that product category; verify in M0. |
| `[S]` | My suggestion. **Not from any repo.** Follow the builder protocol in Section 6. |

Source keys (all fetched this session):
- **OC-README** github.com/anomalyco/opencode (README + file tree)
- **OC-TOOLS** opencode.ai/docs/tools · **OC-CONFIG** opencode.ai/docs/config · **OC-PLUGINS** opencode.ai/docs/plugins
- **OT-README** github.com/nickvasilescu/orgo-teammates README/tree · **OT-ARCH** its `docs/ARCHITECTURE.md`
- **OM-README** github.com/nickvasilescu/openman README/tree · **OM-ARCH** its `docs/ARCHITECTURE.md`
- **NS** nicks-stack README/tree · **LQ** clawdbot-channel-linq README/tree
- **KL** github.com/eliosmernica15/keel front page/tree

## 1. What was and was not read (honest status)

**Read this session:** the six repo front pages/READMEs/trees, opencode `tools`, `config`, `plugins` docs, and both `ARCHITECTURE.md` files (orgo-teammates, openman).

**Not read yet (M0 reading list, in this order):**
1. opencode docs: `agents`, `commands`, `permissions`, `policies`, `mcp-servers`, `snapshots`, `compaction`, `formatters`, `references`, `attachments`, `skills`, `themes`, `providers`, `websearch`, `network`, `warming`, `migrate-v1`, `troubleshooting`, `build/plugins` (server/GUI/TUI), `api`, `cli`, plus `packages/`, `services/`, `specs/v2`, `.opencode/`, `sdks/vscode`, `.zed` in the repo. Folders `salesforce/` and `strobe.json` in opencode are unexplained: inspect.
2. orgo-teammates: `docs/orgo-builder-guide.md`, `docs/xai-and-composio.md`, `SECURITY.md`, `web/src` (screens), `tests/e2e.mjs`.
3. openman: `docs/security-model.md`, `docs/deploy.md`, `docs/OPERATIONS.md`, `AGENTS.md`, `content/docs`, `src/app` (screens), `src/config/usage-limits.ts`, `src/config/brand.ts`.
4. nicks-stack: `files/config.yaml`, `files/SOUL.md`, `files/skills/*` (21), `files/onboard.sh`, `agentphone-bridge/`, `plugins/orgo-desktop-local/` (11 tools: list them), `build_template.py`.
5. clawdbot-channel-linq: `src/*`, `clawdbot.plugin.json`.
6. **Keel itself:** the `keel/` source is not readable by these tools. Builder reads it locally. **The Keel repo still shows "Public" with 108 commits as of this fetch**, so gate G1 (Appendix B runbook) is still pending.

## 2. Reference-sourced features (new rows only)

### 2.1 opencode

| ID | Feature | Source | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| Y1.1 | **Code Mode / `execute` tool:** agent writes a short script that calls many tools in parallel and processes results without pushing intermediate output into context. Runtime has no filesystem, imports or timers; only a `fetch` and the tool catalog. Denying it falls back to listing tools directly. | T:OC-TOOLS | Python (or JS) micro-sandbox (WASM/Pyodide per B3.1) exposing the tool registry as functions; every nested call still goes through the permission gate; per-MCP-server `codemode:false` switch. | M5, M6 | P1 |
| Y1.2 | **Model-dependent tool exposure:** `patch` tool only offered to some model families, others get `edit`+`write`. | T:OC-TOOLS | Tool-exposure table keyed by model family (ties to X1.4). | M5 | P0 |
| Y1.3 | **`patch` multi-file format** (`Add File`/`Update File`/`Delete File` sections, move/rename) with permission check on every affected path. | T:OC-TOOLS | Own parser + atomic apply with rollback. | M5 | P0 |
| Y1.4 | `read` limits and paging: 2,000 lines / 50 KiB per page, long lines truncated, images and PDFs passed to model up to 20 MiB. | T:OC-TOOLS | Same defaults, configurable; local PDF text fallback for non-vision models. | M5 | P0 |
| Y1.5 | `glob`/`grep` defaults: 100 results, 30 s timeout, `literal`, `include`, `caseSensitive`, `hidden` flags; grep permission resource is the **pattern**, not the path. | T:OC-TOOLS | ripgrep wrapper with the same parameters and limits. | M5 | P0 |
| Y1.6 | `edit` requires a unique match unless `replaceAll`; optional formatter run after write/edit/patch. | T:OC-TOOLS, OC-CONFIG | Exact-match edit + `formatter` config. | M5, M11 | P0 |
| Y1.7 | **Shell tool details:** `workdir` param (no `cd` in command), 2-minute foreground timeout, `background:true` returns immediately and **notifies the session when finished**, large output truncated with full output kept in a managed file, command scanner produces one permission resource per sub-command and checks external working dirs. | T:OC-TOOLS | PTY/process manager + analyzer (Tier 2). | M5, M3 | P0 |
| Y1.8 | `webfetch`: markdown/text/html output, 120 s max, rejects binaries; `websearch` provider selection incl. "random" among available. | T:OC-TOOLS, OC-CONFIG | SSRF-safe fetch; websearch limited to **free** providers (self-hosted SearXNG etc.). | M5 | P0 |
| Y1.9 | **`question` tool:** header + prompt + choices, `multiple`, free-form always allowed, cancel on dismiss; clients lacking UI must be detected. | T:OC-TOOLS | `ask_user` with **client capability negotiation** (client declares it can render question forms). | M5, M20 | P0 |
| Y1.10 | `skill` tool loads a skill by ID only if it is in the advertised list or named by the user. | T:OC-TOOLS | Skill loader with advertised-list gate. | M9 | P0 |
| Y1.11 | **Subagent semantics:** always background; returns a `sessionID`; parent is notified when the child goes idle and after each later round; follow-up message continues the same child; default nesting depth 1, configurable (`subagent_depth`). | T:OC-TOOLS, OC-CONFIG | Task-graph child sessions with these exact lifecycle rules. | M12 | P0 |
| Y1.12 | **Session utilities as tools:** `session_rename`, `session_move` (takes effect at a safe boundary). | T:OC-TOOLS | Tools over the session API. | M4, M5 | P2 |
| Y1.13 | **Worktree tools:** `worktree_create/list/remove` (remove needs `force` to discard changes; uses edit permission), configurable parent directory, plugin-registered worktree strategies. | T:OC-TOOLS, OC-CONFIG | git worktree manager (extends X2.6). | M11 | P1 |
| Y1.14 | **Browser tool namespace:** tabs, snapshots, search, click, form input, screenshots, file transfer (5 MiB cap), console and network inspection, performance traces, heap inspection, **Lighthouse audits**; page content treated as untrusted; deny rule removes the whole catalog. | T:OC-TOOLS | Playwright/CDP + free Lighthouse (Apache-2.0, verify) behind consent; extends C4.11. | M16 | P1 |
| Y1.15 | `experimental_image_generate` (background job with notification, optional reference images, save path). | T:OC-TOOLS | Optional local diffusion provider only; shown only when a provider exists (see Y5.2). | M17 | P2 |
| Y1.16 | **MCP permission naming:** action `<server>_<tool>` with resource `*`; per-server `timeout`; global `mcp.timeout`. | T:OC-TOOLS, OC-CONFIG | Same naming in the permission table. | M6 | P0 |
| Y1.17 | **Ordered rule list permissions:** `{action, resource, effect}` entries; **policies** layer (`provider.use`, `tool.use` with `shell:git push *` style resources, block MCP server/skill/plugin) that outranks normal config. | T:OC-CONFIG | Matches Tier 1 + managed policy (Master 6.16/6.17); add `provider.use` and per-extension block actions. | M3, M24 | P0 |
| Y1.18 | **Managed config locations** per OS: `/etc/opencode`, `%ProgramData%\opencode`, `/Library/Application Support/opencode`, macOS managed-preferences plist; managed settings have highest precedence. | T:OC-CONFIG | `keel-policy.json` search paths + plist/ADMX (extends B6.3). | M24 | P2 |
| Y1.19 | **Config precedence algorithm:** merge global, then walk from filesystem root to cwd (farthest to closest), direct files then `.opencode/` files, system config last. | T:OC-CONFIG | Same walk for `.keel/keel.jsonc`; show result in layered config viewer (X6.8). | M2 | P0 |
| Y1.20 | `{env:VAR}` and `{file:path}` substitution inside config strings (missing becomes empty string; warn). | T:OC-CONFIG | Substitution in config loader; **warn instead of silently empty** for secrets. | M2, M3 | P0 |
| Y1.21 | `update: disable | notify | auto` (global config only; project value ignored; auto-install does not restart a running server). | T:OC-CONFIG | Updater modes; project config cannot change it. | M22 | P0 |
| Y1.22 | `snapshots` toggle for undo/revert; `watcher.ignore` globs. | T:OC-CONFIG | Checkpoint toggle; watcher ignore list. | M4, M11 | P1 |
| Y1.23 | `media.image` auto-resize limits (max width/height, max base64 bytes); `tool_output` max lines/bytes. | T:OC-CONFIG | Config keys with defaults (2000 px, 5 MiB; 2000 lines, 50 KiB). | M5 | P1 |
| Y1.24 | **Compaction config:** `auto`, `keep.tokens` (recent tail kept verbatim), `buffer` as % of context kept free; optional "native provider compaction" vs local summary, per provider/model. | T:OC-CONFIG | Compaction settings + per-model override; summary stays default. | M4 | P0 |
| Y1.25 | **Cache warming:** periodic transient request keeps a provider prompt cache alive; per-model `cache.ttl`, `cache.warming`; off by default. | T:OC-CONFIG | Local analog: keep llama.cpp/Ollama KV cache resident (`keep_alive`) and prewarm the system-prompt prefix; remote warming only if the user enables it and shows cost. | M2 | P1 |
| Y1.26 | **References:** named external directories or Git repos made available as context by name (`path` or `repository`+`branch`), with description. | T:OC-CONFIG | `references` config; repos cloned read-only into a cache; searchable by tools. | M11, M13 | P1 |
| Y1.27 | `skills` config accepts directories **and URLs** (`.well-known/skills/` discovery). | T:OC-CONFIG | Local dirs always; URL discovery only for user-listed hosts, signed-pack check. | M9 | P2 |
| Y1.28 | `instructions` accept files, globs, **HTTP(S) URLs** next to `AGENTS.md`. | T:OC-CONFIG | Extends A1.14; URLs fetched through SSRF-safe client and marked tainted. | M7 | P1 |
| Y1.29 | **Plugin management CLI:** `plugin add/list/check/update/remove`; sources: npm name@version/tag/range, `github:` shorthand, git+ssh, `#branch`, `::path:` subdirectory; exact versions and full commit hashes stay pinned; `--builtin` listing. | T:OC-PLUGINS | `keel plugin ...` with **private-source-only default** (G7); pin/unpin and update check. | M10 | P1 |
| Y1.30 | **Plugin enable/disable DSL:** ordered entries, `-id` disables, `*` all, `.*` prefix wildcard, later entry re-enables; **built-in policy plugins cannot be disabled by a repo**. | T:OC-PLUGINS | Same DSL; Tier-2 and policy enforcers are unremovable. | M10, M3 | P0 |
| Y1.31 | **Three plugin surfaces:** server plugins, GUI plugins (panels, commands, settings; Settings > Extensions > Plugins with per-plugin switch and Reload after failure), TUI-only plugins configured separately. Plugins loaded from watched directories hot-reload; unpinned packages checked for updates in background without changing the installed version. | T:OC-PLUGINS | Plugin manifest declares surfaces; Extensions settings page with Reload; hot reload on file change. | M10, M19 | P1 |
| Y1.32 | `location_idle_timeout`: unload a project's services (LSP, watchers) after N idle minutes; running sessions and background jobs keep it loaded. | T:OC-CONFIG | Idle unload per project (extends A2.4). | M16, M21 | P1 |
| Y1.33 | `experimental.todo` flag: `todowrite` tool is opt-in. | T:OC-CONFIG | Keep `todo` tool P0 (A1.10) but expose feature-lifecycle flag (X6.10). | M5 | P2 |
| Y1.34 | Model entries can override ids, display name, `limit.context`/`limit.output`; provider `settings.transport` (e.g. websocket). | T:OC-CONFIG | Offline catalog + user overrides per model. | M2 | P1 |
| Y1.35 | "You can also ask the agent to update the config file for you." | T:OC-CONFIG | `config_edit` tool: proposes a validated diff of `keel.jsonc`, user approves; never touches Tier-2 settings. | M2, M19 | P1 |
| Y1.36 | **Migrate-from-V1 and Troubleshooting docs** exist as first-class pages. | T:OC-CONFIG nav | In-app "Migration notes" and "Troubleshooting" pages generated from the error catalog (C10.2). | M23 | P2 |
| Y1.37 | Install script drops binary in `$HOME/.opencode/bin`; channel formulas (stable brew vs "latest" tap), mise, pacman, AUR beta, Nix, `brew --cask` desktop; "remove versions older than X before installing" tip. | T:OC-README | Per-user install dir by default; stable vs beta channels (B4.14). Store feasibility per X0.5. | M22 | P1 |
| Y1.38 | Repo hygiene: `.husky` hooks, `.gitleaksignore` (reviewed allowlist for scanner false positives), `oxlint`, `turbo`-style task graph, `patches/` for dependency patches, `CHANGELOG.md`, `SECURITY.md`. | T:OC-README | Extends C1.1: add reviewed `.gitleaksignore` policy (each entry needs a reason + expiry). | M0, M1 | P1 |
| Y1.39 | "Building on X" notice: derivative projects must state non-affiliation. | T:OC-README | Keel `TRADEMARKS.md` includes a non-affiliation clause for third-party extensions. | M1 | P2 |

### 2.2 orgo-teammates

| ID | Feature | Source | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| Y2.1 | **Transcript row model:** append-mostly rows with `seq`, `updatedSeq` (per-session revision counter), `kind`, JSON `body`; a streaming reply is the same row rewritten with higher `updatedSeq`; clients **upsert by seq**; per-session `generation` counter resets a conversation. | T:OT-ARCH | Use this for the SSE protocol and for reconnect/replay; add to `events` schema. | M4, M20 | P0 |
| Y2.2 | **Model history stored separately** from UI rows (`llm_items`), so UI redaction/edits never corrupt model input; reasoning blobs passed back unchanged. | T:OT-ARCH | Separate `model_items` table; UI rows derived/annotated. | M4 | P0 |
| Y2.3 | Keep only the **last N screenshots** inline (N=3) in model context. | T:OT-ARCH | Image-pruning rule in context manager (extends B1.5). | M4, M16 | P0 |
| Y2.4 | **Orphaned tool-call repair** before the next model call after an interrupted turn. | T:OT-ARCH | History sanitizer: every tool call gets a synthetic "interrupted" result. | M4 | P0 |
| Y2.5 | **Per-agent serial queue** for turns; user message while a turn pends closes the pending approval as expired. | T:OT-ARCH | Per-session queue + approval expiry rule. | M4, M3 | P0 |
| Y2.6 | **Pending-turn persistence:** when approval is needed, pending tool calls are saved (`pending_turns`) and the turn resumes after the answer, surviving restarts. | T:OT-ARCH | Persisted pending turns; resume on daemon restart. | M3, M4 | P0 |
| Y2.7 | Approval buttons: **Allow** (once), **Always allow** (stores per-tool policy), **Don't allow** (model is told **not to retry**). | T:OT-ARCH | Matches approval card; "Don't allow" must inject a no-retry instruction. | M3, M19 | P0 |
| Y2.8 | **Auto-classification of read-only tools by slug** (`*_GET`, `*_LIST`, `*_SEARCH`, no write verb) for connectors; meta tools that can run arbitrary actions, and batches whose inner tools can't be read, always need approval. | T:OT-ARCH | Connector tool classifier with **explicit manifest flags** `readOnly`, never name-guessing alone (name rules only as a fallback with a warning). | M15, M3 | P0 |
| Y2.9 | Card row kinds in transcript: `approval`, `question`, `connect`, `draft`; event rows: routine created/run, voice call, group changes; `notice`. | T:OT-ARCH | Row-kind registry in the UI component list (matches 9.2). | M19 | P1 |
| Y2.10 | `stay_silent` tool (agent may choose not to reply in group threads) and `request_app_connection` tool (agent asks user to connect an app, rendering a connect card). | T:OT-ARCH | Both tools; connect card opens the connector form. | M5, M12, M15 | P1 |
| Y2.11 | `send_to_bot` messaging between agents; **hidden child agents** (subagents) with own context/screen removed by `stop_subagent`; **group rooms** capped at 3 responding members, @mention routing, `post_to_group`. | T:OT-ARCH | Matches A2.5 loop guards; add the 3-member responder cap as a default. | M12 | P1 |
| Y2.12 | **Screen leasing:** one VM, up to 4 separate desktops, leased least-recently-used among idle agents. | T:OT-ARCH | Container-desktop pool with LRU leases (extends M16). | M16 | P1 |
| Y2.13 | **Idle suspend knobs** (20 min default, sweep every 60 s, dry-run mode logging decisions without acting). | T:OT-ARCH | Resource manager with `dry_run`; settings page. | M16, M21 | P1 |
| Y2.14 | **VNC relay that hides credentials from the browser** and, in **watch mode, drops keyboard/pointer/clipboard on the server** (not just in UI). | T:OT-ARCH | noVNC relay in daemon; server-side input filter for Watch vs Take over. | M16 | P0 |
| Y2.15 | Rate-limit awareness (≈600 control calls/min per computer) and plan for an **in-VM executor**. | T:OT-ARCH | Token-bucket limiter on desktop actions; executor = C1.11. | M16 | P1 |
| Y2.16 | **Compaction knobs:** trigger size, keep-last-N-user-turns verbatim (default 4), method `auto|summary`; **idle consolidation** (10 min idle, 60 s sweep); memory budget in prompt (4,000 chars). | T:OT-ARCH | Settings + defaults; extends A2.9. | M13 | P1 |
| Y2.17 | **Prompt cache key per agent+generation**; hashed user id as safety identifier to providers. | T:OT-ARCH | Stable cache key for remote providers; for local servers keep prefix stability. Never send raw identifiers. | M2 | P1 |
| Y2.18 | `NO_SCHEDULER` flag so extra dev servers sharing a database don't double-fire jobs. | T:OT-ARCH | `--no-scheduler` / `KEEL_NO_SCHEDULER`. | M14 | P1 |
| Y2.19 | **Backward-compatible rename path:** old env var names still read as fallback; old DB filename kept if new one doesn't exist; old cookie still accepted; guarded symlink for renamed data folder. | T:OT-README, OT-ARCH | Apply to Keel's own rename history (e.g., any pre-0.1.0 data dir/env names) and to future renames; test in migration matrix (X9.7). | M4, M22 | P1 |
| Y2.20 | **Exposure defaults:** bind 127.0.0.1; dev login ignored off-localhost; **refuse new sign-ups on a public URL until an allowlist is set**; allowlist entries accept emails or `@domain`. | T:OT-README | `keel serve --listen` refuses to start without auth + allowlist of paired clients (C1.12); documented in `.env`-style reference. | M3, M20 | P0 |
| Y2.21 | **Honest "Project status" section** in README: tested vs built-not-proven, "basic review, not professional audit", known approval gap (browser/shell not covered). | T:OT-README | Feeds A3.7 About page; add "known limits" list to the app. | M26 | P1 |
| Y2.22 | Voice: short-lived realtime client secrets, relay tool `hand_off_task` to the text loop, TTS preview, STT dictation proxy. | T:OT-ARCH | Local pipeline (Master 7.2); same `hand_off_task` pattern. | M17 | P1 |
| Y2.23 | E2E script creates a temp agent and exercises chat, computer tools, viewer, search, connections, voice, groups, settings; separate voice harness needs prepared audio file. | T:OT-README | Extends A2.8; include a **prepared-audio fixture** for voice tests. | M25 | P1 |
| Y2.24 | Per-user **Server-Sent Events** stream carrying row updates, live state, roster changes, computer state. | T:OT-ARCH | One SSE stream per client with typed event kinds. | M20 | P0 |
| Y2.25 | Routines: cron + **event routines** from connector triggers; proactive check-ins for the primary agent. | T:OT-ARCH | Extends A2.6; triggers only from user-configured free connectors. | M14, M15 | P1 |

### 2.3 openman

| ID | Feature | Source | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| Y3.1 | Principle: **"offer only what works":** UI never shows an option that is disabled or unavailable for this install. | T:OM-ARCH | Hide or explain unavailable features (with the exact missing requirement); never a dead button. | M19 | P0 |
| Y3.2 | Principle: **"reuse before building"** and **"the server is the only DB client."** | T:OM-ARCH | Daemon is the only DB writer; renderer never opens SQLite. | M4 | P0 |
| Y3.3 | **Versioned, idempotent, resumable provisioning steps:** each setup step has a version; bumping it re-runs only that step on next launch. | T:OM-ARCH | First-run/upgrade "setup steps" registry (create dirs, probe models, register tools) with per-step versions and retry. | M19, M22 | P1 |
| Y3.4 | **Relay stores every run event** so a client can reconnect and replay. | T:OM-ARCH | Event log + `Last-Event-ID` style resume. | M4, M20 | P0 |
| Y3.5 | Per-user concurrency limit sized to machine; extra tasks **queue and auto-start**. | T:OM-ARCH | Concurrency by RAM/VRAM from hardware detector (B1.7). | M4, M12 | P1 |
| Y3.6 | Table ideas: `task_events`, `task_files`, `project_proposals`, `knowledge`, `shares`, `notifications`, `automation_runs`, `recordings`, `meetings`, `api_keys`, `webhooks`, `webhook_deliveries`, **`revocations` (kept even when data is erased)**, `usage_counters`, `ops_events`, `ops_heartbeats`, `ops_alerts`, `task_costs`. | T:OM-ARCH | Reconcile with Master Section 10 in M0; add `revocations`, `ops_*`, `task_costs`, `automation_runs`, `webhook_deliveries` if missing. | M4 | P0 |
| Y3.7 | **Scheduler tick duties:** fire due automations, poll triggers, deliver/retry webhooks, backfill task costs, sweep idle task folders, record heartbeat, check alerts; ticks safe to overlap. | T:OM-ARCH | Single `tick()` with these jobs and idempotency keys. | M14 | P0 |
| Y3.8 | **Device-approval pairing flow** (short code shown, approve elsewhere, app polls; code expiry 30 min; cancel/retry states). | T:OM-README | Use for pairing phone/web clients and CLI to the daemon (C1.12, B4.8) with no account. | M20 | P1 |
| Y3.9 | **Sign out / Sign out everywhere / Disconnect** (disconnect deletes stored credentials and signs out all clients). | T:OM-README | Extends A3.6: three explicit actions in Settings > Sign-in & security. | M3, M19 | P0 |
| Y3.10 | **Local-only sign-in** gated to loopback + env flag; production refuses to start with the dev bypass set. | T:OM-README | Dev-bypass only in dev builds; release builds hard-fail if set (CI test). | M3, M25 | P0 |
| Y3.11 | **Mock agent** plays scripted runs when no real agent is configured. | T:OM-README | Already A3.3; add rule: UI dev mode uses mock, **release builds never ship it enabled**. | M2, M19 | P0 |
| Y3.12 | **Invite gate** (first account owns the list). | T:OM-README | Only for `keel serve` multi-client mode: paired-client list owned by the first admin client. | M20 | P1 |
| Y3.13 | `setup` script: generates missing secrets only, never overwrites, prints required values and the one step that must be done manually. | T:OM-README | Already A3.5; add "never overwrite" and "print remaining manual step" requirements. | M3 | P0 |
| Y3.14 | **First-run screen offers existing resources first** (reuse an existing machine/model) or creating new, shows cost/size before creating. | T:OM-README | Wizard: detect existing Ollama/llama.cpp models first; show disk/RAM cost of a download before pulling. | M19 | P1 |
| Y3.15 | Settings structure: Account, Sign-in & security, operator options (invite list, alerts, limits). | T:OM-README | Settings tree for M19e: General, Models, Permissions, Security, Connectors, Channels, Memory, Data & privacy, Admin. | M19 | P1 |
| Y3.16 | Public API (`/api/v1`) + outgoing webhooks + operator page. | T:OM-ARCH | Already A3.1/A3.9; version prefix and Keel-specific `/api/keel/v1`. | M20 | P1 |
| Y3.17 | Agent-proposed project updates require approval (`project_proposals`). | T:OM-README, OM-ARCH | Diff proposals (already Master 7.3). Add table + UI list. | M13 | P1 |
| Y3.18 | Large task files stay on the compute side; the app keeps a local cache with a configurable data dir (`OPENMAN_DATA_DIR`). | T:OM-ARCH | `KEEL_DATA_DIR` plus cache eviction (X7.10). | M4, M22 | P1 |
| Y3.19 | Brand strings in **one config file** and brand assets in one folder (fork must rename). | T:OM-README | `brand.ts`-style single source for product name/logo; supports later white-label (M24). | M19, M24 | P1 |
| Y3.20 | Docs set: README, ARCHITECTURE, `security-model.md` (explicit limits), `deploy.md`, `OPERATIONS.md`, AGENTS.md, CODE_OF_CONDUCT, TRADEMARKS, DISCLAIMER, NOTICE, THIRD_PARTY_NOTICES. | T:OM-README | Private equivalents; **security-model doc must list what Keel cannot protect against**. | M1, M23 | P1 |
| Y3.21 | Statement that the agent "runs as administrator on the computer" and can be misled by content it reads. | T:OM-README | Prominent first-run warning + permission preset explanation. | M19 | P0 |

### 2.4 nicks-stack

| ID | Feature | Source | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| Y4.1 | **`/mcp` chat command revives dormant servers instantly**; otherwise a keyed server revives within ~5 minutes automatically. | T:NS | `/reload` and background re-probe every 5 min (configurable). | M6 | P0 |
| Y4.2 | **Chat-based onboarding via QR** (no bot-creation step; scan and tap create) for Telegram. | T:NS | Channel pairing wizard with QR/deep link where the platform supports it; always show manual fallback. | M15, M19 | P1 |
| Y4.3 | First-boot **sign-in test-fire** with a 1-token call so a zero-credit account fails loudly. | T:NS | Already Master 9.3; add "fail loudly with the exact provider error". | M19 | P0 |
| Y4.4 | **Secret provider map:** one token unlocks a named vault/note whose fields are named exactly like env vars; the token is isolated in a separate env file; map is **disabled until the token exists** so the CLI never prompts interactively on every start. | T:NS | Optional `op`/`pass`/`bw` command provider (A4.7): shipped disabled; enabling it validates non-interactivity first. | M3 | P2 |
| Y4.5 | Webhook bridge as a **supervised service** that self-provisions a tunnel and wakes itself when keyed. | T:NS | Inbound webhooks only via user-provided tunnel (Master 7.4); supervised service pattern for the bridge. | M15 | P1 |
| Y4.6 | **Telemetry plugin + chat-side trace query MCP** (every model/tool call traced and queryable by the agent itself). | T:NS | Local traces + an internal `traces` MCP/tool so the agent can answer "what did you do". | M21 | P1 |
| Y4.7 | **Desktop-control plugin with 11 key-less tools** riding the VM's own auth. | T:NS | Enumerate the 11 tools in M0 teardown; Keel's local equivalents (screenshot, click, type, key, scroll, drag, bash, file read/write, window list). | M16 | P1 |
| Y4.8 | **Obsidian vault** the agent reads and writes, opened on the agent's desktop. | T:NS | Vault is plain Markdown (C1.8); open-in-user's-editor. | M13 | P1 |
| Y4.9 | **Persona file with rigor contract + coding-agent routing + desktop control plane** in one `SOUL.md`. | T:NS | `PERSONA.md` sections; routing table consumed by the router (X1.x / A4.5). | M7 | P0 |
| Y4.10 | **Skill library = one setup runbook per integration (21 units).** | T:NS | M0 lists all 21 and maps each to a Keel connector/channel. | M9 | P1 |
| Y4.11 | `config.yaml` carries model, MCP list, plugin list, secret map; "flip the model provider in two documented lines." | T:NS | Provider switch docs with two-line change examples per provider in the generated config reference. | M2 | P1 |
| Y4.12 | **Deterministic template build:** big file trees packed in one deterministic tarball because the publish API caps request size. | T:NS | Reproducible packaging; **artifact size budget check** per upload target. | M22 | P1 |
| Y4.13 | Version badge + `VERSION=x.y.z build` pattern; release scan proves **zero secrets baked in**. | T:NS | Release script takes `VERSION`; scan on artifacts (A4.8). | M22 | P0 |
| Y4.14 | Config for **16 plugins** and **13 MCP servers** as one preset. | T:NS | Preset bundle (C1.9). MCP presets limited to free: filesystem, git, fetch, SQLite, time, memory, Playwright, sequential-thinking, Linear (free tier, user token) etc. | M6, M10 | P1 |

### 2.5 clawdbot-channel-linq

| ID | Feature | Source | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| Y5.1 | `plugin.json` manifest at repo root + `channels.<id>` config namespace + `plugins.load.paths` for local development. | T:LQ | `channel.json` + `channels.<id>` config + dev-link paths. | M10, M15 | P0 |
| Y5.2 | **Install from git URL one-liner** with auto-build via `prepare`; `--link` for local development. | T:LQ | `keel plugin add <private git>`; `--link` dev mode (A5.2). | M10 | P1 |
| Y5.3 | **Webhook subscription lifecycle:** subscribe to a named **event list** (message.received/delivered/read/failed, reaction.added/removed, typing started/stopped), keep the returned signing secret, exported programmatic helper for subscription creation. | T:LQ | Channel SDK event enum + helper; generalize for Telegram/Discord/Matrix/Slack equivalents. | M15 | P1 |
| Y5.4 | Signature headers `X-Webhook-Signature` (hex HMAC) + `X-Webhook-Timestamp`; signed payload is `timestamp.rawBody`; reject older than 5 min; **missing secret means every request is rejected (401)**. | T:LQ | Already in Master; add "no secret configured = reject all", never "accept unsigned". | M3, M15 | P0 |
| Y5.5 | **Reaction mapping table** (emoji groups to native reaction types incl. skin-tone variants), and `react` action usable by the agent, removable. | T:LQ | Reaction map per channel in the capability matrix. | M15 | P2 |
| Y5.6 | Chat-id mapping cache stored under the credentials dir with documented reset. | T:LQ | Per-channel chat cache in SQLite with a "reset mapping" button. | M15 | P1 |
| Y5.7 | `status` command lists loaded channels; `gateway start`. | T:LQ | `keel gateway status` (A5.1). | M15, M20 | P0 |
| Y5.8 | Troubleshooting sections keyed by exact error strings ("token not configured", "fromNumber not configured", "webhook not receiving"). | T:LQ | Error catalog entries with the same pattern: message, cause, fix steps (C10.2). | M15, M23 | P1 |
| Y5.9 | **Excluded:** Linq API/iMessage/RCS/SMS (paid, cloud). Mark "Blocked for free". | T:LQ | Telegram, Discord, Matrix, Slack, email. | M15 | n/a |

### 2.6 Keel's own repo (what the tree tells us)

| ID | Observation | Source | Action | M | Pri |
| --- | --- | --- | --- | --- | --- |
| Y6.1 | Root holds many `agent-evidence-area*.md` files (commands, interactive-tui, skills, dependencies, file-editing, sandboxing, parallel-agents, permission-modes, mcp, tools-reference) plus `feature-checklist.md`, `test-plan.md`, `benchmark-and-evaluation-plan.md`, `compute-feasibility.md`, `interface-spec.md`, `llm-*` and `model-architecture-proposal.md`, `training-data-plan.md`. | T:KL | M0: build a **cross-walk** from each of these to plan IDs; anything uncovered becomes a row. Training-data and model-architecture docs stay out of scope (Master 4.2.5). | M0 | P0 |
| Y6.2 | `.verify-*` folders (`automode`, `headless-adv`, `modelconfig`, `raw`, `skills`, `verify5`) look like verification output; `.build` too. | T:KL | Move to `docs/archive/` (private) or ignore; ensure absent from artifacts (artifact allowlist scan). | M0, M1 | P0 |
| Y6.3 | Repo description names four surfaces: **Cowork, Code, Duet, Fleet**; homepage `keel-desktop.vercel.app`. | T:KL | Implement surface switcher (C2.5); apply D5/free-tier checks to the website host. | M19, M23 | P0 |
| Y6.4 | Repo is **Public** with 0 stars/forks (as of this fetch). | T:KL | Gate G1 still pending; run Appendix B only after owner approval. | M1 | P0 |

## 3. Paid or hosted pieces in the references and their free replacement

| Reference piece | Source | Free replacement in Keel |
| --- | --- | --- |
| Orgo cloud computers, credits, plans | OT-README, OM-README | Local container desktop (M16); no cloud |
| Composio (apps, sign-in, triggers) | OT-README | Direct connectors and free/self-hosted MCP servers with user's own OAuth/tokens (M15) |
| xAI Grok API / realtime voice | OT-README | Local models; local STT/TTS (M17) |
| Claude via Orgo proxy | OM-README | Optional user-key provider only |
| Supabase Postgres | OM-ARCH | SQLite WAL (locked decision) |
| AgentMail / AgentPhone / AgentCard | OM-README, NS | IMAP/SMTP of the user's own mailbox; SMS/phone/payment cards **excluded** |
| ElevenLabs | OM-README | whisper.cpp + Piper/Kokoro (license check X0.7) |
| 1Password, Latitude, Honcho | NS | OS keychain + optional user-owned CLI provider; local traces; local memory |
| ngrok / cloudflared tunnels | LQ, NS | Prefer outbound channels; inbound only via a user-provided tunnel |
| X API, vidiq, ideabrowser MCPs | NS | Not included (paid/third-party); skip |
| Hermes Agent (Nous), gpt-5.5 | NS, OM-README | Keel's own loop; Hermes is a reference only (verify license before reading code) |
| Linq (iMessage/RCS/SMS) | LQ | Excluded (Y5.9) |
| opencode hosted share/Console/infra (`sst`) | OC-README, OC-PLUGINS | Excluded; local HTML export instead |

## 4. UI/UX inventory to capture in M0 (from what these sources actually show)

Capture one **screen spec** (Addendum 3 Section Q template) per item; styling comes only from Keel tokens.

- **opencode:** terminal UI with Build/Plan toggle (Tab); desktop app (beta); Settings > Extensions > Plugins list with per-plugin switch and Reload; question form (header, choices, multi-select, free text); update notice; subagent "background child" indicators; worktree-aware session list. `T:OC-README, OC-TOOLS, OC-PLUGINS`
- **orgo-teammates:** sidebar (agent roster), chat transcript, details panel with tabs **Activity, Tasks, Library**, modals, settings, computer viewer (watch / take over), voice call bar, approval/question/connect/draft cards, group rooms. `T:OT-ARCH`
- **openman:** landing page, sign-in dialog and `/signin` (code approval + API key paste), first-run computer picker with price, task view with live desktop and Agent/Chat/Plan modes, projects, skills library, connectors, automations with run history, websites build/preview/publish, slides/audio generators, meeting notes, settings (Account, Sign-in & security), operator admin page, public docs. `T:OM-README, OM-ARCH`
- **nicks-stack:** first-boot setup window (model sign-in, QR pairing, optional secret-provider step). `T:NS`
- **Keel today:** existing screens read locally from `keel/` renderer in M0. `T:KL (source not readable by tools)`

## 5. Corrections to earlier plan text, from what was read

1. Master 7.1 says Plan agent "cannot write even if config allows" and "asks before bash": README confirms plan denies edits **by default** and asks before bash `[T:OC-README]`. Keep Keel's stricter "cannot write" rule as an intentional difference and record it.
2. Addendum 1 A1.10/A1.11: opencode's `todo` is **opt-in experimental** and its websearch uses selectable providers (some third-party). Keel keeps todo on by default but **no paid search provider** `[T:OC-CONFIG]`.
3. Addendum 1 A1.21 "remove versions older than X" is a README **tip**, not a feature; implement as installer pre-check only if upgrades require it.
4. Master Section 6 rule 6 (permissions) should add the **policies** layer and the rule that policy enforcement plugins cannot be disabled by project config `[T:OC-CONFIG, OC-PLUGINS]` (Y1.17, Y1.30).
5. Master 3.1 listed orgo-teammates "Library", "noVNC via relay": confirmed; the relay **drops input in watch mode server-side** `[T:OT-ARCH]` (Y2.14): add to the M16 acceptance test.
6. Master 7.4 said nicks-stack has "13 MCP servers"; confirmed and note **16 plugins** `[T:NS]`.

## 6. Builder protocol for `[S]` items (ideas with no repo reference)

Every `[S]` row below must follow this sequence. No `[S]` row is "complete" without all seven steps recorded in `PLAN-INDEX.json`.

1. **Research note (private, 1 page):** what the feature is, 2 or more existing products/standards that do something similar, and why Keel needs it. Cite sources; no copying.
2. **License and free check:** list every library, model or service; record license and date (FREE-TIER-REGISTER, X0.6). Reject anything paid or account-gated.
3. **Spec in Keel's words:** user story, behavior, edge cases, failure modes, permissions touched, data stored, what is Tier 2 (never configurable).
4. **Smallest shippable slice:** build the minimal version behind a feature flag labeled `experimental` (X6.10).
5. **Tests first for risk:** security-relevant `[S]` rows need a negative test (what must be refused) before the feature test.
6. **Evidence:** run it end to end, store the run id; verify offline behavior (X0.8).
7. **Owner review gate:** if the feature stores new personal data, touches the network, or affects Tier 2, stop and ask the owner before enabling by default.

## 7. Additional own suggestions `[S]` (not in any repo or earlier addendum)

| ID | Feature | Builder approach (see Section 6) | M | Pri |
| --- | --- | --- | --- | --- |
| Z1 | **Project environment lockfile** (`.keel/lock.json`): pins versions/hashes of skills, plugins, MCP servers, model files and prompt profiles used by a project; mismatch warns before running. | Hash each installed extension at install time; compare at session start; auto-regenerate on user approval. Reuse Y1.29 pin semantics. | M9, M10 | P1 |
| Z2 | **Agent contract tests:** each agent/skill ships tests (scripted fixture-model runs, X9.1) that assert tool allowlist, refusal behavior and output shape; run on install and update. | Define a `tests/` folder spec inside skill/agent packs; runner uses the mock model. | M9, M25 | P1 |
| Z3 | **Redacted replay export:** export a session as standalone HTML with secrets/paths/PII redacted and an integrity hash. | Reuse DLP (B3.8) and redaction (B3.6); show a redaction preview; no network assets. | M4, M3 | P1 |
| Z4 | **Crash-safe turn journal** with exact resume point after power loss (tool call started, result pending). | Write-ahead entry before each tool run, mark done after; on restart show "interrupted tool, retry or skip". Extends Y2.4/Y2.6. | M4 | P0 |
| Z5 | **Capability negotiation handshake** between daemon and every client (TUI, web, IDE, phone): client declares supported UI features (question form, diff viewer, image display, plugin panels). | JSON `capabilities` object sent at connect; daemon degrades gracefully (e.g., text prompt if no form support). Extends Y1.9. | M20 | P0 |
| Z6 | **Local-first sync via the user's own folder** (settings, memory, skills) with conflict resolution UI, no server. | Append-only change files + last-writer-wins per key with visible conflicts; encrypted (B4.11). | M14, M22 | P2 |
| Z7 | **Household/OS-user separation:** per-OS-user data dirs and separate keychain entries; admin can lock model downloads. | Use OS user profile paths; managed policy keys for restrictions. | M22, M24 | P2 |
| Z8 | **Energy and cost estimator for local runs** (tokens/sec, estimated wattage) shown in the usage dashboard. | Use measured tokens/sec and user-entered power draw; label as an estimate. | M21 | P2 |
| Z9 | **Natural-language policy editor:** user describes a rule ("never run git push"), Keel proposes the exact rule, simulates it (policy simulator), user approves. | LLM proposes JSON rule; validator + simulator show matches; Tier-2 conflicts rejected. Extends Y1.35. | M3, M19 | P1 |
| Z10 | **Provider/model drift detector:** weekly local job re-runs the model health check (X1.16); alerts if tool-call score drops after a model or runtime update. | Store scores per model hash and runtime version in SQLite; compare. | M21 | P1 |
| Z11 | **Dormant-integration health board:** one screen listing every connector/channel/MCP server as dormant, connecting, active, error, with last probe time and the exact missing setting. | Reuse probe() (A4.6) and Y4.1 re-probe schedule. | M15, M19 | P0 |
| Z12 | **Offline signed catalog updates:** model catalog, MCP presets and language packs delivered as signed bundles through the update feed or USB (C12.2). | Same Ed25519 chain as release artifacts; verify before import; versioned. | M22 | P1 |
| Z13 | **"Why can't I do X?" explainer** for disabled features: shows which requirement/policy/flag blocks it. | Every feature has a `requires` list; UI renders it. Extends Y3.1. | M19 | P1 |
| Z14 | **Pre-flight installer report** ("this installer will create these files, register these protocols, add this service") before install and in docs. | Generate from the build manifest; display in installer and on download page. | M22, M23 | P2 |
| Z15 | **Prompt-injection regression corpus** that grows from real blocked events (opt-in, local, anonymized) and is replayed in the red-team suite (C8.8). | Store hashed + redacted samples locally; never upload. | M3, M21 | P1 |
| Z16 | **Per-project cost budgets and "stop at budget" with summary** (tokens for local, dollars for user-key remote). | Ledger enforcement (A3.10) with a project scope. | M21 | P1 |

## 8. Priority order for this addendum

1. **Foundation correctness:** Y2.1, Y2.2, Y2.4, Y2.5, Y2.6, Y3.4, Y3.6, Z4, Z5.
2. **Tool fidelity:** Y1.2 to Y1.9, Y1.11, Y1.16, Y1.17, Y1.30.
3. **Security parity:** Y2.7, Y2.8, Y2.14, Y2.20, Y3.9, Y3.10, Y3.11, Y3.21, Y5.4.
4. **Reliability and ops:** Y3.7, Y4.1, Y2.18, Z11.
5. **Everything else** at its milestone; P2 after v1.0 candidate is green.
6. Add all rows to `PLAN-INDEX.json` with their source tag; no `[T]` row may be implemented from copied code, and no `[S]` row skips Section 6.


---

# Appendix A5 — Addendum: DeepSeek Harness and Deep Reads (preserved)

# Keel Plan v5 Addendum 5: DeepSeek Harness, Deeper Reads of Existing References, Plan Conflicts and Builder Guide

Adds only items **not already in** Master Plan, Addenda 1 to 4. Free-only. Milestones follow v5. Every row names its source. IDs use prefix `W` (reference-derived) and `V` (own ideas) to avoid collisions.

## 0. Source tags and keys

| Tag | Meaning |
| --- | --- |
| `[T:key]` | Read this session (21 Nov 2026) in the named source. Reimplement from behavior only (X0.10). |
| `[K]` | General knowledge, verify in M0. |
| `[S]` | My suggestion, **no repo behind it**: follow the builder protocol in Section 7. |

Keys: **DS** = github.com/deepseek-ai/deepseek-harness (README + file tree only) · **OC-AGENTS / OC-PERM / OC-MCP / OC-CMD** = opencode.ai/docs/agents, permissions, mcp-servers, commands · **NS-SOUL** = nicks-stack `files/SOUL.md` · **OM-SEC** = openman `docs/security-model.md` · **OT-SEC** = orgo-teammates `SECURITY.md`. Earlier keys (OC-TOOLS, OC-CONFIG, OC-PLUGINS, OT-ARCH, OM-ARCH, OM-README, NS, LQ, KL) are as defined in Addendum 4.

## 1. Read status (honest)

**Read this session now:** DeepSeek Harness front page (README, file tree, topics, license badge), opencode `agents`, `permissions`, `mcp-servers`, `commands`, nicks-stack `SOUL.md`, openman `security-model.md`, orgo-teammates `SECURITY.md`.

**Still unread (M0 reading list):**
1. **DeepSeek Harness:** `docs/architecture.md`, `docs/development.md`, `docs/user/guide/index.md`, `SAFETY.md`, `AGENTS.md`, `CLAUDE.md`, `BENCHMARK.md`, `BRAND_GUIDELINES.md`, `.agents/`, `.claude/`, `packages/*`, `apps/*`, `native/*`, `python/*`, `vendor/*`, `benchmarks/*`, `snapshots/*`, `website/*`, and the Cordis framework repo + the paper cited in the README. The package/app/plugin list inside this repo is **unknown to me**; every `DS` row below is README/tree-level only.
2. opencode: `policies`, `skills`, `themes`, `providers`, `models`, `websearch`, `network`, `snapshots`, `compaction`, `formatters`, `references`, `attachments`, `instructions`, `warming`, `migrate-v1`, `troubleshooting`, `build/plugins`, `api`, `cli`.
3. orgo-teammates `docs/orgo-builder-guide.md`, `docs/xai-and-composio.md`; openman `docs/deploy.md`, `OPERATIONS.md`, `AGENTS.md`; nicks-stack `files/config.yaml`, `files/skills/*`, `plugins/orgo-desktop-local/`; linq `src/*`.
4. Keel `keel/` source (not readable by these tools).

## 2. DeepSeek Harness (DS): features and what to take

| ID | Feature | Source | Free Keel implementation / approach | M | Pri |
| --- | --- | --- | --- | --- | --- |
| W1.1 | **"Everything is a plugin" architecture:** core features themselves are plugins on a composable runtime (built on Cordis; paper cited in README). | T:DS | Keel is Python; do **not** adopt Cordis. Clean-room: build a plugin **scope tree** (see V1) so providers, tools, channels, UI panels, memory backends and even built-in agents register through the same plugin API and can be disabled/replaced. | M10 | P0 |
| W1.2 | **Single command web launch** (`npx @deepseek-ai/dsh web`) serving a Web UI at `127.0.0.1:3080`, auto-opening the browser locally. | T:DS | `keel web` (A1.4) default loopback port; `--no-open`; also `pipx run`/`uvx` style zero-install launch documented for devs only. | M20 | P1 |
| W1.3 | **SSH-aware launch:** over SSH only print the host URL (client or editor owns the forwarded address). | T:DS | Detect `SSH_CONNECTION`/`SSH_TTY`; print URL + forwarding hint, never open a browser. | M20 | P1 |
| W1.4 | `--no-open` flag; Web and Desktop targets from one codebase (`apps/`, `native/`, Makefile targets for both). | T:DS tree | One renderer bundle used by Electron and `keel web` (A1.4); `make help` style task list for builder. | M19, M20 | P1 |
| W1.5 | **Test suite taxonomy by config:** unit, **bench**, **e2e**, **expected** (golden expected outputs), **snapshot**, **web**, **web-stress**, **web-perf** as separate runner configs; plus Python tests (`pytest.ini`). | T:DS tree | Mirror as separate CI jobs: `unit`, `bench`, `e2e`, `golden`, `snapshot`, `web`, `web-stress`, `web-perf`. Adds `web-stress` and `golden` which Addendum 3 lacked as named suites. | M25 | P0 |
| W1.6 | **`benchmarks/` + `BENCHMARK.md`** at repo root, and `snapshots/` folder. | T:DS tree | Private benchmark folder with documented method; per-release results stored (C13.5). | M21 | P1 |
| W1.7 | **Staged-only lint config** (`.oxlintrc.staged.json`), `lefthook.yml` git hooks, `.jscpd.json` **duplicate-code detector**, `.rgignore` (files ripgrep should skip), `.gitattributes`, `.editorconfig`. | T:DS tree | Python equivalents: ruff on staged files via lefthook/pre-commit; add a duplicate-code check (jscpd is MIT, verify) and a project `.rgignore` consumed by Keel's own grep tool. | M0 | P1 |
| W1.8 | **Dual CI config** (`.github` and `.gitlab-ci.yml`) in one repo. | T:DS tree | Supports C11.1: keep CI definitions portable so the private repo can be mirrored to a free forge with protected branches. | M1 | P1 |
| W1.9 | **`i18n.yaml` single-source docs:** `README.i18n.yaml`, `CONTRIBUTING.i18n.yaml`, `SAFETY.i18n.yaml`, `BRAND_GUIDELINES.i18n.yaml` alongside `.md` and `.zh.md`. | T:DS tree | Keep user-facing docs (README-equivalents, safety notice, EULA summary) as YAML string sources and generate localized Markdown/HTML in CI (extends M25 i18n). | M25 | P1 |
| W1.10 | **`SAFETY.md` surfaced as a first-run notice** ("review the safety notice before running"). | T:DS | In-app **Safety notice** shown at first run and linked from the website; versioned, re-shown when changed (like EULA, C11.5). | M19, M23 | P0 |
| W1.11 | **Developer-preview banner:** explicit "compatibility-breaking changes will happen". | T:DS | Experimental-label policy (X6.10) and a visible version/stability channel in About. | M19, M22 | P1 |
| W1.12 | **`BRAND_GUIDELINES`** file (also localized). | T:DS tree | Keel brand/usage guidelines (C11.7) generated into the website. | M23 | P2 |
| W1.13 | **Builder instruction files for multiple AI tools:** `AGENTS.md`, `CLAUDE.md`, `.agents/`, `.claude/`. | T:DS tree | Private repo keeps `AGENTS.md` plus a `CLAUDE.md` pointer so any AI builder picks up the same rules; Keel also **reads** these files as instruction sources (C7.1). | M0 | P1 |
| W1.14 | **Plugin discoverability via a repository topic** (`dsh-plugin`). | T:DS | Excluded as public mechanism (G7: extension docs private). Replace with a **private plugin index file** the app reads. | M10 | P2 |
| W1.15 | **`python/` package in a TS monorepo** (language bindings or SDK). | T:DS tree | Treat as evidence that an SDK in the other language is expected; Keel ships Python SDK plus a thin TypeScript client (X6.3). Verify what `python/` actually contains in M0. | M20 | P1 |
| W1.16 | **`patches/` and `vendor/`** folders for patched/vendored dependencies. | T:DS tree | Policy: vendored code lives in `vendor/` with its license file and a `PATCHES.md` listing each local modification and upstream issue. | M0, M1 | P1 |
| W1.17 | **Discussions-only feedback** (no Issues tab visible), Discord, citation block, docs site, website folder in repo. | T:DS | Keel: private repo, so feedback via email and in-app redacted bundle (C10.4); public docs site only (no source links). | M23 | P2 |
| W1.18 | MIT license + `THIRD_PARTY_NOTICES.md`. | T:DS | Same notices rule; verify `LICENSE` text and every `vendor/` license in M0 before reading any code. | M0 | P0 |

## 3. Deeper opencode reads (agents, permissions, MCP, commands)

### 3.1 Agents `[T:OC-AGENTS]`

| ID | Feature | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- |
| W2.1 | Markdown agent files with YAML frontmatter; **nested path becomes agent ID** (`team/reviewer`); global + project locations; same fields as config entries; body is the system prompt. | `.keel/agents/**/*.md`, nested IDs. | M7 | P0 |
| W2.2 | **Modes** `primary` / `subagent` / `all`; subagents run in child sessions with fresh context. | Agent `mode` field. | M7, M12 | P0 |
| W2.3 | **Built-ins:** build, plan, general (no further subagents), explore (read-only incl. web); **hidden maintenance agents** (`compaction`, `title`, `summary`) that are not user-selectable and have all actions denied except their job. | Ship the same set; hidden agents map to model roles (`summarizer`, `title`). | M7 | P0 |
| W2.4 | **`steps` limit:** max model steps per turn; on the final step tools are removed and the model must summarize in text; new user input resets. | `max_steps` with forced-summary final step (also feeds doom-loop break C3.2). | M7 | P0 |
| W2.5 | `hidden`, `color`, `disabled` agent fields; `disabled` removes a built-in at config load. | Same fields; `hidden` is visibility only, not security (document this). | M7, M19 | P1 |
| W2.6 | **Subagent launch permissions:** parent's `subagent` rules control **which agents** it may launch (e.g., deny `*`, allow `reviewer`); child uses its own permissions, not a subset of parent's. | Per-agent allowlist of launchable agents; document that child permissions are independent. | M12, M3 | P0 |
| W2.7 | Default agent resolution chain: configured default, else `build`, else first visible primary-capable; changing default does not alter existing sessions. | Same chain. | M7 | P1 |
| W2.8 | `system` replaces the provider base prompt for that agent, but **project instructions, skills, references still get added**. | Prompt assembly order documented and golden-tested (X1.15). | M7 | P0 |
| W2.9 | Agent merge semantics: later scalars replace, maps merge by key, **permission rules append**; global rules apply before agent rules. | Config merger with these rules. | M2 | P0 |
| W2.10 | Model reference format `provider/model#variant` and an expanded object form. | Variant support (e.g., effort level) in model refs. | M2 | P1 |
| W2.11 | Plan agent may write **only plan files** in a dedicated plan folder; shell stays permission-controlled. | Plan agent writes under `.keel/plans/` only (keeps Keel's "plan cannot edit code" rule). | M7 | P0 |

### 3.2 Permissions `[T:OC-PERM]`

| ID | Feature | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- |
| W3.1 | Rule = `{action, resource, effect}`; effects `allow/deny/ask`; **no match means ask**. | Default-ask baseline. | M3 | P0 |
| W3.2 | **Last matching rule wins** (broad first, exceptions after); rules combine in order: lower-priority config, global, then agent. | See Conflict C-1 in Section 6: pick one order and document; show "winning rule" in policy simulator. | M3 | P0 |
| W3.3 | Wildcards: `*` matches any characters including `/`; `?` one character; whole-value match; backslashes normalized; **case-insensitive on Windows**; shell pattern ending ` *` also matches the bare command. | Same matcher with property tests (B7.1). | M3 | P0 |
| W3.4 | **Multi-resource operations:** any `deny` denies; else any `ask` asks; else allow (e.g., a patch touching several files). | Same aggregation. | M3, M5 | P0 |
| W3.5 | `~` / `$HOME` expansion at config load for path actions only; **shell resources stay raw text**. | Same. | M3 | P1 |
| W3.6 | **`external_directory` action:** paths outside the project/worktree are checked before read/edit rules. opencode's default is **allow**. | Keel default: **ask** (Cautious/Balanced), allow only in Trusted. Intentional difference. | M3 | P0 |
| W3.7 | **Shell scanner** for Bash, Zsh, POSIX sh and PowerShell: each extracted subcommand and `cd` target is checked; malformed or dynamically evaluated commands return a **scanner error instead of running**. | Implement as part of the Tier-2 command analyzer; "cannot analyze" = refuse or force ask, never allow. | M3 | P0 |
| W3.8 | **Base default policy:** allow all, but **ask on `.env` / `.env.*` reads except `.env.example`**. | Keep sensitive-file ask list (env files, key files); Tier-2 protected paths stay stricter. | M3 | P0 |
| W3.9 | **Approval replies:** `once`, `always` (saves tool-proposed patterns, **project-scoped**, never overrides a configured deny), `reject` (**rejects every other pending request in that session**; optional feedback text to the model). | Same three buttons; each tool proposes the saved pattern (shell: command prefix; skill/subagent: ID). | M3, M19 | P0 |
| W3.10 | **Policies layer** can hard-deny after rules and saved approvals; turns allow/ask into deny, never grants; global/managed policies override project config. | Matches managed policy (Y1.17); add test "policy never grants". | M3, M24 | P0 |
| W3.11 | Permission actions for MCP resources: `list_mcp_resources` (resource = server) and `read_mcp_resource` (resource = `<server>:<uri>`); MCP tools as `<server>_<tool>`. | Same action names under `keel_` prefix. | M6, M3 | P1 |
| W3.12 | Non-interactive clients must decide approval behavior; **configured deny always enforced**. | `keel run` flags: `--approve=never|rules-only`; default never auto-approve. | M20 | P0 |
| W3.13 | Docs warning: shell has full host authority; **prefer narrow allowlists over trying to recognize every dangerous command**. | Presets ship allowlist-style (Cautious), not denylist-style. | M3, M19 | P0 |

### 3.3 MCP `[T:OC-MCP]`

| ID | Feature | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- |
| W4.1 | CLI: `mcp add` (remote `--url`, local `-- cmd`, `--env`, `--header`, `--global`), `mcp list`, `mcp auth`, `mcp logout`; in-app `/mcps` to view/connect/disconnect/authenticate. | `keel mcp ...` and `/mcps` panel. | M6 | P0 |
| W4.2 | Config shape: `mcp.servers.<name>` with `type local|remote`, `command`, `cwd`, `environment`, `url`, `headers`, `oauth`, `disabled`, `codemode`, `timeout`, `protocol`, `pool`. **A higher-precedence config replaces the whole server object** (no field merge). | Same, and **warn** when an override drops fields. | M6 | P0 |
| W4.3 | **OAuth for remote servers:** PKCE, discovery, refresh; credentials stored **outside** project config; `oauth:false` for header-key servers. | Keychain-stored tokens; same. | M6 | P0 |
| W4.4 | **Client registration order:** pre-registered `client_id` first, then **Client ID Metadata Documents (CIMD)**, then **Dynamic Client Registration (DCR)**; options `client_secret`, `scope`, `callback_port`, `redirect_uri`, `auth_server_metadata_url`. | Implement the same order. CIMD needs a hosted metadata URL: Keel must **not** require a Keel-operated server, so fall back to DCR or user-supplied client IDs. | M6 | P1 |
| W4.5 | **OAuth when the browser is on another machine** (SSH/container): user pastes the failed callback URL into a prompt. | "Paste callback URL" fallback in the MCP sign-in dialog. | M6, M19 | P1 |
| W4.6 | **Timeouts:** startup 30 s, catalog 30 s, execution 12 h defaults; global and per-server. | Same defaults, plus a visible long-running-call indicator and cancel. | M6 | P0 |
| W4.7 | **Protocol version selection** (`legacy`, `auto` probe, pinned newest revision) with probe cost warning. | `protocol` field; default conservative. | M6 | P2 |
| W4.8 | **Pooled shared connections** across project directories when everything that changes the connection matches. | Share one MCP process across projects only when settings are identical (saves RAM). | M6, M21 | P2 |
| W4.9 | **Tool naming normalization** (`<server>_<tool>`, invalid chars to `_`, collisions need unique short names). | Normalizer + collision detector with a clear error. | M6 | P0 |
| W4.10 | **MCP prompts become slash commands** named `<server>:<prompt>` with positional args. | Command registry imports MCP prompts. | M6, M7 | P1 |
| W4.11 | **Server instructions** returned at init are injected into the system prompt in a tagged block; omitted when the agent's permissions deny all that server's tools. | Same; mark as **tainted/untrusted** text, lower priority than user instructions. | M6, M7 | P1 |
| W4.12 | **Elicitation** (server asks the user for input mid-call) rendered as a form or a link; dismiss cancels. | Question card variant for MCP elicitation (Y1.9). | M6, M19 | P1 |
| W4.13 | opencode sends the **session ID in request `_meta`**; docs warn remote servers may log it. | Keel sends **no session id** by default; optional opaque per-server correlation id (V6). | M6, M3 | P0 |
| W4.14 | `disabled` flag keeps a server configured but unconnected; disconnect in UI does not edit config. | Same. | M6 | P1 |

### 3.4 Commands `[T:OC-CMD]`

| ID | Feature | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- |
| W5.1 | Markdown or JSON commands; **nested folders become `/team/review`**; global vs project; project overrides global; nearer overrides ancestor; custom may replace built-in; **hot reload**. | `.keel/commands/**/*.md`. | M7 | P0 |
| W5.2 | Frontmatter: `description`, `agent`, `model`, `subagent` (true/false/omit rules); legacy alias `subtask`. | Same fields. | M7 | P0 |
| W5.3 | **Arguments:** `$ARGUMENTS`, positional `$1..$n` with quote grouping (last placeholder takes the rest, missing = empty); **fallback appends args** when no placeholder. | Same parser with tests. | M7 | P0 |
| W5.4 | **Shell injection** `!` + backtick command: output inserted into the prompt; opencode notes it **runs outside the agent permission flow**. | Keel: run through the **permission gate and Tier 2** like any shell call; show the resolved command to the user before first run. Intentional difference. | M7, M3 | P0 |
| W5.5 | Model precedence: command model, else command agent's model, else session model. | Same documented order. | M7 | P1 |
| W5.6 | **Background child commands** (`subagent: true`): result or failure reported back to parent. | Command runs as child task (Y1.11). | M7, M12 | P1 |
| W5.7 | `@path` is **not** expanded in stored templates; attachments come from the composer. | Same; avoids hidden file reads. | M7 | P1 |

## 4. Deeper reads of the nicks-stack / openman / orgo-teammates docs

### 4.1 Persona contract `[T:NS-SOUL]`

| ID | Feature | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- |
| W6.1 | **Accuracy-over-approval response contract:** verify facts/figures/citations before finalizing; never fabricate; say unknown plainly; **do not anchor on user-supplied numbers**; independent estimates. | Default `PERSONA.md` rigor section + eval (V7). | M7 | P0 |
| W6.2 | **Explicit confidence labels** (high / moderate / low / unknown) on judgments. | Optional response mode; required for factual web claims (C3.10). | M7 | P1 |
| W6.3 | **Anti-sycophancy rules:** no praise of questions, say immediately if the user is wrong, strongest counterargument first, **do not capitulate under pushback without new evidence**. | Include; **do not** copy the instruction to avoid all ethics/safety caveats or to be "aggressive": Keel keeps its own safety messaging and Tier-2 behavior. | M7 | P0 |
| W6.4 | **Conductor + specialists routing:** one conductor agent; external coding agents as optional specialists for multi-file work; **one writer per dirty tree**; always verify diffs/tests after a specialist. | `External specialist adapters` for coding CLIs the **user already has** (V8). | M12 | P1 |
| W6.5 | **Control-plane routing:** prefer local desktop tool over cloud tools when local is healthy; accessibility-tree enrichment optional; DOM work prefers browser tools. | Tool-choice hints in `PERSONA.md`: local desktop tool, then browser tool for DOM. | M16, M7 | P1 |
| W6.6 | **Running ledger of important account facts/decisions** in a memory file. | `MEMORY.md`-style notes in the vault with approval for writes (C3.7). | M13 | P1 |

### 4.2 Security model `[T:OM-SEC]` and `[T:OT-SEC]` (new items only)

| ID | Feature | Free Keel implementation | M | Pri |
| --- | --- | --- | --- | --- |
| W7.1 | Explicit **trust boundary list** (client untrusted, daemon holds secrets, agent environment powerful, third parties). | `security-model.md` (private) + in-app "What Keel protects and what it cannot". | M1, M3 | P0 |
| W7.2 | Live-view URL given only to the owner with **`Cache-Control: no-store`**. | Same for any viewer endpoints. | M16 | P1 |
| W7.3 | Secrets sealed with AES-256-GCM, **random 12-byte IV per value + auth tag**; session cookie sealed with its own key and **additional authenticated data**, HttpOnly, SameSite=Lax, Secure when HTTPS, 30-day life, **checked against a revocations table**. | `keel web` session cookie design; revocations table (Y3.6). | M3, M20 | P0 |
| W7.4 | **API keys:** prefixed random token, stored only as SHA-256, **shown once**; per-key rate limit; per-user idempotency keys. | Local API tokens for CLI/IDE/phone clients (Z30). | M3, M20 | P0 |
| W7.5 | **Secrets reach child processes as a staged file read-and-deleted by the setup script, never on a command line.** | Rule for MCP/plugin launches: pass secrets via env/file descriptor, never argv (visible in process lists). | M3, M6 | P0 |
| W7.6 | **Log redaction plus keyed hash of user ids** instead of ids. | Redactor + keyed hashes for any identifiers in logs/traces. | M3, M21 | P0 |
| W7.7 | **Sign-in bound to the browser that started it** by a sealed SameSite=Strict cookie, so a forwarded link can't be completed by someone else. | Pairing codes (Y3.8) must be completable only on the initiating client. | M20 | P0 |
| W7.8 | Sign-in/pairing attempts **rate limited per client address and globally**; use trusted-proxy hop count for address detection; **only same-origin relative return paths honored**. | Rate limits on pairing; open-redirect guard in `keel web`. | M20, M3 | P0 |
| W7.9 | **CSRF origin check** for cookie-bearing state-changing requests; bearer routes exempt. | `keel web`: Origin check (also in Master 11.1). | M20 | P0 |
| W7.10 | SSRF safe fetch details: http(s) only, **resolve then pin the checked address**, re-check every redirect, cap time and size. | Add "pin resolved IP" and redirect re-check to acceptance tests (Master 11.7). | M3 | P0 |
| W7.11 | **Streaming body-size enforcement** (not just Content-Length), bounded multipart uploads, capped recordings. | Same in local API. | M20 | P1 |
| W7.12 | **Generic client errors + request id**, details only in server log. | Error format with `request_id`; "copy details" in UI pulls from local log. | M20, M21 | P1 |
| W7.13 | **Security headers for any served UI:** CSP, `X-Frame-Options: DENY`, HSTS (when HTTPS), `nosniff`, strict referrer policy, COOP, permissions policy (microphone only inside the app). | `keel web` header set; test per header. | M20 | P0 |
| W7.14 | **Rendering safety:** Markdown rendered **without raw HTML**; link scheme allow-list; no `dangerouslySetInnerHTML`; inline-served HTML/SVG/XML get a **sandboxing CSP**; generated-site previews in a **sandboxed iframe**. | Same in renderer; add XSS test corpus (X9.x). | M19, M18 | P0 |
| W7.15 | **Share tokens with 144 bits of randomness**; public share pages show **redacted** text and short tool previews, never owner identity or instructions. | Local HTML export (Z3) uses the same redaction level. | M4 | P1 |
| W7.16 | **Publishing copies only from the site's own folder; never hidden files or symlink targets outside.** | Sites exporter (M18) uses realpath containment. | M18 | P0 |
| W7.17 | Inbound channel rules: signature verified with constant-time compare, **300 s window, de-duplication, refuse when no secret configured**; **only approved senders can start work**; **voice/phone-initiated tasks require a confirmation code**; email triggers accept **only clean mail and by default only from the owner's address**. | Channel defaults: pairing/allowlist; for remote-initiated risky actions require confirmation in the desktop app (V9). | M15, M3 | P0 |
| W7.18 | **Spending caps enforced atomically in the database before each vendor call.** | Ledger check-then-increment in one transaction (A3.10). | M21 | P0 |
| W7.19 | **Honest "known limitations" list:** prompt injection can still misuse granted power; "watch only" enforced only in client in openman (orgo-teammates enforces on server); one shared sign-in budget; self-hosting is only as safe as setup. | Keel About > "Known limits" page; choose **server-side watch-only**. | M26 | P0 |
| W7.20 | Deployment hygiene from orgo-teammates: **narrowest-scope keys**, never show keys on screen/recordings, set provider spend limits, **be careful with "Always allow"**, private vulnerability reporting, **only latest branch supported, best-effort fixes**. | Same in docs; support policy statement on website (X10). | M23 | P1 |

## 5. New small items from earlier sources that Addendum 4 missed

| ID | Feature | Source | Approach | M | Pri |
| --- | --- | --- | --- | --- | --- |
| W8.1 | orgo-teammates **`ALLOWED_EMAILS` supports `@domain` entries** → paired-client allowlist should support **patterns** (e.g., device label prefixes), not only exact entries. | T:OT-README | Pattern support with explicit test. | M20 | P2 |
| W8.2 | openman: **recordings and screenshots capped in the database**. | T:OM-SEC | Size caps for recorded skills (M9) and screenshots in events. | M4, M9 | P1 |
| W8.3 | openman: **computers named in a request are checked against the user's own listing; changes to the home computer through the API are refused.** | T:OM-SEC | Container-desktop IDs validated against the daemon's own pool; core desktop not mutable by agents. | M16 | P1 |
| W8.4 | opencode `question` and MCP elicitation share one UI form. | T:OC-TOOLS, OC-MCP | One question-card component, two sources. | M19 | P1 |

## 6. Conflicts and corrections to earlier plan text (read before building)

| ID | Conflict | Resolution |
| --- | --- | --- |
| C-1 | **Rule order.** Master 6 rule 6 says "first match wins"; Addendum 4 Y1.17 said it matches opencode. opencode is **last match wins** `[T:OC-PERM]`. | Builder must pick **one** and document it everywhere (simulator, UI, docs). Recommendation: **last-match-wins for Tier 1** (broad first, exceptions after; easier to read and matches the user's likely mental model if they've used opencode) with **deny-aggregation for multi-resource ops** and **Tier 2 always above**. Record in `DECISIONS.md`; owner confirms. |
| C-2 | opencode defaults to **allow everything** including `external_directory`. | Keel defaults are stricter (W3.6). Intentional; list under "Deliberate differences" in `PLAN-INDEX.json`. |
| C-3 | opencode command `!`cmd`` runs **outside** the permission flow; MCP session id is sent to remote servers. | Keel does neither (W5.4, W4.13). Intentional. |
| C-4 | openman: "watch-only" is client-side only; orgo-teammates enforces on the server. | Server-side (Y2.14, W7.19). |
| C-5 | nicks-stack persona tells the agent to avoid ethics/propriety disclaimers and be aggressive. | Adopt rigor and anti-sycophancy only (W6.3). Do not adopt removal of safety behavior. |
| C-6 | Addendum 4 Section 1 said the opencode `agents`, `permissions`, `mcp-servers`, `commands` docs were unread. | Now read; remove them from the M0 list. |
| C-7 | opencode MCP `pool` and `protocol` fields refer to a **2026-07-28 MCP revision**. | Treat as `[T]` for opencode only; verify against the official MCP spec in M0 before implementing. |

## 7. Builder protocol for `[S]` items (ideas with no repo reference)

For every `V` row (and any other `[S]` row in any addendum), record all of these in `PLAN-INDEX.json` before marking complete:

1. **Why:** one paragraph with the user problem; name 2+ similar products or standards **by category** (no copying).
2. **Free check:** each library/model/service, license, date verified; reject anything paid, account-gated, or non-commercial-only.
3. **Spec in Keel's words:** behavior, edge cases, failure modes, permissions touched, data stored, Tier-2 interactions.
4. **Smallest slice behind an `experimental` flag**, off by default if it touches network, personal data or permissions.
5. **Negative tests first** for anything security-relevant (what must be refused), then positive tests.
6. **End-to-end evidence run id**, plus an offline run (X0.8).
7. **Owner review** before enabling by default if it stores new personal data, makes a network call, or changes approval behavior.

## 8. Own suggestions `[S]` (no repo reference; follow Section 7)

| ID | Feature | Builder approach | M | Pri |
| --- | --- | --- | --- | --- |
| V1 | **Plugin scope tree (lifecycle-safe plugins):** every plugin runs in a scope that records what it registered (tools, hooks, routes, UI panels, timers, subprocesses); unload/reload disposes **all** of it automatically; child scopes inherit parent permissions only down, never up. | Python context manager tree; registration functions return disposables attached to the active scope; test by loading/unloading a plugin 100 times and asserting zero leaked handlers/processes. Underpins W1.1, hot reload (Y1.31) and safe mode. | M10 | P0 |
| V2 | **Policy simulator with "winning rule" trace:** shows ordered rules, which matched, which won, why a multi-resource op was denied, and the Tier-2 verdict. | Reuse the matcher; output a JSON trace rendered in the UI and `keel policy test`. Required by C-1. | M3, M19 | P0 |
| V3 | **Broadness scoring for saved "always" approvals:** flag patterns like bare `*` or `rm *`, show last-used date, offer narrowing (e.g., command prefix to exact subcommand). | Score = wildcard coverage vs action risk table; surfaced in permission review screen (X5.7). | M3, M19 | P1 |
| V4 | **Reject-cascade UX:** a "Reject all pending" button plus a per-request reject, mirroring W3.9; rejected reasons passed to the model as no-retry instruction. | UI + Y2.7 behavior. | M19, M3 | P1 |
| V5 | **Strictness presets as rule sets:** Cautious / Balanced / Trusted compiled into ordered rule arrays, diffable and exportable, never able to touch Tier 2. | Ship three JSONC files; wizard (Master 9.3) selects one; policy simulator compares them. | M3, M19 | P0 |
| V6 | **Opaque per-server correlation IDs for MCP** (instead of session ids): random value per (session, server), rotated per session, never reused across servers. | Generate on connect; store in memory only; send in `_meta` only if the server advertises support. | M6 | P1 |
| V7 | **Sycophancy/capitulation eval:** scripted multi-turn tests where a fixture "user" pushes back without new evidence; pass = model keeps correct answer; plus a "new evidence" case where it should change. | Add to the local eval harness (M21); score per model; display in model picker next to tool reliability. | M21, M7 | P1 |
| V8 | **External specialist adapters:** Keel can delegate a task to a **coding CLI the user already has installed** (any tool with a headless mode) as a child agent, with "one writer per working tree" locking and mandatory diff/test verification after. | Generic adapter spec: command template, stdin/stdout contract, timeout, allowed paths, output parser; adapters ship **disabled**; never bundle third-party CLIs; respect each tool's terms; run inside Keel worktree + permission gate. | M12 | P1 |
| V9 | **Remote-initiated action confirmation:** any task started from a channel (Telegram/email/webhook) that would run shell/edit/send actions requires a **one-time code confirmation in the desktop app** (or a pre-approved rule), per W7.17. | Pending-turn state (Y2.6) with a "needs local confirmation" status and a notification (X8.5). | M15, M3 | P0 |
| V10 | **Duplicate-code and dead-feature detector for the builder:** CI reports duplicate blocks (W1.7) and any plan ID with code but no test/evidence. | Combine jscpd-style tool + `PLAN-INDEX.json` check script. | M0, M25 | P1 |
| V11 | **Per-agent "tool surface report":** shows exactly which tools, MCP servers, skills and subagents an agent can reach after merges, with the rule that allowed each. | Computed from the merged config + permission matcher; diff view when an extension update changes it (extends C8.5). | M7, M10 | P1 |
| V12 | **Config "doctor" for rule conflicts:** detects rules that can never match (shadowed by a later rule), duplicate rules, and broad allows after specific denies. | Static analysis over ordered rules; run on save and in `keel doctor`. | M3, M21 | P1 |
| V13 | **Release provenance page in-app** listing for the running build: version, commit-less build id, signing key fingerprint, manifest hash, SBOM link. | Reads embedded manifest; ties to C11.6. | M22, M19 | P1 |
| V14 | **Prompt-assembly viewer for subagents/commands** (what system prompt, instructions, skills and MCP instruction blocks a child actually received), with taint labels. | Extends the Context inspector; store assembled prompt hash per run. | M7, M21 | P1 |
| V15 | **Local "plugin conformance kit":** a checklist-runner that verifies a plugin cleans up on unload, respects permission denials, declares all network hosts, and survives safe-mode boot. | Uses V1 + the mock host (X6.1); required before a plugin is marked "verified" in the private index. | M10 | P1 |

## 9. UI/UX additions from this pass (use Keel tokens only)

| ID | Screen/component | Source | M |
| --- | --- | --- | --- |
| W9.1 | **MCP panel** (`/mcps`): per-server state (connected / needs authentication / disabled / error), connect, disconnect, authenticate, paste-callback-URL dialog, timeout and protocol fields. | T:OC-MCP | M19 |
| W9.2 | **Approval card with three actions** (Once / Always with the **proposed saved pattern shown and editable** / Reject with optional feedback) and a banner when rejecting cancels other pending requests. | T:OC-PERM | M19 |
| W9.3 | **Agent picker and agent editor** (mode, model with variant, step limit, color, hidden, permission list with simulator, launchable-subagent allowlist). | T:OC-AGENTS | M19 |
| W9.4 | **Command palette entries generated from commands**, with argument hints (`$1`, `$ARGUMENTS`) and a preview of the expanded prompt before submit. | T:OC-CMD | M19 |
| W9.5 | **First-run Safety notice** screen and **Known limits** page. | T:DS, T:OM-SEC | M19 |
| W9.6 | Web UI served on loopback with **SSH hint banner** showing the forwarded URL instructions. | T:DS | M20 |

## 10. Priority order for this addendum

1. **Resolve conflicts first:** C-1 to C-7; add to `DECISIONS.md`.
2. **Permission engine parity and stricter defaults:** W3.1 to W3.10, W3.13, V2, V5, V12.
3. **Plugin core:** W1.1, V1, W2.1, W2.2, W2.6, W4.2, W4.9.
4. **Security hardening for `keel web`/API:** W7.3 to W7.14, W7.17.
5. **Quality gates:** W1.5, W1.7, V10.
6. Everything else with its milestone; P2 after the v1.0 candidate is green. Every row is added to `PLAN-INDEX.json` with its source tag; no `[T]` row may be built from copied code and no `[S]` row skips Section 7.


---

# Appendix A6 — Addendum: DeepSeek Harness Full Teardown (preserved)

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


---

# Appendix A7 — Addendum: DeepSeek Deep Reads (preserved)

# Keel Plan v5 Addendum 7: DeepSeek Harness Deep Reads (Tools Pipeline, Subagents, Testing, Desktop Packaging, Providers UX, Seam Map)

Adds only items **not already in** Master Plan and Addenda 1 to 6. Free-only. Milestones follow v5. IDs: `E*` = derived from a source read this session, `V*` = my own ideas (protocol in Section 9). Every row names its source.

## 0. Source keys and ground rules

| Tag | Meaning |
| --- | --- |
| `[T:key]` | Read this session (21 Nov 2026). Reimplement clean-room in Python; never copy code, names, icons, prompts or text (X0.10). |
| `[S]` | My suggestion; follow Section 9. |

Keys (all in `github.com/deepseek-ai/deepseek-harness`, MIT): **DS-TOOLS** `docs/subsystems/tools.md` · **DS-COOK** `docs/cookbook/adding-a-tool.md` · **DS-SUB** `docs/subsystems/subagent.md` · **DS-TEST** `docs/testing.md` · **DS-DESK** `apps/desktop/README.md` · **DS-PROV** `docs/user/guide/providers.md` · **DS-SEAMS** `docs/capability-seams.md` · **DS-DEF** `docs/defensive-patterns/README.md`. Earlier keys (DS-ARCH, DS-AGENTS, DS-DEV, DS-SAFETY, DS-GUIDE, DS-BENCH) are as in Addendum 6.

dsh is TypeScript on a framework called Cordis. Keel stays Python + Electron. Only behavior and design rules are taken.

## 1. Read status

**Read in full this pass:** the eight files above.
**Not read yet (M0 list):** `docs/cordis-primer.md`, other `docs/subsystems/*` (session, scope, core, llm-streaming, system-prompt, conversation, working-directory, agent-team, shell, jobs), `docs/cookbook/*` (adding a package, LLM adapter, settings card, session format version), `docs/defensive-patterns/*` subpages (package-surface, remote-and-api, client-components, conversation-and-session, general), `docs/postmortem/0001-*`, `docs/config-catalog.md`, `docs/session-format-status.md`, `docs/user/develop/basic/*`, `apps/cli/README.md`, `apps/web/tests/*`, `apps/desktop/packaging/README.md`, `benchmarks/AGENTS.md`, `snapshots/AGENTS.md`, `vendor/README.md`, per-package READMEs (especially `packages/core/agent-loop`, `tools`, `jobs`, `spill`, `compaction`, `sandbox`, `skill`), `.agents/skills/*` (code-review, error-handling, ci-test-reliability, client-ui-ux, session-projection), and `.agents/notes/implemented/*`. The GitHub `packages/` and `apps/` directory pages remain robots-blocked.

## 2. Tool pipeline contract (DS-TOOLS, DS-COOK)

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| E1.1 | **Every tool declares a mandatory canonical output** (JSON schema), returns one lossless JSON value, and a **pure `render(args, value)`** produces the model-facing content. Callers never parse prose for ids. | T:DS-TOOLS, DS-COOK | `Tool` = name, description, params schema, `output_schema`, `execute()`, `render()`. Body returns data only; renderer builds text. Gate: tool without output schema fails registration. | M5 | P0 |
| E1.2 | **Model-facing schema built by explicit allowlist** (name, description, parameters only); execution, timeout, presenters, concurrency flags never leak into a request. | T:DS-TOOLS | `schemas()` projects allowlisted fields; test that no callback/field leaks. | M5 | P0 |
| E1.3 | **One schema vocabulary for params and outputs** (scalars, arrays, objects with explicit `additionalProperties`, exact-one `oneOf`, enum/const), with inferred types; mismatch → `INVALID_ARGS`; invalid output → `INVALID_TOOL_OUTPUT`. **Unsupported JSON Schema keywords are rejected, never silently ignored.** | T:DS-TOOLS | pydantic or a small schema compiler; reject unknown keywords at registration; same errors. | M5, M6 | P0 |
| E1.4 | **Args are deep-frozen and snapshotted as lossless JSON before policy runs;** args cannot be rewritten later because history, audit, UI and execution must agree. | T:DS-TOOLS | Immutable arg object; policy hooks return decisions, never modified args. | M5, M3 | P0 |
| E1.5 | **Pre-execute decisions:** `allow`, `deny` (reason + optional structured error id), `cancel`, `ask` (audited reason + optional localized display reason); only `allowed-once` proceeds; missing approval channel or agentless call = denial. | T:DS-TOOLS | Decision type in the permission gate (extends W3.x); display reason localized (M25). | M3 | P0 |
| E1.6 | **Guards are monotonic:** a final guard can only deny, never allow, so listener order cannot turn a denial into permission. | T:DS-TOOLS | `guard()` registry evaluated after all hooks; Tier 2 is implemented as guards. | M3 | P0 |
| E1.7 | **Post-execute decisions:** accept, replace *content* or replace *value* (never both), attach context for the next request, or block with corrective feedback. **Content replacement is presentation, not confidentiality;** confidentiality needs block/replace-value. | T:DS-TOOLS | Post hook API with the same rules; DLP (B3.8) uses block/replace-value. | M3, M5 | P0 |
| E1.8 | **Around-dispatch wrapper** for timeout/retry/metrics may replace but not remove the cancellation signal; the registry re-fuses the caller's signal. | T:DS-TOOLS | `with_signal` wrapper pattern; test that caller cancel always propagates. | M5 | P0 |
| E1.9 | **Cooperative per-tool timeout** (`timeoutMs`): declaring it asserts the tool forwards the cancel signal and reaches quiescence; never sent to the model; result error code `TOOL_TIMEOUT`. | T:DS-TOOLS | Tool metadata `timeout_s`; enforcement plugin; conformance test (V24). | M5 | P0 |
| E1.10 | **Concurrency classifier `isConcurrencySafe(args)`:** pure, only `true` opts in; anything else (omission, exception, invalid) is exclusive; loop forms **exclusive barriers and rolling-pool parallel runs**; batch override `maxParallelToolCalls`. | T:DS-TOOLS | Scheduler with barriers and a bounded pool; default exclusive. | M5 | P0 |
| E1.11 | **Executor contract:** one outcome per input call in input order (skipped calls on abort included); never settles while started work still runs; internal failure drains then rejects with a typed batch error preserving committed outcomes. | T:DS-TOOLS | `ToolBatchExecutionError`; test with injected failures. | M5 | P0 |
| E1.12 | **Per-scope tool restriction** (`allow` / `deny` lists) that **intersect**; scoped registrations stay exempt; deny-only admits later tools, allow-list excludes them. | T:DS-TOOLS | Agent frontmatter `tools.allow/deny` semantics exactly so (extends A1.12). | M7 | P0 |
| E1.13 | **Conditional tool activation (`when`)** evaluated **once per step** with the captured model selection; the resulting admitted set governs declarations *and* every call in that step; disposed after the batch; late results cannot restore removed tools. | T:DS-TOOLS | Per-step tool admission (e.g., vision tool only when the model supports images). | M5, M7 | P1 |
| E1.14 | **Stable error vocabulary:** `INVALID_ARGS`, `INVALID_TOOL_OUTPUT`, `UNKNOWN_TOOL`, `ABORTED`, `ABORTED_BEFORE_DISPATCH`, `TOOL_TIMEOUT`, `APPROVAL_REJECTED/CANCELLED/UNAVAILABLE`, `TOOL_CONTEXT_UNAVAILABLE`; error info = name + code + optional raw reason that is **kept durably but never in model-facing content**. | T:DS-TOOLS | Error catalog (C10.2) with these codes; reason stored in log only. | M5, M23 | P0 |
| E1.15 | **Expected failures are typed errors with stable codes;** successful domain outcomes (e.g., non-zero exit) are values, not exceptions. | T:DS-COOK | Rule in tool authoring guide; tests per tool. | M5 | P1 |
| E1.16 | **`conclude_turn()` marker** lets a successful tool end the turn; composites forward it only from authoritative nested success. **`defer_context()`** attaches context to a result that the loop appends only after the result. | T:DS-TOOLS | Both on the tool run context. | M5, M7 | P1 |
| E1.17 | **`agent.inject()` messages carry a typed source kind;** old untyped wrappers rejected at admission. | T:DS-COOK | Source enum for injected context (supports taint). | M7 | P1 |
| E1.18 | **Long-running work:** background start returns a typed handle (`{kind:'background', job_id}`); job spec has synchronous cancel, non-rejecting `done` that settles after cleanup, and output source; **after publishing the id, use a task-owned cancel signal, not the call's;** cancellation of the call stops waiting but does not kill published work; `job_kill`/owner disposal/teardown own that lifetime. | T:DS-COOK | Matches Y1.7 + D3.7; make this the written lifecycle rule. | M5, M14 | P0 |
| E1.19 | **Programmatic tool-call (PTC) mode:** every visible tool callable as `await tools.name(args)`; generated arg/output type maps; calls **re-enter the normal pipeline**; success returns the canonical value after policy; failure rejects with a limited error (name, tool name, message only). Intermediate values are execution-local, not persisted; **only the outer `run_code` call crosses the output cap and spill pipeline;** model-direct calls to native names are denied while PTC executor is selected; `run_code` is a reserved name. | T:DS-COOK, DS-TOOLS | Keel's Code Mode (Y1.1) follows these rules; design `output_schema` as a useful programmatic API. | M5, M6 | P1 |
| E1.20 | **`ptc-dispatch-log` hook** lets spill policy shorten only the durable log copy of a sub-call result (program already got the full value). Sub-call start/settle events store only ids, name, normalized args. | T:DS-TOOLS | Log-copy hook; never persist schemas/descriptions per sub-call. | M5, M4 | P2 |
| E1.21 | **Executor-owned prompt sections:** guidance registered and disposed with the executor. | T:DS-TOOLS | Tool/executor can add prompt sections (also the MCP instruction blocks, W4.11). | M7 | P1 |

## 3. Tool UI presentation (cards) (DS-TOOLS, DS-COOK)

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| E2.1 | **Presenters are pure** (`present_call(args)`, `present_result(args, result)`), run on live stream **and** log replay, no I/O/clock/session state; malformed or old args fall back to a generic card and **display must never crash a replay**. | T:DS-COOK | Presenter contract + replay fuzz test. | M5, M19 | P0 |
| E2.2 | **Card kinds:** `generic` (title, icon kind: read/edit/delete/move/search/execute/fetch/other, file locations), `terminal` (command; result adds raw output, exit code, signal), `diff` (path, old text or null for new file, new text), `search` (matches grouped by file or flat paths, with `truncated`/`total` so partial results are never shown as complete), `read` (path, 1-based offset, numbered lines, total lines, language hint), `web` (search sources/answer/truncated; fetch url/status/truncated). Completed view replaces pending; search/read/web have no call-time card. | T:DS-TOOLS, DS-COOK | Renderer card components (Master 9.2); one component per kind with states. | M19 | P0 |
| E2.3 | **Durable presentation metadata** (`presentation_meta(args, value)`) stored on the result so replay shows hunks/search facts without persisting the canonical value; skipped for nested code-mode calls. | T:DS-COOK | `meta` field on tool result events. | M4, M5 | P0 |
| E2.4 | **UI-only formatting stays out of model-visible output** (fenced console blocks, relativized paths, diffs). | T:DS-COOK | Rule + review checklist. | M5 | P1 |
| E2.5 | **Web client derives tool cards from raw events** via a keyed slot per tool name, validates wire values locally and falls back to the generic row; no separate presenter registry; no host code imported into the browser bundle. | T:DS-COOK | Renderer `tool_view` registry keyed by tool name; Python presenters only for CLI/TUI. | M19, M20 | P1 |

## 4. Subagents (DS-SUB)

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| E3.1 | **One activation API for local children and external executions;** provider capability flags (`agent_options`, `agent_preset`, `output_schema`, `depth_limit`) validate start options before anything starts. | T:DS-SUB | `SubagentProvider.capabilities`; reject unsupported options with a clear error. | M12 | P0 |
| E3.2 | **Result delivery policy:** `parent` (notifies the model) vs `caller` (only returns result, e.g., workflows/code mode). | T:DS-SUB | Delivery enum on start. | M12, M8 | P1 |
| E3.3 | **Agent names:** 1 to 32 lowercase letters/digits/hyphens starting with a letter, not `lead`; default `agent-N`; root is `lead`; full names are slash paths; **names are model-facing references, session ids are the authority;** resolve returns the id and grants no permission; a slash path with no match fails `AGENT_NAME_NOT_FOUND`. | T:DS-SUB | Name rules + `resolve_name()`; authorization separate. | M12 | P0 |
| E3.4 | **Child working directory** chosen at admission (relative resolves against the parent's current dir); local child keeps the parent's original project; resumed child retains logged directory state. | T:DS-SUB | `cwd` field on start; log it. | M12, M5 | P1 |
| E3.5 | **Local child = durable session with at most one live activation;** manager owns identity/capacity reservation, input admission, cold resume, child-first disposal; structured-output capture closes input for that activation; resume does not inherit the schema. | T:DS-SUB | Child manager with these invariants + tests. | M12 | P0 |
| E3.6 | **Spawn vs Fork:** fork seeds the child with the parent's **completed-turn prefix** (contiguous, lossless, balanced steps), spawn starts fresh; `inherits_parent_context` is descriptive for wording only. | T:DS-SUB | Two local providers; fork cut = prefix length. | M12 | P1 |
| E3.7 | **External backends as providers** (separate coding CLIs or protocol agents): one execution, no follow-ups, results to creator only while online. | T:DS-SUB | Basis for V8 adapters; same activation lifecycle. | M12 | P1 |
| E3.8 | **Result object:** final output = last non-empty assistant message; optional structured value validated against the requested schema; `diagnostic` text limited to 4,096 bytes and **free of tool inputs, file contents, env values, credentials, raw protocol payloads**; stop reason enum (completed, aborted, error, max-tokens, refusal). Child failure resolves with `error`, not an exception. | T:DS-SUB | Result dataclass + diagnostic sanitizer test. | M12 | P0 |
| E3.9 | **Messaging within one tree:** running target gets *steer*, absent target cold-resumes, sender identity rechecked, accepted messages never retracted. **Two distinct message source kinds:** `agent-message` (relay: words the sender chose) vs `subagent-settled` (runtime notice about how a child ended) so a child is never credited with words it didn't write. | T:DS-SUB | Source kinds in the log + UI labels. | M12, M4 | P0 |
| E3.10 | **Interrupt authority:** only the user or an exact live ancestor; fire-and-return; preserves unclaimed inbox, the activation and descendants; claimed work not requeued; absent target is a no-op. | T:DS-SUB | `interrupt()` semantics + tests. | M12, M3 | P0 |
| E3.11 | **Whole-tree drain** and **wait-for-tree-work** (idle members with parked input stay resident without delaying host completion). | T:DS-SUB | Shutdown/idle logic for fleets. | M12 | P1 |
| E3.12 | **Parent-owned subagent catalog projection** (membership at creation, no execution status); recursive `list_descendants` with parent id, depth, path and **per-branch diagnostics** (`unsupported`, `corrupt`, `unavailable`); cycles/repeats skipped; unreadable branch stops only that branch; historical children with unavailable descriptors listed as `unknown` mode with no continuation rights. | T:DS-SUB | Catalog projection + tree viewer; no loading of child logs to list. | M12, M19 | P1 |
| E3.13 | **Subagent model-route setting:** default-off allowlist of provider/model routes the agent may choose for children; reads live on each delegation; malformed/duplicate routes error. | T:DS-SUB | Setting `subagent_model_routes`; applies to all sessions. | M12, M2 | P1 |
| E3.14 | **User-authored message to a child** from the UI with attachments (image parts admitted via attachment store; model must accept images) and client time zone; cold resume at capacity rejects with a typed `delivery-unavailable`. | T:DS-SUB | "Message this agent" box in Fleet view. | M12, M19 | P1 |
| E3.15 | Lifecycle events `subagent/start`, `subagent/end` (scoped to tree root), provider added/removed. | T:DS-SUB | Event kinds in the bus. | M8, M12 | P1 |

## 5. Testing policy (DS-TEST)

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| E4.1 | **HMR-safety test for every registry:** dispose the contributing scope, assert cleanup. | T:DS-TEST | Per-registry unload test (V1/D1.2). | M10, M25 | P0 |
| E4.2 | **Permanent contract-regression specs** for the agent loop. | T:DS-TEST | `tests/contract_regressions/` never deleted without owner note. | M25 | P0 |
| E4.3 | **Coverage gate philosophy:** an uncovered line is often dead code to delete; line coverage is necessary, never sufficient; environment-dependent files exempted locally but enforced on CI that has the tool. | T:DS-TEST | Applies to D7.13; PowerShell executor coverage only on runners with pwsh. | M25 | P1 |
| E4.4 | **Performance benchmark gates** as required PR checks: timed code runs on the plain runtime (never a transpiler); synthetic inputs enforce **time, heap and scaling budgets**; package-local perf files are diagnostic only. | T:DS-TEST | `benchmarks/` with budgets (session open time, memory growth, scaling with event count). | M21, M25 | P0 |
| E4.5 | **Snapshot scenarios:** parent/child session files with version in filename that must agree with header; `snapshot.yml` declares profile, header class, recording policy, workspace facts; typed tokens keep parent/child identity relations; **mutating scenarios compare a full `workspace.expected/` tree that record/refresh never rewrite;** modes `record` (needs key), `refresh` (replay input still valid), review every diff; CI read-only replay. | T:DS-TEST | Keel snapshot harness (X9.2) with these rules. | M25 | P0 |
| E4.6 | **Fixtures omit sequence/time envelopes** (replay synthesizes them); historical fixtures keep released representation with explicit format owners for migration coverage. | T:DS-TEST | Fixture format rules for session export versions. | M25 | P1 |
| E4.7 | **Browser snapshot lane:** UI output compared in Chromium, with the model picker also in WebKit; replay-only in CI. | T:DS-TEST | Playwright visual lane (X8.1) incl. a second engine for key widgets (note: Electron is Chromium; WebKit only for `keel web`). | M25 | P1 |
| E4.8 | **Test-process isolation rules:** forked workers share ports, paths, namespaces and children; **each test owns every resource it acquires through teardown;** a spec that passes only alone is a test defect; fork-exit diagnostics report PID, file, code, signal; flake-diagnosis workflow classifies probabilistic failures. | T:DS-TEST | `tests/conftest.py` fixtures for ports/tmp dirs; xdist-style parallel run; flake report. | M25 | P0 |
| E4.9 | **Smoke tests boot the shipped profile, send one prompt, and check the world** (catches "green unit tests, broken product"); postmortems are documented (`postmortem/0001-*`). | T:DS-TEST | Release smoke (C13.4) + `docs/postmortem/` folder for every escaped bug. | M25, M22 | P0 |
| E4.10 | **Mock only the expensive/non-deterministic boundary** (model, network, clock); keep the real tool registry, pipeline and persistence behind the scripted mock; recovery tests separate pre-chunk vs post-chunk failures and prove failed chunks derive no message or tool side effect; cover exhaustion, cancellation, policy composition, persistence, status, wire counts, transport-closing idle timeouts, and shipping loader composition. | T:DS-TEST | Test harness `make_bridge_harness()` analog on the fixture model server (X9.1). | M25 | P0 |
| E4.11 | **Verify the world, not the agent's self-report:** re-run the command or re-read files externally; assert untouched files are byte-identical; e2e tests create and dispose their own resources even on failure; shared fixtures live in plain helper modules, never in another test file. | T:DS-TEST | Eval/e2e rules for Keel's SWE-task benchmark (C13.1). | M21, M25 | P0 |
| E4.12 | **Real-composition tests for product-visible plugins:** boot a test-only config through the real loader, mock only external services, assert model-visible request/log, durable state or user-visible output; **prove each guard fails when the regression is introduced** (red-green-revert). | T:DS-TEST | Plugin test kit (V15) requires one composition test per plugin. | M10, M25 | P0 |
| E4.13 | **Test the published artifact entry path:** run built entrypoints under the plain runtime; assert a genuinely missing config exits non-zero; singleton modules shared across bundles get a built-scope test. | T:DS-TEST | Built-wheel / PyInstaller smoke; non-zero exit test. | M22, M25 | P0 |
| E4.14 | **Test resolution:** tests resolve imports to source; built artifacts used only by explicit built-mode tests; subprocess tests run built output through one shared launcher. | T:DS-TEST | Source vs built test marks (D6.10). | M25 | P1 |
| E4.15 | **Every non-trivial model/protocol/human-visible change updates a keyless recorded-session scenario;** new capability seams and lifecycle variants name every required test tier at plan time. | T:DS-TEST | Plan-time "test tiers" field in `PLAN-INDEX.json`. | M0, M25 | P0 |

## 6. Desktop shell, packaging and updates (DS-DESK)

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| E5.1 | **No listening port in the desktop app:** the backend runs as a bundled child; **framed byte pipes carry requests and streaming responses with backpressure**, Node IPC carries only lifecycle control, a custom `app://` protocol serves client assets. | T:DS-DESK | Option for Electron: talk to the Python daemon over a **Unix domain socket / Windows named pipe** (or stdio frames) with a custom protocol for assets, removing loopback TCP exposure entirely; `keel web`/CLI keep loopback + token. Decision C-19. | M19, M20 | P0 |
| E5.2 | **Release identity:** shell and backend always carry the **same exact version**; a backend upgrade is a desktop release; no independent versions. | T:DS-DESK | Single version for Electron + daemon; updater never updates one side alone. | M22 | P0 |
| E5.3 | **Bundled runtime, never system runtime or package-manager state** (and never the shell's own runtime for the backend). | T:DS-DESK | Keel ships its own Python (embedded) and never reads system Python site-packages. | M22 | P0 |
| E5.4 | **Process-lifetime single-instance lock acquired before any profile access;** the desktop app **exclusively owns its profile directory;** CLI and desktop share product data (sessions, settings, credentials, workspaces) but **never executable packages, plugin activation, lockfiles or `site-packages`.** | T:DS-DESK | Single-instance lock + two plugin environments (desktop vs CLI). | M19, M22 | P0 |
| E5.5 | **Transactional activation:** install in staging → boot a full backend health check → replace the active profile only after success; **journal + one rollback profile;** recovery combines the journal with the actual directories; a transaction lock records the current owner (including an orphaned worker) so a live worker isn't treated as stale. | T:DS-DESK | Used for app upgrades and plugin installs (extends D1.11, Master 0.4 rollback). | M10, M22 | P0 |
| E5.6 | **Seed store packaging:** offline seed archive of dependencies in **16 deterministic uncompressed shards** so the outer installer compresses them and differential updates reuse unchanged shards; verified by an offline install before shipping; seed extraction on first run (measure disk use separately from installer download size). | T:DS-DESK | Wheelhouse seed for plugins/models-free deps; shard + hash inventory; measure both sizes (B7.4). | M22 | P1 |
| E5.7 | **Update unit:** shell + matching backend seed + runtime form **one signed update unit;** update check **10 seconds after the main window opens** plus a manual "Check for updates…" menu item; native confirmation dialog; waits for an in-flight check; verifies, stops backend, installs; next launch reconciles. | T:DS-DESK | Updater flow (Y1.21): delay, menu item, confirm, verify with Ed25519 manifest (free) instead of paid OS signing. | M22, M19 | P0 |
| E5.8 | **Plugin management window is a separate renderer** receiving only structured list/install/remove/update operations: **no filesystem, raw IPC, shell, or arbitrary package-manager arguments.** | T:DS-DESK | Extensions window with a narrow typed IPC surface (Master 11 Electron hardening). | M10, M19 | P0 |
| E5.9 | **Plugins with install-time lifecycle scripts are rejected** unless in a reviewed allowlist. | T:DS-DESK | Python: refuse sdist builds/post-install hooks unless allowlisted; prefer wheels only. | M10 | P0 |
| E5.10 | **Shell copy localized from app locale** (menus, native dialogs, plugin window share one locale payload; falls back to English); i18n gate also checks desktop shell sources. | T:DS-DESK | Main-process string catalog (X8/W… D4.8). | M19, M25 | P1 |
| E5.11 | **Isolated development home** (data, project and browser data under a disposable folder); debug ports configurable by env; DevTools auto-open toggle; **dev overrides ignored by the packaged app.** | T:DS-DESK | `keel dev:desktop` with disposable home; env overrides only in dev builds. | M19, M25 | P1 |
| E5.12 | **Per-target build isolation:** each target owns its inputs, prepared runtime, seed and artifacts under `targets/<target>/`; shared download cache verified by name+hash; a target never consumes another's mutable state. | T:DS-DESK | Release build dirs per OS/arch. | M22 | P0 |
| E5.13 | **Release prerequisite env validation** (app id format; reject malformed identity values; incomplete credential sets). | T:DS-DESK | `release --dry-run` validates all release inputs before building. | M22 | P1 |
| E5.14 | **Packaging never receives upload credentials** (stripped from subprocesses); a **target completion record** is written only after every build/sign step succeeds. | T:DS-DESK | Release job separation: build job has no deploy secrets; completion record. | M22 | P0 |
| E5.15 | **Upload guard:** uploader requires the completion record to match environment, target, public URL and version, and checks artifact names, sizes, SHA-512 **before it reads credentials**; uploads **immutable versioned artifacts first, channel metadata last with no-cache;** never deletes historical objects. Stable vs prerelease channel files. | T:DS-DESK | Keel `release publish`: same order and checks against `keel-releases` (D5); manifest last; keep old versions for rollback. | M22 | P0 |
| E5.16 | **Test vs production update environments** with distinct origins. | T:DS-DESK | `beta` feed origin vs stable (B4.14). | M22 | P1 |
| E5.17 | **Signing/notarization steps:** hardened runtime + timestamp on every embedded executable; deep strict signature check rejecting unexpected authorities; DMG notarized and stapled by an artifact hook; Windows hardware-token EV signing with PIN never persisted and diagnostics redacted. | T:DS-DESK | **Excluded as paid** (D3 in Master). Keep the *verification script pattern* ready for the day a certificate exists; for now Ed25519 + checksums. | M22 | P2 |
| E5.18 | **Linux is not a supported desktop release target** in dsh; Keel supports it (AppImage/DEB/RPM). | T:DS-DESK | Keel keeps Linux (owner requirement); note effort. | M22 | n/a |
| E5.19 | **Known-limitations section** in the desktop README (features disabled in desktop because they need a server; shared vs separate state; release qualification needs production environment). | T:DS-DESK | Same section in Keel's About > Known limits. | M26 | P1 |

## 7. Providers, credentials and model UX (DS-PROV)

| ID | Feature | Source | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- | --- |
| E6.1 | **Keys are write-only:** the UI receives a redacted descriptor, never the secret; settings store only a **credential reference**; **masked preview rule** (identifier prefix, 5 leading and 4 trailing characters only when at least 8 middle characters remain hidden, else all dots; Unicode code points). | T:DS-PROV | Same behavior in the provider form. | M3, M19 | P0 |
| E6.2 | **Saved key edit rules:** no reveal/copy/partial edit; typing replaces the whole key; Backspace/Delete **stages whole-key removal**, applied only on Apply; Cancel preserves; if deletion succeeds but settings fail, show a warning that deletion cannot be undone and offer retry; clearing a shared credential warns that it affects every feature using the reference. | T:DS-PROV | Same UX rules + tests. | M19 | P1 |
| E6.3 | **Environment-credential hints:** green = env var detected, yellow = none detected, "unconfirmed" = status read failed; detection never validates the credential; provider-managed credential files are outside the check. | T:DS-PROV | Hint component; "Test connection" separate (Master 9.3). | M19 | P1 |
| E6.4 | **Model list follows the provider's published list** (loads on first need, refreshes in the background about every 10 minutes while in use, falls back to built-in); editing the list switches to a pinned custom list; "Restore defaults" re-follows. | T:DS-PROV | Offline catalog default + optional live refresh for providers the user configured (never required). | M2 | P1 |
| E6.5 | **Third-party provider picker from an installed catalog** (endpoint, protocol, models) vs **Custom model API** form: permanent lowercase provider ID, base URL, protocol, credential, models; **four protocols** (OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, Gemini API); one protocol per provider (a gateway that serves two needs two providers); renaming = add new + delete old. | T:DS-PROV | Provider form (Master 9.3) with protocol selector and ID immutability. | M2, M19 | P0 |
| E6.6 | **Model discovery:** `GET /models` with a **searchable picker** (existing models pre-ticked; tick to add, untick to remove; "Update list"); configured models the endpoint doesn't list stay; nothing saved until Save; failures fall back to manual entry; built-in provider always answered from the catalog. | T:DS-PROV | Discovery dialog + tolerant parser (two list formats) with clear failure messages. | M2, M19 | P1 |
| E6.7 | **Model picker behavior:** selecting also sets the default for new sessions; **a session keeps the model recorded in its own log;** drag-to-reorder with keyboard up/down alternative; deleted default provider → composer shows "Select model" and blocks input. | T:DS-PROV | Same rules; a11y for reordering. | M19 | P0 |
| E6.8 | **Per-model capability fields:** input types (`text`, `image`), context window, max output tokens; route-level `defaultInput` fallback (never removes images the catalog knows), per-model override; **"claims about your endpoint are not verified"** warning; image-capable list clears image limits when image is removed. | T:DS-PROV | Capability editor + image-refusal-before-send behavior with clear message. | M2, M19 | P0 |
| E6.9 | **Reasoning-effort declarations per model:** levels with the API value sent for each (`off` may be empty = send nothing), route default, picker choice saved with model as default; thinking-format switch for models that think unless told not to; models can drop levels; unsupported effort refused as `UNSUPPORTED_REASONING_EFFORT`; Effort menu hidden when no levels declared. | T:DS-PROV | Effort UI + config; local reasoning models integrate with X1.3. | M2, M19 | P0 |
| E6.10 | **Request-compatibility switches** (`supports_developer_role`, `max_tokens_field`, `thinking_format`, ...) at route level with per-model field-by-field override; **empty value refused, unknown name refused with the list of valid names;** each switch valid only for protocols that declare it. | T:DS-PROV | Compat profile object in provider config + validation messages. | M2 | P0 |
| E6.11 | **Troubleshooting keyed by error code/symptom** (missing credential, unknown model, 401 on discovery, gateway refuses every request, only reasoning models fail, Effort menu absent, `off` doesn't stop thinking, image refused vs provider rejects image, stale image stays in session log until a new session). | T:DS-PROV | In-app troubleshooting page generated from the error catalog (C10.2). | M23 | P1 |
| E6.12 | **"Open configuration file" button** next to settings for advanced fields, adapters re-read config on the next request (no restart). | T:DS-PROV | Hot re-read per request; button opens the config in `$EDITOR` (only when UI runs on the same machine). | M2, M19 | P1 |
| E6.13 | **Client-upgrade-required error** naming the version to install when a model needs a newer app. | T:DS-PROV | Typed error + update prompt. | M2, M22 | P2 |
| E6.14 | **Config generated reference** (`config-catalog.md`) derived from source so it can't drift; links from the UI to field docs. | T:DS-PROV | Generated config reference (A2.7) linked from forms. | M23 | P1 |

## 8. Seam map: services DeepSeek has that Keel's plan lacks (DS-SEAMS)

Each row = a capability the reference exposes; rows already covered earlier are omitted.

| ID | Service/capability | Keel implementation | M | Pri |
| --- | --- | --- | --- | --- |
| E7.1 | **`tokenMeter`:** isolated per-session replay folds; pressure consumers share immutable revisioned measurements. | Token accounting service with revision ids (X1.8). | M4 | P1 |
| E7.2 | **`toolResultPruner`:** model-free pruning of oversized *current* tool results through replayable surface replacements **before** summary compaction. | Compaction ladder step 1 = prune (no model call), step 2 = summarize (Master rule 7). | M4 | P0 |
| E7.3 | **Compaction via pressure events:** compaction reacts to post-step pressure and request-error recovery; **no model-facing "compact" tool.** | Compaction triggered by loop events only. | M4 | P1 |
| E7.4 | **`sessionStatus`:** reading acknowledgements and manual unread marks stored **outside session history.** | Unread dots/marks in the session list (Master 9.1) in a separate table. | M4, M19 | P1 |
| E7.5 | **`workspaceChanges`:** per-turn **changed-file summaries** with turn-start vs turn-end comparison, served by session and event sequence; the log carries only the turn. | "Changes this turn" panel (extends D3.12 deliverables). | M11, M19 | P0 |
| E7.6 | **`workspaceFiles`:** stat, paged text, byte windows, directory listings and a change feed **confined by `lstat`, containment and a stat re-check.** | File API for the renderer's file tree/viewer with TOCTOU re-check. | M5, M19 | P0 |
| E7.7 | **`fileReferences`:** `@` path completion returns **paths only, never contents.** | Composer `@file` completion (A1.9) contract. | M19 | P1 |
| E7.8 | **`sessionReferenceResolver`:** an `@session` mention embeds a bounded snapshot of another session as **untrusted message context.** | Cross-session references with taint. | M4, M13 | P1 |
| E7.9 | **`sessionQuery` seam:** exact reads, filters, traces; backend adds full-text reconciliation, ranking, snippets and cursor generations. | Session search service (FTS5) with stable cursors. | M4 | P1 |
| E7.10 | **`sessionTitle` seam:** deterministic fallback title, latest-title fold, one optional async provider (first-prompt vs all-prompts variants). | Title service with fallback so titles never block. | M4 | P2 |
| E7.11 | **`planMode`:** plan/mode state folded from the log; user selections flushed at turn boundaries; guidance rendering; `/plan`; stable plan-exit schema. | Plan agent state machine (W2.11). | M7 | P1 |
| E7.12 | **`agentPresets` with revisions:** YAML-declared preset revisions; retired revisions kept until their last user releases them. | Preset versions so running sessions keep their composition. | M7, M12 | P1 |
| E7.13 | **`sessionProjectionCache`:** durable checkpoints of projection state (throttled, mandatory at turn end/detach) to accelerate hydration. | Projection checkpoints for fast session open (E4.4 budget). | M4 | P1 |
| E7.14 | **`mcpManager`:** reconciles MCP client instances against settings, aggregates statuses, serves restart/probe to management surfaces. | MCP fleet manager (Master M6). | M6 | P0 |
| E7.15 | **`schedule` independent of session activation:** tasks stored separately; due messages queued into the target session. | Scheduler (M14) injecting into sessions that may be cold. | M14 | P1 |
| E7.16 | **`ssh` seam:** one authenticated OpenSSH connection, installed helper identity, independent program streams, disconnect cleanup; paired `fs`/`subprocess`/`sandbox` providers for the remote world. | C4.10 implemented as one provider set. | M20 | P1 |
| E7.17 | **`shellEnv`:** plugins declare effect-scoped `KEEL_*` environment facts; each shell tool collects one **trusted snapshot per execution.** | Env facts registry (project root, session id) injected into shells. | M5 | P1 |
| E7.18 | **`sandboxPolicy`:** the single home for default sandbox mode and workspace root so **bash and fs can't confine to different roots;** consumers hand over the exact argv; backend reports enforcement. | One policy service used by shell, fs and terminals. | M3, M5 | P0 |
| E7.19 | **`approval` seam fails closed:** absence of an answerer yields `unavailable`. | Already W3.12; add test. | M3 | P0 |
| E7.20 | **`permissionPresets`:** user-facing presets bundling sandbox mode + approval policy; switching writes one logged `permission/preset` event that updates both knobs. | Cautious/Balanced/Trusted presets (V5) as one logged event. | M3, M4 | P0 |
| E7.21 | **`fs-observation-policy`:** observed-state checks (read-before-edit, stale-file detection) contributed through the `fs/*` event gate. | Master rule 13 implemented as a hook. | M5 | P0 |
| E7.22 | **`lsp` seam with exactly four normalized operations** and no protocol escape hatch. | Keep Keel's LSP tool to a small normalized set (diagnostics, definition, references, symbols); backend translates. | M11 | P1 |
| E7.23 | **`web` seam:** search and fetch providers register into one service; tool names stay stable. | Providers for SearXNG, plain HTTP fetch (A1.11). | M5 | P0 |
| E7.24 | **`speechToText` seam** with local recognizers; browser uses an authenticated remote; transcripts stay in the draft until submission. | Dictation puts text in the composer, never auto-sends (A2.2). | M17 | P1 |
| E7.25 | **`officeKit`:** render Office files to PDF/images, convert, recalculate on the host using a native engine or a WASM fallback; document preview sidebar. | Office preview/convert with optional LibreOffice; WASM fallback; no cloud. | M17, M19 | P1 |
| E7.26 | **`fileUploads`:** streaming intake, durable storage, staged receipts bound to accepted submissions. | Attachment pipeline with staged → committed states. | M4, M19 | P1 |
| E7.27 | **Forge seam (code-host change requests):** providers map remote URLs to change requests, look up by head branch, read status in batches; watchers share one polling loop; session projection binds change requests found in shell push output; a panel shows Git inspection and status. | PR/MR integration for GitHub/GitLab/Forgejo using the user's own token; polling shared. | M11, M15 | P2 |
| E7.28 | **`remoteAccess` role policies:** non-owner peers get role-based access to specific methods; list results filtered; each peer's access snapshot streamed. | Paired-client roles (owner, approver, viewer) for phone/LAN clients (B4.8, C1.12). | M20, M3 | P1 |
| E7.29 | **Connection authentication as a registry** of credential verifiers tried in registration order; first live peer wins; source policy and business authorization stay separate. | Auth providers: token, pairing, desktop-local. | M20 | P1 |
| E7.30 | **`authorization` flow registry:** a plugin that knows how to obtain a credential registers a flow keyed by the record it writes; one attempt per key at a time. | Device-code/OAuth flows for providers/connectors. | M2, M15 | P1 |
| E7.31 | **Action cards:** optional cards with user actions and status notices; card kinds register their actions and handlers. | Generic "action card" row kind (Y2.9) for plugin-proposed actions (e.g., recommend a plugin). | M19, M10 | P2 |
| E7.32 | **Plugin recommendations on explicit need only;** enabling goes through the plugin manager after a click. | Never auto-suggest installs without a stated need. | M10 | P2 |
| E7.33 | **Plugin registry probe:** race several registry mirrors and pick the fastest valid one. | Mirror selection for the update/plugin index (C12.4). | M22 | P2 |
| E7.34 | **Plugin market reader** for **user-configured index sources**, validated; install through the manager. | Private plugin index file/URL list (G7 respected). | M10 | P1 |
| E7.35 | **Message feedback in the canonical log** with per-item compare-and-set; session-level `/feedback` as a log-only event. | Thumbs + note (D3.16) implemented as log events. | M4, M19 | P1 |
| E7.36 | **Hooks bridges:** the reference ships adapters that run hooks defined in other agent tools' formats. | Optional importers/runners for documented hook formats (C7.x); verify formats first. | M8, M20 | P2 |
| E7.37 | **Agent-authored plugins:** a tool lets the agent define plugin code whose host half runs in a sandboxed VM and whose client half is served to the page. | **P2, off by default:** agent proposes a plugin as a diff; user reviews; runs in the V23 isolated subprocess; never auto-enabled. | M10 | P2 |
| E7.38 | **Workflow engine** (script engine) plus a fixed **loop-until-done** workflow consumer that fans out subagents. | Workflow nodes (C5.1) + a built-in "iterate until checks pass" workflow template. | M8 | P1 |
| E7.39 | **Webhook runtime** where trusted rules turn authenticated deliveries into ordinary sessions; provider adapters (e.g., code host events). | Extends D3.8; adapter for repo events via user's own webhook. | M15 | P2 |
| E7.40 | **Inspector service:** worker-hosted debug target + query API over the live plugin tree. | Keel Inspector dock (D3.22) backed by an introspection API. | M21 | P1 |
| E7.41 | **Storage seam with multiple backends (json, sqlite) and a typed "domain" form** for non-session state. | Keep SQLite only, but isolate non-session state behind one storage interface for testability. | M4 | P2 |
| E7.42 | **`mcpResources` seam** (connection-owned providers serve shared resource tools). | Already W3.11; add scoping per agent. | M6 | P2 |
| E7.43 | **Browser-use and computer-use as provider seams** (several interchangeable providers; each provider owns its tools and per-session resources; no shared action API; **per-application consent with cancellation**; retained run-code runtime per agent). | M16: providers (Playwright, CDP) behind one registration; per-app consent for desktop control (extends X5.9). | M16 | P1 |

## 9. Builder protocol for own ideas `[S]`

For every `V` row (and any `[S]` row anywhere): (1) why + 2 comparable products/standards by category; (2) free/license check with date; (3) spec in Keel's words; (4) smallest slice behind an `experimental` flag; (5) negative tests first if security-relevant; (6) end-to-end evidence incl. offline run; (7) owner review before default-on if it stores personal data, uses network, or changes approvals.

| ID | Idea | Approach | M | Pri |
| --- | --- | --- | --- | --- |
| V24 | **Tool conformance kit:** one automated suite every tool must pass: output schema declared, presenter pure on replay, cancel honored within N ms, no leaked fields in `schemas()`, concurrency flag only on read-only tools, timeout cooperative, errors typed. | Table-driven pytest over the registry; fails CI on any new tool that doesn't register conformance metadata. Implements E1.x/E2.x checks. | M5, M25 | P0 |
| V25 | **Tool pipeline fuzzer:** random args, random cancel points, injected failures; assert no hang, no leaked process/task, no orphan call without result, log stays replayable. | Hypothesis-style + chaos tests with the fixture model server. | M25 | P1 |
| V26 | **Request-reconstruction test:** replay a session log and rebuild the exact provider request; byte-compare with what was actually sent (hash) to prove "model-visible = logged" (D2.11). | Store request hash per step; test recomputes from log. | M4, M25 | P0 |
| V27 | **Release publish verifier:** before upload, cross-check manifest, sizes, SHA-256/512, signatures, version monotonicity, completion record; after upload, re-download and verify; metadata last. | `keel-release verify` command used by CI and by the owner manually (E5.14/E5.15). | M22 | P0 |
| V28 | **Error-code catalog generator:** scan code for error constants, produce the troubleshooting pages and the typed-code list; fail CI if a raised code is undocumented. | AST scan + template; ties to E1.14/E6.11. | M23, M25 | P1 |
| V29 | **Per-tool timeout and output-size budget table** visible in the UI (and editable), with default values by tool class. | Config table; show countdown on running tool cards. | M5, M19 | P2 |
| V30 | **Postmortem template and counter:** every escaped bug gets a numbered postmortem (cause, why tests missed it, new test) linked from the fixing commit. | `docs/postmortem/NNNN-*.md` + CI check that a `fix:` commit tagged "escaped" references one (E4.9). | M0, M25 | P1 |
| V31 | **Local-socket transport spike:** prove Electron ↔ Python over named pipe/UDS with streaming and backpressure on all three OSes before committing (C-19); keep TCP+token as fallback. | 1-week spike with benchmark; decide via `DECISIONS.md`. | M19, M20 | P0 |

## 10. UI/UX additions (Keel tokens only)

- Tool cards: generic, terminal (exit pill), diff, search (grouped/paths with "showing N of M"), read (numbered, highlighted), web (sources/fetch summary) `T:DS-TOOLS`
- Subagent tree viewer with names/paths, activity badge (running/inactive), message box, interrupt button, unknown-mode rows `T:DS-SUB`
- Provider forms: masked key field with staged-removal rules, env hints, discovery dialog with search/tick, protocol picker, capability and effort editors, compat switches in an Advanced section, troubleshooting links `T:DS-PROV`
- Model picker with Effort submenu, drag/keyboard reorder, "Select model" blocked state `T:DS-PROV`
- Changes-this-turn panel, unread marks in session list `T:DS-SEAMS`
- Update flow: delayed check, menu item, confirmation dialog, progress, "what changes for you" `T:DS-DESK`
- Extensions window with narrow IPC and transaction log `T:DS-DESK`
- Known limits page in About `T:DS-DESK, DS-DEF`

## 11. Defensive-pattern habits to adopt (DS-DEF)

Five habits become the builder review checklist, each with a documented rule page per artifact (package surface, remote/API, client components, conversation/session, general) once the M0 read of those pages is done:
1. **Make correctness explicit** (structure over timing compensation).
2. **One source of truth** (one read path, one home per fact, one owner for shared state).
3. **Extend through the registered seam** (new capability registers; stop growing branches in an existing carrier).
4. **Change face equals review face** (a change carries only the lines its behavior needs; migrations move code; perf-sensitive changes carry measurements).
5. **Require evidence** (falsifiable claims, measured before/after or checked by a gate).
Each rule states what must hold, how a reviewer judges it, its boundary and who approves exceptions, plus a correct and a wrong example. A `code-review` agent skill reads these rules when reviewing PRs (also usable inside Keel as a bundled reviewer agent, B2.4). `E8.1` (all): create `docs/defensive-patterns/` equivalents after reading the five DS pages. `T:DS-DEF`

## 12. Conflicts and decisions

| ID | Issue | Resolution |
| --- | --- | --- |
| C-13 | DS says content replacement is not confidentiality; Keel's DLP must **block or replace the value**, not just content. | E1.7 enforced; DLP tests assert the program/code-mode value is also hidden. |
| C-14 | DS: "inference is cheap, do not ration real-API tests." Keel must stay free for the user and CI. | Provider e2e is opt-in with user keys; Keel's own CI uses local/mock models; no paid dependency. |
| C-15 | DS excludes Linux desktop releases; Keel requires Linux. | Keep Linux; budget its test lane. |
| C-16 | DS uses paid Apple/Windows EV signing and hosted object storage for updates. | Excluded (Master D3/D5); copy only the verification and publish *process*. |
| C-17 | DS has optional OTLP product analytics. | Excluded: no telemetry (Master 6.18). |
| C-19 | Master architecture says renderer↔daemon over loopback HTTP with a bearer token. DS shows a no-port option. | Run V31 spike; recommended: **desktop uses UDS/named pipe**, `keel web` and CLI use loopback+token. Owner confirms. |
| C-20 | DS requires sandbox/test rigor that assumes paid CI scale. | Same tiering as C-8. |
| C-21 | DS has "agent-authored plugins" (E7.37). | P2, off by default, never auto-enabled; high risk. |

## 13. Priority order

1. **Core contracts:** E1.1 to E1.14, E1.18, E3.3, E3.5, E3.8 to E3.10, E7.2, E7.18, E7.20, E7.21, V24, V26.
2. **Safety and release process:** E5.1 (after V31), E5.2 to E5.5, E5.8, E5.9, E5.14, E5.15, V27.
3. **Test infrastructure:** E4.1 to E4.5, E4.8 to E4.13, E4.15.
4. **Provider/model UX:** E6.1, E6.5, E6.7 to E6.10.
5. **UI cards and fleet views:** E2.1 to E2.3, E3.12, E7.5.
6. Everything else at its milestone; P2 after the v1.0 candidate is green. Add every row to `PLAN-INDEX.json` with its source tag.

