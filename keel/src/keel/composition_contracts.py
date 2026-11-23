"""Pure composition/layering contracts for providers, presenters and plugins.

This module is the stdlib-only, descriptor/policy surface used by three
P0 addendum-6 rows (``D4.2``, ``D4.7``, ``D4.11``).  It deliberately holds no
host state: no files, no network, no subprocess, no clock and no chance input.
Callers own every identifier and value; the functions here only describe,
validate, merge and render.  ``to_dict``/``from_dict`` exchange plain data so a
caller may persist it through its own storage layer.

Feature map
-----------
* **D4.2** -- ``ProviderDescriptor`` / ``ProviderKind.OPENAI_COMPATIBLE`` treat
  custom OpenAI-compatible HTTP endpoints (local servers and LAN) as a
  first-class provider type.  Keys are *references* (``env:``/``keyring:``/
  ``secret:``/``file:``); literal secrets are rejected and scrubbed.
* **D4.7** -- ``PresenterDescriptor`` + ``present``/``render_tool_card`` build a
  tool's summary, icon and expanded view as a pure function of raw events plus
  persisted result metadata.  Presenters cannot expose secret fields.
* **D4.11** -- ``PluginDescriptor`` models the bundled Plugin Manager and
  extension plugins; ``can_activate_plugin`` is the approval gate.  All of it
  composes through typed ``LayerDescriptor`` objects.

Security invariants (enforced by ``test_composition_contracts``):

* typed layers merge deterministically, independent of input order;
* protected-core/bundle contributions always beat plugin/agent/user ones;
* resource paths are contained lexically (no traversal, drive, UNC, encoded
  dot segments or filesystem lookups);
* secret material never appears in a descriptor's public form, an error
  message, or a serialization round-trip;
* every unknown or malformed value fails closed (never silently permissive).
"""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlsplit

FEATURE_IDS = ("D4.2", "D4.7", "D4.11")


class ContractError(ValueError):
    """Base class for composition-contract failures."""


class ContractValidationError(ContractError):
    """Fail-closed validation error; messages are always redacted."""

    def __init__(self, errors: Any):
        if isinstance(errors, str):
            errors = (errors,)
        self.errors = tuple(str(e) for e in errors)
        super().__init__("; ".join(redact(e) for e in self.errors))


# ---------------------------------------------------------------------------
# Secret detection / redaction (no secret value ever survives a boundary)
# ---------------------------------------------------------------------------

_SECRET_REF_RE = re.compile(r"(?i)^(env|keyring|secret|file):(.+)$")
_ALLOWED_SECRET_SOURCES = frozenset({"env", "keyring", "secret", "file"})
_LITERAL_SECRET_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_\-]{12,}|gh[pousr]_[A-Za-z0-9_\-]{12,}|"
    r"xox[baprs]-[A-Za-z0-9_\-]{12,}|AKIA[A-Z0-9]{12,})"
)
_ASSIGNMENT_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|passwd|"
    r"authorization|auth)\b\s*[:=]\s*([^\s,;]+)"
)
_SECRET_FIELD_TOKENS = frozenset({
    "key", "token", "secret", "password", "passwd", "credential",
    "authorization", "auth",
})


def is_secret_reference(value: Any) -> bool:
    """True for an indirection such as ``env:KEEL_KEY`` (not a value)."""
    return _SECRET_REF_RE.match(str(value or "").strip()) is not None


def looks_like_secret(value: Any) -> bool:
    """Best-effort detection of a literal credential in caller-supplied text."""
    text = str(value or "")
    if not text or is_secret_reference(text):
        return False
    return bool(_LITERAL_SECRET_RE.search(text) or
                _ASSIGNMENT_SECRET_RE.search(text))


def redact(value: Any) -> str:
    """Return text with detected secret values replaced by ``[REDACTED]``."""
    text = "" if value is None else str(value)
    text = _ASSIGNMENT_SECRET_RE.sub(
        lambda m: "%s=[REDACTED]" % m.group(1), text)
    text = _LITERAL_SECRET_RE.sub("[REDACTED]", text)
    return text


