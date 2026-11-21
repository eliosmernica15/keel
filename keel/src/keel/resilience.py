"""Trust and resilience helpers (C8.4, C8.6, C8.7).

Canary files that should never be read, a content-addressable artifact store
with dedupe/integrity, and SQLite integrity check + backup helpers. All local.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


class CanaryFiles:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "canary-files.json"

    def _load(self) -> list[str]:
        if not self.path.is_file():
            return []
        import json
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            return list(doc) if isinstance(doc, list) else []
        except (OSError, ValueError):
            return []

    def add(self, path: str) -> None:
        paths = self._load()
        if path not in paths:
            paths.append(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        import json
        self.path.write_text(json.dumps(paths) + "\n", encoding="utf-8")

    def touches(self, path: str) -> bool:
        return any(path == canary or path.startswith(canary.rstrip("/") + "/")
                   for canary in self._load())


class ContentStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def put(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        target = self.root / digest[:2] / digest
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return digest

    def get(self, digest: str) -> bytes | None:
        target = self.root / digest[:2] / digest
        if not target.is_file():
            return None
        data = target.read_bytes()
        return data if hashlib.sha256(data).hexdigest() == digest else None


def db_integrity(db_path: str | Path) -> bool:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()
    return bool(result) and result[0] == "ok"


def db_backup(db_path: str | Path, target: str | Path) -> Path:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as source:
        with sqlite3.connect(target) as dest:
            source.backup(dest)
    return target
