"""Real signed webhook delivery with retry/backoff and a local delivery log (A3.1).

Extends the basic webhook sender with bounded exponential retries, HMAC signing
reuse, and a durable JSONL log of every attempt (no payload bodies are logged).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .webhooks import deliver, sign


class WebhookDelivery:
    def __init__(self, state_root: str | Path):
        self.log_path = Path(state_root) / "webhook-delivery.jsonl"

    def _log(self, entry: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def send(self, url: str, payload: dict, secret: str, *, attempts: int = 3,
             base_delay: float = 0.05, allow_http: bool = False) -> dict:
        attempts = max(1, min(10, int(attempts)))
        last_error = ""
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                time.sleep(base_delay * (2 ** (attempt - 2)))
            try:
                result = deliver(url, payload, secret, allow_http=allow_http)
                self._log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime()),
                           "url": url, "attempt": attempt,
                           "status": result.get("status"),
                           "ok": True, "size": len(json.dumps(payload))})
                return {"ok": True, "attempts": attempt,
                        "status": result.get("status")}
            except Exception as exc:
                last_error = str(exc)[:300]
                self._log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime()),
                           "url": url, "attempt": attempt,
                           "ok": False, "error": last_error})
        return {"ok": False, "attempts": attempts, "error": last_error}

    def history(self) -> list[dict]:
        if not self.log_path.is_file():
            return []
        return [json.loads(line) for line in
                self.log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
