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
import json
import math
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
    # Control characters and whitespace must never reach a URL/header builder.
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise ProviderContractError(
            "endpoint must be an https URL without whitespace or control characters")
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.netloc or not parsed.hostname
            or parsed.username or parsed.password or parsed.fragment):
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


def _strict_bool(data: Mapping, key: str, default: bool = False) -> bool:
    """Read a boolean field without coercing strings/ints into approvals.

    A JSON setting such as ``"user_approved": "false"`` must never become a
    True approval flag; fail closed with a clear diagnostic instead.
    """
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ProviderContractError(f"{key} must be a boolean")
    return value


def provider_from_dict(data: Mapping) -> ProviderDescriptor:
    """Build a :class:`ProviderDescriptor` from an installed-catalog mapping."""
    if not isinstance(data, Mapping):
        raise TypeError("provider data must be a mapping")
    credential = data.get("credential")
    if isinstance(credential, Mapping):
        try:
            credential = SecretDescriptor(
                name=credential["name"],
                source=credential["source"],
                masked_hint=credential["masked_hint"],
                reference=credential["reference"],
            )
        except KeyError as exc:
            raise ProviderContractError(
                f"credential is missing required field {exc.args[0]!r}") from None
    return ProviderDescriptor(
        id=data.get("id", ""),
        base_url=data.get("base_url", ""),
        protocol=data.get("protocol", ""),
        models=tuple(data.get("models", ())),
        credential=credential,
        capabilities=frozenset(data.get("capabilities", ())),
        user_approved=_strict_bool(data, "user_approved"),
        bundled=_strict_bool(data, "bundled"),
        paid=_strict_bool(data, "paid"),
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


# ---------------------------------------------------------------------------
# Production hardening — offline runtime policy (E6.11)
# ---------------------------------------------------------------------------
# Everything below is pure policy over an *injected* transport. No socket is
# ever opened here, no credential value is read, and no provider is contacted.
# The transport callable is supplied by the caller (production supplies its
# own; tests supply scripted failures). This makes error classification,
# retries, cancellation, streaming, usage accounting and fallback discipline
# testable without a live endpoint, a key, or any paid usage.

CATEGORY_AUTH = "authentication_failed"
CATEGORY_ORG = "organization_not_allowed"
CATEGORY_ACCOUNT = "account_on_hold"
CATEGORY_BILLING = "billing_error"
CATEGORY_RATE_LIMIT = "rate_limit"
CATEGORY_OVERLOADED = "overloaded"
CATEGORY_INVALID = "invalid_request"
CATEGORY_MODEL_NOT_FOUND = "model_not_found"
CATEGORY_SERVER = "server_error"
CATEGORY_MAX_OUTPUT = "max_output_tokens"
CATEGORY_CREDENTIAL = "credential_error"
CATEGORY_CONTEXT_LIMIT = "context_limit_exceeded"
CATEGORY_TIMEOUT = "timeout"
CATEGORY_CONNECTION = "connection_error"
CATEGORY_UNAVAILABLE = "provider_unavailable"
CATEGORY_MALFORMED = "malformed_response"
CATEGORY_CANCELLED = "cancelled"
CATEGORY_HTTP = "http_error"
CATEGORY_UNKNOWN = "unknown"

#: Complete failure taxonomy. Security/permission failures are deliberately
#: non-retryable so a bad key can never be replayed (and never billed twice).
CATEGORIES = frozenset({
    CATEGORY_AUTH, CATEGORY_ORG, CATEGORY_ACCOUNT, CATEGORY_BILLING,
    CATEGORY_RATE_LIMIT, CATEGORY_OVERLOADED, CATEGORY_INVALID,
    CATEGORY_MODEL_NOT_FOUND, CATEGORY_SERVER, CATEGORY_MAX_OUTPUT,
    CATEGORY_CREDENTIAL, CATEGORY_CONTEXT_LIMIT, CATEGORY_TIMEOUT,
    CATEGORY_CONNECTION, CATEGORY_UNAVAILABLE, CATEGORY_MALFORMED,
    CATEGORY_CANCELLED, CATEGORY_HTTP, CATEGORY_UNKNOWN,
})

#: Only transport/capacity failures are replayed. A replay of an auth,
#: billing, invalid-request or context-limit failure would be repeated paid
#: usage with no chance of success.
RETRYABLE_CATEGORIES = frozenset({
    CATEGORY_TIMEOUT, CATEGORY_CONNECTION, CATEGORY_RATE_LIMIT,
    CATEGORY_OVERLOADED, CATEGORY_SERVER, CATEGORY_UNAVAILABLE,
})

#: Fallback is a subset of retryable failures. It is applied *only* when the
#: caller explicitly configured fallback providers.
FALLBACK_CATEGORIES = frozenset(RETRYABLE_CATEGORIES)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.25
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_BACKOFF_SECONDS = 30.0
MAX_RETRY_AFTER_SECONDS = 60.0
MAX_ERROR_MESSAGE_CHARS = 512
MAX_EVENT_TEXT_CHARS = 4096

_CONTEXT_MARKERS = (
    "context_length", "context length", "context window", "maximum context",
    "max context", "prompt is too long", "context exceeded", "token limit",
)
_RATE_MARKERS = ("rate_limit", "rate limit", "too_many_requests", "quota")
_OVERLOAD_MARKERS = ("overloaded", "overload", "capacity")
_AUTH_MARKERS = ("authentication", "unauthorized", "permission", "invalid_api_key")
_CREDENTIAL_MARKERS = ("credential", "api_key", "api key", "secret")
_BILLING_MARKERS = ("billing", "payment_required", "credit")
_MODEL_MARKERS = ("model_not_found", "model not found", "unknown_model")

_TOKEN_PATTERNS = (
    re.compile(r"\bBearer\s+(?!Bearer\b)[A-Za-z0-9._~+/=-]{6,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{16,}\b"),
)
_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_CREDENTIAL_KEYS = frozenset({
    "api_key", "apikey", "api-key", "x-api-key", "authorization", "auth",
    "secret", "password", "credential", "credentials", "bearer",
    "private_key", "access_token", "refresh_token", "client_secret",
})
_CREDENTIAL_KEY_FRAGMENTS = (
    "api_key", "apikey", "api-key", "secret", "password", "credential",
    "authorization", "bearer", "private_key", "access_token",
)


# --- redaction -------------------------------------------------------------

def _scrub(text: str, secrets: Iterable[str] = ()) -> str:
    """Remove known secret values and common token shapes from *text*."""
    result = str(text)
    try:
        candidates = list(secrets)
    except TypeError:
        candidates = []
    for secret in sorted((s for s in candidates if isinstance(s, str) and s),
                         key=len, reverse=True):
        result = result.replace(secret, "[REDACTED]")
    for pattern in _TOKEN_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def redact_message(message: Any, secrets: Iterable[str] = ()) -> str:
    """Bounded, redacted error text safe for logs, results and the UI."""
    safe = _scrub("" if message is None else str(message), secrets)
    if len(safe) > MAX_ERROR_MESSAGE_CHARS:
        safe = safe[:MAX_ERROR_MESSAGE_CHARS] + "...[truncated]"
    return safe


def safe_code(value: Any) -> str | None:
    """Keep only simple provider codes/types; never echo arbitrary payloads."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if _SAFE_CODE_RE.match(stripped) else None


def _is_credential_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.strip().lower()
    return (lowered in _CREDENTIAL_KEYS
            or any(fragment in lowered for fragment in _CREDENTIAL_KEY_FRAGMENTS))


def _sanitize_value(value: Any, secrets: Iterable[str] = (),
                    *, _depth: int = 0, cap: int | None = None,
                    drop_credentials: bool = False) -> Any:
    """Redact strings in a nested structure without mutating the original."""
    if _depth > 8:
        return "[truncated]"
    if isinstance(value, str):
        safe = _scrub(value, secrets)
        return safe[:cap] if cap is not None else safe
    if isinstance(value, Mapping):
        return {
            k: _sanitize_value(v, secrets, _depth=_depth + 1, cap=cap,
                               drop_credentials=drop_credentials)
            for k, v in value.items()
            if not (drop_credentials and _is_credential_key(k))
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_sanitize_value(item, secrets, _depth=_depth + 1, cap=cap,
                                 drop_credentials=drop_credentials)
                 for item in value]
        return tuple(items) if isinstance(value, tuple) else items
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _scrub(str(value), secrets)


# --- failures and classification -------------------------------------------

@dataclass(frozen=True)
class ProviderFailure:
    """Normalized, redacted failure. Holds no exception or raw payload."""

    category: str
    message: str
    status: int | None = None
    retryable: bool = False
    retry_after: float | None = None
    code: str | None = None

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            object.__setattr__(self, "category", CATEGORY_UNKNOWN)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "message": self.message,
            "status": self.status,
            "retryable": bool(self.retryable),
            "retry_after": self.retry_after,
            "code": self.code,
        }


class ProviderTransportError(Exception):
    """Raised by this policy (or by an injected transport) for a known failure."""

    def __init__(self, message: str = "provider transport failure", *,
                 category: str = CATEGORY_UNKNOWN, status: int | None = None,
                 retryable: bool | None = None, retry_after: float | None = None,
                 code: str | None = None):
        super().__init__(message)
        self.message_text = str(message)
        self.category = category if category in CATEGORIES else CATEGORY_UNKNOWN
        self.status = status if (isinstance(status, int) and not isinstance(status, bool)) else None
        self.retryable = (category in RETRYABLE_CATEGORIES
                          if retryable is None else bool(retryable))
        self.retry_after = retry_after
        self.code = safe_code(code)

    @classmethod
    def from_failure(cls, failure: ProviderFailure) -> "ProviderTransportError":
        return cls(failure.message, category=failure.category, status=failure.status,
                   retryable=failure.retryable, retry_after=failure.retry_after,
                   code=failure.code)


class ProviderCancelled(Exception):
    """Operator cancellation; a normal stop, never a provider failure."""


def extract_retry_after(payload: Any = None, headers: Any = None) -> float | None:
    """Read a bounded, numeric retry delay from a payload or response headers."""

    def coerce(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            try:
                number = float(value.strip())
            except ValueError:
                return None
        else:
            return None
        if math.isnan(number) or math.isinf(number):
            return None
        return number

    candidates: list[tuple[Any, float]] = []
    if isinstance(headers, Mapping):
        for key, value in headers.items():
            if isinstance(key, str) and key.lower() == "retry-after":
                candidates.append((value, 1.0))
    if isinstance(payload, Mapping):
        candidates.extend([(payload.get("retry_after"), 1.0),
                           (payload.get("retry_after_ms"), 0.001)])
        error = payload.get("error")
        if isinstance(error, Mapping):
            candidates.extend([(error.get("retry_after"), 1.0),
                               (error.get("retry_after_ms"), 0.001)])
    for value, multiplier in candidates:
        parsed = coerce(value)
        if parsed is not None:
            return min(max(parsed * multiplier, 0.0), MAX_RETRY_AFTER_SECONDS)
    return None


def classify_payload(payload: Any, *, status: int = 200,
                     secrets: Iterable[str] = ()) -> ProviderFailure | None:
    """Recognize provider error bodies. Returns None for ordinary responses."""
    if not isinstance(payload, Mapping):
        return None
    error = payload.get("error")
    if isinstance(error, str):
        code = None
        signals = error.lower()
    elif isinstance(error, Mapping):
        code = safe_code(error.get("code") or error.get("type")
                         or error.get("id"))
        signals = " ".join(
            str(error.get(key, "")).lower()
            for key in ("type", "code", "id", "message"))
    else:
        return None
    if any(marker in signals for marker in _CONTEXT_MARKERS):
        category = CATEGORY_CONTEXT_LIMIT
    elif any(marker in signals for marker in _RATE_MARKERS):
        category = CATEGORY_RATE_LIMIT
    elif any(marker in signals for marker in _OVERLOAD_MARKERS):
        category = CATEGORY_OVERLOADED
    elif any(marker in signals for marker in _CREDENTIAL_MARKERS):
        category = CATEGORY_CREDENTIAL
    elif any(marker in signals for marker in _AUTH_MARKERS):
        category = CATEGORY_AUTH
    elif any(marker in signals for marker in _BILLING_MARKERS):
        category = CATEGORY_BILLING
    elif any(marker in signals for marker in _MODEL_MARKERS):
        category = CATEGORY_MODEL_NOT_FOUND
    elif "server" in signals or "internal error" in signals:
        category = CATEGORY_SERVER
    else:
        return None
    shown_status = status if (isinstance(status, int) and status >= 400) else None
    prefix = f"http {shown_status} " if shown_status is not None else ""
    return ProviderFailure(
        category=category,
        message=redact_message(f"{prefix}{category}", secrets),
        status=shown_status,
        retryable=category in RETRYABLE_CATEGORIES,
        retry_after=extract_retry_after(payload),
        code=code,
    )


def classify_status(status: Any, *, payload: Any = None, headers: Any = None,
                    secrets: Iterable[str] = ()) -> ProviderFailure:
    """Map an HTTP status to a conservative (category, retryable) pair."""
    if not isinstance(status, int) or isinstance(status, bool):
        return ProviderFailure(CATEGORY_UNKNOWN, "http error without a status",
                               None, False)
    from_payload = classify_payload(payload, status=status, secrets=secrets)
    if from_payload is not None:
        if from_payload.retry_after is None:
            object.__setattr__(from_payload, "retry_after",
                               extract_retry_after(None, headers))
        return from_payload
    if status == 401:
        category = CATEGORY_AUTH
    elif status == 402:
        category = CATEGORY_BILLING
    elif status == 403:
        category = CATEGORY_ORG
    elif status == 404:
        category = CATEGORY_MODEL_NOT_FOUND
    elif status in (408, 429):
        category = CATEGORY_RATE_LIMIT
    elif status in (400, 409, 422):
        category = CATEGORY_INVALID
    elif status == 451:
        category = CATEGORY_ACCOUNT
    elif status in (503, 504):
        category = CATEGORY_UNAVAILABLE
    elif status >= 500:
        category = CATEGORY_SERVER
    else:
        category = CATEGORY_HTTP
    return ProviderFailure(
        category=category,
        message=redact_message(f"http {status} {category}", secrets),
        status=status,
        retryable=category in RETRYABLE_CATEGORIES,
        retry_after=extract_retry_after(payload, headers),
        code=safe_code(payload.get("error", {}).get("code"))
        if isinstance(payload, Mapping) and isinstance(payload.get("error"), Mapping)
        else None,
    )


def classify_exception(exc: Any, *, secrets: Iterable[str] = ()) -> ProviderFailure:
    """Classify any injected failure without ever echoing the raw exception."""
    # The policy layer has its own cancellation signal, but a production
    # transport may surface the adapter-level one instead (see
    # keel.providers.base.TurnCancelled). Both are normal operator stops, never
    # provider failures; a misclassification here would make a user-initiated
    # stop look like a retryable error. Import lazily to keep this module
    # dependency-free at import time.
    try:
        from .providers.base import TurnCancelled
    except ImportError:  # pragma: no cover - the runtime package is always present
        TurnCancelled = ()  # type: ignore[assignment,misc]
    if isinstance(exc, (ProviderCancelled, TurnCancelled)):
        return ProviderFailure(CATEGORY_CANCELLED, "operation cancelled", None, False)
    if isinstance(exc, ProviderTransportError):
        return ProviderFailure(
            category=exc.category,
            message=redact_message(exc.message_text, secrets),
            status=exc.status,
            retryable=exc.retryable,
            retry_after=exc.retry_after,
            code=exc.code,
        )
    if isinstance(exc, TimeoutError):
        return ProviderFailure(CATEGORY_TIMEOUT, redact_message(str(exc), secrets),
                               None, True)
    if isinstance(exc, (ConnectionError, OSError)):
        return ProviderFailure(CATEGORY_CONNECTION,
                               redact_message(str(exc), secrets), None, True)
    if isinstance(exc, json.JSONDecodeError):
        return ProviderFailure(CATEGORY_MALFORMED, "response was not valid JSON",
                               None, False)
    return ProviderFailure(CATEGORY_UNKNOWN, redact_message(str(exc), secrets),
                           None, False)


# --- response and usage normalization --------------------------------------

@dataclass(frozen=True)
class UsageMetadata:
    """Provider-agnostic usage record; unknown/malformed counts become zero."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    reasoning_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _first_count(*sources: Any, keys: tuple[str, ...]) -> int:
    for source in sources:
        if isinstance(source, Mapping):
            for key in keys:
                if key in source:
                    return _count(source[key])
    return 0


def usage_from_payload(payload: Any) -> UsageMetadata:
    """Read usage from OpenAI, Anthropic or Gemini response shapes."""
    if not isinstance(payload, Mapping):
        return UsageMetadata()
    if "usage" in payload or "usageMetadata" in payload:
        usage = payload.get("usage") or payload.get("usageMetadata") or {}
    else:
        # A streamed usage event carries the usage mapping directly.
        usage = payload
    details_in = usage.get("prompt_tokens_details") if isinstance(usage, Mapping) else {}
    details_out = (usage.get("completion_tokens_details")
                   if isinstance(usage, Mapping) else {})
    return UsageMetadata(
        input_tokens=_first_count(usage, keys=("prompt_tokens", "input_tokens",
                                               "promptTokenCount", "inputTokenCount")),
        output_tokens=_first_count(usage, keys=("completion_tokens", "output_tokens",
                                                "candidatesTokenCount",
                                                "outputTokenCount")),
        cache_read_tokens=_first_count(
            usage, details_in,
            keys=("cache_read_input_tokens", "cached_tokens", "cachedContentTokenCount")),
        cache_creation_tokens=_first_count(usage, keys=("cache_creation_input_tokens",)),
        reasoning_tokens=_first_count(
            usage, details_out, keys=("reasoning_tokens", "thoughtsTokenCount")),
    )


def merge_usage(*usages: UsageMetadata) -> UsageMetadata:
    """Sum usage records; a failed or partial attempt is accounted honestly."""
    total = UsageMetadata()
    for usage in usages:
        if not isinstance(usage, UsageMetadata):
            raise TypeError("usage must be a UsageMetadata")
        total = UsageMetadata(
            input_tokens=total.input_tokens + usage.input_tokens,
            output_tokens=total.output_tokens + usage.output_tokens,
            cache_read_tokens=total.cache_read_tokens + usage.cache_read_tokens,
            cache_creation_tokens=total.cache_creation_tokens + usage.cache_creation_tokens,
            reasoning_tokens=total.reasoning_tokens + usage.reasoning_tokens,
        )
    return total


@dataclass(frozen=True)
class NormalizedResponse:
    """Only safe, normalized content: no raw body, headers or credentials."""

    text: str
    tool_calls: tuple[dict, ...] = ()
    usage: UsageMetadata = field(default_factory=UsageMetadata)
    stop_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "tool_calls": copy.deepcopy(list(self.tool_calls)),
            "usage": self.usage.to_dict(),
            "stop_reason": self.stop_reason,
        }


