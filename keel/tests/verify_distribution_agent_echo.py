"""Distribution round — real local Echo turn through the live bridge.

This is *real local runtime execution*, not a fixture-shaped stand-in:

* a real ``keel.webapp`` HTTP server on 127.0.0.1;
* real HTTP POST/GET requests with a throwaway bridge token;
* a real ``FleetStore`` writing SQLite rows on a tmp_path DB;
* a real worker thread running ``fleet.echo.start_turn``;
* a real SSE subscriber reading ``event: row`` frames off the wire.

Only the environment is isolated (temp DB, local token). No provider key, no
external network and no user data is used. The reply is deliberately the
labelled scripted Echo engine — it is the zero-credential turn path, and the
point of this test is the bridge/rows/events/cancel/persistence plumbing.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.fleet import turn_core

TOKEN = webapp.token()


@pytest.fixture()
def live(tmp_path):
    """A restartable bridge bound to one temporary fleet DB."""
    old = fleet_routes._store
    db_path = tmp_path / "echo-fleet.db"
    fleet_routes.reset_store_for_tests(db_path)
    state = {"server": None, "thread": None}

    def start():
        server = webapp.make_server(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        state["server"] = server
        state["thread"] = thread
        return server

    def stop():
        server = state["server"]
        if server is not None:
            server.shutdown()
            server.server_close()
            state["thread"].join(timeout=5)
            state["server"] = None

    def reopen_store():
        """Simulate the daemon restarting against the same DB file."""
        fleet_routes.reset_store_for_tests(db_path)

    start()
    yield db_path, state, start, stop, reopen_store
    stop()
    fleet_routes._store = old


def _post(server, path, body, token=TOKEN):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"X-Keel-Token": token, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _get(server, path, token=TOKEN):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        headers={"X-Keel-Token": token}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _wait_for(predicate, timeout=8.0, interval=0.04):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _open_sse(server):
    sock = socket.create_connection(("127.0.0.1", server.server_address[1]),
                                    timeout=12)
    sock.settimeout(0.6)
    req = (f"GET /api/fleet/events?t={TOKEN} HTTP/1.1\r\n"
           f"Host: 127.0.0.1:{server.server_address[1]}\r\n"
           f"Connection: close\r\n\r\n").encode()
    sock.sendall(req)
    buf = b""
    deadline = time.monotonic() + 6
    while b"\r\n\r\n" not in buf and time.monotonic() < deadline:
        buf += sock.recv(4096)
    assert b"text/event-stream" in buf, "SSE endpoint did not send an event stream"
    # subscribe() happens just after the header flush; give it a beat.
    time.sleep(0.1)
    return sock


def _sse_rows(sock, bot_id, want_kinds, timeout=12.0):
    """Read SSE frames until every wanted row kind is seen for bot_id.

    Returns ``{kind: [row, ...]}`` — a bot emits two ``message`` rows (user
    then assistant), so a single-value map would hide the assistant reply.
    """
    seen: dict[str, list[dict]] = {}
    buf = b""
    sock.settimeout(0.4)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not set(want_kinds) <= seen.keys():
        try:
            chunk = sock.recv(8192)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n\n" in buf:
            frame, buf = buf.split(b"\n\n", 1)
            for line in frame.split(b"\n"):
                if not line.startswith(b"data: "):
                    continue
                try:
                    row = json.loads(line[6:].decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if row.get("bot_id") != bot_id:
                    continue
                kind = row.get("kind")
                if kind in want_kinds:
                    seen.setdefault(kind, []).append(row)
    return seen


def test_real_local_echo_turn_rows_events_cancel_and_persistence(live):
    db_path, state, start, stop, reopen_store = live
    server = state["server"]

    # 1. Bot create goes through the real HTTP route and writes a notice row.
    status, created = _post(server, "/api/fleet/bots",
                            {"name": "Distro Echo", "engine": "echo"})
    assert status == 201, created
    bot_id = created["bot"]["id"]

    # 2. Subscribe to the SSE stream before the turn so events are observed live.
    sock = _open_sse(server)
    try:
        status, queued = _post(server, f"/api/fleet/bots/{bot_id}/messages",
                               {"content": "distribution smoke"})
        assert status == 202 and queued["queued"] is True, queued

        seen = _sse_rows(sock, bot_id, {"step", "message", "turn_end"})
        assert "step" in seen, "no step row delivered over SSE"
        assistant_events = [r for r in seen.get("message", [])
                            if r["body"].get("role") == "assistant"]
        assert assistant_events, "no assistant message delivered over SSE"
        assert assistant_events[0]["body"]["engine"] == "echo"
        assert seen["turn_end"][0]["body"]["num_steps"] == 3
    finally:
        sock.close()

    # 3. Persisted rows: user + 6 step rows + assistant + turn_end + create notice.
    def rows_ready():
        _, doc = _get(server, f"/api/fleet/bots/{bot_id}/rows")
        return any(r["kind"] == "turn_end" for r in doc.get("rows", []))

    assert _wait_for(rows_ready), "turn never completed"
    status, doc = _get(server, f"/api/fleet/bots/{bot_id}/rows")
    assert status == 200
    rows = doc["rows"]
    kinds = [r["kind"] for r in rows]
    assert any(r["kind"] == "message" and r["body"].get("content") == "distribution smoke"
               for r in rows)
    assistants = [r for r in rows if r["kind"] == "message"
                  and r["body"].get("role") == "assistant"]
    assert len(assistants) == 1
    assert assistants[0]["body"]["engine"] == "echo"
    assert "Echo heard you say" in assistants[0]["body"]["content"]
    assert kinds.count("step") == 6
    assert kinds.count("turn_end") == 1
    assert next(r for r in rows if r["kind"] == "turn_end")["body"]["num_steps"] == 3

    # Incremental history cursor survives a "page reload" of the same session.
    seq = rows[0]["seq"]
    status, tail = _get(server, f"/api/fleet/bots/{bot_id}/rows?after={seq}")
    assert status == 200 and all(r["seq"] > seq for r in tail["rows"])
    assert any(r["kind"] == "turn_end" for r in tail["rows"])

    # 4. Cancel endpoint: token-gated, and signals a registered real turn.
    status, body = _post(server, f"/api/fleet/bots/{bot_id}/cancel", {})
    assert status == 200 and body["cancelled"] is False  # echo turn already finished
    status, _ = _post(server, f"/api/fleet/bots/{bot_id}/cancel", {}, token="wrong")
    assert status == 403
    ev = turn_core._register_active_turn(bot_id)
    try:
        status, body = _post(server, f"/api/fleet/bots/{bot_id}/cancel", {})
        assert status == 200 and body["cancelled"] is True
        assert ev.is_set(), "Stop did not signal the active-turn event"
    finally:
        turn_core._unregister_active_turn(bot_id, ev)

    # 5. Restart continuity: new server process state, same SQLite file.
    stop()
    reopen_store()
    restarted = start()
    status, after = _get(restarted, f"/api/fleet/bots/{bot_id}/rows")
    assert status == 200
    assert [r["seq"] for r in after["rows"]] == [r["seq"] for r in rows]
    status, latest = _get(restarted, f"/api/fleet/bots/{bot_id}/latest_seq")
    assert status == 200 and latest["seq"] == rows[-1]["seq"]
    status, bot_doc = _get(restarted, f"/api/fleet/bots/{bot_id}")
    assert status == 200 and bot_doc["bot"]["engine"] == "echo"

    stop()
    # A second message after restart must append (not reset) the same session.
    final_server = start()
    status, queued2 = _post(final_server, f"/api/fleet/bots/{bot_id}/messages",
                            {"content": "still here after restart"})
    assert status == 202 and queued2["queued"] is True
    assert _wait_for(lambda: _get(final_server, f"/api/fleet/bots/{bot_id}/rows")[1]
                     ["rows"][-1]["kind"] == "turn_end")
    _, final_rows = _get(final_server, f"/api/fleet/bots/{bot_id}/rows")
    assert len(final_rows["rows"]) > len(after["rows"])
    assert any(r["kind"] == "message" and
               r["body"].get("content") == "still here after restart"
               for r in final_rows["rows"])

    assert db_path.is_file(), "the session DB was not persisted"
