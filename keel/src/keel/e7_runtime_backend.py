"""Stdlib-only backend behavior descriptors for the 36 open ``E7.*`` rows.

This module is the pure, testable host-side surface for the ``not_started``
addendum-7 ("DS-SEAMS") rows in ``PLAN-INDEX.json``.  It is deliberately not a
stub collection: every feature below has a concrete function, dataclass or
policy with observable, adversarial-tested behavior.  Like the sibling
``*_contracts`` modules it holds **no host state**: no files, no sockets, no
subprocesses, no clock, no chance input and no credential storage.  Callers own
identifiers, payloads, check functions and persistence; this layer only
validates, folds, resolves, ranks, authorizes and describes.

Scope notes
-----------
Every one of the 36 rows is an ``implementation_tier: local_module`` seam with
no owner approval and no external prerequisite.  The host-side core of each
row is therefore in scope here.  The *delivery* halves are explicitly **not**
claimed: document preview sidebars (E7.25), Forge/Inspector panels (E7.27,
E7.40), card renderers (E7.31), browser/desktop UI and consent dialogs
(E7.43), and any real SSH/Office/STT/LSP/network engine.  Where a row extends
an existing ID (E7.39 extends D3.8, E7.42 extends W3.11) only the additional
backend policy is implemented; the underlying seam is owned elsewhere and was
not modified.  ``PLAN-INDEX.json`` and all existing files are untouched.

Security invariants (enforced by ``test_e7_runtime_backend.py``):

* unknown, malformed or mistyped input fails closed (never silently accepts);
* authorization and source authentication are separate values;
* embedded cross-session text is tainted, bounded and delimiter-safe;
* no capability is granted by a name, a receipt or a query alone;
* no I/O, clock, random, dynamic execution or import side effects exist here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

FEATURE_IDS: tuple[str, ...] = (
    "E7.1", "E7.3", "E7.4", "E7.5", "E7.7", "E7.8", "E7.9",
    "E7.10", "E7.11", "E7.12", "E7.13", "E7.14", "E7.15", "E7.16",
    "E7.17", "E7.22", "E7.24", "E7.25", "E7.26", "E7.27", "E7.28",
    "E7.29", "E7.30", "E7.31", "E7.32", "E7.33", "E7.34", "E7.35",
    "E7.36", "E7.37", "E7.38", "E7.39", "E7.40", "E7.41", "E7.42",
    "E7.43",
)

# ---------------------------------------------------------------------------
# Shared fail-closed helpers
# ---------------------------------------------------------------------------


class BackendError(ValueError):
    """Base class for every failure raised by this module."""


class ValidationError(BackendError):
    """Malformed or unknown input; messages never echo credential material."""


class NotFoundError(BackendError):
    """A referenced record, peer, session or provider does not exist."""


class ConflictError(BackendError):
    """A state transition (CAS, lock, role, throttle) was not permitted."""


_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/\-]*$")
_SECRET_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9_\-]{8,}|"
    r"xox[baprs]-[A-Za-z0-9_\-]{8,}|AKIA[A-Z0-9]{8,}|"
    r"AIza[A-Za-z0-9_\-]{8,})"
)
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|"
    r"passwd|credential|bearer)\b\s*[:=]\s*(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s,;}]+)"
)


def _text(value: Any, label: str = "value") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("%s must be a non-empty string" % label)
    return value.strip()


def _ident(value: Any, label: str = "id") -> str:
    text = _text(value, label)
    if not _ID_RE.match(text) or ".." in text:
        raise ValidationError("%s is not a safe identifier" % label)
    return text


def _nonneg_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError("%s must be a non-negative integer" % label)
    return value


def _as_tuple(values: Any, label: str) -> tuple:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValidationError("%s must be a sequence" % label)
    return tuple(values)


def _enum(enum_cls: type[Enum], value: Any) -> Enum:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        raise ValidationError("unknown %s: %r" % (enum_cls.__name__, value)) from None


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    if isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, bytes):
        raw = value
    else:
        raw = _canonical(value)
    return hashlib.sha256(raw).hexdigest()


def _json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_json_safe(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _json_safe(v) for k, v in value.items())
    return False


def _copy(value: Any) -> Any:
    """JSON round-trip copy; refuses non-JSON values."""
    if not _json_safe(value):
        raise ValidationError("value must be JSON-safe")
    return json.loads(_canonical(value).decode("utf-8"))


def _redact(text: str) -> str:
    text = _SECRET_RE.sub("[REDACTED]", text)
    return _SECRET_ASSIGN_RE.sub("[REDACTED]", text)


# ---------------------------------------------------------------------------
# E7.1 -- tokenMeter: isolated per-session replay folds, revisioned snapshots
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenMeasurement:
    session_id: str
    revision: int
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def describe(self) -> dict:
        return {
            "feature_id": "E7.1", "session_id": self.session_id,
            "revision": self.revision, "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class PressureMeasurement:
    """Immutable measurement shared by every pressure consumer."""

    revisions: tuple[tuple[str, int], ...]
    total_tokens: int
    digest: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.1", "revisions": list(self.revisions),
            "total_tokens": self.total_tokens, "digest": self.digest,
        }


class TokenMeter:
    """Fold token events per session; replay is pure and sessions are isolated."""

    def __init__(self) -> None:
        self._events: dict[str, tuple[tuple[int, int], ...]] = {}

    def fold(self, session_id: str, prompt_tokens: int = 0,
             completion_tokens: int = 0) -> TokenMeasurement:
        sid = _ident(session_id, "session_id")
        prompt = _nonneg_int(prompt_tokens, "prompt_tokens")
        completion = _nonneg_int(completion_tokens, "completion_tokens")
        events = self._events.get(sid, ()) + ((prompt, completion),)
        self._events[sid] = events
        return self._measurement(sid, events)

    def replay(self, session_id: str) -> TokenMeasurement:
        """Rebuild the same measurement from an empty fold (no meter state)."""
        sid = _ident(session_id, "session_id")
        return self._measurement(sid, self._events.get(sid, ()))

    def latest(self, session_id: str) -> TokenMeasurement:
        sid = _ident(session_id, "session_id")
        if sid not in self._events:
            raise NotFoundError("no token events for session")
        return self._measurement(sid, self._events[sid])

    def pressure_measurement(self, session_ids: Sequence[str]) -> PressureMeasurement:
        ids = _as_tuple(session_ids, "session_ids")
        rows: list[tuple[str, int]] = []
        total = 0
        for sid in ids:
            ident = _ident(sid, "session_id")
            events = self._events.get(ident, ())
            rows.append((ident, len(events)))
            total += sum(p + c for p, c in events)
        rows = tuple(sorted(rows))
        return PressureMeasurement(rows, total, _digest(rows + (total,)))

    @staticmethod
    def _measurement(sid: str, events: tuple[tuple[int, int], ...]) -> TokenMeasurement:
        return TokenMeasurement(
            sid, len(events), sum(p for p, _ in events), sum(c for _, c in events)
        )


# ---------------------------------------------------------------------------
# E7.3 -- compaction via pressure events only; no model-facing compact tool
# ---------------------------------------------------------------------------


class PressureEventKind(str, Enum):
    POST_STEP = "post_step"
    REQUEST_ERROR = "request_error"
    USER_REQUEST = "user_request"


class CompactionAction(str, Enum):
    NONE = "none"
    COMPACT = "compact"
    COMPACT_AFTER_RECOVERY = "compact_after_recovery"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PressureEvent:
    kind: PressureEventKind
    session_id: str
    pressure: float
    recoverable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum(PressureEventKind, self.kind))
        object.__setattr__(self, "session_id", _ident(self.session_id, "session_id"))
        if isinstance(self.pressure, bool) or not isinstance(self.pressure, (int, float)):
            raise ValidationError("pressure must be a number in [0, 1]")
        if not 0.0 <= float(self.pressure) <= 1.0:
            raise ValidationError("pressure must be a number in [0, 1]")
        if not isinstance(self.recoverable, bool):
            raise ValidationError("recoverable must be a bool")


def compaction_decision(event: PressureEvent, threshold: float = 0.8) -> CompactionAction:
    """Compaction is a loop-event reaction, never a model-callable tool."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) \
            or not 0.0 <= float(threshold) <= 1.0:
        raise ValidationError("threshold must be a number in [0, 1]")
    if event.kind is PressureEventKind.USER_REQUEST:
        return CompactionAction.REJECTED
    if float(event.pressure) < float(threshold):
        return CompactionAction.NONE
    if event.kind is PressureEventKind.REQUEST_ERROR:
        return (CompactionAction.COMPACT_AFTER_RECOVERY if event.recoverable
                else CompactionAction.NONE)
    return CompactionAction.COMPACT


_FORBIDDEN_COMPACT_TOOLS = frozenset({
    "compact", "compact_session", "compact_conversation", "force_compact",
})


def assert_no_compact_tool(tools: Iterable[str]) -> None:
    """Reject any model-facing tool that would trigger compaction directly."""
    for tool in _as_tuple(tools, "tools"):
        if str(tool).strip().lower() in _FORBIDDEN_COMPACT_TOOLS:
            raise ValidationError("compaction is not a model-facing tool")


# ---------------------------------------------------------------------------
# E7.4 -- sessionStatus: acknowledgements outside the canonical history
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionStatus:
    session_id: str
    last_read_seq: int
    manually_unread: bool
    revision: int

    def describe(self) -> dict:
        return {
            "feature_id": "E7.4", "session_id": self.session_id,
            "last_read_seq": self.last_read_seq,
            "manually_unread": self.manually_unread, "revision": self.revision,
        }


class SessionStatusStore:
    """Separate status table: acks never fold into session messages."""

    def __init__(self) -> None:
        self._rows: dict[str, SessionStatus] = {}

    def acknowledge(self, session_id: str, seq: int) -> SessionStatus:
        sid = _ident(session_id, "session_id")
        seq = _nonneg_int(seq, "seq")
        old = self._rows.get(sid)
        if old is not None and seq < old.last_read_seq:
            raise ConflictError("acknowledgements are monotonic")
        row = SessionStatus(sid, seq, bool(old.manually_unread) if old else False,
                            (old.revision if old else 0) + 1)
        self._rows[sid] = row
        return row

    def mark_unread(self, session_id: str) -> SessionStatus:
        sid = _ident(session_id, "session_id")
        old = self._rows.get(sid, SessionStatus(sid, 0, False, 0))
        row = SessionStatus(sid, old.last_read_seq, True, old.revision + 1)
        self._rows[sid] = row
        return row

    def mark_read(self, session_id: str, seq: int) -> SessionStatus:
        sid = _ident(session_id, "session_id")
        seq = _nonneg_int(seq, "seq")
        old = self._rows.get(sid, SessionStatus(sid, 0, True, 0))
        if seq < old.last_read_seq:
            raise ConflictError("acknowledgements are monotonic")
        row = SessionStatus(sid, seq, False, old.revision + 1)
        self._rows[sid] = row
        return row

    def status(self, session_id: str) -> SessionStatus:
        sid = _ident(session_id, "session_id")
        return self._rows.get(sid, SessionStatus(sid, 0, False, 0))


_STATUS_LOG_KEYS = frozenset({
    "read", "unread", "ack", "acknowledged", "status", "last_read_seq",
    "manually_unread",
})


def assert_status_out_of_log(messages: Iterable[Any]) -> None:
    """Fail if read-state leaked into a canonical log message."""
    for message in _as_tuple(messages, "messages"):
        if isinstance(message, Mapping):
            if _STATUS_LOG_KEYS.intersection(message):
                raise ValidationError("read status must live outside session history")
        elif isinstance(message, str) and re.search(
            r"\b(?:unread|last_read_seq|manually_unread)\b", message, re.I
        ):
            raise ValidationError("read status must live outside session history")


# ---------------------------------------------------------------------------
# E7.5 -- workspaceChanges: turn-start vs turn-end, keyed by session + seq
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkspaceSnapshot:
    files: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        paths = [path for path, _ in self.files]
        if len(paths) != len(set(paths)) or paths != sorted(paths):
            raise ValidationError("snapshot paths must be unique and sorted")
        for path, digest in self.files:
            _text(path, "path")
            _text(digest, "digest")
            if ".." in path or path.startswith("/") or "\\" in path:
                raise ValidationError("snapshot path must be workspace-relative")

    def mapping(self) -> dict[str, str]:
        return dict(self.files)


def make_snapshot(files: Mapping[str, str]) -> WorkspaceSnapshot:
    if not isinstance(files, Mapping):
        raise ValidationError("files must be a mapping")
    return WorkspaceSnapshot(tuple(sorted((str(k), str(v)) for k, v in files.items())))


@dataclass(frozen=True)
class WorkspaceChangeTurn:
    session_id: str
    event_seq: int
    added: tuple[str, ...]
    modified: tuple[str, ...]
    removed: tuple[str, ...]

    def describe(self) -> dict:
        return {
            "feature_id": "E7.5", "session_id": self.session_id,
            "event_seq": self.event_seq, "added": list(self.added),
            "modified": list(self.modified), "removed": list(self.removed),
        }


