"""keel.fleet — F0 test suite.

Runs real HTTP requests against an ephemeral bridge server with a
temporary fleet.db. No mocks — a real end-to-end check of the Fleet
foundation: persistence, rows, SSE and the Echo turn loop.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes


@pytest.fixture
def bridge(tmp_path):
    db_path = tmp_path / "fleet.db"
    fleet_routes.reset_store_for_tests(db_path)
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _post(server, path, body, token=None):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        data=data,
        headers={"X-Keel-Token": token or webapp.token(),
                 "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _get(server, path, token=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        headers={"X-Keel-Token": token or webapp.token()},
        method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _wait_for(predicate, timeout=5.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _post_drain(server, path, body, token):
    # keep the door open: returns status+body, used for POST /messages (202/409)
    return _post(server, path, body, token)


def _row_kinds(server, bot_id):
    status, body = _get(server, f"/api/fleet/bots/{bot_id}/rows")
    return status, [r["kind"] for r in body.get("rows", [])]


def test_create_list_and_fetch_bot(bridge):
    status, body = _post(bridge, "/api/fleet/bots",
                         {"name": "Echo Prime", "role": "field tester",
                          "engine": "echo"})
    assert status == 201
    assert body["bot"]["name"] == "Echo Prime"
    assert body["bot"]["engine"] == "echo"
    assert body["bot"]["provider"] == "auto"

    status, listing = _get(bridge, "/api/fleet/bots")
    assert status == 200
    assert any(b["id"] == body["bot"]["id"] for b in listing["bots"])

    status, detail = _get(bridge, f"/api/fleet/bots/{body['bot']['id']}")
    assert status == 200
    assert detail["bot"]["role"] == "field tester"


def test_create_rejects_empty_name(bridge):
    status, body = _post(bridge, "/api/fleet/bots", {"name": "", "role": ""})
    assert status == 400


def test_bad_token_refused(bridge):
    status, _ = _get(bridge, "/api/fleet/bots", token="wrong")
    assert status == 403
    status, _ = _post(bridge, "/api/fleet/bots", {"name": "x"}, token="wrong")
    assert status == 403


def test_message_and_turn_complete(bridge):
    status, created = _post(bridge, "/api/fleet/bots",
                            {"name": "Echo", "engine": "echo"})
    bot_id = created["bot"]["id"]

    status, body = _post(bridge, f"/api/fleet/bots/{bot_id}/messages",
                         {"content": "hello there"})
    assert status in (202,)
    assert body["queued"] is True

    assert _wait_for(lambda: "turn_end" in _row_kinds(bridge, bot_id)[1])

    status, detail = _get(bridge, f"/api/fleet/bots/{bot_id}/rows")
    rows = {r["kind"]: r for r in detail["rows"]}
    assert any(r["kind"] == "message" and r["body"].get("content") == "hello there"
               for r in detail["rows"])
    assert any(r["kind"] == "message" and r["body"].get("role") == "assistant"
               for r in detail["rows"])
    assert rows["turn_end"]["body"]["num_steps"] == 3


def test_update_bot_fields(bridge):
    status, created = _post(bridge, "/api/fleet/bots",
                            {"name": "Harmony", "role": "old",
                             "engine": "echo"})
    bot_id = created["bot"]["id"]

    status, updated = _post(bridge, f"/api/fleet/bots/{bot_id}/update",
                            {"role": "new role", "notes": "prefers tea", "avatar_hue": 42})
    assert status == 200
    assert updated["bot"]["role"] == "new role"
    assert updated["bot"]["notes"] == "prefers tea"
    assert updated["bot"]["avatar_hue"] == 42


def test_delete_bot(bridge):
    status, created = _post(bridge, "/api/fleet/bots",
                            {"name": "Deleteme", "engine": "echo"})
    bot_id = created["bot"]["id"]
    status, body = _post(bridge, f"/api/fleet/bots/{bot_id}/delete", {})
    assert status == 200 and body["deleted"] is True
    status, body = _get(bridge, f"/api/fleet/bots/{bot_id}")
    assert status == 404


def test_persistence_across_restart(bridge, tmp_path):
    db_path = tmp_path / "fleet.db"
    status, created = _post(bridge, "/api/fleet/bots",
                            {"name": "Persistent", "engine": "echo"})
    bot_id = created["bot"]["id"]
    _post(bridge, f"/api/fleet/bots/{bot_id}/messages", {"content": "remember me"})
    assert _wait_for(lambda: "turn_end" in _row_kinds(bridge, bot_id)[1])
    before = _get(bridge, f"/api/fleet/bots/{bot_id}/rows")[1]["rows"]
    assert len(before) >= 6  # user + 3*2 steps + assistant + turn_end + notice

    # simulate a full server restart against the same fleet.db
    fresh = tmp_path / "fleet.db"
    from keel.fleet.service import FleetStore
    store = FleetStore(fresh)
    rows = store.list_rows(bot_id)
    assert len(rows) == len(before)
    members = [r for r in rows if r["kind"] == "message"]
    assert any("remember me" in str(r["body"]) for r in members)


def test_sse_stream_sees_rows(bridge):
    status, created = _post(bridge, "/api/fleet/bots",
                            {"name": "Streamy", "engine": "echo"})
    bot_id = created["bot"]["id"]

    sock = socket.create_connection(
        ("127.0.0.1", bridge.server_address[1]), timeout=10)
    req = (f"GET /api/fleet/events?t={webapp.token()} HTTP/1.1\r\n"
           f"Host: 127.0.0.1\r\nConnection: close\r\n\r\n").encode()
    sock.sendall(req)

    # post a message in parallel; read the event stream until we see it
    assert _post(bridge, f"/api/fleet/bots/{bot_id}/messages",
                 {"content": "ping"})[0] in (202,)
    buf = b""
    deadline = time.monotonic() + 10.0
    found = False
    while time.monotonic() < deadline and not found:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
        if b"event: row" in buf:
            found = True
    sock.close()
    assert found, "SSE stream never delivered a row event"
