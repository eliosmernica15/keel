"""Distribution round — provider setup in first-run onboarding (FIXTURE, no keys).

The real HTTP bridge, settings_store file I/O, secret_store encryption and
fleet project logic run unmodified. Only the authenticated provider probe
(``session_keys._http_json``) is replaced with a deterministic fixture router.
Every bearer value below is synthetic (``sk-fixture-…``) and never contacts a
real provider.

Covers:
- honest connection status / masking on ``GET providers``;
- offline catalog browsing with provably no network;
- onboarding's exact credential + save payloads and result shapes;
- clear/remove scope and encrypted-at-rest storage;
- "add folder" is not "trust folder";
- the shipped onboarding/BFF source matches those routes and keeps keys out of
  browser storage.

Run with:  $env:PYTHONPATH='src'; python -m pytest tests/verify_distribution_provider_onboarding.py -q
"""

from __future__ import annotations

import http.client
import json
import os
import threading
from pathlib import Path

import pytest

import keel.webapp as webapp
from keel import secret_store, settings_store
from keel.fleet import routes as fleet_routes
from keel.fleet import session_keys
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_KEY = "sk-fixture-onboarding-9f3a"
FAKE_PROBE_OK = {"data": {"label": "fixture-accepted", "limit": None}}
FAKE_CATALOG = {"data": [{"id": "fixture/a"}, {"id": "fixture/b:free"}]}

_FIXTURE_CAPS = {
    "openrouter": CapabilityRecord(
        name="openrouter", base_url="https://fixture.invalid/v1",
        env_var="KEEL_OPENROUTER_API_KEY", default_model="fixture/auto"),
    "anthropic": CapabilityRecord(
        name="anthropic", base_url="https://fixture.invalid/v1",
        env_var="KEEL_ANTHROPIC_API_KEY", default_model="fixture/claude"),
}


def _fixture_router(mapping):
    def fake(url, headers, timeout):
        for needle, outcome in mapping.items():
            if needle in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise AssertionError(f"unexpected fixture provider URL: {url}")
    return fake


@pytest.fixture
def onboarding_bridge(tmp_path, monkeypatch):
    """Real bridge + real file store + fixture probe; synthetic keys only."""
    for var in settings_store.provider_env_var().values():
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KEEL_MASTER_PASSPHRASE", "verification-only-passphrase")
    monkeypatch.delenv("KEEL_STATE_DIR", raising=False)

    state = tmp_path / "state"
    monkeypatch.setattr(settings_store, "STATE_DIR", state)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", state / "settings.json")
    monkeypatch.setattr(settings_store, "BACKUP_PATH", state / "settings.json.bak")
    monkeypatch.setattr(settings_store, "_APPLIED_FROM_STORE", set())

    def _real_load():
        try:
            raw = settings_store.SETTINGS_PATH.read_bytes()
        except FileNotFoundError:
            return {}
        except OSError:
            raw = None
        if raw is not None:
            doc = settings_store._parse_bytes(raw)
            if doc is not None:
                return doc
        return {}

    # conftest.py stubs settings_store.load globally; restore genuine I/O here.
    monkeypatch.setattr(settings_store, "load", _real_load)
    monkeypatch.setattr(secret_store, "_master_key", lambda state_dir: b"V" * 32)
    monkeypatch.setattr(provider_registry, "_PROVIDERS", dict(_FIXTURE_CAPS))

    session_keys._SESSION_SET.clear()
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, webapp.token(), state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        session_keys._SESSION_SET.clear()


def _req(server, method, path, body=None, token=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1],
                                      timeout=10)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {}
    if token is not None:
        headers["X-Keel-Token"] = token
    if data is not None:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    resp = conn.getresponse()
    payload = resp.read()
    status = resp.status
    conn.close()
    return status, json.loads(payload.decode("utf-8") or "{}")


def _accept_fixture_key(monkeypatch):
    monkeypatch.setattr(session_keys, "_http_json", _fixture_router({
        "/auth/key": FAKE_PROBE_OK, "/models": FAKE_CATALOG,
    }))


# --------------------------------------------------------------------------
# 1. Connection status is honest and never leaks a key
# --------------------------------------------------------------------------

def test_provider_status_is_honest_and_unmasked_without_keys(onboarding_bridge):
    server, token, _ = onboarding_bridge
    status, body = _req(server, "GET", "/api/fleet/providers", token=token)
    assert status == 200
    assert len(body["providers"]) == len(_FIXTURE_CAPS)
    assert body["session_keys"] == []
    for entry in body["providers"]:
        assert entry["configured"] is False
        assert entry["session"] is False
        assert entry["key_source"] is None
        assert entry["key_hint"] is None
    assert "sk-" not in json.dumps(body)


