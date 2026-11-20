from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    permission: str = "execute"
    category: str = "native"
    origin: str = "native"
    available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def operation_class(self) -> str:
        """Map registry permission level to permission operation class."""
        mapping = {
            "read": "read",
            "write": "mutate_local",
            "execute": "execute",
            "network": "network",
            "process_control": "process_control",
            "destructive": "irreversible",
        }
        return mapping.get(self.permission, "execute")

    def is_shell_like(self) -> bool:
        return self.name in {"run_shell", "run_python", "run_tests", "run_build",
                            "install_deps", "background_shell", "process_kill"}


class ToolRegistry:
    """Authoritative registry of tool definitions and dispatch.

    This is the single source of truth for tool names, schemas, validation and
    dispatch. Permission enforcement remains in the existing permission system;
    the registry declares each tool's permission level and delegates execution
    to the registered handler.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool, *, replace: bool = False) -> None:
        if not isinstance(tool, Tool):
            raise TypeError("tool must be a Tool instance")
        if not tool.name or not isinstance(tool.name, str):
            raise ValueError("tool name must be a non-empty string")
        if not tool.description or not isinstance(tool.description, str):
            raise ValueError("tool description must be a non-empty string")
        if not isinstance(tool.input_schema, dict):
            raise ValueError("tool input_schema must be a dict")
        if tool.name in self._tools and not replace:
            raise ValueError(f"duplicate tool registration: {tool.name!r}")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def list_tools(self, *, available_only: bool = True) -> list[Tool]:
        tools = list(self._tools.values())
        if available_only:
            tools = [t for t in tools if t.available]
        return sorted(tools, key=lambda t: t.name)

    def schemas(self, names: Iterable[str] | None = None,
                *, available_only: bool = True) -> list[dict[str, Any]]:
        """Provider-compatible tool schemas (name/description/input_schema)."""
        selected: list[Tool]
        if names is None:
            selected = self.list_tools(available_only=available_only)
        else:
            selected = []
            for name in names:
                tool = self.get(name)
                if tool is not None and (tool.available or not available_only):
                    selected.append(tool)
        return [
            {"name": t.name, "description": t.description,
             "input_schema": t.input_schema}
            for t in selected
        ]

    def validate(self, name: str, tool_input: Any) -> list[str]:
        tool = self.get(name)
        if tool is None:
            return [f"unknown tool: {name!r}"]
        if not isinstance(tool_input, dict):
            tool_input = {} if tool_input is None else tool_input
            if not isinstance(tool_input, dict):
                return [f"{name}: input must be an object"]
        return _validate_schema(tool.input_schema, tool_input or {})

    def execute(self, name: str, tool_input: Any) -> Any:
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"unknown tool: {name!r}")
        if not tool.available:
            raise RuntimeError(f"tool is not available: {name!r}")
        errors = self.validate(name, tool_input)
        if errors:
            raise ValueError("; ".join(errors))
        return tool.handler(tool_input or {})

    def clear(self) -> None:
        self._tools.clear()

    def permission_level(self, name: str) -> str:
        tool = self.get(name)
        return tool.permission if tool is not None else "execute"

    def operation_class(self, name: str) -> str | None:
        tool = self.get(name)
        if tool is None:
            return None
        return tool.operation_class()

    def is_shell_like(self, name: str) -> bool:
        tool = self.get(name)
        if tool is None:
            return False
        return tool.is_shell_like()

    def read_tools(self) -> frozenset[str]:
        return frozenset(n for n, t in self._tools.items()
                         if t.permission == "read" and t.available)

    def write_tools(self) -> frozenset[str]:
        return frozenset(n for n, t in self._tools.items()
                         if t.permission == "write" and t.available)

    def shell_tools(self) -> frozenset[str]:
        return frozenset(n for n, t in self._tools.items()
                         if t.is_shell_like() and t.available)

    def network_tools(self) -> frozenset[str]:
        return frozenset(n for n, t in self._tools.items()
                         if t.permission == "network" and t.available)


def _validate_schema(schema: Any, value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        return errors
    typ = schema.get("type")
    if typ == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object"]
        for req in schema.get("required", []) or []:
            if req not in value:
                errors.append(f"{path}: missing required field {req!r}")
        props = schema.get("properties")
        if isinstance(props, dict):
            for key, val in (value or {}).items():
                if key in props:
                    errors.extend(_validate_schema(props[key], val, f"{path}.{key}"))
    elif typ == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: expected string")
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            errors.append(f"{path}: value must be one of {enum!r}")
    elif typ == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"{path}: expected integer")
        _check_number_bounds(schema, value, path, errors)
    elif typ == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{path}: expected number")
        _check_number_bounds(schema, value, path, errors)
    elif typ == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean")
    elif typ == "array":
        if not isinstance(value, list):
            errors.append(f"{path}: expected array")
        else:
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for i, item in enumerate(value):
                    errors.extend(_validate_schema(item_schema, item, f"{path}[{i}]"))
    elif typ == "null":
        if value is not None:
            errors.append(f"{path}: expected null")
    # Unknown/missing type: accept (permissive).
    if isinstance(schema.get("minimum"), (int, float)) and isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema["minimum"]:
            errors.append(f"{path}: value below minimum {schema['minimum']}")
    if isinstance(schema.get("maximum"), (int, float)) and isinstance(value, (int, float)) and not isinstance(value, bool):
        if value > schema["maximum"]:
            errors.append(f"{path}: value above maximum {schema['maximum']}")
    if isinstance(schema.get("minLength"), int) and isinstance(value, str):
        if len(value) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength {schema['minLength']}")
    if isinstance(schema.get("maxLength"), int) and isinstance(value, str):
        if len(value) > schema["maxLength"]:
            errors.append(f"{path}: string longer than maxLength {schema['maxLength']}")
    if isinstance(schema.get("minItems"), int) and isinstance(value, list):
        if len(value) < schema["minItems"]:
            errors.append(f"{path}: array shorter than minItems {schema['minItems']}")
    if isinstance(schema.get("maxItems"), int) and isinstance(value, list):
        if len(value) > schema["maxItems"]:
            errors.append(f"{path}: array longer than maxItems {schema['maxItems']}")
    enum = schema.get("enum")
    if isinstance(enum, list) and typ not in ("string",) and value in enum is False:
        # enum already handled for strings; handle other types here
        if value not in enum:
            errors.append(f"{path}: value must be one of {enum!r}")
    return errors


def _check_number_bounds(schema: dict[str, Any], value: Any, path: str, errors: list[str]) -> None:
    # Bounds already checked generically above; kept for clarity.
    return None


def create_native_registry(executor: Any) -> "ToolRegistry":
    from .native import register_native_tools

    registry = ToolRegistry()
    register_native_tools(registry, executor)
    return registry
