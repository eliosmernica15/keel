"""keel.events — the stream-json event union (Phase 1).

Writers only: this module builds dicts that serialise to one JSON object per
line. Field names and the terminal-subtype vocabulary are pinned by the
interface contract (interface-spec.md §15–17); descriptions are ours.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class Ids:
    """Injectable id factory (determinism seam)."""

    rng: Any = None

    def session_id(self) -> str:
        return self._gen()

    def event_uuid(self) -> str:
        return self._gen()

    def tool_use_id(self) -> str:
        return f"call_{self._gen()}"

    def message_id(self) -> str:
        return f"msg_{self._gen()}"

    def _gen(self) -> str:
        if self.rng is None:
            return _uuid()
        # seeded path: derive a stable UUID from the seeded RNG
        return str(uuid.UUID(int=self.rng.getrandbits(128)))


def iso_ts(clock: Any) -> str:
    return clock.now_iso()


def system_init(*, cwd: str, session_id: str, model: str, permission_mode: str,
                tools: list[str], uuid: str, timestamp: str,
                additional_directories: list[str] | None = None,
                mcp_servers: list[dict] | None = None,
                slash_commands: list[str] | None = None,
                terminal_slash_commands: list[str] | None = None,
                agents: list[str] | None = None,
                skills: list[str] | None = None,
                plugins: list[dict] | None = None,
                capabilities: list[str] | None = None,
                api_key_source: str = "none",
                output_style: str = "default",
                analytics_disabled: bool = True,
                product_feedback_disabled: bool = True,
                fast_mode_state: str = "off",
                per_turn_effort_active: bool = False,
                view_mode: str = "print",
                memory_paths: list[str] | None = None,
                claude_code_version: str = "keel/0.1.0a0") -> dict:
    return {
        "type": "system",
        "subtype": "init",
        "cwd": cwd,
        "original_cwd": cwd,
        "additional_directories": additional_directories or [],
        "session_id": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
        "tools": list(tools),
        "mcp_servers": mcp_servers or [],
        "model": model,
        "permissionMode": permission_mode,
        "slash_commands": slash_commands or [],
        "terminal_slash_commands": terminal_slash_commands or [],
        "agents": agents or [],
        "skills": skills or [],
        "plugins": plugins or [],
        "capabilities": capabilities or [],
        "memory_paths": memory_paths or [],
        "apiKeySource": api_key_source,
        "output_style": output_style,
        "claude_code_version": claude_code_version,
        "analytics_disabled": analytics_disabled,
        "product_feedback_disabled": product_feedback_disabled,
        "fast_mode_state": fast_mode_state,
        "per_turn_effort_active": per_turn_effort_active,
        "view_mode": view_mode,
    }


def assistant_message(*, message_id: str, request_id: str, session_id: str,
                      uuid: str, timestamp: str, model: str,
                      content: list[dict], stop_reason: str | None = None,
                      usage: dict | None = None,
                      parent_tool_use_id: str | None = None) -> dict:
    return {
        "type": "assistant",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "content": content,
            "model": model,
            "stop_reason": stop_reason,
            "usage": usage or _zero_usage(),
        },
        "parent_tool_use_id": parent_tool_use_id,
        "session_id": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
        "request_id": request_id,
    }


def user_tool_result(*, tool_use_id: str, content: str,
                     session_id: str, uuid: str, timestamp: str,
                     tool_use_result: Any = None,
                     tool_result_meta: list[dict] | None = None,
                     is_compact_summary: bool = False,
                     parent_tool_use_id: str | None = None) -> dict:
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [block],
        },
        "parent_tool_use_id": parent_tool_use_id,
        "session_id": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
        "tool_use_result": tool_use_result,
        "tool_result_meta": tool_result_meta or [],
        "isCompactSummary": is_compact_summary,
    }


def system_permission_denied(*, tool_name: str, tool_use_id: str, tool_input: dict,
                             decision_reason_type: str, decision_reason: str,
                             session_id: str, uuid: str, timestamp: str) -> dict:
    return {
        "type": "system",
        "subtype": "permission_denied",
        "tool_name": tool_name,
        "tool_use_id": tool_use_id,
        "tool_input": tool_input,
        "decision_reason_type": decision_reason_type,
        "decision_reason": decision_reason,
        "session_id": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
    }


def system_informational(*, text: str, session_id: str, uuid: str,
                         timestamp: str, level: str = "info") -> dict:
    return {
        "type": "system",
        "subtype": "informational",
        "level": level,
        "content": text,
        "session_id": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
    }


def hook_started(*, session_id: str, uuid: str, timestamp: str,
                 hook_name: str, hook_event: str, tool_use_id: str | None) -> dict:
    return {
        "type": "system",
        "subtype": "hook_started",
        "hook_name": hook_name,
        "hook_event": hook_event,
        "tool_use_id": tool_use_id,
        "session_id": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
    }


def hook_response(*, session_id: str, uuid: str, timestamp: str,
                  hook_name: str, hook_event: str,
                  tool_use_id: str | None, exit_code: int | None,
                  duration_ms: int, verdict: str) -> dict:
    return {
        "type": "system",
        "subtype": "hook_response",
        "hook_name": hook_name,
        "hook_event": hook_event,
        "tool_use_id": tool_use_id,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "verdict": verdict,
        "session_id": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
    }


def compact_boundary(*, session_id: str, uuid: str, timestamp: str,
                     pre_tokens: int, post_tokens: int,
                     cumulative_dropped: int, duration_ms: int,
                     preserved_head: str, preserved_tail: str,
                     preserved_uuids: list[str], logical_parent: str,
                     trigger: str = "auto") -> dict:
    return {
        "type": "system",
        "subtype": "compact_boundary",
        "content": "Conversation compacted",
        "level": "info",
        "trigger": trigger,
        "preTokens": pre_tokens,
        "postTokens": post_tokens,
        "cumulativeDroppedTokens": cumulative_dropped,
        "durationMs": duration_ms,
        "preCompactDiscoveredTools": [],
        "preservedSegment": {
            "headUuid": preserved_head,
            "anchorUuid": preserved_head,
            "tailUuid": preserved_tail,
        },
        "preservedMessages": {
            "anchorUuid": preserved_head,
            "uuids": list(preserved_uuids),
        },
        "parentUuid": None,
        "logicalParentUuid": logical_parent,
        "session_id": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
    }


def turn_duration(*, duration_ms: int, message_count: int, entrypoint: str,
                  cwd: str, session_id: str, uuid: str, timestamp: str) -> dict:
    return {
        "type": "system",
        "subtype": "turn_duration",
        "duration_ms": duration_ms,
        "messageCount": message_count,
        "entrypoint": entrypoint,
        "cwd": cwd,
        "session_id": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
    }


def _zero_usage() -> dict:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def _zero_model_usage(model: str, context_window: int = 128000,
                      max_output_tokens: int = 8192) -> dict:
    return {
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheReadInputTokens": 0,
        "cacheCreationInputTokens": 0,
        "webSearchRequests": 0,
        "costUSD": 0,
        "contextWindow": context_window,
        "maxOutputTokens": max_output_tokens,
        "thinkingTokens": 0,
        "canonicalModel": model,
        "provider": "fake",
        "costBasis": "unknown",
    }


RESULT_SUBTYPES = frozenset({
    "success",
    "error_max_turns",
    "error_max_budget_usd",
    "error_during_execution",
    "error_max_structured_output_retries",
})

EXIT_CODES = {
    "success": 0,
    "error_max_turns": 1,
    "error_max_budget_usd": 1,
    "error_during_execution": 1,
    "error_max_structured_output_retries": 1,
}


def result(*, subtype: str, session_id: str, uuid: str, timestamp: str,
           num_turns: int, duration_ms: int, duration_api_ms: int,
           stop_reason: str | None, terminal_reason: str,
           result_text: str | None, model: str,
           permission_denials: list[dict] | None = None,
           model_usage: dict | None = None,
           subagent_stats: dict | None = None,
           errors: list[dict] | None = None,
           total_cost_usd: float = 0.0,
           usage_tokens: dict | None = None,
           is_error: bool | None = None,
           local_command: str | None = None,
           safety_stops: int = 0) -> dict:
    if subtype not in RESULT_SUBTYPES:
        raise ValueError(f"unknown result subtype: {subtype!r}")
    is_error = (subtype != "success") if is_error is None else is_error
    usage = _zero_usage()
    if usage_tokens:
        usage = {
            "input_tokens": usage_tokens.get("input_tokens", 0),
            "output_tokens": usage_tokens.get("output_tokens", 0),
            "cache_creation_input_tokens":
                usage_tokens.get("cache_creation_input_tokens", 0),
            "cache_read_input_tokens":
                usage_tokens.get("cache_read_input_tokens", 0),
        }
    envelope = {
        "type": "result",
        "subtype": subtype,
        "is_error": is_error,
        "session_id": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
        "num_turns": num_turns,
        "duration_ms": duration_ms,
        "duration_api_ms": duration_api_ms,
        "ttft_ms": duration_api_ms,
        "ttft_stream_ms": duration_api_ms,
        "time_to_request_ms": 0,
        "first_content_frame_ms": duration_api_ms,
        "stop_reason": stop_reason,
        "terminal_reason": terminal_reason,
        "api_error_status": None,
        "total_cost_usd": total_cost_usd,
        "usage": usage,
        "modelUsage": model_usage or {model: _zero_model_usage(model)},
        "permission_denials": permission_denials or [],
        "safety_stops": safety_stops,
        "queued_turn_count": 0,
        "result_index": 0,
        "subagent_stats": subagent_stats or {
            "count": 0,
            "inputTokens": 0,
            "outputTokens": 0,
            "costUSD": 0,
        },
        "fast_mode_state": "off",
        "per_turn_effort_active": False,
    }
    if subtype == "success":
        envelope["result"] = result_text or ""
    elif errors is not None:
        envelope["errors"] = errors
    if local_command:
        envelope["local_command"] = local_command
    return envelope


def iter_lines(events: Iterator[dict]) -> Iterator[str]:
    """Serialise events one compact JSON object per line."""
    import json

    for ev in events:
        yield json.dumps(ev, separators=(",", ":"), ensure_ascii=False)
