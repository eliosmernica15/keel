"""Deterministic fake transport for the v2 runtime acceptance tests.

The transport is injected at the network edge: real adapter, real Session,
real tool registry — only the HTTP round-trip is faked.
"""

import json


def split_text(text, chunk=12):
    return [text[i:i + chunk] for i in range(0, len(text), chunk)] or [text]


def text_turn(text, *, usage=(10, 4), finish="stop"):
    objs = [{"choices": [{"delta": {"content": part}, "finish_reason": None}]}
            for part in split_text(text)]
    objs.append({"choices": [{"delta": {}, "finish_reason": finish}]})
    objs.append({"usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
                 "choices": []})
    return objs


def tool_call_turn(tool_name, tool_input, *, call_id="call_1", usage=(10, 4)):
    objs = [
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": call_id,
             "function": {"name": tool_name, "arguments": ""}}]},
            "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": json.dumps(tool_input)}}]},
            "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        {"usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
         "choices": []},
    ]
    return objs


def error_transport(status, body=None):
    from keel.providers.base import ProviderError, status_to_category

    def transport(request):
        category, retryable = status_to_category(status)
        raise ProviderError((body or f"http {status}"), category, status, retryable)

    return transport


def openai_sse(objs):
    out = b""
    for obj in objs:
        out += b"data: " + json.dumps(obj).encode() + b"\n\n"
    out += b"data: [DONE]\n\n"
    return out


def wait_for(predicate, timeout=10.0, interval=0.025):
    import time as _time
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        _time.sleep(interval)
    return None


def make_fake_adapter(monkeypatch, script_turns):
    """Monkeypatch adapter construction to serve scripted SSE.

    `script_turns` is a list of turns; each turn is a list of SSE data
    objects. The adapter built for ANY provider/model uses a transport
    that pops one scripted body per request. Real adapter, real Session,
    real tools — only the network edge is fake.
    """
    from keel.providers import registry

    # resolve_chain() returns [] when no provider keys are configured,
    # so the fake must come with a throwaway key or it never gets built
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "fake-key-not-real")

    class _FakeTransport:
        def __init__(self, bodies):
            self.bodies = list(bodies)

        def __call__(self, request):
            return 200, {}, iter([self.bodies.pop(0)])

    def fake_build_adapter(name, *, api_key=None, transport=None):
        return registry.OpenAICompatibleAdapter(
            registry._PROVIDERS["openrouter"],
            api_key=api_key or "fake-key-not-real",
            transport=_FakeTransport([openai_sse(turn) for turn in script_turns]),
        )

    monkeypatch.setattr(registry, "build_adapter", fake_build_adapter)
    return None
