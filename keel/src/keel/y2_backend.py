"""keel.y2_backend -- backend contracts for the remaining Y2.* registry rows.

This is an *additive*, standard-library-only module.  It does not edit any
existing source file, test, the web app or the CLI.  It turns the 15
``not_started`` Y2 P1 rows of ``PLAN-INDEX.json`` into real, testable backend
behaviour:

  Y2.9  card / event row-kind registry (approval, question, connect, draft;
        routine/voice/group events; notice) .................. RowKindRegistry
  Y2.10 stay_silent and request_app_connection tools ........ CollabToolRegistry
  Y2.11 send_to_bot, hidden subagents, group rooms (cap 3) .... GroupRoom, SubagentManager
  Y2.12 screen leasing: 4 desktops per VM, LRU leases ........ DesktopPool
  Y2.13 idle suspend knobs (20 min / 60 s sweep / dry-run) .... ResourceManager
  Y2.15 rate-limit awareness + in-VM executor seam ........... TokenBucket, InVmExecutor
  Y2.16 compaction knobs (keep-last-N, method, memory budget)  plan_compaction
  Y2.17 prompt cache key per agent+generation ............... build_provider_identity
  Y2.18 NO_SCHEDULER flag (--no-scheduler / KEEL_NO_SCHEDULER) parse_scheduler_flag
  Y2.19 backward-compatible rename path ..................... RenameCompat
  Y2.21 honest "Project status" section ..................... build_project_status
  Y2.22 voice: realtime secrets, hand_off_task, TTS/STT ..... RealtimeSecretIssuer, ...
  Y2.23 E2E script with a prepared-audio fixture ............ run_e2e_scenario, prepare_audio_fixture
  Y2.24 per-user SSE stream with typed event kinds .......... SSEStream, SSEStreamRegistry
  Y2.25 routines: cron, connector events, check-ins ......... RoutineEngine, parse_cron

The ten not_started **P0** rows (Y2.1-Y2.8, Y2.14, Y2.20) are already
implemented in ``keel.transcript_contracts``; this module does not duplicate
them.  Integration into the live runtime is a separate lead decision (the
seams are recorded in ``master-plan-v6-y2-backend-evidence.md``).

Design rules, identical to the transcript contracts: stdlib only, no uuid or
randomness, no network/socket, no import-time I/O.  Every id is a deterministic
SHA-256 prefix of canonical JSON, every clock is injectable, and all failures
are typed.  Time is only ever used for stamps, never for identity.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field, fields, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# shared helpers: canonical bytes, deterministic ids, clocks, typed errors
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 encoding used by every hash in this module."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def new_id(*parts: Any, length: int = 16) -> str:
    """A stable, collision-resistant id derived only from its inputs."""
    if not 1 <= length <= 64:
        raise Y2BackendError("id length must be in 1..64")
    return content_hash(list(parts))[:length]


def timestamp(clock: Callable[[], float] | None = None) -> str:
    """UTC ISO-8601 stamp; *clock* is an injectable epoch-seconds callable."""
    now = float(clock()) if clock is not None else time.time()
    # Imported lazily here to keep the module import free of side effects.
    from datetime import timezone
    return datetime.fromtimestamp(now, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z")


class Y2BackendError(ValueError):
    """Base class for all typed Y2 backend failures."""


class RowKindError(Y2BackendError):
    """A row kind was unknown or its body did not satisfy the registry."""


class ToolError(Y2BackendError):
    """A collaboration tool was missing, malformed or mis-dispatched."""


class ScreenLeaseError(Y2BackendError):
    """No desktop was available to lease, or a lease was unrecognised."""


class RateLimitError(Y2BackendError):
    """A rate-limit or executor configuration was invalid."""


class CompactionError(Y2BackendError):
    """A compaction configuration or turn was invalid."""


class SchedulerFlagError(Y2BackendError):
    """The NO_SCHEDULER flag or environment value was malformed."""


class RenamePathError(Y2BackendError):
    """A rename fallback or a guarded symlink could not be applied."""


class VoiceError(Y2BackendError):
    """A realtime secret, hand-off or media proxy call was invalid."""


class AudioFixtureError(Y2BackendError):
    """The prepared-audio fixture was missing or could not be built."""


class StreamError(Y2BackendError):
    """An SSE stream event or user id was invalid."""


class RoutineError(Y2BackendError):
    """A routine, cron expression or trigger was invalid."""


_MENTION_RE = re.compile(r"@([A-Za-z0-9_.\-]+)")


def parse_mentions(text: str) -> tuple[str, ...]:
    """Parse @mentions in wire order, de-duplicated without sorting."""
    out: list[str] = []
    for match in _MENTION_RE.finditer(str(text or "")):
        token = match.group(1)
        if token not in out:
            out.append(token)
    return tuple(out)


# ---------------------------------------------------------------------------
# Y2.9 -- card and event row kinds (registry in the UI component list)
# ---------------------------------------------------------------------------


class RowFamily(str, Enum):
    TRANSCRIPT = "transcript"
    CARD = "card"
    EVENT = "event"
    NOTICE = "notice"


class CardKind(str, Enum):
    APPROVAL = "approval"
    QUESTION = "question"
    CONNECT = "connect"
    DRAFT = "draft"


class EventKind(str, Enum):
    ROUTINE_CREATED = "routine_created"
    ROUTINE_RUN = "routine_run"
    VOICE_CALL = "voice_call"
    GROUP_CREATED = "group_created"
    GROUP_MEMBER_ADDED = "group_member_added"
    GROUP_MEMBER_REMOVED = "group_member_removed"
    NOTICE = "notice"


@dataclass(frozen=True)
class RowKindSpec:
    """One registered row kind and the UI component that renders it (9.2)."""

    name: str
    family: RowFamily
    component: str
    required_body: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", RowFamily(self.family))
        if not self.name or not self.component:
            raise RowKindError("a row-kind spec needs a name and a component")
        object.__setattr__(self, "required_body", tuple(self.required_body))

    def to_dict(self) -> dict:
        return {"name": self.name, "family": self.family.value,
                "component": self.component,
                "required_body": list(self.required_body)}


TRANSCRIPT_KIND_SPECS: tuple[RowKindSpec, ...] = (
    RowKindSpec("system", RowFamily.TRANSCRIPT, "TranscriptRow", ("text",)),
    RowKindSpec("user", RowFamily.TRANSCRIPT, "TranscriptRow", ("text",)),
    RowKindSpec("assistant", RowFamily.TRANSCRIPT, "TranscriptRow", ("text",)),
    RowKindSpec("tool", RowFamily.TRANSCRIPT, "ToolRow",
                ("tool_use_id", "phase")),
    RowKindSpec("reasoning", RowFamily.TRANSCRIPT, "ReasoningRow",
                ("reasoning",)),
)

CARD_KIND_SPECS: tuple[RowKindSpec, ...] = (
    RowKindSpec("approval", RowFamily.CARD, "ApprovalCard",
                ("tool_name", "tool_use_id")),
    RowKindSpec("question", RowFamily.CARD, "QuestionCard", ("question",)),
    RowKindSpec("connect", RowFamily.CARD, "ConnectCard", ("connector",)),
    RowKindSpec("draft", RowFamily.CARD, "DraftCard", ("draft",)),
)

EVENT_KIND_SPECS: tuple[RowKindSpec, ...] = (
    RowKindSpec("routine_created", RowFamily.EVENT, "EventRow", ("routine_id",)),
    RowKindSpec("routine_run", RowFamily.EVENT, "EventRow", ("routine_id",)),
    RowKindSpec("voice_call", RowFamily.EVENT, "EventRow", ("call_id",)),
    RowKindSpec("group_created", RowFamily.EVENT, "EventRow", ("room_id",)),
    RowKindSpec("group_member_added", RowFamily.EVENT, "EventRow",
                ("room_id", "actor")),
    RowKindSpec("group_member_removed", RowFamily.EVENT, "EventRow",
                ("room_id", "actor")),
    RowKindSpec("notice", RowFamily.NOTICE, "NoticeRow", ("text",)),
)

DEFAULT_ROW_KIND_SPECS = (TRANSCRIPT_KIND_SPECS + CARD_KIND_SPECS
                          + EVENT_KIND_SPECS)


class RowKindRegistry:
    """The backend half of the UI component list: kinds, families, schemas."""

    def __init__(self, specs: Iterable[RowKindSpec] | None = None,
                 *, seed_defaults: bool = True) -> None:
        self._specs: dict[str, RowKindSpec] = {}
        if seed_defaults:
            for spec in DEFAULT_ROW_KIND_SPECS:
                self.register(spec)
        for spec in (specs or ()):
            self.register(spec)

    def register(self, spec: RowKindSpec) -> RowKindSpec:
        if not isinstance(spec, RowKindSpec):
            raise RowKindError("only RowKindSpec objects can be registered")
        if spec.name in self._specs:
            raise RowKindError(f"row kind already registered: {spec.name}")
        self._specs[spec.name] = spec
        return spec

    def get(self, name: str) -> RowKindSpec:
        try:
            return self._specs[str(name)]
        except KeyError:
            raise RowKindError(f"unknown row kind: {name!r}") from None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def component_for(self, name: str) -> str:
        return self.get(name).component

    def kinds_for(self, family: RowFamily | str) -> tuple[str, ...]:
        wanted = RowFamily(family)
        return tuple(sorted(s.name for s in self._specs.values()
                            if s.family is wanted))

    def validate(self, name: str, body: Mapping[str, Any]) -> RowKindSpec:
        spec = self.get(name)
        if not isinstance(body, Mapping):
            raise RowKindError(f"{name!r} row body must be a mapping")
        missing = tuple(key for key in spec.required_body if key not in body)
        if missing:
            raise RowKindError(
                f"{name!r} row is missing body fields: {', '.join(missing)}")
        return spec

    def make_row(self, name: str, body: Mapping[str, Any], *,
                 clock: Callable[[], float] | None = None) -> dict:
        spec = self.validate(name, body)
        payload = dict(body)
        return {
            "id": new_id("row", name, payload),
            "kind": spec.name,
            "family": spec.family.value,
            "component": spec.component,
            "body": payload,
            "created_at": timestamp(clock),
        }

    def to_dict(self) -> dict:
        return {name: self._specs[name].to_dict() for name in self.names()}


DEFAULT_ROW_KIND_REGISTRY = RowKindRegistry()


# ---------------------------------------------------------------------------
# Y2.10 -- stay_silent and request_app_connection tools
# ---------------------------------------------------------------------------


TOOL_STAY_SILENT = {
    "name": "stay_silent",
    "description": "Choose not to reply to a group thread that did not address you.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "agent_id": {"type": "string"},
            "group": {"type": "boolean", "default": False},
            "addressed_agents": {"type": "array", "items": {"type": "string"}},
            "author_id": {"type": "string", "default": ""},
        },
        "required": ["message", "agent_id"],
    },
}

TOOL_REQUEST_APP_CONNECTION = {
    "name": "request_app_connection",
    "description": "Ask the user to connect an app; renders a connect card.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "connector": {"type": "string"},
            "reason": {"type": "string", "default": ""},
        },
        "required": ["connector"],
    },
}


@dataclass(frozen=True)
class StaySilentDecision:
    silent: bool
    agent_id: str
    reason: str

    def to_dict(self) -> dict:
        return {"silent": self.silent, "agent_id": self.agent_id,
                "reason": self.reason}


def should_stay_silent(message: str, agent_id: str, *,
                       group: bool = False,
                       addressed_agents: Sequence[str] = (),
                       author_id: str = "") -> StaySilentDecision:
    """A group message that did not address this agent is left unanswered."""
    agent = str(agent_id)
    if not agent:
        raise ToolError("stay_silent needs an agent_id")
    if not group:
        return StaySilentDecision(False, agent, "not a group thread")
    mentions = set(addressed_agents) | set(parse_mentions(message))
    if agent == author_id:
        return StaySilentDecision(False, agent, "agent authored the message")
    if agent in mentions:
        return StaySilentDecision(False, agent, "agent was addressed")
    return StaySilentDecision(True, agent,
                              "group message did not address this agent")


@dataclass(frozen=True)
class ConnectCard:
    """A Y2.9 ``connect`` card whose action opens the connector form."""

    id: str
    connector: str
    reason: str
    action: str = "open_connector_form"
    created_at: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": "connect", "connector": self.connector,
                "reason": self.reason, "action": self.action,
                "form": self.connector, "created_at": self.created_at}


def request_app_connection(connector: str, reason: str = "", *,
                           clock: Callable[[], float] | None = None) -> ConnectCard:
    name = str(connector).strip()
    if not name:
        raise ToolError("request_app_connection needs a connector")
    return ConnectCard(id=new_id("connect", name, reason),
                       connector=name, reason=str(reason),
                       created_at=timestamp(clock))


@dataclass(frozen=True)
class ToolResult:
    tool: str
    ok: bool
    data: dict = field(default_factory=dict)
    connect_card: dict | None = None

    def to_dict(self) -> dict:
        return {"tool": self.tool, "ok": self.ok, "data": dict(self.data),
                "connect_card": self.connect_card}


class CollabToolRegistry:
    """Small tool registry/dispatcher for the two collaboration tools."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock
        self._tools: dict[str, dict] = {}

    def register(self, schema: dict) -> dict:
        if not isinstance(schema, dict) or not schema.get("name"):
            raise ToolError("tool schema needs a name")
        self._tools[str(schema["name"])] = schema
        return schema

    def install_defaults(self) -> "CollabToolRegistry":
        self.register(TOOL_STAY_SILENT)
        self.register(TOOL_REQUEST_APP_CONNECTION)
        return self

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def schema(self, name: str) -> dict:
        try:
            return self._tools[str(name)]
        except KeyError:
            raise ToolError(f"unknown tool: {name!r}") from None

    def dispatch(self, name: str, arguments: Mapping[str, Any], *,
                 context: Mapping[str, Any] | None = None) -> ToolResult:
        self.schema(name)
        args = dict(arguments or {})
        if context:
            for key, value in context.items():
                args.setdefault(key, value)
        if name == "stay_silent":
            if "message" not in args or "agent_id" not in args:
                raise ToolError("stay_silent needs message and agent_id")
            decision = should_stay_silent(
                str(args["message"]), str(args["agent_id"]),
                group=bool(args.get("group", False)),
                addressed_agents=tuple(args.get("addressed_agents") or ()),
                author_id=str(args.get("author_id") or ""))
            return ToolResult(name, True, decision.to_dict())
        if name == "request_app_connection":
            if "connector" not in args:
                raise ToolError("request_app_connection needs a connector")
            card = request_app_connection(str(args["connector"]),
                                          str(args.get("reason") or ""),
                                          clock=self._clock)
            return ToolResult(name, True, card.to_dict(), card.to_dict())
        raise ToolError(f"tool has no backend handler: {name!r}")


