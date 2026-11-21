"""Real file/folder watcher triggers (C5.4).

A stdlib polling watcher that detects new/changed files and dispatches them to
a handler. No third-party watcher dependency; bounded by an ignore list.
"""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

SKIP = frozenset({".git", "node_modules", "__pycache__", ".venv", "dist"})


class FileWatcher:
    def __init__(self, root: str | Path, *, interval: float = 1.0):
        self.root = Path(root)
        self.interval = max(0.05, interval)
        self._seen: dict[str, str] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.events: list[dict] = []

    def _scan(self) -> dict[str, str]:
        current = {}
        if not self.root.is_dir():
            return current
        for path in self.root.rglob("*"):
            if not path.is_file() or any(p in SKIP for p in path.parts):
                continue
            rel = path.relative_to(self.root).as_posix()
            current[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return current

    def poll_once(self) -> list[dict]:
        current = self._scan()
        changes = []
        for name, digest in current.items():
            if name not in self._seen:
                changes.append({"kind": "created", "path": name})
            elif self._seen[name] != digest:
                changes.append({"kind": "modified", "path": name})
        for name in self._seen:
            if name not in current:
                changes.append({"kind": "deleted", "path": name})
        self._seen = current
        self.events.extend(changes)
        return changes

    def start(self, handler=None) -> None:
        if self._thread and self._thread.is_alive():
            return

        def loop():
            self.poll_once()  # baseline
            while not self._stop.wait(self.interval):
                for change in self.poll_once():
                    if handler:
                        handler(change)

        self._thread = threading.Thread(target=loop, daemon=True,
                                        name="keel-file-watcher")
        self._thread.start()

    def stop(self, timeout: float = 2) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
