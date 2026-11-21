"""Provider validation path is real and honest about credentials."""

from __future__ import annotations

import json
import subprocess
import sys

from keel.provider_validation import run_validation


def test_validation_without_live_credentials():
    doc = run_validation(live=False)
    assert doc["live"] is False
    assert len(doc["providers"]) >= 5
    for provider, checks in doc["providers"].items():
        statuses = {c["status"] for c in checks}
        assert "FAIL" not in statuses or provider == "openai-compatible"
        assert any(c["name"] == "live_provider" and c["status"] == "SKIP"
                   for c in checks)


def test_no_credentials_means_no_live_success():
    doc = run_validation(live=True)
    # No credentials are configured in this environment; no live calls.
    assert doc["configured"] == []
    for checks in doc["providers"].values():
        live = [c for c in checks if c["name"] == "live_provider"]
        assert live and live[0]["status"] == "SKIP"


def test_mock_adapter_live_matrix():
    """A deterministic adapter can exercise the live matrix honestly."""
    from keel.providers.base import CapabilityRecord, UsageRecord

    cap = CapabilityRecord(
        name="mocklive", base_url="https://x.invalid",
        env_var="KEEL_MOCKLIVE_KEY", default_model="mock-model",
        supports_tools=True, supports_streaming=True)

    class Adapter:
        def __init__(self, cap, *, api_key=""):
            self.api_key = api_key

        def complete(self, request):
            yield {"event": "block_start", "index": 0,
                   "block": {"type": "text", "text": ""}}
            yield {"event": "text_delta", "index": 0, "text": "keel-ok"}
            yield {"event": "block_stop", "index": 0}
            yield {"event": "usage", "usage": UsageRecord(
                input_tokens=3, output_tokens=2)}
            yield {"event": "message_stop", "stop_reason": "end_turn"}

    doc = run_validation(live=True, adapter_factory=lambda c: Adapter(c),
                         providers=[cap])
    checks = doc["providers"]["mocklive"]
    streaming = next(c for c in checks if c["name"] == "streaming_response")
    assert streaming["status"] == "PASS"
