"""Y1.x P1/P2 config / tool / plugin backend contracts (stdlib only, additive).

Companion to :mod:`keel.mcp_contracts`, which already owns the 14 verified
``Y1.*`` P0 rows. This module covers the remaining 25 ``not_started`` rows of
``PLAN-INDEX.json`` (Addendum 4, section 2.1 "opencode"):

    Y1.1  Code Mode / execute tool
    Y1.10 skill loader advertised-list gate
    Y1.11 subagent semantics
    Y1.12 session utilities as tools
    Y1.13 worktree tools
    Y1.14 browser tool namespace
    Y1.15 experimental_image_generate
    Y1.18 managed config locations
    Y1.21 update modes
    Y1.22 snapshots toggle and watcher.ignore
    Y1.23 media.image and tool_output limits
    Y1.25 cache warming
    Y1.26 references
    Y1.27 skills config directories and URLs
    Y1.28 instructions files, globs and HTTP(S) URLs
    Y1.29 plugin management CLI
    Y1.31 three plugin surfaces
    Y1.32 location_idle_timeout
    Y1.33 experimental.todo flag
    Y1.34 model overrides and provider transport
    Y1.35 config_edit tool
    Y1.36 migrate / troubleshooting docs
    Y1.37 install script and release channels
    Y1.38 repo hygiene
    Y1.39 "Building on X" non-affiliation notice

Everything here is a *contract*: it validates, normalises, plans or selects
data and returns deterministic, structured results. No function fetches a URL,
spawns a process, reads a secret, imports a third-party package or writes a
file. Host-owned operations (permission checks, file reads, downloads, git
commands, page loads) are injected callables or are represented as descriptors
only. Strings from untrusted sources are treated as data and are escaped or
rejected, never interpreted.

URL guards also resolve DNS names so a name that points into loopback/private
space is denied. The resolver is an injected seam (``dns_resolver``); its
default is the only place in this module that may touch the network stack
(stdlib ``socket.getaddrinfo``). IP literals and structurally invalid or
non-allow-listed inputs take a no-I/O fast path and are never resolved, so
importing and testing this module stays offline. One-shot resolution cannot
defeat DNS rebinding: the host that actually fetches must re-validate at fetch
time. This module never fetches anything itself.
"""

from __future__ import annotations

import difflib
import html
import ipaddress
import math
import ntpath
import posixpath
import re
import shlex
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

# ---------------------------------------------------------------------------
# Errors: machine-readable codes, messages never carry secret values
# ---------------------------------------------------------------------------


