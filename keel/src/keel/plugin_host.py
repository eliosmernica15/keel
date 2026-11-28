"""Local plugin host: manifest parsing, trust gating and subprocess isolation.

This is a **local** plugin host, not a marketplace and not a sandbox in the
strong sense.  It deliberately claims only what it actually enforces:

* Claude-compatible ``.claude-plugin/plugin.json`` *subset* plus the Keel-local
  ``capabilities`` / ``permissions`` fields.  Skills, agents, hooks and MCP
  server declarations are parsed and described, never activated by this host.
* Plugins are discovered under a configurable directory **inside the Keel
  state root**.  Discovery only reads manifests; it never imports, evaluates,
  executes or auto-enables plugin code.
* Every plugin is disabled until an explicit ``enable(name)`` call.  Invalid,
  quarantined and disabled plugins cannot be invoked.
* ``invoke()`` runs a *declared* command as a child process with ``shell=False``
  and an argv list, cwd pinned to the plugin directory, an environment allowlist
  (no inherited secrets), a bounded timeout and bounded stdout/stderr.  On
  timeout the whole process tree is terminated best-effort (taskkill /T /F on
  Windows, process-group kill on POSIX).  Plugin code never runs in the app
  process.

Limitations, stated honestly:

* This is **process isolation with resource caps**, not a WASM VM and not a
  kernel sandbox.  A plugin process has the OS privileges of the user running
  Keel: it can open files, talk to the network and spawn children until the
  timeout fires.  Do not enable plugins you do not trust.
* There is no signature verification, supply-chain scanning, hosted registry,
  auto-update or remote install.  ``install()`` copies from a local directory
  only, refuses to overwrite silently, and is idempotent for identical content.
* Environment allowlisting, output caps and argv-only execution reduce accidental
  leakage and shell-injection risk; they are not a data-flow confinement system.
  A plugin can still read allowlisted environment values (for example PATH).
* Process-tree termination is best-effort: a grandchild that deliberately
  detaches from its process group may outlive the parent.  Readers stop retaining
  output after the cap but keep draining so a chatty child cannot block.
* Audit records are redacted by key name and common credential patterns, and
  never contain environment *values* or JSON argument *values*.  Redaction is
  heuristic, not a proof.
* The state and audit files are updated with atomic temp-file + replace writes
  under a per-host lock; cross-process concurrent writers are not coordinated.

No third-party imports; this module is stdlib-only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_RELATIVE_PATH = Path(".claude-plugin") / "plugin.json"
PLUGINS_DIRNAME = "plugins"
STATE_FILENAME = "plugins-state.json"
AUDIT_FILENAME = "plugins-audit.jsonl"
QUARANTINE_DIRNAME = ".quarantine"

# ``python`` is the only alias resolved to a host executable.  Every other
# token must be a relative path *inside* the plugin directory.
PYTHON_ALIAS = "python"

DEFAULT_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
    "HOME", "USERPROFILE", "LANG", "LC_ALL", "TZ",
)

FORBIDDEN_CAPABILITIES: frozenset[str] = frozenset({
    "exec", "execute", "shell", "spawn", "process_control", "network",
    "write", "patch", "irreversible", "sampling", "elicitation", "roots",
})

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SAFE_TOKEN_RE = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_VERSION_RE = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_SECRET_KEY_RE = re.compile(
    r"(?i)(secret|password|passwd|token|credential|api[_-]?key|"
    r"access[_-]?key|private[_-]?key|authorization|auth[_-]?header|"
    r"cookie|session[_-]?key)")
_SECRET_VALUE_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|"
    r"xox[baprs]-[A-Za-z0-9\-]{8,}|AKIA[0-9A-Z]{12,}|Bearer\s+\S+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)")
_REDACTED = "<redacted>"

MAX_MANIFEST_BYTES = 1_000_000
MAX_AUDIT_EVENTS = 1000


# ---------------------------------------------------------------------------
# typed errors
# ---------------------------------------------------------------------------


class PluginHostError(RuntimeError):
    """Base error carrying a stable, log-safe ``code``."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(f"[{code}] {message or code}")


