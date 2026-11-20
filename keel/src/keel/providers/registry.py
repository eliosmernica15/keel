"""keel.providers.registry — provider registry, resolution chain, smoke probe.

Default chain (auto): openrouter -> google -> nvidia -> openai-compatible.
Anthropic is opt-in only (--provider anthropic) — see the licensing review's
OPEN-Q1; never a default.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from .anthropic import AnthropicAdapter
from .base import CapabilityRecord, ProviderError, ProviderRequest
from .gemini import GeminiAdapter
from .model_client import ProviderModelClient
from .openai_compatible import OpenAICompatibleAdapter
from .. import settings_store
from ..config_schema import validate as validate_settings
from ..model_ids import ModelIdError, parse_model_ref
from ..provider_catalog import get_provider as catalog_provider

_PROVIDERS: dict[str, CapabilityRecord] = {
    "openrouter": CapabilityRecord(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        env_var="KEEL_OPENROUTER_API_KEY",
        default_model=os.environ.get("KEEL_OPENROUTER_MODEL", "openrouter/auto"),
        supports_tools=True, supports_streaming=True,
        notes="Unified gateway; free models exist (e.g. :free suffixed slugs). "
              "Set KEEL_OPENROUTER_MODEL to pin a model."),
    "nvidia": CapabilityRecord(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
        env_var="KEEL_NVIDIA_API_KEY",
        default_model=os.environ.get("KEEL_NVIDIA_MODEL", "meta/llama-3.1-8b-instruct"),
        supports_tools=True, supports_streaming=True,
        notes="NVIDIA NIM hosted endpoints; free credits on build.nvidia.com. "
              "Set KEEL_NVIDIA_MODEL to the slug you want."),
    "google": CapabilityRecord(
        name="google",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        env_var="KEEL_GOOGLE_API_KEY",
        default_model=os.environ.get("KEEL_GOOGLE_MODEL", "gemini-2.0-flash"),
        supports_tools=True, supports_streaming=True, supports_thinking=True,
        notes="Google AI Studio; free tier, rate-limited. "
              "Set KEEL_GOOGLE_MODEL to override (e.g. gemini-2.5-flash)."),
    "anthropic": CapabilityRecord(
        name="anthropic",
        base_url="https://api.anthropic.com/v1",
        env_var="KEEL_ANTHROPIC_API_KEY",
        default_model=os.environ.get("KEEL_ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        supports_tools=True, supports_streaming=True, supports_thinking=True,
        notes="Anthropic API; opt-in only. Your own key, your terms. "
              "Set KEEL_ANTHROPIC_MODEL to the model id from your console."),
    "openai-compatible": CapabilityRecord(
        name="openai-compatible",
        base_url=os.environ.get("KEEL_COMPAT_BASE_URL", ""),
        env_var="KEEL_COMPAT_API_KEY",
        default_model=os.environ.get("KEEL_COMPAT_MODEL", ""),
        supports_tools=True, supports_streaming=True,
        notes="Generic OpenAI-compatible endpoint; requires KEEL_COMPAT_BASE_URL "
              "and KEEL_COMPAT_MODEL to be usable."),
}

settings_store.apply_stored_keys()

_AUTO_CHAIN = ("openrouter", "google", "nvidia", "openai-compatible")


def _key_for(cap: CapabilityRecord) -> str:
    """Env wins; the settings-store key (explicitly saved by the user) is the
    fallback. Material never leaves this process except into memory and the
    spawned child's env."""
    key = os.environ.get(cap.env_var, "").strip()
    if key:
        return key
    return (settings_store.stored_key(cap.name) or "").strip()


def capability(name: str | None) -> CapabilityRecord | None:
    if not name:
        return None
    return _PROVIDERS.get(name.lower())


def list_providers() -> list[dict]:
    out = []
    for name, cap in _PROVIDERS.items():
        key = _key_for(cap)
        env_var = os.environ.get(cap.env_var, "").strip()
        if not key:
            source = None
        elif env_var:
            source = f"env:{cap.env_var}"
        else:
            source = "settings.json"
        out.append({
            "name": name,
            "configured": bool(key),
            "key_source": source,
            "key_hint": (settings_store.stored_key_hint(name)
                         if source == "settings.json" else None),
            "default_model": cap.default_model,
            "base_url": cap.base_url,
            "opt_in": name == "anthropic",
            "notes": cap.notes,
        })
    return out


