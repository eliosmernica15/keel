"""Recoverable local trash for Keel agent file deletions (C8.1)."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
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


def move_to_trash(path: Path) -> dict:
    """Move *path* into trash and return restore metadata."""
    source = Path(path).resolve()
    if not source.exists():
        raise TrashError(f"not found: {source}")
    root = trash_root()
    trash_id = f"{int(time.time())}-{uuid.uuid4().hex[:12]}"
    target = root / f"{trash_id}-{source.name}"
    shutil.move(str(source), str(target))
    meta = {
        "id": trash_id,
        "original_path": str(source),
        "trashed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "name": source.name,
    }
    (root / f"{trash_id}.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def restore(trash_id: str) -> Path:
    root = trash_root()
    meta_path = root / f"{trash_id}.json"
    if not meta_path.is_file():
        raise TrashError(f"unknown trash id: {trash_id}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    candidates = [p for p in root.glob(f"{trash_id}-*") if not p.suffix == ".json"]
    if len(candidates) != 1:
        raise TrashError(f"trash item missing: {trash_id}")
    dest = Path(meta["original_path"])
    if dest.exists():
        raise TrashError(f"destination already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(candidates[0]), str(dest))
    meta_path.unlink()
    return dest


def list_items() -> list[dict]:
    root = trash_root()
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(root.glob("*.json"))]
