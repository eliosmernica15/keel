# Addendum 4 — Session / event-model contracts (D2.x): implementation evidence

Branch: `agent/a4-events` (worktree `.../worktree/addenda/events`)
Baseline: `fa062a4`, read-only.
Source of requirements: `PLAN-INDEX.json` → `features[]`, IDs
D2.1, D2.3, D2.5, D2.7, D2.8, D2.9, D2.10, D2.11, D2.13, D2.15, D2.16
(11 P0 items, milestones M4/M5/M7/M8/M10/M11/M19).

This workstream is **additive**. No existing file was edited: `session.py`,
`events.py`, `transcript.py`, `session_export.py` and every pre-existing test
are untouched. The canonical implementation lives in a new module and is
exercised by a new, permanent contract-regression test file. Integration into
the live runtime is a separate lead decision (exact seams listed at the end).

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/session_contracts.py` | Canonical implementation of all 11 D2.x contracts (stdlib only, no I/O side effects at import). |
| `keel/tests/test_session_contracts.py` | 32 permanent contract tests, one or more groups per registry ID. |
| `master-plan-v6-session-contracts-evidence.md` | This document. |

## Contracts implemented

| ID | Registry requirement | Primary symbols | Tests |
| --- | --- | --- | --- |
| D2.1 | Three event domains; typed Event with seq/domain/kind/payload_hash | `EventDomain`, `Event`, `make_event`, `EventBus` (broadcast / per-agent / intercept / transient-not-durable) | `test_event_domains_*`, `test_payload_hash_*`, `test_event_bus_*` (4) |
| D2.3 | step = model request + its tool calls; turn = zero or more steps; full lifecycle | `TURN_LIFECYCLE`, `Step`, `Turn`, `ToolCall`, `group_into_turns` | `test_lifecycle_*`, `test_group_events_*`, `test_group_into_turns_*` (3) |
| D2.5 | One inbox per driver; `inject()` waits for waking message; deterministic wake order; tainted by source | `InjectionSource`, `TAINTED_SOURCES`, `Injection`, `AgentInbox`, `InboxRegistry` | `test_inbox_inject_*`, `test_injection_wake_order_*`, `test_admitted_injection_*` (3) |
| D2.7 | System prompt as logged `system/message` history; empty text clears | `SessionJournal.set_system_prompt`, `SessionJournal.system_prompt` | `test_system_prompt_logged_history_and_empty_clears` (1) |
| D2.8 | Cancellation during prompt preparation commits nothing | `StepPreparation`, `CancelledDuringPrepare` | `test_cancellation_during_prepare_*`, `test_successful_prepare_*` (2) |
| D2.9 | Failed steps record synthetic missing tool results | `missing_tool_results`, `repair_missing_tool_results`, `SessionJournal.close_failed_step` | `test_failed_step_records_*`, `test_repair_missing_*` (2) |
| D2.10 | Process-local live stream frames vs durable settled message; attempts kept without model history | `StreamFrame`, `StreamBuffer`, `settle_assistant`, `SessionJournal.record_attempt` | `test_stream_frames_*`, `test_attempts_do_not_*` (2) |
| D2.11 | Model-visible ⇔ logged; replay reproduces exact request bytes (hash); raise if new field invisible | `ModelRequest`, `build_request`, `MODEL_VISIBLE_FIELDS`, `register_model_visible_field`, `assert_request_is_reconstructible`, `reconstruct_model_requests`, `SessionJournal.admit_request` | `test_replay_reproduces_*`, `test_invisible_new_field_*`, `test_unlogged_projection_*`, `test_transient_domains_*` (4) |
| D2.13 | Versioning: header-only stat/list, highest readable generation, adjacent migrations, immutable generations, bounded restart repair, `.zstd` | `write_session`, `read_header`, `stat_session`, `list_sessions`, `read_session`, `write_successor`, `migrate_adjacent`, `migrate_events`, `register_codec`, `repair_interrupted_turn` + 5 typed errors | `test_version_migration_*`, `test_header_stat_*`, `test_read_open_*`, `test_write_successor_*`, `test_interrupted_turn_*`, `test_compressed_*`, `test_unsupported_compression_*` (7) |
| D2.15 | Fork at turn boundary; seeded, inherited event count, only agent-loop events migrate, deterministic | `fork`, `ForkedSession`, `NotATurnBoundaryError` | `test_fork_at_turn_boundary_*`, `test_fork_filters_*` (2) |
| D2.16 | Working dirs give context/execution paths without changing project identity, write roots or cwd | `WorkingDirectory`, `DirectoryContext`, `WorkingDirectoryError` | `test_working_dir_is_metadata_only`, `test_working_dir_validation_*` (2) |

Total: **32 tests**, all passing (repeated 3× — stable, no timing flake).

## Design decisions worth the lead's attention

1. **Hashes commit to content, never to time or uuid.** `Event.payload_hash` and
   `ModelRequest.request_hash` are SHA-256 of canonical JSON (`sort_keys`,
   compact separators, UTF-8). Seq is assigned by the journal at commit time,
   so replay is byte-stable regardless of when it runs (D2.11).
2. **Domain modes are structural.** `EventBus.publish` broadcasts SESSION
   events to all subscribers and the journal; AGENT events are delivered only
   to listeners for that `agent_id`; PROVIDER/UI events are transient and are
   never appended. An intercepting listener may return a replacement Event;
   observers return `None` (D2.1, extends C5.5/Y2.1).
3. **Injections are invisible until admitted.** `inject()` queues WAITING text;
   only `admit()` promotes it to ADMITTED and logs an `agent/injection`
   *SESSION* event. `ModelRequest` automatically materialises admitted
   injections as model-visible messages (with dedup during replay), so a
   caller cannot build a request whose hash replay cannot reproduce. Wake order
   is `(wake_seq, seq)`; ties resolve by agent id in `InboxRegistry.wake_order`
   (D2.5 + D2.11).
4. **Prepare is all-or-nothing.** `StepPreparation` stages system/user events;
   `commit()` re-checks the cancellation predicate and either appends every
   staged event or none. Cancellation can never leak a partial prompt (D2.8).
5. **Replay assembles at `step/end`.** Indices are captured at `step/start`,
   but messages/schema/system are read at `step/end`, so late events (notably
   synthetic tool results) are included. A logged `model/request` hash is
   re-verified against the reconstructed request; a mismatch raises
   `InvisibleModelInputError` (D2.9 + D2.11).
6. **Stream frames never become history.** `StreamBuffer` is process-local;
   `settle_assistant` embeds the compact timed stream into one durable
   `assistant/message`. `assistant/attempt` records are durable but
   `model_visible=False`, so failed/retried/cancelled attempts never enter the
   model history. A crash before settlement leaves no durable message (D2.10).
7. **Versioning is forward-only and adjacent.** Files are
   `<session>.vN.jsonl[.zstd]` with a first-line header carrying version and
   event count, so `stat`/`list` read only that line. `read_session` translates
   v1→v2→v3 in memory; `write_successor` creates vN+1 beside an unchanged
   source using exclusive create (`xb`), so committed generations are never
   renamed, overwritten or deleted. `migrate_adjacent` rejects non-adjacent
   steps with a typed error. Missing `turn/end` is inserted only when a
   released restart is declared, bounded to one turn (D2.13).
8. **Compression is codec-injected.** Python's stdlib has no zstd, so `.zstd`
   support is a registered `(compress, decompress)` pair. Without a
   registration, `codec_for` raises the typed `UnsupportedCompressionError`
   rather than silently treating bytes as plain JSON. A real zstd binding can
   be supplied by the lead with `register_codec(".zstd", ...)` (D2.13).
9. **Fork is deterministic by construction.** `fork(at_turn)` cuts at the
   committed `turn/end`, keeps only `published_by == "agent_loop"` events,
   renumbers them from 1, and records `inherited_event_count`. Later ids derive
   from `(seed, next_seq, label)` via SHA-256 — no uuid, no rng (D2.15).
10. **Working dirs are pure metadata.** `DirectoryContext.with_working_dir`
    replaces only `working_dir`/`metadata`; it asserts that `project_id`
    (hash of the normalised project root), `write_roots` and `process_cwd` are
    unchanged. `execution_path()` is a string join against metadata; no
    `os.chdir` occurs anywhere (D2.16).

## Test results

Command (from worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_session_contracts.py']))"
```

