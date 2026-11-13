"""Command surface tests — print-mode builtins + custom templates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keel.cli.main import main
from keel.commands import (Command, discover, find, render_custom,
                            execute_builtin)


def test_version_flag():
    rc = main(["--version"])
    assert rc == 0


def test_builtins_render_locally():
    out = execute_builtin("help", "", Path("."))
    assert "/help" in out and "/doctor" in out and "/context" in out
    assert "keel" in execute_builtin("version", "", Path("."))
    ctx = execute_builtin("context", "some prompt", Path("."))
    assert "soft limit" in ctx and "usable" in ctx
    assert "cost ledger" in execute_builtin("cost", "", Path("."))
    assert "python" in execute_builtin("doctor", "", Path("."))


def test_render_custom_argument_substitution():
    cmd = Command(name="review", description="review a file",
                  template="Review the following carefully:\n$ARGUMENTS",
                  source="project")
    rendered = render_custom(cmd, "src/foo.py")
    assert "src/foo.py" in rendered
    assert "$ARGUMENTS" not in rendered


def _write_command(path: Path, name: str, **fm):
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = "".join(f"{k}: {v}\n" for k, v in fm.items())
    path.write_text(
        f"---\nname: {name}\ndescription: custom command\n{extra}---\n"
        f"Body of {name} with $ARGUMENTS\n",
        encoding="utf-8")


def test_custom_command_discovery_and_help(tmp_path, monkeypatch, capsys):
    _write_command(tmp_path / ".keel" / "commands" / "review.md",
                   "review", **{"argument-hint": "<file>"})
    monkeypatch.chdir(tmp_path)
    rc = main(["-p", "/help", "--output-format", "text"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "review" in out and "[project]" in out


def test_custom_command_runs_through_loop(tmp_path, monkeypatch, capsys):
    _write_command(tmp_path / ".keel" / "commands" / "review.md",
                   "review", **{})
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("KEEL_OPENROUTER_API_KEY", raising=False)
    rc = main(["-p", "/review src/foo.py", "--output-format", "json",
                "--seed", "1"])
    envelope = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert envelope["local_command"] == "review"
    assert envelope["subtype"] == "success"


def test_builtin_via_json_envelope(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["-p", "/doctor", "--output-format", "json", "--seed", "1"])
    envelope = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert envelope["local_command"] == "doctor"
    assert "python" in envelope["result"]


def test_builtin_via_stream_json(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["-p", "/help", "--output-format", "stream-json", "--seed", "1"])
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l]
    assert rc == 0
    kinds = [e["type"] for e in lines]
    assert kinds[0] == "system" and kinds[-1] == "result"
    assert lines[-1]["local_command"] == "help"


def test_unknown_command_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["-p", "/definitely-not-a-command", "--seed", "1"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "unknown command" in captured.err


def test_broken_custom_command_is_skipped(tmp_path, monkeypatch, capsys):
    bad = tmp_path / ".keel" / "commands" / "broken.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("---\nname: Bad Name With Caps\ndescription: x\n---\nbody\n",
                   encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = main(["-p", "/help", "--seed", "1"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "broken" not in out  # rejected silently (validated away)
