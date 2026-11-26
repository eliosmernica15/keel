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


def _safe_exception_message(exc: Exception) -> str:
    from .redaction import redact_text

    return redact_text(f"{type(exc).__name__}: {exc}")[0][:500]


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


def permission_tiers_for_confirmation(confirmed: bool) -> set[str]:
    """Return the permission ceiling granted by a transport confirmation."""
    if confirmed is True:
        return {"read", "write", "execute"}
    return {"read"}


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
    context = context or {}
    context_permissions = context.get("allowed_permissions")
    if (allowed_permissions is not None
            and not isinstance(allowed_permissions, (set, frozenset))):
        raise CapabilityError(
            "invalid allowed permission set", code="permission_denied")
    if (context_permissions is not None
            and not isinstance(context_permissions, (set, frozenset))):
        raise CapabilityError(
            "invalid context permission set", code="permission_denied")
    if allowed_permissions is not None and context_permissions is not None:
        allowed = allowed_permissions & context_permissions
    elif allowed_permissions is not None:
        allowed = allowed_permissions
    elif context_permissions is not None:
        allowed = context_permissions
    else:
        allowed = {"read", "write", "execute"}
    if cap.permission not in allowed:
        raise CapabilityError(
            f"permission {cap.permission!r} required for {cap_id}",
            code="permission_denied")
    # Saved execution policies bind the capability surface too: a capability
    # carrying a command or URL is checked before its handler runs.
    from .policy_enforcement import enforce as _enforce_policy

    try:
        enforced = _enforce_policy(
            cap_id, params,
            state_root=context.get("state_root"),
            interactive=bool(context.get("interactive")),
            confirmed=bool(context.get("confirm")))
    except CapabilityError:
        raise
    except Exception as exc:
        # A corrupt policy file must never surface as a raw JSON/OS error or
        # bypass the typed CapabilityError boundary used by every transport.
        raise CapabilityError(
            f"policy evaluation failed for {cap_id}: "
            f"{_safe_exception_message(exc)}",
            code="policy_error") from None
    if enforced is not None and enforced.decision == "deny":
        raise CapabilityError(
            f"execution policy denied {cap_id}: {enforced.reason}",
            code="policy_denied")
    if (enforced is not None and enforced.decision == "ask"
            and context.get("confirm") is not True):
        # An unconfirmed `ask` must fail closed on every transport.
        raise CapabilityError(
            f"execution policy requires confirmation for {cap_id}: {enforced.reason}",
            code="confirmation_required")
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
            _safe_exception_message(exc), code="handler_error") from None


def audit_path(state_root: str | Path) -> Path:
    return Path(state_root) / "capability-audit.jsonl"


def record_audit(state_root: str | Path, entry: dict) -> None:
    from .backend_observability import (
        _acquire_lock, _append, _release_lock, redact,
    )

    path = audit_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = redact(dict(entry))
    record.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    lock_path = path.with_name(path.name + ".lock")
    lock_fd = _acquire_lock(lock_path)
    try:
        _append(path, json.dumps(record, ensure_ascii=False) + "\n")
    finally:
        _release_lock(lock_path, lock_fd)


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


