"""Automation: event bus, triggers, notifications (C5.4, C5.5, C5.6).

A tiny event bus with typed topics, file/git triggers, and notification rules
with quiet hours. All local; no external broker.

Persistence (C8 / connected-product repair): when a ``state_root`` is passed to
:class:`EventBus`, every published event is appended to
``<state_root>/eventbus.jsonl`` and the full history is reloaded on
construction. A fresh bus object -- or a fresh interpreter -- therefore sees
every earlier event. With no ``state_root`` the bus stays in-memory only, which
keeps the original single-process behaviour intact.

Anomaly detection in this module scores *actual* event payloads (repeated
denials / errors, destructive tools, mass file reads) from that persisted
history. The legacy static heuristic in :mod:`keel.workflow_history` remains
only as a documented fallback when there are no events at all to inspect.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EVENT_LOG = "eventbus.jsonl"

# Patterns inspected in real event payloads / topics.
DENIED_KINDS = frozenset({"denied", "error"})
DESTRUCTIVE_TOOLS = frozenset({"delete_file", "process_kill"})
READ_TOOLS = frozenset({"read_file", "file_read"})
MASS_READ_THRESHOLD = 20
MASS_READ_SCORE = 0.8


class EventBus:
    """Local publish/subscribe bus with optional JSONL persistence.

    ``state_root`` may be a ``str`` or :class:`~pathlib.Path`. When falsy
    (the default), nothing is written to disk and history is per-object.
    """

    def __init__(self, state_root=None, *, filename: str = DEFAULT_EVENT_LOG):
        self._subscribers: dict[str, list] = defaultdict(list)
        self.path = (Path(state_root) / filename) if state_root else None
        self.history: list[dict] = self._load() if self.path else []

    def _load(self) -> list[dict]:
        """Reload history from the JSONL log, tolerating missing/corrupt data."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return []
        events: list[dict] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    def _append(self, event: dict) -> None:
        """Append one event to the JSONL log (no-op for an in-memory bus)."""
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def subscribe(self, topic: str, handler) -> None:
        self._subscribers[topic].append(handler)

    def publish(self, topic: str, payload: dict) -> int:
        event = {"topic": topic, "payload": payload,
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.history.append(event)
        self._append(event)
        for handler in list(self._subscribers[topic]):
            handler(event)
        return len(self._subscribers[topic])

    def anomaly_score(self, events: list[dict] | None = None, *,
                      window: int = 10) -> float:
        """Score this bus's history, or *events* if explicitly supplied.

        When ``state_root`` was given, ``self.history`` is the persisted event
        log, so this is an honest reading of what actually happened.
        """
        return anomaly_score(events or self.history, window=window)


def _fields(event):
    """Return ``(topic, payload)`` for either a bus event or a raw event dict."""
    if not isinstance(event, dict):
        return "", {}
    topic = str(event.get("topic", ""))
    payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = event if "topic" not in event else {}
    return topic, payload


def anomaly_score(events: list[dict] | None = None, *, state_root=None,
                  window: int = 10) -> float:
    """Score real event patterns from an explicit list or persisted history.

    * With *events*, score those events directly (this preserves the legacy
      caller contract used by ``fleet.anomaly`` when the caller supplies a
      sequence).
    * With no events but a *state_root*, load ``EventBus(state_root).history``
      so detection consumes the events actually published by the fleet.
    * With neither, fall back to the legacy static heuristic from
      :func:`keel.workflow_history.anomaly_score` (an empty sequence scores
      ``0.0``). This is a documented fallback, not the primary path.
    """
    if not events and state_root:
        events = EventBus(state_root).history
    if not events:
        from .workflow_history import anomaly_score as _legacy_anomaly_score

        return _legacy_anomaly_score([], window=window)

    window = max(1, int(window))
    recent = list(events)[-window:]
    suspicious = 0
    for event in recent:
        topic, payload = _fields(event)
        kind = str(payload.get("kind", "")).lower()
        tool = str(payload.get("tool") or payload.get("name") or "").lower()
        if (kind in DENIED_KINDS or topic.endswith((".denied", ".error"))
                or payload.get("denied") is True):
            suspicious += 1
        if tool in DESTRUCTIVE_TOOLS:
            suspicious += 1

    score = min(1.0, suspicious / len(recent))

    # Mass file reads are counted over the whole history, not just the window.
    total_reads = 0
    for event in events:
        _, payload = _fields(event)
        tool = str(payload.get("tool") or payload.get("name") or "").lower()
        if tool in READ_TOOLS or str(payload.get("kind", "")).lower() == "file_read":
            total_reads += 1
    if total_reads > MASS_READ_THRESHOLD:
        score = max(score, MASS_READ_SCORE)
    return round(score, 3)


@dataclass
class Trigger:
    kind: str   # file | folder | git | schedule | clipboard
    value: str
    action: str


def match_trigger(trigger: Trigger, event: dict) -> bool:
    kind = event.get("trigger")
    if kind != trigger.kind:
        return False
    return trigger.value in str(event.get("path", event.get("value", "")))


class NotificationRules:
    def __init__(self, quiet_from: int = 22, quiet_to: int = 8):
        self.quiet_from = quiet_from
        self.quiet_to = quiet_to

    def is_quiet(self, hour: int) -> bool:
        if self.quiet_from > self.quiet_to:
            return hour >= self.quiet_from or hour < self.quiet_to
        return self.quiet_from <= hour < self.quiet_to

    def route(self, channel: str, severity: str) -> str:
        if severity == "critical":
            return "all"
        return channel