DEFAULT_COLLAB_TOOLS = CollabToolRegistry().install_defaults()


# ---------------------------------------------------------------------------
# Y2.11 -- send_to_bot, hidden subagents, group rooms (3-member cap)
# ---------------------------------------------------------------------------


GROUP_RESPONDER_CAP = 3
LOOP_GUARD_MAX_CONSECUTIVE = 3
MAX_HIDDEN_CHILDREN = 8


@dataclass(frozen=True)
class BotMessage:
    id: str
    sender: str
    recipient: str
    text: str
    created_at: str

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def send_to_bot(sender: str, recipient: str, text: str, *,
                clock: Callable[[], float] | None = None) -> BotMessage:
    if not sender or not recipient:
        raise ToolError("send_to_bot needs a sender and a recipient")
    return BotMessage(id=new_id("bot", sender, recipient, text),
                      sender=str(sender), recipient=str(recipient),
                      text=str(text), created_at=timestamp(clock))


@dataclass(frozen=True)
class Subagent:
    id: str
    parent_id: str
    context: dict
    screen: str | None
    hidden: bool = True
    active: bool = True

    def to_dict(self) -> dict:
        return {"id": self.id, "parent_id": self.parent_id,
                "context": dict(self.context), "screen": self.screen,
                "hidden": self.hidden, "active": self.active}


class SubagentManager:
    """Hidden child agents with their own context/screen, removed on stop."""

    def __init__(self) -> None:
        self._children: dict[str, Subagent] = {}
        self._lock = threading.RLock()

    def spawn(self, parent_id: str, child_id: str, *,
              context: Mapping[str, Any] | None = None,
              screen: str | None = None) -> Subagent:
        if not parent_id or not child_id:
            raise ToolError("spawn needs a parent_id and a child_id")
        with self._lock:
            if child_id in self._children:
                raise ToolError(f"subagent id already used: {child_id}")
            if len([a for a in self._children.values() if a.active]) >= MAX_HIDDEN_CHILDREN:
                raise ToolError(f"too many active subagents (max {MAX_HIDDEN_CHILDREN})")
            child = Subagent(id=child_id, parent_id=parent_id,
                             context=dict(context or {}), screen=screen)
            self._children[child_id] = child
            return child

    def stop_subagent(self, child_id: str) -> Subagent:
        """Remove the child's context and screen; the child stays hidden."""
        with self._lock:
            child = self._children.get(child_id)
            if child is None:
                raise ToolError(f"unknown subagent: {child_id}")
            if not child.active:
                raise ToolError(f"subagent already stopped: {child_id}")
            stopped = replace(child, context={}, screen=None, active=False)
            self._children[child_id] = stopped
            return stopped

    def get(self, child_id: str) -> Subagent:
        try:
            return self._children[child_id]
        except KeyError:
            raise ToolError(f"unknown subagent: {child_id}") from None

    def is_hidden(self, child_id: str) -> bool:
        return self.get(child_id).hidden

    def children(self, parent_id: str) -> tuple[Subagent, ...]:
        return tuple(a for a in self._children.values()
                     if a.parent_id == parent_id)

    def snapshot(self) -> tuple[dict, ...]:
        return tuple(a.to_dict() for a in self._children.values())