class ManifestError(PluginHostError):
    """The plugin manifest is missing, malformed or requests forbidden things."""


class UnsafePathError(PluginHostError):
    """A path/name escaped its root, used ``..``/absolute form or a symlink."""


class PluginNotFound(PluginHostError):
    """No such installed plugin."""


class PluginDisabled(PluginHostError):
    """The plugin exists but was never explicitly enabled."""


class PluginInvalid(PluginHostError):
    """The plugin failed validation and cannot be enabled or invoked."""


class PluginQuarantined(PluginHostError):
    """The plugin was quarantined and cannot be invoked."""


class DuplicatePlugin(PluginHostError):
    """A different plugin with the same name is already installed."""


class InvocationError(PluginHostError):
    """The declared command could not be started or resolved safely."""


class PluginState(str, Enum):
    DISABLED = "disabled"
    ENABLED = "enabled"
    INVALID = "invalid"
    QUARANTINED = "quarantined"


# ---------------------------------------------------------------------------
# descriptors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PluginCommand:
    """One declared, argv-only command.  No shell string is ever accepted."""

    name: str
    argv: tuple[str, ...]
    description: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "argv": list(self.argv),
                "description": self.description}


@dataclass(frozen=True)
class PluginManifest:
    """Validated inert manifest data.  Parsing performs no I/O or execution."""

    name: str
    version: str
    description: str = ""
    author: str = ""
    commands: tuple[PluginCommand, ...] = ()
    skills: tuple[str, ...] = ()
    agents: tuple[str, ...] = ()
    hooks: tuple[tuple[str, str], ...] = ()
    mcp_servers: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "name": self.name, "version": self.version,
            "description": self.description, "author": self.author,
            "commands": [c.to_dict() for c in self.commands],
            "skills": list(self.skills), "agents": list(self.agents),
            "hooks": [{"event": event, "path": path}
                      for event, path in self.hooks],
            "mcp_servers": list(self.mcp_servers),
            "capabilities": list(self.capabilities),
            "permissions": list(self.permissions),
        }


# ---------------------------------------------------------------------------
# validation helpers
# ---------------------------------------------------------------------------


def _safe_name(value: Any, label: str = "name") -> str:
    if not isinstance(value, str) or not _SAFE_NAME_RE.fullmatch(value) \
            or ".." in value:
        raise UnsafePathError(f"unsafe_{label}")
    return value


def _safe_rel(value: Any, label: str) -> str:
    """Validate a textual relative path without touching the filesystem."""
    if not isinstance(value, str) or not value or len(value) > 512:
        raise UnsafePathError(f"unsafe_{label}")
    if value.startswith(("/", "\\")) or os.path.isabs(value) \
            or re.match(r"^[A-Za-z]:", value):
        raise UnsafePathError(f"unsafe_{label}")
    parts = PurePosixPath(value.replace("\\", "/")).parts
    if not parts or ".." in parts:
        raise UnsafePathError(f"unsafe_{label}")
    cleaned = "/".join(p for p in parts if p != ".")
    if not cleaned:
        raise UnsafePathError(f"unsafe_{label}")
    return cleaned


def _contained(root: Path, candidate: Path, label: str) -> Path:
    """Require *candidate* to resolve strictly inside *root*, without symlinks."""
    root_r = root.resolve()
    candidate_r = candidate.resolve()
    try:
        relative = candidate_r.relative_to(root_r)
    except ValueError:
        raise UnsafePathError(f"{label}_escapes_root") from None
    if not relative.parts:
        raise UnsafePathError(f"{label}_is_root")
    # Textual walk: a symlink inside the root that still resolves inside must
    # also fail closed.  ``resolve()`` above covers symlinks escaping the root.
    try:
        text_rel = Path(os.path.relpath(candidate, root))
    except ValueError:
        raise UnsafePathError(f"{label}_escapes_root") from None
    cursor = root
    for part in text_rel.parts:
        if part == "..":
            raise UnsafePathError(f"{label}_escapes_root")
        cursor = cursor / part
        if cursor.is_symlink():
            raise UnsafePathError(f"{label}_symlink")
    return candidate_r


