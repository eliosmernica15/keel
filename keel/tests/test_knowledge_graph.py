"""C6.2 — local knowledge graph."""

from __future__ import annotations

from keel.knowledge_graph import KnowledgeGraph


def test_entities_and_relations(tmp_path):
    graph = KnowledgeGraph(tmp_path)
    graph.add_entity("Keel", "product")
    graph.add_entity("local-first", "concept")
    assert graph.relate("Keel", "is", "local-first") is True
    assert graph.relate("missing", "is", "Keel") is False
    assert len(graph.neighbors("Keel")) == 1
    assert len(graph.entities()) == 2


def test_persistence(tmp_path):
    KnowledgeGraph(tmp_path).add_entity("persisted")
    assert "persisted" in [e["name"] for e in KnowledgeGraph(tmp_path).entities()]