@dataclass(frozen=True)
class GroupRouting:
    room_id: str
    message_id: str
    sender: str
    mentioned: tuple[str, ...]
    responders: tuple[str, ...]
    deferred: tuple[str, ...] = ()
    capped: bool = False
    reason: str = "routed"

    def to_dict(self) -> dict:
        return {"room_id": self.room_id, "message_id": self.message_id,
                "sender": self.sender, "mentioned": list(self.mentioned),
                "responders": list(self.responders),
                "deferred": list(self.deferred), "capped": self.capped,
                "reason": self.reason}


class GroupRoom:
    """@mention routing with a default 3-responder cap and a loop guard."""

    def __init__(self, room_id: str, members: Iterable[str] = (),
                 name: str = "",
                 responder_cap: int = GROUP_RESPONDER_CAP) -> None:
        if not room_id:
            raise ToolError("a group room needs an id")
        if not 1 <= responder_cap <= GROUP_RESPONDER_CAP:
            raise ToolError(f"responder_cap must be in 1..{GROUP_RESPONDER_CAP}")
        self.room_id = str(room_id)
        self.name = str(name)
        self.responder_cap = int(responder_cap)
        self._members: OrderedDict[str, None] = OrderedDict()
        self._consecutive: dict[str, int] = {}
        for member in members:
            self.add_member(member)

    def add_member(self, agent_id: str) -> None:
        if not agent_id:
            raise ToolError("member id must be non-empty")
        self._members[str(agent_id)] = None

    def remove_member(self, agent_id: str) -> None:
        self._members.pop(str(agent_id), None)
        self._consecutive.pop(str(agent_id), None)

    @property
    def members(self) -> tuple[str, ...]:
        return tuple(self._members)

    def post(self, sender: str, text: str, *,
             mentions: Sequence[str] = (),
             clock: Callable[[], float] | None = None) -> GroupRouting:
        sender = str(sender)
        parsed = tuple(mentions) if mentions else parse_mentions(text)
        mentioned = tuple(dict.fromkeys(str(m) for m in parsed))
        candidates = [m for m in mentioned
                      if m in self._members and m != sender
                      and self._consecutive.get(m, 0) < LOOP_GUARD_MAX_CONSECUTIVE]
        responders = tuple(candidates[:self.responder_cap])
        deferred = tuple(candidates[self.responder_cap:])
        for member in self._members:
            self._consecutive[member] = (
                self._consecutive.get(member, 0) + 1 if member in responders else 0)
        reason = "loop_guard" if mentioned and not candidates and not deferred else (
            "routed" if responders else "no_responding_member")
        return GroupRouting(
            room_id=self.room_id,
            message_id=new_id("group", self.room_id, sender, text),
            sender=sender, mentioned=mentioned, responders=responders,
            deferred=deferred, capped=bool(deferred), reason=reason)


def post_to_group(room: GroupRoom, sender: str, text: str, *,
                  mentions: Sequence[str] = (),
                  clock: Callable[[], float] | None = None) -> GroupRouting:
    if not isinstance(room, GroupRoom):
        raise ToolError("post_to_group needs a GroupRoom")
    return room.post(sender, text, mentions=mentions, clock=clock)


# ---------------------------------------------------------------------------
# Y2.12 -- screen leasing: one VM, four desktops, LRU among idle agents
# ---------------------------------------------------------------------------


MAX_DESKTOPS = 4


@dataclass(frozen=True)
class ScreenLease:
    desktop_id: str
    agent_id: str
    vm: str
    leased_at: int

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass
class _Desktop:
    id: str
    vm: str
    busy: bool = False
    agent_id: str = ""
    last_released: int = 0


class DesktopPool:
    """Lease up to four desktops, least-recently-released idle one first."""

    def __init__(self, vm: str = "vm-1", capacity: int = MAX_DESKTOPS) -> None:
        if not 1 <= capacity <= MAX_DESKTOPS:
            raise ScreenLeaseError(f"capacity must be in 1..{MAX_DESKTOPS}")
        self.vm = str(vm)
        self._clock_tick = 0
        self._desktops: list[_Desktop] = [
            _Desktop(id=f"desktop-{i}", vm=self.vm)
            for i in range(1, capacity + 1)]
        self._leases: dict[str, ScreenLease] = {}
        self._lock = threading.RLock()

    def tick(self) -> int:
        with self._lock:
            self._clock_tick += 1
            return self._clock_tick

    @property
    def size(self) -> int:
        return len(self._desktops)

    def lease(self, agent_id: str) -> ScreenLease:
        if not agent_id:
            raise ScreenLeaseError("an agent id is required to lease")
        agent_id = str(agent_id)
        with self._lock:
            existing = self._leases.get(agent_id)
            if existing is not None:
                return existing
            idle = [d for d in self._desktops if not d.busy]
            if not idle:
                raise ScreenLeaseError(f"no idle desktop on {self.vm}")
            chosen = min(idle, key=lambda d: (d.last_released, d.id))
            chosen.busy = True
            chosen.agent_id = agent_id
            lease = ScreenLease(chosen.id, agent_id, self.vm, self._clock_tick)
            self._leases[agent_id] = lease
            return lease

    def release(self, agent_id: str) -> ScreenLease:
        with self._lock:
            lease = self._leases.pop(agent_id, None)
            if lease is None:
                raise ScreenLeaseError(f"no lease held by {agent_id!r}")
            desktop = next(d for d in self._desktops
                           if d.id == lease.desktop_id)
            self._clock_tick += 1
            desktop.busy = False
            desktop.agent_id = ""
            desktop.last_released = self._clock_tick
            return lease

    def idle_count(self) -> int:
        return sum(1 for d in self._desktops if not d.busy)

    def busy_count(self) -> int:
        return sum(1 for d in self._desktops if d.busy)

    def snapshot(self) -> tuple[dict, ...]:
        return tuple({"id": d.id, "vm": d.vm, "busy": d.busy,
                      "agent_id": d.agent_id,
                      "last_released": d.last_released}
                     for d in self._desktops)


# ---------------------------------------------------------------------------
# Y2.13 -- idle suspend knobs (20 min / 60 s sweep / dry-run)
# ---------------------------------------------------------------------------


DEFAULT_IDLE_SUSPEND_SECONDS = 20 * 60
DEFAULT_SWEEP_INTERVAL_SECONDS = 60


@dataclass(frozen=True)
class SuspendDecision:
    resource_id: str
    action: str              # suspend | keep
    idle_seconds: float
    applied: bool
    dry_run: bool
    reason: str

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


