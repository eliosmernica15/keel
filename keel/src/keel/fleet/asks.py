"""keel.fleet.asks — operator questions from agents.

Claude Code-style mid-turn questions ("Which framework?") pause the agent
and surface a pop-up in the UI with clickable options (or free text). The
operator answers; the answer becomes the tool result. Timeout = fail closed
(the model sees a refusal and must proceed without operator input).

Design rules:
- questions are per-(bot, ask_id); nobody else can see or answer them
- 5 minute timeout, same semantics as approvals — an unattended question
  fails closed, it does NOT block the fleet forever
- everything is audited (fingerprints only, never full text)
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional


class AskBroker:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending: dict[str, dict] = {}

    # --------------------------------------------------------------- ask
    def ask(self, store, bot: dict, question: str, options: list[str]) -> str:
        import uuid
        ask_id = "ask_" + uuid.uuid4().hex[:12]
        with self._lock:
            self._pending[ask_id] = {
                "event": threading.Event(),
                "answer": None,
                "bot_id": bot["id"],
                "asked_at": time.time(),
            }
        try:
            store.append_row(bot["id"], "ask", {
                "ask_id": ask_id,
                "question": question,
                "options": options or [],
                "status": "pending",
                "icon": "question",
            })
        except Exception:
            # the UI shows the card; if the row write fails the question is
            # unroutable — fail here rather than hang
            with self._lock:
                self._pending.pop(ask_id, None)
            raise
        return ask_id

    # ------------------------------------------------------------ answer
    def get_pending(self, bot_id: str) -> list[dict]:
        with self._lock:
            return [
                {"ask_id": ask_id, "bot_id": p["bot_id"],
                 "asked_at": p["asked_at"]}
                for ask_id, p in self._pending.items()
                if p["bot_id"] == bot_id
            ]

    def answer(self, bot_id: str, ask_id: str, answer: str) -> bool:
        with self._lock:
            pending = self._pending.get(ask_id)
            if pending is None or pending["bot_id"] != bot_id:
                return False
            pending["answer"] = answer
            # The waiting caller consumes (pops) the entry in wait(); popping
            # here would race with a waiter that has not looked it up yet.
            pending["event"].set()
        return True

    def wait(self, ask_id: str, timeout_s: float = 300.0) -> Optional[str]:
        with self._lock:
            pending = self._pending.get(ask_id)
        if pending is None:
            return None
        if not pending["event"].wait(timeout_s):
            # A timed-out ask is unroutable; release it as well.
            with self._lock:
                self._pending.pop(ask_id, None)
            return None
        answer = pending["answer"]
        with self._lock:
            self._pending.pop(ask_id, None)
        return answer

    # ------------------------------------------------------------ sweep
    def expire_sweep(self, store, *, timeout_s: float = 300.0) -> int:
        """Call on restart: pending asks from a dead process can't be answered."""
        expired = 0
        with self._lock:
            ask_ids = list(self._pending.keys())
        for ask_id in ask_ids:
            try:
                with self._lock:
                    pending = self._pending.get(ask_id)
                    if pending is None:
                        continue
                    bot_id = pending["bot_id"]
                pending_event = pending["event"]
                if pending_event.wait(0.001):
                    with self._lock:
                        self._pending.pop(ask_id, None)
                    continue
                store.append_row(bot_id, "notice", {
                    "text": ("A pending question was interrupted by the "
                             "server restarting; the agent got no answer. "
                             "Ask it to redo or continue."),
                    "level": "warning",
                    "icon": "question",
                })
                with self._lock:
                    self._pending.pop(ask_id, None)
                expired += 1
            except Exception:
                pass
        return expired

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)


broker = AskBroker()
