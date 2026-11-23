"""E7.x P0 runtime-contract features — typed descriptor / policy layer.

This module is the single, additive home for six P0 rows of the v6 registry
(Addendum 7, DS-SEAMS seam map).  It is **stdlib only** and deliberately
*shallow*: every factory is a pure function of its inputs and returns an
immutable descriptor.  It performs **no file I/O, no filesystem stat/open, no
subprocess launch, no network call and no database access**.  Every descriptor
carries explicit ``io_performed`` / ``network`` / ``runtime_claimed`` flags so a
consumer can never mistake a description for an executed side effect.

Features (all ``not_started`` P0 rows in the E7 family assigned to this layer):
    E7.18 sandboxPolicy       — one home for the default sandbox mode and the
                                workspace root; ``resolve_sandbox()`` returns a
                                typed policy; no permissive fallback; a deny
                                can never be widened by a later merge.
    E7.2  toolResultPruner    — model-free pruning of oversized *current* tool
                                results into replayable surface replacements;
                                the full value is preserved in an in-memory
                                artifact seam and secrets are redacted before
                                any truncation, never silently.
    E7.20 permissionPresets   — user-facing Cautious/Balanced/Trusted presets
                                bundling sandbox mode + approval policy; a
                                switch writes exactly one logged event that
                                updates both knobs while preserving explicit
                                user overrides.
    E7.21 fs-observation       — read-before-edit + stale-file detection as
           policy                  descriptors contributed through the fs/*
                                event gate; hash/mtime based, no real FS I/O.
    E7.23 web seam             — search/fetch providers register into one
                                service; tool names stay stable; free backends
                                only; no network is performed.
    E7.6  workspaceFiles      — stat, paged text, byte windows, directory
                                listings and a change feed, all confined by
                                pure lexical path containment; no real FS I/O.

Integration seams (what is intentionally NOT wired in here):
    * ``keel.sandbox_exec`` / ``keel.os_sandbox`` / ``keel.sandbox_policy``:
      :func:`handoff_argv` describes the exact argv a consumer hands to a
      backend and :func:`enforcement_report` is the shape a backend uses to
      report what it actually enforced.  This module never spawns a process.
    * ``keel.toolresult`` / transcript compaction: :func:`prune_current_results`
      is compaction-ladder step 1 (prune, no model call); step 2 (summarize)
      stays in the caller.  Replacements are replayable via :class:`ArtifactSeam`.
    * ``keel.permissions`` / ``keel.permission_contracts``: presets here are a
      user-facing bundle only; the live first-match evaluator is unchanged.
    * ``keel.file_watcher`` / fs event gate: :func:`fs_event_gate` is an
      additional observation precondition; callers supply observed state.
    * ``keel.webapp`` / provider catalog: :class:`WebService` is the registry a
      real injected search/fetch provider would be resolved from.
    * renderer file tree / viewer: :func:`paged_text`, :func:`byte_window`,
      :func:`directory_listing` and :func:`change_feed` back those panels.

No existing module imports this new module; integration is a follow-up step, so
this change cannot alter current runtime behaviour.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence

# All P0 rows of the E7 family owned by this descriptor layer.
FEATURE_IDS: tuple[str, ...] = (
    "E7.2", "E7.6", "E7.18", "E7.20", "E7.21", "E7.23",
)


# ---------------------------------------------------------------------------
# shared errors and small normalisers
# ---------------------------------------------------------------------------
class ContractError(ValueError):
    """Base error for a violated runtime-contract invariant."""


class SandboxError(ContractError):
    """Raised for an invalid sandbox mode/workspace or a widening attempt."""


class PruneError(ContractError):
    """Raised when a replacement cannot be replayed from the artifact seam."""


class PresetError(ContractError):
    """Raised for an unknown preset, knob or override value."""


class ObservationError(ContractError):
    """Raised for an invalid fs gate event."""


class WebSeamError(ContractError):
    """Raised for a paid/unstable/conflicting web provider registration."""


class WorkspacePathError(ContractError):
    """Raised when a path escapes its workspace root."""


def _enum(enum_cls: type[Enum], value: Any, error_cls: type[ContractError]) -> Enum:
    """Coerce *value* into *enum_cls* with a clear, typed error on failure."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError) as exc:
        raise error_cls(f"unknown {enum_cls.__name__}: {value!r}") from exc


