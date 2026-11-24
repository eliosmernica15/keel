"""E3 backend: subagent activation tree, messaging and lifecycle (stdlib only).

This module implements the host-side behaviour for the thirteen ``not_started``
**P1/P2** rows of addendum-7 section 4 ("Subagents", DS-SUB): E3.1, E3.2,
E3.4, E3.5, E3.6, E3.7, E3.9, E3.10, E3.11, E3.12, E3.13, E3.14 and E3.15.
The two **P0** rows in that section (E3.3 agent names and E3.8 results) already
live in :mod:`keel.result_contracts`; this module *reuses* them rather than
duplicating them, and :func:`verify_p0_contracts` is the executable check that
they are still present and behaving as documented.

The module is deliberately real but host-free: it owns in-memory state for one
activation tree (identities, activations, inbox, events, providers and the
live model-route setting) and implements the state transitions those rows
require.  It opens no file, socket, subprocess, clock or random source.  Every
identifier, path, message, schema, sequence-bearing step and byte of text is
supplied by the caller; only the ordering counter is derived from call order,
so a replay of the same calls yields byte-identical state.  ``to_dict``-style
exchange is intentionally omitted: callers persist plain dataclass fields with
their own storage layer, exactly as they do for ``result_contracts``.

Feature map
-----------
* **E3.1** -- :class:`Capability`, :class:`ProviderCapabilities`,
  :class:`StartOptions`, :func:`validate_start_options` and
  :meth:`SubagentManager.start` form *one* activation API for local children
  and external executions.  The four capability flags ``agent_options``,
  ``agent_preset``, ``output_schema`` and ``depth_limit`` are checked before
  any state is mutated or any child/event exists.
* **E3.2** -- :class:`DeliveryPolicy` (``parent`` / ``caller``);
  :meth:`SubagentManager.settle` notifies the model with a settled notice on
  ``parent`` and returns the result to the caller only on ``caller``.
* **E3.4** -- :class:`ChildWorkingDirectory` and :func:`resolve_child_cwd`:
  the child cwd is chosen at admission, relative paths resolve against the
  parent's current directory, local children keep the parent's project, and a
  cold resume reuses the logged cwd.
* **E3.5** -- :class:`ChildNode` + :class:`Activation`: a local child is a
  durable identity with at most one live activation; the manager owns capacity
  reservation, input admission, cold resume and child-first disposal;
  structured-output capture closes that activation's input; resume does not
  inherit the schema.
* **E3.6** -- :class:`SpawnMode`, :class:`TurnStep`, :class:`ForkSeed` and
  :func:`compute_fork_prefix`: fork seeds a contiguous, lossless, balanced
  completed-turn prefix; spawn starts fresh; ``inherits_parent_context`` is
  recorded as wording-only and never changes behaviour.
* **E3.7** -- ``EXTERNAL_EXECUTION`` capability, :class:`ProviderRecord.online`
  and ``Activation.one_shot``: external backends get exactly one execution, no
  follow-ups, and results reach the creator only while online.
* **E3.9** -- :func:`send_message` with :class:`MessageSource` (``agent-message``
  relay vs ``subagent-settled`` runtime notice): a running target is steered,
  an absent one cold-resumes, sender identity is rechecked and accepted
  messages are never retracted.  A settled notice is never attributed to the
  child as words it wrote.
* **E3.10** -- :func:`interrupt`: only ``user`` or an exact live ancestor may
  interrupt; it is fire-and-return, preserves the unclaimed inbox, the
  activation and descendants, never requeues claimed work, and a missing
  target is a no-op.
* **E3.11** -- :func:`drain_tree` and :func:`wait_for_tree_work`: whole-tree
  drain settles live work child-first; idle members with parked input stay
  resident and do not delay host completion.
* **E3.12** -- :class:`CatalogEntry` / :func:`list_descendants`: parent-owned
  membership projection (no execution status), recursive with depth/path,
  per-branch ``unsupported``/``corrupt``/``unavailable`` diagnostics, cycles and
  repeats skipped, and historical unavailable descriptors shown as ``unknown``
  mode without continuation rights.
* **E3.13** -- :class:`ModelRouteAllowlist` / :func:`set_route_allowlist`:
  default-off allowlist of ``provider/model`` routes read live on every
  delegation; malformed or duplicate routes fail closed.
* **E3.14** -- :class:`Attachment` and :func:`send_message`: a user-authored
  message to a child with image parts (admitted through a caller-owned
  attachment store, only when the model accepts images) and client time zone;
  cold resume at capacity raises typed :class:`DeliveryUnavailable`.
* **E3.15** -- :class:`LifecycleKind` / :class:`LifecycleEvent`:
  ``subagent/start`` and ``subagent/end`` scoped to the tree root, plus
  provider added/removed events.

Security invariants (enforced by ``test_e3_backend``):

* unknown or malformed values fail closed with a typed, coded error;
* invalid start options never create state -- validation precedes everything;
* names are references only (E3.3), results are sanitized (E3.8) and no
  credential value is ever stored in a message, route or diagnostic;
* no message is retracted, no claimed item is requeued and no external
  execution is followed up once it has settled.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping

from keel.result_contracts import (
    Result,
    StopReason,
    ContractValidationError,
    build_result,
    child_failure_to_result,
    make_agent_name,
    parse_stop_reason,
    validate_agent_name,
)

FEATURE_IDS = (
    "E3.1", "E3.2", "E3.4", "E3.5", "E3.6", "E3.7", "E3.9", "E3.10",
    "E3.11", "E3.12", "E3.13", "E3.14", "E3.15",
)
P0_VERIFIED_IDS = ("E3.3", "E3.8")
USER_ACTOR = "user"
BUILTIN_LOCAL_PROVIDER = "local"
ROOT_AGENT_NAME = "lead"

ERR_VALIDATION = "E3_VALIDATION"
ERR_CAPABILITY = "CAPABILITY_NOT_SUPPORTED"
ERR_AT_CAPACITY = "DELIVERY_UNAVAILABLE"
ERR_ALREADY_ACTIVE = "ALREADY_ACTIVE"
ERR_ALREADY_SETTLED = "ALREADY_SETTLED"
ERR_NO_FOLLOW_UP = "NO_FOLLOW_UP"
ERR_INTERRUPT_DENIED = "INTERRUPT_DENIED"
ERR_ROUTE_NOT_ALLOWED = "ROUTE_NOT_ALLOWED"
ERR_INVALID_ROUTE = "INVALID_ROUTE"
ERR_FORK_PREFIX = "INVALID_FORK_PREFIX"
ERR_IMAGE_NOT_ACCEPTED = "IMAGE_NOT_ACCEPTED"
ERR_INPUT_CLOSED = "INPUT_CLOSED"
ERR_NOT_FOUND = "NOT_FOUND"

_SAFE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/\-]*$")
_ABSOLUTE_PATH_RE = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Typed, coded, fail-closed errors
# ---------------------------------------------------------------------------


class E3Error(ValueError):
    """Base error; every instance carries a stable machine-readable code."""

    code = ERR_VALIDATION

    def __init__(self, message: Any = "", *, code: str | None = None,
                 errors: Iterable[Any] = ()) -> None:
        self.code = code or type(self).code
        self.errors = tuple(str(e) for e in errors) or (str(message),)
        super().__init__("%s: %s" % (self.code, "; ".join(self.errors)))


class E3ValidationError(E3Error):
    """A caller value was malformed or unknown."""


class CapabilityNotSupported(E3Error):
    """Start options require a capability the provider does not advertise."""

    code = ERR_CAPABILITY


class DeliveryUnavailable(E3Error):
    """Typed delivery-unavailable rejection (cold resume at capacity)."""

    code = ERR_AT_CAPACITY


class AlreadyActive(E3Error):
    """A durable child already has a live activation."""

    code = ERR_ALREADY_ACTIVE


class AlreadySettled(E3Error):
    """An activation has already been settled and cannot be settled twice."""

    code = ERR_ALREADY_SETTLED


class NoFollowUp(E3Error):
    """An external one-shot execution cannot be resumed or steered."""

    code = ERR_NO_FOLLOW_UP


class InterruptDeniedError(E3Error):
    """The actor is neither the user nor an exact live ancestor."""

    code = ERR_INTERRUPT_DENIED


class RouteError(E3Error):
    """A model route was malformed or duplicated."""

    code = ERR_INVALID_ROUTE


class RouteNotAllowed(E3Error):
    """The live allowlist is off or does not contain the requested route."""

    code = ERR_ROUTE_NOT_ALLOWED


class ForkPrefixError(E3Error):
    """A fork seed was missing, non-contiguous, lossy or unbalanced."""

    code = ERR_FORK_PREFIX


class ImageNotAccepted(E3Error):
    """An image attachment was sent to a model that does not accept images."""

    code = ERR_IMAGE_NOT_ACCEPTED


class InputClosed(E3Error):
    """Structured-output capture closed this activation's input."""

    code = ERR_INPUT_CLOSED


