"""Performance budgets and measurement (B7.4).

Defines local budgets for cold start, idle memory, installer size and time to
first token, plus a checker that evaluates measured values against them. No
benchmark is run here; the caller supplies measurements.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BUDGETS = {
    "cold_start_ms": 3000,
    "idle_memory_mb": 200,
    "installer_size_mb": 200,
    "time_to_first_token_ms": 5000,
}


@dataclass
class BudgetCheck:
    name: str
    measured: float
    limit: float
    within: bool


def check(measurements: dict[str, float],
          budgets: dict[str, float] | None = None) -> list[BudgetCheck]:
    limits = budgets or DEFAULT_BUDGETS
    results = []
    for name, limit in limits.items():
        if name not in measurements:
            continue
        measured = float(measurements[name])
        results.append(BudgetCheck(
            name=name, measured=measured, limit=float(limit),
            within=measured <= float(limit)))
    return results


def all_within(results: list[BudgetCheck]) -> bool:
    return bool(results) and all(result.within for result in results)
