"""keel.fleet.turn_core — shared, synchronous agent-turn executor.

Used by:
- `provider_turn.start_provider_turn` (under a worker thread + per-bot lock)
- `fleet.delegation.run_delegated_turn` (inline inside the caller's turn)
- `fleet.groups.run_group_round` (inline per member)

Events flow to `fleet.db` rows (message/step/notice/turn_end/approval) and
to the SSE fan-out, exactly as in the F-provider milestone. Nothing here
ever raises through the public entry points — failures land as notices and
`turn_end` with a meaningful `terminal_reason`.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

_log = logging.getLogger(__name__)

from ..instructions import history_attachment, notes_attachment
from ..session import Session, SessionConfig
from ..providers.base import ProviderError
from ..providers.model_client import ProviderModelClient

_FLEET_ROOT = Path.home() / ".keel" / "fleet"
_STATE_ROOT = _FLEET_ROOT / "state"

_DELEGATE_REPLY_CAP = 4000

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_CANCEL: dict[str, threading.Event] = {}


def _register_active_turn(bot_id: str) -> threading.Event:
    ev = threading.Event()
    with _ACTIVE_LOCK:
        _ACTIVE_CANCEL[bot_id] = ev
    return ev


def _unregister_active_turn(bot_id: str, ev: threading.Event) -> None:
    with _ACTIVE_LOCK:
        if _ACTIVE_CANCEL.get(bot_id) is ev:
            _ACTIVE_CANCEL.pop(bot_id, None)


def cancel_active_turn(bot_id: str) -> bool:
    """Operator 'Stop': cooperative cancellation for the current turn.

    The in-flight model round-trip (one HTTP stream) completes; no further
    model round-trips or tool executions are issued. Returns True if a turn
    was mid-flight.
    """
    with _ACTIVE_LOCK:
        ev = _ACTIVE_CANCEL.get(bot_id)
    if ev is None:
        return False
    ev.set()
    return True


def _normalize_permission_mode(mode: str | None) -> str:
    m = (mode or "").strip().lower()
    if m in ("dontAsk", "dont_ask", "dontask"):
        return "dontAsk"
    if m in ("plan", "plan_mode"):
        # "plan" = read-only: reads allow, mutations/shell/network denied
        return "dontAsk"
    if m in ("acceptedits", "accept_edits", "accept-edits"):
        # "acceptEdits" = writes/edits allowed without asking;
        # shells, network, and everything else ask as usual
        return "acceptEdits"
    if m in ("autopilot", "auto"):
        # "autopilot" = the agent does the work without asking first.
        # NOT a safety bypass: Tier-1 deny rules, hooks, Tier-2 and the
        # operator's standing policies still bind — autopilot only skips
        # the F1 "consent required?" pause.
        return "bypassPermissions"
    return "default"


def _fleet_max_turns() -> int:
    """Agentic turn cap for Fleet turns (LLM round-trips per user message).

    Harness default is 25; long multi-tool runs (write → verify → fix)
    blow through 5 in seconds. Env-tunable; clamped to [1, 50].
    """
    raw = os.environ.get("KEEL_FLEET_MAX_TURNS", "25").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 10
    return max(1, min(50, n))


def _state_root() -> Path:
    p = Path(os.environ.get("KEEL_FLEET_STATE", str(_STATE_ROOT)))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_append(store, bot_id: str, kind: str, body: dict) -> None:
    """Best-effort row write; a closed store (test shutdown) is not a crash."""
    try:
        store.append_row(bot_id, kind, body)
    except sqlite3.ProgrammingError:
        _log.debug("fleet store closed while writing %s row", kind)
    except Exception:
        _log.exception("fleet store write failed for %s row", kind)


def _emit_row(store, bot_id: str, sink, kind: str, body: dict) -> None:
    """Route turn rows either to a group ledger sink or the bot's DM rows."""
    if sink is not None:
        try:
            sink(kind, body)
        except Exception:
            _log.exception("row sink failed for %s row", kind)
        return
    _safe_append(store, bot_id, kind, body)


