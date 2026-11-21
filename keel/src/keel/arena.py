"""Compare mode / arena (B1.9).

Runs a prompt through two candidate generators locally, collects both outputs
and a preference, and records a comparison. No provider is contacted by this
module; the caller supplies both generators.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class Comparison:
    prompt: str
    candidates: list[dict]
    winner: int | None
    decided_at: str


def compare(prompt: str, *, generators: list[Callable[[str], str]],
            judge: Callable[[str, str, str], int] | None = None) -> Comparison:
    if len(generators) < 2:
        raise ValueError("arena needs at least two generators")
    outputs = [gen(prompt) for gen in generators]
    candidates = [{"index": i, "output": text} for i, text in enumerate(outputs)]
    winner = None
    if judge is not None:
        winner = judge(prompt, outputs[0], outputs[1])
        if winner not in (0, 1):
            winner = None
    return Comparison(
        prompt=prompt, candidates=candidates, winner=winner,
        decided_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


def to_dict(comparison: Comparison) -> dict:
    return {
        "prompt": comparison.prompt,
        "candidates": comparison.candidates,
        "winner": comparison.winner,
        "decided_at": comparison.decided_at,
    }
