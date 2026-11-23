"""keel.plugin_contracts -- D1.x plugin architecture contracts (P0).

This is an *additive*, stdlib-only module.  It materializes the D1.x registry
rows as typed configuration/data:

  D1.1  every part is a plugin (model adapter, tool registry, session log,
        approval broker, agent loop, ...) registered through one API; the
        permission/safety core is a plugin too but is marked protected ....... PluginPart, PartKind, PluginRegistry, core_parts
  D1.4  deterministic layered composition: bundles -> profile -> home ->
        project -> --patch overlays; protected core cannot be overridden .... Layer, ConfigRow, Patch, compose
  D1.5  --dump-config equivalent: the exact boot tree with provenance on every
        row and no secret values ............................................. dump_config, dump_config_rows, redact_config
  D1.10 desktop shell descriptor (signed production runtime in resources,
        the shell owns the UI); descriptor only, no packaging ................ DesktopShellDescriptor, assert_descriptor_complete
  D1.12 core package map: six context service keys with responsibilities .... CoreService, CORE_PACKAGE_MAP, assert_core_map_complete

No plugin is ever imported, instantiated or executed here: ``implementation``
fields are inert ``module:qualname`` strings.  There is no I/O, no subprocess,
no network and no import-time side effect.  Integration seams are documented
in ``master-plan-v6-plugin-contracts-evidence.md``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, fields, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# shared helpers: deterministic bytes, hashes, typed errors, enum values
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    """Stable UTF-8 encoding used by every fingerprint in this module."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _val(value: Any) -> str:
    """Enum-safe string value."""
    return value.value if isinstance(value, Enum) else str(value)


def _copy_config(value: Mapping[str, Any] | None) -> dict:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise PluginContractError("config must be a mapping")
    return {str(k): _deep_copy(v) for k, v in value.items()}


def _deep_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _deep_copy(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_deep_copy(v) for v in value]
    return value


class PluginContractError(ValueError):
    """Base class for every typed plugin-contract failure."""


class PartDescriptorError(PluginContractError):
    """A part descriptor is malformed."""


class ProtectedCoreOverride(PluginContractError):
    """A later layer tried to replace or disable protected safety core."""


class CompositionError(PluginContractError):
    """The layer composition is invalid (bad order, bad patch, duplicate id)."""


class PatchError(CompositionError):
    """A patch targets a missing row or uses an invalid list operation."""


class DescriptorError(PluginContractError):
    """A D1.10 descriptor is incomplete or internally inconsistent."""


class SecretLeakError(PluginContractError):
    """A rendered config contains a secret value."""


# ---------------------------------------------------------------------------
# D1.1 -- every part is a plugin, with a typed part descriptor
# ---------------------------------------------------------------------------


class PartKind(str, Enum):
    """The kinds of part that register through the single plugin API."""

    MODEL_ADAPTER = "model_adapter"
    TOOL_REGISTRY = "tool_registry"
    SESSION_LOG = "session_log"
    APPROVAL_BROKER = "approval_broker"
    AGENT_LOOP = "agent_loop"
    SYSTEM_PROMPT = "system_prompt"
    AGENT_REGISTRY = "agent_registry"
    LLM_VOCABULARY = "llm_vocabulary"
    MEMORY_BACKEND = "memory_backend"
    SCHEDULER = "scheduler"
    PERMISSION_CORE = "permission_core"
    SAFETY_CORE = "safety_core"


class ServiceTier(str, Enum):
    """Tier 2 safety services are plugins that cannot be replaced or disabled."""

    CORE = "core"
    TIER_2_SAFETY = "tier2_safety"
    EXTENSION = "extension"


_IMPLEMENTATION_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_.]*(?::[A-Za-z_][A-Za-z0-9_.]*)?$")


