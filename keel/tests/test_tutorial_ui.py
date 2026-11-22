"""C10.1 — interactive tutorial: real backend state + usable UI wiring."""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import keel.webapp as webapp
from keel.tutorial import (TUTORIAL_STEPS, TutorialStore, tips,
                           tutorial_state, whats_new)

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
HTML = (SITE / "app.html").read_text(encoding="utf-8")
JS = (SITE / "ui" / "app.js").read_text(encoding="utf-8")
CSS = (SITE / "ui" / "style.css").read_text(encoding="utf-8")
DESKTOP = ROOT / "desktop" / "ui"
DHTML = (DESKTOP / "index.html").read_text(encoding="utf-8")
DJS = (DESKTOP / "app.js").read_text(encoding="utf-8")
DCSS = (DESKTOP / "style.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------- backend
def test_tutorial_state_shape():
    state = tutorial_state(["welcome"])
    assert state["total"] == 4 and state["done"] == 1
    assert state["finished"] is False and state["next"] == "workspace"
    assert state["steps"] == TUTORIAL_STEPS


def test_tutorial_store_persists_and_resets(tmp_path):
    store = TutorialStore(tmp_path)
    assert store.load()["done"] == 0
    store.mark("welcome")
    store.mark("workspace")
    assert store.load()["done"] == 2
    assert store.load()["next"] == "first_prompt"
    # idempotent + validation
    store.mark("welcome")
    assert store.load()["done"] == 2
    try:
        store.mark("does-not-exist")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown step accepted")
    assert store.reset()["done"] == 0
    assert json.loads(store.path.read_text())["completed"] == []


def test_tips_and_whats_new():
    assert len(tips()) >= 1 and all(t["id"] and t["text"] for t in tips())
    news = whats_new()
    assert news["version"] and news["items"]


def test_capabilities(tmp_path):
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    state = invoke("cowork.tutorial.state", {"completed": ["welcome"]},
                   context={})["result"]
    assert state["done"] == 1
    assert invoke("cowork.tutorial.tips", {}, context={})["result"]["tips"]
    assert invoke("cowork.tutorial.whats_new", {}, context={})["result"]["version"]
    persisted = invoke("cowork.tutorial.complete",
                       {"step_id": "welcome", "state_root": str(tmp_path)},
                       context={})["result"]
    assert persisted["done"] == 1


# ------------------------------------------------------------ HTTP bridge
def _http(port, path, *, body=None, token="tour-token"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method="POST",
        headers={"X-Keel-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_tutorial_flow_over_real_bridge(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "_TOKEN", "tour-token")
    monkeypatch.setattr(webapp, "_WORKDIR", str(tmp_path))
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path / "state"))
    server = webapp.make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    try:
        status, doc = _http(port, "/api/capabilities/invoke",
                            body={"id": "cowork.tutorial.state",
                                  "params": {"persist": True}})
        assert status == 200 and doc["ok"] is True
        assert doc["result"]["done"] == 0
        assert len(doc["result"]["steps"]) == 4

        status, doc = _http(port, "/api/capabilities/invoke",
                            body={"id": "cowork.tutorial.complete",
                                  "params": {"step_id": "welcome"},
                                  "confirm": True})
        assert status == 200 and doc["result"]["done"] == 1

        status, doc = _http(port, "/api/capabilities/invoke",
                            body={"id": "cowork.tutorial.state",
                                  "params": {"persist": True}})
        assert status == 200 and doc["result"]["done"] == 1
        assert doc["result"]["next"] == "workspace"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------- frontend
def test_html_has_all_tour_controls():
    for cid in ("nav-tutorial", "btn-tutorial", "tutorial-overlay",
                "tour-backdrop", "tour-close", "tour-status", "tour-loading",
                "tour-empty", "tour-content", "tour-step-count", "tour-title",
                "tour-text", "tour-hint", "tour-dots", "tour-skip", "tour-back",
                "tour-next", "tour-source", "whatsnew-overlay", "whatsnew-list",
                "whatsnew-close", "whatsnew-ok", "whatsnew-remember",
                "tip-banner", "tip-text", "tip-dismiss"):
        assert f'id="{cid}"' in HTML, cid


def test_js_wires_real_handlers_and_backend():
    for token in ('id="nav-tutorial"', 'nav-tutorial")?.addEventListener',
                  'btn-tutorial")?.addEventListener',
                  'tour-next")?.addEventListener',
                  'tour-back")?.addEventListener',
                  'tour-skip")?.addEventListener',
                  'tour-close")?.addEventListener',
                  'whatsnew-ok")?.addEventListener',
                  'tip-dismiss")?.addEventListener',
                  '"/api/capabilities/invoke"',
                  'cowork.tutorial.state', 'cowork.tutorial.complete',
                  'cowork.tutorial.whats_new', 'tourRender()', 'tourLoad()'):
        # html-style id tokens appear in HTML, not JS; check in the right file
        source = HTML if token.startswith('id="') else JS
        assert token in source, token


def test_js_has_real_states():
    for token in ("tour-loading", "tour-empty", "tour-status",
                  "err.denied", "Permission denied", "Local bridge unavailable",
                  "Error: ", "tour-source"):
        assert token in JS, token


def test_js_fallback_steps_match_backend_ids():
    block = JS.split("const TOUR_STEPS_FALLBACK = [", 1)[1].split("];", 1)[0]
    ids = set(re.findall(r'id:\s*"([^"]+)"', block))
    assert ids == {s["id"] for s in TUTORIAL_STEPS}


def test_css_has_tour_styles():
    for token in (".tour-overlay", ".tour-card", ".tour-dots",
                  ".tour-highlight", ".tip-banner", "@media(max-width:600px)"):
        assert token in CSS, token


def test_js_syntax():
    for path in (SITE / "ui" / "app.js", DESKTOP / "app.js"):
        result = subprocess.run(["node", "--check", str(path)],
                                cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, path.name + ": " + result.stderr


# ------------------------------------------------- real desktop app UI tree
def test_desktop_ui_has_tour_controls():
    for cid in ("nav-tutorial", "btn-tutorial", "tutorial-overlay",
                "tour-status", "tour-loading", "tour-empty", "tour-content",
                "tour-step-count", "tour-title", "tour-text", "tour-hint",
                "tour-dots", "tour-back", "tour-next", "tour-skip",
                "tour-source", "whatsnew-overlay", "whatsnew-list",
                "whatsnew-ok", "whatsnew-remember", "tip-banner", "tip-text",
                "tip-dismiss"):
        assert f'id="{cid}"' in DHTML, cid


def test_desktop_ui_js_wires_tour():
    for token in ('nav-tutorial")?.addEventListener',
                  'btn-tutorial")?.addEventListener',
                  'tour-next")?.addEventListener',
                  'cowork.tutorial.state', 'cowork.tutorial.complete',
                  'cowork.tutorial.whats_new', 'err.denied',
                  'Permission denied', 'Local bridge unavailable',
                  '"/api/capabilities/invoke"'):
        assert token in DJS, token


def test_desktop_css_and_fallback_ids():
    for token in (".tour-overlay", ".tour-card", ".tour-dots",
                  ".tour-highlight", ".tip-banner", "@media(max-width:600px)"):
        assert token in DCSS, token
    block = DJS.split("const TOUR_STEPS_FALLBACK = [", 1)[1].split("];", 1)[0]
    ids = set(re.findall(r'id:\s*"([^"]+)"', block))
    assert ids == {s["id"] for s in TUTORIAL_STEPS}
