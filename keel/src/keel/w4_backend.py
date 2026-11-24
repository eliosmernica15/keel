"""Pure, stdlib-only backend contracts for the 13 remaining W4.* MCP rows.

This is an *additive* module: it imports no other Keel module, opens no socket,
spawns no subprocess, reads no clock and writes no file.  Every input comes
from the caller, every result is deterministic and structured, and anything
malformed fails closed with a coded ``W4Error``.  The module deliberately
contains **no UI code**: where the plan mentions a CLI or an in-app panel this
module produces the command result / view model that such a surface consumes.

Coverage (``master-plan-v6-final-matrix.csv``, addendum 5 section 3.3):

* W4.1  ``mcp add/list/auth/logout`` command backend + ``/mcps`` view model
* W4.2  ``mcp.servers.<name>`` shape, whole-object precedence, dropped-field warnings
* W4.4  client registration order: pre-registered -> CIMD -> DCR
* W4.5  pasted failed-callback URL fallback when the browser is remote
* W4.6  startup/catalog/execution timeouts (30 s / 30 s / 12 h) and progress seam
* W4.7  conservative protocol default, ``auto`` probe, pinned revisions
* W4.8  shared-connection identity + reference-counted connection pool
* W4.9  tool-name normalization with deterministic collision suffixes
* W4.10 prompt catalog -> ``<server>:<prompt>`` slash commands with positional args
* W4.11 tainted server instructions in a tagged system-prompt block
* W4.12 elicitation form/link descriptors and answer validation (dismiss cancels)
* W4.13 request ``_meta``: no session id by default, opt-in + remote log warning
* W4.14 ``disabled`` keeps config; runtime disconnect never edits config

W4.3 (OAuth PKCE/discovery/refresh) was already verified in
``keel.product_contracts`` and is intentionally not re-implemented here.
"""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import hmac
import json
import math
import os
import re
import shlex
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import parse_qs, urlencode, urlsplit
from xml.sax.saxutils import escape as _xml_escape

# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

FEATURE_IDS: tuple[str, ...] = (
    "W4.1", "W4.2", "W4.4", "W4.5", "W4.6", "W4.7", "W4.8", "W4.9",
    "W4.10", "W4.11", "W4.12", "W4.13", "W4.14",
)

FEATURE_IMPLEMENTATIONS: dict[str, str] = {
    "W4.1": "dispatch_mcp_command / mcps_panel / McpConfigStore",
    "W4.2": "normalize_server_config / merge_config_layers",
    "W4.4": "select_client_registration",
    "W4.5": "extract_callback_url / parse_pasted_callback",
    "W4.6": "resolve_timeouts / call_progress",
    "W4.7": "select_protocol",
    "W4.8": "connection_identity / ConnectionPool",
    "W4.9": "normalize_tool_name / normalize_tool_names",
    "W4.10": "slash_commands_from_catalog / render_prompt_command",
    "W4.11": "build_system_prompt / server_tools_denied",
    "W4.12": "render_elicitation / answer_elicitation",  # module-level wrapper below
    "W4.13": "build_request_meta / correlation_id_for",
    "W4.14": "ConnectionState / connect_server / disconnect_server",
}


def feature_manifest() -> dict[str, dict[str, str]]:
    """Machine-readable ID -> entry-point map (used by the evidence gate)."""
    return {
        fid: {"id": fid, "entry_point": FEATURE_IMPLEMENTATIONS[fid]}
        for fid in FEATURE_IDS
    }


# ---------------------------------------------------------------------------
# errors and shared helpers
# ---------------------------------------------------------------------------


class W4Error(ValueError):
    """Base class for every W4 contract failure; ``code`` is machine-readable."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(f"[{code}] {self.message}")


class ConfigError(W4Error):
    pass


class CliError(W4Error):
    pass


class OAuthError(W4Error):
    pass


class ProtocolError(W4Error):
    pass


class PoolingError(W4Error):
    pass


class NamingError(W4Error):
    pass


class PromptError(W4Error):
    pass


class ElicitationError(W4Error):
    pass


_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|authorization)\b\s*[:=]\s*\S+"
)


def redact_text(value: Any) -> str:
    """Replace credential-looking assignments before text is logged or returned."""
    text = "" if value is None else str(value)
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)


def _copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _copy(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy(v) for v in value]
    return value


def _as_mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(code, "expected a mapping")
    return value


def _fingerprint(value: Any) -> str:
    """Stable SHA-256 of canonical JSON (no host state, no secret in the digest)."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _check_name(value: Any, code: str) -> str:
    if not isinstance(value, str) or not _NAME_RE.fullmatch(value):
        raise ConfigError(code, "name must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    return value


def _string_map(value: Any, field_name: str) -> dict[str, str]:
    raw = _as_mapping(value, f"bad_{field_name}")
    result: dict[str, str] = {}
    for key, item in raw.items():
        if not isinstance(key, str) or not key:
            raise ConfigError(f"bad_{field_name}_key")
        if isinstance(item, (Mapping, list, tuple)) or item is None:
            raise ConfigError(f"bad_{field_name}_value", f"{field_name}.{key}")
        result[key] = str(item)
    return result


# ===========================================================================
# W4.2 - config shape and whole-object precedence
# ===========================================================================

SERVER_FIELDS: tuple[str, ...] = (
    "type", "command", "cwd", "environment", "url", "headers", "oauth",
    "disabled", "codemode", "timeout", "protocol", "pool",
)
SERVER_TYPES: tuple[str, ...] = ("local", "remote")


@dataclass(frozen=True)
class ServerConfig:
    """One normalized ``mcp.servers.<name>`` object."""

    name: str
    type: str
    command: tuple[str, ...] = ()
    cwd: str | None = None
    environment: Mapping[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    oauth: bool | Mapping[str, Any] = True
    disabled: bool = False
    codemode: bool = False
    timeout: Any = None
    protocol: str | None = None
    pool: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "command": list(self.command),
            "cwd": self.cwd,
            "environment": dict(self.environment),
            "url": self.url,
            "headers": dict(self.headers),
            "oauth": _copy(self.oauth),
            "disabled": self.disabled,
            "codemode": self.codemode,
            "timeout": _copy(self.timeout),
            "protocol": self.protocol,
            "pool": self.pool,
        }


def _parse_command(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        tokens = shlex.split(value)
    elif isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        tokens = list(value)
    else:
        raise ConfigError("bad_command", "command must be a string or list of strings")
    if not tokens or not all(tokens):
        raise ConfigError("empty_command")
    return tuple(tokens)


def normalize_server_config(name: str, raw: Mapping[str, Any]) -> ServerConfig:
    """Validate and normalize one server object; never fills from another layer."""
    _check_name(name, "bad_server_name")
    data = _as_mapping(raw, "bad_server_object")
    unknown = sorted(set(data) - set(SERVER_FIELDS))
    if unknown:
        raise ConfigError("unknown_server_field", ", ".join(unknown))
    kind = data.get("type")
    if kind not in SERVER_TYPES:
        raise ConfigError("bad_server_type", "expected local or remote")
    # A serialized config carries every field; only a *populated* cross-type
    # field is an error (``url: null`` on a local server is harmless).
    if kind == "local" and data.get("url") is not None:
        raise ConfigError("remote_field_on_local", "url")
    if kind == "remote" and data.get("command") not in (None, (), []):
        raise ConfigError("local_field_on_remote", "command")

    command: tuple[str, ...] = ()
    if kind == "local":
        if "command" in data and data["command"] is not None:
            command = _parse_command(data["command"])
        if not command:
            raise ConfigError("missing_command")
    url = data.get("url")
    if kind == "remote":
        if not isinstance(url, str) or not urlsplit(url).scheme or not urlsplit(url).netloc:
            raise ConfigError("bad_url")
        if urlsplit(url).scheme not in ("http", "https", "ws", "wss"):
            raise ConfigError("bad_url_scheme")

    cwd = data.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or not cwd):
        raise ConfigError("bad_cwd")
    oauth = data.get("oauth", True)
    if isinstance(oauth, bool):
        pass
    elif isinstance(oauth, Mapping):
        oauth = _copy(oauth)
    else:
        raise ConfigError("bad_oauth")
    for flag in ("disabled", "codemode"):
        if flag in data and not isinstance(data[flag], bool):
            raise ConfigError(f"bad_{flag}")
    pool = data.get("pool")
    if pool is not None and (not isinstance(pool, str) or not pool):
        raise ConfigError("bad_pool")
    protocol = data.get("protocol")
    if protocol is not None and not isinstance(protocol, str):
        raise ConfigError("bad_protocol")
    return ServerConfig(
        name=name,
        type=kind,
        command=command,
        cwd=cwd,
        environment=_string_map(data.get("environment", {}), "environment"),
        url=url,
        headers=_string_map(data.get("headers", {}), "headers"),
        oauth=oauth,
        disabled=bool(data.get("disabled", False)),
        codemode=bool(data.get("codemode", False)),
        timeout=_copy(data.get("timeout")),
        protocol=protocol,
        pool=pool,
    )


@dataclass(frozen=True)
class ConfigDocument:
    """One precedence layer: ``mcp.servers`` plus global mcp options."""

    servers: Mapping[str, ServerConfig] = field(default_factory=dict)
    global_timeout: Any = None
    global_protocol: str | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mcp": {
                "servers": {name: cfg.to_dict() for name, cfg in self.servers.items()},
                "timeout": _copy(self.global_timeout),
                "protocol": self.global_protocol,
            }
        }