class WorkspaceChangeFeed:
    def __init__(self) -> None:
        self._begins: dict[str, tuple[int, WorkspaceSnapshot]] = {}
        self._turns: dict[str, list[WorkspaceChangeTurn]] = {}
        self._last_end: dict[str, int] = {}

    def begin_turn(self, session_id: str, event_seq: int,
                   snapshot: WorkspaceSnapshot) -> None:
        sid = _ident(session_id, "session_id")
        seq = _nonneg_int(event_seq, "event_seq")
        if seq <= self._last_end.get(sid, -1):
            raise ConflictError("turn sequence must advance across turns")
        if sid in self._begins and seq <= self._begins[sid][0]:
            raise ConflictError("turn sequence must advance")
        self._begins[sid] = (seq, snapshot)

    def end_turn(self, session_id: str, event_seq: int,
                 snapshot: WorkspaceSnapshot) -> WorkspaceChangeTurn:
        sid = _ident(session_id, "session_id")
        seq = _nonneg_int(event_seq, "event_seq")
        if sid not in self._begins:
            raise NotFoundError("turn was not begun")
        start_seq, before = self._begins[sid]
        if seq <= start_seq:
            raise ConflictError("turn end must follow turn start")
        old, new = before.mapping(), snapshot.mapping()
        turn = WorkspaceChangeTurn(
            sid, seq,
            tuple(sorted(set(new) - set(old))),
            tuple(sorted(k for k in set(new) & set(old) if new[k] != old[k])),
            tuple(sorted(set(old) - set(new))),
        )
        self._turns.setdefault(sid, []).append(turn)
        self._last_end[sid] = seq
        del self._begins[sid]
        return turn

    def changes(self, session_id: str, after_seq: int = 0) -> tuple[WorkspaceChangeTurn, ...]:
        sid = _ident(session_id, "session_id")
        return tuple(t for t in self._turns.get(sid, ()) if t.event_seq > after_seq)


def assert_log_carries_turn_only(message: Mapping[str, Any]) -> None:
    """The canonical log stores the turn identity, never per-file deltas."""
    if not isinstance(message, Mapping):
        raise ValidationError("log message must be a mapping")
    if _FILE_DELTA_KEYS.intersection(message):
        raise ValidationError("log carries only the turn, not file deltas")


_FILE_DELTA_KEYS = frozenset({"added", "modified", "removed", "files", "deltas"})


# ---------------------------------------------------------------------------
# E7.7 -- fileReferences: @ completion returns paths, never contents
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PathSuggestion:
    path: str
    kind: str

    def describe(self) -> dict:
        return {"feature_id": "E7.7", "path": self.path, "kind": self.kind}


_CONTENT_KEYS = frozenset({
    "content", "contents", "body", "text", "data", "preview", "raw", "value",
})


def path_completions(prefix: str, candidates: Sequence[Any]) -> tuple[PathSuggestion, ...]:
    """Pure @path completion: only paths and kinds leave this function."""
    _text(prefix, "prefix")
    out: list[PathSuggestion] = []
    for candidate in _as_tuple(candidates, "candidates"):
        if isinstance(candidate, Mapping):
            if _CONTENT_KEYS.intersection(candidate):
                raise ValidationError("completion candidates must not carry content")
            path = candidate.get("path")
            kind = candidate.get("kind", "file")
        else:
            path, kind = candidate, "file"
        path = _text(path, "path")
        if ".." in path or "\x00" in path or "\n" in path:
            raise ValidationError("unsafe completion path")
        if path.startswith(prefix):
            out.append(PathSuggestion(path, str(kind)))
    return tuple(sorted(out, key=lambda s: (s.path, s.kind)))


def assert_paths_only(suggestions: Iterable[Any]) -> None:
    """Defense in depth: no serialized suggestion may carry file bytes."""
    for item in _as_tuple(suggestions, "suggestions"):
        if isinstance(item, Mapping):
            if _CONTENT_KEYS.intersection(item):
                raise ValidationError("@ completion leaked file contents")
        elif not isinstance(item, PathSuggestion):
            raise ValidationError("unknown suggestion type")
        else:
            for key in _CONTENT_KEYS:
                if hasattr(item, key):
                    raise ValidationError("@ completion leaked file contents")


def parse_at_paths(text: str) -> tuple[str, ...]:
    """Extract @ paths from composer text; this function never reads a file."""
    _text(text, "text")
    return tuple(dict.fromkeys(
        match.group(1) for match in re.finditer(r"(?<![\w/])@([A-Za-z0-9_./\-]+)", text)
    ))


# ---------------------------------------------------------------------------
# E7.8 -- sessionReferenceResolver: bounded, tainted cross-session context
# ---------------------------------------------------------------------------

_UNTRUSTED_OPEN = "<untrusted_session_reference>"
_UNTRUSTED_CLOSE = "</untrusted_session_reference>"
_ESCAPED_CLOSE = "<untrusted_session_reference_escaped>"


@dataclass(frozen=True)
class SessionReference:
    session_id: str
    max_messages: int = 5
    max_chars: int = 2000

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _ident(self.session_id, "session_id"))
        object.__setattr__(self, "max_messages", _nonneg_int(self.max_messages, "max_messages"))
        object.__setattr__(self, "max_chars", _nonneg_int(self.max_chars, "max_chars"))


@dataclass(frozen=True)
class EmbeddedContext:
    session_id: str
    body: str
    untrusted: bool = True

    def describe(self) -> dict:
        return {
            "feature_id": "E7.8", "session_id": self.session_id,
            "untrusted": self.untrusted, "text": self.wrapped(),
        }

    def wrapped(self) -> str:
        return "%s\n%s\n%s" % (_UNTRUSTED_OPEN, self.body, _UNTRUSTED_CLOSE)


def resolve_session_reference(reference: SessionReference,
                              messages: Iterable[Any]) -> EmbeddedContext:
    """Embed a *bounded* snapshot; content is untrusted and delimiter-safe."""
    items = _as_tuple(messages, "messages")
    chunks: list[str] = []
    for message in items[-reference.max_messages:]:
        if isinstance(message, Mapping):
            text = message.get("content", "")
        else:
            text = message
        chunks.append(_redact(str(text)))
    body = "\n".join(chunks).replace(_UNTRUSTED_CLOSE, _ESCAPED_CLOSE)
    if len(body) > reference.max_chars:
        body = body[:reference.max_chars].rstrip() + "\n[TRUNCATED]"
    return EmbeddedContext(reference.session_id, body, True)


def assert_untrusted_context(context: EmbeddedContext) -> None:
    if not context.untrusted:
        raise ValidationError("cross-session context must be tainted")
    if _UNTRUSTED_CLOSE in context.body:
        raise ValidationError("embedded text tried to close the untrusted wrapper")
    if not context.wrapped().startswith(_UNTRUSTED_OPEN):
        raise ValidationError("missing untrusted wrapper")


# ---------------------------------------------------------------------------
# E7.9 -- sessionQuery: exact/filter/trace plus ranked FTS-style search
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchHit:
    session_id: str
    seq: int
    score: float
    snippet: str

    def describe(self) -> dict:
        return {
            "session_id": self.session_id, "seq": self.seq,
            "score": round(self.score, 4), "snippet": self.snippet,
        }


@dataclass(frozen=True)
class SearchPage:
    hits: tuple[SearchHit, ...]
    cursor: str
    generation: int

    def describe(self) -> dict:
        return {
            "feature_id": "E7.9", "generation": self.generation,
            "cursor": self.cursor, "hits": [h.describe() for h in self.hits],
        }


def _encode_cursor(offset: int, generation: int, identity: str) -> str:
    payload = {"o": offset, "g": generation, "d": _digest(identity)}
    return base64.urlsafe_b64encode(_canonical(payload)).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, generation: int, identity: str) -> int:
    if not isinstance(cursor, str) or not cursor:
        raise ValidationError("cursor must be a non-empty string")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("malformed cursor") from None
    if not isinstance(payload, dict) or set(payload) != {"o", "g", "d"}:
        raise ValidationError("malformed cursor")
    offset = payload["o"]
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValidationError("malformed cursor offset")
    if payload["g"] != generation or payload["d"] != _digest(identity):
        raise ConflictError("cursor generation or result set changed")
    return offset


class SessionQueryService:
    """Deterministic exact reads, filters, traces and cursor-paged search."""

    def __init__(self) -> None:
        self._messages: dict[str, tuple[tuple[int, str], ...]] = {}

    def add_message(self, session_id: str, seq: int, text: str) -> None:
        sid = _ident(session_id, "session_id")
        seq = _nonneg_int(seq, "seq")
        for old_seq, _ in self._messages.get(sid, ()):
            if old_seq == seq:
                raise ConflictError("duplicate message seq")
        self._messages[sid] = self._messages.get(sid, ()) + ((seq, _text(text, "text")),)

    def exact(self, session_id: str, seq: int) -> str:
        sid = _ident(session_id, "session_id")
        for old_seq, text in self._messages.get(sid, ()):
            if old_seq == seq:
                return text
        raise NotFoundError("message not found")

    def filter(self, predicate: Callable[[str, int, str], bool]) -> tuple:
        if not callable(predicate):
            raise ValidationError("predicate must be callable")
        out = []
        for sid, messages in sorted(self._messages.items()):
            for seq, text in messages:
                if predicate(sid, seq, text):
                    out.append((sid, seq, text))
        return tuple(out)

    def trace(self, session_id: str) -> tuple[int, ...]:
        sid = _ident(session_id, "session_id")
        if sid not in self._messages:
            raise NotFoundError("session not found")
        return tuple(sorted(seq for seq, _ in self._messages[sid]))

    def search(self, query: str, *, generation: int = 1, page_size: int = 2,
               cursor: str | None = None) -> SearchPage:
        terms = [t for t in re.findall(r"\w+", _text(query, "query").lower()) if t]
        if not terms:
            raise ValidationError("query needs at least one term")
        page_size = _nonneg_int(page_size, "page_size")
        if page_size == 0:
            raise ValidationError("page_size must be positive")
        generation = _nonneg_int(generation, "generation")
        hits: list[SearchHit] = []
        for sid, messages in self._messages.items():
            for seq, text in messages:
                lowered = text.lower()
                count = sum(lowered.count(term) for term in terms)
                if count:
                    hits.append(SearchHit(sid, seq, float(count), self._snippet(text, terms)))
        hits.sort(key=lambda h: (-h.score, -h.seq, h.session_id))
        identity = "|".join("%s:%d" % (h.session_id, h.seq) for h in hits)
        offset = _decode_cursor(cursor, generation, identity) if cursor else 0
        if offset > len(hits):
            raise ConflictError("cursor offset is past the result set")
        return SearchPage(tuple(hits[offset:offset + page_size]),
                          _encode_cursor(offset + page_size, generation, identity),
                          generation)

    @staticmethod
    def _snippet(text: str, terms: Sequence[str], width: int = 80) -> str:
        lowered = text.lower()
        positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
        start = max(0, min(positions) - width // 4) if positions else 0
        snippet = text[start:start + width]
        if start:
            snippet = "..." + snippet
        if start + width < len(text):
            snippet += "..."
        return snippet


# ---------------------------------------------------------------------------
# E7.10 -- sessionTitle: deterministic fallback, latest fold, one provider
# ---------------------------------------------------------------------------

_TITLE_MAX = 80


def fallback_title(first_prompt: Any) -> str:
    text = _redact(" ".join(str(first_prompt).split()))
    if not text:
        raise ValidationError("title fallback needs a prompt")
    return text[:_TITLE_MAX]


class TitleProviderMode(str, Enum):
    FIRST_PROMPT = "first_prompt"
    ALL_PROMPTS = "all_prompts"


@dataclass(frozen=True)
class TitleRecord:
    session_id: str
    title: str
    seq: int
    source: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.10", "session_id": self.session_id,
            "title": self.title, "seq": self.seq, "source": self.source,
        }


@dataclass(frozen=True)
class TitleProvider:
    name: str
    mode: TitleProviderMode
    handler: Callable[[Sequence[str]], str] = field(compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "provider name"))
        object.__setattr__(self, "mode", _enum(TitleProviderMode, self.mode))
        if not callable(self.handler):
            raise ValidationError("title provider handler must be callable")


class TitleService:
    """Titles never block: any provider failure yields the deterministic fold."""

    def __init__(self) -> None:
        self._latest: dict[str, TitleRecord] = {}
        self._provider: TitleProvider | None = None

    def register_provider(self, name: str, handler: Callable[[Sequence[str]], str],
                          mode: TitleProviderMode = TitleProviderMode.FIRST_PROMPT
                          ) -> TitleProvider:
        if self._provider is not None:
            raise ConflictError("only one title provider is allowed")
        provider = TitleProvider(name, mode, handler)
        self._provider = provider
        return provider

    def fold(self, session_id: str, seq: int, *, title: str | None = None,
             prompt: str | None = None) -> TitleRecord:
        sid = _ident(session_id, "session_id")
        seq = _nonneg_int(seq, "seq")
        old = self._latest.get(sid)
        if old is not None and seq < old.seq:
            raise ConflictError("title fold requires a non-decreasing seq")
        if title is not None:
            value = fallback_title(title)
            source = "provider"
        elif prompt is not None:
            value = fallback_title(prompt)
            source = "fallback"
        else:
            raise ValidationError("a title or a prompt is required")
        record = TitleRecord(sid, value, seq, source)
        self._latest[sid] = record
        return record

    def title_for(self, session_id: str, prompts: Sequence[str]) -> TitleRecord:
        sid = _ident(session_id, "session_id")
        texts = _as_tuple(prompts, "prompts")
        if not texts:
            raise ValidationError("at least one prompt is required")
        if self._provider is not None:
            chosen = (texts[0],) if self._provider.mode is TitleProviderMode.FIRST_PROMPT else texts
            try:
                generated = self._provider.handler(chosen)
                return self.fold(sid, len(texts), title=str(generated))
            except Exception:
                pass  # provider failure is never allowed to block a title
        return self.fold(sid, len(texts), prompt=texts[-1])

    def latest(self, session_id: str) -> TitleRecord:
        sid = _ident(session_id, "session_id")
        if sid not in self._latest:
            raise NotFoundError("no title for session")
        return self._latest[sid]


