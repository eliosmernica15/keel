"""Provider configuration contracts — E6.1 / E6.5 / E6.8 / E6.10.

Additive, dependency-free (stdlib only) and entirely offline. This module
describes *configuration* for third-party model providers; it never opens a
socket, reads a credential value from disk, or sends a request. Existing modules
keep working unchanged and may adopt these types at their own boundaries — see
``master-plan-v6-provider-contracts-evidence.md`` for the integration seams.

Feature map
-----------
E6.1  :class:`SecretDescriptor`, :func:`describe_secret`,
       :func:`redact_descriptor`, :func:`credential_audit_record`.
       A secret value is accepted only by :func:`describe_secret`, used to
       compute a masked hint, and then discarded. No returned structure ever
       carries the value; audit records carry the credential name only.
E6.5  :class:`ProviderDescriptor`, :class:`ProviderRegistry`,
       :func:`search_catalog`. Installed third-party providers only: https
       endpoints, a four-protocol allowlist, a required model id, one protocol
       per provider, no bundled/paid entries, explicit user approval.
E6.8  :class:`ModelCapabilities`, :func:`effective_input_types`,
       :func:`without_image`, :func:`capability_warning`. Per-model input
       types, context window, max output, tool-call dialect and reasoning flag.
E6.10 :class:`CompatSwitches`, :class:`CompatProfile`,
       :func:`validate_switch`, :func:`adapt_request`. Route defaults with
       per-model field-by-field overrides; every unsupported feature is
       reported in :attr:`AdaptedRequest.adjustments` instead of being dropped
       silently.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field, fields, replace
from types import MappingProxyType
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

#: Schema version of the configuration contract defined here (not the product
#: version). Emitted in :func:`capability_report` so callers can detect drift.
SCHEMA_VERSION = "1.0"

#: Character used for every hidden code point in a masked credential hint.
MASK_CHAR = "\u2022"  # bullet dot

#: E6.1 — only these two storage sources are allowed.
SECRET_SOURCES = ("env", "settings")

#: E6.5 — the four wire protocols from the registry row. One per provider.
PROTOCOLS = (
    "openai-chat-completions",
    "openai-responses",
    "anthropic-messages",
    "gemini-api",
)

#: Capabilities an installed third-party catalog entry may advertise.
CATALOG_CAPABILITIES = (
    "text", "image", "tools", "streaming", "reasoning", "embeddings",
)

#: E6.8 — permitted model input types and tool-call dialect hints.
INPUT_TYPES = ("text", "image")
TOOL_DIALECT_HINTS = (
    "json", "xml", "hermes", "react", "mistral", "qwen", "deepseek", "llama",
    "provider-native", "none",
)

#: E6.8 — claims made in a config are never verified against a live endpoint.
UNVERIFIED_CLAIMS_WARNING = (
    "Capabilities and compatibility settings are claims about your endpoint; "
    "they are not verified by Keel."
)

#: E6.10 — canonical switch names, plus the plan's spelling as an alias.
SWITCH_NAMES = (
    "supports_developer_role",
    "max_tokens_field",
    "thinking_field",
    "streaming_format",
)
SWITCH_ALIASES = {"thinking_format": "thinking_field"}

#: Which protocol declares which switch. A switch is invalid for any protocol
#: that does not list it; validation reports the declaring protocols.
PROTOCOL_SWITCHES: dict[str, frozenset[str]] = {
    "openai-chat-completions": frozenset(SWITCH_NAMES),
    "openai-responses": frozenset(SWITCH_NAMES),
    "anthropic-messages": frozenset({
        "max_tokens_field", "thinking_field", "streaming_format",
    }),
    "gemini-api": frozenset({"max_tokens_field", "streaming_format"}),
}

STREAMING_FORMATS = ("sse", "anthropic-sse", "gemini-sse", "none")

#: Request keys this module knows how to translate (E6.10).
MAX_TOKEN_KEYS = ("max_tokens", "max_output_tokens", "max_completion_tokens")
THINKING_KEYS = ("thinking", "reasoning", "reasoning_effort", "thinking_config")

_PROVIDER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

class ProviderContractError(ValueError):
    """Raised when a provider configuration violates one of the contracts."""


# ---------------------------------------------------------------------------
# E6.1 — write-only credentials
# ---------------------------------------------------------------------------

def mask_secret(secret: str, *, identifier: str = "") -> str:
    """Return a masked preview of *secret* using Unicode code points.

    Rule (E6.1): show 5 leading and 4 trailing characters only when at least
    8 middle code points stay hidden (length >= 17); otherwise show all dots.
    The identifier prefix is included when supplied. The value itself is never
    returned in full.
    """
    if not isinstance(secret, str):
        raise TypeError("secret must be a string")
    if not isinstance(identifier, str):
        raise TypeError("identifier must be a string")
    chars = list(secret)  # code points, not UTF-8 bytes
    count = len(chars)
    if count >= 17:
        preview = "".join(chars[:5]) + MASK_CHAR * (count - 9) + "".join(chars[-4:])
    else:
        preview = MASK_CHAR * count
    return f"{identifier}: {preview}" if identifier else preview


@dataclass(frozen=True)
class SecretDescriptor:
    """Write-only credential descriptor — no field ever holds a secret value.

    ``name`` identifies the credential, ``source`` is ``env`` or ``settings``,
    ``masked_hint`` is the only displayable preview, and ``reference`` is the
    opaque pointer settings may persist.
    """

    name: str
    source: str
    masked_hint: str
    reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ProviderContractError("credential name must be a non-empty string")
        if self.source not in SECRET_SOURCES:
            raise ProviderContractError(
                f"unsupported credential source {self.source!r}; "
                f"valid sources: {', '.join(SECRET_SOURCES)}")
        if not isinstance(self.masked_hint, str) or not self.masked_hint:
            raise ProviderContractError("masked_hint must be a non-empty string")
        prefix = f"{self.name}: "
        if not self.masked_hint.startswith(prefix):
            raise ProviderContractError(
                "masked_hint must start with the identifier prefix "
                f"{prefix!r} and contain no secret value")
        if not isinstance(self.reference, str) or not self.reference:
            raise ProviderContractError("credential reference must be non-empty")

    def to_dict(self) -> dict:
        """Public view. Safe to serialize to a UI, a log or a settings file."""
        return {
            "name": self.name,
            "source": self.source,
            "masked_hint": self.masked_hint,
            "reference": self.reference,
        }


def describe_secret(
    name: str,
    secret: str,
    *,
    source: str = "env",
    reference: str | None = None,
) -> SecretDescriptor:
    """Consume a secret value and return only its descriptor.

    The value is used for the masked preview and is never stored: it is not a
    descriptor field, not logged, and not part of any returned mapping. This is
    the only entry point that accepts a raw secret.
    """
    if source not in SECRET_SOURCES:
        raise ProviderContractError(
            f"unsupported credential source {source!r}; "
            f"valid sources: {', '.join(SECRET_SOURCES)}")
    hint = mask_secret(secret, identifier=name)
    if reference is None:
        reference = (f"{source}:{name}" if source == "env"
                     else f"settings://credentials/{name}")
    return SecretDescriptor(name=name, source=source, masked_hint=hint,
                            reference=reference)


def redact_descriptor(descriptor: SecretDescriptor) -> dict:
    """Return the redacted, serializable view of a credential descriptor."""
    if not isinstance(descriptor, SecretDescriptor):
        raise TypeError("descriptor must be a SecretDescriptor")
    return descriptor.to_dict()


def credential_audit_record(descriptor: SecretDescriptor) -> dict:
    """Build an audit record that names the credential and nothing else."""
    if not isinstance(descriptor, SecretDescriptor):
        raise TypeError("descriptor must be a SecretDescriptor")
    return {"event": "credential.write", "name": descriptor.name}


def secret_appears_in(obj: Any, secret: str) -> bool:
    """Recursively test whether *secret* appears in any string in *obj*.

    A small helper for tests and for defensive boundary checks; it walks dict
    keys and values, sequences, sets and scalars without mutating anything.
    """
    if not isinstance(secret, str) or not secret:
        return False
    if isinstance(obj, str):
        return secret in obj
    if isinstance(obj, Mapping):
        return any(secret_appears_in(k, secret) or secret_appears_in(v, secret)
                   for k, v in obj.items())
    if isinstance(obj, (list, tuple, set, frozenset)):
        return any(secret_appears_in(item, secret) for item in obj)
    return False


# ---------------------------------------------------------------------------
# E6.5 — installed third-party provider picker
# ---------------------------------------------------------------------------

def _validate_endpoint(url: Any) -> None:
    if not isinstance(url, str):
        raise ProviderContractError("endpoint must be an https URL, got a non-string")
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.netloc or not parsed.hostname
            or parsed.username or parsed.password):
        raise ProviderContractError(
            f"endpoint must be an https URL with a host and no credentials, got {url!r}")


def validate_provider_descriptor(descriptor: "ProviderDescriptor") -> None:
    """Validate an installed third-party provider descriptor in place."""
    identifier = descriptor.id
    if not isinstance(identifier, str) or not _PROVIDER_ID_RE.match(identifier):
        raise ProviderContractError(
            f"provider id must be a permanent lowercase slug, got {identifier!r}")
    _validate_endpoint(descriptor.base_url)
    protocol = descriptor.protocol
    if not isinstance(protocol, str) or protocol not in PROTOCOLS:
        valid = ", ".join(PROTOCOLS)
        raise ProviderContractError(
            f"unknown protocol {protocol!r}; valid protocols: {valid}")
    if not isinstance(descriptor.models, tuple) or not descriptor.models:
        raise ProviderContractError("provider must declare at least one model id")
    for model_id in descriptor.models:
        if not isinstance(model_id, str) or not model_id.strip():
            raise ProviderContractError("provider model ids must be non-empty strings")
    if not descriptor.capabilities <= frozenset(CATALOG_CAPABILITIES):
        unknown = sorted(descriptor.capabilities - frozenset(CATALOG_CAPABILITIES))
        valid = ", ".join(CATALOG_CAPABILITIES)
        raise ProviderContractError(
            f"unknown catalog capabilities {unknown}; valid capabilities: {valid}")
    if descriptor.bundled:
        raise ProviderContractError("bundled providers are not selectable")
    if descriptor.paid:
        raise ProviderContractError("paid providers are not selectable")
    if descriptor.credential is not None and not isinstance(
            descriptor.credential, SecretDescriptor):
        raise ProviderContractError("credential must be a SecretDescriptor or None")
    if not isinstance(descriptor.user_approved, bool):
        raise ProviderContractError("user_approved must be a boolean")


@dataclass(frozen=True)
class ProviderDescriptor:
    """One installed third-party provider (E6.5).

    ``id`` is permanent: rename is add-new + delete-old. ``protocol`` is a
    single value, so a gateway serving two protocols must be registered twice.
    """
    id: str
    base_url: str
    protocol: str
    models: tuple[str, ...]
    credential: SecretDescriptor | None = None
    capabilities: frozenset[str] = frozenset()
    user_approved: bool = False
    bundled: bool = False
    paid: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "models", tuple(self.models or ()))
        object.__setattr__(self, "capabilities", frozenset(self.capabilities or ()))
        validate_provider_descriptor(self)

    def to_dict(self) -> dict:
        """Serializable view; only the credential *descriptor* is included."""
        return {
            "id": self.id,
            "base_url": self.base_url,
            "protocol": self.protocol,
            "models": list(self.models),
            "capabilities": sorted(self.capabilities),
            "credential": (self.credential.to_dict()
                           if self.credential is not None else None),
            "user_approved": self.user_approved,
        }


def provider_from_dict(data: Mapping) -> ProviderDescriptor:
    """Build a :class:`ProviderDescriptor` from an installed-catalog mapping."""
    if not isinstance(data, Mapping):
        raise TypeError("provider data must be a mapping")
    credential = data.get("credential")
    if isinstance(credential, Mapping):
        credential = SecretDescriptor(
            name=credential["name"],
            source=credential["source"],
            masked_hint=credential["masked_hint"],
            reference=credential["reference"],
        )
    return ProviderDescriptor(
        id=data.get("id", ""),
        base_url=data.get("base_url", ""),
        protocol=data.get("protocol", ""),
        models=tuple(data.get("models", ())),
        credential=credential,
        capabilities=frozenset(data.get("capabilities", ())),
        user_approved=bool(data.get("user_approved", False)),
        bundled=bool(data.get("bundled", False)),
        paid=bool(data.get("paid", False)),
    )


def search_catalog(
    entries: Iterable[Any],
    *,
    capability: str | None = None,
    protocol: str | None = None,
) -> tuple[Any, ...]:
    """Search an installed catalog by capability and/or protocol.

    Bundled and paid entries are always excluded, even if a caller placed them
    in the catalog. Entries may be :class:`ProviderDescriptor` instances or any
    object exposing the same attributes (e.g. a catalog record).
    """
    if capability is not None and capability not in CATALOG_CAPABILITIES:
        valid = ", ".join(CATALOG_CAPABILITIES)
        raise ProviderContractError(
            f"unknown catalog capability {capability!r}; valid capabilities: {valid}")
    if protocol is not None and protocol not in PROTOCOLS:
        valid = ", ".join(PROTOCOLS)
        raise ProviderContractError(
            f"unknown protocol {protocol!r}; valid protocols: {valid}")
    found = []
    for entry in entries:
        if getattr(entry, "bundled", False) or getattr(entry, "paid", False):
            continue
        if capability is not None and capability not in getattr(
                entry, "capabilities", ()):
            continue
        if protocol is not None and getattr(entry, "protocol", None) != protocol:
            continue
        found.append(entry)
    return tuple(found)


class ProviderRegistry:
    """Additive in-memory registry; no rename operation by design (E6.5)."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderDescriptor] = {}

    def add(self, descriptor: ProviderDescriptor) -> ProviderDescriptor:
        if not isinstance(descriptor, ProviderDescriptor):
            raise TypeError("descriptor must be a ProviderDescriptor")
        validate_provider_descriptor(descriptor)
        if not descriptor.user_approved:
            raise ProviderContractError(
                f"explicit user approval is required to register {descriptor.id!r}")
        if descriptor.id in self._providers:
            raise ProviderContractError(
                f"provider {descriptor.id!r} is already registered")
        self._providers[descriptor.id] = descriptor
        return descriptor

    def remove(self, identifier: str) -> ProviderDescriptor:
        if identifier not in self._providers:
            raise ProviderContractError(f"unknown provider {identifier!r}")
        return self._providers.pop(identifier)

    def get(self, identifier: str) -> ProviderDescriptor:
        if identifier not in self._providers:
            raise ProviderContractError(f"unknown provider {identifier!r}")
        return self._providers[identifier]

    def list(self) -> tuple[ProviderDescriptor, ...]:
        return tuple(self._providers.values())

    def search(self, **criteria: Any) -> tuple[ProviderDescriptor, ...]:
        return search_catalog(self._providers.values(), **criteria)


