"""Fail if Keel's version is inconsistent across the repo.

Sources of truth that must all agree:
  1. keel/pyproject.toml            [project] version
  2. keel/desktop-app/package.json  version
  3. keel/site/download.json        version + tag (tag must be "v" + version)
  4. keel/desktop/src-tauri/tauri.conf.json  version
  5. keel/desktop-app/package-lock.json      root "version"
  6. keel/src/keel/__init__.py               __version__

Usage:
  python scripts/check_version_sync.py            # compare all sources
  python scripts/check_version_sync.py --tag vX.Y.Z   # also require tag == vX.Y.Z

Exits 0 and prints the agreed version on success; exits 1 with a diff on
mismatch. Run from keel/ (the script resolves paths relative to itself).
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    versions: dict[str, str] = {}

    pyproject = load_toml(ROOT / "pyproject.toml")
    versions["pyproject.toml"] = pyproject["project"]["version"]

    desktop = load_json(ROOT / "desktop-app" / "package.json")
    versions["desktop-app/package.json"] = desktop["version"]

    lock = load_json(ROOT / "desktop-app" / "package-lock.json")
    versions["desktop-app/package-lock.json"] = lock.get("version", "")

    site = load_json(ROOT / "site" / "download.json")
    versions["site/download.json (version)"] = site.get("version", "")
    site_tag = site.get("tag", "")

    tauri = load_json(ROOT / "desktop" / "src-tauri" / "tauri.conf.json")
    versions["desktop/src-tauri/tauri.conf.json"] = tauri.get("version", "")

    package_init = (ROOT / "src" / "keel" / "__init__.py").read_text(
        encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', package_init, re.MULTILINE)
    versions["src/keel/__init__.py"] = match.group(1) if match else ""

    if "--tag" in sys.argv:
        idx = sys.argv.index("--tag")
        tag = sys.argv[idx + 1]
        versions["git tag"] = tag[1:] if tag.startswith("v") else tag

    distinct = set(versions.values())
    if len(distinct) != 1:
        print("VERSION MISMATCH", file=sys.stderr)
        for src, v in sorted(versions.items()):
            print(f"  {src:38} {v}", file=sys.stderr)
        return 1

    version = distinct.pop()
    if site_tag != f"v{version}":
        print(f"download.json tag {site_tag!r} != 'v{version}'", file=sys.stderr)
        return 1

    print(f"OK - all sources agree on version {version} (tag v{version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
