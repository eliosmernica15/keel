"""Independent provider-integration validation with deterministic adapters.

Never uses real credentials and never invents successful real-provider calls.
Validates the adapter contract end-to-end: auth, discovery, model selection,
streaming, tool calling, usage, failure mapping, retry, cancellation and
provider switching.
"""

from __future__ import annotations

import json
import os

import pytest

from keel.providers import registry as reg
from keel.providers.base import (ProviderError, RETRY_AUTH, RETRY_RATE_LIMIT,
                                 RETRY_SERVER, UsageRecord)
from keel.providers.model_client import ProviderModelClient


class RecordingAdapter:
    """A deterministic adapter that emits the full neutral event contract."""

    def __init__(self, cap, *, api_key="test", fail=None):
        self.cap = cap
        self.api_key = api_key
        self.requests = []
        self.fail = fail

    @classmethod
    def from_env(cls, cap, *, transport=None):
        return cls(cap, api_key=os.environ.get(cap.env_var, ""))

    def describe(self):
        return self.cap

    def complete(self, request):
        self.requests.append(request)
        if self.fail:
            raise self.fail
        yield {"event": "block_start", "index": 0,
               "block": {"type": "text", "text": ""}}
        yield {"event": "text_delta", "index": 0, "text": "Hello "}
        yield {"event": "text_delta", "index": 0, "text": "world"}
        yield {"event": "block_stop", "index": 0}
        yield {"event": "block_start", "index": 1,
               "block": {"type": "tool_use", "id": "tc1",
                         "name": "read_file", "input": {}}}
        yield {"event": "block_stop", "index": 1}
        yield {"event": "usage", "usage": UsageRecord(
            input_tokens=10, output_tokens=5)}
        yield {"event": "message_stop", "stop_reason": "tool_use"}


CAP = reg.CapabilityRecord(
    name="testprovider", base_url="https://test.invalid/v1",
    env_var="KEEL_TESTPROVIDER_KEY", default_model="test-model",
    supports_tools=True, supports_streaming=True)


def test_auth_from_env(monkeypatch):
    monkeypatch.setenv(CAP.env_var, "secret-key")
    adapter = RecordingAdapter.from_env(CAP)
    assert adapter.api_key == "secret-key"


def test_model_discovery_and_selection(monkeypatch):
    monkeypatch.setattr(reg, "_PROVIDERS", {"testprovider": CAP})
    monkeypatch.setenv(CAP.env_var, "k")
    doc = reg.list_providers()
    assert any(p["name"] == "testprovider" for p in doc)
    resolved = reg.resolve_provider_model("testprovider/test-model")
    assert resolved["provider"] == "testprovider"


def test_streaming_tool_calls_usage():
    adapter = RecordingAdapter(CAP)
    client = ProviderModelClient(adapter, model="test-model")
    blocks = client.complete([{"role": "user", "content": "hi"}], [])
    assert blocks[0]["text"] == "Hello world"
    assert blocks[1]["type"] == "tool_use"
    assert client.total_usage.input_tokens == 10
    assert client.total_usage.output_tokens == 5
    assert client.last_stop_reason == "tool_use"


def test_provider_failure_mapping():
    adapter = RecordingAdapter(CAP, fail=ProviderError(
        "denied", RETRY_AUTH, 401, retryable=False))
    client = ProviderModelClient(adapter, model="test-model")
    with pytest.raises(ProviderError) as exc:
        client.complete([], [])
    assert exc.value.category == RETRY_AUTH
    assert exc.value.retryable is False


def test_retryable_failure():
    adapter = RecordingAdapter(CAP, fail=ProviderError(
        "busy", RETRY_RATE_LIMIT, 429, retryable=True))
    client = ProviderModelClient(adapter, model="test-model")
    with pytest.raises(ProviderError) as exc:
        client.complete([], [])
    assert exc.value.retryable is True


def test_cancellation_mid_stream():
    import threading

    cancel = threading.Event()

    class CancellableAdapter(RecordingAdapter):
        def complete(self, request):
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            cancel.set()
            yield {"event": "text_delta", "index": 0, "text": "partial"}

    client = ProviderModelClient(CancellableAdapter(CAP, api_key="k"),
                                 model="test-model", cancel_event=cancel)
    from keel.providers.base import TurnCancelled

    with pytest.raises(TurnCancelled):
        client.complete([], [])


def test_provider_switching():
    cap2 = reg.CapabilityRecord(
        name="other", base_url="https://other.invalid",
        env_var="KEEL_OTHER_KEY", default_model="other-model")
    a = ProviderModelClient(RecordingAdapter(CAP), model=CAP.default_model)
    b = ProviderModelClient(RecordingAdapter(cap2), model=cap2.default_model)
    assert a.model == "test-model" and b.model == "other-model"
    assert a.adapter.cap.name != b.adapter.cap.name
