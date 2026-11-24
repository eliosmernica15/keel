"""keel.d6_reliability_backend -- additive, stdlib-only backend for the D6 builder constitution.

The 25 ``not_started`` D6 rows of ``PLAN-INDEX.json`` all come from section 7 of
``Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md`` ("Builder
constitution").  This module implements the rows that have a machine-checkable
backend behaviour; the remaining rows are human/owner process conventions and
are classified with reasons in ``master-plan-v6-d6-backend-evidence.md``.

Implemented rows and their concrete surface:

  D6.1   :class:`ApiChangeRecorder`, :func:`check_upgrade_guide`,
         :class:`SchemaVersion`, :func:`assert_monotonic`
  D6.3   :class:`EventCatalog`, :func:`assert_never`
  D6.4   :func:`resolve`, :func:`run`, :func:`find_hidden_defaults`
  D6.5   :class:`PluginTunables`, :func:`lint_plugin_source`
  D6.6   :class:`ReferenceRegistry`, :func:`load_with_references`
  D6.7   SessionId/... ``NewType`` ids, :func:`audit_id_annotations`
  D6.8   :class:`BoundaryRegistry`, :func:`trust`
  D6.9   :class:`CastBaseline`, :func:`scan_cast_calls`
  D6.10  :func:`classify_path`, :class:`ImportGate`
  D6.11  :class:`KeelError` hierarchy, :func:`audit_except_handlers`
  D6.12  :func:`audit_docstrings`, :func:`find_restating_comments`
  D6.13  :class:`DocCoverageChecker`
  D6.15  :class:`SnapshotRegistry`, :func:`assert_keyless`
  D6.16  :func:`validate_projection`, :class:`SdkProjectionValidator`
  D6.19  :class:`VendorManifest`, :func:`render_vendor_manifest`
  D6.22  :func:`scan_markers`, :func:`assert_release_ready`
  D6.24  :class:`TypingAudit`
  D6.25  :class:`GateRegistry`, :func:`top_level_gate`

Design rules (shared by every section):

* **Stdlib only, no ambient I/O.** No network, subprocess, filesystem access,
  SQL, credentials or import-time side effects. Source checks operate on text
  passed in by the caller, so results are reproducible on every platform.
* **Real behaviour, not a flag.** Every feature computes a verdict from the
  supplied data; there is no unconditional ``True`` success.
* **Fail closed.** Missing/bad input raises a typed :class:`KeelError` subclass
  carrying a stable ``code``. Unknown boundaries, unknown references and
  unknown gate inputs are rejected.
* **Deterministic.** All ids/fingerprints are SHA-256 prefixes of canonical
  JSON; every tuple/list output is sorted; no clock, uuid or random values.
* **Additive.** No existing source file, test, settings schema or registry is
  edited by this module.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import io
import json
import re
import tokenize
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, NoReturn, Sequence
from typing import NewType


# ---------------------------------------------------------------------------
# shared helpers + typed error hierarchy (D6.11)
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    """Canonical UTF-8 JSON bytes; the only hashing primitive in this module."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def fingerprint(value: Any) -> str:
    """Stable 16-hex-character fingerprint of any JSON-serialisable value."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()[:16]


class KeelError(ValueError):
    """Base class for every typed Keel failure (D6.11).

    ``code`` is a stable, machine-readable identifier.  Subclasses set
    ``DEFAULT_CODE``; callers may override it only when narrowing a failure.
    ``details`` is structured context, never a formatted user string.
    """

    DEFAULT_CODE: str = "D6.11.KEEL_ERROR"

    def __init__(self, message: str, *, code: str | None = None,
                 details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.DEFAULT_CODE
        self.details: dict[str, Any] = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        """Machine-readable form suitable for a JSON error envelope."""
        return {
            "type": type(self).__name__,
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ApiStabilityError(KeelError):
    DEFAULT_CODE = "D6.1.API_CHANGE_UNRECORDED"


class SchemaVersionError(KeelError):
    DEFAULT_CODE = "D6.1.SCHEMA_VERSION_NOT_MONOTONIC"


class EventUnionError(KeelError):
    DEFAULT_CODE = "D6.3.EVENT_UNION_NOT_EXHAUSTIVE"


class ResolutionError(KeelError):
    DEFAULT_CODE = "D6.4.IMPLICIT_DEFAULT"


class PluginConfigError(KeelError):
    DEFAULT_CODE = "D6.5.PLUGIN_TUNABLE_INVALID"


class MisconfigurationError(KeelError):
    DEFAULT_CODE = "D6.6.MISSING_REFERENT"


class TypedIdError(KeelError):
    DEFAULT_CODE = "D6.7.BARE_CROSS_BOUNDARY_ID"


class BoundaryError(KeelError):
    DEFAULT_CODE = "D6.8.UNVALIDATED_BOUNDARY"


class CastBaselineError(KeelError):
    DEFAULT_CODE = "D6.9.NEW_UNRECORDED_CAST"


class PlaneError(KeelError):
    DEFAULT_CODE = "D6.10.MIXED_SOURCE_ARTIFACT_PLANE"


class UntrustedStateError(KeelError):
    DEFAULT_CODE = "D6.11.UNTRUSTED_STATE"


class UnknownOutcomeError(KeelError):
    DEFAULT_CODE = "D6.11.UNKNOWN_OUTCOME"


class EmptyExceptError(KeelError):
    DEFAULT_CODE = "D6.11.UNNAMED_EMPTY_EXCEPT"


class DocstringError(KeelError):
    DEFAULT_CODE = "D6.12.PUBLIC_EXPORT_UNDOCUMENTED"


class DocSyncError(KeelError):
    DEFAULT_CODE = "D6.13.DOCS_OUT_OF_SYNC"


class SnapshotError(KeelError):
    DEFAULT_CODE = "D6.15.SNAPSHOT_FIXTURE_INVALID"


class SdkProjectionError(KeelError):
    DEFAULT_CODE = "D6.16.SDK_PROJECTION_STALE"


class VendorManifestError(KeelError):
    DEFAULT_CODE = "D6.19.VENDOR_MANIFEST_STALE"


class MarkerError(KeelError):
    DEFAULT_CODE = "D6.22.OPEN_FIXME"


class TypingAuditError(KeelError):
    DEFAULT_CODE = "D6.24.UNTYPED_PUBLIC_SYMBOL"


class GateError(KeelError):
    DEFAULT_CODE = "D6.25.GATE_NOT_PROVEN"


def all_error_codes() -> dict[str, type[KeelError]]:
    """Return every declared ``code -> exception class`` pair (no side effects)."""
    found: dict[str, type[KeelError]] = {}

    def walk(cls: type[KeelError]) -> None:
        found.setdefault(cls.DEFAULT_CODE, cls)
        for child in cls.__subclasses__():
            walk(child)

    walk(KeelError)
    return dict(sorted(found.items()))


def fail_on_untrusted(state_name: str, detail: str = "") -> NoReturn:
    """Stop dependent work when state came from outside the trust boundary."""
    raise UntrustedStateError(
        f"untrusted state {state_name!r}; dependent work stopped",
        details={"state": state_name, "detail": detail},
    )


def fail_on_unknown_outcome(operation: str, detail: str = "") -> NoReturn:
    """Stop instead of guessing the outcome of an operation."""
    raise UnknownOutcomeError(
        f"unknown outcome for {operation!r}; dependent work stopped",
        details={"operation": operation, "detail": detail},
    )


def _nonblank(value: Any, label: str, error: type[KeelError]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error(f"{label} must be a non-empty string", details={"label": label})
    return value.strip()


def _as_text_tuple(value: Iterable[str], label: str, error: type[KeelError]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise error(f"{label} must be a sequence of strings, not a bare string")
    result = tuple(sorted(v for v in (str(item) for item in value) if v))
    if len(result) != len(set(result)):
        raise error(f"{label} contains duplicates", details={"label": label})
    return result


# ===========================================================================
# D6.1 -- public API change recorder, upgrade guide, monotonic schema version
# ===========================================================================


class ChangeKind(str, Enum):
    BREAKING = "breaking"
    ADDITIVE = "additive"
    DEPRECATION = "deprecation"
    FIX = "fix"


@dataclass(frozen=True)
class ApiChange:
    """One externally perceptible change to a public API."""

    change_id: str
    symbol: str
    kind: ChangeKind
    summary: str
    upgrade_note: str = ""
    consumers_updated: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonblank(self.change_id, "change_id", ApiStabilityError)
        _nonblank(self.symbol, "symbol", ApiStabilityError)
        _nonblank(self.summary, "summary", ApiStabilityError)
        if not isinstance(self.kind, ChangeKind):
            raise ApiStabilityError("kind must be a ChangeKind",
                                    details={"kind": repr(self.kind)})
        consumers = _as_text_tuple(self.consumers_updated, "consumers_updated",
                                   ApiStabilityError)
        object.__setattr__(self, "consumers_updated", consumers)
        if self.kind in (ChangeKind.BREAKING, ChangeKind.DEPRECATION):
            _nonblank(self.upgrade_note, "upgrade_note", ApiStabilityError)

    @property
    def guide_marker(self) -> str:
        """The token that must be present in ``UPGRADE.md``."""
        return self.change_id

    @property
    def digest(self) -> str:
        return fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "symbol": self.symbol,
            "kind": self.kind.value,
            "summary": self.summary,
            "upgrade_note": self.upgrade_note,
            "consumers_updated": list(self.consumers_updated),
        }


@dataclass(frozen=True)
class ApiChangeValidation:
    ok: bool
    missing_consumers: Mapping[str, tuple[str, ...]]
    unrecorded_breaking: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "missing_consumers": {k: list(v) for k, v in self.missing_consumers.items()},
            "unrecorded_breaking": list(self.unrecorded_breaking),
        }


class ApiChangeRecorder:
    """Records public-API changes and checks consumer + upgrade-guide duties."""

    def __init__(self, known_consumers: Iterable[str] = ()) -> None:
        self._known = frozenset(_as_text_tuple(known_consumers, "known_consumers",
                                               ApiStabilityError))
        self._changes: dict[str, ApiChange] = {}

    @property
    def changes(self) -> tuple[ApiChange, ...]:
        return tuple(self._changes[key] for key in sorted(self._changes))

    def record(self, change: ApiChange) -> ApiChange:
        if not isinstance(change, ApiChange):
            raise ApiStabilityError("record() requires an ApiChange")
        if change.change_id in self._changes:
            raise ApiStabilityError("duplicate change_id",
                                    details={"change_id": change.change_id})
        self._changes[change.change_id] = change
        return change

    def breaking_changes(self) -> tuple[ApiChange, ...]:
        return tuple(c for c in self.changes
                     if c.kind in (ChangeKind.BREAKING, ChangeKind.DEPRECATION))

    def validate(self) -> ApiChangeValidation:
        missing: dict[str, tuple[str, ...]] = {}
        for change in self.changes:
            skipped = tuple(sorted(self._known - set(change.consumers_updated)))
            if skipped:
                missing[change.change_id] = skipped
        unrecorded = tuple(c.change_id for c in self.breaking_changes()
                           if not c.upgrade_note)
        return ApiChangeValidation(not missing and not unrecorded,
                                   dict(sorted(missing.items())), unrecorded)

    def upgrade_guide_missing(self, guide_text: str) -> tuple[str, ...]:
        if not isinstance(guide_text, str):
            raise ApiStabilityError("guide_text must be a string")
        return tuple(sorted(c.guide_marker for c in self.breaking_changes()
                            if c.guide_marker not in guide_text))


def check_upgrade_guide(changes: Iterable[ApiChange], guide_text: str) -> tuple[str, ...]:
    """Return ids of breaking changes not represented in the upgrade guide."""
    recorder = ApiChangeRecorder()
    for change in changes:
        recorder.record(change)
    return recorder.upgrade_guide_missing(guide_text)


@dataclass(frozen=True, order=True)
class SchemaVersion:
    """A positive, monotonic SQLite schema version."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 1:
            raise SchemaVersionError("schema version must be a positive integer",
                                     details={"value": repr(self.value)})

    def next(self) -> SchemaVersion:
        return SchemaVersion(self.value + 1)


