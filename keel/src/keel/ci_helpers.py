"""CI/test helpers (B7.3, B7.5, B7.9): flaky quarantine, kickoff prompts, gates."""

from __future__ import annotations

import json
import time
from pathlib import Path


class FlakyQuarantine:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "flaky-quarantine.json"

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

    def add(self, test: str, owner: str, *, days: int = 14) -> dict:
        entry = {"owner": owner, "expires": time.strftime(
            "%Y-%m-%d", time.gmtime(time.time() + days * 86400))}
        doc = self._load()
        doc[test] = entry
        self._save(doc)
        return entry

    def is_quarantined(self, test: str) -> bool:
        return test in self._load()


def kickoff_prompt(milestone: str) -> str:
    """B7.9: per-milestone builder prompt with an explicit stop condition."""
    return (f"Implement {milestone}. Work in small verified batches. "
            "Stop and report if an owner decision is required; never invent "
            "missing authoritative requirements.")


def accessibility_gate(results: dict) -> bool:
    """B7.3: pass only when no critical a11y violations are present."""
    return int(results.get("critical", 0)) == 0
