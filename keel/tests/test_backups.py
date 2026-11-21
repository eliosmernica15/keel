"""B4.11 — real encrypted backup and restore."""

from __future__ import annotations

import pytest

from keel.backups import BackupError, create_backup, restore_backup


def test_encrypted_backup_restore(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "note.txt").write_text("secret content", encoding="utf-8")
    (source / "sub").mkdir()
    (source / "sub" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    meta = create_backup(source, tmp_path / "backup.json", "pass123")
    assert meta["files"] == 2
    backup_text = (tmp_path / "backup.json").read_text(encoding="utf-8")
    assert "secret content" not in backup_text  # encrypted at rest

    restored = tmp_path / "restored"
    files = restore_backup(tmp_path / "backup.json", restored, "pass123")
    assert files == ["note.txt", "sub/data.csv"]
    assert (restored / "sub" / "data.csv").read_text() == "a,b\n1,2\n"


def test_wrong_passphrase_fails(tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    (source / "x").write_text("x", encoding="utf-8")
    create_backup(source, tmp_path / "b.json", "right")
    with pytest.raises(BackupError, match="wrong passphrase"):
        restore_backup(tmp_path / "b.json", tmp_path / "out", "wrong")


def test_tampered_backup_fails(tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    (source / "x").write_text("x", encoding="utf-8")
    create_backup(source, tmp_path / "b.json", "pw")
    path = tmp_path / "b.json"
    doc = path.read_text(encoding="utf-8").replace('"format"', '"formatX"')
    path.write_text(doc, encoding="utf-8")
    with pytest.raises(BackupError, match="unsupported"):
        restore_backup(path, tmp_path / "out", "pw")
