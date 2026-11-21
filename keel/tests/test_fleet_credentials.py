"""keel.fleet session keys — UI-entered provider keys, validated, session-only.

Covers: validate+store, catalog load, clear semantics, no key leakage in
responses or errors, parsing of provider model-list payloads. No network
is touched: the HTTP layer (_http_json) is monkeypatched.
"""

from __future__ import annotations

import http.client
import json
import os
import threading

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.fleet import session_keys
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord


OPENROUTER = CapabilityRecord(
    name="openrouter",
    base_url="https://openrouter.ai/api/v1",
    env_var="KEEL_OPENROUTER_API_KEY",
    default_model="openrouter/auto",
    supports_tools=True, supports_streaming=True,
)


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    session_keys._SESSION_SET.clear()
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "")  # scrub any ambient value
    monkeypatch.delenv("KEEL_OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("keel.providers.registry._PROVIDERS",
                        {"openrouter": OPENROUTER})
    db_path = tmp_path / "fleet.db"
    fleet_routes.reset_store_for_tests(db_path)
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield (server, webapp.token())
    server.shutdown()
    server.server_close()
    session_keys._SESSION_SET.clear()


def _req(server, method, path, body=None, token=None, raw=False):
    conn = http.client.HTTPConnection("127.0.0.1",
                                      server.server_address[1], timeout=10)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {}
    if token is not None:
        headers["X-Keel-Token"] = token
    if data:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    if raw:
        return resp.status, payload
    return resp.status, json.loads(payload.decode("utf-8") or "{}")


# ------------------------------------------------------------ validation

def _router(mapping):
    """Fake _http_json dispatched by URL substring → payload or exception."""
    def fake(url, headers, timeout):
        for needle, outcome in mapping.items():
            if needle in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise AssertionError(f"unexpected url: {url}")
    return fake


OPENROUTER_CATALOG = {"data": [{"id": "m/a"}, {"id": "m/b:free"}]}
OPENROUTER_PROBE_OK = {"data": {"label": "sk-test", "limit": None}}


def test_validate_and_store_session_key(bridge, monkeypatch):
    server, token = bridge
    monkeypatch.setattr(session_keys, "_http_json",
                        _router({"/auth/key": OPENROUTER_PROBE_OK,
                                 "/models": OPENROUTER_CATALOG}))
    status, body = _req(server, "POST", "/api/fleet/providers/credential",
                        {"name": "openrouter", "key": "sk-test-123"}, token)
    assert status == 200
    assert body["ok"] is True
    assert body["models"] == ["m/a", "m/b:free"]
    assert body["model_count"] == 2
    assert body["key_source"] == "session"
    assert os.environ["KEEL_OPENROUTER_API_KEY"] == "sk-test-123"
    # the provider now reports configured, flagged as session
    status, body = _req(server, "GET", "/api/fleet/providers", token=token)
    assert status == 200
    entry = next(p for p in body["providers"] if p["name"] == "openrouter")
    assert entry["configured"] is True
    assert entry["session"] is True
    assert body["session_keys"] == ["openrouter"]


def test_key_never_appears_in_response(bridge, monkeypatch):
    server, token = bridge
    secret = "sk-live-SECRET-DO-NOT-ECHO-9876543210"
    monkeypatch.setattr(session_keys, "_http_json",
                        _router({"/auth/key": OPENROUTER_PROBE_OK,
                                 "/models": {"data": [{"id": "m/x"}]}}))
    status, raw = _req(server, "POST", "/api/fleet/providers/credential",
                       {"name": "openrouter", "key": secret}, token, raw=True)
    assert secret.encode() not in raw
    status, raw = _req(server, "GET", "/api/fleet/providers",
                       token=token, raw=True)
    assert secret.encode() not in raw


