"""Opt-in, fail-closed verification of one real provider request.

This harness is deliberately hard to run. It performs **at most one** tiny,
bounded request and only after every gate below is satisfied:

1. the operator passes the explicit ``--allow-live-provider-check`` flag;
2. the operator passes ``--confirm-free-tier-current`` and supplies a JSON
   confirmation record documenting that *current* free-tier terms were checked;
3. an approved free-tier credential is present in the environment (presence is
   checked with ``os.environ.get`` only; values are never printed or recorded);
4. the selected provider/model match the confirmation record and the free-tier
   allowlist (paid, opt-in and unknown providers are refused outright).

When any gate is missing the harness reports ``blocked``, makes **no** external
request, and exits with status 2. There is no retry, no fallback and no
automatic paid usage: the probe uses one request, ``max_output_tokens=16``, no
tools, no images and a hard wall-clock budget.

Only ``provider``, ``model``, ``timestamp``, ``commit``, a ``result`` summary and
``quota_context`` are recorded. No credential value, prompt text, response text,
header or raw payload is written to stdout or to the results file.

Example (operator-supplied, after re-verifying current free-tier terms)::

    python scripts/verify_live_provider.py \
      --allow-live-provider-check \
      --confirm-free-tier-current \
      --provider google \
      --confirmation-file /private/path/confirmation.json \
      --results-json /private/path/result.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

# --- fixed policy -----------------------------------------------------------

ALLOW_LIVE_FLAG = "--allow-live-provider-check"
CONFIRM_FREE_TIER_FLAG = "--confirm-free-tier-current"
CONFIRMATION_ENV = "KEEL_LIVE_CONFIRMATION_FILE"

CONFIRMATION_SCHEMA = 1
MAX_CONFIRMATION_AGE_DAYS = 30
MAX_OUTPUT_TOKENS = 16
WALL_CLOCK_TIMEOUT_SECONDS = 15.0
MAX_TRANSPORT_CALLS = 1

PROMPT = "Reply with exactly: keel-ok"

#: Only providers with an operator-confirmed, currently available free tier may
#: be probed. Anthropic is opt-in only (licensing review OPEN-Q1) and an
#: OpenAI-compatible endpoint has unknown billing, so neither is allowed here.
ALLOWED_PROVIDERS: dict[str, dict[str, Any]] = {
    "openrouter": {"env_var": "KEEL_OPENROUTER_API_KEY", "free_model_marker": ":free"},
    "google": {"env_var": "KEEL_GOOGLE_API_KEY", "free_model_marker": None},
    "nvidia": {"env_var": "KEEL_NVIDIA_API_KEY", "free_model_marker": None},
}

#: Every credential name is known up front so the final report can be scrubbed
#: even when a gate fails before a provider is selected.
ALL_CREDENTIAL_ENV_VARS = (
    "KEEL_OPENROUTER_API_KEY", "KEEL_GOOGLE_API_KEY", "KEEL_NVIDIA_API_KEY",
    "KEEL_ANTHROPIC_API_KEY", "KEEL_COMPAT_API_KEY", "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "NVIDIA_API_KEY", "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)

_CONFIRMATION_KEYS = frozenset({
    "schema_version", "provider", "model", "operator", "confirmed_at",
    "free_tier_current", "no_paid_usage",
})
_SECRET_KEY_RE = re.compile(
    r"(?i)(api[ _-]?key|secret|password|token|credential|authorization)")
_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


@dataclass(frozen=True)
class GateDecision:
    """Outcome of the fail-closed preflight. Never carries a credential value."""

    ok: bool
    provider: str | None
    model: str | None
    reasons: tuple[str, ...]
    confirmation: dict[str, Any] | None = None


# --- small, dependency-free helpers -----------------------------------------

def _env_value(name: str, env: Mapping[str, str] | None = None) -> str:
    """Read one environment variable; callers never receive anything else."""
    source = os.environ if env is None else env
    value = source.get(name, "")
    return value if isinstance(value, str) else ""


def _all_secrets(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    return tuple(
        value.strip() for name in ALL_CREDENTIAL_ENV_VARS
        if (value := _env_value(name, env)).strip()
    )


def _scrub(value: Any, secrets: tuple[str, ...]) -> Any:
    """Remove known secret values from a structure before it is emitted."""
    if isinstance(value, str):
        result = value
        for secret in sorted(secrets, key=len, reverse=True):
            result = result.replace(secret, "[REDACTED]")
        return result
    if isinstance(value, Mapping):
        return {k: _scrub(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [_scrub(item, secrets) for item in value]
        return tuple(items) if isinstance(value, tuple) else items
    return value


def _contains_secret(value: Any, secrets: tuple[str, ...]) -> bool:
    if not secrets:
        return False
    if isinstance(value, str):
        return any(secret in value for secret in secrets)
    if isinstance(value, Mapping):
        return any(_contains_secret(k, secrets) or _contains_secret(v, secrets)
                   for k, v in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_secret(item, secrets) for item in value)
    return False


def _safe_text(value: Any, limit: int = 64) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    cleaned = value.strip()[:limit]
    return cleaned if _SAFE_CODE_RE.match(cleaned) else None


def _strict_true(doc: Mapping, key: str, reasons: list[str]) -> bool:
    value = doc.get(key)
    if value is not True:
        reasons.append(f"confirmation field {key!r} must be the boolean true")
        return False
    return True


def _git_commit(repo_root: str | None) -> str:
    """Return a short commit id only; never stdout/stderr from other commands."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root or str(Path(__file__).resolve().parent.parent),
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    value = proc.stdout.strip() if proc.returncode == 0 else ""
    return value if re.fullmatch(r"[0-9a-f]{5,40}", value) else "unknown"


