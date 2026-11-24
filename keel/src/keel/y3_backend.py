"""keel.y3_backend -- backend behavior for the remaining Y3.* registry IDs.

This is an *additive* module.  It does not edit ``keel.config_contracts``,
``keel.settings``, the web app, the CLI, the fleet layer or any existing test.
The seven Y3 P0 rows (Y3.2, Y3.4, Y3.6, Y3.9, Y3.10, Y3.11, Y3.13) already
live in ``keel.config_contracts``; this module covers the fourteen
``not_started`` P1 rows from ``PLAN-INDEX.json`` and is verified alongside
that P0 module in ``keel/tests/test_y3_backend.py``.

The fourteen features are:

  Y3.1   "offer only what works" ............... availability model, no dead options
  Y3.3   versioned provisioning ................ per-step versions, resumable plan
  Y3.5   per-user concurrency + queue .......... RAM/VRAM sizing, FIFO auto-start
  Y3.7   scheduler tick duties ................. one tick(), 7 jobs, idempotency keys
  Y3.8   device-approval pairing ............... short code, 30-min expiry, poll/cancel
  Y3.12  invite gate ........................... serve-mode, first-admin ownership
  Y3.14  first-run offers existing resources ... reuse first, cost before create
  Y3.15  settings structure .................... validated settings tree
  Y3.16  public API / webhooks / operator ...... version-prefixed route descriptors
  Y3.17  project update proposals .............. approval-gated diff proposals
  Y3.18  compute-side files, local cache ....... KEEL_DATA_DIR + LRU eviction
  Y3.19  brand strings in one place ............ single brand config / fork rename
  Y3.20  docs set + security-model limits ...... required docs, explicit can't-do list
  Y3.21  administrator warning ................. first-run warning + preset explanation

Only the Python standard library is used.  There is no network, socket,
subprocess, SQL execution, credential value or import-time filesystem I/O.
Runtime I/O is confined to injectable seams (default methods raise
``NotImplementedError``) and to an injectable environment mapping
(``resolve_data_dir``).  All identifiers and codes are deterministic SHA-256
prefixes -- no uuid, no RNG -- and every frozen dataclass is safe to hash
where its fields allow it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Mapping


# ---------------------------------------------------------------------------
# shared helpers: canonical bytes, content hashes, typed errors
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 encoding used by every hash in this module."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class Y3BackendError(ValueError):
    """Base class for all typed Y3 backend failures."""


class AvailabilityError(Y3BackendError):
    """An unavailable option was exposed as a dead button or left unexplained."""


class ProvisioningError(Y3BackendError):
    """A setup step, version or provisioning plan was invalid."""


class ConcurrencyError(Y3BackendError):
    """A queue operation or hardware profile was invalid."""


class SchedulerError(Y3BackendError):
    """A tick overlapped another tick or was malformed."""


class PairingError(Y3BackendError):
    """A pairing code was unknown or used in the wrong state."""


class InviteError(Y3BackendError):
    """A client tried to bypass the invite gate."""


class FirstRunError(Y3BackendError):
    """A first-run offer hid an existing resource or omitted a cost."""


class SettingsTreeError(Y3BackendError):
    """The settings tree had duplicate ids or an unknown key."""


class RouteError(Y3BackendError):
    """A route was missing its API version prefix or was malformed."""


class ProposalError(Y3BackendError):
    """A project proposal was malformed or used before approval."""


class CacheError(Y3BackendError):
    """A cache entry could not be admitted or referred to a local file."""


class BrandError(Y3BackendError):
    """A brand string was unknown or brand sources were duplicated."""


class DocsError(Y3BackendError):
    """The docs set was incomplete or the security model was vague."""


class WarningError(Y3BackendError):
    """A mandatory first-run warning was missing or unacknowledged."""


# ---------------------------------------------------------------------------
# Y3.1 -- "offer only what works": hide or explain, never a dead button
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Requirement:
    """One precondition for an option.  ``missing_detail`` names it exactly."""

    name: str
    satisfied: bool
    missing_detail: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise AvailabilityError("requirement needs a name")
        if not self.satisfied and not self.missing_detail:
            raise AvailabilityError(
                f"unsatisfied requirement {self.name!r} must name the missing "
                "requirement exactly")


class OptionState(str, Enum):
    AVAILABLE = "available"
    EXPLAIN = "explain"       # shown, with the exact missing requirement
    HIDDEN = "hidden"         # not offered at all


@dataclass(frozen=True)
class FeatureOption:
    key: str
    label: str
    requirements: tuple[Requirement, ...] = ()
    explain_when_unavailable: bool = True

    def __post_init__(self) -> None:
        if not self.key:
            raise AvailabilityError("option needs a key")
        object.__setattr__(self, "requirements", tuple(self.requirements))


@dataclass(frozen=True)
class Availability:
    option_key: str
    state: OptionState
    missing: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing", tuple(self.missing))

    def to_dict(self) -> dict:
        return {"option": self.option_key, "state": self.state.value,
                "missing": list(self.missing)}


def evaluate_availability(option: FeatureOption) -> Availability:
    """Resolve an option from its requirements, never emitting a dead button."""
    missing = tuple(r.missing_detail for r in option.requirements
                    if not r.satisfied)
    if not missing:
        return Availability(option.key, OptionState.AVAILABLE)
    state = (OptionState.EXPLAIN if option.explain_when_unavailable
             else OptionState.HIDDEN)
    return Availability(option.key, state, missing)


def visible_options(options: Iterable[FeatureOption]) -> tuple[Availability, ...]:
    """Only options that work (or that explain why not) may be shown."""
    return tuple(a for a in (evaluate_availability(o) for o in options)
                 if a.state is not OptionState.HIDDEN)


def assert_no_dead_options(availabilities: Iterable[Availability]) -> None:
    """Reject a dead button: available with a reason, or a reasonless explain."""
    for a in availabilities:
        if a.state is OptionState.AVAILABLE and a.missing:
            raise AvailabilityError(f"{a.option_key!r} is offered but has missing requirements")
        if a.state is OptionState.EXPLAIN and not a.missing:
            raise AvailabilityError(f"{a.option_key!r} is explained without a reason")
        if a.state is OptionState.HIDDEN and a.missing:
            # Hiding is fine, but the option must not also be presented.
            raise AvailabilityError(f"{a.option_key!r} is hidden but still carries a reason")


# ---------------------------------------------------------------------------
# Y3.3 -- versioned, idempotent, resumable provisioning steps
# ---------------------------------------------------------------------------

_STEP_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class SetupStep:
    """A setup step with its own version; bumping it re-runs only that step."""

    key: str
    version: int
    action: str

    def __post_init__(self) -> None:
        if not _STEP_KEY_RE.match(self.key):
            raise ProvisioningError(f"invalid step key: {self.key!r}")
        if self.version < 1:
            raise ProvisioningError("step version must be >= 1")
        if not self.action:
            raise ProvisioningError("step needs an action description")

    @property
    def identity(self) -> str:
        return f"{self.key}@{self.version}"


class ProvisioningRegistry:
    """Ordered registry of setup steps; lookup is by stable key."""

    def __init__(self, steps: Iterable[SetupStep]) -> None:
        indexed: dict[str, SetupStep] = {}
        for step in steps:
            if step.key in indexed:
                raise ProvisioningError(f"duplicate step key: {step.key!r}")
            indexed[step.key] = step
        self._steps: dict[str, SetupStep] = indexed

    @property
    def steps(self) -> tuple[SetupStep, ...]:
        return tuple(self._steps[k] for k in sorted(self._steps))

    def steps_due(self, completed: Mapping[str, int]) -> tuple[SetupStep, ...]:
        """Never-run or version-bumped steps only; deterministic order."""
        return tuple(s for s in self.steps
                     if int(completed.get(s.key, 0)) < s.version)


@dataclass(frozen=True)
class StepResult:
    key: str
    version: int
    ok: bool
    detail: str = ""

    @property
    def identity(self) -> str:
        return f"{self.key}@{self.version}"


class StepRunnerSeam:
    """Real side effects stay behind this seam (default raises)."""

    def run(self, step: SetupStep) -> StepResult:  # pragma: no cover - seam
        raise NotImplementedError


class InMemoryStepRunner(StepRunnerSeam):
    """Deterministic runner used by tests: fails exactly the named keys."""

    def __init__(self, fail_keys: Iterable[str] = ()) -> None:
        self._fail_keys = frozenset(fail_keys)
        self._attempts: list[str] = []

    def run(self, step: SetupStep) -> StepResult:
        self._attempts.append(step.identity)
        if step.key in self._fail_keys:
            return StepResult(step.key, step.version, False, "injected failure")
        return StepResult(step.key, step.version, True, "ok")

    @property
    def attempts(self) -> tuple[str, ...]:
        return tuple(self._attempts)


@dataclass(frozen=True)
class ProvisioningReport:
    planned: tuple[str, ...]
    completed: tuple[str, ...]
    failed: tuple[str, ...]
    remaining: tuple[str, ...]
    new_completed: Mapping[str, int]

    def __post_init__(self) -> None:
        for name in ("planned", "completed", "failed", "remaining"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "new_completed", dict(self.new_completed))

    def to_dict(self) -> dict:
        return {"planned": list(self.planned), "completed": list(self.completed),
                "failed": list(self.failed), "remaining": list(self.remaining),
                "new_completed": dict(self.new_completed)}


def run_provisioning(registry: ProvisioningRegistry,
                     completed: Mapping[str, int],
                     runner: StepRunnerSeam,
                     *, now: float | None = None) -> ProvisioningReport:
    """Run due steps once; failed steps stay due for the next launch/resume.

    ``now`` is accepted for seam symmetry but is deliberately not used in any
    identity: provisioning is reproducible and driven only by step versions.
    """
    del now
    due = registry.steps_due(completed)
    planned = tuple(s.identity for s in due)
    done: list[StepResult] = []
    failed: list[StepResult] = []
    new_completed = dict(completed)
    for step in due:
        result = runner.run(step)
        if result.identity != step.identity or result.key != step.key:
            raise ProvisioningError("runner returned a result for a different step")
        (done if result.ok else failed).append(result)
        if result.ok:
            new_completed[step.key] = step.version
    remaining = tuple(s.identity for s in registry.steps_due(new_completed))
    return ProvisioningReport(planned, tuple(r.identity for r in done),
                              tuple(r.identity for r in failed), remaining,
                              new_completed)


# ---------------------------------------------------------------------------
# Y3.5 -- per-user concurrency limit sized to the machine; extra tasks queue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HardwareProfile:
    ram_gb: float
    vram_gb: float = 0.0
    reserved_gb: float = 2.0

    def __post_init__(self) -> None:
        if self.ram_gb < 0 or self.vram_gb < 0 or self.reserved_gb < 0:
            raise ConcurrencyError("hardware capacities must be non-negative")


# One concurrent task reserves this much memory (system RAM or VRAM).
_SLOT_GB = 6.0


def concurrency_limit(profile: HardwareProfile) -> int:
    """Deterministic slot count from RAM/VRAM, with a floor of one slot."""
    ram_slots = max(0, int((profile.ram_gb - profile.reserved_gb) // _SLOT_GB))
    vram_slots = int(profile.vram_gb // _SLOT_GB)
    return max(1, ram_slots + vram_slots)


@dataclass(frozen=True)
class Task:
    key: str
    label: str = ""

    def __post_init__(self) -> None:
        if not self.key:
            raise ConcurrencyError("task needs a key")


@dataclass(frozen=True)
class QueueState:
    limit: int
    running: tuple[str, ...]
    pending: tuple[str, ...]


class PerUserQueue:
    """FIFO queue for one user: admits up to ``limit`` tasks, auto-starts the rest."""

    def __init__(self, limit: int) -> None:
        if int(limit) < 1:
            raise ConcurrencyError("concurrency limit must be >= 1")
        self._limit = int(limit)
        self._running: list[str] = []
        self._pending: list[Task] = []

    @property
    def limit(self) -> int:
        return self._limit

    def submit(self, task: Task) -> None:
        if any(t.key == task.key for t in self._pending) or task.key in self._running:
            raise ConcurrencyError(f"duplicate task key: {task.key!r}")
        self._pending.append(task)
        self._pump()

    def finish(self, key: str) -> None:
        if key not in self._running:
            raise ConcurrencyError(f"task is not running: {key!r}")
        self._running.remove(key)
        self._pump()

    def cancel(self, key: str) -> None:
        if any(t.key == key for t in self._pending):
            self._pending[:] = [t for t in self._pending if t.key != key]
        elif key in self._running:
            self._running.remove(key)
            self._pump()
        else:
            raise ConcurrencyError(f"unknown task: {key!r}")

    def _pump(self) -> None:
        while len(self._running) < self._limit and self._pending:
            self._running.append(self._pending.pop(0).key)

    def state(self) -> QueueState:
        return QueueState(self._limit, tuple(self._running),
                          tuple(t.key for t in self._pending))


class ConcurrencyManager:
    """Holds one independently-sized queue per user."""

    def __init__(self, hardware: HardwareProfile,
                 overrides: Mapping[str, int] | None = None) -> None:
        self._hardware = hardware
        self._overrides = dict(overrides or {})
        self._queues: dict[str, PerUserQueue] = {}

    def queue_for(self, user: str) -> PerUserQueue:
        if not user:
            raise ConcurrencyError("user id is required")
        if user not in self._queues:
            limit = self._overrides.get(user, concurrency_limit(self._hardware))
            self._queues[user] = PerUserQueue(limit)
        return self._queues[user]

    def submit(self, user: str, task: Task) -> None:
        self.queue_for(user).submit(task)

    def finish(self, user: str, key: str) -> None:
        self.queue_for(user).finish(key)

    def state(self, user: str) -> QueueState:
        return self.queue_for(user).state()


# ---------------------------------------------------------------------------
# Y3.7 -- one tick() with seven duties, idempotency keys and overlap safety
# ---------------------------------------------------------------------------


class TickJob(str, Enum):
    FIRE_AUTOMATIONS = "fire_automations"
    POLL_TRIGGERS = "poll_triggers"
    DELIVER_WEBHOOKS = "deliver_webhooks"
    BACKFILL_COSTS = "backfill_task_costs"
    SWEEP_FOLDERS = "sweep_idle_task_folders"
    HEARTBEAT = "record_heartbeat"
    CHECK_ALERTS = "check_alerts"


TICK_JOBS: tuple[TickJob, ...] = tuple(TickJob)


@dataclass(frozen=True)
class DueWork:
    """Everything a tick needs to know; no file, DB or network access."""

    automations: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()
    webhooks: tuple[str, ...] = ()
    task_costs: tuple[str, ...] = ()
    idle_folders: tuple[str, ...] = ()
    alerts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("automations", "triggers", "webhooks", "task_costs",
                     "idle_folders", "alerts"):
            object.__setattr__(self, name, tuple(getattr(self, name)))


@dataclass(frozen=True)
class TickOutcome:
    job: TickJob
    idempotency_key: str
    processed: tuple[str, ...]
    deduplicated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "processed", tuple(self.processed))

    def to_dict(self) -> dict:
        return {"job": self.job.value, "idempotency_key": self.idempotency_key,
                "processed": list(self.processed),
                "deduplicated": self.deduplicated}


@dataclass(frozen=True)
class TickReport:
    outcomes: tuple[TickOutcome, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcomes", tuple(self.outcomes))

    def for_job(self, job: TickJob) -> TickOutcome:
        for outcome in self.outcomes:
            if outcome.job is job:
                return outcome
        raise SchedulerError(f"tick did not run job {job.value!r}")

    def to_dict(self) -> dict:
        return {"outcomes": [o.to_dict() for o in self.outcomes]}


class IdempotencyLedger:
    """In-memory key ledger; real persistence belongs behind a storage seam."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def claim(self, key: str) -> bool:
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def snapshot(self) -> tuple[str, ...]:
        return tuple(sorted(self._seen))