def normalize_config_document(raw: Mapping[str, Any]) -> ConfigDocument:
    """Parse a whole config layer (``{"mcp": {"servers": {...}}}``)."""
    data = _as_mapping(raw, "bad_config_document")
    mcp = _as_mapping(data.get("mcp", {}), "bad_mcp_section")
    servers_raw = _as_mapping(mcp.get("servers", {}), "bad_servers_section")
    servers = {
        str(name): normalize_server_config(str(name), cfg)
        for name, cfg in servers_raw.items()
    }
    protocol = mcp.get("protocol")
    if protocol is not None and not isinstance(protocol, str):
        raise ConfigError("bad_protocol")
    return ConfigDocument(
        servers=servers,
        global_timeout=_copy(mcp.get("timeout")),
        global_protocol=protocol,
    )


def config_document_from_json(text: str) -> ConfigDocument:
    try:
        raw = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ConfigError("bad_config_json", str(exc)) from exc
    return normalize_config_document(raw)


def config_document_to_json(document: ConfigDocument) -> str:
    return json.dumps(document.to_dict(), sort_keys=True, indent=2, ensure_ascii=False)


def merge_config_layers(layers: Sequence[Mapping[str, Any]]) -> ConfigDocument:
    """Fold layers low -> high precedence.  A higher layer *replaces* a server.

    No field merge is performed.  When a replacement drops keys that the lower
    layer had set, a warning is emitted so the loss is visible instead of
    silently changing a server's behavior.
    """
    servers: dict[str, ServerConfig] = {}
    raw_by_name: dict[str, Mapping[str, Any]] = {}
    warnings: list[str] = []
    global_timeout: Any = None
    global_protocol: str | None = None
    for index, layer in enumerate(layers):
        doc = normalize_config_document(layer)
        if doc.global_timeout is not None:
            global_timeout = doc.global_timeout
        if doc.global_protocol is not None:
            global_protocol = doc.global_protocol
        raw_servers = _as_mapping(
            _as_mapping(layer, "bad_config_document").get("mcp", {}),
            "bad_mcp_section",
        ).get("servers", {})
        for name, cfg in doc.servers.items():
            if name in raw_by_name:
                dropped = sorted(set(raw_by_name[name]) - set(raw_servers[name]))
                if dropped:
                    warnings.append(
                        f"W4.2: server {name!r} replaced by layer {index}; "
                        f"fields not merged: {', '.join(dropped)}"
                    )
            servers[name] = cfg
            raw_by_name[name] = raw_servers[name]
    return ConfigDocument(
        servers=servers,
        global_timeout=global_timeout,
        global_protocol=global_protocol,
        warnings=tuple(warnings),
    )


# ===========================================================================
# W4.6 - timeouts (declared here because config normalization references them)
# ===========================================================================

DEFAULT_TIMEOUTS: dict[str, float] = {
    "startup": 30.0,
    "catalog": 30.0,
    "execution": 12 * 60 * 60.0,
}
PROBE_COST_WARNING = (
    "protocol=auto costs one extra round-trip per new connection (protocol probe)"
)
REMOTE_LOG_WARNING = (
    "remote MCP servers may log request _meta, including the session id; "
    "keep send_session_id disabled unless required"
)


@dataclass(frozen=True)
class TimeoutSpec:
    startup: float
    catalog: float
    execution: float

    def to_dict(self) -> dict[str, float]:
        return {"startup": self.startup, "catalog": self.catalog,
                "execution": self.execution}


def _coerce_timeouts(value: Any, source: str) -> dict[str, float]:
    if value is None:
        return {}
    if isinstance(value, bool):
        raise ConfigError("bad_timeout", source)
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or value <= 0:
            raise ConfigError("bad_timeout", source)
        return {key: float(value) for key in DEFAULT_TIMEOUTS}
    raw = _as_mapping(value, "bad_timeout")
    unknown = sorted(set(raw) - set(DEFAULT_TIMEOUTS))
    if unknown:
        raise ConfigError("unknown_timeout_field", ", ".join(unknown))
    result: dict[str, float] = {}
    for key, item in raw.items():
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ConfigError("bad_timeout", f"{source}.{key}")
        if not math.isfinite(item) or item <= 0:
            raise ConfigError("bad_timeout", f"{source}.{key}")
        result[key] = float(item)
    return result


