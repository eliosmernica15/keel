"""B4.11 — real backup/restore over the HTTP bridge."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import urllib.error

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes

TOKEN = "backup-e2e-token"


def _post(port, path, body, token=TOKEN):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(), method="POST",
        headers={"X-Keel-Token": token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_backup_create_restore_over_bridge(tmp_path, monkeypatch):
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    source = tmp_path / "work"
    source.mkdir()
    (source / "data.txt").write_text("important", encoding="utf-8")

    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        status, meta = _post(port, "/api/backups/create", {
            "source": "work", "target": "backup.json", "passphrase": "pw"})
        assert status == 200 and meta["files"] == 1
        status, result = _post(port, "/api/backups/restore", {
            "backup": "backup.json", "target": "recovered", "passphrase": "pw"})
        assert status == 200 and result["restored"] == ["data.txt"]
        assert (tmp_path / "recovered" / "data.txt").read_text() == "important"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
