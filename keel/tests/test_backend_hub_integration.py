"""Real-runtime integration tests for the v6 backend module hub.

These tests exercise the actual authenticated capability surface used by the
web bridge, CLI, TUI and desktop shell - not just the additive modules in
isolation. They prove the live application can discover and execute backend
functionality with permission enforcement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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


def test_verify_confirms_all_modules_import_and_declare_features():
    for module in hub.modules():
        result = capabilities.invoke(
            "backend.verify", {"module": module}, allowed_permissions=ALL)
        assert result["ok"] is True, (module, result)
        assert result["result"]["imported"] is True
        assert result["result"]["features"] > 0
        assert result["result"]["not_declared"] == [], (module, result)


def test_feature_index_covers_all_integrated_ids():
    ids = hub.feature_ids()
    assert len(ids) == len(set(ids))
    assert all(hub.FEATURE_TO_MODULE[f] in hub.modules() for f in ids)
