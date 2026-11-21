"""C5.1/C5.2 — deterministic map/loop nodes and human-task nodes."""

from __future__ import annotations

from keel.workflows import Workflow, WorkflowStep, execute_workflow


def test_map_node_binds_items():
    seen = []

    def executor(name, tool_input):
        seen.append(tool_input)
        return "ok", {}

    wf = Workflow("m", steps=[WorkflowStep(
        kind="map", items=["a", "b"],
        steps=[{"kind": "tool", "name": "write_file",
                "input": {"path": "{{item}}.txt"}}])])
    results = execute_workflow(wf, tool_executor=executor)
    assert results[0]["ok"] is True
    assert [i["path"] for i in seen] == ["a.txt", "b.txt"]


def test_loop_node_repeats():
    counts = []

    def executor(name, tool_input):
        counts.append(1)
        return "ok", {}

    wf = Workflow("l", steps=[WorkflowStep(
        kind="loop", times=3,
        steps=[{"kind": "tool", "name": "read_file",
                "input": {"path": "f{{index}}.txt"}}])])
    results = execute_workflow(wf, tool_executor=executor)
    assert results[0]["ok"] is True and len(counts) == 3


def test_human_node_uses_responder():
    def executor(name, tool_input):
        assert name == "ask_user"
        return "approved"

    wf = Workflow("h", steps=[WorkflowStep(
        kind="human", name="Approve deploy?",
        input={"options": ["yes", "no"]})])
    results = execute_workflow(wf, tool_executor=executor)
    assert results[0]["result"] == "approved" and results[0]["ok"] is True


def test_human_node_defaults_without_responder():
    wf = Workflow("h", steps=[WorkflowStep(
        kind="human", name="Approve?", default="timeout")])
    results = execute_workflow(wf)
    assert results[0]["result"] == "timeout"
    assert results[0]["defaulted"] is True