def is_secret_field(field: Any) -> bool:
    """True for names like ``api_key``/``token`` that must never be rendered."""
    tokens = {tok for tok in re.split(r"[^a-z0-9]+", str(field or "").lower()) if tok}
    return bool(tokens & _SECRET_FIELD_TOKENS)


@dataclass(frozen=True)
class SecretRef:
    """An immutable indirection to a secret; it never carries the value."""

    source: str
    name: str
    required: bool = True

    def describe(self) -> str:
        return "%s:%s" % (self.source, self.name)

    def to_public_dict(self) -> dict:
        return {"source": self.source, "name": self.name,
                "required": self.required}

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if str(self.source or "").lower() not in _ALLOWED_SECRET_SOURCES:
            errors.append("secret source must be env/keyring/secret/file")
        name = str(self.name or "")
        if not name:
            errors.append("secret reference name must not be empty")
        if re.search(r"[^A-Za-z0-9_./:\-]", name) or ".." in name or "=" in name:
            errors.append("secret reference name is not safe")
        return tuple(errors)

    @classmethod
    def from_dict(cls, data: dict) -> "SecretRef":
        data = data or {}
        return cls(
            source=str(data.get("source", "") or ""),
            name=str(data.get("name", "") or ""),
            required=bool(data.get("required", True)),
        )


def make_secret_ref(source: Any, name: Any, *, required: Any = True) -> SecretRef:
    """Build and validate a secret reference (a raw value is never accepted)."""
    ref = SecretRef(
        source=str(source or "").strip().lower(),
        name=str(name or "").strip(),
        required=bool(required),
    )
    errors = ref.validate()
    if errors:
        raise ContractValidationError(errors)
    return ref


def parse_secret_ref(value: Any) -> SecretRef | None:
    """Parse ``env:NAME`` style text, or return None when it is not a ref."""
    match = _SECRET_REF_RE.match(str(value or "").strip())
    if match is None:
        return None
    try:
        return make_secret_ref(match.group(1), match.group(2).strip())
    except ContractValidationError:
        return None


def _coerce_secret_ref(value: Any) -> SecretRef | None:
    if value is None:
        return None
    if isinstance(value, SecretRef):
        return value
    text = str(value)
    ref = parse_secret_ref(text)
    if ref is not None:
        return ref
    raise ContractValidationError(
        "literal secret %r is not allowed; use a reference such as env:NAME" % text
    )


# ---------------------------------------------------------------------------
# Lexical path containment (no filesystem access, no symlink resolution)
# ---------------------------------------------------------------------------

_ENCODED_TRAVERSAL_RE = re.compile(r"(?i)%2e|%2f|%5c")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_FIELD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _split_segments(path: Any, label: str) -> list[str]:
    text = str(path or "")
    if not text:
        raise ContractValidationError("%s must not be empty" % label)
    if _ENCODED_TRAVERSAL_RE.search(text):
        raise ContractValidationError("encoded traversal is not allowed in %s" % label)
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        raise ContractValidationError("control character in %s" % label)
    normalized = text.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ContractValidationError("%s must be relative" % label)
    segments: list[str] = []
    for part in normalized.split("/"):
        if part in ("", "."):
            continue
        segments.append(part)
    return segments


def safe_join(root: Any, *parts: Any) -> str:
    """Join ``parts`` under ``root`` or raise; purely lexical and fail-closed."""
    root_segments = _split_segments(root, "containment root")
    if not root_segments or ".." in root_segments:
        raise ContractValidationError("invalid containment root")
    combined = list(root_segments)
    for part in parts:
        for segment in _split_segments(part, "path"):
            if segment == "..":
                if len(combined) <= len(root_segments):
                    raise ContractValidationError("path escapes containment root")
                combined.pop()
            else:
                combined.append(segment)
    return "/".join(combined)


def is_contained(root: Any, candidate: Any) -> bool:
    """True when ``candidate`` is a relative path anchored at ``root``."""
    try:
        root_segments = _split_segments(root, "containment root")
        if not root_segments or ".." in root_segments:
            return False
        resolved: list[str] = []
        for segment in _split_segments(candidate, "candidate path"):
            if segment == "..":
                if not resolved:
                    return False
                resolved.pop()
            else:
                resolved.append(segment)
    except ContractValidationError:
        return False
    return (len(resolved) >= len(root_segments) and
            tuple(resolved[:len(root_segments)]) == tuple(root_segments))


