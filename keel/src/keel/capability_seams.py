"""Descriptor/policy layer for the D3.x capability-seam P0 rows.

This module is deliberately *shallow by design*: it models the three roles of a
capability seam (definition / provider / consumer), the swappable execution
world, the missing package groups, and the spill / guard / workspace /
session-query policies as immutable descriptors.  It performs **no file I/O,
no subprocess launches, no network calls and no database access**.  Every
factory is pure: the same inputs always produce the same descriptor.

Scope (all ``not_started`` P0 rows in the D3 family):
    D3.1  capability seam = ServiceDefinition + ServiceProvider + Consumer
    D3.2  one provider swap changes the whole execution world
    D3.6  human commands dispatch without a model turn
    D3.7  background jobs service with ``job_*`` tools
    D3.8  trusted-rule webhook runtime (descriptor only, no network)
    D3.9  shell / terminals / sandbox backends; sandbox wraps argv
    D3.11 package groups with honest local-vs-external classification
    D3.13 spill: large tool output -> file + redacted preview
    D3.14 guard: loop/tool guard plugin group with monotonic deny
    D3.18 workspace entities + session-query (browse/search/export)

Deeper rows (D3.12 deliverables UI, D3.15 extensions approval UI, D3.19 plan /
schedule, D3.20 quarantine policy file, D3.21/22/23 generated/compiled assets)
are classified honestly in :func:`classify_packages` rather than claimed here.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

# All P0 rows of the D3 family that own a descriptor in this module.
FEATURE_IDS: tuple[str, ...] = (
    "D3.1", "D3.2", "D3.6", "D3.7", "D3.8",
    "D3.9", "D3.11", "D3.13", "D3.14", "D3.18",
)


# ---------------------------------------------------------------------------
# errors and small normalisers
# ---------------------------------------------------------------------------
class SeamError(ValueError):
    """Raised when a seam invariant is violated (typed role, exclusivity...)."""


class ProviderError(ValueError):
    """Raised for an invalid provider kind / execution world."""


class PackageError(ValueError):
    """Raised for an invalid package descriptor."""


class SpillError(ValueError):
    """Raised for an invalid spill policy."""


class GuardError(ValueError):
    """Raised when a guard registration would weaken an inherited deny."""


class QueryError(ValueError):
    """Raised when a workspace entity or session query escapes its root."""


def _enum(enum_cls: type[Enum], value: Any) -> Enum:
    """Coerce a string/enum value into *enum_cls* with a clear error."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError) as exc:
        raise SeamError(
            f"expected a {enum_cls.__name__} value, got {value!r}") from exc


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _params(value: Any) -> tuple[tuple[str, str], ...]:
    """Canonicalise config params into a sorted tuple of string pairs."""
    if not value:
        return ()
    items = value.items() if isinstance(value, Mapping) else value
    return tuple(sorted((str(k), str(v)) for k, v in items))


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===========================================================================
# D3.1 — capability seam: definition + provider + consumer
# ===========================================================================
class SeamRole(str, Enum):
    DEFINITION = "definition"
    PROVIDER = "provider"
    CONSUMER = "consumer"


@dataclass(frozen=True)
class ServiceDefinition:
    """The typed interface of a service (never the implementation)."""

    name: str
    interface: str
    operations: tuple[str, ...] = ()
    version: str = "1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "interface", str(self.interface).strip())
        object.__setattr__(self, "operations", _tuple(self.operations))
        object.__setattr__(self, "version", str(self.version))
        if not self.name or not self.interface:
            raise SeamError("a ServiceDefinition needs a name and an interface")

    def describe(self) -> dict:
        return {
            "name": self.name, "interface": self.interface,
            "operations": list(self.operations), "version": self.version,
        }


@dataclass(frozen=True)
class ServiceProvider:
    """One concrete implementation bound to a :class:`ServiceDefinition`."""

    name: str
    definition: str
    impl: str
    realm: str = "default"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "definition", str(self.definition).strip())
        object.__setattr__(self, "impl", str(self.impl).strip())
        object.__setattr__(self, "realm", str(self.realm))
        if not self.name or not self.definition or not self.impl:
            raise SeamError("a ServiceProvider needs name, definition and impl")

    def describe(self) -> dict:
        return {
            "name": self.name, "definition": self.definition,
            "impl": self.impl, "realm": self.realm,
        }


@dataclass(frozen=True)
class Consumer:
    """A tool/UI surface that requires exactly one service definition."""

    name: str
    requires: str
    entrypoint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "requires", str(self.requires).strip())
        object.__setattr__(self, "entrypoint", str(self.entrypoint))
        if not self.name or not self.requires:
            raise SeamError("a Consumer needs a name and a required definition")

    def describe(self) -> dict:
        return {
            "name": self.name, "requires": self.requires,
            "entrypoint": self.entrypoint,
        }


# Friendly alias used by builder-guide prose.
ServiceConsumer = Consumer

_ROLE_TYPES: dict[SeamRole, type] = {
    SeamRole.DEFINITION: ServiceDefinition,
    SeamRole.PROVIDER: ServiceProvider,
    SeamRole.CONSUMER: Consumer,
}


@dataclass(frozen=True)
class CapabilitySeam:
    """A *complete* seam — all three roles are required to exist."""

    definition: ServiceDefinition
    provider: ServiceProvider
    consumer: Consumer

    @property
    def name(self) -> str:
        return self.definition.name

    def describe(self) -> dict:
        return {
            "seam": self.name,
            "definition": self.definition.describe(),
            "provider": self.provider.describe(),
            "consumer": self.consumer.describe(),
            "roles_active": sorted(role.value for role in SeamRole),
        }