class NotFoundError(E3Error):
    """A referenced node, provider or activation does not exist."""

    code = ERR_NOT_FOUND


# ---------------------------------------------------------------------------
# Small boundary validators (caller data is untrusted)
# ---------------------------------------------------------------------------


def _require_id(value: Any, label: str = "id") -> str:
    """Return a trimmed, printable, bounded opaque identifier."""
    text = "" if value is None else str(value)
    if (not text or text != text.strip() or len(text) > 256 or _CONTROL_RE.search(text)
            or any(ch.isspace() for ch in text)):
        raise E3ValidationError("%s must be a non-empty printable string (<=256 chars, no spaces)" % label)
    return text


def _require_text(value: Any, label: str = "text", *, allow_empty: bool = False) -> str:
    """Return caller text; control characters other than newline/tab are refused."""
    text = "" if value is None else str(value)
    if not allow_empty and not text.strip():
        raise E3ValidationError("%s must not be empty" % label)
    if len(text) > 16384:
        raise E3ValidationError("%s exceeds 16384 characters" % label)
    if any(ord(ch) < 0x20 and ch not in "\n\t" for ch in text) or "\x7f" in text:
        raise E3ValidationError("%s contains a control character" % label)
    return text


def _require_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise E3ValidationError("%s must be an integer" % label)
    return value


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise E3ValidationError("%s must be a boolean" % label)
    return value


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise E3ValidationError("%s must be a mapping" % label)
    return dict(value)


# ---------------------------------------------------------------------------
# E3.1 -- capabilities, start options and validation
# ---------------------------------------------------------------------------


class Capability(str, Enum):
    """Provider capability flags advertised before any execution starts."""

    AGENT_OPTIONS = "agent_options"
    AGENT_PRESET = "agent_preset"
    OUTPUT_SCHEMA = "output_schema"
    DEPTH_LIMIT = "depth_limit"
    EXTERNAL_EXECUTION = "external_execution"
    IMAGES = "images"


E3_1_CAPABILITIES = frozenset({
    Capability.AGENT_OPTIONS,
    Capability.AGENT_PRESET,
    Capability.OUTPUT_SCHEMA,
    Capability.DEPTH_LIMIT,
})


def _parse_capability(value: Any) -> Capability:
    try:
        return Capability(value)
    except (ValueError, TypeError) as exc:
        raise E3ValidationError("unknown provider capability %r" % (value,)) from exc


@dataclass(frozen=True)
class ProviderCapabilities:
    """Immutable capability declaration supplied by a provider caller."""

    provider_id: str
    flags: frozenset[Capability] = frozenset()
    accepts_images: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _require_id(self.provider_id, "provider_id"))
        object.__setattr__(self, "flags", frozenset(_parse_capability(c) for c in self.flags))
        object.__setattr__(self, "accepts_images", _require_bool(self.accepts_images, "accepts_images"))

    def supports(self, capability: Capability) -> bool:
        """True when this provider advertises ``capability``."""
        return _parse_capability(capability) in self.flags


@dataclass(frozen=True)
class StartOptions:
    """The four E3.1 capability-gated options of one activation request."""

    agent_options: Mapping[str, Any] | None = None
    agent_preset: str | None = None
    output_schema: Mapping[str, Any] | None = None
    depth_limit: int | None = None

    def __post_init__(self) -> None:
        if self.agent_options is not None:
            object.__setattr__(self, "agent_options", _require_mapping(self.agent_options, "agent_options"))
        if self.agent_preset is not None:
            object.__setattr__(self, "agent_preset", _require_id(self.agent_preset, "agent_preset"))
        if self.output_schema is not None:
            schema = _require_mapping(self.output_schema, "output_schema")
            if not schema:
                raise E3ValidationError("output_schema must not be empty")
            object.__setattr__(self, "output_schema", schema)
        if self.depth_limit is not None:
            limit = _require_int(self.depth_limit, "depth_limit")
            if limit < 0:
                raise E3ValidationError("depth_limit must be non-negative")
            object.__setattr__(self, "depth_limit", limit)


