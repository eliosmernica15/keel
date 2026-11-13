"""keel.fleet.routes — HTTP handlers mounted by keel.webapp.

All fleet routes require the same token as the rest of the bridge and the
same Origin rule on non-GET. SSE stream at /api/fleet/events delivers
`event: row\ndata: <row json>\n\n` frames with `: ping` keep-alives.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import Optional

from ..providers import registry as provider_registry
from . import echo as _echo
from . import groups as _groups
from . import provider_turn as _provider_turn
from . import scheduler as _scheduler
from . import turn_core as _turn_core
from .service import FleetStore

FLEET_UI_DIR = Path(__file__).resolve().parents[3] / "desktop" / "fleet"

_store: Optional[FleetStore] = None


def store() -> FleetStore:
    global _store
    if _store is None:
        _store = FleetStore()
    return _store


def reset_store_for_tests(path=None) -> FleetStore:
    """Point the module-level store at a fresh DB (test hook)."""
    global _store
    if _store is not None:
        try:
            _store.close()
        except Exception:
            pass
    _store = FleetStore(path)
    return _store


def _send(handler, obj, status=HTTPStatus.OK, extra_headers=()):
    body = json.dumps(obj, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Security-Policy",
                        "default-src 'none'; frame-ancestors 'none'")
    for key, value in extra_headers:
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler, limit: int = 256_000):
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length > limit:
        return None, "payload too large"
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        return json.loads(raw or b"{}"), None
    except json.JSONDecodeError:
        return None, "invalid json"


def _path_parts(path: str) -> list[str]:
    return [p for p in path.split("/") if p]


def _query_after(path: str) -> int:
    if "after=" in path:
        raw = path.split("after=", 1)[1].split("&", 1)[0]
        try:
            return max(0, int(raw))
        except ValueError:
            return 0
    return 0


# --------------------------------------------------------------- GET

def dispatch_get(handler, *, _authorized, _origin_ok, _token=""):
    path = handler.path.split("?", 1)[0]
    raw_path = handler.path

    if not path.startswith("/fleet") and not path.startswith("/api/fleet"):
        return False
    if not _authorized():
        _send(handler, {"refused": "token required or mismatch"},
              HTTPStatus.FORBIDDEN)
        return True

    # static app shell
    if path in ("/fleet", "/fleet/"):
        _serve_fleet_file(handler, FLEET_UI_DIR / "index.html", _token)
        return True
    if path.startswith("/fleet/"):
        name = path[len("/fleet/"):]
        candidate = (FLEET_UI_DIR / name).resolve()
        if candidate.is_file() and candidate.is_relative_to(FLEET_UI_DIR.resolve()):
            _serve_fleet_file(handler, candidate, _token)
            return True
        _send(handler, {"error": "not_found"}, HTTPStatus.NOT_FOUND)
        return True

    if not path.startswith("/api/fleet"):
        return False

    parts = _path_parts(path)  # ['api','fleet', ...]

    if parts == ["api", "fleet", "bots"]:
        _send(handler, {"bots": store().list_bots()})
        return True

    if parts == ["api", "fleet", "events"]:
        _stream_events(handler)
        return True

    if parts == ["api", "fleet", "providers"]:
        from . import session_keys
        providers = provider_registry.list_providers()
        for p in providers:
            p["session"] = session_keys.is_session_key(p["name"])
        _send(handler, {"providers": providers,
                        "session_keys": session_keys.session_providers()})
        return True

    if parts == ["api", "fleet", "groups"]:
        _send(handler, {"groups": store().list_groups()})
        return True

    # ---------------- tasks (F2)
    if parts == ["api", "fleet", "tasks"]:
        assigned = None
        status = None
        if "assigned=" in (raw_path or ""):
            assigned = raw_path.split("assigned=", 1)[1].split("&", 1)[0] or None
            if assigned == "all":
                assigned = None
            elif assigned == "unassigned":
                pass  # store handles sentinel
        if "status=" in (raw_path or ""):
            status = raw_path.split("status=", 1)[1].split("&", 1)[0] or None
        tasks = store().list_tasks(assigned_bot_id=assigned,
                                   status=status or None, limit=500)
        _send(handler, {"tasks": tasks})
        return True

    # ---------------- routines (F4)
    if parts == ["api", "fleet", "routines"]:
        bot_id = None
        if "bot_id=" in (raw_path or ""):
            bot_id = raw_path.split("bot_id=", 1)[1].split("&", 1)[0] or None
        _send(handler, {"routines": store().list_routines(bot_id=bot_id)})
        return True

    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "routines":
        rid = parts[3]
        routine = store().get_routine(rid)
        if routine is None:
            _send(handler, {"error": "routine_not_found"},
                  HTTPStatus.NOT_FOUND)
            return True
        extra = parts[4] if len(parts) >= 5 else None
        if extra == "runs":
            _send(handler, {"routine_id": rid,
                            "runs": store().list_routine_runs(rid, 50)})
            return True
        if extra is None:
            _send(handler, {"routine": routine,
                            "runs": store().list_routine_runs(rid, 10)})
            return True
        return False

    # ---------------- library (F2)
    if parts == ["api", "fleet", "library"]:
        bot_id = None
        task_id = None
        if "bot_id=" in (raw_path or ""):
            bot_id = raw_path.split("bot_id=", 1)[1].split("&", 1)[0] or None
        if "task_id=" in (raw_path or ""):
            task_id = raw_path.split("task_id=", 1)[1].split("&", 1)[0] or None
        files = store().list_library(bot_id=bot_id, task_id=task_id,
                                     limit=1000)
        _send(handler, {"files": files,
                        "usage_bytes": store().library_usage(bot_id)
                        if bot_id else None})
        return True

    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "tasks":
        tid = parts[3]
        task = store().get_task(tid)
        if task is None:
            _send(handler, {"error": "task_not_found"}, HTTPStatus.NOT_FOUND)
            return True
        extra = parts[4] if len(parts) >= 5 else None
        if extra == "events":
            _send(handler, {"task_id": tid,
                            "events": store().list_task_events(tid, 50)})
            return True
        if extra is None:
            _send(handler, {"task": task,
                            "events": store().list_task_events(tid, 50)})
            return True
        return False

    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "library":
        fid = parts[3]
        entry = store().get_library_entry(fid)
        if entry is None:
            _send(handler, {"error": "file_not_found"}, HTTPStatus.NOT_FOUND)
            return True
        extra = parts[4] if len(parts) >= 5 else None
        if extra is None:
            _send(handler, {"file": entry})
            return True
        if extra in ("download", "preview"):
            from . import library as library_fs
            try:
                data = library_fs.read_bytes(entry["bot_id"], entry["id"])
            except (OSError, ValueError) as exc:
                _send(handler, {"error": "file_missing",
                                "detail": str(exc)},
                      HTTPStatus.GONE)
                return True
            disposition = ("attachment" if extra == "download"
                           else "inline")
            filename = entry["name"].replace('"', "_")
            # previews of active content must never execute as a document:
            # text/plain for anything non-image/PDF, and CSP everywhere
            stored_mime = entry.get("mime") or "application/octet-stream"
            if extra == "preview" and not (
                    stored_mime.startswith("image/")
                    or stored_mime == "application/pdf"):
                content_type = "text/plain; charset=utf-8"
            else:
                content_type = stored_mime
            handler.send_response(HTTPStatus.OK)
            handler.send_header("Content-Type", content_type)
            handler.send_header("Content-Length", str(len(data)))
            handler.send_header("Content-Disposition",
                                f'{disposition}; filename="{filename}"')
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.send_header("Content-Security-Policy",
                                "default-src 'none'; "
                                "style-src 'unsafe-inline'")
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            handler.wfile.write(data)
            return True
        return False

    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "groups":
        gid = parts[3] if len(parts) >= 4 else None
        if not gid:
            return False
        extra = parts[4] if len(parts) >= 5 else None
        group = store().get_group(gid)
        if group is None:
            _send(handler, {"error": "group_not_found"}, HTTPStatus.NOT_FOUND)
            return True
        if extra is None:
            after = _query_after(raw_path)
            _send(handler, {"group": group,
                            "rows": store().list_group_rows(gid, after, 500)})
            return True
        if extra == "rows":
            after = _query_after(raw_path)
            _send(handler, {"group_id": gid,
                            "rows": store().list_group_rows(gid, after, 500)})
            return True
        return False

    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "fleet" and parts[2] == "bots":
        bot_id = parts[3] if len(parts) >= 4 else None
        if not bot_id:
            return False
        extra = parts[4] if len(parts) >= 5 else None
        bot = store().get_bot(bot_id)
        if bot is None:
            _send(handler, {"error": "bot_not_found"}, HTTPStatus.NOT_FOUND)
            return True
        if extra is None:
            _send(handler, {"bot": bot})
            return True
        if extra == "rows":
            after = _query_after(raw_path)
            limit = 500
            if "limit=" in raw_path:
                try:
                    limit = max(1, min(2000, int(raw_path.split("limit=", 1)[1].split("&", 1)[0])))
                except ValueError:
                    limit = 500
            _send(handler, {"bot_id": bot_id,
                            "rows": store().list_rows(bot_id, after, limit)})
            return True
        if extra == "latest_seq":
            _send(handler, {"bot_id": bot_id,
                            "seq": store().latest_seq(bot_id)})
            return True
        if extra == "policies":
            _send(handler, {"bot_id": bot_id,
                            "policies": store().list_policies(bot_id)})
            return True
        if extra == "audit":
            limit = 50
            if "limit=" in raw_path:
                try:
                    limit = max(1, min(500, int(raw_path.split("limit=", 1)[1].split("&", 1)[0])))
                except ValueError:
                    limit = 50
            _send(handler, {"bot_id": bot_id,
                            "audit": store().list_audit(bot_id, limit)})
            return True
        if extra == "export.md":
            markdown = store().export_chat_markdown(bot_id, bot)
            data = markdown.encode("utf-8")
            filename = f"{bot.get('name', 'chat').replace(' ', '-')}.md"
            handler.send_response(HTTPStatus.OK)
            handler.send_header("Content-Type", "text/markdown; charset=utf-8")
            handler.send_header("Content-Length", str(len(data)))
            handler.send_header("Content-Disposition",
                                f'attachment; filename="{filename}"')
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            handler.wfile.write(data)
            return True
        return False

    if parts == ["api", "fleet", "projects"]:
        _send(handler, {"projects": store().list_projects()})
        return True

    if parts == ["api", "fleet", "usage"]:
        _send(handler, {"usage": store().project_usage()})
        return True

    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "projects":
        pid = parts[3]
        sub = parts[4] if len(parts) >= 5 else None
        if sub == "tree":
            _send(handler, {"entries": store().list_project_tree(pid)})
            return True
        if sub == "review":
            import subprocess as _sp
            proj = store().get_project(pid)
            if not proj:
                _send(handler, {"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return True
            cwd = proj["path"]
            result = {"is_git": False, "status": "", "log": "", "diff_stat": ""}
            try:
                probe = _sp.run(["git", "rev-parse", "--is-inside-work-tree"],
                                cwd=cwd, capture_output=True, text=True,
                                timeout=8)
                if probe.returncode == 0 and probe.stdout.strip() == "true":
                    result["is_git"] = True
                    st = _sp.run(["git", "status", "--porcelain"],
                                 cwd=cwd, capture_output=True, text=True,
                                 timeout=8)
                    result["status"] = st.stdout[:12000]
                    lg = _sp.run(["git", "log", "--oneline", "-n", "8"],
                                 cwd=cwd, capture_output=True, text=True,
                                 timeout=8)
                    result["log"] = lg.stdout[:4000]
                    df = _sp.run(["git", "--no-pager", "diff", "--stat", "HEAD"],
                                 cwd=cwd, capture_output=True, text=True,
                                 timeout=8)
                    result["diff_stat"] = (df.stdout or df.stderr or "")[:12000]
            except (_sp.TimeoutExpired, OSError) as exc:
                result["error"] = f"git unavailable: {exc}"
            _send(handler, result)
            return True
        if sub == "file" and len(parts) >= 6 and parts[5] == "read":
            rel = None
            if "path=" in (raw_path or ""):
                from urllib.parse import unquote
                rel = unquote(raw_path.split("path=", 1)[1].split("&", 1)[0])
            if not rel:
                _send(handler, {"error": "path required"}, HTTPStatus.BAD_REQUEST)
                return True
            try:
                _send(handler, store().read_project_file(pid, rel))
            except FileNotFoundError:
                _send(handler, {"error": "file_not_found"}, HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        _send(handler, {"error": "not_found"}, HTTPStatus.NOT_FOUND)
        return True

    if parts == ["api", "fleet", "skills"]:
        from .. import skills as skills_mod
        try:
            found = skills_mod.discover()
        except Exception as exc:
            _send(handler, {"skills": [], "error": str(exc)})
            return True
        out = []
        for s in found:
            out.append({
                "name": s.name,
                "description": (s.description or "")[:300],
                "scope": s.scope,
                "trusted": bool(s.trusted),
                "injection_suspects": len(s.injection_suspects),
            })
        out.sort(key=lambda s: (s["scope"] != "user", s["scope"] != "bundled", s["name"]))
        _send(handler, {"skills": out})
        return True

    if parts == ["api", "fleet", "connectors"]:
        from . import connector_ops as _cops
        _send(handler, _cops.list_configured())
        return True

    if parts == ["api", "fleet", "keep-awake"]:
        from . import keepawake as _ka
        _send(handler, _ka.status())
        return True

    if parts == ["api", "fleet", "shells"]:
        bot_id = None
        if "bot_id=" in (raw_path or ""):
            bot_id = raw_path.split("bot_id=", 1)[1].split("&", 1)[0] or None
        from . import shells as _shells
        listing = _shells.list_shells(bot_id)
        _send(handler, {"shells": listing,
                        "running": sum(1 for s in listing if s.get("running"))})
        return True

    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "shells":
        handle = parts[3]
        if handle == "clear" and parts[4:] == ["finished"]:
            from . import shells as _shells
            _send(handler, {"cleared": _shells.clear_finished()})
            return True
        from . import shells as _shells
        extra = parts[4] if len(parts) >= 5 else None
        if extra == "output":
            _send(handler, _shells.read_output(handle))
            return True
        _send(handler, {"error": "not_found"}, HTTPStatus.NOT_FOUND)
        return True

    return False


# --------------------------------------------------------------- POST

def dispatch_post(handler, *, _authorized, _origin_ok):
    path = handler.path.split("?", 1)[0]

    if path.startswith("/fleet"):
        return False  # read-only shell; writes all go through /api/fleet/*

    if not path.startswith("/api/fleet"):
        return False
    if not _origin_ok() or not _authorized():
        _send(handler, {"refused": "origin or token mismatch"},
              HTTPStatus.FORBIDDEN)
        return True

    parts = _path_parts(path)

    if parts == ["api", "fleet", "providers", "catalog"]:
        from . import session_keys
        payload, err = _read_json(handler, limit=1024)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        name = str(payload.get("name", "")).strip().lower()
        cap = provider_registry.capability(name)
        if cap is None:
            _send(handler, {"ok": False, "error": "unknown_provider",
                            "detail": f"unknown provider {name!r}"},
                  HTTPStatus.BAD_REQUEST)
            return True
        key = os.environ.get(cap.env_var, "").strip()
        if not key:
            _send(handler, {"ok": False, "error": "not_configured",
                            "detail": f"{name}: no key in env or session"})
            return True
        try:
            models, models_meta = session_keys.fetch_models_with_meta(name, key)
        except session_keys.ProviderKeyError as exc:
            _send(handler, {"ok": False, "error": exc.category,
                            "detail": exc.detail})
            return True
        _send(handler, {"ok": True, "provider": name, "models": models,
                        "model_count": len(models),
                        "models_meta": models_meta,
                        "key_source": ("session" if session_keys.is_session_key(name)
                                       else f"env:{cap.env_var}")})
        return True

    if parts == ["api", "fleet", "providers", "credential"]:
        from . import session_keys
        payload, err = _read_json(handler, limit=4096)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        name = str(payload.get("name", "")).strip().lower()
        key = str(payload.get("key", "")).strip()
        cap = provider_registry.capability(name)
        if cap is None:
            _send(handler, {"ok": False, "error": "unknown_provider",
                            "detail": f"unknown provider {name!r}"},
                  HTTPStatus.BAD_REQUEST)
            return True
        if not key or len(key) > 512:
            _send(handler, {"ok": False, "error": "bad_key",
                            "detail": "key must be 1–512 characters"},
                  HTTPStatus.BAD_REQUEST)
            return True
        try:
            models, models_meta = session_keys.fetch_models_with_meta(name, key)
        except session_keys.ProviderKeyError as exc:
            _send(handler, {"ok": False, "error": exc.category,
                            "detail": exc.detail})
            return True
        session_keys.set_session_key(name, key)
        _log_safe = name
        import logging
        logging.getLogger("keel.fleet").info(
            "session key accepted for provider %s (%d models)",
            _log_safe, len(models))
        _send(handler, {"ok": True, "provider": name,
                        "models": models, "model_count": len(models),
                        "models_meta": models_meta,
                        "key_source": "session",
                        "note": "held for this process only; nothing was "
                                "written to disk. Restart the bridge to forget."})
        return True

    if parts == ["api", "fleet", "providers", "credential", "clear"]:
        from . import session_keys
        payload, err = _read_json(handler, limit=1024)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        name = str(payload.get("name", "")).strip().lower()
        cleared = session_keys.clear_session_key(name)
        if not cleared:
            _send(handler, {"ok": False,
                            "error": "not_session_key",
                            "detail": "no session key to clear for this "
                                      "provider; its key (if any) came from "
                                      "the environment and is untouched"})
            return True
        _send(handler, {"ok": True, "provider": name})
        return True

    if parts == ["api", "fleet", "bots"]:
        payload, err = _read_json(handler)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        name = str(payload.get("name", "")).strip()
        role = str(payload.get("role", "")).strip()
        if not name:
            _send(handler, {"error": "name must not be empty"},
                  HTTPStatus.BAD_REQUEST)
            return True
        engine = str(payload.get("engine", "provider"))
        notes = str(payload.get("notes", ""))[:4096]
        if engine not in ("provider", "echo"):
            engine = "provider"
        avatar_hue = payload.get("avatar_hue")
        try:
            bot = store().create_bot(name=name, role=role, engine=engine,
                                     notes=notes,
                                     avatar_hue=int(avatar_hue) if avatar_hue is not None else None)
        except ValueError as exc:
            _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        _send(handler, {"bot": bot}, HTTPStatus.CREATED)
        return True

    if parts == ["api", "fleet", "groups"]:
        payload, err = _read_json(handler)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        name = str(payload.get("name", "")).strip()
        bot_ids = payload.get("bot_ids", [])
        if not isinstance(bot_ids, list):
            _send(handler, {"error": "bot_ids must be a list"},
                  HTTPStatus.BAD_REQUEST)
            return True
        try:
            group = store().create_group(name=name,
                                         bot_ids=[str(b) for b in bot_ids])
        except ValueError as exc:
            _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        _send(handler, {"group": group}, HTTPStatus.CREATED)
        return True

    if parts == ["api", "fleet", "keep-awake"]:
        payload, err = _read_json(handler)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        from . import keepawake as _ka
        if bool(payload.get("on")):
            _send(handler, _ka.set_on(store()))
        else:
            _send(handler, _ka.set_off())
        return True

    if len(parts) == 5 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "shells" and parts[4] == "kill":
        from . import shells as _shells
        _send(handler, _shells.kill(parts[3]))
        return True

    # ---------------- connectors — add / test / remove
    if parts == ["api", "fleet", "connectors", "add"]:
        payload, err = _read_json(handler)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        from . import connector_ops as _cops
        preset = str(payload.get("preset", "")).strip().lower()
        env = payload.get("env") if isinstance(payload.get("env"), dict) else None
        args = payload.get("args") if isinstance(payload.get("args"), list) else []
        try:
            if preset:
                spec = _cops.preset_spec(preset,
                                         [str(a) for a in args],
                                         {str(k): str(v) for k, v in (env or {}).items()})
                name = str(payload.get("name") or preset or "connector").strip()
                _send(handler, _cops.add_connector(name, spec["command"], spec["args"], spec.get("env")))
            else:
                name = str(payload.get("name", "")).strip()
                command = str(payload.get("command", "")).strip()
                env_dict = {str(k): str(v) for k, v in (env or {}).items()} if env else None
                _send(handler, _cops.add_connector(name, command,
                                                   [str(a) for a in (payload.get("args") or [])],
                                                   env_dict))
        except ValueError as exc:
            _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        return True

    if parts == ["api", "fleet", "connectors", "test"]:
        payload, err = _read_json(handler)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        name = str(payload.get("name", "")).strip()
        if not name:
            _send(handler, {"error": "name required"}, HTTPStatus.BAD_REQUEST)
            return True
        from ..mcp import parse_servers, McpServer
        from ..settings import resolve, default_state_root
        from pathlib import Path as _Path
        try:
            resolved = resolve(state_root=default_state_root(), cwd=_Path.cwd())
            servers = parse_servers(resolved.value.get("mcpServers", {}) or {})
        except Exception as exc:
            _send(handler, {"error": f"settings resolve failed: {exc}"},
                  HTTPStatus.BAD_GATEWAY)
            return True
        target = next((s for s in servers if s.name == name), None)
        if target is None:
            _send(handler, {"error": f"connector {name!r} is not configured"},
                  HTTPStatus.NOT_FOUND)
            return True
        server = McpServer(target, timeout=25.0)
        try:
            server.start()
            tools = [{"name": t.get("name"),
                      "description": str(t.get("description", ""))[:120]}
                     for t in server.tools]
            _send(handler, {"ok": True, "name": name,
                            "tool_count": len(tools), "tools": tools})
        except Exception as exc:
            _send(handler, {"ok": False, "name": name,
                            "error": (str(exc) or "handshake failed")[:300]})
        finally:
            server._kill()
        return True

    if parts == ["api", "fleet", "connectors", "remove"]:
        payload, err = _read_json(handler)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        name = str(payload.get("name", "")).strip()
        if not name:
            _send(handler, {"error": "name required"}, HTTPStatus.BAD_REQUEST)
            return True
        from . import connector_ops as _cops
        _send(handler, _cops.remove_connector(name))
        return True

    # ---------------- project — get/create its dedicated chat
    if len(parts) == 5 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "projects" and parts[4] == "chat":
        pid = parts[3]
        proj = store().get_project(pid)
        if proj is None:
            _send(handler, {"error": "project_not_found"}, HTTPStatus.NOT_FOUND)
            return True
        bot = store().chat_for_project(pid)
        _send(handler, {"bot": bot}, HTTPStatus.OK)
        return True

    # ---------------- projects — terminal exec in the picked folder
    if len(parts) == 6 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "projects" and parts[4] == "terminal" \
            and parts[5] == "exec":
        pid = parts[3]
        proj = store().get_project(pid)
        if not proj:
            _send(handler, {"error": "project_not_found"}, HTTPStatus.NOT_FOUND)
            return True
        payload, err = _read_json(handler, limit=64 * 1024)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        command = str(payload.get("command", "")).strip()
        if not command:
            _send(handler, {"error": "command must not be empty"},
                  HTTPStatus.BAD_REQUEST)
            return True
        shell = str(payload.get("shell", "powershell" if os.name == "nt" else "posix")).strip().lower()
        if shell not in ("posix", "powershell", "cmd"):
            shell = "powershell" if os.name == "nt" else "posix"
        from . import shells as _shells
        try:
            entry = _shells.start(store(), {"id": "__terminal__"},
                                  command, shell, cwd=proj["path"])
        except ValueError as exc:
            _send(handler, {"error": str(exc)}, HTTPStatus.CONFLICT)
            return True
        except OSError as exc:
            _send(handler, {"error": f"spawn failed: {exc}"},
                  HTTPStatus.BAD_REQUEST)
            return True
        _send(handler, {"handle": entry.handle, "pid": entry.pid,
                        "running": True, "command": command,
                        "shell": shell, "cwd": proj["path"]},
              HTTPStatus.ACCEPTED)
        return True

    # ---------------- projects — mutating subroutes (POST)
    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "projects":
        pid = parts[3]
        sub = parts[4] if len(parts) >= 5 else None
        if sub == "trust":
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            trusted = bool(payload.get("trusted"))
            proj = store().set_project_trusted(pid, trusted)
            _send(handler, {"project": proj} if proj else {"error": "not_found"},
                  200 if proj else 404)
            return True
        if sub == "open":
            proj = store().open_project(pid)
            _send(handler, {"project": proj} if proj else {"error": "not_found"},
                  200 if proj else 404)
            return True
        if sub == "remove":
            ok = store().remove_project(pid)
            _send(handler, {"removed": ok})
            return True
        if sub == "model":
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            proj = store().set_project_model(pid, payload.get("model"))
            _send(handler, {"project": proj} if proj else {"error": "not_found"},
                  200 if proj else 404)
            return True
        if sub == "file" and len(parts) >= 6 and parts[5] == "write":
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            rel = str(payload.get("path", "")).strip()
            content = str(payload.get("content", ""))
            if not rel:
                _send(handler, {"error": "path required"}, HTTPStatus.BAD_REQUEST)
                return True
            try:
                _send(handler, store().write_project_file(pid, rel, content))
            except ValueError as exc:
                _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        _send(handler, {"error": "not_found"}, HTTPStatus.NOT_FOUND)
        return True

    # ---------------- projects — user picks a folder on their computer
    if parts == ["api", "fleet", "projects"]:
        payload, err = _read_json(handler)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        path = str(payload.get("path", "")).strip().strip('"')
        if not path:
            _send(handler, {"error": "path must not be empty"},
                  HTTPStatus.BAD_REQUEST)
            return True
        try:
            proj = store().create_project(path=path,
                                          name=(str(payload.get("name", "")).strip()
                                                or None))
        except ValueError as exc:
            _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        _send(handler, {"project": proj}, HTTPStatus.CREATED)
        return True

    # ---------------- tasks (F2) — user-facing CRUD
    if parts == ["api", "fleet", "tasks"]:
        payload, err = _read_json(handler)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        try:
            task = store().create_task(
                title=str(payload.get("title", "")),
                description=str(payload.get("description", "")),
                priority=str(payload.get("priority", "normal")),
                assigned_bot_id=(str(payload["assigned_bot_id"]).strip()
                                 if payload.get("assigned_bot_id") else None),
                created_by="user",
                source="user",
                source_task_id=(str(payload["source_task_id"]).strip()
                                if payload.get("source_task_id") else None))
        except ValueError as exc:
            _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        if task.get("assigned_bot_id"):
            store().append_row(task["assigned_bot_id"], "notice", {
                "text": f"Task assigned by operator: “{task['title']}” "
                        f"(id {task['id']})",
                "level": "info",
                "icon": "task"})
        _send(handler, {"task": task}, HTTPStatus.CREATED)
        return True

    if parts == ["api", "fleet", "tasks", "reorder"]:
        payload, err = _read_json(handler)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        ids = payload.get("ids") or []
        if not isinstance(ids, list):
            _send(handler, {"error": "ids must be a list"}, HTTPStatus.BAD_REQUEST)
            return True
        tasks = store().reorder_tasks([str(i) for i in ids], actor="user")
        _send(handler, {"tasks": tasks})
        return True

    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "tasks":
        tid = parts[3]
        action = parts[4] if len(parts) >= 5 else None
        if action == "undo":
            try:
                undone = store().undo_task(tid, actor="user")
            except ValueError as exc:
                _send(handler, {"error": str(exc)}, HTTPStatus.CONFLICT)
                return True
            if undone is None:
                _send(handler, {"error": "task_not_found"},
                      HTTPStatus.NOT_FOUND)
                return True
            _send(handler, {"task": undone})
            return True
        task = store().get_task(tid)
        if task is None:
            _send(handler, {"error": "task_not_found"}, HTTPStatus.NOT_FOUND)
            return True
        payload, err = _read_json(handler) if action in (
            "update", "assign") else ({}, None)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        if action == "update":
            fields = {}
            if "title" in payload:
                fields["title"] = payload["title"]
            if "description" in payload:
                fields["description"] = payload["description"]
            if "priority" in payload:
                fields["priority"] = payload["priority"]
            try:
                updated = store().update_task(
                    tid, actor="user",
                    status=(str(payload["status"]).strip().lower()
                            if payload.get("status") else None),
                    progress=(int(payload["progress"])
                              if payload.get("progress") is not None else None),
                    note=(str(payload["note"]) if payload.get("note") else None),
                    fields=fields or None)
            except (ValueError, TypeError) as exc:
                _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return True
            _send(handler, {"task": updated})
            return True
        if action == "assign":
            assignee = payload.get("assigned_bot_id")
            assignee = str(assignee).strip() if assignee else None
            try:
                updated = store().assign_task(tid, assignee, actor="user")
            except ValueError as exc:
                _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return True
            if updated and updated.get("assigned_bot_id"):
                store().append_row(updated["assigned_bot_id"], "notice", {
                    "text": f"Task assigned by operator: “{updated['title']}” "
                            f"(id {tid})",
                    "level": "info",
                    "icon": "task"})
            _send(handler, {"task": updated})
            return True
        if action == "cancel":
            updated = store().update_task(tid, actor="user", status="cancelled")
            _send(handler, {"task": updated})
            return True
        if action == "delete":
            deleted = store().delete_task(tid)
            _send(handler, {"deleted": bool(deleted)})
            return True
        return False

    # ---------------- routines (F4) — create/update/enable/pause/run/delete
    if parts == ["api", "fleet", "routines"]:
        payload, err = _read_json(handler)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        try:
            routine = store().create_routine(
                name=str(payload.get("name", "")),
                bot_id=str(payload.get("bot_id", "")),
                prompt=str(payload.get("prompt", "")),
                cron_expr=str(payload.get("cron_expr", "")),
                timezone=str(payload.get("timezone", "UTC")),
                enabled=bool(payload.get("enabled", True)),
                created_by="user")
        except ValueError as exc:
            _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        _send(handler, {"routine": routine}, HTTPStatus.CREATED)
        return True

    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "routines":
        rid = parts[3]
        action = parts[4] if len(parts) >= 5 else None
        routine = store().get_routine(rid)
        if routine is None:
            _send(handler, {"error": "routine_not_found"},
                  HTTPStatus.NOT_FOUND)
            return True
        if action == "update":
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            try:
                updated = store().update_routine(rid, fields=payload)
            except ValueError as exc:
                _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return True
            _send(handler, {"routine": updated})
            return True
        if action in ("enable", "disable", "pause", "resume"):
            payload, err = _read_json(handler) if action == "pause" else ({}, None)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            if action == "enable":
                updated = store().update_routine(rid, fields={"enabled": True})
            elif action == "disable":
                updated = store().update_routine(rid, fields={"enabled": False})
            elif action == "pause":
                updated = store().update_routine(
                    rid, fields={"paused": True,
                                 "pause_reason": str(payload.get("reason", ""))[:200]})
            else:  # resume
                updated = store().update_routine(
                    rid, fields={"paused": False, "pause_reason": ""})
            _send(handler, {"routine": updated})
            return True
        if action == "run":
            if routine.get("paused"):
                _send(handler, {"error": "routine is paused"},
                      HTTPStatus.CONFLICT)
                return True
            if not routine.get("enabled"):
                _send(handler, {"error": "routine is disabled"},
                      HTTPStatus.CONFLICT)
                return True
            if not store().claim_routine(rid):
                _send(handler, {"error": "routine is already running"},
                      HTTPStatus.CONFLICT)
                return True
            def _go():
                from . import scheduler as _sched
                try:
                    _sched.execute_routine(store(), routine,
                                           scheduled_at=None, manual=True)
                except Exception:
                    try:
                        store().release_routine(rid)
                    except Exception:
                        pass
            threading.Thread(target=_go, name=f"fleet-routine-now-{rid}",
                             daemon=True).start()
            _send(handler, {"queued": True, "routine_id": rid},
                  HTTPStatus.ACCEPTED)
            return True
        if action == "delete":
            deleted = store().delete_routine(rid)
            _send(handler, {"deleted": bool(deleted)})
            return True
        return False

    # ---------------- library (F2) — user upload + delete
    if parts == ["api", "fleet", "library"]:
        payload, err = _read_json(handler, limit=6_000_000)
        if err:
            _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
            return True
        from . import library as library_fs
        name = str(payload.get("filename", "")).strip()
        bot_id = str(payload.get("bot_id", "")).strip()
        if not bot_id or store().get_bot(bot_id) is None:
            _send(handler, {"error": "unknown or missing bot_id"},
                  HTTPStatus.BAD_REQUEST)
            return True
        try:
            name = library_fs.validate_filename(name)
        except ValueError as exc:
            _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        task_id = str(payload.get("task_id") or "").strip() or None
        if task_id and store().get_task(task_id) is None:
            _send(handler, {"error": "unknown task_id"}, HTTPStatus.BAD_REQUEST)
            return True
        import base64 as _b64
        try:
            if "content_base64" in payload:
                data = _b64.b64decode(str(payload["content_base64"]),
                                      validate=True)
            else:
                data = str(payload.get("content", "")).encode("utf-8")
        except Exception:
            _send(handler, {"error": "content_base64 is not valid base64"},
                  HTTPStatus.BAD_REQUEST)
            return True
        if len(data) > library_fs.MAX_FILE_BYTES:
            _send(handler, {"error": f"file too large "
                            f"(max {library_fs.MAX_FILE_BYTES} bytes)"},
                  HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return True
        try:
            library_fs.check_quota(store().list_library(
                bot_id=bot_id, limit=10000), len(data))
        except ValueError as exc:
            _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        import hashlib
        import secrets
        sha = hashlib.sha256(data).hexdigest()
        file_id = "f_" + secrets.token_hex(6)
        try:
            library_fs.write_bytes(bot_id, file_id, data)
        except OSError as exc:
            _send(handler, {"error": f"could not write the file: {exc}"},
                  HTTPStatus.INTERNAL_SERVER_ERROR)
            return True
        entry = store().create_library_entry(
            bot_id=bot_id, name=name,
            mime=(str(payload["mime"])[:120] if payload.get("mime")
                  else library_fs.guess_mime(name)),
            size=len(data), sha256=sha, task_id=task_id, source="user",
            file_id=file_id)
        _send(handler, {"file": entry}, HTTPStatus.CREATED)
        return True

    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "library":
        fid = parts[3]
        action = parts[4] if len(parts) >= 5 else None
        if action == "delete":
            from . import library as library_fs
            entry = store().delete_library_entry(fid)
            if entry is None:
                _send(handler, {"error": "file_not_found"},
                      HTTPStatus.NOT_FOUND)
                return True
            library_fs.delete_file(entry["bot_id"], entry["id"])
            _send(handler, {"deleted": True})
            return True
        return False

    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "fleet" \
            and parts[2] == "groups":
        gid = parts[3] if len(parts) >= 4 else None
        if not gid:
            return False
        action = parts[4] if len(parts) >= 5 else None

        if action == "delete":
            deleted = store().delete_group(gid)
            _send(handler, {"deleted": bool(deleted)})
            return True

        if action == "messages":
            group = store().get_group(gid)
            if group is None:
                _send(handler, {"error": "group_not_found"},
                      HTTPStatus.NOT_FOUND)
                return True
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            content = str(payload.get("content", "")).strip()
            if not content:
                _send(handler, {"error": "content must not be empty"},
                      HTTPStatus.BAD_REQUEST)
                return True
            if len(content) > 32_000:
                _send(handler, {"error": "content too long"},
                      HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return True
            user_row = store().append_group_row(gid, "user", "message", {
                "role": "user",
                "content": content,
            })
            lock, started = _groups.start_group_round(store(), group, content)
            if not started:
                _send(handler, {"queued": False,
                                "busy": True,
                                "seq": user_row["seq"]},
                      HTTPStatus.CONFLICT)
                return True
            _send(handler, {"queued": True, "seq": user_row["seq"]},
                  HTTPStatus.ACCEPTED)
            return True
        return False

    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "fleet" and parts[2] == "bots":
        bot_id = parts[3] if len(parts) >= 4 else None
        if not bot_id:
            return False
        action = parts[4] if len(parts) >= 5 else None
        bot = store().get_bot(bot_id)
        if bot is None:
            _send(handler, {"error": "bot_not_found"}, HTTPStatus.NOT_FOUND)
            return True

        if action == "fork":
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            name = str(payload.get("name", "")).strip() or None
            up_to = payload.get("up_to_seq")
            try:
                up_to_seq = int(up_to) if up_to is not None else None
            except (TypeError, ValueError):
                _send(handler, {"error": "up_to_seq must be an integer"},
                      HTTPStatus.BAD_REQUEST)
                return True
            forked = store().fork_bot(bot_id, name=name, up_to_seq=up_to_seq)
            _send(handler, {"bot": forked}, HTTPStatus.CREATED)
            return True

        if action == "rewind":
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            try:
                from_seq = int(payload.get("from_seq") or 0)
            except (TypeError, ValueError):
                _send(handler, {"error": "from_seq must be an integer"},
                      HTTPStatus.BAD_REQUEST)
                return True
            if from_seq <= 0:
                _send(handler, {"error": "from_seq must be positive"},
                      HTTPStatus.BAD_REQUEST)
                return True
            deleted = store().delete_rows_from(bot_id, from_seq)
            _send(handler, {"rows": deleted, "deleted": len(deleted)})
            return True

        if action == "restore":
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            rows = payload.get("rows")
            if not isinstance(rows, list):
                _send(handler, {"error": "rows must be a list"},
                      HTTPStatus.BAD_REQUEST)
                return True
            restored = store().restore_rows(bot_id, rows)
            _send(handler, {"restored": restored})
            return True

        if action == "asks" and len(parts) >= 7:
            ask_id = parts[5]
            sub = parts[6]
            if sub == "answer":
                payload, err = _read_json(handler)
                if err:
                    _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                    return True
                answer = str(payload.get("answer", "")).strip()
                if not answer:
                    _send(handler, {"error": "answer must not be empty"},
                          HTTPStatus.BAD_REQUEST)
                    return True
                from . import asks as _asks
                ok = _asks.broker.answer(bot_id, ask_id, answer)
                if not ok:
                    _send(handler, {"error": "ask_not_found_or_expired"},
                          HTTPStatus.NOT_FOUND)
                    return True
                _send(handler, {"ok": True})
                return True

        if action == "messages":
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            content = str(payload.get("content", "")).strip()
            if not content:
                _send(handler, {"error": "content must not be empty"},
                      HTTPStatus.BAD_REQUEST)
                return True
            if len(content) > 32_000:
                _send(handler, {"error": "content too long"},
                      HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return True
            mode = str(payload.get("mode", "build")).strip().lower()
            if mode not in ("build", "plan", "autopilot", "acceptEdits"):
                mode = "build"
            # engine gate — F0/F-provider: echo + provider both wired here
            if bot["engine"] == "echo":
                seq_bot = store().append_row(bot_id, "message", {
                    "role": "user",
                    "content": content,
                })
                lock, started = _echo.start_turn(store(), bot, content)
            elif bot["engine"] == "provider":
                seq_bot = store().append_row(bot_id, "message", {
                    "role": "user",
                    "content": content,
                })
                lock, started = _provider_turn.start_provider_turn(
                    store(), bot, content, permission_mode=mode)
            else:
                _send(handler, {"error": "unknown_engine",
                                "detail": f"engine {bot['engine']!r} not supported"},
                      HTTPStatus.CONFLICT)
                return True
            if not started:
                _send(handler, {"queued": False,
                                "busy": True,
                                "seq": seq_bot["seq"]},
                      HTTPStatus.CONFLICT)
                return True
            _send(handler, {"queued": True, "seq": seq_bot["seq"]},
                  HTTPStatus.ACCEPTED)
            return True

        if action == "cancel":
            cancelled = _turn_core.cancel_active_turn(bot_id)
            _send(handler, {"cancelled": bool(cancelled)})
            return True

        if action == "update":
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            try:
                updated = store().update_bot(bot_id, **payload)
            except ValueError as exc:
                _send(handler, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return True
            _send(handler, {"bot": updated})
            return True

        if action == "delete":
            deleted = store().delete_bot(bot_id)
            _send(handler, {"deleted": bool(deleted)})
            return True

        if action == "policies":
            sub = parts[5] if len(parts) > 5 else None
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            if sub == "revoke":
                tool_name = str(payload.get("tool_name", "")).strip()
                if not tool_name:
                    _send(handler, {"error": "tool_name must not be empty"},
                          HTTPStatus.BAD_REQUEST)
                    return True
                revoked = store().revoke_policy(bot_id, tool_name)
                if revoked:
                    store().append_audit(bot_id=bot_id, tool_name=tool_name,
                                         fingerprint="policy",
                                         event="policy_revoked",
                                         decision=None, outcome=None)
                _send(handler, {"bot_id": bot_id, "tool_name": tool_name,
                                "revoked": bool(revoked)})
                return True
            _send(handler, {"error": "unknown_policy_action"},
                  HTTPStatus.NOT_FOUND)
            return True

        if action == "approvals":
            approval_id = parts[5] if len(parts) > 5 else None
            verb = parts[6] if len(parts) > 6 else None
            if not approval_id or verb != "decide":
                _send(handler, {"error": "expected /approvals/<id>/decide"},
                      HTTPStatus.NOT_FOUND)
                return True
            payload, err = _read_json(handler)
            if err:
                _send(handler, {"error": err}, HTTPStatus.BAD_REQUEST)
                return True
            decision = str(payload.get("decision", "")).strip().lower()
            if decision not in ("once", "always", "never"):
                _send(handler, {"error": "decision must be once | always | never"},
                      HTTPStatus.BAD_REQUEST)
                return True
            changed, approval, error = store().approvals.decide(
                bot_id=bot_id, approval_id=approval_id, decision=decision)
            if error == "approval_not_found":
                _send(handler, {"error": "approval_not_found"},
                      HTTPStatus.NOT_FOUND)
                return True
            if error:
                _send(handler, {"error": error,
                                "approval": {k: approval[k] for k in
                                             ("approval_id", "status", "decision",
                                              "decided_at") if k in approval}},
                      HTTPStatus.CONFLICT)
                return True
            _send(handler, {"bot_id": bot_id,
                            "approval": approval,
                            "outcome": "granted" if decision != "never" else "refused"})
            return True

    return False


def _serve_fleet_file(handler, path: Path, token: str = "") -> None:
    suffix = path.suffix.lower()
    content_type = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")
    body = path.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-cache")
    from ..webapp import _STATIC_CSP
    handler.send_header("Content-Security-Policy", _STATIC_CSP)
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    if token:
        handler.send_header("Set-Cookie",
                            f"keel_token={token}; HttpOnly; "
                            f"SameSite=Strict; Path=/")
    handler.end_headers()
    handler.wfile.write(body)


# --------------------------------------------------------------- SSE

def _stream_events(handler) -> None:
    try:
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("X-Accel-Buffering", "no")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()
    except (BrokenPipeError, ConnectionResetError):
        return

    q = store().subscribe()
    try:
        while True:
            event = store().poll_subscribed(q, timeout=10)
            try:
                if event is None:
                    payload = b": ping\n\n"
                else:
                    data = json.dumps(event, separators=(",", ":"),
                                      ensure_ascii=False).encode("utf-8")
                    payload = b"event: row\ndata: " + data + b"\n\n"
                handler.wfile.write(payload)
                handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError,
                    ConnectionAbortedError, ValueError, OSError):
                break
    finally:
        store().unsubscribe(q)
