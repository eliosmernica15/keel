"""Behavioral tests for the real backend observability service.

Every assertion reads or mutates an actual JSONL log; no internal function is
mocked.  Tampering is performed on the persisted bytes, concurrency uses real
threads, and unwritable storage is represented by a real filesystem condition.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from keel import backend_observability as obs
from keel.backend_hub import MODULE_FEATURES


MULTI_WORD_SECRET = "trident lunar velvet compass"
BEARER_SECRET = "Bearer abcdef1234567890XYZ"
NESTED_SECRET = "salted caramel universe seven"


def _log(state_root) -> object:
    from pathlib import Path
    return Path(state_root) / obs.LOG_FILENAME


# ---------------------------------------------------------------------------
# Event writing, reading and chain verification
# ---------------------------------------------------------------------------

def test_record_event_writes_real_jsonl_with_structured_fields(tmp_path):
    event = obs.record_event(
        "workflow.start",
        session_id="session-1",
        task_id="task-7",
        agent_id="agent-42",
        feature_id="D3.1",
        module="d3_backend",
        data={"step": 1},
        state_root=tmp_path,
        clock=lambda: 1_700_000_000.0,
    )

    assert _log(tmp_path).is_file()
    stored = _log(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(stored) == 1
    assert json.loads(stored[0]) == event

    assert event["seq"] == 1
    assert event["kind"] == "workflow.start"
    assert event["session_id"] == "session-1"
    assert event["task_id"] == "task-7"
    assert event["agent_id"] == "agent-42"
    assert event["feature_id"] == "D3.1"
    assert event["module"] == "d3_backend"
    assert event["data"] == {"step": 1}
    assert event["ts"] == "2023-11-14T22:13:20.000000Z"
    assert len(event["correlation_id"]) == 32
    assert event["prev_hash"] == obs.GENESIS_HASH
    assert len(event["hash"]) == 64


def test_read_events_filters_and_verify_chain_is_real(tmp_path):
    for index in range(3):
        obs.record_event(
            "error" if index % 2 else "workflow.start",
            session_id="s1" if index < 2 else "s2",
            module="d3_backend",
            data={"index": index},
            state_root=tmp_path,
        )

    result = obs.verify_chain(tmp_path)
    assert result.ok is True
    assert result["event_count"] == 3
    assert result["first_seq"] == 1
    assert result["last_seq"] == 3
    assert result["error"] is None

    all_events = obs.read_events(tmp_path)
    assert [ev["seq"] for ev in all_events] == [1, 2, 3]
    assert [ev["kind"] for ev in obs.read_events(tmp_path, kind="error")] == ["error"]
    assert len(obs.read_events(tmp_path, session_id="s1")) == 2
    assert [ev["seq"] for ev in obs.read_events(tmp_path, since_seq=2)] == [3]


def test_empty_state_verifies_as_ok(tmp_path):
    result = obs.verify_chain(tmp_path)
    assert result.ok is True
    assert result.event_count == 0
    assert obs.read_events(tmp_path) == []


def test_hash_chain_detects_tampering(tmp_path):
    for index in range(3):
        obs.record_event("workflow.step", session_id="s", data={"index": index},
                         state_root=tmp_path)

    path = _log(tmp_path)
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"index":2', '"index":99'), encoding="utf-8")

    result = obs.verify_chain(tmp_path)
    assert result.ok is False
    assert not result  # corrupt results are falsy, not silently truthy
    assert "hash" in result.error.lower() or "mismatch" in result.error.lower()
    with pytest.raises(obs.ChainIntegrityError):
        obs.read_events(tmp_path)


def test_corrupt_chain_is_fail_closed_for_appends(tmp_path):
    obs.record_event("first", session_id="s", state_root=tmp_path)
    obs.record_event("second", session_id="s", state_root=tmp_path)
    path = _log(tmp_path)
    before = path.read_text(encoding="utf-8")
    lines = before.splitlines()
    broken = json.loads(lines[1])
    broken["data"] = {"injected": True}
    lines[1] = json.dumps(broken, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(obs.ChainIntegrityError):
        obs.record_event("third", session_id="s", state_root=tmp_path)

    assert path.read_text(encoding="utf-8") == "\n".join(lines) + "\n"
    assert obs.verify_chain(tmp_path).ok is False


def test_injectable_clock_controls_utc_timestamp(tmp_path):
    fixed = datetime(2024, 3, 5, 6, 7, 8, tzinfo=timezone.utc)
    event = obs.record_event("clocked", session_id="s", state_root=tmp_path,
                             clock=lambda: fixed)
    assert event["ts"] == "2024-03-05T06:07:08.000000Z"


# ---------------------------------------------------------------------------
# Redaction before persistence
# ---------------------------------------------------------------------------

def test_redact_strips_multi_word_secret_and_bearer_token():
    event = {
        "kind": "error",
        "data": {
            "note": f"api_key = '{MULTI_WORD_SECRET}'",
            "Authorization": BEARER_SECRET,
            "api_key": NESTED_SECRET,
            "nested": [{"token": BEARER_SECRET}, {"safe": "ordinary text"}],
        },
    }
    safe = obs.redact(event)

    # Input is never mutated.
    assert event["data"]["note"] == f"api_key = '{MULTI_WORD_SECRET}'"
    assert event["data"]["Authorization"] == BEARER_SECRET

    dumped = json.dumps(safe)
    assert MULTI_WORD_SECRET not in dumped
    assert BEARER_SECRET not in dumped
    assert NESTED_SECRET not in dumped
    assert "[REDACTED]" in dumped
    assert safe["data"]["nested"][1]["safe"] == "ordinary text"


def test_record_event_never_persists_raw_credentials(tmp_path):
    obs.record_event(
        "error",
        session_id="s",
        module="d3_backend",
        data={
            "message": f"api_key = '{MULTI_WORD_SECRET}'",
            "Authorization": BEARER_SECRET,
        },
        state_root=tmp_path,
    )
    raw = _log(tmp_path).read_text(encoding="utf-8")
    assert MULTI_WORD_SECRET not in raw
    assert BEARER_SECRET not in raw
    assert "[REDACTED]" in raw
    assert obs.verify_chain(tmp_path).ok is True


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

def test_concurrent_writers_lose_no_events(tmp_path):
    def write(index: int):
        return obs.record_event(
            "stress",
            session_id=f"session-{index % 2}",
            task_id=f"task-{index}",
            data={"index": index},
            state_root=tmp_path,
        )

    with ThreadPoolExecutor(max_workers=20) as pool:
        written = list(pool.map(write, range(20)))

    assert len(written) == 20
    assert len({event["correlation_id"] for event in written}) == 20

    events = obs.read_events(tmp_path)
    assert len(events) == 20
    assert [ev["seq"] for ev in events] == list(range(1, 21))
    assert sorted(ev["data"]["index"] for ev in events) == list(range(20))
    assert obs.verify_chain(tmp_path).ok is True
    assert len(_log(tmp_path).read_text(encoding="utf-8").splitlines()) == 20


# ---------------------------------------------------------------------------
# Storage failures
# ---------------------------------------------------------------------------

def test_unwritable_state_root_raises_typed_error_and_writes_nothing(tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("occupied", encoding="utf-8")
    state_root = blocker / "state"

    with pytest.raises(obs.ObservabilityStorageError):
        obs.record_event("error", session_id="s", state_root=state_root)

    assert not (state_root / obs.LOG_FILENAME).exists()
    assert not (state_root / (obs.LOG_FILENAME + ".lock")).exists()


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def test_health_snapshot_imports_real_modules_and_reports_errors(tmp_path):
    real_modules = list(MODULE_FEATURES)[:5]
    requested = real_modules + ["no_such_backend_module"]

    snapshot = obs.health_snapshot(tmp_path, requested)

    assert snapshot["module_count"] == len(requested)
    for name in real_modules:
        entry = snapshot["modules"][name]
        assert entry["import_status"] == "ok"
        assert entry["imported"] is True
        assert entry["healthy"] is True
        assert entry["import_error"] is None
        assert entry["feature_count"] == len(MODULE_FEATURES[name])
        assert entry["feature_source"] == "backend_hub.MODULE_FEATURES"

    missing = snapshot["modules"]["no_such_backend_module"]
    assert missing["import_status"] == "error"
    assert missing["imported"] is False
    assert missing["healthy"] is False
    assert missing["import_error"]
    assert snapshot["healthy"] is False


def test_health_snapshot_reports_redacted_recorded_errors(tmp_path):
    obs.record_event(
        "error",
        session_id="s",
        module="d3_backend",
        data={"detail": f"api_key = '{MULTI_WORD_SECRET}'"},
        state_root=tmp_path,
    )
    snapshot = obs.health_snapshot(tmp_path, ["d3_backend"])
    entry = snapshot["modules"]["d3_backend"]

    assert entry["healthy"] is True  # import succeeded; the error is reported
    assert entry["error_count"] == 1
    assert MULTI_WORD_SECRET not in json.dumps(entry["errors"])
    assert entry["errors"][0]["data"]["detail"] == "[REDACTED]"


def test_diagnostic_report_counts_sessions_and_redacts_recent_errors(tmp_path):
    obs.record_event("workflow.start", session_id="s1", state_root=tmp_path)
    obs.record_event("workflow.step", session_id="s1", state_root=tmp_path)
    obs.record_event(
        "error", session_id="s2", module="d3_backend",
        data={"detail": BEARER_SECRET}, state_root=tmp_path,
    )

    report = obs.diagnostic_report(tmp_path)
    assert report["chain_status"] == "ok"
    assert report["chain"]["ok"] is True
    assert report["total_events"] == 3
    assert report["counts_by_kind"] == {
        "error": 1, "workflow.start": 1, "workflow.step": 1,
    }
    assert report["counts_by_session"] == {"s1": 2, "s2": 1}
    assert report["recent_error_count"] == 1
    assert BEARER_SECRET not in json.dumps(report["recent_errors"])
    assert "[REDACTED]" in json.dumps(report["recent_errors"])


def test_diagnostic_report_surfaces_corrupt_chain(tmp_path):
    obs.record_event("workflow.start", session_id="s", state_root=tmp_path)
    path = _log(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace('"seq":1', '"seq":5'),
                    encoding="utf-8")

    report = obs.diagnostic_report(tmp_path)
    assert report["chain_status"] == "corrupt"
    assert report["chain"]["ok"] is False
    assert report["chain"]["error"]
