"""C11.6/C13.x/C4.7 — eval helpers."""

from __future__ import annotations

import hashlib

from keel.eval_tools import (TrendStore, judge_trajectory, profile_call,
                             prompt_regression, verify_official_build)


def test_official_build_verification(tmp_path):
    path = tmp_path / "app.exe"
    path.write_bytes(b"binary")
    digest = hashlib.sha256(b"binary").hexdigest()
    assert verify_official_build(path, digest) is True
    assert verify_official_build(path, "0" * 64) is False


def test_judge_and_regression(tmp_path):
    score = judge_trajectory([{"ok": True}, {"ok": True}])
    assert score["score"] > 0.9
    assert prompt_regression("p1", "output", tmp_path) is True
    assert prompt_regression("p1", "output", tmp_path) is True
    assert prompt_regression("p1", "changed", tmp_path) is False


def test_trend_and_profile(tmp_path):
    store = TrendStore(tmp_path)
    entry = store.record("0.1.1", startup_ms=100, memory_mb=50, size_mb=80)
    assert entry["version"] == "0.1.1"
    prof = profile_call(lambda x: x + 1, 1)
    assert prof["result"] == 2 and prof["elapsed_ms"] >= 0
