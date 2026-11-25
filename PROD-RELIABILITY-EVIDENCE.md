# Production hardening evidence — reliability and failure recovery

**Branch:** `agent/prod-reliability` · **Candidate HEAD:** `e6e7efc`
**Commit:** final commit on this branch titled
`fix(reliability): harden recovery contracts and add production recovery tests`.
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\production\reliability`
**Owner scope (strict):** `keel/src/keel/reliability_contracts.py`,
`keel/tests/test_prod_recovery.py` (new), this evidence file. No other source
files, no frontend, no push.

---

## 1. What was audited (observed, not assumed)

Read-only audit of runtime lifecycle and recovery in the candidate tree:

| Area | Observed implementation | Observation |
|---|---|---|
| Startup/ordering | `keel/src/keel/fleet/scheduler.py:343-357` `start_daemon()` is idempotent behind a lock; `tick_forever()` (`:333-340`) loops on a `threading.Event`; `keel/src/keel/cli/main.py:142,165` and `keel/src/keel/webapp.py` start it. | The scheduler has a stop-event design, but this module exposes no public `stop_daemon()`/`join()`; only `reset_daemon_for_tests()` (`:360-363`). No orderly worker join is reachable from an ordinary shutdown path. **Out of owned scope — not changed.** |
| Provider lifecycle | `keel/src/keel/mcp.py:219,424,565` exposes `shutdown()` / `shutdown_all()`; `keel/src/keel/reliability_contracts.py:1050-1094` `TrackingHTTPTransport` closes streamed responses. | A confirmed gap: HTTP **error** responses were not closed (defect D2 below). |
| Idempotency | `keel/src/keel/backend_workflows.py:320-382` derives keys from explicit values or a canonical digest and denies replay under a lock; `keel/src/keel/fleet/db.py` records migrations once. | Pattern is sound; the testing contracts module had no durable idempotency contract of its own. Added in X9.12. |
| Retry/backoff | `keel/src/keel/backend_events.py:1339-1508` `compute_backoff` + `DeliveryTracker` bound attempts (1..10), cap delays, and make terminal/cancelled states reject further attempts. | Pattern is sound; mirrored these bounds in the new recovery contract rather than inventing unlimited retries. |
| Recovery logs | `keel/src/keel/backend_events.py` `_JsonlStore` validates records on replay and reports tail recovery; `keel/src/keel/events.py:415-442` uses bounded `os.replace` retry. | New ledger uses the same append-only replay model with canonical-JSON records and fsync. |
| Worker budget | `keel/src/keel/d7_workflow_backend.py:268-328` `WorkerBudget` / `effective_workers` cap local workers and honour cgroups/CI. | No change; reference only. |

## 2. Confirmed defects fixed in the owned source file

Both regressions were written **first** and observed failing, then fixed and
observed passing. Evidence: initial `pytest -q keel/tests/test_prod_recovery.py`
reported `2 failed` (`TypeError: 'NoneType' object is not subscriptable` and
`assert False is True` for `stream.closed`); after the fixes the same file
reports `22 passed`.

| ID | Severity | Defect | Root cause | Fix |
|---|---|---|---|---|
| D1 | Medium (availability of the contract suite) | A legal fixture error status with no entry in `EXPECTED_ERROR_CATEGORIES` (e.g. 418) crashed `ProviderContractSuite.run()` instead of returning a typed failing result. | `expected = EXPECTED_ERROR_CATEGORIES.get(status)` then `expected[0]` with `expected is None`. | Explicit `if expected is None:` branch returning `BehaviorResult(ok=False, detail="unmapped fixture error status 418")` — fail closed, no exception, no fabricated success. |
| D2 | Medium (resource cleanup under repeated provider errors) | `TrackingHTTPTransport` leaked the live response owned by `urllib.error.HTTPError`: each provider error left an unclosed socket/response. | HTTPError branch read the body and returned without `exc.close()`. | `exc.close()` after `exc.read()`; the buffered body is still returned, and `closed_count` semantics for streamed responses are unchanged (existing contract test still passes). |

Regression tests: `test_unmapped_error_status_is_a_fail_closed_result_not_a_crash`,
`test_http_error_transport_closes_the_error_response`.

## 3. New recovery contract (X9.12) and real tests

`keel/src/keel/reliability_contracts.py` gained a stdlib-only, additive section:
typed `TaskPhase`/`FailureKind`/`WorkerPhase`/`LifecycleStage`, `RetryPolicy`,
`make_idempotency_key`, immutable `TaskRecord`/`WorkerRecord` snapshots,
`RetryDecision`, `RecoveryReport`, `WorkerShutdown`, the fsynced append-only
`RecoveryLedger`, and the ordered `RuntimeLifecycle`.

Invariants enforced by the ledger:

* One task per idempotency key; derived keys are canonical-JSON fingerprints,
  stable across insertion order and restarts. Replay is a `duplicate=True`
  result; key reuse for a different task is a hard conflict.
* One fsynced canonical-JSON commit per state change; replay is deterministic;
  a process killed mid-write leaves at most one truncated tail line, which is
  skipped (and counted) instead of being replayed.
* Terminal phases (`completed`, `cancelled`, `failed`, `quarantined`) cannot be
  mutated by stale records. The single deliberate exception is a human
  approval lifting a quarantine, logged explicitly.
* Destructive work starts in `awaiting_approval`; approval is a persisted token
  consumed on claim. Crash/failure never yields an implicit retry: a failed
  destructive task is quarantined and needs a new approval token.
* Retries are bounded by `max_attempts` (hard cap 10) and delays by
  `base_delay * factor ** (attempt - 1)` capped at `max_delay`. The ledger
  never sleeps; callers inject the clock and sleeper.
* Worker shutdown is two-phase (`begin_shutdown` → `finish_shutdown`) with a
  bounded `shutdown_worker(timeout, sleeper)`; claims from draining/retired
  workers are rejected and forced interrupts are reported explicitly.
* `recover()` retires workers from other runs, interrupts their RUNNING tasks,
  resets consumed destructive approvals, and quarantines children of blocked
  parents.

Required scenarios are covered by real tests in `keel/tests/test_prod_recovery.py`:

| Requirement | Test |
|---|---|
| Idempotency keys | `test_idempotency_keys_are_canonical_and_conflicts_fail_closed` |
| Concurrent duplicate submissions | `test_concurrent_duplicate_submissions_admit_once` (12 real threads, one admission) |
| Retry after partial failure | `test_retry_after_partial_failure_preserves_observed_output` |
| No blind retry of destructive work | `test_destructive_operations_are_never_blindly_retried`, `test_consumed_approval_does_not_survive_interruption`, `test_approval_state_persists_across_a_new_process` |
| Bounded retry/backoff | `test_bounded_retry_backoff_and_terminal_transitions` |
| Worker shutdown with in-flight work | `test_worker_shutdown_stops_claims_and_reports_forced_interrupt`, `test_worker_shutdown_drains_genuinely_in_flight_work` |
| Restart after mid-task death | `test_recovery_after_process_restart` — spawns `python` with a child script that registers a worker, claims a task, writes `HALF-OUTPUT`, then `os._exit(7)`; the parent process reconstructs from the JSONL state and resumes the same task |
| Duplicate event delivery | `test_duplicate_event_delivery_is_idempotent_and_conflicts_fail_closed`, `test_completion_redelivery_is_idempotent_but_conflicts_fail_closed` |
| Crash-consistent log tail | `test_truncated_tail_from_killed_writer_is_skipped`, `test_corrupt_log_line_fails_closed` |
| Lifecycle ordering | `test_runtime_lifecycle_shutdown_order_is_reverse_and_idempotent`, `test_runtime_startup_failure_cleans_up_in_reverse` |
| Parent/child + cancellation | `test_parent_failure_quarantines_children_during_recovery`, `test_cancellation_is_a_terminal_state_with_optional_cascade` |

## 4. Verification (measured on this worktree)

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_prod_recovery.py','keel/tests/test_reliability_contracts.py','keel/tests/test_reliability_e2e.py']))"
```

