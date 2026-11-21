"""Feature-flag registry with kill-switch config (B7.8)."""

from __future__ import annotations

import json
from pathlib import Path


class FeatureFlags:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "feature-flags.json"

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

    def enabled(self, name: str, default: bool = False) -> bool:
        entry = self._load().get(name)
        if not isinstance(entry, dict):
            return default
        return bool(entry.get("enabled", default))

    def set(self, name: str, enabled: bool, *, kill_switch: bool = False) -> dict:
        doc = self._load()
        doc[name] = {"enabled": bool(enabled), "kill_switch": bool(kill_switch)}
        self._save(doc)
        return doc[name]

    def all(self) -> dict:
        return self._load()
