"""Y1.x P0 MCP / plugin / config contracts (stdlib only, additive).

This module is a *contract layer*: every function validates, normalises or
selects data and returns a structured, deterministic result. It never opens a
network socket, never spawns a subprocess and never applies a patch or writes
a file. The one byte-reading path (``{file:...}`` substitution) is injected by
the caller so even that stays under the host's control.

Feature coverage (PLAN-INDEX.json, source: Addendum 4 section 2.1 opencode):

* Y1.2  - model-dependent tool exposure (tool-exposure table by model family)
* Y1.3  - patch multi-file format parser (unified diff across files)
* Y1.4  - read limits and paging (2,000 lines / 50 KiB, long-line truncation)
* Y1.5  - glob/grep defaults and permission resource = pattern
* Y1.6  - edit unique-match requirement + formatter hook (validation only)
* Y1.7  - shell tool descriptor with safety fields
* Y1.8  - webfetch/websearch provider selection (free backends, policy seam)
* Y1.9  - question tool descriptor with capability negotiation + approval seam
* Y1.16 - canonical MCP permission naming + timeouts
* Y1.17 - ordered rule list, policies layer, explicit deny wins
* Y1.19 - config precedence algorithm and search order
* Y1.20 - {env:VAR} / {file:path} substitution with containment, no secret logs
* Y1.24 - compaction config validation and per-model resolution
* Y1.30 - plugin enable/disable DSL (data only, rejects code and unsafe tags)

Integration seams are documented at the bottom of the companion evidence file.
"""

from __future__ import annotations

import fnmatch
import os
import random
import re
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePath
from typing import Any, Callable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Public constants (values taken verbatim from the registry text)
# ---------------------------------------------------------------------------

READ_MAX_LINES = 2000
READ_MAX_BYTES = 50 * 1024           # 50 KiB per page
MEDIA_MAX_BYTES = 20 * 1024 * 1024   # images / PDFs up to 20 MiB

GLOB_DEFAULT_LIMIT = 100
GREP_DEFAULT_LIMIT = 100
TOOL_DEFAULT_TIMEOUT_SECONDS = 30

SHELL_DEFAULT_TIMEOUT_SECONDS = 120  # 2-minute foreground timeout
WEBFETCH_MAX_SECONDS = 120
MCP_DEFAULT_TIMEOUT_SECONDS = 30     # global mcp.timeout

FREE_WEBSEARCH_PROVIDERS: tuple[str, ...] = (
    "searxng", "duckduckgo", "wikipedia", "local-index",
)

SCOPE_PRIORITY: dict[str, int] = {
    "default": 0, "user": 1, "project": 2, "managed": 3,
}

# ---------------------------------------------------------------------------
# Typed errors (code is machine-readable; messages never carry secret values)
# ---------------------------------------------------------------------------


