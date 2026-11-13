"""keel.fleet.provider_turn — provider-backed Fleet turns (F-provider milestone).

Mirrors echo.py's contract: called with the per-bot lock already held and the
user row already appended. A provider turn may write:

  message|assistant   — the agent's text (kind=message, role=assistant)
  step                — one per tool call / result, with name+status;
                        send_to_bot steps carry a `delegated` payload
                        (target + full reply, capped) for the UI chip
  notice              — provider/policy messages
  approval            — F1 approval card (pending → approved/denied/expired)
  turn_end            — always at completion

Consequential tools are gated by Keel Tier-1 + the Fleet approval broker:
the operator may allow once / always / never from the approval card (or a
standing per-agent policy applies). Tier-2 safety, hooks and deny rules are
never overrideable from Fleet.

The synchronous execution lives in `turn_core.execute_turn` and is shared
with the F3 delegation and group runners.
"""

from __future__ import annotations

import logging
import os
import threading

from .echo import try_lock, unlock
from .turn_core import execute_turn

_log = logging.getLogger(__name__)

_MAX_CONTINUATIONS = max(0, int(os.environ.get("KEEL_FLEET_CONTINUE_LIMIT", "2") or "2"))
_CONTINUE_PROMPT = ("Continue the task until it is fully complete. Do not "
                    "restart, do not summarize what you did — do the "
                    "remaining work.")


def start_provider_turn(store, bot: dict, content: str, *,
                        permission_mode: str | None = None):
    bot_id = bot["id"]
    lock = try_lock(bot_id)
    if lock is None:
        return lock, False

    def _run():
        try:
            result = execute_turn(store, bot, content, chain=(),
                                  user_row=None,  # routes already appended the user row
                                  include_history=True,
                                  executor=None,
                                  permission_mode=permission_mode)
            # provider hit the round cap but wasn't erroring — let it keep
            # working instead of leaving the operator to type "go on".
            # Bounded: billing and infinite loops stay impossible.
            continuation = 0
            while result.get("terminal_reason") == "max_turns" and \
                    continuation < _MAX_CONTINUATIONS:
                continuation += 1
                try:
                    store.append_row(bot_id, "notice", {
                        "text": (f"↻ Turn cap hit — continuing autonomously "
                                 f"({continuation}/{_MAX_CONTINUATIONS})"),
                        "level": "info",
                        "icon": "routine",
                    })
                except Exception:
                    pass
                result = execute_turn(store, bot, _CONTINUE_PROMPT,
                                      chain=(), user_row=None,
                                      include_history=True,
                                      executor=None,
                                      exclude_last_from_history=False,
                                      permission_mode=permission_mode)
        except Exception as exc:  # never strand the UI
            _log.exception("provider turn failed")
            try:
                store.append_row(bot_id, "notice", {
                    "text": f"Provider turn failed: {exc}",
                    "level": "error",
                })
                store.append_row(bot_id, "turn_end",
                                 {"duration_ms": 0, "num_turns": 0,
                                  "terminal_reason": "internal_error"})
            except Exception:
                pass
        finally:
            unlock(bot_id, lock)

    thread = threading.Thread(target=_run, name=f"fleet-provider-{bot_id}",
                              daemon=True)
    thread.start()
    return lock, True
