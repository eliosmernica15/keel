"""STAB-DB recovery hardening: real database, backup and ledger verification.

Every test uses disposable temp directories. No real user database, backup
directory or ledger is read or modified. The tests cover:

* SQLite pragmas, transaction boundaries, FK enforcement and concurrent
  first-open migrations from threads *and* separate processes;
* empty / populated / legacy migration, repeated upgrade, interrupted
  forward-only migration and explicit restore-based recovery;
* corruption detection (including a truncated source file);
* real encrypted database backup: manifest/AAD/hash binding, wrong passphrase,
  existing-target and sidecar refusal, rollback on a failed restore, retention
  and the CLI;
* RecoveryLedger recovery from a real killed subprocess, cross-process
  duplicate submission, bounded retries and destructive-operation quarantine.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import keel.backups as backups
import keel.fleet.db as fleet_db
import keel.reliability_contracts as rc
from keel.backups import (
    BackupRetentionError,
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

KEEL_SRC = Path(__file__).resolve().parents[1] / "src"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _seed(db: Path, bot_id: str = "b1", name: str = "seed") -> None:
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO bots(id,name,created_at,updated_at,last_active_at) "
            "VALUES(?,?,?,?,?)", (bot_id, name, "t", "t", "t"))
        conn.execute(
            "INSERT INTO rows(bot_id,kind,body,created_at) VALUES(?,?,?,?)",
            (bot_id, "message", '{"text":"keep"}', "t"))
        conn.commit()
    finally:
        conn.close()


def _version(db: Path) -> int:
    conn = sqlite3.connect(backups._sqlite_uri(db, read_only=True), uri=True)
    try:
        return int(conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0])
    finally:
        conn.close()


def _read_only(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(backups._sqlite_uri(db, read_only=True), uri=True)


_MIGRATE_CHILD = r"""
import os
import sys
import time
sys.path.insert(0, sys.argv[1])
from keel.fleet.db import connect
gate = sys.argv[-1]
while not os.path.exists(gate):
    time.sleep(0.002)
try:
    c = connect(sys.argv[2])
    print("OK:" + str(c.execute(
        "SELECT MAX(version) FROM schema_version").fetchone()[0]))
    c.close()
except Exception as exc:
    print("FAIL:" + type(exc).__name__ + ":" + str(exc))
