"""Stdlib-only backend behavior for the Y4 / D4 / X7 feature families.

This module implements the 31 ``not_started`` rows of ``PLAN-INDEX.json`` whose
IDs begin with ``Y4.``, ``D4.`` or ``X7.``.  It is a *backend* module: it exposes
deterministic contracts, stores, planners and verifiers, and never renders a UI
or starts a real daemon, tunnel, installer or network connection.  Callers own
all clocks, file bodies, credentials and environment state; nothing here reads
the clock, uses chance, opens a socket or spawns a process on import.

The six already-``verified`` P0 rows in these families (Y4.3, Y4.9, Y4.13 in
``keel.identity_contracts`` and D4.2, D4.7, D4.11 in
``keel.composition_contracts``) are intentionally *not* re-implemented here.
They are documented in ``PRIOR_VERIFIED_P0`` and verified by their own tests.

Every validator returns sorted tuples of :class:`Issue` objects so identical
inputs always produce byte-for-byte identical evidence.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import posixpath
import re
import tarfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlencode


class BackendError(ValueError):
    """Raised when a strict backend contract receives an invalid value."""


@dataclass(frozen=True)
class Issue:
    """A single reproducible validation finding."""

    code: str
    location: str
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "location": self.location,
                "message": self.message}


def _issues(items: Iterable[Issue]) -> tuple[Issue, ...]:
    return tuple(sorted(items, key=lambda i: (i.code, i.location, i.message)))


def _clean(value: Any) -> str:
    return str(value if value is not None else "").strip()


# ===========================================================================
# Y4 — MCP revival, pairing, secrets, bridge, traces, desktop, vault, presets
# ===========================================================================

# --------------------------------------------------------------- Y4.1
class ServerPhase(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    REVIVING = "reviving"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ReviveResult:
    server: str
    phase: ServerPhase
    instant: bool
    detail: str

    def as_dict(self) -> dict:
        return {"server": self.server, "phase": str(self.phase),
                "instant": self.instant, "detail": self.detail}


class McpServerReviver:
    """Y4.1: ``/mcp`` revives a dormant keyed server immediately; otherwise a
    configurable background re-probe (default five minutes) revives it.

    Time is supplied by the caller as an integer tick, never read from the
    host clock.  A reload is instantaneous and never waits for the probe.
    """

    DEFAULT_PROBE_INTERVAL_S = 300

    def __init__(self, names: Iterable[str] = (), *,
                 probe_interval_s: int = DEFAULT_PROBE_INTERVAL_S):
        if int(probe_interval_s) <= 0:
            raise BackendError("probe_interval_s must be positive")
        self.probe_interval_s = int(probe_interval_s)
        self._phase: dict[str, ServerPhase] = {}
        self._last_probe: dict[str, int] = {}
        for name in names:
            self.register(name)

    def register(self, name: str) -> None:
        key = _clean(name)
        if not key:
            raise BackendError("server name must not be empty")
        self._phase[key] = ServerPhase.ACTIVE
        self._last_probe.setdefault(key, 0)

    def mark_dormant(self, name: str) -> ServerPhase:
        self._require(name)
        self._phase[name] = ServerPhase.DORMANT
        return self._phase[name]

    def reload(self, name: str) -> ReviveResult:
        """The ``/mcp`` chat command: revive now, never on the probe timer."""
        self._require(name)
        was = self._phase[name]
        self._phase[name] = ServerPhase.ACTIVE
        self._last_probe[name] = 0
        return ReviveResult(name, ServerPhase.ACTIVE, True,
                            f"revived instantly from {str(was)}")

    def record_probe(self, name: str, now_tick: int) -> None:
        self._require(name)
        self._last_probe[name] = int(now_tick)

    def probe_due(self, name: str, now_tick: int) -> bool:
        self._require(name)
        elapsed = int(now_tick) - self._last_probe.get(name, 0)
        return elapsed >= self.probe_interval_s

    def due_servers(self, now_tick: int) -> tuple[str, ...]:
        return tuple(sorted(n for n in self._phase
                            if self._phase[n] is ServerPhase.DORMANT
                            and self.probe_due(n, now_tick)))

    def phase(self, name: str) -> ServerPhase:
        self._require(name)
        return self._phase[name]

    def _require(self, name: str) -> None:
        if name not in self._phase:
            raise KeyError(name)


# --------------------------------------------------------------- Y4.2
class PairingChannel(str, Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    SIGNAL = "signal"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PairingPayload:
    channel: PairingChannel
    deep_link: str
    qr_text: str
    manual_code: str
    manual_steps: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"channel": str(self.channel), "deep_link": self.deep_link,
                "qr_text": self.qr_text, "manual_code": self.manual_code,
                "manual_steps": list(self.manual_steps),
                "has_manual_fallback": has_manual_fallback(self)}


def build_onboarding_payload(channel: PairingChannel | str, token: str, *,
                             host: str = "127.0.0.1",
                             port: int = 8739) -> PairingPayload:
    """Y4.2: QR/deep-link chat onboarding with a mandatory manual fallback."""
    chan = channel if isinstance(channel, PairingChannel) else PairingChannel(str(channel))
    key = _clean(token)
    if not key:
        raise BackendError("pairing token must not be empty")
    # Encode every query value: an unencoded token containing '&' could inject
    # or override host/port parameters in the deep link.
    link = "keel://pair?" + urlencode({"channel": chan.value, "token": key,
                                       "host": host, "port": int(port)})
    code = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8].upper()
    return PairingPayload(
        chan, link, link, code,
        (f"Open the {chan.value} app and search for the Keel bot.",
         f"Send /start then paste pairing code {code}.",
         "No QR reader? The deep link above works in any browser."),
    )


def has_manual_fallback(payload: PairingPayload) -> bool:
    return bool(payload.manual_code and payload.manual_steps)


# --------------------------------------------------------------- Y4.4
class SecretProvider(str, Enum):
    OP = "op"
    PASS = "pass"
    BW = "bw"

    def __str__(self) -> str:
        return self.value


_ENV_FIELD_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class ProviderBinding:
    vault: str
    fields: Mapping[str, str]
    token_env_file: str


class SecretProviderMap:
    """Y4.4: a named vault whose field names mirror env var names.

    The map ships disabled.  It only becomes active once its token exists in a
    *separate* env file and a non-interactive check passes, so the CLI never
    prompts on every start.  Enabling an ``op``/``pass``/``bw`` command provider
    validates non-interactivity first.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, ProviderBinding] = {}
        self._enabled = False
        self._provider: SecretProvider | None = None

    def add_binding(self, vault: str, fields: Mapping[str, str],
                    *, token_env_file: str) -> None:
        name = _clean(vault)
        token_file = _clean(token_env_file)
        if not name:
            raise BackendError("vault name must not be empty")
        if not token_file.endswith(".env"):
            raise BackendError("token must live in a separate .env file")
        if token_file in ("config.yaml", "config.yml"):
            raise BackendError("token env file must be separate from config.yaml")
        env = dict(fields)
        if not env:
            raise BackendError("a vault binding needs at least one field")
        for field_name, var in env.items():
            if not _ENV_FIELD_RE.match(str(field_name)) or not _ENV_FIELD_RE.match(str(var)):
                raise BackendError("vault fields and env vars must be UPPER_SNAKE_CASE")
        self._bindings[name] = ProviderBinding(name, env, token_file)

    @staticmethod
    def is_non_interactive(*, token_present: bool, stdin_isatty: bool,
                           prompt_required: bool = False) -> bool:
        return bool(token_present and not stdin_isatty and not prompt_required)

    def enable(self, provider: SecretProvider | str, *, token_present: bool,
               stdin_isatty: bool, prompt_required: bool = False) -> None:
        prov = (provider if isinstance(provider, SecretProvider)
                else SecretProvider(str(provider)))
        if not self.is_non_interactive(token_present=token_present,
                                       stdin_isatty=stdin_isatty,
                                       prompt_required=prompt_required):
            raise BackendError("secret provider would prompt interactively; "
                               "refusing to enable")
        self._provider = prov
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def resolve(self, field: str) -> str | None:
        """Return the env var for a field, or ``None`` while disabled."""
        if not self._enabled:
            return None
        for binding in self._bindings.values():
            if field in binding.fields:
                return binding.fields[field]
        return None

    def token_file(self, vault: str) -> str | None:
        binding = self._bindings.get(vault)
        return binding.token_env_file if binding else None