def assert_monotonic(old: SchemaVersion, new: SchemaVersion) -> None:
    """Reject equal or decreasing schema versions."""
    if not isinstance(old, SchemaVersion) or not isinstance(new, SchemaVersion):
        raise SchemaVersionError("both arguments must be SchemaVersion values")
    if new.value <= old.value:
        raise SchemaVersionError("schema version must strictly increase",
                                 details={"old": old.value, "new": new.value})


def scan_schema_version(source: str) -> int:
    """Read a literal ``SCHEMA_VERSION = <int>`` assignment; fail if absent."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SchemaVersionError("source is not valid Python", details={"line": exc.lineno}) from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SCHEMA_VERSION" for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int) \
                    and not isinstance(node.value.value, bool):
                return node.value.value
            raise SchemaVersionError("SCHEMA_VERSION must be an integer literal",
                                     details={"line": node.lineno})
    raise SchemaVersionError("SCHEMA_VERSION assignment not found")


# ===========================================================================
# D6.3 -- typed events, documented modes/payloads, exhaustive closed unions
# ===========================================================================


class EventMode(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"


class UnionStyle(str, Enum):
    CLOSED = "closed"
    EXTENSIBLE = "extensible"


@dataclass(frozen=True)
class EventSpec:
    name: str
    mode: EventMode
    payload_fields: tuple[str, ...]
    style: UnionStyle
    description: str
    default_behavior: str = ""

    def __post_init__(self) -> None:
        _nonblank(self.name, "name", EventUnionError)
        _nonblank(self.description, "description", EventUnionError)
        if not isinstance(self.mode, EventMode) or not isinstance(self.style, UnionStyle):
            raise EventUnionError("mode and style must be enums")
        fields = _as_text_tuple(self.payload_fields, "payload_fields", EventUnionError)
        if not fields:
            raise EventUnionError("an event must document at least one payload field")
        object.__setattr__(self, "payload_fields", fields)
        if self.style is UnionStyle.CLOSED and self.default_behavior:
            raise EventUnionError("a closed union must not declare a default behavior")
        if self.style is UnionStyle.EXTENSIBLE:
            _nonblank(self.default_behavior, "default_behavior", EventUnionError)

    @property
    def digest(self) -> str:
        return fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "mode": self.mode.value,
            "payload_fields": list(self.payload_fields), "style": self.style.value,
            "description": self.description, "default_behavior": self.default_behavior,
        }


@dataclass(frozen=True)
class EventDispatch:
    matched: bool
    used_default: bool
    missing_fields: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return (self.matched or self.used_default) and not self.missing_fields


@dataclass(frozen=True)
class EventCatalogReport:
    ok: bool
    issues: tuple[str, ...]


class EventCatalog:
    """A registry of typed events with mode + payload documentation."""

    def __init__(self) -> None:
        self._events: dict[str, EventSpec] = {}

    def register(self, spec: EventSpec) -> EventSpec:
        if not isinstance(spec, EventSpec):
            raise EventUnionError("register() requires an EventSpec")
        if spec.name in self._events:
            raise EventUnionError("duplicate event name", details={"name": spec.name})
        self._events[spec.name] = spec
        return spec

    def get(self, name: str) -> EventSpec:
        try:
            return self._events[name]
        except KeyError as exc:
            raise EventUnionError("unknown event", details={"name": name}) from exc

    @property
    def specs(self) -> tuple[EventSpec, ...]:
        return tuple(self._events[k] for k in sorted(self._events))

    def validate(self) -> EventCatalogReport:
        issues: list[str] = []
        modes: set[EventMode] = set()
        for spec in self.specs:
            modes.add(spec.mode)
            if spec.style is UnionStyle.CLOSED and not spec.description:
                issues.append(f"{spec.name}: undocumented closed event")
        if len(modes) < len(EventMode):
            issues.append("catalog does not document every EventMode")
        return EventCatalogReport(not issues, tuple(sorted(issues)))

    def dispatch(self, name: str, payload: Mapping[str, Any]) -> EventDispatch:
        if not isinstance(payload, Mapping):
            raise EventUnionError("event payload must be a mapping")
        if name not in self._events:
            # An extensible union uses its documented default for unknown names.
            fallback = [s for s in self.specs if s.style is UnionStyle.EXTENSIBLE]
            if not fallback:
                raise EventUnionError("unknown event in a closed union",
                                      details={"name": name})
            spec = fallback[0]
            return EventDispatch(False, True, tuple(sorted(
                f for f in spec.payload_fields if f not in payload)))
        spec = self._events[name]
        missing = tuple(f for f in spec.payload_fields if f not in payload)
        return EventDispatch(True, False, missing)


def assert_never(value: NoReturn) -> NoReturn:
    """Runtime twin of typing.assert_never for closed-union tails."""
    raise EventUnionError("unhandled member of a closed union",
                          details={"value": repr(value)})


def render_mode(mode: EventMode) -> str:
    """Exhaustive dispatch over the closed EventMode union."""
    if mode is EventMode.REQUEST:
        return "->"
    if mode is EventMode.RESPONSE:
        return "<-"
    if mode is EventMode.NOTIFICATION:
        return "!!"
    return assert_never(mode)  # type: ignore[arg-type]


# ===========================================================================
# D6.4 -- explicit resolve(request) -> Spec; no hidden defaults inside run()
# ===========================================================================


DEFAULT_MODEL = "keel-default"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.0


@dataclass(frozen=True)
class Request:
    """A partially specified caller request; defaults are *not* applied here."""

    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Spec:
    """A fully resolved request.  Every applied default is recorded."""

    model: str
    max_tokens: int
    temperature: float
    metadata: Mapping[str, str]
    applied_defaults: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model, "max_tokens": self.max_tokens,
            "temperature": self.temperature, "metadata": dict(self.metadata),
            "applied_defaults": list(self.applied_defaults),
        }


def resolve(request: Request) -> Spec:
    """Apply defaults in one explicit step and record which ones were applied."""
    if not isinstance(request, Request):
        raise ResolutionError("resolve() requires a Request")
    if not isinstance(request.metadata, Mapping):
        raise ResolutionError("metadata must be a mapping")
    applied: list[str] = []
    model = request.model
    if model is None:
        model = DEFAULT_MODEL
        applied.append("model")
    elif not isinstance(model, str) or not model.strip():
        raise ResolutionError("model must be a non-empty string when supplied")
    max_tokens = request.max_tokens
    if max_tokens is None:
        max_tokens = DEFAULT_MAX_TOKENS
        applied.append("max_tokens")
    elif isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
        raise ResolutionError("max_tokens must be a positive integer when supplied")
    temperature = request.temperature
    if temperature is None:
        temperature = DEFAULT_TEMPERATURE
        applied.append("temperature")
    elif isinstance(temperature, bool) or not isinstance(temperature, (int, float)) \
            or not 0.0 <= float(temperature) <= 2.0:
        raise ResolutionError("temperature must be between 0 and 2 when supplied")
    for key, value in request.metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ResolutionError("metadata keys and values must be strings")
    return Spec(model=model, max_tokens=max_tokens, temperature=float(temperature),
                metadata=dict(request.metadata), applied_defaults=tuple(applied))


def run(spec: Spec) -> str:
    """Consume a resolved Spec only; unresolved Requests are refused loudly."""
    if not isinstance(spec, Spec):
        raise ResolutionError("run() requires a resolved Spec; call resolve(request) first",
                              details={"received": type(spec).__name__})
    return json.dumps(spec.to_dict(), sort_keys=True, separators=(",", ":"))


def find_hidden_defaults(source: str) -> tuple[str, ...]:
    """Find ``x or <default>`` fallbacks inside functions named ``run``."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ResolutionError("source is not valid Python", details={"line": exc.lineno}) from exc
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != "run":
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.BoolOp) and isinstance(child.op, ast.Or):
                findings.append(f"{child.lineno}: hidden 'or' default inside run()")
    return tuple(sorted(set(findings)))


