"""Behavioural tests for keel.backend_events.

Covers the closed typed event union, versioned round-trips, durable replay,
idempotent/concurrent publishing, fail-closed corrupt logs, and network-free
delivery attempts with retry / terminal / cancellation semantics.
"""

from __future__ import annotations

import concurrent.futures
import json
import threading
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from keel.backend_events import (
    SCHEMA_ID,
    SCHEMA_VERSION,
    CorruptRecordError,
    DeliveryStateError,
    DeliveryTracker,
    DuplicateDeliveryError,
    DuplicateEventError,
    EventBus,
    EventBusError,
    InvalidEventError,
    SessionStarted,
    TaskCreated,
    UnknownEventKindError,
    UnsupportedEventVersionError,
    BackendEvent,
    EVENT_TYPES,
    build_event,
    compute_backoff,
    describe_event,
    describe_event_schema,
    event_from_dict,
    get_event_class,
)

SAMPLES: dict[str, dict] = {
    "session_started": dict(session_id="s1", cwd="/work"),
    "task_created": dict(session_id="s1", task_id="t1", title="write tests"),
    "task_delegated": dict(session_id="s1", task_id="t1", agent_id="a1"),
    "tool_invoked": dict(session_id="s1", tool_use_id="call1", tool_name="Read"),
    "permission_decided": dict(session_id="s1", tool_use_id="call1",
                               decision="allow", reason="verified"),
    "approval_requested": dict(session_id="s1", approval_id="ap1",
                               tool_use_id="call1", prompt="allow?"),
    "approval_resolved": dict(session_id="s1", approval_id="ap1", decision="allow"),
    "approval_consumed": dict(session_id="s1", approval_id="ap1"),
    "approval_revoked": dict(session_id="s1", approval_id="ap1", reason="expired"),
    "provider_failed": dict(session_id="s1", provider_id="p1",
                            error_code="429", retryable=True),
    "job_queued": dict(job_id="j1", session_id="s1"),
    "job_started": dict(job_id="j1", session_id="s1"),
    "job_completed": dict(job_id="j1", session_id="s1", status="ok"),
    "job_cancelled": dict(job_id="j1", session_id="s1", reason="user"),
    "event_delivered": dict(delivery_id="d1", target="ui",
                            delivered_event_id="ev-source", status="delivered"),
    "extension_loaded": dict(extension_id="x1", version="1.2.3"),
    "extension_unloaded": dict(extension_id="x1", reason="disabled"),
    "error_recorded": dict(error_id="err1", severity="error", message="boom"),
}


def sample(kind: str, suffix: str = "") -> BackendEvent:
    return build_event(kind, event_id=f"ev-{kind}{suffix}",
                       metadata=[("actor", "test")], **SAMPLES[kind])


# ---------------------------------------------------------------------------
# Typed event union
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(SAMPLES))
def test_round_trip_every_event_type(kind):
    event = sample(kind)
    envelope = event.to_dict()
    assert envelope["schema"] == SCHEMA_ID
    assert envelope["version"] == SCHEMA_VERSION
    assert envelope["kind"] == kind
    assert envelope["data"]["metadata"] == [["actor", "test"]]

    # Force a real serialisation boundary (JSON turns tuples into arrays).
    decoded = event_from_dict(json.loads(json.dumps(envelope)))
    assert type(decoded) is type(event)
    assert decoded == event
    assert decoded.metadata == (("actor", "test"),)
    assert decoded.to_dict() == envelope
    assert type(event).from_dict(envelope) == event


def test_all_kinds_registered_and_schema_is_machine_readable():
    assert {get_event_class(k) for k in SAMPLES} == set(EVENT_TYPES)
    assert all(get_event_class(k).KIND == k for k in SAMPLES)
    schema = describe_event_schema()
    assert schema["schema"] == SCHEMA_ID
    assert schema["version"] == SCHEMA_VERSION
    assert set(schema["kinds"]) == set(SAMPLES)
    assert set(schema["events"]) == set(SAMPLES)
    assert schema["envelope"]["required"] == ["schema", "version", "kind", "data"]
    for kind, description in schema["events"].items():
        names = {f["name"] for f in description["fields"]}
        assert names >= set(SAMPLES[kind]) | {"event_id", "metadata"}
        assert "event_id" in description["required_ids"]
        assert all(isinstance(f["type"], str) for f in description["fields"])
        assert next(f for f in description["fields"]
                    if f["name"] == "event_id")["required"] is True
    json.dumps(schema)  # machine-readable, no exotic values


