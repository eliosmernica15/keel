"""Backend logic for the W1.* (DeepSeek-harness) feature family.

Scope: the non-UI, testable behaviour behind the W1 features described in
``PLAN-INDEX.json``.  Everything here is stdlib-only, local-first and
safe-by-default: nothing binds a non-loopback interface, reads outside an
explicit root, opens a browser on a remote session, or sends data anywhere.

W1.18 (MIT license / THIRD_PARTY_NOTICES.md) is owner-gated and rejected; it
is recorded in ``EXCLUDED_FEATURES`` for documentation only and has no
implementation.
"""

from __future__ import annotations

import fnmatch
import hashlib
import html
import json
import math
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "W1_FEATURES", "IMPLEMENTED_FEATURES", "EXCLUDED_FEATURES",
    "W1BackendError", "PluginError", "LaunchPolicyError", "PluginIndexError",
    # W1.1
    "PLUGIN_KINDS", "PluginRegistration", "PluginScopeTree",
    # W1.2 / W1.3
    "WebLaunchPlan", "plan_web_launch", "detect_ssh_session",
    "ssh_forwarding_hint", "launch_display",
    # W1.4
    "TargetPlan", "plan_target", "bundle_digest", "MAKE_TARGETS", "make_help",
    # W1.5
    "REQUIRED_SUITES", "suite_config", "validate_suite_matrix", "ci_jobs",
    "pytest_ini_section",
    # W1.6
    "BenchmarkStore",
    # W1.7
    "RgIgnore", "find_duplicate_blocks", "StagedLintPlan", "staged_lint_plan",
    "LINT_CONFIG_FILES",
    # W1.8
    "PortableCIMirror",
    # W1.9 / W1.12
    "I18N_DOCS", "parse_simple_yaml", "I18nDocumentStore", "BrandGuidelines",
    # W1.11
    "STABILITY_CHANNELS", "stability_info",
    # W1.13
    "BuilderInstructionScanner",
    # W1.14
    "PrivatePluginIndex",
    # W1.15
    "python_sdk_surface", "validate_payload", "typescript_client_source",
    "sdk_compatibility",
    # W1.16
    "VendorPolicy", "valid_vendor_license_text",
    # W1.17
    "feedback_policy", "redact_feedback", "build_feedback_bundle",
]

# ---------------------------------------------------------------------------
# Feature inventory (single source of truth for evidence/tests)
# ---------------------------------------------------------------------------

W1_FEATURES: dict[str, str] = {
    "W1.1": "Everything-is-a-plugin scope tree with one registration API",
    "W1.2": "Single-command loopback web launch on 127.0.0.1:3080",
    "W1.3": "SSH-aware launch: print URL + forwarding hint, never open a browser",
    "W1.4": "--no-open flag and one renderer bundle for web + desktop targets",
    "W1.5": "Eight named test suites mirrored as separate CI jobs",
    "W1.6": "benchmarks/ + BENCHMARK.md + snapshots/ with per-release results",
    "W1.7": "Staged ruff lint, duplicate-code check and .rgignore consumption",
    "W1.8": "Portable dual CI configuration (GitHub + GitLab) with parity check",
    "W1.9": "i18n.yaml single-source docs rendered to Markdown/HTML",
    "W1.11": "Developer-preview banner and stability channel in About",
    "W1.12": "Localized BRAND_GUIDELINES generated into the website",
    "W1.13": "Builder instruction files read as instruction sources",
    "W1.14": "Private plugin index replaces public repository-topic discovery",
    "W1.15": "Python SDK plus generated thin TypeScript client contract",
    "W1.16": "vendor/ with LICENSE files and a PATCHES.md change log",
    "W1.17": "Feedback via email/in-app with a redacted bundle",
}
IMPLEMENTED_FEATURES: tuple[str, ...] = tuple(W1_FEATURES)
EXCLUDED_FEATURES: dict[str, str] = {
    "W1.18": (
        "Owner-gated/rejected: MIT license and THIRD_PARTY_NOTICES.md are a "
        " licensing decision reserved to the repository owner. Documented "
        "only; deliberately not implemented."
    ),
}


class W1BackendError(ValueError):
    """Base class for W1 backend policy/validation failures."""


class PluginError(W1BackendError):
    """Invalid plugin registration or composition (W1.1)."""


class LaunchPolicyError(W1BackendError):
    """A web launch would break the loopback/no-browser policy (W1.2/W1.3)."""


class PluginIndexError(W1BackendError):
    """The private plugin index is corrupt or unsafe (W1.14)."""


# ---------------------------------------------------------------------------
# Shared path/identity helpers
# ---------------------------------------------------------------------------

def _safe_rel(value: str, *, label: str = "path") -> str:
    """Normalize a caller-supplied relative path, rejecting escapes.

    Backslashes are accepted as separators (Windows callers) but absolute
    paths, drive letters, NUL bytes and ``..`` segments are refused.
    """
    if not isinstance(value, str) or not value.strip():
        raise W1BackendError(f"empty {label}")
    text = value.strip().replace("\\", "/")
    if "\x00" in text:
        raise W1BackendError(f"NUL byte in {label}")
    if PurePosixPath(text).is_absolute() or PureWindowsPath(text).is_absolute():
        raise W1BackendError(f"absolute {label} is not allowed: {value!r}")
    if PureWindowsPath(text).drive:
        raise W1BackendError(f"drive-qualified {label} is not allowed: {value!r}")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise W1BackendError(f"unsafe {label}: {value!r}")
    return "/".join(parts)


def _within(root: str | Path, rel: str, *, label: str = "path") -> Path:
    """Resolve ``rel`` under ``root`` and verify the result stays there."""
    root_r = Path(root).resolve()
    candidate = root_r.joinpath(*_safe_rel(rel, label=label).split("/")).resolve()
    try:
        candidate.relative_to(root_r)
    except ValueError:
        raise W1BackendError(f"{label} escapes root: {rel!r}") from None
    return candidate


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# W1.1 -- everything is a plugin: one API, a scope tree, no Cordis
# ---------------------------------------------------------------------------

PLUGIN_KINDS: tuple[str, ...] = (
    "provider", "tool", "channel", "ui_panel", "memory_backend", "builtin_agent",
)
_PLUGIN_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_SCOPE_SEGMENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
SCOPE_PRECEDENCE: tuple[str, ...] = ("session", "user", "profile", "core")


def _plugin_name(name: str, *, label: str = "plugin name") -> str:
    if not isinstance(name, str) or not _PLUGIN_NAME_RE.fullmatch(name):
        raise PluginError(f"invalid {label}: {name!r}")
    return name


def _plugin_scope(scope: str) -> str:
    if not isinstance(scope, str) or not scope:
        raise PluginError(f"invalid plugin scope: {scope!r}")
    segments = scope.split(".")
    if len(segments) > 8 or any(not _SCOPE_SEGMENT_RE.fullmatch(s) for s in segments):
        raise PluginError(f"invalid plugin scope: {scope!r}")
    return ".".join(segments)


def _scope_rank(scope: str) -> tuple[int, int]:
    root = scope.split(".", 1)[0]
    try:
        precedence = SCOPE_PRECEDENCE.index(root)
    except ValueError:
        precedence = len(SCOPE_PRECEDENCE)
    return (-precedence, len(scope.split(".")))


@dataclass(frozen=True)
class PluginRegistration:
    """A single registration in the composable plugin scope tree."""

    name: str
    kind: str
    scope: str
    replaces: str | None = None
    depends_on: tuple[str, ...] = ()
    factory: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "scope": self.scope,
            "replaces": self.replaces, "depends_on": list(self.depends_on),
            "has_factory": self.factory is not None,
        }


