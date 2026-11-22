"""C7.4 — OpenAPI-to-tools generator with explicit approval gating.

Reads an OpenAPI 3 document and emits concrete tool descriptors: JSON Schema
input schemas from path/query/header parameters and request bodies, plus a
request builder that renders method, URL, query, headers and body from supplied
arguments. Generated tools are always ``dormant`` and ``approved=False``; a
named approver must explicitly approve one before it can be used. This module
only *builds* request descriptors — it never performs network calls.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def resolve_ref(spec: dict, node: object, *, depth: int = 0) -> object:
    """Resolve local ``$ref`` pointers against the spec's components."""
    if depth > 8 or not isinstance(node, dict) or "$ref" not in node:
        return node
    ref = str(node["$ref"])
    if not ref.startswith("#/"):
        return node
    target: object = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or part not in target:
            return node
        target = target[part]
    return resolve_ref(spec, target, depth=depth + 1)


def _schema(spec: dict, raw: object) -> dict:
    node = resolve_ref(spec, raw)
    if not isinstance(node, dict):
        return {"type": "string"}
    allowed = ("type", "format", "description", "enum", "default", "items",
               "properties", "required", "minimum", "maximum", "pattern")
    return {k: v for k, v in node.items() if k in allowed}


def generate_tools(spec: dict) -> list[dict]:
    """Turn an OpenAPI document into dormant, approval-gated tool descriptors."""
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")
    servers = spec.get("servers") or []
    base_url = str(servers[0].get("url", "")) if servers and isinstance(
        servers[0], dict) else ""
    tools: list[dict] = []
    for path, methods in (spec.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        path_params = methods.get("parameters") or []
        for method, operation in methods.items():
            if method.lower() not in METHODS or not isinstance(operation, dict):
                continue
            name = str(operation.get("operationId")
                       or f"{method}_{str(path).strip('/')}".replace("/", "_"))
            name = re.sub(r"[^A-Za-z0-9_]", "_", name)[:64] or "tool"
            properties: dict[str, dict] = {}
            required: list[str] = []
            placement: dict[str, str] = {}
            for raw in list(path_params) + list(operation.get("parameters") or []):
                param = resolve_ref(spec, raw)
                if not isinstance(param, dict) or "name" not in param:
                    continue
                pname = str(param["name"])
                properties[pname] = _schema(spec, param.get("schema"))
                placement[pname] = str(param.get("in", "query"))
                if param.get("required"):
                    required.append(pname)
            body = resolve_ref(spec, operation.get("requestBody"))
            if isinstance(body, dict):
                content = body.get("content") or {}
                media = next(iter(content), "application/json")
                body_schema = _schema(spec, (content.get(media) or {}).get("schema"))
                properties["body"] = body_schema
                placement["body"] = "body"
                if body.get("required"):
                    required.append("body")
            content_type = None
            if isinstance(body, dict):
                content_type = next(iter(body.get("content") or {}),
                                    "application/json")
            tools.append({
                "name": name,
                "description": str(operation.get("summary")
                                   or operation.get("description", ""))[:300],
                "input_schema": {"type": "object", "properties": properties,
                                 "required": required},
                "request": {
                    "method": method.lower(), "path": str(path),
                    "base_url": base_url, "placement": placement,
                    "content_type": content_type,
                },
                "dormant": True, "approved": False, "approver": None,
                "approved_at": None,
            })
    return tools


def approve_tool(tool: dict, *, approver: str = "owner",
                 note: str = "") -> dict:
    """Explicitly approve a generated tool; records who approved it."""
    import time
    tool["approved"] = True
    tool["dormant"] = False
    tool["approver"] = str(approver)
    tool["approval_note"] = str(note)
    tool["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return tool


def build_request(tool: dict, arguments: dict) -> dict:
    """Render a tool + arguments into a concrete request descriptor.

    Refuses to build for dormant/unapproved tools and enforces required
    arguments. No network call is made.
    """
    if tool.get("dormant") or not tool.get("approved"):
        raise ValueError("tool is dormant or not approved")
    schema = tool.get("input_schema", {})
    missing = [k for k in schema.get("required", [])
               if k not in (arguments or {})]
    if missing:
        raise ValueError(f"missing required arguments: {missing}")
    req = tool.get("request", {})
    path = str(req.get("path", ""))
    for key, value in (arguments or {}).items():
        if req.get("placement", {}).get(key) == "path":
            path = path.replace("{" + key + "}", str(value))
    query = {k: v for k, v in (arguments or {}).items()
             if req.get("placement", {}).get(k) == "query"}
    headers = {k: v for k, v in (arguments or {}).items()
               if req.get("placement", {}).get(k) == "header"}
    body = next((v for k, v in (arguments or {}).items()
                 if req.get("placement", {}).get(k) == "body"), None)
    base = str(req.get("base_url", "")).rstrip("/")
    url = base + path
    if query:
        from urllib.parse import urlencode
        url += "?" + urlencode(query)
    return {
        "method": req.get("method", "get"), "url": url,
        "path": path, "query": query, "headers": headers,
        "body": body, "content_type": req.get("content_type"),
        "tool": tool.get("name"),
        "note": "request descriptor only — no network call was made",
    }


class ToolRegistry:
    """Persist generated tools (and their approval state) locally."""

    def __init__(self, state_root: str | Path):
        self.root = Path(state_root) / "openapi-tools"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
            raise ValueError("invalid tool set name")
        return self.root / f"{name}.json"

    def save(self, name: str, tools: list[dict]) -> Path:
        path = self._path(name)
        path.write_text(json.dumps({"name": name, "tools": tools}, indent=2)
                        + "\n", encoding="utf-8")
        return path

    def load(self, name: str) -> list[dict]:
        path = self._path(name)
        if not path.is_file():
            raise KeyError(name)
        return json.loads(path.read_text(encoding="utf-8"))["tools"]

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))
