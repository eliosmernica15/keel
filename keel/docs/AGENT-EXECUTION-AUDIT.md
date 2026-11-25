# Agent C — Agent execution / orchestration audit

**Scope:** Keel Fleet runtime (`keel/src/keel/fleet/**`), shared session/tool
runtime (`keel/src/keel/runner.py`, `keel/src/keel/session.py`,
`keel/src/keel/tools/**`, `keel/src/keel/permissions.py`) and the Fleet UI
(`keel/desktop/fleet/**`). Read-only audit plus two new deterministic test
files. No source files, generated plan files, git state or user data changed.

**Method:** static trace of the authoritative Python paths, cross-checked with
real-runtime tests against an isolated temp SQLite DB and the repo's existing
fake-provider adapter. No live provider, network or user data was used.

---

## 1. One complete execution path (traced end to end)

| Step | Code path | Evidence |
|---|---|---|
| 1. Bot create | `POST /api/fleet/bots` → `FleetStore.create_bot` → INSERT `bots` → `append_row` "notice" | `fleet/routes.py:721-745`, `fleet/service.py:171-220`, `fleet/service.py:635-656` |
| 2. User message | `POST /api/fleet/bots/<id>/messages` validates content (≤32k) and mode, appends a `message` row (role=user), then starts the engine | `fleet/routes.py:1418-1462` |
| 3a. Echo turn | `echo.start_turn` takes the per-bot lock, worker writes 3× (step running/done), assistant `message` (`engine: echo`), `turn_end`, then unlocks | `fleet/echo.py:23-37`, `61-93`, `96-118` |
| 3b. Provider turn | `provider_turn.start_provider_turn` takes the per-bot lock, worker calls `execute_turn`, then unlocks; bounded autonomous continuation on `max_turns`, yielding to a waiting user message | `fleet/provider_turn.py:40-129` |
| 4. Shared turn executor | `execute_turn`: registers cancel event → resolves provider/model → builds `SessionConfig` (permission mode, notes/history/extra attachments, approval decider/audit, delegation chain) → runs `Session` → replays events into rows | `fleet/turn_core.py:207-353`, `383-511` |
| 5. Rows / events | `append_row` commits to SQLite then fans the same dict out to SSE subscribers via `_publish`; token deltas are ephemeral `stream` frames only | `fleet/service.py:635-656`, `127-168`; `fleet/turn_core.py:239-259`; `fleet/routes.py:1727` |
| 6. Approval / ask | At the tool boundary Session consults the approval decider; the broker creates a `fleet_approvals` row + approval card, blocks its worker on an Event; HTTP decide transitions `pending→approved/denied/expired` and sets the Event. `ask_user` writes an `ask` row and blocks up to 300 s; HTTP answer sets its Event | `session.py:972-1007`; `fleet/approvals.py:126-303`; `fleet/service.py:718-782`; `fleet/routes.py:1512-1544`; `fleet/tools.py:267-316`; `fleet/asks.py:22-112`; `fleet/routes.py:1396-1416` |
| 7. Completion / cancel | `result` event → usage row + `turn_end` with `terminal_reason`; Stop sets the per-bot cancel Event, Session skips remaining tools and emits `terminal_reason=cancelled` | `fleet/turn_core.py:466-510`, `43-77`; `session.py:779-796`, `913-917`; `fleet/routes.py:1464-1467` |
| 8. Persistence / history | Rows are committed per event; `list_rows(after_seq)` is the history source for the next turn and for the UI; a fresh `FleetStore` on the same DB sees the same history | `fleet/service.py:635-678`; `fleet/turn_core.py:179-188`; `fleet/routes.py:303-367` |

**Conclusion:** the execution path is real, observable and durable. It is not a
UI mock: the HTTP layer, SQLite, the permission gate, the shared Session loop
and the SSE fan-out all run unmodified in the traced tests.

---

## 2. Verification matrix

