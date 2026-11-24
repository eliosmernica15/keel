"""X1.13 — steering and interrupt (mid-turn message handling).

The controller is the session-facing primitive for three ways to inject a
message while a turn is running:

* ``QUEUE`` — leave it queued for the next turn (never delivered mid-turn);
* ``STEER_AT_BOUNDARY`` — deliver it at the next tool boundary;
* ``ABORT_RESUME`` — cancel the turn, keep the partial output byte-for-byte,
  and hand the message back on :meth:`resume`.

Everything is in-process and stdlib-only; no storage or network is involved.
"""

from __future__ import annotations

import threading
import time
from dataclasses import FrozenInstanceError

import pytest

from keel.steering import (
    SteeringController,
    SteeringError,
    SteeringMessage,
    SteeringMode,
    SteeringSnapshot,
)


def test_modes_are_an_enum_with_the_three_required_values():
    assert [m.value for m in SteeringMode] == [
        "queue", "steer_at_boundary", "abort_resume"]
    assert SteeringController.QUEUE is SteeringMode.QUEUE
    assert SteeringController.STEER_AT_BOUNDARY is SteeringMode.STEER_AT_BOUNDARY
    assert SteeringController.ABORT_RESUME is SteeringMode.ABORT_RESUME


def test_no_message_boundary_returns_none():
    controller = SteeringController()
    assert controller.poll_boundary() is None
    assert controller.poll_boundary() is None
    assert not controller.cancelled
    assert not controller.cancel_event.is_set()


def test_queue_messages_are_not_delivered_at_boundary():
    controller = SteeringController()
    message = controller.submit_message("after this turn", SteeringMode.QUEUE)
    assert controller.poll_boundary() is None
    assert controller.drain_queue() == (message,)
    assert controller.drain_queue() == ()


def test_steer_at_boundary_delivers_in_submission_order():
    controller = SteeringController()
    first = controller.submit_message("first steer", SteeringMode.STEER_AT_BOUNDARY)
    second = controller.submit_message("second steer", SteeringMode.STEER_AT_BOUNDARY)
    assert controller.poll_boundary() == first
    assert controller.poll_boundary() == second
    assert controller.poll_boundary() is None
    assert controller.delivered_messages() == (first, second)


def test_boundary_poll_drains_one_message_at_a_time():
    controller = SteeringController()
    for index in range(4):
        controller.submit_message(f"steer-{index}", SteeringMode.STEER_AT_BOUNDARY)
    got = [controller.poll_boundary() for _ in range(5)]
    assert [m.text for m in got[:4]] == ["steer-0", "steer-1", "steer-2", "steer-3"]
    assert got[-1] is None
    assert [m.seq for m in got[:4]] == [0, 1, 2, 3]


def test_explicit_mode_overrides_the_current_mode():
    controller = SteeringController()
    controller.set_mode(SteeringMode.QUEUE)
    steer = controller.submit_message("explicit", SteeringMode.STEER_AT_BOUNDARY)
    assert controller.poll_boundary() == steer
    queued = controller.submit_message("default", None)
    assert controller.drain_queue() == (queued,)


def test_mode_transitions_change_default_routing():
    controller = SteeringController()
    assert controller.mode is SteeringMode.QUEUE

    controller.set_mode(SteeringMode.STEER_AT_BOUNDARY)
    assert controller.mode is SteeringMode.STEER_AT_BOUNDARY
    steered = controller.submit_message("steered by default")
    assert controller.poll_boundary() == steered

    controller.set_mode(SteeringMode.QUEUE)
    queued = controller.submit_message("queued by default")
    assert controller.poll_boundary() is None
    assert controller.drain_queue() == (queued,)

    controller.set_mode(SteeringMode.ABORT_RESUME)
    aborted = controller.submit_message("interrupt by default")
    assert controller.cancelled
    result = controller.resume()
    assert result.messages == (aborted,)
    assert controller.mode is SteeringMode.ABORT_RESUME
    assert not controller.cancelled


