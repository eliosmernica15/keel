"""Provider configuration contracts — E6.1, E6.5, E6.8, E6.10.

Tests-first contract for the additive, stdlib-only module
``keel.provider_contracts``. Every assertion here is runnable offline: no
network, no credentials, no installed provider packages. The module owns the
*configuration* contract only — it never sends a request.

Coverage map:
  * E6.1  write-only keys, masked hints, name-only audit records
  * E6.5  third-party provider descriptors, installed catalog, user approval
  * E6.8  typed per-model capabilities, image fallback, unverified-claim warning
  * E6.10 compat switches, per-model overrides, honest request adaptation
"""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from keel.provider_contracts import (  # noqa: E402
    CATALOG_CAPABILITIES,
    MASK_CHAR,
    MAX_TOKEN_KEYS,
    PROTOCOL_SWITCHES,
    PROTOCOLS,
    SCHEMA_VERSION,
    STREAMING_FORMATS,
    SWITCH_NAMES,
    THINKING_KEYS,
    TOOL_DIALECT_HINTS,
    UNVERIFIED_CLAIMS_WARNING,
    AdaptedRequest,
    CompatProfile,
    CompatSwitches,
    ModelCapabilities,
    ProviderContractError,
    ProviderDescriptor,
    ProviderRegistry,
    SecretDescriptor,
    adapt_request,
    capability_report,
    capability_warning,
    credential_audit_record,
    describe_secret,
    effective_input_types,
    image_preflight_message,
    merge_input_types,
    provider_from_dict,
    redact_descriptor,
    resolve_switches,
    search_catalog,
    secret_appears_in,
    validate_provider_descriptor,
    validate_switch,
    without_image,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SECRET = "sk-or-v1-" + "abc123XYZ" * 3 + "TAIL"


def caps(**overrides) -> ModelCapabilities:
    base = dict(
        model_id="model-a",
        input_types=frozenset({"text"}),
        context_window=8192,
        max_output=2048,
        tool_call_dialect="json",
        supports_reasoning=True,
    )
    base.update(overrides)
    return ModelCapabilities(**base)


def provider(**overrides) -> ProviderDescriptor:
    base = dict(
        id="acme-gateway",
        base_url="https://api.acme.example/v1",
        protocol="openai-chat-completions",
        models=("model-a", "model-b"),
        capabilities=frozenset({"text", "tools"}),
        user_approved=True,
    )
    base.update(overrides)
    return ProviderDescriptor(**base)


# ---------------------------------------------------------------------------
# E6.1 — write-only credentials
# ---------------------------------------------------------------------------

def test_mask_secret_long_reveals_only_edges():
    hint = describe_secret("KEEL_ACME_KEY", SECRET).masked_hint
    assert hint.startswith("KEEL_ACME_KEY: ")
    preview = hint.split(": ", 1)[1]
    assert preview[:5] == SECRET[:5]
    assert preview[-4:] == SECRET[-4:]
    run = len(preview) - 9
    assert preview[5:5 + run] == MASK_CHAR * run
    assert run >= 8
    assert SECRET not in hint


def test_mask_secret_short_is_all_dots():
    assert describe_secret("k", "abc", source="settings").masked_hint == (
        "k: " + MASK_CHAR * 3)
    assert describe_secret("k", "").masked_hint == "k: "


def test_mask_secret_boundary_at_seventeen_code_points():
    hint17 = describe_secret("k", "a" * 17).masked_hint.split(": ", 1)[1]
    assert hint17 == "aaaaa" + MASK_CHAR * 8 + "aaaa"
    hint16 = describe_secret("k", "b" * 16).masked_hint.split(": ", 1)[1]
    assert hint16 == MASK_CHAR * 16


def test_mask_secret_counts_unicode_code_points_not_bytes():
    secret = "\u00e9" * 9 + "\U0001f600" * 9  # 18 code points
    hint = describe_secret("u", secret).masked_hint.split(": ", 1)[1]
    assert hint[:5] == "\u00e9" * 5
    assert hint[-4:] == "\U0001f600" * 4
    assert hint[5:-4] == MASK_CHAR * 9
    assert secret not in hint


def test_secret_never_appears_in_descriptors_or_redactions():
    desc = describe_secret("KEEL_ACME_KEY", SECRET)
    returned = (desc, desc.to_dict(), redact_descriptor(desc),
                credential_audit_record(desc), capability_warning())
    for structure in returned:
        assert not secret_appears_in(structure, SECRET), structure
    assert not any(SECRET == str(value) for value in vars(desc).values())


def test_redact_descriptor_exposes_only_public_fields():
    desc = describe_secret("KEEL_ACME_KEY", SECRET, source="settings",
                           reference="settings://credentials/acme")
    public = redact_descriptor(desc)
    assert set(public) == {"name", "source", "masked_hint", "reference"}
    assert public["name"] == "KEEL_ACME_KEY"
    assert public["source"] == "settings"
    assert public["reference"] == "settings://credentials/acme"
    assert not {"secret", "value", "api_key", "plaintext"} & set(public)


def test_audit_record_records_name_only():
    desc = describe_secret("KEEL_ACME_KEY", SECRET)
    record = credential_audit_record(desc)
    assert record == {"event": "credential.write", "name": "KEEL_ACME_KEY"}
    assert SECRET not in json.dumps(record)
    assert desc.masked_hint not in json.dumps(record)


def test_secret_appears_in_walks_nested_structures():
    needle = "TOPSECRET12345"
    assert secret_appears_in({"a": [1, {"b": (needle,)}]}, needle)
    assert secret_appears_in(f"prefix {needle} suffix", needle)
    assert not secret_appears_in({"a": "safe"}, needle)
    assert not secret_appears_in(None, needle)


@pytest.mark.parametrize("name,secret,source", [
    ("", SECRET, "env"),
    ("K", SECRET, "keychain"),
    ("K", 12345, "env"),
    ("K", SECRET, ""),
])
def test_secret_descriptor_validation(name, secret, source):
    with pytest.raises((ValueError, TypeError)):
        describe_secret(name, secret, source=source)


def test_secret_descriptor_rejects_forged_masked_hint_with_value():
    with pytest.raises(ValueError):
        SecretDescriptor(name="k", source="env", masked_hint=SECRET,
                         reference="ref")


# ---------------------------------------------------------------------------
# E6.5 — third-party provider picker
# ---------------------------------------------------------------------------

def test_provider_descriptor_valid_and_frozen():
    desc = provider()
    assert validate_provider_descriptor(desc) is None
    assert desc.models == ("model-a", "model-b")
    assert isinstance(desc.models, tuple)
    assert isinstance(desc.capabilities, frozenset)
    with pytest.raises(FrozenInstanceError):
        desc.id = "other"


@pytest.mark.parametrize("url", [
    "http://api.acme.example/v1",
    "api.acme.example/v1",
    "ftp://api.acme.example",
    "https://",
    "https://user:pass@api.acme.example",
    "file:///etc/passwd",
])
def test_endpoint_must_be_https_without_credentials(url):
    with pytest.raises(ProviderContractError, match="https"):
        provider(base_url=url)


def test_unknown_protocol_rejected_with_valid_list():
    with pytest.raises(ProviderContractError) as exc:
        provider(protocol="mystery-protocol")
    message = str(exc.value)
    for valid in PROTOCOLS:
        assert valid in message


@pytest.mark.parametrize("models", [(), ("",), ("model-a", "")])
def test_model_id_is_required(models):
    with pytest.raises(ProviderContractError, match="model"):
        provider(models=models)


@pytest.mark.parametrize("identifier", ["ACME", "-acme", "ac me", "", "a/b"])
def test_provider_id_is_permanent_lowercase_slug(identifier):
    with pytest.raises(ProviderContractError):
        provider(id=identifier)


@pytest.mark.parametrize("flag", ["bundled", "paid"])
def test_bundled_and_paid_providers_are_not_selectable(flag):
    with pytest.raises(ProviderContractError, match=flag):
        provider(**{flag: True})


def test_explicit_user_approval_is_required_to_register():
    registry = ProviderRegistry()
    with pytest.raises(ProviderContractError, match="approval"):
        registry.add(provider(user_approved=False))
    assert registry.list() == ()
    added = registry.add(provider(user_approved=True))
    assert added.id == "acme-gateway"
    assert registry.get("acme-gateway") is added


def test_catalog_search_by_capability_filters_unapproved_kinds():
    entries = [
        provider(id="alpha", capabilities=frozenset({"text", "image"})),
        provider(id="beta", capabilities=frozenset({"text"})),
        SimpleNamespace(id="bundled", capabilities=frozenset({"image"}),
                        bundled=True, paid=False, protocol=PROTOCOLS[0]),
        SimpleNamespace(id="paid", capabilities=frozenset({"image"}),
                        bundled=False, paid=True, protocol=PROTOCOLS[0]),
    ]
    found = search_catalog(entries, capability="image")
    assert [entry.id for entry in found] == ["alpha"]
    assert [entry.id for entry in search_catalog(entries, protocol=PROTOCOLS[1])] == []
    assert {entry.id for entry in search_catalog(entries)} == {"alpha", "beta"}


def test_unknown_catalog_capability_lists_valid_names():
    with pytest.raises(ProviderContractError) as exc:
        search_catalog([provider()], capability="telepathy")
    for valid in CATALOG_CAPABILITIES:
        assert valid in str(exc.value)


def test_one_protocol_per_provider_and_gateway_needs_two_ids():
    with pytest.raises(ProviderContractError):
        provider(protocol=[PROTOCOLS[0], PROTOCOLS[2]])
    registry = ProviderRegistry()
    registry.add(provider(id="acme-openai", protocol=PROTOCOLS[0]))
    registry.add(provider(id="acme-anthropic", protocol=PROTOCOLS[2]))
    assert {p.id for p in registry.list()} == {"acme-openai", "acme-anthropic"}


def test_registry_duplicate_remove_and_no_rename():
    registry = ProviderRegistry()
    registry.add(provider())
    with pytest.raises(ProviderContractError, match="already"):
        registry.add(provider())
    assert not hasattr(registry, "rename")
    registry.remove("acme-gateway")
    assert registry.list() == ()
    with pytest.raises(ProviderContractError, match="unknown"):
        registry.remove("acme-gateway")


def test_provider_from_dict_builds_and_validates_descriptor():
    desc = provider_from_dict({
        "id": "gamma-ai",
        "base_url": "https://gamma.example/api",
        "protocol": "gemini-api",
        "models": ["gem-pro"],
        "capabilities": ["text", "reasoning"],
        "user_approved": True,
        "credential": {
            "name": "GAMMA_KEY", "source": "env",
            "masked_hint": "GAMMA_KEY: " + MASK_CHAR * 4,
            "reference": "env:GAMMA_KEY",
        },
    })
    assert isinstance(desc.credential, SecretDescriptor)
    assert desc.protocol == "gemini-api"
    with pytest.raises(ProviderContractError):
        provider_from_dict({"id": "broken", "base_url": "http://x"})


# ---------------------------------------------------------------------------
# E6.8 — per-model capabilities
# ---------------------------------------------------------------------------

def test_capabilities_valid_defaults():
    model = ModelCapabilities(model_id="m")
    assert model.input_types == frozenset({"text"})
    assert model.context_window > 0
    assert 0 < model.max_output <= model.context_window
    assert model.tool_call_dialect in TOOL_DIALECT_HINTS
    assert model.supports_reasoning is False


@pytest.mark.parametrize("field,value", [
    ("context_window", 0), ("context_window", -5), ("context_window", True),
    ("context_window", "8192"),
    ("max_output", 0), ("max_output", 999999), ("max_output", False),
])
def test_capabilities_reject_invalid_numeric_fields(field, value):
    with pytest.raises((ValueError, TypeError)):
        caps(**{field: value})


@pytest.mark.parametrize("field,value", [
    ("input_types", frozenset()),
    ("input_types", frozenset({"audio"})),
    ("tool_call_dialect", "telepathy"),
    ("tool_call_dialect", ""),
])
def test_capabilities_reject_unknown_input_type_or_dialect(field, value):
    with pytest.raises(ValueError):
        caps(**{field: value})


def test_image_limits_require_image_input():
    with pytest.raises(ValueError, match="image"):
        caps(max_images=2)
    with pytest.raises(ValueError, match="image"):
        caps(image_max_bytes=1024)
    model = caps(input_types=frozenset({"text", "image"}), max_images=2,
                 image_max_bytes=1024)
    assert model.max_images == 2


def test_without_image_clears_image_limits():
    model = caps(input_types=frozenset({"text", "image"}), max_images=3,
                 image_max_bytes=4096)
    text_only = without_image(model)
    assert text_only.input_types == frozenset({"text"})
    assert text_only.max_images is None
    assert text_only.image_max_bytes is None
    assert model.max_images == 3  # immutable original untouched


def test_merge_input_types_never_drops_images():
    merged = merge_input_types(frozenset({"text"}), {"text", "image"}, ["text"])
    assert merged == frozenset({"text", "image"})
    with pytest.raises(ValueError):
        merge_input_types({"audio"})


def test_effective_input_types_uses_route_default_and_catalog_union():
    model = caps(input_types=frozenset({"text"}))
    effective = effective_input_types(
        model, route_default=frozenset({"text"}),
        catalog_types=frozenset({"text", "image"}))
    assert "image" in effective
    assert effective == frozenset({"text", "image"})


def test_capability_report_carries_unverified_claim_warning():
    report = capability_report(caps())
    assert report["model_id"] == "model-a"
    assert report["warning"] == UNVERIFIED_CLAIMS_WARNING
    assert "not verified" in UNVERIFIED_CLAIMS_WARNING.lower()
    assert capability_warning() == UNVERIFIED_CLAIMS_WARNING
    assert SCHEMA_VERSION == "1.0"


# ---------------------------------------------------------------------------
# E6.10 — request compatibility switches
# ---------------------------------------------------------------------------

def test_switch_table_is_consistent():
    assert set(SWITCH_NAMES) == set(PROTOCOL_SWITCHES[PROTOCOLS[0]])
    for proto in PROTOCOLS:
        assert PROTOCOL_SWITCHES[proto] <= set(SWITCH_NAMES)
        assert PROTOCOL_SWITCHES[proto]
    assert "supports_developer_role" not in PROTOCOL_SWITCHES["anthropic-messages"]
    assert "thinking_field" not in PROTOCOL_SWITCHES["gemini-api"]


@pytest.mark.parametrize("name", ["max_tokens_field", "thinking_field", "streaming_format"])
def test_empty_switch_value_refused(name):
    with pytest.raises(ProviderContractError, match="empty"):
        validate_switch(name, "", protocol=PROTOCOLS[0])


def test_unknown_switch_name_refused_with_valid_list():
    with pytest.raises(ProviderContractError) as exc:
        validate_switch("temperature", 0.5, protocol=PROTOCOLS[0])
    for valid in SWITCH_NAMES:
        assert valid in str(exc.value)


def test_thinking_format_alias_resolves_to_canonical_name():
    assert validate_switch("thinking_format", "thinking",
                           protocol="anthropic-messages") == "thinking_field"


def test_switch_valid_only_for_declaring_protocols():
    with pytest.raises(ProviderContractError, match="protocol"):
        validate_switch("supports_developer_role", True,
                        protocol="anthropic-messages")
    with pytest.raises(ProviderContractError, match="protocol"):
        validate_switch("thinking_field", "thinking", protocol="gemini-api")
    assert validate_switch("supports_developer_role", True,
                           protocol=PROTOCOLS[0]) == "supports_developer_role"


@pytest.mark.parametrize("name,value", [
    ("supports_developer_role", "yes"),
    ("supports_developer_role", 1),
    ("max_tokens_field", "9bad-name"),
    ("thinking_field", "has space"),
    ("streaming_format", "websocket"),
])
def test_switch_value_types_and_allowlists(name, value):
    with pytest.raises(ProviderContractError):
        validate_switch(name, value, protocol=PROTOCOLS[0])


def test_compat_profile_field_by_field_override():
    profile = CompatProfile(
        protocol="openai-chat-completions",
        defaults=CompatSwitches(supports_developer_role=True,
                                max_tokens_field="max_tokens",
                                thinking_field="reasoning_effort",
                                streaming_format="sse"),
        overrides={"model-b": CompatSwitches(max_tokens_field="max_completion_tokens")},
    )
    base = profile.for_model("model-a")
    override = profile.for_model("model-b")
    assert base.max_tokens_field == "max_tokens"
    assert override.max_tokens_field == "max_completion_tokens"
    assert override.supports_developer_role is True  # inherited field-by-field
    assert override.thinking_field == "reasoning_effort"
    assert override.streaming_format == "sse"
    assert profile.for_model("model-a") == base


def test_compat_profile_rejects_switch_unsupported_by_its_protocol():
    with pytest.raises(ProviderContractError):
        CompatProfile(protocol="gemini-api",
                      defaults=CompatSwitches(supports_developer_role=True))
    with pytest.raises(ProviderContractError):
        CompatProfile(protocol="openai-chat-completions",
                      defaults=CompatSwitches(streaming_format="nope"))


def test_resolve_switches_merges_non_none_fields_only():
    resolved = resolve_switches(
        CompatSwitches(max_tokens_field="max_tokens", thinking_field="thinking"),
        CompatSwitches(max_tokens_field="max_output_tokens"),
        protocol="anthropic-messages")
    assert resolved.max_tokens_field == "max_output_tokens"
    assert resolved.thinking_field == "thinking"
    assert resolved.supports_developer_role is None


def _openai_request():
    return {
        "model": "model-a",
        "messages": [
            {"role": "developer", "content": "be concise"},
            {"role": "user", "content": "hi"},
        ],
        "max_tokens": 9000,
        "thinking": {"effort": "high"},
        "stream": True,
    }


def test_adapt_request_openai_chat_completions_style():
    switches = CompatSwitches(supports_developer_role=True,
                              max_tokens_field="max_tokens",
                              thinking_field="reasoning_effort",
                              streaming_format="sse")
    result = adapt_request(caps(max_output=4096), _openai_request(),
                           switches=switches)
    assert isinstance(result, AdaptedRequest)
    req = result.request
    assert req["messages"][0]["role"] == "developer"
    assert req["reasoning_effort"] == {"effort": "high"}
    assert "thinking" not in req
    assert req["max_tokens"] == 4096
    assert req["stream"] is True
    assert any("max output" in note.lower() for note in result.adjustments)
    assert any("reasoning_effort" in note for note in result.adjustments)


def test_adapt_request_openai_responses_style():
    request = _openai_request()
    request["max_tokens"] = 100
    switches = CompatSwitches(supports_developer_role=True,
                              max_tokens_field="max_completion_tokens",
                              thinking_field="reasoning",
                              streaming_format="sse")
    result = adapt_request(caps(), request, switches=switches)
    assert result.request["max_completion_tokens"] == 100
    assert "max_tokens" not in result.request
    assert result.request["reasoning"] == {"effort": "high"}
    assert result.request["messages"][0]["role"] == "developer"


def test_adapt_request_anthropic_messages_style():
    switches = CompatSwitches(max_tokens_field="max_tokens",
                              thinking_field="thinking",
                              streaming_format="anthropic-sse")
    result = adapt_request(caps(), _openai_request(), switches=switches)
    assert result.request["messages"][0]["role"] == "system"
    assert any("developer" in note.lower() for note in result.adjustments)
    assert result.request["thinking"] == {"effort": "high"}
    assert result.request["stream"] is True
    assert any("anthropic-sse" in note for note in result.adjustments)


def test_adapt_request_gemini_api_style_removes_thinking_with_note():
    switches = CompatSwitches(max_tokens_field="maxOutputTokens",
                              streaming_format="gemini-sse")
    result = adapt_request(caps(), _openai_request(), switches=switches)
    assert result.request["maxOutputTokens"] == 2048
    assert "max_tokens" not in result.request
    assert "thinking" not in result.request
    assert any("thinking" in note.lower() for note in result.adjustments)
    assert result.request["messages"][0]["role"] == "system"


def test_unsupported_feature_degrades_honestly_without_silent_drop():
    switches = CompatSwitches(max_tokens_field="max_tokens",
                              streaming_format="none")
    result = adapt_request(caps(), _openai_request(), switches=switches)
    assert result.request["stream"] is False
    assert any("stream" in note.lower() for note in result.adjustments)
    assert result.adjustments  # every change is reported


def test_adapt_request_is_pure_and_does_not_mutate_input():
    request = _openai_request()
    snapshot = copy.deepcopy(request)
    switches = CompatSwitches(supports_developer_role=False,
                              max_tokens_field="max_output_tokens",
                              thinking_field=None,
                              streaming_format="sse")
    result = adapt_request(caps(), request, switches=switches)
    assert request == snapshot
    assert result.request is not request


def test_adapt_request_uses_profile_per_model_switches():
    profile = CompatProfile(
        protocol="anthropic-messages",
        defaults=CompatSwitches(max_tokens_field="max_tokens",
                                thinking_field="thinking",
                                streaming_format="sse"),
        overrides={"model-b": CompatSwitches(max_tokens_field="max_output_tokens")},
    )
    result = adapt_request(caps(model_id="model-b"), _openai_request(),
                           profile=profile)
    assert result.request["max_output_tokens"] == 2048
    assert "max_tokens" not in result.request


@pytest.mark.parametrize("field", MAX_TOKEN_KEYS)
def test_all_known_max_token_fields_are_recognised(field):
    request = {"messages": [], field: 10}
    switches = CompatSwitches(max_tokens_field="max_tokens")
    result = adapt_request(caps(), request, switches=switches)
    assert result.request["max_tokens"] == 10


@pytest.mark.parametrize("field", THINKING_KEYS)
def test_all_known_thinking_fields_are_recognised(field):
    request = {"messages": [], field: {"effort": "low"}}
    switches = CompatSwitches(thinking_field="reasoning_config")
    result = adapt_request(caps(), request, switches=switches)
    assert result.request["reasoning_config"] == {"effort": "low"}
    assert field not in result.request


def test_image_preflight_refuses_before_send_and_never_drops_images():
    request = {
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "what is this?"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
        ]}],
    }
    message = image_preflight_message(caps(), request)
    assert message is not None
    assert "image" in message.lower() and "model-a" in message
    result = adapt_request(caps(), request)
    assert result.request == request  # images preserved, never silently dropped
    assert any("image" in note.lower() for note in result.adjustments)
    assert image_preflight_message(
        caps(input_types=frozenset({"text", "image"})), request) is None


def test_unsupported_reasoning_claim_is_reported():
    request = {"messages": [], "thinking": {"effort": "high"}}
    result = adapt_request(caps(supports_reasoning=False), request,
                           switches=CompatSwitches(thinking_field="thinking"))
    assert any("reason" in note.lower() for note in result.adjustments)
