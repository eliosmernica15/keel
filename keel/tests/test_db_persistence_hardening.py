"""Hardening regressions for database / persistence integrity.

These tests exercise real on-disk paths with temporary directories:

* backups are written atomically (an interrupted write must not leave a
  corrupt file that looks like a valid backup);
* restore validates the *whole* archive before touching the destination and
  refuses to clobber newer state unless explicitly forced;
* restore rejects path traversal in archive member names;
* persisted event logs carry a verifiable integrity chain and tolerate
  concurrent appenders without losing or interleaving records.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from keel.backups import (BackupError, _derive, create_backup,
                          restore_backup)


# --------------------------------------------------------------------------
# helpers: build a *valid encrypted* backup with arbitrary member names/data
# --------------------------------------------------------------------------
def _build_backup(path: Path, files: dict[str, bytes], *,
                  passphrase: str = "pw", bad_hash_for: str | None = None,
                  omit_entry_for: str | None = None) -> None:
    """Create a keel-backup-v1 file with controlled members/manifest."""
    buffer = io.BytesIO()
    entries = []
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
            digest = hashlib.sha256(data).hexdigest()
            if name == bad_hash_for:
                digest = "0" * 64
            if name != omit_entry_for:
                entries.append({"path": name, "bytes": len(data),
                                "sha256": digest})
    salt = b"s" * 16
    nonce = b"n" * 12
    ciphertext = AESGCM(_derive(passphrase, salt)).encrypt(
        nonce, buffer.getvalue(), None)
    doc = {
        "format": "keel-backup-v1",
        "created": "2026-01-01T00:00:00Z",
        "entries": entries,
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": 200_000,
        "salt": salt.hex(),
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
    }
    path.write_text(json.dumps(doc), encoding="utf-8")


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


# --------------------------------------------------------------------------
# 1. interrupted backup creation
# --------------------------------------------------------------------------
def test_create_backup_is_atomic_on_interrupted_write(tmp_path, monkeypatch):
    """A failed write must not destroy the previous, valid backup."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "data.txt").write_text("new data", encoding="utf-8")

    target = tmp_path / "backups" / "backup.json"
    target.parent.mkdir()
    old_bytes = b'{"format":"keel-backup-v1","old":true}'
    target.write_bytes(old_bytes)

    real_write_bytes = Path.write_bytes
    original_write_text = Path.write_text
    real_replace = os.replace

    def exploding_write_bytes(self, data, *args, **kwargs):
        if Path(self) == target:
            # simulate a crash halfway through writing the backup file
            real_write_bytes(self, b'{"format":"keel-backup-v1","trunc')
            raise OSError("simulated disk failure")
        return real_write_bytes(self, data, *args, **kwargs)

    def exploding_write_text(self, data, *args, **kwargs):
        if Path(self) == target:
            real_write_bytes(self, b'{"format":"keel-backup-v1","trunc')
            raise OSError("simulated disk failure")
        return original_write_text(self, data, *args, **kwargs)

    def exploding_replace(src, dst, *args, **kwargs):
        if Path(dst) == target:
            # modern implementation stages in a temp file, then renames
            raise OSError("simulated disk failure")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(Path, "write_bytes", exploding_write_bytes)
    monkeypatch.setattr(Path, "write_text", exploding_write_text)
    monkeypatch.setattr(os, "replace", exploding_replace)

    with pytest.raises(OSError, match="simulated disk failure"):
        create_backup(source, target, "pw")

    # The last known-good backup survives byte-for-byte, and no half-written
    # staging file is left behind.
    assert target.read_bytes() == old_bytes
    assert not list(target.parent.glob("*.tmp"))


def test_atomic_write_retries_transient_windows_sharing_violation(tmp_path, monkeypatch):
    """WinError 5 while the destination is briefly open must not fail a create."""
    import keel.backups as backups

    source = tmp_path / "source"
    source.mkdir()
    (source / "data.txt").write_text("payload", encoding="utf-8")
    target = tmp_path / "backup.json"
    old_bytes = b"old-backup"
    target.write_bytes(old_bytes)

    original_replace = os.replace
    calls = []

    def flaky_replace(src, dst, *args, **kwargs):
        calls.append(1)
        if len(calls) <= 2 and Path(dst) == target:
            raise OSError(5, "Access is denied", None, 5)
        return original_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", flaky_replace)
    monkeypatch.setattr(backups.time, "sleep", lambda _seconds: None)

    create_backup(source, target, "pw")

    assert len(calls) == 3  # two transient failures, then success
    assert json.loads(target.read_text(encoding="utf-8"))["format"] == \
        "keel-backup-v1"
    assert not [p for p in target.parent.iterdir() if p.name.endswith(".tmp")]


