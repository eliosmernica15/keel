"""Sandbox descriptors (B3.1, B3.2, B3.10).

The actual isolation is provided by the user's environment (WASM runtime,
optional container tool, OS lock screen). These local descriptors record the
requested limits so the runtime/UI can show them and refuse out-of-policy
requests. No sandbox is silently weaker than declared.
"""

from __future__ import annotations

import time


def wasm_sandbox(code: str, *, fuel: int = 1000000) -> dict:
    return {"runtime": "wasm", "code_bytes": len(code), "fuel": fuel,
            "network": False, "filesystem": False,
            "note": "No host I/O; caller must run in a real WASM runtime."}


def container_sandbox(image: str, *, cpus: float = 1.0, memory_mb: int = 512,
                      timeout_s: int = 60, network: bool = False) -> dict:
    if cpus <= 0 or memory_mb <= 0 or timeout_s <= 0:
        raise ValueError("sandbox limits must be positive")
    return {"image": image, "cpus": cpus, "memory_mb": memory_mb,
            "timeout_s": timeout_s, "network": network,
            "optional": True, "note": "Requires user-installed container runtime."}


class AppLock:
    def __init__(self, *, idle_s: int = 300):
        self.idle_s = max(1, int(idle_s))
        self._last = time.monotonic()
        self.locked = False
        self.passphrase_set = False

    def set_passphrase(self) -> None:
        self.passphrase_set = True

    def touch(self, *, now: float | None = None) -> None:
        self._last = now if now is not None else time.monotonic()
        self.locked = False

    def maybe_lock(self, *, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        if current - self._last >= self.idle_s:
            self.locked = True
        return self.locked
