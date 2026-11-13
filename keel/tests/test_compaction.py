"""Compaction / context-budget tests (M5 shape)."""

from __future__ import annotations

import json

import pytest

from keel import events as evmod
from keel.context import Budget, CompactionState, estimate_tokens, select_preserved
from keel.fakes import ScriptedModel, SeededRng, VirtualClock
from keel.session import Session, SessionConfig


def big_message(text: str, uuid: str) -> dict:
    return {"role": "user", "content": text, "uuid": uuid}


def test_estimate_tokens_orders_correctly():
    small = estimate_tokens([{"role": "user", "content": "hi"}])
    large = estimate_tokens([{"role": "user", "content": "hello " * 10_000}])
    assert large > small > 0


def _budget():
    return Budget(context_window=8000, reserved_output=1000,
                  soft_trigger_ratio=0.65, preserved_ratio=0.4)


def test_select_preserved_none_under_limit():
    messages = [big_message("word " * 50, f"id-{i}") for i in range(3)]
    assert select_preserved(messages, _budget()) is None


def test_select_preserved_splits_over_limit():
    b = _budget()
    messages = [big_message("x" * 4096, f"id-{i}") for i in range(8)]
    sel = select_preserved(messages, b)
    assert sel is not None
    assert sel.dropped and sel.preserved
    assert [m["uuid"] for m in messages] == (
        [m["uuid"] for m in sel.dropped] + [m["uuid"] for m in sel.preserved])
    assert sel.pre_tokens == estimate_tokens(messages)
    assert sel.dropped_tokens > 0


def _cfg(tmp_path, **overrides):
    cfg = dict(cwd=str(tmp_path),
               state_root=str(tmp_path / "state"),
               bare=True, permission_mode="default",
               session_id="44444444-4444-4444-8444-444444444444",
               model="keel-fake-1", seed=0, context_window=10_000,
               reserved_output=2_000)
    cfg.update(overrides)
    return SessionConfig(**cfg)


class _Executor:
    def invoke(self, name, tool_input):
        return "", {}


def test_compaction_emits_boundary_and_keeps_ids(tmp_path):
    huge_args = {"command": "cat " + "stacktrace-line\n" * 1400,
                 "shell": "posix"}
    model = ScriptedModel([
        # turn 1: the model emits a huge tool call (inflates the transcript)
        [{"type": "tool_use", "name": "run_shell", "input": huge_args}],
        # compaction summariser: a separate scripted model call
        [{"type": "text", "text": "compacted summary of the investigation"}],
        # turn 2: the real final answer
        [{"type": "text", "text": "done"}],
    ])
    session = Session(model_client=model, executor=_Executor(),
                      config=_cfg(tmp_path),
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("investigate this failure\n" + "noise line\n" * 400)
    boundary = next(e for e in out.events
                    if e.get("subtype") == "compact_boundary")
    assert boundary["cumulativeDroppedTokens"] > 0
    assert boundary["preTokens"] > boundary["postTokens"]
    assert boundary["preservedSegment"]["headUuid"] == \
        boundary["preservedSegment"]["anchorUuid"]
    assert boundary["preservedSegment"]["headUuid"] in boundary["preservedMessages"]["uuids"]
    assert boundary["trigger"] == "auto"
    assert boundary["preCompactDiscoveredTools"] == []
    assert boundary["parentUuid"] is None
    assert boundary["logicalParentUuid"]


def test_compaction_cumulative_is_monotonic(tmp_path):
    events = []

    class Collect(list):
        pass

    model = ScriptedModel(
        [[{"type": "text", "text": f"summary {i}"}] for i in range(4)])
    session = Session(model_client=model, executor=_Executor(),
                      config=_cfg(tmp_path),
                      clock=VirtualClock(), rng=SeededRng(0))

    emitted = Collect()
    emit = lambda e, t=None: emitted.append(e)

    messages = [big_message("seed " * 900, f"id-{i}") for i in range(6)]
    out1 = session._maybe_compact(list(messages), emit)
    out2 = session._maybe_compact(
        list(out1) + [big_message("seed " * 900, f"id-extra-{i}")
                      for i in range(3)], emit)
    assert session.compaction.cumulative_dropped_tokens > 0
    boundaries = [e for e in emitted if e.get("subtype") == "compact_boundary"]
    assert len(boundaries) == 2
    assert boundaries[1]["cumulativeDroppedTokens"] > \
        boundaries[0]["cumulativeDroppedTokens"]


def test_thrash_detected_disables_auto_compact(tmp_path):
    emitted = []
    model = ScriptedModel(
        [[{"type": "text", "text": f"s{i}"}] for i in range(4)])
    session = Session(model_client=model, executor=_Executor(),
                      config=_cfg(tmp_path),
                      clock=VirtualClock(), rng=SeededRng(0))
    emit = lambda e, t=None: emitted.append(e)
    base = [big_message("seed " * 900, f"id-{i}") for i in range(6)]
    messages = list(base)
    for _ in range(3):
        messages = session._maybe_compact(list(messages), emit)
        messages = messages + [big_message("seed " * 900, f"id-more-{_}")
                               for _ in range(3)]
    assert session.compaction.disabled is True
    assert session.compaction.disable_reason
    assert any(e.get("subtype") == "informational" for e in emitted)