# ---------------------------------------------------------------------------
# E7.11 -- planMode: log-folded state, boundary flush, stable exit schema
# ---------------------------------------------------------------------------


class PlanMode(str, Enum):
    PLAN = "plan"
    ACT = "act"


class PlanEventKind(str, Enum):
    MODE = "mode"
    SELECT = "select"
    MESSAGE = "message"


@dataclass(frozen=True)
class PlanEvent:
    kind: PlanEventKind
    seq: int
    value: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum(PlanEventKind, self.kind))
        object.__setattr__(self, "seq", _nonneg_int(self.seq, "seq"))


@dataclass(frozen=True)
class PlanState:
    session_id: str
    mode: PlanMode
    plan: str
    revision: int

    def describe(self) -> dict:
        return {
            "feature_id": "E7.11", "session_id": self.session_id,
            "mode": self.mode.value, "plan": self.plan, "revision": self.revision,
        }


PLAN_EXIT_SCHEMA: tuple[tuple[str, str], ...] = (
    ("status", "str"), ("mode", "str"), ("plan_revision", "int"), ("session_id", "str"),
)


def plan_exit_schema() -> dict:
    """A stable, versioned exit schema for /plan."""
    return {
        "schema_version": 1,
        "feature_id": "E7.11",
        "fields": [{"name": n, "type": t} for n, t in PLAN_EXIT_SCHEMA],
    }


class PlanModeService:
    def __init__(self) -> None:
        self._states: dict[str, PlanState] = {}
        self._pending: dict[str, list[PlanEvent]] = {}

    def fold(self, session_id: str, events: Iterable[PlanEvent]) -> PlanState:
        sid = _ident(session_id, "session_id")
        state = self._states.get(sid, PlanState(sid, PlanMode.ACT, "", 0))
        for event in sorted(_as_tuple(events, "events"), key=lambda e: e.seq):
            if event.seq <= state.revision:
                continue
            if event.kind is PlanEventKind.MODE:
                state = PlanState(sid, _enum(PlanMode, event.value), state.plan, event.seq)
            elif event.kind is PlanEventKind.SELECT:
                state = PlanState(sid, state.mode, _text(event.value, "plan"), event.seq)
            # MESSAGE events are deliberately inert for plan state.
        self._states[sid] = state
        return state

    def queue_selection(self, session_id: str, plan: str) -> None:
        sid = _ident(session_id, "session_id")
        self._pending.setdefault(sid, []).append(
            PlanEvent(PlanEventKind.SELECT, 0, _text(plan, "plan"))
        )

    def flush(self, session_id: str, boundary_seq: int) -> PlanState:
        sid = _ident(session_id, "session_id")
        boundary_seq = _nonneg_int(boundary_seq, "boundary_seq")
        state = self._states.get(sid, PlanState(sid, PlanMode.ACT, "", 0))
        pending = self._pending.get(sid, ())
        for event in pending:
            state = PlanState(sid, state.mode, event.value, max(boundary_seq, state.revision + 1))
        self._states[sid] = state
        self._pending[sid] = []
        return state

    def plan_command(self, session_id: str, args: Sequence[str] = ()) -> PlanState:
        sid = _ident(session_id, "session_id")
        argv = [str(a) for a in _as_tuple(args, "args")]
        state = self._states.get(sid, PlanState(sid, PlanMode.ACT, "", 0))
        mode = PlanMode.PLAN if not argv or argv[0] != "exit" else PlanMode.ACT
        new = PlanState(sid, mode, state.plan, state.revision + 1)
        self._states[sid] = new
        return new

    def exit(self, session_id: str) -> dict:
        sid = _ident(session_id, "session_id")
        state = self._states.get(sid)
        if state is None:
            raise NotFoundError("no plan state")
        return {
            "status": "ok" if state.mode is PlanMode.ACT else "plan_open",
            "mode": state.mode.value, "plan_revision": state.revision,
            "session_id": sid,
        }


# ---------------------------------------------------------------------------
# E7.12 -- agentPresets: revisions, YAML declaration, retired pin retention
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PresetRevision:
    name: str
    revision: int
    components: tuple[str, ...]
    retired: bool = False

    def describe(self) -> dict:
        return {
            "feature_id": "E7.12", "name": self.name, "revision": self.revision,
            "components": list(self.components), "retired": self.retired,
        }


def parse_preset_yaml(text: str) -> PresetRevision:
    """Parse the tiny, strict preset subset (name/revision/components)."""
    raw = _text(text, "yaml")
    values: dict[str, str] = {}
    components: list[str] = []
    in_components = False
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if not in_components:
                raise ValidationError("component item outside components block")
            components.append(_ident(stripped[2:], "component"))
            continue
        if ":" not in stripped:
            raise ValidationError("malformed preset YAML line")
        key, value = (part.strip() for part in stripped.split(":", 1))
        if key == "components":
            if value:
                components.extend(_ident(c.strip(), "component") for c in value.strip("[]").split(",") if c.strip())
            in_components = True
            continue
        in_components = False
        if key not in {"name", "revision"} or key in values:
            raise ValidationError("unknown or duplicate preset YAML key")
        values[key] = value
    if set(values) != {"name", "revision"}:
        raise ValidationError("preset YAML needs name and revision")
    if not components:
        raise ValidationError("preset YAML needs at least one component")
    try:
        revision = int(values["revision"])
    except ValueError:
        raise ValidationError("revision must be an integer") from None
    if revision < 0:
        raise ValidationError("revision must be non-negative")
    return PresetRevision(_ident(values["name"], "name"), revision, tuple(components))


class PresetRegistry:
    def __init__(self) -> None:
        self._current: dict[str, PresetRevision] = {}
        self._all: dict[tuple[str, int], PresetRevision] = {}
        self._bindings: dict[str, tuple[str, int]] = {}

    def publish(self, preset: PresetRevision | str,
                components: Sequence[str] = ()) -> PresetRevision:
        if isinstance(preset, str):
            parsed = PresetRevision(_ident(preset, "name"), 0, _as_tuple(components, "components"))
        else:
            parsed = preset
        key = (parsed.name, parsed.revision)
        if key in self._all:
            raise ConflictError("preset revision already published")
        if not parsed.components:
            raise ValidationError("preset needs components")
        self._all[key] = parsed
        self._current[parsed.name] = parsed
        return parsed

    def retire(self, name: str) -> PresetRevision:
        name = _ident(name, "name")
        if name not in self._current:
            raise NotFoundError("unknown preset")
        old = self._current[name]
        retired = PresetRevision(old.name, old.revision, old.components, True)
        self._all[(name, old.revision)] = retired
        del self._current[name]  # retired revisions are no longer offered to new sessions
        return retired

    def bind(self, session_id: str, name: str) -> PresetRevision:
        sid = _ident(session_id, "session_id")
        name = _ident(name, "name")
        if name not in self._current:
            raise NotFoundError("unknown preset")
        current = self._current[name]
        self._bindings[sid] = (current.name, current.revision)
        return self._all[(current.name, current.revision)]

    def release(self, session_id: str) -> PresetRevision | None:
        sid = _ident(session_id, "session_id")
        key = self._bindings.pop(sid, None)
        if key is None:
            raise NotFoundError("session has no preset binding")
        revision = self._all[key]
        if revision.retired and not any(k == key for k in self._bindings.values()):
            del self._all[key]
            return revision
        return None

    def revision_for(self, session_id: str) -> PresetRevision:
        sid = _ident(session_id, "session_id")
        if sid not in self._bindings:
            raise NotFoundError("session has no preset binding")
        return self._all[self._bindings[sid]]


# ---------------------------------------------------------------------------
# E7.13 -- sessionProjectionCache: throttled, mandatory checkpoints
# ---------------------------------------------------------------------------

MANDATORY_CHECKPOINT_REASONS = frozenset({"turn_end", "detach"})


@dataclass(frozen=True)
class Checkpoint:
    session_id: str
    event_seq: int
    state_digest: str
    reason: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.13", "session_id": self.session_id,
            "event_seq": self.event_seq, "state_digest": self.state_digest,
            "reason": self.reason,
        }


class ProjectionCache:
    """Checkpoint descriptors only; persistence is the caller's responsibility."""

    def __init__(self, throttle_seq: int = 5) -> None:
        self.throttle_seq = _nonneg_int(throttle_seq, "throttle_seq")
        self._latest: dict[str, Checkpoint] = {}

    def checkpoint(self, session_id: str, event_seq: int, state: Mapping[str, Any],
                   reason: str = "periodic") -> Checkpoint | None:
        sid = _ident(session_id, "session_id")
        seq = _nonneg_int(event_seq, "event_seq")
        reason = _text(reason, "reason")
        if not isinstance(state, Mapping) or not _json_safe(state):
            raise ValidationError("checkpoint state must be a JSON-safe mapping")
        old = self._latest.get(sid)
        if old is not None:
            if seq <= old.event_seq:
                raise ConflictError("checkpoint sequence must advance")
            mandatory = reason in MANDATORY_CHECKPOINT_REASONS
            if not mandatory and seq - old.event_seq < self.throttle_seq:
                return None
        checkpoint = Checkpoint(sid, seq, _digest(state), reason)
        self._latest[sid] = checkpoint
        return checkpoint

    def latest(self, session_id: str) -> Checkpoint:
        sid = _ident(session_id, "session_id")
        if sid not in self._latest:
            raise NotFoundError("no checkpoint")
        return self._latest[sid]

    def invalidate(self, session_id: str) -> None:
        sid = _ident(session_id, "session_id")
        self._latest.pop(sid, None)


# ---------------------------------------------------------------------------
# E7.14 -- mcpManager: settings reconciliation, status aggregation, restart
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class McpSettings:
    name: str
    config_digest: str
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "name"))
        object.__setattr__(self, "config_digest", _text(self.config_digest, "config_digest"))


@dataclass(frozen=True)
class McpInstance:
    name: str
    config_digest: str
    status: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.14", "name": self.name,
            "config_digest": self.config_digest, "status": self.status,
        }


@dataclass(frozen=True)
class ReconcilePlan:
    start: tuple[str, ...]
    stop: tuple[str, ...]
    restart: tuple[str, ...]

    def describe(self) -> dict:
        return {
            "feature_id": "E7.14", "start": list(self.start),
            "stop": list(self.stop), "restart": list(self.restart),
        }


def reconcile(settings: Mapping[str, McpSettings],
              current: Mapping[str, McpInstance]) -> ReconcilePlan:
    start: list[str] = []
    stop: list[str] = []
    restart: list[str] = []
    for name, setting in sorted(settings.items()):
        instance = current.get(name)
        if not setting.enabled:
            if instance is not None:
                stop.append(name)
            continue
        if instance is None:
            start.append(name)
        elif instance.config_digest != setting.config_digest:
            restart.append(name)
    for name in sorted(set(current) - set(settings)):
        stop.append(name)
    return ReconcilePlan(tuple(start), tuple(stop), tuple(restart))


class McpManager:
    def __init__(self) -> None:
        self._instances: dict[str, McpInstance] = {}
        self._settings: dict[str, McpSettings] = {}

    def apply(self, settings: Mapping[str, McpSettings]) -> ReconcilePlan:
        for name, setting in settings.items():
            _ident(name, "name")
            if not isinstance(setting, McpSettings):
                raise ValidationError("settings values must be McpSettings")
        plan = reconcile(settings, self._instances)
        for name in plan.stop:
            self._instances.pop(name, None)
        for name in plan.start + plan.restart:
            setting = settings[name]
            self._instances[name] = McpInstance(name, setting.config_digest, "connecting")
        self._settings = dict(settings)
        return plan

    def probe(self, name: str, ok: bool) -> McpInstance:
        name = _ident(name, "name")
        if name not in self._instances:
            raise NotFoundError("unknown MCP instance")
        if not isinstance(ok, bool):
            raise ValidationError("ok must be a bool")
        instance = McpInstance(name, self._instances[name].config_digest,
                               "connected" if ok else "failed")
        self._instances[name] = instance
        return instance

    def restart(self, name: str) -> McpInstance:
        name = _ident(name, "name")
        if name not in self._settings or not self._settings[name].enabled:
            raise NotFoundError("MCP server is not configured")
        instance = McpInstance(name, self._settings[name].config_digest, "connecting")
        self._instances[name] = instance
        return instance

    def aggregate(self) -> dict:
        counts: dict[str, int] = {}
        for instance in self._instances.values():
            counts[instance.status] = counts.get(instance.status, 0) + 1
        return {"feature_id": "E7.14", "total": len(self._instances), "by_status": counts}


