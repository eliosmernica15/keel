"""Steering and interrupt for a running turn (X1.13).

A single controller handles the three ways a user (or another agent) can
inject a message while a turn is in flight:

* :class:`SteeringMode.QUEUE` — hold it for the next turn; never deliver it
  into the turn that is already running.
* :class:`SteeringMode.STEER_AT_BOUNDARY` — hold it until the session reaches
  a tool boundary, then deliver exactly one message per :meth:`poll_boundary`.
* :class:`SteeringMode.ABORT_RESUME` — cancel the turn, keep the text written
  so far byte-for-byte, and return the message on :meth:`resume`.

The controller is in-process, thread-safe (multiple submitters and consumers
may call it concurrently) and stdlib-only. It does not itself run tools or
talk to a provider: the session loop owns those concerns and calls
:meth:`poll_boundary` / :attr:`cancel_event` at its own boundaries.

Retention policy (bounded memory, explicit overflow)
----------------------------------------------------
An unbounded controller retained every message forever (20k undrained messages
kept 20k objects and >6 MB RSS). Retention is now bounded and configurable via
``max_messages``/``max_protected`` on :class:`SteeringController`:

* Ordinary messages are evicted **oldest first** when the total cap is reached,
  so the most recent context is always kept.
* Messages tagged with a :data:`PROTECTED_TAGS` entry, messages submitted in
  ``ABORT_RESUME`` mode, and anything still waiting in ``resume_pending`` are
  pinned (they are security/control context or still needed for resume) and
  are never evicted by that ordinary-message rule. Pinned entries have their
  own ``max_protected`` bound; a submission that would exceed it raises
  :class:`SteeringError` instead of silently discarding security context.
* Eviction is **never silent**: :attr:`overflow_count` and
  :meth:`dropped_messages` expose what was dropped (sequence number plus a
  short text preview). Callers that need durable history must persist it;
  this in-memory controller only guarantees the bounded recent window.
* Untrusted text is not treated as disposable merely because it is untrusted:
  callers that must keep a piece of untrusted context can tag it (e.g.
  ``tags={"untrusted"}``) to pin it, subject to ``max_protected``. If the pin
  budget is exhausted the submission fails closed with ``SteeringError``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from enum import Enum
from threading import Event, RLock

__all__ = [
    "PROTECTED_TAGS",
    "SteeringController",
    "SteeringError",
    "SteeringMessage",
    "SteeringMode",
    "SteeringSnapshot",
    "ResumeResult",
]

# Tags that mark a message as security/control context. Such messages are
# pinned: ordinary-message eviction never removes them. The pins are bounded
# separately (``max_protected``) so a caller cannot bypass the memory cap by
# tagging everything.
PROTECTED_TAGS = frozenset({"security", "sensitive", "untrusted", "audit"})

_DEFAULT_MAX_MESSAGES = 4096
_DEFAULT_MAX_PROTECTED = 256
_DROPPED_HISTORY = 128


def _positive_limit(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SteeringError(f"{label} must be a positive integer")
    return value


class SteeringError(ValueError):
    """Raised for an invalid mode or payload, or a retention limit breach."""


class SteeringMode(Enum):
    QUEUE = "queue"
    STEER_AT_BOUNDARY = "steer_at_boundary"
    ABORT_RESUME = "abort_resume"


@dataclass(frozen=True)
class SteeringMessage:
    """An immutable, ordered steering message.

    ``seq`` is assigned under the controller lock, so it is a deterministic
    total order across concurrent submitters (the order in which they acquired
    the lock). It is also a stable identity for delivery and de-duplication.
    """

    text: str
    mode: SteeringMode
    seq: int
    tags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SteeringSnapshot:
    """A point-in-time copy of the whole controller state.

    ``partial_output`` is an immutable ``bytes`` copy, so a snapshot keeps the
    output byte-for-byte even if the live buffer is later extended or reset.
    """

    partial_output: bytes
    seq: int
    mode: SteeringMode
    cancelled: bool
    abort_count: int
    queued: tuple[SteeringMessage, ...] = ()
    boundary: tuple[SteeringMessage, ...] = ()
    resume_pending: tuple[SteeringMessage, ...] = ()
    delivered: tuple[SteeringMessage, ...] = ()
    all_messages: tuple[SteeringMessage, ...] = ()
    overflow_count: int = 0
    dropped: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class ResumeResult:
    """What the session needs after an abort-and-resume.

    ``partial_output`` is the byte-for-byte output captured at abort time;
    ``messages`` are the steering messages to inject into the resumed turn,
    in submission order.
    """

    partial_output: bytes
    messages: tuple[SteeringMessage, ...] = ()


class SteeringController:
    """Thread-safe coordinator for mid-turn message injection.

    Class-level aliases (``QUEUE``, ``STEER_AT_BOUNDARY``, ``ABORT_RESUME``)
    let callers write ``submit_message(text, controller.ABORT_RESUME)``.
    """

    QUEUE = SteeringMode.QUEUE
    STEER_AT_BOUNDARY = SteeringMode.STEER_AT_BOUNDARY
    ABORT_RESUME = SteeringMode.ABORT_RESUME
    Mode = SteeringMode

    def __init__(self, mode: SteeringMode | str = SteeringMode.QUEUE, *,
                 max_messages: int = _DEFAULT_MAX_MESSAGES,
                 max_protected: int = _DEFAULT_MAX_PROTECTED) -> None:
        self._lock = RLock()
        self._cancel = Event()
        self._output = bytearray()
        self._seq = 0
        self._abort_count = 0
        self._mode = self._coerce_mode(mode, required=True)
        self.max_messages = _positive_limit(max_messages, "max_messages")
        self.max_protected = _positive_limit(max_protected, "max_protected")
        if self.max_protected > self.max_messages:
            raise SteeringError("max_protected cannot exceed max_messages")
        # Insertion-ordered dicts keyed by seq give O(1) removal and a
        # deterministic oldest-first iteration order.
        self._queued: dict[int, SteeringMessage] = {}
        self._boundary: dict[int, SteeringMessage] = {}
        self._resume_pending: dict[int, SteeringMessage] = {}
        self._delivered: dict[int, SteeringMessage] = {}
        self._all: dict[int, SteeringMessage] = {}
        self._location: dict[int, str] = {}
        self._overflow_count = 0
        self._dropped: deque[tuple[int, str]] = deque(maxlen=_DROPPED_HISTORY)
        self._abort_snapshot: SteeringSnapshot | None = None

    # ------------------------------------------------------------------
    # bounded-retention helpers (all called with self._lock held)
    # ------------------------------------------------------------------
    @staticmethod
    def _bucket(name: str) -> str:
        return "_" + name

    @staticmethod
    def _is_protected(message: SteeringMessage) -> bool:
        return (message.mode is SteeringMode.ABORT_RESUME
                or bool(message.tags & PROTECTED_TAGS))

    def _is_pinned(self, message: SteeringMessage) -> bool:
        # resume_pending is still needed by the next resume(), so it is never
        # a candidate for ordinary eviction.
        return (self._is_protected(message)
                or self._location.get(message.seq) == "resume_pending")

    def _protected_count_locked(self) -> int:
        return sum(1 for message in self._all.values()
                   if self._is_protected(message))

    def _note_overflow_locked(self, message: SteeringMessage) -> None:
        self._overflow_count += 1
        self._dropped.append((message.seq, message.text[:80]))

    def _evict_oldest_locked(self) -> bool:
        """Drop the oldest non-pinned message. Returns False if none exists."""
        for seq, message in self._all.items():
            if self._is_pinned(message):
                continue
            self._all.pop(seq)
            bucket_name = self._location.pop(seq, None)
            if bucket_name:
                getattr(self, self._bucket(bucket_name)).pop(seq, None)
            self._note_overflow_locked(message)
            return True
        return False

    def _reserve_locked(self, *, protected: bool) -> None:
        """Make room for one message or fail closed without mutating state."""
        if protected and self._protected_count_locked() >= self.max_protected:
            raise SteeringError(
                f"protected steering message limit reached ({self.max_protected})")
        while len(self._all) >= self.max_messages:
            if not self._evict_oldest_locked():
                raise SteeringError(
                    f"steering message cap reached ({self.max_messages})")

    def _set_location_locked(self, seq: int, name: str | None) -> None:
        if name is None:
            self._location.pop(seq, None)
        else:
            self._location[seq] = name

    # ------------------------------------------------------------------
    # mode / cancellation accessors
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_mode(mode: SteeringMode | str | None,
                     *, required: bool = False) -> SteeringMode | None:
        if mode is None:
            if required:
                raise SteeringError("mode is required")
            return None
        if isinstance(mode, SteeringMode):
            return mode
        if isinstance(mode, str):
            key = mode.strip().upper()
            if key in SteeringMode.__members__:
                return SteeringMode[key]
            try:
                return SteeringMode(mode.strip().lower())
            except ValueError:
                pass
        raise SteeringError(f"unknown steering mode: {mode!r}")

    @property
    def mode(self) -> SteeringMode:
        """The default mode used when ``submit_message`` is called without one."""
        with self._lock:
            return self._mode

    def set_mode(self, mode: SteeringMode | str) -> SteeringMode:
        """Change the default mode used by subsequent ``submit_message`` calls."""
        resolved = self._coerce_mode(mode, required=True)
        with self._lock:
            self._mode = resolved
            return resolved

    @property
    def cancel_event(self) -> Event:
        """The event a session's tool loop checks to propagate cancellation."""
        return self._cancel

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def abort_count(self) -> int:
        with self._lock:
            return self._abort_count

    # ------------------------------------------------------------------
    # partial output
    # ------------------------------------------------------------------
    def append_output(self, chunk: bytes | bytearray | memoryview | str) -> None:
        """Record text produced so far; ``str`` is encoded as UTF-8.

        Kept as raw bytes so binary/invalid-UTF-8 fragments are preserved.
        """
        if isinstance(chunk, str):
            data = chunk.encode("utf-8")
        elif isinstance(chunk, (bytes, bytearray, memoryview)):
            data = bytes(chunk)
        else:
            raise SteeringError("output chunk must be bytes or str")
        with self._lock:
            self._output.extend(data)

    @property
    def partial_output(self) -> bytes:
        """An immutable copy of everything appended so far."""
        with self._lock:
            return bytes(self._output)

    # ------------------------------------------------------------------
    # submission / delivery
    # ------------------------------------------------------------------
    def submit_message(self, text: str,
                       mode: SteeringMode | str | None = None, *,
                       tags: object = None) -> SteeringMessage:
        """Accept a mid-turn message and route it according to ``mode``.

        ``mode`` defaults to the controller's current mode. Every submission
        gets a unique, monotonically increasing ``seq``. Retention is bounded
        (see the module docstring): oldest ordinary messages are evicted when
        ``max_messages`` is reached, while security-tagged / abort / resume
        messages are pinned up to ``max_protected``. Overflow is observable
        through :attr:`overflow_count` and :meth:`dropped_messages`.

        ``tags`` may be a single string or an iterable of strings. A tag in
        :data:`PROTECTED_TAGS` pins the message (e.g. ``tags={"untrusted"}``
        for untrusted context that must survive until the next turn).
        """
        if not isinstance(text, str):
            raise SteeringError("message text must be str")
        resolved_mode = self._coerce_mode(mode)
        if tags is None:
            tagset: frozenset[str] = frozenset()
        else:
            try:
                raw = (tags,) if isinstance(tags, str) else tuple(tags)
            except TypeError as exc:
                raise SteeringError("tags must be strings") from exc
            if not all(isinstance(tag, str) for tag in raw):
                raise SteeringError("tags must be strings")
            tagset = frozenset(tag.strip().lower() for tag in raw if tag.strip())
        with self._lock:
            effective = resolved_mode if resolved_mode is not None else self._mode
            message = SteeringMessage(text=text, mode=effective,
                                      seq=self._seq, tags=tagset)
            # Reserve space before assigning seq so a rejected submission does
            # not leave a gap in the deterministic ordering.
            self._reserve_locked(protected=self._is_protected(message))
            self._seq += 1
            seq = message.seq
            self._all[seq] = message

            if effective is SteeringMode.ABORT_RESUME:
                # Add before aborting: the abort snapshot must include it.
                self._resume_pending[seq] = message
                self._set_location_locked(seq, "resume_pending")
                self._abort_locked()
            elif self._cancel.is_set() and effective is SteeringMode.STEER_AT_BOUNDARY:
                # A cancelled turn cannot be steered; hand it to resume instead.
                self._resume_pending[seq] = message
                self._set_location_locked(seq, "resume_pending")
            elif effective is SteeringMode.STEER_AT_BOUNDARY:
                self._boundary[seq] = message
                self._set_location_locked(seq, "boundary")
            else:
                self._queued[seq] = message
                self._set_location_locked(seq, "queued")
            return message

    def poll_boundary(self) -> SteeringMessage | None:
        """Return the next steering message at a tool boundary, or ``None``.

        Only ``STEER_AT_BOUNDARY`` messages are delivered here. After an abort
        the turn is over, so this always returns ``None``; pending messages
        are carried into the resume payload instead.
        """
        with self._lock:
            if self._cancel.is_set() or not self._boundary:
                return None
            seq = next(iter(self._boundary))  # insertion order == seq order
            message = self._boundary.pop(seq)
            self._delivered[seq] = message
            self._set_location_locked(seq, "delivered")
            return message

    def drain_queue(self) -> tuple[SteeringMessage, ...]:
        """Take all ``QUEUE`` messages in submission order (for the next turn)."""
        with self._lock:
            messages = tuple(self._queued.values())
            for seq in self._queued:
                self._set_location_locked(seq, None)
            self._queued.clear()
            return messages

    def pending_resume_messages(self) -> tuple[SteeringMessage, ...]:
        """Messages waiting to be injected when the aborted turn resumes."""
        with self._lock:
            return tuple(self._resume_pending.values())

    def delivered_messages(self) -> tuple[SteeringMessage, ...]:
        with self._lock:
            return tuple(self._delivered.values())

    def all_messages(self) -> tuple[SteeringMessage, ...]:
        """Every retained message, in the deterministic ``seq`` order.

        Retained is the operative word: when the bounded window overflows the
        oldest ordinary messages are evicted and recorded in
        :meth:`dropped_messages`.
        """
        with self._lock:
            return tuple(self._all.values())

    @property
    def overflow_count(self) -> int:
        """Total number of messages evicted by the bounded retention policy."""
        with self._lock:
            return self._overflow_count

    def dropped_messages(self) -> tuple[tuple[int, str], ...]:
        """Bounded history of evictions as ``(seq, text_preview)`` pairs."""
        with self._lock:
            return tuple(self._dropped)

    # ------------------------------------------------------------------
    # abort / snapshot / restore / resume
    # ------------------------------------------------------------------
    def _abort_locked(self) -> SteeringSnapshot:
        # Idempotent: a second abort must not overwrite the first snapshot or
        # change the partial output it preserved.
        if not self._cancel.is_set():
            self._abort_count += 1
            self._cancel.set()
            # Never strand a message that was waiting at a boundary: carry it
            # into the resume payload so cancellation cannot lose it.
            if self._boundary:
                self._resume_pending.update(self._boundary)
                for seq in self._boundary:
                    self._set_location_locked(seq, "resume_pending")
                self._boundary.clear()
                # Delivery order is always submission order, even when an
                # abort message jumps the queue by triggering the abort.
                self._resume_pending = dict(sorted(
                    self._resume_pending.items(), key=lambda pair: pair[0]))
            self._abort_snapshot = self._snapshot_locked()
        return self._abort_snapshot  # type: ignore[return-value]

    def abort(self) -> SteeringSnapshot:
        """Cancel the turn and preserve its partial output.

        Repeated calls are harmless and return the same snapshot; only the
        first abort increments ``abort_count``. Cancellation is observable via
        :attr:`cancelled` and :attr:`cancel_event`, which the session's tool
        loop can check to stop work.
        """
        with self._lock:
            return self._abort_locked()

    def _snapshot_locked(self) -> SteeringSnapshot:
        return SteeringSnapshot(
            partial_output=bytes(self._output),
            seq=self._seq,
            mode=self._mode,
            cancelled=self._cancel.is_set(),
            abort_count=self._abort_count,
            queued=tuple(self._queued.values()),
            boundary=tuple(self._boundary.values()),
            resume_pending=tuple(self._resume_pending.values()),
            delivered=tuple(self._delivered.values()),
            all_messages=tuple(self._all.values()),
            overflow_count=self._overflow_count,
            dropped=tuple(self._dropped),
        )

    def snapshot(self) -> SteeringSnapshot:
        """Capture the full controller state, including immutable output bytes."""
        with self._lock:
            return self._snapshot_locked()

    def restore(self, snapshot: SteeringSnapshot) -> None:
        """Replace the live state with a previously captured snapshot."""
        if not isinstance(snapshot, SteeringSnapshot):
            raise SteeringError("restore() expects a SteeringSnapshot")
        with self._lock:
            self._output = bytearray(snapshot.partial_output)
            self._seq = snapshot.seq
            self._mode = snapshot.mode
            self._abort_count = snapshot.abort_count
            if snapshot.cancelled:
                self._cancel.set()
            else:
                self._cancel.clear()
            self._queued = {m.seq: m for m in snapshot.queued}
            self._boundary = {m.seq: m for m in snapshot.boundary}
            self._resume_pending = {m.seq: m for m in snapshot.resume_pending}
            self._delivered = {m.seq: m for m in snapshot.delivered}
            self._all = {m.seq: m for m in snapshot.all_messages}
            self._location = {}
            for name in ("queued", "boundary", "resume_pending", "delivered"):
                for seq in getattr(self, self._bucket(name)):
                    self._set_location_locked(seq, name)
            self._overflow_count = int(snapshot.overflow_count)
            self._dropped = deque(snapshot.dropped, maxlen=_DROPPED_HISTORY)
            # A snapshot from an older/unbounded controller could exceed the
            # configured cap; enforce the same policy on restore.
            while len(self._all) > self.max_messages:
                if not self._evict_oldest_locked():
                    raise SteeringError(
                        "snapshot exceeds steering retention limits")

    def resume(self) -> ResumeResult:
        """Restore the output captured at abort and release steering messages.

        Only the partial output is rewound (byte-for-byte). Message queues are
        deliberately kept live, so a message submitted *after* the abort is
        not lost by restoring an older snapshot. A resume without a preceding
        abort is a harmless no-op.
        """
        with self._lock:
            base = self._abort_snapshot
            if base is None:
                self._cancel.clear()
                return ResumeResult(partial_output=self.partial_output, messages=())

            # Overlay the live message state onto the abort snapshot so that
            # restore() is used for the byte-exact output without discarding
            # anything submitted in the meantime.
            merged = replace(
                base,
                partial_output=base.partial_output,
                cancelled=False,
                seq=self._seq,
                mode=self._mode,
                queued=tuple(self._queued.values()),
                boundary=tuple(self._boundary.values()),
                resume_pending=tuple(self._resume_pending.values()),
                delivered=tuple(self._delivered.values()),
                all_messages=tuple(self._all.values()),
                overflow_count=self._overflow_count,
                dropped=tuple(self._dropped),
            )
            self.restore(merged)  # RLock is reentrant
            messages = tuple(self._resume_pending.values())
            for seq in self._resume_pending:
                self._set_location_locked(seq, None)
            self._resume_pending.clear()
            self._abort_snapshot = None
            return ResumeResult(partial_output=self.partial_output, messages=messages)

    def reset(self) -> None:
        """Clear all state so the controller can be reused for a new turn."""
        with self._lock:
            self._cancel.clear()
            self._output.clear()
            self._seq = 0
            self._abort_count = 0
            self._queued.clear()
            self._boundary.clear()
            self._resume_pending.clear()
            self._delivered.clear()
            self._all.clear()
            self._location.clear()
            self._overflow_count = 0
            self._dropped.clear()
            self._abort_snapshot = None
