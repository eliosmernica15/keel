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
