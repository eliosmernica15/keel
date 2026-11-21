"""Browser and workspace resource management (A1.11).

Tracks resource usage (browser tabs, attached workspace bytes) against local
configurable limits. All state is in-process; no external service is involved.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class ResourceLimitError(RuntimeError):
    pass


class ResourceManager:
    def __init__(self, *, max_tabs: int = 8, max_workspace_bytes: int = 64 * 1024 * 1024,
                 max_resource_bytes: int = 4 * 1024 * 1024):
        self.max_tabs = max_tabs
        self.max_workspace_bytes = max_workspace_bytes
        self.max_resource_bytes = max_resource_bytes
        self._tabs: dict[str, dict] = {}
        self._workspace_bytes = 0
        self._lock = threading.RLock()

    def open_tab(self, tab_id: str, *, url: str = "") -> dict:
        with self._lock:
            if tab_id in self._tabs:
                raise ResourceLimitError(f"tab already open: {tab_id}")
            if len(self._tabs) >= self.max_tabs:
                raise ResourceLimitError(f"tab limit reached ({self.max_tabs})")
            entry = {"id": tab_id, "url": url,
                     "opened_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                time.gmtime())}
            self._tabs[tab_id] = entry
            return entry

    def close_tab(self, tab_id: str) -> bool:
        with self._lock:
            return self._tabs.pop(tab_id, None) is not None

    def attach_workspace(self, size: int) -> int:
        size = max(0, int(size))
        with self._lock:
            if self._workspace_bytes + size > self.max_workspace_bytes:
                raise ResourceLimitError("workspace byte budget exceeded")
            self._workspace_bytes += size
            return self._workspace_bytes

    def detach_workspace(self, size: int) -> int:
        with self._lock:
            self._workspace_bytes = max(0, self._workspace_bytes - max(0, int(size)))
            return self._workspace_bytes

    def check_resource(self, data: Any) -> int:
        size = len(data if isinstance(data, (bytes, str)) else str(data).encode())
        if size > self.max_resource_bytes:
            raise ResourceLimitError(
                f"resource exceeds {self.max_resource_bytes} bytes")
        return size

    def status(self) -> dict:
        with self._lock:
            return {"tabs": len(self._tabs),
                    "tab_limit": self.max_tabs,
                    "workspace_bytes": self._workspace_bytes,
                    "workspace_limit": self.max_workspace_bytes,
                    "resource_limit": self.max_resource_bytes}
