"""B1.3 — difficulty-based model routing."""

from __future__ import annotations

from keel.model_router import estimate_difficulty, route


def test_difficulty_scales():
    assert estimate_difficulty("hi") == "easy"
    assert estimate_difficulty("x" * 500) == "medium"
    assert estimate_difficulty("x" * 2000, tool_count=5,
                               needs_verification=True) == "hard"


def test_route_selects_model():
    easy = route("hi")
    hard = route("x" * 2000, tool_count=5, needs_verification=True)
    assert easy.tier == "easy" and easy.model == "keel-fake-1"
    assert hard.tier == "hard" and hard.model == "local-large"
    assert "difficulty" in hard.reason


def test_custom_tiers():
    decision = route("hi", tiers={"easy": "fast", "medium": "m", "hard": "h"})
    assert decision.model == "fast"
