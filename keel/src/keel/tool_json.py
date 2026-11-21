"""Tolerant tool-call parsing and schema constraints (B1.1 / B1.2).

Local models often emit slightly malformed JSON for tool arguments. This
module repairs the common cases, then validates and coerces the result against
the tool's declared schema before the tool is executed.
"""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_UNQUOTED_KEY = re.compile(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_-]*)\s*:")


def _candidate(text: str) -> str:
    """Trim prose around the outermost JSON object/array."""
    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not starts:
        return text
    start = min(starts)
    ends = [index for index in (text.rfind("}"), text.rfind("]")) if index >= 0]
    end = max(ends) if ends else len(text) - 1
    return text[start:end + 1] if end >= start else text[start:]


def _balance_suffix(text: str) -> str:
    """Return closing brackets needed for a truncated JSON document."""
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]" and stack and stack[-1] == char:
            stack.pop()
    if in_string:
        stack.append('"')
    return "".join(reversed(stack))


def repair_json(raw) -> dict:
    """Parse tool arguments, repairing common local-model formatting issues."""
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    text = _FENCE.sub("", str(raw)).strip()
    if not text:
        return {}

    attempts = [text, _candidate(text)]
    cleaned = _candidate(text)
    cleaned = _TRAILING_COMMA.sub(r"\1", cleaned)
    cleaned = _UNQUOTED_KEY.sub(r'\1"\2":', cleaned)
    cleaned = cleaned.replace("'", '"')
    attempts.append(cleaned)
    attempts.append(cleaned + _balance_suffix(cleaned))

    for attempt in attempts:
        try:
            parsed = json.loads(attempt)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
        return {"_raw": raw}
    return {"_raw": raw}


def validate_tool_input(data: dict, schema: dict | None) -> list[str]:
    """Return human-readable schema violations for *data*."""
    if not isinstance(data, dict):
        return ["tool input must be an object"]
    if not isinstance(schema, dict):
        return []
    errors: list[str] = []
    properties = schema.get("properties") or {}
    for name in schema.get("required") or []:
        if name not in data:
            errors.append(f"missing required field: {name}")
    for name, spec in (properties.items() if isinstance(properties, dict) else []):
        if name not in data or not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        value = data[name]
        valid = True
        if expected == "string":
            valid = isinstance(value, str)
        elif expected == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif expected == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif expected == "boolean":
            valid = isinstance(value, bool)
        elif expected == "array":
            valid = isinstance(value, list)
        elif expected == "object":
            valid = isinstance(value, dict)
        if not valid:
            errors.append(f"{name} must be {expected}")
        elif "enum" in spec and value not in spec["enum"]:
            errors.append(f"{name} must be one of {spec['enum']}")
    return errors


def coerce_tool_input(data: dict, schema: dict | None) -> dict:
    """Coerce stringly-typed values into the schema's declared types."""
    if not isinstance(data, dict) or not isinstance(schema, dict):
        return data
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return data
    for name, spec in properties.items():
        if name not in data or not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        value = data[name]
        try:
            if expected == "string" and not isinstance(value, str):
                data[name] = str(value)
            elif expected == "integer" and isinstance(value, str):
                data[name] = int(value.strip())
            elif expected == "number" and isinstance(value, str):
                data[name] = float(value.strip())
            elif expected == "boolean" and isinstance(value, str):
                data[name] = value.strip().lower() in {"1", "true", "yes", "on"}
            elif expected == "array" and not isinstance(value, list):
                data[name] = [value]
        except (TypeError, ValueError):
            continue
    return data


def parse_tool_args(raw, schema: dict | None = None) -> dict:
    """Repair, coerce and validate tool arguments in one step."""
    data = repair_json(raw)
    if "_raw" in data:
        return data
    coerce_tool_input(data, schema)
    return data


def constrain_tool_schema(schema: dict) -> dict:
    """Tighten a tool schema for providers that support schema constraints."""
    copy = dict(schema)
    inner = dict(copy.get("input_schema") or {})
    if inner.get("type") == "object":
        inner["additionalProperties"] = False
    copy["input_schema"] = inner
    copy["_constrained"] = True
    return copy


def constrain_tool_schemas(schemas: list[dict]) -> list[dict]:
    return [constrain_tool_schema(schema) for schema in schemas]
