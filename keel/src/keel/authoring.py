"""Local authoring helpers: macro recording, prompt improvement, spec scaffolding.

All operations are deterministic, local, and produce reusable artifacts without
any external service.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def record_macro(name: str, transcript: list[dict]) -> dict:
    """Extract successful tool calls from a transcript into a reusable macro."""
    steps = []
    for entry in transcript:
        if entry.get("type") != "assistant":
            continue
        for block in entry.get("message", {}).get("content", []):
            if block.get("type") == "tool_use" and not block.get("is_error"):
                steps.append({"tool": block.get("name"),
                              "input": block.get("input", {})})
    return {"name": name, "steps": steps[:50],
            "note": "review before replaying; tool inputs are recorded verbatim"}


def save_macro(macro: dict, state_root: str | Path) -> Path:
    root = Path(state_root)
    path = root / "macros.json"
    items = []
    if path.is_file():
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            items = []
    if not isinstance(items, list):
        items = []
    items = [item for item in items if item.get("name") != macro["name"]]
    items.append(macro)
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
    return path


def improve_prompt(text: str) -> dict:
    """Suggest concrete local improvements to a prompt."""
    suggestions = []
    if len(text.strip()) < 20:
        suggestions.append("Add more context about the desired outcome")
    if not re.search(r"\b(test|verify|check)\b", text, re.I):
        suggestions.append("State how success should be verified")
    if "example" not in text.lower():
        suggestions.append("Include an example of the expected output")
    if not re.search(r"\b(do not|don't|avoid)\b", text, re.I):
        suggestions.append("Name constraints or things to avoid")
    return {"original": text, "suggestions": suggestions,
            "improved": (text.strip() + "\n\nVerify with tests and report evidence."
                         if suggestions else text)}


def spec_scaffold(goal: str) -> dict:
    """Spec-driven scaffold: spec, task breakdown, implement, verify."""
    return {
        "goal": goal,
        "spec": {"problem": goal, "requirements": [], "out_of_scope": []},
        "tasks": ["write spec", "break down tasks", "implement", "verify"],
        "approval_gate": True,
    }