class ResourceManager:
    """Sweep idle resources; a dry run logs decisions without acting."""

    def __init__(self, *, idle_timeout_seconds: int = DEFAULT_IDLE_SUSPEND_SECONDS,
                 sweep_interval_seconds: int = DEFAULT_SWEEP_INTERVAL_SECONDS,
                 dry_run: bool = True,
                 clock: Callable[[], float] | None = None) -> None:
        if idle_timeout_seconds <= 0 or sweep_interval_seconds <= 0:
            raise Y2BackendError("idle timeout and sweep interval must be positive")
        self.idle_timeout_seconds = int(idle_timeout_seconds)
        self.sweep_interval_seconds = int(sweep_interval_seconds)
        self.dry_run = bool(dry_run)
        self._clock = clock
        self._activity: dict[str, float] = {}
        self._suspended: set[str] = set()
        self._decisions: list[SuspendDecision] = []
        self._lock = threading.RLock()

    def _now(self, now: float | None) -> float:
        return float(now) if now is not None else float(
            self._clock() if self._clock is not None else time.time())

    def register(self, resource_id: str, *, now: float | None = None) -> None:
        if not resource_id:
            raise Y2BackendError("a resource id is required")
        with self._lock:
            self._activity[str(resource_id)] = self._now(now)

    def touch(self, resource_id: str, *, now: float | None = None) -> None:
        with self._lock:
            key = str(resource_id)
            self._activity[key] = self._now(now)
            self._suspended.discard(key)

    def sweep(self, *, now: float | None = None) -> tuple[SuspendDecision, ...]:
        current = self._now(now)
        batch: list[SuspendDecision] = []
        with self._lock:
            for resource_id in sorted(self._activity):
                idle = current - self._activity[resource_id]
                if idle < self.idle_timeout_seconds:
                    batch.append(SuspendDecision(
                        resource_id, "keep", idle, False, self.dry_run,
                        "below idle timeout"))
                    continue
                applied = False
                if not self.dry_run and resource_id not in self._suspended:
                    self._suspended.add(resource_id)
                    applied = True
                batch.append(SuspendDecision(
                    resource_id, "suspend", idle, applied, self.dry_run,
                    "dry run: decision logged, no action"
                    if self.dry_run else "idle timeout reached"))
            self._decisions.extend(batch)
            return tuple(batch)

    @property
    def suspended(self) -> tuple[str, ...]:
        return tuple(sorted(self._suspended))

    @property
    def decisions(self) -> tuple[SuspendDecision, ...]:
        return tuple(self._decisions)

    def settings(self) -> dict:
        """Values for the settings page (Y2.13 acceptance criterion)."""
        return {"idle_suspend_seconds": self.idle_timeout_seconds,
                "sweep_interval_seconds": self.sweep_interval_seconds,
                "dry_run": self.dry_run}


# ---------------------------------------------------------------------------
# Y2.15 -- rate-limit awareness + in-VM executor seam (≈600 calls/min/computer)
# ---------------------------------------------------------------------------


DEFAULT_CONTROL_CALLS_PER_MINUTE = 600


class TokenBucket:
    """A thread-safe token bucket; ~600 desktop control calls/min by default."""

    def __init__(self, rate_per_minute: int = DEFAULT_CONTROL_CALLS_PER_MINUTE,
                 *, capacity: float | None = None,
                 clock: Callable[[], float] | None = None) -> None:
        if rate_per_minute <= 0:
            raise RateLimitError("rate_per_minute must be positive")
        self.rate_per_minute = float(rate_per_minute)
        self.rate_per_second = self.rate_per_minute / 60.0
        self.capacity = float(capacity) if capacity is not None else self.rate_per_minute
        if self.capacity <= 0:
            raise RateLimitError("bucket capacity must be positive")
        self._clock = clock
        self._tokens = self.capacity
        self._last = self._now(None)
        self._lock = threading.RLock()

    def _now(self, now: float | None) -> float:
        return float(now) if now is not None else float(
            self._clock() if self._clock is not None else time.time())

    def _refill(self, now: float) -> None:
        if now > self._last:
            elapsed = now - self._last
            self._tokens = min(self.capacity,
                               self._tokens + elapsed * self.rate_per_second)
            self._last = now
        elif now < self._last:
            # A clock regression must not mint tokens.
            self._last = now

    def allow(self, cost: float = 1.0, *, now: float | None = None) -> bool:
        if cost <= 0 or cost > self.capacity:
            raise RateLimitError("cost must be in (0, capacity]")
        current = self._now(now)
        with self._lock:
            self._refill(current)
            if self._tokens >= cost:
                self._tokens -= cost
                return True
            return False

    def available(self, *, now: float | None = None) -> float:
        current = self._now(now)
        with self._lock:
            self._refill(current)
            return self._tokens

    def retry_after(self, cost: float = 1.0, *,
                    now: float | None = None) -> float:
        current = self._now(now)
        with self._lock:
            self._refill(current)
            missing = max(0.0, cost - self._tokens)
            return missing / self.rate_per_second if self.rate_per_second else 0.0


@dataclass(frozen=True)
class RateDecision:
    computer_id: str
    allowed: bool
    retry_after_seconds: float = 0.0
    reason: str = "within budget"

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


class RateLimiter:
    """One token bucket per computer for desktop control actions."""

    def __init__(self, rate_per_minute: int = DEFAULT_CONTROL_CALLS_PER_MINUTE,
                 *, clock: Callable[[], float] | None = None) -> None:
        self.rate_per_minute = rate_per_minute
        self._clock = clock
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.RLock()

    def bucket(self, computer_id: str) -> TokenBucket:
        with self._lock:
            key = str(computer_id)
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(
                    self.rate_per_minute, clock=self._clock)
            return self._buckets[key]

    def check(self, computer_id: str, *, now: float | None = None) -> RateDecision:
        bucket = self.bucket(computer_id)
        allowed = bucket.allow(now=now)
        return RateDecision(
            computer_id=str(computer_id), allowed=allowed,
            retry_after_seconds=0.0 if allowed else round(
                bucket.retry_after(now=now), 6),
            reason="within budget" if allowed else "rate limit reached")


@dataclass(frozen=True)
class DesktopAction:
    computer_id: str
    kind: str
    payload: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return new_id("action", self.computer_id, self.kind, self.payload)

    def to_dict(self) -> dict:
        return {"id": self.id, "computer_id": self.computer_id,
                "kind": self.kind, "payload": dict(self.payload)}


@dataclass(frozen=True)
class ExecutionReceipt:
    id: str
    action_id: str
    status: str            # accepted | rate_limited
    computer_id: str

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


class ExecutorSeam:
    """Stand-in for the C1.11 in-VM executor; no real action is taken here."""

    def execute(self, action: DesktopAction) -> ExecutionReceipt:  # pragma: no cover
        raise NotImplementedError


class RecordingExecutorSeam(ExecutorSeam):
    def __init__(self) -> None:
        self._actions: list[DesktopAction] = []

    def execute(self, action: DesktopAction) -> ExecutionReceipt:
        self._actions.append(action)
        return ExecutionReceipt(new_id("receipt", action.id, "accepted"),
                                action.id, "accepted", action.computer_id)

    @property
    def actions(self) -> tuple[DesktopAction, ...]:
        return tuple(self._actions)


class InVmExecutor:
    """Check the rate limit before forwarding an action to the C1.11 seam."""

    def __init__(self, *, limiter: RateLimiter | None = None,
                 seam: ExecutorSeam | None = None) -> None:
        self.limiter = limiter or RateLimiter()
        self.seam = seam or RecordingExecutorSeam()

    def submit(self, action: DesktopAction, *,
               now: float | None = None) -> ExecutionReceipt:
        if not isinstance(action, DesktopAction) or not action.computer_id:
            raise RateLimitError("submit needs a DesktopAction with a computer_id")
        decision = self.limiter.check(action.computer_id, now=now)
        if not decision.allowed:
            # Never forwarded: the executor did not run the action.
            return ExecutionReceipt(
                new_id("receipt", action.id, "rate_limited"),
                action.id, "rate_limited", action.computer_id)
        return self.seam.execute(action)


# ---------------------------------------------------------------------------
# Y2.16 -- compaction knobs (trigger size, keep-last-N, method, memory budget)
# ---------------------------------------------------------------------------


DEFAULT_KEEP_LAST_USER_TURNS = 4
DEFAULT_COMPACTION_TRIGGER_CHARS = 100_000
DEFAULT_MEMORY_BUDGET_CHARS = 4_000
DEFAULT_IDLE_CONSOLIDATION_SECONDS = 10 * 60
DEFAULT_CONSOLIDATION_SWEEP_SECONDS = 60


class CompactionMethod(str, Enum):
    AUTO = "auto"
    SUMMARY = "summary"


@dataclass(frozen=True)
class CompactionConfig:
    trigger_chars: int = DEFAULT_COMPACTION_TRIGGER_CHARS
    keep_last_user_turns: int = DEFAULT_KEEP_LAST_USER_TURNS
    method: CompactionMethod | str = CompactionMethod.AUTO
    idle_consolidation_seconds: int = DEFAULT_IDLE_CONSOLIDATION_SECONDS
    consolidation_sweep_seconds: int = DEFAULT_CONSOLIDATION_SWEEP_SECONDS
    memory_budget_chars: int = DEFAULT_MEMORY_BUDGET_CHARS

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", CompactionMethod(self.method))
        for name in ("trigger_chars", "keep_last_user_turns",
                     "idle_consolidation_seconds", "consolidation_sweep_seconds",
                     "memory_budget_chars"):
            if getattr(self, name) < 0:
                raise CompactionError(f"{name} must be >= 0")
        if self.memory_budget_chars == 0:
            raise CompactionError("memory_budget_chars must be positive")

    def to_dict(self) -> dict:
        return {"trigger_chars": self.trigger_chars,
                "keep_last_user_turns": self.keep_last_user_turns,
                "method": self.method.value,
                "idle_consolidation_seconds": self.idle_consolidation_seconds,
                "consolidation_sweep_seconds": self.consolidation_sweep_seconds,
                "memory_budget_chars": self.memory_budget_chars}


