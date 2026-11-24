"""Production provider hardening — deterministic, offline failure-injection tests.

Every test here uses an injected transport or a temporary catalog file. Nothing
in this module opens a socket, loads a credential, or spends money. The fake
secret below is a literal test fixture, never a real credential.

Coverage:
  * confirmed config defects: approval gate bypass, CRLF endpoint, catalog
    cache poisoning and malformed catalog entries
  * audit areas: registration, model resolution, config validation, request
    and response normalization, streaming, timeout, cancellation, error
    classification, retries/backoff, rate limits, usage metadata, credential
    redaction, fallback discipline, local operation without a provider
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from keel import provider_catalog  # noqa: E402
from keel.provider_contracts import (  # noqa: E402
    CATEGORIES,
    CATEGORY_AUTH,
    CATEGORY_CONNECTION,
    CATEGORY_CONTEXT_LIMIT,
    CATEGORY_CREDENTIAL,
    CATEGORY_INVALID,
    CATEGORY_MALFORMED,
    CATEGORY_MODEL_NOT_FOUND,
    CATEGORY_ORG,
    CATEGORY_RATE_LIMIT,
    CATEGORY_SERVER,
    CATEGORY_TIMEOUT,
    CATEGORY_UNAVAILABLE,
    FALLBACK_CATEGORIES,
    RETRYABLE_CATEGORIES,
    ExecutionConfig,
    ModelCapabilities,
    NormalizedResponse,
    ProviderCancelled,
    ProviderContractError,
    ProviderDescriptor,
    ProviderFailure,
    ProviderRegistry,
    ProviderResult,
    ProviderTransportError,
    SecretDescriptor,
    TransportResponse,
    UsageMetadata,
    classify_exception,
    classify_payload,
    classify_status,
    execute_request,
    execute_stream,
    extract_retry_after,
    merge_usage,
    normalize_request,
    normalize_response,
    provider_from_dict,
    redact_message,
    retry_schedule,
    sanitize_event,
    validate_execution_config,
)

# Obvious fixture value: no real provider accepts this, it is not a credential.
FAKE_SECRET = "FAKE-TEST-KEY-q9w8e7r6q9w8e7r6-END"


def cfg(**overrides):
    base = dict(
        primary="alpha",
        fallbacks=(),
        max_attempts=3,
        base_backoff_seconds=0.25,
        backoff_factor=2.0,
        max_backoff_seconds=30.0,
        timeout_seconds=60.0,
        protocols={"alpha": "openai-chat-completions",
                   "backup": "openai-chat-completions"},
    )
    base.update(overrides)
    return ExecutionConfig(**base)


def descriptor(identifier="alpha", **overrides):
    base = dict(
        id=identifier,
        base_url=f"https://{identifier}.example.test/v1",
        protocol="openai-chat-completions",
        models=("model-a", "model-b"),
        capabilities=frozenset({"text", "tools"}),
        user_approved=True,
    )
    base.update(overrides)
    return ProviderDescriptor(**base)


def stub_descriptor(identifier="alpha", **overrides):
    """Structurally-compatible descriptor for fail-closed validation checks.

    ProviderDescriptor itself refuses paid/bundled construction, so this stub
    proves the execution gate also refuses them if such a config reaches it.
    """
    base = dict(id=identifier, base_url=f"https://{identifier}.example.test/v1",
                protocol="openai-chat-completions", models=("model-a",),
                capabilities=frozenset({"text"}), user_approved=True,
                bundled=False, paid=False)
    base.update(overrides)
    return SimpleNamespace(**base)


def capabilities(**overrides):
    base = dict(model_id="model-a", input_types=frozenset({"text"}),
                context_window=8192, max_output=2048)
    base.update(overrides)
    return ModelCapabilities(**base)


def ok_payload(text="hello", *, input_tokens=10, output_tokens=5):
    return {
        "choices": [{"message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": input_tokens,
                  "completion_tokens": output_tokens},
    }


class ScriptedTransport:
    """Returns/raises scripted outcomes; records every call. Never uses network."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, request):
        self.calls.append(copy.deepcopy(request))
        if not self.outcomes:
            raise AssertionError("unexpected transport call")
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return outcome(request)
        return outcome


class FakeCancel:
    def __init__(self, cancelled=False):
        self._cancelled = cancelled

    def is_set(self):
        return self._cancelled

    def set(self):
        self._cancelled = True


class SleepRecorder:
    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


# ---------------------------------------------------------------------------
# Confirmed defects (each failed before the fix)
# ---------------------------------------------------------------------------


