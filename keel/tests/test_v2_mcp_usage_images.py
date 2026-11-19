"""v2 milestone-5 tests: MCP on the agent path, usage accounting, images.

Every test exercises the real HTTP bridge → compat shim → fleet provider
turn → Session → MCP client. Only the network edge is faked, plus the MCP
server (a deterministic Python stdio JSON-RPC script).
"""

import http.client
import json
import os
import sys
import threading
import time
import time

import pytest

TOKEN = os.environ.get("KEEL_TOKEN", "tracetoken12345")

FAKE_MCP_SERVER = r"""
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
                             "required": ["text"]}}]}})
    elif method == "tools/call":
        params = msg.get("params", {})
        args = params.get("arguments", {})
        if params.get("name") == "echo":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "content": [{"type": "text", "text": str(args.get("text", ""))}],
                "isError": False}})
        else:
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {
                "code": -32601, "message": "unknown tool"}})
    elif method == "shutdown":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
"""


def _post(server, path, body, token=TOKEN):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1],
                                      timeout=30)
    try:
        headers = {"Content-Type": "application/json", "X-Keel-Token": token}
        conn.request("POST", path, body=json.dumps(body), headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read().decode()
    finally:
        conn.close()


def _get(server, path, token=TOKEN):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1],
                                      timeout=30)
    try:
        conn.request("GET", path, headers={"X-Keel-Token": token})
        resp = conn.getresponse()
        return resp.status, resp.read().decode()
    finally:
        conn.close()


def _make_session(server):
    status, body = _post(server, "/api/v2/sessions", {"title": "m5-test"})
    assert status == 201, body
    return json.loads(body)["id"]


def _wait_for_row(store, sid, kind, predicate=None, timeout=15.0):
    import compat_fakes as C
    return C.wait_for(
        lambda: next(
            (r for r in store.list_rows(sid, 0, 10_000)
             if r["kind"] == kind
             and (predicate is None or predicate(r["body"]))),
            None),
        timeout=timeout)


@pytest.fixture()
def fake_mcp_server(tmp_path, monkeypatch):
    script = tmp_path / "fake_mcp_server.py"
    script.write_text(FAKE_MCP_SERVER, encoding="utf-8")
    import keel.fleet.turn_core as turn_core
    monkeypatch.setattr(turn_core.settings_store, "load", lambda: {
        "mcpServers": {"fake": {"command": sys.executable,
                                "args": [str(script)]}},
    })
    return script


def test_mcp_tool_offered_and_executable(compat_store, fake_mcp_server,
                                         compat_server, monkeypatch):
    import compat_fakes as C
    C.make_fake_adapter(monkeypatch, [
        C.tool_call_turn("mcp__fake__echo", {"text": "hello-from-mcp"}),
        C.text_turn("done"),
    ])

    sid = _make_session(compat_server)
    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                         {"text": "echo through mcp"})
    assert status == 202, body

    approval = _wait_for_row(
        compat_store, sid, "approval",
        predicate=lambda b: b.get("status") == "pending")
    assert approval is not None, "MCP tool never asked for approval"
    assert approval["body"]["tool_name"] == "mcp__fake__echo"
    assert "fake" in (approval["body"].get("explanation") or "")

    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/approve", {})
    assert status == 200, body

    done = _wait_for_row(compat_store, sid, "turn_end")
    assert done

    steps = [r for r in compat_store.list_rows(sid, 0, 10_000)
             if r["kind"] == "step" and r["body"].get("name") == "mcp__fake__echo"]
    assert any(s["body"].get("status") == "done" for s in steps), steps
    assistant = [r for r in compat_store.list_rows(sid, 0, 10_000)
                 if r["kind"] == "message" and r["body"].get("role") == "assistant"]
    assert assistant and assistant[-1]["body"]["content"] == "done"


