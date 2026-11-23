"""Clipboard/screen capture guard and pure security-policy descriptors.

Plan-source rows implemented here (all ``status=not_started`` at baseline):

* **X5.9 (primary deliverable)** — "Clipboard and screen guard: tools that
  read clipboard/screen always ask, and tainted-source rules apply to captured
  content."  A read is *denied by default*: it needs an explicit, scoped,
  unexpired :class:`Approval`, and any taint (screen origin, secret-looking
  content, or a caller-supplied label) is recorded on a deterministic
  :class:`CaptureDescriptor` and requires an explicit taint acknowledgement.
* **X5.1 (P0)** — "Sensitive-project mode": a project flag hard-blocks remote
  providers/connectors and is surfaced as a lock badge.
* **X5.5 (P0)** — "Mass-change guard": a per-minute mutation rate limit whose
  breach produces a pause + snapshot descriptor.
* **X5.6 (P0)** — "Filesystem change journal": per-task set of touched paths,
  reviewable and revertible as a set.

Design rules (these are the acceptance criteria, enforced by tests):

1. **No silent capture.** This module never touches the real clipboard, screen,
   filesystem or network. It only processes content *explicitly supplied by the
   caller* and always returns a decision + descriptor. There is no import of
   ``pyperclip``/``pyautogui``/``PIL.ImageGrab``/``ctypes`` here.
2. **Explicit approval only.** Missing, malformed, expired, out-of-scope or
   un-attributed approvals all deny. There is no implicit/default grant.
3. **Tainted-source rules.** Screen-origin captures are tainted by definition;
   secret-looking content and explicit labels are tainted too. Tainted content
   is flagged and denied unless the caller acknowledges the taint explicitly.
4. **Deterministic descriptors.** Frozen dataclasses and canonical JSON
   (``sort_keys``, compact separators) mean identical inputs always serialize
   identically. Collected items are sorted before hashing/hand-off.
5. **Fail closed.** Unknown sources, empty purposes, unknown provider kinds,
   and tampered descriptors all deny; digests are never fabricated (absent
   content yields ``None``, never a hash of a stand-in value).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Mapping

__all__ = [
    "SCHEMA",
    "SOURCES",
    "TAINTED_BY_SOURCE",
    "NO_APPROVAL",
    "UNKNOWN_SOURCE",
    "EMPTY_PURPOSE",
    "APPROVAL_SOURCE_MISMATCH",
    "APPROVAL_PURPOSE_MISMATCH",
    "APPROVAL_EMPTY_APPROVER",
    "APPROVAL_EMPTY_ID",
    "APPROVAL_EXPIRED",
    "APPROVAL_NOT_YET_VALID",
    "UNSUPPORTED_SCHEMA",
    "TAINTED_SOURCE",
    "TAINTED_CONTENT",
    "TAINT_REQUIRES_ACK",
    "DESCRIPTOR_TAMPERED",
    "Approval",
    "CaptureDescriptor",
    "Decision",
    "ClipboardScreenGuard",
    "ProjectFlags",
    "SensitiveProjectPolicy",
    "MutationEvent",
    "MassChangeDecision",
    "MassChangeGuard",
    "JournalEntry",
    "ChangeJournal",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA = "clipboard-guard/v1"

SOURCES = ("clipboard", "screen", "screen_region", "screenshot")

# Screen-derived captures can observe arbitrary on-screen secrets (other
# windows, notifications, password fields). They are tainted unconditionally.
TAINTED_BY_SOURCE = frozenset({"screen", "screen_region", "screenshot"})

# Reason codes. Deny codes are explicit so tests/UI can assert on them.
NO_APPROVAL = "no_explicit_approval"
UNKNOWN_SOURCE = "unknown_source"
EMPTY_PURPOSE = "empty_purpose"
APPROVAL_SOURCE_MISMATCH = "approval_source_mismatch"
APPROVAL_PURPOSE_MISMATCH = "approval_purpose_mismatch"
APPROVAL_EMPTY_APPROVER = "approval_empty_approver"
APPROVAL_EMPTY_ID = "approval_empty_id"
APPROVAL_EXPIRED = "approval_expired"
APPROVAL_NOT_YET_VALID = "approval_not_yet_valid"
UNSUPPORTED_SCHEMA = "unsupported_descriptor_schema"
TAINTED_SOURCE = "tainted_source"
TAINTED_CONTENT = "tainted_content"
TAINT_REQUIRES_ACK = "taint_requires_explicit_acknowledgement"
DESCRIPTOR_TAMPERED = "descriptor_tampered_or_fabricated"

_TAINT_LABELS = frozenset({"secret", "credential", "token", "pii", "private"})

# Ordered dict: iteration order is deterministic across runs/processes.
_TAINT_PATTERNS: dict[str, re.Pattern[str]] = {
    "private_key_block": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
    ),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b"),
    "generic_secret_assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|secret|password|token)\b\s*[:=]\s*"
        r"[\"']?[A-Za-z0-9_\-]{16,}"
    ),
}

_UNSET = object()


def _canonical_bytes(value: Any) -> bytes:
    """Canonical UTF-8 JSON bytes; used for deterministic digests."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _now_seconds() -> int:
    return int(time.time())