def validate_start_options(
    options: StartOptions, capabilities: ProviderCapabilities
) -> tuple[str, ...]:
    """Return every reason ``options`` exceed the provider's advertised flags."""
    if not isinstance(options, StartOptions) or not isinstance(capabilities, ProviderCapabilities):
        raise E3ValidationError("validate_start_options expects typed arguments")
    errors: list[str] = []
    required = (
        (Capability.AGENT_OPTIONS, options.agent_options is not None, "agent_options"),
        (Capability.AGENT_PRESET, options.agent_preset is not None, "agent_preset"),
        (Capability.OUTPUT_SCHEMA, options.output_schema is not None, "output_schema"),
        (Capability.DEPTH_LIMIT, options.depth_limit is not None, "depth_limit"),
    )
    for capability, used, label in required:
        if used and not capabilities.supports(capability):
            errors.append(
                "provider %s does not support %s" % (capabilities.provider_id, label)
            )
    return tuple(errors)


class ProviderKind(str, Enum):
    """E3.1: the two activation targets share one API."""

    LOCAL = "local"
    EXTERNAL = "external"


class DeliveryPolicy(str, Enum):
    """E3.2: who receives the settled result."""

    PARENT = "parent"
    CALLER = "caller"


class SpawnMode(str, Enum):
    """E3.6: fresh child or completed-turn-prefix seed."""

    SPAWN = "spawn"
    FORK = "fork"


class AgentMode(str, Enum):
    """E3.12: durable descriptor mode; UNKNOWN for unavailable descriptors."""

    LOCAL = "local"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class MessageSource(str, Enum):
    """E3.9: never credit a child with words it did not choose."""

    AGENT_MESSAGE = "agent-message"
    SUBAGENT_SETTLED = "subagent-settled"


class ActivationStatus(str, Enum):
    """Lifecycle of a single activation (not of the durable child)."""

    LIVE = "live"
    INTERRUPT_REQUESTED = "interrupt-requested"
    SETTLED = "settled"
    CLOSED = "closed"


class BranchDiagnostic(str, Enum):
    """E3.12: per-branch catalog projection diagnostics."""

    NONE = "none"
    UNSUPPORTED = "unsupported"
    CORRUPT = "corrupt"
    UNAVAILABLE = "unavailable"


class LifecycleKind(str, Enum):
    """E3.15: event kinds on the tree event bus."""

    SUBAGENT_START = "subagent/start"
    SUBAGENT_END = "subagent/end"
    PROVIDER_ADDED = "provider/added"
    PROVIDER_REMOVED = "provider/removed"


def _parse_enum(enum_type: type[Enum], value: Any, label: str) -> Enum:
    try:
        return enum_type(value)
    except (ValueError, TypeError) as exc:
        raise E3ValidationError("unknown %s %r" % (label, value)) from exc


# ---------------------------------------------------------------------------
# E3.13 -- live model-route allowlist
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRoute:
    """A ``provider/model`` route a child may choose for a delegation."""

    provider: str
    model: str

    def __str__(self) -> str:
        return "%s/%s" % (self.provider, self.model)


def parse_model_route(value: Any) -> ModelRoute:
    """Parse and validate a ``provider/model`` route; fail closed otherwise."""
    if isinstance(value, ModelRoute):
        return value
    if not isinstance(value, str) or value.count("/") < 1:
        raise RouteError("model route must be 'provider/model'")
    parts = value.split("/")
    if any(not part or not _SAFE_ID_RE.match(part) for part in parts):
        raise RouteError("model route has an unsafe segment")
    return ModelRoute(_require_id(parts[0], "route provider"), "/".join(parts[1:]))


@dataclass
class ModelRouteAllowlist:
    """Default-off allowlist; reconfigured values are read on next delegation."""

    enabled: bool = False
    routes: frozenset[str] = frozenset()

    def configure(self, enabled: Any, routes: Iterable[Any] = ()) -> ModelRouteAllowlist:
        """Validate and atomically replace the live setting; duplicates error."""
        flag = _require_bool(enabled, "enabled")
        keys: list[str] = []
        for value in routes:
            key = str(parse_model_route(value))
            if key in keys:
                raise RouteError("duplicate model route %s" % key)
            keys.append(key)
        self.enabled = flag
        self.routes = frozenset(keys)
        return self


def check_route(allowlist: ModelRouteAllowlist, route: ModelRoute | None) -> None:
    """Enforce the live allowlist for one delegation (``None`` = provider default)."""
    if route is None:
        return
    if not isinstance(allowlist, ModelRouteAllowlist):
        raise E3ValidationError("route allowlist is missing")
    parsed = parse_model_route(route)
    if not allowlist.enabled:
        raise RouteNotAllowed("subagent model routes are disabled by default")
    if str(parsed) not in allowlist.routes:
        raise RouteNotAllowed("model route %s is not allowlisted" % parsed)


# ---------------------------------------------------------------------------
# E3.4 -- child working directory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChildWorkingDirectory:
    """Logged admission state: requested text, resolved path and project."""

    requested: str
    resolved: str
    project: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested", _require_text(self.requested, "cwd", allow_empty=True))
        object.__setattr__(self, "resolved", _require_text(self.resolved, "resolved cwd", allow_empty=True))
        object.__setattr__(self, "project", _require_text(self.project, "project", allow_empty=True))


def _normalize_path(value: str) -> str:
    path = posixpath.normpath((value or ".").replace("\\", "/"))
    return path or "."


def resolve_child_cwd(
    parent_cwd: ChildWorkingDirectory, requested: Any, project: Any
) -> ChildWorkingDirectory:
    """Resolve a relative child cwd against the parent's current directory."""
    if not isinstance(parent_cwd, ChildWorkingDirectory):
        raise E3ValidationError("parent_cwd must be a ChildWorkingDirectory")
    raw = _require_text(requested, "cwd", allow_empty=True) or "."
    project_text = "" if project is None else _require_text(project, "project", allow_empty=True)
    if _ABSOLUTE_PATH_RE.match(raw):
        resolved = _normalize_path(raw)
    else:
        resolved = _normalize_path(posixpath.join(_normalize_path(parent_cwd.resolved), raw))
    return ChildWorkingDirectory(raw, resolved, project_text)


# ---------------------------------------------------------------------------
# E3.6 -- spawn vs fork prefix
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnStep:
    """One completed/incomplete step with optional balanced group markers."""

    token: str
    complete: bool = True
    opens: str | None = None
    closes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "token", _require_text(self.token, "step token"))
        object.__setattr__(self, "complete", _require_bool(self.complete, "complete"))
        for label in ("opens", "closes"):
            value = getattr(self, label)
            if value is not None:
                object.__setattr__(self, label, _require_id(value, label))