# ===========================================================================
# D6.5 -- no hardcoded tunables in plugins; validated config + allowlist
# ===========================================================================


@dataclass(frozen=True)
class PluginTunables:
    """Deployment-varying plugin choices; all fields validated at load."""

    timeout_ms: int
    max_retries: int
    backoff_factor: float

    def __post_init__(self) -> None:
        if isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int) \
                or not 1 <= self.timeout_ms <= 600_000:
            raise PluginConfigError("timeout_ms must be an integer in [1, 600000]")
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int) \
                or not 0 <= self.max_retries <= 10:
            raise PluginConfigError("max_retries must be an integer in [0, 10]")
        if isinstance(self.backoff_factor, bool) or not isinstance(self.backoff_factor, (int, float)) \
                or not 1.0 <= float(self.backoff_factor) <= 10.0:
            raise PluginConfigError("backoff_factor must be in [1.0, 10.0]")

    def to_dict(self) -> dict[str, Any]:
        return {"timeout_ms": self.timeout_ms, "max_retries": self.max_retries,
                "backoff_factor": float(self.backoff_factor)}


CONFIG_TUNABLE_FIELDS: tuple[str, ...] = ("timeout_ms", "max_retries", "backoff_factor")

#: Protocol/external-spec/security constants may stay literal (allowlist).
PROTOCOL_CONSTANTS_ALLOWLIST: frozenset[str] = frozenset({
    "HTTP_OK", "HTTP_TOO_MANY_REQUESTS", "MAX_RETRIES", "TIMEOUT_MS",
    "BACKOFF_FACTOR", "MAX_PAYLOAD_BYTES",
})


def validate_plugin_config(data: Mapping[str, Any]) -> PluginTunables:
    """Reject missing, unknown or out-of-range tunables at plugin load."""
    if not isinstance(data, Mapping):
        raise PluginConfigError("plugin config must be a mapping")
    missing = tuple(sorted(f for f in CONFIG_TUNABLE_FIELDS if f not in data))
    if missing:
        raise PluginConfigError("missing deployment-varying config fields",
                                details={"missing": list(missing)})
    unknown = tuple(sorted(set(data) - set(CONFIG_TUNABLE_FIELDS)))
    if unknown:
        raise PluginConfigError("unknown config fields", details={"unknown": list(unknown)})
    return PluginTunables(**{f: data[f] for f in CONFIG_TUNABLE_FIELDS})


@dataclass(frozen=True)
class MagicNumberFinding:
    path: str
    line: int
    column: int
    literal: str
    context: str