# --- Cowork/Code/Duet/Fleet surface services (Master Plan surface spec) ----
def _register_surface_services() -> None:
    def _bad(exc: Exception) -> CapabilityError:
        return CapabilityError(str(exc), code="bad_request")
    from . import surface_services_backend as _s

    @capability("surface.deliverables.record", "surface_services", "core", "read",
               "Build a per-turn deliverable record with previews",
               schema={"type": "object", "properties": {
                   "turn_id": {"type": "string"}, "files": {"type": "array"}}},
               mutates=False)
    def _surface_deliverables(params, context):
        try:
            return _s.deliverable_record(params.get("turn_id", ""),
                                         params.get("files") or [])
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.checkpoint.create", "surface_services", "core", "execute",
               "Snapshot files into a per-turn checkpoint",
               schema={"type": "object", "properties": {
                   "state_root": {"type": "string"}, "turn_id": {"type": "string"},
                   "files": {"type": "object"}}, "required": ["state_root", "turn_id"]},
               mutates=True)
    def _surface_checkpoint_create(params, context):
        try:
            return _s.create_checkpoint(Path(params["state_root"]), params["turn_id"],
                                        params.get("files") or {})
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.checkpoint.restore", "surface_services", "core", "read",
               "Restore a per-turn checkpoint",
               schema={"type": "object", "properties": {
                   "state_root": {"type": "string"}, "turn_id": {"type": "string"}},
                   "required": ["state_root", "turn_id"]})
    def _surface_checkpoint_restore(params, context):
        try:
            return _s.restore_checkpoint(Path(params["state_root"]), params["turn_id"])
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.trash", "surface_services", "core", "execute",
               "Move a file to the recoverable Keel trash",
               schema={"type": "object", "properties": {
                   "state_root": {"type": "string"}, "target": {"type": "string"}},
                   "required": ["state_root", "target"]}, mutates=True)
    def _surface_trash(params, context):
        try:
            return {"trash_path": str(_s.trash_path(
                Path(params["state_root"]), Path(params["target"])))}
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.context.inspect", "surface_services", "core", "read",
               "Account prompt sources and token totals",
               schema={"type": "object", "properties": {
                   "sources": {"type": "array"}}})
    def _surface_context(params, context):
        return _s.context_inspector(params.get("sources") or [])

    @capability("surface.git.status", "surface_services", "core", "read",
               "Git working-tree status",
               schema={"type": "object", "properties": {
                   "repo": {"type": "string"}}, "required": ["repo"]})
    def _surface_git_status(params, context):
        try:
            return {"changes": _s.git_status(params["repo"])}
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.git.diff", "surface_services", "core", "read",
               "Git diff (optionally scoped to a path)",
               schema={"type": "object", "properties": {
                   "repo": {"type": "string"}, "path": {"type": "string"}},
                   "required": ["repo"]})
    def _surface_git_diff(params, context):
        try:
            return {"diff": _s.git_diff(params["repo"], path=params.get("path"))}
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.git.init", "surface_services", "core", "execute",
               "Initialize a git repository",
               schema={"type": "object", "properties": {
                   "repo": {"type": "string"}}, "required": ["repo"]}, mutates=True)
    def _surface_git_init(params, context):
        try:
            return {"output": _s.git_init(params["repo"])}
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.git.commit", "surface_services", "core", "execute",
               "Create a commit (requires allow_write)",
               schema={"type": "object", "properties": {
                   "repo": {"type": "string"}, "message": {"type": "string"}},
                   "required": ["repo", "message"]}, mutates=True)
    def _surface_git_commit(params, context):
        try:
            return {"output": _s.git_commit(
                params["repo"], params["message"], allow_write=True)}
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.notifications.push", "surface_services", "core", "write",
               "Queue a notification",
               schema={"type": "object", "properties": {
                   "state_root": {"type": "string"}, "kind": {"type": "string"},
                   "title": {"type": "string"}, "body": {"type": "string"}},
                   "required": ["state_root", "kind", "title", "body"]}, mutates=True)
    def _surface_notify_push(params, context):
        try:
            n = _s.NotificationQueue(Path(params["state_root"])).push(
                params["kind"], params["title"], params["body"])
            return {"kind": n.kind, "title": n.title, "body": n.body}
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.notifications.list", "surface_services", "core", "read",
               "List queued notifications",
               schema={"type": "object", "properties": {
                   "state_root": {"type": "string"}}, "required": ["state_root"]})
    def _surface_notify_list(params, context):
        try:
            return {"notifications": [
                {"kind": n.kind, "title": n.title, "body": n.body,
                 "acknowledged": n.acknowledged}
                for n in _s.NotificationQueue(Path(params["state_root"])).list()]}
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.terminal.run", "surface_services", "core", "execute",
               "Run a command in a real PTY and capture output",
               schema={"type": "object", "properties": {
                   "command": {"type": "array"}, "timeout": {"type": "number"}},
                   "required": ["command"]}, mutates=False)
    def _surface_terminal_run(params, context):
        try:
            session = _s.TerminalSession(params["command"])
            code, out = session.run_sync(timeout=float(params.get("timeout", 10.0)))
            return {"exit_code": code, "output": out.decode("utf-8", errors="replace")}
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc

    @capability("surface.deliverables.export", "surface_services", "core", "write",
               "Export deliverables to a zip archive",
               schema={"type": "object", "properties": {
                   "turn_id": {"type": "string"}, "files": {"type": "object"},
                   "dest": {"type": "string"}}, "required": ["turn_id", "files", "dest"]},
               mutates=True)
    def _surface_deliverables_export(params, context):
        try:
            return {"path": str(_s.export_deliverables_zip(
                params["turn_id"], params["files"], Path(params["dest"])))}
        except _s.SurfaceError as exc:
            raise _bad(exc) from exc


_register_surface_services()
