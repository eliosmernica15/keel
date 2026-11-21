"""Gateway process wrapper with status/start/stop (A5.1).

The gateway runs the Fleet routine scheduler in a managed background thread
inside the Python daemon. No extra process, account or service is required.
"""

from __future__ import annotations

import threading
import time
from typing import Callable


class Gateway:
    def __init__(self, *, work: Callable[[], None] | None = None,
                 interval: float = 20.0):
        self._work = work
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.started_at: float | None = None
        self.ticks = 0

    def status(self) -> dict:
        running = self._thread is not None and self._thread.is_alive()
        return {
            "running": running,
            "ticks": self.ticks,
            "started_at": self.started_at,
            "uptime_s": (round(time.time() - self.started_at, 2)
                         if self.started_at else 0),
        }

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop.clear()
            self.started_at = time.time()

            def _loop():
                while not self._stop.wait(self._interval):
                    try:
                        if self._work is not None:
                            self._work()
                        self.ticks += 1
                    except Exception:
                        pass  # one failed tick must not kill the gateway

            self._thread = threading.Thread(
                target=_loop, name="keel-gateway", daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout: float = 5.0) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                return False
            self._stop.set()
        thread.join(timeout=timeout)
        return not thread.is_alive()


_gateway: Gateway | None = None


def gateway() -> Gateway:
    global _gateway
    if _gateway is None:
        from .fleet.scheduler import tick

        _gateway = Gateway(work=tick)
    return _gateway