def _normalize_contained(root: Any, path: Any) -> str:
    """Return a normalized path already anchored at ``root``, or raise."""
    if not is_contained(root, path):
        raise ContractValidationError("path escapes the containment root")
    root_segments = _split_segments(root, "containment root")
    resolved: list[str] = []
    for segment in _split_segments(path, "path"):
        if segment == "..":
            resolved.pop()
        else:
            resolved.append(segment)
    return "/".join(resolved)


# ---------------------------------------------------------------------------
# Typed layer descriptors
# ---------------------------------------------------------------------------

class LayerOrigin(str, Enum):
    """Where a contribution came from; lower precedence number wins."""

    CORE = "core"
    BUNDLE = "bundle"
    PLUGIN = "plugin"
    AGENT = "agent"
    USER = "user"
    UNKNOWN = "unknown"

    @property
    def precedence(self) -> int:
        return {
            LayerOrigin.CORE: 0,
            LayerOrigin.BUNDLE: 1,
            LayerOrigin.PLUGIN: 2,
            LayerOrigin.AGENT: 3,
            LayerOrigin.USER: 4,
            LayerOrigin.UNKNOWN: 99,
        }[self]

    def __str__(self) -> str:
        return self.value


CORE = LayerOrigin.CORE
BUNDLE = LayerOrigin.BUNDLE
PLUGIN = LayerOrigin.PLUGIN
AGENT = LayerOrigin.AGENT
USER = LayerOrigin.USER
UNKNOWN = LayerOrigin.UNKNOWN

# Bundled code (the Plugin Manager itself) is as protected as the core.
PROTECTED_ORIGINS = frozenset({CORE, BUNDLE})

_ORIGIN_ALIASES = {
    "bundled": "bundle", "extension": "plugin", "ext": "plugin",
}


def _origin(value: Any) -> LayerOrigin:
    if isinstance(value, LayerOrigin):
        return value
    text = str(value or "").strip().lower()
    text = _ORIGIN_ALIASES.get(text, text)
    try:
        return LayerOrigin(text)
    except ValueError:
        return LayerOrigin.UNKNOWN


class ProviderKind(str, Enum):
    """Provider types; ``OPENAI_COMPATIBLE`` is the first-class custom path."""

    OPENAI_COMPATIBLE = "openai_compatible"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


_KIND_ALIASES = {
    "openai-compatible": "openai_compatible",
    "openai compatible": "openai_compatible",
    "compatible": "openai_compatible",
    "ollama": "local",
    "llama.cpp": "local",
    "llamacpp": "local",
}


def _provider_kind(value: Any) -> ProviderKind:
    if isinstance(value, ProviderKind):
        return value
    text = str(value or "").strip().lower()
    text = _KIND_ALIASES.get(text, text.replace("-", "_").replace(" ", "_"))
    try:
        return ProviderKind(text)
    except ValueError:
        return ProviderKind.UNKNOWN


def _pairs(metadata: Any) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    items = metadata.items() if isinstance(metadata, dict) else metadata
    return tuple(sorted((str(k), str(v)) for k, v in items))


# ---------------------------------------------------------------------------
# D4.2 -- OpenAI-compatible provider descriptors
# ---------------------------------------------------------------------------

def _url_error(url: Any) -> str | None:
    text = str(url or "")
    if not text.strip():
        return "base_url must not be empty"
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        return "base_url must not contain control characters"
    if looks_like_secret(text):
        return "base_url must not contain a literal secret"
    try:
        parts = urlsplit(text)
    except ValueError:
        return "base_url is not a valid URL"
    if parts.scheme not in ("http", "https"):
        return "base_url scheme must be http or https"
    if not parts.netloc:
        return "base_url must include a host"
    if parts.username or parts.password:
        return "base_url must not embed credentials"
    if parts.fragment:
        return "base_url must not contain a fragment"
    for _, value in parse_qsl(parts.query):
        if looks_like_secret(value):
            return "base_url query must not contain a secret"
    return None


