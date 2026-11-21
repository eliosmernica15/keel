"""C8.1 recoverable trash tests."""

from __future__ import annotations

from keel import trash
from keel.runner import RealTools


def test_delete_file_is_recoverable(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEL_TRASH_DIR", str(tmp_path / "trash"))
    target = tmp_path / "note.txt"
    target.write_text("important", encoding="utf-8")

    _, payload = RealTools().invoke("delete_file", {"path": str(target)})

    assert payload["recoverable"] is True
    assert not target.exists()
    items = trash.list_items()
    assert len(items) == 1
    restored = trash.restore(items[0]["id"])
    assert restored == target
    assert target.read_text(encoding="utf-8") == "important"
    assert trash.list_items() == []


def test_restore_unknown_id_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEL_TRASH_DIR", str(tmp_path / "trash"))
    import pytest

    with pytest.raises(trash.TrashError):
        trash.restore("missing")