def _validate_tree(root: Path) -> None:
    """Reject symlinks anywhere under a plugin root (no escaping file reads)."""
    try:
        for child in root.rglob("*"):
            if child.is_symlink():
                raise UnsafePathError("symlink_in_plugin")
    except OSError:
        raise UnsafePathError("unreadable_plugin_tree") from None


def _text(value: Any, limit: int, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise ManifestError(f"bad_{label}")
    return value


def _safe_tokens(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ManifestError(f"bad_{label}")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _SAFE_TOKEN_RE.fullmatch(item):
            raise ManifestError(f"bad_{label}")
        out.append(item)
    return tuple(out)


def _parse_commands(raw: Any) -> tuple[PluginCommand, ...]:
    if raw is None:
        return ()
    entries: list[tuple[Any, Any, str]] = []
    if isinstance(raw, Mapping):
        for name, spec in raw.items():
            entries.append((name, spec, ""))
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for item in raw:
            if isinstance(item, str):
                entries.append((item, item, ""))
            elif isinstance(item, Mapping):
                entries.append((item.get("name"),
                                item.get("argv", item.get("command")),
                                _text(item.get("description", ""), 500,
                                      "command_description")))
            else:
                raise ManifestError("bad_commands")
    else:
        raise ManifestError("bad_commands")

    commands: list[PluginCommand] = []
    seen: set[str] = set()
    for raw_name, spec, description in entries:
        name = _safe_name(raw_name, "command_name")
        if name in seen:
            raise ManifestError("duplicate_command")
        seen.add(name)
        if isinstance(spec, Mapping):
            spec = spec.get("argv", spec.get("command"))
        if isinstance(spec, str):
            tokens = (spec,)
        elif isinstance(spec, Sequence) and not isinstance(spec, (str, bytes)):
            tokens = tuple(spec)
        else:
            raise ManifestError("bad_command_argv")
        if not tokens or len(tokens) > 64:
            raise ManifestError("bad_command_argv")
        argv: list[str] = []
        for token in tokens:
            if not isinstance(token, str) or len(token) > 512:
                raise ManifestError("bad_command_argv")
            if token != PYTHON_ALIAS:
                token = _safe_rel(token, "command_argv")
            argv.append(token)
        commands.append(PluginCommand(name=name, argv=tuple(argv),
                                      description=description))
    return tuple(commands)


def _parse_paths(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ManifestError(f"bad_{label}")
    return tuple(_safe_rel(item, label) for item in value)


def _parse_hooks(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise ManifestError("bad_hooks")
    hooks: list[tuple[str, str]] = []
    for event, paths in value.items():
        if not isinstance(event, str) \
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", event) \
                or isinstance(paths, (str, bytes)) \
                or not isinstance(paths, Sequence):
            raise ManifestError("bad_hooks")
        for path in paths:
            hooks.append((event, _safe_rel(path, "hook_path")))
    return tuple(hooks)


def _parse_mcp_servers(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise ManifestError("bad_mcp_servers")
    names: list[str] = []
    for name, spec in value.items():
        # Only names are retained: MCP specs can carry credentials and this
        # host never starts them.
        _safe_name(name, "mcp_server_name")
        if not isinstance(spec, Mapping):
            raise ManifestError("bad_mcp_servers")
        names.append(name)
    return tuple(names)


def parse_manifest(data: Any) -> PluginManifest:
    """Parse and validate the supported manifest subset; no execution, no I/O."""
    if not isinstance(data, Mapping):
        raise ManifestError("bad_manifest")
    name = _safe_name(data.get("name"), "plugin_name")
    version = data.get("version")
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise ManifestError("bad_version")
    author = data.get("author", "")
    if isinstance(author, Mapping):
        author = author.get("name", "")
    author = _text(author, 200, "author")
    capabilities = _safe_tokens(data.get("capabilities"), "capabilities")
    if any(c in FORBIDDEN_CAPABILITIES for c in capabilities):
        raise ManifestError("forbidden_capability")
    return PluginManifest(
        name=name, version=version,
        description=_text(data.get("description", ""), 2000, "description"),
        author=author,
        commands=_parse_commands(data.get("commands")),
        skills=_parse_paths(data.get("skills"), "skills"),
        agents=_parse_paths(data.get("agents"), "agents"),
        hooks=_parse_hooks(data.get("hooks")),
        mcp_servers=_parse_mcp_servers(data.get("mcpServers")),
        capabilities=capabilities,
        permissions=_safe_tokens(data.get("permissions"), "permissions"),
    )


def load_manifest(root: Path) -> PluginManifest:
    """Read and validate a plugin root; rejects symlinks and traversal."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise UnsafePathError("bad_plugin_root")
    _validate_tree(root)
    manifest_path = root / MANIFEST_RELATIVE_PATH
    if not manifest_path.is_file():
        raise ManifestError("missing_manifest")
    try:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ManifestError("manifest_too_large")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ManifestError("unreadable_manifest") from None
    return parse_manifest(data)


def _tree_hash(root: Path) -> str:
    """Content fingerprint of a plugin tree (stable across copies)."""
    digest = hashlib.sha256()
    try:
        paths = sorted(p for p in root.rglob("*") if p.is_file())
    except OSError:
        raise UnsafePathError("unreadable_plugin_tree") from None
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# redaction, atomic IO, bounded process execution
# ---------------------------------------------------------------------------


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): (_REDACTED if _SECRET_KEY_RE.search(str(key))
                           else _redact(item))
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str) and _SECRET_VALUE_RE.search(value):
        return _REDACTED
    return value


def _atomic_write_text(path: Path, text: str) -> None:
    """Sibling temp file + fsync + replace, with a bounded Windows rename retry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        last_error: OSError | None = None
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                break
            except OSError as exc:
                last_error = exc
                time.sleep(0.01 * (attempt + 1))
        else:
            raise last_error  # type: ignore[misc]
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, document: Any) -> None:
    _atomic_write_text(path, json.dumps(
        document, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False) + "\n")


class _BoundedReader(threading.Thread):
    """Drain a pipe into at most ``limit`` retained bytes; never block the child."""

    def __init__(self, stream: Any, limit: int) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self._limit = limit
        self.chunks: list[bytes] = []
        self.length = 0
        self.truncated = False

    def run(self) -> None:
        try:
            while True:
                chunk = self._stream.read(8192)
                if not chunk:
                    break
                remaining = self._limit - self.length
                if remaining > 0:
                    kept = chunk[:remaining]
                    self.chunks.append(kept)
                    self.length += len(kept)
                    if len(chunk) > remaining:
                        self.truncated = True
                else:
                    self.truncated = True
        except (OSError, ValueError):
            pass
        finally:
            try:
                self._stream.close()
            except OSError:
                pass


def _terminate_tree(process: subprocess.Popen) -> None:
    """Best-effort process-tree kill; never uses a shell."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=5, shell=False, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (OSError, AttributeError):
            try:
                process.terminate()
            except OSError:
                pass
    try:
        process.kill()
    except OSError:
        pass


def _run_process(argv: Sequence[str], cwd: Path, env: Mapping[str, str],
                 timeout_s: float, max_output_bytes: int) -> dict:
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": str(cwd),
        "env": dict(env),
        "shell": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    started = time.monotonic()
    try:
        process = subprocess.Popen(list(argv), **kwargs)
    except (OSError, ValueError):
        raise InvocationError("spawn_failed") from None

    out_reader = _BoundedReader(process.stdout, max_output_bytes)
    err_reader = _BoundedReader(process.stderr, max_output_bytes)
    out_reader.start()
    err_reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_tree(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _terminate_tree(process)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass  # documented best-effort limit
    for reader in (out_reader, err_reader):
        reader.join(timeout=2.0)
    if out_reader.is_alive() or err_reader.is_alive():
        # A detached grandchild may still hold the pipe open.  Kill the tree
        # again, then stop waiting: retained output stays bounded either way.
        _terminate_tree(process)
        for reader in (out_reader, err_reader):
            reader.join(timeout=0.5)
    exit_code = process.returncode
    if exit_code is None:
        _terminate_tree(process)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        exit_code = process.returncode
    return {
        "ok": (not timed_out and exit_code == 0),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout": b"".join(out_reader.chunks).decode("utf-8", errors="replace"),
        "stderr": b"".join(err_reader.chunks).decode("utf-8", errors="replace"),
        "output_truncated": bool(out_reader.truncated or err_reader.truncated),
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
    }


# ---------------------------------------------------------------------------
# host
# ---------------------------------------------------------------------------


class PluginHost:
    """Discover, gate and invoke locally installed plugins.

    ``plugins_dir`` defaults to ``<state_root>/plugins`` and must stay inside
    the state root.  No method runs plugin code except ``invoke()``, and only
    for a plugin in the ``enabled`` state.
    """

    def __init__(self, state_root: str | Path, *,
                 plugins_dir: str | Path | None = None,
                 env_allowlist: Iterable[str] = DEFAULT_ENV_ALLOWLIST,
                 timeout_s: float = 5.0,
                 max_output_bytes: int = 64 * 1024) -> None:
        self.state_root = Path(state_root).resolve()
        if not self.state_root.is_dir():
            raise UnsafePathError("bad_state_root")
        supplied = Path(plugins_dir) if plugins_dir is not None \
            else self.state_root / PLUGINS_DIRNAME
        if supplied.is_symlink():
            raise UnsafePathError("plugins_dir_symlink")
        self.plugins_root = _contained(self.state_root, supplied, "plugins_dir")
        if timeout_s <= 0 or timeout_s > 300:
            raise PluginHostError("bad_timeout")
        if max_output_bytes <= 0 or max_output_bytes > 8 * 1024 * 1024:
            raise PluginHostError("bad_output_cap")
        self.timeout_s = float(timeout_s)
        self.max_output_bytes = int(max_output_bytes)
        self.env_allowlist = tuple(str(name) for name in env_allowlist)
        self.state_path = self.state_root / STATE_FILENAME
        self.audit_path = self.state_root / AUDIT_FILENAME
        self.quarantine_root = self.plugins_root / QUARANTINE_DIRNAME
        self._lock = threading.RLock()
        self.plugins_root.mkdir(parents=True, exist_ok=True)

    # -- persistence --------------------------------------------------------

    def _load_state(self) -> dict:
        if not self.state_path.is_file():
            return {"version": 1, "plugins": {}}
        try:
            document = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise PluginHostError("corrupt_plugin_state") from None
        if not isinstance(document, dict) \
                or document.get("version") != 1 \
                or not isinstance(document.get("plugins"), dict):
            raise PluginHostError("corrupt_plugin_state")
        return document

    def _save_state(self, document: dict) -> None:
        with self._lock:
            _atomic_write_json(self.state_path, document)

    def _emit(self, event: str, **fields: Any) -> dict:
        record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event}
        record.update(_redact(fields))
        with self._lock:
            existing = self.audit_events(limit=MAX_AUDIT_EVENTS)
            lines = [json.dumps(item, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False) for item in existing]
            lines.append(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False))
            _atomic_write_text(self.audit_path, "\n".join(lines) + "\n")
        return record

    def audit_events(self, limit: int = 200) -> list[dict]:
        """Return the most recent redacted audit records (newest last)."""
        if not self.audit_path.is_file():
            return []
        try:
            lines = self.audit_path.read_text(encoding="utf-8").splitlines()
            records = [json.loads(line) for line in lines if line.strip()]
        except (OSError, UnicodeError, json.JSONDecodeError):
            return []
        return records[-max(0, limit):] if limit else []

    # -- discovery and inspection -------------------------------------------

    def _describe(self, root: Path, state: Mapping[str, Any],
                  *, quarantined: bool = False) -> dict:
        base_name = root.name
        if quarantined:
            # Prefer the name recorded in state; directory names carry a
            # timestamp suffix and may themselves contain hyphens.
            candidates = [str(name) for name, entry in state.items()
                          if isinstance(entry, Mapping)
                          and entry.get("quarantined") is True
                          and root.name.startswith(f"{name}-")]
            if candidates:
                base_name = max(candidates, key=len)
            else:
                base_name = root.name.rsplit("-", 1)[0]
        base = {"name": _safe_name(base_name, "plugin_dir"),
                "version": "", "description": "", "author": "",
                "commands": [], "skills": [], "agents": [], "hooks": [],
                "mcp_servers": [], "capabilities": [], "permissions": [],
                "root": str(root), "manifest_sha256": "", "reason": "",
                "state": PluginState.DISABLED.value}
        if quarantined:
            base["state"] = PluginState.QUARANTINED.value
            base["reason"] = "quarantined"
            return base
        try:
            manifest = load_manifest(root)
            entry = state.get(manifest.name)
            if isinstance(entry, Mapping) and entry.get("quarantined") is True:
                base.update(state=PluginState.QUARANTINED.value,
                            reason="quarantined")
            elif isinstance(entry, Mapping) and entry.get("enabled") is True:
                base["state"] = PluginState.ENABLED.value
            base.update(manifest.to_dict())
            base["manifest_sha256"] = _tree_hash(root)
            base["root"] = str(_contained(self.plugins_root, root, "plugin_root"))
            return base
        except PluginHostError as exc:
            base.update(state=PluginState.INVALID.value, reason=exc.code)
            return base

    def discover(self) -> tuple[dict, ...]:
        """Read manifests only.  Never imports or executes plugin code."""
        state = self._load_state()["plugins"]
        records: list[dict] = []
        try:
            children = sorted(self.plugins_root.iterdir())
        except OSError:
            raise UnsafePathError("unreadable_plugins_root") from None
        for child in children:
            if child.name.startswith("."):
                continue
            if child.is_symlink():
                records.append({"name": child.name, "version": "",
                                "state": PluginState.INVALID.value,
                                "reason": "symlink_plugin_root",
                                "root": str(child), "commands": [],
                                "manifest_sha256": "", "description": "",
                                "author": "", "skills": [], "agents": [],
                                "hooks": [], "mcp_servers": [],
                                "capabilities": [], "permissions": []})
                continue
            if not child.is_dir():
                continue
            records.append(self._describe(child, state))
        # Duplicate manifest names are never silently ambiguous: every live
        # copy becomes invalid so no enable/invoke can pick a winner.
        counts: dict[str, int] = {}
        for record in records:
            counts[record["name"]] = counts.get(record["name"], 0) + 1
        quarantined_records: list[dict] = []
        if self.quarantine_root.is_dir():
            for child in sorted(self.quarantine_root.iterdir()):
                if child.is_dir() and not child.is_symlink():
                    quarantined_records.append(
                        self._describe(child, state, quarantined=True))
        records.extend(quarantined_records)
        for record in records:
            if counts.get(record["name"], 0) > 1 \
                    and record["state"] != PluginState.QUARANTINED.value:
                record["state"] = PluginState.INVALID.value
                record["reason"] = "duplicate_name"
        return tuple(records)

    def list(self) -> tuple[dict, ...]:
        """Public alias for :meth:`discover`."""
        return self.discover()

    def inspect(self, name: str) -> dict:
        """Return the full redacted record for one plugin."""
        wanted = _safe_name(name, "plugin_name")
        for record in self.discover():
            if record["name"] == wanted:
                return dict(record)
        raise PluginNotFound("unknown_plugin")

    def _enabled_record(self, name: str) -> dict:
        record = self.inspect(name)
        state = record["state"]
        if state == PluginState.QUARANTINED.value:
            raise PluginQuarantined("plugin_quarantined")
        if state == PluginState.INVALID.value:
            raise PluginInvalid(record.get("reason") or "plugin_invalid")
        if state != PluginState.ENABLED.value:
            raise PluginDisabled("plugin_disabled")
        return record

    # -- lifecycle ----------------------------------------------------------

    def install(self, source: str | Path, *, replace: bool = False) -> dict:
        """Copy a local plugin directory into the state root, disabled.

        Identical re-installs are idempotent.  A different plugin with the same
        name is refused unless ``replace=True``; replacement quarantines the
        old copy instead of deleting it silently.
        """
        src = Path(source)
        if src.is_symlink():
            raise UnsafePathError("source_symlink")
        src = src.resolve()
        if not src.is_dir():
            raise UnsafePathError("source_not_directory")
        _validate_tree(src)
        manifest = load_manifest(src)
        content_hash = _tree_hash(src)
        state = self._load_state()
        destination = _contained(self.plugins_root,
                                 self.plugins_root / manifest.name,
                                 "plugin_destination")

        existed = destination.exists()
        if existed:
            try:
                existing_hash = _tree_hash(destination)
            except PluginHostError:
                existing_hash = ""
            if existing_hash == content_hash:
                self._emit("plugin.install", plugin=manifest.name,
                           outcome="idempotent", sha256=content_hash)
                return self.inspect(manifest.name)
            if not replace:
                raise DuplicatePlugin("plugin_already_installed")

        staging = self.plugins_root / f".staging-{uuid.uuid4().hex}"
        try:
            shutil.copytree(src, staging, symlinks=False)
            staged_manifest = load_manifest(staging)
            if staged_manifest != manifest or _tree_hash(staging) != content_hash:
                raise UnsafePathError("source_changed_during_install")
            _contained(self.plugins_root, staging, "staging_directory")
            if destination.exists():
                self.quarantine_root.mkdir(parents=True, exist_ok=True)
                retired = self.quarantine_root / (
                    f"{manifest.name}-replaced-{int(time.time() * 1000)}")
                _contained(self.quarantine_root, retired, "retired_plugin")
                os.replace(str(destination), str(retired))
            os.replace(str(staging), str(destination))
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise

        with self._lock:
            plugins = state["plugins"]
            plugins[manifest.name] = {
                "enabled": False,
                "quarantined": False,
                "installed_at": datetime.now(timezone.utc).isoformat(),
                "manifest_sha256": content_hash,
            }
            self._save_state(state)
        self._emit("plugin.install", plugin=manifest.name,
                   outcome="updated" if existed else "installed",
                   sha256=content_hash)
        return self.inspect(manifest.name)

    def enable(self, name: str) -> dict:
        """Explicit trust decision: only an enabled plugin may be invoked."""
        wanted = _safe_name(name, "plugin_name")
        record = self.inspect(wanted)
        if record["state"] == PluginState.INVALID.value:
            raise PluginInvalid(record.get("reason") or "plugin_invalid")
        if record["state"] == PluginState.QUARANTINED.value:
            raise PluginQuarantined("plugin_quarantined")
        with self._lock:
            state = self._load_state()
            entry = state["plugins"].setdefault(wanted, {})
            entry["enabled"] = True
            entry["quarantined"] = False
            self._save_state(state)
        self._emit("plugin.enable", plugin=wanted, outcome="enabled")
        return self.inspect(wanted)

    def disable(self, name: str) -> dict:
        wanted = _safe_name(name, "plugin_name")
        self.inspect(wanted)  # existence check; disabling invalid is harmless
        with self._lock:
            state = self._load_state()
            entry = state["plugins"].setdefault(wanted, {})
            entry["enabled"] = False
            self._save_state(state)
        self._emit("plugin.disable", plugin=wanted, outcome="disabled")
        return self.inspect(wanted)

    def quarantine(self, name: str, reason: str = "operator") -> dict:
        """Move a plugin out of the live directory; it can never be invoked."""
        wanted = _safe_name(name, "plugin_name")
        record = self.inspect(wanted)
        root = _contained(self.plugins_root, Path(record["root"]), "plugin_root")
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        target = self.quarantine_root / (
            f"{wanted}-{int(time.time() * 1000)}")
        _contained(self.quarantine_root, target, "quarantine_destination")
        with self._lock:
            os.replace(str(root), str(target))
            state = self._load_state()
            entry = state["plugins"].setdefault(wanted, {})
            entry["enabled"] = False
            entry["quarantined"] = True
            self._save_state(state)
        self._emit("plugin.quarantine", plugin=wanted, outcome="quarantined",
                   reason=_text(reason, 200, "reason"))
        return self.inspect(wanted)

    def remove(self, name: str) -> bool:
        """Remove an installed or quarantined plugin, then drop its state row."""
        wanted = _safe_name(name, "plugin_name")
        record = self.inspect(wanted)
        root = Path(record["root"])
        if root.is_relative_to(self.quarantine_root):
            root = _contained(self.quarantine_root, root, "quarantined_plugin")
        else:
            root = _contained(self.plugins_root, root, "plugin_root")
        staging = self.plugins_root / f".removing-{uuid.uuid4().hex}"
        with self._lock:
            os.replace(str(root), str(staging))
            shutil.rmtree(staging, ignore_errors=True)
            state = self._load_state()
            state["plugins"].pop(wanted, None)
            self._save_state(state)
        self._emit("plugin.remove", plugin=wanted, outcome="removed")
        return True

    # -- execution ----------------------------------------------------------

    def _build_env(self, plugin_name: str, command_name: str) -> dict:
        environment: dict[str, str] = {}
        for key in self.env_allowlist:
            if not key or _SECRET_KEY_RE.search(key):
                continue
            value = os.environ.get(key)
            if value is not None:
                environment[key] = value
        environment["KEEL_PLUGIN_NAME"] = plugin_name
        environment["KEEL_PLUGIN_COMMAND"] = command_name
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return environment

    def invoke(self, name: str, command: str, args: Mapping[str, Any] | None = None,
               *, timeout_s: float | None = None,
               max_output_bytes: int | None = None) -> dict:
        """Run one declared command with JSON args in an isolated child process.

        ``args`` is serialized as a single final argv token; no shell is used.
        Output beyond the byte cap is discarded (the flag is reported), and a
        timeout terminates the child process tree.
        """
        wanted = _safe_name(name, "plugin_name")
        command_name = _safe_name(command, "command_name")
        record = self._enabled_record(wanted)
        root = _contained(self.plugins_root, Path(record["root"]), "plugin_root")
        manifest = load_manifest(root)  # re-validate immediately before exec
        declared = next((c for c in manifest.commands if c.name == command_name),
                        None)
        if declared is None:
            raise InvocationError("unknown_command")
        if args is not None and not isinstance(args, Mapping):
            raise InvocationError("args_must_be_object")
        # Args are passed verbatim to the child; redaction applies only to the
        # audit record (which logs key names, never values).
        payload = json.dumps(args or {}, sort_keys=True,
                             separators=(",", ":"), ensure_ascii=False,
                             allow_nan=False)
        argv: list[str] = []
        for token in declared.argv:
            if token == PYTHON_ALIAS:
                argv.append(sys.executable)
            else:
                resolved = _contained(root, root / _safe_rel(token, "command_argv"),
                                      "command_argv")
                if not resolved.is_file():
                    raise InvocationError("command_executable_missing")
                argv.append(str(resolved))
        argv.append(payload)

        limit = self.max_output_bytes if max_output_bytes is None \
            else int(max_output_bytes)
        deadline = self.timeout_s if timeout_s is None else float(timeout_s)
        if deadline <= 0 or deadline > 300 or limit <= 0 \
                or limit > 8 * 1024 * 1024:
            raise InvocationError("bad_execution_limits")
        environment = self._build_env(wanted, command_name)
        try:
            result = _run_process(argv, root, environment, deadline, limit)
        except InvocationError as exc:
            self._emit("plugin.invoke.error", plugin=wanted,
                       command=command_name, reason=exc.code)
            raise
        result.update({"plugin": wanted, "command": command_name})
        self._emit("plugin.invoke", plugin=wanted, command=command_name,
                   outcome="ok" if result["ok"] else "failed",
                   exit_code=result["exit_code"],
                   timed_out=result["timed_out"],
                   output_truncated=result["output_truncated"],
                   stdout_bytes=len(result["stdout"]),
                   stderr_bytes=len(result["stderr"]),
                   duration_ms=result["duration_ms"],
                   env_keys=sorted(environment),
                   args_keys=sorted(str(key) for key in (args or {})))
        return result


__all__ = [
    "PluginHost", "PluginManifest", "PluginCommand", "PluginHostError",
    "ManifestError", "UnsafePathError", "PluginNotFound", "PluginDisabled",
    "PluginInvalid", "PluginQuarantined", "DuplicatePlugin",
    "InvocationError", "PluginState", "parse_manifest", "load_manifest",
    "DEFAULT_ENV_ALLOWLIST", "MANIFEST_RELATIVE_PATH",
]
