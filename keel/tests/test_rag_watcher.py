"""B2.6 + C5.4 — RAG auto-indexing on file changes."""

from __future__ import annotations

import time

from keel.rag_watcher import RagAutoIndex


def test_manual_reindex(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("local first workspace", encoding="utf-8")
    indexer = RagAutoIndex(tmp_path, docs, "auto")
    result = indexer.reindex()
    assert result["files"] == 1 and indexer.reindex_count == 1
    assert indexer.search("local")  # index is searchable


def test_background_auto_reindex(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("initial content", encoding="utf-8")
    indexer = RagAutoIndex(tmp_path, docs, "auto", interval=0.02)
    indexer.start(debounce_s=0.1)
    try:
        time.sleep(0.3)
        assert indexer.reindex_count >= 1
        (docs / "b.md").write_text("new searchable keyword", encoding="utf-8")
        deadline = time.time() + 3
        while time.time() < deadline and indexer.reindex_count < 2:
            time.sleep(0.05)
        assert indexer.reindex_count >= 2
        assert any("searchable" in h["text"] for h in indexer.search("keyword"))
    finally:
        indexer.stop()
