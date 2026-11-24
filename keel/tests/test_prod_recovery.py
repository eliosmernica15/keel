"""Production hardening: runtime lifecycle and task/worker recovery contracts.

These tests are additive.  They import only public, stdlib-backed contracts
from :mod:`keel.reliability_contracts` and exercise real subprocess crashes,
real threads, real JSONL persistence and real cleanup ordering -- no mocked
success paths.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import time
import urllib.error
from pathlib import Path

import pytest

import keel.reliability_contracts as rc
from keel.reliability_contracts import EventKind, ScriptEvent


KEEL_SRC = Path(__file__).resolve().parents[1] / "src"


def _script_set(**replacements):
    scripts = list(rc.standard_scripts())
    for index, script in enumerate(scripts):
        if script.name in replacements:
            scripts[index] = replacements[script.name]
    return tuple(scripts)


def _ledger(tmp_path, *, run_id="main", clock=None):
    return rc.RecoveryLedger(tmp_path / "state", run_id=run_id, clock=clock)


# ===========================================================================
# Regressions for confirmed defects in the existing contracts module
# ===========================================================================


def test_unmapped_error_status_is_a_fail_closed_result_not_a_crash():
    """An HTTP status without a category table entry must not crash the suite.

    Before the fix, ``EXPECTED_ERROR_CATEGORIES.get(418)`` returned None and
    ``expected[0]`` raised ``TypeError`` out of ``ProviderContractSuite.run``.
    """
    error = rc.FixtureScript("error", "fx-error", (
        ScriptEvent(EventKind.ERROR, status=418, error="unmapped status"),))
    with rc.make_fixture_server(_script_set(error=error)) as server:
        report = rc.ProviderContractSuite().run(
            rc.default_bindings()[0], server)
    result = next(r for r in report.results if r.case == "errors")
    assert not result.ok
    assert "418" in result.detail
    assert not report.ok


def test_http_error_transport_closes_the_error_response():
    """HTTPError responses are sockets too; the transport must close them.

    Before the fix the HTTPError branch returned the body iterator without
    closing the error response, leaking one socket per provider error.
    """
    stream = io.BytesIO(b'{"error":{"message":"rate limit"}}')
    error = urllib.error.HTTPError(
        "http://127.0.0.1:1/v1/chat/completions", 429, "rate limit", {}, stream)
    original = rc.urllib.request.urlopen

    def raising(*_args, **_kwargs):
        raise error

    rc.urllib.request.urlopen = raising
    try:
        transport = rc.TrackingHTTPTransport()
        status, headers, chunks = transport(
            {"url": "http://127.0.0.1:1/v1/chat/completions"})
        assert status == 429 and dict(headers) == {}
        assert json.loads(b"".join(chunks))["error"]["message"] == "rate limit"
    finally:
        rc.urllib.request.urlopen = original
    assert stream.closed is True
    # Error responses are not streamed by chunks(), so closed_count stays 0.
    assert transport.closed_count == 0


# ===========================================================================
# Idempotency and duplicate delivery
# ===========================================================================


def test_idempotency_keys_are_canonical_and_conflicts_fail_closed(tmp_path):
    payload = {"b": 2, "a": 1}
    first = rc.make_idempotency_key("task", task_id="t1", payload=payload)
    reordered = rc.make_idempotency_key(
        "task", task_id="t1", payload={"a": 1, "b": 2})
    assert first == reordered and first.startswith("task:")
    assert first != rc.make_idempotency_key(
        "task", task_id="t2", payload=payload)
    assert rc.make_idempotency_key("task", explicit="client-key-1") == "client-key-1"
    with pytest.raises(rc.ValidationError):
        rc.make_idempotency_key("bad scope!")
    with pytest.raises(rc.ValidationError):
        rc.make_idempotency_key("task", explicit="bad key")

    ledger = _ledger(tmp_path)
    admitted = ledger.submit("t1", idempotency_key="client-key-1", payload=payload)
    assert admitted.duplicate is False
    repeated = ledger.submit("t1", idempotency_key="client-key-1", payload=payload)
    assert repeated.duplicate is True and repeated.task == admitted.task
    with pytest.raises(rc.DuplicateSubmissionError):
        ledger.submit("t2", idempotency_key="client-key-1")
    with pytest.raises(rc.DuplicateSubmissionError):
        ledger.submit("t1", idempotency_key="another-key")
    assert len(ledger.tasks()) == 1
    assert ledger.ops == 1


def test_concurrent_duplicate_submissions_admit_once(tmp_path):
    ledger = _ledger(tmp_path)
    results: list[rc.TaskResult] = []
    barrier = threading.Barrier(12)

    def submit(index: int) -> None:
        barrier.wait()
        results.append(ledger.submit(
            "t-concurrent", idempotency_key="shared-key",
            payload={"attempt": index}))

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert len(results) == 12
    assert sum(not result.duplicate for result in results) == 1
    assert len(ledger.tasks()) == 1
    assert ledger.ops == 1


def test_duplicate_event_delivery_is_idempotent_and_conflicts_fail_closed(tmp_path):
    ledger = _ledger(tmp_path)
    first, accepted = ledger.record_event("event-1", {"seq": 1, "text": "hi"})
    assert accepted is True
    redelivered, accepted = ledger.record_event(
        "event-1", {"text": "hi", "seq": 1})
    assert accepted is False and redelivered == first
    with pytest.raises(rc.ReliabilityError, match="different payload"):
        ledger.record_event("event-1", {"seq": 2})
    assert len(ledger.as_dict()["events"]) == 1
    assert ledger.ops == 1


# ===========================================================================
# Retry, partial output and destructive-operation recovery
# ===========================================================================


def test_retry_after_partial_failure_preserves_observed_output(tmp_path):
    now = [1000.0]
    ledger = _ledger(tmp_path, clock=lambda: now[0])
    ledger.register_worker("worker-1")
    ledger.submit("task-1", policy=rc.RetryPolicy(
        max_attempts=3, base_delay=0.5, factor=2.0, max_delay=4.0))
    first = ledger.claim("task-1", "worker-1")
    assert first.attempt == 1
    ledger.record_partial("task-1", "worker-1", "partial-token-")

    decision = ledger.fail("task-1", "worker-1", error="provider timed out",
                           kind=rc.FailureKind.PROVIDER_TIMEOUT)
    assert decision.retry is True and decision.delay == 0.5
    assert decision.task.phase is rc.TaskPhase.RETRY_WAIT
    assert decision.task.partial_output == "partial-token-"
    with pytest.raises(rc.InvalidTransitionError, match="not due"):
        ledger.claim("task-1", "worker-1")

    now[0] += 0.5
    assert ledger.due("task-1") is True
    assert ledger.requeue("task-1").phase is rc.TaskPhase.QUEUED
    second = ledger.claim("task-1", "worker-1")
    assert second.attempt == 2 and second.partial_output == "partial-token-"
    ledger.record_partial("task-1", "worker-1", "final")
    done = ledger.complete("task-1", "worker-1", "full output")
    assert done.task.phase is rc.TaskPhase.COMPLETED
    assert done.task.partial_output == "partial-token-final"
    assert done.task.output == "full output"


def test_completion_redelivery_is_idempotent_but_conflicts_fail_closed(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.register_worker("worker-1")
    ledger.submit("task-1")
    ledger.claim("task-1", "worker-1")
    first = ledger.complete("task-1", "worker-1", "answer")
    again = ledger.complete("task-1", "worker-1", "answer")
    assert again.duplicate is True and again.task == first.task
    with pytest.raises(rc.ReliabilityError, match="conflicting completion"):
        ledger.complete("task-1", "worker-1", "different answer")
    assert len(ledger.tasks(rc.TaskPhase.COMPLETED)) == 1


def test_destructive_operations_are_never_blindly_retried(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.register_worker("worker-1")
    submitted = ledger.submit("danger", destructive=True)
    assert submitted.task.phase is rc.TaskPhase.AWAITING_APPROVAL
    with pytest.raises(rc.ApprovalRequiredError):
        ledger.claim("danger", "worker-1")

    ledger.approve("danger", "approval-1")
    ledger.requeue("danger")
    claimed = ledger.claim("danger", "worker-1")
    assert claimed.approval_token == ""  # consumed on claim
    ledger.record_partial("danger", "worker-1", "side effect may have started")
    crash = ledger.fail("danger", "worker-1", error="worker died",
                        kind=rc.FailureKind.WORKER_CRASH)
    assert crash.retry is False
    assert crash.task.phase is rc.TaskPhase.QUARANTINED
    assert isinstance(rc.ApprovalRequiredError("x"), rc.DestructiveRetryError)
    with pytest.raises(rc.InvalidTransitionError):
        ledger.requeue("danger")  # quarantine is not a retry state

    ledger.approve("danger", "approval-2")
    ledger.requeue("danger")
    retried = ledger.claim("danger", "worker-1")
    assert retried.attempt == 2
    assert retried.partial_output == "side effect may have started"
    ledger.complete("danger", "worker-1", "done")


def test_consumed_approval_does_not_survive_interruption(tmp_path):
    ledger = _ledger(tmp_path, run_id="first")
    ledger.register_worker("worker-1")
    ledger.submit("danger", destructive=True)
    ledger.approve("danger", "approval-1")
    ledger.requeue("danger")
    ledger.claim("danger", "worker-1")
    ledger.interrupt("danger", "worker-1", error="process lost")
    report = ledger.recover()
    assert "danger" in report.approval_resets
    assert ledger.task("danger").phase is rc.TaskPhase.AWAITING_APPROVAL
    with pytest.raises(rc.ApprovalRequiredError):
        ledger.requeue("danger")
    ledger.approve("danger", "approval-2")
    ledger.requeue("danger")
    assert ledger.claim("danger", "worker-1").approval_token == ""


def test_approval_state_persists_across_a_new_process(tmp_path):
    first = _ledger(tmp_path, run_id="first")
    first.submit("danger", destructive=True)
    first.approve("danger", "persisted-approval")
    fresh = _ledger(tmp_path, run_id="second")
    assert fresh.task("danger").approval_token == "persisted-approval"
    fresh.recover()
    assert fresh.task("danger").phase is rc.TaskPhase.AWAITING_APPROVAL
    fresh.register_worker("worker-2")
    fresh.requeue("danger")
    assert fresh.claim("danger", "worker-2").attempt == 1


def test_bounded_retry_backoff_and_terminal_transitions(tmp_path):
    policy = rc.RetryPolicy(max_attempts=3, base_delay=0.1,
                            factor=2.0, max_delay=0.35)
    assert [policy.delay_for(attempt) for attempt in (1, 2, 3, 4)] == [
        0.1, 0.2, 0.35, 0.35]
    assert policy.allows(1) and policy.allows(2) and not policy.allows(3)
    for invalid in ({"max_attempts": 0}, {"max_attempts": rc.MAX_RETRIES + 1},
                    {"factor": 0.5}, {"base_delay": 5.0, "max_delay": 1.0},
                    {"base_delay": float("nan")}):
        with pytest.raises(rc.ValidationError):
            rc.RetryPolicy(**invalid)

    now = [0.0]
    ledger = _ledger(tmp_path, clock=lambda: now[0])
    ledger.register_worker("worker-1")
    ledger.submit("limited", policy=policy)
    delays = []
    for attempt in (1, 2, 3):
        ledger.claim("limited", "worker-1")
        decision = ledger.fail("limited", "worker-1", error="transient")
        delays.append(decision.delay)
        assert decision.retry is (attempt < 3)
        if decision.retry:
            now[0] += decision.delay
            ledger.requeue("limited")
    assert delays == [0.1, 0.2, 0.0]
    final = ledger.task("limited")
    assert final.phase is rc.TaskPhase.FAILED and final.attempt == 3
    assert final.failure_kind == rc.FailureKind.TRANSIENT.value
    with pytest.raises(rc.InvalidTransitionError):
        ledger.requeue("limited")
    with pytest.raises(rc.InvalidTransitionError):
        ledger.claim("limited", "worker-1")

    ledger.submit("invalid-input", policy=policy)
    ledger.claim("invalid-input", "worker-1")
    rejected = ledger.fail("invalid-input", "worker-1",
                           kind=rc.FailureKind.VALIDATION)
    assert rejected.retry is False
    assert rejected.task.phase is rc.TaskPhase.FAILED


def test_cancellation_is_a_terminal_state_with_optional_cascade(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.register_worker("worker-1")
    ledger.submit("parent")
    ledger.submit("child-1", parent_id="parent")
    ledger.submit("child-2", parent_id="parent")
    ledger.claim("parent", "worker-1")
    ledger.cancel("parent", reason="user cancelled", cascade=True)
    assert ledger.task("parent").phase is rc.TaskPhase.CANCELLED
    assert all(t.phase is rc.TaskPhase.CANCELLED for t in ledger.tasks())
    assert ledger.worker("worker-1").in_flight == ()
    with pytest.raises(rc.InvalidTransitionError):
        ledger.claim("child-1", "worker-1")


def test_parent_failure_quarantines_children_during_recovery(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.register_worker("worker-1")
    ledger.submit("parent")
    ledger.submit("child-a", parent_id="parent")
    ledger.submit("child-b", parent_id="parent")
    ledger.claim("parent", "worker-1")
    ledger.fail("parent", "worker-1", kind=rc.FailureKind.VALIDATION)
    report = ledger.recover()
    assert report.quarantined == ("child-a", "child-b")
    assert all(t.phase is rc.TaskPhase.QUARANTINED
               for t in ledger.tasks() if t.parent_id == "parent")
    with pytest.raises(rc.InvalidTransitionError):
        ledger.claim("child-a", "worker-1")


# ===========================================================================
# Worker lifecycle and graceful shutdown
# ===========================================================================


def test_worker_shutdown_stops_claims_and_reports_forced_interrupt(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.register_worker("worker-1")
    ledger.register_worker("worker-2")
    ledger.submit("in-flight")
    ledger.submit("waiting")
    ledger.claim("in-flight", "worker-1")
    ledger.begin_shutdown("worker-1")
    assert ledger.worker("worker-1").phase is rc.WorkerPhase.DRAINING
    with pytest.raises(rc.InvalidTransitionError):
        ledger.claim("waiting", "worker-1")
    assert ledger.claim("waiting", "worker-2").attempt == 1

    sleeps: list[float] = []
    report = ledger.shutdown_worker("worker-1", timeout=0.0,
                                    sleeper=sleeps.append)
    assert sleeps == []
    assert report.timed_out is True
    assert report.interrupted == ("in-flight",)
    assert ledger.task("in-flight").phase is rc.TaskPhase.INTERRUPTED
    assert ledger.worker("worker-1").phase is rc.WorkerPhase.RETIRED
    assert ledger.claim("in-flight", "worker-2").attempt == 2


def test_worker_shutdown_drains_genuinely_in_flight_work(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.register_worker("worker-1")
    ledger.submit("running-task")
    release = threading.Event()
    finished = threading.Event()

    def work() -> None:
        ledger.claim("running-task", "worker-1")
        ledger.record_partial("running-task", "worker-1", "half")
        assert release.wait(timeout=10)
        ledger.complete("running-task", "worker-1", "all done")
        finished.set()

    thread = threading.Thread(target=work)
    thread.start()
    deadline = time.time() + 5
    while not ledger.worker("worker-1").in_flight and time.time() < deadline:
        time.sleep(0.005)
    assert ledger.worker("worker-1").in_flight == ("running-task",)
    timer = threading.Timer(0.05, release.set)
    timer.start()
    report = ledger.shutdown_worker("worker-1", timeout=5.0)
    timer.join(timeout=5)
    thread.join(timeout=10)
    assert finished.is_set()
    assert report.timed_out is False and report.interrupted == ()
    assert ledger.task("running-task").phase is rc.TaskPhase.COMPLETED
    assert ledger.worker("worker-1").phase is rc.WorkerPhase.RETIRED


def test_heartbeat_is_bounded_and_stale_worker_requires_recovery(tmp_path):
    first = _ledger(tmp_path, run_id="first")
    worker = first.register_worker("worker-1")
    assert first.heartbeat("worker-1").heartbeats == worker.heartbeats + 1
    fresh = _ledger(tmp_path, run_id="second")
    with pytest.raises(rc.ReliabilityError, match="another run"):
        fresh.register_worker("worker-1")
    fresh.recover()
    assert fresh.worker("worker-1").phase is rc.WorkerPhase.RETIRED
    assert fresh.register_worker("worker-1").run_id == "second"


# ===========================================================================
# Restart reconstruction from a real killed subprocess
# ===========================================================================

_CHILD_SCRIPT = r'''
import os
import sys
sys.path.insert(0, sys.argv[1])
from keel.reliability_contracts import RecoveryLedger

ledger = RecoveryLedger(sys.argv[2], run_id="child-run")
ledger.register_worker("child-worker")
ledger.submit("crash-task", idempotency_key="crash-key", payload={"step": 1})
ledger.claim("crash-task", "child-worker")
ledger.record_partial("crash-task", "child-worker", "HALF-OUTPUT")
os._exit(7)
'''


def test_recovery_after_process_restart(tmp_path):
    child = tmp_path / "crashing_worker.py"
    child.write_text(_CHILD_SCRIPT, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(child), str(KEEL_SRC), str(tmp_path / "state")],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 7, result.stderr

    parent = _ledger(tmp_path, run_id="parent-run")
    task_before = parent.task("crash-task")
    assert task_before.phase is rc.TaskPhase.RUNNING
    assert task_before.partial_output == "HALF-OUTPUT"

    report = parent.recover()
    assert "crash-task" in report.interrupted
    assert "child-worker" in report.workers_retired
    task = parent.task("crash-task")
    assert task.phase is rc.TaskPhase.INTERRUPTED
    assert task.partial_output == "HALF-OUTPUT"

    parent.register_worker("parent-worker")
    assert parent.requeue("crash-task").phase is rc.TaskPhase.QUEUED
    resumed = parent.claim("crash-task", "parent-worker")
    assert resumed.attempt == 2 and "HALF-OUTPUT" in resumed.partial_output
    done = parent.complete("crash-task", "parent-worker", "finished-after-restart")
    assert done.task.phase is rc.TaskPhase.COMPLETED
    assert done.task.output == "finished-after-restart"
    assert parent.recover().interrupted == ()


def test_truncated_tail_from_killed_writer_is_skipped(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.submit("task-1")
    ledger.submit("task-2")
    with open(ledger.path, "ab") as handle:
        handle.write(b'{"op":"task","task":{"task_id":')
    fresh = _ledger(tmp_path)
    assert fresh.tail_recovered == 1
    assert [t.task_id for t in fresh.tasks()] == ["task-1", "task-2"]
    assert fresh.recover().tail_recovered == 1


def test_corrupt_log_line_fails_closed(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.submit("task-1")
    with open(ledger.path, "ab") as handle:
        handle.write(b'{"op":"unknown-op"}\n')
    with pytest.raises(rc.ReliabilityError, match="unknown recovery log op"):
        _ledger(tmp_path)


# ===========================================================================
# Runtime lifecycle ordering
# ===========================================================================


def test_runtime_lifecycle_shutdown_order_is_reverse_and_idempotent(tmp_path):
    calls: list[tuple[str, str]] = []

    def initializer(name):
        return lambda: calls.append(("init", name))

    def closer(name):
        return lambda: calls.append(("close", name))

    ledger = _ledger(tmp_path)
    ledger.register_worker("worker-1")
    runtime = rc.RuntimeLifecycle(
        {"api": initializer("api"), "db": initializer("db")},
        cleanup={"api": closer("api"), "db": closer("db")},
        ledger=ledger, worker_ids=("worker-1",), db_names=("db",))
    runtime.startup()
    trace = runtime.shutdown()
    assert list(trace[:6]) == [
        ("register_services", "api"), ("initialize", "api"),
        ("register_services", "db"), ("initialize", "db"),
        ("recover", "ledger"), ("serve", "runtime")]
    assert list(trace[6:]) == [
        ("drain", "runtime"), ("stop_workers", "runtime"),
        ("close_db", "db"), ("close_resources", "api")]
    assert calls == [("init", "api"), ("init", "db"),
                     ("close", "db"), ("close", "api")]
    assert runtime.shutdown() == trace
    assert calls == [("init", "api"), ("init", "db"),
                     ("close", "db"), ("close", "api")]


def test_runtime_startup_failure_cleans_up_in_reverse(tmp_path):
    calls: list[str] = []

    def ok():
        calls.append("init:api")

    def broken():
        calls.append("init:broken")
        raise RuntimeError("configuration missing")

    runtime = rc.RuntimeLifecycle(
        {"api": ok, "broken": broken,
         "never": lambda: calls.append("init:never")},
        cleanup={"api": lambda: calls.append("close:api")})
    with pytest.raises(rc.ReliabilityError, match="startup failed"):
        runtime.startup()
    assert "init:never" not in calls
    assert calls.index("close:api") > calls.index("init:broken")
    assert calls == ["init:api", "init:broken", "close:api"]
    assert not any(name == "serve" for _stage, name in runtime.trace)


def test_recovery_ledger_snapshot_is_deterministic(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.submit("task-1", payload={"a": 1})
    ledger.register_worker("worker-1")
    first = json.dumps(ledger.as_dict(), sort_keys=True)
    rebuilt = _ledger(tmp_path)
    assert json.dumps(rebuilt.as_dict(), sort_keys=True) == first
