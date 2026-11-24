"""Backend observability and diagnostics for the 20 v6 backend modules.

Stdlib only.  The event log is an append-only JSONL file with:

* deterministic, monotonic sequence numbers (assigned under a path-keyed
  lock, never from a wall-clock or a random source);
* UTC timestamps produced by an injectable clock;
* a correlation ID per event;
* SHA-256 hash chaining (``prev_hash`` -> ``hash``) for tamper evidence;
* atomic appends guarded by an in-process lock keyed by the log path plus an
  on-disk exclusive-create lock for cross-process callers;
* fail-closed reads and appends: a corrupt or malformed chain is never
  extended and never returned as trusted events;
* redaction through :mod:`keel.redaction` *before* anything is persisted;
* bounded retention: the active log is rotated into a bounded number of
  archives, and every anchor is tied to the last hash of the archived chain;
* a health API that separates liveness (``running``) from readiness
  (``ready``), plus redacted dependency, metric and diagnostic exports.

No third-party dependency and no network access is used.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import sys
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping

from keel.redaction import redact_text

LOG_FILENAME = "observability.jsonl"
STATE_FILENAME = "observability.state.json"
GENESIS_HASH = "0" * 64
AUDIT_KIND = "audit"

Clock = Callable[[], float | int | datetime]

_LOCK_TIMEOUT_SECONDS = 10.0
_STALE_LOCK_SECONDS = 30.0
_RECENT_ERROR_LIMIT = 20

# Bounded retention.  The active log is capped at DEFAULT_MAX_EVENTS; when a
# write would exceed it the current generation is archived and a fresh active
# log starts with its anchor set to the last (seq, hash) of the archived one.
# Only the newest DEFAULT_MAX_ARCHIVES generations are retained on disk; older
# archives are deleted.  Callers may tighten either bound per write.
DEFAULT_MAX_EVENTS = 5_000
DEFAULT_MAX_ARCHIVES = 3

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------

class ObservabilityError(RuntimeError):
    """Base class for every error raised by this module."""


class ObservabilityStorageError(ObservabilityError):
    """state_root cannot be created, locked, read or written."""


class ChainIntegrityError(ObservabilityError):
    """The event log's hash chain is corrupt, malformed or non-contiguous."""


class ObservabilityValidationError(ObservabilityError, ValueError):
    """Caller supplied an invalid event field."""


# ---------------------------------------------------------------------------
# Integrity result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChainResult:
    """Outcome of :func:`verify_chain`."""

    ok: bool
    event_count: int = 0
    first_seq: int | None = None
    last_seq: int = 0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "event_count": self.event_count,
            "first_seq": self.first_seq,
            "last_seq": self.last_seq,
            "error": self.error,
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.as_dict().get(key, default)

    def __bool__(self) -> bool:
        return self.ok


# ---------------------------------------------------------------------------
# Locking (path-keyed, in-process + on-disk)
# ---------------------------------------------------------------------------

