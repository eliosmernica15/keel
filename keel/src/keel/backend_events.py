"""Typed backend event contracts, a durable event bus and delivery tracking.

This module is deliberately self-contained and stdlib-only.  It provides:

* a *closed* union of frozen, versioned backend events with strict
  ``to_dict`` / ``from_dict`` round-trips (``SCHEMA_VERSION``);
* :class:`EventBus`, a publish/subscribe bus with per-subscriber cursors,
  idempotent event IDs, replay from a digest-chained JSONL log keyed by
  ``state_root``, and a cross-process exclusive lock so appends are atomic;
* :class:`DeliveryTracker`, which records outgoing delivery *attempts* with
  deterministic backoff, terminal failure and cancellation.  No network and
  no sleeping happen here -- success is only ever recorded from an explicit
  ``ok=True`` attempt.

Every persisted record carries a sequence number and a SHA-256 digest that
commits to its predecessor.  A truncated, reordered, edited or unparseable
log raises :class:`CorruptRecordError` instead of silently losing events.
A crash between appending a record and committing its ``.head`` marker is the
one exception: the verified tail is rolled forward (or a partial tail is
trimmed) under the same lock, and surfaced as a :class:`LogRecovery` value.

Durability uses only the standard library: a re-entrant in-process lock is
combined with an ``O_CREAT|O_EXCL`` lock file next to the log, so readers and
writers in *different processes* observe the same serialised history.

The event union is immutable by construction: all field values are scalars or
tuples, so an event produced in one module can be consumed in another without
sharing mutable state.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import types
import typing
from dataclasses import MISSING, dataclass, fields
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Mapping

__all__ = [
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "BackendEventsError",
    "EventSchemaError",
    "InvalidEventError",
    "UnknownEventKindError",
    "UnsupportedEventVersionError",
    "EventBusError",
    "CorruptRecordError",
    "EventBusLockError",
    "EventBusWriteError",
    "LogRecovery",
    "DuplicateEventError",
    "DeliveryError",
    "DuplicateDeliveryError",
    "DeliveryStateError",
    "BackendEvent",
    "SessionStarted",
    "TaskCreated",
    "TaskDelegated",
    "ToolInvoked",
    "PermissionDecided",
    "ApprovalRequested",
    "ApprovalResolved",
    "ApprovalConsumed",
    "ApprovalRevoked",
    "ProviderFailed",
    "JobQueued",
    "JobStarted",
    "JobCompleted",
    "JobCancelled",
    "EventDelivered",
    "ExtensionLoaded",
    "ExtensionUnloaded",
    "ErrorRecorded",
    "EVENT_TYPES",
    "EVENT_BY_KIND",
    "get_event_class",
    "build_event",
    "event_from_dict",
    "describe_event",
    "describe_event_schema",
    "EventBus",
    "Subscription",
    "DeliveryState",
    "compute_backoff",
    "DeliveryTracker",
]

SCHEMA_ID = "keel.backend_events"
SCHEMA_VERSION = 1
GENESIS_DIGEST = "0" * 64
_METADATA_TYPE = tuple[tuple[str, str], ...]


# ---------------------------------------------------------------------------
# Typed errors (fail closed, never silent)
# ---------------------------------------------------------------------------


class BackendEventsError(Exception):
    """Base class for every error raised by this module."""


class EventSchemaError(BackendEventsError, ValueError):
    """A serialised event does not satisfy the closed schema."""


class InvalidEventError(EventSchemaError):
    """Missing / extra / wrongly typed fields, or a kind/class mismatch."""


class UnknownEventKindError(EventSchemaError):
    """The ``kind`` is not part of the closed event union."""


class UnsupportedEventVersionError(EventSchemaError):
    """The event carries a schema version this build cannot decode."""


class EventBusError(BackendEventsError):
    """Base class for event-bus failures."""


class CorruptRecordError(EventBusError):
    """A durable JSONL record failed structural or chain verification."""

    def __init__(self, path: str | Path, line: int, reason: str):
        self.path = str(path)
        self.line = int(line)
        self.reason = str(reason)
        super().__init__(f"corrupt record {self.path}:{self.line}: {self.reason}")


class EventBusLockError(EventBusError):
    """The cross-process log lock could not be acquired or released.

    A live lock is never stolen: acquisition fails closed with this typed
    error after a bounded timeout.
    """


class EventBusWriteError(EventBusError):
    """A durable write could not be completed (e.g. a short record write)."""


@dataclass(frozen=True, slots=True)
class LogRecovery:
    """Typed description of an automatic recovery applied while opening a log.

    ``action`` is ``"committed_tail"`` when verified records beyond the
    committed head were rolled forward, or ``"truncated_tail"`` when an
    incomplete trailing record was discarded.  Neither case leaves the log
    unreadable; both are performed under the exclusive lock.
    """

    path: str
    action: str
    count: int
    seq: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "action": self.action,
            "count": self.count,
            "seq": self.seq,
            "digest": self.digest,
        }


class DuplicateEventError(EventBusError):
    """A different payload tried to reuse an existing event ID."""


class DeliveryError(BackendEventsError):
    """Base class for delivery-tracker failures."""


class DuplicateDeliveryError(DeliveryError):
    """A (event_id, target) pair was registered more than once."""


class DeliveryStateError(DeliveryError):
    """An attempted transition is illegal for the current delivery state."""


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _hints_for(cls: type) -> dict[str, Any]:
    """Resolved (not stringified) annotations for a dataclass."""
    return typing.get_type_hints(cls)


def _encode_value(value: Any) -> Any:
    """Turn immutable tuples into JSON arrays; leave scalars untouched."""
    if isinstance(value, tuple):
        return [_encode_value(item) for item in value]
    if isinstance(value, list):
        return [_encode_value(item) for item in value]
    return value


def _decode_value(value: Any, annotation: Any) -> Any:
    """Strictly decode one JSON value according to ``annotation``."""
    if annotation is Any:
        return value
    if annotation is str:
        if not isinstance(value, str):
            raise InvalidEventError(f"expected str, got {type(value).__name__}")
        return value
    if annotation is bool:
        if not isinstance(value, bool):
            raise InvalidEventError(f"expected bool, got {type(value).__name__}")
        return value
    if annotation is int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvalidEventError(f"expected int, got {type(value).__name__}")
        return value
    if annotation is float:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise InvalidEventError(f"expected float, got {type(value).__name__}")
        return float(value)

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is tuple or annotation is tuple:
        if not isinstance(value, list):
            raise InvalidEventError(f"expected tuple/array, got {type(value).__name__}")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode_value(item, args[0]) for item in value)
        if len(args) != len(value):
            raise InvalidEventError(
                f"expected {len(args)} tuple items, got {len(value)}")
        return tuple(_decode_value(item, kind) for item, kind in zip(value, args))

    if origin in (types.UnionType, typing.Union):
        none_allowed = type(None) in args
        if value is None and none_allowed:
            return None
        for option in args:
            if option is type(None):
                continue
            try:
                return _decode_value(value, option)
            except InvalidEventError:
                continue
        raise InvalidEventError(f"value {value!r} matches no union member")

    raise InvalidEventError(f"unsupported field annotation {annotation!r}")


def _normalize_metadata(value: Any) -> _METADATA_TYPE:
    """Copy caller-supplied pairs into an immutable tuple of tuples."""
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise ValueError("metadata must be an iterable of (str, str) pairs")
    try:
        items = list(value)
    except TypeError as exc:
        raise ValueError("metadata must be an iterable of (str, str) pairs") from exc
    result: list[tuple[str, str]] = []
    for item in items:
        if (not isinstance(item, (tuple, list)) or len(item) != 2
                or not all(isinstance(part, str) for part in item)):
            raise ValueError("metadata pairs must be (str, str)")
        result.append((item[0], item[1]))
    return tuple(result)


# ---------------------------------------------------------------------------
# Closed union of typed events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BackendEvent:
    """Base class; subclasses are registered in ``EVENT_BY_KIND`` only."""

    event_id: str

    KIND: ClassVar[str] = ""
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = ("event_id",)
    _union_closed: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # NOTE: ``@dataclass(slots=True)`` recreates the class, which triggers
        # this hook a second time.  Call object's hook explicitly: zero-arg
        # ``super()`` breaks on that synthetic class object.
        object.__init_subclass__()
        if BackendEvent._union_closed:
            raise TypeError("the backend event union is closed")

    def __post_init__(self) -> None:
        # Normalise mutable inputs to immutable tuples before any validation.
        if hasattr(type(self), "metadata"):
            object.__setattr__(self, "metadata",
                               _normalize_metadata(getattr(self, "metadata")))
        hints = _hints_for(type(self))
        for name in type(self).REQUIRED_ID_FIELDS:
            value = getattr(self, name, None)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        for f in fields(self):
            try:
                checked = _decode_value(_encode_value(getattr(self, f.name)),
                                        hints[f.name])
            except InvalidEventError as exc:
                raise ValueError(f"{f.name}: {exc}") from exc
            if checked != getattr(self, f.name):
                object.__setattr__(self, f.name, checked)

    def to_dict(self) -> dict[str, Any]:
        """Versioned, JSON-serialisable envelope for this event."""
        envelope: dict[str, Any] = {
            "schema": SCHEMA_ID,
            "version": SCHEMA_VERSION,
            "kind": self.KIND,
        }
        # Event fields live under ``data`` so a field named ``version`` (e.g.
        # ExtensionLoaded) can never shadow the schema version.
        envelope["data"] = {f.name: _encode_value(getattr(self, f.name))
                            for f in fields(self)}
        return envelope

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BackendEvent:
        """Decode an envelope, rejecting a wrong kind for the called class."""
        return _decode_event(payload, expected_cls=cls)


@dataclass(frozen=True, slots=True)
class SessionStarted(BackendEvent):
    KIND: ClassVar[str] = "session_started"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = ("event_id", "session_id")

    session_id: str
    cwd: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class TaskCreated(BackendEvent):
    KIND: ClassVar[str] = "task_created"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = ("event_id", "session_id", "task_id")

    session_id: str
    task_id: str
    title: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class TaskDelegated(BackendEvent):
    KIND: ClassVar[str] = "task_delegated"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = (
        "event_id", "session_id", "task_id", "agent_id")

    session_id: str
    task_id: str
    agent_id: str
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class ToolInvoked(BackendEvent):
    KIND: ClassVar[str] = "tool_invoked"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = (
        "event_id", "session_id", "tool_use_id")

    session_id: str
    tool_use_id: str
    tool_name: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class PermissionDecided(BackendEvent):
    KIND: ClassVar[str] = "permission_decided"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = (
        "event_id", "session_id", "tool_use_id")

    session_id: str
    tool_use_id: str
    decision: str = "deny"
    reason: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class ApprovalRequested(BackendEvent):
    KIND: ClassVar[str] = "approval_requested"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = (
        "event_id", "session_id", "approval_id")

    session_id: str
    approval_id: str
    tool_use_id: str = ""
    prompt: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class ApprovalResolved(BackendEvent):
    KIND: ClassVar[str] = "approval_resolved"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = (
        "event_id", "session_id", "approval_id")

    session_id: str
    approval_id: str
    decision: str = "deny"
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class ApprovalConsumed(BackendEvent):
    KIND: ClassVar[str] = "approval_consumed"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = (
        "event_id", "session_id", "approval_id")

    session_id: str
    approval_id: str
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class ApprovalRevoked(BackendEvent):
    KIND: ClassVar[str] = "approval_revoked"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = (
        "event_id", "session_id", "approval_id")

    session_id: str
    approval_id: str
    reason: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class ProviderFailed(BackendEvent):
    KIND: ClassVar[str] = "provider_failed"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = (
        "event_id", "session_id", "provider_id")

    session_id: str
    provider_id: str
    error_code: str = ""
    retryable: bool = False
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class JobQueued(BackendEvent):
    KIND: ClassVar[str] = "job_queued"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = ("event_id", "job_id")

    job_id: str
    session_id: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class JobStarted(BackendEvent):
    KIND: ClassVar[str] = "job_started"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = ("event_id", "job_id")

    job_id: str
    session_id: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class JobCompleted(BackendEvent):
    KIND: ClassVar[str] = "job_completed"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = ("event_id", "job_id")

    job_id: str
    session_id: str = ""
    status: str = "completed"
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class JobCancelled(BackendEvent):
    KIND: ClassVar[str] = "job_cancelled"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = ("event_id", "job_id")

    job_id: str
    session_id: str = ""
    reason: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class EventDelivered(BackendEvent):
    KIND: ClassVar[str] = "event_delivered"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = (
        "event_id", "delivery_id", "target", "delivered_event_id")

    delivery_id: str
    target: str
    delivered_event_id: str
    status: str = "delivered"
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class ExtensionLoaded(BackendEvent):
    KIND: ClassVar[str] = "extension_loaded"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = ("event_id", "extension_id")

    extension_id: str
    version: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class ExtensionUnloaded(BackendEvent):
    KIND: ClassVar[str] = "extension_unloaded"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = ("event_id", "extension_id")

    extension_id: str
    reason: str = ""
    metadata: _METADATA_TYPE = ()


@dataclass(frozen=True, slots=True)
class ErrorRecorded(BackendEvent):
    KIND: ClassVar[str] = "error_recorded"
    REQUIRED_ID_FIELDS: ClassVar[tuple[str, ...]] = ("event_id", "error_id")

    error_id: str
    severity: str = "error"
    message: str = ""
    metadata: _METADATA_TYPE = ()


EVENT_TYPES: tuple[type[BackendEvent], ...] = (
    SessionStarted,
    TaskCreated,
    TaskDelegated,
    ToolInvoked,
    PermissionDecided,
    ApprovalRequested,
    ApprovalResolved,
    ApprovalConsumed,
    ApprovalRevoked,
    ProviderFailed,
    JobQueued,
    JobStarted,
    JobCompleted,
    JobCancelled,
    EventDelivered,
    ExtensionLoaded,
    ExtensionUnloaded,
    ErrorRecorded,
)
EVENT_BY_KIND: dict[str, type[BackendEvent]] = {
    cls.KIND: cls for cls in EVENT_TYPES
}
BackendEvent._union_closed = True


def get_event_class(kind: str) -> type[BackendEvent]:
    """Look up a class in the closed union, or raise a typed error."""
    try:
        return EVENT_BY_KIND[kind]
    except (KeyError, TypeError):
        raise UnknownEventKindError(f"unknown backend event kind: {kind!r}") from None


def _decode_event(payload: Mapping[str, Any],
                  expected_cls: type[BackendEvent] | None = None) -> BackendEvent:
    if not isinstance(payload, Mapping):
        raise InvalidEventError("event envelope must be a mapping")
    version = payload.get("version")
    if not isinstance(version, int) or isinstance(version, bool) \
            or version != SCHEMA_VERSION:
        raise UnsupportedEventVersionError(
            f"unsupported event schema version: {version!r}")
    if payload.get("schema") != SCHEMA_ID:
        raise InvalidEventError(f"unknown event schema: {payload.get('schema')!r}")
    kind = payload.get("kind")
    cls = get_event_class(kind)
    if expected_cls is not None and cls is not expected_cls:
        raise InvalidEventError(
            f"kind {kind!r} does not match {expected_cls.__name__}.from_dict")
    if set(payload) != {"schema", "version", "kind", "data"}:
        raise InvalidEventError(
            "envelope must contain exactly schema, version, kind and data")
    data = payload["data"]
    if not isinstance(data, Mapping):
        raise InvalidEventError("envelope 'data' must be a mapping")
    hints = _hints_for(cls)
    allowed = {f.name for f in fields(cls)}
    missing = allowed.difference(data)
    if missing:
        raise InvalidEventError(f"missing fields: {sorted(missing)}")
    extra = set(data).difference(allowed)
    if extra:
        raise InvalidEventError(f"unknown fields: {sorted(extra)}")
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        raw = data[f.name]
        try:
            kwargs[f.name] = _decode_value(raw, hints[f.name])
        except InvalidEventError as exc:
            raise InvalidEventError(f"{f.name}: {exc}") from exc
    try:
        return cls(**kwargs)
    except (TypeError, ValueError) as exc:
        raise InvalidEventError(f"cannot construct {cls.__name__}: {exc}") from exc


def event_from_dict(payload: Mapping[str, Any]) -> BackendEvent:
    """Dispatch a versioned envelope to the correct typed event class."""
    return _decode_event(payload)


def build_event(kind: str, **values: Any) -> BackendEvent:
    """Factory helper: build a typed event from a kind name and field values."""
    cls = get_event_class(kind)
    try:
        return cls(**values)
    except (TypeError, ValueError) as exc:
        raise InvalidEventError(f"cannot build {kind}: {exc}") from exc


def describe_event(event: BackendEvent) -> dict[str, Any]:
    """Consumer helper: a plain summary derived from any typed event."""
    if not isinstance(event, BackendEvent):
        raise TypeError("expected a BackendEvent")
    ids = {name: getattr(event, name)
           for name in type(event).REQUIRED_ID_FIELDS}
    return {"kind": event.KIND, "version": SCHEMA_VERSION, "ids": ids,
            "metadata": list(event.metadata)}


def describe_event_schema() -> dict[str, Any]:
    """Machine-readable description of the closed, versioned event schema."""
    events: dict[str, Any] = {}
    for kind, cls in EVENT_BY_KIND.items():
        hints = _hints_for(cls)
        event_fields = []
        for f in fields(cls):
            event_fields.append({
                "name": f.name,
                "type": str(hints[f.name]),
                "required": f.default is MISSING,
                "is_id": f.name in cls.REQUIRED_ID_FIELDS,
            })
        events[kind] = {
            "class": cls.__name__,
            "fields": event_fields,
            "required_ids": list(cls.REQUIRED_ID_FIELDS),
        }
    return {
        "schema": SCHEMA_ID,
        "version": SCHEMA_VERSION,
        "kinds": list(EVENT_BY_KIND),
        "envelope": {
            "required": ["schema", "version", "kind", "data"],
            "schema": SCHEMA_ID,
            "version": SCHEMA_VERSION,
        },
        "events": events,
    }


# ---------------------------------------------------------------------------
# Durable JSONL records, digest chained and cross-process locked
# ---------------------------------------------------------------------------

# Bounded wait for a concurrent writer; stale locks are reclaimed only when
# their owning PID is provably gone (or has aged out with no readable PID).
_LOCK_TIMEOUT_SECONDS = 10.0
_STALE_LOCK_SECONDS = 30.0

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, Any] = {}
_BUS_STATES: dict[str, Any] = {}


class _BusSharedState:
    """Per-log shared subscriber list (subscribers survive bus re-creation)."""

    def __init__(self) -> None:
        self.subscriptions: list[Subscription] = []


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check; unknown outcomes are treated as alive.

    ``os.kill(pid, 0)`` is deliberately *not* used on Windows: it can report
    success for a process that has already exited, which would leave an
    abandoned lock file unwedgeable.  Query the real exit code instead.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # PROCESS_QUERY_LIMITED_INFORMATION; no PROCESS_ALL_ACCESS needed.
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True  # cannot tell: fail closed
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # a live process we may not signal
    except OSError as exc:
        return False if exc.errno == 3 else True  # ESRCH; else fail closed


class _LogLock:
    """Re-entrant guard combining an in-process ``RLock`` with a lock file.

    The in-process lock preserves the existing 20-thread behaviour (including
    re-entrant calls from subscriber callbacks) and serialises contenders
    before they touch the file system.  The ``O_CREAT|O_EXCL`` lock file makes
    the same critical section exclusive across *processes*.  Only the thread
    that owns the file lock writes the PID marker, and nested acquisitions on
    that thread simply increment a depth counter instead of re-locking.
    """

    def __init__(self, log_path: Path):
        self.path = Path(log_path)
        self.lock_path = Path(str(self.path) + ".lock")
        self.thread_lock = threading.RLock()
        self._local = threading.local()

    @property
    def _depth(self) -> int:
        return getattr(self._local, "depth", 0)

    def _lock_is_stale(self) -> bool:
        try:
            marker = self.lock_path.read_bytes().decode("ascii").strip()
        except FileNotFoundError:
            return True
        except (OSError, UnicodeDecodeError):
            return False  # unreadable marker: fail closed
        try:
            pid = int(marker.split(" ", 1)[0])
        except (ValueError, IndexError):
            pid = -1
        if pid == os.getpid():
            # Re-entrant depth handled in __enter__; anything else is a lock
            # left behind by a dead thread in this process.  Fail closed.
            return False
        if pid > 0:
            return not _pid_alive(pid)
        # No usable PID: reclaim only a clearly aged-out lock.
        try:
            age = time.time() - self.lock_path.stat().st_mtime
        except OSError:
            return False
        return age > _STALE_LOCK_SECONDS

    def _acquire_file(self) -> int:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fd = os.open(str(self.lock_path),
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                break
            except FileExistsError:
                if self._lock_is_stale():
                    try:
                        self.lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        raise EventBusLockError(
                            f"cannot clear stale event log lock "
                            f"{self.lock_path}: {exc}") from exc
                    continue
                if time.monotonic() >= deadline:
                    raise EventBusLockError(
                        f"timed out acquiring event log lock {self.lock_path}")
                time.sleep(0.005)
            except OSError as exc:
                raise EventBusLockError(
                    f"cannot create event log lock {self.lock_path}: {exc}") from exc
        try:
            marker = f"{os.getpid()} {time.time():.6f}\n".encode("ascii")
            os.write(fd, marker)
            os.fsync(fd)
        except OSError as exc:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                self.lock_path.unlink()
            except OSError:
                pass
            raise EventBusLockError(
                f"cannot write event log lock {self.lock_path}: {exc}") from exc
        return fd

    def _release_file(self, fd: int) -> None:
        try:
            os.close(fd)
        except OSError:
            pass
        # Windows can briefly refuse unlink while another contender reads the
        # lock marker.  Retry instead of abandoning a file that would then
        # look like a live lock to everyone else.
        deadline = time.monotonic() + 0.5
        while True:
            try:
                self.lock_path.unlink()
                return
            except FileNotFoundError:
                return
            except OSError:
                if time.monotonic() >= deadline:
                    return  # stale-lock handling will reclaim it
                time.sleep(0.002)

    def __enter__(self) -> "_LogLock":
        self.thread_lock.acquire()
        try:
            depth = self._depth
            if depth:
                self._local.depth = depth + 1
            else:
                self._local.fd = self._acquire_file()
                self._local.depth = 1
            return self
        except BaseException:
            self.thread_lock.release()
            raise

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        depth = self._depth
        if depth <= 1:
            fd = getattr(self._local, "fd", None)
            if fd is not None:
                self._release_file(fd)
                self._local.fd = None
            self._local.depth = 0
        else:
            self._local.depth = depth - 1
        self.thread_lock.release()


def _log_lock(path: str | Path) -> _LogLock:
    """One combined lock per resolved path, shared by all bus instances."""
    key = os.path.normcase(str(Path(path).resolve()))
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = _LogLock(Path(key))
            _PATH_LOCKS[key] = lock
        return lock


def _record_digest(record: Mapping[str, Any]) -> str:
    body = json.dumps(
        {"seq": record["seq"], "prev": record["prev"], "data": record["data"]},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _append_line(path: Path, record: Mapping[str, Any]) -> None:
    """Append one complete record with a single durable write.

    Called only while holding the log's exclusive lock.  A short write is
    rolled back to the exact prior size, so a partial record can never become
    visible to a reader (or wedge recovery).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    payload = (line + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        before = os.fstat(fd).st_size
        written = os.write(fd, payload)
        os.fsync(fd)
        if written != len(payload):
            os.ftruncate(fd, before)
            os.fsync(fd)
            raise EventBusWriteError(
                f"short write to {path}: {written} of {len(payload)} bytes")
    finally:
        os.close(fd)


def _write_head(path: Path, count: int, digest: str) -> None:
    """Atomically commit the committed record count and chain head."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"count": count, "digest": digest}, sort_keys=True,
                      separators=(",", ":"))
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                    dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


class _JsonlStore:
    """Append-only, digest-chained JSONL store with a cross-process lock.

    A sibling ``.head`` file commits the record count and chain head, so
    truncation or deletion of the tail is detectable rather than silently
    replaying a shorter history.  Reads, appends and head commits all run
    under the same exclusive lock file next to the log.
    """

    def __init__(self, path: Path, *, validator: Any = None):
        self.path = Path(path)
        self.head_path = Path(str(path) + ".head")
        self.validator = validator
        self.lock = _log_lock(self.path)
        self.records: list[dict[str, Any]] = []
        self.last_recovery: LogRecovery | None = None
        self.reload()

    def reload(self) -> None:
        with self.lock:
            self.records = self._read()

    def _read_head(self) -> dict[str, Any]:
        try:
            head = json.loads(self.head_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise CorruptRecordError(
                self.path, 0, f"unreadable commit head: {exc}") from exc
        if (not isinstance(head, dict) or set(head) != {"count", "digest"}
                or not isinstance(head["count"], int)
                or isinstance(head["count"], bool)
                or not isinstance(head["digest"], str)):
            raise CorruptRecordError(self.path, 0, "invalid commit head")
        return head

    @staticmethod
    def _is_uncommitted_tail(head: dict[str, Any] | None, count: int,
                             lineno: int, total: int) -> bool:
        """Only a final line beyond a committed prefix may be an interrupted write."""
        return head is not None and count >= head["count"] and lineno == total

    def _parse_line(self, raw: bytes, lineno: int,
                    records: list[dict[str, Any]], prev: str) -> dict[str, Any]:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise CorruptRecordError(
                self.path, lineno, "non-UTF-8 record") from None
        if not text.strip():
            raise CorruptRecordError(self.path, lineno, "blank line in log")
        try:
            obj = json.loads(text)
        except (ValueError, TypeError):
            raise CorruptRecordError(
                self.path, lineno, "unparseable JSON record") from None
        if not isinstance(obj, dict) or set(obj) != {"seq", "prev", "data", "digest"}:
            raise CorruptRecordError(self.path, lineno, "unexpected record shape")
        seq = obj["seq"]
        if not isinstance(seq, int) or isinstance(seq, bool) or seq != len(records) + 1:
            raise CorruptRecordError(self.path, lineno, f"bad sequence: {seq!r}")
        if obj["prev"] != prev:
            raise CorruptRecordError(self.path, lineno, "broken digest chain")
        if obj["digest"] != _record_digest(obj):
            raise CorruptRecordError(self.path, lineno, "digest mismatch")
        if self.validator is not None:
            self.validator(obj["data"], lineno)
        return obj

    def _truncate_tail(self, keep_bytes: int) -> None:
        fd = os.open(str(self.path), os.O_WRONLY, 0o600)
        try:
            os.ftruncate(fd, keep_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)

    def _read(self) -> list[dict[str, Any]]:
        """Verify the chain and reconcile the head with the durable records.

        Must be called under ``self.lock``.  The head is the commit marker; a
        *longer* verified log is an interrupted append and is rolled forward,
        while a trailing incomplete line is trimmed.  Any other mismatch is
        genuine corruption and still fails closed.
        """
        has_log = self.path.is_file()
        has_head = self.head_path.is_file()
        if not has_log:
            if has_head and self._read_head()["count"] != 0:
                raise CorruptRecordError(
                    self.path, 0, "log is missing but commit head has records")
            return []
        try:
            lines = self.path.read_bytes().split(b"\n")
        except OSError as exc:
            raise CorruptRecordError(self.path, 0, f"cannot read log: {exc}") from exc
        if lines and lines[-1] == b"":
            lines.pop()
        head = self._read_head() if has_head else None
        line_ends: list[int] = []
        cursor = 0
        for line in lines:
            cursor += len(line) + 1
            line_ends.append(cursor)

        records: list[dict[str, Any]] = []
        prev = GENESIS_DIGEST
        tail_index: int | None = None
        for lineno, raw in enumerate(lines, 1):
            try:
                obj = self._parse_line(raw, lineno, records, prev)
            except CorruptRecordError:
                if self._is_uncommitted_tail(head, len(records), lineno, len(lines)):
                    tail_index = lineno - 1
                    break
                raise
            records.append(obj)
            prev = obj["digest"]

        if tail_index is not None:
            # Discard the incomplete trailing record and re-commit the verified
            # prefix.  The lock guarantees no writer can observe the short log.
            keep = line_ends[tail_index - 1] if tail_index else 0
            self._truncate_tail(keep)
            _write_head(self.head_path, len(records), prev)
            self.last_recovery = LogRecovery(
                path=str(self.path), action="truncated_tail", count=1,
                seq=len(records), digest=prev)
            return records

        if head is None:
            if records:
                raise CorruptRecordError(
                    self.path, len(records), "missing commit head for non-empty log")
            return records
        if head["count"] > len(records):
            raise CorruptRecordError(
                self.path, len(records) + 1,
                "commit head claims more records than the log contains")
        if head["count"] < len(records):
            # Crash after the record was fsynced but before the head was
            # replaced: every extra record passed the full chain validation.
            _write_head(self.head_path, len(records), prev)
            self.last_recovery = LogRecovery(
                path=str(self.path), action="committed_tail",
                count=len(records) - head["count"], seq=len(records), digest=prev)
            return records
        if head["digest"] != prev:
            raise CorruptRecordError(
                self.path, len(records) + 1,
                f"commit head mismatch: expected digest={prev}")
        return records

    def append(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.records = self._read()
            seq = len(self.records) + 1
            prev = self.records[-1]["digest"] if self.records else GENESIS_DIGEST
            record = {"seq": seq, "prev": prev, "data": data}
            record["digest"] = _record_digest(record)
            if self.validator is not None:
                self.validator(data, seq)
            _append_line(self.path, record)
            _write_head(self.head_path, seq, record["digest"])
            self.records.append(record)
            return record


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class Subscription:
    """A subscriber's independent cursor into the durable event stream."""

    bus: EventBus
    name: str
    callback: Any
    cursor: int
    active: bool = True
    delivered: int = 0

    def pending(self) -> int:
        return max(0, len(self.bus.events) - self.cursor)

    def drain(self) -> int:
        """Deliver all pending events now; returns the number delivered."""
        return self.bus.drain(self)

    def cancel(self) -> None:
        self.active = False


class EventBus:
    """Publish/subscribe over a digest-chained JSONL log keyed by state_root.

    ``publish`` is atomic and idempotent per event ID.  It serialises append
    *and* subscriber delivery under an in-process lock plus an exclusive
    lock file, so subscribers always observe events in sequence order even
    with many concurrent publishers in separate processes.
    A handler that raises leaves its subscription cursor unchanged, giving
    at-least-once delivery rather than silent loss.
    """

    def __init__(self, state_root: str | Path, *,
                 log_name: str = "backend-events.jsonl"):
        self.state_root = Path(state_root)
        self.log_path = self.state_root / log_name
        self._store = _JsonlStore(self.log_path, validator=self._validate_record)
        self._events: list[BackendEvent] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        key = os.path.normcase(str(self.log_path.resolve()))
        with _LOCKS_GUARD:
            shared = _BUS_STATES.get(key)
            if shared is None:
                shared = _BusSharedState()
                _BUS_STATES[key] = shared
        self._shared = shared
        self._reindex()

    # -- validation / indexing ---------------------------------------------

    def _validate_record(self, data: Any, lineno: int) -> None:
        if not isinstance(data, dict) or set(data) != {"event"}:
            raise CorruptRecordError(
                self.log_path, lineno, "event record must contain only 'event'")
        try:
            event_from_dict(data["event"])
        except EventSchemaError as exc:
            raise CorruptRecordError(self.log_path, lineno, str(exc)) from exc

    def _reindex(self) -> None:
        events: list[BackendEvent] = []
        by_id: dict[str, dict[str, Any]] = {}
        for record in self._store.records:
            envelope = record["data"]["event"]
            event = event_from_dict(envelope)
            if event.event_id in by_id:
                raise CorruptRecordError(
                    self.log_path, record["seq"],
                    f"duplicate event id in log: {event.event_id}")
            by_id[event.event_id] = envelope
            events.append(event)
        self._events = events
        self._by_id = by_id

    def _refresh(self) -> None:
        self._store.reload()
        self._reindex()

    # -- public API ---------------------------------------------------------

    @property
    def last_recovery(self) -> LogRecovery | None:
        """Typed record of an automatic tail recovery applied on load, if any."""
        return self._store.last_recovery

    @property
    def events(self) -> tuple[BackendEvent, ...]:
        """Immutable snapshot of every durable event, in sequence order."""
        with self._store.lock:
            self._refresh()
            return tuple(self._events)

    def replay(self, from_cursor: int = 0) -> tuple[BackendEvent, ...]:
        """Replay durable events from ``from_cursor`` without delivering."""
        with self._store.lock:
            self._refresh()
            if not isinstance(from_cursor, int) or isinstance(from_cursor, bool) \
                    or not 0 <= from_cursor <= len(self._events):
                raise ValueError(f"invalid replay cursor: {from_cursor!r}")
            return tuple(self._events[from_cursor:])

    def subscribe(self, callback: Any, *, name: str = "",
                  from_cursor: int | None = None,
                  replay: bool = True) -> Subscription:
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._store.lock:
            self._refresh()
            start = len(self._events) if not replay and from_cursor is None else (
                0 if from_cursor is None else from_cursor)
            if not isinstance(start, int) or isinstance(start, bool) \
                    or not 0 <= start <= len(self._events):
                raise ValueError(f"invalid subscription cursor: {start!r}")
            sub = Subscription(bus=self, name=name or f"subscriber-{len(self._shared.subscriptions)}",
                               callback=callback, cursor=start)
            self._shared.subscriptions.append(sub)
            return sub

    def drain(self, sub: Subscription) -> int:
        """Deliver pending events for one subscription (cursor advances on success)."""
        with self._store.lock:
            self._refresh()
            if sub not in self._shared.subscriptions:
                raise EventBusError("subscription is not attached to this bus")
            count = 0
            while sub.active and sub.cursor < len(self._events):
                event = self._events[sub.cursor]
                sub.callback(event)
                sub.cursor += 1
                sub.delivered += 1
                count += 1
            return count

    def publish(self, event: BackendEvent) -> bool:
        """Append an event and deliver it in order.

        Returns ``True`` for a new event, ``False`` for an idempotent retry of
        an identical event ID.  A reused ID with a different payload raises
        :class:`DuplicateEventError`.
        """
        if not isinstance(event, BackendEvent):
            raise TypeError("publish expects a BackendEvent")
        envelope = event.to_dict()
        with self._store.lock:
            self._refresh()
            existing = self._by_id.get(event.event_id)
            if existing is not None:
                if existing == envelope:
                    return False
                raise DuplicateEventError(
                    f"event id {event.event_id!r} already used with a different payload")
            self._store.append({"event": envelope})
            self._reindex()
            for sub in list(self._shared.subscriptions):
                if sub.active:
                    while sub.cursor < len(self._events):
                        pending = self._events[sub.cursor]
                        sub.callback(pending)
                        sub.cursor += 1
                        sub.delivered += 1
            return True

    def subscribers(self) -> tuple[Subscription, ...]:
        return tuple(self._shared.subscriptions)


# ---------------------------------------------------------------------------
# Delivery tracking
# ---------------------------------------------------------------------------

_DELIVERY_STATUSES = frozenset({"pending", "delivered", "terminal", "cancelled"})
_DELIVERY_FIELDS = (
    "event_id", "target", "status", "attempts", "retry_count", "next_delay",
    "max_attempts", "base_delay", "backoff_factor", "max_delay", "error", "reason",
)


@dataclass(frozen=True, slots=True)
class DeliveryState:
    """Immutable snapshot of one logical delivery attempt sequence."""

    event_id: str
    target: str
    status: str
    attempts: int
    retry_count: int
    next_delay: float
    max_attempts: int
    base_delay: float
    backoff_factor: float
    max_delay: float
    error: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.event_id or not isinstance(self.event_id, str):
            raise ValueError("event_id must be a non-empty string")
        if not self.target or not isinstance(self.target, str):
            raise ValueError("target must be a non-empty string")
        if self.status not in _DELIVERY_STATUSES:
            raise ValueError(f"unknown delivery status: {self.status!r}")
        for name in ("attempts", "retry_count", "max_attempts"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative int")
        for name in ("next_delay", "base_delay", "backoff_factor", "max_delay"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative number")

    @property
    def is_success(self) -> bool:
        return self.status == "delivered"

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _DELIVERY_FIELDS}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DeliveryState:
        if not isinstance(data, Mapping) or set(data) != set(_DELIVERY_FIELDS):
            raise ValueError("invalid delivery state record")
        try:
            return cls(**dict(data))
        except TypeError as exc:
            raise ValueError(f"invalid delivery state: {exc}") from exc


def compute_backoff(attempt: int, *, base_delay: float,
                    backoff_factor: float, max_delay: float) -> float:
    """Pure, deterministic delay before ``attempt + 1`` (never sleeps)."""
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ValueError("attempt must be a positive int")
    delay = base_delay * (backoff_factor ** (attempt - 1))
    return float(min(delay, max_delay))


class DeliveryTracker:
    """Durable, network-free record of outgoing delivery attempts.

    Success is never assumed: only ``record_attempt(..., ok=True)`` can set
    ``status='delivered'``.  Failures are retried up to ``max_attempts`` with
    computed backoff and then become terminal.  A cancelled or terminal
    delivery rejects further attempts, so no fake success can be recorded.
    """

    def __init__(self, state_root: str | Path, *,
                 log_name: str = "backend-delivery.jsonl"):
        self.state_root = Path(state_root)
        self.log_path = self.state_root / log_name
        self._store = _JsonlStore(self.log_path, validator=self._validate_record)
        self._states: dict[tuple[str, str], DeliveryState] = {}
        self._rebuild()

    def _validate_record(self, data: Any, lineno: int) -> None:
        if not isinstance(data, dict) or set(data) != {"op", "state"}:
            raise CorruptRecordError(
                self.log_path, lineno, "delivery record must contain 'op' and 'state'")
        if data["op"] not in {"register", "attempt", "cancel"}:
            raise CorruptRecordError(self.log_path, lineno, "unknown delivery op")
        try:
            DeliveryState.from_dict(data["state"])
        except ValueError as exc:
            raise CorruptRecordError(self.log_path, lineno, str(exc)) from exc

    def _rebuild(self) -> None:
        states: dict[tuple[str, str], DeliveryState] = {}
        for record in self._store.records:
            data = record["data"]
            state = DeliveryState.from_dict(data["state"])
            key = (state.event_id, state.target)
            op = data["op"]
            previous = states.get(key)
            if op == "register":
                if previous is not None:
                    raise CorruptRecordError(
                        self.log_path, record["seq"], "duplicate delivery registration")
                if state.attempts != 0 or state.status != "pending":
                    raise CorruptRecordError(
                        self.log_path, record["seq"], "invalid initial delivery state")
            elif previous is None:
                raise CorruptRecordError(
                    self.log_path, record["seq"], "delivery transition without registration")
            elif op == "attempt" and state.attempts != previous.attempts + 1:
                raise CorruptRecordError(
                    self.log_path, record["seq"], "non-monotonic delivery attempt")
            states[key] = state
        self._states = states

    def _refresh(self) -> None:
        self._store.reload()
        self._rebuild()

    # -- public API ---------------------------------------------------------

    @property
    def last_recovery(self) -> LogRecovery | None:
        """Typed record of an automatic tail recovery applied on load, if any."""
        return self._store.last_recovery

    def register(self, event_id: str, target: str, *, max_attempts: int = 3,
                 base_delay: float = 0.05, backoff_factor: float = 2.0,
                 max_delay: float = 5.0) -> DeliveryState:
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) \
                or not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if base_delay < 0 or backoff_factor < 1 or max_delay < base_delay:
            raise ValueError("invalid backoff configuration")
        state = DeliveryState(
            event_id=event_id, target=target, status="pending", attempts=0,
            retry_count=0, next_delay=0.0, max_attempts=max_attempts,
            base_delay=float(base_delay), backoff_factor=float(backoff_factor),
            max_delay=float(max_delay))
        with self._store.lock:
            self._refresh()
            if (event_id, target) in self._states:
                raise DuplicateDeliveryError(
                    f"delivery already registered: {(event_id, target)!r}")
            self._store.append({"op": "register", "state": state.to_dict()})
            self._rebuild()
            return state

    def state(self, event_id: str, target: str) -> DeliveryState | None:
        with self._store.lock:
            self._refresh()
            return self._states.get((event_id, target))

    def states(self) -> dict[tuple[str, str], DeliveryState]:
        with self._store.lock:
            self._refresh()
            return dict(self._states)

    def pending(self) -> tuple[DeliveryState, ...]:
        with self._store.lock:
            self._refresh()
            return tuple(s for s in self._states.values() if s.status == "pending")

    def history(self) -> tuple[dict[str, Any], ...]:
        with self._store.lock:
            self._store.reload()
            return tuple(json.loads(json.dumps(r["data"]))
                         for r in self._store.records)

    def record_attempt(self, event_id: str, target: str, *, ok: bool,
                       error: str = "") -> DeliveryState:
        if not isinstance(ok, bool):
            raise TypeError("ok must be a bool")
        with self._store.lock:
            self._refresh()
            key = (event_id, target)
            previous = self._states.get(key)
            if previous is None:
                raise DeliveryStateError(f"unknown delivery: {key!r}")
            if previous.status != "pending":
                raise DeliveryStateError(
                    f"cannot attempt a {previous.status} delivery: {key!r}")
            attempt = previous.attempts + 1
            if ok:
                state = DeliveryState(
                    **{**previous.to_dict(), "status": "delivered",
                       "attempts": attempt, "next_delay": 0.0, "error": ""})
            elif attempt >= previous.max_attempts:
                state = DeliveryState(
                    **{**previous.to_dict(), "status": "terminal",
                       "attempts": attempt, "next_delay": 0.0,
                       "error": error[:300]})
            else:
                state = DeliveryState(
                    **{**previous.to_dict(), "status": "pending",
                       "attempts": attempt,
                       "retry_count": previous.retry_count + 1,
                       "next_delay": compute_backoff(
                           attempt, base_delay=previous.base_delay,
                           backoff_factor=previous.backoff_factor,
                           max_delay=previous.max_delay),
                       "error": error[:300]})
            self._store.append({"op": "attempt", "state": state.to_dict()})
            self._rebuild()
            return state

    def cancel(self, event_id: str, target: str, *, reason: str = "") -> DeliveryState:
        with self._store.lock:
            self._refresh()
            key = (event_id, target)
            previous = self._states.get(key)
            if previous is None:
                raise DeliveryStateError(f"unknown delivery: {key!r}")
            if previous.status == "cancelled":
                return previous
            if previous.status in {"delivered", "terminal"}:
                raise DeliveryStateError(
                    f"cannot cancel a {previous.status} delivery: {key!r}")
            state = DeliveryState(
                **{**previous.to_dict(), "status": "cancelled",
                   "next_delay": 0.0, "reason": reason[:300]})
            self._store.append({"op": "cancel", "state": state.to_dict()})
            self._rebuild()
            return state
