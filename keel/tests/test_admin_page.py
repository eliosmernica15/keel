"""A3.9 — Operator Admin page backed by real local runtime state."""

from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import keel.webapp as webapp
from keel.admin_page import admin_overview

ROOT = Path(__file__).resolve().parents[1]
TREES = [
    (ROOT / "desktop" / "ui" / "index.html", ROOT / "desktop" / "ui" / "app.js"),
    (ROOT / "site" / "app.html", ROOT / "site" / "ui" / "app.js"),
]


def test_overview_shape_real_data(tmp_path):
    data = admin_overview(tmp_path)
    assert data["local_only"] is True and data["generated_at"]
    assert set(data) >= {"health", "alerts", "resources", "background",
                         "flags", "audit", "diagnostics"}
    assert len(data["resources"]["meters"]) == 3
    assert all("feature" in m and "cap" in m for m in data["resources"]["meters"])
    assert data["background"]["timeout_s"] == 300
    assert isinstance(data["flags"], dict)
    assert data["audit"]["count"] >= 0
    assert data["alerts"][0]["level"] in ("ok", "warning")


def test_overview_alert_on_failed_start(tmp_path):
    from keel.start_health import record_start
    record_start(str(tmp_path), "0.1.1", ok=False)
    data = admin_overview(tmp_path)
    assert any(a["level"] == "warning" for a in data["alerts"])


def test_capability(tmp_path):
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke
    result = invoke("core.admin.overview", {"state_root": str(tmp_path)},
                    context={})["result"]
    assert result["local_only"] is True


def test_overview_over_real_bridge(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", "admin-token")
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/capabilities/invoke",
            data=json.dumps({"id": "core.admin.overview", "params": {}}).encode(),
            method="POST", headers={"X-Keel-Token": "admin-token",
                                    "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            doc = json.loads(resp.read().decode())
        assert doc["ok"] is True and doc["result"]["local_only"] is True
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_both_ui_trees_have_admin_pane():
    ids = ("pane-admin", "admin-refresh", "admin-generated", "admin-status",
           "admin-loading", "admin-alerts", "admin-resources",
           "admin-background", "admin-flags", "admin-audit", "admin-health",
           "admin-health-empty", "admin-diagnostics")
    for html, js in TREES:
        h = html.read_text(encoding="utf-8")
        j = js.read_text(encoding="utf-8")
        assert 'data-section="admin"' in h, html.name
        for cid in ids:
            assert f'id="{cid}"' in h, f"{html.name}: {cid}"
        for token in ("core.admin.overview", "loadAdmin", "adminRender",
                      "Permission denied", "No data recorded yet."):
            assert token in j, f"{js.name}: {token}"
        assert "Reading local state" in h, html.name


def test_js_syntax():
    for _, js in TREES:
        result = subprocess.run(["node", "--check", str(js)],
                                cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, js.name + ": " + result.stderr
