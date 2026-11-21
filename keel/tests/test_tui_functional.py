"""A1.3 — full functional TUI driven against the real runtime."""

from __future__ import annotations

from keel.fakes import ScriptedModel
from keel.tui import Tui


def _model_factory(prompt):
    return ScriptedModel([[{"type": "text", "text": f"echo: {prompt}"}]],
                         model="tui-local")


def test_new_session_and_persistent_history(tmp_path):
    outputs = []
    tui = Tui(cwd=str(tmp_path), state_root=str(tmp_path / "state"),
              output_fn=outputs.append, model_factory=_model_factory)
    sid = tui.new_session()
    tui.submit("hello world")
    assert tui.sessions[sid].turns[0]["prompt"] == "hello world"
    assert any("echo: hello world" in line for line in outputs)

    # A fresh TUI resumes persisted sessions from disk.
    restored = Tui(cwd=str(tmp_path), state_root=str(tmp_path / "state"),
                   output_fn=lambda _: None, model_factory=_model_factory)
    assert sid in restored.list_sessions()
    assert restored.sessions[sid].turns[0]["result"] == "echo: hello world"


def test_commands_and_session_management(tmp_path):
    outputs = []
    tui = Tui(cwd=str(tmp_path), state_root=str(tmp_path / "state"),
              output_fn=outputs.append, model_factory=_model_factory)
    sid = tui.new_session()
    assert tui.handle_command("/sessions") is True
    assert tui.handle_command("/resume " + sid[:8]) is True
    tui.submit("again")
    assert tui.handle_command("/history") is True
    assert any("again" in line for line in outputs)
    assert tui.handle_command("/quit") is False


def test_error_handling_in_runtime(tmp_path):
    outputs = []

    def broken_factory(prompt):
        raise RuntimeError("boom")

    tui = Tui(cwd=str(tmp_path), state_root=str(tmp_path / "state"),
              output_fn=outputs.append, model_factory=broken_factory)
    result = tui.submit("cause an error")
    assert "error" in result
    assert any("boom" in line for line in outputs)
