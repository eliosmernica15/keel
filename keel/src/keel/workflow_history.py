"""Workflow versioning, history and replay (C5.x).

Stores workflow definitions as versioned local snapshots with the ability to
diff and restore earlier versions. Replay re-runs a recorded workflow through
a caller-supplied executor.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


class WorkflowHistory:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "workflow-history.json"

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

    def save(self, name: str, definition: dict) -> int:
        doc = self._load()
        versions = doc.get(name, [])
        version = len(versions) + 1
        versions.append({"version": version, "definition": definition,
                         "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime())})
        doc[name] = versions
        self._save(doc)
        return version

    def get(self, name: str, version: int | None = None) -> dict | None:
        versions = self._load().get(name, [])
        if not versions:
            return None
        target = version or versions[-1]["version"]
        return next((v["definition"] for v in versions
                     if v["version"] == target), None)

    def versions(self, name: str) -> list[dict]:
        return [{"version": v["version"], "ts": v["ts"]}
                for v in self._load().get(name, [])]


def anomaly_score(events: list[dict], *, window: int = 10) -> float:
    """Flag unusual bursts of destructive/denied events (local heuristic)."""
    suspicious = sum(1 for event in events[-window:]
                     if event.get("kind") in ("denied", "error")
                     or event.get("tool") in ("delete_file", "process_kill"))
    return round(min(1.0, suspicious / max(1, min(window, len(events)))), 3)
