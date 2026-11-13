"""keel.fleet.runtime — per-thread execution markers.

The routine executor marks the current routine run on its worker thread;
the F1 approval broker reads the marker so a blocked run flips to
`awaiting_approval` in place, live.
"""

from __future__ import annotations

import threading

_local = threading.local()


def mark_routine_run(run_id: int, bot_id: str) -> None:
    _local.run = (run_id, bot_id)


def current_routine_run():
    return getattr(_local, "run", None)


def clear_routine_run() -> None:
    _local.run = None