@pytest.mark.parametrize("kind", ["nope", "", None, 42, "SESSION_STARTED"])
def test_unknown_kind_rejected(kind):
    with pytest.raises(UnknownEventKindError):
        event_from_dict(dict(sample("session_started").to_dict(), kind=kind))
    with pytest.raises(UnknownEventKindError):
        SessionStarted.from_dict(dict(sample("session_started").to_dict(), kind=kind))
    with pytest.raises(UnknownEventKindError):
        get_event_class(kind)
    with pytest.raises(UnknownEventKindError):
        build_event(kind, event_id="e1")


@pytest.mark.parametrize("version", [None, 0, 2, 99, "1", True, 1.0])
def test_unsupported_version_rejected(version):
    envelope = sample("task_created").to_dict()
    envelope["version"] = version
    with pytest.raises(UnsupportedEventVersionError):
        event_from_dict(envelope)
    with pytest.raises(UnsupportedEventVersionError):
        TaskCreated.from_dict(envelope)


def test_missing_version_rejected():
    envelope = sample("task_created").to_dict()
    del envelope["version"]
    with pytest.raises(UnsupportedEventVersionError):
        event_from_dict(envelope)


def test_invalid_envelopes_rejected():
    good = sample("session_started").to_dict()

    missing = dict(good, data={k: v for k, v in good["data"].items()
                               if k != "session_id"})
    with pytest.raises(InvalidEventError):
        event_from_dict(missing)

    extra = dict(good, data=dict(good["data"], surprise=True))
    with pytest.raises(InvalidEventError):
        event_from_dict(extra)

    wrong_type = dict(good, data=dict(good["data"], session_id=7))
    with pytest.raises(InvalidEventError):
        event_from_dict(wrong_type)

    wrong_metadata = dict(good, data=dict(good["data"], metadata=[["actor", 3]]))
    with pytest.raises(InvalidEventError):
        event_from_dict(wrong_metadata)

    with pytest.raises(InvalidEventError):
        event_from_dict([1, 2, 3])
    with pytest.raises(InvalidEventError):
        event_from_dict(dict(good, schema="some.other.schema"))
    with pytest.raises(InvalidEventError):
        event_from_dict(dict(good, surprise=True))


def test_kind_class_mismatch_rejected():
    other = sample("task_created").to_dict()
    with pytest.raises(InvalidEventError):
        SessionStarted.from_dict(other)
    assert event_from_dict(other) == sample("task_created")


def test_bad_ids_rejected_at_construction():
    with pytest.raises(ValueError):
        SessionStarted(event_id="", session_id="s1")
    with pytest.raises(ValueError):
        SessionStarted(event_id="e1", session_id="")
    with pytest.raises(ValueError):
        SessionStarted(event_id="e1", session_id="s1", metadata=[("only",)])


def test_events_are_frozen_and_union_is_closed():
    event = sample("session_started")
    with pytest.raises(FrozenInstanceError):
        event.event_id = "changed"
    with pytest.raises(TypeError):

        class RogueEvent(BackendEvent):
            KIND = "rogue"


def test_cross_module_helpers_do_not_share_mutable_state():
    # Producer side: caller-owned mutable inputs are copied into the event.
    pairs = [("actor", "producer")]
    event = build_event("session_started", event_id="cross-1",
                        session_id="s1", metadata=pairs)
    pairs[0] = ("actor", "mutated")
    pairs.append(("extra", "value"))
    assert event.metadata == (("actor", "producer"),)

    # Consumer side: a summary is derived, never aliased to the event.
    summary = describe_event(event)
    assert summary["kind"] == "session_started"
    assert summary["ids"] == {"event_id": "cross-1", "session_id": "s1"}
    summary["ids"]["session_id"] = "changed"
    summary["metadata"].append(("x", "y"))
    assert event.session_id == "s1"
    assert event.metadata == (("actor", "producer"),)

    # Serialisation boundary creates an independent, equal object.
    envelope = event.to_dict()
    envelope["data"]["metadata"][0][1] = "tampered"
    parsed = event_from_dict(event.to_dict())
    assert parsed == event
    assert parsed is not event
    assert parsed.metadata is not event.metadata


# ---------------------------------------------------------------------------
# Durable event bus
# ---------------------------------------------------------------------------


def test_replay_from_new_bus_object(tmp_path: Path):
    bus = EventBus(tmp_path)
    events = [sample("session_started"), sample("task_created", "-2"),
              sample("job_queued", "-3")]
    for event in events:
        assert bus.publish(event) is True

    assert bus.events == tuple(events)
    fresh = EventBus(tmp_path)  # a brand-new object over the same state_root
    assert fresh.replay() == tuple(events)
    assert fresh.replay(1) == tuple(events[1:])
    assert fresh.events == tuple(events)

    seen: list[BackendEvent] = []
    fresh.subscribe(seen.append).drain()
    assert seen == events