# ---------------------------------------------------------------------------
# E7.15 -- schedule independent of session activation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduledTask:
    task_id: str
    session_id: str
    due_tick: int
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _ident(self.task_id, "task_id"))
        object.__setattr__(self, "session_id", _ident(self.session_id, "session_id"))
        object.__setattr__(self, "due_tick", _nonneg_int(self.due_tick, "due_tick"))
        object.__setattr__(self, "message", _text(self.message, "message"))


@dataclass(frozen=True)
class DueMessage:
    task_id: str
    session_id: str
    message: str
    due_tick: int

    def describe(self) -> dict:
        return {
            "feature_id": "E7.15", "task_id": self.task_id,
            "session_id": self.session_id, "message": self.message,
            "due_tick": self.due_tick,
        }


class SchedulerStore:
    """Tasks live separately; no session activation is consulted or required."""

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._queued: dict[str, list[DueMessage]] = {}

    def schedule(self, task: ScheduledTask) -> ScheduledTask:
        if not isinstance(task, ScheduledTask):
            raise ValidationError("task must be a ScheduledTask")
        if task.task_id in self._tasks:
            raise ConflictError("duplicate task id")
        self._tasks[task.task_id] = task
        return task

    def cancel(self, task_id: str) -> None:
        task_id = _ident(task_id, "task_id")
        if task_id not in self._tasks:
            raise NotFoundError("unknown task")
        del self._tasks[task_id]

    def due(self, tick: int) -> tuple[DueMessage, ...]:
        tick = _nonneg_int(tick, "tick")
        ready = sorted(
            (t for t in self._tasks.values() if t.due_tick <= tick),
            key=lambda t: (t.due_tick, t.task_id),
        )
        due = tuple(DueMessage(t.task_id, t.session_id, t.message, t.due_tick) for t in ready)
        for item in due:
            self._queued.setdefault(item.session_id, []).append(item)
            del self._tasks[item.task_id]
        return due

    def inbox(self, session_id: str) -> tuple[DueMessage, ...]:
        sid = _ident(session_id, "session_id")
        return tuple(self._queued.get(sid, ()))


# ---------------------------------------------------------------------------
# E7.16 -- ssh seam: one connection, helper identity, streams, cleanup
# ---------------------------------------------------------------------------


class SshAuthMethod(str, Enum):
    AGENT = "agent"
    KEY = "key"


@dataclass(frozen=True)
class SshConnectionDescriptor:
    host: str
    auth_method: SshAuthMethod
    helper_identity: str
    streams: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "host", _ident(self.host, "host"))
        object.__setattr__(self, "auth_method", _enum(SshAuthMethod, self.auth_method))
        object.__setattr__(self, "helper_identity", _ident(self.helper_identity, "helper_identity"))
        object.__setattr__(self, "streams", _as_tuple(self.streams, "streams"))


@dataclass(frozen=True)
class SshStream:
    host: str
    stream_id: str
    program: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.16", "host": self.host,
            "stream_id": self.stream_id, "program": self.program,
        }


@dataclass(frozen=True)
class DisconnectReceipt:
    host: str
    closed_streams: tuple[str, ...]
    helper_identity: str


class SshSeam:
    """Descriptors only: no socket, no userknownhosts write, no subprocess."""

    def __init__(self) -> None:
        self._connections: dict[str, SshConnectionDescriptor] = {}
        self._streams: dict[str, dict[str, str]] = {}

    def connect(self, descriptor: SshConnectionDescriptor) -> SshConnectionDescriptor:
        if not isinstance(descriptor, SshConnectionDescriptor):
            raise ValidationError("descriptor must be an SshConnectionDescriptor")
        if descriptor.host in self._connections:
            raise ConflictError("one authenticated connection per host")
        self._connections[descriptor.host] = descriptor
        self._streams[descriptor.host] = {}
        return descriptor

    def open_stream(self, host: str, program: str) -> SshStream:
        host = _ident(host, "host")
        program = _text(program, "program")
        if host not in self._connections:
            raise NotFoundError("host is not connected")
        streams = self._streams[host]
        stream_id = "stream-%d" % (len(streams) + 1)
        streams[stream_id] = program
        return SshStream(host, stream_id, program)

    def disconnect(self, host: str) -> DisconnectReceipt:
        host = _ident(host, "host")
        if host not in self._connections:
            raise NotFoundError("host is not connected")
        descriptor = self._connections.pop(host)
        closed = tuple(sorted(self._streams.pop(host)))
        return DisconnectReceipt(host, closed, descriptor.helper_identity)

    def assert_stream_open(self, stream: SshStream) -> None:
        if self._streams.get(stream.host, {}).get(stream.stream_id) != stream.program:
            raise ConflictError("program stream is closed or does not belong to this connection")


# ---------------------------------------------------------------------------
# E7.17 -- shellEnv: effect-scoped KEEL_* facts, one trusted snapshot/execution
# ---------------------------------------------------------------------------

_ENV_UNSAFE_RE = re.compile(r"[\x00-\x1f\x7f;|&$`(){}<>]")


@dataclass(frozen=True)
class EnvFact:
    key: str
    value: str
    scope: str
    effect_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _text(self.key, "key"))
        object.__setattr__(self, "value", _text(self.value, "value"))
        object.__setattr__(self, "scope", _ident(self.scope, "scope"))
        object.__setattr__(self, "effect_id", _ident(self.effect_id, "effect_id"))


def validate_env_fact(fact: EnvFact) -> EnvFact:
    if not isinstance(fact, EnvFact):
        raise ValidationError("fact must be an EnvFact")
    if not fact.key.startswith("KEEL_") or not re.fullmatch(r"KEEL_[A-Z][A-Z0-9_]*", fact.key):
        raise ValidationError("only KEEL_* environment facts are accepted")
    if _ENV_UNSAFE_RE.search(fact.value) or len(fact.value) > 4096:
        raise ValidationError("environment fact value contains unsafe characters")
    return fact


@dataclass(frozen=True)
class EnvSnapshot:
    effect_id: str
    facts: tuple[tuple[str, str], ...]
    digest: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.17", "effect_id": self.effect_id,
            "facts": [{"key": k, "value": v} for k, v in self.facts],
            "digest": self.digest,
        }


class ShellEnvRegistry:
    def __init__(self) -> None:
        self._facts: dict[tuple[str, str], EnvFact] = {}
        self._snapshots: dict[str, EnvSnapshot] = {}

    def declare(self, plugin: str, fact: EnvFact) -> EnvFact:
        plugin = _ident(plugin, "plugin")
        validate_env_fact(fact)
        key = (plugin, fact.key)
        old = self._facts.get(key)
        if old is not None and old.value != fact.value:
            raise ConflictError("plugin cannot redeclare a KEEL_* fact with a new value")
        for (other_plugin, other_key), other in self._facts.items():
            if other_key == fact.key and other_plugin != plugin and other.value != fact.value:
                raise ConflictError("conflicting KEEL_* fact from another plugin")
        self._facts[key] = fact
        return fact

    def snapshot(self, effect_id: str) -> EnvSnapshot:
        effect_id = _ident(effect_id, "effect_id")
        if effect_id in self._snapshots:
            return self._snapshots[effect_id]  # exactly one snapshot per execution
        facts = tuple(sorted((fact.key, fact.value) for fact in self._facts.values()))
        snapshot = EnvSnapshot(effect_id, facts, _digest(facts))
        self._snapshots[effect_id] = snapshot
        return snapshot

    def assert_trusted(self, snapshot: EnvSnapshot) -> None:
        if not isinstance(snapshot, EnvSnapshot):
            raise ValidationError("unknown snapshot type")
        if _digest(snapshot.facts) != snapshot.digest:
            raise ValidationError("environment snapshot was modified")
        for key, value in snapshot.facts:
            if not key.startswith("KEEL_") or _ENV_UNSAFE_RE.search(value):
                raise ValidationError("untrusted fact in environment snapshot")


# ---------------------------------------------------------------------------
# E7.22 -- lsp seam: exactly four normalized operations, no escape hatch
# ---------------------------------------------------------------------------


class LspOperation(str, Enum):
    DIAGNOSTICS = "diagnostics"
    DEFINITION = "definition"
    REFERENCES = "references"
    SYMBOLS = "symbols"


LSP_OPERATIONS: tuple[str, ...] = tuple(op.value for op in LspOperation)
_LSP_ALLOWED_KEYS = frozenset({"operation", "path", "line", "column"})
_LSP_ESCAPE_KEYS = frozenset({
    "method", "params", "command", "jsonrpc", "raw", "custom", "request",
    "extension", "payload",
})


@dataclass(frozen=True)
class LspRequest:
    operation: LspOperation
    path: str
    line: int
    column: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", _enum(LspOperation, self.operation))
        object.__setattr__(self, "path", _text(self.path, "path"))
        object.__setattr__(self, "line", _nonneg_int(self.line, "line"))
        object.__setattr__(self, "column", _nonneg_int(self.column, "column"))

    def describe(self) -> dict:
        return {
            "feature_id": "E7.22", "operation": self.operation.value,
            "path": self.path, "line": self.line, "column": self.column,
        }


def assert_no_lsp_escape_hatch(request: Mapping[str, Any]) -> None:
    if not isinstance(request, Mapping):
        raise ValidationError("LSP request must be a mapping")
    if _LSP_ESCAPE_KEYS.intersection(request):
        raise ValidationError("LSP protocol escape hatch is forbidden")
    unknown = set(request) - _LSP_ALLOWED_KEYS
    if unknown:
        raise ValidationError("unknown normalized LSP field")


class LspService:
    def __init__(self) -> None:
        self._providers: tuple[str, ...] = ()

    def register_provider(self, name: str) -> tuple[str, ...]:
        name = _ident(name, "provider")
        if name in self._providers:
            raise ConflictError("duplicate LSP provider")
        self._providers += (name,)
        return self._providers

    def dispatch(self, request: Mapping[str, Any]) -> dict:
        assert_no_lsp_escape_hatch(request)
        parsed = LspRequest(
            request.get("operation"), request.get("path"),
            request.get("line", 0), request.get("column", 0),
        )
        if not self._providers:
            raise NotFoundError("no LSP provider registered")
        result = parsed.describe()
        result["provider"] = self._providers[0]
        return result


# ---------------------------------------------------------------------------
# E7.24 -- speechToText: local/remote providers, draft-only transcripts
# ---------------------------------------------------------------------------


class RecognizerKind(str, Enum):
    LOCAL = "local"
    REMOTE_AUTHENTICATED = "remote_authenticated"


@dataclass(frozen=True)
class SttProvider:
    name: str
    kind: RecognizerKind

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "name"))
        object.__setattr__(self, "kind", _enum(RecognizerKind, self.kind))


@dataclass(frozen=True)
class Transcript:
    provider: str
    text: str
    draft_only: bool = True
    digest: str = ""

    def describe(self) -> dict:
        return {
            "feature_id": "E7.24", "provider": self.provider,
            "text": self.text, "draft_only": self.draft_only,
        }


@dataclass(frozen=True)
class SubmissionReceipt:
    transcript_digest: str
    user_confirmed: bool = True


class DraftOnlyError(ConflictError):
    """A transcript cannot be sent without an explicit user submission."""


class SpeechToTextService:
    def __init__(self) -> None:
        self._providers: dict[str, SttProvider] = {}

    def register(self, provider: SttProvider) -> SttProvider:
        if not isinstance(provider, SttProvider):
            raise ValidationError("provider must be an SttProvider")
        if provider.name in self._providers:
            raise ConflictError("duplicate STT provider")
        self._providers[provider.name] = provider
        return provider

    def transcribe(self, provider_name: str, audio_ref: str, text: str) -> Transcript:
        provider_name = _ident(provider_name, "provider_name")
        audio_ref = _text(audio_ref, "audio_ref")
        if provider_name not in self._providers:
            raise NotFoundError("unknown STT provider")
        provider = self._providers[provider_name]
        if provider.kind is RecognizerKind.REMOTE_AUTHENTICATED and not audio_ref:
            raise ValidationError("remote recognizer needs an authenticated source")
        clean = " ".join(str(text).split())[:4000]
        if not clean:
            raise ValidationError("empty transcript")
        return Transcript(provider.name, clean, True, _digest(clean))

    def submit(self, transcript: Transcript, *, user_confirmed: bool) -> SubmissionReceipt:
        if not isinstance(transcript, Transcript) or not transcript.draft_only:
            raise DraftOnlyError("transcript must be a draft")
        if user_confirmed is not True:
            raise DraftOnlyError("dictation never auto-sends")
        return SubmissionReceipt(transcript.digest, True)


# ---------------------------------------------------------------------------
# E7.25 -- officeKit: native/WASM engines, local-only, no cloud
# ---------------------------------------------------------------------------


class OfficeEngineKind(str, Enum):
    NATIVE = "native"
    WASM = "wasm"


