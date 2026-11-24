"""Typed contracts that bridge the real v6 backend modules through the hub.

This module is a *consumer-side* adapter. It never edits or imports a sibling
backend module by name at import time, stays stdlib-only and offline, and has
three responsibilities:

1. **Canonical envelopes.** The hub serialises typed dataclass results as
   ``{"type": ..., "fields": ...}``. :func:`encode` produces that shape,
   :func:`decode_envelope` returns the minimal dict form accepted by
   object-taking consumers, and :func:`rehydrate` rebuilds the owning module's
   real class so a typed consumer such as ``e3_backend.check_route`` accepts
   the value again (audit gap G1).

2. **Normalised model identity.** ``ModelReference`` (small_groups),
   ``ModelRoute`` (e3) and bare discovery ids (e6) are converted to and from a
   single frozen :class:`ModelId` value (audit gap G3).

3. **Signature-derived schemas.** :func:`function_schema` turns a real
   callable's ``inspect.signature`` and annotations into a deterministic,
   JSON-serialisable object schema (audit gap G4).

Every helper is deterministic and side-effect free; none of them performs I/O
or reaches the network.
"""

from __future__ import annotations

import ast
import collections.abc
import dataclasses
import enum
import inspect
import re
import types
import typing
from dataclasses import dataclass
from typing import Any, Literal, get_args, get_origin, get_type_hints

__all__ = [
    "BackendContractError",
    "ENVELOPE_KEYS",
    "ModelId",
    "annotation_schema",
    "coerce_value",
    "decode_envelope",
    "encode",
    "from_discovery",
    "from_model_reference",
    "from_model_route",
    "from_string",
    "from_any",
    "function_schema",
    "is_envelope",
    "model_id_contract",
    "normalize_model_ids",
    "rehydrate",
    "to_discovery",
    "to_model_reference",
    "to_route",
]


class BackendContractError(ValueError):
    """Typed error for invalid cross-module contract values."""


# ---------------------------------------------------------------------------
# 1. Canonical typed envelope
# ---------------------------------------------------------------------------

ENVELOPE_KEYS = frozenset({"type", "fields"})

#: The canonical envelope is ``{"type": <class name>, "fields": {...}}``.
#: ``hub._jsonable`` emits exactly this shape; :func:`encode` is the single
#: public encoder so producers and decoders cannot drift apart.
ENVELOPE_FORMAT = {
    "type": "object",
    "required": ["type", "fields"],
    "additionalProperties": False,
    "properties": {
        "type": {"type": "string", "description": "owning class __name__"},
        "fields": {"type": "object", "description": "JSON-able instance attributes"},
    },
}


