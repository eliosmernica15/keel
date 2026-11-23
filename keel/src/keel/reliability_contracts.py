"""keel.reliability_contracts -- X9.x reliability testing contracts.

This is an *additive*, stdlib-only module.  It implements the four not_started
P0 rows of ``PLAN-INDEX.json`` (Addendum 3, section I "Testing and quality"):

  X9.1  :class:`FixtureModelServer` -- a real, loopback-only, OpenAI-compatible
        HTTP server that replays scripted text, tool calls, malformed frames,
        partial streams, slow tokens and errors.  Scripts are pure validated
        descriptors rendered to wire frames for three provider dialects.
  X9.3  :class:`ProviderContractSuite` -- one behaviour suite (streaming,
        cancel, tool calls, usage, errors plus wire-fault cases) run against
        each provider adapter through the same typed contract.
  X9.5  :func:`evaluate_path`, :func:`evaluate_permission` and their matrix
        runners -- a deterministic cross-platform path/permission matrix
        (Windows reserved names, ADS, long paths, case-insensitive FS,
        symlinks/junctions) with deny-by-default permission decisions.
  X9.7  :class:`MigrationMatrix` -- every released schema version upgraded to
        the current one with canonical-JSON data checksums and fail-closed
        verification that no payload data was lost.

Design rules (shared by all four contracts):

* **No fake success.** Every report's ``ok`` is computed from observed events,
  wire statistics, checksums or verdicts.  There is no unconditional ``True``.
* **Fail closed.** Unknown scripts, malformed requests, unsafe paths and bad
  migrations raise a typed :class:`ReliabilityError` subclass; network errors
  and incomplete streams are reported, never swallowed into a success.
* **Deterministic.** Canonical JSON (sorted keys, compact separators, strict
  numbers), no wall-clock values in results, no discovery-order dependence,
  and an injectable sleeper so slow-token replay is reproducible.
* **No ambient I/O at import time.** The server binds only when explicitly
  started; the provider suite imports keel adapters lazily; the matrixes are
  pure functions.

Integration into live tests is described in
``master-plan-v6-reliability-contracts-evidence.md``.  No existing file is
modified by this module.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

__all__ = [
    "SCHEMA_VERSION", "ReliabilityError", "ValidationError",
    "canonical_bytes", "fingerprint",
    # X9.1
    "Dialect", "EventKind", "ScriptEvent", "WireFrame", "FixtureScript",
    "RecordedRequest", "StreamStats", "FixtureModelServer",
    "make_fixture_server", "standard_scripts", "render_script",
    "MAX_BODY_BYTES", "MAX_DELAY_MS", "FINISH_REASONS",
    # X9.3
    "AdapterRequest", "KeelAdapter", "CancellingAdapter", "AdapterBinding",
    "TrackingHTTPTransport", "BehaviorCase", "BehaviorResult",
    "ContractReport", "ProviderContractSuite", "default_bindings",
    "EXPECTED_ERROR_CATEGORIES",
    # X9.5
    "Platform", "PathHazard", "PathCase", "PathVerdict", "Permission",
    "Principal", "PermissionRequest", "PermissionDecision",
    "evaluate_path", "evaluate_permission", "path_matrix",
    "permission_matrix", "MatrixReport", "run_path_matrix",
    "run_permission_matrix",
    # X9.7
    "MIGRATIONS", "RELEASED_VERSIONS", "CURRENT_SCHEMA_VERSION",
    "MigrationResult", "MigrationMatrix", "checksum_data", "payload_view",
    "build_version_fixture",
]

#: Version of the contract descriptors defined here (not the product version).
SCHEMA_VERSION = "1.0"


class ReliabilityError(ValueError):
    """Base class for every typed failure raised by this module."""


class ValidationError(ReliabilityError):
    """A descriptor, request or migration input failed validation."""


def canonical_bytes(value: Any) -> bytes:
    """UTF-8 JSON with sorted keys and compact separators.

    ``allow_nan=False`` keeps checksums strict: NaN/Infinity are rejected
    instead of producing a platform-dependent spelling.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def fingerprint(value: Any) -> str:
    """Stable SHA-256 of a canonical JSON representation."""
    return hashlib.sha256(canonical_bytes(_jsonable(value))).hexdigest()


def _jsonable(value: Any) -> Any:
    """Convert adapter event payloads into deterministic JSON-compatible data."""
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return repr(value)


# ---------------------------------------------------------------------------
# X9.1 -- fixture model server
# ---------------------------------------------------------------------------

MAX_BODY_BYTES = 1 << 20
MAX_DELAY_MS = 60_000
FINISH_REASONS = ("stop", "length", "tool_calls", "refusal")
_DIALECT_PATHS = {
    "openai_chat": "/v1/chat/completions",
    "anthropic_messages": "/v1/messages",
    "gemini_generate": "/v1beta/models/{model}:streamGenerateContent",
}
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_ERROR_CATEGORIES = {400: "invalid_request_error", 401: "authentication_error",
                     403: "permission_error", 404: "not_found_error",
                     429: "rate_limit_error", 500: "api_error",
                     502: "api_error", 503: "overloaded_error"}


class Dialect(str, Enum):
    OPENAI_CHAT = "openai_chat"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    GEMINI_GENERATE = "gemini_generate"