Result: `32 passed` (3 consecutive runs: 0.82s / 0.28s / 0.29s). Python 3.11.9,
pytest 9.0.2. `py_compile` clean on both new files.

## Exact integration seams needed by the lead

This module is deliberately not wired into `keel/session.py`, `keel/events.py`,
`keel/transcript.py`, `keel/session_export.py` or any agent driver. To adopt
it, the lead should make these changes (none are required for the tests above
to pass):

1. **`keel/events.py` / session `emit()`** — construct `Event` records via
   `make_event(kind, payload, ...)` and publish through `EventBus` instead of
   appending raw dicts; attach `SessionJournal` to the bus so SESSION events
   are durably committed once, in order.
2. **`keel/session.py` loop (D2.3/D2.8/D2.9)** — wrap prompt assembly in
   `StepPreparation` (cancel event → `is_set`); emit the `TURN_LIFECYCLE`
   stages as logged events; replace the current "provider error" path with
   `journal.close_failed_step(step_index)` so orphaned tool calls get synthetic
   results; use `SessionJournal.turns()` / `group_into_turns()` for turn counts
   and replay.
3. **System prompt (D2.7)** — route persona/attachment text through
   `journal.set_system_prompt(text)` (empty text clears) rather than folding it
   into the first user message, then rebuild the model input from the journal.
