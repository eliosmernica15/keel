"""Pure contracts for agent names, results, snapshots, isolation and change logs.

This module is the stdlib-only, descriptor/policy surface used by five P0
addendum-7 rows (``E3.3``, ``E3.8``, ``E4.5``, ``E4.8``, ``E4.15``).  It holds
no host state: no files, no network, no subprocess, no clock, no chance input
and no credential storage.  Callers own every identifier, message, path, port
and record; the functions here only validate, resolve, derive and compare.
``to_dict``/``from_dict`` exchange plain data so a caller may persist it through
its own storage layer.

Feature map
-----------
* **E3.3** -- ``validate_agent_name``/``make_agent_name`` enforce 1-32 lowercase
  letters/digits/hyphens starting with a letter, with ``lead`` reserved for the
  root.  Full names are slash paths.  ``AgentRegistry``/``resolve_name`` return
  only the authoritative session id (names are model-facing references and
  grant no permission); a path with no match raises ``AgentNameNotFoundError``
  (code ``AGENT_NAME_NOT_FOUND``).  ``default_agent_name`` yields ``agent-N``.
* **E3.8** -- ``Result``/``build_result`` define the final output as the last
  non-empty assistant message, with optional structured output validated
  against a requested (minimal JSON-Schema) schema.  ``sanitize_diagnostics``
  caps text at 4,096 UTF-8 bytes and strips tool inputs, file contents, env
  values, credentials and raw protocol payloads.  ``StopReason`` is the closed
  enum; ``child_failure_to_result``/``resolve_child_outcome`` turn child
  failures into an ``ERROR`` result, never an exception.
* **E4.5** -- ``parse_session_file`` reads the version from a parent/child
  session filename; ``validate_snapshot_pair`` requires it to agree with the
  header.  ``SnapshotConfig`` models snapshot.yml (profile, header class,
  recording policy, workspace facts); typed ``TypedToken`` objects bind parent
  and child identity; ``WorkspaceManifest``/``compare_workspace`` compare a full
  ``workspace.expected/`` tree, which ``snapshot_write_allowed`` and
  ``assert_expected_immutable`` protect from record/refresh rewrites.  Modes and
  the ``can_run_mode``/``review_all_diffs`` gates keep CI read-only and replay
  truthful.
* **E4.8** -- ``ResourceLease``/``detect_isolation_violations`` model forked
  workers sharing ports, paths, namespaces and children and require teardown
  ownership; ``ForkExit``/``fork_exit_diagnostic`` always report PID, file, code
  and signal; ``classify_flake`` treats a spec that passes only alone as a test
  defect and classifies probabilistic failures.
* **E4.15** -- ``ChangeRecord``/``ChangeLog`` implement a keyless recorded
  change log: every non-trivial model/protocol/human-visible change must name a
  recorded scenario and its test tiers, and new capability seams/lifecycle
  variants must name every required tier at plan time.  ``TestTier`` mirrors the
  test-plan legend (U/C/I/G/P/E/A/S/D/F).

Security invariants (enforced by ``test_result_contracts``):

* every unknown or malformed value fails closed (never silently permissive);
* no credential value survives a boundary -- not in a result, error, change
  record, diagnostic or serialized form;
* name resolution returns identity only and never a permission;
* snapshot expected trees are immutable to record/refresh and CI never writes;
* no test can silently share a resource or leak a fork-exit field.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

FEATURE_IDS = ("E3.3", "E3.8", "E4.5", "E4.8", "E4.15")

# ---------------------------------------------------------------------------
# Shared policy constants and fail-closed errors
# ---------------------------------------------------------------------------

DIAGNOSTIC_BYTE_LIMIT = 4096
ROOT_AGENT_NAME = "lead"
DEFAULT_AGENT_PREFIX = "agent-"
MAX_AGENT_NAME_LEN = 32
AGENT_NAME_NOT_FOUND = "AGENT_NAME_NOT_FOUND"
EXPECTED_TREE_ROOT = "workspace.expected"

_CREDENTIAL_PREFIX_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9_\-]{8,}|"
    r"xox[baprs]-[A-Za-z0-9_\-]{8,}|AKIA[A-Z0-9]{8,}|"
    r"AIza[A-Za-z0-9_\-]{8,})"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r'(?i)(?P<key>\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|'
    r'secret|password|passwd|credential|authorization|bearer)\b)'
    r'\s*[:=]\s*(?P<val>"[^"\n]*"|\'[^\'\n]*\'|[^\s,;}]+)'
)
_ENV_ASSIGNMENT_RE = re.compile(
    r"(?m)^[ \t]*(?:export[ \t]+)?(?P<name>[A-Z][A-Z0-9_]*)[ \t]*=[ \t]*(?P<val>.*)$"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{6,}")
_PEM_RE = re.compile(
    r"(?s)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
_FILE_BLOCK_RE = re.compile(
    r"(?is)<(?:file|file_contents|contents)>.*?</(?:file|file_contents|contents)>"
)
_TOOL_INPUT_RE = re.compile(
    r"(?i)\b(?P<label>tool[_-]?input|tool[_-]?use[_-]?id|input[_-]?json|"
    r"raw[_-]?payload|protocol[_-]?payload|base64[_-]?blob)\b.*$"
)
_SECRET_FIELD_TOKENS = frozenset({
    "key", "token", "secret", "password", "passwd", "credential",
    "authorization", "auth", "bearer",
})
_SAFE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]*$")
_SAFE_SCENARIO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./\-]*$")
_ENCODED_TRAVERSAL_RE = re.compile(r"(?i)%2e|%2f|%5c")


def _redact(value: Any) -> str:
    """Return text with literal credential material replaced."""
    text = "" if value is None else str(value)
    text = _PEM_RE.sub("[PRIVATE_KEY_REDACTED]", text)
    text = _CREDENTIAL_PREFIX_RE.sub("[REDACTED]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _SECRET_ASSIGNMENT_RE.sub(lambda m: "%s=[REDACTED]" % m.group("key"), text)
    return text


def looks_like_secret(value: Any) -> bool:
    """Best-effort detection of literal credential material in caller text."""
    text = "" if value is None else str(value)
    if not text:
        return False
    return bool(
        _CREDENTIAL_PREFIX_RE.search(text)
        or _BEARER_RE.search(text)
        or _SECRET_ASSIGNMENT_RE.search(text)
        or _PEM_RE.search(text)
    )


class ContractError(ValueError):
    """Base class for result-contract failures."""


class ContractValidationError(ContractError):
    """Fail-closed validation error; every message is redacted."""

    def __init__(self, errors: Any):
        if isinstance(errors, str):
            errors = (errors,)
        self.errors = tuple(str(e) for e in errors)
        super().__init__("; ".join(_redact(e) for e in self.errors))


class AgentNameNotFoundError(ContractError):
    """A slash path did not resolve; no permission is implied by the failure."""

    code = AGENT_NAME_NOT_FOUND

    def __init__(self, name: Any):
        self.name = str(name)
        super().__init__("%s: %s" % (AGENT_NAME_NOT_FOUND, self.name))


def _truncate_utf8(text: str, limit: int) -> str:
    """Truncate on codepoint boundaries so the UTF-8 encoding fits ``limit``."""
    if limit < 0:
        raise ContractValidationError("byte limit must be non-negative")
    if len(text.encode("utf-8")) <= limit:
        return text
    keep = max(0, limit - 3)
    out: list[str] = []
    used = 0
    for ch in text:
        size = len(ch.encode("utf-8"))
        if used + size > keep:
            break
        out.append(ch)
        used += size
    return "".join(out) + "..."


def _safe_identifier(value: Any, label: str = "identifier") -> str:
    text = str(value or "")
    if not text or not _SAFE_ID_RE.match(text):
        raise ContractValidationError("%s must be a safe identifier" % label)
    return text


# ---------------------------------------------------------------------------
# E3.3 -- agent names, defaults and resolution
# ---------------------------------------------------------------------------

_AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9\-]{0,%d}$" % (MAX_AGENT_NAME_LEN - 1))
RESERVED_AGENT_NAMES = frozenset({ROOT_AGENT_NAME})


def is_reserved_agent_name(name: Any) -> bool:
    """True for names owned by the system (the root ``lead`` agent)."""
    return str(name or "") in RESERVED_AGENT_NAMES


def validate_agent_name(name: Any) -> tuple[str, ...]:
    """Return all reasons ``name`` is not a valid non-root agent name."""
    text = str(name or "")
    errors: list[str] = []
    if not text:
        errors.append("agent name must not be empty")
    if len(text) > MAX_AGENT_NAME_LEN:
        errors.append("agent name must be at most 32 characters")
    if text and not _AGENT_NAME_RE.match(text):
        errors.append(
            "agent name must be 1-32 lowercase letters/digits/hyphens starting with a letter"
        )
    if text in RESERVED_AGENT_NAMES:
        errors.append("agent name %r is reserved for the root" % text)
    return tuple(errors)


def make_agent_name(name: Any) -> str:
    """Validate and return an agent name; fail closed on any violation."""
    errors = validate_agent_name(name)
    if errors:
        raise ContractValidationError(errors)
    return str(name)


def validate_agent_path(path: Any, *, require_root: bool = True) -> tuple[str, ...]:
    """Validate a full slash-path name such as ``lead/researcher/writer``."""
    text = str(path or "")
    errors: list[str] = []
    if not text:
        return ("agent path must not be empty",)
    if "\\" in text or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        return ("agent path contains an illegal character",)
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        errors.append("agent path has an empty or traversal segment")
    if require_root and parts and parts[0] != ROOT_AGENT_NAME:
        errors.append("full agent paths must start with %r" % ROOT_AGENT_NAME)
    for index, part in enumerate(parts):
        for error in validate_agent_name(part):
            # The root is allowed to be the reserved name; children are not.
            if index == 0 and require_root and part == ROOT_AGENT_NAME and \
                    error.startswith("agent name %r is reserved" % part):
                continue
            errors.append("segment %d: %s" % (index, error))
    return tuple(dict.fromkeys(errors))


def make_agent_path(path: Any, *, require_root: bool = True) -> str:
    errors = validate_agent_path(path, require_root=require_root)
    if errors:
        raise ContractValidationError(errors)
    return str(path)


def parent_agent_path(path: Any) -> str | None:
    """Return the parent full path, or ``None`` for the root."""
    text = str(path or "")
    parts = text.split("/")
    if len(parts) <= 1:
        return None
    return "/".join(parts[:-1])


def default_agent_name(existing: Iterable[Any] = ()) -> str:
    """Return the smallest unused ``agent-N`` name (N >= 1)."""
    used = {str(value) for value in existing}
    index = 1
    while "%s%d" % (DEFAULT_AGENT_PREFIX, index) in used:
        index += 1
    name = "%s%d" % (DEFAULT_AGENT_PREFIX, index)
    if validate_agent_name(name):  # pragma: no cover - defensive
        raise ContractValidationError("could not generate a valid default agent name")
    return name


@dataclass(frozen=True)
class AgentRegistry:
    """Name -> authoritative session id map. Names grant no permission."""

    entries: tuple[tuple[str, str], ...]

    def by_name(self, full_name: Any) -> str | None:
        key = str(full_name or "")
        return next((sid for name, sid in self.entries if name == key), None)

    def has_session(self, session_id: Any) -> bool:
        target = str(session_id or "")
        return any(sid == target for _, sid in self.entries)

    def to_dict(self) -> dict:
        return {"entries": [{"full_name": n, "session_id": s}
                            for n, s in self.entries]}


def make_registry(entries: Any) -> AgentRegistry:
    """Build and validate a registry; a root ``lead`` entry is mandatory."""
    if isinstance(entries, Mapping):
        items = tuple((str(k), str(v)) for k, v in entries.items())
    else:
        items = tuple((str(pair[0]), str(pair[1])) for pair in (entries or ()))
    errors: list[str] = []
    if not items:
        errors.append("agent registry must not be empty")
    names: set[str] = set()
    for name, sid in items:
        for error in validate_agent_path(name):
            errors.append("path %r: %s" % (name, error))
        if name in names:
            errors.append("duplicate full agent path: %s" % name)
        names.add(name)
        if not sid or _ENCODED_TRAVERSAL_RE.search(sid) or any(
                ord(ch) < 0x20 or ord(ch) == 0x7F for ch in sid):
            errors.append("invalid session id for %s" % name)
    if ROOT_AGENT_NAME not in names:
        errors.append("agent registry must define the root %r" % ROOT_AGENT_NAME)
    if errors:
        raise ContractValidationError(errors)
    return AgentRegistry(entries=tuple(sorted(items)))


def resolve_name(registry: AgentRegistry, full_name: Any) -> str:
    """Resolve a full name to its session id, or raise ``AGENT_NAME_NOT_FOUND``.

    Resolution returns identity only.  It never consults, returns or grants a
    permission -- authorization is a separate concern and lives elsewhere.
    """
    try:
        validated = make_agent_path(full_name)
    except ContractValidationError as exc:
        raise AgentNameNotFoundError(full_name) from exc
    session_id = registry.by_name(validated) if isinstance(registry, AgentRegistry) else None
    if session_id is None:
        raise AgentNameNotFoundError(validated)
    return session_id


# ---------------------------------------------------------------------------
# E3.8 -- result object, stop reasons, diagnostics and child failures
# ---------------------------------------------------------------------------

class StopReason(str, Enum):
    """Closed stop-reason vocabulary for a result."""

    COMPLETED = "completed"
    ABORTED = "aborted"
    ERROR = "error"
    MAX_TOKENS = "max-tokens"
    REFUSAL = "refusal"

    def __str__(self) -> str:
        return self.value


_STOP_REASON_ALIASES = {
    "max_tokens": StopReason.MAX_TOKENS,
    "max tokens": StopReason.MAX_TOKENS,
    "maxtokens": StopReason.MAX_TOKENS,
    "cancel": StopReason.ABORTED,
    "cancelled": StopReason.ABORTED,
    "cancelled_by_user": StopReason.ABORTED,
    "fail": StopReason.ERROR,
    "failed": StopReason.ERROR,
    "done": StopReason.COMPLETED,
    "success": StopReason.COMPLETED,
}


def parse_stop_reason(value: Any) -> StopReason:
    """Parse a stop reason; unknown values fail closed as an error."""
    if isinstance(value, StopReason):
        return value
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered in _STOP_REASON_ALIASES:
        return _STOP_REASON_ALIASES[lowered]
    try:
        return StopReason(lowered)
    except ValueError as exc:
        raise ContractValidationError("unknown stop reason: %s" % text) from exc


def _message_text(message: Any) -> str:
    """Extract the textual content of a message (str or list of text blocks)."""
    if not isinstance(message, Mapping):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, Mapping):
                for key in ("text", "content", "value"):
                    val = block.get(key)
                    if isinstance(val, str):
                        parts.append(val)
                        break
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def last_assistant_message(messages: Iterable[Any] = ()) -> str:
    """Return the last non-empty assistant message, or ``''`` if there is none."""
    result = ""
    try:
        for message in messages or ():
            if not isinstance(message, Mapping):
                continue
            role = str(message.get("role", "") or "").strip().lower()
            if role != "assistant":
                continue
            text = _message_text(message)
            if text.strip():
                result = text
    except TypeError:
        return ""
    return result


def sanitize_diagnostics(value: Any, *, limit: int = DIAGNOSTIC_BYTE_LIMIT) -> str:
    """Return sanitized diagnostic text bounded by ``limit`` UTF-8 bytes.

    Removes PEM private keys, literal credentials, bearer tokens, secret-like
    assignments, env values, tool inputs/raw payload markers, fenced file
    contents and over-long lines (file dumps), then truncates on a codepoint
    boundary.  The operation is idempotent on its own output.
    """
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        ch if (ch in "\n\t" or (ord(ch) >= 0x20 and ord(ch) != 0x7F)) else " "
        for ch in text
    )
    text = _PEM_RE.sub("[PRIVATE_KEY_REDACTED]", text)
    text = _FILE_BLOCK_RE.sub("[FILE_CONTENT_REDACTED]", text)
    text = _CREDENTIAL_PREFIX_RE.sub("[REDACTED]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _SECRET_ASSIGNMENT_RE.sub(lambda m: "%s=[REDACTED]" % m.group("key"), text)
    text = _ENV_ASSIGNMENT_RE.sub(lambda m: "[env:%s=REDACTED]" % m.group("name"), text)
    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        line = _TOOL_INPUT_RE.sub(lambda m: "%s=[TOOL_INPUT_REDACTED]" % m.group("label"), line)
        if len(line) > 256:
            line = line[:200] + " ...[TRUNCATED]"
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    return _truncate_utf8(text, limit)


def assert_clean_diagnostics(value: Any) -> str:
    """Return text only if already sanitized; otherwise fail closed."""
    text = "" if value is None else str(value)
    if len(text.encode("utf-8")) > DIAGNOSTIC_BYTE_LIMIT:
        raise ContractValidationError("diagnostics exceed the 4096 byte limit")
    if _CREDENTIAL_PREFIX_RE.search(text) or _PEM_RE.search(text):
        raise ContractValidationError("diagnostics still contain credential material")
    if sanitize_diagnostics(text) != text:
        raise ContractValidationError("diagnostics are not sanitized")
    return text


_JSON_TYPES = frozenset({
    "object", "array", "string", "number", "integer", "boolean", "null"
})
_SCHEMA_KEYS = frozenset({
    "type", "required", "properties", "items", "enum", "const",
    "additionalProperties", "minLength", "maxLength", "pattern",
    "minimum", "maximum", "minItems", "maxItems", "description", "title",
})


def is_json_safe(value: Any) -> bool:
    """True when a value can round-trip through JSON."""
    try:
        json.dumps(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def _json_equal(left: Any, right: Any) -> bool:
    try:
        return json.dumps(left, sort_keys=True, separators=(",", ":")) == \
            json.dumps(right, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError):
        return False


def normalize_schema(schema: Any) -> dict:
    """Validate a minimal JSON-Schema subset and return a canonical copy."""
    if not isinstance(schema, Mapping):
        raise ContractValidationError("schema must be an object")
    unknown = set(str(k) for k in schema) - _SCHEMA_KEYS
    if unknown:
        raise ContractValidationError(
            "unsupported schema keyword(s): %s" % ", ".join(sorted(unknown)))
    out: dict = {}
    if "type" in schema:
        types = schema["type"]
        types = (types,) if isinstance(types, str) else tuple(types or ())
        if not types or any(str(t) not in _JSON_TYPES for t in types):
            raise ContractValidationError("schema type must be a known JSON type")
        out["type"] = tuple(str(t) for t in types)
    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, (list, tuple)) or any(
                not isinstance(k, str) or not k for k in required):
            raise ContractValidationError("schema required must be a list of names")
        out["required"] = tuple(required)
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, Mapping):
            raise ContractValidationError("schema properties must be an object")
        out["properties"] = {
            str(k): normalize_schema(v) for k, v in properties.items()
        }
    if "items" in schema:
        out["items"] = normalize_schema(schema["items"])
    for key in ("enum",):
        if key in schema:
            values = schema[key]
            if not isinstance(values, (list, tuple)) or not values or not is_json_safe(values):
                raise ContractValidationError("schema enum must be a non-empty JSON list")
            out[key] = tuple(values)
    if "const" in schema:
        if not is_json_safe(schema["const"]):
            raise ContractValidationError("schema const must be JSON-safe")
        out["const"] = schema["const"]
    if "additionalProperties" in schema:
        value = schema["additionalProperties"]
        if not isinstance(value, bool):
            raise ContractValidationError("additionalProperties must be a boolean")
        out["additionalProperties"] = value
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        if key in schema:
            value = schema[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ContractValidationError("%s must be a non-negative integer" % key)
            out[key] = value
    for key in ("minimum", "maximum"):
        if key in schema:
            value = schema[key]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ContractValidationError("%s must be a number" % key)
            out[key] = value
    if "pattern" in schema:
        try:
            re.compile(str(schema["pattern"]))
        except re.error as exc:
            raise ContractValidationError("schema pattern is invalid") from exc
        out["pattern"] = str(schema["pattern"])
    for key in ("description", "title"):
        if key in schema:
            out[key] = _redact(str(schema[key]))
    return out


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, (list, tuple))
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _validate_value(value: Any, schema: dict, path: str) -> tuple[str, ...]:
    errors: list[str] = []
    if "type" in schema and not any(_matches_type(value, t) for t in schema["type"]):
        return ("%s: wrong type (expected %s)" % (path, "/".join(schema["type"])),)
    if "enum" in schema and not any(_json_equal(value, option) for option in schema["enum"]):
        errors.append("%s: value is not in enum" % path)
    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.append("%s: value does not match const" % path)
    if isinstance(value, Mapping):
        for key in schema.get("required", ()):
            if key not in value:
                errors.append("%s: missing required property %s" % (path, key))
        properties = schema.get("properties", {})
        allow_extra = schema.get("additionalProperties", False)
        for key, sub_value in value.items():
            if key in properties:
                for error in _validate_value(sub_value, properties[key], "%s.%s" % (path, key)):
                    errors.append(error)
            elif not allow_extra:
                errors.append("%s: unexpected property %s" % (path, key))
    if isinstance(value, (list, tuple)):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append("%s: fewer than minItems entries" % path)
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append("%s: more than maxItems entries" % path)
        if "items" in schema:
            for index, item in enumerate(value):
                for error in _validate_value(item, schema["items"], "%s[%d]" % (path, index)):
                    errors.append(error)
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append("%s: shorter than minLength" % path)
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append("%s: longer than maxLength" % path)
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append("%s: does not match pattern" % path)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s: below minimum" % path)
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s: above maximum" % path)
    return tuple(errors)


def validate_structured(value: Any, schema: Any) -> tuple[str, ...]:
    """Validate a structured value against a schema; empty errors means valid."""
    canonical = normalize_schema(schema)
    if not is_json_safe(value):
        return ("structured value is not JSON-safe",)
    return _validate_value(value, canonical, "$")


@dataclass(frozen=True)
class Result:
    """Immutable final result of an agent or child run."""

    final_output: str
    stop_reason: StopReason
    structured: Any
    schema: Any
    diagnostics: str

    @property
    def diagnostics_bytes(self) -> int:
        return len(self.diagnostics.encode("utf-8"))

    @property
    def has_structured_output(self) -> bool:
        return self.structured is not None

    def to_dict(self) -> dict:
        return {
            "final_output": self.final_output,
            "stop_reason": self.stop_reason.value,
            "structured": self.structured,
            "schema": self.schema,
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Result":
        if not isinstance(data, Mapping):
            raise ContractValidationError("result payload must be an object")
        return build_result(
            messages=(),
            final_output=data.get("final_output", ""),
            structured=data.get("structured"),
            schema=data.get("schema"),
            diagnostics=data.get("diagnostics", ""),
            stop_reason=parse_stop_reason(data.get("stop_reason", "completed")),
        )


def build_result(
    messages: Iterable[Any] = (),
    *,
    final_output: Any = None,
    structured: Any = None,
    schema: Any = None,
    diagnostics: Any = "",
    stop_reason: Any = StopReason.COMPLETED,
) -> Result:
    """Build a validated result; final output is the last non-empty assistant message."""
    reason = parse_stop_reason(stop_reason)
    output = str(final_output) if final_output is not None else last_assistant_message(messages)
    clean_diagnostics = sanitize_diagnostics(diagnostics)
    canonical_schema: Any = None
    if not is_json_safe(output):  # pragma: no cover - str() always safe
        raise ContractValidationError("final output must be text")
    if schema is not None:
        canonical_schema = normalize_schema(schema)
        if structured is None:
            raise ContractValidationError("a requested schema requires a structured value")
        errors = validate_structured(structured, canonical_schema)
        if errors:
            raise ContractValidationError(errors)
        structured = json.loads(json.dumps(structured))
    elif structured is not None:
        if not is_json_safe(structured):
            raise ContractValidationError("structured output must be JSON-safe")
        if looks_like_secret(structured):
            raise ContractValidationError("structured output must not contain credentials")
        structured = json.loads(json.dumps(structured))
    return Result(
        final_output=output,
        stop_reason=reason,
        structured=structured,
        schema=canonical_schema,
        diagnostics=clean_diagnostics,
    )


def child_failure_to_result(error: Any = None, *, messages: Iterable[Any] = ()) -> Result:
    """Resolve a child failure into an ERROR result; this never raises."""
    try:
        detail = ""
        if isinstance(error, Mapping):
            detail = str(error.get("error", error.get("message", "child failed")))
        elif error is not None:
            detail = str(error)
        output = last_assistant_message(messages)
        diagnostics = sanitize_diagnostics("child failure: %s" % detail)
        return Result(
            final_output=output,
            stop_reason=StopReason.ERROR,
            structured=None,
            schema=None,
            diagnostics=diagnostics,
        )
    except Exception:  # pragma: no cover - absolute last-resort guard
        return Result(
            final_output="",
            stop_reason=StopReason.ERROR,
            structured=None,
            schema=None,
            diagnostics="child failure",
        )


def resolve_child_outcome(outcome: Any) -> Result:
    """Turn any child outcome mapping into a Result, never an exception."""
    if not isinstance(outcome, Mapping):
        return child_failure_to_result(outcome)
    failed = (
        outcome.get("ok") is False
        or parse_stop_reason_safe(outcome.get("stop_reason")) == StopReason.ERROR
        or "error" in outcome
    )
    if failed:
        return child_failure_to_result(
            outcome.get("error", "child failed"),
            messages=outcome.get("messages", ()),
        )
    try:
        return build_result(
            messages=outcome.get("messages", ()),
            structured=outcome.get("structured"),
            schema=outcome.get("schema"),
            diagnostics=outcome.get("diagnostics", ""),
            stop_reason=outcome.get("stop_reason", "completed"),
        )
    except Exception:
        return child_failure_to_result("invalid child outcome")


def parse_stop_reason_safe(value: Any) -> StopReason:
    """Permissive parser used internally: unknown reasons map to ERROR."""
    try:
        return parse_stop_reason(value)
    except ContractValidationError:
        return StopReason.ERROR


# ---------------------------------------------------------------------------
# E4.5 -- snapshot scenarios
# ---------------------------------------------------------------------------

class SnapshotMode(str, Enum):
    """Snapshot lifecycle modes; CI replay is strictly read-only."""

    RECORD = "record"
    REFRESH = "refresh"
    REVIEW = "review"
    CI_REPLAY = "ci_replay"

    def __str__(self) -> str:
        return self.value


class RecordingPolicy(str, Enum):
    """What a scenario is allowed to record and replay."""

    KEYLESS = "keyless"
    RECORD_REQUIRES_KEY = "record-requires-key"
    REPLAY_ONLY = "replay-only"

    def __str__(self) -> str:
        return self.value


ALLOWED_HEADER_CLASSES = frozenset({"session.v1", "session.v2"})
ALLOWED_PROFILES = frozenset({"default", "claude-code", "openai-compatible", "local"})
MODE_REQUIREMENTS: dict[SnapshotMode, frozenset[str]] = {
    SnapshotMode.RECORD: frozenset({"api_key"}),
    SnapshotMode.REFRESH: frozenset({"replay_input"}),
    SnapshotMode.REVIEW: frozenset({"diff_review"}),
    SnapshotMode.CI_REPLAY: frozenset({"read_only"}),
}
READ_ONLY_MODES = frozenset({SnapshotMode.REVIEW, SnapshotMode.CI_REPLAY})

_SESSION_FILE_RE = re.compile(
    r"^(?P<role>parent|child)[-_]v(?P<version>[0-9]{1,6})\.(?P<ext>json|jsonl|yaml|yml)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SessionFileRef:
    """A parent/child session filename carrying its version."""

    name: str
    role: str
    version: int
    extension: str

    def to_dict(self) -> dict:
        return {"name": self.name, "role": self.role,
                "version": self.version, "extension": self.extension}


def parse_session_file(filename: Any) -> SessionFileRef:
    """Parse ``parent-v3.json`` style filenames; fail closed on bad input."""
    text = str(filename or "")
    match = _SESSION_FILE_RE.match(text)
    if match is None:
        raise ContractValidationError(
            "session file must be named parent-vN or child-vN with a recorded extension")
    return SessionFileRef(
        name=text,
        role=match.group("role").lower(),
        version=int(match.group("version")),
        extension=match.group("ext").lower(),
    )


@dataclass(frozen=True)
class SessionHeader:
    """Header carried inside a session file (version must match its filename)."""

    version: int
    session_id: str
    role: str
    header_class: str
    parent_id: str | None = None

    def to_dict(self) -> dict:
        return {"version": self.version, "session_id": self.session_id,
                "role": self.role, "header_class": self.header_class,
                "parent_id": self.parent_id}


@dataclass(frozen=True)
class SnapshotConfig:
    """The parsed ``snapshot.yml`` declaration."""

    profile: str
    header_class: str
    recording_policy: RecordingPolicy
    workspace_facts: tuple[tuple[str, str], ...]
    mutating: bool = False

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "header_class": self.header_class,
            "recording_policy": self.recording_policy.value,
            "workspace_facts": dict(self.workspace_facts),
            "mutating": self.mutating,
        }


def make_snapshot_config(
    profile: Any,
    header_class: Any,
    *,
    recording_policy: Any = RecordingPolicy.KEYLESS,
    workspace_facts: Any = None,
    mutating: Any = False,
) -> SnapshotConfig:
    """Build and validate a snapshot.yml declaration."""
    if isinstance(recording_policy, RecordingPolicy):
        policy = recording_policy
    else:
        try:
            policy = RecordingPolicy(str(recording_policy or "").strip().lower())
        except ValueError as exc:
            raise ContractValidationError("unknown recording policy") from exc
    facts = workspace_facts or {}
    items = tuple(sorted((str(k), str(v)) for k, v in facts.items())) \
        if isinstance(facts, Mapping) else tuple(sorted((str(p[0]), str(p[1])) for p in facts))
    config = SnapshotConfig(
        profile=str(profile or ""),
        header_class=str(header_class or ""),
        recording_policy=policy,
        workspace_facts=items,
        mutating=bool(mutating),
    )
    errors = validate_snapshot_config(config)
    if errors:
        raise ContractValidationError(errors)
    return config


def validate_snapshot_config(config: SnapshotConfig) -> tuple[str, ...]:
    errors: list[str] = []
    if config.profile not in ALLOWED_PROFILES:
        errors.append("unknown snapshot profile: %s" % config.profile)
    if config.header_class not in ALLOWED_HEADER_CLASSES:
        errors.append("unknown header class: %s" % config.header_class)
    if not isinstance(config.recording_policy, RecordingPolicy):
        errors.append("recording policy must be a known enum value")
    for key, value in config.workspace_facts:
        if not _SAFE_ID_RE.match(key):
            errors.append("unsafe workspace fact key")
        if looks_like_secret(value) or _CREDENTIAL_PREFIX_RE.search(value):
            errors.append("workspace facts must be keyless")
    return tuple(errors)


class TokenKind(str, Enum):
    """Typed identity tokens shared by parent and child session files."""

    PARENT_SESSION_ID = "parent_session_id"
    CHILD_SESSION_ID = "child_session_id"
    CHILD_PARENT_LINK = "child_parent_link"
    PARENT_FILE_VERSION = "parent_file_version"
    PARENT_HEADER_VERSION = "parent_header_version"
    CHILD_FILE_VERSION = "child_file_version"
    CHILD_HEADER_VERSION = "child_header_version"
    HEADER_CLASS = "header_class"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TypedToken:
    """A typed token; its kind fixes which relation it participates in."""

    kind: TokenKind
    value: str
    owner: str

    def to_dict(self) -> dict:
        return {"kind": self.kind.value, "value": self.value, "owner": self.owner}


@dataclass(frozen=True)
class SnapshotPair:
    """A validated parent/child scenario with its typed identity tokens."""

    parent_ref: SessionFileRef
    parent_header: SessionHeader
    child_ref: SessionFileRef
    child_header: SessionHeader
    config: SnapshotConfig
    tokens: tuple[TypedToken, ...]

    def to_dict(self) -> dict:
        return {
            "parent": self.parent_ref.to_dict(),
            "parent_header": self.parent_header.to_dict(),
            "child": self.child_ref.to_dict(),
            "child_header": self.child_header.to_dict(),
            "config": self.config.to_dict(),
            "tokens": [t.to_dict() for t in self.tokens],
        }


def validate_snapshot_pair(
    parent_ref: SessionFileRef,
    parent_header: SessionHeader,
    child_ref: SessionFileRef,
    child_header: SessionHeader,
    config: SnapshotConfig,
) -> tuple[str, ...]:
    """Return all reasons a parent/child scenario is inconsistent."""
    errors: list[str] = list(validate_snapshot_config(config))
    if parent_ref.role != "parent":
        errors.append("parent file must use a parent- name")
    if child_ref.role != "child":
        errors.append("child file must use a child- name")
    for label, ref, header in (
        ("parent", parent_ref, parent_header),
        ("child", child_ref, child_header),
    ):
        if ref.version != header.version:
            errors.append("%s version mismatch: filename v%d, header v%d" % (
                label, ref.version, header.version))
        if header.role != ref.role:
            errors.append("%s header role does not match its filename" % label)
        if header.header_class != config.header_class:
            errors.append("%s header class does not match snapshot.yml" % label)
        if not header.session_id or _ENCODED_TRAVERSAL_RE.search(header.session_id):
            errors.append("%s session id is invalid" % label)
    if parent_header.session_id == child_header.session_id:
        errors.append("parent and child must have distinct session ids")
    if child_header.parent_id != parent_header.session_id:
        errors.append("child parent_id must reference the parent session id")
    return tuple(dict.fromkeys(errors))


def make_snapshot_pair(
    parent: Any,
    parent_header: Any,
    child: Any,
    child_header: Any,
    config: SnapshotConfig,
) -> SnapshotPair:
    """Validate and bind a parent/child scenario, returning typed tokens."""
    parent_ref = parent if isinstance(parent, SessionFileRef) else parse_session_file(parent)
    child_ref = child if isinstance(child, SessionFileRef) else parse_session_file(child)
    p_header = (parent_header if isinstance(parent_header, SessionHeader)
                else SessionHeader(**dict(parent_header)))
    c_header = (child_header if isinstance(child_header, SessionHeader)
                else SessionHeader(**dict(child_header)))
    errors = validate_snapshot_pair(parent_ref, p_header, child_ref, c_header, config)
    if errors:
        raise ContractValidationError(errors)
    tokens = (
        TypedToken(TokenKind.PARENT_SESSION_ID, p_header.session_id, "parent"),
        TypedToken(TokenKind.CHILD_SESSION_ID, c_header.session_id, "child"),
        TypedToken(TokenKind.CHILD_PARENT_LINK, str(c_header.parent_id), "child"),
        TypedToken(TokenKind.PARENT_FILE_VERSION, str(parent_ref.version), "parent"),
        TypedToken(TokenKind.PARENT_HEADER_VERSION, str(p_header.version), "parent"),
        TypedToken(TokenKind.CHILD_FILE_VERSION, str(child_ref.version), "child"),
        TypedToken(TokenKind.CHILD_HEADER_VERSION, str(c_header.version), "child"),
        TypedToken(TokenKind.HEADER_CLASS, config.header_class, "shared"),
    )
    return SnapshotPair(parent_ref, p_header, child_ref, c_header, config, tokens)


def verify_identity_tokens(tokens: Iterable[TypedToken]) -> tuple[str, ...]:
    """Check that typed tokens still encode a consistent parent/child relation."""
    values: dict[TokenKind, TypedToken] = {}
    errors: list[str] = []
    expected_owner = {
        TokenKind.PARENT_SESSION_ID: "parent",
        TokenKind.CHILD_SESSION_ID: "child",
        TokenKind.CHILD_PARENT_LINK: "child",
        TokenKind.PARENT_FILE_VERSION: "parent",
        TokenKind.PARENT_HEADER_VERSION: "parent",
        TokenKind.CHILD_FILE_VERSION: "child",
        TokenKind.CHILD_HEADER_VERSION: "child",
        TokenKind.HEADER_CLASS: "shared",
    }
    for token in tokens or ():
        if not isinstance(token, TypedToken) or token.kind not in expected_owner:
            errors.append("unknown or malformed typed token")
            continue
        if token.kind in values:
            errors.append("duplicate typed token: %s" % token.kind.value)
        if token.owner != expected_owner[token.kind]:
            errors.append("token %s has the wrong owner" % token.kind.value)
        values[token.kind] = token
    if len(values) != len(expected_owner):
        errors.append("missing typed identity tokens")
        return tuple(errors)
    if values[TokenKind.CHILD_PARENT_LINK].value != values[TokenKind.PARENT_SESSION_ID].value:
        errors.append("child parent link does not match the parent session id")
    if values[TokenKind.PARENT_SESSION_ID].value == values[TokenKind.CHILD_SESSION_ID].value:
        errors.append("parent and child tokens share a session id")
    for prefix in ("PARENT", "CHILD"):
        file_v = values[TokenKind["%s_FILE_VERSION" % prefix]].value
        header_v = values[TokenKind["%s_HEADER_VERSION" % prefix]].value
        if file_v != header_v:
            errors.append("%s file/header version tokens disagree" % prefix.lower())
    return tuple(dict.fromkeys(errors))


def _is_snapshot_path(path: Any) -> bool:
    text = str(path or "")
    if not text or _ENCODED_TRAVERSAL_RE.search(text):
        return False
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text) or text.startswith("\\\\"):
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        return False
    normalized = text.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return False
    return True


@dataclass(frozen=True)
class WorkspaceManifest:
    """A pure digest manifest of a workspace tree (no filesystem access)."""

    entries: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict:
        return {"entries": [{"path": p, "sha256": d} for p, d in self.entries]}


def make_workspace_manifest(files: Any) -> WorkspaceManifest:
    """Hash caller-provided ``path -> content`` pairs into a sorted manifest."""
    if not isinstance(files, Mapping):
        raise ContractValidationError("workspace files must be a path-to-content mapping")
    errors: list[str] = []
    entries: list[tuple[str, str]] = []
    for path, content in files.items():
        key = str(path)
        if not _is_snapshot_path(key):
            errors.append("unsafe workspace path: %s" % key)
            continue
        if isinstance(content, bytes):
            raw = content
        elif isinstance(content, str):
            raw = content.encode("utf-8")
        else:
            errors.append("workspace content must be text or bytes")
            continue
        entries.append((key, hashlib.sha256(raw).hexdigest()))
    if errors:
        raise ContractValidationError(errors)
    return WorkspaceManifest(entries=tuple(sorted(entries)))


@dataclass(frozen=True)
class WorkspaceDiff:
    """A pure diff between an expected manifest and an observed one."""

    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def paths(self) -> frozenset[str]:
        return frozenset((*self.added, *self.removed, *self.changed))

    def to_dict(self) -> dict:
        return {"added": list(self.added), "removed": list(self.removed),
                "changed": list(self.changed)}


def compare_workspace(expected: WorkspaceManifest, actual: WorkspaceManifest) -> WorkspaceDiff:
    """Compare two manifests; returns a deterministic diff."""
    before = dict(expected.entries)
    after = dict(actual.entries)
    added = tuple(sorted(set(after) - set(before)))
    removed = tuple(sorted(set(before) - set(after)))
    changed = tuple(sorted(k for k in set(before) & set(after) if before[k] != after[k]))
    return WorkspaceDiff(added=added, removed=removed, changed=changed)


def assert_expected_immutable(before: WorkspaceManifest, after: WorkspaceManifest) -> None:
    """Fail closed if a record/refresh rewrote the expected workspace tree."""
    if before.entries != after.entries:
        raise ContractValidationError("workspace.expected/ must never be rewritten")


def _resolve_mode(mode: Any) -> SnapshotMode:
    if isinstance(mode, SnapshotMode):
        return mode
    try:
        return SnapshotMode(str(mode or ""))
    except ValueError as exc:
        raise ContractValidationError("unknown snapshot mode") from exc


def mode_requirements(mode: Any) -> frozenset[str]:
    """Return the named preconditions that must hold for a snapshot mode."""
    return MODE_REQUIREMENTS[_resolve_mode(mode)]


def can_run_mode(
    mode: Any,
    *,
    key_present: bool = False,
    replay_input_valid: bool = False,
    diff_reviewed: bool = False,
) -> bool:
    """Check a mode's preconditions; all requirements must be satisfied."""
    requirements = mode_requirements(mode)
    satisfied = {
        "api_key": bool(key_present),
        "replay_input": bool(replay_input_valid),
        "diff_review": bool(diff_reviewed),
        "read_only": True,
    }
    return all(satisfied[requirement] for requirement in requirements)