class EventKind(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    USAGE = "usage"
    FINISH = "finish"
    MALFORMED_JSON = "malformed_json"
    PARTIAL_STREAM = "partial_stream"
    SLOW_TOKEN = "slow_token"
    ERROR = "error"


def _require_str(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string, got {type(value).__name__}")
    if not allow_empty and not value:
        raise ValidationError(f"{field_name} must not be empty")
    return value


def _require_int(value: Any, field_name: str, *, minimum: int = 0,
                 maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field_name} must be an int, got {type(value).__name__}")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValidationError(f"{field_name}={value} out of range")
    return value


@dataclass(frozen=True)
class ScriptEvent:
    """One semantic event of a scripted model response.

    A single descriptor renders to all three wire dialects, so an adapter
    cannot pass the contract suite by special-casing one provider.
    """

    kind: EventKind
    text: str = ""
    tool_id: str = ""
    tool_name: str = ""
    arguments: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    status: int = 0
    error: str = ""
    raw: bytes = b""
    delay_ms: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EventKind):
            raise ValidationError("kind must be an EventKind value")
        _require_str(self.text, "text", allow_empty=True)
        _require_str(self.tool_id, "tool_id", allow_empty=True)
        _require_str(self.tool_name, "tool_name", allow_empty=True)
        _require_str(self.arguments, "arguments", allow_empty=True)
        _require_str(self.error, "error", allow_empty=True)
        if not isinstance(self.raw, bytes):
            raise ValidationError("raw must be bytes")
        _require_int(self.input_tokens, "input_tokens")
        _require_int(self.output_tokens, "output_tokens")
        _require_int(self.delay_ms, "delay_ms", maximum=MAX_DELAY_MS)
        _require_int(self.status, "status", maximum=599)
        _require_str(self.finish_reason, "finish_reason")
        if self.kind in (EventKind.TEXT, EventKind.SLOW_TOKEN):
            if not self.text:
                raise ValidationError(f"{self.kind.value} requires text")
            if self.kind is EventKind.SLOW_TOKEN and self.delay_ms <= 0:
                raise ValidationError("slow_token requires a positive delay_ms")
        if self.kind is EventKind.TOOL_CALL:
            if not self.tool_name and not self.arguments:
                raise ValidationError("tool_call requires tool_name or arguments")
        if self.kind is EventKind.FINISH:
            if self.finish_reason not in FINISH_REASONS:
                raise ValidationError(f"unknown finish_reason {self.finish_reason!r}")
            if self.status:
                raise ValidationError("finish must not carry a status")
        if self.kind is EventKind.USAGE and self.status:
            raise ValidationError("usage must not carry a status")
        if self.kind is EventKind.ERROR:
            if not 400 <= self.status <= 599:
                raise ValidationError("error requires an HTTP status in 400..599")
            if not self.error:
                raise ValidationError("error requires a message")
        elif self.status:
            raise ValidationError(f"{self.kind.value} must not carry a status")
        if self.kind is EventKind.MALFORMED_JSON:
            if not self.raw:
                raise ValidationError("malformed_json requires raw bytes")
            try:
                json.loads(self.raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                pass
            else:
                raise ValidationError("malformed_json raw payload is valid JSON")
        if self.kind is EventKind.PARTIAL_STREAM and self.raw:
            raise ValidationError("partial_stream cannot carry a raw frame")

    def as_dict(self) -> dict:
        out = {"kind": self.kind.value}
        for key in ("text", "tool_id", "tool_name", "arguments", "input_tokens",
                    "output_tokens", "finish_reason", "status", "error",
                    "delay_ms"):
            value = getattr(self, key)
            if value not in ("", 0) or key in ("finish_reason",):
                out[key] = value
        if self.raw:
            out["raw"] = self.raw.decode("utf-8", errors="replace")
        return out


@dataclass(frozen=True)
class WireFrame:
    """A literal response frame emitted by the fixture server."""

    payload: bytes
    delay_ms: int = 0
    status: int = 200
    terminate: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.payload, bytes):
            raise ValidationError("frame payload must be bytes")
        _require_int(self.delay_ms, "delay_ms", maximum=MAX_DELAY_MS)
        _require_int(self.status, "status", minimum=100, maximum=599)
        if not isinstance(self.terminate, bool):
            raise ValidationError("terminate must be a bool")
        _require_str(self.note, "note", allow_empty=True)

    def as_dict(self) -> dict:
        return {"bytes": len(self.payload), "delay_ms": self.delay_ms,
                "status": self.status, "terminate": self.terminate,
                "note": self.note}


def _sse(obj: Mapping[str, Any], *, delay_ms: int = 0, note: str = "") -> WireFrame:
    return WireFrame(b"data: " + canonical_bytes(obj) + b"\n\n",
                     delay_ms=delay_ms, note=note)


def _raw_sse(raw: bytes, *, note: str) -> WireFrame:
    return WireFrame(b"data: " + raw + b"\n\n", note=note)


def _done() -> WireFrame:
    return WireFrame(b"data: [DONE]\n\n", note="done")


def _tool_arguments(script: "FixtureScript") -> dict:
    raw = "".join(e.arguments for e in script.events
                  if e.kind is EventKind.TOOL_CALL)
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{script.name}: tool arguments are not JSON: {exc}") from None
    if not isinstance(parsed, dict):
        raise ValidationError(f"{script.name}: tool arguments must be a JSON object")
    return parsed


def _usage(script: "FixtureScript") -> ScriptEvent | None:
    for event in script.events:
        if event.kind is EventKind.USAGE:
            return event
    return None


def _finish(script: "FixtureScript") -> ScriptEvent | None:
    for event in script.events:
        if event.kind is EventKind.FINISH:
            return event
    return None


def _openai_reason(reason: str) -> str:
    return {"stop": "stop", "length": "length",
            "tool_calls": "tool_calls", "refusal": "stop"}[reason]


def _anthropic_reason(reason: str) -> str:
    return {"stop": "end_turn", "length": "max_tokens",
            "tool_calls": "tool_use", "refusal": "refusal"}[reason]


def _gemini_reason(reason: str) -> str:
    return {"stop": "STOP", "length": "MAX_TOKENS",
            "tool_calls": "STOP", "refusal": "SAFETY"}[reason]


def _error_payload(script: "FixtureScript", event: ScriptEvent) -> dict:
    return {"error": {"message": event.error,
                      "type": _ERROR_CATEGORIES.get(event.status, "api_error"),
                      "code": event.status,
                      "fixture": script.name}}


def _error_frame(script: "FixtureScript", event: ScriptEvent) -> WireFrame:
    return WireFrame(canonical_bytes(_error_payload(script, event)),
                     status=event.status, note="error")


def _render_openai(script: "FixtureScript") -> tuple[WireFrame, ...]:
    frames: list[WireFrame] = []
    tool_started = False
    for event in script.events:
        if event.kind is EventKind.ERROR:
            return (_error_frame(script, event),)
        if event.kind is EventKind.MALFORMED_JSON:
            frames.append(_raw_sse(event.raw, note="malformed_json"))
            continue
        if event.kind is EventKind.PARTIAL_STREAM:
            frames.append(_sse({"choices": [{"index": 0,
                                             "delta": {"content": event.text},
                                             "finish_reason": None}]},
                               note="partial_chunk"))
            frames.append(WireFrame(b"", terminate=True, note="partial_stream"))
            continue
        if event.kind is EventKind.TEXT or event.kind is EventKind.SLOW_TOKEN:
            frames.append(_sse({"id": "fx", "object": "chat.completion.chunk",
                                "created": 0, "model": script.model,
                                "choices": [{"index": 0,
                                             "delta": {"content": event.text},
                                             "finish_reason": None}]},
                               delay_ms=event.delay_ms, note=event.kind.value))
            continue
        if event.kind is EventKind.TOOL_CALL:
            function: dict[str, Any] = {}
            if event.tool_name:
                function["name"] = event.tool_name
            if event.arguments:
                function["arguments"] = event.arguments
            call: dict[str, Any] = {"index": 0, "type": "function",
                                    "function": function}
            if not tool_started:
                call["id"] = event.tool_id or "call_fx_0"
                tool_started = True
            frames.append(_sse({"choices": [{"index": 0,
                                             "delta": {"tool_calls": [call]},
                                             "finish_reason": None}]},
                               note="tool_call"))
            continue
        if event.kind is EventKind.USAGE:
            frames.append(_sse({"choices": [],
                                "usage": {"prompt_tokens": event.input_tokens,
                                          "completion_tokens": event.output_tokens,
                                          "total_tokens": (event.input_tokens
                                                           + event.output_tokens)}},
                               note="usage"))
            continue
        if event.kind is EventKind.FINISH:
            frames.append(_sse({"choices": [{"index": 0, "delta": {},
                                             "finish_reason":
                                                 _openai_reason(event.finish_reason)}]},
                               note="finish"))
            frames.append(_done())
    return tuple(frames)


def _render_anthropic(script: "FixtureScript") -> tuple[WireFrame, ...]:
    usage = _usage(script)
    finish = _finish(script)
    input_tokens = usage.input_tokens if usage else 0
    frames: list[WireFrame] = [
        _sse({"type": "message_start",
              "message": {"id": "msg_fx", "type": "message",
                          "role": "assistant", "model": script.model,
                          "content": [],
                          "usage": {"input_tokens": input_tokens,
                                    "output_tokens": 0}}},
             note="message_start")]
    text_started = False
    tool_started = False
    for event in script.events:
        if event.kind is EventKind.ERROR:
            return (_error_frame(script, event),)
        if event.kind is EventKind.MALFORMED_JSON:
            frames.append(_raw_sse(event.raw, note="malformed_json"))
            continue
        if event.kind is EventKind.PARTIAL_STREAM:
            if not text_started:
                frames.append(_sse({"type": "content_block_start", "index": 0,
                                    "content_block": {"type": "text", "text": ""}},
                                   note="content_block_start"))
                text_started = True
            frames.append(_sse({"type": "content_block_delta", "index": 0,
                                "delta": {"type": "text_delta",
                                          "text": event.text}},
                               note="partial_chunk"))
            frames.append(WireFrame(b"", terminate=True, note="partial_stream"))
            continue
        if event.kind is EventKind.TEXT or event.kind is EventKind.SLOW_TOKEN:
            if not text_started:
                frames.append(_sse({"type": "content_block_start", "index": 0,
                                    "content_block": {"type": "text", "text": ""}},
                                   note="content_block_start"))
                text_started = True
            frames.append(_sse({"type": "content_block_delta", "index": 0,
                                "delta": {"type": "text_delta",
                                          "text": event.text}},
                               delay_ms=event.delay_ms, note=event.kind.value))
            continue
        if event.kind is EventKind.TOOL_CALL:
            if not tool_started:
                frames.append(_sse({"type": "content_block_start", "index": 1,
                                    "content_block": {
                                        "type": "tool_use",
                                        "id": event.tool_id or "call_fx_0",
                                        "name": event.tool_name, "input": {}}},
                                   note="tool_start"))
                tool_started = True
            if event.arguments:
                frames.append(_sse({"type": "content_block_delta", "index": 1,
                                    "delta": {"type": "input_json_delta",
                                              "partial_json": event.arguments}},
                                   note="tool_call"))
            continue
        if event.kind is EventKind.FINISH:
            if text_started:
                frames.append(_sse({"type": "content_block_stop", "index": 0},
                                   note="content_block_stop"))
            if tool_started:
                frames.append(_sse({"type": "content_block_stop", "index": 1},
                                   note="content_block_stop"))
            frames.append(_sse({"type": "message_delta",
                                "delta": {"stop_reason":
                                          _anthropic_reason(event.finish_reason)},
                                "usage": {"output_tokens":
                                          usage.output_tokens if usage else 0}},
                               note="message_delta"))
            frames.append(_sse({"type": "message_stop"}, note="done"))
    return tuple(frames)


def _render_gemini(script: "FixtureScript") -> tuple[WireFrame, ...]:
    frames: list[WireFrame] = []
    tool_started = False
    args = _tool_arguments(script)
    for event in script.events:
        if event.kind is EventKind.ERROR:
            return (_error_frame(script, event),)
        if event.kind is EventKind.MALFORMED_JSON:
            frames.append(_raw_sse(event.raw, note="malformed_json"))
            continue
        if event.kind is EventKind.PARTIAL_STREAM:
            frames.append(_sse({"candidates": [{"index": 0,
                                                "content": {"role": "model",
                                                            "parts": [{"text": event.text}]},
                                                "finishReason": None}]},
                               note="partial_chunk"))
            frames.append(WireFrame(b"", terminate=True, note="partial_stream"))
            continue
        if event.kind is EventKind.TEXT or event.kind is EventKind.SLOW_TOKEN:
            frames.append(_sse({"candidates": [{"index": 0,
                                                "content": {"role": "model",
                                                            "parts": [{"text": event.text}]},
                                                "finishReason": None}]},
                               delay_ms=event.delay_ms, note=event.kind.value))
            continue
        if event.kind is EventKind.TOOL_CALL:
            if not tool_started:
                name = next((e.tool_name for e in script.events
                             if e.kind is EventKind.TOOL_CALL and e.tool_name), "")
                frames.append(_sse({"candidates": [{
                    "index": 0,
                    "content": {"role": "model", "parts": [{
                        "functionCall": {"name": name, "args": args}}]},
                    "finishReason": None}]}, note="tool_call"))
                tool_started = True
            continue
        if event.kind is EventKind.USAGE:
            frames.append(_sse({"usageMetadata": {
                "promptTokenCount": event.input_tokens,
                "candidatesTokenCount": event.output_tokens,
                "totalTokenCount": event.input_tokens + event.output_tokens}},
                note="usage"))
            continue
        if event.kind is EventKind.FINISH:
            frames.append(_sse({"candidates": [{"index": 0,
                                                "content": {"role": "model",
                                                            "parts": []},
                                                "finishReason":
                                                    _gemini_reason(event.finish_reason)}]},
                               note="finish"))
            frames.append(_done())
    return tuple(frames)


_RENDERERS: dict[Dialect, Callable[["FixtureScript"], tuple[WireFrame, ...]]] = {
    Dialect.OPENAI_CHAT: _render_openai,
    Dialect.ANTHROPIC_MESSAGES: _render_anthropic,
    Dialect.GEMINI_GENERATE: _render_gemini,
}


@dataclass(frozen=True)
class FixtureScript:
    """A validated, reusable script of semantic model events."""

    name: str
    model: str
    events: tuple[ScriptEvent, ...]
    dialect: Dialect | None = None
    max_calls: int = 0  # 0 == replay without limit

    def __post_init__(self) -> None:
        _require_str(self.name, "name")
        _require_str(self.model, "model")
        if not _NAME_RE.match(self.name):
            raise ValidationError(f"{self.name}: invalid script name")
        if not _MODEL_RE.match(self.model):
            raise ValidationError(f"{self.model}: invalid model id")
        if self.dialect is not None and not isinstance(self.dialect, Dialect):
            raise ValidationError("dialect must be a Dialect value or None")
        _require_int(self.max_calls, "max_calls")
        if isinstance(self.events, (str, bytes)) or not isinstance(
                self.events, Iterable):
            raise ValidationError("events must be a sequence of ScriptEvent")
        events = tuple(self.events)
        if not events:
            raise ValidationError(f"{self.name}: a script needs at least one event")
        if not all(isinstance(e, ScriptEvent) for e in events):
            raise ValidationError(f"{self.name}: events must be ScriptEvent values")
        object.__setattr__(self, "events", events)
        kinds = [e.kind for e in events]
        if kinds.count(EventKind.ERROR) > 1:
            raise ValidationError(f"{self.name}: at most one error event")
        if EventKind.ERROR in kinds and kinds[-1] is not EventKind.ERROR:
            raise ValidationError(f"{self.name}: error must be the final event")
        if kinds.count(EventKind.PARTIAL_STREAM) > 1:
            raise ValidationError(f"{self.name}: at most one partial stream")
        if EventKind.PARTIAL_STREAM in kinds and kinds[-1] is not EventKind.PARTIAL_STREAM:
            raise ValidationError(f"{self.name}: partial stream must be the final event")
        if kinds.count(EventKind.FINISH) > 1:
            raise ValidationError(f"{self.name}: at most one finish event")
        if any(k is EventKind.PARTIAL_STREAM for k in kinds) and any(
                k in (EventKind.ERROR, EventKind.FINISH) for k in kinds):
            raise ValidationError(f"{self.name}: partial stream cannot also finish")
        if any(k is EventKind.ERROR for k in kinds) and len(events) != 1:
            raise ValidationError(f"{self.name}: an error script has exactly one event")
        if any(e.kind is EventKind.TOOL_CALL for e in events):
            _tool_arguments(self)

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.as_dict())

    def frames(self, dialect: Dialect) -> tuple[WireFrame, ...]:
        if not isinstance(dialect, Dialect):
            raise ValidationError("dialect must be a Dialect value")
        if self.dialect is not None and self.dialect is not dialect:
            raise ValidationError(
                f"{self.name}: bound to {self.dialect.value}, got {dialect.value}")
        return _RENDERERS[dialect](self)

    def as_dict(self) -> dict:
        return {"name": self.name, "model": self.model,
                "dialect": None if self.dialect is None else self.dialect.value,
                "max_calls": self.max_calls,
                "events": [e.as_dict() for e in self.events]}


