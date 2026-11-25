"""FIXTURE-BASED verification — catalog, per-agent models, errors, cancellation.

Label: FIXTURE / fake transport + fake HTTP probe. No real provider key and no
network are used. The real bridge, Session, Fleet store and provider adapters
run unmodified; only the provider HTTP probe and the adapter transport are
replaced by deterministic fixtures.

Covers requirement 2 of the provider verification round:
    live vs offline model catalog, per-agent model config, provider errors,
    timeout/cancellation propagation, and the data the UI uses to distinguish a
    fixture/scripted response from a live response.
"""

from __future__ import annotations

import http.client
import json
import os
import threading
import time
import urllib.error
from pathlib import Path

import pytest

import keel.webapp as webapp
from keel import settings_store
from keel.fleet import routes as fleet_routes
from keel.fleet import session_keys, turn_core
from keel.providers import registry as provider_registry
from keel.providers.base import (
    RETRY_UNKNOWN,
    CapabilityRecord,
    ProviderError,
    ProviderRequest,
    TurnCancelled,
    UsageRecord,
    http_transport,
)
from keel.providers.model_client import ProviderModelClient
from keel.providers.openai_compatible import OpenAICompatibleAdapter

FIXTURE_CAP = CapabilityRecord(
    name="openrouter",
    base_url="https://fixture.invalid/v1",
    env_var="KEEL_OPENROUTER_API_KEY",
    default_model="fixture/auto",
    supports_tools=True,
    supports_streaming=True,
)

FAKE_PROBE_OK = {"data": {"label": "fixture-accepted", "limit": None}}
FAKE_CATALOG = {
    "data": [
        {
            "id": "fixture/a",
            "supported_parameters": ["tools"],
            "context_length": 128000,
        },
        {"id": "fixture/b:free", "reasoning": {"supported_efforts": ["low", "high"]}},
    ]
}


def _fixture_router(mapping):
    def fake(url, headers, timeout):
        for needle, outcome in mapping.items():
            if needle in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise AssertionError(f"fixture router saw unexpected url: {url}")

    return fake


class FakeAdapter:
    """Scripted adapter; captures the exact request the Session assembled."""

    instances: list["FakeAdapter"] = []
    script: str = "plain"

    def __init__(self, cap, *, api_key=None, transport=None):
        self.cap = cap
        self.api_key = api_key or ""
        self.requests: list[ProviderRequest] = []
        FakeAdapter.instances.append(self)

    @classmethod
    def from_env(cls, cap, *, transport=None):
        return cls(cap, api_key=os.environ.get(cap.env_var, ""))

    def describe(self):
        return self.cap

    def complete(self, request):
        self.requests.append(request)
        if self.script == "plain":
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            yield {"event": "text_delta", "index": 0, "text": "fixture-reply"}
            yield {"event": "block_stop", "index": 0}
            yield {"event": "usage", "usage": UsageRecord(input_tokens=3, output_tokens=2)}
            yield {"event": "message_stop", "stop_reason": "end_turn"}
            return
        if self.script == "error":
            raise ProviderError("fixture rate limit", "rate_limit", 429, retryable=True)
        raise AssertionError(f"unknown fixture script {self.script!r}")


@pytest.fixture
def turn_bridge(tmp_path, monkeypatch):
    """Real HTTP bridge + fixture adapter + fixture provider probe."""
    for var in settings_store.provider_env_var().values():
        monkeypatch.delenv(var, raising=False)
    # Provider turns resolve a chain via _key_for(); a fixture key makes the
    # registry build the (monkeypatched) fixture adapter. Never a real key.
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "fixture-key")
    monkeypatch.setattr(provider_registry, "_PROVIDERS", {"openrouter": FIXTURE_CAP})
    monkeypatch.setattr(
        provider_registry,
        "build_adapter",
        lambda name, *a, **k: FakeAdapter(FIXTURE_CAP, api_key="fixture-key"),
    )
    FakeAdapter.instances = []
    FakeAdapter.script = "plain"
    session_keys._SESSION_SET.clear()
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, webapp.token()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        session_keys._SESSION_SET.clear()


