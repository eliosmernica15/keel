"""OpenCode-compatible REST/stream surface for Keel.

Scope: tracer bullet. This module implements the smallest surface that lets
an OpenCode-shaped client create a session, send a prompt, and receive a
reply with tool-call events. It is NOT a port of the OpenCode backend, and
it deliberately does NOT call any LLM provider: replies come from a simple
local loop so the contract can be exercised offline, deterministically,
and in tests. What it does:

- POST /api/v2/sessions
    creates a session visible to the compatibility layer
- GET  /api/v2/sessions
    lists sessions (id, title, counts, pendingApproval)
- GET  /api/v2/sessions/:id
    session summary
- DELETE /api/v2/sessions/:id
    removes the session, its messages, events and pending approval
- POST /api/v2/sessions/:id/messages
    runs the prompt through the local loop and stores the result
- GET  /api/v2/sessions/:id/messages
    stored message history
- GET  /api/v2/sessions/:id/events
    Server-sent events replay; accepts ?since=<unix-seconds>
- POST /api/v2/sessions/:id/approve
    acknowledges a pending permission request (404 for unknown session)
- POST /api/v2/sessions/:id/reject
    rejects a pending permission request (404 for unknown session)

What it does NOT do (deliberately):

- Does not stream tokens from a real model; replies are local and
  deterministic. The Keel runtime has provider plumbing (providers/,
  runner.py) but this surface does not use it yet.
- Does not implement arbitrary OpenCode event types
- Does not mutate or fork upstream OpenCode code
- Does not introduce new tooling not already in the Keel runtime
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# Compat store — held in-process; sessions do not persist across restarts.
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_MESSAGES: Dict[str, List[Dict[str, Any]]] = {}
_EVENTS: Dict[str, List[Dict[str, Any]]] = {}
_APPROVALS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.RLock()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time()))


def _session(sid: str) -> Dict[str, Any]:
    with _LOCK:
        return _SESSIONS.get(sid, {})


def _messages(sid: str) -> List[Dict[str, Any]]:
    with _LOCK:
        return _MESSAGES.get(sid, [])


def _events(sid: str) -> List[Dict[str, Any]]:
    with _LOCK:
        return _EVENTS.get(sid, [])


def _approval(sid: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        return _APPROVALS.get(sid)


def create_session(title: str) -> Dict[str, Any]:
    sid = secrets.token_urlsafe(12)
    now = _now_iso()
    with _LOCK:
        _SESSIONS[sid] = {"id": sid, "title": title or "Untitled", "createdAt": now, "updatedAt": now}
        _MESSAGES[sid] = []
        _EVENTS[sid] = []
    return _SESSIONS[sid]


def get_session(sid: str) -> Optional[Dict[str, Any]]:
    return _SESSIONS.get(sid)


def message_history(sid: str) -> List[Dict[str, Any]]:
    return _messages(sid)


def session_events(sid: str, since: float) -> List[Dict[str, Any]]:
    return [e for e in _events(sid) if e.get("ts", 0) >= since]


def _emit(sid: str, event: Dict[str, Any]) -> None:
    with _LOCK:
        event = {"ts": time.time(), **event}
        _EVENTS[sid].append(event)
        # trim
        if len(_EVENTS[sid]) > 1000:
            _EVENTS[sid] = _EVENTS[sid][-1000:]


def _fake_agent_loop(prompt: str, workdir: Optional[str]) -> Tuple[str, List[Dict[str, Any]]]:
    """Minimal agent loop: returns a text response + tool-call log."""
    events: List[Dict[str, Any]] = []
    ws = workdir or "."
    _emit_text = f"Running against {ws} — reading files and listing the workspace."
    events.append({"type": "text", "text": _emit_text})
    events.append({"type": "tool", "tool": "read_file", "args": {"path": "README.md"}, "result": "(read)"})
    events.append({"type": "tool", "tool": "ls", "args": {"path": "."}, "result": "(listed)"})
    events.append({"type": "done"})
    reply = f"I inspected the workspace at {ws}. README.md found; workspace listed. (Keel compat tracer)"
    return reply, events


def run_message(sid: str, text: str, workdir: Optional[str] = None) -> Dict[str, Any]:
    session = _SESSIONS.get(sid)
    if not session:
        raise ValueError("session not found")
    with _LOCK:
        _MESSAGES[sid].append({"role": "user", "content": text, "ts": _now_iso()})
    _emit(sid, {"type": "user", "text": text})
    reply, tool_events = _fake_agent_loop(text, workdir)
    with _LOCK:
        _MESSAGES[sid].append({"role": "assistant", "content": reply, "ts": _now_iso()})
    _emit(sid, {"type": "assistant", "text": reply, "tools": tool_events})
    _emit(sid, {"type": "done"})
    session["updatedAt"] = _now_iso()
    return {"ok": True, "reply": reply}


def request_approval(sid: str, tool_name: str, args: Dict[str, Any], reason: str) -> Dict[str, Any]:
    with _LOCK:
        _APPROVALS[sid] = {"tool": tool_name, "args": args, "reason": reason, "ts": _now_iso()}
    _emit(sid, {"type": "approval_required", "tool": tool_name, "reason": reason})
    return _APPROVALS[sid]


def approve(sid: str) -> Optional[bool]:
    with _LOCK:
        if sid not in _SESSIONS:
            return None
        _APPROVALS.pop(sid, None)
    _emit(sid, {"type": "approval_granted"})
    return True


def reject(sid: str) -> Optional[bool]:
    with _LOCK:
        if sid not in _SESSIONS:
            return None
        _APPROVALS.pop(sid, None)
    _emit(sid, {"type": "approval_rejected"})
    return True


def delete_session(sid: str) -> bool:
    with _LOCK:
        if sid not in _SESSIONS:
            return False
        del _SESSIONS[sid]
        _MESSAGES.pop(sid, None)
        _EVENTS.pop(sid, None)
        _APPROVALS.pop(sid, None)
    return True


def stream(sid: str, last_event_id: int = 0) -> List[Dict[str, Any]]:
    return _events(sid)[last_event_id:]


def session_summary(sid: str) -> Dict[str, Any]:
    session = _SESSIONS.get(sid)
    if not session:
        return {}
    return {
        "id": session["id"],
        "title": session["title"],
        "createdAt": session["createdAt"],
        "updatedAt": session["updatedAt"],
        "messageCount": len(_messages(sid)),
        "pendingApproval": bool(_approval(sid)),
    }


def sessions_list() -> List[Dict[str, Any]]:
    with _LOCK:
        return [session_summary(sid) for sid in list(_SESSIONS.keys())]
