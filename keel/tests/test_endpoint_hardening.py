"""Security hardening of the new E2E HTTP endpoints."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes

TOKEN = "harden-token"


def _post(port, path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(), method="POST",
        headers={"X-Keel-Token": TOKEN,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_backup_endpoint_hardening(tmp_path, monkeypatch):
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    source = tmp_path / "work"
    source.mkdir()
    (source / "x.txt").write_text("data")

    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        # empty passphrase refused
        status, body = _post(port, "/api/backups/create", {
            "source": "work", "target": "b.json", "passphrase": ""})
        assert status == 400 and "passphrase" in body["error"]
        # path escape refused
        status, body = _post(port, "/api/backups/create", {
            "source": "../outside", "target": "b.json", "passphrase": "pw"})
        assert status == 200 and "error" in body
        # corrupted backup refused safely
        (tmp_path / "bad.json").write_text("not-json")
        status, body = _post(port, "/api/backups/restore", {
            "backup": "bad.json", "target": "out", "passphrase": "pw"})
        assert status == 400 and "error" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
