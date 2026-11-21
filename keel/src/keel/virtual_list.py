"""Virtualized list windowing and streaming backpressure (C9.2).

Given a large list and a scroll position, compute the visible slice plus an
overscan buffer so the UI renders only what is on screen. Also provides a
token-bucket backpressure helper to bound streaming update rates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Window:
    start: int
    end: int
    offset: int


def visible_window(total: int, scroll_top: int, viewport: int,
                   item_height: int, overscan: int = 5) -> Window:
    if item_height < 1 or viewport < 1:
        return Window(0, 0, 0)
    first = max(0, scroll_top // item_height - overscan)
    count = viewport // item_height + 2 * overscan + 1
    end = min(total, first + max(1, count))
    return Window(start=first, end=end, offset=first * item_height)


class Backpressure:
    """Token bucket that admits at most ``rate`` events per second."""

    def __init__(self, rate: float = 60.0, burst: int = 10):
        self.rate = max(0.1, float(rate))
        self.capacity = max(1, int(burst))
        self._tokens = float(self.capacity)
        self._last = time.monotonic()

    def allow(self, *, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        elapsed = max(0.0, current - self._last)
        self._last = current
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
