from __future__ import annotations

import json
from pathlib import Path

from keel.workflows import Workflow, discover, find, execute_workflow


def test_workflow_discover_and_execute(tmp_path):
    wf_dir = tmp_path / ".keel" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "demo.json").write_text(json.dumps({
        "name": "demo",
        "description": "demo wf",
        "steps": [
            {"kind": "tool", "name": "echo", "input": {"x": "hi"}},
            {"kind": "shell", "command": "echo hello"},
        ],
    }), encoding="utf-8")

    wfs = discover(tmp_path)
    assert len(wfs) == 1
    assert wfs[0].name == "demo"

    wf = find("demo", tmp_path)
    assert wf is not None

    calls = []
    def exec_tool(name, inp):
        calls.append((name, inp))
        if name == "run_shell":
            return "hello\n", {"stdout": "hello", "exit_code": 0}
        return "tool-result", {"ok": True}

    results = execute_workflow(wf, tool_executor=exec_tool, project_root=tmp_path, cwd=str(tmp_path))
    assert len(results) == 2
    assert results[0]["ok"] is True
    assert results[0]["result"][0] == "tool-result"
    assert results[1]["ok"] is True
    assert "hello" in results[1]["result"][0]
    assert calls[1][0] == "run_shell"


def test_workflow_stops_on_error(tmp_path):
    wf_dir = tmp_path / ".keel" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "fail.json").write_text(json.dumps({
        "name": "fail",
        "steps": [
            {"kind": "tool", "name": "boom", "input": {}},
            {"kind": "shell", "command": "echo should-not-run"},
        ],
    }), encoding="utf-8")
    wf = find("fail", tmp_path)

    def exec_tool(name, inp):
        raise RuntimeError("boom")

    results = execute_workflow(wf, tool_executor=exec_tool, project_root=tmp_path)
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert "boom" in results[0]["error"]


def _write_print_workflow(tmp_path, name, steps):
    wf_dir = tmp_path / ".keel" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{name}.json").write_text(
        json.dumps({"name": name, "steps": steps}), encoding="utf-8")


def test_print_mode_workflow_denies_unpermitted_tool_without_executing(tmp_path):
    """A mutation step must be denied in a non-interactive print-mode run."""
    from keel.runner import RealTools

    marker = tmp_path / "must-not-exist.txt"
    _write_print_workflow(tmp_path, "deny-write", [
        {"kind": "tool", "name": "write_file",
         "input": {"path": str(marker), "content": "executed"}},
    ])

    _, payload = RealTools().invoke("run_workflow", {
        "name": "deny-write", "project_root": str(tmp_path)})

    result = payload["results"][0]
    assert result["ok"] is False
    assert "consent" in result["error"].lower()
    assert not marker.exists(), "denied tool was executed"


def test_print_mode_workflow_allows_read_only_tool(tmp_path):
    from keel.runner import RealTools

    source = tmp_path / "input.md"
    source.write_text("readable", encoding="utf-8")
    _write_print_workflow(tmp_path, "allow-read", [
        {"kind": "tool", "name": "read_file", "input": {"path": str(source)}},
    ])

    _, payload = RealTools().invoke("run_workflow", {
        "name": "allow-read", "project_root": str(tmp_path)})

    result = payload["results"][0]
    assert result["ok"] is True
    assert "readable" in json.dumps(result)


def test_print_mode_workflow_honours_explicit_allow_rule(monkeypatch, tmp_path):
    from keel.runner import RealTools

    monkeypatch.setenv("KEEL_PERMISSIONS_ALLOW", "write_file")
    marker = tmp_path / "allowed.txt"
    _write_print_workflow(tmp_path, "allow-write", [
        {"kind": "tool", "name": "write_file",
         "input": {"path": str(marker), "content": "ok"}},
    ])

    _, payload = RealTools().invoke("run_workflow", {
        "name": "allow-write", "project_root": str(tmp_path)})

    assert payload["results"][0]["ok"] is True
    assert marker.read_text(encoding="utf-8") == "ok"