def test_verify_result_matches_onboarding_contract_and_is_session_only(
        onboarding_bridge, monkeypatch):
    server, token, state = onboarding_bridge
    _accept_fixture_key(monkeypatch)

    # Exact payload built by Onboarding.tsx verifyCredential().
    status, body = _req(server, "POST", "/api/fleet/providers/credential",
                        {"name": "openrouter", "key": FIXTURE_KEY}, token)
    assert status == 200
    assert body["ok"] is True
    assert body["model_count"] == 2
    assert body["key_source"] == "session"
    assert body["note"].startswith("held for this process only")
    assert FIXTURE_KEY not in json.dumps(body)
    assert not (state / "settings.json").exists()
    assert os.environ["KEEL_OPENROUTER_API_KEY"] == FIXTURE_KEY

    _, listing = _req(server, "GET", "/api/fleet/providers", token=token)
    entry = next(p for p in listing["providers"] if p["name"] == "openrouter")
    assert entry["session"] is True
    assert listing["session_keys"] == ["openrouter"]
    assert FIXTURE_KEY not in json.dumps(listing)


def test_failed_verification_never_marks_a_provider_configured(
        onboarding_bridge, monkeypatch):
    server, token, state = onboarding_bridge
    from keel.fleet.session_keys import ProviderKeyError

    monkeypatch.setattr(session_keys, "_http_json", lambda *a, **k: (
        (_ for _ in ()).throw(ProviderKeyError(
            "invalid_key", "provider rejected the key (HTTP 401)"))
    ))
    status, body = _req(server, "POST", "/api/fleet/providers/credential",
                        {"name": "openrouter", "key": "sk-fixture-bad-0000"},
                        token)
    assert status == 200
    assert body["ok"] is False
    assert body["error"] == "invalid_key"
    assert "HTTP 401" in body["detail"]
    assert "sk-fixture" not in json.dumps(body)
    _, listing = _req(server, "GET", "/api/fleet/providers", token=token)
    assert listing["session_keys"] == []
    assert all(not p["session"] and not p["configured"]
               for p in listing["providers"])
    assert not (state / "settings.json").exists()


# --------------------------------------------------------------------------
# 2. Catalog browsing in the wizard is offline and network-free
# --------------------------------------------------------------------------

def test_onboarding_offline_catalog_makes_no_network_call(
        onboarding_bridge, monkeypatch):
    server, token, _ = onboarding_bridge

    def no_network(*args, **kwargs):
        raise AssertionError("offline catalog must not call a provider")

    monkeypatch.setattr(session_keys, "_http_json", no_network)
    # Exact payload built by Onboarding.tsx's catalog effect.
    status, body = _req(server, "POST", "/api/fleet/providers/catalog",
                        {"name": "anthropic", "source": "offline"}, token)
    assert status == 200
    assert body["ok"] is True
    assert body["source"] == "offline"
    assert body["catalog_version"]
    assert body["model_count"] == len(body["models"]) >= 1
    assert "key_source" not in body  # browsing is not a connection test


# --------------------------------------------------------------------------
# 3. Save / clear / remove keep secrets local and scope-limited
# --------------------------------------------------------------------------

def test_save_returns_only_a_hint_and_encrypts_at_rest(
        onboarding_bridge, monkeypatch):
    server, token, state = onboarding_bridge
    _accept_fixture_key(monkeypatch)
    _req(server, "POST", "/api/fleet/providers/credential",
         {"name": "openrouter", "key": FIXTURE_KEY}, token)

    status, body = _req(server, "POST", "/api/fleet/providers/save",
                        {"name": "openrouter", "key": FIXTURE_KEY}, token)
    assert status == 200
    assert body["ok"] is True
    assert body["hint"] == FIXTURE_KEY[-4:]
    assert len(body["hint"]) == 4
    assert FIXTURE_KEY not in json.dumps(body)

    raw = (state / "settings.json").read_text(encoding="utf-8")
    assert FIXTURE_KEY not in raw
    saved = json.loads(raw)["providerKeys"]["openrouter"]
    assert saved["enc"] == secret_store.ENC_MARKER
    assert saved["hint"] == FIXTURE_KEY[-4:]
    assert settings_store.stored_key("openrouter") == FIXTURE_KEY

    # export_view is secret-free even when the user exports settings.
    assert "providerKeys" not in settings_store.export_view()
    _, listing = _req(server, "GET", "/api/fleet/providers", token=token)
    assert FIXTURE_KEY not in json.dumps(listing)
    entry = next(p for p in listing["providers"] if p["name"] == "openrouter")
    assert entry["key_source"] == "env:KEEL_OPENROUTER_API_KEY"


def test_clear_and_remove_are_scope_limited(onboarding_bridge, monkeypatch):
    server, token, state = onboarding_bridge
    _accept_fixture_key(monkeypatch)
    _req(server, "POST", "/api/fleet/providers/credential",
         {"name": "openrouter", "key": FIXTURE_KEY}, token)
    _req(server, "POST", "/api/fleet/providers/save",
         {"name": "openrouter", "key": FIXTURE_KEY}, token)

    status, body = _req(server, "POST",
                        "/api/fleet/providers/credential/clear",
                        {"name": "openrouter"}, token)
    assert status == 200 and body["ok"] is True
    assert body["provider"] == "openrouter"
    _, again = _req(server, "POST", "/api/fleet/providers/credential/clear",
                    {"name": "openrouter"}, token)
    assert again["error"] == "not_session_key"
    # Saved key survives session clear and stays encrypted.
    assert (state / "settings.json").exists()
    assert settings_store.stored_key("openrouter") == FIXTURE_KEY

    status, body = _req(server, "POST", "/api/fleet/providers/remove",
                        {"name": "openrouter"}, token)
    assert status == 200 and body == {"ok": True, "provider": "openrouter"}
    assert settings_store.stored_key("openrouter") is None
    _, again = _req(server, "POST", "/api/fleet/providers/remove",
                    {"name": "openrouter"}, token)
    assert again["error"] == "not_saved"


