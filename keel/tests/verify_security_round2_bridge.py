"""Round-2 release-gate verification: local bridge auth, Origin and mirror.

Exercises the real Handler helpers, a live loopback server and the Next.js BFF
source. Also asserts the public mirror never calls desktop-only fleet APIs.
"""

from __future__ import annotations

import http.client
import json
from pathlib import Path

import pytest

from keel import webapp

ROOT = Path(__file__).resolve().parents[1]


class _HeaderMap:
    def __init__(self, items=None):
        self._d = {str(k).lower(): v for k, v in (items or {}).items()}

    def get(self, name, default=None):
        return self._d.get(str(name).lower(), default)


class _Handler:
    def __init__(self, headers=None, path=""):
        self.headers = _HeaderMap(headers)
        self.path = path

    def path_token(self):
        if "?t=" in self.path:
            return self.path.split("?t=", 1)[1].split("&", 1)[0]
        if "&t=" in self.path:
            return self.path.split("&t=", 1)[1].split("&", 1)[0]
        return None


@pytest.fixture()
def handler_class():
    server = webapp.make_server(0)
    cls = server.RequestHandlerClass
    server.server_close()
    return cls


def test_bridge_binds_loopback_only():
    server = webapp.make_server(0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_origin_check(handler_class):
    ok = handler_class._origin_ok(_Handler({"Host": "127.0.0.1:8739",
                                            "Origin": "http://127.0.0.1:8739"}))
    assert ok is True
    bad = handler_class._origin_ok(_Handler({"Host": "127.0.0.1:8739",
                                             "Origin": "https://evil.example"}))
    assert bad is False
    absent = handler_class._origin_ok(_Handler({"Host": "127.0.0.1:8739"}))
    assert absent is True  # documented CLI/curl allowance


@pytest.mark.xfail(
    strict=False,
    reason=("HARDENING GAP: expected origin is derived from the request-controlled "
            "Host header at webapp.py:257-259, so a DNS-rebound name that matches "
            "its own Origin passes. Pin to 127.0.0.1/<bound port> instead."),
)
def test_origin_is_pinned_to_loopback_not_the_request_host(handler_class):
    rebound = handler_class._origin_ok(_Handler({
        "Host": "attacker.example",
        "Origin": "http://attacker.example",
    }))
    assert rebound is False


def test_token_is_accepted_from_header_query_and_cookie(handler_class, monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", "round2-secret-token")
    assert handler_class._authorized(_Handler(
        {"X-Keel-Token": "round2-secret-token"})) is True
    assert handler_class._authorized(_Handler({}, "/api/health?t=round2-secret-token")) is True
    assert handler_class._authorized(_Handler(
        {"Cookie": "other=1; keel_token=round2-secret-token"})) is True
    assert handler_class._authorized(_Handler(
        {"X-Keel-Token": "wrong"})) is False


def test_rotate_token_revokes_every_existing_credential(handler_class):
    original = webapp._TOKEN
    webapp._TOKEN = "old-token"
    try:
        old = handler_class._authorized(_Handler({"X-Keel-Token": "old-token"}))
        new_token = webapp.rotate_token()
        assert old is True
        assert new_token != "old-token"
        assert handler_class._authorized(_Handler({"X-Keel-Token": "old-token"})) is False
        assert handler_class._authorized(_Handler({"X-Keel-Token": new_token})) is True
    finally:
        webapp._TOKEN = original


def _request(server, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1],
                                      timeout=10)
    payload = json.dumps(body or {}).encode("utf-8") if body is not None else None
    hdrs = dict(headers or {})
    if payload is not None:
        hdrs["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=hdrs)
    response = conn.getresponse()
    data = response.read()
    result = (response.status, data, dict(response.getheaders()))
    conn.close()
    return result


def test_live_bridge_refuses_missing_token_and_bad_origin(compat_server):
    token = webapp.token()
    status, _, _ = _request(compat_server, "GET", "/api/health")
    assert status == 403
    status, body, _ = _request(compat_server, "GET",
                               f"/api/health?t={token}")
    assert status == 200 and json.loads(body)["ok"] is True
    status, _, _ = _request(compat_server, "POST", "/api/upload?t=" + token,
                            headers={"Origin": "https://evil.example",
                                     "X-Keel-Token": token},
                            body={"name": "x", "contentB64": "eA=="})
    assert status == 403


def test_bff_sanitizes_headers_and_rejects_traversal():
    source = (ROOT / "fleet-next" / "app" / "api" / "bridge"
              / "[...path]" / "route.ts").read_text(encoding="utf-8")
    for header in ("host", "connection", "cookie", "origin", "referer"):
        assert f'headers.delete("{header}")' in source
    assert 'headers.set("x-keel-token", BRIDGE_TOKEN)' in source
    assert 's.includes("..")' in source
    assert 'process.env.KEEL_BRIDGE_TOKEN' in source
    assert 'error: "bridge_unavailable"' in source


def test_public_mirror_has_no_desktop_only_api_calls():
    ui = (ROOT / "site" / "ui" / "app.js").read_text(encoding="utf-8")
    assert "/api/fleet/" not in ui
    assert "providers/save" not in ui
    assert "providers/credential" not in ui
    assert "keel_mirror_settings_v1" in ui
    html = (ROOT / "site" / "app.html").read_text(encoding="utf-8")
    assert "PUBLIC MIRROR" in html.upper()