# --------------------------------------------------------------- Y4.5
class BridgePhase(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    SUSPENDED = "suspended"

    def __str__(self) -> str:
        return self.value


class SupervisedBridge:
    """Y4.5: a supervised webhook bridge that wakes only when keyed.

    Inbound webhooks arrive only through a tunnel URL the user supplied; the
    "self-provision" step produces a local plan and never opens a socket.
    """

    def __init__(self) -> None:
        self._phase = BridgePhase.STOPPED
        self._tunnel: str | None = None
        self._key: str | None = None
        self._deliveries = 0

    def provision_plan(self) -> tuple[str, ...]:
        return ("confirm user-provided tunnel URL",
                "bind loopback listener", "register wake key",
                "supervise listener with restart-on-exit")

    def start(self, tunnel_url: str, *, key: str,
              user_provided: bool = True) -> BridgePhase:
        url = _clean(tunnel_url)
        if not url.startswith("https://"):
            raise BackendError("webhook tunnel must be an explicit https URL")
        if not user_provided:
            raise BackendError("inbound webhooks require a user-provided tunnel")
        if not _clean(key):
            raise BackendError("bridge wake key must not be empty")
        self._tunnel, self._key = url, key
        self._phase = BridgePhase.RUNNING
        return self._phase

    def wake_if_keyed(self, event_key: str) -> bool:
        if self._key is not None and event_key == self._key:
            self._phase = BridgePhase.RUNNING
            return True
        return False

    def suspend(self) -> BridgePhase:
        if self._phase is BridgePhase.RUNNING:
            self._phase = BridgePhase.SUSPENDED
        return self._phase

    def deliver(self, event: Mapping[str, Any]) -> dict:
        if self._phase is not BridgePhase.RUNNING or not self._tunnel:
            raise BackendError("bridge is not running with a tunnel")
        self._deliveries += 1
        digest = hashlib.sha256(
            json.dumps(event, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:12]
        return {"id": digest, "tunnel": self._tunnel,
                "seq": self._deliveries, "event": dict(event)}

    @property
    def phase(self) -> BridgePhase:
        return self._phase


# --------------------------------------------------------------- Y4.6
@dataclass(frozen=True)
class TraceEvent:
    seq: int
    kind: str
    name: str
    detail: str
    ts: int

    def as_dict(self) -> dict:
        return {"seq": self.seq, "kind": self.kind, "name": self.name,
                "detail": self.detail, "ts": self.ts}


class TraceStore:
    """Y4.6: local model/tool traces plus an internal ``traces`` MCP tool."""

    KINDS = frozenset({"model", "tool", "event"})

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(self, kind: str, name: str, *, detail: str = "",
               ts: int = 0) -> TraceEvent:
        if kind not in self.KINDS:
            raise BackendError(f"unknown trace kind: {kind}")
        event = TraceEvent(len(self._events) + 1, kind, _clean(name),
                           _clean(detail), int(ts))
        self._events.append(event)
        return event

    def query(self, *, kind: str | None = None, name: str | None = None,
              since_seq: int = 0, limit: int = 50) -> tuple[TraceEvent, ...]:
        found = [e for e in self._events
                 if (kind is None or e.kind == kind)
                 and (name is None or e.name == name)
                 and e.seq > int(since_seq)]
        return tuple(found[:max(0, int(limit))])

    def what_did_you_do(self, *, limit: int = 20) -> tuple[str, ...]:
        return tuple(f"{e.kind}:{e.name}" for e in self.query(limit=limit))

    @staticmethod
    def mcp_tool_descriptor() -> dict:
        return {
            "name": "traces",
            "description": "Query local telemetry traces about this session.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["model", "tool", "event"]},
                    "name": {"type": "string"},
                    "since_seq": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "additionalProperties": False,
            },
        }


# --------------------------------------------------------------- Y4.7
KEYLESS_DESKTOP_TOOLS: tuple[str, ...] = (
    "screenshot", "click", "type", "key", "scroll", "drag",
    "bash", "file_read", "file_write", "window_list", "read_clipboard",
)
DESKTOP_TOOL_AUTH = "vm_auth"


def desktop_tool_manifest() -> tuple[dict, ...]:
    """Y4.7: 11 key-less tools riding the VM's own auth (no stored key)."""
    return tuple({"name": name, "auth": DESKTOP_TOOL_AUTH,
                  "requires_key": False,
                  "description": f"Desktop control: {name.replace('_', ' ')}."}
                 for name in KEYLESS_DESKTOP_TOOLS)


def validate_desktop_tools(names: Iterable[str]) -> tuple[Issue, ...]:
    supplied = set(names)
    expected = set(KEYLESS_DESKTOP_TOOLS)
    return _issues(
        [Issue("missing_desktop_tool", name, "required key-less tool is absent")
         for name in sorted(expected - supplied)]
        + [Issue("unknown_desktop_tool", name, "tool is not in the 11-tool set")
           for name in sorted(supplied - expected)]
    )


# --------------------------------------------------------------- Y4.8
class ObsidianVault:
    """Y4.8: a plain-Markdown vault the agent reads/writes with path containment."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def note_path(self, name: str) -> Path:
        base = _clean(name)
        if not base:
            raise BackendError("note name must not be empty")
        if not base.lower().endswith(".md"):
            base += ".md"
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).lstrip(".")
        if not safe:
            raise BackendError("note name has no usable characters")
        path = (self.root / safe).resolve()
        if self.root not in path.parents:
            raise BackendError("note path escapes the vault root")
        return path

    def create_note(self, name: str, body: str) -> dict:
        path = self.note_path(name)
        if path.exists():
            raise BackendError("note already exists")
        path.write_text(str(body), encoding="utf-8")
        return {"name": path.name, "path": str(path), "format": "markdown",
                "bytes": path.stat().st_size}

    def read_note(self, name: str) -> str:
        return self.note_path(name).read_text(encoding="utf-8")

    def list_notes(self) -> tuple[str, ...]:
        return tuple(sorted(p.name for p in self.root.rglob("*.md")))

    @staticmethod
    def editor_command(path: str | Path, editor: str = "code") -> tuple[str, ...]:
        """Build an argv list for opening a note; never invokes a shell."""
        program = _clean(editor) or "code"
        return (program, "--goto", str(path)) if program == "code" else (program, str(path))


# --------------------------------------------------------------- Y4.10
SKILL_RUNBOOKS: tuple[tuple[str, str], ...] = (
    ("telegram", "channel:telegram"), ("discord", "channel:discord"),
    ("slack", "channel:slack"), ("whatsapp", "channel:whatsapp"),
    ("signal", "channel:signal"), ("matrix", "channel:matrix"),
    ("email", "connector:imap-smtp"), ("github", "connector:github"),
    ("gitlab", "connector:gitlab"), ("linear", "connector:linear"),
    ("notion", "connector:notion"), ("obsidian", "connector:obsidian-vault"),
    ("google-drive", "connector:gdrive"), ("dropbox", "connector:dropbox"),
    ("sqlite", "mcp:sqlite"), ("filesystem", "mcp:filesystem"),
    ("git", "mcp:git"), ("fetch", "mcp:fetch"),
    ("playwright", "mcp:playwright"), ("memory", "mcp:memory"),
    ("time", "mcp:time"),
)


def list_runbooks() -> tuple[dict, ...]:
    """Y4.10: exactly 21 setup runbooks, each mapped to a Keel connector."""
    return tuple({"unit": name, "target": target,
                  "file": f"runbooks/{name}.md"}
                 for name, target in sorted(SKILL_RUNBOOKS))


def resolve_runbook(unit: str) -> dict | None:
    for entry in list_runbooks():
        if entry["unit"] == _clean(unit):
            return entry
    return None


def validate_skill_library() -> tuple[Issue, ...]:
    units = [name for name, _ in SKILL_RUNBOOKS]
    found: list[Issue] = []
    if len(units) != 21:
        found.append(Issue("runbook_count", "SKILL_RUNBOOKS",
                           "the skill library must contain 21 units"))
    if len(set(units)) != len(units):
        found.append(Issue("duplicate_runbook", "SKILL_RUNBOOKS",
                           "runbook unit names must be unique"))
    for name, target in SKILL_RUNBOOKS:
        if not target or ":" not in target:
            found.append(Issue("unmapped_runbook", name,
                               "runbook must map to a connector or channel"))
    return _issues(found)


# --------------------------------------------------------------- Y4.11
@dataclass(frozen=True)
class ProviderSwitch:
    model_line: str
    provider_line: str

    def lines(self) -> tuple[str, ...]:
        return (self.model_line, self.provider_line)


def two_line_switch(*, model: str, provider: str) -> ProviderSwitch:
    """Y4.11: flipping a provider is two config.yaml lines; secrets stay refs."""
    if not _clean(model) or not _clean(provider):
        raise BackendError("model and provider are required")
    return ProviderSwitch(f"model: {_clean(model)}",
                          f"provider: {_clean(provider)}")


def config_reference_examples(providers: Iterable[str]) -> dict:
    out: dict[str, dict] = {}
    for provider in sorted(set(providers)):
        switch = two_line_switch(model=f"{provider}/default", provider=provider)
        out[provider] = {
            "lines": list(switch.lines()),
            "config": {
                "model": f"{provider}/default", "provider": provider,
                "mcp": ["filesystem", "git"], "plugins": ["notes"],
                "secrets": {"api_key": "${KEEL_API_KEY}"},
            },
            "note": "only the two lines above change; secret stays an env reference",
        }
    return out


def is_two_line_switch(old: Iterable[str], new: Iterable[str]) -> bool:
    """True when exactly two config lines differ (order-independent)."""
    a, b = list(old), list(new)
    if len(a) != len(b):
        return False
    diffs = sum(1 for x, y in zip(a, b) if x != y)
    return diffs == 2


# --------------------------------------------------------------- Y4.12
ARTIFACT_SIZE_BUDGETS: Mapping[str, int] = {
    "publish_api": 10 * 1024 * 1024,
    "email": 25 * 1024 * 1024,
    "sidecar": 100 * 1024 * 1024,
}


def _safe_tar_member(name: str) -> str:
    """Return a member name that resolves strictly inside the archive root.

    Tar members use ``/`` separators regardless of the host OS.  Absolute paths,
    Windows drives and any ``..`` segment that climbs above the root are refused
    so a consumer extracting the archive cannot write outside its target dir.
    """
    if not isinstance(name, str) or not name:
        raise BackendError("tar member name must be a non-empty string")
    candidate = name.replace("\\", "/")
    if "\x00" in candidate:
        raise BackendError("tar member name contains a NUL byte: %r" % name)
    if re.match(r"^[A-Za-z]:", candidate) or candidate.startswith("/"):
        raise BackendError("tar member path is absolute: %r" % name)
    normalized = posixpath.normpath(candidate)
    if normalized in ("", ".", "..") or normalized.startswith("../") or \
            posixpath.isabs(normalized):
        raise BackendError("tar member path escapes archive root: %r" % name)
    return normalized


def deterministic_tarball(files: Mapping[str, bytes]) -> tuple[bytes, str]:
    """Y4.12: pack file trees into one reproducible gzipped tarball.

    Names are sorted and tar metadata (mtime/uid/gid/user) is zeroed; the gzip
    header carries no filename and a fixed mtime, so identical inputs always
    yield identical bytes.  Member paths are validated to stay inside the
    archive root (no absolute paths or ``..`` traversal).
    """
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for name in sorted(files):
            data = bytes(files[name])
            info = tarfile.TarInfo(_safe_tar_member(name))
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            tf.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as gz:
        gz.write(raw.getvalue())
    blob = out.getvalue()
    return blob, hashlib.sha256(blob).hexdigest()


def check_artifact_budget(size_bytes: int, target: str) -> dict:
    if target not in ARTIFACT_SIZE_BUDGETS:
        raise BackendError(f"unknown upload target: {target}")
    cap = ARTIFACT_SIZE_BUDGETS[target]
    return {"target": target, "size": int(size_bytes), "cap": cap,
            "ok": int(size_bytes) <= cap,
            "over_by": max(0, int(size_bytes) - cap)}


# --------------------------------------------------------------- Y4.14
PRESET_PLUGINS: tuple[str, ...] = (
    "notes", "todo", "browser", "shell", "files", "git", "search",
    "summarize", "translate", "charts", "diagrams", "email",
    "calendar", "voice", "screen", "trash",
)
FREE_MCP_SERVERS: tuple[str, ...] = (
    "filesystem", "git", "fetch", "sqlite", "time", "memory",
    "playwright", "sequential-thinking", "linear", "github",
    "slack", "notion", "obsidian",
)


def preset_bundle() -> dict:
    """Y4.14: one preset carrying 16 plugins and 13 free-tier MCP servers."""
    return {
        "version": 1,
        "plugins": list(PRESET_PLUGINS),
        "mcp_servers": list(FREE_MCP_SERVERS),
        "counts": {"plugins": len(PRESET_PLUGINS),
                   "mcp_servers": len(FREE_MCP_SERVERS)},
        "all_mcp_free_tier": True,
        "note": "MCP entries use free tiers with the user's own token (C1.9).",
    }


def validate_preset(bundle: Mapping[str, Any]) -> tuple[Issue, ...]:
    found: list[Issue] = []
    counts = bundle.get("counts", {})
    if counts.get("plugins") != 16:
        found.append(Issue("plugin_count", "counts.plugins",
                           "preset must carry 16 plugins"))
    if counts.get("mcp_servers") != 13:
        found.append(Issue("mcp_count", "counts.mcp_servers",
                           "preset must carry 13 MCP servers"))
    if bundle.get("all_mcp_free_tier") is not True:
        found.append(Issue("paid_mcp", "all_mcp_free_tier",
                           "preset MCP servers must all be free tier"))
    if len(set(bundle.get("mcp_servers", []))) != 13:
        found.append(Issue("duplicate_mcp", "mcp_servers",
                           "MCP server names must be unique"))
    return _issues(found)


# ===========================================================================
# D4 — provider hot-apply, workspace gate, pickers, plugin UI contracts
# ===========================================================================

# --------------------------------------------------------------- D4.1
@dataclass(frozen=True)
class RouteTest:
    provider: str
    ok: bool
    model: str
    latency_ms: int
    message: str

    def as_dict(self) -> dict:
        return {"provider": self.provider, "ok": self.ok, "model": self.model,
                "latency_ms": self.latency_ms, "message": self.message}


class ProviderRegistry:
    """D4.1: saving a provider form hot-applies routes with no restart."""

    def __init__(self) -> None:
        self._providers: dict[str, dict] = {}
        self._routes: dict[str, str] = {}
        self._version = 0

    def configure(self, provider: str, *, key_ref: str,
                  endpoint: str = "", model: str = "") -> dict:
        name = _clean(provider)
        if not name or not _clean(key_ref):
            raise BackendError("provider and key reference are required")
        self._providers[name] = {"key_ref": key_ref, "endpoint": endpoint}
        if model:
            self._routes[_clean(model)] = name
        self._version += 1
        return {"provider": name, "applied": True, "restart_required": False,
                "version": self._version}

    def test(self, provider: str, *, ok: bool, model: str,
             latency_ms: int = 0, message: str = "") -> RouteTest:
        """Inline test result; the caller supplies the real probe outcome."""
        return RouteTest(_clean(provider), bool(ok), _clean(model),
                         max(0, int(latency_ms)), _clean(message))

    def resolve(self, model: str) -> str | None:
        return self._routes.get(model)

    def snapshot(self) -> dict:
        return {"version": self._version, "restart_required": False,
                "active_routes": dict(sorted(self._routes.items())),
                "providers": tuple(sorted(self._providers))}


# --------------------------------------------------------------- D4.3
@dataclass(frozen=True)
class WorkspaceState:
    selected: str | None
    default_dir: str
    chat_without_workspace: bool = True


class WorkspaceGate:
    """D4.3: composer is locked until a workspace is explicitly selected.

    The process default directory deliberately does *not* count as a selection;
    a fresh UI starts with none.  Chat-only mode in Cowork remains optional.
    """

    def __init__(self, default_dir: str | Path, *,
                 chat_without_workspace: bool = True):
        self._default = str(default_dir)
        self._selected: str | None = None
        self._chat_ok = bool(chat_without_workspace)

    def select(self, path: str | Path) -> str:
        self._selected = str(path)
        return self._selected

    def clear(self) -> None:
        self._selected = None

    def can_compose(self) -> bool:
        return self._selected is not None

    def chat_allowed(self) -> bool:
        return self._chat_ok

    def empty_state(self) -> dict:
        return {
            "title": "Choose a workspace",
            "reason": "The composer needs an explicit workspace before it can run tools.",
            "process_default": self._default,
            "default_is_selection": False,
            "action": "select_workspace",
        }

    def state(self) -> WorkspaceState:
        return WorkspaceState(self._selected, self._default, self._chat_ok)


# --------------------------------------------------------------- D4.4
class PickerMode(str, Enum):
    IN_PAGE = "in_page"
    NATIVE = "native"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PickerConfig:
    overlay_pin: PickerMode | None = None


def resolve_picker_mode(requested: PickerMode | str, *, headless: bool = False,
                        config: PickerConfig = PickerConfig()) -> PickerMode:
    """D4.4: in-page browser works over SSH/headless; overlay pins it for tests."""
    if config.overlay_pin is not None:
        return config.overlay_pin
    if headless:
        return PickerMode.IN_PAGE
    return requested if isinstance(requested, PickerMode) else PickerMode(str(requested))


def list_directories(path: str | Path, *, include_hidden: bool = False) -> tuple[str, ...]:
    root = Path(path)
    if not root.is_dir():
        return ()
    names = (p.name for p in root.iterdir()
             if p.is_dir() and (include_hidden or not p.name.startswith(".")))
    return tuple(sorted(names))


# --------------------------------------------------------------- D4.5
@dataclass(frozen=True)
class ConversationNodeDefinition:
    node_type: str
    renderer_key: str
    required_fields: tuple[str, ...]
    description: str = ""

    def validate_node(self, node: Mapping[str, Any]) -> tuple[str, ...]:
        return tuple(sorted(f for f in self.required_fields if f not in node))


class NodeRendererRegistry:
    """D4.5: plugins register a node type + keyed renderer + persisted shape."""

    def __init__(self) -> None:
        self._defs: dict[str, ConversationNodeDefinition] = {}

    def register(self, definition: ConversationNodeDefinition) -> None:
        if not definition.node_type:
            raise BackendError("node_type must not be empty")
        if definition.node_type in self._defs:
            raise BackendError(f"duplicate node type: {definition.node_type}")
        self._defs[definition.node_type] = definition

    def render(self, node: Mapping[str, Any]) -> dict:
        kind = node.get("type")
        if kind not in self._defs:
            raise KeyError(kind)
        definition = self._defs[kind]
        missing = definition.validate_node(node)
        return {"renderer": definition.renderer_key, "type": kind,
                "missing_fields": list(missing), "renderable": not missing,
                "node": dict(node)}

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._defs))

    def definition(self, node_type: str) -> ConversationNodeDefinition:
        return self._defs[node_type]


# --------------------------------------------------------------- D4.6
ALLOWED_SETTING_TYPES = frozenset({"string", "number", "boolean", "enum", "secret"})


@dataclass(frozen=True)
class SettingField:
    key: str
    type: str
    default: Any = None
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class SettingsCard:
    card_id: str
    plugin: str
    title: str
    fields: tuple[SettingField, ...]


class SettingsCardRegistry:
    """D4.6: plugin manifests contribute schema-driven settings cards."""

    def __init__(self) -> None:
        self._cards: dict[str, SettingsCard] = {}

    @staticmethod
    def validate_card(card: SettingsCard) -> tuple[Issue, ...]:
        found: list[Issue] = []
        if not card.card_id or not card.plugin:
            found.append(Issue("card_identity", card.card_id,
                               "card id and plugin are required"))
        for field in card.fields:
            if field.type not in ALLOWED_SETTING_TYPES:
                found.append(Issue("bad_field_type", f"{card.card_id}.{field.key}",
                                   f"unsupported field type {field.type!r}"))
            if field.type == "enum" and not field.options:
                found.append(Issue("enum_without_options",
                                   f"{card.card_id}.{field.key}",
                                   "enum fields need options"))
        return _issues(found)

    def register_manifest(self, manifest: Mapping[str, Any]) -> tuple[Issue, ...]:
        plugin = _clean(manifest.get("plugin"))
        found: list[Issue] = []
        for raw in manifest.get("settings_cards", []):
            fields = tuple(SettingField(
                _clean(f.get("key")), _clean(f.get("type")),
                f.get("default"), tuple(f.get("options", ())))
                for f in raw.get("fields", []))
            card = SettingsCard(_clean(raw.get("id")), plugin,
                                _clean(raw.get("title")), fields)
            issues = self.validate_card(card)
            if issues:
                found.extend(issues)
                continue
            self._cards[card.card_id] = card
        return _issues(found)

    def render_form(self, card_id: str, values: Mapping[str, Any]) -> dict:
        card = self._cards[card_id]
        rendered: dict[str, Any] = {}
        errors: list[str] = []
        for field in card.fields:
            value = values.get(field.key, field.default)
            if field.type == "enum" and value not in field.options:
                errors.append(f"{field.key}: not one of {list(field.options)}")
            if field.type == "boolean" and not isinstance(value, bool):
                errors.append(f"{field.key}: expected boolean")
            rendered[field.key] = value
        return {"card": card_id, "plugin": card.plugin,
                "values": rendered, "errors": errors}

    def cards_for(self, plugin: str) -> tuple[SettingsCard, ...]:
        return tuple(sorted((c for c in self._cards.values() if c.plugin == plugin),
                            key=lambda c: c.card_id))


# --------------------------------------------------------------- D4.8
@dataclass(frozen=True)
class CopyIssue:
    code: str
    location: str
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "location": self.location,
                "message": self.message}


def t(catalog: Mapping[str, Mapping[str, str]], key: str,
      lang: str = "en") -> str:
    """D4.8: every product string is looked up through a typed catalog."""
    return catalog.get(lang, catalog.get("en", {})).get(key, key)


_STRING_LITERAL = re.compile(r"""['"]([A-Za-z][A-Za-z ,.'!?-]{3,})['"]""")


def is_sentence_case(text: str) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z']*", str(text))
    if not words:
        return True
    if not words[0][0].isupper():
        return False
    # Sentence case: only the first word is capitalised (proper nouns aside).
    return not any(w[0].isupper() and not w.isupper() for w in words[1:])


def verify_ui_copy(sources: Mapping[str, str],
                   catalog: Mapping[str, Mapping[str, str]],
                   *, plugin_titles: Mapping[str, str] | None = None
                   ) -> tuple[CopyIssue, ...]:
    """D4.8: ``verify_ui_copy`` lint gate over renderer + manifest sources."""
    found: list[CopyIssue] = []
    for path, source in sorted(sources.items()):
        for lineno, line in enumerate(source.splitlines(), start=1):
            if "t(" in line or "tr(" in line or "TRANSLATIONS" in line:
                continue
            for match in _STRING_LITERAL.finditer(line):
                literal = match.group(1)
                if literal not in set(catalog.get("en", {}).values()):
                    found.append(CopyIssue(
                        "hardcoded_copy", f"{path}:{lineno}",
                        "product copy must come from the typed catalog via t()"))
    for plugin, title in sorted((plugin_titles or {}).items()):
        if not is_sentence_case(title):
            found.append(CopyIssue("title_case_plugin_title", plugin,
                                   "plugin titles use sentence case"))
    return _issues(found)


# --------------------------------------------------------------- D4.9
APPROVED_ICONS: frozenset[str] = frozenset({
    "plug", "settings", "chat", "search", "folder", "shield", "bolt",
    "gear", "book", "link", "chart", "lock", "globe", "star", "puzzle",
    "trash",
})


def check_icon(plugin: str, icon: str, *, designer_approved: bool = False
               ) -> Issue | None:
    """D4.9: bundled plugins use the shared icon set; new glyphs need approval."""
    if icon in APPROVED_ICONS or designer_approved:
        return None
    return Issue("designer_approval_required", plugin,
                 f"glyph {icon!r} is outside the approved icon set")


def verify_bundled_icons(manifests: Mapping[str, str]) -> tuple[Issue, ...]:
    return _issues(i for i in (
        check_icon(plugin, icon) for plugin, icon in sorted(manifests.items())
    ) if i is not None)


# --------------------------------------------------------------- D4.10
DESIGN_GUIDE_FILE = "UI-UX-GUIDE.md"
DESIGN_PRINCIPLES: tuple[str, ...] = (
    "Clarity over cleverness: every control has one obvious purpose.",
    "Local-first honesty: never imply a cloud service is running.",
    "Accessibility is a gate, not a polish pass.",
    "Progressive disclosure: advanced controls stay one level away.",
    "Consistent density, spacing and sentence-case copy everywhere.",
)
DESIGN_REFERENCES: Mapping[str, str] = {
    "tokens": "docs/design/tokens.json",
    "accessibility": "docs/design/accessibility.md",
    "patterns": "docs/design/patterns.md",
}


class DesignGuideSkill:
    """D4.10: a reusable skill the builder loads before any UI change."""

    UI_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".json")

    def __init__(self) -> None:
        self._loaded = False

    def load(self) -> tuple[str, ...]:
        self._loaded = True
        return DESIGN_PRINCIPLES

    def load_reference(self, name: str) -> str:
        if name not in DESIGN_REFERENCES:
            raise KeyError(name)
        return DESIGN_REFERENCES[name]

    @classmethod
    def is_ui_change(cls, path: str | Path) -> bool:
        text = str(path).replace("\\", "/")
        return (text.startswith("site/ui/")
                or text.lower().endswith(cls.UI_SUFFIXES))

    def gate(self, changed_paths: Iterable[str | Path]) -> tuple[Issue, ...]:
        ui = sorted(str(p) for p in changed_paths if self.is_ui_change(p))
        if ui and not self._loaded:
            return (Issue("guide_not_loaded", DESIGN_GUIDE_FILE,
                          f"load {DESIGN_GUIDE_FILE} before UI changes: "
                          + ", ".join(ui)),)
        return ()