class PluginScopeTree:
    """Registers every plugin kind through one API (W1.1, no Cordis).

    Plugins live in dotted scopes (``core``, ``core.tools``, ``user`` ...).
    For a given name the effective plugin is the enabled registration with the
    highest scope precedence; deeper scopes win inside the same root and later
    registrations win exact ties. ``replaces`` explicitly retires a target.
    """

    def __init__(self) -> None:
        self._registrations: dict[tuple[str, str], PluginRegistration] = {}
        self._enabled: dict[tuple[str, str], bool] = {}
        self._order: dict[tuple[str, str], int] = {}
        self._replaced: dict[tuple[str, str], tuple[str, str]] = {}
        self._counter = 0

    def register(self, name: str, kind: str, scope: str = "core", *,
                 factory: Any = None, replaces: str | None = None,
                 depends_on: Iterable[str] = (), enabled: bool = True) -> PluginRegistration:
        name = _plugin_name(name)
        if kind not in PLUGIN_KINDS:
            raise PluginError(f"unknown plugin kind: {kind!r}")
        scope = _plugin_scope(scope)
        key = (scope, name)
        if key in self._registrations:
            raise PluginError(f"duplicate registration: {scope}:{name}")
        deps = tuple(_plugin_name(d, label="dependency") for d in depends_on)
        if name in deps or len(set(deps)) != len(deps):
            raise PluginError(f"invalid dependencies for {name!r}")

        replacement_of: str | None = None
        if replaces is not None:
            if not isinstance(replaces, str) or not replaces:
                raise PluginError(f"invalid replacement target: {replaces!r}")
            target = self._resolve_key(replaces)
            if target is None:
                raise PluginError(f"replacement target not registered: {replaces!r}")
            if self._registrations[target].kind != kind:
                raise PluginError("replacement must have the same plugin kind")
            if target in self._replaced:
                raise PluginError("replacement target was already replaced")
            self._replaced[target] = key
            replacement_of = f"{target[0]}:{target[1]}"

        registration = PluginRegistration(
            name=name, kind=kind, scope=scope, replaces=replacement_of,
            depends_on=deps, factory=factory,
        )
        self._registrations[key] = registration
        self._enabled[key] = bool(enabled)
        self._order[key] = self._counter
        self._counter += 1
        return registration

    def _resolve_key(self, name_or_key: str) -> tuple[str, str] | None:
        if ":" in name_or_key:
            scope, name = name_or_key.split(":", 1)
            key = (_plugin_scope(scope), _plugin_name(name))
            return key if key in self._registrations else None
        wanted = _plugin_name(name_or_key)
        keys = [k for k, reg in self._registrations.items() if reg.name == wanted]
        if not keys:
            return None
        return max(keys, key=lambda k: (_scope_rank(k[0]), self._order[k]))

    def resolve(self, name: str, *, kind: str | None = None) -> PluginRegistration | None:
        """Return the effective registration for ``name`` or ``None``."""
        wanted = _plugin_name(name)
        candidates = [
            key for key, reg in self._registrations.items()
            if reg.name == wanted and key not in self._replaced and self._enabled[key]
            and (kind is None or reg.kind == kind)
        ]
        if not candidates:
            return None
        winner = max(candidates, key=lambda k: (_scope_rank(k[0]), self._order[k]))
        return self._registrations[winner]

    def resolve_all(self, kind: str) -> dict[str, PluginRegistration]:
        """Effective plugin for every registered name of ``kind``."""
        if kind not in PLUGIN_KINDS:
            raise PluginError(f"unknown plugin kind: {kind!r}")
        names = sorted({reg.name for reg in self._registrations.values()
                        if reg.kind == kind})
        return {name: reg for name in names
                if (reg := self.resolve(name, kind=kind)) is not None}

    def list_plugins(self, *, kind: str | None = None, scope: str | None = None,
                     include_disabled: bool = False) -> list[PluginRegistration]:
        if kind is not None and kind not in PLUGIN_KINDS:
            raise PluginError(f"unknown plugin kind: {kind!r}")
        scope = _plugin_scope(scope) if scope is not None else None
        selected = [
            reg for key, reg in self._registrations.items()
            if (include_disabled or (self._enabled[key] and key not in self._replaced))
            and (kind is None or reg.kind == kind)
            and (scope is None or reg.scope == scope or reg.scope.startswith(scope + "."))
        ]
        return sorted(selected, key=lambda reg: (reg.scope, reg.name))

    def disable(self, scope: str, name: str) -> None:
        key = (_plugin_scope(scope), _plugin_name(name))
        if key not in self._registrations:
            raise PluginError(f"not registered: {scope}:{name}")
        self._enabled[key] = False

    def enable(self, scope: str, name: str) -> None:
        key = (_plugin_scope(scope), _plugin_name(name))
        if key not in self._registrations:
            raise PluginError(f"not registered: {scope}:{name}")
        self._enabled[key] = True

    def unregister(self, scope: str, name: str) -> None:
        key = (_plugin_scope(scope), _plugin_name(name))
        if key not in self._registrations:
            raise PluginError(f"not registered: {scope}:{name}")
        del self._registrations[key]
        self._enabled.pop(key, None)
        self._order.pop(key, None)
        self._replaced.pop(key, None)
        for target, replacement in list(self._replaced.items()):
            if replacement == key:
                del self._replaced[target]

    def validate(self) -> dict[str, Any]:
        """Report missing dependencies and dependency cycles."""
        issues: list[str] = []
        graph: dict[str, list[str]] = {}
        for reg in self.list_plugins():
            missing = [dep for dep in reg.depends_on if self.resolve(dep) is None]
            for dep in missing:
                issues.append(f"{reg.scope}:{reg.name} missing dependency {dep}")
            graph[reg.name] = [dep for dep in reg.depends_on if dep not in missing]

        state: dict[str, int] = {}
        stack: list[str] = []

        def visit(node: str) -> None:
            state[node] = 1
            stack.append(node)
            for dep in graph.get(node, []):
                if state.get(dep) == 1:
                    cycle = stack[stack.index(dep):] + [dep]
                    issues.append("dependency cycle: " + " -> ".join(cycle))
                elif state.get(dep, 0) == 0:
                    visit(dep)
            stack.pop()
            state[node] = 2

        for node in sorted(graph):
            if state.get(node, 0) == 0:
                visit(node)
        return {"ok": not issues, "issues": sorted(set(issues))}


# ---------------------------------------------------------------------------
# W1.2 / W1.3 / W1.4 -- launch surfaces
# ---------------------------------------------------------------------------

DEFAULT_WEB_PORT = 3080
_LOOPBACK_V4_RE = re.compile(r"^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _is_loopback(host: str) -> bool:
    if host in ("localhost", "::1", "0:0:0:0:0:0:0:1"):
        return True
    match = _LOOPBACK_V4_RE.fullmatch(host)
    if not match:
        return False
    return all(0 <= int(part) <= 255 for part in host.split(".")[1:])


def _ssh_detected(environ: Mapping[str, str] | None) -> bool:
    env = os.environ if environ is None else environ
    for key in ("SSH_CONNECTION", "SSH_TTY", "SSH_CLIENT"):
        value = env.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


@dataclass(frozen=True)
class WebLaunchPlan:
    host: str
    port: int
    url: str
    path: str
    open_browser: bool
    ssh: bool
    command: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host, "port": self.port, "url": self.url,
            "path": self.path, "open_browser": self.open_browser,
            "ssh": self.ssh, "command": list(self.command),
        }


