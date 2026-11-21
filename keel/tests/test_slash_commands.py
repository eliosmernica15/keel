"""A1.7 — slash commands: undo/redo, compact, export, models, themes, details."""

from __future__ import annotations

from pathlib import Path

import pytest

from keel import commands, trash
from keel.cli.main import main


NEW = ("undo", "redo", "compact", "export", "models", "themes", "details")


def test_all_new_commands_are_discoverable():
    found = {c.name for c in commands.discover(Path("."))}
    assert set(NEW) <= found


@pytest.mark.parametrize("name", NEW)
def test_builtin_executes_without_model(name):
    out = commands.execute_builtin(name, "", Path("."))
    assert isinstance(out, str) and out


def test_models_lists_offline_catalog():
    out = commands.execute_builtin("models", "", Path("."))
    assert "offline catalog" in out


def test_themes_lists_dark_and_light():
    out = commands.execute_builtin("themes", "", Path("."))
    assert "dark" in out and "light" in out


def test_details_shows_runtime():
    out = commands.execute_builtin("details", "", Path("."))
    assert "python" in out and "platform" in out


def test_undo_redo_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEL_TRASH_DIR", str(tmp_path / "trash"))
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    trash.move_to_trash(target)
    assert not target.exists()

    assert "restored" in commands.execute_builtin("undo", "", tmp_path)
    assert target.exists()
    assert "back to trash" in commands.execute_builtin("redo", "", tmp_path)
    assert not target.exists()


def test_help_lists_new_commands():
    out = commands.execute_builtin("help", "", Path("."))
    for name in NEW:
        assert f"/{name}" in out


def test_cli_slash_command_is_local(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["-p", "/themes", "--output-format", "text"]) == 0
