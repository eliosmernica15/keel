"""Phase 1 — vertical slice tests (M1/M2 shape).

M1: exactly one init, one result; denial order; bare-name deny removes the
tool from the manifest; transcript survives truncation.
M2-ish: seeded runs are byte-identical across repeats (two-machine check
remains future work).
"""

from __future__ import annotations

import json
import os

import pytest

from keel.fakes import InMemoryFileSystem, ScriptedModel, SeededRng, VirtualClock
from keel.runner import CliValidationError, parse_argv
from keel.session import ALL_TOOLS, Session, SessionConfig


def _cfg(tmp_path, **overrides):
    cfg = dict(cwd=str(tmp_path),
               state_root=str(tmp_path / "state"),
               bare=True, permission_mode="default",
               session_id="11111111-1111-4111-8111-111111111111",
               model="keel-fake-1", max_turns=10, interactive=False,
               seed=42)
    cfg.update(overrides)
    return SessionConfig(**cfg)


def _session(tmp_path, script, rules=((), (), ()), fs=None):
    model = ScriptedModel(script, model="keel-fake-1")
    cfg = _cfg(tmp_path)
    session = Session(model_client=model, executor=_FakeExec(),
                      config=cfg, rules=rules,
                      clock=VirtualClock(), rng=SeededRng(42),
                      fs=fs)
    return session


class _FakeExec:
    def __init__(self):
        self.calls = []

    def invoke(self, name, tool_input):
        self.calls.append((name, tool_input))
        return f"fake output for {name}", {"text": f"fake output for {name}"}


def test_slice_end_to_end_success(tmp_path):
    session = _session(tmp_path, [
        [{"type": "tool_use", "name": "run_shell",
          "input": {"command": "ls", "shell": "posix"}}],
        [{"type": "text", "text": "all done"}],
    ], rules=((), (), ("run_shell",)))  # allow run_shell explicitly
    out = session.run("look around")

    kinds = [e["type"] for e in out.events]
    assert kinds[0] == "system" and out.events[0]["subtype"] == "init"
    assert out.events[-1]["type"] == "result"
    assert out.events[-1]["subtype"] == "success"
    assert out.events[-1]["result"] == "all done"
    assert kinds.count("assistant") == 2
    assert kinds.count("user") == 1  # the tool_result
    assert kinds.count("result") == 1
    # correlation by tool_use_id
    assistant_id = next(
        b["id"] for e in out.events if e["type"] == "assistant"
        for b in e["message"]["content"] if b["type"] == "tool_use")
    result_id = next(
        b["tool_use_id"] for e in out.events if e["type"] == "user"
        for b in e["message"]["content"] if b["type"] == "tool_result")
    assert assistant_id == result_id


def test_bare_name_deny_removes_tool_from_manifest(tmp_path):
    session = _session(tmp_path, [[{"type": "text", "text": "hi"}]],
                       rules=(("run_shell",), (), ()))
    out = session.run("hello")
    init = out.events[0]
    assert "run_shell" not in init["tools"]
    assert "read_file" in init["tools"]


def test_denial_emits_permission_denied_then_is_error_result(tmp_path):
    # default manual mode, non-interactive: consent required -> deny
    # (rm classifies as irreversible; `ls` would be allowed as read)
    session = _session(tmp_path, [
        [{"type": "tool_use", "name": "run_shell",
          "input": {"command": "rm /tmp/probe-file", "shell": "posix"}}],
        [{"type": "text", "text": "blocked"}],
    ])
    out = session.run("try ls")
    denial_idx = next(i for i, e in enumerate(out.events)
                      if e["type"] == "system" and e.get("subtype") == "permission_denied")
    result_idx = next(i for i, e in enumerate(out.events)
                      if e["type"] == "user"
                      and any(b.get("content") for b in e["message"]["content"]))
    assert denial_idx < result_idx
    tool_result = out.events[result_idx]
    block = tool_result["message"]["content"][0]
    assert "permission denied" in block["content"]
    meta = tool_result["tool_result_meta"][0]["permission_decision"]
    assert meta == {"decision": "deny", "source": "mode",
                    "reason_type": "consent_required"}
    assert out.events[-1]["permission_denials"], "denial must be recorded on the envelope"
    assert out.events[-1]["subtype"] == "success"  # denial is a policy outcome; exit 0


def test_zero_ambient_reads_in_bare_mode(tmp_path):
    # every path the session opens must live under its state root
    fs = InMemoryFileSystem()
    session = _session(tmp_path, [[{"type": "text", "text": "hi"}]], fs=fs)
    session.run("hello")
    state_root = os.path.join(str(tmp_path), "state").replace("\\", "/")
    for opened in fs.opened:
        assert opened.startswith(state_root), opened


def test_transcript_survives_truncation(tmp_path):
    session = _session(tmp_path, [[{"type": "text", "text": "hi"}]])
    out = session.run("hello")
    path = out.transcript_path
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"type":"assistant","message":{"id":"msg_x"')  # truncated line
    from keel.transcript import read_entries
    entries = list(read_entries(path))
    good = [e for e, ok in entries if ok]
    bad = [e for e, ok in entries if not ok]
    assert good and len(bad) == 1
    assert any(e.get("type") == "system" for e in good)


def test_stream_json_lines_parse_and_envelope_is_last(tmp_path, capsys=None):
    session = _session(tmp_path, [[{"type": "text", "text": "hi"}]])
    out = session.run("hello")
    lines = [json.dumps(e, separators=(",", ":")) for e in out.events]
    parsed = [json.loads(l) for l in lines]
    assert parsed[0]["subtype"] == "init"
    assert parsed[-1]["type"] == "result"
    for ev_line in parsed:
        assert "type" in ev_line


def test_determinism_byte_identical_across_runs(tmp_path):
    outputs = []
    for _ in range(10):
        session = _session(tmp_path / "r", [
            [{"type": "tool_use", "name": "run_shell",
              "input": {"command": "ls", "shell": "posix"}}],
            [{"type": "text", "text": "done"}],
        ], rules=((), (), ("run_shell",)))
        out = session.run("look")
        outputs.append(json.dumps(out.events, separators=(",", ":"),
                                  sort_keys=False))
    assert len(set(outputs)) == 1


def test_flag_validation_precedes_model_call(tmp_path):
    with pytest.raises(CliValidationError):
        parse_argv(["--output-format", "yaml", "hi"])
    with pytest.raises(CliValidationError):
        parse_argv(["--session-id", "not-a-uuid", "hi"])
    with pytest.raises(CliValidationError):
        parse_argv(["--permission-mode", "plan", "hi"])  # not in Phase 1 subset
    with pytest.raises(CliValidationError):
        parse_argv(["--permission-mode", "bypassPermissions", "hi"])
    plan = parse_argv(["--output-format", "stream-json",
                       "--permission-mode", "bypassPermissions",
                       "--i-accept-the-risk", "--seed", "7", "hi"])
    assert plan.permission_mode == "bypassPermissions"


def test_denial_exit_envelope_shape(tmp_path):
    session = _session(tmp_path, [
        [{"type": "tool_use", "name": "run_shell",
          "input": {"command": "rm /tmp/probe-file", "shell": "posix"}}],
        [{"type": "text", "text": "done"}],
    ])
    out = session.run("attempt")
    envelope = out.envelope
    for key in ("subtype", "is_error", "num_turns", "session_id", "usage",
                "total_cost_usd", "stop_reason", "terminal_reason",
                "permission_denials", "subagent_stats"):
        assert key in envelope, key
    assert envelope["permission_denials"][0]["tool_name"] == "run_shell"
