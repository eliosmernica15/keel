"""C4.9 — real git extras with write gating."""

from __future__ import annotations

import subprocess

import pytest

from keel.git_extras_runtime import GitError, blame, log, stacked_commit, status


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "a@b.c"],
                   check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Tester"],
                   check=True)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "first"],
                   check=True)
    return tmp_path


def test_read_ops(repo):
    assert isinstance(status(repo), list)
    assert any("first" in line for line in log(repo))
    assert any("a.txt" in line or "x" in line for line in blame(repo, "a.txt"))


def test_write_gating(repo):
    with pytest.raises(GitError, match="allow_write"):
        stacked_commit(repo, "msg")
    (repo / "b.txt").write_text("y", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "b.txt"], check=True)
    out = stacked_commit(repo, "second", allow_write=True)
    assert "second" in out or "1 file" in out


def test_not_a_repo(tmp_path):
    with pytest.raises(GitError, match="not a git repository"):
        status(tmp_path)
