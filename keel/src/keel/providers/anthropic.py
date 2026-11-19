"""Anthropic Messages API adapter (optional provider; opt-in).

POST {base}/v1/messages, stream=true. Auth: x-api-key + anthropic-version.
Not configured as a default; enable with --provider anthropic or
KEEL_ANTHROPIC_API_KEY. See licensing-and-provenance-review.md OPEN-Q1.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from .base import (CapabilityRecord, ProviderError, ProviderRequest, UsageRecord,
                   anthropic_tools, http_transport, parse_sse_lines,
                   status_to_category, RETRY_UNKNOWN, image_block)
from .openai_compatible import _iter_text_lines


class AnthropicAdapter:
    def __init__(self, cap: CapabilityRecord, *, api_key: str | None,
                 transport=None):
        self.cap = cap
        self.api_key = api_key or ""
        self._transport = transport or http_transport

    @classmethod
    def from_env(cls, cap: CapabilityRecord, *, transport=None) -> "AnthropicAdapter":
        import os
        return cls(cap, api_key=os.environ.get(cap.env_var, ""),
                   transport=transport)

    def describe(self) -> CapabilityRecord:
        return self.cap

    def complete(self, request: ProviderRequest) -> Iterator[dict]:
        messages = _to_anthropic_messages(request.messages)
        body: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "stream": True,
            "messages": messages,
        }
        if request.system:
            body["system"] = request.system
        if request.tools:
            body["tools"] = anthropic_tools(request.tools)
        if not self.api_key:
            raise ProviderError(f"{self.cap.name}: no API key (set {self.cap.env_var})",
                                RETRY_UNKNOWN)
        try:
            status, _headers, stream = self._transport({
                "method": "POST",
                "url": f"{self.cap.base_url.rstrip('/')}/messages",
                "headers": {"x-api-key": self.api_key,
                            "anthropic-version": "2023-06-01",
                            "Content-Type": "application/json"},
                "body_json": body,
                "timeout": 120,
            })
        except ProviderError:
            raise
        if status and status >= 400:
            category, retryable = status_to_category(status)
            raise ProviderError(f"http {status}", category, status, retryable)

        lines = _iter_text_lines(stream)
        index = 0
        usage: UsageRecord | None = None
        stop_reason: str | None = None
        tool_args: dict[int, str] = {}

        for obj in parse_sse_lines(lines):
            event = obj.get("type")
            if event == "message_start":
                msg = obj.get("message") or {}
                u = msg.get("usage") or {}
                usage = UsageRecord(
                    input_tokens=u.get("input_tokens", 0),
                    output_tokens=u.get("output_tokens", 0),
                    cache_read_input_tokens=u.get("cache_read_input_tokens", 0),
                    cache_creation_input_tokens=u.get(
                        "cache_creation_input_tokens", 0),
                )
            elif event == "content_block_start":
                index = obj.get("index", 0)
                block = obj.get("content_block") or {}
                btype = block.get("type")
                if btype == "text":
                    yield {"event": "block_start", "index": index,
                           "block": {"type": "text", "text": ""}}
                elif btype == "tool_use":
                    tool_args[index] = ""
                    yield {"event": "block_start", "index": index,
                           "block": {"type": "tool_use",
                                     "id": block.get("id", ""),
                                     "name": block.get("name", ""),
                                     "input": {}}}
                elif btype == "thinking":
                    yield {"event": "block_start", "index": index,
                           "block": {"type": "thinking", "thinking": ""}}
            elif event == "content_block_delta":
                index = obj.get("index", 0)
                delta = obj.get("delta") or {}
                dtype = delta.get("type")
                if dtype == "text_delta":
                    yield {"event": "text_delta", "index": index,
                           "text": delta.get("text", "")}
                elif dtype == "thinking_delta":
                    yield {"event": "thinking_delta", "index": index,
                           "text": delta.get("thinking", "")}
                elif dtype == "input_json_delta":
                    tool_args[index] = tool_args.get(index, "") + delta.get(
                        "partial_json", "")
            elif event == "content_block_stop":
                index = obj.get("index", 0)
                if index in tool_args:
                    raw = tool_args.pop(index)
                    try:
                        parsed = json.loads(raw) if raw.strip() else {}
                    except json.JSONDecodeError:
                        parsed = {"_raw": raw}
                    yield {"event": "tool_input", "index": index,
                           "input": parsed if isinstance(parsed, dict)
                           else {"_raw": raw}}
                yield {"event": "block_stop", "index": index}
            elif event == "message_delta":
                delta = obj.get("delta") or {}
                stop_reason = delta.get("stop_reason", stop_reason)
                u = obj.get("usage") or {}
                if u and usage is not None:
                    usage.output_tokens = u.get("output_tokens",
                                                usage.output_tokens)
            elif event == "message_stop":
                pass
            elif event == "error":
                err = obj.get("error") or {}
                err_type = err.get("type", "unknown")
                category = {"overloaded_error": "overloaded",
                            "rate_limit_error": "rate_limit",
                            "authentication_error": "authentication_failed",
                            "permission_error": "organization_not_allowed",
                            "billing_error": "billing_error",
                            "invalid_request_error": "invalid_request",
                            "not_found_error": "model_not_found",
                            "api_error": "server_error"}.get(err_type, "unknown")
                raise ProviderError(err.get("message", err_type), category,
                                    retryable=category in
                                    ("rate_limit", "overloaded", "server_error"))

        if usage is not None:
            yield {"event": "usage", "usage": usage}
        yield {"event": "message_stop",
               "stop_reason": stop_reason or "end_turn"}


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")
        blocks: list[dict] = []
        if isinstance(content, str):
            if content:
                blocks.append({"type": "text", "text": content})
        else:
            for block in content:
                btype = block.get("type")
                if btype == "text":
                    blocks.append({"type": "text", "text": block["text"]})
                elif btype == "thinking":
                    blocks.append({"type": "thinking",
                                   "thinking": block.get("thinking", "")})
                elif btype == "image":
                    img = image_block(block)
                    if img:
                        mime, data = img
                        blocks.append({"type": "image",
                                       "source": {"type": "base64",
                                                  "media_type": mime,
                                                  "data": data}})
                elif btype == "tool_use":
                    blocks.append({"type": "tool_use",
                                   "id": block.get("id", "call_0"),
                                   "name": block["name"],
                                   "input": block.get("input", {})})
                elif btype == "tool_result":
                    blocks.append({"type": "tool_result",
                                   "tool_use_id": block.get("tool_use_id", ""),
                                   "content": block.get("content", "")})
        if blocks:
            out.append({"role": role, "content": blocks})
    return out
