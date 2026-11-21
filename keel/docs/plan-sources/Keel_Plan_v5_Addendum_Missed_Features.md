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