class ContractError(ValueError):
    """Base class for every contract validation failure."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(f"[{code}] {self.message}")


class ToolExposureError(ContractError):
    pass


class PatchParseError(ContractError):
    pass


class PagingError(ContractError):
    pass


class EditMatchError(ContractError):
    def __init__(self, code: str, *, count: int = 0) -> None:
        self.count = count
        super().__init__(code, f"match count {count}" if count else code)


class FormatterConfigError(ContractError):
    pass


class ShellDescriptorError(ContractError):
    pass


class ProviderPolicyError(ContractError):
    pass


class QuestionDescriptorError(ContractError):
    pass


class PermissionRuleError(ContractError):
    pass


class ConfigSubstitutionError(ContractError):
    pass


class CompactionConfigError(ContractError):
    def __init__(self, code: str, key: str = "") -> None:
        self.key = key
        super().__init__(code, f"key={key}" if key else code)


class PluginDSLError(ContractError):
    def __init__(self, code: str, token: str = "") -> None:
        self.token = token
        super().__init__(code, f"unsafe token {token!r}" if token else code)


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------


def _copy_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _copy_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_copy_value(v) for v in value)
    return value


def _contained(path: Any, root: Any) -> bool:
    """Pure string containment check (POSIX and Windows separators)."""
    candidate = os.path.normpath(str(path)).replace("\\", "/")
    anchor = os.path.normpath(str(root)).replace("\\", "/")
    return candidate == anchor or candidate.startswith(anchor.rstrip("/") + "/")


# ===========================================================================
# Y1.2 - model-dependent tool exposure
# ===========================================================================

EDIT_TOOLS: frozenset[str] = frozenset({"patch", "edit", "write"})

# Families that get the atomic ``patch`` dialect; every other family gets
# ``edit`` + ``write``. This is the tool-exposure table keyed by model family.
PATCH_FAMILIES: tuple[str, ...] = (
    "claude", "anthropic", "gpt", "openai", "o1", "o3", "gemini", "deepseek",
)
OTHER_FAMILIES: tuple[str, ...] = (
    "local", "llama", "mistral", "qwen", "cohere", "command", "unknown",
)
KNOWN_FAMILIES: tuple[str, ...] = PATCH_FAMILIES + OTHER_FAMILIES

_FAMILY_SPLIT_RE = re.compile(r"[/\\\-_:.]+")


@dataclass(frozen=True)
class ToolProfile:
    """A caller-supplied profile that can only further restrict exposure."""

    name: str = "default"
    allow: frozenset[str] = field(default_factory=frozenset)
    deny: frozenset[str] = field(default_factory=frozenset)


def model_family(model: str, *, family_map: Mapping[str, str] | None = None) -> str:
    """Normalise a model id to a tool-exposure family.

    An explicit ``family_map`` (model prefix -> family) wins via longest-prefix
    match; otherwise a known family token is located in the model id.
    """
    if not isinstance(model, str) or not model.strip():
        raise ToolExposureError("empty_model")
    normalised = model.strip().lower()
    if family_map:
        matches = [
            prefix for prefix in family_map
            if normalised == prefix.lower()
            or normalised.startswith(prefix.lower() + "-")
            or normalised.startswith(prefix.lower() + "/")
            or normalised.startswith(prefix.lower() + ":")
        ]
        if matches:
            return str(family_map[max(matches, key=len)]).lower()
    tokens = [t for t in _FAMILY_SPLIT_RE.split(normalised) if t]
    for family in KNOWN_FAMILIES:
        if family in tokens:
            return family
    return tokens[0] if tokens else "unknown"


def tools_for_model(
    model: str,
    *,
    all_tools: Sequence[str],
    profile: ToolProfile | None = None,
    family_map: Mapping[str, str] | None = None,
) -> list[str]:
    """Filter ``all_tools`` to exactly one edit dialect for the model family.

    ``patch`` families receive ``patch``; all others receive ``edit``+``write``.
    A :class:`ToolProfile` may only narrow the result (deny, then allow).
    """
    family = model_family(model, family_map=family_map)
    offered = {"patch"} if family in PATCH_FAMILIES else {"edit", "write"}
    base = set(all_tools)
    result = (base - EDIT_TOOLS) | (offered & base)
    if profile is not None:
        result -= set(profile.deny)
        if profile.allow:
            result &= set(profile.allow)
    return sorted(result)


# ===========================================================================
# Y1.3 - patch multi-file format parser (parse only, never apply)
# ===========================================================================


@dataclass(frozen=True)
class PatchHunk:
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[tuple[str, str], ...]  # (marker, content) marker in ' +- '
    added: int
    removed: int

    def to_dict(self) -> dict:
        return {
            "header": self.header,
            "old_start": self.old_start, "old_count": self.old_count,
            "new_start": self.new_start, "new_count": self.new_count,
            "added": self.added, "removed": self.removed,
        }


@dataclass(frozen=True)
class FilePatch:
    path: str
    op: str                       # add | update | delete | move
    hunks: tuple[PatchHunk, ...] = ()
    move_from: str | None = None
    move_to: str | None = None

    def to_dict(self) -> dict:
        return {
            "path": self.path, "op": self.op,
            "hunks": [h.to_dict() for h in self.hunks],
            "move_from": self.move_from, "move_to": self.move_to,
        }


@dataclass(frozen=True)
class PatchDescriptor:
    files: tuple[FilePatch, ...]
    affected_paths: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "files": [f.to_dict() for f in self.files],
            "affected_paths": list(self.affected_paths),
        }


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
_EXT_RE = re.compile(r"^\*\*\* (Add File|Update File|Delete File|Move to):\s*(.+?)\s*$")
_EXT_OPS = {"Add File": "add", "Update File": "update", "Delete File": "delete"}


def _strip_ab(path: str) -> str:
    cleaned = path.strip()
    if cleaned.startswith(("a/", "b/")):
        return cleaned[2:]
    if cleaned == "/dev/null":
        return ""
    return cleaned


def parse_patch(text: str) -> PatchDescriptor:
    """Parse a unified/multi-file patch into a descriptor.

    Supports both ``--- a/x / +++ b/x`` headers and the ``*** Add File:`` /
    ``*** Update File:`` / ``*** Delete File:`` / ``*** Move to:`` sections.
    Hunk line counts are validated; no file is read or written.
    """
    if not isinstance(text, str):
        raise PatchParseError("bad_patch")

    files: list[FilePatch] = []
    current: dict[str, Any] | None = None
    hunks: list[PatchHunk] = []
    hunk_header: dict[str, Any] | None = None
    hunk_lines: list[tuple[str, str]] = []

    def finish_hunk() -> None:
        nonlocal hunk_header, hunk_lines
        if hunk_header is None:
            return
        context = sum(1 for marker, _ in hunk_lines if marker == " ")
        added = sum(1 for marker, _ in hunk_lines if marker == "+")
        removed = sum(1 for marker, _ in hunk_lines if marker == "-")
        old_actual = context + removed
        new_actual = context + added
        if old_actual != hunk_header["old_count"] or new_actual != hunk_header["new_count"]:
            raise PatchParseError("hunk_count_mismatch")
        hunks.append(PatchHunk(
            header=hunk_header["header"],
            old_start=hunk_header["old_start"], old_count=hunk_header["old_count"],
            new_start=hunk_header["new_start"], new_count=hunk_header["new_count"],
            lines=tuple(hunk_lines), added=added, removed=removed,
        ))
        hunk_header = None
        hunk_lines = []

    def finish_file() -> None:
        nonlocal current, hunks
        finish_hunk()
        if current is None:
            return
        if current["op"] == "move":
            patch = FilePatch(
                path=current["path"], op="move", hunks=tuple(hunks),
                move_from=current.get("original"), move_to=current["path"],
            )
        else:
            patch = FilePatch(path=current["path"], op=current["op"], hunks=tuple(hunks))
        files.append(patch)
        current = None
        hunks = []

    for raw in text.splitlines():
        line = raw.rstrip("\r")
        ext = _EXT_RE.match(line)
        if ext:
            kind, value = ext.group(1), ext.group(2).strip()
            if kind == "Move to":
                finish_hunk()
                if current is None:
                    raise PatchParseError("move_without_file")
                current.setdefault("original", current["path"])
                current["path"] = value
                current["op"] = "move"
                continue
            finish_file()
            current = {"path": value, "op": _EXT_OPS[kind]}
            continue
        if line.startswith("diff --git ") or line.startswith("*** Begin Patch") \
                or line.startswith("*** End Patch"):
            finish_file()
            continue
        if line.startswith("--- "):
            finish_file()
            old = _strip_ab(line[4:])
            current = {"path": old, "op": "add" if old == "" else "update"}
            continue
        if line.startswith("+++ "):
            if current is None:
                raise PatchParseError("no_file_header")
            new_path = _strip_ab(line[4:])
            if new_path:
                current["path"] = new_path
            continue
        if line.startswith("@@"):
            finish_hunk()
            match = _HUNK_RE.match(line)
            if match is None:
                raise PatchParseError("bad_hunk_header")
            hunk_header = {
                "header": line,
                "old_start": int(match.group(1)),
                "old_count": int(match.group(2) or 1),
                "new_start": int(match.group(3)),
                "new_count": int(match.group(4) or 1),
            }
            continue
        if hunk_header is not None and line[:1] in (" ", "+", "-"):
            hunk_lines.append((line[0], line[1:]))

    finish_file()
    if not files:
        raise PatchParseError("no_file_header")

    affected: list[str] = []
    for patch in files:
        for candidate in (patch.move_from, patch.path):
            if candidate and candidate not in affected:
                affected.append(candidate)
    return PatchDescriptor(tuple(files), tuple(affected))


# ===========================================================================
# Y1.4 - read limits and paging
# ===========================================================================


@dataclass(frozen=True)
class PageResult:
    lines: tuple[str, ...]
    text: str
    offset: int
    next_offset: int
    limit: int
    max_bytes: int
    included: int
    omitted_lines: int
    omitted_bytes: int
    truncated: bool
    marker: str | None
    line_truncated: bool

    def to_dict(self) -> dict:
        return {
            "lines": list(self.lines), "text": self.text,
            "offset": self.offset, "next_offset": self.next_offset,
            "included": self.included, "omitted_lines": self.omitted_lines,
            "omitted_bytes": self.omitted_bytes, "truncated": self.truncated,
            "marker": self.marker, "line_truncated": self.line_truncated,
        }


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _utf8_prefix(text: str, budget: int) -> str:
    return text.encode("utf-8")[:budget].decode("utf-8", errors="ignore")


def page(
    lines: Sequence[str],
    offset: int = 0,
    limit: int = READ_MAX_LINES,
    max_bytes: int = READ_MAX_BYTES,
) -> PageResult:
    """Return a deterministic page of ``lines`` with a truncation marker.

    Line count and byte budget are both enforced; a single over-long line is
    truncated on a UTF-8 boundary. ``next_offset`` is always safe to page from.
    """
    if offset < 0:
        raise PagingError("bad_offset")
    if limit < 0:
        raise PagingError("bad_limit")
    if max_bytes < 1:
        raise PagingError("bad_max_bytes")

    seq = list(lines)
    candidates = seq[offset:offset + limit]
    output: list[str] = []
    used = 0
    line_truncated = False
    for raw in candidates:
        line = raw if isinstance(raw, str) else str(raw)
        size = _utf8_len(line)
        if used + size <= max_bytes:
            output.append(line)
            used += size
            continue
        if used == 0:
            # A single line larger than the whole budget is truncated on a
            # UTF-8 boundary; otherwise the page simply ends before this line.
            output.append(_utf8_prefix(line, max_bytes))
            line_truncated = True
        break

    included = len(output)
    omitted = seq[offset + included:]
    omitted_bytes = sum(_utf8_len(str(item)) for item in omitted)
    truncated = bool(omitted) or line_truncated
    next_offset = offset + included
    marker: str | None = None
    if truncated:
        extra = " line_truncated=1" if line_truncated else ""
        marker = (
            f"[keel:truncated omitted_lines={len(omitted)} "
            f"omitted_bytes={omitted_bytes} next_offset={next_offset}{extra}]"
        )
    rendered = list(output) + ([marker] if marker else [])
    return PageResult(
        lines=tuple(output), text="\n".join(rendered), offset=offset,
        next_offset=next_offset, limit=limit, max_bytes=max_bytes,
        included=included, omitted_lines=len(omitted), omitted_bytes=omitted_bytes,
        truncated=truncated, marker=marker, line_truncated=line_truncated,
    )


# ===========================================================================
# Y1.5 - glob/grep defaults
# ===========================================================================


def _search_defaults() -> dict[str, Any]:
    return {
        "limit": 100,
        "timeout_seconds": TOOL_DEFAULT_TIMEOUT_SECONDS,
        "literal": False,
        "include": None,
        "case_sensitive": True,
        "hidden": False,
    }


def glob_defaults() -> dict[str, Any]:
    return _search_defaults()


def grep_defaults() -> dict[str, Any]:
    return _search_defaults()


def resolve_search_options(kind: str, options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Merge caller options over registry defaults, validating types."""
    if kind not in ("glob", "grep"):
        raise ContractError("unknown_search_kind")
    resolved = _search_defaults()
    if options is None:
        return resolved
    if not isinstance(options, Mapping):
        raise ContractError("bad_options")
    for key, value in options.items():
        if key not in resolved:
            raise ContractError("unknown_option")
        resolved[key] = value
    if isinstance(resolved["limit"], bool) or not isinstance(resolved["limit"], int) \
            or resolved["limit"] < 1:
        raise ContractError("bad_limit")
    if isinstance(resolved["timeout_seconds"], bool) \
            or not isinstance(resolved["timeout_seconds"], (int, float)) \
            or resolved["timeout_seconds"] <= 0:
        raise ContractError("bad_timeout")
    for flag in ("literal", "case_sensitive", "hidden"):
        if not isinstance(resolved[flag], bool):
            raise ContractError("bad_flag")
    if resolved["include"] is not None and not isinstance(resolved["include"], str):
        raise ContractError("bad_include")
    return resolved


