"""Knowledge-work tools (B2.x): prompt library, spec mode, DB explorer, notebook.

Local descriptors and lightweight helpers; no external service is contacted.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path


class PromptLibrary:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "prompt-library.json"

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

    def add(self, name: str, template: str, variables: list[str]) -> dict:
        entry = {"name": name, "template": template,
                 "variables": list(variables)}
        doc = self._load()
        doc[name] = entry
        self._save(doc)
        return entry

    def render(self, name: str, values: dict) -> str:
        entry = self._load().get(name)
        if not entry:
            return ""
        text = entry["template"]
        for key, value in values.items():
            text = text.replace("{{" + key + "}}", str(value))
        return text


def spec_plan(goal: str) -> dict:
    """A spec-driven plan scaffold with an explicit approval gate."""
    return {"goal": goal, "steps": ["write spec", "break down tasks",
                                    "implement", "verify"],
            "approval_required": True}


def sqlite_tables(db_path: str | Path) -> list[str]:
    """Read-only listing of SQLite table names."""
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return [row[0] for row in rows]


def notebook_cells(source: str) -> list[dict]:
    """Split a simple markdown notebook into code/text cells."""
    cells = []
    for block in re.split(r"```(?:python)?\n(.*?)```", source, flags=re.S):
        if not block.strip():
            continue
        kind = "code" if block.strip().startswith((
            "import ", "print(", "def ", "x ")) else "text"
        cells.append({"kind": kind, "source": block.strip()})
    return cells
