"""Difficulty-based model routing (B1.3).

Chooses a model tier from cheap/local signals (prompt length, tool use,
whether verification is requested) before a provider call. No hosted router
is involved; the decision is a local function the caller applies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RoutingDecision:
    tier: str
    model: str
    reason: str


DEFAULT_TIERS = {
    "easy": "keel-fake-1",
    "medium": "local-medium",
    "hard": "local-large",
}


def estimate_difficulty(prompt: str, *, tool_count: int = 0,
                        needs_verification: bool = False) -> str:
    length = len(prompt or "")
    score = 0
    if length > 400:
        score += 1
    if length > 1500:
        score += 1
    if tool_count > 3:
        score += 1
    if needs_verification:
        score += 1
    if score >= 3:
        return "hard"
    if score >= 1:
        return "medium"
    return "easy"


def route(prompt: str, *, tool_count: int = 0,
          needs_verification: bool = False,
          tiers: dict[str, str] | None = None) -> RoutingDecision:
    tiers = tiers or DEFAULT_TIERS
    tier = estimate_difficulty(prompt, tool_count=tool_count,
                               needs_verification=needs_verification)
    model = tiers.get(tier) or tiers["easy"]
    return RoutingDecision(
        tier=tier, model=model,
        reason=f"difficulty={tier}, chars={len(prompt or '')}, tools={tool_count}")