@dataclass(frozen=True)
class PluginPart:
    """An inert descriptor for one replaceable (or protected) part.

    ``implementation`` is a string only: this module never imports it.  The
    same descriptor type is used for core services and third-party plugins,
    which is what makes "no privileged core to patch" true at the contract
    level.
    """

    id: str
    kind: PartKind
    implementation: str
    tier: ServiceTier = ServiceTier.CORE
    replaceable: bool = True
    protected: bool = False
    config: dict = field(default_factory=dict)
    responsibility: str = ""
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise PartDescriptorError("part id must be non-empty")
        try:
            object.__setattr__(self, "kind", PartKind(self.kind))
            object.__setattr__(self, "tier", ServiceTier(self.tier))
        except ValueError:
            raise PartDescriptorError(
                f"unknown part kind/tier for {self.id!r}") from None
        if not isinstance(self.implementation, str) or not \
                _IMPLEMENTATION_RE.fullmatch(self.implementation):
            raise PartDescriptorError(
                f"implementation must be a module:qualname string: {self.implementation!r}")
        if self.protected and self.replaceable:
            raise PartDescriptorError(
                f"protected part {self.id!r} cannot be marked replaceable")
        if self.tier is ServiceTier.TIER_2_SAFETY and not self.protected:
            raise PartDescriptorError(
                f"tier-2 safety part {self.id!r} must be protected")
        object.__setattr__(self, "config", _copy_config(self.config))
        object.__setattr__(self, "dependencies",
                           tuple(str(d) for d in self.dependencies))

    @property
    def service_key(self) -> str:
        return self.id

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind.value,
            "implementation": self.implementation, "tier": self.tier.value,
            "replaceable": self.replaceable, "protected": self.protected,
            "config": _deep_copy(self.config),
            "responsibility": self.responsibility,
            "dependencies": list(self.dependencies),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PluginPart":
        d = dict(data)
        return cls(
            id=str(d.get("id") or ""),
            kind=PartKind(d.get("kind", PartKind.MODEL_ADAPTER.value)),
            implementation=str(d.get("implementation") or "unknown:unknown"),
            tier=ServiceTier(d.get("tier", ServiceTier.CORE.value)),
            replaceable=bool(d.get("replaceable", True)),
            protected=bool(d.get("protected", False)),
            config=dict(d.get("config") or {}),
            responsibility=str(d.get("responsibility") or ""),
            dependencies=tuple(d.get("dependencies") or ()),
        )


def _part(part_id: str, kind: PartKind, implementation: str,
          responsibility: str, **kwargs: Any) -> PluginPart:
    return PluginPart(id=part_id, kind=kind, implementation=implementation,
                      responsibility=responsibility, **kwargs)


def core_parts() -> tuple[PluginPart, ...]:
    """The canonical part set.  Every core service registers as a plugin."""
    return (
        _part("llm", PartKind.MODEL_ADAPTER, "keel.providers:ModelAdapter",
              "LLM vocabulary and adapter seam",
              dependencies=()),
        _part("tools", PartKind.TOOL_REGISTRY, "keel.tool_registry:ToolRegistry",
              "Tool registry plus guarded execution pipeline",
              dependencies=("llm",)),
        _part("sessions", PartKind.SESSION_LOG,
              "keel.transcript_contracts:TranscriptStore",
              "Append-only typed session log with replay",
              dependencies=()),
        _part("approval_broker", PartKind.APPROVAL_BROKER,
              "keel.approvals:ApprovalBroker",
              "Human approval broker for guarded tool execution",
              tier=ServiceTier.TIER_2_SAFETY, protected=True, replaceable=False,
              dependencies=("sessions",)),
        _part("agent_loop", PartKind.AGENT_LOOP, "keel.loop:AgentLoop",
              "Agent loop driver / turn orchestration",
              dependencies=("llm", "tools", "sessions")),
        _part("system_prompt", PartKind.SYSTEM_PROMPT,
              "keel.prompts:SystemPromptAssembler",
              "Deterministic system-prompt assembly from ordered sections",
              dependencies=()),
        _part("agents", PartKind.AGENT_REGISTRY, "keel.agent_contracts:AgentRegistry",
              "Agent interface and live registry",
              dependencies=("system_prompt",)),
        _part("permission_core", PartKind.PERMISSION_CORE,
              "keel.permissions:PermissionCore",
              "Non-replaceable permission decision core",
              tier=ServiceTier.TIER_2_SAFETY, protected=True, replaceable=False),
        _part("safety_core", PartKind.SAFETY_CORE, "keel.safety:SafetyCore",
              "Non-replaceable safety guard and injection defenses",
              tier=ServiceTier.TIER_2_SAFETY, protected=True, replaceable=False,
              dependencies=("permission_core",)),
    )


CORE_PART_IDS: tuple[str, ...] = tuple(p.id for p in core_parts())
PROTECTED_CORE_IDS: tuple[str, ...] = tuple(
    p.id for p in core_parts() if p.protected)


