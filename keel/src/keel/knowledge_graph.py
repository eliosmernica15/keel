"""Entity/relation knowledge graph (C6.2).

A small local graph stored as JSON: entities with typed relations to other
entities. It complements the flat memory store without any external database.
"""

from __future__ import annotations

import json
from pathlib import Path


class KnowledgeGraph:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "knowledge-graph.json"

    def _load(self) -> dict:
        if not self.path.is_file():
            return {"entities": {}, "relations": []}
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"entities": {}, "relations": []}
        doc.setdefault("entities", {})
        doc.setdefault("relations", [])
        return doc

    def _save(self, doc: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def add_entity(self, name: str, kind: str = "concept") -> dict:
        doc = self._load()
        entity = {"name": name, "kind": kind}
        doc["entities"][name] = entity
        self._save(doc)
        return entity

    def relate(self, source: str, relation: str, target: str) -> bool:
        doc = self._load()
        if source not in doc["entities"] or target not in doc["entities"]:
            return False
        doc["relations"].append({"source": source, "relation": relation,
                                 "target": target})
        self._save(doc)
        return True

    def neighbors(self, name: str) -> list[dict]:
        doc = self._load()
        return [rel for rel in doc["relations"]
                if rel["source"] == name or rel["target"] == name]

    def entities(self) -> list[dict]:
        return list(self._load()["entities"].values())