def plan_web_launch(*, host: str = "127.0.0.1", port: int = DEFAULT_WEB_PORT,
                    no_open: bool = False, path: str = "/",
                    environ: Mapping[str, str] | None = None) -> WebLaunchPlan:
    """Build a launch plan that can only bind a loopback interface (W1.2)."""
    if not isinstance(host, str) or not host.strip():
        raise LaunchPolicyError("host must be a non-empty string")
    normalized = host.strip().lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    if not _is_loopback(normalized):
        raise LaunchPolicyError(f"non-loopback host refused: {host!r}")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise LaunchPolicyError(f"invalid port: {port!r}")
    if not isinstance(path, str) or not path.startswith("/") or ".." in path.split("/"):
        raise LaunchPolicyError(f"invalid web path: {path!r}")
    safe_path = re.sub(r"[^A-Za-z0-9/._~-]", lambda m: "%%%02X" % ord(m.group()), path)
    display_host = f"[{normalized}]" if ":" in normalized else normalized
    url = f"http://{display_host}:{port}{safe_path}"
    ssh = _ssh_detected(environ)
    command = ["keel", "web", "--host", normalized, "--port", str(port)]
    if no_open:
        command.append("--no-open")
    return WebLaunchPlan(
        host=normalized, port=port, url=url, path=safe_path,
        open_browser=(not no_open and not ssh), ssh=ssh, command=tuple(command),
    )


def detect_ssh_session(environ: Mapping[str, str] | None = None) -> bool:
    """True when SSH_CONNECTION, SSH_TTY or SSH_CLIENT is set (W1.3)."""
    return _ssh_detected(environ)


def ssh_forwarding_hint(port: int = DEFAULT_WEB_PORT, *, user: str = "<user>",
                        host: str = "<host>") -> str:
    return f"ssh -L {port}:127.0.0.1:{port} {user}@{host}"


def launch_display(plan: WebLaunchPlan, *, environ: Mapping[str, str] | None = None,
                   stream: Any = None) -> dict[str, Any]:
    """Decide what to print/do at launch; SSH sessions never open a browser."""
    ssh = plan.ssh or _ssh_detected(environ)
    open_browser = plan.open_browser and not ssh
    hint = ssh_forwarding_hint(plan.port) if ssh else ""
    if ssh:
        message = (f"Keel Web UI: {plan.url}\n"
                   f"SSH session detected; browser not opened.\n"
                   f"Forward locally: {hint}")
    else:
        message = f"Keel Web UI: {plan.url}"
        if not open_browser:
            message += "\nBrowser not opened (--no-open)."
    if stream is not None:
        stream.write(message + "\n")
    return {
        "mode": "ssh" if ssh else "local", "url": plan.url,
        "open_browser": open_browser, "hint": hint, "message": message,
    }


# W1.4 -- one renderer bundle for both targets
_RENDERER_SOURCES: dict[str, str] = {
    "index.html": "<!doctype html><html><body><div id='app'></div></body></html>",
    "app.js": "export function mount(root){root.textContent='Keel';}",
    "styles.css": ":root{color-scheme:dark}body{margin:0}",
}
MAKE_TARGETS: dict[str, str] = {
    "help": "list builder tasks",
    "web": "run the loopback Web UI",
    "desktop": "run the desktop target with the same renderer",
    "unit": "run the unit suite",
    "e2e": "run the end-to-end suite",
    "lint": "ruff the staged Python files",
    "build": "build the shared renderer bundle",
}


def bundle_digest(sources: Mapping[str, str]) -> str:
    """Content hash of a renderer source set, independent of dict order."""
    if not sources:
        raise W1BackendError("renderer sources are empty")
    digest = hashlib.sha256()
    for name in sorted(sources):
        content = sources[name]
        if not isinstance(name, str) or not isinstance(content, str):
            raise W1BackendError("renderer sources must be str -> str")
        digest.update(name.encode("utf-8") + b"\0" + content.encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class TargetPlan:
    target: str
    bundle: str
    bundle_sha256: str
    open_browser: bool
    command: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": self.target, "bundle": self.bundle,
            "bundle_sha256": self.bundle_sha256,
            "open_browser": self.open_browser, "command": list(self.command),
        }


def plan_target(target: str, *, no_open: bool = False,
                sources: Mapping[str, str] | None = None,
                environ: Mapping[str, str] | None = None) -> TargetPlan:
    """Plan a web or desktop launch sharing exactly one renderer bundle."""
    if target not in ("web", "desktop"):
        raise W1BackendError(f"unknown target: {target!r}")
    digest = bundle_digest(_RENDERER_SOURCES if sources is None else sources)
    bundle = f"renderer-{digest[:16]}.js"
    if target == "web":
        web = plan_web_launch(no_open=no_open, environ=environ)
        command, open_browser = web.command, web.open_browser
    else:
        command = ("keel", "desktop", "--bundle", bundle)
        open_browser = False
    return TargetPlan(target=target, bundle=bundle, bundle_sha256=digest,
                      open_browser=open_browser, command=command)


def make_help() -> str:
    """Text produced by ``make help`` for the builder (W1.4)."""
    width = max(len(name) for name in MAKE_TARGETS)
    return "Builder targets:\n" + "\n".join(
        f"  {name.ljust(width)}  {description}"
        for name, description in MAKE_TARGETS.items()
    ) + "\n"


# ---------------------------------------------------------------------------
# W1.5 -- test suite taxonomy and mirrored CI jobs
# ---------------------------------------------------------------------------

_SUITE_SPECS: dict[str, tuple[str, int]] = {
    "unit": ("not slow and not e2e and not web", 300),
    "bench": ("benchmark", 900),
    "e2e": ("e2e", 1800),
    "golden": ("golden", 900),
    "snapshot": ("snapshot", 900),
    "web": ("web and not web_stress and not web_perf", 900),
    "web-stress": ("web_stress", 1800),
    "web-perf": ("web_perf", 1800),
}
REQUIRED_SUITES: tuple[str, ...] = tuple(_SUITE_SPECS)
_SUITE_MARKERS: dict[str, str] = {
    "benchmark": "performance benchmark measurements",
    "e2e": "real subprocess/end-to-end tests",
    "golden": "golden expected-output tests",
    "snapshot": "snapshot comparison tests",
    "web": "browser web tests",
    "web_stress": "web stress tests",
    "web_perf": "web performance tests",
}


def suite_config(name: str) -> dict[str, Any]:
    if name not in _SUITE_SPECS:
        raise W1BackendError(f"unknown test suite: {name!r}")
    marker, timeout = _SUITE_SPECS[name]
    return {
        "name": name, "ci_job": name,
        "pytest_args": ["tests", "-m", marker],
        "timeout_seconds": timeout,
    }


def validate_suite_matrix(names: Sequence[str]) -> None:
    if isinstance(names, (str, bytes)) or not isinstance(names, Sequence):
        raise W1BackendError("suite matrix must be a sequence of names")
    if len(set(names)) != len(names):
        raise W1BackendError("duplicate suite names in matrix")
    unknown = [name for name in names if name not in _SUITE_SPECS]
    if unknown:
        raise W1BackendError(f"unknown suite names: {sorted(unknown)}")
    missing = [name for name in REQUIRED_SUITES if name not in names]
    if missing:
        raise W1BackendError(f"required suites missing: {missing}")


def ci_jobs(names: Sequence[str] | None = None) -> list[dict[str, Any]]:
    selected = REQUIRED_SUITES if names is None else names
    validate_suite_matrix(selected)
    jobs = []
    for name in selected:
        config = suite_config(name)
        jobs.append({
            "name": config["ci_job"], "stage": "test",
            "timeout_seconds": config["timeout_seconds"],
            "command": "python -m pytest " + " ".join(
                shlex.quote(arg) for arg in config["pytest_args"]),
        })
    return jobs