class PluginRegistry:
    """The one registration API used by core parts and extensions alike."""

    def __init__(self, parts: Iterable[PluginPart] = ()) -> None:
        self._parts: dict[str, PluginPart] = {}
        for part in parts:
            self.register(part)

    def register(self, part: PluginPart) -> PluginPart:
        if not isinstance(part, PluginPart):
            raise PartDescriptorError("register() expects a PluginPart")
        if part.id in self._parts:
            raise PartDescriptorError(f"duplicate part id: {part.id!r}")
        self._parts[part.id] = part
        return part

    def part(self, part_id: str) -> PluginPart:
        try:
            return self._parts[str(part_id)]
        except KeyError:
            raise PartDescriptorError(f"unknown part id: {part_id!r}") from None

    @property
    def parts(self) -> tuple[PluginPart, ...]:
        return tuple(self._parts.values())

    def ids(self) -> tuple[str, ...]:
        return tuple(self._parts)

    def is_protected(self, part_id: str) -> bool:
        return part_id in self._parts and self._parts[part_id].protected

    def assert_replaceable(self, part_id: str) -> PluginPart:
        part = self.part(part_id)
        if part.protected:
            raise ProtectedCoreOverride(
                f"protected part {part_id!r} cannot be replaced or disabled")
        return part

    def to_dict(self) -> dict:
        return {"parts": [p.to_dict() for p in self.parts],
                "protected_ids": [p.id for p in self.parts if p.protected]}


def default_registry() -> PluginRegistry:
    """Register every core part through the same API an extension uses."""
    return PluginRegistry(core_parts())


# ---------------------------------------------------------------------------
# D1.4 -- deterministic layered composition
# ---------------------------------------------------------------------------


class Layer(str, Enum):
    BUNDLE = "bundle"
    PROFILE = "profile"
    HOME = "home"
    PROJECT = "project"
    PATCH = "patch"


LAYER_ORDER: tuple[Layer, ...] = (
    Layer.BUNDLE, Layer.PROFILE, Layer.HOME, Layer.PROJECT, Layer.PATCH)


class RowKind(str, Enum):
    PART = "part"
    PRESET = "preset"
    VALUE = "value"


@dataclass(frozen=True)
class ConfigRow:
    """One stable-id row of the composed configuration."""

    id: str
    layer: Layer = Layer.BUNDLE
    source: str = ""
    kind: RowKind = RowKind.PART
    plugin_id: str = ""
    config: dict = field(default_factory=dict)
    enabled: bool = True
    protected: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise CompositionError("every config row needs a stable id")
        try:
            object.__setattr__(self, "layer", Layer(self.layer))
            object.__setattr__(self, "kind", RowKind(self.kind))
        except ValueError:
            raise CompositionError(f"unknown layer/kind for row {self.id!r}") from None
        if not isinstance(self.source, str) or not self.source:
            raise CompositionError(f"row {self.id!r} needs a non-empty source")
        object.__setattr__(self, "config", _copy_config(self.config))
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "protected", bool(self.protected))

    @property
    def provenance(self) -> dict:
        return {"layer": self.layer.value, "source": self.source}

    def semantic_fields(self) -> dict:
        """Fields a later layer is allowed to change (identity excluded)."""
        return {"kind": self.kind.value, "plugin_id": self.plugin_id,
                "config": _deep_copy(self.config), "enabled": self.enabled}

    def to_dict(self) -> dict:
        return {"id": self.id, "layer": self.layer.value, "source": self.source,
                "kind": self.kind.value, "plugin_id": self.plugin_id,
                "config": _deep_copy(self.config), "enabled": self.enabled,
                "protected": self.protected}


def row(part_id: str, *, config: Mapping[str, Any] | None = None,
        source: str = "core-bundle", layer: Layer = Layer.BUNDLE,
        kind: RowKind = RowKind.PART, plugin_id: str = "",
        enabled: bool = True, protected: bool = False) -> ConfigRow:
    """Convenience constructor for a ConfigRow in tests and bundle tables."""
    return ConfigRow(id=part_id, layer=layer, source=source, kind=kind,
                     plugin_id=plugin_id or part_id, config=dict(config or {}),
                     enabled=enabled, protected=protected)


