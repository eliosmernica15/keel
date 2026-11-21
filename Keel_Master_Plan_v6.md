# Keel Master Plan v6

**Status:** canonical expanded roadmap. Supersedes v5 for planning purposes while preserving v5 as the historical baseline.

## Source documents (preserved unchanged)

- `C:\Users\Admin\Downloads\Keel_Master_Plan_v5.md`
- `C:\Users\Admin\Downloads\Keel_Plan_v5_Addendum_Missed_Features.md`
- `C:\Users\Admin\Downloads\Keel_Plan_v5_Addendum_2_More_Features.md`

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
| A1.1 | Non-interactive run mode (`keel run "prompt"`, pipes, JSON output, exit codes) for scripts and CI | M20 | P0 | verified |
| A1.10 | `todo` tool (agent keeps a visible task checklist), separate from the plan | M5 | P0 | verified |
| A1.11 | `webfetch` tool and `websearch` tool with **free** backends | M5 | P0 | verified |
| A1.12 | Per-agent tool enable/disable and per-agent permission overrides | M7 | P0 | verified |
| A1.13 | Custom tools as code files dropped in `.keel/tools/` (Python) | M10 | P0 | verified |
| A1.14 | `instructions` config: extra instruction files by glob or URL | M7 | P1 | not_started |
| A1.15 | `small_model` for titles/summaries (already a role) plus per-agent model override | M2 | P1 | not_started |
| A1.16 | Configurable leader-key keybinds, custom theme JSON files | M19 | P1 | not_started |
| A1.17 | Session import/export commands and `keel stats` (usage by model/day) | M21 | P1 | not_started |
| A1.18 | `keel agent create` wizard, `keel models`, `keel auth` subcommands | M20 | P1 | not_started |
| A1.19 | **GitHub Actions mode**: run Keel headless in the user's own CI to answer issues/PR comments | M20 | P2 | not_started |
| A1.2 | Attach a CLI/TUI/IDE client to an already-running daemon (`keel attach`) | M20 | P0 | verified |
| A1.20 | Watcher ignore list, auto-update toggle, env-var overrides (`KEEL_*`) | M2 | P1 | not_started |
| A1.21 | Remove versions older than X before install notice | M22 | P2 | not_started |
| A1.22 | `AGENTS.md` for the builder itself (internal) describing layout and conventions | M0 | P0 | verified |
| A1.3 | **Terminal UI front-end** (full TUI, not only Electron) | M20 | P1 | not_started |
| A1.4 | **Local web UI** served on loopback (`keel web`) for browser access | M20 | P1 | not_started |
| A1.5 | `/init` command: scan repo and generate `AGENTS.md` | M7 | P0 | verified |
| A1.6 | Inline shell via `!cmd` prefix in composer (goes through permission gate) | M19 | P1 | not_started |
| A1.7 | Slash commands: `/undo /redo /compact /export /models /themes /details /editor /share-local` | M7 | P0 | verified |
| A1.8 | Open file/diff in user's `$EDITOR` / VS Code | M19 | P1 | not_started |
| A1.9 | Image paste/drag into composer, fuzzy `@file` search | M19 | P0 | verified |
| A2.1 | **Voice-to-task handoff**: a voice session hands work to the same agent loop and reads results back | M17 | P1 | not_started |
| A2.2 | System-wide push-to-talk dictation hotkey (types into any app) | M17 | P1 | verified |
| A2.3 | Per-agent **persistent browser profile** and per-agent workspace folder | M16 | P0 | not_started |
| A2.4 | Idle suspend/wake of heavy resources (browser, container desktop, LSP) | M16 | P1 | not_started |
| A2.5 | Group-chat loop guards (agents @mentioning each other endlessly) | M12 | P0 | verified |
| A2.6 | Primary-agent daily check-in/digest at chosen times | M14 | P1 | not_started |
| A2.7 | Documented `.env.example`-style config reference for every setting | M2 | P1 | not_started |
| A2.8 | Local Playwright E2E that exercises real flows (chat, tools, viewer, search, connections, voice, groups, settings) | M25 | P0 | verified |
| A2.9 | Memory-consolidation and history-compaction **tunable knobs** surfaced in settings | M13 | P1 | not_started |
| A3.1 | **Outgoing signed webhooks** with retry/backoff and delivery log | M14 | P1 | not_started |
| A3.10 | Per-vendor **cost caps with daily and monthly windows** | M21 | P0 | verified |
| A3.11 | Deploy/operations docs for headless mode (`keel serve` on a home server) | M20 | P1 | not_started |
| A3.2 | Idle task-workspace garbage collection (temp folders) | M14 | P1 | not_started |
| A3.3 | **Mock/scripted agent** for UI development and tests (deterministic scripted runs) | M19 | P0 | verified |
| A3.4 | Interactive **questions** from agent mid-task with timeout and default answer | M5 | P0 | verified |
| A3.5 | Setup script that generates local secrets idempotently and prints what is missing (`keel setup`) | M3 | P1 | not_started |
| A3.6 | "Sign out everywhere / disconnect" equivalent: **revoke all client tokens** and reset daemon key | M3 | P0 | verified |
| A3.7 | Honest "Project status" page listing what is proven end-to-end vs built-but-unproven | M26 | P1 | not_started |
| A3.8 | Site tools: secrets manager, DB browser, scheduled jobs, analytics, element editor for generated sites | M18 | P2 | not_started |
| A3.9 | Operator-style **Admin page** (limits, alerts, health, background job table) | M21 | P1 | not_started |
| A4.1 | **OS service supervision**: daemon as systemd user unit / launchd agent / Windows scheduled task, watchdog, crash-loop backoff | M14 | P1 | verified |
| A4.2 | Deterministic, reproducible template/package build (stable tarball, pinned versions) | M22 | P1 | not_started |
| A4.3 | MCP presets catalog limited to free/self-hosted servers (filesystem, git, fetch, SQLite, time, memory, Playwright, sequential-thinking, etc.), one-click add, dormant until configured | M6 | P0 | not_started |
| A4.4 | Rigor contract in persona (verify before claiming done, cite evidence) as default agent preamble | M7 | P0 | verified |
| A4.5 | Coding-agent routing rules (which sub-agent/model for which task type) in the persona | M12 | P1 | not_started |
| A4.6 | "Test-fire" check for every integration after saving credentials | M15 | P0 | verified |
| A4.7 | Secret providers beyond keychain as user choice: env file, command (`pass`, `bw` CLI the user already owns) | M3 | P2 | not_started |
| A4.8 | Release scan proving **zero secrets in artifacts** on every release | M22 | P0 | verified |
| A5.1 | **Gateway** process concept with `status`, start/stop, and a list of running channels | M15 | P0 | verified |
| A5.2 | Install a channel/plugin from a git URL or local link for development (`install --link`) | M10 | P1 | not_started |
| A5.3 | **Account-level config inheritance** (account overrides channel defaults) | M15 | P0 | verified |
| A5.4 | **Delivery fallback chain** (preferred service, then fallback) | M15 | P1 | not_started |
| A5.5 | Outbound message state machine: queued, sent, delivered, read, failed with retries and dedupe by message id | M15 | P0 | not_started |
| A5.6 | Webhook subscription helper (register, list, rotate secret) as a CLI command | M15 | P1 | not_started |
| A5.7 | Per-channel troubleshooting checklist surfaced in UI when a channel fails | M15 | P1 | not_started |
| B1.1 | **Grammar/JSON-schema constrained decoding** for tool calls | M2 | P0 | verified |
| B1.10 | Speculative/draft decoding toggle where the runtime supports it | M2 | P2 | not_started |
| B1.2 | Tolerant tool-call parser + **repair loop** | M2 | P0 | verified |
| B1.3 | Difficulty-based **model router** | M2 | P1 | not_started |
| B1.4 | Prefix/KV-cache reuse | M2 | P1 | not_started |
| B1.5 | Smart context management | M4 | P0 | verified |
| B1.6 | **Model download manager** | M2 | P0 | verified |
| B1.7 | Hardware detector and quantization advisor | M2 | P1 | not_started |
| B1.8 | Local embedding + reranker models | M11 | P1 | not_started |
| B1.9 | **Compare mode (arena)** | M19 | P1 | not_started |
| B2.1 | **Verification loop**: auto-detect test/lint/type commands, run after edits, feed failures back, stop at "definition of done" checklist | M7 | P0 | verified |
| B2.10 | HTTP/API tester with saved collections | M15 | P2 | not_started |
| B2.11 | Diagram tools: Mermaid and Graphviz rendering offline | M17 | P1 | not_started |
| B2.12 | OCR and document parsing (Tesseract, PDF text/tables) with license check | M17 | P1 | not_started |
| B2.13 | Optional local image generation (user-installed ComfyUI/diffusers, model licenses shown) | M17 | P2 | not_started |
| B2.14 | Prompt library with variables, snippets, "improve my prompt" helper | M19 | P1 | not_started |
| B2.15 | Macro/workflow recorder from chat history into a reusable workflow | M8 | P1 | not_started |
| B2.16 | Workflow and team template **gallery** (bundled, offline) | M12 | P1 | not_started |
| B2.2 | Spec-driven mode: spec, task breakdown, implement, verify, with approvals between stages | M7 | P1 | not_started |
| B2.3 | **Keel Duet default design**: builder agent + independent reviewer agent with different model/prompt; reviewer can only comment | M12 | P0 | verified |
| B2.4 | Specialist agents shipped as bundled markdown: code reviewer, security reviewer, test writer, refactorer, docs writer, dependency upgrader, merge-conflict resolver, bisect helper, changelog and PR-description writer | M7 | P1 | not_started |
| B2.5 | Deep-research mode with citations, local files plus web, saved as a report | M17 | P1 | not_started |
| B2.6 | Local **RAG knowledge bases** over folders, PDFs, docs; file watcher; citations with file and line | M13 | P0 | not_started |
| B2.7 | Offline documentation packs (language/library docs) the agent can search | M13 | P2 | not_started |
| B2.8 | Notebook/REPL tool for data analysis with inline charts | M5 | P1 | not_started |
| B2.9 | Read-only **database explorer** tool (SQLite, Postgres, MySQL via user's own connection), write needs approval | M15 | P1 | not_started |
| B3.1 | **WASM/Pyodide sandbox** for running untrusted generated code with no Docker | M5 | P1 | not_started |
| B3.10 | Optional app-lock passphrase and auto-lock on idle | M3 | P2 | not_started |
| B3.11 | Provider **circuit breaker**, retry/backoff, health score, automatic failover | M2 | P0 | verified |
| B3.12 | Immutable, exportable audit bundle with verification tool | M3 | P1 | not_started |
| B3.2 | Container sandbox with CPU, memory, time and network limits (optional Podman) | M5 | P1 | not_started |
| B3.3 | **Dry-run mode**: agent plans and shows every side effect, executes none | M7 | P0 | verified |
| B3.4 | Read-only session mode and per-project **network egress allowlist** per tool | M3 | P0 | verified |
| B3.5 | **Egress log / privacy dashboard**: exactly what was sent to which provider and when | M21 | P0 | verified |
| B3.6 | PII/secret **redaction before sending to any remote provider** (regex + small local classifier), with preview | M3 | P0 | verified |
| B3.7 | Local prompt-injection classifier and canary tokens in fetched content | M3 | P1 | not_started |
| B3.8 | Output DLP: block agent from writing secrets into files, commits or messages | M3 | P0 | verified |
| B3.9 | **Global kill switch** (hotkey and tray): stop all agents, revoke tokens, freeze scheduler | M14 | P0 | verified |
| B4.1 | Global quick-ask hotkey overlay (spotlight style) | M19 | P1 | not_started |
| B4.10 | Portable mode, multiple profiles (work/personal data dirs), relocatable data dir | M22 | P1 | not_started |
| B4.11 | Scheduled **encrypted backups** with restore wizard; optional E2EE folder sync of settings/memory via the user's own synced folder | M14 | P1 | not_started |
| B4.12 | `keel doctor --bundle`: redacted diagnostics zip the user can send to support | M21 | P0 | not_started |
| B4.13 | Auto-rollback if a new version fails to start 3 times | M22 | P0 | not_started |
| B4.14 | Delta updates and optional beta channel (opt-in) | M22 | P2 | not_started |
| B4.2 | `keel://` deep links, `keel .` to open a folder, "Open with Keel" shell integration, shell completions | M19 | P1 | not_started |
| B4.3 | Multi-window, detachable and split panels, saved workspace layouts | M19 | P1 | not_started |
| B4.4 | Message edit/regenerate, pin, bookmark, tags/folders, semantic conversation search | M19 | P1 | not_started |
| B4.5 | Rich rendering: Markdown, Mermaid, LaTeX, image/PDF preview, copy and apply buttons on code blocks | M19 | P0 | not_started |
| B4.6 | Fleet views: kanban task board, agent org chart, cost per agent, live "agent wall" | M12 | P1 | not_started |
| B4.7 | Observability views: token waterfall, flame graph, prompt diff between turns, slow-tool detector | M21 | P1 | not_started |
| B4.8 | Phone companion: **LAN web app with QR pairing** and pinned self-signed TLS (control and approvals from phone, no cloud) | M20 | P2 | not_started |
| B4.9 | Optional vim keybindings in composer; dyslexia-friendly font option (OFL fonts, notices) | M19 | P2 | not_started |
| B5.1 | Download page with OS and CPU auto-detect, file size, SHA-256, "how to verify" guide for Windows/macOS/Linux | M23 | P0 | not_started |
| B5.2 | `latest.json` plus release-notes RSS/JSON feed and version history | M23 | P0 | not_started |
| B5.3 | System requirements, model-size guide, first-run guide for unsigned installers (SmartScreen, Gatekeeper) | M23 | P0 | not_started |
| B5.4 | Offline-capable docs search (static index) and versioned docs | M23 | P1 | not_started |
| B5.5 | Privacy page ("what Keel does not collect"), EULA page, third-party notices page, SBOM download | M23 | P0 | not_started |
| B5.6 | Auto-generated screenshot gallery from E2E runs; short recorded demo replays | M23 | P1 | not_started |
| B5.7 | Curated public roadmap and FAQ, comparison page, press kit, `mailto` support (no third-party form service) | M23 | P2 | not_started |
| B5.8 | Localized website using the same string catalogs | M25 | P2 | not_started |
| B5.9 | Static status page for update feed and mirrors | M23 | P2 | not_started |
| B6.1 | Reserved offline **signed license token** format and verifier module, disabled and unused | M24 | P2 | not_started |
| B6.2 | Edition/channel field in manifest and About screen (value "standard") | M24 | P2 | not_started |
| B6.3 | Enterprise: silent-install flags for MSI/pkg/deb/rpm, Windows Group Policy templates (ADMX), macOS managed-preferences plist | M24 | P2 | not_started |
| B6.4 | Private org **update mirror** (signed manifests, custom feed URL) and private extension registry | M24 | P2 | not_started |
| B6.5 | Compliance pack: security whitepaper, accessibility conformance report, data-flow diagram, SBOM export, DPA/EULA templates (lawyer review) | M24 | P2 | not_started |
| B6.6 | Per-organization audit export format and retention settings | M24 | P2 | not_started |
| B7.1 | Property-based and fuzz tests for path containment and the command analyzer; mutation testing on the permission gate | M25 | P0 | not_started |
| B7.2 | Golden-file tests for prompt assembly; chaos tests (kill daemon mid-turn, disk full, DB locked); soak tests | M25 | P0 | not_started |
| B7.3 | Accessibility audit (axe) and visual regression in CI | M25 | P1 | not_started |
| B7.4 | Performance budgets: cold start, idle memory, installer size, time to first token overhead | M21 | P0 | not_started |
| B7.5 | Flaky-test quarantine with owner and expiry | M25 | P1 | not_started |
| B7.6 | Machine-readable task index (`PLAN-INDEX.json`): one entry per feature ID with status, evidence path, test path | M0 | P0 | verified |
| B7.7 | Architecture Decision Records (ADRs), commit convention, pre-commit hooks, devcontainer-free dev setup script | M0 | P1 | verified |
| B7.8 | Feature-flag registry with kill-switch config for risky features | M3 | P1 | not_started |
| B7.9 | Per-milestone kickoff prompt file for the AI builder with explicit "stop and ask" points | M0 | P1 | not_started |
| C1.1 | Repo hygiene stack seen in opencode: pre-commit hooks, editorconfig, linters, lockfiles, dependency **patch** folder, changelog file, release scripts folder | M0 | P0 | verified |
| C1.10 | Draft-only social/content skills (posts, threads, SEO notes); nothing posts without approval | M9 | P2 | not_started |
| C1.11 | Local task executor inside the container desktop for faster desktop actions (orgo "planned") | M16 | P2 | not_started |
| C1.12 | Client pairing allowlist for LAN/headless access (analog of orgo's `ALLOWED_EMAILS`) | M20 | P0 | not_started |
| C1.2 | More package-manager distribution: Scoop, Chocolatey, Flatpak, Snap, AUR (binary PKGBUILD), Nix flake (opencode ships several) | M22 | P1 | not_started |
| C1.3 | Dev-container-free contributor setup script and `AGENTS.md` for AI builders | M0 | P1 | not_started |
| C1.4 | **Screen-share/recording safe mode** (orgo-teammates warns never to show `.env`/dashboards on screen): mask secrets, emails, paths and tokens in UI while on | M19 | P0 | verified |
| C1.5 | Per-integration **builder/operator guides** (orgo ships separate integration guides) | M15 | P1 | not_started |
| C1.6 | Agent "looks": avatar, color, voice per agent, voice preview and speed | M12 | P1 | not_started |
| C1.7 | Meeting recorder: capture system/mic audio, local transcript, **speaker labels** (optional), summary, action items, link to project | M17 | P1 | not_started |
| C1.8 | Notes vault extras: backlinks, graph view, daily notes, templates (nicks-stack uses an Obsidian vault) | M13 | P1 | not_started |
| C1.9 | Plugin **presets bundle** (nicks-stack ships a 16-plugin config) | M10 | P1 | not_started |
| C10.1 | Interactive tutorial with a sample project, guided tours, tips, "what's new" modal | M19 | P1 | not_started |
| C10.2 | Error catalog with stable codes and fix pages (offline) | M23 | P1 | not_started |
| C10.3 | Contextual help linking to offline docs | M19 | P1 | not_started |
| C10.4 | In-app feedback saved locally, exported as a redacted bundle for email | M21 | P1 | not_started |
| C10.5 | Voice control and spoken responses for accessibility; live-region announcements for streaming text | M17 | P1 | not_started |
| C11.1 | **Source-hosting caveats to decide (verify current terms):** on GitHub's free plan, private repos may lack branch protection and advanced code/secret scanning; GitHub Pages for private repos may need a paid plan. Options: accept and use local pre-push hooks + gitleaks + signed commits; host the primary private repo on a free forge with protected branches (e.g. GitLab free tier or self-hosted Forgejo/Gitea) and mirror to GitHub; or consciously pay later (gate G6) | M1 | P0 | not_started |
| C11.2 | Security hygiene for the private repo: mandatory 2FA, signed commits, least-privilege tokens, Actions pinned by commit SHA, restricted Actions on forks (forks disabled), environment secrets with required reviewer for release publishing, access review checklist | M1 | P0 | not_started |
| C11.3 | **Source-leak incident runbook**: rotate keys, revoke tokens, take-down notices, history review, canary strings in source to trace leaks | M1 | P1 | not_started |
| C11.4 | **REUSE-style licensing metadata** (SPDX headers incl. a custom `LicenseRef-Keel-Proprietary`), auto-generated `THIRD_PARTY_NOTICES` from lockfiles, license allowlist policy file in CI | M1 | P0 | verified |
| C11.5 | EULA acceptance stored locally with version; re-prompt when the EULA changes; EULA viewable in-app and on the website | M1 | P0 | not_started |
| C11.6 | "Verified official build" indicator in About (app verifies its own hash/signature against the signed manifest); website page explaining how to recognize official downloads; typosquat/fake-site guidance | M22 | P1 | not_started |
| C11.7 | Trademark usage guidelines page; takedown/abuse contact; export-control and privacy notes (lawyer review) | M23 | P2 | not_started |
| C11.8 | Obfuscation depth (deterrent only): Nuitka-compiled core, bytecode-compiled Electron main, asar integrity, string encryption for sensitive constants, per-build canary identifiers | M22 | P1 | not_started |
| C12.1 | Manifest fields for **blocked versions**, `min_version`, security advisories, and **staged rollout** (deterministic client bucket) with no server logic | M22 | P0 | verified |
| C12.2 | **Air-gapped install and update**: offline installer bundle, sideload update file verified by signature, model import from USB/folder | M22 | P1 | not_started |
| C12.3 | Self-hosted APT and YUM repositories (static files, signed) | M22 | P1 | not_started |
| C12.4 | Mirror list with automatic failover and signature check on every mirror | M22 | P0 | verified |
| C12.5 | Portable zip builds for Windows and Linux | M22 | P2 | not_started |
| C12.6 | Release dry-run command that builds everything and runs the artifact allowlist and secret scans without publishing | M22 | P0 | verified |
| C13.1 | Local SWE-task benchmark suite (small repos with failing tests) with per-model leaderboard | M21 | P0 | not_started |
| C13.2 | LLM-as-judge with a local judge model plus trajectory scoring (steps, wasted calls, cost) | M21 | P1 | not_started |
| C13.3 | Prompt regression tests across model versions; golden transcripts | M25 | P1 | not_started |
| C13.4 | Installer smoke tests in clean VMs per OS and architecture, including upgrade from every prior release and rollback | M22 | P0 | not_started |
| C13.5 | Startup, memory and install-size trend charts stored per release | M21 | P1 | not_started |
| C2.1 | **Keel Cowork** (knowledge work) | M15 | P0 | not_started |
| C2.2 | **Keel Code** | M11 | P0 | not_started |
| C2.3 | **Keel Duet** (assumed pair mode, confirm D4) | M12 | P1 | not_started |
| C2.4 | **Fleet** | M12 | P0 | not_started |
| C2.5 | Surface switcher with per-surface default agents, tools and permissions | M19 | P0 | verified |
| C3.1 | **Best-of-N with test selection** | M7 | P0 | not_started |
| C3.10 | Uncertainty policy | M7 | P1 | not_started |
| C3.11 | Style learning | M11 | P2 | not_started |
| C3.12 | Context packs and a **context budget UI** | M19 | P1 | not_started |
| C3.2 | **Doom-loop and stuck detector** | M4 | P0 | verified |
| C3.3 | **Goal mode / overnight mode** | M14 | P1 | not_started |
| C3.4 | Think-harder slider | M19 | P1 | not_started |
| C3.5 | Planner / critic / executor roles | M7 | P1 | not_started |
| C3.6 | Map-reduce refactors | M12 | P1 | not_started |
| C3.7 | **Reflection with approval** | M13 | P1 | not_started |
| C3.8 | Failure postmortems stored per project | M13 | P2 | not_started |
| C3.9 | Cost and time **estimate before run**, with confidence | M21 | P1 | not_started |
| C4.1 | **Debugger integration via DAP**: breakpoints, step, inspect, so the agent can debug for real | M11 | P1 | not_started |
| C4.10 | **Remote targets**: run on the user's SSH servers, WSL, devcontainers; remote daemon over SSH tunnel | M20 | P1 | not_started |
| C4.11 | Browser devtools tools (console, network, performance) and **visual diff** of UI before/after; screenshot-to-code | M16 | P1 | not_started |
| C4.12 | Terminal session recording and replay | M21 | P2 | not_started |
| C4.13 | Issue-to-change pipeline from a markdown backlog or the user's own tracker token | M15 | P2 | not_started |
| C4.14 | Auto-generated architecture docs and diagrams kept in sync with code | M11 | P2 | not_started |
| C4.2 | Symbol, call and dependency **graph** with impact analysis ("what breaks if I change X") | M11 | P1 | not_started |
| C4.3 | Change-risk score and impacted-test selection | M11 | P2 | not_started |
| C4.4 | Structural search and codemods | M11 | P1 | not_started |
| C4.5 | Static analysis ingestion (SARIF in/out) | M11 | P1 | not_started |
| C4.6 | **Project security scans for the user**: secrets (gitleaks), dependency CVEs (OSV), SBOM of the user's project, license-compliance report | M11 | P1 | not_started |
| C4.7 | Profiling and benchmark agent | M11 | P2 | not_started |
| C4.8 | Log/process/port inspector, docker-compose helper, service health probes | M5 | P1 | not_started |
| C4.9 | Git extras: stacked commits, hunk staging, conflict resolver, blame-aware context, submodule and monorepo awareness, signed commits with the user's own key | M11 | P1 | not_started |
| C5.1 | Deterministic (no-LLM) nodes, loop/map nodes, sub-workflows, typed inputs/outputs with JSON Schema | M8 | P0 | not_started |
| C5.2 | Human-task node (wait for approval/answer, timeout and default) | M8 | P0 | not_started |
| C5.3 | Workflow versioning, diff, test mode with mocked tools, run history and replay | M8 | P1 | not_started |
| C5.4 | Triggers: file-watcher, folder "inbox" (drop files to process), git hook, email, clipboard, schedule | M14 | P1 | not_started |
| C5.5 | Internal event bus exposed to plugins and hooks | M10 | P1 | not_started |
| C5.6 | Notification rules: quiet hours, digests, per-channel routing; optional free push through a self-hosted or public ntfy-style service the user chooses | M14 | P1 | not_started |
| C6.1 | Separate **episodic, semantic, procedural** memory | M13 | P1 | not_started |
| C6.2 | Entity/relation knowledge graph alongside flat items | M13 | P1 | not_started |
| C6.3 | Importance scoring and decay; "dreaming" consolidation job; per-agent vs shared scopes | M13 | P1 | not_started |
| C6.4 | User profile page the person can read and edit | M13 | P1 | not_started |
| C6.5 | Memory provenance (which session/tool produced it) and tainted-source flag | M13 | P0 | verified |
| C7.1 | Read other tools' instruction files as sources (`CLAUDE.md`, `.cursorrules`, Copilot instructions, `GEMINI.md`) with merge diagnostics; add a "not affiliated" note | M7 | P0 | verified |
| C7.2 | **Importers/exporters**: MCP configs from other apps, settings, rules, sessions where formats are documented | M20 | P1 | not_started |
| C7.3 | Skill format compatible with the open `SKILL.md` convention; command format compatible with opencode-style markdown | M9 | P0 | verified |
| C7.4 | OpenAPI-to-tools generator (point at a spec, get tools, dormant until approved) | M15 | P1 | not_started |
| C7.5 | Standards checklist: AGENTS.md, MCP, ACP, LSP, DAP, OpenTelemetry GenAI conventions, SARIF, CycloneDX, SPDX, OpenAPI, JSON Schema, ICS | M25 | P1 | not_started |
| C8.1 | **Recoverable trash**: every agent delete goes to a Keel trash for N days; automatic git/stash snapshot before bulk operations | M5 | P0 | verified |
| C8.2 | Delayed destructive ops with undo window; **approve from phone** for dangerous actions | M20 | P1 | not_started |
| C8.3 | Behavior anomaly detection (sudden mass file reads, unusual network, repeated denials) pauses the agent | M3 | P1 | not_started |
| C8.4 | Honeypot/canary files that should never be read; alert if touched | M3 | P2 | not_started |
| C8.5 | Plugin/skill supply chain: capability review UI with **permission diff on update**, trust levels (bundled, signed, local, unsigned), static scan of skill scripts, signed **revocation list** delivered via the update feed | M10 | P0 | not_started |
| C8.6 | Content-addressable artifact store with dedupe and integrity checks | M4 | P1 | not_started |
| C8.7 | DB resilience: scheduled integrity check, `VACUUM INTO` backups, **rebuild projections from the events log** after corruption, retention policies, optional SQLCipher encryption at rest (verify license/packaging) | M4 | P1 | not_started |
| C8.8 | Local red-team suite (prompt injection, exfiltration, tool-abuse scenarios) run per model | M21 | P0 | not_started |
| C9.1 | **Model manager**: load/unload idle models, VRAM/RAM budget, queue concurrent requests, warm-up | M2 | P0 | not_started |
| C9.2 | Virtualized lists, incremental rendering, streaming backpressure, startup prewarm, memory-leak watchdog | M19 | P0 | not_started |
| C9.3 | Incremental repo indexing with file watching; low-power/battery mode | M11 | P1 | not_started |
| C9.4 | Per-feature resource caps (browser, LSP, container) with visible meters | M16 | P1 | not_started |

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

