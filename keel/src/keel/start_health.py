"""Auto-rollback after repeated failed starts (B4.13).

Tracks consecutive failed launches of a version in a local JSON file. After a
configurable number of failures, the caller is instructed to restore the
previous installation via the existing ``updater.rollback``. Successful starts
reset the counter.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

DEFAULT_THRESHOLD = 3


def state_path(state_root: str) -> Path:
    raw = os.environ.get("KEEL_START_HEALTH_FILE")
    return Path(raw) if raw else Path(state_root) / "start-health.json"


def _load(state_root: str) -> dict:
    path = state_path(state_root)
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _save(state_root: str, doc: dict) -> None:
    """Persist the counters atomically.

    A torn write (crash, disk-full, lock) must never leave a truncated JSON
    file: ``_load`` treats an unreadable file as empty state, which would reset
    the consecutive-failure counter and silently defeat auto-rollback. Write to
    a sibling temp file and replace the real file only once the bytes are
    complete.
    """
    path = state_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def record_start(state_root: str, version: str, *, ok: bool,
                 threshold: int = DEFAULT_THRESHOLD) -> dict:
    doc = _load(state_root)
    entry = dict(doc.get(version, {}) or {})
    entry["failures"] = 0 if ok else int(entry.get("failures", 0)) + 1
    entry["last"] = "ok" if ok else "failed"
    doc[version] = entry
    _save(state_root, doc)
    return {"version": version,
            "failures": entry["failures"],
            "rollback": entry["failures"] >= max(1, threshold)}


def reset(state_root: str, version: str | None = None) -> None:
    if version is None:
        _save(state_root, {})
        return
    doc = _load(state_root)
    doc.pop(version, None)
    _save(state_root, doc)