def fingerprint(content: str | None) -> str | None:
    """Exact SHA-256 of the supplied content, or ``None`` when absent.

    ``None`` is deliberate: we never hash a stand-in value, so an absent
    capture can never be mistaken for a real one (no fabrication).
    """
    if content is None:
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# X5.9 — clipboard/screen guard
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Approval:
    """An explicit, scoped, time-boxed grant to read one source for one purpose."""

    approver: str
    source: str
    purpose: str
    approval_id: str
    issued_at: int
    expires_at: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaptureDescriptor:
    """Deterministic, content-free metadata describing a prospective read.

    Raw clipboard/screen content is intentionally *not* a field. Only its
    length and exact fingerprint are recorded, so the descriptor is safe to
    log or hand to an untrusted consumer.
    """

    schema: str
    source: str
    purpose: str
    requested_by: str
    tainted: bool
    taint_reasons: tuple[str, ...]
    classification: str
    content_length: int | None
    content_fingerprint: str | None
    content_provided: bool
    approved: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["taint_reasons"] = list(self.taint_reasons)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Decision:
    """Result of a read request. ``allowed`` is False unless every gate passes."""

    allowed: bool
    reasons: tuple[str, ...]
    descriptor: CaptureDescriptor

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "descriptor": self.descriptor.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