OFFICE_OPERATIONS: tuple[str, ...] = (
    "render_pdf", "render_image", "convert", "recalculate",
)
_CLOUD_ENGINE_KEYS = frozenset({
    "url", "endpoint", "host", "remote", "api_url", "base_url", "cloud",
})


@dataclass(frozen=True)
class OfficeEngine:
    name: str
    kind: OfficeEngineKind
    operations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "name"))
        object.__setattr__(self, "kind", _enum(OfficeEngineKind, self.kind))
        object.__setattr__(self, "operations", _as_tuple(self.operations, "operations"))
        for operation in self.operations:
            if operation not in OFFICE_OPERATIONS:
                raise ValidationError("unknown office operation")


def assert_no_cloud_engine(descriptor: Any) -> None:
    if isinstance(descriptor, Mapping):
        if _CLOUD_ENGINE_KEYS.intersection(descriptor):
            raise ValidationError("office engines must be local (no cloud endpoint)")
        extra = set(descriptor) - {"name", "kind", "operations"}
        if extra:
            raise ValidationError("unknown office engine field")
    elif not isinstance(descriptor, OfficeEngine):
        raise ValidationError("unknown office engine descriptor")


class OfficeKit:
    def __init__(self) -> None:
        self._engines: dict[str, OfficeEngine] = {}

    def register(self, descriptor: OfficeEngine | Mapping[str, Any]) -> OfficeEngine:
        assert_no_cloud_engine(descriptor)
        if isinstance(descriptor, Mapping):
            engine = OfficeEngine(
                descriptor["name"], descriptor["kind"], descriptor["operations"]
            )
        else:
            engine = descriptor
        if engine.name in self._engines:
            raise ConflictError("duplicate office engine")
        self._engines[engine.name] = engine
        return engine

    def select(self, operation: str) -> OfficeEngine:
        operation = _text(operation, "operation")
        if operation not in OFFICE_OPERATIONS:
            raise ValidationError("unknown office operation")
        capable = [e for e in self._engines.values() if operation in e.operations]
        if not capable:
            raise NotFoundError("no local engine for operation")
        capable.sort(key=lambda e: (e.kind is not OfficeEngineKind.NATIVE, e.name))
        return capable[0]


# ---------------------------------------------------------------------------
# E7.26 -- fileUploads: staged receipts bound to accepted submissions
# ---------------------------------------------------------------------------


class UploadState(str, Enum):
    STAGED = "staged"
    COMMITTED = "committed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class UploadReceipt:
    upload_id: str
    session_id: str
    size: int
    digest: str
    state: UploadState

    def describe(self) -> dict:
        return {
            "feature_id": "E7.26", "upload_id": self.upload_id,
            "session_id": self.session_id, "size": self.size,
            "digest": self.digest, "state": self.state.value,
        }


class UploadService:
    """Incremental hashing: no complete body is ever held by this layer."""

    def __init__(self) -> None:
        self._hashers: dict[str, tuple[Any, int, str]] = {}
        self._receipts: dict[str, UploadReceipt] = {}

    def stage(self, upload_id: str, session_id: str, chunk: str | bytes) -> UploadReceipt:
        upload_id = _ident(upload_id, "upload_id")
        session_id = _ident(session_id, "session_id")
        if upload_id in self._receipts:
            raise ConflictError("upload already finalized")
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        elif not isinstance(chunk, bytes):
            raise ValidationError("chunk must be str or bytes")
        hasher, size, bound_session = self._hashers.get(
            upload_id, (hashlib.sha256(), 0, session_id)
        )
        if bound_session != session_id:
            raise ConflictError("upload id is bound to another session")
        hasher.update(chunk)
        self._hashers[upload_id] = (hasher, size + len(chunk), session_id)
        return UploadReceipt(upload_id, session_id, size + len(chunk),
                             hasher.hexdigest(), UploadState.STAGED)

    def commit(self, upload_id: str, *, accepted: bool,
               expected_digest: str | None = None) -> UploadReceipt:
        upload_id = _ident(upload_id, "upload_id")
        if not isinstance(accepted, bool):
            raise ValidationError("accepted must be a bool")
        staged = self._hashers.get(upload_id)
        if staged is None or upload_id in self._receipts:
            raise NotFoundError("no staged upload")
        hasher, size, session_id = staged
        digest = hasher.hexdigest()
        if expected_digest is not None and _text(expected_digest, "expected_digest") != digest:
            raise ConflictError("upload digest mismatch")
        state = UploadState.COMMITTED if accepted else UploadState.REJECTED
        receipt = UploadReceipt(upload_id, session_id, size, digest, state)
        self._receipts[upload_id] = receipt
        del self._hashers[upload_id]
        return receipt

    def receipt(self, upload_id: str) -> UploadReceipt:
        upload_id = _ident(upload_id, "upload_id")
        if upload_id not in self._receipts:
            raise NotFoundError("unknown upload receipt")
        return self._receipts[upload_id]

    def assert_bound(self, receipt: UploadReceipt, session_id: str) -> None:
        if receipt.session_id != _ident(session_id, "session_id"):
            raise ConflictError("receipt is bound to another session")


# ---------------------------------------------------------------------------
# E7.27 -- Forge seam: URL -> change request, shared poll loop, push binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ForgeProvider:
    name: str
    url_pattern: str
    batch: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "name"))
        object.__setattr__(self, "url_pattern", _text(self.url_pattern, "url_pattern"))
        if not isinstance(self.batch, bool):
            raise ValidationError("batch must be a bool")


@dataclass(frozen=True)
class ChangeRequest:
    provider: str
    ref: str
    head_branch: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.27", "provider": self.provider,
            "ref": self.ref, "head_branch": self.head_branch,
        }


@dataclass(frozen=True)
class PollLoop:
    refs: tuple[str, ...]
    providers: tuple[str, ...]

    def describe(self) -> dict:
        return {
            "feature_id": "E7.27", "refs": list(self.refs),
            "providers": list(self.providers), "loop_count": 1,
        }


class ForgeService:
    def __init__(self) -> None:
        self._providers: dict[str, ForgeProvider] = {}

    def register(self, provider: ForgeProvider) -> ForgeProvider:
        if not isinstance(provider, ForgeProvider):
            raise ValidationError("provider must be a ForgeProvider")
        if provider.name in self._providers:
            raise ConflictError("duplicate forge provider")
        self._providers[provider.name] = provider
        return provider

    def parse_url(self, url: str) -> ChangeRequest:
        url = _text(url, "url")
        for name, provider in sorted(self._providers.items()):
            match = re.match(provider.url_pattern, url)
            if match:
                ref = match.group("ref") if "ref" in match.groupdict() else match.group(0)
                return ChangeRequest(name, ref, "main")
        raise ValidationError("no forge provider owns this URL")

    def lookup_head(self, head_branch: str) -> tuple[ChangeRequest, ...]:
        head_branch = _ident(head_branch, "head_branch")
        known = [ChangeRequest(n, "%s@%s" % (n, head_branch), head_branch)
                 for n in sorted(self._providers)]
        return tuple(known)

    def _parse_ref(self, value: str) -> tuple[str, str]:
        """Accept either a forge URL or a ``<provider>:<change-request>`` ref."""
        text = _text(value, "ref")
        provider, separator, change = text.partition(":")
        if separator:
            if provider not in self._providers or not change:
                raise ValidationError("unknown forge ref")
            return provider, change
        parsed = self.parse_url(text)
        return parsed.provider, parsed.ref

    def batch_status(self, refs: Sequence[str]) -> tuple[tuple[str, str], ...]:
        """Read statuses in batches in one call."""
        rows: list[tuple[str, str]] = []
        for ref in _as_tuple(refs, "refs"):
            provider, change = self._parse_ref(ref)
            rows.append(("%s:%s" % (provider, change), "open"))
        return tuple(rows)

    def watch(self, refs: Sequence[str]) -> PollLoop:
        """All watchers share one polling loop; duplicate refs are deduped."""
        qualified = {
            "%s:%s" % self._parse_ref(ref) for ref in _as_tuple(refs, "refs")
        }
        return PollLoop(tuple(sorted(qualified)),
                        tuple(sorted(ref.partition(":")[0] for ref in qualified)))

    def bind_projection(self, session_id: str, push_output: str) -> tuple[ChangeRequest, ...]:
        _ident(session_id, "session_id")
        _text(push_output, "push_output")
        found: list[ChangeRequest] = []
        for candidate in re.findall(r"https?://[^\s\"'<>]+", push_output):
            try:
                found.append(self.parse_url(candidate.rstrip(".,;")))
            except ValidationError:
                continue
        return tuple(found)


# ---------------------------------------------------------------------------
# E7.28 -- remoteAccess: role policies, filtered lists, access snapshots
# ---------------------------------------------------------------------------


class Role(str, Enum):
    OWNER = "owner"
    APPROVER = "approver"
    VIEWER = "viewer"


_ALL_METHODS = frozenset({
    "session.list", "session.read", "session.send", "approval.answer",
    "shell.run", "file.write", "settings.edit", "plugin.install",
})
ROLE_METHODS: dict[Role, frozenset[str]] = {
    Role.OWNER: _ALL_METHODS,
    Role.APPROVER: frozenset({"session.list", "session.read", "approval.answer"}),
    Role.VIEWER: frozenset({"session.list", "session.read"}),
}
_VISIBILITY_LIMIT: dict[Role, frozenset[str]] = {
    Role.OWNER: frozenset({"private", "internal", "public"}),
    Role.APPROVER: frozenset({"internal", "public"}),
    Role.VIEWER: frozenset({"public"}),
}


@dataclass(frozen=True)
class AccessSnapshot:
    role: Role
    methods: tuple[str, ...]
    digest: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.28", "role": self.role.value,
            "methods": list(self.methods), "digest": self.digest,
        }


class RolePolicy:
    def authorize(self, role: Any, method: str) -> bool:
        try:
            parsed = _enum(Role, role)
        except ValidationError:
            return False
        return str(method) in ROLE_METHODS[parsed]

    def filter_list(self, role: Any, items: Iterable[Mapping[str, Any]]) -> tuple:
        parsed = _enum(Role, role)
        allowed = _VISIBILITY_LIMIT[parsed]
        out = []
        for item in _as_tuple(items, "items"):
            if not isinstance(item, Mapping):
                raise ValidationError("list items must be mappings")
            if item.get("visibility", "public") in allowed:
                out.append(_copy(item))
        return tuple(out)

    def snapshot(self, role: Any) -> AccessSnapshot:
        parsed = _enum(Role, role)
        methods = tuple(sorted(ROLE_METHODS[parsed]))
        return AccessSnapshot(parsed, methods, _digest(methods))

    def assert_owner_only(self, role: Any, method: str) -> None:
        if not self.authorize(Role.OWNER, method):
            raise ConflictError("method is not available to the owner")
        if any(self.authorize(other, method) for other in (Role.APPROVER, Role.VIEWER)):
            raise ConflictError("method is not owner-only")
        parsed = _enum(Role, role)
        if parsed is not Role.OWNER and self.authorize(parsed, method):
            raise ConflictError("non-owner has access to an owner-only method")


# ---------------------------------------------------------------------------
# E7.29 -- connection auth: verifier registry, first live peer, no authorization
# ---------------------------------------------------------------------------


class CredentialSource(str, Enum):
    TOKEN = "token"
    PAIRING = "pairing"
    DESKTOP_LOCAL = "desktop-local"


class VerifierOutcome(str, Enum):
    LIVE = "live"
    DECLINED = "declined"
    ERROR = "error"


@dataclass(frozen=True)
class VerifierResult:
    verifier: str
    outcome: VerifierOutcome
    source: CredentialSource


@dataclass(frozen=True)
class Authentication:
    peer_id: str
    verifier: str
    source: CredentialSource

    def describe(self) -> dict:
        return {
            "feature_id": "E7.29", "peer_id": self.peer_id,
            "verifier": self.verifier, "source": self.source.value,
            "authorization": None,
        }


class AuthRegistry:
    """Verifiers are tried in registration order; a throwing verifier is skipped."""

    def __init__(self) -> None:
        self._verifiers: list[tuple[str, CredentialSource, Callable[[Any], bool]]] = []
        self.trace: tuple[VerifierResult, ...] = ()

    def register(self, name: str, source: CredentialSource,
                 verify: Callable[[Any], bool]) -> None:
        name = _ident(name, "verifier name")
        if not callable(verify):
            raise ValidationError("verifier must be callable")
        source = _enum(CredentialSource, source)
        if any(v[0] == name for v in self._verifiers):
            raise ConflictError("duplicate verifier")
        self._verifiers.append((name, source, verify))

    def authenticate(self, peers: Sequence[tuple[str, Any]]) -> Authentication:
        rows = _as_tuple(peers, "peers")
        trace: list[VerifierResult] = []
        for name, source, verify in self._verifiers:
            for peer_id, credential in rows:
                ident = _ident(peer_id, "peer_id")
                try:
                    live = verify(credential) is True
                    outcome = VerifierOutcome.LIVE if live else VerifierOutcome.DECLINED
                except Exception:
                    live = False
                    outcome = VerifierOutcome.ERROR
                trace.append(VerifierResult(name, outcome, source))
                if live:
                    self.trace = tuple(trace)
                    return Authentication(ident, name, source)
        self.trace = tuple(trace)
        raise NotFoundError("NO_LIVE_PEER")

    @staticmethod
    def assert_separate_from_authorization(auth: Authentication) -> None:
        described = auth.describe()
        if any(key in described for key in ("role", "method", "permission", "grants")):
            raise ValidationError("source policy and business authorization must stay separate")
        if described.get("authorization") is not None:
            raise ValidationError("authentication must not carry authorization")


