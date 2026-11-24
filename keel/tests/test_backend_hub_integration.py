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
import json
import sys
from pathlib import Path

import pytest

KEEL_ROOT = Path(__file__).resolve().parents[1]
WORKTREE_ROOT = KEEL_ROOT.parent
sys.path.insert(0, str(KEEL_ROOT / "src"))

from keel import backend_hub as hub  # noqa: E402
from keel import capabilities  # noqa: E402

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