def lint_plugin_source(source: str, path: str,
                       allowlist: frozenset[str] = PROTOCOL_CONSTANTS_ALLOWLIST) \
        -> tuple[MagicNumberFinding, ...]:
    """Flag numeric literals outside allowlisted constant assignments."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise PluginConfigError("source is not valid Python",
                                details={"path": path, "line": exc.lineno}) from exc
    allowed_names: set[str] = set(allowlist)
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    findings: list[MagicNumberFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or isinstance(node.value, bool) \
                or not isinstance(node.value, (int, float)):
            continue
        if node.value in (0, 1, -1):
            continue
        parent = parents.get(id(node))
        if isinstance(parent, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in allowed_names for t in parent.targets):
            continue
        if isinstance(parent, ast.UnaryOp) and isinstance(parent.op, (ast.USub, ast.UAdd)):
            grand = parents.get(id(parent))
            if isinstance(grand, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id in allowed_names for t in grand.targets):
                continue
        line_text = source.splitlines()[node.lineno - 1].strip() if source else ""
        findings.append(MagicNumberFinding(path, node.lineno, node.col_offset,
                                           repr(node.value), line_text))
    return tuple(sorted(findings, key=lambda f: (f.path, f.line, f.column, f.literal)))


def assert_no_magic_numbers(source: str, path: str) -> None:
    findings = lint_plugin_source(source, path)
    if findings:
        raise PluginConfigError("hardcoded tunable in plugin source",
                                details={"count": len(findings),
                                         "first_line": findings[0].line})


# ===========================================================================
# D6.6 -- misconfiguration fails loud at load; never skip a missing referent
# ===========================================================================


class ReferenceRegistry:
    """Named referents that must all resolve during configuration load."""

    def __init__(self) -> None:
        self._targets: dict[str, Any] = {}

    def register(self, name: str, target: Any) -> None:
        _nonblank(name, "name", MisconfigurationError)
        if name in self._targets:
            raise MisconfigurationError("duplicate referent", details={"name": name})
        self._targets[name] = target

    def resolve(self, name: str) -> Any:
        try:
            return self._targets[name]
        except KeyError as exc:
            raise MisconfigurationError(
                "missing referent; refusing to skip it",
                details={"name": name, "known": sorted(self._targets)},
            ) from exc

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._targets))


@dataclass(frozen=True)
class LoadedConfig:
    resolved: Mapping[str, Any]
    skipped: tuple[str, ...] = ()


def load_with_references(config: Mapping[str, Any], registry: ReferenceRegistry) -> LoadedConfig:
    """Resolve ``$ref:name`` strings recursively; unknown names abort the load."""
    if not isinstance(config, Mapping) or not isinstance(registry, ReferenceRegistry):
        raise MisconfigurationError("load_with_references needs a mapping and a registry")

    def walk(value: Any, trail: str) -> Any:
        if isinstance(value, str) and value.startswith("$ref:"):
            name = value[len("$ref:"):]
            return registry.resolve(name)
        if isinstance(value, Mapping):
            return {str(k): walk(v, f"{trail}.{k}") for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
        if isinstance(value, (list, tuple)):
            return [walk(v, f"{trail}[{i}]") for i, v in enumerate(value)]
        return value

    return LoadedConfig(walk(config, "$"), skipped=())


# ===========================================================================
# D6.7 -- opaque cross-boundary ids are branded NewTypes
# ===========================================================================


SessionId = NewType("SessionId", str)
RequestId = NewType("RequestId", str)
PluginId = NewType("PluginId", str)
SnapshotId = NewType("SnapshotId", str)

OPAQUE_ID_TYPES: tuple[Any, ...] = (SessionId, RequestId, PluginId, SnapshotId)


def brand_id(kind: Callable[[str], Any], value: str) -> Any:
    """Validate a boundary id and wrap it in its ``NewType`` brand."""
    if kind not in OPAQUE_ID_TYPES:
        raise TypedIdError("kind must be a declared opaque id NewType")
    if not isinstance(value, str) or not value.strip() or any(c.isspace() for c in value):
        raise TypedIdError("opaque id must be a non-empty string without whitespace",
                          details={"kind": getattr(kind, "__name__", repr(kind))})
    return kind(value)


@dataclass(frozen=True)
class IdAnnotationFinding:
    path: str
    line: int
    symbol: str
    parameter: str


def audit_id_annotations(source: str, path: str) -> tuple[IdAnnotationFinding, ...]:
    """Find cross-boundary ``*_id`` parameters annotated as bare ``str``."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise TypedIdError("source is not valid Python", details={"line": exc.lineno}) from exc
    findings: list[IdAnnotationFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
        for arg in args:
            if arg.arg == "self" or arg.arg == "cls":
                continue
            if not (arg.arg.endswith("_id") or arg.arg == "id"):
                continue
            ann = arg.annotation
            if isinstance(ann, ast.Name) and ann.id == "str":
                findings.append(IdAnnotationFinding(path, arg.lineno, node.name, arg.arg))
    return tuple(sorted(findings, key=lambda f: (f.path, f.line, f.symbol, f.parameter)))


# ===========================================================================
# D6.8 -- trust inside the process; validate at external boundaries
# ===========================================================================


class Boundary(str, Enum):
    PARSER_CONFIG = "parser/config"
    QUEUED_MESSAGE = "queued_message"
    MODEL_TOOL_JSON = "model/tool_json"
    DURABLE_FILE = "durable_file"
    WIRE = "wire"
    WORKER_PROCESS = "worker_process"
    IN_PROCESS = "in_process"


EXTERNAL_BOUNDARIES: frozenset[Boundary] = frozenset(b for b in Boundary
                                                     if b is not Boundary.IN_PROCESS)


@dataclass(frozen=True)
class TrustedValue:
    """Marker for a value produced inside the process by typed code."""

    value: Any


def trust(value: Any) -> TrustedValue:
    return TrustedValue(value)


@dataclass(frozen=True)
class ValidatorSpec:
    boundary: Boundary
    required_fields: tuple[str, ...]
    field_types: Mapping[str, type]

    def __post_init__(self) -> None:
        if not isinstance(self.boundary, Boundary):
            raise BoundaryError("boundary must be a Boundary enum")
        fields = _as_text_tuple(self.required_fields, "required_fields", BoundaryError)
        object.__setattr__(self, "required_fields", fields)
        if any(f not in fields for f in self.field_types):
            raise BoundaryError("field_types contains an undeclared field")


@dataclass(frozen=True)
class BoundaryReport:
    boundary: Boundary
    trusted: bool
    checked_fields: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return bool(self.checked_fields) or self.trusted


class BoundaryRegistry:
    """Fail-closed boundary validators; unknown boundaries are never trusted."""

    def __init__(self) -> None:
        self._specs: dict[Boundary, ValidatorSpec] = {}

    def register(self, spec: ValidatorSpec) -> None:
        if not isinstance(spec, ValidatorSpec):
            raise BoundaryError("register() requires a ValidatorSpec")
        if spec.boundary in self._specs:
            raise BoundaryError("duplicate boundary validator",
                                details={"boundary": spec.boundary.value})
        self._specs[spec.boundary] = spec

    @property
    def boundaries(self) -> tuple[str, ...]:
        return tuple(sorted(b.value for b in self._specs))

    def validate(self, boundary: Boundary, payload: Any) -> BoundaryReport:
        if not isinstance(boundary, Boundary):
            raise BoundaryError("boundary must be a Boundary enum")
        if boundary is Boundary.IN_PROCESS:
            if not isinstance(payload, TrustedValue):
                raise BoundaryError("in-process values must be explicitly trusted")
            return BoundaryReport(boundary, True, ())
        spec = self._specs.get(boundary)
        if spec is None:
            raise BoundaryError("no validator registered for boundary",
                                details={"boundary": boundary.value})
        if isinstance(payload, TrustedValue):
            payload = payload.value
        if not isinstance(payload, Mapping):
            raise BoundaryError("external payload must be a mapping",
                                details={"boundary": boundary.value})
        missing = tuple(f for f in spec.required_fields if f not in payload)
        if missing:
            raise BoundaryError("external payload is missing required fields",
                                details={"boundary": boundary.value, "missing": list(missing)})
        for name, expected in sorted(spec.field_types.items()):
            value = payload[name]
            if expected is float and isinstance(value, (int, float)) \
                    and not isinstance(value, bool):
                continue
            if isinstance(value, bool) or not isinstance(value, expected):
                raise BoundaryError("external payload field has the wrong type",
                                    details={"boundary": boundary.value, "field": name,
                                             "expected": expected.__name__})
        return BoundaryReport(boundary, False, spec.required_fields)


# ===========================================================================
# D6.9 -- no new casts to Any/object beyond the recorded baseline
# ===========================================================================


@dataclass(frozen=True)
class CastRecord:
    path: str
    line: int
    target: str
    reason: str

    def __post_init__(self) -> None:
        _nonblank(self.path, "path", CastBaselineError)
        if self.target not in ("Any", "object"):
            raise CastBaselineError("cast target must be Any or object",
                                    details={"target": self.target})
        if not isinstance(self.reason, str):
            raise CastBaselineError("cast reason must be a string")

    @property
    def key(self) -> str:
        return f"{self.path}:{self.line}:{self.target}"


@dataclass(frozen=True)
class CastGateReport:
    ok: bool
    new_casts: tuple[str, ...]
    missing_reasons: tuple[str, ...]


class CastBaseline:
    """A recorded set of allowed ``cast(Any|object, ...)`` sites."""

    def __init__(self, records: Iterable[CastRecord] = ()) -> None:
        self._records: dict[str, CastRecord] = {}
        for record in records:
            self.add(record)

    def add(self, record: CastRecord) -> None:
        if not isinstance(record, CastRecord):
            raise CastBaselineError("baseline entries must be CastRecord values")
        if not record.reason.strip():
            raise CastBaselineError("baseline casts must record why they are needed",
                                    details={"key": record.key})
        if record.key in self._records:
            raise CastBaselineError("duplicate cast baseline entry", details={"key": record.key})
        self._records[record.key] = record

    @property
    def records(self) -> tuple[CastRecord, ...]:
        return tuple(self._records[k] for k in sorted(self._records))

    def check(self, observed: Iterable[CastRecord]) -> CastGateReport:
        new: list[str] = []
        unreasoned: list[str] = []
        for record in observed:
            if not isinstance(record, CastRecord):
                raise CastBaselineError("observed casts must be CastRecord values")
            if record.key not in self._records:
                new.append(record.key)
                if not record.reason.strip():
                    unreasoned.append(record.key)
        return CastGateReport(not new, tuple(sorted(new)), tuple(sorted(unreasoned)))


def scan_cast_calls(source: str, path: str) -> tuple[CastRecord, ...]:
    """Find ``cast(Any|object, ...)`` calls and their ``# reason:`` comment."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CastBaselineError("source is not valid Python",
                                details={"path": path, "line": exc.lineno}) from exc
    lines = source.splitlines()
    records: list[CastRecord] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) \
                or node.func.id != "cast" or not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Name) or first.id not in ("Any", "object"):
            continue
        reason = ""
        comment = lines[node.lineno - 1].split("#", 1)
        if len(comment) == 2:
            marker = comment[1].strip()
            if marker.lower().startswith("reason:"):
                reason = marker.split(":", 1)[1].strip()
        # A reason-less record is still returned so the gate can flag it.
        records.append(CastRecord(path, node.lineno, first.id, reason))
    return tuple(sorted(records, key=lambda r: (r.line, r.target)))


# ===========================================================================
# D6.10 -- source plane vs artifact plane, explicit gate declaration
# ===========================================================================


class Plane(str, Enum):
    SOURCE = "source"
    ARTIFACT = "artifact"


ARTIFACT_PATH_SEGMENTS: frozenset[str] = frozenset({
    "dist", "build", "release", "node_modules", "site-packages", "__pycache__",
})
ARTIFACT_SUFFIXES: tuple[str, ...] = (".pyc", ".so", ".dll", ".dylib", ".whl")


def classify_path(path: str) -> Plane:
    """Classify a module path as source or build output (pure, no I/O)."""
    if not isinstance(path, str) or not path:
        raise PlaneError("path must be a non-empty string")
    normalised = path.replace("\\", "/")
    if normalised.endswith(ARTIFACT_SUFFIXES):
        return Plane.ARTIFACT
    segments = {s for s in normalised.split("/") if s}
    if segments & ARTIFACT_PATH_SEGMENTS:
        return Plane.ARTIFACT
    return Plane.SOURCE


@dataclass(frozen=True)
class GateDeclaration:
    name: str
    needs_artifact: bool
    artifact_dependency: str = ""

    def __post_init__(self) -> None:
        _nonblank(self.name, "name", PlaneError)
        if self.needs_artifact:
            _nonblank(self.artifact_dependency, "artifact_dependency", PlaneError)
        elif self.artifact_dependency:
            raise PlaneError("source-only gate must not declare an artifact dependency")


@dataclass(frozen=True)
class ResolvedImport:
    module: str
    path: str
    plane: Plane


class ImportGate:
    """Resolve imports to a declared plane; mixed planes fail closed."""

    def __init__(self, declarations: Iterable[GateDeclaration] = ()) -> None:
        self._gates: dict[str, GateDeclaration] = {}
        for declaration in declarations:
            self.declare(declaration)

    def declare(self, declaration: GateDeclaration) -> None:
        if not isinstance(declaration, GateDeclaration):
            raise PlaneError("declare() requires a GateDeclaration")
        if declaration.name in self._gates:
            raise PlaneError("duplicate gate declaration", details={"name": declaration.name})
        self._gates[declaration.name] = declaration

    @property
    def declarations(self) -> tuple[GateDeclaration, ...]:
        return tuple(self._gates[k] for k in sorted(self._gates))

    def resolve(self, gate_name: str, module: str, path: str) -> ResolvedImport:
        declaration = self._gates.get(gate_name)
        if declaration is None:
            raise PlaneError("undeclared gate", details={"gate": gate_name})
        if not isinstance(module, str) or not module:
            raise PlaneError("module must be a non-empty string")
        plane = classify_path(path)
        if plane is Plane.ARTIFACT and not declaration.needs_artifact:
            raise PlaneError(
                "source-only gate resolved an artifact import; declare the dependency",
                details={"gate": gate_name, "module": module, "path": path},
            )
        return ResolvedImport(module, path, plane)

    def validate(self) -> tuple[str, ...]:
        issues: list[str] = []
        for gate in self.declarations:
            if gate.needs_artifact and not gate.artifact_dependency:
                issues.append(f"{gate.name}: missing artifact dependency")
        return tuple(issues)


def assert_source_import(module: str, path: str) -> Plane:
    """Convenience gate: refuse an artifact path for a source-only test."""
    resolved = ImportGate([GateDeclaration("tests", False)]).resolve("tests", module, path)
    return resolved.plane


# ===========================================================================
# D6.11 -- empty-except gate (typed errors are defined at the top of module)
# ===========================================================================


@dataclass(frozen=True)
class ExceptFinding:
    path: str
    line: int
    caught: str
    reasons: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.reasons


def audit_except_handlers(source: str, path: str) -> tuple[ExceptFinding, ...]:
    """Audit otherwise-empty ``except`` blocks: name the error and say why."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise EmptyExceptError("source is not valid Python",
                               details={"path": path, "line": exc.lineno}) from exc
    lines = source.splitlines()
    findings: list[ExceptFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        caught = ast.unparse(node.type) if node.type is not None else "bare"
        body = node.body
        only_pass = len(body) == 1 and isinstance(
            body[0], (ast.Pass, ast.Expr)) and (
                isinstance(body[0], ast.Pass) or (
                    isinstance(body[0].value, ast.Constant)
                    and body[0].value.value is Ellipsis))
        if not only_pass:
            continue
        reasons: list[str] = []
        line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
        comment = line.split("#", 1)[1].strip() if "#" in line else ""
        lowered = comment.lower()
        names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", caught)
        if caught == "bare":
            reasons.append("bare_except_must_name_an_error")
        elif not any(name in comment for name in names):
            reasons.append("comment_must_name_caught_error")
        if "why:" not in lowered and "because" not in lowered:
            reasons.append("comment_must_explain_why")
        findings.append(ExceptFinding(path, node.lineno, caught, tuple(sorted(reasons))))
    return tuple(sorted(findings, key=lambda f: f.line))


def assert_handled_excepts(source: str, path: str) -> None:
    bad = tuple(f for f in audit_except_handlers(source, path) if not f.ok)
    if bad:
        raise EmptyExceptError("empty except block must name the error and why",
                               details={"lines": [f.line for f in bad]})


# ===========================================================================
# D6.12 -- docstrings on public exports and word budgets
# ===========================================================================


DOCSTRING_WORD_BUDGETS: Mapping[str, int] = {
    "module": 120, "class": 80, "function": 60,
}


@dataclass(frozen=True)
class DocFinding:
    path: str
    line: int
    symbol: str
    kind: str
    problem: str


def audit_docstrings(source: str, path: str,
                     budgets: Mapping[str, int] = DOCSTRING_WORD_BUDGETS) \
        -> tuple[DocFinding, ...]:
    """Check public exports for docstrings, args/returns docs and budgets."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise DocstringError("source is not valid Python",
                             details={"path": path, "line": exc.lineno}) from exc
    findings: list[DocFinding] = []

    def check_doc(node: ast.AST, kind: str, symbol: str) -> str:
        doc = ast.get_docstring(node) or ""
        line = getattr(node, "lineno", 1)
        if not doc.strip():
            findings.append(DocFinding(path, line, symbol, kind, "missing_docstring"))
            return doc
        words = len(doc.split())
        if words > budgets.get(kind, 10**6):
            findings.append(DocFinding(path, line, symbol, kind,
                                       f"word_budget_exceeded:{words}"))
        return doc

    module_doc = check_doc(tree, "module", "<module>")
    if not module_doc.strip():
        findings.append(DocFinding(path, 1, "<module>", "module", "missing_docstring"))
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.name.startswith("_"):
            continue
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        doc = check_doc(node, kind, node.name)
        if kind == "function" and doc.strip():
            params = [a.arg for a in (
                list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs))
                if a.arg not in ("self", "cls")]
            if params and "Args:" not in doc and ":param" not in doc:
                findings.append(DocFinding(path, node.lineno, node.name, kind,
                                           "missing_args_section"))
            if node.returns is not None and not isinstance(node.returns, ast.Constant) \
                    and "Returns:" not in doc and ":return" not in doc:
                findings.append(DocFinding(path, node.lineno, node.name, kind,
                                           "missing_returns_section"))
    return tuple(sorted(findings, key=lambda f: (f.line, f.symbol, f.problem)))


def assert_documented(source: str, path: str) -> None:
    findings = audit_docstrings(source, path)
    if findings:
        raise DocstringError("public export is undocumented or over budget",
                             details={"count": len(findings),
                                      "first": findings[0].to_dict() if hasattr(
                                          findings[0], "to_dict") else findings[0].problem})


def find_restating_comments(source: str, path: str) -> tuple[DocFinding, ...]:
    """Flag comments that merely restate the code on their own line."""
    findings: list[DocFinding] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type != tokenize.COMMENT:
                continue
            line = source.splitlines()[token.start[0] - 1]
            code = line[:token.start[1]].strip()
            comment = token.string.lstrip("#").strip()
            norm = lambda s: re.sub(r"\s+", "", s).rstrip(";:")  # noqa: E731
            if code and comment and norm(code) == norm(comment):
                findings.append(DocFinding(path, token.start[0], code, "comment",
                                           "restating_comment"))
    except (tokenize.TokenError, IndentationError) as exc:
        raise DocstringError("source cannot be tokenized", details={"path": path,
                                                                     "error": str(exc)}) from exc
    return tuple(sorted(findings, key=lambda f: f.line))


# ===========================================================================
# D6.13 -- docs accompany code in the same change
# ===========================================================================


@dataclass(frozen=True)
class DocRule:
    name: str
    path_glob: str
    required_docs: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        _nonblank(self.name, "name", DocSyncError)
        _nonblank(self.path_glob, "path_glob", DocSyncError)
        _nonblank(self.reason, "reason", DocSyncError)
        object.__setattr__(self, "required_docs",
                           _as_text_tuple(self.required_docs, "required_docs", DocSyncError))
        if not self.required_docs:
            raise DocSyncError("a doc rule must require at least one document")


DEFAULT_DOC_RULES: tuple[DocRule, ...] = (
    DocRule("public_python_source", "*/keel/src/keel/*.py", ("README.md",),
            "public module changed: README/docstrings must move with the code"),
    DocRule("package_readme", "*/keel/README.md", ("CHANGELOG.md",),
            "README changed: release notes must move with it"),
)


@dataclass(frozen=True)
class DocCoverageReport:
    ok: bool
    covered_rules: tuple[str, ...]
    missing: Mapping[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "covered_rules": list(self.covered_rules),
                "missing": {k: list(v) for k, v in self.missing.items()}}


class DocCoverageChecker:
    """Check that every changed path's required documents changed too."""

    def __init__(self, rules: Iterable[DocRule] = DEFAULT_DOC_RULES) -> None:
        self._rules: dict[str, DocRule] = {}
        for rule in rules:
            self.add(rule)

    def add(self, rule: DocRule) -> None:
        if not isinstance(rule, DocRule):
            raise DocSyncError("add() requires a DocRule")
        if rule.name in self._rules:
            raise DocSyncError("duplicate doc rule", details={"name": rule.name})
        self._rules[rule.name] = rule

    @property
    def rules(self) -> tuple[DocRule, ...]:
        return tuple(self._rules[k] for k in sorted(self._rules))

    def check(self, changed_paths: Iterable[str], docs_updated: Iterable[str]) \
            -> DocCoverageReport:
        changed = _as_text_tuple(changed_paths, "changed_paths", DocSyncError)
        docs = _as_text_tuple(docs_updated, "docs_updated", DocSyncError)
        missing: dict[str, tuple[str, ...]] = {}
        covered: list[str] = []
        for rule in self.rules:
            matched = tuple(p for p in changed if fnmatch.fnmatch(p, rule.path_glob))
            if not matched:
                continue
            absent = tuple(doc for doc in rule.required_docs
                           if not any(path.endswith("/" + doc) or path == doc for path in docs))
            if absent:
                missing[rule.name] = absent
            else:
                covered.append(rule.name)
        covered.sort()
        return DocCoverageReport(not missing, tuple(covered), dict(sorted(missing.items())))


def assert_docs_in_sync(changed_paths: Iterable[str], docs_updated: Iterable[str]) -> None:
    report = DocCoverageChecker().check(changed_paths, docs_updated)
    if not report.ok:
        raise DocSyncError("docs did not accompany the code change",
                           details=report.to_dict())


# ===========================================================================
# D6.15 -- keyless recorded-session snapshots and a fixture registry
# ===========================================================================


ALL_PLATFORMS: tuple[str, ...] = ("macos", "linux", "windows")
KEYLESS_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "timestamp", "created_at", "updated_at", "uuid", "session_id", "request_id",
    "run_id", "hostname", "pid", "cwd", "absolute_path",
})
_ISO_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_WIN_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_UNIX_ABS_RE = re.compile(r"^/(Users|home|root|tmp)/")