class TickGuard:
    """Makes ticks safe to overlap: a second concurrent tick is refused."""

    def __init__(self) -> None:
        self._active = False

    def acquire(self) -> None:
        if self._active:
            raise SchedulerError("a scheduler tick is already in progress")
        self._active = True

    def release(self) -> None:
        self._active = False


def _job_items(job: TickJob, work: DueWork) -> tuple[str, ...]:
    if job is TickJob.FIRE_AUTOMATIONS:
        return work.automations
    if job is TickJob.POLL_TRIGGERS:
        return work.triggers
    if job is TickJob.DELIVER_WEBHOOKS:
        return work.webhooks
    if job is TickJob.BACKFILL_COSTS:
        return work.task_costs
    if job is TickJob.SWEEP_FOLDERS:
        return work.idle_folders
    if job is TickJob.HEARTBEAT:
        return ("heartbeat",)
    return work.alerts


def tick(work: DueWork, *, now: str,
         ledger: IdempotencyLedger | None = None,
         guard: TickGuard | None = None) -> TickReport:
    """Run all seven tick duties once for ``now``; repeated keys are no-ops."""
    if not now:
        raise SchedulerError("tick needs a 'now' stamp")
    ledger = ledger or IdempotencyLedger()
    outcomes: list[TickOutcome] = []

    def _run() -> None:
        for job in TICK_JOBS:
            items = _job_items(job, work)
            key = content_hash({"job": job.value, "now": now,
                                "items": sorted(items)})[:16]
            if ledger.claim(key):
                outcomes.append(TickOutcome(job, key, items))
            else:
                outcomes.append(TickOutcome(job, key, (), True))

    if guard is None:
        _run()
    else:
        guard.acquire()
        try:
            _run()
        finally:
            guard.release()
    return TickReport(tuple(outcomes))


