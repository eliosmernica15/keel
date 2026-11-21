"""Real local model runtime manager (C9.1 upgrade).

Tracks loaded models with an actual RAM budget and LRU eviction, and can
spawn a user-supplied local model command with resource bounds. No model is
downloaded or fetched here.
"""

from __future__ import annotations

import os
import subprocess
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class LoadedModel:
    name: str
    bytes_est: int
    command: str


class ModelRuntime:
    def __init__(self, budget_bytes: int):
        self.budget = max(1, budget_bytes)
        self.models: OrderedDict[str, LoadedModel] = OrderedDict()
        self.evicted: list[str] = []

    @property
    def used(self) -> int:
        return sum(model.bytes_est for model in self.models.values())

    def load(self, name: str, bytes_est: int, command: str = "") -> bool:
        entry = LoadedModel(name, max(0, bytes_est), command)
        if name in self.models:
            self.models.move_to_end(name)
            return True
        while self.used + entry.bytes_est > self.budget and self.models:
            evicted, _ = self.models.popitem(last=False)
            self.evicted.append(evicted)
        if self.used + entry.bytes_est > self.budget:
            return False
        self.models[name] = entry
        return True

    def touch(self, name: str) -> bool:
        if name not in self.models:
            return False
        self.models.move_to_end(name)
        return True

    def unload(self, name: str) -> bool:
        return self.models.pop(name, None) is not None

    def start(self, name: str, *, extra_args: list[str] | None = None) -> subprocess.Popen | None:
        """Opt-in launch of a user-supplied local model command."""
        entry = self.models.get(name)
        if not entry or not entry.command:
            return None
        import shlex
        args = shlex.split(entry.command) + list(extra_args or [])
        return subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)

    def status(self) -> dict:
        return {"loaded": list(self.models), "used_bytes": self.used,
                "budget_bytes": self.budget, "evicted": list(self.evicted)}
