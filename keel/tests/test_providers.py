"""Adapter contract tests — fake transport only, no network."""

from __future__ import annotations

import json
import os

import pytest

from keel.providers import registry
from keel.providers.base import CapabilityRecord, ProviderError, ProviderRequest
from keel.providers.anthropic import AnthropicAdapter
from keel.providers.gemini import GeminiAdapter
from keel.providers.model_client import ProviderModelClient
from keel.providers.openai_compatible import OpenAICompatibleAdapter

CAP = CapabilityRecord(name="test", base_url="https://example.invalid/v1",
                       env_var="KEEL_TEST_API_KEY", default_model="test-model")


def fake_transport(sse_bytes_list):
    responses = list(sse_bytes_list)

    def transport(request):
        assert request["method"] == "POST"
        body = responses.pop(0)
        return 200, {}, iter([body])

    return transport


def _req(messages, tools=None):
    return ProviderRequest(model="test-model", messages=messages,
                           tools=tools or [], max_output_tokens=16,
                           temperature=0.0)


READ_TOOL = [{"name": "read_file", "description": "read",
              "input_schema": {"type": "object",
                              "properties": {"path": {"type": "string"}},
                              "required": ["path"]}}]

OPENAI_TURN1 = (
    b'data: {"choices":[{"delta":{"content":"listing"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_abc",'
    b'"function":{"name":"read_file","arguments":"{\\"path\\": "}}]}}]}\n\n'
    b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"/tmp/x\\"}"}}]}}]}\n\n'
    b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
    b'data: {"usage":{"prompt_tokens":10,"completion_tokens":4},"choices":[]}\n\n'
    b'data: [DONE]\n\n'
)
OPENAI_TURN2 = (
    b'data: {"choices":[{"delta":{"content":"done"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    b'data: {"usage":{"prompt_tokens":20,"completion_tokens":2},"choices":[]}\n\n'
    b'data: [DONE]\n\n'
)
GEMINI_TURN1 = (
    b'data: {"candidates":[{"content":{"parts":[{"text":"listing"}]}}]}\n\n'
    b'data: {"candidates":[{"content":{"parts":[{"functionCall":{"name":"read_file",'
    b'"args":{"path":"/tmp/x"}}}]}}]}\n\n'
    b'data: {"candidates":[{"finishReason":"STOP"}],'
    b'"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":4}}\n\n'
)
GEMINI_TURN2 = (
    b'data: {"candidates":[{"content":{"parts":[{"text":"done"}]}}]}\n\n'
    b'data: {"candidates":[{"finishReason":"STOP"}],'
    b'"usageMetadata":{"promptTokenCount":20,"candidatesTokenCount":2}}\n\n'
)
ANTHROPIC_TURN1 = (
    b'event: message_start\ndata: {"type":"message_start","message":'
    b'{"usage":{"input_tokens":10,"output_tokens":0}}}\n\n'
    b'event: content_block_start\ndata: {"type":"content_block_start",'
    b'"index":0,"content_block":{"type":"text","text":""}}\n\n'
    b'event: content_block_delta\ndata: {"type":"content_block_delta",'
    b'"index":0,"delta":{"type":"text_delta","text":"listing"}}\n\n'
    b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'
    b'event: content_block_start\ndata: {"type":"content_block_start",'
    b'"index":1,"content_block":{"type":"tool_use","id":"toolu_1",'
    b'"name":"read_file","input":{}}}\n\n'
    b'event: content_block_delta\ndata: {"type":"content_block_delta",'
    b'"index":1,"delta":{"type":"input_json_delta",'
    b'"partial_json":"{\\"path\\": \\"/tmp/x\\"}"}}\n\n'
    b'event: content_block_stop\ndata: {"type":"content_block_stop","index":1}\n\n'
    b'event: message_delta\ndata: {"type":"message_delta",'
    b'"delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":4}}\n\n'
    b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
)
ANTHROPIC_TURN2 = (
    b'event: message_start\ndata: {"type":"message_start","message":'
    b'{"usage":{"input_tokens":20,"output_tokens":0}}}\n\n'
    b'event: content_block_start\ndata: {"type":"content_block_start",'
    b'"index":0,"content_block":{"type":"text","text":""}}\n\n'
    b'event: content_block_delta\ndata: {"type":"content_block_delta",'
    b'"index":0,"delta":{"type":"text_delta","text":"done"}}\n\n'
    b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'
    b'event: message_delta\ndata: {"type":"message_delta",'
    b'"delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}\n\n'
    b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
)


