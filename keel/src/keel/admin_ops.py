"""Idle suspend, daily digest, tunables and config reference (A2.x).

Local descriptors and state helpers for background resource management and
operator-facing settings. Nothing here starts a service without the caller.
"""

from __future__ import annotations

import time

# A2.7: every setting with a short description and default (config reference).
CONFIG_REFERENCE = {
    "KEEL_TOKEN": ("Bridge auth token", "auto"),
    "KEEL_STATE_DIR": ("Where local state lives", "~/.keel"),
    "KEEL_TRASH_DIR": ("Recoverable trash location", "state/trash"),
    "KEEL_EGRESS_ALLOWLIST": ("Comma-separated allowed egress hosts", ""),
    "KEEL_OUTPUT_DLP": ("Block secrets in written files", "1"),
    "KEEL_SPECULATIVE_DECODING": ("Opt-in speculative decoding", "0"),
    "KEEL_ROLLOUT_MODE": ("Update rollout mode", "full"),
}

# A2.9: tunables for memory consolidation and compaction.
DEFAULT_TUNABLES = {"memory_half_life_days": 30,
                    "compaction_threshold": 0.65,
                    "checkpoint_interval": 10}


class IdleSuspend:
    def __init__(self, timeout_s: float = 300):
        self.timeout_s = max(1.0, float(timeout_s))
        self._last_active = time.monotonic()
        self.suspended = False

    def touch(self, *, now: float | None = None) -> None:
        current = now if now is not None else time.monotonic()
        self._last_active = current
        self.suspended = False

    def maybe_suspend(self, *, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        if current - self._last_active >= self.timeout_s:
            self.suspended = True
        return self.suspended


def daily_digest(events: list[dict]) -> dict:
    kinds: dict[str, int] = {}
    for event in events:
        key = event.get("kind") or event.get("subtype") or "other"
        kinds[str(key)] = kinds.get(str(key), 0) + 1
    return {"date": time.strftime("%Y-%m-%d"), "counts": kinds}