class Y1ContractError(ValueError):
    """Base class for every Y1 backend contract failure."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(f"[{code}] {self.message}")


class CodeModeError(Y1ContractError):
    pass


class SkillGateError(Y1ContractError):
    pass


class SubagentError(Y1ContractError):
    pass


class SessionToolError(Y1ContractError):
    pass


class WorktreeError(Y1ContractError):
    pass


class BrowserContractError(Y1ContractError):
    pass


class ImageJobError(Y1ContractError):
    pass


class ManagedConfigError(Y1ContractError):
    pass


class UpdateConfigError(Y1ContractError):
    pass


class WatchConfigError(Y1ContractError):
    pass


class LimitConfigError(Y1ContractError):
    pass


class CacheConfigError(Y1ContractError):
    pass


class ReferenceError(Y1ContractError):
    pass


class SkillSourceError(Y1ContractError):
    pass


class InstructionSourceError(Y1ContractError):
    pass


class PluginCommandError(Y1ContractError):
    pass


class PluginManifestError(Y1ContractError):
    pass


class IdleConfigError(Y1ContractError):
    pass


class ExperimentalFlagError(Y1ContractError):
    pass


class ModelConfigError(Y1ContractError):
    pass


class ConfigEditError(Y1ContractError):
    pass


class DocsContractError(Y1ContractError):
    pass


class InstallPlanError(Y1ContractError):
    pass


class HygieneError(Y1ContractError):
    pass


class TrademarkError(Y1ContractError):
    pass


# ---------------------------------------------------------------------------
# Shared validation helpers (no I/O, no ambient environment reads)
# ---------------------------------------------------------------------------

_UNSAFE_RE = re.compile(
    r"<\s*/?\s*(?:script|iframe|object|embed|svg|img|style|link|meta|"
    r"form|base|template)\b|javascript\s*:|"
    r"on(?:error|load|click|mouseover|focus)\s*=",
    re.IGNORECASE,
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHELL_META_RE = re.compile(r"[;&|`$(){}\[\]<>\n\r]")
_SHELL_INJECTION_RE = re.compile(r"[;&|`$(){}\n\r]")
_ENV_VAR_RE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
_GIT_REF_BAD_RE = re.compile(r"\.\.|[\x00-\x1f ~^:?*\[\\]|^[-/]")


def _text(
    value: Any,
    field_name: str,
    *,
    max_len: int = 256,
    min_len: int = 1,
    error: type[Y1ContractError] = Y1ContractError,
) -> str:
    if not isinstance(value, str):
        raise error("invalid_type", f"{field_name} must be a string")
    result = value.strip()
    if len(result) < min_len:
        raise error("empty_value", f"{field_name} is empty")
    if len(result) > max_len:
        raise error("too_long", f"{field_name} exceeds {max_len} characters")
    if _CONTROL_RE.search(result):
        raise error("control_character", f"{field_name} has a control character")
    if _UNSAFE_RE.search(result):
        raise error("unsafe_tag", f"{field_name} contains an unsafe tag")
    return result


def _blob_text(
    value: Any,
    field_name: str,
    *,
    max_len: int = 10**8,
    error: type[Y1ContractError] = Y1ContractError,
) -> str:
    """Accept multi-line, markup-bearing blobs; reject only null bytes."""
    if not isinstance(value, str):
        raise error("invalid_type", f"{field_name} must be a string")
    if "\x00" in value:
        raise error("control_character", f"{field_name} contains a null byte")
    if not value.strip():
        raise error("empty_value", f"{field_name} is empty")
    if len(value) > max_len:
        raise error("too_long", f"{field_name} exceeds {max_len} characters")
    return value


def _safe_id(
    value: Any,
    field_name: str = "id",
    *,
    max_len: int = 128,
    error: type[Y1ContractError] = Y1ContractError,
) -> str:
    result = _text(value, field_name, max_len=max_len, error=error)
    lowered = result.lower()
    if (
        result in (".", "..")
        or ".." in result
        or "%2e%2e" in lowered
        or "/" in result
        or "\\" in result
    ):
        raise error("unsafe_id", f"{field_name} contains traversal syntax")
    if not _SAFE_ID_RE.fullmatch(result):
        raise error("unsafe_id", f"{field_name} is not a safe identifier")
    return result


def _relative_path(
    value: Any,
    field_name: str = "path",
    *,
    error: type[Y1ContractError] = Y1ContractError,
) -> str:
    raw = _text(value, field_name, max_len=2048, error=error)
    decoded = unquote(raw)
    if decoded != raw and (".." in decoded or "/" in decoded and raw.startswith("%")):
        raise error("encoded_path", f"{field_name} is percent-encoded")
    normal = decoded.replace("\\", "/")
    if normal.startswith("/") or re.match(r"^[A-Za-z]:", normal):
        raise error("absolute_path", f"{field_name} must be relative")
    parts = normal.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise error("unsafe_path", f"{field_name} contains a traversal segment")
    return "/".join(parts)


def _rooted(
    root: Any,
    relative: str,
    *,
    error: type[Y1ContractError] = Y1ContractError,
    windows: bool | None = None,
) -> str:
    root_text = _text(root, "root", max_len=2048, error=error)
    if windows is None:
        windows = bool(re.match(r"^[A-Za-z]:[\\/]", root_text))
    module = ntpath if windows else posixpath
    joined = module.normpath(module.join(root_text, relative.replace("/", module.sep)))
    if not _contained(joined, root_text, windows=windows):
        raise error("path_outside_root", "path escapes its configured root")
    return joined


def _contained(candidate: str, root: str, *, windows: bool | None = None) -> bool:
    if windows is None:
        windows = bool(re.match(r"^[A-Za-z]:[\\/]", root))
    sep = "\\" if windows else "/"
    norm_candidate = candidate.replace("/", sep).replace("\\", sep)
    norm_root = root.replace("/", sep).replace("\\", sep)
    norm_candidate = norm_candidate.rstrip(sep)
    norm_root = norm_root.rstrip(sep)
    if windows:
        norm_candidate = norm_candidate.lower()
        norm_root = norm_root.lower()
    return norm_candidate == norm_root or norm_candidate.startswith(norm_root + sep)


def _int(
    value: Any,
    field_name: str,
    *,
    minimum: int = 1,
    maximum: int = 10**9,
    error: type[Y1ContractError] = Y1ContractError,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise error("invalid_type", f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise error("out_of_range", f"{field_name} must be in [{minimum}, {maximum}]")
    return value


def _number(
    value: Any,
    field_name: str,
    *,
    minimum: float = 0.0,
    maximum: float = 10**9,
    error: type[Y1ContractError] = Y1ContractError,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise error("invalid_type", f"{field_name} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < minimum or result > maximum:
        raise error("out_of_range", f"{field_name} is out of range")
    return result


def _bool(value: Any, field_name: str, *, error: type[Y1ContractError] = Y1ContractError) -> bool:
    if not isinstance(value, bool):
        raise error("invalid_type", f"{field_name} must be a boolean")
    return value


def _mapping(value: Any, field_name: str, *, error: type[Y1ContractError] = Y1ContractError) -> Mapping:
    if not isinstance(value, Mapping):
        raise error("invalid_type", f"{field_name} must be a mapping")
    return value


def _sequence(value: Any, field_name: str, *, error: type[Y1ContractError] = Y1ContractError) -> Sequence:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise error("invalid_type", f"{field_name} must be a sequence")
    return value


def _canonical_ipv4_text(host: str) -> str | None:
    """Normalise inet_aton-style IPv4 spellings to a canonical dotted quad.

    Covers decimal integers (2130706433), hexadecimal (0x7f000001), octal
    (017700000001) and short forms (127.1, 0x7f.0.0.1), all of which accept
    loopback/private addresses while evading a literal ip_address() check.
    """
    if ":" in host:
        return None  # IPv6 is handled directly by ip_address().
    parts = host.split(".")
    if not parts or len(parts) > 4:
        return None
    numbers: list[int] = []
    for part in parts:
        if not part:
            return None
        try:
            if part.lower().startswith("0x"):
                number = int(part[2:], 16)
            elif len(part) > 1 and part.startswith("0"):
                number = int(part, 8)
            else:
                number = int(part, 10)
        except ValueError:
            return None
        if number < 0:
            return None
        numbers.append(number)
    count = len(numbers)
    limits = [255] * (count - 1) + [256 ** (5 - count) - 1]
    if any(number > limit for number, limit in zip(numbers, limits)):
        return None
    value = 0
    for index, number in enumerate(numbers):
        shift = 8 if index < count - 1 else 8 * (5 - count)
        value = (value << shift) | number
    return str(ipaddress.IPv4Address(value))


def _ip_address_or_none(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    candidate = host.strip("[]")
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        pass
    canonical = _canonical_ipv4_text(candidate.lower())
    if canonical is None:
        return None
    try:
        return ipaddress.ip_address(canonical)
    except ValueError:
        return None


# A resolver accepts a hostname and returns an iterable of literal IP address
# strings. The default seam is the only place in this module that may touch the
# network stack; callers and tests can inject a pure, offline resolver instead.
_DnsResolver = Callable[[str], Sequence[str]]


def _default_dns_resolver(host: str) -> Sequence[str]:
    """Resolve a DNS name via the stdlib; fail closed if resolution errors."""
    import socket  # local import: importing this module has no network effects

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError("dns resolution failed") from exc
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            addresses.append(str(sockaddr[0]))
    return addresses


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


def _reject_non_public_addresses(
    addresses: Sequence[Any],
    field_name: str,
    error: type[Y1ContractError],
) -> None:
    """Deny if any resolved address is non-public or not a literal address."""
    for candidate in addresses:
        address = _ip_address_or_none(str(candidate))
        if address is None or not _is_public_address(address):
            raise error("unsafe_host", f"{field_name} points at a non-public address")


def _url(
    value: Any,
    *,
    schemes: Sequence[str],
    allowed_hosts: Sequence[str] = (),
    field_name: str = "url",
    error: type[Y1ContractError] = Y1ContractError,
    dns_resolver: _DnsResolver | None = None,
):
    raw = _text(value, field_name, max_len=2048, error=error)
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        raise error("invalid_url", f"{field_name} has an invalid port") from exc
    if parts.scheme.lower() not in tuple(s.lower() for s in schemes):
        raise error("unsupported_scheme", f"{field_name} has an unsupported scheme")
    if parts.username is not None or parts.password is not None:
        raise error("credentials_in_url", f"{field_name} must not carry credentials")
    host = (parts.hostname or "").lower()
    if not host:
        raise error("missing_host", f"{field_name} has no host")
    address = _ip_address_or_none(host)
    if address is not None:
        # Fast path: a literal IP is already known; no DNS lookup is performed.
        _reject_non_public_addresses((str(address),), field_name, error)
    if allowed_hosts:
        allowed = tuple(str(h).lower() for h in allowed_hosts)
        matched = False
        for entry in allowed:
            if entry.startswith("*."):
                matched = matched or (host.endswith(entry[1:]) and host != entry[2:])
            else:
                matched = matched or host == entry
        if not matched:
            raise error("host_not_allowed", f"{field_name} host is not allow-listed")
    if port is not None and port not in (80, 443):
        raise error("invalid_port", f"{field_name} uses a disallowed port")
    if address is None:
        # DNS name: resolve through the injected seam, after all cheap
        # structural checks have already rejected unsafe/disallowed inputs.
        # Fail closed on a resolution error, an empty answer or any resolved
        # address that is not public. The host must re-check at fetch time to
        # defeat DNS rebinding; this contract never fetches.
        resolver = dns_resolver if dns_resolver is not None else _default_dns_resolver
        try:
            resolved = tuple(resolver(host))
        except Exception as exc:  # noqa: BLE001 - any resolver failure is fatal
            raise error("unsafe_host", f"{field_name} host could not be resolved") from exc
        if not resolved:
            raise error("unsafe_host", f"{field_name} host could not be resolved")
        _reject_non_public_addresses(resolved, field_name, error)
    return parts


@dataclass(frozen=True)
class _Descriptor:
    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# Y1.1 - Code Mode / execute tool
# ===========================================================================

CODE_MODE_ALLOWED_GLOBALS: tuple[str, ...] = ("fetch", "tools")
CODE_MODE_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    r"\b(?:import|from)\s+[A-Za-z_.]",
    r"\b__import__\s*\(",
    r"\b(?:eval|exec|compile|open|input)\s*\(",
    r"\brequire\s*\(",
    r"\b(?:setTimeout|setInterval|requestAnimationFrame)\s*\(",
    r"\b(?:sleep|time\.sleep)\s*\(",
    r"\b(?:os|sys|subprocess|pathlib|shutil|socket)\b",
    r"\b(?:globals|locals|vars|getattr)\s*\(",
    r"\bprocess\s*\.",
    r"\bfs\s*\.",
    r"\b(?:while\s+True|for\s*\(;;)",
)
_CODE_MODE_FORBIDDEN_RE = tuple(re.compile(p, re.IGNORECASE) for p in CODE_MODE_FORBIDDEN_PATTERNS)


@dataclass(frozen=True)
class CodeModeDescriptor(_Descriptor):
    available: bool
    fallback: str
    tools: tuple[str, ...]
    fetch: bool
    globals: tuple[str, ...] = CODE_MODE_ALLOWED_GLOBALS


def code_mode_server_switches(config: Any) -> dict[str, bool]:
    """Normalise per-MCP-server ``codemode`` switches (default on)."""
    result: dict[str, bool] = {}
    for key, value in _mapping(config, "codemode", error=CodeModeError).items():
        server = _safe_id(str(key), "server", error=CodeModeError)
        result[server] = _bool(value, f"codemode.{server}", error=CodeModeError)
    return result


def validate_code_script(script: Any, *, max_chars: int = 8192, max_lines: int = 200) -> str:
    """Static gate for the micro-sandbox. Never executes the script."""
    result = _blob_text(script, "script", max_len=max_chars, error=CodeModeError)
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", result):
        raise CodeModeError("control_character", "script has an illegal control character")
    if len(result.splitlines()) > max_lines:
        raise CodeModeError("too_many_lines", f"script exceeds {max_lines} lines")
    if _UNSAFE_RE.search(result):
        raise CodeModeError("unsafe_tag", "script contains an unsafe tag")
    for pattern in _CODE_MODE_FORBIDDEN_RE:
        match = pattern.search(result)
        if match:
            raise CodeModeError("unsafe_token", f"forbidden token {match.group(0)!r}")
    return result


def code_mode_descriptor(
    tools: Sequence[str],
    *,
    enabled: bool = True,
    denied: bool = False,
    server_switches: Mapping[str, bool] | None = None,
) -> CodeModeDescriptor:
    """Build the Code Mode catalog; a denials falls back to listing tools."""
    switches = dict(server_switches or {})
    exposed: list[str] = []
    for tool in _sequence(tools, "tools", error=CodeModeError):
        name = _text(tool, "tool", max_len=256, error=CodeModeError)
        server = None
        if name.startswith("mcp__"):
            parts = name.split("__")
            if len(parts) >= 3:
                server = parts[1]
        elif name.startswith("mcp."):
            parts = name.split(".")
            if len(parts) >= 3:
                server = parts[1]
        if server is not None and switches.get(server, True) is False:
            continue
        exposed.append(name)
    available = bool(enabled) and not bool(denied)
    return CodeModeDescriptor(
        available=available,
        fallback="" if available else "tool_list",
        tools=tuple(exposed) if available else (),
        fetch=available,
    )


def authorize_code_mode_call(
    tool: str,
    descriptor: CodeModeDescriptor,
    permission_gate: Callable[[str, str], Any],
) -> dict:
    """Every nested tool call still passes through the injected permission gate."""
    name = _text(tool, "tool", error=CodeModeError)
    if not descriptor.available:
        raise CodeModeError("code_mode_denied", "fall back to the direct tool list")
    if name not in descriptor.tools:
        raise CodeModeError("tool_not_exposed", "tool is not in the Code Mode catalog")
    if permission_gate is None:
        raise CodeModeError("permission_gate_required")
    decision = permission_gate("execute", name)
    allowed = decision is True
    if isinstance(decision, Mapping):
        allowed = str(decision.get("effect", decision.get("decision", ""))).lower() == "allow"
    if not allowed:
        raise CodeModeError("nested_permission_denied", f"nested call to {name} was denied")
    return {"tool": name, "gate": "allow", "executed": False}


# ===========================================================================
# Y1.10 - skill loader advertised-list gate
# ===========================================================================


@dataclass(frozen=True)
class SkillLoadDecision(_Descriptor):
    skill_id: str
    allowed: bool
    reason: str
    matched_by: str = ""


def can_load_skill(
    skill_id: Any,
    advertised: Sequence[str] = (),
    user_named: Sequence[str] = (),
) -> SkillLoadDecision:
    """A skill loads only when advertised or explicitly named by the user."""
    candidate = _safe_id(skill_id, "skill_id", error=SkillGateError)
    ads = tuple(
        _safe_id(item, "advertised_skill", error=SkillGateError)
        for item in _sequence(advertised, "advertised", error=SkillGateError)
    )
    named = tuple(
        _safe_id(item, "user_named_skill", error=SkillGateError)
        for item in _sequence(user_named, "user_named", error=SkillGateError)
    )
    if candidate in ads:
        return SkillLoadDecision(candidate, True, "advertised", "advertised")
    if candidate in named:
        return SkillLoadDecision(candidate, True, "user_named", "user")
    return SkillLoadDecision(candidate, False, "not_advertised")


def require_skill(
    skill_id: Any,
    advertised: Sequence[str] = (),
    user_named: Sequence[str] = (),
) -> SkillLoadDecision:
    decision = can_load_skill(skill_id, advertised, user_named)
    if not decision.allowed:
        raise SkillGateError("not_advertised", "skill is neither advertised nor user-named")
    return decision


# ===========================================================================
# Y1.11 - subagent semantics
# ===========================================================================

DEFAULT_SUBAGENT_DEPTH = 1
MAX_SUBAGENT_DEPTH = 8
_SUBAGENT_NAMESPACE = uuid.UUID("6f3c8a4e-0b11-4d6c-9f20-3b5a7e1c8d42")


def validate_subagent_depth(value: Any, *, maximum: int = MAX_SUBAGENT_DEPTH) -> int:
    return _int(value, "subagent_depth", minimum=0, maximum=maximum, error=SubagentError)


@dataclass(frozen=True)
class SubagentLaunch(_Descriptor):
    session_id: str
    parent_session_id: str
    background: bool
    depth: int
    notifications: tuple[str, ...] = ("idle", "round")


def spawn_subagent(
    parent_session_id: Any,
    task: Any,
    *,
    depth: int = 0,
    config_depth: int = DEFAULT_SUBAGENT_DEPTH,
    session_id: str | None = None,
) -> SubagentLaunch:
    parent = _safe_id(parent_session_id, "parent_session_id", error=SubagentError)
    description = _text(task, "task", max_len=4096, error=SubagentError)
    child_depth = validate_subagent_depth(depth)
    limit = validate_subagent_depth(config_depth)
    if child_depth >= limit:
        raise SubagentError("depth_exceeded", f"maximum nesting depth is {limit}")
    sid = session_id or "ses_" + uuid.uuid5(
        _SUBAGENT_NAMESPACE, f"{parent}|{child_depth}|{description}"
    ).hex[:24]
    sid = _safe_id(sid, "session_id", error=SubagentError)
    return SubagentLaunch(sid, parent, True, child_depth)


def subagent_notification(launch: SubagentLaunch, event: str, *, round_number: int = 0) -> dict:
    name = _text(event, "event", error=SubagentError)
    if name not in launch.notifications:
        raise SubagentError("unsupported_notification", f"no notification for {name}")
    number = _int(round_number, "round_number", minimum=0, maximum=10**6, error=SubagentError)
    if name == "idle" and number != 0:
        raise SubagentError("invalid_idle_round", "idle notifications have no round number")
    if name == "round" and number < 1:
        raise SubagentError("invalid_round_number", "round notifications start at round 1")
    return {
        "type": f"subagent.{name}",
        "sessionID": launch.session_id,
        "parentSessionID": launch.parent_session_id,
        "round": number,
        "background": True,
    }


def subagent_followup(
    launch: SubagentLaunch,
    known_sessions: Mapping[str, SubagentLaunch],
    message: Any,
) -> dict:
    """A follow-up continues the same child; it never spawns a new one."""
    known = _mapping(known_sessions, "known_sessions", error=SubagentError)
    if launch.session_id not in known:
        raise SubagentError("unknown_child_session", "child session is not registered")
    text = _text(message, "message", max_len=4096, error=SubagentError)
    return {
        "sessionID": launch.session_id,
        "continue": True,
        "background": True,
        "message": text,
    }


# ===========================================================================
# Y1.12 - session utilities as tools
# ===========================================================================

SESSION_UTILITY_TOOLS: tuple[str, ...] = ("session_rename", "session_move")


def session_rename_tool(title: Any, *, session_id: str | None = None) -> dict:
    result = _text(title, "title", max_len=120, error=SessionToolError)
    sid = _safe_id(session_id, "session_id", error=SessionToolError) if session_id else None
    return {
        "tool": "session_rename",
        "arguments": {"title": result, "sessionID": sid},
        "applies_immediately": True,
    }


@dataclass(frozen=True)
class SessionMovePlan(_Descriptor):
    directory: str
    effective_at: str
    applied_now: bool
    tool: str = "session_move"


def session_move_tool(
    directory: Any,
    *,
    allowed_root: Any,
    current_directory: Any | None = None,
) -> SessionMovePlan:
    relative = _relative_path(directory, "directory", error=SessionToolError)
    target = _rooted(allowed_root, relative, error=SessionToolError)
    if current_directory is not None:
        _relative_path(current_directory, "current_directory", error=SessionToolError)
    return SessionMovePlan(target, "safe_boundary", False)


# ===========================================================================
# Y1.13 - worktree tools
# ===========================================================================

WORKTREE_BUILTIN_STRATEGIES: tuple[str, ...] = ("git", "local")
WORKTREE_TOOLS: tuple[str, ...] = ("worktree_create", "worktree_list", "worktree_remove")


def worktree_strategy_registry(plugins: Mapping[str, Callable[..., Any]] | None = None) -> dict[str, str]:
    registry = {name: "builtin" for name in WORKTREE_BUILTIN_STRATEGIES}
    for name, factory in _mapping(plugins or {}, "plugins", error=WorktreeError).items():
        safe = _safe_id(str(name), "strategy", error=WorktreeError)
        if not callable(factory):
            raise WorktreeError("invalid_strategy_factory", f"{safe} is not callable")
        registry[safe] = "plugin"
    return registry


@dataclass(frozen=True)
class WorktreePlan(_Descriptor):
    action: str
    name: str
    directory: str
    strategy: str
    permission: str
    permission_resource: str
    force: bool
    discard_changes: bool


def worktree_create(
    name: Any,
    parent_directory: Any,
    *,
    allowed_root: Any,
    strategy: str = "git",
    strategies: Mapping[str, Any] | None = None,
) -> WorktreePlan:
    safe_name = _safe_id(name, "name", error=WorktreeError)
    relative = _relative_path(parent_directory, "parent_directory", error=WorktreeError)
    target = _rooted(allowed_root, relative, error=WorktreeError)
    registry = worktree_strategy_registry(strategies)
    chosen = _safe_id(strategy, "strategy", error=WorktreeError)
    if chosen not in registry:
        raise WorktreeError("unknown_strategy", f"{chosen} is not registered")
    return WorktreePlan(
        "create", safe_name, target, chosen, "edit", f"worktree:{safe_name}", False, False
    )


def worktree_list(*, root: Any | None = None) -> dict:
    validated = _text(root, "root", max_len=2048, error=WorktreeError) if root is not None else None
    return {"tool": "worktree_list", "root": validated, "executes": False}


def worktree_remove(
    name: Any,
    *,
    dirty: bool = False,
    force: bool = False,
    permission_check: Callable[[str, str], bool] | None = None,
) -> WorktreePlan:
    safe_name = _safe_id(name, "name", error=WorktreeError)
    is_dirty = _bool(dirty, "dirty", error=WorktreeError)
    use_force = _bool(force, "force", error=WorktreeError)
    if permission_check is not None and permission_check("edit", f"worktree:{safe_name}") is not True:
        raise WorktreeError("permission_denied", "edit permission is required")
    if is_dirty and not use_force:
        raise WorktreeError("force_required", "dirty worktrees require force=True")
    return WorktreePlan(
        "remove", safe_name, "", "", "edit", f"worktree:{safe_name}", use_force, is_dirty and use_force
    )


# ===========================================================================
# Y1.14 - browser tool namespace
# ===========================================================================

BROWSER_TOOLS: tuple[str, ...] = (
    "browser.tabs.open",
    "browser.tabs.list",
    "browser.tabs.close",
    "browser.snapshot",
    "browser.search",
    "browser.click",
    "browser.input",
    "browser.screenshot",
    "browser.file_transfer",
    "browser.console",
    "browser.network",
    "browser.performance",
    "browser.heap",
    "browser.lighthouse",
)
BROWSER_FILE_TRANSFER_MAX_BYTES = 5 * 1024 * 1024


def browser_tool_catalog(
    *,
    denied: Sequence[str] = (),
    allowed: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """A deny rule for ``browser`` or ``browser.*`` removes the whole catalog."""
    denials = tuple(_text(d, "deny_rule", error=BrowserContractError) for d in denied)
    if "browser" in denials or "browser.*" in denials:
        return ()
    result = [
        tool
        for tool in BROWSER_TOOLS
        if not any(d == tool or d == "*" for d in denials)
    ]
    if allowed is not None:
        selectors = tuple(_text(a, "allow_rule", error=BrowserContractError) for a in allowed)
        result = [
            tool
            for tool in result
            if tool in selectors or any(s.endswith(".*") and tool.startswith(s[:-1]) for s in selectors)
        ]
    return tuple(result)


def validate_browser_url(
    url: Any,
    *,
    allowed_hosts: Sequence[str] = (),
    dns_resolver: _DnsResolver | None = None,
) -> str:
    parts = _url(
        url,
        schemes=("http", "https"),
        allowed_hosts=allowed_hosts,
        field_name="browser_url",
        error=BrowserContractError,
        dns_resolver=dns_resolver,
    )
    return parts.geturl()


def browser_page_content(text: Any, *, source_url: Any = "") -> dict:
    """Page text is data: escape it and label it untrusted for the model."""
    raw = _blob_text(text, "page_text", error=BrowserContractError)
    source = _text(source_url, "source_url", max_len=2048, error=BrowserContractError) if source_url else ""
    return {
        "text": html.escape(raw),
        "trust": "untrusted",
        "source": source,
        "instructions": [],
    }


def validate_browser_transfer_size(size_bytes: Any) -> int:
    size = _int(
        size_bytes, "size_bytes", minimum=0, maximum=BROWSER_FILE_TRANSFER_MAX_BYTES,
        error=BrowserContractError,
    )
    return size


def lighthouse_descriptor(*, consent: bool = False, license_ack: bool = False) -> dict:
    if not _bool(consent, "consent", error=BrowserContractError):
        raise BrowserContractError("lighthouse_consent_required", "audits require explicit consent")
    if not _bool(license_ack, "license_ack", error=BrowserContractError):
        raise BrowserContractError("license_ack_required", "verify the Apache-2.0 licence first")
    return {"tool": "browser.lighthouse", "license": "Apache-2.0", "background": True, "consent": True}


# ===========================================================================
# Y1.15 - experimental_image_generate
# ===========================================================================

LOCAL_IMAGE_PROVIDERS: tuple[str, ...] = ("local-diffusion", "local-sdxl")
IMAGE_SAVE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")
MAX_REFERENCE_IMAGES = 8


@dataclass(frozen=True)
class ImageJobDescriptor(_Descriptor):
    available: bool
    reason: str
    provider: str
    save_path: str
    references: tuple[str, ...]
    background: bool
    notification: str


def image_generate_descriptor(
    *,
    providers: Sequence[str] = (),
    save_path: Any,
    allowed_root: Any,
    references: Sequence[str] = (),
) -> ImageJobDescriptor:
    available_providers = tuple(
        _safe_id(str(p), "provider", error=ImageJobError) for p in providers
    )
    local = tuple(p for p in available_providers if p in LOCAL_IMAGE_PROVIDERS)
    if not local:
        return ImageJobDescriptor(False, "no_local_provider", "", "", (), True, "")
    relative = _relative_path(save_path, "save_path", error=ImageJobError)
    if not relative.lower().endswith(IMAGE_SAVE_EXTENSIONS):
        raise ImageJobError("unsupported_extension", "save path needs an image extension")
    target = _rooted(allowed_root, relative, error=ImageJobError)
    refs = tuple(
        _rooted(allowed_root, _relative_path(r, "reference", error=ImageJobError), error=ImageJobError)
        for r in _sequence(references, "references", error=ImageJobError)
    )
    if len(refs) > MAX_REFERENCE_IMAGES:
        raise ImageJobError("too_many_references", f"at most {MAX_REFERENCE_IMAGES} references")
    return ImageJobDescriptor(True, "", local[0], target, refs, True, "on_completion")


# ===========================================================================
# Y1.18 - managed config locations
# ===========================================================================

MANAGED_PRECEDENCE: tuple[str, ...] = ("default", "user", "project", "managed")
MANAGED_LOCATIONS: Mapping[str, tuple[tuple[str, str], ...]] = {
    "linux": (("/etc/opencode", "json"),),
    "darwin": (
        ("/Library/Application Support/opencode", "json"),
        ("/Library/Managed Preferences/com.opencode.plist", "plist"),
    ),
    "win32": (("%ProgramData%\\opencode", "json"), ("%ProgramData%\\opencode\\policy.admx", "admx")),
}


@dataclass(frozen=True)
class ManagedLocation(_Descriptor):
    path: str
    kind: str
    os_name: str


def _normalise_os(os_name: Any) -> str:
    name = _text(os_name, "os_name", max_len=32, error=ManagedConfigError).lower()
    aliases = {"windows": "win32", "nt": "win32", "macos": "darwin", "mac": "darwin"}
    name = aliases.get(name, name)
    if name not in MANAGED_LOCATIONS:
        raise ManagedConfigError("unsupported_os", f"no managed paths for {name}")
    return name


def managed_config_locations(os_name: Any, *, env: Mapping[str, str] | None = None) -> tuple[ManagedLocation, ...]:
    name = _normalise_os(os_name)
    variables = _mapping(env or {}, "env", error=ManagedConfigError)
    result: list[ManagedLocation] = []
    for template, kind in MANAGED_LOCATIONS[name]:
        def expand(match: re.Match) -> str:
            key = match.group(1)
            if key not in variables:
                raise ManagedConfigError("managed_env_missing", f"no value supplied for {key}")
            value = _text(variables[key], key, max_len=1024, error=ManagedConfigError)
            if ".." in value or "/" in value and "\\" not in template:
                raise ManagedConfigError("unsafe_env_path", f"{key} has an unsafe value")
            return value

        path = _ENV_VAR_RE.sub(expand, template)
        if ".." in path.replace("\\", "/").split("/"):
            raise ManagedConfigError("unsafe_managed_path", "managed path contains traversal")
        result.append(ManagedLocation(path, kind, name))
    return tuple(result)


def managed_value(layers: Mapping[str, Any]) -> tuple[Any, str]:
    """Managed settings have the highest precedence; report provenance."""
    values = _mapping(layers, "layers", error=ManagedConfigError)
    for scope in reversed(MANAGED_PRECEDENCE):
        if scope in values:
            return values[scope], scope
    raise ManagedConfigError("no_config_value", "no layer provided a value")


# ===========================================================================
# Y1.21 - update modes
# ===========================================================================

UPDATE_MODES: tuple[str, ...] = ("disable", "notify", "auto")


@dataclass(frozen=True)
class UpdatePlan(_Descriptor):
    mode: str
    scope: str
    install: bool
    notify: bool
    restart: bool


def resolve_update_mode(value: Any, *, scope: str = "global") -> tuple[str, bool]:
    """Project-scope values are ignored; only global config can change updates."""
    chosen_scope = _text(scope, "scope", max_len=32, error=UpdateConfigError)
    mode = _text(value, "update", max_len=32, error=UpdateConfigError)
    if mode not in UPDATE_MODES:
        raise UpdateConfigError("invalid_update_mode", f"unknown update mode {mode!r}")
    if chosen_scope != "global":
        return "notify", True
    return mode, False


def update_plan(value: Any, *, scope: str = "global", server_running: bool = False) -> UpdatePlan:
    mode, ignored = resolve_update_mode(value, scope=scope)
    running = _bool(server_running, "server_running", error=UpdateConfigError)
    return UpdatePlan(
        mode=mode,
        scope="ignored_project_value" if ignored else "global",
        install=mode == "auto",
        notify=mode in ("notify", "auto"),
        # Auto-install never restarts a running server (and plans never restart).
        restart=False,
    )


# ===========================================================================
# Y1.22 - snapshots toggle and watcher.ignore
# ===========================================================================

import fnmatch  # noqa: E402  (kept near its only consumer)


def snapshots_enabled(config: Any = None) -> bool:
    if config is None:
        return True
    values = _mapping(config, "config", error=WatchConfigError)
    if "snapshots" not in values:
        return True
    return _bool(values["snapshots"], "snapshots", error=WatchConfigError)


def validate_watcher_ignore(patterns: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for pattern in _sequence(patterns, "watcher.ignore", error=WatchConfigError):
        name = _text(pattern, "watcher.ignore entry", max_len=256, error=WatchConfigError)
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/"):
            raise WatchConfigError("unsafe_ignore_pattern", "ignore globs must be relative")
        if len(result) >= 200:
            raise WatchConfigError("too_many_patterns", "at most 200 ignore globs")
        result.append(name)
    return tuple(result)


def watcher_ignored(path: Any, patterns: Sequence[str]) -> bool:
    relative = _relative_path(path, "path", error=WatchConfigError)
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in validate_watcher_ignore(patterns))


# ===========================================================================
# Y1.23 - media.image and tool_output limits
# ===========================================================================

IMAGE_MAX_DIMENSION = 2000
IMAGE_MAX_BASE64_BYTES = 5 * 1024 * 1024
TOOL_OUTPUT_MAX_LINES = 2000
TOOL_OUTPUT_MAX_BYTES = 50 * 1024


@dataclass(frozen=True)
class MediaLimits(_Descriptor):
    max_width: int
    max_height: int
    max_base64_bytes: int


@dataclass(frozen=True)
class ToolOutputLimits(_Descriptor):
    max_lines: int
    max_bytes: int


@dataclass(frozen=True)
class ToolOutputChunk(_Descriptor):
    text: str
    truncated: bool
    omitted_lines: int
    omitted_bytes: int
    marker: str


def resolve_media_limits(config: Mapping[str, Any] | None = None) -> MediaLimits:
    values = dict(_mapping(config or {}, "media.image", error=LimitConfigError))
    return MediaLimits(
        _int(values.get("maxWidth", values.get("max_width", IMAGE_MAX_DIMENSION)), "maxWidth", error=LimitConfigError),
        _int(values.get("maxHeight", values.get("max_height", IMAGE_MAX_DIMENSION)), "maxHeight", error=LimitConfigError),
        _int(
            values.get("maxBase64Bytes", values.get("max_base64_bytes", IMAGE_MAX_BASE64_BYTES)),
            "maxBase64Bytes",
            error=LimitConfigError,
        ),
    )


def resolve_tool_output_limits(config: Mapping[str, Any] | None = None) -> ToolOutputLimits:
    values = dict(_mapping(config or {}, "tool_output", error=LimitConfigError))
    return ToolOutputLimits(
        _int(values.get("maxLines", values.get("max_lines", TOOL_OUTPUT_MAX_LINES)), "maxLines", error=LimitConfigError),
        _int(values.get("maxBytes", values.get("max_bytes", TOOL_OUTPUT_MAX_BYTES)), "maxBytes", error=LimitConfigError),
    )


def resize_dimensions(width: Any, height: Any, limits: MediaLimits | None = None) -> tuple[int, int, bool]:
    effective = limits or resolve_media_limits()
    w = _int(width, "width", error=LimitConfigError)
    h = _int(height, "height", error=LimitConfigError)
    scale = min(1.0, effective.max_width / w, effective.max_height / h)
    return max(1, int(math.floor(w * scale))), max(1, int(math.floor(h * scale))), scale < 1.0


def validate_base64_size(size_bytes: Any, limits: MediaLimits | None = None) -> int:
    effective = limits or resolve_media_limits()
    return _int(
        size_bytes, "base64_bytes", minimum=0, maximum=effective.max_base64_bytes,
        error=LimitConfigError,
    )


def clip_tool_output(text: Any, limits: ToolOutputLimits | None = None) -> ToolOutputChunk:
    effective = limits or resolve_tool_output_limits()
    raw = _blob_text(text, "output", error=LimitConfigError)
    lines = raw.splitlines(keepends=True)
    kept: list[str] = []
    used = 0
    for line in lines:
        size = len(line.encode("utf-8"))
        if len(kept) >= effective.max_lines or used + size > effective.max_bytes:
            break
        kept.append(line)
        used += size
    omitted_lines = max(0, len(lines) - len(kept))
    omitted_bytes = max(0, len(raw.encode("utf-8")) - used)
    truncated = omitted_lines > 0 or omitted_bytes > 0
    marker = (
        ""
        if not truncated
        else f"[output truncated omitted_lines={omitted_lines} omitted_bytes={omitted_bytes}]"
    )
    return ToolOutputChunk("".join(kept), truncated, omitted_lines, omitted_bytes, marker)


# ===========================================================================
# Y1.25 - cache warming
# ===========================================================================


@dataclass(frozen=True)
class CachePolicy(_Descriptor):
    ttl_seconds: int = 3600
    warming: bool = False
    keep_alive: str = ""
    prewarm_prefix: bool = False


def cache_policy(config: Mapping[str, Any] | None = None) -> CachePolicy:
    values = dict(_mapping(config or {}, "cache", error=CacheConfigError))
    warming = _bool(values.get("warming", False), "cache.warming", error=CacheConfigError)
    ttl = _int(values.get("ttl", 3600), "cache.ttl", minimum=1, maximum=86400, error=CacheConfigError)
    keep_alive = _text(values["keep_alive"], "keep_alive", max_len=64, error=CacheConfigError) if "keep_alive" in values else ""
    prewarm = _bool(values.get("prewarm_prefix", False), "prewarm_prefix", error=CacheConfigError)
    return CachePolicy(ttl, warming, keep_alive, prewarm)


def warm_due(policy: CachePolicy, *, last_warm: float, now: float) -> bool:
    if not policy.warming:
        return False
    previous = _number(last_warm, "last_warm", error=CacheConfigError)
    current = _number(now, "now", error=CacheConfigError)
    return current - previous >= policy.ttl_seconds


def warming_plan(
    policy: CachePolicy,
    *,
    remote: bool = False,
    opt_in: bool = False,
    cost_shown: bool = False,
) -> dict:
    """Local warming is free; remote warming needs explicit opt-in and cost."""
    if not policy.warming:
        return {"enabled": False, "actions": (), "cost_shown": False}
    if remote:
        if not _bool(opt_in, "opt_in", error=CacheConfigError):
            raise CacheConfigError("remote_opt_in_required", "remote warming needs user opt-in")
        if not _bool(cost_shown, "cost_shown", error=CacheConfigError):
            raise CacheConfigError("cost_disclosure_required", "show estimated cost before warming")
    actions = ["keep_alive"] if policy.keep_alive else []
    if policy.prewarm_prefix:
        actions.append("prewarm_system_prompt_prefix")
    return {
        "enabled": True,
        "mode": "remote" if remote else "local",
        "actions": tuple(actions),
        "cost_shown": bool(cost_shown) and remote,
        "transient_request": remote,
    }


# ===========================================================================
# Y1.26 - references
# ===========================================================================


@dataclass(frozen=True)
class Reference(_Descriptor):
    name: str
    description: str
    path: str
    repository: str
    branch: str
    cache_path: str
    read_only: bool = True


def parse_references(
    config: Any,
    *,
    allowed_root: Any,
    cache_root: Any,
) -> tuple[Reference, ...]:
    result: list[Reference] = []
    for key, spec in _mapping(config, "references", error=ReferenceError).items():
        name = _safe_id(str(key), "reference name", error=ReferenceError)
        values = dict(_mapping(spec, f"references.{name}", error=ReferenceError))
        description = _text(values.get("description", ""), "description", max_len=280, error=ReferenceError)
        has_path = "path" in values
        has_repo = "repository" in values
        if has_path == has_repo:
            raise ReferenceError("exactly_one_source", f"{name} needs path or repository")
        path = ""
        repository = ""
        branch = ""
        if has_path:
            path = _rooted(allowed_root, _relative_path(values["path"], "path", error=ReferenceError), error=ReferenceError)
        else:
            repository = _text(values["repository"], "repository", max_len=256, error=ReferenceError)
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
                raise ReferenceError("invalid_repository", "repository must be owner/name")
            if "branch" in values:
                branch = _safe_id(values["branch"], "branch", error=ReferenceError)
        cache = _rooted(cache_root, name, error=ReferenceError)
        result.append(Reference(name, description, path, repository, branch, cache))
    return tuple(result)


def reference_by_name(name: Any, references: Sequence[Reference]) -> Reference:
    wanted = _safe_id(name, "reference name", error=ReferenceError)
    for reference in references:
        if reference.name == wanted:
            return reference
    raise ReferenceError("unknown_reference", f"no reference named {wanted}")


def search_references(query: Any, references: Sequence[Reference]) -> tuple[Reference, ...]:
    needle = _text(query, "query", max_len=200, error=ReferenceError).lower()
    return tuple(
        sorted(
            (r for r in references if needle in r.name.lower() or needle in r.description.lower()),
            key=lambda r: r.name,
        )
    )


# ===========================================================================
# Y1.27 - skills config directories and URLs
# ===========================================================================


@dataclass(frozen=True)
class SkillSource(_Descriptor):
    kind: str
    value: str
    host: str
    discovery_url: str
    requires_signature: bool


def parse_skill_sources(
    sources: Sequence[Any],
    *,
    allowed_hosts: Sequence[str] = (),
    dns_resolver: _DnsResolver | None = None,
) -> tuple[SkillSource, ...]:
    result: list[SkillSource] = []
    for item in _sequence(sources, "skills", error=SkillSourceError):
        if isinstance(item, Mapping):
            value = item.get("url") or item.get("path") or item.get("directory")
            is_url = "url" in item
        else:
            value = item
            is_url = isinstance(value, str) and value.lower().startswith(("http://", "https://"))
        if is_url:
            parts = _url(
                value,
                schemes=("https",),
                allowed_hosts=allowed_hosts,
                field_name="skills URL",
                error=SkillSourceError,
                dns_resolver=dns_resolver,
            )
            host = (parts.hostname or "").lower()
            discovery = f"https://{host}/.well-known/skills/"
            result.append(SkillSource("url", parts.geturl(), host, discovery, True))
        else:
            relative = _relative_path(value, "skills directory", error=SkillSourceError)
            result.append(SkillSource("directory", relative, "", "", False))
    return tuple(result)


def skill_pack_signature_check(
    manifest: Mapping[str, Any],
    *,
    verifier: Callable[[str, str, str, str], bool] | None = None,
) -> dict:
    """Check a skill-pack signature; never claim an unperformed verification.

    This contract has no bundled cryptographic provider and must not fetch
    keys from the network. The host may inject a ``verifier`` callable taking
    (algorithm, signature, material, key) and returning a boolean; only then
    is ``verified`` allowed to be True. Without one the result is explicitly
    unverified and fail-closed.
    """
    values = dict(_mapping(manifest, "manifest", error=SkillSourceError))
    signature = values.get("signature", "")
    algorithm = values.get("algorithm", "")
    if (
        not isinstance(signature, str)
        or not isinstance(algorithm, str)
        or not signature
        or algorithm.lower() not in ("ed25519", "ecdsa-sha256")
    ):
        raise SkillSourceError("signature_check_failed", "signed pack requires a supported signature")
    _text(signature, "signature", max_len=4096, error=SkillSourceError)
    result = {
        "verified": False,
        "algorithm": algorithm.lower(),
        "network_used": False,
        "verification_performed": False,
    }
    if verifier is None:
        result["reason"] = "verification_unavailable"
        return result
    if not callable(verifier):
        raise SkillSourceError("signature_check_failed", "verifier must be callable")
    material = values.get("material", values.get("payload", ""))
    key = values.get("key", values.get("public_key", ""))
    try:
        verified = bool(verifier(algorithm.lower(), signature, str(material), str(key)))
    except Exception as exc:  # noqa: BLE001
        raise SkillSourceError("signature_check_failed", f"verifier error: {type(exc).__name__}") from exc
    result["verified"] = verified
    result["verification_performed"] = True
    if not verified:
        result["reason"] = "signature_mismatch"
    return result


# ===========================================================================
# Y1.28 - instructions files, globs and HTTP(S) URLs
# ===========================================================================


@dataclass(frozen=True)
class InstructionSource(_Descriptor):
    kind: str
    value: str
    tainted: bool


def parse_instruction_sources(
    items: Sequence[Any],
    *,
    allowed_hosts: Sequence[str] = (),
    dns_resolver: _DnsResolver | None = None,
) -> tuple[InstructionSource, ...]:
    result: list[InstructionSource] = []
    for item in _sequence(items, "instructions", error=InstructionSourceError):
        value = item.get("url", item.get("path", item.get("glob"))) if isinstance(item, Mapping) else item
        if not isinstance(value, str):
            raise InstructionSourceError("invalid_type", "instruction entry must be a string")
        if value.lower().startswith(("http://", "https://")):
            parts = _url(
                value,
                schemes=("http", "https"),
                allowed_hosts=allowed_hosts,
                field_name="instructions URL",
                error=InstructionSourceError,
                dns_resolver=dns_resolver,
            )
            result.append(InstructionSource("url", parts.geturl(), True))
        else:
            relative = _relative_path(value, "instruction path", error=InstructionSourceError)
            result.append(InstructionSource("glob" if any(c in relative for c in "*?[") else "file", relative, False))
    return tuple(result)


def instruction_context(sources: Sequence[InstructionSource]) -> dict:
    entries = tuple(_mapping(s.to_dict(), "source", error=InstructionSourceError) for s in sources)
    return {
        "sources": entries,
        "count": len(entries),
        "tainted": tuple(s.value for s in sources if s.tainted),
        "fetched": False,
    }


# ===========================================================================
# Y1.29 - plugin management CLI
# ===========================================================================

_EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_BRANCH_SUFFIX_RE = re.compile(r"#([^:]+)")
_SUBDIR_SUFFIX_RE = re.compile(r"::path:([^#]+)$")


@dataclass(frozen=True)
class PluginSource(_Descriptor):
    kind: str
    name: str
    version_spec: str
    branch: str
    subdirectory: str
    pinned: bool


def _git_ref(value: Any) -> str:
    ref = _text(value, "branch", max_len=128, error=PluginCommandError)
    if _GIT_REF_BAD_RE.search(ref):
        raise PluginCommandError("unsafe_branch", "branch is not a safe git ref")
    return ref


def parse_plugin_source(
    spec: Any,
    *,
    private_sources: Sequence[str] = (),
    allow_public: bool = False,
) -> PluginSource:
    raw = _text(spec, "plugin source", max_len=512, error=PluginCommandError)
    if _SHELL_INJECTION_RE.search(raw):
        raise PluginCommandError("unsafe_token", "plugin source contains shell metacharacters")
    subdir = ""
    sub_match = _SUBDIR_SUFFIX_RE.search(raw)
    if sub_match:
        subdir = _relative_path(sub_match.group(1), "subdirectory", error=PluginCommandError)
        raw = raw[: sub_match.start()]
    branch = ""
    branch_match = _BRANCH_SUFFIX_RE.search(raw)
    if branch_match:
        branch = _git_ref(branch_match.group(1))
        raw = raw[: branch_match.start()]
    if raw.startswith("github:"):
        slug = raw[len("github:") :]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", slug):
            raise PluginCommandError("invalid_github_source", "use github:owner/repo")
        kind, name, version = "github", slug, ""
        pinned = False
    elif raw.startswith("git+ssh://"):
        rest = raw[len("git+ssh://") :]
        if ".." in rest or "@" not in rest:
            raise PluginCommandError("invalid_git_source", "git+ssh source needs an explicit host")
        kind, name, version = "git_ssh", rest, ""
        pinned = False
    else:
        if raw.startswith("@"):
            pieces = raw[1:].split("@", 1)
            name = "@" + pieces[0]
            version = pieces[1] if len(pieces) == 2 else ""
        else:
            pieces = raw.split("@", 1)
            name, version = pieces[0], pieces[1] if len(pieces) == 2 else ""
        if not re.fullmatch(r"@?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?", name):
            raise PluginCommandError("invalid_npm_name", "unsupported package name")
        kind = "npm"
        pinned = bool(_EXACT_VERSION_RE.fullmatch(version) or _COMMIT_RE.fullmatch(version))
    source = PluginSource(kind, name, version, branch, subdir, pinned)
    if not allow_public:
        private = tuple(str(p) for p in private_sources)
        if not any(name == p or name.startswith(p) for p in private):
            raise PluginCommandError("public_source_blocked", "only private sources are allowed by default")
    return source


def plugin_command(
    action: Any,
    spec: Any = None,
    *,
    builtin: bool = False,
    private_sources: Sequence[str] = (),
    allow_public: bool = False,
) -> dict:
    verb = _text(action, "action", max_len=32, error=PluginCommandError)
    if verb not in ("add", "list", "check", "update", "remove"):
        raise PluginCommandError("unknown_action", f"unknown plugin command {verb!r}")
    use_builtin = _bool(builtin, "builtin", error=PluginCommandError)
    if verb == "list":
        if spec is not None:
            raise PluginCommandError("unexpected_source", "list does not take a source")
        return {"action": "list", "builtin": use_builtin, "network_used": False}
    source = parse_plugin_source(
        spec, private_sources=private_sources, allow_public=allow_public
    )
    return {"action": verb, "source": source.to_dict(), "network_used": False}


def update_plugin_plan(source: PluginSource) -> dict:
    if source.pinned:
        return {"action": "none", "reason": "pinned", "installed_version_unchanged": True}
    return {"action": "check_only", "installed_version_unchanged": True, "network_used": False}


# ===========================================================================
# Y1.31 - three plugin surfaces
# ===========================================================================

PLUGIN_SURFACES: tuple[str, ...] = ("server", "gui", "tui")


@dataclass(frozen=True)
class PluginManifest(_Descriptor):
    name: str
    surfaces: tuple[str, ...]
    panels: tuple[str, ...]
    commands: tuple[str, ...]
    settings: tuple[str, ...]
    hot_reload: bool


def parse_plugin_manifest(manifest: Mapping[str, Any]) -> PluginManifest:
    values = _mapping(manifest, "manifest", error=PluginManifestError)
    name = _safe_id(str(values.get("name", "")), "plugin name", error=PluginManifestError)
    surfaces = tuple(
        _safe_id(str(s), "surface", error=PluginManifestError)
        for s in _sequence(values.get("surfaces", ()), "surfaces", error=PluginManifestError)
    )
    if not surfaces or any(s not in PLUGIN_SURFACES for s in surfaces):
        raise PluginManifestError("unknown_surface", "manifest declares no known surface")
    def _names(key: str) -> tuple[str, ...]:
        return tuple(
            _safe_id(str(item), key, error=PluginManifestError)
            for item in _sequence(values.get(key, ()), key, error=PluginManifestError)
        )

    panels, commands, settings = _names("panels"), _names("commands"), _names("settings")
    if "gui" in surfaces and not (panels or commands or settings):
        # A GUI plugin may be settings-only; the manifest still declares a surface.
        pass
    if "gui" not in surfaces and (panels or settings):
        raise PluginManifestError("surface_mismatch", "panels/settings require the gui surface")
    hot = _bool(values.get("hot_reload", False), "hot_reload", error=PluginManifestError)
    return PluginManifest(name, tuple(sorted(set(surfaces))), panels, commands, settings, hot)


def tui_plugin_ids(config: Mapping[str, Any]) -> tuple[str, ...]:
    values = _mapping(config, "tui", error=PluginManifestError)
    plugins = values.get("plugins", ())
    return tuple(
        _safe_id(str(p), "tui plugin", error=PluginManifestError)
        for p in _sequence(plugins, "tui.plugins", error=PluginManifestError)
    )


def extensions_page_state(
    manifests: Sequence[PluginManifest],
    *,
    failed: Sequence[str] = (),
    disabled: Sequence[str] = (),
) -> tuple[dict, ...]:
    failures = tuple(_safe_id(f, "failed plugin", error=PluginManifestError) for f in failed)
    off = tuple(_safe_id(d, "disabled plugin", error=PluginManifestError) for d in disabled)
    return tuple(
        {
            "name": m.name,
            "surface": ",".join(m.surfaces),
            "enabled": m.name not in failures and m.name not in off,
            "reload_available": m.name in failures,
        }
        for m in sorted(manifests, key=lambda item: item.name)
    )


def hot_reload_plan(
    changed_paths: Sequence[str],
    *,
    watched_dirs: Mapping[str, str],
) -> tuple[dict, ...]:
    watched = _mapping(watched_dirs, "watched_dirs", error=PluginManifestError)
    plan: list[dict] = []
    for path in _sequence(changed_paths, "changed_paths", error=PluginManifestError):
        relative = _relative_path(path, "changed_path", error=PluginManifestError)
        for name, directory in watched.items():
            plugin = _safe_id(str(name), "watched plugin", error=PluginManifestError)
            root = _text(directory, "watched directory", max_len=2048, error=PluginManifestError)
            if _contained(relative, root.replace("\\", "/")):
                plan.append({"plugin": plugin, "action": "reload", "reason": "file_changed"})
    return tuple(plan)


# ===========================================================================
# Y1.32 - location_idle_timeout
# ===========================================================================


@dataclass(frozen=True)
class IdleState(_Descriptor):
    running_sessions: int = 0
    background_jobs: int = 0


def validate_idle_timeout(minutes: Any) -> float:
    return _number(minutes, "location_idle_timeout", minimum=0.0, maximum=10080.0, error=IdleConfigError)


def should_unload(
    *,
    idle_minutes: Any,
    timeout_minutes: Any,
    state: IdleState,
) -> bool:
    idle = _number(idle_minutes, "idle_minutes", error=IdleConfigError)
    limit = validate_idle_timeout(timeout_minutes)
    sessions = _int(state.running_sessions, "running_sessions", minimum=0, error=IdleConfigError)
    jobs = _int(state.background_jobs, "background_jobs", minimum=0, error=IdleConfigError)
    if limit == 0 or sessions > 0 or jobs > 0:
        return False
    return idle >= limit


def unload_plan(*, should_unload_now: bool, services: Sequence[str] = ("lsp", "watchers")) -> dict:
    enabled = _bool(should_unload_now, "should_unload_now", error=IdleConfigError)
    names = tuple(_safe_id(str(s), "service", error=IdleConfigError) for s in services)
    return {"unload": tuple(names) if enabled else (), "sessions_kept": not enabled}


# ===========================================================================
# Y1.33 - experimental.todo flag
# ===========================================================================

TODO_TOOL = "todo"
TODOWRITE_TOOL = "todowrite"


def todo_tool_exposure(config: Mapping[str, Any] | None, tools: Sequence[str]) -> dict:
    """The P0 ``todo`` tool stays; ``todowrite`` is an opt-in alias."""
    values = _mapping(config or {}, "experimental", error=ExperimentalFlagError)
    experimental = dict(values.get("experimental", values))
    option = experimental.get("todo", False)
    enabled = _bool(option, "experimental.todo", error=ExperimentalFlagError)
    available = tuple(_text(t, "tool", error=ExperimentalFlagError) for t in tools)
    exposed = tuple(t for t in available if t != TODOWRITE_TOOL) if not enabled else available
    return {
        "flag": enabled,
        "exposed": exposed,
        "hidden": tuple(t for t in available if t not in exposed),
        "todo_always_available": TODO_TOOL in exposed or TODO_TOOL not in available,
    }


# ===========================================================================
# Y1.34 - model overrides and provider transport
# ===========================================================================

SUPPORTED_TRANSPORTS: tuple[str, ...] = ("http", "https", "websocket", "stdio", "sse")


def validate_transport(value: Any) -> str:
    transport = _text(value, "transport", max_len=32, error=ModelConfigError).lower()
    if transport not in SUPPORTED_TRANSPORTS:
        raise ModelConfigError("unsupported_transport", f"unknown transport {transport!r}")
    return transport


def apply_model_overrides(
    catalog: Mapping[str, Mapping[str, Any]],
    overrides: Mapping[str, Mapping[str, Any]],
) -> dict:
    result: dict[str, dict[str, Any]] = {}
    for key, value in catalog.items():
        entry = dict(_mapping(value, f"catalog.{key}", error=ModelConfigError))
        if isinstance(entry.get("limit"), Mapping):
            entry["limit"] = dict(entry["limit"])
        result[key] = entry
    for key, change in _mapping(overrides, "model overrides", error=ModelConfigError).items():
        model = _safe_id(str(key), "model id", error=ModelConfigError)
        if model not in result:
            raise ModelConfigError("unknown_model", f"{model} is not in the offline catalog")
        values = dict(_mapping(change, f"overrides.{model}", error=ModelConfigError))
        entry = result[model]
        if "id" in values:
            entry["id"] = _safe_id(values["id"], "model id override", error=ModelConfigError)
        if "name" in values:
            entry["name"] = _text(values["name"], "display name", max_len=120, error=ModelConfigError)
        if "limit" in values:
            limits = dict(_mapping(values["limit"], "limit", error=ModelConfigError))
            if "context" in limits:
                entry.setdefault("limit", {})["context"] = _int(
                    limits["context"], "limit.context", error=ModelConfigError
                )
            if "output" in limits:
                entry.setdefault("limit", {})["output"] = _int(
                    limits["output"], "limit.output", error=ModelConfigError
                )
            if (
                "context" in entry.get("limit", {})
                and "output" in entry.get("limit", {})
                and entry["limit"]["output"] > entry["limit"]["context"]
            ):
                raise ModelConfigError("output_exceeds_context", "output limit exceeds context limit")
    return result


def provider_transport(config: Mapping[str, Any]) -> dict:
    values = _mapping(config, "provider", error=ModelConfigError)
    settings = dict(_mapping(values.get("settings", {}), "settings", error=ModelConfigError))
    return {"transport": validate_transport(settings.get("transport", "http"))}


# ===========================================================================
# Y1.35 - config_edit tool
# ===========================================================================

TIER2_CONFIG_KEYS: tuple[str, ...] = (
    "auth", "credentials", "secrets", "secret", "tokens", "token", "api_key",
    "apikey", "policy", "managed", "tier2", "permission", "sandbox",
)
_TIER2_RE = re.compile(
    r"[\"']?(" + "|".join(TIER2_CONFIG_KEYS) + r")[\"']?\s*[:=]", re.IGNORECASE
)


def _value_region(text: str, start: int) -> tuple[int, int]:
    """Return the [start, end) span of the JSON(C) value beginning at *start*.

    Quoted strings are skipped when tracking nesting so braces and colons
    inside strings cannot truncate a value region.
    """
    length = len(text)
    while start < length and text[start].isspace():
        start += 1
    if start >= length:
        return start, start
    if text[start] not in "{[":
        quote = ""
        end = start
        while end < length:
            char = text[end]
            if quote:
                if char == "\\":
                    end += 2
                    continue
                if char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char in ",}]" or char in "\r\n":
                break
            end += 1
        return start, end
    stack = [text[start]]
    quote = ""
    end = start + 1
    while end < length and stack:
        char = text[end]
        if quote:
            if char == "\\":
                end += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            stack.pop()
        end += 1
    return start, end


def _tier2_value_regions(text: str) -> dict[str, list[str]]:
    """Index every Tier-2 key's complete value in a whole config document."""
    regions: dict[str, list[str]] = {}
    for match in _TIER2_RE.finditer(text):
        start, end = _value_region(text, match.end())
        regions.setdefault(match.group(1).lower(), []).append(text[start:end])
    return regions


