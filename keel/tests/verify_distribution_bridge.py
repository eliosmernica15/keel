"""Agent B / production distribution round — deterministic bridge checks.

Covers the surfaces the packaged Electron shell actually drives:

* ``/api/health`` (liveness + version) and the renderer entry at ``/``,
  ``/app`` and ``/app.html`` (full local UI first, index.html fallback);
* token + Origin enforcement, including token rotation and the cookie set
  by the renderer entry;
* the read-only fs/workdir/capabilities/provider surfaces used by the UI;
* the UI-root selection contract: the Python bridge is profile-agnostic and
  serves whichever root the shell selects (full local UI by default, the
  ``site`` mirror only via the explicit mirror rollback profile).

Every test owns its HTTP server and temporary UI tree and tears them down.
No external service and no ``/api/run`` subprocess is used, so results are
deterministic and independent of provider credentials.
"""

from __future__ import annotations

import http.client
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

import keel
import keel.webapp as webapp


@pytest.fixture
def ui_tree(tmp_path: Path):
    """A minimal, isolated stand-in for desktop/ui + the desktop PWA dir."""
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text(
        "<!doctype html><html><body>INDEX-SHELL</body></html>", encoding="utf-8")
    (ui / "app.js").write_text("mkBridge", encoding="utf-8")
    pwa = tmp_path / "desktop"
    pwa.mkdir()
    (pwa / "manifest.webmanifest").write_text('{"name":"Keel"}', encoding="utf-8")
    (pwa / "sw.js").write_text("// service worker", encoding="utf-8")
    return ui, pwa


@pytest.fixture
def server(ui_tree, monkeypatch):
    ui, pwa = ui_tree
    monkeypatch.setattr(webapp, "UI_DIR", ui)
    monkeypatch.setattr(webapp, "PWA_DIR", pwa)
    monkeypatch.setattr(webapp, "_WORKDIR", None)
    srv = webapp.make_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)


def _base(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def _url(server, path: str, token: str | None = None) -> str:
    sep = "&" if "?" in path else "?"
    return f"{_base(server)}{path}{sep}t={token}" if token else f"{_base(server)}{path}"


def _get(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8"), dict(exc.headers)


def _post(server, path: str, body: dict | bytes, token: str | None,
          origin: str | None = None, *, send_token_header: bool = True):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1],
                                      timeout=10)
    headers = {"Content-Type": "application/json"}
    if token is not None and send_token_header:
        headers["X-Keel-Token"] = token
    if origin is not None:
        headers["Origin"] = origin
    payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    conn.request("POST", path, body=payload, headers=headers)
    resp = conn.getresponse()
    result = resp.status, resp.read().decode("utf-8")
    conn.close()
    return result


# ---------------------------------------------------------------- health / renderer

def test_health_requires_token_and_reports_version(server):
    status, _, _ = _get(_url(server, "/api/health"))
    assert status == 403

    status, body, headers = _get(_url(server, "/api/health", webapp.token()))
    assert status == 200
    doc = json.loads(body)
    assert doc["ok"] is True
    assert doc["version"] == keel.__version__
    assert headers.get("Cache-Control") == "no-store"
    assert headers.get("X-Content-Type-Options") == "nosniff"


def test_renderer_entry_prefers_app_html_then_falls_back(server, ui_tree):
    ui, _ = ui_tree
    app = ui / "app.html"
    app.write_text("<!doctype html><html>APP-SHELL</html>", encoding="utf-8")
    try:
        for path in ("/", "/app", "/app.html"):
            status, body, headers = _get(_url(server, path, webapp.token()))
            assert status == 200
            assert "APP-SHELL" in body
            cookie = next((v for k, v in headers.items()
                           if k.lower() == "set-cookie"), "")
            assert f"keel_token={webapp.token()}" in cookie
            assert "SameSite=Strict" in cookie and "HttpOnly" in cookie
    finally:
        app.unlink()

    # Full local UI ships index.html (no app.html); that is the default entry.
    status, body, _ = _get(_url(server, "/", webapp.token()))
    assert status == 200
    assert "INDEX-SHELL" in body


def test_renderer_entry_rejects_requests_without_token(server):
    for path in ("/", "/app", "/app.html"):
        status, body, _ = _get(_url(server, path))
        assert status == 403
        assert "refused" in body


def test_static_ui_asset_served_and_traversal_refused(server):
    status, body, _ = _get(_url(server, "/ui/app.js", webapp.token()))
    assert status == 200
    assert "mkBridge" in body

    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1],
                                      timeout=10)
    conn.request("GET", "/ui/../src/keel/webapp.py?t=" + webapp.token())
    resp = conn.getresponse()
    assert resp.status == 404
    assert "BaseHTTPRequestHandler" not in resp.read().decode("utf-8", "replace")
    conn.close()