@dataclass(frozen=True)
class ProviderDescriptor:
    """A typed provider endpoint; secrets are references, never values."""

    name: str
    kind: ProviderKind
    base_url: str
    secret_ref: SecretRef | None
    models: tuple[str, ...]
    origin: LayerOrigin
    metadata: tuple[tuple[str, str], ...]

    @property
    def is_openai_compatible(self) -> bool:
        return self.kind == ProviderKind.OPENAI_COMPATIBLE

    def to_public_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "base_url": self.base_url,
            "models": list(self.models),
            "origin": _origin(self.origin).value,
            "metadata": dict(self.metadata),
            "secret_ref": self.secret_ref.describe() if self.secret_ref else None,
            "has_secret": self.secret_ref is not None,
        }

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "base_url": self.base_url,
            "models": list(self.models),
            "origin": _origin(self.origin).value,
            "metadata": dict(self.metadata),
            "secret_ref": (self.secret_ref.to_public_dict()
                           if self.secret_ref else None),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderDescriptor":
        data = data or {}
        ref = data.get("secret_ref")
        if isinstance(ref, SecretRef):
            secret_ref: SecretRef | None = ref
        elif isinstance(ref, dict):
            secret_ref = SecretRef.from_dict(ref)
        else:
            secret_ref = parse_secret_ref(ref) if ref else None
        return make_provider(
            data.get("name", ""),
            kind=_provider_kind(data.get("kind")),
            base_url=data.get("base_url", ""),
            secret_ref=secret_ref,
            models=data.get("models", ()),
            origin=_origin(data.get("origin")),
            metadata=data.get("metadata", {}),
        )


def validate_provider(provider: ProviderDescriptor) -> tuple[str, ...]:
    errors: list[str] = []
    name = str(provider.name or "")
    if not name or not _IDENTIFIER_RE.match(name):
        errors.append("provider name must be a non-empty safe identifier")
    if provider.kind == ProviderKind.UNKNOWN:
        errors.append("provider kind is unknown")
    url_error = _url_error(provider.base_url)
    if url_error:
        errors.append(url_error)
    if provider.secret_ref is not None:
        errors.extend(provider.secret_ref.validate())
    for key, value in provider.metadata:
        if not _FIELD_RE.match(str(key)):
            errors.append("provider metadata key is not safe")
        if looks_like_secret(value):
            errors.append("provider metadata must not contain a literal secret")
    return tuple(errors)


def make_provider(
    name: Any,
    *,
    kind: Any = ProviderKind.OPENAI_COMPATIBLE,
    base_url: Any = "",
    secret_ref: Any = None,
    models: Iterable[Any] = (),
    origin: Any = CORE,
    metadata: Any = None,
) -> ProviderDescriptor:
    """Build a validated provider descriptor (D4.2)."""
    descriptor = ProviderDescriptor(
        name=str(name or ""),
        kind=_provider_kind(kind),
        base_url=str(base_url or ""),
        secret_ref=_coerce_secret_ref(secret_ref),
        models=tuple(str(m) for m in models),
        origin=_origin(origin),
        metadata=_pairs(metadata),
    )
    errors = validate_provider(descriptor)
    if errors:
        raise ContractValidationError(errors)
    return descriptor


