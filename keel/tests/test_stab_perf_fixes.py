"""Regressions for two measured stabilization performance defects.

1. Steering retention was unbounded: 20,000 undrained messages stayed in memory
   (~6.3 MB RSS). Retention is now bounded, oldest-first, with pinned
   security/control context and observable overflow.
2. Timed-out routine workers were abandoned: five 0.4 s timeouts against a
   slow provider left 1, 2, 3, 4, 4 live ``fleet-routine-*`` threads, and the
   error text said "after 0s". Workers are now cancellation-signalled, joined,
   and admitted through a bounded gate; the text reports real elapsed time.

No production module outside the two owned files is modified.
"""

from __future__ import annotations

import re
import threading
import time
import tracemalloc

import pytest

import keel.fleet.scheduler as scheduler
import keel.steering as steering
from keel.fleet import turn_core
from keel.fleet.service import FleetStore

SteeringController = steering.SteeringController
SteeringError = steering.SteeringError
SteeringMode = steering.SteeringMode


# ---------------------------------------------------------------------------
# 1. bounded steering retention
# ---------------------------------------------------------------------------

def test_steering_evicts_oldest_first_and_reports_overflow():
    controller = SteeringController(max_messages=32, max_protected=8)
    sent = [controller.submit_message(f"m{i}", SteeringMode.QUEUE)
            for i in range(100)]

    retained = controller.all_messages()
    assert len(retained) == 32
    assert [m.seq for m in retained] == [m.seq for m in sent[-32:]]
    assert [m.text for m in retained] == [f"m{i}" for i in range(68, 100)]

    # Every retained message is still deliverable (no stale bucket entry).
    assert len(controller.drain_queue()) == 32
    assert controller.drain_queue() == ()
    assert controller.overflow_count == 68
    dropped = controller.dropped_messages()
    assert len(dropped) == 68
    assert dropped[0][0] == 0 and dropped[-1][0] == 67
    assert dropped[0][1] == "m0"


def test_steering_pins_security_context_and_newest_messages():
    controller = SteeringController(max_messages=8, max_protected=4)
    for i in range(10):
        controller.submit_message(f"old-{i}", SteeringMode.QUEUE)
    security = controller.submit_message("do not drop: security token",
                                         SteeringMode.QUEUE, tags={"security"})
    untrusted = controller.submit_message("untrusted context needed next turn",
                                          SteeringMode.QUEUE, tags=["untrusted"])
    for i in range(10):
        controller.submit_message(f"new-{i}", SteeringMode.QUEUE)

    retained = controller.all_messages()
    texts = [m.text for m in retained]
    assert len(retained) <= controller.max_messages
    assert security in retained and untrusted in retained
    assert "new-9" in texts and "new-8" in texts
    assert "old-0" not in texts
    # Oldest-first eviction applies to ordinary entries; the six newest
    # ordinary entries plus the two pinned entries survive.
    assert [m.text for m in retained if not m.tags] == [
        f"new-{i}" for i in range(4, 10)]
    assert controller.overflow_count == 14


def test_steering_pins_abort_and_resume_pending_messages():
    controller = SteeringController(max_messages=6, max_protected=4)
    for i in range(6):
        controller.submit_message(f"filler-{i}", SteeringMode.QUEUE)
    aborting = controller.submit_message("stop", SteeringMode.ABORT_RESUME)
    late = controller.submit_message("needed after resume",
                                     SteeringMode.STEER_AT_BOUNDARY)
    for i in range(20):
        controller.submit_message(f"later-{i}", SteeringMode.QUEUE)

    retained = controller.all_messages()
    assert aborting in retained
    assert late in retained
    assert controller.pending_resume_messages() == (aborting, late)
    assert len(retained) <= controller.max_messages
    assert "later-19" in [m.text for m in retained]


def test_steering_protected_limit_fails_closed_without_consuming_seq():
    controller = SteeringController(max_messages=8, max_protected=2)
    assert getattr(steering, "PROTECTED_TAGS", frozenset()) <= {
        "security", "sensitive", "untrusted", "audit"}
    first = controller.submit_message("p1", tags="security")
    second = controller.submit_message("p2", tags={"sensitive"})
    with pytest.raises(SteeringError, match="protected"):
        controller.submit_message("p3", tags={"security"})
    assert controller.all_messages() == (first, second)
    # A rejected submission leaves no seq gap.
    ordinary = controller.submit_message("ordinary")
    assert ordinary.seq == 2
    with pytest.raises(SteeringError, match="positive integer"):
        SteeringController(max_messages=0)
    with pytest.raises(SteeringError, match="cannot exceed"):
        SteeringController(max_messages=4, max_protected=5)


