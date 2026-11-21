"""Prefix/KV-cache reuse and speculative-decoding toggle (B1.4, B1.10).

Both are local helpers a runtime can consult before a model call: a prefix
cache that finds the longest shared prompt prefix, and an opt-in speculative
decoding flag that is off by default and only reports support.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class CacheHit:
    length: int
    text: str


class PrefixCache:
    def __init__(self, max_entries: int = 64, max_chars: int = 200_000):
        self.max_entries = max(1, max_entries)
        self.max_chars = max(0, max_chars)
        self._entries: list[str] = []

    def longest_prefix(self, prompt: str) -> CacheHit:
        best = ""
        for entry in self._entries:
            if not (entry and prompt) :
                continue
            limit = min(len(entry), len(prompt))
            count = 0
            while count < limit and entry[count] == prompt[count]:
                count += 1
            if count > len(best):
                best = prompt[:count]
        return CacheHit(length=len(best), text=best)

    def store(self, prompt: str) -> None:
        if not prompt or len(prompt) > self.max_chars:
            return
        if prompt in self._entries:
            self._entries.remove(prompt)
        self._entries.append(prompt)
        while len(self._entries) > self.max_entries:
            self._entries.pop(0)

    def clear(self) -> None:
        self._entries.clear()


def speculative_enabled() -> bool:
    raw = os.environ.get("KEEL_SPECULATIVE_DECODING", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}
