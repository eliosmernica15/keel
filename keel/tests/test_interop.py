"""C7.2/C7.4/C7.5 — config import/export, OpenAPI tools, standards."""

from __future__ import annotations

from keel.interop import (export_config, import_mcp_config, openapi_to_tools,
                          standards_checklist)


def test_import_mcp_config_marks_dormant():
    result = import_mcp_config({"mcpServers": {
        "fs": {"command": "npx", "args": ["server-fs"], "env": {"X": "1"}}}})
    assert result["fs"]["approved"] is False
    assert result["fs"]["command"] == "npx"
    assert result["fs"]["env"] == {"X": "1"}


def test_export_config():
    out = export_config({"mcpServers": {"a": 1}, "ui": {"theme": "light"}})
    assert out["format"] == "keel-config-v1" and "a" in out["mcpServers"]


def test_openapi_to_tools_is_dormant():
    spec = {"paths": {"/items": {"get": {"operationId": "listItems",
                                           "summary": "List items"}}}}
    tools = openapi_to_tools(spec)
    assert tools[0]["name"] == "listItems"
    assert tools[0]["dormant"] is True and tools[0]["approved"] is False


def test_standards_checklist():
    checklist = standards_checklist()
    assert "MCP" in checklist and "OpenAPI" in checklist
    assert checklist["MCP"]["supported"] is True