@dataclass(frozen=True)
class ConfigEditProposal(_Descriptor):
    target: str
    diff: str
    requires_approval: bool
    applies: bool
    changed_keys: tuple[str, ...]


def propose_config_edit(
    current_text: Any,
    replacements: Sequence[tuple[str, str]],
    *,
    target: Any = "keel.jsonc",
) -> ConfigEditProposal:
    """Propose a validated diff only; approval and writing stay with the host."""
    name = _relative_path(target, "target", error=ConfigEditError)
    if not name.endswith(".jsonc"):
        raise ConfigEditError("unsupported_target", "config_edit only edits keel.jsonc")
    original = _blob_text(current_text, "current_text", error=ConfigEditError)
    updated = original
    for pair in _sequence(replacements, "replacements", error=ConfigEditError):
        if not isinstance(pair, Sequence) or isinstance(pair, (str, bytes)) or len(pair) != 2:
            raise ConfigEditError("invalid_replacement", "each replacement is (old, new)")
        old, new = pair
        if not isinstance(old, str) or not isinstance(new, str) or not old:
            raise ConfigEditError("invalid_replacement", "old text must be a non-empty string")
        count = updated.count(old)
        if count == 0:
            raise ConfigEditError("missing_match", "replacement text was not found")
        if count != 1:
            raise ConfigEditError("ambiguous_match", "replacement text must match exactly once")
        updated = updated.replace(old, new, 1)
    if updated == original:
        raise ConfigEditError("no_change", "proposal does not change the file")
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=name,
            tofile=name,
        )
    )
    # The diff alone is not a sufficient gate: a value nested well below a
    # Tier-2 key can change without that key ever appearing in the diff.
    # Compare the complete Tier-2 value regions of both full documents.
    touched = {key.lower() for key in _TIER2_RE.findall(diff)}
    before = _tier2_value_regions(original)
    after = _tier2_value_regions(updated)
    for key in set(before) | set(after):
        if before.get(key, []) != after.get(key, []):
            touched.add(key)
    if touched:
        raise ConfigEditError("tier2_blocked", "Tier-2 settings cannot be edited by the agent")
    return ConfigEditProposal(name, diff, True, False, tuple(sorted(touched)))