def build_adapter(name: str, *, api_key: str | None = None,
                  transport=None):
    cap = _PROVIDERS.get(name)
    if cap is None:
        raise ProviderError(f"unknown provider {name!r} "
                            f"(known: {', '.join(_PROVIDERS)})")
    if name == "anthropic":
        return AnthropicAdapter(cap, api_key=api_key or _key_for(cap),
                                transport=transport)
    if name == "google":
        return GeminiAdapter(cap, api_key=api_key or _key_for(cap),
                             transport=transport)
    if name == "openai-compatible" and not cap.base_url:
        raise ProviderError("openai-compatible requires KEEL_COMPAT_BASE_URL "
                            "(and KEEL_COMPAT_MODEL) to be usable")
    return OpenAICompatibleAdapter(cap, api_key=api_key or _key_for(cap),
                                   transport=transport)


def resolve_chain(requested: str | None) -> list[CapabilityRecord]:
    """Auto: first configured provider in the default chain; explicit: only it."""
    if requested and requested != "auto":
        name = requested.lower()
        if name not in _PROVIDERS:
            raise ProviderError(f"unknown provider {name!r} "
                                f"(known: {', '.join(_PROVIDERS)} | auto)")
        return [_PROVIDERS[name]]
    chain = []
    for name in _AUTO_CHAIN:
        cap = _PROVIDERS.get(name)
        if cap is None:
            continue
        if not _key_for(cap):
            continue
        if name == "openai-compatible" and not cap.base_url:
            continue
        chain.append(cap)
    return chain


def smoke(name: str, *, model: str | None = None,
          transport=None) -> dict:
    """One tiny live request; returns a report dict. Raises ProviderError."""
    name = name.lower()
    if name not in _PROVIDERS:
        raise ProviderError(f"unknown provider {name!r}")
    cap = _PROVIDERS[name]
    adapter = build_adapter(name, transport=transport)
    chosen_model = model or cap.default_model
    t0 = time.monotonic()
    request = ProviderRequest(
        model=chosen_model,
        messages=[{"role": "user", "content":
                   "Reply with exactly the word: pong"}],
        tools=[],
        max_output_tokens=16,
        temperature=0.0,
    )
    text_parts: list[str] = []
    for event in adapter.complete(request):
        if event.get("event") == "text_delta":
            text_parts.append(event.get("text", ""))
    latency_ms = int((time.monotonic() - t0) * 1000)
    return {
        "provider": name,
        "model": chosen_model,
        "base_url": cap.base_url,
        "text": "".join(text_parts),
        "latency_ms": latency_ms,
        "key_source": f"env:{cap.env_var}",
    }


def validate_configuration(doc: dict) -> list[str]:
    """Return configuration diagnostics; values are never included."""
    return [str(item) for item in validate_settings(doc)]


def resolve_provider_model(identifier: str, *,
                           provider_config: dict | None = None) -> dict:
    """Resolve a bare model or provider/model id to an executable adapter.

    Catalog entries are informational. A provider present only in the offline
    catalog is rejected with a clear error; it is never treated as executable.
    """
    try:
        ref = parse_model_ref(identifier)
    except ModelIdError as exc:
        raise ProviderError(str(exc)) from None

    config = provider_config if provider_config is not None \
        else settings_store.get_provider_config()
    configured = str(config.get("defaultProvider") or "").strip().lower()
    default_provider = configured or os.environ.get("KEEL_DEFAULT_PROVIDER", "auto").lower()

    provider = "" if ref.provider in (None, "auto") else ref.provider
    model = ref.model
    auto = not provider

    if not provider and default_provider != "auto":
        provider = default_provider

    cap = _PROVIDERS.get(provider) if provider else None
    if provider and cap is None:
        if catalog_provider(provider) is not None:
            raise ProviderError(
                f"provider {provider!r} is listed in the offline catalog "
                "but has no executable Keel runtime adapter")
        raise ProviderError(
            f"unknown provider {provider!r} "
            f"(runnable: {', '.join(sorted(_PROVIDERS))})")

    if cap is None:
        chain = resolve_chain(None)
        if not chain:
            raise ProviderError(
                "no configured runtime provider; set a provider key or choose "
                "a catalog-only provider is not sufficient to execute")
        cap = chain[0]
        provider = cap.name

    chosen_model = model or cap.default_model
    if not chosen_model:
        raise ProviderError(
            f"provider {provider!r} requires an explicit model id")
    catalog_entry = catalog_provider(provider)
    return {
        "provider": provider,
        "model": chosen_model,
        "qualified": f"{provider}/{chosen_model}",
        "runtime_adapter": provider,
        "catalog_listed": catalog_entry is not None,
        "default_used": not model,
    }