# ---------------------------------------------------------------------------
# E6.8 — per-model capabilities
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelCapabilities:
    """Typed per-model capability claims (E6.8).

    Image limits are only legal for image-capable models; :func:`without_image`
    clears them when image support is removed. All values are caller claims —
    :func:`capability_warning` must be shown wherever they are edited.
    """
    model_id: str
    input_types: frozenset[str] = frozenset({"text"})
    context_window: int = 8192
    max_output: int = 2048
    tool_call_dialect: str = "none"
    supports_reasoning: bool = False
    max_images: int | None = None
    image_max_bytes: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ProviderContractError("model_id must be a non-empty string")
        object.__setattr__(self, "input_types", frozenset(self.input_types))
        if not self.input_types or not self.input_types <= frozenset(INPUT_TYPES):
            valid = ", ".join(INPUT_TYPES)
            raise ProviderContractError(
                f"input_types must be a non-empty subset of: {valid}")
        for name in ("context_window", "max_output"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ProviderContractError(f"{name} must be a positive integer")
        if self.max_output > self.context_window:
            raise ProviderContractError(
                "max_output must not exceed context_window")
        if self.tool_call_dialect not in TOOL_DIALECT_HINTS:
            valid = ", ".join(TOOL_DIALECT_HINTS)
            raise ProviderContractError(
                f"unknown tool-call dialect {self.tool_call_dialect!r}; "
                f"valid dialects: {valid}")
        if not isinstance(self.supports_reasoning, bool):
            raise ProviderContractError("supports_reasoning must be a boolean")
        for name in ("max_images", "image_max_bytes"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ProviderContractError(f"{name} must be a positive integer or None")
            if "image" not in self.input_types:
                raise ProviderContractError(
                    f"{name} requires 'image' in input_types")

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "model_id": self.model_id,
            "input_types": sorted(self.input_types),
            "context_window": self.context_window,
            "max_output": self.max_output,
            "tool_call_dialect": self.tool_call_dialect,
            "supports_reasoning": self.supports_reasoning,
            "max_images": self.max_images,
            "image_max_bytes": self.image_max_bytes,
            "warning": UNVERIFIED_CLAIMS_WARNING,
        }


def merge_input_types(*sources: Iterable[str]) -> frozenset[str]:
    """Union input types; a fallback can never remove a type another source knows."""
    merged: set[str] = set()
    for source in sources:
        for value in source:
            if value not in INPUT_TYPES:
                valid = ", ".join(INPUT_TYPES)
                raise ProviderContractError(
                    f"unknown input type {value!r}; valid input types: {valid}")
            merged.add(value)
    if not merged:
        raise ProviderContractError("at least one input type is required")
    return frozenset(merged)


def effective_input_types(
    capabilities: ModelCapabilities,
    *,
    route_default: Iterable[str] = (),
    catalog_types: Iterable[str] = (),
) -> frozenset[str]:
    """Resolve route default + catalog knowledge + per-model override.

    The union preserves image support whenever the route or the installed
    catalog declares it, even if a per-model override lists text only.
    """
    return merge_input_types(route_default, catalog_types,
                             capabilities.input_types)


def without_image(capabilities: ModelCapabilities) -> ModelCapabilities:
    """Return a copy with image input removed and all image limits cleared."""
    return replace(capabilities, input_types=frozenset({"text"}),
                   max_images=None, image_max_bytes=None)


def capability_warning() -> str:
    """The mandatory 'claims are not verified' warning for capability editors."""
    return UNVERIFIED_CLAIMS_WARNING


def capability_report(capabilities: ModelCapabilities) -> dict:
    """Serializable capability view including the unverified-claims warning."""
    if not isinstance(capabilities, ModelCapabilities):
        raise TypeError("capabilities must be a ModelCapabilities")
    return capabilities.to_dict()


# ---------------------------------------------------------------------------
# E6.10 — request-compatibility switches
# ---------------------------------------------------------------------------

def _validate_switch_value(name: str, value: Any) -> None:
    """Validate a non-None switch value (without protocol applicability)."""
    if name == "supports_developer_role":
        if not isinstance(value, bool):
            raise ProviderContractError(
                f"switch {name!r} must be a boolean")
        return
    if not isinstance(value, str) or not value:
        raise ProviderContractError(f"switch {name!r} must not be empty")
    if name in ("max_tokens_field", "thinking_field"):
        if not _FIELD_NAME_RE.match(value):
            raise ProviderContractError(
                f"switch {name!r} must be a field name matching "
                r"[A-Za-z_][A-Za-z0-9_]*, got " + repr(value))
        return
    if name == "streaming_format" and value not in STREAMING_FORMATS:
        valid = ", ".join(STREAMING_FORMATS)
        raise ProviderContractError(
            f"unknown streaming_format {value!r}; valid formats: {valid}")


def validate_switch(
    name: str,
    value: Any,
    *,
    protocol: str | None = None,
) -> str:
    """Validate a switch, returning its canonical name.

    Refuses empty values, unknown names (listing valid names) and switches a
    protocol does not declare (listing that protocol's valid switches).
    """
    canonical = SWITCH_ALIASES.get(name, name)
    if canonical not in SWITCH_NAMES:
        valid = ", ".join(SWITCH_NAMES)
        raise ProviderContractError(
            f"unknown switch name {name!r}; valid switch names: {valid}")
    _validate_switch_value(canonical, value)
    if protocol is not None:
        if protocol not in PROTOCOLS:
            valid = ", ".join(PROTOCOLS)
            raise ProviderContractError(
                f"unknown protocol {protocol!r}; valid protocols: {valid}")
        if canonical not in PROTOCOL_SWITCHES[protocol]:
            valid = ", ".join(sorted(PROTOCOL_SWITCHES[protocol]))
            raise ProviderContractError(
                f"switch {name!r} is not valid for protocol {protocol!r}; "
                f"valid switches for {protocol}: {valid}")
    return canonical


@dataclass(frozen=True)
class CompatSwitches:
    """Field-by-field request compatibility switches (E6.10).

    ``None`` means 'unset' — it is a valid override value that inherits the
    route default. An empty string is never valid.
    """
    supports_developer_role: bool | None = None
    max_tokens_field: str | None = None
    thinking_field: str | None = None
    streaming_format: str | None = None

    def __post_init__(self) -> None:
        for switch in fields(self):
            value = getattr(self, switch.name)
            if value is not None:
                _validate_switch_value(switch.name, value)

    def to_dict(self) -> dict:
        return {switch.name: getattr(self, switch.name) for switch in fields(self)}


def resolve_switches(
    base: CompatSwitches | None,
    override: CompatSwitches | None,
    *,
    protocol: str | None = None,
) -> CompatSwitches:
    """Merge two switch sets field by field; only non-None overrides replace."""
    for candidate in (base, override):
        if candidate is not None and not isinstance(candidate, CompatSwitches):
            raise TypeError("switches must be CompatSwitches or None")
    resolved: dict[str, Any] = {}
    for name in SWITCH_NAMES:
        value = getattr(override, name) if override is not None else None
        if value is None and base is not None:
            value = getattr(base, name)
        if value is not None:
            validate_switch(name, value, protocol=protocol)
        resolved[name] = value
    return CompatSwitches(**resolved)


@dataclass(frozen=True)
class CompatProfile:
    """Route-level compat profile with per-model field-by-field overrides."""
    protocol: str
    defaults: CompatSwitches = field(default_factory=CompatSwitches)
    overrides: Mapping[str, CompatSwitches] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.protocol not in PROTOCOLS:
            valid = ", ".join(PROTOCOLS)
            raise ProviderContractError(
                f"unknown protocol {self.protocol!r}; valid protocols: {valid}")
        if not isinstance(self.defaults, CompatSwitches):
            raise TypeError("defaults must be a CompatSwitches")
        object.__setattr__(self, "overrides", MappingProxyType(dict(self.overrides)))
        for name in SWITCH_NAMES:
            value = getattr(self.defaults, name)
            if value is not None:
                validate_switch(name, value, protocol=self.protocol)
        for model_id, switches in self.overrides.items():
            if not isinstance(model_id, str) or not model_id.strip():
                raise ProviderContractError("override model_id must be non-empty")
            if not isinstance(switches, CompatSwitches):
                raise TypeError("per-model overrides must be CompatSwitches")
            for name in SWITCH_NAMES:
                value = getattr(switches, name)
                if value is not None:
                    validate_switch(name, value, protocol=self.protocol)

    def for_model(self, model_id: str) -> CompatSwitches:
        """Resolve the switches for *model_id* against route defaults."""
        return resolve_switches(self.defaults, self.overrides.get(model_id),
                                protocol=self.protocol)

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "defaults": self.defaults.to_dict(),
            "overrides": {model: switches.to_dict()
                          for model, switches in self.overrides.items()},
        }


