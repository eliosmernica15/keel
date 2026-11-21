"""Local embeddings and reranker (B1.8).

Deterministic bag-of-words hashing embeddings with cosine similarity and a
simple reranker. No model download or hosted embedding API is required.
"""

from __future__ import annotations

import hashlib
import math
import re

_WORD = re.compile(r"[a-zA-Z0-9_]+")


def embed(text: str, dims: int = 128) -> list[float]:
    vector = [0.0] * max(8, dims)
    for word in _WORD.findall((text or "").lower()):
        slot = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % len(vector)
        vector[slot] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]


def similarity(a: list[float], b: list[float]) -> float:
    return round(sum(x * y for x, y in zip(a, b)), 6)


def rerank(query: str, documents: list[str], *, limit: int = 5) -> list[dict]:
    q = embed(query)
    scored = [{"index": i, "text": doc[:500],
               "score": similarity(q, embed(doc))}
              for i, doc in enumerate(documents)]
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:max(1, limit)]
