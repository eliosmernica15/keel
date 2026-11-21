"""C3.12 — context packs and budget UI."""

from __future__ import annotations

from keel.context_packs import ContextPackStore


def test_define_and_render(tmp_path):
    (tmp_path / "a.md").write_text("hello world", encoding="utf-8")
    store = ContextPackStore(tmp_path)
    pack = store.define("docs", [str(tmp_path / "a.md")], budget=1000)
    assert pack["name"] == "docs" and len(store.list()) == 1
    rendered = store.render("docs")
    assert "hello world" in rendered and "a.md" in rendered


def test_budget_status(tmp_path):
    (tmp_path / "a.md").write_text("x" * 100, encoding="utf-8")
    store = ContextPackStore(tmp_path)
    store.define("small", [str(tmp_path / "a.md")], budget=100)
    status = store.budget_status("small")
    assert status["budget"] == 100 and status["used"] >= 0
    assert store.budget_status("missing") == {}
