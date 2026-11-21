"""Agent profile layouts and management (B4.10/C1.6).

Full persistence of named work/personal profiles, each with its own data
directory, agent list, layout and active selection. Profiles are real state
the application reads and writes, not display-only descriptors.
"""

from __future__ import annotations

import json
from pathlib import Path

from .agent_style import style_for
from .surfaces import SURFACES


class AgentProfiles:
    def __init__(self, state_root: str | Path):
        self.root = Path(state_root)
        self.path = self.root / "agent-profiles.json"

    def _load(self) -> dict:
        if not self.path.is_file():
            return {"profiles": {}, "active": None}
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"profiles": {}, "active": None}
        doc.setdefault("profiles", {})
        doc.setdefault("active", None)
        return doc

    def _save(self, doc: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def create(self, name: str, *, agents: list[str] | None = None,
               layout: str = "split") -> dict:
        doc = self._load()
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_")[:64]
        profile = {
            "name": name,
            "data_dir": str(self.root / "profiles" / (safe or "default")),
            "agents": list(agents or ["cowork", "code"]),
            "layout": layout,
            "surface_defaults": {
                key: value["default_agent"] for key, value in SURFACES.items()},
        }
        doc["profiles"][name] = profile
        if doc["active"] is None:
            doc["active"] = name
        self._save(doc)
        Path(profile["data_dir"]).mkdir(parents=True, exist_ok=True)
        return profile

    def list(self) -> list[dict]:
        return list(self._load()["profiles"].values())

    def get(self, name: str) -> dict | None:
        return self._load()["profiles"].get(name)

    def activate(self, name: str) -> bool:
        doc = self._load()
        if name not in doc["profiles"]:
            return False
        doc["active"] = name
        self._save(doc)
        return True

    def active(self) -> dict | None:
        doc = self._load()
        return doc["profiles"].get(doc["active"]) if doc["active"] else None

    def agent_details(self, name: str) -> list[dict]:
        profile = self.get(name)
        if not profile:
            return []
        return [style_for(agent) for agent in profile["agents"]]

    def remove(self, name: str) -> bool:
        doc = self._load()
        if name not in doc["profiles"]:
            return False
        doc["profiles"].pop(name)
        if doc["active"] == name:
            doc["active"] = next(iter(doc["profiles"]), None)
        self._save(doc)
        return True
