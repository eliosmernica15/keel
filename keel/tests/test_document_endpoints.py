"""C2.1 — Cowork document workflows over the real HTTP bridge."""

from __future__ import annotations

import json
import threading
import time

import keel.settings_store as settings_store
import keel.webapp as webapp
from keel.documents import write_docx, write_xlsx
from keel.fleet import routes as fleet_routes

TOKEN = "doc-e2e-token"


def _http(port, path, token=TOKEN):
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 headers={"X-Keel-Token": token})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode())


def test_document_read_endpoints(tmp_path, monkeypatch):
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    write_docx(tmp_path / "report.docx", "Title\nKeel is local-first.")
    write_xlsx(tmp_path / "data.xlsx", [["A", "B"], ["1", "2"]])

    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        doc = _http(port, "/api/docx/read?path=report.docx")
        assert "local-first" in doc["content"]
        grid = _http(port, "/api/xlsx/read?path=data.xlsx")
        assert grid["content"][0][0] == "A"
        try:
            _http(port, "/api/docx/read?path=../outside.docx")
            assert False, "path escape must be refused"
        except Exception:
            pass
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