# ===========================================================================
# Y1.36 - migrate / troubleshooting docs
# ===========================================================================

DOC_ROUTES: tuple[str, ...] = ("/docs/migrate-from-v1", "/docs/troubleshooting")


@dataclass(frozen=True)
class DocPage(_Descriptor):
    route: str
    title: str
    body: str


def build_docs_pages(error_catalog: Sequence[Mapping[str, Any]]) -> tuple[DocPage, ...]:
    """Generate both in-app pages from the error catalog, escaping all text."""
    codes: set[str] = set()
    troubleshooting: list[str] = []
    migration: list[str] = []
    for entry in _sequence(error_catalog, "error_catalog", error=DocsContractError):
        values = dict(_mapping(entry, "error entry", error=DocsContractError))
        code = _text(values.get("code", ""), "code", max_len=64, error=DocsContractError)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", code) or code in codes:
            raise DocsContractError("invalid_or_duplicate_code", f"bad error code {code!r}")
        codes.add(code)
        message = html.escape(_blob_text(values.get("message") or code, "message", max_len=2000, error=DocsContractError))
        remedy = html.escape(
            _blob_text(
                values.get("remedy", "See the documentation."),
                "remedy",
                max_len=2000,
                error=DocsContractError,
            )
        )
        troubleshooting.append(f"- {html.escape(code)}: {message} -> {remedy}")
        migration.append(f"- {html.escape(code)}: {remedy}")
    if not codes:
        raise DocsContractError("empty_catalog", "the error catalog has no entries")
    body_ts = "# Troubleshooting\n\n" + "\n".join(sorted(troubleshooting)) + "\n"
    body_mig = "# Migrating from V1\n\n" + "\n".join(sorted(migration)) + "\n"
    return (
        DocPage(DOC_ROUTES[0], "Migrate from V1", body_mig),
        DocPage(DOC_ROUTES[1], "Troubleshooting", body_ts),
    )


