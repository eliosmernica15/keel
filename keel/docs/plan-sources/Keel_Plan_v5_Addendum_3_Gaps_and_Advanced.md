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