class SeamRegistry:
    """Typed, role-exclusive registration of seam participants.

    A participant (identified by ``name``) can hold exactly one role, and a
    role accepts exactly one participant type.  A seam is only "complete"
    when a definition, a provider and a consumer are all registered for the
    same definition name — one role alone is never reported as a seam.
    """

    def __init__(self) -> None:
        self._by_role: dict[SeamRole, dict[str, Any]] = {
            role: {} for role in SeamRole}
        self._role_of: dict[str, SeamRole] = {}

    def register(self, role: SeamRole | str, participant: Any) -> Any:
        role = _enum(SeamRole, role)
        expected = _ROLE_TYPES[role]
        # Exact type check: a duck-typed object is not a typed registration.
        if type(participant) is not expected:
            raise SeamError(
                f"typed registration failed: role {role.value} requires "
                f"{expected.__name__}, got {type(participant).__name__}")
        name = participant.name
        current = self._role_of.get(name)
        if current is not None and current != role:
            raise SeamError(
                f"role exclusivity violated: {name!r} is already active as "
                f"{current.value}, cannot also be {role.value}")
        existing = self._by_role[role].get(name)
        if existing is not None and existing != participant:
            raise SeamError(f"conflicting registration for {name!r} in {role.value}")
        self._by_role[role][name] = participant
        self._role_of[name] = role
        return participant

    def role_of(self, name: str) -> SeamRole | None:
        return self._role_of.get(str(name))

    def get(self, role: SeamRole | str, name: str) -> Any | None:
        return self._by_role[_enum(SeamRole, role)].get(str(name))

    def complete_seams(self) -> tuple[CapabilitySeam, ...]:
        seams: list[CapabilitySeam] = []
        for name, definition in sorted(self._by_role[SeamRole.DEFINITION].items()):
            providers = [p for p in self._by_role[SeamRole.PROVIDER].values()
                         if p.definition == name]
            consumers = [c for c in self._by_role[SeamRole.CONSUMER].values()
                         if c.requires == name]
            if len(providers) == 1 and len(consumers) == 1:
                seams.append(CapabilitySeam(definition, providers[0], consumers[0]))
        return tuple(seams)

    def describe(self) -> dict:
        return {
            "roles": {r.value: sorted(self._by_role[r]) for r in SeamRole},
            "complete_seams": [s.describe() for s in self.complete_seams()],
        }


def seam_checklist() -> dict:
    """D3.1's builder-guide checklist, as data."""
    return {
        "feature_id": "D3.1",
        "roles": [r.value for r in SeamRole],
        "rule": "one role alone is not a seam; define all three",
        "required_types": {r.value: t.__name__ for r, t in _ROLE_TYPES.items()},
        "exclusivity": "one participant name -> exactly one active role",
        "io_performed": False,
    }


# ===========================================================================
# D3.2 / D3.9 — one execution world drives every provider
# ===========================================================================
class ExecutionWorld(str, Enum):
    LOCAL = "local"
    CONTAINER = "container"
    SSH = "ssh"
    WSL = "wsl"


class ProviderKind(str, Enum):
    FILESYSTEM = "filesystem"
    SUBPROCESS = "subprocess"
    SHELL = "shell"
    TERMINALS = "terminals"
    SANDBOX = "sandbox"


_PROVIDER_CONTRACT: dict[ProviderKind, str] = {
    ProviderKind.FILESYSTEM: "keel.providers.FilesystemProvider",
    ProviderKind.SUBPROCESS: "keel.providers.SubprocessProvider",
    ProviderKind.SHELL: "keel.providers.ShellBackend",
    ProviderKind.TERMINALS: "keel.providers.TerminalsBackend",
    ProviderKind.SANDBOX: "keel.providers.SandboxBackend",
}

_PROVIDER_CAPABILITIES: dict[ProviderKind, tuple[str, ...]] = {
    ProviderKind.FILESYSTEM: ("read", "write", "stat", "list", "export"),
    ProviderKind.SUBPROCESS: ("spawn", "wait", "terminate"),
    ProviderKind.SHELL: ("exec", "pipe"),
    ProviderKind.TERMINALS: ("pty", "resize", "close"),
    ProviderKind.SANDBOX: ("wrap_argv", "apply_policy"),
}

_WORLD_SCHEME: dict[ExecutionWorld, str] = {
    ExecutionWorld.LOCAL: "local",
    ExecutionWorld.CONTAINER: "container",
    ExecutionWorld.SSH: "ssh",
    ExecutionWorld.WSL: "wsl",
}

_WORLD_HOST_PARAM: dict[ExecutionWorld, str] = {
    ExecutionWorld.LOCAL: "root",
    ExecutionWorld.CONTAINER: "image",
    ExecutionWorld.SSH: "host",
    ExecutionWorld.WSL: "distro",
}

# Services that must move together when the execution world changes.
WORLD_MOVED_SERVICES: tuple[str, ...] = (
    "filesystem", "bash", "pty", "lsp", "sandbox",
)


@dataclass(frozen=True)
class ProviderConfig:
    """Pure configuration value; it never opens a connection or a file."""

    kind: ProviderKind
    world: ExecutionWorld = ExecutionWorld.LOCAL
    params: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum(ProviderKind, self.kind))
        object.__setattr__(self, "world", _enum(ExecutionWorld, self.world))
        object.__setattr__(self, "params", _params(self.params))

    def params_dict(self) -> dict[str, str]:
        return dict(self.params)

    def replace(self, *, world: Any = None, params: Any = None) -> ProviderConfig:
        return ProviderConfig(
            kind=self.kind,
            world=self.world if world is None else world,
            params=self.params if params is None else params,
        )


