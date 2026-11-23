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