def assert_keyless(payload: Any, path: str = "$") -> None:
    """Reject keys and values that vary by machine, clock or run."""
    if isinstance(payload, Mapping):
        for key, value in sorted(payload.items(), key=lambda kv: str(kv[0])):
            child = f"{path}.{key}"
            if str(key).lower() in KEYLESS_FORBIDDEN_KEYS:
                raise SnapshotError("snapshot fixture is not keyless",
                                    details={"path": child, "key": str(key)})
            assert_keyless(value, child)
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_keyless(value, f"{path}[{index}]")
    elif isinstance(payload, str):
        if _ISO_TIME_RE.search(payload) or _UUID_RE.search(payload) \
                or _WIN_ABS_RE.match(payload) or _UNIX_ABS_RE.match(payload):
            raise SnapshotError("snapshot fixture contains a volatile value",
                                details={"path": path})


@dataclass(frozen=True)
class SnapshotFixture:
    fixture_id: str
    input_events: tuple[str, ...]
    expected_output: Any
    platforms: tuple[str, ...] = ALL_PLATFORMS
    note: str = ""

    def __post_init__(self) -> None:
        _nonblank(self.fixture_id, "fixture_id", SnapshotError)
        if isinstance(self.input_events, (str, bytes)) or not self.input_events:
            raise SnapshotError("a fixture needs a non-empty event sequence")
        events = tuple(str(e) for e in self.input_events)
        object.__setattr__(self, "input_events", events)
        platforms = tuple(sorted(set(str(p) for p in self.platforms)))
        if platforms != tuple(sorted(ALL_PLATFORMS)):
            raise SnapshotError("fixture must replay on macOS, Linux and Windows",
                                details={"platforms": list(platforms)})
        assert_keyless(self.expected_output)
        assert_keyless(events)

    @property
    def digest(self) -> str:
        return fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {"fixture_id": self.fixture_id, "input_events": list(self.input_events),
                "expected_output": self.expected_output,
                "platforms": list(self.platforms), "note": self.note}


