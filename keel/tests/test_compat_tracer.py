import http.client
import os
import sys

import pytest

os.environ.setdefault("PYTHONPATH", "src")

os.environ["KEEL_TOKEN"] = "tracetoken12345"

import keel.webapp as webapp  # noqa: E402

TOKEN = os.environ["KEEL_TOKEN"]


@pytest.fixture()
def server():
    srv = webapp.make_server(0)
    import threading
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    t.join(timeout=5)


def _post(server, path, body, token=None):
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    headers = {"Content-Type": "application/json", "X-Keel-Token": token}
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    return resp.status, resp.read().decode()


def _get(server, path, token=None):
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    headers = {"X-Keel-Token": token}
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    return resp.status, resp.read().decode()


def test_v2_session_roundtrip(server):
    status, body = _post(server, "/api/v2/sessions", '{"title":"tracer"}', TOKEN)
    assert status == 201, body
    sid = body and __import__("json").loads(body)["id"]
    assert sid

    status, body = _post(server, f"/api/v2/sessions/{sid}/messages", '{"text":"hi"}', TOKEN)
    assert status == 202, body

    status, body = _get(server, f"/api/v2/sessions/{sid}", TOKEN)
    assert status == 200
    doc = __import__("json").loads(body)
    assert doc["session"]["id"] == sid


def test_v2_unauthorized(server):
    status, _ = _get(server, "/api/v2/sessions", "bad")
    assert status == 403


def _delete(server, path, token=None):
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    headers = {"X-Keel-Token": token}
    conn.request("DELETE", path, headers=headers)
    resp = conn.getresponse()
    return resp.status, resp.read().decode()


def _make_session(server):
    status, body = _post(server, "/api/v2/sessions", '{"title":"t"}', TOKEN)
    assert status == 201, body
    return __import__("json").loads(body)["id"]


def test_v2_sessions_list(server):
    sid = _make_session(server)
    status, body = _get(server, "/api/v2/sessions", TOKEN)
    assert status == 200
    doc = __import__("json").loads(body)
    assert any(s["id"] == sid for s in doc["sessions"])


def test_v2_message_roundtrip_history(server):
    sid = _make_session(server)
    status, _ = _post(server, f"/api/v2/sessions/{sid}/messages",
                      '{"text":"hello"}', TOKEN)
    assert status == 202
    status, body = _get(server, f"/api/v2/sessions/{sid}/messages", TOKEN)
    assert status == 200
    doc = __import__("json").loads(body)
    roles = [m["role"] for m in doc["messages"]]
    assert roles == ["user", "assistant"]


def test_v2_session_get_includes_messages(server):
    sid = _make_session(server)
    _post(server, f"/api/v2/sessions/{sid}/messages", '{"text":"hi"}', TOKEN)
    status, body = _get(server, f"/api/v2/sessions/{sid}", TOKEN)
    assert status == 200
    doc = __import__("json").loads(body)
    assert doc["session"]["id"] == sid
    assert [m["role"] for m in doc["messages"]] == ["user", "assistant"]


def test_v2_delete_session(server):
    sid = _make_session(server)
    status, _ = _delete(server, f"/api/v2/sessions/{sid}", TOKEN)
    assert status == 200
    status, _ = _get(server, f"/api/v2/sessions/{sid}", TOKEN)
    assert status == 404
    status, _ = _delete(server, f"/api/v2/sessions/{sid}", TOKEN)
    assert status == 404


def test_v2_unknown_session_endpoints(server):
    for method, path in (("GET", "/api/v2/sessions/nope"),
                         ("GET", "/api/v2/sessions/nope/messages"),
                         ("GET", "/api/v2/sessions/nope/events"),
                         ("POST", "/api/v2/sessions/nope/messages"),
                         ("POST", "/api/v2/sessions/nope/approve"),
                         ("POST", "/api/v2/sessions/nope/reject")):
        if method == "GET":
            status, _ = _get(server, path, TOKEN)
        else:
            status, _ = _post(server, path, '{"text":"x"}', TOKEN)
        assert status == 404, (method, path, status)


def test_v2_events_since_filter(server):
    sid = _make_session(server)
    _post(server, f"/api/v2/sessions/{sid}/messages", '{"text":"hi"}', TOKEN)
    status, body = _get(server, f"/api/v2/sessions/{sid}/events", TOKEN)
    assert status == 200
    assert "data:" in body
    status, body = _get(server, f"/api/v2/sessions/{sid}/events?since=99999999999", TOKEN)
    assert status == 200
    assert "data:" not in body
