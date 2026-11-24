"""Unit tests for the cross-module typed contracts (audit gaps G1, G3, G4).

Every test uses the real backend modules and real dataclasses; no module under
test is edited or mocked. The helpers are offline and stdlib-only.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pytest

KEEL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KEEL_ROOT / "src"))

from keel import backend_contracts as c  # noqa: E402
from keel import backend_hub as hub  # noqa: E402
from keel import e3_backend, e6_x5_x6_backend, small_groups_backend  # noqa: E402


@dataclass(frozen=True)
class _Sample:
    name: str
    tags: tuple[str, ...]


def test_encode_produces_canonical_jsonable_envelope():
    envelope = c.encode(_Sample("a", ("x", "y")))
    assert envelope == {
        "type": "_Sample",
        "fields": {"name": "a", "tags": ["x", "y"]},
    }
    assert c.is_envelope(envelope)
    assert c.encode({"b": 1, "a": ("x",)}) == {"b": 1, "a": ["x"]}
    assert c.encode(42) == 42
    assert not c.is_envelope({"type": "X", "fields": {}, "extra": 1})


def test_hub_serialisation_and_contract_encoder_are_the_same_shape():
    route = e3_backend.parse_model_route("anthropic/claude-sonnet-4")
    assert hub._jsonable(route) == c.encode(route)


def test_decode_envelope_returns_minimal_dict_and_guards_type():
    envelope = c.encode(_Sample("a", ("x",)))
    assert c.decode_envelope(envelope) == {"name": "a", "tags": ["x"]}
    assert c.decode_envelope(envelope, expected_type="_Sample") == {
        "name": "a", "tags": ["x"]}
    with pytest.raises(c.BackendContractError):
        c.decode_envelope(envelope, expected_type="ModelRoute")
    with pytest.raises(c.BackendContractError):
        c.decode_envelope({"type": "X"})


def test_decode_envelope_recurses_into_nested_envelopes():
    envelope = {"type": "Outer", "fields": {
        "inner": c.encode(_Sample("n", ())),
        "items": [c.encode(_Sample("m", ("t",)))],
    }}
    assert c.decode_envelope(envelope) == {
        "inner": {"name": "n", "tags": []},
        "items": [{"name": "m", "tags": ["t"]}],
    }


def test_rehydrate_rebuilds_real_model_route_accepted_by_typed_consumer():
    envelope = c.encode(e3_backend.parse_model_route("anthropic/claude-sonnet-4"))
    rebuilt = c.rehydrate(envelope, e3_backend.ModelRoute)
    assert isinstance(rebuilt, e3_backend.ModelRoute)
    assert str(rebuilt) == "anthropic/claude-sonnet-4"
    allow = e3_backend.ModelRouteAllowlist(
        True, frozenset({"anthropic/claude-sonnet-4"}))
    # The old bare dict was rejected; the rehydrated object is accepted.
    with pytest.raises(e3_backend.RouteError):
        e3_backend.check_route(allow, envelope)
    assert e3_backend.check_route(allow, rebuilt) is None


def test_rehydrate_restores_frozenset_from_historical_repr_fallback():
    allow = e3_backend.ModelRouteAllowlist(
        True, frozenset({"anthropic/claude-sonnet-4"}))
    envelope = c.encode(allow)
    assert isinstance(envelope["fields"]["routes"], str)
    rebuilt = c.rehydrate(envelope, e3_backend.ModelRouteAllowlist)
    assert rebuilt == allow
    route = c.rehydrate(
        c.encode(e3_backend.parse_model_route("anthropic/claude-sonnet-4")),
        e3_backend.ModelRoute)
    assert e3_backend.check_route(rebuilt, route) is None


def test_rehydrate_uses_annotation_for_dict_target_and_fails_closed():
    assert c.coerce_value(c.encode(_Sample("z", ())), _Sample) == _Sample("z", ())
    assert c.coerce_value({"provider": "anthropic", "model": "m"}, dict) == {
        "provider": "anthropic", "model": "m"}
    with pytest.raises(c.BackendContractError):
        c.rehydrate(c.encode(_Sample("z", ())), e3_backend.ModelRoute)


def test_model_id_converters_cover_all_three_representations():
    reference = small_groups_backend.ModelReference.parse(
        "anthropic/claude-sonnet-4#fast")
    route = e3_backend.parse_model_route("anthropic/claude-sonnet-4")
    discovery = e6_x5_x6_backend.parse_models_response(
        {"data": [{"id": "claude-sonnet-4"}]})

    from_ref = c.from_model_reference(reference)
    from_route = c.from_model_route(route)
    from_envelope = c.from_model_route(c.encode(route))
    from_discovery = c.from_discovery(discovery)

    assert from_ref == c.ModelId("anthropic", "claude-sonnet-4", "fast")
    assert from_route == from_envelope == c.ModelId(
        "anthropic", "claude-sonnet-4")
    assert from_discovery == c.ModelId("", "claude-sonnet-4")
    assert from_ref.as_dict() == {
        "provider": "anthropic", "model": "claude-sonnet-4", "variant": "fast"}
    assert c.to_route(from_route) == "anthropic/claude-sonnet-4"
    assert c.to_discovery(from_discovery) == "claude-sonnet-4"
    assert c.to_model_reference(from_route)["provider"] == "anthropic"
    with pytest.raises(c.BackendContractError):
        c.to_route(from_discovery)  # a discovery id has no provider to route with


def test_model_id_from_string_and_any_dispatch():
    assert c.from_string("anthropic/claude-sonnet-4#fast").qualified == (
        "anthropic/claude-sonnet-4")
    assert c.from_string("claude-sonnet-4") == c.ModelId("", "claude-sonnet-4")
    route = e3_backend.parse_model_route("anthropic/claude-sonnet-4")
    assert c.from_any(c.encode(route)) == c.ModelId("anthropic", "claude-sonnet-4")
    assert c.from_any(c.from_string("x/y")) == c.ModelId("x", "y")
    with pytest.raises(c.BackendContractError):
        c.from_string("")


def test_model_id_roundtrip_preserves_extras_and_is_hashable():
    mid = c.from_any({"provider": "anthropic", "model": "m", "context": 128000})
    assert mid.extras == (("context", 128000),)
    assert mid.as_dict() == {
        "provider": "anthropic", "model": "m", "context": 128000}
    assert len({mid, c.from_any(mid.as_dict())}) == 1


def test_normalize_model_ids_only_touches_model_shaped_values():
    result = {"model": c.encode(e3_backend.parse_model_route("x/y")),
              "count": 3, "note": "x/y is just text"}
    assert c.normalize_model_ids(result) == {
        "model": {"provider": "x", "model": "y"},
        "count": 3,
        "note": "x/y is just text",
    }
    assert c.normalize_model_ids(["x/y"], strings=True) == [
        {"provider": "x", "model": "y"}]


def test_model_id_contract_is_machine_readable_and_deterministic():
    contract = c.model_id_contract()
    assert contract["type"] == "ModelId"
    assert set(contract["representations"]) == {
        "model_reference", "model_route", "discovery_id", "string"}
    assert json.dumps(contract, sort_keys=True) == json.dumps(
        c.model_id_contract(), sort_keys=True)


def test_function_schema_is_derived_without_executing_the_function():
    calls: list[Any] = []

    def never_called(value: int, *, flag: bool = False) -> str:
        calls.append(value)
        raise AssertionError("schema derivation must not execute the callable")

    schema = c.function_schema(never_called)
    assert calls == []
    assert schema["type"] == "object"
    assert schema["required"] == ["value"]
    assert schema["properties"]["value"] == {"type": "integer"}
    assert schema["properties"]["flag"] == {
        "type": "boolean", "default": False, "x-parameter-kind": "keyword-only"}
    assert schema["returns"] == {"type": "string"}
    assert json.dumps(schema, sort_keys=True) == json.dumps(
        c.function_schema(never_called), sort_keys=True)


def test_annotation_schema_handles_literal_union_and_typed_classes():
    def sample(mode: Literal["server", "gui"], route: e3_backend.ModelRoute | None):
        return mode, route

    schema = c.function_schema(sample)
    assert schema["properties"]["mode"]["enum"] == ["server", "gui"]
    route_schema = schema["properties"]["route"]["anyOf"]
    assert {"type": "null"} in route_schema
    assert any("ModelRoute" in part.get("x-class", "") for part in route_schema)


def test_real_dispatch_schemas_are_json_serialisable_and_stable():
    schemas = hub.function_schemas()
    assert len(schemas) == sum(len(hub.dispatchable(m)) for m in hub.modules())
    assert "e3_backend.parse_model_route" in schemas
    assert json.dumps(schemas, sort_keys=True) == json.dumps(
        hub.function_schemas(), sort_keys=True)
    for key, schema in schemas.items():
        assert schema["type"] == "object"
        assert set(schema["required"]) <= set(schema["properties"])
        assert "signature" in schema
        json.dumps(schema, sort_keys=True)  # fails on non-serialisable values