@dataclass(frozen=True)
class ReplayReport:
    fixture_id: str
    ok: bool
    events_match: bool
    output_match: bool

    def to_dict(self) -> dict[str, Any]:
        return {"fixture_id": self.fixture_id, "ok": self.ok,
                "events_match": self.events_match, "output_match": self.output_match}


class SnapshotRegistry:
    """Exact replay registry -- no normaliser is allowed to hide a fixture drift."""

    def __init__(self) -> None:
        self._fixtures: dict[str, SnapshotFixture] = {}

    def register(self, fixture: SnapshotFixture) -> None:
        if not isinstance(fixture, SnapshotFixture):
            raise SnapshotError("register() requires a SnapshotFixture")
        if fixture.fixture_id in self._fixtures:
            raise SnapshotError("duplicate fixture id", details={"id": fixture.fixture_id})
        self._fixtures[fixture.fixture_id] = fixture

    def get(self, fixture_id: str) -> SnapshotFixture:
        try:
            return self._fixtures[fixture_id]
        except KeyError as exc:
            raise SnapshotError("unknown snapshot fixture",
                                details={"id": fixture_id}) from exc

    @property
    def fixtures(self) -> tuple[SnapshotFixture, ...]:
        return tuple(self._fixtures[k] for k in sorted(self._fixtures))

    def replay(self, fixture_id: str, observed_events: Sequence[str],
               observed_output: Any) -> ReplayReport:
        fixture = self.get(fixture_id)
        events_ok = tuple(observed_events) == fixture.input_events
        # Exact comparison: fixes belong in the fixture, not in a normaliser.
        output_ok = observed_output == fixture.expected_output
        return ReplayReport(fixture_id, events_ok and output_ok, events_ok, output_ok)

    def replay_all(self, observations: Mapping[str, tuple[Sequence[str], Any]]) \
            -> tuple[ReplayReport, ...]:
        reports = [self.replay(fid, obs[0], obs[1]) for fid, obs in sorted(observations.items())]
        return tuple(reports)


