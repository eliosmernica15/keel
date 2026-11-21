"""C11.5 — local EULA acceptance state and re-prompt."""

from __future__ import annotations

import json

import pytest

from keel import eula, settings_store


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


def test_first_run_needs_acceptance(settings_tmp):
    assert eula.needs_acceptance("1.0") is True
    assert eula.accepted_version() is None


def test_accept_and_reprompt_on_version_change(settings_tmp):
    eula.accept("1.0")
    assert eula.accepted_version() == "1.0"
    assert eula.needs_acceptance("1.0") is False
    assert eula.needs_acceptance("1.1") is True
    assert eula.accepted_version() is not None


def test_decline_clears_acceptance(settings_tmp):
    eula.accept("1.0")
    eula.decline()
    assert eula.needs_acceptance("1.0") is True
    assert eula.accepted_version() is None
