"""Visible task checklist for a Keel session (A1.10).

Stored locally under ``state_root/todos.json`` so the checklist survives
turns and restarts. No cloud dependency.
"""

from __future__ import annotations

import json
from pathlib import Path

VALID_STATUS = ("pending", "in_progress", "completed", "cancelled")
_MARK = {"pending": "[ ]", "in_progress": "[~]",
         "completed": "[x]", "cancelled": "[-]"}


class TodoStore:
    def __init__(self, state_root: str):
        self.path = Path(state_root) / "todos.json"

    def load(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = doc.get("items", doc if isinstance(doc, list) else [])
        return [item for item in items if isinstance(item, dict)][:50]

    def replace(self, items: list) -> list[dict]:
        cleaned = []
        for item in items[:50]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("text") or "").strip()
            if not content:
                continue
            status = str(item.get("status") or "pending")
            if status not in VALID_STATUS:
                status = "pending"
            cleaned.append({"content": content[:500], "status": status})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"items": cleaned}, indent=2) + "\n", encoding="utf-8")
        return cleaned


def render_todos(items: list[dict]) -> str:
    if not items:
        return "Task checklist is empty."
    lines = ["Task checklist:"]
    for index, item in enumerate(items):
        mark = _MARK.get(item.get("status"), "[ ]")
        lines.append(f"{index + 1}. {mark} {item['content']}")
    done = sum(1 for i in items if i.get("status") == "completed")
    lines.append(f"\n{done}/{len(items)} completed")
    return "\n".join(lines)
