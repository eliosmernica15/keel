"""A3.x — operations helpers."""

from __future__ import annotations

import os
import time

from keel.ops_tools import (gc_temp_dirs, project_status, retry_backoff,
                            setup_env_example)


def test_retry_backoff():
    assert retry_backoff(1) == 1.0
    assert retry_backoff(3) == 4.0
    assert retry_backoff(20) <= 60.0


def test_gc_temp_dirs(tmp_path):
    temp = tmp_path / "temp"
    temp.mkdir()
    old = temp / "old"
    old.mkdir()
    os.utime(old, (time.time() - 100000, time.time() - 100000))
    recent = temp / "recent"
    recent.mkdir()
    removed = gc_temp_dirs(tmp_path, max_age_s=1000)
    assert "old" in removed and "recent" not in removed


def test_setup_and_status(tmp_path):
    path = setup_env_example(tmp_path, keys=["KEEL_TOKEN", "KEEL_STATE_DIR"])
    assert "KEEL_TOKEN=" in path.read_text(encoding="utf-8")
    status = project_status(10, 2, 1)
    assert status["verified"] == 10