def test_approval_gate_cannot_be_bypassed_by_string_false():
    with pytest.raises(ProviderContractError, match="boolean"):
        provider_from_dict({
            "id": "alpha", "base_url": "https://alpha.example.test/v1",
            "protocol": "openai-chat-completions", "models": ["model-a"],
            "user_approved": "false",
        })


@pytest.mark.parametrize("field,value", [
    ("user_approved", 1),
    ("user_approved", "true"),
    ("paid", 0),
    ("paid", "false"),
    ("bundled", ""),
    ("bundled", 1),
])
def test_registration_boolean_fields_are_strict(field, value):
    data = {
        "id": "alpha", "base_url": "https://alpha.example.test/v1",
        "protocol": "openai-chat-completions", "models": ["model-a"],
        "user_approved": True,
    }
    data[field] = value
    with pytest.raises(ProviderContractError, match=field):
        provider_from_dict(data)


def test_endpoint_rejects_crlf_and_embedded_whitespace():
    for url in ("https://alpha.example.test/v1\r\nX-Evil: 1",
                "https://alpha.example.test/v1 token",
                "https://alpha.example.test/\tv1"):
        with pytest.raises(ProviderContractError, match="https"):
            descriptor(base_url=url)


def test_catalog_get_provider_does_not_expose_the_live_cache():
    first = provider_catalog.get_provider("302ai")
    assert first is not None
    first["models"].append("INJECTED-MODEL")
    first["id"] = "corrupted"
    again = provider_catalog.get_provider("302ai")
    assert "INJECTED-MODEL" not in provider_catalog.model_ids("302ai")
    assert again["id"] == "302ai"
    assert again is not first


def _catalog_file(tmp_path, **overrides):
    doc = {
        "schema_version": "1", "catalog_version": "test",
        "providers": {"alpha": {"id": "alpha", "models": ["m1", "m2"],
                                "api": "https://alpha.example.test"}},
        "provider_count": 1, "model_count": 2,
        "source": {"name": "test", "url": "https://example.test",
                   "license": "MIT"},
    }
    doc.update(overrides)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


@pytest.mark.parametrize("bad_models", ["ab", 7, None, [1, 2]])
def test_catalog_rejects_malformed_models_field(tmp_path, bad_models):
    path = _catalog_file(tmp_path, providers={
        "alpha": {"id": "alpha", "models": bad_models}})
    with pytest.raises(provider_catalog.CatalogError, match="models"):
        provider_catalog.model_ids("alpha", path=path)


def test_catalog_rejects_inconsistent_counts_and_schema(tmp_path):
    path = _catalog_file(tmp_path, provider_count=99)
    with pytest.raises(provider_catalog.CatalogError, match="provider_count"):
        provider_catalog.load_catalog(path=path)
    path = _catalog_file(tmp_path, model_count=99)
    with pytest.raises(provider_catalog.CatalogError, match="model_count"):
        provider_catalog.load_catalog(path=path)
    path = _catalog_file(tmp_path, schema_version="999")
    with pytest.raises(provider_catalog.CatalogError, match="schema_version"):
        provider_catalog.load_catalog(path=path)


def test_catalog_entry_must_be_an_object_with_a_matching_id(tmp_path):
    path = _catalog_file(tmp_path, providers={"alpha": {"id": "other", "models": []}})
    with pytest.raises(provider_catalog.CatalogError, match="id"):
        provider_catalog.provider_ids(path=path)


# ---------------------------------------------------------------------------
# Taxonomy and normalization
# ---------------------------------------------------------------------------


def test_taxonomy_retry_and_fallback_sets_are_disjoint_on_security_errors():
    assert CATEGORIES >= RETRYABLE_CATEGORIES | FALLBACK_CATEGORIES
    for category in (CATEGORY_AUTH, CATEGORY_CREDENTIAL):
        assert category not in RETRYABLE_CATEGORIES
        assert category not in FALLBACK_CATEGORIES
    assert CATEGORY_SERVER in RETRYABLE_CATEGORIES
    assert CATEGORY_RATE_LIMIT in FALLBACK_CATEGORIES