def is_read_only_mode(mode: Any) -> bool:
    """True for modes that must never write (review and CI replay)."""
    return _resolve_mode(mode) in READ_ONLY_MODES


def snapshot_write_allowed(mode: Any, path: Any) -> bool:
    """Decide whether a mode may write a path; expected tree is never writable."""
    if not _is_snapshot_path(path):
        return False
    if _resolve_mode(mode) in READ_ONLY_MODES:
        return False
    parts = str(path).replace("\\", "/").split("/")
    if parts[0] == EXPECTED_TREE_ROOT:
        return False
    return True


def assert_snapshot_write_allowed(mode: Any, path: Any) -> None:
    if not snapshot_write_allowed(mode, path):
        raise ContractValidationError("snapshot mode may not write %s" % path)


def review_all_diffs(diffs: Iterable[WorkspaceDiff], reviewed_paths: Iterable[Any]) -> None:
    """Fail closed unless every changed path has been explicitly reviewed."""
    unreviewed: set[str] = set()
    for diff in diffs or ():
        unreviewed |= set(diff.paths())
    unreviewed -= {str(p) for p in (reviewed_paths or ())}
    if unreviewed:
        raise ContractValidationError(
            "unreviewed snapshot diffs: %s" % ", ".join(sorted(unreviewed)))


