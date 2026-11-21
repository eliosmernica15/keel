"""B4.x — desktop state helpers."""

from __future__ import annotations

from keel.desktop_state import DesktopState, quick_ask_descriptor


def test_layouts_profiles_conversations(tmp_path):
    state = DesktopState(tmp_path)
    layout = state.save_layout("split", [{"id": "chat"}, {"id": "code"}])
    assert len(layout["panels"]) == 2
    assert state.profile("work")["name"] == "work"
    entry = state.tag_conversation("c1", ["important"])
    assert "important" in entry["tags"]
    # persistence
    assert "work" in DesktopState(tmp_path)._load()["profiles"]


def test_quick_ask():
    desc = quick_ask_descriptor()
    assert desc["overlay"] is True and desc["hotkey"]
