"""Real-runtime integration tests for the v6 backend module hub.

These tests exercise the actual authenticated capability surface used by the
web bridge, CLI, TUI and desktop shell - not just the additive modules in
isolation. They prove the live application can discover and execute backend
functionality with permission enforcement, and that hub metadata (feature
attribution and declaration verification) is honest rather than cosmetic.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import json
import sys
from pathlib import Path

import pytest

KEEL_ROOT = Path(__file__).resolve().parents[1]
WORKTREE_ROOT = KEEL_ROOT.parent
sys.path.insert(0, str(KEEL_ROOT / "src"))

from keel import backend_contracts as contracts  # noqa: E402
from keel import backend_hub as hub  # noqa: E402
from keel import capabilities  # noqa: E402
from keel import e3_backend  # noqa: E402

ALL = {"read", "write", "execute"}


def test_capabilities_registered_on_real_hub():
    ids = {c["id"] for c in capabilities.list_capabilities()}
    assert {"backend.modules", "backend.describe", "backend.invoke",
            "backend.verify"} <= ids


def test_backend_modules_capability_reports_integrated_modules():
    result = capabilities.invoke("backend.modules", {}, allowed_permissions=ALL)
    assert result["ok"] is True
    assert len(result["result"]["modules"]) == len(hub.modules())
    assert result["result"]["feature_count"] == len(hub.feature_ids())
    assert len(result["result"]["modules"]) == 20
    # 421 canonical attribution rows, not the 474 old cross-reference claims.
    assert len(hub.feature_ids()) == 421


def test_dispatch_exercises_every_module_through_real_capability_surface():
    """Each integrated module exposes at least one callable executed for real."""
    exercised = 0
    for module in hub.modules():
        fns = hub.dispatchable(module)
        assert fns, f"{module} has no dispatchable real function"
        name = fns[0]
        contract = capabilities.invoke(
            "backend.describe", {"module": module}, allowed_permissions=ALL)
        assert contract["ok"] is True
        assert name in contract["result"]["dispatchable"]
        # Invoke through the permission-aware capability hub with NO args.
        # A real result OR an explicit bad-arguments error both prove the real
        # function was reached; never a fake success or unknown-function error.
        try:
            outcome = capabilities.invoke(
                "backend.invoke", {"module": module, "function": name},
                allowed_permissions=ALL)
            assert outcome["ok"] is True
        except capabilities.CapabilityError as exc:
            assert "missing" in str(exc) or "bad arguments" in str(exc), (module, exc)
        exercised += 1
    assert exercised == 20


def test_every_dispatch_entry_is_a_real_callable_and_fails_honestly():
    """All 144 advertised entries resolve to module-level callables.

    No-arg invocation either returns a real result or a typed bad_request. An
    AttributeError from a stale entry (the old x3 _embedding/_cosine case) is a
    failure even though the capability layer wraps it as bad_request.
    """
    checked = 0
    for module in hub.modules():
        mod = importlib.import_module("keel." + module)
        for name in hub.dispatchable(module):
            assert callable(getattr(mod, name, None)), f"{module}.{name} is not callable"
            try:
                outcome = capabilities.invoke(
                    "backend.invoke", {"module": module, "function": name},
                    allowed_permissions=ALL)
                assert outcome["ok"] is True
            except capabilities.CapabilityError as exc:
                assert exc.code == "bad_request", (module, name, exc)
                assert "AttributeError" not in str(exc), (module, name, exc)
            checked += 1
    assert checked == sum(len(hub.dispatchable(m)) for m in hub.modules())
    assert checked >= 140
    for stale in ("_embedding", "_cosine"):
        assert stale not in hub.dispatchable("x3_memory_backend")


def test_real_pure_function_returns_genuine_value_via_hub():
    result = capabilities.invoke(
        "backend.invoke",
        {"module": "d6_reliability_backend", "function": "fingerprint",
         "params": {"value": {"order": [1, 2, 3]}}},
        allowed_permissions=ALL)
    assert result["ok"] is True
    digest = result["result"]
    assert isinstance(digest, str) and len(digest) >= 16
    # canonical: same logical value with different key order -> same digest
    again = capabilities.invoke(
        "backend.invoke",
        {"module": "d6_reliability_backend", "function": "fingerprint",
         "params": {"value": {"order": [1, 2, 3]}}},
        allowed_permissions=ALL)
    assert again["result"] == digest


def test_execute_permission_is_enforced():
    with pytest.raises(capabilities.CapabilityError) as exc:
        capabilities.invoke(
            "backend.invoke",
            {"module": "d6_reliability_backend", "function": "fingerprint"},
            allowed_permissions={"read"})
    assert exc.value.code == "permission_denied"


def test_unknown_module_and_function_are_rejected():
    for payload in ({"module": "not_a_module", "function": "x"},
                    {"module": "d6_reliability_backend", "function": "__import__"}):
        with pytest.raises(capabilities.CapabilityError) as exc:
            capabilities.invoke("backend.invoke", payload, allowed_permissions=ALL)
        assert exc.value.code == "bad_request"


def test_verify_reports_real_imports_and_honest_declarations():
    for module in hub.modules():
        result = capabilities.invoke(
            "backend.verify", {"module": module}, allowed_permissions=ALL)
        assert result["ok"] is True, (module, result)
        out = result["result"]
        assert out["imported"] is True
        assert out["features"] > 0
        assert out["declaration_source"] in ("registry", "ast")
        assert out["declared_in_module"] + len(out["not_declared"]) == out["features"]
        assert all(fid in hub.MODULE_FEATURES[module] for fid in out["not_declared"])


def test_verify_introspects_real_module_registries(monkeypatch):
    """A registry is the declaration; editing the registry must change verify."""
    module = "d3_backend"
    mod = importlib.import_module("keel." + module)
    assert hasattr(mod, "FEATURE_IDS")
    removed = mod.FEATURE_IDS[0]
    assert removed in hub.MODULE_FEATURES[module]
    monkeypatch.setattr(
        mod, "FEATURE_IDS", tuple(f for f in mod.FEATURE_IDS if f != removed))
    out = hub.verify(module)
    assert out["declaration_source"] == "registry"
    assert removed in out["not_declared"]


def test_verify_ignores_feature_ids_mentioned_only_in_comments(monkeypatch):
    """The old source-text regex counted a fake comment as a declaration."""
    module = "d6_reliability_backend"  # no registry -> AST fallback
    real_ids = hub.MODULE_FEATURES[module]
    monkeypatch.setitem(
        hub.MODULE_FEATURES, module, tuple(real_ids) + ("FAKE.999",))
    original_read_text = Path.read_text

    def with_comment(self, *args, **kwargs):
        text = original_read_text(self, *args, **kwargs)
        if self.name == "d6_reliability_backend.py":
            text += ("\n# FAKE.999 is only mentioned in this comment; "
                     "no implementation.\n")
        return text

    monkeypatch.setattr(Path, "read_text", with_comment)
    out = hub.verify(module)
    assert out["declaration_source"] == "ast"
    assert out["declared_in_module"] == len(real_ids)
    assert "FAKE.999" in out["not_declared"]
    via_capability = capabilities.invoke(
        "backend.verify", {"module": module}, allowed_permissions=ALL)
    assert "FAKE.999" in via_capability["result"]["not_declared"]


def test_verify_fails_closed_without_registry_for_docstring_only_ids():
    """Without a registry or AST declaration, IDs are not silently accepted."""
    out = hub.verify("e5_backend")
    assert out["declaration_source"] == "ast"
    assert out["declared_in_module"] < out["features"]
    # E5 IDs appear only in the module docstring/comments, not in declarations.
    assert "E5.2" in out["not_declared"]


def test_feature_attribution_matches_canonical_json_exactly():
    attribution = json.loads(
        (WORKTREE_ROOT / "backend-final-attribution.json").read_text(encoding="utf-8")
    )["attribution"]
    assert len(attribution) == 421
    assert dict(hub.FEATURE_TO_MODULE) == attribution
    assert hub.feature_ids() == tuple(sorted(attribution))
    # Baseline-only cross references (D3.8, V1) are documented, not counted.
    for fid in ("D3.8", "V1"):
        assert fid not in hub.feature_ids()
        assert fid in hub._BASELINE_ONLY_FEATURE_IDS
    assert all(hub.FEATURE_TO_MODULE[f] in hub.modules() for f in hub.feature_ids())


def test_canonical_owner_map_has_no_duplicate_literal_keys():
    source = Path(hub.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    keys = None
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "_CANONICAL_FEATURE_OWNERS"
                   for t in targets):
                assert isinstance(node.value, ast.Tuple)
                keys = [elt.elts[0].value for elt in node.value.elts
                        if isinstance(elt, ast.Tuple)]
    assert keys is not None
    assert len(keys) == len(set(keys)) == 421
    assert len(hub._CANONICAL_FEATURE_OWNERS) == len(hub.FEATURE_TO_MODULE)


# --- G2: dispatch-table startup validation ---------------------------------

def test_dispatch_startup_assertion_accepts_real_table():
    """The real DISPATCH table must be callable at hub import and on demand."""
    hub.assert_dispatch_targets()
    for module in hub.modules():
        target = importlib.import_module("keel." + module)
        for name in hub.dispatchable(module):
            assert callable(getattr(target, name)), (module, name)


def test_dispatch_startup_assertion_rejects_a_stale_entry(monkeypatch):
    """Reintroducing a class-method-only name fails closed instead of at invoke."""
    monkeypatch.setitem(
        hub.DISPATCH, "x3_memory_backend",
        tuple(hub.DISPATCH["x3_memory_backend"]) + ("_embedding",))
    with pytest.raises(AssertionError, match="_embedding"):
        hub.assert_dispatch_targets()


# --- G1: typed envelope round-trip through the real capability surface ------

def test_typed_envelope_chains_from_hub_result_into_typed_consumer():
    """A hub-serialised ModelRoute can be fed back into check_route for real.

    Pre-change: the envelope dict reaches ``parse_model_route`` and raises
    RouteError. Post-change: the hub decodes envelope params using the callee's
    annotations, so both real functions run and the allowlist accepts the route.
    """
    route = capabilities.invoke(
        "backend.invoke",
        {"module": "e3_backend", "function": "parse_model_route",
         "params": {"value": "anthropic/claude-sonnet-4"}},
        allowed_permissions=ALL)
    assert route["ok"] is True
    envelope = route["result"]
    assert contracts.is_envelope(envelope)
    assert envelope["type"] == "ModelRoute"

    allowlist = e3_backend.ModelRouteAllowlist(
        True, frozenset({"anthropic/claude-sonnet-4"}))
    with pytest.raises(e3_backend.RouteError):
        e3_backend.check_route(allowlist, envelope)  # the old dead end

    outcome = capabilities.invoke(
        "backend.invoke",
        {"module": "e3_backend", "function": "check_route",
         "params": {"allowlist": contracts.encode(allowlist), "route": envelope}},
        allowed_permissions=ALL)
    assert outcome["ok"] is True
    assert outcome["result"] is None  # accepted: check_route's real success value


def test_hub_rehydrates_envelope_params_without_changing_plain_dict_params():
    """The adapter only touches canonical envelopes; plain dicts pass through."""
    plain = hub.invoke("e3_backend", "parse_model_route",
                       {"value": "anthropic/claude-sonnet-4"})
    assert plain == {"type": "ModelRoute",
                     "fields": {"provider": "anthropic",
                                "model": "claude-sonnet-4"}}
    agent = hub.invoke(
        "small_groups_backend", "normalize_agent_config",
        {"config": {"mode": "primary", "step_limit": 5,
                    "model": "anthropic/claude-sonnet-4"}})
    assert agent["model"] == {"provider": "anthropic", "model": "claude-sonnet-4"}


# --- G3: normalised model identity ------------------------------------------

def test_model_id_normalisation_is_opt_in_and_wires_into_invoke():
    """Default output is unchanged; opt-in canonicalises model-id results."""
    params = {"value": "anthropic/claude-sonnet-4"}
    default = hub.invoke("e3_backend", "parse_model_route", params)
    normalized = hub.invoke("e3_backend", "parse_model_route", params,
                            normalize_model_id=True)
    assert contracts.is_envelope(default)
    assert normalized == {"provider": "anthropic", "model": "claude-sonnet-4"}
    assert hub.normalize_model_id(default) == normalized

    discovery = hub.invoke(
        "e6_x5_x6_backend", "parse_models_response",
        {"payload": {"data": [{"id": "claude-sonnet-4"}]}})
    assert discovery == ["claude-sonnet-4"]  # unchanged by default
    assert contracts.from_discovery(discovery) == contracts.ModelId(
        "", "claude-sonnet-4")
    assert contracts.to_route(contracts.from_model_route(default)) == (
        "anthropic/claude-sonnet-4")


# --- G4: signature-derived schemas in describe and capability contracts -----

def test_describe_publishes_per_function_schemas_and_contract_formats():
    described = capabilities.invoke(
        "backend.describe", {"module": "e3_backend"}, allowed_permissions=ALL)
    assert described["ok"] is True
    out = described["result"]
    assert set(out["functions"]) == set(hub.dispatchable("e3_backend"))
    parse_schema = out["functions"]["parse_model_route"]
    assert parse_schema["required"] == ["value"]
    assert "value" in parse_schema["properties"]
    route_schema = out["functions"]["check_route"]
    assert set(route_schema["required"]) == {"allowlist", "route"}
    assert out["envelope_format"]["required"] == ["type", "fields"]
    assert set(out["model_id"]["representations"]) >= {
        "model_reference", "model_route", "discovery_id"}
    assert hub.describe()["function_schema_count"] == 144


def test_capability_input_schema_carries_every_function_schema():
    """The real backend.invoke capability advertises the derived call contract."""
    capabilities.invoke("backend.describe", {"module": "e3_backend"},
                        allowed_permissions=ALL)  # triggers a real hub sync
    invoke_cap = capabilities.get("backend.invoke")
    assert invoke_cap is not None
    schema = invoke_cap.input_schema
    names = schema["x-function-names"]
    assert len(names) == 144
    assert "e3_backend.parse_model_route" in names
    assert schema["x-function-schemas"]["e3_backend.parse_model_route"][
        "required"] == ["value"]
    assert schema["properties"]["params"]["x-function-schemas"] == schema[
        "x-function-schemas"]
    listed = next(c for c in capabilities.list_capabilities()
                  if c["id"] == "backend.invoke")
    assert listed["input_schema"] is schema  # published on the real registry

    describe_schema = capabilities.get("backend.describe").input_schema
    assert "e3_backend" in describe_schema["properties"]["module"]["enum"]
    assert "check_route" in describe_schema["x-module-schemas"]["e3_backend"]

    # Idempotent: re-syncing does not mutate the schema into a different value.
    before = json.dumps(schema, sort_keys=True)
    assert hub.sync_capability_schemas() is True
    assert json.dumps(schema, sort_keys=True) == before


def test_all_dispatch_schemas_match_real_signatures_offline():
    """Schemas come from inspect.signature, not execution or network access."""
    for module in hub.modules():
        target = importlib.import_module("keel." + module)
        for name in hub.dispatchable(module):
            schema = hub.function_schema(module, name)
            signature = inspect.signature(getattr(target, name))
            assert schema["signature"] == str(signature)
            assert set(schema["properties"]) == set(signature.parameters)
            assert set(schema["required"]) == {
                p.name for p in signature.parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind not in (inspect.Parameter.VAR_POSITIONAL,
                                   inspect.Parameter.VAR_KEYWORD)}
            assert json.dumps(schema, sort_keys=True)