def _history_rows(store, bot_id: str, *, exclude_last: bool) -> list[dict]:
    try:
        rows = store.list_rows(bot_id, after_seq=0, limit=64)
    except Exception:
        return []
    convo = [r for r in rows if r["kind"] == "message"]
    if exclude_last and convo:
        convo = convo[:-1]  # drop the prompt that was just appended
    return [{"role": r["body"].get("role"), "content": r["body"].get("content")}
            for r in convo]


def _input_summary(tool_input) -> str:
    try:
        text = json.dumps(tool_input, ensure_ascii=False,
                          separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(tool_input)
    return text[:180]


def _result_excerpt(tool_result) -> str:
    content = tool_result.get("content") if isinstance(tool_result, dict) else str(tool_result)
    if not isinstance(content, str):
        content = str(content)
    return content[:156]


def execute_turn(store, bot: dict, content: str, *,
                 chain: tuple = (),
                 user_row: dict | None = None,
                 extra_attachment: str | None = None,
                 include_history: bool = True,
                 exclude_last_from_history: bool = True,
                 executor=None,
                 row_sink=None,
                 permission_mode: str | None = None) -> dict:
    """Run one agent turn synchronously and return a summary dict.

    Returns `{ok, assistant_text, terminal_reason, permission_denials,
              error?}`. Caller decides on locking; every failure is captured.
    """
    bot_id = bot["id"]
    cancel_ev = _register_active_turn(bot_id)
    assistant_text_parts: list[str] = []
    permission_denials = 0
    approval_denials: list[dict] = []
    terminal_reason = "completed"
    ok = True
    error = None

    # live token streaming: deltas are buffered here and fanned out as
    # ephemeral SSE frames (never persisted), roughly one frame per ~30
    # chars or ~80ms — fast enough to look fluid, rare enough to stay cheap
    stream_buf: list[str] = []
    pending_chars = [0]
    last_flush = [time.monotonic()]

    def _flush_stream() -> None:
        if not stream_buf:
            return
        chunk = "".join(stream_buf)
        stream_buf.clear()
        pending_chars[0] = 0
        try:
            store.publish({"type": "stream", "bot_id": bot_id,
                           "delta": chunk})
        except Exception:
            pass  # streaming is best-effort; persistence is the rows
        last_flush[0] = time.monotonic()

    def _on_delta(text: str) -> None:
        if not text:
            return
        stream_buf.append(text)
        pending_chars[0] += len(text)
        if (pending_chars[0] >= 30
                or time.monotonic() - last_flush[0] >= 0.08):
            _flush_stream()

    try:
        if user_row is not None:
            # the delegated prompt lands in the callee's DM, never the sink
            _safe_append(store, bot_id, "message", user_row)
        if bot.get("engine") == "echo":
            from .echo import echo_reply
            text = echo_reply(content)
            _emit_row(store, bot_id, row_sink, "message", {
                "role": "assistant", "content": text, "engine": "echo"})
            _emit_row(store, bot_id, row_sink, "turn_end", {
                "duration_ms": 0, "num_turns": 1, "num_steps": 0,
                "terminal_reason": "completed"})
            return {"ok": True, "assistant_text": text,
                    "terminal_reason": "completed",
                    "permission_denials": 0, "error": None}
        provider = (bot.get("provider") or "auto").strip().lower()
        model_pref = (bot.get("model") or "").strip() or None
        from ..providers import registry as provider_registry
        if provider == "auto":
            provider_chain = provider_registry.resolve_chain("auto")
            if not provider_chain:
                _emit_row(store, bot_id, row_sink, "notice", {
                    "text": ("Provider turn could not start: no provider is "
                             "configured for this agent. Set one with "
                             "`keel provider list` and configure a key, "
                             "then retry."),
                    "level": "warning",
                })
                _emit_row(store, bot_id, row_sink, "turn_end",
                             {"duration_ms": 0, "num_turns": 0,
                              "terminal_reason": "not_configured"})
                return {"ok": False, "assistant_text": "",
                        "terminal_reason": "not_configured",
                        "permission_denials": 0,
                        "error": "no provider configured"}
            adapter = provider_registry.build_adapter(provider_chain[0].name)
            chosen = provider_chain[0]
        else:
            cap = provider_registry.capability(provider)
            if cap is None:
                _emit_row(store, bot_id, row_sink, "notice", {
                    "text": f"Unknown provider {provider!r}. Check "
                            f"`keel provider list`.",
                    "level": "error"})
                _emit_row(store, bot_id, row_sink, "turn_end",
                             {"duration_ms": 0, "num_turns": 0,
                              "terminal_reason": "provider_unknown"})
                return {"ok": False, "assistant_text": "",
                        "terminal_reason": "provider_unknown",
                        "permission_denials": 0,
                        "error": f"unknown provider {provider!r}"}
            adapter = provider_registry.build_adapter(provider)
            chosen = cap
        model_name = model_pref or chosen.default_model
        effort = (bot.get("reasoning_effort") or "").strip().lower() or None
        client = ProviderModelClient(adapter, model=model_name,
                                     delta_sink=_on_delta,
                                     reasoning_effort=effort)
        state_root = _state_root()
        broker = store.approvals
        hist = (_history_rows(store, bot_id,
                              exclude_last=exclude_last_from_history)
                if include_history else [])
        notes = (bot.get("notes") or "").strip()
        executor = executor or _fleet_tools(store, bot, chain)
        if row_sink is not None and hasattr(executor, "row_sink"):
            executor.row_sink = row_sink
        config = SessionConfig(
            cwd=str(state_root),
            state_root=str(state_root),
            bare=True,
            permission_mode=_normalize_permission_mode(permission_mode),
            session_id=str(uuid.uuid4()),
            model=model_name,
            max_turns=_fleet_max_turns(),
            cancel_event=cancel_ev,
            notes_attachment=notes_attachment(notes) if notes else None,
            history_attachment=history_attachment(hist) if hist else None,
            extra_attachment=extra_attachment,
            # F1: operator approval cards at the tool boundary
            approval_decider=broker.decider(bot),
            approval_audit=broker.outcome_audit(bot_id),
            delegation_chain=tuple(chain or ()),
        )
        session = Session(model_client=client,
                          executor=executor,
                          config=config, clock=None, rng=None)

        outcome = session.run(content)
        _flush_stream()  # tail of whatever the model produced

        turn_steps = 0
        pending: dict[str, str] = {}
        # when the executor publishes live steps, don't double-write from
        # the event replay
        live_steps = getattr(executor, "live_steps", False)
        for event in outcome.events:
            etype = event.get("type")
            if etype == "assistant":
                for block in event.get("message", {}).get("content", []):
                    btype = block.get("type")
                    if btype == "text":
                        text = block.get("text", "")
                        assistant_text_parts.append(text)
                        _emit_row(store, bot_id, row_sink, "message", {
                            "role": "assistant",
                            "content": text,
                            "engine": provider,
                            "model": model_name,
                        })
                    elif btype == "tool_use":
                        pending[block.get("id")] = block.get("name", "tool")
                        if live_steps:
                            continue
                        name = block.get("name", "tool")
                        body = {
                            "name": name,
                            "status": "running",
                            "detail": _input_summary(block.get("input") or {}),
                        }
                        if name == "send_to_bot":
                            slug = str((block.get("input") or {}).get("bot_slug", ""))
                            body["detail"] = f"→ {slug}: {_input_summary(block.get('input') or {})}"[:180]
                        _emit_row(store, bot_id, row_sink, "step", body)
                        turn_steps += 1
            elif etype == "user":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") != "tool_result":
                        continue
                    content_raw = block.get("content", "")
                    if not isinstance(content_raw, str):
                        content_raw = json.dumps(content_raw, default=str)
                    failed = content_raw.startswith("<tool_use_error>")
                    if live_steps:
                        # the executor already logged executed calls; only gate-
                        # blocked calls (tool_use_error) were never published
                        if failed:
                            name = pending.get(block.get("tool_use_id"), "tool")
                            _emit_row(store, bot_id, row_sink, "step", {
                                "name": name,
                                "status": "error",
                                "detail": _result_excerpt({"content": content_raw}),
                            })
                        continue
                    name = pending.get(block.get("tool_use_id"), "tool")
                    failed = content_raw.startswith("<tool_use_error>")
                    body = {
                        "name": name,
                        "status": "error" if failed else "done",
                        "detail": _result_excerpt({"content": content_raw}),
                    }
                    del_info = getattr(executor, "last_delegation", None)
                    if name == "send_to_bot" and del_info:
                        body["delegated"] = {
                            "to": del_info.get("to"),
                            "to_id": del_info.get("to_id"),
                            "reply": (del_info.get("reply") or "")[:_DELEGATE_REPLY_CAP],
                            "ok": bool(del_info.get("ok")),
                            "task_id": del_info.get("task_id"),
                        }
                    _emit_row(store, bot_id, row_sink, "step", body)
            elif etype == "system":
                subtype = event.get("subtype")
                if subtype == "permission_denied":
                    permission_denials += 1
                    rtype = event.get("decision_reason_type", "")
                    reason = event.get("decision_reason", "not approved")
                    approval_denials.append({
                        "tool_name": event.get("tool_name", "tool"),
                        "reason_type": rtype,
                        "reason": reason,
                    })
                    is_fleet = str(rtype).startswith("fleet")
                    _emit_row(store, bot_id, row_sink, "notice", {
                        "text": (f"Refused ({rtype}): {reason}" if is_fleet else
                                 f"Permission gate refused "
                                 f"{event.get('tool_name', 'tool')}: {reason}"),
                        "level": "warning",
                    })
            elif etype == "result":
                terminal_reason = event.get("terminal_reason") or "completed"
                usage = (event.get("usage") or {}) if isinstance(event.get("usage"), dict) else {}
                _emit_row(store, bot_id, row_sink, "turn_end", {
                    "duration_ms": event.get("duration_ms", 0),
                    "num_turns": event.get("num_turns", 0),
                    "num_steps": ((getattr(executor, "step_count", 0) if executor is not None else 0)
                                  or turn_steps),
                    "terminal_reason": terminal_reason,
                    "usage": {
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                    },
                })
                if event.get("subtype") != "success":
                    errors = event.get("errors") or []
                    first = errors[0] if errors else {}
                    category = first.get("category") or terminal_reason
                    message = first.get("message") or terminal_reason
                    _emit_row(store, bot_id, row_sink, "notice", {
                        "text": f"Provider error: {category}: {message}",
                        "level": "error",
                    })
                    ok = False
                    error = f"{category}: {message}"
    except ProviderError as exc:
        _emit_row(store, bot_id, row_sink, "notice", {
            "text": f"Provider error: {exc.category}: {exc}",
            "level": "error",
        })
        _emit_row(store, bot_id, row_sink, "turn_end",
                     {"duration_ms": 0, "num_turns": 0,
                      "terminal_reason": "provider_error"})
        return {"ok": False, "assistant_text": "".join(assistant_text_parts),
                "terminal_reason": "provider_error",
                "permission_denials": permission_denials,
                "approval_denials": approval_denials,
                "error": str(exc)}
    except Exception as exc:  # never strand the UI
        _log.exception("turn failed")
        _flush_stream()
        _emit_row(store, bot_id, row_sink, "notice", {
            "text": f"Provider turn failed: {exc}",
            "level": "error",
        })
        _emit_row(store, bot_id, row_sink, "turn_end",
                     {"duration_ms": 0, "num_turns": 0,
                      "terminal_reason": "internal_error"})
        return {"ok": False, "assistant_text": "".join(assistant_text_parts),
                "terminal_reason": "internal_error",
                "permission_denials": permission_denials,
                "approval_denials": approval_denials,
                "error": str(exc)}
    finally:
        _unregister_active_turn(bot_id, cancel_ev)
    return {"ok": ok, "assistant_text": "".join(assistant_text_parts),
            "terminal_reason": terminal_reason,
            "permission_denials": permission_denials,
            "approval_denials": approval_denials,
            "error": error}


def _fleet_tools(store, bot, chain):
    from .tools import FleetTools
    return FleetTools(store, bot, tuple(chain or ()))
