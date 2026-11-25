"""keel.fleet.approvals — F1 approval cards broker.

One broker per FleetStore. The broker owns the *waiting* side of the approval
flow: provider turns block on a threading.Event inside their own worker
thread (never the HTTP server), the web bridge decides cards via
`decide()`.

Guarantees:

- A card left unanswered for `timeout_s` (default 300s, env override
  KEEL_FLEET_APPROVAL_TIMEOUT_S) resolves to *denied*; the tool does not run.
- `decide()` and `expire()` race through a guarded SQL transition
  (pending -> decided); exactly one wins.
- Approvals are scoped per (bot_id, tool_name); nothing is ever shared
  across agents.
- Fleet decisions only ever *convert* a `consent_required` Tier-1 verdict.
  They cannot widen deny rules, hooks or Tier 2 — those stay authoritative.
- Audit records carry fingerprints (sha256 of canonical tool_input), never
  raw arguments.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone

from ..redaction import redact_text

from ..permissions import Decision


APPROVAL_DECIDED_RACE_MSG = "approval already decided"


def fingerprint(tool_input) -> str:
    try:
        canonical = json.dumps(tool_input or {}, sort_keys=True,
                               separators=(",", ":"), ensure_ascii=False,
                               default=str)
    except (TypeError, ValueError):
        canonical = str(tool_input)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _utcnow() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _truncate(text: str, limit: int) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def args_summary(tool_name: str, tool_input: dict) -> str:
    """Human-facing one-liner for the card. Truncated and redacted."""
    summary = _raw_args_summary(tool_name, tool_input)
    redacted, _ = redact_text(summary)
    return redacted


def _raw_args_summary(tool_name: str, tool_input: dict) -> str:
    """Build the raw summary; only ``args_summary`` may expose it."""
    args = tool_input or {}
    if tool_name == "run_shell":
        return _truncate(args.get("command") or "(empty command)", 1000)
    if tool_name in ("write_file", "edit_file"):
        path = args.get("path") or args.get("file_path") or "?"
        if tool_name == "write_file":
            content = str(args.get("content") or "")
            return _truncate(f"{path}  ({len(content)} chars)", 1000)
        return _truncate(f"{path}  (old_string → new_string)", 1000)
    if tool_name == "Task":
        return _truncate(f"prompt: {args.get('prompt') or args.get('description') or ''}", 1000)
    if tool_name == "send_to_bot":
        slug = args.get("bot_slug") or "?"
        task = args.get("task_id")
        suffix = f"  [task {task}]" if task else ""
        return _truncate(f"→ {slug}: {args.get('message', '')}{suffix}", 1000)
    if tool_name == "create_task":
        return _truncate(f"task: {args.get('title', '')!r}"
                         + (f" (priority={args.get('priority')})" if args.get("priority") else ""),
                         1000)
    if tool_name == "update_task":
        parts = [str(args.get("task_id", "?"))]
        if args.get("status"):
            parts.append(f"→ {args['status']}")
        if args.get("progress") is not None:
            parts.append(f"progress {args['progress']}%")
        if args.get("note"):
            parts.append(f"note: {args['note']}")
        return _truncate("  ".join(parts), 1000)
    if tool_name == "list_tasks":
        return _truncate(f"list tasks (assigned_to={args.get('assigned_to', 'me')})", 1000)
    if tool_name == "save_file":
        task = args.get("task_id")
        suffix = f"  [task {task}]" if task else ""
        content = str(args.get("content", ""))
        return _truncate(f"save {args.get('filename', '?')} "
                         f"({len(content)} chars){suffix}", 1000)
    if tool_name.startswith("mcp__"):
        return _truncate(f"args: {json.dumps(args, ensure_ascii=False, default=str)}", 1000)
    try:
        return _truncate(json.dumps(args, ensure_ascii=False, default=str), 1000)
    except (TypeError, ValueError):
        return _truncate(str(args), 1000)


def explanation(tool_name: str) -> str:
    table = {
        "write_file": "Create or overwrite a file on disk.",
        "edit_file": "Edit an existing file on disk.",
        "run_shell": "Run a shell command on this machine.",
        "Task": "Delegate work to a subagent, which may itself use tools.",
        "send_to_bot": "Send a task to another Fleet agent; the receiving agent runs with its own permissions.",
        "create_task": "Create a tracked task in the Fleet task list.",
        "update_task": "Change a task's status, progress or note.",
        "list_tasks": "List tasks and their statuses.",
        "save_file": "Write a file into your Fleet Library (owned by you).",
    }
    if tool_name in table:
        return table[tool_name]
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        server = parts[1] if len(parts) > 1 else "?"
        tool = parts[2] if len(parts) > 2 else tool_name
        return f"Call external MCP tool “{tool}” on server “{server}”."
    return f"Use the {tool_name} tool."


class ApprovalBroker:
    """Per-store decision registry; owns the waiting side of approvals."""

    def __init__(self, store, timeout_s: float | None = None):
        self.store = store
        self.timeout_s = float(timeout_s if timeout_s is not None
                               else os.environ.get("KEEL_FLEET_APPROVAL_TIMEOUT_S", 300))
        self._events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # ---------------- creation + waiting (provider turn thread)
    def request(self, *, bot: dict, tool_name: str, tool_input: dict,
                tool_use_id: str) -> dict:
        fp = fingerprint(tool_input)
        approval_id = uuid.uuid4().hex
        now = _utcnow()
        from datetime import timedelta
        expires_dt = datetime.now(timezone.utc) + timedelta(seconds=self.timeout_s)
        expires_at = (expires_dt.strftime("%Y-%m-%dT%H:%M:%S.")
                      + f"{expires_dt.microsecond // 1000:03d}Z")
        summary = args_summary(tool_name, tool_input)
        approval = self.store.create_approval(
            approval_id=approval_id, bot_id=bot["id"],
            tool_name=tool_name, fingerprint=fp,
            args_summary=summary, expires_at=expires_at)
        self.store.append_row(bot["id"], "approval", {
            "approval_id": approval_id,
            "tool_name": tool_name,
            "fingerprint": fp,
            "summary": summary,
            "explanation": explanation(tool_name),
            "status": "pending",
            "expires_at": expires_at,
            "requested_at": now,
        })
        self.store.append_audit(bot_id=bot["id"], tool_name=tool_name,
                                fingerprint=fp, event="requested",
                                approval_id=approval_id)
        from .runtime import current_routine_run
        active = current_routine_run()
        if active is not None:
            run_id, owner_bot = active
            if owner_bot == bot["id"]:
                self.store.mark_run_awaiting_approval(run_id)
        with self._lock:
            self._events[approval_id] = threading.Event()
        return approval

    def wait_for_decision(self, approval_id: str) -> dict | None:
        """Block the worker thread until decided or expired."""
        with self._lock:
            event = self._events.get(approval_id)
        if event is None:
            return self.store.get_approval(approval_id)
        decided = event.wait(timeout=self.timeout_s)
        with self._lock:
            self._events.pop(approval_id, None)
        if not decided:
            changed, approval = self.store.expire_approval(approval_id, by="timeout")
            if changed:
                self._announce_resolution(approval, "expired", "timeout")
            return self.store.get_approval(approval_id)
        return self.store.get_approval(approval_id)

    # ---------------- resolution handlers (HTTP bridge)
    def decide(self, *, bot_id: str, approval_id: str, decision: str) -> tuple[bool, dict, str | None]:
        """Operator click. Returns (changed, approval, error).

        'once' / 'always' / 'reject' never set a standing policy; 'never'
        denies this call and pins a standing Never policy.
        """
        if decision not in ("once", "always", "never", "reject"):
            return False, {}, "decision must be once | always | never | reject"
        approval = self.store.get_approval(approval_id)
        if approval is None or approval["bot_id"] != bot_id:
            return False, {}, "approval_not_found"
        changed, final = self.store.decide_approval(approval_id, decision=decision)
        if not changed:
            return False, final or approval, APPROVAL_DECIDED_RACE_MSG
        if decision == "always":
            self.store.set_policy(bot_id, final["tool_name"], "always")
        elif decision == "never":
            self.store.set_policy(bot_id, final["tool_name"], "never")
        granted = decision in ("once", "always")
        self.store.append_audit(bot_id=bot_id,
                                tool_name=final["tool_name"],
                                fingerprint=final["fingerprint"],
                                event="decided",
                                decision=decision,
                                outcome="granted" if granted else "refused",
                                approval_id=approval_id)
        self._announce_resolution(final,
                                  "approved" if granted else "denied",
                                  decision)
        with self._lock:
            event = self._events.get(approval_id)
        if event is not None:
            event.set()
        return True, final, None

    def _announce_resolution(self, approval: dict, status: str, decision: str) -> None:
        if not approval:
            return
        self.store.append_row(approval["bot_id"], "approval", {
            "approval_id": approval["approval_id"],
            "tool_name": approval["tool_name"],
            "status": status,
            "decision": decision,
            "decided_at": approval.get("decided_at"),
        })
        if status == "expired":
            self.store.append_audit(bot_id=approval["bot_id"],
                                    tool_name=approval["tool_name"],
                                    fingerprint=approval["fingerprint"],
                                    event="decided", decision="timeout",
                                    outcome="refused",
                                    approval_id=approval["approval_id"])

    def policy_outcome(self, *, bot: dict, tool_name: str,
                       tool_input: dict) -> Decision | None:
        """Short-circuit a standing policy, if one exists."""
        policy = self.store.get_policy(bot["id"], tool_name)
        fp = fingerprint(tool_input)
        if policy == "always":
            self.store.append_audit(bot_id=bot["id"], tool_name=tool_name,
                                    fingerprint=fp, event="decided",
                                    decision="always", outcome="granted")
            return Decision("allow", "fleet_policy",
                            "always-allowed by standing policy for this agent",
                            "fleet", "policy:always", None, False)
        if policy == "never":
            self.store.append_audit(bot_id=bot["id"], tool_name=tool_name,
                                    fingerprint=fp, event="decided",
                                    decision="never", outcome="refused")
            self.store.append_row(bot["id"], "notice", {
                "text": f"{tool_name} refused — standing Never policy for this agent. "
                        f"Revoke it in the Permissions tab.",
                "level": "warning",
            })
            return Decision("deny", "fleet_policy",
                            "refused by standing Never policy for this agent",
                            "fleet", "policy:never", None, False)
        return None

    # ---------------- the decider Session invokes at the tool boundary
    def decider(self, bot: dict):
        def _decide(ctx: dict) -> Decision:
            tool_name = ctx["tool_name"]
            tool_input = ctx.get("tool_input") or {}
            policy_decision = self.policy_outcome(bot=bot,
                                                  tool_name=tool_name,
                                                  tool_input=tool_input)
            if policy_decision is not None:
                return policy_decision
            approval = self.request(bot=bot, tool_name=tool_name,
                                    tool_input=tool_input,
                                    tool_use_id=ctx.get("tool_use_id") or "")
            approval = self.wait_for_decision(approval["approval_id"]) or {}
            decision = approval.get("decision")
            status = approval.get("status")
            if status == "approved":
                reason = ("approved once by operator via Fleet card"
                          if decision == "once" else
                          "approved always by operator via Fleet card")
                return Decision("allow", "fleet_approval", reason,
                                "fleet", f"card:{approval.get('approval_id')}",
                                None, False)
            if decision == "never":
                return Decision("deny", "fleet_approval",
                                "declined by operator via Fleet card",
                                "fleet", f"card:{approval.get('approval_id')}",
                                None, False)
            return Decision("deny", "fleet_timeout",
                            f"timed out after {int(self.timeout_s)}s waiting for "
                            "the operator; refused",
                            "fleet", f"card:{approval.get('approval_id')}",
                            None, False)
        return _decide

    # ---------------- fleet-side audit of execution outcome
    def outcome_audit(self, bot_id: str):
        def _record(ctx: dict) -> None:
            if ctx.get("source") != "fleet":
                return
            self.store.append_audit(
                bot_id=bot_id,
                tool_name=ctx["tool_name"],
                fingerprint=fingerprint(ctx.get("tool_input") or {}),
                event="outcome",
                decision=ctx.get("reason_type"),
                outcome=ctx.get("outcome"),
                approval_id=ctx.get("matched_rule", "").replace("card:", "")
                if str(ctx.get("matched_rule", "")).startswith("card:") else None)
        return _record