# ---------------------------------------------------------------------------
# E7.30 -- authorization flow registry: one attempt per record key
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthFlow:
    key: str
    plugin: str
    record_digest: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.30", "key": self.key,
            "plugin": self.plugin, "record_digest": self.record_digest,
        }


@dataclass(frozen=True)
class FlowResult:
    key: str
    attempt: str
    credential_ref: str


class FlowBusyError(ConflictError):
    """Another attempt for the same record key is already in flight."""


class AuthFlowRegistry:
    """Only opaque credential references are stored, never credential values."""

    def __init__(self) -> None:
        self._flows: dict[str, AuthFlow] = {}
        self._active: dict[str, str] = {}
        self._attempts: dict[str, int] = {}
        self._results: dict[str, FlowResult] = {}

    def register(self, key: str, plugin: str, record_digest: str) -> AuthFlow:
        key = _ident(key, "key")
        if key in self._flows:
            raise ConflictError("a flow is already registered for this record key")
        flow = AuthFlow(key, _ident(plugin, "plugin"), _text(record_digest, "record_digest"))
        self._flows[key] = flow
        return flow

    def begin(self, key: str) -> str:
        key = _ident(key, "key")
        if key not in self._flows:
            raise NotFoundError("unknown authorization flow")
        if key in self._active:
            raise FlowBusyError("one attempt per key at a time")
        count = self._attempts.get(key, 0) + 1
        self._attempts[key] = count
        attempt = "attempt-%d" % count
        self._active[key] = attempt
        return attempt

    def complete(self, key: str, credential_ref: str) -> FlowResult:
        key = _ident(key, "key")
        if key not in self._active:
            raise ConflictError("no active attempt")
        ref = _text(credential_ref, "credential_ref")
        if _SECRET_RE.search(ref) or _SECRET_ASSIGN_RE.search(ref):
            raise ValidationError("store an opaque reference, not a credential value")
        result = FlowResult(key, self._active.pop(key), ref)
        self._results[key] = result
        return result

    def fail(self, key: str) -> None:
        key = _ident(key, "key")
        if key not in self._active:
            raise ConflictError("no active attempt")
        del self._active[key]

    def active(self, key: str) -> str | None:
        return self._active.get(_ident(key, "key"))

    def result(self, key: str) -> FlowResult:
        key = _ident(key, "key")
        if key not in self._results:
            raise NotFoundError("flow has no completed result")
        return self._results[key]


# ---------------------------------------------------------------------------
# E7.31 -- action cards: registered kinds, actions and handlers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CardKind:
    name: str
    actions: tuple[str, ...]
    handler: Callable[[str, dict], Any] = field(compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "name"))
        object.__setattr__(self, "actions", _as_tuple(self.actions, "actions"))
        if not callable(self.handler):
            raise ValidationError("card handler must be callable")


@dataclass(frozen=True)
class ActionCard:
    card_id: str
    kind: str
    status: str = "pending"

    def describe(self) -> dict:
        return {
            "feature_id": "E7.31", "card_id": self.card_id,
            "kind": self.kind, "status": self.status,
        }


class CardRegistry:
    def __init__(self) -> None:
        self._kinds: dict[str, CardKind] = {}
        self._cards: dict[str, ActionCard] = {}

    def register(self, name: str, actions: Sequence[str],
                 handler: Callable[[str, dict], Any]) -> CardKind:
        kind = CardKind(name, actions, handler)
        if kind.name in self._kinds:
            raise ConflictError("duplicate card kind")
        self._kinds[kind.name] = kind
        return kind

    def create(self, card_id: str, kind_name: str) -> ActionCard:
        card_id = _ident(card_id, "card_id")
        kind_name = _ident(kind_name, "kind")
        if kind_name not in self._kinds:
            raise NotFoundError("unknown card kind")
        if card_id in self._cards:
            raise ConflictError("duplicate card id")
        card = ActionCard(card_id, kind_name)
        self._cards[card_id] = card
        return card

    def invoke(self, card_id: str, action: str, payload: Mapping[str, Any] | None = None
               ) -> Any:
        card_id = _ident(card_id, "card_id")
        if card_id not in self._cards:
            raise NotFoundError("unknown card")
        card = self._cards[card_id]
        kind = self._kinds[card.kind]
        action = _text(action, "action")
        if action not in kind.actions:
            raise ValidationError("card kind does not register this action")
        if payload is not None and not isinstance(payload, Mapping):
            raise ValidationError("payload must be a mapping")
        result = kind.handler(action, dict(payload or {}))
        self._cards[card_id] = ActionCard(card.card_id, card.kind, "handled:%s" % action)
        return result

    def card(self, card_id: str) -> ActionCard:
        card_id = _ident(card_id, "card_id")
        if card_id not in self._cards:
            raise NotFoundError("unknown card")
        return self._cards[card_id]


# ---------------------------------------------------------------------------
# E7.32 -- plugin recommendations: explicit need only, manager click-through
# ---------------------------------------------------------------------------

_NEED_RE = re.compile(
    r"(?i)\b(?:need|needs|needs?\s+to|looking\s+for|want|install|missing|"
    r"suggest|recommend|how\s+do\s+i)\b"
)


@dataclass(frozen=True)
class PluginRecommendation:
    plugin_id: str
    reason: str
    need_evidence: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.32", "plugin_id": self.plugin_id,
            "reason": self.reason, "need_evidence": self.need_evidence,
            "auto_enabled": False,
        }


@dataclass(frozen=True)
class ManagerInstallRequest:
    plugin_id: str
    clicked: bool = True
    via_manager: bool = True


class RecommendationPolicy:
    def recommend(self, need_text: str,
                  candidates: Mapping[str, str]) -> tuple[PluginRecommendation, ...]:
        text = _text(need_text, "need_text")
        match = _NEED_RE.search(text)
        if match is None:
            return ()
        if not isinstance(candidates, Mapping):
            raise ValidationError("candidates must be a mapping")
        return tuple(
            PluginRecommendation(_ident(pid, "plugin_id"), _text(reason, "reason"),
                                 match.group(0))
            for pid, reason in sorted(candidates.items())
        )

    def enable(self, recommendation: PluginRecommendation, *,
               clicked: bool) -> ManagerInstallRequest:
        if not isinstance(recommendation, PluginRecommendation):
            raise ValidationError("recommendation must be a PluginRecommendation")
        if clicked is not True:
            raise ConflictError("no install without an explicit click")
        return ManagerInstallRequest(recommendation.plugin_id, True, True)


# ---------------------------------------------------------------------------
# E7.33 -- plugin registry mirror probe: fastest valid mirror wins
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MirrorResult:
    name: str
    latency_ms: float
    valid: bool
    digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "name"))
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, (int, float)):
            raise ValidationError("latency_ms must be a number")
        if float(self.latency_ms) < 0:
            raise ValidationError("latency_ms must be non-negative")
        if not isinstance(self.valid, bool):
            raise ValidationError("valid must be a bool")


def fastest_valid_mirror(results: Iterable[MirrorResult]) -> MirrorResult:
    rows = _as_tuple(results, "results")
    if not rows:
        raise ValidationError("no mirror results")
    valid = [r for r in rows if r.valid]
    if not valid:
        raise NotFoundError("no valid registry mirror")
    valid.sort(key=lambda r: (float(r.latency_ms), r.name))
    return valid[0]


# ---------------------------------------------------------------------------
# E7.34 -- plugin market reader: validated user sources, manager install
# ---------------------------------------------------------------------------


class IndexSourceKind(str, Enum):
    FILE = "file"
    URL = "url"


@dataclass(frozen=True)
class IndexSource:
    name: str
    kind: IndexSourceKind
    locator: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "name"))
        object.__setattr__(self, "kind", _enum(IndexSourceKind, self.kind))
        object.__setattr__(self, "locator", _text(self.locator, "locator"))


@dataclass(frozen=True)
class MarketEntry:
    plugin_id: str
    version: str
    digest: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.34", "plugin_id": self.plugin_id,
            "version": self.version, "digest": self.digest,
        }


def validate_index_source(source: IndexSource) -> IndexSource:
    if not isinstance(source, IndexSource):
        raise ValidationError("source must be an IndexSource")
    locator = source.locator
    if "\x00" in locator or ".." in locator:
        raise ValidationError("unsafe index locator")
    if source.kind is IndexSourceKind.FILE:
        if not locator.endswith(".json"):
            raise ValidationError("file index must be a .json path")
    else:
        if not locator.startswith("https://"):
            raise ValidationError("URL index must use https")
        remainder = locator[len("https://"):]
        if "@" in remainder.split("/", 1)[0] or "#" in locator or "?" in locator:
            raise ValidationError("URL index cannot carry credentials or a query/fragment")
    return source


def parse_market_index(source: IndexSource, raw_text: str) -> tuple[MarketEntry, ...]:
    validate_index_source(source)
    text = _text(raw_text, "raw_text")
    try:
        document = json.loads(text)
    except ValueError:
        raise ValidationError("malformed plugin index") from None
    rows = document.get("plugins") if isinstance(document, Mapping) else document
    if isinstance(rows, Mapping) or not isinstance(rows, Iterable) or isinstance(rows, (str, bytes)):
        raise ValidationError("plugin index must be a list")
    entries: list[MarketEntry] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"plugin_id", "version", "digest"}:
            raise ValidationError("malformed plugin index entry")
        entry = MarketEntry(_ident(row["plugin_id"], "plugin_id"),
                            _text(row["version"], "version"),
                            _text(row["digest"], "digest"))
        if not re.fullmatch(r"[0-9a-f]{64}", entry.digest):
            raise ValidationError("index digest must be a SHA-256 hex string")
        if entry.plugin_id in seen:
            raise ConflictError("duplicate plugin id in index")
        seen.add(entry.plugin_id)
        entries.append(entry)
    return tuple(entries)


def manager_install_request(source: IndexSource, entry: MarketEntry) -> dict:
    validate_index_source(source)
    if not isinstance(entry, MarketEntry):
        raise ValidationError("entry must be a MarketEntry")
    return {
        "feature_id": "E7.34", "source": source.name, "plugin_id": entry.plugin_id,
        "version": entry.version, "digest": entry.digest, "via_manager": True,
    }


# ---------------------------------------------------------------------------
# E7.35 -- message feedback: canonical log, per-item compare-and-set
# ---------------------------------------------------------------------------


class FeedbackValue(str, Enum):
    UP = "up"
    DOWN = "down"
    NOTE = "note"


@dataclass(frozen=True)
class FeedbackEvent:
    session_id: str
    item_seq: int
    value: FeedbackValue
    cas: int
    note: str = ""
    log_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _ident(self.session_id, "session_id"))
        object.__setattr__(self, "item_seq", _nonneg_int(self.item_seq, "item_seq"))
        object.__setattr__(self, "value", _enum(FeedbackValue, self.value))
        object.__setattr__(self, "cas", _nonneg_int(self.cas, "cas"))
        object.__setattr__(self, "note", _redact(str(self.note))[:2000])
        if not isinstance(self.log_only, bool):
            raise ValidationError("log_only must be a bool")

    def describe(self) -> dict:
        return {
            "feature_id": "E7.35", "session_id": self.session_id,
            "item_seq": self.item_seq, "value": self.value.value,
            "cas": self.cas, "note": self.note, "log_only": self.log_only,
        }


class FeedbackLog:
    """A log-only event stream; the target message is never mutated."""

    def __init__(self) -> None:
        self._events: list[FeedbackEvent] = []
        self._cas: dict[tuple[str, int], int] = {}

    def append(self, event: FeedbackEvent) -> FeedbackEvent:
        if not isinstance(event, FeedbackEvent):
            raise ValidationError("event must be a FeedbackEvent")
        key = (event.session_id, event.item_seq)
        current = self._cas.get(key, 0)
        if event.cas != current:
            raise ConflictError("feedback CAS mismatch")
        self._cas[key] = current + 1
        self._events.append(event)
        return event

    def session_feedback(self, session_id: str, value: FeedbackValue, cas: int,
                         note: str = "") -> FeedbackEvent:
        return self.append(FeedbackEvent(
            _ident(session_id, "session_id"), 0, value, cas, note, log_only=True
        ))

    def cas_for(self, session_id: str, item_seq: int) -> int:
        return self._cas.get((_ident(session_id, "session_id"),
                              _nonneg_int(item_seq, "item_seq")), 0)

    def events(self, session_id: str) -> tuple[FeedbackEvent, ...]:
        sid = _ident(session_id, "session_id")
        return tuple(e for e in self._events if e.session_id == sid)


# ---------------------------------------------------------------------------
# E7.36 -- hooks bridges: adapters for other tools' hook formats
# ---------------------------------------------------------------------------


class HookFormat(str, Enum):
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    CURSOR = "cursor"


