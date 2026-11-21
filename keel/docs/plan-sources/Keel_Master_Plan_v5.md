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
