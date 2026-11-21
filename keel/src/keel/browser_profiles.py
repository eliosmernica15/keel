"""Persistent per-agent browser profiles and workspace folders (A2.3).

Manages isolated local directories per agent so each agent's browser state and
workspace stay separate. No browser is launched here — profiles aredata-only
scaffolding the desktop shell can use.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(name))[:64] or "agent"


class BrowserProfiles:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.index_path = self.root / "profiles.json"

    def _load(self) -> dict:
        if not self.index_path.is_file():
            return {}
        try:
            doc = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def _save(self, doc: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(doc, indent=2) + "\n",
                                   encoding="utf-8")

    def profile(self, agent_id: str) -> dict:
        key = _safe(agent_id)
        doc = self._load()
        entry = doc.get(key)
        if entry is None:
            profile_dir = self.root / "profiles" / key
            workspace = self.root / "workspaces" / key
            profile_dir.mkdir(parents=True, exist_ok=True)
            workspace.mkdir(parents=True, exist_ok=True)
            entry = {"agent": agent_id, "profile_dir": str(profile_dir),
                     "workspace": str(workspace)}
            doc[key] = entry
            self._save(doc)
        return entry

    def list_profiles(self) -> list[dict]:
        return list(self._load().values())

    def reset(self, agent_id: str) -> bool:
        doc = self._load()
        if _safe(agent_id) not in doc:
            return False
        del doc[_safe(agent_id)]
        self._save(doc)
        return True