@dataclass(frozen=True)
class Turn:
    id: str
    role: str
    text: str

    def __post_init__(self) -> None:
        if self.role not in ("user", "assistant", "system", "tool"):
            raise CompactionError(f"unknown turn role: {self.role!r}")


@dataclass(frozen=True)
class CompactionPlan:
    should_compact: bool
    reason: str
    method: CompactionMethod
    verbatim_turns: tuple[Turn, ...]
    summary_text: str
    memory_budget_chars: int

    def render_memory(self) -> str:
        """Never exceed the in-prompt memory budget; mark truncation honestly."""
        budget = self.memory_budget_chars
        if len(self.summary_text) <= budget:
            return self.summary_text
        if budget <= len("[truncated]"):
            return self.summary_text[:budget]
        return self.summary_text[:budget - len("[truncated]")] + "[truncated]"

    def to_dict(self) -> dict:
        return {"should_compact": self.should_compact, "reason": self.reason,
                "method": self.method.value,
                "verbatim_ids": tuple(t.id for t in self.verbatim_turns),
                "memory_budget_chars": self.memory_budget_chars,
                "rendered_memory": self.render_memory()}


def plan_compaction(turns: Sequence[Turn], config: CompactionConfig, *,
                    last_activity: float, now: float) -> CompactionPlan:
    """Build a bounded compaction plan from size + idle triggers."""
    if not isinstance(config, CompactionConfig):
        raise CompactionError("config must be a CompactionConfig")
    items = tuple(turns)
    if any(not isinstance(t, Turn) for t in items):
        raise CompactionError("compaction turns must be Turn objects")
    total_chars = sum(len(t.text) for t in items)
    idle = max(0.0, float(now) - float(last_activity))
    size_due = bool(config.trigger_chars) and total_chars >= config.trigger_chars
    idle_due = bool(config.idle_consolidation_seconds) and (
        idle >= config.idle_consolidation_seconds)
    should = size_due or idle_due
    method = config.method
    # 'summary' always summarises; 'auto' only summarises when a trigger fires.
    summarise = should or method is CompactionMethod.SUMMARY
    user_turns = [t for t in items if t.role == "user"]
    verbatim = tuple(user_turns[-config.keep_last_user_turns:]) if summarise else ()
    verbatim_ids = {id(t) for t in verbatim}
    summary = "\n".join(t.text for t in items if id(t) not in verbatim_ids) \
        if summarise else ""
    if size_due:
        reason = "size trigger"
    elif idle_due:
        reason = "idle consolidation"
    elif method is CompactionMethod.SUMMARY:
        reason = "summary method"
    else:
        reason = "below trigger"
    return CompactionPlan(should, reason, method, verbatim, summary,
                          config.memory_budget_chars)


# ---------------------------------------------------------------------------
# Y2.17 -- prompt cache key per agent+generation, hashed safety identifier
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderIdentity:
    cache_key: str
    local_prefix: str
    safety_identifier: str

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def prompt_cache_key(agent_id: str, generation: int, *, model: str = "",
                     prefix: str = "") -> str:
    """Stable across calls for the same agent+generation; never time-based."""
    if not agent_id or generation < 1:
        raise Y2BackendError("prompt cache needs an agent_id and generation>=1")
    return new_id("cache", agent_id, int(generation), model, prefix)


def local_prefix(agent_id: str, generation: int) -> str:
    """Prefix kept stable for local servers so their KV cache is reused."""
    return f"keel:{agent_id}:{int(generation)}:"


def safety_identifier(user_id: str) -> str:
    """A hashed safety id; the raw user id is never sent to a provider."""
    if not user_id:
        raise Y2BackendError("safety_identifier needs a user id")
    return "user_" + new_id("safety", user_id, length=24)


def build_provider_identity(agent_id: str, generation: int, user_id: str, *,
                            model: str = "") -> ProviderIdentity:
    return ProviderIdentity(
        cache_key=prompt_cache_key(agent_id, generation, model=model),
        local_prefix=local_prefix(agent_id, generation),
        safety_identifier=safety_identifier(user_id))


def assert_no_raw_identifier(identity: ProviderIdentity, raw_user_id: str) -> bool:
    if raw_user_id and raw_user_id in json.dumps(identity.to_dict()):
        raise Y2BackendError("raw user identifier leaked into provider identity")
    return True


# ---------------------------------------------------------------------------
# Y2.18 -- NO_SCHEDULER flag (--no-scheduler / KEEL_NO_SCHEDULER)
# ---------------------------------------------------------------------------


NO_SCHEDULER_ENV = "KEEL_NO_SCHEDULER"
_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on", "y", "t"})
_FALSE_ENV_VALUES = frozenset({"0", "false", "no", "off", "n", "f", ""})


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool   # True means the scheduler is disabled
    source: str     # cli | env | default

    def to_dict(self) -> dict:
        return {"no_scheduler": self.enabled, "source": self.source}


def _env_flag(value: str) -> bool:
    normalised = str(value).strip().lower()
    if normalised in _TRUE_ENV_VALUES:
        return True
    if normalised in _FALSE_ENV_VALUES:
        return False
    raise SchedulerFlagError(
        f"{NO_SCHEDULER_ENV} must be a boolean, got {value!r}")


def parse_scheduler_flag(argv: Sequence[str] | None = None,
                         environ: Mapping[str, str] | None = None) -> SchedulerConfig:
    args = tuple(argv) if argv is not None else tuple(
        __import__("sys").argv[1:])
    env = environ if environ is not None else os.environ
    if "--no-scheduler" in args:
        return SchedulerConfig(True, "cli")
    if NO_SCHEDULER_ENV in env:
        return SchedulerConfig(_env_flag(env[NO_SCHEDULER_ENV]), "env")
    return SchedulerConfig(False, "default")


def strip_no_scheduler(argv: Sequence[str]) -> tuple[str, ...]:
    """Return argv without the flag so an ordinary CLI parser still works."""
    return tuple(a for a in argv if a != "--no-scheduler")


def should_run_scheduler(config: SchedulerConfig) -> bool:
    return not config.enabled


# ---------------------------------------------------------------------------
# Y2.19 -- backward-compatible rename path (env / DB / cookie / data dir)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompatRenames:
    """New name -> old name for each renamed resource."""

    env: Mapping[str, str] = field(default_factory=dict)
    db_filename: tuple[str, str] = ("keel.db", "keel-old.db")
    cookie_name: tuple[str, str] = ("keel_session", "keel_session_old")
    data_dir: tuple[str, str] = ("data", "data-old")


@dataclass(frozen=True)
class CompatReport:
    env_fallbacks: tuple[tuple[str, str], ...] = ()
    db_used_old: bool = False
    cookie_used_old: bool = False
    symlink_created: bool = False
    symlink_error: str = ""

    def to_dict(self) -> dict:
        return {"env_fallbacks": [list(pair) for pair in self.env_fallbacks],
                "db_used_old": self.db_used_old,
                "cookie_used_old": self.cookie_used_old,
                "symlink_created": self.symlink_created,
                "symlink_error": self.symlink_error}


class RenameCompat:
    """Read old names as fallbacks, keep old files, guard the compat symlink."""

    def __init__(self, base: str | Path, renames: CompatRenames | None = None) -> None:
        self.base = Path(base)
        self.renames = renames or CompatRenames()
        self._env_fallbacks: list[tuple[str, str]] = []
        self._db_used_old = False
        self._cookie_used_old = False
        self._symlink_created = False
        self._symlink_error = ""

    def env(self, environ: Mapping[str, str], name: str,
            default: str = "") -> str:
        old = self.renames.env.get(name)
        if name in environ:
            return str(environ[name])
        if old and old in environ:
            self._env_fallbacks.append((name, old))
            return str(environ[old])
        return default

    def database_path(self) -> Path:
        new_name, old_name = self.renames.db_filename
        new_path = self.base / new_name
        if new_path.exists():
            return new_path
        old_path = self.base / old_name
        if old_path.exists():
            self._db_used_old = True
            return old_path
        return new_path

    def cookie(self, cookies: Mapping[str, str], default: str = "") -> str:
        new_name, old_name = self.renames.cookie_name
        if new_name in cookies:
            return str(cookies[new_name])
        if old_name in cookies:
            self._cookie_used_old = True
            return str(cookies[old_name])
        return default

    def ensure_symlink(self) -> bool:
        """Link old data dir -> new one, only if both stay inside *base*."""
        new_name, old_name = self.renames.data_dir
        base = self.base.resolve()
        new_path = (base / new_name)
        old_path = (base / old_name)
        if not new_path.exists() or old_path.exists():
            return False
        try:
            resolved_new = new_path.resolve(strict=True)
            if not resolved_new.is_relative_to(base):
                raise RenamePathError("compat symlink target escapes its base")
            old_path.symlink_to(new_name, target_is_directory=new_path.is_dir())
            self._symlink_created = True
            return True
        except (OSError, RenamePathError) as exc:
            # Symlinks may be unavailable (Windows privileges); never crash.
            self._symlink_error = str(exc)
            return False

    def report(self) -> CompatReport:
        return CompatReport(tuple(self._env_fallbacks), self._db_used_old,
                            self._cookie_used_old, self._symlink_created,
                            self._symlink_error)


