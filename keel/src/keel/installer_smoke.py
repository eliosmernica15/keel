"""Installer smoke-test harness (C13.4).

Validates locally staged installer artifacts: expected file presence, checksums
in the release manifest, upgrade/rollback metadata hooks. Actual clean-VM
execution belongs in CI after a push (not authorized here), so this harness
reports what it can verify locally and what remains CI-only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

EXPECTED = {
    "windows": "Keel-Setup-{version}.exe",
    "macos-arm64": "Keel-{version}-macos-arm64.dmg",
    "macos-x64": "Keel-{version}-macos-x64.dmg",
    "linux-rpm": "keel-{version}.x86_64.rpm",
}


@dataclass
class SmokeCheck:
    target: str
    ok: bool
    detail: str


def check_manifest(release_dir: str | Path, version: str) -> list[SmokeCheck]:
    root = Path(release_dir)
    manifest_path = root / "RELEASE-MANIFEST.json"
    checks: list[SmokeCheck] = []
    if not manifest_path.is_file():
        return [SmokeCheck("manifest", False, "RELEASE-MANIFEST.json missing")]
    try:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [SmokeCheck("manifest", False, f"unreadable: {exc}")]
    files = {Path(entry.get("file", "")).name: entry
             for entry in doc.get("files", []) if isinstance(entry, dict)}

    for target, template in EXPECTED.items():
        name = template.format(version=version)
        entry = files.get(name)
        if entry is None:
            checks.append(SmokeCheck(target, False, f"{name} not in manifest"))
            continue
        expected = str(entry.get("sha256", "")).lower()
        artifact = root / name
        if not artifact.is_file():
            checks.append(SmokeCheck(target, False, f"{name} not staged"))
            continue
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        checks.append(SmokeCheck(
            target, actual == expected,
            "checksum OK" if actual == expected else "checksum mismatch"))

    # Upgrade/rollback hooks are declared in the manifest policy fields.
    policy_ok = "min_version" in doc and "blocked_versions" in doc
    checks.append(SmokeCheck("upgrade_policy", policy_ok,
                             "min/blocked versions present"
                             if policy_ok else "policy fields missing"))
    return checks


def ci_only_checks() -> list[str]:
    return [
        "clean-VM install on each OS/architecture",
        "upgrade from every prior release",
        "rollback after failed start",
    ]