4. **Model client (D2.11)** — before `model.complete`, call
   `journal.admit_request(build_request(...))` with the exact model, system,
   messages, tool schemas and admitted injections; pass `request.canonical_bytes()`
   to the transport (or hash-check the transport's bytes). Register a pure
   projection with `register_model_visible_field` for any new model-visible
   field (attachments, redaction markers, model selection snapshots).
5. **Agent drivers / hooks / plugins (D2.5)** — give each driver an
   `InboxRegistry.inbox(agent_id)`; `agent.inject(text, source)` enqueues and
   `admit(agent_id)` is called once at the next admitted request; map the
   existing `tool_contracts.SourceKind` vocabulary onto `InjectionSource` so
   taint follows the source.
6. **Streaming UI (D2.10)** — UI reads `StreamBuffer` frames for
   `assistant-stream` start/chunk/end; on settlement call `settle_assistant`;
   on failure/retry/cancel call `record_attempt`. Transcripts/replays must use
   only durable `assistant/message` events.
7. **Session export/import (D2.13)** — use `session_path`/`write_session`/
   `read_session`/`list_sessions` for `session.vN.jsonl.zst` bundles; register
   a real zstd codec via `register_codec`; replace in-place rewrites with
   `write_successor` so older generations stay readable. SQLite schema
   migrations remain forward-only and unrelated to this file format.
8. **Branching (D2.15)** — branches (Master 9.1) call `fork(journal, at_turn,
   seed=...)` and adopt `ForkedSession.inherited_event_count` as the seed for
   subsequent event numbering.
9. **Directory context (D2.16)** — add a `DirectoryContext` alongside
   `SessionConfig`; pass working directories as context/execution metadata to
   tools, and keep `project_root`, `write_roots` and `os.getcwd()` untouched.

No change to `keel/tool_contracts.py` is required: that module governs tool
pipelines; this one governs the session/event model.
