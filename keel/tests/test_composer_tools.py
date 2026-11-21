"""A1.6/A1.8 — inline shell and editor helpers."""

from __future__ import annotations

from keel.composer_tools import editor_command, parse_inline_shell


def test_inline_shell_prefix():
    assert parse_inline_shell("!git status") == "git status"
    assert parse_inline_shell("normal text") is None
    assert parse_inline_shell("!") is None


def test_editor_command(monkeypatch):
    monkeypatch.setenv("EDITOR", "vim")
    assert editor_command("a.py") == ["vim", "a.py"]
    monkeypatch.delenv("EDITOR", raising=False)
    assert editor_command("a.py") == ["code", "--goto", "a.py"]