def _params(value: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Canonicalise call parameters into a sorted tuple of string pairs."""
    return tuple(sorted((str(k), str(v)) for k, v in value.items()))


def _case(value: str) -> str:
    """Case-fold on Windows (case-insensitive paths) and leave POSIX alone."""
    import os
    return value.lower() if os.name == "nt" else value


def _normalize_path(value: object) -> str:
    """Lexically normalise a path (both separators, ``.`` / ``..`` collapsed).

    Pure string logic only — no stat, no realpath, no filesystem access.  The
    forward-slash form is used internally so the same rule works on both
    Windows and POSIX; callers keep their native separators in the original
    inputs, while descriptors use the canonical forward-slash form.
    """
    if value is None:
        raise WorkspacePathError("path must not be None")
    text = str(value).replace("\\", "/").strip()
    if not text:
        raise WorkspacePathError("path must not be empty")
    return posixpath.normpath(text)


def contained_path(root: object, path: object) -> str:
    """Return the canonical form of *path* if contained in *root*, else raise.

    Containment is purely lexical: ``..`` traversal, sibling prefixes and
    absolute paths outside the root are rejected.  An absolute *path* is only
    accepted when it is inside an absolute *root*.  No filesystem is touched.
    """
    root_norm = _normalize_path(root)
    path_norm = _normalize_path(path)
    root_abs = posixpath.isabs(root_norm)
    if posixpath.isabs(path_norm) and not root_abs:
        raise WorkspacePathError(
            f"absolute path {path!r} cannot be contained in relative root {root!r}")

    candidate = path_norm if posixpath.isabs(path_norm) else posixpath.normpath(
        posixpath.join(root_norm, path_norm))

    r, c = _case(root_norm), _case(candidate)
    if r == c:
        return candidate
    if r == "/":
        prefix = "/"
    elif r in (".", ""):
        prefix = ""
    else:
        prefix = r + "/"
    if prefix and c.startswith(prefix):
        return candidate
    if prefix == "" and not posixpath.isabs(c):
        return candidate
    raise WorkspacePathError(f"path escapes workspace root: {path!r} (root {root!r})")


def _descriptor_flags(*, network: bool = False) -> dict:
    """Uniform honesty flags shared by every descriptor in this layer."""
    return {
        "layer": "descriptor_only",
        "io_performed": False,
        "network": network,
        "runtime_claimed": False,
    }


# ===========================================================================
# E7.18 — sandboxPolicy: one home for default mode + workspace root
# ===========================================================================
class SandboxMode(str, Enum):
    """Sandbox strictness ladder.  ``OFF`` is an explicit opt-in, never a fallback."""

    STRICT = "strict"
    WORKSPACE = "workspace"
    OFF = "off"

    @property
    def restrictiveness(self) -> int:
        """0 = unrestricted, higher = more restrictive."""
        return {SandboxMode.OFF: 0, SandboxMode.WORKSPACE: 1,
                SandboxMode.STRICT: 2}[self]


DEFAULT_SANDBOX_MODE = SandboxMode.STRICT

CAP_NETWORK = "network"
CAP_PROCESS_SPAWN = "process_spawn"
CAP_WRITE_OUTSIDE = "write_outside_workspace"
CAP_READ_OUTSIDE = "read_outside_workspace"
CAPABILITY_NAMES: tuple[str, ...] = (
    CAP_NETWORK, CAP_PROCESS_SPAWN, CAP_WRITE_OUTSIDE, CAP_READ_OUTSIDE,
)

#: The single source of truth for what each mode permits.  Consumers read this
#: descriptor rather than re-deriving confinement in bash, fs and terminals.
MODE_CAPABILITIES: dict[SandboxMode, dict[str, bool]] = {
    SandboxMode.STRICT: {
        CAP_NETWORK: False, CAP_PROCESS_SPAWN: False,
        CAP_WRITE_OUTSIDE: False, CAP_READ_OUTSIDE: False,
    },
    SandboxMode.WORKSPACE: {
        CAP_NETWORK: False, CAP_PROCESS_SPAWN: False,
        CAP_WRITE_OUTSIDE: False, CAP_READ_OUTSIDE: True,
    },
    SandboxMode.OFF: {
        CAP_NETWORK: True, CAP_PROCESS_SPAWN: True,
        CAP_WRITE_OUTSIDE: True, CAP_READ_OUTSIDE: True,
    },
}


@dataclass(frozen=True)
class SandboxPolicy:
    """Resolved, typed sandbox policy for one workspace root."""

    mode: SandboxMode
    workspace_root: str
    network: bool
    process_spawn: bool
    write_outside_workspace: bool
    read_outside_workspace: bool
    denied_capabilities: tuple[str, ...] = ()
    audit_hook: bool = True
    enforcement_reported: bool = True
    io_performed: bool = False
    network_calls: bool = False

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            CAP_NETWORK: self.network,
            CAP_PROCESS_SPAWN: self.process_spawn,
            CAP_WRITE_OUTSIDE: self.write_outside_workspace,
            CAP_READ_OUTSIDE: self.read_outside_workspace,
        }

    @property
    def restrictiveness(self) -> int:
        return self.mode.restrictiveness


def resolve_sandbox(mode: object, workspace: object, *,
                    default_mode: SandboxMode = DEFAULT_SANDBOX_MODE) -> SandboxPolicy:
    """Resolve one sandbox policy from a mode and a workspace root.

    An invalid mode/workspace raises instead of falling back to a permissive
    policy.  ``mode=None`` selects the single module-level default (strict), so
    there is exactly one home for the default sandbox mode.
    """
    effective = default_mode if mode is None else _enum(SandboxMode, mode, SandboxError)
    if not isinstance(effective, SandboxMode):
        effective = _enum(SandboxMode, effective, SandboxError)
    try:
        root = _normalize_path(workspace)
    except WorkspacePathError as exc:
        raise SandboxError(str(exc)) from exc
    caps = dict(MODE_CAPABILITIES[effective])
    return SandboxPolicy(
        mode=effective,
        workspace_root=root,
        network=caps[CAP_NETWORK],
        process_spawn=caps[CAP_PROCESS_SPAWN],
        write_outside_workspace=caps[CAP_WRITE_OUTSIDE],
        read_outside_workspace=caps[CAP_READ_OUTSIDE],
        audit_hook=(effective is not SandboxMode.OFF),
    )


def restrict_sandbox(policy: SandboxPolicy,
                     denied: Iterable[str]) -> SandboxPolicy:
    """Return a policy with *denied* capabilities forced off (monotone deny).

    This can only tighten: a capability already False stays False.  Unknown
    capability names are rejected rather than ignored.
    """
    names = tuple(str(name) for name in denied)
    unknown = [name for name in names if name not in CAPABILITY_NAMES]
    if unknown:
        raise SandboxError(f"unknown sandbox capability: {unknown}")
    caps = policy.capabilities
    for name in names:
        caps[name] = False
    denied_all = tuple(sorted(set(policy.denied_capabilities) | set(names)))
    return SandboxPolicy(
        mode=policy.mode,
        workspace_root=policy.workspace_root,
        network=caps[CAP_NETWORK],
        process_spawn=caps[CAP_PROCESS_SPAWN],
        write_outside_workspace=caps[CAP_WRITE_OUTSIDE],
        read_outside_workspace=caps[CAP_READ_OUTSIDE],
        denied_capabilities=denied_all,
        audit_hook=policy.audit_hook,
    )


def merge_sandbox(base: SandboxPolicy, overlay: SandboxPolicy) -> SandboxPolicy:
    """Intersect two policies: the result is never wider than either input.

    The more restrictive mode wins and every capability is the logical AND of
    the two, so an overlay that tries to grant a denied capability cannot.
    """
    if base.workspace_root != overlay.workspace_root:
        raise SandboxError("cannot merge policies with different workspace roots")
    mode = base.mode if base.restrictiveness >= overlay.restrictiveness else overlay.mode
    a, b = base.capabilities, overlay.capabilities
    caps = {name: a[name] and b[name] for name in CAPABILITY_NAMES}
    denied = tuple(sorted(set(base.denied_capabilities) | set(overlay.denied_capabilities)))
    return SandboxPolicy(
        mode=mode,
        workspace_root=base.workspace_root,
        network=caps[CAP_NETWORK],
        process_spawn=caps[CAP_PROCESS_SPAWN],
        write_outside_workspace=caps[CAP_WRITE_OUTSIDE],
        read_outside_workspace=caps[CAP_READ_OUTSIDE],
        denied_capabilities=denied,
        audit_hook=base.audit_hook or overlay.audit_hook,
    )


def can_widen_sandbox(base: SandboxPolicy, overlay: SandboxPolicy) -> bool:
    """Always False — a policy merge is an intersection, never a widening."""
    return False


@dataclass(frozen=True)
class SandboxArgv:
    """The exact argv a consumer hands to a backend (no process is spawned)."""

    argv: tuple[str, ...]
    workspace_root: str
    mode: SandboxMode
    wrap_required: bool
    spawn: bool = False
    io_performed: bool = False


def handoff_argv(policy: SandboxPolicy, argv: Sequence[object]) -> SandboxArgv:
    """Describe the exact argv handed over; the backend wraps/enforces it."""
    exact = tuple(str(item) for item in argv)
    if not exact:
        raise SandboxError("argv must not be empty")
    return SandboxArgv(
        argv=exact,
        workspace_root=policy.workspace_root,
        mode=policy.mode,
        wrap_required=(policy.mode is not SandboxMode.OFF),
    )


def enforcement_report(policy: SandboxPolicy) -> dict:
    """Shape a backend uses to report what it actually enforced."""
    return {
        "backend_reported": policy.enforcement_reported,
        "mode": policy.mode.value,
        "workspace_root": policy.workspace_root,
        "capabilities": policy.capabilities,
        "denied_capabilities": policy.denied_capabilities,
        "audit_hook": policy.audit_hook,
        **_descriptor_flags(),
    }


# ===========================================================================
# E7.2 — toolResultPruner: model-free, replayable, secret-safe pruning
# ===========================================================================
@dataclass(frozen=True)
class PrunableResult:
    """A single tool result offered to the pruner (current vs historical)."""

    tool_use_id: str
    value: str
    is_current: bool = True
    secret_markers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.tool_use_id:
            raise PruneError("tool_use_id must be non-empty")


# Redact high-entropy secret shapes before any truncation.  Caller-provided
# markers are handled literally in ``redact_text``.
_SECRET_PATTERNS: tuple[str, ...] = (
    r"sk-[A-Za-z0-9_\-]{16,}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"Bearer\s+[A-Za-z0-9._\-]+",
    r"(?i)(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
)
_REDACTED = "[REDACTED]"


def redact_text(text: str, secret_markers: Iterable[str] = (),
                patterns: Iterable[str] = _SECRET_PATTERNS) -> str:
    """Replace known markers and secret-shaped spans before truncation.

    Redaction happens over the *whole* value, so a secret can never straddle a
    later preview boundary.  Pure and deterministic.
    """
    out = text
    for marker in secret_markers:
        if marker:
            out = out.replace(marker, _REDACTED)
    for pattern in patterns:
        out = re.sub(pattern, _REDACTED, out)
    return out


@dataclass(frozen=True)
class Replacement:
    """Replayable surface replacement for an oversized current tool result."""

    tool_use_id: str
    artifact_key: str
    preview: str
    original_chars: int
    original_bytes: int
    digest: str
    secret_redacted: bool
    kind: str = "replacement"
    replayable: bool = True
    network: bool = False


@dataclass(frozen=True)
class ArtifactSeam:
    """In-memory artifact store.  Preserves full values for replay, no FS I/O."""

    _artifacts: Mapping[str, str] = field(default_factory=dict)

    def put(self, key: str, value: str) -> str:
        mutable = dict(self._artifacts)
        mutable[key] = value
        object.__setattr__(self, "_artifacts", dict(mutable))
        return key

    def get(self, key: str) -> str:
        try:
            return self._artifacts[key]
        except KeyError as exc:
            raise PruneError(f"artifact not found: {key}") from exc

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._artifacts))

    def replay(self, replacement: Replacement) -> str:
        return replay_replacement(replacement, self)


def replay_replacement(replacement: Replacement, seam: ArtifactSeam) -> str:
    """Re-inflate the full original value from the artifact seam."""
    if not replacement.replayable:
        raise PruneError("replacement is not replayable")
    return seam.get(replacement.artifact_key)


@dataclass(frozen=True)
class PrunePolicy:
    """Thresholds for the model-free pruning step."""

    max_inline_chars: int = 30_000
    preview_chars: int = 2_000
    secret_patterns: tuple[str, ...] = _SECRET_PATTERNS

    def __post_init__(self) -> None:
        if self.max_inline_chars < 1 or self.preview_chars < 1:
            raise PruneError("prune thresholds must be positive")


DEFAULT_PRUNE_POLICY = PrunePolicy()


class PruneAction(str, Enum):
    KEEP_INLINE = "keep_inline"
    REPLACE = "replace"


@dataclass(frozen=True)
class PruneDecision:
    """One result's pruning outcome, with a human-readable, model-free reason."""

    tool_use_id: str
    action: PruneAction
    reason: str
    replacement: Optional[Replacement] = None


@dataclass(frozen=True)
class PruneReport:
    """Deterministic result of :func:`prune_current_results`."""

    decisions: tuple[PruneDecision, ...]

    @property
    def pruned_count(self) -> int:
        return sum(d.action is PruneAction.REPLACE for d in self.decisions)

    @property
    def preserved_count(self) -> int:
        return sum(d.action is PruneAction.KEEP_INLINE for d in self.decisions)


def _artifact_key(tool_use_id: str, value: str) -> tuple[str, str]:
    digest = hashlib.sha256(
        (tool_use_id + "\x00" + value).encode("utf-8", errors="replace")
    ).hexdigest()
    return f"tool-result:{tool_use_id}:{digest[:16]}", digest


def prune_current_results(results: Iterable[PrunableResult], *,
                          policy: PrunePolicy = DEFAULT_PRUNE_POLICY,
                          seam: ArtifactSeam | None = None) -> PruneReport:
    """Prune oversized *current* results into replayable replacements.

    Model-free (no summarization call).  Historical results are left inline.
    The full original value is preserved in the artifact seam; the model-facing
    preview is redacted *before* truncation so secrets never leak, and the
    replacement explicitly flags ``secret_redacted`` rather than truncating
    silently.  Re-running with the same inputs yields the same report.
    """
    store = seam if seam is not None else ArtifactSeam()
    decisions: list[PruneDecision] = []
    for result in results:
        if not result.is_current:
            decisions.append(PruneDecision(
                result.tool_use_id, PruneAction.KEEP_INLINE,
                "historical result — pruning is limited to current results"))
            continue
        if len(result.value) <= policy.max_inline_chars:
            decisions.append(PruneDecision(
                result.tool_use_id, PruneAction.KEEP_INLINE,
                "within inline cap — no summarization performed"))
            continue

        redacted = redact_text(result.value, result.secret_markers,
                               policy.secret_patterns)
        truncated = len(redacted) > policy.preview_chars
        marker = "…[pruned]"
        if truncated and policy.preview_chars >= len(marker):
            preview = redacted[:policy.preview_chars - len(marker)] + marker
        else:
            preview = redacted[:policy.preview_chars]  # always bounded by the cap
        key, digest = _artifact_key(result.tool_use_id, result.value)
        store.put(key, result.value)
        replacement = Replacement(
            tool_use_id=result.tool_use_id,
            artifact_key=key,
            preview=preview,
            original_chars=len(result.value),
            original_bytes=len(result.value.encode("utf-8", errors="replace")),
            digest=digest,
            secret_redacted=(redacted != result.value),
        )
        decisions.append(PruneDecision(
            result.tool_use_id, PruneAction.REPLACE,
            "oversized current result — replayable replacement produced deterministically",
            replacement))
    return PruneReport(tuple(decisions))


# ===========================================================================
# E7.20 — permissionPresets: one logged event updates both knobs
# ===========================================================================
class ApprovalPolicy(str, Enum):
    """User-facing approval policy bundled into a permission preset."""

    ASK_EVERYTHING = "ask_everything"
    ASK_OUTSIDE_WORKSPACE = "ask_outside_workspace"
    ALLOW_ALL = "allow_all"


@dataclass(frozen=True)
class PermissionPreset:
    """A named bundle of sandbox mode + approval policy (V5 presets)."""

    name: str
    sandbox_mode: SandboxMode
    approval_policy: ApprovalPolicy
    description: str


PRESETS: tuple[PermissionPreset, ...] = (
    PermissionPreset(
        "cautious", SandboxMode.STRICT, ApprovalPolicy.ASK_EVERYTHING,
        "Lock everything to the workspace and ask on every action."),
    PermissionPreset(
        "balanced", SandboxMode.WORKSPACE, ApprovalPolicy.ASK_OUTSIDE_WORKSPACE,
        "Confine writes to the workspace; ask only for outside actions."),
    PermissionPreset(
        "trusted", SandboxMode.OFF, ApprovalPolicy.ALLOW_ALL,
        "Explicit opt-in: unrestricted sandbox and automatic approvals."),
)
_PRESET_BY_NAME = {p.name: p for p in PRESETS}

KNOB_SANDBOX_MODE = "sandbox_mode"
KNOB_APPROVAL_POLICY = "approval_policy"
VALID_KNOBS = frozenset({KNOB_SANDBOX_MODE, KNOB_APPROVAL_POLICY})


def preset_list() -> tuple[PermissionPreset, ...]:
    """Return the typed list of shipped presets."""
    return PRESETS


def preset_by_name(name: str) -> PermissionPreset:
    try:
        return _PRESET_BY_NAME[str(name)]
    except KeyError as exc:
        raise PresetError(f"unknown permission preset: {name!r}") from exc


@dataclass(frozen=True)
class ExplicitOverride:
    """A knob the user set explicitly; it survives later preset switches."""

    knob: str
    value: str
    source: str = "user"


@dataclass(frozen=True)
class PresetEvent:
    """One logged permission/preset event that updates both knobs at once."""

    kind: str
    from_preset: str
    to_preset: str
    sandbox_mode: SandboxMode
    approval_policy: ApprovalPolicy
    preserved_overrides: tuple[ExplicitOverride, ...] = ()
    single_event: bool = True


@dataclass(frozen=True)
class PresetState:
    """Effective permission state: active preset + knobs + explicit overrides."""

    active_preset: str
    sandbox_mode: SandboxMode
    approval_policy: ApprovalPolicy
    overrides: tuple[ExplicitOverride, ...] = ()


@dataclass(frozen=True)
class PresetSwitch:
    """Result of a switch: a new state and exactly one logged event."""

    state: PresetState
    event: PresetEvent
    events: tuple[PresetEvent, ...]


def initial_state(preset_name: str = "balanced") -> PresetState:
    preset = preset_by_name(preset_name)
    return PresetState(
        active_preset=preset.name,
        sandbox_mode=preset.sandbox_mode,
        approval_policy=preset.approval_policy,
    )


def set_override(state: PresetState, knob: str, value: object) -> PresetState:
    """Record an explicit override on a knob, validating its value."""
    if knob not in VALID_KNOBS:
        raise PresetError(f"unknown preset knob: {knob!r}")
    if knob == KNOB_SANDBOX_MODE:
        coerced = _enum(SandboxMode, value, PresetError).value
    else:
        coerced = _enum(ApprovalPolicy, value, PresetError).value
    kept = tuple(ov for ov in state.overrides if ov.knob != knob)
    overrides = kept + (ExplicitOverride(knob, str(coerced)),)
    return PresetState(
        active_preset=state.active_preset,
        sandbox_mode=(_enum(SandboxMode, coerced, PresetError)
                      if knob == KNOB_SANDBOX_MODE else state.sandbox_mode),
        approval_policy=(_enum(ApprovalPolicy, coerced, PresetError)
                         if knob == KNOB_APPROVAL_POLICY else state.approval_policy),
        overrides=overrides,
    )


def clear_override(state: PresetState, knob: str) -> PresetState:
    """Drop an explicit override so future switches use the preset value."""
    if knob not in VALID_KNOBS:
        raise PresetError(f"unknown preset knob: {knob!r}")
    return PresetState(
        active_preset=state.active_preset,
        sandbox_mode=state.sandbox_mode,
        approval_policy=state.approval_policy,
        overrides=tuple(ov for ov in state.overrides if ov.knob != knob),
    )


def switch_preset(state: PresetState, preset_name: str) -> PresetSwitch:
    """Switch presets, updating both knobs in one logged event.

    Explicit user overrides are preserved: for each overridden knob the user's
    value wins over the newly selected preset's value.  The event lists exactly
    which overrides were preserved.
    """
    preset = preset_by_name(preset_name)
    mode = preset.sandbox_mode
    approval = preset.approval_policy
    preserved: list[ExplicitOverride] = []
    for override in state.overrides:
        if override.knob == KNOB_SANDBOX_MODE:
            mode = _enum(SandboxMode, override.value, PresetError)
            preserved.append(override)
        elif override.knob == KNOB_APPROVAL_POLICY:
            approval = _enum(ApprovalPolicy, override.value, PresetError)
            preserved.append(override)

    new_state = PresetState(
        active_preset=preset.name,
        sandbox_mode=mode,
        approval_policy=approval,
        overrides=state.overrides,
    )
    event = PresetEvent(
        kind="permission_preset_switched",
        from_preset=state.active_preset,
        to_preset=preset.name,
        sandbox_mode=mode,
        approval_policy=approval,
        preserved_overrides=tuple(preserved),
    )
    return PresetSwitch(state=new_state, event=event, events=(event,))


# ===========================================================================
# E7.21 — fs-observation-policy: read-before-edit + stale detection
# ===========================================================================
def hash_content(data: bytes) -> str:
    """Pure content hash of caller-supplied bytes (no file is read)."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Observation:
    """Observed state of a path, supplied by the caller (never read from disk)."""

    path: str
    content_hash: str
    mtime_ns: int
    size: int
    seq: int = 0


@dataclass(frozen=True)
class ObservationCheck:
    """Result of a read-before-edit check."""

    path: str
    allowed: bool
    reason: str
    observation: Optional[Observation] = None
    io_performed: bool = False
    network: bool = False


@dataclass(frozen=True)
class StaleCheck:
    """Result of a stale-file detection (hash and/or mtime discrepancy)."""

    path: str
    stale: bool
    reason: str
    observed: Optional[Observation] = None
    current: Optional[Observation] = None
    io_performed: bool = False
    network: bool = False


def check_read_before_edit(path: object,
                           observations: Mapping[str, Observation]) -> ObservationCheck:
    """Allow an edit only when the path has a prior observation (rule 13)."""
    key = str(path)
    observation = observations.get(key)
    if observation is None:
        return ObservationCheck(
            key, False,
            "read-before-edit: no observed state for this path")
    return ObservationCheck(
        key, True, "read-before-edit: observation present", observation)


def detect_stale(observed: Observation, current: Observation) -> StaleCheck:
    """Detect drift between observed and current state by hash and mtime."""
    hash_changed = observed.content_hash != current.content_hash
    mtime_advanced = current.mtime_ns > observed.mtime_ns
    stale = hash_changed or mtime_advanced
    if stale:
        reasons = []
        if hash_changed:
            reasons.append("content hash changed")
        if mtime_advanced:
            reasons.append("mtime advanced")
        reason = "stale file: " + " and ".join(reasons)
    else:
        reason = "fresh: observed state matches current state"
    return StaleCheck(observed.path, stale, reason, observed, current)


class FsEvent(str, Enum):
    """The ``fs/*`` event gate event names."""

    READ = "fs.read"
    EDIT = "fs.edit"
    WRITE = "fs.write"
    DELETE = "fs.delete"


@dataclass(frozen=True)
class GateVerdict:
    """Typed verdict contributed by the observation policy to the fs gate."""

    event: FsEvent
    path: str
    allowed: bool
    reason: str
    stale: bool = False
    io_performed: bool = False
    network: bool = False


def fs_event_gate(event: object, path: object, *,
                  observations: Mapping[str, Observation] | None = None,
                  observed: Observation | None = None,
                  current: Observation | None = None) -> GateVerdict:
    """Evaluate a ``fs/*`` gate event with observation / stale preconditions.

    ``fs.read`` records observation (the caller supplies it) and is allowed;
    mutating events require a prior observation and, when both states are
    supplied, reject a stale file.  No filesystem access occurs.
    """
    gate_event = _enum(FsEvent, event, ObservationError)
    key = str(path)
    obs = observations or {}

    if gate_event is FsEvent.READ:
        return GateVerdict(gate_event, key, True,
                           "fs.read: observation accepted (no I/O performed)")

    check = check_read_before_edit(key, obs)
    if not check.allowed:
        return GateVerdict(gate_event, key, False, check.reason)

    if observed is not None and current is not None:
        stale_check = detect_stale(observed, current)
        if stale_check.stale:
            return GateVerdict(gate_event, key, False, stale_check.reason,
                               stale=True)
    return GateVerdict(gate_event, key, True,
                       "observation present and fresh; stale check passed")


# ===========================================================================
# E7.23 — web seam: one service, stable tool names, free backends only
# ===========================================================================
WEB_SEARCH_TOOL = "web_search"
WEB_FETCH_TOOL = "web_fetch"


class ProviderKind(str, Enum):
    SEARCH = "search"
    FETCH = "fetch"


_STABLE_TOOL_NAME = {
    ProviderKind.SEARCH: WEB_SEARCH_TOOL,
    ProviderKind.FETCH: WEB_FETCH_TOOL,
}


@dataclass(frozen=True)
class WebProvider:
    """A registered free search/fetch backend (descriptor only, no network)."""

    name: str
    kind: ProviderKind
    backend: str
    tool_name: str
    free: bool = True
    paid_only: bool = False
    auth_required: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise WebSeamError("provider name must be non-empty")
        object.__setattr__(self, "kind",
                           _enum(ProviderKind, self.kind, WebSeamError))


@dataclass(frozen=True)
class WebCallDescriptor:
    """A prospective web tool call.  It never executes a request."""

    tool_name: str
    provider: str
    kind: ProviderKind
    params: tuple[tuple[str, str], ...]
    network: bool = False
    io_performed: bool = False


class WebService:
    """One service that search/fetch providers register into.

    Tool names are stable regardless of which provider is active, so callers
    (and the model) never see a backend-specific tool name.
    """

    def __init__(self) -> None:
        self._providers: dict[tuple[ProviderKind, str], WebProvider] = {}

    def register(self, provider: WebProvider) -> WebProvider:
        if not isinstance(provider, WebProvider):
            raise WebSeamError("provider must be a WebProvider")
        if not provider.free or provider.paid_only:
            raise WebSeamError("web seam accepts free backends only")
        expected = _STABLE_TOOL_NAME[provider.kind]
        if provider.tool_name != expected:
            raise WebSeamError(
                f"tool name must stay stable ({expected!r}), got {provider.tool_name!r}")
        key = (provider.kind, provider.name)
        existing = self._providers.get(key)
        if existing is not None and existing != provider:
            raise WebSeamError(f"conflicting registration for {key!r}")
        self._providers[key] = provider
        return provider

    def resolve(self, kind: object, name: str | None = None) -> WebProvider:
        provider_kind = _enum(ProviderKind, kind, WebSeamError)
        if name is None:
            matches = [p for (k, _), p in self._providers.items() if k is provider_kind]
            if not matches:
                raise WebSeamError(f"no {provider_kind.value} provider registered")
            return sorted(matches, key=lambda p: p.name)[0]
        try:
            return self._providers[(provider_kind, name)]
        except KeyError as exc:
            raise WebSeamError(f"unknown {provider_kind.value} provider: {name!r}") from exc

    def tool_names(self) -> frozenset[str]:
        return frozenset(_STABLE_TOOL_NAME.values())

    def invoke(self, kind: object, name: str | None = None,
               **params: Any) -> WebCallDescriptor:
        provider = self.resolve(kind, name)
        return WebCallDescriptor(
            tool_name=provider.tool_name,
            provider=provider.name,
            kind=provider.kind,
            params=_params(params),
        )


def default_web_service() -> WebService:
    """Build the shipped web seam: SearXNG search + plain HTTP fetch (A1.11)."""
    service = WebService()
    service.register(WebProvider("searxng", ProviderKind.SEARCH,
                                 "searxng", WEB_SEARCH_TOOL))
    service.register(WebProvider("plain-http", ProviderKind.FETCH,
                                 "http", WEB_FETCH_TOOL))
    return service


# ===========================================================================
# E7.6 — workspaceFiles: descriptors + path containment, no FS I/O
# ===========================================================================
@dataclass(frozen=True)
class FileStat:
    path: str
    size: int
    kind: str
    mtime_ns: int = 0
    content_hash: str = ""
    io_performed: bool = False
    network: bool = False


def stat_descriptor(root: object, path: object, *, size: int, kind: str,
                    mtime_ns: int = 0, content_hash: str = "") -> FileStat:
    """Describe a stat result for a contained path (caller supplies metadata)."""
    if kind not in ("file", "dir", "symlink"):
        raise WorkspacePathError(f"unknown file kind: {kind!r}")
    return FileStat(contained_path(root, path), int(size), kind,
                    int(mtime_ns), str(content_hash))


@dataclass(frozen=True)
class TextPage:
    path: str
    page: int
    page_size: int
    lines: tuple[str, ...]
    total_lines: int
    has_more: bool
    io_performed: bool = False
    network: bool = False


def paged_text(root: object, path: object, text: str, *, page: int = 0,
               page_size: int = 100) -> TextPage:
    """Return one page of caller-supplied text.  Pure, deterministic pagination."""
    if page < 0 or page_size < 1:
        raise WorkspacePathError("page must be >= 0 and page_size must be >= 1")
    lines = str(text).splitlines()
    start = page * page_size
    chunk = tuple(lines[start:start + page_size])
    return TextPage(
        contained_path(root, path), page, page_size, chunk, len(lines),
        (start + page_size) < len(lines),
    )


@dataclass(frozen=True)
class ByteWindow:
    path: str
    offset: int
    length: int
    data: bytes
    total_bytes: int
    truncated: bool
    io_performed: bool = False
    network: bool = False


def byte_window(root: object, path: object, data: bytes, *, offset: int = 0,
                length: int = 4096) -> ByteWindow:
    """Return an exact byte window of caller-supplied bytes (clamped at EOF)."""
    if offset < 0 or length < 0:
        raise WorkspacePathError("offset and length must be non-negative")
    total = len(data)
    end = min(offset + length, total)
    window = bytes(data[offset:end])
    return ByteWindow(
        contained_path(root, path), offset, length, window, total,
        (offset + length) > total,
    )


@dataclass(frozen=True)
class DirEntry:
    name: str
    kind: str
    size: int = 0


@dataclass(frozen=True)
class DirectoryListing:
    path: str
    entries: tuple[DirEntry, ...]
    io_performed: bool = False
    network: bool = False


def directory_listing(root: object, path: object,
                      entries: Iterable[Sequence[object]]) -> DirectoryListing:
    """Describe a directory listing from caller-supplied entry tuples."""
    described = tuple(
        DirEntry(str(item[0]), str(item[1]), int(item[2]) if len(item) > 2 else 0)
        for item in entries
    )
    return DirectoryListing(contained_path(root, path), described)


@dataclass(frozen=True)
class ChangeEvent:
    seq: int
    path: str
    kind: str
    mtime_ns: int = 0
    content_hash: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("created", "modified", "deleted"):
            raise WorkspacePathError(f"unknown change kind: {self.kind!r}")


def change_feed(events: Iterable[ChangeEvent], *,
                root: object | None = None) -> tuple[ChangeEvent, ...]:
    """Return a change feed ordered by sequence; optionally confine paths."""
    materialised = tuple(events)
    if root is not None:
        for event in materialised:
            contained_path(root, event.path)
    return tuple(sorted(materialised, key=lambda e: e.seq))


WORKSPACE_FILES_TOOLS: tuple[str, ...] = (
    "workspace.stat", "workspace.readText", "workspace.readBytes",
    "workspace.listDirectory", "workspace.changes",
)


# ===========================================================================
# aggregate descriptor for all six features
# ===========================================================================
_FEATURE_CONTRACTS: dict[str, str] = {
    "E7.18": "resolve_sandbox(mode, workspace) -> SandboxPolicy; no permissive "
             "fallback; denies cannot be widened; one workspace root for bash/fs.",
    "E7.2": "prune_current_results() replaces oversized current results with "
            "replayable descriptors; full values preserved in ArtifactSeam; "
            "secrets redacted before truncation; model-free and deterministic.",
    "E7.20": "preset_list() bundles sandbox mode + approval policy; switch_preset() "
             "writes exactly one logged event and preserves explicit overrides.",
    "E7.21": "check_read_before_edit()/detect_stale()/fs_event_gate() contribute "
             "hash/mtime-based observation verdicts through the fs/* gate, no I/O.",
    "E7.23": "WebService registers free search/fetch providers; tool names stay "
             "stable across swaps; invoke() descriptors perform no network call.",
    "E7.6": "stat/paged_text/byte_window/directory_listing/change_feed descriptors "
            "are confined by lexical path containment; no filesystem I/O.",
}


def feature_descriptors() -> dict[str, dict]:
    """One uniform summary row per owned feature ID (all descriptor-only)."""
    return {
        fid: {**_descriptor_flags(), "feature_id": fid,
              "contract": _FEATURE_CONTRACTS[fid]}
        for fid in FEATURE_IDS
    }
