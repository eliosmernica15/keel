# Phase 1 — Vertical Slice: progress note (2026-11-12)

**Status:** the spine works end to end under the scripted fake; the real
provider adapter, settings registry, and CI are not wired. This is the
first increment toward M1/M2, not a completion of them.

## What runs today

```
PYTHONPATH=src python -m keel -p "hi" --bare --output-format stream-json --seed 7
```

Emits (verified on Windows, exit 0):

1. exactly one `system/init` (first event, after any hook lifecycle events),
2. assistant event(s) — one per content block, shared `message.id`,
3. `user/tool_result` correlated by `tool_use_id`, or `system/permission_denied`
   **then** the is_error tool result (order verified in tests),
4. exactly one terminal `result` envelope (`subtype=success`, exit 0);
   `error_max_turns` would exit 1.

- Flag validation happens before any model call (exit 1, `[keel:cli_validation]`
  on stderr, stdout untouched). `--permission-mode bypassPermissions` requires
  `--i-accept-the-risk` and still loses to deny rules (deny → ask → allow → mode).
- A bare-name deny removes the tool from the `init` manifest (tested).
- The transcript is append-only JSONL; a truncated final line is skipped by the
  reader (tested).
- `--seed` makes runs byte-identical; 10 consecutive processes produced one
  SHA-256. Golden normalisation corpus and the second machine are future work
  (M2 requires two machines).
- `keel` never runs a tool without a Tier-1 decision; print mode has no
  interactive callback, so `ask` resolves to `consent_required` deny unless an
  allow rule matches — the CI/safe default.

## Requirements traceability (implementation-plan.md Phase 1)

| Exit criterion | State |
| :- | :- |
| `keel -p … --output-format stream-json` → one init, one result, correlated tool_result | **met** (test_slice_end_to_end_success) |
| Envelope carries subtype/is_error/num_turns/session_id/usage/total_cost_usd/stop_reason/terminal_reason/permission_denials/subagent_stats | **met** (test_denial_exit_envelope_shape); `result` only on success ✓ |
| Denied call → `system/permission_denied` then is_error tool_result, order pinned | **met** (test_denial_emits_permission_denied_then_is_error_result) |
| Bare-name deny removes tool from manifest `tools` | **met** (test_bare_name_deny_removes_tool_from_manifest) |
| Transcript survives kill mid-write | **reader-side met**; writer is fsync-per-line; kill-9 recovery test is future work |
| Bare profile opens no file outside session dir | **met in-process** (test_zero_ambient_reads_in_bare_mode); OS-level proof is future work |
| Full suite headless in CI < 4 min | **not wired** — no CI yet; suite is 137 tests, ~26 s locally |
| Fake model / fake clock / fake filesystem / fake executor | **met** (keel/fakes.py) |

## Deliberate decisions (review with the gate)

1. Permission order pinned to the **spec** order (`deny → ask → allow → mode`),
   not the implementation-plan's `deny → allow → mode` summary.
2. Language: Python 3.11 + stdlib only (implementation-plan §9.3 asks for
   statically-typed; open decision, recorded in README).
3. Tool names are ours and snake_case (`run_shell`, `read_file`, …); reference
   names are aliases to be accepted on ingest, not emitted.
