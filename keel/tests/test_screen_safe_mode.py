"""C1.4 screen-share / recording safe mode static integration checks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "site" / "ui" / "app.js"
CSS = ROOT / "site" / "ui" / "style.css"
HTML = ROOT / "site" / "app.html"


def test_safe_screen_toggle_is_wired():
    js = UI.read_text(encoding="utf-8")
    assert "function setSafeScreen" in js
    assert 'window.__keelSetSafeScreen = setSafeScreen' in js
    assert "Ctrl" in js and "shiftKey" in js
    assert "safe-screen" in js


def test_sensitive_fields_are_marked():
    js = UI.read_text(encoding="utf-8")
    assert "data-sensitive" in js
    assert "provider-src" in js


def test_css_masks_sensitive_data():
    css = CSS.read_text(encoding="utf-8")
    assert "body.safe-screen" in css
    assert "[data-sensitive]" in css


def test_badge_present():
    html = HTML.read_text(encoding="utf-8")
    assert 'class="safe-mode-badge"' in html
