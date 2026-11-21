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
    """Turn OpenAPI paths into dormant tool descriptors."""
    tools = []
    for path, methods in (spec.get("paths", {}) or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            if not isinstance(operation, dict):
                continue
            op_id = operation.get("operationId") or f"{method}_{path.strip('/')}"
            tools.append({
                "name": str(op_id)[:64],
                "description": str(operation.get("summary", ""))[:200],
                "input_schema": {"type": "object", "properties": {}},
                "method": method.lower(), "path": path,
                "dormant": True, "approved": False,
            })
    return tools


STANDARDS = ["AGENTS.md", "MCP", "ACP", "LSP", "DAP", "OpenTelemetry",
             "SARIF", "CycloneDX", "SPDX", "OpenAPI", "JSON Schema", "ICS"]


def standards_checklist() -> dict:
    return {name: {"supported": name in ("AGENTS.md", "MCP", "OpenAPI",
                                          "JSON Schema", "SPDX")}
            for name in STANDARDS}
