"""Automation: event bus, triggers, notifications (C5.4, C5.5, C5.6).

A tiny in-process event bus with typed topics, file/git triggers, and
notification rules with quiet hours. All local; no external broker.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list] = defaultdict(list)
        self.history: list[dict] = []

    def subscribe(self, topic: str, handler) -> None:
        self._subscribers[topic].append(handler)

    def publish(self, topic: str, payload: dict) -> int:
        event = {"topic": topic, "payload": payload,
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.history.append(event)
        for handler in list(self._subscribers[topic]):
            handler(event)
        return len(self._subscribers[topic])


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
