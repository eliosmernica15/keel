# Stabilization evidence — events and observability

**Branch:** `agent/stab-events`
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\stab\events`
**Baseline:** stabilization HEAD `f60b080`, merged to
`origin/stabilization/post-promotion-production-2026-11-25` HEAD `17c4420`.

**Files owned / changed**

- `keel/src/keel/backend_events.py`
- `keel/src/keel/backend_observability.py`
- `keel/src/keel/events.py` (audited, no change needed)
- `keel/tests/test_stab_events_integration.py` (new)
- `keel/tests/test_backend_events.py` (adapted fixtures to keyed head/record MACs; assertions strengthened)
- `STAB-EVENTS-EVIDENCE.md` (this file)

No frontend changes. No push.

---

## 1. Event-system boundary (task 1)

`backend_events.EventBus` / `DeliveryTracker` are **not consumed by any real
runtime path**. A source scan of `keel/src/keel/**/*.py` found zero imports of
`backend_events`; the only references are inside the module itself and tests.
This matches the independent audit finding `PRODUCTION-ARCHITECTURE-AUDIT.md`
MEDIUM-6.

Authoritative runtime event systems (left untouched; no competing system
introduced):

| System | Real call site | Role |
|---|---|---|
| `keel.events` | `session.py` (`ev.system_init`, `ev.assistant_message`, `ev.result`, `ev.system_permission_denied`, …), `runner.py` (`ev.result`) | stream-json event union emitted by the runtime |
| `automation.EventBus` | `capability_registry.py:1535,1548` (`fleet.anomaly`, `fleet.eventbus.publish`) | persisted local fleet event bus |
| `session_contracts.EventBus` | contract/test surface only | canonical session event journal |
| `d3_backend.FsEventBus` | D3 filesystem domain | filesystem event domain |

Verdict: `backend_events` is a **durable library contract** (closed typed
union, replay, idempotent publish, delivery state machine, cross-process
lock, HMAC chain). Its properties were verified with real files, threads and
subprocesses, but no runtime wiring was added. Consolidation with
`automation.EventBus` is an owner-level architectural decision, not a
stabilization change.

## 2. Observability runtime coverage (task 2)

`backend_observability` is also **not called by production code** (grep of
`src/keel` returns only its own definitions). Therefore no real runtime event
can honestly be claimed as recorded today. The module supports the required
kind vocabulary, and tests prove that workflow start/success/denial/failure,
task transitions, tool/provider failures, recovery and security events are
written with correlation IDs and verified chain links — but those writes are
test-driven, not runtime-driven.

**Exact changes required by the lead (outside owned files):**

1. `keel/src/keel/session.py` / `runner.py`: call `obs.record_event(...)` at
   the existing lifecycle branches (`Session.run` start, `ev.result`
   construction, `system_permission_denied`, provider exception handlers,
   recovery paths, security denial paths), passing the real
   `session_id/task_id/agent_id` and a module id.
2. `keel/src/keel/capability_registry.py` / `backend_hub.py`: expose
   `health_snapshot`, `health_check`, `health_http_payload`,
   `diagnostic_report` and `export_diagnostics` as capabilities; call
   `record_audit_event(...)` at the capability audit boundary.
3. `keel/src/keel/webapp.py`: route `/api/health` (and a new `/api/ready`) to
   `obs.health_http_payload(...)` / `obs.health_check(...)`.

Health itself was hardened in the owned file: `health_check` and
`health_http_payload` now report three distinct signals — `running`
(liveness), `initialized` (an event log or retention sidecar exists and its
chain verifies) and `ready` (chain + modules + dependencies healthy) — plus
per-dependency status for `database`, `provider`, `worker` and `event_log`.
A fresh install is legitimately live and ready before its first event, so
`initialized` is reported separately and does not gate readiness.

## 3. Fixes made in owned files

| # | Severity | Defect | Fix | Test |
|---|---|---|---|---|
| F1 | High | On Windows `os.open` without `O_BINARY` translated `\n`→`\r\n`; every rotation added CR bytes, so archived copies could never be byte-identical. | `_O_BINARY` on all byte appends/writes in both modules. | `test_forensic_retention_archives_evidence_and_keeps_chain` (SHA-256 match) |
| F2 | High | Cross-process lock acquisition failed on Windows `PermissionError` (WinError 5/32) while another process held the lock; 32-process key creation/probes could fail. | Treat `PermissionError` as contention, PID-liveness stale reclamation, bounded unlink retries in both modules. | `test_keyed_chain_and_delivery_state_survive_32_processes`, repeated `test_cross_process_event_integrity` (3/3) |
| F3 | High (M-4) | Unkeyed SHA-256 let an attacker append forged records and recompute the head; `['REAL-1','FORGED-2']` verified. | HMAC-SHA256 key (0600 `<state_root>/.keel-event.key` or `KEEL_EVENT_HMAC_KEY`), keyed record chain bound to `seq` + previous MAC + canonical bytes, MAC-protected head with `compare_digest`. | `test_forged_record_with_recomputed_plain_digest_is_rejected`, `test_truncated_log_with_recomputed_head_is_rejected`, `test_keyed_chain_and_delivery_state_survive_32_processes` |
| F4 | Medium | Legacy unkeyed logs would be silently trusted (or silently fail with no typed reason). | Explicit `legacy_mode=True` opts into documented plain SHA-256 verification; otherwise `CorruptRecordError` typed integrity error. | `test_unkeyed_legacy_log_fails_closed_unless_explicitly_enabled` |
| F5 | Medium | Retention deleted archives beyond the hot window, destroying forensic evidence. | Retired generations moved byte-for-byte into `<log>.forensic/` with a SHA-256 manifest; `verify_forensic_archives` / `read_forensic_archives`; collision fails closed. | `test_forensic_retention_archives_evidence_and_keeps_chain`, `test_missing_retention_state_next_to_archives_fails_closed` |
| F6 | Medium | Missing retention state next to archives silently restarted a genesis chain. | `_anchor` fails closed with a typed error. | `test_missing_retention_state_next_to_archives_fails_closed` |
| F7 | Medium | Liveness/readiness were the only health distinctions; no `initialized` signal and no DB/provider/worker/event-log per-dependency view in HTTP body. | `initialization_probe`, `initialized` in readiness/health/HTTP payload; dependency statuses retained. | `test_health_distinguishes_liveness_initialization_readiness_and_deps` |

## 4. M-4 before / after evidence

Pre-fix module copied verbatim from `HEAD~1` into an isolated `PYTHONPATH`
tree; the red-team reproduction script appended a `FORGED-2` record with a
recomputed unkeyed SHA-256 and an unkeyed head:

```
BEFORE  REPLAY: ['REAL-1', 'FORGED-2']        # forged record accepted
AFTER   REJECTED: CorruptRecordError ...:2: record HMAC mismatch
                  (unkeyed legacy record requires legacy_mode=True)