def endpoint_scope(provider: ProviderDescriptor) -> str:
    """Classify an endpoint as ``local``, ``lan`` or ``remote`` (D4.2)."""
    host = (urlsplit(provider.base_url).hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return "local"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if host.endswith((".local", ".lan", ".internal")):
            return "lan"
        return "remote"
    if address.is_loopback:
        return "local"
    if address.is_private:
        return "lan"
    return "remote"


# ---------------------------------------------------------------------------
# D4.7 -- pure tool presenters
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PresenterDescriptor:
    """Declarative, serializable spec for a tool's UI card (D4.7)."""

    tool_name: str
    icon: str
    summary_fields: tuple[str, ...]
    expanded_fields: tuple[str, ...]
    metadata_fields: tuple[str, ...]
    origin: LayerOrigin
    version: int

    def _fields(self) -> tuple[tuple[str, ...], ...]:
        return (self.summary_fields, self.expanded_fields, self.metadata_fields)

    def to_public_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "icon": self.icon,
            "summary_fields": list(self.summary_fields),
            "expanded_fields": list(self.expanded_fields),
            "metadata_fields": list(self.metadata_fields),
            "origin": _origin(self.origin).value,
            "version": self.version,
        }

    to_dict = to_public_dict

    @classmethod
    def from_dict(cls, data: dict) -> "PresenterDescriptor":
        data = data or {}
        return make_presenter(
            data.get("tool_name", ""),
            icon=data.get("icon", "tool"),
            summary_fields=data.get("summary_fields", ()),
            expanded_fields=data.get("expanded_fields", ()),
            metadata_fields=data.get("metadata_fields", ()),
            origin=_origin(data.get("origin")),
            version=data.get("version", 1),
        )


@dataclass(frozen=True)
class Presentation:
    """Immutable, host-independent result of a pure presenter."""

    tool_name: str
    summary: str
    icon: str
    expanded: tuple[str, ...]
    fields_used: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "summary": self.summary,
            "icon": self.icon,
            "expanded": list(self.expanded),
            "fields_used": list(self.fields_used),
        }


def validate_presenter(spec: PresenterDescriptor) -> tuple[str, ...]:
    errors: list[str] = []
    if not _IDENTIFIER_RE.match(str(spec.tool_name or "")):
        errors.append("presenter tool name is not a safe identifier")
    if not _IDENTIFIER_RE.match(str(spec.icon or "")):
        errors.append("presenter icon is not a safe token")
    for group in spec._fields():
        for field in group:
            if not _FIELD_RE.match(str(field)):
                errors.append("presenter field name is not safe")
            if is_secret_field(field):
                errors.append("presenter must not render secret fields")
    try:
        if int(spec.version) < 1:
            errors.append("presenter version must be at least 1")
    except (TypeError, ValueError):
        errors.append("presenter version must be an integer")
    return tuple(errors)


def make_presenter(
    tool_name: Any,
    *,
    icon: Any = "tool",
    summary_fields: Iterable[Any] = (),
    expanded_fields: Iterable[Any] = (),
    metadata_fields: Iterable[Any] = (),
    origin: Any = CORE,
    version: Any = 1,
) -> PresenterDescriptor:
    """Build a validated presenter descriptor (D4.7)."""
    descriptor = PresenterDescriptor(
        tool_name=str(tool_name or ""),
        icon=str(icon or ""),
        summary_fields=tuple(str(f) for f in summary_fields),
        expanded_fields=tuple(str(f) for f in expanded_fields),
        metadata_fields=tuple(str(f) for f in metadata_fields),
        origin=_origin(origin),
        version=version if isinstance(version, int) else -1,
    )
    errors = validate_presenter(descriptor)
    if errors:
        raise ContractValidationError(errors)
    return descriptor


def present(spec: PresenterDescriptor, event: Any = None,
            metadata: Any = None) -> Presentation:
    """Purely derive a card from raw events and persisted result metadata."""
    event = event or {}
    metadata = metadata or {}

    def lookup(field: str) -> Any:
        if is_secret_field(field):
            return None
        if field in event:
            return event[field]
        if field in metadata:
            return metadata[field]
        return None

    summary_parts: list[str] = []
    fields: list[str] = []
    for field in spec.summary_fields:
        value = lookup(field)
        if value is None:
            continue
        summary_parts.append("%s=%s" % (field, redact(value)))
        fields.append(field)
    status = str(event.get("status", "ok") or "ok")
    summary = ", ".join(summary_parts) if summary_parts else "%s (%s)" % (
        spec.tool_name, status)

    expanded: list[str] = []
    for field in (*spec.expanded_fields, *spec.metadata_fields):
        value = lookup(field)
        if value is None:
            continue
        expanded.append("%s: %s" % (field, redact(value)))
        fields.append(field)

    return Presentation(
        tool_name=spec.tool_name,
        summary=summary,
        icon=spec.icon,
        expanded=tuple(expanded),
        fields_used=tuple(fields),
    )


