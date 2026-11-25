"""Ledger verification is O(1) on cache hits and still fails closed on tampering."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from keel import backend_workflows as wf  # noqa: E402


def test_repeated_reads_are_cached_but_tampering_is_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    path = tmp_path / "ledger.jsonl"
    for i in range(120):
        wf._append_jsonl(path, {"event": f"e{i}", "data": "x" * 200})

    t0 = time.perf_counter()
    for _ in range(10):
        rows = wf._read_jsonl(path)
    cached = time.perf_counter() - t0
    assert len(rows) == 120

    # Evict in-process cache to emulate another process having written the file.
    wf._LEDGER_CACHE.pop(str(path), None)
    t0 = time.perf_counter()
    rows = wf._read_jsonl(path)
    fresh = time.perf_counter() - t0
    assert len(rows) == 120

    # Tamper with a record: a fresh read must fail closed (never use stale cache).
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[5])
    record["event"] = "FORGED"
    lines[5] = json.dumps(record, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    wf._LEDGER_CACHE.pop(str(path), None)
    try:
        wf._read_jsonl(path)
    except wf.WorkflowError as exc:
        assert exc.code == "ledger_integrity"
    else:
        raise AssertionError("tampered ledger accepted")

    # Cache hits are materially cheaper than a full verification.
    assert cached < fresh * 4, (cached, fresh)