@dataclass(frozen=True)
class ProviderDescriptor:
    """The deterministic result of :func:`resolve_provider`."""

    kind: ProviderKind
    world: ExecutionWorld
    provider_id: str
    interface: str
    target: str
    capabilities: tuple[str, ...]
    moves_with_world: bool = True
    io_performed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum(ProviderKind, self.kind))
        object.__setattr__(self, "world", _enum(ExecutionWorld, self.world))
        object.__setattr__(self, "capabilities", _tuple(self.capabilities))

    def describe(self) -> dict:
        return {
            "kind": self.kind.value, "world": self.world.value,
            "provider_id": self.provider_id, "interface": self.interface,
            "target": self.target, "capabilities": list(self.capabilities),
            "moves_with_world": self.moves_with_world,
            "io_performed": self.io_performed,
        }


def _config_from(value: Any, kind: Any) -> ProviderConfig:
    if isinstance(value, ProviderConfig):
        config = value
    elif isinstance(value, Mapping):
        config = ProviderConfig(
            kind=value.get("kind", kind),
            world=value.get("world", ExecutionWorld.LOCAL),
            params=value.get("params", value),
        )
    else:
        config = ProviderConfig(kind=kind)
    wanted = _enum(ProviderKind, kind)
    if config.kind != wanted:
        raise ProviderError(
            f"provider kind mismatch: config is {config.kind.value}, asked for {wanted.value}")
    return config


def resolve_provider(kind: ProviderKind | str, config: ProviderConfig | Mapping) -> ProviderDescriptor:
    """Pure factory: describe a provider without constructing one.

    ``config`` may be a :class:`ProviderConfig` or a mapping with ``kind``,
    ``world`` and ``params``.  No OS API is touched; the returned descriptor is
    what a real (injected) provider factory would consume.
    """
    config = _config_from(config, kind)
    kind = config.kind
    params = config.params_dict()
    host = params.get(_WORLD_HOST_PARAM[config.world], "")
    target = _WORLD_SCHEME[config.world] + "://" + host
    if params.get("root"):
        target += "/" + str(params["root"]).strip("/")
    suffix = _digest("|".join(f"{k}={v}" for k, v in config.params))[:8] \
        if config.params else ""
    provider_id = f"{kind.value}.{config.world.value}"
    if suffix:
        provider_id += "." + suffix
    return ProviderDescriptor(
        kind=kind, world=config.world, provider_id=provider_id,
        interface=_PROVIDER_CONTRACT[kind], target=target,
        capabilities=_PROVIDER_CAPABILITIES[kind],
    )


def swap_world(config: ProviderConfig | Mapping, world: ExecutionWorld | str) -> ProviderConfig:
    """Return a new config with only the execution world changed."""
    if isinstance(config, ProviderConfig):
        return config.replace(world=world)
    base = _config_from(config, config.get("kind", ProviderKind.FILESYSTEM)
                        if isinstance(config, Mapping) else ProviderKind.FILESYSTEM)
    return base.replace(world=world)


def resolve_world_bundle(world: ExecutionWorld | str,
                         params: Mapping | None = None) -> tuple[ProviderDescriptor, ...]:
    """All provider kinds resolved against *one* world (the D3.2 promise)."""
    return tuple(
        resolve_provider(kind, ProviderConfig(kind=kind, world=world, params=params))
        for kind in sorted(ProviderKind, key=lambda k: k.value)
    )


def world_manifest(world: ExecutionWorld | str) -> dict:
    world = _enum(ExecutionWorld, world)
    return {
        "feature_id": "D3.2", "world": world.value,
        "moved_services": list(WORLD_MOVED_SERVICES),
        "providers": [d.describe() for d in resolve_world_bundle(world)],
        "rule": "one provider swap moves filesystem, bash, PTY and LSP together",
        "io_performed": False,
    }


_DIRECT_OS_IMPORT = re.compile(
    r"^\s*(?:import\s+(?:os|subprocess)\b|from\s+(?:os|subprocess)\s+import\b)",
    re.MULTILINE,
)


def provider_boundary_check(sources: Mapping[str, str]) -> dict:
    """Pure source-text check for the D3.2 rule "tools never import OS APIs".

    Callers pass tool name -> source text; nothing is read from disk.
    """
    violations = [name for name, text in sorted(sources.items())
                  if _DIRECT_OS_IMPORT.search(str(text))]
    return {
        "feature_id": "D3.2",
        "rule": "tools never import OS APIs directly",
        "checked": sorted(sources), "violations": violations,
        "clean": not violations, "io_performed": False,
    }


# ===========================================================================
# D3.9 — backends as services; sandbox wraps argv before spawning
# ===========================================================================
@dataclass(frozen=True)
class ServiceDescriptor:
    feature_id: str
    name: str
    contract: tuple[str, ...] = ()
    backend: str = "descriptor_only"
    io_performed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract", _tuple(self.contract))

    def describe(self) -> dict:
        return {
            "feature_id": self.feature_id, "name": self.name,
            "contract": list(self.contract), "backend": self.backend,
            "io_performed": self.io_performed,
        }


def backend_services() -> tuple[ServiceDescriptor, ...]:
    """D3.9: shell, terminals and sandbox are separate services."""
    return (
        ServiceDescriptor("D3.9", "shell", ("exec", "pipe", "detach")),
        ServiceDescriptor("D3.9", "terminals", ("pty", "resize", "close")),
        ServiceDescriptor("D3.9", "sandbox", ("wrap_argv", "apply_policy")),
    )


@dataclass(frozen=True)
class SandboxWrapDescriptor:
    argv: tuple[str, ...]
    wrapped_argv: tuple[str, ...]
    policy: str
    launcher: str
    spawn: bool = False
    feature_id: str = "D3.9"

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", _tuple(self.argv))
        object.__setattr__(self, "wrapped_argv", _tuple(self.wrapped_argv))

    def describe(self) -> dict:
        return {
            "feature_id": self.feature_id, "argv": list(self.argv),
            "wrapped_argv": list(self.wrapped_argv), "policy": self.policy,
            "launcher": self.launcher, "spawn": self.spawn,
        }