def assert_no_normalizers(source: str, path: str) -> None:
    """Reject normaliser helpers in fixture code (fix the fixture instead)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SnapshotError("source is not valid Python",
                            details={"path": path, "line": exc.lineno}) from exc
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith(("normalize_", "scrub_", "sanitise_", "sanitize_")):
                bad.append(node.name)
    if bad:
        raise SnapshotError("normalizers are forbidden in snapshot fixtures",
                            details={"path": path, "functions": sorted(bad)})


def assert_snapshot_updated(visible_change: bool, fixtures_updated: Iterable[str]) -> None:
    if visible_change and not tuple(fixtures_updated):
        raise SnapshotError("user/model-visible change requires a snapshot fixture update")


# ===========================================================================
# D6.16 -- both SDKs project the loop in the same change
# ===========================================================================


CORE_LIFECYCLE: tuple[str, ...] = ("session.created", "session.closed")


@dataclass(frozen=True)
class SdkProjection:
    """One loop projection shared by the Python and TypeScript SDKs."""

    event_map: Mapping[str, str]
    lifecycle: tuple[str, ...]
    python_events: Mapping[str, str]
    typescript_events: Mapping[str, str]

    def __post_init__(self) -> None:
        for label, mapping in (("event_map", self.event_map),
                               ("python_events", self.python_events),
                               ("typescript_events", self.typescript_events)):
            if not isinstance(mapping, Mapping):
                raise SdkProjectionError(f"{label} must be a mapping")
        lifecycle = tuple(sorted(set(str(s) for s in self.lifecycle)))
        if not lifecycle:
            raise SdkProjectionError("lifecycle must not be empty")
        object.__setattr__(self, "lifecycle", lifecycle)


@dataclass(frozen=True)
class SdkProjectionReport:
    ok: bool
    missing: Mapping[str, tuple[str, ...]]
    mismatched: tuple[str, ...]
    stale: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "missing": {k: list(v) for k, v in self.missing.items()},
                "mismatched": list(self.mismatched), "stale": list(self.stale)}


def validate_projection(projection: SdkProjection) -> SdkProjectionReport:
    """Check that both SDK expected outputs cover the loop exactly."""
    if not isinstance(projection, SdkProjection):
        raise SdkProjectionError("validate_projection requires an SdkProjection")
    core = set(projection.event_map) | set(projection.lifecycle) | set(CORE_LIFECYCLE)
    missing: dict[str, tuple[str, ...]] = {}
    for sdk, events in (("python", projection.python_events),
                        ("typescript", projection.typescript_events)):
        absent = tuple(sorted(e for e in core if e not in events))
        if absent:
            missing[sdk] = absent
    mismatched = tuple(sorted(e for e in core
                              if e in projection.python_events
                              and e in projection.typescript_events
                              and projection.python_events[e]
                              != projection.typescript_events[e]))
    stale = tuple(sorted({e for sdk in (projection.python_events,
                                        projection.typescript_events)
                           for e in sdk} - core))
    ok = not missing and not mismatched and not stale
    return SdkProjectionReport(ok, dict(sorted(missing.items())), mismatched, stale)


class SdkProjectionValidator:
    """Registry form of :func:`validate_projection` for multiple projections."""

    def __init__(self) -> None:
        self._projections: dict[str, SdkProjection] = {}

    def register(self, name: str, projection: SdkProjection) -> None:
        _nonblank(name, "name", SdkProjectionError)
        if name in self._projections:
            raise SdkProjectionError("duplicate projection", details={"name": name})
        self._projections[name] = projection

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._projections))

    def validate_all(self) -> Mapping[str, SdkProjectionReport]:
        return {name: validate_projection(self._projections[name]) for name in self.names}


def assert_projection_in_sync(projection: SdkProjection) -> None:
    report = validate_projection(projection)
    if not report.ok:
        raise SdkProjectionError("Python/TypeScript SDK projection is stale",
                                 details=report.to_dict())


def projection_manifest(projection: SdkProjection) -> dict[str, Any]:
    return {
        "event_map": dict(sorted(projection.event_map.items())),
        "lifecycle": list(projection.lifecycle),
        "python": dict(sorted(projection.python_events.items())),
        "typescript": dict(sorted(projection.typescript_events.items())),
        "fingerprint": fingerprint(projection.to_dict()) if hasattr(projection, "to_dict")
                       else fingerprint({"event_map": projection.event_map,
                                         "lifecycle": projection.lifecycle,
                                         "python": projection.python_events,
                                         "typescript": projection.typescript_events}),
    }


# ===========================================================================
# D6.19 -- vendoring: pinned SHAs, manifest updates, logged local patches
# ===========================================================================


_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class LocalPatch:
    patch_id: str
    sha256: str
    reason: str

    def __post_init__(self) -> None:
        _nonblank(self.patch_id, "patch_id", VendorManifestError)
        _nonblank(self.reason, "reason", VendorManifestError)
        if not _SHA256_RE.match(self.sha256):
            raise VendorManifestError("patch sha256 must be 64 lowercase hex characters")


@dataclass(frozen=True)
class VendoredPackage:
    name: str
    upstream_sha: str
    source_path: str
    local_patches: tuple[LocalPatch, ...] = ()

    def __post_init__(self) -> None:
        _nonblank(self.name, "name", VendorManifestError)
        _nonblank(self.source_path, "source_path", VendorManifestError)
        if not _SHA40_RE.match(self.upstream_sha):
            raise VendorManifestError("upstream_sha must be 40 lowercase hex characters")
        patches = tuple(sorted(self.local_patches, key=lambda p: p.patch_id))
        if len({p.patch_id for p in patches}) != len(patches):
            raise VendorManifestError("duplicate local patch id")
        object.__setattr__(self, "local_patches", patches)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "upstream_sha": self.upstream_sha,
                "source_path": self.source_path,
                "local_patches": [{"patch_id": p.patch_id, "sha256": p.sha256,
                                   "reason": p.reason} for p in self.local_patches]}


class VendorManifest:
    """Pin every vendored package and require a manifest update for changes."""

    def __init__(self, manifest_path: str = "vendor/manifest.json") -> None:
        self.manifest_path = manifest_path
        self._packages: dict[str, VendoredPackage] = {}

    def register(self, package: VendoredPackage) -> None:
        if not isinstance(package, VendoredPackage):
            raise VendorManifestError("register() requires a VendoredPackage")
        if package.name in self._packages:
            raise VendorManifestError("duplicate vendored package", details={"name": package.name})
        self._packages[package.name] = package

    @property
    def packages(self) -> tuple[VendoredPackage, ...]:
        return tuple(self._packages[k] for k in sorted(self._packages))

    def check_tree_sha(self, name: str, observed_sha: str) -> bool:
        package = self._packages.get(name)
        if package is None:
            raise VendorManifestError("vendored package not in manifest", details={"name": name})
        if observed_sha == package.upstream_sha:
            return True
        if any(p.sha256 == hashlib.sha256(observed_sha.encode("utf-8")).hexdigest()
               for p in package.local_patches):
            return True
        raise VendorManifestError("vendored tree changed without a manifest patch entry",
                                  details={"name": name, "observed": observed_sha})

    def changes_require_manifest_update(self, changed_paths: Iterable[str]) \
            -> tuple[str, ...]:
        changed = _as_text_tuple(changed_paths, "changed_paths", VendorManifestError)
        if not changed:
            return ()
        if any(path.endswith(self.manifest_path) or path == self.manifest_path
               for path in changed):
            return ()
        affected: list[str] = []
        for package in self.packages:
            root = package.source_path.rstrip("/")
            if any(path == root or path.startswith(root + "/") or
                   path.replace("\\", "/").startswith(root + "/") for path in changed):
                affected.append(package.name)
        return tuple(sorted(affected))

    def validate(self) -> tuple[str, ...]:
        issues: list[str] = []
        for package in self.packages:
            if not _SHA40_RE.match(package.upstream_sha):
                issues.append(f"{package.name}: bad upstream sha")
            for patch in package.local_patches:
                if not _SHA256_RE.match(patch.sha256):
                    issues.append(f"{package.name}: bad patch sha for {patch.patch_id}")
        return tuple(sorted(issues))


def render_vendor_manifest(manifest: VendorManifest) -> str:
    payload = {"manifest_path": manifest.manifest_path,
               "packages": [p.to_dict() for p in manifest.packages]}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ===========================================================================
# D6.22 -- TODO markers by urgency, release gate on open FIXME
# ===========================================================================


class MarkerUrgency(str, Enum):
    FIXME = "FIXME"  # blocks release
    TODO = "TODO"    # soon
    XXX = "XXX"      # someday


MARKER_PATTERN = re.compile(r"\b(FIXME|TODO|XXX)\b\s*:?\s*(.*)")


@dataclass(frozen=True)
class MarkerFinding:
    path: str
    line: int
    marker: MarkerUrgency
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "line": self.line,
                "marker": self.marker.value, "text": self.text}


def scan_markers(source: str, path: str) -> tuple[MarkerFinding, ...]:
    findings: list[MarkerFinding] = []
    for number, line in enumerate(source.splitlines(), start=1):
        match = MARKER_PATTERN.search(line)
        if match:
            findings.append(MarkerFinding(path, number,
                                          MarkerUrgency(match.group(1)),
                                          match.group(2).strip()))
    return tuple(findings)


def release_gate(findings: Iterable[MarkerFinding]) -> tuple[MarkerFinding, ...]:
    return tuple(sorted((f for f in findings if f.marker is MarkerUrgency.FIXME),
                        key=lambda f: (f.path, f.line)))


def assert_release_ready(findings: Iterable[MarkerFinding]) -> None:
    blocking = release_gate(findings)
    if blocking:
        raise MarkerError("open FIXME blocks release",
                          details={"count": len(blocking),
                                   "first": blocking[0].to_dict()})


# ===========================================================================
# D6.24 -- strict typing with narrow, justified dynamic exceptions
# ===========================================================================


@dataclass(frozen=True)
class JustifiedDynamic:
    path: str
    symbol: str
    reason: str

    def __post_init__(self) -> None:
        _nonblank(self.path, "path", TypingAuditError)
        _nonblank(self.symbol, "symbol", TypingAuditError)
        reason = _nonblank(self.reason, "reason", TypingAuditError)
        if len(reason) < 12 or reason.lower() in {"legacy", "temporary", "tbd", "dynamic"}:
            raise TypingAuditError("dynamic-type exception needs a concrete reason",
                                   details={"symbol": self.symbol})


@dataclass(frozen=True)
class TypingFinding:
    path: str
    line: int
    symbol: str
    problem: str


class TypingAudit:
    """Audit public functions for missing annotations and unjustified ``Any``."""

    def __init__(self, justifications: Iterable[JustifiedDynamic] = ()) -> None:
        self._justified = {(j.path, j.symbol) for j in justifications}

    def audit(self, source: str, path: str) -> tuple[TypingFinding, ...]:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise TypingAuditError("source is not valid Python",
                                   details={"path": path, "line": exc.lineno}) from exc
        findings: list[TypingFinding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            justified = (path, node.name) in self._justified
            if node.returns is None:
                findings.append(TypingFinding(path, node.lineno, node.name,
                                              "missing_return_annotation"))
            args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
            for arg in args:
                if arg.arg in ("self", "cls"):
                    continue
                if arg.annotation is None:
                    findings.append(TypingFinding(path, arg.lineno,
                                                  f"{node.name}.{arg.arg}",
                                                  "missing_parameter_annotation"))
            if justified:
                findings = [f for f in findings if not (
                    f.symbol == node.name or f.symbol.startswith(node.name + "."))]
        return tuple(sorted(findings, key=lambda f: (f.line, f.symbol, f.problem)))

    def assert_strict(self, source: str, path: str) -> None:
        findings = self.audit(source, path)
        if findings:
            raise TypingAuditError("public function is not strictly typed",
                                   details={"count": len(findings),
                                            "first": findings[0].problem})


# ===========================================================================
# D6.25 -- top-level gate registry with per-gate invalid-case proof
# ===========================================================================


@dataclass(frozen=True)
class GateProbe:
    name: str
    accepts_valid: bool
    rejects_invalid: bool

    @property
    def ok(self) -> bool:
        return self.accepts_valid and self.rejects_invalid


@dataclass(frozen=True)
class InvariantGate:
    name: str
    predicate: Callable[[Any], bool]
    valid_case: Any
    invalid_case: Any

    def probe(self) -> GateProbe:
        def rejects(value: Any) -> bool:
            try:
                return not bool(self.predicate(value))
            except Exception:
                return True  # a raise is a valid rejection of an invalid case

        accepts = False
        try:
            accepts = bool(self.predicate(self.valid_case))
        except Exception:
            accepts = False
        return GateProbe(self.name, accepts, rejects(self.invalid_case))


@dataclass(frozen=True)
class GateException:
    gate: str
    scope: str
    reason: str

    def __post_init__(self) -> None:
        _nonblank(self.gate, "gate", GateError)
        _nonblank(self.scope, "scope", GateError)
        _nonblank(self.reason, "reason", GateError)
        if self.scope.lower() == "global":
            raise GateError("gate exceptions must be narrow, never global",
                            details={"gate": self.gate})


@dataclass(frozen=True)
class GateReport:
    ok: bool
    probes: tuple[GateProbe, ...]
    exceptions: tuple[str, ...]


class GateRegistry:
    """Executed top-level gate; each rule must reject an invalid case."""

    def __init__(self) -> None:
        self._gates: dict[str, InvariantGate] = {}
        self._exceptions: dict[str, GateException] = {}

    def register(self, gate: InvariantGate) -> None:
        if not isinstance(gate, InvariantGate):
            raise GateError("register() requires an InvariantGate")
        if gate.name in self._gates:
            raise GateError("duplicate invariant gate", details={"name": gate.name})
        self._gates[gate.name] = gate

    def exempt(self, exception: GateException) -> None:
        if not isinstance(exception, GateException):
            raise GateError("exempt() requires a GateException")
        if exception.gate not in self._gates:
            raise GateError("exception refers to an unknown gate",
                            details={"gate": exception.gate})
        if exception.gate in self._exceptions:
            raise GateError("duplicate gate exception", details={"gate": exception.gate})
        self._exceptions[exception.gate] = exception

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._gates))

    def probe_all(self) -> tuple[GateProbe, ...]:
        return tuple(g.probe() for g in (self._gates[n] for n in self.names))

    def assert_proven(self) -> None:
        bad = [p.name for p in self.probe_all() if not p.ok]
        if bad:
            raise GateError("gate did not reject its invalid case", details={"gates": bad})


def top_level_gate(registry: GateRegistry) -> GateReport:
    """Run every registered gate's valid/invalid probe in one top-level call."""
    if not isinstance(registry, GateRegistry):
        raise GateError("top_level_gate requires a GateRegistry")
    probes = registry.probe_all()
    return GateReport(all(p.ok for p in probes) and bool(probes), probes,
                      tuple(sorted(e.gate for e in registry._exceptions.values())))


