"""Recoverable local trash for Keel agent file deletions (C8.1)."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


class TrashError(RuntimeError):
    pass


def trash_root() -> Path:
    raw = os.environ.get(
        "KEEL_TRASH_DIR",
        str(Path(os.environ.get("KEEL_STATE_DIR",
                                 str(Path.home() / ".keel"))) / "trash"))
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_meta(root: Path, trash_id: str, meta: dict) -> None:
    """Publish metadata atomically so a crash cannot leave torn JSON."""
    path = root / f"{trash_id}.json"
    tmp = path.with_name(f".{path.name}.{os.urandom(6).hex()}.tmp")
    try:
        tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _parse_ts(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def _retention_limits() -> tuple[float, int]:
    try:
        days = float(os.environ.get("KEEL_TRASH_RETENTION_DAYS", "30"))
    except ValueError:
        days = 30.0
    try:
        max_items = int(os.environ.get("KEEL_TRASH_MAX_ITEMS", "100"))
    except ValueError:
        max_items = 100
    return days, max_items


def _load_meta(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(doc, dict) or not doc.get("id")
            or not doc.get("original_path")):
        return None
    return doc


def purge_expired() -> int:
    """Drop metadata/data past the age or count limit. Returns items purged.

    Retention is configured with ``KEEL_TRASH_RETENTION_DAYS`` (default 30)
    and ``KEEL_TRASH_MAX_ITEMS`` (default 100). Corrupt or foreign JSON files
    are ignored rather than deleting unrelated state.
    """
    root = trash_root()
    days, max_items = _retention_limits()
    now = datetime.now(timezone.utc)

    entries: list[tuple[Path, dict]] = []
    for meta_path in sorted(root.glob("*.json")):
        doc = _load_meta(meta_path)
        if doc is not None:
            entries.append((meta_path, doc))

    doomed: set[Path] = set()
    for meta_path, doc in entries:
        ts = _parse_ts(doc.get("trashed_at"))
        if (ts is not None and days >= 0
                and (now - ts).total_seconds() > days * 86400):
            doomed.add(meta_path)

    if 0 <= max_items < len(entries):
        keep_newest = len(entries) - max_items
        oldest = sorted(
            entries,
            key=lambda item: (
                _parse_ts(item[1].get("trashed_at"))
                or datetime.min.replace(tzinfo=timezone.utc),
                item[0].stat().st_mtime_ns,
            ),
        )
        doomed.update(path for path, _ in oldest[:keep_newest])

    for meta_path in doomed:
        doc = _load_meta(meta_path)
        if doc is not None:
            trash_id = doc["id"]
            for blob in root.glob(f"{trash_id}-*"):
                if blob.is_file() and blob != meta_path:
                    blob.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
    return len(doomed)


def move_to_trash(path: Path) -> dict:
    """Move *path* into trash and return restore metadata."""
    source = Path(path).resolve()
    if not source.exists():
        raise TrashError(f"not found: {source}")
    root = trash_root()
    purge_expired()
    trash_id = f"{int(time.time())}-{uuid.uuid4().hex[:12]}"
    target = root / f"{trash_id}-{source.name}"
    shutil.move(str(source), str(target))
    meta = {
        "id": trash_id,
        "original_path": str(source),
        "trashed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "name": source.name,
    }
    _write_meta(root, trash_id, meta)
    return meta


def restore(trash_id: str) -> Path:
    root = trash_root()
    meta_path = root / f"{trash_id}.json"
    if not meta_path.is_file():
        raise TrashError(f"unknown trash id: {trash_id}")
    meta = _load_meta(meta_path)
    if meta is None:
        raise TrashError(f"corrupt trash metadata: {trash_id}")
    # Match the data blob by name, not by suffix: a trashed config.json is
    # still a data blob, not metadata.
    candidates = [p for p in root.glob(f"{trash_id}-*")
                  if p.is_file() and p != meta_path]
    if len(candidates) != 1:
        raise TrashError(f"trash item missing: {trash_id}")
    dest = Path(meta["original_path"])
    if dest.exists():
        raise TrashError(f"destination already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(candidates[0]), str(dest))
    meta_path.unlink(missing_ok=True)
    return dest


def list_items() -> list[dict]:
    root = trash_root()
    purge_expired()
    items = []
    for meta_path in sorted(root.glob("*.json")):
        doc = _load_meta(meta_path)
        if doc is not None:
            items.append(doc)
    return items