# ===========================================================================
# Y1.37 - install script and release channels
# ===========================================================================

INSTALL_CHANNELS: Mapping[str, tuple[str, ...]] = {
    "stable": ("script", "brew", "mise", "pacman", "nix"),
    "latest": ("script", "brew-tap", "aur", "nix-unstable"),
    "beta": ("script", "brew-tap", "aur"),
}
STORE_FEASIBILITY: Mapping[str, bool] = {
    "brew": True, "brew-tap": True, "brew-cask": True, "mise": True,
    "pacman": True, "aur": True, "nix": True, "nix-unstable": True, "script": True,
}
_FORBIDDEN_INSTALL_DIRS = (
    "/usr", "/usr/bin", "/usr/local", "/usr/local/bin", "/bin", "/sbin",
    "c:/program files", "c:/windows",
)


@dataclass(frozen=True)
class InstallPlan(_Descriptor):
    channel: str
    method: str
    target_dir: str
    script_preview: str
    cleanup_tip: str
    per_user: bool


def install_plan(
    channel: Any,
    method: Any,
    *,
    home: Any,
    platform: str = "linux",
    cleanup_older_than: int | None = None,
    existing_versions: Sequence[str] = (),
) -> InstallPlan:
    name = _text(channel, "channel", max_len=32, error=InstallPlanError).lower()
    if name not in INSTALL_CHANNELS:
        raise InstallPlanError("unknown_channel", f"unknown channel {name!r}")
    how = _text(method, "method", max_len=32, error=InstallPlanError).lower()
    if how not in INSTALL_CHANNELS[name]:
        raise InstallPlanError("channel_method_mismatch", f"{how} is not available on {name}")
    home_text = _text(home, "home", max_len=1024, error=InstallPlanError)
    if _SHELL_META_RE.search(home_text) or '"' in home_text or ".." in home_text.replace("\\", "/").split("/"):
        raise InstallPlanError("unsafe_home", "home path contains injection or traversal")
    is_windows = platform.lower().startswith("win")
    if is_windows:
        if not re.match(r"^[A-Za-z]:[\\/]", home_text):
            raise InstallPlanError("unsafe_home", "Windows home must be absolute")
        target = ntpath.join(home_text, ".opencode", "bin")
    else:
        if not home_text.startswith("/"):
            raise InstallPlanError("unsafe_home", "home must be an absolute path")
        target = posixpath.join(home_text, ".opencode", "bin")
    lowered = target.replace("\\", "/").lower()
    home_lowered = home_text.replace("\\", "/").rstrip("/").lower()
    if any(home_lowered == p or home_lowered.startswith(p + "/") for p in _FORBIDDEN_INSTALL_DIRS):
        raise InstallPlanError("system_install_dir", "install must be per-user")
    if any(lowered == p or lowered.startswith(p + "/") for p in _FORBIDDEN_INSTALL_DIRS):
        raise InstallPlanError("system_install_dir", "install must be per-user")
    tip = ""
    if cleanup_older_than is not None:
        threshold = _int(cleanup_older_than, "cleanup_older_than", minimum=0, error=InstallPlanError)
        old = [
            _safe_id(v, "existing_version", error=InstallPlanError)
            for v in _sequence(existing_versions, "existing_versions", error=InstallPlanError)
            if v.split(".")[0].isdigit() and int(v.split(".")[0]) < threshold
        ]
        tip = "Remove older versions before installing: " + ", ".join(sorted(old)) if old else ""
    quoted = f'"{target}"' if is_windows else shlex.quote(target)
    preview = f"# preview only: install {name} binary into {quoted}"
    return InstallPlan(name, how, target, preview, tip, True)


