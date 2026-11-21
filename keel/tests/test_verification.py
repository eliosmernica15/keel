"""B2.1 — automatic verification loop after file edits."""

from __future__ import annotations

import sys

from keel import verification
from keel.fakes import SeededRng, VirtualClock
from keel.runner import parse_argv
from keel.session import Session, SessionConfig


def test_detect_commands_from_manifests(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    found = verification.detect_commands(str(tmp_path))
    kinds = {c["kind"] for c in found}
    assert "test" in kinds and "lint" in kinds
    assert any("pytest" in " ".join(c["argv"]) for c in found)
    assert any("npm" in " ".join(c["argv"]) for c in found)


def test_no_commands_without_manifest(tmp_path):
    assert verification.detect_commands(str(tmp_path)) == []


def test_run_verification_reports_pass_and_fail():
    results = verification.run_verification(
        ".", [{"kind": "test", "argv": [sys.executable, "-c", "pass"]},
              {"kind": "test", "argv": [sys.executable, "-c", "raise SystemExit(1)"]}])
    assert results[0]["ok"] is True
    assert results[1]["ok"] is False


def _cfg(tmp_path):
    return SessionConfig(cwd=str(tmp_path),
                         state_root=str(tmp_path / "state"),
                         bare=True, permission_mode="default",
                         session_id="bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb",
                         model="boom-1", seed=0, auto_verify=True)


class _Executor:
    def invoke(self, name, tool_input):
        return "", {}


def _session_with_write(tmp_path, monkeypatch):
    target = tmp_path / "out.txt"

    class Model:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return [{"type": "tool_use", "name": "write_file",
                         "input": {"path": str(target), "content": "hello"}}]
            return [{"type": "text", "text": "done"}]

    monkeypatch.setattr(
        "keel.verification.detect_commands",
        lambda cwd: [{"kind": "test",
                      "argv": [sys.executable, "-c", "print('ok')"]}])
    class WritingExecutor:
        def invoke(self, name, tool_input):
            if name == "write_file":
                target.write_text(tool_input["content"], encoding="utf-8")
            return "", {}

    session = Session(model_client=Model(), executor=WritingExecutor(),
                      config=_cfg(tmp_path),
                      rules=((), (), ("write_file",)),
                      clock=VirtualClock(), rng=SeededRng(0))
    return session, target


def test_session_runs_verification_after_edit(tmp_path, monkeypatch):
    session, target = _session_with_write(tmp_path, monkeypatch)
    out = session.run("write a file")
    assert target.exists()
    assert out.envelope["verification"][0]["ok"] is True
    assert any("verification:" in str(e.get("content", ""))
               for e in out.events if e.get("subtype") == "informational")


def test_no_verification_without_file_changes(tmp_path, monkeypatch):
    class TextModel:
        def complete(self, messages, tools):
            return [{"type": "text", "text": "done"}]

    monkeypatch.setattr(
        "keel.verification.detect_commands",
        lambda cwd: [{"kind": "test",
                      "argv": [sys.executable, "-c", "print('ok')"]}])
    session = Session(model_client=TextModel(), executor=_Executor(),
                      config=_cfg(tmp_path),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("hello")
    assert "verification" not in out.envelope


def test_cli_no_verify_flag():
    plan = parse_argv(["--no-verify", "-p", "hello", "--model", "keel-fake-1"])
    assert plan.no_verify is True
