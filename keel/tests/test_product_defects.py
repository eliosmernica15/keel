"""Connected-product defect regressions (Agent 21-24).

These tests drive four real product flows through the *capability hub*
(``keel.capabilities.invoke``) and assert the actual artifacts/outputs, not
just ``ok=True``.  Each test here corresponds to a defect found while
revalidating Cowork / Code / Duet / Fleet as a connected product.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from keel import capability_registry  # noqa: F401 - registers capabilities
from keel.capabilities import invoke
from keel.workflows import Workflow, WorkflowStep, execute_workflow

ROOT = Path(__file__).resolve().parents[1]  # .../keel
SRC = ROOT / "src"


def _ctx(tmp_path: Path) -> dict:
    return {"cwd": str(tmp_path), "state_root": str(tmp_path / "state")}


def _fresh_process_doc_read(doc: Path, cwd: Path) -> str:
    """Read a document in a brand-new Python process (a real restart)."""
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        "import keel.capability_registry\n"
        "from keel.capabilities import invoke\n"
        "r = invoke('cowork.doc.read', {'path': sys.argv[1]}, "
        "context={'cwd': sys.argv[2]})\n"
        "print(json.dumps(r['result']['text']))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(doc), str(cwd)],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ---------------------------------------------------------------- Cowork (a)
def test_cowork_doc_roundtrip_survives_restart(tmp_path):
    """DEFECT: blank lines (and a trailing newline) were lost on DOCX writing.

    create -> read back -> restart (fresh process) -> read again must yield the
    exact original text.  Previously ``write_docx`` emitted empty paragraphs
    but ``read_docx`` dropped them, so the persisted document silently lost
    every blank line.
    """
    doc = tmp_path / "report.docx"
    original = "Project Report\n\nKeel is local-first. & <tag>\n\nFinal line\n"
    written = invoke("cowork.doc.write", {"path": str(doc), "text": original},
                     context=_ctx(tmp_path))
    assert written["ok"] is True

    first = invoke("cowork.doc.read", {"path": str(doc)}, context=_ctx(tmp_path))
    assert first["ok"] is True
    assert first["result"]["text"] == original, (
        "read-back lost content: %r" % first["result"]["text"])

    after_restart = _fresh_process_doc_read(doc, tmp_path)
    assert after_restart == original, (
        "content did not survive restart: %r" % after_restart)


# ---------------------------------------------------------------- Code (b)
def test_codemod_rename_renames_attribute_references(tmp_path):
    """DEFECT: ``rename_symbol`` promised to rename attribute references but
    only rewrote bare ``Name`` nodes, leaving ``obj.old()`` untouched.
    """
    mod = tmp_path / "service.py"
    original = (
        "class Service:\n"
        "    def old(self):\n"
        "        return self.old()\n"
        "\n"
        "svc = Service()\n"
        "result = svc.old()\n"
    )
    mod.write_text(original, encoding="utf-8")
    params = {"path": str(mod), "kind": "rename",
              "old": "old", "new": "new"}

    preview = invoke("code.codemod.preview", params, context=_ctx(tmp_path))
    assert preview["ok"] is True
    assert preview["result"]["changed"] is True
    assert "svc.new()" in preview["result"]["diff"]
    assert mod.read_text(encoding="utf-8") == original  # preview must not write

    applied = invoke("code.codemod.apply", params, context=_ctx(tmp_path))
    assert applied["ok"] is True
    after = mod.read_text(encoding="utf-8")
    assert "def new" in after
    assert "self.new()" in after
    assert "svc.new()" in after
    assert "old" not in after


# ---------------------------------------------------------------- Duet (c)
def test_duet_best_of_n_selects_by_real_score(tmp_path):
    """Deterministic providers: the winner must be the highest *scored*
    candidate, not simply the first one or the hub's ``ok`` flag."""
    candidates = [
        {"score": 0.1, "value": "bad", "evidence": "low"},
        {"score": 0.95, "value": "best", "evidence": "high"},
        {"score": 0.5, "value": "mid", "evidence": "mid"},
    ]
    result = invoke("duet.best_of_n",
                    {"prompt": "task", "candidates": candidates},
                    context=_ctx(tmp_path))
    assert result["ok"] is True
    assert result["result"]["index"] == 1
    assert result["result"]["value"]["value"] == "best"

    # A reordered input must select on score, not on position.
    reordered = invoke("duet.best_of_n",
                       {"prompt": "task", "candidates": list(reversed(candidates))},
                       context=_ctx(tmp_path))
    assert reordered["result"]["index"] == 1
    assert reordered["result"]["value"]["value"] == "best"


