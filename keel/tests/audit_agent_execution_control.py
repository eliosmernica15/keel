"""Agent C — cancellation and operator-question control-path audit tests.

Targets runtime surface that the existing suite does not exercise directly:

* ``POST /api/fleet/bots/<id>/cancel`` against a genuinely in-flight provider
  turn, proving cooperative cancellation stops further model round-trips;
* the ``ask_user`` timeout / per-bot answer scoping / restart-expiry path.

All model/network boundaries are replaced by the repo's existing fake-adapter
pattern; state is written only under pytest ``tmp_path``.
"""

from __future__ import annotations

import http.client
import json
import threading
import time

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.fleet import asks as asks_module
from keel.fleet import turn_core
from keel.fleet.service import FleetStore
from keel.fleet.tools import FleetTools
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord


CAP = CapabilityRecord(
    name="openrouter",
    base_url="https://openrouter.ai/api/v1",
    env_var="KEEL_OPENROUTER_API_KEY",
    default_model="openrouter/auto",
    supports_tools=True, supports_streaming=True,
)


class GatedAdapter:
    """Blocks the first provider call until the test opens ``gate``."""

    instances: list["GatedAdapter"] = []
    calls: list = []
    entered: threading.Event | None = None
    gate: threading.Event | None = None

    def __init__(self, cap, *, api_key, transport=None):
        self.cap = cap
        GatedAdapter.instances.append(self)

    @classmethod
    def from_env(cls, cap, *, transport=None):
        return cls(cap, api_key="test-key", transport=transport)

    def describe(self):
        return self.cap

    def complete(self, request):
        GatedAdapter.calls.append(request)
        GatedAdapter.entered.set()
        assert GatedAdapter.gate.wait(timeout=10), "test never opened the gate"
        # First round: a text block plus a tool call. If Stop works, the tool
        # is skipped and no second complete() is ever issued.
        yield {"event": "block_start", "index": 0,
               "block": {"type": "text", "text": ""}}
        yield {"event": "text_delta", "index": 0, "text": "partial"}
        yield {"event": "block_stop", "index": 0}
        yield {"event": "block_start", "index": 1,
               "block": {"type": "tool_use", "id": "call_should_not_run",
                         "name": "read_file", "input": {"path": "."}}}
        yield {"event": "block_stop", "index": 1}
        yield {"event": "message_stop", "stop_reason": "tool_use"}


def _req(server, method, path, body=None, token=None):
    conn = http.client.HTTPConnection("127.0.0.1",
                                      server.server_address[1], timeout=30)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Keel-Token": token or webapp.token(),
               "Content-Type": "application/json"}
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        doc = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        doc = {"raw": raw}
    return resp.status, doc


def _get_rows(server, bot_id):
    return _req(server, "GET", f"/api/fleet/bots/{bot_id}/rows")[1].get("rows", [])