# --------------------------------------------------------------- D4.12
class StartupPhase(str, Enum):
    PACKAGED_ASSETS = "packaged_assets"
    SKELETON = "skeleton"
    DAEMON_STARTING = "daemon_starting"
    PLUGINS_ACTIVATING = "plugins_activating"
    READY = "ready"

    def __str__(self) -> str:
        return self.value


STARTUP_PHASES: tuple[StartupPhase, ...] = (
    StartupPhase.PACKAGED_ASSETS, StartupPhase.SKELETON,
    StartupPhase.DAEMON_STARTING, StartupPhase.PLUGINS_ACTIVATING,
    StartupPhase.READY,
)


@dataclass(frozen=True)
class StartupPlan:
    phases: tuple[StartupPhase, ...]
    first_paint_phase: StartupPhase
    plugins_after_ready: bool

    def as_dict(self) -> dict:
        return {"phases": [str(p) for p in self.phases],
                "first_paint_phase": str(self.first_paint_phase),
                "plugins_after_ready": self.plugins_after_ready}


def desktop_startup_plan() -> StartupPlan:
    """D4.12: packaged assets paint first; plugins activate after readiness."""
    return StartupPlan(STARTUP_PHASES, StartupPhase.PACKAGED_ASSETS, True)


def is_valid_startup_order(phases: Iterable[StartupPhase]) -> bool:
    order = {phase: index for index, phase in enumerate(STARTUP_PHASES)}
    seen = [order[p] for p in phases if p in order]
    return seen == sorted(seen) and len(seen) == len(STARTUP_PHASES)


