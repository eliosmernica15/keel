"""C7.4 — real OpenAPI-to-tools generation with approval gating."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from keel.openapi_tools import (ToolRegistry, approve_tool, build_request,
                                generate_tools, resolve_ref)

ROOT = Path(__file__).resolve().parents[1]

SPEC = {
    "openapi": "3.0.0",
    "servers": [{"url": "https://api.example.test/v1"}],
    "paths": {
        "/items/{item_id}": {
            "parameters": [{"name": "item_id", "in": "path", "required": True,
                            "schema": {"type": "string"}}],
            "get": {
                "operationId": "getItem",
                "summary": "Get an item",
                "parameters": [{"name": "verbose", "in": "query",
                                "schema": {"type": "boolean"}}],
            },
            "put": {
                "operationId": "updateItem",
                "requestBody": {"required": True, "content": {
                    "application/json": {"schema": {
                        "type": "object", "properties": {"name": {"type": "string"}}}}}},
            },
        }
    },
}


def test_generate_tools_with_schemas():
    tools = generate_tools(SPEC)
    assert len(tools) == 2
    by_name = {t["name"]: t for t in tools}
    get = by_name["getItem"]
    assert get["dormant"] is True and get["approved"] is False
    assert set(get["input_schema"]["properties"]) == {"item_id", "verbose"}
    assert "item_id" in get["input_schema"]["required"]
    assert get["request"]["method"] == "get"
    assert get["request"]["placement"]["verbose"] == "query"
    put = by_name["updateItem"]
    assert put["request"]["placement"]["body"] == "body"
    assert "body" in put["input_schema"]["required"]


def test_resolve_ref():
    spec = {"components": {"schemas": {"X": {"type": "object"}}}}
    assert resolve_ref(spec, {"$ref": "#/components/schemas/X"}) == {
        "type": "object"}
    assert resolve_ref(spec, {"$ref": "#/missing"}) == {"$ref": "#/missing"}


def test_approval_gating_and_request_build():
    tool = generate_tools(SPEC)[0]
    try:
        build_request(tool, {"item_id": "42"})
    except ValueError as exc:
        assert "dormant" in str(exc) or "approved" in str(exc)
    else:
        raise AssertionError("built request from dormant tool")

    approve_tool(tool, approver="alice")
    assert tool["approved"] is True and tool["approver"] == "alice"
    req = build_request(tool, {"item_id": "42", "verbose": True})
    assert req["method"] == "get"
    assert req["url"] == "https://api.example.test/v1/items/42?verbose=True"
    assert "no network call" in req["note"]
    try:
        build_request(tool, {})  # missing required item_id
    except ValueError as exc:
        assert "missing required" in str(exc)
    else:
        raise AssertionError("missing required argument accepted")


def test_registry_roundtrip(tmp_path):
    store = ToolRegistry(tmp_path)
    tools = generate_tools(SPEC)
    store.save("api", tools)
    assert store.list() == ["api"]
    assert store.load("api")[0]["name"] in ("getItem", "updateItem")


def test_interop_backward_compat():
    from keel.interop import openapi_to_tools
    tools = openapi_to_tools(SPEC)
    assert tools[0]["dormant"] is True and tools[0]["approved"] is False


def test_capability_integration(tmp_path):
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    state = str(tmp_path / "state")
    gen = invoke("code.openapi.generate",
                 {"name": "api", "spec": SPEC, "state_root": state},
                 context={})["result"]
    assert gen["dormant"] is True and gen["count"] == 2
    apr = invoke("code.openapi.approve",
                 {"name": "api", "tool": "getItem", "state_root": state},
                 context={})["result"]
    assert apr["approved"] is True
    req = invoke("code.openapi.request",
                 {"name": "api", "tool": "getItem",
                  "arguments": {"item_id": "7"}, "state_root": state},
                 context={})["result"]
    assert req["url"].endswith("/items/7")


def test_cli_openapi(tmp_path):
    state = tmp_path / "state"
    env = {**os.environ, "KEEL_STATE_DIR": str(state)}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(SPEC), encoding="utf-8")
    build = subprocess.run(
        [sys.executable, "-m", "keel", "openapi", "generate", "api",
         str(spec_path)], cwd=ROOT, capture_output=True, text=True,
        timeout=60, env=env)
    assert build.returncode == 0, build.stderr
    approve = subprocess.run(
        [sys.executable, "-m", "keel", "openapi", "approve", "api", "getItem"],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert approve.returncode == 0, approve.stderr
    args_path = tmp_path / "args.json"
    args_path.write_text('{"item_id": "9"}', encoding="utf-8")
    request = subprocess.run(
        [sys.executable, "-m", "keel", "openapi", "request", "api", "getItem",
         str(args_path)], cwd=ROOT, capture_output=True, text=True,
        timeout=60, env=env)
    assert request.returncode == 0, request.stderr
    assert "/items/9" in json.loads(request.stdout)["url"]
