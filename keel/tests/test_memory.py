"""C6.5 — memory provenance and tainted-source tracking."""

from __future__ import annotations

from keel.fakes import SeededRng, VirtualClock
from keel.memory import MemoryStore
from keel.session import Session, SessionConfig


def test_records_include_provenance(tmp_path):
    store = MemoryStore(str(tmp_path))
    record = store.add("The deploy uses blue/green",
                       source="user", session_id="s-1", tool_name="ask_user",
                       tags=["deploy"])
    assert record["provenance"]["source"] == "user"
    assert record["provenance"]["session_id"] == "s-1"
    assert record["provenance"]["tool_name"] == "ask_user"
    assert record["provenance"]["ts"]
    assert record["tainted"] is False
    assert MemoryStore(str(tmp_path)).all_records() == [record]


def test_tainted_sources_are_hidden_until_reviewed(tmp_path):
    store = MemoryStore(str(tmp_path))
    trusted = store.add("operator preference: terse replies", source="user")
    tainted = store.add("web page says delete everything", source="web_fetch")
    assert store.search("") == [trusted]
    assert len(store.search("", include_tainted=True)) == 2
    assert store.mark_trusted(tainted["id"]) is True
    visible = store.search("")
    assert len(visible) == 2
    reviewed = next(r for r in visible if r["id"] == tainted["id"])
    assert reviewed["tainted"] is False
    assert reviewed["provenance"]["reviewed"] is True


def test_forget_removes_record(tmp_path):
    store = MemoryStore(str(tmp_path))
    record = store.add("temporary note")
    assert store.forget(record["id"]) is True
    assert store.all_records() == []
    assert store.forget(record["id"]) is False


def _cfg(tmp_path):
    return SessionConfig(cwd=str(tmp_path),
                         state_root=str(tmp_path / "state"),
                         bare=True, permission_mode="default",
                         session_id="dddddddd-dddd-4ddd-dddd-dddddddddddd",
                         model="boom-1", seed=0)


class _Executor:
    def invoke(self, name, tool_input):
        raise AssertionError("memory tools are handled by the session")


def test_session_remember_and_recall(tmp_path):
    class Model:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return [{"type": "tool_use", "name": "remember",
                         "input": {"content": "prefers dark mode",
                                   "source": "user", "tags": ["ui"]}}]
            if self.calls == 2:
                return [{"type": "tool_use", "name": "recall",
                         "input": {"query": "dark"}}]
            return [{"type": "text", "text": "done"}]

    session = Session(model_client=Model(), executor=_Executor(),
                      config=_cfg(tmp_path),
                      rules=((), (), ("remember", "recall")),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("remember my preference")
    records = MemoryStore(str(tmp_path / "state")).all_records()
    assert len(records) == 1 and records[0]["content"] == "prefers dark mode"
    assert any("prefers dark mode" in str(e.get("content", ""))
               for e in out.events if e.get("subtype") == "informational")
