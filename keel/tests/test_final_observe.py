"""Final verification — observability integration and operational safety.

Every test uses the real JSONL log, real filesystem bytes, real threads and (for
the HTTP endpoints) a real local HTTP server. No production function is mocked
except two deliberate fault injections: an import failure carrying a credential
and a failing dependency probe carrying a Bearer token. Those injections exist
only to prove redaction at the diagnostic/HTTP boundary.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from keel import backend_observability as obs
from keel import diagnostics, webapp

NATURAL_SECRET = "The password is Harbor Seal42 Tango Mike"
NATURAL_SECRET_VALUE = "Harbor Seal42 Tango Mike"
PASSPHRASE_SECRET = "The passphrase was green lantern delta 99"
PASSPHRASE_VALUE = "green lantern delta 99"
BEARER = "Bearer abcdef1234567890XYZ"
BEARER_VALUE = "abcdef1234567890XYZ"
INLINE_SECRET = "trident lunar velvet compass"

ALL_SECRETS = (NATURAL_SECRET, NATURAL_SECRET_VALUE,
               PASSPHRASE_SECRET, PASSPHRASE_VALUE,
               BEARER, BEARER_VALUE, INLINE_SECRET)


def _assert_clean(value: object) -> None:
    dumped = value if isinstance(value, str) else json.dumps(value, default=str)
    for secret in ALL_SECRETS:
        assert secret not in dumped, f"secret leaked into: {dumped[:400]}"


def _log(root) -> "os.PathLike[str]":
    from pathlib import Path
    return Path(root) / obs.LOG_FILENAME


# ---------------------------------------------------------------------------
# Structured logs, correlation IDs and audit linkage
# ---------------------------------------------------------------------------

def test_structured_event_and_audit_carry_correlation_and_identity(tmp_path):
    event = obs.record_event(
        "workflow.start", session_id="s-1", task_id="t-1", agent_id="a-1",
        feature_id="F1", module="d3_backend", data={"step": 1},
        state_root=tmp_path,
    )
    audit = obs.record_audit_event(
        "config.change", actor="operator-7", outcome="success",
        request_id=event["correlation_id"], detail="approved",
        state_root=tmp_path,
    )

    for field in ("seq", "ts", "kind", "session_id", "task_id", "agent_id",
                  "feature_id", "module", "correlation_id", "data",
                  "prev_hash", "hash"):
        assert field in event
    assert len(event["correlation_id"]) == 32
    assert len(event["hash"]) == 64

    assert audit["kind"] == obs.AUDIT_KIND
    assert audit["seq"] == event["seq"] + 1
    assert audit["data"]["action"] == "config.change"
    assert audit["data"]["actor"] == "operator-7"
    assert audit["data"]["outcome"] == "success"
    assert audit["data"]["request_id"] == event["correlation_id"]
    assert audit["correlation_id"] != event["correlation_id"]
    assert obs.verify_chain(tmp_path).ok is True


def test_high_volume_concurrent_writes_keep_unique_ids_and_full_history(tmp_path):
    def write(index: int):
        return obs.record_event(
            "stress", session_id=f"session-{index % 4}", task_id=f"task-{index}",
            data={"i": index}, state_root=tmp_path,
            max_events=25, max_archives=2,
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        events = list(pool.map(write, range(150)))

    assert len(events) == 150
    assert len({event["correlation_id"] for event in events}) == 150
    assert obs.verify_chain(tmp_path).ok is True

    hot = obs.read_events(tmp_path, include_archives=True)
    cold = obs.read_forensic_archives(tmp_path)
    history = cold + hot
    assert len(history) == 150
    assert [event["seq"] for event in history] == list(range(1, 151))
    assert obs.verify_forensic_archives(tmp_path)["ok"] is True


# ---------------------------------------------------------------------------
# Real dependency probes and honest readiness at the library boundary
# ---------------------------------------------------------------------------

def test_health_http_payload_reports_every_real_dependency(tmp_path):
    executed: set[str] = set()

    def make(name: str):
        def probe() -> bool:
            executed.add(name)
            return True
        return probe

    dependencies = {name: make(name)
                    for name in ("database", "events", "workers", "providers")}
    payload = obs.health_http_payload(tmp_path, ["d3_backend"],
                                      dependencies=dependencies)

    assert executed == {"database", "events", "workers", "providers"}
    assert payload["dependencies"] == {
        "database": "ok", "events": "ok", "workers": "ok", "providers": "ok",
    }
    assert payload["ready"] is True
    assert payload["status"] == "ready"
    assert len(payload["correlation_id"]) == 32


def test_failing_provider_probe_is_reported_without_leaking_secret(tmp_path):
    def bad_provider():
        raise RuntimeError(f"Authorization: {BEARER}")

    deps = obs.dependency_health({"provider": bad_provider})
    assert deps["healthy"] is False
    assert deps["dependencies"]["provider"]["status"] == "error"
    assert "[REDACTED]" in deps["dependencies"]["provider"]["error"]
    _assert_clean(deps)

    payload = obs.health_http_payload(tmp_path, dependencies={
        "database": lambda: True,
        "provider": bad_provider,
    })
    assert payload["ready"] is False
    assert payload["status"] == "running"
    assert payload["dependencies"]["provider"] == "error"
    _assert_clean(payload)
    assert "RuntimeError" not in json.dumps(payload)


def test_dependency_health_without_probes_is_not_healthy(tmp_path):
    empty = obs.dependency_health({})
    assert empty["healthy"] is False
    assert empty["dependency_count"] == 0

    check = obs.health_check(tmp_path, dependencies={})
    assert check["running"] is True
    assert check["ready"] is False
    assert check["status"] == "running"


def test_default_provider_probe_is_a_real_executable_probe(tmp_path, monkeypatch):
    from keel.providers import registry

    deps = obs.dependency_health(obs.default_dependency_probes(tmp_path))
    assert deps["healthy"] is True
    assert set(deps["dependencies"]) == {
        "database", "provider", "worker", "event_log",
    }
    assert deps["dependencies"]["provider"]["ok"] is True

    # A mere module-presence check would still pass here; a real probe must
    # fail when the registry cannot enumerate or construct providers.
    monkeypatch.setattr(registry, "list_providers", lambda: [])
    broken = obs.dependency_health(obs.default_dependency_probes(tmp_path))
    assert broken["dependencies"]["provider"]["status"] == "error"


def test_health_payload_omits_paths_and_raw_import_errors(tmp_path, monkeypatch):
    def failing_import(name):
        return None, "RuntimeError: broken import"

    monkeypatch.setattr(obs, "_import_module", failing_import)
    payload = obs.health_http_payload(tmp_path, ["broken_backend"])
    dumped = json.dumps(payload)
    assert str(tmp_path) not in dumped
    assert "import_error" not in dumped
    assert "broken import" not in dumped


# ---------------------------------------------------------------------------
# Real local HTTP endpoints (/api/health and /api/ready only)
# ---------------------------------------------------------------------------

@pytest.fixture
def http_server(monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "_state_root", lambda: tmp_path)
    monkeypatch.setattr(webapp, "_SHUTDOWN", threading.Event())
    monkeypatch.setattr(webapp, "_WORKER", None)
    server = webapp.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _get_json(server, path: str):
    url = (f"http://127.0.0.1:{server.server_address[1]}{path}"
           f"?t={webapp.token()}")
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_webapp_health_and_ready_report_real_dependencies(http_server):
    status, doc = _get_json(http_server, "/api/health")
    assert status == 200
    assert doc["ok"] is True
    assert set(doc["dependencies"]) == {
        "database", "events", "workers", "providers",
    }
    assert all(value in {"ok", "error"} for value in doc["dependencies"].values())
    assert doc["chain_status"] == "ok"
    assert doc["initialized"] is False  # fresh root: no event recorded yet
    assert len(doc["correlation_id"]) == 32

    status, ready = _get_json(http_server, "/api/ready")
    assert status == 200
    assert ready == {"ready": True, "status": "ready"}


def test_webapp_ready_refuses_when_provider_probe_fails_with_secret(
    http_server, monkeypatch,
):
    def bad_provider():
        raise RuntimeError(f"Authorization: {BEARER}")

    monkeypatch.setattr(webapp, "_readiness_dependencies", lambda: {
        "database": lambda: True,
        "events": lambda: True,
        "workers": lambda: True,
        "providers": bad_provider,
    })

    status, ready = _get_json(http_server, "/api/ready")
    assert status == 503
    assert ready["ready"] is False
    assert ready["status"] == "running"
    _assert_clean(ready)

    status, health = _get_json(http_server, "/api/health")
    assert status == 200
    assert health["ok"] is True          # liveness is unaffected
    assert health["ready"] is False      # readiness never claimed falsely
    assert health["dependencies"]["providers"] == "error"
    _assert_clean(health)


# ---------------------------------------------------------------------------
# Redaction across exceptions, HTTP responses, logs, events, audit and exports
# ---------------------------------------------------------------------------

def test_natural_language_secrets_are_redacted_in_every_channel(
    tmp_path, monkeypatch,
):
    obs.record_event(
        "error", session_id="s", module="d3_backend",
        data={"message": NATURAL_SECRET,
              "nested": {"note": PASSPHRASE_SECRET}},
        state_root=tmp_path,
    )
    audit = obs.record_audit_event(
        "provider.call", actor="operator", detail=NATURAL_SECRET,
        state_root=tmp_path,
    )

    def failing_import(name):
        return None, f"RuntimeError: {NATURAL_SECRET}"

    monkeypatch.setattr(obs, "_import_module", failing_import)

    _assert_clean(_log(tmp_path).read_text(encoding="utf-8"))
    _assert_clean(obs.read_events(tmp_path))
    _assert_clean(audit)
    _assert_clean(obs.diagnostic_report(tmp_path))

    snapshot = obs.health_snapshot(tmp_path, ["failing_backend"])
    assert "[REDACTED]" in snapshot["modules"]["failing_backend"]["import_error"]
    _assert_clean(snapshot)

    payload = obs.health_http_payload(tmp_path, ["failing_backend"])
    _assert_clean(payload)

    bundle = obs.export_diagnostics(
        tmp_path, tmp_path / "support" / "bundle.json",
        modules=["failing_backend"],
    )
    _assert_clean(bundle.read_text(encoding="utf-8"))


def test_bearer_token_is_redacted_in_exception_response_logs_and_audit(
    tmp_path,
):
    def bad_probe():
        raise RuntimeError(f"Authorization: {BEARER}")

    deps = obs.dependency_health({"provider": bad_probe})
    assert BEARER not in deps["dependencies"]["provider"]["error"]
    assert "[REDACTED]" in deps["dependencies"]["provider"]["error"]

    payload = obs.health_http_payload(tmp_path, dependencies={
        "provider": bad_probe,
    })
    _assert_clean(payload)

    event = obs.record_event(
        "provider.call", session_id="s", data={"header": BEARER},
        state_root=tmp_path,
    )
    _assert_clean(event)

    audit = obs.record_audit_event(
        "provider.call", actor="a", detail=f"header: {BEARER}",
        state_root=tmp_path,
    )
    _assert_clean(audit)
    _assert_clean(_log(tmp_path).read_text(encoding="utf-8"))


def test_diagnostics_bundle_masks_secret_named_environment_values(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("KEEL_PASSPHRASE_VERIFY", NATURAL_SECRET_VALUE)
    monkeypatch.setenv("KEEL_AUTHORIZATION_VERIFY", BEARER)
    monkeypatch.setenv("KEEL_PRIVATE_KEY_VERIFY", INLINE_SECRET)

    collected = diagnostics.collect()
    assert "KEEL_PASSPHRASE_VERIFY" in collected["env_flags"]
    assert "KEEL_AUTHORIZATION_VERIFY" in collected["env_flags"]
    _assert_clean(collected)

    target = diagnostics.write_bundle(tmp_path / "support" / "diag.zip")
    with zipfile.ZipFile(target) as archive:
        report = archive.read("diagnostics.json").decode("utf-8")
    _assert_clean(report)
    assert "No conversation content" in report


# ---------------------------------------------------------------------------
# Bounded retention, forensic evidence and atomic writes
# ---------------------------------------------------------------------------

def test_forensic_archives_preserve_hash_chain_and_full_history(tmp_path):
    for index in range(40):
        obs.record_event(
            "stress", session_id="s", data={"i": index},
            state_root=tmp_path, max_events=5, max_archives=2,
        )

    forensic = obs.verify_forensic_archives(tmp_path)
    assert forensic["ok"] is True
    assert forensic["archive_count"] > 0
    assert forensic["event_count"] > 0

    hot = obs.read_events(tmp_path, include_archives=True)
    cold = obs.read_forensic_archives(tmp_path)
    history = cold + hot
    assert len(history) == 40
    assert [event["seq"] for event in history] == list(range(1, 41))
    # Hot window = max_archives hot generations + active log; each generation
    # holds at most max_events + 1 (the overflow write that triggers rotation).
    assert len(hot) <= 3 * (5 + 1)
    assert obs.verify_chain(tmp_path).ok is True


def test_tampered_forensic_archive_fails_closed(tmp_path):
    for index in range(30):
        obs.record_event(
            "stress", session_id="s", data={"i": index},
            state_root=tmp_path, max_events=5, max_archives=2,
        )
    before = obs.verify_forensic_archives(tmp_path)
    assert before["ok"] is True
    item = before["archives"][0]
    cold_dir = tmp_path / (obs.LOG_FILENAME + obs.FORENSIC_DIR_SUFFIX)
    archive = cold_dir / item["archive"]
    text = archive.read_text(encoding="utf-8")
    archive.write_text(text.replace('"i":0', '"i":999', 1), encoding="utf-8")

    after = obs.verify_forensic_archives(tmp_path)
    assert after["ok"] is False
    assert after["error"]
    with pytest.raises(obs.ChainIntegrityError):
        obs.read_forensic_archives(tmp_path)


def test_rotation_failure_preserves_evidence_and_raises_typed_error(tmp_path):
    for index in range(5):
        obs.record_event(
            "stress", session_id="s", data={"i": index},
            state_root=tmp_path, max_events=2, max_archives=1,
        )
    forensic = tmp_path / (obs.LOG_FILENAME + obs.FORENSIC_DIR_SUFFIX)
    forensic.write_text("occupied", encoding="utf-8")

    with pytest.raises(obs.ObservabilityStorageError):
        obs.record_event(
            "stress", session_id="s", data={"i": 5},
            state_root=tmp_path, max_events=2, max_archives=1,
        )

    # Security evidence is intact: no archive deleted, no bytes rewritten.
    assert forensic.is_file()
    assert forensic.read_text(encoding="utf-8") == "occupied"
    assert (tmp_path / f"{obs.LOG_FILENAME}.1").is_file()
    assert (tmp_path / f"{obs.LOG_FILENAME}.2").is_file()
    assert obs.verify_chain(tmp_path).ok is True
    assert len(_log(tmp_path).read_text(encoding="utf-8").splitlines()) == 3


def test_atomic_write_is_replacement_and_cleans_up_on_failure(
    tmp_path, monkeypatch,
):
    target = tmp_path / "bundle.json"
    target.write_text("old", encoding="utf-8")
    obs._atomic_write(target, b'{"new": true}\n')
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    assert not (tmp_path / "bundle.json.tmp").exists()

    real_write = os.write

    def failing_write(fd, data):
        raise OSError("simulated disk full")

    monkeypatch.setattr(os, "write", failing_write)
    try:
        with pytest.raises(OSError):
            obs._atomic_write(target, b'{"partial": true}\n')
    finally:
        monkeypatch.setattr(os, "write", real_write)

    assert not (tmp_path / "bundle.json.tmp").exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}


def test_tightest_configurable_caps_still_verify(tmp_path):
    for index in range(6):
        obs.record_event(
            "stress", session_id="s", data={"i": index},
            state_root=tmp_path, max_events=1, max_archives=1,
        )
    assert obs.verify_chain(tmp_path).ok is True
    history = (obs.read_forensic_archives(tmp_path)
               + obs.read_events(tmp_path, include_archives=True))
    assert [event["seq"] for event in history] == list(range(1, 7))


def test_corrupt_retention_state_fails_closed(tmp_path):
    for index in range(2):
        obs.record_event(
            "stress", session_id="s", data={"i": index},
            state_root=tmp_path, max_events=1, max_archives=1,
        )
    assert obs.verify_chain(tmp_path).ok is True
    (tmp_path / obs.STATE_FILENAME).write_text("not json", encoding="utf-8")

    assert obs.verify_chain(tmp_path).ok is False
    with pytest.raises(obs.ChainIntegrityError):
        obs.record_event("refused", session_id="s", state_root=tmp_path)


# ---------------------------------------------------------------------------
# Metrics, error categories and bounded diagnostic windows
# ---------------------------------------------------------------------------

def test_metrics_error_categories_and_recent_error_window_are_bounded(tmp_path):
    for index in range(25):
        obs.record_event(
            "error", session_id=f"s{index % 2}",
            data={"error_category": "provider" if index % 2 else "database"},
            state_root=tmp_path, max_events=30, max_archives=2,
        )
    obs.record_audit_event("config.change", actor="admin", state_root=tmp_path)

    metrics = obs.metrics_snapshot(tmp_path)
    assert metrics["chain_status"] == "ok"
    assert metrics["error_count"] == 25
    assert metrics["audit_count"] == 1
    assert metrics["error_categories"] == {"database": 13, "provider": 12}
    assert metrics["recent_error_count"] <= 20
    assert metrics["resources"]["thread_count"] >= 1

    report = obs.diagnostic_report(tmp_path)
    assert report["recent_error_count"] <= 20
    assert report["retention"]["active_events"] == 26


def test_no_mandatory_external_monitoring_service():
    sources = "".join(
        Path(module.__file__).read_text(encoding="utf-8").lower()
        for module in (obs, diagnostics)
    )
    for banned in ("prometheus", "opentelemetry", "datadog", "sentry",
                   "statsd", "requests.post", "urllib.request"):
        assert banned not in sources