# --- confirmation record ----------------------------------------------------

def _read_confirmation(path: str) -> tuple[dict | None, str]:
    """Read a confirmation record; malformed files fail closed without values."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, ValueError):
        return None, ""
    if not isinstance(doc, dict):
        return None, raw
    return doc, raw


def _validate_confirmation(
    doc: dict | None, raw: str, *, provider: str | None, model: str | None,
    now: datetime, env: Mapping[str, str] | None,
) -> tuple[dict[str, Any] | None, str | None, tuple[str, ...]]:
    """Validate the operator's documented, current free-tier confirmation."""
    reasons: list[str] = []
    if doc is None:
        return None, None, ("free-tier confirmation file is missing or not valid JSON",)

    secrets = _all_secrets(env)
    if _contains_secret(doc, secrets) or _contains_secret(raw, secrets):
        return None, None, ("confirmation record must not contain credential material",)

    unknown = sorted(set(doc) - _CONFIRMATION_KEYS)
    if unknown:
        reasons.append("confirmation record has unexpected fields: "
                       + ", ".join(unknown))
    if doc.get("schema_version") != CONFIRMATION_SCHEMA or isinstance(
            doc.get("schema_version"), bool):
        reasons.append(f"confirmation schema_version must be {CONFIRMATION_SCHEMA}")

    doc_provider = doc.get("provider")
    if not isinstance(doc_provider, str) or doc_provider not in ALLOWED_PROVIDERS:
        reasons.append("confirmation provider is not on the free-tier allowlist")
    elif provider is not None and doc_provider != provider:
        reasons.append("selected provider does not match the confirmation record")

    doc_model = doc.get("model")
    if not isinstance(doc_model, str) or not doc_model.strip() \
            or doc_model.strip().lower() in ("auto", "none"):
        reasons.append("confirmation must name an explicit free-tier model")
    elif model is not None and model != doc_model:
        reasons.append("selected model does not match the confirmation record")
    elif isinstance(doc_provider, str) and doc_provider in ALLOWED_PROVIDERS:
        marker = ALLOWED_PROVIDERS[doc_provider]["free_model_marker"]
        if marker and marker not in doc_model:
            reasons.append(f"model for {doc_provider} must be a ':free' model")

    operator = doc.get("operator")
    if not isinstance(operator, str) or not operator.strip():
        reasons.append("confirmation must name the operator who verified the terms")

    stamp = doc.get("confirmed_at")
    confirmed_day: date | None = None
    if isinstance(stamp, str) and stamp.strip():
        try:
            confirmed_day = (datetime.fromisoformat(stamp.strip()).date()
                             if "T" in stamp else date.fromisoformat(stamp.strip()))
        except ValueError:
            confirmed_day = None
    if confirmed_day is None:
        reasons.append("confirmation confirmed_at must be an ISO date")
    else:
        age = (now.date() - confirmed_day).days
        if age < 0:
            reasons.append("confirmation date is in the future")
        elif age > MAX_CONFIRMATION_AGE_DAYS:
            reasons.append(f"confirmation is older than {MAX_CONFIRMATION_AGE_DAYS} days")

    _strict_true(doc, "free_tier_current", reasons)
    _strict_true(doc, "no_paid_usage", reasons)

    if reasons:
        return None, None, tuple(reasons)
    return ({"operator": operator.strip()[:64],
             "confirmed_at": confirmed_day.isoformat(),
             "max_age_days": MAX_CONFIRMATION_AGE_DAYS},
            doc_model, ())


# --- gate -------------------------------------------------------------------