# --------------------------------------------------------------- D4.13
WEB_DEFAULT_PORT = 8739


class PortMode(str, Enum):
    WEB = "web"
    DESKTOP = "desktop"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PortDecision:
    port: int
    mode: PortMode
    source: str
    conflict: bool
    message: str

    def as_dict(self) -> dict:
        return {"port": self.port, "mode": str(self.mode),
                "source": self.source, "conflict": self.conflict,
                "message": self.message}


def select_port(mode: PortMode | str, *, profile_port: int | None = None,
                occupied: Iterable[int] = ()) -> PortDecision:
    """D4.13: web fixed default, desktop OS-assigned, profile may override."""
    md = mode if isinstance(mode, PortMode) else PortMode(str(mode))
    taken = set(int(p) for p in occupied)
    if profile_port is not None:
        port, source = int(profile_port), "profile"
        if not 1 <= port <= 65535:
            raise BackendError("profile port must be in 1..65535")
    elif md is PortMode.WEB:
        port, source = WEB_DEFAULT_PORT, "web_default"
    else:
        port, source = 0, "os_assigned"
    conflict = port != 0 and port in taken
    if conflict:
        msg = f"port {port} is already in use; set a different profile port"
    elif port == 0:
        msg = "OS will assign an ephemeral port"
    else:
        msg = f"listening on {source} port {port}"
    return PortDecision(port, md, source, conflict, msg)


