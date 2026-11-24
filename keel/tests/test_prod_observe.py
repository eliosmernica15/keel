"""Production-hardening acceptance tests for backend observability.

These tests exercise the real JSONL event log, the real on-disk lock, real
subprocesses and real threads.  No internal function is replaced except the
single import failure injection used to prove that an exception carrying a
credential is redacted before it reaches a diagnostic/HTTP response.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from keel import backend_observability as obs

SRC = Path(__file__).resolve().parents[1] / "src"

MULTI_WORD_SECRET = "trident lunar velvet compass"
BEARER_SECRET = "Bearer abcdef1234567890XYZ"
NESTED_SECRET = "salted caramel universe seven"


def _log(root: Path) -> Path:
    return root / obs.LOG_FILENAME


def _assert_no_secrets(value: object) -> None:
    dumped = json.dumps(value, default=str)
    for secret in (MULTI_WORD_SECRET, BEARER_SECRET.split(None, 1)[1],
                   BEARER_SECRET, NESTED_SECRET):
        assert secret not in dumped


# ---------------------------------------------------------------------------
# Health: running (alive) is not ready (fully operational)
# ---------------------------------------------------------------------------

def test_health_check_distinguishes_running_from_ready(tmp_path):
    live = obs.liveness_probe()
    assert live["status"] == "running"
    assert live["alive"] is True

    ready = obs.health_check(tmp_path, [])
    assert ready["running"] is True
    assert ready["ready"] is True
    assert ready["status"] == "ready"

    def broken_database():
        raise RuntimeError("database unavailable")

    degraded = obs.health_check(
        tmp_path,
        ["no_such_backend_module_for_prod_observe"],
        dependencies={"database": broken_database},
    )
    assert degraded["running"] is True          # still alive
    assert degraded["ready"] is False           # not ready
    assert degraded["status"] == "running"      # the distinction under test
    assert degraded["readiness"]["checks"]["modules_ok"] is False
    assert degraded["readiness"]["checks"]["dependencies_ok"] is False
    assert degraded["readiness"]["chain_status"] == "ok"
    assert degraded["liveness"]["status"] == "running"


def test_readiness_tracks_corrupt_event_chain(tmp_path):
    obs.record_event("workflow.start", session_id="s", state_root=tmp_path)
    path = _log(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace('"seq":1', '"seq":9'),
                    encoding="utf-8")

    check = obs.health_check(tmp_path, [])
    assert check["running"] is True
    assert check["ready"] is False
    assert check["status"] == "running"
    assert check["readiness"]["checks"]["chain_ok"] is False
    assert check["readiness"]["chain_status"] == "corrupt"


# ---------------------------------------------------------------------------
# Secret hygiene across exceptions, responses, events, logs, audit, exports
# ---------------------------------------------------------------------------

def test_no_secrets_in_http_response_exceptions_logs_events_and_audit(
    tmp_path, monkeypatch,
):
    obs.record_event(
        "error",
        session_id="s",
        module="d3_backend",
        data={
            "message": f"api_key = '{MULTI_WORD_SECRET}'",
            "Authorization": BEARER_SECRET,
            "note": f"secret = {NESTED_SECRET}",
        },
        state_root=tmp_path,
    )
    audit = obs.record_audit_event(
        "provider.call",
        actor="operator-7",
        outcome="denied",
        request_id="request-42",
        detail=f"token: {BEARER_SECRET}",
        state_root=tmp_path,
    )
    assert audit["kind"] == obs.AUDIT_KIND
    assert audit["data"]["request_id"] == "request-42"

    # A real import failure whose message carries a credential must be
    # redacted before it reaches a snapshot or an HTTP body.
    def failing_import(name):
        return None, f"RuntimeError: api_key = '{MULTI_WORD_SECRET}'"

    monkeypatch.setattr(obs, "_import_module", failing_import)
    snapshot = obs.health_snapshot(tmp_path, ["sensitive_backend"])
    assert MULTI_WORD_SECRET not in json.dumps(snapshot)
    error_text = snapshot["modules"]["sensitive_backend"]["import_error"]
    assert "[REDACTED]" in error_text
    assert MULTI_WORD_SECRET not in error_text

    payload = obs.health_http_payload(tmp_path, ["sensitive_backend"])
    _assert_no_secrets(payload)
    assert payload["status"] in {"ready", "running"}
    assert "import_error" not in payload

    # The persisted bytes themselves are free of every credential.
    raw = _log(tmp_path).read_text(encoding="utf-8")
    for secret in (MULTI_WORD_SECRET, BEARER_SECRET, BEARER_SECRET.split(None, 1)[1],
                   NESTED_SECRET):
        assert secret not in raw

    events = obs.read_events(tmp_path)
    _assert_no_secrets(events)
    _assert_no_secrets(obs.diagnostic_report(tmp_path))
    _assert_no_secrets(obs.health_check(tmp_path, ["sensitive_backend"]))
    _assert_no_secrets(obs.export_diagnostics(tmp_path, tmp_path / "bundle.json"))

    # Storage errors embed caller-controlled paths; those are redacted too.
    blocker = tmp_path / f"blocker api_key = {MULTI_WORD_SECRET}"
    blocker.write_text("occupied", encoding="utf-8")
    with pytest.raises(obs.ObservabilityStorageError) as caught:
        obs.record_event("error", session_id="s", state_root=blocker / "state")
    assert MULTI_WORD_SECRET not in str(caught.value)


def test_redaction_of_multi_word_secret_and_bearer_token(tmp_path):
    event = {
        "data": {
            "note": f"api_key = '{MULTI_WORD_SECRET}'",
            "Authorization": BEARER_SECRET,
            "api_key": NESTED_SECRET,
            "nested": [{"token": BEARER_SECRET}, {"safe": "ordinary text"}],
        },
    }
    safe = obs.redact(event)
    assert event["data"]["note"] == f"api_key = '{MULTI_WORD_SECRET}'"
    _assert_no_secrets(safe)
    assert safe["data"]["nested"][1]["safe"] == "ordinary text"

    stored = obs.record_event(
        "provider.error",
        session_id="s",
        data=event["data"],
        state_root=tmp_path,
    )
    _assert_no_secrets(stored)
    _assert_no_secrets(_log(tmp_path).read_text(encoding="utf-8"))
    assert obs.verify_chain(tmp_path).ok is True


def test_dependency_health_db_provider_worker_and_error_redaction(tmp_path):
    deps = obs.dependency_health(obs.default_dependency_probes(tmp_path))
    assert deps["healthy"] is True
    for name in ("database", "provider", "worker", "event_log"):
        assert deps["dependencies"][name]["status"] == "ok"
        assert deps["dependencies"][name]["duration_ms"] >= 0

    def broken_provider():
        raise RuntimeError(f"Authorization: {BEARER_SECRET}")

    bad = obs.dependency_health({"provider": broken_provider})
    assert bad["healthy"] is False
    assert bad["dependencies"]["provider"]["status"] == "error"
    _assert_no_secrets(bad)


def test_error_categories_and_resource_metrics(tmp_path):
    obs.record_event("error", session_id="s", data={"error_category": "provider"},
                     state_root=tmp_path)
    obs.record_event("error", session_id="s", data={"category": "database"},
                     state_root=tmp_path)
    obs.record_audit_event("config.change", actor="admin", state_root=tmp_path)

    metrics = obs.metrics_snapshot(tmp_path)
    assert metrics["chain_status"] == "ok"
    assert metrics["error_count"] == 2
    assert metrics["audit_count"] == 1
    assert metrics["error_categories"] == {"database": 1, "provider": 1}
    assert metrics["resources"]["thread_count"] >= 1
    assert metrics["resources"]["max_rss_kb"] is None or \
        metrics["resources"]["max_rss_kb"] >= 0


# ---------------------------------------------------------------------------
# Bounded retention and log rotation
# ---------------------------------------------------------------------------

def test_bounded_retention_rotates_and_preserves_chain(tmp_path):
    for index in range(20):
        obs.record_event(
            "stress", session_id="s", task_id=f"task-{index}", data={"i": index},
            state_root=tmp_path, max_events=5, max_archives=2,
        )

    assert len(_log(tmp_path).read_text(encoding="utf-8").splitlines()) <= 5
    archives = [name for name in os.listdir(tmp_path)
                if name.startswith(obs.LOG_FILENAME + ".") and name.split(".")[-1].isdigit()]
    assert 0 < len(archives) <= 2

    verified = obs.verify_chain(tmp_path)
    assert verified.ok is True
    history = obs.read_events(tmp_path, include_archives=True)
    assert len(history) <= 5 * (2 + 1)
    assert [event["seq"] for event in history] == list(range(history[0]["seq"],
                                                            history[0]["seq"] + len(history)))
    report = obs.diagnostic_report(tmp_path)
    assert report["retention"]["archive_count"] <= 2
    assert report["retention"]["generation"] > 1

    # A rotated log continues the global sequence without a chain break.
    appended = obs.record_event(
        "after-rotation", session_id="s", state_root=tmp_path,
        max_events=5, max_archives=2,
    )
    assert appended["seq"] == history[-1]["seq"] + 1
    assert appended["prev_hash"] == history[-1]["hash"]
    assert obs.verify_chain(tmp_path).ok is True


def test_corruption_in_archive_fails_closed(tmp_path):
    for index in range(12):
        obs.record_event("stress", session_id="s", data={"i": index},
                         state_root=tmp_path, max_events=5, max_archives=2)
    archive = tmp_path / f"{obs.LOG_FILENAME}.2"
    assert archive.is_file()
    lines = [line for line in archive.read_text(encoding="utf-8").splitlines() if line.strip()]
    damaged = json.loads(lines[-1])
    damaged["data"]["i"] = 999
    lines[-1] = json.dumps(damaged, sort_keys=True, separators=(",", ":"))
    archive.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert obs.verify_chain(tmp_path).ok is False
    with pytest.raises(obs.ChainIntegrityError):
        obs.read_events(tmp_path, include_archives=True)
    with pytest.raises(obs.ChainIntegrityError):
        obs.record_event("should-be-refused", session_id="s", state_root=tmp_path,
                         max_events=5, max_archives=2)
    assert obs.diagnostic_report(tmp_path)["chain_status"] == "corrupt"


# ---------------------------------------------------------------------------
# Diagnostic export
# ---------------------------------------------------------------------------

def test_diagnostic_export_writes_redacted_bundle(tmp_path):
    obs.record_event("error", session_id="s", module="d3_backend",
                     data={"detail": f"api_key = '{MULTI_WORD_SECRET}'"},
                     state_root=tmp_path)
    obs.record_audit_event("login", actor="admin", detail=BEARER_SECRET,
                           state_root=tmp_path)
    target = tmp_path / "support" / "bundle.json"

    returned = obs.export_diagnostics(tmp_path, target, modules=["d3_backend"])
    assert returned == target
    assert target.is_file()
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["format"] == "keel-observability-export-v1"
    assert document["health"]["running"] is True
    assert document["diagnostics"]["chain_status"] == "ok"
    assert document["metrics"]["audit_count"] == 1
    _assert_no_secrets(document)
    _assert_no_secrets(target.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Cross-process integrity and concurrent load
# ---------------------------------------------------------------------------

def _child_env(tmp_path: Path, worker: str) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + existing if existing else "")
    env["OBS_ROOT"] = str(tmp_path)
    env["OBS_WORKER"] = worker
    return env


def test_cross_process_event_integrity(tmp_path):
    script = (
        "import os\n"
        "from keel import backend_observability as obs\n"
        "for i in range(10):\n"
        "    obs.record_event('cross', session_id='s-' + os.environ['OBS_WORKER'],\n"
        "                     task_id='t-%s-%d' % (os.environ['OBS_WORKER'], i),\n"
        "                     data={'i': i}, state_root=os.environ['OBS_ROOT'])\n"
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda index: subprocess.run(
                [sys.executable, "-c", script],
                env=_child_env(tmp_path, str(index)),
                capture_output=True, text=True, timeout=90,
            ),
            range(4),
        ))
    for result in results:
        assert result.returncode == 0, result.stderr

    assert obs.verify_chain(tmp_path).ok is True
    events = obs.read_events(tmp_path)
    assert len(events) == 40
    assert [event["seq"] for event in events] == list(range(1, 41))
    assert len({event["correlation_id"] for event in events}) == 40
    assert len(_log(tmp_path).read_text(encoding="utf-8").splitlines()) == 40


def test_cross_process_append_refused_after_corruption(tmp_path):
    for index in range(3):
        obs.record_event("before", session_id="s", data={"i": index},
                         state_root=tmp_path)
    log = _log(tmp_path)
    original = log.read_text(encoding="utf-8")
    log.write_text(original.replace('"i":1', '"i":99'), encoding="utf-8")
    corrupted = log.read_text(encoding="utf-8")

    script = (
        "import os\n"
        "from keel import backend_observability as obs\n"
        "obs.record_event('after', session_id='s', state_root=os.environ['OBS_ROOT'])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], env=_child_env(tmp_path, "late"),
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode != 0
    assert "ChainIntegrityError" in result.stderr
    assert log.read_text(encoding="utf-8") == corrupted


def test_concurrent_record_verify_and_report(tmp_path):
    def operation(index: int):
        if index % 3 == 0:
            obs.record_event(
                "stress", session_id=f"s-{index % 2}", task_id=f"task-{index}",
                data={"secret": BEARER_SECRET, "i": index}, state_root=tmp_path,
            )
            return "write"
        if index % 3 == 1:
            assert obs.verify_chain(tmp_path).ok is True
            return "verify"
        report = obs.diagnostic_report(tmp_path)
        assert report["chain_status"] == "ok"
        return "report"

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(operation, range(30)))

    assert outcomes.count("write") == 10
    assert obs.verify_chain(tmp_path).ok is True
    events = obs.read_events(tmp_path)
    assert len(events) == 10
    assert sorted(event["data"]["i"] for event in events) == list(range(0, 30, 3))
    for secret in (BEARER_SECRET, BEARER_SECRET.split(None, 1)[1]):
        assert secret not in _log(tmp_path).read_text(encoding="utf-8")


def test_verify_report_and_append_after_in_process_corruption(tmp_path):
    for index in range(5):
        obs.record_event("before", session_id="s", data={"i": index},
                         state_root=tmp_path)
    log = _log(tmp_path)
    original = log.read_text(encoding="utf-8")
    log.write_text(original.replace('"seq":3', '"seq":30'), encoding="utf-8")

    assert obs.verify_chain(tmp_path).ok is False
    report = obs.diagnostic_report(tmp_path)
    assert report["chain_status"] == "corrupt"
    assert report["chain"]["error"]
    with pytest.raises(obs.ChainIntegrityError):
        obs.read_events(tmp_path)
    with pytest.raises(obs.ChainIntegrityError):
        obs.record_event("refused", session_id="s", state_root=tmp_path)
    assert log.read_text(encoding="utf-8") == original.replace('"seq":3', '"seq":30')