def pytest_ini_section() -> str:
    lines = ["[pytest]", "markers ="]
    for marker, description in sorted(_SUITE_MARKERS.items()):
        lines.append(f"    {marker}: {description}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# W1.6 -- benchmarks, method doc and per-release snapshots
# ---------------------------------------------------------------------------

_RELEASE_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_METHOD_HEADINGS = ("# method", "# hardware", "# command", "# metric")


class BenchmarkStore:
    """On-disk benchmark repository with a documented method (C13.5)."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.benchmarks = self.root / "benchmarks"
        self.snapshots = self.root / "snapshots"
        self.method_doc = self.root / "BENCHMARK.md"

    def initialize(self, method_text: str) -> dict[str, Any]:
        if not isinstance(method_text, str):
            raise W1BackendError("benchmark method must be text")
        present = {line.strip().lower() for line in method_text.splitlines()}
        missing = [h for h in _METHOD_HEADINGS if h not in present]
        if missing:
            raise W1BackendError(f"BENCHMARK.md missing sections: {missing}")
        _atomic_write_text(self.method_doc, "# Keel benchmark method\n\n" + method_text.strip() + "\n")
        self.benchmarks.mkdir(parents=True, exist_ok=True)
        self.snapshots.mkdir(parents=True, exist_ok=True)
        return {"method_doc": str(self.method_doc), "sections": list(_METHOD_HEADINGS)}

    @staticmethod
    def _validate_release(release: str) -> str:
        if not isinstance(release, str) or not _RELEASE_RE.fullmatch(release):
            raise W1BackendError(f"invalid release: {release!r}")
        return release

    def record(self, release: str, suite: str, metrics: Mapping[str, int | float],
               *, snapshot: str | None = None) -> dict[str, Any]:
        release = self._validate_release(release)
        if suite not in REQUIRED_SUITES:
            raise W1BackendError(f"unknown benchmark suite: {suite!r}")
        if not self.method_doc.is_file():
            raise W1BackendError("BENCHMARK.md must document the method first")
        if not isinstance(metrics, Mapping) or not metrics:
            raise W1BackendError("metrics must be a non-empty mapping")
        clean: dict[str, float] = {}
        for key, value in metrics.items():
            if not isinstance(key, str) or not key or isinstance(value, bool) \
                    or not isinstance(value, (int, float)) or not math.isfinite(value) \
                    or value < 0:
                raise W1BackendError(f"invalid metric {key!r}={value!r}")
            clean[key] = float(value)
        entry: dict[str, Any] = {"release": release, "suite": suite, "metrics": clean}
        if snapshot is not None:
            if not isinstance(snapshot, str):
                raise W1BackendError("snapshot must be text")
            snap_path = self.snapshots / f"{release}-{suite}.txt"
            _atomic_write_text(snap_path, snapshot)
            entry["snapshot"] = snap_path.name
            entry["snapshot_sha256"] = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()

        # One file per (suite, release); repeated measurements append runs.
        path = self.benchmarks / suite / f"{release}.json"
        document: dict[str, Any] = {"release": release, "suite": suite, "runs": []}
        if path.is_file():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(previous, Mapping):
                    if isinstance(previous.get("runs"), list):
                        document["runs"] = [run for run in previous["runs"]
                                            if isinstance(run, Mapping)]
                    elif isinstance(previous.get("metrics"), Mapping):
                        document["runs"] = [previous]
            except (OSError, ValueError):
                pass
        document["runs"].append(entry)
        _atomic_write_text(path, json.dumps(document, indent=2, sort_keys=True) + "\n")
        return entry

    def results(self, *, suite: str | None = None,
                release: str | None = None) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if not self.benchmarks.is_dir():
            return found
        for path in sorted(self.benchmarks.glob("*/*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(doc, dict):
                continue
            runs = doc.get("runs")
            if not isinstance(runs, list):
                runs = [doc]
            for run in runs:
                if not isinstance(run, Mapping):
                    continue
                row = dict(run)
                row.setdefault("release", doc.get("release"))
                row.setdefault("suite", doc.get("suite"))
                if suite is not None and row.get("suite") != suite:
                    continue
                if release is not None and row.get("release") != release:
                    continue
                found.append(row)
        return sorted(found, key=lambda doc: (str(doc.get("suite")), str(doc.get("release"))))

    def summary(self, *, release: str | None = None) -> dict[str, Any]:
        rows = self.results(release=release)
        by_suite: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_suite.setdefault(str(row.get("suite")), []).append(row)
        suites: dict[str, Any] = {}
        for name, group in sorted(by_suite.items()):
            metric_rows: dict[str, list[float]] = {}
            for row in group:
                for key, value in row.get("metrics", {}).items():
                    metric_rows.setdefault(key, []).append(float(value))
            suites[name] = {
                "runs": len(group),
                "metrics": {key: sum(values) / len(values)
                            for key, values in sorted(metric_rows.items())},
            }
        return {"release": release, "runs": len(rows), "suites": suites}

    def validate_layout(self) -> list[str]:
        issues: list[str] = []
        if not self.method_doc.is_file() or not self.method_doc.stat().st_size:
            issues.append("missing or empty BENCHMARK.md")
        for directory in (self.benchmarks, self.snapshots):
            if not directory.is_dir():
                issues.append(f"missing {directory.name}/ directory")
        for row in self.results():
            for key in ("release", "suite", "metrics"):
                if key not in row:
                    issues.append(f"benchmark row missing {key}: {row}")
            snap = row.get("snapshot")
            if snap and not (self.snapshots / str(snap)).is_file():
                issues.append(f"missing snapshot: {snap}")
        return sorted(set(issues))


# ---------------------------------------------------------------------------
# W1.7 -- staged lint, duplicate-code check, .rgignore
# ---------------------------------------------------------------------------

class RgIgnore:
    """Parses a project ``.rgignore`` and filters paths for Keel's grep tool."""

    def __init__(self, lines: Iterable[str] = ()):
        self._patterns: list[tuple[str, bool, bool]] = []  # pattern, negated, dir_only
        for raw in lines:
            if not isinstance(raw, str):
                raise W1BackendError(".rgignore lines must be text")
            line = raw.strip().replace("\\", "/")
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:].strip()
            if not line:
                continue
            anchored = line.startswith("/")
            if anchored:
                line = line[1:]
            dir_only = line.endswith("/")
            if dir_only:
                line = line[:-1]
            if not line:
                continue
            self._patterns.append((line, negated, dir_only or anchored))

    @classmethod
    def from_text(cls, text: str) -> "RgIgnore":
        return cls(text.splitlines())

    @classmethod
    def from_file(cls, path: str | Path) -> "RgIgnore":
        return cls(Path(path).read_text(encoding="utf-8").splitlines())

    def ignored(self, relpath: str) -> bool:
        rel = _safe_rel(relpath, label="ignore path")
        result = False
        for pattern, negated, dir_only in self._patterns:
            parts = rel.split("/")
            candidates = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)] if dir_only else [rel]
            matched = any(fnmatch.fnmatchcase(candidate, pattern) for candidate in candidates)
            if matched:
                result = not negated
        return result

    def filter(self, paths: Iterable[str]) -> list[str]:
        return [path for path in paths if not self.ignored(path)]


def find_duplicate_blocks(sources: Mapping[str, str], *, min_lines: int = 5) -> list[dict[str, Any]]:
    """Find identical non-overlapping line blocks shared by two or more files."""
    if not isinstance(min_lines, int) or min_lines < 2:
        raise W1BackendError("min_lines must be >= 2")
    blocks: dict[str, set[str]] = {}
    for name, text in sources.items():
        if not isinstance(name, str) or not isinstance(text, str):
            raise W1BackendError("duplicate-check sources must be str -> str")
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        for start in range(0, max(0, len(lines) - min_lines + 1), min_lines):
            window = lines[start:start + min_lines]
            if not any(window):
                continue
            key = hashlib.sha256("\n".join(window).encode("utf-8")).hexdigest()
            blocks.setdefault(key, set()).add(name)
    return [
        {"sha256": key, "files": sorted(files), "min_lines": min_lines}
        for key, files in sorted(blocks.items()) if len(files) > 1
    ]


LINT_CONFIG_FILES: dict[str, str] = {
    ".oxlintrc.staged.json": "staged-only lint rule set (ruff-equivalent)",
    "lefthook.yml": "git hook that lints staged files",
    ".jscpd.json": "duplicate-code detector configuration",
    ".rgignore": "paths Keel's own grep tool skips",
    ".gitattributes": "line-ending and diff policy",
    ".editorconfig": "editor formatting policy",
}