def _text_from_payload(payload: Mapping) -> str:
    parts: list[str] = []

    def add_blocks(blocks: Any) -> None:
        if not isinstance(blocks, (list, tuple)):
            return
        for block in blocks:
            if isinstance(block, Mapping) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)

    choices = payload.get("choices")
    if isinstance(choices, (list, tuple)) and choices and isinstance(choices[0], Mapping):
        message = choices[0].get("message") or {}
        if isinstance(message, Mapping):
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            else:
                add_blocks(content)
    add_blocks(payload.get("content"))  # anthropic-messages
    candidates = payload.get("candidates")
    if isinstance(candidates, (list, tuple)):
        for candidate in candidates:
            content = candidate.get("content") if isinstance(candidate, Mapping) else None
            if isinstance(content, Mapping):
                add_blocks(content.get("parts"))
    output = payload.get("output")  # openai-responses
    if isinstance(output, (list, tuple)):
        for item in output:
            if isinstance(item, Mapping):
                add_blocks(item.get("content"))
    return "".join(parts)


def _tool_calls_from_payload(payload: Mapping, secrets: Iterable[str]) -> tuple[dict, ...]:
    calls: list[dict] = []

    def add(name: Any, arguments: Any) -> None:
        clean_name = safe_code(name)
        if not clean_name:
            return
        args: Any = {}
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except (ValueError, TypeError):
                parsed = {}
            args = parsed if isinstance(parsed, dict) else {}
        elif isinstance(arguments, Mapping):
            args = dict(arguments)
        calls.append({"name": clean_name,
                      "arguments": _sanitize_value(args, secrets)})
        if len(calls) >= 32:
            raise ProviderTransportError("too many tool calls in response",
                                         category=CATEGORY_MALFORMED)

    choices = payload.get("choices")
    if isinstance(choices, (list, tuple)) and choices and isinstance(choices[0], Mapping):
        message = choices[0].get("message") or {}
        for call in message.get("tool_calls", []) if isinstance(message, Mapping) else []:
            if isinstance(call, Mapping):
                function = call.get("function") or {}
                if isinstance(function, Mapping):
                    add(function.get("name"), function.get("arguments"))
    add_blocks = payload.get("content")
    if isinstance(add_blocks, (list, tuple)):
        for block in add_blocks:
            if isinstance(block, Mapping) and block.get("type") == "tool_use":
                add(block.get("name"), block.get("input"))
    candidates = payload.get("candidates")
    if isinstance(candidates, (list, tuple)):
        for candidate in candidates:
            content = candidate.get("content") if isinstance(candidate, Mapping) else None
            if not isinstance(content, Mapping):
                continue
            for part in content.get("parts", []):
                if isinstance(part, Mapping) and isinstance(part.get("functionCall"), Mapping):
                    function = part["functionCall"]
                    add(function.get("name"), function.get("args"))
    output = payload.get("output")
    if isinstance(output, (list, tuple)):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            for content in item.get("content", []):
                if isinstance(content, Mapping) and content.get("type") == "function_call":
                    try:
                        args = json.loads(content.get("arguments", "{}"))
                    except (ValueError, TypeError):
                        args = {}
                    add(content.get("name"), args)
    return tuple(calls)