@dataclass(frozen=True)
class Bundle:
    """A distributable set of config rows, applied in list order."""

    name: str
    rows: tuple[ConfigRow, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise CompositionError("bundle needs a name")
        object.__setattr__(self, "rows", tuple(self.rows))
        for item in self.rows:
            if not isinstance(item, ConfigRow):
                raise CompositionError("bundle rows must be ConfigRow objects")

    def to_dict(self) -> dict:
        return {"name": self.name, "rows": [r.to_dict() for r in self.rows]}


class PatchAction(str, Enum):
    REPLACE = "replace"   # replace the whole config of a targeted row by id
    INSERT = "insert"     # insert a new row with a stable id
    PRESET = "preset"     # edit inside a declaration's plugin list
    DISABLE = "disable"   # flip enabled=False on an existing row


class PluginListOp(str, Enum):
    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"


@dataclass(frozen=True)
class Patch:
    """One patch operation.  ``source`` is the provenance of the patch file."""

    action: PatchAction
    target_id: str
    source: str = ""
    config: Mapping[str, Any] | None = None
    kind: RowKind | None = None
    plugin_id: str | None = None
    enabled: bool | None = None
    plugin_list_op: PluginListOp = PluginListOp.ADD
    plugin_list: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "action", PatchAction(self.action))
            object.__setattr__(self, "plugin_list_op",
                               PluginListOp(self.plugin_list_op))
        except ValueError:
            raise PatchError(f"unknown patch action/op: {self.action!r}") from None
        if not isinstance(self.target_id, str) or not self.target_id:
            raise PatchError("patch needs a target row id")
        if not isinstance(self.source, str) or not self.source:
            raise PatchError("patch needs a non-empty source")
        if self.kind is not None:
            object.__setattr__(self, "kind", RowKind(self.kind))
        object.__setattr__(self, "config", _copy_config(self.config))
        object.__setattr__(self, "plugin_list",
                           tuple(str(p) for p in self.plugin_list))

    def to_dict(self) -> dict:
        return {"action": self.action.value, "target_id": self.target_id,
                "source": self.source, "config": _deep_copy(self.config or {}),
                "kind": self.kind.value if self.kind else None,
                "plugin_id": self.plugin_id, "enabled": self.enabled,
                "plugin_list_op": self.plugin_list_op.value,
                "plugin_list": list(self.plugin_list)}


@dataclass(frozen=True)
class PatchDocument:
    """A profile/home/project/--patch document: an ordered set of patches."""

    layer: Layer
    source: str
    patches: tuple[Patch, ...] = ()

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "layer", Layer(self.layer))
        except ValueError:
            raise CompositionError(f"unknown layer: {self.layer!r}") from None
        if self.layer is Layer.BUNDLE:
            raise CompositionError("a PatchDocument cannot be a bundle layer")
        if not isinstance(self.source, str) or not self.source:
            raise CompositionError("patch document needs a non-empty source")
        object.__setattr__(self, "patches", tuple(self.patches))
        for patch in self.patches:
            if not isinstance(patch, Patch):
                raise PatchError("patch document entries must be Patch objects")

    def to_dict(self) -> dict:
        return {"layer": self.layer.value, "source": self.source,
                "patches": [p.to_dict() for p in self.patches]}


@dataclass(frozen=True)
class Composition:
    """The deterministic result of applying every layer in canonical order."""

    rows: tuple[ConfigRow, ...]
    applied_layers: tuple[str, ...] = ()
    protected_ids: tuple[str, ...] = PROTECTED_CORE_IDS

    @property
    def layer_order(self) -> tuple[str, ...]:
        return tuple(Layer(x.split(":", 1)[0]).value for x in self.applied_layers)

    @property
    def fingerprint(self) -> str:
        return content_hash([r.to_dict() for r in self.rows])

    def row(self, row_id: str) -> ConfigRow:
        for item in self.rows:
            if item.id == row_id:
                return item
        raise CompositionError(f"no composed row with id {row_id!r}")

    def ids(self) -> tuple[str, ...]:
        return tuple(r.id for r in self.rows)

    def to_dict(self) -> dict:
        return {"rows": [r.to_dict() for r in self.rows],
                "applied_layers": list(self.applied_layers),
                "layer_order": list(self.layer_order),
                "protected_ids": list(self.protected_ids),
                "fingerprint": self.fingerprint}