# ---------------------------------------------------------------------------
# E4.8 -- test-process isolation rules
# ---------------------------------------------------------------------------

class ResourceKind(str, Enum):
    """Resources forked test workers can accidentally share."""

    PORT = "port"
    PATH = "path"
    NAMESPACE = "namespace"
    CHILD_PROCESS = "child_process"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ResourceLease:
    """A resource acquired by an owned test with a promised teardown."""

    kind: ResourceKind
    resource_id: str
    owner_test: str
    worker_id: str
    teardown_owned: bool = True

    def to_dict(self) -> dict:
        return {"kind": self.kind.value, "resource_id": self.resource_id,
                "owner_test": self.owner_test, "worker_id": self.worker_id,
                "teardown_owned": self.teardown_owned}


def validate_lease(lease: ResourceLease) -> tuple[str, ...]:
    errors: list[str] = []
    if not isinstance(lease.kind, ResourceKind):
        errors.append("unknown resource kind")
    if not str(lease.resource_id or "").strip():
        errors.append("resource id must not be empty")
    if not str(lease.owner_test or "").strip():
        errors.append("a lease must name its owning test")
    if not str(lease.worker_id or "").strip():
        errors.append("a lease must name its worker")
    if not lease.teardown_owned:
        errors.append("each test must own every resource through teardown")
    return tuple(errors)