def encode(value: Any) -> Any:
    """Encode a real function result as deterministic JSON-able data.

    The output shape is deliberately identical to the historical
    ``backend_hub._jsonable`` contract so existing callers are unaffected.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if hasattr(value, "__dict__"):
        return {
            "type": type(value).__name__,
            "fields": {k: encode(v) for k, v in vars(value).items()},
        }
    return repr(value)


def is_envelope(value: Any) -> bool:
    """True iff *value* is exactly the canonical ``type``/``fields`` envelope."""
    return (
        isinstance(value, dict)
        and set(value) == ENVELOPE_KEYS
        and isinstance(value["type"], str)
        and bool(value["type"])
        and isinstance(value["fields"], dict)
    )


def _decode_deep(value: Any) -> Any:
    if is_envelope(value):
        return {k: _decode_deep(v) for k, v in value["fields"].items()}
    if isinstance(value, list):
        return [_decode_deep(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _decode_deep(v) for k, v in value.items()}
    return value


def decode_envelope(value: Any, *, expected_type: str | type | None = None) -> dict:
    """Return the minimal dict form of an envelope (nested envelopes included).

    ``ModelReference.from_object`` and other dict-taking consumers accept this
    shape. Passing ``expected_type`` makes the decoder fail closed on a
    mismatched envelope instead of silently handing a wrong type downstream.
    """
    if not is_envelope(value):
        raise BackendContractError("value is not a canonical type/fields envelope")
    if expected_type is not None:
        name = value["type"]
        wanted = expected_type if isinstance(expected_type, str) else expected_type.__name__
        if not _type_name_matches(name, wanted):
            raise BackendContractError(
                f"envelope type {name!r} does not match expected {wanted!r}")
    return {k: _decode_deep(v) for k, v in value["fields"].items()}


def _type_name_matches(actual: str, expected: str | type) -> bool:
    wanted = expected if isinstance(expected, str) else expected.__name__
    return actual == wanted or actual.endswith("." + wanted)


# Annotation names that can appear as strings under ``from __future__
# annotations``. Unknown names are left untouched rather than guessed at.
_NAME_TYPES: dict[str, Any] = {
    "Any": Any,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "bytes": bytes,
    "dict": dict,
    "list": list,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "None": type(None),
    "NoneType": type(None),
    "Mapping": collections.abc.Mapping,
    "Sequence": collections.abc.Sequence,
    "Iterable": collections.abc.Iterable,
    "Callable": collections.abc.Callable,
}


def _resolve(annotation: Any) -> Any:
    """Resolve a possibly-string annotation to a runtime type, or ``None``."""
    if not isinstance(annotation, str):
        return annotation
    text = annotation.strip().strip("'\"")
    if "[" in text:
        text = text.split("[", 1)[0].strip()
    parts = [part.strip() for part in text.split("|")]
    resolved = [_NAME_TYPES.get(part) for part in parts if part]
    resolved = [item for item in resolved if item is not None]
    if not resolved:
        return None
    if len(resolved) == 1:
        return resolved[0]
    return typing.Union[tuple(resolved)]


def _hints(obj: Any) -> dict[str, Any]:
    try:
        return get_type_hints(obj)
    except Exception:
        raw = dict(getattr(obj, "__annotations__", {}) or {})
        if dataclasses.is_dataclass(obj):
            for field in dataclasses.fields(obj):
                raw.setdefault(field.name, field.type)
        return raw


def _collection_from_repr(value: Any, target: Any) -> Any:
    """Undo the hub's historical ``repr()`` fallback for frozenset/set fields."""
    if not isinstance(value, str):
        return value
    match = re.match(r"^(frozenset|set)\((.*)\)$", value.strip(), re.DOTALL)
    if not match:
        return value
    try:
        parsed = ast.literal_eval(match.group(2))
    except (ValueError, SyntaxError):
        return value
    if target is frozenset:
        return frozenset(parsed)
    if target is set:
        return set(parsed)
    return value


def _coerce(value: Any, annotation: Any) -> Any:
    """Recursively turn envelope values into the target annotation's shape."""
    if annotation is inspect.Parameter.empty or annotation is None:
        return value
    resolved = _resolve(annotation)
    if resolved is None or resolved is Any:
        return value
    origin = get_origin(resolved)
    if origin is typing.Union or isinstance(resolved, types.UnionType):
        args = [arg for arg in get_args(resolved)]
        if value is None:
            return None
        classes = [arg for arg in args if isinstance(arg, type) and arg is not type(None)]
        for arg in classes:
            if is_envelope(value) and _type_name_matches(value["type"], arg):
                return rehydrate(value, arg)
        return value
    if origin in (list, tuple, set, frozenset, collections.abc.Sequence,
                  collections.abc.Iterable):
        restored = _collection_from_repr(value, origin)
        if restored is not value:
            return restored
        if isinstance(value, (list, tuple, set, frozenset)):
            if origin is frozenset:
                return frozenset(value)
            if origin is set:
                return set(value)
            if origin is tuple:
                return tuple(value)
            return list(value)
        return value
    if isinstance(resolved, type) and resolved not in (dict, object):
        if is_envelope(value) and _type_name_matches(value["type"], resolved):
            return rehydrate(value, resolved)
    return value


def coerce_value(value: Any, annotation: Any) -> Any:
    """Public entry point for annotation-directed envelope coercion."""
    return _coerce(value, annotation)