def render_script(script: FixtureScript, dialect: Dialect) -> tuple[WireFrame, ...]:
    """Pure renderer: script -> deterministic wire frames (no I/O)."""
    return script.frames(dialect)


def standard_scripts() -> tuple[FixtureScript, ...]:
    """The shared script set used by provider and agent tests (X9.1)."""
    return (
        FixtureScript("stream", "fx-stream", (
            ScriptEvent(EventKind.TEXT, text="He"),
            ScriptEvent(EventKind.TEXT, text="llo "),
            ScriptEvent(EventKind.TEXT, text="world."),
            ScriptEvent(EventKind.USAGE, input_tokens=12, output_tokens=4),
            ScriptEvent(EventKind.FINISH, finish_reason="stop"),
        )),
        FixtureScript("tool_call", "fx-tool", (
            ScriptEvent(EventKind.TOOL_CALL, tool_id="call_fx_0",
                        tool_name="get_weather", arguments='{"city":'),
            ScriptEvent(EventKind.TOOL_CALL, arguments='"Oslo"}'),
            ScriptEvent(EventKind.USAGE, input_tokens=20, output_tokens=6),
            ScriptEvent(EventKind.FINISH, finish_reason="tool_calls"),
        )),
        FixtureScript("usage", "fx-usage", (
            ScriptEvent(EventKind.TEXT, text="counted"),
            ScriptEvent(EventKind.USAGE, input_tokens=101, output_tokens=7),
            ScriptEvent(EventKind.FINISH, finish_reason="stop"),
        )),
        FixtureScript("error", "fx-error", (
            ScriptEvent(EventKind.ERROR, status=429, error="rate limit reached"),
        )),
        FixtureScript("malformed_json", "fx-malformed", (
            ScriptEvent(EventKind.TEXT, text="before the bad frame"),
            ScriptEvent(EventKind.MALFORMED_JSON, raw=b"{not-json"),
            ScriptEvent(EventKind.USAGE, input_tokens=3, output_tokens=1),
            ScriptEvent(EventKind.FINISH, finish_reason="stop"),
        )),
        FixtureScript("partial_stream", "fx-partial", (
            ScriptEvent(EventKind.TEXT, text="this stream is cut"),
            ScriptEvent(EventKind.PARTIAL_STREAM, text="partial"),
        )),
        FixtureScript("slow_tokens", "fx-slow", (
            ScriptEvent(EventKind.SLOW_TOKEN, text="s", delay_ms=10),
            ScriptEvent(EventKind.SLOW_TOKEN, text="l", delay_ms=10),
            ScriptEvent(EventKind.SLOW_TOKEN, text="o", delay_ms=10),
            ScriptEvent(EventKind.USAGE, input_tokens=5, output_tokens=3),
            ScriptEvent(EventKind.FINISH, finish_reason="stop"),
        )),
    )


@dataclass(frozen=True)
class RecordedRequest:
    """A redacted record of one request served by the fixture."""

    ordinal: int
    method: str
    path: str
    headers: Mapping[str, str]
    body: Mapping[str, Any] | None
    script_name: str

    def as_dict(self) -> dict:
        hidden = {"authorization", "x-api-key", "x-goog-api-key"}
        headers = {k.lower(): ("<redacted>" if k.lower() in hidden else v)
                   for k, v in self.headers.items()}
        return {"ordinal": self.ordinal, "method": self.method,
                "path": self.path, "headers": headers,
                "body": dict(self.body) if self.body is not None else None,
                "script_name": self.script_name}


@dataclass(frozen=True)
class StreamStats:
    """Wire-level observations that cannot be faked by an adapter."""

    frames_sent: int
    terminated: bool
    malformed_frames: int
    error_frames: int
    delays_ms: int
    notes: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"frames_sent": self.frames_sent, "terminated": self.terminated,
                "malformed_frames": self.malformed_frames,
                "error_frames": self.error_frames, "delays_ms": self.delays_ms,
                "notes": list(self.notes)}


@dataclass
class _ServerState:
    scripts: dict[str, FixtureScript]
    calls: dict[str, int]
    requests: list[RecordedRequest]
    stats: dict[tuple[str, str], list[WireFrame]]
    lock: threading.Lock = field(default_factory=threading.Lock)