def _req(server, method, path, body=None, token=None, raw=False):
    conn = http.client.HTTPConnection(
        "127.0.0.1", server.server_address[1], timeout=20
    )
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {}
    if token is not None:
        headers["X-Keel-Token"] = token
    if data is not None:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    if raw:
        return resp.status, payload
    return resp.status, json.loads(payload.decode("utf-8") or "{}")


def _wait(predicate, timeout=8.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _create_bot(server, engine="provider", **over):
    status, created = _req(
        server,
        "POST",
        "/api/fleet/bots",
        {"name": "verify-agent", "engine": engine, **over},
        webapp.token(),
    )
    assert status == 201, created
    return created["bot"]


def _rows(server, bot_id):
    status, body = _req(
        server, "GET", f"/api/fleet/bots/{bot_id}/rows", token=webapp.token()
    )
    return body.get("rows", [])


# ---------------------------------------------------------------------------
# 2a. Model catalog: live (fixture probe) vs offline (bundled catalogue)
# ---------------------------------------------------------------------------

def test_fixture_live_catalog_reports_key_source(turn_bridge, monkeypatch):
    """FIXTURE probe: live catalog carries models_meta and a key_source."""
    server, token = turn_bridge
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "fixture-env-key")
    monkeypatch.setattr(
        session_keys,
        "_http_json",
        _fixture_router({"/auth/key": FAKE_PROBE_OK, "/models": FAKE_CATALOG}),
    )
    status, body = _req(
        server, "POST", "/api/fleet/providers/catalog", {"name": "openrouter"}, token
    )
    assert status == 200 and body["ok"] is True
    assert body["models"] == ["fixture/a", "fixture/b:free"]
    assert body["model_count"] == 2
    assert body["key_source"] == "env:KEEL_OPENROUTER_API_KEY"
    assert body["models_meta"][0]["context_length"] == 128000
    assert body["models_meta"][1]["reasoning"]["supported_efforts"] == ["low", "high"]
    # A live response is NOT tagged source:"offline" — this is the field the UI reads.
    assert body.get("source") != "offline"


def test_fixture_live_catalog_after_session_key_uses_session_source(
    turn_bridge, monkeypatch
):
    """FIXTURE: after UI credential entry the live catalog reports 'session'."""
    server, token = turn_bridge
    monkeypatch.setattr(
        session_keys,
        "_http_json",
        _fixture_router({"/auth/key": FAKE_PROBE_OK, "/models": FAKE_CATALOG}),
    )
    _req(
        server,
        "POST",
        "/api/fleet/providers/credential",
        {"name": "openrouter", "key": "sk-fixture-session"},
        token,
    )
    status, body = _req(
        server, "POST", "/api/fleet/providers/catalog", {"name": "openrouter"}, token
    )
    assert body["ok"] is True and body["key_source"] == "session"


def test_fixture_offline_catalog_needs_no_key_and_no_network(turn_bridge, monkeypatch):
    """FIXTURE: offline catalog is bundled, tagged source:'offline'."""
    server, token = turn_bridge
    monkeypatch.delenv("KEEL_OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        session_keys,
        "_http_json",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("offline catalog must not touch the network")
        ),
    )
    status, body = _req(
        server,
        "POST",
        "/api/fleet/providers/catalog",
        {"name": "google", "source": "offline"},
        token,
    )
    assert status == 200 and body["ok"] is True
    assert body["source"] == "offline"
    assert body["catalog_version"]
    assert any("gemini" in m for m in body["models"])
    assert "key_source" not in body  # no credential is involved


def test_fixture_live_catalog_without_key_reports_not_configured(
    turn_bridge, monkeypatch
):
    """FIXTURE: a live catalog request without any key is refused honestly."""
    server, token = turn_bridge
    monkeypatch.delenv("KEEL_OPENROUTER_API_KEY", raising=False)
    status, body = _req(
        server, "POST", "/api/fleet/providers/catalog", {"name": "openrouter"}, token
    )
    assert body["ok"] is False and body["error"] == "not_configured"


# ---------------------------------------------------------------------------
# 2b. Per-agent model configuration is really used by the turn
# ---------------------------------------------------------------------------

