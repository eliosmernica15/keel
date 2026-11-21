"""C3.1 — best-of-N with test selection."""

from __future__ import annotations

import pytest

from keel.best_of_n import Candidate, best_of_n, select_by_tests


def test_picks_highest_scoring_candidate():
    values = ["bad", "good", "best"]
    scores = {"bad": 0.1, "good": 0.5, "best": 0.9}
    result = best_of_n(
        "task", n=3,
        generate=lambda prompt, i: values[i],
        select=lambda value: (scores[value], f"score {scores[value]}"))
    assert result.value == "best"
    assert result.score == 0.9
    assert "0.9" in result.evidence


def test_test_selector():
    selector = select_by_tests(lambda value: value == "passing")
    result = best_of_n(
        "task", n=3,
        generate=lambda p, i: ["failing", "passing", "also-failing"][i],
        select=selector)
    assert result.value == "passing"
    assert result.evidence == "tests passed"


def test_ties_keep_first():
    result = best_of_n("t", n=3, generate=lambda p, i: i,
                       select=lambda v: (1.0, "tie"))
    assert result.index == 0


def test_invalid_n():
    with pytest.raises(ValueError):
        best_of_n("t", n=0, generate=lambda p, i: i, select=lambda v: (0, ""))
