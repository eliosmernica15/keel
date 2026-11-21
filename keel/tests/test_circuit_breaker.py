"""B3.11 — provider circuit breaker, health scoring and fail-fast."""

from __future__ import annotations

import time

import pytest

from keel import circuit_breaker
from keel.providers.base import ProviderError
from keel.providers.model_client import ProviderModelClient


def test_breaker_opens_after_threshold_and_recovers():
    breaker = circuit_breaker.CircuitBreaker(
        "test-provider", failure_threshold=2, recovery_timeout=0.05)
    assert breaker.state == "closed"
    breaker.record_failure()
    assert breaker.state == "closed"
    breaker.record_failure()
    assert breaker.state == "open"
    assert breaker.allow() is False
    breaker._opened_at = time.monotonic() - 0.1  # deterministic recovery window
    assert breaker.state == "half_open"
    assert breaker.allow() is True
    breaker.record_success()
    assert breaker.state == "closed"
    assert breaker.health_score() == pytest.approx(0.333, abs=1e-3)


def test_health_score_reflects_failures():
    breaker = circuit_breaker.CircuitBreaker("h", failure_threshold=10)
    for _ in range(3):
        breaker.record_failure()
    breaker.record_success()
    assert breaker.health_score() == 0.25
    assert breaker.snapshot()["name"] == "h"


def test_registry_is_shared():
    a = circuit_breaker.breaker_for("shared")
    b = circuit_breaker.breaker_for("shared")
    assert a is b
    assert any(s["name"] == "shared" for s in circuit_breaker.all_breakers())


class _GoodAdapter:
    def complete(self, request):
        yield {"event": "block_start", "index": 0,
               "block": {"type": "text", "text": ""}}
        yield {"event": "text_delta", "index": 0, "text": "ok"}
        yield {"event": "block_stop", "index": 0}
        yield {"event": "message_stop", "stop_reason": "end_turn"}


class _BadAdapter:
    def __init__(self):
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        raise RuntimeError("provider down")
        yield  # pragma: no cover


def test_model_client_trips_breaker_and_fails_fast():
    breaker = circuit_breaker.CircuitBreaker("down", failure_threshold=2)
    adapter = _BadAdapter()
    client = ProviderModelClient(adapter, model="m", breaker=breaker)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            client.complete([], [])
    assert breaker.state == "open"
    with pytest.raises(ProviderError, match="circuit breaker open"):
        client.complete([], [])
    assert adapter.calls == 2  # no further provider call was made


def test_success_keeps_breaker_closed():
    breaker = circuit_breaker.CircuitBreaker("up", failure_threshold=1)
    client = ProviderModelClient(_GoodAdapter(), model="m", breaker=breaker)
    assert client.complete([], [])[0]["text"] == "ok"
    assert breaker.state == "closed"
    assert breaker.health_score() == 1.0