def resolve_timeouts(*, global_timeout: Any = None,
                     server_timeout: Any = None) -> TimeoutSpec:
    """Defaults <- global ``mcp.timeout`` <- per-server ``timeout``."""
    values = dict(DEFAULT_TIMEOUTS)
    values.update(_coerce_timeouts(global_timeout, "global"))
    values.update(_coerce_timeouts(server_timeout, "server"))
    return TimeoutSpec(**values)


def call_progress(elapsed_seconds: float, spec: TimeoutSpec,
                  *, phase: str = "execution") -> dict[str, Any]:
    """Backend for the long-running-call indicator and cancel affordance."""
    if phase not in DEFAULT_TIMEOUTS:
        raise ConfigError("bad_phase", phase)
    if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, (int, float)):
        raise ConfigError("bad_elapsed")
    elapsed = max(0.0, float(elapsed_seconds))
    budget = getattr(spec, phase)
    return {
        "phase": phase,
        "elapsed_seconds": elapsed,
        "budget_seconds": budget,
        "remaining_seconds": max(0.0, budget - elapsed),
        "timed_out": elapsed >= budget,
        "show_indicator": elapsed >= budget * 0.8,
        "cancel_supported": True,
    }


# ===========================================================================
# W4.7 - protocol selection
# ===========================================================================

PROTOCOL_REVISIONS: tuple[str, ...] = ("2024-11-05", "2025-03-26", "2025-06-18")
LATEST_PROTOCOL = PROTOCOL_REVISIONS[-1]
LEGACY_PROTOCOL = "legacy"
DEFAULT_PROTOCOL = LEGACY_PROTOCOL  # plan: "default conservative"


@dataclass(frozen=True)
class ProtocolSelection:
    protocol: str
    needs_probe: bool
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "needs_probe": self.needs_probe,
            "warnings": list(self.warnings),
        }


def select_protocol(configured: str | None = None, *,
                    probe_result: Mapping[str, Any] | None = None,
                    allow_probe: bool = True,
                    supported: Sequence[str] = PROTOCOL_REVISIONS) -> ProtocolSelection:
    """Choose legacy, resolve an ``auto`` probe, or validate a pinned revision."""
    revisions = tuple(supported)
    choice = configured or DEFAULT_PROTOCOL
    if not isinstance(choice, str):
        raise ProtocolError("bad_protocol")
    if choice == LEGACY_PROTOCOL:
        return ProtocolSelection(LEGACY_PROTOCOL, False)
    if choice == "auto":
        warnings = [PROBE_COST_WARNING]
        if probe_result is None:
            if allow_probe:
                return ProtocolSelection(LEGACY_PROTOCOL, True, tuple(warnings))
            warnings.append("probe disabled; using conservative legacy protocol")
            return ProtocolSelection(LEGACY_PROTOCOL, False, tuple(warnings))
        probe = _as_mapping(probe_result, "bad_probe_result")
        if probe.get("error"):
            warnings.append(f"probe failed: {redact_text(probe['error'])}")
            return ProtocolSelection(LEGACY_PROTOCOL, False, tuple(warnings))
        version = probe.get("version")
        if version not in revisions:
            raise ProtocolError("bad_probe_version")
        return ProtocolSelection(version, False, tuple(warnings))
    if choice not in revisions:
        raise ProtocolError("unknown_protocol", choice)
    return ProtocolSelection(choice, False)


# ===========================================================================
# W4.4 - client registration order
# ===========================================================================

DEFAULT_CALLBACK_PORT = 8765  # loopback listener used when none was configured


@dataclass(frozen=True)
class ClientRegistration:
    method: str  # none | pre_registered | cimd | dcr
    client_id: str = ""
    client_secret: str | None = None
    scope: str = ""
    callback_port: int = 0
    redirect_uri: str = ""
    auth_server_metadata_url: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "client_id": self.client_id,
            "client_secret": "[REDACTED]" if self.client_secret else None,
            "has_secret": bool(self.client_secret),
            "scope": self.scope,
            "callback_port": self.callback_port,
            "redirect_uri": self.redirect_uri,
            "auth_server_metadata_url": self.auth_server_metadata_url,
            "reason": self.reason,
        }


def _metadata_url_for(server_url: str | None) -> str | None:
    if not server_url:
        return None
    parts = urlsplit(server_url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}/.well-known/oauth-authorization-server"


def select_client_registration(
    raw: Any,
    *,
    pre_registered: Mapping[str, Mapping[str, Any]] | None = None,
    server_url: str | None = None,
    allow_cimd: bool = True,
    allow_dcr: bool = True,
) -> ClientRegistration:
    """Pre-registered client_id -> CIMD -> DCR, in that order.

    A CIMD ``client_id`` is an ``https://`` metadata URL and must be hosted by
    the caller: Keel never requires a Keel-operated metadata service.  If CIMD
    is unavailable, DCR (or a user-supplied id) is used instead.
    """
    catalog = dict(pre_registered or {})
    if raw is False or raw is None:
        return ClientRegistration("none", reason="oauth_disabled_header_key_server")
    options = _as_mapping(raw, "bad_oauth_options")
    client_id = options.get("client_id")
    source: dict[str, Any] = {}
    reason = ""
    if isinstance(client_id, str) and client_id and not client_id.startswith(("http://", "https://")):
        source = dict(catalog.get(client_id, {}))
        method = "pre_registered"
        reason = "pre_registered_client_id"
        effective_id = client_id
    elif isinstance(client_id, str) and client_id.startswith("https://") and len(urlsplit(client_id).netloc) > 0:
        if not allow_cimd:
            raise OAuthError("cimd_disallowed", "CIMD disabled and no client_id supplied")
        source = {"auth_server_metadata_url": client_id}
        method = "cimd"
        reason = "client_id_metadata_document"
        effective_id = client_id
    elif isinstance(client_id, str) and client_id:
        raise OAuthError("bad_client_id", "CIMD requires an https:// metadata URL")
    elif allow_dcr:
        source = {}
        method = "dcr"
        reason = "dynamic_client_registration"
        effective_id = ""
    else:
        raise OAuthError("no_registration_method")

    merged = dict(source)
    merged.update(options)
    for key in ("client_secret", "auth_server_metadata_url"):
        if merged.get(key) is not None and not isinstance(merged[key], str):
            raise OAuthError("bad_oauth_option", key)
    scope = merged.get("scope", "")
    if not isinstance(scope, str):
        raise OAuthError("bad_oauth_option", "scope")
    redirect_uri = merged.get("redirect_uri")
    if redirect_uri is not None and not isinstance(redirect_uri, str):
        raise OAuthError("bad_redirect_uri")
    port = merged.get("callback_port")
    if port is None:
        derived = urlsplit(redirect_uri or "").port
        port = derived or DEFAULT_CALLBACK_PORT
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise OAuthError("bad_callback_port")
    redirect_uri = redirect_uri or f"http://127.0.0.1:{port}/callback"
    if not urlsplit(redirect_uri).scheme:
        raise OAuthError("bad_redirect_uri")
    metadata_url = merged.get("auth_server_metadata_url") or _metadata_url_for(server_url)
    if method in ("cimd", "dcr") and not metadata_url:
        raise OAuthError("missing_metadata_url", method)
    return ClientRegistration(
        method=method,
        client_id=effective_id,
        client_secret=merged.get("client_secret"),
        scope=scope,
        callback_port=port,
        redirect_uri=redirect_uri,
        auth_server_metadata_url=metadata_url,
        reason=reason,
    )