__all__ = [
    # shared
    "canonical_bytes", "fingerprint", "KeelError", "all_error_codes",
    "fail_on_untrusted", "fail_on_unknown_outcome",
    "ApiStabilityError", "SchemaVersionError", "EventUnionError", "ResolutionError",
    "PluginConfigError", "MisconfigurationError", "TypedIdError", "BoundaryError",
    "CastBaselineError", "PlaneError", "UntrustedStateError", "UnknownOutcomeError",
    "EmptyExceptError", "DocstringError", "DocSyncError", "SnapshotError",
    "SdkProjectionError", "VendorManifestError", "MarkerError", "TypingAuditError",
    "GateError",
    # D6.1
    "ChangeKind", "ApiChange", "ApiChangeValidation", "ApiChangeRecorder",
    "check_upgrade_guide", "SchemaVersion", "assert_monotonic", "scan_schema_version",
    # D6.3
    "EventMode", "UnionStyle", "EventSpec", "EventDispatch", "EventCatalogReport",
    "EventCatalog", "assert_never", "render_mode",
    # D6.4
    "Request", "Spec", "DEFAULT_MODEL", "DEFAULT_MAX_TOKENS", "DEFAULT_TEMPERATURE",
    "resolve", "run", "find_hidden_defaults",
    # D6.5
    "PluginTunables", "CONFIG_TUNABLE_FIELDS", "PROTOCOL_CONSTANTS_ALLOWLIST",
    "validate_plugin_config", "MagicNumberFinding", "lint_plugin_source",
    "assert_no_magic_numbers",
    # D6.6
    "ReferenceRegistry", "LoadedConfig", "load_with_references",
    # D6.7
    "SessionId", "RequestId", "PluginId", "SnapshotId", "OPAQUE_ID_TYPES",
    "brand_id", "IdAnnotationFinding", "audit_id_annotations",
    # D6.8
    "Boundary", "EXTERNAL_BOUNDARIES", "TrustedValue", "trust", "ValidatorSpec",
    "BoundaryReport", "BoundaryRegistry",
    # D6.9
    "CastRecord", "CastGateReport", "CastBaseline", "scan_cast_calls",
    # D6.10
    "Plane", "ARTIFACT_PATH_SEGMENTS", "ARTIFACT_SUFFIXES", "classify_path",
    "GateDeclaration", "ResolvedImport", "ImportGate", "assert_source_import",
    # D6.11
    "ExceptFinding", "audit_except_handlers", "assert_handled_excepts",
    # D6.12
    "DOCSTRING_WORD_BUDGETS", "DocFinding", "audit_docstrings", "assert_documented",
    "find_restating_comments",
    # D6.13
    "DocRule", "DEFAULT_DOC_RULES", "DocCoverageReport", "DocCoverageChecker",
    "assert_docs_in_sync",
    # D6.15
    "ALL_PLATFORMS", "KEYLESS_FORBIDDEN_KEYS", "assert_keyless", "SnapshotFixture",
    "ReplayReport", "SnapshotRegistry", "assert_no_normalizers", "assert_snapshot_updated",
    # D6.16
    "CORE_LIFECYCLE", "SdkProjection", "SdkProjectionReport", "validate_projection",
    "SdkProjectionValidator", "assert_projection_in_sync", "projection_manifest",
    # D6.19
    "LocalPatch", "VendoredPackage", "VendorManifest", "render_vendor_manifest",
    # D6.22
    "MarkerUrgency", "MARKER_PATTERN", "MarkerFinding", "scan_markers", "release_gate",
    "assert_release_ready",
    # D6.24
    "JustifiedDynamic", "TypingFinding", "TypingAudit",
    # D6.25
    "GateProbe", "InvariantGate", "GateException", "GateReport", "GateRegistry",
    "top_level_gate",
]
