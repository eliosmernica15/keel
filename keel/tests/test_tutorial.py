"""C10.1/C10.5 — tutorial and voice accessibility descriptors."""

from __future__ import annotations

from keel.tutorial import accessibility_descriptor, tutorial_state


def test_tutorial_progress():
    state = tutorial_state([])
    assert state["done"] == 0 and state["next"] == "welcome"
    state = tutorial_state(["welcome", "workspace"])
    assert state["done"] == 2 and state["next"] == "first_prompt"
    done = tutorial_state(["welcome", "workspace", "first_prompt", "verify"])
    assert done["finished"] is True and done["next"] is None


def test_accessibility_opt_in():
    assert accessibility_descriptor()["spoken_responses"] is False
    assert accessibility_descriptor(True)["spoken_responses"] is True
    assert accessibility_descriptor()["live_region"] == "polite"
