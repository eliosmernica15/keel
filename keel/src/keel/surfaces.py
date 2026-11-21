"""Unified surface configuration (C2.5).

Four product surfaces share one Python runtime but carry their own default
agent, permission mode and tool allowlist. Overrides live in the local
settings document; nothing here requires a hosted service.
"""

from __future__ import annotations

from . import settings_store
from .permissions import normalize_mode

SURFACES: dict[str, dict] = {
    "cowork": {
        "name": "Keel Cowork",
        "view": "chat",
        "default_agent": "cowork",
        "permission_mode": "default",
        "tools": ["read_file", "write_file", "edit_file", "web_fetch",
                  "web_search", "list_dir", "grep", "glob", "save_file"],
        "description": "Documents, folders, email, calendars and research.",
    },
    "code": {
        "name": "Keel Code",
        "view": "code",
        "default_agent": "code",
        "permission_mode": "default",
        "tools": ["read_file", "write_file", "edit_file", "apply_patch",
                  "glob", "grep", "run_shell", "run_tests", "git_status",
                  "git_diff", "project_summary"],
        "description": "Repository understanding, editing, testing and Git.",
    },
    "duet": {
        "name": "Keel Duet",
        "view": "code",
        "default_agent": "duet",
        "permission_mode": "default",
        "tools": ["read_file", "edit_file", "apply_patch", "grep", "glob",
                  "run_tests", "git_diff"],
        "description": "Live pairing with inline completion and reviewers.",
    },
    "fleet": {
        "name": "Keel Fleet",
        "view": "chat",
        "default_agent": "fleet",
        "permission_mode": "default",
        "tools": ["send_to_bot", "create_task", "update_task", "list_tasks",
                  "read_file", "glob", "grep"],
        "description": "Multi-agent teams, delegation and task boards.",
    },
}

_EDITABLE = ("default_agent", "permission_mode", "tools", "notes")


def _effective(name: str, overrides: dict) -> dict | None:
    base = SURFACES.get(name)
    if base is None:
        return None
    merged = dict(base)
    merged.update(overrides.get(name, {}) or {})
    merged["id"] = name
    return merged


def list_surfaces() -> list[dict]:
    doc = settings_store.load()
    overrides = doc.get("surfaces", {}) or {}
    return [_effective(name, overrides) for name in SURFACES]


def get_surface(name: str) -> dict | None:
    return _effective(name, (settings_store.load().get("surfaces", {}) or {}))


def update_surface(name: str, patch: dict) -> dict:
    if name not in SURFACES:
        raise KeyError(name)
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")
    doc = settings_store.load()
    overrides = dict(doc.get("surfaces", {}) or {})
    current = dict(overrides.get(name, {}) or {})
    for key, value in patch.items():
        if key not in _EDITABLE:
            continue
        if key == "permission_mode":
            value = normalize_mode(str(value))
        if key == "tools":
            if not isinstance(value, list):
                raise ValueError("tools must be a list")
            value = [str(item) for item in value][:100]
        current[key] = value
    overrides[name] = current
    doc["surfaces"] = overrides
    settings_store.save(doc)
    return _effective(name, overrides)
