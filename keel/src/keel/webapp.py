"""keel.webapp — local web app + PWA bridge for the desktop UI.

Serves the static UI at 127.0.0.1:<port> and exposes a minimal JSON API:

    GET  /                      -> the app (needs ?t=<token>)
    GET  /api/health            -> {"ok": true, "version": "..."}
    GET  /api/providers         -> the provider registry status table
    POST /api/run               -> stream-json NDJSON from a real `keel` run
    GET  /ui/<file>             -> static assets (app shell)
    GET  /api/fs/list?path=     -> list sub-directories of a local folder
    GET  /api/fs/roots          -> drive/filesystem roots (C:\\, /, …)
    GET  /api/workdir           -> {"path": ...} currently chosen folder (or null)
    POST /api/workdir           -> {"path": ...} set the agent's working folder,
                                   or {"path": null} to reset
    POST /api/upload            -> {"name","contentB64"} saves one file to
                                   ~/.keel/uploads/ and returns {"path": ...};
                                   the agent reads it from there with its tools

Security model (honest, machine-local):
- binds 127.0.0.1 only, never an external interface;
- a fresh random token is generated per launch and printed in the URL —
  without it, /api/* returns 403; the token is the only credential;
- non-GET requests whose Origin header is present must match the server
  origin (curl/watchers with no Origin header are allowed, like any CLI);
- /api/fs/list only ever returns *directory names*, never file contents, and
  it is token-gated like everything else — it serves the local folder
  picker. It does not sandbox: you can navigate anywhere your user can,
  by design, because you are the user;
- /api/workdir only stores a path in memory for this server process;
  nothing is written to disk.
- no state is written outside ~/.keel (transcripts are keel's own files).

/api/run passes the user's prompt to `keel -p ... --output-format stream-json`
and streams its stdout lines to the browser, newline-delimited. When a
working folder is set (see /api/workdir), the run is spawned with that
folder as its cwd, so the agent's tools (read_file / glob / grep / run_shell)
operate on it.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
import base64
import re

from . import __version__
from .fleet import routes as _fleet_routes
from .providers import registry as provider_registry
from . import settings_store as _settings_store

# In source, keel/webapp.py sits two levels below the repo root; in a
# PyInstaller one-file bundle it sits directly under sys._MEIPASS, one level
# shallower. Resolve the bundle root explicitly so the packaged sidecar serves
# the same canonical UI that is tested from source.
if getattr(sys, "frozen", False):
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
else:
    _BUNDLE_ROOT = Path(__file__).resolve().parents[2]

UI_DIR = Path(os.environ.get("KEEL_UI_DIR") or _BUNDLE_ROOT / "desktop" / "ui")
PWA_DIR = _BUNDLE_ROOT / "desktop"

DEFAULT_PORT = 8739
_STATIC_CSP = ("default-src 'none'; script-src 'self'; "
               "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
               "connect-src 'self'; font-src 'self' data:; "
               "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
_TOKEN = os.environ.get("KEEL_TOKEN") or secrets.token_urlsafe(24)
_LOCK = threading.Lock()
_CURRENT_RUN: dict = {}
_WORKDIR: Optional[str] = None

_FS_LIST_CAP = 400
_UPLOAD_MAX_BYTES = 24 * 1024 * 1024  # 24 MB per file, kept in memory while decoding
_UPLOAD_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_upload_name(name: object) -> str:
    """Reduce an attacker/user-supplied filename to a safe basename (never a path)."""
    raw = str(name or "upload").replace("\\", "/")
    base = Path(raw).name
    base = _UPLOAD_SAFE.sub("_", base).strip("._ ") or "upload"
    return base[:120]


def _fire_config_hook(payload: dict) -> None:
    """Fire ConfigChange hooks. Only section names, never values, are exposed."""
    try:
        from . import settings_store
        from .hooks import fire, parse_hooks

        hooks = parse_hooks(settings_store.load().get("hooks", {}))
        if hooks:
            fire(hooks, "ConfigChange", payload)
    except Exception:
        pass  # hooks are advisory; settings persistence must not fail


def _safe_workspace_path(raw: str) -> Path | None:
    """Resolve a path inside the bound workspace (or CWD) for read endpoints."""
    if not raw:
        return None
    base = Path(_WORKDIR).resolve() if _WORKDIR else Path(os.getcwd()).resolve()
    try:
        target = (base / raw).resolve()
    except OSError:
        return None
    if target != base and base not in target.parents:
        return None
    return target if target.is_file() else None


def _resolve_workspace_path(raw: str) -> Path | None:
    """Resolve a path inside the bound workspace without requiring a file."""
    if not raw:
        return None
    base = Path(_WORKDIR).resolve() if _WORKDIR else Path(os.getcwd()).resolve()
    try:
        target = (base / raw).resolve()
    except OSError:
        return None
    if target != base and base not in target.parents:
        return None
    return target


def _fs_roots() -> list[str]:
    if os.name == "nt":
        roots = []
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            root = f"{letter}:\\"
            try:
                if os.path.isdir(root):
                    roots.append(root)
            except OSError:
                continue
        return roots
    return ["/"]


_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", "release", ".pytest_cache", ".mypy_cache",
})


def _fuzzy_match(needle: str, haystack: str) -> bool:
    iterator = iter(haystack.lower())
    return all(char in iterator for char in needle.lower())


def _search_files(query: str, limit: int = 30) -> list[str]:
    root = (Path(_WORKDIR).expanduser() if _WORKDIR
            else Path(os.getcwd())).resolve()
    if not root.is_dir():
        return []
    needle = (query or "").strip()
    direct: list[str] = []
    fuzzy: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            try:
                rel = (Path(dirpath) / name).relative_to(root).as_posix()
            except ValueError:
                continue
            if not needle or needle.lower() in rel.lower():
                direct.append(rel)
            elif _fuzzy_match(needle, rel):
                fuzzy.append(rel)
    return (direct + fuzzy)[:max(1, min(100, limit))]


def _fs_list_payload(raw: str):
    raw = (raw or "").strip()
    if not raw:
        target = Path.home()
    else:
        try:
            target = Path(raw).expanduser()
        except (OSError, RuntimeError, ValueError):
            return HTTPStatus.BAD_REQUEST, {"error": "bad path"}
    try:
        target = target.resolve()
        exists = target.exists()
        directory = target.is_dir()
    except (OSError, RuntimeError, ValueError):
        # e.g. an embedded NUL byte: report a JSON error, never drop the socket
        return HTTPStatus.BAD_REQUEST, {"error": "bad path"}
    if not exists:
        return HTTPStatus.NOT_FOUND, {"error": "not found", "path": str(target)}
    if not directory:
        return HTTPStatus.BAD_REQUEST, {"error": "not a directory", "path": str(target)}
    parent = str(target.parent) if target.parent != target else None
    try:
        children = [p for p in target.iterdir() if p.is_dir()]
    except PermissionError:
        return HTTPStatus.OK, {"ok": True, "path": str(target), "parent": parent,
                               "roots": _fs_roots(), "dirs": [],
                               "warning": "permission denied"}
    except (OSError, ValueError) as exc:
        return HTTPStatus.OK, {"ok": True, "path": str(target), "parent": parent,
                               "roots": _fs_roots(), "dirs": [],
                               "warning": str(exc)}
    children.sort(key=lambda p: p.name.lower())
    dirs = [{"name": p.name} for p in children[:_FS_LIST_CAP]]
    return HTTPStatus.OK, {"ok": True, "path": str(target), "parent": parent,
                           "roots": _fs_roots(), "dirs": dirs,
                           "truncated": len(children) > _FS_LIST_CAP}


def token() -> str:
    return _TOKEN


def rotate_token() -> str:
    """A3.6: revoke every existing client credential by rotating the token."""
    global _TOKEN
    _TOKEN = secrets.token_urlsafe(24)
    return _TOKEN


class _KeelThreadingHTTPServer(ThreadingHTTPServer):
    """Bridge HTTP server with a listen backlog sized for client bursts.

    The stdlib default of 5 drops connections under a 100-client burst;
    128 keeps them queued without changing any handler behaviour.
    """

    request_queue_size = 128
    daemon_threads = True


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

        def _json_body(self, limit: int, *, too_large: str = "body too large"):
            """Read a bounded JSON *object* body; None means an error was sent.

            Invalid or negative Content-Length values used to raise ValueError
            or block forever on rfile.read(-1); a JSON array used to crash the
            route on ``.get``. All three now produce a normal JSON 4xx.
            """
            raw_length = self.headers.get("Content-Length", "0") or "0"
            try:
                length = int(raw_length)
            except (TypeError, ValueError):
                self._send_json({"error": "invalid Content-Length"},
                                HTTPStatus.BAD_REQUEST)
                return None
            if length < 0:
                self._send_json({"error": "invalid Content-Length"},
                                HTTPStatus.BAD_REQUEST)
                return None
            if length > limit:
                self._send_json({"error": too_large},
                                HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return None
            raw = self.rfile.read(length) if length else b"{}"
            try:
                request = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._send_json({"error": "invalid json"},
                                HTTPStatus.BAD_REQUEST)
                return None
            if not isinstance(request, dict):
                self._send_json({"error": "body must be an object"},
                                HTTPStatus.BAD_REQUEST)
                return None
            return request

        # ---------------- static UI
        def do_GET(self):
            if _fleet_routes.dispatch_get(self,
                                          _authorized=self._authorized,
                                          _origin_ok=self._origin_ok,
                                          _token=_TOKEN):
                return
            path = self.path.split("?", 1)[0]
            # ---------------- Keel v2 compat surface
            if path.startswith("/api/v2/sessions"):
                from . import compat
                parts = path.split("/", 4)
                sid = parts[4] if len(parts) > 4 else ""
                return self._v2_sessions(path, sid, compat)
            if path in ("/", ""):
                if not self._authorized():
                    self._refuse()
                    return
                # the desktop app shows the app UI at /, not the marketing
                # landing page; dev trees without app.html keep serving index.html
                ui_page = UI_DIR / "app.html"
                if not ui_page.is_file():
                    ui_page = UI_DIR / "index.html"
                self._serve_file(ui_page,
                                 extra_headers=(("Set-Cookie",
                                                 f"keel_token={_TOKEN}; HttpOnly; "
                                                 f"SameSite=Strict; Path=/"),))
                return
            if path in ("/app", "/app.html"):
                if not self._authorized():
                    self._refuse()
                    return
                page = UI_DIR / "app.html"
                if not page.is_file():
                    page = UI_DIR / "index.html"
                self._serve_file(page,
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
                nested = (UI_DIR / "ui" / name).resolve()
                if nested.is_file() and nested.is_relative_to(UI_DIR.resolve()):
                    self._serve_file(nested)
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
            if path == "/api/model-catalog":
                if not self._authorized():
                    self._refuse()
                    return
                from .provider_catalog import catalog_info, load_catalog

                doc = load_catalog()
                info = catalog_info()
                providers = [
                    {key: value for key, value in entry.items()
                     if key != "models"} | {
                        "model_count": len(entry.get("models", []))}
                    for name, entry in sorted(doc["providers"].items())
                ]
                self._send_json({
                    "version": info.version,
                    "provider_count": info.provider_count,
                    "model_count": info.model_count,
                    "source": {
                        "name": info.source_name,
                        "url": info.source_url,
                        "license": info.license,
                    },
                    "notice": info.notice,
                    "providers": providers,
                })
                return
            if path.startswith("/api/model-catalog/"):
                if not self._authorized():
                    self._refuse()
                    return
                from .provider_catalog import model_ids

                provider = urllib.parse.unquote(path[len("/api/model-catalog/"):])
                try:
                    models = model_ids(provider)
                except ValueError as exc:
                    self._send_json({"error": str(exc)},
                                    HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"provider": provider, "models": models})
                return
            if path == "/api/settings/schema":
                if not self._authorized():
                    self._refuse()
                    return
                from .config_schema import load_schema

                self._send_json(load_schema())
                return
            if path == "/api/models/resolve":
                if not self._authorized():
                    self._refuse()
                    return
                query = urllib.parse.urlparse(self.path).query
                ref = (urllib.parse.parse_qs(query).get("ref") or [""])[0]
                try:
                    from .providers.base import ProviderError
                    from .providers.registry import resolve_provider_model

                    self._send_json(resolve_provider_model(ref))
                except (ProviderError, ValueError) as exc:
                    self._send_json({"error": str(exc)},
                                    HTTPStatus.BAD_REQUEST)
                return
            if path in ("/api/docx/read", "/api/xlsx/read"):
                if not self._authorized():
                    self._refuse()
                    return
                params = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query)
                name = (params.get("path") or [""])[0]
                target = _safe_workspace_path(name)
                if target is None:
                    self._send_json({"error": "path outside workspace"},
                                    HTTPStatus.BAD_REQUEST)
                    return
                try:
                    from .documents import read_docx, read_xlsx
                    self._send_json({
                        "path": str(target),
                        "content": (read_docx(target) if path == "/api/docx/read"
                                    else read_xlsx(target)),
                    })
                except (OSError, ValueError, KeyError) as exc:
                    self._send_json({"error": str(exc)[:300]},
                                    HTTPStatus.BAD_REQUEST)
                return
            if path == "/api/fs/roots":
                if not self._authorized():
                    self._refuse()
                    return
                self._send_json({"roots": _fs_roots()})
                return
            if path == "/api/fs/list":
                if not self._authorized():
                    self._refuse()
                    return
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                raw_path = (params.get("path") or [""])[0]
                status, payload = _fs_list_payload(raw_path)
                self._send_json(payload, status)
                return
            if path == "/api/capabilities":
                if not self._authorized():
                    self._refuse()
                    return
                from . import capability_registry  # noqa: F401 - registers all
                from .capabilities import list_capabilities

                query = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query)
                surface = (query.get("surface") or [None])[0]
                self._send_json({"capabilities": list_capabilities(
                    surface=surface)})
                return
            if path == "/api/profiles":
                if not self._authorized():
                    self._refuse()
                    return
                from .agent_profiles import AgentProfiles

                state = os.environ.get("KEEL_STATE_DIR",
                                       str(Path.home() / ".keel"))
                manager = AgentProfiles(state)
                self._send_json({"profiles": manager.list(),
                                 "active": manager.active()})
                return
            if path == "/api/gateway":
                if not self._authorized():
                    self._refuse()
                    return
                from .gateway import gateway
                self._send_json(gateway().status())
                return
            if path == "/api/surfaces":
                if not self._authorized():
                    self._refuse()
                    return
                from . import surfaces as surfaces_mod
                self._send_json({"surfaces": surfaces_mod.list_surfaces()})
                return
            if path == "/api/files/search":
                if not self._authorized():
                    self._refuse()
                    return
                params = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query)
                query = (params.get("query") or [""])[0]
                try:
                    limit = int((params.get("limit") or ["30"])[0])
                except ValueError:
                    limit = 30
                self._send_json({"files": _search_files(query, limit)})
                return
            if path == "/api/workdir":
                if not self._authorized():
                    self._refuse()
                    return
                self._send_json({"path": _WORKDIR})
                return
            if path == "/api/settings":
                if not self._authorized():
                    self._refuse()
                    return
                from . import settings_store
                self._send_json(settings_store.public_view())
                return
            if path == "/api/settings/export":
                if not self._authorized():
                    self._refuse()
                    return
                from . import settings_store
                self._send_json(settings_store.export_view())
                return
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self):
            global _WORKDIR
            if _fleet_routes.dispatch_post(self,
                                           _authorized=self._authorized,
                                           _origin_ok=self._origin_ok):
                return
            if not self._origin_ok() or not self._authorized():
                self._refuse()
                return
            path = self.path.split("?", 1)[0]
            if path == "/api/capabilities/invoke":
                request = self._json_body(2_000_000)
                if request is None:
                    return
                from . import capability_registry  # noqa: F401
                from .capabilities import CapabilityError, invoke, record_audit

                cap_id = str(request.get("id", ""))
                from .capabilities import get as get_capability

                cap = get_capability(cap_id)
                needs_confirm = bool(
                    cap and (cap.permission in ("write", "execute")
                             or cap.mutates))
                # Mutating capabilities need an explicit, real boolean confirm.
                # Truthy values such as "false" or 1 must not satisfy the gate.
                if needs_confirm and request.get("confirm") is not True:
                    self._send_json({
                        "error": "confirmation_required",
                        "capability": cap_id,
                        "permission": cap.permission if cap else None},
                        HTTPStatus.CONFLICT)
                    return
                state_root = os.environ.get(
                    "KEEL_STATE_DIR", str(Path.home() / ".keel"))
                try:
                    result = invoke(
                        cap_id, request.get("params", {}),
                        context={"state_root": state_root,
                                 "cwd": _WORKDIR or os.getcwd(),
                                 "confirm": bool(request.get("confirm")),
                                 "interactive": True})
                    record_audit(state_root, {"capability": cap_id,
                                              "ok": True, "surface": "web"})
                    self._send_json(result)
                except CapabilityError as exc:
                    record_audit(state_root, {"capability": cap_id,
                                              "ok": False, "code": exc.code,
                                              "surface": "web"})
                    # Canonical error envelope with correct HTTP status:
                    # policy_denied/permission_denied -> 403,
                    # not_found -> 404, handler_error -> 500, bad_params -> 400.
                    from .api_contracts import http_status_for_code
                    status = http_status_for_code(exc.code)
                    self._send_json(
                        {"error": str(exc), "code": exc.code},
                        HTTPStatus(status))
                return
            # ---------------- Real backend product workflows
            # Same token/origin gate as every other POST (checked above) plus
            # the same strict boolean confirm requirement as capability invoke.
            if path.startswith("/api/backend-workflows/"):
                name = path[len("/api/backend-workflows/"):].strip("/")
                request = self._json_body(256_000, too_large="params too large")
                if request is None:
                    return
                if request.get("confirm") is not True:
                    self._send_json({"error": "confirmation_required",
                                     "workflow": name}, HTTPStatus.CONFLICT)
                    return
                from . import backend_workflows as _workflows
                if name not in _workflows.WORKFLOWS:
                    self._send_json({"error": "unknown_workflow", "workflow": name},
                                    HTTPStatus.NOT_FOUND)
                    return
                result = _workflows.run_workflow(name, request.get("params", {}))
                code = str(result.get("code") or "")
                hinted = result.get("http_status")
                if result.get("ok"):
                    status = HTTPStatus.OK
                elif isinstance(hinted, int) and 400 <= hinted <= 599:
                    # Workflows declare the accurate denial/status (403 for
                    # policy/permission denials, 400 for bad input) so real
                    # security failures are not reported as server errors.
                    status = HTTPStatus(hinted)
                else:
                    status = HTTPStatus.BAD_REQUEST if code in {
                        "bad_params", "bad_state_root", "unknown_workflow",
                        "permission_denied", "replay_denied", "bound_exceeded",
                        "unsupported_tool", "path_escape", "not_found",
                        "revoked", "invalid_token", "unknown_request",
                        "bad_ttl", "invalid_token", "operation_denied",
                        "csrf_denied", "bad_manifest",
                    } else HTTPStatus.INTERNAL_SERVER_ERROR
                self._send_json(result, status)
                return
            if path in ("/api/profiles/create", "/api/profiles/activate",
                        "/api/profiles/remove"):
                request = self._json_body(2_000_000)
                if request is None:
                    return
                from .agent_profiles import AgentProfiles

                state = os.environ.get("KEEL_STATE_DIR",
                                       str(Path.home() / ".keel"))
                manager = AgentProfiles(state)
                name = str(request.get("name", ""))
                if path.endswith("/create"):
                    profile = manager.create(
                        name, agents=request.get("agents") or None,
                        layout=str(request.get("layout", "split")))
                    self._send_json({"profile": profile})
                elif path.endswith("/activate"):
                    self._send_json({"ok": manager.activate(name)})
                else:
                    self._send_json({"ok": manager.remove(name)})
                return
            if path in ("/api/sessions/import", "/api/sessions/stats"):
                request = self._json_body(2_000_000)
                if request is None:
                    return
                try:
                    result = self._session_action(path, request)
                except Exception as exc:
                    self._send_json({"error": str(exc)[:300]},
                                    HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(result)
                return
            if path in ("/api/backups/create", "/api/backups/restore"):
                request = self._json_body(64_000)
                if request is None:
                    return
                try:
                    result = self._backup_action(path, request)
                except Exception as exc:
                    self._send_json({"error": str(exc)[:300]},
                                    HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(result)
                return
            # ---------------- Keel v2 compat surface
            if path.startswith("/api/v2/sessions") or path == "/api/v2/sessions":
                from . import compat
                sid = path[len("/api/v2/sessions"):].strip("/")
                return self._v2_sessions(path, sid, compat)
            if path in ("/api/gateway/start", "/api/gateway/stop"):
                from .gateway import gateway
                service = gateway()
                changed = (service.start() if path.endswith("/start")
                           else service.stop())
                self._send_json({"changed": changed,
                                 "status": service.status()})
                return
            if path == "/api/kill-switch":
                from .fleet import turn_core
                cancelled = turn_core.cancel_all_turns()
                new_token = rotate_token()
                self._send_json({"ok": True, "cancelled": cancelled,
                                 "token": new_token})
                return
            if path.startswith("/api/surfaces/"):
                name = path[len("/api/surfaces/"):].strip("/")
                from . import surfaces as surfaces_mod
                request = self._json_body(16_000)
                if request is None:
                    return
                try:
                    updated = surfaces_mod.update_surface(name, request)
                except KeyError:
                    self._send_json({"error": "unknown surface"},
                                    HTTPStatus.NOT_FOUND)
                    return
                except ValueError as exc:
                    self._send_json({"error": str(exc)},
                                    HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"surface": updated})
                return
            if path == "/api/settings":
                from . import settings_store
                request = self._json_body(64_000)
                if request is None:
                    return
                doc = settings_store.load()
                changed = False
                if isinstance(request.get("ui"), dict):
                    doc["ui"] = {**settings_store.get_ui(doc), **request["ui"]}
                    changed = True
                cfg = request.get("providerConfig")
                if isinstance(cfg, dict):
                    cur = settings_store.get_provider_config(doc)
                    merged_cfg = dict(cur)
                    if isinstance(cfg.get("preferred"), str):
                        merged_cfg["preferred"] = cfg["preferred"]
                    if isinstance(cfg.get("models"), dict):
                        merged_cfg["models"] = {**cur.get("models", {}),
                                                **cfg["models"]}
                    doc["providerConfig"] = merged_cfg
                    changed = True
                if not changed:
                    self._send_json({"error": "nothing to change"},
                                    HTTPStatus.BAD_REQUEST)
                    return
                settings_store.save(doc)
                _fire_config_hook({
                    "source": "webapp",
                    "changed_sections": sorted(request.keys()),
                })
                self._send_json({"ok": True, **settings_store.public_view(doc)})
                return
            if path == "/api/settings/import":
                from . import settings_store
                payload = self._json_body(512_000)
                if payload is None:
                    return
                doc = payload.get("doc")
                if not isinstance(doc, dict):
                    self._send_json({"error": "doc must be an object"},
                                    HTTPStatus.BAD_REQUEST)
                    return
                include_keys = bool(isinstance(payload, dict)
                                    and payload.get("include_keys"))
                try:
                    view = settings_store.merge_import(doc, include_keys=include_keys)
                except Exception as exc:
                    self._send_json({"error": f"import failed: {exc}"},
                                    HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"ok": True, **view})
                return
            if path == "/api/workdir":
                request = self._json_body(8_000)
                if request is None:
                    return
                value = request.get("path")
                if value is None or str(value).strip() == "":
                    _WORKDIR = None
                    self._send_json({"ok": True, "path": None})
                    return
                try:
                    target = Path(str(value)).expanduser().resolve()
                except Exception as exc:
                    self._send_json({"error": f"bad path: {exc}"},
                                    HTTPStatus.BAD_REQUEST)
                    return
                if not target.exists() or not target.is_dir():
                    self._send_json({"error": "not a directory",
                                     "path": str(target)},
                                    HTTPStatus.BAD_REQUEST)
                    return
                _WORKDIR = str(target)
                self._send_json({"ok": True, "path": _WORKDIR})
                return
            if path == "/api/upload":
                request = self._json_body(40 * 1024 * 1024)
                if request is None:
                    return
                name = request.get("name")
                content_b64 = request.get("contentB64")
                if not name or not content_b64:
                    self._send_json({"error": "name and contentB64 are required"},
                                    HTTPStatus.BAD_REQUEST)
                    return
                try:
                    data = base64.b64decode(str(content_b64), validate=True)
                except Exception:
                    self._send_json({"error": "contentB64 is not valid base64"},
                                    HTTPStatus.BAD_REQUEST)
                    return
                if len(data) > _UPLOAD_MAX_BYTES:
                    self._send_json({"error": "file too large (24 MB cap)"},
                                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return
                safe = _safe_upload_name(name)
                uploads = _settings_store.STATE_DIR / "uploads"
                uploads.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%d-%H%M%S")
                target = uploads / f"{stamp}-{secrets.token_hex(3)}-{safe}"
                target.write_bytes(data)
                self._send_json({"ok": True, "path": str(target),
                                 "bytes": len(data)})
                return
            if path == "/api/quick-ask":
                request = self._json_body(128_000, too_large="prompt too large")
                if request is None:
                    return
                prompt = str(request.get("prompt", "")).strip()
                if not prompt:
                    self._send_json({"error": "prompt must not be empty"},
                                    HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(self._run_sync(
                    prompt, str(request.get("provider", "auto"))))
                return
            if path != "/api/run":
                self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            request = self._json_body(128_000, too_large="prompt too large")
            if request is None:
                return
            prompt = str(request.get("prompt", "")).strip()
            if not prompt:
                self._send_json({"error": "prompt must not be empty"},
                                HTTPStatus.BAD_REQUEST)
                return
            provider = str(request.get("provider", "auto"))
            permission_mode = str(request.get("permission_mode", "default"))
            accept_risk = bool(request.get("accept_risk", False))
            model = str(request.get("model", "") or "").strip()
            self._stream_run(prompt, provider, permission_mode, accept_risk, model)

        def _run_sync(self, prompt: str, provider: str = "auto") -> dict:
            """Run a prompt synchronously and return a single JSON result."""
            args = [sys.executable, "-m", "keel", "-p", prompt,
                    "--output-format", "json", "--provider", provider,
                    "--seed", "0"]
            fake_script = os.environ.get("KEEL_FAKE_SCRIPT")
            if fake_script:
                args += ["--fake-script", fake_script]
            kwargs = {}
            if _WORKDIR and Path(_WORKDIR).is_dir():
                kwargs["cwd"] = _WORKDIR
            try:
                proc = subprocess.run(
                    args, capture_output=True, text=True, timeout=120,
                    **kwargs)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {"ok": False, "error": str(exc)[:300]}
            lines = [line for line in proc.stdout.splitlines() if line.strip()]
            if not lines:
                return {"ok": False, "error": (proc.stderr or "no output")[:300]}
            try:
                envelope = json.loads(lines[-1])
            except json.JSONDecodeError:
                return {"ok": False, "error": "invalid runtime output"}
            return {"ok": not envelope.get("is_error", False),
                    "result": envelope.get("result"),
                    "subtype": envelope.get("subtype"),
                    "permission_denials": envelope.get("permission_denials", 0),
                    "errors": envelope.get("errors", [])}

        # ---------------- internals

        def do_DELETE(self):
            if not self._origin_ok() or not self._authorized():
                self._refuse()
                return
            path = self.path.split("?", 1)[0]
            if path.startswith("/api/v2/sessions") or path == "/api/v2/sessions":
                from . import compat
                sid = path[len("/api/v2/sessions"):].strip("/")
                return self._v2_sessions(path, sid, compat)
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

        def _sse_raw(self, payload: bytes) -> None:
            try:
                self.wfile.write(payload)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError,
                    ConnectionAbortedError, ValueError, OSError) as exc:
                raise ConnectionError(str(exc) or "client disconnected")

        def _sse_write(self, event: dict) -> None:
            import json as _json
            data = _json.dumps(event, separators=(",", ":"),
                               ensure_ascii=False).encode("utf-8")
            self._sse_raw(b"data: " + data + b"\n\n")

        def _session_action(self, path: str, request: dict) -> dict:
            from .session_export import import_bundle, statistics

            store = _fleet_routes.store()
            if path.endswith("/import"):
                bundle = request.get("bundle")
                if not isinstance(bundle, dict):
                    return {"error": "bundle must be an object"}
                bot = import_bundle(store, bundle)
                return {"session": bot}
            sid = str(request.get("session_id", ""))
            return statistics(store, sid)

        def _backup_action(self, path: str, request: dict) -> dict:
            from .backups import create_backup, restore_backup

            state_root = os.environ.get(
                "KEEL_STATE_DIR", str(Path.home() / ".keel"))
            if path.endswith("/create"):
                source = _resolve_workspace_path(str(request.get("source", "")))
                if source is None or not source.is_dir():
                    return {"error": "source directory not in workspace"}
                target = _resolve_workspace_path(str(request.get("target", "")))
                if target is None:
                    return {"error": "target must be inside workspace"}
                return create_backup(source, target,
                                     str(request.get("passphrase", "")))
            target = _resolve_workspace_path(str(request.get("target", "")))
            backup = _resolve_workspace_path(str(request.get("backup", "")))
            if target is None or backup is None:
                return {"error": "backup/target must be inside workspace"}
            files = restore_backup(backup, target,
                                   str(request.get("passphrase", "")))
            return {"restored": files}

        def _v2_sessions(self, path: str, sid: str, compat) -> None:
            """OpenCode-compatible sessions surface (tracer bullet)."""
            if sid == "":
                if path != "/api/v2/sessions":
                    self._send_json({"error": "bad v2 path"}, HTTPStatus.NOT_FOUND)
                    return
                if self.command == "POST":
                    request = self._json_body(16_000)
                    if request is None:
                        return
                    title = str(request.get("title", "Untitled")).strip() or "Untitled"
                    created = compat.create_session(title)
                    self._send_json(created, HTTPStatus.CREATED)
                    return
                if self.command != "GET":
                    self._send_json({"error": "method not allowed"},
                                   HTTPStatus.METHOD_NOT_ALLOWED)
                    return
                if not self._authorized():
                    self._refuse()
                    return
                self._send_json({"sessions": compat.sessions_list()})
                return

            if not self._authorized():
                self._refuse()
                return

            parts = sid.split("/")
            base = parts[0]
            rest = "/".join(parts[1:])

            if rest == "":
                if self.command == "DELETE":
                    if not compat.delete_session(base):
                        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                        return
                    self._send_json({"ok": True})
                    return
                if self.command != "GET":
                    self._send_json({"error": "method not allowed"},
                                   HTTPStatus.METHOD_NOT_ALLOWED)
                    return
                summary = compat.get_session(base)
                if not summary:
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"session": summary,
                                 "messages": compat.message_history(base)})
                return

            if rest in ("messages",):
                if not compat.get_session(base):
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                if self.command == "GET":
                    self._send_json({"messages": compat.message_history(base)})
                    return
                if self.command != "POST":
                    self._send_json({"error": "method not allowed"},
                                   HTTPStatus.METHOD_NOT_ALLOWED)
                    return
                sid = base
                # 32 MB cap: text turns stay tiny; image turns can be several MB
                request = self._json_body(32 * 1024 * 1024)
                if request is None:
                    return
                text = str(request.get("text", "")).strip()
                workdir = str(request.get("workdir", "")).strip() or None
                if not workdir and _WORKDIR and Path(_WORKDIR).is_dir():
                    workdir = _WORKDIR  # honor the folder bound via the picker
                if not text:
                    self._send_json({"error": "text must not be empty"},
                                   HTTPStatus.BAD_REQUEST)
                    return
                # images: allowlist mime + 4 MB (base64) each, max 8
                images = []
                raw_images = request.get("images")
                if isinstance(raw_images, list):
                    if len(raw_images) > 8:
                        self._send_json({"error": "at most 8 images per message"},
                                        HTTPStatus.BAD_REQUEST)
                        return
                    for i, img in enumerate(raw_images):
                        if not isinstance(img, dict):
                            self._send_json({"error": f"images[{i}]: object expected"},
                                            HTTPStatus.BAD_REQUEST)
                            return
                        mime = str(img.get("mime") or "").strip().lower()
                        if mime not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
                            self._send_json({"error": f"images[{i}]: mime {mime!r} not allowed (png|jpeg|gif|webp)"},
                                            HTTPStatus.BAD_REQUEST)
                            return
                        data = img.get("data")
                        if not isinstance(data, str) or not data:
                            self._send_json({"error": f"images[{i}]: base64 data required"},
                                            HTTPStatus.BAD_REQUEST)
                            return
                        if len(data) > 4 * 1024 * 1024 * 4 // 3 + 8:
                            self._send_json({"error": f"images[{i}]: exceeds 4 MB"},
                                            HTTPStatus.BAD_REQUEST)
                            return
                        try:
                            import base64 as _b64
                            _b64.b64decode(data, validate=True)
                        except Exception:
                            self._send_json({"error": f"images[{i}]: invalid base64"},
                                            HTTPStatus.BAD_REQUEST)
                            return
                        images.append({"mime": mime, "data": data,
                                       "name": str(img.get("name") or f"image-{i}")[:120]})
                permission_mode = str(request.get("permission_mode", "")).strip() or None
                try:
                    result = compat.run_message(sid, text, workdir=workdir,
                                                permission_mode=permission_mode,
                                                images=images)
                except ValueError:
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                if not result.get("ok") and result.get("terminal_reason") == "busy":
                    self._send_json(result, HTTPStatus.CONFLICT)
                    return
                self._send_json(result, HTTPStatus.ACCEPTED)
                return

            if rest == "events":
                if self.command != "GET":
                    self._send_json({"error": "method not allowed"},
                                   HTTPStatus.METHOD_NOT_ALLOWED)
                    return
                if not compat.get_session(base):
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                sid = base
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                raw_since = (params.get("since") or ["0"])[0]
                try:
                    since = max(0, int(float(raw_since)))
                except (TypeError, ValueError):
                    since = 0

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                # Register the live subscription BEFORE replay so no event is
                # lost between the two reads; seq-dedup handles the overlap.
                from .fleet import routes as _fleet_routes
                store = _fleet_routes.store()
                q = store.subscribe()
                try:
                    last_seq = since
                    for e in compat.session_events(sid, since):
                        if e.get("seq") is not None:
                            last_seq = max(last_seq, e["seq"])
                        self._sse_write(e)
                    while True:
                        event = store.poll_subscribed(q, timeout=15)
                        if event is None:
                            self._sse_raw(b": ping\n\n")
                            continue
                        if event.get("bot_id") != sid:
                            continue
                        if event.get("type") == "row":
                            seq = event.get("seq") or 0
                            if seq <= last_seq:
                                continue  # already replayed
                            last_seq = seq
                        mapped = compat.live_event_to_v2(event)
                        if mapped is None:
                            continue
                        self._sse_write(mapped)
                except (BrokenPipeError, ConnectionResetError,
                        ConnectionAbortedError, ValueError, OSError,
                        ConnectionError):
                    pass
                finally:
                    store.unsubscribe(q)
                return

            if rest in ("approve", "reject"):
                if self.command != "POST":
                    self._send_json({"error": "method not allowed"},
                                   HTTPStatus.METHOD_NOT_ALLOWED)
                    return
                sid = base
                body = self._json_body(16_000)
                if body is None:
                    return
                approval_id = body.get("approval_id")
                try:
                    if rest == "approve":
                        result = compat.approve(sid, approval_id=approval_id)
                    else:
                        result = compat.reject(sid, approval_id=approval_id)
                except ValueError:
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                except KeyError as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                    return
                except RuntimeError as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
                    return
                self._send_json(result)
                return

            if rest == "pending":
                if self.command != "GET":
                    self._send_json({"error": "method not allowed"},
                                   HTTPStatus.METHOD_NOT_ALLOWED)
                    return
                try:
                    pending = compat.pending_approvals(base)
                except ValueError:
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"approvals": pending})
                return

            if rest == "cancel":
                if self.command != "POST":
                    self._send_json({"error": "method not allowed"},
                                   HTTPStatus.METHOD_NOT_ALLOWED)
                    return
                try:
                    cancelled = compat.cancel_session(base)
                except ValueError:
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
                if cancelled:
                    self._send_json({"ok": True, "cancelled": True})
                else:
                    self._send_json({"ok": False,
                                     "error": "no active turn for this session"},
                                    HTTPStatus.CONFLICT)
                return

            self._send_json({"error": "bad v2 path"}, HTTPStatus.NOT_FOUND)

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
                        permission_mode: str, accept_risk: bool,
                        model: str = ""):
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

            run_kwargs = {}
            if _WORKDIR and Path(_WORKDIR).is_dir():
                run_kwargs["cwd"] = _WORKDIR
            run_env = dict(os.environ)
            _MODEL_ENV = {"openrouter": "KEEL_OPENROUTER_MODEL",
                          "google": "KEEL_GOOGLE_MODEL",
                          "nvidia": "KEEL_NVIDIA_MODEL",
                          "anthropic": "KEEL_ANTHROPIC_MODEL",
                          "openai-compatible": "KEEL_COMPAT_MODEL"}
            if model and provider in _MODEL_ENV:
                run_env[_MODEL_ENV[provider]] = model
            run_kwargs["env"] = run_env

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace",
                    **run_kwargs)
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

    return _KeelThreadingHTTPServer(("127.0.0.1", port), Handler)


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
