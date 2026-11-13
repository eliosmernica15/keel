"""keel.fleet.service — Fleet roster state + SSE broadcast.

Thread model: the fleet worker (per turn) writes rows through a single
FleetStore; SSE subscribers read-only via /api/fleet/events with a cursor
(after_seq). The store hands each subscriber a private queue; publishing
must never block a turn on a slow client (drop-oldest, bounded).
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Iterator

from .db import connect
from .approvals import ApprovalBroker

_SUBSCRIBER_QUEUE = 256


def _utcnow() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _row_to_dict(row) -> dict:
    d = dict(row)
    for k, v in list(d.items()):
        if isinstance(v, str) and v.startswith("{") and k in ("body",):
            try:
                d[k] = json.loads(v)
            except json.JSONDecodeError:
                pass
    return d


class FleetStore:
    """Single-threaded access point with a publish/subscribe fan-out."""

    def __init__(self, db_path=None):
        self._conn = connect(db_path)
        self._lock = threading.RLock()
        self._subscribers: set[queue.Queue] = set()
        self._subscribers_lock = threading.Lock()
        self.approvals = ApprovalBroker(self)
        # F1: pending approvals cannot survive a restart — refuse them closed
        # and leave a resolved card behind for anyone who opens the chat.
        restarted = self.expire_pending_approvals(by="restart")
        for approval in restarted:
            self.append_row(approval["bot_id"], "approval", {
                "approval_id": approval["approval_id"],
                "tool_name": approval["tool_name"],
                "status": "expired",
                "decision": "restart",
                "decided_at": approval.get("decided_at"),
            })
            self.append_audit(bot_id=approval["bot_id"],
                              tool_name=approval["tool_name"],
                              fingerprint=approval["fingerprint"],
                              event="decided", decision="restart",
                              outcome="refused",
                              approval_id=approval["approval_id"])
        # pending ask_user questions cannot survive a restart either —
        # expire them, leave a notice behind for the chat
        self.expire_pending_asks()
        # F4: routines interrupted by a restart must not stay "running"
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, routine_id, task_id FROM fleet_routine_runs\n"
                " WHERE status = 'running'").fetchall()
            now = _utcnow()
            for row in rows:
                self._conn.execute(
                    "UPDATE fleet_routine_runs\n"
                    "   SET status = 'failed',\n"
                    "       error = 'interrupted by server restart',\n"
                    "       finished_at = ?\n"
                    " WHERE id = ?", (now, row["id"]))
                if row["task_id"]:
                    self._conn.execute(
                        "UPDATE fleet_tasks SET status = 'failed',\n"
                        " updated_at = ? WHERE id = ? AND status != 'completed'",
                        (now, row["task_id"]))
                    self.append_task_event(
                        row["task_id"], actor="user", event="status",
                        to_status="failed",
                        note="routine interrupted by server restart")
            if rows:
                self._conn.execute(
                    "UPDATE fleet_routines SET running = 0 WHERE running = 1")
                self._conn.commit()

    # ---------------- pending asks (F1-style timeouts)
    def expire_pending_asks(self) -> int:
        """On restart: pending asks are unroutable. Expire them with a notice."""
        import json as _json
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, bot_id, body FROM rows\n"
                " WHERE kind = 'ask'\n"
                "   AND json_type(body, '$.status') = '\"pending\"'").fetchall()
            count = 0
            for row in rows:
                count += 1
                body = _json.loads(row["body"]) if isinstance(row["body"], str) else dict(row["body"])
                body["status"] = "interrupted"
                self._conn.execute(
                    "UPDATE rows SET body = ? WHERE seq = ?",
                    (_json.dumps(body), row["seq"]))
                self.append_row(row["bot_id"], "notice", {
                    "text": ("A question for you (“{0}”) was interrupted by "
                             "the server restarting; the agent got no answer."
                             .format(str(body.get("question", ""))[:120])),
                    "level": "warning",
                    "icon": "question",
                })
            if count:
                self._conn.commit()
            return count

    # ---------------- subscriber machinery
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=_SUBSCRIBER_QUEUE)
        with self._subscribers_lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._subscribers_lock:
            self._subscribers.discard(q)

    def _publish(self, event: dict) -> None:
        with self._subscribers_lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    try:
                        q.get_nowait()  # drop oldest
                    except queue.Empty:
                        pass
                    try:
                        q.put_nowait(event)
                    except queue.Full:
                        pass

    def poll_subscribed(self, q: queue.Queue, timeout: float) -> dict | None:
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return None

    def publish(self, event: dict) -> None:
        """Publish an ephemeral (non-persisted) event to SSE subscribers.

        Used for live token streaming; these frames are NOT written to
        the rows table. Subscribers receive them raw on the same fan-out
        as persisted rows.
        """
        try:
            self._publish(event)
        except Exception:
            pass  # fan-out is best-effort

    # ---------------- bots
    def create_bot(self, *, name: str, role: str = "",
                   engine: str = "provider",
                   notes: str = "",
                   preset: str | None = None,
                   avatar_hue: int | None = None) -> dict:
        slug = _slugify(name)
        base = slug
        suffix = 0
        while self._bot_exists(base):
            suffix += 1
            base = f"{slug}-{suffix}"
        name = name.strip()
        if not name:
            raise ValueError("name must not be empty")
        if len(name) > 64:
            raise ValueError("name must be at most 64 characters")
        if engine not in ("provider", "echo"):
            raise ValueError(f"unknown engine {engine!r}; "
                             "choose 'provider' or 'echo'")
        avatar_hue = (int(avatar_hue) % 360 if avatar_hue is not None
                      else int.from_bytes(os.urandom(2), "big") % 360)
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                "INSERT INTO bots(id, name, role, engine, provider, model,\n"
                "                 notes, avatar_hue, created_at, updated_at,\n"
                "                 last_active_at)\n"
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (base, name, role.strip()[:120], engine, "auto", "",
                 str(notes)[:4096], avatar_hue, now, now, now))
            self._conn.commit()
            bot = self.get_bot(base)
        # announce creation as a notice so open tabs update without reload
        note = self.append_row(base, "notice", {
            "text": (f"{name} joined the fleet. Engine: echo (scripted)."
                     if engine == "echo" else
                     f"{name} joined the fleet. Engine: provider."),
            "icon": "confetti",
        })
        return bot

    def get_bot(self, bot_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def list_bots(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM bots ORDER BY last_active_at DESC").fetchall()
        return [_row_to_dict(r) for r in rows]

    def _bot_exists(self, bot_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM bots WHERE id = ?", (bot_id,)).fetchone()
        return row is not None

    def update_bot(self, bot_id: str, **fields) -> dict | None:
        allowed = {"name", "role", "provider", "model", "notes",
                   "avatar_hue", "engine", "reasoning_effort"}
        updates: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "name":
                value = str(value).strip()[:64]
                if not value:
                    continue
            elif key == "role":
                value = str(value).strip()[:120]
            elif key == "notes":
                value = str(value)[:4096]
            elif key == "avatar_hue":
                value = int(value) % 360
            elif key == "engine" and value not in ("provider", "echo"):
                continue
            elif key in ("provider", "model"):
                value = str(value).strip()[:120]
            elif key == "reasoning_effort":
                effort = str(value or "").strip().lower()
                if effort:
                    known = {"none", "low", "medium", "high", "xhigh", "max",
                             "minimal"}
                    if effort not in known:
                        raise ValueError(
                            f"reasoning_effort must be one of "
                            f"{sorted(known)}")
                    value = effort
                else:
                    value = None
            updates.append(f"{key} = ?")
            values.append(value)
        if not updates:
            return self.get_bot(bot_id)
        updates.append("updated_at = ?")
        values.append(_utcnow())
        with self._lock:
            self._conn.execute(
                f"UPDATE bots SET {', '.join(updates)} WHERE id = ?",
                (*values, bot_id))
            self._conn.execute(
                "UPDATE bots SET last_active_at = ? WHERE id = ?",
                (values[-2], bot_id))
            self._conn.commit()
        return self.get_bot(bot_id)

    # ---------------- projects (local folders the human picked)
    def create_project(self, *, path: str, name: str | None = None) -> dict:
        import uuid as _uuid
        from pathlib import Path as _Path
        p = _Path(path).expanduser().resolve()
        if not p.is_dir():
            raise ValueError(f"not a directory: {p}")
        pid = _uuid.uuid4().hex[:12]
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                "INSERT INTO fleet_projects(id, path, name, model, created_at, last_opened_at)\n"
                " VALUES (?,?,?,NULL,?,?)",
                (pid, str(p), name or p.name, now, now))
            self._conn.commit()
        return self.get_project(pid) or {}

    def list_projects(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, path, name, model, created_at, last_opened_at, trusted\n"
                " FROM fleet_projects ORDER BY last_opened_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_project(self, project_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, path, name, model, created_at, last_opened_at, trusted\n"
                " FROM fleet_projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def open_project(self, project_id: str) -> dict | None:
        with self._lock:
            self._conn.execute(
                "UPDATE fleet_projects SET last_opened_at = ? WHERE id = ?",
                (_utcnow(), project_id))
            self._conn.commit()
        return self.get_project(project_id)

    def set_project_model(self, project_id: str, model: str | None) -> dict | None:
        with self._lock:
            self._conn.execute(
                "UPDATE fleet_projects SET model = ? WHERE id = ?",
                (model, project_id))
            self._conn.commit()
        return self.get_project(project_id)

    def set_project_trusted(self, project_id: str, trusted: bool) -> dict | None:
        with self._lock:
            self._conn.execute(
                "UPDATE fleet_projects SET trusted = ? WHERE id = ?",
                (1 if trusted else 0, project_id))
            self._conn.commit()
        return self.get_project(project_id)

    def remove_project(self, project_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM fleet_projects WHERE id = ?", (project_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def project_usage(self) -> dict:
        """Sum token usage recorded in turn_end rows. Approximate: fleet doesn't
        bind conversations to projects, so this is a global
        'this session of Keel' view, clearly labelled in the UI."""
        totals = {"input_tokens": 0, "output_tokens": 0,
                  "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0}
        with self._lock:
            rows = self._conn.execute(
                "SELECT body FROM rows WHERE kind = 'turn_end'").fetchall()
        for r in rows:
            try:
                body = json.loads(r["body"])
            except json.JSONDecodeError:
                continue
            usage = body.get("usage") or {}
            for k in totals:
                totals[k] += int(usage.get(k, 0))
        return totals

    def list_project_tree(self, project_id: str, *, max_entries: int = 4000) -> list[dict]:
        """Depth-first listing of the project folder; dirs and files."""
        proj = self.get_project(project_id)
        if not proj:
            return []
        from pathlib import Path as _Path
        root = _Path(proj["path"])
        entries: list[dict] = []
        ignored = {".git", "node_modules", "__pycache__", ".venv", "venv",
                   "dist", "build", ".next", "target", ".idea", ".vs",
                   ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        try:
            for dirpath, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs
                           if d not in ignored
                           and not d.startswith(".")]
                for f in sorted(files):
                    if f.startswith("."):
                        continue
                    rel = os.path.relpath(os.path.join(dirpath, f), root)
                    try:
                        size = os.path.getsize(os.path.join(dirpath, f))
                    except OSError:
                        size = 0
                    entries.append({"path": rel.replace("\\", "/"),
                                    "name": f,
                                    "size": size,
                                    "dir": os.path.relpath(dirpath, root).replace("\\", "/") if os.path.relpath(dirpath, root) != "." else ""})
                    if len(entries) >= max_entries:
                        return entries
        except OSError:
            pass
        return entries

    def read_project_file(self, project_id: str, rel_path: str,
                          *, max_bytes: int = 1_500_000) -> dict:
        proj = self.get_project(project_id)
        if not proj:
            raise ValueError("unknown project")
        from pathlib import Path as _Path
        base = _Path(proj["path"]).resolve()
        target = (base / rel_path).resolve()
        # strict containment — never escape the project root
        if base != target.parent and base not in target.parents:
            raise ValueError("path escapes the project root")
        if not target.is_file():
            raise FileNotFoundError(rel_path)
        data = target.read_bytes()[: max_bytes + 1]
        truncated = len(data) > max_bytes
        try:
            text = data[:max_bytes].decode("utf-8")
        except UnicodeDecodeError:
            # binary: base64-encode with a marker so the UI can offer download
            import base64
            return {"path": rel_path, "name": target.name,
                    "binary": True,
                    "mime": "application/octet-stream",
                    "content": base64.b64encode(data[:max_bytes]).decode("ascii"),
                    "size": len(data), "truncated": truncated}
        return {"path": rel_path, "name": target.name,
                "binary": False, "mime": "text/plain; charset=utf-8",
                "content": text, "size": len(data), "truncated": truncated}

    def write_project_file(self, project_id: str, rel_path: str,
                           content: str) -> dict:
        proj = self.get_project(project_id)
        if not proj:
            raise ValueError("unknown project")
        from pathlib import Path as _Path
        base = _Path(proj["path"]).resolve()
        target = (base / rel_path).resolve()
        if base != target.parent and base not in target.parents:
            raise ValueError("path escapes the project root")
        _Path(target.parent).mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        return {"ok": True, "path": rel_path, "size": len(content.encode("utf-8"))}

    def delete_bot(self, bot_id: str) -> bool:
        # purge the bot's Library files on disk before the rows cascade
        try:
            from .library import delete_file
            for entry in self.list_library(bot_id=bot_id, limit=10000):
                delete_file(bot_id, entry["id"])
        except Exception:
            pass  # rows still cascade; a stray file beats a hung delete
        with self._lock:
            cur = self._conn.execute("DELETE FROM bots WHERE id = ?", (bot_id,))
            self._conn.commit()
        return cur.rowcount > 0

    # ---------------- fork / rewind / restore (message actions)
    def fork_bot(self, source_id: str, *, name: str | None = None,
                 up_to_seq: int | None = None) -> dict | None:
        """Clone a bot (same engine/provider/model/notes) and replay its
        rows up to `up_to_seq` (inclusive) into the fork."""
        source = self.get_bot(source_id)
        if source is None:
            return None
        fork = self.create_bot(
            name=name or f"{source['name']} fork",
            role=source.get("role") or "",
            engine=source.get("engine") or "provider",
            notes=source.get("notes") or "",
            avatar_hue=source.get("avatar_hue"))
        with self._lock:
            self._conn.execute(
                "UPDATE bots SET provider = ?, model = ? WHERE id = ?",
                (source.get("provider"), source.get("model"), fork["id"]))
            if up_to_seq is None:
                rows = self._conn.execute(
                    "SELECT kind, body, created_at FROM rows\n"
                    " WHERE bot_id = ? ORDER BY seq ASC", (source_id,)).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT kind, body, created_at FROM rows\n"
                    " WHERE bot_id = ? AND seq <= ? ORDER BY seq ASC",
                    (source_id, int(up_to_seq))).fetchall()
            for row in rows:
                self._conn.execute(
                    "INSERT INTO rows(bot_id, kind, body, created_at)\n"
                    " VALUES (?,?,?,?)",
                    (fork["id"], row["kind"], row["body"], row["created_at"]))
            self._conn.execute(
                "UPDATE bots SET updated_at = ?, last_active_at = ? WHERE id = ?",
                (_utcnow(), _utcnow(), fork["id"]))
            self._conn.commit()
        self.append_row(fork["id"], "notice", {
            "text": f"Forked from {source_id}"
                    + (f" at message #{up_to_seq}" if up_to_seq else ""),
            "level": "info",
            "icon": "fork",
        })
        return self.get_bot(fork["id"])

    def delete_rows_from(self, bot_id: str, from_seq: int) -> list[dict]:
        """Rewind: delete rows with seq >= from_seq and return them (so the
        client can restore them if the operator undoes the rewind)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, bot_id, kind, body, created_at FROM rows\n"
                " WHERE bot_id = ? AND seq >= ? ORDER BY seq ASC",
                (bot_id, int(from_seq))).fetchall()
            ids = [r["seq"] for r in rows]
            if ids:
                self._conn.execute(
                    f"DELETE FROM rows WHERE seq IN ({','.join('?' * len(ids))})",
                    ids)
                self._conn.commit()
        return [_row_to_dict(r) for r in rows]

    def restore_rows(self, bot_id: str, rows: list[dict]) -> int:
        """Re-append previously deleted rows, in order."""
        count = 0
        with self._lock:
            for row in rows:
                kind = str(row.get("kind") or "message")
                body = row.get("body")
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except json.JSONDecodeError:
                        body = {"content": body}
                self._conn.execute(
                    "INSERT INTO rows(bot_id, kind, body, created_at)\n"
                    " VALUES (?,?,?,?)",
                    (bot_id, kind,
                     json.dumps(body, separators=(",", ":"), ensure_ascii=False),
                     str(row.get("created_at") or _utcnow())))
                count += 1
            self._conn.commit()
        return count

    # ---------------- rows
    def append_row(self, bot_id: str, kind: str, body: dict) -> dict:
        body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        now = _utcnow()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO rows(bot_id, kind, body, created_at) VALUES (?,?,?,?)",
                (bot_id, kind, body_json, now))
            row_id = cur.lastrowid
            self._conn.execute(
                "UPDATE bots SET updated_at = ?, last_active_at = ? WHERE id = ?",
                (now, now, bot_id))
            self._conn.commit()
        event = {
            "type": "row",
            "seq": row_id,
            "bot_id": bot_id,
            "kind": kind,
            "body": body,
            "created_at": now,
        }
        self._publish(event)
        return event

    def list_rows(self, bot_id: str, after_seq: int = 0,
                  limit: int = 500) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, kind, body, created_at FROM rows\n"
                " WHERE bot_id = ? AND seq > ?\n"
                " ORDER BY seq ASC LIMIT ?",
                (bot_id, after_seq, limit)).fetchall()
        return [{
            "seq": r["seq"],
            "bot_id": bot_id,
            "kind": r["kind"],
            "body": json.loads(r["body"]),
            "created_at": r["created_at"],
        } for r in rows]

    def latest_seq(self, bot_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(seq) FROM rows WHERE bot_id = ?", (bot_id,)).fetchone()
        return int(row[0] or 0)

    # ---------------- approval policies (F1)
    def get_policy(self, bot_id: str, tool_name: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT decision FROM fleet_policies WHERE bot_id = ? AND tool_name = ?",
                (bot_id, tool_name)).fetchone()
        return row["decision"] if row else None

    def list_policies(self, bot_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT bot_id, tool_name, decision, created_at, updated_at\n"
                " FROM fleet_policies WHERE bot_id = ?\n"
                " ORDER BY tool_name ASC", (bot_id,)).fetchall()
        return [dict(r) for r in rows]

    def set_policy(self, bot_id: str, tool_name: str, decision: str) -> None:
        if decision not in ("always", "never"):
            raise ValueError("policy decision must be 'always' or 'never'")
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                "INSERT INTO fleet_policies(bot_id, tool_name, decision, created_at, updated_at)\n"
                "VALUES (?,?,?,?,?)\n"
                "ON CONFLICT(bot_id, tool_name) DO UPDATE SET\n"
                "  decision = excluded.decision, updated_at = excluded.updated_at",
                (bot_id, tool_name, decision, now, now))
            self._conn.commit()

    def revoke_policy(self, bot_id: str, tool_name: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM fleet_policies WHERE bot_id = ? AND tool_name = ?",
                (bot_id, tool_name))
            self._conn.commit()
        return cur.rowcount > 0

    # ---------------- approvals (F1)
    def create_approval(self, *, approval_id: str, bot_id: str, tool_name: str,
                        fingerprint: str, args_summary: str,
                        expires_at: str) -> dict:
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                "INSERT INTO fleet_approvals(approval_id, bot_id, tool_name,\n"
                " fingerprint, args_summary, status, decision, created_at,\n"
                " decided_at, decided_by, expires_at)\n"
                "VALUES (?,?,?,?,?,'pending',NULL,?,NULL,NULL,?)",
                (approval_id, bot_id, tool_name, fingerprint,
                 args_summary, now, expires_at))
            self._conn.commit()
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fleet_approvals WHERE approval_id = ?",
                (approval_id,)).fetchone()
        return dict(row) if row else None

    def _transition_approval(self, approval_id: str, target: str, *,
                             decision: str | None, decided_by: str) -> tuple[bool, dict | None]:
        """Guarded pending->target transition; exactly one caller wins."""
        now = _utcnow()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE fleet_approvals\n"
                "   SET status = ?, decision = ?, decided_at = ?, decided_by = ?\n"
                " WHERE approval_id = ? AND status = 'pending'",
                (target, decision, now, decided_by, approval_id))
            self._conn.commit()
            changed = cur.rowcount > 0
        return changed, self.get_approval(approval_id)

    def decide_approval(self, approval_id: str, *, decision: str,
                        decided_by: str = "operator") -> tuple[bool, dict | None]:
        if decision not in ("once", "always", "never"):
            raise ValueError("decision must be once | always | never")
        target = "approved" if decision in ("once", "always") else "denied"
        return self._transition_approval(approval_id, target,
                                         decision=decision,
                                         decided_by=decided_by)

    def expire_approval(self, approval_id: str, *, by: str = "timeout") -> tuple[bool, dict | None]:
        return self._transition_approval(approval_id, "expired",
                                         decision="timeout" if by == "timeout" else by,
                                         decided_by=by)

    def expire_pending_approvals(self, *, by: str = "restart") -> list[dict]:
        """Fail every pending approval closed. Returns the affected rows."""
        now = _utcnow()
        with self._lock:
            rows = self._conn.execute(
                "SELECT approval_id FROM fleet_approvals WHERE status = 'pending'").fetchall()
            ids = [r[0] for r in rows]
            if ids:
                self._conn.execute(
                    f"UPDATE fleet_approvals\n"
                    f"   SET status = 'expired', decision = ?, decided_at = ?, decided_by = ?\n"
                    f" WHERE status = 'pending'",
                    (by, now, by))
                self._conn.commit()
        return [a for a in (self.get_approval(i) for i in ids) if a]

    # ---------------- audit (F1) — fingerprints only, never raw arguments
    def append_audit(self, *, bot_id: str, tool_name: str, fingerprint: str,
                     event: str, decision: str | None = None,
                     outcome: str | None = None,
                     approval_id: str | None = None) -> None:
        if fingerprint and len(fingerprint) > 64:
            fingerprint = fingerprint[:64]
        with self._lock:
            self._conn.execute(
                "INSERT INTO fleet_audit(bot_id, tool_name, fingerprint, event,\n"
                "                        decision, outcome, approval_id, created_at)\n"
                "VALUES (?,?,?,?,?,?,?,?)",
                (bot_id, tool_name, fingerprint, event,
                 decision, outcome, approval_id, _utcnow()))
            self._conn.commit()

    def list_audit(self, bot_id: str, limit: int = 50) -> list[dict]:
        limit = max(1, min(500, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM fleet_audit WHERE bot_id = ?\n"
                " ORDER BY id DESC LIMIT ?", (bot_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ---------------- groups (F3)
    def create_group(self, *, name: str, bot_ids: list[str]) -> dict:
        name = str(name).strip()[:64]
        if not name:
            raise ValueError("name must not be empty")
        bot_ids = [str(b).strip() for b in (bot_ids or []) if str(b).strip()]
        if len(bot_ids) < 2 or len(bot_ids) > 3:
            raise ValueError("a group needs 2 to 3 agents")
        if len(set(bot_ids)) != len(bot_ids):
            raise ValueError("agents in a group must be distinct")
        for bot_id in bot_ids:
            if self.get_bot(bot_id) is None:
                raise ValueError(f"unknown agent {bot_id!r}")
        slug = _slugify(name)
        base, suffix = slug, 0
        while self._group_exists(base):
            suffix += 1
            base = f"{slug}-{suffix}"
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                "INSERT INTO groups(id, name, created_at, updated_at)\n"
                "VALUES (?,?,?,?)", (base, name, now, now))
            for ord_, bot_id in enumerate(bot_ids):
                self._conn.execute(
                    "INSERT INTO group_members(group_id, bot_id, ord) VALUES (?,?,?)",
                    (base, bot_id, ord_))
            self._conn.commit()
        group = self.get_group(base)
        self.append_group_row(base, "system", "notice", {
            "text": f"Group “{name}” created with "
                    f"{', '.join(bot_ids)}.", "icon": "confetti"})
        return group

    def _group_exists(self, group_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone()
        return row is not None

    def get_group(self, group_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
            if row is None:
                return None
            members = self._conn.execute(
                "SELECT b.* FROM group_members m JOIN bots b ON b.id = m.bot_id\n"
                " WHERE m.group_id = ? ORDER BY m.ord ASC",
                (group_id,)).fetchall()
        d = dict(row)
        d["members"] = [_row_to_dict(m) for m in members]
        return d

    def list_groups(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM groups ORDER BY updated_at DESC").fetchall()
        groups = []
        for r in rows:
            group = self.get_group(r["id"])
            if group:
                groups.append(group)
        return groups

    def delete_group(self, group_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM groups WHERE id = ?", (group_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def append_group_row(self, group_id: str, author: str, kind: str,
                         body: dict) -> dict:
        body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        now = _utcnow()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO group_rows(group_id, author, kind, body, created_at)\n"
                "VALUES (?,?,?,?,?)",
                (group_id, author, kind, body_json, now))
            row_id = cur.lastrowid
            self._conn.execute(
                "UPDATE groups SET updated_at = ? WHERE id = ?", (now, group_id))
            self._conn.commit()
        event = {
            "type": "row",
            "group_id": group_id,
            "seq": row_id,
            "author": author,
            "kind": kind,
            "body": body,
            "created_at": now,
        }
        self._publish(event)
        return event

    def list_group_rows(self, group_id: str, after_seq: int = 0,
                        limit: int = 500) -> list[dict]:
        limit = max(1, min(2000, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, author, kind, body, created_at FROM group_rows\n"
                " WHERE group_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
                (group_id, after_seq, limit)).fetchall()
        return [{
            "seq": r["seq"],
            "group_id": group_id,
            "author": r["author"],
            "kind": r["kind"],
            "body": json.loads(r["body"]),
            "created_at": r["created_at"],
        } for r in rows]

    # ---------------- tasks (F2)
    @staticmethod
    def _new_task_id() -> str:
        import secrets
        return "t_" + secrets.token_hex(6)

    def create_task(self, *, title: str, description: str = "",
                    priority: str = "normal",
                    assigned_bot_id: str | None = None,
                    created_by: str = "user",
                    source: str = "user",
                    source_task_id: str | None = None) -> dict:
        title = str(title).strip()[:200]
        if not title:
            raise ValueError("title must not be empty")
        if priority not in ("low", "normal", "high"):
            raise ValueError("priority must be low | normal | high")
        if source not in ("user", "agent", "delegation"):
            source = "user"
        if assigned_bot_id is not None:
            assigned_bot_id = str(assigned_bot_id).strip()[:64] or None
            if assigned_bot_id and self.get_bot(assigned_bot_id) is None:
                raise ValueError(f"unknown agent {assigned_bot_id!r}")
        if source_task_id is not None:
            if self.get_task(source_task_id) is None:
                raise ValueError(f"unknown source task {source_task_id!r}")
        task_id = self._new_task_id()
        now = _utcnow()
        with self._lock:
            next_pos = self._conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM fleet_tasks"
            ).fetchone()[0]
            self._conn.execute(
                "INSERT INTO fleet_tasks(id, title, description, priority, status,\n"
                "                        progress, assigned_bot_id, created_by,\n"
                "                        source, source_task_id, created_at,\n"
                "                        updated_at, completed_at, position)\n"
                "VALUES (?,?,?,?,'pending',0,?,?,?,?,?,?,NULL,?)",
                (task_id, title, str(description)[:4000], priority,
                 assigned_bot_id, created_by, source, source_task_id,
                 now, now, next_pos))
            self._conn.commit()
        self.append_task_event(task_id, actor=created_by, event="created",
                               note=f"assigned to {assigned_bot_id or 'unassigned'}")
        task = self.get_task(task_id)
        return task

    def get_task(self, task_id: str, *, include_deleted: bool = False) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fleet_tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        task = dict(row)
        if task.get("deleted_at") and not include_deleted:
            return None
        return task

    # ---------------- single-level undo (v6)
    @staticmethod
    def _task_snapshot(task: dict) -> str:
        import json as _json
        return _json.dumps({
            "title": task.get("title"),
            "description": task.get("description"),
            "priority": task.get("priority"),
            "status": task.get("status"),
            "progress": task.get("progress"),
            "assigned_bot_id": task.get("assigned_bot_id"),
            "position": task.get("position"),
            "deleted_at": task.get("deleted_at"),
            "completed_at": task.get("completed_at"),
        }, ensure_ascii=False)

    def _stash_prev_state(self, task_id: str) -> None:
        task = self.get_task(task_id, include_deleted=True)
        if task is None:
            return
        with self._lock:
            self._conn.execute(
                "UPDATE fleet_tasks SET prev_state = ? WHERE id = ?",
                (self._task_snapshot(task), task_id))
            self._conn.commit()

    def undo_task(self, task_id: str, *, actor: str) -> dict | None:
        import json as _json
        task = self.get_task(task_id, include_deleted=True)
        if task is None:
            return None
        prev = task.get("prev_state")
        if not prev:
            raise ValueError("nothing to undo")
        try:
            snap = _json.loads(prev)
        except ValueError:
            raise ValueError("nothing to undo")
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                "UPDATE fleet_tasks SET title = ?, description = ?, priority = ?,\n"
                " status = ?, progress = ?, assigned_bot_id = ?, position = ?,\n"
                " deleted_at = ?, completed_at = ?, updated_at = ?, prev_state = NULL\n"
                " WHERE id = ?",
                (snap.get("title"), snap.get("description"), snap.get("priority"),
                 snap.get("status"), snap.get("progress"), snap.get("assigned_bot_id"),
                 snap.get("position"), snap.get("deleted_at"), snap.get("completed_at"),
                 now, task_id))
            self._conn.commit()
        self.append_task_event(task_id, actor=actor, event="undo",
                               note="reverted to previous state")
        return self.get_task(task_id, include_deleted=True)

    def reorder_tasks(self, ids: list[str], *, actor: str) -> list[dict]:
        ids = [str(i) for i in ids][:500]
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM fleet_tasks").fetchall()
            known = {r["id"] for r in rows}
            present = [i for i in ids if i in known]
            rest = [r["id"] for r in self._conn.execute(
                "SELECT id FROM fleet_tasks ORDER BY position ASC, created_at ASC"
            ).fetchall() if r["id"] not in set(present)]
            ordered = present + rest
            # stash BEFORE assigning so every task can be reverted individually
            for tid in ordered:
                cur = self._conn.execute(
                    "SELECT * FROM fleet_tasks WHERE id = ?", (tid,)).fetchone()
                if cur is not None:
                    import json as _json
                    self._conn.execute(
                        "UPDATE fleet_tasks SET prev_state = ? WHERE id = ?",
                        (self._task_snapshot(dict(cur)), tid))
            for pos, tid in enumerate(ordered):
                self._conn.execute(
                    "UPDATE fleet_tasks SET position = ?, updated_at = ? WHERE id = ?",
                    (pos, _utcnow(), tid))
            self._conn.commit()
        if ordered:
            self.append_task_event(ordered[0], actor=actor, event="reordered",
                                   note=f"work order updated ({len(ordered)} tasks)")
        return self.list_tasks()

    def list_tasks(self, *, assigned_bot_id: str | None = None,
                   status: str | None = None,
                   limit: int = 200) -> list[dict]:
        limit = max(1, min(500, int(limit)))
        sql = "SELECT * FROM fleet_tasks"
        clauses: list[str] = ["deleted_at IS NULL"]
        args: list = []
        if assigned_bot_id is not None:
            if assigned_bot_id == "unassigned":
                clauses.append("assigned_bot_id IS NULL")
            else:
                clauses.append("assigned_bot_id = ?")
                args.append(assigned_bot_id)
        if status:
            clauses.append("status = ?")
            args.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        # manual work order is the source of truth (v6)
        sql += " ORDER BY position ASC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def update_task(self, task_id: str, *, actor: str,
                    status: str | None = None,
                    progress: int | None = None,
                    note: str | None = None,
                    fields: dict | None = None) -> dict | None:
        self._stash_prev_state(task_id)
        task = self.get_task(task_id)
        if task is None:
            return None
        now = _utcnow()
        with self._lock:
            if status is not None:
                if status not in ("pending", "in_progress", "completed",
                                  "failed", "cancelled"):
                    raise ValueError("unknown status")
                from_status = task["status"]
                updates = ["status = ?", "updated_at = ?"]
                args = [status, now]
                if status == "completed":
                    updates.append("completed_at = ?")
                    args.append(now)
                    updates.append("progress = 100")
                elif from_status == "completed":
                    updates.append("completed_at = NULL")
                self._conn.execute(
                    f"UPDATE fleet_tasks SET {', '.join(updates)} WHERE id = ?",
                    (*args, task_id))
                self.append_task_event(
                    task_id, actor=actor, event="status",
                    from_status=from_status, to_status=status)
            if progress is not None:
                progress = int(progress)
                if progress < 0 or progress > 100:
                    raise ValueError("progress must be between 0 and 100")
                self._conn.execute(
                    "UPDATE fleet_tasks SET progress = ?, updated_at = ? WHERE id = ?",
                    (progress, now, task_id))
                self.append_task_event(
                    task_id, actor=actor, event="progress",
                    note=f"progress {progress}%")
            if note:
                self.append_task_event(task_id, actor=actor, event="note",
                                       note=str(note)[:500])
            if fields:
                updates, values = [], []
                if "title" in fields:
                    title = str(fields["title"]).strip()[:200]
                    if title:
                        updates.append("title = ?")
                        values.append(title)
                if "description" in fields:
                    updates.append("description = ?")
                    values.append(str(fields["description"])[:4000])
                if "priority" in fields:
                    if fields["priority"] not in ("low", "normal", "high"):
                        raise ValueError("priority must be low | normal | high")
                    updates.append("priority = ?")
                    values.append(fields["priority"])
                if updates:
                    updates.append("updated_at = ?")
                    values.append(now)
                    self._conn.execute(
                        f"UPDATE fleet_tasks SET {', '.join(updates)} WHERE id = ?",
                        (*values, task_id))
                    self.append_task_event(
                        task_id, actor=actor, event="edited",
                        note=", ".join(fields.keys()))
            self._conn.commit()
        return self.get_task(task_id)

    def assign_task(self, task_id: str, assigned_bot_id: str | None,
                    *, actor: str) -> dict | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        assigned_bot_id = (str(assigned_bot_id).strip()[:64]
                           if assigned_bot_id else None)
        if assigned_bot_id and self.get_bot(assigned_bot_id) is None:
            raise ValueError(f"unknown agent {assigned_bot_id!r}")
        self._stash_prev_state(task_id)
        now = _utcnow()
        previous = task["assigned_bot_id"]
        with self._lock:
            self._conn.execute(
                "UPDATE fleet_tasks SET assigned_bot_id = ?, updated_at = ? WHERE id = ?",
                (assigned_bot_id, now, task_id))
            self._conn.commit()
        self.append_task_event(
            task_id, actor=actor, event="reassigned",
            note=f"{previous or 'unassigned'} → {assigned_bot_id or 'unassigned'}")
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        task = self.get_task(task_id, include_deleted=True)
        if task is None or task.get("deleted_at"):
            return False
        self._stash_prev_state(task_id)
        with self._lock:
            self._conn.execute(
                "UPDATE fleet_tasks SET deleted_at = ?, updated_at = ?\n"
                " WHERE id = ?",
                (_utcnow(), _utcnow(), task_id))
            self._conn.commit()
        return True

    def append_task_event(self, task_id: str, *, actor: str, event: str,
                          from_status: str | None = None,
                          to_status: str | None = None,
                          note: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO fleet_task_events(task_id, actor, event,\n"
                " from_status, to_status, note, created_at)\n"
                "VALUES (?,?,?,?,?,?,?)",
                (task_id, actor, event, from_status, to_status,
                 str(note)[:500], _utcnow()))
            self._conn.commit()

    def list_task_events(self, task_id: str, limit: int = 50) -> list[dict]:
        limit = max(1, min(500, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM fleet_task_events WHERE task_id = ?\n"
                " ORDER BY id ASC LIMIT ?", (task_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ---------------- library (F2)
    @staticmethod
    def _new_library_id() -> str:
        import secrets
        return "f_" + secrets.token_hex(6)

    def create_library_entry(self, *, bot_id: str, name: str, mime: str,
                             size: int, sha256: str,
                             task_id: str | None = None,
                             source: str = "agent",
                             file_id: str | None = None) -> dict:
        file_id = file_id or self._new_library_id()
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                "INSERT INTO fleet_library(id, bot_id, task_id, name, mime,\n"
                "                           size, sha256, source, created_at)\n"
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (file_id, bot_id, task_id, name, mime, size, sha256,
                 source, now))
            self._conn.commit()
        return self.get_library_entry(file_id)

    def get_library_entry(self, file_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fleet_library WHERE id = ?", (file_id,)).fetchone()
        return dict(row) if row else None

    def list_library(self, *, bot_id: str | None = None,
                     task_id: str | None = None,
                     limit: int = 500) -> list[dict]:
        limit = max(1, min(1000, int(limit)))
        sql = "SELECT * FROM fleet_library"
        clauses, args = [], []
        if bot_id is not None:
            clauses.append("bot_id = ?")
            args.append(bot_id)
        if task_id is not None:
            clauses.append("task_id = ?")
            args.append(task_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def delete_library_entry(self, file_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fleet_library WHERE id = ?", (file_id,)).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "DELETE FROM fleet_library WHERE id = ?", (file_id,))
            self._conn.commit()
        return dict(row)

    def library_usage(self, bot_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(size), 0) FROM fleet_library WHERE bot_id = ?",
                (bot_id,)).fetchone()
        return int(row[0] or 0)

    # ---------------- routines (F4)
    @staticmethod
    def _new_routine_id() -> str:
        import secrets
        return "r_" + secrets.token_hex(6)

    @staticmethod
    def _utc_iso(dt) -> str:
        return dt.astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"

    def create_routine(self, *, name: str, bot_id: str, prompt: str,
                       cron_expr: str, timezone: str = "UTC",
                       enabled: bool = True,
                       created_by: str = "user") -> dict:
        from .cron import CronError, next_run, parse_cron
        from datetime import datetime, timezone as _tzmod
        from zoneinfo import ZoneInfo

        name = str(name).strip()[:64]
        if not name:
            raise ValueError("name must not be empty")
        prompt = str(prompt).strip()
        if not prompt:
            raise ValueError("prompt must not be empty")
        if self.get_bot(bot_id) is None:
            raise ValueError(f"unknown agent {bot_id!r}")
        try:
            tz = ZoneInfo(str(timezone).strip() or "UTC")
        except Exception:
            raise ValueError(f"unknown timezone {timezone!r}")
        try:
            expr = parse_cron(str(cron_expr))
        except CronError as exc:
            raise ValueError(str(exc))
        now_local = datetime.now(tz)
        first = next_run(expr, now_local)
        routine_id = self._new_routine_id()
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                "INSERT INTO fleet_routines(id, name, bot_id, prompt, cron_expr,\n"
                " timezone, enabled, paused, running, pause_reason, next_run_at,\n"
                " last_run_at, last_status, last_summary, created_by,\n"
                " created_at, updated_at)\n"
                "VALUES (?,?,?,?,?,?,?,0,0,'',?,NULL,NULL,'',?,?,?)",
                (routine_id, name, bot_id, prompt[:8000], expr.raw,
                 str(timezone), int(bool(enabled)), self._utc_iso(first),
                 created_by, now, now))
            self._conn.commit()
        return self.get_routine(routine_id)

    def get_routine(self, routine_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fleet_routines WHERE id = ?",
                (routine_id,)).fetchone()
        return dict(row) if row else None

    def list_routines(self, *, bot_id: str | None = None,
                      limit: int = 200) -> list[dict]:
        limit = max(1, min(500, int(limit)))
        sql = "SELECT * FROM fleet_routines"
        args: list = []
        if bot_id:
            sql += " WHERE bot_id = ?"
            args.append(bot_id)
        sql += " ORDER BY enabled DESC, paused ASC, name ASC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def update_routine(self, routine_id: str, *, fields: dict) -> dict | None:
        from .cron import CronError, next_run, parse_cron
        from datetime import datetime
        from zoneinfo import ZoneInfo

        routine = self.get_routine(routine_id)
        if routine is None:
            return None
        now = _utcnow()
        updates: list[str] = []
        values: list = []
        recompute_next = False
        cron_expr = routine["cron_expr"]
        tz_name = routine["timezone"]

        if "name" in fields:
            name = str(fields["name"]).strip()[:64]
            if not name:
                raise ValueError("name must not be empty")
            updates.append("name = ?")
            values.append(name)
        if "prompt" in fields:
            prompt = str(fields["prompt"]).strip()
            if not prompt:
                raise ValueError("prompt must not be empty")
            updates.append("prompt = ?")
            values.append(prompt[:8000])
        if "cron_expr" in fields:
            try:
                expr = parse_cron(str(fields["cron_expr"]))
            except CronError as exc:
                raise ValueError(str(exc))
            cron_expr = expr.raw
            updates.append("cron_expr = ?")
            values.append(cron_expr)
            recompute_next = True
        if "timezone" in fields:
            try:
                tz = ZoneInfo(str(fields["timezone"]).strip())
            except Exception:
                raise ValueError(f"unknown timezone {fields['timezone']!r}")
            tz_name = str(fields["timezone"]).strip()
            updates.append("timezone = ?")
            values.append(tz_name)
            recompute_next = True
        if "bot_id" in fields:
            bot_id = str(fields["bot_id"]).strip()
            if self.get_bot(bot_id) is None:
                raise ValueError(f"unknown agent {bot_id!r}")
            updates.append("bot_id = ?")
            values.append(bot_id)
        if "enabled" in fields:
            updates.append("enabled = ?")
            values.append(1 if fields["enabled"] else 0)
            recompute_next = True
        if "paused" in fields:
            updates.append("paused = ?")
            values.append(1 if fields["paused"] else 0)
            reason = str(fields.get("pause_reason", ""))[:200]
            updates.append("pause_reason = ?")
            values.append(reason)
        if not updates:
            return routine
        if recompute_next:
            try:
                tz = ZoneInfo(tz_name)
                expr = parse_cron(cron_expr)
                first = next_run(expr, datetime.now(tz))
                updates.append("next_run_at = ?")
                values.append(self._utc_iso(first))
            except Exception as exc:
                raise ValueError(f"could not recompute next run: {exc}")
        updates.append("updated_at = ?")
        values.append(now)
        with self._lock:
            self._conn.execute(
                f"UPDATE fleet_routines SET {', '.join(updates)} WHERE id = ?",
                (*values, routine_id))
            self._conn.commit()
        return self.get_routine(routine_id)

    def delete_routine(self, routine_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM fleet_routines WHERE id = ?", (routine_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def due_routines(self, now_iso: str, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM fleet_routines\n"
                " WHERE enabled = 1 AND paused = 0 AND running = 0\n"
                "   AND next_run_at IS NOT NULL AND next_run_at <= ?\n"
                " ORDER BY next_run_at ASC LIMIT ?",
                (now_iso, limit)).fetchall()
        return [dict(r) for r in rows]

    def claim_routine(self, routine_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE fleet_routines SET running = 1\n"
                " WHERE id = ? AND running = 0", (routine_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def release_routine(self, routine_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE fleet_routines SET running = 0 WHERE id = ?",
                (routine_id,))
            self._conn.commit()

    def create_routine_run(self, routine_id: str, *, scheduled_at: str,
                           task_id: str | None) -> int:
        now = _utcnow()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO fleet_routine_runs(routine_id, task_id,\n"
                " scheduled_at, started_at, finished_at, status, summary,\n"
                " error, created_at)\n"
                "VALUES (?,?,?,?,NULL,'running','','',?)",
                (routine_id, task_id, scheduled_at, now, now))
            self._conn.commit()
        return int(cur.lastrowid)

    def finish_routine_run(self, run_id: int, *, status: str,
                           summary: str = "", error: str = "") -> None:
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                "UPDATE fleet_routine_runs\n"
                "   SET status = ?, summary = ?, error = ?, finished_at = ?\n"
                " WHERE id = ?",
                (status, str(summary)[:2000], str(error)[:1000], now, run_id))
            self._conn.commit()

    def list_routine_runs(self, routine_id: str, limit: int = 20) -> list[dict]:
        limit = max(1, min(200, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM fleet_routine_runs WHERE routine_id = ?\n"
                " ORDER BY id DESC LIMIT ?", (routine_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def record_run_outcome(self, routine_id: str, *, next_run_at: str | None,
                           status: str, summary: str) -> None:
        now = _utcnow()
        updates = ["last_run_at = ?", "last_status = ?", "last_summary = ?",
                   "updated_at = ?"]
        values = [now, status, str(summary)[:2000], now]
        if next_run_at is not None:
            updates.append("next_run_at = ?")
            values.append(next_run_at)
        with self._lock:
            self._conn.execute(
                f"UPDATE fleet_routines SET {', '.join(updates)} WHERE id = ?",
                (*values, routine_id))
            self._conn.commit()

    def mark_run_awaiting_approval(self, run_id: int) -> None:
        """Flip a live routine run to awaiting_approval (idempotent)."""
        with self._lock:
            self._conn.execute(
                "UPDATE fleet_routine_runs SET status = 'awaiting_approval'\n"
                " WHERE id = ? AND status = 'running'", (run_id,))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


_slug_token = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    slug = _slug_token.sub("-", name.lower().strip()).strip("-")
    if not slug:
        slug = "bot"
    return slug[:40]
