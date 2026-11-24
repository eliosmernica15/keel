# Y2 backend contracts (remaining P1 rows): implementation evidence

Branch: `agent/b2-y2` (worktree `.../worktree/backend/b2-y2`)
Baseline: `982335d4085b40be680bb0bd0a31c6e764d7c566`, read-only except the three
files owned by this workstream.
Source of requirements: `PLAN-INDEX.json` -> `features[]`, every **not_started**
Y2.x row. There are 25 Y2 rows in the index: 10 are already `verified` and
15 are `not_started`. All 15 not_started rows are P1 (two were originally P0:
Y2.24; the remaining P0 rows are the ten verified ones).

This workstream is **additive**. No existing source file, test, web page or CLI
file was edited: `keel/transcript_contracts.py` (the P0 implementation),
`keel/transcript.py`, `keel/session.py`, `keel/webapp.py`, the CLI and every
pre-existing test are untouched. Integration into the live runtime is a
separate lead decision (seams listed at the end). No frontend was added.

## Files owned

| File | Purpose |
| --- | --- |
| `keel/src/keel/y2_backend.py` | Canonical stdlib-only implementation of all 15 remaining Y2 backend contracts. No import-time I/O, no uuid/random, no network/socket. |
| `keel/tests/test_y2_backend.py` | 41 permanent contract tests (one ID-coverage guard plus one or more groups per registry ID). |
| `master-plan-v6-y2-backend-evidence.md` | This document. |

## P0 rows: verify / document (no code change)

The ten not_started **P0** Y2 rows were already implemented in a previous
addendum and are `verified` in `PLAN-INDEX.json`:

| ID | Requirement | Canonical module | Test |
| --- | --- | --- | --- |
| Y2.1 | Typed append-mostly transcript rows | `keel.transcript_contracts` | `test_transcript_contracts.py` |
| Y2.2 | Model history stored separately | " | " |
| Y2.3 | Last N screenshots inline (N=3) | " | " |
| Y2.4 | Orphaned tool-call repair | " | " |
| Y2.5 | Per-agent serial queue | " | " |
| Y2.6 | Pending-turn persistence | " | " |
| Y2.7 | Allow / Always allow / Don't allow | " | " |
| Y2.8 | Read-only tool classification by slug | " | " |
| Y2.14 | Credential-free VNC relay | " | " |
| Y2.20 | Least-exposure defaults | " | " |

Verification performed in this worktree at baseline (no edits):
`python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_transcript_contracts.py']))"`
-> **39 passed**. The ten P0 rows need no further backend work here and are
not duplicated in `y2_backend.py`.

## Contracts implemented (15 not_started P1 rows)

