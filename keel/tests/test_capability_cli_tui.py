"""Capability hub in the CLI and TUI surfaces."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from keel.tui import Tui


def _cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "keel", *args],
        cwd=cwd, capture_output=True, text=True, timeout=60)


def test_cli_capability_list_and_describe(tmp_path):
    result = _cli("capability", "list", "--surface", "duet", cwd=tmp_path)
    assert result.returncode == 0
    assert "duet.inline.suggest" in result.stdout
    assert all("[duet/" in line for line in result.stdout.splitlines())

    result = _cli("capability", "describe", "core.hardware.detect",
                  cwd=tmp_path)
    assert result.returncode == 0
    doc = json.loads(result.stdout)
    assert doc["permission"] == "read"


def test_cli_capability_invoke_with_confirm(tmp_path, monkeypatch):
    env = dict(__import__("os").environ, KEEL_STATE_DIR=str(tmp_path / "state"))
    result = subprocess.run(
        [sys.executable, "-m", "keel", "capability", "invoke",
         "core.hardware.detect", "--params", "{}"],
        cwd=tmp_path, capture_output=True, text=True, timeout=60, env=env)
    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"] is True

    # write capability needs --confirm
    result = subprocess.run(
        [sys.executable, "-m", "keel", "capability", "invoke",
         "core.flags.set", "--params",
         json.dumps({"name": "x", "enabled": True})],
        cwd=tmp_path, capture_output=True, text=True, timeout=60, env=env)
    assert result.returncode == 1
    assert "--confirm" in result.stderr

    # with --confirm it runs
    result = subprocess.run(
        [sys.executable, "-m", "keel", "capability", "invoke",
         "core.flags.set", "--params",
         json.dumps({"name": "x", "enabled": True}), "--confirm"],
        cwd=tmp_path, capture_output=True, text=True, timeout=60, env=env)
    assert result.returncode == 0


def test_tui_capability_commands(tmp_path):
    outputs = []
    tui = Tui(cwd=str(tmp_path), state_root=str(tmp_path / "state"),
              output_fn=outputs.append)
    assert tui.handle_command("/capabilities") is True
    assert any("capabilit" in line.lower() for line in outputs)
    assert tui.handle_command("/invoke core.hardware.detect") is True
    assert any("hardware" in line.lower() or "os" in line.lower()
               for line in outputs)
