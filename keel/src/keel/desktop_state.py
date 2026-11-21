"""Desktop layout and profile helpers (B4.x).

Local descriptors for saved workspace layouts, multiple profiles, quick-ask,
and conversation organisation. No Electron code is required here; these are
the data shapes the desktop shell persists.
"""

from __future__ import annotations

import json
from pathlib import Path


class DesktopState:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "desktop-state.json"

    def _load(self) -> dict:
        if not self.path.is_file():
            return {"layouts": {}, "profiles": {}, "conversations": {}}
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"layouts": {}, "profiles": {}, "conversations": {}}
        for key in ("layouts", "profiles", "conversations"):
            doc.setdefault(key, {})
        return doc

    def _save(self, doc: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def save_layout(self, name: str, panels: list[dict]) -> dict:
        doc = self._load()
        entry = {"name": name, "panels": panels[:20]}
        doc["layouts"][name] = entry
        self._save(doc)
        return entry

    def profile(self, name: str) -> dict:
        doc = self._load()
        if name not in doc["profiles"]:
            doc["profiles"][name] = {"name": name, "data_dir": f"profiles/{name}"}
            self._save(doc)
        return doc["profiles"][name]

    def tag_conversation(self, conv_id: str, tags: list[str]) -> dict:
        doc = self._load()
        entry = doc["conversations"].get(conv_id, {"id": conv_id, "tags": []})
        entry["tags"] = list(tags)[:20]
        doc["conversations"][conv_id] = entry
        self._save(doc)
        return entry


def quick_ask_descriptor() -> dict:
    return {"hotkey": "Ctrl+Shift+K", "overlay": True,
            "note": "Send a prompt without switching windows"}
