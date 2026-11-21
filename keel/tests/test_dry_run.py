"""B3.3 — dry-run mode plans tool side effects but executes none."""

from __future__ import annotations

from keel.fakes import SeededRng, VirtualClock
from keel.runner import parse_argv
from keel.session import Session, SessionConfig


def test_cli_accepts_dry_run_flag():
    plan = parse_argv(["--dry-run", "-p", "hello", "--model", "keel-fake-1"])
    assert plan.dry_run is True


def _cfg(tmp_path, *, dry_run):
    return SessionConfig(cwd=str(tmp_path),
                         state_root=str(tmp_path / "state"),
                         bare=True, permission_mode="default",
                         session_id="99999999-9999-4999-9999-999999999999",
                         model="boom-1", seed=0, dry_run=dry_run)


class _NeverExecute:
    def __init__(self):
        self.calls = []

    def invoke(self, name, tool_input):
        self.calls.append(name)
        raise AssertionError("dry-run must not execute tools")


def test_dry_run_records_planned_side_effects(tmp_path):
    target = tmp_path / "out.txt"

    class DryModel:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return [{"type": "tool_use", "name": "write_file",
                         "input": {"path": str(target), "content": "hello"}}]
            return [{"type": "text", "text": "done"}]

    executor = _NeverExecute()
    session = Session(model_client=DryModel(), executor=executor,
                      config=_cfg(tmp_path, dry_run=True),
                      rules=((), (), ("write_file",)),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("write a file")

    assert executor.calls == []
    assert not target.exists()
    plan = out.envelope["dry_run_plan"]
    assert len(plan) == 1
    assert plan[0]["tool"] == "write_file"
    assert plan[0]["input"]["content"] == "hello"
    assert any("[dry-run] would call write_file" in str(e.get("content", ""))
               for e in out.events if e.get("subtype") == "informational")


def test_normal_run_has_no_dry_run_plan(tmp_path):
    class TextModel:
        def complete(self, messages, tools):
            return [{"type": "text", "text": "done"}]

    session = Session(model_client=TextModel(), executor=_NeverExecute(),
                      config=_cfg(tmp_path, dry_run=False),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("hello")
    assert "dry_run_plan" not in out.envelope
