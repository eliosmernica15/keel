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

import contextlib
import errno
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .redaction import redact_text


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


_SCHEMA_SYNC_LOCK = threading.Lock()
_SCHEMA_SYNC_STATE = {"done": False, "busy": False}


def _ensure_backend_schemas() -> None:
    """Publish signature-derived backend schemas on first capability discovery.

    Importing ``backend_hub`` at module import time would make every startup
    pay for the whole backend registry.  Instead discovery (``get`` /
    ``list_capabilities``) triggers the hub's idempotent sync exactly once.
    The busy flag prevents recursion: the hub's sync calls ``capabilities.get``.
    """
    state = _SCHEMA_SYNC_STATE
    if state["done"] or state["busy"]:
        return
    with _SCHEMA_SYNC_LOCK:
        if state["done"] or state["busy"]:
            return
        state["busy"] = True
        try:
            from . import backend_hub
            backend_hub.sync_capability_schemas()
            state["done"] = True
        except Exception:
            # Discovery must still work if the optional backend registry is
            # unavailable; the next call may retry.
            pass
        finally:
            state["busy"] = False


def get(cap_id: str) -> Capability | None:
    _ensure_backend_schemas()
    return _REGISTRY.get(cap_id)


def list_capabilities(*, surface: str | None = None) -> list[dict]:
    _ensure_backend_schemas()
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
    context = dict(context or {})
    if allowed_permissions is None:
        # Derive tiers from the real caller/session when it supplies them.
        # HTTP now passes its derived tier set explicitly; legacy in-process
        # callers (which historically omitted the argument) keep all tiers so
        # existing capability calls are not broken.  A session-supplied set is
        # authoritative and can narrow the call to least privilege.
        session_tiers = context.get("allowed_permissions")
        allowed = (set(session_tiers) if session_tiers is not None
                   else {"read", "write", "execute"})
    else:
        allowed = set(allowed_permissions)
    if cap.permission not in allowed:
        reason = f"permission {cap.permission!r} required for {cap_id}"
        _emit_capability_event(
            cap_id, params, context, outcome="denied", kind="permission_decided",
            tool_use_id=_safe_error(reason)[:200], decision="deny",
            reason=_safe_error(reason))
        raise CapabilityError(reason, code="permission_denied")
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
        raise CapabilityError(_safe_error(
            f"policy evaluation failed for {cap_id}: "
            f"{type(exc).__name__}: {exc}"), code="policy_error") from exc
    if enforced is not None and enforced.decision == "deny":
        reason = f"execution policy denied {cap_id}: {enforced.reason}"
        _emit_capability_event(
            cap_id, params, context, outcome="denied", kind="permission_decided",
            tool_use_id=_safe_error(reason)[:200], decision="deny",
            reason=_safe_error(reason))
        raise CapabilityError(reason, code="policy_denied")
    if (enforced is not None and enforced.decision == "ask"
            and context.get("confirm") is not True):
        # An unconfirmed `ask` must fail closed on every transport.
        reason = f"execution policy requires confirmation for {cap_id}: {enforced.reason}"
        _emit_capability_event(
            cap_id, params, context, outcome="denied", kind="permission_decided",
            tool_use_id=_safe_error(reason)[:200], decision="deny",
            reason=_safe_error(reason))
        raise CapabilityError(reason, code="confirmation_required")
    started = time.monotonic()
    try:
        result = cap.handler(params, context)
        _emit_capability_event(
            cap_id, params, context, outcome="ok", kind="job_completed",
            job_id=_safe_error(cap_id)[:200], status="completed")
        return {
            "ok": True, "capability": cap_id, "result": result,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }
    except CapabilityError:
        raise
    except Exception as exc:  # handlers must surface real errors, not fake success
        reason = _safe_error(f"{type(exc).__name__}: {exc}")
        _emit_capability_event(
            cap_id, params, context, outcome="error", kind="error_recorded",
            error_id=_safe_error(cap_id)[:200], severity="error",
            message=reason)
        raise CapabilityError(reason, code="handler_error") from exc


