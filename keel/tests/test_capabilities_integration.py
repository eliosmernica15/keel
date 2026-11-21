"""Capability hub integrated into the real HTTP backend."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import keel.webapp as webapp

TOKEN = "cap-token"


def _http(port, path, *, method="GET", body=None, token=TOKEN,
          origin=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"X-Keel-Token": token,
               "Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data,
        method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_capability_listing_over_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        status, doc = _http(port, "/api/capabilities")
        assert status == 200
        assert len(doc["capabilities"]) >= 150
        ids = {c["id"] for c in doc["capabilities"]}
        assert "core.hardware.detect" in ids
        assert "cowork.doc.qa" in ids
        # surface filter
        status, doc = _http(port, "/api/capabilities?surface=duet")
        assert status == 200 and all(c["surface"] == "duet"
                                     for c in doc["capabilities"])
        assert _http(port, "/api/capabilities", token="bad")[0] == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_capability_invoke_over_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path / "state"))
    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        status, result = _http(port, "/api/capabilities/invoke",
                               method="POST",
                               body={"id": "core.hardware.detect",
                                     "params": {}})
        assert status == 200 and result["ok"] is True
        assert "os" in result["result"]

        status, result = _http(port, "/api/capabilities/invoke",
                               method="POST",
                               body={"id": "cowork.doc.qa",
                                     "params": {
                                         "question": "private local",
                                         "text": "Keel is local-first and private."}})
        assert status == 200 and result["result"]["hits"]

        status, result = _http(port, "/api/capabilities/invoke",
                               method="POST",
                               body={"id": "no.such.capability",
                                     "params": {}})
        assert status == 404

        # destructive capability requires confirm
        status, result = _http(port, "/api/capabilities/invoke",
                               method="POST",
                               body={"id": "core.flags.set",
                                     "params": {"name": "x",
                                                "enabled": True}})
        assert status == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_audit_log_written(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path / "state"))
    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        _http(port, "/api/capabilities/invoke", method="POST",
              body={"id": "core.hardware.detect", "params": {}})
        path = tmp_path / "state" / "capability-audit.jsonl"
        assert path.is_file()
        entries = [json.loads(line) for line in
                   path.read_text().splitlines() if line.strip()]
        assert entries[-1]["capability"] == "core.hardware.detect"
        assert entries[-1]["ok"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
