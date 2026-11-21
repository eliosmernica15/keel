"""C4.1 — real local Python debugging."""

from __future__ import annotations

from keel.debugger import DebugSession


def test_breakpoint_captures_frame(tmp_path):
    script = tmp_path / "sample.py"
    script.write_text(
        "def compute():\n    x = 1\n    y = x + 2\n    return y\n\ncompute()\n",
        encoding="utf-8")
    session = DebugSession()
    session.set_breakpoint(script, 3)
    stops = session.run_file(script)
    hits = [stop for stop in stops if stop.line == 3]
    assert hits
    assert hits[0].function == "compute"
    assert "x" in hits[0].locals


def test_no_breakpoint_still_runs(tmp_path):
    script = tmp_path / "simple.py"
    script.write_text("value = 42\n", encoding="utf-8")
    session = DebugSession()
    session.run_file(script)  # must not raise
    assert session.inspect() is None