@dataclass(frozen=True)
class ForkSeed:
    """The lossless, contiguous, balanced completed-turn prefix given to a fork."""

    tokens: tuple[str, ...] = ()
    source_agent_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "tokens", tuple(self.tokens))
        if self.source_agent_id:
            object.__setattr__(self, "source_agent_id", _require_id(self.source_agent_id, "source_agent_id"))


def compute_fork_prefix(steps: Iterable[TurnStep], *, source_agent_id: str = "") -> ForkSeed:
    """Derive the completed-turn prefix; reject gaps, loss and unbalanced groups."""
    tokens: list[str] = []
    open_groups: list[str] = []
    saw_incomplete = False
    for index, step in enumerate(steps):
        if not isinstance(step, TurnStep):
            raise ForkPrefixError("step %d is not a TurnStep" % index)
        if not step.complete:
            saw_incomplete = True
        elif saw_incomplete:
            raise ForkPrefixError("completed step after an incomplete step breaks contiguity")
        if step.closes is not None:
            if not open_groups or open_groups[-1] != step.closes:
                raise ForkPrefixError("step %d closes an unopened or mismatched group" % index)
            open_groups.pop()
        if step.opens is not None:
            if step.opens in open_groups:
                raise ForkPrefixError("step %d reopens an open group" % index)
            open_groups.append(step.opens)
        if step.complete:
            tokens.append(step.token)
    if open_groups:
        raise ForkPrefixError("completed-turn prefix has unclosed groups")
    return ForkSeed(tuple(tokens), _require_id(source_agent_id, "source_agent_id") if source_agent_id else "")


# ---------------------------------------------------------------------------
# E3.5 / E3.9 -- durable children, activations, inbox
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Attachment:
    """Opaque reference into a caller-owned attachment store (never a payload)."""

    attachment_id: str
    media_type: str
    store_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "attachment_id", _require_id(self.attachment_id, "attachment_id"))
        object.__setattr__(self, "media_type", _require_id(self.media_type, "media_type"))
        object.__setattr__(self, "store_ref", _require_id(self.store_ref, "store_ref"))


def _validate_attachment(value: Any) -> Attachment:
    if isinstance(value, Attachment):
        return value
    if not isinstance(value, Mapping):
        raise E3ValidationError("attachment must be an Attachment or mapping")
    return Attachment(
        value.get("attachment_id"), value.get("media_type"), value.get("store_ref")
    )


@dataclass(frozen=True)
class Message:
    """An accepted inbox item; ``accepted`` items are never retracted."""

    message_id: str
    source: MessageSource
    sender_id: str
    recipient_id: str
    text: str
    sequence: int
    attachments: tuple[Attachment, ...] = ()
    client_timezone: str | None = None
    accepted: bool = True
    claimed: bool = False
    attributed_to_child: bool = True
    settled_result: Result | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, MessageSource):
            raise E3ValidationError("message source must be a MessageSource")


@dataclass
class ChildNode:
    """Durable child identity; holds membership and logged cwd, no status."""

    agent_id: str
    parent_id: str | None
    name: str
    provider_id: str
    mode: AgentMode
    cwd: ChildWorkingDirectory
    project: str = ""
    child_ids: tuple[str, ...] = ()
    descriptor_available: bool = True
    descriptor_corrupt: bool = False
    created_sequence: int = 0


@dataclass
class Activation:
    """One execution of a durable child; at most one may be live per child."""

    activation_id: str
    agent_id: str
    provider_id: str
    kind: ProviderKind
    options: StartOptions
    delivery: DeliveryPolicy
    spawn_mode: SpawnMode
    cwd: ChildWorkingDirectory
    status: ActivationStatus
    sequence: int
    model_route: ModelRoute | None = None
    fork_seed: ForkSeed | None = None
    steered: list[str] = field(default_factory=list)
    input_closed: bool = False
    interrupt_requested: bool = False
    one_shot: bool = False
    inherits_parent_context_is_wording: bool = False
    settled_result: Result | None = None


@dataclass
class ProviderRecord:
    """Live provider state; removal keeps a historical record for the catalog."""

    capabilities: ProviderCapabilities
    online: bool = True
    removed: bool = False


@dataclass(frozen=True)
class LifecycleEvent:
    """E3.15 event; ``tree_root`` is None for provider-level events."""

    kind: LifecycleKind
    sequence: int
    tree_root: str | None = None
    agent_id: str | None = None
    provider_id: str | None = None


@dataclass(frozen=True)
class ActivationRequest:
    """The single E3.1 activation request for local children and external runs."""

    agent_id: str
    parent_id: str
    provider_id: str
    kind: ProviderKind
    options: StartOptions = field(default_factory=StartOptions)
    cwd_request: str = "."
    delivery: DeliveryPolicy = DeliveryPolicy.PARENT
    spawn_mode: SpawnMode = SpawnMode.SPAWN
    fork_seed: ForkSeed | None = None
    model_route: ModelRoute | None = None
    inherits_parent_context: bool = False
    initiated_by: str = USER_ACTOR

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _require_id(self.agent_id, "agent_id"))
        object.__setattr__(self, "parent_id", _require_id(self.parent_id, "parent_id"))
        object.__setattr__(self, "provider_id", _require_id(self.provider_id, "provider_id"))
        object.__setattr__(self, "kind", _parse_enum(ProviderKind, self.kind, "provider kind"))
        object.__setattr__(self, "delivery", _parse_enum(DeliveryPolicy, self.delivery, "delivery policy"))
        object.__setattr__(self, "spawn_mode", _parse_enum(SpawnMode, self.spawn_mode, "spawn mode"))
        object.__setattr__(self, "cwd_request", _require_text(self.cwd_request, "cwd", allow_empty=True))
        object.__setattr__(self, "initiated_by", _require_id(self.initiated_by, "initiated_by"))
        object.__setattr__(
            self, "inherits_parent_context", _require_bool(self.inherits_parent_context, "inherits_parent_context")
        )
        if not isinstance(self.options, StartOptions):
            raise E3ValidationError("options must be StartOptions")
        if self.fork_seed is not None and not isinstance(self.fork_seed, ForkSeed):
            raise E3ValidationError("fork_seed must be a ForkSeed")
        if self.model_route is not None:
            object.__setattr__(self, "model_route", parse_model_route(self.model_route))