```

Regression tests against the pre-fix tree: **3 failed**
(`test_forged_record…`, `test_truncated_log…`, `test_unkeyed_legacy_log…` —
the latter two proved the corrupt states were accepted). Against the fixed
tree: **4 passed** (including the 32-process keyed-chain probe).

## 5. Verification (clean HOME)

A fresh `HOME`/`USERPROFILE` directory was created under the approved temp
root for the required run.

```
python -m pytest -q \
  keel/tests/test_backend_events.py \
  keel/tests/test_prod_observe.py \
  keel/tests/test_stab_events_integration.py
# 83 passed

python -m pytest -q \
  keel/tests/test_backend_events.py \
  keel/tests/test_backend_observability.py \
  keel/tests/test_prod_observe.py \
  keel/tests/test_stab_events_integration.py
# 97 passed
```

Related suites (`test_event_bus_persistence`, `test_automation`,
`test_session_contracts`, `test_compaction`, `test_db_persistence_hardening`,
`test_redaction`, `test_diagnostics`, `test_prod_revocation`): **84 passed**.

A full-suite run at the earlier stabilization commit produced
`6 failed, 4443 passed, 51 skipped, 3707 subtests passed`; all six failures
were pre-existing/environmental (five missing release-artifact fixtures and
one `test_quick_ask` HTTP timeout), unrelated to these files. After merging
the latest stabilization HEAD the targeted suites above were re-run and pass.

## 6. Residual gaps

- No runtime call site emits to `backend_observability`; real-event coverage
  remains an integration task for the lead (exact changes in §2).
- `backend_events` has no redaction of event metadata. It is not runtime-wired,
  so no secret currently reaches it; any future wiring must add redaction at
  the producer boundary.
- The HMAC key file is created with mode `0600` where the OS honours it;
  Windows may report a different effective mode. The key is never stored in
  the log, and env-supplied keys are supported for orchestrated deployments.
- Legacy mode is intentionally unkeyed and must only be used to migrate old
  logs; new deployments always use HMAC chains.
- Full-suite reproducibility after the merge was not re-run in this task;
  only the targeted suites were verified.

**Verdict:** M-4 and all HIGH/MEDIUM defects found in the owned area are
fixed with failing-then-passing tests. No competing event system was
introduced. Runtime wiring remains the lead's integration work.
