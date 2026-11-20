"""Small JSON Schema validator for Keel's supported configuration subset.

Avoids adding a new runtime dependency. Diagnostics contain JSON pointers and
expected types only - never user values, keys that may hold secrets, or raw
configuration text.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .resources import resource_path


@dataclass(frozen=True)
class SchemaDiagnostic:
    pointer: str
    message: str

    def __str__(self) -> str:
        return f"{self.pointer or '<root>'}: {self.message}"


def schema_path() -> Path:
    return resource_path("schema", "keel.settings.schema.json")


def load_schema(*, path: Path | None = None) -> dict:
    target = path or schema_path()
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load settings schema at {target}: {exc}") from None
    return doc


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
}


def validate(doc: object, *, schema: dict | None = None,
             path: Path | None = None) -> list[SchemaDiagnostic]:
    schema = schema or load_schema(path=path)
    problems: list[SchemaDiagnostic] = []

    def check(value: object, spec: dict, pointer: str) -> None:
        expected = spec.get("type")
        if expected:
            py = _TYPES.get(expected)
            if py and not isinstance(value, py):
                problems.append(SchemaDiagnostic(pointer, f"expected {expected}"))
                return
            if expected == "number" and isinstance(value, bool):
                problems.append(SchemaDiagnostic(pointer, "expected number"))
                return
        if "enum" in spec and value not in spec["enum"]:
            problems.append(SchemaDiagnostic(pointer, "value is not one of the allowed values"))
        if "pattern" in spec and isinstance(value, str):
            if not re.search(spec["pattern"], value):
                problems.append(SchemaDiagnostic(pointer, "value does not match required pattern"))
        if isinstance(value, dict):
            for key in spec.get("required", []):
                if key not in value:
                    problems.append(SchemaDiagnostic(
                        f"{pointer}/{key}".replace("//", "/"), "required property is missing"))
            props = spec.get("properties", {})
            for key, child in value.items():
                child_pointer = f"{pointer}/{key}".replace("//", "/")
                if key in props:
                    check(child, props[key], child_pointer)
                elif spec.get("additionalProperties") is False:
                    problems.append(SchemaDiagnostic(child_pointer, "property is not supported"))
                elif isinstance(spec.get("additionalProperties"), dict):
                    check(child, spec["additionalProperties"], child_pointer)
        if isinstance(value, list) and isinstance(spec.get("items"), dict):
            for index, child in enumerate(value):
                check(child, spec["items"], f"{pointer}/{index}".replace("//", "/"))

    check(doc, schema, "")
    return problems