"""


def _spawn_gated(script: str, *args: str, count: int) -> tuple[list[subprocess.Popen], Path]:
    """Spawn children that wait on a gate file, then release them together.

    Children receive ``sys.argv[1]`` = keel/src, the supplied *args*, and the
    gate path last so every script can read ``sys.argv[-1]``.
    """
    child = Path(args[0]).parent / "gated_child.py"
    child.write_text(script, encoding="utf-8")
    gate = child.with_name("gate.txt")
    gate.unlink(missing_ok=True)
    procs = [subprocess.Popen(
        [sys.executable, str(child), str(KEEL_SRC), *args, str(gate)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(count)]
    gate.write_text("go", encoding="utf-8")
    return procs, gate


_LEGACY_SQL = """
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
INSERT INTO bots VALUES ('old','legacy-bot','','echo','auto','','',200,'t','t','t');
INSERT INTO rows(bot_id,kind,body,created_at) VALUES ('old','message','legacy row','t');
"""


# ---------------------------------------------------------------------------
# 1. SQLite fundamentals and concurrent migration
# ---------------------------------------------------------------------------
def test_connect_enables_wal_busy_timeout_and_foreign_keys(tmp_path):
    db = tmp_path / "fleet.db"
    conn = connect(db)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30_000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert _version(db) == SCHEMA_VERSION
    finally:
        conn.close()


def test_transaction_boundaries_and_foreign_keys_are_real(tmp_path):
    db = tmp_path / "fleet.db"
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO bots(id,name,created_at,updated_at,last_active_at) "
            "VALUES('a','Alice','t','t','t')")
        conn.execute(
            "INSERT INTO rows(bot_id,kind,body,created_at) "
            "VALUES('a','message','committed','t')")
        conn.commit()

        conn.execute(
            "INSERT INTO rows(bot_id,kind,body,created_at) "
            "VALUES('a','message','rolled-back','t')")
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO rows(bot_id,kind,body,created_at) "
                "VALUES('missing','message','bad fk','t')")
        conn.execute("DELETE FROM bots WHERE id='a'")  # ON DELETE CASCADE
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM rows").fetchone()[0] == 0
    finally:
        conn.close()
    assert _read_only(db).execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_first_open_migration_is_serialized_across_threads_and_processes(tmp_path):
    """A fresh DB opened concurrently must upgrade cleanly, exactly once."""
    db = tmp_path / "fleet.db"
    procs, gate = _spawn_gated(
        _MIGRATE_CHILD, str(db), "ignored", count=4)
    thread_results: list[str] = []

    def thread_open(_index: int) -> None:
        while not gate.exists():
            time.sleep(0.002)
        try:
            conn = connect(db)
            thread_results.append("OK:" + str(conn.execute(
                "SELECT MAX(version) FROM schema_version").fetchone()[0]))
            conn.close()
        except Exception as exc:  # report, never swallow
            thread_results.append(f"FAIL:{type(exc).__name__}:{exc}")

    threads = [threading.Thread(target=thread_open, args=(i,))
               for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=90)
        assert not thread.is_alive()
    proc_results = []
    for proc in procs:
        out, err = proc.communicate(timeout=90)
        assert proc.returncode == 0, err
        proc_results.append(out.strip())

    all_results = thread_results + proc_results
    assert len(all_results) == 10, all_results
    assert all(result == f"OK:{SCHEMA_VERSION}" for result in all_results), all_results
    assert _version(db) == SCHEMA_VERSION
    conn = _read_only(db)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_empty_populated_and_legacy_migrations_preserve_data(tmp_path):
    empty = tmp_path / "empty.db"
    for _ in range(3):
        connect(empty).close()
    assert _version(empty) == SCHEMA_VERSION
    assert _read_only(empty).execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'").fetchone()[0] >= 10

    legacy = tmp_path / "legacy.db"
    raw = sqlite3.connect(legacy)
    raw.executescript(_LEGACY_SQL)
    raw.commit()
    raw.close()
    for _ in range(3):
        conn = connect(legacy)
        try:
            assert conn.execute("SELECT name FROM bots WHERE id='old'").fetchone()[0] \
                == "legacy-bot"
            assert conn.execute("SELECT body FROM rows WHERE bot_id='old'").fetchone()[0] \
                == "legacy row"
            assert _version(legacy) == SCHEMA_VERSION
        finally:
            conn.close()
    cols = {row[1] for row in _read_only(legacy).execute("PRAGMA table_info(bots)")}
    assert {"kind", "reasoning_effort", "project_id"} <= cols


def test_interrupted_migration_is_forward_only_and_restored_explicitly(
        tmp_path, monkeypatch):
    seed = tmp_path / "pre-migration.db"
    _seed(seed)
    setup = connect(seed)
    setup.execute("DROP INDEX IF EXISTS idx_bots_kind")
    setup.execute("ALTER TABLE bots DROP COLUMN kind")
    setup.execute("DELETE FROM schema_version WHERE version > 9")
    setup.commit()
    setup.close()

    broken = tmp_path / "interrupted.db"
    broken.write_bytes(seed.read_bytes())
    created: list[sqlite3.Connection] = []
    original_connect = sqlite3.connect
    original_ddl = fleet_db._DDL_V10

    def boom() -> None:
        raise RuntimeError("simulated crash inside V10")

    def wrapped(*args, **kwargs):
        conn = original_connect(*args, **kwargs)
        created.append(conn)
        conn.create_function("crash_v10", 0, boom)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(fleet_db.sqlite3, "connect", wrapped)
        patch.setattr(fleet_db, "_DDL_V10",
                      original_ddl + "\nSELECT crash_v10();\n")
        with pytest.raises(sqlite3.OperationalError, match="user-defined function"):
            connect(broken).close()
        # No down migration and no automatic rollback: the half-applied V10
        # ALTER makes a blind retry fail. Recovery is an explicit restore.
        with pytest.raises(sqlite3.OperationalError, match="duplicate column name"):
            connect(broken).close()
    for conn in created:
        try:
            conn.close()
        except sqlite3.Error:
            pass

    artifact = backup_database(seed, tmp_path / "backups", "pw")
    recovered = tmp_path / "recovered.db"
    restore_database(artifact["path"], recovered, "pw")
    final = connect(recovered)
    try:
        assert _version(recovered) == SCHEMA_VERSION
        assert final.execute("SELECT name FROM bots WHERE id='b1'").fetchone()[0] \
            == "seed"
        assert final.execute("SELECT body FROM rows").fetchone()[0] == '{"text":"keep"}'
    finally:
        final.close()


def test_corruption_detection_rejects_byte_flips_fk_violations_and_truncation(tmp_path):
    good = tmp_path / "good.db"
    _seed(good)
    backup_database(good, tmp_path / "good-backups", "pw")

    flipped = tmp_path / "flipped.db"
    flipped.write_bytes(good.read_bytes())
    with flipped.open("r+b") as fh:
        fh.seek(4096)
        fh.write(b"\xff" * 128)
    with pytest.raises(DatabaseCorruptionError, match="integrity_check"):
        backup_database(flipped, tmp_path / "bad-backups", "pw")
    assert not list((tmp_path / "bad-backups").glob("*.dbbak"))

    fk_broken = tmp_path / "fk.db"
    raw = sqlite3.connect(fk_broken)
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.executescript("""
    CREATE TABLE parent(id TEXT PRIMARY KEY);
    CREATE TABLE child(id TEXT PRIMARY KEY, parent_id TEXT REFERENCES parent(id));
    INSERT INTO child VALUES('c','missing');
    """)
    raw.commit()
    raw.close()
    with pytest.raises(DatabaseCorruptionError, match="foreign key"):
        backup_database(fk_broken, tmp_path / "bad-backups", "pw")

    for size in (0, 100):
        truncated = tmp_path / f"truncated-{size}.db"
        truncated.write_bytes(good.read_bytes()[:size])
        with pytest.raises(DatabaseCorruptionError):
            backup_database(truncated, tmp_path / "bad-backups", "pw")


# ---------------------------------------------------------------------------
# 2. real encrypted backup + restore
# ---------------------------------------------------------------------------
def test_manifest_hash_encryption_and_aad_are_all_verified(tmp_path):
    db = tmp_path / "db.sqlite"
    _seed(db)
    artifact = backup_database(db, tmp_path / "backups", "pw")
    path = Path(artifact["path"])
    doc = json.loads(path.read_text(encoding="utf-8"))

    assert doc["format"] == backups.DB_BACKUP_FORMAT
    assert doc["kdf"] == "PBKDF2-HMAC-SHA256"
    assert doc["iterations"] == backups.ITERATIONS
    assert doc["ciphertext"] not in ("", doc["sha256"])
    assert verify_database_backup(path, "pw")["counts"]["bots"] == 1

    with pytest.raises(DatabaseBackupValidationError, match="wrong passphrase"):
        verify_database_backup(path, "wrong")

    for mutate, match in (
        (lambda d: d.update(ciphertext=(bytes.fromhex(d["ciphertext"])[:1]
                                        + bytes([bytes.fromhex(d["ciphertext"])[0] ^ 0xFF])
                                        + bytes.fromhex(d["ciphertext"])[2:]).hex()),
         "corrupted"),
    ):
        tampered = json.loads(path.read_text(encoding="utf-8"))
        mutate(tampered)
        bad = tmp_path / "tampered.dbbak"
        bad.write_text(json.dumps(tampered), encoding="utf-8")
        with pytest.raises(DatabaseBackupValidationError, match=match):
            verify_database_backup(bad, "pw")
        assert not (tmp_path / "never.db").exists()

    # A holder of the key can re-encrypt, but cannot change the plaintext
    # manifest fields: they are bound as AES-GCM authenticated data.
    key = backups._derive("pw", bytes.fromhex(doc["salt"]))
    nonce = bytes.fromhex(doc["nonce"])
    payload = AESGCM(key).decrypt(nonce, bytes.fromhex(doc["ciphertext"]),
                                  backups._db_aad(doc))
    rebound = json.loads(json.dumps(doc))
    rebound["counts"]["bots"] += 99
    rebound["ciphertext"] = AESGCM(key).encrypt(
        nonce, payload, backups._db_aad(rebound)).hex()
    aad_bad = tmp_path / "aad-mismatch.dbbak"
    aad_bad.write_text(json.dumps(rebound), encoding="utf-8")
    with pytest.raises(DatabaseBackupValidationError, match="manifest"):
        restore_database(aad_bad, tmp_path / "never.db", "pw")
    assert not (tmp_path / "never.db").exists()


def test_restore_refuses_existing_target_and_active_sidecars(tmp_path):
    db = tmp_path / "db.sqlite"
    _seed(db)
    artifact = backup_database(db, tmp_path / "backups", "pw")
    target = tmp_path / "target.db"
    result = restore_database(artifact["path"], target, "pw")
    assert result["counts"]["bots"] == 1

    before = target.read_bytes()
    with pytest.raises(DatabaseRestoreError, match="already exists"):
        restore_database(artifact["path"], target, "pw")
    assert target.read_bytes() == before

    sidecar = Path(str(target) + "-wal")
    sidecar.write_bytes(b"live-wal-frames")
    with pytest.raises(DatabaseRestoreError, match="sidecar"):
        restore_database(artifact["path"], target, "pw", overwrite=True)
    assert sidecar.read_bytes() == b"live-wal-frames"
    assert target.read_bytes() == before

    sidecar.unlink()
    assert restore_database(artifact["path"], target, "pw",
                            overwrite=True)["counts"]["bots"] == 1


def test_failed_post_write_verification_rolls_back_only_our_restore(tmp_path,
                                                                    monkeypatch):
    db = tmp_path / "db.sqlite"
    _seed(db)
    artifact = backup_database(db, tmp_path / "backups", "pw")
    target = tmp_path / "target.db"
    _seed(target, bot_id="old", name="previous-state")
    before = target.read_bytes()

    original = backups._db_health
    calls: list[str] = []

    def failing_health(conn, *, context):
        calls.append(context)
        if context.startswith("restored database"):
            raise DatabaseCorruptionError("simulated post-write failure")
        return original(conn, context=context)

    monkeypatch.setattr(backups, "_db_health", failing_health)
    with pytest.raises(DatabaseRestoreError, match="post-write verification"):
        restore_database(artifact["path"], target, "pw", overwrite=True)

    assert target.read_bytes() == before
    assert not [p for p in tmp_path.iterdir() if ".restore.tmp" in p.name]
    assert any(c.startswith("restored database") for c in calls)
    conn = _read_only(target)
    try:
        assert conn.execute("SELECT name FROM bots WHERE id='old'").fetchone()[0] \
            == "previous-state"
    finally:
        conn.close()


def test_retention_and_cli_roundtrip(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    _seed(db)
    directory = tmp_path / "backups"
    assert backups.main(["db-backup", "--db", str(db), "--dir", str(directory),
                         "--passphrase", "pw"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert backups.main(["db-verify", "--backup", created["path"],
                         "--passphrase", "pw"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["bots"] == 1
    assert backups.main(["db-list", "--dir", str(directory)]) == 0
    assert len(json.loads(capsys.readouterr().out)["backups"]) == 1

    restored = tmp_path / "cli-restored.db"
    assert backups.main(["db-restore", "--backup", created["path"],
                         "--to", str(restored), "--passphrase", "pw"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["bots"] == 1
    assert _read_only(restored).execute(
        "PRAGMA integrity_check").fetchone()[0] == "ok"
    assert backups.main(["db-verify", "--backup", created["path"],
                         "--passphrase", "wrong"]) == 1
    assert "wrong passphrase" in capsys.readouterr().out

    for _ in range(3):
        backup_database(db, directory, "pw")
    (directory / "notes.txt").write_text("keep", encoding="utf-8")
    pruned = prune_database_backups(directory, keep=2)
    assert len(pruned["kept"]) == 2 and len(pruned["removed"]) == 2
    assert (directory / "notes.txt").read_text(encoding="utf-8") == "keep"
    assert len(list_database_backups(directory)) == 2
    with pytest.raises(BackupRetentionError):
        prune_database_backups(directory, keep=0)


# ---------------------------------------------------------------------------
# 3. RecoveryLedger crash recovery and idempotency
# ---------------------------------------------------------------------------
_KILL_CHILD = r"""
import os
import sys
import time
sys.path.insert(0, sys.argv[1])
from keel.reliability_contracts import RecoveryLedger
ledger = RecoveryLedger(sys.argv[2], run_id="killed-run")
ledger.register_worker("killed-worker")
ledger.submit("kill-task", idempotency_key="kill-key", payload={"step": 1})
ledger.claim("kill-task", "killed-worker")
ledger.record_partial("kill-task", "killed-worker", "HALF-OUTPUT")
open(sys.argv[3], "w").write("ready")
while True:
    time.sleep(1)