def evaluate(
    options: Mapping[str, Any], *, env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> GateDecision:
    """Run every gate without touching the network. Injection points are for tests."""
    reasons: list[str] = []
    flags = set(options.get("flags") or ())
    if ALLOW_LIVE_FLAG not in flags:
        reasons.append(f"missing explicit {ALLOW_LIVE_FLAG} flag")
    if CONFIRM_FREE_TIER_FLAG not in flags:
        reasons.append(f"missing operator {CONFIRM_FREE_TIER_FLAG} flag")

    provider = options.get("provider")
    if not isinstance(provider, str) or provider not in ALLOWED_PROVIDERS:
        reasons.append("provider must be one of "
                       + ", ".join(sorted(ALLOWED_PROVIDERS))
                       + "; paid/opt-in providers are never auto-probed")
        provider = None

    model = options.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        reasons.append("model must be a non-empty string")
        model = None

    path = options.get("confirmation_file") or _env_value(CONFIRMATION_ENV, env)
    confirmation: dict[str, Any] | None = None
    if not isinstance(path, str) or not path.strip():
        reasons.append("missing free-tier confirmation file")
    else:
        doc, raw = _read_confirmation(path.strip())
        confirmed, confirmed_model, problems = _validate_confirmation(
            doc, raw, provider=provider, model=model,
            now=now or datetime.now(timezone.utc), env=env)
        reasons.extend(problems)
        if confirmed is not None:
            confirmation = confirmed
            if model is None:
                model = confirmed_model

    if provider is not None:
        env_var = ALLOWED_PROVIDERS[provider]["env_var"]
        raw_key = _env_value(env_var, env)
        if not raw_key.strip():
            reasons.append(f"{env_var} is not set or blank")
        elif any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in raw_key):
            reasons.append(f"{env_var} contains whitespace or control characters")

    return GateDecision(
        ok=not reasons, provider=provider, model=model,
        reasons=tuple(reasons), confirmation=confirmation,
    )


# --- bounded probe ----------------------------------------------------------

class _BoundedTransport:
    """Exactly one call, with the provider timeout clamped to the hard budget."""

    def __init__(self, delegate: Any, *, timeout_s: float):
        self._delegate = delegate
        self._timeout_s = timeout_s
        self.calls = 0

    def __call__(self, request: dict) -> Any:
        if self.calls >= MAX_TRANSPORT_CALLS:
            raise RuntimeError("live harness refuses a second provider request")
        self.calls += 1
        bounded = dict(request)
        try:
            requested = float(bounded.get("timeout", self._timeout_s))
        except (TypeError, ValueError):
            requested = self._timeout_s
        bounded["timeout"] = min(requested, self._timeout_s)
        return self._delegate(bounded)


def _production_transport() -> Any:
    from keel.providers.base import http_transport

    return http_transport


