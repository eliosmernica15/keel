"""A2.8 — local end-to-end flows over the real authenticated bridge.

Exercises the same HTTP surface the desktop UI uses: app shell, settings,
surfaces, file search and Fleet chat. Browser-driven Playwright specs are an
optional layer; this harness verifies real behaviour without extra services.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

import pytest

import keel.settings_store as settings_store
import keel.webapp as webapp
from keel.fleet import routes as fleet_routes

TOKEN = "e2e-local-token"


def _request(port, path, *, method="GET", body=None, token=TOKEN):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Keel-Token": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data,
        method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
            try:
                return response.status, json.loads(raw)
            except ValueError:
                return response.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    monkeypatch.setattr(settings_store, "SETTINGS_PATH",
                        tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "BACKUP_PATH",
                        tmp_path / "settings.json.bak")

    def _real_load():
        path = settings_store.SETTINGS_PATH
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    # The suite autouse fixture stubs load(); restore real file-backed loading.
    monkeypatch.setattr(settings_store, "load", _real_load)
    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_app_shell_and_auth(bridge):
    port = bridge
    status, body = _request(port, f"/?t={TOKEN}", token=TOKEN)
    assert status == 200 and "Keel" in str(body)
    assert _request(port, "/api/settings", token="wrong")[0] == 403


def test_settings_flow(bridge):
    port = bridge
    status, doc = _request(port, "/api/settings")
    assert status == 200 and isinstance(doc, dict)
    status, _ = _request(port, "/api/settings", method="POST",
                         body={"ui": {"theme": "light"}})
    assert status == 200
    _, doc = _request(port, "/api/settings")
    assert doc.get("ui", {}).get("theme") == "light"


def test_surfaces_and_file_search(bridge, tmp_path):
    port = bridge
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    status, doc = _request(port, "/api/surfaces")
    assert status == 200 and len(doc["surfaces"]) == 4
    status, doc = _request(port, "/api/files/search?query=README")
    assert status == 200 and "README.md" in doc["files"]


def test_fleet_chat_flow(bridge):
    port = bridge
    status, created = _request(port, "/api/fleet/bots", method="POST",
                               body={"name": "E2E", "engine": "provider"})
    assert status == 201
    bot_id = created["bot"]["id"]
    status, _ = _request(port, f"/api/fleet/bots/{bot_id}/messages",
                         method="POST", body={"content": "hello e2e"})
    assert status == 202
    deadline = time.time() + 8
    while time.time() < deadline:
        _, payload = _request(port, f"/api/fleet/bots/{bot_id}/rows")
        rows = payload.get("rows", []) if isinstance(payload, dict) else payload
        if any(row.get("body", {}).get("content") == "hello e2e"
               for row in rows):
            return
        time.sleep(0.2)
    pytest.fail("user message never appeared in the Fleet transcript")
