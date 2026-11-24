# E7 backend implementation evidence (36 `not_started` rows)

**Branch:** `agent/b1-e7` · **Baseline:** `982335d`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\backend\b1-e7`

## 1. Scope and registry reading

`PLAN-INDEX.json` contains 43 `E7.*` rows: 7 `verified` and **36 `not_started`**.
All 36 open rows were read in full (feature text, `detail`, milestone, priority,
dependencies, `owner_approval_required`, `external_prerequisite`,
`known_limitations`, `source_document`, `implementation_tier`). Findings:

* every open row comes from `Keel_Plan_v5_Addendum_7_DeepSeek_Deep_Reads.md`,
  section 8 ("Seam map: services DeepSeek has that Keel's plan lacks");
* every open row has `implementation_tier: local_module`, an **empty**
  `source_files` list, `owner_approval_required: false` and an empty
  `external_prerequisite`;
* the 7 already-`verified` rows (`E7.2`, `E7.6`, `E7.18`–`E7.21`, `E7.23`) are
  implemented in the pre-existing `keel/runtime_contracts.py` and were **not**
  touched, re-implemented or re-counted here;
* three rows carry the limitation "Unverifiable reference claim; treat as
  unproven until native/source evidence exists" (`E7.17`, `E7.29`, `E7.33`).
  Their host-side policies are implemented and tested, but no claim is made
  that a native reference implementation was observed (see §5).

**Classification result: 36 classified · 36 implemented (backend) · 0 whole IDs
excluded.** Every open row is a service/seam whose host half has observable
behavior (fold, authorize, rank, validate, reconcile, bound, audit). The
frontend delivery halves, external engines and other owners' seams are listed
as *sub-scope exclusions* per ID in §3 and are explicitly not claimed.

## 2. Files owned (only these were added)

* NEW `keel/src/keel/e7_runtime_backend.py` (3,138 lines, stdlib only)
* NEW `keel/tests/test_e7_runtime_backend.py` (1,073 lines, **79 tests**)
* NEW `master-plan-v6-e7-backend-evidence.md` (this file)

No existing source, test or registry file was modified. `PLAN-INDEX.json` was
read only; no status was changed here.

## 3. Per-ID classification, implementation and sub-scope exclusions

"Backend" means the row's core is a host-side policy/descriptor, not a view or
a documentation task. "Excluded" is always a *part* of a row (a UI panel, a
third-party engine, or a seam owned by another ID); no whole ID was dropped.

| ID | Registry feature (short) | Class | Implemented in `e7_runtime_backend.py` | Excluded / not claimed |
| --- | --- | --- | --- | --- |
| E7.1 | tokenMeter: isolated per-session replay folds; immutable revisioned measurements | backend | `TokenMeasurement`, `PressureMeasurement`, `TokenMeter.fold/replay/latest/pressure_measurement`; negative/mixed-type counts fail closed, replay equals fold, sessions isolated | None |
| E7.3 | compaction reacts to post-step pressure and request-error recovery; no model-facing compact tool | backend | `PressureEvent`, `compaction_decision`, `assert_no_compact_tool`; user/loop events distinguished, recovery produces `COMPACT_AFTER_RECOVERY` | Actual transcript compaction/truncation engine |
| E7.4 | reading acks and manual unread marks outside session history | backend | `SessionStatusStore.acknowledge/mark_unread/mark_read`, `assert_status_out_of_log`; acks monotonic, manual mark sticky | Session-list UI/unread dot |
| E7.5 | per-turn changed-file summaries by session + event seq; log carries only the turn | backend | `WorkspaceSnapshot`, `WorkspaceChangeFeed`, `assert_log_carries_turn_only`; add/modify/remove diff, turn ordering | "Changes this turn" panel (D3.12) |
| E7.7 | `@` path completion returns paths only, never contents | backend | `path_completions`, `assert_paths_only`, `parse_at_paths`; content keys and traversal rejected | Composer rendering |
| E7.8 | `@session` mention embeds bounded snapshot as untrusted context | backend | `resolve_session_reference`, `assert_untrusted_context`, delimiter escaping, redaction, char/message caps | Mention picker UI |
| E7.9 | sessionQuery: exact reads, filters, traces, FTS ranking, snippets, cursors | backend | `SessionQueryService`; deterministic ranking/snippets, opaque generation-bound cursors, tampered cursor fails closed | Search results view; real SQLite FTS5 index |
| E7.10 | sessionTitle: deterministic fallback, latest fold, one async provider | backend | `fallback_title`, `TitleService` with single provider registration and first/all-prompt modes; provider failure falls back | Provider network transport |
| E7.11 | planMode folded from log, boundary flush, `/plan`, stable exit schema | backend | `PlanModeService.fold/queue_selection/flush/plan_command/exit`, `plan_exit_schema` | Plan guidance renderer |
| E7.12 | agentPresets revisions; retired revisions kept until last user releases | backend | strict `parse_preset_yaml`, `PresetRegistry.publish/retire/bind/release`; last-release GC and pinned composition | YAML file loader/watcher |
| E7.13 | projection checkpoints, throttled, mandatory at turn end/detach | backend | `ProjectionCache.checkpoint/latest/invalidate`; seq throttle, mandatory reasons, stale-state rejection | Durable persistence write (dependency E4.4, not claimed) |
| E7.14 | mcpManager reconciles instances against settings, aggregates status, restart/probe | backend | `reconcile`, `McpManager.apply/probe/restart/aggregate`; start/stop/restart plan and status counts | Management surface UI; real MCP client lifecycle |
| E7.15 | schedule independent of activation; due messages queued into target session | backend | `ScheduledTask`, `SchedulerStore.schedule/cancel/due/inbox`; no activation input exists in the API | Delivery transport to a live session |
| E7.16 | ssh seam: one authenticated connection, helper identity, streams, cleanup | backend | `SshSeam.connect/open_stream/disconnect/assert_stream_open`, `DisconnectReceipt`; duplicate host, closed stream and bad auth fail closed | Real OpenSSH/socket, installed helper binary (external) |
| E7.17 | shellEnv: effect-scoped `KEEL_*` facts, one trusted snapshot per execution | backend | `EnvFact`, `validate_env_fact`, `ShellEnvRegistry.declare/snapshot/assert_trusted`; conflicting/hostile facts rejected | Shell process injection; native source proof (see §5) |
| E7.22 | LSP seam with exactly four normalized operations, no protocol escape hatch | backend | `LSP_OPERATIONS`, `LspService.dispatch`, `assert_no_lsp_escape_hatch`; `method`/`params`/`raw`/unknown keys rejected | Real language server transport |
| E7.24 | speechToText seam: local recognizers, authenticated remote, draft-only transcripts | backend | `SpeechToTextService` provider kinds, `Transcript`, `submit(user_confirmed=True)`; never auto-sends | Composer/dictation UI; recognizer/remote service |
| E7.25 | officeKit render/convert/recalculate via native engine or WASM fallback | backend | `OfficeEngine`, `OfficeKit.register/select`, `assert_no_cloud_engine`; native preferred, cloud/typed escape rejected | Document preview sidebar; LibreOffice/WASM engine (external) |
| E7.26 | fileUploads: streaming intake, durable storage, staged receipts | backend | `UploadService.stage/commit/receipt/assert_bound`; incremental SHA-256, accepted-only commit, session binding | Durable blob store; upload UI |
| E7.27 | Forge seam: URL→change request, head lookup, batch status, one poll loop, push binding | backend | `ForgeService.parse_url/lookup_head/batch_status/watch/bind_projection`; watchers dedupe, unknown hosts fail closed | Git inspection panel; provider HTTP/token |
| E7.28 | remoteAccess role policies, filtered lists, per-peer access snapshot | backend | `RolePolicy.authorize/filter_list/snapshot/assert_owner_only`; owner/approver/viewer matrix, copied results | Peer transport/consent UI (B4.8/C1.12 owners) |
| E7.29 | connection auth: verifier registry in registration order, first live peer wins | backend | `AuthRegistry.register/authenticate`; throwing verifier recorded as `error` and skipped, source object never carries authorization | Real peer sockets; native source proof (see §5) |
| E7.30 | authorization flow registry keyed by written record, one attempt per key | backend | `AuthFlowRegistry.register/begin/complete/fail`; `FlowBusyError` single-flight, opaque refs only | OAuth/device-code network flow |
| E7.31 | action cards: card kinds register actions and handlers | backend | `CardRegistry.register/create/invoke/card`, `ActionCard`; unknown action rejected, status notice recorded | Card row renderer (Y2.9) |
| E7.32 | plugin recommendations on explicit need only; enabling via manager click | backend | `RecommendationPolicy.recommend/enable`; no need signal → no suggestions, no click → no install | Recommendation card UI |
| E7.33 | registry probe: race mirrors, pick fastest valid one | backend | `MirrorResult`, `fastest_valid_mirror`; invalid mirrors ignored, deterministic tie-break | Actual HTTP race; native source proof (see §5) |
| E7.34 | plugin market reader for configured sources, validated; install via manager | backend | `validate_index_source`, `parse_market_index`, `manager_install_request`; HTTPS/no-userinfo/traversal and digest checks | Marketplace UI; direct install (never performed here) |
| E7.35 | message feedback in canonical log with per-item CAS; `/feedback` log-only | backend | `FeedbackLog.append/session_feedback/cas_for/events`; stale CAS rejected, note redacted | Thumbs UI (D3.16) |
| E7.36 | hooks bridges: adapters for other tools' hook formats | backend | `HookBridgeRegistry.register/translate/formats`, known format enum; broken adapter fails closed | Hook execution/runner; format discovery (C7.x) |
| E7.37 | agent-authored plugins: diff proposal, user review, sandbox host half, off by default | backend | `AgentPluginPolicy.propose/review/enable`; never auto-enabled, V23 required | V23 isolated subprocess runner (dependency V23, not claimed); served client half |
| E7.38 | workflow engine + fixed loop-until-done fan-out consumer | backend | `Workflow`, `LoopUntilDone.tick`, `WorkflowStep`; bounded fan-out, iteration budget, check gating | Script executor/subagent runtime (C5.1 owner) |
| E7.39 | webhook runtime: trusted rules turn authenticated deliveries into sessions | backend | `WebhookRuntime.register_rule/register_adapter/deliver`; unsigned/untrusted/unknown/unconfirmed fail closed | Listener/HTTP (D3.8 base seam owned elsewhere, not modified) |
| E7.40 | inspector service: worker-hosted debug target + query API over plugin tree | backend | `InspectorService.register_worker/query/trace`, read-only query guard, cycle detection | Inspector dock UI (D3.22) |
| E7.41 | storage seam: json/sqlite backends and typed domain form | backend | `StorageSeam.register_backend/put/get/list`, `assert_typed_domain`, deep copies | Real DB/file I/O (storage owner) |
| E7.42 | mcpResources: connection-owned providers, per-agent scoping | backend | `McpResourcesService.register/list_resources/read`; cross-agent read fails closed | Base MCP resource seam W3.11 (not modified) |
| E7.43 | browser/computer use provider seams; per-app consent with cancellation; retained runtime | backend | `ProviderSeams.register/resolve/consent/runtime_for`, `assert_no_shared_action_api`; per-provider tools/resources | Playwright/CDP/desktop engines (external), consent dialog UI (X5.9 base) |

Each of the 36 IDs appears exactly once in `FEATURE_IDS` and once in the test
suite (one `TestCase` class per ID plus two cross-cutting classes).

## 4. What the implementation actually does

The module is a *behavior* layer, not a name list. Representative observable
contracts, all asserted by tests:

* **Pure folds/monotonicity** — token measurements are immutable and replayable
  (E7.1); read acks never decrease (E7.4); turn and checkpoint sequences must
  advance (E7.5, E7.13); feedback uses compare-and-set (E7.35).
* **Fail-closed authorization** — role matrix and owner-only assertions
  (E7.28); verifier order with thrown-verifier skipping and no implicit
  authorization (E7.29); per-agent resource scoping (E7.42); per-app consent
  where cancellation overrides grant (E7.43).
* **Taint and injection safety** — cross-session text is truncated, credential
  patterns are redacted and a `</untrusted_session_reference>` breakout is
  escaped (E7.8); `KEEL_*` env facts reject shell metacharacters and conflicting
  owners (E7.17); no file bytes leave `@` completion (E7.7); inspector queries
  are read-only (E7.40); no shared LSP action/escape hatch (E7.22).
* **Single-flight and lifecycle** — one title provider (E7.10), one auth
  attempt per record key (E7.30), one SSH connection per host with cleanup
  receipt (E7.16), one deduplicated Forge poll loop (E7.27).
* **Binding and receipts** — uploads bound to session (E7.26), presets pinned
  until last release (E7.12), staged→committed/rejected states, manager
  install requests instead of direct enable (E7.32, E7.34, E7.37).
* **Determinism** — search ranking/snippets/cursors (E7.9), fallback titles
  (E7.10), mirror selection (E7.33), session spawn ids (E7.39) and engine
  selection (E7.25) are all reproducible without clock or chance.

Every public surface raises `ValidationError`, `NotFoundError`, `ConflictError`
or a typed subclass for bad input; nothing silently degrades to permissive.
The final AST test proves the module imports only `__future__`, `base64`,
`hashlib`, `json`, `re`, `dataclasses`, `enum`, `typing` and calls none of
`open/eval/exec/input/system/popen/subprocess/socket/time/random/print`.

## 5. Exclusions, owners and IDs referred to lead

* **Frontend-only delivery halves (not claimed):** document preview sidebar
  (E7.25), Forge and Inspector panels (E7.27, E7.40), action-card row renderer
  (E7.31 / Y2.9), recommendation and consent dialogs (E7.32, E7.43), session
  list unread dot (E7.4), plan guidance rendering (E7.11), composer/mention UI
  (E7.7, E7.8, E7.24). Reason: this assignment owns backend modules only.
* **External engines/services (not claimed):** OpenSSH and helper identity
  (E7.16), LibreOffice/WASM engine (E7.25), STT recognizers/authenticated
  remote (E7.24), Playwright/CDP/desktop control (E7.43), real MCP/forge/webhook
  HTTP clients (E7.14, E7.27, E7.39), real DB/file storage (E7.41), V23
  subprocess isolation (E7.37). Reason: descriptors and policy are testable
  offline; running those engines would violate the stdlib-only, no-I/O tier.
* **Other owners' seams (not modified):** D3.8 webhook base (E7.39), W3.11 MCP
  resources base (E7.42), D3.12 deliverables (E7.5), X5.9 clipboard/consent
  base (E7.43), C4.10 SSH provider (E7.16), A2.2 dictation (E7.24), C5.1
  workflow nodes (E7.38), C7.x hook formats (E7.36), Y2.9 cards (E7.31).
  These are referenced as dependencies/parents only; no existing file was
  edited and no foreign ID's status was changed.
* **Owner approval:** none of the 36 rows sets `owner_approval_required` or an
  `external_prerequisite`, so **no ID is referred to the owner as blocked**.
  The three rows with an "unverifiable reference claim" limitation (`E7.17`,
  `E7.29`, `E7.33`) are implemented as local, adversarial-tested policy; if the
  lead requires *native/source* equivalence rather than policy behavior, those
  three should be referred back with that stricter evidence bar. `E7.13`
  depends on E4.4 and `E7.37` depends on V23 for durable/runner halves; those
  halves remain owned by those IDs.

## 6. Verification

Both commands were run from the worktree root.

Required command:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_e7_runtime_backend.py']))"
```

