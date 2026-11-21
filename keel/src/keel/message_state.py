"""Outbound message state machine (A5.5).

Tracks the lifecycle of messages sent to external channels: queued, sent,
delivered, read and failed. State is a local JSONL file; no external service
is required and no message content is stored.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

STATES = ("queued", "sent", "delivered", "read", "failed", "cancelled")
_TRANSITIONS = {
    "queued": {"sent", "failed", "cancelled"},
    "sent": {"delivered", "failed"},
    "delivered": {"read", "failed"},
    "read": set(),
    "failed": {"queued"},  # explicit retry
    "cancelled": set(),
}


class MessageStateError(RuntimeError):
    pass


def transition(current: str, target: str) -> str:
    if current not in STATES:
        raise MessageStateError(f"unknown state: {current}")
    if target not in STATES:
        raise MessageStateError(f"unknown state: {target}")
    if target not in _TRANSITIONS[current]:
        raise MessageStateError(f"illegal transition: {current} -> {target}")
    return target


class MessageStates:
    def __init__(self, state_root: str):
        self.path = Path(state_root) / "message-states.jsonl"

    def _records(self) -> list[dict]:
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out

    def _append(self, record: dict) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        return record

    def queue(self, *, channel: str, destination: str = "",
              size: int = 0) -> dict:
        return self._append({
            "id": uuid.uuid4().hex[:16],
            "state": "queued",
            "channel": channel,
            "destination": destination,
            "size": int(size),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def state(self, message_id: str) -> str | None:
        current = None
        for record in self._records():
            if record.get("id") == message_id:
                current = record.get("state")
        return current

    def advance(self, message_id: str, target: str) -> dict:
        current = self.state(message_id)
        if current is None:
            raise MessageStateError(f"unknown message: {message_id}")
        next_state = transition(current, target)
        return self._append({"id": message_id, "state": next_state,
                             "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime())})

    def history(self, message_id: str) -> list[dict]:
        return [record for record in self._records()
                if record.get("id") == message_id]
