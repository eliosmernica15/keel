"""keel.command_contracts -- canonical W5.x command/slash-command contracts.

This is an *additive*, stdlib-only module.  It parses command definitions and
builds immutable descriptors; it never starts a process, reads or writes a
file, imports a provider, or executes a shell command.  Integration into the
live CLI is a separate lead decision (exact seams are documented in
``master-plan-v6-command-contracts-evidence.md``).

Contracts covered (Addendum 5, section 3.4 ``[T:OC-CMD]``):

  W5.1 Markdown or JSON definitions; nested folders become ``/team/review``;
       global vs project scope with deterministic precedence (project over
       global, nearer over ancestor, custom over built-in); content-addressed
       hot reload.
  W5.2 Frontmatter ``description``, ``agent``, ``model``, ``subagent`` with
       true/false/omit rules; legacy alias ``subtask``; typed validation.
  W5.3 Arguments: ``$ARGUMENTS``, positional ``$1..$n`` with quote grouping,
       last placeholder takes the rest, missing = empty, fallback append.
       Substitution is a single non-recursive pass: argument text is never
       re-scanned or shell-interpolated.
  W5.4 Shell-injection ``!`cmd` `` descriptors: parsed and described only.
       Output insertion requires an explicit approval flag; the descriptor
       carries a Tier 2 / permission-gate seam.  No execution happens here,
       and argument text can never create a new descriptor.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = [
    "Scope", "CommandFormat", "SourceKind",
    "CommandContractError", "CommandPathError", "CommandParseError",
    "CommandValidationError", "ArgumentParseError", "ShellApprovalError",
    "CommandSource", "CommandDescriptor", "CommandRegistry", "RegistryReload",
    "ArgumentRender", "ShellCommandDescriptor", "ShellInsertion",
    "PermissionGate", "RenderedPrompt",
    "assert_contained_command_path", "is_contained_command_path",
    "command_id_from_path", "command_title", "command_name",
    "parse_frontmatter", "parse_json_command", "parse_command_source",
    "tokenize_arguments", "substitute_arguments", "parse_shell_descriptors",
    "permission_gate_for", "render_shell_output", "render_command_prompt",
    "hot_reload",
]


# ---------------------------------------------------------------------------
# Vocabulary and typed failures
# ---------------------------------------------------------------------------


class Scope(str, Enum):
    GLOBAL = "global"
    PROJECT = "project"


class CommandFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class SourceKind(str, Enum):
    BUILTIN = "builtin"
    CUSTOM = "custom"


class CommandContractError(Exception):
    """Base type for every failure raised by this module."""


class CommandPathError(CommandContractError):
    def __init__(self, path: str, reason: str) -> None:
        self.path = str(path)
        self.reason = reason
        super().__init__(f"unsafe command path {self.path!r}: {reason}")


class CommandParseError(CommandContractError):
    def __init__(self, path: str, reason: str) -> None:
        self.path = str(path)
        self.reason = reason
        super().__init__(f"cannot parse command {self.path!r}: {reason}")


class CommandValidationError(CommandContractError):
    def __init__(self, path: str, field: str, reason: str,
                 value: Any = None) -> None:
        self.path = str(path)
        self.field = field
        self.reason = reason
        self.value = value
        super().__init__(f"{self.path}: invalid {field!r}: {reason}")


class ArgumentParseError(CommandContractError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"cannot tokenize arguments: {reason}")


class ShellApprovalError(CommandContractError):
    def __init__(self, descriptor_id: str, reason: str) -> None:
        self.descriptor_id = descriptor_id
        self.reason = reason
        super().__init__(f"shell descriptor {descriptor_id}: {reason}")


# ---------------------------------------------------------------------------
# W5.1 -- paths, ids, source declarations
# ---------------------------------------------------------------------------

_SUFFIX_TO_FORMAT = {".md": CommandFormat.MARKDOWN,
                     ".json": CommandFormat.JSON}
_ID_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _normalize_relative_path(relative_path: str, root: str | None) -> str:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise CommandPathError(str(relative_path), "empty path")
    raw = relative_path.strip()
    # Reject absolute/drive/UNC forms before any separator normalisation.
    if raw.startswith(("/", "\\")):
        raise CommandPathError(relative_path, "absolute path is not contained")
    if _DRIVE_RE.match(raw):
        raise CommandPathError(relative_path, "drive-qualified path")
    candidate = raw.replace("\\", "/")
    if candidate.startswith("//"):
        raise CommandPathError(relative_path, "UNC path")
    parts = candidate.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise CommandPathError(relative_path, "empty, dot or parent segment")
    if any("\x00" in part for part in parts):
        raise CommandPathError(relative_path, "NUL byte in path")
    if root is not None:
        # The root is an opaque anchor label (no I/O, no symlink resolution).
        # Strip both separator styles at its edges, including a POSIX-looking
        # absolute root on Windows, then reject inner dot/parent segments.
        root_text = str(root).strip().replace("\\", "/").strip("/")
        if not root_text or any(p in ("", ".", "..")
                                for p in root_text.split("/")):
            raise CommandPathError(relative_path, "invalid containment root")
    return candidate


def assert_contained_command_path(relative_path: str,
                                  root: str | Path | None = None) -> str:
    """Return a normalised, POSIX-style relative path or raise.

    Pure lexical containment: no filesystem lookup, no symlink resolution.
    Every parent/dot/absolute/drive/UNC segment is refused outright, so the
    returned path can never escape ``root`` when joined to it by a caller.
    """
    root_text = None if root is None else str(root)
    return _normalize_relative_path(relative_path, root_text)


def is_contained_command_path(relative_path: str,
                              root: str | Path | None = None) -> bool:
    try:
        assert_contained_command_path(relative_path, root)
    except CommandPathError:
        return False
    return True


def command_id_from_path(relative_path: str) -> str:
    """Map ``team/review.md`` to ``team/review`` (nested folders = `/` ids)."""
    path = assert_contained_command_path(relative_path, None)
    stem = path.rsplit("/", 1)[-1]
    dot = stem.rfind(".")
    if dot <= 0 or stem[dot:] not in _SUFFIX_TO_FORMAT:
        raise CommandPathError(relative_path, "unsupported command extension")
    segments = path.split("/")[:-1] + [stem[:dot].lower()]
    for segment in segments:
        lowered = segment.lower()
        if not _ID_SEGMENT_RE.match(lowered):
            raise CommandPathError(relative_path, f"invalid id segment {segment!r}")
    return "/".join(segment.lower() for segment in segments)


def command_title(command_id: str) -> str:
    return "/" + command_id


def command_name(command_id: str) -> str:
    return command_id.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class CommandSource:
    """A command definition as text plus the scope it was discovered under.

    Callers supply text and a repository-relative path; this module performs
    no I/O.  ``command_id`` is an optional explicit id for alias/override
    sources (for example a global config that targets a nested id from a
    flatter file) and is still validated for containment.
    """

    relative_path: str
    text: str
    scope: Scope = Scope.PROJECT
    format: CommandFormat | None = None
    command_id: str | None = None

    def __post_init__(self) -> None:
        assert_contained_command_path(self.relative_path, None)
        if not isinstance(self.scope, Scope):
            raise CommandValidationError(self.relative_path, "scope",
                                         "expected a Scope value", self.scope)
        if self.command_id is not None:
            if not isinstance(self.command_id, str) or not self.command_id:
                raise CommandValidationError(
                    self.relative_path, "command_id", "expected a non-empty id",
                    self.command_id)
            for segment in self.command_id.split("/"):
                if not _ID_SEGMENT_RE.match(segment.lower()):
                    raise CommandValidationError(
                        self.relative_path, "command_id",
                        f"invalid id segment {segment!r}", self.command_id)


@dataclass(frozen=True)
class CommandDescriptor:
    id: str
    title: str
    name: str
    description: str
    template: str
    argument_hint: str
    agent: str | None
    model: str | None
    subagent: bool | None
    subagent_source: str
    scope: Scope
    format: CommandFormat
    source_path: str
    source_kind: SourceKind = SourceKind.CUSTOM
    proximity: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "name": self.name,
            "description": self.description,
            "template": self.template,
            "argument_hint": self.argument_hint,
            "agent": self.agent,
            "model": self.model,
            "subagent": self.subagent,
            "subagent_source": self.subagent_source,
            "scope": self.scope.value,
            "format": self.format.value,
            "source_path": self.source_path,
            "source_kind": self.source_kind.value,
            "proximity": self.proximity,
        }

    def fingerprint(self) -> str:
        payload = self.to_dict()
        payload.pop("proximity", None)  # location, not definition content
        return _sha256(payload)


def _sha256(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# W5.2 -- frontmatter / JSON parsing and validation
# ---------------------------------------------------------------------------

_MISSING = object()
_KNOWN_FIELDS = frozenset({
    "description", "agent", "model", "subagent", "subtask",
    "argument-hint", "argument_hint", "template", "body", "prompt",
})


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner.strip()
    return value


def _yaml_scalar(value: str) -> Any:
    """Give unquoted flow/bool/number literals their native types.

    This is intentionally small (no YAML dependency): a quoted value is always
    a string, while unquoted ``[a, b]``, ``true`` and ``42`` become list/bool/
    int so that field validation can reject them with a typed error.
    """
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return _unquote(stripped)
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1].strip()
        return [item.strip() for item in inner.split(",")] if inner else []
    if stripped.startswith("{") and stripped.endswith("}"):
        inner = stripped[1:-1].strip()
        if not inner:
            return {}
        items: dict[str, str] = {}
        for item in inner.split(","):
            if ":" in item:
                key, val = item.split(":", 1)
                items[key.strip()] = val.strip()
        return items or stripped
    lowered = stripped.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if re.fullmatch(r"-?\d+", stripped):
        try:
            return int(stripped)
        except ValueError:
            return stripped
    return stripped


def parse_frontmatter(text: str, path: str = "<memory>", *,
                      required: bool = True) -> tuple[dict, str]:
    """Parse the minimal YAML-ish ``---`` frontmatter used by command files.

    With ``required=False`` a bodyless-frontmatter markdown file is accepted as
    pure prompt text (empty metadata).  Direct calls default to strict parsing.
    """
    if not isinstance(text, str):
        raise CommandParseError(path, "definition text must be a string")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        if not required:
            return {}, text
        raise CommandParseError(path, "missing frontmatter fence")
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise CommandParseError(path, "unterminated frontmatter fence")
    values: dict[str, Any] = {}
    for raw in lines[1:end]:
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if not match:
            raise CommandParseError(path, f"unparseable frontmatter line {line!r}")
        values[match.group(1).lower()] = _yaml_scalar(match.group(2))
    body = "".join(lines[end + 1:]).lstrip("\n")
    return values, body


def parse_json_command(text: str, path: str = "<memory>") -> tuple[dict, str]:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise CommandParseError(path, f"invalid JSON: {exc}") from None
    if not isinstance(payload, dict):
        raise CommandParseError(path, "command JSON must be an object")
    values = {str(key).lower(): value for key, value in payload.items()}
    template = ""
    for key in ("template", "body", "prompt"):
        if key in values:
            raw_template = values.pop(key)
            if not isinstance(raw_template, str):
                raise CommandValidationError(
                    path, key, "template must be a string", raw_template)
            template = raw_template
            break
    return values, template


def _as_string(value: Any, path: str, field: str) -> str | None:
    if value is None or value is _MISSING:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    raise CommandValidationError(path, field, "expected a string", value)


def _as_bool(value: Any, path: str, field: str) -> bool | None:
    if value is None or value is _MISSING:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise CommandValidationError(path, field, "expected true or false", value)


def _resolve_subagent(meta: Mapping[str, Any], path: str) -> tuple[bool | None, str]:
    explicit = meta.get("subagent", _MISSING)
    legacy = meta.get("subtask", _MISSING)
    if explicit is _MISSING and legacy is _MISSING:
        return None, "omitted"
    explicit_value = _as_bool(explicit, path, "subagent") if explicit is not _MISSING else _MISSING
    legacy_value = _as_bool(legacy, path, "subagent") if legacy is not _MISSING else _MISSING
    if explicit_value is not _MISSING and legacy_value is not _MISSING:
        if explicit_value != legacy_value:
            raise CommandValidationError(
                path, "subagent", "subagent and legacy subtask disagree",
                {"subagent": explicit_value, "subtask": legacy_value})
        return explicit_value, "field"
    if explicit_value is not _MISSING:
        return explicit_value, "field"
    return legacy_value, "legacy"


def parse_command_source(source: CommandSource, *, strict: bool = False) -> CommandDescriptor:
    path = source.relative_path
    fmt = source.format
    if fmt is None:
        suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if suffix not in _SUFFIX_TO_FORMAT:
            raise CommandPathError(path, "unsupported command extension")
        fmt = _SUFFIX_TO_FORMAT[suffix]
    if fmt is CommandFormat.MARKDOWN:
        meta, template = parse_frontmatter(source.text, path, required=False)
    else:
        meta, template = parse_json_command(source.text, path)

    if strict:
        for key in meta:
            if key not in _KNOWN_FIELDS:
                raise CommandValidationError(path, key, "unknown field", meta[key])

    command_id = source.command_id or command_id_from_path(path)
    description = (_as_string(meta.get("description"), path, "description")
                   or "(no description)")
    agent = _as_string(meta.get("agent"), path, "agent")
    model = _as_string(meta.get("model"), path, "model")
    subagent, subagent_source = _resolve_subagent(meta, path)
    hint = (_as_string(meta.get("argument-hint"), path, "argument-hint")
            or _as_string(meta.get("argument_hint"), path, "argument_hint")
            or "")
    return CommandDescriptor(
        id=command_id,
        title=command_title(command_id),
        name=command_name(command_id),
        description=description,
        template=template,
        argument_hint=hint,
        agent=agent,
        model=model,
        subagent=subagent,
        subagent_source=subagent_source,
        scope=source.scope,
        format=fmt,
        source_path=path,
        source_kind=SourceKind.CUSTOM,
        proximity=len(path.split("/")) - 1,
    )


def _builtin_descriptor(command_id: str) -> CommandDescriptor:
    return CommandDescriptor(
        id=command_id, title=command_title(command_id),
        name=command_name(command_id), description=f"Built-in /{command_id}",
        template="", argument_hint="", agent=None, model=None, subagent=None,
        subagent_source="omitted", scope=Scope.GLOBAL,
        format=CommandFormat.MARKDOWN, source_path="<builtin>",
        source_kind=SourceKind.BUILTIN, proximity=10_000,
    )


def _precedence_key(descriptor: CommandDescriptor) -> tuple[int, int, int, str, str, str]:
    """Higher wins.  custom > builtin, project > global, nearer > ancestor.

    The last components are stable string tie-breakers, so equal inputs in a
    different discovery order produce an identical registry.
    """
    return (
        1 if descriptor.source_kind is SourceKind.CUSTOM else 0,
        1 if descriptor.scope is Scope.PROJECT else 0,
        -descriptor.proximity,
        descriptor.source_path,
        descriptor.format.value,
        descriptor.fingerprint(),
    )


@dataclass(frozen=True)
class CommandRegistry:
    commands: tuple[CommandDescriptor, ...]
    builtin_ids: tuple[str, ...]
    fingerprint: str

    @classmethod
    def build(cls, sources: Iterable[CommandSource],
              builtin_ids: Iterable[str] = ()) -> CommandRegistry:
        builtins = tuple(sorted({str(item).lstrip("/").lower()
                                 for item in builtin_ids}))
        winners: dict[str, CommandDescriptor] = {}
        for descriptor in ([_builtin_descriptor(item) for item in builtins]
                           + [parse_command_source(src) for src in sources]):
            current = winners.get(descriptor.id)
            if current is None or _precedence_key(descriptor) > _precedence_key(current):
                winners[descriptor.id] = descriptor
        commands = tuple(winners[key] for key in sorted(winners))
        return cls(commands=commands, builtin_ids=builtins,
                   fingerprint=_sha256([item.to_dict() for item in commands]))

    def get(self, command_id: str) -> CommandDescriptor | None:
        key = str(command_id).lstrip("/").lower()
        return next((item for item in self.commands if item.id == key), None)

    def list_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.commands)

    def custom(self) -> tuple[CommandDescriptor, ...]:
        return tuple(item for item in self.commands
                     if item.source_kind is SourceKind.CUSTOM)


@dataclass(frozen=True)
class RegistryReload:
    registry: CommandRegistry
    changed: bool
    previous_fingerprint: str
    fingerprint: str
    added_ids: tuple[str, ...]
    removed_ids: tuple[str, ...]
    changed_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "previous_fingerprint": self.previous_fingerprint,
            "fingerprint": self.fingerprint,
            "added_ids": list(self.added_ids),
            "removed_ids": list(self.removed_ids),
            "changed_ids": list(self.changed_ids),
        }


def hot_reload(previous: CommandRegistry, sources: Iterable[CommandSource],
               builtin_ids: Iterable[str] | None = None) -> RegistryReload:
    """Pure rebuild: same content yields the same fingerprint and no change."""
    registry = CommandRegistry.build(
        sources, previous.builtin_ids if builtin_ids is None else builtin_ids)
    old = {item.id: item for item in previous.commands}
    new = {item.id: item for item in registry.commands}
    added = tuple(sorted(new.keys() - old.keys()))
    removed = tuple(sorted(old.keys() - new.keys()))
    changed = tuple(sorted(
        key for key in old.keys() & new.keys()
        if old[key].fingerprint() != new[key].fingerprint()))
    return RegistryReload(
        registry=registry,
        changed=bool(added or removed or changed
                     or registry.fingerprint != previous.fingerprint),
        previous_fingerprint=previous.fingerprint,
        fingerprint=registry.fingerprint,
        added_ids=added, removed_ids=removed, changed_ids=changed,
    )


# ---------------------------------------------------------------------------
# W5.3 -- argument tokenisation and substitution
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\$(ARGUMENTS|\{?\d+\}?)(?![0-9A-Za-z_])")


def tokenize_arguments(text: str) -> tuple[str, ...]:
    """Shell-style *tokenisation only* -- no expansion of any kind.

    Quotes group tokens (including an explicitly empty ``""`` token) and
    backslashes escape the next character.  ``$``, backticks, globs and
    separators remain ordinary characters inside tokens.
    """
    if text is None:
        return ()
    if not isinstance(text, str):
        raise ArgumentParseError("arguments must be a string")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=False)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escapedquotes = "\"'"
    try:
        return tuple(lexer)
    except ValueError as exc:
        raise ArgumentParseError(str(exc)) from None


@dataclass(frozen=True)
class ArgumentRender:
    text: str
    tokens: tuple[str, ...]
    raw_arguments: str
    placeholders: tuple[str, ...]
    fallback_appended: bool


def substitute_arguments(template: str, arguments: str,
                         tokens: tuple[str, ...] | None = None) -> ArgumentRender:
    """Single-pass substitution; replacement text is never re-scanned.

    ``$ARGUMENTS`` gets the raw argument string.  ``$1..$n`` get quote-grouped
    tokens; the highest positional placeholder used gets all remaining tokens
    joined by single spaces; a missing token becomes ``""``.  With no
    placeholder, arguments are appended after a blank line.
    """
    if not isinstance(template, str):
        raise ArgumentParseError("template must be a string")
    raw = "" if arguments is None else str(arguments)
    resolved_tokens = tokenize_arguments(raw) if tokens is None else tuple(tokens)
    matches = list(_PLACEHOLDER_RE.finditer(template))
    placeholders = tuple(
        "ARGUMENTS" if match.group(1) == "ARGUMENTS"
        else match.group(1).strip("{}")
        for match in matches)
    if not matches:
        text = template
        if raw:
            text = template.rstrip() + "\n\n" + raw
        return ArgumentRender(text=text, tokens=resolved_tokens,
                              raw_arguments=raw, placeholders=(),
                              fallback_appended=bool(raw))

    positional = [int(item) for item in placeholders if item.isdigit()]
    remainder_from = max(positional) if positional else None

    def replacement(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "ARGUMENTS":
            return raw
        index = int(token.strip("{}"))
        if index < 1:
            return ""
        if index == remainder_from:
            return " ".join(resolved_tokens[index - 1:])
        return resolved_tokens[index - 1] if index <= len(resolved_tokens) else ""

    text = _PLACEHOLDER_RE.sub(replacement, template)
    return ArgumentRender(text=text, tokens=resolved_tokens,
                          raw_arguments=raw, placeholders=placeholders,
                          fallback_appended=False)


# ---------------------------------------------------------------------------
# W5.4 -- shell descriptors (never executed here)
# ---------------------------------------------------------------------------

_SENTINEL_RE = re.compile("\x00KEEL_SHELL_(\\d+)\x00")


@dataclass(frozen=True)
class ShellCommandDescriptor:
    """A parsed ``!`command` `` marker, with an always-required approval seam."""

    id: str
    command: str
    raw: str
    position: int
    approval_required: bool = True
    tier: int = 2
    executed: bool = False
    output: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "raw": self.raw,
            "position": self.position,
            "approval_required": self.approval_required,
            "tier": self.tier,
            "executed": self.executed,
            "output": self.output,
            "permission_gate": "Tier2Shell",
            "runs_outside_agent_permission_flow": False,
        }


@dataclass(frozen=True)
class PermissionGate:
    tier: int
    gate: str
    approval_required: bool
    show_resolved_command: bool
    runs_outside_agent_permission_flow: bool


@dataclass(frozen=True)
class ShellInsertion:
    descriptor_id: str
    command: str
    output: str
    text: str
    approved: bool


@dataclass(frozen=True)
class RenderedPrompt:
    command_id: str
    text: str
    descriptors: tuple[ShellCommandDescriptor, ...]
    tokens: tuple[str, ...]
    placeholders: tuple[str, ...]
    fallback_appended: bool
    pending_descriptor_ids: tuple[str, ...]
    inserted_descriptor_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "text": self.text,
            "descriptors": [item.to_dict() for item in self.descriptors],
            "tokens": list(self.tokens),
            "placeholders": list(self.placeholders),
            "fallback_appended": self.fallback_appended,
            "pending_descriptor_ids": list(self.pending_descriptor_ids),
            "inserted_descriptor_ids": list(self.inserted_descriptor_ids),
            "pending": bool(self.pending_descriptor_ids),
        }


def parse_shell_descriptors(template: str) -> tuple[ShellCommandDescriptor, ...]:
    """Describe every ``!`cmd` `` marker in *template text only*.

    Backtick escapes (``\\```) are skipped; the command itself cannot contain a
    backtick or a newline.  Nothing is executed and no output is fabricated.
    """
    if not isinstance(template, str):
        return ()
    found: list[ShellCommandDescriptor] = []
    index = 0
    while index < len(template):
        if template[index] == "\\" and index + 1 < len(template) and template[index + 1] == "`":
            index += 2
            continue
        if template[index] == "!" and index + 1 < len(template) and template[index + 1] == "`":
            end = template.find("`", index + 2)
            if end == -1:
                break
            command = template[index + 2:end]
            if "\n" in command or "\r" in command:
                index = end + 1
                continue
            descriptor_id = hashlib.sha256(
                f"{index}|{command}".encode("utf-8")).hexdigest()[:12]
            found.append(ShellCommandDescriptor(
                id=descriptor_id, command=command,
                raw=template[index:end + 1], position=index))
            index = end + 1
            continue
        index += 1
    return tuple(found)


def permission_gate_for(descriptor: ShellCommandDescriptor) -> PermissionGate:
    return PermissionGate(
        tier=descriptor.tier, gate="Tier2Shell",
        approval_required=descriptor.approval_required,
        show_resolved_command=True,
        runs_outside_agent_permission_flow=False,
    )


def render_shell_output(descriptor: ShellCommandDescriptor, output: str,
                        approved: bool) -> ShellInsertion:
    """Insert caller-supplied output into the prompt, never run the command.

    The caller must pass an explicit ``approved=True`` after showing the
    resolved command to the user; otherwise this raises ``ShellApprovalError``.
    """
    if not approved or not descriptor.approval_required:
        raise ShellApprovalError(
            descriptor.id,
            "shell output requires explicit approval (show the resolved "
            "command and pass the Tier 2 permission gate first)")
    return ShellInsertion(descriptor_id=descriptor.id,
                          command=descriptor.command, output=str(output),
                          text=str(output), approved=True)


def render_command_prompt(
        command: CommandDescriptor, arguments: str = "",
        outputs: Mapping[str, str] | None = None,
        approvals: Mapping[str, bool] | None = None) -> RenderedPrompt:
    """Render a command prompt safely.

    Descriptors are parsed from the *template* before substitution and replaced
    with opaque sentinels.  Argument text therefore cannot introduce a new
    ``!`cmd` `` descriptor, and inserted output is never re-parsed.  Output is
    inserted only when the caller supplies both output and explicit approval.
    """
    descriptors = parse_shell_descriptors(command.template)
    working = command.template
    for index, descriptor in enumerate(descriptors):
        working = working.replace(
            descriptor.raw, f"\x00KEEL_SHELL_{index}\x00", 1)
    render = substitute_arguments(working, arguments)
    supplied = dict(outputs or {})
    granted = dict(approvals or {})
    pending: list[str] = []
    inserted: list[str] = []

    def restore(match: re.Match[str]) -> str:
        descriptor = descriptors[int(match.group(1))]
        if descriptor.id not in supplied:
            pending.append(descriptor.id)
            return descriptor.raw
        insertion = render_shell_output(
            descriptor, supplied[descriptor.id],
            bool(granted.get(descriptor.id, False)))
        inserted.append(descriptor.id)
        return insertion.text

    text = _SENTINEL_RE.sub(restore, render.text)
    return RenderedPrompt(
        command_id=command.id, text=text, descriptors=descriptors,
        tokens=render.tokens, placeholders=render.placeholders,
        fallback_appended=render.fallback_appended,
        pending_descriptor_ids=tuple(pending),
        inserted_descriptor_ids=tuple(inserted),
    )
