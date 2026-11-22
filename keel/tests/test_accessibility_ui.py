"""C10.5 — voice control, spoken responses and live-region accessibility."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from keel.tutorial import AccessibilityStore, accessibility_descriptor

ROOT = Path(__file__).resolve().parents[1]
TREES = [
    (ROOT / "desktop" / "ui" / "index.html", ROOT / "desktop" / "ui" / "app.js"),
    (ROOT / "site" / "app.html", ROOT / "site" / "ui" / "app.js"),
]


def test_descriptor_defaults_are_opt_in():
    desc = accessibility_descriptor()
    assert desc["spoken_responses"] is False
    assert desc["live_region"] == "polite"
    assert accessibility_descriptor(True)["spoken_responses"] is True


def test_accessibility_store(tmp_path):
    store = AccessibilityStore(tmp_path)
    assert store.load()["spoken_responses"] is False
    assert store.load()["stored"] is False
    saved = store.save({"spoken_responses": True, "live_region": "assertive"})
    assert saved["spoken_responses"] is True
    assert saved["live_region"] == "assertive"
    assert saved["stored"] is True
    assert json.loads(store.path.read_text())["spoken_responses"] is True
    try:
        store.save({"live_region": "invalid"})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid live_region accepted")


def test_capabilities(tmp_path):
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    state = str(tmp_path)
    cur = invoke("cowork.accessibility.get", {"state_root": state},
                 context={})["result"]
    assert cur["spoken_responses"] is False
    updated = invoke("cowork.accessibility.set",
                     {"settings": {"spoken_responses": True},
                      "state_root": state}, context={})["result"]
    assert updated["spoken_responses"] is True


def test_both_ui_trees_have_controls():
    for html, _ in TREES:
        text = html.read_text(encoding="utf-8")
        for cid in ("mic-chat", "mic-code", "voice-status-chat",
                    "voice-status-code", "a11y-live-region", "a11y-spoken",
                    "a11y-live"):
            assert f'id="{cid}"' in text, f"{html.name}: {cid}"


def test_both_ui_trees_wire_voice():
    for _, js_path in TREES:
        js = js_path.read_text(encoding="utf-8")
        for token in ("SpeechRecognition", "startVoice", "stopVoice",
                      "speechSynthesis", "SpeechSynthesisUtterance",
                      "cowork.accessibility.get", "cowork.accessibility.set",
                      "__keelAnnounce", "__keelSpeak", "dictation error",
                      "not available in this browser", "window.confirm"):
            assert token in js, f"{js_path.name}: {token}"


def test_js_syntax():
    for _, js_path in TREES:
        result = subprocess.run(["node", "--check", str(js_path)],
                                cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, js_path.name + ": " + result.stderr