def grep_permission_resource(pattern: str) -> str:
    """The grep permission resource is the *pattern*, not a path."""
    if not isinstance(pattern, str) or not pattern:
        raise ContractError("bad_pattern")
    return pattern


# ===========================================================================
# Y1.6 - edit unique-match requirement and formatter hook seam
# ===========================================================================


@dataclass(frozen=True)
class MatchValidation:
    count: int
    replace_all: bool
    ok: bool = True


def check_unique_match(text: str, old: str, *, replace_all: bool = False) -> MatchValidation:
    """Pure validation: exactly one match unless ``replace_all`` is set."""
    if not isinstance(text, str) or not isinstance(old, str):
        raise EditMatchError("bad_input")
    if old == "":
        raise EditMatchError("empty_old_string")
    count = text.count(old)
    if count == 0:
        raise EditMatchError("not_found", count=0)
    if count > 1 and not replace_all:
        raise EditMatchError("ambiguous", count=count)
    return MatchValidation(count=count, replace_all=bool(replace_all))


@dataclass(frozen=True)
class FormatterSpec:
    command: str | None
    extensions: tuple[str, ...]
    enabled: bool

    def to_dict(self) -> dict:
        return {"command": self.command, "extensions": list(self.extensions), "enabled": self.enabled}


def validate_formatter_config(config: Mapping[str, Any] | None) -> FormatterSpec:
    """Validate the optional post-write formatter config without running it."""
    if config is None:
        return FormatterSpec(None, (), False)
    if not isinstance(config, Mapping):
        raise FormatterConfigError("bad_config")
    command = config.get("command")
    if not isinstance(command, str) or not command.strip():
        raise FormatterConfigError("missing_command")
    extensions = config.get("extensions", ())
    if extensions is None:
        extensions = ()
    if not isinstance(extensions, (list, tuple)) or any(not isinstance(x, str) for x in extensions):
        raise FormatterConfigError("bad_extensions")
    enabled = config.get("enabled", True)
    if not isinstance(enabled, bool):
        raise FormatterConfigError("bad_enabled")
    return FormatterSpec(command, tuple(extensions), enabled)


