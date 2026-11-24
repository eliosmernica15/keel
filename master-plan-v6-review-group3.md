# Independent review — Group 3 backend modules (v6)

**Branch reviewed:** `integration/v6-backend-complete` @ `1ffffb2`
**Review branch:** `agent/review-g3` (created from the branch above; not pushed)
**Scope:** 5 backend modules + their test files (10 files total)
**Method:** line-by-line source read; each module's own test file executed individually
(`python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_X.py']))"`).
The *full* suite was **not** run, per instruction.

## Test results (per-module, all pass)

| Test file | Result |
|---|---|
| `keel/tests/test_y2_backend.py` | 41 passed |
| `keel/tests/test_y3_backend.py` | 31 passed |
| `keel/tests/test_y4_d4_x7_backend.py` | 43 passed |
| `keel/tests/test_z_backend.py` | 90 passed, 4 subtests passed |
| `keel/tests/test_d3_backend.py` | 35 passed |

## Verdicts at a glance

| Module | Verdict | One-line reason |
|---|---|---|
| `y2_backend.py` | **GENUINE_BACKEND** | Real state machines/algorithms throughout; 2 confirmed logic/security defects. |
| `y3_backend.py` | **GENUINE_BACKEND** | Real provisioning/queue/pairing/state logic; retry returns an unstored object; tick guard racy. |
| `y4_d4_x7_backend.py` | **GENUINE_BACKEND** | Real validators, deterministic tarball, path-safe file ops; minor injection/validator gaps. |
| `z_backend.py` | **GENUINE_BACKEND** | Real hashing, JSONL/SQLite ledgers, Ed25519 with RFC 8032 vector; dangerous redaction gap. |
| `d3_backend.py` | **GENUINE_BACKEND** | Real state machines, fs veto waterfall, wire codecs; minor input-validation gaps. |

None of these are descriptor-only stubs. Each implements executable invariants with typed
errors and deterministic outputs, and each test file asserts concrete outputs, errors and
state transitions (not merely symbol existence).

---

## Cross-cutting finding: wiring

The five modules themselves import **no** `keel.*` runtime symbols (verified by grep:
zero `from keel`/`import keel` matches in all five files). They are stdlib-only and
additive at the source level, so their own docstrings' "additive, not wired in" language
is accurate *for the module files*.

However, on this branch they **are** wired into the live runtime externally:

- `keel/src/keel/backend_hub.py:17,1380` — `importlib.import_module("keel." + module)`;
  each module is registered in `MODULE_FEATURES` (lines 24, 232, 244, 256, 274) and has a
  strict allowlist in `DISPATCH` (lines 291, 323, 325, 327, 329).
- `keel/src/keel/capabilities.py:141-198` — `_register_backend_capabilities()` exposes
  `backend.modules`, `backend.describe`, `backend.invoke` (permission `core`/`execute`,
  `mutates=False`) and `backend.verify`, consumed by the web bridge/CLI/TUI/desktop.

So: **not self-wired, but integrated through a permission-aware hub.** Consequences for
severity below: e.g. `z_backend.render_replay` and `y2_backend.plan_compaction` are live
dispatchable entry points via `backend.invoke`.

---

## 1. `keel/src/keel/y2_backend.py` + `test_y2_backend.py`

**Verdict: GENUINE_BACKEND**

### Q1 — Real observable behavior vs descriptor-only
Real behavior dominates (not just constants/docstrings). Specific examples:

- `RowKindRegistry.register/get/kinds_for/validate/make_row` (lines 242-288): real schema
  validation, duplicate rejection, deterministic row ids.
- `should_stay_silent` (343-359): decision logic over mentions/author/group.
- `CollabToolRegistry.dispatch` (427-450): real dispatch with context merging and typed errors.
- `SubagentManager.spawn/stop_subagent` (509-534): real lifecycle (context/screen cleared,
  cap `MAX_HIDDEN_CHILDREN=8`).
