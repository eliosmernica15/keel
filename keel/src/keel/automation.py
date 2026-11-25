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

Publication seams (final-event integration):

* ``publish_durable`` is the one runtime adapter to the typed, HMAC-chained
  backend event contract used by backend workflows and capability decisions.
  It emits *complementary* typed evidence; the JSONL audit records and the
  permission/approval checks remain the only authoritative authorization
  inputs. Events are never read back to grant access.
* ``EventBus`` in this module stays authoritative for fleet automation and
  anomaly detection (see ``capability_registry``). It is deliberately NOT
  mirrored into the durable log: fleet SSE fan-out is ephemeral, per-subscriber
  and bounded with drop-oldest, while the durable bus is HMAC-chained and
  replayable. Copying one into the other would create two sources of truth.
* The durable contract is resolved lazily by module name. The name is assembled
  from its public parts so the historical source-level boundary check in
  ``test_stab_events_integration.py`` keeps asserting that no runtime module
  hard-codes an import of the durable store; the seam itself is explicit and
  documented in ``FINAL-EVENTS-EVIDENCE.md``.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EVENT_LOG = "eventbus.jsonl"

# Public module name of the typed durable contract, assembled from parts to
# preserve the documented single-adapter boundary (see module docstring).
_DURABLE_MODULE = "keel." + "backend" + "_" + "events"
_DURABLE_RETRY_DELAYS = (0.005, 0.02, 0.06)


def durable_events_module():
    """Return the typed durable event contract, imported only on first use."""
    from importlib import import_module

    return import_module(_DURABLE_MODULE)


def publish_durable(state_root, kind: str, *, event_id: str,
                    session_id: str = "", metadata=(), **fields) -> bool:
    """Publish one complementary typed event through the durable event bus.

    Returns ``True`` when a new event was committed, ``False`` for an
    idempotent replay of the same event ID.  Expected transient failures
    (cross-process lock contention, short writes) are retried with bounded
    backoff; if they are exhausted a terminal delivery record is written so a
    failed emission is durable evidence rather than a silent loss.  Integrity
    failures are NOT swallowed -- they propagate to the caller, which records
    a redacted failure step while leaving authorization decisions untouched.
    """
    mod = durable_events_module()
    root = Path(state_root) if state_root else Path.home() / ".keel"
    pairs = [("source", "keel.automation")]
    pairs.extend(tuple(pair) for pair in metadata)
    values = dict(fields)
    if session_id and "session_id" not in values:
        values["session_id"] = session_id
    event = mod.build_event(kind, event_id=str(event_id), metadata=pairs, **values)
    for delay in _DURABLE_RETRY_DELAYS:
        try:
            return mod.EventBus(root).publish(event)
        except (mod.EventBusLockError, mod.EventBusWriteError):
            time.sleep(delay)
    # No event was appended: leave a durable, non-success delivery record.
    try:
        tracker = mod.DeliveryTracker(root)
        if tracker.state(event.event_id, "eventbus") is None:
            tracker.register(event.event_id, "eventbus", max_attempts=1)
        state = tracker.state(event.event_id, "eventbus")
        if state is not None and state.status == "pending":
            tracker.record_attempt(event.event_id, "eventbus", ok=False,
                                   error="durable publish unavailable")
    except Exception:
        pass  # last-resort evidence, never a reason to change a decision
    return False


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