@dataclass(frozen=True)
class DeliveryOutcome:
    """What :meth:`SubagentManager.settle` did with a settled result."""

    delivered_to_parent: bool
    returned_to_caller: bool
    message_id: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class Settlement:
    """Result, delivery decision and emitted event for one settled activation."""

    activation_id: str
    agent_id: str
    result: Result
    delivery: DeliveryOutcome


@dataclass(frozen=True)
class InterruptReceipt:
    """Fire-and-return result of :meth:`SubagentManager.interrupt`."""

    target_id: str
    actor_id: str
    found: bool
    authorized: bool
    requested: bool
    preserved_inbox: int
    preserved_descendants: int


@dataclass(frozen=True)
class DrainReport:
    """Outcome of a whole-tree drain; child-first ordering is explicit."""

    tree_root: str
    settled: tuple[str, ...]
    still_live: tuple[str, ...]
    parked_input_members: tuple[str, ...]
    disposal_order: tuple[str, ...]


@dataclass(frozen=True)
class TreeWorkStatus:
    """Idle members with parked input do not delay host completion."""

    tree_root: str
    live_activations: tuple[str, ...]
    parked_members: tuple[str, ...]
    host_can_complete: bool


@dataclass(frozen=True)
class CatalogEntry:
    """Parent-owned projection of one member (no execution status field)."""

    agent_id: str
    parent_id: str | None
    depth: int
    path: tuple[str, ...]
    mode: AgentMode
    diagnostic: BranchDiagnostic
    continuation_rights: bool


# ---------------------------------------------------------------------------
# The manager: one in-memory activation tree
# ---------------------------------------------------------------------------


