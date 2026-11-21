"""B1.8 — local embeddings and reranker."""

from __future__ import annotations

import math

from keel.embeddings import embed, rerank, similarity


def test_embed_normalized():
    vector = embed("hello world hello")
    assert len(vector) == 128
    assert abs(math.sqrt(sum(v * v for v in vector)) - 1.0) < 1e-3


def test_similarity_and_rerank():
    query = "local first workspace"
    docs = ["Keel is a local-first AI workspace",
            "recipe for pancakes", "another local tool"]
    ranked = rerank(query, docs, limit=3)
    assert ranked[0]["index"] == 0
    assert similarity(embed(query), embed(query)) > 0.99
