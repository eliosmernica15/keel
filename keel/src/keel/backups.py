"""Encrypted backup and restore (B4.11).

Real AES-256-GCM encrypted backups of a local directory, with a derived key
from a user passphrase (PBKDF2-HMAC-SHA256), authenticated file manifests and
verified restore. All data stays on the user's machine.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

# Windows keeps a short lock on a file while another thread has it open;
# os.replace onto that path can transiently fail with WinError 5/32. The
# staging file stays intact between attempts, so retrying preserves atomicity.
_REPLACE_ATTEMPTS = 5
_REPLACE_BACKOFF_S = 0.02

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ITERATIONS = 200_000
SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "dist", "build"})


class BackupError(RuntimeError):
    pass


def _derive(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                    salt=salt, iterations=ITERATIONS)
    return kdf.derive(passphrase.encode("utf-8"))


def _replace_with_retry(tmp: Path, target: Path) -> None:
    """os.replace with a bounded retry for transient Windows file locks.

    Only sharing/access failures are retried; every other OSError is raised
    immediately. Until the rename succeeds the destination is untouched, so
    the previous file remains intact throughout the retries.
    """
    last_exc: OSError | None = None
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, target)
            return
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            if winerror is not None and winerror not in (5, 32):
                raise
            last_exc = exc
            if attempt < _REPLACE_ATTEMPTS - 1:
                time.sleep(_REPLACE_BACKOFF_S)
    raise last_exc  # type: ignore[misc]


def _atomic_write(target: Path, data: bytes) -> None:
    """Write bytes via a sibling temp file + atomic rename.

    An interrupted/failed write must never truncate an existing file: the
    previous version stays byte-for-byte intact until the rename succeeds.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                    dir=str(target.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _replace_with_retry(tmp, target)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _safe_member_name(name: str) -> str:
    """Reject archive member names that could escape the destination root."""
    if (not name or name.startswith("/") or "\\" in name or ":" in name
            or name != name.strip() or "\x00" in name):
        raise BackupError(f"unsafe path in backup: {name!r}")
    parts = PurePosixPath(name).parts
    if not parts or any(part in ("..", "") for part in parts):
        raise BackupError(f"unsafe path in backup: {name!r}")
    return str(PurePosixPath(*parts))


def _tar_bytes(source: Path) -> tuple[bytes, list[dict]]:
    buffer = io.BytesIO()
    entries = []
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                continue
            rel = path.relative_to(source).as_posix()
            data = path.read_bytes()
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            info.mtime = int(path.stat().st_mtime)
            archive.addfile(info, io.BytesIO(data))
            entries.append({"path": rel, "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "mtime": info.mtime})
    return buffer.getvalue(), entries


def create_backup(source: str | Path, target: str | Path,
                  passphrase: str) -> dict:
    """Create an encrypted backup file; returns the manifest metadata."""
    if not passphrase:
        raise BackupError("a passphrase is required")
    source = Path(source)
    if not source.is_dir():
        raise BackupError(f"not a directory: {source}")
    payload, entries = _tar_bytes(source)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive(passphrase, salt)).encrypt(nonce, payload, None)
    doc = {
        "format": "keel-backup-v1",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entries": entries,
        "kdf": "PBKDF2-HMAC-SHA256", "iterations": ITERATIONS,
        "salt": salt.hex(), "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
    }
    target = Path(target)
    # Write to a temp file and rename: a crash or a disk error during the
    # write leaves the previous (valid) backup untouched, never a truncated
    # file that passes the format check but fails on restore.
    _atomic_write(target, json.dumps(doc).encode("utf-8"))
    return {"format": doc["format"], "files": len(entries),
            "bytes": len(payload), "path": str(target)}


def restore_backup(backup: str | Path, destination: str | Path,
                   passphrase: str, *, overwrite: bool = False) -> list[str]:
    """Verify and restore an encrypted backup; returns restored file paths.

    The entire archive is authenticated and checked against the manifest
    before *any* file is written, so a damaged backup cannot leave a partial
    restore behind. Files that are newer on disk than the archived version
    are protected unless ``overwrite=True`` is explicitly requested.
    """
    try:
        doc = json.loads(Path(backup).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackupError(f"cannot read backup: {exc}") from None
    if doc.get("format") != "keel-backup-v1":
        raise BackupError("unsupported backup format")
    try:
        payload = AESGCM(_derive(passphrase, bytes.fromhex(doc["salt"]))).decrypt(
            bytes.fromhex(doc["nonce"]), bytes.fromhex(doc["ciphertext"]), None)
    except Exception:
        raise BackupError("wrong passphrase or corrupted backup") from None
    expected = {}
    for entry in doc.get("entries", []):
        name = _safe_member_name(entry["path"])
        expected[name] = entry
    destination = Path(destination)

    # Pass 1: validate every member and stage its bytes in memory. No
    # destination writes happen until the whole archive has been verified.
    staged: list[tuple[str, bytes, object]] = []
    seen: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                name = _safe_member_name(member.name)
                entry = expected.get(name)
                if entry is None:
                    raise BackupError(
                        f"manifest mismatch: {name!r} is not in the backup manifest")
                data = archive.extractfile(member).read()
                if entry["sha256"] != hashlib.sha256(data).hexdigest():
                    raise BackupError(f"integrity check failed: {name}")
                staged.append((name, data, entry.get("mtime")))
                seen.add(name)
    except tarfile.TarError as exc:
        raise BackupError(f"corrupted backup archive: {exc}") from None

    missing = sorted(set(expected) - seen)
    if missing:
        raise BackupError(
            f"manifest mismatch: missing archived files: {', '.join(missing)}")

    # Pass 2: refuse to clobber files changed after the backup was taken.
    if not overwrite:
        for name, data, _mtime in staged:
            target = destination / name
            if not target.is_file():
                continue
            if hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(
                    data).hexdigest():
                continue  # already identical; no state can be lost
            archived_mtime = expected[name].get("mtime")
            if archived_mtime is None:
                continue  # legacy backup without timestamps: nothing to compare
            try:
                if target.stat().st_mtime > float(archived_mtime) + 1.0:
                    raise BackupError(
                        f"refusing to overwrite newer file: {name} "
                        "(pass overwrite=True to force)")
            except (TypeError, ValueError):
                continue

    # Pass 3: write. Each file is replaced atomically so a mid-restore failure
    # never leaves a half-written file at the destination.
    destination.mkdir(parents=True, exist_ok=True)
    restored = []
    for name, data, mtime in staged:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, data)
        if mtime is not None:
            try:
                os.utime(target, (float(mtime), float(mtime)))
            except (OSError, TypeError, ValueError):
                pass
        restored.append(name)
    return sorted(restored)
