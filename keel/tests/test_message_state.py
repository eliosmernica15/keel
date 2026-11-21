"""A5.5 — outbound message state machine."""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from keel.cli.main import main
from keel.message_state import (MessageStateError, MessageStates, transition)


def test_transition_rules():
    assert transition("queued", "sent") == "sent"
    assert transition("sent", "delivered") == "delivered"
    assert transition("delivered", "read") == "read"
    assert transition("failed", "queued") == "queued"
    with pytest.raises(MessageStateError, match="illegal"):
        transition("queued", "read")
    with pytest.raises(MessageStateError, match="unknown"):
        transition("bogus", "sent")


def test_lifecycle_and_history(tmp_path):
    states = MessageStates(str(tmp_path))
    record = states.queue(channel="webhook", destination="https://x.test/hook",
                          size=42)
    assert states.state(record["id"]) == "queued"
    states.advance(record["id"], "sent")
    states.advance(record["id"], "delivered")
    states.advance(record["id"], "read")
    assert states.state(record["id"]) == "read"
    assert [entry["state"] for entry in states.history(record["id"])] == [
        "queued", "sent", "delivered", "read"]


def test_failed_can_be_retried(tmp_path):
    states = MessageStates(str(tmp_path))
    record = states.queue(channel="webhook")
    states.advance(record["id"], "failed")
    with pytest.raises(MessageStateError):
        states.advance(record["id"], "delivered")
    states.advance(record["id"], "queued")
    assert states.state(record["id"]) == "queued"


class _Ok(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_webhook_send_records_sent_state(tmp_path, monkeypatch):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Ok)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    monkeypatch.setenv("KEEL_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("KEEL_STATE_DIR", str(tmp_path))
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/hook"
        assert main(["webhook", "send", url, "--payload", '{"a":1}',
                     "--allow-http"]) == 0
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    records = MessageStates(str(tmp_path))._records()
    assert records[-1]["state"] == "sent"