# ===========================================================================
# W4.5 - pasted callback URL (browser on another machine)
# ===========================================================================

CALLBACK_PASTE_PROMPT = (
    "The browser could not reach the local callback. Paste the failed "
    "callback URL (or the whole address-bar line) here to finish sign-in."
)
_URL_RE = re.compile(r"https?://[^\s<>\"'`)\]}]+")


def extract_callback_url(text: Any) -> str:
    """Pull the first HTTP(S) URL out of prose, quotes or a fenced code block."""
    if not isinstance(text, str) or not text.strip():
        raise OAuthError("empty_callback_text")
    match = _URL_RE.search(text)
    if not match:
        raise OAuthError("callback_url_not_found")
    url = match.group(0).rstrip(".,;")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise OAuthError("bad_callback_url")
    return url


@dataclass(frozen=True)
class CallbackResult:
    code: str
    state: str
    redirect_uri: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "state": self.state,
                "redirect_uri": self.redirect_uri}


def parse_pasted_callback(
    text: Any,
    *,
    expected_state: str,
    redirect_uri: str | None = None,
    allowed_hosts: Iterable[str] = ("localhost", "127.0.0.1", "::1"),
) -> CallbackResult:
    """Validate a pasted callback: loopback host, exact state, single code."""
    if not isinstance(expected_state, str) or not expected_state:
        raise OAuthError("bad_expected_state")
    url = extract_callback_url(text)
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in {h.lower() for h in allowed_hosts}:
        raise OAuthError("callback_host_not_allowed", host)
    values = parse_qs(parts.query, keep_blank_values=True)
    if "error" in values:
        raise OAuthError("oauth_error", redact_text(values["error"][0]))
    codes = values.get("code", [])
    states = values.get("state", [])
    if len(codes) != 1 or not codes[0]:
        raise OAuthError("callback_code_missing")
    if len(states) != 1 or not hmac.compare_digest(states[0], expected_state):
        raise OAuthError("callback_state_mismatch")
    if redirect_uri:
        expected = urlsplit(redirect_uri)
        if (parts.scheme, parts.netloc, parts.path) != (
            expected.scheme, expected.netloc, expected.path
        ):
            raise OAuthError("callback_redirect_mismatch")
    return CallbackResult(codes[0], states[0], url)


def build_authorization_url(
    authorization_endpoint: str,
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_verifier: str | None = None,
    scope: str = "",
) -> str:
    """Pure URL builder for ``mcp auth`` (no discovery, no network, no PKCE secret log)."""
    if not authorization_endpoint or not urlsplit(authorization_endpoint).scheme:
        raise OAuthError("bad_authorization_endpoint")
    if not client_id or not redirect_uri or not state:
        raise OAuthError("bad_authorization_request")
    query = [("response_type", "code"), ("client_id", client_id),
             ("redirect_uri", redirect_uri), ("state", state)]
    if scope:
        query.append(("scope", scope))
    if code_verifier:
        if not isinstance(code_verifier, str) or len(code_verifier) < 43:
            raise OAuthError("bad_code_verifier")
        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        query.extend([("code_challenge", challenge), ("code_challenge_method", "S256")])
    separator = "&" if urlsplit(authorization_endpoint).query else "?"
    return f"{authorization_endpoint}{separator}{urlencode(query)}"


# ===========================================================================
# W4.9 - tool naming normalization
# ===========================================================================

_INVALID_TOOL_CHARS = re.compile(r"[^A-Za-z0-9_]")


def _short_name(base: str, digest: str, max_length: int) -> str:
    room = max_length - len(digest) - 1
    if room <= 0:
        raise NamingError("max_length_too_small")
    return f"{base[:room]}_{digest}"


def normalize_tool_name(server: str, tool: str, *,
                        used: Iterable[str] = (),
                        max_length: int = 64) -> str:
    """``<server>_<tool>`` with invalid characters folded to ``_``.

    Collisions get a deterministic short suffix derived from the exact
    (server, tool) pair; a numeric suffix breaks any residual collision.  The
    caller supplies ``used`` so the result is stable for a fixed registry.
    """
    if not isinstance(server, str) or not server.strip():
        raise NamingError("empty_server")
    if not isinstance(tool, str) or not tool.strip():
        raise NamingError("empty_tool")
    if max_length < 16:
        raise NamingError("max_length_too_small")
    base = _INVALID_TOOL_CHARS.sub("_", f"{server.strip()}_{tool.strip()}")
    base = re.sub(r"_+", "_", base).strip("_")
    if not base:
        raise NamingError("empty_normalized_name")
    taken = set(used)
    if len(base) <= max_length and base not in taken:
        return base
    digest = hashlib.sha1(f"{server}\0{tool}".encode("utf-8")).hexdigest()[:8]
    candidate = _short_name(base, digest, max_length)
    counter = 2
    while candidate in taken:
        suffix = f"{digest[:6]}{counter:02d}"
        candidate = _short_name(base, suffix, max_length)
        counter += 1
        if counter > 1000:
            raise NamingError("collision_exhausted")
    return candidate


def normalize_tool_names(server: str, tools: Iterable[str]) -> dict[str, str]:
    """Normalize a whole catalog; duplicate source names are a hard error."""
    result: dict[str, str] = {}
    for tool in tools:
        if tool in result:
            raise NamingError("duplicate_tool", tool)
        result[tool] = normalize_tool_name(server, tool, used=result.values())
    return result


# ===========================================================================
# W4.8 - pooled shared connections
# ===========================================================================

# ``disabled`` and ``pool`` are runtime/layout hints: they do not change what a
# connection talks to, so they are excluded from the identity on purpose.
_IDENTITY_EXCLUDE = frozenset({"disabled", "pool", "name"})