def make_lease(
    kind: Any,
    resource_id: Any,
    *,
    owner_test: Any,
    worker_id: Any,
    teardown_owned: Any = True,
) -> ResourceLease:
    """Build a validated lease; fail closed on missing owner or teardown."""
    try:
        resolved = kind if isinstance(kind, ResourceKind) else ResourceKind(str(kind or ""))
    except ValueError as exc:
        raise ContractValidationError("unknown resource kind") from exc
    lease = ResourceLease(
        kind=resolved,
        resource_id=str(resource_id or ""),
        owner_test=str(owner_test or ""),
        worker_id=str(worker_id or ""),
        teardown_owned=bool(teardown_owned),
    )
    errors = validate_lease(lease)
    if errors:
        raise ContractValidationError(errors)
    return lease


def detect_isolation_violations(leases: Iterable[ResourceLease]) -> tuple[str, ...]:
    """Detect shared resources and unowned teardowns across forked workers."""
    errors: list[str] = []
    seen: dict[tuple[str, str], ResourceLease] = {}
    for lease in leases or ():
        for error in validate_lease(lease):
            errors.append(error)
        key = (lease.kind.value if isinstance(lease.kind, ResourceKind) else str(lease.kind),
               str(lease.resource_id))
        if key in seen:
            first = seen[key]
            errors.append(
                "shared %s %r between workers %s and %s" % (
                    key[0], key[1], first.worker_id, lease.worker_id))
        else:
            seen[key] = lease
    return tuple(dict.fromkeys(errors))


