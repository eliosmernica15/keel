"""Bridge tests: live native tools conform to Addendum 7 model-facing contracts."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from keel.runner import RealTools
from keel.tool_contracts_bridge import (
    MODEL_FACING_FIELDS,
    adapt_native_tools,
    check_native_conformance,
    project_model_schemas,
)
from keel.tools.registry import create_native_registry


def test_native_registry_conforms():
    registry = create_native_registry(RealTools())
    report = check_native_conformance(registry)
    assert report["ok"], report["problems"]
    assert report["tool_count"] >= 40


def test_model_schemas_are_allowed_fields_only():
    registry = create_native_registry(RealTools())
    projected = project_model_schemas(registry.schemas())
    assert len(projected) == len(registry.names())
    for schema in projected:
        assert set(schema) <= MODEL_FACING_FIELDS


def test_model_schema_leak_is_rejected():
    try:
        project_model_schemas([{
            "name": "x", "description": "d", "input_schema": {},
            "handler": "leak", "timeout_s": 3,
        }])
    except ValueError as exc:
        assert "leaked" in str(exc)
    else:
        raise AssertionError("internal fields were silently accepted")


def test_conformance_reports_schema_leak_instead_of_raising():
    """M4: a leaked internal field must appear in problems, not abort CI."""
    class LeakyRegistry:
        def list_tools(self):
            return []

        def schemas(self):
            return [{
                "name": "x", "description": "d", "input_schema": {},
                "handler": "leak", "timeout_s": 3,
            }]

    report = check_native_conformance(LeakyRegistry())
    assert report["ok"] is False
    assert report["tool_count"] == 0
    assert report["model_schema_count"] == 0
    assert any("leaked" in problem for problem in report["problems"])


def test_adapted_specs_have_canonical_output_schema():
    registry = create_native_registry(RealTools())
    specs = adapt_native_tools(registry)
    assert len(specs) == len(registry.names())
    for spec in specs:
        assert spec.output_schema
        assert spec.output_schema.get("type") == "object"