def ordered_layer_docs(
    bundles: Sequence[Bundle] = (), *,
    profile: PatchDocument | None = None,
    home: PatchDocument | None = None,
    project: PatchDocument | None = None,
    overlays: Sequence[PatchDocument] = (),
) -> tuple[tuple[Layer, str, Any], ...]:
    """Return (layer, source, payload) in the one canonical composition order.

    Bundles keep their list order; then profile, home, project and finally
    every ``--patch`` overlay in the order supplied.  Callers can pass the
    documents in any argument order -- the returned sequence is canonical.
    """
    out: list[tuple[Layer, str, Any]] = []
    for bundle in bundles:
        if not isinstance(bundle, Bundle):
            raise CompositionError("bundles must be Bundle objects")
        out.append((Layer.BUNDLE, bundle.name, bundle.rows))
    for doc in [profile, home, project, *overlays]:
        if doc is None:
            continue
        if not isinstance(doc, PatchDocument):
            raise CompositionError("layer documents must be PatchDocument objects")
        expected = Layer.BUNDLE if doc.layer is Layer.BUNDLE else doc.layer
        out.append((expected, doc.source, doc.patches))
    return tuple(out)


def _merge_row(rows: dict[str, ConfigRow], incoming: ConfigRow,
               protected_ids: frozenset[str]) -> None:
    current = rows.get(incoming.id)
    if current is None:
        if incoming.id in protected_ids and incoming.layer is not Layer.BUNDLE:
            raise ProtectedCoreOverride(
                f"protected core id {incoming.id!r} cannot be introduced by "
                f"layer {_val(incoming.layer)} ({incoming.source})")
        rows[incoming.id] = incoming
        return
    if current.protected or incoming.id in protected_ids:
        # A later layer may restate a protected row byte-for-byte; it may not
        # change its config, plugin, kind or enablement.  First provenance wins.
        if current.semantic_fields() == incoming.semantic_fields():
            return
        raise ProtectedCoreOverride(
            f"protected core row {incoming.id!r} cannot be overridden by "
            f"layer {_val(incoming.layer)} ({incoming.source})")
    merged = replace(current,
                     kind=incoming.kind,
                     plugin_id=incoming.plugin_id,
                     config=_copy_config(incoming.config),
                     enabled=incoming.enabled,
                     layer=incoming.layer,
                     source=incoming.source,
                     protected=incoming.protected)
    rows[incoming.id] = merged


def _apply_patch(rows: dict[str, ConfigRow], patch: Patch, doc: PatchDocument,
                 protected_ids: frozenset[str]) -> None:
    current = rows.get(patch.target_id)
    if patch.action is PatchAction.INSERT:
        if current is not None:
            raise PatchError(f"insert target {patch.target_id!r} already exists")
        _merge_row(rows, ConfigRow(
            id=patch.target_id, layer=doc.layer, source=patch.source,
            kind=patch.kind or RowKind.PART,
            plugin_id=patch.plugin_id or patch.target_id,
            config=dict(patch.config or {}),
            enabled=True if patch.enabled is None else patch.enabled),
            protected_ids)
        return
    if current is None:
        raise PatchError(f"patch target {patch.target_id!r} does not exist")
    if patch.action is PatchAction.PRESET:
        if current.kind is not RowKind.PRESET:
            raise PatchError(
                f"preset patch target {patch.target_id!r} is not a preset row")
        config = _deep_copy(current.config)
        plugins = [str(p) for p in (config.get("plugins") or ())]
        op = patch.plugin_list_op
        if op is PluginListOp.ADD:
            for name in patch.plugin_list:
                if name not in plugins:
                    plugins.append(name)
        elif op is PluginListOp.REMOVE:
            plugins = [p for p in plugins if p not in patch.plugin_list]
        elif op is PluginListOp.REPLACE:
            plugins = list(patch.plugin_list)
        config["plugins"] = plugins
        incoming = replace(current, config=config, layer=doc.layer,
                           source=patch.source)
    elif patch.action is PatchAction.DISABLE:
        incoming = replace(current, enabled=False, layer=doc.layer,
                           source=patch.source)
    else:  # REPLACE -- the whole config is replaced, not deep-merged.
        incoming = replace(current, config=_copy_config(patch.config),
                           kind=patch.kind or current.kind,
                           plugin_id=current.plugin_id if patch.plugin_id is None
                           else patch.plugin_id,
                           enabled=current.enabled if patch.enabled is None
                           else patch.enabled,
                           layer=doc.layer, source=patch.source)
    _merge_row(rows, incoming, protected_ids)


