"""Episodic, semantic and procedural memory types (C6.x).

Layered view over the existing local memory store: episodes (events), facts
(semantic) and procedures (how-to), with importance scoring and consolidation
of duplicate facts. All data stays local; no external embedding service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .memory import MemoryStore


@dataclass
class MemoryItem:
    kind: str
    content: str
    importance: float
    tags: list[str]


class TypedMemory:
    def __init__(self, store: MemoryStore):
        self.store = store

    def remember(self, kind: str, content: str, *, importance: float = 1.0,
                 tags: list[str] | None = None) -> dict:
        if kind not in ("episodic", "semantic", "procedural"):
            raise ValueError(f"unknown memory kind: {kind}")
        return self.store.add(
            content, source=f"memory:{kind}",
            tags=[kind, *(tags or [])])

    def recall_kind(self, kind: str, query: str = "") -> list[dict]:
        results = []
        for record in self.store.search(query, include_tainted=True):
            if kind in record.get("tags", []):
                results.append(record)
        return results

    @staticmethod
    def importance_decay(importance: float, days: float,
                         half_life: float = 30.0) -> float:
        if half_life <= 0:
            return importance
        return round(importance * (0.5 ** (days / half_life)), 4)

    def importance(self, record: dict, *, base: float = 1.0) -> float:
        """Score a memory by tag richness and trust (provenance-aware)."""
        score = base + 0.1 * min(5, len(record.get("tags", [])))
        if record.get("tainted"):
            score *= 0.5
        return round(score, 3)

    def dreaming(self) -> dict:
        """Consolidation pass: dedupe facts and report retained count."""
        removed = self.consolidate()
        return {"removed_duplicates": removed,
                "remaining": len(self.store.all_records())}

    def consolidate(self) -> int:
        """Remove exact-duplicate semantic facts; return count removed."""
        facts = self.recall_kind("semantic")
        seen: set[str] = set()
        duplicates: list[str] = []
        for record in facts:
            key = record["content"].strip().lower()
            if key in seen:
                duplicates.append(record["id"])
            else:
                seen.add(key)
        for record_id in duplicates:
            self.store.forget(record_id)
        return len(duplicates)