- `GroupRoom.post` (603-623): real @mention routing, 3-responder cap, loop guard
  (`LOOP_GUARD_MAX_CONSECUTIVE=3`).
- `DesktopPool.lease/release` (685-714): real 4-desktop LRU leasing with monotonic ticks.
- `ResourceManager.sweep` (785-805): real idle-timeout decisions, dry-run vs applied.
- `TokenBucket.allow/refill/retry_after` (852-885): real token bucket with clock-regression
  guard; `InVmExecutor.submit` (982-992) really short-circuits rate-limited actions.
- `plan_compaction` (1077-1108): real size/idle triggers, verbatim user turns, bounded memory.
- `prompt_cache_key`/`safety_identifier`/`assert_no_raw_identifier` (1126-1157): real stable
  hashing and leak detection.
- `parse_scheduler_flag` (1189-1198), `RenameCompat.ensure_symlink` (1283-1301),
  `RealtimeSecretIssuer` (1461-1498), `prepare_audio_fixture` (1643-1663: real PCM/WAV bytes),
  `SSEStream.publish/drain` (1821-1840: bounded replayable event buffer),
  `parse_cron`/`CronSchedule.matches`/`RoutineEngine` (1884-2097: real cron parser and engine).

Descriptor-only seams are explicitly honest: `ExecutorSeam`, `TextLoopSeam`,
`TranscriptionSeam`, `E2EHarness` default methods raise `NotImplementedError`;
`TtsPreview` (1549) deliberately never fabricates audio.

### Q2 — Test quality
Tests assert real behavior, not just existence: outputs, errors, state transitions, e.g.
`test_row_kind_registry_validates_bodies_and_is_deterministic` (69-83),
`test_group_room_loop_guard_blocks_a_repeating_responder` (187-193),
`test_token_bucket_burst_then_refill` (279-289),
`test_sse_reconnect_drain_and_bounded_buffer` (605-613).
Only `test_all_fifteen_feature_ids_have_backend_symbols` (40-44) is existence-only, and it
is a coverage guard backed by behavioral tests for every feature.

### Q3 — Real defects
1. **MEDIUM — off-by-one in compaction.** `plan_compaction` line 1095:
   `verbatim = tuple(user_turns[-config.keep_last_user_turns:]) if summarise else ()`.
   `CompactionConfig.__post_init__` (1021-1029) explicitly allows `keep_last_user_turns == 0`,
   but in Python `user_turns[-0:] == user_turns[0:]` — **all** user turns are kept verbatim
   instead of none. Reproduced: with `keep_last_user_turns=0`, turns `u1,u2,a1` produced
   `verbatim_ids == ['u1','u2']` and `summary_text == 'a1'`. `plan_compaction` is dispatchable
   through `backend_hub.DISPATCH` (line 323), so this is live. Test at 331-347 only uses the
   default `keep_last=4`, so it misses this.
2. **MEDIUM — predictable "secret" token.** `RealtimeSecretIssuer.issue` line 1484 derives
   the token as `new_id("realtime", session_id, current, self._nonce, length=24)` — a plain
   SHA-256 of public values plus a small incrementing counter. `RealtimeSecret.public_dict()`
   (1452-1455) publishes `session_id` and `issued_at` (the exact `current`). Reproduced:
   after `issue("session-1", now=1000.0)`, guessing nonce `1` reproduced the token exactly.
   No RNG, no server-side secret input — anyone who sees the redacted metadata can recover
   the bearer token.
3. **LOW — symlink TOCTOU / unchecked base names.** `RenameCompat.ensure_symlink`
   (1286-1296) resolves the containment check and then calls `symlink_to` separately; a
   concurrent swap of `new_name` between `resolve()` and `symlink_to()` can bypass the
   `is_relative_to(base)` guard. `CompatRenames` fields (1219-1222) are caller-supplied and
   `database_path()` (1263-1272) joins them to `base` without validating absolutism, so an
   absolute name escapes the base. No symlink/TOCTOU test beyond the static `../outside`
   case (test 449-466).

No `eval`/`exec`/`os.system`/network/socket usage; no mutable-default bugs found.

