"""Real, stdlib-only backend behaviour for the remaining D3.* capability rows.

The ten ``P0`` rows of the D3 family already live in :mod:`keel.capability_seams`
as a descriptor/policy layer.  This module covers the other thirteen rows (the
``not_started`` ``P1``/``P2`` features) with *executable in-process behaviour*:
registries, state machines, validation, hashing and wire codecs.  Everything is
deterministic for a given input and uses only the Python standard library.

Scope (one section per feature ID)::

    D3.3   subagent providers behind one activation interface
    D3.4   agent teams: per-root-session board, tasks, messaging, inbox
    D3.5   agent presets composing capability sets with ``isolate`` realms
    D3.10  filesystem policy through ``fs/*`` events on top of providers
    D3.12  named per-turn deliverables and result cards
    D3.15  approval-gated extension proposals (never auto-installed)
    D3.16  local human feedback records and summaries
    D3.17  anonymous install identity, never transmitted
    D3.19  replayable plan log and scheduled follow-ups
    D3.20  ``experimental/`` quarantine and product-package policy
    D3.21  generated provider metadata with a read-only staleness check
    D3.22  inspector build seam (backend only: pin/offline checks, no UI)
    D3.23  Live Share wire codecs (backend only: no browser carrier/relay)

Honest boundaries: this layer performs **no OS file I/O, no subprocess launch,
no socket/network call and no database access**.  It does not render any UI:
the deliverable result cards, inspector dock and live-share viewer are backend
descriptors that a separate frontend would consume.  ``runtime_claimed`` in
:func:`all_backend_descriptors` therefore means the in-process logic really
executes; it never claims an external side effect that did not happen.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

# The thirteen D3 rows that were `not_started` at the baseline commit.  Derived
# from PLAN-INDEX.json priority (P1/P2) in the tests so coverage cannot drift.
FEATURE_IDS: tuple[str, ...] = (
    "D3.3", "D3.4", "D3.5", "D3.10", "D3.12", "D3.15", "D3.16",
    "D3.17", "D3.19", "D3.20", "D3.21", "D3.22", "D3.23",
)


# ---------------------------------------------------------------------------
# errors and small normalisers
# ---------------------------------------------------------------------------
class D3BackendError(ValueError):
    """Base class for every invariant violation in this layer."""


class SubagentError(D3BackendError):
    """Raised when a subagent provider breaks the one-interface contract."""


class TeamError(D3BackendError):
    """Raised for an invalid team state transition or an unenabled board."""


class PresetError(D3BackendError):
    """Raised for an invalid agent preset or service row."""


class FsPolicyError(D3BackendError):
    """Raised for an invalid ``fs/*`` listener registration."""


class DeliverableError(D3BackendError):
    """Raised for an invalid deliverable or result-card request."""


class ExtensionError(D3BackendError):
    """Raised when an extension is applied without approval."""


class FeedbackError(D3BackendError):
    """Raised for an invalid feedback record."""


class IdentityError(D3BackendError):
    """Raised when someone tries to transmit the anonymous install id."""


class PlanError(D3BackendError):
    """Raised for an invalid plan event or replay."""


class ScheduleError(D3BackendError):
    """Raised for an invalid scheduled follow-up."""


class QuarantineError(D3BackendError):
    """Raised when a package escapes quarantine or lacks a classification."""


class MetadataError(D3BackendError):
    """Raised when generated provider metadata is stale."""


class InspectorError(D3BackendError):
    """Raised for an unpinned or network-dependent inspector build spec."""


class WireError(D3BackendError):
    """Raised for a corrupt or unsupported Live Share wire frame."""


def _enum(enum_cls: type[Enum], value: Any) -> Enum:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError) as exc:
        raise D3BackendError(
            f"expected a {enum_cls.__name__} value, got {value!r}") from exc


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _nonempty(value: Any, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise D3BackendError(f"{label} must not be empty")
    return text


# ===========================================================================
# D3.3 — subagent providers behind one interface
# ===========================================================================
SUBAGENT_INTERFACE = "keel.subagents.SubagentProvider"


class SubagentKind(str, Enum):
    CHILD = "child"              # a fresh in-process child agent
    DELEGATED = "delegated"      # a delegated turn in another product
    EXTERNAL = "external"        # an external specialist adapter (V8)


@dataclass(frozen=True)
class SubagentProvider:
    """One implementation of the single subagent activation interface."""

    name: str
    kind: SubagentKind
    interface: str = SUBAGENT_INTERFACE
    capabilities: tuple[str, ...] = ()
    remote: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty(self.name, "provider name"))
        object.__setattr__(self, "kind", _enum(SubagentKind, self.kind))
        object.__setattr__(self, "interface", str(self.interface))
        object.__setattr__(self, "capabilities", _tuple(self.capabilities))
        object.__setattr__(self, "remote", bool(self.remote))
        if self.interface != SUBAGENT_INTERFACE:
            raise SubagentError(
                f"provider {self.name!r} must implement {SUBAGENT_INTERFACE}, "
                f"got {self.interface!r}")
        if self.remote != (self.kind in (SubagentKind.DELEGATED, SubagentKind.EXTERNAL)):
            raise SubagentError(
                f"remote flag for {self.kind.value!r} provider is inconsistent")

    def describe(self) -> dict:
        return {
            "name": self.name, "kind": self.kind.value,
            "interface": self.interface, "capabilities": list(self.capabilities),
            "remote": self.remote,
        }


@dataclass(frozen=True)
class ActivationDescriptor:
    """What one activation of a subagent provider would do (nothing spawned)."""

    provider: str
    kind: SubagentKind
    interface: str
    task: str
    fresh_child: bool
    delegates_turn: bool
    spawn: bool = False
    io_performed: bool = False

    def describe(self) -> dict:
        return {
            "provider": self.provider, "kind": self.kind.value,
            "interface": self.interface, "task": self.task,
            "fresh_child": self.fresh_child, "delegates_turn": self.delegates_turn,
            "spawn": self.spawn, "io_performed": self.io_performed,
        }


class SubagentRegistry:
    """Fresh child -> delegated turn -> external specialist, one interface."""

    def __init__(self) -> None:
        self._providers: dict[str, SubagentProvider] = {}

    def register(self, provider: SubagentProvider) -> SubagentProvider:
        if not isinstance(provider, SubagentProvider):
            raise SubagentError("register() requires a SubagentProvider")
        if provider.name in self._providers:
            raise SubagentError(f"duplicate subagent provider {provider.name!r}")
        self._providers[provider.name] = provider
        return provider

    def get(self, name: str) -> SubagentProvider:
        try:
            return self._providers[_nonempty(name, "provider name")]
        except KeyError as exc:
            raise SubagentError(f"unknown subagent provider {name!r}") from exc

    def activate(self, name: str, task: str) -> ActivationDescriptor:
        provider = self.get(name)
        return ActivationDescriptor(
            provider=provider.name, kind=provider.kind,
            interface=provider.interface, task=_nonempty(task, "task"),
            fresh_child=provider.kind is SubagentKind.CHILD,
            delegates_turn=provider.kind in (SubagentKind.DELEGATED,
                                             SubagentKind.EXTERNAL),
        )

    def describe(self) -> dict:
        return {
            "feature_id": "D3.3", "interface": SUBAGENT_INTERFACE,
            "providers": [p.describe() for p in
                          sorted(self._providers.values(), key=lambda p: p.name)],
            "spawn": False,
        }


# ===========================================================================
# D3.4 — agent teams: per-root-session board, task policy and inbox
# ===========================================================================
class TaskState(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class MessageKind(str, Enum):
    NOTE = "note"
    TASK = "task"
    RESULT = "result"
    INTERRUPT = "interrupt"


BROADCAST = "@all"


@dataclass(frozen=True)
class TeamMember:
    name: str
    identity: str
    role: str = "member"

    def describe(self) -> dict:
        return {"name": self.name, "identity": self.identity, "role": self.role}


@dataclass(frozen=True)
class TeamTask:
    id: str
    title: str
    state: TaskState
    owner: str | None = None

    def describe(self) -> dict:
        return {
            "id": self.id, "title": self.title, "state": self.state.value,
            "owner": self.owner,
        }


@dataclass(frozen=True)
class TeamMessage:
    seq: int
    sender: str
    recipient: str
    kind: MessageKind
    body: str

    def describe(self) -> dict:
        return {
            "seq": self.seq, "sender": self.sender, "recipient": self.recipient,
            "kind": self.kind.value, "body": self.body,
        }


class TeamBoard:
    """The shared board belonging to exactly one root session."""

    def __init__(self, root_session_id: str) -> None:
        self._root = _nonempty(root_session_id, "root session id")
        self._members: dict[str, TeamMember] = {}
        self._tasks: dict[str, TeamTask] = {}
        self._messages: list[TeamMessage] = []
        self._interrupted: set[str] = set()

    @property
    def root_session_id(self) -> str:
        return self._root

    def _member(self, name: str) -> TeamMember:
        try:
            return self._members[_nonempty(name, "member name")]
        except KeyError as exc:
            raise TeamError(f"{name!r} is not a member of this team") from exc

    def join(self, name: str, identity: str, *, role: str = "member") -> TeamMember:
        """A subagent controls its own identity; the board only records it."""
        name = _nonempty(name, "member name")
        identity = _nonempty(identity, "identity")
        if name in self._members:
            raise TeamError(f"duplicate team member {name!r}")
        member = TeamMember(name, identity, _nonempty(role, "role"))
        self._members[name] = member
        return member

    def discover(self, name: str) -> tuple[TeamMember, ...]:
        self._member(name)
        return tuple(sorted((m for n, m in self._members.items() if n != name),
                            key=lambda m: m.name))

    def add_task(self, task_id: str, title: str, *,
                 owner: str | None = None) -> TeamTask:
        task_id = _nonempty(task_id, "task id")
        if task_id in self._tasks:
            raise TeamError(f"duplicate task {task_id!r}")
        if owner is not None:
            self._member(owner)
        task = TeamTask(task_id, _nonempty(title, "task title"),
                        TaskState.TODO, owner)
        self._tasks[task_id] = task
        return task

    def claim(self, task_id: str, member: str) -> TeamTask:
        self._member(member)
        task = self._task(task_id)
        if task.state is not TaskState.TODO:
            raise TeamError(f"task {task_id!r} is already {task.state.value}")
        if task.owner is not None and task.owner != member:
            raise TeamError(f"task {task_id!r} is reserved for {task.owner!r}")
        updated = replace(task, state=TaskState.IN_PROGRESS, owner=member)
        self._tasks[task_id] = updated
        return updated

    def complete(self, task_id: str, member: str) -> TeamTask:
        self._member(member)
        task = self._task(task_id)
        if task.state is not TaskState.IN_PROGRESS or task.owner != member:
            raise TeamError(f"only the owner can complete task {task_id!r}")
        updated = replace(task, state=TaskState.DONE)
        self._tasks[task_id] = updated
        return updated

    def _task(self, task_id: str) -> TeamTask:
        try:
            return self._tasks[_nonempty(task_id, "task id")]
        except KeyError as exc:
            raise TeamError(f"unknown task {task_id!r}") from exc

    def tasks(self) -> tuple[TeamTask, ...]:
        return tuple(sorted(self._tasks.values(), key=lambda t: t.id))

    def send(self, sender: str, recipient: str, body: str,
             kind: MessageKind | str = MessageKind.NOTE) -> TeamMessage:
        self._member(sender)
        if recipient != BROADCAST:
            self._member(recipient)
        message = TeamMessage(
            seq=len(self._messages) + 1, sender=sender, recipient=recipient,
            kind=_enum(MessageKind, kind), body=_nonempty(body, "message body"))
        self._messages.append(message)
        return message

    def inbox(self, member: str) -> tuple[TeamMessage, ...]:
        self._member(member)
        return tuple(m for m in self._messages
                     if m.recipient in (member, BROADCAST) and m.sender != member)

    def wait_descriptor(self, member: str, *, timeout_s: float = 30.0) -> dict:
        """Describe an inbox wait; this never blocks a thread or opens a socket."""
        self._member(member)
        timeout = float(timeout_s)
        if timeout <= 0:
            raise TeamError("timeout_s must be positive")
        return {
            "feature_id": "D3.4", "member": member, "timeout_s": timeout,
            "pending": len(self.inbox(member)), "blocking": False,
            "io_performed": False,
        }

    def interrupt(self, sender: str, member: str) -> TeamMessage:
        self._member(sender)
        self._member(member)
        self._interrupted.add(member)
        return self.send(sender, member, f"interrupt from {sender}",
                         MessageKind.INTERRUPT)

    def is_interrupted(self, member: str) -> bool:
        self._member(member)
        return member in self._interrupted

    def clear_interrupt(self, member: str) -> None:
        self._member(member)
        self._interrupted.discard(member)

    def describe(self) -> dict:
        return {
            "feature_id": "D3.4", "root_session_id": self._root,
            "members": [m.describe() for m in
                        sorted(self._members.values(), key=lambda m: m.name)],
            "tasks": [t.describe() for t in self.tasks()],
            "message_count": len(self._messages),
            "interrupted": sorted(self._interrupted),
            "io_performed": False,
        }


class TeamService:
    """Agent teams are enabled per root session, never globally by default."""

    def __init__(self) -> None:
        self._board: TeamBoard | None = None

    def enable(self, root_session_id: str) -> TeamBoard:
        root = _nonempty(root_session_id, "root session id")
        if self._board is not None and self._board.root_session_id != root:
            raise TeamError(
                f"teams already enabled for root session {self._board.root_session_id!r}")
        if self._board is None:
            self._board = TeamBoard(root)
        return self._board

    @property
    def board(self) -> TeamBoard:
        if self._board is None:
            raise TeamError("agent teams are not enabled for a root session")
        return self._board

    def describe(self) -> dict:
        return {
            "feature_id": "D3.4", "enabled": self._board is not None,
            "root_session_id": self._board.root_session_id if self._board else None,
            "policy": "per_root_session",
        }


# ===========================================================================
# D3.5 — agent presets compose capability sets with isolate realms
# ===========================================================================
class Realm(str, Enum):
    SHARED = "shared"
    ISOLATE = "isolate"


@dataclass(frozen=True)
class ServiceRow:
    """One service in a preset; ``isolate`` rows get their own instance."""

    name: str
    realm: Realm = Realm.SHARED

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty(self.name, "service name"))
        object.__setattr__(self, "realm", _enum(Realm, self.realm))

    def describe(self) -> dict:
        return {"name": self.name, "realm": self.realm.value}


@dataclass(frozen=True)
class AgentPreset:
    name: str
    rows: tuple[ServiceRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty(self.name, "preset name"))
        rows = tuple(self.rows)
        if not rows:
            raise PresetError(f"preset {self.name!r} needs at least one service row")
        names = [row.name for row in rows]
        if len(set(names)) != len(names):
            raise PresetError(f"preset {self.name!r} has duplicate service rows")
        object.__setattr__(self, "rows", rows)

    def describe(self) -> dict:
        return {"name": self.name, "rows": [r.describe() for r in self.rows]}


@dataclass(frozen=True)
class ResolvedPreset:
    preset: str
    session_id: str
    capabilities: tuple[str, ...]
    instances: tuple[tuple[str, str, str], ...]  # (service, instance_id, realm)
    scope: str = "one_session"
    io_performed: bool = False

    def describe(self) -> dict:
        return {
            "preset": self.preset, "session_id": self.session_id,
            "capabilities": list(self.capabilities),
            "instances": [list(row) for row in self.instances],
            "scope": self.scope, "io_performed": self.io_performed,
        }


class PresetService:
    """Resolve a preset into a per-session capability set and instances."""

    def __init__(self) -> None:
        self._presets: dict[str, AgentPreset] = {}

    def register(self, preset: AgentPreset) -> AgentPreset:
        if not isinstance(preset, AgentPreset):
            raise PresetError("register() requires an AgentPreset")
        if preset.name in self._presets:
            raise PresetError(f"duplicate agent preset {preset.name!r}")
        self._presets[preset.name] = preset
        return preset

    def resolve(self, name: str, session_id: str) -> ResolvedPreset:
        preset = self._presets.get(_nonempty(name, "preset name"))
        if preset is None:
            raise PresetError(f"unknown agent preset {name!r}")
        session = _nonempty(session_id, "session id")
        instances: list[tuple[str, str, str]] = []
        for row in preset.rows:
            if row.realm is Realm.ISOLATE:
                instance_id = f"{preset.name}/{session}/{row.name}"
            else:
                instance_id = f"shared/{row.name}"
            instances.append((row.name, instance_id, row.realm.value))
        return ResolvedPreset(
            preset=preset.name, session_id=session,
            capabilities=tuple(sorted(r.name for r in preset.rows)),
            instances=tuple(sorted(instances)),
        )

    def describe(self) -> dict:
        return {
            "feature_id": "D3.5",
            "presets": [p.describe() for p in
                        sorted(self._presets.values(), key=lambda p: p.name)],
        }


# ===========================================================================
# D3.10 — filesystem policy through fs/* events on top of providers
# ===========================================================================
class FsEvent(str, Enum):
    BEFORE_READ = "fs/before_read"
    BEFORE_WRITE = "fs/before_write"
    AFTER_WRITE = "fs/after_write"
    BEFORE_DELETE = "fs/before_delete"
    AFTER_DELETE = "fs/after_delete"


@dataclass(frozen=True)
class FsRequest:
    event: FsEvent
    path: str
    provider: str = "filesystem"
    operation: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "event", _enum(FsEvent, self.event))
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "provider", str(self.provider))

    def describe(self) -> dict:
        return {
            "event": self.event.value, "path": self.path,
            "provider": self.provider, "operation": self.operation,
        }


@dataclass(frozen=True)
class FsVerdict:
    event: FsEvent
    path: str
    allowed: bool
    veto_source: str | None
    reasons: tuple[str, ...]
    chain: tuple[str, ...]
    io_performed: bool = False

    def describe(self) -> dict:
        return {
            "feature_id": "D3.10", "event": self.event.value, "path": self.path,
            "allowed": self.allowed, "veto_source": self.veto_source,
            "reasons": list(self.reasons), "chain": list(self.chain),
            "io_performed": self.io_performed,
        }


@dataclass(frozen=True)
class FsListener:
    name: str
    tier: int
    events: tuple[FsEvent, ...]
    decision: Callable[[FsRequest], str | None]

    def describe(self) -> dict:
        return {
            "name": self.name, "tier": self.tier,
            "events": [e.value for e in self.events],
        }


class FsEventBus:
    """Waterfall ``fs/*`` listeners: tier 2 (policy/plugins) listens first."""

    def __init__(self) -> None:
        self._listeners: dict[str, FsListener] = {}

    def register(self, name: str, tier: int, events: Iterable[FsEvent | str],
                 decision: Callable[[FsRequest], str | None]) -> FsListener:
        name = _nonempty(name, "listener name")
        if name in self._listeners:
            raise FsPolicyError(f"duplicate fs listener {name!r}")
        if int(tier) not in (1, 2):
            raise FsPolicyError("tier must be 1 (default) or 2 (policy/plugins)")
        if not callable(decision):
            raise FsPolicyError("a listener decision must be callable")
        parsed = tuple(_enum(FsEvent, event) for event in events)
        if not parsed:
            raise FsPolicyError("a listener must subscribe to at least one event")
        listener = FsListener(name, int(tier), parsed, decision)
        self._listeners[name] = listener
        return listener

    def _ordered(self, event: FsEvent) -> tuple[FsListener, ...]:
        return tuple(sorted(
            (listener for listener in self._listeners.values()
             if event in listener.events),
            key=lambda listener: (-listener.tier, listener.name)))

    def dispatch(self, request: FsRequest) -> FsVerdict:
        if not isinstance(request, FsRequest):
            raise FsPolicyError("dispatch() requires an FsRequest")
        chain: list[str] = []
        reasons: list[str] = []
        for listener in self._ordered(request.event):
            chain.append(listener.name)
            try:
                answer = listener.decision(request)
            except Exception as exc:
                # A plugin must not break the typed-error contract of dispatch.
                raise FsPolicyError(
                    f"fs listener {listener.name!r} failed: {exc}") from exc
            if answer is None or answer == "allow":
                continue
            if answer != "veto":
                raise FsPolicyError(
                    f"listener {listener.name!r} returned invalid decision {answer!r}")
            reasons.append(listener.name)
            return FsVerdict(request.event, request.path, False,
                             listener.name, tuple(reasons), tuple(chain))
        return FsVerdict(request.event, request.path, True,
                         None, tuple(reasons), tuple(chain))

    def describe(self) -> dict:
        return {
            "feature_id": "D3.10",
            "order": "tier 2 before tier 1, then name",
            "listeners": [l.describe() for l in sorted(
                self._listeners.values(),
                key=lambda l: (-l.tier, l.name))],
            "io_performed": False,
        }


# ===========================================================================
# D3.12 — per-turn deliverables and result cards
# ===========================================================================
class DeliverableKind(str, Enum):
    FILE = "file"
    SUMMARY = "summary"
    REPORT = "report"


@dataclass(frozen=True)
class Deliverable:
    name: str
    kind: DeliverableKind
    path: str = ""
    detail: str = ""
    sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty(self.name, "deliverable name"))
        object.__setattr__(self, "kind", _enum(DeliverableKind, self.kind))

    def describe(self) -> dict:
        return {
            "name": self.name, "kind": self.kind.value, "path": self.path,
            "detail": self.detail, "sha256": self.sha256,
        }


class DeliverableService:
    """Attach named deliverables to a turn; render result-card descriptors."""

    def __init__(self) -> None:
        self._by_turn: dict[str, dict[str, Deliverable]] = {}

    def attach(self, turn_id: str, name: str, kind: DeliverableKind | str,
               *, path: str = "", detail: str = "",
               content: str | bytes | None = None) -> Deliverable:
        turn = _nonempty(turn_id, "turn id")
        item = Deliverable(name, _enum(DeliverableKind, kind), str(path),
                           str(detail))
        if item.kind is DeliverableKind.FILE and not item.path and content is None:
            raise DeliverableError("a file deliverable needs a path or content")
        if item.kind is not DeliverableKind.FILE and not item.detail and content is None:
            raise DeliverableError("a summary/report needs detail or content")
        digest = ""
        if content is not None:
            raw = content if isinstance(content, bytes) else content.encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()
            if not item.detail:
                object.__setattr__(item, "detail", f"{len(raw)} bytes")
        bucket = self._by_turn.setdefault(turn, {})
        if item.name in bucket:
            raise DeliverableError(
                f"duplicate deliverable {item.name!r} on turn {turn!r}")
        object.__setattr__(item, "sha256", digest)
        bucket[item.name] = item
        return item

    def for_turn(self, turn_id: str) -> tuple[Deliverable, ...]:
        bucket = self._by_turn.get(str(turn_id), {})
        return tuple(sorted(bucket.values(), key=lambda d: d.name))

    def card(self, turn_id: str, name: str) -> dict:
        bucket = self._by_turn.get(str(turn_id), {})
        item = bucket.get(_nonempty(name, "deliverable name"))
        if item is None:
            raise DeliverableError(f"unknown deliverable {name!r} on turn {turn_id!r}")
        return {
            "feature_id": "D3.12", "turn_id": str(turn_id),
            "deliverable": item.describe(),
            "open_action": item.path or None,
            "export_action": f"export:{item.name}",
            "frontend_rendered": False,
        }

    def describe(self) -> dict:
        return {
            "feature_id": "D3.12",
            "turns": sorted(self._by_turn),
            "deliverable_count": sum(len(bucket) for bucket in self._by_turn.values()),
            "io_performed": False,
        }


# ===========================================================================
# D3.15 — extensions: approval-gated proposals, never auto-installed
# ===========================================================================
class ExtensionKind(str, Enum):
    SKILL = "skill"
    COMMAND = "command"
    AGENT = "agent"


class ProposalState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ExtensionProposal:
    id: str
    kind: ExtensionKind
    target: str
    diff_sha256: str
    state: ProposalState = ProposalState.PROPOSED
    approver: str = ""
    reason: str = ""

    def describe(self) -> dict:
        return {
            "id": self.id, "kind": self.kind.value, "target": self.target,
            "diff_sha256": self.diff_sha256, "state": self.state.value,
            "approver": self.approver, "reason": self.reason,
            "auto_installed": False,
        }


class ExtensionService:
    """An agent may propose diffs; only an explicit owner may approve them."""

    def __init__(self) -> None:
        self._proposals: dict[str, ExtensionProposal] = {}

    def propose(self, proposal_id: str, kind: ExtensionKind | str,
                target: str, diff: str) -> ExtensionProposal:
        proposal_id = _nonempty(proposal_id, "proposal id")
        if proposal_id in self._proposals:
            raise ExtensionError(f"duplicate extension proposal {proposal_id!r}")
        proposal = ExtensionProposal(
            proposal_id, _enum(ExtensionKind, kind), _nonempty(target, "target"),
            _digest(str(diff)))
        self._proposals[proposal_id] = proposal
        return proposal

    def _get(self, proposal_id: str) -> ExtensionProposal:
        try:
            return self._proposals[_nonempty(proposal_id, "proposal id")]
        except KeyError as exc:
            raise ExtensionError(f"unknown extension proposal {proposal_id!r}") from exc

    def approve(self, proposal_id: str, approver: str) -> ExtensionProposal:
        proposal = self._get(proposal_id)
        approver = _nonempty(approver, "approver")
        if proposal.state is not ProposalState.PROPOSED:
            raise ExtensionError(f"proposal {proposal_id!r} is already resolved")
        updated = replace(proposal, state=ProposalState.APPROVED, approver=approver)
        self._proposals[proposal.id] = updated
        return updated

    def reject(self, proposal_id: str, approver: str,
               reason: str = "") -> ExtensionProposal:
        proposal = self._get(proposal_id)
        approver = _nonempty(approver, "approver")
        if proposal.state is not ProposalState.PROPOSED:
            raise ExtensionError(f"proposal {proposal_id!r} is already resolved")
        updated = replace(proposal, state=ProposalState.REJECTED,
                          approver=approver, reason=str(reason))
        self._proposals[proposal.id] = updated
        return updated

    def application(self, proposal_id: str) -> dict:
        """Describe an application; writing files is always out of scope."""
        proposal = self._get(proposal_id)
        if proposal.state is not ProposalState.APPROVED:
            raise ExtensionError(
                f"proposal {proposal_id!r} is {proposal.state.value}: "
                "never auto-install an extension")
        return {
            "feature_id": "D3.15", "proposal": proposal.describe(),
            "performed": False, "writes": False,
            "requires_explicit_approval": True,
        }

    def proposals(self) -> tuple[ExtensionProposal, ...]:
        return tuple(sorted(self._proposals.values(), key=lambda p: p.id))

    def describe(self) -> dict:
        return {
            "feature_id": "D3.15",
            "rule": "never auto-installs",
            "proposals": [p.describe() for p in self.proposals()],
            "writes": False,
        }


# ===========================================================================
# D3.16 — human feedback, stored locally and fed to local evals
# ===========================================================================
class Sentiment(str, Enum):
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True)
class Feedback:
    seq: int
    message_id: str
    sentiment: Sentiment
    note: str

    def describe(self) -> dict:
        return {
            "seq": self.seq, "message_id": self.message_id,
            "sentiment": self.sentiment.value, "note": self.note,
        }


class FeedbackService:
    def __init__(self) -> None:
        self._records: list[Feedback] = []

    def record(self, message_id: str, sentiment: Sentiment | str,
               note: str = "") -> Feedback:
        message_id = _nonempty(message_id, "message id")
        text = str(note)
        if len(text) > 2000:
            raise FeedbackError("feedback note cannot exceed 2000 characters")
        item = Feedback(len(self._records) + 1, message_id,
                        _enum(Sentiment, sentiment), text)
        self._records.append(item)
        return item

    def for_message(self, message_id: str) -> tuple[Feedback, ...]:
        return tuple(r for r in self._records if r.message_id == str(message_id))

    def summary(self) -> dict:
        return {
            "feature_id": "D3.16", "total": len(self._records),
            "up": sum(1 for r in self._records if r.sentiment is Sentiment.UP),
            "down": sum(1 for r in self._records if r.sentiment is Sentiment.DOWN),
            "storage": "local", "transmitted": False,
            "eval_feed": "local_eval_only",
        }

    def describe(self) -> dict:
        return {
            "feature_id": "D3.16",
            "records": [r.describe() for r in self._records],
            "io_performed": False,
        }


# ===========================================================================
# D3.17 — anonymous install identity, never transmitted
# ===========================================================================
@dataclass(frozen=True)
class InstallIdentity:
    install_id: str
    source: str
    telemetry: bool = False
    transmitted: bool = False

    def __post_init__(self) -> None:
        if not self.install_id.startswith("local-"):
            raise IdentityError("install id must be in the local- namespace")
        if self.transmitted or self.telemetry:
            raise IdentityError("anonymous identity must never be transmitted")
        if self.source not in ("provided", "generated", "seed"):
            raise IdentityError(f"unknown identity source {self.source!r}")

    def describe(self) -> dict:
        return {
            "feature_id": "D3.17", "install_id": self.install_id,
            "source": self.source, "telemetry": self.telemetry,
            "transmitted": self.transmitted,
            "purpose": "local_keys_only",
        }

    def public_view(self) -> dict:
        """A shareable view that never reveals the anonymous local id."""
        return {
            "feature_id": "D3.17", "has_local_id": True,
            "telemetry": False, "transmitted": False,
        }

    def export_for_transmission(self) -> str:
        raise IdentityError("the anonymous install id is never sent anywhere")


def derive_install_id(seed: str | bytes) -> str:
    """Deterministic local id for tests/config; still never transmitted."""
    raw = seed.encode("utf-8") if isinstance(seed, str) else bytes(seed)
    if not raw:
        raise IdentityError("identity seed must not be empty")
    return "local-" + hashlib.sha256(raw).hexdigest()[:24]


def generate_install_id() -> str:
    """Random local id from the stdlib CSPRNG; no network, no keyring write."""
    return "local-" + secrets.token_hex(16)


def identity_from_seed(seed: str | bytes) -> InstallIdentity:
    return InstallIdentity(derive_install_id(seed), "seed")


def generate_identity() -> InstallIdentity:
    return InstallIdentity(generate_install_id(), "generated")


# ===========================================================================
# D3.19 — replayable plan log and scheduled follow-ups
# ===========================================================================
class PlanEventKind(str, Enum):
    ADD = "plan/add"
    DONE = "plan/done"
    NOTE = "plan/note"


@dataclass(frozen=True)
class PlanEvent:
    seq: int
    kind: PlanEventKind
    step_id: str
    text: str = ""

    def describe(self) -> dict:
        return {
            "seq": self.seq, "kind": self.kind.value,
            "step_id": self.step_id, "text": self.text,
        }


@dataclass(frozen=True)
class PlanStep:
    id: str
    text: str
    done: bool

    def describe(self) -> dict:
        return {"id": self.id, "text": self.text, "done": self.done}


class PlanLog:
    """Append-only log; replaying its events rebuilds the checklist."""

    def __init__(self) -> None:
        self._events: list[PlanEvent] = []

    def append(self, kind: PlanEventKind | str, step_id: str,
               text: str = "") -> PlanEvent:
        event_kind = _enum(PlanEventKind, kind)
        step_id = _nonempty(step_id, "step id")
        known = {event.step_id for event in self._events}
        if event_kind is PlanEventKind.ADD:
            if step_id in known:
                raise PlanError(f"duplicate plan step {step_id!r}")
            if not str(text).strip():
                raise PlanError("a plan/add event needs step text")
        elif event_kind is PlanEventKind.DONE:
            if step_id not in known:
                raise PlanError(f"cannot finish unknown plan step {step_id!r}")
        elif not str(text).strip():
            raise PlanError("a plan/note event needs text")
        event = PlanEvent(len(self._events) + 1, event_kind, step_id, str(text))
        self._events.append(event)
        return event

    def events(self) -> tuple[PlanEvent, ...]:
        return tuple(self._events)

    def checklist(self) -> tuple[PlanStep, ...]:
        steps: dict[str, PlanStep] = {}
        for event in self._events:
            if event.kind is PlanEventKind.ADD:
                steps[event.step_id] = PlanStep(event.step_id, event.text, False)
            elif event.kind is PlanEventKind.DONE and event.step_id in steps:
                old = steps[event.step_id]
                steps[event.step_id] = replace(old, done=True)
        return tuple(sorted(steps.values(), key=lambda s: s.id))

    @classmethod
    def replay(cls, events: Iterable[PlanEvent]) -> PlanLog:
        """Rebuild the exact log from durable events (survives a restart)."""
        log = cls()
        for index, event in enumerate(events, start=1):
            if not isinstance(event, PlanEvent) or event.seq != index:
                raise PlanError("plan replay requires contiguous, typed events")
            if event.kind not in tuple(PlanEventKind):
                raise PlanError(f"unknown plan event kind {event.kind!r}")
            text = event.text
            if event.kind is PlanEventKind.DONE:
                text = ""
            log.append(event.kind, event.step_id, text)
        return log

    def describe(self) -> dict:
        return {
            "feature_id": "D3.19", "group": "plan",
            "events": [e.describe() for e in self._events],
            "checklist": [s.describe() for s in self.checklist()],
            "replayable": True,
        }


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ScheduleError(f"invalid datetime {value!r}") from exc
    raise ScheduleError("now must be a datetime or an ISO 8601 string")


@dataclass(frozen=True)
class ScheduledFollowUp:
    id: str
    prompt: str
    hours: float
    created_at: str
    due_at: str
    fired: bool = False

    def describe(self) -> dict:
        return {
            "id": self.id, "prompt": self.prompt, "hours": self.hours,
            "created_at": self.created_at, "due_at": self.due_at,
            "fired": self.fired,
        }


class ScheduleService:
    """Deterministic follow-up scheduling; no live timer or background thread."""

    def __init__(self) -> None:
        self._items: dict[str, ScheduledFollowUp] = {}

    def schedule(self, item_id: str, prompt: str, *, hours: float,
                 now: datetime | str) -> ScheduledFollowUp:
        item_id = _nonempty(item_id, "follow-up id")
        if item_id in self._items:
            raise ScheduleError(f"duplicate follow-up {item_id!r}")
        hours = float(hours)
        if not math.isfinite(hours) or hours <= 0:
            raise ScheduleError("hours must be a finite positive number")
        start = _as_datetime(now)
        item = ScheduledFollowUp(
            id=item_id, prompt=_nonempty(prompt, "prompt"), hours=hours,
            created_at=start.isoformat(),
            due_at=(start + timedelta(hours=hours)).isoformat())
        self._items[item_id] = item
        return item

    def is_due(self, item_id: str, now: datetime | str) -> bool:
        item = self._get(item_id)
        return not item.fired and _as_datetime(now) >= datetime.fromisoformat(item.due_at)

    def _get(self, item_id: str) -> ScheduledFollowUp:
        try:
            return self._items[_nonempty(item_id, "follow-up id")]
        except KeyError as exc:
            raise ScheduleError(f"unknown follow-up {item_id!r}") from exc

    def pending(self, now: datetime | str) -> tuple[ScheduledFollowUp, ...]:
        return tuple(sorted(
            (item for item in self._items.values()
             if not item.fired and not self.is_due(item.id, now)),
            key=lambda item: (item.due_at, item.id)))

    def fire(self, item_id: str, now: datetime | str) -> ScheduledFollowUp:
        item = self._get(item_id)
        if item.fired:
            raise ScheduleError(f"follow-up {item_id!r} already fired")
        if not self.is_due(item_id, now):
            raise ScheduleError(f"follow-up {item_id!r} is not due yet")
        updated = replace(item, fired=True)
        self._items[item_id] = updated
        return updated

    def describe(self) -> dict:
        return {
            "feature_id": "D3.19", "group": "schedule",
            "follow_ups": [i.describe() for i in
                           sorted(self._items.values(), key=lambda i: i.id)],
            "timer": False, "io_performed": False,
        }


# ===========================================================================
# D3.20 — experimental/ quarantine and product-package policy
# ===========================================================================
@dataclass(frozen=True)
class PackageEntry:
    package: str
    experimental: bool
    product_use: str = ""
    classification: str = ""

    def describe(self) -> dict:
        return {
            "package": self.package, "experimental": self.experimental,
            "product_use": self.product_use,
            "classification": self.classification,
        }


def _norm_path(path: Any) -> tuple[str, ...]:
    return tuple(part for part in str(path).replace("\\", "/").split("/")
                 if part not in ("", "."))


class ProductPackagePolicy:
    """A policy file (as data): experimental packages live in quarantine."""

    QUARANTINE_ROOT = "keel/experimental"
    ENFORCED_FLAGS = ("X6.10",)

    def __init__(self, entries: Iterable[PackageEntry] = ()) -> None:
        self._entries: dict[str, PackageEntry] = {}
        for entry in entries:
            self.add(entry)

    def add(self, entry: PackageEntry) -> PackageEntry:
        if not isinstance(entry, PackageEntry):
            raise QuarantineError("add() requires a PackageEntry")
        package = _nonempty(entry.package, "package")
        if package in self._entries:
            raise QuarantineError(f"duplicate policy entry {package!r}")
        if "/" in package or ".." in package:
            raise QuarantineError(f"invalid package name {package!r}")
        if not entry.experimental and not (entry.product_use or entry.classification):
            raise QuarantineError(
                f"non-experimental package {package!r} needs product use "
                "or an explicit classification")
        self._entries[package] = entry
        return entry

    def classify(self, package: str) -> PackageEntry:
        try:
            return self._entries[_nonempty(package, "package")]
        except KeyError as exc:
            raise QuarantineError(f"package {package!r} has no policy entry") from exc

    def check_layout(self, paths: Iterable[str]) -> dict:
        """Verify each package's location matches its classification."""
        violations: list[str] = []
        for raw in sorted(paths):
            parts = _norm_path(raw)
            try:
                root_index = parts.index("experimental")
            except ValueError:
                root_index = -1
            in_quarantine = root_index >= 0 and parts[:root_index + 1] == (
                "keel", "experimental")
            if in_quarantine:
                package = parts[root_index + 1] if len(parts) > root_index + 1 else ""
                if not package:
                    violations.append(f"{raw}: no package under experimental/")
                else:
                    entry = self._entries.get(package)
                    if entry is None or not entry.experimental:
                        violations.append(f"{raw}: not classified as experimental")
            else:
                # A declared experimental package must stay inside quarantine;
                # match policy package names against path segments.
                for package in self._entries:
                    if package in parts and self._entries[package].experimental:
                        violations.append(
                            f"{raw}: experimental package outside quarantine")
        return {
            "feature_id": "D3.20", "checked": sorted(paths),
            "violations": violations, "clean": not violations,
            "flags": list(self.ENFORCED_FLAGS),
            "writes": False, "io_performed": False,
        }

    def describe(self) -> dict:
        return {
            "feature_id": "D3.20", "namespace": self.QUARANTINE_ROOT,
            "enforced_flags": list(self.ENFORCED_FLAGS),
            "packages": [e.describe() for e in
                         sorted(self._entries.values(), key=lambda e: e.package)],
            "writes": False,
        }


# ===========================================================================
# D3.21 — generated provider metadata with a read-only staleness check
# ===========================================================================
@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    version: str
    input_digest: str
    generated_by: str = "llm-pi-ai-generator"

    def describe(self) -> dict:
        return {
            "provider": self.provider, "version": self.version,
            "input_digest": self.input_digest, "generated_by": self.generated_by,
        }


def canonical_digest(sources: Mapping[str, str]) -> str:
    """Length-prefixed digest of sorted (path, text) pairs (no file access)."""
    hasher = hashlib.sha256()
    for path in sorted(sources):
        raw = str(sources[path]).encode("utf-8")
        hasher.update(path.encode("utf-8") + b"\0")
        hasher.update(len(raw).to_bytes(8, "big"))
        hasher.update(raw)
    return hasher.hexdigest()


def generate_metadata(provider: str, version: str,
                      sources: Mapping[str, str]) -> ProviderMetadata:
    return ProviderMetadata(
        provider=_nonempty(provider, "provider"),
        version=_nonempty(version, "version"),
        input_digest=canonical_digest(sources))


def check_metadata(metadata: Mapping[str, ProviderMetadata],
                   sources: Mapping[str, Mapping[str, str]]) -> dict:
    """Reject stale generated data; never rewrite or touch a file."""
    expected = {provider: canonical_digest(files)
                for provider, files in sources.items()}
    rows: list[dict] = []
    for provider in sorted(set(expected) | set(metadata)):
        item = metadata.get(provider)
        actual = expected.get(provider, "")
        if item is None:
            fresh, reason = False, "missing_metadata"
        elif actual == "":
            fresh, reason = False, "no_source_inputs"
        elif item.input_digest != actual:
            fresh, reason = False, "digest_mismatch"
        else:
            fresh, reason = True, ""
        rows.append({
            "provider": provider, "fresh": fresh, "reason": reason,
            "metadata": item.describe() if item else None,
            "expected_digest": actual,
        })
    return {
        "feature_id": "D3.21", "fresh": all(row["fresh"] for row in rows),
        "reject_stale": True, "writes": False, "rewrites": False,
        "providers": rows,
    }


def assert_metadata_fresh(metadata: Mapping[str, ProviderMetadata],
                          sources: Mapping[str, Mapping[str, str]]) -> dict:
    report = check_metadata(metadata, sources)
    if not report["fresh"]:
        stale = [row["provider"] for row in report["providers"] if not row["fresh"]]
        raise MetadataError(f"stale generated provider metadata: {stale}")
    return report


# ===========================================================================
# D3.22 — inspector build seam (backend only, no frontend)
# ===========================================================================
@dataclass(frozen=True)
class PinnedSource:
    package: str
    version: str
    sha256: str

    def __post_init__(self) -> None:
        _nonempty(self.package, "package")
        _nonempty(self.version, "version")
        if not re.fullmatch(r"[0-9a-f]{64}", str(self.sha256)):
            raise InspectorError("a pinned source needs a 64-char sha256")

    def describe(self) -> dict:
        return {
            "package": self.package, "version": self.version,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class InspectorBuildSpec:
    source: PinnedSource
    output: str = "keel/inspector/dist"
    offline: bool = True
    browser_download: bool = False
    published: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.source, PinnedSource):
            raise InspectorError("spec.source must be a PinnedSource")
        if not self.offline or self.browser_download:
            raise InspectorError("inspector build must be offline with no browser download")

    def describe(self) -> dict:
        return {
            "feature_id": "D3.22", "source": self.source.describe(),
            "output": self.output, "offline": self.offline,
            "browser_download": self.browser_download,
            "published": self.published,
            "frontend_rendered": False,
        }


def inspector_build_plan(spec: InspectorBuildSpec) -> dict:
    """Read-only build plan: verify pin, compile locally, package the asset."""
    if not isinstance(spec, InspectorBuildSpec):
        raise InspectorError("spec must be an InspectorBuildSpec")
    steps = (
        {"step": "verify_pin", "network": False, "writes": False},
        {"step": "compile_local", "network": False, "writes": False},
        {"step": "package_asset", "network": False, "writes": False},
    )
    return {
        "feature_id": "D3.22", "spec": spec.describe(), "steps": list(steps),
        "network": False, "browser_download": False,
        "published_contains_built_frontend": spec.published,
        "backend_only": True,
    }


# Conservative text patterns retained for non-Python build recipes (shell, JS,
# JSON, ...).  Python sources are additionally analysed with ``ast`` below.
_NETWORK_BUILD_PATTERNS = (
    re.compile(r"https?://"),
    re.compile(r"\b(?:curl|wget)\b"),
    re.compile(r"\bfetch\s*\("),
    re.compile(r"\burlopen\s*\("),
    re.compile(r"\burlretrieve\s*\("),
    re.compile(r"\bcreate_connection\s*\("),
    re.compile(r"\b(?:import|from)\s+"
               r"(?:socket|urllib|requests|http|httpx|aiohttp|ftplib|smtplib)\b"),
)

# Roots of modules whose import alone gives a build step network reach.
_NETWORK_MODULE_ROOTS = frozenset({
    "socket", "ssl", "urllib", "http", "httplib", "requests", "httpx",
    "aiohttp", "ftplib", "smtplib", "imaplib", "poplib", "nntplib",
    "telnetlib", "xmlrpc", "websocket", "websockets", "grpc", "paramiko",
})

# High-signal call targets detected even without a statically resolved import.
_NETWORK_CALLS = frozenset({
    "urlopen", "urlretrieve", "create_connection", "socket.socket",
    "fetch", "download", "sendmail", "requests.get", "requests.post",
    "requests.request", "urllib.request.urlopen",
})

_PYTHON_SUFFIXES = (".py", ".pyw", ".pyi")

_OFFLINE_SCAN_LIMITS = (
    "Static analysis only: no build is executed and no runtime sandbox is used.",
    "Python sources (.py/.pyw/.pyi) are parsed with ast; unparseable Python fails closed.",
    "Other languages are checked with conservative text patterns (network only); "
    "file-write detection applies to Python sources.",
    "Dynamic code (eval/exec), non-literal imports and indirect calls are flagged "
    "when statically resolvable; fully opaque runtime behaviour cannot be proven absent.",
    "A clean report is a best-effort static check, not proof of offline execution.",
)


def _static_string(node: ast.AST) -> str | None:
    """Resolve literal strings, concatenations, joins and constant f-strings."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _static_string(node.left), _static_string(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts = [_static_string(value) for value in node.values]
        if all(part is not None for part in parts):
            return "".join(parts)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join" and node.args):
        items = node.args[0]
        if isinstance(items, (ast.List, ast.Tuple)):
            separator = _static_string(node.func.value)
            parts = [_static_string(element) for element in items.elts]
            if separator is not None and all(part is not None for part in parts):
                return separator.join(parts)
    return None


def _dynamic_import_target(call: ast.Call) -> str | None:
    """Return the literal module name of a dynamic import, if resolvable."""
    if call.args:
        if isinstance(call.func, ast.Name) and call.func.id == "__import__":
            return _static_string(call.args[0])
        if (isinstance(call.func, ast.Attribute)
                and call.func.attr == "import_module"):
            return _static_string(call.args[0])
    return None


def _static_dotted(node: ast.AST, bindings: Mapping[str, str]) -> str | None:
    """Resolve a Name/Attribute/getattr chain to a dotted name where possible."""
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _static_dotted(node.value, bindings)
        return None if base is None else f"{base}.{node.attr}"
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "getattr" and len(node.args) >= 2):
        base = _static_dotted(node.args[0], bindings)
        attribute = _static_string(node.args[1])
        if base is not None and attribute is not None:
            return f"{base}.{attribute}"
    return None


def _call_leaf(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _file_write_mode(call: ast.Call) -> bool:
    for argument in call.args[1:2]:
        mode = _static_string(argument)
        if mode and any(flag in mode for flag in "wax+"):
            return True
    for keyword in call.keywords:
        if keyword.arg == "mode":
            mode = _static_string(keyword.value)
            if mode and any(flag in mode for flag in "wax+"):
                return True
    return False


def _is_file_write_call(call: ast.Call, bindings: Mapping[str, str]) -> bool:
    dotted = _static_dotted(call.func, bindings) or ""
    leaf = _call_leaf(call)
    if leaf in ("write_text", "write_bytes", "write_file"):
        return True
    if leaf == "open" and _file_write_mode(call):
        return True
    if dotted == "os.open":
        for argument in call.args[1:]:
            flags = _static_dotted(argument, bindings) or _static_string(argument) or ""
            if re.search(r"O_(?:WRONLY|RDWR|APPEND|CREAT|TRUNC)", flags):
                return True
    return dotted in {
        "os.write", "os.replace", "os.rename", "shutil.copy",
        "shutil.copyfile", "shutil.copy2", "shutil.move",
    }


def _python_violations(text: str, name: str) -> list[str]:
    """AST-based static scan; syntax errors and opaque code fail closed."""
    try:
        tree = ast.parse(text, filename=name)
    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError) as exc:
        return ["unparseable_python:%s" % type(exc).__name__]

    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bindings[alias.asname] = alias.name
                else:
                    # ``import urllib.request`` binds the root name ``urllib``;
                    # the full path is recovered attribute by attribute.
                    root = alias.name.split(".")[0]
                    bindings[root] = root
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            for alias in node.names:
                dotted = f"{base}.{alias.name}" if base else alias.name
                bindings[alias.asname or alias.name] = dotted
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            target = _dynamic_import_target(node.value)
            if target is not None:
                for item in node.targets:
                    if isinstance(item, ast.Name):
                        bindings[item.id] = target

    reasons: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _NETWORK_MODULE_ROOTS:
                    reasons.append("network_import:%s" % alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            for alias in node.names:
                dotted = f"{base}.{alias.name}" if base else alias.name
                if dotted.split(".")[0] in _NETWORK_MODULE_ROOTS:
                    reasons.append("network_import:%s" % dotted)
        elif isinstance(node, ast.Call):
            target = _dynamic_import_target(node)
            if target is not None and target.split(".")[0] in _NETWORK_MODULE_ROOTS:
                reasons.append("dynamic_network_import:%s" % target)
            dotted = _static_dotted(node.func, bindings)
            if dotted is not None:
                if dotted.split(".")[0] in _NETWORK_MODULE_ROOTS or dotted in _NETWORK_CALLS:
                    reasons.append("network_call:%s" % dotted)
            if _is_file_write_call(node, bindings):
                reasons.append("file_write:%s" % (_call_leaf(call=node) or "call"))
            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                reasons.append("dynamic_code:%s" % node.func.id)
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and ("http://" in node.value or "https://" in node.value)):
            reasons.append("network_url_literal")
    return list(dict.fromkeys(reasons))


def check_offline_build(sources: Mapping[str, str]) -> dict:
    """Statically check build sources for network reach and file writes.

    This is a *source-text* check, not a build and not a runtime sandbox: it
    parses Python sources with :mod:`ast` and applies conservative text
    patterns to every source.  ``clean=True`` means only that no forbidden
    construct was found.  See ``limits`` for what cannot be proven.
    """
    if not isinstance(sources, Mapping):
        raise InspectorError("sources must be a mapping of name to source text")
    violations: list[str] = []
    reasons: dict[str, list[str]] = {}
    checked: list[str] = []
    for raw_name, raw_text in sorted(sources.items(), key=lambda item: str(item[0])):
        name = str(raw_name)
        checked.append(name)
        if not isinstance(raw_text, str):
            raise InspectorError("source %r must be text" % name)
        found = ["text_pattern:%s" % pattern.pattern
                 for pattern in _NETWORK_BUILD_PATTERNS
                 if pattern.search(raw_text)]
        if name.lower().endswith(_PYTHON_SUFFIXES):
            found.extend(_python_violations(raw_text, name))
        if found:
            violations.append(name)
            reasons[name] = list(dict.fromkeys(found))
    return {
        "feature_id": "D3.22", "checked": checked,
        "violations": violations, "reasons": reasons,
        "clean": not violations, "network": False, "io_performed": False,
        "method": "ast+text", "limits": _OFFLINE_SCAN_LIMITS,
    }


# ===========================================================================
# D3.23 — Live Share wire codecs (no browser carrier, no cloud relay)
# ===========================================================================
WIRE_MAGIC = b"KEEL1"
WIRE_VERSION = 1
WIRE_KINDS: tuple[str, ...] = ("hello", "event", "heartbeat", "bye")


def encode_message(kind: str, payload: Mapping[str, Any]) -> bytes:
    """Frame a JSON payload for the node wire codec (no socket is opened)."""
    if kind not in WIRE_KINDS:
        raise WireError(f"unknown wire kind {kind!r}")
    body = json.dumps(
        {"v": WIRE_VERSION, "kind": kind, "payload": dict(payload)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    checksum = hashlib.sha256(body).digest()[:8]
    return WIRE_MAGIC + len(body).to_bytes(4, "big") + body + checksum


def decode_message(data: bytes) -> dict:
    """Decode and verify a frame; reject corrupt or unsupported wire data."""
    if not isinstance(data, (bytes, bytearray)):
        raise WireError("wire frame must be bytes")
    frame = bytes(data)
    head = len(WIRE_MAGIC) + 4
    if len(frame) < head + 8:
        raise WireError("truncated wire frame")
    if frame[:len(WIRE_MAGIC)] != WIRE_MAGIC:
        raise WireError("bad wire magic")
    length = int.from_bytes(frame[len(WIRE_MAGIC):head], "big")
    end = head + length
    if end + 8 != len(frame):
        raise WireError("wire frame length mismatch")
    body, checksum = frame[head:end], frame[end:]
    if hashlib.sha256(body).digest()[:8] != checksum:
        raise WireError("wire checksum mismatch")
    try:
        message = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WireError("wire payload is not valid JSON") from exc
    if not isinstance(message, dict) or message.get("v") != WIRE_VERSION:
        raise WireError("unsupported wire version")
    if message.get("kind") not in WIRE_KINDS:
        raise WireError("unknown wire kind")
    return message


class WireCodec:
    """Node-compatible codec for a read-only, LAN-only viewer."""

    def encode(self, kind: str, payload: Mapping[str, Any]) -> bytes:
        return encode_message(kind, payload)

    def decode(self, data: bytes) -> dict:
        return decode_message(data)

    def describe(self) -> dict:
        return {
            "feature_id": "D3.23", "magic": WIRE_MAGIC.decode("ascii"),
            "version": WIRE_VERSION, "kinds": list(WIRE_KINDS),
            "read_only": True, "lan_only": True, "cloud_relay": False,
            "browser_carrier_implemented": False,
            "network": False, "io_performed": False,
        }


# ===========================================================================
# aggregate descriptors + verified P0 references
# ===========================================================================
def all_backend_descriptors() -> dict[str, dict]:
    """One uniform summary row per D3 backend feature implemented here."""
    def row(feature_id: str, name: str, contract: Sequence[str], **extra: Any) -> dict:
        return {
            "feature_id": feature_id, "name": name, "contract": list(contract),
            "layer": "stdlib_backend", "runtime_claimed": True,
            "io_performed": False, "network": False, "frontend": False,
            **extra,
        }

    return {
        "D3.3": row("D3.3", "subagent-providers",
                    tuple(k.value for k in SubagentKind)),
        "D3.4": row("D3.4", "agent-teams",
                    ("task_policy", "task_board", "messaging", "inbox")),
        "D3.5": row("D3.5", "agent-presets", tuple(r.value for r in Realm)),
        "D3.10": row("D3.10", "fs-policy", tuple(e.value for e in FsEvent)),
        "D3.12": row("D3.12", "deliverables", tuple(k.value for k in DeliverableKind)),
        "D3.15": row("D3.15", "extensions",
                     ("propose", "approve", "reject", "never_auto_install")),
        "D3.16": row("D3.16", "feedback", tuple(s.value for s in Sentiment)),
        "D3.17": row("D3.17", "identity", ("local_only", "never_transmitted")),
        "D3.19": row("D3.19", "plan-schedule", ("replayable_plan", "follow_ups")),
        "D3.20": row("D3.20", "quarantine", ("experimental", "product_policy")),
        "D3.21": row("D3.21", "provider-metadata",
                     ("generate", "read_only_staleness_check")),
        "D3.22": row("D3.22", "inspector-seam",
                     ("pinned_source", "offline_build", "published_asset")),
        "D3.23": row("D3.23", "liveshare-wire", tuple(WIRE_KINDS)),
    }


def verified_p0_references() -> dict[str, dict]:
    """Documented verification of the ten D3 P0 rows already in capability_seams."""
    source = "keel/src/keel/capability_seams.py"
    test = "keel/tests/test_capability_seams.py"
    return {
        "D3.1": {"source": source, "test": test,
                 "symbols": ("SeamRegistry", "CapabilitySeam", "seam_checklist")},
        "D3.2": {"source": source, "test": test,
                 "symbols": ("resolve_provider", "swap_world", "world_manifest")},
        "D3.6": {"source": source, "test": test,
                 "symbols": ("CommandService", "CommandRegistration")},
        "D3.7": {"source": source, "test": test,
                 "symbols": ("job_tools", "JOB_TOOLS")},
        "D3.8": {"source": source, "test": test,
                 "symbols": ("webhook_rule", "WebhookRuleDescriptor")},
        "D3.9": {"source": source, "test": test,
                 "symbols": ("backend_services", "sandbox_wrap_argv")},
        "D3.11": {"source": source, "test": test,
                  "symbols": ("classify_packages", "package_policy")},
        "D3.13": {"source": source, "test": test,
                  "symbols": ("plan_spill", "redact_preview")},
        "D3.14": {"source": source, "test": test,
                  "symbols": ("GuardRegistry", "GuardRegistration", "GuardVerdict")},
        "D3.18": {"source": source, "test": test,
                  "symbols": ("WorkspaceService", "SessionQueryService")},
    }


__all__ = [
    "FEATURE_IDS", "D3BackendError", "SubagentError", "TeamError", "PresetError",
    "FsPolicyError", "DeliverableError", "ExtensionError", "FeedbackError",
    "IdentityError", "PlanError", "ScheduleError", "QuarantineError",
    "MetadataError", "InspectorError", "WireError",
    "SUBAGENT_INTERFACE", "SubagentKind", "SubagentProvider",
    "ActivationDescriptor", "SubagentRegistry",
    "TaskState", "MessageKind", "BROADCAST", "TeamMember", "TeamTask",
    "TeamMessage", "TeamBoard", "TeamService",
    "Realm", "ServiceRow", "AgentPreset", "ResolvedPreset", "PresetService",
    "FsEvent", "FsRequest", "FsVerdict", "FsListener", "FsEventBus",
    "DeliverableKind", "Deliverable", "DeliverableService",
    "ExtensionKind", "ProposalState", "ExtensionProposal", "ExtensionService",
    "Sentiment", "Feedback", "FeedbackService",
    "InstallIdentity", "derive_install_id", "generate_install_id",
    "identity_from_seed", "generate_identity",
    "PlanEventKind", "PlanEvent", "PlanStep", "PlanLog", "ScheduledFollowUp",
    "ScheduleService", "PackageEntry", "ProductPackagePolicy",
    "ProviderMetadata", "canonical_digest", "generate_metadata",
    "check_metadata", "assert_metadata_fresh",
    "PinnedSource", "InspectorBuildSpec", "inspector_build_plan",
    "check_offline_build", "WIRE_MAGIC", "WIRE_VERSION", "WIRE_KINDS",
    "encode_message", "decode_message", "WireCodec",
    "all_backend_descriptors", "verified_p0_references",
]
