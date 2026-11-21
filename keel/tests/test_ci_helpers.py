"""B7.3/B7.5/B7.9 — CI helpers and site runbook pages."""

from __future__ import annotations

from pathlib import Path

from keel.ci_helpers import FlakyQuarantine, accessibility_gate, kickoff_prompt

SITE = Path(__file__).resolve().parents[1] / "site"


def test_flaky_quarantine(tmp_path):
    q = FlakyQuarantine(tmp_path)
    assert q.add("test_x", "alice", days=7)["owner"] == "alice"
    assert q.is_quarantined("test_x") is True
    assert q.is_quarantined("test_y") is False


def test_kickoff_and_gate():
    prompt = kickoff_prompt("M6")
    assert "M6" in prompt and "Stop" in prompt
    assert accessibility_gate({"critical": 0}) is True
    assert accessibility_gate({"critical": 2}) is False


def test_runbook_pages():
    roadmap = (SITE / "roadmap.html").read_text(encoding="utf-8")
    assert "Roadmap" in roadmap and "FAQ" in roadmap
    trademark = (SITE / "trademark.html").read_text(encoding="utf-8")
    assert "Trademark" in trademark and "takedown" in trademark.lower()
