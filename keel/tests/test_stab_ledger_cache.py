"""Ledger verification is O(1) on cache hits and still fails closed on tampering."""
from __future__ import annotations

import json
import os
import subprocess
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


def test_idempotency_index_avoids_hot_scans_and_tracks_appends(
        tmp_path, monkeypatch):
    path = tmp_path / "workflow.jsonl"
    wf._append_jsonl(path, {"idempotency_key": "duplicate", "value": "first"})
    wf._append_jsonl(path, {"idempotency_key": "duplicate", "value": "last"})

    assert wf._find_idempotency_record(path, "duplicate")["value"] == "first"
    assert wf._find_idempotency_record(
        path, "duplicate", newest=True)["value"] == "last"

    original_read = wf._read_jsonl
    reads = 0

    def counted_read(target):
        nonlocal reads
        reads += 1
        return original_read(target)

    monkeypatch.setattr(wf, "_read_jsonl", counted_read)
    for _ in range(10):
        assert wf._find_idempotency_record(
            path, "duplicate", newest=True)["value"] == "last"
    wf._append_jsonl(path, {"idempotency_key": "local", "value": "local"})
    assert wf._find_idempotency_record(path, "local")["value"] == "local"
    assert reads == 0


def test_idempotency_index_revalidates_after_external_append(tmp_path):
    path = tmp_path / "workflow.jsonl"
    wf._append_jsonl(path, {"idempotency_key": "local"})
    assert wf._find_idempotency_record(path, "local") is not None

    source = Path(__file__).resolve().parents[1] / "src"
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from keel import backend_workflows as wf; "
        "wf._append_jsonl(sys.argv[2], {'idempotency_key': 'external'})"
    )
    subprocess.run(
        [sys.executable, "-c", code, str(source), str(path)],
        check=True, capture_output=True, text=True, timeout=30)

    record = wf._find_idempotency_record(path, "external")
    assert record is not None
    assert record["idempotency_key"] == "external"
