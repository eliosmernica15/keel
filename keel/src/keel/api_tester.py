"""Real HTTP/API tester with saved collections (B2.10).

Executes actual HTTP requests against explicitly allowed hosts (loopback by
default) using the standard library, records status/headers/body timing, and
persists named request collections locally. No external service is required.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path


class APIError(RuntimeError):
    pass


class APICollection:
    def __init__(self, state_root: str | Path):
        self.path = Path(state_root) / "api-collection.json"

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def _save(self, doc: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def save_request(self, name: str, method: str, url: str,
                     body: str = "", headers: dict | None = None) -> dict:
        entry = {"method": method.upper(), "url": url, "body": body,
                 "headers": dict(headers or {})}
        doc = self._load()
        doc[name] = entry
        self._save(doc)
        return entry

    def list(self) -> list[dict]:
        return [{"name": name, **entry}
                for name, entry in self._load().items()]


def run_request(name: str, collection: APICollection, *,
                allow_hosts: set[str] | None = None,
                timeout: int = 10) -> dict:
    """Execute a saved request; hosts are restricted (loopback by default)."""
    entry = collection._load().get(name)
    if entry is None:
        raise APIError(f"unknown request: {name}")
    from urllib.parse import urlparse

    host = urlparse(entry["url"]).hostname or ""
    allowed = allow_hosts if allow_hosts is not None else {"127.0.0.1", "localhost", "::1"}
    if host not in allowed:
        raise APIError(f"host not allowed: {host}")
    data = entry.get("body", "").encode() if entry.get("body") else None
    req = urllib.request.Request(
        entry["url"], data=data, method=entry["method"],
        headers=entry.get("headers") or {})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(100000).decode("utf-8", errors="replace")
            return {"ok": True, "status": response.status, "body": body,
                    "elapsed_ms": round((time.monotonic() - start) * 1000, 2)}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code,
                "body": exc.read(100000).decode("utf-8", errors="replace"),
                "elapsed_ms": round((time.monotonic() - start) * 1000, 2)}
    except OSError as exc:
        raise APIError(f"request failed: {exc}") from None
