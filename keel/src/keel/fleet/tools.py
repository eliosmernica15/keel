"""keel.fleet.tools — Fleet-owned tool handlers (F3).

Wraps RealTools with the Fleet delegation tool. `send_to_bot` runs a
synchronous, bounded inline turn for the receiving agent:

- depth cap: a chain may hold at most two delegating ancestors;
  delegating past it, or delegating to an agent already in the chain
  (or to itself), is refused;
- the receiver runs with its own provider, model, notes, history and
  permission broker — nothing about the caller's authority transfers;
- the receiver's reply is returned to the caller as the tool result.
"""

from __future__ import annotations

import base64
import binascii
import json

from ..runner import RealTools
from .approvals import fingerprint
from . import library as library_fs
from . import asks as _asks
from . import shells as _shells

_MAX_DELEGATION_DEPTH = 2


def _input_summary(tool_input) -> str:
    try:
        text = json.dumps(tool_input, ensure_ascii=False,
                          separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(tool_input)
    return text[:180]


def _result_excerpt(result) -> str:
    # RealTools returns (content, payload) tuples or raw strings; meta-rich
    # returns land in content too
    if isinstance(result, tuple):
        content = result[0] if result else ""
    elif isinstance(result, dict):
        content = result.get("content", str(result))
    else:
        content = str(result)
    if not isinstance(content, str):
        content = str(content)
    return content[:156]


class FleetTools(RealTools):
    """RealTools + delegation, bound to one bot and one chain."""

    def __init__(self, store, bot: dict, chain: tuple = (),
                 *, timeout_s: float | None = None,
                 row_sink=None):
        super().__init__()
        self.store = store
        self.bot = bot
        self.chain = tuple(chain or ())
        self.timeout_s = timeout_s
        self.row_sink = row_sink
        # live tools publish step rows as they execute; turn_core skips its
        # post-hoc step replay when this flag is set (no duplicates)
        self.live_steps = True
        self.last_delegation = None
        # background shell handles owned by this bot instance — nothing here
        # ever blocks the process event loop; detached work is reported via
        # notice rows and the shells registry

    def _notice(self, text: str, *, level: str = "info",
                icon: str | None = None) -> None:
        body = {"text": text, "level": level}
        if icon:
            body["icon"] = icon
        sink = getattr(self, "row_sink", None)
        if sink is not None:
            try:
                sink("notice", body)
                return
            except Exception:
                pass
        self.store.append_row(self.bot["id"], "notice", body)

    # ---------------- live step emission (streamed to the UI mid-turn)
    def _emit_step(self, body: dict) -> None:
        sink = getattr(self, "row_sink", None)
        if sink is not None:
            try:
                sink("step", body)
                return
            except Exception:
                pass
        try:
            self.store.append_row(self.bot["id"], "step", body)
        except Exception:
            pass  # steps are best-effort; the turn's safety never depends on them

    def _step_in(self, name: str, tool_input: dict) -> dict:
        detail = _input_summary(tool_input or {})
        if name == "send_to_bot":
            slug = str((tool_input or {}).get("bot_slug", "")).strip()
            detail = f"→ {slug}: {detail}"[:180]
        return {"name": name, "status": "running", "detail": detail}

    @staticmethod
    def _result_failed(result) -> bool:
        """True when the tool outcome is itself an error."""
        if isinstance(result, tuple) and len(result) >= 2:
            meta = result[1]
            if isinstance(meta, dict) and (
                    meta.get("ok") is False or bool(meta.get("error"))):
                return True
            content = result[0]
        else:
            content = result
        return isinstance(content, str) and content.startswith("<tool_use_error>")

    def _step_out(self, name: str, tool_input: dict, result) -> dict:
        failed = self._result_failed(result)
        body = {"name": name,
                "status": "error" if failed else "done",
                "detail": _result_excerpt(result)}
        if name == "send_to_bot" and getattr(self, "last_delegation", None):
            d = self.last_delegation
            body["delegated"] = {
                "to": d.get("to"), "to_id": d.get("to_id"),
                "reply": (d.get("reply") or "")[:4000],
                "ok": bool(d.get("ok")), "task_id": d.get("task_id"),
            }
        return body

    def invoke(self, name: str, tool_input: dict):
        tool_input = tool_input or {}
        self.step_count = getattr(self, "step_count", 0) + 1
        self._emit_step(self._step_in(name, tool_input))
        try:
            result = self._dispatch(name, tool_input)
        except Exception as exc:
            self._emit_step({"name": name, "status": "error",
                             "detail": str(exc)[:156]})
            raise
        self._emit_step(self._step_out(name, tool_input, result))
        return result

    def _dispatch(self, name: str, tool_input: dict):
        if name == "send_to_bot":
            return self._delegate(tool_input)
        if name == "create_task":
            return self._create_task(tool_input)
        if name == "update_task":
            return self._update_task(tool_input)
        if name == "list_tasks":
            return self._list_tasks(tool_input)
        if name == "save_file":
            return self._save_file(tool_input)
        if name == "ask_user":
            return self._ask_user(tool_input)
        if name == "run_shell":
            if tool_input.get("background"):
                return self._background_shell(tool_input)
        return super().invoke(name, tool_input)

    # ------------------------------------------------------------------
    def _delegate(self, tool_input: dict):
        slug = str(tool_input.get("bot_slug", "")).strip()
        message = str(tool_input.get("message", "")).strip()
        task_id = str(tool_input.get("task_id", "") or "").strip() or None

        def _audit(outcome: str) -> None:
            try:
                self.store.append_audit(
                    bot_id=self.bot["id"], tool_name="send_to_bot",
                    fingerprint=fingerprint(tool_input),
                    event="outcome", decision="delegate", outcome=outcome)
            except Exception:
                pass  # audit never breaks a turn

        def _refuse(error: str, reason: str):
            _audit("refused")
            self.last_delegation = {"to": slug, "to_id": slug,
                                    "reply": reason, "ok": False,
                                    "task_id": task_id}
            return (f"<tool_use_error>{reason}</tool_use_error>"
                    ), {"ok": False, "error": error,
                        "delegated_to": slug, "detail": reason}

        if not slug:
            return _refuse("empty_slug",
                           "send_to_bot needs a non-empty bot_slug")
        if not message:
            return _refuse("empty_message",
                           "send_to_bot needs a non-empty message")
        if len(self.chain) >= _MAX_DELEGATION_DEPTH:
            return _refuse("depth_limit",
                           f"delegation depth limit reached "
                           f"({_MAX_DELEGATION_DEPTH}): {self.bot['id']} "
                           f"may not delegate further")
        if slug == self.bot["id"]:
            return _refuse("self_delegation",
                           f"{slug!r} cannot send_to_bot itself")
        if slug in self.chain:
            return _refuse("circular_delegation",
                           f"circular delegation refused: {slug!r} is "
                           f"already in the delegation chain")
        if task_id and self.store.get_task(task_id) is None:
            return _refuse("task_not_found",
                           f"unknown task {task_id!r}; list your tasks to confirm the id")
        if slug.strip().lower() == "user":
            return _refuse("self_delegation",
                           "send_to_bot targets fleet agents, not the user")

        target = self.store.get_bot(slug)
        if target is None:
            return _refuse("bot_not_found",
                           f"no agent named {slug!r} in the fleet; "
                           f"list agents to confirm the slug")

        if task_id:
            self.store.append_task_event(
                task_id, actor=self.bot["id"], event="delegated",
                note=f"→ {slug}: {message[:180]}")
        from .delegation import run_delegated_turn
        result = run_delegated_turn(
            self.store, self.bot, target, message,
            chain=self.chain + (self.bot["id"],),
            timeout_s=self.timeout_s,
            task_id=task_id)
        self.last_delegation = {
            "to": target.get("name") or slug,
            "to_id": slug,
            "reply": (result.get("assistant_text") or result.get("error") or ""),
            "ok": bool(result.get("ok")),
            "task_id": task_id,
        }
        _audit("executed" if result.get("ok") else
               "refused" if result.get("error") == "agent_busy" else
               "error")
        if result.get("ok"):
            inline = result.get("assistant_text") or "(no reply)"
            return inline, {"ok": True, "delegated_to": slug,
                            "from_bot": self.bot["id"],
                            "task_id": task_id,
                            "denials": result.get("permission_denials", 0),
                            "terminal_reason": result.get("terminal_reason")}
        reason = result.get("error") or "delegation failed"
        return (f"<tool_use_error>{reason}</tool_use_error>"
                ), {"ok": False, "error": "delegation_failed",
                    "delegated_to": slug,
                    "task_id": task_id,
                    "detail": reason}

    # ---------------- operator questions (ask_user)
    def _ask_user(self, tool_input: dict):
        question = str(tool_input.get("question", "")).strip()
        if not question:
            return ("<tool_use_error>ask_user needs a non-empty question"
                    "</tool_use_error>"), {"ok": False, "error": "empty_question"}
        options = tool_input.get("options") or []
        if not isinstance(options, list):
            options = [options]
        options = [str(o).strip() for o in options if str(o).strip()][:6]
        ask_id = _asks.broker.ask(self.store, self.bot, question, options)
        answer = _asks.broker.wait(ask_id, timeout_s=300)
        if answer is None:
            try:
                self.store.append_row(self.bot["id"], "ask", {
                    "ask_id": ask_id,
                    "question": question,
                    "options": options or [],
                    "status": "timeout",
                    "icon": "question",
                })
            except Exception:
                pass
            self._emit_step({"name": "ask_user", "status": "error",
                             "detail": "question timed out — no answer"})
            return ("<tool_use_error>operator did not answer the question in "
                    "time (5 min). Proceed without operator input."
                    "</tool_use_error>"), {"ok": False, "error": "timeout",
                                           "ask_id": ask_id}
        try:
            self.store.append_row(self.bot["id"], "ask", {
                "ask_id": ask_id,
                "question": question,
                "options": options or [],
                "status": "answered",
                "answer": answer,
                "icon": "question",
            })
        except Exception:
            pass
        return (f"operator answered: {answer}",
                {"ok": True, "ask_id": ask_id, "answer": answer})

    # ---------------- background shells (run_shell + background=true)
    def _background_shell(self, tool_input: dict):
        command = str(tool_input.get("command", "")).strip()
        if not command:
            return ("<tool_use_error>background shell needs a command"
                    "</tool_use_error>"), {"ok": False, "error": "empty_command"}
        shell = str(tool_input.get("shell", "posix")).strip().lower()
        if shell not in ("posix", "powershell", "cmd"):
            shell = "posix"
        try:
            entry = _shells.start(self.store, self.bot, command, shell)
        except ValueError as exc:
            return (f"<tool_use_error>{exc}</tool_use_error>"), \
                   {"ok": False, "error": "capacity", "detail": str(exc)}
        except OSError as exc:
            return (f"<tool_use_error>failed to start shell: {exc}"
                    "</tool_use_error>"), {"ok": False, "error": "spawn_failed",
                                           "detail": str(exc)}
        try:
            self.store.append_row(self.bot["id"], "notice", {
                "text": (f"Background shell {entry.handle} started detached "
                         f"(pid {entry.pid}): {command[:160]}"),
                "level": "info",
                "icon": "terminal",
            })
        except Exception:
            pass
        running = _shells.running_count(self.bot["id"])
        return (f"background shell {entry.handle} started (pid {entry.pid}, "
                f"{running} total running) — you will be notified when it "
                f"finishes; poll its output at any time",
                {"ok": True, "handle": entry.handle, "pid": entry.pid,
                 "running": running})
    def _resolve_assignee(self, assignee):
        raw = str(assignee or "").strip().lower()
        if raw in ("", "me", "self"):
            return self.bot["id"]
        if raw in ("unassigned", "none", "nobody"):
            return None
        candidate = self.store.get_bot(raw)
        if candidate is None:
            from .service import _slugify
            candidate = self.store.get_bot(_slugify(raw))
        if candidate is not None:
            return candidate["id"]
        return raw

    def _create_task(self, tool_input: dict):
        title = str(tool_input.get("title", "")).strip()
        if not title:
            return ("<tool_use_error>create_task needs a non-empty title"
                    "</tool_use_error>"), {"ok": False, "error": "empty_title"}
        priority = str(tool_input.get("priority") or "normal").strip().lower()
        if priority not in ("low", "normal", "high"):
            return ("<tool_use_error>priority must be low | normal | high"
                    "</tool_use_error>"), {"ok": False, "error": "bad_priority"}
        description = str(tool_input.get("description") or "")
        target = self._resolve_assignee(tool_input.get("assignee"))
        if target is not None and self.store.get_bot(target) is None:
            return (f"<tool_use_error>unknown agent {target!r} in the fleet"
                    f"</tool_use_error>"), {"ok": False, "error": "bot_not_found"}
        try:
            task = self.store.create_task(
                title=title, description=description, priority=priority,
                assigned_bot_id=target,
                created_by=self.bot["id"], source="agent")
        except ValueError as exc:
            return (f"<tool_use_error>{exc}</tool_use_error>"
                    ), {"ok": False, "error": "invalid_task"}
        if target and target != self.bot["id"]:
            self.store.append_row(target, "notice", {
                "text": f"Task assigned by {self.bot.get('name') or self.bot['id']}: "
                        f"“{task['title']}” (id {task['id']})",
                "level": "info",
                "icon": "task",
            })
        else:
            self._notice(f"Task created: “{task['title']}” (id {task['id']})",
                         icon="task")
        return (f"task {task['id']} created and assigned to "
                f"{target or 'unassigned'}"), {
            "ok": True, "task_id": task["id"],
            "assigned_to": target,
            "status": task["status"],
            "priority": priority,
        }

    def _update_task(self, tool_input: dict):
        task_id = str(tool_input.get("task_id", "")).strip()
        if not task_id:
            return ("<tool_use_error>update_task needs a task_id"
                    "</tool_use_error>"), {"ok": False, "error": "empty_task_id"}
        task = self.store.get_task(task_id)
        if task is None:
            return (f"<tool_use_error>unknown task {task_id!r}"
                    f"</tool_use_error>"), {"ok": False, "error": "task_not_found"}
        owner = self.bot["id"]
        if task["assigned_bot_id"] not in (owner, None) \
                and task["created_by"] != owner:
            return (f"<tool_use_error>task {task_id!r} is assigned to "
                    f"{task['assigned_bot_id']}, not you; only its assignee "
                    f"or creator can change it</tool_use_error>"
                    ), {"ok": False, "error": "not_your_task"}
        status = tool_input.get("status")
        progress = tool_input.get("progress")
        note = tool_input.get("note")
        if status is None and progress is None and not note:
            return ("<tool_use_error>nothing to update: pass status, progress "
                    "or note</tool_use_error>"
                    ), {"ok": False, "error": "no_change"}
        try:
            updated = self.store.update_task(
                task_id, actor=owner,
                status=(str(status).strip().lower()
                        if status is not None else None),
                progress=(int(progress) if progress is not None else None),
                note=(str(note) if note else None))
        except (ValueError, TypeError) as exc:
            return (f"<tool_use_error>{exc}</tool_use_error>"
                    ), {"ok": False, "error": "invalid_update"}
        if status:
            self._notice(f"Task {task_id}: {updated['status']}", icon="task")
        return (f"task {task_id} updated: status={updated['status']} "
                f"progress={updated['progress']}%"), {
            "ok": True, "task_id": task_id,
            "status": updated["status"],
            "progress": updated["progress"],
        }

    def _list_tasks(self, tool_input: dict):
        assigned = str(tool_input.get("assigned_to") or "me").strip().lower()
        if assigned in ("me", "self"):
            assigned_bot_id = self.bot["id"]
        elif assigned in ("all", "*"):
            assigned_bot_id = None
        else:
            assigned_bot_id = self._resolve_assignee(assigned)
        status = tool_input.get("status")
        if status:
            status = str(status).strip().lower()
            if status not in ("pending", "in_progress", "completed",
                              "failed", "cancelled"):
                return ("<tool_use_error>unknown status filter"
                        f" {status!r}</tool_use_error>"
                        ), {"ok": False, "error": "bad_status"}
        try:
            limit = int(tool_input.get("limit") or 10)
        except (TypeError, ValueError):
            limit = 10
        tasks = self.store.list_tasks(assigned_bot_id=assigned_bot_id,
                                      status=status,
                                      limit=max(1, min(25, limit)))
        if not tasks:
            return "no tasks match", {"ok": True, "count": 0, "tasks": []}
        lines = []
        for t in tasks:
            owner = t["assigned_bot_id"] or "unassigned"
            lines.append(
                f"- {t['id']}  [{t['status']}]  ({t['priority']})  "
                f"{t['title'][:80]}  · owner={owner}  · {t['progress']}%")
        return "\n".join(lines), {
            "ok": True, "count": len(tasks),
            "tasks": [{"id": t["id"], "title": t["title"],
                       "status": t["status"], "priority": t["priority"],
                       "progress": t["progress"],
                       "assigned_to": t["assigned_bot_id"]} for t in tasks],
        }

    # ---------------- F2: library ----------------
    def _save_file(self, tool_input: dict):
        from . import library as library_fs
        name = str(tool_input.get("filename", "")).strip()
        try:
            name = library_fs.validate_filename(name)
        except ValueError as exc:
            return (f"<tool_use_error>{exc}</tool_use_error>"
                    ), {"ok": False, "error": "bad_filename"}
        task_id = str(tool_input.get("task_id") or "").strip() or None
        if task_id and self.store.get_task(task_id) is None:
            return (f"<tool_use_error>unknown task {task_id!r}"
                    f"</tool_use_error>"), {"ok": False, "error": "task_not_found"}
        content_raw = tool_input.get("content")
        if content_raw is None:
            return ("<tool_use_error>save_file needs content"
                    "</tool_use_error>"), {"ok": False, "error": "no_content"}
        encoding = str(tool_input.get("encoding") or "utf8").lower()
        if encoding == "base64":
            import base64
            try:
                data = base64.b64decode(str(content_raw), validate=True)
            except Exception:
                return ("<tool_use_error>content is not valid base64"
                        "</tool_use_error>"), {"ok": False, "error": "bad_base64"}
        elif encoding == "utf8":
            data = str(content_raw).encode("utf-8")
        else:
            return ("<tool_use_error>encoding must be utf8 or base64"
                    "</tool_use_error>"), {"ok": False, "error": "bad_encoding"}
        if len(data) > library_fs.MAX_FILE_BYTES:
            return (f"<tool_use_error>file too large: {len(data)} bytes "
                    f"(max {library_fs.MAX_FILE_BYTES})</tool_use_error>"
                    ), {"ok": False, "error": "file_too_large"}
        try:
            library_fs.check_quota(self.store.list_library(
                bot_id=self.bot["id"], limit=10000), len(data))
        except ValueError as exc:
            return (f"<tool_use_error>{exc}</tool_use_error>"
                    ), {"ok": False, "error": "quota_exceeded"}
        import hashlib
        import secrets
        sha = hashlib.sha256(data).hexdigest()
        file_id = "f_" + secrets.token_hex(6)
        try:
            library_fs.write_bytes(self.bot["id"], file_id, data)
        except OSError as exc:
            return (f"<tool_use_error>could not write the file: {exc}"
                    f"</tool_use_error>"
                    ), {"ok": False, "error": "write_failed"}
        file_row = self.store.create_library_entry(
            bot_id=self.bot["id"], name=name,
            mime=(str(tool_input["mime"])[:120] if tool_input.get("mime")
                  else library_fs.guess_mime(name)),
            size=len(data), sha256=sha, task_id=task_id, source="agent",
            file_id=file_id)
        if task_id:
            self.store.append_task_event(
                task_id, actor=self.bot["id"], event="note",
                note=f"saved {name} to Library (file {file_row['id']})")
        self._notice(f"Saved {name} to the Library "
                     f"({len(data)} bytes, id {file_row['id']})",
                     icon="file")
        return (f"saved {name} ({len(data)} bytes, file id {file_id})"
                ), {"ok": True, "file_id": file_id, "name": name,
                    "size": len(data), "mime": file_row["mime"],
                    "task_id": task_id}
