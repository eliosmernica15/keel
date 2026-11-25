"""Web/PWA surface hardening.

The packaged desktop app serves ``site/app.html`` + ``site/ui/app.js`` through
the local Python bridge (``keel.webapp``).  Two classes of defect are guarded
here:

1. static UI that calls routes the bridge never registered (disconnected
   controls), and local-only controls gated on a mock flag that is never true;
2. stale / incomplete PWA assets (service-worker cache + manifest icons).
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "site" / "ui" / "app.js"
APP_HTML = ROOT / "site" / "app.html"
BRIDGE = ROOT / "src" / "keel" / "webapp.py"
PWA_DIR = ROOT / "desktop"
# A SHELL asset may be served from any of these trees depending on whether
# the bridge runs from source or from the packaged Electron app.
UI_DIRS = (ROOT / "site", ROOT / "site" / "ui", ROOT / "desktop" / "ui")


def _bridge_routes():
    """Extract route literals actually registered by webapp.py (no hardcoding)."""
    tree = ast.parse(BRIDGE.read_text(encoding="utf-8"))
    exact: set[str] = set()
    prefixes: set[str] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                and node.left.id == "path"):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.In)):
                    values = (comp.elts if isinstance(comp, (ast.Tuple, ast.List, ast.Set))
                              else [comp])
                    exact.update(v.value for v in values
                                 if isinstance(v, ast.Constant)
                                 and isinstance(v.value, str))
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "startswith"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "path"):
            prefixes.update(a.value for a in node.args
                            if isinstance(a, ast.Constant)
                            and isinstance(a.value, str))
    return exact, prefixes


def _app_js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_static_ui_references_only_implemented_endpoints():
    js = _app_js()
    exact, prefixes = _bridge_routes()
    literals = re.findall(r'["\'`](/api/[^"\'`]*)["\'`]', js)
    assert literals, "no API paths found in app.js - parser is broken"
    unmapped = []
    for raw in sorted(set(literals)):
        path = raw.split("?", 1)[0].split("${", 1)[0].rstrip("/") or "/"
        if path in exact or any(path.startswith(p.rstrip("/")) for p in prefixes):
            continue
        unmapped.append((raw, path))
    assert not unmapped, f"app.js calls routes webapp.py does not register: {unmapped}"


def test_fetch_literals_are_api_routes_or_external_providers():
    js = _app_js()
    for _quote, raw in re.findall(r'\bfetch\(\s*(["\'`])([^"\'`]*)\1', js):
        assert raw.startswith("/api/") or raw.startswith("http") or "://" in raw, (
            f"unexpected fetch target: {raw!r}")
    # The v2 agent stream is an EventSource, not fetch().
    assert 'new EventSource(url)' in js
    assert '/api/v2/sessions/${encodeURIComponent(sess.id)}/events?since=' in js


def test_local_controls_probe_the_real_bridge():
    js = _app_js()
    # A mock bridge object exists for the static mirror, but its `live` flag is
    # hard-coded false. It must never gate a control that needs the real
    # bridge; `agent.ready` comes from GET /api/health.
    assert "bridge.live" not in js
    body = js[js.index("async function applyWorkdir"):js.index('$("fs-use").addEventListener')]
    assert 'fetch("/api/workdir"' in body and "agent.ready" in body
    fs_body = js[js.index("function openFsPicker"):js.index("function setWorkdirUI")]
    assert "/api/fs/list" in fs_body and "agent.ready" in fs_body
    kill_body = js[js.index("if (killBtn)"):js.index("/* B4.1 — Quick Ask")]
    assert "/api/kill-switch" in kill_body and "agent.ready" in kill_body


def test_kill_switch_keeps_url_token_in_sync():
    """Rotating the bridge token must not leave the stale ?t= in the URL."""
    js = _app_js()
    body = js[js.index("if (killBtn)"):js.index("/* B4.1 — Quick Ask")]
    assert 'sessionStorage.setItem("keel_token", doc.token)' in body
    assert 'url.searchParams.set("t", doc.token)' in body
    assert "history.replaceState" in body


def test_navigation_has_no_dead_download_link():
    js = _app_js()
    assert 'downloadLink.hidden = agent.ready' in js
    assert "navCursor" in js and "syncNavButtons" in js


def test_pwa_assets_exist_and_are_consistent():
    manifest_path = PWA_DIR / "manifest.webmanifest"
    sw_path = PWA_DIR / "sw.js"
    assert manifest_path.is_file() and sw_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["theme_color"] == "#0a0605"

    sw = sw_path.read_text(encoding="utf-8")
    version = re.search(r'const VERSION\s*=\s*"keel-shell-v(\d+)"', sw)
    assert version and int(version.group(1)) >= 6, "stale service-worker cache version"
    shell_block = re.search(r'const SHELL\s*=\s*\[(.*?)\]', sw, re.S)
    assert shell_block
    shell = re.findall(r'["\']([^"\']+)["\']', shell_block.group(1))
    for required in ("/", "/ui/index.html", "/ui/style.css", "/ui/app.js",
                     "/ui/management.js", "/manifest.webmanifest"):
        assert required in shell, f"shell cache is missing {required}"
    assert 'url.pathname.startsWith("/api/")' in sw, "API calls must bypass the cache"

    def _exists(path: str) -> bool:
        name = path[len("/ui/"):] if path.startswith("/ui/") else path.lstrip("/")
        candidates = [d / name for d in UI_DIRS]
        candidates += [d / "ui" / name for d in UI_DIRS]
        return any(c.is_file() for c in candidates)

    for path in shell:
        if path == "/":
            continue
        assert _exists(path), f"cached asset does not exist: {path}"
    for icon in manifest["icons"]:
        assert _exists(icon["src"]), f"manifest icon does not exist: {icon['src']}"

    # Theme colour must match the app shell (dark theme).
    html = APP_HTML.read_text(encoding="utf-8")
    assert f'content="{manifest["theme_color"]}"' in html


def test_js_syntax():
    for path in (APP_JS, PWA_DIR / "sw.js"):
        result = subprocess.run(["node", "--check", str(path)],
                                cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, f"{path.name}: {result.stderr}"


def test_referenced_get_endpoints_answer_on_real_bridge():
    import keel.webapp as webapp

    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        for path in ("/api/health", "/api/surfaces", "/api/capabilities",
                     "/api/model-catalog/google", "/api/files/search?query=x",
                     "/api/fs/list", "/api/workdir", "/manifest.webmanifest",
                     "/sw.js", "/ui/app.js", "/ui/management.js"):
            url = f"{base}{path}{'&' if '?' in path else '?'}t={webapp.token()}"
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    status = resp.status
                    resp.read(256)
            except urllib.error.HTTPError as exc:
                status = exc.code
            assert status == 200, f"bridge did not serve {path}: {status}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
