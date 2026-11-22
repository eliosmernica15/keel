"""B2.2 — real spec-driven mode with approval gates and evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from keel.spec_mode import (SpecStore, approve, break_down_tasks, can_advance,
                            create_spec, record_evidence, set_task_status,
                            status)

ROOT = Path(__file__).resolve().parents[1]


def _spec():
    return break_down_tasks(create_spec(
        "add search", requirements=["index files", "query index"],
        out_of_scope=["cloud sync"], name="search"))


def test_create_spec_structure():
    spec = create_spec("add search", requirements=["a", "b"], name="s")
    assert spec["phase"] == "spec"
    assert [r["id"] for r in spec["spec"]["requirements"]] == ["R1", "R2"]
    assert spec["spec"]["out_of_scope"] == []
    assert status(spec)["requirements"] == 2


def test_break_down_tasks_dependencies():
    spec = _spec()
    assert spec["phase"] == "tasks"
    assert len(spec["tasks"]) == 3
    assert spec["tasks"][1]["depends_on"] == ["T1"]
    assert spec["tasks"][-1]["depends_on"] == ["T1", "T2"]
    assert status(spec)["tasks_total"] == 3


def test_approval_gate_enforced():
    spec = _spec()
    # No implicit advance: the current phase is locked until approval is
    # recorded. Approval is an explicit, attributed human action, not something
    # the runtime does on its own.
    assert can_advance(spec) is False
    approve(spec, approver="owner", note="plan looks right")
    assert spec["phase"] == "implement"
    assert spec["approvals"]["tasks"]["approver"] == "owner"
    assert can_advance(spec) is False  # next phase needs its own approval
    approve(spec)
    assert spec["phase"] == "verify"


def test_dependency_order_enforced():
    spec = _spec()
    try:
        set_task_status(spec, "T2", "done")
    except ValueError as exc:
        assert "unmet dependencies" in str(exc)
    else:
        raise AssertionError("dependency bypassed")


def test_verify_requires_evidence():
    spec = _spec()
    set_task_status(spec, "T1", "done")
    set_task_status(spec, "T2", "done")
    approve(spec)
    approve(spec)
    assert spec["phase"] == "verify"
    assert can_advance(spec) is False
    record_evidence(spec, "T1", "test_index passed")
    record_evidence(spec, "T2", "test_query passed")
    assert can_advance(spec) is True
    approve(spec)
    assert spec["phase"] == "done"
    assert list(spec["approvals"]) == ["tasks", "implement", "verify"]


def test_store_roundtrip(tmp_path):
    store = SpecStore(tmp_path)
    spec = _spec()
    store.save(spec)
    assert store.list() == ["search"]
    assert store.load("search")["goal"] == "add search"


def test_capability_integration():
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    spec = invoke("code.spec.create", {"goal": "x", "name": "s"},
                  context={})["result"]
    planned = invoke("code.spec.plan", {"spec": spec}, context={})["result"]
    assert planned["phase"] == "tasks"
    st = invoke("code.spec.status", {"spec": planned}, context={})["result"]
    assert st["tasks_total"] >= 1


def test_cli_spec_workflow(tmp_path):
    state = tmp_path / "state"
    import os
    env = {**os.environ, "KEEL_STATE_DIR": str(state)}

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "keel", "spec", *args],
            cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)

    new = run("new", "demo", "add search", "--requirements", "a,b")
    assert new.returncode == 0, new.stderr
    plan = run("plan", "demo")
    assert plan.returncode == 0 and json.loads(plan.stdout)["phase"] == "tasks"
    listed = run("list")
    assert "demo" in listed.stdout
