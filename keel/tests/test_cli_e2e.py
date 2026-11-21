"""CLI end-to-end: real `keel` process drives real tools through the runtime."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "keel", *args], cwd=cwd,
        capture_output=True, text=True, timeout=60)


def test_cli_writes_real_file_via_scripted_provider(tmp_path):
    target = tmp_path / "created.txt"
    script = tmp_path / "script.json"
    script.write_text(json.dumps({"script": [
        [{"type": "tool_use", "name": "write_file",
          "input": {"path": str(target), "content": "created by keel"}}],
        [{"type": "text", "text": "done"}],
    ]}), encoding="utf-8")

    result = _run("-p", "create a file", "--fake-script", str(script),
                  "--allow-rule", "write_file", "--state-root",
                  str(tmp_path / "state"), "--output-format", "json",
                  cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert target.is_file() and target.read_text() == "created by keel"
    envelope = json.loads(result.stdout.strip().splitlines()[-1])
    assert envelope["subtype"] == "success"


def test_cli_dry_run_does_not_write(tmp_path):
    target = tmp_path / "should-not-exist.txt"
    script = tmp_path / "script.json"
    script.write_text(json.dumps({"script": [
        [{"type": "tool_use", "name": "write_file",
          "input": {"path": str(target), "content": "x"}}],
        [{"type": "text", "text": "done"}],
    ]}), encoding="utf-8")
    result = _run("-p", "write", "--fake-script", str(script),
                  "--allow-rule", "write_file", "--dry-run",
                  "--state-root", str(tmp_path / "state"),
                  "--output-format", "json", cwd=tmp_path)
    assert result.returncode == 0
    assert not target.exists()
    envelope = json.loads(result.stdout.strip().splitlines()[-1])
    assert envelope["dry_run_plan"][0]["tool"] == "write_file"


def test_cli_read_only_denies_write(tmp_path):
    target = tmp_path / "blocked.txt"
    script = tmp_path / "script.json"
    script.write_text(json.dumps({"script": [
        [{"type": "tool_use", "name": "write_file",
          "input": {"path": str(target), "content": "x"}}],
        [{"type": "text", "text": "done"}],
    ]}), encoding="utf-8")
    result = _run("-p", "write", "--fake-script", str(script),
                  "--allow-rule", "write_file", "--read-only",
                  "--state-root", str(tmp_path / "state"),
                  "--output-format", "json", cwd=tmp_path)
    assert result.returncode == 0
    assert not target.exists()