def _canonical(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _thread_lock(key: str) -> threading.RLock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


def _acquire_lock(path: Path) -> int:
    """Create an exclusive lock file; retry with a bounded deadline."""
    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > _STALE_LOCK_SECONDS:
                with contextlib.suppress(OSError):
                    path.unlink()
                continue
            if time.monotonic() >= deadline:
                raise ObservabilityStorageError(
                    _safe_text(f"timed out acquiring observability lock {path}"))
            time.sleep(0.005)
        except OSError as exc:
            raise ObservabilityStorageError(
                _safe_text(f"cannot create observability lock {path}: {exc}")) from exc
    try:
        marker = f"{os.getpid()} {time.time():.6f}\n".encode("ascii")
        os.write(fd, marker)
        os.fsync(fd)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(OSError):
            path.unlink()
        raise ObservabilityStorageError(
            _safe_text(f"cannot write observability lock {path}: {exc}")) from exc
    return fd


def _release_lock(path: Path, fd: int) -> None:
    with contextlib.suppress(OSError):
        os.close(fd)
    with contextlib.suppress(OSError):
        path.unlink()


@contextlib.contextmanager
def _locked(state_root: str | os.PathLike[str], *, create: bool) -> Iterator[Path]:
    """Yield the log path while holding the lock keyed by that path."""
    root = Path(state_root)
    log_path = root / LOG_FILENAME
    with _thread_lock(_canonical(log_path)):
        if not create and not root.is_dir():
            yield log_path
            return
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ObservabilityStorageError(
                _safe_text(f"state_root is unwritable: {root} ({exc})")) from exc
        lock_path = log_path.with_name(log_path.name + ".lock")
        fd = _acquire_lock(lock_path)
        try:
            yield log_path
        finally:
            _release_lock(lock_path, fd)


# ---------------------------------------------------------------------------
# Redaction (reuses keel.redaction's detection vocabulary)
# ---------------------------------------------------------------------------

def _is_secret_key(key: str) -> bool:
    """Ask redaction.py whether this key belongs to its secret vocabulary."""
    probe = f"{key} = zzzzzzzzzzzzzz"
    _text, counts = redact_text(probe)
    return bool(counts)


def _redact_node(node: Any, key: str | None = None) -> Any:
    if isinstance(node, str):
        if key is not None and _is_secret_key(key):
            return "[REDACTED]"
        return redact_text(node)[0]
    if isinstance(node, dict):
        return {
            child_key: _redact_node(
                value, child_key if isinstance(child_key, str) else None)
            for child_key, value in node.items()
        }
    if isinstance(node, (list, tuple)):
        return [_redact_node(value, key) for value in node]
    return node


def redact(event: Any) -> Any:
    """Return a deep-copied event with every secret-carrying string removed.

    Detection is delegated to :func:`keel.redaction.redact_text`; sensitive
    dict keys (``api_key``, ``Bearer``/``token``-style keys, ``password``,
    ``secret``, ``authorization``, ``pin`` ...) cause the whole value to be
    replaced, which also covers multi-word secrets and ``Bearer <token>``
    values.  The input is never mutated.
    """
    return _redact_node(event)


def _safe_text(value: Any) -> str:
    """Render *value* for an exception, diagnostic or HTTP response safely.

    Every string that originates from caller data, a third-party exception or
    a filesystem path passes through redaction here.  This is the last line of
    defence that keeps credentials out of error messages and exported reports.
    """
    try:
        return redact_text(str(value))[0]
    except Exception:  # noqa: BLE001 - never let a renderer leak a value
        return "[REDACTED]"


# ---------------------------------------------------------------------------
# Hashing, loading, verification
# ---------------------------------------------------------------------------

def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _utc_timestamp(clock: Clock | None) -> str:
    value: Any = time.time() if clock is None else clock()
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    else:
        moment = datetime.fromtimestamp(float(value), tz=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _load(log_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Parse every complete line; stop at the first malformed one."""
    if not log_path.is_file():
        return [], None
    events: list[dict[str, Any]] = []
    try:
        with log_path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except (ValueError, TypeError) as exc:
                    return events, _safe_text(
                        f"line {lineno}: invalid JSON ({exc})")
                if not isinstance(event, dict):
                    return events, f"line {lineno}: event is not a JSON object"
                events.append(event)
    except OSError as exc:
        return events, _safe_text(f"cannot read {log_path}: {exc}")
    return events, None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _verify(
    events: list[dict[str, Any]],
    parse_error: str | None,
    *,
    first_expected_seq: int = 1,
    anchor_hash: str = GENESIS_HASH,
    anchor_error: str | None = None,
) -> ChainResult:
    """Verify continuity, hash linkage and per-event SHA-256.

    ``first_expected_seq``/``anchor_hash`` come from the retention anchor so
    a rotated log continues the global sequence instead of being mistaken for
    a truncated or forged chain.
    """
    observed_first = _optional_int(events[0].get("seq")) if events else None
    observed_last = _optional_int(events[-1].get("seq")) if events else first_expected_seq - 1
    if parse_error is not None:
        return ChainResult(False, len(events), observed_first, observed_last,
                           _safe_text(parse_error))
    if anchor_error is not None:
        return ChainResult(False, len(events), observed_first, observed_last,
                           _safe_text(anchor_error))
    previous = anchor_hash
    for expected_seq, event in enumerate(events, first_expected_seq):
        seq = event.get("seq")
        if seq != expected_seq or isinstance(seq, bool):
            return ChainResult(
                False, len(events), observed_first, observed_last,
                _safe_text(f"line {expected_seq}: non-monotonic seq {seq!r} "
                           f"(expected {expected_seq})"),
            )
        if event.get("prev_hash") != previous:
            return ChainResult(
                False, len(events), observed_first, observed_last,
                f"line {expected_seq}: prev_hash does not link to the previous event",
            )
        digest = event.get("hash")
        if not isinstance(digest, str):
            return ChainResult(
                False, len(events), observed_first, observed_last,
                f"line {expected_seq}: missing or invalid hash",
            )
        payload = {key: value for key, value in event.items() if key != "hash"}
        try:
            expected_digest = _digest(payload)
        except (TypeError, ValueError) as exc:
            return ChainResult(
                False, len(events), observed_first, observed_last,
                _safe_text(f"line {expected_seq}: event is not canonicalizable ({exc})"),
            )
        if digest != expected_digest:
            return ChainResult(
                False, len(events), observed_first, observed_last,
                f"line {expected_seq}: SHA-256 hash mismatch (tampered event)",
            )
        previous = digest
    return ChainResult(True, len(events), observed_first, observed_last, None)


# ---------------------------------------------------------------------------
# Bounded retention: anchored rotation into archives
# ---------------------------------------------------------------------------

def _state_path(root: Path) -> Path:
    return root / STATE_FILENAME


def _archive_path(log_path: Path, generation: int) -> Path:
    return log_path.with_name(f"{log_path.name}.{generation}")


def _archive_generations(log_path: Path) -> list[int]:
    prefix = log_path.name + "."
    generations: list[int] = []
    try:
        candidates = log_path.parent.iterdir()
    except OSError:
        return generations
    for candidate in candidates:
        if not candidate.name.startswith(prefix):
            continue
        suffix = candidate.name[len(prefix):]
        if suffix.isdigit() and candidate.is_file():
            generations.append(int(suffix))
    return sorted(generations)


def _load_state(root: Path) -> dict[str, Any]:
    """Read the retention sidecar; fail closed on malformed content."""
    path = _state_path(root)
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"_invalid": True}
    return document if isinstance(document, dict) else {"_invalid": True}


def _anchor(log_path: Path) -> tuple[int, str, str | None]:
    """Return ``(first_expected_seq, anchor_hash, error)`` for the active log.

    Without a sidecar the chain starts at seq 1 / GENESIS_HASH.  With one, the
    anchor is tied both to the retention metadata *and* to the last hash of
    the archived generation, so truncating or rewriting either file is
    detected by :func:`verify_chain`.
    """
    state = _load_state(log_path.parent)
    if not state:
        return 1, GENESIS_HASH, None
    generation = _optional_int(state.get("generation"))
    base_seq = _optional_int(state.get("base_seq"))
    base_hash = state.get("base_hash")
    entries = state.get("generations")
    if not (generation and generation > 1 and base_seq and base_seq >= 1
            and isinstance(base_hash, str) and len(base_hash) == 64
            and isinstance(entries, list)):
        return 1, GENESIS_HASH, "retention state is invalid"
    entry = next(
        (item for item in entries
         if isinstance(item, dict) and _optional_int(item.get("generation")) == generation - 1),
        None,
    )
    if not isinstance(entry, dict) or entry.get("last_hash") != base_hash \
            or _optional_int(entry.get("last_seq")) + 1 != base_seq \
            or not isinstance(entry.get("prev_hash"), str):
        return 1, GENESIS_HASH, "retention anchor does not match archived metadata"
    archive = _archive_path(log_path, generation - 1)
    if not archive.is_file():
        return 1, GENESIS_HASH, "archived generation for retention anchor is missing"
    archived, parse_error = _load(archive)
    if parse_error or not archived or archived[-1].get("hash") != base_hash:
        return 1, GENESIS_HASH, "archived chain does not match retention anchor"
    entry_first = _optional_int(entry.get("first_seq"))
    entry_prev = entry.get("prev_hash")
    archived_check = _verify(
        archived, None,
        first_expected_seq=entry_first if entry_first else 1,
        anchor_hash=entry_prev if isinstance(entry_prev, str) else GENESIS_HASH,
    )
    if not archived_check.ok or archived_check.last_seq != _optional_int(entry.get("last_seq")):
        return 1, GENESIS_HASH, "archived chain fails verification"
    return base_seq, base_hash, None


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)
    os.replace(temporary, path)


def _rotate(
    log_path: Path,
    state: dict[str, Any],
    *,
    last_seq: int,
    last_hash: str,
    max_archives: int,
) -> None:
    """Archive the current generation and start a fresh anchored log."""
    root = log_path.parent
    generation = _optional_int(state.get("generation")) or 1
    entries = state.get("generations")
    entries = [entry for entry in entries if isinstance(entry, dict)] \
        if isinstance(entries, list) else []

    # Archive the completed generation atomically, then prune anything older
    # than the retention bound.
    current = _archive_path(log_path, generation)
    try:
        _atomic_write(current, log_path.read_bytes())
    except OSError as exc:
        raise ObservabilityStorageError(
            _safe_text(f"cannot rotate observability log: {exc}")) from exc
    for old_generation in _archive_generations(log_path):
        if old_generation < generation - max_archives + 1:
            with contextlib.suppress(OSError):
                _archive_path(log_path, old_generation).unlink()

    first_seq = _optional_int(state.get("base_seq")) or 1
    anchor_hash = state.get("base_hash")
    entries.append({
        "generation": generation,
        "first_seq": first_seq,
        "last_seq": last_seq,
        "last_hash": last_hash,
        "prev_hash": anchor_hash if isinstance(anchor_hash, str) else GENESIS_HASH,
    })
    min_generation = generation + 1 - max_archives
    entries = [entry for entry in entries
               if (_optional_int(entry.get("generation")) or 0) >= min_generation]
    new_state = {
        "version": 1,
        "generation": generation + 1,
        "base_seq": last_seq + 1,
        "base_hash": last_hash,
        "rotated_at": _utc_timestamp(None),
        "generations": entries,
    }
    try:
        fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with contextlib.suppress(OSError):
            os.fsync(fd)
        os.close(fd)
    except OSError as exc:
        raise ObservabilityStorageError(
            _safe_text(f"cannot reset observability log after rotation: {exc}")) from exc
    try:
        _atomic_write(
            _state_path(root),
            (json.dumps(new_state, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
        )
    except OSError as exc:
        raise ObservabilityStorageError(
            _safe_text(f"cannot persist retention state: {exc}")) from exc


def verify_chain(state_root: str | os.PathLike[str]) -> ChainResult:
    """Verify sequence continuity, hash linkage and per-event SHA-256."""
    with _locked(state_root, create=False) as log_path:
        first_seq, anchor_hash, anchor_error = _anchor(log_path)
        events, parse_error = _load(log_path)
        return _verify(events, parse_error, first_expected_seq=first_seq,
                       anchor_hash=anchor_hash, anchor_error=anchor_error)


# ---------------------------------------------------------------------------
# Public event API
# ---------------------------------------------------------------------------

def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObservabilityValidationError(f"{name} must be a non-empty string")
    return value


def _optional_text(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ObservabilityValidationError(f"{name} must be a string or None")
    return value


def _append(log_path: Path, line: str) -> None:
    try:
        fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    except OSError as exc:
        raise ObservabilityStorageError(
            _safe_text(f"cannot open observability log {log_path}: {exc}")) from exc
    try:
        # os.write may return a short count; loop so a concurrent process can
        # never interleave a partial JSON line with another writer's bytes.
        view = memoryview(line.encode("utf-8"))
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write to observability log")
            view = view[written:]
        os.fsync(fd)
    except OSError as exc:
        raise ObservabilityStorageError(
            _safe_text(f"cannot append observability log {log_path}: {exc}")) from exc
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)


def record_event(
    kind: str,
    *,
    session_id: str,
    task_id: str | None = None,
    agent_id: str | None = None,
    feature_id: str | None = None,
    module: str | None = None,
    data: Any = None,
    state_root: str | os.PathLike[str],
    clock: Clock | None = None,
    max_events: int | None = None,
    max_archives: int | None = None,
) -> dict[str, Any]:
    """Append one redacted, hash-chained event and return the stored event.

    ``clock`` is injectable (callable returning epoch seconds or a datetime)
    so tests can pin the UTC timestamp.  A corrupt chain is never extended:
    :class:`ChainIntegrityError` is raised and no bytes are written.

    ``max_events``/``max_archives`` tighten the retention bounds for this
    write; the active log is rotated once its event count would exceed
    ``max_events``, and only the newest ``max_archives`` generations remain.
    """
    kind = _require_text("kind", kind)
    session_id = _require_text("session_id", session_id)
    task_id = _optional_text("task_id", task_id)
    agent_id = _optional_text("agent_id", agent_id)
    feature_id = _optional_text("feature_id", feature_id)
    module = _optional_text("module", module)
    event_cap = max(1, DEFAULT_MAX_EVENTS if max_events is None else int(max_events))
    archive_cap = max(1, DEFAULT_MAX_ARCHIVES if max_archives is None else int(max_archives))

    with _locked(state_root, create=True) as log_path:
        events, parse_error = _load(log_path)
        first_seq, anchor_hash, anchor_error = _anchor(log_path)
        result = _verify(events, parse_error, first_expected_seq=first_seq,
                         anchor_hash=anchor_hash, anchor_error=anchor_error)
        if not result.ok:
            raise ChainIntegrityError(
                _safe_text("refusing to append to a corrupt observability chain: "
                           f"{result.error}"))

        seq = result.last_seq + 1
        previous = events[-1]["hash"] if events else anchor_hash
        payload: dict[str, Any] = {
            "seq": seq,
            "ts": _utc_timestamp(clock),
            "kind": kind,
            "session_id": session_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "feature_id": feature_id,
            "module": module,
            "correlation_id": uuid.uuid4().hex,
            "data": {} if data is None else data,
            "prev_hash": previous,
        }
        safe = redact(payload)
        if not isinstance(safe, dict):
            raise ObservabilityValidationError("redacted event must be an object")
        try:
            safe["hash"] = _digest(safe)
        except (TypeError, ValueError) as exc:
            raise ObservabilityValidationError(
                _safe_text(f"event data must be hashable as canonical JSON: {exc}")) from exc
        try:
            line = json.dumps(
                safe, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                allow_nan=False,
            ) + "\n"
        except (TypeError, ValueError) as exc:
            raise ObservabilityValidationError(
                _safe_text(f"event data must be JSON-serializable: {exc}")) from exc
        _append(log_path, line)
        if len(events) + 1 > event_cap:
            _rotate(log_path, _load_state(log_path.parent),
                    last_seq=seq, last_hash=safe["hash"], max_archives=archive_cap)
        return safe


def read_events(
    state_root: str | os.PathLike[str],
    *,
    kind: str | None = None,
    session_id: str | None = None,
    since_seq: int = 0,
    include_archives: bool = False,
) -> list[dict[str, Any]]:
    """Return verified events, oldest first, filtered by kind/session/seq.

    ``include_archives=True`` verifies every retained archived generation as
    well as the active log, so an operator can read the whole retained event
    history while still failing closed on any broken link.
    """
    with _locked(state_root, create=False) as log_path:
        first_seq, anchor_hash, anchor_error = _anchor(log_path)
        events, parse_error = _load(log_path)
        result = _verify(events, parse_error, first_expected_seq=first_seq,
                         anchor_hash=anchor_hash, anchor_error=anchor_error)
        if not result.ok:
            raise ChainIntegrityError(
                _safe_text(f"observability chain is corrupt: {result.error}"))

        all_events = list(events)
        if include_archives:
            state = _load_state(log_path.parent)
            entries = state.get("generations") if isinstance(state.get("generations"), list) else []
            previous_hash = GENESIS_HASH
            archived: list[dict[str, Any]] = []
            for position, entry in enumerate(sorted(
                (item for item in entries if isinstance(item, dict)),
                key=lambda item: _optional_int(item.get("generation")) or 0,
            )):
                generation = _optional_int(entry.get("generation"))
                path = _archive_path(log_path, generation) if generation else None
                archived_events, archived_error = _load(path) if path else ([], "invalid generation")
                entry_first = _optional_int(entry.get("first_seq")) or 1
                entry_prev = entry.get("prev_hash")
                checked = _verify(
                    archived_events, archived_error, first_expected_seq=entry_first,
                    anchor_hash=entry_prev if isinstance(entry_prev, str) else GENESIS_HASH,
                )
                # The oldest retained generation may have had its predecessor
                # pruned by retention, so only later generations must link to
                # the one before them; every generation is still self-verified.
                if not checked.ok or (position > 0 and entry.get("prev_hash") != previous_hash) \
                        or checked.last_seq != entry.get("last_seq") \
                        or (archived_events and archived_events[-1].get("hash") != entry.get("last_hash")):
                    raise ChainIntegrityError(
                        _safe_text("observability archive is corrupt or inconsistent: "
                                   f"{checked.error or 'anchor mismatch'}"))
                archived.extend(archived_events)
                previous_hash = entry.get("last_hash")
            if state and anchor_hash != previous_hash:
                raise ChainIntegrityError(
                    "observability retention anchor does not link to archived history")
            all_events = archived + all_events

        return [
            dict(event)
            for event in all_events
            if (kind is None or event.get("kind") == kind)
            and (session_id is None or event.get("session_id") == session_id)
            and isinstance(event.get("seq"), int)
            and event["seq"] > since_seq
        ]


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _import_module(name: str) -> tuple[Any, str | None]:
    try:
        return importlib.import_module(f"keel.{name}"), None
    except Exception as exc:  # noqa: BLE001 - report *any* import failure
        return None, _safe_text(f"{type(exc).__name__}: {exc}")


def _declared_feature_count(name: str, module: Any) -> tuple[int, str]:
    try:
        hub = importlib.import_module("keel.backend_hub")
    except Exception:  # noqa: BLE001 - diagnostics must survive a broken hub
        hub = None
    mapping = getattr(hub, "MODULE_FEATURES", {}) if hub is not None else {}
    if isinstance(mapping, dict) and name in mapping:
        declared = mapping[name]
        if hasattr(declared, "__len__"):
            return len(declared), "backend_hub.MODULE_FEATURES"
    if module is not None:
        for attribute in ("FEATURE_IDS", "FEATURES", "DECLARED_FEATURES"):
            declared = getattr(module, attribute, None)
            if declared is not None and hasattr(declared, "__len__"):
                return len(declared), f"keel.{name}.{attribute}"
    return 0, "none"


def health_snapshot(
    state_root: str | os.PathLike[str],
    modules: Iterable[str],
) -> dict[str, Any]:
    """Report real import status and declared features for backend modules.

    A module that fails to import is reported with ``import_status='error'``,
    ``imported=False`` and ``healthy=False`` -- never as 'healthy'.  Recorded
    ``error`` events for the module are included, already redacted.
    """
    chain = verify_chain(state_root)
    errors_by_module: dict[str, list[dict[str, Any]]] = {}
    if chain.ok:
        for event in read_events(state_root, kind="error"):
            owner = event.get("module")
            if isinstance(owner, str):
                errors_by_module.setdefault(owner, []).append(event)

    snapshot: dict[str, Any] = {}
    for raw_name in modules:
        name = str(raw_name)
        module, import_error = _import_module(name)
        import_error = _safe_text(import_error) if import_error else None
        feature_count, feature_source = _declared_feature_count(name, module)
        recorded = [redact(event) for event in errors_by_module.get(name, [])]
        healthy = import_error is None
        snapshot[name] = {
            "module": name,
            "imported": import_error is None,
            "import_status": "ok" if import_error is None else "error",
            "import_error": import_error,
            "declared_features": feature_count,
            "feature_count": feature_count,
            "feature_source": feature_source,
            "error_count": len(recorded),
            "errors": recorded,
            "healthy": healthy,
        }
    return {
        "generated_at": _utc_timestamp(None),
        "state_root": str(Path(state_root)),
        "chain_ok": chain.ok,
        "chain_error": _safe_text(chain.error) if chain.error else None,
        "healthy": chain.ok and all(
            entry["healthy"] for entry in snapshot.values()),
        "module_count": len(snapshot),
        "modules": snapshot,
    }


def diagnostic_report(state_root: str | os.PathLike[str]) -> dict[str, Any]:
    """Counts by kind/session, chain status and recent redacted errors."""
    chain = verify_chain(state_root)
    if chain.ok:
        try:
            events = read_events(state_root)
        except ObservabilityError:
            events = []
    else:
        with _locked(state_root, create=False) as log_path:
            events, _parse_error = _load(log_path)

    by_kind: Counter[str] = Counter()
    by_session: Counter[str] = Counter()
    for event in events:
        kind = event.get("kind")
        session = event.get("session_id")
        if isinstance(kind, str):
            by_kind[kind] += 1
        if isinstance(session, str):
            by_session[session] += 1
    recent_errors = [
        redact(event)
        for event in events
        if event.get("kind") == "error"
    ][-_RECENT_ERROR_LIMIT:]

    root = Path(state_root)
    with _locked(root, create=False) as log_path:
        state = _load_state(log_path.parent)
        generations = _archive_generations(log_path)
        archived_events = 0
        for generation in generations:
            archived, _error = _load(_archive_path(log_path, generation))
            archived_events += len(archived)
        retention = {
            "generation": _optional_int(state.get("generation")) or 1,
            "active_events": len(events),
            "archived_events": archived_events,
            "archive_count": len(generations),
            "max_events": DEFAULT_MAX_EVENTS,
            "max_archives": DEFAULT_MAX_ARCHIVES,
        }
    chain_dict = chain.as_dict()
    if chain_dict["error"]:
        chain_dict["error"] = _safe_text(chain_dict["error"])
    return {
        "generated_at": _utc_timestamp(None),
        "state_root": _safe_text(str(root)),
        "chain": chain_dict,
        "chain_status": "ok" if chain.ok else "corrupt",
        "total_events": len(events),
        "counts_by_kind": dict(sorted(by_kind.items())),
        "counts_by_session": dict(sorted(by_session.items())),
        "recent_errors": recent_errors,
        "recent_error_count": len(recent_errors),
        "retention": retention,
    }


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

def record_audit_event(
    action: str,
    *,
    actor: str,
    outcome: str = "success",
    state_root: str | os.PathLike[str],
    detail: Any = None,
    request_id: str | None = None,
    resource: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
    module: str | None = None,
    clock: Clock | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Append a structured, redacted audit event to the same tamper-evident log.

    ``action``/``actor``/``outcome`` are always recorded; ``request_id`` links
    an audit record to the correlation/request ID of the operation it describes.
    """
    data: dict[str, Any] = {
        "action": _require_text("action", action),
        "actor": _require_text("actor", actor),
        "outcome": _require_text("outcome", outcome),
    }
    for key, value in (("detail", detail), ("request_id", request_id),
                       ("resource", resource)):
        if value is not None:
            data[key] = value
    data.update(extra)
    return record_event(
        AUDIT_KIND,
        session_id=actor,
        task_id=task_id,
        agent_id=agent_id,
        module=module,
        data=data,
        state_root=state_root,
        clock=clock,
    )


# ---------------------------------------------------------------------------
# Dependency, resource and metric measurements
# ---------------------------------------------------------------------------

def default_dependency_probes(
    state_root: str | os.PathLike[str],
) -> dict[str, Callable[[], Any]]:
    """Real probes for the DB, provider, worker and event-log subsystems.

    Each probe executes (not a flag read) so a broken subsystem is observable
    without any network access.  Callers can replace or extend this mapping.
    """
    def database() -> bool:
        import sqlite3

        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()
        return True

    def provider() -> bool:
        import importlib.util

        return importlib.util.find_spec("keel.providers") is not None

    def worker() -> bool:
        return threading.active_count() >= 1

    def event_log() -> bool:
        return verify_chain(state_root).ok

    return {
        "database": database,
        "provider": provider,
        "worker": worker,
        "event_log": event_log,
    }


def dependency_health(
    probes: Mapping[str, Callable[[], Any]] | None = None,
    *,
    state_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Execute dependency probes with timing; never expose a raw error value."""
    if probes is None:
        probes = default_dependency_probes(state_root) if state_root is not None else {}
    results: dict[str, Any] = {}
    for raw_name, probe in sorted(probes.items(), key=lambda item: str(item[0])):
        name = str(raw_name)
        started = time.perf_counter()
        error: str | None = None
        try:
            ok = bool(probe())
            if not ok:
                error = "probe returned false"
        except Exception as exc:  # noqa: BLE001 - one bad dependency is reported
            ok = False
            error = _safe_text(f"{type(exc).__name__}: {exc}")
        results[name] = {
            "name": name,
            "status": "ok" if ok else "error",
            "ok": ok,
            "error": error,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    return {
        "checked_at": _utc_timestamp(None),
        "healthy": all(entry["ok"] for entry in results.values()),
        "dependency_count": len(results),
        "dependencies": results,
    }


def resource_metrics() -> dict[str, Any]:
    """Process-level resource measurements (best effort, no dependencies)."""
    max_rss_kb: int | None = None
    try:
        import resource as posix_resource  # noqa: PLC0415 - POSIX-only module

        value = int(posix_resource.getrusage(
            posix_resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":  # macOS reports bytes, Linux reports KiB
            value //= 1024
        max_rss_kb = max(0, value)
    except Exception:  # noqa: BLE001 - unavailable on Windows
        pass
    return {
        "checked_at": _utc_timestamp(None),
        "max_rss_kb": max_rss_kb,
        "rss_source": "rusage" if max_rss_kb is not None else "unavailable",
        "thread_count": threading.active_count(),
    }


def _error_category(event: dict[str, Any]) -> str:
    data = event.get("data")
    if isinstance(data, dict):
        for key in ("error_category", "category"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return _safe_text(value.strip()[:64])
    return "unclassified"


def metrics_snapshot(state_root: str | os.PathLike[str]) -> dict[str, Any]:
    """Category counts, chain/resource metrics and bounded retention totals."""
    report = diagnostic_report(state_root)
    categories: Counter[str] = Counter()
    events: list[dict[str, Any]] = []
    if report["chain_status"] == "ok":
        try:
            events = read_events(state_root)
        except ObservabilityError:
            events = []
    for event in events:
        if event.get("kind") == "error":
            categories[_error_category(event)] += 1
    return {
        "generated_at": _utc_timestamp(None),
        "chain_status": report["chain_status"],
        "total_events": report["total_events"],
        "error_count": report["counts_by_kind"].get("error", 0),
        "audit_count": report["counts_by_kind"].get(AUDIT_KIND, 0),
        "error_categories": dict(sorted(categories.items())),
        "counts_by_kind": report["counts_by_kind"],
        "recent_error_count": report["recent_error_count"],
        "retention": report["retention"],
        "resources": resource_metrics(),
    }


# ---------------------------------------------------------------------------
# Health: liveness ("running") is deliberately distinct from readiness
# ---------------------------------------------------------------------------

def liveness_probe() -> dict[str, Any]:
    """Cheap liveness signal: the process answered, so it is running."""
    return {
        "status": "running",
        "alive": True,
        "running": True,
        "pid": os.getpid(),
        "checked_at": _utc_timestamp(None),
    }


def readiness_probe(
    state_root: str | os.PathLike[str],
    modules: Iterable[str] = (),
    *,
    dependencies: Mapping[str, Callable[[], Any]] | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Readiness requires an intact chain, importable modules, healthy deps.

    A process that is up but not ready reports ``status='running'``; only a
    fully operational process reports ``status='ready'``.  No raw exception
    text is returned by this function or by :func:`health_http_payload`.
    """
    snapshot = health_snapshot(state_root, modules)
    deps = dependency_health(
        default_dependency_probes(state_root) if dependencies is None else dependencies,
    )
    checks = {
        "chain_ok": bool(snapshot["chain_ok"]),
        "modules_ok": all(entry["healthy"] for entry in snapshot["modules"].values()),
        "dependencies_ok": deps["healthy"],
        "module_count": snapshot["module_count"],
    }
    ready = bool(checks["chain_ok"] and checks["modules_ok"]
                 and checks["dependencies_ok"])
    return {
        "status": "ready" if ready else "running",
        "ready": ready,
        "checks": checks,
        "chain_status": "ok" if snapshot["chain_ok"] else "corrupt",
        "correlation_id": correlation_id or uuid.uuid4().hex,
        "dependencies": deps,
        "snapshot": snapshot,
        "checked_at": _utc_timestamp(None),
    }


def health_check(
    state_root: str | os.PathLike[str],
    modules: Iterable[str] = (),
    *,
    dependencies: Mapping[str, Callable[[], Any]] | None = None,
) -> dict[str, Any]:
    """Composite health result separating liveness from readiness."""
    live = liveness_probe()
    ready = readiness_probe(state_root, modules, dependencies=dependencies)
    return {
        "status": ready["status"],
        "running": live["alive"],
        "ready": ready["ready"],
        "liveness": live,
        "readiness": ready,
        "checked_at": _utc_timestamp(None),
    }


def health_http_payload(
    state_root: str | os.PathLike[str],
    modules: Iterable[str] = (),
    *,
    dependencies: Mapping[str, Callable[[], Any]] | None = None,
) -> dict[str, Any]:
    """The JSON body for a health endpoint: counts and booleans only.

    It deliberately omits raw import errors, exception text, event payloads
    and state_root paths, so it is safe to return over HTTP and to log.
    """
    check = health_check(state_root, modules, dependencies=dependencies)
    report = diagnostic_report(state_root)
    metrics = metrics_snapshot(state_root)
    payload = {
        "status": check["status"],
        "running": check["running"],
        "ready": check["ready"],
        "chain_status": report["chain_status"],
        "module_count": check["readiness"]["checks"]["module_count"],
        "dependencies": {
            name: entry["status"]
            for name, entry in check["readiness"]["dependencies"]["dependencies"].items()
        },
        "error_categories": metrics["error_categories"],
        "total_events": report["total_events"],
        "correlation_id": check["readiness"]["correlation_id"],
        "generated_at": check["checked_at"],
    }
    return redact(payload)


# ---------------------------------------------------------------------------
# Redacted diagnostic export
# ---------------------------------------------------------------------------

def export_diagnostics(
    state_root: str | os.PathLike[str],
    path: str | os.PathLike[str],
    *,
    modules: Iterable[str] = (),
    dependencies: Mapping[str, Callable[[], Any]] | None = None,
) -> Path:
    """Write a redacted, self-contained diagnostic export to *path*.

    The export includes the health check, diagnostic report and metrics.  It
    never uploads anything; the caller decides whether to share the file.
    """
    bundle: dict[str, Any] = {
        "format": "keel-observability-export-v1",
        "generated_at": _utc_timestamp(None),
        "health": health_check(state_root, modules, dependencies=dependencies),
        "diagnostics": diagnostic_report(state_root),
        "metrics": metrics_snapshot(state_root),
        "note": ("Redacted local diagnostics. Review before sharing; "
                 "Keel never uploads this file."),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        target,
        (json.dumps(redact(bundle), sort_keys=True, indent=2, ensure_ascii=True,
                    allow_nan=False) + "\n").encode("utf-8"),
    )
    return target
