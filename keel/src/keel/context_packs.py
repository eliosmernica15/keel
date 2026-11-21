"""Context packs and budget UI descriptors (C3.12).

A context pack is a named, reusable set of files/notes with a token budget.
Packs are stored locally and resolved to text for injection on demand.
"""

from __future__ import annotations

import json
from pathlib import Path

from .context import estimate_tokens


class ContextPackStore:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "context-packs.json"

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def _save(self, doc: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def define(self, name: str, files: list[str], *, budget: int = 8000) -> dict:
        entry = {"name": name, "files": list(files)[:100],
                 "budget": max(100, int(budget))}
        doc = self._load()
        doc[name] = entry
        self._save(doc)
        return entry

    def list(self) -> list[dict]:
        return list(self._load().values())

    def render(self, name: str) -> str:
        entry = self._load().get(name)
        if not entry:
            return ""
        parts = []
        used = 0
        for file in entry.get("files", []):
            path = Path(file)
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if used + estimate_tokens([{"content": text}]) > entry["budget"]:
                break
            parts.append(f"### {file}\n{text}")
            used += estimate_tokens([{"content": text}])
        return "\n\n".join(parts)

    def budget_status(self, name: str) -> dict:
        entry = self._load().get(name)
        if not entry:
            return {}
        rendered = self.render(name)
        used = estimate_tokens([{"content": rendered}])
        return {"name": name, "used": used, "budget": entry["budget"],
                "remaining": max(0, entry["budget"] - used)}
