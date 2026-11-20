"""M2: JSONC config, schema, provider/model ids and offline catalog."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from keel import settings, settings_store
from keel.config_schema import load_schema, validate
from keel.jsonc import JsoncError, loads as jsonc_loads
from keel.model_ids import parse_model_ref
from keel.providers.registry import (ProviderError, list_providers,
                                     resolve_provider_model,
                                     validate_configuration)
from keel.provider_catalog import (catalog_info, get_provider, load_catalog,
                                   model_ids, provider_ids)
from keel.resources import resource_path

ROOT = Path(__file__).resolve().parents[1]


def test_jsonc_supports_comments_and_trailing_commas():
    doc = jsonc_loads('''{
      // provider selection
      "defaultProvider": "google", /* inline */
      "model": "google/gemini-2.0-flash", // comment with // inside
      "providerConfig": { "models": { "google": "gemini-2.0-flash", }, },
    }''')
    assert doc["defaultProvider"] == "google"
    assert doc["providerConfig"]["models"]["google"] == "gemini-2.0-flash"


def test_jsonc_preserves_comment_markers_inside_strings():
    assert jsonc_loads('{"url": "https://example.com/a//b"}')["url"] == \
        "https://example.com/a//b"


def test_jsonc_reports_line_and_column_without_values():
    with pytest.raises(JsoncError) as exc:
        jsonc_loads('{\n  "model": "x",\n  "broken" :: 1\n}')
    message = str(exc.value)
    assert "line 3" in message
    assert "broken" not in message


def test_settings_resolve_accepts_jsonc(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "settings.json").write_text(
        '{\n  // M2 JSONC\n  "defaultProvider": "google",\n}\n',
        encoding="utf-8")
    result = settings.resolve(state_root=state, cwd=tmp_path)
    assert result.value["defaultProvider"] == "google"
    assert all(d.code != "settings_json_invalid" for d in result.diagnostics)


def test_settings_store_accepts_jsonc(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{\n  // saved by user\n  "ui": {"theme": "dark"},\n}\n',
                    encoding="utf-8")
    # conftest globally stubs settings_store.load for fake-transport tests;
    # verify the JSONC read path directly instead.
    assert settings_store._parse_bytes(path.read_bytes())["ui"]["theme"] == "dark"


def test_schema_validates_supported_configuration():
    schema = load_schema()
    assert validate({
        "model": "google/gemini-2.0-flash",
        "defaultProvider": "google",
        "providerConfig": {"customEndpoints": {
            "local": {"baseUrl": "http://127.0.0.1:11434/v1"}}},
    }, schema=schema) == []


def test_schema_rejects_invalid_configuration_without_values():
    problems = validate({
        "providerConfig": {"customEndpoints": {
            "local": {"unexpected": "super-secret-value"}}},
    })
    text = " ".join(str(p) for p in problems)
    assert "not supported" in text
    assert "super-secret-value" not in text


def test_registry_validation_reports_no_secrets():
    problems = validate_configuration({"permissions": {"allow": 7}})
    assert problems
    assert all("7" not in p for p in problems)


def test_offline_catalog_loads_without_network():
    info = catalog_info()
    assert info.provider_count == len(provider_ids())
    assert info.provider_count >= 75
    assert info.model_count > 0
    assert info.source_name == "models.dev"
    assert info.license == "MIT"
    doc = load_catalog()
    assert doc["source"]["attribution"]
    assert "informational" in doc["notice"]


def test_catalog_entries_distinguished_from_runtime_adapters():
    assert "openai" in provider_ids()  # catalog-only
    assert model_ids("openai")
    runtime = {p["name"] for p in list_providers()}
    assert runtime == {"openrouter", "google", "nvidia", "anthropic", "openai-compatible"}
    assert get_provider("not-a-real-provider") is None


def test_provider_model_identifiers():
    assert parse_model_ref("google/gemini-2.0-flash").qualified == \
        "google/gemini-2.0-flash"
    assert parse_model_ref("gemini-2.0-flash").provider is None


def test_resolver_existing_runtime_adapter():
    result = resolve_provider_model(
        "google/gemini-2.0-flash",
        provider_config={"defaultProvider": "auto"})
    assert result["provider"] == "google"
    assert result["model"] == "gemini-2.0-flash"
    assert result["qualified"] == "google/gemini-2.0-flash"
    assert result["runtime_adapter"] == "google"


def test_resolver_bare_model_uses_configured_default():
    result = resolve_provider_model(
        "custom-model", provider_config={"defaultProvider": "openrouter"})
    assert result["provider"] == "openrouter"
    assert result["model"] == "custom-model"
    assert result["default_used"] is False


def test_resolver_rejects_catalog_only_provider():
    with pytest.raises(ProviderError) as exc:
        resolve_provider_model("openai/gpt-example",
                               provider_config={"defaultProvider": "auto"})
    message = str(exc.value)
    assert "offline catalog" in message
    assert "no executable" in message


def test_resolver_rejects_unknown_provider():
    with pytest.raises(ProviderError) as exc:
        resolve_provider_model("nowhere/model",
                               provider_config={"defaultProvider": "auto"})
    assert "unknown provider" in str(exc.value)


def test_resolver_preserves_custom_endpoint():
    result = resolve_provider_model("openai-compatible/local-model",
                                    provider_config={
                                        "defaultProvider": "auto",
                                        "customEndpoints": {
                                            "local": {
                                                "baseUrl": "http://127.0.0.1:11434/v1"}}})
    assert result["qualified"] == "openai-compatible/local-model"
    assert result["runtime_adapter"] == "openai-compatible"


def test_m2_resources_declared_in_packaging():
    spec = (ROOT / "desktop-app" / "sidecar.spec").read_text(encoding="utf-8")
    assert 'resources/schema' in spec
    assert 'resources/catalog' in spec
    assert (resource_path("schema", "keel.settings.schema.json")).is_file()
    assert (resource_path("catalog", "providers.json")).is_file()
    assert (resource_path("catalog", "LICENSE.models-dev.txt")).is_file()