def _stop_reason_from_payload(payload: Mapping) -> str | None:
    choices = payload.get("choices")
    if isinstance(choices, (list, tuple)) and choices and isinstance(choices[0], Mapping):
        value = choices[0].get("finish_reason")
        if safe_code(value):
            return safe_code(value)
    for key in ("stop_reason", "status"):
        if safe_code(payload.get(key)) and key == "stop_reason":
            return safe_code(payload.get(key))
    candidates = payload.get("candidates")
    if isinstance(candidates, (list, tuple)) and candidates and isinstance(
            candidates[0], Mapping):
        return safe_code(candidates[0].get("finishReason"))
    return None


def normalize_response(payload: Any, *, protocol: str | None = None,
                       secrets: Iterable[str] = ()) -> NormalizedResponse:
    """Normalize a successful provider response; refuse malformed bodies."""
    if protocol is not None and protocol not in PROTOCOLS:
        raise ProviderContractError(f"unknown protocol {protocol!r}")
    if not isinstance(payload, Mapping):
        raise ProviderTransportError("response payload must be an object",
                                     category=CATEGORY_MALFORMED)
    failure = classify_payload(payload, secrets=secrets)
    if failure is not None:
        raise ProviderTransportError.from_failure(failure)
    text = _scrub(_text_from_payload(payload), secrets)
    tool_calls = _tool_calls_from_payload(payload, secrets)
    if not text and not tool_calls:
        raise ProviderTransportError("response contains no text or tool calls",
                                     category=CATEGORY_MALFORMED)
    return NormalizedResponse(
        text=text,
        tool_calls=tool_calls,
        usage=usage_from_payload(payload),
        stop_reason=_stop_reason_from_payload(payload),
    )