def rehydrate(value: Any, target: str | type, *, module: Any = None) -> Any:
    """Rebuild the owning module's real typed instance from an envelope.

    ``target`` may be the class itself or its name (resolved against *module*).
    Constructor arguments are matched by name and coerced using the class's
    annotations, so ``{"type": "ModelRoute", "fields": {...}}`` becomes a real
    ``e3_backend.ModelRoute`` that ``check_route`` accepts.
    """
    if isinstance(target, str):
        cls = getattr(module, target, None) if module is not None else None
        if cls is None:
            cls = _NAME_TYPES.get(target)
        if not isinstance(cls, type):
            raise BackendContractError(f"cannot resolve target type {target!r}")
    else:
        cls = target
    if is_envelope(value):
        cls_name = value["type"]
        if not _type_name_matches(cls_name, cls):
            raise BackendContractError(
                f"envelope type {cls_name!r} is not {cls.__name__!r}")
        fields = decode_envelope(value)
    elif isinstance(value, dict):
        fields = dict(value)
    else:
        raise BackendContractError(
            f"cannot rehydrate {type(value).__name__} into {cls.__name__}")
    try:
        signature = inspect.signature(cls)
    except (TypeError, ValueError) as exc:
        raise BackendContractError(
            f"{cls.__name__} has no introspectable constructor") from exc
    hints = _hints(cls)
    ctor_hints = _hints(cls.__init__)
    kwargs: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    for name, param in signature.parameters.items():
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            extras.update({k: v for k, v in fields.items() if k not in kwargs})
            continue
        if name in fields:
            annotation = hints.get(name, ctor_hints.get(name, param.annotation))
            kwargs[name] = _coerce(fields[name], annotation)
        elif param.default is inspect.Parameter.empty:
            raise BackendContractError(
                f"missing field {name!r} to rehydrate {cls.__name__}")
    kwargs.update(extras)
    try:
        return cls(**kwargs)
    except Exception as exc:
        raise BackendContractError(
            f"rehydrating {cls.__name__} failed: {exc}") from exc


# ---------------------------------------------------------------------------
# 2. Normalised model identity (G3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelId:
    """One canonical model identity across all backend representations.

    ``provider=''`` means a discovery id with no provider context (it cannot be
    routed until a caller supplies one). ``extras`` is a sorted tuple of pairs
    so the value is hashable and its serialised form is deterministic.
    """

    provider: str = ""
    model: str = ""
    variant: str | None = None
    extras: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise BackendContractError("model id must have a non-empty model")
        if not isinstance(self.provider, str):
            raise BackendContractError("model id provider must be a string")

    @property
    def qualified(self) -> str:
        """``provider/model`` (bare model when no provider is known)."""
        return f"{self.provider}/{self.model}" if self.provider else self.model

    @property
    def string(self) -> str:
        """``provider/model#variant`` form used by ModelReference."""
        return f"{self.qualified}#{self.variant}" if self.variant else self.qualified

    def as_dict(self) -> dict[str, Any]:
        """Canonical dict form accepted by ``ModelReference.from_object``."""
        result: dict[str, Any] = {"provider": self.provider, "model": self.model}
        if self.variant:
            result["variant"] = self.variant
        result.update(self.extras)
        return result

    def __str__(self) -> str:
        return self.string


