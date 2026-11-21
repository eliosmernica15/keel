"""keel.providers.model_client — bridges adapters to the Session contract.

The Session expects model_client.complete(messages, tools) -> list[blocks].
This class consumes the adapter's neutral event stream and assembles the
blocks. Also aggregates usage across calls (Session threads it into the
envelope when present).
"""

from __future__ import annotations

import time
from typing import Any, Iterator

from .base import ProviderRequest, UsageRecord


class ProviderModelClient:
    def __init__(self, adapter: Any, *, model: str,
                 max_output_tokens: int = 4096,
                 delta_sink: Any = None,
                 reasoning_effort: str | None = None,
                 cancel_event: Any = None,
                 breaker: Any = None, provider_name: str = ""):
        self.adapter = adapter
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.request_count = 0
        self.total_usage = UsageRecord()
        self.last_stop_reason: str | None = None
        # called with each raw text delta as it arrives off the wire;
        # never allowed to raise into the turn
        self.delta_sink = delta_sink
        # per-agent effort; forwarded to providers that understand it
        self.reasoning_effort = reasoning_effort
        # when set, Stop aborts generation mid-stream, not just at round boundaries
        self.cancel_event = cancel_event
        # B3.11: per-provider circuit breaker; opt-in via ``breaker`` or by
        # naming the provider so a shared breaker can be looked up.
        self.breaker = breaker
        if self.breaker is None and provider_name:
            from ..circuit_breaker import breaker_for
            self.breaker = breaker_for(provider_name)

    def complete(self, messages: list[dict], tools: list[dict]) -> list[dict]:
        """Provider call guarded by the circuit breaker."""
        from .base import RETRY_SERVER, ProviderError

        if self.breaker is not None and not self.breaker.allow():
            raise ProviderError(
                f"circuit breaker open for {self.breaker.name}",
                RETRY_SERVER, 503, retryable=False)
        try:
            result = self._complete_inner(messages, tools)
        except Exception:
            if self.breaker is not None:
                self.breaker.record_failure()
            raise
        if self.breaker is not None:
            self.breaker.record_success()
        return result

    def _complete_inner(self, messages: list[dict], tools: list[dict]) -> list[dict]:
        self.request_count += 1
        request = ProviderRequest(
            model=self.model,
            messages=messages,
            tools=tools,
            max_output_tokens=self.max_output_tokens,
            reasoning_effort=self.reasoning_effort,
        )
        index_map: dict[int, dict] = {}
        order: list[int] = []
        for event in self.adapter.complete(request):
            if self.cancel_event is not None and self.cancel_event.is_set():
                from .base import TurnCancelled
                raise TurnCancelled()
            kind = event.get("event")
            if kind == "block_start":
                idx = event["index"]
                index_map[idx] = dict(event["block"])
                order.append(idx)
            elif kind == "text_delta":
                index_map[event["index"]]["text"] = (
                    index_map[event["index"]].get("text", "") + event["text"])
                if self.delta_sink is not None:
                    try:
                        self.delta_sink(event["text"])
                    except Exception:
                        pass  # streaming must never break the turn
            elif kind == "thinking_delta":
                index_map[event["index"]]["thinking"] = (
                    index_map[event["index"]].get("thinking", "") + event["text"])
            elif kind == "tool_input":  # anthropic: full input arrives at stop
                index_map[event["index"]]["input"] = event["input"]
            elif kind == "block_stop":
                pass  # block stays in index_map; emitted at end in order
            elif kind == "usage":
                u = event["usage"]
                self.total_usage.input_tokens += u.input_tokens
                self.total_usage.output_tokens += u.output_tokens
                self.total_usage.cache_read_input_tokens += u.cache_read_input_tokens
                self.total_usage.cache_creation_input_tokens += \
                    u.cache_creation_input_tokens
                self.total_usage.thinking_tokens += u.thinking_tokens
            elif kind == "message_stop":
                self.last_stop_reason = event.get("stop_reason")
        blocks = []
        for idx in order:
            block = index_map[idx]
            btype = block.get("type")
            if btype == "text" and not block.get("text"):
                continue
            blocks.append(block)
        return blocks

    def describe(self):
        return self.adapter.describe()