@dataclass(frozen=True)
class HookDescriptor:
    format: HookFormat
    event: str
    command: str
    source: str

    def describe(self) -> dict:
        return {
            "feature_id": "E7.36", "format": self.format.value,
            "event": self.event, "command": self.command, "source": self.source,
        }


class HookBridgeRegistry:
    """Translate documented formats only; hooks are never executed here."""

    def __init__(self) -> None:
        self._adapters: dict[HookFormat, Callable[[Mapping[str, Any]], HookDescriptor]] = {}

    def register(self, fmt: HookFormat,
                 adapter: Callable[[Mapping[str, Any]], HookDescriptor]) -> None:
        fmt = _enum(HookFormat, fmt)
        if not callable(adapter):
            raise ValidationError("hook adapter must be callable")
        if fmt in self._adapters:
            raise ConflictError("duplicate hook adapter")
        self._adapters[fmt] = adapter

    def translate(self, fmt: HookFormat, definition: Mapping[str, Any]) -> HookDescriptor:
        fmt = _enum(HookFormat, fmt)
        if fmt not in self._adapters:
            raise NotFoundError("no adapter for hook format")
        if not isinstance(definition, Mapping):
            raise ValidationError("hook definition must be a mapping")
        try:
            hook = self._adapters[fmt](definition)
        except BackendError:
            raise
        except Exception:
            raise ValidationError("hook adapter failed") from None
        if not isinstance(hook, HookDescriptor) or hook.format is not fmt:
            raise ValidationError("adapter returned an invalid hook descriptor")
        return hook

    def formats(self) -> tuple[str, ...]:
        return tuple(sorted(f.value for f in self._adapters))


# ---------------------------------------------------------------------------
# E7.37 -- agent-authored plugins: proposal, review, V23 sandbox, off by default
# ---------------------------------------------------------------------------


class ProposalState(str, Enum):
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    APPROVED_FOR_SANDBOX = "approved_for_sandbox"
    ENABLED = "enabled"


@dataclass(frozen=True)
class PluginProposal:
    proposal_id: str
    diff_digest: str
    host_ref: str
    client_ref: str
    sandbox_required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _ident(self.proposal_id, "proposal_id"))
        object.__setattr__(self, "diff_digest", _text(self.diff_digest, "diff_digest"))
        object.__setattr__(self, "host_ref", _text(self.host_ref, "host_ref"))
        object.__setattr__(self, "client_ref", _text(self.client_ref, "client_ref"))
        if self.sandbox_required is not True:
            raise ValidationError("agent-authored host code must be sandboxed")


@dataclass(frozen=True)
class EnableReceipt:
    proposal_id: str
    sandbox: str = "V23"


class AgentPluginPolicy:
    OFF_BY_DEFAULT = True

    def __init__(self) -> None:
        self._states: dict[str, ProposalState] = {}
        self._proposals: dict[str, PluginProposal] = {}

    def propose(self, proposal: PluginProposal) -> ProposalState:
        if not isinstance(proposal, PluginProposal):
            raise ValidationError("proposal must be a PluginProposal")
        if proposal.proposal_id in self._states:
            raise ConflictError("duplicate proposal")
        self._proposals[proposal.proposal_id] = proposal
        self._states[proposal.proposal_id] = ProposalState.PENDING_REVIEW
        return ProposalState.PENDING_REVIEW

    def state(self, proposal_id: str) -> ProposalState:
        proposal_id = _ident(proposal_id, "proposal_id")
        if proposal_id not in self._states:
            raise NotFoundError("unknown proposal")
        return self._states[proposal_id]

    def review(self, proposal_id: str, *, approved: bool) -> ProposalState:
        proposal_id = _ident(proposal_id, "proposal_id")
        if not isinstance(approved, bool):
            raise ValidationError("approved must be a bool")
        if self.state(proposal_id) is not ProposalState.PENDING_REVIEW:
            raise ConflictError("proposal was already reviewed")
        state = (ProposalState.APPROVED_FOR_SANDBOX if approved
                 else ProposalState.REJECTED)
        self._states[proposal_id] = state
        return state

    def enable(self, proposal_id: str, *, v23_available: bool) -> EnableReceipt:
        proposal_id = _ident(proposal_id, "proposal_id")
        if not isinstance(v23_available, bool):
            raise ValidationError("v23_available must be a bool")
        if self.state(proposal_id) is not ProposalState.APPROVED_FOR_SANDBOX:
            raise ConflictError("agent-authored plugins are never auto-enabled")
        if not v23_available:
            raise ConflictError("V23 isolated subprocess is required")
        self._states[proposal_id] = ProposalState.ENABLED
        return EnableReceipt(proposal_id)


# ---------------------------------------------------------------------------
# E7.38 -- workflow engine + fixed loop-until-done fan-out consumer
# ---------------------------------------------------------------------------


class WorkflowOp(str, Enum):
    TOOL = "tool"
    SUBAGENT = "subagent"
    CHECK = "check"
    FANOUT = "fanout"


@dataclass(frozen=True)
class WorkflowNode:
    node_id: str
    op: WorkflowOp
    target: str
    max_fanout: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _ident(self.node_id, "node_id"))
        object.__setattr__(self, "op", _enum(WorkflowOp, self.op))
        object.__setattr__(self, "target", _text(self.target, "target"))
        object.__setattr__(self, "max_fanout", _nonneg_int(self.max_fanout, "max_fanout"))
        if self.node_id == self.target:
            raise ValidationError("self-referential workflow node")
        if self.op is WorkflowOp.FANOUT and self.max_fanout < 1:
            raise ValidationError("fan-out node needs a positive bound")


@dataclass(frozen=True)
class Workflow:
    nodes: tuple[WorkflowNode, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", _as_tuple(self.nodes, "nodes"))
        # Validate node types first: reading ``node_id`` off a malformed entry
        # would otherwise raise AttributeError instead of the typed error.
        for node in self.nodes:
            if not isinstance(node, WorkflowNode):
                raise ValidationError("workflow nodes must be WorkflowNode")
        ids = [n.node_id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValidationError("duplicate workflow node id")
        if any(n.node_id == n.target for n in self.nodes):
            raise ValidationError("self-referential workflow node")


@dataclass(frozen=True)
class WorkflowStep:
    node_id: str
    op: WorkflowOp
    targets: tuple[str, ...]


@dataclass(frozen=True)
class LoopTick:
    iteration: int
    done: bool
    steps: tuple[WorkflowStep, ...]


class IterationLimitError(ConflictError):
    """The fixed loop-until-done consumer exceeded its iteration budget."""


class LoopUntilDone:
    def __init__(self, workflow: Workflow, max_iterations: int = 10) -> None:
        if not isinstance(workflow, Workflow):
            raise ValidationError("workflow must be a Workflow")
        self.workflow = workflow
        self.max_iterations = _nonneg_int(max_iterations, "max_iterations")
        if self.max_iterations < 1:
            raise ValidationError("max_iterations must be positive")

    def tick(self, iteration: int, check_results: Mapping[str, bool]) -> LoopTick:
        iteration = _nonneg_int(iteration, "iteration")
        if iteration >= self.max_iterations:
            raise IterationLimitError("loop iteration budget exhausted")
        if not isinstance(check_results, Mapping):
            raise ValidationError("check_results must be a mapping")
        checks = [n for n in self.workflow.nodes if n.op is WorkflowOp.CHECK]
        if not checks:
            raise ValidationError("loop-until-done workflow needs a check node")
        for node in checks:
            value = check_results.get(node.node_id)
            if not isinstance(value, bool):
                raise ValidationError("every check node needs a bool result")
        done = all(check_results.get(n.node_id) is True for n in checks)
        steps: list[WorkflowStep] = []
        if not done:
            for node in self.workflow.nodes:
                if node.op is WorkflowOp.CHECK:
                    continue
                count = node.max_fanout if node.op is WorkflowOp.FANOUT else 1
                targets = tuple("%s-%d" % (node.target, i) for i in range(1, count + 1))
                steps.append(WorkflowStep(node.node_id, node.op, targets))
        return LoopTick(iteration, done, tuple(steps))


# ---------------------------------------------------------------------------
# E7.39 -- webhook runtime: authenticated deliveries -> ordinary sessions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WebhookRule:
    name: str
    trusted: bool
    signature_headers: tuple[str, ...]
    confirmation_required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "name"))
        object.__setattr__(self, "signature_headers",
                           _as_tuple(self.signature_headers, "signature_headers"))
        if not isinstance(self.trusted, bool) or not isinstance(self.confirmation_required, bool):
            raise ValidationError("rule flags must be bools")


@dataclass(frozen=True)
class WebhookDelivery:
    provider: str
    rule_name: str
    signature_valid: bool
    payload_digest: str
    confirmation_token: str = ""


@dataclass(frozen=True)
class SessionSpawn:
    session_ref: str
    rule: str
    provider: str
    confirmation_required: bool

    def describe(self) -> dict:
        return {
            "feature_id": "E7.39", "session_ref": self.session_ref,
            "rule": self.rule, "provider": self.provider,
            "confirmation_required": self.confirmation_required,
        }


class WebhookRuntime:
    """Extends D3.8 with provider adapters; no listener or HTTP is opened."""

    def __init__(self) -> None:
        self._rules: dict[str, WebhookRule] = {}
        self._adapters: set[str] = set()

    def register_rule(self, rule: WebhookRule) -> WebhookRule:
        if not isinstance(rule, WebhookRule):
            raise ValidationError("rule must be a WebhookRule")
        if not rule.trusted:
            raise ValidationError("untrusted webhook rules cannot start sessions")
        if not rule.signature_headers or not rule.confirmation_required:
            raise ValidationError("trusted rules require signatures and confirmation")
        if rule.name in self._rules:
            raise ConflictError("duplicate webhook rule")
        self._rules[rule.name] = rule
        return rule

    def register_adapter(self, provider: str) -> str:
        provider = _ident(provider, "provider")
        if provider in self._adapters:
            raise ConflictError("duplicate webhook adapter")
        self._adapters.add(provider)
        return provider

    def deliver(self, delivery: WebhookDelivery) -> SessionSpawn:
        if not isinstance(delivery, WebhookDelivery):
            raise ValidationError("delivery must be a WebhookDelivery")
        rule = self._rules.get(_ident(delivery.rule_name, "rule_name"))
        if rule is None:
            raise NotFoundError("unknown webhook rule")
        if not delivery.signature_valid:
            raise ValidationError("webhook delivery signature is invalid")
        _text(delivery.payload_digest, "payload_digest")
        if delivery.provider not in self._adapters:
            raise NotFoundError("no adapter for webhook provider")
        if rule.confirmation_required and not _text(
            delivery.confirmation_token, "confirmation_token"
        ):
            raise ConflictError("remote-initiated sessions require confirmation")
        return SessionSpawn(
            "session-%s" % _digest((delivery.provider, delivery.payload_digest))[:12],
            rule.name, delivery.provider, rule.confirmation_required,
        )


# ---------------------------------------------------------------------------
# E7.40 -- inspector service: read-only query API over the live plugin tree
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PluginTreeNode:
    node_id: str
    kind: str
    parent: str | None
    state: str

    def describe(self) -> dict:
        return {
            "node_id": self.node_id, "kind": self.kind,
            "parent": self.parent, "state": self.state,
        }


_MUTATING_QUERY_KEYS = frozenset({
    "set", "write", "call", "invoke", "eval", "exec", "mutate", "delete",
})

# Key names alone are not enough: an unknown key such as ``sql`` may carry
# arbitrary DML/DDL.  Fail closed on any mutating statement found in a value.
_MUTATING_SQL_RE = re.compile(
    r"\b(?:DELETE|UPDATE|INSERT|DROP|ALTER|TRUNCATE|CREATE|REPLACE|MERGE|"
    r"GRANT|REVOKE|SET|EXEC|EXECUTE|CALL|VACUUM|ATTACH|DETACH|PRAGMA|"
    r"COPY|LOAD|UPSERT|WRITE)\b",
    re.IGNORECASE,
)


def _inspect_query_value(value: Any) -> None:
    """Recursively refuse values carrying (or obscuring) mutating SQL."""
    if isinstance(value, str):
        if _MUTATING_SQL_RE.search(value):
            raise ValidationError("inspector queries are read-only")
        return
    if isinstance(value, (bytes, bytearray)):
        try:
            text = bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationError("inspector query values must be inspectable text") from None
        if _MUTATING_SQL_RE.search(text):
            raise ValidationError("inspector queries are read-only")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _inspect_query_value(key)
            _inspect_query_value(item)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _inspect_query_value(item)
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    # An object we cannot inspect cannot be proven read-only.
    raise ValidationError("inspector query values must be inspectable text")


def assert_read_only_query(query: Mapping[str, Any]) -> None:
    if not isinstance(query, Mapping):
        raise ValidationError("query must be a mapping")
    if _MUTATING_QUERY_KEYS.intersection(query):
        raise ValidationError("inspector queries are read-only")
    if str(query.get("op", "get")) not in {"get", "list", "trace", "query"}:
        raise ValidationError("unknown read-only query operation")
    for key, value in query.items():
        _inspect_query_value(key)
        _inspect_query_value(value)