# ===========================================================================
# Y1.7 - shell tool descriptor (data only, never executes)
# ===========================================================================


@dataclass(frozen=True)
class ShellDescriptor:
    command: str
    shell: str
    cwd: str | None
    timeout_seconds: int
    background: bool
    returns_immediately: bool
    permission_resources: tuple[str, ...]
    external_workdirs: tuple[str, ...]
    safety: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "command": self.command, "shell": self.shell, "cwd": self.cwd,
            "timeout_seconds": self.timeout_seconds, "background": self.background,
            "returns_immediately": self.returns_immediately,
            "permission_resources": list(self.permission_resources),
            "external_workdirs": list(self.external_workdirs),
            "safety": dict(self.safety),
        }


_CD_RE = re.compile(r"(?:^|[;&|\n]\s*)cd(?:\s|$)", re.IGNORECASE)
_SUBCOMMAND_SPLIT_RE = re.compile(r"[;&|\n]+")


def _split_subcommands(command: str) -> list[str]:
    return [part.strip() for part in _SUBCOMMAND_SPLIT_RE.split(command) if part.strip()]


def shell_descriptor(
    command: str,
    *,
    workdir: str | None = None,
    shell: str | None = None,
    timeout_seconds: int = SHELL_DEFAULT_TIMEOUT_SECONDS,
    background: bool = False,
    allowed_roots: Sequence[str] = (),
) -> ShellDescriptor:
    """Build a shell-tool descriptor with one permission resource per sub-command."""
    if not isinstance(command, str) or not command.strip():
        raise ShellDescriptorError("empty_command")
    if _CD_RE.search(command):
        raise ShellDescriptorError("cd_in_command")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) \
            or timeout_seconds <= 0:
        raise ShellDescriptorError("bad_timeout")

    resources = tuple("shell:" + part for part in _split_subcommands(command))
    externals: tuple[str, ...] = ()
    if workdir and allowed_roots and not any(_contained(workdir, root) for root in allowed_roots):
        externals = (str(workdir),)

    return ShellDescriptor(
        command=command, shell=shell or "sh", cwd=workdir,
        timeout_seconds=timeout_seconds, background=bool(background),
        returns_immediately=bool(background), permission_resources=resources,
        external_workdirs=externals,
        safety={
            "cd_in_command": False,
            "no_subprocess_execution": True,
            "one_permission_per_subcommand": True,
            "external_workdir_checked": bool(allowed_roots),
            "large_output_policy": "truncate_with_managed_file",
            "notify_on_finish": bool(background),
        },
    )


# ===========================================================================
# Y1.8 - webfetch/websearch provider selection (free backends only)
# ===========================================================================


def select_websearch_provider(
    requested: str,
    *,
    available: Sequence[str] = (),
    policy: Callable[[str, str], bool] | None = None,
    seed: int = 0,
) -> str:
    """Select a free websearch provider; ``random`` is deterministic per seed."""
    if not isinstance(requested, str) or not requested.strip():
        raise ProviderPolicyError("bad_provider")
    requested = requested.strip().lower()
    available = list(available) if available else list(FREE_WEBSEARCH_PROVIDERS)
    if requested == "random":
        candidates = sorted({p for p in available if p in FREE_WEBSEARCH_PROVIDERS})
        if not candidates:
            raise ProviderPolicyError("no_free_provider")
        chosen = random.Random(seed).choice(candidates)
    else:
        if requested not in FREE_WEBSEARCH_PROVIDERS:
            raise ProviderPolicyError("non_free_provider")
        if available and requested not in available:
            raise ProviderPolicyError("unavailable")
        chosen = requested
    if policy is not None and policy(chosen, "websearch") is False:
        raise ProviderPolicyError("policy_denied")
    return chosen


def validate_fetch_target(url: str, *, policy: Callable[[str, str], bool] | None = None) -> str:
    """Scheme allowlist + caller policy seam. No DNS, sockets or requests."""
    if not isinstance(url, str) or not url.strip():
        raise ProviderPolicyError("bad_url")
    scheme = url.strip().lower().split(":", 1)[0] if ":" in url else ""
    if scheme not in ("http", "https"):
        raise ProviderPolicyError("bad_scheme")
    if policy is not None and policy(url, "webfetch") is False:
        raise ProviderPolicyError("policy_denied")
    return url


def webfetch_descriptor(
    url: str,
    *,
    format: str = "markdown",
    max_seconds: int = WEBFETCH_MAX_SECONDS,
    content_type: str = "text/html",
    policy: Callable[[str, str], bool] | None = None,
) -> dict[str, Any]:
    """Validate a webfetch request into a descriptor without fetching it."""
    validate_fetch_target(url, policy=policy)
    if format not in ("markdown", "text", "html"):
        raise ProviderPolicyError("bad_format")
    if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) \
            or max_seconds <= 0 or max_seconds > WEBFETCH_MAX_SECONDS:
        raise ProviderPolicyError("timeout_out_of_range")
    base_type = content_type.split(";", 1)[0].strip().lower() if isinstance(content_type, str) else ""
    if base_type.startswith(("image/", "audio/", "video/", "application/octet-stream")):
        raise ProviderPolicyError("binary_rejected")
    return {
        "url": url, "format": format, "max_seconds": max_seconds,
        "content_type": content_type, "no_network": True,
        "policy_applied": policy is not None,
        "ssrf_policy": "caller_policy_seam",
    }


