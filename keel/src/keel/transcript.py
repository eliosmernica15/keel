"""keel.transcript — append-only JSONL transcript (Phase 1).

Path: <root>/projects/<sanitised-cwd>/<session-id>.jsonl
Sanitisation: every non-alphanumeric character becomes '-' (interface-spec §11.3).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Iterator


def project_slug(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def default_root() -> str:
    return os.path.join(os.path.expanduser("~"), ".keel")


def session_path(root: str, cwd: str, session_id: str) -> str:
    return os.path.join(root, "projects", project_slug(cwd), f"{session_id}.jsonl")


class TranscriptWriter:
    """Append-only. Never truncates, never rewrites. fsync per line."""

    def __init__(self, path: str, fs: Any = None):
        self.path = path
        self._fs = fs
        directory = os.path.dirname(path)
        if fs is not None:
            fs.makedirs(directory)
            self._lines: list[str] = []
        else:
            os.makedirs(directory, exist_ok=True)
            self._fh = open(path, "a", encoding="utf-8", errors="replace", newline="\n")

    def write(self, entry: dict) -> None:
        line = json.dumps(entry, separators=(",", ":"), ensure_ascii=False)
        if getattr(self, "_fs", None) is not None:
            self._lines.append(line)
            self._fs.write_text(self.path, "\n".join(self._lines) + "\n")
            return
        self._fh.write(line + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        fh = getattr(self, "_fh", None)
        if fh is not None:
            fh.close()


def read_entries(path: str) -> Iterator[tuple[dict | None, bool]]:
    """Yield (entry, ok). A truncated final line is skipped, not fatal."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                yield None, False
                continue
            yield entry, True
