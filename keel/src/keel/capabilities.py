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
    # Saved execution policies bind the capability surface too: a capability
    # carrying a command or URL is checked before its handler runs.
    from .policy_enforcement import enforce as _enforce_policy

    enforced = _enforce_policy(
        cap_id, params,
        state_root=context.get("state_root"),
        interactive=bool(context.get("interactive")),
        confirmed=bool(context.get("confirm")))
    if enforced is not None and enforced.decision == "deny":
        raise CapabilityError(
            f"execution policy denied {cap_id}: {enforced.reason}",
            code="policy_denied")
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


# --- Master Plan v6 backend module integration -----------------------------
# The 20 backend modules implemented for the v6 registry are reached through
# this authenticated, permission-aware surface (web bridge, CLI, TUI, desktop).
# Handlers import the hub lazily so capability-hub import stays cheap.


def _register_backend_capabilities() -> None:
    from . import backend_hub as _hub

    def _bad(exc: Exception) -> CapabilityError:
        return CapabilityError(str(exc), code="bad_request")

    @capability(
        "backend.modules", "backend_hub", "core", "read",
        "List integrated v6 backend modules and their feature counts",
        schema={"type": "object", "properties": {}},
    )
    def _backend_modules(params: dict, context: dict):
        return {"modules": _hub.modules(), "feature_count": len(_hub.feature_ids())}

    @capability(
        "backend.describe", "backend_hub", "core", "read",
        "Describe a backend module's feature IDs and dispatchable functions",
        schema={"type": "object", "properties": {
            "module": {"type": "string"}}, "required": ["module"]},
    )
    def _backend_describe(params: dict, context: dict):
        try:
            return _hub.describe(params.get("module"))
        except _hub.BackendHubError as exc:
            raise _bad(exc) from exc

    @capability(
        "backend.invoke", "backend_hub", "core", "execute",
        "Execute an allowlisted deterministic function from a backend module",
        schema={"type": "object", "properties": {
            "module": {"type": "string"},
            "function": {"type": "string"},
            "params": {"type": "object"}},
            "required": ["module", "function"]},
        mutates=False,
    )
    def _backend_invoke(params: dict, context: dict):
        try:
            return _hub.invoke(
                params.get("module", ""), params.get("function", ""),
                params.get("params") or {})
        except _hub.BackendHubError as exc:
            raise _bad(exc) from exc

    @capability(
        "backend.verify", "backend_hub", "core", "read",
        "Verify a backend module imports and declares its feature contract",
        schema={"type": "object", "properties": {
            "module": {"type": "string"}}, "required": ["module"]},
    )
    def _backend_verify(params: dict, context: dict):
        try:
            return _hub.verify(params.get("module", ""))
        except _hub.BackendHubError as exc:
            raise _bad(exc) from exc


_register_backend_capabilities()