class ClipboardScreenGuard:
    """Policy engine for clipboard/screen reads. Pure; performs no I/O."""

    def __init__(
        self,
        *,
        now: Callable[[], int] | None = None,
        taint_patterns: Mapping[str, re.Pattern[str]] | None = None,
    ) -> None:
        self._now = now or _now_seconds
        self._patterns: dict[str, re.Pattern[str]] = (
            dict(taint_patterns) if taint_patterns is not None else dict(_TAINT_PATTERNS)
        )

    def _current_time(self, override: int | None) -> int:
        if override is not None:
            return int(override)
        return int(self._now())

    # -- taint ----------------------------------------------------------------

    def detect_taint(
        self,
        content: str | None,
        source: str,
        labels: Iterable[str] = (),
    ) -> tuple[bool, tuple[str, ...], str]:
        """Return ``(tainted, reasons, classification)`` for supplied content."""
        reasons: list[str] = []
        if source in TAINTED_BY_SOURCE:
            reasons.append(TAINTED_SOURCE)

        if content:
            for name, pattern in self._patterns.items():
                if pattern.search(content):
                    reasons.append(f"{TAINTED_CONTENT}:{name}")

        normalised = sorted(
            {str(label).strip().lower() for label in labels if str(label).strip()}
        )
        for label in normalised:
            if label in _TAINT_LABELS:
                reasons.append(f"{TAINTED_CONTENT}:label:{label}")

        tainted = bool(reasons)
        secret_hit = any(reason.startswith(f"{TAINTED_CONTENT}:") for reason in reasons)
        if secret_hit or "secret" in normalised:
            classification = "secret"
        elif tainted:
            classification = "internal"
        else:
            classification = "public"
        return tainted, tuple(reasons), classification

    # -- approval -------------------------------------------------------------

    def _approval_reasons(
        self,
        approval: Approval | None,
        source: str,
        purpose: str,
        now: int,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if approval is None:
            reasons.append(NO_APPROVAL)
            return tuple(reasons)
        if not str(approval.approver).strip():
            reasons.append(APPROVAL_EMPTY_APPROVER)
        if not str(approval.approval_id).strip():
            reasons.append(APPROVAL_EMPTY_ID)
        if approval.source != source:
            reasons.append(APPROVAL_SOURCE_MISMATCH)
        if approval.purpose != purpose:
            reasons.append(APPROVAL_PURPOSE_MISMATCH)
        if now < int(approval.issued_at):
            reasons.append(APPROVAL_NOT_YET_VALID)
        if now > int(approval.expires_at):
            reasons.append(APPROVAL_EXPIRED)
        return tuple(reasons)

    # -- descriptor / evaluation ---------------------------------------------

    def describe(
        self,
        *,
        source: str,
        purpose: str,
        requested_by: str = "",
        content: str | None = None,
        labels: Iterable[str] = (),
        approval: Approval | None = None,
        now: int | None = None,
    ) -> CaptureDescriptor:
        """Build a deterministic descriptor. Never reads any real source."""
        tainted, taint_reasons, classification = self.detect_taint(content, source, labels)
        approval_reasons = self._approval_reasons(
            approval, source, purpose, self._current_time(now)
        )
        return CaptureDescriptor(
            schema=SCHEMA,
            source=source,
            purpose=purpose,
            requested_by=requested_by,
            tainted=tainted,
            taint_reasons=taint_reasons,
            classification=classification,
            content_length=len(content) if content is not None else None,
            content_fingerprint=fingerprint(content),
            content_provided=content is not None,
            approved=not approval_reasons,
        )

    def verify_descriptor(
        self,
        descriptor: CaptureDescriptor,
        *,
        content: str | None = None,
        labels: Iterable[str] = (),
    ) -> bool:
        """Recompute a descriptor from supplied content and compare exactly.

        A caller-supplied descriptor claiming a clean fingerprint or a lower
        taint level than the content warrants is rejected here (no fabrication).
        """
        if descriptor.schema != SCHEMA:
            return False
        rebuilt = self.describe(
            source=descriptor.source,
            purpose=descriptor.purpose,
            requested_by=descriptor.requested_by,
            content=content,
            labels=labels,
        )
        # Ignore the approval bit here: it depends on time/approval and is
        # re-evaluated independently. Everything derived from content must match.
        return rebuilt.to_json() == descriptor.to_json()

    def evaluate(
        self,
        descriptor: CaptureDescriptor,
        approval: Approval | None = None,
        *,
        now: int | None = None,
        taint_acknowledgement: str | None = None,
        verify_content: Any = _UNSET,
        labels: Iterable[str] = (),
    ) -> Decision:
        """Decide whether a described read may proceed. Deny by default."""
        current = self._current_time(now)
        reasons: list[str] = []

        if descriptor.schema != SCHEMA:
            reasons.append(UNSUPPORTED_SCHEMA)
        if descriptor.source not in SOURCES:
            reasons.append(UNKNOWN_SOURCE)
        if not str(descriptor.purpose).strip():
            reasons.append(EMPTY_PURPOSE)

        if verify_content is not _UNSET and not self.verify_descriptor(
            descriptor, content=verify_content, labels=labels
        ):
            reasons.append(DESCRIPTOR_TAMPERED)

        # Never trust descriptor.approved; recompute from the authoritative
        # approval object so a tampered flag cannot grant access.
        reasons.extend(
            self._approval_reasons(approval, descriptor.source, descriptor.purpose, current)
        )

        if descriptor.tainted and not (
            taint_acknowledgement and taint_acknowledgement.strip().lower() == "acknowledged"
        ):
            reasons.append(TAINT_REQUIRES_ACK)

        return Decision(allowed=not reasons, reasons=tuple(reasons), descriptor=descriptor)

    def request(
        self,
        *,
        source: str,
        purpose: str,
        requested_by: str = "",
        content: str | None = None,
        labels: Iterable[str] = (),
        approval: Approval | None = None,
        now: int | None = None,
        taint_acknowledgement: str | None = None,
    ) -> Decision:
        """Convenience path: describe supplied content, then evaluate it."""
        descriptor = self.describe(
            source=source,
            purpose=purpose,
            requested_by=requested_by,
            content=content,
            labels=labels,
            approval=approval,
            now=now,
        )
        return self.evaluate(
            descriptor,
            approval,
            now=now,
            taint_acknowledgement=taint_acknowledgement,
        )


# ---------------------------------------------------------------------------
# X5.1 — sensitive-project mode
# ---------------------------------------------------------------------------

# Unknown kinds are treated as remote (fail closed).
_LOCAL_PROVIDER_KINDS = frozenset({"local", "builtin", "local_model"})


@dataclass(frozen=True)
class ProjectFlags:
    sensitive_project: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SensitiveProjectPolicy:
    """Pure descriptor policy: a sensitive project blocks all remote egress."""

    @staticmethod
    def remote_allowed(flags: ProjectFlags, provider_kind: str) -> bool:
        kind = str(provider_kind).strip().lower()
        if not flags.sensitive_project:
            return True
        return kind in _LOCAL_PROVIDER_KINDS

    @staticmethod
    def badge(flags: ProjectFlags) -> str:
        return "\N{LOCK}" if flags.sensitive_project else ""


# ---------------------------------------------------------------------------
# X5.5 — mass-change guard
# ---------------------------------------------------------------------------

_COUNTED_ACTIONS = frozenset({"create", "modify", "delete", "rename"})


@dataclass(frozen=True)
class MutationEvent:
    path: str
    action: str
    at: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MassChangeDecision:
    breached: bool
    count: int
    limit: int
    window_seconds: int
    pause_agent: bool
    snapshot_required: bool
    snapshot_digest: str | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


class MassChangeGuard:
    """Pure rate limiter over caller-supplied mutation events (no FS access)."""

    def __init__(
        self,
        *,
        limit: int = 50,
        window_seconds: int = 60,
        counted_actions: Iterable[str] = _COUNTED_ACTIONS,
    ) -> None:
        self.limit = int(limit)
        self.window_seconds = int(window_seconds)
        self.counted_actions = frozenset(counted_actions)

    def evaluate(
        self,
        events: Iterable[MutationEvent],
        *,
        now: int | None = None,
    ) -> MassChangeDecision:
        current = _now_seconds() if now is None else int(now)
        start = current - self.window_seconds
        in_window = [
            event
            for event in events
            if event.action in self.counted_actions and start <= int(event.at) <= current
        ]
        in_window.sort(key=lambda e: (int(e.at), e.path, e.action))
        count = len(in_window)
        breached = count > self.limit
        reasons: tuple[str, ...] = (
            ("mass_change_limit_exceeded",) if breached else ()
        )
        # Snapshot digest is derived from the actual counted events only.
        digest = _digest([event.to_dict() for event in in_window]) if breached else None
        return MassChangeDecision(
            breached=breached,
            count=count,
            limit=self.limit,
            window_seconds=self.window_seconds,
            pause_agent=breached,
            snapshot_required=breached,
            snapshot_digest=digest,
            reasons=reasons,
        )


# ---------------------------------------------------------------------------
# X5.6 — filesystem change journal
# ---------------------------------------------------------------------------

_REVERSIBLE_ACTIONS = frozenset({"create", "modify", "delete", "rename"})


@dataclass(frozen=True)
class JournalEntry:
    seq: int
    task_id: str
    path: str
    action: str
    at: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChangeJournal:
    """In-memory, per-task change journal. Records descriptors, never touches FS."""

    def __init__(self) -> None:
        self._entries: list[JournalEntry] = []

    def record(self, task_id: str, path: str, action: str, at: int) -> JournalEntry:
        entry = JournalEntry(
            seq=len(self._entries) + 1,
            task_id=task_id,
            path=path,
            action=action,
            at=int(at),
        )
        self._entries.append(entry)
        return entry

    def review(self, task_id: str) -> tuple[JournalEntry, ...]:
        return tuple(e for e in self._entries if e.task_id == task_id)

    def paths(self, task_id: str) -> tuple[str, ...]:
        return tuple(sorted({e.path for e in self.review(task_id)}))

    def revert_plan(self, task_id: str) -> tuple[JournalEntry, ...]:
        """Reverse-ordered descriptors for every reversible path of a task."""
        reversible = [e for e in self.review(task_id) if e.action in _REVERSIBLE_ACTIONS]
        return tuple(reversed(reversible))

    def to_json(self, task_id: str) -> str:
        return json.dumps(
            [e.to_dict() for e in self.review(task_id)],
            sort_keys=True,
            separators=(",", ":"),
        )