def test_bridge_serves_whichever_ui_root_the_shell_selects(
        server, ui_tree, tmp_path, monkeypatch):
    """The Python bridge has no hardcoded mirror: it serves UI_DIR.

    The shell chooses the full local UI by default and the ``site`` mirror only
    under KEEL_UI_PROFILE=mirror; once KEEL_UI_DIR is set, the renderer entry
    must faithfully serve that selected root.
    """
    mirror = tmp_path / "site-mirror"
    mirror.mkdir()
    (mirror / "index.html").write_text("<!doctype html>MIRROR-SHELL", encoding="utf-8")
    monkeypatch.setattr(webapp, "UI_DIR", mirror)
    status, body, _ = _get(_url(server, "/", webapp.token()))
    assert status == 200
    assert "MIRROR-SHELL" in body
    assert "INDEX-SHELL" not in body


def test_default_ui_dir_is_full_local_ui_when_unconfigured(monkeypatch):
    if os.environ.get("KEEL_UI_DIR"):
        pytest.skip("KEEL_UI_DIR is set in this environment")
    # In source the unconfigured default is <repo>/desktop/ui. This test reads
    # the module-level constant without mutating it, so it cannot disturb the
    # per-test server fixtures.
    assert webapp.UI_DIR.parent.name == "desktop"
    assert webapp.UI_DIR.name == "ui"
    assert (webapp.UI_DIR.parent / "ui").is_dir()


# ------------------------------------------------------------- token / origin gates

def test_token_sources_query_header_cookie(server):
    tok = webapp.token()
    # query parameter
    assert _get(_url(server, "/api/health", tok))[0] == 200
    # explicit header
    assert _get(_url(server, "/api/health"),
                headers={"X-Keel-Token": tok})[0] == 200
    # cookie minted by the renderer entry
    headers = _get(_url(server, "/", tok))[2]
    cookie = next(v for k, v in headers.items() if k.lower() == "set-cookie")
    assert _get(_url(server, "/api/health"),
                headers={"Cookie": cookie.split(";")[0]})[0] == 200


def test_rotate_token_revokes_previous_credential(server, monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", webapp.token())
    old = webapp.token()
    assert _get(_url(server, "/api/health", old))[0] == 200
    new = webapp.rotate_token()
    assert new != old
    assert _get(_url(server, "/api/health", old))[0] == 403
    assert _get(_url(server, "/api/health", new))[0] == 200


def test_post_rejects_bad_token_and_wrong_origin(server, ui_tree, tmp_path):
    ui, _ = ui_tree
    folder = tmp_path / "work"
    folder.mkdir()

    # no token -> refused
    status, body = _post(server, "/api/workdir", {"path": str(folder)}, None)
    assert status == 403 and "refused" in body
    # wrong token -> refused
    status, _ = _post(server, "/api/workdir", {"path": str(folder)}, "wrong-token")
    assert status == 403
    # correct token but hostile Origin -> refused
    status, body = _post(server, "/api/workdir",
                         {"path": str(folder)}, webapp.token(),
                         origin="https://evil.example.com")
    assert status == 403 and "refused" in body

    # matching Origin (browser) and absent Origin (CLI-like client) both pass
    status, body = _post(server, "/api/workdir",
                         {"path": str(folder)}, webapp.token(),
                         origin=_base(server))
    assert status == 200 and json.loads(body)["path"] == str(folder.resolve())
    status, body = _post(server, "/api/workdir",
                         {"path": str(folder)}, webapp.token())
    assert status == 200 and json.loads(body)["path"] == str(folder.resolve())


def test_fleet_post_origin_gate_fires_before_any_mutation(server):
    # /api/fleet/* is dispatched first; a hostile Origin must be refused there
    # too, before the (writable) fleet store is touched.
    status, body = _post(server, "/api/fleet/bots", {"name": "should-not-exist"},
                         webapp.token(), origin="https://evil.example.com")
    assert status == 403
    assert "refused" in body.lower() or "origin" in body.lower()
    status, body, _ = _get(_url(server, "/api/fleet/bots", webapp.token()))
    assert status == 200
    assert all(bot["name"] != "should-not-exist"
               for bot in json.loads(body)["bots"])


# ------------------------------------------------------------- read surfaces used by UI

def test_read_surfaces_are_token_gated_and_well_shaped(server, ui_tree):
    ui, _ = ui_tree
    tok = webapp.token()

    for path in ("/api/providers", "/api/capabilities", "/api/fs/roots",
                 "/api/fs/list", "/api/workdir"):
        assert _get(_url(server, path))[0] == 403

    status, body, _ = _get(_url(server, "/api/providers", tok))
    assert status == 200
    providers = json.loads(body)["providers"]
    assert {"openrouter", "google", "nvidia", "anthropic"} <= {
        row["name"] for row in providers}

    status, body, _ = _get(_url(server, "/api/capabilities", tok))
    assert status == 200
    assert isinstance(json.loads(body)["capabilities"], list)

    status, body, _ = _get(_url(server, "/api/fs/roots", tok))
    assert status == 200
    assert isinstance(json.loads(body)["roots"], list)

    q = urllib.parse.urlencode({"path": str(ui)})
    status, body, _ = _get(_url(server, f"/api/fs/list?{q}", tok))
    assert status == 200
    listing = json.loads(body)
    assert listing["ok"] is True
    assert listing["path"] == str(ui.resolve())
    assert isinstance(listing["dirs"], list)  # directory names only, never file contents

    status, body, _ = _get(_url(server, "/api/workdir", tok))
    assert status == 200
    assert "path" in json.loads(body)
