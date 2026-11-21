"""Unified capability hub (final integration phase).

Exposes real functionality from the local modules through one authenticated,
permission-aware surface used by the web bridge, CLI, TUI and desktop UI.
Every capability has an explicit id, product surface, permission tier, input
schema and a handler. Handlers import their module lazily so startup stays
cheap and circular imports are avoided.

No capability here is a placeholder: each calls the real module function and
returns structured data or an explicit error.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class CapabilityError(RuntimeError):
    def __init__(self, message: str, *, code: str = "capability_error"):
        super().__init__(message)
        self.code = code


@dataclass
class Capability:
    id: str
    module: str
    surface: str           # cowork | code | duet | fleet | desktop | web | cli | tui | core
    permission: str        # read | write | execute
    description: str
    input_schema: dict
    handler: Callable[[dict, dict], Any]
    mutates: bool = False


_REGISTRY: dict[str, Capability] = {}


def register(cap: Capability) -> None:
    _REGISTRY[cap.id] = cap


def capability(
    name: str, module: str, surface: str, permission: str,
    description: str, *, schema: dict | None = None, mutates: bool = False
):
    """Decorator registering a handler as a capability."""
    def deco(fn):
        register(Capability(
            id=name, module=module, surface=surface, permission=permission,
            description=description,
            input_schema=schema or {"type": "object", "properties": {}},
            handler=fn, mutates=mutates))
        return fn
    return deco


def get(cap_id: str) -> Capability | None:
    return _REGISTRY.get(cap_id)


def list_capabilities(*, surface: str | None = None) -> list[dict]:
    return [
        {
            "id": cap.id, "module": cap.module, "surface": cap.surface,
            "permission": cap.permission, "description": cap.description,
            "input_schema": cap.input_schema, "mutates": cap.mutates,
        }
        for cap in sorted(_REGISTRY.values(), key=lambda c: c.id)
        if surface is None or cap.surface == surface
    ]


def invoke(cap_id: str, params: dict | None = None, *,
           context: dict | None = None,
           allowed_permissions: set[str] | None = None) -> dict:
    """Invoke a capability with permission enforcement and error handling."""
    cap = _REGISTRY.get(cap_id)
    if cap is None:
        raise CapabilityError(f"unknown capability: {cap_id}", code="not_found")
    params = params or {}
    if not isinstance(params, dict):
        raise CapabilityError("params must be an object", code="bad_params")
    allowed = allowed_permissions if allowed_permissions is not None else {
        "read", "write", "execute"}
    if cap.permission not in allowed:
        raise CapabilityError(
            f"permission {cap.permission!r} required for {cap_id}",
            code="permission_denied")
    context = context or {}
    started = time.monotonic()
    try:
        result = cap.handler(params, context)
        return {
            "ok": True, "capability": cap_id, "result": result,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }
    except CapabilityError:
        raise
    except Exception as exc:  # handlers must surface real errors, not fake success
        raise CapabilityError(
            f"{type(exc).__name__}: {exc}"[:500], code="handler_error") from exc


def audit_path(state_root: str | Path) -> Path:
    return Path(state_root) / "capability-audit.jsonl"


def record_audit(state_root: str | Path, entry: dict) -> None:
    path = audit_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(entry)
    record.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
