"""A3.1 — real webhook retry/backoff and delivery log."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from keel.webhook_delivery import WebhookDelivery


class Flaky(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        Flaky.calls += 1
        self.send_response(500 if Flaky.calls < 3 else 200)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_retry_until_success(tmp_path):
    Flaky.calls = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), Flaky)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import time
        time.sleep(0.1)
        url = f"http://127.0.0.1:{server.server_address[1]}/hook"
        result = WebhookDelivery(tmp_path).send(
            url, {"event": "x"}, "secret", attempts=4, allow_http=True)
        assert result["ok"] is True and result["attempts"] == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_delivery_log_has_no_payload(tmp_path):
    delivery = WebhookDelivery(tmp_path)
    delivery.send("https://invalid.test/hook", {"secret": "do-not-log"},
                  "s", attempts=1)
    text = (tmp_path / "webhook-delivery.jsonl").read_text()
    assert "do-not-log" not in text
    assert delivery.history()[0]["ok"] is False
