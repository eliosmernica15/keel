"""Webhook authentication, replay and channel-delivery security regressions.

Every secret in this module is a synthetic test value — no real credentials.
Tests exercise the real functions in keel.webhooks / keel.webhook_delivery /
keel.channel_ops; nothing is stubbed except the network edge where noted.
"""

from __future__ import annotations

import inspect
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from keel import channel_ops, webhook_delivery, webhooks
from keel.channel_ops import SubscriptionStore, deliver_with_fallback
from keel.webhook_delivery import WebhookDelivery

SECRET = "synthetic-webhook-secret-for-tests"
OTHER_SECRET = "synthetic-other-webhook-secret"
BODY = b'{"event":"invoice.paid","amount":100,"id":"evt_1"}'


# ---------------------------------------------------------------------------
# HMAC validation
# ---------------------------------------------------------------------------

def test_verify_uses_constant_time_comparison():
    """The signature comparison must use hmac.compare_digest, never ==."""
    source = inspect.getsource(webhooks.verify)
    assert "hmac.compare_digest" in source
    assert "signature ==" not in source and "== signature" not in source
    assert "signature !=" not in source and "!= signature" not in source


def test_forged_valid_signature_is_accepted():
    """A correctly forged HMAC over ts.body with a synthetic secret is valid."""
    ts, signature = webhooks.sign(BODY, SECRET, timestamp=1000)
    assert ts == 1000
    assert signature.startswith("sha256=")
    assert webhooks.verify(BODY, signature, SECRET, ts, now=1000) is True


def test_tampered_payload_and_wrong_secret_are_rejected():
    ts, signature = webhooks.sign(BODY, SECRET, timestamp=1000)
    assert webhooks.verify(BODY + b" ", signature, SECRET, ts, now=1000) is False
    assert webhooks.verify(BODY.replace(b"100", b"999"), signature, SECRET,
                           ts, now=1000) is False
    assert webhooks.verify(BODY, signature, OTHER_SECRET, ts, now=1000) is False


# ---------------------------------------------------------------------------
# Replay prevention (timestamp + nonce + bounded seen-cache)
# ---------------------------------------------------------------------------

def test_signed_message_cannot_be_replayed():
    cache = webhooks.NonceCache()
    ts, signature = webhooks.sign(BODY, SECRET, timestamp=1000,
                                  nonce="nonce-abc")
    assert webhooks.verify(BODY, signature, SECRET, ts, nonce="nonce-abc",
                           seen=cache, now=1000) is True
    # Exact same signed message replayed within the freshness window.
    assert webhooks.verify(BODY, signature, SECRET, ts, nonce="nonce-abc",
                           seen=cache, now=1000) is False


def test_nonce_is_bound_to_signature():
    cache = webhooks.NonceCache()
    ts, signature = webhooks.sign(BODY, SECRET, timestamp=1000,
                                  nonce="nonce-abc")
    assert webhooks.verify(BODY, signature, SECRET, ts, nonce="nonce-xyz",
                           seen=cache, now=1000) is False


def test_invalid_signature_does_not_consume_nonce():
    """An attacker must not be able to poison the seen-cache with bad sigs."""
    cache = webhooks.NonceCache()
    ts, signature = webhooks.sign(BODY, SECRET, timestamp=1000, nonce="n1")
    assert webhooks.verify(BODY, signature, OTHER_SECRET, ts, nonce="n1",
                           seen=cache, now=1000) is False
    assert webhooks.verify(BODY, signature, SECRET, ts, nonce="n1",
                           seen=cache, now=1000) is True


def test_nonce_cache_is_bounded():
    cache = webhooks.NonceCache(capacity=3)
    for i in range(10):
        assert cache.check_and_add(f"key-{i}") is True
        assert cache.check_and_add(f"key-{i}") is False
    assert len(cache) <= 3