def assert_isolated(leases: Iterable[ResourceLease]) -> None:
    violations = detect_isolation_violations(leases)
    if violations:
        raise ContractValidationError(violations)


@dataclass(frozen=True)
class ForkExit:
    """The complete, reportable exit description of a forked worker."""

    pid: int
    file: str
    code: int | None
    signal: str | None

    def to_dict(self) -> dict:
        return {"pid": self.pid, "file": self.file,
                "code": self.code, "signal": self.signal}


def fork_exit_diagnostic(exit_info: Any) -> str:
    """Format PID, file, code and signal; fail closed if any is unavailable."""
    if isinstance(exit_info, ForkExit):
        exit_value = exit_info
    elif isinstance(exit_info, Mapping):
        exit_value = ForkExit(
            pid=exit_info.get("pid", 0),
            file=str(exit_info.get("file", "") or ""),
            code=exit_info.get("code"),
            signal=exit_info.get("signal"),
        )
    else:
        raise ContractValidationError("fork exit info must be a mapping or ForkExit")
    errors: list[str] = []
    try:
        pid = int(exit_value.pid)
    except (TypeError, ValueError):
        pid = 0
    if pid <= 0:
        errors.append("fork exit diagnostic is missing a valid PID")
    if not str(exit_value.file or "").strip():
        errors.append("fork exit diagnostic is missing the file")
    if exit_value.code is None and exit_value.signal is None:
        errors.append("fork exit diagnostic needs a code or a signal")
    if errors:
        raise ContractValidationError(errors)
    code = "n/a" if exit_value.code is None else str(exit_value.code)
    signal = "n/a" if exit_value.signal is None else str(exit_value.signal)
    return "fork exit: pid=%d file=%s code=%s signal=%s" % (
        pid, exit_value.file, code, signal)


