"""Best-of-N candidate generation with test selection (C3.1).

Generates N candidate responses locally via a pluggable generator, scores each
with a selector function (e.g. a test-run result), and returns the best. No
extra provider calls beyond what the caller's generator makes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Candidate:
    index: int
    value: Any
    score: float = 0.0
    evidence: str = ""


def best_of_n(
    prompt: str,
    *,
    n: int = 3,
    generate: Callable[[str, int], Any],
    select: Callable[[Any], tuple[float, str]],
) -> Candidate:
    """Generate ``n`` candidates and pick the highest-scoring one.

    ``generate(prompt, index)`` returns a candidate value.
    ``select(value)`` returns ``(score, evidence)`` — e.g. from running tests.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    best: Candidate | None = None
    for index in range(n):
        value = generate(prompt, index)
        score, evidence = select(value)
        candidate = Candidate(index=index, value=value,
                              score=float(score), evidence=str(evidence))
        if best is None or candidate.score > best.score:
            best = candidate
    return best or Candidate(index=0, value=None, score=0.0)


def select_by_tests(run_tests: Callable[[Any], bool]) -> Callable[[Any], tuple[float, str]]:
    """Build a selector that scores 1.0 when tests pass, 0.0 otherwise."""
    def selector(value: Any) -> tuple[float, str]:
        ok = bool(run_tests(value))
        return (1.0, "tests passed") if ok else (0.0, "tests failed")
    return selector
