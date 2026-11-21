"""A4.1 — signed outgoing webhooks."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from keel import webhooks
from keel.cli.main import main

SECRET = "test-webhook-secret"


class _Capture(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        signature = self.headers.get(webhooks.SIGNATURE_HEADER, "")
        timestamp = self.headers.get(webhooks.TIMESTAMP_HEADER, "")
        self.received.append({
            "body": body,
            "valid": webhooks.verify(body, signature, SECRET, timestamp),
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
    time.sleep(0.1)
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/hook"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_sign_and_verify_roundtrip():
    body = b'{"event":"test"}'
    ts, signature = webhooks.sign(body, SECRET, timestamp=1000)
    assert ts == 1000
    assert webhooks.verify(body, signature, SECRET, ts, now=1000)
    assert not webhooks.verify(body + b"x", signature, SECRET, ts, now=1000)
    assert not webhooks.verify(body, signature, "wrong-secret", ts, now=1000)


def test_stale_timestamp_is_rejected():
    body = b"{}"
    _, signature = webhooks.sign(body, SECRET, timestamp=1000)
    assert not webhooks.verify(body, signature, SECRET, 1000, now=1000 + 400)


def test_delivery_is_signed(server):
    result = webhooks.deliver(server, {"event": "ping"}, SECRET,
                              allow_http=True)
    assert result["ok"] and result["status"] == 200
    assert len(_Capture.received) == 1
    assert _Capture.received[0]["valid"] is True
    assert json.loads(_Capture.received[0]["body"]) == {"event": "ping"}


def test_http_requires_opt_in(server):
    with pytest.raises(webhooks.WebhookError, match="allow_http"):
        webhooks.deliver(server, {}, SECRET)


def test_cli_webhook_send(server, monkeypatch, capsys):
    monkeypatch.setenv("KEEL_WEBHOOK_SECRET", SECRET)
    assert main(["webhook", "send", server, "--payload", '{"event":"cli"}',
                 "--allow-http"]) == 0
    assert "ok" in capsys.readouterr().out
    assert _Capture.received[0]["valid"] is True
