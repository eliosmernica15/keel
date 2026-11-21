"""A1.10 — visible task checklist (`todo` tool)."""

from __future__ import annotations

from keel.fakes import SeededRng, VirtualClock
from keel.session import Session, SessionConfig
from keel.todos import TodoStore, render_todos


def test_store_persists_and_normalizes(tmp_path):
    store = TodoStore(str(tmp_path))
    items = store.replace([
        {"content": " write tests ", "status": "in_progress"},
        {"content": "review", "status": "nonsense"},
        {"content": "", "status": "pending"},
    ])
    assert len(items) == 2
    assert items[0] == {"content": "write tests", "status": "in_progress"}
    assert items[1]["status"] == "pending"
    assert TodoStore(str(tmp_path)).load() == items


def test_render_checklist(tmp_path):
    text = render_todos([
        {"content": "one", "status": "completed"},
        {"content": "two", "status": "in_progress"},
    ])
    assert "1. [x] one" in text
    assert "2. [~] two" in text
    assert "1/2 completed" in text
    assert render_todos([]) == "Task checklist is empty."


def _cfg(tmp_path):
    return SessionConfig(cwd=str(tmp_path),
                         state_root=str(tmp_path / "state"),
                         bare=True, permission_mode="default",
                         session_id="cccccccc-cccc-4ccc-cccc-cccccccccccc",
                         model="boom-1", seed=0)


class _Executor:
    def invoke(self, name, tool_input):
        raise AssertionError("todo is handled by the session")


def test_session_todo_tool_updates_checklist(tmp_path):
    class Model:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return [{"type": "tool_use", "name": "todo",
                         "input": {"items": [
                             {"content": "implement", "status": "completed"},
                             {"content": "verify", "status": "pending"}]}}]
            return [{"type": "text", "text": "done"}]

    session = Session(model_client=Model(), executor=_Executor(),
                      config=_cfg(tmp_path),
                      rules=((), (), ("todo",)),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("track work")
    stored = TodoStore(str(tmp_path / "state")).load()
    assert [i["content"] for i in stored] == ["implement", "verify"]
    assert stored[0]["status"] == "completed"
    assert any("Task checklist" in str(e.get("content", ""))
               for e in out.events if e.get("subtype") == "informational")


def test_todo_is_registered_with_read_permission():
    from keel.tools.native import NATIVE_TOOL_NAMES, NATIVE_TOOL_PERMISSIONS

    assert "todo" in NATIVE_TOOL_NAMES
    assert NATIVE_TOOL_PERMISSIONS["todo"] == "read"
