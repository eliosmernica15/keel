"""Agent roles and goal modes (C3.3, C3.5, C3.6, C3.7).

Local orchestration descriptors: planner/critic/executor prompts, a bounded
map-reduce split, reflection gated on approval, and overnight goal checkpoints.
No provider call happens here; the caller drives the actual turns.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE_PROMPTS = {
    "planner": "Break the goal into ordered, testable steps. Do not execute.",
    "critic": "Review the plan for risks and missing steps. Cite concerns.",
    "executor": "Carry out the approved step and verify the result.",
}


def role_prompt(role: str) -> str:
    return ROLE_PROMPTS.get(role, "Proceed carefully and report evidence.")


@dataclass
class GoalCheckpoint:
    step: int
    total: int
    approved: bool = False
    note: str = ""


def map_reduce_chunks(text: str, workers: int = 3) -> list[str]:
    """Split text into balanced chunks for a map-reduce refactor."""
    words = (text or "").split()
    workers = max(1, min(8, workers))
    size = max(1, (len(words) + workers - 1) // workers)
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def reflection_gate(reflection: str, *, approved: bool) -> dict:
    """Reflection only becomes memory when the operator approves it."""
    return {"reflection": reflection, "approved": approved,
            "stored": bool(approved)}


def overnight_checkpoint(step: int, total: int, *, needs_approval: bool = False) -> GoalCheckpoint:
    return GoalCheckpoint(step=step, total=total,
                          approved=not needs_approval,
                          note="approval gate" if needs_approval else "auto")