def test_duplicate_event_id_detection_is_idempotent(tmp_path: Path):
    bus = EventBus(tmp_path)
    event = sample("approval_requested")
    assert bus.publish(event) is True
    assert bus.publish(event) is False  # identical retry: no new record

    other_bus = EventBus(tmp_path)
    assert other_bus.publish(event) is False
    assert len(other_bus.events) == 1

    conflicting = build_event("approval_requested", event_id=event.event_id,
                              session_id="different", approval_id="ap1")
    with pytest.raises(DuplicateEventError):
        bus.publish(conflicting)
    assert bus.events == (event,)
    assert len(bus._store.records) == 1


def test_concurrent_publish_twenty_threads(tmp_path: Path):
    bus = EventBus(tmp_path)
    seen: list[str] = []
    sub = bus.subscribe(lambda event: seen.append(event.event_id))
    barrier = threading.Barrier(20)

    def worker(index: int) -> bool:
        event = sample("tool_invoked", f"-{index:02d}")
        barrier.wait(timeout=10)
        # Each thread uses its own bus object; the path-keyed lock is shared.
        return EventBus(tmp_path).publish(event)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(worker, range(20)))

    assert results == [True] * 20
    published = bus.events
    assert len(published) == 20
    expected_ids = {f"ev-tool_invoked-{i:02d}" for i in range(20)}
    assert {e.event_id for e in published} == expected_ids
    assert [r["seq"] for r in bus._store.records] == list(range(1, 21))
    # Subscribers observe a single deterministic, sequence-ordered stream.
    assert seen == [e.event_id for e in published]
    assert sub.cursor == 20 and sub.pending() == 0 and sub.delivered == 20


def test_subscriber_cursors_and_replay_control(tmp_path: Path):
    bus = EventBus(tmp_path)
    first, second = sample("job_queued", "-a"), sample("job_queued", "-b")
    bus.publish(first)
    bus.publish(second)

    seen: list[str] = []
    sub = bus.subscribe(lambda event: seen.append(event.event_id), from_cursor=1)
    assert sub.pending() == 1
    assert sub.drain() == 1
    assert seen == [second.event_id]

    third = sample("job_started", "-c")
    bus.publish(third)
    assert seen == [second.event_id, third.event_id]

    sub.cancel()
    bus.publish(sample("job_completed", "-d"))
    assert len(seen) == 2  # cancelled subscriber receives nothing
    assert sub.pending() == 1  # and does not silently lose the event

    latest = bus.subscribe(lambda event: seen.append(event.event_id), replay=False)
    assert latest.cursor == len(bus.events) and latest.pending() == 0


def test_failing_handler_does_not_advance_cursor(tmp_path: Path):
    bus = EventBus(tmp_path)
    bus.publish(sample("extension_loaded"))

    def explode(event: BackendEvent) -> None:
        raise RuntimeError("handler failed")

    sub = bus.subscribe(explode, replay=False)
    with pytest.raises(RuntimeError, match="handler failed"):
        bus.publish(sample("extension_unloaded"))
    assert sub.cursor == 1  # at-least-once, no silent loss

    delivered: list[str] = []
    sub.callback = lambda event: delivered.append(event.event_id)
    assert sub.drain() == 1
    assert delivered == ["ev-extension_unloaded"]


@pytest.mark.parametrize("mode", ["bad_json", "edited", "truncated", "missing_head"])
def test_corrupt_log_fails_closed(tmp_path: Path, mode: str):
    bus = EventBus(tmp_path)
    bus.publish(sample("session_started"))
    bus.publish(sample("task_created", "-2"))
    log = tmp_path / "backend-events.jsonl"
    head = tmp_path / "backend-events.jsonl.head"

    if mode == "bad_json":
        lines = log.read_text(encoding="utf-8").splitlines()
        lines[0] = "{not json"
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif mode == "edited":
        text = log.read_text(encoding="utf-8")
        log.write_text(text.replace('"/work"', '"/elsewhere"', 1), encoding="utf-8")
    elif mode == "truncated":
        lines = log.read_text(encoding="utf-8").splitlines()
        log.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    else:
        head.unlink()

    with pytest.raises(CorruptRecordError):
        EventBus(tmp_path)
    with pytest.raises(CorruptRecordError):
        bus.publish(sample("error_recorded"))
    with pytest.raises(CorruptRecordError):
        bus.replay()


# ---------------------------------------------------------------------------
# Delivery tracking (no network, no fake success)
# ---------------------------------------------------------------------------


