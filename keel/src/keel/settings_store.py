"""keel.settings_store — shared read/write helpers for ~/.keel/settings.json.

One local, user-owned file holds Keel's own configuration: the MCP
connector registry (managed by keel.fleet.connector_ops), the provider API
keys the user explicitly chose to persist here, and the UI preferences the
desktop PWA saves. Everything in it is as readable as the user's shell
environment — any process running as this account can read the file. That
is the trade-off the operator selected for their machine.

Guarantees kept:
- never assume the file is valid — load() tolerates BOMs, trailing junk
  and missing keys, exactly like connector_ops does;
- secrets never leave this module except through the provider registry,
  which reports only presence and (for the UI) a last-4 hint;
- writes keep one rolling backup at settings.json.bak before replacing;
- unknown top-level sections are preserved verbatim.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from . import secret_store
from .jsonc import loads as jsonc_loads
from .settings import default_state_root

# Derived from the one authoritative resolver in keel.settings, so CLI,
# web runtime and this store agree on where durable state lives.
STATE_DIR = default_state_root()
SETTINGS_PATH = STATE_DIR / "settings.json"
BACKUP_PATH = STATE_DIR / "settings.json.bak"

_SCHEMA = ("mcpServers", "providerKeys", "providerConfig", "ui")

# module-level set of env vars this process applied from the store, so we
# never stomp a shell-provided key with a stored one we didn't apply.
_APPLIED_FROM_STORE: set[str] = set()


def _parse_bytes(raw: bytes) -> Optional[dict]:
    try:
        text = raw.lstrip(b"\xef\xbb\xbf")
        doc = jsonc_loads(text.decode("utf-8"))
        return doc if isinstance(doc, dict) else None
    except Exception:
        return None


def load() -> dict:
    try:
        raw = SETTINGS_PATH.read_bytes()
    except FileNotFoundError:
        return {}  # deliberately absent: never resurrect the backup
    except OSError:
        raw = None
    if raw is not None:
        doc = _parse_bytes(raw)
        if doc is not None:
            return doc
    # primary present but unreadable — try the rolling backup
    try:
        doc = _parse_bytes(BACKUP_PATH.read_bytes())
        return doc if doc is not None else {}
    except OSError:
        return {}


def save(doc: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if SETTINGS_PATH.is_file():
        try:
            shutil.copy2(SETTINGS_PATH, BACKUP_PATH)
            _harden(BACKUP_PATH)
        except OSError:
            pass
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    payload = json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8")
    # O_TRUNC (rather than O_EXCL) keeps concurrent saves from failing when a
    # previous run left a stale temp file; the 0600 creation mode still closes
    # the world-readable window for the normal case.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(tmp), flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    _harden(tmp)
    tmp.replace(SETTINGS_PATH)
    _harden(SETTINGS_PATH)


def _harden(path: Path) -> None:
    """Best-effort owner-only mode on a secret-bearing local file."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows has no POSIX mode bits


def get_ui(doc: Optional[dict] = None) -> dict:
    doc = doc if doc is not None else load()
    ui = doc.get("ui")
    return ui if isinstance(ui, dict) else {}


def get_provider_config(doc: Optional[dict] = None) -> dict:
    doc = doc if doc is not None else load()
    cfg = doc.get("providerConfig")
    return cfg if isinstance(cfg, dict) else {}


def get_provider_keys(doc: Optional[dict] = None) -> dict:
    doc = doc if doc is not None else load()
    keys = doc.get("providerKeys")
    return keys if isinstance(keys, dict) else {}


def _entry_key(entry: Any) -> Optional[str]:
    if not isinstance(entry, dict):
        return None
    key = entry.get("key")
    if not isinstance(key, str) or not key.strip():
        return None
    if entry.get("enc") == secret_store.ENC_MARKER:
        return secret_store.decrypt_secret(key, state_dir=STATE_DIR).strip()
    return key.strip()


def stored_key(name: str) -> Optional[str]:
    return _entry_key(get_provider_keys().get(name))


def stored_key_hint(name: str) -> Optional[str]:
    entry = get_provider_keys().get(name)
    hint = entry.get("hint") if isinstance(entry, dict) else None
    return hint if isinstance(hint, str) else None


def public_view(doc: Optional[dict] = None) -> dict:
    """Secret-free projection for the UI: hints and metadata only."""
    doc = doc if doc is not None else load()
    keys = get_provider_keys(doc)
    return {
        "ui": get_ui(doc),
        "providerConfig": get_provider_config(doc),
        "providerKeys": {
            name: {
                "hint": (entry.get("hint") or ""),
                "savedAt": entry.get("savedAt"),
            }
            for name, entry in keys.items()
            if isinstance(entry, dict)
        },
        "mcpCount": len((doc.get("mcpServers") or {})) if isinstance(
            doc.get("mcpServers"), dict) else 0,
    }