def compose(
    bundles: Sequence[Bundle] = (), *,
    profile: PatchDocument | None = None,
    home: PatchDocument | None = None,
    project: PatchDocument | None = None,
    overlays: Sequence[PatchDocument] = (),
    protected_ids: Iterable[str] = PROTECTED_CORE_IDS,
) -> Composition:
    """Compose all layers deterministically.

    Rows keep the position of their first appearance.  Later layers win on
    config/enablement and on provenance, but never on identity or on protected
    core.  The result is identical for two calls with the same inputs.
    """
    docs = ordered_layer_docs(bundles, profile=profile, home=home,
                              project=project, overlays=overlays)
    protected = frozenset(str(p) for p in protected_ids)
    rows: dict[str, ConfigRow] = {}
    applied: list[str] = []
    for layer, source, payload in docs:
        applied.append(f"{_val(layer)}:{source}")
        if layer is Layer.BUNDLE:
            for item in payload:
                _merge_row(
                    rows,
                    replace(item, layer=Layer.BUNDLE, source=source),
                    protected)
        else:
            doc = PatchDocument(layer=layer, source=source, patches=payload)
            for patch in doc.patches:
                _apply_patch(rows, patch, doc, protected)
    return Composition(rows=tuple(rows.values()),
                       applied_layers=tuple(applied),
                       protected_ids=tuple(sorted(protected)))


# ---------------------------------------------------------------------------
# D1.5 -- --dump-config: exact boot tree, provenance on every row, no secrets
# ---------------------------------------------------------------------------


_SECRET_KEY_RE = re.compile(
    r"(?i)(secret|password|passwd|token|credential|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|authorization|auth[_-]?header|cookie|session[_-]?key)")
_SECRET_VALUE_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|xox[baprs]-"
    r"[A-Za-z0-9\-]{8,}|AKIA[0-9A-Z]{12,}|Bearer\s+\S+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)")
REDACTED = "<redacted>"


def redact_value(value: Any) -> Any:
    """Recursively redact secret keys and obvious secret value patterns."""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            name = str(key)
            result[name] = (REDACTED if _SECRET_KEY_RE.search(name)
                            else redact_value(item))
        return result
    if isinstance(value, (list, tuple)):
        return [redact_value(v) for v in value]
    if isinstance(value, str) and _SECRET_VALUE_RE.search(value):
        return REDACTED
    return value


def redact_config(config: Mapping[str, Any]) -> dict:
    """A copy of *config* safe to print; never mutates the source."""
    redacted = redact_value(config)
    return redacted if isinstance(redacted, dict) else {}


def find_secret_patterns(text: str) -> tuple[str, ...]:
    """Obvious credential patterns still present in rendered text."""
    return tuple(sorted(set(m.group(0) for m in _SECRET_VALUE_RE.finditer(text))))


def assert_no_secrets(text: str, secrets: Iterable[str] = ()) -> None:
    """Fail if *text* contains a known secret string or a credential pattern."""
    for secret in secrets:
        if isinstance(secret, str) and secret and secret in text:
            raise SecretLeakError("a known secret value leaked into the dump")
    found = find_secret_patterns(text)
    if found:
        raise SecretLeakError(f"secret-looking values leaked into the dump: {found}")


def dump_config_rows(composition: Composition) -> tuple[dict, ...]:
    """The "What is running" view: one redacted, provenance-tagged row each."""
    out: list[dict] = []
    for item in composition.rows:
        data = item.to_dict()
        data["config"] = redact_config(item.config)
        data["source_layer"] = item.layer.value
        data["source"] = item.source
        out.append(data)
    return tuple(out)


def dump_config(composition: Composition) -> str:
    """Print the exact plugin tree the machine will boot.

    Each row carries its provenance (``[layer=... source=...]``).  Config is
    rendered redacted, so no secret value reaches stdout or the UI.
    """
    if not isinstance(composition, Composition):
        raise PluginContractError("dump_config expects a Composition")
    lines = [
        "# Keel plugin tree (exact boot composition)",
        f"fingerprint: {composition.fingerprint}",
        f"rows: {len(composition.rows)}",
        "protected-core: " + ",".join(composition.protected_ids),
        "",
    ]
    for data in dump_config_rows(composition):
        lines.append(
            f"- id={data['id']} kind={data['kind']} plugin={data['plugin_id']} "
            f"enabled={str(data['enabled']).lower()} "
            f"protected={str(data['protected']).lower()} "
            f"[layer={data['source_layer']} source={data['source']}]")
        if data["config"]:
            lines.append("    config: " + json.dumps(
                data["config"], sort_keys=True, separators=(",", ":"),
                ensure_ascii=False))
    text = "\n".join(lines) + "\n"
    assert_no_secrets(text)
    return text