### Q4 — Runtime import
No `keel.*` imports. Additive source, wired externally via `backend_hub` +
`capabilities.backend.invoke` (see cross-cutting).

### Q5 — Verdict + top 3
**GENUINE_BACKEND.**
1. MEDIUM — `y2_backend.py:1095` `plan_compaction` `[-0:]` keeps all user turns (reproduced).
2. MEDIUM — `y2_backend.py:1484` (+ `public_dict` 1452-1455) realtime token brute-forceable
   from published metadata (reproduced, nonce=1).
3. LOW — `y2_backend.py:1286-1296` symlink check/use TOCTOU and unvalidated rename names.

---

## 2. `keel/src/keel/y3_backend.py` + `test_y3_backend.py`

**Verdict: GENUINE_BACKEND**

### Q1 — Real observable behavior vs descriptor-only
Real behavior throughout:

- `evaluate_availability`/`visible_options`/`assert_no_dead_options` (179-205): real
  availability state machine.
- `ProvisioningRegistry.steps_due` + `run_provisioning` (251-338): real versioned,
  resumable, idempotent step runner with runner-result identity checks.
- `concurrency_limit`/`PerUserQueue.submit/finish/cancel/_pump` (361-426): real FIFO queue
  with RAM/VRAM-derived limits; `ConcurrencyManager` (429-453) per-user isolation.
- `tick` + `IdempotencyLedger.claim` + `TickGuard` (524-598): real 7-job tick with
  content-hash idempotency keys and overlap guard.
- `PairingBroker` (631-703): real pairing state machine (pending→approved/expired/
  cancelled/denied, 30-min TTL, retry).
- `InviteGate` (727-772): first-admin ownership enforcement in serve mode.
- `plan_first_run`/`estimate_cost` (837-872): reuse-first offers with computed costs.
- `validate_settings_tree`/`section_for_key` (915-931), `build_route`/`validate_route`
  (966-993), `ProposalLedger` approval gate (1056-1110), `LocalCache` LRU (1148-1200),
  `forked_brand` (1239-1247), `assert_security_model_complete` (1301-1309),
  `AcknowledgementLedger` (1367-1381) — all real logic.

`StepRunnerSeam`, `ModelProbeSeam`, `ProposalApplySeam` default methods raise
`NotImplementedError` (honest seams), with `InMemory*`/`Recording*` implementations for tests.

### Q2 — Test quality
Behavioral: version-bump reruns and resume (125-153), queue auto-start (178-203), tick
dedup/overlap (218-249), pairing lifecycle/expiry (257-294), invite gate (301-324), LRU
eviction (467-479), proposal approval gate (425-455). One existence-only guard
(`test_p0_y3_rows_verified_in_config_contracts`, 549-570) checks P0 symbols in the *other*
module (`config_contracts`), acceptable.

### Q3 — Real defects
1. **MEDIUM — `retry()` returns an object that is not stored.** `PairingBroker.retry`
   lines 695-703 calls `fresh = self.create(nonce)` (which stores a `PENDING` session with
   `attempts=1`) and then returns a *newly constructed* `PairingSession(..., attempts=session.attempts + 1)`
   that is never written to `self._sessions`. Reproduced: returned `attempts=2`, but
   `broker.poll(retried.code).attempts == 1`, and `retried is not broker.poll(retried.code)`.
   The test (line 282) only checks the returned object, so the divergence is invisible.
2. **LOW/MEDIUM — `TickGuard` is not actually concurrency-safe.** `TickGuard.acquire`
   (546-549) does `if self._active: raise ...` then `self._active = True` with no lock;
   two threads can both pass the check and both run a tick, contradicting the class
   docstring "Makes ticks safe to overlap: a second concurrent tick is refused" (540).
   `IdempotencyLedger` (527-534) likewise has no lock and grows without bound.
