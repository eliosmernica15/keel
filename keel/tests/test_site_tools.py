"""B5.x/B4.2 — site helpers and deep links."""

from __future__ import annotations

from keel.site_tools import build_docs_index, parse_deep_link, status_page


def test_docs_index(tmp_path):
    (tmp_path / "guide.md").write_text("# Guide\nlocal first offline",
                                        encoding="utf-8")
    index = build_docs_index(tmp_path)
    assert index["format"] == "keel-docs-index-v1"
    assert "offline" in index["entries"][0]["words"]


def test_status_page():
    page = status_page(True, False)
    assert page["update_feed"] == "operational"
    assert page["mirrors"] == "degraded"


def test_deep_link():
    link = parse_deep_link("keel://open?path=C%3A%2Fwork")
    assert link["action"] == "open" and "path" in link["params"]
    assert parse_deep_link("https://x.test") is None
