"""Stabilization install-recovery regressions.

These tests target the two fail-open paths found during the install/rollback
drill: (1) a failed/aborted swap could destroy the last known-good backup, and
(2) a torn write of the start-health JSON silently reset the consecutive
failure counter, defeating auto-rollback. Faults are injected deterministically
at the filesystem boundary; no network egress, production key, credential or
paid service is used.
"""

from __future__ import annotations

import functools
import json
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from keel import start_health
from keel.release import common, updater
from keel.release.signing import (
    generate_keypair,
    load_private_key,
    load_public_key,
    sign_bytes,
    sign_manifest,
)


def _dirs(tmp_path, *, with_backup: bool = True):
    install = tmp_path / "install"
    backup = tmp_path / "backup"
    staged = tmp_path / "staged"
    install.mkdir()
    staged.mkdir()
    (install / "version.txt").write_text("old", encoding="utf-8")
    (staged / "version.txt").write_text("new", encoding="utf-8")
    if with_backup:
        backup.mkdir()
        (backup / "version.txt").write_text("older-backup", encoding="utf-8")
    return install, backup, staged


def test_failed_first_rename_preserves_existing_backup(tmp_path, monkeypatch):
    """A lock on the live install must not delete the pre-existing fallback."""
    install, backup, staged = _dirs(tmp_path)
    real_rename = Path.rename

    def blocked(self, target):
        if self == install:
            raise OSError("simulated lock on live install")
        return real_rename(self, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", blocked)
        with pytest.raises(OSError):
            updater.atomic_install(staged, install, backup)

    assert (install / "version.txt").read_text(encoding="utf-8") == "old"
    assert (backup / "version.txt").read_text(encoding="utf-8") == "older-backup"
    assert (staged / "version.txt").read_text(encoding="utf-8") == "new"


def test_failed_second_rename_restores_full_pre_state(tmp_path, monkeypatch):
    """A lock on the staged copy restores install *and* the older backup."""
    install, backup, staged = _dirs(tmp_path)
    real_rename = Path.rename

    def blocked(self, target):
        if self == staged:
            raise OSError("simulated lock on staged install")
        return real_rename(self, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", blocked)
        with pytest.raises(OSError):
            updater.atomic_install(staged, install, backup)

    assert (install / "version.txt").read_text(encoding="utf-8") == "old"
    assert (backup / "version.txt").read_text(encoding="utf-8") == "older-backup"
    assert (staged / "version.txt").read_text(encoding="utf-8") == "new"


def test_missing_install_does_not_destroy_backup(tmp_path):
    """A crash between the two renames leaves install missing but backup intact."""
    install, backup, staged = _dirs(tmp_path)
    shutil.rmtree(install)  # simulated hard interruption after install -> backup

    with pytest.raises(updater.UpdateError, match="does not exist"):
        updater.atomic_install(staged, install, backup)
    assert (backup / "version.txt").read_text(encoding="utf-8") == "older-backup"

    # The surviving backup is still usable by the real rollback path.
    updater.rollback(install, backup)
    assert (install / "version.txt").read_text(encoding="utf-8") == "older-backup"


def test_rollback_refuses_when_backup_missing(tmp_path):
    install, _, staged = _dirs(tmp_path, with_backup=False)
    with pytest.raises(updater.UpdateError, match="no backup"):
        updater.rollback(install, tmp_path / "no-such-backup")
    assert (install / "version.txt").read_text(encoding="utf-8") == "old"
    assert (staged / "version.txt").read_text(encoding="utf-8") == "new"


def test_rollback_recovers_when_install_missing(tmp_path):
    install, backup, _ = _dirs(tmp_path)
    shutil.rmtree(install)
    updater.rollback(install, backup)
    assert (install / "version.txt").read_text(encoding="utf-8") == "older-backup"
    assert not backup.exists()


def test_torn_health_write_does_not_reset_failure_counter(tmp_path, monkeypatch):
    """A crash during state persistence must not re-arm the failure count."""
    root = str(tmp_path)
    start_health.record_start(root, "0.2.0", ok=False)
    start_health.record_start(root, "0.2.0", ok=False)

    real_write_text = Path.write_text

    def torn_write(self, *args, **kwargs):
        if self.name == "start-health.json" or self.name.startswith("."):
            real_write_text(self, "{", encoding="utf-8")  # truncated JSON
            raise OSError("simulated crash mid-write")
        return real_write_text(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "write_text", torn_write)
        with pytest.raises(OSError):
            start_health.record_start(root, "0.2.0", ok=False)

    result = start_health.record_start(root, "0.2.0", ok=False)
    assert result["failures"] == 3
    assert result["rollback"] is True


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # pragma: no cover - output noise only
        pass


@pytest.fixture
def signed_release(tmp_path):
    """Real loopback release server with an ephemeral Ed25519 dev keypair."""
    private_path = tmp_path / "dev.pem"
    public_path = tmp_path / "dev.pub.pem"
    generate_keypair(private_path, public_path)
    private = load_private_key(private_path)
    public = load_public_key(public_path)

    serve_root = tmp_path / "serve"
    tag_dir = serve_root / "v0.1.2"
    tag_dir.mkdir(parents=True)
    name = "Keel-Setup-0.1.2.exe"
    payload = b"real-installer-bytes"
    artifact = tag_dir / name
    artifact.write_bytes(payload)
    (tag_dir / f"{name}.sig").write_bytes(sign_bytes(payload, private))

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        functools.partial(_QuietHandler, directory=str(serve_root)),
    )
    base_url = f"http://127.0.0.1:{server.server_port}"
    manifest = common.build_release_manifest(
        {name: artifact}, "0.1.2", "v0.1.2", base_url)
    (serve_root / "download.json").write_text(
        json.dumps(sign_manifest(manifest, private)), encoding="utf-8")

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield public, f"{base_url}/download.json", artifact, payload
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_signed_download_sha256_with_optional_ed25519(signed_release, tmp_path):
    """SHA-256 always applies; Ed25519 is enforced when a key is supplied."""
    public, url, artifact, payload = signed_release
    plan = updater.check_for_update(
        url, current_version="0.1.1", platform="windows",
        public_key=public, allow_http=True)
    assert plan is not None and plan.version == "0.1.2"

    # No key -> SHA-256 only, still succeeds.
    sha_only = tmp_path / "sha-only.exe"
    updater.download_update(plan, sha_only, allow_http=True)
    assert sha_only.read_bytes() == payload

    # A different (real) key -> Ed25519 verification fails closed.
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    generate_keypair(other_dir / "p.pem", other_dir / "pub.pem")
    wrong_public = load_public_key(other_dir / "pub.pem")
    with pytest.raises(updater.UpdateError, match="signature invalid"):
        updater.download_update(
            plan, tmp_path / "wrong-key.exe", public_key=wrong_public,
            allow_http=True)

    # Tampered bytes on the server -> SHA-256 mismatch, no file written.
    # Same length so the size check passes and the SHA-256 check is the one
    # that rejects the tampered artifact.
    artifact.write_bytes(payload.replace(b"real", b"REAL"))
    destination = tmp_path / "tampered.exe"
    with pytest.raises(updater.UpdateError, match="sha256 mismatch"):
        updater.download_update(
            plan, destination, public_key=public, allow_http=True)
    assert not destination.exists()
