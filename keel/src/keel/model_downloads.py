"""Resumable, integrity-verified model downloads (B1.6).

Uses only the standard library: HTTP Range for resume, a ``.part`` staging
file, and SHA-256 verification before the file becomes visible at its final
path. Nothing is downloaded unless the caller supplies a URL.
"""

from __future__ import annotations

import hashlib
import os
import urllib.parse
import urllib.request
from pathlib import Path

CHUNK = 1024 * 1024


class DownloadError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def part_path(dest: Path) -> Path:
    return dest.with_name(dest.name + ".part")


def download(url: str, dest: str | Path, *, sha256: str | None = None,
             timeout: int = 60, allow_http: bool = False,
             max_bytes: int = 20 * 1024 * 1024 * 1024) -> Path:
    """Download *url* to *dest*, resuming any existing ``.part`` file."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise DownloadError("url must be http or https")
    if parsed.scheme == "http" and not allow_http:
        raise DownloadError("http downloads require allow_http=True")

    target = Path(dest).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = part_path(target)
    offset = staging.stat().st_size if staging.is_file() else 0
    headers = {"User-Agent": "Keel/1.0"}
    if offset:
        headers["Range"] = f"bytes={offset}-"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            mode = "ab" if offset and response.status == 206 else "wb"
            if mode == "wb":
                offset = 0
            with open(staging, mode) as handle:
                written = 0
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    written += len(block)
                    if offset + written > max_bytes:
                        raise DownloadError("download exceeds max_bytes")
                    handle.write(block)
    except DownloadError:
        raise
    except OSError as exc:
        raise DownloadError(f"download failed: {exc}") from exc

    if sha256:
        actual = sha256_file(staging)
        if actual.lower() != str(sha256).strip().lower():
            staging.unlink(missing_ok=True)
            raise DownloadError(
                f"integrity check failed: expected {sha256}, got {actual}")
    staging.replace(target)
    return target
