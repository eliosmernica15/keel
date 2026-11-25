"""Distribution round — renderer selection and bridge token auth.

Two kinds of evidence live here and are deliberately kept apart:

* ``test_shipped_sources_*`` are *source-level* checks. They prove the
  packaged Electron shell resolves the full local ``desktop/ui`` first, that
  the PyInstaller sidecar bundles it, and that neither packaging nor installer
  config injects a fake-execution environment variable. They do not launch
  Electron.

* ``test_live_bridge_*`` are *real local runtime* checks. They start an actual
  ``keel.webapp`` HTTP server on 127.0.0.1 with a throwaway token, issue real
  HTTP requests and assert the served page and the auth gate. No provider key
  or external network is involved.

The "demo mode" branch in ``desktop/ui/app.js`` is intentionally reachable
only from ``file:`` (standalone browser). Electron loads ``http://127.0.0.1``
with a token, so it takes the live ``/api/run`` branch; that contract is
asserted below.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import keel.webapp as webapp
from keel.fleet import routes as fleet_routes

ROOT = Path(__file__).resolve().parents[1]
TOKEN = webapp.token()  # conftest.py pins a throwaway local token


@pytest.fixture()
def bridge(tmp_path):
    old = fleet_routes._store
    fleet_routes.reset_store_for_tests(tmp_path / "renderer-fleet.db")
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    fleet_routes._store = old


def _base(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def _raw(server, path, *, token=None, method="GET", headers=None, body=None):
    h = {"X-Keel-Token": TOKEN if token is None else token}
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(_base(server) + path, data=data,
                                 headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# source-level: what a packaged build is wired to do
# ---------------------------------------------------------------------------

def test_shipped_sources_select_full_local_renderer():
    main_js = (ROOT / "desktop-app" / "main.js").read_text(encoding="utf-8")
    spec = (ROOT / "desktop-app" / "sidecar.spec").read_text(encoding="utf-8")
    webapp_py = (ROOT / "src" / "keel" / "webapp.py").read_text(encoding="utf-8")
    app_js = (ROOT / "desktop" / "ui" / "app.js").read_text(encoding="utf-8")
    pkg = json.loads((ROOT / "desktop-app" / "package.json").read_text(encoding="utf-8"))

    # Electron: resources/desktop/ui is the first candidate; site is reachable
    # only behind the explicit mirror rollback flag.
    local = main_js.index('join(res, "desktop", "ui")')
    legacy = main_js.index('join(res, "ui")')
    assert local < legacy, "full local UI must precede the legacy layout"
    profile_at = main_js.index("KEEL_UI_PROFILE")
    mirror_gate_at = main_js.index('=== "mirror"')
    mirror_at = main_js.index('join(res, "site")')
    # `join(res, "site")` appears only inside the explicit mirror rollback
    # branch, which is gated by KEEL_UI_PROFILE and precedes the default list.
    assert profile_at < mirror_gate_at < mirror_at < local
    assert "env.KEEL_UI_DIR = uiRoot() || undefined;" in main_js
    assert 'mainWindow.loadURL(`http://127.0.0.1:${sidecarPort}/?t=${sidecarToken}`)' in main_js

    # electron-builder ships the same local tree into resources/desktop/ui.
    targets = {r.get("to") for r in pkg["build"]["extraResources"]}
    assert "desktop/ui" in targets

    # Frozen sidecar bundles desktop/ui and the bridge falls back to it.
    assert '(str(ROOT / "desktop" / "ui"), "desktop/ui")' in spec
    assert 'UI_DIR = Path(os.environ.get("KEEL_UI_DIR") or _BUNDLE_ROOT / "desktop" / "ui")' in webapp_py

    # Renderer takes the live bridge branch on http(s) (Electron's scheme),
    # and the labelled demo branch only on file:.
    live_at = app_js.index('if (location.protocol === "http:" || location.protocol === "https:")')
    demo_at = app_js.index('live: false,')
    assert live_at < demo_at
    assert 'fetch("/api/run"' in app_js
    assert "no model and no keel backend are connected" in app_js  # honest demo label


def test_shipped_configs_do_not_inject_fake_execution():
    """Installer/release config must never turn the real runtime into a fake."""
    scan_roots = [ROOT / "desktop-app", ROOT / "src" / "keel" / "release",
                  ROOT.parent / ".github" / "workflows"]
    config_files: list[Path] = []
    for scan in scan_roots:
        if scan.is_dir():
            config_files.extend(p for p in scan.rglob("*")
                                if p.is_file() and p.suffix.lower() in
                                {".js", ".json", ".yml", ".yaml", ".nsi", ".spec", ".py"})
    offenders = []
    for path in config_files:
        # Scripts under desktop-app/scripts are read-only assertions/test
        # tooling, not configuration that reaches a shipped process.
        if "scripts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("//", "/*", "*", "#")):
                continue  # documentation of the rollback flag, not injection
            if "KEEL_FAKE_SCRIPT" in line or "KEEL_UI_PROFILE=mirror" in line:
                offenders.append(str(path.relative_to(ROOT.parent)))
    assert offenders == [], f"shipped config injects a fake path: {offenders}"

    # The only KEEL_FAKE_SCRIPT consumers in the bridge are opt-in test hooks.
    webapp_py = (ROOT / "src" / "keel" / "webapp.py").read_text(encoding="utf-8")
    assert webapp_py.count('os.environ.get("KEEL_FAKE_SCRIPT")') == 2  # quick-ask + run


# ---------------------------------------------------------------------------
# real local runtime: live HTTP bridge
# ---------------------------------------------------------------------------

def test_live_bridge_serves_full_local_ui_not_browser_mirror(bridge):
    status, page = _raw(bridge, "/?t=" + TOKEN)
    assert status == 200
    for marker in ("Keel Cowork", "Execution policies", "Take the tour"):
        assert marker in page, marker
    # `safe-mode-badge` is unique to site/app.html (the restricted mirror).
    assert "safe-mode-badge" not in page

    status, js = _raw(bridge, "/ui/app.js")
    assert status == 200 and 'fetch("/api/run"' in js
    status, css = _raw(bridge, "/ui/style.css")
    assert status == 200 and len(css) > 100


def test_live_bridge_token_auth_is_enforced(bridge):
    # No credential at all.
    status, body = _raw(bridge, "/api/fleet/bots", token="")
    assert status == 403 and "refused" in body
    # Wrong credential.
    status, _ = _raw(bridge, "/api/fleet/bots", token="definitely-wrong")
    assert status == 403
    # Token in the query string (this is what Electron's loadURL uses).
    status, body = _raw(bridge, "/api/fleet/bots?t=" + TOKEN, token="")
    assert status == 200 and "bots" in body
    # Cookie credential (set by the bridge on '/').
    status, body = _raw(bridge, "/api/fleet/bots", token="",
                        headers={"Cookie": f"keel_token={TOKEN}"})
    assert status == 200 and "bots" in body
    # POST without a valid token must be refused before any route runs.
    status, body = _raw(bridge, "/api/run", token="wrong", method="POST",
                        body={"prompt": "should not execute"})
    assert status == 403 and "refused" in body.lower()

    # A foreign Origin on a mutating request is refused even with a good token.
    status, body = _raw(bridge, "/api/fleet/bots", method="POST",
                        headers={"Origin": "https://evil.example"},
                        body={"name": "nope", "engine": "echo"})
    assert status == 403 and "refused" in body.lower()
