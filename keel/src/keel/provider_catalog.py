"""Bundled, versioned offline provider/model catalog.

Catalog data is informational only. It never grants execution capability:
runtime adapters live in keel.providers.registry and are listed separately.
"""

from __future__ import annotations

import json
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


_CACHE: dict | None = None


def catalog_path() -> Path:
    return resource_path("catalog", "providers.json")


def load_catalog(*, path: Path | None = None, refresh: bool = False) -> dict:
    global _CACHE
    if path is None and _CACHE is not None and not refresh:
        return _CACHE
    target = path or catalog_path()
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"cannot load provider catalog at {target}: {exc}") from None
    for key in ("schema_version", "catalog_version", "providers", "provider_count",
                "model_count", "source"):
        if key not in doc:
            raise CatalogError(f"provider catalog missing required key: {key}")
    if not isinstance(doc["providers"], dict):
        raise CatalogError("provider catalog 'providers' must be an object")
    if path is None:
        _CACHE = doc
    return doc


def catalog_info(*, path: Path | None = None) -> CatalogInfo:
    doc = load_catalog(path=path)
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
    return sorted(load_catalog(path=path)["providers"])


def get_provider(provider: str, *, path: Path | None = None) -> dict | None:
    return load_catalog(path=path)["providers"].get(provider.lower())


def model_ids(provider: str, *, path: Path | None = None) -> list[str]:
    entry = get_provider(provider, path=path)
    if entry is None:
        raise CatalogError(f"unknown catalog provider {provider!r}")
    return list(entry.get("models", []))


def has_model(provider: str, model: str, *, path: Path | None = None) -> bool:
    return model in model_ids(provider, path=path)
