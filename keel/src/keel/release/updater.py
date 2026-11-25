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


def rollout_bucket(version: str, client_id: str, bucket_count: int = 100) -> int:
    """Stable deterministic bucket for staged rollout decisions."""
    import hashlib

    digest = hashlib.sha256(f"{client_id}:{version}".encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big") % max(1, bucket_count)


def check_for_update(manifest_url: str | list[str], *, current_version: str,
                     platform: str, public_key=None,
                     allow_http: bool = False, timeout: int = 60,
                     client_id: str = "") -> UpdatePlan | None:
    """Return the newest signed artifact for *platform*, or None if up to date.

    Multiple URLs are tried in order (mirror failover). Every successfully
    loaded manifest is signature-verified before it can influence the result.
    """
    urls = [manifest_url] if isinstance(manifest_url, str) else list(manifest_url)
    if not urls:
        raise UpdateError("no manifest URLs configured")

    manifest = None
    last_error: Exception | None = None
    for url in urls:
        try:
            candidate = verify.load_manifest(
                url, allow_http=allow_http, timeout=timeout)
            if public_key is not None and not verify_manifest(candidate, public_key):
                raise UpdateError(f"release manifest signature invalid at {url}")
            manifest = candidate
            break
        except Exception as exc:  # try the next mirror
            last_error = exc
    if manifest is None:
        raise UpdateError(f"all manifest mirrors failed: {last_error}")

    blocked = {str(v) for v in manifest.get("blocked_versions", [])}
    min_version = str(manifest.get("min_version", ""))
    if min_version and _version_tuple(current_version) < _version_tuple(min_version):
        raise UpdateError(
            f"installation {current_version} is below minimum {min_version}")

    rollout = manifest.get("rollout") if isinstance(
        manifest.get("rollout"), dict) else {}
    percentage = int(rollout.get("percentage", 100) or 100)
    bucket_count = int(rollout.get("bucket_count", 100) or 100)

    candidates = []
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("platform") != platform:
            continue
        version = str(entry.get("version") or manifest.get("version") or "")
        if not version or version in blocked:
            continue
        if _version_tuple(version) <= _version_tuple(current_version):
            continue
        candidates.append((version, entry))

    if not candidates:
        return None
    version, entry = max(candidates, key=lambda item: _version_tuple(item[0]))
    if percentage < 100 and rollout_bucket(
            version, client_id or "keel-client", bucket_count) >= percentage:
        return None
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
    """Swap a staged installation into place, preserving the old one.

    An existing backup is moved aside rather than deleted: it stays available
    until the new backup and the new install are both in place. On any failure
    the pre-call state (including the older backup) is restored, so a failed or
    interrupted upgrade can never destroy the last known-good fallback.
    """
    if not staged_dir.is_dir():
        raise UpdateError("staged update is not a directory")
    if not install_dir.is_dir():
        raise UpdateError("installation directory does not exist")

    prior_backup: Path | None = None
    if backup_dir.exists():
        prior_backup = backup_dir.with_name(
            f".{backup_dir.name}.prior.{uuid.uuid4().hex}")
        backup_dir.rename(prior_backup)

    try:
        install_dir.rename(backup_dir)
    except Exception:
        if (prior_backup is not None and prior_backup.exists()
                and not backup_dir.exists()):
            prior_backup.rename(backup_dir)
        raise

    try:
        staged_dir.rename(install_dir)
    except Exception:
        if backup_dir.exists() and not install_dir.exists():
            backup_dir.rename(install_dir)
        if (prior_backup is not None and prior_backup.exists()
                and not backup_dir.exists()):
            prior_backup.rename(backup_dir)
        raise

    if prior_backup is not None and prior_backup.exists():
        # The new install is already live; stale-backup cleanup must never turn
        # a successful upgrade into a reported failure.
        try:
            shutil.rmtree(prior_backup)
        except OSError:
            pass


def rollback(install_dir: Path, backup_dir: Path) -> None:
    if not backup_dir.is_dir():
        raise UpdateError("no backup available for rollback")
    if install_dir.exists():
        shutil.rmtree(install_dir)
    backup_dir.rename(install_dir)
