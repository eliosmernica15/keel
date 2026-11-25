"""Round-2 release-gate verification: secret handling.

Checks AES-256-GCM-at-rest, masked descriptors, no secret in browser-facing
views or exports, and the approval-card redaction gap.
"""

from __future__ import annotations

import json

import pytest

from keel import secret_store, settings_store
from keel.fleet import approvals

SECRET = "sk-or-v1-" + "A1b2C3d4E5f6G7h8I9j0K1l2"


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    """A state root with a fixed local master key; no real keyring access."""
    monkeypatch.setattr(secret_store, "_master_key",
                        lambda state_dir: b"\x11" * 32)
    monkeypatch.setattr(settings_store, "STATE_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH",
                        tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "BACKUP_PATH",
                        tmp_path / "settings.json.bak")
    monkeypatch.delenv("KEEL_OPENROUTER_API_KEY", raising=False)
    settings_store._APPLIED_FROM_STORE.clear()

    # conftest's autouse fixture replaces settings_store.load with `lambda: {}`
    # for every test. Restore realistic file-backed reads for this isolated root.
    def _load():
        try:
            raw = settings_store.SETTINGS_PATH.read_bytes()
        except FileNotFoundError:
            return {}
        return settings_store._parse_bytes(raw) or {}

    monkeypatch.setattr(settings_store, "load", _load)
    return tmp_path


def test_encryption_is_aes_gcm_with_a_random_nonce(isolated_store):
    first = secret_store.encrypt_secret(SECRET, state_dir=isolated_store)
    second = secret_store.encrypt_secret(SECRET, state_dir=isolated_store)
    assert first != second
    assert SECRET not in first and SECRET not in second
    assert len(first) > len(SECRET)
    assert secret_store.decrypt_secret(first, state_dir=isolated_store) == SECRET
    assert secret_store.decrypt_secret(second, state_dir=isolated_store) == SECRET


def test_tampered_ciphertext_fails_closed(isolated_store):
    payload = secret_store.encrypt_secret(SECRET, state_dir=isolated_store)
    tampered = ("A" if payload[0] != "A" else "B") + payload[1:]
    with pytest.raises(secret_store.SecretStoreError):
        secret_store.decrypt_secret(tampered, state_dir=isolated_store)


def test_saved_key_is_encrypted_at_rest(isolated_store):
    settings_store.save_provider_key("openrouter", SECRET)
    raw = (isolated_store / "settings.json").read_text(encoding="utf-8")
    assert SECRET not in raw
    doc = json.loads(raw)
    entry = doc["providerKeys"]["openrouter"]
    assert entry["enc"] == secret_store.ENC_MARKER
    assert entry["key"] != SECRET
    assert settings_store.stored_key("openrouter") == SECRET


def test_browser_view_returns_only_a_four_character_hint(isolated_store):
    settings_store.save_provider_key("openrouter", SECRET)
    view = settings_store.public_view()
    entry = view["providerKeys"]["openrouter"]
    assert set(entry) == {"hint", "savedAt"}
    assert entry["hint"] == SECRET[-4:]
    assert SECRET not in json.dumps(view)


def test_export_view_has_no_provider_keys(isolated_store):
    settings_store.save_provider_key("openrouter", SECRET)
    view = settings_store.export_view()
    assert "providerKeys" not in view
    assert SECRET not in json.dumps(view)


def test_import_without_keys_cannot_reveal_a_saved_key(isolated_store):
    settings_store.save_provider_key("openrouter", SECRET)
    view = settings_store.merge_import({"ui": {"theme": "dark"}},
                                       include_keys=False)
    assert "providerKeys" not in view or SECRET not in json.dumps(view)


def test_plaintext_imported_key_is_encrypted_on_write(isolated_store):
    view = settings_store.merge_import(
        {"providerKeys": {"openrouter": {"key": SECRET}}}, include_keys=True)
    raw = (isolated_store / "settings.json").read_text(encoding="utf-8")
    assert SECRET not in raw
    assert view["providerKeys"]["openrouter"]["hint"] == SECRET[-4:]


def test_approval_card_summary_redacts_a_secret_in_shell_command():
    summary = approvals.args_summary("run_shell", {
        "command": f"curl -H 'Authorization: Bearer {SECRET}' https://example.test"})
    assert SECRET not in summary
