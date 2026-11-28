"""Regression tests for connector settings read/write safety.

Corrupt settings must never be silently replaced: a subsequent write would
destroy user configuration. See ``keel/src/keel/fleet/connector_ops.py``.
"""

from __future__ import annotations

import json

import pytest

from keel.fleet import connector_ops


def _state(tmp_path):
    return tmp_path / "settings.json"


def test_missing_settings_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(connector_ops, "state_root", lambda: tmp_path)
    assert connector_ops.load_settings() == {}


@pytest.mark.parametrize("raw", ["{not json", '["list", "root"]', "null"])
def test_corrupt_settings_refuse_to_load(tmp_path, monkeypatch, raw):
    monkeypatch.setattr(connector_ops, "state_root", lambda: tmp_path)
    _state(tmp_path).write_text(raw, encoding="utf-8")
    with pytest.raises(connector_ops.ConnectorSettingsError):
        connector_ops.load_settings()
    # The original bytes are untouched — no implicit overwrite.
    assert _state(tmp_path).read_text(encoding="utf-8") == raw


@pytest.mark.parametrize("raw", ['{"mcpServers": []}', '{"mcpServers": "bad"}'])
def test_invalid_mcpservers_refuse_to_overwrite(tmp_path, monkeypatch, raw):
    monkeypatch.setattr(connector_ops, "state_root", lambda: tmp_path)
    _state(tmp_path).write_text(raw, encoding="utf-8")
    with pytest.raises(connector_ops.ConnectorSettingsError):
        connector_ops.add_connector("x", "cmd", [], {})
    assert _state(tmp_path).read_text(encoding="utf-8") == raw


def test_atomic_write_leaves_no_temp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(connector_ops, "state_root", lambda: tmp_path)
    connector_ops.atomic_dump({"mcpServers": {"a": {"command": "cmd"}}})
    persisted = json.loads(_state(tmp_path).read_text(encoding="utf-8"))
    assert persisted["mcpServers"]["a"]["command"] == "cmd"
    assert list(tmp_path.glob(".settings.json.*.tmp")) == []
