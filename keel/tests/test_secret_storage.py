"""Provider secrets must be encrypted at rest and remain readable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keel import secret_store, settings_store

# conftest's autouse fixture stubs settings_store.load for MCP isolation;
# capture the real functions at import time so this suite can restore them.
_REAL_LOAD = settings_store.load
_REAL_SAVE = settings_store.save


@pytest.fixture(autouse=True)
def _private_process_environment(monkeypatch):
    """Keep provider keys written by save_provider_key/apply_stored_keys from
    leaking into later tests (real hidden test pollution)."""
    import os
    monkeypatch.setattr(os, "environ", dict(os.environ))


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "load", _REAL_LOAD)
    monkeypatch.setattr(settings_store, "save", _REAL_SAVE)
    monkeypatch.setattr(settings_store, "STATE_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "BACKUP_PATH", tmp_path / "settings.json.bak")
    monkeypatch.setattr(secret_store, "_master_key", lambda state_dir: b"m" * 32)
    for var in settings_store.provider_env_var().values():
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_provider_key_is_encrypted_and_round_trips(isolated_store):
    secret = "sk-secret-value-1234"
    settings_store.save_provider_key("google", secret)

    raw = settings_store.SETTINGS_PATH.read_text(encoding="utf-8")
    assert secret not in raw
    doc = json.loads(raw)
    assert doc["providerKeys"]["google"]["enc"] == secret_store.ENC_MARKER
    assert settings_store.stored_key("google") == secret


def test_legacy_plaintext_key_is_readable_then_migrated(isolated_store):
    secret = "legacy-secret-1234"
    settings_store.SETTINGS_PATH.write_text(json.dumps({
        "providerKeys": {"google": {"key": secret, "hint": secret[-4:]}},
    }), encoding="utf-8")

    assert settings_store.stored_key("google") == secret
    settings_store.save_provider_key("google", secret)
    raw = settings_store.SETTINGS_PATH.read_text(encoding="utf-8")
    assert secret not in raw
    assert settings_store.stored_key("google") == secret


def test_public_view_never_exposes_key_material(isolated_store):
    settings_store.save_provider_key("google", "sk-secret-value-1234")
    view = settings_store.public_view()
    assert "key" not in view["providerKeys"]["google"]
    assert "sk-secret-value-1234" not in json.dumps(view)


def test_apply_stored_keys_uses_decrypted_value(isolated_store):
    secret = "sk-applied-secret-1234"
    settings_store.save_provider_key("google", secret)
    applied = settings_store.apply_stored_keys()
    assert "google" in applied
    assert __import__("os").environ["KEEL_GOOGLE_API_KEY"] == secret
