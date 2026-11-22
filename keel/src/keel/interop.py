"""Interop: config import/export, OpenAPI-to-tools, standards checklist (C7.x).

All conversions are local and produce dormant tool descriptors that require
explicit approval before any execution.
"""

from __future__ import annotations

import json
from pathlib import Path


def import_mcp_config(doc: dict) -> dict:
    """Normalise another app's MCP config into Keel's mcpServers shape."""
    servers = {}
    raw = doc.get("mcpServers", doc.get("mcp_servers", {}))
    if isinstance(raw, dict):
        for name, spec in raw.items():
            if not isinstance(spec, dict):
                continue
            servers[str(name)] = {
                "command": str(spec.get("command", "")),
                "args": [str(a) for a in (spec.get("args") or [])],
                "env": {str(k): str(v) for k, v in (spec.get("env") or {}).items()}
                if isinstance(spec.get("env"), dict) else {},
                "scope": "imported",
                "approved": False,
            }
    return servers


def export_config(doc: dict) -> dict:
    return {"mcpServers": doc.get("mcpServers", {}),
            "ui": doc.get("ui", {}), "format": "keel-config-v1"}


def openapi_to_tools(spec: dict) -> list[dict]:
    """Turn OpenAPI paths into dormant tool descriptors.

    Backward-compatible entry point; delegates to the real generator in
    :mod:`keel.openapi_tools` (full schemas, request builder, approval gating).
    """
    from .openapi_tools import generate_tools
    return generate_tools(spec)


STANDARDS = ["AGENTS.md", "MCP", "ACP", "LSP", "DAP", "OpenTelemetry",
             "SARIF", "CycloneDX", "SPDX", "OpenAPI", "JSON Schema", "ICS"]


def standards_checklist() -> dict:
    return {name: {"supported": name in ("AGENTS.md", "MCP", "OpenAPI",
                                          "JSON Schema", "SPDX")}
            for name in STANDARDS}