class SubagentManager:
    """Own identities, capacity, activations, inbox, events and live settings."""

    def __init__(self, *, capacity: int = 8, tree_root_id: str = "lead") -> None:
        limit = _require_int(capacity, "capacity")
        if limit < 1:
            raise E3ValidationError("capacity must be at least 1")
        self.capacity = limit
        self.tree_root_id = _require_id(tree_root_id, "tree_root_id")
        self.nodes: dict[str, ChildNode] = {}
        self.activations: dict[str, Activation] = {}
        self.providers: dict[str, ProviderRecord] = {}
        self.messages: list[Message] = []
        self.events: list[LifecycleEvent] = []
        self.route_allowlist = ModelRouteAllowlist()
        self._sequence = 0
        root_cwd = ChildWorkingDirectory(".", ".", "")
        self.nodes[self.tree_root_id] = ChildNode(
            agent_id=self.tree_root_id,
            parent_id=None,
            name=ROOT_AGENT_NAME,
            provider_id=BUILTIN_LOCAL_PROVIDER,
            mode=AgentMode.LOCAL,
            cwd=root_cwd,
            project="",
            created_sequence=self._next(),
        )
        self.providers[BUILTIN_LOCAL_PROVIDER] = ProviderRecord(
            capabilities=ProviderCapabilities(
                BUILTIN_LOCAL_PROVIDER, E3_1_CAPABILITIES | {Capability.IMAGES}, accepts_images=True
            )
        )

    # -- internal helpers ---------------------------------------------------

    def _next(self) -> int:
        self._sequence += 1
        return self._sequence

    def _node(self, agent_id: str) -> ChildNode:
        node = self.nodes.get(_require_id(agent_id, "agent_id"))
        if node is None:
            raise NotFoundError("agent %s has no descriptor" % agent_id)
        return node

    def _activation(self, activation_id: str) -> Activation:
        act = self.activations.get(_require_id(activation_id, "activation_id"))
        if act is None:
            raise NotFoundError("activation %s does not exist" % activation_id)
        return act

    def _provider(self, provider_id: str) -> ProviderRecord:
        record = self.providers.get(_require_id(provider_id, "provider_id"))
        if record is None or record.removed or not record.online:
            raise NotFoundError("provider %s is unavailable" % provider_id)
        return record

    def _live_activation(self, agent_id: str) -> Activation | None:
        for act in self.activations.values():
            if act.agent_id == agent_id and act.status in (
                ActivationStatus.LIVE, ActivationStatus.INTERRUPT_REQUESTED
            ):
                return act
        return None

    def _live_count(self) -> int:
        return sum(
            1 for act in self.activations.values()
            if act.status in (ActivationStatus.LIVE, ActivationStatus.INTERRUPT_REQUESTED)
        )

    def _last_activation(self, agent_id: str) -> Activation | None:
        matches = [act for act in self.activations.values() if act.agent_id == agent_id]
        return max(matches, key=lambda a: a.sequence) if matches else None

    def _ancestors(self, agent_id: str) -> tuple[str, ...]:
        out: list[str] = []
        node = self.nodes.get(agent_id)
        seen = {agent_id}
        while node is not None and node.parent_id and node.parent_id not in seen:
            out.append(node.parent_id)
            seen.add(node.parent_id)
            node = self.nodes.get(node.parent_id)
        return tuple(out)

    def _tree_root_of(self, agent_id: str) -> str:
        ancestors = self._ancestors(agent_id)
        return ancestors[-1] if ancestors else agent_id

    def _descendants(self, root_id: str) -> tuple[str, ...]:
        out: list[str] = []
        visited = {root_id}

        def walk(parent_id: str) -> None:
            parent = self.nodes.get(parent_id)
            if parent is None:
                return
            for child_id in parent.child_ids:
                if child_id in visited:
                    continue
                visited.add(child_id)
                out.append(child_id)
                walk(child_id)

        walk(root_id)
        return tuple(out)

    def _members(self, root_id: str) -> tuple[str, ...]:
        return (root_id,) + self._descendants(root_id)

    def _parked(self, agent_id: str) -> tuple[Message, ...]:
        return tuple(
            m for m in self.messages
            if m.recipient_id == agent_id and m.accepted and not m.claimed
        )

    def _emit(self, kind: LifecycleKind, tree_root: str | None,
              agent_id: str | None = None, provider_id: str | None = None) -> LifecycleEvent:
        event = LifecycleEvent(kind, self._next(), tree_root, agent_id, provider_id)
        self.events.append(event)
        return event

    def _new_activation(
        self, *, agent_id: str, provider_id: str, kind: ProviderKind,
        options: StartOptions, delivery: DeliveryPolicy, spawn_mode: SpawnMode,
        cwd: ChildWorkingDirectory, model_route: ModelRoute | None,
        fork_seed: ForkSeed | None, wording_only: bool,
    ) -> Activation:
        act = Activation(
            activation_id="act-%d" % self._next(),
            agent_id=agent_id,
            provider_id=provider_id,
            kind=kind,
            options=options,
            delivery=delivery,
            spawn_mode=spawn_mode,
            cwd=cwd,
            status=ActivationStatus.LIVE,
            sequence=self._next(),
            model_route=model_route,
            fork_seed=fork_seed,
            one_shot=(kind is ProviderKind.EXTERNAL),
            inherits_parent_context_is_wording=wording_only,
        )
        self.activations[act.activation_id] = act
        self._emit(LifecycleKind.SUBAGENT_START, self._tree_root_of(agent_id), agent_id, provider_id)
        return act

    # -- E3.15 provider events ---------------------------------------------

    def register_provider(self, capabilities: ProviderCapabilities) -> ProviderRecord:
        """Add a provider and emit a global ``provider/added`` event."""
        if not isinstance(capabilities, ProviderCapabilities):
            raise E3ValidationError("capabilities must be ProviderCapabilities")
        record = ProviderRecord(capabilities)
        self.providers[record.capabilities.provider_id] = record
        self._emit(LifecycleKind.PROVIDER_ADDED, None, None, record.capabilities.provider_id)
        return record

    def unregister_provider(self, provider_id: str) -> None:
        """Mark a provider unavailable and emit ``provider/removed`` (E3.15)."""
        provider = self.providers.get(_require_id(provider_id, "provider_id"))
        if provider is None:
            raise NotFoundError("provider %s does not exist" % provider_id)
        provider.online = False
        provider.removed = True
        self._emit(LifecycleKind.PROVIDER_REMOVED, None, None, provider_id)

    def events_for_root(self, tree_root: str) -> tuple[LifecycleEvent, ...]:
        """Return subagent events scoped to ``tree_root`` (provider events excluded)."""
        _require_id(tree_root, "tree_root")
        return tuple(e for e in self.events if e.tree_root == tree_root)

    # -- E3.1 / E3.2 / E3.4 / E3.5 / E3.6 / E3.7 / E3.13 start -------------

    def start(self, request: ActivationRequest) -> str:
        """Validate *everything*, then start one activation and return its id."""
        if not isinstance(request, ActivationRequest):
            raise E3ValidationError("start expects an ActivationRequest")

        # E3.1: capability validation happens before any state mutation.
        provider = self._provider(request.provider_id)
        errors = validate_start_options(request.options, provider.capabilities)
        if errors:
            raise CapabilityNotSupported("start options are not supported", errors=errors)

        # E3.13: the live allowlist is read on every delegation.
        check_route(self.route_allowlist, request.model_route)

        # E3.7: external backends need the explicit capability.
        if request.kind is ProviderKind.EXTERNAL and not provider.capabilities.supports(
            Capability.EXTERNAL_EXECUTION
        ):
            raise CapabilityNotSupported("provider %s has no external_execution capability" % request.provider_id)

        if request.spawn_mode is SpawnMode.FORK:
            if request.fork_seed is None:
                raise ForkPrefixError("fork requires a fork_seed")
            if not isinstance(request.fork_seed, ForkSeed):
                raise ForkPrefixError("fork_seed must be a ForkSeed")

        # Parent must exist; a new child gets an identity only after validation.
        parent = self._node(request.parent_id)
        node = self.nodes.get(request.agent_id)
        if node is not None and self._live_activation(request.agent_id) is not None:
            raise AlreadyActive("agent %s already has a live activation" % request.agent_id)
        if self._live_count() >= self.capacity:
            raise DeliveryUnavailable("no capacity for a new activation")

        # E3.4: cwd chosen at admission; local children keep the parent's project.
        cwd = resolve_child_cwd(parent.cwd, request.cwd_request, parent.project)
        if node is None:
            name = ROOT_AGENT_NAME if request.agent_id == self.tree_root_id else make_agent_name(request.agent_id)
            node = ChildNode(
                agent_id=request.agent_id,
                parent_id=request.parent_id,
                name=name,
                provider_id=request.provider_id,
                mode=(AgentMode.EXTERNAL if request.kind is ProviderKind.EXTERNAL else AgentMode.LOCAL),
                cwd=cwd,
                project=parent.project,
                created_sequence=self._next(),
            )
            self.nodes[request.agent_id] = node
            parent.child_ids = parent.child_ids + (request.agent_id,)
        else:
            node.cwd = cwd

        act = self._new_activation(
            agent_id=request.agent_id,
            provider_id=request.provider_id,
            kind=request.kind,
            options=request.options,
            delivery=request.delivery,
            spawn_mode=request.spawn_mode,
            cwd=cwd,
            model_route=request.model_route,
            fork_seed=request.fork_seed,
            wording_only=request.inherits_parent_context,
        )
        return act.activation_id

    def _cold_resume(self, agent_id: str, *, initiated_by: str = USER_ACTOR) -> Activation:
        """Resume an absent durable child; reuses logged cwd, never the old schema."""
        node = self._node(agent_id)
        if self._live_activation(agent_id) is not None:
            raise AlreadyActive("agent %s already has a live activation" % agent_id)
        if self._live_count() >= self.capacity:
            raise DeliveryUnavailable("cold resume at capacity", code=ERR_AT_CAPACITY)
        previous = self._last_activation(agent_id)
        if previous is not None and previous.one_shot:
            raise NoFollowUp("external execution %s has no follow-ups" % previous.activation_id)
        if node.mode is AgentMode.EXTERNAL:
            provider = self._provider(node.provider_id)
            if not provider.capabilities.supports(Capability.EXTERNAL_EXECUTION):
                raise CapabilityNotSupported("external execution is no longer supported")
        return self._new_activation(
            agent_id=agent_id,
            provider_id=node.provider_id,
            kind=(ProviderKind.EXTERNAL if node.mode is AgentMode.EXTERNAL else ProviderKind.LOCAL),
            options=StartOptions(),  # resume never inherits a structured-output schema
            delivery=DeliveryPolicy.PARENT,
            spawn_mode=SpawnMode.SPAWN,
            cwd=node.cwd,  # logged admission state is retained
            model_route=None,
            fork_seed=None,
            wording_only=False,
        )

    # -- E3.2 / E3.9 / E3.14 messaging -------------------------------------

    def send_message(
        self,
        sender_id: str,
        recipient_id: str,
        text: Any,
        *,
        attachments: Iterable[Any] = (),
        client_timezone: Any = None,
        message_id: Any = None,
    ) -> Message:
        """Steer a running target or cold-resume an absent one (E3.9/E3.14)."""
        # Sender identity is rechecked on every send.
        self._node(sender_id)
        self._node(recipient_id)
        clean_text = _require_text(text, "text")
        atts = tuple(_validate_attachment(a) for a in attachments)
        tz = None if client_timezone is None else _require_id(client_timezone, "client_timezone")

        live = self._live_activation(recipient_id)
        provider_id = live.provider_id if live is not None else self._node(recipient_id).provider_id
        image_parts = [a for a in atts if a.media_type.startswith("image/")]
        if image_parts:
            provider = self._provider(provider_id)
            if not provider.capabilities.supports(Capability.IMAGES) or not provider.capabilities.accepts_images:
                raise ImageNotAccepted("provider %s does not accept images" % provider_id)
        if live is not None and live.input_closed:
            raise InputClosed("activation %s input is closed for structured-output capture" % live.activation_id)

        mid = _require_id(message_id, "message_id") if message_id is not None else "msg-%d" % self._next()
        if any(m.message_id == mid for m in self.messages):
            raise E3ValidationError("duplicate message_id %s" % mid)
        # Cold resume happens before acceptance: a capacity rejection leaves no
        # accepted-but-undelivered message to retract.
        if live is None:
            self._cold_resume(recipient_id)
        msg = Message(
            message_id=mid,
            source=MessageSource.AGENT_MESSAGE,
            sender_id=sender_id,
            recipient_id=recipient_id,
            text=clean_text,
            sequence=self._next(),
            attachments=atts,
            client_timezone=tz,
            accepted=True,
            claimed=(live is not None),
            attributed_to_child=True,
        )
        self.messages.append(msg)
        if live is not None:
            live.steered.append(mid)
        return msg

    def _settled_notice(self, act: Activation, result: Result) -> Message:
        """Runtime notice about *how* a child ended (never its own words)."""
        text = "subagent %s ended (%s)" % (act.agent_id, result.stop_reason.value)
        msg = Message(
            message_id="notice-%d" % self._next(),
            source=MessageSource.SUBAGENT_SETTLED,
            sender_id=act.agent_id,
            recipient_id=self._node(act.agent_id).parent_id or self.tree_root_id,
            text=text,
            sequence=self._next(),
            accepted=True,
            claimed=False,
            attributed_to_child=False,
            settled_result=result,
        )
        self.messages.append(msg)
        return msg

    def settle(
        self,
        activation_id: str,
        *,
        final_text: Any = "",
        structured: Any = None,
        diagnostics: Any = "",
        stop_reason: Any = StopReason.COMPLETED,
        error: Any = None,
    ) -> Settlement:
        """Build a sanitized result (E3.8), close input where required, deliver (E3.2)."""
        act = self._activation(activation_id)
        if act.status in (ActivationStatus.SETTLED, ActivationStatus.CLOSED):
            raise AlreadySettled("activation %s is already settled" % activation_id)
        reason = parse_stop_reason(stop_reason)
        if error is not None or reason is StopReason.ERROR:
            result = child_failure_to_result(error)
        else:
            try:
                result = build_result(
                    final_output=final_text,
                    structured=structured,
                    schema=act.options.output_schema,
                    diagnostics=diagnostics,
                    stop_reason=reason,
                )
            except ContractValidationError as exc:
                # Re-type the P0 result-contract failure at this host boundary.
                raise E3ValidationError("invalid settled result", errors=exc.errors) from exc
        act.status = ActivationStatus.SETTLED
        act.settled_result = result
        if act.options.output_schema is not None:
            act.input_closed = True
        self._emit(LifecycleKind.SUBAGENT_END, self._tree_root_of(act.agent_id), act.agent_id, act.provider_id)

        provider = self.providers.get(act.provider_id)
        online = provider is not None and provider.online and not provider.removed
        if act.delivery is DeliveryPolicy.CALLER:
            delivery = DeliveryOutcome(False, True, None, "caller-policy")
        elif act.kind is ProviderKind.EXTERNAL and not online:
            # E3.7: results reach the creator only while it is online.
            delivery = DeliveryOutcome(False, False, None, "creator-offline")
        elif self._node(act.agent_id).parent_id is None:
            delivery = DeliveryOutcome(False, True, None, "root-has-no-parent")
        else:
            notice = self._settled_notice(act, result)
            delivery = DeliveryOutcome(True, False, notice.message_id, "parent-notified")
        return Settlement(act.activation_id, act.agent_id, result, delivery)

    # -- E3.10 interrupt ----------------------------------------------------

    def interrupt(self, target_id: str, actor_id: str) -> InterruptReceipt:
        """Fire-and-return interrupt by ``user`` or an exact live ancestor."""
        target = _require_id(target_id, "target_id")
        actor = _require_id(actor_id, "actor_id")
        if target not in self.nodes:
            return InterruptReceipt(target, actor, False, False, False, 0, 0)
        ancestors = self._ancestors(target)
        authorized = actor == USER_ACTOR or actor in ancestors
        if not authorized:
            raise InterruptDeniedError("%s is not an ancestor of %s" % (actor, target))
        if actor != USER_ACTOR and self._live_activation(actor) is None:
            raise InterruptDeniedError("ancestor %s is not live" % actor)
        act = self._live_activation(target)
        # Report the whole preserved inbox: steered (claimed) plus parked
        # (unclaimed) items.  Neither is cleared or requeued by an interrupt.
        inbox = (len(act.steered) if act is not None else 0) + len(self._parked(target))
        descendants = len(self._descendants(target))
        requested = act is not None
        if requested and act.status is ActivationStatus.LIVE:
            act.status = ActivationStatus.INTERRUPT_REQUESTED
            act.interrupt_requested = True
        return InterruptReceipt(target, actor, True, True, requested, inbox, descendants)

    # -- E3.11 whole-tree drain / wait -------------------------------------

    def drain_tree(self, root_id: str) -> DrainReport:
        """Settle live work child-first; leave parked-input members resident."""
        self._node(root_id)
        descendants = self._descendants(root_id)
        child_first = tuple(reversed(descendants)) + (root_id,)
        settled: list[str] = []
        for agent_id in child_first:
            act = self._live_activation(agent_id)
            if act is not None:
                self.settle(act.activation_id, final_text="", stop_reason=StopReason.ABORTED)
                settled.append(act.activation_id)
        parked = tuple(mid for mid in self._members(root_id) if self._parked(mid))
        return DrainReport(root_id, tuple(settled), (), parked, child_first)

    def wait_for_tree_work(self, root_id: str) -> TreeWorkStatus:
        """Report live work; parked input must not delay host completion."""
        self._node(root_id)
        members = self._members(root_id)
        live = tuple(
            act.activation_id for mid in members
            if (act := self._live_activation(mid)) is not None
        )
        parked = tuple(mid for mid in members if self._parked(mid))
        return TreeWorkStatus(root_id, live, parked, not live)

    def dispose_tree(self, root_id: str) -> tuple[str, ...]:
        """Explicit child-first teardown; returns the disposal order."""
        self._node(root_id)
        child_first = tuple(reversed(self._descendants(root_id))) + (root_id,)
        for agent_id in child_first:
            act = self._live_activation(agent_id)
            if act is not None:
                self.settle(act.activation_id, final_text="", stop_reason=StopReason.ABORTED)
        for agent_id in child_first:
            self.nodes.pop(agent_id, None)
        return child_first

    # -- E3.12 catalog projection ------------------------------------------

    def list_descendants(self, root_id: str) -> tuple[CatalogEntry, ...]:
        """Project parent-owned membership with per-branch diagnostics."""
        root = self._node(root_id)
        entries: list[CatalogEntry] = []
        visited = {root_id}

        def walk(parent_id: str, depth: int, path: tuple[str, ...]) -> None:
            parent = self.nodes.get(parent_id)
            if parent is None:
                return
            for child_id in parent.child_ids:
                if child_id in visited:
                    continue
                visited.add(child_id)
                child = self.nodes.get(child_id)
                child_path = path + ((child.name if child is not None else child_id),)
                if child is None:
                    entries.append(CatalogEntry(
                        child_id, parent_id, depth + 1, child_path,
                        AgentMode.UNKNOWN, BranchDiagnostic.UNAVAILABLE, False,
                    ))
                    continue
                if child.descriptor_corrupt:
                    entries.append(CatalogEntry(
                        child_id, parent_id, depth + 1, child_path,
                        AgentMode.UNKNOWN, BranchDiagnostic.CORRUPT, False,
                    ))
                    continue
                if not child.descriptor_available:
                    entries.append(CatalogEntry(
                        child_id, parent_id, depth + 1, child_path,
                        AgentMode.UNKNOWN, BranchDiagnostic.UNAVAILABLE, False,
                    ))
                    continue
                provider = self.providers.get(child.provider_id)
                if provider is None or provider.removed or not provider.online:
                    entries.append(CatalogEntry(
                        child_id, parent_id, depth + 1, child_path,
                        AgentMode.UNKNOWN, BranchDiagnostic.UNAVAILABLE, False,
                    ))
                    continue
                if child.mode is AgentMode.EXTERNAL and not provider.capabilities.supports(
                    Capability.EXTERNAL_EXECUTION
                ):
                    entries.append(CatalogEntry(
                        child_id, parent_id, depth + 1, child_path,
                        AgentMode.UNKNOWN, BranchDiagnostic.UNSUPPORTED, False,
                    ))
                    continue
                entries.append(CatalogEntry(
                    child_id, parent_id, depth + 1, child_path,
                    child.mode, BranchDiagnostic.NONE, True,
                ))
                walk(child_id, depth + 1, child_path)

        walk(root_id, 0, (root.name,))
        return tuple(entries)