3. **LOW — pairing code has no attempt lockout despite tracking attempts.** `create`
   line 645 issues a 6-hex-char (24-bit) code from `hash(nonce, created)`, and `attempts`
   (field line 623) is incremented only by `retry` — `approve`/`deny`/`resolve` never
   enforce a limit. Brute-forcing a 16.7M-space code within the 30-minute TTL is feasible
   with no throttle at this layer.

No injection/eval/path-traversal found; `resolve_data_dir` only reads an injectable env
mapping (1123-1127).

### Q4 — Runtime import
No `keel.*` imports (test imports `config_contracts` only to guard P0). Additive source,
wired via hub (`backend_hub.py:244/325`, `capabilities.py`).

### Q5 — Verdict + top 3
**GENUINE_BACKEND.**
1. MEDIUM — `y3_backend.py:701-703` `retry()` returns an unstored session; stored `attempts`
   stays 1 while caller sees 2 (reproduced).
2. LOW/MEDIUM — `y3_backend.py:546-549` `TickGuard.acquire` check-then-set race; no lock.
3. LOW — `y3_backend.py:623,645` tracked `attempts` never enforced; 24-bit pairing code
   with no throttling.

---

## 3. `keel/src/keel/y4_d4_x7_backend.py` + `test_y4_d4_x7_backend.py`

**Verdict: GENUINE_BACKEND**

### Q1 — Real observable behavior vs descriptor-only
Real algorithms and validators, not constant tables:

- `McpServerReviver` (85-146): real dormant/reload/probe state machine.
- `SecretProviderMap.add_binding/enable/resolve` (232-282): real non-interactive gating so
  the provider never prompts on startup.
- `SupervisedBridge.start/wake_if_keyed/suspend/deliver` (314-346): real bridge state and
  delivery sequencing (requires user-supplied https tunnel).
- `TraceStore.record/query/what_did_you_do` (375-393): real event log and queries.
- `validate_desktop_tools` (429-437): real sorted `Issue` validator.
- `ObsidianVault.note_path/create_note/read_note` (448-471): real filesystem writes with
  regex sanitization + `resolve()` + `parents` containment (test 174 checks `../../evil.md`).
- `deterministic_tarball` (580-604): real reproducible gzip/tar with zeroed metadata.
- `ProviderRegistry.configure/resolve` (686-705), `WorkspaceGate` (721-757),
  `NodeRendererRegistry.render` (818-826), `SettingsCardRegistry.render_form` (894-906),
  `verify_ui_copy` (944-964), `DesignGuideSkill.gate` (1029-1035), `select_port` (1106-1126),
  `verify_target_matrix` (1155-1161), `uninstall_plan` (1204-1220), `verify_download`
  (1354-1366), `plan_import`/`execute_import` (1385-1417: real copy with source/target
  containment), `scan_disk_usage`/`safe_clean_plan` (1430-1465: real size scan, no deletes),
  `verify_coverage` (1526-1547): all real.

### Q2 — Test quality
Tests assert outputs/errors/effects, including real filesystem round-trips (`test_dry_run_then_copy`
492-510, `test_scan_and_safe_clean_plan` 513-530) and determinism (`test_reproducible_tarball`
208-221). `CoverageTests` (24-32) checks `verify_coverage() == ()` — a real validator, not
mere `hasattr`.

### Q3 — Real defects
1. **LOW/MEDIUM — query-parameter injection in the pairing deep link.**
   `build_onboarding_payload` (175-191) interpolates `token`, `host` and `port` directly into
   `keel://pair?channel=...&token=...&host=...&port=...` without URL-encoding. Reproduced:
   token `"abc&host=evil.example"` yields
   `keel://pair?channel=telegram&token=abc&host=evil.example&host=127.0.0.1&port=8739`
   — a caller-controlled token overrides the host parameter. The function is dispatchable via
   `backend_hub.DISPATCH` (line 327).
2. **LOW — `verify_clean_removal` misses unknown removals.** Line 1247:
   `for key in sorted(rem & expected - reg & expected)`. Because `-` binds tighter than `&`,
   this is `rem & (expected - reg)`; a key that is removed but is neither registered nor in
   `expected` is never reported as `unexpected_removal`. Reproduced with a removed
   `"totally-unknown"` key — no such issue emitted.