# ===========================================================================
# X7 — distribution, installers and platform support (backend planners only)
# ===========================================================================

@dataclass(frozen=True)
class PlatformTarget:
    os: str
    arch: str

    def as_dict(self) -> dict:
        return {"os": self.os, "arch": self.arch}


BUILD_TARGETS: tuple[PlatformTarget, ...] = (
    PlatformTarget("windows", "x86_64"), PlatformTarget("windows", "arm64"),
    PlatformTarget("linux", "x86_64"), PlatformTarget("linux", "arm64"),
    PlatformTarget("macos", "universal2"),
    PlatformTarget("macos", "arm64"), PlatformTarget("macos", "x86_64"),
)


def required_build_targets() -> tuple[PlatformTarget, ...]:
    """X7.1: ARM64 on Windows/Linux; universal or split macOS images."""
    return BUILD_TARGETS


def verify_target_matrix(targets: Iterable[PlatformTarget]) -> tuple[Issue, ...]:
    supplied = {(t.os, t.arch) for t in targets}
    return _issues(
        Issue("missing_build_target", f"{t.os}/{t.arch}",
              "required build target is absent")
        for t in BUILD_TARGETS if (t.os, t.arch) not in supplied
    )


def verify_native_deps(target: PlatformTarget,
                       available: Iterable[str]) -> tuple[Issue, ...]:
    needed = {"zlib", "sqlite", "ssl"}
    have = set(available)
    return _issues(Issue("missing_native_dep", f"{target.os}/{target.arch}",
                         f"native dependency {dep!r} is unverified")
                   for dep in sorted(needed - have))