| ID | Registry requirement | Primary symbols | Tests |
| --- | --- | --- | --- |
| Y2.9 | Card row kinds `approval`/`question`/`connect`/`draft`; event rows for routine/voice/group changes and `notice`; row-kind registry in the UI component list (9.2) | `RowKindRegistry`, `RowKindSpec`, `RowFamily`, `CardKind`, `EventKind`, `DEFAULT_ROW_KIND_REGISTRY`, `DEFAULT_ROW_KIND_SPECS`, `RowKindError` | `test_row_kind_registry_*` (3) |
| Y2.10 | `stay_silent` (do not answer an unaddressed group message) and `request_app_connection` (connect card that opens the connector form) | `CollabToolRegistry`, `TOOL_STAY_SILENT`, `TOOL_REQUEST_APP_CONNECTION`, `should_stay_silent`, `request_app_connection`, `ConnectCard`, `ToolResult`, `parse_mentions` | `test_stay_silent_*`, `test_request_app_connection_*`, `test_collab_tool_registry_*` (3) |
| Y2.11 | `send_to_bot` messaging, hidden child agents with own context/screen removed by `stop_subagent`, group rooms capped at 3 responders with @mention routing and loop guards (A2.5) | `send_to_bot`, `BotMessage`, `SubagentManager`, `Subagent`, `GroupRoom`, `GroupRouting`, `post_to_group`, `GROUP_RESPONDER_CAP` | `test_send_to_bot_*`, `test_hidden_subagents_*`, `test_group_room_*` (4) |
| Y2.12 | One VM, up to four desktops, leased least-recently-used among idle agents | `DesktopPool`, `ScreenLease`, `MAX_DESKTOPS`, `ScreenLeaseError` | `test_screen_pool_*` (2) |
| Y2.13 | Idle suspend knobs: 20 min default, 60 s sweep, dry-run logging without acting; settings | `ResourceManager`, `SuspendDecision`, `DEFAULT_IDLE_SUSPEND_SECONDS`, `DEFAULT_SWEEP_INTERVAL_SECONDS` | `test_idle_suspend_*`, `test_dry_run_*`, `test_real_sweep_*` (3) |
| Y2.15 | ~600 control calls/min per computer token bucket; in-VM executor seam (C1.11) | `TokenBucket`, `RateLimiter`, `RateDecision`, `DesktopAction`, `ExecutionReceipt`, `ExecutorSeam`, `RecordingExecutorSeam`, `InVmExecutor` | `test_token_bucket_*`, `test_rate_limiter_*`, `test_in_vm_executor_*` (3) |
| Y2.16 | Compaction knobs: trigger size, keep-last-4-user-turns verbatim, method `auto\|summary`, 10 min idle consolidation / 60 s sweep, 4,000-char prompt memory budget | `CompactionConfig`, `CompactionMethod`, `Turn`, `CompactionPlan`, `plan_compaction`, `DEFAULT_*` constants | `test_compaction_*` (3) |
| Y2.17 | Prompt cache key per agent+generation; hashed user id as safety identifier; raw identifiers never sent | `prompt_cache_key`, `local_prefix`, `safety_identifier`, `build_provider_identity`, `ProviderIdentity`, `assert_no_raw_identifier` | `test_prompt_cache_key_*`, `test_safety_identifier_*` (2) |
| Y2.18 | `NO_SCHEDULER` flag so extra dev servers sharing a DB do not double-fire jobs (`--no-scheduler` / `KEEL_NO_SCHEDULER`) | `parse_scheduler_flag`, `SchedulerConfig`, `strip_no_scheduler`, `should_run_scheduler`, `NO_SCHEDULER_ENV`, `SchedulerFlagError` | `test_no_scheduler_*` (2) |
| Y2.19 | Backward-compatible rename: old env names fallback, old DB filename kept, old cookie accepted, guarded symlink for the renamed data dir | `RenameCompat`, `CompatRenames`, `CompatReport`, `RenamePathError` | `test_env_and_cookie_*`, `test_database_path_*`, `test_compat_symlink_*` (3) |
| Y2.21 | Honest "Project status": tested vs built-not-proven, "basic review, not professional audit", known browser/shell approval gap; feeds A3.7 About | `build_project_status`, `ProjectStatus`, `StatusEntry`, `VerificationLevel`, `status_from_plan`, `level_for_status`, `KNOWN_LIMITS`, `AUDIT_DISCLAIMER`, `APPROVAL_GAP` | `test_project_status_*`, `test_status_from_plan_*` (2) |
| Y2.22 | Voice: short-lived realtime secrets, `hand_off_task` relay to the text loop, TTS preview, STT dictation proxy | `RealtimeSecretIssuer`, `RealtimeSecret`, `HandoffRelay`, `HandoffTask`, `TextLoopSeam`, `tts_preview`, `TtsPreview`, `stt_dictation_proxy`, `SttDictation`, `RecordingTranscriptionSeam` | `test_realtime_secret_*`, `test_handoff_task_*`, `test_tts_preview_*` (3) |
| Y2.23 | E2E script over chat/computer/viewer/search/connections/voice/groups/settings with a prepared-audio fixture for the voice harness (A2.8) | `E2EScenario`, `SCENARIO_FULL`, `E2E_SURFACES`, `AudioFixture`, `prepare_audio_fixture`, `voice_harness_fixture`, `run_e2e_scenario`, `RecordingE2EHarness`, `E2EReport` | `test_prepared_audio_*`, `test_e2e_scenario_*` (2) |
| Y2.24 | One per-user SSE stream with typed event kinds (row updates, live state, roster, computer state) | `SSEStream`, `SSEStreamRegistry`, `SSEEvent`, `SSEEventKind`, `DEFAULT_SSE_BUFFER` | `test_sse_registry_*`, `test_sse_reconnect_*` (2) |
| Y2.25 | Routines: cron, event routines from user-configured free connectors, proactive check-ins (A2.6) | `RoutineEngine`, `Routine`, `parse_cron`, `CronSchedule`, `ConnectorEvent`, `RoutineTrigger`, `FiredRoutine`, `make_routine` | `test_cron_parser_*`, `test_event_routines_*`, `test_checkin_cadence_*` (3) |

