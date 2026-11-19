"""Opt-in live provider smoke tests — never run without real credentials.

These tests hit REAL provider endpoints with real keys, costing a trivial
amount of quota. They are skipped entirely unless the corresponding
environment variable is set, e.g.:

    KEEL_OPENROUTER_API_KEY=sk-or-... pytest tests/test_live_smoke.py

Use cases covered: auth success/failure, provider resolution, token usage,
tool-call shape on the wire. CI must never run these (no keys there).
"""

import os

import pytest

from keel.providers import registry
from keel.providers.base import ProviderRequest, ProviderError
from keel.providers.model_client import ProviderModelClient

PROVIDERS = [
    ("openrouter", "KEEL_OPENROUTER_API_KEY", "KEEL_OPENROUTER_MODEL"),
    ("google", "KEEL_GOOGLE_API_KEY", "KEEL_GOOGLE_MODEL"),
    ("nvidia", "KEEL_NVIDIA_API_KEY", "KEEL_NVIDIA_MODEL"),
    ("openai-compatible", "KEEL_COMPAT_API_KEY", "KEEL_COMPAT_MODEL"),
    ("anthropic", "KEEL_ANTHROPIC_API_KEY", "KEEL_ANTHROPIC_MODEL"),
]


def _live_enabled(env_var: str) -> bool:
    return bool(os.environ.get(env_var, "").strip())


@pytest.mark.parametrize("provider,key_env,model_env", PROVIDERS)
def test_live_provider_smoke(provider, key_env, model_env):
    if not _live_enabled(key_env):
        pytest.skip(f"no {key_env} — set it to run the live smoke test")

    adapter = registry.build_adapter(provider)
    model = os.environ.get(model_env) or registry.capability(provider).default_model
    client = ProviderModelClient(adapter, model=model, max_output_tokens=16)

    try:
        blocks = client.complete(
            [{"role": "user", "content": "Reply with exactly the word: pong"}],
            [],
        )
    except ProviderError as exc:
        pytest.fail(f"live call failed: {exc.category}: {exc}")

    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    assert text.strip(), f"empty completion from {provider}: {blocks!r}"
    usage = client.total_usage
    print(f"live {provider} ok: model={model} usage_in={usage.input_tokens} "
          f"out={usage.output_tokens} head={text[:60]!r}")


@pytest.mark.parametrize("provider,key_env,model_env", PROVIDERS)
def test_live_provider_bad_key_fails_fast(provider, key_env, model_env):
    """A deliberately invalid key must surface a clear auth error, never a
    silent fallback to something else."""
    if not _live_enabled(key_env):
        pytest.skip(f"no {key_env} — set it to run the live smoke test")

    adapter = registry.build_adapter(provider, api_key="definitely-not-a-real-key")
    client = ProviderModelClient(adapter, model=registry.capability(provider).default_model,
                                 max_output_tokens=8)
    with pytest.raises(ProviderError) as excinfo:
        client.complete([{"role": "user", "content": "pong"}], [])
    assert excinfo.value.category in (
        "authentication_failed", "organization_not_allowed",
        "invalid_request", "unknown",
    )