# --------------------------------------------------------------------------
# 4. Workspace trust is an explicit second decision, never a sidebar effect
# --------------------------------------------------------------------------

def test_add_folder_is_not_trust_and_file_access_needs_explicit_trust(
        onboarding_bridge, tmp_path):
    server, token, _ = onboarding_bridge
    folder = tmp_path / "my-project"
    folder.mkdir()
    (folder / "note.txt").write_text("private", encoding="utf-8")

    # Exact payload built by Onboarding.tsx addProject().
    status, body = _req(server, "POST", "/api/fleet/projects",
                        {"path": str(folder)}, token)
    assert status == 201
    project = body["project"]
    assert project["id"] and not project["trusted"]  # SQLite stores 0/1

    status, blocked = _req(server, "GET",
                           f"/api/fleet/projects/{project['id']}/file/read?path=note.txt",
                           token=token)
    assert status == 403
    assert blocked["error"] == "workspace_not_trusted"

    # Exact payload built by Onboarding.tsx trustProject(trusted).
    status, body = _req(server, "POST",
                        f"/api/fleet/projects/{project['id']}/trust",
                        {"trusted": True}, token)
    assert status == 200
    assert bool(body["project"]["trusted"]) is True
    status, readable = _req(
        server, "GET",
        f"/api/fleet/projects/{project['id']}/file/read?path=note.txt",
        token=token)
    assert status == 200
    assert "private" in json.dumps(readable)


# --------------------------------------------------------------------------
# 5. Shipped source contracts (static, no runtime credential required)
# --------------------------------------------------------------------------

def test_onboarding_source_uses_the_real_bridge_routes_and_password_input():
    tsx = (ROOT / "fleet-next/features/onboarding/Onboarding.tsx").read_text(
        encoding="utf-8")
    api = (ROOT / "fleet-next/lib/api.ts").read_text(encoding="utf-8")
    client = (ROOT / "fleet-next/lib/client.ts").read_text(encoding="utf-8")
    bff = (ROOT / "fleet-next/app/api/bridge/[...path]/route.ts").read_text(
        encoding="utf-8")

    # The wizard calls real routes; it never invents a local provider shortcut.
    assert 'bridge.setCredential({ name, key })' in tsx
    assert 'bridge.saveProvider({ name, key })' in tsx
    assert 'bridge.catalog({ name: providerName, source: "offline" })' in tsx
    assert 'bridge.addProject({ path })' in tsx
    assert 'bridge.trustProject(pendingTrustId, trusted)' in tsx
    for route in ('api("providers/credential"', 'api("providers/save"',
                  'api<CatalogResponse>("providers/catalog"',
                  'api("projects"', 'projects/${id}/trust'):
        assert route in api
    assert '/api/bridge/${path.replace(/^\\//, "")}' in client

    # Validation is performed by the credential call itself; Save is gated.
    assert 'if (!sessionVerified || !name || !key)' in tsx
    assert 'setSessionVerified(true)' in tsx
    assert 'setSessionVerified(false)' in tsx
    assert 'useEffect(() => () => setSecret(""), [current === "provider"])' in tsx

    # Secure entry + masking copy.
    assert 'type="password"' in tsx
    assert 'autoComplete="off"' in tsx
    assert 'spellCheck={false}' in tsx
    assert 'The bridge never returns a full key to the UI.' in tsx

    # Token stays server-side; browser headers are stripped at the BFF.
    assert 'headers.delete("cookie")' in bff
    assert 'headers.delete("origin")' in bff
    assert 'headers.set("x-keel-token", BRIDGE_TOKEN)' in bff
    assert 'process.env.KEEL_BRIDGE_TOKEN' in bff


def test_onboarding_progress_storage_is_ui_preferences_only():
    progress = (ROOT / "fleet-next/features/onboarding/progress.ts").read_text(
        encoding="utf-8")
    tsx = (ROOT / "fleet-next/features/onboarding/Onboarding.tsx").read_text(
        encoding="utf-8")
    assert "localStorage" not in tsx  # no key ever written by the wizard
    for key in ('keel-onboarding:step', 'keel-onboarding:checklist',
                'keel-mode'):
        assert f'"{key}"' in progress
    # Ignore prose comments; only executable code may touch storage keys.
    code = "\n".join(line for line in progress.splitlines()
                     if not line.lstrip().startswith("//")).lower()
    for forbidden in ("api_key", "apikey", "secret", "credential", "token"):
        assert forbidden not in code
