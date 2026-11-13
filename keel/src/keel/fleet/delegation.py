"""keel.fleet.delegation — the receiving side of send_to_bot.

Runs the target agent inline (on a worker thread with a deadline) so the
caller's tool call resolves as a normal tool_result. Guarantees:

- the target sees only its own identity, notes, history and permissions —
  nothing of the caller's private data leaks into its turn;
- the target's per-bot lock is honoured: a busy target fails fast with
  `agent_busy` instead of deadlocking either side;
- the turn has a hard deadline (KEEL_FLEET_DELEGATE_TIMEOUT_S, default 60s);
  on expiry the caller gets an error result while the target's rows still
  land when its detached worker finishes;
- the target appends a delegated user row in its own conversation; the
  caller sees a `delegated_to` payload on its send_to_bot step row.
"""

from __future__ import annotations

import os
import threading

from ..instructions import delegation_attachment
from .echo import try_lock, unlock
from .turn_core import execute_turn


def delegation_timeout_s() -> float:
    try:
        return float(os.environ.get("KEEL_FLEET_DELEGATE_TIMEOUT_S", 60))
    except ValueError:
        return 60.0


def build_delegated_user_row(caller: dict, message: str,
                             task_id: str | None = None) -> dict:
    body = {
        "role": "user",
        "content": message,
        "delegated_from": {"id": caller["id"],
                           "name": caller.get("name") or caller["id"]},
    }
    if task_id:
        body["task_id"] = task_id
    return body


def run_delegated_turn(store, caller: dict, target: dict, message: str,
                       *, chain: tuple, timeout_s: float | None = None,
                       task_id: str | None = None) -> dict:
    """Run the target's turn synchronously from the caller's worker thread."""
    timeout = delegation_timeout_s() if timeout_s is None else timeout_s
    lock = try_lock(target["id"])
    if lock is None:
        return {"ok": False, "error": "agent_busy",
                "assistant_text": "",
                "terminal_reason": "agent_busy",
                "permission_denials": 0}

    result_box: dict[str, dict] = {}

    def _work():
        try:
            result_box["result"] = execute_turn(
                store, target, message,
                chain=tuple(chain or ()),
                user_row=build_delegated_user_row(caller, message, task_id),
                extra_attachment=delegation_attachment(
                    caller.get("name") or caller["id"],
                    caller["id"], message),
                include_history=True)
        except Exception as exc:  # never strand the caller
            result_box["result"] = {"ok": False,
                                    "assistant_text": "",
                                    "terminal_reason": "internal_error",
                                    "permission_denials": 0,
                                    "error": str(exc)}
        finally:
            unlock(target["id"], lock)

    thread = threading.Thread(target=_work,
                              name=f"fleet-delegate-{target['id']}",
                              daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        # the target keeps running detached; its rows land when it finishes
        return {"ok": False,
                "error": f"delegation timed out after {int(timeout)}s",
                "assistant_text": "",
                "terminal_reason": "timeout",
                "permission_denials": 0}
    return result_box.get("result") or {"ok": False, "error": "unknown failure",
                                        "assistant_text": "",
                                        "terminal_reason": "internal_error",
                                        "permission_denials": 0}
