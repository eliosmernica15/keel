"""Additive bridge from the native tool registry to Addendum 7 contracts.

The live tool dispatch (``keel.tools.registry`` / ``keel.session``) is preserved
unchanged. This module adapts registered native tools into the contract types
so the model-facing projection is provably free of runtime internals, and
provides a conformance report for CI.

It never replaces permission evaluation: the native registry already declares
each tool's permission, and ``permissions.evaluate`` remains authoritative.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from .tool_contracts import (
    ALLOWED_SCHEMA_KEYWORDS,
    ToolSpec,
)

# Fields that may appear in a model-facing tool schema. Any other field
# (handler, renderer, timeout, concurrency, metadata, callbacks) is a leak.
MODEL_FACING_FIELDS = frozenset({"name", "description", "input_schema"})

# Canonical output schema applied to tools that do not declare a narrower one.
# It is lossless at the JSON level and requires no prose parsing.
GENERIC_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
}


def project_model_schemas(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deep-copied schemas with ONLY explicitly allowed fields.

    Raises ValueError if a runtime/internal field is present, rather than
    silently dropping it (Addendum 7: reject unsupported keywords/leaks).
    """
    out: list[dict[str, Any]] = []
    for schema in schemas:
        leaked = set(schema) - MODEL_FACING_FIELDS
        if leaked:
            raise ValueError(
                f"model-facing schema leaked fields: {sorted(leaked)}")
        out.append(deepcopy(schema))
    return out


def adapt_native_tools(native_registry: Any) -> list[ToolSpec]:
    """Adapt native Tool objects into contract ToolSpecs (no dispatch change)."""
    specs: list[ToolSpec] = []
    for tool in native_registry.list_tools():
        specs.append(ToolSpec(
            name=tool.name,
            description=tool.description,
            input_schema=deepcopy(tool.input_schema),
            output_schema=deepcopy(GENERIC_OUTPUT_SCHEMA),
            handler=tool.handler,
            renderer=lambda args, value: value,  # pure, lossless
            permission=tool.permission,
        ))
    return specs


def check_native_conformance(native_registry: Any) -> dict[str, Any]:
    """Produce a conformance report for the live native tool registry."""
    specs = adapt_native_tools(native_registry)
    problems: list[str] = []
    try:
        projected = project_model_schemas(native_registry.schemas())
    except ValueError as exc:
        # A schema leak is the single most important conformance failure. It
        # must be reported in the durable report, not abort CI with a raw
        # exception from the (deliberately strict) projection API.
        projected = []
        problems.append(f"model-facing schema projection: {exc}")
    for spec in specs:
        if not spec.name or not spec.description:
            problems.append(f"{spec.name}: missing name/description")
        for keyword in _walk_schema_keys(spec.input_schema):
            if keyword not in ALLOWED_SCHEMA_KEYWORDS:
                problems.append(f"{spec.name}: unsupported keyword {keyword!r}")
    return {
        "tool_count": len(specs),
        "model_schema_count": len(projected),
        "problems": problems,
        "ok": not problems,
    }


def _walk_schema_keys(node: Any, *, _in_properties: bool = False) -> set[str]:
    """Collect JSON-Schema structural keywords only.

    Keys inside a ``properties`` / ``$defs`` mapping are user-defined property
    names (e.g. ``path``, ``command``), not schema keywords, and must not be
    validated as keywords.
    """
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if not _in_properties:
                keys.add(key)
            child_in_properties = key in {"properties", "$defs", "patternProperties"}
            keys.update(_walk_schema_keys(value, _in_properties=child_in_properties))
    elif isinstance(node, list):
        for value in node:
            keys.update(_walk_schema_keys(value, _in_properties=_in_properties))
    return keys
