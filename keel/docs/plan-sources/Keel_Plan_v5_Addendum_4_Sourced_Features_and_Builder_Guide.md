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
