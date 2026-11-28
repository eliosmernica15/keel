"""keel.providers.ollama — explicit opt-in local Ollama adapter.

Ollama runs on the user's own machine: no API key, no account, no cloud
service. It is deliberately *not* part of the auto resolution chain; Keel
only talks to it when the caller explicitly selects ``provider="ollama"``.

Chat completions use Ollama's OpenAI-compatible endpoint
(``POST {base_url}/chat/completions``) and model discovery uses the native
``GET /api/tags`` endpoint. If Ollama is unavailable the adapter raises a
ProviderError — it never substitutes a fake or bundled model.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterator

from .base import (CapabilityRecord, ProviderError, ProviderRequest, UsageRecord,
                   http_transport, openai_tools, parse_sse_lines,
                   RETRY_UNKNOWN, status_to_category)
# Internal but package-local helpers: reusing them keeps this adapter thin and
# ensures local models see exactly the same message/tool conversion as other
# OpenAI-compatible endpoints.
from .openai_compatible import _iter_text_lines, _to_openai_messages

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DISCOVERY_TIMEOUT = 5.0
REQUEST_TIMEOUT = 120

__all__ = [
    "DEFAULT_BASE_URL",
    "DISCOVERY_TIMEOUT",
    "OllamaAdapter",
    "discover_models",
    "make_capability",
    "tags_url",
]


def default_base_url() -> str:
    """Loopback by default; an explicit env override is allowed, never a key."""
    return (os.environ.get("KEEL_OLLAMA_BASE_URL", "").strip()
            or DEFAULT_BASE_URL)


def tags_url(base_url: str | None = None) -> str:
    """/api/tags lives at the daemon root, not under the /v1 compatibility path."""
    base = (base_url or default_base_url()).rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base.rstrip("/") + "/api/tags"


def make_capability() -> CapabilityRecord:
    """Honest capability record: local, unmetered, opt-in, no credentials."""
    return CapabilityRecord(
        name="ollama",
        base_url=default_base_url(),
        env_var="",  # no key and no account are needed
        default_model=os.environ.get("KEEL_OLLAMA_MODEL", "").strip(),
        context_window=0,       # depends on the selected local model
        max_output_tokens=0,    # depends on the selected local model
        supports_tools=True,    # Ollama's OpenAI-compatible tool calls
        supports_streaming=True,
        supports_thinking=False,  # not part of the OpenAI-compatible seam
        price_input_per_mtok=None,
        price_output_per_mtok=None,
        cost_basis="free",      # no per-token charge; local hardware only
        notes=("Local Ollama daemon; explicit opt-in only "
               '(provider="ollama"). No API key or account. '
               "Discovery: GET /api/tags. Set KEEL_OLLAMA_MODEL or use "
               "an explicit ollama/<model> reference."),
    )


def discover_models(*, base_url: str | None = None, transport=None,
                    timeout: float = DISCOVERY_TIMEOUT,
                    strict: bool = False) -> list[str]:
    """Return the names reported by ``GET /api/tags``, sorted and deduped.

    Failure is graceful by default: an unreachable daemon, an HTTP error or a
    malformed payload yields ``[]`` (which means "no model available") and
    never a placeholder/fake name. With ``strict=True`` a ProviderError is
    raised instead. Error messages intentionally omit the endpoint and any
    exception detail, which could carry credentials from a custom base URL.
    """
    url = tags_url(base_url)
    try:
        status, _headers, stream = (transport or http_transport)({
            "method": "GET",
            "url": url,
            "headers": {},
            "timeout": timeout,
        })
    except Exception:
        if strict:
            raise ProviderError(
                "Ollama is not reachable at the configured local endpoint",
                RETRY_UNKNOWN, None, True) from None
        return []
    if status >= 400:
        if strict:
            category, retryable = status_to_category(status)
            raise ProviderError(f"Ollama /api/tags returned http {status}",
                                category, status, retryable)
        return []
    try:
        doc = json.loads(b"".join(stream).decode("utf-8", errors="replace"))
        entries = doc.get("models") if isinstance(doc, dict) else None
        names: set[str] = set()
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or entry.get("model")
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
        return sorted(names)
    except Exception:
        if strict:
            raise ProviderError("Ollama /api/tags returned an invalid payload",
                                RETRY_UNKNOWN, None, False) from None
        return []


class OllamaAdapter:
    """Thin OpenAI-compatible local adapter; no Authorization header is sent."""

    def __init__(self, cap: CapabilityRecord | None = None, *,
                 api_key: str | None = None, transport=None):
        # An api_key argument is accepted only for signature compatibility
        # with the other adapters; it is never stored, sent or logged.
        self.cap = cap or make_capability()
        self.api_key = ""
        self._transport = transport or http_transport

    @classmethod
    def from_env(cls, cap: CapabilityRecord | None = None, *, transport=None):
        return cls(cap, transport=transport)

    def describe(self) -> CapabilityRecord:
        return self.cap

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def discover(self, *, transport=None) -> list[str]:
        """Discover models from this adapter's base URL (best effort)."""
        return discover_models(base_url=self.cap.base_url,
                               transport=transport or self._transport)

    def complete(self, request: ProviderRequest) -> Iterator[dict]:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": _to_openai_messages(request.messages, request.system),
            "stream": True,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.tools:
            body["tools"] = openai_tools(request.tools)
        try:
            status, _headers, stream = self._transport({
                "method": "POST",
                "url": self.cap.base_url.rstrip("/") + "/chat/completions",
                "headers": self._headers(),
                "body_json": body,
                "timeout": REQUEST_TIMEOUT,
            })
        except ProviderError as exc:
            # Keep the taxonomy, add an explicit no-fallback statement. Never
            # echo the original message: it may contain a custom endpoint.
            raise ProviderError(
                "Ollama unavailable at the configured local endpoint "
                f"({exc.category}); no fallback model is used",
                exc.category, exc.status, exc.retryable) from None
        except Exception:
            raise ProviderError(
                "Ollama unavailable at the configured local endpoint; "
                "no fallback model is used", RETRY_UNKNOWN, None, True) from None
        if status >= 400:
            category, retryable = status_to_category(status)
            raise ProviderError(f"Ollama /chat/completions returned http {status}",
                                category, status, retryable)

        text_open = False
        text_index = 0
        tool_acc: dict[int, dict] = {}
        next_block_index = 0
        usage: UsageRecord | None = None
        finish_reason: str | None = None

        for obj in parse_sse_lines(_iter_text_lines(stream)):
            if obj.get("usage"):
                u = obj["usage"]
                usage = UsageRecord(
                    input_tokens=u.get("prompt_tokens", 0),
                    output_tokens=u.get("completion_tokens", 0),
                )
                continue
            for choice in obj.get("choices") or []:
                delta = choice.get("delta") or choice.get("message") or {}
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
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
                    acc = tool_acc.setdefault(
                        idx, {"id": None, "name": "", "args": ""})
                    if tc.get("id"):
                        acc["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        acc["name"] += fn["name"]
                    if fn.get("arguments"):
                        acc["args"] += fn["arguments"]

        if text_open:
            yield {"event": "block_stop", "index": text_index}

        for idx in sorted(tool_acc):
            acc = tool_acc[idx]
            try:
                from ..tool_json import repair_json

                parsed = (repair_json(acc["args"]) if acc["args"].strip()
                          else {})
                if not isinstance(parsed, dict):
                    parsed = {"_raw": acc["args"]}
            except (ValueError, TypeError):
                parsed = {"_raw": acc["args"]}
            block_index = next_block_index
            next_block_index += 1
            yield {"event": "block_start", "index": block_index,
                   "block": {"type": "tool_use",
                             "id": acc["id"] or f"call_{block_index}",
                             "name": acc["name"], "input": parsed}}
            yield {"event": "block_stop", "index": block_index}

        if usage is not None:
            yield {"event": "usage", "usage": usage}
        stop = {"stop": "end_turn", "length": "max_tokens",
                "tool_calls": "tool_use", "tool_use": "tool_use",
                "end_turn": "end_turn"}.get(finish_reason or "stop", "end_turn")
        if tool_acc and finish_reason in (None, "stop"):
            stop = "tool_use"
        yield {"event": "message_stop", "stop_reason": stop}
