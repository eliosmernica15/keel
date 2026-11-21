"""C8.4/C8.6/C8.7 — canary files, content store, DB resilience."""

from __future__ import annotations

import sqlite3

from keel.resilience import (CanaryFiles, ContentStore, db_backup,
                             db_integrity)


def test_canary_files(tmp_path):
    canaries = CanaryFiles(tmp_path)
    canaries.add("secrets/canary.txt")
    assert canaries.touches("secrets/canary.txt") is True
    assert canaries.touches("normal.txt") is False
    canaries.add("honeyfolder")
    assert canaries.touches("honeyfolder/a.txt") is True


def test_content_store_dedupe(tmp_path):
    store = ContentStore(tmp_path)
    digest = store.put(b"hello")
    assert store.put(b"hello") == digest
    assert store.get(digest) == b"hello"
    assert store.get("0" * 64) is None


def test_db_integrity_and_backup(tmp_path):
    db = tmp_path / "test.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.execute("INSERT INTO t VALUES ('a')")
    assert db_integrity(db) is True
    backup = db_backup(db, tmp_path / "backup.db")
    assert backup.is_file() and db_integrity(backup) is True
