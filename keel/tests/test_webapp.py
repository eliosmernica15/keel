"""Webapp bridge tests — local HTTP server, real POST /api/run streaming."""

from __future__ import annotations

import json
import http.client
import os
import threading
import urllib.request
from pathlib import Path

import pytest

import keel.webapp as webapp


@pytest.fixture
def server():
    srv = webapp.make_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)


def _url(server, path, token=None):
    base = f"http://127.0.0.1:{server.server_address[1]}"
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}t={token}" if token else f"{base}{path}"


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8"), dict(exc.headers)


def _post(server, path, body, token, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1],
                                      timeout=30)
    headers = {"X-Keel-Token": token, "Content-Type": "application/json"}
    if origin is not None:
        headers["Origin"] = origin
    payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    conn.request("POST", path, body=payload, headers=headers)
    resp = conn.getresponse()
    return resp.status, resp.read().decode("utf-8")


def test_index_requires_token(server):
    status, body, _ = _get(_url(server, "/"))
    assert status == 403
    assert "refused" in body


def test_index_with_token_sets_cookie(server):
    status, body, headers = _get(_url(server, "/", webapp.token()))
    assert status == 200
    assert "<!doctype html" in body.lower()
    cookie = next((v for k, v in headers.items()
                   if k.lower() == "set-cookie"), "")
    assert "keel_token=" in cookie and "SameSite=Strict" in cookie


def test_cookie_alone_authorizes(server):
    # first get the cookie via token URL, then use it alone
    status, body, headers = _get(_url(server, "/", webapp.token()))
    cookie = next(v for k, v in headers.items() if k.lower() == "set-cookie")
    cookie = cookie.split(";")[0]
    status, body, _ = _get(_url(server, "/"), headers={"Cookie": cookie})
    assert status == 200


def test_health_requires_token(server):
    status, _, _ = _get(_url(server, "/api/health"))
    assert status == 403
    status, body, _ = _get(_url(server, "/api/health", webapp.token()))
    assert status == 200
    assert json.loads(body)["ok"] is True


def test_providers_endpoint(server):
    status, body, _ = _get(_url(server, "/api/providers", webapp.token()))
    assert status == 200
    rows = json.loads(body)["providers"]
    names = {r["name"] for r in rows}
    assert {"openrouter", "google", "nvidia", "anthropic"} <= names


def test_upload_roundtrip(server, tmp_path, monkeypatch):
    from keel import settings_store
    monkeypatch.setattr(settings_store, "STATE_DIR", tmp_path)
    payload = {"name": "..\\..\\evil.txt", "contentB64": "aGVsbG8="}  # "hello"
    status, body = _post(server, "/api/upload", payload, webapp.token())
    assert status == 200
    doc = json.loads(body)
    assert doc["ok"] is True
    target = Path(doc["path"])
    assert target.parent == tmp_path / "uploads"
    assert target.read_bytes() == b"hello"
    assert ".." not in target.name


def test_upload_rejects_bad_base64(server, tmp_path, monkeypatch):
    from keel import settings_store
    monkeypatch.setattr(settings_store, "STATE_DIR", tmp_path)
    status, body = _post(server, "/api/upload",
                         {"name": "a.txt", "contentB64": "!!!notb64!!!"},
                         webapp.token())
    assert status == 400
    assert "base64" in body


def test_upload_requires_fields(server, tmp_path, monkeypatch):
    from keel import settings_store
    monkeypatch.setattr(settings_store, "STATE_DIR", tmp_path)
    status, _ = _post(server, "/api/upload", {}, webapp.token())
    assert status == 400


def test_upload_requires_token(server):
    status, _ = _post(server, "/api/upload", {"name": "a.txt", "contentB64": "aA=="},
                      "definitely-not-the-token")
    assert status == 403


def test_static_asset_served(server):
    status, body, headers = _get(_url(server, "/ui/app.js", webapp.token()))
    assert status == 200
    assert "mkBridge" in body


def test_path_traversal_refused(server):
    conn = http.client.HTTPConnection("127.0.0.1",
                                      server.server_address[1], timeout=10)
    conn.request("GET", "/ui/../src/keel/webapp.py?t=" + webapp.token())
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", errors="replace")
    assert resp.status == 404
    assert "BaseHTTPRequestHandler" not in body


def test_bad_token_post_refused(server):
    status, _ = _post(server, "/api/run",
                      {"prompt": "hi"}, token="wrong-token")
    assert status == 403


def test_origin_mismatch_refused(server):
    status, body = _post(server, "/api/run",
                         {"prompt": "hi"},
                         token=webapp.token(),
                         origin="https://evil.example.com")
    assert status == 403


def test_empty_prompt_refused(server):
    status, body = _post(server, "/api/run",
                         {"prompt": ""}, token=webapp.token())
    assert status == 400


def test_run_streams_events_and_done_marker(server, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path / "state"))
    script = tmp_path / "canned.json"
    script.write_text(json.dumps(
        {"script": [[{"type": "text", "text": "webapp works"}]]}),
        encoding="utf-8")
    monkeypatch.setenv("KEEL_FAKE_SCRIPT", str(script))
    status, body = _post(server, "/api/run",
                         {"prompt": "say hi", "provider": "auto",
                          "permission_mode": "default"},
                         token=webapp.token())
    assert status == 200
    events = [json.loads(line) for line in body.splitlines() if line.strip()]
    kinds = [e.get("type") for e in events]
    assert "system" in kinds and "result" in kinds
    assert events[-1]["type"] == "bridge"
    assert events[-1]["subtype"] == "done"