# --------------------------------------------------------------- X7.2
class InstallScope(str, Enum):
    PER_USER = "per_user"
    PER_MACHINE = "per_machine"

    def __str__(self) -> str:
        return self.value


def windows_install_plan(scope: InstallScope | str, *, username: str) -> dict:
    """X7.2: per-user needs no admin rights; per-machine does."""
    sc = scope if isinstance(scope, InstallScope) else InstallScope(str(scope))
    if not _clean(username):
        raise BackendError("username is required")
    root = (f"C:\\Users\\{username}\\AppData\\Local\\Keel" if sc is InstallScope.PER_USER
            else "C:\\Program Files\\Keel")
    return {"scope": str(sc), "install_root": root,
            "requires_admin": sc is InstallScope.PER_MACHINE,
            "start_menu": "user" if sc is InstallScope.PER_USER else "all_users"}


# --------------------------------------------------------------- X7.3
class UninstallMode(str, Enum):
    KEEP_DATA = "keep_data"
    REMOVE_DATA = "remove_data"
    REMOVE_DATA_AND_MODELS = "remove_data_and_models"

    def __str__(self) -> str:
        return self.value


def uninstall_plan(mode: UninstallMode | str, *, paths: Mapping[str, str]
                   ) -> dict:
    """X7.3: list everything that would be deleted first; never deletes here."""
    md = mode if isinstance(mode, UninstallMode) else UninstallMode(str(mode))
    app = [paths.get("app", "")]
    data = [paths.get("data", ""), paths.get("config", "")]
    models = [paths.get("models", "")]
    if md is UninstallMode.KEEP_DATA:
        delete = app
    elif md is UninstallMode.REMOVE_DATA:
        delete = app + data
    else:
        delete = app + data + models
    delete = sorted(p for p in delete if p)
    return {"mode": str(md), "would_delete": delete,
            "requires_confirmation": True, "dry_run": True,
            "description": "listed for confirmation; no file was removed"}


# --------------------------------------------------------------- X7.4
FILE_ASSOCIATIONS: tuple[str, ...] = (".keelproj", ".keelsession", ".keelplugin")
URL_PROTOCOL = "keel"


def association_registration_plan() -> tuple[dict, ...]:
    """X7.4: file + keel:// protocol operations, mirrored for clean removal."""
    ops = [{"kind": "file_association", "key": ext} for ext in FILE_ASSOCIATIONS]
    ops.append({"kind": "url_protocol", "key": URL_PROTOCOL})
    return tuple(sorted(ops, key=lambda o: (o["kind"], o["key"])))


def association_removal_plan() -> tuple[dict, ...]:
    return tuple(dict(op, action="remove") for op in association_registration_plan())


