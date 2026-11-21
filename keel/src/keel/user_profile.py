"""Editable user profile (C6.4).

A small local profile stored in settings: name, role, preferences and notes.
The person can read and edit it; it is injected as context only if they opt in.
"""

from __future__ import annotations

from . import settings_store

PROFILE_KEY = "userProfile"


def get(doc: dict | None = None) -> dict:
    doc = doc if doc is not None else settings_store.load()
    profile = doc.get(PROFILE_KEY, {})
    return dict(profile) if isinstance(profile, dict) else {}


def update(patch: dict) -> dict:
    if not isinstance(patch, dict):
        raise ValueError("profile patch must be an object")
    doc = settings_store.load()
    current = get(doc)
    allowed = ("name", "role", "preferences", "notes")
    for key, value in patch.items():
        if key in allowed:
            current[key] = value
    doc[PROFILE_KEY] = current
    settings_store.save(doc)
    return current


def context_attachment(profile: dict | None = None) -> str:
    profile = profile if profile is not None else get()
    if not profile:
        return ""
    lines = ["<user-profile trust=\"user\">"]
    for key, value in profile.items():
        lines.append(f"{key}: {value}")
    lines.append("</user-profile>")
    return "\n".join(lines)