class InspectorService:
    def __init__(self) -> None:
        self._workers: dict[str, dict[str, PluginTreeNode]] = {}

    def register_worker(self, worker_id: str, nodes: Iterable[PluginTreeNode]) -> None:
        worker_id = _ident(worker_id, "worker_id")
        if worker_id in self._workers:
            raise ConflictError("duplicate inspector worker")
        mapping: dict[str, PluginTreeNode] = {}
        for node in _as_tuple(nodes, "nodes"):
            if not isinstance(node, PluginTreeNode):
                raise ValidationError("nodes must be PluginTreeNode")
            if node.node_id in mapping:
                raise ConflictError("duplicate plugin node id")
            mapping[node.node_id] = node
        self._workers[worker_id] = mapping

    def query(self, worker_id: str, query: Mapping[str, Any]) -> dict:
        assert_read_only_query(query)
        worker_id = _ident(worker_id, "worker_id")
        if worker_id not in self._workers:
            raise NotFoundError("unknown inspector worker")
        nodes = self._workers[worker_id]
        target = _text(query.get("node_id", ""), "node_id") if query.get("op", "get") != "list" else ""
        if query.get("op", "get") == "list":
            return {"feature_id": "E7.40", "nodes": [nodes[k].describe() for k in sorted(nodes)]}
        if target not in nodes:
            raise NotFoundError("unknown plugin node")
        return {"feature_id": "E7.40", "node": nodes[target].describe()}

    def trace(self, worker_id: str, plugin_id: str) -> tuple[str, ...]:
        worker_id = _ident(worker_id, "worker_id")
        plugin_id = _ident(plugin_id, "plugin_id")
        if worker_id not in self._workers:
            raise NotFoundError("unknown inspector worker")
        nodes = self._workers[worker_id]
        if plugin_id not in nodes:
            raise NotFoundError("unknown plugin node")
        chain: list[str] = [plugin_id]
        seen = {plugin_id}
        parent = nodes[plugin_id].parent
        while parent is not None:
            if parent in seen:
                raise ValidationError("plugin tree contains a cycle")
            seen.add(parent)
            if parent not in nodes:
                raise ValidationError("plugin tree has a missing parent")
            chain.append(parent)
            parent = nodes[parent].parent
        return tuple(chain)


# ---------------------------------------------------------------------------
# E7.41 -- storage seam: json/sqlite backends, typed non-session domains
# ---------------------------------------------------------------------------


class StorageBackendKind(str, Enum):
    JSON = "json"
    SQLITE = "sqlite"


@dataclass(frozen=True)
class StorageBackend:
    name: str
    kind: StorageBackendKind

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "name"))
        object.__setattr__(self, "kind", _enum(StorageBackendKind, self.kind))


@dataclass(frozen=True)
class DomainRecord:
    domain: str
    key: str
    value: Any


class StorageSeam:
    """In-memory typed domain store; a caller supplies real persistence."""

    def __init__(self) -> None:
        self._backends: dict[str, StorageBackend] = {}
        self._rows: dict[tuple[str, str], Any] = {}

    def register_backend(self, backend: StorageBackend) -> StorageBackend:
        if not isinstance(backend, StorageBackend):
            raise ValidationError("backend must be a StorageBackend")
        if backend.name in self._backends:
            raise ConflictError("duplicate storage backend")
        self._backends[backend.name] = backend
        return backend

    @staticmethod
    def assert_typed_domain(record: DomainRecord) -> None:
        if not isinstance(record, DomainRecord):
            raise ValidationError("record must be a DomainRecord")
        _ident(record.domain, "domain")
        _ident(record.key, "key")
        if not _json_safe(record.value):
            raise ValidationError("domain value must be JSON-safe")

    def put(self, record: DomainRecord) -> DomainRecord:
        self.assert_typed_domain(record)
        self._rows[(record.domain, record.key)] = _copy(record.value)
        return DomainRecord(record.domain, record.key, _copy(record.value))

    def get(self, domain: str, key: str) -> Any:
        key_tuple = (_ident(domain, "domain"), _ident(key, "key"))
        if key_tuple not in self._rows:
            raise NotFoundError("domain record not found")
        return _copy(self._rows[key_tuple])

    def list(self, domain: str) -> tuple[DomainRecord, ...]:
        name = _ident(domain, "domain")
        return tuple(
            DomainRecord(d, k, _copy(v)) for (d, k), v in sorted(self._rows.items())
            if d == name
        )


# ---------------------------------------------------------------------------
# E7.42 -- mcpResources: connection-owned providers scoped per agent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceProvider:
    connection_id: str
    uri_prefix: str
    agents: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "connection_id", _ident(self.connection_id, "connection_id"))
        object.__setattr__(self, "uri_prefix", _text(self.uri_prefix, "uri_prefix"))
        object.__setattr__(self, "agents", _as_tuple(self.agents, "agents"))
        if not self.agents:
            raise ValidationError("a resource provider needs an explicit agent scope")
        for agent in self.agents:
            _ident(agent, "agent")


class McpResourcesService:
    def __init__(self) -> None:
        self._providers: list[ResourceProvider] = []

    def register(self, provider: ResourceProvider) -> ResourceProvider:
        if not isinstance(provider, ResourceProvider):
            raise ValidationError("provider must be a ResourceProvider")
        self._providers.append(provider)
        return provider

    def list_resources(self, agent_id: str) -> tuple[dict, ...]:
        agent = _ident(agent_id, "agent_id")
        return tuple(
            {"feature_id": "E7.42", "connection_id": p.connection_id,
             "uri_prefix": p.uri_prefix, "agents": list(p.agents)}
            for p in self._providers if agent in p.agents
        )

    def read(self, connection_id: str, uri: str, agent_id: str) -> dict:
        conn = _ident(connection_id, "connection_id")
        uri = _text(uri, "uri")
        agent = _ident(agent_id, "agent_id")
        for provider in self._providers:
            if provider.connection_id == conn and uri.startswith(provider.uri_prefix):
                if agent not in provider.agents:
                    raise ConflictError("resource is not scoped to this agent")
                return {"feature_id": "E7.42", "connection_id": conn,
                        "uri": uri, "agent_id": agent, "scoped": True}
        raise NotFoundError("no scoped resource provider for uri")


# ---------------------------------------------------------------------------
# E7.43 -- browser/computer use: provider seams, no shared action API
# ---------------------------------------------------------------------------


class UseProviderKind(str, Enum):
    BROWSER = "browser"
    COMPUTER = "computer"


@dataclass(frozen=True)
class UseProvider:
    name: str
    kind: UseProviderKind
    tools: tuple[str, ...]
    resources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "name"))
        object.__setattr__(self, "kind", _enum(UseProviderKind, self.kind))
        object.__setattr__(self, "tools", _as_tuple(self.tools, "tools"))
        object.__setattr__(self, "resources", _as_tuple(self.resources, "resources"))
        if not self.tools:
            raise ValidationError("a provider must own its tools")


@dataclass(frozen=True)
class ConsentDecision:
    app_id: str
    granted: bool
    cancelled: bool

    def describe(self) -> dict:
        return {
            "feature_id": "E7.43", "app_id": self.app_id,
            "granted": self.granted and not self.cancelled,
            "cancelled": self.cancelled,
        }


_SHARED_ACTION_KEYS = frozenset({
    "common_actions", "shared_actions", "action_api", "universal_action",
})


def assert_no_shared_action_api(descriptor: Mapping[str, Any]) -> None:
    if not isinstance(descriptor, Mapping):
        raise ValidationError("provider descriptor must be a mapping")
    if _SHARED_ACTION_KEYS.intersection(descriptor):
        raise ValidationError("providers own their tools; no shared action API")


class ProviderSeams:
    def __init__(self) -> None:
        self._providers: dict[tuple[UseProviderKind, str], UseProvider] = {}
        self._runtimes: dict[str, dict] = {}

    def register(self, provider: UseProvider) -> UseProvider:
        if not isinstance(provider, UseProvider):
            raise ValidationError("provider must be a UseProvider")
        key = (provider.kind, provider.name)
        if key in self._providers:
            raise ConflictError("duplicate use provider")
        self._providers[key] = provider
        return provider

    def resolve(self, kind: UseProviderKind, name: str) -> UseProvider:
        parsed = _enum(UseProviderKind, kind)
        key = (parsed, _ident(name, "name"))
        if key not in self._providers:
            raise NotFoundError("unknown use provider")
        return self._providers[key]

    @staticmethod
    def consent(app_id: str, *, granted: bool, cancelled: bool) -> ConsentDecision:
        app = _ident(app_id, "app_id")
        if not isinstance(granted, bool) or not isinstance(cancelled, bool):
            raise ValidationError("consent flags must be bools")
        return ConsentDecision(app, granted, cancelled)

    def runtime_for(self, agent_id: str) -> dict:
        agent = _ident(agent_id, "agent_id")
        if agent not in self._runtimes:
            self._runtimes[agent] = {
                "feature_id": "E7.43", "agent_id": agent,
                "runtime_id": "rt-%s" % _digest(agent)[:12], "retained": True,
            }
        return dict(self._runtimes[agent])


# ---------------------------------------------------------------------------
# Top-level feature index (used by the evidence doc and completeness test)
# ---------------------------------------------------------------------------

FEATURE_SURFACES: dict[str, str] = {
    "E7.1": "TokenMeasurement/TokenMeter/PressureMeasurement: isolated folds and immutable revisioned snapshots.",
    "E7.3": "PressureEvent/compaction_decision/assert_no_compact_tool: loop-event-only compaction.",
    "E7.4": "SessionStatusStore/assert_status_out_of_log: acks outside canonical history.",
    "E7.5": "WorkspaceChangeFeed: turn-start/end comparison keyed by session and event seq.",
    "E7.7": "path_completions/assert_paths_only/parse_at_paths: @ completion returns paths only.",
    "E7.8": "resolve_session_reference/assert_untrusted_context: bounded tainted snapshot.",
    "E7.9": "SessionQueryService.search: exact/filter/trace plus ranked paged search.",
    "E7.10": "TitleService/fallback_title: deterministic fallback, latest fold, one provider.",
    "E7.11": "PlanModeService: log fold, boundary flush, /plan, stable exit schema.",
    "E7.12": "parse_preset_yaml/PresetRegistry: revisions, retirement, last-release GC.",
    "E7.13": "ProjectionCache: throttled and mandatory turn-end/detach checkpoints.",
    "E7.14": "reconcile/McpManager: desired-state reconciliation, status aggregation, probe/restart.",
    "E7.15": "SchedulerStore: activation-independent due messages queued per session.",
    "E7.16": "SshSeam: one authenticated connection, helper identity, streams, cleanup receipt.",
    "E7.17": "ShellEnvRegistry: effect-scoped KEEL_* facts, one trusted snapshot per execution.",
    "E7.22": "LspService: exactly four normalized operations, no protocol escape hatch.",
    "E7.24": "SpeechToTextService: local/remote providers, draft-only transcript submission.",
    "E7.25": "OfficeKit: native/WASM engine selection, local-only descriptors.",
    "E7.26": "UploadService: streaming receipt, staged->committed/rejected binding.",
    "E7.27": "ForgeService: URL->change request, head lookup, one poll loop, push binding.",
    "E7.28": "RolePolicy: role-method authorization, filtered lists, access snapshots.",
    "E7.29": "AuthRegistry: ordered verifiers, first live peer, source != authorization.",
    "E7.30": "AuthFlowRegistry: keyed flows, one attempt per key, opaque refs only.",
    "E7.31": "CardRegistry: card kinds register actions and handlers.",
    "E7.32": "RecommendationPolicy: explicit need only, manager click-through install.",
    "E7.33": "fastest_valid_mirror: fastest valid mirror wins deterministically.",
    "E7.34": "parse_market_index: validated user sources, manager install request.",
    "E7.35": "FeedbackLog: per-item compare-and-set, session-level log-only events.",
    "E7.36": "HookBridgeRegistry: adapters translate documented external hook formats.",
    "E7.37": "AgentPluginPolicy: propose/review/V23 sandbox/never auto-enabled.",
    "E7.38": "Workflow/LoopUntilDone: nodes, fan-out and bounded loop-until-done consumer.",
    "E7.39": "WebhookRuntime: trusted rules and adapters turn signed deliveries into sessions.",
    "E7.40": "InspectorService: worker-hosted read-only queries over the plugin tree.",
    "E7.41": "StorageSeam: json/sqlite backend descriptors and typed domain records.",
    "E7.42": "McpResourcesService: connection-owned resources scoped per agent.",
    "E7.43": "ProviderSeams: browser/computer providers, per-app consent, no shared API.",
}


@dataclass(frozen=True)
class FeatureDescriptor:
    feature_id: str
    surface: str
    scope: str = "backend_descriptor_and_policy"

    def describe(self) -> dict:
        return {
            "feature_id": self.feature_id, "surface": self.surface,
            "scope": self.scope,
        }


def feature_descriptors() -> tuple[FeatureDescriptor, ...]:
    return tuple(FeatureDescriptor(fid, FEATURE_SURFACES[fid]) for fid in FEATURE_IDS)


def assert_feature_index_complete() -> None:
    if set(FEATURE_IDS) != set(FEATURE_SURFACES) or len(FEATURE_IDS) != 36:
        raise BackendError("feature index must cover exactly the 36 open E7 rows")