class FlakeClass(str, Enum):
    """How a suspicious test outcome is classified."""

    DETERMINISTIC_PASS = "deterministic_pass"
    DETERMINISTIC_FAIL = "deterministic_fail"
    PROBABILISTIC = "probabilistic"
    ISOLATION_DEFECT = "isolation_defect"
    ORDER_DEPENDENT = "order_dependent"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


def solo_only_is_defect(solo_passed: bool, suite_passed: bool) -> bool:
    """A spec that passes only alone is a test defect, by policy."""
    return bool(solo_passed) and not bool(suite_passed)


def classify_flake(
    test_id: Any,
    *,
    solo_passed: bool,
    suite_passed: bool,
    repeated_runs: Iterable[bool] = (),
) -> FlakeClass:
    """Classify a probabilistic/order-dependent failure, fail-closed."""
    if not str(test_id or "").strip():
        raise ContractValidationError("flake classification needs a test id")
    if solo_only_is_defect(solo_passed, suite_passed):
        return FlakeClass.ISOLATION_DEFECT
    runs = tuple(bool(value) for value in (repeated_runs or ()))
    if not runs:
        return FlakeClass.UNKNOWN
    if len(set(runs)) > 1:
        return FlakeClass.PROBABILISTIC
    if not solo_passed and suite_passed:
        return FlakeClass.ORDER_DEPENDENT
    if all(runs):
        return FlakeClass.DETERMINISTIC_PASS
    return FlakeClass.DETERMINISTIC_FAIL