# --- request normalization --------------------------------------------------

def normalize_request(capabilities: ModelCapabilities | None, request: Mapping,
                      *, profile: CompatProfile | None = None,
                      model_id: str | None = None,
                      secrets: Iterable[str] = ()) -> AdaptedRequest:
    """Deep-copy a request, drop credential-like fields and apply compat rules."""
    if not isinstance(request, Mapping):
        raise TypeError("request must be a mapping")
    dropped = sorted(str(key) for key in request if _is_credential_key(key))
    cleaned = {key: value for key, value in request.items()
               if not _is_credential_key(key)}
    notes = [f"removed credential-like field {key!r}; credentials are never "
             "carried by the policy layer" for key in dropped]
    if capabilities is not None:
        adapted = adapt_request(capabilities, cleaned, profile=profile,
                                model_id=model_id)
        body = adapted.request
        notes = list(adapted.adjustments) + notes
    else:
        body = copy.deepcopy(dict(cleaned))
    return AdaptedRequest(
        request=_sanitize_value(body, secrets, drop_credentials=True),
        adjustments=tuple(notes))


# --- retry policy -----------------------------------------------------------

@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay_seconds: float = 0.0
    use_fallback: bool = False


@dataclass(frozen=True)
class ExecutionConfig:
    """Explicit, offline execution policy. Fallbacks default to none."""

    primary: str | None = None
    fallbacks: tuple[str, ...] = ()
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    base_backoff_seconds: float = DEFAULT_BACKOFF_SECONDS
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR
    max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    protocols: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fallbacks", tuple(self.fallbacks or ()))
        object.__setattr__(self, "protocols",
                           MappingProxyType(dict(self.protocols or {})))

    def to_dict(self) -> dict:
        return {
            "primary": self.primary,
            "fallbacks": list(self.fallbacks),
            "max_attempts": self.max_attempts,
            "base_backoff_seconds": self.base_backoff_seconds,
            "backoff_factor": self.backoff_factor,
            "max_backoff_seconds": self.max_backoff_seconds,
            "timeout_seconds": self.timeout_seconds,
            "protocols": dict(self.protocols),
        }


