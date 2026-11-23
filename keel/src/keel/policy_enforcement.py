"""Enforce saved execution policies at real runtime boundaries.

A policy that is only evaluated by a CLI command is not enforced. This module
is called by the Tier-1 permission evaluator (``permissions.evaluate``) and by
the capability hub (``capabilities.invoke``) *before* any command or network
operation runs. It is dormant until a ``default`` policy is saved locally, so
existing installs keep their current behaviour; once configured it is binding
and cannot be weakened by ``bypassPermissions`` mode.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path

from .exec_policy import (ALLOW, FORBIDDEN, PROMPT, ExecPolicyStore,
                          normalize_host)

# Any parameter that can carry a command, argv or source to an execute-class
# capability must be visible to the policy boundary. Previously argv[]-based
# capabilities (`core.os.sandbox.run`) and code/prompt-based ones bypassed it.
COMMAND_FIELDS = (
    "command", "cmd", "shell_command", "shellCommand",
    "argv", "args", "code", "prompt", "script", "input",
)
URL_FIELDS = ("url", "uri", "endpoint")
DEFAULT_POLICY = "default"


def policy_path(state_root: str | Path | None = None) -> Path:
    if state_root is None:
        from . import settings

        state_root = settings.default_state_root()
    return Path(state_root) / "exec-policies" / f"{DEFAULT_POLICY}.json"


def active_policy(state_root: str | Path | None = None):
    """Return the saved default policy, or None when none was configured."""
    path = policy_path(state_root)
    from .exec_policy import from_dict, read_policy_doc

    document = read_policy_doc(path)
    return from_dict(document) if document is not None else None


def command_from(tool_name: str, tool_input: dict) -> str | None:
    for field in COMMAND_FIELDS:
        value = tool_input.get(field)
        if isinstance(value, (list, tuple)):
            parts = [str(item) for item in value if str(item).strip()]
            if parts:
                return " ".join(parts)
        if isinstance(value, str) and value.strip():
            return value
    # Inline shell prefix (!cmd) is stored under `text` / `prompt` by A1.6.
    if tool_name.lower() in ("inline_shell", "inline_shell_command", "shell"):
        for field in ("text", "prompt", "input"):
            value = tool_input.get(field)
            if isinstance(value, str) and value.startswith("!"):
                return value[1:].strip()
    return None


def url_from(tool_input: dict) -> str | None:
    for field in URL_FIELDS:
        value = tool_input.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _decision(decision: str, reason: str, matched: str | None):
    # Delay import to avoid a cycle: permissions imports shell_ast only.
    from .permissions import Decision

    return Decision(
        decision, "policy", reason, "policy", matched,
        None if decision != "deny" else "execute", False)


def enforce(tool_name: str, tool_input: dict, *,
            state_root: str | Path | None = None,
            interactive: bool = False,
            confirmed: bool = False):
    """Return a Decision when a saved policy governs this tool call, else None.

    ``forbidden`` always denies. ``prompt`` asks interactively and denies in
    non-interactive mode unless ``confirmed`` is supplied by the caller's
    approval workflow. Explicit ``allow`` overrides a mode baseline (but never
    a config deny rule, which is evaluated first by the caller).
    """
    # Policy-management capabilities must never be blocked by the policy they
    # inspect or edit (otherwise the UI cannot evaluate or deactivate it).
    if tool_name.startswith("core.execpolicy."):
        return None
    policy = active_policy(state_root)
    if policy is None:
        return None
    tool_input = tool_input or {}

    command = command_from(tool_name, tool_input)
    if command:
        evaluation = policy.check(command)
        if evaluation.is_match:
            rule = evaluation.matched_rules[0]
            if evaluation.decision == FORBIDDEN:
                return _decision("deny",
                                 f"execution policy forbids {command!r}"
                                 + (f": {rule.justification}"
                                    if rule.justification else ""),
                                 rule.justification)
            if evaluation.decision == PROMPT:
                if confirmed:
                    return _decision("allow",
                                     f"execution policy approval recorded for "
                                     f"{command!r}", rule.justification)
                if not interactive:
                    return _decision("deny",
                                     f"policy requires consent for {command!r}; "
                                     "no interactive approval in this mode",
                                     rule.justification)
                return _decision("ask",
                                 f"policy requires approval for {command!r}",
                                 rule.justification)
            return _decision("allow",
                             f"execution policy allows {command!r}",
                             rule.justification)

    url = url_from(tool_input)
    if url:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in ("http", "https"):
            host = parsed.hostname or ""
            verdict = policy.evaluate_network(host, parsed.scheme)
            if verdict != PROMPT:
                if verdict == FORBIDDEN:
                    return _decision("deny",
                                     f"egress policy forbids host {host!r}",
                                     f"network:{parsed.scheme}:{host}")
                return _decision("allow",
                                 f"egress policy allows host {host!r}",
                                 f"network:{parsed.scheme}:{host}")
    return None
