"""Google AI Studio (Gemini API) adapter.

POST {base}/models/{model}:streamGenerateContent?alt=sse
Auth: x-goog-api-key header.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from .base import (CapabilityRecord, ProviderError, ProviderRequest, UsageRecord,
                   gemini_function_declarations, http_transport, parse_sse_lines,
                   status_to_category, RETRY_UNKNOWN, image_block)
from .openai_compatible import _iter_text_lines


class GeminiAdapter:
    def __init__(self, cap: CapabilityRecord, *, api_key: str | None,
                 transport=None):
        self.cap = cap
        self.api_key = api_key or ""
        self._transport = transport or http_transport

    @classmethod
    def from_env(cls, cap: CapabilityRecord, *, transport=None) -> "GeminiAdapter":
        import os
        return cls(cap, api_key=os.environ.get(cap.env_var, ""),
                   transport=transport)

    def describe(self) -> CapabilityRecord:
        return self.cap

    def complete(self, request: ProviderRequest) -> Iterator[dict]:
        contents = _to_gemini_contents(request.messages)
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_output_tokens,
                "temperature": request.temperature,
            },
        }
        if request.system:
            body["systemInstruction"] = {"parts": [{"text": request.system}]}
        if request.tools:
            body["tools"] = [{"functionDeclarations":
                              gemini_function_declarations(request.tools)}]
        if not self.api_key:
            raise ProviderError(f"{self.cap.name}: no API key (set {self.cap.env_var})",
                                RETRY_UNKNOWN)
        url = f"{self.cap.base_url.rstrip('/')}/models/{request.model}:streamGenerateContent?alt=sse"
        try:
            status, _headers, stream = self._transport({
                "method": "POST",
                "url": url,
                "headers": {"x-goog-api-key": self.api_key,
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
        text_open = False
        text_index = 0
        next_block_index = 0
        usage: UsageRecord | None = None
        finish: str | None = None
        tool_calls: list[dict] = []

        for obj in parse_sse_lines(lines):
            for cand in obj.get("candidates") or []:
                parts = (cand.get("content") or {}).get("parts") or []
                for part in parts:
                    if part.get("text"):
                        if not text_open:
                            text_index = next_block_index
                            next_block_index += 1
                            text_open = True
                            yield {"event": "block_start", "index": text_index,
                                   "block": {"type": "text", "text": ""}}
                        yield {"event": "text_delta", "index": text_index,
                               "text": part["text"]}
                    fc = part.get("functionCall")
                    if fc:
                        tool_calls.append({"name": fc.get("name", ""),
                                           "args": fc.get("args") or {}})
                fr = cand.get("finishReason")
                if fr:
                    finish = fr
            um = obj.get("usageMetadata")
            if um:
                usage = UsageRecord(
                    input_tokens=um.get("promptTokenCount", 0),
                    output_tokens=um.get("candidatesTokenCount", 0),
                    thinking_tokens=um.get("thoughtsTokenCount", 0),
                )

        if text_open:
            yield {"event": "block_stop", "index": text_index}

        for i, call in enumerate(tool_calls):
            block_index = next_block_index
            next_block_index += 1
            yield {"event": "block_start", "index": block_index,
                   "block": {"type": "tool_use",
                             "id": f"call_gemini_{i}",
                             "name": call["name"],
                             "input": call["args"]}}
            yield {"event": "block_stop", "index": block_index}

        if usage is not None:
            yield {"event": "usage", "usage": usage}
        stop = {"STOP": "end_turn", "MAX_TOKENS": "max_tokens",
                "SAFETY": "refusal", "RECITATION": "refusal"}.get(
                    finish or "STOP", "end_turn")
        yield {"event": "message_stop", "stop_reason": stop}


def _to_gemini_contents(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        content = msg.get("content", "")
        parts: list[dict] = []
        if isinstance(content, str):
            if content:
                parts.append({"text": content})
        else:
            for block in content:
                btype = block.get("type")
                if btype == "text":
                    parts.append({"text": block["text"]})
                elif btype == "thinking":
                    continue
                elif btype == "image":
                    img = image_block(block)
                    if img:
                        mime, data = img
                        parts.append({"inlineData": {"mimeType": mime,
                                                     "data": data}})
                elif btype == "tool_use":
                    parts.append({"functionCall": {
                        "name": block["name"],
                        "args": block.get("input", {})}})
                elif btype == "tool_result":
                    parts.append({"functionResponse": {
                        "name": block.get("tool_name", "tool"),
                        "response": {"result": block.get("content", "")}}})
        if parts:
            out.append({"role": role, "parts": parts})
    return out
