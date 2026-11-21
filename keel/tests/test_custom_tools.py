"""A1.13 — custom Python tools from .keel/tools/ with approval gating."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from keel import custom_tools
from keel.cli.main import main
from keel.fakes import SeededRng, VirtualClock
from keel.session import Session, SessionConfig

SOURCE = '''\
"""A sample custom tool."""
TOOL_NAME = "hello_custom"
DESCRIPTION = "Say hello."
INPUT_SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}}

def run(tool_input, context=None):
    return "hello " + str(tool_input.get("name", "world")), {"ok": True}
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    tools = tmp_path / ".keel" / "tools"
    tools.mkdir(parents=True)
    (tools / "hello.py").write_text(SOURCE, encoding="utf-8")
    monkeypatch.setenv("KEEL_CUSTOM_TOOL_APPROVALS",
                       str(tmp_path / "approvals.json"))
    return tmp_path


def test_describe_does_not_execute_module(project, tmp_path):
    marker = tmp_path / "executed"
    (project / ".keel" / "tools" / "side_effect.py").write_text(
        f"open({str(marker)!r}, 'w').close()\nTOOL_NAME = 'side'\n",
        encoding="utf-8")
    spec = custom_tools.describe(project / ".keel" / "tools" / "side_effect.py")
    assert spec["name"] == "side"
    assert not marker.exists()


def test_discover_and_approval(project):
    found = custom_tools.discover(project)
    assert len(found) >= 1
    hello = next(s for s in found if s["name"] == "hello_custom")
    assert hello["approved"] is False
    custom_tools.approve(hello["path"])
    hello = next(s for s in custom_tools.discover(project)
                 if s["name"] == "hello_custom")
    assert hello["approved"] is True
    assert custom_tools.revoke("hello_custom") is True
    assert next(s for s in custom_tools.discover(project)
                if s["name"] == "hello_custom")["approved"] is False


def test_load_callable_runs(project):
    spec = custom_tools.discover(project)[0]
    run = custom_tools.load_callable(spec["path"])
    text, typed = run({"name": "Keel"}, {"cwd": str(project)})
    assert text == "hello Keel" and typed["ok"] is True


def test_session_registers_only_approved_custom_tools(project):
    spec = next(s for s in custom_tools.discover(project)
                if s["name"] == "hello_custom")
    custom_tools.approve(spec["path"])

    class TextModel:
        def complete(self, messages, tools):
            return [{"type": "text", "text": "done"}]

    config = SessionConfig(cwd=str(project), state_root=str(project / "state"),
                           bare=False, permission_mode="default",
                           session_id="eeeeeeee-eeee-4eee-eeee-eeeeeeeeeeee",
                           model="boom-1", seed=0)
    session = Session(model_client=TextModel(), executor=object(), config=config,
                      clock=VirtualClock(), rng=SeededRng(0))
    session.run("hello")
    assert "hello_custom" in session.tools.names()


def test_cli_tools_commands(project, monkeypatch, capsys):
    monkeypatch.chdir(project)
    assert main(["tools", "list"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert any(s["name"] == "hello_custom" for s in data)
    assert main(["tools", "approve", "hello_custom"]) == 0
    assert main(["tools", "revoke", "hello_custom"]) == 0
    assert main(["tools", "unknown"]) == 1
