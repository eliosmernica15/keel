"""C6.4 — editable local user profile."""

from __future__ import annotations

import json

import pytest

from keel import settings_store, user_profile


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

    monkeypatch.setattr(settings_store, "load", _load)
    return path


def test_profile_update_and_read(settings_tmp):
    assert user_profile.get() == {}
    profile = user_profile.update({"name": "Ada", "role": "engineer",
                                   "secret": "ignored"})
    assert profile["name"] == "Ada" and "secret" not in profile
    assert user_profile.get()["role"] == "engineer"


def test_context_attachment(settings_tmp):
    text = user_profile.context_attachment({"name": "Ada"})
    assert "user-profile" in text and "Ada" in text
    assert user_profile.context_attachment({}) == ""
