"""Independent EventBus / observability acceptance recheck (read-only audit).

This file is written by the final events recheck.  It does not change any
production module: every assertion drives the real code paths and reads the
real on-disk artefacts.  Its central purpose is to prove that the durable
``backend_events.EventBus`` is an *emit-only* evidence channel: even an
attacker who controls the HMAC key and writes perfectly authentic events
claiming "allow" cannot grant a permission, approve an action, or relax a
saved execution policy.

The exact probe transcript produced by
``test_authorization_independence_forged_event_probe`` is reproduced in
``FINAL-EVENTS-RECHECK.md`` at the repository root.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from keel import automation  # noqa: E402
from keel import backend_events as be  # noqa: E402
from keel import backend_observability as obs  # noqa: E402
from keel import backend_workflows as wf  # noqa: E402
from keel import capabilities  # noqa: E402
from keel import diagnostics  # noqa: E402
from keel import permissions  # noqa: E402
from keel import policy_enforcement  # noqa: E402
from keel import settings  # noqa: E402
from keel.exec_policy import ExecPolicyStore  # noqa: E402

ATTACKER_KEY = "attacker-controlled-key-0123456789"
SECRET = "harbor lantern amber delta"
BEARER = "Bearer sk-abcdefghijklmnopqrstuv"


def _wire_state(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setenv("KEEL_STATE_DIR", str(root))
    monkeypatch.setattr(settings, "default_state_root", lambda: root)


def _bus(root: Path, **kwargs: object) -> be.EventBus:
    return be.EventBus(root, **kwargs)


def _chain_ok(root: Path) -> bool:
    """Independently verify every record and the commit head under the real key."""
    key = be._existing_key(root)
    if key is None:
        return False
    bus = _bus(root)
    if not all(record["digest"] == be._record_digest(record, key)
               for record in bus._store.records):
        return False
    head = json.loads((root / "backend-events.jsonl.head").read_text(encoding="utf-8"))
    return head["mac"] == be._head_mac(head, key)


def _result_code(result: dict) -> str:
    return "ok" if result.get("ok") else str(result.get("code"))


def _request_params(root: Path, *, key: str, providers: object = None) -> dict:
    note = root / "probe-note.md"
    note.write_text("forensic marker", encoding="utf-8")
    params = {
        "state_root": str(root), "project_root": str(root),
        "file_path": str(note), "query": "marker", "prompt": "read the marker",
        "idempotency_key": key,
    }
    if providers is not None:
        params["providers"] = providers
    return params


# ---------------------------------------------------------------------------
# 1. Authoritative publisher for the five evidence domains
# ---------------------------------------------------------------------------


def test_eventbus_is_authoritative_publisher_for_all_domains(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_state(monkeypatch, tmp_path)

    ok = wf.run_workflow("request", _request_params(tmp_path, key="domains-ok"))
    assert ok["ok"] is True, ok
    denied = wf.run_request_workflow({
        **_request_params(tmp_path, key="domains-deny"),
        "deny_rules": ["read_file"],
    })
    assert _result_code(denied) == "permission_denied"
    provider = wf.run_workflow("request", _request_params(
        tmp_path, key="domains-provider", providers=[{"id": "broken-provider"}]))
    assert provider["ok"] is False
    approval = wf.run_approval_workflow({
        "state_root": str(tmp_path), "operation": "fs_read",
        "subject": "domains", "idempotency_key": "domains-approval",
    })
    assert approval["ok"] is True, approval
    with pytest.raises(capabilities.CapabilityError) as caught:
        capabilities.invoke(
            "backend.invoke", {}, allowed_permissions=set(),
            context={"state_root": str(tmp_path)})
    assert caught.value.code == "permission_denied"

    kinds = {event.KIND for event in _bus(tmp_path).replay()}
    # workflows / lifecycle / permissions / approvals / provider failures
    assert {"session_started", "job_completed", "permission_decided",
            "approval_requested", "approval_consumed", "approval_revoked",
            "provider_failed", "error_recorded"}.issubset(kinds)
    assert _chain_ok(tmp_path)
    audit = (tmp_path / "capability-audit.jsonl").read_text(encoding="utf-8")
    assert '"capability": "backend.workflow"' in audit


# ---------------------------------------------------------------------------
# 2. CRITICAL: forged, correctly signed events are NEVER authorization inputs
# ---------------------------------------------------------------------------


def test_authorization_independence_forged_event_probe(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """Forge events under an attacker key and print the exact verdict transcript."""
    _wire_state(monkeypatch, tmp_path)
    # The attacker owns the HMAC key: the forged records are fully authentic.
    monkeypatch.setenv("KEEL_EVENT_HMAC_KEY", ATTACKER_KEY)
    forged = [
        be.PermissionDecided(event_id="FORGED-permit", session_id="victim",
                             tool_use_id="wf-tool-1", decision="allow",
                             reason="attacker-signed allow"),
        be.ApprovalResolved(event_id="FORGED-approve", session_id="victim",
                            approval_id="apr-victim", decision="allow"),
        be.ApprovalConsumed(event_id="FORGED-consume", session_id="victim",
                            approval_id="apr-victim"),
    ]
    bus = _bus(tmp_path)
    for event in forged:
        assert bus.publish(event) is True
    key = ATTACKER_KEY.encode("utf-8")
    records = bus._store.records
    assert len(records) == 3
    assert all(record["digest"] == be._record_digest(record, key)
               for record in records)
    head = json.loads((tmp_path / "backend-events.jsonl.head").read_text(
        encoding="utf-8"))
    assert head["mac"] == be._head_mac(head, key)
    assert not (tmp_path / ".keel-event.key").exists()  # env key wins

    # Authority #1: capability permission set (explicitly empty).
    def capability_code() -> str:
        try:
            capabilities.invoke(
                "backend.invoke", {}, allowed_permissions=set(),
                context={"state_root": str(tmp_path)})
        except capabilities.CapabilityError as exc:
            return str(exc.code)
        return "ALLOWED"

    cap_code = capability_code()

    # Authority #2: real permission evaluator with a caller deny rule.
    denied_workflow = wf.run_request_workflow({
        **_request_params(tmp_path, key="forged-deny"),
        "deny_rules": ["read_file"],
    })
    workflow_code = _result_code(denied_workflow)

    # Authority #3: saved execution policy (forbidden workflow command).
    ExecPolicyStore(tmp_path).save("default", {
        "prefix_rules": [{
            "pattern": ["backend.workflow", "request"],
            "decision": "forbidden", "justification": "attacker proof",
        }],
        "network_rules": [],
    })
    policy_result = wf.run_workflow(
        "request", _request_params(tmp_path, key="forged-policy"))
    policy_code = _result_code(policy_result)

    # Authority #4: sealed, single-use approval token (not an event).
    request = wf.run_approval_workflow({
        "state_root": str(tmp_path), "action": "request",
        "operation": "fs_read", "subject": "victim",
        "request_id": "apr-victim", "idempotency_key": "forged-apr-request",
    })
    token = request["result"]["token"]
    no_token = wf.run_approval_workflow({
        "state_root": str(tmp_path), "action": "resolve",
        "request_id": "apr-victim", "idempotency_key": "forged-apr-notoken",
    })
    bogus = wf.run_approval_workflow({
        "state_root": str(tmp_path), "action": "resolve",
        "request_id": "apr-victim", "token": "FORGED-approve",
        "idempotency_key": "forged-apr-bogus",
    })
    genuine = wf.run_approval_workflow({
        "state_root": str(tmp_path), "action": "resolve",
        "request_id": "apr-victim", "token": token,
        "idempotency_key": "forged-apr-genuine",
    })
    replay = wf.run_approval_workflow({
        "state_root": str(tmp_path), "action": "resolve",
        "request_id": "apr-victim", "token": token,
        "idempotency_key": "forged-apr-replay",
    })
    forged_consume_in_ledger = sum(
        1 for row in wf._read_jsonl(wf._approval_events_path(tmp_path))
        if row.get("request_id") == "apr-victim" and row.get("action") == "consume")

    lines = [
        "=== AUTHORIZATION-INDEPENDENCE PROBE (exec-events recheck) ===",
        "forge: 3 events published with attacker-controlled KEEL_EVENT_HMAC_KEY",
        "  PermissionDecided(decision=allow) HMAC-valid=True",
        "  ApprovalResolved(decision=allow) HMAC-valid=True",
        "  ApprovalConsumed(approval_id=apr-victim) HMAC-valid=True",
        "  commit head MAC valid under attacker key=True; key file created=False",
        "outcomes (all decisions made without reading the event stream):",
        f"  capabilities.invoke(allowed_permissions=set()) -> {cap_code}",
        f"  workflow request with deny_rules=[read_file] -> {workflow_code}",
        f"  saved policy forbids backend.workflow request -> {policy_code}",
        f"  approval resolve, forged allow events, no token -> {_result_code(no_token)}",
        f"  approval resolve, forged allow events, bogus token -> {_result_code(bogus)}",
        (f"  forged approval_consumed event -> consume records in approval ledger: "
         f"{forged_consume_in_ledger}"),
        f"  approval resolve with genuine sealed token -> {_result_code(genuine)}",
        f"  replay after genuine consume -> {_result_code(replay)}",
        "VERDICT: forged events granted no permission, no approval, no policy bypass.",
    ]
    print("\n".join(lines))
    assert cap_code == "permission_denied"
    assert workflow_code == "permission_denied"
    assert policy_code == "policy_denied"
    assert _result_code(no_token) == "missing_token"
    assert _result_code(bogus) == "invalid_token"
    assert forged_consume_in_ledger == 1  # only the genuine resolve consumed it
    assert _result_code(genuine) == "ok"
    assert _result_code(replay) == "replay_denied"
    assert capsys.readouterr().out.count("VERDICT:") == 1


def test_forged_events_do_not_create_an_approval_request(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_state(monkeypatch, tmp_path)
    monkeypatch.setenv("KEEL_EVENT_HMAC_KEY", ATTACKER_KEY)
    assert _bus(tmp_path).publish(be.ApprovalRequested(
        event_id="FORGED-request", session_id="victim",
        approval_id="apr-ghost", tool_use_id="approval",
        prompt="attacker says approved"))
    result = wf.run_approval_workflow({
        "state_root": str(tmp_path), "action": "resolve",
        "request_id": "apr-ghost", "token": "FORGED-request",
        "idempotency_key": "ghost-resolve",
    })
    assert _result_code(result) == "unknown_request"
    assert wf._approval_events(tmp_path, "apr-ghost") == []


def test_authorization_modules_never_read_the_event_stream() -> None:
    """Source-level proof of the emit-only boundary in every decision module."""
    names = ("permissions.py", "capabilities.py", "policy_enforcement.py",
             "backend_workflows.py", "e6_x5_x6_backend.py")
    roots = SRC / "keel"
    for name in names:
        source = (roots / name).read_text(encoding="utf-8")
        for banned in ("from .backend_events", "import backend_events",
                       "event_from_dict(", ".replay(", "EventBus("):
            assert banned not in source, f"{name} contains {banned!r}"
    for name in ("permissions.py", "policy_enforcement.py", "e6_x5_x6_backend.py"):
        assert "publish_durable" not in (roots / name).read_text(encoding="utf-8")


def test_event_publication_failure_never_changes_a_decision(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_state(monkeypatch, tmp_path)

    def unusable(*args: object, **kwargs: object) -> bool:
        raise RuntimeError(f"emit unavailable: api_key = {SECRET}")

    monkeypatch.setattr(automation, "publish_durable", unusable)
    denied = wf.run_request_workflow({
        **_request_params(tmp_path, key="emit-fail-deny"),
        "deny_rules": ["read_file"],
    })
    assert _result_code(denied) == "permission_denied"
    assert SECRET not in json.dumps(denied, default=str)
    assert any(step.get("step") == "event_emit_failed"
               for step in denied["steps"])
    ok = wf.run_workflow("request", _request_params(tmp_path, key="emit-fail-ok"))
    assert ok["ok"] is True
    with pytest.raises(capabilities.CapabilityError) as caught:
        capabilities.invoke(
            "backend.invoke", {}, allowed_permissions=set(),
            context={"state_root": str(tmp_path)})
    assert caught.value.code == "permission_denied"


# ---------------------------------------------------------------------------
# 3. HMAC authenticity, key management, redaction, retention, recovery
# ---------------------------------------------------------------------------


def test_hmac_key_management_and_tamper_detection(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    assert bus.publish(be.SessionStarted(event_id="hmac-1", session_id="s"))
    key_path = tmp_path / ".keel-event.key"
    assert key_path.is_file() and key_path.stat().st_size >= 16
    # Windows does not expose POSIX mode bits; os.open/chmod request 0600 in
    # backend_events._event_key.  No secret is ever written into the log.
    mode = stat.S_IMODE(key_path.stat().st_mode)
    if os.name == "posix":
        assert mode == 0o600
    else:
        assert mode in (0o600, 0o444, 0o666)
    assert _chain_ok(tmp_path)
    log = tmp_path / "backend-events.jsonl"

    # Field edit breaks the keyed chain even when the head is left untouched.
    log.write_text(log.read_text(encoding="utf-8").replace('"s"', '"attacker"', 1),
                   encoding="utf-8")
    with pytest.raises(be.CorruptRecordError):
        _bus(tmp_path)
    # Re-append with a recomputed *unkeyed* digest under the real key: rejected.
    log.write_text(json.dumps({
        "seq": 1, "prev": be.GENESIS_DIGEST,
        "data": {"event": be.SessionStarted(
            event_id="hmac-1", session_id="s").to_dict()},
        "digest": be._record_digest({"seq": 1, "prev": be.GENESIS_DIGEST,
                                     "data": {"event": be.SessionStarted(
                                         event_id="hmac-1", session_id="s").to_dict()}}),
    }, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(be.CorruptRecordError, match="HMAC mismatch"):
        _bus(tmp_path)


def test_env_key_override_is_used_and_no_key_file_is_written(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEEL_EVENT_HMAC_KEY", ATTACKER_KEY)
    assert _bus(tmp_path).publish(
        be.SessionStarted(event_id="env-key-1", session_id="s"))
    assert not (tmp_path / ".keel-event.key").exists()
    record = _bus(tmp_path)._store.records[0]
    assert record["digest"] == be._record_digest(
        record, ATTACKER_KEY.encode("utf-8"))
    assert _chain_ok(tmp_path)


def test_redaction_happens_at_publisher_boundary(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    bus.publish(be.ErrorRecorded(
        event_id="redact-probe", error_id="redact-probe", severity="error",
        message=f"api_key = '{SECRET}'; Authorization: {BEARER}",
        metadata=[("prompt", f"the secret is {SECRET}")]))
    replayed = bus.replay()
    assert len(replayed) == 1
    for secret in (SECRET, BEARER, BEARER.split(None, 1)[1]):
        assert secret not in json.dumps([e.to_dict() for e in replayed])
        assert secret not in (tmp_path / "backend-events.jsonl").read_text(
            encoding="utf-8")
    assert bus.publish(replayed[0]) is False  # redacted envelope is canonical


def test_bounded_merged_archives_preserve_all_evidence(tmp_path: Path) -> None:
    bus = _bus(tmp_path, max_events=3, max_archives=2)
    for index in range(12):
        assert bus.publish(be.SessionStarted(
            event_id=f"bounded-{index:02d}", session_id="s")) is True
    fresh = _bus(tmp_path, max_events=3, max_archives=2)
    assert [event.event_id for event in fresh.replay()] == [
        f"bounded-{index:02d}" for index in range(12)]
    assert len(fresh._store.records) <= 3
    assert 0 < len(fresh._store.archives) <= 2
    archive_dir = tmp_path / "backend-events.jsonl.forensic"
    merged = sorted(path.name for path in archive_dir.glob("events-*.jsonl"))
    assert merged  # records were merged, never silently deleted
    manifest = json.loads((archive_dir / "manifest.json").read_text(
        encoding="utf-8"))
    assert manifest["mac"] == __import__("hmac").new(
        be._existing_key(tmp_path),
        be._canonical_bytes({"archives": manifest["archives"]}),
        "sha256").hexdigest()
    assert _chain_ok(tmp_path)
    assert fresh.publish(be.SessionStarted(
        event_id="bounded-00", session_id="s")) is False  # retired ID reserved

    victim = archive_dir / merged[0]
    victim.write_text(victim.read_text(encoding="utf-8").replace(
        '"session_id":"s"', '"session_id":"evil"', 1), encoding="utf-8")
    with pytest.raises(be.CorruptRecordError):
        _bus(tmp_path, max_events=3, max_archives=2)


_WORKER = r"""
import sys
sys.path.insert(0, sys.argv[1])
from keel.backend_events import EventBus, SessionStarted
root, index = sys.argv[2], sys.argv[3]
assert EventBus(root).publish(SessionStarted(
    event_id=f"cp-{index}", session_id=f"s-{index}")) is True