def test_openai_compatible_tool_call_and_usage():
    adapter = OpenAICompatibleAdapter(
        CAP, api_key="k", transport=fake_transport([OPENAI_TURN1, OPENAI_TURN2]))
    client = ProviderModelClient(adapter, model="m")
    blocks = client.complete([{"role": "user", "content": "hi"}], READ_TOOL)
    kinds = [b["type"] for b in blocks]
    assert kinds == ["text", "tool_use"]
    assert blocks[0]["text"] == "listing"
    assert blocks[1]["name"] == "read_file"
    assert blocks[1]["input"] == {"path": "/tmp/x"}
    assert blocks[1]["id"] == "call_abc"
    assert client.total_usage.input_tokens == 10


def test_gemini_tool_call_and_usage():
    adapter = GeminiAdapter(CAP, api_key="k",
                            transport=fake_transport([GEMINI_TURN1, GEMINI_TURN2]))
    client = ProviderModelClient(adapter, model="m")
    blocks = client.complete([{"role": "user", "content": "hi"}], READ_TOOL)
    assert [b["type"] for b in blocks] == ["text", "tool_use"]
    assert blocks[1]["name"] == "read_file"
    assert blocks[1]["input"] == {"path": "/tmp/x"}
    assert client.total_usage.input_tokens == 10


def test_anthropic_tool_call_and_usage():
    adapter = AnthropicAdapter(CAP, api_key="k",
                               transport=fake_transport([ANTHROPIC_TURN1]))
    client = ProviderModelClient(adapter, model="m")
    blocks = client.complete([{"role": "user", "content": "hi"}], READ_TOOL)
    assert [b["type"] for b in blocks] == ["text", "tool_use"]
    assert blocks[1]["name"] == "read_file"
    assert blocks[1]["input"] == {"path": "/tmp/x"}
    assert client.last_stop_reason == "tool_use"
    assert client.total_usage.input_tokens == 10


def test_session_runs_tool_loop_with_provider_client(tmp_path):
    from keel.fakes import SeededRng, VirtualClock
    from keel.session import Session, SessionConfig

    target = tmp_path / "note.txt"
    target.write_text("remember this", encoding="utf-8")
    # build the turn-1 SSE inline with the real path
    args = json.dumps({"path": str(target)}).encode()
    turn1 = (
        b'data: {"choices":[{"delta":{"content":"listing"},"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_abc",'
        b'"function":{"name":"read_file","arguments":' + json.dumps(args.decode()).encode() + b'}}]}}]}\n\n'
        b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
        b'data: {"usage":{"prompt_tokens":10,"completion_tokens":4},"choices":[]}\n\n'
        b'data: [DONE]\n\n'
    )
    transport = fake_transport([turn1, OPENAI_TURN2])
    adapter = OpenAICompatibleAdapter(CAP, api_key="k", transport=transport)
    client = ProviderModelClient(adapter, model="m")

    cfg = SessionConfig(cwd=str(tmp_path), state_root=str(tmp_path / "st"),
                        bare=True, permission_mode="default",
                        session_id="22222222-2222-4222-8222-222222222222",
                        model="m", seed=0)
    session = Session(model_client=client, executor=_Executor(), config=cfg,
                      rules=((), (), ()), clock=VirtualClock(),
                      rng=SeededRng(0))
    out = session.run("read the note")
    assert out.envelope["subtype"] == "success"
    tool_result_events = [
        blk for e in out.events if e["type"] == "user"
        for blk in e["message"]["content"] if blk["type"] == "tool_result"]
    assert len(tool_result_events) == 1
    assert "remember this" in tool_result_events[0]["content"]
    assert out.envelope["usage"]["input_tokens"] == 30


class _Executor:
    def invoke(self, name, tool_input):
        with open(tool_input["path"], "r", encoding="utf-8") as fh:
            return fh.read(), {"path": tool_input["path"]}


def test_registry_resolution_order(monkeypatch):
    for var in ("KEEL_OPENROUTER_API_KEY", "KEEL_GOOGLE_API_KEY",
                "KEEL_NVIDIA_API_KEY", "KEEL_COMPAT_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert registry.resolve_chain("auto") == []
    monkeypatch.setenv("KEEL_NVIDIA_API_KEY", "k")
    assert [c.name for c in registry.resolve_chain("auto")] == ["nvidia"]
    monkeypatch.setenv("KEEL_OPENROUTER_API_KEY", "k")
    assert [c.name for c in registry.resolve_chain("auto")] == ["openrouter", "nvidia"]
    with pytest.raises(ProviderError):
        registry.resolve_chain("not-a-provider")


def test_provider_list_shape(monkeypatch, capsys):
    from keel.cli.main import main
    monkeypatch.delenv("KEEL_ANTHROPIC_API_KEY", raising=False)
    rc = main(["provider", "list"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    by_name = {row["name"]: row for row in out}
    assert by_name["anthropic"]["opt_in"] is True
    assert by_name["openrouter"]["configured"] is False
