# Keel Fleet — persistent roadmap

Last updated: 2026-11-12 (live verification done — bridge PASSED; live model BLOCKED, no credentials on host)

## Vision

Keel Fleet is Keel's first-class multi-agent workspace: a named roster of personal agents,
each with its own persona notes, provider/model, memory and permissions, collaborating through
chat. Own branding, own assets, one shell. Local-first, no external SaaS dependency beyond the
user's own provider keys. Not a clone of Grok Bot or Bot HQ — an independent product that shares
a category, not an identity.

## Non-goals (hard)

- No screens/VNC/browser-streaming in V1 (F-Screen later, optional phase).
- No Composio/xAI/third-party SaaS connectors just because Bot HQ has them.
- No lookalike branding of Bot HQ / Grok Bot / Claude Duet — original identity only.
- No second provider credential store. Fleet reuses Keel's registry (`keel provider list`).
- No writes into global `settings.json` or env from Fleet code.
- No Echo/scripted content in any production agent. Echo is a test harness for F0–F1.

---

## Release verification & hardening (2026-11-12, complete)

Full milestone, not a feature drop. What was verified, and what is **not**:

**Verified live (this host)**
- Browser UI verification (headless Chrome 157): empty roster, agent creation,
  chat with scripted Echo, steps-fold chip, drawer tabs (Studio/Engine/Notes/
  Tasks/Permissions), notes save, task create/detail, file upload, routine
  create/run, no overflow on desktop (1440×900) and mobile (390×844), zero
  SEVERE console messages. 23/23 checks pass.
- Restart sweep (interrupted routines marked failed, tasks failed, routine unclaimed).
- Fresh-install migration: fleet.db from scratch → schema v5, all 14 tables present,
  re-migration idempotent.
- Concurrency: 30 concurrent message posts → 12 × 202 + 18 × 409, no 5xx, all
  accepted turns completed without crashes.
- Quota: 25 MB agent library quota enforced at the API/tool boundary.
- SSE: row stream flows, and SSE reconnect after an abrupt disconnect re-fetches
  missed rows (UI now catches up on reconnect via `after=<lastSeq>`).
- Security review: library preview endpoint now forces `text/plain` for non-
  image/PDF content and adds `default-src 'none'` sandbox CSP; fleet static
  pages carry `default-src 'none'; script-src 'self'; connect-src 'self'`;
  JSON APIs carry `X-Content-Type-Options: nosniff`.

**Blocked by environment (honest)**
- Live model verification: **no provider credentials exist anywhere on this host**
  (process/user/machine scopes, and local gateways on 11434/1234/3000/5000/8000
  all closed). No live model turn has ever occurred on this host. All model-backed
  turns in tests and browser checks run against a scripted deterministic adapter.
- Consequence: real provider-backed conversation, notes injection, streaming,
  delegation round-trip, routine execution — end-to-end with a real model — are
  **not verified**. This is the single blocking item for a release claim.

**Found and fixed during verification**
- Fleet app shell referenced `fleet.css`/`fleet.js` as relative URLs, resolving
  against `/` on `/fleet` (no trailing slash) — the UI was completely unstyled and
  non-interactive in real browsers. Fixed to absolute `/fleet/...` paths.
- Details drawer toggled the wrong way on first click (`panelEl.style.display` truthiness).
- Mobile CSS cascade: `.lf-panel {display:flex}` overrode the `≤1100px` hide rule —
  drawer stayed visible on mobile. Fixed with an end-of-cascade override.
- Engine panel never populated after agent creation (`syncPanelFromBot` never called in the creation path).
- SSE reconnect dropped rows that landed during the disconnect — UI now re-fetches
  `rows?after=<lastSeq>` on `open`.
- Routine claim leaked on unexpected exception in `execute_routine` — now fails
  closed with task/run marked failed and claim released.
- SSE handler crashed on client close (`ConnectionAbortedError` now caught).

**Not claimable**: production readiness; not even "feature complete" until a live
model round-trip passes on a keyed host.

---

## Live verification — 2026-11-12 (bridge verified; live model blocked)

