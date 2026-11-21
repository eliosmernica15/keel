"""A4.3 — MCP presets catalog limited to free/self-hosted servers."""

from __future__ import annotations

import pytest

from keel.fleet import connector_ops


def test_presets_are_free_self_hosted():
    catalog = connector_ops.list_configured()
    presets = catalog["presets"]
    names = {p["name"] for p in presets}
    assert {"filesystem", "memory", "github", "sequential-thinking"} <= names
    for preset in presets:
        assert preset.get("label")
        assert "npx" in preset.get("command", "") or "cmd" in preset.get("command", "")


def test_preset_spec_works_for_local_servers():
    filesystem = connector_ops.preset_spec("filesystem", ["/tmp"], {})
    assert filesystem
    memory = connector_ops.preset_spec("memory", [], {})
    assert memory
    with pytest.raises(ValueError, match="unknown preset"):
        connector_ops.preset_spec("not-real", [], {})
