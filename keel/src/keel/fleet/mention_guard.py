"""Group-chat loop guards (A2.5).

Bounds agent-to-agent @mentions inside a single Fleet group round so two
members cannot keep re-triggering each other. Counts are per round and reset
when a new round starts.
"""

from __future__ import annotations

import re
from collections import Counter

MENTION_RE = re.compile(r"@([A-Za-z0-9][A-Za-z0-9_-]{1,63})")


def extract_mentions(text: str) -> list[str]:
    return [match.lower() for match in MENTION_RE.findall(text or "")]


class MentionGuard:
    def __init__(self, *, max_per_pair: int = 2, max_per_round: int = 8):
        self.max_per_pair = max(1, max_per_pair)
        self.max_per_round = max(1, max_per_round)
        self.pairs: Counter = Counter()
        self.total = 0

    def check(self, author: str, text: str) -> list[str]:
        """Return the mention targets that must be suppressed."""
        blocked: list[str] = []
        author_key = (author or "").lower()
        for target in extract_mentions(text):
            if target == author_key:
                continue
            key = (author_key, target)
            if self.pairs[key] >= self.max_per_pair or self.total >= self.max_per_round:
                blocked.append(target)
                continue
            self.pairs[key] += 1
            self.total += 1
        return blocked