def dump_config_json(composition: Composition) -> str:
    """Machine-readable variant of :func:`dump_config` with the same content."""
    payload = {
        "fingerprint": composition.fingerprint,
        "applied_layers": list(composition.applied_layers),
        "protected_core": list(composition.protected_ids),
        "rows": list(dump_config_rows(composition)),
    }
    text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)
    assert_no_secrets(text)
    return text


# ---------------------------------------------------------------------------
# D1.10 -- desktop shell descriptor (descriptor only, no packaging)
# ---------------------------------------------------------------------------


RESERVED_DESKTOP_PROFILE = "desktop"

BOOT_SEQUENCE: tuple[str, ...] = (
    "load_packaged_web_assets",
    "start_private_desktop_host",
    "wait_for_boot_injections",
    "activate_client_plugins_same_document",
)

IPC_CHANNELS: tuple[str, ...] = (
    "boot-injections", "ready", "fatal-error", "shutdown")


class IpcChannel(str, Enum):
    BOOT_INJECTIONS = "boot-injections"
    READY = "ready"
    FATAL_ERROR = "fatal-error"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class DesktopShellDescriptor:
    """What the Electron shell must be, as inert, reviewable configuration.

    No packaging, signing, subprocess or file write happens here: the fields
    describe the production shell contract so a lead can wire it to the real
    build.  ``runtime_source='signed_resources'`` and ``repackaging_allowed=
    False`` encode "ships the exact production runtime in signed resources".
    """

    profile: str = RESERVED_DESKTOP_PROFILE
    runtime_resource: str = "resources/runtime/keel-production"
    runtime_source: str = "signed_resources"
    runtime_identity: str = "keel-production-runtime"
    signature_algorithm: str = "platform-code-signature"
    signed: bool = True
    repackaging_allowed: bool = False
    ui_owner: str = "electron_shell"
    host_mode: str = "electron_as_node"
    host_bind: str = "127.0.0.1"
    host_port: str = "os_assigned"
    host_port_value: int = 0
    per_launch_token_env: str = "KEEL_DESKTOP_TOKEN"
    boot_assets: str = "resources/web"
    boot_sequence: tuple[str, ...] = BOOT_SEQUENCE
    wait_for_boot_injections: bool = True
    activate_plugins_in_same_document: bool = True
    ipc_channels: tuple[str, ...] = IPC_CHANNELS
    fatal_error_screen: bool = True
    shared_product_data: bool = True
    separate_plugin_packages: bool = True
    separate_activation_state: bool = True
    separate_lockfiles: bool = True
    packaging: str = "descriptor_only"

    def __post_init__(self) -> None:
        object.__setattr__(self, "boot_sequence", tuple(self.boot_sequence))
        object.__setattr__(self, "ipc_channels", tuple(self.ipc_channels))

    @property
    def is_reserved_profile(self) -> bool:
        return self.profile == RESERVED_DESKTOP_PROFILE

    def to_dict(self) -> dict:
        return {f.name: (
            list(getattr(self, f.name)) if isinstance(getattr(self, f.name), tuple)
            else getattr(self, f.name)) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DesktopShellDescriptor":
        d = dict(data)
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})

    def validate(self) -> "DesktopShellDescriptor":
        return assert_descriptor_complete(self)


