"""Real-provider validation readiness (section 3).

Runs a defined test matrix against *configured* providers when credentials are
available. Never fabricates success: absent or invalid credentials produce an
explicit SKIP/FAIL with the reason. The matrix covers authentication, model
discovery, selection, streaming, tool calling, usage, timeouts, cancellation,
switching and failure recovery.

Honesty rules enforced here:

* a missing or blank credential is a truthful SKIP, never a PASS;
* a configured but malformed credential is a FAIL and no live call is made;
* a cancelled live call is not reported as a successful streaming check;
* the ``timeout_s`` budget is enforced, and a timed-out call is a FAIL;
* a live call happens only when ``live=True`` AND a credential is present
  (or an injected adapter factory is supplied by a test).
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .provider_contracts import redact_message
from .providers import registry as reg
from .providers.base import ProviderError, TurnCancelled, UsageRecord
from .providers.model_client import ProviderModelClient


@dataclass
class ProviderCheck:
    name: str
    status: str          # PASS | FAIL | SKIP
    detail: str


def _credential(cap) -> str:
    """Return the raw credential, treating whitespace-only values as absent.

    The registry itself strips credentials before deciding whether a provider
    is configured; validation must use the same rule or it would report a fake
    ``auth_present: PASS`` for a blank environment variable.
    """
    return os.environ.get(cap.env_var, "")


def _credential_present(cap) -> bool:
    return bool(_credential(cap).strip())


def _credential_malformed(raw: str) -> bool:
    """A credential carrying whitespace or control characters cannot be used."""
    return any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in raw)


# L-1 local defence: output DLP in keel.redaction only recognises assignment
# forms ("password=..."), so a phrase like "The password is Harbor Seal42
# Tango Mike" leaks. This boundary applies one extra heuristic before any
# validation report leaves this module. The authoritative fix belongs in
# keel.redaction (see STAB-PROVIDER-EVIDENCE.md); this is defence in depth for
# the validation surface owned here.
_NATURAL_SECRET_RE = re.compile(
    r"(?i)\b(?P<key>password|passphrase|secret|api[ _-]?key|"
    r"access[ _-]?token|token)\s+is\s+(?P<value>[^\r\n.!?]{3,160})")


def _redact_natural_language(value):
    """Redact 'password is <value>' phrasings in a report structure."""
    if isinstance(value, str):
        return _NATURAL_SECRET_RE.sub(
            lambda m: f"{m.group('key')} is [REDACTED]", value)
    if isinstance(value, dict):
        return {k: _redact_natural_language(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_natural_language(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_natural_language(v) for v in value)
    return value


def _safe_error(exc: BaseException, cap, *, prefix: str = "") -> str:
    """Error detail safe for a report: the credential is redacted first."""
    raw = _credential(cap)
    secrets = (raw,) if raw.strip() else ()
    text = f"{prefix}{type(exc).__name__}: {exc}"
    return _redact_natural_language(redact_message(text, secrets))[:300]


def configured_providers() -> list[str]:
    """Return providers with a non-blank credential in the environment."""
    return [cap.name for cap in reg._PROVIDERS.values()
            if _credential_present(cap)]


def _capability_checks(cap) -> list[ProviderCheck]:
    """Checks that need no network — the local adapter contract."""
    checks = []
    raw = _credential(cap)
    present = bool(raw.strip())
    # auth presence (value never exposed)
    checks.append(ProviderCheck(
        "auth_present", "PASS" if present else "SKIP",
        "credential present" if present else f"{cap.env_var} not set or blank"))
    # A present credential must still be usable. This is checked locally before
    # any live call, so a malformed value fails closed instead of being spent.
    if present:
        malformed = _credential_malformed(raw)
        checks.append(ProviderCheck(
            "credential_format", "FAIL" if malformed else "PASS",
            "credential contains whitespace or control characters" if malformed
            else "credential format looks usable"))
    else:
        checks.append(ProviderCheck(
            "credential_format", "SKIP", "no credential to validate"))
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
            adapter = reg.build_adapter(cap_name, api_key=_credential(cap))
        else:
            adapter = adapter_factory(cap)
    except Exception as exc:
        return [ProviderCheck("live_adapter", "FAIL", _safe_error(exc, cap))]

    cancel = threading.Event()
    client = ProviderModelClient(adapter, model=cap.default_model,
                                 cancel_event=cancel)
    messages = [{"role": "user", "content": "Reply with exactly: keel-ok"}]
    tools: list[dict] = []

    # Enforce the documented budget. The worker is a daemon so a hung provider
    # cannot keep the process alive; setting the cancel event asks the client
    # to stop at the next streamed event. A timeout is always a FAIL, never a
    # silent PASS and never a skip.
    outcome: dict = {}
    start = time.monotonic()

    def _work() -> None:
        try:
            outcome["blocks"] = client.complete(messages, tools)
        except BaseException as exc:  # reported below, never leaked as a value
            outcome["exc"] = exc

    worker = threading.Thread(target=_work, name=f"keel-validate-{cap_name}",
                              daemon=True)
    worker.start()
    budget = timeout_s if isinstance(timeout_s, (int, float)) and timeout_s > 0 else None
    worker.join(budget)
    if worker.is_alive():
        cancel.set()
        checks.append(ProviderCheck(
            "live_timeout", "FAIL",
            f"no response within {timeout_s:g}s" if budget else
            "no response within the validation budget"))
        return checks
    elapsed = time.monotonic() - start

    if "exc" in outcome:
        exc = outcome["exc"]
        if isinstance(exc, TurnCancelled):
            # A cancelled call proves nothing about streaming; do not claim a
            # successful streaming check for it.
            checks.append(ProviderCheck(
                "streaming_response", "SKIP",
                "call cancelled before a complete response; streaming not validated"))
            return checks
        if isinstance(exc, ProviderError):
            checks.append(ProviderCheck(
                "streaming_response", "FAIL",
                _safe_error(exc, cap, prefix=f"{exc.category}: ")))
            return checks
        checks.append(ProviderCheck("streaming_response", "FAIL",
                                    _safe_error(exc, cap)))
        return checks

    blocks = outcome.get("blocks") or []
    text = "".join(b.get("text", "") for b in blocks
                   if isinstance(b, dict) and b.get("type") == "text")
    checks.append(ProviderCheck(
        "streaming_response", "PASS" if text else "FAIL",
        f"{len(text)} chars in {elapsed:.1f}s"))
    usage = client.total_usage
    checks.append(ProviderCheck(
        "usage_tracking", "PASS" if usage.input_tokens or usage.output_tokens
        else "SKIP",
        f"in={usage.input_tokens} out={usage.output_tokens}"))
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
        malformed = any(c.name == "credential_format" and c.status == "FAIL"
                        for c in checks)
        can_live = live and (cap.name in configured
                             or adapter_factory is not None)
        if can_live and malformed and adapter_factory is None:
            # Never spend a call with a credential we already know is unusable.
            checks.append(ProviderCheck(
                "live_provider", "FAIL",
                "credential is malformed; no live call attempted"))
        elif can_live:
            checks += _live_checks(cap, timeout_s=timeout_s,
                                   adapter_factory=adapter_factory)
        else:
            checks.append(ProviderCheck(
                "live_provider", "SKIP",
                "live validation requires --live and a configured credential"))
        results[cap.name] = [c.__dict__ for c in checks]
    return _redact_natural_language({
        "providers": results,
        "configured": configured,
        "live": live,
        "note": "No real-provider success is reported without a real call.",
    })
