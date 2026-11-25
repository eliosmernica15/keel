"""FIXTURE-BASED verification — provider credential lifecycle (no credentials).

Label: FIXTURE / fake transport + fake HTTP probe. No real provider key, no
network, no credential is ever used here. The real bridge, settings_store and
secret_store encryption all run unmodified; only the provider HTTP probe
(``session_keys._http_json``) is replaced by a deterministic fixture router.

Covers requirement 1 of the provider verification round:
    secure entry -> validation -> session key vs saved key -> masking ->
    clear / remove.

Every test asserts that the full key never appears in any HTTP response or in
the on-disk settings file. Only a 4-character hint is ever exposed.
"""

from __future__ import annotations

import http.client
import json
import threading

import pytest

import keel.webapp as webapp
from keel import secret_store, settings_store
from keel.fleet import routes as fleet_routes
from keel.fleet import session_keys
from keel.providers import registry as provider_registry
from keel.providers.base import CapabilityRecord

# A synthetic provider record. The base_url is never contacted: the probe is
# intercepted by the fixture router below.
FIXTURE_CAP = CapabilityRecord(
    name="openrouter",
    base_url="https://fixture.invalid/v1",
    env_var="KEEL_OPENROUTER_API_KEY",
    default_model="fixture/auto",
    supports_tools=True,
    supports_streaming=True,
)

FAKE_PROBE_OK = {"data": {"label": "fixture-accepted", "limit": None}}
FAKE_CATALOG = {"data": [{"id": "fixture/a"}, {"id": "fixture/b:free"}]}


def _fixture_router(mapping):
    """Return a fake ``_http_json`` that dispatches on a URL substring."""

    def fake(url, headers, timeout):
        for needle, outcome in mapping.items():
            if needle in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise AssertionError(f"fixture router saw unexpected url: {url}")

    return fake


@pytest.fixture
def credential_bridge(tmp_path, monkeypatch):
    """Real HTTP bridge + real store/crypto + fixture provider probe."""
    # Scrub and register every provider env var for restoration. monkeypatch
    # restores "absent" at teardown even when code writes to os.environ directly.
    for var in settings_store.provider_env_var().values():
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KEEL_MASTER_PASSPHRASE", "verification-only-passphrase")
    monkeypatch.delenv("KEEL_STATE_DIR", raising=False)

    state = tmp_path / "state"
    monkeypatch.setattr(settings_store, "STATE_DIR", state)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", state / "settings.json")
    monkeypatch.setattr(settings_store, "BACKUP_PATH", state / "settings.json.bak")
    monkeypatch.setattr(settings_store, "_APPLIED_FROM_STORE", set())
    # conftest.py's autouse _no_mcp_servers fixture globally stubs
    # settings_store.load -> {}. Restore a real file-backed reader here so the
    # encrypted-at-rest assertions observe the genuine on-disk state.
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

    monkeypatch.setattr(settings_store, "load", _real_load)
    # Deterministic local master key; never touch a real OS keyring.
    monkeypatch.setattr(secret_store, "_master_key", lambda state_dir: b"V" * 32)

    monkeypatch.setattr(provider_registry, "_PROVIDERS", {"openrouter": FIXTURE_CAP})

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
        "127.0.0.1", server.server_address[1], timeout=10
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


def _accept_fixture_key(monkeypatch):
    monkeypatch.setattr(
        session_keys,
        "_http_json",
        _fixture_router({"/auth/key": FAKE_PROBE_OK, "/models": FAKE_CATALOG}),
    )


# ---------------------------------------------------------------------------
# 1a. Secure entry -> validation -> session key
# ---------------------------------------------------------------------------

def test_fixture_entry_validation_creates_session_key(credential_bridge, monkeypatch):
    """FYI: FIXTURE probe. A validated key becomes a process-only session key."""
    server, token = credential_bridge
    _accept_fixture_key(monkeypatch)
    key = "sk-fixture-session-123456"

    status, body = _req(
        server,
        "POST",
        "/api/fleet/providers/credential",
        {"name": "openrouter", "key": key},
        token,
    )
    assert status == 200
    assert body["ok"] is True
    assert body["models"] == ["fixture/a", "fixture/b:free"]
    assert body["model_count"] == 2
    assert body["key_source"] == "session"
    assert body["note"].startswith("held for this process only")

    # The bridge process now holds the key in its environment ...
    import os

    assert os.environ["KEEL_OPENROUTER_API_KEY"] == key
    # ... and reports it as a session key, never as a saved/env key.
    status, listing = _req(server, "GET", "/api/fleet/providers", token=token)
    entry = next(p for p in listing["providers"] if p["name"] == "openrouter")
    assert entry["configured"] is True
    assert entry["session"] is True
    assert entry["key_source"] == "env:KEEL_OPENROUTER_API_KEY"
    assert listing["session_keys"] == ["openrouter"]


