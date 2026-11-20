"""keel.hooks — the hook bus (command handlers only).

Event set is the 33 spec names (spec §7.1, open set: unrecognised configured
events are ignored, never fatal). The Session turn loop wires the lifecycle
events that have real execution paths: SessionStart, UserPromptSubmit,
PreToolUse, PermissionRequest, PermissionDenied, PostToolUse,
PostToolUseFailure, PostToolBatch, PreCompact, PostCompact, Stop, StopFailure
and SessionEnd. Other declared events remain available for future runtime
surfaces; configuring them is harmless.

Verdict protocol (spec §7.4): exit 0 = proceed; exit 2 = block (reason is
stderr); anything else / timeout / crash = proceed + report. Combining:
deny > defer > ask > allow; deny blocks; ask -> deny when non-interactive.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

KNOWN_EVENTS = frozenset([
    "SessionStart", "Setup",
    "UserPromptSubmit", "UserPromptExpansion",
    "PreToolUse", "PermissionRequest", "PermissionDenied",
    "PostToolUse", "PostToolUseFailure", "PostToolBatch",
    "Notification", "MessageDisplay",
    "SubagentStart", "SubagentStop",
    "TaskCreated", "TaskCompleted",
    "Stop", "StopFailure", "TeammateIdle",
    "InstructionsLoaded", "ConfigChange",
    "CwdChanged", "DirectoryAdded", "FileChanged",
    "WorktreeCreate", "WorktreeRemove",
    "PreCompact", "PostCompact",
    "PreModelSwitch", "PostModelSwitch",
    "Elicitation", "ElicitationResult",
    "SessionEnd",
])


@dataclass(frozen=True)
class HookDefinition:
    event: str
    matcher: str | None          # absent = match everything
    command: str
    name: str = "hook"
    timeout: float = 10.0


@dataclass
class HookOutcome:
    name: str
    event: str
    verdict: str                  # allow | defer | ask | deny | proceed | blocked
    reason: str = ""
    stderr: str = ""
    exit_code: int | None = None
    stdout_json: dict | None = None
    duration_ms: int = 0
    updated_input: dict | None = None
    additional_context: str | None = None
    system_message: str | None = None


@dataclass
class HookDecision:
    outcomes: list[HookOutcome] = field(default_factory=list)

    @property
    def denied(self) -> bool:
        return any(o.verdict == "deny" for o in self.outcomes)

    @property
    def ask(self) -> bool:
        return any(o.verdict == "ask" for o in self.outcomes)

    @property
    def updated_input(self) -> dict | None:
        for o in self.outcomes:
            if o.updated_input is not None:
                return o.updated_input
        return None

    def reason(self) -> str:
        for o in self.outcomes:
            if o.verdict in ("deny", "ask"):
                return o.reason or o.stderr or "hook verdict"
        return ""


def parse_hooks(raw: Any) -> list[HookDefinition]:
    """Parse the settings `hooks` object into definitions; tolerate junk."""
    out: list[HookDefinition] = []
    if not isinstance(raw, dict):
        return out
    for event, entries in raw.items():
        event_name = str(event)
        if event_name not in KNOWN_EVENTS:
            continue  # open set: ignore, never fail
        if not isinstance(entries, list):
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            command = entry.get("command")
            if not command or not isinstance(command, str):
                continue  # non-command handlers not supported yet
            timeout = entry.get("timeout", 10)
            try:
                timeout_f = float(timeout)
            except (TypeError, ValueError):
                timeout_f = 10.0
            out.append(HookDefinition(
                event=event_name,
                matcher=entry.get("matcher"),
                command=command,
                name=str(entry.get("name", f"{event_name}[{i}]")),
                timeout=timeout_f))
    return out


def _match(hook: HookDefinition, subject: str | None) -> bool:
    if not hook.matcher:
        return True
    if subject is None:
        return False
    return hook.matcher.lower() == subject.lower()


def _subject_for(event: str, payload: dict) -> str | None:
    if event.startswith("User"):
        return payload.get("user_input") or payload.get("command")
    return payload.get("tool_name") or payload.get("command")


def _tokenize_command(command: str) -> list[str]:
    """Shell-word split without a shell: quotes group, backslashes escape.

    Pipelines/subshells are not supported by design — a hook that needs a
    shell can invoke `cmd /c "..."` or `sh -c "..."` explicitly. Windows
    cmd.exe nested-quote ambiguity is avoided by construction.
    """
    argv: list[str] = []
    cur: list[str] = []
    in_single = in_double = False
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and i + 1 < len(command) and command[i + 1] in ('"', "'", "\\"):
            cur.append(command[i + 1])
            i += 2
            continue
        if ch == "'":
            in_single = not in_single
            i += 1
            continue
        if ch == '"':
            in_double = not in_double
            i += 1
            continue
        if ch in " \t\r\n" and not in_single and not in_double:
            if cur:
                argv.append("".join(cur))
                cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    if in_single or in_double:
        raise ValueError("unterminated quote in hook command")
    if cur:
        argv.append("".join(cur))
    if not argv:
        raise ValueError("empty hook command")
    return argv


def fire(hooks: list[HookDefinition], event: str, payload: dict, *,
         stop_hook_active: bool = False,
         emit=None) -> HookDecision:
    """Run every matching hook; combine verdicts (deny > defer > ask > allow).

    If emit is given it is called as emit(kind, hook_or_outcome, event, tool_use_id).
    """
    subject = _subject_for(event, payload)
    tool_use_id = payload.get("tool_use_id")
    decision = HookDecision()
    for hook in hooks:
        if hook.event != event:
            continue
        if not _match(hook, subject):
            continue
        if emit is not None:
            emit("started", hook, event, tool_use_id)
        outcome = _run_one(hook, event, payload, stop_hook_active)
        decision.outcomes.append(outcome)
        if emit is not None:
            emit("response", outcome, event, tool_use_id)
    return decision


def _run_one(hook: HookDefinition, event: str, payload: dict,
             stop_hook_active: bool) -> HookOutcome:
    body = json.dumps({**payload,
                       "hook_event_name": event,
                       "stop_hook_active": stop_hook_active},
                      separators=(",", ":"), ensure_ascii=False)
    t0 = time.monotonic()
    try:
        argv = _tokenize_command(hook.command)
    except ValueError as exc:
        return HookOutcome(name=hook.name, event=event, verdict="proceed",
                           reason=f"hook command rejected: {exc}",
                           exit_code=None,
                           duration_ms=int((time.monotonic() - t0) * 1000))
    try:
        proc = subprocess.run(
            argv,
            input=body.encode("utf-8"),
            capture_output=True,
            timeout=hook.timeout,
            check=False)
    except FileNotFoundError:
        return HookOutcome(name=hook.name, event=event, verdict="proceed",
                           reason="hook command not found",
                           exit_code=None,
                           duration_ms=int((time.monotonic() - t0) * 1000))
    except subprocess.TimeoutExpired:
        return HookOutcome(name=hook.name, event=event, verdict="proceed",
                           reason="hook timed out",
                           exit_code=None,
                           duration_ms=int((time.monotonic() - t0) * 1000))
    except OSError as exc:
        return HookOutcome(name=hook.name, event=event, verdict="proceed",
                           reason=f"hook could not be started: {exc}",
                           exit_code=None,
                           duration_ms=int((time.monotonic() - t0) * 1000))

    duration_ms = int((time.monotonic() - t0) * 1000)
    stderr = proc.stderr.decode("utf-8", errors="replace")
    stdout_text = proc.stdout.decode("utf-8", errors="replace")
    stdout_json = None
    if stdout_text.strip():
        try:
            candidate = json.loads(stdout_text)
            if isinstance(candidate, dict):
                stdout_json = candidate
        except json.JSONDecodeError:
            pass  # §7.8: invalid stdout JSON is ignored

    if proc.returncode == 2:
        reason = stderr.strip() or "hook blocked (exit 2)"
        return HookOutcome(name=hook.name, event=event, verdict="deny",
                           reason=reason, stderr=stderr,
                           exit_code=2, stdout_json=stdout_json,
                           duration_ms=duration_ms,
                           updated_input=_updated_input(stdout_json),
                           system_message=_str_field(stdout_json,
                                                     "systemMessage"))
    if proc.returncode == 0:
        if stdout_json is None:
            return HookOutcome(name=hook.name, event=event,
                               verdict="allow",
                               stderr=stderr, exit_code=0,
                               duration_ms=duration_ms)
        decision = str(stdout_json.get("decision", "allow")).lower()
        verdict = decision if decision in ("allow", "deny", "ask", "defer") \
            else "allow"
        return HookOutcome(
            name=hook.name, event=event, verdict=verdict,
            reason=str(stdout_json.get("reason", "")),
            stderr=stderr, exit_code=0, stdout_json=stdout_json,
            duration_ms=duration_ms,
            updated_input=_updated_input(stdout_json),
            additional_context=_additional_context(stdout_json),
            system_message=_str_field(stdout_json, "systemMessage"))
    # §7.4: anything else = proceed + report
    first_line = stderr.strip().splitlines()[0] if stderr.strip() else ""
    return HookOutcome(name=hook.name, event=event, verdict="proceed",
                       reason=first_line or f"hook exited {proc.returncode}",
                       stderr=stderr, exit_code=proc.returncode,
                       stdout_json=stdout_json, duration_ms=duration_ms)


def _updated_input(stdout_json: dict | None) -> dict | None:
    if not stdout_json:
        return None
    hso = stdout_json.get("hookSpecificOutput")
    if isinstance(hso, dict):
        ui = hso.get("updatedInput")
        if isinstance(ui, dict):
            return ui
    return None


def _additional_context(stdout_json: dict | None) -> str | None:
    if not stdout_json:
        return None
    hso = stdout_json.get("hookSpecificOutput")
    if isinstance(hso, dict):
        ctx = hso.get("additionalContext")
        if isinstance(ctx, str):
            return ctx
    return None


def _str_field(stdout_json: dict | None, field: str) -> str | None:
    if not stdout_json:
        return None
    value = stdout_json.get(field)
    return value if isinstance(value, str) else None