def test_delivery_retry_backoff_and_terminal_failure(tmp_path: Path):
    tracker = DeliveryTracker(tmp_path)
    initial = tracker.register("ev-1", "worker", max_attempts=3,
                               base_delay=0.1, backoff_factor=2.0, max_delay=0.4)
    assert (initial.status, initial.attempts, initial.retry_count) == ("pending", 0, 0)

    first = tracker.record_attempt("ev-1", "worker", ok=False, error="500")
    assert (first.status, first.attempts, first.retry_count) == ("pending", 1, 1)
    assert first.next_delay == 0.1

    second = tracker.record_attempt("ev-1", "worker", ok=False, error="500")
    assert (second.status, second.attempts, second.retry_count) == ("pending", 2, 2)
    assert second.next_delay == 0.2

    terminal = tracker.record_attempt("ev-1", "worker", ok=False, error="500")
    assert terminal.status == "terminal"
    assert terminal.attempts == 3 and terminal.retry_count == 2
    assert terminal.next_delay == 0.0 and terminal.is_success is False

    with pytest.raises(DeliveryStateError):
        tracker.record_attempt("ev-1", "worker", ok=True)  # no fake success

    history = tracker.history()
    assert [r["op"] for r in history] == ["register", "attempt", "attempt", "attempt"]
    assert all(r["state"]["status"] != "delivered" for r in history)
    assert DeliveryTracker(tmp_path).state("ev-1", "worker") == terminal


def test_delivery_cancel_prevents_later_success(tmp_path: Path):
    tracker = DeliveryTracker(tmp_path)
    tracker.register("ev-2", "ui")
    first = tracker.record_attempt("ev-2", "ui", ok=False, error="timeout")
    assert first.next_delay == 0.05

    cancelled = tracker.cancel("ev-2", "ui", reason="user aborted")
    assert cancelled.status == "cancelled" and cancelled.reason == "user aborted"
    assert cancelled.next_delay == 0.0
    assert tracker.cancel("ev-2", "ui") == cancelled  # idempotent

    with pytest.raises(DeliveryStateError):
        tracker.record_attempt("ev-2", "ui", ok=True)
    assert tracker.state("ev-2", "ui").status == "cancelled"
    assert all(r["state"]["status"] != "delivered" for r in tracker.history())
    assert tracker.pending() == ()

    with pytest.raises(DeliveryStateError):
        tracker.record_attempt("unknown", "ui", ok=False)


def test_delivery_success_and_duplicate_registration(tmp_path: Path):
    tracker = DeliveryTracker(tmp_path)
    tracker.register("ev-3", "hook")
    with pytest.raises(DuplicateDeliveryError):
        tracker.register("ev-3", "hook")
    assert len(tracker.history()) == 1

    other = tracker.register("ev-3", "other-hook")
    assert other.target == "other-hook"
    delivered = tracker.record_attempt("ev-3", "hook", ok=True)
    assert delivered.status == "delivered" and delivered.is_success is True
    assert delivered.attempts == 1 and delivered.next_delay == 0.0
    assert tracker.state("ev-3", "hook") == delivered
    assert [s.target for s in tracker.pending()] == ["other-hook"]

    fresh = DeliveryTracker(tmp_path)
    assert fresh.state("ev-3", "hook") == delivered
    with pytest.raises(DeliveryStateError):
        fresh.cancel("ev-3", "hook")


def test_backoff_is_pure_deterministic_and_bounded():
    kwargs = dict(base_delay=0.1, backoff_factor=2.0, max_delay=0.5)
    assert compute_backoff(1, **kwargs) == pytest.approx(0.1)
    assert compute_backoff(2, **kwargs) == pytest.approx(0.2)
    assert compute_backoff(3, **kwargs) == pytest.approx(0.4)
    assert compute_backoff(4, **kwargs) == pytest.approx(0.5)  # capped
    assert compute_backoff(9, **kwargs) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        compute_backoff(0, **kwargs)


def test_delivery_corrupt_log_fails_closed(tmp_path: Path):
    tracker = DeliveryTracker(tmp_path)
    tracker.register("ev-4", "sink")
    head = tmp_path / "backend-delivery.jsonl.head"
    head.write_text('{"count": 99, "digest": "x"}', encoding="utf-8")
    with pytest.raises(CorruptRecordError):
        DeliveryTracker(tmp_path)
    with pytest.raises(CorruptRecordError):
        tracker.register("ev-5", "sink")


def test_event_bus_rejects_non_events(tmp_path: Path):
    bus = EventBus(tmp_path)
    with pytest.raises(TypeError):
        bus.publish({"event_id": "e1"})
    with pytest.raises(TypeError):
        bus.subscribe("not callable")
    with pytest.raises(EventBusError):
        bus.drain(object())  # type: ignore[arg-type]