"""

_CROSS_SUBMIT_CHILD = r"""
import os
import sys
import time
sys.path.insert(0, sys.argv[1])
from keel.reliability_contracts import RecoveryLedger
gate = sys.argv[-1]
while not os.path.exists(gate):
    time.sleep(0.002)
ledger = RecoveryLedger(sys.argv[2], run_id="cross-run")
result = ledger.submit("cross-task", idempotency_key="cross-key",
                       payload={"source": "process"})
print("DUP" if result.duplicate else "FIRST")
"""


def test_real_subprocess_kill_mid_task_recovers_partial_output(tmp_path):
    child = tmp_path / "kill_child.py"
    child.write_text(_KILL_CHILD, encoding="utf-8")
    ready = tmp_path / "ready.txt"
    proc = subprocess.Popen(
        [sys.executable, str(child), str(KEEL_SRC), str(tmp_path / "state"),
         str(ready)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 30
    while not ready.exists() and time.time() < deadline:
        time.sleep(0.01)
    assert ready.exists(), "child never reached the mid-task point"
    proc.kill()
    proc.communicate(timeout=30)
    assert proc.returncode != 0

    parent = rc.RecoveryLedger(tmp_path / "state", run_id="parent-run")
    before = parent.task("kill-task")
    assert before.phase is rc.TaskPhase.RUNNING
    assert before.partial_output == "HALF-OUTPUT"

    report = parent.recover()
    assert "kill-task" in report.interrupted
    assert "killed-worker" in report.workers_retired
    after = parent.task("kill-task")
    assert after.phase is rc.TaskPhase.INTERRUPTED
    assert after.partial_output == "HALF-OUTPUT"

    parent.register_worker("parent-worker")
    assert parent.requeue("kill-task").phase is rc.TaskPhase.QUEUED
    resumed = parent.claim("kill-task", "parent-worker")
    assert resumed.attempt == 2 and resumed.partial_output == "HALF-OUTPUT"
    done = parent.complete("kill-task", "parent-worker", "finished")
    assert done.task.phase is rc.TaskPhase.COMPLETED
    assert parent.recover().interrupted == ()


def test_cross_process_duplicate_submission_admits_exactly_once(tmp_path):
    procs, gate = _spawn_gated(
        _CROSS_SUBMIT_CHILD, str(tmp_path / "state"), "ignored", count=4)
    results = []
    for proc in procs:
        out, err = proc.communicate(timeout=90)
        assert proc.returncode == 0, err
        results.append(out.strip())
    assert results.count("FIRST") == 1, results
    assert results.count("DUP") == 3, results

    ledger = rc.RecoveryLedger(tmp_path / "state", run_id="verifier")
    assert len(ledger.tasks()) == 1
    assert ledger.ops == 1
    with pytest.raises(rc.DuplicateSubmissionError):
        ledger.submit("other-task", idempotency_key="cross-key")


def test_bounded_retries_and_destructive_quarantine(tmp_path):
    now = [0.0]
    ledger = rc.RecoveryLedger(tmp_path / "state", run_id="main",
                               clock=lambda: now[0])
    ledger.register_worker("w1")
    policy = rc.RetryPolicy(max_attempts=2, base_delay=0.01)
    ledger.submit("bounded", policy=policy)
    for attempt in (1, 2):
        ledger.claim("bounded", "w1")
        decision = ledger.fail("bounded", "w1")
        assert decision.retry is (attempt == 1)
        now[0] += decision.delay
    final = ledger.task("bounded")
    assert final.phase is rc.TaskPhase.FAILED and final.attempt == 2
    with pytest.raises(rc.InvalidTransitionError):
        ledger.claim("bounded", "w1")

    ledger.submit("danger", destructive=True)
    with pytest.raises(rc.ApprovalRequiredError):
        ledger.claim("danger", "w1")
    ledger.approve("danger", "approval-1")
    ledger.requeue("danger")
    ledger.claim("danger", "w1")
    quarantined = ledger.fail("danger", "w1", kind=rc.FailureKind.WORKER_CRASH)
    assert quarantined.retry is False
    assert quarantined.task.phase is rc.TaskPhase.QUARANTINED
    with pytest.raises(rc.InvalidTransitionError):
        ledger.requeue("danger")
    assert ledger.task("danger").approval_token == ""
    ledger.approve("danger", "approval-2")
    ledger.requeue("danger")
    assert ledger.claim("danger", "w1").attempt == 2