"""


def test_cross_process_append_is_atomic_and_authentic(tmp_path: Path) -> None:
    workers = 5
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(
            lambda index: subprocess.run(
                [sys.executable, "-c", _WORKER, str(SRC), str(tmp_path), str(index)],
                capture_output=True, text=True, timeout=90),
            range(workers)))
    for result in results:
        assert result.returncode == 0, result.stderr
    bus = _bus(tmp_path)
    assert [record["seq"] for record in bus._store.records] == list(
        range(1, workers + 1))
    assert {event.event_id for event in bus.replay()} == {
        f"cp-{index}" for index in range(workers)}
    assert _chain_ok(tmp_path)
    assert bus.last_recovery is None


def test_corruption_recovery_is_typed_and_fail_closed(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    assert bus.publish(be.SessionStarted(event_id="rec-1", session_id="s"))
    log = tmp_path / "backend-events.jsonl"
    with log.open("ab") as handle:
        handle.write(b'{"seq":2,"prev":')  # torn tail
    reopened = _bus(tmp_path)
    assert reopened.last_recovery is not None
    assert reopened.last_recovery.action == "truncated_tail"
    assert len(reopened.replay()) == 1
    assert _chain_ok(tmp_path)

    # Crash after fsync, before head commit: verified tail rolled forward.
    stale_head = tmp_path / "backend-events.jsonl.head"
    be._write_head(stale_head, 0, be.GENESIS_DIGEST, reopened._store.key)
    again = _bus(tmp_path)
    assert again.last_recovery is not None
    assert again.last_recovery.action == "committed_tail"
    assert len(again.replay()) == 1
    assert json.loads(stale_head.read_text(encoding="utf-8"))["count"] == 1
    assert _chain_ok(tmp_path)


# ---------------------------------------------------------------------------
# 4. Truthful readiness, redacted diagnostics, no external monitoring
# ---------------------------------------------------------------------------


def test_readiness_distinguishes_liveness_initialization_and_dependencies(
        tmp_path: Path) -> None:
    live = obs.liveness_probe()
    assert live["status"] == "running" and live["alive"] is True
    fresh = obs.health_check(tmp_path, [])
    assert fresh["running"] is True and fresh["ready"] is True
    assert fresh["initialized"] is False
    obs.record_event("workflow.start", session_id="s", state_root=tmp_path)
    assert obs.health_check(tmp_path, [])["initialized"] is True

    def broken_provider() -> bool:
        raise RuntimeError(f"Authorization: {BEARER}")

    degraded = obs.health_check(tmp_path, [], dependencies={
        "provider": broken_provider})
    assert degraded["running"] is True       # liveness still truthful
    assert degraded["ready"] is False        # readiness honestly refused
    assert degraded["status"] == "running"
    assert degraded["readiness"]["checks"]["dependencies_ok"] is False
    assert BEARER not in json.dumps(degraded, default=str)
    without_probes = obs.dependency_health({})
    assert without_probes["healthy"] is False
    assert obs.health_check(tmp_path, dependencies={})["ready"] is False


def test_observability_retention_redaction_and_no_external_dependency(
        tmp_path: Path) -> None:
    for index in range(12):
        obs.record_event("stress", session_id="s",
                         data={"i": index, "token": BEARER},
                         state_root=tmp_path, max_events=3, max_archives=2)
    assert obs.verify_chain(tmp_path).ok is True
    history = (obs.read_forensic_archives(tmp_path)
               + obs.read_events(tmp_path, include_archives=True))
    assert len(history) == 12
    assert [event["seq"] for event in history] == list(range(1, 13))
    assert BEARER not in json.dumps(history)
    report = obs.diagnostic_report(tmp_path)
    assert report["retention"]["archive_count"] <= 2
    assert BEARER not in json.dumps(report)
    bundle = obs.export_diagnostics(tmp_path, tmp_path / "bundle.json")
    assert BEARER not in bundle.read_text(encoding="utf-8")
    collected = diagnostics.collect()
    assert BEARER not in json.dumps(collected, default=str)
    sources = (Path(obs.__file__).read_text(encoding="utf-8")
               + Path(diagnostics.__file__).read_text(encoding="utf-8")).lower()
    for banned in ("prometheus", "opentelemetry", "datadog", "sentry",
                   "statsd", "requests.post", "urllib.request"):
        assert banned not in sources
