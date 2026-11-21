"""B3.4 — read-only sessions and per-project network egress allowlist."""

from __future__ import annotations

import pytest

from keel import egress
from keel.fakes import SeededRng, VirtualClock
from keel.runner import RealTools, parse_argv
from keel.session import Session, SessionConfig


def test_allowlist_matches_exact_and_suffix_hosts():
    allow = ["example.com", "*.trust.dev"]
    assert egress.host_allowed("https://example.com/a", allow)
    assert egress.host_allowed("https://api.example.com/a", allow)
    assert egress.host_allowed("https://x.trust.dev", allow)
    assert egress.host_allowed("https://trust.dev", allow)
    assert not egress.host_allowed("https://evil.com", allow)
    assert egress.host_allowed("https://evil.com")


def test_check_url_raises_for_disallowed_host(monkeypatch):
    monkeypatch.setenv("KEEL_EGRESS_ALLOWLIST", "example.com")
    with pytest.raises(ValueError, match="egress allowlist"):
        RealTools().invoke("web_fetch", {"url": "https://evil.com/a"})
    with pytest.raises(ValueError, match="egress allowlist"):
        RealTools().invoke("web_search", {"query": "hello"})


def test_wildcard_allows_everything():
    assert egress.host_allowed("https://anything.org", ["*"])


def _cfg(tmp_path, *, read_only):
    return SessionConfig(cwd=str(tmp_path),
                         state_root=str(tmp_path / "state"),
                         bare=True, permission_mode="default",
                         session_id="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
                         model="boom-1", seed=0, read_only=read_only)


class _NeverExecute:
    def invoke(self, name, tool_input):
        raise AssertionError("read-only must not execute mutating tools")


def test_read_only_session_denies_write_tool(tmp_path):
    target = tmp_path / "out.txt"

    class Model:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return [{"type": "tool_use", "name": "write_file",
                         "input": {"path": str(target), "content": "x"}}]
            return [{"type": "text", "text": "done"}]

    calls = []

    class Executor:
        def invoke(self, name, tool_input):
            calls.append(name)
            return "", {}

    session = Session(model_client=Model(), executor=Executor(),
                      config=_cfg(tmp_path, read_only=True),
                      rules=((), (), ("write_file",)),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("write a file")
    assert calls == []
    assert not target.exists()
    assert any("read-only session" in str(e.get("content", ""))
               for e in out.events if e.get("subtype") == "informational")


def test_cli_accepts_read_only_flag():
    plan = parse_argv(["--read-only", "-p", "hello", "--model", "keel-fake-1"])
    assert plan.read_only is True
