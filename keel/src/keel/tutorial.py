"""Interactive tutorial scaffold (C10.1) and voice accessibility descriptors (C10.5)."""

from __future__ import annotations

TUTORIAL_STEPS = [
    {"id": "welcome", "title": "Welcome to Keel",
     "text": "Keel is local-first. Your files stay on your machine."},
    {"id": "workspace", "title": "Bind a workspace",
     "text": "Select a folder; tools run only inside it."},
    {"id": "first_prompt", "title": "Send a prompt",
     "text": "Ask a question or request a change; approve tool calls."},
    {"id": "verify", "title": "Verify the result",
     "text": "Keel runs detected checks after edits; review the evidence."},
]


def tutorial_state(completed: list[str] | None = None) -> dict:
    completed = set(completed or [])
    total = len(TUTORIAL_STEPS)
    done = sum(1 for step in TUTORIAL_STEPS if step["id"] in completed)
    return {"completed": sorted(completed), "total": total, "done": done,
            "finished": done == total,
            "next": next((s["id"] for s in TUTORIAL_STEPS
                          if s["id"] not in completed), None)}


VOICE_ACCESSIBILITY = {
    "announce_tool_calls": True,
    "live_region": "polite",
    "spoken_responses": False,  # opt-in in the UI
}


def accessibility_descriptor(enabled: bool = False) -> dict:
    desc = dict(VOICE_ACCESSIBILITY)
    desc["spoken_responses"] = bool(enabled)
    return desc
