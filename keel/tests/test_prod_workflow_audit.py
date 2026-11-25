"""Every workflow outcome, including policy denials, must be audited."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from keel import backend_workflows as wf  # noqa: E402


def _audit_rows(root: Path) -> list[dict]:
    path = root / "capability-audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_policy_denied_workflow_is_audited(tmp_path, monkeypatch):
    base = tmp_path / "trusted"
    base.mkdir(parents=True)
    monkeypatch.setenv("KEEL_STATE_DIR", str(base))
    root = base / "project"
    (root / "exec-policies").mkdir(parents=True)
    (root / "exec-policies" / "default.json").write_text(json.dumps({
        "prefix_rules": [{"pattern": ["backend.workflow"],
                          "decision": "forbidden", "justification": "test deny"}]
    }), encoding="utf-8")
    result = wf.run_workflow("request", {"state_root": str(root), "prompt": "hi"})
    assert result["ok"] is False
    assert result["code"] == "policy_denied", result
    rows = [r for r in _audit_rows(root) if r.get("capability") == "backend.workflow"]
    assert rows, "policy denial must still produce an audit record"
    assert rows[-1]["ok"] is False
    assert rows[-1]["code"] == "policy_denied"


def test_workflow_outcome_is_audited(tmp_path, monkeypatch):
    base = tmp_path / "trusted"
    base.mkdir(parents=True)
    monkeypatch.setenv("KEEL_STATE_DIR", str(base))
    result = wf.run_workflow("request", {"prompt": "hi"})
    rows = [r for r in _audit_rows(base) if r.get("capability") == "backend.workflow"]
    assert rows, "every workflow outcome must be audited"
    assert rows[-1]["ok"] == bool(result.get("ok"))
