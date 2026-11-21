"""Draft-only social/content skills (C1.10) and notes vault extras (C1.8).

Drafts are stored locally and explicitly marked as never auto-published.
Notes support backlinks and templates without a hosted service.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


class DraftStore:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "content-drafts.json"

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

    def create(self, kind: str, text: str) -> dict:
        entry = {"id": f"draft-{int(time.time() * 1000)}",
                 "kind": kind, "text": str(text)[:10000],
                 "status": "draft", "published": False}
        doc = self._load()
        doc[entry["id"]] = entry
        self._save(doc)
        return entry

    def list(self) -> list[dict]:
        return list(self._load().values())

    def never_published(self) -> bool:
        return all(not entry.get("published") for entry in self.list())


def backlinks(notes: dict[str, str]) -> dict[str, list[str]]:
    """Map note names to the notes that reference them via [[wiki links]]."""
    import re

    result: dict[str, list[str]] = {}
    for source, text in notes.items():
        for target in re.findall(r"\[\[([^\]]+)\]\]", text):
            result.setdefault(target, []).append(source)
    return result


PLUGIN_PRESETS = {
    "essentials": ["filesystem", "git", "memory"],
    "research": ["web", "fetch", "pdf", "notes"],
    "coding": ["lsp", "terminal", "test", "review"],
}


def preset_plugins(name: str) -> list[str]:
    return list(PLUGIN_PRESETS.get(name, []))
