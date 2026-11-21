"""B7.4 — performance budgets."""

from __future__ import annotations

from keel.performance_budgets import all_within, check


def test_within_budget():
    results = check({"cold_start_ms": 1500, "idle_memory_mb": 120})
    assert len(results) == 2
    assert all_within(results) is True


def test_over_budget_flagged():
    results = check({"cold_start_ms": 5000})
    assert results[0].within is False
    assert all_within(results) is False


def test_unknown_measurements_ignored():
    assert check({"unknown": 999999}) == []