# ---------------------------------------------------------------- Fleet (d)
def test_fleet_workflow_history_persists_across_restart(tmp_path):
    """Workflow versioning must survive a fresh process; anomaly detection
    and the event bus are exercised through the same hub."""
    ctx = _ctx(tmp_path)
    saved = invoke("fleet.workflow.version",
                   {"name": "deploy", "definition": {"steps": ["build", "test"]}},
                   context=ctx)
    assert saved["ok"] is True and saved["result"]["version"] == 1

    history = invoke("fleet.workflow.history", {"name": "deploy"}, context=ctx)
    assert history["ok"] is True
    assert len(history["result"]["versions"]) == 1

    anomaly = invoke("fleet.anomaly",
                     {"events": [{"tool": "delete_file"}] * 25}, context=ctx)
    assert anomaly["ok"] is True
    assert anomaly["result"]["score"] > 0.5

    published = invoke("fleet.eventbus.publish",
                       {"topic": "task.done", "payload": {"id": "t1"}},
                       context=ctx)
    assert published["ok"] is True
    assert published["result"]["history"][0]["payload"] == {"id": "t1"}

    # Fresh process: the version snapshot must still be there.
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        "import keel.capability_registry\n"
        "from keel.capabilities import invoke\n"
        "r = invoke('fleet.workflow.history', {'name': 'deploy'}, "
        "context={'state_root': sys.argv[1]})\n"
        "print(json.dumps(r['result']['versions']))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code, str(tmp_path / "state")],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert len(json.loads(proc.stdout)) == 1


# ------------------------------------------- workflows: fake-success fixes
def test_workflow_tool_step_honors_reported_failure():
    """DEFECT: a tool step set ``ok=True`` even when the tool reported
    ``{'ok': False, 'error': ...}``."""
    wf = Workflow("wf", steps=[WorkflowStep(kind="tool", name="flaky")])
    results = execute_workflow(
        wf, tool_executor=lambda name, inp: {"ok": False, "error": "tool failed"})
    assert results[0]["ok"] is False
    assert results[0]["result"]["error"] == "tool failed"


def test_workflow_shell_step_honors_reported_failure():
    wf = Workflow("wf", steps=[WorkflowStep(kind="shell", command="echo hi")])
    results = execute_workflow(
        wf, tool_executor=lambda name, inp: ("out", {"ok": False, "error": "denied"}))
    assert results[0]["ok"] is False


def test_workflow_map_step_reports_child_failure():
    """DEFECT: a map step reported success even when a child step failed."""
    wf = Workflow("m", steps=[WorkflowStep(
        kind="map", items=[1, 2],
        steps=[{"kind": "tool", "name": "child"}])])
    calls = {"n": 0}

    def executor(name, inp):
        calls["n"] += 1
        if calls["n"] == 2:
            return {"ok": False, "error": "child failed"}
        return {"ok": True}

    results = execute_workflow(wf, tool_executor=executor)
    assert results[0]["ok"] is False


def test_workflow_human_step_without_responder_is_not_success():
    """DEFECT: an unanswered human approval was reported as ``ok=True``
    while silently substituting the default."""
    wf = Workflow("h", steps=[WorkflowStep(
        kind="human", name="Approve?", default="denied")])
    results = execute_workflow(wf)
    assert results[0]["result"] == "denied"
    assert results[0]["defaulted"] is True
    assert results[0]["ok"] is False


def test_workflow_human_step_no_answer_is_not_success():
    wf = Workflow("h", steps=[WorkflowStep(
        kind="human", name="Approve?", default="denied")])
    results = execute_workflow(wf, tool_executor=lambda name, inp: None)
    assert results[0]["result"] == "denied"
    assert results[0]["defaulted"] is True
    assert results[0]["ok"] is False
