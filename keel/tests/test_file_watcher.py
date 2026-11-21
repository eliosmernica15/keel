"""C5.4 — real file watcher triggers."""

from __future__ import annotations

import time

from keel.file_watcher import FileWatcher


def test_poll_detects_created_modified_deleted(tmp_path):
    watcher = FileWatcher(tmp_path, interval=0.05)
    assert watcher.poll_once() == []  # baseline
    target = tmp_path / "note.txt"
    target.write_text("one")
    assert watcher.poll_once() == [{"kind": "created", "path": "note.txt"}]
    target.write_text("two")
    assert watcher.poll_once() == [{"kind": "modified", "path": "note.txt"}]
    target.unlink()
    assert watcher.poll_once() == [{"kind": "deleted", "path": "note.txt"}]


def test_background_watcher_dispatches(tmp_path):
    seen = []
    watcher = FileWatcher(tmp_path, interval=0.02)
    watcher.start(seen.append)
    time.sleep(0.05)
    (tmp_path / "new.txt").write_text("data")
    deadline = time.time() + 2
    while time.time() < deadline and not seen:
        time.sleep(0.02)
    watcher.stop()
    assert any(c["path"] == "new.txt" for c in seen)