4. Diagnostics use `[keel:<event>]` + JSON payload (spec §16.1 / divergence #9),
   not the checklist's `[claude-code:<tag>]` form.
5. `bypassPermissions` requires explicit `--i-accept-the-risk`; refuses
   nothing by itself (deny rules still apply).
6. No `--version`, `doctor`, `mcp` or other CLI verbs yet; print mode only.

## Phase A + B completion (2026-11-12)

- **Phase A — provider registry done** (fake-transport-verified): OpenAI-compatible
  (OpenRouter/NIM/generic), Gemini (AI Studio), Anthropic (opt-in). Auto chain
  OpenRouter → AI Studio → NIM. `keel provider list|smoke`. Usage threaded into the
  envelope (`costBasis: unknown`).
- **Phase B — skills done**: loader never executes bodies, injection scan, bundled/
  user/project scopes (project untrusted), 21 default skills (18 vendored Apache-2.0
  anthropics/skills @ 2c5958e, with notices; 3 authored from scratch).
- CLAUDE.md discovery wired (root→cwd, user-role attachment, skipped in bare mode).
- Tests: **167 passing**. Provider contract tests use fixtures, zero network.
- **Unverified**: live provider responses (no keys were used); smoke lane is the
  user's. Determinism: same-machine only.
- **Phase C — scoped settings registry (first slice, done 2026-11-12)**: generic
  fold per spec §13; managed > flags > local > project > user > env; project excluded
  from `bypassPermissionsEnabled`/`dangerouslyAllowWithoutConfirm`; monotonic
  restrictive lattice; `$defaults` splice; managed
  `locks`/`highest-priority-only`; provenance + `keel settings show/schema/validate`;
  runner resolves settings before client construction.
- **Phase C — compaction (M5 shape, done 2026-11-12)**: `keel/context.py` —
  deterministic byte estimator (`BYTES_PER_TOKEN=4`), preservation of the tail
  segment, summary via a model call, `compact_boundary` event carrying the
  preserved-segment UUIDs and monotonic `cumulativeDroppedTokens`, 3-compaction
  thrash circuit breaker (auto-compact disabled + informational warning).
  Tests cover boundary shape, monotonicity, and thrash detection. Not covered:
  /compact manual trigger, hooks pre-compact, or real-tokenizer estimates.
- **Phase D — Tauri desktop (done, uncompiled, 2026-11-12)**: `desktop/` —
  vanilla-JS dark-theme UI (`ui/index.html|app.js|style.css`), zero build step;
  browser demo mode replays a scripted run through the real event renderer;
- **Phase C — subagent MVP (done 2026-11-12)**: Task tool — depth-1 inline
  subagent (`src/keel/subagent.py`): same model/executor/rules, bare child, no
  CLAUDE.md re-injection, Task removed from the child's allowlist,
  `<subagent_output>` injected into the parent's `tool_result` with turns/denials
  in a typed payload, parent events tagged with `parent_tool_use_id`. Permissions
  and Tier-2 still gate the spawn. Provider failures now produce a spec-shaped
  `error_during_execution` envelope, never a traceback.
  Honest limits: no `.keel/agents/*.md` custom subagent definitions, no
  worktree isolation, child shares the parent transcript (flat), depth enforced
  only by allowlist removal, no parallel delegation.
  Tauri shell (`src-tauri/`, ~90 lines) spawns `keel -p … --output-format
  stream-json` via a `keel_send` command, re-emits lines as `keel:event`; the
  frontend parses NDJSON defensively (no innerHTML on model output). HTML
  well-formedness + app.js syntax verified; Rust 1.99.1 installed via winget
  (2026-11-12), `cargo fetch` OK; VS Build Tools (VCTools) still installing in
  background on this host; app not yet built — see `desktop/README.md`. `keel
  --version` now exists to feed the shell's version probe. Icons generated
  (256/128/64/32 + .ico).
- **Real provider integration — Fleet (done 2026-11-12)**: `keel/fleet/provider_turn.py`
  turns a Fleet agent loose on a real provider through Keel's existing registry —
  no second credential store, keys read from the environment only, never in the
  UI. Per-agent `provider` (`auto` preserves the OpenRouter → Google AI Studio →
  NVIDIA NIM chain) and per-agent `model` (free text, defaults to the provider's
  declared model). New engines create provider-backed agents by default; Echo
  remains as a labeled scripted test bot. Fleet notes (`notes`, ≤4096 B, private
  per agent) and the conversation so far are injected as clearly labelled,
  untrusted attachments (`<fleet-notes trust="untrusted">` / `<fleet-history>`);
  the harness treats them as context, never as instructions or authority.
  Streaming tool/result steps land in `fleet.db` as `step` rows with
  running/done/error status; provider errors surface as inline `notice` rows
  (`Provider error: <category>: <message>`) and `turn_end` with
  `terminal_reason ∈ not_configured|provider_error|completed|provider_unknown|
  internal_error`; nothing raises through the UI. `provider=auto` with no keys
  answers with an inline explanation, not a crash. Fleet approvals (F1, added
  same day) gate consequential tools; until F1 they were refused outright. Live
  checks on this host: create/send/inline-error round-trip; notes and history
  survive a store reopen (tested). **Not done**: a live model smoke (no keys
  are configured on this host — run `keel provider smoke openrouter` after
  exporting `KEEL_OPENROUTER_API_KEY`). Tests at that milestone: **260 passing**.
- **Release verification & hardening — Keel Fleet (done 2026-11-12)**: full
  audit pass with fixes, no new features. Browser check (headless Chrome 157,
  desktop + mobile): 23/23 checks pass after fixing two real defects found by
  the browser: (1) `fleet.css`/`fleet.js` loaded with relative URLs resolving
  against `/` on `/fleet` — the whole F2/F3/F4 UI was silently broken in real
  browsers (never opened before; all earlier "live" checks were HTTP-only);
  (2) the Details drawer hid instead of showing on first click
  (`panelEl.style.display` truthiness), and the ≤1100px hide rule lost its
  cascade to a later `display:flex`. Engine panel now syncs on creation.
  SSE auto-reconnect previously dropped rows that arrived off-connection —
  the UI now re-fetches `rows?after=<lastSeq>` on `open`. Routines claim no
  longer leaks on unexpected exception in `execute_routine` — fails closed with
  run/task marked failed and claim released. SSE handler catches
  `ConnectionAbortedError`. Library `preview` forces `text/plain` for
  non-image/PDF content and adds `default-src 'none'; style-src 'unsafe-inline'`
  sandbox CSP; fleet static pages carry `default-src 'none'; script-src 'self'`.
  **386 tests passing.** **Honest blocker: no provider credentials exist on
  this host anywhere (env scopes, local gateways) — no live model turn has
  ever run. Real provider verification remains open and is the only thing
  between this and any release claim.** First live model turn: needs
  `KEEL_OPENROUTER_API_KEY` (or a keyed host) and `keel provider smoke openrouter`.
- **Live verification — Keel Fleet (done 2026-11-12)**: the real harness,
  run end-to-end on a verified-zero fleet.db (backed up and confirmed empty
  before any test traffic). Results by section, PASSED / FAILED / BLOCKED:
  1. **Automated tests — PASSED**: 386 passed after one real defect was found
     and fixed (see §7). No regressions.
  2. **Provider smoke — FAILED (not configured)**: `keel provider smoke
     openrouter` exits 1 with
     `{"provider":"openrouter","category":"unknown","error":"openrouter: no API key"}`.
     No credentials exist in any env scope (process/user/machine); local
     gateways on 11434/1234/3000/5000/8000 refuse connections; all five Keel
     providers report `configured: false`. No fakes were created and provider
     configuration was not modified.
  3. **Real model-backed conversation — BLOCKED**: impossible without a key.
     The provider-turn path itself is verified end-to-end as far as it can go
     without keys: a provider agent's message exercises the real
     `execute_turn` → provider-resolution code path and returns the inline
     "Provider turn could not start: no provider is configured" notice with a
     `not_configured` turn_end row — rendered by the real UI path.
  4. **Memory (notes) injection — PARTIAL/BLOCKED**: notes are stored per
     agent and survive restarts (AtlasRestart kept `FLEET-VERIFY-KEY is
     VIOLET-1337.`, Atlas kept the HELIO-7741 fact; verified via API and in
     the browser post-restart). Notes are injected into the outgoing request
     as untrusted context — covered by automated tests
     (`tests/test_fleet_provider.py`). A model actually *using* the note
     cannot be verified without a key: BLOCKED.
  5. **Approval system — NOT TESTED LIVE / BLOCKED**: no live turn can reach
     a tool call without a key. F1 is automated-test-verified against the
     real tool boundary (15 tests in `tests/test_fleet_approvals.py`:
     Allow once / Always allow / Don't allow, timeout→deny, audit
     fingerprints only, restart sweep). Tier-1 deny rules, hooks and Tier-2
     remain authoritative and were not weakened; Fleet's approval cards only
     convert `consent_required` pauses. No live approval-card demonstration.
  6. **Browser verification — PASSED**: headless Chrome 157. Pre-restart:
     13/13 checks (bridge, /fleet, default engine=provider, agent creation,
     notes save, echo agent reply, engine pane honest "no providers
     configured" state, zero SEVERE console messages, mobile no overflow).
     Post-restart (transcript replay): 10/10 checks; Atlas's 4 persisted rows
     render in the DOM (join notice, user message, not-configured explanation,
     turn_end). Desktop 1440×900, mobile 390×844.
  7. **Errors found and fixed during this pass**: (a) replayed transcript
     rows from `/api/fleet/bots/<id>/rows` (and the group rows endpoint)
     omitted `bot_id`/`group_id`, so `handleRow` dropped every replayed row —
     after ANY navigation away and back, or any reload/restart, the chat
     pane rendered empty. Live SSE was unaffected (its payloads do carry
     bot_id), which is why the relver milestone never caught it. Fixed by
     adding the id to both replay payloads; suite re-run green; replay
     re-verified 10/10. (b) Engine pane told unconfigured-`auto` users
     "follows Keel's fallback chain (OpenRouter → Google → NIM)" — now
     honestly shows "no providers configured; the agent cannot run".
  8. **Blocked-by-environment / not done**: live provider conversation,
     notes-as-model-context, streaming from a real model, delegation round-trip
     with a real model, live approval cards, production-readiness claim of any
     kind. One item stands between this and a release claim: export
     `KEEL_OPENROUTER_API_KEY`, run `keel provider smoke openrouter`, then one
     real turn through `/fleet`.
  Cleanup: all test agents deleted via the API; fleet.db verified all-zero
  (bots/rows/tasks/events/routines/runs/files/groups/approvals/policies/audit);
  test-created files/routines/tasks: none created; helper scripts removed;
  pytest session dirs under `~/.keel/projects` purged (real project transcripts
  untouched); all test bridge processes stopped.
- **Fleet F4 — Routines & Scheduling (done 2026-11-12)**: `fleet/cron.py`
  (5-field cron; lists/ranges/steps; month/day-of-week names; dom-or-dow
  semantics; nonexistent spring-forward wall times skipped; everything in
  local wall time via `zoneinfo` — DST-correct on both transitions, verified
  by dedicated tests per transition), `fleet/scheduler.py` (`tick()`-driven;
  the CLI daemon ticks every 20s; `KEEL_FLEET_SCHEDULER_DISABLED=1` switches
  it off; tests drive `tick(store, now=...)` directly), `fleet/runtime.py`
  (thread-local marker so the F1 broker flips a blocked routine run to
  `awaiting_approval` live). `fleet.db` v5: `fleet_routines`/
  `fleet_routine_runs` (+ `fleet_library.routine_id`); restart sweep marks
  interrupted runs `failed` and resets `running`. A routine execution
  creates a task (created_by = the routine's agent), links `run.task_id`,
  runs the same gated turn loop as everything else, and closes the task
  completed (success) or failed (error/approval timeout/denial) with an
  event note. Overlapping executions are atomically impossible (`running`
  0→1 claim; second claim refused with 409), duplicate slots cannot execute
  twice (skip to next future slot after each run), and a slot overdue by
  more than one period is recorded `skipped_missed` instead of backfiring.
  Unattended runs never auto-approve anything: a consequential tool call
  raises the ordinary F1 card, waits, and fails closed on timeout with the
  tool name and reason — by design, an operator who wants an unattended
  routine to write must pre-approve it (Always allow). **All consequential
  routine tools verified against the real gate** (write_file refused after
  awaiting_approval; timeout variant; always-allow variant). Verified:
  **382 tests passing** (33 routines tests: cron unit incl. DST matrix,
  CRUD over HTTP, manual + tick-driven execution, missed-run skip, task
  completion/linkage, file attribution, F1 gate incl. awaiting_approval
  live flip, restart sweep, per-agent model isolation). Live smoke on this
  host: full CRUD + validation errors + pause/resume/409 + manual run +
  agent DM rows + cleanup to zero. **Not verified**: a real model executing
  a routine end-to-end (no keys on this host — the loop is scripted); the
  browser routines view (rail, list, detail, history) not screenshot-checked
  here; routine→task linkage when the model ignores `save_file(task_id=…)` in
  its instructions (works because the attachment supplies the id); F5
  (memory) remains out of scope.
- **Fleet F2 — Tasks & Library (done 2026-11-12)**: `fleet.db` schema v4
  (`fleet_tasks` — status pending|in_progress|completed|failed|cancelled,
  priority low|normal|high, progress 0-100, assignment/provenance fields;
  `fleet_task_events` — per-task history created|status|progress|note|
  reassigned|delegated; `fleet_library` — id-addressed files with sha256,
  size, mime, task/owner provenance). User-facing CRUD under `/api/fleet/
  tasks[...]` (create/update/assign/cancel/delete, per-bot filtering,
  unassigned scoping) with notices in the assignee's DM on assignment;
  agent surface via three new Keel builtin tools gated by F1 like
  everything else: `create_task` (self/other/unassigned assignee), `update_task`
  (status+progress+note, owners only: assignee or creator), `list_tasks`
  (me/all/assignee + status filter); plus `save_file` (text UTF-8 / base64
  binary, 2 MB cap, 25 MB per-agent quota, id-addressed storage
  `~/.keel/fleet/library/<bot>/<file_id>` — filename never touches disk).
  Preview (text inline as utf-8, images as img, PDF as iframe) and download
  served inline with `X-Content-Type-Options: nosniff`; delete is
  user-only; deleting a bot deletes its library files; quota enforced
  before writes; task_events note entries when files land or saves link to
  tasks; `send_to_bot(..., task_id=)` writes `delegated` task events and
  threads task_id through the callee row, step payload and typed result.
  UI: Workspace rail section (Tasks/Library with open-count badges), Tasks
  view (filters incl. active scope, inline create, detail pane with
  progress slider, status buttons, event timeline, assign dropdown),
  Library view (grid, per-agent filter + quota readout, previews, upload,
  delete), per-agent drawer Tasks tab; SSE `turn_end` refreshes workspace
  counts. Verified: **349 tests passing** (14 tasks + 26 library e2e tests
  through the real HTTP bridge + SQLite; path-traversal matrix, quota,
  hash verification, restart persistence, delegation→task linkage,
  task+file org tests), plus live HTTP smoke of every endpoint (create →
  assign → update → delete; upload → preview → download → delete), all
  cleaned back to zero. **Not done**: live model smoke (no keys on this
  host); browser UI not screenshot-verified; tasks/library counts refresh
  only on SSE turn_end (no dedicated task SSE channel); group-member counts
  refresh on group activity too; no zip export/age-tag tooling from the
  original F2 sketch; Routines (F4) remain closed.
- **Fleet F3 — agent-to-agent communication & collaboration (done 2026-11-12)**:
  `send_to_bot(bot_slug, message)` is now a Keel builtin tool (`session.py`
  catalog) whose execution is Fleet-owned (`fleet/tools.py` — `FleetTools`
  subclass of `RealTools` bound per turn). The receiving agent runs its own
  provider, model, notes, history and approval broker via the shared synchronous
  core (`fleet/turn_core.py`); nothing of the caller's authority transfers, and
  the caller's turn blocks until the callee's reply arrives (hard deadline
  `KEEL_FLEET_DELEGATE_TIMEOUT_S`, default 60s; unanswered F1 card for the
  delegation call itself still applies). Depth cap: ≤2 nested delegations
  (`SessionConfig.delegation_chain`); cycle detection on (caller,target) pairs;
  self-delegation refused; callee busy yields `agent_busy`, never a deadlock
  (verified by test). Both conversations record the exchange (callee sees a
  `<fleet-delegation … trust="relayed">` attachment + its own DM rows; caller
  sees a `delegated` payload on the `send_to_bot` step row — rendered as an
  expandable delegation chip in chat). Groups are bounded, backend-validated
  2–3 agents with a shared persistent ledger (`fleet.db` v3: `groups`,
  `group_members`, `group_rows`); a user message fans out once per member per
  round; members keep their own DM isolation (group rounds never write member
  DMs) and their own permissions; no agent-to-agent auto-fan-out. SSE fans
  group rows out over the same channel (`group_id` tag). Verified:
  **309 tests passing** (20 delegation + 14 group tests against the real
  HTTP bridge; depth/cycle/privacy/concurrent/restart/SSE/audit cases
  covered).
  Live: group create/list/message/delete round-trip verified over HTTP with
  no provider keys (clean per-member `not_configured` failures, no crashes).
  **Not done**: live model smoke; Echo remains usable as a deterministic
  delegation/group callee but stays a labeled test engine; cross-group
  orchestration, routines/F4, and F-Screen remain deferred.
- **Fleet F1 — approval cards & permission policies (done 2026-11-12)**:
  `keel/fleet/approvals.py` (broker), schema v2 in `keel/fleet/db.py`
  (`fleet_policies` PK bot+tool always|never; `fleet_approvals` single-use
  cards pending|approved|denied|expired; `fleet_audit` fingerprint-only — no
  raw arguments anywhere), per-bot serial waits off a `threading.Event` (HTTP
  threads never block), 5-minute unanswered-card timeout (env override
  `KEEL_FLEET_APPROVAL_TIMEOUT_S`), restart sweep that expires pending cards
  closed and records `decision=restart` in audit. Fleet approvals convert only
  Keel's `consent_required` verdict — deny rules, hooks and Tier 2 are never
  revisited (test: a fleet-approved `.env` write is still refused by Tier 2).
  Subagents inherit the gate via `approval_decider`/`approval_audit` on
  `SessionConfig`. Enforced in `session.py`'s tool boundary; outcomes written
  to audit by the fleet closure. `Task` cards mention the subagent may itself
  use tools; MCP `mcp__server__tool` calls get a card too. UI: inline cards in
  chat (Don't allow · Allow once · Always allow), superseding rows re-render
  in place, Permissions drawer tab (standing policies + revoke + recent
  decisions), `keel` webapp serves them over the existing tokenized bridge.
  Verified: **275 tests passing** (15 new end-to-end approval tests through
  the real HTTP bridge + 2 direct boundary tests), live endpoint semantics
  (400 bad decision / 404 unknown id / 409 already-decided) smoke-checked
  against a throwaway instance; the live browser flow was not
  screenshot-verified on this host. **Not done**: command-level policy
  granularity (`run_shell(git *)`), per-path rules, approval of `read_file`
  class tools (auto-allow by design), dormancy detection for a closed browser
  tab (expiry is the enforcement), policy revoke confirmation, and F3's
  agent-to-agent gate interplay (shipped as part of F3 — see next entry).
- **Fleet F0 (done 2026-11-12)**: `keel fleet` — `src/keel/fleet/` +
  `desktop/fleet/`. Persistent roster (`fleet.db`), Echo test bot wired through
  the real turn loop (user → steps → `turn_end`), SSE row stream, Studio/Engine/Notes
  panels. 250 tests. Detailed scope + next slices in `docs/FLEET-ROADMAP.md`.
- **Phase D route 2 — website + PWA (done 2026-11-12)**: `keel serve` — local
  webapp on 127.0.0.1:8739 (`src/keel/webapp.py`): serves the same `ui/`
  shell, `/api/health` + `/api/providers` + `/api/run` (NDJSON stream-json
  from a real `keel` run), PWA (`manifest.webmanifest` + `sw.js` +
  192/512 icons), tokenized URL + SameSite=Strict cookie, origin checks on
  POSTs, test_webapp.py + test_webapp bridge verified end-to-end. 235 tests.
- **Phase C — Tier 2 (done 2026-11-12)**: `keel/safety.py` —
  the non-configurable post-rule veto. Catastrophic command names refused
  (format/diskpart/mkfs/fdisk/sdelete/initialize-disk/...), protected targets
  refused (secret-bearing paths incl. .env*/keys/.ssh/.aws/.gnupg/.kube/.azure,
  system dirs incl. %SystemRoot%\//etc//boot//usr, raw block devices),
  recursive root/wildcard deletion refused, unparseable shell refused in every
  mode, redirect-into-protected refused. `safety_stops` counter on the
  `result` envelope (verified: 0 in manual consent-denied mode, 1 in
  bypassPermissions). 20 tests incl. the "can Tier 2 be disabled?" matrix.
  Honest limits: Tier 2 is effect-by-command, not taint-aware — a command
  piped through a trusted wrapper that exfiltrates a secret to a remote
  host is out of scope; reg-key granularity (HKLM) not modeled; PS path
  works off the AST, cmd/posix off the lexer.
- **Phase C — MCP (done 2026-11-12)**: `keel/mcp.py` — stdio MCP client,
  newline-JSON-RPC (`initialize`/`tools/list`/`tools/call`/`shutdown`),
  eager start at session init, `mcp__server__tool` naming, 100 KB output cap,
  project-scope servers INERT until `keel mcp approve` (command-shape sha256 in
  `~/.keel/mcp-approvals.json`), approval gate enforced at runner. Tools
  require permission like any other (default = consent-required). Runner
  emits `mcp_servers` on the init event; session routes `mcp__*` to servers.
  Honest limits: stdio only (HTTP/SSE/WS unbuilt); single-line JSON framing
  (no Content-Length headers); no resources/prompts/list-changed; approval
  stores only command-shape, not a parent-dir allowlist; MCP tool permission
  class is `execute` (consent) in manual mode.
- **Phase C — commands (M6 shape, done 2026-11-12)**: `keel/commands.py` —
  print-mode `/help /context /cost /version /doctor` builtins run fully local
  (no model call, `local_command` on the envelope); custom prompt-template
  commands from `.keel/commands/*.md` (`$ARGUMENTS` substitution) run through
  the normal loop; unknown command exits 1 with a hint. Envelope now carries
  `local_command` per spec §9.9.
- **Flaky-test fix (2026-11-12)**: PowerShell AST subprocess now retries once
  on empty/timeout output (parse errors still Decline). A full-suite run had
  intermittently failed `ps-005` under load; suite is green.
- **Phase C — hooks (done 2026-11-12)**: `keel/hooks.py` — command-handler
  hooks (not http/mcp/prompt/agent yet), 33-event open set, matcher filtering,
  `hooks` settings object (deep merge), `hook_started`/`hook_response` events,
  verdict protocol (exit 2 = block with stderr as reason; any other code/timeout/
  crash = proceed + report; ask→deny non-interactive; deny>defer>ask>allow),
  `updatedInput` rewrite with mandatory permission re-validation. Settings
  `hooks` object now folds correctly through the typed resolver (found and fixed
  a real bug there). Live-fired against temp hooks in tests and via a scratch
  settings file — `PreToolUse` blocked a scripted `rm`.

## Honest gaps

- No provider adapter (ScriptedModel only). No two-machine determinism proof.
  No CI (three platform lanes are M14). No Tier-2 (M7), no settings registry
  (Phase 2), no compaction, hooks, skills, MCP, subagents, budgets, or signal
  handling (SIGTERM → 143 unimplemented).
- The `RealTools` executor is deliberately minimal and synchronous; `run_shell`
  uses a 120 s timeout and 5 MB cap with no process-group kill tree (R-02).
- The model never sees a `stop_reason` other than `null`/`end_turn`; streaming
  content blocks are emitted as one event each, unbuffered.

- **Duet — second surface (2026-11-13)**: `fleet-next` gained a `Fleet | Duet`
  top-bar toggle. Duet renders a project-centric coding layout: left panel =
  project picker (paste absolute path; registry in `fleet_projects`, schema v7,
  idempotent migration) + collapsible file tree (skips VCS/deps, 4,000-entry
  cap, depth-first, sorted); right pane = tab strip (add/close, Ctrl+B
  unaffected) with four built-in tabs and unlimited file tabs.

  Verification record (this host; the browser automation tool was removed from
  this environment mid-session, so UI verification is HTTP + pytest + build, not
  screenshots):

  - `pytest` 408/408 green (incl. `test_fleet_ask_user.py`, v7 fresh-schema v7
    assertion, live steps, streaming).
  - Bridge (`python -m keel fleet`) endpoints exercised over HTTP: projects
    create/list/open/remove, tree, file read/write (containment refused an
    escape earlier in development), review (`is_git:false` on a non-repo;
    `true` + real status/log/diffstat on a repo), terminal/exec (`powershell`
    echo captured: `duet-terminal-ok`, `python --version` → `Python 3.11.9`;
    cwd = project root; exit codes recorded), usage aggregation (zeros with no
    prior turns), fork/rewind/restore, shells pill polling.
  - BFF (`/api/bridge/*`): `/projects`, `/usage`, `/shells/*/output`,
    `/projects/<id>/terminal/exec` all proxy correctly; unknown project id →
    `project_not_found` 404, not a crash; write path is POST-only.
  - `next build` clean (types + lint); page chunk contains the Duet strings;
    `/` serves 200; bridge auth gate intact (403 without token).
  - Test data hygiene: scratch project `duet-verify` in `%TEMP%` was created,
    exercised, removed via the remove endpoint (files stay on disk), and the
    scratch dir deleted. Real user data (`hi`, `TEST`, task "do this") untouched
    throughout; schema migration v6→v7 ran against the live DB.

  Honest gaps (all documented in FLEET-ROADMAP.md):

  - No live model turn ever observed (no provider credentials on this host;
    OpenRouter free tier 402/403). ask_user/autopilot/background shells are
    verified with scripted deterministic adapters + HTTP, not with a real model.
  - No PTY; each terminal command is its own detached process (stdin devnull;
    no Ctrl+C forwarding; dev servers work, are not interruptible from the UI).
  - Browser tab = sandboxed iframe; framing-refusing sites (CSP/X-Frame-Options)
    will not render. Not a browser.
  - `/context` reports recorded usage; "remaining context window" is not
    universal and is deliberately not shown as a fake percentage.
  - POSIX shell requires `sh`/`bash` on PATH (absent on this host); powershell
    and cmd always work. The three bug classes found during verification were
    (1) SQLite placeholder/column mismatch dropping `name`, (2) read-vs-POST
    split of the projects subroutes (frontend calls POST; GET silently 404'd),
    (3) `DETACHED_PROCESS` swallowing PowerShell stdout entirely (fixed with
    `CREATE_NO_WINDOW`).

- **Four surfaces + trust gate (2026-11-13)**: `fleet-next` top bar is now
  `Cowork | Code | Duet | Fleet`. Cowork adds hero home, Projects (create/
  trust/remove folders; grid), Artifacts (all agents' library files, iframe
  preview for text/images/PDF, download), Scheduled (templates + New task
  modal + run/pause/delete; Keep awake = real detached PowerShell calling
  `SetThreadExecutionState(ES_CONTINUOUS|ES_SYSTEM_REQUIRED)` — verified in
  its log — and a kill switch), Customize (skills: bundled 21 discovered,
  injection-flag counts shown; connectors: resolved from settings, 0 on this
  host; plugins: explicitly absent). Code adds Environment/Context/
  Connectors rail and Accept edits mode. Trust gate: `fleet_projects.trusted`
  (schema v8, idempotent), POST `projects/<id>/trust`; due-screen prompt is
  shared by Duet/Code/Cowork-new-project flows. Three bugs found by live
  testing and fixed: SQLite placeholder/column mismatch (name NULL), GET/POST
  split of project subroutes (frontend POST 404ed), DETACHED_PROCESS
  swallowing PowerShell stdout (fixed with CREATE_NO_WINDOW), and the
  keep-awake literal wrapping negative (0x80000000) — now `[uint32]2147483649`
  with marker output + a short honest verify loop; PowerShell confirmed via log.
  414 tests green. BFF `/skills`, `/connectors`, `/keep-awake`,
  `/projects/<id>/trust`, `/shells/<handle>/kill` all exercised end-to-end
  through `/api/bridge/*`.

- **Shells pill truthfulness + slash interception (2026-11-13)**: the
  Background shells popover previously listed everything, including Keel's
  own internal keep-awake machinery and finished test processes — it now
  shows real detached work only: the keep-awake loop is hidden from the
  list (`_is_internal`, tested), finished entries remain visible with exit
  codes until cleared, the pill renders only while ≥1 shell is running, the
  popover gained a working "Clear finished" button wired to
  `GET /shells/clear/finished`, and terminal-launched commands (deliberate
  user work) are intentionally visible. Also fixed: every draft starting
  with `/` that names a known command now runs locally instead of hitting
  the provider (previously `/help` with a dismissed palette or `/shell x`
  with arguments was sent as a prompt, ending in provider_error against an
  unconfigured host); unknown `/commands` show a toast, never a model call.
  Verified against the running bridge: 8s detached shell spawned through
  terminal/exec was visible as `running` via `/api/bridge/shells` (BFF),
  reaped to `exit 0` with 12 bytes of captured output, then cleared.
  415 tests green.

- **Axiom glass pass across every surface (2026-11-13)**: the Axiom reference
  mock was applied to the whole product —
  fleet-next app: tokens converted from opaque to translucent Axiom values
  (light + dark), ember orb backdrop drifts behind everything
  (`body::before/after` + a `.glass` field inside the window), window frosts
  to `blur(36px) saturate(1.5)` with an inner edge highlight, layered panels
  (sidebar, top bar, composers, queue panel, shells popover, slash/usage/help
  pops, trust modal, ask cards, artifact previews, project/artifact/template/
  routine/skill/connector cards, rail cards, folder picker) all frosted, and
  display type switched to Space Grotesk. Hierarchy now follows order of
  operations via accordions (`.acc-*`, keyboard-accessible): Recents (open)
  nests an "Earlier" accordion for tasks past the first three, a closed
  "Workspace" accordion carries All chats / Projects / Tasks / Agents /
  Customize, "Quick start" (fleet) and "Ideas for you" (Cowork) collapse
  into their own accordions. Sidebar and Fleet/Cowork nav unchanged
  functionally; 154 UI region call-sites untouched except where accordion
  wrappers were inserted.
  Website + PWA (`desktop/ui`): console rebuilt on the same language —
  ember page background, drifting orbs, translucent top bar/sidebar blocks/
  chat composer/status bar, gold primary actions, Space Grotesk + Inter +
  JetBrains Mono bundled locally (offline PWA intact), theme-color and
  manifest colors moved to the ember palette, service-worker caches bumped.
  Verification: `next build`+prerender clean, `/` 200, BFF smoke 575 B,
  `/manifest.webmanifest` serves new colors; desktop console served from
  `keel serve --port 8743` — `/ui/style.css` 200 with the new tokens, fonts
  200, `keel serve` root 403 without token as designed; 22/22 targeted
  pytest green (webapp + schema + duet bridge). No visual pass was possible
  in this environment (no browser tool); everything verified by inspection,
  build, and HTTP.

- **Top-bar mode switch fixed + reduced to three modes (2026-11-13)**: the
  segmented control overlaid its own labels — flex items were allowed to shrink
  below text width, so button text overflowed and the ember is-active pill
  painted over neighbors (visible as "COWOR|ODE DUET FLEET"). Fix: `.top`
  grid is now `auto minmax(0,1fr) auto`, `.tl`/`.surface-toggle` are fixed to
  content width with nowrap buttons that never shrink; center crumbs truncate.
  Fleet was removed from the toggle per operator request — the three modes are
  Keel Cowork, Keel Code, Keel Duet (the Fleet views remain reachable from the
  sidebar Workspace accordion: Tasks and Agents). Verified: build clean,
  page 200, SSR markup contains exactly the three buttons, BFF smoke OK.

- **Top-bar mode switch fixed + reduced to three modes (2026-11-13)**: the
  segmented control overlaid its own labels — flex items were allowed to shrink
  below text width, so button text overflowed and the ember is-active pill
  painted over neighbors (visible as "COWOR|ODE DUET FLEET"). Fix: `.top`
  grid is now `auto minmax(0,1fr) auto`, `.tl`/`.surface-toggle` are fixed to
  content width with nowrap buttons that never shrink; center crumbs truncate.
  Fleet was removed from the toggle per operator request — the three modes are
  Keel Cowork, Keel Code, Keel Duet (the Fleet views remain reachable from the
  sidebar Workspace accordion: Tasks and Agents). Verified: build clean,
  page 200, SSR markup contains exactly the three buttons, BFF smoke OK.

- **Chat rename / export / delete + New chat one-click (2026-11-13)**:
  sidebar chat rows (fleet view) gained a ⋯ menu on hover / right-click
  (onContextMenu) with Rename… / Export… / Delete…. Rename → PATCH-style
  POST `bots/<id>/update {name}`; Export → NEW `GET /api/fleet/bots/<id>/
  export.md` (text/markdown, Content-Disposition attachment, filename
  `<chat>.md`; running-step rows are intentionally skipped, done/error steps
  kept, turn_end carries duration + in/out tokens); Delete → existing
  confirmed `bots/<id>/delete`. Cowork's `+ New chat` now creates a fresh
  agent (provider engine if any provider is configured, else echo), switches
  to it, and focuses the composer — like Claude's +.
  Verified live over HTTP: create → message → export 200 with correct
  headers and deduped steps → rename → delete → gone; scratch chats cleaned
  up; `hi` / `TEST` / `hi fork` untouched. 415 tests green. Note: a chat in
  Keel IS the agent row — deleting a "chat" deletes that agent and its whole
  transcript (confirm dialog).

- **Project→chat binding + real connectors + MCP startup fix (2026-11-13)**:
  - Opening a project now lands you in ITS dedicated chat. Schema v9
    (`bots.project_id REFERENCES fleet_projects(id) ON DELETE SET NULL`) —
    `chat_for_project()` creates/reuses the bound agent; clicking a project
    calls it (Cowork Projects grid, Duet sidebar, Code sidebar) so you never
    inherit a stale global chat. Deleting a project keeps its chat, unbound.
    Forks inherit project_id. 415 tests green after v9 migration defaulted.
  - Connectors overhauled: presets for GitHub (auth via the user's `gh`
    login — zero token on disk and nothing requested), Filesystem, Memory,
    Sequential-thinking. `GET /api/fleet/connectors` now returns {connectors,
    presets}; POST `/connectors/add` writes ~/.keel/settings.json mcpServers
    atomically; POST `/connectors/test` runs a REAL handshake (initialize →
    tools/list) and reports tool count or the exact error; POST
    `/connectors/remove`. Verified live: github 26 tools, filesystem 16,
    memory 9, sequential-thinking 1 — all handshakes succeed. Deleted/removed
    test artifacts cleaned up; the mis-saved "cmd" entry removed.
  - Real "Add GitHub" browser-backed auth works through the user's existing
    `gh auth login` — no credentials requested or stored.
  - MCP startup was sequential and blocked the first token for ~40s on a hot
    registry (four npm servers); McpManager.start_all now spawns them
    concurrently with the same failure contract — `keel -p` and the test
    suite (which was timing out at 30s) are back under a minute. Slow npm
    handshake is inherent (~10s first run) and is noted honestly.
  - Known remaining issue: on this host `hi`/`hi fork` show OpenRouter 402
    (account out of credits) — real, unrelated to the code.

- **Model-behavior fix — the agent ignored "hi" (2026-11-13)**: three real
  defects stacked into the exact behavior the operator hit.

  (1) **Auto-continue starved the operator**: provider_turn looped
  execute_turn with a continuation prompt whenever a turn hit the round cap,
  and never looked at whether the operator had messaged in the meantime.
  Fixed: the continuation loop checks for any user row with seq > turn-start
  seq and bails the moment the operator speaks — their message is delivered
  instead of replaced by autopilot.
  (2) **Busy-composer dropped messages silently**: sending while a turn was
  running returned without doing anything (no toast, draft stuck). Fixed:
  the composer auto-queues (says so) and queue flushes as soon as the turn
  ends; a 409 from the backend now re-queues instead of losing the text.
  (3) **The model had no life-guidance**: no system instruction told it to
  greet operators who greet it. Fixed: Keel now injects a trusted
  <fleet-guidance> attachment into every fleet turn — operator's latest
  message is authoritative; greetings get greetings; no invented work.
  (4) **posix `ls -la` [WinError 2]** — requested shell was unavailable; the
  agent burned two turns. Fixed: posix falls back to WSL `bash` inside
  Ubuntu (cwd maps correctly, exit code propagated). Verified via probe.
  (5) **MCP connectors actually configured + fast** — user's settings.json
  had a UTF-8 BOM (written by PowerShell), making every read fail silently
  with "connector not configured"; settings.py now reads utf-8-sig. npm
  packages are pre-installed globally and invoked via absolute `node dist/
  index.js` paths instead of npx: handshakes went from ~10-26s each to
  ~0.5-1.1s. Four connectors verified live through bridge: github (26
  tools), filesystem (16), memory (9), sequential-thinking (1).
  (6) 415/415 pytest green after all changes.

- **Vercel deploy of Keel Desktop (2026-11-16)**: the `keel-desktop` Vercel
  project (`losis-projects/keel-desktop`) is now connected to this repo,
  with Root Directory = `keel/site`, Framework Preset = Other, Output
  Directory = `.`, auto-deploys on push to main. Deployed to production and
  live at https://keel-desktop.vercel.app (alias) plus the unique URL.
  All 12 public assets verified 200 (HTML+CSS+JS+SW+manifest+icons+fonts),
  404 router intact. The deployed site is intentionally only the app shell
  — Keel's bridge is not reachable from the internet, by design. Local PWA:
  `keel serve --port 8744` serves the original `desktop/ui` at
  127.0.0.1:8744 with all absolute refs; /api/health 200; verified.

  Verification: `curl` from this machine for all public assets; keel serve
  HTML + JS served; /api/health returns {"ok":true, version}; icons present
  (192/512/256+ico); manifest.webmanifest starts PWA with proper icons and
  theme colors; service worker caches shell.

- **Desktop PWA rebuilt as two surfaces (2026-11-16)**: the installable app
  (`desktop/ui`, service `keel-shell-v3`) is now a single PWA with two
  switchable surfaces — **Keel Desktop** (Cowork-style hero: starburst +
  "You're here." + ideas + folder + composer) and **Keel Code** (coding
  console: start card with "New coding session" / "Autopilot", bottom
  composer, this-computer + permission-mode chips). Both ride the same
  `/api/run` NDJSON bridge, one shared provider/permission config in the
  Customize panel, one session state, one shared recents store (localStorage,
  with pinned entries; stored only on this machine). Interactive send path
  verified against the running 127.0.0.1:8744 instance — the agent replied
  through the pipeline with `model keel-fake-1` (no provider is wired on
  this host, so no live model turn has been observed); UI rendered the
  result honestly. Screenshots verified for both surfaces. Service worker
  re-registered and activated as v3. Local recents list left clean
  (verification entries removed). The public Vercel site is unchanged.

- **Local folder picker + home-chat morph public site (2026-11-16)**:
  the PWA can bind agent tools to any folder on this machine — the bridge
  gained token-gated /api/fs/roots and /api/fs/list (directory names only)
  plus /api/workdir (POST set/clear, GET read; memory only, never disk);
  `/api/run` now spawns keel with cwd=<workdir>. The PWA shows a real
  picker (drives, parent navigation, Use/Reset), a working-in pill on both
  surfaces, and degrades honestly (restart message) against an unrestarted
  keel-serve. Verified end-to-end against a fresh bridge instance: full
  picker flow to "working in: Claude clone".
  The Vercel site is now the Keel Desktop home screen that morphs (composer
  into the pill) into the conversation layout on Enter — mirror-mode
  replies, zero third-party branding. Verified live on
  keel-desktop.vercel.app: zero console errors, morph exercised both ways,
  this-visit prompts stored in sessionStorage only. No live model turn was
  involved; the mirror never claims one.

  NOTE: the keel-serve instance that was already running keeps the old
  bridge code in memory until it is restarted — until then the PWA's
  folder picker shows the restart reminder instead of browsing.

- **Full Settings system in the desktop PWA (2026-11-16)**: a full-window
  settings panel with twelve pages (General, Providers, Usage, Privacy,
  Import & export, Keel Code, Keel Desktop, System, Developer, Skills,
  Connectors, Plugins) — all wired to the local bridge. Keys can now be
  saved on this machine (~/.keel/settings.json, rolling .bak, 0600 best
  effort, last-4 hint in the UI, shell env always wins, authenticated probe
  required before persisting). Model catalogs are fetched live for pinning
  a preferred model per provider; pinned models are passed to /api/run and
  injected as KEEL_*_MODEL for the spawned agent. Instructions set in
  General are prepended to every outbound message. Export excludes keys;
  import merges ui/providerConfig/connectors with a backup kept.
  Verified: 415/415 pytest green; settings save/load roundtrip; export
  secret-free; fake key rejected with HTTP 401; all 12 panes + rail search
  + hydration verified in-browser against an isolated bridge instance
  (temp state dir; real ~/.keel untouched). Requires a keel serve restart
  to take effect.

- **Keel Code footer popovers + folder->session attach, reference rebuild (2026-11-18)**:
  rebuilt the code-surface footer from the user's Claude Code menu reference
  (`claude-code-menus-clone.html`, keel-branded, glass-dark): environment /
  folder / permission chips now open anchored popovers. Environment popover
  is honest (this machine only - WSL/remote are not wired in this build).
  Folder popover lists real recent working folders (searchable, current
  one marked, full path in title) with Enter-to-apply against the bridge's
  validation and an Open folder… path to the full fs picker; the picker
  was verified working against a fresh bridge (typed path -> agent cwd).
  Permission popover maps to the real modes (manual/acceptEdits/bypass);
  bypass stays gated behind the risk checkbox. THE BUG: the installed local
  bridge had died and the PWA pointed at nothing, so "selecting a project"
  silently did nothing - restarted keel fleet (8739), keel serve (8744) and
  fleet-next (3000) with the SAME tokens the installed PWA already holds
  (webapp now accepts KEEL_TOKEN env to preserve tokens across restarts).
  Verified live: typed path -> POST /api/workdir -> label "keel" + pill +
  system note; recents record it; chat surface shows the same pill. Local
  service worker bumped to v4 with network-first navigations.
  Note: the user's installed PWA is the Vercel mirror, which by design
  cannot reach a local bridge - folder-attached sessions only work on
  http://127.0.0.1:8744/?t=<token printed by keel serve>.
  In-flight cleanup: my automated verification session accidentally armed
  bypass mode via stray synthetic clicks; reset to manual BEFORE finishing
  (nothing about it persists - accept-risk is in-memory only, verified).

- **Mirror rebuilt as the local UI, client-side BYOK (2026-11-18)**:
  site/ is now the SAME shell as the 127.0.0.1:8744 app (surfaces, popovers,
  Settings, theme, menus) but with the bridge layer replaced by an entirely
  client-side provider engine. Picks: the mirror cannot and never could reach
  a local bridge from keel-desktop.vercel.app, so the send path streams
  straight from the browser to OpenRouter / Google AI Studio with the key
  saved in Settings -> Providers (localStorage keel_mirror_settings_v1,
  never leaves the browser except to the provider). Local app keeps 415/415
  tests green; the mirror is not executable off-machine against the local
  backend. Honestly degraded panes: folder attach/skills/connectors/import
  say so; no agent runs claimed; manifest stays "Keel - mirror (demo)".
  Verified in an isolated static-server profile: zero console errors,
  send-without-key -> honest note + counters, both providers empty-key
  verify, bogus OpenRouter key -> live 401 surfaced honestly (OpenAI-compat
  SSE path incl. attribution headers exercised), theme toggle, Keel Code
  surface + popovers, mirror-mode notes for folder flows. Streaming success
  path NOT yet observed live (no provider key on this host); SW bumped to
  v7 (network-first navigations).

- **Composer attach menu + attachments on both builds (2026-11-18)**:
  the + (Add) button in both composers now opens a keel-branded menu
  (Attach files… Ctrl+U · Select folder from your desktop…), replacing the
  old "name the file in your prompt" hint. Attachments are read as text
  (File System Access API for folders, caps: 40 files / 256 KB each /
  512 KB total, binaries skipped) and inlined into the next message as a
  read-only context block; the user bubble shows a compact marker, the
  wire prompt carries the content. Verified end-to-end for file attach:
  upload -> chip -> send -> marker in bubble, chips cleared, per-tab
  counters unaffected. Folder path implemented but not machine-verified
  (native picker dialog) - one click in Chrome/Edge confirms.

- **Composer attach, per-surface rules + real upload paths (2026-11-18)**:
  Local app gains POST /api/upload (base64 JSON, token-gated, filename
  sanitized to a basename, capped 24 MB; saved to ~/.keel/uploads/) - the
  agent unpacks/reads attachments itself with its tools (zip via shell).
  Keel Desktop attaches Documents/Images/Spreadsheets/Code files; Keel
  Code attaches anything and "Select folder as workspace" binds the
  agent's cwd via the real disk picker. Attachment uploads now flow
  through the bridge (not inlined); bubble marker lists names. Fixed a
  real routing bug (uploads from Desktop leaked into the Code tray after
  the Keel Code menu had been opened). Mirror build: Desktop restricted to
  docs/images/sheets/code; Code attaches anything - files, images (real
  vision over BYOK: OpenAI-compatible + Google contents inlineData, both
  proven byte-for-byte via intercepted fetch), .zip archives unpacked in
  browser (stored+deflate, text entries become context), folders become
  text context. No agent execution on the mirror, honestly labeled.
  Verified: pytest 15/15 (4 new upload tests), node --check, static-server
  smoke both builds incl. real zip parse (DecompressionStream) and both
  providers' multimodal payloads. Streaming success turn not observable
  (no keys on this host); 401 path verified earlier.