# ---------------------------------------------------------------------------
# Y3.8 -- device-approval pairing flow (short code, 30-min expiry, poll/cancel)
# ---------------------------------------------------------------------------


class PairingState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    DENIED = "denied"


PAIRING_TTL_SECONDS = 30 * 60


@dataclass(frozen=True)
class PairingSession:
    code: str
    created_at: float
    state: PairingState
    approved_by: str = ""
    attempts: int = 1

    def to_dict(self) -> dict:
        return {"code": self.code, "created_at": self.created_at,
                "state": self.state.value, "approved_by": self.approved_by,
                "attempts": self.attempts}


class PairingBroker:
    """In-memory broker; a lead supplies the real clocks/storage at the seam."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock if clock is not None else time.time
        self._sessions: dict[str, PairingSession] = {}

    def _now(self) -> float:
        return float(self._clock())

    def create(self, nonce: str) -> PairingSession:
        if not nonce:
            raise PairingError("pairing needs a nonce")
        created = self._now()
        code = content_hash({"nonce": nonce, "created": created})[:6].upper()
        session = PairingSession(code, created, PairingState.PENDING)
        self._sessions[code] = session
        return session

    def _resolve(self, code: str) -> PairingSession:
        session = self._sessions.get(code)
        if session is None:
            raise PairingError(f"unknown pairing code: {code!r}")
        if (session.state is PairingState.PENDING
                and self._now() - session.created_at > PAIRING_TTL_SECONDS):
            session = PairingSession(session.code, session.created_at,
                                     PairingState.EXPIRED, attempts=session.attempts)
            self._sessions[code] = session
        return session

    def poll(self, code: str) -> PairingSession:
        """The app polls; this never advances the state beyond expiry."""
        return self._resolve(code)

    def approve(self, code: str, approver: str) -> PairingSession:
        if not approver:
            raise PairingError("approver is required")
        session = self._resolve(code)
        if session.state is not PairingState.PENDING:
            raise PairingError(f"cannot approve a {session.state.value} pairing")
        approved = PairingSession(session.code, session.created_at,
                                  PairingState.APPROVED, approver,
                                  session.attempts)
        self._sessions[code] = approved
        return approved

    def deny(self, code: str) -> PairingSession:
        session = self._resolve(code)
        if session.state is not PairingState.PENDING:
            raise PairingError(f"cannot deny a {session.state.value} pairing")
        denied = PairingSession(session.code, session.created_at,
                                PairingState.DENIED, attempts=session.attempts)
        self._sessions[code] = denied
        return denied

    def cancel(self, code: str) -> PairingSession:
        session = self._resolve(code)
        if session.state is not PairingState.PENDING:
            raise PairingError(f"cannot cancel a {session.state.value} pairing")
        cancelled = PairingSession(session.code, session.created_at,
                                   PairingState.CANCELLED, attempts=session.attempts)
        self._sessions[code] = cancelled
        return cancelled

    def retry(self, code: str, nonce: str) -> PairingSession:
        """Retry from a terminal state; issues a fresh code, keeps history."""
        session = self._resolve(code)
        if session.state not in (PairingState.EXPIRED, PairingState.CANCELLED,
                                 PairingState.DENIED):
            raise PairingError(f"cannot retry a {session.state.value} pairing")
        fresh = self.create(nonce)
        return PairingSession(fresh.code, fresh.created_at, PairingState.PENDING,
                              attempts=session.attempts + 1)


# ---------------------------------------------------------------------------
# Y3.12 -- invite gate: serve-mode, first-admin owns the paired-client list
# ---------------------------------------------------------------------------


class ServeMode(str, Enum):
    SINGLE = "single"
    SERVE = "serve"          # keel serve, multi-client


@dataclass(frozen=True)
class PairedClient:
    id: str
    label: str = ""
    admin: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            raise InviteError("client needs an id")


class InviteGate:
    """In single-client mode the gate is off; in serve mode the first client owns it."""

    def __init__(self, mode: ServeMode | str = ServeMode.SINGLE) -> None:
        self._mode = ServeMode(mode)
        self._owner: str | None = None
        self._clients: dict[str, PairedClient] = {}

    @property
    def mode(self) -> ServeMode:
        return self._mode

    @property
    def owner(self) -> str | None:
        return self._owner

    def pair(self, client_id: str, label: str = "",
             *, requested_by: str = "") -> PairedClient:
        if self._mode is ServeMode.SINGLE:
            client = PairedClient(client_id, label)
            self._clients[client_id] = client
            return client
        if not self._clients:
            self._owner = client_id
            client = PairedClient(client_id, label, admin=True)
        else:
            if requested_by != self._owner:
                raise InviteError("only the first admin client may pair clients")
            client = PairedClient(client_id, label)
        self._clients[client_id] = client
        return client

    def revoke(self, client_id: str, *, requested_by: str) -> None:
        if self._mode is ServeMode.SERVE and requested_by != self._owner:
            raise InviteError("only the first admin client may revoke clients")
        if client_id not in self._clients:
            raise InviteError(f"unknown client: {client_id!r}")
        if client_id == self._owner:
            raise InviteError("the owner cannot revoke itself")
        del self._clients[client_id]

    def is_allowed(self, client_id: str) -> bool:
        return client_id in self._clients

    def clients(self) -> tuple[PairedClient, ...]:
        return tuple(self._clients[k] for k in sorted(self._clients))


# ---------------------------------------------------------------------------
# Y3.14 -- first run offers existing resources first, with costs before create
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelResource:
    name: str
    source: str                 # "ollama" | "llamacpp"
    size_mb: int = 0
    ram_mb: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            raise FirstRunError("resource needs a name")


class ModelProbeSeam:
    """Detection of existing Ollama / llama.cpp models (default raises)."""

    def detect(self) -> tuple[ModelResource, ...]:  # pragma: no cover - seam
        raise NotImplementedError


class StaticModelProbe(ModelProbeSeam):
    def __init__(self, found: Iterable[ModelResource]) -> None:
        self._found = tuple(found)

    def detect(self) -> tuple[ModelResource, ...]:
        return self._found


@dataclass(frozen=True)
class CandidateModel:
    name: str
    source: str
    params_b: float
    bits_per_weight: float

    def __post_init__(self) -> None:
        if self.params_b <= 0 or self.bits_per_weight <= 0:
            raise FirstRunError("model size / quantization must be positive")


@dataclass(frozen=True)
class ResourceOffer:
    action: str                 # "reuse" | "create"
    model: str
    source: str
    disk_cost_mb: int
    ram_cost_mb: int

    def __post_init__(self) -> None:
        if self.action not in ("reuse", "create"):
            raise FirstRunError(f"invalid offer action: {self.action!r}")

    def to_dict(self) -> dict:
        return {"action": self.action, "model": self.model,
                "source": self.source, "disk_cost_mb": self.disk_cost_mb,
                "ram_cost_mb": self.ram_cost_mb}


def estimate_cost(params_b: float, bits_per_weight: float) -> tuple[int, int]:
    """Deterministic disk/RAM estimate in MB before a download is pulled."""
    base_mb = params_b * 1_000_000_000 * bits_per_weight / 8 / 1_000_000
    return math.ceil(base_mb * 1.3), math.ceil(base_mb * 1.2)


def plan_first_run(candidates: Iterable[CandidateModel],
                   probe: ModelProbeSeam) -> tuple[ResourceOffer, ...]:
    """Detect existing models first; creation options always carry a cost."""
    found = tuple(probe.detect())
    offers = [ResourceOffer("reuse", r.name, r.source, 0, 0)
              for r in sorted(found, key=lambda r: r.name)]
    existing = {r.name for r in found}
    for candidate in candidates:
        if candidate.name in existing:
            continue
        disk, ram = estimate_cost(candidate.params_b, candidate.bits_per_weight)
        offers.append(ResourceOffer("create", candidate.name,
                                    candidate.source, disk, ram))
    return tuple(offers)


def assert_reuse_first(offers: Iterable[ResourceOffer]) -> None:
    seen_create = False
    for offer in offers:
        if offer.action == "create":
            seen_create = True
        elif seen_create:
            raise FirstRunError("a create offer was shown before a reuse offer")


def assert_cost_disclosed(offers: Iterable[ResourceOffer]) -> None:
    for offer in offers:
        if offer.action == "create" and (offer.disk_cost_mb <= 0
                                         or offer.ram_cost_mb <= 0):
            raise FirstRunError(f"create offer {offer.model!r} omitted its cost")


# ---------------------------------------------------------------------------
# Y3.15 -- settings structure (M19e tree)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SettingSection:
    id: str
    label: str
    keys: tuple[str, ...] = ()
    children: tuple[SettingSection, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.label:
            raise SettingsTreeError("section needs an id and label")
        object.__setattr__(self, "keys", tuple(self.keys))
        object.__setattr__(self, "children", tuple(self.children))


SETTINGS_TREE: tuple[SettingSection, ...] = (
    SettingSection("general", "General", ("theme", "language")),
    SettingSection("models", "Models", ("default_model", "model_path")),
    SettingSection("permissions", "Permissions", ("permission_preset",)),
    SettingSection("security", "Security", ("sign_in", "alerts")),
    SettingSection("connectors", "Connectors", ("mcp_servers",)),
    SettingSection("channels", "Channels", ("channels",)),
    SettingSection("memory", "Memory", ("memory_enabled",)),
    SettingSection("data_privacy", "Data & privacy", ("data_dir", "telemetry")),
    SettingSection("admin", "Admin", ("invite_list", "limits", "operator_page")),
)

REQUIRED_SETTING_SECTIONS = tuple(s.id for s in SETTINGS_TREE)


def _walk(tree: Iterable[SettingSection]):
    for section in tree:
        yield section
        yield from _walk(section.children)


def validate_settings_tree(tree: Iterable[SettingSection] = SETTINGS_TREE
                           ) -> tuple[str, ...]:
    ids = [s.id for s in _walk(tree)]
    if len(ids) != len(set(ids)):
        raise SettingsTreeError("settings tree has duplicate section ids")
    missing = set(REQUIRED_SETTING_SECTIONS) - set(ids)
    if missing:
        raise SettingsTreeError(f"settings tree missing sections: {sorted(missing)}")
    return tuple(ids)


def section_for_key(key: str,
                    tree: Iterable[SettingSection] = SETTINGS_TREE) -> str:
    for section in _walk(tree):
        if key in section.keys:
            return section.id
    raise SettingsTreeError(f"setting key has no section: {key!r}")


# ---------------------------------------------------------------------------
# Y3.16 -- public API, outgoing webhooks, operator page: version-prefixed routes
# ---------------------------------------------------------------------------


PUBLIC_API_PREFIX = "/api/v1"
KEEL_API_PREFIX = "/api/keel/v1"
_VERSIONED_RE = re.compile(r"^/api/(keel/)?v[1-9][0-9]*$")


@dataclass(frozen=True)
class RouteDescriptor:
    surface: str
    prefix: str
    resource: str
    method: str = "GET"

    def __post_init__(self) -> None:
        if not self.surface or not self.resource:
            raise RouteError("route needs a surface and a resource")
        if isinstance(self.method, str):
            object.__setattr__(self, "method", self.method.upper())

    @property
    def path(self) -> str:
        return f"{self.prefix}/{self.resource.strip('/')}"

    def to_dict(self) -> dict:
        return {"surface": self.surface, "path": self.path,
                "method": self.method}


def build_route(surface: str, resource: str, *,
                prefix: str | None = None, method: str = "GET") -> RouteDescriptor:
    default = KEEL_API_PREFIX if surface == "keel_api" else PUBLIC_API_PREFIX
    route = RouteDescriptor(surface, prefix or default, resource, method)
    validate_route(route)
    return route


def validate_route(route: RouteDescriptor) -> None:
    if not _VERSIONED_RE.match(route.prefix):
        raise RouteError(f"route prefix must be versioned (/api/vN): {route.prefix!r}")
    if route.method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        raise RouteError(f"invalid HTTP method: {route.method!r}")


def is_keel_specific(route: RouteDescriptor) -> bool:
    return route.prefix.startswith("/api/keel/")


# Declared surfaces: public /api/v1, Keel-specific /api/keel/v1, outgoing
# webhooks (API contract A3.9) and the operator page (A3.1).
API_SURFACES: tuple[RouteDescriptor, ...] = (
    build_route("public_api", "runs"),
    build_route("public_api", "models"),
    build_route("keel_api", "operator"),
    build_route("keel_api", "pairing"),
    build_route("webhooks", "deliveries", method="POST"),
)


# ---------------------------------------------------------------------------
# Y3.17 -- agent-proposed project updates require approval
# ---------------------------------------------------------------------------


class ProposalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


@dataclass(frozen=True)
class DiffLine:
    path: str
    op: str                     # "+" or "-"
    text: str

    def __post_init__(self) -> None:
        if not self.path or self.op not in ("+", "-"):
            raise ProposalError("diff line needs a path and +/- operator")


@dataclass(frozen=True)
class ProjectProposal:
    id: str
    title: str
    diff: tuple[DiffLine, ...]
    state: ProposalState

    def __post_init__(self) -> None:
        object.__setattr__(self, "diff", tuple(self.diff))

    @property
    def fingerprint(self) -> str:
        return content_hash({"title": self.title,
                             "diff": [(d.path, d.op, d.text)
                                      for d in self.diff]})[:16]

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "state": self.state.value,
                "diff": [(d.path, d.op, d.text) for d in self.diff]}


class ProposalApplySeam:
    """Applying an approved diff is a real side effect: keep it behind a seam."""

    def apply(self, proposal: ProjectProposal) -> str:  # pragma: no cover - seam
        raise NotImplementedError


class RecordingApplySeam(ProposalApplySeam):
    def __init__(self) -> None:
        self.applied: list[str] = []

    def apply(self, proposal: ProjectProposal) -> str:
        self.applied.append(proposal.id)
        return f"applied:{proposal.id}"


class ProposalLedger:
    """Stores diff proposals; nothing is applied until a human approves it."""

    def __init__(self) -> None:
        self._proposals: dict[str, ProjectProposal] = {}

    def submit(self, title: str, diff: Iterable[DiffLine]) -> ProjectProposal:
        lines = tuple(diff)
        if not title or not lines:
            raise ProposalError("proposal needs a title and a non-empty diff")
        proposal_id = content_hash({"title": title,
                                    "diff": [(d.path, d.op, d.text)
                                             for d in lines]})[:12]
        proposal = ProjectProposal(proposal_id, title, lines, ProposalState.PENDING)
        self._proposals[proposal_id] = proposal
        return proposal

    def get(self, proposal_id: str) -> ProjectProposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise ProposalError(f"unknown proposal: {proposal_id!r}")
        return proposal

    def list(self) -> tuple[ProjectProposal, ...]:
        return tuple(self._proposals[k] for k in sorted(self._proposals))

    def approve(self, proposal_id: str, approver: str) -> ProjectProposal:
        if not approver:
            raise ProposalError("approver is required")
        proposal = self.get(proposal_id)
        if proposal.state is not ProposalState.PENDING:
            raise ProposalError(f"cannot approve a {proposal.state.value} proposal")
        approved = ProjectProposal(proposal.id, proposal.title, proposal.diff,
                                   ProposalState.APPROVED)
        self._proposals[proposal_id] = approved
        return approved

    def reject(self, proposal_id: str) -> ProjectProposal:
        proposal = self.get(proposal_id)
        if proposal.state is not ProposalState.PENDING:
            raise ProposalError(f"cannot reject a {proposal.state.value} proposal")
        rejected = ProjectProposal(proposal.id, proposal.title, proposal.diff,
                                   ProposalState.REJECTED)
        self._proposals[proposal_id] = rejected
        return rejected

    def apply(self, proposal_id: str, seam: ProposalApplySeam) -> str:
        proposal = self.get(proposal_id)
        if proposal.state is not ProposalState.APPROVED:
            raise ProposalError("project proposals require approval before apply")
        result = seam.apply(proposal)
        applied = ProjectProposal(proposal.id, proposal.title, proposal.diff,
                                  ProposalState.APPLIED)
        self._proposals[proposal_id] = applied
        return result


# ---------------------------------------------------------------------------
# Y3.18 -- large files stay compute-side; local cache with KEEL_DATA_DIR
# ---------------------------------------------------------------------------


DATA_DIR_ENV = "KEEL_DATA_DIR"
DEFAULT_DATA_DIR = ".keel/data"
_REMOTE_RE = re.compile(r"^(compute|relay)://")


def resolve_data_dir(env: Mapping[str, str] | None = None) -> str:
    """Read KEEL_DATA_DIR from an injectable env mapping (no filesystem I/O)."""
    source: Mapping[str, str] = os.environ if env is None else env
    value = source.get(DATA_DIR_ENV, "")
    return str(value) if value else DEFAULT_DATA_DIR


def assert_compute_side(uri: str) -> None:
    """Large task files must be referenced remotely, never by a local path."""
    if not _REMOTE_RE.match(uri):
        raise CacheError(f"large task files must stay compute-side: {uri!r}")


@dataclass(frozen=True)
class CachedFile:
    key: str
    remote_uri: str
    size_bytes: int
    last_used: int

    def __post_init__(self) -> None:
        if self.size_bytes < 0:
            raise CacheError("cache entry size must be non-negative")


class LocalCache:
    """Bounded LRU metadata cache; the bytes stay on the compute side."""

    def __init__(self, capacity_bytes: int,
                 data_dir: str | None = None) -> None:
        if capacity_bytes <= 0:
            raise CacheError("cache capacity must be positive")
        self._capacity = capacity_bytes
        self._data_dir = data_dir or resolve_data_dir()
        self._entries: dict[str, CachedFile] = {}
        self._clock = 0

    @property
    def data_dir(self) -> str:
        return self._data_dir

    @property
    def used_bytes(self) -> int:
        return sum(e.size_bytes for e in self._entries.values())

    def put(self, key: str, remote_uri: str, size_bytes: int) -> None:
        assert_compute_side(remote_uri)
        if size_bytes > self._capacity:
            raise CacheError("entry is larger than the entire cache")
        if key in self._entries:
            self._clock += 1
            self._entries[key] = CachedFile(key, remote_uri, size_bytes,
                                            self._clock)
            return
        while self.used_bytes + size_bytes > self._capacity:
            self.evict_one()
        self._clock += 1
        self._entries[key] = CachedFile(key, remote_uri, size_bytes, self._clock)

    def get(self, key: str) -> CachedFile:
        entry = self._entries.get(key)
        if entry is None:
            raise CacheError(f"cache miss: {key!r}")
        self._clock += 1
        refreshed = CachedFile(entry.key, entry.remote_uri, entry.size_bytes,
                               self._clock)
        self._entries[key] = refreshed
        return refreshed

    def evict_one(self) -> str | None:
        if not self._entries:
            return None
        victim = min(self._entries.values(), key=lambda e: (e.last_used, e.key))
        del self._entries[victim.key]
        return victim.key

    def snapshot(self) -> tuple[CachedFile, ...]:
        return tuple(self._entries[k] for k in sorted(self._entries))


# ---------------------------------------------------------------------------
# Y3.19 -- brand strings and assets in one config (fork must rename)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrandConfig:
    product_name: str
    logo_asset: str
    strings: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.product_name or not self.logo_asset:
            raise BrandError("brand needs a product name and a logo asset")
        object.__setattr__(self, "strings", dict(self.strings))


BRAND = BrandConfig(
    product_name="Keel",
    logo_asset="assets/brand/keel-logo.svg",
    strings={
        "app_name": "Keel",
        "tagline": "An independent coding harness",
        "setup_title": "Set up Keel",
        "admin_warning": "The agent runs as administrator on the computer.",
    },
)


def brand_string(key: str, brand: BrandConfig = BRAND) -> str:
    try:
        return brand.strings[key]
    except KeyError:
        raise BrandError(f"unknown brand string: {key!r}") from None


def forked_brand(product_name: str, logo_asset: str,
                 brand: BrandConfig = BRAND) -> BrandConfig:
    """White-label rename: every brand string comes from the one config."""
    if not product_name or not logo_asset:
        raise BrandError("forked brand needs a name and a logo asset")
    strings = {k: v.replace(brand.product_name, product_name)
               for k, v in brand.strings.items()}
    strings["app_name"] = product_name
    return BrandConfig(product_name, logo_asset, strings)


def assert_single_brand_source(brand: BrandConfig = BRAND,
                               other_literals: Iterable[str] = ()) -> None:
    """Reject hard-coded duplicate brand literals outside the one config."""
    for literal in other_literals:
        if brand.product_name in literal:
            raise BrandError(f"brand literal outside brand config: {literal!r}")


# ---------------------------------------------------------------------------
# Y3.20 -- docs set incl. security-model with explicit limits
# ---------------------------------------------------------------------------


REQUIRED_DOCS: tuple[str, ...] = (
    "README.md", "ARCHITECTURE.md", "security-model.md", "deploy.md",
    "OPERATIONS.md", "AGENTS.md", "CODE_OF_CONDUCT.md", "TRADEMARKS.md",
    "DISCLAIMER.md", "NOTICE.md", "THIRD_PARTY_NOTICES.md",
)

SECURITY_MODEL_LIMITS: tuple[str, ...] = (
    "prompt injection",
    "malicious content it reads",
    "runs as administrator",
    "no sandbox escape guarantees",
    "compromised dependencies",
    "social engineering",
)


@dataclass(frozen=True)
class DocDescriptor:
    name: str
    purpose: str
    requires_limits: bool = False


DOCS_SET: tuple[DocDescriptor, ...] = tuple(
    DocDescriptor(name, "required docs-set deliverable",
                  name == "security-model.md")
    for name in REQUIRED_DOCS
)


def validate_docs_set(names: Iterable[str]) -> tuple[str, ...]:
    present = set(names)
    missing = [name for name in REQUIRED_DOCS if name not in present]
    if missing:
        raise DocsError(f"docs set is missing: {missing}")
    return tuple(sorted(present))


def assert_security_model_complete(text: str) -> None:
    """The security model must state, not imply, what Keel cannot protect against."""
    if not text:
        raise DocsError("security-model.md is empty")
    lowered = text.lower()
    absent = [limit for limit in SECURITY_MODEL_LIMITS
              if limit.lower() not in lowered]
    if absent:
        raise DocsError(f"security model omits limits: {absent}")


# ---------------------------------------------------------------------------
# Y3.21 -- prominent administrator warning + permission preset explanation
# ---------------------------------------------------------------------------


ADMIN_WARNING = (
    "The agent runs as administrator on the computer and can be misled by "
    "content it reads. Review every proposed action, especially after the "
    "agent has read files, web pages or tool output."
)

PERMISSION_PRESET_EXPLANATIONS: tuple[tuple[str, str], ...] = (
    ("read-only", "The agent may read files but cannot edit or run commands."),
    ("workspace", "The agent may edit files inside the workspace only."),
    ("full", "The agent may run commands with your administrator privileges."),
)


@dataclass(frozen=True)
class FirstRunWarning:
    id: str
    title: str
    body: str
    severity: str = "warning"

    def __post_init__(self) -> None:
        if not self.id or not self.title or not self.body:
            raise WarningError("warning needs an id, title and body")


FIRST_RUN_WARNINGS: tuple[FirstRunWarning, ...] = (
    FirstRunWarning("admin-privilege", "Agent runs as administrator",
                    ADMIN_WARNING, "critical"),
    FirstRunWarning("permission-presets", "Choose a permission preset",
                    " ".join(f"{name}: {text}"
                             for name, text in PERMISSION_PRESET_EXPLANATIONS)),
)


def assert_admin_warning_present(
        warnings: Iterable[FirstRunWarning] = FIRST_RUN_WARNINGS) -> None:
    for warning in warnings:
        if "administrator" in warning.body.lower():
            return
    raise WarningError("first run is missing the administrator warning")


def assert_presets_explained(
        warnings: Iterable[FirstRunWarning] = FIRST_RUN_WARNINGS) -> None:
    body = " ".join(w.body for w in warnings)
    for name, explanation in PERMISSION_PRESET_EXPLANATIONS:
        if name not in body or explanation not in body:
            raise WarningError(f"permission preset {name!r} is not explained")


class AcknowledgementLedger:
    """Tracks which first-run warnings the user has acknowledged."""

    def __init__(self) -> None:
        self._acked: set[str] = set()

    def acknowledge(self, warning_id: str) -> None:
        self._acked.add(warning_id)

    def is_acknowledged(self, warning_id: str) -> bool:
        return warning_id in self._acked

    def require_admin_acknowledged(self) -> None:
        if not self.is_acknowledged("admin-privilege"):
            raise WarningError("the administrator warning must be acknowledged")