def test_atomic_write_rethrows_after_retries_without_clobbering(tmp_path, monkeypatch):
    """Persistent WinError 5 still fails, with the old backup intact."""
    import keel.backups as backups

    source = tmp_path / "source"
    source.mkdir()
    (source / "data.txt").write_text("payload", encoding="utf-8")
    target = tmp_path / "backup.json"
    old_bytes = b"old-backup"
    target.write_bytes(old_bytes)

    calls = []

    def always_denied(src, dst, *args, **kwargs):
        calls.append(1)
        raise OSError(5, "Access is denied", None, 5)

    monkeypatch.setattr(os, "replace", always_denied)
    monkeypatch.setattr(backups.time, "sleep", lambda _seconds: None)

    with pytest.raises(OSError):
        create_backup(source, target, "pw")

    assert len(calls) == backups._REPLACE_ATTEMPTS
    assert target.read_bytes() == old_bytes
    assert not [p for p in target.parent.iterdir() if p.name.endswith(".tmp")]


# --------------------------------------------------------------------------
# 2. restore must not clobber newer state
# --------------------------------------------------------------------------
def test_restore_refuses_to_clobber_newer_state(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "config.txt").write_text("old value", encoding="utf-8")
    backup = tmp_path / "backup.json"
    create_backup(source, backup, "pw")

    destination = tmp_path / "destination"
    restore_backup(backup, destination, "pw")
    target_file = destination / "config.txt"

    # A human edited the file after the backup was taken.
    target_file.write_text("newer value", encoding="utf-8")
    old_mtime = target_file.stat().st_mtime
    os.utime(target_file, (old_mtime + 3600, old_mtime + 3600))

    with pytest.raises(BackupError, match="newer"):
        restore_backup(backup, destination, "pw")
    assert target_file.read_text(encoding="utf-8") == "newer value"

    # An explicit overwrite is still possible.
    restore_backup(backup, destination, "pw", overwrite=True)
    assert target_file.read_text(encoding="utf-8") == "old value"


# --------------------------------------------------------------------------
# 3. restore is all-or-nothing
# --------------------------------------------------------------------------
def test_restore_validates_entire_archive_before_writing(tmp_path):
    backup = tmp_path / "backup.json"
    _build_backup(backup, {"a.txt": b"aaa", "b.txt": b"bbb"},
                  bad_hash_for="b.txt")

    destination = tmp_path / "destination"
    with pytest.raises(BackupError, match="integrity"):
        restore_backup(backup, destination, "pw")

    # Nothing at all should have been written: no partial restore.
    assert not destination.exists() or not any(destination.iterdir())


def test_restore_rejects_manifest_missing_members(tmp_path):
    backup = tmp_path / "backup.json"
    _build_backup(backup, {"a.txt": b"aaa", "b.txt": b"bbb"},
                  omit_entry_for="b.txt")

    destination = tmp_path / "destination"
    with pytest.raises(BackupError, match="manifest"):
        restore_backup(backup, destination, "pw")
    assert not destination.exists() or not any(destination.iterdir())


# --------------------------------------------------------------------------
# 4. restore rejects traversal
# --------------------------------------------------------------------------
def test_restore_rejects_path_traversal(tmp_path):
    backup = tmp_path / "backup.json"
    _build_backup(backup, {"../escaped.txt": b"pwned"})

    destination = tmp_path / "destination"
    with pytest.raises(BackupError, match="unsafe path"):
        restore_backup(backup, destination, "pw")
    assert not (tmp_path / "escaped.txt").exists()


# --------------------------------------------------------------------------
# 5. event log integrity + concurrency
# --------------------------------------------------------------------------
def test_event_log_detects_tampering(tmp_path):
    from keel.events import (EventLogError, read_event_log,
                             verify_event_log, write_event_log)

    path = tmp_path / "events.jsonl"
    events = [{"type": "system", "subtype": "init", "n": i} for i in range(3)]
    write_event_log(path, events)
    assert verify_event_log(path) is True
    assert read_event_log(path) == events

    # Flip one byte of an event without changing the line count.
    raw = path.read_text(encoding="utf-8")
    raw = raw.replace('"n":1', '"n":9', 1)
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(EventLogError, match="integrity"):
        read_event_log(path)
    assert verify_event_log(path) is False


