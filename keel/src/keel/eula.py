"""Local EULA acceptance with version re-prompt (C11.5).

Stores acceptance of a specific EULA version in local settings only. The
legal text is a draft and finalization remains owner-gated; this module just
tracks the user's accept/re-prompt state and never sends it anywhere.
"""

from __future__ import annotations

from . import settings_store

EULA_KEY = "eulaAcceptedVersion"


def accepted_version(doc: dict | None = None) -> str | None:
    doc = doc if doc is not None else settings_store.load()
    ui = doc.get("ui", {}) or {}
    value = ui.get(EULA_KEY) if isinstance(ui, dict) else doc.get(EULA_KEY)
    return str(value) if value else None


def needs_acceptance(current_version: str, doc: dict | None = None) -> bool:
    return accepted_version(doc) != str(current_version)


def accept(current_version: str) -> str:
    doc = settings_store.load()
    ui = dict(doc.get("ui", {}) or {}) if isinstance(doc.get("ui", {}), dict) else {}
    ui[EULA_KEY] = str(current_version)
    doc["ui"] = ui
    settings_store.save(doc)
    return str(current_version)


def decline() -> None:
    doc = settings_store.load()
    ui = dict(doc.get("ui", {}) or {}) if isinstance(doc.get("ui", {}), dict) else {}
    ui.pop(EULA_KEY, None)
    doc["ui"] = ui
    settings_store.save(doc)
