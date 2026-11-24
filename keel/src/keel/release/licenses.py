"""Dependency license inventory for proprietary release notices (M1)."""

from __future__ import annotations

import json
import re
import tomllib
from importlib import metadata
from pathlib import Path

from .common import LICENSE_INVENTORY, PROJECT_ROOT


def _python_direct_dependencies() -> list[str]:
    data = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names: list[str] = []
    for requirement in data.get("project", {}).get("dependencies", []):
        match = re.match(r"^[A-Za-z0-9_.-]+", requirement.strip())
        if match:
            names.append(match.group(0))
    return sorted(set(names))


def _python_inventory() -> list[dict]:
    out: list[dict] = []
    for name in _python_direct_dependencies():
        try:
            dist = metadata.distribution(name)
            version = dist.version
            license_value = dist.metadata.get("License") or ""
            classifiers = [
                c for c in dist.metadata.get_all("Classifier", [])
                if c.startswith("License ::")
            ]
            license_text = license_value or " / ".join(classifiers) or "UNKNOWN"
        except metadata.PackageNotFoundError:
            version, license_text = None, "UNKNOWN"
        out.append({"name": name, "version": version,
                    "license": license_text, "ecosystem": "python"})
    return out


def _license_value(entry: dict) -> str:
    value = entry.get("license", "UNKNOWN")
    if isinstance(value, dict):
        return str(value.get("type") or value.get("text") or "UNKNOWN")
    return str(value or "UNKNOWN")


def _installed_electron_licenses() -> dict[tuple[str, str | None], str]:
    """Read package licenses from installed node_modules (lockfiles omit them)."""
    result: dict[tuple[str, str | None], str] = {}
    node_modules = PROJECT_ROOT / "desktop-app" / "node_modules"
    if not node_modules.is_dir():
        return result
    for manifest in node_modules.rglob("package.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = data.get("name")
        if name:
            result[(str(name), data.get("version"))] = _license_value(data)
    return result


def _electron_inventory() -> list[dict]:
    lock_path = PROJECT_ROOT / "desktop-app" / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock.get("packages", {})
    installed = _installed_electron_licenses()
    out: list[dict] = []
    for key, entry in sorted(packages.items()):
        if not key or key == "":
            continue
        name = entry.get("name") or key.rsplit("node_modules/", 1)[-1]
        version = entry.get("version")
        license_text = _license_value(entry)
        if license_text == "UNKNOWN":
            license_text = installed.get((name, version), "UNKNOWN")
        out.append({
            "name": name,
            "version": version,
            "license": license_text,
            "ecosystem": "electron",
            "path": key,
        })
    return out


def collect_inventory() -> dict:
    python = _python_inventory()
    electron = _electron_inventory()
    unresolved = [p["name"] for p in python + electron
                  if p["license"] in ("", "UNKNOWN", "UNLICENSED")]
    return {
        "generator": "keel.release.licenses",
        "source_of_truth": [
            "pyproject.toml",
            "desktop-app/package-lock.json",
            "installed Python distribution metadata",
        ],
        "python": python,
        "electron": electron,
        "unresolved": unresolved,
    }


def write_inventory(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(collect_inventory(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def licenses_command(args) -> int:
    out = Path(args.out)
    if str(out) in ("release", ""):
        # Default output is the canonical inventory path read by sbom_export().
        path = write_inventory(LICENSE_INVENTORY)
    else:
        if not out.is_absolute():
            out = PROJECT_ROOT / out
        path = write_inventory(out / "DEPENDENCY-LICENSES.json")
    inventory = json.loads(path.read_text(encoding="utf-8"))
    print(f"wrote {path} ({len(inventory['electron'])} electron, "
          f"{len(inventory['python'])} python packages)")
    if inventory["unresolved"]:
        print("unresolved licenses: " + ", ".join(inventory["unresolved"][:20]))
    return 0
