"""keel.fleet.library — the Fleet Library's filesystem side.

Files live under `<library_root>/<bot_id>/<file_id>` — the on-disk name is
the id, never the user-chosen filename, so path traversal is impossible by
construction. The filename is metadata in `fleet_library`, shown in the UI.

`library_root` resolves: KEEL_FLEET_LIBRARY env → ~/.keel/fleet/library.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\- ]{0,119}$")
_MAX_FILE_BYTES = 2 * 1024 * 1024          # per file, agent or user
_BOT_QUOTA_BYTES = 25 * 1024 * 1024        # per agent total


def library_root() -> Path:
    p = Path(os.environ.get("KEEL_FLEET_LIBRARY",
                            str(Path.home() / ".keel" / "fleet" / "library")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def validate_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("filename must not be empty")
    if len(name) > 120:
        raise ValueError("filename must be at most 120 characters")
    if "/" in name or "\\" in name or "\x00" in name:
        raise ValueError("filename must not contain path separators")
    if not _NAME_RE.match(name):
        raise ValueError(
            "filename may only contain letters, digits, dots, "
            "dashes, underscores and spaces, and must start alphanumerically")
    if name.startswith("."):
        raise ValueError("filename must not start with a dot")
    return name


def file_path(bot_id: str, file_id: str) -> Path:
    root = library_root().resolve()
    dest = (root / bot_id / file_id).resolve()
    if root not in dest.parents:
        raise ValueError("resolved library path escapes the library root")
    return dest


def write_bytes(bot_id: str, file_id: str, data: bytes) -> tuple[Path, str, int]:
    """Write data atomically-ish; returns (path, sha256, size)."""
    dest = file_path(bot_id, file_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, dest)
    return dest, hashlib.sha256(data).hexdigest(), len(data)


def read_bytes(bot_id: str, file_id: str) -> bytes:
    with open(file_path(bot_id, file_id), "rb") as fh:
        return fh.read()


def delete_file(bot_id: str, file_id: str) -> None:
    try:
        os.remove(file_path(bot_id, file_id))
    except FileNotFoundError:
        pass


def bot_usage_bytes(rows: list[dict]) -> int:
    return sum(int(r.get("size") or 0) for r in rows)


def check_quota(existing_rows: list[dict], incoming: int) -> None:
    used = bot_usage_bytes(existing_rows)
    if used + incoming > _BOT_QUOTA_BYTES:
        raise ValueError(
            f"agent library quota exceeded (25 MB): {used + incoming} bytes "
            f"would be stored; delete files first")


def guess_mime(name: str) -> str:
    dot = name.rfind(".")
    ext = name[dot:].lower() if dot >= 0 else ""
    return {
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".json": "application/json",
        ".csv": "text/csv; charset=utf-8",
        ".yaml": "text/yaml; charset=utf-8",
        ".yml": "text/yaml; charset=utf-8",
        ".py": "text/x-python; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".ts": "text/typescript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".xml": "application/xml",
        ".sh": "text/x-sh; charset=utf-8",
        ".sql": "text/x-sql; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".pdf": "application/pdf",
        ".zip": "application/zip",
    }.get(ext, "application/octet-stream")


MAX_FILE_BYTES = _MAX_FILE_BYTES
BOT_QUOTA_BYTES = _BOT_QUOTA_BYTES