# ===========================================================================
# Y1.38 - repo hygiene
# ===========================================================================

REPO_HYGIENE_ARTIFACTS: tuple[str, ...] = (
    ".husky/", ".gitleaksignore", "oxlint", "turbo", "patches/", "CHANGELOG.md", "SECURITY.md",
)


@dataclass(frozen=True)
class AllowlistEntry(_Descriptor):
    pattern: str
    reason: str
    expiry: str
    reviewed: bool


def validate_gitleaks_allowlist(
    entries: Sequence[Mapping[str, Any]],
    *,
    today: date | None = None,
) -> tuple[AllowlistEntry, ...]:
    reference = today or date.today()
    seen: set[str] = set()
    result: list[AllowlistEntry] = []
    for item in _sequence(entries, "gitleaks_allowlist", error=HygieneError):
        values = dict(_mapping(item, "allowlist entry", error=HygieneError))
        pattern = _text(values.get("pattern", ""), "pattern", max_len=512, error=HygieneError)
        reason = _text(values.get("reason", ""), "reason", max_len=500, min_len=8, error=HygieneError)
        expiry = _text(values.get("expiry", ""), "expiry", max_len=32, error=HygieneError)
        reviewed = _bool(values.get("reviewed", False), "reviewed", error=HygieneError)
        try:
            expires = date.fromisoformat(expiry)
        except ValueError as exc:
            raise HygieneError("invalid_expiry", "expiry must be YYYY-MM-DD") from exc
        if expires <= reference:
            raise HygieneError("expired_allowlist", "allowlist entry has expired")
        if not reviewed:
            raise HygieneError("unreviewed_allowlist", "every entry needs a review")
        if pattern in seen:
            raise HygieneError("duplicate_allowlist", "duplicate allowlist pattern")
        seen.add(pattern)
        result.append(AllowlistEntry(pattern, reason, expiry, reviewed))
    return tuple(result)


