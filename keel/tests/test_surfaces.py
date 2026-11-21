"""C2.5 — unified surface switcher with per-surface configuration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from keel import settings_store, surfaces

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings_tmp(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", path)
    monkeypatch.setattr(settings_store, "BACKUP_PATH",
                        tmp_path / "settings.json.bak")

    def _load():
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    # The suite-wide autouse fixture stubs load(); restore real file-backed
    # loading here so persistence is actually exercised.
    monkeypatch.setattr(settings_store, "load", _load)
    return tmp_path


def test_all_four_surfaces_registered(settings_tmp):
    ids = {s["id"] for s in surfaces.list_surfaces()}
    assert ids == {"cowork", "code", "duet", "fleet"}


def test_each_surface_has_agent_permission_and_tools(settings_tmp):
    for config in surfaces.list_surfaces():
        assert config["default_agent"]
        assert config["permission_mode"]
        assert isinstance(config["tools"], list) and config["tools"]


def test_update_persists_override(settings_tmp):
    updated = surfaces.update_surface("code", {
        "default_agent": "senior-engineer",
        "permission_mode": "acceptEdits",
        "notes": "review before commit",
    })
    assert updated["default_agent"] == "senior-engineer"
    assert updated["permission_mode"] == "acceptEdits"
    assert surfaces.get_surface("code")["notes"] == "review before commit"
    assert settings_store.load()["surfaces"]["code"]["default_agent"] == "senior-engineer"


def test_unknown_surface_and_bad_field(settings_tmp):
    with pytest.raises(KeyError):
        surfaces.update_surface("nope", {})
    updated = surfaces.update_surface("duet", {"unknown": "ignored", "tools": ["read_file"]})
    assert updated["tools"] == ["read_file"]


def test_ui_applies_surface_config():
    js = (ROOT / "site" / "ui" / "app.js").read_text(encoding="utf-8")
    assert "/api/surfaces" in js
    assert "function applySurfaceBadge" in js
    assert "function loadSurfaceConfig" in js
    html = (ROOT / "site" / "app.html").read_text(encoding="utf-8")
    assert 'class="surface-agent-badge"' in html


def test_app_js_syntax():
    result = subprocess.run(["node", "--check", str(ROOT / "site" / "ui" / "app.js")],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