# ===========================================================================
# Y1.9 - question tool descriptor
# ===========================================================================


@dataclass(frozen=True)
class QuestionDescriptor:
    question: str
    header: str | None
    options: tuple[dict[str, str], ...]
    multiple: bool
    timeout_seconds: int
    default: Any
    free_form_allowed: bool
    cancel_on_dismiss: bool
    ui_available: bool
    capability_known: bool
    mode: str
    requires_approval: bool

    def to_dict(self) -> dict:
        return {
            "question": self.question, "header": self.header,
            "options": [dict(o) for o in self.options], "multiple": self.multiple,
            "timeout_seconds": self.timeout_seconds, "default": self.default,
            "free_form_allowed": self.free_form_allowed,
            "cancel_on_dismiss": self.cancel_on_dismiss,
            "ui_available": self.ui_available, "capability_known": self.capability_known,
            "mode": self.mode, "requires_approval": self.requires_approval,
        }


def question_descriptor(
    question: str,
    *,
    header: str | None = None,
    options: Sequence[Any] = (),
    multiple: bool = False,
    timeout_seconds: int = 30,
    default: Any = None,
    client_can_render: bool | None = None,
    approval_policy: Callable[[QuestionDescriptor], bool] | None = None,
) -> QuestionDescriptor:
    """Describe an interactive question with negotiation and approval seams."""
    if not isinstance(question, str) or not question.strip():
        raise QuestionDescriptorError("empty_question")
    if options is None:
        options = ()
    normalised: list[dict[str, str]] = []
    for option in options:
        if isinstance(option, str):
            normalised.append({"label": option, "value": option})
        elif isinstance(option, Mapping) and isinstance(option.get("value"), str):
            normalised.append({
                "label": str(option.get("label", option["value"])),
                "value": option["value"],
            })
        else:
            raise QuestionDescriptorError("bad_option")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) \
            or timeout_seconds <= 0:
        raise QuestionDescriptorError("bad_timeout")

    values = [option["value"] for option in normalised]
    if default is not None:
        if multiple:
            if not isinstance(default, (list, tuple)) or any(v not in values for v in default):
                raise QuestionDescriptorError("bad_default")
        elif default not in values:
            raise QuestionDescriptorError("bad_default")

    known = isinstance(client_can_render, bool)
    ui_available = client_can_render is True
    descriptor = QuestionDescriptor(
        question=question, header=header, options=tuple(normalised),
        multiple=bool(multiple), timeout_seconds=timeout_seconds, default=default,
        free_form_allowed=True, cancel_on_dismiss=True,
        ui_available=ui_available, capability_known=known,
        mode="form" if ui_available else "text", requires_approval=False,
    )
    if approval_policy is not None:
        descriptor = replace(descriptor, requires_approval=bool(approval_policy(descriptor)))
    return descriptor


# ===========================================================================
# Y1.16 / Y1.17 - permission naming, ordered rules and policy layer
# ===========================================================================

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _sanitize(name: str) -> str:
    return _SANITIZE_RE.sub("_", name)


def canonical_mcp_permission(server: str, tool: str) -> str:
    """Canonical permission name ``mcp.<server>.<tool>``."""
    if not isinstance(server, str) or not server.strip():
        raise PermissionRuleError("empty_server")
    if not isinstance(tool, str) or not tool.strip():
        raise PermissionRuleError("empty_tool")
    return f"mcp.{_sanitize(server.strip())}.{_sanitize(tool.strip())}"


def mcp_timeout(
    server: str,
    *,
    per_server: Mapping[str, int] | None = None,
    global_timeout: int = MCP_DEFAULT_TIMEOUT_SECONDS,
) -> int:
    """Resolve per-server timeout, falling back to the global ``mcp.timeout``."""
    value = per_server.get(server) if per_server else None
    if value is None:
        value = global_timeout
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PermissionRuleError("bad_timeout")
    return value


@dataclass(frozen=True)
class PermissionRule:
    """One ``{action, resource, effect}`` entry of an ordered rule list."""

    action: str
    resource: str
    effect: str
    timeout_seconds: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or not self.action:
            raise PermissionRuleError("bad_action")
        if not isinstance(self.resource, str) or not self.resource:
            raise PermissionRuleError("bad_resource")
        if self.effect not in ("allow", "ask", "deny"):
            raise PermissionRuleError("bad_effect")

    def matches(self, action: str, resource: str) -> bool:
        return (fnmatch.fnmatchcase(str(action), self.action)
                and fnmatch.fnmatchcase(str(resource), self.resource))

    def to_dict(self) -> dict:
        return {
            "action": self.action, "resource": self.resource, "effect": self.effect,
            "timeout_seconds": self.timeout_seconds,
        }


def mcp_permission_rule(
    server: str,
    tool: str,
    *,
    effect: str = "allow",
    timeout_seconds: int | None = None,
    global_timeout: int = MCP_DEFAULT_TIMEOUT_SECONDS,
) -> PermissionRule:
    """Canonical MCP rule: action ``mcp.<server>.<tool>``, resource ``*``."""
    per_server = {server: timeout_seconds} if timeout_seconds is not None else None
    return PermissionRule(
        canonical_mcp_permission(server, tool), "*", effect,
        mcp_timeout(server, per_server=per_server, global_timeout=global_timeout),
    )


def _as_rule(rule: Any) -> PermissionRule:
    if isinstance(rule, PermissionRule):
        return rule
    if isinstance(rule, Mapping):
        return PermissionRule(
            rule["action"], rule["resource"], rule["effect"],
            rule.get("timeout_seconds"),
        )
    raise PermissionRuleError("bad_rule")


