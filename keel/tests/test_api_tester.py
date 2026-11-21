"""B2.10 — real HTTP API tester with saved collections."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from keel.api_tester import APIError, APICollection, run_request


class Echo(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def test_saved_collection_and_real_request(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import time
        time.sleep(0.1)
        url = f"http://127.0.0.1:{server.server_address[1]}/ping"
        collection = APICollection(tmp_path)
        collection.save_request("ping", "GET", url)
        assert collection.list()[0]["name"] == "ping"
        result = run_request("ping", collection)
        assert result["ok"] and result["status"] == 200 and result["body"] == "ok"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_host_restriction_and_unknown(tmp_path):
    collection = APICollection(tmp_path)
    with pytest.raises(APIError, match="unknown"):
        run_request("missing", collection)
    collection.save_request("evil", "GET", "https://example.com/x")
    with pytest.raises(APIError, match="not allowed"):
        run_request("evil", collection)
