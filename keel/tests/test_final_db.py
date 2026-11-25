"""Final database & state-reliability verification (agent/final-db).

Every probe uses disposable temp directories and a clean HOME. No real user
database, backup, or settings file is read or modified.

Sections:
  1. one authoritative, absolute state root across CLI / web / store / DB;
  2. SQLite pragmas, transactions, concurrent writers, migrations and
     corruption detection;
  3. encrypted DB backup/restore, interrupted writes, refusal rules,
     rollback, retention and the CLI;
  4. honest forward-only migration policy.

Several tests in this module are *regression guards* for defects found during
verification: they were written to fail against the original code and pass
only after the fix in ``keel.fleet.db``.
"""

from __future__ import annotations

import json
import os
import re
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

SRC = Path(__file__).resolve().parents[1] / "src"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _read_only(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(backups._sqlite_uri(db, read_only=True), uri=True)


def _seed(db: Path, bot_id: str = "b1", name: str = "verified") -> None:
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


def _init_counter_db(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE counters(id TEXT PRIMARY KEY, writer TEXT NOT NULL, "
            "n INTEGER NOT NULL)")
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
    conn.execute("INSERT INTO counters(id,writer,n) VALUES(?,?,?)",
                 (f"{tag}:{i}", tag, i))
conn.commit()
conn.close()
"""


def _thread_writer(db: Path, tag: str, count: int) -> None:
    conn = sqlite3.connect(str(db), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN IMMEDIATE")
        for i in range(count):
            conn.execute("INSERT INTO counters(id,writer,n) VALUES(?,?,?)",
                         (f"{tag}:{i}", tag, i))
        conn.commit()
    finally:
        conn.close()


# ===========================================================================
# 1. one authoritative, absolute state root
# ===========================================================================
def test_default_db_path_uses_authoritative_state_root(tmp_path, monkeypatch):
    """REGRESSION: fleet.db used to hardcode ~/.keel, ignoring KEEL_STATE_DIR."""
    from keel.settings import default_state_root

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    root = (tmp_path / "configured-state").resolve()
    monkeypatch.setenv("KEEL_STATE_DIR", str(root))

    assert default_state_root() == root
    assert fleet_db.default_db_path() == root / "fleet.db"
    assert fleet_db.default_db_path().is_absolute()


def test_connect_without_path_creates_db_only_in_state_root(tmp_path, monkeypatch):
    """REGRESSION: a default connect() wrote a stray ~/.keel/fleet.db."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    root = (tmp_path / "configured-state").resolve()
    monkeypatch.setenv("KEEL_STATE_DIR", str(root))

    conn = connect()  # no explicit path
    try:
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] \
            == SCHEMA_VERSION
    finally:
        conn.close()

    assert (root / "fleet.db").is_file()
    assert not (home / ".keel").exists(), "a stray relative/home .keel was created"


def test_relative_db_path_is_normalised_to_absolute(tmp_path, monkeypatch):
    """connect() must never create an accidental relative DB file."""
    monkeypatch.chdir(tmp_path)
    seen: list[str] = []
    original_connect = sqlite3.connect

    def spy(*args, **kwargs):
        seen.append(str(args[0]))
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(fleet_db.sqlite3, "connect", spy)
    conn = connect(Path("relative-fleet.db"))
    try:
        assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] >= 1
    finally:
        conn.close()
    assert (tmp_path / "relative-fleet.db").is_file()
    assert seen, "sqlite3.connect was never called"
    assert Path(seen[0]).is_absolute(), f"relative DB path reached SQLite: {seen[0]}"