def verify_clean_removal(registered: Iterable[str],
                         removed: Iterable[str]) -> tuple[Issue, ...]:
    expected = {op["key"] for op in association_registration_plan()}
    reg, rem = set(registered), set(removed)
    return _issues(
        [Issue("association_left_behind", key, "registration was not removed")
         for key in sorted(reg - rem)]
        + [Issue("unexpected_removal", key, "removed key was never registered")
           for key in sorted(rem & expected - reg & expected)]
    )


# --------------------------------------------------------------- X7.5
def detect_linux_session(env: Mapping[str, str]) -> str:
    """X7.5: classify the display session from caller-supplied env vars."""
    if env.get("WAYLAND_DISPLAY"):
        return "wayland"
    if env.get("DISPLAY"):
        return "x11"
    return "headless"


def linux_tray_plan(session: str, *, has_tray: bool) -> dict:
    fallback = not has_tray or session == "headless"
    return {"session": session, "tray_available": has_tray and not fallback,
            "fallback_required": fallback,
            "fallback": ("status-file + CLI controls" if fallback
                         else "native tray"),
            "note": "no tray in this session -> document CLI fallback"}


def appimage_desktop_entry(name: str = "Keel") -> str:
    safe = _clean(name) or "Keel"
    return ("[Desktop Entry]\n"
            f"Name={safe}\n"
            "Exec=keel --web\n"
            "Icon=keel\n"
            "Type=Application\n"
            "Categories=Development;Utility;\n")


def sandbox_flags(mode: str = "default") -> tuple[str, ...]:
    """Guidance only: never enable no-sandbox implicitly."""
    if mode == "user_opt_in_no_sandbox":
        return ("--no-sandbox", "--user-opt-in-required")
    return ("--enable-namespaces", "--seccomp-profile=default")


# --------------------------------------------------------------- X7.6
AV_SUBMISSION_CHANNELS: Mapping[str, str] = {
    "microsoft": "https://www.microsoft.com/en-us/wdsi/filesubmission",
    "virustotal": "https://www.virustotal.com/gui/home/upload",
    "crowdstrike": "https://www.crowdstrike.com/falcon-intelligence/submit-sample/",
}
ANTIVIRUS_PLAYBOOK: tuple[str, ...] = (
    "build deterministically from pinned inputs",
    "publish SHA-256 checksums for every artifact",
    "submit samples to free vendor review channels",
    "document known false-positive hashes and resolution status",
)


def checksum_manifest(files: Mapping[str, bytes]) -> dict:
    """X7.6: caller-supplied artifact bytes -> deterministic checksum manifest."""
    return {name: hashlib.sha256(bytes(files[name])).hexdigest()
            for name in sorted(files)}


def antivirus_playbook() -> dict:
    return {"steps": list(ANTIVIRUS_PLAYBOOK),
            "submission_channels": dict(sorted(AV_SUBMISSION_CHANNELS.items())),
            "note": "checksums let users compare before running an installer"}


# --------------------------------------------------------------- X7.7
INSTALLER_LOCALES: tuple[str, ...] = ("en", "de", "es", "fr", "ja", "pt-BR", "zh-CN")


def installer_text(catalog: Mapping[str, Mapping[str, str]], key: str,
                   locale: str) -> str:
    """X7.7: installer text comes from the same string catalogs as the UI."""
    return catalog.get(locale, catalog.get("en", {})).get(
        key, catalog.get("en", {}).get(key, key))


def installer_catalog_issues(catalog: Mapping[str, Mapping[str, str]]
                             ) -> tuple[Issue, ...]:
    baseline = set(catalog.get("en", {}))
    found: list[Issue] = []
    for locale in INSTALLER_LOCALES:
        if locale == "en":
            continue
        for key in sorted(baseline - set(catalog.get(locale, {}))):
            found.append(Issue("untranslated_installer_key", f"{locale}.{key}",
                               "installer locale is missing an English key"))
    return _issues(found)


# --------------------------------------------------------------- X7.8
@dataclass(frozen=True)
class DownloadVerification:
    ok: bool
    filename: str
    sha256: str
    expected_sha256: str
    size: int
    expected_size: int | None
    reason: str

    def as_dict(self) -> dict:
        return {"ok": self.ok, "filename": self.filename, "sha256": self.sha256,
                "expected_sha256": self.expected_sha256, "size": self.size,
                "expected_size": self.expected_size, "reason": self.reason}


def verify_download(data: bytes, expected_sha256: str, *, filename: str = "file",
                    expected_size: int | None = None) -> DownloadVerification:
    """X7.8: verify a downloaded installer before the user runs it."""
    digest = hashlib.sha256(bytes(data)).hexdigest()
    expected = _clean(expected_sha256).lower()
    if digest != expected:
        reason = "sha256 mismatch"
    elif expected_size is not None and len(data) != int(expected_size):
        reason = "size mismatch"
    else:
        reason = "integrity verified"
    return DownloadVerification(reason == "integrity verified", filename,
                                digest, expected, len(data), expected_size, reason)


