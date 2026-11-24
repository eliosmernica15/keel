"""Bundled, versioned offline provider/model catalog.

Catalog data is informational only. It never grants execution capability:
runtime adapters live in keel.providers.registry and are listed separately.

Hardening (production provider audit):
  * the cached document is internal; callers never receive a live reference,
    so a mutated provider entry cannot poison the process-wide cache;
  * every load validates the schema version, entry shapes and the declared
    counts, so a truncated or tampered file fails closed instead of silently
    reporting a different catalog.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .resources import resource_path


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogInfo:
    version: str
    provider_count: int
    model_count: int
    source_name: str
    source_url: str
    license: str
    notice: str


#: Only this catalog schema is understood. A future schema must be added
#: deliberately; an unknown version is never interpreted with old rules.
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1", "1.0"})

_CACHE: dict | None = None


def catalog_path() -> Path:
    return resource_path("catalog", "providers.json")


def _read_and_validate(target: Path) -> dict:
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"cannot load provider catalog at {target}: {exc}") from None
    if not isinstance(doc, dict):
        raise CatalogError("provider catalog must be a JSON object")
    for key in ("schema_version", "catalog_version", "providers", "provider_count",
                "model_count", "source"):
        if key not in doc:
            raise CatalogError(f"provider catalog missing required key: {key}")
    if str(doc["schema_version"]) not in SUPPORTED_SCHEMA_VERSIONS:
        valid = ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
        raise CatalogError(
            f"unsupported provider catalog schema_version "
            f"{doc['schema_version']!r}; supported: {valid}")
    providers = doc["providers"]
    if not isinstance(providers, dict):
        raise CatalogError("provider catalog 'providers' must be an object")
    if not isinstance(doc["source"], Mapping):
        raise CatalogError("provider catalog 'source' must be an object")

    total_models = 0
    for identifier, entry in providers.items():
        if not isinstance(identifier, str) or not identifier:
            raise CatalogError("provider catalog ids must be non-empty strings")
        if not isinstance(entry, Mapping):
            raise CatalogError(f"provider catalog entry {identifier!r} must be an object")
        if entry.get("id") != identifier:
            raise CatalogError(
                f"provider catalog entry {identifier!r} has a mismatched id")
        models = entry.get("models")
        if not isinstance(models, list):
            raise CatalogError(
                f"provider catalog entry {identifier!r} 'models' must be a list")
        if any(not isinstance(model, str) or not model for model in models):
            raise CatalogError(
                f"provider catalog entry {identifier!r} has an invalid "
                "model id in 'models'")
        total_models += len(models)

    for key, actual in (("provider_count", len(providers)),
                        ("model_count", total_models)):
        declared = doc[key]
        if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
            raise CatalogError(f"provider catalog {key} must be a non-negative integer")
        if declared != actual:
            raise CatalogError(
                f"provider catalog {key} is {declared} but the entries contain {actual}")
    return doc


def _document(path: Path | None = None) -> dict:
    """Internal read-only-by-convention view; never returned to callers."""
    global _CACHE
    if path is None:
        if _CACHE is None:
            _CACHE = _read_and_validate(catalog_path())
        return _CACHE
    return _read_and_validate(path)


def load_catalog(*, path: Path | None = None, refresh: bool = False) -> dict:
    """Return an isolated catalog document; mutating it cannot affect later loads."""
    global _CACHE
    if path is None and refresh:
        _CACHE = None
    if path is None:
        return copy.deepcopy(_document())
    return _read_and_validate(path)


def catalog_info(*, path: Path | None = None) -> CatalogInfo:
    doc = _document(path)
    source = doc["source"]
    return CatalogInfo(
        version=str(doc["catalog_version"]),
        provider_count=int(doc["provider_count"]),
        model_count=int(doc["model_count"]),
        source_name=str(source.get("name", "")),
        source_url=str(source.get("url", "")),
        license=str(source.get("license", "")),
        notice=str(doc.get("notice", "")),
    )


def provider_ids(*, path: Path | None = None) -> list[str]:
    return sorted(_document(path)["providers"])


def get_provider(provider: str, *, path: Path | None = None) -> dict | None:
    """Return a copy of one entry; the cached original stays private."""
    if not isinstance(provider, str):
        raise CatalogError("provider id must be a string")
    entry = _document(path)["providers"].get(provider.lower())
    return copy.deepcopy(entry) if entry is not None else None


def model_ids(provider: str, *, path: Path | None = None) -> list[str]:
    entry = get_provider(provider, path=path)
    if entry is None:
        raise CatalogError(f"unknown catalog provider {provider!r}")
    return list(entry["models"])


def has_model(provider: str, model: str, *, path: Path | None = None) -> bool:
    return model in model_ids(provider, path=path)
