"""B2.6 — local RAG knowledge bases over folders."""

from __future__ import annotations

from keel.rag import KnowledgeBase, chunk_text, tokenize


def test_chunking_has_overlap():
    chunks = chunk_text(" ".join(f"word{i}" for i in range(300)),
                        size=100, overlap=20)
    assert len(chunks) > 1
    assert "word99" in chunks[0]
    assert "word80" in chunks[1]  # overlap preserved


def test_tokenize_is_lowercase():
    assert tokenize("Hello, hello WORLD!") == {"hello": 2, "world": 1}


def test_index_and_search(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text(
        "Keel is a local-first AI workspace. It respects privacy and runs "
        "offline. The agent edits code with explicit permission.",
        encoding="utf-8")
    (docs / "other.txt").write_text("Gardening tips for tomatoes.",
                                    encoding="utf-8")
    (docs / ".hidden").mkdir()  # non-text dir ignored
    base = KnowledgeBase(str(tmp_path / "state"), "project")
    summary = base.index(docs)
    assert summary["files"] == 2 and summary["chunks"] >= 2
    hits = base.search("privacy offline workspace")
    assert hits
    assert hits[0]["source"].endswith("notes.md")
    assert "privacy" in hits[0]["text"].lower()


def test_empty_base_search():
    base = KnowledgeBase("/nonexistent-state-dir", "empty")
    assert base.search("anything") == []


def test_rag_tools_registered():
    import os

    os.environ.setdefault("KEEL_TOKEN", "x")
    from keel.tools.native import (NATIVE_TOOL_NAMES, NATIVE_TOOL_PERMISSIONS)

    assert "rag_index" in NATIVE_TOOL_NAMES
    assert "rag_search" in NATIVE_TOOL_NAMES
    assert NATIVE_TOOL_PERMISSIONS["rag_index"] == "write"
    assert NATIVE_TOOL_PERMISSIONS["rag_search"] == "read"


def test_multiple_named_bases(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("alpha content", encoding="utf-8")
    KnowledgeBase(str(tmp_path / "state"), "one").index(docs)
    KnowledgeBase(str(tmp_path / "state"), "two").index(docs)
    assert (tmp_path / "state" / "rag" / "one.json").is_file()
    assert (tmp_path / "state" / "rag" / "two.json").is_file()