def perform_probe(
    *, provider: str, model: str, key: str, transport: Any,
    timeout_s: float = WALL_CLOCK_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Issue one tiny request through an injected transport; never log values."""
    from keel.providers import registry as reg
    from keel.providers.model_client import ProviderModelClient

    bounded = _BoundedTransport(transport, timeout_s=timeout_s)
    result: dict[str, Any] = {
        "status": "failed",
        "text_chars": 0,
        "stop_reason": None,
        "error_category": None,
        "transport_calls": bounded.calls,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
    try:
        adapter = reg.build_adapter(provider, api_key=key, transport=bounded)
        cancel = threading.Event()
        client = ProviderModelClient(
            adapter, model=model, max_output_tokens=MAX_OUTPUT_TOKENS,
            cancel_event=cancel)
        outcome: dict[str, Any] = {}

        def _work() -> None:
            try:
                outcome["blocks"] = client.complete(
                    [{"role": "user", "content": PROMPT}], [])
            except BaseException as exc:  # never recorded as a value
                outcome["exc"] = exc

        worker = threading.Thread(target=_work, name="keel-live-probe", daemon=True)
        worker.start()
        worker.join(timeout_s)
        if worker.is_alive():
            cancel.set()
            result["status"] = "timeout"
            return result

        if "exc" in outcome:
            exc = outcome["exc"]
            result["error_category"] = _safe_text(
                getattr(exc, "category", None), 64) or type(exc).__name__
            from keel.providers.base import TurnCancelled

            result["status"] = "cancelled" if isinstance(exc, TurnCancelled) else "failed"
            return result

        blocks = outcome.get("blocks") or []
        text = "".join(block.get("text", "") for block in blocks
                       if isinstance(block, dict) and block.get("type") == "text")
        result.update({
            "status": "ok" if text else "failed",
            "text_chars": len(text),
            "stop_reason": _safe_text(client.last_stop_reason),
            "usage": {
                "input_tokens": int(client.total_usage.input_tokens),
                "output_tokens": int(client.total_usage.output_tokens),
            },
        })
        return result
    finally:
        result["transport_calls"] = bounded.calls


# --- report and CLI ---------------------------------------------------------

def build_report(
    *, decision: GateDecision, now: datetime, commit: str,
    probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the only fields this harness is allowed to record."""
    return {
        "kind": "keel-live-provider-verification",
        "status": (probe or {}).get("status", "blocked"),
        "provider": decision.provider,
        "model": decision.model,
        "timestamp_utc": now.isoformat(),
        "commit": commit,
        "quota_context": {
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "tools": 0,
            "images": 0,
            "fallbacks": [],
            "max_attempts": 1,
            "timeout_seconds": WALL_CLOCK_TIMEOUT_SECONDS,
            "transport_calls": (probe or {}).get("transport_calls", 0),
            "free_tier_confirmation": decision.confirmation,
        },
        "result": {
            "text_chars": (probe or {}).get("text_chars", 0),
            "stop_reason": (probe or {}).get("stop_reason"),
            "usage": (probe or {}).get(
                "usage", {"input_tokens": 0, "output_tokens": 0}),
            "error_category": (probe or {}).get("error_category"),
            "reasons": list(decision.reasons),
        },
        "note": "No credential value, prompt, response text or payload is recorded.",
    }


def parse_args(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(
        description="Opt-in, fail-closed live provider verification (one bounded request).",
        allow_abbrev=False,
    )
    parser.add_argument(ALLOW_LIVE_FLAG, dest="allow_live", action="store_true",
                        help="explicitly allow a real provider request")
    parser.add_argument(CONFIRM_FREE_TIER_FLAG, dest="confirm_free", action="store_true",
                        help="operator confirms current free-tier terms were checked")
    parser.add_argument("--provider", default=None, help="free-tier provider to probe")
    parser.add_argument("--model", default=None, help="explicit free-tier model id")
    parser.add_argument("--confirmation-file", default=None,
                        help="JSON record of the operator's current free-tier confirmation")
    parser.add_argument("--results-json", default=None,
                        help="optional path for the safe JSON report")
    parser.add_argument("--timeout-seconds", type=float, default=None,
                        help="override the wall-clock budget (clamped to 15s)")
    namespace = parser.parse_args(argv)
    flags = []
    if namespace.allow_live:
        flags.append(ALLOW_LIVE_FLAG)
    if namespace.confirm_free:
        flags.append(CONFIRM_FREE_TIER_FLAG)
    return {
        "flags": flags,
        "provider": namespace.provider,
        "model": namespace.model,
        "confirmation_file": namespace.confirmation_file,
        "results_json": namespace.results_json,
        "timeout_seconds": namespace.timeout_seconds,
    }


def main(
    argv: list[str] | None = None, *, env: Mapping[str, str] | None = None,
    transport: Any = None, now: datetime | None = None,
    repo_root: str | None = None, stdout: Any = None,
) -> int:
    """Run the harness. Return 0 ok, 1 failed probe, 2 blocked (no request)."""
    options = parse_args(argv)
    moment = now or datetime.now(timezone.utc)
    decision = evaluate(options, env=env, now=moment)
    report = build_report(decision=decision, now=moment,
                          commit=_git_commit(repo_root))

    if not decision.ok:
        status, code = "blocked", 2
    else:
        assert decision.provider is not None and decision.model is not None
        key = _env_value(ALLOWED_PROVIDERS[decision.provider]["env_var"], env)
        budget = WALL_CLOCK_TIMEOUT_SECONDS
        override = options.get("timeout_seconds")
        if isinstance(override, (int, float)) and not isinstance(override, bool) \
                and 0 < override < budget:
            budget = float(override)
        probe = perform_probe(
            provider=decision.provider, model=decision.model, key=key,
            transport=transport if transport is not None else _production_transport(),
            timeout_s=budget)
        report = build_report(decision=decision, now=moment,
                              commit=report["commit"], probe=probe)
        status = probe["status"]
        code = 0 if status == "ok" else 1

    report["status"] = status
    safe = _scrub(report, _all_secrets(env))
    text = json.dumps(safe, sort_keys=True)
    stream = stdout if stdout is not None else sys.stdout
    print(text, file=stream)
    target = options.get("results_json")
    if isinstance(target, str) and target.strip():
        Path(target.strip()).write_text(json.dumps(safe, indent=2, sort_keys=True) + "\n",
                                        encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