def retry_schedule(config: ExecutionConfig, failure: ProviderFailure,
                   attempt: int) -> RetryDecision:
    """Deterministic backoff; no wall-clock time, randomness or sleeping here."""
    if (failure.category == CATEGORY_CANCELLED or not failure.retryable
            or attempt >= config.max_attempts):
        return RetryDecision(False, 0.0, False)
    delay = config.base_backoff_seconds * (config.backoff_factor ** (attempt - 1))
    delay = min(max(float(delay), 0.0), config.max_backoff_seconds)
    if failure.retry_after is not None:
        delay = min(float(failure.retry_after), config.max_backoff_seconds)
    return RetryDecision(True, round(delay, 6),
                         failure.category in FALLBACK_CATEGORIES)


@dataclass(frozen=True)
class AttemptRecord:
    provider: str
    attempt: int
    category: str | None
    status: int | None
    retryable: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "attempt": self.attempt,
            "category": self.category,
            "status": self.status,
            "retryable": bool(self.retryable),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProviderResult:
    """Serializable result; never holds a transport, exception or raw body."""

    status: str
    provider: str | None = None
    model: str | None = None
    response: NormalizedResponse | None = None
    error: ProviderFailure | None = None
    attempts: tuple[AttemptRecord, ...] = ()
    fallbacks_used: tuple[str, ...] = ()
    backoff_seconds: tuple[float, ...] = ()

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "response": self.response.to_dict() if self.response is not None else None,
            "error": self.error.to_dict() if self.error is not None else None,
            "attempts": [record.to_dict() for record in self.attempts],
            "fallbacks_used": list(self.fallbacks_used),
            "backoff_seconds": list(self.backoff_seconds),
        }


@dataclass(frozen=True)
class TransportResponse:
    """Convenience reply for injected transports (no network is performed)."""

    status: int
    payload: Any = None
    headers: Mapping[str, str] = field(default_factory=dict)


