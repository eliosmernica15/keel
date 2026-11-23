"""keel.config_contracts -- config / setup / sign-in contracts (Y3.x P0).

This is an *additive* module.  It does not edit ``keel.settings``,
``keel.settings_store``, ``keel.onboarding``, ``keel.start_health``, the web
app, the CLI, the fleet DB layer or any existing test.  Integration into the
live runtime is a separate lead decision (the exact seams are listed in
``master-plan-v6-config-contracts-evidence.md``).

The seven not_started P0 registry IDs are turned into real, testable Python
functionality:

  Y3.2  reuse before building + "server is the only DB client" .............. ReusePolicy, ServerOnlyDbPolicy, evaluate_reuse, validate_db_client
  Y3.4  relay stores every run event (typed envelope + audit) ............... RunEventEnvelope, EventAuditGuarantee, EventLedger, check_event_completeness
  Y3.6  table ideas / schema additions as data-only descriptors ............. Column, TableDescriptor, SCHEMA_ADDITIONS, validate_schema
  Y3.9  sign out / sign out everywhere / disconnect (revocations) .......... RevocationScope, TokenRevocationDescriptor, build_revocation, RevocationLedger
  Y3.10 local-only sign-in, no account/cloud, offline guarantee ............. LocalSignInDescriptor, validate_offline_guarantee, validate_signin_policy
  Y3.11 deterministic mock agent, clearly labelled, never a real provider .. MockAgentDescriptor, MockAgent, assert_never_real_provider
  Y3.13 setup: generate-only, never overwrite, atomic seam, idempotent ..... GeneratedFile, GenerationPlan, apply_plan, setup_once, WriteSeam

Only the Python standard library is used.  There is no network, no socket, no
subprocess, no SQL execution, no credential value and no filesystem I/O in this
module: persistence is represented by injectable *seams* whose default methods
raise ``NotImplementedError``.  There are no import-time side effects and no
uuid/rng: every id and fingerprint is a deterministic SHA-256 prefix.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, fields, replace
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Callable, Collection, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# shared helpers: canonical bytes, content hashes, typed errors
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 encoding used by every hash in this module."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def stamp(clock: Callable[[], float] | None = None) -> str:
    """UTC ISO-8601 stamp for an injectable epoch-seconds callable.

    Kept as a pure function of *clock*; every identity below deliberately
    excludes the stamp so ids stay reproducible across runs.
    """
    from datetime import datetime, timezone
    import time
    now = float(clock()) if clock is not None else time.time()
    return datetime.fromtimestamp(now, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z")


class ConfigContractError(ValueError):
    """Base class for all typed config-contract failures."""


class PolicyViolation(ConfigContractError):
    """A requested action breaks a stated reuse / DB / sign-in policy."""


class DbClientViolation(PolicyViolation):
    """A non-server component tried to act as a database client."""


class EventContractError(ConfigContractError):
    """An event envelope was malformed or a run log is incomplete."""


class SchemaDescriptorError(ConfigContractError):
    """A data-only schema descriptor was invalid."""


class RevocationError(ConfigContractError):
    """A revocation descriptor was malformed or leaked a secret."""


class OfflineGuaranteeError(ConfigContractError):
    """A sign-in descriptor depends on an account, cloud or network."""


class MockLabelingError(ConfigContractError):
    """A mock agent was mislabelled or presented as a real provider."""


class SetupContractError(ConfigContractError):
    """A generated file or setup plan was invalid."""


class OverwriteError(SetupContractError):
    """A target file already exists and may not be overwritten."""


# ---------------------------------------------------------------------------
# Y3.2 -- reuse before building / server is the only DB client
# ---------------------------------------------------------------------------


class Disposition(str, Enum):
    REUSE = "reuse"
    BUILD = "build"
    REJECTED = "rejected"


class DbClientKind(str, Enum):
    SERVER = "server"
    CLIENT = "client"
    WORKER = "worker"
    RELAY = "relay"
    MIGRATION = "migration"
    TOOL = "tool"


@dataclass(frozen=True)
class ExistingCapability:
    """A capability that already exists in the codebase (reuse first)."""

    name: str
    covers: tuple[str, ...] = ()
    available: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise PolicyViolation("capability needs a non-empty name")
        covers = tuple(self.covers or ())
        if any(not isinstance(c, str) or not c for c in covers):
            raise PolicyViolation("covers entries must be non-empty strings")
        object.__setattr__(self, "covers", covers)

    def to_dict(self) -> dict:
        return {"name": self.name, "covers": list(self.covers),
                "available": self.available}


@dataclass(frozen=True)
class ReuseRequest:
    capability: str
    justification: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.capability, str) or not self.capability.strip():
            raise PolicyViolation("reuse request needs a capability name")


@dataclass(frozen=True)
class ReuseDecision:
    capability: str
    disposition: Disposition
    matched_capability: str = ""
    reasons: tuple[str, ...] = ()
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "disposition", Disposition(self.disposition))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash({
                "capability": self.capability,
                "disposition": self.disposition.value,
                "matched_capability": self.matched_capability,
            })[:16])

    def to_dict(self) -> dict:
        return {"capability": self.capability,
                "disposition": self.disposition.value,
                "matched_capability": self.matched_capability,
                "reasons": list(self.reasons),
                "fingerprint": self.fingerprint}


@dataclass(frozen=True)
class ReusePolicy:
    """Descriptor of the 'reuse before building' policy."""

    name: str = "reuse-before-building"
    require_justification_to_build: bool = True
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash({
                "name": self.name,
                "require_justification_to_build":
                    self.require_justification_to_build,
            })[:16])

    def to_dict(self) -> dict:
        return {"name": self.name,
                "require_justification_to_build":
                    self.require_justification_to_build,
                "fingerprint": self.fingerprint}


def evaluate_reuse(request: ReuseRequest,
                   catalog: Sequence[ExistingCapability],
                   policy: ReusePolicy | None = None) -> ReuseDecision:
    """Reuse an available covering capability; otherwise demand a justification.

    A build with no justification is *rejected*, not silently approved: the
    default is always to reuse what the codebase already has.
    """
    rules = policy or ReusePolicy()
    for capability in catalog:
        if capability.available and request.capability in capability.covers:
            return ReuseDecision(
                request.capability, Disposition.REUSE, capability.name,
                ("existing capability covers the request",))
    if (request.justification.strip()
            or not rules.require_justification_to_build):
        return ReuseDecision(
            request.capability, Disposition.BUILD, "",
            ("no existing capability covers the request",
             "build justification recorded"))
    return ReuseDecision(
        request.capability, Disposition.REJECTED, "",
        ("reuse first: no covering capability is available",
         "a build justification is required"))


@dataclass(frozen=True)
class DbClientClaim:
    component: str
    kind: DbClientKind | str
    accesses_db: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.component, str) or not self.component.strip():
            raise PolicyViolation("DB client claim needs a component name")
        object.__setattr__(self, "kind", DbClientKind(self.kind))
        if not isinstance(self.accesses_db, bool):
            raise PolicyViolation("accesses_db must be a bool")

    def to_dict(self) -> dict:
        return {"component": self.component, "kind": self.kind.value,
                "accesses_db": self.accesses_db}


@dataclass(frozen=True)
class DbAccessDecision:
    component: str
    allowed: bool
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))

    def to_dict(self) -> dict:
        return {"component": self.component, "allowed": self.allowed,
                "reasons": list(self.reasons)}


@dataclass(frozen=True)
class ServerOnlyDbPolicy:
    """Descriptor: only the server process may open the database."""

    name: str = "server-is-only-db-client"
    allowed_kinds: tuple[str, ...] = (DbClientKind.SERVER.value,)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_kinds", tuple(self.allowed_kinds))
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash({
                "name": self.name, "allowed_kinds": self.allowed_kinds,
            })[:16])

    def to_dict(self) -> dict:
        return {"name": self.name, "allowed_kinds": list(self.allowed_kinds),
                "fingerprint": self.fingerprint}


def validate_db_client(claim: DbClientClaim,
                       policy: ServerOnlyDbPolicy | None = None
                       ) -> DbAccessDecision:
    rules = policy or ServerOnlyDbPolicy()
    allowed_kinds = {DbClientKind(k) for k in rules.allowed_kinds}
    if not claim.accesses_db:
        return DbAccessDecision(claim.component, True,
                                ("component does not access the DB",))
    if claim.kind in allowed_kinds:
        return DbAccessDecision(claim.component, True,
                                ("server is the only DB client",))
    return DbAccessDecision(
        claim.component, False,
        (f"{claim.kind.value} may not open the database",
         "route all DB work through the server"))


def assert_db_client_allowed(claim: DbClientClaim,
                             policy: ServerOnlyDbPolicy | None = None) -> bool:
    decision = validate_db_client(claim, policy)
    if not decision.allowed:
        raise DbClientViolation("; ".join(decision.reasons))
    return True


# ---------------------------------------------------------------------------
# Y3.4 -- relay stores every run event (typed envelope + audit guarantee)
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    USER_MESSAGE = "message.user"
    AGENT_MESSAGE = "message.agent"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    APPROVAL = "approval.decision"
    ERROR = "run.error"
    HEARTBEAT = "run.heartbeat"


#: Every event type the relay must retain so a client can reconnect and replay.
RELAY_REQUIRED_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.RUN_STARTED,
    EventType.USER_MESSAGE,
    EventType.AGENT_MESSAGE,
    EventType.TOOL_CALL,
    EventType.TOOL_RESULT,
    EventType.APPROVAL,
    EventType.RUN_FINISHED,
)

_SECRET_FIELD_NAMES = frozenset({
    "token", "secret", "password", "api_key", "apikey", "access_token",
    "refresh_token", "credential", "credential_value", "private_key",
})


@dataclass(frozen=True)
class RunEventEnvelope:
    """One typed, content-addressed run event.  Carries no secret values."""

    run_id: str
    seq: int
    event_type: EventType
    payload: dict
    source: str = "relay"
    occurred_at: str = ""
    event_id: str = ""
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise EventContractError("event needs a run_id")
        if not isinstance(self.seq, int) or self.seq < 1:
            raise EventContractError("event seq must be a positive integer")
        try:
            object.__setattr__(self, "event_type", EventType(self.event_type))
        except ValueError:
            raise EventContractError(
                f"unknown event type: {self.event_type!r}") from None
        if not isinstance(self.payload, dict):
            raise EventContractError("event payload must be a JSON object")
        try:
            canonical_bytes(self.payload)
        except (TypeError, ValueError) as exc:
            raise EventContractError(f"event payload is not JSON: {exc}") from None
        if not isinstance(self.source, str) or not self.source:
            raise EventContractError("event needs a source")
        if not isinstance(self.occurred_at, str) or not self.occurred_at:
            raise EventContractError("event needs an occurred_at stamp")
        identity = content_hash({
            "run_id": self.run_id, "seq": self.seq,
            "event_type": self.event_type.value, "payload": self.payload,
        })[:16]
        if self.event_id and self.event_id != identity:
            raise EventContractError("event_id does not commit to its content")
        object.__setattr__(self, "event_id", identity)
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash(self.to_dict(
                include_fingerprint=False))[:16])

    def to_dict(self, *, include_fingerprint: bool = True) -> dict:
        doc = {"run_id": self.run_id, "seq": self.seq,
               "event_type": self.event_type.value, "payload": dict(self.payload),
               "source": self.source, "occurred_at": self.occurred_at,
               "event_id": self.event_id}
        if include_fingerprint:
            doc["fingerprint"] = self.fingerprint
        return doc

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunEventEnvelope":
        d = dict(data)
        return cls(run_id=str(d.get("run_id") or ""),
                   seq=int(d.get("seq", 0)),
                   event_type=d.get("event_type", EventType.RUN_STARTED),
                   payload=dict(d.get("payload") or {}),
                   source=str(d.get("source") or "relay"),
                   occurred_at=str(d.get("occurred_at") or ""),
                   event_id=str(d.get("event_id") or ""),
                   fingerprint=str(d.get("fingerprint") or ""))


def build_event_envelope(run_id: str, seq: int, event_type: EventType | str,
                         payload: dict | None = None, *, source: str = "relay",
                         clock: Callable[[], float] | None = None
                         ) -> RunEventEnvelope:
    """Create an envelope whose identity excludes wall-clock time."""
    return RunEventEnvelope(
        run_id=run_id, seq=seq, event_type=event_type,
        payload=dict(payload or {}), source=source, occurred_at=stamp(clock))


@dataclass(frozen=True)
class EventAuditGuarantee:
    """Descriptor declaring that the relay persists *every* run event."""

    run_id: str
    required_event_types: tuple[str, ...]
    event_count: int
    store_all: bool = True
    append_only: bool = True
    replayable: bool = True
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_event_types",
                           tuple(self.required_event_types))
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash({
                "run_id": self.run_id,
                "required_event_types": self.required_event_types,
                "event_count": self.event_count, "store_all": self.store_all,
                "append_only": self.append_only,
                "replayable": self.replayable,
            })[:16])

    def to_dict(self) -> dict:
        return {"run_id": self.run_id,
                "required_event_types": list(self.required_event_types),
                "event_count": self.event_count, "store_all": self.store_all,
                "append_only": self.append_only,
                "replayable": self.replayable,
                "fingerprint": self.fingerprint}


@dataclass(frozen=True)
class CompletenessReport:
    run_id: str
    complete: bool
    missing: tuple[str, ...] = ()
    seq_gaps: tuple[int, ...] = ()
    duplicates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing", tuple(self.missing))
        object.__setattr__(self, "seq_gaps", tuple(self.seq_gaps))
        object.__setattr__(self, "duplicates", tuple(self.duplicates))

    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "complete": self.complete,
                "missing": list(self.missing), "seq_gaps": list(self.seq_gaps),
                "duplicates": list(self.duplicates)}


def check_event_completeness(
        events: Sequence[RunEventEnvelope], *,
        required_types: Sequence[EventType | str] = RELAY_REQUIRED_EVENT_TYPES,
        run_id: str = "") -> CompletenessReport:
    """Prove a run log holds every required type with no gaps or duplicates."""
    if not events:
        return CompletenessReport(
            run_id, False, tuple(sorted(EventType(t).value for t in required_types)))
    rid = run_id or events[0].run_id
    required = {EventType(t) for t in required_types}
    present = {e.event_type for e in events}
    missing = tuple(sorted(t.value for t in required - present))
    seqs = sorted(e.seq for e in events)
    seq_gaps = tuple(s for s in range(1, seqs[-1] + 1) if s not in set(seqs))
    seen: set[str] = set()
    duplicates: list[str] = []
    for event in events:
        if event.event_id in seen:
            duplicates.append(event.event_id)
        seen.add(event.event_id)
    complete = not (missing or seq_gaps or duplicates)
    return CompletenessReport(rid, complete, missing, seq_gaps,
                              tuple(duplicates))


def audit_guarantee(run_id: str, events: Sequence[RunEventEnvelope],
                    *, required_types: Sequence[EventType | str] =
                    RELAY_REQUIRED_EVENT_TYPES) -> EventAuditGuarantee:
    return EventAuditGuarantee(
        run_id=run_id,
        required_event_types=tuple(EventType(t).value for t in required_types),
        event_count=len(events))


class RelayStorageSeam:
    """Replace with a real relay store; no I/O or network lives here."""

    def store(self, event: RunEventEnvelope) -> None:  # pragma: no cover - seam
        raise NotImplementedError

    def all_events(self, run_id: str) -> tuple[RunEventEnvelope, ...]:
        # pragma: no cover - seam
        raise NotImplementedError


class EventLedger:
    """In-memory, append-only ledger used to validate the audit contract.

    This is a pure accumulator, *not* a durable store: the registry's "no
    actual storage" constraint is honoured by keeping persistence behind
    ``RelayStorageSeam``.
    """

    def __init__(self, run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id:
            raise EventContractError("ledger needs a run_id")
        self.run_id = run_id
        self._events: list[RunEventEnvelope] = []

    def append(self, event: RunEventEnvelope) -> RunEventEnvelope:
        if not isinstance(event, RunEventEnvelope):
            raise EventContractError("ledger only accepts RunEventEnvelope")
        if event.run_id != self.run_id:
            raise EventContractError("event belongs to a different run")
        if event.seq != len(self._events) + 1:
            raise EventContractError(
                f"expected seq {len(self._events) + 1}, got {event.seq}")
        if any(e.event_id == event.event_id for e in self._events):
            raise EventContractError("duplicate event_id")
        self._events.append(event)
        return event

    def events(self) -> tuple[RunEventEnvelope, ...]:
        return tuple(self._events)

    def audit(self) -> EventAuditGuarantee:
        return audit_guarantee(self.run_id, self.events())

    def completeness(self) -> CompletenessReport:
        return check_event_completeness(self.events(), run_id=self.run_id)


def assert_event_secrets_absent(event: RunEventEnvelope,
                                forbidden_values: Iterable[str] = ()
                                ) -> bool:
    """Fail if a secret field name or a known secret value reached an event."""
    doc = json.dumps(event.to_dict(), sort_keys=True)
    keys = {str(k).lower() for k in event.payload}
    if keys & _SECRET_FIELD_NAMES:
        raise EventContractError("event payload exposes a secret field name")
    for value in forbidden_values:
        if value and value in doc:
            raise EventContractError("event carries a secret value")
    return True


# ---------------------------------------------------------------------------
# Y3.6 -- table ideas / schema additions as data-only descriptors
# ---------------------------------------------------------------------------


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COLUMN_TYPES = frozenset({
    "TEXT", "INTEGER", "REAL", "BLOB", "NUMERIC", "BOOLEAN", "TIMESTAMP",
    "JSON",
})


def _is_identifier(value: str) -> bool:
    return isinstance(value, str) and bool(_IDENTIFIER_RE.fullmatch(value))


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    primary_key: bool = False
    nullable: bool = True
    references: str = ""

    def __post_init__(self) -> None:
        if not _is_identifier(self.name):
            raise SchemaDescriptorError(f"unsafe column identifier {self.name!r}")
        column_type = str(self.type).upper()
        if column_type not in _COLUMN_TYPES:
            raise SchemaDescriptorError(f"unknown column type {self.type!r}")
        object.__setattr__(self, "type", column_type)
        if self.references and not _is_identifier(self.references):
            raise SchemaDescriptorError(
                f"unsafe reference identifier {self.references!r}")

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type,
                "primary_key": self.primary_key, "nullable": self.nullable,
                "references": self.references}


@dataclass(frozen=True)
class TableDescriptor:
    """A data-only description of a proposed table.  Never executed here."""

    name: str
    columns: tuple[Column, ...]
    indexes: tuple[str, ...] = ()
    purpose: str = ""
    retained_on_erase: bool = False

    def __post_init__(self) -> None:
        if not _is_identifier(self.name):
            raise SchemaDescriptorError(f"unsafe table identifier {self.name!r}")
        columns = tuple(self.columns)
        if not columns or any(not isinstance(c, Column) for c in columns):
            raise SchemaDescriptorError("a table needs at least one Column")
        names = [c.name for c in columns]
        if len(set(names)) != len(names):
            raise SchemaDescriptorError("duplicate column name in table")
        indexes = tuple(self.indexes)
        if any(not _is_identifier(i) for i in indexes):
            raise SchemaDescriptorError("unsafe index identifier")
        if any(i not in names for i in indexes):
            raise SchemaDescriptorError("index names an unknown column")
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "indexes", indexes)

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"name": self.name,
                "columns": [c.to_dict() for c in self.columns],
                "indexes": list(self.indexes), "purpose": self.purpose,
                "retained_on_erase": self.retained_on_erase}


def _table(name: str, columns: Sequence[tuple[str, str]], *,
           purpose: str = "", indexes: Sequence[str] = (),
           retained_on_erase: bool = False) -> TableDescriptor:
    return TableDescriptor(
        name=name,
        columns=tuple(Column(n, t) for n, t in columns),
        indexes=tuple(indexes), purpose=purpose,
        retained_on_erase=retained_on_erase)


_PK = ("id", "TEXT")

#: The registry's "table ideas / schema additions" (Y3.6), as pure data.
SCHEMA_ADDITIONS: tuple[TableDescriptor, ...] = (
    _table("task_events", [_PK, ("task_id", "TEXT"), ("kind", "TEXT"),
                           ("payload", "JSON"), ("created_at", "TIMESTAMP")],
           purpose="append-only per-task event log", indexes=("task_id",)),
    _table("task_files", [_PK, ("task_id", "TEXT"), ("path", "TEXT"),
                          ("sha256", "TEXT"), ("byte_size", "INTEGER")],
           purpose="files touched by a task", indexes=("task_id",)),
    _table("project_proposals", [_PK, ("project_id", "TEXT"),
                                  ("title", "TEXT"), ("body", "TEXT"),
                                  ("status", "TEXT")],
           purpose="proposed project changes awaiting a decision"),
    _table("knowledge", [_PK, ("title", "TEXT"), ("body", "TEXT"),
                         ("source", "TEXT"), ("created_at", "TIMESTAMP")],
           purpose="local knowledge entries"),
    _table("shares", [_PK, ("artifact_id", "TEXT"), ("visibility", "TEXT"),
                      ("created_at", "TIMESTAMP")],
           purpose="explicit share opt-in records"),
    _table("notifications", [_PK, ("subject", "TEXT"), ("body", "TEXT"),
                              ("read", "BOOLEAN"), ("created_at", "TIMESTAMP")],
           purpose="local notifications"),
    _table("automation_runs", [_PK, ("automation_id", "TEXT"),
                                ("status", "TEXT"),
                                ("started_at", "TIMESTAMP")],
           purpose="automation run history"),
    _table("recordings", [_PK, ("session_id", "TEXT"), ("path", "TEXT"),
                          ("sha256", "TEXT")],
           purpose="descriptors for local recordings"),
    _table("meetings", [_PK, ("title", "TEXT"), ("started_at", "TIMESTAMP"),
                        ("notes", "TEXT")],
           purpose="meeting metadata"),
    _table("api_keys", [_PK, ("label", "TEXT"), ("key_hash", "TEXT"),
                        ("created_at", "TIMESTAMP")],
           purpose="hashed API key records, never raw secrets"),
    _table("webhooks", [_PK, ("url", "TEXT"), ("event", "TEXT"),
                        ("enabled", "BOOLEAN")],
           purpose="webhook registrations"),
    _table("webhook_deliveries", [_PK, ("webhook_id", "TEXT"),
                                   ("status", "TEXT"), ("attempt", "INTEGER"),
                                   ("created_at", "TIMESTAMP")],
           purpose="webhook delivery attempts", indexes=("webhook_id",)),
    _table("revocations", [_PK, ("subject_id", "TEXT"), ("scope", "TEXT"),
                            ("revoked_at", "TIMESTAMP")],
           purpose="token revocations, kept even when user data is erased",
           indexes=("subject_id",), retained_on_erase=True),
    _table("usage_counters", [_PK, ("metric", "TEXT"), ("count", "INTEGER"),
                               ("period", "TEXT")],
           purpose="aggregate usage counters"),
    _table("ops_events", [_PK, ("kind", "TEXT"), ("payload", "JSON"),
                           ("created_at", "TIMESTAMP")],
           purpose="operations audit events"),
    _table("ops_heartbeats", [_PK, ("node", "TEXT"),
                               ("observed_at", "TIMESTAMP")],
           purpose="fleet heartbeat samples"),
    _table("ops_alerts", [_PK, ("severity", "TEXT"), ("message", "TEXT"),
                           ("created_at", "TIMESTAMP")],
           purpose="operations alerts"),
)


@dataclass(frozen=True)
class SchemaValidation:
    ok: bool
    errors: tuple[str, ...] = ()
    table_count: int = 0
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "errors", tuple(self.errors))

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": list(self.errors),
                "table_count": self.table_count,
                "fingerprint": self.fingerprint}


def validate_schema(tables: Sequence[TableDescriptor]) -> SchemaValidation:
    errors: list[str] = []
    seen: set[str] = set()
    for table in tables:
        if not isinstance(table, TableDescriptor):
            errors.append("schema entry is not a TableDescriptor")
            continue
        if table.name in seen:
            errors.append(f"duplicate table {table.name}")
        seen.add(table.name)
        try:
            _ = table.fingerprint
        except ConfigContractError as exc:
            errors.append(str(exc))
    # Order-independent: same tables in any order address the same schema.
    table_docs = sorted(
        (t.to_dict() for t in tables if isinstance(t, TableDescriptor)),
        key=lambda doc: doc["name"])
    result = content_hash(table_docs)[:16]
    return SchemaValidation(not errors, tuple(errors), len(tables), result)


@dataclass(frozen=True)
class MigrationDescriptor:
    """A data-only migration plan.  It explicitly cannot execute SQL."""

    table_names: tuple[str, ...]
    column_count: int
    executes_sql: bool = False
    schema_fingerprint: str = ""
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_names", tuple(self.table_names))
        if self.executes_sql:
            raise SchemaDescriptorError("a data-only migration cannot execute SQL")
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash({
                "table_names": self.table_names,
                "column_count": self.column_count,
                "schema_fingerprint": self.schema_fingerprint,
            })[:16])

    def to_dict(self) -> dict:
        return {"table_names": list(self.table_names),
                "column_count": self.column_count,
                "executes_sql": self.executes_sql,
                "schema_fingerprint": self.schema_fingerprint,
                "fingerprint": self.fingerprint}


def describe_migration(tables: Sequence[TableDescriptor]) -> MigrationDescriptor:
    validation = validate_schema(tables)
    if not validation.ok:
        raise SchemaDescriptorError("; ".join(validation.errors))
    return MigrationDescriptor(
        table_names=tuple(t.name for t in tables),
        column_count=sum(len(t.columns) for t in tables),
        schema_fingerprint=validation.fingerprint)


class SchemaApplySeam:
    """Replace with a real, reviewable migration runner; no SQL here."""

    def apply(self, migration: MigrationDescriptor) -> None:
        # pragma: no cover - seam
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Y3.9 -- sign out / sign out everywhere / disconnect (revocation descriptors)
# ---------------------------------------------------------------------------


class RevocationScope(str, Enum):
    SESSION = "session"            # sign out this client/session
    ALL_SESSIONS = "all_sessions"  # sign out everywhere
    ALL_CLIENTS = "all_clients"    # disconnect: purge creds + all clients


@dataclass(frozen=True)
class RevocationRequest:
    scope: RevocationScope | str
    subject_id: str
    reason: str = ""
    initiated_by: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", RevocationScope(self.scope))
        if not isinstance(self.subject_id, str) or not self.subject_id:
            raise RevocationError("revocation needs a subject_id")

    def to_dict(self) -> dict:
        return {"scope": self.scope.value, "subject_id": self.subject_id,
                "reason": self.reason, "initiated_by": self.initiated_by}


@dataclass(frozen=True)
class TokenRevocationDescriptor:
    """Semantics of a revocation.  Never carries a token or secret value."""

    scope: RevocationScope
    subject_id: str
    revocation_id: str
    revoke_all: bool
    delete_stored_credentials: bool
    sign_out_all_clients: bool
    reason_code: str = ""
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", RevocationScope(self.scope))
        if not isinstance(self.subject_id, str) or not self.subject_id:
            raise RevocationError("revocation descriptor needs a subject_id")
        expected = content_hash({
            "scope": self.scope.value, "subject_id": self.subject_id,
        })[:16]
        if self.revocation_id and self.revocation_id != expected:
            raise RevocationError("revocation_id does not commit to its scope")
        object.__setattr__(self, "revocation_id", expected)
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash(self.to_dict(
                include_fingerprint=False))[:16])
        assert_no_secrets(self)

    def to_dict(self, *, include_fingerprint: bool = True) -> dict:
        doc = {"scope": self.scope.value, "subject_id": self.subject_id,
               "revocation_id": self.revocation_id,
               "revoke_all": self.revoke_all,
               "delete_stored_credentials": self.delete_stored_credentials,
               "sign_out_all_clients": self.sign_out_all_clients,
               "reason_code": self.reason_code}
        if include_fingerprint:
            doc["fingerprint"] = self.fingerprint
        return doc

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TokenRevocationDescriptor":
        d = dict(data)
        return cls(scope=d.get("scope", RevocationScope.SESSION),
                   subject_id=str(d.get("subject_id") or ""),
                   revocation_id=str(d.get("revocation_id") or ""),
                   revoke_all=bool(d.get("revoke_all", False)),
                   delete_stored_credentials=bool(
                       d.get("delete_stored_credentials", False)),
                   sign_out_all_clients=bool(d.get("sign_out_all_clients", False)),
                   reason_code=str(d.get("reason_code") or ""),
                   fingerprint=str(d.get("fingerprint") or ""))


#: Scope -> (revoke_all, delete stored credentials, sign out all clients).
_SCOPE_EFFECTS: dict[RevocationScope, tuple[bool, bool, bool]] = {
    RevocationScope.SESSION: (False, False, False),
    RevocationScope.ALL_SESSIONS: (True, False, False),
    RevocationScope.ALL_CLIENTS: (True, True, True),
}


def build_revocation(request: RevocationRequest) -> TokenRevocationDescriptor:
    revoke_all, delete_creds, sign_out_all = _SCOPE_EFFECTS[request.scope]
    return TokenRevocationDescriptor(
        scope=request.scope, subject_id=request.subject_id,
        revocation_id="", revoke_all=revoke_all,
        delete_stored_credentials=delete_creds,
        sign_out_all_clients=sign_out_all,
        reason_code=request.reason)


def assert_no_secrets(descriptor: TokenRevocationDescriptor,
                      forbidden_values: Iterable[str] = ()) -> bool:
    """Fail if a secret field name or a known secret value reached a descriptor."""
    doc = descriptor.to_dict(include_fingerprint=False)
    if {str(k).lower() for k in doc} & _SECRET_FIELD_NAMES:
        raise RevocationError("revocation descriptor exposes a secret field")
    text = json.dumps(doc, sort_keys=True)
    for value in forbidden_values:
        if value and value in text:
            raise RevocationError("revocation descriptor carries a secret value")
    return True


@dataclass(frozen=True)
class RevocationEffect:
    scope: RevocationScope
    subject_id: str
    revoked_sessions: bool
    credentials_deleted: bool
    clients_signed_out: bool

    def to_dict(self) -> dict:
        return {"scope": self.scope.value, "subject_id": self.subject_id,
                "revoked_sessions": self.revoked_sessions,
                "credentials_deleted": self.credentials_deleted,
                "clients_signed_out": self.clients_signed_out}


class RevocationLedger:
    """Pure bookkeeping of revocation effects; stores no tokens or secrets."""

    def __init__(self) -> None:
        self._revoked: set[str] = set()
        self._credentials_deleted: set[str] = set()
        self._all_clients_signed_out = False

    def apply(self, descriptor: TokenRevocationDescriptor) -> RevocationEffect:
        if not isinstance(descriptor, TokenRevocationDescriptor):
            raise RevocationError("expected a TokenRevocationDescriptor")
        if descriptor.revoke_all:
            self._revoked.add(descriptor.subject_id)
        else:
            self._revoked.add(descriptor.subject_id)
        if descriptor.delete_stored_credentials:
            self._credentials_deleted.add(descriptor.subject_id)
        if descriptor.sign_out_all_clients:
            self._all_clients_signed_out = True
        return RevocationEffect(
            scope=descriptor.scope, subject_id=descriptor.subject_id,
            revoked_sessions=descriptor.revoke_all,
            credentials_deleted=descriptor.delete_stored_credentials,
            clients_signed_out=descriptor.sign_out_all_clients)

    def is_revoked(self, subject_id: str) -> bool:
        return subject_id in self._revoked or self._all_clients_signed_out

    def has_deleted_credentials(self, subject_id: str) -> bool:
        return subject_id in self._credentials_deleted

    @property
    def all_clients_signed_out(self) -> bool:
        return self._all_clients_signed_out


# ---------------------------------------------------------------------------
# Y3.10 -- local-only sign-in (no account / cloud; explicit offline guarantee)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OfflineGuarantee:
    ok: bool
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))

    def to_dict(self) -> dict:
        return {"ok": self.ok, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class LocalSignInDescriptor:
    """Describes a purely local sign-in.  No account, cloud or egress."""

    scheme: str = "local_only"
    loopback_only: bool = True
    account_required: bool = False
    cloud_required: bool = False
    offline_capable: bool = True
    network_egress: bool = False
    env_flag: str = "KEEL_LOCAL_SIGNIN"
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.scheme != "local_only":
            raise OfflineGuaranteeError("only the local_only scheme is valid")
        if not self.env_flag or not isinstance(self.env_flag, str):
            raise OfflineGuaranteeError("local sign-in needs an env flag name")
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash(self.to_dict(
                include_fingerprint=False))[:16])

    def to_dict(self, *, include_fingerprint: bool = True) -> dict:
        doc = {"scheme": self.scheme, "loopback_only": self.loopback_only,
               "account_required": self.account_required,
               "cloud_required": self.cloud_required,
               "offline_capable": self.offline_capable,
               "network_egress": self.network_egress,
               "env_flag": self.env_flag}
        if include_fingerprint:
            doc["fingerprint"] = self.fingerprint
        return doc

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LocalSignInDescriptor":
        d = dict(data)
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})


def validate_offline_guarantee(descriptor: LocalSignInDescriptor
                               ) -> OfflineGuarantee:
    reasons: list[str] = []
    if not descriptor.loopback_only:
        reasons.append("local sign-in must be gated to loopback")
    if descriptor.account_required:
        reasons.append("local sign-in requires no account")
    if descriptor.cloud_required:
        reasons.append("local sign-in requires no cloud service")
    if descriptor.network_egress:
        reasons.append("local sign-in must not require network egress")
    if not descriptor.offline_capable:
        reasons.append("local sign-in must work fully offline")
    return OfflineGuarantee(not reasons, tuple(reasons))


def assert_offline(descriptor: LocalSignInDescriptor) -> bool:
    result = validate_offline_guarantee(descriptor)
    if not result.ok:
        raise OfflineGuaranteeError("; ".join(result.reasons))
    return True


@dataclass(frozen=True)
class SignInPolicy:
    """Runtime gating: dev bypass is only legal off-loopback is never legal."""

    environment: str = "development"   # development | production
    dev_bypass_enabled: bool = False
    loopback_bind: bool = True

    def __post_init__(self) -> None:
        if self.environment not in ("development", "production"):
            raise OfflineGuaranteeError("environment must be development|production")

    def to_dict(self) -> dict:
        return {"environment": self.environment,
                "dev_bypass_enabled": self.dev_bypass_enabled,
                "loopback_bind": self.loopback_bind}


@dataclass(frozen=True)
class SignInValidation:
    allowed: bool
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "reasons": list(self.reasons)}


def validate_signin_policy(policy: SignInPolicy,
                           descriptor: LocalSignInDescriptor | None = None
                           ) -> SignInValidation:
    reasons: list[str] = []
    desc = descriptor or LocalSignInDescriptor()
    offline = validate_offline_guarantee(desc)
    reasons.extend(offline.reasons)
    if not policy.loopback_bind:
        reasons.append("local sign-in requires a loopback bind")
    if policy.dev_bypass_enabled and policy.environment == "production":
        reasons.append("production refuses to start with the dev bypass set")
    if policy.dev_bypass_enabled and not desc.loopback_only:
        reasons.append("the dev bypass is only valid with loopback-only sign-in")
    return SignInValidation(not reasons, tuple(reasons))


# ---------------------------------------------------------------------------
# Y3.11 -- deterministic mock agent, clearly labelled, never a real provider
# ---------------------------------------------------------------------------


MOCK_LABEL = "MOCK AGENT — deterministic, not a real provider"


@dataclass(frozen=True)
class MockAgentDescriptor:
    id: str
    label: str = MOCK_LABEL
    is_mock: bool = True
    real_provider: bool = False
    deterministic: bool = True
    provider_kind: str = "mock"
    scripted_responses: tuple[str, ...] = ()
    fingerprint: str = ""

    def __post_init__(self) -> None:
        self._assert_labelled()
        object.__setattr__(self, "scripted_responses",
                           tuple(self.scripted_responses))
        if not isinstance(self.id, str) or not self.id:
            raise MockLabelingError("mock agent needs an id")
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash({
                "id": self.id, "label": self.label,
                "scripted_responses": self.scripted_responses,
            })[:16])

    def _assert_labelled(self) -> None:
        if "mock" not in str(self.label).lower():
            raise MockLabelingError("a mock agent label must contain 'mock'")
        if self.real_provider:
            raise MockLabelingError("a mock agent may never be a real provider")
        if not self.is_mock or not self.deterministic:
            raise MockLabelingError("a mock agent must be mock and deterministic")
        if str(self.provider_kind).lower() != "mock":
            raise MockLabelingError("mock agent provider_kind must be 'mock'")

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "is_mock": self.is_mock,
                "real_provider": self.real_provider,
                "deterministic": self.deterministic,
                "provider_kind": self.provider_kind,
                "scripted_responses": list(self.scripted_responses),
                "fingerprint": self.fingerprint}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MockAgentDescriptor":
        d = dict(data)
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})


def assert_never_real_provider(descriptor: MockAgentDescriptor) -> bool:
    if not isinstance(descriptor, MockAgentDescriptor):
        raise MockLabelingError("expected a MockAgentDescriptor")
    descriptor._assert_labelled()
    return True


@dataclass(frozen=True)
class MockReply:
    prompt: str
    text: str
    label: str
    is_mock: bool = True
    deterministic: bool = True

    def to_dict(self) -> dict:
        return {"prompt": self.prompt, "text": self.text, "label": self.label,
                "is_mock": self.is_mock, "deterministic": self.deterministic}


class MockAgent:
    """Plays scripted runs when no real agent is configured.

    Every reply is derived only from the prompt and the descriptor, so repeated
    calls with the same prompt are byte-identical.  Each reply carries the mock
    disclosure and can never be confused with a real provider response.
    """

    def __init__(self, descriptor: MockAgentDescriptor,
                 script: Sequence[str] | None = None) -> None:
        assert_never_real_provider(descriptor)
        self.descriptor = descriptor
        self._script = tuple(script if script is not None
                             else descriptor.scripted_responses)
        if any(not isinstance(s, str) for s in self._script):
            raise MockLabelingError("scripted responses must be strings")

    def respond(self, prompt: str) -> MockReply:
        if not isinstance(prompt, str):
            raise MockLabelingError("prompt must be a string")
        if self._script:
            index = int(content_hash(prompt)[:8], 16) % len(self._script)
            text = self._script[index]
        else:
            text = f"[mock response to] {prompt}"
        return MockReply(prompt=prompt, text=text,
                         label=self.descriptor.label)

    def disclose(self) -> str:
        return self.descriptor.label

    def to_descriptor(self) -> MockAgentDescriptor:
        return replace(self.descriptor, scripted_responses=self._script)


# ---------------------------------------------------------------------------
# Y3.13 -- setup: generate-only, never overwrite, atomic seam, idempotent
# ---------------------------------------------------------------------------


_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class GeneratedFile:
    """A file the setup script is allowed to *create*, never overwrite."""

    path: str
    content: str

    def __post_init__(self) -> None:
        path = str(self.path)
        if not path or _DRIVE_RE.match(path) or path.startswith("/") \
                or path.startswith("\\") or "\\" in path:
            raise SetupContractError(f"generated path must be relative: {path!r}")
        parts = PurePosixPath(path).parts
        if any(p in ("", ".", "..") for p in parts):
            raise SetupContractError(f"unsafe generated path: {path!r}")
        if not isinstance(self.content, str):
            raise SetupContractError("generated content must be a string")
        object.__setattr__(self, "path", path)

    @property
    def fingerprint(self) -> str:
        return content_hash({"path": self.path, "content": self.content})[:16]

    def to_dict(self) -> dict:
        return {"path": self.path, "content": self.content,
                "fingerprint": self.fingerprint}


@dataclass(frozen=True)
class GenerationPlan:
    create: tuple[GeneratedFile, ...]
    skip_existing: tuple[str, ...]
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "create", tuple(self.create))
        object.__setattr__(self, "skip_existing", tuple(self.skip_existing))
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash({
                "create": [g.fingerprint for g in self.create],
                "skip_existing": self.skip_existing,
            })[:16])

    def to_dict(self) -> dict:
        return {"create": [g.to_dict() for g in self.create],
                "skip_existing": list(self.skip_existing),
                "fingerprint": self.fingerprint}


def plan_generation(desired: Sequence[GeneratedFile],
                    existing: Collection[str]) -> GenerationPlan:
    """Partition desired files into create/skip, deterministically ordered."""
    present = set(existing)
    create: list[GeneratedFile] = []
    skip: list[str] = []
    for item in desired:
        if not isinstance(item, GeneratedFile):
            raise SetupContractError("desired entries must be GeneratedFile")
        if item.path in present:
            skip.append(item.path)
        else:
            create.append(item)
    create.sort(key=lambda g: g.path)
    return GenerationPlan(tuple(create), tuple(sorted(skip)))


class WriteSeam:
    """Atomic-write seam.  A lead replaces this with tmp + fsync + os.replace."""

    def exists(self, path: str) -> bool:  # pragma: no cover - seam
        raise NotImplementedError

    def atomic_write(self, path: str, content: str) -> None:
        # pragma: no cover - seam
        raise NotImplementedError


class InMemoryWriteSeam(WriteSeam):
    """In-process seam used by the contract tests.  No filesystem I/O."""

    def __init__(self, initial: Mapping[str, str] | None = None) -> None:
        self._files: dict[str, str] = dict(initial or {})
        self._writes: list[str] = []

    def exists(self, path: str) -> bool:
        return path in self._files

    def atomic_write(self, path: str, content: str) -> None:
        self._files[path] = content
        self._writes.append(path)

    @property
    def writes(self) -> tuple[str, ...]:
        return tuple(self._writes)

    def snapshot(self) -> dict[str, str]:
        return dict(self._files)


@dataclass(frozen=True)
class ApplyReport:
    created: tuple[str, ...]
    skipped: tuple[str, ...]
    manual_steps: tuple[str, ...]
    required_values: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "created", tuple(self.created))
        object.__setattr__(self, "skipped", tuple(self.skipped))
        object.__setattr__(self, "manual_steps", tuple(self.manual_steps))
        object.__setattr__(self, "required_values", tuple(self.required_values))

    def to_dict(self) -> dict:
        return {"created": list(self.created), "skipped": list(self.skipped),
                "manual_steps": list(self.manual_steps),
                "required_values": list(self.required_values)}


def setup_manual_steps() -> tuple[str, ...]:
    """The one manual step the operator must perform, plus its context."""
    return (
        "Copy the printed required values into your local .env file.",
        "Restart the Keel server once so the new values take effect.",
    )


def apply_plan(plan: GenerationPlan, seam: WriteSeam, *,
               on_existing: str = "skip") -> ApplyReport:
    """Create only missing files through the seam; never overwrite.

    ``on_existing="skip"`` (the default) is generate-only and idempotent.
    ``on_existing="error"`` turns a pre-existing target into a hard failure so
    callers can prove the no-overwrite guarantee explicitly.
    """
    if on_existing not in ("skip", "error"):
        raise SetupContractError("on_existing must be 'skip' or 'error'")
    created: list[str] = []
    skipped = list(plan.skip_existing)
    for item in plan.create:
        if seam.exists(item.path):
            if on_existing == "error":
                raise OverwriteError(f"refusing to overwrite {item.path!r}")
            skipped.append(item.path)
            continue
        seam.atomic_write(item.path, item.content)
        created.append(item.path)
    return ApplyReport(
        created=tuple(sorted(created)), skipped=tuple(sorted(set(skipped))),
        manual_steps=setup_manual_steps(),
        required_values=tuple(sorted(g.path for g in plan.create)))


def setup_once(desired: Sequence[GeneratedFile], seam: WriteSeam, *,
               on_existing: str = "skip") -> ApplyReport:
    """Plan from the seam's current state, then apply.  Safe to call twice."""
    existing = {g.path for g in desired if isinstance(g, GeneratedFile)
                and seam.exists(g.path)}
    plan = plan_generation(desired, existing)
    return apply_plan(plan, seam, on_existing=on_existing)
