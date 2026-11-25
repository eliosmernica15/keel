"""Surface service tests: real deliverables, checkpoints, context, terminal, notifications, git."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from keel import capabilities  # noqa: E402
from keel import surface_services_backend as s  # noqa: E402

ALL = {"read", "write", "execute"}


def test_deliverable_record_and_export(tmp_path):
    rec = s.deliverable_record("t1", [{"path": "a.txt", "content": "hi", "kind": "new"}])
    assert rec["count"] == 1 and rec["deliverables"][0]["path"] == "a.txt"
    out = s.export_deliverables_zip("t1", {"a.txt": "hi"}, tmp_path / "out.zip")
    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        assert zf.read("a.txt") == b"hi"


def test_checkpoint_roundtrip(tmp_path):
    root = tmp_path / "state"
    snap = s.create_checkpoint(root, "turn1", {"x.py": "print(1)"})
    assert (snap / "x.py").exists()
    res = s.restore_checkpoint(root, "turn1")
    assert res["count"] == 1 and res["restored"][0]["path"] == "x.py"


def test_checkpoint_restore_rejects_path_traversal(tmp_path):
    root = tmp_path / "state"
    s.create_checkpoint(root, "turn2", {"evil": "x"})
    (root / "checkpoints" / "turn2" / "manifest.json").write_text(
        '{"turn_id":"turn2","files":[{"path":"../escape","bytes":1}]}',
        encoding="utf-8")
    try:
        s.restore_checkpoint(root, "turn2")
    except s.SurfaceError:
        pass
    else:
        raise AssertionError("path traversal accepted")


def test_trash_moves_file(tmp_path):
    root = tmp_path / "state"
    f = tmp_path / "a.txt"; f.write_text("x", encoding="utf-8")
    loc = s.trash_path(root, f)
    assert loc.exists() and not f.exists()


def test_context_inspector(tmp_path):
    r = s.context_inspector([{"name": "system", "text": "a" * 400, "token_estimate": 0}])
    assert r["count"] == 1 and r["total_tokens"] >= 1


def test_notification_queue(tmp_path):
    q = s.NotificationQueue(tmp_path / "state")
    n = q.push("done", "Title", "Body")
    assert n.title == "Title"
    assert len(q.list()) == 1
    assert q.ack(0) is True
    assert q.list()[0].acknowledged is True


def test_git_integration(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    try:
        s.git_status(repo)
    except s.SurfaceError:
        pass
    else:
        raise AssertionError("git_status accepted a non-repo")
    out = s.git_init(repo)
    assert "Initialized" in out or "Reinitialized" in out
    (repo / "f.txt").write_text("hi", encoding="utf-8")
    assert "f.txt" in " ".join(s.git_status(repo))
    diff = s.git_diff(repo)
    assert "f.txt" in diff or diff == ""
    sha = s.git_commit(repo, "initial", allow_write=True)
    assert sha is not None
    assert s.git_status(repo) == []


def test_terminal_run_sync():
    code, out = s.TerminalSession([sys.executable, "-c", "print('hi')"]).run_sync(timeout=5.0)
    assert code == 0 and b"hi" in out


def test_terminal_cancel():
    import threading
    sess = s.TerminalSession([sys.executable, "-c", "import time; time.sleep(30)"])
    sess.start()
    sess.cancel()
    st = sess.status()
    assert st["state"] == "exited"


def test_capability_surface_services_registered():
    ids = {c["id"] for c in capabilities.list_capabilities()}
    assert "surface.deliverables.record" in ids
    assert "surface.terminal.run" in ids
    r = capabilities.invoke("surface.context.inspect", {"sources": [
        {"name": "s", "text": "hello", "token_estimate": 0}]}, allowed_permissions={"read"})
    assert r["ok"] is True and r["result"]["total_tokens"] >= 1
    r2 = capabilities.invoke("surface.terminal.run", {"command": [sys.executable, "-c", "print(42)"]},
                             allowed_permissions={"read", "execute"})
    assert r2["ok"] is True and "42" in r2["result"]["output"]


def test_git_commit_requires_allow_write():
    import tempfile
    repo = Path(tempfile.mkdtemp()) / "r"; repo.mkdir()
    s.git_init(repo)
    try:
        s.git_commit(repo, "msg")
    except s.SurfaceError:
        pass
    else:
        raise AssertionError("commit without allow_write accepted")


def test_checkpoint_path_traversal_rejected(tmp_path):
    root = tmp_path / "st"
    s.create_checkpoint(root, "t", {"evil": "x"})
    manifest = root / "checkpoints" / "t" / "manifest.json"
    manifest.write_text('{"turn_id":"t","files":[{"path":"../escape","bytes":1}]}', encoding="utf-8")
    (root / "checkpoints" / "t" / "escape").write_text("x", encoding="utf-8")
    try:
        s.restore_checkpoint(root, "t")
    except s.SurfaceError:
        pass
    else:
        raise AssertionError("traversal checkpoint accepted")
