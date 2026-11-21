"""C4.12/C4.13 — terminal replay and issue-to-change."""

from __future__ import annotations

from keel.issue_to_change import parse_issue, to_change_plan
from keel.terminal_replay import TerminalRecorder


def test_record_and_replay(tmp_path):
    recorder = TerminalRecorder(tmp_path / "session.jsonl")
    recorder.record("echo hi", "hi\n", exit_code=0)
    recorder.record("false", "", exit_code=1)
    seen = []
    assert recorder.replay(seen.append) == 2
    assert seen[0]["command"] == "echo hi" and seen[1]["exit_code"] == 1


def test_issue_to_change():
    issue = parse_issue("Fix login\n#bug #urgent\n- [ ] reset password\n- [x] add test")
    assert issue["title"] == "Fix login"
    assert set(issue["labels"]) == {"bug", "urgent"}
    plan = to_change_plan(issue)
    assert plan["draft_only"] is True
    assert "Verify each acceptance criterion" in plan["steps"]
