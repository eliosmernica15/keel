"""C9.3 — real incremental repository indexing with content hashes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from keel.repo_index import (IndexStore, build_index, search_index,
                             update_index)

ROOT = Path(__file__).resolve().parents[1]


def _tree(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "README.md").write_text("# Demo\nhello index\n", encoding="utf-8")
    (root / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (root / ".git" / "config").write_text("secret", encoding="utf-8")
    return root


def test_build_index_skips_ignores(tmp_path):
    index = build_index(_tree(tmp_path))
    assert index["count"] == 2
    assert "README.md" in index["files"] and "src/main.py" in index["files"]
    assert not any(".git" in p for p in index["files"])


def test_incremental_update_detects_changes(tmp_path):
    root = _tree(tmp_path)
    index = build_index(root)
    original_hash = index["files"]["README.md"]["hash"]
    unchanged = update_index(index, root)
    assert unchanged["rehashed"] == 0
    assert unchanged["added"] == [] and unchanged["modified"] == []

    (root / "README.md").write_text("# Demo\nchanged content\n", encoding="utf-8")
    (root / "new.py").write_text("x = 1\n", encoding="utf-8")
    (root / "src" / "main.py").unlink()
    changed = update_index(index, root)
    assert "README.md" in changed["modified"]
    assert "new.py" in changed["added"]
    assert "src/main.py" in changed["removed"]
    assert changed["files"]["README.md"]["hash"] != original_hash
    assert changed["count"] == 2


def test_search_path_and_content(tmp_path):
    index = build_index(_tree(tmp_path))
    assert any(h["path"] == "README.md"
               for h in search_index(index, "readme")["hits"])
    assert any(h["matched"] == "content"
               for h in search_index(index, "hello", content=True)["hits"])
    assert search_index(index, "   ")["hits"] == []


def test_store_roundtrip(tmp_path):
    store = IndexStore(tmp_path)
    index = build_index(_tree(tmp_path))
    store.save("repo", index)
    assert store.list() == ["repo"]
    assert store.load("repo")["count"] == 2


def test_capability_integration(tmp_path):
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    root = str(_tree(tmp_path))
    state = str(tmp_path / "state")
    built = invoke("code.repoindex.build",
                   {"name": "repo", "root": root, "state_root": state},
                   context={})["result"]
    assert built["count"] == 2
    found = invoke("code.repoindex.search",
                   {"name": "repo", "query": "readme", "state_root": state},
                   context={})["result"]
    assert found["hits"]


def test_cli_repoindex(tmp_path):
    root = str(_tree(tmp_path))
    state = tmp_path / "state"
    env = {**os.environ, "KEEL_STATE_DIR": str(state)}
    build = subprocess.run(
        [sys.executable, "-m", "keel", "repoindex", "build", "repo", root],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert build.returncode == 0, build.stderr
    assert json.loads(build.stdout)["count"] == 2
    found = subprocess.run(
        [sys.executable, "-m", "keel", "repoindex", "search", "repo", "README"],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert found.returncode == 0, found.stderr
    assert json.loads(found.stdout)["hits"]
