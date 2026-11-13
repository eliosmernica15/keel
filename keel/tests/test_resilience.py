"""Error-envelope resilience tests — a provider failure must not crash."""

from __future__ import annotations

import json

import pytest

from keel.fakes import SeededRng, VirtualClock
from keel.providers.base import ProviderError, RETRY_RATE_LIMIT
from keel.session import Session, SessionConfig


def _cfg(tmp_path):
    return SessionConfig(cwd=str(tmp_path),
                         state_root=str(tmp_path / "state"),
                         bare=True, permission_mode="default",
                         session_id="77777777-7777-4777-8777-777777777777",
                         model="boom-1", seed=0)


class _Executor:
    def invoke(self, name, tool_input):
        return "", {}


def test_provider_exception_produces_bad_envelope_not_crash(tmp_path):
    class Boom:
        def complete(self, messages, tools):
            raise ProviderError("rate limited", RETRY_RATE_LIMIT, 429,
                                retryable=True)

    session = Session(model_client=Boom(), executor=_Executor(),
                      config=_cfg(tmp_path),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("do the thing")
    env = out.envelope
    assert env["subtype"] == "error_during_execution"
    assert env["is_error"] is True
    assert env["terminal_reason"] == "provider_error"
    assert env["errors"][0]["retryable"] is True
    assert env["errors"][0]["category"] == "rate_limit"


def test_unexpected_exception_produces_bad_envelope_not_crash(tmp_path):
    class Boom:
        def complete(self, messages, tools):
            raise KeyError("oh no, a programming bug")

    session = Session(model_client=Boom(), executor=_Executor(),
                      config=_cfg(tmp_path),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("do the thing")
    env = out.envelope
    assert env["subtype"] == "error_during_execution"
    assert env["errors"][0]["category"].startswith("internal:")
    assert env["terminal_reason"] == "provider_error"


def test_exit_code_mapping_is_1():
    from keel import events
    assert events.EXIT_CODES["error_during_execution"] == 1
