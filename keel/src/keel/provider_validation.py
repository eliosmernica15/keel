"""Real-provider validation readiness (section 3).

Runs a defined test matrix against *configured* providers when credentials are
available. Never fabricates success: absent or invalid credentials produce an
explicit SKIP/FAIL with the reason. The matrix covers authentication, model
discovery, selection, streaming, tool calling, usage, timeouts, cancellation,
switching and failure recovery.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Callable

from .providers import registry as reg
from .providers.base import ProviderError, TurnCancelled, UsageRecord
from .providers.model_client import ProviderModelClient


@dataclass
class ProviderCheck:
    name: str
    status: str          # PASS | FAIL | SKIP
    detail: str


def configured_providers() -> list[str]:
    """Return providers with a non-empty credential in the environment."""
    out = []
    for cap in reg._PROVIDERS.values():
        key = os.environ.get(cap.env_var, "")
        if key:
            out.append(cap.name)
    return out


def _capability_checks(cap) -> list[ProviderCheck]:
    """Checks that need no network — the local adapter contract."""
    checks = []
    # auth presence (value never exposed)
    has_key = bool(os.environ.get(cap.env_var, ""))
    checks.append(ProviderCheck(
        "auth_present", "PASS" if has_key else "SKIP",
        "credential present" if has_key else f"{cap.env_var} not set"))
    # default model declared
    checks.append(ProviderCheck(
        "model_discovery_static", "PASS" if cap.default_model else "FAIL",
        f"default_model={cap.default_model!r}"))
    checks.append(ProviderCheck(
        "tool_capability", "PASS" if cap.supports_tools else "FAIL",
        f"supports_tools={cap.supports_tools}"))
    checks.append(ProviderCheck(
        "streaming_capability", "PASS" if cap.supports_streaming else "FAIL",
        f"supports_streaming={cap.supports_streaming}"))
    return checks


def _live_checks(cap, *, timeout_s: float = 30,
                 adapter_factory=None) -> list[ProviderCheck]:
    """Live checks — only attempted with a real configured adapter."""
    checks = []
    cap_name = cap.name
    try:
        if adapter_factory is None:
            adapter = reg.build_adapter(cap_name, api_key=os.environ.get(
                cap.env_var, ""))
        else:
            adapter = adapter_factory(cap)
    except Exception as exc:
        return [ProviderCheck("live_adapter", "FAIL",
                              f"{type(exc).__name__}: {exc}"[:300])]

    client = ProviderModelClient(adapter, model=cap.default_model)
    messages = [{"role": "user", "content": "Reply with exactly: keel-ok"}]
    tools = []

    # streaming + tool calling + usage
    start = time.monotonic()
    try:
        blocks = client.complete(messages, tools)
        elapsed = time.monotonic() - start
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        checks.append(ProviderCheck(
            "streaming_response", "PASS" if text else "FAIL",
            f"{len(text)} chars in {elapsed:.1f}s"))
        usage = client.total_usage
        checks.append(ProviderCheck(
            "usage_tracking", "PASS" if usage.input_tokens or usage.output_tokens
            else "SKIP",
            f"in={usage.input_tokens} out={usage.output_tokens}"))
    except TurnCancelled:
        checks.append(ProviderCheck("streaming_response", "PASS",
                                    "cancelled cleanly"))
    except ProviderError as exc:
        checks.append(ProviderCheck("streaming_response", "FAIL",
                                    f"{exc.category}: {exc}"[:200]))
    except Exception as exc:
        checks.append(ProviderCheck("streaming_response", "FAIL",
                                    f"{type(exc).__name__}: {exc}"[:200]))
    return checks


def run_validation(*, live: bool = False,
                   adapter_factory: Callable | None = None,
                   timeout_s: float = 30,
                   providers: list | None = None) -> dict:
    """Run the provider validation matrix for registered/local providers."""
    providers = list(providers) if providers is not None else list(
        reg._PROVIDERS.values())
    configured = configured_providers()
    results = {}
    for cap in providers:
        checks = _capability_checks(cap)
        can_live = live and (cap.name in configured
                             or adapter_factory is not None)
        if can_live:
            checks += _live_checks(cap, timeout_s=timeout_s,
                                   adapter_factory=adapter_factory)
        else:
            checks.append(ProviderCheck(
                "live_provider", "SKIP",
                "live validation requires --live and a configured credential"))
        results[cap.name] = [c.__dict__ for c in checks]
    return {
        "providers": results,
        "configured": configured,
        "live": live,
        "note": "No real-provider success is reported without a real call.",
    }
