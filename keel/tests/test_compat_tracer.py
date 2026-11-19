"""v2 surface — HTTP contract tests (thin layer over the fleet runtime).

Deep acceptance coverage lives in test_compat_runtime.py; these tests pin
the wire contract: status codes, JSON shapes, and authn/authz.
"""

import json
import os

import pytest

TOKEN = os.environ.get("KEEL_TOKEN", "tracetoken12345")


def _http(server):
    return __import__("http.client", fromlist=["HTTPConnection"]).HTTPConnection(
        "127.0.0.1", server.server_address[1], timeout=20)


def _post(server, path, body, token=TOKEN):
    conn = _http(server)
    try:
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Keel-Token"] = token
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read().decode()
    finally:
        conn.close()


def _get(server, path, token=TOKEN):
    conn = _http(server)
    try:
        headers = {}
        if token is not None:
            headers["X-Keel-Token"] = token
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read().decode()
    finally:
        conn.close()


def _delete(server, path, token=TOKEN):
    conn = _http(server)
    try:
        headers = {}
        if token is not None:
            headers["X-Keel-Token"] = token
        conn.request("DELETE", path, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read().decode()
    finally:
        conn.close()


def _make_session(server):
    status, body = _post(server, "/api/v2/sessions", '{"title":"tracer"}')
    assert status == 201, body
    return json.loads(body)["id"]


def test_create_returns_201_and_fields(compat_store, compat_server):
    status, body = _post(compat_server, "/api/v2/sessions",
                         '{"title":"contract check"}')
    assert status == 201
    doc = json.loads(body)
    assert doc["id"]
    assert doc["title"] == "contract check"
    assert doc["engine"] == "provider"


def test_unauthorized(compat_store, compat_server):
    status, _ = _get(compat_server, "/api/v2/sessions", "bad")
    assert status == 403


def test_sessions_list_contains_created(compat_store, compat_server):
    sid = _make_session(compat_server)
    status, body = _get(compat_server, "/api/v2/sessions", TOKEN)
    assert status == 200
    doc = json.loads(body)
    assert any(s["id"] == sid for s in doc["sessions"])


def test_delete_session(compat_store, compat_server):
    sid = _make_session(compat_server)
    status, _ = _delete(compat_server, f"/api/v2/sessions/{sid}", TOKEN)
    assert status == 200
    status, _ = _get(compat_server, f"/api/v2/sessions/{sid}", TOKEN)
    assert status == 404


def test_unknown_session_endpoints_404(compat_store, compat_server):
    for method, path in (("GET", "/api/v2/sessions/nope"),
                         ("GET", "/api/v2/sessions/nope/messages"),
                         ("GET", "/api/v2/sessions/nope/events"),
                         ("POST", "/api/v2/sessions/nope/messages"),
                         ("POST", "/api/v2/sessions/nope/approve"),
                         ("POST", "/api/v2/sessions/nope/reject"),
                         ("POST", "/api/v2/sessions/nope/cancel")):
        if method == "GET":
            status, _ = _get(compat_server, path, TOKEN)
        else:
            status, _ = _post(compat_server, path, '{"text":"x"}', TOKEN)
        assert status == 404, (method, path, status)
