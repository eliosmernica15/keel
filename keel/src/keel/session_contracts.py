"""keel.session_contracts -- canonical session / event-model contracts (D2.x).

This is an *additive* module.  It does not edit ``keel.session``,
``keel.events``, ``keel.transcript`` or any existing test.  Integration into
the live loop is a separate decision for the lead (see
``master-plan-v6-session-contracts-evidence.md``).

The eleven P0 registry IDs are turned into real, testable Python functionality:

  D2.1  three event domains + typed Event (seq/domain/kind/payload_hash) ... Event, EventBus
  D2.3  turn/step model, full lifecycle vocabulary ..................... Step, Turn, group_into_turns
  D2.5  per-agent inbox, inject() waits for waking message ............. AgentInbox, InboxRegistry
  D2.7  system prompt as logged history; empty text clears it .......... SessionJournal.set_system_prompt
  D2.8  cancellation during prompt preparation commits nothing ........ StepPreparation
  D2.9  failed steps record synthetic missing tool results ............. repair_missing_tool_results
  D2.10 process-local stream frames vs durable settled message ......... StreamBuffer, record_attempt
  D2.11 model-visible <=> logged; exact request bytes/hash ............. ModelRequest, reconstruct_model_requests
  D2.13 session format versioning with adjacent migrations ............. read_session, migrate_adjacent, list_sessions
  D2.15 fork at a turn boundary, seeded, deterministic ................ fork, ForkedSession
  D2.16 working dirs are metadata only, pure dataclasses ............... WorkingDirectory, DirectoryContext

Only the Python standard library is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field, fields, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

AGENT_LOOP = "agent_loop"


# ---------------------------------------------------------------------------
# shared helpers: canonical bytes and content hashes (no wall clock, no uuid)
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 encoding used by every hash in this module."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


# ---------------------------------------------------------------------------
# D2.1 -- event domains and typed Event records
# ---------------------------------------------------------------------------


class EventDomain(str, Enum):
    """The documented event domains.

    SESSION   durable facts, written to the log and broadcast to every reader.
    AGENT     per-agent live events: observe / intercept in-flight work only.
    PROVIDER  transient capability events (``fs/*``, ``tools/*``,
              ``telemetry/*``, policy/adapters on a seam) and provider traffic.
    UI        transient process-local presentation events.
    """

    SESSION = "session"
    AGENT = "agent"
    PROVIDER = "provider"
    UI = "ui"


TRANSIENT_DOMAINS = frozenset({EventDomain.PROVIDER, EventDomain.UI})
SESSION_KINDS = ("system/", "user/", "assistant/", "tool/", "turn/",
                 "step/", "model/")
AGENT_KINDS = ("agent/",)
CAPABILITY_KINDS = ("fs/", "tools/", "telemetry/", "provider/")
UI_KINDS = ("ui/", "assistant-stream")


def infer_domain(kind: str) -> EventDomain:
    """Domain is derived from the kind prefix unless explicitly overridden."""
    if kind.startswith(AGENT_KINDS):
        return EventDomain.AGENT
    if kind.startswith(CAPABILITY_KINDS):
        return EventDomain.PROVIDER
    if kind.startswith(UI_KINDS):
        return EventDomain.UI
    return EventDomain.SESSION


@dataclass(frozen=True)
class Event:
    """A typed event record.

    ``payload_hash`` commits to the payload only (not to wall-clock time), so a
    replay can reproduce the exact bytes independently of when it runs.  The
    journal assigns ``seq`` at append time; events built directly carry the
    seq given by their producer (0 for staged events).
    """

    seq: int
    domain: EventDomain
    kind: str
    payload: dict
    payload_hash: str = ""
    turn_index: int | None = None
    step_index: int | None = None
    agent_id: str | None = None
    published_by: str = AGENT_LOOP
    model_visible: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", EventDomain(self.domain))
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("event kind must be a non-empty string")
        if not self.payload_hash:
            object.__setattr__(self, "payload_hash", content_hash(self.payload))

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "domain": self.domain.value,
            "kind": self.kind,
            "payload": self.payload,
            "payload_hash": self.payload_hash,
            "turn_index": self.turn_index,
            "step_index": self.step_index,
            "agent_id": self.agent_id,
            "published_by": self.published_by,
            "model_visible": self.model_visible,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        d = dict(data)
        domain = EventDomain(d.get("domain") or infer_domain(d.get("kind", "")))
        payload = d.get("payload") or {}
        return cls(
            seq=int(d.get("seq", 0)),
            domain=domain,
            kind=str(d.get("kind", "")),
            payload=payload,
            payload_hash=str(d.get("payload_hash") or ""),
            turn_index=d.get("turn_index"),
            step_index=d.get("step_index"),
            agent_id=d.get("agent_id"),
            published_by=str(d.get("published_by") or AGENT_LOOP),
            model_visible=bool(d.get("model_visible", True)),
        )


def make_event(seq: int, kind: str, payload: dict, *,
               domain: EventDomain | str | None = None, **kwargs: Any) -> Event:
    return Event(seq=seq, domain=domain or infer_domain(kind), kind=kind,
                 payload=payload, **kwargs)


Listener = Callable[[Event], "Event | None"]


class EventBus:
    """Small synchronous bus with documented domain modes.

    * SESSION events are broadcast to all SESSION subscribers and (when a
      journal is attached) committed to the durable log.
    * AGENT events are delivered only to subscribers registered for that
      ``agent_id``.  A listener may return a replacement Event: this is the
      documented *intercept* mode; observers return ``None``.
    * PROVIDER / UI events are transient: delivered live, never committed.
    """

    def __init__(self, journal: "SessionJournal | None" = None) -> None:
        self._subscribers: list[tuple[EventDomain, str | None, Listener]] = []
        self._journal = journal
        self._lock = threading.RLock()

    def attach_journal(self, journal: "SessionJournal") -> None:
        self._journal = journal

    def subscribe(self, domain: EventDomain | str,
                  listener: Listener, *, agent_id: str | None = None) -> Listener:
        with self._lock:
            self._subscribers.append(
                (EventDomain(domain), agent_id, listener))
        return listener

    def publish(self, event: Event) -> Event:
        with self._lock:
            for domain, agent_id, listener in tuple(self._subscribers):
                if domain is not event.domain:
                    continue
                if agent_id is not None and agent_id != event.agent_id:
                    continue
                replacement = listener(event)
                if isinstance(replacement, Event):
                    event = replacement
            if (self._journal is not None
                    and event.domain is EventDomain.SESSION
                    and event.model_visible):
                self._journal.append(event)
            return event


# ---------------------------------------------------------------------------
# D2.11 -- model-visible <=> logged, system prompt, reconstruction
# ---------------------------------------------------------------------------

#: Every model-visible input field must have a logged projection.  Plugins
#: register new fields with :func:`register_model_visible_field`; a field that
#: has no projection is rejected by :func:`assert_request_is_reconstructible`.
MODEL_VISIBLE_FIELDS: dict[str, tuple[str, ...]] = {
    "model": ("model/selection",),
    "system": ("system/message",),
    "messages": ("user/message", "assistant/message", "tool/result",
                 "agent/injection"),
    "tool_schemas": ("tool/schemas", "model/selection"),
    "injections": ("agent/injection",),
}


def register_model_visible_field(name: str, kinds: Iterable[str]) -> None:
    """Register a pure message projection for a new model-visible field."""
    if not name or not name.isidentifier():
        raise ValueError("field name must be an identifier")
    MODEL_VISIBLE_FIELDS[name] = tuple(kinds)


class InvisibleModelInputError(ValueError):
    """A model input has no logged event, so the log cannot reproduce it."""


class ModelRequest:
    """One model request, rebuilt byte-for-byte from durable events."""

    __slots__ = ("model", "system", "messages", "tool_schemas", "injections",
                 "turn_index", "step_index")

    def __init__(self, *, model: str, system: str | None,
                 messages: Sequence[dict],
                 tool_schemas: Sequence[dict],
                 injections: Sequence["Injection"] = (),
                 turn_index: int | None = None,
                 step_index: int | None = None) -> None:
        self.model = model
        self.system = system
        self.messages = tuple(messages)
        self.tool_schemas = tuple(tool_schemas)
        self.injections = tuple(injections)
        self.turn_index = turn_index
        self.step_index = step_index
        # An admitted injection *lands in the next request*: it is always a
        # model-visible message.  Appending it here (with dedup for replay)
        # prevents a caller from building a request whose hash replay cannot
        # reproduce because the injection was left out of ``messages``.
        for injection in self.injections:
            message = {"role": "user", "content": injection.text,
                       "source": injection.source.value,
                       "tainted": injection.tainted}
            if not any(m.get("role") == message["role"]
                       and m.get("content") == message["content"]
                       and m.get("source") == message["source"]
                       for m in self.messages):
                self.messages = self.messages + (message,)

    def canonical_dict(self) -> dict:
        return {
            "model": self.model,
            "system": self.system,
            "messages": list(self.messages),
            "tool_schemas": list(self.tool_schemas),
            "injections": [
                {"text": i.text, "source": i.source.value, "tainted": i.tainted}
                for i in self.injections
            ],
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.canonical_dict())

    @property
    def request_hash(self) -> str:
        return content_hash(self.canonical_dict())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModelRequest):
            return NotImplemented
        return self.canonical_bytes() == other.canonical_bytes()

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (f"ModelRequest(model={self.model!r}, system={self.system!r}, "
                f"messages={len(self.messages)}, hash={self.request_hash[:12]})")


def build_request(*, model: str, system: str | None,
                  messages: Sequence[dict], tool_schemas: Sequence[dict],
                  injections: Sequence["Injection"] = (),
                  turn_index: int | None = None,
                  step_index: int | None = None) -> ModelRequest:
    return ModelRequest(model=model, system=system, messages=messages,
                        tool_schemas=tool_schemas, injections=injections,
                        turn_index=turn_index, step_index=step_index)


def _logged_kinds(events: Sequence[Event]) -> set[str]:
    return {e.kind for e in events
            if e.domain is EventDomain.SESSION and e.model_visible}


def assert_request_is_reconstructible(request: ModelRequest,
                                      events: Sequence[Event], *,
                                      extra_fields: Iterable[str] = ()) -> None:
    """Raise when a model-visible field would not survive a replay.

    This is the enforcement point for D2.11: any new field a plugin adds to a
    request must be backed by a registered, logged projection.  Empty optional
    fields are ignored (nothing to hide).
    """
    kinds = _logged_kinds(events)
    values = {
        "model": request.model,
        "system": request.system,
        "messages": request.messages,
        "tool_schemas": request.tool_schemas,
        "injections": request.injections,
    }
    for name, value in values.items():
        if value is None or value == "" or value == ():
            continue
        projections = MODEL_VISIBLE_FIELDS.get(name)
        if not projections or not kinds.intersection(projections):
            raise InvisibleModelInputError(
                f"model-visible field {name!r} has no logged projection")
    for name in extra_fields:
        projections = MODEL_VISIBLE_FIELDS.get(name)
        if not projections:
            raise InvisibleModelInputError(
                f"model-visible field {name!r} is not registered")
        if not kinds.intersection(projections):
            raise InvisibleModelInputError(
                f"model-visible field {name!r} has no logged projection")


def reconstruct_model_requests(events: Sequence[Event], *,
                               require_fields: Iterable[str] = ()) -> tuple[ModelRequest, ...]:
    """Replay a log and reproduce every model request (including its hash).

    Non-model-visible events (attempts, stream frames, agent-side live events)
    are ignored by construction: model-visible <=> logged.
    """
    ordered = sorted(events, key=lambda e: e.seq)
    kinds = _logged_kinds(ordered)
    for name in require_fields:
        projections = MODEL_VISIBLE_FIELDS.get(name)
        if not projections or not kinds.intersection(projections):
            raise InvisibleModelInputError(
                f"model-visible field {name!r} has no logged projection")

    model = "unknown"
    system: str | None = None
    tool_schemas: list[dict] = []
    messages: list[dict] = []
    injections: list[Injection] = []
    expected_hashes: dict[int, str] = {}
    requests: list[ModelRequest] = []
    current: dict[str, Any] | None = None

    for e in ordered:
        if e.domain is not EventDomain.SESSION or not e.model_visible:
            continue
        kind = e.kind
        payload = e.payload
        if kind == "model/selection":
            model = str(payload.get("model") or "unknown")
            if payload.get("tool_schemas") is not None:
                tool_schemas = list(payload["tool_schemas"])
        elif kind == "tool/schemas":
            tool_schemas = list(payload.get("schemas") or [])
        elif kind == "system/message":
            text = payload.get("text")
            system = text if isinstance(text, str) and text else None
        elif kind in ("user/message", "assistant/message", "tool/result"):
            message = dict(payload)
            message.pop("stream", None)  # process-local metadata, not model input
            messages.append(message)
        elif kind == "agent/injection" and payload.get("admitted"):
            inj = Injection(
                text=str(payload.get("text") or ""),
                source=InjectionSource(payload.get("source", "agent-message")),
                seq=int(payload.get("injection_seq") or 0),
                wake_seq=int(payload.get("wake_seq") or 0),
                agent_id=e.agent_id,
                state=InjectionState.ADMITTED,
            )
            injections.append(inj)
            messages.append({
                "role": "user",
                "content": inj.text,
                "source": inj.source.value,
                "tainted": inj.tainted,
            })
        elif kind == "model/request":
            idx = e.step_index
            if idx is not None and payload.get("request_hash"):
                expected_hashes[int(idx)] = str(payload["request_hash"])
        elif kind == "step/start":
            # Only the boundary indices are captured here: the request is
            # assembled at step/end from every message logged before it.
            current = {"turn_index": e.turn_index, "step_index": e.step_index}
        elif kind == "step/end" and current is not None:
            req = ModelRequest(
                model=model, system=system, messages=list(messages),
                tool_schemas=list(tool_schemas), injections=list(injections),
                turn_index=current["turn_index"],
                step_index=current["step_index"])
            expected = expected_hashes.get(req.step_index)  # type: ignore[arg-type]
            if expected is not None and expected != req.request_hash:
                raise InvisibleModelInputError(
                    "log replay does not reproduce the exact request bytes")
            requests.append(req)
            current = None
    return tuple(requests)


class SessionJournal:
    """Append-only durable log with helpers for every model-visible input."""

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._lock = threading.RLock()

    # -- writing ----------------------------------------------------------
    def append(self, event: Event) -> Event:
        with self._lock:
            committed = replace(event, seq=len(self._events) + 1)
            self._events.append(committed)
            return committed

    def set_system_prompt(self, text: str) -> Event:
        """Log a ``system/message`` event; empty text clears the prompt."""
        return self.append(make_event(0, "system/message", {"text": text}))

    def add_user(self, content: Any) -> Event:
        return self.append(make_event(0, "user/message",
                                      {"role": "user", "content": content}))

    def add_assistant(self, content: str, stream: Sequence[dict] | None = None) -> Event:
        payload: dict[str, Any] = {"role": "assistant", "content": content}
        if stream is not None:
            payload["stream"] = list(stream)
        return self.append(make_event(0, "assistant/message", payload))

    def add_tool_call(self, tool_use_id: str, name: str,
                      tool_input: dict, *, turn_index: int | None = None,
                      step_index: int | None = None) -> Event:
        return self.append(make_event(
            0, "tool/call",
            {"tool_use_id": tool_use_id, "name": name, "input": tool_input},
            turn_index=turn_index, step_index=step_index))

    def add_tool_result(self, tool_use_id: str, content: str, *,
                        synthetic: bool = False, reason: str = "",
                        turn_index: int | None = None,
                        step_index: int | None = None) -> Event:
        return self.append(make_event(
            0, "tool/result",
            {"role": "user", "tool_use_id": tool_use_id, "content": content,
             "synthetic": synthetic, "reason": reason},
            turn_index=turn_index, step_index=step_index))

    def snapshot_model(self, model: str, tool_schemas: Sequence[dict]) -> Event:
        return self.append(make_event(
            0, "model/selection",
            {"model": model, "tool_schemas": list(tool_schemas)}))

    def record_schemas(self, schemas: Sequence[dict]) -> Event:
        return self.append(make_event(0, "tool/schemas",
                                      {"schemas": list(schemas)}))

    def log_injection(self, injection: "Injection") -> Event:
        """Durable projection of an admitted injection (D2.5 + D2.11)."""
        return self.append(make_event(
            0, "agent/injection",
            {"text": injection.text, "source": injection.source.value,
             "admitted": injection.state is InjectionState.ADMITTED,
             "tainted": injection.tainted,
             "injection_seq": injection.seq, "wake_seq": injection.wake_seq},
            domain=EventDomain.SESSION, agent_id=injection.agent_id))

    def admit_request(self, request: ModelRequest) -> Event:
        """Commit a request only if every model-visible input is logged."""
        assert_request_is_reconstructible(request, self._events)
        return self.append(make_event(
            0, "model/request",
            {"request_hash": request.request_hash},
            turn_index=request.turn_index, step_index=request.step_index))

    def start_turn(self, turn_index: int) -> Event:
        return self.append(make_event(0, "turn/start",
                                      {"turn_index": turn_index},
                                      turn_index=turn_index))

    def end_turn(self, turn_index: int) -> Event:
        return self.append(make_event(0, "turn/end",
                                      {"turn_index": turn_index},
                                      turn_index=turn_index))

    def start_step(self, step_index: int,
                   turn_index: int | None = None) -> Event:
        return self.append(make_event(0, "step/start",
                                      {"step_index": step_index},
                                      step_index=step_index,
                                      turn_index=turn_index))

    def end_step(self, step_index: int, *, failed: bool = False,
                 reason: str = "") -> Event:
        return self.append(make_event(
            0, "step/end",
            {"step_index": step_index, "failed": failed, "reason": reason},
            step_index=step_index))

    def record_attempt(self, status: str, *, reason: str = "",
                       step_index: int | None = None) -> Event:
        """D2.10: failed/retried/cancelled attempts, never model history."""
        if status not in ("failed", "retried", "cancelled"):
            raise ValueError(f"unknown attempt status: {status!r}")
        return self.append(make_event(
            0, "assistant/attempt", {"status": status, "reason": reason},
            step_index=step_index, model_visible=False))

    def close_failed_step(self, step_index: int, *, reason: str = "") -> tuple[Event, ...]:
        """D2.9: append synthetic results for every outstanding tool call."""
        committed: list[Event] = []
        for call in missing_tool_results(self._events):
            committed.append(self.add_tool_result(
                str(call.payload.get("tool_use_id") or ""),
                "[missing tool result: step failed]",
                synthetic=True, reason=reason or "step_failed",
                turn_index=call.turn_index, step_index=step_index))
        committed.append(self.end_step(step_index, failed=True, reason=reason))
        return tuple(committed)

    # -- reading ----------------------------------------------------------
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def system_prompt(self) -> str | None:
        """Current system prompt; ``None`` when empty text cleared it."""
        for e in reversed(self._events):
            if e.kind == "system/message":
                text = e.payload.get("text")
                return text if isinstance(text, str) and text else None
        return None

    def model_visible_events(self) -> tuple[ModelRequest, ...]:
        return reconstruct_model_requests(self._events)

    def turns(self) -> tuple["Turn", ...]:
        requests = {r.step_index: r for r in self.model_visible_events()}
        return group_into_turns(self._events, requests=requests)


# ---------------------------------------------------------------------------
# D2.3 -- turn / step model and the ordered lifecycle
# ---------------------------------------------------------------------------

#: ``turn/start`` -> claim input -> snapshot model selection -> assemble prompt
#: + tool schemas -> pre-step hook -> ``step/start`` -> prepare call -> stream ->
#: assistant message or failed attempt -> ``tool/call`` -> pre-execute ->
#: execute -> post-execute -> ``tool/result`` -> ``step/end`` -> loop or
#: turn-stopping hook -> ``turn/end``.  Every named stage has a hook and a log
#: event in the live loop (internal doc seam).
TURN_LIFECYCLE: tuple[str, ...] = (
    "turn/start", "input/claim", "model/selection", "prompt/assemble",
    "hook/pre-step", "step/start", "call/prepare", "assistant-stream",
    "assistant/message", "assistant/attempt", "tool/call", "hook/pre-execute",
    "tool/execute", "hook/post-execute", "tool/result", "step/end",
    "hook/turn-stop", "turn/end",
)


@dataclass(frozen=True)
class ToolCall:
    tool_use_id: str
    name: str
    tool_input: dict


@dataclass(frozen=True)
class Step:
    """One model request plus the tool calls it produced."""

    index: int
    turn_index: int | None
    request: ModelRequest | None
    tool_calls: tuple[ToolCall, ...]
    events: tuple[Event, ...]
    failed: bool = False


@dataclass(frozen=True)
class Turn:
    """A turn contains zero or more steps (turn/start ... turn/end)."""

    index: int
    steps: tuple[Step, ...]
    start_seq: int
    end_seq: int


@dataclass
class _StepBuilder:
    index: int
    turn_index: int | None
    request: ModelRequest | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    failed: bool = False

    def build(self) -> Step:
        return Step(self.index, self.turn_index, self.request,
                    tuple(self.tool_calls), tuple(self.events), self.failed)


@dataclass
class _TurnBuilder:
    index: int
    start_seq: int

    def build(self, steps: Sequence[Step], end_seq: int) -> Turn:
        return Turn(self.index, tuple(steps), self.start_seq, end_seq)


def group_into_turns(events: Sequence[Event], *,
                     requests: dict[int | None, ModelRequest] | None = None,
                     repair_interrupted: bool = False) -> tuple[Turn, ...]:
    """Group an ordered event log into turns and their steps."""
    requests = requests or {}
    turns: list[Turn] = []
    current_turn: _TurnBuilder | None = None
    current_step: _StepBuilder | None = None
    steps: list[Step] = []

    for e in sorted(events, key=lambda ev: ev.seq):
        kind = e.kind
        if kind == "turn/start":
            current_turn = _TurnBuilder(
                int(e.payload.get("turn_index", len(turns))), e.seq)
            steps = []
        elif kind == "step/start":
            idx = e.step_index
            if idx is None:
                idx = e.payload.get("step_index", len(steps))
            current_step = _StepBuilder(
                int(idx),
                e.turn_index if e.turn_index is not None
                else (current_turn.index if current_turn else None),
                request=requests.get(int(idx)))
            steps.append(current_step)
        elif kind == "tool/call":
            if current_step is not None:
                current_step.tool_calls.append(ToolCall(
                    str(e.payload.get("tool_use_id") or ""),
                    str(e.payload.get("name") or ""),
                    dict(e.payload.get("input") or {})))
                current_step.events.append(e)
        elif kind in ("tool/result", "user/message", "assistant/message"):
            if current_step is not None:
                current_step.events.append(e)
        elif kind == "step/end":
            if current_step is not None:
                current_step.failed = bool(e.payload.get("failed", False))
                current_step.events.append(e)
                current_step = None
        elif kind == "turn/end":
            if current_turn is not None:
                turns.append(current_turn.build(steps, e.seq))
                current_turn = None
                current_step = None
    if current_turn is not None:
        if repair_interrupted:
            turns.append(current_turn.build(
                steps, max((e.seq for e in events), default=0) + 1))
        current_step = None
    return tuple(turns)


# ---------------------------------------------------------------------------
# D2.5 -- per-agent inbox, inject() and deterministic wake ordering
# ---------------------------------------------------------------------------


class InjectionSource(str, Enum):
    USER = "user"
    SYSTEM = "system"
    AGENT_MESSAGE = "agent-message"
    SUBAGENT_SETTLED = "subagent-settled"
    TOOL_RESULT = "tool-result"
    HOOK = "hook"


TAINTED_SOURCES = frozenset({
    InjectionSource.AGENT_MESSAGE, InjectionSource.SUBAGENT_SETTLED,
    InjectionSource.TOOL_RESULT,
})


class InjectionState(str, Enum):
    WAITING = "waiting"        # injected, waits for a waking message
    ADMITTED = "admitted"      # landed in the next admitted model request


@dataclass(frozen=True)
class Injection:
    text: str
    source: InjectionSource
    seq: int
    wake_seq: int
    agent_id: str | None = None
    state: InjectionState = InjectionState.WAITING

    @property
    def tainted(self) -> bool:
        return self.source in TAINTED_SOURCES


class AgentInbox:
    """One inbox per agent driver.  ``inject`` never shows text immediately."""

    def __init__(self, agent_id: str, registry: "InboxRegistry") -> None:
        self.agent_id = agent_id
        self._registry = registry
        self._pending: list[Injection] = []

    def inject(self, text: str, source: InjectionSource | str,
               *, wake: bool = True) -> Injection:
        """Queue context; with ``wake`` it waits for the next waking message."""
        src = InjectionSource(source)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("injected text must be non-empty")
        injection = Injection(
            text=text, source=src, seq=self._registry.next_seq(),
            wake_seq=self._registry.next_wake_seq() if wake else -1,
            agent_id=self.agent_id)
        self._pending.append(injection)
        return injection

    def pending(self) -> tuple[Injection, ...]:
        return tuple(self._pending)

    def admit(self) -> tuple[Injection, ...]:
        """Admit all waiting injections into the next model request, in order."""
        admitted: list[Injection] = []
        for injection in sorted(self._pending,
                                key=lambda i: (i.wake_seq, i.seq)):
            promoted = replace(injection, state=InjectionState.ADMITTED)
            admitted.append(promoted)
            if self._registry.journal is not None:
                self._registry.journal.log_injection(promoted)
        self._pending.clear()
        return tuple(admitted)


class InboxRegistry:
    """Holds one :class:`AgentInbox` per agent and fixes wake order."""

    def __init__(self, journal: SessionJournal | None = None) -> None:
        self.journal = journal
        self._inboxes: dict[str, AgentInbox] = {}
        self._seq = 0
        self._wake_seq = 0
        self._lock = threading.RLock()

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def next_wake_seq(self) -> int:
        with self._lock:
            self._wake_seq += 1
            return self._wake_seq

    def inbox(self, agent_id: str) -> AgentInbox:
        with self._lock:
            if agent_id not in self._inboxes:
                self._inboxes[agent_id] = AgentInbox(agent_id, self)
            return self._inboxes[agent_id]

    def inject(self, agent_id: str, text: str,
               source: InjectionSource | str) -> Injection:
        return self.inbox(agent_id).inject(text, source)

    def wake_order(self) -> tuple[str, ...]:
        """Agents ordered by their earliest waiting wake token, then id."""
        waiting = []
        for agent_id, inbox in self._inboxes.items():
            wakes = [i.wake_seq for i in inbox.pending() if i.wake_seq >= 0]
            if wakes:
                waiting.append((min(wakes), agent_id))
        return tuple(agent_id for _, agent_id in sorted(waiting))

    def admit(self, agent_id: str) -> tuple[Injection, ...]:
        return self.inbox(agent_id).admit()


# ---------------------------------------------------------------------------
# D2.8 -- atomic prompt preparation (commit only after prepare succeeds)
# ---------------------------------------------------------------------------


class CancelledDuringPrepare(RuntimeError):
    """Preparation was cancelled; nothing was committed."""


class StepPreparation:
    """Stage system/user events, then commit them all or none.

    ``cancelled`` is a zero-argument predicate (e.g. ``threading.Event.is_set``).
    Cancellation before :meth:`commit` discards the staged events, so neither
    the system prompt nor the user message can leak into the durable log.
    """

    def __init__(self, journal: SessionJournal,
                 cancelled: Callable[[], bool]) -> None:
        self._journal = journal
        self._cancelled = cancelled
        self._staged: list[Event] = []
        self._done = False

    def stage(self, kind: str, payload: dict, **kwargs: Any) -> "StepPreparation":
        if self._done:
            raise RuntimeError("preparation already completed")
        self._staged.append(make_event(0, kind, payload, **kwargs))
        return self

    def system(self, text: str) -> "StepPreparation":
        return self.stage("system/message", {"text": text})

    def user(self, content: Any) -> "StepPreparation":
        return self.stage("user/message", {"role": "user", "content": content})

    def commit(self) -> tuple[Event, ...]:
        if self._done:
            raise RuntimeError("preparation already completed")
        self._done = True
        staged, self._staged = self._staged, []
        if self._cancelled():
            raise CancelledDuringPrepare("cancelled during prompt preparation")
        return tuple(self._journal.append(e) for e in staged)

    def __enter__(self) -> "StepPreparation":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is not None:
            self._staged.clear()
            self._done = True
        else:
            self.commit()
        return False


# ---------------------------------------------------------------------------
# D2.9 -- synthetic missing tool results for failed steps
# ---------------------------------------------------------------------------


def missing_tool_results(events: Sequence[Event]) -> tuple[Event, ...]:
    """Tool calls with no matching tool/result (Y2.4 repair contract)."""
    results = {str(e.payload.get("tool_use_id") or "")
               for e in events if e.kind == "tool/result"}
    return tuple(e for e in sorted(events, key=lambda ev: ev.seq)
                 if e.kind == "tool/call"
                 and str(e.payload.get("tool_use_id") or "") not in results)


def repair_missing_tool_results(events: Sequence[Event], *,
                                reason: str = "step_failed") -> tuple[Event, ...]:
    """Build synthetic result events (not appended; caller owns the journal)."""
    return tuple(make_event(
        0, "tool/result",
        {"role": "user",
         "tool_use_id": str(call.payload.get("tool_use_id") or ""),
         "content": "[missing tool result: step failed]",
         "synthetic": True, "reason": reason},
        turn_index=call.turn_index, step_index=call.step_index)
        for call in missing_tool_results(events))


# ---------------------------------------------------------------------------
# D2.10 -- process-local stream frames vs durable settled message
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StreamFrame:
    kind: str                 # start | chunk | end
    text: str
    offset_ms: int = 0


class StreamBuffer:
    """Process-local live frames; lost on a hard crash before settlement."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._frames: list[StreamFrame] = []
        self._t0: float | None = None

    def _offset(self) -> int:
        now = self._clock()
        if self._t0 is None:
            self._t0 = now
        return max(0, int((now - self._t0) * 1000))

    def start(self) -> StreamFrame:
        frame = StreamFrame("start", "", self._offset())
        self._frames.append(frame)
        return frame

    def chunk(self, text: str) -> StreamFrame:
        frame = StreamFrame("chunk", text, self._offset())
        self._frames.append(frame)
        return frame

    def end(self) -> StreamFrame:
        frame = StreamFrame("end", "", self._offset())
        self._frames.append(frame)
        return frame

    def frames(self) -> tuple[StreamFrame, ...]:
        return tuple(self._frames)

    def compact(self) -> list[dict]:
        """Compact timed stream embedded in the settled durable message."""
        return [{"k": f.kind, "t": f.text, "ms": f.offset_ms}
                for f in self._frames]

    def clear(self) -> None:
        self._frames = []
        self._t0 = None


def settle_assistant(journal: SessionJournal, text: str,
                     stream: StreamBuffer) -> Event:
    """Settle a live stream into one durable assistant message."""
    event = journal.add_assistant(text, stream.compact())
    stream.clear()
    return event


# ---------------------------------------------------------------------------
# D2.13 -- session format versioning with adjacent migrations
# ---------------------------------------------------------------------------


FORMAT = "keel-session"
CURRENT_VERSION = 3

_NON_ADJACENT_RE = re.compile(r"v(\d+)")


class SessionFormatError(ValueError):
    """Base class for typed session-format failures."""


class NonAdjacentMigrationError(SessionFormatError):
    """A migration skipped a generation (only vN -> vN+1 is allowed)."""


class UnsupportedVersionError(SessionFormatError):
    """A file was written by a newer, unreadable generation."""


class GenerationExistsError(SessionFormatError):
    """A committed generation already exists and is never overwritten."""


class UnsupportedCompressionError(SessionFormatError):
    """No codec was registered for a compressed session suffix."""


class UnboundedRestartRepairError(SessionFormatError):
    """Too many interrupted turns to repair for one bounded restart."""


_CODECS: dict[str, tuple[Callable[[bytes], bytes],
                          Callable[[bytes], bytes]]] = {}
COMPRESSED_SUFFIXES = (".zstd", ".zst")


def register_codec(suffix: str, compress: Callable[[bytes], bytes],
                   decompress: Callable[[bytes], bytes]) -> None:
    """Register a codec for a compressed session suffix (e.g. ``.zstd``)."""
    suffix = suffix.lower()
    if not suffix.startswith("."):
        suffix = "." + suffix
    _CODECS[suffix] = (compress, decompress)


def codec_for(path: str | Path) -> tuple[Callable[[bytes], bytes],
                                         Callable[[bytes], bytes]] | None:
    name = str(path).lower()
    for suffix in COMPRESSED_SUFFIXES:
        if name.endswith(suffix):
            if suffix not in _CODECS:
                raise UnsupportedCompressionError(
                    f"no codec registered for {suffix}; register one with "
                    "register_codec() (zstd needs an optional external lib)")
            return _CODECS[suffix]
    return None


def session_path(directory: str | Path, session_id: str, version: int, *,
                 compressed: bool = False) -> Path:
    name = f"{session_id}.v{version}.jsonl"
    if compressed:
        name += ".zstd"
    return Path(directory) / name


def _header(session_id: str, version: int, event_count: int) -> dict:
    return {"format": FORMAT, "version": version, "session_id": session_id,
            "event_count": event_count}


def _encode(text: str, path: str | Path) -> bytes:
    data = text.encode("utf-8")
    codec = codec_for(path)
    return codec[0](data) if codec else data


def _decode(data: bytes, path: str | Path) -> str:
    codec = codec_for(path)
    return (codec[1](data) if codec else data).decode("utf-8")


def write_session(path: str | Path, events: Sequence[Event], *,
                  session_id: str, version: int = CURRENT_VERSION) -> Path:
    """Write a new generation; refuse to overwrite a committed one."""
    target = Path(path)
    if target.exists():
        raise GenerationExistsError(f"generation already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(_header(session_id, version, len(events)),
                        separators=(",", ":"), ensure_ascii=False)]
    lines.extend(json.dumps(e.to_dict(), separators=(",", ":"),
                            ensure_ascii=False) for e in events)
    payload = _encode("\n".join(lines) + "\n", target)
    with open(target, "xb") as handle:  # exclusive create: never overwrite
        handle.write(payload)
    return target


def read_header(path: str | Path) -> dict:
    """Header-only read: stat/list never parse the event body."""
    target = Path(path)
    codec = codec_for(target)
    if codec is None:
        # Header-only: never parse the event body for uncompressed files.
        with open(target, "r", encoding="utf-8") as handle:
            header = handle.readline().strip()
    else:
        # A generic codec produces one opaque blob; decode it, but still only
        # parse the first line (the body stays unparsed).
        blob = codec[1](Path(target).read_bytes()).decode("utf-8")
        header = blob.split("\n", 1)[0].strip()
    try:
        doc = json.loads(header)
    except ValueError as exc:
        raise SessionFormatError(f"invalid session header: {exc}") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise SessionFormatError("not a Keel session file")
    doc["version"] = int(doc.get("version", 0))
    return doc


@dataclass(frozen=True)
class SessionStat:
    session_id: str
    version: int
    readable: bool
    event_count: int
    path: str


def stat_session(path: str | Path) -> SessionStat:
    header = read_header(path)
    return SessionStat(str(header["session_id"]), header["version"],
                       header["version"] <= CURRENT_VERSION,
                       int(header.get("event_count", 0)), str(path))


def list_sessions(directory: str | Path) -> dict[str, SessionStat]:
    """Pick the highest *readable* generation per session, from headers only."""
    best: dict[str, SessionStat] = {}
    for path in sorted(Path(directory).glob("*.jsonl*")):
        try:
            stat = stat_session(path)
        except (SessionFormatError, OSError, ValueError):
            continue
        if not stat.readable:
            continue
        prior = best.get(stat.session_id)
        if prior is None or stat.version > prior.version:
            best[stat.session_id] = stat
    return best


def repair_interrupted_turn(events: Sequence[Event], *,
                            released_restart: bool = True,
                            max_insert: int = 1) -> tuple[Event, ...]:
    """Insert a missing ``turn/end`` only for a bounded released restart."""
    open_turns = [
        e for e in events
        if e.kind == "turn/start"
        and not any(end.kind == "turn/end"
                    and end.turn_index == e.turn_index
                    and end.seq > e.seq for end in events)
    ]
    if not open_turns:
        return tuple(events)
    if not released_restart:
        return tuple(events)
    if len(open_turns) > max_insert:
        raise UnboundedRestartRepairError(
            f"{len(open_turns)} interrupted turns exceed bound {max_insert}")
    result = list(events)
    last_seq = max((e.seq for e in events), default=0)
    for start in open_turns:
        last_seq += 1
        result.append(make_event(
            last_seq, "turn/end",
            {"turn_index": start.turn_index, "reason": "released_restart"},
            turn_index=start.turn_index))
    return tuple(result)


def migrate_1_to_2(events: Sequence[Event], **_: Any) -> tuple[Event, ...]:
    # v1 had no payload_hash; content hashing makes replay deterministic.
    return tuple(replace(e, payload_hash=e.payload_hash or content_hash(e.payload))
                 for e in events)


def migrate_2_to_3(events: Sequence[Event], *,
                   released_restart: bool = True, **_: Any) -> tuple[Event, ...]:
    out: list[Event] = []
    for e in events:
        payload = dict(e.payload)
        if e.kind == "assistant/message":
            payload.setdefault("stream", [])
        turn_index = e.turn_index if e.turn_index is not None else payload.get("turn_index")
        step_index = e.step_index if e.step_index is not None else payload.get("step_index")
        out.append(replace(e, payload=payload,
                           payload_hash=content_hash(payload),
                           turn_index=turn_index, step_index=step_index))
    return repair_interrupted_turn(out, released_restart=released_restart)


_MIGRATIONS: dict[int, Callable[[Sequence[Event]], tuple[Event, ...]]] = {
    1: migrate_1_to_2,
    2: migrate_2_to_3,
}


def migrate_adjacent(events: Sequence[Event], from_version: int,
                     to_version: int, *, released_restart: bool = True) -> tuple[Event, ...]:
    """Apply exactly one adjacent step: ``vN -> vN+1``."""
    if to_version != from_version + 1:
        raise NonAdjacentMigrationError(
            f"migration must be adjacent: v{from_version} -> v{to_version}")
    step = _MIGRATIONS.get(from_version)
    if step is None:
        raise NonAdjacentMigrationError(
            f"no migration registered from v{from_version}")
    return step(events, released_restart=released_restart)


def migrate_events(events: Sequence[Event], from_version: int,
                   to_version: int, *, released_restart: bool = True) -> tuple[Event, ...]:
    """Translate through every adjacent step, in memory only."""
    if from_version > to_version:
        raise NonAdjacentMigrationError("migrations are forward-only")
    current: Sequence[Event] = tuple(events)
    version = from_version
    while version < to_version:
        current = migrate_adjacent(current, version, version + 1,
                                   released_restart=released_restart)
        version += 1
    return tuple(current)


def read_session(path: str | Path) -> tuple[int, tuple[Event, ...]]:
    """Read-open: translate to CURRENT_VERSION in memory, never on disk."""
    header = read_header(path)
    version = header["version"]
    if version > CURRENT_VERSION:
        raise UnsupportedVersionError(
            f"cannot read v{version} (highest readable v{CURRENT_VERSION})")
    target = Path(path)
    codec = codec_for(target)
    if codec is None:
        text = Path(target).read_text(encoding="utf-8")
    else:
        text = codec[1](Path(target).read_bytes()).decode("utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    events = tuple(Event.from_dict(json.loads(line)) for line in lines[1:])
    return version, migrate_events(events, version, CURRENT_VERSION)


def write_successor(source: str | Path, events: Sequence[Event], *,
                    session_id: str | None = None) -> Path:
    """Write a version-named successor beside an unchanged source."""
    source_path = Path(source)
    header = read_header(source_path)
    version = header["version"]
    name = session_id or str(header["session_id"])
    target = session_path(source_path.parent, name, version + 1,
                          compressed=str(source_path).endswith(COMPRESSED_SUFFIXES))
    return write_session(target, events, session_id=name, version=version + 1)


# ---------------------------------------------------------------------------
# D2.15 -- fork at a turn boundary (seeded, inherited count, deterministic)
# ---------------------------------------------------------------------------


class NotATurnBoundaryError(ValueError):
    """The requested fork point is not a committed ``turn/end``."""


@dataclass(frozen=True)
class ForkedSession:
    session_id: str
    seed: int
    at_turn: int
    events: tuple[Event, ...]
    inherited_event_count: int
    next_seq: int

    def event_id(self, label: str = "step") -> str:
        """Deterministic id from the seed and inherited count; no uuid/rng."""
        return content_hash(f"{self.seed}:{self.next_seq}:{label}")[:16]


def fork(session: SessionJournal | Sequence[Event], at_turn: int, *,
         seed: int = 0, session_id: str = "forked") -> ForkedSession:
    """Seed a new session from all agent-loop events up to ``at_turn``."""
    events = tuple(session.events()) if isinstance(session, SessionJournal) else tuple(session)
    ends = [e for e in events
            if e.kind == "turn/end"
            and int(e.turn_index if e.turn_index is not None
                    else e.payload.get("turn_index", -1)) == at_turn]
    if not ends:
        raise NotATurnBoundaryError(f"no committed turn boundary at {at_turn}")
    boundary = min(ends, key=lambda e: e.seq)
    migrated = [e for e in events
                if e.seq <= boundary.seq and e.published_by == AGENT_LOOP]
    renumbered = tuple(replace(e, seq=i + 1)
                       for i, e in enumerate(migrated))
    count = len(renumbered)
    return ForkedSession(session_id=session_id, seed=seed, at_turn=at_turn,
                         events=renumbered, inherited_event_count=count,
                         next_seq=count + 1)


# ---------------------------------------------------------------------------
# D2.16 -- working directories are context/execution metadata only
# ---------------------------------------------------------------------------


class WorkingDirectoryError(ValueError):
    """Invalid working-directory metadata."""


@dataclass(frozen=True)
class WorkingDirectory:
    path: str
    label: str = ""
    purpose: str = "context"     # context | execution

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise WorkingDirectoryError("working_dir path must be non-empty")
        if "\x00" in self.path:
            raise WorkingDirectoryError("working_dir path contains NUL")
        if self.purpose not in ("context", "execution"):
            raise WorkingDirectoryError(f"unknown purpose: {self.purpose!r}")


@dataclass(frozen=True)
class DirectoryContext:
    """Pure metadata: no chdir, no write-root or project-identity changes."""

    project_root: str
    working_dir: str
    write_roots: tuple[str, ...]
    process_cwd: str
    metadata: tuple[WorkingDirectory, ...] = ()

    @property
    def project_id(self) -> str:
        return content_hash(os.path.normcase(os.path.abspath(self.project_root)))[:16]

    def with_working_dir(self, path: str, *, label: str = "",
                         purpose: str = "context") -> "DirectoryContext":
        wd = WorkingDirectory(path, label, purpose)
        new = replace(self, working_dir=wd.path,
                      metadata=self.metadata + (wd,))
        # Identity, sandbox roots and process cwd are structurally untouched.
        assert new.project_root == self.project_root
        assert new.write_roots == self.write_roots
        assert new.process_cwd == self.process_cwd
        assert new.project_id == self.project_id
        return new

    def execution_path(self, relative: str) -> str:
        """Resolve a path against working_dir metadata only; never chdir."""
        return os.path.normpath(os.path.join(self.working_dir, relative))

    def validate_change(self, path: str) -> dict:
        """Return before/after fields proving nothing but metadata changed."""
        new = self.with_working_dir(path)
        return {
            "project_identity_unchanged": new.project_id == self.project_id,
            "write_roots_unchanged": new.write_roots == self.write_roots,
            "process_cwd_unchanged": new.process_cwd == self.process_cwd,
            "new_context": new,
        }


__all__ = [
    "AGENT_LOOP", "canonical_bytes", "content_hash",
    "EventDomain", "TRANSIENT_DOMAINS", "infer_domain", "Event", "make_event",
    "EventBus", "MODEL_VISIBLE_FIELDS", "register_model_visible_field",
    "InvisibleModelInputError", "ModelRequest", "build_request",
    "assert_request_is_reconstructible", "reconstruct_model_requests",
    "SessionJournal", "TURN_LIFECYCLE", "ToolCall", "Step", "Turn",
    "group_into_turns", "InjectionSource", "TAINTED_SOURCES",
    "InjectionState", "Injection", "AgentInbox", "InboxRegistry",
    "CancelledDuringPrepare", "StepPreparation", "missing_tool_results",
    "repair_missing_tool_results", "StreamFrame", "StreamBuffer",
    "settle_assistant", "FORMAT", "CURRENT_VERSION", "SessionFormatError",
    "NonAdjacentMigrationError", "UnsupportedVersionError",
    "GenerationExistsError", "UnsupportedCompressionError",
    "UnboundedRestartRepairError", "register_codec", "codec_for",
    "session_path", "write_session", "read_header", "SessionStat",
    "stat_session", "list_sessions", "repair_interrupted_turn",
    "migrate_1_to_2", "migrate_2_to_3", "migrate_adjacent",
    "migrate_events", "read_session", "write_successor",
    "NotATurnBoundaryError", "ForkedSession", "fork",
    "WorkingDirectoryError", "WorkingDirectory", "DirectoryContext",
]