# ---------------------------------------------------------------------------
# Y2.21 -- honest "Project status" section (feeds A3.7 About page)
# ---------------------------------------------------------------------------


class VerificationLevel(str, Enum):
    TESTED = "tested"
    BUILT_UNPROVEN = "built-not-proven"
    DOCUMENTED = "documented"
    PLANNED = "planned"


_STATUS_LEVELS = {
    "verified": VerificationLevel.TESTED,
    "tested": VerificationLevel.TESTED,
    "built": VerificationLevel.BUILT_UNPROVEN,
    "implemented": VerificationLevel.BUILT_UNPROVEN,
    "in_progress": VerificationLevel.BUILT_UNPROVEN,
    "documented": VerificationLevel.DOCUMENTED,
    "not_started": VerificationLevel.PLANNED,
}

AUDIT_DISCLAIMER = "Basic review, not a professional audit."
APPROVAL_GAP = (
    "Known approval gap: browser and shell tool calls are not covered by the "
    "approval matrix.")
KNOWN_LIMITS: tuple[str, ...] = (
    "Built does not mean proven in the live runtime; only 'tested' rows carry "
    "passing automated evidence.",
    AUDIT_DISCLAIMER,
    APPROVAL_GAP,
)


def level_for_status(status: str) -> VerificationLevel:
    return _STATUS_LEVELS.get(str(status).strip().lower(),
                              VerificationLevel.PLANNED)


@dataclass(frozen=True)
class StatusEntry:
    feature_id: str
    label: str
    level: VerificationLevel | str
    evidence: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.level, str):
            try:
                level = VerificationLevel(self.level)
            except ValueError:
                level = level_for_status(self.level)
        else:
            level = VerificationLevel(self.level)
        object.__setattr__(self, "level", level)

    def to_dict(self) -> dict:
        return {"feature_id": self.feature_id, "label": self.label,
                "level": self.level.value, "evidence": self.evidence,
                "note": self.note}


@dataclass(frozen=True)
class ProjectStatus:
    entries: tuple[StatusEntry, ...]
    known_limits: tuple[str, ...] = KNOWN_LIMITS

    def groups(self) -> dict[VerificationLevel, tuple[StatusEntry, ...]]:
        return {level: tuple(e for e in self.entries if e.level is level)
                for level in VerificationLevel}

    def render_markdown(self) -> str:
        lines = ["# Project status", "",
                 "Honest status of this build. Categories are evidence-based, "
                 "not aspirational.", ""]
        titles = {
            VerificationLevel.TESTED: "Tested (automated evidence passes)",
            VerificationLevel.BUILT_UNPROVEN: "Built, not proven in the live runtime",
            VerificationLevel.DOCUMENTED: "Documented only",
            VerificationLevel.PLANNED: "Planned / not started",
        }
        grouped = self.groups()
        for level in VerificationLevel:
            lines.append(f"## {titles[level]}")
            lines.append("")
            members = grouped[level]
            if not members:
                lines.append("_None._")
            else:
                for entry in members:
                    suffix = f" — {entry.evidence}" if entry.evidence else ""
                    lines.append(f"- {entry.feature_id} {entry.label}{suffix}")
            lines.append("")
        lines.append("## Known limits")
        lines.append("")
        for limit in self.known_limits:
            lines.append(f"- {limit}")
        lines.append("")
        return "\n".join(lines)

    def to_about_payload(self) -> dict:
        """The machine-readable form consumed by the A3.7 About page."""
        return {"entries": [e.to_dict() for e in self.entries],
                "known_limits": list(self.known_limits),
                "audit_disclaimer": AUDIT_DISCLAIMER,
                "approval_gap": APPROVAL_GAP,
                "markdown": self.render_markdown()}


def build_project_status(entries: Iterable[StatusEntry]) -> ProjectStatus:
    return ProjectStatus(tuple(entries))


def status_from_plan(features: Iterable[Mapping[str, Any]]) -> ProjectStatus:
    """Map PLAN-INDEX rows to honest status levels without changing the plan."""
    entries = []
    for row in features:
        label = str(row.get("feature") or row.get("detail") or "").strip()
        entries.append(StatusEntry(
            feature_id=str(row.get("id", "")), label=label,
            level=level_for_status(str(row.get("status", "not_started"))),
            evidence=str(row.get("verification_evidence") or "")))
    return build_project_status(entries)


# ---------------------------------------------------------------------------
# Y2.22 -- voice: realtime secrets, hand_off_task, TTS preview, STT proxy
# ---------------------------------------------------------------------------


DEFAULT_REALTIME_SECRET_TTL_SECONDS = 300


@dataclass(frozen=True)
class RealtimeSecret:
    """Short-lived token plus its expiry; the token is never logged."""

    token: str
    session_id: str
    expires_at: float
    issued_at: float

    def public_dict(self) -> dict:
        return {"session_id": self.session_id,
                "expires_at": self.expires_at, "issued_at": self.issued_at,
                "token": "[redacted]"}

    def to_dict(self) -> dict:
        return self.public_dict()


class RealtimeSecretIssuer:
    """Issue deterministic, short-lived tokens; no uuid, no RNG."""

    def __init__(self, ttl_seconds: int = DEFAULT_REALTIME_SECRET_TTL_SECONDS,
                 *, clock: Callable[[], float] | None = None) -> None:
        if ttl_seconds <= 0:
            raise VoiceError("ttl_seconds must be positive")
        self.ttl_seconds = int(ttl_seconds)
        self._clock = clock
        self._nonce = 0
        self._revoked: set[str] = set()
        self._lock = threading.RLock()

    def _now(self, now: float | None) -> float:
        return float(now) if now is not None else float(
            self._clock() if self._clock is not None else time.time())

    def issue(self, session_id: str, *, now: float | None = None) -> RealtimeSecret:
        if not session_id:
            raise VoiceError("a session id is required")
        current = self._now(now)
        with self._lock:
            self._nonce += 1
            token = new_id("realtime", session_id, current, self._nonce,
                           length=24)
            return RealtimeSecret(token=token, session_id=str(session_id),
                                  expires_at=current + self.ttl_seconds,
                                  issued_at=current)

    def is_valid(self, secret: RealtimeSecret, *, now: float | None = None) -> bool:
        current = self._now(now)
        with self._lock:
            return (secret.session_id not in self._revoked
                    and secret.expires_at > current)

    def revoke(self, session_id: str) -> None:
        with self._lock:
            self._revoked.add(str(session_id))


@dataclass(frozen=True)
class HandoffTask:
    id: str
    session_id: str
    transcript: str
    status: str = "queued_for_text_loop"
    created_at: str = ""

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


class TextLoopSeam:
    def relay(self, task: HandoffTask) -> HandoffTask:  # pragma: no cover
        raise NotImplementedError


class RecordingTextLoopSeam(TextLoopSeam):
    def __init__(self) -> None:
        self._tasks: list[HandoffTask] = []

    def relay(self, task: HandoffTask) -> HandoffTask:
        self._tasks.append(task)
        return task

    @property
    def tasks(self) -> tuple[HandoffTask, ...]:
        return tuple(self._tasks)


class HandoffRelay:
    """Relay a voice turn to the text loop with the same hand_off_task pattern."""

    def __init__(self, *, seam: TextLoopSeam | None = None,
                 clock: Callable[[], float] | None = None) -> None:
        self.seam = seam or RecordingTextLoopSeam()
        self._clock = clock

    def hand_off_task(self, session_id: str, transcript: str) -> HandoffTask:
        if not session_id:
            raise VoiceError("hand_off_task needs a session id")
        task = HandoffTask(
            id=new_id("handoff", session_id, transcript),
            session_id=str(session_id), transcript=str(transcript),
            created_at=timestamp(self._clock))
        return self.seam.relay(task)


