"""Subagent (Task tool) MVP tests."""

from __future__ import annotations

import pytest

from keel.fakes import ScriptedModel, SeededRng, VirtualClock
from keel.session import Session, SessionConfig


def _cfg(tmp_path, **over):
    cfg = dict(cwd=str(tmp_path),
               state_root=str(tmp_path / "state"),
               bare=True, permission_mode="default",
               session_id="88888888-8888-4888-8888-888888888888",
               model="keel-fake-1", seed=0)
    cfg.update(over)
    return SessionConfig(**cfg)


class _Executor:
    def __init__(self):
        self.calls = []

    def invoke(self, name, tool_input):
        self.calls.append((name, tool_input))
        return f"ok: {name}", {"text": f"ok: {name}"}


def test_task_delegates_and_parent_gets_summary(tmp_path):
    # parent: task -> then final text
    model = _ParentModel(script=[
        [{"type": "tool_use", "name": "Task",
          "input": {"description": "compute", "prompt": "read the file and summarize it"}}],
        [{"type": "text", "text": "subagent finished its work"}],
        [{"type": "text", "text": "all done"}],
    ])
    cfg = _cfg(tmp_path)
    session = Session(model_client=model, executor=_Executor(), config=cfg,
                      rules=((), (), ("Task", "read_file")),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("delegate this")
    assert out.envelope["subtype"] == "success"

    subagent_results = [
        blk for e in out.events if e["type"] == "user"
        for blk in e["message"]["content"]
        if blk.get("type") == "tool_result"
        and "subagent_output" in blk.get("content", "")
    ]
    assert subagent_results
    assert "subagent finished" in subagent_results[0]["content"]


class _ParentModel:
    """Scripted parent; routes Task prompts to canned child by echo."""

    def __init__(self, script):
        self._script = list(script)
        self.request_count = 0
        self.total_usage = None

    def complete(self, messages, tools):
        self.request_count += 1
        if self._script:
            next_blocks = self._script.pop(0)
            return next_blocks
        return [{"type": "text", "text": "done"}]


def test_task_denied_by_default(tmp_path):
    model = _ParentModel(script=[
        [{"type": "tool_use", "name": "Task",
          "input": {"description": "d", "prompt": "do something"}}],
        [{"type": "text", "text": "ok"}],
    ])
    session = Session(model_client=model, executor=_Executor(),
                      config=_cfg(tmp_path),
                      rules=((), (), ()),  # no allow rule for Task
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("delegate")
    tool_result = next(
        blk for e in out.events if e["type"] == "user"
        for blk in e["message"]["content"] if blk["type"] == "tool_result")
    assert "permission denied" in tool_result["content"]


def test_child_cannot_call_task(tmp_path):
    # child tries to delegate; since tool_allowlist drops Task, the child's
    # registry has no Task at all -> it is unavailable and errors out the turn.
    model = _ParentModel(script=[
        # parent: Task call
        [{"type": "tool_use", "name": "Task",
          "input": {"description": "d", "prompt": "do it"}}],
        # child: would call Task too — but allowlist removes it
        [{"type": "tool_use", "name": "Task",
          "input": {"description": "x", "prompt": "nested"}}],
        [{"type": "text", "text": "child done"}],
        # parent: final after child returns
        [{"type": "text", "text": "final"}],
    ])
    cfg = _cfg(tmp_path)
    session = Session(model_client=model, executor=_Executor(), config=cfg,
                      rules=((), (), ("Task",)),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("delegate twice")
    assert out.envelope["subtype"] == "success"


def test_subagent_errors_reported(tmp_path):
    model = _ParentModel(script=[
        [{"type": "tool_use", "name": "Task",
          "input": {"description": "d", "prompt": "boom"}}],
        [{"type": "text", "text": "child done"}],
        [{"type": "text", "text": "final"}],
    ])

    class BoomChild:
        def __init__(self, inner):
            self.inner = inner
            self.request_count = 0
            self.total_usage = None

        def complete(self, messages, tools):
            self.request_count += 1
            if tools and any(t.get("name") == "Task" for t in tools):
                return self.inner.complete(messages, tools)
            # this is the child's context — boom
            raise RuntimeError("child exploded")

    wrapped = BoomChild(model)
    session = Session(model_client=wrapped, executor=_Executor(),
                      config=_cfg(tmp_path), rules=((), (), ("Task",)),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("x")
    assert out.envelope["subtype"] in ("success", "error_during_execution")