def connection_identity(config: ServerConfig | Mapping[str, Any]) -> str:
    """Fingerprint every connection-affecting setting (secrets stay hashed)."""
    if isinstance(config, ServerConfig):
        data = config.to_dict()
    else:
        data = normalize_server_config(
            str(_as_mapping(config, "bad_server_object").get("name", "server")),
            config,
        ).to_dict()
    payload = {k: _copy(v) for k, v in data.items() if k not in _IDENTITY_EXCLUDE}
    if payload.get("cwd"):
        payload["cwd"] = os.path.normpath(payload["cwd"])
    return _fingerprint(payload)


@dataclass(frozen=True)
class ConnectionLease:
    lease_id: str
    identity: str
    owner: str
    shared: bool

    def to_dict(self) -> dict[str, Any]:
        return {"lease_id": self.lease_id, "identity": self.identity,
                "owner": self.owner, "shared": self.shared}


@dataclass
class _PoolEntry:
    identity: str
    descriptor: Mapping[str, Any]
    owners: set[str] = field(default_factory=set)


class ConnectionPool:
    """Reference-counted in-memory registry of *shared* MCP connections.

    No sockets are opened: the descriptor is supplied by the caller and the
    pool decides whether an existing connection can be reused.  Identical
    settings in different project directories therefore yield one entry.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _PoolEntry] = {}
        self._leases: dict[str, str] = {}
        self._lease_owner: dict[str, str] = {}
        self._counter = 0

    def acquire(self, identity: str, *, owner: str,
                descriptor: Mapping[str, Any] | None = None) -> ConnectionLease:
        if not isinstance(identity, str) or not identity:
            raise PoolingError("bad_identity")
        if not isinstance(owner, str) or not owner:
            raise PoolingError("bad_owner")
        existing = self._entries.get(identity)
        if existing is None:
            existing = _PoolEntry(identity, dict(descriptor or {}))
            self._entries[identity] = existing
        elif descriptor and dict(descriptor) != dict(existing.descriptor):
            raise PoolingError("descriptor_mismatch", identity)
        self._counter += 1
        lease_id = f"{identity[:12]}-{self._counter}"
        self._leases[lease_id] = identity
        self._lease_owner[lease_id] = owner
        existing.owners = {
            self._lease_owner[lid] for lid, ident in self._leases.items()
            if ident == identity
        }
        return ConnectionLease(lease_id, identity, owner, len(existing.owners) > 1)

    def release(self, lease_id: str) -> dict[str, bool]:
        identity = self._leases.pop(lease_id, None)
        if identity is None:
            raise PoolingError("unknown_lease", lease_id)
        self._lease_owner.pop(lease_id, None)
        entry = self._entries[identity]
        entry.owners = {
            self._lease_owner[lid] for lid, ident in self._leases.items()
            if ident == identity
        }
        if not any(ident == identity for ident in self._leases.values()):
            del self._entries[identity]
            return {"released": True, "closed": True}
        return {"released": True, "closed": False}

    def descriptor_for(self, identity: str) -> dict[str, Any]:
        entry = self._entries.get(identity)
        if entry is None:
            raise PoolingError("unknown_identity", identity)
        return dict(entry.descriptor)

    def stats(self) -> dict[str, int]:
        return {
            "connections": len(self._entries),
            "leases": len(self._leases),
            "shared_connections": sum(1 for e in self._entries.values()
                                      if len(e.owners) > 1),
        }


# ===========================================================================
# W4.10 - prompts as slash commands
# ===========================================================================

_SLASH_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class SlashCommand:
    name: str
    server: str
    prompt: str
    template: str
    arguments: tuple[str, ...]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "server": self.server, "prompt": self.prompt,
                "template": self.template, "arguments": list(self.arguments),
                "description": self.description}


def prompt_slash_name(server: str, prompt: str) -> str:
    for value, code in ((server, "bad_server_name"), (prompt, "bad_prompt_name")):
        if not isinstance(value, str) or not _SLASH_NAME_RE.fullmatch(value):
            raise PromptError(code, value)
    return f"{server}:{prompt}"


def parse_slash_arguments(text: str) -> tuple[str, ...]:
    """Split a slash command's positional arguments (quotes respected)."""
    if not isinstance(text, str):
        raise PromptError("bad_arguments")
    try:
        return tuple(shlex.split(text))
    except ValueError as exc:
        raise PromptError("bad_arguments", str(exc)) from exc


def make_slash_command(server: str, prompt: str, template: str,
                       *, arguments: Sequence[str] = (),
                       description: str = "") -> SlashCommand:
    if not isinstance(template, str):
        raise PromptError("bad_template")
    names = tuple(arguments)
    if len(set(names)) != len(names):
        raise PromptError("duplicate_argument")
    for name in names:
        if not isinstance(name, str) or not _SLASH_NAME_RE.fullmatch(name):
            raise PromptError("bad_argument_name", str(name))
    return SlashCommand(prompt_slash_name(server, prompt), server, prompt,
                        template, names, description)


def render_prompt_command(command: SlashCommand, argv: Sequence[str]) -> str:
    """Bind positional args to ``{{name}}`` / ``${name}`` prompt placeholders."""
    args = tuple(argv)
    if len(args) != len(command.arguments):
        raise PromptError("argument_count_mismatch",
                          f"expected {len(command.arguments)}, got {len(args)}")
    text = command.template
    for name, value in zip(command.arguments, args):
        text = text.replace("{{" + name + "}}", value)
        text = text.replace("${" + name + "}", value)
    if "{{" in text or "${" in text:
        raise PromptError("unresolved_placeholder")
    return text


def slash_commands_from_catalog(
    server: str, prompts: Mapping[str, Mapping[str, Any]],
) -> dict[str, SlashCommand]:
    """Import an MCP prompt catalog into a command registry."""
    catalog = _as_mapping(prompts, "bad_prompt_catalog")
    result: dict[str, SlashCommand] = {}
    for name, raw in catalog.items():
        entry = _as_mapping(raw, "bad_prompt_entry")
        command = make_slash_command(
            server, str(name), str(entry.get("template", "")),
            arguments=entry.get("arguments", ()),
            description=str(entry.get("description", "")),
        )
        result[command.name] = command
    return result


# ===========================================================================
# W4.11 - tainted server instructions in the system prompt
# ===========================================================================

INSTRUCTION_TAG = "mcp_instructions"


@dataclass(frozen=True)
class PermissionRule:
    """Minimal ordered permission rule; ``resource``/``action`` are globs."""

    action: str = "*"
    resource: str = "*"
    effect: str = "allow"

    def __post_init__(self) -> None:
        if self.effect not in ("allow", "ask", "deny"):
            raise ConfigError("bad_effect", self.effect)
        if not isinstance(self.resource, str) or not self.resource:
            raise ConfigError("bad_permission_resource")
        if not isinstance(self.action, str) or not self.action:
            raise ConfigError("bad_permission_action")

    def matches(self, target: str) -> bool:
        return (fnmatch.fnmatchcase(target, self.resource)
                or fnmatch.fnmatchcase(target, self.action))

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action, "resource": self.resource,
                "effect": self.effect}