@dataclass(frozen=True)
class TtsPreview:
    """A preview descriptor only: it never fabricates audio bytes."""

    id: str
    text: str
    voice: str
    chars: int
    mime_type: str = "audio/pcm"

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def tts_preview(text: str, voice: str = "default") -> TtsPreview:
    body = str(text)
    return TtsPreview(id=new_id("tts", body, voice), text=body,
                      voice=str(voice), chars=len(body))


@dataclass(frozen=True)
class SttDictation:
    """Metadata for a real audio buffer queued to a transcription seam."""

    id: str
    byte_size: int
    sha256: str
    mime_type: str
    status: str = "queued_for_transcription"
    transcript: str = ""

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


class TranscriptionSeam:
    def transcribe(self, dictation: SttDictation) -> SttDictation:  # pragma: no cover
        raise NotImplementedError


class RecordingTranscriptionSeam(TranscriptionSeam):
    def __init__(self) -> None:
        self._dictations: list[SttDictation] = []

    def transcribe(self, dictation: SttDictation) -> SttDictation:
        self._dictations.append(dictation)
        return dictation

    @property
    def dictations(self) -> tuple[SttDictation, ...]:
        return tuple(self._dictations)


def stt_dictation_proxy(audio_bytes: bytes, *, mime_type: str = "audio/webm",
                        seam: TranscriptionSeam | None = None) -> SttDictation:
    """Hash real audio bytes; never invent a transcript or audio content."""
    if not isinstance(audio_bytes, (bytes, bytearray)) or not audio_bytes:
        raise VoiceError("dictation proxy needs non-empty audio bytes")
    data = bytes(audio_bytes)
    digest = hashlib.sha256(data).hexdigest()
    descriptor = SttDictation(
        id=new_id("stt", mime_type, digest), byte_size=len(data),
        sha256=digest, mime_type=str(mime_type))
    (seam or RecordingTranscriptionSeam()).transcribe(descriptor)
    return descriptor


# ---------------------------------------------------------------------------
# Y2.23 -- E2E script with a prepared-audio fixture
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AudioFixture:
    """Real, deterministic PCM/WAV bytes built in memory (no fake success)."""

    name: str
    mime_type: str
    data: bytes
    sha256: str
    sample_rate: int
    duration_ms: int
    channels: int = 1

    def to_dict(self) -> dict:
        return {"name": self.name, "mime_type": self.mime_type,
                "byte_size": len(self.data), "sha256": self.sha256,
                "sample_rate": self.sample_rate,
                "duration_ms": self.duration_ms, "channels": self.channels}


def prepare_audio_fixture(name: str = "voice-prepared.wav", *,
                          sample_rate: int = 16000,
                          duration_ms: int = 250,
                          frequency_hz: int = 440) -> AudioFixture:
    """Generate a real 16-bit PCM WAV tone; deterministic, stdlib only."""
    if sample_rate <= 0 or duration_ms <= 0 or frequency_hz <= 0:
        raise AudioFixtureError("sample_rate, duration_ms and frequency must be positive")
    frames_count = sample_rate * duration_ms // 1000
    if frames_count < 1:
        raise AudioFixtureError("duration is too short to produce a sample")
    pcm = bytearray()
    for index in range(frames_count):
        sample = int(12000 * math.sin(2 * math.pi * frequency_hz
                                       * index / sample_rate))
        pcm.extend(struct.pack("<h", sample))
    data_size = len(pcm)
    header = (b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
              + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate,
                                      sample_rate * 2, 2, 16)
              + b"data" + struct.pack("<I", data_size))
    audio = bytes(header) + bytes(pcm)
    return AudioFixture(name=str(name), mime_type="audio/wav", data=audio,
                        sha256=hashlib.sha256(audio).hexdigest(),
                        sample_rate=sample_rate, duration_ms=duration_ms)


def voice_harness_fixture() -> AudioFixture:
    """The separate voice harness needs a prepared audio file (Y2.23)."""
    return prepare_audio_fixture("voice-harness.wav")


E2E_SURFACES: tuple[str, ...] = (
    "chat", "computer_tools", "viewer", "search", "connections", "voice",
    "groups", "settings",
)

E2E_FULL_SCENARIO: tuple[str, ...] = (
    "chat.send_message", "computer_tools.screenshot", "viewer.open",
    "search.query", "connections.list", "voice.dictation",
    "groups.post", "settings.read",
)


@dataclass(frozen=True)
class E2EScenario:
    name: str
    steps: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise AudioFixtureError("an E2E scenario needs at least one step")
        object.__setattr__(self, "steps", tuple(self.steps))


SCENARIO_FULL = E2EScenario("full", E2E_FULL_SCENARIO)


@dataclass(frozen=True)
class StepResult:
    step: str
    status: str            # passed | recorded | failed
    detail: str = ""
    harness: str = "unknown"


class E2EHarness:
    def execute(self, step: str, *, fixture: AudioFixture | None = None
                ) -> StepResult:  # pragma: no cover
        raise NotImplementedError


class RecordingE2EHarness(E2EHarness):
    """Records steps honestly: 'recorded' is not the same as 'passed'."""

    def __init__(self) -> None:
        self._executed: list[str] = []

    def execute(self, step: str, *, fixture: AudioFixture | None = None
                ) -> StepResult:
        self._executed.append(step)
        return StepResult(step, "recorded",
                          "recorded, not executed against a live app",
                          "recording")

    @property
    def executed(self) -> tuple[str, ...]:
        return tuple(self._executed)


@dataclass(frozen=True)
class E2EReport:
    scenario: str
    results: tuple[StepResult, ...]
    fixture: str = ""

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "passed")

    @property
    def recorded(self) -> int:
        return sum(1 for r in self.results if r.status == "recorded")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    def to_dict(self) -> dict:
        return {"scenario": self.scenario, "fixture": self.fixture,
                "results": [{"step": r.step, "status": r.status,
                             "detail": r.detail, "harness": r.harness}
                            for r in self.results],
                "passed": self.passed, "recorded": self.recorded,
                "failed": self.failed}


def run_e2e_scenario(scenario: E2EScenario, harness: E2EHarness, *,
                     fixture: AudioFixture | None = None) -> E2EReport:
    """Run every step; voice steps require a prepared-audio fixture."""
    if not isinstance(scenario, E2EScenario) or not isinstance(harness, E2EHarness):
        raise AudioFixtureError("run_e2e_scenario needs a scenario and a harness")
    results: list[StepResult] = []
    for step in scenario.steps:
        if step.startswith("voice.") and fixture is None:
            raise AudioFixtureError(
                f"step {step!r} requires a prepared-audio fixture")
        results.append(harness.execute(step, fixture=fixture))
    return E2EReport(scenario.name, tuple(results),
                     fixture.name if fixture else "")


# ---------------------------------------------------------------------------
# Y2.24 -- per-user SSE stream with typed event kinds
# ---------------------------------------------------------------------------


class SSEEventKind(str, Enum):
    ROW_UPDATE = "row_update"
    LIVE_STATE = "live_state"
    ROSTER_CHANGE = "roster_change"
    COMPUTER_STATE = "computer_state"


@dataclass(frozen=True)
class SSEEvent:
    id: int
    kind: SSEEventKind
    user_id: str
    data: dict
    created_at: str

    def encode(self) -> str:
        payload = json.dumps(self.data, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False)
        return (f"id: {self.id}\nevent: {self.kind.value}\n"
                f"data: {payload}\n\n")

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind.value,
                "user_id": self.user_id, "data": dict(self.data),
                "created_at": self.created_at}


DEFAULT_SSE_BUFFER = 1000


class SSEStream:
    """One bounded stream per client; events replayable by id on reconnect."""

    def __init__(self, user_id: str, *, buffer_size: int = DEFAULT_SSE_BUFFER,
                 clock: Callable[[], float] | None = None) -> None:
        if not user_id or buffer_size < 1:
            raise StreamError("SSEStream needs a user id and positive buffer")
        self.user_id = str(user_id)
        self.buffer_size = int(buffer_size)
        self._clock = clock
        self._events: OrderedDict[int, SSEEvent] = OrderedDict()
        self._next_id = 0
        self._oldest_id = 0
        self._lock = threading.RLock()

    def publish(self, kind: SSEEventKind | str, data: Mapping[str, Any]) -> SSEEvent:
        try:
            typed = SSEEventKind(kind)
        except ValueError:
            raise StreamError(f"unknown SSE event kind: {kind!r}") from None
        if not isinstance(data, Mapping):
            raise StreamError("SSE event data must be a mapping")
        with self._lock:
            self._next_id += 1
            event = SSEEvent(self._next_id, typed, self.user_id,
                             dict(data), timestamp(self._clock))
            self._events[event.id] = event
            while len(self._events) > self.buffer_size:
                self._events.popitem(last=False)
                self._oldest_id += 1
            return event

    def drain(self, *, since_id: int = 0) -> tuple[SSEEvent, ...]:
        with self._lock:
            return tuple(e for e in self._events.values() if e.id > since_id)

    def snapshot(self) -> dict:
        with self._lock:
            return {"user_id": self.user_id, "oldest_id": self._oldest_id,
                    "next_id": self._next_id,
                    "events": [e.to_dict() for e in self._events.values()]}