def test_verifier_enforces_replay_and_persists_state(tmp_path):
    ts, signature = webhooks.sign(BODY, SECRET, timestamp=1000,
                                  nonce="stable-nonce")
    first = webhooks.WebhookVerifier(SECRET, state_root=str(tmp_path))
    assert first.verify(BODY, signature, ts, nonce="stable-nonce",
                        now=1000) is True
    assert first.verify(BODY, signature, ts, nonce="stable-nonce",
                        now=1000) is False
    # A fresh verifier over the same state must still remember the nonce.
    second = webhooks.WebhookVerifier(SECRET, state_root=str(tmp_path))
    assert second.verify(BODY, signature, ts, nonce="stable-nonce",
                         now=1000) is False


def test_verifier_fails_closed_without_nonce():
    ts, signature = webhooks.sign(BODY, SECRET, timestamp=1000)
    verifier = webhooks.WebhookVerifier(SECRET)
    assert verifier.verify(BODY, signature, ts, now=1000) is False


# ---------------------------------------------------------------------------
# Outgoing delivery: nonce header + stable retry identity
# ---------------------------------------------------------------------------

class _Capture(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        _Capture.received.append({
            "body": body,
            "sig": self.headers.get(webhooks.SIGNATURE_HEADER, ""),
            "ts": self.headers.get(webhooks.TIMESTAMP_HEADER, ""),
            "nonce": self.headers.get(webhooks.NONCE_HEADER, ""),
        })
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    _Capture.received = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Capture)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    import time
    time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/hook"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_deliver_sends_nonce_header_with_matching_signature(server):
    result = webhooks.deliver(server, {"event": "ping"}, SECRET,
                              allow_http=True, nonce="delivery-1")
    assert result["ok"] is True
    record = _Capture.received[0]
    assert record["nonce"] == "delivery-1"
    assert webhooks.verify(record["body"], record["sig"], SECRET,
                           record["ts"], nonce=record["nonce"]) is True


def test_retries_reuse_one_delivery_identity(monkeypatch, tmp_path):
    """A retried message must be byte-identical so a receiver can dedupe it."""
    calls: list[dict] = []

    def fake_deliver(url, payload, secret, *, allow_http=False,
                     nonce=None, timestamp=None):
        calls.append({"nonce": nonce, "timestamp": timestamp})
        if len(calls) < 3:
            raise OSError("synthetic network hiccup")
        return {"ok": True, "status": 200}

    monkeypatch.setattr(webhook_delivery, "deliver", fake_deliver)
    result = WebhookDelivery(tmp_path).send(
        "https://example.test/hook", {"event": "x"}, SECRET, attempts=4)

    assert result["ok"] is True and result["attempts"] == 3
    assert result["delivery_id"]
    assert len(calls) == 3
    assert len({c["nonce"] for c in calls}) == 1
    assert len({c["timestamp"] for c in calls}) == 1
    assert calls[0]["nonce"] == result["delivery_id"]


# ---------------------------------------------------------------------------
# Channel / outbox durability
# ---------------------------------------------------------------------------

def test_parallel_outbox_writes_produce_valid_jsonl(tmp_path):
    count = 40

    def writer(i):
        channel_ops.deliver_to_outbox(tmp_path, "outbox", f"message-{i}")

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    lines = channel_ops.outbox_path(tmp_path).read_text(
        encoding="utf-8").splitlines()
    assert len(lines) == count
    records = [json.loads(line) for line in lines]
    assert {r["message"] for r in records} == {f"message-{i}" for i in range(count)}


def test_outbox_write_is_locked_and_durable():
    source = inspect.getsource(channel_ops.deliver_to_outbox)
    assert "os.open" in source or "_append_jsonl" in source
    assert "O_APPEND" in inspect.getsource(channel_ops)
    assert "fsync" in inspect.getsource(channel_ops)
    assert "_OUTBOX_LOCK" in inspect.getsource(channel_ops)


def test_subscription_save_uses_atomic_replace():
    assert "os.replace" in inspect.getsource(SubscriptionStore._save)


def test_subscription_save_leaves_no_temp_file(tmp_path):
    store = SubscriptionStore(tmp_path)
    store.register("builds", "https://x.test/hook", ["build"])
    store.rotate("builds")
    assert not list(tmp_path.glob("*.tmp"))


def test_fallback_max_attempts_zero_means_no_calls():
    called: list[str] = []

    def send(channel):
        called.append(channel)
        return True

    deliver_with_fallback(["a", "b"], send, max_attempts=0)
    assert called == []