def test_string_modes_are_accepted_and_invalid_modes_rejected():
    controller = SteeringController()
    message = controller.submit_message("from string", "STEER_AT_BOUNDARY")
    assert message.mode is SteeringMode.STEER_AT_BOUNDARY
    assert controller.poll_boundary() == message
    with pytest.raises(SteeringError):
        controller.submit_message("bad", "not_a_mode")
    with pytest.raises(SteeringError):
        controller.set_mode("bogus")


def test_messages_are_immutable_value_objects():
    controller = SteeringController()
    message = controller.submit_message("hello", SteeringMode.QUEUE)
    assert isinstance(message, SteeringMessage)
    with pytest.raises(FrozenInstanceError):
        message.text = "mutated"


def test_concurrent_submits_are_ordered_and_lossless():
    controller = SteeringController()
    threads: list[threading.Thread] = []
    barrier = threading.Barrier(12)

    def submit(worker: int) -> None:
        barrier.wait()
        for index in range(50):
            controller.submit_message(f"w{worker}-{index}", SteeringMode.QUEUE)

    for worker in range(12):
        thread = threading.Thread(target=submit, args=(worker,))
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()

    queued = controller.drain_queue()
    assert len(queued) == 12 * 50
    assert [m.seq for m in queued] == list(range(12 * 50))
    assert len({m.text for m in queued}) == 12 * 50
    assert len(controller.all_messages()) == 12 * 50


def test_concurrent_boundary_delivery_has_no_duplicates():
    controller = SteeringController()
    threads: list[threading.Thread] = []
    barrier = threading.Barrier(12)  # 8 submitters + 4 consumers
    delivered: list[SteeringMessage] = []
    deliver_lock = threading.Lock()
    submits_done = threading.Event()

    def submit(worker: int) -> None:
        barrier.wait()
        for index in range(40):
            controller.submit_message(
                f"w{worker}-{index}", SteeringMode.STEER_AT_BOUNDARY)

    def consume() -> None:
        barrier.wait()
        while True:
            message = controller.poll_boundary()
            if message is None:
                if submits_done.is_set():
                    return
                time.sleep(0)
                continue
            with deliver_lock:
                delivered.append(message)

    for worker in range(8):
        thread = threading.Thread(target=submit, args=(worker,))
        thread.start()
        threads.append(thread)
    consumers: list[threading.Thread] = []
    for _ in range(4):
        thread = threading.Thread(target=consume)
        thread.start()
        threads.append(thread)
        consumers.append(thread)
    for thread in threads[:8]:
        thread.join(timeout=15)
        assert not thread.is_alive()
    submits_done.set()
    for thread in consumers:
        thread.join(timeout=15)
        assert not thread.is_alive()

    assert len(delivered) == 8 * 40
    assert sorted(m.seq for m in delivered) == list(range(8 * 40))
    assert controller.poll_boundary() is None


def test_abort_sets_cancellation_and_preserves_partial_output():
    controller = SteeringController()
    controller.append_output(b"line one\n")
    controller.append_output("line two\n")

    snapshot = controller.abort()

    assert controller.cancelled
    assert controller.cancel_event.is_set()
    assert snapshot.cancelled
    assert snapshot.partial_output == b"line one\nline two\n"
    assert controller.partial_output == snapshot.partial_output


def test_abort_resume_message_preserves_bytes_byte_for_byte():
    controller = SteeringController()
    raw = b"prefix \x00\xff\xfe utf8: \xc3\x28 (invalid on purpose)"
    controller.append_output(raw)
    message = controller.submit_message("change plan", SteeringMode.ABORT_RESUME)

    assert controller.cancelled
    assert controller.pending_resume_messages() == (message,)
    result = controller.resume()

    assert result.partial_output == raw
    assert controller.partial_output == raw
    assert result.messages == (message,)
    assert not controller.cancelled
    assert not controller.cancel_event.is_set()
    assert controller.pending_resume_messages() == ()
    # A second resume is a harmless no-op; it never re-delivers the message.
    assert controller.resume().messages == ()


def test_double_abort_is_idempotent():
    controller = SteeringController()
    controller.append_output(b"partial")
    first = controller.abort()
    second = controller.abort()

    assert first == second
    assert controller.abort_count == 1
    assert controller.cancelled
    assert controller.partial_output == b"partial"

    result = controller.resume()
    assert not controller.cancelled
    assert result.partial_output == b"partial"
    assert controller.abort_count == 1


