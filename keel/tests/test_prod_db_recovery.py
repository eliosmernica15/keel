"""Production database integrity: verified backup, restore, migrations, concurrency.

Every test uses disposable temp directories only. No real user database is
read, backed up, migrated, or overwritten by this module.

Coverage:
  * consistent SQLite snapshot (including live WAL data) and verified restore;
  * migrations from an empty DB and from a populated legacy schema, repeated
    invocation, and an interrupted migration recovered by explicit restore;
  * concurrent writes from threads and from separate OS processes;
  * validation/fail-closed behaviour, retention, typed errors, and the CLI.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import keel.backups as backups
import keel.fleet.db as fleet_db
from keel.backups import (
    BackupRetentionError,
    DatabaseBackupError,
    DatabaseBackupValidationError,
    DatabaseCorruptionError,
    DatabaseRestoreError,
    backup_database,
    list_database_backups,
    prune_database_backups,
    restore_database,
    verify_database_backup,
)
from keel.fleet.db import SCHEMA_VERSION, connect


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _seed_bot(path: Path, bot_id: str = "b1", name: str = "legacy") -> None:
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO bots(id,name,created_at,updated_at,last_active_at) "
            "VALUES(?,?,?,?,?)", (bot_id, name, "t", "t", "t"))
        conn.execute(
            "INSERT INTO rows(bot_id,kind,body,created_at) VALUES(?,?,?,?)",
            (bot_id, "message", '{"text":"hello"}', "t"))
        conn.commit()
    finally:
        conn.close()


def _indexes(db_path: Path) -> set[str]:
    conn = sqlite3.connect(backups._sqlite_uri(db_path, read_only=True), uri=True)
    try:
        return {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_%'")}
    finally:
        conn.close()


def _healthy(db_path: Path) -> None:
    conn = sqlite3.connect(backups._sqlite_uri(db_path, read_only=True), uri=True)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def _init_records_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE records(id TEXT PRIMARY KEY, writer TEXT NOT NULL, "
            "n INTEGER NOT NULL)")
        conn.commit()
    finally:
        conn.close()


def _thread_writer(db_path: Path, tag: str, count: int) -> None:
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN IMMEDIATE")
        for i in range(count):
            conn.execute(
                "INSERT INTO records(id, writer, n) VALUES(?,?,?)",
                (f"{tag}:{i}", tag, i))
        conn.commit()
    finally:
        conn.close()


_PROCESS_WRITER = r"""
import sqlite3, sys
db, tag, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
conn = sqlite3.connect(db, timeout=30)
conn.execute("PRAGMA busy_timeout=30000")
conn.execute("BEGIN IMMEDIATE")
for i in range(count):
    conn.execute("INSERT INTO records(id, writer, n) VALUES(?, ?, ?)",
                 (f"{tag}:{i}", tag, i))