@pytest.mark.parametrize("status,category,retryable", [
    (401, CATEGORY_AUTH, False),
    (403, CATEGORY_ORG, False),
    (404, CATEGORY_MODEL_NOT_FOUND, False),
    (422, CATEGORY_INVALID, False),
    (429, CATEGORY_RATE_LIMIT, True),
    (500, CATEGORY_SERVER, True),
    (503, CATEGORY_UNAVAILABLE, True),
])
def test_http_error_normalization_never_echoes_body(status, category, retryable):
    failure = classify_status(status, payload={
        "error": {"message": "leaked " + FAKE_SECRET}})
    assert failure.category == category
    assert failure.retryable is retryable
    assert failure.status == status
    assert failure.message == f"http {status} {category}"
    assert FAKE_SECRET not in str(failure.to_dict())
    assert not any("leaked" in value for value in failure.to_dict().values()
                   if isinstance(value, str))


def test_payload_error_classification_detects_context_limit_without_echoing():
    failure = classify_payload({
        "error": {"code": "context_length_exceeded",
                  "message": "secret " + FAKE_SECRET}})
    assert failure is not None
    assert failure.category == CATEGORY_CONTEXT_LIMIT
    assert failure.retryable is False
    assert FAKE_SECRET not in str(failure.to_dict())


def test_extract_retry_after_is_bounded_and_type_safe():
    assert extract_retry_after({"retry_after": 0.01}) == 0.01
    assert extract_retry_after({"error": {"retry_after_ms": 500}}) == 0.5
    assert extract_retry_after({}, {"Retry-After": "2"}) == 2.0
    assert extract_retry_after({"retry_after": 10 ** 9}) == 60.0
    assert extract_retry_after({"retry_after": -4}) == 0.0
    assert extract_retry_after({"retry_after": True}) is None
    assert extract_retry_after({"retry_after": "nonsense"}) is None