def sandbox_wrap_argv(argv: Sequence[str], *, launcher: str = "keel-sandbox",
                      policy: str = "default") -> SandboxWrapDescriptor:
    """Describe argv wrapping; *nothing is spawned*."""
    args = _tuple(argv)
    if not args:
        raise SeamError("cannot wrap an empty argv")
    return SandboxWrapDescriptor(
        argv=args,
        wrapped_argv=(str(launcher), "--policy", str(policy), "--", *args),
        policy=str(policy), launcher=str(launcher),
    )


# ===========================================================================
# D3.6 / D3.7 / D3.8 — remaining P0 descriptor seams
# ===========================================================================
@dataclass(frozen=True)
class CommandRegistration:
    name: str
    handler: str
    model_turn: bool
    pure_code: bool
    feature_id: str = "D3.6"

    def describe(self) -> dict:
        return {
            "feature_id": self.feature_id, "name": self.name,
            "handler": self.handler, "model_turn": self.model_turn,
            "pure_code": self.pure_code,
            "dispatch_without_model_turn": not self.model_turn,
        }


class CommandService:
    """D3.6: slash commands that are pure code never call the model."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandRegistration] = {}

    def register(self, name: str, handler: str, *,
                 model_turn: bool = False, pure_code: bool = True) -> CommandRegistration:
        if model_turn and pure_code:
            raise SeamError("a pure-code command cannot declare a model turn")
        cmd = CommandRegistration(
            name=str(name).lstrip("/"), handler=str(handler),
            model_turn=bool(model_turn), pure_code=bool(pure_code))
        if cmd.name in self._commands:
            raise SeamError(f"duplicate command {cmd.name!r}")
        self._commands[cmd.name] = cmd
        return cmd

    def dispatch_descriptor(self, name: str) -> dict:
        cmd = self._commands.get(str(name).lstrip("/"))
        if cmd is None:
            raise SeamError(f"unknown command {name!r}")
        return cmd.describe()


JOB_TOOLS: tuple[str, ...] = ("job_list", "job_read", "job_stop")


def job_tools() -> tuple[ServiceDescriptor, ...]:
    """D3.7: read/stop tools for the background-jobs service (no jobs run)."""
    return tuple(ServiceDescriptor("D3.7", name, ("read_only",)) for name in JOB_TOOLS)


@dataclass(frozen=True)
class WebhookRuleDescriptor:
    name: str
    trusted: bool
    signature_headers: tuple[str, ...]
    confirmation_required: bool
    adapters: tuple[str, ...] = ()
    network: bool = False
    feature_id: str = "D3.8"

    def __post_init__(self) -> None:
        object.__setattr__(self, "signature_headers", _tuple(self.signature_headers))
        object.__setattr__(self, "adapters", _tuple(self.adapters))

    def describe(self) -> dict:
        return {
            "feature_id": self.feature_id, "name": self.name,
            "trusted": self.trusted,
            "signature_headers": list(self.signature_headers),
            "confirmation_required": self.confirmation_required,
            "adapters": list(self.adapters), "network": self.network,
            "dependencies": ["Y5.4", "V9"],
        }


def webhook_rule(name: str, *, trusted: bool = True,
                 signature_headers: Sequence[str] = ("x-signature",),
                 confirmation_required: bool = True,
                 adapters: Sequence[str] = ()) -> WebhookRuleDescriptor:
    """D3.8: only an explicitly trusted rule may start a session.

    This is a descriptor only — no listener is opened and no HTTP is sent.
    """
    if not trusted:
        raise SeamError("an untrusted webhook rule cannot start a session")
    if not signature_headers:
        raise SeamError("a trusted webhook rule requires signature headers")
    if not confirmation_required:
        raise SeamError("remote-initiated actions require confirmation (V9)")
    return WebhookRuleDescriptor(
        name=str(name), trusted=True,
        signature_headers=_tuple(signature_headers),
        confirmation_required=True, adapters=_tuple(adapters),
    )


# ===========================================================================
# D3.11 — package groups and honest classification
# ===========================================================================
class PackageClassification(str, Enum):
    LOCALLY_ACHIEVABLE = "locally_achievable"
    EXTERNAL_DEPENDENCY = "external_dependency"
    OWNER_GATED = "owner_gated"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class PackageDescriptor:
    group: str
    purpose: str
    classification: PackageClassification
    rationale: str
    feature_id: str = ""
    external_requirement: str = ""
    scope: str = "descriptor_only"
    runtime_claimed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "classification",
                           _enum(PackageClassification, self.classification))
        if not self.purpose or not self.rationale:
            raise PackageError("a package descriptor needs a purpose and a rationale")
        if self.runtime_claimed:
            raise PackageError("this layer never claims a running implementation")

    def describe(self) -> dict:
        return {
            "group": self.group, "purpose": self.purpose,
            "classification": self.classification.value,
            "rationale": self.rationale, "feature_id": self.feature_id,
            "external_requirement": self.external_requirement,
            "scope": self.scope, "runtime_claimed": self.runtime_claimed,
        }


# (group, purpose, classification, rationale, feature_id, external_requirement)
_PACKAGE_ROWS: tuple[tuple[str, str, PackageClassification, str, str, str], ...] = (
    ("deliverables", "Named per-turn result cards (files, summaries)",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "Result-card data is pure; the delivered UI panel is D3.12 (P1) and is not claimed here.",
     "D3.12", ""),
    ("spill", "Large tool output spills to a file with a short preview",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "Threshold, preview and redaction policy are pure stdlib; this layer writes no file.",
     "D3.13", ""),
    ("attachment", "Attachments carried into turns",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "Descriptor/policy shape only; the existing runtime surface is owned elsewhere and was not modified.",
     "D3.11", ""),
    ("guard", "Loop and tool guard plugin group with monotonic deny",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "Registration and effective-decision rules are pure; no model loop hooks are installed here.",
     "D3.14", ""),
    ("extensions", "Runtime self-modification (skills/commands/agents as diffs)",
     PackageClassification.OWNER_GATED,
     "The plan forbids auto-install; only an approval-gated proposal descriptor is safe locally.",
     "D3.15", "owner approval workflow"),
    ("feedback", "Human feedback (thumbs up/down plus note)",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "Feedback records are pure descriptors; persistence/eval wiring is a separate seam.",
     "D3.16", ""),
    ("identity", "Anonymous local install id, never transmitted",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "A random local id with no telemetry is achievable with stdlib and no network in this layer.",
     "D3.17", ""),
    ("workspace", "Workspace entities with path containment",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "Entities and containment checks are pure string logic; no database is opened.",
     "D3.18", ""),
    ("plan", "Logged planning checklist surviving restart",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "Plan events are pure descriptors; durable event persistence is out of scope here.",
     "D3.19", ""),
    ("schedule", "Scheduled follow-ups",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "Schedule descriptors are pure; a live timer/scheduler needs runtime integration not provided here.",
     "D3.19", ""),
    ("ptc-runtime", "Programmatic tool-call execution",
     PackageClassification.UNVERIFIED,
     "The plan explicitly says the meaning is to be verified; no local contract is asserted.",
     "D3.11", "spec clarification"),
    ("session-query", "Browse/search/export of sessions",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "Query descriptors enforce workspace containment; FTS5 is a planned backend, no DB is used here.",
     "D3.18", ""),
    ("typert", "Type graph for RPC",
     PackageClassification.UNVERIFIED,
     "No local type-graph contract is specified in the source plan; nothing is claimed.",
     "D3.11", "spec clarification"),
    ("liveshare", "Experimental read-only live session viewer",
     PackageClassification.EXTERNAL_DEPENDENCY,
     "Requires a browser carrier and node wire codecs; no cloud relay, and outside this stdlib-only layer.",
     "D3.23", "browser carrier + node wire codecs"),
    ("inspector", "DevTools-style frontend dock",
     PackageClassification.EXTERNAL_DEPENDENCY,
     "Needs a pinned source package compiled offline; only the dock descriptor is provided here.",
     "D3.22", "pinned compiled frontend"),
    ("experimental", "Quarantine namespace and product-package policy",
     PackageClassification.LOCALLY_ACHIEVABLE,
     "Namespace and policy descriptors are pure data; flag enforcement lives in the flag surface.",
     "D3.20", ""),
)

PACKAGE_GROUPS: tuple[str, ...] = tuple(row[0] for row in _PACKAGE_ROWS)


def classify_packages() -> tuple[PackageDescriptor, ...]:
    """D3.11: every group with an honest local-vs-external classification."""
    return tuple(PackageDescriptor(*row) for row in _PACKAGE_ROWS)


def package_by_group(group: str) -> PackageDescriptor:
    for descriptor in classify_packages():
        if descriptor.group == group:
            return descriptor
    raise PackageError(f"unknown package group {group!r}")


def package_policy() -> dict:
    return {
        "feature_id": "D3.11",
        "classifications": [c.value for c in PackageClassification],
        "groups": list(PACKAGE_GROUPS),
        "rule": "locally achievable means a stdlib descriptor/policy; "
                "external and unverified groups are never claimed as implemented",
        "scope": "descriptor_only", "runtime_claimed": False,
    }


# ===========================================================================
# D3.13 — spill: large output -> file + redacted preview
# ===========================================================================
_SECRET_RULES: tuple[tuple[re.Pattern, str | None], ...] = (
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
                r"[\s\S]*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), None),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), None),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"), None),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), None),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{8,}"), None),
    (re.compile(r"(?i)(?P<key>\b(?:api[_-]?key|apikey|secret|token|password|"
                r"passwd|authorization|access[_-]?key)\b\s*[:=]\s*[\"']?)"
                r"(?P<secret>[^\s\"',;}]+)"), "secret"),
)


@dataclass(frozen=True)
class SpillPolicy:
    threshold_bytes: int = 65536
    preview_bytes: int = 2048
    redaction_marker: str = "[REDACTED]"
    extra_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        threshold = int(self.threshold_bytes)
        preview = int(self.preview_bytes)
        if threshold <= 0 or preview <= 0:
            raise SpillError("threshold_bytes and preview_bytes must be positive")
        if preview > threshold:
            raise SpillError("preview_bytes cannot exceed threshold_bytes")
        object.__setattr__(self, "threshold_bytes", threshold)
        object.__setattr__(self, "preview_bytes", preview)
        object.__setattr__(self, "redaction_marker", str(self.redaction_marker))
        object.__setattr__(self, "extra_patterns", _tuple(self.extra_patterns))


@dataclass(frozen=True)
class SpillDescriptor:
    output_id: str
    total_bytes: int
    spilled: bool
    spill_path: str
    preview: str
    preview_bytes: int
    preview_truncated: bool
    sha256: str
    redaction_count: int
    threshold_bytes: int
    io_performed: bool = False

    def describe(self) -> dict:
        return {
            "output_id": self.output_id, "total_bytes": self.total_bytes,
            "spilled": self.spilled, "spill_path": self.spill_path,
            "preview": self.preview, "preview_bytes": self.preview_bytes,
            "preview_truncated": self.preview_truncated, "sha256": self.sha256,
            "redaction_count": self.redaction_count,
            "threshold_bytes": self.threshold_bytes,
            "open_full_output": "spill_path" if self.spilled else None,
            "io_performed": self.io_performed,
        }


def _replace_group(match: re.Match, group: str, marker: str) -> str:
    text = match.group(0)
    start, end = match.span(group)
    base = match.start()
    return text[:start - base] + marker + text[end - base:]


def redact_preview(text: str, *, secrets: Iterable[str] = (),
                   patterns: Iterable[str] = (),
                   marker: str = "[REDACTED]") -> tuple[str, int]:
    """Redact secrets/patterns *before* truncation, returning (text, count)."""
    result = str(text)
    count = 0
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        found = result.count(secret)
        if found:
            result = result.replace(secret, marker)
            count += found
    rules = list(_SECRET_RULES)
    for pattern in patterns:
        rules.append((re.compile(pattern), None))
    for regex, group in rules:
        matches = list(regex.finditer(result))
        if not matches:
            continue
        count += len(matches)
        result = regex.sub(
            (lambda m, g=group: _replace_group(m, g, marker)) if group else
            (lambda m: marker), result)
    return result, count


def _utf8_preview(text: str, limit: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    truncated = len(encoded) > limit
    return encoded[:limit].decode("utf-8", "replace"), truncated


def plan_spill(output: str | bytes, *, name: str = "tool-output",
               policy: SpillPolicy | None = None,
               secrets: Iterable[str] = (),
               patterns: Iterable[str] = ()) -> SpillDescriptor:
    """D3.13: compute a spill descriptor without writing any file.

    Secrets are redacted *before* the preview is cut, so a secret straddling
    the preview boundary cannot leak even partially-in-context.
    """
    policy = policy or SpillPolicy()
    if not isinstance(policy, SpillPolicy):
        raise SpillError("policy must be a SpillPolicy")
    raw = output if isinstance(output, bytes) else str(output).encode("utf-8")
    text = raw.decode("utf-8", "replace")
    digest = _digest(text)
    redacted, count = redact_preview(
        text, secrets=secrets, patterns=patterns,
        marker=policy.redaction_marker)
    preview, truncated = _utf8_preview(redacted, policy.preview_bytes)
    # Defensive final pass: a caller secret must never survive in a preview.
    for secret in secrets:
        if secret and secret in preview:
            preview = preview.replace(secret, policy.redaction_marker)
            count += 1
    spilled = len(raw) > policy.threshold_bytes
    path = f".keel/spill/{name}-{digest[:16]}.txt" if spilled else ""
    return SpillDescriptor(
        output_id=name, total_bytes=len(raw), spilled=spilled,
        spill_path=path, preview=preview,
        preview_bytes=len(preview.encode("utf-8")),
        preview_truncated=truncated, sha256=digest,
        redaction_count=count, threshold_bytes=policy.threshold_bytes,
    )


# ===========================================================================
# D3.14 — guard plugin group with monotonic deny
# ===========================================================================
class GuardKind(str, Enum):
    LOOP = "loop"
    TOOL = "tool"
    MASS_CHANGE = "mass_change"
    STEP_LIMIT = "step_limit"


class GuardDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class GuardRegistration:
    scope: str
    kind: GuardKind
    decision: GuardDecision
    reason: str
    parent: str | None

    def describe(self) -> dict:
        return {
            "scope": self.scope, "kind": self.kind.value,
            "decision": self.decision.value, "reason": self.reason,
            "parent": self.parent,
        }


@dataclass(frozen=True)
class GuardVerdict:
    scope: str
    kind: GuardKind
    decision: GuardDecision
    source: str | None
    reason: str
    chain: tuple[str, ...]

    def describe(self) -> dict:
        return {
            "scope": self.scope, "kind": self.kind.value,
            "decision": self.decision.value, "source": self.source,
            "reason": self.reason, "chain": list(self.chain),
        }


def _scope_text(scope: Any) -> str:
    return str(scope).replace("\\", "/").strip().strip("/")


class GuardRegistry:
    """Guards form a scope tree where deny is monotone down the tree.

    A child may tighten a parent's decision (allow -> deny) but can never
    enable what an ancestor denied.  Both registration and effective lookup
    enforce the invariant, so even an out-of-band registration cannot relax a
    denial.
    """

    def __init__(self) -> None:
        self._regs: dict[tuple[str, GuardKind], GuardRegistration] = {}

    def _parent_of(self, scope: str, explicit: Any) -> str | None:
        if explicit is not None and _scope_text(explicit):
            return _scope_text(explicit)
        head, sep, _ = scope.rpartition("/")
        return head if sep else None

    def _ancestors(self, scope: str, kind: GuardKind,
                   explicit: Any) -> tuple[str, ...]:
        chain: list[str] = []
        seen: set[str] = set()
        parent = self._parent_of(scope, explicit)
        while parent is not None and parent not in seen:
            seen.add(parent)
            chain.append(parent)
            reg = self._regs.get((parent, kind))
            parent = self._parent_of(parent, reg.parent if reg else None)
        parts = scope.split("/") if scope else []
        for index in range(len(parts) - 1, 0, -1):
            candidate = "/".join(parts[:index])
            if candidate not in seen:
                seen.add(candidate)
                chain.append(candidate)
        return tuple(chain)

    def register(self, scope: str, kind: GuardKind | str,
                 decision: GuardDecision | str, *, reason: str = "",
                 parent: Any = None) -> GuardRegistration:
        scope = _scope_text(scope)
        kind = _enum(GuardKind, kind)
        verdict = _enum(GuardDecision, decision)
        chain = self._ancestors(scope, kind, parent)
        key = (scope, kind)
        existing = self._regs.get(key)
        if verdict is GuardDecision.ALLOW and existing is not None \
                and existing.decision is GuardDecision.DENY:
            raise GuardError(f"cannot enable {kind.value} at {scope!r}: "
                             "it is denied at this scope")
        for ancestor in chain:
            reg = self._regs.get((ancestor, kind))
            if reg is not None and reg.decision is GuardDecision.DENY \
                    and verdict is GuardDecision.ALLOW:
                raise GuardError(
                    f"monotonic deny: {ancestor!r} denied {kind.value}, "
                    f"so {scope!r} cannot enable it")
        if existing is not None and existing.decision == verdict:
            return existing
        registration = GuardRegistration(
            scope=scope, kind=kind, decision=verdict,
            reason=str(reason), parent=self._parent_of(scope, parent))
        self._regs[key] = registration
        return registration

    def effective(self, scope: str, kind: GuardKind | str) -> GuardVerdict:
        scope = _scope_text(scope)
        kind = _enum(GuardKind, kind)
        chain = self._ancestors(scope, kind, None)
        for candidate in (scope, *chain):
            reg = self._regs.get((candidate, kind))
            if reg is not None and reg.decision is GuardDecision.DENY:
                return GuardVerdict(scope, kind, GuardDecision.DENY,
                                    reg.scope, reg.reason, chain)
        return GuardVerdict(scope, kind, GuardDecision.ALLOW, None, "", chain)

    def can_enable(self, scope: str, kind: GuardKind | str) -> bool:
        return self.effective(scope, kind).decision is GuardDecision.ALLOW

    def deny_sources(self, kind: GuardKind | str) -> tuple[str, ...]:
        kind = _enum(GuardKind, kind)
        return tuple(sorted(scope for (scope, k), reg in self._regs.items()
                            if k is kind and reg.decision is GuardDecision.DENY))

    def group_descriptor(self) -> dict:
        return {
            "feature_id": "D3.14", "group": "guard",
            "kinds": [k.value for k in GuardKind],
            "rule": "monotonic deny: a child cannot enable what its parent denied",
            "registrations": sum(1 for _ in self._regs),
            "deny_sources": {k.value: list(self.deny_sources(k))
                             for k in GuardKind},
            "io_performed": False,
        }


# ===========================================================================
# D3.18 — workspace entities + session-query (no database)
# ===========================================================================
class EntityKind(str, Enum):
    PROJECT = "project"
    FOLDER = "folder"


class QueryKind(str, Enum):
    BROWSE = "browse"
    SEARCH = "search"
    EXPORT = "export"


def _norm_segments(path: Any) -> tuple[tuple[str, ...], bool]:
    """Pure, cross-platform path normalisation (no filesystem access)."""
    raw = str(path).replace("\\", "/")
    absolute = raw.startswith("/") or bool(re.match(r"^[A-Za-z]:/", raw))
    if re.match(r"^[A-Za-z]:", raw):
        raw = raw[2:]
    segments: list[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if segments and segments[-1] != "..":
                segments.pop()
            elif not absolute:
                segments.append("..")
            continue
        segments.append(part)
    return tuple(segments), absolute


def _relative_within(root: Any, candidate: Any) -> str | None:
    """Return a normalised relative path, or None if *candidate* escapes."""
    root_segments, root_absolute = _norm_segments(root)
    cand_segments, cand_absolute = _norm_segments(candidate)
    if ".." in root_segments or ".." in cand_segments:
        return None
    if root_absolute != cand_absolute:
        return None
    if len(cand_segments) < len(root_segments):
        return None
    if cand_segments[:len(root_segments)] != root_segments:
        return None
    return "/".join(cand_segments[len(root_segments):]) or "."


@dataclass(frozen=True)
class WorkspaceEntity:
    id: str
    name: str
    path: str
    kind: EntityKind

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum(EntityKind, self.kind))

    def describe(self) -> dict:
        return {
            "id": self.id, "name": self.name, "path": self.path,
            "kind": self.kind.value,
        }


@dataclass(frozen=True)
class Workspace:
    id: str
    root: str
    entities: tuple[WorkspaceEntity, ...] = ()

    def describe(self) -> dict:
        return {
            "id": self.id, "root": self.root,
            "entities": [e.describe() for e in self.entities],
            "storage": "descriptor_only",
        }


class WorkspaceService:
    """Pure workspace entity registry with path containment."""

    def __init__(self, root: str, workspace_id: str = "ws-default") -> None:
        segments, absolute = _norm_segments(root)
        if ".." in segments:
            raise QueryError("workspace root cannot contain '..' traversal")
        prefix = "/" if absolute else ""
        self._root = prefix + "/".join(segments)
        self._absolute = absolute
        self._id = str(workspace_id)
        self._entities: dict[str, WorkspaceEntity] = {}

    @property
    def root(self) -> str:
        return self._root

    def contains(self, path: Any) -> bool:
        return _relative_within(self._root, path) is not None

    def add_entity(self, entity_id: str, name: str, path: str,
                   kind: EntityKind | str = EntityKind.FOLDER) -> WorkspaceEntity:
        relative = _relative_within(self._root, path)
        if relative is None:
            raise QueryError(
                f"workspace containment violated: {path!r} escapes {self._root!r}")
        if entity_id in self._entities:
            raise QueryError(f"duplicate workspace entity {entity_id!r}")
        entity = WorkspaceEntity(
            id=str(entity_id), name=str(name), path=relative,
            kind=_enum(EntityKind, kind))
        self._entities[entity.id] = entity
        return entity

    def workspace(self) -> Workspace:
        return Workspace(self._id, self._root, tuple(self._entities.values()))


@dataclass(frozen=True)
class SessionQueryDescriptor:
    kind: QueryKind
    workspace_id: str
    filters: tuple[tuple[str, str], ...]
    path_scope: str
    limit: int
    offset: int = 0
    fields: tuple[str, ...] = ()
    export_format: str = ""
    backend: str = "descriptor_only"
    io_performed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum(QueryKind, self.kind))
        object.__setattr__(self, "filters", tuple(self.filters))
        object.__setattr__(self, "fields", _tuple(self.fields))

    def describe(self) -> dict:
        return {
            "kind": self.kind.value, "workspace_id": self.workspace_id,
            "filters": [list(f) for f in self.filters],
            "path_scope": self.path_scope, "limit": self.limit,
            "offset": self.offset, "fields": list(self.fields),
            "export_format": self.export_format, "backend": self.backend,
            "sql": None, "io_performed": self.io_performed,
        }


class SessionQueryService:
    """D3.18: browse/search/export descriptors scoped to a workspace.

    No SQLite connection is opened — FTS5 is the planned backend, but this
    layer only produces query descriptors constrained by workspace containment.
    """

    def __init__(self, workspace: WorkspaceService) -> None:
        self._workspace = workspace

    def _scope(self, path: Any) -> str:
        if path is None or str(path) in ("", "."):
            return "."
        relative = _relative_within(self._workspace.root, path)
        if relative is None:
            raise QueryError(
                f"session query escaped workspace root {self._workspace.root!r}: "
                f"{path!r}")
        return relative

    def browse(self, path: Any = ".", *, limit: int = 50,
               offset: int = 0) -> SessionQueryDescriptor:
        return SessionQueryDescriptor(
            kind=QueryKind.BROWSE, workspace_id=self._workspace._id,
            filters=(("path_scope", self._scope(path)),),
            path_scope=self._scope(path), limit=int(limit), offset=int(offset),
            fields=("id", "title", "updated_at"),
        )

    def search(self, term: str, path: Any = ".", *, limit: int = 50,
               offset: int = 0) -> SessionQueryDescriptor:
        return SessionQueryDescriptor(
            kind=QueryKind.SEARCH, workspace_id=self._workspace._id,
            filters=(("term", str(term)), ("path_scope", self._scope(path))),
            path_scope=self._scope(path), limit=int(limit), offset=int(offset),
            fields=("id", "title", "snippet", "updated_at"),
        )

    def export(self, fmt: str = "json", path: Any = ".", *,
               limit: int = 1000) -> SessionQueryDescriptor:
        if fmt not in ("json", "jsonl", "csv"):
            raise QueryError(f"unsupported export format {fmt!r}")
        return SessionQueryDescriptor(
            kind=QueryKind.EXPORT, workspace_id=self._workspace._id,
            filters=(("path_scope", self._scope(path)),),
            path_scope=self._scope(path), limit=int(limit),
            fields=("id", "title", "events"), export_format=fmt,
        )


# ===========================================================================
# aggregate descriptor
# ===========================================================================
def all_p0_descriptors() -> dict[str, dict]:
    """One summary row per D3.x P0 feature owned by this module."""
    def row(feature_id: str, name: str, contract: Sequence[str], **extra) -> dict:
        return {
            "feature_id": feature_id, "name": name,
            "contract": list(contract), "layer": "descriptor_only",
            "io_performed": False, "network": False, "runtime_claimed": False,
            **extra,
        }

    return {
        "D3.1": row("D3.1", "capability-seam", tuple(r.value for r in SeamRole)),
        "D3.2": row("D3.2", "execution-world-provider",
                    tuple(k.value for k in ProviderKind)),
        "D3.6": row("D3.6", "commands", ("dispatch_without_model_turn",)),
        "D3.7": row("D3.7", "jobs", JOB_TOOLS),
        "D3.8": row("D3.8", "webhook-rule", ("trusted_rule", "signature", "confirmation")),
        "D3.9": row("D3.9", "backends", tuple(s.name for s in backend_services())),
        "D3.11": row("D3.11", "packages", PACKAGE_GROUPS),
        "D3.13": row("D3.13", "spill", ("threshold", "preview", "redaction")),
        "D3.14": row("D3.14", "guard", tuple(k.value for k in GuardKind)),
        "D3.18": row("D3.18", "workspace-session-query",
                     tuple(k.value for k in QueryKind)),
    }


__all__ = [
    "FEATURE_IDS", "SeamError", "ProviderError", "PackageError", "SpillError",
    "GuardError", "QueryError", "SeamRole", "ServiceDefinition",
    "ServiceProvider", "Consumer", "ServiceConsumer", "CapabilitySeam",
    "SeamRegistry", "seam_checklist", "ExecutionWorld", "ProviderKind",
    "ProviderConfig", "ProviderDescriptor", "resolve_provider", "swap_world",
    "resolve_world_bundle", "world_manifest", "provider_boundary_check",
    "ServiceDescriptor", "backend_services", "SandboxWrapDescriptor",
    "sandbox_wrap_argv", "CommandRegistration", "CommandService", "JOB_TOOLS",
    "job_tools", "WebhookRuleDescriptor", "webhook_rule",
    "PackageClassification", "PackageDescriptor", "PACKAGE_GROUPS",
    "classify_packages", "package_by_group", "package_policy", "SpillPolicy",
    "SpillDescriptor", "redact_preview", "plan_spill", "GuardKind",
    "GuardDecision", "GuardRegistration", "GuardVerdict", "GuardRegistry",
    "EntityKind", "QueryKind", "WorkspaceEntity", "Workspace",
    "WorkspaceService", "SessionQueryDescriptor", "SessionQueryService",
    "all_p0_descriptors",
]