| Requirement | Status | Evidence |
|---|---|---|
| Bot create → message → turn → completion | **verified** | `fleet/routes.py:721-745,1418-1462`; `fleet/echo.py:61-93`; new `test_full_execution_path_rows_events_completion_and_history` |
| Delegation (`send_to_bot`) with own identity/history/permissions, depth 2, circular/self refusal, busy fail-fast, hard timeout | **verified** | `fleet/tools.py:178-264`; `fleet/delegation.py:47-95`; `fleet/turn_core.py:352`; `test_fleet_delegation.py` (18 tests) |
| Task assignment (operator + agent), ownership checks, events, hooks | **verified** | `fleet/service.py:976-1265`; `fleet/tools.py:351-484`; `fleet/routes.py:1090-1105`; `test_fleet_tasks.py` (16 tests) |
| Cancellation (per-bot Stop + global kill switch) | **verified** | `fleet/turn_core.py:43-77`; `fleet/routes.py:1464-1467`; `session.py:779-796,913-917`; new `test_cancel_endpoint_signals_active_turn_and_stops_further_rounds`; `test_kill_switch.py` |
| Recovery (restart expiry of approvals/routines; detached delegated turns finish) | **verified for approvals/routines/delegation; partial for asks (A-1)** | `fleet/service.py:50-96`; `fleet/scheduler.py:97-191`; `fleet/delegation.py:85-91`; `test_fleet_approvals.py::test_pending_approvals_are_refused_on_restart` |
| Event delivery (SSE rows + ephemeral stream frames) | **verified** | `fleet/service.py:127-168`; `fleet/routes.py:1727`; `fleet/turn_core.py:239-259`; `test_fleet.py::test_sse_stream_sees_rows`; `test_fleet_streaming.py` |
| History (rows→model context, rewind/restore, reopen) | **verified** | `fleet/turn_core.py:179-188`; `fleet/service.py:596-634`; new reopen assertion in lifecycle test |
| Permission-mode separation (build/plan/autopilot/acceptEdits) | **verified in effect; vocabulary defect A-3** | `fleet/turn_core.py:80-97`; `permissions.py:276-295`; new mode tests |
| Role separation (free-text `role`) | **partial — UI metadata only (A-4)** | `fleet/service.py:171-220,245-286`; `fleet/routes.py:727,738`; no runtime consumer found; new `test_role_does_not_change_runtime_behaviour` |
| `ask_user` cards with clickable options | **runtime verified; UI gap A-5; defects A-1/A-2** | `fleet/asks.py`, `fleet/tools.py:267-316`, `fleet/routes.py:1396-1416`; `fleet/fleet.js:1413-1466` |
| Subagent trust boundary: tool allowlist, worktree isolation, depth/concurrency caps, scanned reports | **not verified for the Fleet `send_to_bot` path** — depth/circular/self caps exist, but worktree isolation, exact allowlists and report scanning were not found in `fleet/**`; the generic `Task` subagent path is covered by `test_subagent.py` | `fleet/approvals.py:57-123`; `fleet/delegation.py:47-95`; plan rule `Keel_Master_Plan_v6.md:1108` |

---

## 3. Gap register

Status legend: **verified** = test + runtime evidence pass; **implemented-unverified**
= code exists but no focused runtime proof here; **partial** = present but
incorrect/incomplete; **blocked** = owner/tooling gate outside this agent.

### A-1 — pending `ask_user` rows are never interrupted on restart — **partial**

- Evidence: `fleet/service.py:104-106` selects
  `WHERE kind='ask' AND json_type(body,'$.status') = '"pending"'`. SQLite's
  `json_type` returns the *type name* `'text'`, never the value `'"pending"'`
  (probe: `json_type('{"status":"pending"}','$.status') -> ('text',)`).
  `expire_pending_asks()` is the only restart handler (`fleet/service.py:70`)
  and therefore always returns 0.
- Impact: after a daemon restart, an in-flight `ask` row stays `status=pending`
  forever; the in-memory `AskBroker` entry is gone, so the answer endpoint
  (`fleet/routes.py:1396-1416`) returns 404 and the chat shows an
  unanswerable card.
- Test: `test_pending_ask_is_interrupted_and_reported_on_restart` (xfail,
  non-strict, reason `AUDIT GAP A-1`).
- Exact remaining action: one-line fix in `fleet/service.py:106` —
  `AND json_extract(body, '$.status') = 'pending'` — then remove the xfail
  marker and re-run the test. Owner: whoever owns `fleet/service.py` (Agent B
  territory); Agent C does not mutate that file.

### A-2 — answered asks are never removed from the pending registry — **partial**

