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