# ---------------------------------------------------------------------------
# Live setting + P0 verification helpers
# ---------------------------------------------------------------------------


def set_route_allowlist(
    manager: SubagentManager, enabled: bool, routes: Iterable[Any] = ()
) -> ModelRouteAllowlist:
    """Reconfigure the live route allowlist read by every subsequent start."""
    if not isinstance(manager, SubagentManager):
        raise E3ValidationError("set_route_allowlist expects a SubagentManager")
    return manager.route_allowlist.configure(enabled, routes)


def verify_p0_contracts() -> dict[str, bool]:
    """Execute the E3.3/E3.8 P0 surfaces and report ``{feature_id: ok}``.

    This is the executable cross-check for the two rows already implemented in
    :mod:`keel.result_contracts`; any regression raises :class:`E3Error`.
    """
    name_ok = (
        validate_agent_name("researcher") == ()
        and bool(validate_agent_name(ROOT_AGENT_NAME))
        and bool(validate_agent_name("Bad_Name"))
        and make_agent_name("writer-2") == "writer-2"
    )
    sanitized = build_result(final_output="x", diagnostics="sk-abcdefghijklmnopqrstuvwxyz")
    result_ok = (
        build_result(final_output="done").final_output == "done"
        and child_failure_to_result("boom").stop_reason is StopReason.ERROR
        and "sk-abcdefghijklmnopqrstuvwxyz" not in sanitized.diagnostics
    )
    report = {"E3.3": name_ok, "E3.8": result_ok}
    if not all(report.values()):
        raise E3ValidationError("P0 contract verification failed", errors=[
            "%s=%r" % item for item in report.items()
        ])
    return report