@dataclass(frozen=True)
class StagedLintPlan:
    files: tuple[str, ...]
    command: tuple[str, ...]
    duplicate_command: tuple[str, ...]
    skipped: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "files": list(self.files), "command": list(self.command),
            "duplicate_command": list(self.duplicate_command),
            "skipped": list(self.skipped),
        }


def staged_lint_plan(staged_files: Iterable[str], *, rgignore: RgIgnore | None = None
                     ) -> StagedLintPlan:
    """Build ruff + duplicate-code commands for staged Python files only."""
    chosen: set[str] = set()
    skipped: list[str] = []
    for raw in staged_files:
        try:
            rel = _safe_rel(raw, label="staged path")
        except W1BackendError:
            skipped.append(f"{raw}: unsafe path")
            continue
        if not rel.endswith(".py"):
            skipped.append(f"{rel}: not a Python file")
        elif rgignore is not None and rgignore.ignored(rel):
            skipped.append(f"{rel}: ignored by .rgignore")
        else:
            chosen.add(rel)
    files = tuple(sorted(chosen))
    command = ("ruff", "check", "--no-cache", *files) if files else ()
    duplicate = ("python", "-m", "keel.duplicate_code", *files) if files else ()
    return StagedLintPlan(files=files, command=command,
                          duplicate_command=duplicate, skipped=tuple(sorted(skipped)))


# ---------------------------------------------------------------------------
# W1.8 -- portable dual CI configuration
# ---------------------------------------------------------------------------

_CI_JOB_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,49}$")


class PortableCIMirror:
    """Keeps GitHub Actions and GitLab CI job sets in lockstep (C11.1)."""

    def __init__(self, *, protected_branch: str = "main"):
        if not _CI_JOB_NAME_RE.fullmatch(protected_branch):
            raise W1BackendError(f"invalid branch name: {protected_branch!r}")
        self.protected_branch = protected_branch
        self._jobs: dict[str, dict[str, Any]] = {}

    def add_job(self, name: str, *, forge: str = "both",
                runs_on: str = "ubuntu-latest", steps: Iterable[str] = ()) -> None:
        if not _CI_JOB_NAME_RE.fullmatch(name):
            raise W1BackendError(f"invalid CI job name: {name!r}")
        if forge not in ("github", "gitlab", "both"):
            raise W1BackendError(f"unknown forge: {forge!r}")
        if name in self._jobs:
            raise W1BackendError(f"duplicate CI job: {name}")
        if not isinstance(runs_on, str) or not runs_on:
            raise W1BackendError("runs_on must be a non-empty string")
        self._jobs[name] = {
            "forges": ("github", "gitlab") if forge == "both" else (forge,),
            "runs_on": runs_on, "steps": tuple(steps),
        }

    def _for(self, forge: str) -> list[str]:
        return sorted(name for name, job in self._jobs.items() if forge in job["forges"])

    def github_workflow(self) -> str:
        lines = [
            "name: Keel CI",
            "on:",
            "  push:",
            f"    branches: [{self.protected_branch}]",
            "  pull_request:",
            f"    branches: [{self.protected_branch}]",
            "jobs:",
        ]
        for name in self._for("github"):
            job = self._jobs[name]
            lines += [f"  {name}:", f"    runs-on: {job['runs_on']}", "    steps:"]
            lines += [f"      - run: {json.dumps(step)}" for step in job["steps"]]
        return "\n".join(lines) + "\n"

    def gitlab_config(self) -> str:
        lines = ["stages: [test]", ""]
        for name in self._for("gitlab"):
            job = self._jobs[name]
            lines += [
                f"{name}:",
                "  stage: test",
                f"  tags: [{job['runs_on']}]",
                "  script:",
            ]
            lines += [f"    - {json.dumps(step)}" for step in job["steps"]]
            lines += [
                "  rules:",
                f"    - if: '$CI_COMMIT_BRANCH == \"{self.protected_branch}\"'",
                "",
            ]
        return "\n".join(lines) + "\n"

    def parity_report(self) -> dict[str, Any]:
        github, gitlab = self._for("github"), self._for("gitlab")
        return {
            "jobs": sorted(self._jobs),
            "github": github, "gitlab": gitlab,
            "missing_in_github": sorted(set(gitlab) - set(github)),
            "missing_in_gitlab": sorted(set(github) - set(gitlab)),
            "protected_branch": self.protected_branch,
            "ok": set(github) == set(gitlab),
        }

    def validate(self) -> dict[str, Any]:
        report = self.parity_report()
        if not report["ok"]:
            raise W1BackendError(f"CI job drift: {report}")
        return report


# ---------------------------------------------------------------------------
# W1.9 / W1.12 -- single-source i18n docs and brand guidelines
# ---------------------------------------------------------------------------

I18N_DOCS: tuple[str, ...] = ("README", "CONTRIBUTING", "SAFETY", "BRAND_GUIDELINES")
_LOCALE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")


def _strip_yaml_comment(text: str) -> str:
    quote = ""
    for index, char in enumerate(text):
        if quote:
            if char == quote and (index == 0 or text[index - 1] != "\\"):
                quote = ""
        elif char in ("'", '"'):
            quote = char
        elif char == "#" and (index == 0 or text[index - 1].isspace()):
            return text[:index]
    return text


