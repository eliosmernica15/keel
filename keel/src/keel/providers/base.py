"""keel.providers.base — the provider seam (Phase A).

Every adapter speaks the internal *neutral* format:

    messages: [{"role": "user"|"assistant",
                "content": str | list[block]}]
    blocks:   {"type": "text", "text": str} |
              {"type": "thinking", "thinking": str} |
              {"type": "tool_use", "id": str, "name": str, "input": dict} |
              {"type": "tool_result", "tool_use_id": str, "content": str}

`complete()` yields provider-agnostic events:

    {"event": "block_start", "index": int, "block": {...}}
    {"event": "text_delta", "index": int, "text": str}
    {"event": "thinking_delta", "index": int, "text": str}
    {"event": "tool_input_delta", "index": int, "partial_json": str}
    {"event": "block_stop", "index": int}
    {"event": "usage", "usage": UsageRecord}
    {"event": "message_stop", "stop_reason": str | None}
    {"event": "error", "category": str, "message": str, "retryable": bool}

The transport is injectable: `transport(request) -> response` where request is a
dict {method, url, headers, body_json|body_bytes}. Production uses stdlib
urllib; tests pass a fake returning canned (status, headers, chunk iterator).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

# Retry taxonomy (interface-spec §12.7, 12 values).
RETRY_AUTH = "authentication_failed"
RETRY_ORG = "organization_not_allowed"
RETRY_ACCOUNT = "account_on_hold"
RETRY_BILLING = "billing_error"
RETRY_RATE_LIMIT = "rate_limit"
RETRY_OVERLOADED = "overloaded"
RETRY_INVALID = "invalid_request"
RETRY_NOT_FOUND = "model_not_found"
RETRY_SERVER = "server_error"
RETRY_MAX_OUTPUT = "max_output_tokens"
RETRY_CREDENTIAL = "credential_error"
RETRY_UNKNOWN = "unknown"

ALL_CATEGORIES = frozenset([RETRY_AUTH, RETRY_ORG, RETRY_ACCOUNT, RETRY_BILLING,
                            RETRY_RATE_LIMIT, RETRY_OVERLOADED, RETRY_INVALID,
                            RETRY_NOT_FOUND, RETRY_SERVER, RETRY_MAX_OUTPUT,
                            RETRY_CREDENTIAL, RETRY_UNKNOWN])


class ProviderError(Exception):
    def __init__(self, message: str, category: str = RETRY_UNKNOWN,
                 status: Optional[int] = None, retryable: bool = False):
        super().__init__(message)
        self.category = category if category in ALL_CATEGORIES else RETRY_UNKNOWN
        self.status = status
        self.retryable = retryable


class TurnCancelled(Exception):
    """Raised when the operator hits Stop mid-generation.

    Carried up from the streaming adapter through ProviderModelClient into
    Session.run, which converts it to a `cancelled` result envelope. It is
    NOT an error — the model simply stops emitting.
    """
    pass


def status_to_category(status: int | None) -> tuple[str, bool]:
    """Map HTTP status -> (category, retryable). Conservative: only known
    capacity classes retry."""
    if status is None:
        return RETRY_UNKNOWN, False
    if status in (401,):
        return RETRY_AUTH, False
    if status in (402,):
        return RETRY_BILLING, False
    if status in (403,):
        return RETRY_ORG, False
    if status == 404:
        return RETRY_NOT_FOUND, False
    if status == 408 or status == 429:
        return RETRY_RATE_LIMIT, True
    if status == 409:
        return RETRY_INVALID, False
    if status in (400, 422):
        return RETRY_INVALID, False
    if status == 451:
        return RETRY_ACCOUNT, False
    if status in (500, 502):
        return RETRY_SERVER, True
    if status == 503:
        return RETRY_OVERLOADED, True
    if status >= 500:
        return RETRY_SERVER, True
    return RETRY_UNKNOWN, False


@dataclass(frozen=True)
class CapabilityRecord:
    name: str
    base_url: str
    env_var: str
    default_model: str
    context_window: int = 0
    max_output_tokens: int = 0
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_thinking: bool = False
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    cost_basis: str = "unknown"   # unknown | metered | free
    notes: str = ""


@dataclass
class UsageRecord:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    thinking_tokens: int = 0
    web_search_requests: int = 0

    def zero(self) -> "UsageRecord":
        return UsageRecord()


@dataclass
class ProviderRequest:
    model: str
    messages: list[dict]
    tools: list[dict]
    max_output_tokens: int = 4096
    temperature: float = 0.7
    system: str | None = None
    metadata: dict = field(default_factory=dict)
    # per-agent reasoning effort (e.g. low|medium|high|xhigh|max|none);
    # forwarded to providers that accept it (OpenRouter: reasoning.effort)
    reasoning_effort: str | None = None


def openai_tools(tools: list[dict]) -> list[dict]:
    """Neutral tool schema -> OpenAI function tools."""
    out = []
    for t in tools:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object",
                                                     "properties": {}}),
            },
        })
    return out


def gemini_function_declarations(tools: list[dict]) -> list[dict]:
    out = []
    for t in tools:
        out.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("input_schema", {"type": "object",
                                                 "properties": {}}),
        })
    return out


def anthropic_tools(tools: list[dict]) -> list[dict]:
    return list(tools)  # neutral schema already matches Anthropic's shape


def parse_sse_lines(lines: Iterator[str]) -> Iterator[dict]:
    """Minimal SSE parser: yields parsed JSON objects from `data:` lines."""
    data_buf: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line == "":
            if data_buf:
                payload = "\n".join(data_buf).strip()
                data_buf = []
                if payload == "[DONE]":
                    continue
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue
            continue
        if line.startswith("data:"):
            data_buf.append(line[5:].lstrip())
        # event: / id: / retry: lines ignored for our purposes
    if data_buf:
        payload = "\n".join(data_buf).strip()
        if payload and payload != "[DONE]":
            try:
                yield json.loads(payload)
            except json.JSONDecodeError:
                pass


def http_transport(request: dict) -> tuple[int, dict, Iterator[bytes]]:
    """Production transport: urllib. request = {method, url, headers, body_json|body_bytes}."""
    import urllib.error
    import urllib.request

    body = request.get("body_bytes")
    if body is None and request.get("body_json") is not None:
        body = json.dumps(request["body_json"]).encode("utf-8")
    req = urllib.request.Request(
        request["url"],
        data=body,
        method=request.get("method", "POST"),
        headers=request.get("headers", {}),
    )
    try:
        resp = urllib.request.urlopen(req, timeout=request.get("timeout", 60))
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        try:
            message = raw.decode("utf-8", errors="replace")[:2000]
        except Exception:
            message = f"http {exc.code}"
        category, retryable = status_to_category(exc.code)
        raise ProviderError(message, category, exc.code, retryable) from None
    except urllib.error.URLError as exc:
        raise ProviderError(f"connection failed: {exc.reason}", RETRY_UNKNOWN,
                            None, True) from None
    headers = dict(resp.headers.items())

    def gen() -> Iterator[bytes]:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            yield chunk

    return resp.status, headers, gen()