3. **LOW — unvalidated tar member names.** `deterministic_tarball` line 591 uses
   `tarfile.TarInfo(name)` with caller-supplied keys verbatim; a key such as
   `../../etc/passwd` produces a tarball with traversal member names. The module only emits
   bytes (no extraction), so impact depends on the consumer, but the "reproducible artifact"
   claim would be stronger with sanitization. (Related minor gap: `windows_install_plan`
   line 1187 interpolates `username` into `C:\Users\{username}\...` without sanitization;
   output is a plan descriptor only.)

No `eval`/`exec`/network/socket. `ObsidianVault` and import functions do real I/O but with
containment checks. Typed-error consistency gap: `_require` (144-146),
`NodeRendererRegistry.definition` (831-832) and `SettingsCardRegistry.render_form` (894-895)
raise bare `KeyError` while the rest uses `BackendError`.

### Q4 — Runtime import
No `keel.*` imports. Additive source, wired via hub (`backend_hub.py:256/327`, `capabilities.py`).

### Q5 — Verdict + top 3
**GENUINE_BACKEND.**
1. LOW/MEDIUM — `y4_d4_x7_backend.py:183-184` unencoded deep-link token injects `host`/`port`
   query parameters (reproduced).
2. LOW — `y4_d4_x7_backend.py:1247` operator precedence hides unknown-removal keys in
   `verify_clean_removal` (reproduced).
3. LOW — `y4_d4_x7_backend.py:591` tar member names unsanitized (path-traversal payload possible).

---

## 4. `keel/src/keel/z_backend.py` + `test_z_backend.py`

**Verdict: GENUINE_BACKEND**

### Q1 — Real observable behavior vs descriptor-only
This is the most implementation-heavy module. Real behavior includes:

- `_atomic_write_text` (96-112): real temp-file + fsync + os.replace.
- `_safe_relpath` (140-150): real absolute/NUL/`..` rejection used by lockfile, sync, budgets,
  preflight.
- `hash_file`/`build_lock`/`verify_lock` (168-293): real SHA-256 pinning and drift detection.
- `run_contract_tests` + checkers (365-450): real scripted-runner evaluation.
- `redact_text`/`redact_record`/`render_replay`/`verify_replay` (472-577): real redaction,
  standalone HTML and integrity re-computation (`hmac.compare_digest`).
- `LocalSync` (725-809): real hash-chained JSONL ledger, LWW with visible conflicts, conflict
  resolution; `changes()` fails closed on tamper.
- `DriftStore` (1079-1170): real SQLite persistence, score-drift detection, weekly schedule.
- Z12 Ed25519 (1258-1482): a full hand-implemented RFC 8032 point arithmetic, `generate_keypair`
  (uses `os.urandom(32)` when no seed), `sign`, cofactored `verify`, certificate chain and
  signed bundles with downgrade rejection in `import_bundle`.
- `propose_rule`/`validate_rule`/`simulate`/`policy_editor` (983-1072): real policy translation,
  Tier-2 conflict checks, explicit-approval gate.
- `InjectionCorpus` (1744-1809): consent-gated, hashed+redacted local corpus.
- `ProjectBudgets` (1816-1924): real stop-at-budget ledger over JSONL usage.

Tests include the official RFC 8032 vector (`test_rfc8032_test_vector`, 584-592), so the
crypto is genuinely verified, not decorative.

### Q2 — Test quality
Excellent: real temp files/SQLite, tamper detection, hash chains, Ed25519 test vector,
budget stop behavior. `test_module_is_stdlib_only_and_offline` (38-52) parses the AST and
checks the import allowlist — a real static assertion. Existence-only coverage is limited to
`FEATURE_IDS` scope (29-36).

