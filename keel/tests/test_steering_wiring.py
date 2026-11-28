"""Live Session.run() wiring for the X1.13 steering controller.

These tests drive a real Session (scripted model + fake tool executor) so they
prove messages queued on a SteeringController are consumed by the running
turn, and that an abort stops the turn through the pre-existing cancel seam.
No network, hooks, or subprocesses are involved.
"""

from __future__ import annotations

import threading

from keel.fakes import ScriptedModel, SeededRng, VirtualClock
from keel.session import Session, SessionConfig
from keel.steering import SteeringController, SteeringMode

SESSION_ID = "33333333-3333-4333-8333-333333333333"
TOOL_BLOCK = {"type": "tool_use", "name": "run_shell",
              "input": {"command": "echo hi", "shell": "posix"}}


def _cfg(tmp_path, *, steering=None, cancel_event=None):
    return SessionConfig(
        cwd=str(tmp_path), state_root=str(tmp_path / "state"),
        bare=True, permission_mode="default", session_id=SESSION_ID,
        model="keel-fake-1", seed=0, steering=steering,
        cancel_event=cancel_event)


class _Executor:
    """Records tool calls and optionally runs a callback at the tool boundary."""

    def __init__(self, on_invoke=None):
        self.calls: list[tuple[str, dict]] = []
        self.on_invoke = on_invoke

    def invoke(self, name, tool_input):
        self.calls.append((name, tool_input))
        if self.on_invoke is not None:
            self.on_invoke(name, tool_input)
        return "ok", {"ok": True}


def _session(tmp_path, model, executor, *, steering=None, cancel_event=None):
    return Session(
        model_client=model, executor=executor,
        config=_cfg(tmp_path, steering=steering, cancel_event=cancel_event),
        rules=((), (), ("run_shell",)),  # allow the one scripted tool
        clock=VirtualClock(), rng=SeededRng(0))


def test_boundary_message_is_consumed_by_live_session_run(tmp_path):
    controller = SteeringController()
    submitted = []

    def submit_at_tool(name, tool_input):
        submitted.append(controller.submit_message(
            "stop and use plan B", SteeringMode.STEER_AT_BOUNDARY))

    model = ScriptedModel([
        [{"type": "text", "text": "working"}, TOOL_BLOCK],
        [{"type": "text", "text": "done"}],
    ])
    executor = _Executor(on_invoke=submit_at_tool)
    session = _session(tmp_path, model, executor, steering=controller)

    out = session.run("initial prompt")

    assert out.envelope["subtype"] == "success"
    assert out.envelope["result"] == "done"
    assert executor.calls and model.request_count == 2
    # The injected message reached the *next* model call, not just the
    # controller's own queue.
    second_call = model.seen_messages[1]
    assert [m["content"] for m in second_call
            if m.get("role") == "user"
            and isinstance(m.get("content"), str)
            and m["content"].startswith("[steering] ")] == [
                "[steering] stop and use plan B"]
    assert controller.delivered_messages() == tuple(submitted)
    assert any(e.get("subtype") == "informational"
               and "[steering] stop and use plan B" in str(e.get("content"))
               for e in out.events)
    # Assistant output is captured for the abort snapshot.
    assert controller.partial_output == b"workingdone"


def test_queue_message_is_not_delivered_mid_turn(tmp_path):
    controller = SteeringController()
    submitted = []

    def submit_at_tool(name, tool_input):
        submitted.append(controller.submit_message(
            "for the next turn", SteeringMode.QUEUE))

    model = ScriptedModel([
        [TOOL_BLOCK], [{"type": "text", "text": "done"}],
    ])
    session = _session(tmp_path, model, _Executor(on_invoke=submit_at_tool),
                       steering=controller)
    out = session.run("initial prompt")

    assert out.envelope["result"] == "done"
    assert "for the next turn" not in str(model.seen_messages[1])
    assert controller.drain_queue() == tuple(submitted)
    assert controller.delivered_messages() == ()


def test_steering_abort_stops_live_run_via_existing_cancel_seam(tmp_path):
    controller = SteeringController()
    model = ScriptedModel([
        [{"type": "text", "text": "partial"}, TOOL_BLOCK],
        [{"type": "text", "text": "must not happen"}],
    ])
    executor = _Executor(on_invoke=lambda name, tool_input: controller.abort())
    session = _session(tmp_path, model, executor, steering=controller)

    out = session.run("initial prompt")

    assert out.envelope["subtype"] == "success"
    assert out.envelope["terminal_reason"] == "cancelled"
    assert out.envelope["result"] == ""
    assert model.request_count == 1  # no second model round-trip
    assert len(executor.calls) == 1
    assert controller.cancelled
    assert controller.abort_count == 1
    # Partial text is preserved byte-for-byte for the snapshot.
    assert controller.partial_output == b"partial"


def test_abort_resume_message_is_held_not_injected(tmp_path):
    controller = SteeringController()
    submitted = []

    def submit_at_tool(name, tool_input):
        submitted.append(controller.submit_message(
            "restart with plan C", SteeringMode.ABORT_RESUME))

    model = ScriptedModel([
        [TOOL_BLOCK], [{"type": "text", "text": "must not happen"}],
    ])
    session = _session(tmp_path, model, _Executor(on_invoke=submit_at_tool),
                       steering=controller)

    out = session.run("initial prompt")

    assert out.envelope["terminal_reason"] == "cancelled"
    assert model.request_count == 1
    assert controller.pending_resume_messages() == tuple(submitted)
    assert controller.delivered_messages() == ()
    assert "restart with plan C" not in str(model.seen_messages)
    resumed = controller.resume()
    assert resumed.messages == tuple(submitted)
    assert not controller.cancelled


def test_external_cancel_event_still_stops_run_without_steering(tmp_path):
    cancel = threading.Event()
    cancel.set()
    model = ScriptedModel([[{"type": "text", "text": "never"}]])
    session = _session(tmp_path, model, _Executor(), cancel_event=cancel)

    out = session.run("initial prompt")

    assert out.envelope["terminal_reason"] == "cancelled"
    assert model.request_count == 0


def test_unused_steering_does_not_change_event_shape(tmp_path):
    script = [[TOOL_BLOCK], [{"type": "text", "text": "done"}]]

    def shape(tmp_path, steering):
        model = ScriptedModel([list(response) for response in script])
        out = _session(tmp_path, model, _Executor(), steering=steering).run("hi")
        return [(e["type"], e.get("subtype")) for e in out.events]

    plain = shape(tmp_path / "plain", None)
    with_controller = shape(tmp_path / "with", SteeringController())
    assert plain == with_controller