def test_fixture_per_agent_model_is_used_by_provider_turn(turn_bridge):
    """FIXTURE adapter: bots/:id/update('model') reaches the wire request."""
    server, token = turn_bridge
    bot = _create_bot(server)
    status, updated = _req(
        server,
        "POST",
        f"/api/fleet/bots/{bot['id']}/update",
        {"provider": "openrouter", "model": "fixture/chosen-7b"},
        token,
    )
    assert status == 200 and updated["bot"]["model"] == "fixture/chosen-7b"

    status, _ = _req(
        server,
        "POST",
        f"/api/fleet/bots/{bot['id']}/messages",
        {"content": "use my model"},
        token,
    )
    assert status == 202
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(server, bot["id"])))

    assert FakeAdapter.instances, "fixture adapter was never constructed"
    assert FakeAdapter.instances[0].requests[0].model == "fixture/chosen-7b"
    assistant = next(
        r
        for r in _rows(server, bot["id"])
        if r["kind"] == "message" and r["body"].get("role") == "assistant"
    )
    assert assistant["body"]["model"] == "fixture/chosen-7b"
    assert assistant["body"]["engine"] == "openrouter"


# ---------------------------------------------------------------------------
# 2c. Provider errors, cancellation and timeout propagation
# ---------------------------------------------------------------------------

def test_fixture_provider_error_surfaces_as_error_row(turn_bridge):
    """FIXTURE: a ProviderError becomes a visible notice + terminal_reason."""
    server, token = turn_bridge
    FakeAdapter.script = "error"
    bot = _create_bot(server)
    status, _ = _req(
        server,
        "POST",
        f"/api/fleet/bots/{bot['id']}/messages",
        {"content": "trigger error"},
        token,
    )
    assert status == 202
    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(server, bot["id"])))
    rows = _rows(server, bot["id"])
    notices = [r for r in rows if r["kind"] == "notice"]
    assert any("Provider error" in r["body"].get("text", "") for r in notices)
    turn_end = next(r for r in rows if r["kind"] == "turn_end")
    assert turn_end["body"]["terminal_reason"] == "provider_error"


def test_fixture_cancel_propagates_to_cancelled_turn(turn_bridge, monkeypatch):
    """FIXTURE: operator Stop propagates through the model client mid-stream."""
    server, token = turn_bridge
    emitted = threading.Event()
    gate = threading.Event()

    class GatedAdapter(FakeAdapter):
        def complete(self, request):
            self.requests.append(request)
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            emitted.set()
            gate.wait(timeout=5)  # hold the turn mid-stream
            yield {"event": "text_delta", "index": 0, "text": "never delivered"}

    monkeypatch.setattr(
        provider_registry,
        "build_adapter",
        lambda name, *a, **k: GatedAdapter(FIXTURE_CAP, api_key="fixture-key"),
    )
    bot = _create_bot(server)
    _req(
        server,
        "POST",
        f"/api/fleet/bots/{bot['id']}/messages",
        {"content": "long running"},
        token,
    )
    assert emitted.wait(timeout=5), "fixture turn never started"
    status, body = _req(
        server, "POST", f"/api/fleet/bots/{bot['id']}/cancel", {}, token
    )
    assert status == 200 and body["cancelled"] is True
    gate.set()

    assert _wait(lambda: any(r["kind"] == "turn_end" for r in _rows(server, bot["id"])))
    rows = _rows(server, bot["id"])
    turn_end = next(r for r in rows if r["kind"] == "turn_end")
    assert turn_end["body"]["terminal_reason"] == "cancelled"
    # turn_core.cancel_active_turn() documents: "The in-flight model round-trip
    # (one HTTP stream) completes; no further model round-trips or tool
    # executions are issued." The delta released after Stop is therefore
    # observed in the transcript, and the Stop takes effect at the round
    # boundary. True mid-stream abort is an opt-in capability of
    # ProviderModelClient(cancel_event=...) — verified separately below.
    assert any(
        "never delivered" in str(r["body"].get("content", "")) for r in rows
    )


def test_fixture_mid_stream_cancel_raises_turn_cancelled():
    """FIXTURE: ProviderModelClient observes cancel_event between deltas."""
    cancel = threading.Event()

    class Cancellable(FakeAdapter):
        def complete(self, request):
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            cancel.set()
            yield {"event": "text_delta", "index": 0, "text": "partial"}

    client = ProviderModelClient(
        Cancellable(FIXTURE_CAP, api_key="k"),
        model="fixture/m",
        cancel_event=cancel,
    )
    with pytest.raises(TurnCancelled):
        client.complete([{"role": "user", "content": "hi"}], [])


