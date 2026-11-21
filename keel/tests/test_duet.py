"""B2.3 — Duet builder and independent reviewer roles."""

from __future__ import annotations

from keel.duet import (BUILDER_PROMPT, REVIEWER_PROMPT, builder_allowlist,
                       review_allowlist)
from keel.fakes import SeededRng, VirtualClock
from keel.session import Session, SessionConfig


def test_reviewer_is_read_only():
    allowed = set(review_allowlist())
    assert "read_file" in allowed and "git_diff" in allowed
    assert "write_file" not in allowed and "Duet" not in allowed
    assert "Task" not in allowed


def test_builder_cannot_recurse():
    allowed = set(builder_allowlist())
    assert "write_file" in allowed
    assert "Duet" not in allowed and "Task" not in allowed


def test_role_prompts_require_evidence():
    assert "verification" in BUILDER_PROMPT.lower()
    assert "cannot edit" in REVIEWER_PROMPT.lower()


def _cfg(tmp_path):
    return SessionConfig(cwd=str(tmp_path),
                         state_root=str(tmp_path / "state"),
                         bare=True, permission_mode="default",
                         session_id="22222222-2222-4222-8222-222222222222",
                         model="boom-1", seed=0)


class _Executor:
    def invoke(self, name, tool_input):
        raise AssertionError("Duet roles are handled by subagents")


def test_session_duet_returns_both_summaries(tmp_path):
    class Model:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return [{"type": "tool_use", "name": "Duet",
                         "input": {"task": "fix the bug"}}]
            if self.calls == 2:
                return [{"type": "text", "text": "builder fixed it, tests ran"}]
            if self.calls == 3:
                return [{"type": "text", "text": "reviewer verified the fix"}]
            return [{"type": "text", "text": "done"}]

    session = Session(model_client=Model(), executor=_Executor(),
                      config=_cfg(tmp_path),
                      rules=((), (), ("Duet",)),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("run duet")
    result = None
    for event in out.events:
        if event.get("subtype") == "informational" and "## Builder" in str(
                event.get("content", "")):
            result = event["content"]
    assert result and "builder fixed it" in result
    assert "reviewer verified" in result