### Q3 — Real defects
1. **MEDIUM — redaction leaves the actual credential.** The `secret` rule
   (`_REDACTION_RULES`, lines 461-463) captures only the *first* token after `key[:=]`.
   Reproduced: `redact_text("Authorization: Bearer abcdef123456")` returns
   `"[REDACTED:secret] abcdef123456"` — the word "Bearer" is redacted and the real token
   survives. `redact_record` (489-497) also redacts only string *values*, never dict keys
   (`redact_record({"sk-abcdefghijklmnop": "ok"})` is unchanged). `render_replay` is a
   dispatchable `backend.invoke` function (`backend_hub.py:329`), so an exported "redacted"
   replay can still contain secrets — a direct contradiction of the feature's purpose.
2. **LOW/MEDIUM — no locking on append-only ledgers (TOCTOU).** `LocalSync.append`
   (755-767) reads the whole chain via `self.changes()` and then calls `_append_jsonl`
   (132-137, plain `open(..., "a")`); two concurrent appends can compute the same `seq`/`prev`,
   producing a chain that `changes()` then rejects as "out of order" (741-742). The same
   check-then-write pattern exists in `ProjectBudgets.record` (1864-1871, `check()` then
   `_append_jsonl`), so a concurrent burst can bypass `stop_at_budget`.
3. **LOW — `False`/`0` counted as a present setting.** `_setting_present` (1198-1199) uses
   `value is not None and value != "" and value != [] and value != {}`; `False` and `0`
   satisfy all four comparisons. Reproduced: `probe(Integration("x","connector",("flag",)),
   {"flag": False}, now=1)` returns `status == "active"`, so an explicitly disabled required
   flag is treated as satisfied by the health board.

No `eval`/`exec`/shell/network. Path handling (`_safe_relpath`, `import_bundle` kind/version
validation at 1439-1505) is sound; Ed25519 implementation is verified by the RFC vector.
Minor: `assert_no_network_assets` (582-586) scans the head for literal `src=`/`href=`/`url(`,
so an escaped title containing those substrings gives a false positive.

### Q4 — Runtime import
No `keel.*` imports. Additive source, wired via hub (`backend_hub.py:274/329`, `capabilities.py`).

### Q5 — Verdict + top 3
**GENUINE_BACKEND.**
1. MEDIUM — `z_backend.py:461-463,489-497` redaction misses the secret after "Bearer" and
   never redacts dict keys; `render_replay` is live via `backend.invoke` (reproduced).
2. LOW/MEDIUM — `z_backend.py:755-767,132-137,1864-1871` unlocked append/TOCTOU in sync
   and budget ledgers.
3. LOW — `z_backend.py:1198-1199` `_setting_present` treats `False`/`0` as present
   (reproduced: disabled flag → `active`).

---

## 5. `keel/src/keel/d3_backend.py` + `test_d3_backend.py`

**Verdict: GENUINE_BACKEND**

### Q1 — Real observable behavior vs descriptor-only
Real in-process behavior for all 13 rows:

- `SubagentProvider.__post_init__`/`SubagentRegistry.activate` (166-238): validates the
  single-interface contract and remote-flag consistency; activation descriptors.
- `TeamBoard` (307-435): real per-root task state machine (claim/complete ownership),
  messaging/inbox with broadcast, interrupt flags; `TeamService.enable` (444-451) enforces
  one root session.
- `PresetService.resolve` (541-557): real isolate instance ids vs shared ones.
- `FsEventBus.dispatch` (658-675): real tier-2-before-tier-1 veto waterfall with chain/reasons.
- `DeliverableService.attach/card` (722-761): real per-turn storage, SHA-256 of content.
- `ExtensionService` (806-863): real propose→approve/reject gate; `application()` refuses
  anything not approved and never writes.
- `FeedbackService`/`InstallIdentity` (896-986): local-only records; CSPRNG install ids
  (`secrets.token_hex(16)`), `export_for_transmission()` always raises.
- `PlanLog.append/checklist/replay` (1028-1073): real append-only event log with
  contiguous-event replay; `ScheduleService` (1112-1158): real due/fire state machine.
