"""Signed outgoing webhooks (A4.1).

HMAC-SHA256 over ``timestamp + "." + body``, with a timestamp header so a
receiver can reject replays. Delivery is explicit and opt-in: nothing is sent
unless a caller supplies a URL and a secret (preferably via environment).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request

DEFAULT_MAX_AGE = 300
SIGNATURE_HEADER = "X-Keel-Signature"
TIMESTAMP_HEADER = "X-Keel-Timestamp"


class WebhookError(RuntimeError):
    pass


def sign(body: bytes, secret: str, timestamp: int | None = None) -> tuple[int, str]:
    ts = int(timestamp if timestamp is not None else time.time())
    message = str(ts).encode("ascii") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return ts, f"sha256={digest}"


def verify(body: bytes, signature: str, secret: str, timestamp: str | int,
           *, max_age: int = DEFAULT_MAX_AGE, now: int | None = None) -> bool:
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int(now if now is not None else time.time())
    if abs(current - ts) > max_age:
        return False
    _, expected = sign(body, secret, ts)
    return hmac.compare_digest(expected, signature)


def deliver(url: str, payload: dict, secret: str, *, allow_http: bool = False,
            timeout: int = 15) -> dict:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise WebhookError("webhook url must be http or https")
    if parsed.scheme == "http" and not allow_http:
        raise WebhookError("http webhooks require allow_http=True")
    body = json.dumps(payload, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    ts, signature = sign(body, secret)
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "Keel-Webhook/1.0",
                 SIGNATURE_HEADER: signature,
                 TIMESTAMP_HEADER: str(ts)})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"ok": True, "status": response.status,
                    "body": response.read(4096).decode("utf-8", errors="replace")}
    except OSError as exc:
        raise WebhookError(f"webhook delivery failed: {exc}") from exc