class SSEStreamRegistry:
    """Guarantee exactly one stream per user/client."""

    def __init__(self, *, buffer_size: int = DEFAULT_SSE_BUFFER,
                 clock: Callable[[], float] | None = None) -> None:
        self.buffer_size = buffer_size
        self._clock = clock
        self._streams: dict[str, SSEStream] = {}
        self._lock = threading.RLock()

    def for_user(self, user_id: str) -> SSEStream:
        with self._lock:
            key = str(user_id)
            if key not in self._streams:
                self._streams[key] = SSEStream(
                    key, buffer_size=self.buffer_size, clock=self._clock)
            return self._streams[key]

    def publish(self, user_id: str, kind: SSEEventKind | str,
                data: Mapping[str, Any]) -> SSEEvent:
        return self.for_user(user_id).publish(kind, data)

    def users(self) -> tuple[str, ...]:
        return tuple(sorted(self._streams))

    def close(self, user_id: str) -> None:
        with self._lock:
            self._streams.pop(str(user_id), None)


# ---------------------------------------------------------------------------
# Y2.25 -- routines: cron, connector event triggers, proactive check-ins
# ---------------------------------------------------------------------------


def _parse_cron_field(raw: str, low: int, high: int) -> frozenset[int]:
    values: set[int] = set()
    for item in str(raw).split(","):
        item = item.strip()
        if not item:
            raise RoutineError("empty cron field")
        step = 1
        if "/" in item:
            item, step_raw = item.split("/", 1)
            try:
                step = int(step_raw)
            except ValueError:
                raise RoutineError(f"invalid cron step: {step_raw!r}") from None
            if step < 1:
                raise RoutineError("cron step must be >= 1")
        if item == "*":
            start, end = low, high
        elif "-" in item:
            start_raw, end_raw = item.split("-", 1)
            try:
                start, end = int(start_raw), int(end_raw)
            except ValueError:
                raise RoutineError(f"invalid cron range: {item!r}") from None
        elif item.isdigit():
            start = end = int(item)
        else:
            raise RoutineError(f"invalid cron token: {item!r}")
        if start < low or end > high or start > end:
            raise RoutineError(f"cron field out of range: {item!r}")
        values.update(range(start, end + 1, step))
    if not values:
        raise RoutineError("cron field produced no values")
    return frozenset(values)


@dataclass(frozen=True)
class CronSchedule:
    expression: str
    minute: frozenset[int]
    hour: frozenset[int]
    day_of_month: frozenset[int]
    month: frozenset[int]
    day_of_week: frozenset[int]   # cron convention: Sunday == 0

    def matches(self, moment: datetime) -> bool:
        # datetime.weekday(): Monday == 0 -> cron: Sunday == 0
        cron_dow = (moment.weekday() + 1) % 7
        return (moment.minute in self.minute
                and moment.hour in self.hour
                and moment.day in self.day_of_month
                and moment.month in self.month
                and cron_dow in self.day_of_week)

    def to_dict(self) -> dict:
        return {"expression": self.expression}


def parse_cron(expression: str) -> CronSchedule:
    parts = str(expression).split()
    if len(parts) != 5:
        raise RoutineError("a cron expression needs exactly 5 fields")
    minute, hour, dom, month, dow = parts
    return CronSchedule(
        expression=" ".join(parts),
        minute=_parse_cron_field(minute, 0, 59),
        hour=_parse_cron_field(hour, 0, 23),
        day_of_month=_parse_cron_field(dom, 1, 31),
        month=_parse_cron_field(month, 1, 12),
        day_of_week=_parse_cron_field(dow, 0, 6))


class RoutineKind(str, Enum):
    CRON = "cron"
    EVENT = "event"
    CHECKIN = "checkin"


@dataclass(frozen=True)
class Routine:
    id: str
    name: str
    kind: RoutineKind
    agent_id: str
    schedule: str = ""
    trigger: str = ""
    connector: str = ""
    interval_seconds: int = 3600
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", RoutineKind(self.kind))
        if not self.name or not self.agent_id:
            raise RoutineError("a routine needs a name and an agent_id")
        if self.kind is RoutineKind.CRON:
            parse_cron(self.schedule)
        if self.kind is RoutineKind.EVENT and not (self.trigger and self.connector):
            raise RoutineError("an event routine needs a trigger and a connector")
        if self.interval_seconds < 0:
            raise RoutineError("interval_seconds must be >= 0")

    def to_dict(self) -> dict:
        return {f.name: (self.kind.value if f.name == "kind"
                         else getattr(self, f.name)) for f in fields(self)}


def make_routine(name: str, kind: RoutineKind | str, agent_id: str, **kwargs: Any
                 ) -> Routine:
    typed = RoutineKind(kind)
    return Routine(id=new_id("routine", name, typed.value, agent_id),
                   name=str(name), kind=typed, agent_id=str(agent_id), **kwargs)


@dataclass(frozen=True)
class ConnectorEvent:
    name: str
    connector: str
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RoutineTrigger:
    routine_id: str
    kind: RoutineKind
    due: bool
    reason: str

    def to_dict(self) -> dict:
        return {"routine_id": self.routine_id, "kind": self.kind.value,
                "due": self.due, "reason": self.reason}


@dataclass(frozen=True)
class FiredRoutine:
    id: str
    routine_id: str
    kind: RoutineKind
    fired_at: str

    def to_dict(self) -> dict:
        return {"id": self.id, "routine_id": self.routine_id,
                "kind": self.kind.value, "fired_at": self.fired_at}


class RoutineEngine:
    """Evaluate cron/event/check-in routines from user-configured sources."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock
        self._routines: dict[str, Routine] = {}
        self._free_connectors: set[str] = set()
        self._last_checkin: dict[str, float] = {}

    def _now(self, now: float | None) -> float:
        return float(now) if now is not None else float(
            self._clock() if self._clock is not None else time.time())

    def configure_free_connectors(self, connectors: Iterable[str]) -> None:
        """Only user-configured free connectors may fire event routines."""
        self._free_connectors = {str(c) for c in connectors}

    def register(self, routine: Routine) -> Routine:
        if not isinstance(routine, Routine):
            raise RoutineError("register needs a Routine")
        self._routines[routine.id] = routine
        if routine.kind is RoutineKind.CHECKIN:
            self._last_checkin.setdefault(routine.id, self._now(None))
        return routine

    def routines(self) -> tuple[Routine, ...]:
        return tuple(self._routines.values())

    def evaluate(self, *, now: float | None = None,
                 event: ConnectorEvent | None = None
                 ) -> tuple[RoutineTrigger, ...]:
        current = self._now(now)
        moment = datetime.fromtimestamp(current)
        triggers: list[RoutineTrigger] = []
        for routine in self._routines.values():
            if not routine.enabled:
                triggers.append(RoutineTrigger(routine.id, routine.kind, False,
                                               "disabled"))
                continue
            if routine.kind is RoutineKind.CRON:
                due = parse_cron(routine.schedule).matches(moment)
                reason = "cron match" if due else "cron does not match"
            elif routine.kind is RoutineKind.EVENT:
                if event is None:
                    due, reason = False, "no event"
                elif event.connector not in self._free_connectors:
                    due, reason = False, "connector is not user-configured/free"
                else:
                    due = event.name == routine.trigger
                    reason = "event trigger match" if due else "event name differs"
            else:
                last = self._last_checkin.get(routine.id, current)
                due = (current - last) >= routine.interval_seconds
                reason = "check-in due" if due else "check-in not due"
            triggers.append(RoutineTrigger(routine.id, routine.kind, due, reason))
        return tuple(triggers)

    def fire(self, trigger: RoutineTrigger, *, now: float | None = None
             ) -> FiredRoutine:
        if not isinstance(trigger, RoutineTrigger):
            raise RoutineError("fire needs a RoutineTrigger")
        if not trigger.due:
            raise RoutineError(f"routine is not due: {trigger.reason}")
        routine = self._routines[trigger.routine_id]
        current = self._now(now)
        if routine.kind is RoutineKind.CHECKIN:
            self._last_checkin[routine.id] = current
        return FiredRoutine(
            id=new_id("fired", routine.id, current),
            routine_id=routine.id, kind=routine.kind,
            fired_at=timestamp(lambda: current))