# ---------------------------------------------------------------------------
# D4.11 -- plugin descriptors and the approval gate
# ---------------------------------------------------------------------------

_CAPABILITIES = frozenset({
    "ui", "tools", "providers", "presenters", "settings", "storage",
    "network", "shell", "browser", "memory",
})


@dataclass(frozen=True)
class PluginDescriptor:
    """A plugin contribution; bundled plugins are protected core."""

    plugin_id: str
    name: str
    origin: LayerOrigin
    requires_approval: bool
    enabled: bool
    capabilities: tuple[str, ...]
    resource_paths: tuple[str, ...]
    settings_card: str | None

    @property
    def is_protected(self) -> bool:
        return _origin(self.origin) in PROTECTED_ORIGINS

    def to_public_dict(self) -> dict:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "origin": _origin(self.origin).value,
            "requires_approval": self.requires_approval,
            "enabled": self.enabled,
            "capabilities": list(self.capabilities),
            "resource_paths": list(self.resource_paths),
            "settings_card": self.settings_card,
            "is_protected": self.is_protected,
        }

    to_dict = to_public_dict

    @classmethod
    def from_dict(cls, data: dict) -> "PluginDescriptor":
        data = data or {}
        return make_plugin(
            data.get("plugin_id", ""),
            data.get("name", ""),
            origin=_origin(data.get("origin")),
            requires_approval=data.get("requires_approval", True),
            enabled=data.get("enabled", True),
            capabilities=data.get("capabilities", ()),
            resource_paths=data.get("resource_paths", ()),
            settings_card=data.get("settings_card"),
        )


def validate_plugin(plugin: PluginDescriptor) -> tuple[str, ...]:
    errors: list[str] = []
    if not _IDENTIFIER_RE.match(str(plugin.plugin_id or "")):
        errors.append("plugin id is not a safe identifier")
    if not str(plugin.name or "").strip():
        errors.append("plugin name must not be empty")
    for capability in plugin.capabilities:
        if str(capability) not in _CAPABILITIES:
            errors.append("unknown plugin capability: %s" % capability)
    for path in plugin.resource_paths:
        if not is_contained("plugins", path):
            errors.append("plugin resource path escapes the plugins root")
    if plugin.settings_card is not None and not _IDENTIFIER_RE.match(
            str(plugin.settings_card)):
        errors.append("settings card must be a safe identifier")
    return tuple(errors)


def make_plugin(
    plugin_id: Any,
    name: Any,
    *,
    origin: Any = CORE,
    requires_approval: Any = True,
    enabled: Any = True,
    capabilities: Iterable[Any] = (),
    resource_paths: Iterable[Any] = (),
    settings_card: Any = None,
) -> PluginDescriptor:
    """Build a validated plugin descriptor (D4.11)."""
    descriptor = PluginDescriptor(
        plugin_id=str(plugin_id or ""),
        name=str(name or ""),
        origin=_origin(origin),
        requires_approval=bool(requires_approval),
        enabled=bool(enabled),
        capabilities=tuple(sorted(str(c) for c in capabilities)),
        resource_paths=tuple(_normalize_contained("plugins", p)
                             for p in resource_paths),
        settings_card=(None if settings_card is None
                       else str(settings_card)),
    )
    errors = validate_plugin(descriptor)
    if errors:
        raise ContractValidationError(errors)
    return descriptor


def with_plugin_enabled(plugin: PluginDescriptor, enabled: Any) -> PluginDescriptor:
    """Return a copy with the requested enable state."""
    return replace(plugin, enabled=bool(enabled))


def can_activate_plugin(plugin: PluginDescriptor, *,
                        approved: Any = False) -> bool:
    """Fail-closed extension gate: bundled core is active, others need approval."""
    if not plugin.enabled:
        return False
    origin = _origin(plugin.origin)
    if origin == LayerOrigin.UNKNOWN:
        return False
    if origin in PROTECTED_ORIGINS:
        return True
    if plugin.requires_approval:
        return bool(approved)
    return True


