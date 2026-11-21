"""Provider circuit breaker with health scoring (B3.11).

Tracks per-provider outcomes locally. After a configurable number of
consecutive failures the breaker opens and calls fail fast; after a recovery
window a single probe is allowed through (half-open).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock, RLock


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    recovery_timeout: float = 60.0
    half_open_max: int = 1
    _failures: int = 0
    _total_failures: int = 0
    _successes: int = 0
    _total: int = 0
    _opened_at: float = 0.0
    _half_open_inflight: int = 0
    _lock: RLock = field(default_factory=RLock, repr=False)

    @property
    def state(self) -> str:
        with self._lock:
            if not self._opened_at:
                return "closed"
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                return "half_open"
            return "open"

    def allow(self) -> bool:
        with self._lock:
            if not self._opened_at:
                return True
            if time.monotonic() - self._opened_at < self.recovery_timeout:
                return False
            if self._half_open_inflight >= max(1, self.half_open_max):
                return False
            self._half_open_inflight += 1
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._opened_at:
                self._opened_at = 0.0
                self._failures = 0
                self._half_open_inflight = max(
                    0, self._half_open_inflight - 1)
            else:
                self._failures = 0
            self._successes += 1
            self._total += 1

    def record_failure(self) -> None:
        with self._lock:
            self._total += 1
            self._total_failures += 1
            if self._opened_at:
                # half-open probe failed: restart the recovery window
                self._opened_at = time.monotonic()
                self._half_open_inflight = max(
                    0, self._half_open_inflight - 1)
            else:
                self._failures += 1
                if self._failures >= max(1, self.failure_threshold):
                    self._opened_at = time.monotonic()

    def health_score(self) -> float:
        with self._lock:
            if not self._total:
                return 1.0
            return round(max(0.0, 1.0 - self._total_failures / self._total), 3)

    def snapshot(self) -> dict:
        with self._lock:
            state = ("closed" if not self._opened_at else
                     "half_open" if time.monotonic() - self._opened_at
                     >= self.recovery_timeout else "open")
            return {"name": self.name, "state": state,
                    "health": self.health_score(),
                    "failures": self._failures, "total": self._total}


_REGISTRY: dict[str, CircuitBreaker] = {}
_REGISTRY_LOCK = Lock()


def breaker_for(name: str) -> CircuitBreaker:
    key = str(name or "default")
    with _REGISTRY_LOCK:
        if key not in _REGISTRY:
            _REGISTRY[key] = CircuitBreaker(key)
        return _REGISTRY[key]


def all_breakers() -> list[dict]:
    with _REGISTRY_LOCK:
        return [breaker.snapshot() for breaker in _REGISTRY.values()]