def flake_report(outcomes: Iterable[Mapping[str, Any]]) -> dict:
    """Build a deterministic, sorted flake report from outcome mappings."""
    result: dict[str, str] = {}
    for outcome in outcomes or ():
        if not isinstance(outcome, Mapping):
            raise ContractValidationError("flake outcomes must be mappings")
        test_id = str(outcome.get("test_id", ""))
        classification = classify_flake(
            test_id,
            solo_passed=bool(outcome.get("solo_passed", False)),
            suite_passed=bool(outcome.get("suite_passed", False)),
            repeated_runs=outcome.get("repeated_runs", ()),
        )
        if test_id in result and result[test_id] != classification.value:
            raise ContractValidationError("conflicting classifications for %s" % test_id)
        result[test_id] = classification.value
    return {"classifications": {k: result[k] for k in sorted(result)}}


# ---------------------------------------------------------------------------
# E4.15 -- keyless recorded change log and plan-time test tiers
# ---------------------------------------------------------------------------

class TestTier(str, Enum):
    """Test tiers mirrored from the test-plan legend (U/C/I/G/P/E/A/S/D/F)."""

    UNIT = "unit"
    CONTRACT = "contract"
    INTEGRATION = "integration"
    GOLDEN = "golden"
    PROPERTY = "property"
    E2E = "e2e"
    ADVERSARIAL = "adversarial"
    SOAK = "soak"
    DIFFERENTIAL = "differential"
    FAULT_INJECTION = "fault-injection"

    def __str__(self) -> str:
        return self.value


TEST_TIERS = frozenset(tier.value for tier in TestTier)
_TIER_ALIASES = {
    "u": TestTier.UNIT, "c": TestTier.CONTRACT, "i": TestTier.INTEGRATION,
    "g": TestTier.GOLDEN, "p": TestTier.PROPERTY, "e": TestTier.E2E,
    "a": TestTier.ADVERSARIAL, "s": TestTier.SOAK, "d": TestTier.DIFFERENTIAL,
    "f": TestTier.FAULT_INJECTION,
    "fault injection": TestTier.FAULT_INJECTION,
    "fault_injection": TestTier.FAULT_INJECTION,
    "end-to-end": TestTier.E2E, "end_to_end": TestTier.E2E,
}
REQUIRED_TIERS_FOR_NEW_SURFACE = frozenset({
    TestTier.UNIT.value, TestTier.CONTRACT.value, TestTier.INTEGRATION.value,
    TestTier.E2E.value, TestTier.ADVERSARIAL.value,
})


def parse_test_tier(value: Any) -> TestTier:
    """Parse a tier code/name; unknown tiers fail closed."""
    if isinstance(value, TestTier):
        return value
    text = str(value or "").strip().lower()
    if text in _TIER_ALIASES:
        return _TIER_ALIASES[text]
    try:
        return TestTier(text)
    except ValueError as exc:
        raise ContractValidationError("unknown test tier: %s" % text) from exc


@dataclass(frozen=True)
class ChangeRecord:
    """A keyless log entry for a non-trivial change."""

    change_id: str
    summary: str
    model_visible: bool
    protocol_visible: bool
    human_visible: bool
    scenario_ref: str
    test_tiers: tuple[str, ...]
    new_capability_seam: bool = False
    lifecycle_variant: bool = False

    @property
    def is_nontrivial(self) -> bool:
        return (self.model_visible or self.protocol_visible or self.human_visible
                or bool(self.scenario_ref) or self.new_capability_seam
                or self.lifecycle_variant)

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "summary": self.summary,
            "model_visible": self.model_visible,
            "protocol_visible": self.protocol_visible,
            "human_visible": self.human_visible,
            "scenario_ref": self.scenario_ref,
            "test_tiers": list(self.test_tiers),
            "new_capability_seam": self.new_capability_seam,
            "lifecycle_variant": self.lifecycle_variant,
        }