def evaluate_rules(
    rules: Sequence[Any],
    action: str,
    resource: str,
    *,
    default: str = "deny",
) -> str:
    """Evaluate an ordered rule list; an explicit deny always wins.

    Among matching allows the *last* rule wins (later entries override
    earlier ones); ``ask`` outranks ``allow`` but never ``deny``.
    """
    if default not in ("allow", "ask", "deny"):
        raise PermissionRuleError("bad_default")
    has_ask = False
    has_allow = False
    for raw in rules or ():
        rule = _as_rule(raw)
        if not rule.matches(action, resource):
            continue
        if rule.effect == "deny":
            return "deny"
        if rule.effect == "ask":
            has_ask = True
        else:
            has_allow = True
    if has_ask:
        return "ask"
    if has_allow:
        return "allow"
    return default


_EXTENSION_KINDS = ("mcp", "skill", "plugin")


def tool_use_rule(tool: str, resource: str, effect: str) -> PermissionRule:
    """Build a ``tool.use`` rule with a ``shell:git push *`` style resource."""
    return PermissionRule("tool.use", f"{tool}:{resource}", effect)


def block_extension(kind: str, identifier: str, *, effect: str = "deny") -> PermissionRule:
    """Build a policy-layer rule that blocks an MCP server / skill / plugin."""
    if kind not in _EXTENSION_KINDS:
        raise PermissionRuleError("bad_extension_kind")
    return PermissionRule(f"{kind}.block", identifier, effect)


def _block_matches(rule: PermissionRule, action: str, resource: str) -> bool:
    kind = rule.action[:-len(".block")]
    action_text = str(action)
    if not (action_text == kind or action_text.startswith(kind + ".")):
        return False
    identifier = rule.resource
    if identifier in ("*", ""):
        return True
    return identifier in action_text or identifier == str(resource)


def evaluate_permissions(
    *,
    config_rules: Sequence[Any] = (),
    policy_rules: Sequence[Any] = (),
    action: str,
    resource: str,
    default: str = "deny",
) -> str:
    """Combine normal config rules with the higher-priority policies layer.

    A policy deny (including extension blocks) outranks everything; a config
    deny still wins over a policy allow, so "explicit deny wins" is preserved.
    """
    for raw in policy_rules or ():
        rule = _as_rule(raw)
        if rule.effect == "deny" and rule.action.endswith(".block") \
                and _block_matches(rule, action, resource):
            return "deny"
    policy_effect = evaluate_rules(policy_rules, action, resource, default="allow")
    if policy_effect == "deny":
        return "deny"
    config_effect = evaluate_rules(config_rules, action, resource, default=default)
    if config_effect == "deny":
        return "deny"
    if policy_effect == "ask":
        return "ask"
    if policy_effect == "allow":
        return "allow"
    return config_effect


# ===========================================================================
# Y1.19 - config precedence algorithm and search order
# ===========================================================================

_RULE_LIST_KEYS = ("permissions", "rules", "config_rules", "policy_rules")


def _deep_merge(dest: dict[str, Any], src: Mapping[str, Any]) -> None:
    for key, value in src.items():
        if isinstance(value, Mapping) and isinstance(dest.get(key), Mapping):
            _deep_merge(dest[key], value)
        elif isinstance(value, list) and key in _RULE_LIST_KEYS:
            dest[key] = list(dest.get(key, [])) + list(value)
        else:
            dest[key] = _copy_value(value)