def validate_execution_config(
    config: ExecutionConfig, *, registry: ProviderRegistry | None = None,
    descriptors: Mapping[str, ProviderDescriptor] | None = None,
    model: str | None = None,
) -> tuple[str, ...]:
    """Return diagnostics only — values and credential material are never included."""
    if not isinstance(config, ExecutionConfig):
        raise TypeError("config must be an ExecutionConfig")
    problems: list[str] = []
    for name in ("max_attempts",):
        value = getattr(config, name)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            problems.append(f"{name} must be an integer between 1 and 5")
    for name in ("base_backoff_seconds", "backoff_factor", "max_backoff_seconds",
                 "timeout_seconds"):
        value = getattr(config, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"{name} must be a number")
    if isinstance(config.base_backoff_seconds, (int, float)) and not isinstance(
            config.base_backoff_seconds, bool) and config.base_backoff_seconds < 0:
        problems.append("base_backoff_seconds must not be negative")
    if isinstance(config.backoff_factor, (int, float)) and not isinstance(
            config.backoff_factor, bool) and config.backoff_factor < 1:
        problems.append("backoff_factor must be at least 1")
    if isinstance(config.max_backoff_seconds, (int, float)) and not isinstance(
            config.max_backoff_seconds, bool) and config.max_backoff_seconds <= 0:
        problems.append("max_backoff_seconds must be positive")
    if isinstance(config.timeout_seconds, (int, float)) and not isinstance(
            config.timeout_seconds, bool) and not 0 < config.timeout_seconds <= 300:
        problems.append("timeout_seconds must be between 0 and 300")
    if config.primary is not None and not isinstance(config.primary, str):
        problems.append("primary must be a provider id or None")
    if config.fallbacks and not config.primary:
        problems.append("fallback providers require an explicitly configured primary")
    seen: set[str] = set()
    for name in config.fallbacks:
        if not isinstance(name, str) or not name:
            problems.append("fallback provider ids must be non-empty strings")
            continue
        if name == config.primary:
            problems.append(f"fallback {name!r} is the primary provider (self-fallback)")
        if name in seen:
            problems.append(f"fallback {name!r} is listed more than once (duplicate)")
        seen.add(name)
    for name, protocol in config.protocols.items():
        if protocol not in PROTOCOLS:
            problems.append(f"protocol for {name!r} is not a supported protocol")
    if descriptors is not None and not isinstance(descriptors, Mapping):
        raise TypeError("descriptors must be a mapping")
    if registry is not None and not isinstance(registry, ProviderRegistry):
        raise TypeError("registry must be a ProviderRegistry")
    known: dict[str, ProviderDescriptor] = {}
    if descriptors is not None:
        known.update(descriptors)
    if registry is not None:
        for entry in registry.list():
            known.setdefault(entry.id, entry)
    if known or registry is not None or descriptors is not None:
        candidates = ([config.primary] if config.primary else []) + list(config.fallbacks)
        for name in candidates:
            if not isinstance(name, str) or not name:
                continue
            entry = known.get(name)
            if entry is None:
                problems.append(f"provider {name!r} is not registered for execution")
                continue
            if entry.user_approved is not True:
                problems.append(f"provider {name!r} requires explicit user approval")
            if entry.bundled:
                problems.append(f"provider {name!r} is bundled and not selectable")
            if entry.paid:
                problems.append(f"provider {name!r} is paid and cannot be used "
                                "on an automatic path")
            if entry.protocol not in PROTOCOLS:
                problems.append(f"provider {name!r} declares an unknown protocol")
            if model is not None and name == config.primary and model not in entry.models:
                problems.append(f"model {model!r} is not declared by provider {name!r}")
    return tuple(problems)


# --- execution over an injected transport ----------------------------------

def _transport_reply(reply: Any, *, secrets: Iterable[str] = ()) -> tuple[int, Any, Mapping]:
    if isinstance(reply, TransportResponse):
        return reply.status, reply.payload if reply.payload is not None else {}, \
            reply.headers or {}
    if isinstance(reply, Mapping):
        return 200, reply, {}
    if isinstance(reply, tuple) and len(reply) in (2, 3):
        status = reply[0]
        if len(reply) == 2:
            headers, payload = {}, reply[1]
        else:
            headers, payload = reply[1] or {}, reply[2]
        if not isinstance(status, int) or isinstance(status, bool):
            raise ProviderTransportError("transport returned an invalid status",
                                         category=CATEGORY_MALFORMED)
        if not isinstance(headers, Mapping):
            raise ProviderTransportError("transport returned invalid headers",
                                         category=CATEGORY_MALFORMED)
        return status, payload, headers
    raise ProviderTransportError("transport returned an unusable reply",
                                 category=CATEGORY_MALFORMED)


def _wire_request(provider: str, model: str | None, body: Mapping,
                  config: ExecutionConfig, *, stream: bool, attempt: int,
                  secrets: Iterable[str] = ()) -> dict:
    return {
        "provider": provider,
        "model": model,
        "body": _sanitize_value(body, secrets, cap=MAX_EVENT_TEXT_CHARS),
        "timeout_seconds": config.timeout_seconds,
        "stream": stream,
        "attempt": attempt,
    }


def _preflight(config: ExecutionConfig, request: Mapping, *, transport: Any,
               registry: ProviderRegistry | None,
               descriptors: Mapping[str, ProviderDescriptor] | None,
               capabilities: ModelCapabilities | None, model: str | None,
               secrets: Iterable[str]) -> tuple[tuple[str, ...], dict, str | None]:
    problems = validate_execution_config(config, registry=registry,
                                         descriptors=descriptors, model=model)
    if problems:
        return problems, {}, None
    if not callable(transport):
        raise TypeError("transport must be callable")
    if capabilities is not None:
        refusal = image_preflight_message(capabilities, request)
        if refusal:
            return (redact_message(refusal, secrets),), {}, None
        body = normalize_request(capabilities, request, secrets=secrets).request
    else:
        body = normalize_request(None, request, secrets=secrets).request
    chosen_model = (model or body.get("model")
                    or (capabilities.model_id if capabilities is not None else None))
    return (), body, chosen_model


def _candidates(config: ExecutionConfig) -> tuple[str, ...]:
    if not config.primary:
        return ()
    return (config.primary,) + tuple(config.fallbacks)


def _failed(status: str, failure: ProviderFailure, *, provider: str | None = None,
            model: str | None = None, attempts: tuple[AttemptRecord, ...] = (),
            fallbacks: tuple[str, ...] = (),
            backoffs: tuple[float, ...] = ()) -> ProviderResult:
    return ProviderResult(status=status, provider=provider, model=model,
                          error=failure, attempts=attempts,
                          fallbacks_used=fallbacks, backoff_seconds=backoffs)


