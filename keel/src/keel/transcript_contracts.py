"""keel.transcript_contracts -- transcript / history contracts (Y2.x P0).

This is an *additive* module.  It does not edit ``keel.transcript``,
``keel.session``, ``keel.pairing``, the web app, the CLI or any existing test.
Integration into the live runtime is a separate lead decision (the exact seams
are listed in ``master-plan-v6-transcript-contracts-evidence.md``).

The ten not_started P0 registry IDs are turned into real, testable Python
functionality:

  Y2.1  typed append-mostly rows, seq/updatedSeq, stable ids, provenance .... TranscriptRow, TranscriptStore, apply_snapshot
  Y2.2  model history separate from UI rows; model-visible <=> logged ........ split_history, reconcile, ModelHistory
  Y2.3  last N screenshots inline (N=3), local refs, no fabrication .......... ScreenshotDescriptor, ScreenshotRing
  Y2.4  orphaned tool-call repair with an honest marker ...................... find_orphan_tool_calls, repair_orphaned_tool_calls
  Y2.5  per-agent serial queue + approval expiry on a new message ............ SerialTurnQueue
  Y2.6  persisted pending turns, resumable after a restart ................... PendingTurnFileStore
  Y2.7  Allow / Always allow / Don't allow (no-retry instruction) ............ resolve_approval
  Y2.8  read-only connector classification (manifest first, slug fallback) ... classify_connector_tool
  Y2.14 credential-free VNC relay descriptor + server-side input filter ...... VncRelay, VncRelayDescriptor, RelaySeam
  Y2.20 least-exposure defaults, allowlist, explicit share opt-in ............ ExposurePolicy, validate_exposure

Only the Python standard library is used.  There is no network, no socket, no
VNC and no browser credential handling: the relay is a seam with an in-process
input filter.  There are no import-time side effects and no uuid/rng: all ids
are deterministic SHA-256 prefixes.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field, fields, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# shared helpers: canonical bytes, content hashes, timestamps, typed errors
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 encoding used by every hash in this module."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def timestamp(clock: Callable[[], float] | None = None) -> str:
    """UTC ISO-8601 stamp; *clock* is an injectable epoch-seconds callable."""
    now = float(clock()) if clock is not None else time.time()
    return datetime.fromtimestamp(now, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z")


class TranscriptContractError(ValueError):
    """Base class for all typed transcript contract failures."""


class InvalidRowError(TranscriptContractError):
    """A row's own fields are invalid."""


class AppendOnlyViolation(TranscriptContractError):
    """A write would delete, reuse, reorder or silently rewrite history."""


class HistoryReconciliationError(TranscriptContractError):
    """A model item has no exact durable row, or vice versa."""


# ---------------------------------------------------------------------------
# Y2.1 -- typed transcript rows and the append-mostly store
# ---------------------------------------------------------------------------