def test_resume_restores_snapshot_after_late_output():
    controller = SteeringController()
    controller.append_output(b"keep me")
    controller.abort()
    controller.append_output(b"in-flight chunk that must be discarded")

    result = controller.resume()

    assert result.partial_output == b"keep me"
    assert controller.partial_output == b"keep me"


def test_snapshot_and_restore_roundtrip():
    controller = SteeringController()
    controller.set_mode(SteeringMode.STEER_AT_BOUNDARY)
    controller.append_output(b"state")
    queued = controller.submit_message("q", SteeringMode.QUEUE)
    steered = controller.submit_message("s", SteeringMode.STEER_AT_BOUNDARY)
    snapshot = controller.snapshot()
    assert isinstance(snapshot, SteeringSnapshot)

    controller.drain_queue()
    controller.poll_boundary()
    controller.append_output(b"changed")
    controller.set_mode(SteeringMode.ABORT_RESUME)
    assert controller.partial_output != snapshot.partial_output

    controller.restore(snapshot)

    assert controller.partial_output == snapshot.partial_output == b"state"
    assert controller.mode is SteeringMode.STEER_AT_BOUNDARY
    assert controller.drain_queue() == (queued,)
    assert controller.poll_boundary() == steered
    assert controller.all_messages() == (queued, steered)


def test_restore_restores_cancellation_state():
    controller = SteeringController()
    controller.append_output(b"abc")
    snapshot = controller.abort()
    controller.resume()
    assert not controller.cancelled

    controller.restore(snapshot)
    assert controller.cancelled
    assert controller.cancel_event.is_set()
    assert controller.partial_output == b"abc"


def test_cancellation_propagates_to_boundary_and_preserves_steered_messages():
    controller = SteeringController()
    steered = controller.submit_message("steer me", SteeringMode.STEER_AT_BOUNDARY)
    aborting = controller.submit_message("interrupt", SteeringMode.ABORT_RESUME)

    # Once cancelled, no further mid-turn steering is delivered, and anything
    # still pending is carried into the resume payload rather than lost.
    assert controller.poll_boundary() is None
    late = controller.submit_message("late steer", SteeringMode.STEER_AT_BOUNDARY)
    assert controller.pending_resume_messages() == (steered, aborting, late)

    result = controller.resume()
    assert result.messages == (steered, aborting, late)
    assert [m.seq for m in result.messages] == [0, 1, 2]


def test_concurrent_output_appends_are_lossless():
    controller = SteeringController()
    threads: list[threading.Thread] = []
    barrier = threading.Barrier(8)
    chunk = b"0123456789"

    def append() -> None:
        barrier.wait()
        for _ in range(100):
            controller.append_output(chunk)

    for _ in range(8):
        thread = threading.Thread(target=append)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()

    assert controller.partial_output == chunk * 800


def test_mixed_modes_never_lose_a_message():
    controller = SteeringController()
    threads: list[threading.Thread] = []
    barrier = threading.Barrier(9)
    modes = [
        SteeringMode.QUEUE,
        SteeringMode.STEER_AT_BOUNDARY,
        SteeringMode.ABORT_RESUME,
    ]

    def submit(worker: int) -> None:
        barrier.wait()
        for index in range(30):
            controller.submit_message(
                f"w{worker}-{index}", modes[(worker + index) % len(modes)])

    for worker in range(9):
        thread = threading.Thread(target=submit, args=(worker,))
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()

    # Drain every bucket except delivered, which poll_boundary() populates.
    queued = controller.drain_queue()
    boundary: list[SteeringMessage] = []
    while True:
        message = controller.poll_boundary()
        if message is None:
            break
        boundary.append(message)
    resume = controller.pending_resume_messages()

    buckets = queued + tuple(boundary) + resume + controller.delivered_messages()
    assert len(buckets) == 9 * 30
    assert len({m.seq for m in buckets}) == 9 * 30
    assert {m.seq for m in buckets} == set(range(9 * 30))
    assert controller.all_messages() == tuple(
        sorted(buckets, key=lambda m: m.seq))
