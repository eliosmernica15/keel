"""Distribution hardening: air-gapped bundles, static repos, portable builds (C12).

All functions describe and verify local artifacts; nothing is published or
uploaded. Signing uses the existing release signing helpers with a caller-
supplied public key.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def airgap_bundle(artifacts: list[str | Path], base: str | Path) -> dict:
    """Describe an offline bundle of already-staged artifacts."""
    base = Path(base)
    entries = []
    for name in artifacts:
        path = base / name
        if not path.is_file():
            continue
        entries.append({
            "file": str(name),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return {"format": "keel-airgap-v1", "files": entries,
            "note": "Sideload only from a trusted source; verify signatures."}


def static_repo_layout(root: str | Path, distro: str = "apt") -> dict:
    """Describe the directory layout for a signed static APT/YUM repo."""
    root = Path(root)
    layout = {
        "apt": ["dists/stable/Release", "dists/stable/main/binary-amd64/Packages",
                "pool/"],
        "yum": ["repodata/repomd.xml", "Packages/"],
    }[distro if distro in ("apt", "yum") else "apt"]
    present = {name: (root / name).exists() for name in layout}
    return {"distro": distro, "expected": layout, "present": present,
            "complete": all(present.values())}


def portable_manifest(version: str, platform: str) -> dict:
    return {"name": f"Keel-{version}-{platform}-portable",
            "version": version, "platform": platform,
            "format": "zip", "portable": True,
            "note": "No install; extract and run. Settings stay in the bundle."}


def write_bundle_index(doc: dict, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return target
