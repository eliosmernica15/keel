"""Per-feature resource caps and battery-aware mode (C9.3, C9.4).

Local meters for browser/LSP/container features and a low-power mode that
tightens budgets. No OS-level enforcement is claimed; these are advisory
limits the runtime and UI consult.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

DEFAULT_CAPS = {"browser": 4, "lsp": 2, "container": 2}
LOW_POWER_CAPS = {"browser": 1, "lsp": 1, "container": 0}


@dataclass
class Meter:
    feature: str
    used: int
    cap: int
    within: bool


class ResourceMeter:
    def __init__(self, low_power: bool = False):
        self.low_power = low_power
        self.caps = dict(LOW_POWER_CAPS if low_power else DEFAULT_CAPS)
        self._used: dict[str, int] = {key: 0 for key in self.caps}
        # The check-then-increment in acquire() must be atomic: without this
        # lock concurrent callers can both pass the cap check and over-issue.
        self._lock = threading.RLock()

    def acquire(self, feature: str) -> bool:
        with self._lock:
            cap = self.caps.get(feature, 0)
            used = self._used.get(feature, 0)
            if used >= cap:
                return False
            self._used[feature] = used + 1
            return True

    def release(self, feature: str) -> bool:
        with self._lock:
            if self._used.get(feature, 0) <= 0:
                return False
            self._used[feature] -= 1
            return True

    def meters(self) -> list[Meter]:
        with self._lock:
            return [Meter(feature=name, used=self._used.get(name, 0),
                          cap=cap, within=self._used.get(name, 0) <= cap)
                    for name, cap in self.caps.items()]

    def set_low_power(self, enabled: bool) -> None:
        with self._lock:
            self.low_power = enabled
            self.caps = dict(LOW_POWER_CAPS if enabled else DEFAULT_CAPS)
            for key in self.caps:
                self._used.setdefault(key, 0)
