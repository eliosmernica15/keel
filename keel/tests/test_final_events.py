"""Final integration evidence: the durable event bus in real code paths.

These tests exercise real workflows, real durable logs, real subprocesses and
real permission checks. They pin the boundary as well as the integration:

* backend workflow / lifecycle / provider / security decisions publish typed
  complementary events through ``backend_events.EventBus``;
* audit records and permission/approval checks remain the only authorization
  authority -- events are never read back to grant access;
* fleet SSE fan-out and automation anomaly scoring keep their own authoritative
  event mechanisms;
* published strings are redacted, IDs are idempotent, the hot log is bounded
  with MAC-verified forensic archives, and records stay authentic across
  processes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from keel import automation  # noqa: E402
from keel import backend_events as be  # noqa: E402
from keel import backend_workflows as wf  # noqa: E402
from keel import capabilities  # noqa: E402
from keel import permissions  # noqa: E402
from keel import settings  # noqa: E402

MULTI_WORD_SECRET = "harbor lantern amber delta"
BEARER_SECRET = "Bearer sk-abcdefghijklmnopqrstuv"
NESTED_SECRET = "vault melon orbit seven"


def _assert_no_secrets(node: object) -> None:
    dumped = json.dumps(node, default=str)
    for secret in (MULTI_WORD_SECRET, BEARER_SECRET,
                   BEARER_SECRET.split(None, 1)[1], NESTED_SECRET):
        assert secret not in dumped


def _bus(root: Path, **kwargs: object) -> be.EventBus:
    return be.EventBus(root, **kwargs)


def _kinds(events: tuple[be.BackendEvent, ...]) -> list[str]:
    return [event.KIND for event in events]


# ---------------------------------------------------------------------------
# 1. A real workflow publishes typed events and keeps audit authoritative
# ---------------------------------------------------------------------------


def test_real_workflow_emits_typed_events_through_event_bus(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "default_state_root", lambda: tmp_path)
    note = tmp_path / "runbook.md"
    note.write_text("deployment runbook recovery marker", encoding="utf-8")
    params = {
        "state_root": str(tmp_path), "project_root": str(tmp_path),
        "file_path": str(note), "query": "runbook", "prompt": "read the runbook",
        "idempotency_key": "final-events-demo",
    }

    result = wf.run_workflow("request", params)
    assert result["ok"] is True, result

    events = _bus(tmp_path).replay()
    kinds = _kinds(events)
    assert "session_started" in kinds
    assert "permission_decided" in kinds
    assert "job_completed" in kinds
    assert len({event.event_id for event in events}) == len(events)
    correlations = {value for event in events
                    for key, value in event.metadata if key == "correlation_id"}
    assert result["idempotency_key"] in correlations

    # The pre-existing capability audit is still the authoritative record.
    audit = (tmp_path / "capability-audit.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in audit.splitlines() if line.strip()]
    assert any(row.get("capability") == "backend.workflow" and row.get("ok") is True
               for row in rows)


def test_approval_lifecycle_emits_typed_events(tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "default_state_root", lambda: tmp_path)
    result = wf.run_approval_workflow({
        "state_root": str(tmp_path), "operation": "fs_read",
        "subject": "final-events", "profile": "no_network",
    })
    assert result["ok"] is True, result
    kinds = _kinds(_bus(tmp_path).replay())
    assert {"approval_requested", "approval_consumed",
            "approval_revoked"}.issubset(set(kinds))


# ---------------------------------------------------------------------------
# 2. Denial emits a redacted failure event, never a privileged allow
# ---------------------------------------------------------------------------


def test_denied_workflow_emits_redacted_failure_event(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "default_state_root", lambda: tmp_path)

    import keel.policy_enforcement as policy

    def explode(*args: object, **kwargs: object):
        raise RuntimeError(
            f"policy refused: api_key = '{MULTI_WORD_SECRET}'; "
            f"Authorization: {BEARER_SECRET}; password = {NESTED_SECRET}")

    monkeypatch.setattr(policy, "enforce_workflow", explode)
    result = wf.run_workflow("request", {"state_root": str(tmp_path)})
    assert result["ok"] is False

    failures = [event for event in _bus(tmp_path).replay()
                if event.KIND == "error_recorded"]
    assert failures, "a denied workflow must emit a typed failure event"
    assert failures[-1].severity in {"error", "denied"}
    _assert_no_secrets([event.to_dict() for event in failures])
    _assert_no_secrets((tmp_path / "backend-events.jsonl").read_text(
        encoding="utf-8"))
    _assert_no_secrets((tmp_path / "capability-audit.jsonl").read_text(
        encoding="utf-8"))


def test_events_cannot_widen_a_permission_or_capability_denial(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "default_state_root", lambda: tmp_path)
    # A crafted durable event claiming an allow must not become input to a
    # permission decision.
    assert _bus(tmp_path).publish(be.PermissionDecided(
        event_id="forged-allow", session_id="s", tool_use_id="wf-tool-1",
        decision="allow", reason="event says so")) is True

    note = tmp_path / "secret.md"
    note.write_text("sensitive runbook", encoding="utf-8")
    result = wf.run_request_workflow({
        "state_root": str(tmp_path), "project_root": str(tmp_path),
        "file_path": str(note), "query": "sensitive",
        "deny_rules": ["read_file"], "idempotency_key": "deny-stays-denied",
    })
    assert result["ok"] is False
    assert result["code"] == "permission_denied"

    with pytest.raises(capabilities.CapabilityError) as exc:
        capabilities.invoke("backend.invoke", {}, allowed_permissions=set())
    assert exc.value.code == "permission_denied"

    # Neither decision path consumes the event stream.
    perm_source = (SRC / "keel" / "permissions.py").read_text(encoding="utf-8")
    workflow_source = (SRC / "keel" / "backend_workflows.py").read_text(
        encoding="utf-8")
    assert "publish_durable" not in perm_source
    assert ".replay(" not in perm_source
    assert "publish_durable" in workflow_source
    assert ".replay(" not in workflow_source


# ---------------------------------------------------------------------------
# 3. Cross-process authenticity, replay safety, bounded retention
# ---------------------------------------------------------------------------


_WORKER = r"""
import sys
sys.path.insert(0, sys.argv[1])
from keel.automation import publish_durable
root, index = sys.argv[2], sys.argv[3]
secret = 'api_key = \'harbor lantern amber delta\''
ok = publish_durable(root, 'error_recorded', event_id=f'cp-{index}',
                     error_id=f'cp-{index}', severity='error', message=secret,
                     metadata=[('correlation_id', f'corr-{index}')])
