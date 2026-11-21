"""Local model manager: load/unload idle models and budget resources (C9.1).

Tracks which local models are loaded with an idle timeout and a configurable
RAM/VRAM budget. Unloading is a local decision only — no model files are
deleted and no remote service is contacted.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class LoadedModel:
    name: str
    size_mb: int
    loaded_at: float
    last_used: float

    def idle_for(self, now: float | None = None) -> float:
        current = now if now is not None else time.monotonic()
        return max(0.0, current - self.last_used)


class ModelManager:
    def __init__(self, *, budget_mb: int = 4096, idle_timeout_s: float = 600.0):
        self.budget_mb = max(1, int(budget_mb))
        self.idle_timeout_s = max(1.0, float(idle_timeout_s))
        self._models: dict[str, LoadedModel] = {}
        self._lock = threading.RLock()
        self.unloaded: list[str] = []

    def load(self, name: str, size_mb: int, *, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        with self._lock:
            existing = self._models.get(name)
            if existing is not None:
                existing.last_used = current
                return True
            if self.total_mb + max(0, int(size_mb)) > self.budget_mb:
                self.unload_idle(now=current)
            if self.total_mb + max(0, int(size_mb)) > self.budget_mb:
                return False
            self._models[name] = LoadedModel(
                name=name, size_mb=max(0, int(size_mb)),
                loaded_at=current, last_used=current)
            return True

    def touch(self, name: str, *, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        with self._lock:
            model = self._models.get(name)
            if model is None:
                return False
            model.last_used = current
            return True

    def unload_idle(self, *, now: float | None = None) -> list[str]:
        current = now if now is not None else time.monotonic()
        removed = []
        with self._lock:
            for name, model in list(self._models.items()):
                if model.idle_for(current) >= self.idle_timeout_s:
                    self._models.pop(name, None)
                    self.unloaded.append(name)
                    removed.append(name)
        return removed

    def unload(self, name: str) -> bool:
        with self._lock:
            if self._models.pop(name, None) is None:
                return False
            self.unloaded.append(name)
            return True

    @property
    def total_mb(self) -> int:
        return sum(model.size_mb for model in self._models.values())

    def status(self, *, now: float | None = None) -> dict:
        current = now if now is not None else time.monotonic()
        with self._lock:
            return {
                "loaded": [{"name": m.name, "size_mb": m.size_mb,
                            "idle_s": round(m.idle_for(current), 2)}
                           for m in self._models.values()],
                "total_mb": self.total_mb,
                "budget_mb": self.budget_mb,
                "idle_timeout_s": self.idle_timeout_s,
                "unloaded": list(self.unloaded),
            }