- Evidence: `fleet/asks.py:64-71` sets the answer and Event but never pops
  `_pending`; `wait()` (`fleet/asks.py:73-80`) does not pop either;
  `expire_sweep()` (`fleet/asks.py:83-112`) is the only popper and a
  whole-tree grep finds **no caller**. `pending_count()` therefore grows for
  the process lifetime.
- Impact: bounded memory/count leak; no cross-bot leak (answer is still
  scoped by `bot_id`). The UI never calls `get_pending`, so no user-visible
  symptom today.
- Test: `test_ask_answer_is_scoped_to_the_asking_bot` (xfail on the
  `pending_count()==0` assertion only; the scoping assertions pass).
- Exact remaining action: pop the entry in `answer()` after `event.set()`, or
  in `wait()` after reading the answer; alternatively call `expire_sweep()`
  from `FleetStore.__init__`. Remove the xfail and keep the scoping test green.

### A-3 — mode-table `deny` verdict is reported as `ask` — **partial (safe effect)**

- Evidence: `permissions.py:276-295`. `verdict = table.get(op_class, "ask")`;
  the code handles `"allow"` and non-interactive, then unconditionally returns
  `Decision("ask", "mode", ...)` at line 294 — the explicit `"deny"` rows of
  `MODE_DONT_ASK` (`permissions.py:20-27`) are never emitted as a deny.
- Effect: not a safety failure — `session.py:1153+` refuses every non-allow
  decision and fires `PermissionDenied` — but the decision vocabulary and the
  `reason_type` are wrong for plan/readonly modes.
- Test: `test_mode_table_deny_verdict_uses_deny_vocabulary` (xfail);
  `test_plan_mode_blocks_writes_while_default_mode_asks` proves the safe
  observable effect.
- Exact remaining action: add `if verdict == "deny": return Decision("deny",
  "mode", ...)` before the final `ask` return; then remove the xfail.

### A-4 — "role separation" is a UI card only — **partial**

- Evidence: `fleet/service.py:171-220` stores the free-text `role`;
  `fleet/routes.py:727,738` accept it from the create form;
  `fleet/service.py:483,515-516,561` only copy/render it. A grep of every
  `fleet/*.py` file shows `role` used solely as message-role labels
  (`"user"`/`"assistant"`), never as an authorization or tool-surface input.
  UI field: `keel/desktop/fleet/index.html:40` (Studio panel role input).
- Test: `test_role_does_not_change_runtime_behaviour` documents that two
  agents differing only in `role` behave identically.
- Exact remaining action: product decision required — either map `role` to a
  real default permission mode / tool allowlist in `create_bot` and
  `start_provider_turn`, or relabel the UI field as descriptive-only and
  strike "role separation" from the acceptance claim. Not fixable inside an
  audit-only workstream.

### A-5 — no UI card/button for runtime ask and Stop endpoints — **runtime verified, UI blocked**

- Evidence: runtime answer endpoint `fleet/routes.py:1396-1416` and per-bot
  cancel endpoint `fleet/routes.py:1464-1467` exist and are tested. The Fleet
  renderer `keel/desktop/fleet/fleet.js:1413-1466` handles only `message`,
  `step`, `turn_end`, `notice` (`ask` rows fall through to an empty div); a
  whole-file grep finds **no** `/asks/` or `/cancel` request. Delegation chips,
  approval cards, tasks, library and routines *are* wired.
- Impact: an `ask_user` question is invisible in Fleet chat and cannot be
  answered from the UI; per-agent Stop is unavailable in the Fleet UI (the
  main app has a global kill button, `test_kill_switch.py:56-61`).
- Exact remaining action: Agent A (frontend owner) to add an `ask` row
  renderer with option buttons + free-text answer posting to
  `/api/fleet/bots/<id>/asks/<ask_id>/answer`, and a Stop button posting to
  `/api/fleet/bots/<id>/cancel`. Agent C supplies the runtime proof above.

### A-6 — Fleet `send_to_bot` subagent trust-boundary rules are incomplete — **implemented-unverified**

- Evidence: depth cap 2, circular/self/empty-target refusal, per-bot busy
  fail-fast and hard timeout are real (`fleet/tools.py:207-230`,
  `fleet/delegation.py:52-91`). Not found in `fleet/**`: exact tool allowlist
  per delegated target, worktree isolation, and scanning of child reports for
  instruction-shaped text required by `Keel_Master_Plan_v6.md:1108`.
  Generic `Task` subagents do have isolation/hook coverage (`test_subagent.py`).
