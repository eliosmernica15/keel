"""OpenCode-compatible REST/stream surface for Keel — backed by the real runtime.

This module is a thin compatibility shim over Keel's actual agent stack:

- sessions  = fleet bots (`fleet.db`, kind="session")
- messages  = persisted rows (kind="message"), user + assistant
- runs      = `fleet.provider_turn.start_provider_turn` on a worker thread,
              executing through `session.Session` with the real tool registry,
              permission/approval broker, compaction and transcript writer
- streaming = ephemeral `{"type": "stream", ...}` fan-out frames + persisted
              row events, both replayed via `events?since=<seq>`
- approvals = the F1 approval broker (once / always / reject)

It does NOT contain an agent loop, does NOT fake provider responses, and does
NOT fall back to a scripted fake when no provider is configured: the turn
simply ends with `terminal_reason="not_configured"` and a notice row explains
what to do. The deterministic fake transport exists only in tests, injected
at the network edge (`build_adapter(..., transport=...)`).

Scope: this remains a compatibility shim, not an OpenCode port. What is
implemented: the /api/v2/sessions* surface. What is deliberately absent:
OpenCode's schema layer, plugins, PTY/computer-use, and full event taxonomy.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class SessionNotFound(Exception):
    """Raised when a v2 session id does not name a live compat session."""


# ---------------- plumbing
def _store():
    from .fleet import routes as _routes
    return _routes.store()


def _bot_or_raise(sid: str) -> dict:
    bot = _store().get_bot(sid)
    if bot is None or bot.get("kind") != "session":
        raise SessionNotFound(f"session {sid!r} not found")
    return bot


def _session_dict(bot: dict, *, message_count: int = 0,
                  pending_approval: bool = False) -> Dict[str, Any]:
    try:
        totals = _store().usage_totals(bot["id"])
    except Exception:
        totals = {"records": 0, "input_tokens": 0, "output_tokens": 0,
                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                  "thinking_tokens": 0, "cost_usd": 0.0,
                  "cost_basis": "unknown (no provider-reported cost)"}
    return {
        "id": bot["id"],
        "title": bot["name"],
        "createdAt": bot["created_at"],
        "updatedAt": bot["updated_at"],
        "engine": bot["engine"],
        "provider": bot["provider"],
        "model": bot["model"],
        "kind": bot["kind"],
        "messageCount": message_count,
        "pendingApproval": pending_approval,
        "usage": totals,
    }


def _pending_approvals(sid: str) -> List[Dict[str, Any]]:
    return _store().list_pending_approvals(sid)


def _message_rows(sid: str) -> List[Dict[str, Any]]:
    return _store().list_rows(sid, 0, 10_000)


def _row_to_v2(event: Dict[str, Any]) -> Dict[str, Any]:
    kind = event["kind"]
    body = event.get("body") or {}
    seq = event["seq"]
    ts = event["created_at"]
    sid = event["bot_id"]
    if kind == "message":
        role = body.get("role") or "assistant"
        out = {"type": role, "sessionID": sid, "text": body.get("content", ""),
               "seq": seq, "ts": ts}
        if body.get("engine"):
            out["engine"] = body["engine"]
        if body.get("model"):
            out["model"] = body["model"]
        if body.get("workdir"):
            out["workdir"] = body["workdir"]
        return out
    if kind == "step":
        return {"type": "tool", "sessionID": sid,
                "name": body.get("name"), "status": body.get("status"),
                "detail": body.get("detail"), "seq": seq, "ts": ts}
    if kind == "notice":
        return {"type": "notice", "sessionID": sid,
                "level": body.get("level"), "text": body.get("text"),
                "seq": seq, "ts": ts}
    if kind == "turn_end":
        return {"type": "done", "sessionID": sid,
                "terminal_reason": body.get("terminal_reason"),
                "duration_ms": body.get("duration_ms"),
                "num_turns": body.get("num_turns"),
                "usage": body.get("usage"),
                "seq": seq, "ts": ts}
    if kind == "usage":
        return {"type": "usage", "sessionID": sid,
                "provider": body.get("provider"),
                "model": body.get("model"),
                "input_tokens": body.get("input_tokens", 0),
                "output_tokens": body.get("output_tokens", 0),
                "cache_read_input_tokens": body.get("cache_read_input_tokens", 0),
                "cache_creation_input_tokens": body.get("cache_creation_input_tokens", 0),
                "thinking_tokens": body.get("thinking_tokens", 0),
                "cost_basis": body.get("cost_basis", "unknown"),
                "seq": seq, "ts": ts}
    if kind == "approval":
        return {"type": "approval", "sessionID": sid,
                "approval_id": body.get("approval_id"),
                "tool_name": body.get("tool_name"),
                "status": body.get("status"),
                "decision": body.get("decision"),
                "summary": body.get("summary"),
                "explanation": body.get("explanation"),
                "expires_at": body.get("expires_at"),
                "seq": seq, "ts": ts}
    return {"type": kind, "sessionID": sid, "seq": seq, "ts": ts, **body}


def _stream_frame_to_v2(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ephemeral token frame -> v2 token event."""
    if event.get("type") != "stream" or not event.get("delta"):
        return None
    return {"type": "token", "sessionID": event.get("bot_id"),
            "text": event["delta"], "seq": None, "ts": None}