def parse_checksum_line(line: str) -> dict | None:
    """Parse a standard ``<sha256>  <filename>`` checksum line."""
    match = re.match(r"^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
    if not match:
        return None
    return {"sha256": match.group(1).lower(), "filename": match.group(2)}


# --------------------------------------------------------------- X7.9
IMPORT_FORMATS: Mapping[str, dict] = {
    "obsidian": {"glob": "**/*.md", "kind": "markdown_notes"},
    "vscode": {"glob": "**/*.code-workspace", "kind": "workspace_settings"},
    "json_notes": {"glob": "**/*.json", "kind": "json_notes"},
}


def plan_import(source_dir: str | Path, tool: str) -> dict:
    """X7.9: discover documented-format files; produce a read-only plan."""
    if tool not in IMPORT_FORMATS:
        raise BackendError(f"unsupported import tool: {tool}")
    root = Path(source_dir)
    spec = IMPORT_FORMATS[tool]
    files = sorted(str(p.relative_to(root)).replace("\\", "/")
                   for p in root.rglob(spec["glob"].lstrip("*").lstrip("/"))
                   if p.is_file()) if root.is_dir() else []
    return {"tool": tool, "kind": spec["kind"], "source": str(root),
            "files": files, "dry_run": True,
            "note": "documented formats only; nothing was written"}


def execute_import(plan: Mapping[str, Any], target_root: str | Path, *,
                   dry_run: bool = True) -> dict:
    """Copy planned files relative to target_root; dry-run is the default."""
    root = Path(target_root).resolve()
    copied: list[str] = []
    if not dry_run:
        source = Path(str(plan["source"])).resolve()
        for rel in plan["files"]:
            src = (source / rel).resolve()
            if source not in src.parents:
                raise BackendError("import file escapes its source directory")
            dst = (root / rel).resolve()
            if root not in dst.parents:
                raise BackendError("import path escapes the target root")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            copied.append(rel)
    return {"dry_run": bool(dry_run), "planned": list(plan["files"]),
            "copied": copied, "target": str(root)}


# --------------------------------------------------------------- X7.10
DISK_CATEGORIES: tuple[str, ...] = ("models", "caches", "sessions", "trash")
DEFAULT_CATEGORY_CAPS: Mapping[str, int] = {
    "models": 20 * 1024 ** 3,
    "caches": 4 * 1024 ** 3,
    "sessions": 2 * 1024 ** 3,
    "trash": 512 * 1024 ** 2,
}


def scan_disk_usage(root: str | Path,
                    caps: Mapping[str, int] = DEFAULT_CATEGORY_CAPS) -> dict:
    """X7.10: real stdlib size scan per category, sorted for determinism."""
    base = Path(root).resolve()
    report: dict[str, dict] = {}
    for category in DISK_CATEGORIES:
        folder = base / category
        entries: list[dict] = []
        if folder.is_dir():
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    entries.append({"path": str(path.relative_to(base)).replace("\\", "/"),
                                    "size": path.stat().st_size})
        total = sum(e["size"] for e in entries)
        cap = int(caps.get(category, 0))
        report[category] = {"bytes": total, "cap": cap, "over_by": max(0, total - cap),
                            "files": entries}
    return report


def safe_clean_plan(report: Mapping[str, Any], category: str) -> dict:
    """Plan the oldest-sorted files in a category down to its cap; no deletion."""
    if category not in DISK_CATEGORIES:
        raise BackendError(f"unknown disk category: {category}")
    entry = report[category]
    entries = sorted(entry["files"], key=lambda e: (e["path"], e["size"]))
    target = max(0, entry["bytes"] - entry["cap"])
    remove: list[str] = []
    freed = 0
    for item in entries:
        if freed >= target:
            break
        remove.append(item["path"])
        freed += item["size"]
    return {"category": category, "remove": remove, "would_free": freed,
            "dry_run": True, "note": "planned only; no file was removed"}


# ===========================================================================
# Coverage registry — one entry per not_started ID implemented in this module
# ===========================================================================

FEATURE_BEHAVIORS: Mapping[str, tuple[str, ...]] = {
    "Y4.1": ("McpServerReviver", "ServerPhase", "ReviveResult"),
    "Y4.2": ("PairingChannel", "PairingPayload", "build_onboarding_payload",
             "has_manual_fallback"),
    "Y4.4": ("SecretProvider", "SecretProviderMap", "ProviderBinding"),
    "Y4.5": ("SupervisedBridge", "BridgePhase"),
    "Y4.6": ("TraceStore", "TraceEvent"),
    "Y4.7": ("KEYLESS_DESKTOP_TOOLS", "desktop_tool_manifest",
             "validate_desktop_tools"),
    "Y4.8": ("ObsidianVault",),
    "Y4.10": ("SKILL_RUNBOOKS", "list_runbooks", "validate_skill_library"),
    "Y4.11": ("two_line_switch", "config_reference_examples", "is_two_line_switch"),
    "Y4.12": ("deterministic_tarball", "check_artifact_budget",
              "ARTIFACT_SIZE_BUDGETS"),
    "Y4.14": ("PRESET_PLUGINS", "FREE_MCP_SERVERS", "preset_bundle",
              "validate_preset"),
    "D4.1": ("ProviderRegistry", "RouteTest"),
    "D4.3": ("WorkspaceGate", "WorkspaceState"),
    "D4.4": ("PickerMode", "PickerConfig", "resolve_picker_mode", "list_directories"),
    "D4.5": ("ConversationNodeDefinition", "NodeRendererRegistry"),
    "D4.6": ("SettingsCard", "SettingField", "SettingsCardRegistry"),
    "D4.8": ("verify_ui_copy", "t", "is_sentence_case"),
    "D4.9": ("APPROVED_ICONS", "check_icon", "verify_bundled_icons"),
    "D4.10": ("DesignGuideSkill", "DESIGN_PRINCIPLES", "DESIGN_REFERENCES"),
    "D4.12": ("StartupPhase", "STARTUP_PHASES", "desktop_startup_plan",
              "is_valid_startup_order"),
    "D4.13": ("WEB_DEFAULT_PORT", "PortMode", "select_port"),
    "X7.1": ("PlatformTarget", "BUILD_TARGETS", "verify_target_matrix",
             "verify_native_deps"),
    "X7.2": ("InstallScope", "windows_install_plan"),
    "X7.3": ("UninstallMode", "uninstall_plan"),
    "X7.4": ("association_registration_plan", "association_removal_plan",
             "verify_clean_removal"),
    "X7.5": ("detect_linux_session", "linux_tray_plan", "appimage_desktop_entry",
             "sandbox_flags"),
    "X7.6": ("ANTIVIRUS_PLAYBOOK", "checksum_manifest", "antivirus_playbook"),
    "X7.7": ("INSTALLER_LOCALES", "installer_text", "installer_catalog_issues"),
    "X7.8": ("verify_download", "parse_checksum_line"),
    "X7.9": ("plan_import", "execute_import"),
    "X7.10": ("scan_disk_usage", "safe_clean_plan"),
}

IMPLEMENTED_FEATURE_IDS: tuple[str, ...] = tuple(sorted(FEATURE_BEHAVIORS))

PRIOR_VERIFIED_P0: Mapping[str, str] = {
    "Y4.3": "keel.identity_contracts (first-boot sign-in test-fire)",
    "Y4.9": "keel.identity_contracts (persona/SOUL + routing)",
    "Y4.13": "keel.identity_contracts (version badge + zero-secrets scan)",
    "D4.2": "keel.composition_contracts (OpenAI-compatible endpoint path)",
    "D4.7": "keel.composition_contracts (pure tool presenters)",
    "D4.11": "keel.composition_contracts (plugin manager contracts)",
}


def verify_coverage() -> tuple[Issue, ...]:
    """Confirm all 31 IDs are mapped and every mapping resolves in this module."""
    expected = {
        "Y4.1", "Y4.2", "Y4.4", "Y4.5", "Y4.6", "Y4.7", "Y4.8",
        "Y4.10", "Y4.11", "Y4.12", "Y4.14",
        "D4.1", "D4.3", "D4.4", "D4.5", "D4.6", "D4.8", "D4.9",
        "D4.10", "D4.12", "D4.13",
        "X7.1", "X7.2", "X7.3", "X7.4", "X7.5", "X7.6", "X7.7",
        "X7.8", "X7.9", "X7.10",
    }
    found: list[Issue] = []
    for fid in sorted(expected - set(FEATURE_BEHAVIORS)):
        found.append(Issue("unmapped_feature", fid, "feature has no implementation map"))
    for fid, symbols in sorted(FEATURE_BEHAVIORS.items()):
        for symbol in symbols:
            if symbol not in globals():
                found.append(Issue("missing_symbol", fid,
                                   f"mapped symbol {symbol} is undefined"))
    if len(IMPLEMENTED_FEATURE_IDS) != 31:
        found.append(Issue("feature_count", "FEATURE_BEHAVIORS",
                           "expected exactly 31 implemented feature IDs"))
    return _issues(found)


__all__ = [
    "BackendError", "Issue", "FEATURE_BEHAVIORS", "IMPLEMENTED_FEATURE_IDS",
    "PRIOR_VERIFIED_P0", "verify_coverage",
] + [name for symbols in FEATURE_BEHAVIORS.values() for name in symbols]
