"""OpenAI-compatible chat completions adapter.

Covers OpenRouter, NVIDIA NIM, Azure OpenAI v1 (via base_url), LiteLLM,
and self-hosted vLLM. Contract: POST {base}/chat/completions with
stream=true and stream_options.include_usage=true.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from .base import (CapabilityRecord, ProviderError, ProviderRequest, UsageRecord,
                   http_transport, openai_tools, parse_sse_lines,
                   status_to_category, RETRY_UNKNOWN)


class OpenAICompatibleAdapter:
    def __init__(self, cap: CapabilityRecord, *, api_key: str | None,
                 transport=None, http_headers: dict | None = None):
        self.cap = cap
        self.api_key = api_key or ""
        self._transport = transport or http_transport

    @classmethod
    def from_env(cls, cap: CapabilityRecord, *, env_value: str | None = None,
                 transport=None) -> "OpenAICompatibleAdapter":
        import os
        return cls(cap, api_key=env_value or os.environ.get(cap.env_var, ""),
                   transport=transport)

    def describe(self) -> CapabilityRecord:
        return self.cap

    def _headers(self) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        return headers

    def complete(self, request: ProviderRequest) -> Iterator[dict]:
        messages = _to_openai_messages(request.messages, request.system)
        body: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.tools:
            body["tools"] = openai_tools(request.tools)
        effort = getattr(request, "reasoning_effort", None)
        if effort and effort != "none":
            # OpenRouter reasoning effort; ignored by endpoints that
            # don't understand it (tools stay intact either way)
            body["reasoning"] = {"effort": effort}
        if not self.api_key:
            raise ProviderError(f"{self.cap.name}: no API key (set {self.cap.env_var})",
                                RETRY_UNKNOWN)
        try:
            status, _headers, stream = self._transport({
                "method": "POST",
                "url": f"{self.cap.base_url.rstrip('/')}/chat/completions",
                "headers": self._headers(),
                "body_json": body,
                "timeout": 120,
            })
        except ProviderError:
            raise
        if status and status >= 400:
            category, retryable = status_to_category(status)
            raise ProviderError(f"http {status}", category, status, retryable)

        lines = _iter_text_lines(stream)
        text_open = False
        text_index = 0
        tool_acc: dict[int, dict] = {}
        next_block_index = 0
        usage: UsageRecord | None = None
        finish_reason: str | None = None

        for obj in parse_sse_lines(lines):
            if "usage" in obj and obj["usage"]:
                u = obj["usage"]
                usage = UsageRecord(
                    input_tokens=u.get("prompt_tokens", 0),
                    output_tokens=u.get("completion_tokens", 0),
                )
                continue
            choices = obj.get("choices") or []
            for choice in choices:
                delta = choice.get("delta") or {}
                fr = choice.get("finish_reason")
                if fr:
                    finish_reason = fr
                if delta.get("content"):
                    if not text_open:
                        text_index = next_block_index
                        next_block_index += 1
                        text_open = True
                        yield {"event": "block_start", "index": text_index,
                               "block": {"type": "text", "text": ""}}
                    yield {"event": "text_delta", "index": text_index,
                           "text": delta["content"]}
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    acc = tool_acc.setdefault(idx, {"id": None, "name": "",
                                                    "args": ""})
                    if tc.get("id"):
                        acc["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        acc["name"] += fn["name"]
                    if fn.get("arguments"):
                        acc["args"] += fn["arguments"]

        if text_open:
            yield {"event": "block_stop", "index": text_index}

        # tool_use blocks: emit complete (arguments are only safely parseable
        # once the stream is done)
        for idx in sorted(tool_acc):
            acc = tool_acc[idx]
            try:
                parsed = json.loads(acc["args"]) if acc["args"].strip() else {}
                if not isinstance(parsed, dict):
                    parsed = {"_raw": acc["args"]}
            except json.JSONDecodeError:
                parsed = {"_raw": acc["args"]}
            block_index = next_block_index
            next_block_index += 1
            yield {"event": "block_start", "index": block_index,
                   "block": {"type": "tool_use",
                             "id": acc["id"] or f"call_{block_index}",
                             "name": acc["name"],
                             "input": parsed}}
            yield {"event": "block_stop", "index": block_index}

        if usage is not None:
            yield {"event": "usage", "usage": usage}
        stop = {"stop": "end_turn", "length": "max_tokens",
                "tool_calls": "end_turn", "stop_sequence": "end_turn"}.get(
                    finish_reason or "stop", "end_turn")
        yield {"event": "message_stop", "stop_reason": stop}


def _iter_text_lines(stream: Iterator[bytes]) -> Iterator[str]:
    buf = b""
    for chunk in stream:
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line.decode("utf-8", errors="replace")
    if buf:
        yield buf.decode("utf-8", errors="replace")


def _content_parts(content: Any):
    if isinstance(content, str):
        yield ("text", content)
        return
    for block in content:
        yield (block.get("type"), block)


def _to_openai_messages(messages: list[dict], system: str | None) -> list[dict]:
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        tool_results: list[dict] = []
        for btype, block in _content_parts(content):
            if btype == "text":
                text_parts.append(block["text"])
            elif btype == "thinking":
                continue  # thinking is not echoed back by OpenAI endpoints
            elif btype == "tool_use":
                tool_calls.append({
                    "id": block.get("id", "call_0"),
                    "type": "function",
                    "function": {"name": block["name"],
                                 "arguments": json.dumps(block.get("input", {}))},
                })
            elif btype == "tool_result":
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id", ""),
                    "content": block.get("content", ""),
                })
        if role == "assistant":
            entry: dict[str, Any] = {"role": "assistant",
                                     "content": "\n".join(text_parts) or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
        else:
            if text_parts:
                out.append({"role": role, "content": "\n".join(text_parts)})
            out.extend(tool_results)
    return out