class FixtureModelServer:
    """Loopback-only model server that replays :class:`FixtureScript` objects.

    The server never binds a non-loopback address, never reads credentials from
    the environment, never proxies a request, and refuses unknown models,
    paths, methods or bodies.  A script may be replayed indefinitely by
    default; ``max_calls`` gives adversarial tests a fail-closed budget.
    """

    _LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

    def __init__(self, scripts: Sequence[FixtureScript] | None = None, *,
                 host: str = "127.0.0.1",
                 sleeper: Callable[[int], None] | None = None) -> None:
        if host not in self._LOOPBACK_HOSTS:
            raise ValidationError(f"refusing to bind non-loopback host {host!r}")
        chosen = tuple(standard_scripts() if scripts is None else scripts)
        by_name: dict[str, FixtureScript] = {}
        by_model: dict[str, FixtureScript] = {}
        for script in chosen:
            if not isinstance(script, FixtureScript):
                raise ValidationError("scripts must contain FixtureScript values")
            if script.name in by_name:
                raise ValidationError(f"duplicate script name {script.name!r}")
            if script.model in by_model:
                raise ValidationError(f"duplicate script model {script.model!r}")
            if script.name in by_model and by_model[script.name] is not script:
                raise ValidationError(f"ambiguous script selector {script.name!r}")
            if script.model in by_name and by_name[script.model] is not script:
                raise ValidationError(f"ambiguous script selector {script.model!r}")
            by_name[script.name] = script
            by_model[script.model] = script
        self._host = host
        self._sleeper = sleeper if sleeper is not None else (lambda _ms: None)
        if not callable(self._sleeper):
            raise ValidationError("sleeper must be callable")
        lookup = dict(by_name)
        lookup.update(by_model)  # a request may select a script by model id
        self._state = _ServerState(lookup,
                                   {name: 0 for name in by_name}, [], {})
        self._httpd = _FixtureHTTPServer((host, 0), _FixtureHandler)
        self._httpd.fixture = self
        self._httpd.daemon_threads = True
        self._thread: threading.Thread | None = None
        self._closed = False

    @property
    def host(self) -> str:
        return self._host

    @property
    def base_url(self) -> str:
        host = f"[{self._host}]" if ":" in self._host else self._host
        return f"http://{host}:{self._httpd.server_address[1]}"

    @property
    def requests(self) -> tuple[RecordedRequest, ...]:
        with self._state.lock:
            return tuple(self._state.requests)

    def stream_stats(self, script_name: str, dialect: Dialect) -> StreamStats:
        with self._state.lock:
            frames = list(self._state.stats.get((script_name, dialect.value), ()))
        return StreamStats(
            frames_sent=len(frames),
            terminated=any(f.terminate for f in frames),
            malformed_frames=sum(f.note == "malformed_json" for f in frames),
            error_frames=sum(f.note == "error" for f in frames),
            delays_ms=sum(f.delay_ms for f in frames),
            notes=tuple(f.note for f in frames),
        )

    def start(self) -> "FixtureModelServer":
        if self._closed:
            raise ReliabilityError("fixture server is closed")
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._httpd.serve_forever,
                kwargs={"poll_interval": 0.01}, daemon=True,
                name="keel-fixture-model-server")
            self._thread.start()
        return self

    def reset(self) -> None:
        with self._state.lock:
            self._state.requests.clear()
            self._state.stats.clear()
            for name in self._state.calls:
                self._state.calls[name] = 0

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._thread is not None:
            self._httpd.shutdown()
            self._thread.join(timeout=5)
        self._httpd.server_close()

    def __enter__(self) -> "FixtureModelServer":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- handler implementation (called on server threads) -----------------

    def _send_json(self, handler: BaseHTTPRequestHandler, status: int,
                   payload: dict) -> None:
        body = canonical_bytes(payload)
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        handler.wfile.flush()

    def _dialect_for_path(self, path: str) -> Dialect | None:
        if path == _DIALECT_PATHS["openai_chat"]:
            return Dialect.OPENAI_CHAT
        if path == _DIALECT_PATHS["anthropic_messages"]:
            return Dialect.ANTHROPIC_MESSAGES
        if (path.startswith("/v1beta/models/")
                and path.endswith(":streamGenerateContent")):
            return Dialect.GEMINI_GENERATE
        return None

    def handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        try:
            self._handle_post(handler)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # A cancelled or timed-out client is an observed outcome.
            return

    def _handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urllib.parse.urlsplit(handler.path)
        dialect = self._dialect_for_path(parsed.path)
        if dialect is None:
            self._send_json(handler, 404, {"error": "unknown fixture endpoint",
                                           "path": parsed.path})
            return
        raw_length = handler.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            self._send_json(handler, 400, {"error": "invalid content length"})
            return
        if length < 0:
            self._send_json(handler, 400, {"error": "invalid content length"})
            return
        if length > MAX_BODY_BYTES:
            # Drain a bounded amount so the client finishes its write before
            # the refusal; a larger body is still refused, never processed.
            remaining = min(length, 8 << 20)
            while remaining > 0:
                chunk = handler.rfile.read(min(65_536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            self._send_json(handler, 413, {"error": "request body too large"})
            return
        raw = handler.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(handler, 400, {"error": "request body is not JSON"})
            return
        if not isinstance(body, dict):
            self._send_json(handler, 400, {"error": "request body must be an object"})
            return
        model = handler.headers.get("X-Keel-Fixture-Script")
        if model is None:
            if dialect is Dialect.GEMINI_GENERATE:
                segment = parsed.path[len("/v1beta/models/"):-len(":streamGenerateContent")]
                model = urllib.parse.unquote(segment)
            else:
                candidate = body.get("model")
                model = candidate if isinstance(candidate, str) else ""
        with self._state.lock:
            script = self._state.scripts.get(model)
            if script is None:
                self._send_json(handler, 503,
                                {"error": "unknown fixture model", "model": model})
                return
            if script.dialect is not None and script.dialect is not dialect:
                self._send_json(handler, 400,
                                {"error": "script bound to another dialect",
                                 "model": model})
                return
            count = self._state.calls[script.name]
            if script.max_calls and count >= script.max_calls:
                self._send_json(handler, 503,
                                {"error": "fixture script call budget exhausted",
                                 "script": script.name})
                return
            self._state.calls[script.name] = count + 1
            self._state.requests.append(RecordedRequest(
                ordinal=len(self._state.requests) + 1, method="POST",
                path=parsed.path, headers=dict(handler.headers.items()),
                body=body, script_name=script.name))
            frames = script.frames(dialect)
            key = (script.name, dialect.value)
            self._state.stats.setdefault(key, []).extend(frames)
        try:
            first = frames[0]
            if first.status >= 400:
                self._send_json(handler, first.status,
                                json.loads(first.payload.decode("utf-8")))
                return
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            for frame in frames:
                if frame.delay_ms:
                    self._sleeper(frame.delay_ms)
                if frame.terminate:
                    # Deliberately cut without [DONE] and without a final chunk.
                    break
                handler.wfile.write(frame.payload)
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            # A cancelled client is an observed outcome, not a server failure.
            return


class _FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "KeelFixtureModel/1.0"

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.server.fixture.handle_post(self)  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        self.server.fixture._send_json(
            self, 405, {"error": "only POST is supported by the fixture"})

    def log_message(self, fmt: str, *args: Any) -> None:
        return  # fixtures must not write to stderr


class _FixtureHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    fixture: FixtureModelServer


def make_fixture_server(scripts: Sequence[FixtureScript] | None = None, *,
                        host: str = "127.0.0.1",
                        sleeper: Callable[[int], None] | None = None
                        ) -> FixtureModelServer:
    """Convenience constructor with the shared standard script set."""
    return FixtureModelServer(scripts, host=host, sleeper=sleeper)


# ---------------------------------------------------------------------------
# X9.3 -- shared provider behaviour suite
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdapterRequest:
    """The neutral request every adapter under test must accept."""

    model: str
    messages: tuple[dict, ...] = ({"role": "user", "content": "hello fixture"},)
    tools: tuple[dict, ...] = ()
    max_output_tokens: int = 256
    temperature: float = 0.0

    def __post_init__(self) -> None:
        _require_str(self.model, "model")
        if not isinstance(self.messages, tuple) or not all(
                isinstance(m, dict) for m in self.messages):
            raise ValidationError("messages must be a tuple of dicts")
        if not isinstance(self.tools, tuple) or not all(
                isinstance(t, dict) for t in self.tools):
            raise ValidationError("tools must be a tuple of dicts")
        _require_int(self.max_output_tokens, "max_output_tokens", minimum=1)
        if isinstance(self.temperature, bool) or not isinstance(
                self.temperature, (int, float)) or not 0.0 <= self.temperature <= 2.0:
            raise ValidationError("temperature must be a number in 0..2")


class KeelAdapter:
    """Adapter for any keel provider adapter speaking the neutral event seam."""

    def __init__(self, name: str, adapter: Any) -> None:
        _require_str(name, "name")
        if not callable(getattr(adapter, "complete", None)):
            raise ValidationError("adapter must expose complete(request)")
        self.name = name
        self._adapter = adapter

    def events(self, request: AdapterRequest) -> Iterator[dict]:
        from keel.providers.base import ProviderRequest  # lazy: suite stays import-pure

        neutral = ProviderRequest(
            model=request.model,
            messages=[dict(m) for m in request.messages],
            tools=[dict(t) for t in request.tools],
            max_output_tokens=request.max_output_tokens,
            temperature=request.temperature,
        )
        return iter(self._adapter.complete(neutral))


class CancellingAdapter:
    """Cancels an adapter stream after N events and closes the source."""

    def __init__(self, delegate: Any, after_events: int) -> None:
        if not callable(getattr(delegate, "events", None)):
            raise ValidationError("delegate must expose events(request)")
        _require_int(after_events, "after_events", minimum=1)
        self._delegate = delegate
        self.after_events = after_events
        self.sources_closed = 0

    def events(self, request: AdapterRequest) -> Iterator[dict]:
        source = iter(self._delegate.events(request))

        end = object()

        def gen() -> Iterator[dict]:
            try:
                for _ in range(self.after_events):
                    event = next(source, end)
                    if event is end:
                        return
                    yield event
            finally:
                close = getattr(source, "close", None)
                if close is not None:
                    close()
                self.sources_closed += 1

        return gen()


class TrackingHTTPTransport:
    """stdlib urllib transport that records calls and closes responses.

    Returning status codes (including HTTP errors) instead of raising keeps
    the real provider adapters responsible for their own typed error mapping.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.closed_count = 0

    def __call__(self, request: dict) -> tuple[int, dict, Iterator[bytes]]:
        if not isinstance(request, dict) or not isinstance(request.get("url"), str):
            raise ValidationError("transport request needs a url")
        url = urllib.parse.urlsplit(request["url"])
        if url.scheme != "http" or url.hostname not in FixtureModelServer._LOOPBACK_HOSTS:
            raise ValidationError("contract suite allows only loopback http URLs")
        self.calls.append(dict(request))
        body = request.get("body_bytes")
        if body is None and request.get("body_json") is not None:
            body = canonical_bytes(request["body_json"])
        req = urllib.request.Request(request["url"], data=body,
                                     headers=dict(request.get("headers", {})),
                                     method=request.get("method", "POST"))
        try:
            response = urllib.request.urlopen(req, timeout=request.get("timeout", 10))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, dict(exc.headers.items()), iter((raw,))
        except urllib.error.URLError as exc:
            raise ReliabilityError(f"fixture connection failed: {exc.reason}") from None
        headers = dict(response.headers.items())

        def chunks() -> Iterator[bytes]:
            try:
                while True:
                    piece = response.read(4096)
                    if not piece:
                        break
                    yield piece
            finally:
                response.close()
                self.closed_count += 1

        return response.status, headers, chunks()


@dataclass(frozen=True)
class AdapterBinding:
    """How to build one real adapter against the fixture server."""

    name: str
    dialect: Dialect
    build: Callable[[str, Callable[..., Any]], Any]

    def __post_init__(self) -> None:
        _require_str(self.name, "name")
        if not isinstance(self.dialect, Dialect):
            raise ValidationError("dialect must be a Dialect value")
        if not callable(self.build):
            raise ValidationError("build must be callable")

    def base_url(self, server: FixtureModelServer) -> str:
        if self.dialect is Dialect.GEMINI_GENERATE:
            return server.base_url + "/v1beta"
        # OpenAI-compatible and Anthropic adapters append their own endpoint
        # to the supplied base URL.
        return server.base_url + "/v1"


@dataclass(frozen=True)
class BehaviorCase:
    name: str
    script_name: str
    description: str


@dataclass(frozen=True)
class BehaviorResult:
    adapter: str
    case: str
    ok: bool
    detail: str
    events: tuple[dict, ...] = ()
    request: dict | None = None
    transport_closed: bool = False

    def as_dict(self) -> dict:
        # Drop the ephemeral loopback port from the URL so fingerprints are
        # stable across runs; the path still proves which endpoint was used.
        request = dict(self.request) if self.request is not None else None
        if request is not None and isinstance(request.get("url"), str):
            parts = urllib.parse.urlsplit(request["url"])
            request["url"] = parts.path + (("?" + parts.query) if parts.query else "")
        return {"adapter": self.adapter, "case": self.case, "ok": self.ok,
                "detail": self.detail,
                "events": [_jsonable(e) for e in self.events],
                "request": _jsonable(request),
                "transport_closed": self.transport_closed}


@dataclass(frozen=True)
class ContractReport:
    adapter: str
    results: tuple[BehaviorResult, ...]

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(r.ok for r in self.results)

    @property
    def failures(self) -> tuple[BehaviorResult, ...]:
        return tuple(r for r in self.results if not r.ok)

    @property
    def fingerprint(self) -> str:
        return fingerprint([r.as_dict() for r in self.results])

    def as_dict(self) -> dict:
        return {"adapter": self.adapter, "ok": self.ok,
                "results": [r.as_dict() for r in self.results],
                "fingerprint": self.fingerprint}


EXPECTED_ERROR_CATEGORIES: dict[int, tuple[str, bool]] = {
    400: ("invalid_request", False), 401: ("authentication_failed", False),
    403: ("organization_not_allowed", False), 404: ("model_not_found", False),
    408: ("rate_limit", True), 429: ("rate_limit", True),
    500: ("server_error", True), 502: ("server_error", True),
    503: ("overloaded", True),
}


def _text_of(events: Sequence[dict]) -> str:
    return "".join(str(e.get("text", "")) for e in events
                   if e.get("event") == "text_delta")


def _tools_of(events: Sequence[dict]) -> dict[int, dict]:
    tools: dict[int, dict] = {}
    for event in events:
        name = event.get("event")
        index = event.get("index", 0)
        if name == "block_start":
            block = event.get("block") or {}
            if block.get("type") == "tool_use":
                tools[index] = {"id": block.get("id"), "name": block.get("name"),
                                "input": dict(block.get("input") or {})}
        elif name == "tool_input" and isinstance(event.get("input"), dict):
            entry = tools.setdefault(index, {"id": None, "name": "", "input": {}})
            entry["input"].update(event["input"])
    return tools


def _usage_of(events: Sequence[dict]) -> dict | None:
    for event in events:
        if event.get("event") == "usage":
            usage = event.get("usage")
            if usage is None:
                return None
            if isinstance(usage, Mapping):
                return dict(usage)
            return dict(vars(usage))  # keel's UsageRecord dataclass
    return None


def _expected_script(server: FixtureModelServer, name: str) -> FixtureScript:
    for script in server._state.scripts.values():  # read-only lookup
        if script.name == name:
            return script
    raise ValidationError(f"fixture server has no script {name!r}")


def _adapter_request(script: FixtureScript) -> AdapterRequest:
    tools = ()
    if any(e.kind is EventKind.TOOL_CALL for e in script.events):
        tools = ({"name": "get_weather",
                  "description": "fixture tool",
                  "input_schema": {"type": "object", "properties": {}}},)
    return AdapterRequest(model=script.model, tools=tools)


def default_bindings() -> tuple[AdapterBinding, ...]:
    """Bindings for the three real adapters; lazy so import stays pure."""
    try:
        from keel.providers.anthropic import AnthropicAdapter
        from keel.providers.base import CapabilityRecord
        from keel.providers.gemini import GeminiAdapter
        from keel.providers.openai_compatible import OpenAICompatibleAdapter
    except ImportError as exc:  # pragma: no cover - keel is normally present
        raise ReliabilityError(f"provider adapters unavailable: {exc}") from None

    def capability(name: str, base_url: str) -> CapabilityRecord:
        return CapabilityRecord(name=name, base_url=base_url,
                                env_var="KEEL_FIXTURE_UNUSED_KEY",
                                default_model="fx-stream")

    return (
        AdapterBinding("openai-compatible", Dialect.OPENAI_CHAT,
                       lambda url, transport: KeelAdapter(
                           "openai-compatible",
                           OpenAICompatibleAdapter(
                               capability("fixture-openai", url),
                               api_key="fixture-key", transport=transport))),
        AdapterBinding("anthropic", Dialect.ANTHROPIC_MESSAGES,
                       lambda url, transport: KeelAdapter(
                           "anthropic",
                           AnthropicAdapter(
                               capability("fixture-anthropic", url),
                               api_key="fixture-key", transport=transport))),
        AdapterBinding("google-gemini", Dialect.GEMINI_GENERATE,
                       lambda url, transport: KeelAdapter(
                           "google-gemini",
                           GeminiAdapter(
                               capability("fixture-gemini", url),
                               api_key="fixture-key", transport=transport))),
    )


class ProviderContractSuite:
    """One behaviour suite applied unchanged to every provider adapter."""

    CASES: tuple[BehaviorCase, ...] = (
        BehaviorCase("streaming", "stream", "ordered text deltas and stop"),
        BehaviorCase("tool_call", "tool_call", "assembled tool arguments"),
        BehaviorCase("usage", "usage", "provider-reported token counts only"),
        BehaviorCase("errors", "error", "typed, non-retryable-invented error"),
        BehaviorCase("malformed_json", "malformed_json", "bad frame is not content"),
        BehaviorCase("partial_stream", "partial_stream", "incomplete wire is reported"),
        BehaviorCase("slow_tokens", "slow_tokens", "delayed tokens stay in order"),
        BehaviorCase("cancel", "stream", "consumer cancels and closes the stream"),
    )

    def run(self, binding: AdapterBinding, server: FixtureModelServer) -> ContractReport:
        results: list[BehaviorResult] = []
        for case in self.CASES:
            results.append(self._run_case(binding, server, case))
        return ContractReport(binding.name, tuple(results))

    def _run_case(self, binding: AdapterBinding, server: FixtureModelServer,
                  case: BehaviorCase) -> BehaviorResult:
        script = _expected_script(server, case.script_name)
        transport = TrackingHTTPTransport()
        adapter = binding.build(binding.base_url(server), transport)
        request = _adapter_request(script)

        if case.name == "cancel":
            cancelling = CancellingAdapter(adapter, after_events=2)
            stream = cancelling.events(request)
            events: list[dict] = []
            try:
                for _ in range(2):
                    events.append(next(stream))
            except StopIteration:
                return BehaviorResult(binding.name, case.name, False,
                                      "stream ended before two events")
            finally:
                stream.close()
            delivered = tuple(events)
            ok = (cancelling.sources_closed == 1
                  and len(delivered) == 2
                  and _text_of(delivered) == "He"
                  and transport.closed_count >= 1
                  and len(transport.calls) == 1)
            return BehaviorResult(
                binding.name, case.name, ok,
                "cancelled after 2 events; source closed "
                f"{cancelling.sources_closed} time(s)" if ok
                else "cancel contract violated",
                delivered, transport.calls[0] if transport.calls else None,
                transport.closed_count > 0)

        try:
            events = list(adapter.events(request))
        except Exception as exc:  # typed adapter/provider failures are data here
            category = getattr(exc, "category", None)
            status = getattr(exc, "status", None)
            expected = EXPECTED_ERROR_CATEGORIES.get(script.events[0].status)
            if case.name != "errors":
                return BehaviorResult(binding.name, case.name, False,
                                      f"unexpected {type(exc).__name__}: {exc}",
                                      (), transport.calls[0] if transport.calls else None)
            ok = (category == expected[0] and status == script.events[0].status
                  and getattr(exc, "retryable", None) is expected[1]
                  and transport.calls.__len__() == 1)
            stats = server.stream_stats(script.name, binding.dialect)
            ok = ok and stats.error_frames == 1
            return BehaviorResult(
                binding.name, case.name, ok,
                f"error category={category} status={status} retryable="
                f"{getattr(exc, 'retryable', None)}" if ok else
                f"error mapping wrong: category={category} status={status}",
                (), transport.calls[0] if transport.calls else None)

        delivered = tuple(events)
        stats = server.stream_stats(script.name, binding.dialect)
        has_stop = any(e.get("event") == "message_stop" for e in delivered)
        request_record = transport.calls[0] if transport.calls else None
        if case.name == "errors":
            return BehaviorResult(binding.name, case.name, False,
                                  "error script did not raise a typed error",
                                  delivered, request_record)

        if case.name in ("streaming", "slow_tokens"):
            expected_text = "".join(e.text for e in script.events
                                    if e.kind in (EventKind.TEXT, EventKind.SLOW_TOKEN))
            ok = (_text_of(delivered) == expected_text and has_stop
                  and len(transport.calls) == 1)
            if case.name == "slow_tokens":
                ok = ok and stats.delays_ms >= sum(
                    e.delay_ms for e in script.events
                    if e.kind is EventKind.SLOW_TOKEN)
            detail = f"text={_text_of(delivered)!r}, delays_ms={stats.delays_ms}"
        elif case.name == "tool_call":
            tools = _tools_of(delivered)
            expected_args = _tool_arguments(script)
            expected_name = next(e.tool_name for e in script.events
                                 if e.kind is EventKind.TOOL_CALL and e.tool_name)
            ok = (len(tools) == 1
                  and next(iter(tools.values()))["name"] == expected_name
                  and next(iter(tools.values()))["input"] == expected_args
                  and has_stop)
            detail = f"tools={tools!r}"
        elif case.name == "usage":
            usage = _usage_of(delivered)
            expected_usage = _usage(script)
            ok = (usage is not None and expected_usage is not None
                  and usage.get("input_tokens") == expected_usage.input_tokens
                  and usage.get("output_tokens") == expected_usage.output_tokens
                  and has_stop)
            detail = f"usage={usage!r}"
        elif case.name == "malformed_json":
            expected_text = "".join(e.text for e in script.events
                                    if e.kind is EventKind.TEXT)
            ok = (_text_of(delivered) == expected_text
                  and stats.malformed_frames == 1
                  and not _tools_of(delivered)
                  and has_stop)
            detail = (f"text={_text_of(delivered)!r}, "
                      f"malformed_frames={stats.malformed_frames}")
        elif case.name == "partial_stream":
            usage = _usage_of(delivered)
            # Some adapters emit a zero-valued usage block at message_start;
            # the contract only forbids *reported* token counts on a cut wire.
            counted = usage is not None and any(
                isinstance(v, int) and v > 0 for v in usage.values())
            expected_text = "".join(e.text for e in script.events
                                     if e.kind in (EventKind.TEXT,
                                                   EventKind.PARTIAL_STREAM))
            ok = (stats.terminated and not counted
                  and _text_of(delivered) == expected_text
                  and not _tools_of(delivered))
            detail = (f"terminated={stats.terminated}, counted={counted}, "
                      f"usage={usage!r}")
        else:  # pragma: no cover - CASES is a closed tuple
            ok = False
            detail = f"unknown case {case.name}"

        return BehaviorResult(binding.name, case.name, bool(ok), detail,
                              delivered, request_record,
                              transport.closed_count > 0)

    def run_all(self, server: FixtureModelServer) -> dict[str, ContractReport]:
        return {binding.name: self.run(binding, server)
                for binding in default_bindings()}


# ---------------------------------------------------------------------------
# X9.5 -- cross-platform path / permission matrix
# ---------------------------------------------------------------------------


class Platform(str, Enum):
    WINDOWS = "windows"
    POSIX = "posix"


class PathHazard(str, Enum):
    NONE = "none"
    ABSOLUTE = "absolute"
    UNC = "unc"
    DRIVE_QUALIFIED = "drive_qualified"
    PARENT_TRAVERSAL = "parent_traversal"
    NUL_OR_CONTROL = "nul_or_control"
    RESERVED_DEVICE_NAME = "reserved_device_name"
    ALTERNATE_DATA_STREAM = "alternate_data_stream"
    TRAILING_DOT_OR_SPACE = "trailing_dot_or_space"
    LONG_COMPONENT = "long_component"
    LONG_PATH = "long_path"
    CASE_COLLISION = "case_collision"
    NORMALIZATION_CONFLICT = "normalization_conflict"
    SYMLINK_ESCAPE = "symlink_escape"
    JUNCTION_ESCAPE = "junction_escape"


@dataclass(frozen=True)
class PathCase:
    path: str
    platform: Platform
    root: str = ""
    case_insensitive_fs: bool = False
    existing_paths: tuple[str, ...] = ()
    symlink_target: str | None = None
    junction_target: str | None = None
    # Independent expectation for the matrix runner. Empty means "expect a
    # safe path"; it is never used by evaluate_path itself.
    expected_hazards: tuple[PathHazard, ...] = ()

    def __post_init__(self) -> None:
        _require_str(self.path, "path")
        if not isinstance(self.platform, Platform):
            raise ValidationError("platform must be a Platform value")
        root = self.root or ("C:\\workspace" if self.platform is Platform.WINDOWS
                             else "/workspace")
        _require_str(root, "root")
        if not isinstance(self.case_insensitive_fs, bool):
            raise ValidationError("case_insensitive_fs must be a bool")
        if not isinstance(self.existing_paths, tuple) or not all(
                isinstance(p, str) for p in self.existing_paths):
            raise ValidationError("existing_paths must be a tuple of strings")
        for target in (self.symlink_target, self.junction_target):
            if target is not None and not isinstance(target, str):
                raise ValidationError("link targets must be strings or None")
        if not isinstance(self.expected_hazards, tuple) or not all(
                isinstance(h, PathHazard) for h in self.expected_hazards):
            raise ValidationError("expected_hazards must be a tuple of PathHazard")

    @property
    def effective_root(self) -> str:
        return self.root or ("C:\\workspace" if self.platform is Platform.WINDOWS
                             else "/workspace")


@dataclass(frozen=True)
class PathVerdict:
    case: PathCase
    allowed: bool
    hazards: tuple[PathHazard, ...]
    normalized: str
    reason: str

    @property
    def ok(self) -> bool:
        # ``allowed`` is already false when any real hazard was found; a safe
        # path carries the sentinel (NONE,) purely to keep the tuple stable.
        return self.allowed

    def as_dict(self) -> dict:
        return {"path": self.case.path, "platform": self.case.platform.value,
                "allowed": self.allowed,
                "hazards": [h.value for h in self.hazards],
                "normalized": self.normalized, "reason": self.reason}


def _win_parts(text: str) -> list[str]:
    return [p for p in text.replace("/", "\\").split("\\") if p]


def _posix_parts(text: str) -> list[str]:
    return [p for p in text.replace("\\", "/").split("/") if p]


def _parts(case: PathCase, text: str) -> list[str]:
    return _win_parts(text) if case.platform is Platform.WINDOWS else _posix_parts(text)


def _fold(case: PathCase, text: str) -> str:
    nfc = unicodedata.normalize("NFC", text)
    return nfc.casefold() if case.case_insensitive_fs else nfc


def _device_name(component: str) -> bool:
    stem = component.rstrip(". ").split(".", 1)[0].rstrip(". ").upper()
    if stem in _DEVICE_NAMES:
        return True
    # Superscript digits are accepted by Windows device-name parsing.
    for base, digits in (("COM", "¹²³"), ("LPT", "¹²³")):
        if stem.startswith(base) and len(stem) == len(base) + 1 and stem[-1] in digits:
            return True
    return False


def _is_absolute(case: PathCase, text: str) -> tuple[bool, PathHazard | None]:
    if case.platform is Platform.WINDOWS:
        if text.startswith("\\\\") or text.startswith("//"):
            return True, PathHazard.UNC
        if re.match(r"^[A-Za-z]:", text):
            return True, PathHazard.DRIVE_QUALIFIED
        if text.startswith(("/", "\\")):
            return True, PathHazard.ABSOLUTE
    else:
        if text.startswith("/"):
            return True, PathHazard.ABSOLUTE
        if re.match(r"^[A-Za-z]:", text):
            return True, PathHazard.DRIVE_QUALIFIED
        if text.startswith("\\\\"):
            return True, PathHazard.UNC
    return False, None


def _resolved_target(case: PathCase, target: str, link_parent: tuple[str, ...]
                     ) -> tuple[str, ...]:
    absolute, _ = _is_absolute(case, target)
    resolved = list(link_parent) if not absolute else []
    for part in _parts(case, target):
        if part in (".", ""):
            continue
        if part == "..":
            if resolved and resolved[-1] != "..":
                resolved.pop()
            elif not absolute:
                # Escaping above the link's base stays as an explicit marker;
                # a marker can never be contained by the root.
                resolved.append("..")
            continue
        resolved.append(part)
    return tuple(_fold(case, p) for p in resolved)


def _contained(case: PathCase, resolved: tuple[str, ...]) -> bool:
    root = tuple(_fold(case, p) for p in _parts(case, case.effective_root))
    # A drive-qualified root contributes a first component like "C:".
    return len(resolved) >= len(root) and resolved[:len(root)] == root


def evaluate_path(case: PathCase) -> PathVerdict:
    """Deterministically classify a repository-relative path.

    Purely lexical: no filesystem call can race the verdict or be fooled by a
    link planted between validation and use.  Link targets are supplied by the
    caller (a watcher/scanner) and resolved lexically against the link's parent.
    """
    hazards: list[PathHazard] = []
    absolute, hazard = _is_absolute(case, case.path)
    if absolute and hazard is not None:
        hazards.append(hazard)
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in case.path):
        hazards.append(PathHazard.NUL_OR_CONTROL)
    components = _parts(case, case.path)
    if any(part in (".", "..") for part in case.path.replace("\\", "/").split("/")):
        hazards.append(PathHazard.PARENT_TRAVERSAL)
    if not components:
        hazards.append(PathHazard.ABSOLUTE)

    for index, part in enumerate(components):
        if case.platform is Platform.WINDOWS:
            drive_part = index == 0 and bool(re.match(r"^[A-Za-z]:$", part))
            if ":" in part and not drive_part:
                hazards.append(PathHazard.ALTERNATE_DATA_STREAM)
            if part not in (".", "..") and part != part.rstrip(". "):
                hazards.append(PathHazard.TRAILING_DOT_OR_SPACE)
            if _device_name(part):
                hazards.append(PathHazard.RESERVED_DEVICE_NAME)
        if len(part) > 255:
            hazards.append(PathHazard.LONG_COMPONENT)
        if unicodedata.normalize("NFC", part) != part:
            hazards.append(PathHazard.NORMALIZATION_CONFLICT)

    full = _parts(case, case.effective_root) + components
    if case.platform is Platform.WINDOWS:
        if sum(len(p) + 1 for p in full) > 260:
            hazards.append(PathHazard.LONG_PATH)
    elif sum(len(p) + 1 for p in full) > 4096:
        hazards.append(PathHazard.LONG_PATH)

    existing = {_fold(case, "/".join(_parts(case, p))) for p in case.existing_paths}
    candidate = _fold(case, "/".join(components))
    if case.case_insensitive_fs and candidate in existing:
        hazards.append(PathHazard.CASE_COLLISION)

    link_parent = tuple(_fold(case, p) for p in full[:-1])
    if case.symlink_target is not None:
        resolved = _resolved_target(case, case.symlink_target, link_parent)
        if not _contained(case, resolved):
            hazards.append(PathHazard.SYMLINK_ESCAPE)
    if case.junction_target is not None:
        absolute_target, kind = _is_absolute(case, case.junction_target)
        resolved = _resolved_target(case, case.junction_target, link_parent)
        if not absolute_target or not _contained(case, resolved) or kind is PathHazard.UNC:
            hazards.append(PathHazard.JUNCTION_ESCAPE)

    # Stable order, no duplicates.
    unique = tuple(dict.fromkeys(hazards)) or (PathHazard.NONE,)
    allowed = all(h is PathHazard.NONE for h in unique)
    reasons = {
        PathHazard.RESERVED_DEVICE_NAME: "windows reserved device name",
        PathHazard.ALTERNATE_DATA_STREAM: "alternate data stream syntax",
        PathHazard.LONG_PATH: "path exceeds the platform limit",
        PathHazard.LONG_COMPONENT: "path component exceeds NAME_MAX",
        PathHazard.CASE_COLLISION: "collides on a case-insensitive filesystem",
        PathHazard.SYMLINK_ESCAPE: "symlink target escapes the containment root",
        PathHazard.JUNCTION_ESCAPE: "junction target escapes the containment root",
    }
    reason = "; ".join(reasons.get(h, h.value) for h in unique)
    return PathVerdict(case, allowed, unique,
                       "/".join(components) if case.platform is Platform.POSIX
                       else "\\".join(components), reason)


class Permission(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    ADMIN = "admin"


class Principal(str, Enum):
    USER = "user"
    AGENT = "agent"
    SANDBOX = "sandbox"
    GUEST = "guest"


@dataclass(frozen=True)
class PermissionRequest:
    principal: Principal
    permission: Permission
    path_case: PathCase
    approval_granted: bool = False
    elevated_token: bool = False
    # Independent expectation for the matrix runner; None fails closed.
    expected_allowed: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.principal, Principal):
            raise ValidationError("principal must be a Principal value")
        if not isinstance(self.permission, Permission):
            raise ValidationError("permission must be a Permission value")
        if not isinstance(self.path_case, PathCase):
            raise ValidationError("path_case must be a PathCase")
        if not isinstance(self.approval_granted, bool) or not isinstance(
                self.elevated_token, bool):
            raise ValidationError("approval flags must be bools")
        if self.expected_allowed is not None and not isinstance(
                self.expected_allowed, bool):
            raise ValidationError("expected_allowed must be a bool or None")


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str
    obligations: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.allowed

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "reason": self.reason,
                "obligations": list(self.obligations)}


def evaluate_permission(request: PermissionRequest) -> PermissionDecision:
    """Deny-by-default permission decision; approval never bypasses hazards."""
    verdict = evaluate_path(request.path_case)
    if not verdict.allowed:
        return PermissionDecision(False, f"unsafe path: {verdict.reason}")
    if request.principal is Principal.GUEST:
        return PermissionDecision(False, "guest principals have no grants")
    if request.permission is Permission.ADMIN:
        if request.principal is Principal.USER and request.elevated_token:
            return PermissionDecision(True, "elevated user admin",
                                       ("audit", "timeboxed"))
        return PermissionDecision(False, "admin requires an elevated user token")
    if request.principal is Principal.SANDBOX and request.permission in (
            Permission.WRITE, Permission.DELETE, Permission.EXECUTE):
        return PermissionDecision(False, "sandbox is read-only and non-executing")
    if request.permission in (Permission.WRITE, Permission.DELETE):
        if request.principal is Principal.AGENT and not request.approval_granted:
            return PermissionDecision(False, "agent mutation requires approval")
        if request.principal is Principal.AGENT:
            return PermissionDecision(True, "approved agent mutation", ("audit",))
        return PermissionDecision(True, f"user {request.permission.value}")
    if request.permission is Permission.EXECUTE:
        return PermissionDecision(True, "execute from a contained path")
    return PermissionDecision(True, "read from a contained path")


@dataclass(frozen=True)
class MatrixReport:
    name: str
    entries: tuple[tuple[str, bool, str], ...]

    @property
    def ok(self) -> bool:
        return bool(self.entries) and all(entry[1] for entry in self.entries)

    @property
    def failures(self) -> tuple[tuple[str, bool, str], ...]:
        return tuple(entry for entry in self.entries if not entry[1])

    @property
    def fingerprint(self) -> str:
        return fingerprint([[name, ok, detail] for name, ok, detail in self.entries])

    def as_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok,
                "entries": [list(e) for e in self.entries],
                "fingerprint": self.fingerprint}


def path_matrix() -> tuple[PathCase, ...]:
    """The cross-platform path matrix (hazards + safe controls).

    Expectations are declared independently of :func:`evaluate_path`; the
    runner fails if the classifier disagrees with them in either direction.
    """
    long_path = "\\".join(["folder"] * 40)
    H = PathHazard
    return (
        PathCase("reports/q3.md", Platform.WINDOWS),
        PathCase("reports/q3.md", Platform.POSIX),
        PathCase("CON", Platform.WINDOWS, expected_hazards=(H.RESERVED_DEVICE_NAME,)),
        PathCase("dir\\aux.txt", Platform.WINDOWS,
                 expected_hazards=(H.RESERVED_DEVICE_NAME,)),
        PathCase("dir\\COM1.log", Platform.WINDOWS,
                 expected_hazards=(H.RESERVED_DEVICE_NAME,)),
        PathCase("dir\\LPT9", Platform.WINDOWS,
                 expected_hazards=(H.RESERVED_DEVICE_NAME,)),
        PathCase("notes.txt:secret", Platform.WINDOWS,
                 expected_hazards=(H.ALTERNATE_DATA_STREAM,)),
        PathCase("notes.txt ", Platform.WINDOWS,
                 expected_hazards=(H.TRAILING_DOT_OR_SPACE,)),
        PathCase("notes.txt.", Platform.WINDOWS,
                 expected_hazards=(H.TRAILING_DOT_OR_SPACE,)),
        PathCase(long_path, Platform.WINDOWS, expected_hazards=(H.LONG_PATH,)),
        PathCase("dir/" + "b" * 300, Platform.POSIX,
                 expected_hazards=(H.LONG_COMPONENT,)),
        PathCase("docs/README.md", Platform.WINDOWS,
                 case_insensitive_fs=True, existing_paths=("docs/readme.MD",),
                 expected_hazards=(H.CASE_COLLISION,)),
        PathCase("docs/README.md", Platform.POSIX,
                 existing_paths=("docs/readme.MD",)),
        PathCase("docs/cafe\u0301.md", Platform.WINDOWS,
                 case_insensitive_fs=True,
                 expected_hazards=(H.NORMALIZATION_CONFLICT,)),
        PathCase("../outside.txt", Platform.WINDOWS,
                 expected_hazards=(H.PARENT_TRAVERSAL,)),
        PathCase("C:\\Windows\\evil.txt", Platform.WINDOWS,
                 expected_hazards=(H.DRIVE_QUALIFIED,)),
        PathCase("\\\\server\\share\\evil.txt", Platform.WINDOWS,
                 expected_hazards=(H.UNC,)),
        PathCase("link.txt", Platform.WINDOWS,
                 symlink_target="..\\secrets\\key.txt",
                 expected_hazards=(H.SYMLINK_ESCAPE,)),
        PathCase("sub/link.txt", Platform.POSIX,
                 symlink_target="../../etc/passwd",
                 expected_hazards=(H.SYMLINK_ESCAPE,)),
        PathCase("sub/link.txt", Platform.POSIX,
                 symlink_target="sibling/ok.txt"),
        PathCase("junction", Platform.WINDOWS,
                 junction_target="C:\\other\\volume",
                 expected_hazards=(H.JUNCTION_ESCAPE,)),
        PathCase("junction", Platform.WINDOWS,
                 junction_target="relative\\target",
                 expected_hazards=(H.JUNCTION_ESCAPE,)),
        PathCase("link.txt", Platform.WINDOWS,
                 symlink_target="..\\workspace\\safe.txt"),
    )


def run_path_matrix(cases: Sequence[PathCase] | None = None) -> MatrixReport:
    chosen = tuple(path_matrix() if cases is None else cases)
    if not chosen:
        raise ValidationError("path matrix needs at least one case")
    entries = []
    for case in chosen:
        verdict = evaluate_path(case)
        expected = tuple(case.expected_hazards)
        observed = tuple(h for h in verdict.hazards if h is not PathHazard.NONE)
        matched = observed == expected and verdict.ok == (not expected)
        label = f"{case.platform.value}:{case.path[:48]!r}"
        entries.append((label, matched,
                        f"expected={[h.value for h in expected]} "
                        f"observed={[h.value for h in observed]}"))
    return MatrixReport("x9.5-paths", tuple(entries))


def permission_matrix() -> tuple[PermissionRequest, ...]:
    """Explicit principal x permission x approval/elevation expectation table."""
    safe = PathCase("reports/q3.md", Platform.WINDOWS)
    unsafe = PathCase("CON", Platform.WINDOWS)
    requests: list[PermissionRequest] = []
    for principal in Principal:
        for permission in Permission:
            for approved, elevated in ((False, False), (True, True)):
                if principal is Principal.GUEST:
                    expected = False
                elif principal is Principal.SANDBOX:
                    expected = permission is Permission.READ
                elif principal is Principal.AGENT:
                    if permission in (Permission.WRITE, Permission.DELETE):
                        expected = approved
                    elif permission is Permission.ADMIN:
                        expected = False
                    else:
                        expected = True
                elif permission is Permission.ADMIN:
                    expected = elevated
                else:
                    expected = True
                requests.append(PermissionRequest(
                    principal, permission, safe,
                    approval_granted=approved, elevated_token=elevated,
                    expected_allowed=expected))
    requests.append(PermissionRequest(Principal.USER, Permission.READ, unsafe,
                                      expected_allowed=False))
    return tuple(requests)


def run_permission_matrix(requests: Sequence[PermissionRequest] | None = None
                          ) -> MatrixReport:
    chosen = tuple(permission_matrix() if requests is None else requests)
    if not chosen:
        raise ValidationError("permission matrix needs at least one request")
    entries = []
    for request in chosen:
        decision = evaluate_permission(request)
        matched = (request.expected_allowed is not None
                   and decision.ok is request.expected_allowed)
        label = (f"{request.principal.value}:{request.permission.value}:"
                 f"{request.path_case.path[:24]}:"
                 f"approved={request.approval_granted}")
        entries.append((label, matched,
                        f"expected={request.expected_allowed} "
                        f"observed={decision.ok} ({decision.reason})"))
    return MatrixReport("x9.5-permissions", tuple(entries))


# ---------------------------------------------------------------------------
# X9.7 -- migration matrix with data checksums
# ---------------------------------------------------------------------------

RELEASED_VERSIONS = tuple(range(1, 12))  # fleet.db currently reports schema 11
CURRENT_SCHEMA_VERSION = RELEASED_VERSIONS[-1]


def checksum_data(data: Mapping[str, Any]) -> str:
    """SHA-256 of canonical JSON -- no timestamps, no insertion-order effects."""
    if not isinstance(data, Mapping):
        raise ValidationError("checksum_data expects a mapping")
    return fingerprint(dict(data))


def _copy(data: Mapping[str, Any]) -> dict:
    return json.loads(canonical_bytes(dict(data)).decode("utf-8"))


def _migrate_2(data: dict) -> None:
    data.setdefault("policies", [])


def _migrate_3(data: dict) -> None:
    data.setdefault("groups", [])


def _migrate_4(data: dict) -> None:
    for key in ("tasks", "task_events", "library"):
        data.setdefault(key, [])


def _migrate_5(data: dict) -> None:
    for item in data.get("library", []):
        item.setdefault("routine_id", None)


def _migrate_6(data: dict) -> None:
    tasks = data.get("tasks", [])
    for position, task in enumerate(sorted(tasks, key=lambda t: (t["created_at"], t["id"]))):
        task.setdefault("position", position)
    for task in tasks:
        task.setdefault("prev_state", None)
        task.setdefault("deleted_at", None)
    for bot in data.get("bots", []):
        bot.setdefault("reasoning_effort", None)


def _migrate_7(data: dict) -> None:
    data.setdefault("projects", [])


def _migrate_8(data: dict) -> None:
    for project in data.get("projects", []):
        project.setdefault("trusted", 0)


def _migrate_9(data: dict) -> None:
    for bot in data.get("bots", []):
        bot.setdefault("project_id", None)


def _migrate_10(data: dict) -> None:
    for bot in data.get("bots", []):
        bot.setdefault("kind", "agent")


def _migrate_11(data: dict) -> None:
    data.setdefault("usage", [])


#: from_version -> (to_version, transform).  v1 is the baseline DDL, so the
#: first migration step is 1 -> 2.  Transforms are real, data-preserving edits.
MIGRATIONS: dict[int, tuple[int, Callable[[dict], None]]] = {
    1: (2, _migrate_2), 2: (3, _migrate_3), 3: (4, _migrate_4),
    4: (5, _migrate_5), 5: (6, _migrate_6), 6: (7, _migrate_7),
    7: (8, _migrate_8), 8: (9, _migrate_9), 9: (10, _migrate_10),
    10: (11, _migrate_11),
}


def payload_view(data: Mapping[str, Any]) -> dict:
    """The stable subset that must survive every migration unchanged."""
    return {
        "bots": [{"id": b["id"], "name": b["name"]}
                 for b in sorted(data.get("bots", []), key=lambda b: b["id"])],
        "rows": [{"bot_id": r["bot_id"], "body": r["body"]}
                 for r in sorted(data.get("rows", []),
                                 key=lambda r: (r["bot_id"], r["body"]))],
        "tasks": [{"id": t["id"], "title": t["title"]}
                  for t in sorted(data.get("tasks", []), key=lambda t: t["id"])],
        "library": [{"id": x["id"], "sha256": x["sha256"]}
                    for x in sorted(data.get("library", []), key=lambda x: x["id"])],
    }


def build_version_fixture(version: int) -> dict:
    """Deterministic data shaped like ``fleet.db`` at a released version."""
    version = _require_int(version, "version", minimum=1,
                           maximum=CURRENT_SCHEMA_VERSION)
    data: dict = {
        "bots": [{"id": "bot-1", "name": "Alpha", "created_at": "2024-01-01T00:00:00Z"},
                 {"id": "bot-2", "name": "Beta", "created_at": "2024-01-02T00:00:00Z"}],
        "rows": [{"bot_id": "bot-2", "body": '{"kind":"message","text":"second"}'},
                 {"bot_id": "bot-1", "body": '{"kind":"message","text":"first"}'}],
        "tasks": [{"id": "task-b", "title": "Write docs",
                   "created_at": "2024-02-02T00:00:00Z"},
                  {"id": "task-a", "title": "Ship release",
                   "created_at": "2024-01-01T00:00:00Z"}],
        "library": [{"id": "lib-1", "sha256": "abc123"}],
    }
    # Reuse the production steps so each fixture really has that version's
    # shape (added columns/lists), while the payload stays identical.
    for step in RELEASED_VERSIONS:
        if step >= version:
            break
        MIGRATIONS[step][1](data)
    return data


@dataclass(frozen=True)
class MigrationResult:
    from_version: int
    to_version: int
    version_path: tuple[int, ...]
    checksum_before: str
    checksum_after: str
    payload_checksum_before: str
    payload_checksum_after: str
    obligations: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return bool(self.version_path) and (
            self.version_path[0] == self.from_version
            and self.version_path[-1] == self.to_version
            and self.from_version <= self.to_version
            and self.payload_checksum_before == self.payload_checksum_after)

    def as_dict(self) -> dict:
        return {"from_version": self.from_version, "to_version": self.to_version,
                "version_path": list(self.version_path),
                "checksum_before": self.checksum_before,
                "checksum_after": self.checksum_after,
                "payload_checksum_before": self.payload_checksum_before,
                "payload_checksum_after": self.payload_checksum_after,
                "obligations": list(self.obligations)}


class MigrationMatrix:
    """Upgrade each released version to current and verify data checksums."""

    def __init__(self, migrations: Mapping[int, tuple[int, Callable[[dict], None]]] | None = None,
                 current: int = CURRENT_SCHEMA_VERSION,
                 released: Sequence[int] = RELEASED_VERSIONS) -> None:
        table = dict(MIGRATIONS if migrations is None else migrations)
        for key, value in table.items():
            _require_int(key, "from_version", minimum=1)
            if not isinstance(value, tuple) or len(value) != 2 or not callable(value[1]):
                raise ValidationError(f"invalid migration step for version {key}")
            _require_int(value[0], "to_version", minimum=1)
        _require_int(current, "current", minimum=1)
        versions = tuple(released)
        if not versions or len(set(versions)) != len(versions):
            raise ValidationError("released versions must be unique and non-empty")
        self.migrations = table
        self.current = current
        self.released = versions

    def path(self, from_version: int) -> tuple[int, ...]:
        version = _require_int(from_version, "from_version", minimum=1)
        if version > self.current:
            raise ReliabilityError(f"cannot downgrade from v{version} to v{self.current}")
        path = [version]
        seen = {version}
        while path[-1] != self.current:
            step = self.migrations.get(path[-1])
            if step is None:
                raise ReliabilityError(
                    f"no migration step from v{path[-1]} to current v{self.current}")
            target = step[0]
            if target <= path[-1] or target > self.current or target in seen:
                raise ReliabilityError(f"invalid or cyclic migration step at v{path[-1]}")
            path.append(target)
            seen.add(target)
        return tuple(path)

    def upgrade(self, data: Mapping[str, Any], from_version: int, *,
                expected_checksum: str | None = None) -> MigrationResult:
        path = self.path(from_version)
        before = _copy(data)
        checksum_before = checksum_data(before)
        if expected_checksum is not None and expected_checksum != checksum_before:
            raise ReliabilityError("source data checksum mismatch; refusing to migrate")
        payload_before = checksum_data(payload_view(before))
        result = _copy(before)
        for version in path[:-1]:
            self.migrations[version][1](result)
        payload_after = checksum_data(payload_view(result))
        after_checksum = checksum_data(result)
        if payload_after != payload_before:
            raise ReliabilityError(
                f"v{from_version}->v{self.current} lost or changed payload data")
        return MigrationResult(
            from_version=from_version, to_version=self.current,
            version_path=path, checksum_before=checksum_before,
            checksum_after=after_checksum,
            payload_checksum_before=payload_before,
            payload_checksum_after=payload_after,
            obligations=("verify_checksum_before_write",))

    def run_all(self) -> tuple[MigrationResult, ...]:
        if self.current not in self.released:
            raise ReliabilityError("current version must be one of the released versions")
        results: list[MigrationResult] = []
        for version in self.released:
            fixture = build_version_fixture(version)
            results.append(self.upgrade(fixture, version,
                                        expected_checksum=checksum_data(fixture)))
        return tuple(results)