def test_fixture_session_key_is_never_written_to_disk(
    credential_bridge, monkeypatch
):
    """FIXTURE: a session key must not persist anywhere on disk."""
    server, token = credential_bridge
    _accept_fixture_key(monkeypatch)
    key = "sk-fixture-never-on-disk"

    _req(
        server,
        "POST",
        "/api/fleet/providers/credential",
        {"name": "openrouter", "key": key},
        token,
    )
    settings_path = settings_store.SETTINGS_PATH
    if settings_path.exists():
        assert key.encode() not in settings_path.read_bytes()
    assert settings_store.get_provider_keys() == {}


def test_fixture_saved_key_is_encrypted_at_rest_and_masked(
    credential_bridge, monkeypatch
):
    """FIXTURE: saved keys use AES-256-GCM at rest; only a 4-char hint leaks."""
    server, token = credential_bridge
    _accept_fixture_key(monkeypatch)
    key = "sk-fixture-PERSIST-9876"

    status, raw = _req(
        server,
        "POST",
        "/api/fleet/providers/save",
        {"name": "openrouter", "key": key},
        token,
        raw=True,
    )
    body = json.loads(raw.decode("utf-8"))
    assert status == 200 and body["ok"] is True
    assert body["hint"] == key[-4:]  # exactly the last 4 characters
    assert len(body["hint"]) == 4
    assert key.encode() not in raw  # full key never returned

    # On disk: encrypted marker + hint, never plaintext.
    doc = settings_store.load()
    entry = doc["providerKeys"]["openrouter"]
    assert entry["enc"] == secret_store.ENC_MARKER
    assert entry["hint"] == key[-4:]
    assert entry["key"] != key
    on_disk = settings_store.SETTINGS_PATH.read_text(encoding="utf-8")
    assert key not in on_disk

    # The secret-free UI projection exposes only hint + savedAt.
    public = settings_store.public_view(doc)
    assert set(public["providerKeys"]["openrouter"]) == {"hint", "savedAt"}
    assert key not in json.dumps(public)


def test_fixture_saved_key_round_trips_through_decryption(
    credential_bridge, monkeypatch
):
    """FIXTURE: the encrypted key is genuinely recoverable by the registry."""
    server, token = credential_bridge
    _accept_fixture_key(monkeypatch)
    key = "sk-fixture-ROUNDTRIP-4242"

    _req(
        server,
        "POST",
        "/api/fleet/providers/save",
        {"name": "openrouter", "key": key},
        token,
    )
    assert settings_store.stored_key("openrouter") == key
    assert settings_store.stored_key_hint("openrouter") == key[-4:]
    assert provider_registry._key_for(FIXTURE_CAP) == key


def test_fixture_shell_env_takes_precedence_over_saved_key(
    credential_bridge, monkeypatch
):
    """FIXTURE: a shell-provided key is never overwritten by a saved key."""
    import os

    server, token = credential_bridge
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "shell-owned-key")
    _accept_fixture_key(monkeypatch)

    _req(
        server,
        "POST",
        "/api/fleet/providers/save",
        {"name": "openrouter", "key": "sk-fixture-saved-key"},
        token,
    )
    # The saved key is on disk, but the shell key still wins in memory.
    assert settings_store.stored_key("openrouter") == "sk-fixture-saved-key"
    assert os.environ["KEEL_OPENROUTER_API_KEY"] == "shell-owned-key"
    assert provider_registry._key_for(FIXTURE_CAP) == "shell-owned-key"


# ---------------------------------------------------------------------------
# 1b. Masking in every response + invalid key rejection
# ---------------------------------------------------------------------------

def test_fixture_full_key_absent_from_every_credential_response(
    credential_bridge, monkeypatch
):
    """FIXTURE: no credential endpoint echoes the key, on success or failure."""
    server, token = credential_bridge
    key = "sk-fixture-ULTRA-SECRET-NO-ECHO-5555"
    _accept_fixture_key(monkeypatch)

    endpoints = [
        ("POST", "/api/fleet/providers/credential", {"name": "openrouter", "key": key}),
        ("POST", "/api/fleet/providers/save", {"name": "openrouter", "key": key}),
        ("POST", "/api/fleet/providers/catalog", {"name": "openrouter"}),
        ("POST", "/api/fleet/providers/credential/clear", {"name": "openrouter"}),
        ("POST", "/api/fleet/providers/remove", {"name": "openrouter"}),
    ]
    for method, path, body in endpoints:
        _, raw = _req(server, method, path, body, token, raw=True)
        assert key.encode() not in raw, f"key leaked from {path}"
    _, raw = _req(server, "GET", "/api/fleet/providers", token=token, raw=True)
    assert key.encode() not in raw