def test_event_log_write_retries_transient_windows_sharing_violation(
        tmp_path, monkeypatch):
    import keel.events as events
    from keel.events import read_event_log, write_event_log

    path = tmp_path / "events.jsonl"
    original_replace = os.replace
    calls = []

    def flaky_replace(src, dst, *args, **kwargs):
        calls.append(1)
        if len(calls) <= 2:
            raise OSError(5, "Access is denied", None, 5)
        return original_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", flaky_replace)
    monkeypatch.setattr(events.time, "sleep", lambda _seconds: None)

    write_event_log(path, [{"n": 1}, {"n": 2}])

    assert len(calls) == 4  # 2 retries + 2 atomic writes (log + chain)
    assert read_event_log(path) == [{"n": 1}, {"n": 2}]
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_event_log_detects_truncation(tmp_path):
    from keel.events import EventLogError, read_event_log, write_event_log

    path = tmp_path / "events.jsonl"
    write_event_log(path, [{"n": i} for i in range(4)])
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")

    with pytest.raises(EventLogError, match="integrity"):
        read_event_log(path)


def test_concurrent_event_appends_keep_a_valid_chain(tmp_path):
    from keel.events import append_event, read_event_log, verify_event_log

    path = tmp_path / "events.jsonl"
    count = 120

    def append(i):
        append_event(path, {"type": "user", "index": i})

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(append, range(count)))

    events = read_event_log(path)
    assert len(events) == count
    assert sorted(e["index"] for e in events) == list(range(count))
    assert verify_event_log(path) is True
    # A second writer process/thread appends after the first batch and the
    # chain remains valid (seq continues, no stale-head overwrite).
    append_event(path, {"type": "result", "index": count})
    assert len(read_event_log(path)) == count + 1


def test_concurrent_backup_creates_leave_one_valid_backup(tmp_path):
    """Concurrent writes to the same backup path must not interleave bytes."""
    backup = tmp_path / "shared-backup.json"

    def create(i):
        source = tmp_path / f"source-{i}"
        source.mkdir(exist_ok=True)
        (source / "id.txt").write_text(f"value-{i}", encoding="utf-8")
        create_backup(source, backup, "pw")
        return i

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(create, range(16)))

    # The final file is a complete, decryptable backup of one of the writers.
    restored = tmp_path / "restored"
    files = restore_backup(backup, restored, "pw")
    assert files == ["id.txt"]
    assert (restored / "id.txt").read_text(encoding="utf-8").startswith("value-")


def test_legacy_db_migration_preserves_existing_rows(tmp_path):
    """Audit: fleet.db migrations upgrade an old schema without data loss."""
    import sqlite3

    from keel.fleet.db import SCHEMA_VERSION, connect

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
    INSERT INTO schema_version VALUES (1, '2020-01-01T00:00:00Z');
    CREATE TABLE bots (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '',
      engine TEXT NOT NULL DEFAULT 'echo', provider TEXT NOT NULL DEFAULT 'auto',
      model TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
      avatar_hue INTEGER NOT NULL DEFAULT 200, created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL, last_active_at TEXT NOT NULL);
    CREATE TABLE rows (
      seq INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT NOT NULL,
      kind TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
    INSERT INTO bots VALUES ('b1','legacy','','echo','auto','','',200,'t','t','t');
    INSERT INTO rows(bot_id,kind,body,created_at) VALUES ('b1','message','hello','t');
    """)
    conn.commit()
    conn.close()

    with connect(path) as migrated:
        assert migrated.execute("SELECT name FROM bots WHERE id='b1'").fetchone()[0] \
            == "legacy"
        assert migrated.execute("SELECT body FROM rows WHERE bot_id='b1'").fetchone()[0] \
            == "hello"
        assert migrated.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] \
            == SCHEMA_VERSION


def test_event_log_chain_missing_is_detected(tmp_path):
    from keel.events import (EventLogError, read_event_log,
                             verify_event_log, write_event_log)

    path = tmp_path / "events.jsonl"
    write_event_log(path, [{"n": 1}, {"n": 2}])
    Path(str(path) + ".chain").unlink()

    assert verify_event_log(path) is False
    with pytest.raises(EventLogError, match="chain"):
        read_event_log(path)
