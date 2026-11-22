"""C9.3 — incremental repository indexing with content hashes.

Builds a local, content-addressed index of a source tree and updates it
incrementally: unchanged files (same size + mtime) are reused without
rehashing, while added/modified/removed files are detected precisely. The
index is persisted as JSON and supports path/content search. The low-power
resource meter in :mod:`resource_caps` remains advisory; this module is the
concrete indexing half of C9.3. No external service or OS-level watcher is
required — callers invoke ``update_index`` when they want a refresh.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

IGNORE_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".keel", ".pytest_cache", ".mypy_cache", ".next",
})
MAX_FILE = 2_000_000
PREVIEW = 1500


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _walk(root: Path, extensions: set[str] | None):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.relative_to(root).parts):
            continue
        if extensions and path.suffix.lower() not in extensions:
            continue
        try:
            if path.stat().st_size > MAX_FILE:
                continue
        except OSError:
            continue
        yield path


def _entry(path: Path, root: Path) -> dict:
    data = path.read_bytes()
    try:
        preview = data[:PREVIEW].decode("utf-8", errors="replace")
    except OSError:
        preview = ""
    stat = path.stat()
    return {
        "hash": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "mtime": stat.st_mtime,
        "indexed_at": _now(),
        "preview": preview,
    }


def build_index(root: str | Path, *, extensions: list[str] | None = None) -> dict:
    root_path = Path(root)
    if not root_path.is_dir():
        raise ValueError(f"not a directory: {root}")
    exts = {e.lower() if e.startswith(".") else "." + e.lower()
            for e in (extensions or [])} or None
    files = {}
    for path in _walk(root_path, exts):
        files[str(path.relative_to(root_path).as_posix())] = _entry(path, root_path)
    return {"root": str(root_path.resolve()), "files": files,
            "count": len(files), "built_at": _now()}


def update_index(index: dict, root: str | Path,
                 *, extensions: list[str] | None = None) -> dict:
    """Refresh an index, rehashing only changed files."""
    root_path = Path(root)
    if not root_path.is_dir():
        raise ValueError(f"not a directory: {root}")
    exts = {e.lower() if e.startswith(".") else "." + e.lower()
            for e in (extensions or [])} or None
    old = index.get("files", {})
    new: dict[str, dict] = {}
    added: list[str] = []
    modified: list[str] = []
    for path in _walk(root_path, exts):
        rel = path.relative_to(root_path).as_posix()
        try:
            stat = path.stat()
        except OSError:
            continue
        previous = old.get(rel)
        if previous and previous.get("size") == stat.st_size \
                and previous.get("mtime") == stat.st_mtime:
            new[rel] = previous          # unchanged: no rehash
            continue
        entry = _entry(path, root_path)
        if previous and previous.get("hash") != entry["hash"]:
            modified.append(rel)
        elif not previous:
            added.append(rel)
        new[rel] = entry
    removed = sorted(set(old) - set(new))
    return {
        "root": index.get("root", str(root_path.resolve())),
        "files": new, "count": len(new), "updated_at": _now(),
        "added": sorted(added), "modified": sorted(modified),
        "removed": removed, "rehashed": len(added) + len(modified),
    }


def search_index(index: dict, query: str, *, limit: int = 10,
                 content: bool = False) -> dict:
    """Find files whose path (or preview) matches a query token."""
    needle = query.strip().lower()
    if not needle:
        return {"query": query, "hits": []}
    hits = []
    for rel, entry in index.get("files", {}).items():
        path_match = needle in rel.lower()
        content_match = content and needle in entry.get("preview", "").lower()
        if path_match or content_match:
            hits.append({"path": rel, "hash": entry["hash"],
                         "size": entry["size"],
                         "matched": "path" if path_match else "content"})
    hits.sort(key=lambda h: (h["matched"] != "path", h["path"]))
    return {"query": query, "hits": hits[:max(1, int(limit))],
            "total": len(hits)}


class IndexStore:
    """Persist repository indexes in a local state root."""

    def __init__(self, state_root: str | Path):
        self.root = Path(state_root) / "repo-indexes"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
            raise ValueError("invalid index name")
        return self.root / f"{name}.json"

    def save(self, name: str, index: dict) -> Path:
        path = self._path(name)
        path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        return path

    def load(self, name: str) -> dict:
        path = self._path(name)
        if not path.is_file():
            raise KeyError(name)
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))
