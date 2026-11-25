"""Final provider verification: offline integration + opt-in live harness gates.

No test in this file opens a socket, reads a real credential value or makes a
live request. The harness is exercised entirely with injected transports and
injected environment mappings, including every fail-closed path.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from keel import provider_catalog, provider_contracts as pc
from keel import provider_validation as pv
from keel.providers import registry as reg
from keel.providers.base import (RETRY_AUTH, ProviderError, TurnCancelled,
                                 UsageRecord)

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
HARNESS_PATH = SCRIPTS / "verify_live_provider.py"

_spec = importlib.util.spec_from_file_location("verify_live_provider", HARNESS_PATH)
harness = importlib.util.module_from_spec(_spec)
sys.modules["verify_live_provider"] = harness
_spec.loader.exec_module(harness)

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
FAKE_KEY = "final-synthetic-not-a-real-key-0123456789abcdef"
OPENROUTER_KEY = "KEEL_OPENROUTER_API_KEY"


# --- helpers -----------------------------------------------------------------

def _descriptor(identifier: str = "free", **overrides):
    values = {
        "id": identifier,
        "base_url": "https://free.example/v1",
        "protocol": "openai-chat-completions",
        "models": ("m1",),
        "user_approved": True,
    }
    values.update(overrides)
    return pc.ProviderDescriptor(**values)


def _entry(identifier: str, **overrides):
    values = {
        "id": identifier,
        "protocol": "openai-chat-completions",
        "models": ("m1",),
        "user_approved": True,
        "bundled": False,
        "paid": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _ok_payload(text: str = "hello") -> dict:
    return {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3},
    }


def _confirmation(**overrides) -> dict:
    doc = {
        "schema_version": 1,
        "provider": "openrouter",
        "model": "openrouter/free-test:free",
        "operator": "operator-alpha",
        "confirmed_at": NOW.date().isoformat(),
        "free_tier_current": True,
        "no_paid_usage": True,
    }
    doc.update(overrides)
    return doc


def _write_confirmation(tmp_path: Path, doc: dict) -> str:
    target = tmp_path / "confirmation.json"
    target.write_text(json.dumps(doc), encoding="utf-8")
    return str(target)


def _flags(*names: str) -> tuple[str, ...]:
    return tuple(names)


def _options(tmp_path: Path, doc: dict | None = None, **overrides) -> dict:
    options = {
        "flags": _flags(harness.ALLOW_LIVE_FLAG,
                        harness.CONFIRM_FREE_TIER_FLAG),
        "provider": "openrouter",
        "model": None,
        "confirmation_file": _write_confirmation(
            tmp_path, _confirmation() if doc is None else doc),
    }
    options.update(overrides)
    return options


def _sse(*objects: dict):
    return iter([("data: " + json.dumps(obj) + "\n\n").encode("utf-8")
                 for obj in objects])


def _fake_openai_transport(calls: list[dict], *, secret: str = FAKE_KEY):
    def transport(wire: dict):
        calls.append(dict(wire))
        return (200, {}, _sse(
            {"choices": [{"index": 0, "delta": {"content": "keel-ok"}}]},
            {"usage": {"prompt_tokens": 3, "completion_tokens": 1}},
        ))
    return transport


# --- 1. adapter registration, config and model discovery ---------------------

def test_registration_requires_explicit_approval_and_is_unique():
    registry = pc.ProviderRegistry()
    with pytest.raises(pc.ProviderContractError):
        registry.add(_descriptor(user_approved=False))
    registry.add(_descriptor())
    with pytest.raises(pc.ProviderContractError):
        registry.add(_descriptor())
    assert [entry.id for entry in registry.list()] == ["free"]


@pytest.mark.parametrize("bad", [
    {"base_url": "http://plain.example/v1"},
    {"base_url": "https://user:pw@example/v1"},
    {"protocol": "unknown-protocol"},
    {"models": ()},
])
def test_provider_descriptors_fail_closed_on_bad_config(bad):
    with pytest.raises(pc.ProviderContractError):
        _descriptor(**bad)


def test_string_approval_cannot_be_coerced_into_true():
    with pytest.raises(pc.ProviderContractError):
        pc.provider_from_dict({
            "id": "free", "base_url": "https://free.example/v1",
            "protocol": "openai-chat-completions", "models": ["m1"],
            "user_approved": "false",
        })


def test_search_excludes_paid_and_bundled_entries():
    entries = (_descriptor(), _entry("paid", paid=True),
               _entry("bundled", bundled=True))
    assert tuple(entry.id for entry in pc.search_catalog(
        entries, capability=None)) == ("free",)
    assert tuple(entry.id for entry in pc.search_catalog(
        entries, protocol="openai-chat-completions")) == ("free",)


def test_model_discovery_catalog_is_validated_and_isolated(tmp_path):
    info = provider_catalog.catalog_info()
    assert info.provider_count >= 5 and info.model_count > 0
    doc = provider_catalog.load_catalog()
    doc["providers"].clear()
    assert provider_catalog.catalog_info().provider_count == info.provider_count

    tampered = json.loads(provider_catalog.catalog_path().read_text(encoding="utf-8"))
    tampered["provider_count"] += 1
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(provider_catalog.CatalogError):
        provider_catalog.load_catalog(path=path)


def test_runtime_adapters_are_registered_and_catalog_only_is_not_executable():
    names = set(reg._PROVIDERS)
    assert {"openrouter", "google", "nvidia", "anthropic",
            "openai-compatible"} <= names
    with pytest.raises(reg.ProviderError):
        reg.resolve_provider_model("catalog-only/model",
                                   provider_config={"defaultProvider": "auto"})


# --- 2. request normalization and health diagnostics -------------------------

def test_request_normalization_drops_credentials_and_clamps_output():
    capabilities = pc.ModelCapabilities(
        model_id="m1", input_types=frozenset({"text"}),
        context_window=1024, max_output=64)
    request = {
        "model": "m1", "messages": [{"role": "user", "content": "hi"}],
        "api_key": FAKE_KEY, "max_tokens": 999,
        "reasoning_effort": "high",
    }
    adapted = pc.normalize_request(capabilities, request, secrets=(FAKE_KEY,))
    assert "api_key" not in adapted.request
    assert adapted.request["max_tokens"] == 64
    assert FAKE_KEY not in json.dumps(adapted.request)
    assert any("removed credential-like field" in note
               for note in adapted.adjustments)
    report = pc.capability_report(capabilities)
    assert report["warning"] == pc.UNVERIFIED_CLAIMS_WARNING


def test_offline_validation_reports_no_live_success():
    doc = pv.run_validation(live=False)
    assert doc["live"] is False
    for checks in doc["providers"].values():
        live = [check for check in checks if check["name"] == "live_provider"]
        assert live and live[0]["status"] == "SKIP"


def test_execution_config_diagnostics_are_value_free():
    problems = pc.validate_execution_config(
        pc.ExecutionConfig(max_attempts=0, timeout_seconds=400,
                           fallbacks=("backup",)))
    assert any("max_attempts" in item for item in problems)
    assert any("timeout_seconds" in item for item in problems)
    assert any("primary" in item for item in problems)
    assert all(FAKE_KEY not in item for item in problems)


# --- 3. execution: streaming, retries, cancellation, classification ----------

def test_non_streaming_success_and_usage():
    calls: list[dict] = []
    cfg = pc.ExecutionConfig(primary="free", max_attempts=1)
    result = pc.execute_request(
        cfg, {"model": "m1", "messages": []},
        transport=lambda wire: (calls.append(wire) or _ok_payload()),
        descriptors={"free": _entry("free")})
    assert result.status == "ok"
    assert result.response is not None and result.response.text == "hello"
    assert result.response.usage.input_tokens == 2
    assert len(calls) == 1
    assert FAKE_KEY not in json.dumps(result.to_dict())


def test_streaming_accumulates_and_does_not_replay_partial_content():
    def chunks(_wire):
        yield {"event": "text_delta", "text": "partial "}
        yield {"event": "error", "category": pc.CATEGORY_SERVER,
               "message": "busy", "retryable": True}

    cfg = pc.ExecutionConfig(primary="free", fallbacks=("backup",),
                             max_attempts=3)
    descriptors = {"free": _entry("free"), "backup": _entry("backup")}
    result = pc.execute_stream(
        cfg, {"model": "m1", "messages": []},
        transport=chunks, descriptors=descriptors)
    assert result.status == "partial_failed"
    assert result.response is not None and result.response.text == "partial "
    assert result.fallbacks_used == ()


def test_retries_are_bounded_and_security_errors_never_retry():
    cfg = pc.ExecutionConfig(primary="free", max_attempts=5,
                             base_backoff_seconds=0)
    descriptors = {"free": _entry("free")}

    retry_calls: list[dict] = []

    def busy(wire):
        retry_calls.append(wire)
        raise pc.ProviderTransportError("busy", category=pc.CATEGORY_RATE_LIMIT,
                                        retryable=True)

    result = pc.execute_request(
        cfg, {"model": "m1", "messages": []}, transport=busy,
        descriptors=descriptors, sleep=lambda _: None)
    assert result.status == "failed" and len(retry_calls) == 5
    assert len(result.backoff_seconds) == 4

    auth_calls: list[dict] = []

    def denied(wire):
        auth_calls.append(wire)
        raise pc.ProviderTransportError("denied", category=pc.CATEGORY_AUTH,
                                        retryable=False)

    pc.execute_request(cfg, {"model": "m1", "messages": []},
                       transport=denied, descriptors=descriptors,
                       sleep=lambda _: None)
    assert len(auth_calls) == 1


def test_cancellation_precedes_any_transport_call():
    cancel = threading.Event()
    cancel.set()
    called: list[dict] = []
    cfg = pc.ExecutionConfig(primary="free")
    result = pc.execute_request(
        cfg, {"model": "m1", "messages": []},
        transport=lambda wire: called.append(wire),
        cancel=cancel, descriptors={"free": _entry("free")})
    assert result.status == "cancelled" and called == []


def test_error_classification_redacts_and_never_retries_auth():
    failure = pc.classify_status(401, payload={
        "error": {"code": "invalid_api_key", "message": "denied " + FAKE_KEY}},
        secrets=(FAKE_KEY,))
    assert failure.category in (pc.CATEGORY_AUTH, pc.CATEGORY_CREDENTIAL)
    assert not failure.retryable
    assert FAKE_KEY not in failure.message
    payload_failure = pc.classify_payload({
        "error": {"type": "overloaded_error", "message": "busy"}})
    assert payload_failure is not None
    assert payload_failure.category == pc.CATEGORY_OVERLOADED
    assert pc.classify_exception(TimeoutError("late")).category == pc.CATEGORY_TIMEOUT
    assert pc.classify_exception(TurnCancelled()).category == pc.CATEGORY_CANCELLED


def test_fallback_cannot_route_to_a_paid_service():
    descriptors = {"free": _entry("free"), "paid": _entry("paid", paid=True)}
    cfg = pc.ExecutionConfig(primary="free", fallbacks=("paid",), max_attempts=1)
    problems = pc.validate_execution_config(cfg, descriptors=descriptors)
    assert any("paid" in item for item in problems)
    called: list[dict] = []
    result = pc.execute_request(
        cfg, {"model": "m1", "messages": []},
        transport=lambda wire: called.append(wire) or _ok_payload(),
        descriptors=descriptors)
    assert result.status == "failed" and called == []
    assert result.fallbacks_used == ()


def test_validation_timeout_is_a_failure_not_a_skip(monkeypatch):
    cap = reg.CapabilityRecord(
        name="slow-probe", base_url="https://slow.invalid/v1",
        env_var="KEEL_SLOW_PROBE_KEY", default_model="m1",
        supports_tools=True, supports_streaming=True)
    monkeypatch.setenv(cap.env_var, "synthetic-key")

    class Slow:
        def __init__(self, cap, *, api_key=""):
            pass

        def complete(self, request):
            time.sleep(0.3)
            yield {"event": "text_delta", "index": 0, "text": "late"}

    doc = pv.run_validation(live=True, providers=[cap],
                            adapter_factory=Slow, timeout_s=0.02)
    checks = {check["name"]: check for check in doc["providers"][cap.name]}
    assert checks["live_timeout"]["status"] == "FAIL"
    assert "streaming_response" not in checks


# --- 4. live harness: fail-closed gates (all mocked, no network) -------------

def _exploding_transport(*_args, **_kwargs):
    raise AssertionError("no external request may be attempted by a blocked harness")


def _blocked_case(tmp_path, env, options):
    calls: list[dict] = []
    output = io.StringIO()
    # main() takes argv; use explicit flag arguments matching the options dict.
    argv = []
    if harness.ALLOW_LIVE_FLAG in options.get("flags", ()):
        argv.append(harness.ALLOW_LIVE_FLAG)
    if harness.CONFIRM_FREE_TIER_FLAG in options.get("flags", ()):
        argv.append(harness.CONFIRM_FREE_TIER_FLAG)
    if options.get("provider"):
        argv += ["--provider", options["provider"]]
    if options.get("model"):
        argv += ["--model", options["model"]]
    if options.get("confirmation_file"):
        argv += ["--confirmation-file", options["confirmation_file"]]
    code = harness.main(argv, env=env, transport=_fake_openai_transport(calls),
                        now=NOW, repo_root=str(REPO), stdout=output)
    return code, output.getvalue(), calls


@pytest.mark.parametrize("flags", [
    (),
    _flags(harness.ALLOW_LIVE_FLAG),
    _flags(harness.CONFIRM_FREE_TIER_FLAG),
])
def test_harness_requires_both_explicit_flags(tmp_path, flags):
    env = {OPENROUTER_KEY: FAKE_KEY}
    options = _options(tmp_path, flags=flags)
    code, output, calls = _blocked_case(tmp_path, env, options)
    assert code == 2 and calls == []
    report = json.loads(output)
    assert report["status"] == "blocked" and report["quota_context"]["transport_calls"] == 0


def test_harness_blocks_missing_or_bad_confirmation(tmp_path):
    env = {OPENROUTER_KEY: FAKE_KEY}
    cases = [
        _options(tmp_path, confirmation_file=str(tmp_path / "missing.json")),
        _options(tmp_path, doc=_confirmation(confirmed_at=(
            NOW - timedelta(days=60)).date().isoformat())),
        _options(tmp_path, doc=_confirmation(free_tier_current=False)),
        _options(tmp_path, doc=_confirmation(no_paid_usage=False)),
        _options(tmp_path, doc=_confirmation(operator="")),
        _options(tmp_path, doc=_confirmation(model="auto")),
        _options(tmp_path, doc=_confirmation(model="openrouter/gpt-4o")),
        _options(tmp_path, doc=_confirmation(operator=FAKE_KEY)),
    ]
    for options in cases:
        code, output, calls = _blocked_case(tmp_path, env, options)
        assert code == 2 and calls == []
        assert json.loads(output)["status"] == "blocked"
        assert FAKE_KEY not in output


def test_harness_blocks_missing_blank_and_malformed_credentials(tmp_path):
    good = _write_confirmation(tmp_path, _confirmation())
    for value in ("", "   \t ", "final-bad\ncredential"):
        env = {} if value == "" else {OPENROUTER_KEY: value}
        options = _options(tmp_path, confirmation_file=good)
        code, output, calls = _blocked_case(tmp_path, env, options)
        assert code == 2 and calls == []
        assert json.loads(output)["status"] == "blocked"


def test_harness_blocks_paid_and_unlisted_providers(tmp_path):
    doc = _confirmation(provider="anthropic", model="claude-sonnet-4-5")
    path = _write_confirmation(tmp_path, doc)
    env = {OPENROUTER_KEY: FAKE_KEY, "KEEL_ANTHROPIC_API_KEY": FAKE_KEY}
    options = _options(tmp_path, provider="anthropic", confirmation_file=path)
    code, output, calls = _blocked_case(tmp_path, env, options)
    assert code == 2 and calls == []
    assert any("paid/opt-in" in reason or "allowlist" in reason
               for reason in json.loads(output)["result"]["reasons"])


def test_harness_blocks_model_mismatch(tmp_path):
    good = _write_confirmation(tmp_path, _confirmation())
    options = _options(tmp_path, confirmation_file=good,
                       model="openrouter/other:free")
    code, output, calls = _blocked_case(
        tmp_path, {OPENROUTER_KEY: FAKE_KEY}, options)
    assert code == 2 and calls == []


def test_harness_success_records_only_safe_fields(tmp_path):
    path = _write_confirmation(tmp_path, _confirmation())
    calls: list[dict] = []
    output = io.StringIO()
    results = tmp_path / "result.json"
    argv = [harness.ALLOW_LIVE_FLAG, harness.CONFIRM_FREE_TIER_FLAG,
            "--provider", "openrouter", "--confirmation-file", path,
            "--results-json", str(results)]
    code = harness.main(argv, env={OPENROUTER_KEY: FAKE_KEY},
                        transport=_fake_openai_transport(calls), now=NOW,
                        repo_root=str(REPO), stdout=output)
    assert code == 0
    report = json.loads(output.getvalue())
    assert report["status"] == "ok"
    assert report["provider"] == "openrouter"
    assert report["model"] == "openrouter/free-test:free"
    assert report["timestamp_utc"] == NOW.isoformat()
    assert report["commit"] and report["commit"] != "unknown"
    assert report["result"]["text_chars"] == len("keel-ok")
    assert report["result"]["usage"] == {"input_tokens": 3, "output_tokens": 1}
    assert report["quota_context"]["transport_calls"] == 1
    assert report["quota_context"]["max_output_tokens"] == 16
    assert report["quota_context"]["fallbacks"] == []
    assert set(report) == {"kind", "status", "provider", "model",
                           "timestamp_utc", "commit", "quota_context",
                           "result", "note"}
    assert len(calls) == 1
    assert calls[0]["body_json"]["max_tokens"] == 16
    assert "tools" not in calls[0]["body_json"]
    assert calls[0]["timeout"] <= harness.WALL_CLOCK_TIMEOUT_SECONDS
    saved = results.read_text(encoding="utf-8")
    assert FAKE_KEY not in output.getvalue() and FAKE_KEY not in saved
    assert "keel-ok" not in saved


def test_harness_accepts_confirmation_path_from_env(tmp_path):
    path = _write_confirmation(tmp_path, _confirmation())
    calls: list[dict] = []
    output = io.StringIO()
    argv = [harness.ALLOW_LIVE_FLAG, harness.CONFIRM_FREE_TIER_FLAG,
            "--provider", "openrouter"]
    code = harness.main(argv, env={OPENROUTER_KEY: FAKE_KEY,
                                   harness.CONFIRMATION_ENV: path},
                        transport=_fake_openai_transport(calls), now=NOW,
                        repo_root=str(REPO), stdout=output)
    assert code == 0 and len(calls) == 1
    assert json.loads(output.getvalue())["status"] == "ok"


def test_harness_failure_is_not_retried_and_is_redacted(tmp_path):
    path = _write_confirmation(tmp_path, _confirmation())
    calls: list[dict] = []

    def failing(wire):
        calls.append(dict(wire))
        raise ProviderError("denied for " + FAKE_KEY, RETRY_AUTH, 401)

    output = io.StringIO()
    argv = [harness.ALLOW_LIVE_FLAG, harness.CONFIRM_FREE_TIER_FLAG,
            "--provider", "openrouter", "--confirmation-file", path]
    code = harness.main(argv, env={OPENROUTER_KEY: FAKE_KEY},
                        transport=failing, now=NOW, repo_root=str(REPO),
                        stdout=output)
    assert code == 1 and len(calls) == 1
    report = json.loads(output.getvalue())
    assert report["status"] == "failed"
    assert report["result"]["error_category"] == RETRY_AUTH
    assert FAKE_KEY not in output.getvalue()


def test_harness_timeout_is_reported_without_secret(tmp_path):
    path = _write_confirmation(tmp_path, _confirmation())

    def slow(_wire):
        time.sleep(0.25)
        return (200, {}, _sse(
            {"choices": [{"index": 0, "delta": {"content": "late"}}]}))

    output = io.StringIO()
    argv = [harness.ALLOW_LIVE_FLAG, harness.CONFIRM_FREE_TIER_FLAG,
            "--provider", "openrouter", "--confirmation-file", path,
            "--timeout-seconds", "0.02"]
    code = harness.main(argv, env={OPENROUTER_KEY: FAKE_KEY}, transport=slow,
                        now=NOW, repo_root=str(REPO), stdout=output)
    assert code == 1
    report = json.loads(output.getvalue())
    assert report["status"] == "timeout"
    assert FAKE_KEY not in output.getvalue()


def test_bounded_transport_refuses_a_second_request():
    bounded = harness._BoundedTransport(lambda request: (200, {}, iter(())),
                                        timeout_s=1.0)
    bounded({"timeout": 999})
    with pytest.raises(RuntimeError):
        bounded({"timeout": 1})
