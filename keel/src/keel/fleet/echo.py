"""keel.fleet.echo — the scripted test bot (F0).

IMPORTANT: this is a *scripted test harness*, not a model. It lets you verify
roster, persistence, rows, SSE and UI plumbing before wiring a real provider.
Every reply is tagged with `engine: "echo"`; the UI labels it "Scripted test".
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import Callable

_log = logging.getLogger(__name__)

# per-bot lock so two turns never overlap on the same agent
_locks: dict[str, threading.Lock] = {}
_global_lock = threading.Lock()


def try_lock(bot_id: str) -> threading.Lock | None:
    with _global_lock:
        lock = _locks.setdefault(bot_id, threading.Lock())
        if lock.locked():
            return None
        lock.acquire()
        return lock


def unlock(bot_id: str, lock: threading.Lock | None) -> None:
    with _global_lock:
        if lock:
            lock.release()
        # keep lock entry cached, that's fine


def _delay(seconds: float) -> None:
    time.sleep(seconds)


def echo_reply(content: str) -> str:
    raw = content.strip()
    length = len(raw)
    reversed_raw = raw[::-1]
    reversed_display = reversed_raw[:120]
    if len(reversed_raw) > 120:
        reversed_display += "…"

    reply_lines = [
        f"Echo heard you say: “{raw[:200]}”",
        f"Reversed: “{reversed_display}”",
        f"({length} characters)",
        "",
        "This is the scripted Echo test bot. Create a provider agent for a real model.",
    ]
    return "\n".join(reply_lines)


def run_echo_turn(store, bot: dict, content: str, *, delay: float = 0.35) -> None:
    """Write step rows then the assistant reply + turn_end. Caller already
    appended the user row and holds the per-bot lock."""
    bot_id = bot["id"]
    t0 = time.monotonic()
    steps = [
        ("analyze-request", "parsed the message and picked a shape for the reply"),
        ("consider-options", "considered whether reversing or quoting reads better"),
        ("compose-reply", "assembled the scripted response"),
    ]
    for name, detail in steps:
        store.append_row(bot_id, "step", {
            "name": name,
            "status": "running",
            "detail": detail,
        })
        _delay(delay)
        store.append_row(bot_id, "step", {
            "name": name,
            "status": "done",
            "detail": detail,
        })

    store.append_row(bot_id, "message", {
        "role": "assistant",
        "content": echo_reply(content),
        "engine": "echo",
    })
    took_ms = int((time.monotonic() - t0) * 1000)
    store.append_row(bot_id, "turn_end", {
        "duration_ms": took_ms,
        "num_steps": len(steps),
    })


def start_turn(store, bot: dict, content: str) -> tuple[threading.Lock | None, bool]:
    """Returns (lock, started). Caller uses `started` for UI feedback."""
    lock = try_lock(bot["id"])
    if lock is None:
        return None, False
    t = threading.Thread(
        target=_run_with_unlock, args=(store, bot, content, lock),
        name=f"fleet-echo-{bot['id']}", daemon=True)
    t.start()
    return lock, True


def _run_with_unlock(store, bot, content, lock):
    try:
        run_echo_turn(store, bot, content)
    except sqlite3.ProgrammingError:
        # the store was closed while this scripted turn was in flight
        # (test shutdown); nothing left to write to
        _log.debug("echo turn aborted: store is closed")
    except Exception:
        _log.exception("echo turn failed")
    finally:
        unlock(bot["id"], lock)