The real harness under `keel fleet`, exercised end-to-end on a verified-zero
fleet.db (backed up and confirmed empty before any test traffic).

**Verified live (this host)**
- Bridge boots; `/fleet` serves with `default-src 'none'; script-src 'self'`;
  token auth enforced (403 without, 200 with); providers endpoint honestly
  reports every provider `configured: false`; migrations at schema v5.
- SSE row delivery confirmed live on the running bridge (row frames, incl.
  `turn_end`, from a fresh connection).
- Restart persistence verified by killing and relaunching the bridge: agent
  provider/model, notes (unique test facts) and transcripts all survive;
  replayed rows now carry `bot_id` (replayed transcripts rendered empty
  before the fix — see below).
- Browser (headless Chrome 157; desktop 1440×900, mobile 390×844):
  13/13 checks pre-restart, 10/10 post-restart; Atlas (provider agent) shows
  its configured OpenRouter model and persisted notes; Vega (Echo) replayed
  its transcript; zero SEVERE console messages; no mobile overflow.
- One real defect found and fixed: replayed transcript rows from
  `/api/fleet/bots/<id>/rows` and the group-rows endpoint omitted
  `bot_id`/`group_id`; the UI's replay path silently dropped them — chat
  panes were empty after any reload/navigation/restart. Added the ids;
  386/386 tests green; replay re-verified in the browser.

**Blocked / not verified (honest)**
- `keel provider smoke openrouter` fails: `no API key` (exit 1). No credentials
  exist in any env scope (process/user/machine); local gateways are closed;
  all five providers report unconfigured. **No live model turn has ever run.**
  Real-conversation, notes-as-model-context, live streaming, delegation
  round-trip, live approval cards: NOT VERIFIED. Echo was not substituted for
  a provider result anywhere.
- Approval system (Section 6): automated-test evidence only — 15 tests in
  `tests/test_fleet_approvals.py` drive the real F1 gate and tool boundary;
  Tier-1/Tier-2 remain authoritative. Not demonstrated live.
- `docs/PHASE1-SLICE-PROGRESS.md` carries the per-section PASSED/FAILED/BLOCKED
  breakdown for the 2026-11-12 live-verification run.

---

## F0 — Foundation (complete 2026-11-12)

Goal: working shell with a scripted Echo bot, proving roster, persistence, rows, SSE and UI.

**Delivered**
- `src/keel/fleet/` — `db.py` (SQLite v1: `bots`, `rows`, `schema_version`, WAL),
  `service.py` (`FleetStore` + pub/sub fan-out, cursor `seq`), `echo.py`
  (per-bot serial-lock turn driver), `routes.py` (`/api/fleet/*` handlers).
- `desktop/fleet/` — `index.html`, `fleet.css`, `fleet.js` — three-pane shell
  (rail · chat · Details drawer with Studio/Engine/Notes tabs), Keel palette,
  own mark/wordmark, avatar-initials system with hue picker, steps-fold chip
  (`Worked for Xs · N steps`), per-bot status dot, SSE-driven live updates.
- CLI: `keel fleet [--port N]` (aliases `keel serve` with the same bridge).
  The webapp now prints both URLs.
- Tests: `tests/test_fleet.py` — 8 end-to-end tests (create/list/detail, message
  turn end-to-end with steps and `turn_end`, update, delete, SSE row stream,
  restart persistence on the same db file). Full suite: **250 tests passing**.
- Docs: this roadmap + README update.

**Verified live**
- `/fleet`, `/fleet/fleet.css`, `/fleet/fleet.js` → HTTP 200
- `/api/fleet/bots` → 200
- `keel fleet` serves with a fresh tokenized URL and prints both links.

**Deliberately NOT in F0**
- No real provider calls (Echo only — see Engine tab; shipped in the provider
  milestone, 2026-11-12).
- No approvals (F1); F1 shipped 2026-11-12 — inline cards, per-agent policies,
  audit, Permissions tab.
- No agent-to-agent messaging (F3 — shipped 2026-11-12).
- No routines/tasks/Library (F4+/F2, still deferred).