def test_public_catalog_alone_never_validates_key(bridge, monkeypatch):
    """The bug the user hit: /models is public and must not accept a key."""
    server, token = bridge
    monkeypatch.setattr(session_keys, "_http_json",
                        _router({"/auth/key": session_keys.ProviderKeyError(
                                     "invalid_key",
                                     "provider rejected the key (HTTP 401)"),
                                 "/models": OPENROUTER_CATALOG}))
    status, body = _req(server, "POST", "/api/fleet/providers/credential",
                        {"name": "openrouter", "key": "totally-bogus-key"}, token)
    assert status == 200
    assert body["ok"] is False
    assert body["error"] == "invalid_key"
    assert "KEEL_OPENROUTER_API_KEY" not in os.environ


def test_invalid_key_is_rejected_and_env_untouched(bridge, monkeypatch):
    server, token = bridge
    monkeypatch.setattr(session_keys, "_http_json",
                        _router({"/auth/key": session_keys.ProviderKeyError(
                                     "invalid_key",
                                     "provider rejected the key (HTTP 401)"),
                                 "/models": OPENROUTER_CATALOG}))
    status, body = _req(server, "POST", "/api/fleet/providers/credential",
                        {"name": "openrouter", "key": "sk-wrong"}, token)
    assert status == 200
    assert body["ok"] is False
    assert body["error"] == "invalid_key"
    assert "KEEL_OPENROUTER_API_KEY" not in os.environ
    status, body = _req(server, "GET", "/api/fleet/providers", token=token)
    entry = next(p for p in body["providers"] if p["name"] == "openrouter")
    assert entry["configured"] is False


def test_network_error_is_rejected_and_env_untouched(bridge, monkeypatch):
    server, token = bridge

    monkeypatch.setattr(session_keys, "_http_json",
                        _router({"/auth/key": session_keys.ProviderKeyError(
                                     "network_error",
                                     "could not reach the provider"),
                                 "/models": OPENROUTER_CATALOG}))
    status, body = _req(server, "POST", "/api/fleet/providers/credential",
                        {"name": "openrouter", "key": "sk-whatever"}, token)
    assert status == 200
    assert body["ok"] is False
    assert body["error"] == "network_error"
    assert "KEEL_OPENROUTER_API_KEY" not in os.environ


def test_unknown_provider_and_bad_key_rejected(bridge):
    server, token = bridge
    status, body = _req(server, "POST", "/api/fleet/providers/credential",
                        {"name": "not-a-provider", "key": "x"}, token)
    assert status == 400 and body["ok"] is False
    status, body = _req(server, "POST", "/api/fleet/providers/credential",
                        {"name": "openrouter", "key": ""}, token)
    assert status == 400 and body["ok"] is False
    status, body = _req(server, "POST", "/api/fleet/providers/credential",
                        {"name": "openrouter", "key": "y" * 513}, token)
    assert status == 400 and body["ok"] is False
    assert "KEEL_OPENROUTER_API_KEY" not in os.environ


def test_credential_endpoint_requires_token(bridge):
    server, token = bridge
    status, body = _req(server, "POST", "/api/fleet/providers/credential",
                        {"name": "openrouter", "key": "sk-x"})
    assert status == 403


# --------------------------------------------------------------- clear

def test_clear_forgets_session_key(bridge, monkeypatch):
    server, token = bridge
    monkeypatch.setattr(session_keys, "_http_json",
                        _router({"/auth/key": OPENROUTER_PROBE_OK,
                                 "/models": {"data": [{"id": "m/a"}]}}))
    _req(server, "POST", "/api/fleet/providers/credential",
         {"name": "openrouter", "key": "sk-session"}, token)
    assert os.environ["KEEL_OPENROUTER_API_KEY"] == "sk-session"
    status, body = _req(server, "POST", "/api/fleet/providers/credential/clear",
                        {"name": "openrouter"}, token)
    assert body["ok"] is True
    assert "KEEL_OPENROUTER_API_KEY" not in os.environ
    # clearing again is a no-op, not a surprise
    status, body = _req(server, "POST", "/api/fleet/providers/credential/clear",
                        {"name": "openrouter"}, token)
    assert body["ok"] is False
    assert body["error"] == "not_session_key"


