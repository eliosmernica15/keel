"""A1.3/A1.4 — TUI renderer and web alias."""

from __future__ import annotations

from keel.cli.main import main
from keel.tui import render_events


def test_render_events():
    events = [
        {"type": "user", "message": {"content": "hello"}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "hi there"},
            {"type": "tool_use", "name": "read_file"}]}},
        {"type": "result", "subtype": "success"},
    ]
    text = render_events(events)
    assert "> hello" in text and "hi there" in text
    assert "[tool read_file]" in text and "--- success ---" in text


def test_web_alias_help():
    assert main(["web", "--help"]) == 0