def repo_hygiene_status(files: Sequence[str]) -> dict:
    present = tuple(_relative_path(f, "file", error=HygieneError) for f in files)
    return {
        "present": {artifact: any(p.startswith(artifact) or p == artifact.rstrip("/") for p in present) for artifact in REPO_HYGIENE_ARTIFACTS},
        "missing": tuple(a for a in REPO_HYGIENE_ARTIFACTS if not any(p.startswith(a) or p == a.rstrip("/") for p in present)),
    }


def task_graph_order(tasks: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """Deterministic topological order; cycles are rejected."""
    graph = {
        _safe_id(str(name), "task", error=HygieneError): tuple(
            _safe_id(str(dep), "dependency", error=HygieneError) for dep in deps
        )
        for name, deps in _mapping(tasks, "tasks", error=HygieneError).items()
    }
    order: list[str] = []
    remaining = dict(graph)
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if all(d in order for d in deps))
        if not ready:
            raise HygieneError("task_cycle", "task graph contains a cycle")
        order.extend(ready)
        for name in ready:
            del remaining[name]
    return tuple(order)


# ===========================================================================
# Y1.39 - "Building on X" non-affiliation notice
# ===========================================================================


def non_affiliation_notice(project: Any, upstream: Any, *, year: int | None = None) -> str:
    name = html.escape(_blob_text(project, "project", max_len=120, error=TrademarkError))
    origin = html.escape(_blob_text(upstream, "upstream", max_len=120, error=TrademarkError))
    suffix = ""
    if year is not None:
        suffix = f" (c) {_int(year, 'year', minimum=2000, maximum=2100, error=TrademarkError)}"
    return (
        f"# Building on {origin}\n\n{name} is an independent project. "
        f"It is not affiliated with, endorsed by, or sponsored by {origin}.{suffix}\n"
    )


def validate_trademarks_doc(text: Any, upstream: Any) -> bool:
    doc = _blob_text(text, "TRADEMARKS.md", max_len=10000, error=TrademarkError)
    origin = html.escape(_blob_text(upstream, "upstream", max_len=120, error=TrademarkError))
    if _UNSAFE_RE.search(doc):
        raise TrademarkError("unsafe_tag", "notice contains an unsafe tag")
    if "not affiliated with" not in doc.lower() or origin not in doc:
        raise TrademarkError("missing_non_affiliation", "notice must state non-affiliation")
    return True


__all__ = [name for name in globals() if not name.startswith("_")]