Result: **68 passed in 16.96s** (22 new recovery tests + 39 existing contract
tests + 7 existing e2e tests). All three named files exist; no skip was needed.
Baseline before changes: 46 passed (39 + 7); the two new regression tests were
confirmed failing before the fixes.

## 5. PROPOSED operational targets — NOT owner-approved

The numbers below are **PROPOSED measurement targets** for an owner to review.
They are not approved service levels, not commitments, and not claims about the
current production deployment. The test suite verifies the *mechanisms*
(bounds, replay, recovery) and the deterministic delays; it does not verify
wall-clock production performance.

| Target (PROPOSED) | Value | How it would be measured |
|---|---|---|
| Recovery time objective (RTO) after a worker/process loss | ≤ 60 s to mark affected tasks `interrupted` and make non-destructive tasks reclaimable | Time from injected `os._exit` to `recover()` reporting all affected tasks, in a staging soak run |
| Recovery point objective (RPO) | ≤ 1 fsynced JSONL record (one committed transition); partial output preserved from the last committed `partial` record | Kill-writer test plus checksum comparison of replayed state |
| Retry bound | ≤ 10 attempts per task; delays capped at `max_delay` (default 5 s) | `RetryPolicy` assertions and end-to-end failure loop |
| Destructive-operation retries | 0 blind retries; 1 new approval token required per attempt | Quarantine/approval tests |
| Worker drain | ≤ 30 s graceful drain, then forced interrupt with explicit report | `shutdown_worker(timeout=...)` with injected clock/sleeper; staging timing |
| Duplicate event delivery | 100% of redelivered event IDs accepted once; conflicting payload rejected | Ledger event tests |
| Startup failure cleanup | 100% of initialized services closed in reverse order | `RuntimeLifecycle` trace assertions |

## 6. Limits and non-changes

* No other source files were edited. The scheduler shutdown gap in section 1 is
  **documented only** because that module is outside this agent's ownership.
* The ledger is process-local + file-locked; it is deliberately not a
  distributed coordinator. Cross-host leasing, a real database transaction
  boundary, and distributed event delivery are out of scope for this stdlib
  contract.
* Retry delays are computed deterministically and never slept by the ledger;
  production sleep policy must be supplied by the owning service.
* `MAX_PARTIAL_BYTES` caps captured partial output at 64 KiB; larger provider
  output is rejected rather than silently truncated.
* No frontend changes, no push, no release-manifest or plan-registry changes.
  Operational targets in section 5 remain PROPOSED pending owner approval.