---

## Near-term roadmap (agreed 2026-11-12)

1. **F0 — Foundation** *(complete 2026-11-12)*
2. **Real provider integration** *(complete 2026-11-12)* — OpenRouter first via Keel's existing
   provider registry; per-agent provider/model; Echo stays available as a labeled
   test engine; Fleet agent notes + prior rows injected every turn as untrusted,
   labeled context; streaming step rows, provider errors and history persist across
   restarts. Verified live with no keys (clear inline explanation + `not_configured`
   terminal reason); live model smoke is the user's (`keel provider smoke openrouter`).
   See `docs/PHASE1-SLICE-PROGRESS.md` for the full verification record.
3. **F1 — Approval cards and permission policies** *(complete 2026-11-12)* — once/always/never,
   per bot+tool scope, audit trail, permission drawer; enforced at the tool
   execution boundary; never promoted to `settings.json`; never cross-bot leaks.
   - `fleet.db` schema v2: `fleet_policies(bot_id, tool_name, decision ∈ always|never,
     updated_at)` (PK bot+tool), `fleet_approvals(approval_id, …, status ∈
     pending|approved|denied|expired, decision ∈ once|always|never, expires_at)`,
     `fleet_audit(fingerprint-only — never raw tool arguments)`; scope strictly
     per bot+tool, never global.
   - Any consequential call (`write_file` / `edit_file` / `run_shell` / `Task` /
     side-effecting MCP tools) → inline approval card in chat (<agent> asks:
     Don't allow · Allow once · Always allow). Allow-once = single invocation;
     Always = persist scoped; Don't = refuse + persist never-policy.
   - Unanswered cards are refused after 5 minutes (env override for tests);
     pending approvals are refused closed on server restart; browser disconnect
     is modeled as non-response → timeout.
   - Fleet decisions only convert Keel's `consent_required` verdict; Tier-1 deny
     rules, hooks and Tier-2 remain authoritative (verified: a fleet-approved
     `.env` write is still refused by Tier 2). Subagents inherit the gate.
   - Permission manager tab in Details drawer; revoke granularly; recent
     decisions list. Policies never leak across agents; never in `settings.json`.
4. **F3 — Agent-to-agent communication** *(complete 2026-11-12)* — `send_to_bot`,
   bounded 2–3 groups, hop caps and cycle detection, same SSE fan-out.
   - `send_to_bot(bot_slug, message)` tool (Keel catalog, `send_to_bot`); the
     receiver runs its own provider/model/identity/notes/history with its own
     approval broker — no authority transfers; reply returns as the tool result;
     rows appended to both conversations.
   - Delegation rides the F1 gate (card → allow/policy); Tier-1 deny rules,
     hooks and Tier 2 remain authoritative; subagents inherit the same gate.
   - Hard cap: ≤2 nested hops; cycle detection on (caller,target) pairs;
     self-delegation refused; chain tracked on `SessionConfig.delegation_chain`;
     hard deadline per delegation (env `KEEL_FLEET_DELEGATE_TIMEOUT_S`, 60s);
     callee's per-bot lock yields `agent_busy` instead of deadlocking.
   - Groups 2–3 members, backend-enforced (create validates size, distinctness,
     existing agents); user message fans out once per member per round; shared
     persistent ledger (`fleet.db` v3: `groups`, `group_members`, `group_rows`);
     no auto fan-out; members keep their own DM isolation and permissions.
   - UI: delegation chips (expandable reply, click-through to the callee's
     chat), groups in the rail, group view with member chips and per-agent
     done/failed/denied/busy member_status rows; SSE fans group rows out too.
   - Docs: `PHASE1-SLICE-PROGRESS.md` (full verification record).
5. **F2 — Tasks & Library** *(complete 2026-11-12)* — fleet-wide task list
   (`fleet.db` v4: `fleet_tasks`, `fleet_task_events`, `fleet_library`) and a
   persistent per-agent Library for deliverables.
   - Tasks: title/description/priority/status (`pending | in_progress |
     completed | failed | cancelled`)/progress/assignee/timestamps; event
     history (`created | status | progress | note | reassigned | delegated`);
     user CRUD over HTTP, agent access via `create_task` / `update_task` /
     `list_tasks` tools (gated by F1 like everything else); assign/reassign
     with visible notices; `send_to_bot(..., task_id=)` links delegated work to
     its originating task (events land on the task).
   - Library: `save_file` tool (text UTF-8 / base64 binary, 2 MB cap, 25 MB
     per-agent quota), storage under `~/.keel/fleet/library/<bot>/<file_id>`
     (id-addressed — traversal-proof), per-agent filtering, task and
     conversation provenance, sha256 on every file, browse/preview/download/
     delete over the bridge (user-side delete only).
   - UI: Workspace rail section (Tasks + Library with open counts), Tasks
     view (filters, inline create, detail pane with progress/events/reassign),
     Library view (grid, previews for text/images/PDF, upload, delete),
     per-agent drawer Tasks tab.
   - F1 remains the single permission engine; no second policy system added.
   - Docs: `PHASE1-SLICE-PROGRESS.md` (full verification record).
6. **F4 — Routines & Scheduling** *(complete 2026-11-12)* — cron-driven,
   timezone-aware scheduled work per agent.
   - Cron engine `fleet/cron.py` (5-field, lists/ranges/steps, month/dow
     names, dom-or-dow semantics, DST-correct via `zoneinfo`; nonexistent
     spring-forward wall times are skipped).
   - `fleet.db` v5: `fleet_routines` (name/agent/prompt/cron/timezone/
     enabled/paused/running/next/last run), `fleet_routine_runs` (per-run
     history: scheduled vs started vs finished, status, summary, error),
     `fleet_library.routine_id` (routine-attributed saves). Schema v4 → v5
     migration is idempotent; restart sweep marks interrupted runs failed and
     resets `running`.
   - Scheduler `fleet/scheduler.py`: `tick()`-driven (CLI `keel fleet` /
     `keel serve` start a 20s daemon; tests call `tick(store, now=...)`);
     atomic `running` claim prevents overlap; overdue-by-more-than-period
     slots are recorded `skipped_missed` instead of backfiring; per-run
     timeout (`KEEL_FLEET_ROUTINE_TIMEOUT_S`, default 600s).
   - Every run creates a task (`created_by`=agent), links `run.task_id`,
     flips in_progress, executes through the ordinary gated turn loop, and
     closes the task completed/failed. Files saved during the run are
     attributed to the routine.
   - **F1 remains the only permission gate**: unattended runs never
     auto-approve; cards behave exactly as in ordinary turns; on timeout the
     run fails closed with the tool name and reason; on denial the run fails
     with the same clarity. Standing `Always allow` policies are the
     sanctioned way to let unattended routines write. Live `awaiting_approval`
     status flips on the run row while a card is open.
   - UI: Routines rail entry with active-count badge; list (state dot, cron,
     next/last run), create form (agent, cron, timezone selector), detail
     (meta panel, enable/pause/disable/Run-now/Delete/Save, history list with
     per-run status/error/task link).
   - Docs: `PHASE1-SLICE-PROGRESS.md` (full verification record).

---

## Later (deferred, documented)

- **F5 — Memory.** Still notes-only; automatic memory has not been approved and
  will not be introduced without a fresh design pass.
- **F-Screen — isolated per-bot desktop.** VNC/noVNC remote desktops per agent;
  read-only observe mode; watch-only vs interactive; never in F0–F3. Explicit
  revisit only after a security review — not before.
- **Voice / x_search / Composio / other SaaS bridges.** Out unless a user
  explicitly approves an external dependency (none approved so far).
- **Native Tauri/Electron wrapper.** PWA (`sw.js`) and `keel serve` remain
  the shipping surfaces; any Tauri shell is a later add-on, untouched by fleet work.

---

## Principles worth protecting

1. **Own identity.** Any visual, copy or logo resembling Bot HQ/Grok Bot/Claude
   Duet is a defect, not a detail.
2. **No credit for free.** Echo never becomes a default agent; it must remain a
   clearly-labeled test harness.
3. **Local data, local trust.** `fleet.db` is SQLite; agents call Keel's harness;
   keys never leave `~/.keel` ecosystem nor appear in UI.
4. **Policy-first approvals.** Keel's existing restrictions are authoritative:
   Fleet approvals convert only `consent_required` verdicts; Tier-2, hooks and
   deny rules always win; unanswered cards refuse.
5. **Kill-switch-aware.** Every long-running step is cancellable from the UI;
   unanswered cards refuse; bots never proceed on ambiguity.


---

## Duet — coding surface with Fleet agents one toggle away (2026-11-13)

Keel Fleet stays the agents-first view. **Duet** is the second surface: one
toggle (`Fleet | Duet` in the top bar) swaps the chat UI into a Claude-Code-class
coding layout while keeping the same agent engine underneath — no fork of the
harness, no second conversation system.

**Duet ships (HTTP/pytest-verified; see PHASE1-SLICE-PROGRESS.md):**

- **Project registry** — pick any folder on your computer (paste an absolute
  path; browsers cannot reveal it otherwise). Stored in SQLite (`fleet_projects`,
  schema v7). Add/open/remove (never deletes files), tree listing (≤4,000
  entries, skips VCS/deps/caches), strict path containment on every file read/write.
- **Tabbed pane** — Review (git status/log/diffstat, read-only, honest
  "not a git repo" state), Terminal (each command its own detached process,
  live-streamed output, history, working dir = project root), Open file
  (quick path open), Browser (sandboxed iframe preview — local dev servers
  only; framing-refusing sites say so), plus per-file tabs with edit + save
  for text (≤1.5 MB), image preview, and binary honesty for everything else.
- **Slash palette** — `/context` (real token totals from `turn_end` rows),
  `/model <name>`, `/shell <cmd>`, `/review`, `/open <path>`, `/help`.
- **Attachments** — paperclip accepts every file type; text is embedded in
  the message, small binaries go as base64, the rest by name+size.
- **Sub-agents stay automatic** — the `Task` tool remains available to the
  model; it delegates when a job warrants it. Duet adds no toggle on purpose.
- **Background shells** — pill + Ctrl+B (works in both surfaces).
- **ask_user pop-ups, Autopilot mode, message actions (Copy/Fork/Undo)** —
  carried over from the Fleet view unchanged.

**Explicitly not done (documented honestly):**

- No live model turn has ever been observed on this host — no provider
  credentials are configured (all `configured: false`; OpenRouter free tier
  returns 402/403). All correctness evidence is pytest (408) + HTTP + build.
- The Browser tab cannot defeat sites that send `X-Frame-Options`/CSP
  `frame-ancestors`. It is a dev-server preview, not a browser.
- No PTY — the Terminal is not a shared shell session; each command is its
  own process, stdin is devnull, and Ctrl+C cannot reach a running child.
- POSIX shell is only offered when `sh` is on PATH (powershell/cmd always are
  on Windows); agents can ask for background shells with `background: true`.
- "How much context is left" has no universal honest number; `/context` shows
  recorded usage only.


---

## Four surfaces — Cowork, Code, Duet, Fleet (2026-11-13)

The original single agents view is now one of four top-bar surfaces
(`Cowork | Code | Duet | Fleet`). All share one agent engine, one transcript,
one toolset — the surfaces differ in layout and purpose, not in capability.

**Cowork** = the desktop. Home hero with quick-starts, plus sidebar pages
(Projects with trust gate, Artifacts over the Fleet Library, Scheduled over
Keel routines incl. a Windows Keep-awake process, Customize: Skills from
discover() + Connectors from settings). **Code** = the session with an
Environment/Context/Connectors rail and an Accept-edits permission mode
(writes allowed; shells still ask). Verification is unchanged: pytest
(414 passing), HTTP, and build — no browser automation available this
session; the host has no provider credentials, so no live model turn has
ever been observed anywhere on this machine. Trust is enforced in the UI:
untrusted folders cannot be opened for work until trusted; the choice is
per-folder and revocable.
