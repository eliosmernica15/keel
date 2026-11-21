"""B4.1 — Quick Ask overlay backed by real runtime execution."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes
from keel.tui import Tui
from keel.cli.main import main

TOKEN = "quick-token"


def _post(port, path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(), method="POST",
        headers={"X-Keel-Token": TOKEN,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_quick_ask_endpoint_uses_real_runtime(tmp_path, monkeypatch):
    script = tmp_path / "script.json"
    script.write_text(json.dumps({"script": [
        [{"type": "text", "text": "quick answer"}]]}), encoding="utf-8")
    monkeypatch.setenv("KEEL_FAKE_SCRIPT", str(script))
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    monkeypatch.setattr(webapp, "_TOKEN", TOKEN)
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))

    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        status, result = _post(port, "/api/quick-ask", {"prompt": "hi"})
        assert status == 200 and result["ok"] is True
        assert result["result"] == "quick answer"
        status, result = _post(port, "/api/quick-ask", {"prompt": "  "})
        assert status == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_cli_tui_command():
    assert main(["tui", "--help"]) == 0


def test_overlay_ui_wired():
    from pathlib import Path

    site = Path(__file__).resolve().parents[1] / "site"
    js = (site / "ui" / "app.js").read_text(encoding="utf-8")
    html = (site / "app.html").read_text(encoding="utf-8")
    assert "/api/quick-ask" in js
    assert "submitQuickAsk" in js
    assert 'id="quick-overlay"' in html
    assert 'id="btn-quick"' in html
