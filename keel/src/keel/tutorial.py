"""C10.1 — Interactive tutorial state, tips and "what's new" data.

Backs the UI guided tour with real persisted progress: steps are marked
complete, stored locally, and reported with accurate progress. Also exposes
contextual tips and an honest "what's new" record derived from the canonical
feature registry, so the UI never invents a success state. The voice
accessibility descriptors (C10.5) remain separate and unchanged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TUTORIAL_STEPS = [
    {"id": "welcome", "title": "Welcome to Keel",
     "text": "Keel is local-first. Your files stay on your machine.",
     "target": "#head-title", "hint": "This header shows the active product surface."},
    {"id": "workspace", "title": "Bind a workspace",
     "text": "Select a folder; tools run only inside it.",
     "target": "#chip-folder", "hint": "In Keel Code, choose the working folder here."},
    {"id": "first_prompt", "title": "Send a prompt",
     "text": "Ask a question or request a change; approve tool calls.",
     "target": "#prompt-chat", "hint": "Type your request and press Send."},
    {"id": "verify", "title": "Verify the result",
     "text": "Keel runs detected checks after edits; review the evidence.",
     "target": "#btn-caps", "hint": "Open Modules to inspect real local capabilities."},
]

TIPS = [
    {"id": "local_first", "title": "Local-first by design",
     "text": "No account is required. Data stays in this browser or your local Keel state."},
    {"id": "permissions", "title": "Approve consequential actions",
     "text": "Keel asks before changing files; you can switch permission modes in the footer."},
    {"id": "modules", "title": "Every module is inspectable",
     "text": "Ctrl+Shift+M opens the Modules browser with the real capability list."},
]

WHATS_NEW = [
    {"version": "0.1.1", "title": "Local workspace, real modules",
     "text": "Notebooks, spec-driven mode, offline doc packs, repository indexing "
             "and an honest status page are now available through Modules."},
    {"version": "0.1.0", "title": "First local release",
     "text": "Python-authoritative runtime, Electron shell and local HTTP bridge."},
]


def tutorial_state(completed: list[str] | None = None) -> dict:
    completed = set(completed or [])
    total = len(TUTORIAL_STEPS)
    done = sum(1 for step in TUTORIAL_STEPS if step["id"] in completed)
    return {"completed": sorted(completed), "total": total, "done": done,
            "finished": done == total,
            "next": next((s["id"] for s in TUTORIAL_STEPS
                          if s["id"] not in completed), None),
            "steps": [dict(s) for s in TUTORIAL_STEPS]}


class TutorialStore:
    """Persist guided-tour progress in local state (never in the mirror)."""

    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "tutorial-progress.json"

    def _load(self) -> list[str]:
        if not self.path.is_file():
            return []
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = doc.get("completed", []) if isinstance(doc, dict) else []
        valid = {s["id"] for s in TUTORIAL_STEPS}
        return [str(x) for x in items if x in valid] if isinstance(items, list) else []

    def _save(self, completed: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"completed": completed}, indent=2) + "\n",
            encoding="utf-8")

    def load(self) -> dict:
        return tutorial_state(self._load())

    def mark(self, step_id: str) -> dict:
        valid = {s["id"] for s in TUTORIAL_STEPS}
        if step_id not in valid:
            raise ValueError(f"unknown tutorial step: {step_id}")
        completed = set(self._load())
        completed.add(step_id)
        self._save(sorted(completed))
        return self.load()

    def reset(self) -> dict:
        self._save([])
        return self.load()


# C10.5 — voice accessibility descriptors (kept for backward compatibility).
VOICE_ACCESSIBILITY = {
    "announce_tool_calls": True,
    "live_region": "polite",
    "spoken_responses": False,  # opt-in in the UI
}


def accessibility_descriptor(enabled: bool = False) -> dict:
    desc = dict(VOICE_ACCESSIBILITY)
    desc["spoken_responses"] = bool(enabled)
    return desc


class AccessibilityStore:
    """Persist opt-in voice/accessibility settings in local state."""

    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "accessibility.json"

    def load(self) -> dict:
        base = dict(VOICE_ACCESSIBILITY)
        if self.path.is_file():
            try:
                doc = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(doc, dict):
                    base.update({k: doc[k] for k in base if k in doc})
            except (OSError, ValueError):
                pass
        base["stored"] = self.path.is_file()
        return base

    def save(self, settings: dict) -> dict:
        current = self.load()
        for key in VOICE_ACCESSIBILITY:
            if key in settings:
                if key == "live_region":
                    if settings[key] not in ("polite", "assertive", "off"):
                        raise ValueError("invalid live_region")
                    current[key] = settings[key]
                else:
                    current[key] = bool(settings[key])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({k: current[k] for k in VOICE_ACCESSIBILITY}, indent=2)
            + "\n", encoding="utf-8")
        return self.load()


def tips() -> list[dict]:
    return [dict(t) for t in TIPS]


def whats_new() -> dict:
    return {"version": WHATS_NEW[0]["version"], "items": [dict(x) for x in WHATS_NEW]}