def _live_row_to_v2(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Persisted row arriving on the live fan-out -> v2 event."""
    if event.get("type") != "row" or not event.get("kind"):
        return None
    return _row_to_v2(event)


def live_event_to_v2(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if event.get("type") == "stream":
        return _stream_frame_to_v2(event)
    if event.get("type") == "row":
        return _live_row_to_v2(event)
    return None


# ---------------- public API (used by webapp.py)
def create_session(title: str) -> Dict[str, Any]:
    import secrets
    bot = _store().create_bot(name=(title or "Untitled").strip()[:64] or "Untitled",
                              engine="provider",
                              notes="",
                              bot_id=secrets.token_urlsafe(9),
                              kind="session")
    return _session_dict(bot)


def get_session(sid: str) -> Optional[Dict[str, Any]]:
    try:
        bot = _bot_or_raise(sid)
    except SessionNotFound:
        return None
    rows = _message_rows(sid)
    return _session_dict(bot,
                         message_count=len([r for r in rows if r["kind"] == "message"]),
                         pending_approval=bool(_pending_approvals(sid)))


def sessions_list() -> List[Dict[str, Any]]:
    out = []
    for bot in _store().list_bots(kind="session"):
        rows = _message_rows(bot["id"])
        out.append(_session_dict(
            bot,
            message_count=len([r for r in rows if r["kind"] == "message"]),
            pending_approval=bool(_pending_approvals(bot["id"]))))
    return out


def message_history(sid: str) -> List[Dict[str, Any]]:
    try:
        _bot_or_raise(sid)
    except SessionNotFound:
        return []
    messages = []
    for row in _message_rows(sid):
        if row["kind"] != "message":
            continue
        body = row.get("body") or {}
        messages.append({
            "role": body.get("role") or "assistant",
            "content": body.get("content", ""),
            "ts": row["created_at"],
            "engine": body.get("engine"),
            "model": body.get("model"),
        })
    return messages


def run_message(sid: str, text: str, workdir: Optional[str] = None,
                permission_mode: Optional[str] = None,
                images: Optional[list] = None) -> Dict[str, Any]:
    """Append the user message and start the provider-backed turn.

    Returns immediately (202 semantics); the turn streams into the fan-out
    and persists rows. Raises ValueError for unknown sessions.
    """
    try:
        bot = _bot_or_raise(sid)
    except SessionNotFound:
        raise ValueError("session not found") from None

    store = _store()
    row = store.append_row(sid, "message",
                           {"role": "user", "content": text,
                            "workdir": workdir,
                            "images": len(images or [])})

    from .fleet import provider_turn
    lock, started = provider_turn.start_provider_turn(
        store, bot, text, permission_mode=permission_mode, workdir=workdir,
        images=images)
    if not started:
        return {"ok": False, "error": "a turn is already in progress for this session",
                "terminal_reason": "busy", "runId": None}

    return {"ok": True, "runId": f"msg-{row['seq']}",
            "assistant_text": "", "terminal_reason": "started"}


def delete_session(sid: str) -> bool:
    from .fleet import turn_core
    try:
        _bot_or_raise(sid)
    except SessionNotFound:
        return False
    turn_core.cancel_active_turn(sid)
    return _store().delete_bot(sid)


def cancel_session(sid: str) -> bool:
    from .fleet import turn_core
    try:
        _bot_or_raise(sid)
    except SessionNotFound:
        raise ValueError("session not found") from None
    return turn_core.cancel_active_turn(sid)


def session_events(sid: str, since: float = 0.0) -> List[Dict[str, Any]]:
    try:
        _bot_or_raise(sid)
    except SessionNotFound:
        raise ValueError("session not found") from None
    try:
        cursor = max(0, int(since or 0))
    except (TypeError, ValueError):
        cursor = 0
    rows = _store().list_rows(sid, cursor, 10_000)
    return [_row_to_v2(r) for r in rows]


def latest_seq(sid: str) -> int:
    try:
        _bot_or_raise(sid)
    except SessionNotFound:
        return 0
    return _store().latest_seq(sid)


def stream(sid: str, last_event_id: int = 0) -> List[Dict[str, Any]]:  # legacy name
    return session_events(sid, last_event_id)


def session_summary(sid: str) -> Dict[str, Any]:
    got = get_session(sid)
    return got or {}


def _resolve_pending(sid: str, approval_id: Optional[str]) -> Optional[Dict[str, Any]]:
    pending = _pending_approvals(sid)
    if approval_id:
        return next((a for a in pending if a.get("approval_id") == approval_id), None)
    if len(pending) == 1:
        return pending[0]
    return None


def _decide(sid: str, decision: str, approval_id: Optional[str]) -> Dict[str, Any]:
    try:
        _bot_or_raise(sid)
    except SessionNotFound:
        raise ValueError("session not found") from None
    pending = _pending_approvals(sid)
    if not pending:
        raise KeyError("no pending approval for this session")
    target = _resolve_pending(sid, approval_id)
    if target is None:
        if approval_id:
            raise KeyError(f"approval {approval_id!r} not pending for this session")
        raise RuntimeError(
            f"session has {len(pending)} pending approvals; pass approval_id")

    broker = _store().approvals
    changed, approval, error = broker.decide(
        bot_id=sid, approval_id=target["approval_id"], decision=decision)
    if error:
        raise KeyError(error)
    return {"ok": True, "changed": changed,
            "approval_id": approval.get("approval_id"),
            "status": approval.get("status"),
            "decision": approval.get("decision"),
            "tool_name": approval.get("tool_name")}


def approve(sid: str, approval_id: Optional[str] = None) -> Dict[str, Any]:
    return _decide(sid, "once", approval_id)


def reject(sid: str, approval_id: Optional[str] = None) -> Dict[str, Any]:
    return _decide(sid, "reject", approval_id)


def pending_approvals(sid: str) -> List[Dict[str, Any]]:
    try:
        _bot_or_raise(sid)
    except SessionNotFound:
        raise ValueError("session not found") from None
    return [{
        "approval_id": a.get("approval_id"),
        "tool_name": a.get("tool_name"),
        "fingerprint": a.get("fingerprint"),
        "summary": a.get("args_summary"),
        "expires_at": a.get("expires_at"),
        "created_at": a.get("created_at"),
    } for a in _pending_approvals(sid)]