def test_fixture_invalid_key_is_rejected_before_any_storage(
    credential_bridge, monkeypatch
):
    """FIXTURE: authenticated probe failure leaves no key in env or on disk."""
    import os

    server, token = credential_bridge
    monkeypatch.setattr(
        session_keys,
        "_http_json",
        _fixture_router(
            {
                "/auth/key": session_keys.ProviderKeyError(
                    "invalid_key", "provider rejected the key (HTTP 401)"
                ),
                "/models": FAKE_CATALOG,
            }
        ),
    )
    status, body = _req(
        server,
        "POST",
        "/api/fleet/providers/credential",
        {"name": "openrouter", "key": "sk-fixture-WRONG"},
        token,
    )
    assert status == 200 and body["ok"] is False
    assert body["error"] == "invalid_key"
    assert "KEEL_OPENROUTER_API_KEY" not in os.environ
    assert settings_store.get_provider_keys() == {}

    # Same guard on the persisted path.
    status, body = _req(
        server,
        "POST",
        "/api/fleet/providers/save",
        {"name": "openrouter", "key": "sk-fixture-WRONG"},
        token,
    )
    assert body["ok"] is False and body["error"] == "invalid_key"
    assert settings_store.get_provider_keys() == {}


# ---------------------------------------------------------------------------
# 1c. Clear (session) and remove (saved)
# ---------------------------------------------------------------------------

def test_fixture_clear_session_key_is_scope_limited(credential_bridge, monkeypatch):
    """FIXTURE: clear forgets only the session key, never an env/saved key."""
    import os

    server, token = credential_bridge
    _accept_fixture_key(monkeypatch)
    _req(
        server,
        "POST",
        "/api/fleet/providers/credential",
        {"name": "openrouter", "key": "sk-fixture-CLEAR-ME"},
        token,
    )
    assert os.environ["KEEL_OPENROUTER_API_KEY"] == "sk-fixture-CLEAR-ME"

    status, body = _req(
        server,
        "POST",
        "/api/fleet/providers/credential/clear",
        {"name": "openrouter"},
        token,
    )
    assert status == 200 and body["ok"] is True
    assert "KEEL_OPENROUTER_API_KEY" not in os.environ
    assert session_keys.session_providers() == []

    # Clearing again is an explicit no-op, not a surprise.
    status, body = _req(
        server,
        "POST",
        "/api/fleet/providers/credential/clear",
        {"name": "openrouter"},
        token,
    )
    assert body["ok"] is False and body["error"] == "not_session_key"


def test_fixture_clear_never_touches_env_owned_key(credential_bridge, monkeypatch):
    """FIXTURE: an operator's shell key is not cleared by the UI action."""
    import os

    server, token = credential_bridge
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "env-owned-key")
    status, body = _req(
        server,
        "POST",
        "/api/fleet/providers/credential/clear",
        {"name": "openrouter"},
        token,
    )
    assert body["ok"] is False and body["error"] == "not_session_key"
    assert os.environ["KEEL_OPENROUTER_API_KEY"] == "env-owned-key"


def test_fixture_remove_saved_key_is_scope_limited(
    credential_bridge, monkeypatch
):
    """FIXTURE: remove deletes the stored key and never touches shell env."""
    import os

    server, token = credential_bridge
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "shell-owned-key")
    _accept_fixture_key(monkeypatch)
    _req(
        server,
        "POST",
        "/api/fleet/providers/save",
        {"name": "openrouter", "key": "sk-fixture-REMOVE-ME"},
        token,
    )
    assert settings_store.stored_key("openrouter") == "sk-fixture-REMOVE-ME"

    status, body = _req(
        server,
        "POST",
        "/api/fleet/providers/remove",
        {"name": "openrouter"},
        token,
    )
    assert status == 200 and body["ok"] is True
    assert settings_store.stored_key("openrouter") is None
    assert os.environ["KEEL_OPENROUTER_API_KEY"] == "shell-owned-key"

    # Removing again reports the explicit no-saved-key state.
    status, body = _req(
        server,
        "POST",
        "/api/fleet/providers/remove",
        {"name": "openrouter"},
        token,
    )
    assert body["ok"] is False and body["error"] == "not_saved"


def test_fixture_credentials_require_bridge_token(credential_bridge):
    """FIXTURE: credential mutations never succeed without the bridge token."""
    server, _ = credential_bridge
    for path in (
        "/api/fleet/providers/credential",
        "/api/fleet/providers/save",
        "/api/fleet/providers/credential/clear",
        "/api/fleet/providers/remove",
    ):
        status, body = _req(
            server, "POST", path, {"name": "openrouter", "key": "sk-fixture-x"}
        )
        assert status == 403, f"{path} accepted an unauthenticated request"
