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
* redaction through :mod:`keel.redaction` *before* anything is persisted.

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
from typing import Any, Callable, Iterable, Iterator

from keel.redaction import redact_text

LOG_FILENAME = "observability.jsonl"
GENESIS_HASH = "0" * 64

Clock = Callable[[], float | int | datetime]

_LOCK_TIMEOUT_SECONDS = 10.0
_STALE_LOCK_SECONDS = 30.0
_RECENT_ERROR_LIMIT = 20

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
                    f"timed out acquiring observability lock {path}")
            time.sleep(0.005)
        except OSError as exc:
            raise ObservabilityStorageError(
                f"cannot create observability lock {path}: {exc}") from exc
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
            f"cannot write observability lock {path}: {exc}") from exc
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
                f"state_root is unwritable: {root} ({exc})") from exc
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
                    return events, f"line {lineno}: invalid JSON ({exc})"
                if not isinstance(event, dict):
                    return events, f"line {lineno}: event is not a JSON object"
                events.append(event)
    except OSError as exc:
        return events, f"cannot read {log_path}: {exc}"
    return events, None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _verify(events: list[dict[str, Any]], parse_error: str | None) -> ChainResult:
    count = len(events)
    first_seq = _optional_int(events[0].get("seq")) if events else None
    last_seq = _optional_int(events[-1].get("seq")) if events else 0
    if parse_error is not None:
        return ChainResult(False, count, first_seq, last_seq, parse_error)
    previous = GENESIS_HASH
    for expected_seq, event in enumerate(events, 1):
        seq = event.get("seq")
        if seq != expected_seq or isinstance(seq, bool):
            return ChainResult(
                False, count, first_seq, last_seq,
                f"line {expected_seq}: non-monotonic seq {seq!r} "
                f"(expected {expected_seq})",
            )
        if event.get("prev_hash") != previous:
            return ChainResult(
                False, count, first_seq, last_seq,
                f"line {expected_seq}: prev_hash does not link to the previous event",
            )
        digest = event.get("hash")
        if not isinstance(digest, str):
            return ChainResult(
                False, count, first_seq, last_seq,
                f"line {expected_seq}: missing or invalid hash",
            )
        payload = {key: value for key, value in event.items() if key != "hash"}
        try:
            expected_digest = _digest(payload)
        except (TypeError, ValueError) as exc:
            return ChainResult(
                False, count, first_seq, last_seq,
                f"line {expected_seq}: event is not canonicalizable ({exc})",
            )
        if digest != expected_digest:
            return ChainResult(
                False, count, first_seq, last_seq,
                f"line {expected_seq}: SHA-256 hash mismatch (tampered event)",
            )
        previous = digest
    return ChainResult(True, count, first_seq, last_seq, None)


def verify_chain(state_root: str | os.PathLike[str]) -> ChainResult:
    """Verify sequence continuity, hash linkage and per-event SHA-256."""
    with _locked(state_root, create=False) as log_path:
        events, parse_error = _load(log_path)
        return _verify(events, parse_error)


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
            f"cannot open observability log {log_path}: {exc}") from exc
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    except OSError as exc:
        raise ObservabilityStorageError(
            f"cannot append observability log {log_path}: {exc}") from exc
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
) -> dict[str, Any]:
    """Append one redacted, hash-chained event and return the stored event.

    ``clock`` is injectable (callable returning epoch seconds or a datetime)
    so tests can pin the UTC timestamp.  A corrupt chain is never extended:
    :class:`ChainIntegrityError` is raised and no bytes are written.
    """
    kind = _require_text("kind", kind)
    session_id = _require_text("session_id", session_id)
    task_id = _optional_text("task_id", task_id)
    agent_id = _optional_text("agent_id", agent_id)
    feature_id = _optional_text("feature_id", feature_id)
    module = _optional_text("module", module)

    with _locked(state_root, create=True) as log_path:
        events, parse_error = _load(log_path)
        result = _verify(events, parse_error)
        if not result.ok:
            raise ChainIntegrityError(
                f"refusing to append to a corrupt observability chain: {result.error}")

        seq = result.last_seq + 1
        previous = events[-1]["hash"] if events else GENESIS_HASH
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
                f"event data must be hashable as canonical JSON: {exc}") from exc
        try:
            line = json.dumps(
                safe, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                allow_nan=False,
            ) + "\n"
        except (TypeError, ValueError) as exc:
            raise ObservabilityValidationError(
                f"event data must be JSON-serializable: {exc}") from exc
        _append(log_path, line)
        return safe


def read_events(
    state_root: str | os.PathLike[str],
    *,
    kind: str | None = None,
    session_id: str | None = None,
    since_seq: int = 0,
) -> list[dict[str, Any]]:
    """Return verified events, oldest first, filtered by kind/session/seq."""
    with _locked(state_root, create=False) as log_path:
        events, parse_error = _load(log_path)
        result = _verify(events, parse_error)
        if not result.ok:
            raise ChainIntegrityError(
                f"observability chain is corrupt: {result.error}")
        return [
            dict(event)
            for event in events
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
        return None, f"{type(exc).__name__}: {exc}"


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
        "chain_error": chain.error,
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
    return {
        "generated_at": _utc_timestamp(None),
        "state_root": str(Path(state_root)),
        "chain": chain.as_dict(),
        "chain_status": "ok" if chain.ok else "corrupt",
        "total_events": len(events),
        "counts_by_kind": dict(sorted(by_kind.items())),
        "counts_by_session": dict(sorted(by_session.items())),
        "recent_errors": recent_errors,
        "recent_error_count": len(recent_errors),
    }