Plus `test_all_fifteen_feature_ids_have_backend_symbols`, a guard that fails if
any of the 15 IDs loses its implementation. **Total: 41 tests.**

## Design decisions worth the lead's attention

1. **Deterministic identity, injected time.** Every id is a SHA-256 prefix of
   canonical JSON (sorted keys, compact separators, UTF-8, no NaN). No uuid,
   no RNG. Clocks are injectable; time only ever stamps records, never forms
   identity. `test_all_fifteen_feature_ids_have_backend_symbols` enforces full
   ID coverage.
2. **Y2.9 is a registry, not a UI.** `RowKindSpec` couples each kind to the UI
   component that renders it (9.2), a family and the required body fields.
   `make_row` validates then produces a typed, deterministic row; custom kinds
   can be registered but duplicates are rejected. The five base transcript
   kinds are included so clients have one component list.
3. **Y2.10 tools are schemas plus honest handlers.** `stay_silent` returns a
   typed decision (group message that did not @mention the agent and was not
   authored by it -> silent). `request_app_connection` returns a `connect`
   card whose `action` is `open_connector_form` and whose `form` names the
   connector; no form is silently auto-filled.
4. **Y2.11 groups are bounded.** `GROUP_RESPONDER_CAP = 3` is a hard default
   (`post_to_group` defers the rest), a loop guard stops an agent after three
   consecutive replies to its own mention, and `stop_subagent` clears both the
   child's context and its screen while keeping the child hidden.
5. **Y2.12/Y2.13/Y2.15 use counters and buckets, not sleeps.** The desktop pool
   leases the least-recently-*released* idle desktop (monotonic tick, no wall
   clock). Idle suspension defaults to 20 min / 60 s and its dry run *logs but
   never acts*. The 600/min token bucket is per computer and refills from an
   injected clock; a rate-limited `DesktopAction` is never forwarded to the
   C1.11 executor seam.
6. **Y2.16 memory is bounded and honesty-marked.** `plan_compaction` keeps the
   last four user turns verbatim, summarises the rest, and `render_memory`
   truncates to the 4,000-char budget with an explicit `[truncated]` marker.
   `auto` summarises only on a size/idle trigger; `summary` always summarises.
7. **Y2.17/Y2.18/Y2.19 fail closed.** Provider identity carries a hashed
   `user_*` safety id and a stable agent+generation cache key; the raw user id
   never appears. `NO_SCHEDULER` accepts a strict boolean truth table (CLI wins
   over env) and rejects garbage instead of guessing. Rename compatibility
   reads old names only as fallbacks, keeps an existing old DB filename, and
   refuses a compat symlink that resolves outside its base.
