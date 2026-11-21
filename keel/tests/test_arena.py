"""B1.9 — compare mode (arena)."""

from __future__ import annotations

import pytest

from keel.arena import compare, to_dict


def test_compare_collects_both_candidates():
    result = compare("hello", generators=[lambda p: "A", lambda p: "B"])
    assert [c["output"] for c in result.candidates] == ["A", "B"]
    assert result.winner is None


def test_judge_selects_winner():
    result = compare("q", generators=[lambda p: "short", lambda p: "a much longer answer"],
                     judge=lambda p, a, b: 1 if len(b) > len(a) else 0)
    assert result.winner == 1
    assert to_dict(result)["winner"] == 1


def test_needs_two_generators():
    with pytest.raises(ValueError):
        compare("x", generators=[lambda p: "only"])
