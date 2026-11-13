"""keel.webapp — local web app + PWA bridge for the desktop UI.

Serves the static UI at 127.0.0.1:<port> and exposes a minimal JSON API:

    GET  /                      -> the app (needs ?t=<token>)
    GET  /api/health            -> {"ok": true, "version": "..."}
    GET  /api/providers         -> the provider registry status table
    POST /api/run               -> stream-json NDJSON from a real `keel` run
    GET  /ui/<file>             -> static assets (app shell)

Security model (honest, machine-local):
- binds 127.0.0.1 only, never an external interface;
- a fresh random token is generated per launch and printed in the URL —
  without it, /api/* returns 403; the token is the only credential;
- non-GET requests whose Origin header is present must match the server
  origin (curl/watchers with no Origin header are allowed, like any CLI);
- no state is written outside ~/.keel (transcripts are keel's own files).

/api/run passes the user's prompt to `keel -p ... --output-format stream-json`
and streams its stdout lines to the browser, newline-delimited.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from . import __version__
from .fleet import routes as _fleet_routes
from .providers import registry as provider_registry

UI_DIR = Path(__file__).resolve().parents[2] / "desktop" / "ui"
PWA_DIR = Path(__file__).resolve().parents[2] / "desktop"

DEFAULT_PORT = 8739
_STATIC_CSP = ("default-src 'none'; script-src 'self'; "
               "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
               "connect-src 'self'; font-src 'self' data:; "
               "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
_TOKEN = secrets.token_urlsafe(24)
_LOCK = threading.Lock()
_CURRENT_RUN: dict = {}


def token() -> str:
    return _TOKEN


def make_server(port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Create (but do not start) the bridge server. Port 0 = ephemeral."""
    class Handler(BaseHTTPRequestHandler):
        server_version = f"keel-webapp/{__version__}"

        # ---------------- helpers
        def _send_json(self, obj, status=HTTPStatus.OK, extra_headers=()):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in extra_headers:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is None:
                return True  # curl / non-browser clients
            host = self.headers.get("Host", "")
            expected = f"http://{host}"
            return origin.rstrip("/") == expected.rstrip("/")

        def _authorized(self) -> bool:
            provided = self.headers.get("X-Keel-Token") or self.path_token()
            if not provided:
                cookies = self.headers.get("Cookie", "")
                for part in cookies.split(";"):
                    part = part.strip()
                    if part.startswith("keel_token="):
                        provided = part[len("keel_token="):]
                        break
            return bool(provided) and secrets.compare_digest(provided, _TOKEN)

        def path_token(self) -> Optional[str]:
            if "?t=" in self.path:
                return self.path.split("?t=", 1)[1].split("&", 1)[0]
            if "&t=" in self.path:
                return self.path.split("&t=", 1)[1].split("&", 1)[0]
            return None

        def _refuse(self):
            self._send_json({"error": "refused", "reason": "bad token or origin"},
                            HTTPStatus.FORBIDDEN)

        # ---------------- static UI
        def do_GET(self):
            if _fleet_routes.dispatch_get(self,
                                          _authorized=self._authorized,
                                          _origin_ok=self._origin_ok,
                                          _token=_TOKEN):
                return
            path = self.path.split("?", 1)[0]
            if path in ("/", ""):
                if not self._authorized():
                    self._refuse()
                    return
                self._serve_file(UI_DIR / "index.html",
                                 extra_headers=(("Set-Cookie",
                                                 f"keel_token={_TOKEN}; HttpOnly; "
                                                 f"SameSite=Strict; Path=/"),))
                return
            if path.startswith("/ui/"):
                name = path[len("/ui/"):]
                candidate = (UI_DIR / name).resolve()
                if candidate.is_file() and candidate.is_relative_to(UI_DIR.resolve()):
                    self._serve_file(candidate)
                    return
                self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            if path == "/manifest.webmanifest":
                self._serve_file(PWA_DIR / "manifest.webmanifest",
                                 content_type="application/manifest+json")
                return
            if path == "/sw.js":
                self._serve_file(PWA_DIR / "sw.js",
                                 content_type="application/javascript")
                return
            if path == "/api/health":
                if not self._authorized():
                    self._refuse()
                    return
                self._send_json({"ok": True, "version": __version__})
                return
            if path == "/api/providers":
                if not self._authorized():
                    self._refuse()
                    return
                self._send_json({"providers": provider_registry.list_providers()})
                return
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self):
            if _fleet_routes.dispatch_post(self,
                                           _authorized=self._authorized,
                                           _origin_ok=self._origin_ok):
                return
            if not self._origin_ok() or not self._authorized():
                self._refuse()
                return
            path = self.path.split("?", 1)[0]
            if path != "/api/run":
                self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > 128_000:
                self._send_json({"error": "prompt too large"},
                                HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            raw = self.rfile.read(length) if length else b"{}"
            try:
                request = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._send_json({"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
                return
            prompt = str(request.get("prompt", "")).strip()
            if not prompt:
                self._send_json({"error": "prompt must not be empty"},
                                HTTPStatus.BAD_REQUEST)
                return
            provider = str(request.get("provider", "auto"))
            permission_mode = str(request.get("permission_mode", "default"))
            accept_risk = bool(request.get("accept_risk", False))
            self._stream_run(prompt, provider, permission_mode, accept_risk)

        # ---------------- internals
        def _serve_file(self, path: Path, content_type: Optional[str] = None,
                        extra_headers=()):
            if not path.is_file():
                self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            if content_type is None:
                suffix = path.suffix.lower()
                content_type = {
                    ".html": "text/html; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".png": "image/png",
                    ".ico": "image/x-icon",
                    ".svg": "image/svg+xml",
                    ".webmanifest": "application/manifest+json",
                }.get(suffix, "application/octet-stream")
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Security-Policy",
                             _STATIC_CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for key, value in extra_headers:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _stream_run(self, prompt: str, provider: str,
                        permission_mode: str, accept_risk: bool):
            args = [sys.executable, "-m", "keel",
                    "-p", prompt,
                    "--output-format", "stream-json",
                    "--provider", provider,
                    "--permission-mode", permission_mode,
                    "--seed", "0"]
            if permission_mode == "bypassPermissions":
                if not accept_risk:
                    self._send_json(
                        {"error": "bypassPermissions requires accept_risk"},
                        HTTPStatus.FORBIDDEN)
                    return
                args.append("--i-accept-the-risk")
            fake_script = os.environ.get("KEEL_FAKE_SCRIPT")
            if fake_script:
                args += ["--fake-script", fake_script]

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace")
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
                proc.wait()
                self.wfile.write(b'{"type":"bridge","subtype":"done","exit_code":%d}\n'
                                 % proc.returncode)
            except (BrokenPipeError, ConnectionResetError,
                    ConnectionAbortedError, ValueError, OSError):
                pass
            except Exception as exc:  # reported, never fatal
                try:
                    self.wfile.write(json.dumps(
                        {"type": "bridge", "subtype": "error",
                         "error": str(exc)}).encode("utf-8") + b"\n")
                except Exception:
                    pass

        def log_message(self, format, *args):  # keep stderr quiet; keel owns logs
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port: int = DEFAULT_PORT, *, start: bool = True) -> None:
    server = make_server(port)
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={_TOKEN}"
    fleet_url = f"http://127.0.0.1:{server.server_address[1]}/fleet?t={_TOKEN}"
    sys.stderr.write(f"keel webapp running at {url}\n")
    sys.stderr.write(f"Keel Fleet at {fleet_url}\n")
    sys.stderr.write("Ctrl+C to stop\n")
    try:
        if start:
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