def _yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        inner = value[1:-1]
        return inner.replace("''", "'") if value[0] == "'" else inner.replace('\\"', '"')
    if value[0] in ("'", '"') and value[-1] != value[0]:
        raise W1BackendError(f"unbalanced YAML quote: {value!r}")
    return value


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the restricted YAML subset used by ``*.i18n.yaml`` sources.

    Supports nested mappings, quoted scalars, ``#`` comments and ``|`` block
    scalars.  Tabs, duplicate keys and unbalanced quoting are rejected.
    """
    if not isinstance(text, str):
        raise W1BackendError("YAML source must be text")
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        index += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if "\t" in raw[:indent]:
            raise W1BackendError("tabs are not allowed for YAML indentation")
        content = _strip_yaml_comment(raw.strip()).strip()
        if not content:
            continue
        match = re.fullmatch(r"([^:#]+):(?:\s*(.*))?", content)
        if not match:
            raise W1BackendError(f"unsupported YAML line: {raw!r}")
        key, value = match.group(1).strip(), (match.group(2) or "").strip()
        if not key:
            raise W1BackendError(f"empty YAML key: {raw!r}")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            raise W1BackendError(f"invalid YAML indentation: {raw!r}")
        parent = stack[-1][1]
        if key in parent:
            raise W1BackendError(f"duplicate YAML key: {key}")
        if value == "|":
            block: list[str] = []
            while index < len(lines):
                candidate = lines[index]
                if candidate.strip() and len(candidate) - len(candidate.lstrip(" ")) <= indent:
                    break
                block.append(candidate.strip())
                index += 1
            parent[key] = "\n".join(block).strip()
        elif value:
            parent[key] = _yaml_scalar(value)
        else:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
    return root


def _flatten(mapping: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in mapping.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flat.update(_flatten(value, name))
        elif isinstance(value, str):
            flat[name] = value
        else:
            raise W1BackendError(f"non-string YAML value at {name!r}")
    return flat


class I18nDocumentStore:
    """Stores YAML string sources and renders localized Markdown/HTML."""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, dict[str, str]]] = {}

    @staticmethod
    def _check(doc: str, locale: str) -> None:
        if doc not in I18N_DOCS:
            raise W1BackendError(f"unknown i18n document: {doc!r}")
        if not isinstance(locale, str) or not _LOCALE_RE.fullmatch(locale):
            raise W1BackendError(f"invalid locale: {locale!r}")

    def load_yaml(self, doc: str, locale: str, text: str, *,
                  base_locale: str = "en") -> dict[str, str]:
        self._check(doc, locale)
        self._check(doc, base_locale)
        fields = _flatten(parse_simple_yaml(text))
        self._docs.setdefault(doc, {}).setdefault(locale, {}).update(fields)
        return dict(fields)

    def locales(self, doc: str) -> list[str]:
        if doc not in I18N_DOCS:
            raise W1BackendError(f"unknown i18n document: {doc!r}")
        return sorted(self._docs.get(doc, {}))

    def _chain(self, doc: str, locale: str) -> list[str]:
        self._check(doc, locale)
        chain = [locale]
        if "-" in locale:
            chain.append(locale.split("-", 1)[0])
        for fallback in ("en",):
            if fallback not in chain:
                chain.append(fallback)
        return chain

    def get(self, doc: str, field: str, locale: str = "en") -> str | None:
        for candidate in self._chain(doc, locale):
            value = self._docs.get(doc, {}).get(candidate, {}).get(field)
            if value is not None:
                return value
        return None

    def missing_keys(self, doc: str, locale: str) -> list[str]:
        """Keys absent from the locale's own source (fallback does not hide gaps)."""
        base = self._docs.get(doc, {}).get("en", {})
        own = self._docs.get(doc, {}).get(locale, {})
        language = locale.split("-", 1)[0]
        inherited = self._docs.get(doc, {}).get(language, {}) if language != locale else {}
        return sorted(key for key in base if key not in own and key not in inherited)

    def render_markdown(self, doc: str, locale: str = "en") -> str:
        keys = sorted(self._docs.get(doc, {}).get("en", {}))
        parts = [f"# {doc} ({locale})", ""]
        for key in keys:
            parts += [f"## {key}", "", self.get(doc, key, locale) or "", ""]
        return "\n".join(parts) + "\n"

    def render_html(self, doc: str, locale: str = "en") -> str:
        keys = sorted(self._docs.get(doc, {}).get("en", {}))
        parts = [f"<h1>{html.escape(doc)} ({html.escape(locale)})</h1>", "<dl>"]
        for key in keys:
            parts.append(
                f"<dt>{html.escape(key)}</dt><dd>{html.escape(self.get(doc, key, locale) or '')}</dd>"
            )
        parts.append("</dl>")
        return "\n".join(parts) + "\n"

    @staticmethod
    def document_files(doc: str, locales: Iterable[str] = ("en", "zh")) -> dict[str, str]:
        if doc not in I18N_DOCS:
            raise W1BackendError(f"unknown i18n document: {doc!r}")
        files = {f"{doc}.i18n.yaml": "en", f"{doc}.md": "en"}
        for locale in locales:
            I18nDocumentStore._check(doc, locale)
            if locale != "en":
                files[f"{doc}.{locale}.md"] = locale
        return files


_BRAND_SECTIONS: tuple[str, ...] = ("name", "tagline", "logo", "colors", "usage", "prohibited")


class BrandGuidelines:
    """Brand/usage rules rendered into the public website (C11.7)."""

    def __init__(self, sections: Mapping[str, str], *, locale: str = "en"):
        self.sections = dict(sections)
        self.locale = locale
        I18nDocumentStore._check("BRAND_GUIDELINES", locale)

    @classmethod
    def from_yaml(cls, text: str, *, locale: str = "en") -> "BrandGuidelines":
        return cls(_flatten(parse_simple_yaml(text)), locale=locale)

    def validate(self) -> list[str]:
        return sorted(
            section for section in _BRAND_SECTIONS
            if not isinstance(self.sections.get(section), str)
            or not self.sections[section].strip()
        )

    def render_markdown(self) -> str:
        parts = [f"# Brand guidelines ({self.locale})", ""]
        for section in sorted(self.sections):
            parts += [f"## {section}", "", self.sections[section].strip(), ""]
        return "\n".join(parts) + "\n"

    def render_html(self) -> str:
        parts = ["<h1>Brand guidelines</h1>", "<dl>"]
        for section in sorted(self.sections):
            parts.append(
                f"<dt>{html.escape(section)}</dt>"
                f"<dd>{html.escape(self.sections[section].strip())}</dd>"
            )
        return "\n".join(parts) + "</dl>\n"

    def website_filename(self, locale: str | None = None) -> str:
        target = locale or self.locale
        if not isinstance(target, str) or not _LOCALE_RE.fullmatch(target):
            raise W1BackendError(f"invalid locale: {target!r}")
        return f"BRAND_GUIDELINES.{target}.html"


# ---------------------------------------------------------------------------
# W1.11 -- stability channel / developer-preview banner
# ---------------------------------------------------------------------------

STABILITY_CHANNELS: tuple[str, ...] = ("stable", "beta", "dev", "experimental")
_EXPERIMENTAL_LABELS: frozenset[str] = frozenset(
    {"experimental", "preview", "unstable", "internal", "breaking"}
)
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class StabilityInfo:
    version: str
    channel: str
    labels: tuple[str, ...]
    preview: bool
    banner: str
    breaking_changes_allowed: bool
    about: dict[str, Any]


def stability_info(version: str, channel: str = "stable", *,
                   labels: Iterable[str] = ()) -> StabilityInfo:
    """Compute the About-channel descriptor and preview banner (X6.10)."""
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise W1BackendError(f"invalid version string: {version!r}")
    if not isinstance(channel, str) or channel.lower() not in STABILITY_CHANNELS:
        raise W1BackendError(f"unknown stability channel: {channel!r}")
    channel = channel.lower()
    cleaned = tuple(sorted({str(label).strip().lower() for label in labels}))
    unknown = [label for label in cleaned if label not in _EXPERIMENTAL_LABELS]
    if unknown:
        raise W1BackendError(f"unknown experimental labels: {unknown}")
    preview = channel != "stable" or bool(cleaned)
    banner = ""
    if preview:
        banner = (
            f"Developer preview ({channel} {version}). "
            "Compatibility-breaking changes will happen. Do not rely on stable APIs."
        )
    breaking = channel in ("dev", "experimental") or "breaking" in cleaned
    about = {
        "version": version, "channel": channel, "labels": list(cleaned),
        "stability": "preview" if preview else "stable",
        "notice": banner or "Stable release: compatibility is preserved.",
    }
    return StabilityInfo(version=version, channel=channel, labels=cleaned,
                         preview=preview, banner=banner,
                         breaking_changes_allowed=breaking, about=about)


# ---------------------------------------------------------------------------
# W1.13 -- builder instruction files as instruction sources
# ---------------------------------------------------------------------------

class BuilderInstructionScanner:
    """Discovers/read AGENTS.md, CLAUDE.md and .agents/.claude docs safely."""

    _SKIP_DIRS = frozenset({".git", ".venv", "node_modules", "__pycache__", "vendor"})

    def __init__(self, root: str | Path, *, max_bytes: int = 262_144):
        self.root = Path(root).resolve()
        if not isinstance(max_bytes, int) or max_bytes < 1:
            raise W1BackendError("max_bytes must be positive")
        self.max_bytes = max_bytes
        self.issues: list[str] = []

    def discover(self) -> list[str]:
        if not self.root.is_dir():
            return []
        found: set[str] = set()
        for name in ("AGENTS.md", "CLAUDE.md"):
            candidate = self.root / name
            if candidate.is_file():
                found.add(name)
        for directory in (".agents", ".claude"):
            base = self.root / directory
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*.md")):
                if any(part in self._SKIP_DIRS for part in path.parts):
                    continue
                try:
                    rel = _within(self.root, str(path.relative_to(self.root))).relative_to(self.root).as_posix()
                except W1BackendError:
                    self.issues.append(f"instruction path escapes root: {path}")
                    continue
                found.add(rel)
        return sorted(found, key=lambda rel: (rel != "AGENTS.md", rel))

    def read(self, rel: str) -> str:
        path = _within(self.root, rel, label="instruction path")
        if not path.is_file():
            raise W1BackendError(f"instruction file missing: {rel}")
        if path.stat().st_size > self.max_bytes:
            raise W1BackendError(f"instruction file too large: {rel}")
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise W1BackendError(f"cannot read instruction file {rel}: {exc}") from None

    def load(self) -> dict[str, str]:
        """Return non-pointer instruction texts keyed by relative path."""
        self.issues = []
        loaded: dict[str, str] = {}
        discovered = self.discover()
        for rel in discovered:
            try:
                text = self.read(rel)
            except W1BackendError as exc:
                self.issues.append(str(exc))
                continue
            stripped = text.strip()
            is_pointer = bool(re.fullmatch(r"@?AGENTS\.md|[Ss]ee\s+AGENTS\.md\.?", stripped))
            if rel == "CLAUDE.md" and is_pointer:
                if "AGENTS.md" not in discovered:
                    self.issues.append("CLAUDE.md points to missing AGENTS.md")
                continue
            loaded[rel] = text
        return loaded

    def merged_instructions(self) -> str:
        loaded = self.load()
        return "".join(
            f"\n# Source: {rel}\n\n{text.strip()}\n" for rel, text in sorted(loaded.items())
        ).lstrip()