class RowKind(str, Enum):
    """The five canonical transcript row kinds."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    REASONING = "reasoning"


@dataclass(frozen=True)
class Provenance:
    """Where a row came from; ``synthetic`` marks honest machine repairs."""

    source: str = "agent"
    actor: str = ""
    channel: str = ""
    model: str = ""
    synthetic: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise InvalidRowError("provenance source must be non-empty")

    def to_dict(self) -> dict:
        return {"source": self.source, "actor": self.actor,
                "channel": self.channel, "model": self.model,
                "synthetic": self.synthetic}

    @classmethod
    def from_dict(cls, data: dict) -> "Provenance":
        d = dict(data or {})
        return cls(source=str(d.get("source") or "agent"),
                   actor=str(d.get("actor") or ""),
                   channel=str(d.get("channel") or ""),
                   model=str(d.get("model") or ""),
                   synthetic=bool(d.get("synthetic", False)))


def _coerce_provenance(value: Provenance | dict | None) -> Provenance:
    if value is None:
        return Provenance()
    if isinstance(value, Provenance):
        return value
    if isinstance(value, dict):
        return Provenance.from_dict(value)
    raise InvalidRowError("provenance must be a Provenance or dict")


@dataclass(frozen=True)
class TranscriptRow:
    """One durable row.

    ``seq`` is a stable per-session identity assigned once by the journal and
    never reused.  ``updated_seq`` is the per-session revision counter: a
    streaming reply is the *same* row (same ``id``/``seq``) rewritten with a
    higher ``updated_seq``, so clients upsert by ``seq``.  ``content_hash``
    commits to kind + JSON body + generation, never to wall-clock time.
    """

    seq: int
    id: str
    updated_seq: int
    kind: RowKind
    body: dict
    created_at: str
    updated_at: str
    provenance: Provenance = field(default_factory=Provenance)
    generation: int = 1
    model_visible: bool = True

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "kind", RowKind(self.kind))
        except ValueError:
            raise InvalidRowError(f"unknown row kind: {self.kind!r}") from None
        if not isinstance(self.seq, int) or self.seq < 0:
            raise InvalidRowError("row seq must be a non-negative integer")
        if not isinstance(self.updated_seq, int) or self.updated_seq < self.seq:
            raise InvalidRowError("updated_seq must be >= seq")
        if self.seq and (not isinstance(self.id, str) or not self.id):
            raise InvalidRowError("a committed row needs a stable id")
        if not isinstance(self.body, dict):
            raise InvalidRowError("row body must be a JSON object")
        try:
            canonical_bytes(self.body)
        except (TypeError, ValueError) as exc:
            raise InvalidRowError(f"row body is not JSON: {exc}") from None
        if not isinstance(self.created_at, str) or not self.created_at:
            raise InvalidRowError("row needs a created_at timestamp")
        if not isinstance(self.updated_at, str) or not self.updated_at:
            raise InvalidRowError("row needs an updated_at timestamp")
        if not isinstance(self.generation, int) or self.generation < 1:
            raise InvalidRowError("generation must be a positive integer")
        object.__setattr__(self, "provenance",
                           _coerce_provenance(self.provenance))
        if self.kind is RowKind.TOOL:
            phase = self.body.get("phase")
            tool_use_id = self.body.get("tool_use_id")
            if phase not in ("call", "result"):
                raise InvalidRowError("tool row needs phase call|result")
            if not isinstance(tool_use_id, str) or not tool_use_id:
                raise InvalidRowError("tool row needs a non-empty tool_use_id")
        if self.kind is RowKind.REASONING and not isinstance(
                self.body.get("reasoning"), str):
            raise InvalidRowError("reasoning row needs a string reasoning blob")

    @property
    def content_hash(self) -> str:
        return content_hash({"kind": self.kind.value, "body": self.body,
                             "generation": self.generation})

    def to_dict(self) -> dict:
        return {
            "seq": self.seq, "id": self.id, "updated_seq": self.updated_seq,
            "kind": self.kind.value, "body": self.body,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "provenance": self.provenance.to_dict(),
            "generation": self.generation, "model_visible": self.model_visible,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TranscriptRow":
        d = dict(data)
        return cls(
            seq=int(d.get("seq", 0)), id=str(d.get("id") or ""),
            updated_seq=int(d.get("updated_seq", 0)),
            kind=RowKind(d.get("kind", RowKind.USER.value)),
            body=dict(d.get("body") or {}),
            created_at=str(d.get("created_at") or ""),
            updated_at=str(d.get("updated_at") or d.get("created_at") or ""),
            provenance=Provenance.from_dict(d.get("provenance") or {}),
            generation=int(d.get("generation", 1)),
            model_visible=bool(d.get("model_visible", True)),
        )


def validate_rows(rows: Sequence[TranscriptRow]) -> None:
    """Validate a whole snapshot: strict seq order, unique ids, no gaps."""
    seen_seq: set[int] = set()
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, TranscriptRow):
            raise AppendOnlyViolation("snapshot contains a non-row object")
        if row.seq < 1 or row.seq in seen_seq:
            raise AppendOnlyViolation(f"invalid or repeated seq {row.seq}")
        if row.id in seen_ids:
            raise AppendOnlyViolation(f"repeated row id {row.id}")
        seen_seq.add(row.seq)
        seen_ids.add(row.id)


def validate_append(existing: Sequence[TranscriptRow], new: TranscriptRow, *,
                    revision: int | None = None) -> None:
    """A new row must extend the log; it may not reuse seq/id or go back in time."""
    max_seq = max((r.seq for r in existing), default=0)
    max_revision = max((r.updated_seq for r in existing), default=0)
    if new.seq != max_seq + 1:
        raise AppendOnlyViolation(
            f"append must use seq {max_seq + 1}, got {new.seq}")
    if any(r.id == new.id for r in existing):
        raise AppendOnlyViolation(f"row id {new.id} was already committed")
    if new.updated_seq <= max_revision:
        raise AppendOnlyViolation("append needs a fresh, higher updated_seq")
    if revision is not None and new.updated_seq != revision:
        raise AppendOnlyViolation("append revision does not match the session")
    validate_rows(tuple(existing) + (new,))


def validate_rewrite(old: TranscriptRow, new: TranscriptRow, *,
                     revision: int | None = None) -> None:
    """Upsert identity is immutable; only body/revision/timestamp may change."""
    if (new.seq != old.seq or new.id != old.id or new.kind != old.kind
            or new.created_at != old.created_at
            or new.generation != old.generation):
        raise AppendOnlyViolation("a rewrite may not change row identity")
    if new.updated_seq <= old.updated_seq:
        raise AppendOnlyViolation("a rewrite needs a higher updated_seq")
    if revision is not None and new.updated_seq != revision:
        raise AppendOnlyViolation("rewrite revision does not match the session")


def apply_snapshot(rows: Sequence[TranscriptRow],
                   incoming: Sequence[TranscriptRow]) -> tuple[TranscriptRow, ...]:
    """Client reconnect/replay: upsert by seq, highest updated_seq wins.

    Rows are never deleted and seq is never renumbered.  A stale frame cannot
    regress a live row; two different bodies at the same revision is a
    contract violation rather than a silent coin flip.
    """
    merged: dict[int, TranscriptRow] = {r.seq: r for r in rows}
    for row in incoming:
        current = merged.get(row.seq)
        if current is None:
            merged[row.seq] = row
        elif row.updated_seq > current.updated_seq:
            merged[row.seq] = row
        elif (row.updated_seq == current.updated_seq
              and row.content_hash != current.content_hash):
            raise AppendOnlyViolation(
                f"conflicting bodies at revision {row.updated_seq}")
    result = tuple(merged[key] for key in sorted(merged))
    validate_rows(result)
    return result


class TranscriptStore:
    """The durable, append-mostly session log of typed rows."""

    SNAPSHOT_FORMAT = "keel-transcript"

    def __init__(self, session_id: str = "session",
                 clock: Callable[[], float] | None = None) -> None:
        self.session_id = str(session_id)
        self._clock = clock
        self._rows: list[TranscriptRow] = []
        self._revision = 0
        self._generation = 1
        self._lock = threading.RLock()

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def revision(self) -> int:
        return self._revision

    def reset_generation(self) -> int:
        """Start a new conversation; seq/revision keep increasing forever."""
        with self._lock:
            self._generation += 1
            return self._generation

    def rows(self, generation: int | None = None) -> tuple[TranscriptRow, ...]:
        with self._lock:
            if generation is None:
                return tuple(self._rows)
            return tuple(r for r in self._rows if r.generation == generation)

    def get(self, seq: int) -> TranscriptRow:
        for row in self._rows:
            if row.seq == seq:
                return row
        raise AppendOnlyViolation(f"no row with seq {seq}")

    def append(self, kind: RowKind | str, body: dict, *,
               provenance: Provenance | dict | None = None,
               model_visible: bool = True) -> TranscriptRow:
        with self._lock:
            seq = len(self._rows) + 1
            self._revision += 1
            now = timestamp(self._clock)
            try:
                typed_kind = RowKind(kind)
            except ValueError:
                raise InvalidRowError(f"unknown row kind: {kind!r}") from None
            row = TranscriptRow(
                seq=seq,
                id=content_hash(f"{self.session_id}:{self._generation}:{seq}")[:16],
                updated_seq=self._revision, kind=typed_kind,
                body=dict(body) if isinstance(body, dict) else body,
                created_at=now, updated_at=now,
                provenance=_coerce_provenance(provenance),
                generation=self._generation, model_visible=bool(model_visible))
            validate_append(self._rows, row, revision=self._revision)
            self._rows.append(row)
            return row

    def rewrite(self, seq: int, body: dict, *,
                provenance: Provenance | dict | None = None,
                model_visible: bool | None = None) -> TranscriptRow:
        """Rewrite one existing row (e.g. a streamed reply) at a new revision."""
        with self._lock:
            index = next((i for i, r in enumerate(self._rows)
                          if r.seq == seq), None)
            if index is None:
                raise AppendOnlyViolation(f"no row with seq {seq}")
            old = self._rows[index]
            self._revision += 1
            new = TranscriptRow(
                seq=old.seq, id=old.id, updated_seq=self._revision,
                kind=old.kind,
                body=dict(body) if isinstance(body, dict) else body,
                created_at=old.created_at,
                updated_at=timestamp(self._clock),
                provenance=_coerce_provenance(provenance)
                if provenance is not None else old.provenance,
                generation=old.generation,
                model_visible=old.model_visible if model_visible is None
                else bool(model_visible))
            validate_rewrite(old, new, revision=self._revision)
            self._rows[index] = new
            return new

    def snapshot(self) -> dict:
        """Wire format for SSE reconnect / replay."""
        return {"format": self.SNAPSHOT_FORMAT, "session_id": self.session_id,
                "generation": self._generation, "revision": self._revision,
                "rows": [r.to_dict() for r in self._rows]}

    @classmethod
    def restore(cls, snapshot: dict) -> "TranscriptStore":
        rows = tuple(TranscriptRow.from_dict(r)
                     for r in (snapshot.get("rows") or ()))
        validate_rows(rows)
        store = cls(str(snapshot.get("session_id") or "session"))
        store._rows = list(rows)
        store._generation = int(snapshot.get("generation", 1))
        store._revision = max(int(snapshot.get("revision", 0)),
                              *(r.updated_seq for r in rows), 0)
        return store

    def apply(self, incoming: Sequence[TranscriptRow]) -> None:
        with self._lock:
            self._rows = list(apply_snapshot(self._rows, incoming))
            self._revision = max(self._revision,
                                 *(r.updated_seq for r in self._rows), 0)


# ---------------------------------------------------------------------------
# Y2.2 -- model history stored separately from UI rows
# ---------------------------------------------------------------------------

UI_TABLE_NAME = "llm_items"
MODEL_TABLE_NAME = "model_items"
_ROLE_BY_KIND = {
    RowKind.SYSTEM: "system",
    RowKind.USER: "user",
    RowKind.ASSISTANT: "assistant",
    RowKind.TOOL: "tool",
    RowKind.REASONING: "assistant",
}


@dataclass(frozen=True)
class ModelItem:
    """One model-visible input item, stored in its own table/projection."""

    seq: int
    source_id: str
    role: str
    content: str = ""
    generation: int = 1
    reasoning: str = ""
    phase: str = ""
    tool_use_id: str = ""
    images: tuple[str, ...] = ()
    omitted_images: tuple[str, ...] = ()
    content_hash: str = ""

    def __post_init__(self) -> None:
        if self.role not in ("system", "user", "assistant", "tool"):
            raise InvalidRowError(f"unknown model role {self.role!r}")
        object.__setattr__(self, "images", tuple(self.images))
        object.__setattr__(self, "omitted_images", tuple(self.omitted_images))
        if not self.content_hash:
            object.__setattr__(self, "content_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        return content_hash({
            "role": self.role, "content": self.content,
            "reasoning": self.reasoning, "phase": self.phase,
            "tool_use_id": self.tool_use_id, "images": self.images,
            "generation": self.generation,
        })

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict) -> "ModelItem":
        d = dict(data)
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})


def _text_field(body: dict) -> str:
    for key in ("text", "content"):
        if isinstance(body.get(key), str):
            return body[key]
    return ""


def model_item_from_row(row: TranscriptRow) -> ModelItem | None:
    """Project one model-visible row into one immutable model item."""
    if not row.model_visible:
        return None
    body = row.body
    return ModelItem(
        seq=row.seq, source_id=row.id, role=_ROLE_BY_KIND[row.kind],
        content=_text_field(body), generation=row.generation,
        reasoning=str(body.get("reasoning") or ""),
        phase=str(body.get("phase") or ""),
        tool_use_id=str(body.get("tool_use_id") or ""),
        images=tuple(body.get("screenshot_ids") or ()),
    )


@dataclass(frozen=True)
class UiRow:
    """A derived/annotated UI row; redaction never touches model items."""

    row: TranscriptRow
    display_content: str
    redacted: bool = False
    note: str = ""


@dataclass(frozen=True)
class Reconciliation:
    ok: bool
    model_only: tuple[int, ...] = ()
    log_only: tuple[int, ...] = ()
    hash_mismatches: tuple[int, ...] = ()
    reasoning_mismatches: tuple[int, ...] = ()


def reconcile(model_items: Sequence[ModelItem],
              rows: Sequence[TranscriptRow]) -> Reconciliation:
    """Model-visible <=> logged, with exact content/reasoning hashes."""
    log = {r.seq: r for r in rows}
    item_seqs = {i.seq for i in model_items}
    model_only = tuple(i.seq for i in model_items if i.seq not in log)
    log_only = tuple(r.seq for r in rows
                     if r.model_visible and r.seq not in item_seqs)
    mismatches: list[int] = []
    reasoning_mismatches: list[int] = []
    for item in model_items:
        source = log.get(item.seq)
        if source is None:
            continue
        expected = model_item_from_row(source)
        if expected is None or expected.content_hash != item.content_hash:
            mismatches.append(item.seq)
        if item.reasoning != str(source.body.get("reasoning") or ""):
            reasoning_mismatches.append(item.seq)
    ok = not (model_only or log_only or mismatches or reasoning_mismatches)
    return Reconciliation(ok, model_only, log_only, tuple(mismatches),
                          tuple(reasoning_mismatches))


def assert_reconciled(model_items: Sequence[ModelItem],
                      rows: Sequence[TranscriptRow]) -> Reconciliation:
    result = reconcile(model_items, rows)
    if not result.ok:
        raise HistoryReconciliationError(
            f"model history / durable log divergence: {result}")
    return result


@dataclass(frozen=True)
class SplitHistory:
    model_items: tuple[ModelItem, ...]
    ui_rows: tuple[UiRow, ...]
    reconciliation: Reconciliation


def split_history(rows: Sequence[TranscriptRow], *,
                  ui_redactions: Mapping[int, str] | None = None) -> SplitHistory:
    """Build the separate model history and annotated UI rows from one log."""
    redactions = dict(ui_redactions or {})
    items: list[ModelItem] = []
    ui: list[UiRow] = []
    for row in rows:
        if row.seq in redactions:
            ui.append(UiRow(row, str(redactions[row.seq]), True, "ui_redaction"))
        else:
            ui.append(UiRow(row, _text_field(row.body), False, ""))
        item = model_item_from_row(row)
        if item is not None:
            items.append(item)
    result = reconcile(items, rows)
    if not result.ok:
        raise HistoryReconciliationError(
            f"cannot split a divergent history: {result}")
    return SplitHistory(tuple(items), tuple(ui), result)


class ModelHistory:
    """The separate ``model_items`` projection (never the UI row table)."""

    TABLE_NAME = MODEL_TABLE_NAME

    def __init__(self, items: Iterable[ModelItem] = ()) -> None:
        self._items = tuple(items)

    @classmethod
    def from_rows(cls, rows: Sequence[TranscriptRow]) -> "ModelHistory":
        return cls(split_history(rows).model_items)

    def items(self) -> tuple[ModelItem, ...]:
        return self._items

    def append(self, item: ModelItem) -> None:
        self._items += (item,)

    def snapshot(self) -> tuple[dict, ...]:
        return tuple(i.to_dict() for i in self._items)


# ---------------------------------------------------------------------------
# Y2.3 -- last N screenshots inline, local refs only, no fabrication
# ---------------------------------------------------------------------------

DEFAULT_INLINE_SCREENSHOTS = 3
_LOCAL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class ScreenshotContractError(TranscriptContractError):
    """Base class for screenshot descriptor / retention failures."""


class ScreenshotReferenceError(ScreenshotContractError):
    """A screenshot reference was not a local file reference."""


class ScreenshotNotFoundError(ScreenshotContractError):
    """The referenced local screenshot file does not exist."""


def is_local_ref(value: str) -> bool:
    """Accept local file paths only; reject every URL/data/UNC reference."""
    if not isinstance(value, str) or not value.strip():
        return False
    ref = value.strip()
    if "\x00" in ref or _LOCAL_RE.match(ref):
        return False
    if ref.lower().startswith("data:") or ref.startswith("//"):
        return False
    if ref.startswith("\\\\"):
        return False
    return True


@dataclass(frozen=True)
class ScreenshotDescriptor:
    """Metadata about a real local file.  Never carries image bytes."""

    id: str
    local_path: str
    sha256: str
    byte_size: int
    captured_at: str
    source: str = "screenshot"
    inline: bool = True

    def __post_init__(self) -> None:
        if not is_local_ref(self.local_path):
            raise ScreenshotReferenceError(
                f"not a local file reference: {self.local_path!r}")
        if not isinstance(self.sha256, str) or not _HEX64_RE.fullmatch(self.sha256):
            raise ScreenshotContractError("descriptor sha256 must be 64 hex chars")
        if not isinstance(self.byte_size, int) or self.byte_size < 1:
            raise ScreenshotContractError("descriptor byte_size must be positive")
        expected = content_hash({"local_path": self.local_path,
                                 "sha256": self.sha256,
                                 "byte_size": self.byte_size})[:16]
        if self.id != expected:
            raise ScreenshotContractError(
                "descriptor id does not commit to its local file bytes")

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict) -> "ScreenshotDescriptor":
        d = dict(data)
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})


def describe_screenshot(path: str, *, root: str | Path | None = None,
                        clock: Callable[[], float] | None = None,
                        source: str = "screenshot") -> ScreenshotDescriptor:
    """Hash a real file and produce its descriptor.  No image is fabricated."""
    if not is_local_ref(str(path)):
        raise ScreenshotReferenceError(f"not a local file reference: {path!r}")
    target = Path(path)
    if root is not None:
        base = Path(root).resolve()
        target = (target if target.is_absolute() else base / target).resolve()
        if not target.is_relative_to(base):
            raise ScreenshotReferenceError("screenshot escapes its local root")
    if not target.is_file():
        raise ScreenshotNotFoundError(f"no local screenshot at {path!r}")
    data = target.read_bytes()
    if not data:
        raise ScreenshotContractError("screenshot file is empty")
    digest = hashlib.sha256(data).hexdigest()
    local_path = str(path)
    return ScreenshotDescriptor(
        id=content_hash({"local_path": local_path, "sha256": digest,
                         "byte_size": len(data)})[:16],
        local_path=local_path, sha256=digest, byte_size=len(data),
        captured_at=timestamp(clock), source=source)


def assert_real_screenshot(descriptor: ScreenshotDescriptor) -> None:
    """Re-read the local file to prove the descriptor was not invented."""
    path = Path(descriptor.local_path)
    if not path.is_file():
        raise ScreenshotNotFoundError(
            f"screenshot no longer exists: {descriptor.local_path!r}")
    data = path.read_bytes()
    if (hashlib.sha256(data).hexdigest() != descriptor.sha256
            or len(data) != descriptor.byte_size):
        raise ScreenshotContractError(
            "descriptor does not match the bytes on disk")


@dataclass(frozen=True)
class PruneReport:
    items: tuple[ModelItem, ...]
    kept_ids: tuple[str, ...]
    omitted_ids: tuple[str, ...]
    capacity: int


class ScreenshotRing:
    """Bounded retention of the last N screenshot descriptors for context."""

    def __init__(self, capacity: int = DEFAULT_INLINE_SCREENSHOTS) -> None:
        if not isinstance(capacity, int) or capacity < 0:
            raise ScreenshotContractError("screenshot capacity must be >= 0")
        self.capacity = capacity
        self._descriptors: list[ScreenshotDescriptor] = []
        self._evicted = 0
        self._lock = threading.RLock()

    @property
    def evicted_count(self) -> int:
        return self._evicted

    def add(self, descriptor: ScreenshotDescriptor, *,
            verify: bool = True) -> None:
        if not isinstance(descriptor, ScreenshotDescriptor):
            raise ScreenshotContractError("expected a ScreenshotDescriptor")
        if verify:
            assert_real_screenshot(descriptor)
        with self._lock:
            self._descriptors.append(descriptor)
            overflow = len(self._descriptors) - self.capacity
            if overflow > 0:
                self._evicted += overflow
                self._descriptors = self._descriptors[overflow:]

    def descriptors(self) -> tuple[ScreenshotDescriptor, ...]:
        with self._lock:
            return tuple(self._descriptors)

    def inline_ids(self) -> tuple[str, ...]:
        return tuple(d.id for d in self.descriptors())

    def prune(self, items: Sequence[ModelItem]) -> PruneReport:
        """Keep image parts only for the last N inline screenshot ids.

        Older images become an explicit ``omitted_images`` marker.  No bytes,
        placeholder image or success claim is ever generated.
        """
        inline = set(self.inline_ids())
        kept: list[str] = []
        omitted: list[str] = []
        pruned: list[ModelItem] = []
        for item in items:
            keep = tuple(i for i in item.images if i in inline)
            drop = tuple(i for i in item.images if i not in inline)
            kept.extend(keep)
            omitted.extend(drop)
            pruned.append(replace(item, images=keep,
                                  omitted_images=item.omitted_images + drop))
        return PruneReport(tuple(pruned), tuple(kept), tuple(omitted),
                           self.capacity)


# ---------------------------------------------------------------------------
# Y2.4 -- orphaned tool-call repair with an honest missing-result marker
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCallRef:
    tool_use_id: str
    name: str
    row_seq: int
    row_id: str


def find_orphan_tool_calls(rows: Sequence[TranscriptRow]) -> tuple[ToolCallRef, ...]:
    """Every tool call without a matching tool result (after an interruption)."""
    results = {str(r.body.get("tool_use_id") or "") for r in rows
               if r.kind is RowKind.TOOL and r.body.get("phase") == "result"}
    return tuple(
        ToolCallRef(str(r.body.get("tool_use_id") or ""),
                    str(r.body.get("name") or ""), r.seq, r.id)
        for r in sorted(rows, key=lambda row: row.seq)
        if r.kind is RowKind.TOOL and r.body.get("phase") == "call"
        and str(r.body.get("tool_use_id") or "") not in results
    )


def synthetic_missing_result(call: ToolCallRef, *,
                             reason: str = "interrupted turn") -> dict:
    """The typed, honest body used for a repaired tool result."""
    return {
        "phase": "result",
        "tool_use_id": call.tool_use_id,
        "name": call.name,
        "content": "[interrupted tool call: no result was recorded]",
        "status": "unknown",
        "synthetic": True,
        "honest_marker": "interrupted",
        "reason": str(reason),
    }


def repair_orphaned_tool_calls(store: TranscriptStore, *,
                               reason: str = "interrupted turn"
                               ) -> tuple[TranscriptRow, ...]:
    """Append one synthetic missing-result row per orphan before the next call.

    The result is explicitly marked synthetic/interrupted with status
    ``unknown``.  It never invents output, success, an exit code or a tool
    result that was not recorded.  Calling it twice is a no-op.
    """
    committed: list[TranscriptRow] = []
    for call in find_orphan_tool_calls(store.rows()):
        committed.append(store.append(
            RowKind.TOOL, synthetic_missing_result(call, reason=reason),
            provenance=Provenance(source="synthetic", actor="repair",
                                  synthetic=True),
            model_visible=True))
    return tuple(committed)


# ---------------------------------------------------------------------------
# Y2.14 -- credential-free VNC relay descriptor and server-side input filter
# ---------------------------------------------------------------------------


class VncRelayError(ValueError):
    """Invalid relay configuration or an attempted credential leak."""


class RelayMode(str, Enum):
    WATCH = "watch"
    TAKEOVER = "takeover"


INPUT_KINDS = ("keyboard", "pointer", "clipboard")


@dataclass(frozen=True)
class VncCredentials:
    """Server-side only.  Never placed in a descriptor or sent to a browser."""

    host: str
    port: int
    username: str
    password: str

    def __post_init__(self) -> None:
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise VncRelayError("VNC port must be in 1..65535")
        for name in ("host", "username", "password"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise VncRelayError(f"VNC {name} must be non-empty")


@dataclass(frozen=True)
class VncInputEvent:
    kind: str
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in INPUT_KINDS:
            raise VncRelayError(f"unknown VNC input kind {self.kind!r}")


@dataclass(frozen=True)
class VncRelayDescriptor:
    """Credential-free handle the browser is allowed to see."""

    relay_id: str
    endpoint: str
    mode: RelayMode
    frame_only: bool
    input_allowed: bool
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", RelayMode(self.mode))
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", content_hash({
                "relay_id": self.relay_id, "endpoint": self.endpoint,
                "mode": self.mode.value, "frame_only": self.frame_only,
                "input_allowed": self.input_allowed,
            })[:16])

    def to_dict(self) -> dict:
        return {"relay_id": self.relay_id, "endpoint": self.endpoint,
                "mode": self.mode.value, "frame_only": self.frame_only,
                "input_allowed": self.input_allowed,
                "fingerprint": self.fingerprint}

    @classmethod
    def from_dict(cls, data: dict) -> "VncRelayDescriptor":
        return cls(**dict(data))


class RelaySeam:
    """Seam a lead can replace with a real relay; no sockets here."""

    def forward(self, event: VncInputEvent) -> None:  # pragma: no cover - seam
        raise NotImplementedError


class RecordingSeam(RelaySeam):
    """In-process seam used by the relay and its contract tests."""

    def __init__(self) -> None:
        self._forwarded: list[VncInputEvent] = []

    def forward(self, event: VncInputEvent) -> None:
        self._forwarded.append(event)

    @property
    def forwarded(self) -> tuple[VncInputEvent, ...]:
        return tuple(self._forwarded)


class VncRelay:
    """Binds credentials server-side; exposes only a descriptor to clients."""

    def __init__(self, credentials: VncCredentials, *, session_id: str = "",
                 mode: RelayMode | str = RelayMode.WATCH,
                 seam: RelaySeam | None = None) -> None:
        if not isinstance(credentials, VncCredentials):
            raise VncRelayError("credentials must be a VncCredentials")
        try:
            self._mode = RelayMode(mode)
        except ValueError:
            raise VncRelayError(f"unknown relay mode: {mode!r}") from None
        self._credentials = credentials
        self._session_id = str(session_id)
        self._seam = seam or RecordingSeam()

    @property
    def mode(self) -> RelayMode:
        return self._mode

    def descriptor(self) -> VncRelayDescriptor:
        relay_id = content_hash(
            f"vnc:{self._session_id}:{self._credentials.port}")[:16]
        return VncRelayDescriptor(
            relay_id=relay_id, endpoint=f"/relay/vnc/{relay_id}",
            mode=self._mode, frame_only=True,
            input_allowed=self._mode is RelayMode.TAKEOVER)

    def allows_input(self, event: VncInputEvent) -> bool:
        return self._mode is RelayMode.TAKEOVER and event.kind in INPUT_KINDS

    def receive_input(self, events: Iterable[VncInputEvent]
                      ) -> tuple[VncInputEvent, ...]:
        """Server-side filter: watch mode drops all input before forwarding."""
        allowed = tuple(event for event in events if self.allows_input(event))
        for event in allowed:
            self._seam.forward(event)
        return allowed


def assert_credential_free(descriptor: VncRelayDescriptor,
                           credentials: VncCredentials) -> bool:
    """Fail if any secret or credential field name reached the descriptor."""
    doc = json.dumps(descriptor.to_dict(), sort_keys=True)
    for secret in (credentials.password, credentials.username,
                   credentials.host, f"{credentials.host}:{credentials.port}"):
        if secret and secret in doc:
            raise VncRelayError("VNC credentials leaked into the descriptor")
    forbidden = {"password", "username", "host", "token", "credentials"}
    if forbidden.intersection(descriptor.to_dict()):
        raise VncRelayError("descriptor exposes a credential field")
    return True


# ---------------------------------------------------------------------------
# Y2.20 -- least-exposure defaults, allowlist, explicit share opt-in
# ---------------------------------------------------------------------------


class ExposureError(RuntimeError):
    """Base class for exposure-policy violations."""


class ExposureViolation(ExposureError):
    """An artifact was private but an attempt was made to expose it."""


class SignupRefused(ExposureError):
    """New sign-ups are not permitted under the current policy."""


class AllowlistEntryError(ValueError):
    """An allowlist entry was neither an email nor an @domain."""


class Visibility(str, Enum):
    PRIVATE = "private"
    SHARED = "shared"


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+$")
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+$")


def normalize_allowlist(entries: Iterable[str]) -> tuple[str, ...]:
    """Accept only an email address or ``@domain``; dedupe and sort."""
    out: set[str] = set()
    for raw in entries:
        if not isinstance(raw, str):
            raise AllowlistEntryError("allowlist entries must be strings")
        entry = raw.strip().lower()
        if entry.startswith("@"):
            if not _DOMAIN_RE.fullmatch(entry[1:]):
                raise AllowlistEntryError(f"invalid allowlist domain: {raw!r}")
        elif not _EMAIL_RE.fullmatch(entry):
            raise AllowlistEntryError(f"invalid allowlist entry: {raw!r}")
        out.add(entry)
    return tuple(sorted(out))


def allowlist_matches(entry: str, email: str) -> bool:
    address = str(email).strip().lower()
    rule = str(entry).strip().lower()
    if rule.startswith("@"):
        return address.rpartition("@")[2] == rule[1:]
    return address == rule


def is_local_host(host: str) -> bool:
    """Loopback bind only; empty bind / 0.0.0.0 / DNS names are public."""
    value = str(host).strip().lower().rstrip(".")
    if value in ("localhost", "::1", "[::1]"):
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class ExposurePolicy:
    """Private-by-default server + transcript/screenshot exposure policy."""

    bind_host: str = "127.0.0.1"
    auth_enabled: bool = True
    dev_login_enabled: bool = False
    signups_enabled: bool = False
    allowlist: tuple[str, ...] = ()
    transcript_visibility: Visibility = Visibility.PRIVATE
    screenshot_visibility: Visibility = Visibility.PRIVATE

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowlist", normalize_allowlist(self.allowlist))
        object.__setattr__(self, "transcript_visibility",
                           Visibility(self.transcript_visibility))
        object.__setattr__(self, "screenshot_visibility",
                           Visibility(self.screenshot_visibility))

    @property
    def public(self) -> bool:
        return not is_local_host(self.bind_host)

    def to_dict(self) -> dict:
        return {"bind_host": self.bind_host, "auth_enabled": self.auth_enabled,
                "dev_login_enabled": self.dev_login_enabled,
                "signups_enabled": self.signups_enabled,
                "allowlist": list(self.allowlist),
                "transcript_visibility": self.transcript_visibility.value,
                "screenshot_visibility": self.screenshot_visibility.value}

    @classmethod
    def from_dict(cls, data: dict) -> "ExposurePolicy":
        d = dict(data)
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})


@dataclass(frozen=True)
class ExposureDecision:
    allowed: bool
    reasons: tuple[str, ...] = ()


def effective_dev_login(policy: ExposurePolicy) -> bool:
    """Dev login is ignored off localhost, even when the flag is set."""
    return bool(policy.dev_login_enabled) and not policy.public


def validate_exposure(policy: ExposurePolicy) -> ExposureDecision:
    """Public binds need auth + allowlist; sharing needs explicit opt-in."""
    reasons: list[str] = []
    if policy.public:
        if not policy.auth_enabled:
            reasons.append("a public bind requires authentication")
        if not policy.allowlist:
            reasons.append("a public bind requires an allowlist")
        if policy.signups_enabled and not policy.allowlist:
            reasons.append(
                "new sign-ups on a public URL are refused until an allowlist is set")
        shared = (policy.transcript_visibility is Visibility.SHARED
                  or policy.screenshot_visibility is Visibility.SHARED)
        if shared and (not policy.auth_enabled or not policy.allowlist):
            reasons.append("sharing on a public URL requires auth and an allowlist")
    return ExposureDecision(not reasons, tuple(reasons))


def authorize_signup(policy: ExposurePolicy, email: str) -> bool:
    """Explicit opt-in and (on a public URL) an allowlist are both required."""
    if not policy.signups_enabled:
        return False
    if not _EMAIL_RE.fullmatch(str(email).strip().lower()):
        return False
    if policy.public and not policy.allowlist:
        return False
    if policy.allowlist and not any(
            allowlist_matches(entry, email) for entry in policy.allowlist):
        return False
    return True


def share_transcripts(policy: ExposurePolicy) -> ExposurePolicy:
    return replace(policy, transcript_visibility=Visibility.SHARED)


def share_screenshots(policy: ExposurePolicy) -> ExposurePolicy:
    return replace(policy, screenshot_visibility=Visibility.SHARED)


def can_expose(policy: ExposurePolicy, artifact: str) -> bool:
    """Raise unless transcripts/screenshots were explicitly opted in to share."""
    key = {"transcripts": "transcript_visibility",
           "screenshots": "screenshot_visibility"}.get(artifact)
    if key is None:
        raise ExposureViolation(f"unknown artifact: {artifact!r}")
    if getattr(policy, key) is not Visibility.SHARED:
        raise ExposureViolation(
            f"{artifact} are private by default; explicit opt-in is required")
    return True


def env_reference() -> dict[str, str]:
    """`.env`-style reference values for the least-exposure defaults."""
    return {
        "KEEL_BIND": "127.0.0.1",
        "KEEL_AUTH": "true",
        "KEEL_DEV_LOGIN": "false",
        "KEEL_SIGNUPS": "false",
        "KEEL_ALLOWLIST": "",
        "KEEL_SHARE_TRANSCRIPTS": "false",
        "KEEL_SHARE_SCREENSHOTS": "false",
    }


# ---------------------------------------------------------------------------
# Y2.5 -- per-agent serial turn queue and approval expiry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnTicket:
    agent_id: str
    turn_id: str
    seq: int
    state: str = "queued"       # queued | running | awaiting_approval | done | expired

    def _identity(self) -> tuple[str, str, int]:
        return self.agent_id, self.turn_id, self.seq

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TurnTicket):
            return NotImplemented
        return self._identity() == other._identity()

    def __hash__(self) -> int:
        return hash(self._identity())


@dataclass
class _AgentQueue:
    running: TurnTicket | None = None
    queued: list[TurnTicket] = field(default_factory=list)
    expired: list[str] = field(default_factory=list)


class SerialTurnQueue:
    """At most one active turn per agent; a new message expires an approval."""

    def __init__(self) -> None:
        self._seq = 0
        self._agents: dict[str, _AgentQueue] = {}
        self._lock = threading.RLock()

    def _agent(self, agent_id: str) -> _AgentQueue:
        if agent_id not in self._agents:
            self._agents[agent_id] = _AgentQueue()
        return self._agents[agent_id]

    def enqueue(self, agent_id: str, turn_id: str) -> TurnTicket:
        if not agent_id or not turn_id:
            raise TranscriptContractError("agent_id and turn_id are required")
        with self._lock:
            self._seq += 1
            ticket = TurnTicket(agent_id, turn_id, self._seq)
            self._agent(agent_id).queued.append(ticket)
            return ticket

    def start(self, agent_id: str) -> TurnTicket | None:
        with self._lock:
            state = self._agent(agent_id)
            if state.running is not None:
                return None
            if not state.queued:
                return None
            ticket = replace(state.queued.pop(0), state="running")
            state.running = ticket
            return ticket

    def request_approval(self, agent_id: str) -> TurnTicket | None:
        with self._lock:
            state = self._agent(agent_id)
            if state.running is None:
                return None
            state.running = replace(state.running, state="awaiting_approval")
            return state.running

    def user_message(self, agent_id: str) -> tuple[str, ...]:
        """A user message while an approval pends closes it as expired."""
        with self._lock:
            state = self._agent(agent_id)
            if (state.running is not None
                    and state.running.state == "awaiting_approval"):
                expired = state.running.turn_id
                state.running = None
                state.expired.append(expired)
                return (expired,)
            return ()

    def finish(self, agent_id: str) -> TurnTicket | None:
        with self._lock:
            state = self._agent(agent_id)
            done = state.running
            state.running = None
            return replace(done, state="done") if done is not None else None

    def snapshot(self, agent_id: str) -> dict:
        with self._lock:
            state = self._agent(agent_id)
            return {"running": state.running,
                    "queued": tuple(state.queued),
                    "expired": tuple(state.expired)}


# ---------------------------------------------------------------------------
# Y2.6 -- persisted pending turns (survive a daemon restart)
# ---------------------------------------------------------------------------


class PendingTurnError(TranscriptContractError):
    """A pending turn was malformed or could not be resumed."""


_PENDING_STATUSES = ("awaiting_approval", "resumed", "expired")


@dataclass(frozen=True)
class PendingTurn:
    session_id: str
    turn_id: str
    generation: int
    pending_tool_calls: tuple[dict, ...]
    status: str = "awaiting_approval"
    answer: str = ""

    def __post_init__(self) -> None:
        if not self.session_id or not self.turn_id:
            raise PendingTurnError("pending turn needs session_id and turn_id")
        if self.generation < 1:
            raise PendingTurnError("generation must be positive")
        if self.status not in _PENDING_STATUSES:
            raise PendingTurnError(f"unknown pending status: {self.status!r}")
        object.__setattr__(self, "pending_tool_calls",
                           tuple(self.pending_tool_calls))

    @property
    def key(self) -> tuple[str, str]:
        return self.session_id, self.turn_id

    def to_dict(self) -> dict:
        return {"session_id": self.session_id, "turn_id": self.turn_id,
                "generation": self.generation,
                "pending_tool_calls": list(self.pending_tool_calls),
                "status": self.status, "answer": self.answer}

    @classmethod
    def from_dict(cls, data: dict) -> "PendingTurn":
        try:
            return cls(
                session_id=str(data["session_id"]),
                turn_id=str(data["turn_id"]),
                generation=int(data["generation"]),
                pending_tool_calls=tuple(data.get("pending_tool_calls") or ()),
                status=str(data.get("status") or "awaiting_approval"),
                answer=str(data.get("answer") or ""))
        except (KeyError, TypeError, ValueError) as exc:
            raise PendingTurnError(f"malformed pending turn: {exc}") from None


class PendingTurnFileStore:
    """Small atomic JSON store; a new instance reads the same saved state."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PendingTurnError(f"cannot read pending turns: {exc}") from None
        if not isinstance(doc, list):
            raise PendingTurnError("pending turn file must hold a list")
        return doc

    def _write(self, doc: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(doc, sort_keys=True, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        os.replace(tmp, self.path)

    def save(self, pending: PendingTurn) -> PendingTurn:
        doc = [d for d in self._read()
               if (d.get("session_id"), d.get("turn_id")) != pending.key]
        doc.append(pending.to_dict())
        self._write(doc)
        return pending

    def load(self, session_id: str) -> tuple[PendingTurn, ...]:
        return tuple(PendingTurn.from_dict(d) for d in self._read()
                     if d.get("session_id") == session_id)

    def resume(self, session_id: str, turn_id: str, *,
               answer: str = "") -> PendingTurn:
        doc = self._read()
        for index, entry in enumerate(doc):
            if entry.get("session_id") == session_id and entry.get("turn_id") == turn_id:
                resumed = replace(PendingTurn.from_dict(entry),
                                  status="resumed", answer=answer)
                doc[index] = resumed.to_dict()
                self._write(doc)
                return resumed
        raise PendingTurnError(f"no pending turn {turn_id!r} in {session_id!r}")


# ---------------------------------------------------------------------------
# Y2.7 -- Allow / Always allow / Don't allow
# ---------------------------------------------------------------------------


class ApprovalChoice(str, Enum):
    ALLOW = "allow"
    ALWAYS_ALLOW = "always_allow"
    DONT_ALLOW = "dont_allow"


@dataclass(frozen=True)
class ApprovalCard:
    tool_name: str
    tool_use_id: str
    prompt: str = ""


@dataclass(frozen=True)
class ApprovalOutcome:
    choice: ApprovalChoice
    execute: bool
    stored_tools: tuple[str, ...] = ()
    instruction: str = ""
    no_retry: bool = False


NO_RETRY_INSTRUCTION = (
    "The user denied the tool {tool!r}. Do not retry this tool call or "
    "attempt an equivalent action."
)


class ApprovalPolicyStore:
    """Remembers only explicit 'Always allow' grants, per tool name."""

    def __init__(self) -> None:
        self._always: set[str] = set()

    def allow_always(self, tool_name: str) -> None:
        self._always.add(str(tool_name))

    def is_always_allowed(self, tool_name: str) -> bool:
        return str(tool_name) in self._always

    def snapshot(self) -> tuple[str, ...]:
        return tuple(sorted(self._always))


def resolve_approval(card: ApprovalCard, choice: ApprovalChoice | str,
                     policy: ApprovalPolicyStore | None = None) -> ApprovalOutcome:
    """Resolve one approval card; denial injects an explicit no-retry rule."""
    selected = ApprovalChoice(choice)
    if selected is ApprovalChoice.ALWAYS_ALLOW:
        if policy is not None:
            policy.allow_always(card.tool_name)
        return ApprovalOutcome(selected, True, (card.tool_name,))
    if selected is ApprovalChoice.DONT_ALLOW:
        return ApprovalOutcome(
            selected, False, (),
            NO_RETRY_INSTRUCTION.format(tool=card.tool_name), True)
    return ApprovalOutcome(selected, True)


# ---------------------------------------------------------------------------
# Y2.8 -- read-only connector classification by slug (manifest first)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolClassification:
    read_only: bool
    needs_approval: bool
    basis: str           # manifest | slug | meta | unknown
    warning: str = ""


WRITE_MARKERS = ("SET", "PUT", "POST", "PATCH", "DELETE", "CREATE", "UPDATE",
                 "WRITE", "SEND", "REMOVE", "ADD", "INSERT", "EXECUTE")
META_MARKERS = ("exec", "run", "batch", "script", "shell", "invoke", "multi")
READ_SLUGS = ("_GET", "_LIST", "_SEARCH", "GET_", "LIST_", "SEARCH_")


def classify_connector_tool(name: str, *,
                            manifest_flags: Mapping[str, bool] | None = None,
                            inner_tools: Sequence[str] | None = None,
                            warn: Callable[[str], None] | None = None
                            ) -> ToolClassification:
    """Explicit manifest flags win; slug rules are a warned fallback only.

    Meta tools that can run arbitrary actions and batches with inner tools
    that cannot be proven read-only always require approval.
    """
    slug = str(name).strip()
    upper = slug.upper()
    flags = dict(manifest_flags or {})
    explicit = flags.get("readOnly", flags.get("read_only"))

    def emit(message: str) -> None:
        if warn is not None:
            warn(message)

    if inner_tools:
        inner = [classify_connector_tool(t) for t in inner_tools]
        if any(not tool.read_only for tool in inner):
            message = ("batch contains tools that cannot be proven read-only; "
                       "approval required")
            emit(message)
            return ToolClassification(False, True, "meta", message)

    meta = any(marker in slug.lower() for marker in META_MARKERS)
    if meta:
        message = "meta tool can run arbitrary actions; approval required"
        emit(message)
        return ToolClassification(False, True, "meta", message)

    if explicit is True:
        return ToolClassification(True, False, "manifest")
    if explicit is False:
        return ToolClassification(False, True, "manifest")

    has_write = any(marker in upper for marker in WRITE_MARKERS)
    looks_read = any(rule in upper for rule in READ_SLUGS)
    if looks_read and not has_write:
        message = ("Warning: read-only inferred from tool slug without an "
                   "explicit manifest flag; add readOnly to the connector manifest")
        emit(message)
        return ToolClassification(True, False, "slug", message)
    return ToolClassification(False, True, "unknown")
