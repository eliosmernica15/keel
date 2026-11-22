"""Product labels must match the four-surface product vision."""

from __future__ import annotations

import subprocess
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"


def test_surface_labels_match_products():
    js = (SITE / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'chat: "Keel Cowork"' in js
    assert 'code: "Keel Code"' in js
    assert "Keel Desktop: upload" not in js


def test_desktop_ui_labels_match_products():
    """The real Electron UI tree must use the same product labels as the mirror."""
    desktop = Path(__file__).resolve().parents[1] / "desktop" / "ui"
    js = (desktop / "app.js").read_text(encoding="utf-8")
    html = (desktop / "index.html").read_text(encoding="utf-8")
    assert 'chat: "Keel Cowork"' in js
    assert "Keel Desktop: upload" not in js
    assert 'aria-label="Keel Cowork"' in html
    assert 'id="head-title">Keel Cowork<' in html


def test_aria_labels_match():
    html = (SITE / "app.html").read_text(encoding="utf-8")
    assert 'aria-label="Keel Cowork"' in html
    assert 'aria-label="Keel Code"' in html


def test_capability_browser_surface_filters_match_backend():
    """The UI filter options must use real backend surface values."""
    from keel import capability_registry  # noqa: F401 - registers all
    from keel.capabilities import list_capabilities

    surfaces = {c["surface"] for c in list_capabilities()}
    html = (SITE / "app.html").read_text(encoding="utf-8")
    for name in ("cowork", "code", "duet", "fleet", "core", "web",
                 "release", "external"):
        assert name in surfaces
        assert f'value="{name}"' in html


def test_js_syntax():
    result = subprocess.run(
        ["node", "--check", str(SITE / "ui" / "app.js")],
        cwd=SITE.parent, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