8. **Y2.21/Y2.22/Y2.23 do not fabricate evidence.** The status section separates
   *tested* from *built-not-proven* and always prints the audit disclaimer, the
   browser/shell approval gap and the known-limits list. TTS returns a preview
   descriptor with no audio bytes; STT hashes real bytes and returns no
   invented transcript; realtime tokens are short-lived and redacted by
   default. The E2E harness distinguishes `recorded` from `passed`, and voice
   steps require a real deterministic WAV fixture built in memory.
9. **Y2.24 streams are bounded and replayable.** One `SSEStream` per user with
   four typed kinds; `drain(since_id)` supports reconnect replay, and the
   1,000-event buffer eviction is tracked with `oldest_id`/`next_id` so a client
   can detect a gap instead of silently missing events.
10. **Y2.25 connectors are opt-in.** A cron expression is validated and matched
    locally; an event routine only fires when its connector is in the
    user-configured free set; check-ins advance their own last-fire time. A
    trigger that is not due cannot be fired.

## Test results

Command (from worktree root, as required):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_y2_backend.py']))"
```

Result: **41 passed** on three consecutive runs (5.65 s / 3.70 s / 3.08 s).
P0 regression suite `keel/tests/test_transcript_contracts.py`: **39 passed**.
`py_compile` clean on both new Python files. Python 3.11.9, pytest 9.0.2.
No existing test file was modified.

## Exact integration seams needed by the lead

This module is deliberately not wired into the live runtime. To adopt it:

1. Y2.9: expose `DEFAULT_ROW_KIND_REGISTRY.to_dict()` as the UI component list;
   route card/event `make_row` output through `keel/events.py`.
2. Y2.10: register `TOOL_STAY_SILENT`/`TOOL_REQUEST_APP_CONNECTION` with the tool
   registry and render `ConnectCard.to_dict()` as the connect form trigger.
3. Y2.11-Y2.13: wrap agent turn intake in `GroupRoom`/`SubagentManager`, route
   group posts through `post_to_group`, and bind `DesktopPool`, `ResourceManager`
   and `RateLimiter` into the desktop lifecycle (dry_run from settings).
4. Y2.15-Y2.17: replace `ExecutorSeam` with the C1.11 in-VM executor; pass
   `CompactionConfig` from settings into the context manager; send
   `build_provider_identity(...).to_dict()` to remote providers (never the raw
   user id) and use `local_prefix` for local servers.
5. Y2.18-Y2.19: call `parse_scheduler_flag(sys.argv[1:], os.environ)` at startup
   and skip job registration when `should_run_scheduler` is false; call
   `RenameCompat` during config/DB/session migration.
6. Y2.21-Y2.23: feed `ProjectStatus.to_about_payload()` to the A3.7 About page;
   use `RealtimeSecretIssuer` for voice sessions and `HandoffRelay` for the
   text loop; wire the E2E scenario to a real harness and use the prepared WAV
   fixture for the voice harness.
7. Y2.24-Y2.25: serve `SSEStream` frames from per-user connections and register
   routines in the scheduler with `RoutineEngine.evaluate(...)`.

## Per-ID traceability: ID → implementing symbols → behavioral test

The compaction-knobs ID is declared in `FEATURE_TRACEABILITY` in
`keel/src/keel/y2_backend.py` (AST-visible string key mapping to real symbols).
This row names the concrete definitions and the concrete behavioral test
functions in `keel/tests/test_y2_backend.py`; it is the per-ID cross-check
consumed by `scripts/verify_backend_operation.py`.

| ID | Implementing symbols (`keel.y2_backend`) | Behavioral test function |
| --- | --- | --- |
| Y2.16 | `DEFAULT_KEEP_LAST_USER_TURNS`, `DEFAULT_MEMORY_BUDGET_CHARS`, `CompactionConfig`, `CompactionMethod`, `plan_compaction` | `test_compaction_defaults_and_method_validation`, `test_compaction_keeps_last_n_user_turns_and_bounds_memory`, `test_compaction_idle_consolidation_and_summary_method` |

All other Y2 IDs already passed the evidence gate; no registry row status was
changed and no other module was modified.