def test_clear_never_touches_env_origin_key(bridge, monkeypatch):
    server, token = bridge
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "env-owned-key")
    status, body = _req(server, "POST", "/api/fleet/providers/credential/clear",
                        {"name": "openrouter"}, token)
    assert body["ok"] is False
    assert os.environ["KEEL_OPENROUTER_API_KEY"] == "env-owned-key"


# ------------------------------------------------------------- catalog

def test_catalog_uses_env_key_without_echoing_it(bridge, monkeypatch):
    server, token = bridge
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "env-key-abc")
    monkeypatch.setattr(session_keys, "_http_json",
                        _router({"/auth/key": OPENROUTER_PROBE_OK,
                                 "/models": {"data": [{"id": "m/z"}]}}))
    status, raw = _req(server, "POST", "/api/fleet/providers/catalog",
                       {"name": "openrouter"}, token, raw=True)
    body = json.loads(raw.decode("utf-8"))
    assert body["ok"] is True
    assert body["key_source"] == "env:KEEL_OPENROUTER_API_KEY"
    assert body["models"] == ["m/z"]
    assert b"env-key-abc" not in raw


def test_catalog_offline_works_without_key_or_network(bridge, monkeypatch):
    server, token = bridge
    monkeypatch.delenv("KEEL_OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(session_keys, "_http_json",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("network must not be used")))
    status, body = _req(server, "POST", "/api/fleet/providers/catalog",
                        {"name": "google", "source": "offline"}, token)
    assert status == 200
    assert body["ok"] is True
    assert body["source"] == "offline"
    assert any("gemini" in m for m in body["models"])


def test_catalog_offline_unknown_provider(bridge):
    server, token = bridge
    status, body = _req(server, "POST", "/api/fleet/providers/catalog",
                        {"name": "not-a-provider", "source": "offline"}, token)
    assert body["ok"] is False
    assert body["error"] == "unknown_provider"


def test_catalog_without_key_reports_not_configured(bridge):
    server, token = bridge
    status, body = _req(server, "POST", "/api/fleet/providers/catalog",
                        {"name": "openrouter"}, token)
    assert body["ok"] is False
    assert body["error"] == "not_configured"


# ------------------------------------------------------------ parsing

def test_parse_models_google_shape():
    cap = CapabilityRecord(name="google", base_url="https://x",
                           env_var="KEEL_GOOGLE_API_KEY",
                           default_model="gemini-2.0-flash",
                           supports_tools=True, supports_streaming=True)
    payload = {"models": [{"name": "models/gemini-2.0-flash"},
                          {"name": "models/gemini-2.5-pro"},
                          {"no_name": "missing"},
                          "garbage"]}
    assert session_keys.parse_models(cap, payload) == [
        "gemini-2.0-flash", "gemini-2.5-pro"]


def test_parse_models_dedupes_and_caps():
    cap = OPENROUTER
    payload = {"data": [{"id": f"m/{i % 10}"} for i in range(500)]}
    models = session_keys.parse_models(cap, payload)
    assert len(models) == 10
    assert len(set(models)) == 10


def test_parse_models_meta_reasoning_efforts():
    """The UI's effort dropdown reads exactly this shape."""
    cap = OPENROUTER
    payload = {
        "data": [
            {"id": "anthropic/claude-sonnet-5",
             "supported_parameters": ["reasoning", "reasoning_effort", "tools"],
             "reasoning": {"mandatory": False, "default_enabled": True,
                           "supported_efforts": ["max", "high", "medium", "low", "none"],
                           "default_effort": "high"}},
            {"id": "nvidia/nemotron-3.5-super-vl:free",
             "supported_parameters": ["tools", "max_tokens"]},
        ],
    }
    meta = session_keys.parse_models_meta(cap, payload)
    assert len(meta) == 2
    reasoning = meta[0]
    assert reasoning["reasoning"]["supported_efforts"] == ["max", "high", "medium", "low", "none"]
    assert reasoning["reasoning"]["default_effort"] == "high"
    assert "tools" in reasoning["supported_parameters"]
    plain = meta[1]
    assert plain["reasoning"] is None
    assert meta[0]["supported_parameters"][:3] == ["reasoning", "reasoning_effort", "tools"]