def test_cli_web_store_and_db_share_the_same_root(tmp_path, monkeypatch):
    from keel import settings, settings_store, webapp
    from keel.cli.main import _state_root

    root = (tmp_path / "shared-state").resolve()
    monkeypatch.setenv("KEEL_STATE_DIR", str(root))
    expected = settings.default_state_root()
    assert expected == root
    assert _state_root() == expected
    assert webapp._state_root() == expected
    assert settings_store.STATE_DIR.is_absolute()

    env = dict(os.environ, KEEL_STATE_DIR=str(root), HOME=str(tmp_path / "home"),
               USERPROFILE=str(tmp_path / "home"), PYTHONPATH=str(SRC))
    (tmp_path / "home").mkdir(exist_ok=True)
    probe = subprocess.run(
        [sys.executable, "-c",
         "from keel import settings, settings_store; "
         "import keel.fleet.db as fd; "
         "print(settings_store.STATE_DIR == settings.default_state_root() "
         "and fd.default_db_path() == settings.default_state_root()/'fleet.db')"],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "True"


def test_no_relative_keel_fallback_in_database_sources():
    """Owned modules must not reintroduce a relative `.keel` default."""
    bad_env = re.compile(
        r"os\.environ\.get\(\s*['\"]KEEL_STATE_DIR['\"]\s*,\s*['\"]\.keel['\"]")
    bad_home = re.compile(r"Path\.home\(\)\s*/\s*['\"]\.keel['\"]")
    for relative in ("keel/settings.py", "keel/settings_store.py",
                     "keel/fleet/db.py"):
        text = (SRC / relative).read_text(encoding="utf-8")
        assert not bad_env.search(text), f"relative KEEL_STATE_DIR default in {relative}"
        assert not bad_home.search(text), f"Path.home()/.keel fallback in {relative}"


# ===========================================================================
# 2. SQLite fundamentals, concurrency, migrations, corruption
# ===========================================================================
def test_wal_busy_timeout_fk_and_transactions(tmp_path):
    db = tmp_path / "fleet.db"
    conn = connect(db)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30_000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

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
                "VALUES('missing','message','bad-fk','t')")
        conn.execute("DELETE FROM bots WHERE id='a'")  # ON DELETE CASCADE
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM rows").fetchone()[0] == 0
    finally:
        conn.close()
    assert _read_only(db).execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_concurrent_first_open_is_serialized_across_threads_and_processes(
        tmp_path):
    db = tmp_path / "fleet.db"
    child = tmp_path / "gated.py"
    gate = tmp_path / "gate.txt"
    gate.unlink(missing_ok=True)
    child.write_text(
        "import os, sys, time\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from keel.fleet.db import connect\n"
        "while not os.path.exists(sys.argv[-1]):\n"
        "    time.sleep(0.002)\n"
        "c = connect(sys.argv[2])\n"
        "print('OK:' + str(c.execute("
        "'SELECT MAX(version) FROM schema_version').fetchone()[0]))\n"
        "c.close()\n", encoding="utf-8")
    procs = [subprocess.Popen(
        [sys.executable, str(child), str(SRC), str(db), str(gate)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(4)]
    thread_results: list[str] = []

    def thread_open(_i):
        while not gate.exists():
            time.sleep(0.002)
        try:
            conn = connect(db)
            thread_results.append("OK:" + str(conn.execute(
                "SELECT MAX(version) FROM schema_version").fetchone()[0]))
            conn.close()
        except Exception as exc:
            thread_results.append(f"FAIL:{type(exc).__name__}:{exc}")

    threads = [threading.Thread(target=thread_open, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    gate.write_text("go", encoding="utf-8")
    for t in threads:
        t.join(timeout=90)
        assert not t.is_alive()
    proc_results = []
    for proc in procs:
        out, err = proc.communicate(timeout=90)
        assert proc.returncode == 0, err
        proc_results.append(out.strip())

    results = thread_results + proc_results
    assert len(results) == 10, results
    assert all(r == f"OK:{SCHEMA_VERSION}" for r in results), results
    conn = _read_only(db)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_concurrent_writes_from_six_threads_and_four_processes_are_lossless(
        tmp_path):
    db = tmp_path / "concurrent.db"
    _init_counter_db(db)
    expected = 6 * 20 + 4 * 20

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda i: _thread_writer(db, f"t{i}", 20), range(6)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(
            lambda i: subprocess.run(
                [sys.executable, "-c", _PROCESS_WRITER, str(db), f"p{i}", "20"],
                capture_output=True, text=True, timeout=60, check=True),
            range(4)))

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM counters").fetchone()[0] == expected
        assert conn.execute("SELECT COUNT(DISTINCT id) FROM counters").fetchone()[0] \
            == expected
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


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


def test_empty_populated_and_legacy_migrations_preserve_data(tmp_path):
    empty = tmp_path / "empty.db"
    for _ in range(3):
        connect(empty).close()
    assert _read_only(empty).execute(
        "SELECT MAX(version) FROM schema_version").fetchone()[0] == SCHEMA_VERSION

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
            assert conn.execute(
                "SELECT body FROM rows WHERE bot_id='old'").fetchone()[0] == "legacy row"
        finally:
            conn.close()
    cols = {r[1] for r in _read_only(legacy).execute("PRAGMA table_info(bots)")}
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

    def boom():
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
        assert final.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] \
            == SCHEMA_VERSION
        assert final.execute("SELECT name FROM bots WHERE id='b1'").fetchone()[0] \
            == "verified"
    finally:
        final.close()


def test_corruption_detection_rejects_flips_fk_violations_and_truncation(tmp_path):
    good = tmp_path / "good.db"
    _seed(good)
    backup_database(good, tmp_path / "good-backups", "pw")

    flipped = tmp_path / "flipped.db"
    flipped.write_bytes(good.read_bytes())
    with flipped.open("r+b") as fh:
        fh.seek(4096)
        fh.write(b"\xff" * 128)
    with pytest.raises(DatabaseCorruptionError):
        backup_database(flipped, tmp_path / "bad-backups", "pw")

    fk_broken = tmp_path / "fk.db"
    raw = sqlite3.connect(fk_broken)
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.executescript(
        "CREATE TABLE parent(id TEXT PRIMARY KEY);"
        "CREATE TABLE child(id TEXT PRIMARY KEY, parent_id TEXT REFERENCES parent(id));"
        "INSERT INTO child VALUES('c','missing');")
    raw.commit()
    raw.close()
    with pytest.raises(DatabaseCorruptionError, match="foreign key"):
        backup_database(fk_broken, tmp_path / "bad-backups", "pw")

    for size in (0, 100):
        truncated = tmp_path / f"truncated-{size}.db"
        truncated.write_bytes(good.read_bytes()[:size])
        with pytest.raises(DatabaseCorruptionError):
            backup_database(truncated, tmp_path / "bad-backups", "pw")
    assert not list((tmp_path / "bad-backups").glob("*.dbbak"))


# ===========================================================================
# 3. encrypted backup / restore
# ===========================================================================
def test_manifest_hash_encryption_and_aad_are_verified(tmp_path):
    db = tmp_path / "db.sqlite"
    _seed(db)
    artifact = backup_database(db, tmp_path / "backups", "pw")
    path = Path(artifact["path"])
    doc = json.loads(path.read_text(encoding="utf-8"))

    assert doc["format"] == backups.DB_BACKUP_FORMAT
    assert doc["kdf"] == "PBKDF2-HMAC-SHA256"
    assert doc["iterations"] == backups.ITERATIONS
    assert doc["ciphertext"] and doc["ciphertext"] != doc["sha256"]
    assert verify_database_backup(path, "pw")["counts"]["bots"] == 1
    with pytest.raises(DatabaseBackupValidationError, match="wrong passphrase"):
        verify_database_backup(path, "wrong")

    cipher = bytearray(bytes.fromhex(doc["ciphertext"]))
    cipher[0] ^= 0xFF
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["ciphertext"] = cipher.hex()
    bad = tmp_path / "tampered.dbbak"
    bad.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(DatabaseBackupValidationError, match="corrupted"):
        verify_database_backup(bad, "pw")

    key = backups._derive("pw", bytes.fromhex(doc["salt"]))
    nonce = bytes.fromhex(doc["nonce"])
    payload = AESGCM(key).decrypt(nonce, bytes.fromhex(doc["ciphertext"]),
                                   backups._db_aad(doc))
    rebound = json.loads(json.dumps(doc))
    rebound["counts"]["bots"] += 99
    rebound["ciphertext"] = AESGCM(key).encrypt(
        nonce, payload, backups._db_aad(rebound)).hex()
    aad_bad = tmp_path / "aad.dbbak"
    aad_bad.write_text(json.dumps(rebound), encoding="utf-8")
    with pytest.raises(DatabaseBackupValidationError, match="manifest"):
        restore_database(aad_bad, tmp_path / "never.db", "pw")
    assert not (tmp_path / "never.db").exists()


def test_live_wal_data_is_captured_and_restored(tmp_path):
    db = tmp_path / "wal.db"
    _seed(db)
    conn = connect(db)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn.execute(
        "INSERT INTO rows(bot_id,kind,body,created_at) "
        "VALUES('b1','message','wal-only','t')")
    conn.commit()
    assert Path(str(db) + "-wal").exists()
    conn.close()

    artifact = backup_database(db, tmp_path / "backups", "pw")
    restored = tmp_path / "wal-restored.db"
    result = restore_database(artifact["path"], restored, "pw")
    assert result["counts"]["rows"] == 2
    check = _read_only(restored)
    try:
        assert "wal-only" in {r[0] for r in check.execute(
            "SELECT body FROM rows WHERE bot_id='b1'")}
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        check.close()


def test_restore_refuses_existing_target_and_active_sidecar(tmp_path):
    db = tmp_path / "db.sqlite"
    _seed(db)
    artifact = backup_database(db, tmp_path / "backups", "pw")
    target = tmp_path / "target.db"
    restore_database(artifact["path"], target, "pw")

    before = target.read_bytes()
    with pytest.raises(DatabaseRestoreError, match="already exists"):
        restore_database(artifact["path"], target, "pw")
    assert target.read_bytes() == before

    sidecar = Path(str(target) + "-wal")
    sidecar.write_bytes(b"live-wal")
    with pytest.raises(DatabaseRestoreError, match="sidecar"):
        restore_database(artifact["path"], target, "pw", overwrite=True)
    assert sidecar.read_bytes() == b"live-wal"
    assert target.read_bytes() == before

    sidecar.unlink()
    assert restore_database(artifact["path"], target, "pw",
                            overwrite=True)["counts"]["bots"] == 1


def test_failed_post_write_verification_rolls_back_only_our_write(
        tmp_path, monkeypatch):
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
    check = _read_only(target)
    try:
        assert check.execute("SELECT name FROM bots WHERE id='old'").fetchone()[0] \
            == "previous-state"
    finally:
        check.close()


def test_interrupted_backup_write_leaves_previous_artifact_intact(
        tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite"
    _seed(db)
    target = tmp_path / "backups" / "existing.dbbak"
    target.parent.mkdir()
    old_bytes = b'{"format":"keel-db-backup-v1","old":true}'
    target.write_bytes(old_bytes)

    original_replace = os.replace
    calls = []

    def always_denied(src, dst, *args, **kwargs):
        calls.append(1)
        raise OSError(5, "Access is denied", None, 5)

    monkeypatch.setattr(os, "replace", always_denied)
    monkeypatch.setattr(backups.time, "sleep", lambda _seconds: None)
    with pytest.raises(OSError):
        backup_database(db, target.parent, "pw")  # publishes a *different* file
    assert old_bytes == target.read_bytes()
    # The new artifact's own temp file is cleaned up; the old one is untouched.
    assert not [p for p in target.parent.iterdir() if p.name.endswith(".tmp")]

    monkeypatch.setattr(os, "replace", original_replace)
    result = backup_database(db, target.parent, "pw")
    assert verify_database_backup(result["path"], "pw")["counts"]["bots"] == 1


def test_retention_and_cli_roundtrip(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    _seed(db)
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

    restored = tmp_path / "cli-restored.db"
    assert backups.main(["db-restore", "--backup", created["path"],
                         "--to", str(restored), "--passphrase", "pw"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["bots"] == 1
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
    dry = prune_database_backups(directory, keep=1, dry_run=True)
    assert len(dry["removed"]) == 1 and dry["dry_run"] is True


# ===========================================================================
# 4. forward-only migration policy is documented, not invented
# ===========================================================================
def test_forward_only_migration_policy_is_documented():
    text = (SRC / "keel/fleet/db.py").read_text(encoding="utf-8")
    normalised = " ".join(text.lower().split())
    assert "forward-only" in normalised
    assert "no down migrations" in normalised
    assert "no automatic rollback" in normalised
    assert "explicit restore" in normalised
    evidence = Path(__file__).resolve().parents[2] / "FINAL-DATABASE-EVIDENCE.md"
    if evidence.is_file():  # the report is authored alongside these tests
        body = evidence.read_text(encoding="utf-8").lower()
        assert "forward-only" in body
        assert "no down migration" in body
