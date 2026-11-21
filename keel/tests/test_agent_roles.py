"""C3.3/C3.5/C3.6/C3.7 — agent roles, map-reduce, reflection and goals."""

from __future__ import annotations

from keel.agent_roles import (map_reduce_chunks, overnight_checkpoint,
                              reflection_gate, role_prompt)


def test_role_prompts():
    assert "Do not execute" in role_prompt("planner")
    assert role_prompt("unknown")


def test_map_reduce_chunks_bounded():
    chunks = map_reduce_chunks(" ".join(f"w{i}" for i in range(100)), workers=3)
    assert len(chunks) <= 3
    assert " ".join(c for chunk in chunks for c in chunk.split()).split() == [
        f"w{i}" for i in range(100)]


def test_reflection_and_checkpoint():
    assert reflection_gate("lesson", approved=False)["stored"] is False
    assert reflection_gate("lesson", approved=True)["stored"] is True
    cp = overnight_checkpoint(1, 5, needs_approval=True)
    assert cp.approved is False and cp.note == "approval gate"
    assert overnight_checkpoint(2, 5).approved is True