Result: **79 passed in ~11 s, 0 failed, 0 skipped** (79 TestCase methods across
37 classes: one per implemented feature plus two cross-cutting purity/index
tests).

Additional stdlib runner (for portability):

```
python -c "import sys,unittest; sys.path.insert(0,'keel/src'); suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_e7_runtime_backend.py'); raise SystemExit(0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1)"
```

Result: **79 tests OK**.

### Adversarial coverage (all green)

* Security: tainted session-reference breakout, secret redaction, `"content"`
  leak in `@` completion, `KEEL_*` metacharacter/conflict injection, cloud
  engine fields, LSP `method`/`raw`/unknown fields, shared-action API,
  inspector `set`/`eval`, CAS races, single-flight flow attempts, cross-agent
  and cross-session reads, credential values in flow results.
* Reliability: monotonic acks/turns/checkpoints, stale checkpoint rejection,
  duplicate registrations, stale/tampered cursors, iteration and fan-out
  budgets, hook-tree cycles, verifier exceptions, upload digest mismatch,
  one-connection-per-host and stream teardown, fail-open title fallback.
* Determinism: replayed folds, stable cursors/snippets/ranking, deterministic
  tie-breaks, stable engine/mirror/session-spawn selection, deep-copied
  storage/list results.

## 7. Honesty statement

This change implements and tests the **backend descriptor/policy surface** of
all 36 open E7 rows. It does not claim that full products (SSH client, Office
renderer, STT service, browser/driver providers, real DB persistence, V23 VM,
durable checkpoint writer) were shipped, nor does it change any registry status.
The 7 already-`verified` E7 rows were left intact in `keel/runtime_contracts.py`.
