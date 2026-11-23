"""Signed outgoing webhooks (A4.1).

HMAC-SHA256 over ``timestamp + "." + body``. When a nonce is supplied the
signed message is ``timestamp + "." + len(nonce) + ":" + nonce + "." + body``
(the length prefix makes the nonce unambiguous). A timestamp header lets a
receiver reject stale messages; a nonce header plus the bounded seen-cache in
:class:`NonceCache` lets it reject replays. Delivery is explicit and opt-in:
nothing is sent unless a caller supplies a URL and a secret (preferably via
environment).
"""

from __future__ import annotations

import collections
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_MAX_AGE = 300
DEFAULT_SEEN_CAPACITY = 4096
SIGNATURE_HEADER = "X-Keel-Signature"
TIMESTAMP_HEADER = "X-Keel-Timestamp"
NONCE_HEADER = "X-Keel-Nonce"


class WebhookError(RuntimeError):
    pass


def _signed_message(ts: int, body: bytes, nonce: str | None) -> bytes:
    prefix = str(ts).encode("ascii") + b"."
    if nonce is None:
        # Legacy wire format — kept byte-for-byte compatible.
        return prefix + body
    nonce_bytes = nonce.encode("utf-8")
    return (prefix + str(len(nonce_bytes)).encode("ascii") + b":" +
            nonce_bytes + b"." + body)


def sign(body: bytes, secret: str, timestamp: int | None = None,
         *, nonce: str | None = None) -> tuple[int, str]:
    """Return the timestamp and ``sha256=...`` signature for ``body``.

    ``nonce`` is optional; when present it is bound into the HMAC so it cannot
    be altered in transit without invalidating the signature.
    """
    ts = int(timestamp if timestamp is not None else time.time())
    message = _signed_message(ts, body, nonce)
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return ts, f"sha256={digest}"


def _replay_key(ts: int, nonce: str, body: bytes) -> str:
    material = str(ts).encode("ascii") + b"." + nonce.encode("utf-8") + b"." + body
    return hashlib.sha256(material).hexdigest()


class NonceCache:
    """Bounded, thread-safe seen-nonce cache with optional file persistence.

    Keys live in an insertion-ordered mapping trimmed to ``capacity`` entries.
    When ``state_root`` is supplied the keys are persisted atomically to
    ``webhook-seen-nonces.json`` so replays are still rejected after a restart.
    Persistence is best-effort: the in-memory cache still holds for the life of
    the process if the state directory is unavailable.
    """

    def __init__(self, state_root: str | Path | None = None,
                 *, capacity: int = DEFAULT_SEEN_CAPACITY):
        self.capacity = max(1, int(capacity))
        self._lock = threading.Lock()
        self._seen: collections.OrderedDict[str, None] = collections.OrderedDict()
        self._path = (Path(state_root) / "webhook-seen-nonces.json"
                      if state_root is not None else None)
        if self._path is not None and self._path.is_file():
            try:
                loaded = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    for key in loaded:
                        if isinstance(key, str):
                            self._seen[key] = None
            except (OSError, ValueError):
                pass
            self._trim()

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._seen

    def _trim(self) -> None:
        while len(self._seen) > self.capacity:
            self._seen.popitem(last=False)

    def _persist(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_name(self._path.name + ".tmp")
            tmp.write_text(json.dumps(list(self._seen)), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError:
            pass

    def check_and_add(self, key: str) -> bool:
        """Record ``key``; return True if new, False if it was already seen."""
        with self._lock:
            if key in self._seen:
                return False
            self._seen[key] = None
            self._trim()
            self._persist()
            return True


def verify(body: bytes, signature: str, secret: str, timestamp: str | int,
           *, max_age: int = DEFAULT_MAX_AGE, now: int | None = None,
           nonce: str | None = None, seen: NonceCache | None = None) -> bool:
    """Validate an incoming webhook.

    The signature is always checked in constant time (``hmac.compare_digest``)
    before any replay state is touched, so a forged request cannot poison the
    seen-cache. Pass both ``nonce`` and ``seen`` to enable replay defense; the
    signature is checked first and only then is the nonce recorded.
    """
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int(now if now is not None else time.time())
    if abs(current - ts) > max_age:
        return False
    _, expected = sign(body, secret, ts, nonce=nonce)
    if not hmac.compare_digest(expected, signature):
        return False
    if seen is not None:
        if not nonce:
            return False  # replay defense requested but nothing to dedupe on
        return seen.check_and_add(_replay_key(ts, nonce, body))
    return True


class WebhookVerifier:
    """Receiver helper that always enforces authenticity and replay safety."""

    def __init__(self, secret: str, *, max_age: int = DEFAULT_MAX_AGE,
                 state_root: str | Path | None = None,
                 capacity: int = DEFAULT_SEEN_CAPACITY):
        self.secret = secret
        self.max_age = max_age
        self.seen = NonceCache(state_root, capacity=capacity)

    def verify(self, body: bytes, signature: str, timestamp: str | int,
               nonce: str | None = None, *, now: int | None = None) -> bool:
        if not nonce:
            # Without a nonce a message can be replayed freely in the window.
            return False
        return verify(body, signature, self.secret, timestamp,
                      max_age=self.max_age, now=now, nonce=nonce,
                      seen=self.seen)


def deliver(url: str, payload: dict, secret: str, *, allow_http: bool = False,
            timeout: int = 15, nonce: str | None = None,
            timestamp: int | None = None) -> dict:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise WebhookError("webhook url must be http or https")
    if parsed.scheme == "http" and not allow_http:
        raise WebhookError("http webhooks require allow_http=True")
    body = json.dumps(payload, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    ts, signature = sign(body, secret, timestamp=timestamp, nonce=nonce)
    headers = {"Content-Type": "application/json",
               "User-Agent": "Keel-Webhook/1.0",
               SIGNATURE_HEADER: signature,
               TIMESTAMP_HEADER: str(ts)}
    if nonce is not None:
        headers[NONCE_HEADER] = nonce
    request = urllib.request.Request(
        url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"ok": True, "status": response.status,
                    "body": response.read(4096).decode("utf-8", errors="replace")}
    except OSError as exc:
        raise WebhookError(f"webhook delivery failed: {exc}") from exc
