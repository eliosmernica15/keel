"""Stabilization integration evidence for events and observability.

This file records the *boundary* between the real runtime event systems and
the durable library contracts owned by the stabilization agent, and exercises
the hardening fixes: cross-process durable publishing, forensic (archive,
never delete) retention, three-way health distinction and end-to-end
redaction. All assertions read real files, real subprocesses or real modules.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from keel import backend_events as be
from keel import backend_observability as obs

SRC = Path(__file__).resolve().parents[1] / "src"

MULTI_WORD_SECRET = "harbor lantern amber delta"
BEARER_SECRET = "Bearer sk-abcdefghijklmnopqrstuv"
NESTED_SECRET = "vault melon orbit seven"


def _assert_no_secrets(value: object) -> None:
    dumped = json.dumps(value, default=str)
    for secret in (MULTI_WORD_SECRET, BEARER_SECRET,
                   BEARER_SECRET.split(None, 1)[1], NESTED_SECRET):
        assert secret not in dumped


# ---------------------------------------------------------------------------
# 1. Event-system boundary: do not create a competing runtime event bus
# ---------------------------------------------------------------------------

def test_backend_events_is_a_library_boundary_not_a_runtime_consumer() -> None:
    source = SRC / "keel"
    offenders = []
    for path in sorted(source.rglob("*.py")):
        if path.name == "backend_events.py":
            continue
        if "backend_events" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(SRC).as_posix())
    assert offenders == [], offenders

    # The authoritative runtime event systems are verified to be wired:
    # stream-json union in session/runner, local fleet bus in the registry.
    session = (source / "session.py").read_text(encoding="utf-8")
    runner = (source / "runner.py").read_text(encoding="utf-8")
    registry = (source / "capability_registry.py").read_text(encoding="utf-8")
    assert "ev.system_init(" in session and "ev.result(" in session
    assert "ev.result(" in runner
    assert "from .automation import EventBus" in registry
    assert "fleet.eventbus.publish" in registry


# ---------------------------------------------------------------------------
# 2. Durable backend event contract (library, not runtime-wired)
# ---------------------------------------------------------------------------

_WORKER = r"""
import sys
sys.path.insert(0, sys.argv[1])
from keel.backend_events import DeliveryTracker, EventBus, SessionStarted
root, index = sys.argv[2], sys.argv[3]
event = SessionStarted(event_id=f"stab-evt-{index}", session_id=f"stab-s-{index}")
assert EventBus(root).publish(event) is True
DeliveryTracker(root).register(event.event_id, "sink", max_attempts=2)
"""

def test_backend_events_cross_process_replay_and_delivery(tmp_path: Path) -> None:
    workers = 4
    results = [
        subprocess.run(
            [sys.executable, "-c", _WORKER, str(SRC), str(tmp_path), str(index)],
            capture_output=True, text=True, timeout=90,
        )
        for index in range(workers)
    ]
    for result in results:
        assert result.returncode == 0, result.stderr

    bus = be.EventBus(tmp_path)
    events = bus.replay()
    assert [event.event_id for event in events] == [
        f"stab-evt-{index}" for index in range(workers)]
    assert [record["seq"] for record in bus._store.records] == list(
        range(1, workers + 1))
    # Idempotent retry and a conflicting payload are handled explicitly.
    assert bus.publish(events[0]) is False
    with pytest.raises(be.DuplicateEventError):
        bus.publish(be.SessionStarted(
            event_id=events[0].event_id, session_id="different"))

    tracker = be.DeliveryTracker(tmp_path)
    assert set(tracker.states()) == {
        (f"stab-evt-{index}", "sink") for index in range(workers)}
    assert len(tracker.pending()) == workers
    delivered = tracker.record_attempt("stab-evt-0", "sink", ok=True)
    assert delivered.is_success is True
    assert be.DeliveryTracker(tmp_path).state("stab-evt-0", "sink") == delivered


# ---------------------------------------------------------------------------
# 3. Observability event kinds and three-way health
# ---------------------------------------------------------------------------

def test_observability_records_runtime_event_kinds_with_correlation(tmp_path) -> None:
    kinds = [
        "workflow.start", "workflow.success", "workflow.denied",
        "workflow.failure", "task.created", "task.assigned",
        "task.completed", "tool.invoked", "tool.failed",
        "provider.failed", "recovery.started", "recovery.completed",
        "security.denied",
    ]
    for kind in kinds:
        obs.record_event(kind, session_id="stab-session", module="d3_backend",
                         data={"kind": kind}, state_root=tmp_path)

    events = obs.read_events(tmp_path)
    assert [event["kind"] for event in events] == kinds
    assert len({event["correlation_id"] for event in events}) == len(kinds)
    assert [event["seq"] for event in events] == list(range(1, len(kinds) + 1))
    assert obs.verify_chain(tmp_path).ok is True


def test_health_distinguishes_liveness_initialization_readiness_and_deps(
        tmp_path) -> None:
    fresh = obs.health_check(tmp_path, [])
    assert fresh["liveness"]["status"] == "running"
    assert fresh["running"] is True
    assert fresh["initialized"] is False  # no log has been established yet
    assert fresh["ready"] is True         # a fresh install is operational

    obs.record_event("workflow.start", session_id="s", state_root=tmp_path)
    ready = obs.health_check(tmp_path, [])
    assert ready["initialized"] is True
    assert ready["ready"] is True

    payload = obs.health_http_payload(tmp_path, [])
    assert payload["running"] is True
    assert payload["initialized"] is True
    assert payload["ready"] is True
    for name in ("database", "provider", "worker", "event_log"):
        assert payload["dependencies"][name] == "ok"

    def broken_database():
        raise RuntimeError("database unavailable")

    degraded = obs.health_check(tmp_path, [], dependencies={
        "database": broken_database})
    assert degraded["running"] is True
    assert degraded["initialized"] is True
    assert degraded["ready"] is False
    assert degraded["status"] == "running"


# ---------------------------------------------------------------------------
# 4. Forensic retention: archive evidence, never delete it
# ---------------------------------------------------------------------------

def test_forensic_retention_archives_evidence_and_keeps_chain(tmp_path) -> None:
    for index in range(12):
        obs.record_event("stress", session_id="s", data={"i": index},
                         state_root=tmp_path, max_events=3, max_archives=2)

    cold_dir = tmp_path / (obs.LOG_FILENAME + obs.FORENSIC_DIR_SUFFIX)
    assert cold_dir.is_dir()
    report = obs.verify_forensic_archives(tmp_path)
    assert report["ok"] is True
    assert report["manifest_error"] is None
    assert report["archive_count"] >= 1
    for item in report["archives"]:
        assert item["ok"] is True
        archived = cold_dir / item["archive"]
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == item["sha256"]

    history = obs.read_forensic_archives(tmp_path)
    assert [event["seq"] for event in history] == list(
        range(1, len(history) + 1))
    hot = [path for path in tmp_path.glob(obs.LOG_FILENAME + ".*")
           if path.is_file() and path.name.rsplit(".", 1)[-1].isdigit()]
    assert 0 < len(hot) <= 2
    assert obs.verify_chain(tmp_path).ok is True

    # Tampering with cold evidence is detected without corrupting the hot log.
    victim = cold_dir / report["archives"][0]["archive"]
    victim.write_text(
        victim.read_text(encoding="utf-8").replace('"i":0', '"i":99', 1),
        encoding="utf-8")
    assert obs.verify_forensic_archives(tmp_path)["ok"] is False
    assert obs.verify_chain(tmp_path).ok is True
    with pytest.raises(obs.ChainIntegrityError):
        obs.read_forensic_archives(tmp_path)


def test_missing_retention_state_next_to_archives_fails_closed(tmp_path) -> None:
    for index in range(5):
        obs.record_event("stress", session_id="s", data={"i": index},
                         state_root=tmp_path, max_events=2, max_archives=1)
    assert list(tmp_path.glob(obs.LOG_FILENAME + ".*"))
    (tmp_path / obs.STATE_FILENAME).unlink()

    assert obs.verify_chain(tmp_path).ok is False
    with pytest.raises(obs.ChainIntegrityError):
        obs.record_event("after", session_id="s", state_root=tmp_path)


# ---------------------------------------------------------------------------
# 5. Redaction across events, audit, diagnostics and export
# ---------------------------------------------------------------------------

def test_secrets_are_absent_from_events_audit_diagnostics_and_export(
        tmp_path) -> None:
    obs.record_event(
        "error", session_id="s", module="d3_backend",
        data={
            "message": f"api_key = '{MULTI_WORD_SECRET}'",
            "Authorization": BEARER_SECRET,
            "nested": {"secret": NESTED_SECRET},
        },
        state_root=tmp_path,
    )
    audit = obs.record_audit_event(
        "security.denied", actor="operator", outcome="denied",
        detail=f"token: {BEARER_SECRET}", state_root=tmp_path,
    )
    assert audit["kind"] == obs.AUDIT_KIND

    _assert_no_secrets((tmp_path / obs.LOG_FILENAME).read_text(encoding="utf-8"))
    _assert_no_secrets(obs.read_events(tmp_path))
    _assert_no_secrets(obs.diagnostic_report(tmp_path))
    health = obs.health_check(tmp_path, ["d3_backend"])
    _assert_no_secrets(health)
    _assert_no_secrets(obs.health_http_payload(tmp_path, ["d3_backend"]))

    export = obs.export_diagnostics(tmp_path, tmp_path / "bundle.json",
                                    modules=["d3_backend"])
    _assert_no_secrets(export.read_text(encoding="utf-8"))
    assert obs.verify_chain(tmp_path).ok is True
