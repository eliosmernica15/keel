"""Auto-reindexing RAG knowledge bases (B2.6 + C5.4 integration).

Wires the real file watcher to the local RAG index so a knowledge base stays
in sync with its source folder. Changes are debounced and re-indexing is
bounded; no external service is involved.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from .file_watcher import FileWatcher
from .rag import KnowledgeBase


class RagAutoIndex:
    def __init__(self, state_root: str | Path, folder: str | Path,
                 name: str = "default", *, interval: float = 1.0):
        self.base = KnowledgeBase(str(state_root), name)
        self.folder = Path(folder)
        self.watcher = FileWatcher(self.folder, interval=interval)
        self._lock = threading.Lock()
        self.reindex_count = 0
        self.last_error = ""

    def reindex(self) -> dict:
        with self._lock:
            try:
                result = self.base.index(self.folder)
                self.reindex_count += 1
                self.last_error = ""
                return result
            except Exception as exc:  # keep the watcher alive on bad files
                self.last_error = str(exc)[:200]
                return {"files": 0, "chunks": 0, "error": self.last_error}

    def start(self, *, debounce_s: float = 0.5) -> None:
        pending = threading.Event()

        def on_change(change):
            pending.set()

        self.reindex()  # initial index of existing content
        self.watcher.start(on_change)

        def loop():
            while True:
                if self.watcher._stop.wait(0.1):
                    break
                if pending.is_set():
                    time.sleep(debounce_s)
                    pending.clear()
                    self.reindex()

        self._loop = threading.Thread(target=loop, daemon=True,
                                      name="keel-rag-indexer")
        self._loop.start()

    def stop(self) -> None:
        self.watcher.stop()
        if getattr(self, "_loop", None):
            self._loop.join(timeout=2)

    def search(self, query: str) -> list[dict]:
        return self.base.search(query)
