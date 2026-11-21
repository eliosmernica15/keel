"""B4.10 — agent profile management over the HTTP bridge."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request

import keel.webapp as webapp

TOKEN = "profile-token"


def _req(port, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data,
        method="POST" if body is not None else "GET",
        headers={"X-Keel-Token": TOKEN,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode())


def test_profile_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path / "state"))
    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        created = _req(port, "/api/profiles/create",
                       {"name": "work", "agents": ["cowork", "code"]})
        assert created["profile"]["name"] == "work"
        doc = _req(port, "/api/profiles")
        assert len(doc["profiles"]) == 1 and doc["active"]["name"] == "work"
        activated = _req(port, "/api/profiles/activate", {"name": "work"})
        assert activated["ok"] is True
        removed = _req(port, "/api/profiles/remove", {"name": "work"})
        assert removed["ok"] is True
        assert _req(port, "/api/profiles")["profiles"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
