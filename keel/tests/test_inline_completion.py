"""C2.3 — real Duet inline completion and reviewer comments."""

from __future__ import annotations

from keel.inline_completion import reviewer_comments, suggest


def test_suggestion_from_buffer():
    suggestions = suggest("def greet(name):", language="python")
    assert "    pass" in suggestions


def test_suggestion_from_suffix():
    suggestions = suggest("res", suffix="result = compute()", language="python")
    assert "result" in suggestions


def test_no_suggestion_for_empty():
    assert suggest("") == []


def test_reviewer_comments():
    comments = reviewer_comments("done", ["src/app.py"])
    assert any(c["severity"] == "warning" for c in comments)
    assert any(c.get("file") == "src/app.py" for c in comments)