conn.commit()
conn.close()
"""


def _process_writer(db_path: Path, tag: str, count: int) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROCESS_WRITER, str(db_path), tag, str(count)],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# 1. snapshot + restore, empty and populated databases
# ---------------------------------------------------------------------------
def test_backup_empty_database_and_restore_into_fresh_db(tmp_path):
    db = tmp_path / "empty.db"
    connect(db).close()

    result = backup_database(db, tmp_path / "backups", "pw")
    info = verify_database_backup(result["path"], "pw", expected_source=db)
    assert info["schema_version"] == SCHEMA_VERSION
    assert info["counts"]["bots"] == 0
    assert result["records"] == info["records"]

    fresh = tmp_path / "fresh.db"
    restored = restore_database(result["path"], fresh, "pw")
    assert restored["counts"] == info["counts"]
    assert restored["schema_version"] == SCHEMA_VERSION
    _healthy(fresh)
    # The installed DB can be opened through the normal fleet helper again.
    reopened = connect(fresh)
    assert reopened.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] \
        == SCHEMA_VERSION
    reopened.close()


def test_backup_populated_database_preserves_records_indexes_and_fks(tmp_path):
    db = tmp_path / "populated.db"
    _seed_bot(db)
    artifact = backup_database(db, tmp_path / "backups", "pw")
    info = verify_database_backup(artifact["path"], "pw")
    assert info["counts"]["bots"] == 1
    assert info["counts"]["rows"] == 1

    fresh = tmp_path / "recovered.db"
    restore_database(artifact["path"], fresh, "pw")
    _healthy(fresh)
    checked = sqlite3.connect(backups._sqlite_uri(fresh, read_only=True), uri=True)
    try:
        assert checked.execute(
            "SELECT name FROM bots WHERE id='b1'").fetchone()[0] == "legacy"
        assert checked.execute(
            "SELECT body FROM rows WHERE bot_id='b1'").fetchone()[0] \
            == '{"text":"hello"}'
        # Deleting the parent must cascade: the restored FKs are real.
        assert "ON DELETE CASCADE" in checked.execute(
            "SELECT sql FROM sqlite_master WHERE name='rows'").fetchone()[0]
    finally:
        checked.close()
    assert {"idx_rows_bot_seq", "idx_fleet_tasks_assigned",
            "idx_fleet_audit_bot", "idx_bots_kind"} <= _indexes(fresh)

    # Never clobber an existing database unless explicitly asked.
    with pytest.raises(DatabaseRestoreError, match="already exists"):
        restore_database(artifact["path"], fresh, "pw")
    reopened = sqlite3.connect(backups._sqlite_uri(fresh, read_only=True), uri=True)
    try:
        assert reopened.execute("SELECT COUNT(*) FROM bots").fetchone()[0] == 1
    finally:
        reopened.close()


def test_restore_refuses_non_empty_wal_sidecar(tmp_path):
    db = tmp_path / "live.db"
    _seed_bot(db)
    artifact = backup_database(db, tmp_path / "backups", "pw")
    target = tmp_path / "target.db"
    restore_database(artifact["path"], target, "pw")
    sidecar = Path(str(target) + "-wal")
    sidecar.write_bytes(b"stale-wal-frames")  # simulate an unclean shutdown
    with pytest.raises(DatabaseRestoreError, match="sidecar"):
        restore_database(artifact["path"], target, "pw", overwrite=True)
    assert sidecar.read_bytes() == b"stale-wal-frames"


def test_backup_captures_live_wal_data(tmp_path):
    db = tmp_path / "wal.db"
    _seed_bot(db)
    conn = connect(db)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    # Write but deliberately do not checkpoint: the data lives in the WAL.
    conn.execute(
        "INSERT INTO rows(bot_id,kind,body,created_at) VALUES('b1','message','wal','t')")
    conn.commit()
    assert Path(str(db) + "-wal").exists()  # committed row is still in the WAL
    conn.close()

    artifact = backup_database(db, tmp_path / "backups", "pw")
    fresh = tmp_path / "wal-restored.db"
    restored = restore_database(artifact["path"], fresh, "pw")
    assert restored["counts"]["rows"] == 2
    checked = sqlite3.connect(backups._sqlite_uri(fresh, read_only=True), uri=True)
    try:
        assert "wal" in {row[0] for row in checked.execute(
            "SELECT body FROM rows WHERE bot_id='b1'")}
    finally:
        checked.close()


# ---------------------------------------------------------------------------
# 2. migrations: empty, legacy populated, repeated, interrupted
# ---------------------------------------------------------------------------
def test_migration_from_empty_and_repeated_invocation_is_idempotent(tmp_path):
    db = tmp_path / "fresh.db"
    for _ in range(3):
        conn = connect(db)
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] \
            == SCHEMA_VERSION
        conn.close()
    _healthy(db)
    tables = {row[0] for row in sqlite3.connect(str(db)).execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"bots", "rows", "fleet_tasks", "fleet_usage", "fleet_projects"} <= tables


def test_migration_from_populated_legacy_schema_preserves_data(tmp_path):
    db = tmp_path / "legacy.db"
    raw = sqlite3.connect(db)
    raw.executescript("""
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
    INSERT INTO bots VALUES ('b1','old-bot','','echo','auto','','',200,'t','t','t');
    INSERT INTO rows(bot_id,kind,body,created_at) VALUES ('b1','message','keep me','t');
    """)
    raw.commit()
    raw.close()

    for _ in range(2):  # repeated invocation must not re-apply migrations
        conn = connect(db)
        assert conn.execute("SELECT name FROM bots WHERE id='b1'").fetchone()[0] \
            == "old-bot"
        assert conn.execute("SELECT body FROM rows WHERE bot_id='b1'").fetchone()[0] \
            == "keep me"
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] \
            == SCHEMA_VERSION
        conn.close()


def test_interrupted_migration_recovers_only_by_explicit_restore(tmp_path,
                                                                 monkeypatch):
    seed = tmp_path / "pre-migration.db"
    _seed_bot(seed)
    setup = connect(seed)
    setup.execute("DROP INDEX IF EXISTS idx_bots_kind")
    setup.execute("ALTER TABLE bots DROP COLUMN kind")  # undo the V10 column
    setup.execute("DELETE FROM schema_version WHERE version > 9")
    setup.commit()
    setup.close()
    assert "kind" not in {row[1] for row in sqlite3.connect(seed).execute(
        "PRAGMA table_info(bots)")}

    broken = tmp_path / "interrupted.db"
    shutil.copyfile(seed, broken)
    created_conns: list[sqlite3.Connection] = []
    original_connect = sqlite3.connect
    original_ddl_v10 = fleet_db._DDL_V10

    def boom():
        raise RuntimeError("simulated crash after V10 ALTER")

    def wrapped_connect(*args, **kwargs):
        conn = original_connect(*args, **kwargs)
        created_conns.append(conn)
        conn.create_function("interrupt_migration", 0, boom)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(fleet_db.sqlite3, "connect", wrapped_connect)
        patch.setattr(fleet_db, "_DDL_V10",
                      original_ddl_v10 + "\nSELECT interrupt_migration();\n")
        with pytest.raises(sqlite3.OperationalError, match="user-defined function"):
            connect(broken).close()
        # V10's ALTER TABLE is not idempotent: a blind retry fails. There is
        # no automatic rollback; recovery is an explicit snapshot restore.
        with pytest.raises(sqlite3.OperationalError, match="duplicate column name"):
            connect(broken).close()
    for conn in created_conns:
        try:
            conn.close()
        except sqlite3.Error:
            pass

    artifact = backup_database(seed, tmp_path / "backups", "pw")
    recovered = tmp_path / "recovered.db"
    restore_database(artifact["path"], recovered, "pw")
    final = connect(recovered)
    try:
        assert final.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] \
            == SCHEMA_VERSION
        assert final.execute("SELECT name FROM bots WHERE id='b1'").fetchone()[0] \
            == "legacy"
        assert final.execute("SELECT body FROM rows WHERE bot_id='b1'").fetchone()[0] \
            == '{"text":"hello"}'
    finally:
        final.close()


# ---------------------------------------------------------------------------
# 3. concurrency: threads and processes, lossless and non-corrupting
# ---------------------------------------------------------------------------
def test_concurrent_thread_and_process_writes_are_lossless(tmp_path):
    db = tmp_path / "concurrent.db"
    _init_records_db(db)
    thread_total, process_total = 6 * 20, 4 * 20

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda i: _thread_writer(db, f"t{i}", 20), range(6)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: _process_writer(db, f"p{i}", 20), range(4)))

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] \
            == thread_total + process_total
        assert conn.execute("SELECT COUNT(DISTINCT id) FROM records").fetchone()[0] \
            == thread_total + process_total
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()
    _healthy(db)

    artifact = backup_database(db, tmp_path / "backups", "pw")
    restored = tmp_path / "restored.db"
    result = restore_database(artifact["path"], restored, "pw")
    assert result["counts"]["records"] == thread_total + process_total
    _healthy(restored)


def test_backup_is_consistent_while_writer_is_active(tmp_path):
    db = tmp_path / "live.db"
    _init_records_db(db)
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executemany("INSERT INTO records(id,writer,n) VALUES(?,?,?)",
                     [(f"seed:{i}", "seed", i) for i in range(250)])
    conn.commit()
    conn.close()

    stop = threading.Event()

    def writer():
        local = sqlite3.connect(str(db), timeout=30)
        try:
            for i in range(200):
                if stop.is_set():
                    break
                local.execute("PRAGMA busy_timeout=30000")
                local.execute("INSERT INTO records(id,writer,n) VALUES(?,?,?)",
                              (f"live:{i}", "live", i))
                local.commit()
                time.sleep(0.0005)
        finally:
            local.close()

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        artifact = backup_database(db, tmp_path / "backups", "pw")
    finally:
        stop.set()
        thread.join(timeout=20)

    info = verify_database_backup(artifact["path"], "pw")
    assert info["counts"]["records"] >= 250
    restored = tmp_path / "snapshot.db"
    result = restore_database(artifact["path"], restored, "pw")
    assert result["counts"]["records"] == info["counts"]["records"]
    _healthy(restored)


# ---------------------------------------------------------------------------
# 4. fail-closed validation, typed errors, retention, CLI
# ---------------------------------------------------------------------------
def test_corrupt_source_is_refused_before_backup(tmp_path):
    db = tmp_path / "corrupt.db"
    _seed_bot(db)
    artifact = backup_database(db, tmp_path / "good-backups", "pw")
    assert verify_database_backup(artifact["path"], "pw")["tables"]

    with db.open("r+b") as fh:
        fh.seek(4096)
        fh.write(b"\x00" * 256)
    with pytest.raises(DatabaseCorruptionError, match="integrity_check"):
        backup_database(db, tmp_path / "bad-backups", "pw")
    assert not list((tmp_path / "bad-backups").glob("*.dbbak"))


def test_wrong_passphrase_and_tampered_ciphertext_are_refused(tmp_path):
    db = tmp_path / "db.sqlite"
    _seed_bot(db)
    artifact = backup_database(db, tmp_path / "backups", "pw")

    with pytest.raises(DatabaseBackupValidationError, match="wrong passphrase"):
        verify_database_backup(artifact["path"], "wrong")
    with pytest.raises(DatabaseBackupValidationError):
        restore_database(artifact["path"], tmp_path / "out", "wrong")

    path = Path(artifact["path"])
    doc = json.loads(path.read_text(encoding="utf-8"))
    cipher = bytearray(bytes.fromhex(doc["ciphertext"]))
    cipher[0] ^= 0xFF
    doc["ciphertext"] = cipher.hex()
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DatabaseBackupValidationError, match="corrupted"):
        verify_database_backup(path, "pw")
    assert not (tmp_path / "out").exists()


def test_manifest_mismatch_fails_before_any_destination_write(tmp_path):
    db = tmp_path / "db.sqlite"
    _seed_bot(db)
    artifact = backup_database(db, tmp_path / "backups", "pw")
    path = Path(artifact["path"])
    doc = json.loads(path.read_text(encoding="utf-8"))
    key = backups._derive("pw", bytes.fromhex(doc["salt"]))
    nonce = bytes.fromhex(doc["nonce"])
    payload = AESGCM(key).decrypt(nonce, bytes.fromhex(doc["ciphertext"]),
                                   backups._db_aad(doc))
    doc["counts"]["rows"] += 99  # attacker with the key cannot change the DB
    doc["ciphertext"] = AESGCM(key).encrypt(nonce, payload, backups._db_aad(doc)).hex()
    tampered = tmp_path / "tampered.dbbak"
    tampered.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(DatabaseBackupValidationError, match="manifest"):
        restore_database(tampered, tmp_path / "never-created.db", "pw")
    assert not (tmp_path / "never-created.db").exists()


def test_retention_keeps_newest_backups_and_leaves_foreign_files(tmp_path,
                                                                 monkeypatch):
    db = tmp_path / "db.sqlite"
    _seed_bot(db)
    counter = [0]

    def fmt(pattern, *args):
        counter[0] += 1
        if "%Y%m%d" in pattern:
            return f"20260101T{counter[0]:06d}Z"
        return f"2026-01-01T00:00:{counter[0]:02d}Z"

    monkeypatch.setattr(backups, "time", types.SimpleNamespace(
        strftime=fmt, gmtime=time.gmtime, sleep=lambda _seconds: None))
    directory = tmp_path / "backups"
    for _ in range(4):
        backup_database(db, directory, "pw")  # no automatic pruning
    paths = sorted(directory.glob("*.dbbak"))
    assert len(paths) == 4
    foreign = directory / "notes.txt"
    foreign.write_text("keep", encoding="utf-8")
    unknown = directory / "keel-db-unknown.dbbak"
    unknown.write_text("not a backup", encoding="utf-8")

    result = prune_database_backups(directory, keep=2)
    assert len(result["kept"]) == 2 and len(result["removed"]) == 2
    assert len(list(directory.glob("*.dbbak"))) == 3  # 2 good + 1 unknown
    assert foreign.read_text() == "keep"
    assert unknown.exists()
    assert set(result["kept"]) == {p["path"] for p in
                                   list_database_backups(directory)}

    with pytest.raises(BackupRetentionError):
        prune_database_backups(directory, keep=0)
    dry = prune_database_backups(directory, keep=1, dry_run=True)
    assert len(dry["removed"]) == 1
    assert len(list_database_backups(directory)) == 2


def test_backup_prune_parameter_and_typed_error_hierarchy(tmp_path):
    db = tmp_path / "db.sqlite"
    _seed_bot(db)
    result = backup_database(db, tmp_path / "backups", "pw", keep=1)
    assert result["retention"]["kept"] == [result["path"]]
    assert issubclass(DatabaseCorruptionError, DatabaseBackupError)
    assert issubclass(DatabaseBackupValidationError, DatabaseBackupError)
    assert issubclass(DatabaseRestoreError, DatabaseBackupError)
    assert issubclass(BackupRetentionError, DatabaseBackupError)
    with pytest.raises(DatabaseBackupError):
        backup_database(tmp_path / "missing.db", tmp_path / "backups", "pw")
    with pytest.raises(DatabaseBackupError):
        backup_database(db, tmp_path / "backups", "")


def test_cli_backup_verify_restore_list_prune(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    _seed_bot(db)
    directory = tmp_path / "backups"
    assert backups.main(["db-backup", "--db", str(db), "--dir", str(directory),
                         "--passphrase", "pw"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["format"] == backups.DB_BACKUP_FORMAT
    assert backups.main(["db-verify", "--backup", created["path"],
                         "--passphrase", "pw"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["bots"] == 1
    assert backups.main(["db-list", "--dir", str(directory)]) == 0
    assert len(json.loads(capsys.readouterr().out)["backups"]) == 1
    assert backups.main(["db-prune", "--dir", str(directory), "--keep", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["kept"] == [created["path"]]
    assert backups.main(["db-restore", "--backup", created["path"],
                         "--to", str(tmp_path / "cli-restored.db"),
                         "--passphrase", "pw"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["bots"] == 1
    assert backups.main(["db-verify", "--backup", created["path"],
                         "--passphrase", "bad"]) == 1
    assert "wrong passphrase" in capsys.readouterr().out