def merge_config_layers(layers: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Deep-merge scope layers from lowest to highest precedence.

    Permission rule lists are concatenated (lowest first) rather than
    replaced, so a deny in any layer survives into the effective config.
    """
    if not isinstance(layers, Mapping):
        raise ContractError("bad_layers")
    if set(layers) - set(SCOPE_PRIORITY):
        raise ContractError("unknown_scope")
    result: dict[str, Any] = {}
    for _, layer in sorted(layers.items(), key=lambda item: SCOPE_PRIORITY[item[0]]):
        if not isinstance(layer, Mapping):
            raise ContractError("bad_layer")
        _deep_merge(result, layer)
    return result


@dataclass(frozen=True)
class EffectiveConfig:
    config: dict[str, Any]
    provenance: dict[str, str]

    def to_dict(self) -> dict:
        return {"config": _copy_value(self.config), "provenance": dict(self.provenance)}


def _trace_provenance(obj: Mapping[str, Any], prefix: str, scope: str, out: dict[str, str]) -> None:
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            _trace_provenance(value, path, scope, out)
        else:
            out[path] = scope


def effective_config(
    *,
    default: Mapping[str, Any] | None = None,
    user: Mapping[str, Any] | None = None,
    project: Mapping[str, Any] | None = None,
    managed: Mapping[str, Any] | None = None,
) -> EffectiveConfig:
    """Merge default < user < project < managed and trace each key's source."""
    layers: dict[str, Mapping[str, Any]] = {}
    for scope, value in (("default", default), ("user", user),
                         ("project", project), ("managed", managed)):
        if value is not None:
            layers[scope] = value
    config = merge_config_layers(layers)
    provenance: dict[str, str] = {}
    for scope in sorted(layers, key=lambda name: SCOPE_PRIORITY[name]):
        _trace_provenance(layers[scope], "", scope, provenance)
    return EffectiveConfig(config=config, provenance=provenance)


def config_search_order(
    cwd: Any,
    *,
    root: Any = None,
    direct_name: str = "keel.jsonc",
    dir_name: str = ".keel",
) -> list[dict[str, str]]:
    """Deterministic config search: defaults, root->cwd direct then dot-dir,
    user, managed/system last (highest precedence)."""
    cwd_path = PurePath(cwd)
    root_path = PurePath(root) if root is not None else PurePath(cwd_path.anchor)
    try:
        parts = cwd_path.relative_to(root_path).parts
    except ValueError as exc:
        raise ContractError("root_not_parent_of_cwd") from exc

    chain = [root_path]
    current = root_path
    for part in parts:
        current = current / part
        chain.append(current)

    entries: list[dict[str, str]] = [
        {"scope": "default", "path": "<defaults>", "kind": "defaults"}
    ]
    for directory in chain:
        entries.append({
            "scope": "project", "path": str(directory / direct_name), "kind": "direct",
        })
        entries.append({
            "scope": "project", "path": str(directory / dir_name / direct_name),
            "kind": "dot_dir",
        })
    entries.append({"scope": "user", "path": "~/.keel/keel.jsonc", "kind": "user"})
    entries.append({
        "scope": "managed", "path": "<managed>/keel-policy.json", "kind": "managed",
    })
    return entries


# ===========================================================================
# Y1.20 - {env:VAR} / {file:path} substitution
# ===========================================================================

_SUB_RE = re.compile(r"\{(env|file):([^{}]+)\}")
_SECRET_NAME_RE = re.compile(
    r"(SECRET|TOKEN|PASSWORD|PASSWD|APIKEY|API_KEY|CREDENTIAL|PRIVATE_KEY)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SubstitutionWarning:
    kind: str
    key: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "key": self.key}


@dataclass(frozen=True)
class SubstitutionResult:
    value: Any
    warnings: tuple[SubstitutionWarning, ...]

    def to_dict(self) -> dict:
        return {
            "value": _copy_value(self.value),
            "warnings": [w.to_dict() for w in self.warnings],
        }


def _substitute_walk(value: Any, transform: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, Mapping):
        return {key: _substitute_walk(item, transform) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute_walk(item, transform) for item in value]
    if isinstance(value, tuple):
        return tuple(_substitute_walk(item, transform) for item in value)
    return value


def substitute_config(
    value: Any,
    *,
    env: Mapping[str, str] | None = None,
    base_dir: Any = None,
    file_reader: Callable[[Path], str] | None = None,
) -> SubstitutionResult:
    """Recursively substitute ``{env:VAR}`` and ``{file:path}`` in config data.

    Missing variables/files become the empty string with a warning; warnings
    carry only the *name*, never the resolved secret value. File paths must
    stay inside ``base_dir`` (traversal is rejected).
    """
    env_map: Mapping[str, str] = env if env is not None else os.environ
    warnings: list[SubstitutionWarning] = []

    def default_reader(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def transform(text_value: str) -> str:
        def replace_match(match: re.Match[str]) -> str:
            kind, key = match.group(1), match.group(2).strip()
            secret_named = bool(_SECRET_NAME_RE.search(key))
            if kind == "env":
                if key in env_map:
                    if secret_named:
                        warnings.append(SubstitutionWarning("secret_reference", key))
                    return str(env_map[key])
                warnings.append(SubstitutionWarning("missing_env", key))
                if secret_named:
                    warnings.append(SubstitutionWarning("secret_reference", key))
                return ""

            # file:
            if base_dir is None:
                raise ConfigSubstitutionError("no_base_dir")
            root = os.path.normpath(str(base_dir))
            candidate = os.path.normpath(os.path.join(root, key))
            if not _contained(candidate, root):
                raise ConfigSubstitutionError("path_outside_base_dir")
            reader = file_reader or default_reader
            try:
                content = reader(Path(candidate))
            except OSError:
                content = ""
            if content is None or content == "":
                warnings.append(SubstitutionWarning("missing_file", key))
                return ""
            return str(content)

        return _SUB_RE.sub(replace_match, text_value)

    return SubstitutionResult(_substitute_walk(value, transform), tuple(warnings))


# ===========================================================================
# Y1.24 - compaction config validation
# ===========================================================================


@dataclass(frozen=True)
class CompactionConfig:
    auto: bool = True
    keep_tokens: int = 4000
    buffer: float = 0.1
    strategy: str = "summary"       # "summary" stays the default
    per_model: Mapping[str, Any] = field(default_factory=dict)

    def resolve(self, model: str) -> CompactionConfig:
        """Resolve an exact model override, then a provider prefix, else base."""
        override = self.per_model.get(model)
        if override is None:
            provider = str(model).split("/", 1)[0]
            override = self.per_model.get(provider)
        if not override:
            return CompactionConfig(self.auto, self.keep_tokens, self.buffer, self.strategy, {})
        merged: dict[str, Any] = {
            "auto": self.auto, "keep_tokens": self.keep_tokens,
            "buffer": self.buffer, "strategy": self.strategy,
        }
        merged.update(override)
        return CompactionConfig(
            bool(merged["auto"]), int(merged["keep_tokens"]),
            float(merged["buffer"]), str(merged["strategy"]), {},
        )

    def to_dict(self) -> dict:
        return {
            "auto": self.auto, "keep_tokens": self.keep_tokens,
            "buffer": self.buffer, "strategy": self.strategy,
            "per_model": _copy_value(self.per_model),
        }


def validate_compaction_config(config: Mapping[str, Any] | None = None) -> CompactionConfig:
    """Validate compaction knobs with a local-summary default."""
    if config is None:
        return CompactionConfig()
    if not isinstance(config, Mapping):
        raise CompactionConfigError("bad_config")
    allowed = {"auto", "keep", "keep_tokens", "buffer", "strategy", "per_model", "overrides"}
    for key in config:
        if key not in allowed:
            raise CompactionConfigError("unknown_key", str(key))

    auto = config.get("auto", True)
    if not isinstance(auto, bool):
        raise CompactionConfigError("bad_auto")

    keep = config.get("keep_tokens", config.get("keep", 4000))
    if isinstance(keep, Mapping):
        keep = keep.get("tokens", 4000)
    if isinstance(keep, bool) or not isinstance(keep, int) or keep < 0:
        raise CompactionConfigError("bad_keep_tokens")

    buffer = config.get("buffer", 0.1)
    if isinstance(buffer, bool) or not isinstance(buffer, (int, float)) or not (0 <= buffer < 1):
        raise CompactionConfigError("bad_buffer")

    strategy = config.get("strategy", "summary")
    if strategy not in ("summary", "native"):
        raise CompactionConfigError("bad_strategy")

    raw_overrides = config.get("per_model", config.get("overrides", {})) or {}
    if not isinstance(raw_overrides, Mapping):
        raise CompactionConfigError("bad_per_model")
    per_model: dict[str, Any] = {}
    for model, override in raw_overrides.items():
        if not isinstance(override, Mapping):
            raise CompactionConfigError("bad_override")
        normalised: dict[str, Any] = {}
        for key, value in override.items():
            if key == "keep":
                normalised["keep_tokens"] = (
                    value.get("tokens", 4000) if isinstance(value, Mapping) else value
                )
            elif key in ("auto", "keep_tokens", "buffer", "strategy"):
                normalised[key] = value
            else:
                raise CompactionConfigError("unknown_key", str(key))
        validated = validate_compaction_config(normalised)
        per_model[str(model)] = {
            "auto": validated.auto, "keep_tokens": validated.keep_tokens,
            "buffer": validated.buffer, "strategy": validated.strategy,
        }
    return CompactionConfig(auto, keep, float(buffer), strategy, per_model)


# ===========================================================================
# Y1.30 - plugin enable/disable DSL (data only)
# ===========================================================================

_UNSAFE_CHARS = set(";&|$`(){}<>='\"\\\r\n")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.*/\-]*$")
_CODE_WORDS = {"eval", "exec", "import", "lambda", "script", "javascript"}


@dataclass(frozen=True)
class PluginSelection:
    tokens: tuple[str, ...]
    rules: tuple[tuple[str, str], ...]   # (enable|disable, value)
    builtin_ids: frozenset[str]

    def is_enabled(self, plugin_id: str) -> bool:
        if plugin_id in self.builtin_ids:
            return True
        best_specificity = -1
        best_index = -1
        enabled = False
        for index, (operation, value) in enumerate(self.rules):
            if not _rule_matches(value, plugin_id):
                continue
            specificity = _rule_specificity(value)
            if specificity > best_specificity or (specificity == best_specificity
                                                  and index > best_index):
                best_specificity = specificity
                best_index = index
                enabled = operation == "enable"
        return enabled

    def enabled(self, available: Sequence[str]) -> list[str]:
        return [plugin for plugin in available if self.is_enabled(plugin)]

    def to_dict(self) -> dict:
        return {
            "tokens": list(self.tokens),
            "rules": [{"operation": op, "value": val} for op, val in self.rules],
            "builtin_ids": sorted(self.builtin_ids),
        }


def _rule_specificity(value: str) -> int:
    if value == "*":
        return 1
    if value.endswith(".*"):
        return 2
    return 3


def _rule_matches(value: str, plugin_id: str) -> bool:
    if value == "*":
        return True
    if value.endswith(".*"):
        return plugin_id.startswith(value[:-1])
    return plugin_id == value


def parse_plugin_dsl(text: str, *, builtin_plugins: Sequence[str] = ()) -> PluginSelection:
    """Parse an ordered plugin DSL into a data-only selection.

    Rejects code, shell metacharacters and unsafe template/script tags. More
    specific rules beat general ones; at equal specificity the later entry
    wins (so a later enable re-enables a plugin). Built-in policy plugins are
    always enabled and cannot be disabled by a repository config.
    """
    if not isinstance(text, str):
        raise PluginDSLError("bad_dsl")
    tokens = [token for token in re.split(r"[,\s]+", text.strip()) if token]
    rules: list[tuple[str, str]] = []
    for token in tokens:
        if any(char in token for char in _UNSAFE_CHARS) or ".." in token:
            raise PluginDSLError("unsafe_token", token)
        raw = token[1:] if token.startswith("-") else token
        if not raw:
            raise PluginDSLError("unsafe_token", token)
        if raw not in ("*", ".*") and not _SAFE_TOKEN_RE.match(raw):
            raise PluginDSLError("unsafe_token", token)
        if raw.lower() in _CODE_WORDS:
            raise PluginDSLError("unsafe_token", token)
        rules.append(("disable" if token.startswith("-") else "enable", raw))
    return PluginSelection(
        tokens=tuple(tokens), rules=tuple(rules),
        builtin_ids=frozenset(builtin_plugins or ()),
    )


__all__ = [
    # constants
    "READ_MAX_LINES", "READ_MAX_BYTES", "MEDIA_MAX_BYTES", "GLOB_DEFAULT_LIMIT",
    "GREP_DEFAULT_LIMIT", "TOOL_DEFAULT_TIMEOUT_SECONDS",
    "SHELL_DEFAULT_TIMEOUT_SECONDS", "WEBFETCH_MAX_SECONDS",
    "MCP_DEFAULT_TIMEOUT_SECONDS", "FREE_WEBSEARCH_PROVIDERS", "SCOPE_PRIORITY",
    "PATCH_FAMILIES", "EDIT_TOOLS",
    # errors
    "ContractError", "ToolExposureError", "PatchParseError", "PagingError",
    "EditMatchError", "FormatterConfigError", "ShellDescriptorError",
    "ProviderPolicyError", "QuestionDescriptorError", "PermissionRuleError",
    "ConfigSubstitutionError", "CompactionConfigError", "PluginDSLError",
    # records
    "ToolProfile", "PatchHunk", "FilePatch", "PatchDescriptor", "PageResult",
    "MatchValidation", "FormatterSpec", "ShellDescriptor", "QuestionDescriptor",
    "PermissionRule", "EffectiveConfig", "SubstitutionWarning",
    "SubstitutionResult", "CompactionConfig", "PluginSelection",
    # functions
    "model_family", "tools_for_model", "parse_patch", "page", "glob_defaults",
    "grep_defaults", "resolve_search_options", "grep_permission_resource",
    "check_unique_match", "validate_formatter_config", "shell_descriptor",
    "select_websearch_provider", "validate_fetch_target", "webfetch_descriptor",
    "question_descriptor", "canonical_mcp_permission", "mcp_timeout",
    "mcp_permission_rule", "evaluate_rules", "tool_use_rule", "block_extension",
    "evaluate_permissions", "merge_config_layers", "effective_config",
    "config_search_order", "substitute_config", "validate_compaction_config",
    "parse_plugin_dsl",
]
