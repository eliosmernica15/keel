"""Safe update primitives for Keel (v5 §0.4, §11).

The updater verifies manifests and artifacts before applying an update, swaps
installation directories atomically, keeps the previous version for rollback,
and never touches an existing install on failed verification.
"""

from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import verify
from .signing import verify_bytes, verify_manifest


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdatePlan:
    version: str
    platform: str
    file: str
    url: str
    size: int
    sha256: str
    manifest_version: str


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = tuple(int(p) for p in re.findall(r"\d+", value or ""))
    return parts or (0,)


def check_for_update(manifest_url: str, *, current_version: str,
                     platform: str, public_key=None,
                     allow_http: bool = False, timeout: int = 60) -> UpdatePlan | None:
    """Return the newest signed artifact for *platform*, or None if up to date."""
    manifest = verify.load_manifest(
        manifest_url, allow_http=allow_http, timeout=timeout)
    if public_key is not None and not verify_manifest(manifest, public_key):
        raise UpdateError("release manifest signature is invalid")

    candidates = []
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("platform") != platform:
            continue
        version = str(entry.get("version") or manifest.get("version") or "")
        if not version or _version_tuple(version) <= _version_tuple(current_version):
            continue
        candidates.append((version, entry))

    if not candidates:
        return None
    version, entry = max(candidates, key=lambda item: _version_tuple(item[0]))
    return UpdatePlan(
        version=version,
        platform=platform,
        file=str(entry.get("file", "")),
        url=str(entry.get("url", "")),
        size=int(entry.get("bytes", 0)),
        sha256=str(entry.get("sha256", "")),
        manifest_version=str(manifest.get("version", "")),
    )


def download_update(plan: UpdatePlan, destination: Path, *,
                    public_key=None, allow_http: bool = False,
                    timeout: int = 300) -> Path:
    """Download and verify an artifact; write it only after all checks pass."""
    data, size = verify.fetch_bytes(
        plan.url, allow_http=allow_http, timeout=timeout)
    if size != plan.size:
        raise UpdateError(f"size mismatch for {plan.file}")
    import hashlib

    if hashlib.sha256(data).hexdigest().upper() != plan.sha256.upper():
        raise UpdateError(f"sha256 mismatch for {plan.file}")
    if public_key is not None:
        sig_data, _ = verify.fetch_bytes(
            plan.url + ".sig", allow_http=allow_http, timeout=timeout)
        if not verify_bytes(data, sig_data, public_key):
            raise UpdateError(f"signature invalid for {plan.file}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_bytes(data)
    tmp.replace(destination)
    return destination


def atomic_install(staged_dir: Path, install_dir: Path,
                   backup_dir: Path) -> None:
    """Swap a staged installation into place, preserving the old one."""
    if not staged_dir.is_dir():
        raise UpdateError("staged update is not a directory")
    if not install_dir.is_dir():
        raise UpdateError("installation directory does not exist")

    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    install_dir.rename(backup_dir)
    try:
        staged_dir.rename(install_dir)
    except Exception:
        if backup_dir.exists() and not install_dir.exists():
            backup_dir.rename(install_dir)
        raise


def rollback(install_dir: Path, backup_dir: Path) -> None:
    if not backup_dir.is_dir():
        raise UpdateError("no backup available for rollback")
    if install_dir.exists():
        shutil.rmtree(install_dir)
    backup_dir.rename(install_dir)