def audit_path(state_root: str | Path) -> Path:
    return Path(state_root) / "capability-audit.jsonl"


_AUDIT_LOCKS: dict[str, threading.Lock] = {}
_AUDIT_LOCKS_GUARD = threading.Lock()
_AUDIT_LOCK_TIMEOUT_SECONDS = 5.0
_AUDIT_LOCK_STALE_SECONDS = 30.0


@contextlib.contextmanager
def _audit_lock(path: Path):
    """Serialize audit appends across threads and processes.

    A plain text-mode ``open(..., "a")`` can lose or split records when several
    processes write at once.  An exclusive O_EXCL lock file (with stale-lock
    recovery) makes each JSONL line atomic.  On extreme contention we fall back
    to an O_APPEND write rather than raising from a best-effort audit call.
    """
    with _AUDIT_LOCKS_GUARD:
        thread_lock = _AUDIT_LOCKS.setdefault(str(path.resolve()),
                                              threading.Lock())
    with thread_lock:
        lock_path = path.with_name(path.name + ".lock")
        deadline = time.monotonic() + _AUDIT_LOCK_TIMEOUT_SECONDS
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(
                    lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                try:
                    age = time.time() - lock_path.stat().st_mtime
                except OSError:
                    age = 0.0
                if age > _AUDIT_LOCK_STALE_SECONDS:
                    with contextlib.suppress(OSError):
                        lock_path.unlink()
                    continue
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(0.005)
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EPERM, errno.EBUSY,
                                 errno.EAGAIN, errno.EINTR):
                    if time.monotonic() >= deadline:
                        yield False
                        return
                    time.sleep(0.005)
                    continue
                raise
        try:
            marker = f"{os.getpid()} {time.time():.6f}\n".encode("ascii")
            os.write(descriptor, marker)
            yield True
        finally:
            with contextlib.suppress(OSError):
                os.close(descriptor)
            with contextlib.suppress(OSError):
                lock_path.unlink()


def _safe_error(text: Any) -> str:
    """Never echo a raw handler/policy exception: it may contain credentials."""
    return redact_text(str(text))[0][:500]


def _emit_capability_event(cap_id: str, params: dict, context: dict, *,
                           outcome: str, kind: str, **fields: Any) -> None:
    """Publish complementary typed evidence for a capability decision.

    This is a post-decision emit only. Permission/policy verdicts above are the
    sole authorization authority; nothing reads these events back. Emission
    failures are deliberately non-fatal to the capability call, but are
    redacted and never reported as success through the event stream.
    """
    try:
        from .automation import publish_durable
        from .settings import default_state_root

        correlation = hashlib.sha256(json.dumps(
            [cap_id, params], sort_keys=True, default=str,
            ensure_ascii=False).encode("utf-8")).hexdigest()
        event_id = "cap-" + hashlib.sha256(
            f"{cap_id}:{outcome}:{correlation}".encode("utf-8")
        ).hexdigest()[:24]
        session_id = str(context.get("session_id") or "capability")
        metadata = [("source", "capabilities"), ("correlation_id", correlation),
                    ("outcome", outcome)]
        publish_durable(
            context.get("state_root") or default_state_root(), kind,
            event_id=event_id, session_id=session_id, metadata=metadata, **fields)
    except Exception:
        pass  # complementary evidence must never change the decision


def _redact_value(node: Any) -> Any:
    if isinstance(node, str):
        return redact_text(node)[0]
    if isinstance(node, dict):
        return {key: _redact_value(value) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_redact_value(value) for value in node]
    return node


def record_audit(state_root: str | Path, entry: dict) -> None:
    """Append one redacted, atomically written JSONL audit record."""
    path = audit_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = _redact_value(dict(entry))
    record.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    payload = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    with _audit_lock(path):
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            remaining = payload
            while remaining:
                remaining = remaining[os.write(descriptor, remaining):]
        finally:
            os.close(descriptor)


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