# ---------------------------------------------------------------------------
# W1.14 -- private plugin index instead of a public repository topic
# ---------------------------------------------------------------------------

class PrivatePluginIndex:
    """Reads a private JSON index; no public discovery mechanism (G7)."""

    def __init__(self, path: str | Path, *, root: str | Path | None = None):
        self.path = Path(path).resolve()
        self.root = Path(root).resolve() if root is not None else self.path.parent
        self._cache_key: tuple[int, int] | None = None
        self._cache: list[dict[str, Any]] = []

    @staticmethod
    def reject_public_topic(topic: str) -> None:
        if isinstance(topic, str) and "dsh-plugin" in topic.lower():
            raise PluginIndexError(
                "public repository-topic discovery is excluded (G7); "
                "use the private plugin index"
            )

    @staticmethod
    def validate_entry(entry: Any) -> list[str]:
        problems: list[str] = []
        if not isinstance(entry, Mapping):
            return ["entry is not an object"]
        name = entry.get("name")
        if not isinstance(name, str) or not _PLUGIN_NAME_RE.fullmatch(name):
            problems.append("invalid plugin name")
        version = entry.get("version")
        if not isinstance(version, str) or not _RELEASE_RE.fullmatch(version):
            problems.append("invalid plugin version")
        if entry.get("kind") not in PLUGIN_KINDS:
            problems.append("invalid plugin kind")
        try:
            _safe_rel(str(entry.get("path", "")), label="plugin path")
        except W1BackendError:
            problems.append("invalid or unsafe plugin path")
        tags = entry.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            problems.append("tags must be a list of strings")
        for key in ("topic", "repository_topic", "public_topic"):
            if "dsh-plugin" in str(entry.get(key, "")).lower():
                problems.append(f"public discovery key {key} is forbidden")
        if str(entry.get("discoverable_via", "")).lower() == "topic":
            problems.append("topic discovery is forbidden")
        return problems

    def _load(self) -> list[dict[str, Any]]:
        stat = self.path.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        if self._cache_key == key:
            return self._cache
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PluginIndexError(f"cannot read plugin index: {exc}") from None
        if not isinstance(doc, Mapping) or not isinstance(doc.get("plugins"), list):
            raise PluginIndexError("plugin index must be {'plugins': [...]}")
        entries: list[dict[str, Any]] = []
        names: set[str] = set()
        for raw in doc["plugins"]:
            problems = self.validate_entry(raw)
            if problems:
                raise PluginIndexError(f"invalid plugin entry: {problems}")
            name = raw["name"]
            if name in names:
                raise PluginIndexError(f"duplicate plugin name: {name}")
            names.add(name)
            resolved = _within(self.root, str(raw["path"]), label="plugin path")
            entry = dict(raw)
            entry["resolved_path"] = str(resolved)
            entries.append(entry)
        self._cache_key, self._cache = key, entries
        return entries

    def plugins(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._load()]

    def get(self, name: str) -> dict[str, Any] | None:
        for entry in self._load():
            if entry["name"] == name:
                return dict(entry)
        return None

    def search(self, *, kind: str | None = None, tag: str | None = None,
               query: str = "") -> list[dict[str, Any]]:
        if kind is not None and kind not in PLUGIN_KINDS:
            raise PluginIndexError(f"unknown plugin kind: {kind!r}")
        needle = query.strip().lower()
        return [
            dict(entry) for entry in self._load()
            if (kind is None or entry["kind"] == kind)
            and (tag is None or tag in entry.get("tags", []))
            and (not needle or needle in entry["name"].lower()
                 or needle in str(entry.get("description", "")).lower())
        ]


# ---------------------------------------------------------------------------
# W1.15 -- Python SDK and generated thin TypeScript client
# ---------------------------------------------------------------------------

_SDK_METHODS: dict[str, dict[str, Any]] = {
    "run": {
        "params": {"prompt": "str", "stream": "bool"},
        "defaults": {"stream": False},
        "returns": "RunResult",
    },
    "list_sessions": {"params": {}, "defaults": {}, "returns": "list[SessionSummary]"},
    "send": {
        "params": {"session_id": "str", "message": "str"},
        "defaults": {}, "returns": "TurnResult",
    },
}
_TS_TYPES: dict[str, str] = {
    "str": "string", "bool": "boolean", "int": "number", "float": "number",
    "list[str]": "string[]", "dict": "Record<string, unknown>",
}
_TYPE_CHECKS: dict[str, Any] = {
    "str": lambda value: isinstance(value, str),
    "bool": lambda value: isinstance(value, bool),
    "int": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "float": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "list[str]": lambda value: isinstance(value, list) and all(isinstance(v, str) for v in value),
    "dict": lambda value: isinstance(value, dict),
}


def python_sdk_surface() -> dict[str, Any]:
    return {
        name: {
            "params": dict(spec["params"]),
            "required": sorted(set(spec["params"]) - set(spec["defaults"])),
            "defaults": dict(spec["defaults"]),
            "returns": spec["returns"],
        }
        for name, spec in sorted(_SDK_METHODS.items())
    }


def validate_payload(method: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if method not in _SDK_METHODS:
        raise W1BackendError(f"unknown SDK method: {method!r}")
    spec = _SDK_METHODS[method]
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping):
        raise W1BackendError("SDK payload must be a mapping")
    unknown = sorted(set(payload) - set(spec["params"]))
    if unknown:
        raise W1BackendError(f"unknown SDK payload keys: {unknown}")
    result = dict(spec["defaults"])
    result.update(payload)
    for key, expected in spec["params"].items():
        if key not in result:
            raise W1BackendError(f"missing SDK payload key: {key}")
        if not _TYPE_CHECKS[expected](result[key]):
            raise W1BackendError(f"SDK payload key {key!r} must be {expected}")
    return result


def _ts_type(kind: str) -> str:
    if kind.startswith("list["):
        return _ts_type(kind[5:-1]) + "[]"
    return _TS_TYPES.get(kind, kind)


def typescript_client_source() -> str:
    """Generate the thin TS client from the Python SDK contract (X6.3)."""
    lines = [
        "// Generated from the Keel Python SDK contract (W1.15). Do not edit.",
        "export interface RunResult { output: string; exit_code: number }",
        "export interface SessionSummary { id: string; title: string }",
        "export interface TurnResult { session_id: string; text: string }",
        "export interface Bridge { call(method: string, payload: Record<string, unknown>): Promise<unknown> }",
        "export class KeelClient {",
        "  constructor(private readonly bridge: Bridge) {}",
    ]
    for method, spec in sorted(_SDK_METHODS.items()):
        args = []
        for name, kind in spec["params"].items():
            suffix = "?" if name in spec["defaults"] else ""
            args.append(f"{name}{suffix}: {_ts_type(kind)}")
        arg_text = ", ".join(args)
        payload_items = ", ".join(spec["params"])
        return_type = _ts_type(spec["returns"])
        lines += [
            f"  async {method}({arg_text}): Promise<{return_type}> {{",
            f"    return this.bridge.call({json.dumps(method)}, "
            f"{{{payload_items}}}) as Promise<{return_type}>;",
            "  }",
        ]
    lines += ["}", ""]
    return "\n".join(lines)


