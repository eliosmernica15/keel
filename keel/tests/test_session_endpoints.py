"""A1.17/A1.2 — session import and stats over the HTTP bridge."""

from __future__ import annotations

import json
import threading
import time
import urllib.request

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.session_export import export_bundle

TOKEN = "session-token"


def _post(port, path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(), method="POST",
        headers={"X-Keel-Token": TOKEN,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, json.loads(response.read().decode())


def test_session_import_and_stats_over_bridge(tmp_path, monkeypatch):
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    source = fleet_routes.store().create_bot(
        name="Source", engine="provider", bot_id="source1", kind="session")
    fleet_routes.store().append_row(source["id"], "message",
                                    {"role": "user", "content": "hello"})
    bundle = export_bundle(fleet_routes.store(), source["id"])

    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        status, result = _post(port, "/api/sessions/import", {"bundle": bundle})
        assert status == 200 and result["session"]["id"] != source["id"]
        imported = result["session"]["id"]
        status, stats = _post(port, "/api/sessions/stats",
                              {"session_id": imported})
        assert status == 200 and stats["rows"] >= 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