- Exact remaining action: decide whether Fleet delegation is meant to satisfy
  plan rule 10; if yes, thread an allowlist/worktree/report-scan through
  `run_delegated_turn` and add tests. Owner: Agent B or lead product decision.

### A-7 — mid-stream cancellation is intentionally not wired — **verified limitation (not a defect)**

- Evidence: `ProviderModelClient` accepts `cancel_event` for mid-stream abort
  (`providers/model_client.py:18-34,73-75`) but `fleet/turn_core.py:316-318`
  does not pass it; `cancel_active_turn`'s docstring states the in-flight
  stream completes (`fleet/turn_core.py:56-62`). New cancel test proves no
  second round-trip is issued after Stop.
- Exact remaining action: none, unless product wants mid-stream abort; then
  pass `cancel_event=cancel_ev` at `turn_core.py:316-318`.

### A-8 — runtime endpoints without UI affordances — **observation**

- `fork`, `rewind`, `restore` (`fleet/routes.py:1346-1394`) and usage/cost
  rows (`fleet/turn_core.py:469-486`, `fleet/service.py:784-823`) have no
  Fleet UI call (`fleet.js` grep). Behaviour is real; only discoverability is
  missing. Owner: Agent A if in scope.

---

## 4. Tests added and exact output

New files (exclusive ownership):

- `keel/tests/audit_agent_execution_lifecycle.py` — 4 tests (full path + SSE +
  reopen, role-only metadata, mode normalization, mode gate effect + A-3 xfail)
- `keel/tests/audit_agent_execution_control.py` — 6 tests (per-agent Stop
  against a gated fake provider, Stop with no active turn, ask answer scoping
  + A-2 xfail, ask timeout fail-closed, restart expiry + A-1 xfail)

All state is written under pytest `tmp_path`; provider responses come from an
in-process `GatedAdapter`; `KEEL_FLEET_STATE` is redirected to `tmp_path`.

Targeted command and result:

```
$env:PYTHONPATH = 'keel/src'
python -m pytest -q keel/tests/audit_agent_execution_lifecycle.py keel/tests/audit_agent_execution_control.py -rxX
....x..x.x                                                               [100%]
=========================== short test summary info ============================
XFAIL keel\tests\audit_agent_execution_lifecycle.py::test_mode_table_deny_verdict_uses_deny_vocabulary - AUDIT GAP A-3: permissions.py:294 returns Decision('ask', ...) for every non-allow mode-table verdict, including the explicit 'deny' rows of MODE_DONT_ASK (permissions.py:276-295).
XFAIL keel\tests\audit_agent_execution_control.py::test_ask_answer_is_scoped_to_the_asking_bot - AUDIT GAP A-2: AskBroker.answer() never pops _pending (asks.py:64-71) and expire_sweep() has no caller; the answered ask stays pending for the process lifetime.
XFAIL keel\tests\audit_agent_execution_control.py::test_pending_ask_is_interrupted_and_reported_on_restart - AUDIT GAP A-1: service.py:106 filters with json_type(body,'$.status') = '"pending"' but json_type returns 'text'; pending asks are never interrupted on restart.
7 passed, 3 xfailed in 9.42s
```

Regression check with the existing fleet/kill-switch suites (same command,
plus the ten listed existing files):

```
........................................................................ [ 69%]
.........................x..x.x                                          [100%]
100 passed, 3 xfailed in 151.84s (0:02:31)
```

The three xfails are **non-strict** and each carries a gap ID, so a future fix
turns them into XPASS (visible, not a failure) until the marker is removed.

---

## 5. Scope and limitations

- Only `keel/docs/AGENT-EXECUTION-AUDIT.md` and the two
  `keel/tests/audit_agent_execution_*.py` files were created. No git operation
  was performed.
- Findings A-1/A-2/A-3 are real source defects but were not fixed here because
  source files are outside this agent's exclusive ownership; they are handed
  off with exact one-line actions above.
- The audit did not launch real providers, open the desktop app, or exercise a
  browser; UI gap A-5 is established by static inspection of `fleet.js` and
  `index.html`, not by clicking through a packaged renderer.
- Registry statuses in `PLAN-INDEX.json`/`parity.json` were read, not edited.
  This audit does not change the 854/865 registry claim.