def sdk_compatibility(client_version: str, sdk_version: str) -> bool:
    """A thin client is compatible with the same SDK major and newer minor."""
    def parse(value: str) -> tuple[int, int]:
        if not isinstance(value, str):
            raise W1BackendError("SDK versions must be strings")
        match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.\d+)?", value.strip())
        if not match:
            raise W1BackendError(f"invalid SDK version: {value!r}")
        return int(match.group(1)), int(match.group(2))

    client_major, client_minor = parse(client_version)
    sdk_major, sdk_minor = parse(sdk_version)
    return client_major == sdk_major and client_minor <= sdk_minor


# ---------------------------------------------------------------------------
# W1.16 -- vendored dependencies and patch accounting
# ---------------------------------------------------------------------------

def valid_vendor_license_text(text: str) -> bool:
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    return len(stripped) >= 40 and bool(
        re.search(r"copyright|permission|license", stripped, re.IGNORECASE)
    )


class VendorPolicy:
    """Audits vendor/ licenses and PATCHES.md entries (M0 policy)."""

    def __init__(self, root: str | Path, *, vendor_dir: str = "vendor",
                 patches_file: str = "PATCHES.md"):
        self.root = Path(root).resolve()
        self.vendor_path = self.root / _safe_rel(vendor_dir, label="vendor dir")
        self.patches_path = self.root / _safe_rel(patches_file, label="patches file")

    @staticmethod
    def parse_patches(text: str) -> dict[str, dict[str, str]]:
        entries: dict[str, dict[str, str]] = {}
        current: str | None = None
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("## "):
                current = line[3:].strip().lower()
                if not current or current in entries:
                    raise W1BackendError(f"invalid or duplicate patch section: {line!r}")
                entries[current] = {}
            elif current and line.startswith("- "):
                key, sep, value = line[2:].partition(":")
                if sep:
                    entries[current][key.strip().lower()] = value.strip()
        return entries

    def audit(self) -> dict[str, Any]:
        violations: list[str] = []
        if not self.vendor_path.is_dir():
            violations.append("vendor/ directory missing")
            packages: list[str] = []
        else:
            packages = sorted(
                path.name for path in self.vendor_path.iterdir()
                if path.is_dir() and not path.is_symlink()
            )
        if not self.patches_path.is_file():
            violations.append("PATCHES.md missing")
            patches: dict[str, dict[str, str]] = {}
        else:
            patches = self.parse_patches(self.patches_path.read_text(encoding="utf-8"))

        for package in packages:
            package_dir = self.vendor_path / package
            licenses = [p for p in package_dir.iterdir()
                        if p.is_file() and p.name.lower().startswith("license")]
            if not licenses or not any(
                valid_vendor_license_text(p.read_text(encoding="utf-8", errors="replace"))
                for p in licenses
            ):
                violations.append(f"{package}: missing or invalid LICENSE")
            entry = patches.get(package.lower())
            if entry is None:
                violations.append(f"{package}: missing PATCHES.md entry")
            else:
                for field in ("upstream", "issue"):
                    if not entry.get(field):
                        violations.append(f"{package}: PATCHES.md missing {field}")
            if any(p.suffix == ".patch" for p in package_dir.iterdir()):
                if entry is None:
                    violations.append(f"{package}: local patch file has no PATCHES.md entry")
        for name in sorted(set(patches) - {p.lower() for p in packages}):
            violations.append(f"orphan PATCHES.md entry: {name}")

        return {
            "ok": not violations, "packages": packages,
            "patches": sorted(patches), "violations": sorted(violations),
        }


# ---------------------------------------------------------------------------
# W1.17 -- feedback channels and redacted bundle
# ---------------------------------------------------------------------------

ALLOWED_FEEDBACK_CHANNELS: tuple[str, ...] = ("email", "in-app")
_FORBIDDEN_MARKERS: tuple[str, ...] = (
    "discord", "issues tab", "github.com/", "gitlab.com/", "source link",
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_TOKEN_RE = re.compile(r"\b(?:sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9]{12,}|AKIA[0-9A-Z]{12,})\b")
_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd)\b\s*[:=]\s*[\"']?([^\s\"',;]{4,})"
)
_URL_RE = re.compile(r"https?://[^\s\"'<>)]+")
_BARE_REPO_RE = re.compile(r"(?i)\b(?:github|gitlab)\.com/[A-Za-z0-9_.\-/]+")
_WIN_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+")
_UNIX_PATH_RE = re.compile(r"(?<![\w])/(?:home|Users|root|tmp|var|etc)/[^\s\"'<>]+")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def feedback_policy() -> dict[str, Any]:
    return {
        "channels": list(ALLOWED_FEEDBACK_CHANNELS),
        "forbidden": list(_FORBIDDEN_MARKERS),
        "bundle": "redacted in-app bundle; public docs site only, no source links",
    }


def redact_feedback(text: str, *, allowed_urls: Iterable[str] = ()) -> tuple[str, dict[str, int]]:
    """Strip secrets, PII, paths and source links from a feedback payload."""
    if not isinstance(text, str):
        raise W1BackendError("feedback text must be a string")
    allowed = tuple(allowed_urls)
    counts: dict[str, int] = {}
    result = text

    def sub(pattern: re.Pattern[str], replacement: Any, label: str,
            *, preserve: Any = None) -> None:
        nonlocal result
        found: list[str] = []

        def replace(match: re.Match[str]) -> str:
            original = match.group(0)
            if preserve is not None and preserve(original):
                return original
            found.append(original)
            return replacement if isinstance(replacement, str) else replacement(match)

        result = pattern.sub(replace, result)
        if found:
            counts[label] = counts.get(label, 0) + len(found)

    sub(_TOKEN_RE, "[REDACTED_TOKEN]", "tokens")
    sub(_SECRET_RE, lambda m: f"{m.group(1)}=[REDACTED]", "secrets")
    sub(_EMAIL_RE, "[REDACTED_EMAIL]", "emails")
    sub(_URL_RE, "[REDACTED_URL]", "urls",
        preserve=lambda url: any(url == a or url.startswith(a) for a in allowed))
    sub(_BARE_REPO_RE, "[REDACTED_SOURCE_LINK]", "source_links")
    sub(_WIN_PATH_RE, "[REDACTED_PATH]", "paths")
    sub(_UNIX_PATH_RE, "[REDACTED_PATH]", "paths")
    sub(_IPV4_RE, "[REDACTED_IP]", "ips")
    return result, counts


def build_feedback_bundle(text: str, *, channel: str = "in-app",
                          docs_site: str = "https://docs.keel.example",
                          allowed_urls: Iterable[str] | None = None) -> dict[str, Any]:
    if channel not in ALLOWED_FEEDBACK_CHANNELS:
        raise W1BackendError(f"feedback channel not allowed: {channel!r}")
    allow = set(allowed_urls) if allowed_urls is not None else set()
    allow.add(docs_site)
    redacted, counts = redact_feedback(text, allowed_urls=allow)
    lowered = text.lower()
    violations = sorted({marker for marker in _FORBIDDEN_MARKERS if marker in lowered})
    return {
        "channel": channel, "redacted": redacted, "redactions": counts,
        "violations": violations, "safe_to_send": not violations,
        "docs_site": docs_site,
    }
