"""Ollama local adapter: explicit opt-in, no key, fake HTTP transport only.

Every test replaces the HTTP boundary with an in-process fake; no live network
or installed Ollama daemon is touched.
"""

from __future__ import annotations

import json

import pytest

from keel.providers import ollama, registry
from keel.providers.base import ProviderError, ProviderRequest
from keel.providers.model_client import ProviderModelClient

READ_TOOL = [{"name": "read_file", "description": "read",
              "input_schema": {"type": "object",
                               "properties": {"path": {"type": "string"}},
                               "required": ["path"]}}]

STREAM = (
    b'data: {"choices":[{"delta":{"content":"hel"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_local",'
    b'"function":{"name":"read_file","arguments":"{\\"path\\": "}}]}}]}\n\n'
    b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":'
    b'{"arguments":"\\"/tmp/x\\"}"}}]}}]}\n\n'
    b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
    b'data: {"usage":{"prompt_tokens":10,"completion_tokens":4},"choices":[]}\n\n'
    b'data: [DONE]\n\n'
)


def _transport(responses):
    """Return (transport, calls); responses is a list of (status, chunks)."""
    remaining = list(responses)
    calls: list[dict] = []

    def transport(request):
        calls.append(request)
        status, chunks = remaining.pop(0)
        if isinstance(status, Exception):
            raise status
        return status, {}, iter(chunks)

    return transport, calls


def _tags(*names):
    return json.dumps({"models": [{"name": n} for n in names]}).encode("utf-8")


@pytest.fixture
def local_capability(monkeypatch):
    """Make capability construction deterministic even with host env vars."""
    for var in ("KEEL_OLLAMA_BASE_URL", "KEEL_OLLAMA_MODEL"):
        monkeypatch.delenv(var, raising=False)
    cap = ollama.make_capability()
    monkeypatch.setitem(registry._LOCAL_PROVIDERS, "ollama", cap)
    return cap


def test_discovery_success_uses_root_api_tags_with_timeout(local_capability):
    transport, calls = _transport([(200, [_tags("qwen2.5:7b", "llama3.2:latest")])])

    names = ollama.discover_models(transport=transport)

    assert names == ["llama3.2:latest", "qwen2.5:7b"]
    request = calls[0]
    assert request["method"] == "GET"
    assert request["url"] == "http://127.0.0.1:11434/api/tags"
    assert request["timeout"] == ollama.DISCOVERY_TIMEOUT
    assert "Authorization" not in request["headers"]
    assert "body_json" not in request



def test_discovery_failure_is_graceful_and_invents_no_model(local_capability):
    cases = [
        (OSError("daemon offline"), [b""]),
        (500, [b'{"error":"oops"}']),
        (200, [b'not-json']),
    ]
    for status, chunks in cases:
        transport, calls = _transport([(status, chunks)])
        assert ollama.discover_models(transport=transport) == []
        assert calls[0]["timeout"] == ollama.DISCOVERY_TIMEOUT

    strict_transport, _ = _transport([(OSError("secret://user:pw@host"), [b""])])
    with pytest.raises(ProviderError) as exc:
        ollama.discover_models(transport=strict_transport, strict=True)
    assert "secret://" not in str(exc.value)
    assert "user:pw" not in str(exc.value)



def test_explicit_selection_required_and_no_auto_network(monkeypatch,
                                                         local_capability):
    monkeypatch.setattr(registry, "_key_for", lambda cap: "")
    for var in ("KEEL_OPENROUTER_API_KEY", "KEEL_GOOGLE_API_KEY",
                "KEEL_NVIDIA_API_KEY", "KEEL_COMPAT_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    def no_network(_request):
        raise AssertionError("auto resolution must not contact Ollama")

    monkeypatch.setattr(ollama, "http_transport", no_network)
    assert [c.name for c in registry.resolve_chain("auto")] == []
    with pytest.raises(ProviderError):
        registry.resolve_provider_model(
            "llama3.2", provider_config={"defaultProvider": "auto"})
    assert [c.name for c in registry.resolve_chain("ollama")] == ["ollama"]
    assert registry.capability("ollama") is not None
    assert "ollama" not in {p["name"] for p in registry.list_providers()}

    resolved = registry.resolve_provider_model(
        "ollama/llama3.2", provider_config={"defaultProvider": "auto"})
    assert resolved["provider"] == "ollama"
    assert resolved["model"] == "llama3.2"
    assert resolved["qualified"] == "ollama/llama3.2"
    with pytest.raises(ProviderError):
        registry.resolve_provider_model(
            "ollama", provider_config={"defaultProvider": "auto"})



def test_streaming_chat_completions_and_tool_calls(local_capability):
    transport, calls = _transport([(200, [STREAM])])
    adapter = registry.build_adapter("ollama", api_key="must-not-be-sent",
                                     transport=transport)
    client = ProviderModelClient(adapter, model="llama3.2")

    blocks = client.complete([{"role": "user", "content": "hi"}], READ_TOOL)

    assert [b["type"] for b in blocks] == ["text", "tool_use"]
    assert blocks[0]["text"] == "hello"
    assert blocks[1]["name"] == "read_file"
    assert blocks[1]["input"] == {"path": "/tmp/x"}
    assert blocks[1]["id"] == "call_local"
    assert client.total_usage.input_tokens == 10
    assert client.total_usage.output_tokens == 4
    assert client.last_stop_reason == "tool_use"

    request = calls[0]
    assert request["method"] == "POST"
    assert request["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    body = request["body_json"]
    assert body["model"] == "llama3.2"
    assert body["stream"] is True
    assert body["tools"] and body["messages"][0]["content"] == "hi"
    # No key, no account: nothing secret-looking is on the wire.
    assert "Authorization" not in request["headers"]
    assert "must-not-be-sent" not in json.dumps(request)



def test_no_secret_requirement_and_no_fake_fallback(local_capability):
    adapter = registry.build_adapter("ollama", transport=lambda request: None)
    assert adapter.api_key == ""
    cap = adapter.describe()
    assert cap.env_var == "" and cap.cost_basis == "free"
    assert cap.supports_tools and cap.supports_streaming
    assert not cap.supports_thinking
    assert cap.base_url == ollama.DEFAULT_BASE_URL

    transport, calls = _transport([
        (ProviderError("connection failed: refused"), [b""]),
    ])
    failing = ollama.OllamaAdapter(local_capability, transport=transport)
    with pytest.raises(ProviderError) as exc:
        list(failing.complete(
            ProviderRequest(model="llama3.2", messages=[],
                                   tools=[], max_output_tokens=16,
                                   temperature=0.0)))
    assert "no fallback model" in str(exc.value)
    assert "connection failed" not in str(exc.value)
    assert calls[0]["body_json"]["model"] == "llama3.2"
    assert "keel-fake" not in json.dumps(calls[0]["body_json"])



def test_registry_smoke_requires_a_real_model(local_capability):
    transport, calls = _transport([
        (200, [b'data: {"choices":[{"delta":{"content":"pong"},'
               b'"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n']),
    ])
    report = registry.smoke("ollama", model="llama3.2", transport=transport)
    assert report["provider"] == "ollama"
    assert report["text"] == "pong"
    assert report["key_source"] == "local"
    assert calls[0]["body_json"]["model"] == "llama3.2"
    with pytest.raises(ProviderError):
        registry.smoke("ollama", transport=transport)