def test_fixture_configured_timeout_reaches_network_edge(monkeypatch):
    """FIXTURE: the 120s request timeout reaches the transport, and URLError maps."""
    captured: dict = {}

    def recording_transport(request):
        captured["timeout"] = request.get("timeout")
        return 200, {}, iter(
            [
                b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n',
                b"data: [DONE]\n\n",
            ]
        )

    adapter = OpenAICompatibleAdapter(
        FIXTURE_CAP, api_key="k", transport=recording_transport
    )
    client = ProviderModelClient(adapter, model="fixture/m")
    blocks = client.complete([{"role": "user", "content": "hi"}], [])
    assert blocks and blocks[0]["text"] == "ok"
    assert captured["timeout"] == 120

    # A transport timeout (URLError) is surfaced as a retryable ProviderError.
    def urlopen_stub(request, timeout=None):
        captured["urlopen_timeout"] = timeout
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", urlopen_stub)
    with pytest.raises(ProviderError) as exc:
        http_transport({"url": "https://fixture.invalid/v1/messages",
                        "timeout": 120})
    assert exc.value.category == RETRY_UNKNOWN
    assert exc.value.retryable is True
    assert captured["urlopen_timeout"] == 120


# ---------------------------------------------------------------------------
# 2d. The UI-visible signal that separates fixture/scripted from live
# ---------------------------------------------------------------------------

def test_fixture_payload_carries_live_and_offline_markers(turn_bridge, monkeypatch):
    """FIXTURE: bridge payloads contain the exact fields the UI branches on."""
    server, token = turn_bridge
    monkeypatch.setattr(
        session_keys,
        "_http_json",
        _fixture_router({"/auth/key": FAKE_PROBE_OK, "/models": FAKE_CATALOG}),
    )
    _req(
        server,
        "POST",
        "/api/fleet/providers/credential",
        {"name": "openrouter", "key": "sk-fixture-live-marker"},
        token,
    )
    _, live = _req(
        server, "POST", "/api/fleet/providers/catalog", {"name": "openrouter"}, token
    )
    _, offline = _req(
        server,
        "POST",
        "/api/fleet/providers/catalog",
        {"name": "google", "source": "offline"},
        token,
    )
    # ProvidersSettings.tsx branches on catalog.source === "offline" and otherwise
    # renders `live · ${key_source}`. Both signals must be present and distinct.
    assert live["ok"] is True and live["key_source"] == "session"
    assert live.get("source") != "offline"
    assert offline["ok"] is True and offline["source"] == "offline"
    assert "key_source" not in offline

    # Agents.tsx / support.ts branch on engine === "echo" ("Scripted Echo agent").
    echo_bot = _create_bot(server, engine="echo")
    _, listing = _req(server, "GET", "/api/fleet/bots", token=token)
    listed = next(b for b in listing["bots"] if b["id"] == echo_bot["id"])
    assert listed["engine"] == "echo"


def test_ui_source_reads_fixture_and_live_markers():
    """Static check: the shipped UI consumes the bridge markers verified above."""
    ui_root = Path(__file__).resolve().parents[1] / "fleet-next"
    providers_ui = (
        ui_root / "features" / "settings" / "ProvidersSettings.tsx"
    ).read_text(encoding="utf-8")
    agents_ui = (ui_root / "features" / "fleet" / "Agents.tsx").read_text(
        encoding="utf-8"
    )
    support_ui = (ui_root / "features" / "fleet" / "support.ts").read_text(
        encoding="utf-8"
    )
    assert 'catalog.source === "offline"' in providers_ui
    assert "offline catalogue" in providers_ui
    assert "live ·" in providers_ui
    assert 'bot.engine === "echo"' in providers_ui
    assert 'text(b.engine) === "echo"' in agents_ui
    assert "scripted (Echo)" in agents_ui
    assert "never shown as a live model run" in agents_ui
    assert 'text(engine).toLowerCase() === "echo"' in support_ui
    assert "Scripted (Echo)" in support_ui


def test_cancel_active_turn_reports_false_without_a_turn(turn_bridge):
    """FIXTURE: Stop is honest when no turn is in flight."""
    assert turn_core.cancel_active_turn("no-such-bot") is False
