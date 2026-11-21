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
import time
from pathlib import Path

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
                            "sha256": hashlib.sha256(data).hexdigest()})
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
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc), encoding="utf-8")
    return {"format": doc["format"], "files": len(entries),
            "bytes": len(payload), "path": str(target)}


def restore_backup(backup: str | Path, destination: str | Path,
                   passphrase: str) -> list[str]:
    """Verify and restore an encrypted backup; returns restored file paths."""
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
    expected = {entry["path"]: entry["sha256"] for entry in doc.get("entries", [])}
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    restored = []
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            data = archive.extractfile(member).read()
            if expected.get(member.name) != hashlib.sha256(data).hexdigest():
                raise BackupError(f"integrity check failed: {member.name}")
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            restored.append(member.name)
    return sorted(restored)
