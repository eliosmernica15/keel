"""Live token streaming: deltas flow as ephemeral SSE frames.

Guards: the Fleet agentic turn cap is env-tunable (default 10), and the
provider delta stream reaches SSE subscribers during the turn while the
canonical message row is still persisted once at the end.
"""

from __future__ import annotations

import os
import queue

import pytest

from keel.fleet import routes as fleet_routes
from keel.fleet import turn_core
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord


OPENROUTER = CapabilityRecord(
    name="openrouter",
    base_url="https://openrouter.ai/api/v1",
    env_var="KEEL_OPENROUTER_API_KEY",
    default_model="openrouter/auto",
    supports_tools=True, supports_streaming=True,
)


class FakeAdapter:
    """Minimal scripted adapter: one text block, end_turn."""

    instances: list["FakeAdapter"] = []

    def __init__(self, cap, *, api_key, transport=None):
        self.cap = cap
        self.api_key = api_key
        self.requests = []
        FakeAdapter.instances.append(self)

    @classmethod
    def from_env(cls, cap, *, transport=None):
        return cls(cap, api_key=os.environ.get(cap.env_var, ""),
                   transport=transport)

    def describe(self):
        return self.cap

    def complete(self, request):
        self.requests.append(request)
        yield {"event": "block_start", "index": 0,
               "block": {"type": "text", "text": ""}}
        # split into small deltas so throttling is actually exercised
        for chunk in ("Hello, ", "operator."):
            yield {"event": "text_delta", "index": 0, "text": chunk}
        yield {"event": "block_stop", "index": 0}
        yield {"event": "message_stop", "stop_reason": "end_turn"}


@pytest.fixture
def store(tmp_path, monkeypatch):
    FakeAdapter.instances = []
    monkeypatch.setenv("KEEL_FLEET_APPROVAL_TIMEOUT_S", "1")
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("keel.providers.registry._PROVIDERS",
                        {"openrouter": OPENROUTER})
    monkeypatch.setattr("keel.providers.registry._key_for",
                        lambda cap: "test-key")
    monkeypatch.setattr("keel.providers.registry.build_adapter",
                        lambda name, *a, **k: FakeAdapter(OPENROUTER,
                                                          api_key="test-key"))
    return fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")


# ------------------------------------------------------- turn cap parsing

def test_fleet_max_turns_default_and_env(monkeypatch):
    monkeypatch.delenv("KEEL_FLEET_MAX_TURNS", raising=False)
    assert turn_core._fleet_max_turns() == 25
    monkeypatch.setenv("KEEL_FLEET_MAX_TURNS", "25")
    assert turn_core._fleet_max_turns() == 25
    monkeypatch.setenv("KEEL_FLEET_MAX_TURNS", "bogus")
    assert turn_core._fleet_max_turns() == 10
    monkeypatch.setenv("KEEL_FLEET_MAX_TURNS", "999")
    assert turn_core._fleet_max_turns() == 50
    monkeypatch.setenv("KEEL_FLEET_MAX_TURNS", "0")
    assert turn_core._fleet_max_turns() == 1
    monkeypatch.setenv("KEEL_FLEET_MAX_TURNS", "-4")
    assert turn_core._fleet_max_turns() == 1


# ---------------------------------------------------------- live deltas

def test_stream_frames_published_during_turn(store):
    bot = store.create_bot(name="Streamy", engine="provider")
    q = store.subscribe()
    try:
        result = turn_core.execute_turn(
            store, bot, "say hi",
            chain=(),
            user_row={"role": "user", "content": "say hi"},
            include_history=False,
            exclude_last_from_history=False)
    finally:
        frames = []
        while True:
            try:
                frames.append(q.get_nowait())
            except queue.Empty:
                break
        store.unsubscribe(q)

    assert result["ok"] is True
    streams = [f for f in frames
               if f.get("type") == "stream" and f.get("bot_id") == bot["id"]]
    assert streams, f"expected stream frames, got kinds: " \
                    f"{[f.get('kind') for f in frames]}"
    assert "".join(f["delta"] for f in streams) == "Hello, operator."

    # the ephemeral frames are NOT persisted as rows
    persisted = store.list_rows(bot["id"], after_seq=0, limit=50)
    stream_rows = [r for r in persisted if r["kind"] == "stream"]
    assert stream_rows == []
    msgs = [r for r in persisted if r["kind"] == "message"
            and r["body"].get("role") == "assistant"]
    assert msgs and msgs[-1]["body"]["content"] == "Hello, operator."