__all__ = [
    "FEATURE_IDS", "P0_VERIFIED_IDS", "USER_ACTOR", "E3_1_CAPABILITIES",
    "ERR_AT_CAPACITY", "ERR_CAPABILITY", "ERR_IMAGE_NOT_ACCEPTED",
    "ERR_INPUT_CLOSED", "ERR_INTERRUPT_DENIED", "ERR_INVALID_ROUTE",
    "ERR_NO_FOLLOW_UP", "ERR_NOT_FOUND", "ERR_ROUTE_NOT_ALLOWED",
    "E3Error", "E3ValidationError", "CapabilityNotSupported", "DeliveryUnavailable",
    "AlreadyActive", "AlreadySettled", "NoFollowUp", "InterruptDeniedError",
    "RouteError", "RouteNotAllowed", "ForkPrefixError", "ImageNotAccepted",
    "InputClosed", "NotFoundError",
    "Capability", "ProviderKind", "DeliveryPolicy", "SpawnMode", "AgentMode",
    "MessageSource", "ActivationStatus", "BranchDiagnostic", "LifecycleKind",
    "ProviderCapabilities", "StartOptions", "validate_start_options",
    "ModelRoute", "parse_model_route", "ModelRouteAllowlist", "check_route",
    "ChildWorkingDirectory", "resolve_child_cwd",
    "TurnStep", "ForkSeed", "compute_fork_prefix",
    "Attachment", "Message", "ChildNode", "Activation", "ProviderRecord",
    "LifecycleEvent", "ActivationRequest", "DeliveryOutcome", "Settlement",
    "InterruptReceipt", "DrainReport", "TreeWorkStatus", "CatalogEntry",
    "SubagentManager", "set_route_allowlist", "verify_p0_contracts",
]
