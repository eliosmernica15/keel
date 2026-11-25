"""FIXTURE upstream for deterministic / error-path checks only.

This is NOT the real bridge. It echoes the headers the Next BFF actually sent
upstream (to prove token injection and cookie/origin stripping) and returns
fixed statuses for error-envelope tests. Every test that uses it is labelled
FIXTURE in its title. Genuine round-trips use bridge_server.py instead.
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, status=200):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        path = self.path.split("?", 1)[0]
        if path == "/__bridge_ready":
            self._send({"ok": True, "source": "fixture-mock-bridge"})
            return
        if path == "/api/fleet/echo":
            self._send({
                "path": self.path,
                "method": self.command,
                "headers": {k.lower(): v for k, v in self.headers.items()},
            })
            return
        if path == "/api/fleet/fixture/502":
            self._send({"error": "fixture_gateway", "detail": "deterministic 502"}, 502)
            return
        if path == "/api/fleet/fixture/400":
            self._send({"error": "fixture_bad_request", "detail": "deterministic 400"}, 400)
            return
        if path == "/api/fleet/fixture/text":
            body = b"plain-text-error-from-upstream"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # A deliberately unmatched upstream route: the BFF forwards the status.
        self._send({"error": "not_found", "path": path}, 404)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle

    def log_message(self, *_args):
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"fixture mock bridge ready on 127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