def test_response_normalization_extracts_usage_and_tool_calls():
    response = normalize_response({
        "choices": [{"message": {
            "content": "done",
            "tool_calls": [{"function": {"name": "calc", "arguments": '{"x": 1}'}}],
        }, "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7,
                  "prompt_tokens_details": {"cached_tokens": 4},
                  "completion_tokens_details": {"reasoning_tokens": 3}},
    })
    assert isinstance(response, NormalizedResponse)
    assert response.text == "done"
    assert response.tool_calls == ({"name": "calc", "arguments": {"x": 1}},)
    assert response.stop_reason == "tool_calls"
    assert response.usage == UsageMetadata(12, 7, 4, 0, 3)
    assert response.to_dict()["usage"]["input_tokens"] == 12


def test_normalize_response_refuses_malformed_payloads_without_echoing_them():
    with pytest.raises(ProviderTransportError) as exc:
        normalize_response({"unexpected": FAKE_SECRET})
    assert exc.value.category == CATEGORY_MALFORMED
    assert FAKE_SECRET not in str(exc.value)
    with pytest.raises(ProviderTransportError):
        normalize_response("not a mapping")
    with pytest.raises(ProviderTransportError):
        normalize_response({"choices": []})


def test_merge_usage_sums_all_known_fields_and_rejects_bad_input():
    total = merge_usage(UsageMetadata(1, 2, 3, 4, 5), UsageMetadata(10, 20, 30, 40, 50))
    assert total == UsageMetadata(11, 22, 33, 44, 55)
    with pytest.raises(TypeError):
        merge_usage(UsageMetadata(), {"input_tokens": 1})


def test_redact_message_scrubs_fake_secret_and_common_token_shapes():
    message = (f"key {FAKE_SECRET} bearer Bearer abc.def-1234567890 "
               "openai sk-" + "A1B2C3D4E5F6G7H8I9J0")
    safe = redact_message(message, [FAKE_SECRET])
    assert FAKE_SECRET not in safe
    assert "abc.def" not in safe
    assert "[REDACTED]" in safe
    assert len(redact_message("x" * 10000)) <= 600


def test_request_normalization_drops_credentials_and_preserves_useful_fields():
    request = {
        "model": "model-a", "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 100, "api_key": FAKE_SECRET,
        "metadata": {"authorization": "Bearer " + FAKE_SECRET},
    }
    result = normalize_request(capabilities(), request)
    assert result.request["max_tokens"] == 100
    assert result.request["messages"] == request["messages"]
    assert "api_key" not in result.request
    assert "authorization" not in json.dumps(result.request)
    assert FAKE_SECRET not in json.dumps(result.to_dict() if hasattr(result, "to_dict")
                                         else result.__dict__)
    assert any("credential" in note.lower() for note in result.adjustments)


# ---------------------------------------------------------------------------
# Failure transports: auth, credentials, timeout, connection, HTTP, rate limit
# ---------------------------------------------------------------------------


def test_auth_failure_is_not_retried_and_never_discloses_secret():
    transport = ScriptedTransport(
        ProviderTransportError("401 bad " + FAKE_SECRET,
                               category=CATEGORY_AUTH, status=401))
    result = execute_request(cfg(fallbacks=("backup",)),
                             {"model": "model-a", "messages": [{"role": "user",
                              "content": "hi"}]},
                             transport=transport, secrets=[FAKE_SECRET])
    assert isinstance(result, ProviderResult)
    assert result.status == "failed"
    assert result.error.category == CATEGORY_AUTH
    assert len(result.attempts) == 1
    assert result.fallbacks_used == ()
    assert FAKE_SECRET not in json.dumps(result.to_dict())
    assert len(transport.calls) == 1


def test_invalid_credentials_are_not_fallback_eligible():
    transport = ScriptedTransport(
        ProviderTransportError("invalid credential " + FAKE_SECRET,
                               category=CATEGORY_CREDENTIAL))
    result = execute_request(cfg(fallbacks=("backup",)),
                             {"model": "model-a", "messages": []},
                             transport=transport, secrets=[FAKE_SECRET])
    assert result.error.category == CATEGORY_CREDENTIAL
    assert result.fallbacks_used == ()
    assert len(transport.calls) == 1


def test_timeout_is_retried_with_deterministic_exponential_backoff():
    transport = ScriptedTransport(TimeoutError("timed out"), TimeoutError("timed out"),
                                  ok_payload())
    sleeper = SleepRecorder()
    result = execute_request(cfg(), {"model": "model-a", "messages": []},
                             transport=transport, sleep=sleeper)
    assert result.status == "ok"
    assert result.response.text == "hello"
    assert len(result.attempts) == 3
    assert sleeper.delays == [0.25, 0.5]
    assert result.backoff_seconds == (0.25, 0.5)
    assert all(call["timeout_seconds"] == 60.0 for call in transport.calls)


def test_connection_error_is_retried_then_reported_without_raw_reason():
    transport = ScriptedTransport(ConnectionError("dial " + FAKE_SECRET + " failed"))
    sleeper = SleepRecorder()
    result = execute_request(cfg(), {"model": "model-a", "messages": []},
                             transport=transport, secrets=[FAKE_SECRET], sleep=sleeper)
    assert result.status == "failed"
    assert result.error.category == CATEGORY_CONNECTION
    assert result.error.retryable is True
    assert len(result.attempts) == 3
    assert sleeper.delays == [0.25, 0.5]
    assert FAKE_SECRET not in json.dumps(result.to_dict())


def test_rate_limit_retry_after_is_capped_by_configured_max_backoff():
    transport = ScriptedTransport(
        TransportResponse(429, {"error": {"type": "rate_limit_error",
                                          "retry_after": 120}}), ok_payload())
    sleeper = SleepRecorder()
    result = execute_request(cfg(), {"model": "model-a", "messages": []},
                             transport=transport, sleep=sleeper)
    assert result.status == "ok"
    assert result.attempts[0].category == CATEGORY_RATE_LIMIT
    assert sleeper.delays == [30.0]


def test_small_retry_after_is_honoured_exactly():
    decision = retry_schedule(cfg(), classify_status(
        429, payload={"retry_after": 0.01}), 1)
    assert decision.retry is True
    assert decision.delay_seconds == 0.01


def test_context_limit_error_never_retries_or_falls_back():
    transport = ScriptedTransport(TransportResponse(400, {
        "error": {"code": "context_length_exceeded",
                  "message": "secret " + FAKE_SECRET}}))
    result = execute_request(cfg(fallbacks=("backup",)),
                             {"model": "model-a", "messages": []},
                             transport=transport, secrets=[FAKE_SECRET])
    assert result.error.category == CATEGORY_CONTEXT_LIMIT
    assert result.error.retryable is False
    assert len(result.attempts) == 1
    assert result.fallbacks_used == ()
    assert FAKE_SECRET not in json.dumps(result.to_dict())


def test_provider_unavailable_is_not_fallback_eligible_without_explicit_config():
    transport = ScriptedTransport(
        ProviderTransportError("down", category=CATEGORY_UNAVAILABLE))
    result = execute_request(cfg(), {"model": "model-a", "messages": []},
                             transport=transport)
    assert result.error.category == CATEGORY_UNAVAILABLE
    assert len(result.attempts) == 3
    assert result.fallbacks_used == ()


def test_provider_unavailable_falls_back_only_once_when_explicitly_configured():
    transport = ScriptedTransport(
        ProviderTransportError("down", category=CATEGORY_UNAVAILABLE),
        ok_payload("from backup"))
    result = execute_request(cfg(fallbacks=("backup",), max_attempts=1),
                             {"model": "model-a", "messages": []},
                             transport=transport)
    assert result.status == "ok"
    assert result.response.text == "from backup"
    assert result.provider == "backup"
    assert result.fallbacks_used == ("backup",)
    assert transport.calls[0]["provider"] == "alpha"
    assert transport.calls[1]["provider"] == "backup"


# ---------------------------------------------------------------------------
# Cancellation, streaming, usage
# ---------------------------------------------------------------------------


def test_cancellation_before_first_attempt_never_calls_transport():
    transport = ScriptedTransport(ok_payload())
    result = execute_request(cfg(), {"model": "model-a", "messages": []},
                             transport=transport, cancel=FakeCancel(True))
    assert result.status == "cancelled"
    assert result.attempts == ()
    assert transport.calls == []


def test_cancellation_mid_attempt_returns_cancelled_not_fake_success():
    def interrupted(_request):
        raise ProviderCancelled()
    result = execute_request(cfg(), {"model": "model-a", "messages": []},
                             transport=ScriptedTransport(interrupted))
    assert result.status == "cancelled"
    assert result.response is None
    assert result.error is None


def test_streaming_success_accumulates_text_usage_and_stop_reason():
    events = [
        {"event": "text_delta", "text": "hel"},
        {"event": "text_delta", "text": "lo"},
        {"event": "usage", "usage": {"prompt_tokens": 4, "completion_tokens": 2}},
        {"event": "stop", "stop_reason": "stop"},
    ]
    result = execute_stream(cfg(), {"model": "model-a", "messages": []},
                            transport=ScriptedTransport(events))
    assert result.status == "ok"
    assert result.response.text == "hello"
    assert result.response.usage.input_tokens == 4
    assert result.response.usage.output_tokens == 2
    assert result.response.stop_reason == "stop"
    assert result.fallbacks_used == ()


def test_streaming_partial_failure_preserves_text_without_retry_or_fallback():
    def streaming_then_failure(_request):
        def chunks():
            yield {"event": "text_delta", "text": "partial "}
            yield {"event": "text_delta", "text": "answer"}
            raise ConnectionError("wire " + FAKE_SECRET + " dropped")
        return chunks()

    transport = ScriptedTransport(streaming_then_failure)
    result = execute_stream(cfg(fallbacks=("backup",)),
                            {"model": "model-a", "messages": []},
                            transport=transport, secrets=[FAKE_SECRET])
    assert result.status == "partial_failed"
    assert result.response.text == "partial answer"
    assert result.error.category == CATEGORY_CONNECTION
    assert len(result.attempts) == 1
    assert result.fallbacks_used == ()
    assert len(transport.calls) == 1
    assert FAKE_SECRET not in json.dumps(result.to_dict())


def test_stream_cancellation_keeps_partial_text_and_stops_immediately():
    cancel = FakeCancel()

    def chunks(_request):
        yield {"event": "text_delta", "text": "before stop"}
        cancel.set()
        yield {"event": "text_delta", "text": "MUST NOT APPEAR"}

    result = execute_stream(cfg(fallbacks=("backup",)),
                            {"model": "model-a", "messages": []},
                            transport=ScriptedTransport(chunks), cancel=cancel)
    assert result.status == "cancelled"
    assert result.response.text == "before stop"
    assert result.fallbacks_used == ()


def test_stream_error_event_before_content_can_retry_and_fallback():
    events = [{"event": "error", "category": CATEGORY_UNAVAILABLE,
               "message": "upstream unavailable"}]
    transport = ScriptedTransport(events, [
        {"event": "text_delta", "text": "backup ok"},
        {"event": "stop", "stop_reason": "stop"},
    ])
    result = execute_stream(cfg(fallbacks=("backup",), max_attempts=1),
                            {"model": "model-a", "messages": []},
                            transport=transport)
    assert result.status == "ok"
    assert result.response.text == "backup ok"
    assert result.fallbacks_used == ("backup",)


def test_sanitize_event_redacts_strings_and_ignores_unknown_kinds():
    event = sanitize_event({"event": "text_delta", "text": FAKE_SECRET}, [FAKE_SECRET])
    assert event["kind"] == "text_delta"
    assert FAKE_SECRET not in json.dumps(event)
    assert sanitize_event({"event": "mystery"})["kind"] == "ignored"


# ---------------------------------------------------------------------------
# Config validation: approval, paid paths, local operation
# ---------------------------------------------------------------------------


def test_no_provider_is_required_for_local_operation():
    config = ExecutionConfig()
    assert validate_execution_config(config) == ()
    transport = ScriptedTransport()
    result = execute_request(config, {"model": "model-a", "messages": []},
                             transport=transport)
    assert result.status == "no_provider"
    assert result.attempts == ()
    assert transport.calls == []


def test_fallback_validation_requires_explicit_approved_non_paid_providers():
    registry = ProviderRegistry()
    registry.add(descriptor("alpha"))
    unregistered = validate_execution_config(cfg(fallbacks=("backup",)),
                                              registry=registry)
    assert any("not registered" in problem for problem in unregistered)
    unapproved = validate_execution_config(
        cfg(fallbacks=("backup",)),
        descriptors={"alpha": descriptor(),
                     "backup": stub_descriptor("backup", user_approved=False)})
    assert any("approval" in problem for problem in unapproved)
    paid = validate_execution_config(
        cfg(fallbacks=("backup",)),
        descriptors={"alpha": descriptor(),
                     "backup": stub_descriptor("backup", paid=True)})
    assert any("paid" in problem for problem in paid)


def test_fallback_validation_rejects_duplicate_self_and_unregistered_names():
    registry = ProviderRegistry()
    registry.add(descriptor("alpha"))
    registry.add(descriptor("backup"))
    problems = validate_execution_config(
        cfg(fallbacks=("alpha", "backup", "backup")), registry=registry)
    assert any("self" in problem for problem in problems)
    assert any("duplicate" in problem for problem in problems)
    assert validate_execution_config(cfg(fallbacks=("ghost",)), registry=registry)


def test_config_validation_rejects_unbounded_timeouts_and_attempts():
    problems = validate_execution_config(cfg(max_attempts=99, timeout_seconds=-1,
                                             base_backoff_seconds=-1))
    assert len(problems) >= 3
    assert any("max_attempts" in problem for problem in problems)
    assert any("timeout" in problem for problem in problems)
    assert any("backoff" in problem for problem in problems)


def test_paid_or_bundled_primary_is_rejected_before_any_transport_call():
    transport = ScriptedTransport()
    paid = stub_descriptor(paid=True)
    result = execute_request(cfg(), {"model": "model-a", "messages": []},
                             transport=transport, descriptors={"alpha": paid})
    assert result.status == "failed"
    assert result.error.category == CATEGORY_INVALID
    assert any("paid" in problem for problem in validate_execution_config(
        cfg(), descriptors={"alpha": paid}))
    assert any("bundled" in problem for problem in validate_execution_config(
        cfg(), descriptors={"alpha": stub_descriptor(bundled=True)}))
    assert transport.calls == []


def test_model_resolution_checks_model_against_registered_descriptor():
    problems = validate_execution_config(
        cfg(), model="not-a-model",
        descriptors={"alpha": descriptor()})
    assert any("model" in problem for problem in problems)
    assert validate_execution_config(
        cfg(), model="model-a", descriptors={"alpha": descriptor()}) == ()


def test_image_request_is_refused_before_sending():
    transport = ScriptedTransport()
    request = {"model": "model-a", "messages": [{"role": "user", "content": [
        {"type": "text", "text": "what is this"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
    ]}]}
    result = execute_request(cfg(), request, transport=transport,
                             capabilities=capabilities())
    assert result.error.category == CATEGORY_INVALID
    assert "image" in result.error.message.lower()
    assert transport.calls == []


def test_classify_exception_handles_plain_stdlib_exceptions():
    assert classify_exception(TimeoutError("slow")).category == CATEGORY_TIMEOUT
    assert classify_exception(ConnectionError("refused")).category == CATEGORY_CONNECTION
    assert classify_exception(ProviderCancelled()).category == "cancelled"
    assert classify_exception(RuntimeError("odd")).retryable is False


def test_failure_and_result_serialization_contain_no_exception_objects():
    failure = ProviderFailure(CATEGORY_AUTH, http_message := "http 401 authentication_failed",
                              401, False)
    assert failure.to_dict()["message"] == http_message
    result = execute_request(cfg(), {"model": "model-a", "messages": []},
                             transport=ScriptedTransport(ok_payload()))
    data = result.to_dict()
    assert set(data) == {"status", "provider", "model", "response", "error",
                         "attempts", "fallbacks_used", "backoff_seconds"}
    assert isinstance(data["attempts"], list)
    assert json.dumps(data)