def test_mcp_failing_server_isolated(tmp_path, monkeypatch, compat_store,
                                     compat_server):
    import compat_fakes as C
    import keel.fleet.turn_core as turn_core

    broken = tmp_path / "broken.py"
    broken.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    monkeypatch.setattr(turn_core.settings_store, "load", lambda: {
        "mcpServers": {"broken": {"command": sys.executable,
                                  "args": [str(broken)]}},
    })
    C.make_fake_adapter(monkeypatch, [C.text_turn("still here")])

    sid = _make_session(compat_server)
    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                         {"text": "hello"})
    assert status == 202
    assert _wait_for_row(compat_store, sid, "turn_end")
    rows = compat_store.list_rows(sid, 0, 10_000)
    notices = [r["body"].get("text", "") for r in rows if r["kind"] == "notice"]
    assert any("broken" in n for n in notices), notices


def test_usage_persisted_and_survives_restart(compat_store, compat_server,
                                              monkeypatch):
    import compat_fakes as C
    C.make_fake_adapter(monkeypatch, [C.text_turn("persistent-usage",
                                                  usage=(11, 7))])

    sid = _make_session(compat_server)
    status, _ = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                      {"text": "hi"})
    assert status == 202
    assert _wait_for_row(compat_store, sid, "turn_end")

    status, body = _get(compat_server, f"/api/v2/sessions/{sid}")
    assert status == 200
    usage = json.loads(body)["session"]["usage"]
    assert usage["input_tokens"] >= 11
    assert usage["output_tokens"] >= 7
    assert usage["records"] == 1
    assert usage["cost_basis"] != ""

    # restart: brand-new store on the same file
    from keel.fleet.service import FleetStore
    fresh = FleetStore(compat_store._test_db_path)
    try:
        totals = fresh.usage_totals(sid)
    finally:
        fresh.close()
    assert totals["input_tokens"] >= 11
    assert totals["output_tokens"] >= 7

    # usage row appears in the event replay — read the stream incrementally
    conn = http.client.HTTPConnection("127.0.0.1", compat_server.server_address[1],
                                      timeout=10)
    body = b""
    try:
        conn.request("GET", f"/api/v2/sessions/{sid}/events?since=0",
                     headers={"X-Keel-Token": TOKEN})
        resp = conn.getresponse()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            line = resp.fp.readline()
            if not line:
                break
            body += line
            if b'"usage"' in body:
                break
    finally:
        conn.close()
    assert b'"usage"' in body, f"no usage event in replay: {body[:200]!r}"


def test_message_with_image_reaches_provider(compat_store, compat_server,
                                             monkeypatch, tmp_path):
    import compat_fakes as C
    import keel.providers.openai_compatible as oc
    import keel.providers.registry as registry

    captured = []

    class _RecordingTransport:
        def __call__(self, request):
            captured.append(request)
            body = compat_fakes.openai_sse(
                compat_fakes.text_turn("image received"))
            return 200, {}, iter([body])

    def fake_build_adapter(name, *, api_key=None, transport=None):
        return oc.OpenAICompatibleAdapter(
            registry._PROVIDERS["openrouter"],
            api_key="fake-key-not-real",
            transport=_RecordingTransport())

    monkeypatch.setattr(registry, "build_adapter", fake_build_adapter)
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "fake-key-not-real")

    sid = _make_session(compat_server)
    img_b64 = "aGVsbG8taW1hZ2U="  # "hello-image"
    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                         {"text": "what is in this picture",
                          "images": [{"mime": "image/png",
                                      "data": img_b64,
                                      "name": "pic.png"}]})
    assert status == 202, body
    assert _wait_for_row(compat_store, sid, "turn_end")

    assert captured, "provider was never called"
    sent = json.loads(json.dumps(captured[0]["body_json"]))
    parts = sent["messages"][-1]["content"]
    image_parts = [p for p in parts if p.get("type") == "image_url"]
    assert image_parts, f"no image_url part in {sent}"
    assert image_parts[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_message_bad_image_mime_400(compat_store, compat_server):
    sid = _make_session(compat_server)
    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                         {"text": "x",
                          "images": [{"mime": "image/tiff",
                                      "data": "AAAA",
                                      "name": "x.tiff"}]})
    assert status == 400


def test_message_bad_base64_400(compat_store, compat_server):
    sid = _make_session(compat_server)
    status, body = _post(compat_server, f"/api/v2/sessions/{sid}/messages",
                         {"text": "x",
                          "images": [{"mime": "image/png",
                                      "data": "!!!not-base64!!!",
                                      "name": "x.png"}]})
    assert status == 400