def test_steering_memory_does_not_grow_with_unbounded_submissions():
    controller = SteeringController(max_messages=256, max_protected=16)
    tracemalloc.start()
    try:
        for i in range(20_000):
            controller.submit_message(f"message-{i}-" + "x" * 80,
                                      SteeringMode.QUEUE)
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    retained = controller.all_messages()
    assert len(retained) == 256
    assert retained[-1].text.startswith("message-19999-")
    assert controller.overflow_count == 20_000 - 256
    # The old controller retained all 20k objects (peak ~5.7 MB traced,
    # +6.3 MB RSS). A bounded window must stay far below that.
    assert current < 2_000_000
    assert peak < 2_000_000


# ---------------------------------------------------------------------------
# 2. safe timeout cancellation and bounded workers
# ---------------------------------------------------------------------------

def _routine_for(store):
    bot = store.create_bot(name="routine-bot", engine="echo")
    created = store.create_routine(name="r", bot_id=bot["id"], prompt="p",
                                   cron_expr="0 0 * * *")
    return store.get_routine(created["id"])


def _cooperative_fake(monkeypatch):
    """execute_turn stand-in that honours the real cancellation primitive."""
    def fake(store, agent, prompt, **kwargs):
        bot_id = agent["id"]
        event = turn_core._register_active_turn(bot_id)
        deadline = time.monotonic() + 5.0
        try:
            while not event.wait(0.01):
                if time.monotonic() > deadline:
                    break
            return {"ok": True, "assistant_text": "cancelled cleanly"}
        finally:
            turn_core._unregister_active_turn(bot_id, event)

    monkeypatch.setattr(turn_core, "execute_turn", fake)


def _timeout_settings(monkeypatch, timeout="0.4", workers="2", grace="0.5"):
    monkeypatch.setenv("KEEL_FLEET_ROUTINE_TIMEOUT_S", timeout)
    monkeypatch.setenv("KEEL_FLEET_ROUTINE_MAX_WORKERS", workers)
    monkeypatch.setenv("KEEL_FLEET_ROUTINE_CANCEL_GRACE_S", grace)
    getattr(scheduler, "reset_workers_for_tests", lambda: None)()


def _live_routine_threads() -> list[str]:
    return [t.name for t in threading.enumerate()
            if t.name.startswith("fleet-routine-")]


def test_timed_out_workers_are_cancelled_joined_and_report_real_duration(
        tmp_path, monkeypatch):
    _timeout_settings(monkeypatch)
    _cooperative_fake(monkeypatch)
    store = FleetStore(tmp_path / "cancel.db")
    routine = _routine_for(store)
    try:
        for index in range(5):
            outcome = scheduler.execute_routine(store, routine)
            assert outcome["terminal_reason"] == "timeout"
            assert outcome["ok"] is False
            assert "after 0s" not in outcome["error"]
            assert re.search(r"timed out after 0\.\d\ds", outcome["error"])
            assert 0.30 <= outcome["elapsed_s"] <= 1.5
            assert outcome["worker_stopped"] is True
            assert outcome["cancel_requested"] is True
            # No accumulation across successive timeouts.
            assert _live_routine_threads() == []
            assert scheduler.active_worker_count() == 0
            assert store.get_routine(routine["id"])["running"] == 0
    finally:
        store.close()
    assert _live_routine_threads() == []


def test_concurrent_timeouts_respect_worker_cap_and_do_not_leak(
        tmp_path, monkeypatch):
    _timeout_settings(monkeypatch, timeout="0.15", workers="2", grace="0.05")
    # Provider that ignores cancellation for a bounded time: the cap, not
    # cooperation, is what prevents unbounded thread accumulation.
    def stubborn_fake(store, agent, prompt, **kwargs):
        time.sleep(0.35)
        return {"ok": True, "assistant_text": "late"}

    monkeypatch.setattr(turn_core, "execute_turn", stubborn_fake)
    store = FleetStore(tmp_path / "cap.db")
    routine = _routine_for(store)
    peak_workers = [0]
    stop_monitor = threading.Event()

    def monitor():
        while not stop_monitor.is_set():
            peak_workers[0] = max(peak_workers[0],
                                  getattr(scheduler, "active_worker_count",
                                          lambda: 0)())
            time.sleep(0.005)

    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        threads = [threading.Thread(
            target=lambda: scheduler.execute_routine(store, routine))
            for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive()
    finally:
        stop_monitor.set()
        watcher.join(timeout=2)
        store.close()

    assert 1 <= peak_workers[0] <= 2
    deadline = time.monotonic() + 3.0
    while scheduler.active_worker_count() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert scheduler.active_worker_count() == 0
    assert _live_routine_threads() == []
