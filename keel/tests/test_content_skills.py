"""C1.8/C1.9/C1.10 — draft-only skills, backlinks, plugin presets."""

from __future__ import annotations

from keel.content_skills import DraftStore, backlinks, preset_plugins


def test_drafts_are_never_published(tmp_path):
    store = DraftStore(tmp_path)
    draft = store.create("post", "Hello world")
    assert draft["published"] is False and draft["status"] == "draft"
    assert store.never_published() is True
    assert len(store.list()) == 1


def test_backlinks():
    graph = backlinks({"a": "see [[b]] and [[c]]", "b": "see [[a]]"})
    assert graph["b"] == ["a"]
    assert graph["a"] == ["b"]


def test_plugin_presets():
    assert "filesystem" in preset_plugins("essentials")
    assert preset_plugins("unknown") == []
