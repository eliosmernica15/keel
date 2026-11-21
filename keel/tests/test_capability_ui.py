"""Capability browser UI wired to the real backend endpoints."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def test_capability_ui_markup_present():
    html = (SITE / "app.html").read_text(encoding="utf-8")
    assert 'id="btn-caps"' in html
    assert 'id="caps-overlay"' in html
    assert 'id="caps-list"' in html
    assert 'id="caps-params"' in html
    assert 'id="caps-confirm"' in html
    assert 'id="caps-run"' in html


def test_capability_ui_uses_real_endpoints():
    js = (SITE / "ui" / "app.js").read_text(encoding="utf-8")
    assert "/api/capabilities/invoke" in js
    assert "loadCapabilities" in js
    assert "invokeCapability" in js
    assert "confirm:" in js


def test_js_syntax():
    result = subprocess.run(
        ["node", "--check", str(SITE / "ui" / "app.js")],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