def execute_request(
    config: ExecutionConfig, request: Mapping, *, transport: Any,
    secrets: Iterable[str] = (), sleep: Any = None, cancel: Any = None,
    registry: ProviderRegistry | None = None,
    descriptors: Mapping[str, ProviderDescriptor] | None = None,
    capabilities: ModelCapabilities | None = None, model: str | None = None,
) -> ProviderResult:
    """Execute one non-streaming call through the injected transport only.

    No credential is placed in the wire request. Failures are classified,
    retried with deterministic backoff, and failed over *only* to providers the
    caller explicitly listed. No provider configured means no call at all.
    """
    problems, body, chosen_model = _preflight(
        config, request, transport=transport, registry=registry,
        descriptors=descriptors, capabilities=capabilities, model=model,
        secrets=secrets)
    if problems:
        return _failed("failed", ProviderFailure(CATEGORY_INVALID,
                                                 "; ".join(problems), None, False),
                       provider=config.primary, model=chosen_model)
    candidates = _candidates(config)
    if not candidates:
        return ProviderResult(status="no_provider", model=chosen_model)

    attempts: list[AttemptRecord] = []
    delays: list[float] = []
    fallbacks: list[str] = []
    last_failure: ProviderFailure | None = None
    for position, provider in enumerate(candidates):
        if cancel is not None and cancel.is_set():
            return ProviderResult(status="cancelled", provider=provider,
                                  model=chosen_model, attempts=tuple(attempts),
                                  fallbacks_used=tuple(fallbacks),
                                  backoff_seconds=tuple(delays))
        for attempt in range(1, config.max_attempts + 1):
            if cancel is not None and cancel.is_set():
                return ProviderResult(status="cancelled", provider=provider,
                                      model=chosen_model, attempts=tuple(attempts),
                                      fallbacks_used=tuple(fallbacks),
                                      backoff_seconds=tuple(delays))
            wire = _wire_request(provider, chosen_model, body, config,
                                 stream=False, attempt=attempt, secrets=secrets)
            try:
                status, payload, headers = _transport_reply(transport(wire),
                                                            secrets=secrets)
                if status >= 400:
                    raise ProviderTransportError.from_failure(
                        classify_status(status, payload=payload, headers=headers,
                                        secrets=secrets))
                response = normalize_response(
                    payload, protocol=config.protocols.get(provider), secrets=secrets)
            except Exception as exc:
                failure = classify_exception(exc, secrets=secrets)
                attempts.append(AttemptRecord(provider, attempt, failure.category,
                                              failure.status, failure.retryable,
                                              failure.message))
                last_failure = failure
                if failure.category == CATEGORY_CANCELLED:
                    return ProviderResult(status="cancelled", provider=provider,
                                          model=chosen_model, attempts=tuple(attempts),
                                          fallbacks_used=tuple(fallbacks),
                                          backoff_seconds=tuple(delays))
                decision = retry_schedule(config, failure, attempt)
                if decision.retry:
                    delays.append(decision.delay_seconds)
                    if sleep is not None:
                        sleep(decision.delay_seconds)
                    continue
                break
            attempts.append(AttemptRecord(provider, attempt, None, status,
                                          False, "ok"))
            return ProviderResult(
                status="ok", provider=provider, model=chosen_model,
                response=response, attempts=tuple(attempts),
                fallbacks_used=tuple(fallbacks), backoff_seconds=tuple(delays))
        if (last_failure is not None
                and last_failure.category in FALLBACK_CATEGORIES
                and position + 1 < len(candidates)):
            fallbacks.append(candidates[position + 1])
            continue
        break
    return _failed("failed", last_failure or ProviderFailure(
        CATEGORY_UNKNOWN, "provider call did not produce a result", None, False),
        provider=candidates[-1], model=chosen_model, attempts=tuple(attempts),
        fallbacks=tuple(fallbacks), backoffs=tuple(delays))


def sanitize_event(event: Any, secrets: Iterable[str] = ()) -> dict:
    """Normalize one streamed event; unknown kinds are explicitly ignored."""
    if not isinstance(event, Mapping):
        return {"kind": "ignored"}
    kind = event.get("kind") or event.get("event") or event.get("type")
    if not isinstance(kind, str) or not kind:
        return {"kind": "ignored"}
    if kind in ("text_delta", "thinking_delta", "tool_input_delta"):
        raw = event.get("text")
        if raw is None:
            raw = event.get("partial_json", "")
        return {"kind": kind,
                "text": _scrub(str(raw), secrets)[:MAX_EVENT_TEXT_CHARS]}
    if kind in ("usage", "usage_metadata"):
        usage = event.get("usage") if isinstance(event.get("usage"), Mapping) else event
        return {"kind": "usage", "usage": usage_from_payload(usage)}
    if kind == "stop":
        return {"kind": "stop",
                "stop_reason": safe_code(event.get("stop_reason")
                                         or event.get("finish_reason"))}
    if kind == "error":
        raw_error = event.get("error")
        if isinstance(raw_error, Mapping):
            # Streamed frames wrap the provider error body as {"error": {...}}
            # and put the human-readable text inside it. classify_payload()
            # expects that wrapper; passing the inner mapping directly would
            # classify every such frame as "unknown" and drop its message.
            classified: Any = {"error": raw_error}
            message = raw_error.get("message") or event.get("message")
        else:
            classified = event
            message = event.get("message")
        from_payload = classify_payload(classified, secrets=secrets)
        category = safe_code(event.get("category"))
        if category not in CATEGORIES:
            category = from_payload.category if from_payload else CATEGORY_UNKNOWN
        retryable = event.get("retryable")
        if not isinstance(retryable, bool):
            retryable = category in RETRYABLE_CATEGORIES
        return {
            "kind": "error",
            "category": category,
            "message": redact_message(message or "stream error", secrets),
            "status": event.get("status") if isinstance(event.get("status"), int)
            else None,
            "retryable": retryable,
        }
    return {"kind": "ignored"}


def _stream_failure(event: dict, secrets: Iterable[str]) -> ProviderFailure:
    return ProviderFailure(
        category=event["category"],
        message=redact_message(event.get("message", "stream error"), secrets),
        status=event.get("status"),
        retryable=bool(event.get("retryable")),
    )