# ---------------------------------------------------------------------------
# Deterministic composition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LayerDescriptor:
    """A typed, ordered contribution bundle from one origin."""

    origin: LayerOrigin
    name: str
    enabled: bool
    providers: tuple[ProviderDescriptor, ...]
    presenters: tuple[PresenterDescriptor, ...]
    plugins: tuple[PluginDescriptor, ...]

    def to_public_dict(self) -> dict:
        return {
            "origin": _origin(self.origin).value,
            "name": self.name,
            "enabled": self.enabled,
            "providers": [p.to_public_dict() for p in self.providers],
            "presenters": [p.to_public_dict() for p in self.presenters],
            "plugins": [p.to_public_dict() for p in self.plugins],
        }


def make_layer(
    origin: Any,
    name: Any,
    *,
    enabled: Any = True,
    providers: Iterable[ProviderDescriptor] = (),
    presenters: Iterable[PresenterDescriptor] = (),
    plugins: Iterable[PluginDescriptor] = (),
) -> LayerDescriptor:
    """Build a layer descriptor; unknown origins are retained but ignored."""
    return LayerDescriptor(
        origin=_origin(origin),
        name=str(name or ""),
        enabled=bool(enabled),
        providers=tuple(providers),
        presenters=tuple(presenters),
        plugins=tuple(plugins),
    )


def _stable_key(item: Any) -> str:
    return json.dumps(item.to_public_dict(), sort_keys=True, ensure_ascii=False)


def _merge_rank(origin: Any) -> tuple[int, int]:
    """Protected origins win; among the rest, the higher layer wins.

    Group 0 is protected core/bundle (smaller sub-rank wins); group 1 holds
    plugin/agent/user contributions (larger precedence number wins, so a
    profile patch can override an extension but can never touch the core).
    """
    resolved = _origin(origin)
    rank = resolved.precedence
    if resolved in PROTECTED_ORIGINS:
        return (0, rank)
    return (1, -rank)


def _winners(items: Iterable[Any], key_of: Any) -> tuple[Any, ...]:
    """Deterministically pick one item per key: protected origin first."""
    best: dict[str, tuple[tuple[tuple[int, int], str], Any]] = {}
    for item in items:
        key = str(key_of(item))
        candidate = (_merge_rank(item.origin), _stable_key(item))
        if key not in best or candidate < best[key][0]:
            best[key] = (candidate, item)
    return tuple(best[key][1] for key in sorted(best))


def merge_providers(providers: Iterable[ProviderDescriptor]) -> tuple[ProviderDescriptor, ...]:
    return _winners(providers, lambda p: p.name)


def merge_presenters(presenters: Iterable[PresenterDescriptor]) -> tuple[PresenterDescriptor, ...]:
    return _winners(presenters, lambda p: p.tool_name)


def merge_plugins(plugins: Iterable[PluginDescriptor]) -> tuple[PluginDescriptor, ...]:
    return _winners(plugins, lambda p: p.plugin_id)


@dataclass(frozen=True)
class Composition:
    """A frozen, keyed result of a deterministic layer merge."""

    providers: tuple[ProviderDescriptor, ...]
    presenters: tuple[PresenterDescriptor, ...]
    plugins: tuple[PluginDescriptor, ...]

    def provider(self, name: Any) -> ProviderDescriptor | None:
        return next((p for p in self.providers if p.name == str(name)), None)

    def presenter(self, tool_name: Any) -> PresenterDescriptor | None:
        return next((p for p in self.presenters if p.tool_name == str(tool_name)), None)

    def plugin(self, plugin_id: Any) -> PluginDescriptor | None:
        return next((p for p in self.plugins if p.plugin_id == str(plugin_id)), None)

    def to_public_dict(self) -> dict:
        return {
            "providers": [p.to_public_dict() for p in self.providers],
            "presenters": [p.to_public_dict() for p in self.presenters],
            "plugins": [p.to_public_dict() for p in self.plugins],
        }

    to_dict = to_public_dict

    @classmethod
    def from_dict(cls, data: dict) -> "Composition":
        """Rebuild and re-merge so a payload cannot smuggle an override."""
        data = data or {}
        providers = [ProviderDescriptor.from_dict(p)
                     for p in data.get("providers", ())]
        presenters = [PresenterDescriptor.from_dict(p)
                      for p in data.get("presenters", ())]
        plugins = [PluginDescriptor.from_dict(p)
                   for p in data.get("plugins", ())]
        return cls(
            providers=merge_providers(providers),
            presenters=merge_presenters(presenters),
            plugins=merge_plugins(plugins),
        )