def _extras_from(payload: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    known = {"provider", "model", "variant", "raw"}
    return tuple(sorted(
        (str(k), encode(v)) for k, v in payload.items() if k not in known
    ))


def from_string(text: str) -> ModelId:
    """Parse ``provider/model#variant`` or a bare discovery id."""
    if not isinstance(text, str) or not text.strip():
        raise BackendContractError("model identifier must be a non-empty string")
    main, separator, variant = text.strip().partition("#")
    if "/" in main:
        provider, model = main.split("/", 1)
        provider, model = provider.strip(), model.strip()
        if not provider or not model:
            raise BackendContractError(f"invalid model identifier {text!r}")
    else:
        provider, model = "", main.strip()
        if not model:
            raise BackendContractError(f"invalid model identifier {text!r}")
    if separator and not variant.strip():
        raise BackendContractError(f"invalid model variant in {text!r}")
    return ModelId(provider, model, variant.strip() or None)


def from_model_reference(value: Any) -> ModelId:
    """Convert small_groups.ModelReference (object or ``to_dict`` output)."""
    if isinstance(value, ModelId):
        return value
    if isinstance(value, str):
        return from_string(value)
    if is_envelope(value):
        value = decode_envelope(value)
    if isinstance(value, dict):
        provider = str(value.get("provider") or "")
        model = value.get("model")
        if not isinstance(model, str) or not model:
            raise BackendContractError("model reference has no 'model'")
        variant = value.get("variant")
        return ModelId(provider, model, variant or None, _extras_from(value))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return from_model_reference(to_dict())
    provider = getattr(value, "provider", None)
    model = getattr(value, "model", None)
    if provider is not None or model is not None:
        return ModelId(str(provider or ""), str(model or ""),
                       getattr(value, "variant", None))
    raise BackendContractError(f"not a model reference: {type(value).__name__}")


def from_model_route(value: Any) -> ModelId:
    """Convert e3_backend.ModelRoute (typed, enveloped or dict form)."""
    return from_model_reference(value)


def from_discovery(value: Any) -> ModelId:
    """Convert a bare discovery id (e6 ``parse_models_response`` output)."""
    if isinstance(value, dict) and "id" in value:
        value = value["id"]
    if isinstance(value, (tuple, list)) and len(value) == 1:
        value = value[0]
    if not isinstance(value, str) or not value.strip():
        raise BackendContractError("discovery model id must be a non-empty string")
    return ModelId(provider="", model=value.strip())


def from_any(value: Any) -> ModelId:
    """Dispatch across every supported model-id representation."""
    if isinstance(value, ModelId):
        return value
    if isinstance(value, str):
        return from_string(value)
    if isinstance(value, dict):
        return from_model_reference(value)
    if hasattr(value, "provider") and hasattr(value, "model"):
        return from_model_reference(value)
    if callable(getattr(value, "to_dict", None)):
        return from_model_reference(value)
    raise BackendContractError(
        f"unsupported model-id representation: {type(value).__name__}")


def to_model_reference(model: ModelId) -> dict[str, Any]:
    """Canonical dict accepted by ``ModelReference.from_object``."""
    return from_model_reference(model).as_dict()


def to_route(model: ModelId) -> str:
    """``provider/model`` string accepted by ``parse_model_route``/check_route."""
    mid = from_model_reference(model)
    if not mid.provider:
        raise BackendContractError("a discovery id has no provider; cannot route it")
    return mid.qualified


def to_discovery(model: ModelId) -> str:
    """Bare model id used by discovery/compatibility checks."""
    return from_model_reference(model).model


def _looks_like_model_dict(value: dict[str, Any]) -> bool:
    return "model" in value and "provider" in value


def normalize_model_ids(value: Any, *, strings: bool = False) -> Any:
    """Recursively canonicalise model-id-shaped values; leave others intact.

    ``strings`` is off by default so ordinary result strings are never mangled.
    The hub opts in for typed results only (``invoke(..., normalize_model_id=True)``).
    """
    if isinstance(value, ModelId):
        return value.as_dict()
    if is_envelope(value):
        type_name = value["type"].lower()
        if "model" in type_name or "route" in type_name or "reference" in type_name:
            fields = decode_envelope(value)
            if _looks_like_model_dict(fields):
                return from_model_reference(fields).as_dict()
        return {k: normalize_model_ids(v, strings=strings)
                for k, v in value["fields"].items()}
    if isinstance(value, dict):
        if _looks_like_model_dict(value):
            return from_model_reference(value).as_dict()
        return {str(k): normalize_model_ids(v, strings=strings)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_model_ids(v, strings=strings) for v in value]
    if strings and isinstance(value, str) and ("/" in value or "#" in value):
        return from_string(value).as_dict()
    if not isinstance(value, (str, int, float, bool)) and value is not None:
        if hasattr(value, "provider") and hasattr(value, "model"):
            return from_model_reference(value).as_dict()
    return value


def model_id_contract() -> dict[str, Any]:
    """Machine-readable description of the normalised model-id contract."""
    return {
        "type": "ModelId",
        "fields": ["provider", "model", "variant", "extras"],
        "representations": {
            "model_reference": {
                "example": {"provider": "anthropic", "model": "claude-sonnet-4"},
                "converter": "from_model_reference",
            },
            "model_route": {
                "example": {
                    "type": "ModelRoute",
                    "fields": {"provider": "anthropic", "model": "claude-sonnet-4"},
                },
                "converter": "from_model_route",
            },
            "discovery_id": {
                "example": "claude-sonnet-4",
                "converter": "from_discovery",
            },
            "string": {
                "example": "anthropic/claude-sonnet-4#fast",
                "converter": "from_string",
            },
        },
        "converters": [
            "from_string", "from_model_reference", "from_model_route",
            "from_discovery", "from_any", "to_model_reference", "to_route",
            "to_discovery",
        ],
        "envelope_format": dict(ENVELOPE_FORMAT),
    }


# ---------------------------------------------------------------------------
# 3. Signature-derived schemas (G4)
# ---------------------------------------------------------------------------


def _default_json(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_default_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _default_json(v) for k, v in value.items()}
    return repr(value)


def annotation_schema(annotation: Any) -> dict[str, Any]:
    """Deterministic JSON-schema fragment for one Python annotation."""
    original = annotation
    if annotation is inspect.Parameter.empty or annotation is None:
        return {}
    resolved = _resolve(annotation)
    if resolved is None:
        return {"x-annotation": str(original)}
    if resolved is Any:
        return {}
    if resolved is type(None):
        return {"type": "null"}
    origin = get_origin(resolved)
    args = get_args(resolved)
    if origin is Literal:
        return {"type": "string", "enum": [_default_json(v) for v in args]}
    if origin is typing.Union or isinstance(resolved, types.UnionType):
        return {"anyOf": [annotation_schema(arg) for arg in args]}
    if origin in (list, tuple, set, frozenset, collections.abc.Sequence,
                  collections.abc.Iterable):
        item = annotation_schema(args[0]) if args else {}
        return {"type": "array", "items": item}
    if origin is dict or origin is collections.abc.Mapping:
        return {"type": "object"}
    if isinstance(resolved, type):
        if issubclass(resolved, enum.Enum):
            return {"type": "string",
                    "enum": [_default_json(member.value) for member in resolved]}
        if issubclass(resolved, bool):
            return {"type": "boolean"}
        if issubclass(resolved, int):
            return {"type": "integer"}
        if issubclass(resolved, float):
            return {"type": "number"}
        if issubclass(resolved, str):
            return {"type": "string"}
        if issubclass(resolved, (dict, collections.abc.Mapping)):
            return {"type": "object"}
        if issubclass(resolved, (list, tuple, set, frozenset,
                                 collections.abc.Sequence)):
            return {"type": "array"}
        return {
            "type": "object",
            "x-class": f"{resolved.__module__}.{resolved.__qualname__}",
        }
    return {"x-annotation": str(original)}


def function_schema(function: Any) -> dict[str, Any]:
    """Signature-derived schema for a real callable, with no execution.

    ``invoke`` calls ``fn(**params)``, so the parameter names are the actual
    JSON bridge contract; this schema makes them machine-discoverable.
    """
    signature = inspect.signature(function)
    hints = _hints(function)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in signature.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL,
                          inspect.Parameter.VAR_KEYWORD):
            continue
        schema = annotation_schema(hints.get(name, param.annotation))
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            schema = dict(schema)
            schema["default"] = _default_json(param.default)
        if param.kind is inspect.Parameter.KEYWORD_ONLY:
            schema = dict(schema)
            schema["x-parameter-kind"] = "keyword-only"
        properties[name] = schema
    returns = hints.get("return", signature.return_annotation)
    schema = {
        "type": "object",
        "signature": str(signature),
        "properties": properties,
        "required": required,
        "additionalProperties": False,
        "returns": annotation_schema(returns),
    }
    doc = inspect.getdoc(function) or ""
    if doc:
        schema["description"] = doc.splitlines()[0]
    return schema