def execute_stream(
    config: ExecutionConfig, request: Mapping, *, transport: Any,
    secrets: Iterable[str] = (), sleep: Any = None, cancel: Any = None,
    registry: ProviderRegistry | None = None,
    descriptors: Mapping[str, ProviderDescriptor] | None = None,
    capabilities: ModelCapabilities | None = None, model: str | None = None,
) -> ProviderResult:
    """Consume an injected event stream; never replay content already emitted.

    A failure after the first content delta yields ``partial_failed`` with the
    text preserved, no retry and no fallback: replaying would duplicate output
    and possibly duplicate paid usage. Cancellation is a normal stop, not an
    error, and likewise preserves the text already emitted.
    """
    problems, body, chosen_model = _preflight(
        config, request, transport=transport, registry=registry,
        descriptors=descriptors, capabilities=capabilities, model=model,
        secrets=secrets)
    if problems:
        return _failed("failed", ProviderFailure(CATEGORY_INVALID,
                                                 "; ".join(problems), None, False),
                       provider=config.primary, model=chosen_model)
    candidates = _candidates(config)
    if not candidates:
        return ProviderResult(status="no_provider", model=chosen_model)

    attempts: list[AttemptRecord] = []
    delays: list[float] = []
    fallbacks: list[str] = []
    last_failure: ProviderFailure | None = None
    for position, provider in enumerate(candidates):
        if cancel is not None and cancel.is_set():
            return ProviderResult(status="cancelled", provider=provider,
                                  model=chosen_model, attempts=tuple(attempts),
                                  fallbacks_used=tuple(fallbacks),
                                  backoff_seconds=tuple(delays))
        for attempt in range(1, config.max_attempts + 1):
            if cancel is not None and cancel.is_set():
                return ProviderResult(status="cancelled", provider=provider,
                                      model=chosen_model, attempts=tuple(attempts),
                                      fallbacks_used=tuple(fallbacks),
                                      backoff_seconds=tuple(delays))
            wire = _wire_request(provider, chosen_model, body, config,
                                 stream=True, attempt=attempt, secrets=secrets)
            text_parts: list[str] = []
            usage = UsageMetadata()
            stop_reason: str | None = None
            emitted = False
            failure: ProviderFailure | None = None
            interrupted = False
            try:
                reply = transport(wire)
                if isinstance(reply, Mapping):
                    raise ProviderTransportError("stream transport returned an object",
                                                 category=CATEGORY_MALFORMED)
                for raw_event in reply:
                    if cancel is not None and cancel.is_set():
                        interrupted = True
                        break
                    event = sanitize_event(raw_event, secrets)
                    kind = event["kind"]
                    if kind == "error":
                        failure = _stream_failure(event, secrets)
                        break
                    if kind in ("text_delta", "thinking_delta", "tool_input_delta"):
                        emitted = True
                        if kind == "text_delta":
                            text_parts.append(event["text"])
                    elif kind == "usage":
                        usage = merge_usage(usage, event["usage"])
                    elif kind == "stop":
                        stop_reason = event.get("stop_reason")
            except Exception as exc:
                failure = classify_exception(exc, secrets=secrets)
            partial = NormalizedResponse(
                text=_scrub("".join(text_parts), secrets),
                tool_calls=(), usage=usage, stop_reason=stop_reason)
            if interrupted:
                attempts.append(AttemptRecord(provider, attempt, None, None, False,
                                              "cancelled mid-stream"))
                return ProviderResult(status="cancelled", provider=provider,
                                      model=chosen_model, response=partial,
                                      attempts=tuple(attempts),
                                      fallbacks_used=tuple(fallbacks),
                                      backoff_seconds=tuple(delays))
            if failure is not None:
                attempts.append(AttemptRecord(provider, attempt, failure.category,
                                              failure.status, failure.retryable,
                                              failure.message))
                last_failure = failure
                # Cancellation is a normal stop, never a provider failure —
                # even when delivered as a streamed error frame after content.
                # It must be checked before the partial-failure path or a
                # user-initiated stop would be mislabelled as a failure.
                if failure.category == CATEGORY_CANCELLED:
                    return ProviderResult(status="cancelled", provider=provider,
                                          model=chosen_model, response=partial,
                                          attempts=tuple(attempts),
                                          fallbacks_used=tuple(fallbacks),
                                          backoff_seconds=tuple(delays))
                if emitted:
                    return ProviderResult(
                        status="partial_failed", provider=provider,
                        model=chosen_model, response=partial, error=failure,
                        attempts=tuple(attempts), fallbacks_used=tuple(fallbacks),
                        backoff_seconds=tuple(delays))
                decision = retry_schedule(config, failure, attempt)
                if decision.retry:
                    delays.append(decision.delay_seconds)
                    if sleep is not None:
                        sleep(decision.delay_seconds)
                    continue
                break
            if not emitted:
                last_failure = ProviderFailure(
                    CATEGORY_MALFORMED, "stream contained no content", None, False)
                attempts.append(AttemptRecord(provider, attempt, CATEGORY_MALFORMED,
                                              None, False, last_failure.message))
                break
            attempts.append(AttemptRecord(provider, attempt, None, 200, False, "ok"))
            return ProviderResult(
                status="ok", provider=provider, model=chosen_model, response=partial,
                attempts=tuple(attempts), fallbacks_used=tuple(fallbacks),
                backoff_seconds=tuple(delays))
        if (last_failure is not None
                and last_failure.category in FALLBACK_CATEGORIES
                and position + 1 < len(candidates)):
            fallbacks.append(candidates[position + 1])
            continue
        break
    return _failed("failed", last_failure or ProviderFailure(
        CATEGORY_UNKNOWN, "provider stream did not produce content", None, False),
        provider=candidates[-1], model=chosen_model, attempts=tuple(attempts),
        fallbacks=tuple(fallbacks), backoffs=tuple(delays))