def _coerce_rule(value: PermissionRule | Mapping[str, Any]) -> PermissionRule:
    if isinstance(value, PermissionRule):
        return value
    raw = _as_mapping(value, "bad_permission_rule")
    return PermissionRule(str(raw.get("action", "*")),
                          str(raw.get("resource", "*")),
                          str(raw.get("effect", "allow")))


def canonical_tool_resource(server: str, tool: str) -> str:
    return f"mcp.{server}.{tool}"


def server_tools_denied(server: str, tools: Iterable[str],
                        rules: Iterable[PermissionRule | Mapping[str, Any]]) -> bool:
    """True only when at least one tool exists and every tool is denied."""
    names = list(tools)
    if not names:
        return False
    compiled = [_coerce_rule(r) for r in rules]
    for tool in names:
        target = canonical_tool_resource(server, tool)
        denied = any(r.effect == "deny" and r.matches(target) for r in compiled)
        if not denied:
            return False
    return True


@dataclass(frozen=True)
class SystemPrompt:
    text: str
    injected_servers: tuple[str, ...]
    omitted_servers: tuple[str, ...]
    trusted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "injected_servers": list(self.injected_servers),
                "omitted_servers": list(self.omitted_servers),
                "trusted": self.trusted}


def build_system_prompt(
    base_prompt: str,
    *,
    server_instructions: Mapping[str, str],
    server_tools: Mapping[str, Sequence[str]],
    permissions: Sequence[PermissionRule | Mapping[str, Any]] = (),
) -> SystemPrompt:
    """Append each server's init instructions in a tagged, tainted block.

    Content is XML-escaped so a server cannot close the tag and promote its
    text to a user/system instruction.  A server whose every tool is denied is
    omitted entirely.
    """
    if not isinstance(base_prompt, str):
        raise ConfigError("bad_base_prompt")
    instructions = _as_mapping(server_instructions, "bad_server_instructions")
    tools = _as_mapping(server_tools, "bad_server_tools")
    parts = [base_prompt]
    injected: list[str] = []
    omitted: list[str] = []
    for server in sorted(instructions):
        text = instructions[server]
        if not isinstance(text, str):
            raise ConfigError("bad_instruction_text", server)
        if server_tools_denied(server, tools.get(server, ()), permissions):
            omitted.append(server)
            continue
        attrs = _xml_escape(server, {'"': "&quot;"})
        body = _xml_escape(text)
        parts.append(
            f'<{INSTRUCTION_TAG} server="{attrs}" trusted="false" '
            f'priority="below_user">\n{body}\n</{INSTRUCTION_TAG}>'
        )
        injected.append(server)
    return SystemPrompt("\n\n".join(parts), tuple(injected), tuple(omitted), False)


# ===========================================================================
# W4.12 - elicitation
# ===========================================================================

_ELICITATION_TYPES = frozenset({"string", "number", "integer", "boolean"})


@dataclass(frozen=True)
class ElicitationRequest:
    request_id: str
    server: str
    message: str
    schema: Mapping[str, Any]
    link_url: str | None = None

    @classmethod
    def create(cls, server: str, message: str, schema: Mapping[str, Any],
               *, link_url: str | None = None) -> ElicitationRequest:
        if not isinstance(server, str) or not server:
            raise ElicitationError("bad_server")
        if not isinstance(message, str) or not message:
            raise ElicitationError("bad_message")
        raw = _as_mapping(schema, "bad_schema")
        properties = _as_mapping(raw.get("properties", {}), "bad_properties")
        for name, field_schema in properties.items():
            spec = _as_mapping(field_schema, "bad_field_schema")
            kind = spec.get("type", "string")
            if kind not in _ELICITATION_TYPES:
                raise ElicitationError("unsupported_field_type", str(kind))
        for required in raw.get("required", ()):
            if required not in properties:
                raise ElicitationError("unknown_required_field", str(required))
        if link_url is not None and not isinstance(link_url, str):
            raise ElicitationError("bad_link_url")
        rid = _fingerprint({"server": server, "message": message,
                            "schema": raw, "link_url": link_url})[:16]
        return cls(rid, server, message, _copy(raw), link_url)

    def render(self) -> dict[str, Any]:
        """Backend view model: a form (or a link) plus a dismiss action."""
        raw = _as_mapping(self.schema, "bad_schema")
        properties = _as_mapping(raw.get("properties", {}), "bad_properties")
        required = set(raw.get("required", ()))
        fields: list[dict[str, Any]] = []
        for name, spec in properties.items():
            entry = dict(spec)
            entry["name"] = name
            entry["required"] = name in required
            fields.append(entry)
        return {
            "id": self.request_id,
            "kind": "link" if self.link_url else "form",
            "server": self.server,
            "message": self.message,
            "fields": fields,
            "link_url": self.link_url,
            "actions": ["submit", "decline", "dismiss"],
            "dismiss_cancels": True,
        }


def render_elicitation(request: ElicitationRequest) -> dict[str, Any]:
    """Module-level entry point for the form/link view model."""
    return request.render()


@dataclass(frozen=True)
class ElicitationResult:
    status: str  # submitted | cancelled | declined | invalid
    values: Mapping[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()

    @property
    def cancelled(self) -> bool:
        return self.status == "cancelled"

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "values": dict(self.values),
                "errors": list(self.errors), "cancelled": self.cancelled}


def answer_elicitation(request: ElicitationRequest, *, action: str = "submit",
                       values: Mapping[str, Any] | None = None) -> ElicitationResult:
    """Validate a form submission; dismiss/decline always cancel the request."""
    if action in ("dismiss", "cancel"):
        return ElicitationResult("cancelled")
    if action == "decline":
        return ElicitationResult("declined")
    if action != "submit":
        raise ElicitationError("bad_action", action)
    supplied = dict(values or {})
    schema = _as_mapping(request.schema, "bad_schema")
    properties = _as_mapping(schema.get("properties", {}), "bad_properties")
    required = list(schema.get("required", ()))
    errors: list[str] = []
    unknown = sorted(set(supplied) - set(properties))
    if unknown:
        errors.append("unknown_field: " + ", ".join(unknown))
    for name in required:
        if name not in supplied or supplied[name] in (None, ""):
            errors.append(f"required_field_missing: {name}")
    validated: dict[str, Any] = {}
    for name, spec in properties.items():
        if name not in supplied:
            if "default" in spec:
                validated[name] = _copy(spec["default"])
            continue
        value = supplied[name]
        kind = spec.get("type", "string")
        if kind == "string":
            if not isinstance(value, str):
                errors.append(f"type_mismatch: {name}")
                continue
            if len(value) < int(spec.get("minLength", 0)):
                errors.append(f"too_short: {name}")
            if "maxLength" in spec and len(value) > int(spec["maxLength"]):
                errors.append(f"too_long: {name}")
            if spec.get("pattern") and not re.search(str(spec["pattern"]), value):
                errors.append(f"pattern_mismatch: {name}")
        elif kind == "boolean":
            if not isinstance(value, bool):
                errors.append(f"type_mismatch: {name}")
                continue
        elif kind in ("integer", "number"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"type_mismatch: {name}")
                continue
            if kind == "integer" and not float(value).is_integer():
                errors.append(f"type_mismatch: {name}")
                continue
            if "minimum" in spec and value < spec["minimum"]:
                errors.append(f"below_minimum: {name}")
            if "maximum" in spec and value > spec["maximum"]:
                errors.append(f"above_maximum: {name}")
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"not_in_enum: {name}")
        validated[name] = value
    if errors:
        return ElicitationResult("invalid", {}, tuple(errors))
    return ElicitationResult("submitted", validated)