- `ProductPackagePolicy.check_layout` (1224-1255), `canonical_digest`/`check_metadata`
  (1284-1338), `PinnedSource`/`inspector_build_plan`/`check_offline_build` (1344-1421),
  `encode_message`/`decode_message` (1432-1469): real layout validation, length-prefixed
  digests, offline build checks and framed wire codec with length/checksum/version/kind checks.

The module is honest that it does no OS I/O/network/UI; result cards and descriptors are
explicitly marked `frontend_rendered=False`/`io_performed=False`.

### Q2 — Test quality
Behavioral: task ownership transitions (115-139), fs veto ordering (207-245), plan replay
(384-412), schedule due/fire (415-446), quarantine violations (452-490), metadata staleness
(496-522), wire round-trip for every kind plus eight corrupt-frame cases (563-600). Coverage
tests (27-55) derive expected IDs from `PLAN-INDEX.json` and verify real P0 symbols in
`capability_seams` — stronger than `hasattr`-only guards.

### Q3 — Real defects
1. **LOW — unhandled exceptions for non-finite `hours`.** `ScheduleService.schedule`
   (1118-1132) does `hours = float(hours)` and checks only `hours <= 0`. `NaN` and `inf`
   pass the check; `timedelta(hours=hours)` then raises raw `ValueError: cannot convert float
   NaN to integer` / `OverflowError: cannot convert float infinity to integer` instead of
   `ScheduleError`. Reproduced for both values.
2. **LOW — `check_offline_build` can give false assurance.** Lines 1404-1421 only regex-scan
   source text for `http(s)://`, `curl`/`wget` and `fetch(`. Network access via
   `urllib.request.urlopen`, `requests.get`, sockets, etc. passes as "clean". The docstring
   calls it a "pure source-text check", so this is a documented limitation, but consumers may
   reasonably read `clean=True` as a security gate.
3. **LOW — listener exceptions escape the typed-error layer.** `FsEventBus.dispatch`
   (663-665) calls `listener.decision(request)` without a try/except; a plugin listener that
   raises propagates an arbitrary exception instead of a typed `FsPolicyError`, breaking the
   module's "every invariant violation is a `D3BackendError`" design. (`ProductPackagePolicy.check_layout`
   at 1246-1249 likewise detects an experimental package only when its exact name is a path
   segment, so a renamed/repackaged path evades that check.)

No `eval`/`exec`/subprocess/network/file I/O; no mutable-default bugs. The only RNG use
(`secrets.token_hex`) is appropriate for local install ids.

### Q4 — Runtime import
No `keel.*` imports inside the module (the test imports `capability_seams` only for the P0
reference guard). Additive source, wired via hub (`backend_hub.py:24/291`, `capabilities.py`).

### Q5 — Verdict + top 3
**GENUINE_BACKEND.**
1. LOW — `d3_backend.py:1123-1130` non-finite `hours` raises raw `ValueError`/`OverflowError`
   instead of `ScheduleError` (reproduced).
2. LOW — `d3_backend.py:1404-1421` offline-build check is a narrow text regex that can be
   trivially bypassed while reporting `clean=True`.
3. LOW — `d3_backend.py:663-665` listener exceptions bypass the typed-error contract.

---

## Overall recommendation

All five modules are genuine executable backends with substantive behavioral tests; none
should be reclassified as descriptor-only. Before treating them as release-ready, the
highest-value fixes are:

1. `y2_backend.py:1095` — `keep_last_user_turns == 0` (use an explicit zero check).
2. `z_backend.py:461-463` — extend the redaction regex so the captured group is the actual
   credential (`(?:Bearer\s+)?<token>`) and redact secret-bearing dict keys.
3. `y2_backend.py:1484` — stop deriving bearer tokens from published metadata; use a
   CSPRNG-backed secret (or at minimum stop publishing `issued_at`).
4. `y3_backend.py:701-703` — store the retried session object returned to the caller.
5. Add locking to the hash-chained/budget ledgers (`z_backend.LocalSync`, `ProjectBudgets`).