def assert_descriptor_complete(
    descriptor: DesktopShellDescriptor,
) -> DesktopShellDescriptor:
    """Fail closed unless the descriptor covers every D1.10 obligation."""
    if not isinstance(descriptor, DesktopShellDescriptor):
        raise DescriptorError("expected a DesktopShellDescriptor")
    checks = (
        (descriptor.is_reserved_profile, "reserved `desktop` profile"),
        (descriptor.runtime_source == "signed_resources",
         "exact production runtime in signed resources"),
        (descriptor.signed and bool(descriptor.signature_algorithm)
         and not descriptor.repackaging_allowed,
         "signed, non-repackaged runtime"),
        (descriptor.ui_owner == "electron_shell", "shell owns the UI"),
        (descriptor.host_mode == "electron_as_node", "private Desktop Host"),
        (descriptor.host_bind == "127.0.0.1"
         and descriptor.host_port == "os_assigned"
         and descriptor.host_port_value == 0
         and bool(descriptor.per_launch_token_env),
         "loopback host with OS-assigned port and per-launch token"),
        (tuple(descriptor.boot_sequence) == BOOT_SEQUENCE
         and descriptor.wait_for_boot_injections
         and descriptor.activate_plugins_in_same_document
         and bool(descriptor.boot_assets),
         "packaged assets first, then boot injections, then plugins"),
        (set(descriptor.ipc_channels) == set(IPC_CHANNELS),
         "Node IPC channels for injections/readiness/fatal/shutdown"),
        (descriptor.fatal_error_screen, "structured fatal-error screen"),
        (descriptor.shared_product_data
         and descriptor.separate_plugin_packages
         and descriptor.separate_activation_state
         and descriptor.separate_lockfiles,
         "shared product data, separate packages/activation/lockfiles"),
        (descriptor.packaging == "descriptor_only", "no packaging performed"),
    )
    for ok, obligation in checks:
        if not ok:
            raise DescriptorError(f"incomplete desktop descriptor: {obligation}")
    return descriptor


def desktop_shell_descriptor() -> DesktopShellDescriptor:
    """The canonical, validated D1.10 descriptor."""
    return assert_descriptor_complete(DesktopShellDescriptor())


# ---------------------------------------------------------------------------
# D1.12 -- core package map: one service key per core package on the context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoreService:
    """One package's typed responsibility and its single context service key."""

    key: str
    part_id: str
    package: str
    responsibility: str
    guarded: bool = False
    context_exposed: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        for name in ("key", "part_id", "package", "responsibility"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise PluginContractError(
                    f"core service {name} must be non-empty")

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


CORE_SERVICE_KEYS: tuple[str, ...] = (
    "sessions", "system_prompt", "tools", "agents", "agent_loop", "llm")

CORE_PACKAGE_MAP: dict[str, CoreService] = {
    "sessions": CoreService(
        key="sessions", part_id="sessions", package="keel.session_contracts",
        responsibility="Append-only typed session log; persistence and replay",
        notes="Inert descriptor; durable sink is keel/transcript.py."),
    "system_prompt": CoreService(
        key="system_prompt", part_id="system_prompt", package="keel.prompts",
        responsibility="Deterministic system-prompt assembly from ordered sections"),
    "tools": CoreService(
        key="tools", part_id="tools", package="keel.tool_registry",
        responsibility="Tool registry plus guarded execution pipeline",
        guarded=True,
        notes="Guarded pipeline covers approval, permission and safety checks."),
    "agents": CoreService(
        key="agents", part_id="agents", package="keel.agent_contracts",
        responsibility="Agent interface and live registry"),
    "agent_loop": CoreService(
        key="agent_loop", part_id="agent_loop", package="keel.loop",
        responsibility="Agent loop driver / turn orchestration"),
    "llm": CoreService(
        key="llm", part_id="llm", package="keel.provider_contracts",
        responsibility="LLM vocabulary and adapter seam",
        notes="Model adapter implementation is an inert descriptor string."),
}


def core_service_keys() -> tuple[str, ...]:
    return CORE_SERVICE_KEYS


def core_package_map() -> dict[str, CoreService]:
    """A copy of the typed map (callers cannot mutate the canonical one)."""
    return dict(CORE_PACKAGE_MAP)


def assert_core_map_complete(registry: PluginRegistry | None = None) -> None:
    """Prove every key has one exposed service, a responsibility and a part."""
    if tuple(CORE_PACKAGE_MAP) != CORE_SERVICE_KEYS:
        raise PluginContractError("core package map keys drifted from the contract")
    known = registry.ids() if registry is not None else CORE_PART_IDS
    for key in CORE_SERVICE_KEYS:
        service = CORE_PACKAGE_MAP.get(key)
        if service is None or not service.context_exposed:
            raise PluginContractError(f"service key {key!r} is not exposed on context")
        if service.key != key or not service.responsibility or not service.package:
            raise PluginContractError(f"service key {key!r} is incomplete")
        if service.part_id not in known:
            raise PluginContractError(
                f"service key {key!r} references unknown part {service.part_id!r}")
    if not CORE_PACKAGE_MAP["tools"].guarded:
        raise PluginContractError("the tool registry must expose a guarded pipeline")