# ===========================================================================
# W4.13 - request _meta
# ===========================================================================

META_SESSION_KEY = "opencode.sessionId"
META_CORRELATION_KEY = "keel.correlationId"


def correlation_id_for(server: str, session_id: str, *, salt: str = "") -> str:
    """Opaque, per-server correlation id (never the raw session id)."""
    if not server or not session_id:
        raise ConfigError("bad_correlation_input")
    digest = hashlib.sha256(f"{server}\0{session_id}\0{salt}".encode("utf-8")).hexdigest()
    return "kc_" + digest[:24]


@dataclass(frozen=True)
class RequestMeta:
    meta: Mapping[str, Mapping[str, str]]
    warnings: tuple[str, ...] = ()
    sent_session_id: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"_meta": _copy(self.meta.get("_meta", {})),
                "warnings": list(self.warnings),
                "sent_session_id": self.sent_session_id}


def build_request_meta(
    *,
    session_id: str | None = None,
    send_session_id: bool = False,
    correlation_id: str | None = None,
    remote: bool = False,
    extra: Mapping[str, str] | None = None,
) -> RequestMeta:
    """Keel sends no session id by default; opt-in carries a remote-log warning."""
    if session_id is not None and not isinstance(session_id, str):
        raise ConfigError("bad_session_id")
    meta: dict[str, str] = dict(extra or {})
    if correlation_id:
        meta[META_CORRELATION_KEY] = correlation_id
    send = bool(send_session_id and session_id)
    if send:
        meta[META_SESSION_KEY] = session_id  # type: ignore[assignment]
    warnings: list[str] = []
    if send and remote:
        warnings.append(REMOTE_LOG_WARNING)
    return RequestMeta({"_meta": meta} if meta else {}, tuple(warnings), send)


# ===========================================================================
# W4.14 - disabled servers and runtime disconnect (config is immutable here)
# ===========================================================================


@dataclass
class ConnectionState:
    configured: set[str] = field(default_factory=set)
    disabled: dict[str, bool] = field(default_factory=dict)
    connected: set[str] = field(default_factory=set)
    runtime_disconnected: set[str] = field(default_factory=set)

    @classmethod
    def from_documents(cls, documents: Sequence[ConfigDocument]) -> ConnectionState:
        merged = merge_config_layers([doc.to_dict() for doc in documents])
        return cls(
            configured=set(merged.servers),
            disabled={name: cfg.disabled for name, cfg in merged.servers.items()},
        )

    def view(self, name: str) -> dict[str, Any]:
        known = name in self.configured
        disabled = bool(self.disabled.get(name, False))
        connected = name in self.connected and not disabled
        state = ("unconfigured" if not known else "disabled" if disabled
                 else "connected" if connected else "disconnected")
        return {"server": name, "configured": known, "disabled": disabled,
                "connected": connected, "state": state}

    def snapshot(self) -> dict[str, Any]:
        return {name: self.view(name) for name in sorted(self.configured)}


def connect_server(state: ConnectionState, name: str) -> dict[str, Any]:
    """Connect a configured, enabled server; a disabled server is refused."""
    view = state.view(name)
    if not view["configured"]:
        raise CliError("unknown_server", name)
    if view["disabled"]:
        raise CliError("server_disabled", name)
    state.runtime_disconnected.discard(name)
    state.connected.add(name)
    return state.view(name)


def disconnect_server(state: ConnectionState, name: str) -> dict[str, Any]:
    """Runtime-only disconnect: the config document is never touched."""
    if name not in state.configured:
        raise CliError("unknown_server", name)
    state.connected.discard(name)
    state.runtime_disconnected.add(name)
    result = state.view(name)
    result["config_unchanged"] = True
    return result


# ===========================================================================
# W4.1 - CLI command backend and /mcps view model
# ===========================================================================


@dataclass(frozen=True)
class CliResult:
    command: str
    ok: bool
    data: Any
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"command": self.command, "ok": self.ok,
                "data": _copy(self.data), "message": self.message}


class McpConfigStore:
    """In-memory user/project config, credentials and runtime connection state.

    Config is held as parsed documents; callers that need JSON use
    ``config_document_to_json`` on ``document(scope)``.  No file is written.
    """

    def __init__(self, *, user_config: Mapping[str, Any] | None = None,
                 project_config: Mapping[str, Any] | None = None,
                 credentials: Mapping[str, str] | None = None) -> None:
        self._documents: dict[str, ConfigDocument] = {
            "user": normalize_config_document(user_config or {}),
            "project": normalize_config_document(project_config or {}),
        }
        self.credentials: dict[str, str] = dict(credentials or {})
        self.pending_auth: dict[str, str] = {}
        self.state = ConnectionState.from_documents(
            [self._documents["user"], self._documents["project"]]
        )

    def document(self, scope: str) -> ConfigDocument:
        if scope not in self._documents:
            raise CliError("bad_scope", scope)
        return self._documents[scope]

    def set_document(self, scope: str, raw: Mapping[str, Any]) -> ConfigDocument:
        if scope not in self._documents:
            raise CliError("bad_scope", scope)
        doc = normalize_config_document(raw)
        self._documents[scope] = doc
        self.state = ConnectionState.from_documents(list(self._documents.values()))
        return doc

    def add_server(self, scope: str, name: str, raw: Mapping[str, Any]) -> dict[str, Any]:
        doc = self._documents[scope]
        cfg = normalize_server_config(name, raw)
        servers = dict(doc.servers)
        servers[name] = cfg
        self._documents[scope] = ConfigDocument(
            servers, doc.global_timeout, doc.global_protocol, doc.warnings
        )
        self.state = ConnectionState.from_documents(list(self._documents.values()))
        return cfg.to_dict()

    def find(self, name: str) -> tuple[str, ServerConfig] | None:
        for scope in ("project", "user"):
            cfg = self._documents[scope].servers.get(name)
            if cfg is not None:
                return scope, cfg
        return None

    def rows(self) -> list[dict[str, Any]]:
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for scope in ("project", "user"):
            for name, cfg in self._documents[scope].servers.items():
                if name in seen:
                    continue
                seen.add(name)
                view = self.state.view(name)
                rows.append({
                    "name": name,
                    "scope": scope,
                    "type": cfg.type,
                    "target": cfg.url if cfg.type == "remote" else " ".join(cfg.command),
                    "disabled": cfg.disabled,
                    "connected": view["connected"],
                    "state": view["state"],
                    "authenticated": name in self.credentials,
                })
        return sorted(rows, key=lambda row: row["name"])

    def effective(self) -> ConfigDocument:
        return merge_config_layers(
            [self._documents["user"].to_dict(), self._documents["project"].to_dict()]
        )


