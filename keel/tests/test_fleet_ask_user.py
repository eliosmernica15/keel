"""ask_user end-to-end: agent pauses, operator answers, agent continues."""

from __future__ import annotations

import json
import threading
import time

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


class AskAdapter:
    """Scripted: first call asks; second call answers the question."""

    instances: list["AskAdapter"] = []

    def __init__(self, cap, *, api_key, transport=None):
        self.cap = cap
        self.api_key = api_key
        self.requests: list[object] = []
        AskAdapter.instances.append(self)

    @classmethod
    def from_env(cls, cap, *, transport=None):
        return cls(cap, api_key=os.environ.get(cap.env_var, ""),
                   transport=transport)

    def describe(self):
        return self.cap

    def complete(self, request):
        self.requests.append(request)
        msg = json.dumps(request.messages[-1]["content"])
        if "operator answered" in msg:
            # continuation after the answer — reply with plain text
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            yield {"event": "text_delta", "index": 0,
                   "text": "Done with your answer."}
            yield {"event": "block_stop", "index": 0}
            yield {"event": "message_stop", "stop_reason": "end_turn"}
            return
        yield {"event": "block_start", "index": 0,
               "block": {"type": "tool_use",
                         "id": f"ask_{len(self.requests)}",
                         "name": "ask_user",
                         "input": {"question": "Pick one",
                                   "options": ["A", "B"]}}}
        yield {"event": "block_stop", "index": 0}
        yield {"event": "message_stop", "stop_reason": "tool_use"}


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    AskAdapter.instances = []
    monkeypatch.setenv("KEEL_FLEET_APPROVAL_TIMEOUT_S", "5")
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("KEEL_FLEET_MAX_TURNS", "3")
    monkeypatch.setenv("KEEL_FLEET_CONTINUE_LIMIT", "0")
    monkeypatch.setattr("keel.providers.registry._PROVIDERS",
                        {"openrouter": OPENROUTER})
    monkeypatch.setattr("keel.providers.registry._key_for",
                        lambda cap: "test-key" if cap.env_var ==
                        "KEEL_OPENROUTER_API_KEY" else "")
    monkeypatch.setattr("keel.providers.registry.build_adapter",
                        lambda name, *a, **k: AskAdapter(OPENROUTER,
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
    import http.client
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


def _wait(predicate, timeout=10.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


import os  # noqa: E402 — used by fixtures above


def test_ask_user_pauses_and_operator_answer_closes_it(bridge):
    status, created = _post(bridge, "/api/fleet/bots",
                            {"name": "AskTest", "engine": "provider"})
    assert status == 201
    bot = created["bot"]
    # send the user message that triggers the question
    status, _ = _post(bridge, f"/api/fleet/bots/{bot['id']}/messages",
                      {"content": "hi"})
    assert status == 202

    # wait for the ask card to land
    ok = _wait(lambda: any(r["kind"] == "ask" and r["body"].get("status") == "pending"
                          for r in _rows(bridge, bot["id"])), timeout=8)
    assert ok, "ask card never appeared"

    rows = _rows(bridge, bot["id"])
    ask = next(r for r in rows
               if r["kind"] == "ask" and r["body"].get("status") == "pending")
    ask_id = ask["body"]["ask_id"]
    assert ask["body"]["question"] == "Pick one"

    # answer it
    status, resp = _post(bridge,
                         f"/api/fleet/bots/{bot['id']}/asks/{ask_id}/answer",
                         {"answer": "A"})
    assert status == 200
    assert resp["ok"] is True

    # wait for turn_end — agent finished with the answer
    ok = _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(bridge, bot["id"])),
               timeout=8)
    assert ok
    rows = _rows(bridge, bot["id"])
    # transcript contains the answer
    ask_rows = [r for r in rows if r["kind"] == "ask"]
    assert any(r["body"].get("status") == "answered" and r["body"].get("answer") == "A"
               for r in ask_rows)