def compose_layers(layers: Iterable[LayerDescriptor]) -> Composition:
    """Merge layers deterministically; disabled and unknown layers add nothing."""
    providers: list[ProviderDescriptor] = []
    presenters: list[PresenterDescriptor] = []
    plugins: list[PluginDescriptor] = []
    for layer in layers:
        if not layer.enabled or _origin(layer.origin) == LayerOrigin.UNKNOWN:
            continue
        providers.extend(layer.providers)
        presenters.extend(layer.presenters)
        plugins.extend(layer.plugins)
    return Composition(
        providers=merge_providers(providers),
        presenters=merge_presenters(presenters),
        plugins=merge_plugins(plugins),
    )


def validate_composition(composition: Composition) -> tuple[str, ...]:
    errors: list[str] = []
    for kind, items, validator, key_of in (
        ("provider", composition.providers, validate_provider,
         lambda p: p.name),
        ("presenter", composition.presenters, validate_presenter,
         lambda p: p.tool_name),
        ("plugin", composition.plugins, validate_plugin,
         lambda p: p.plugin_id),
    ):
        keys = [key_of(item) for item in items]
        if len(keys) != len(set(keys)):
            errors.append("duplicate %s key in composition" % kind)
        for item in items:
            for error in validator(item):
                errors.append("%s %s: %s" % (kind, key_of(item), error))
    return tuple(errors)


def set_plugin_enabled(composition: Composition, plugin_id: Any,
                       enabled: Any) -> Composition:
    """Enable/disable a plugin; protected core plugins can never be disabled."""
    target = composition.plugin(plugin_id)
    if target is None:
        raise ContractValidationError("unknown plugin: %s" % plugin_id)
    if target.is_protected and not bool(enabled):
        raise ContractValidationError(
            "cannot disable protected core plugin %s" % plugin_id)
    changed = with_plugin_enabled(target, enabled)
    others = [p for p in composition.plugins if p.plugin_id != target.plugin_id]
    return Composition(
        providers=composition.providers,
        presenters=composition.presenters,
        plugins=merge_plugins([*others, changed]),
    )


def render_tool_card(presenters: Iterable[PresenterDescriptor], event: Any = None,
                     metadata: Any = None) -> Presentation:
    """Derive a tool card from events/metadata, using the merged winner."""
    event = event or {}
    tool_name = str(event.get("tool_name", "") or "")
    for spec in merge_presenters(presenters):
        if spec.tool_name == tool_name:
            return present(spec, event, metadata)
    name = tool_name or "unknown"
    return Presentation(
        tool_name=name,
        summary="%s (no presenter)" % name,
        icon="tool",
        expanded=(),
        fields_used=(),
    )


__all__ = [
    "FEATURE_IDS", "PROTECTED_ORIGINS",
    "AGENT", "BUNDLE", "CORE", "PLUGIN", "USER", "UNKNOWN",
    "Composition", "ContractError", "ContractValidationError",
    "LayerDescriptor", "LayerOrigin", "PluginDescriptor", "Presentation",
    "PresenterDescriptor", "ProviderDescriptor", "ProviderKind", "SecretRef",
    "can_activate_plugin", "compose_layers", "endpoint_scope", "is_contained",
    "is_secret_field", "is_secret_reference", "looks_like_secret", "make_layer",
    "make_plugin", "make_presenter", "make_provider", "make_secret_ref",
    "merge_plugins", "merge_presenters", "merge_providers", "parse_secret_ref",
    "present", "redact", "render_tool_card", "safe_join", "set_plugin_enabled",
    "validate_composition", "validate_plugin", "validate_presenter",
    "validate_provider", "with_plugin_enabled",
]
