"""Live step emission + bounded auto-continuation.

Guards: tool start/finish rows are published by the executor mid-turn
(not replayed in a burst when the turn ends), and an agent that hits the
round cap without erroring is continued autonomously, bounded.
"""

from __future__ import annotations

import http.client
import json
import os
import threading

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
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
    """Scripted: every call returns the same read_file tool_use forever."""

    instances: list["FakeAdapter"] = []
    script: str = "loop_tool"
    tool_path: str = "."

    def __init__(self, cap, *, api_key, transport=None):
        self.cap = cap
        self.api_key = api_key
        self.requests: list[object] = []
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
               "block": {"type": "tool_use",
                         "id": f"call_{len(self.requests)}",
                         "name": "read_file",
                         "input": {"path": FakeAdapter.tool_path}}}
        yield {"event": "block_stop", "index": 0}
        yield {"event": "message_stop", "stop_reason": "tool_use"}


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    FakeAdapter.instances = []
    FakeAdapter.script = "loop_tool"
    FakeAdapter.tool_path = str(tmp_path / "note.txt")
    (tmp_path / "note.txt").write_text("fleet verification note\n",
                                       encoding="utf-8")
    monkeypatch.setenv("KEEL_FLEET_APPROVAL_TIMEOUT_S", "5")
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("KEEL_FLEET_MAX_TURNS", "2")
    monkeypatch.setenv("KEEL_FLEET_CONTINUE_LIMIT", "2")
    monkeypatch.setattr("keel.providers.registry._PROVIDERS",
                        {"openrouter": OPENROUTER})
    monkeypatch.setattr("keel.providers.registry._key_for",
                        lambda cap: "test-key" if cap.env_var ==
                        "KEEL_OPENROUTER_API_KEY" else "")
    monkeypatch.setattr("keel.providers.registry.build_adapter",
                        lambda name, *a, **k: FakeAdapter(OPENROUTER,
                                                          api_key="test-key"))
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _req(server, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1",
                                      server.server_address[1], timeout=30)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Keel-Token": webapp.token(),
               "Content-Type": "application/json"}
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    return resp.status, json.loads(raw) if raw else {}


def _post(server, path, body):
    return _req(server, "POST", path, body)


def _get(server, path):
    return _req(server, "GET", path)


def _rows(server, bot_id):
    status, body = _get(server, f"/api/fleet/bots/{bot_id}/rows")
    return body.get("rows", [])


def _wait(predicate, timeout=20.0, interval=0.05):
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_live_steps_and_continuation_run_to_cap(bridge):
    status, created = _post(bridge, "/api/fleet/bots",
                            {"name": "Looper", "engine": "provider"})
    assert status == 201
    bot = created["bot"]
    status, _ = _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
                      {"content": "loop forever"})
    assert status == 202
    # wait for the FINAL capped turn (initial + 2 continuations)
    ok = _wait(lambda: len([r for r in _rows(bridge, bot["id"])
                            if r["kind"] == "turn_end"]) >= 3,
               timeout=30.0)
    assert ok
    rows = _rows(bridge, bot["id"])
    turn_ends = [r for r in rows if r["kind"] == "turn_end"]
    assert turn_ends, "turn never ended"
    # 1 initial turn + 2 cap continuations = 3 turn_end rows
    assert len(turn_ends) == 3
    steps = [r for r in rows if r["kind"] == "step"]
    running = [r for r in steps if r["body"].get("status") == "running"]
    done = [r for r in steps if r["body"].get("status") == "done"]
    # no duplicates from the event replay
    assert len(running) == 6 and len(done) == 6
    # one running + one done per tool invocation
    assert len(steps) == 12
    # continuation notices were emitted
    notices = [r for r in rows if r["kind"] == "notice"]
    cont = [n for n in notices if "continuing autonomously" in
            (n["body"].get("text") or "")]
    assert len(cont) == 2
