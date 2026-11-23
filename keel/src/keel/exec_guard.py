"""Shared authorization guard for exec-capable capability handlers.

The capability hub (``capabilities.invoke``) already checks the declared
permission tier and calls ``policy_enforcement.enforce`` on the raw params.
That policy check only recognises canonical command fields (``command``,
``cmd``, ``shell_command``, ``shellCommand``) plus inline ``!cmd`` text.
Several real capability handlers carry the executable or source under other
names (``argv``, ``code``, ``source``, ``script``). Without normalisation a
saved execution policy silently does not apply to those routes.

``enforce_command`` closes that gap. It is called *inside* the command-bearing
handler, immediately before the sandbox boundary, so a policy denial cannot be
bypassed by changing the parameter name. It never starts a process itself; it
only normalises and re-checks the authoritative saved policy.

Handlers keep importing their sandbox boundary lazily so tests can spy on
``keel.os_sandbox.run_confined`` / ``keel.sandbox_exec.run_python``.
"""

from __future__ import annotations

import shlex

from .capabilities import CapabilityError

# Fields that carry executable content on the capability surface. The first
# four are the fields policy_enforcement already understands; the rest need
# normalisation here.
EXEC_FIELDS = (
    "command", "cmd", "shell_command", "shellCommand",
    "argv", "code", "source", "script",
)


def command_text(params: dict, *, field: str | None = None) -> str | None:
    """Return a single command string for *params*, or None when absent."""
    params = params or {}
    fields = (field,) if field else EXEC_FIELDS
    for name in fields:
        if name not in params:
            continue
        value = params[name]
        if isinstance(value, (list, tuple)):
            parts = [str(v) for v in value if str(v).strip()]
            if not parts:
                continue
            return " ".join(shlex.quote(p) for p in parts)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def enforce_command(cap_id: str, params: dict, ctx: dict | None = None, *,
                    command: str | None = None,
                    field: str | None = None) -> str | None:
    """Enforce the authoritative saved exec policy for a command route.

    Returns the normalised command text (useful for audit/logging) or None when
    the route carried no executable content. Raises ``CapabilityError`` with
    code ``policy_denied`` / ``policy_requires_approval`` on a deny or an
    unresolved ask. ``allow`` and "no policy configured" both pass through.
    """
    text = command if command is not None else command_text(params, field=field)
    if not text:
        return None

    normalized = dict(params or {})
    # policy_enforcement only inspects this canonical field; set it
    # unconditionally so renamed command fields cannot slip past the check.
    normalized["command"] = text
    # Drop duplicate payload fields so a policy cannot be satisfied by one
    # field while a different field is what actually gets executed.
    for name in ("argv", "code", "source", "script", "cmd",
                 "shell_command", "shellCommand"):
        normalized.pop(name, None)

    from .policy_enforcement import enforce as _enforce

    decision = _enforce(
        cap_id, normalized,
        state_root=(ctx or {}).get("state_root"),
        interactive=bool((ctx or {}).get("interactive")),
        confirmed=bool((ctx or {}).get("confirm")))
    if decision is None or decision.decision == "allow":
        return text
    if decision.decision == "ask":
        # The capability hub has no interactive approval UI. Fail closed
        # instead of letting an unresolved prompt run unattended.
        raise CapabilityError(
            f"execution policy requires approval for {cap_id}: {decision.reason}",
            code="policy_requires_approval")
    raise CapabilityError(
        f"execution policy denied {cap_id}: {decision.reason}",
        code="policy_denied")