def _validate_scenario_ref(value: Any) -> tuple[str, ...]:
    text = str(value or "")
    if not text:
        return ("a non-trivial change must update a recorded scenario",)
    if not _SAFE_SCENARIO_RE.match(text) or ".." in text:
        return ("scenario reference must be a safe keyless path",)
    if looks_like_secret(text):
        return ("scenario reference must not contain credentials",)
    return ()


def validate_change_record(record: ChangeRecord) -> tuple[str, ...]:
    """Validate keylessness, scenario coverage and named test tiers."""
    errors: list[str] = []
    if not _SAFE_ID_RE.match(str(record.change_id or "")):
        errors.append("change id must be a safe identifier")
    summary = str(record.summary or "")
    if not summary.strip():
        errors.append("change summary must not be empty")
    if looks_like_secret(summary):
        errors.append("change summary must not contain credentials")
    for flag in (record.model_visible, record.protocol_visible, record.human_visible,
                 record.new_capability_seam, record.lifecycle_variant):
        if not isinstance(flag, bool):
            errors.append("change visibility flags must be booleans")
    if record.is_nontrivial:
        errors.extend(_validate_scenario_ref(record.scenario_ref))
        if not record.test_tiers:
            errors.append("a non-trivial change must name its test tiers at plan time")
        for tier in record.test_tiers:
            try:
                parse_test_tier(tier)
            except ContractValidationError:
                errors.append("unknown test tier: %s" % tier)
        if record.new_capability_seam or record.lifecycle_variant:
            named: set[str] = set()
            for tier in record.test_tiers:
                try:
                    named.add(parse_test_tier(tier).value)
                except ContractValidationError:
                    pass
            missing = REQUIRED_TIERS_FOR_NEW_SURFACE - named
            if missing:
                errors.append("new surfaces must name required tiers: %s" %
                              ", ".join(sorted(missing)))
    elif record.scenario_ref:
        errors.extend(_validate_scenario_ref(record.scenario_ref))
    return tuple(dict.fromkeys(errors))


def make_change_record(
    change_id: Any,
    summary: Any,
    *,
    model_visible: Any = False,
    protocol_visible: Any = False,
    human_visible: Any = False,
    scenario_ref: Any = "",
    test_tiers: Iterable[Any] = (),
    new_capability_seam: Any = False,
    lifecycle_variant: Any = False,
) -> ChangeRecord:
    """Build and validate a keyless change record; fail closed on secrets."""
    tiers: list[str] = []
    for tier in test_tiers or ():
        try:
            tiers.append(parse_test_tier(tier).value)
        except ContractValidationError:
            tiers.append(str(tier))
    record = ChangeRecord(
        change_id=str(change_id or ""),
        summary=str(summary or ""),
        model_visible=bool(model_visible),
        protocol_visible=bool(protocol_visible),
        human_visible=bool(human_visible),
        scenario_ref=str(scenario_ref or ""),
        test_tiers=tuple(tiers),
        new_capability_seam=bool(new_capability_seam),
        lifecycle_variant=bool(lifecycle_variant),
    )
    errors = validate_change_record(record)
    if errors:
        raise ContractValidationError(errors)
    return record


@dataclass(frozen=True)
class ChangeLog:
    """An immutable, keyless, sorted collection of change records."""

    records: tuple[ChangeRecord, ...]

    def by_id(self, change_id: Any) -> ChangeRecord | None:
        target = str(change_id or "")
        return next((r for r in self.records if r.change_id == target), None)

    def to_dict(self) -> dict:
        return {"records": [r.to_dict() for r in self.records]}


def validate_change_log(log: ChangeLog) -> tuple[str, ...]:
    errors: list[str] = []
    ids: set[str] = set()
    for record in log.records:
        errors.extend(validate_change_record(record))
        if record.change_id in ids:
            errors.append("duplicate change id: %s" % record.change_id)
        ids.add(record.change_id)
    return tuple(dict.fromkeys(errors))


def make_change_log(records: Iterable[ChangeRecord] = ()) -> ChangeLog:
    """Build and validate a change log; order-independent and keyless."""
    log = ChangeLog(records=tuple(sorted(records or (), key=lambda r: r.change_id)))
    errors = validate_change_log(log)
    if errors:
        raise ContractValidationError(errors)
    return log


def add_change(log: ChangeLog, record: ChangeRecord) -> ChangeLog:
    """Return a new validated log with one more change record."""
    return make_change_log([*log.records, record])


def assert_keyless(log: ChangeLog) -> None:
    """Fail closed if any log field carries literal credential material."""
    errors: list[str] = []
    for field, value in log.to_dict().items():
        if looks_like_secret(value):
            errors.append("change log field %s is not keyless" % field)
    if errors:
        raise ContractValidationError(errors)


def assert_all_nontrivial_covered(log: ChangeLog) -> None:
    """Every non-trivial visible change must name a scenario and test tiers."""
    errors: list[str] = []
    for record in log.records:
        if record.is_nontrivial:
            errors.extend("%s: %s" % (record.change_id, error)
                          for error in validate_change_record(record))
    if errors:
        raise ContractValidationError(errors)


__all__ = [
    "FEATURE_IDS", "DIAGNOSTIC_BYTE_LIMIT", "ROOT_AGENT_NAME",
    "DEFAULT_AGENT_PREFIX", "MAX_AGENT_NAME_LEN", "AGENT_NAME_NOT_FOUND",
    "EXPECTED_TREE_ROOT", "RESERVED_AGENT_NAMES", "TEST_TIERS",
    "ALLOWED_HEADER_CLASSES", "ALLOWED_PROFILES", "MODE_REQUIREMENTS",
    "READ_ONLY_MODES", "REQUIRED_TIERS_FOR_NEW_SURFACE",
    "AgentNameNotFoundError", "AgentRegistry", "ChangeRecord", "ChangeLog",
    "ContractError", "ContractValidationError", "FlakeClass", "ForkExit",
    "RecordingPolicy", "ResourceKind", "ResourceLease", "Result",
    "SessionFileRef", "SessionHeader", "SnapshotConfig", "SnapshotMode",
    "SnapshotPair", "StopReason", "TestTier", "TokenKind", "TypedToken",
    "WorkspaceDiff", "WorkspaceManifest", "add_change", "assert_clean_diagnostics",
    "assert_all_nontrivial_covered", "assert_expected_immutable", "assert_isolated",
    "assert_keyless", "assert_snapshot_write_allowed", "build_result",
    "can_run_mode", "child_failure_to_result", "classify_flake",
    "compare_workspace", "default_agent_name", "detect_isolation_violations",
    "flake_report", "fork_exit_diagnostic", "is_json_safe", "is_read_only_mode",
    "is_reserved_agent_name", "last_assistant_message", "looks_like_secret",
    "make_agent_name", "make_agent_path", "make_change_log", "make_change_record",
    "make_lease", "make_registry", "make_snapshot_config", "make_snapshot_pair",
    "make_workspace_manifest", "mode_requirements", "normalize_schema",
    "parent_agent_path", "parse_session_file", "parse_stop_reason",
    "parse_stop_reason_safe", "parse_test_tier", "resolve_child_outcome",
    "resolve_name", "review_all_diffs", "sanitize_diagnostics",
    "snapshot_write_allowed", "validate_agent_name", "validate_agent_path",
    "validate_change_log", "validate_change_record", "validate_lease",
    "validate_snapshot_config", "validate_snapshot_pair", "validate_structured",
    "verify_identity_tokens",
]