def save_provider_key(name: str, key: str) -> None:
    doc = load()
    keys = get_provider_keys(doc)
    keys[name] = {
        "key": secret_store.encrypt_secret(key, state_dir=STATE_DIR),
        "enc": secret_store.ENC_MARKER,
        "hint": key[-4:] if len(key) >= 4 else key,
        "savedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    doc["providerKeys"] = keys
    save(doc)
    apply_stored_keys(env_var_for=provider_env_var())


def remove_provider_key(name: str) -> bool:
    doc = load()
    keys = get_provider_keys(doc)
    entry = keys.pop(name, None)
    if entry is None:
        return False
    doc["providerKeys"] = keys
    save(doc)
    # drop the applied env var only if it matches what we stored
    env_var = provider_env_var().get(name)
    if env_var and env_var in _APPLIED_FROM_STORE:
        os.environ.pop(env_var, None)
        _APPLIED_FROM_STORE.discard(env_var)
    return True


def provider_env_var() -> dict[str, str]:
    return {
        "openrouter": "KEEL_OPENROUTER_API_KEY",
        "google": "KEEL_GOOGLE_API_KEY",
        "nvidia": "KEEL_NVIDIA_API_KEY",
        "anthropic": "KEEL_ANTHROPIC_API_KEY",
        "openai-compatible": "KEEL_COMPAT_API_KEY",
    }


def apply_stored_keys(*, env_var_for: Optional[dict[str, str]] = None) -> list[str]:
    """Set process env from the store for keys not already provided by the
    shell. Never overrides a shell key. Returns applied provider names."""
    applied = []
    mapping = env_var_for or provider_env_var()
    keys = get_provider_keys()
    for name, entry in keys.items():
        env_var = mapping.get(name)
        if not env_var:
            continue
        existing = os.environ.get(env_var, "").strip()
        stored = _entry_key(entry)
        if not stored:
            continue
        if existing and existing != stored:
            continue  # shell wins, untouched
        os.environ[env_var] = stored
        _APPLIED_FROM_STORE.add(env_var)
        applied.append(name)
    return applied


def merge_import(doc: dict, *, include_keys: bool) -> dict:
    """Merge a user-provided export into the store. Non-secret sections
    always merge; providerKeys only when include_keys is true. Unknown
    sections are preserved from the current store, never invented."""
    current = load()
    merged = dict(current)
    if isinstance(doc.get("ui"), dict):
        merged["ui"] = {**get_ui(current), **doc["ui"]}
    if isinstance(doc.get("providerConfig"), dict):
        cur = get_provider_config(current)
        inc = doc["providerConfig"]
        merged_cfg = dict(cur)
        if isinstance(inc.get("preferred"), str):
            merged_cfg["preferred"] = inc["preferred"]
        if isinstance(inc.get("models"), dict):
            merged_cfg["models"] = {**cur.get("models", {}), **inc["models"]}
        merged["providerConfig"] = merged_cfg
    if isinstance(doc.get("mcpServers"), dict):
        merged["mcpServers"] = doc["mcpServers"]
    if include_keys and isinstance(doc.get("providerKeys"), dict):
        keys = get_provider_keys(current)
        for name, entry in doc["providerKeys"].items():
            if isinstance(entry, dict) and isinstance(entry.get("key"), str) and entry["key"].strip():
                key = entry["key"].strip()
                # Imported keys must get the same AES-GCM-at-rest protection as
                # keys saved through save_provider_key(), otherwise an export
                # containing plaintext keys silently defeats encryption. An
                # already-encrypted entry is preserved verbatim (including its
                # marker) rather than being encrypted twice.
                encrypted = entry.get("enc") == secret_store.ENC_MARKER
                hint = entry.get("hint")
                if not isinstance(hint, str) or not hint:
                    hint = key[-4:] if len(key) >= 4 else key
                keys[name] = {
                    "key": key if encrypted else secret_store.encrypt_secret(
                        key, state_dir=STATE_DIR),
                    "enc": secret_store.ENC_MARKER,
                    "hint": hint,
                    "savedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
        merged["providerKeys"] = keys
        apply_stored_keys()
    save(merged)
    return public_view(merged)


def export_view() -> dict:
    """Secret-free export: ui + providerConfig + mcpServers only."""
    doc = load()
    return {
        "version": 1,
        "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ui": get_ui(doc),
        "providerConfig": get_provider_config(doc),
        "mcpServers": doc.get("mcpServers") if isinstance(
            doc.get("mcpServers"), dict) else {},
    }
