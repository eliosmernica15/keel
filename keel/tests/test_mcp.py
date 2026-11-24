"""MCP client tests — stdio transport with a fake JSON-RPC server."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

import keel
import keel.mcp as mcp
from keel.fakes import ScriptedModel, SeededRng, VirtualClock
from keel.mcp import (McpManager, McpServer, McpServerConfig, is_approved,
                      parse_servers, tool_name_for)
from keel.session import Session, SessionConfig

FAKE_SERVER = r"""
import json, sys

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake", "version": "1.0"}}})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [
            {"name": "echo", "description": "echo the input text",
             "inputSchema": {"type": "object",
                             "properties": {"text": {"type": "string"}},
                             "required": ["text"]}},
            {"name": "blob", "description": "return a big string",
             "inputSchema": {"type": "object", "properties": {}}}]}})
    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "echo":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "content": [{"type": "text", "text": str(args.get("text", ""))}],
                "isError": False}})
        elif name == "blob":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "content": [{"type": "text", "text": "x" * 300_000}],
                "isError": False}})
        else:
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {
                "code": -32601, "message": "unknown tool"}})
    elif method == "shutdown":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
"""


@pytest.fixture
def fake_server(tmp_path):
    script = tmp_path / "fake_mcp_server.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    return McpServerConfig(name="fake", command=sys.executable,
                           args=(str(script),))


def test_handshake_and_tools_list(fake_server):
    client = McpServer(fake_server)
    try:
        client.start()
        assert client.running
        names = [t["name"] for t in client.tools]
        assert names == ["echo", "blob"]
    finally:
        client.shutdown()
    assert not client.running


def test_stdio_client_info_uses_canonical_version(monkeypatch):
    captured: dict[str, dict] = {}
    client = McpServer(McpServerConfig(name="fake", command="unused"))

    def fake_request(method, params, *, notify=False):
        captured[method] = params
        return {"capabilities": {}, "tools": []} if method == "initialize" else {}

    class FakeProc:
        def poll(self):
            return 0

    monkeypatch.setattr(mcp.subprocess, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_notify", lambda *a, **k: None)
    client.start()
    assert captured["initialize"]["clientInfo"] == {
        "name": "keel", "version": keel.__version__}


def test_http_client_info_uses_canonical_version(monkeypatch):
    captured: dict[str, dict] = {}
    client = mcp.HttpMcpServer(McpServerConfig(
        name="fake", transport="http", url="http://example.invalid"))

    def fake_post(method, params, *, notify=False):
        captured[method] = params
        return {}

    monkeypatch.setattr(client, "_post", fake_post)
    client.start()
    assert captured["initialize"]["clientInfo"] == {
        "name": "keel", "version": keel.__version__}


def test_call_echo(fake_server):
    client = McpServer(fake_server)
    try:
        client.start()
        ok, text = client.call_tool("echo", {"text": "hello keel"})
        assert ok and text == "hello keel"
    finally:
        client.shutdown()


def test_call_unknown_tool_fails_cleanly(fake_server):
    client = McpServer(fake_server)
    try:
        client.start()
        ok, text = client.call_tool("nope", {})
        assert not ok and "unknown tool" in text
    finally:
        client.shutdown()


def test_output_cap_truncates(fake_server):
    client = McpServer(fake_server)
    try:
        client.start()
        ok, text = client.call_tool("blob", {})
        assert ok
        assert len(text) <= mcp.MCP_OUTPUT_CAP + 64
        assert "output truncated" in text
    finally:
        client.shutdown()


def test_tool_name_mapping_and_parse(fake_server):
    assert tool_name_for("srv", "echo") == "mcp__srv__echo"
    assert tool_name_for("s-v/x", "t.o.ol") == "mcp__s-v_x__t_o_ol"
    cfg = McpServerConfig(name="s", command="cmd")
    parts = tool_name_for("s", "a__b").split("__", 2)
    assert parts == ["mcp", "s", "a__b"]


def test_project_server_inert_until_approved(tmp_path, monkeypatch):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr(mcp, "approvals_path", lambda: approvals_file)
    cfg = McpServerConfig(name="proj", command=sys.executable,
                          args=("server.py",), scope="project")
    assert not is_approved(cfg)
    key = mcp.approve(cfg)
    assert is_approved(cfg)
    assert key == mcp.approval_key(cfg)
    assert mcp.revoke("proj")
    assert not is_approved(cfg)


def test_parse_servers_tolerance():
    raw = {
        "ok": {"command": "python", "args": ["s.py"]},
        "bad-not-dict": "nope",
        "bad-no-command": {"args": []},
        "bad-args": {"command": "x", "args": "notalist"},
    }
    parsed = parse_servers(raw)
    assert [s.name for s in parsed] == ["ok"]


def _cfg(tmp_path):
    return SessionConfig(cwd=str(tmp_path),
                         state_root=str(tmp_path / "state"),
                         bare=True, permission_mode="default",
                         session_id="66666666-6666-4666-8666-666666666666",
                         model="keel-fake-1", seed=0)


class _Executor:
    def invoke(self, name, tool_input):
        return "", {}


def test_session_manifest_and_mcp_call(tmp_path, fake_server):
    manager = McpManager([fake_server])
    model = ScriptedModel([
        [{"type": "tool_use", "name": "mcp__fake__echo",
          "input": {"text": "ping"}}],
        [{"type": "text", "text": "done"}],
    ])
    session = Session(model_client=model, executor=_Executor(),
                      config=_cfg(tmp_path),
                      clock=VirtualClock(), rng=SeededRng(0),
                      mcp=manager,
                      rules=((), (), ("mcp__fake__echo",)))
    try:
        out = session.run("ping via mcp")
    finally:
        manager.shutdown_all()
    init = out.events[0]
    assert init["subtype"] == "init"
    assert "mcp__fake__echo" in init["tools"]
    assert init["mcp_servers"][0]["status"] == "connected"
    tool_results = [blk for e in out.events if e["type"] == "user"
                    for blk in e["message"]["content"]
                    if blk["type"] == "tool_result"]
    assert tool_results[0]["content"] == "ping"


def test_mcp_tool_requires_permission(tmp_path, fake_server):
    manager = McpManager([fake_server])
    model = ScriptedModel([
        [{"type": "tool_use", "name": "mcp__fake__echo",
          "input": {"text": "ping"}}],
        [{"type": "text", "text": "done"}],
    ])
    session = Session(model_client=model, executor=_Executor(),
                      config=_cfg(tmp_path),
                      clock=VirtualClock(), rng=SeededRng(0),
                      mcp=manager, rules=((), (), ()))
    try:
        out = session.run("ping via mcp")
    finally:
        manager.shutdown_all()
    tool_results = [blk for e in out.events if e["type"] == "user"
                    for blk in e["message"]["content"]
                    if blk["type"] == "tool_result"]
    assert "permission denied" in tool_results[0]["content"]
