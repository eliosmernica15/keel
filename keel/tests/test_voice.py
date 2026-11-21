"""A2.2 — push-to-talk dictation and voice-to-task handoff."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_voice_buttons_present():
    html = (ROOT / "site" / "app.html").read_text(encoding="utf-8")
    assert 'id="mic-chat"' in html
    assert 'id="mic-code"' in html
    assert 'id="voice-status-chat"' in html
    assert 'id="voice-status-code"' in html


def test_speech_recognition_is_opt_in_and_visible():
    js = (ROOT / "site" / "ui" / "app.js").read_text(encoding="utf-8")
    assert "webkitSpeechRecognition" in js
    assert "keel_voice_consent" in js
    assert "window.confirm" in js
    assert "function startVoice" in js
    assert "function stopVoice" in js
    assert "voiceState.sendOnDone" in js  # Shift+hold sends as a task
    assert "Listening…" in js


def test_css_has_voice_styles():
    css = (ROOT / "site" / "ui" / "style.css").read_text(encoding="utf-8")
    assert ".mic" in css and ".voice-status" in css


def test_app_js_syntax():
    result = subprocess.run(["node", "--check", str(ROOT / "site" / "ui" / "app.js")],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