def _wait(predicate, timeout=8.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def gated_bridge(tmp_path, monkeypatch):
    GatedAdapter.instances = []
    GatedAdapter.calls = []
    GatedAdapter.entered = threading.Event()
    GatedAdapter.gate = threading.Event()
    monkeypatch.setenv("KEEL_FLEET_STATE", str(tmp_path / "fleet-state"))
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("keel.providers.registry._PROVIDERS",
                        {"openrouter": CAP})
    monkeypatch.setattr("keel.providers.registry._key_for",
                        lambda cap: "test-key")
    monkeypatch.setattr("keel.providers.registry.build_adapter",
                        lambda name, *a, **kw: GatedAdapter(
                            CAP, api_key="test-key"))
    old = fleet_routes._store
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    GatedAdapter.gate.set()  # never leave a worker blocked on teardown
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    fleet_routes._store = old


# --------------------------------------------------------------------------- cancel

def test_cancel_endpoint_signals_active_turn_and_stops_further_rounds(gated_bridge):
    status, created = _req(gated_bridge, "POST", "/api/fleet/bots",
                           {"name": "Cancel Target", "engine": "provider"})
    assert status == 201
    bot_id = created["bot"]["id"]

    status, posted = _req(
        gated_bridge, "POST", f"/api/fleet/bots/{bot_id}/messages",
        {"content": "start a long task"})
    assert status == 202 and posted["queued"] is True
    assert _wait(GatedAdapter.entered.is_set)
    assert _wait(lambda: bot_id in turn_core._ACTIVE_CANCEL)

    status, cancelled = _req(
        gated_bridge, "POST", f"/api/fleet/bots/{bot_id}/cancel", {})
    assert status == 200
    assert cancelled["cancelled"] is True

    GatedAdapter.gate.set()
    assert _wait(lambda: any(r["kind"] == "turn_end"
                             for r in _get_rows(gated_bridge, bot_id)))

    rows = _get_rows(gated_bridge, bot_id)
    ends = [r for r in rows if r["kind"] == "turn_end"]
    assert ends[-1]["body"]["terminal_reason"] == "cancelled"
    # Cooperative cancellation: the in-flight stream completed, but no
    # further model round-trip or tool execution was issued.
    assert len(GatedAdapter.calls) == 1
    assert not any(r["kind"] == "step" for r in rows)
    assert _wait(lambda: bot_id not in turn_core._ACTIVE_CANCEL)


def test_cancel_endpoint_with_no_active_turn_returns_false(gated_bridge):
    status, created = _req(gated_bridge, "POST", "/api/fleet/bots",
                           {"name": "Idle Bot", "engine": "provider"})
    assert status == 201
    bot_id = created["bot"]["id"]
    status, body = _req(gated_bridge, "POST",
                        f"/api/fleet/bots/{bot_id}/cancel", {})
    assert status == 200 and body["cancelled"] is False


# --------------------------------------------------------------------------- asks

@pytest.fixture
def ask_store(tmp_path, monkeypatch):
    """Isolated store plus a fresh AskBroker (the production one is a singleton)."""
    monkeypatch.setattr(asks_module, "broker", asks_module.AskBroker())
    store = FleetStore(db_path=tmp_path / "asks.db")
    bot = store.create_bot(name="Asker", engine="provider")
    yield store, bot, asks_module.broker
    store.close()


def test_ask_answer_is_scoped_to_the_asking_bot(ask_store):
    store, bot, broker = ask_store
    other = store.create_bot(name="Other", engine="provider")
    ask_id = broker.ask(store, bot, "Which library?", ["aiohttp", "requests"])
    assert broker.pending_count() == 1
    assert len(store.list_rows(bot["id"], 0, 100)) >= 1

    assert broker.answer(other["id"], ask_id, "wrong bot") is False
    assert broker.answer(bot["id"], ask_id, "aiohttp") is True
    assert broker.wait(ask_id, timeout_s=0.5) == "aiohttp"
    # GAP A-2 (see AGENT-EXECUTION-AUDIT.md): answer() sets the Event but never
    # pops _pending, and AskBroker.expire_sweep() has no caller in the runtime.
    # The answered ask therefore stays counted as pending for the process life.
    assert broker.pending_count() == 0


def test_ask_timeout_fails_closed_with_a_timeout_row(ask_store, monkeypatch):
    store, bot, broker = ask_store
    import keel.fleet.tools as fleet_tools

    monkeypatch.setattr(broker, "wait", lambda ask_id, timeout_s=300: None)
    tools = FleetTools(store, bot)
    content, payload = tools._ask_user(
        {"question": "Choose a framework", "options": ["A", "B"]})
    assert payload["ok"] is False and payload["error"] == "timeout"
    assert "did not answer" in content
    rows = store.list_rows(bot["id"], 0, 100)
    assert any(r["kind"] == "ask" and r["body"].get("status") == "timeout"
               for r in rows)


def test_pending_ask_is_interrupted_and_reported_on_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(asks_module, "broker", asks_module.AskBroker())
    path = tmp_path / "restart.db"
    store = FleetStore(db_path=path)
    bot = store.create_bot(name="Restart Asker", engine="provider")
    asks_module.broker.ask(store, bot, "Still there?", ["yes"])
    store.close()

    reopened = FleetStore(db_path=path)
    try:
        rows = reopened.list_rows(bot["id"], 0, 100)
        assert any(r["kind"] == "ask" and
                   r["body"].get("status") == "interrupted" for r in rows)
        assert any(r["kind"] == "notice" and "interrupted by" in
                   r["body"].get("text", "") for r in rows)
    finally:
        reopened.close()