def mcps_panel(store: McpConfigStore) -> dict[str, Any]:
    """Backend view model for the in-app ``/mcps`` surface (no rendering)."""
    return {
        "servers": store.rows(),
        "actions": ["view", "connect", "disconnect", "authenticate"],
        "config_edits_by_disconnect": False,
        "warnings": list(store.effective().warnings),
    }


_CLI_FLAGS = {
    "--url": "value", "--env": "multi", "--header": "multi",
    "--cwd": "value", "--protocol": "value", "--timeout": "value",
    "--client-id": "value", "--metadata-url": "value", "--global": "flag",
    "--verifier": "value", "--endpoint": "value",
}


def _parse_cli(tokens: Sequence[str], command: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {"positional": [], "--env": [], "--header": []}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            parsed["positional"].extend(tokens[index + 1:])
            break
        kind = _CLI_FLAGS.get(token)
        if kind is None:
            if token.startswith("-"):
                raise CliError("unknown_flag", token)
            parsed["positional"].append(token)
            index += 1
            continue
        if kind == "flag":
            parsed[token] = True
            index += 1
            continue
        if index + 1 >= len(tokens):
            raise CliError("missing_flag_value", token)
        value = tokens[index + 1]
        if kind == "multi":
            parsed[token].append(value)
        else:
            parsed[token] = value
        index += 2
    if command == "add" and not parsed["positional"]:
        raise CliError("missing_server_name")
    return parsed


def _parse_assignments(items: Sequence[str], code: str, separator: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if separator not in item:
            raise CliError(code, redact_text(item))
        key, value = item.split(separator, 1)
        if not key.strip():
            raise CliError(code, "empty_key")
        result[key.strip()] = value.strip()
    return result


def dispatch_mcp_command(argv: Sequence[str], store: McpConfigStore) -> CliResult:
    """Parse and run ``mcp add|list|auth|logout`` without printing or exiting."""
    args = list(argv)
    if args and args[0] == "mcp":
        args = args[1:]
    if not args:
        return CliResult("mcp", False, {"code": "missing_subcommand"},
                         "missing_subcommand")
    command, tokens = args[0], args[1:]
    try:
        if command not in ("add", "list", "auth", "logout"):
            raise CliError("unknown_subcommand", command)
        if command == "list":
            if tokens:
                raise CliError("unexpected_argument", " ".join(tokens))
            return CliResult("list", True, store.rows())

        parsed = _parse_cli(tokens, command)
        if not parsed["positional"]:
            # ``add`` is guarded in _parse_cli; ``auth``/``logout`` are not, so
            # a bare command (or one carrying only flags) would otherwise index
            # an empty list and raise an unhandled IndexError here.
            raise CliError("missing_server_name")
        name = parsed["positional"][0]
        if command == "add":
            scope = "user" if parsed.get("--global") else "project"
            environment = _parse_assignments(parsed["--env"], "bad_env", "=")
            headers = _parse_assignments(parsed["--header"], "bad_header", ":")
            rest = parsed["positional"][1:]
            if parsed.get("--url"):
                raw: dict[str, Any] = {"type": "remote", "url": parsed["--url"]}
            else:
                if not rest:
                    raise CliError("missing_command")
                raw = {"type": "local", "command": rest}
            if environment:
                raw["environment"] = environment
            if headers:
                raw["headers"] = headers
            if parsed.get("--cwd"):
                raw["cwd"] = parsed["--cwd"]
            if parsed.get("--protocol"):
                raw["protocol"] = parsed["--protocol"]
            if parsed.get("--timeout"):
                raw["timeout"] = parsed["--timeout"]
            cfg = store.add_server(scope, name, raw)
            return CliResult("add", True, {"server": name, "scope": scope, "config": cfg})

        found = store.find(name)
        if found is None:
            raise CliError("unknown_server", name)
        _, cfg = found
        if command == "auth":
            if cfg.oauth is False:
                return CliResult("auth", False, {}, "oauth_disabled_header_key_server")
            # ``oauth: true`` means "use OAuth, discover the rest": start from
            # empty options so DCR/metadata derivation still produces a plan.
            oauth_options = {} if cfg.oauth is True else cfg.oauth
            options = dict(_as_mapping(oauth_options, "bad_oauth_options"))
            if parsed.get("--client-id"):
                options["client_id"] = parsed["--client-id"]
            if parsed.get("--metadata-url"):
                options["auth_server_metadata_url"] = parsed["--metadata-url"]
            registration = select_client_registration(options, server_url=cfg.url)
            endpoint = str(parsed.get("--endpoint")
                           or options.get("authorization_endpoint") or "")
            if not endpoint:
                return CliResult(
                    "auth", True,
                    {"server": name, "method": registration.method,
                     "metadata_url": registration.auth_server_metadata_url,
                     "registration": registration.to_dict(),
                     "next": "discover_authorization_endpoint"},
                    "authorization_endpoint_not_configured",
                )
            state = _fingerprint({"server": name, "client_id": registration.client_id})[:16]
            store.pending_auth[name] = state
            url = build_authorization_url(
                endpoint,
                client_id=registration.client_id or "keel-client",
                redirect_uri=registration.redirect_uri,
                state=state,
                code_verifier=parsed.get("--verifier"),
                scope=registration.scope,
            )
            return CliResult("auth", True, {
                "server": name, "method": registration.method,
                "authorization_url": url, "state": state,
                "registration": registration.to_dict(),
                "paste_prompt": CALLBACK_PASTE_PROMPT,
            })
        store.credentials.pop(name, None)
        store.pending_auth.pop(name, None)
        return CliResult("logout", True, {"server": name, "credentials_removed": True})
    except W4Error as exc:
        return CliResult(command, False, {"code": exc.code}, redact_text(exc.message))


# Backwards-friendly alias used by the CLI adapter.
MCP_COMMANDS: tuple[str, ...] = ("add", "list", "auth", "logout")