@dataclass(frozen=True)
class AdaptedRequest:
    """Pure result of :func:`adapt_request`.

    ``request`` is a deep copy of the input with only documented translations.
    ``adjustments`` is the honest, human-readable list of every change or
    degradation; an unsupported feature is never silently removed.
    """
    request: dict
    adjustments: tuple[str, ...]


def _contains_image(obj: Any) -> bool:
    if isinstance(obj, Mapping):
        if ("image_url" in obj or "image" in obj
                or obj.get("type") in ("image", "image_url", "input_image")):
            return True
        return any(_contains_image(value) for value in obj.values())
    if isinstance(obj, (list, tuple, set, frozenset)):
        return any(_contains_image(item) for item in obj)
    return False


def image_preflight_message(capabilities: ModelCapabilities,
                            request: Mapping) -> str | None:
    """Return a clear refusal message when image input is not supported."""
    if not isinstance(capabilities, ModelCapabilities):
        raise TypeError("capabilities must be a ModelCapabilities")
    if ("image" not in capabilities.input_types and _contains_image(request)):
        return (f"Model {capabilities.model_id} does not accept image input; "
                "remove image content before sending.")
    return None


def adapt_request(
    capabilities: ModelCapabilities,
    request: Mapping,
    *,
    switches: CompatSwitches | None = None,
    profile: CompatProfile | None = None,
    model_id: str | None = None,
) -> AdaptedRequest:
    """Translate a request for a provider dialect without losing information.

    Pure: *request* is deep-copied and never mutated. When a profile is given
    it takes precedence and is resolved for ``model_id`` (or
    ``capabilities.model_id``). Every translation or degradation is described
    in :attr:`AdaptedRequest.adjustments`; unsupported thinking parameters are
    removed with a note, streaming can be disabled with a note, and image
    content is preserved with a preflight refusal note rather than dropped.
    """
    if not isinstance(capabilities, ModelCapabilities):
        raise TypeError("capabilities must be a ModelCapabilities")
    if not isinstance(request, Mapping):
        raise TypeError("request must be a mapping")
    if profile is not None:
        if not isinstance(profile, CompatProfile):
            raise TypeError("profile must be a CompatProfile")
        switches = profile.for_model(model_id or capabilities.model_id)
    elif switches is None:
        switches = CompatSwitches()
    elif not isinstance(switches, CompatSwitches):
        raise TypeError("switches must be a CompatSwitches or None")

    adapted = copy.deepcopy(dict(request))
    notes: list[str] = []

    # --- max-token field + capability clamp ---------------------------------
    target = switches.max_tokens_field
    present = [key for key in MAX_TOKEN_KEYS if key in adapted]
    if present:
        raw = adapted[present[0]]
        for key in present:
            adapted.pop(key)
        adapted[target or present[0]] = raw
        if target and target != present[0]:
            notes.append(f"renamed {present[0]} to {target} for this protocol")
        value_key = target or present[0]
        value = adapted[value_key]
        if (isinstance(value, int) and not isinstance(value, bool)
                and value > capabilities.max_output):
            adapted[value_key] = capabilities.max_output
            notes.append(
                f"clamped {value_key} to model max output {capabilities.max_output}")

    # --- developer role ------------------------------------------------------
    if switches.supports_developer_role is not True:
        messages = adapted.get("messages")
        if isinstance(messages, list):
            changed = False
            for message in messages:
                if isinstance(message, dict) and message.get("role") == "developer":
                    message["role"] = "system"
                    changed = True
            if changed:
                notes.append(
                    "developer role is not supported by this protocol; "
                    "mapped to system")

    # --- thinking field ------------------------------------------------------
    found_thinking = [key for key in THINKING_KEYS if key in adapted]
    for key in found_thinking:
        value = adapted.pop(key)
        if switches.thinking_field is not None:
            adapted[switches.thinking_field] = value
            if switches.thinking_field != key:
                notes.append(
                    f"renamed thinking field {key} to {switches.thinking_field}")
        else:
            notes.append(
                "thinking parameter removed: protocol declares no thinking field")
    if found_thinking and not capabilities.supports_reasoning:
        notes.append(
            "model does not declare reasoning support; thinking may be ignored")

    # --- streaming format ----------------------------------------------------
    if adapted.get("stream") is True:
        streaming = switches.streaming_format
        if streaming == "none":
            adapted["stream"] = False
            notes.append("streaming disabled: protocol declares no streaming format")
        elif streaming is not None and streaming != "sse":
            notes.append(
                f"streaming format {streaming} requires caller-side translation; "
                "request left unchanged")

    # --- image input: preserve and report, never drop ------------------------
    if _contains_image(adapted) and "image" not in capabilities.input_types:
        notes.append(
            "image content present but model declares no image input; "
            "refuse before sending")

    return AdaptedRequest(request=adapted, adjustments=tuple(notes))