assert ok is True, index
"""


def test_cross_process_publishes_remain_authentic(tmp_path: Path) -> None:
    workers = 6
    results = [
        subprocess.run([sys.executable, "-c", _WORKER, str(SRC), str(tmp_path),
                        str(index)], capture_output=True, text=True, timeout=90)
        for index in range(workers)
    ]
    for result in results:
        assert result.returncode == 0, result.stderr

    bus = _bus(tmp_path)
    events = bus.replay()
    assert {event.event_id for event in events} == {
        f"cp-{index}" for index in range(workers)}
    assert [record["seq"] for record in bus._store.records] == list(
        range(1, workers + 1))
    key = be._existing_key(tmp_path)
    assert key is not None
    assert all(record["digest"] == be._record_digest(record, key)
               for record in bus._store.records)
    head = json.loads((tmp_path / "backend-events.jsonl.head").read_text(
        encoding="utf-8"))
    assert head["count"] == workers
    assert head["mac"] == be._head_mac(head, key)
    _assert_no_secrets((tmp_path / "backend-events.jsonl").read_text(
        encoding="utf-8"))
    _assert_no_secrets([event.to_dict() for event in events])


def test_replay_is_safe_and_conflicting_ids_are_rejected(tmp_path: Path) -> None:
    kwargs = dict(event_id="same-id", error_id="same-id", severity="error",
                  message="first")
    assert automation.publish_durable(
        tmp_path, "error_recorded", **kwargs) is True
    assert automation.publish_durable(
        tmp_path, "error_recorded", **kwargs) is False
    bus = _bus(tmp_path)
    assert [event.event_id for event in bus.replay()] == ["same-id"]
    with pytest.raises(be.DuplicateEventError):
        bus.publish(be.ErrorRecorded(event_id="same-id", error_id="other",
                                     message="second"))
    assert len(bus.replay()) == 1


def test_payload_redaction_covers_multi_word_secrets_bearers_and_credentials(
        tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    bus.publish(be.ErrorRecorded(
        event_id="redact-1", error_id="redact-1", severity="error",
        message=(f"api_key = '{MULTI_WORD_SECRET}'; Authorization: {BEARER_SECRET}; "
                 f"password = {NESTED_SECRET}"),
        metadata=[("prompt", f"the secret is {MULTI_WORD_SECRET}")]))
    events = bus.replay()
    assert len(events) == 1
    _assert_no_secrets([event.to_dict() for event in events])
    _assert_no_secrets((tmp_path / "backend-events.jsonl").read_text(
        encoding="utf-8"))
    # The clean envelope is what is durably indexed (idempotency still works).
    assert bus.publish(events[0]) is False


def test_bounded_retention_archives_records_without_losing_replay(
        tmp_path: Path) -> None:
    bus = _bus(tmp_path, max_events=3, max_archives=2)
    for index in range(10):
        assert bus.publish(be.SessionStarted(
            event_id=f"bounded-{index}", session_id="s")) is True

    fresh = _bus(tmp_path, max_events=3, max_archives=2)
    assert [event.event_id for event in fresh.replay()] == [
        f"bounded-{index}" for index in range(10)]
    assert len(fresh._store.records) <= 3
    assert fresh._store.archives
    assert len(fresh._store.archives) <= 2

    key = be._existing_key(tmp_path)
    assert key is not None
    assert all(record["digest"] == be._record_digest(record, key)
               for record in fresh._store.records)
    head = json.loads((tmp_path / "backend-events.jsonl.head").read_text(
        encoding="utf-8"))
    assert head["count"] == 10
    assert head["base"] == fresh._store.base_seq
    assert head["mac"] == be._head_mac(head, key)
    # A retired event ID is still reserved for duplicate suppression.
    assert fresh.publish(be.SessionStarted(
        event_id="bounded-0", session_id="s")) is False


# ---------------------------------------------------------------------------
# 4. Fleet automation keeps its own authoritative event mechanism
# ---------------------------------------------------------------------------


def test_fleet_keeps_its_authoritative_bus(tmp_path: Path) -> None:
    source = (SRC / "keel" / "fleet" / "service.py").read_text(encoding="utf-8")
    assert "publish_durable" not in source
    registry = (SRC / "keel" / "capability_registry.py").read_text(
        encoding="utf-8")
    assert "from .automation import EventBus" in registry
    bus = automation.EventBus(tmp_path)
    bus.publish("fleet.eventbus.publish", {"kind": "denied"})
    assert len(automation.EventBus(tmp_path).history) == 1


# ---------------------------------------------------------------------------
# 5. M-1: an empty ledger with a committed head must fail closed
# ---------------------------------------------------------------------------


def _seeded_ledger(root: Path) -> tuple[Path, str]:
    ledger = wf._result_path(root, "request")
    for index in range(3):
        wf._append_jsonl(ledger, {"workflow": "request", "ok": True,
                                  "code": "ok", "idempotency_key": f"seed-{index}"})
    head = wf._head_path(ledger)
    assert json.loads(head.read_text(encoding="utf-8"))["seq"] == 3
    return ledger, head.read_text(encoding="utf-8")


@pytest.mark.parametrize("replacement", ["", " \n\t\n"])
def test_empty_ledger_with_committed_head_fails_closed(
        tmp_path: Path, replacement: str) -> None:
    ledger, head_before = _seeded_ledger(tmp_path)
    ledger.write_text(replacement, encoding="utf-8")

    with pytest.raises(wf.WorkflowError) as read_error:
        wf._read_jsonl(ledger)
    assert read_error.value.code == "ledger_integrity"
    with pytest.raises(wf.WorkflowError) as append_error:
        wf._append_jsonl(ledger, {"workflow": "request", "code": "ok"})
    assert append_error.value.code == "ledger_integrity"

    # The attacker cannot launder the truncation with a subsequent append: the
    # file stays exactly as truncated and the committed head is untouched.
    assert ledger.read_text(encoding="utf-8") == replacement
    assert wf._head_path(ledger).read_text(encoding="utf-8") == head_before


def test_deleted_ledger_with_committed_head_fails_closed(tmp_path: Path) -> None:
    ledger, head_before = _seeded_ledger(tmp_path)
    ledger.unlink()
    with pytest.raises(wf.WorkflowError) as exc:
        wf._read_jsonl(ledger)
    assert exc.value.code == "ledger_integrity"
    with pytest.raises(wf.WorkflowError):
        wf._append_jsonl(ledger, {"workflow": "request", "code": "ok"})
    assert not ledger.exists()
    assert wf._head_path(ledger).read_text(encoding="utf-8") == head_before


def test_genuinely_new_ledger_still_starts_at_genesis(tmp_path: Path) -> None:
    ledger = wf._result_path(tmp_path, "request")
    assert not ledger.exists()
    assert not wf._head_path(ledger).exists()
    assert wf._read_jsonl(ledger) == []
    assert wf._append_jsonl(ledger, {"workflow": "request", "code": "ok"}) == 1
    assert json.loads(wf._head_path(ledger).read_text(
        encoding="utf-8"))["seq"] == 1


def test_workflow_result_cannot_launder_truncated_ledger(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "default_state_root", lambda: tmp_path)
    note = tmp_path / "note.md"
    note.write_text("marker", encoding="utf-8")
    base = {"state_root": str(tmp_path), "project_root": str(tmp_path),
            "file_path": str(note), "query": "marker"}
    for index in range(3):
        result = wf.run_request_workflow({**base, "idempotency_key": f"pre-{index}"})
        assert result["ok"] is True, result

    ledger = wf._result_path(tmp_path, "request")
    head_before = wf._head_path(ledger).read_text(encoding="utf-8")
    ledger.write_text(" \n", encoding="utf-8")
    blocked = wf.run_request_workflow({**base, "idempotency_key": "after-truncation"})
    assert blocked["ok"] is False
    assert blocked["code"] == "ledger_integrity"
    assert ledger.read_text(encoding="utf-8") == " \n"
    assert wf._head_path(ledger).read_text(encoding="utf-8") == head_before
