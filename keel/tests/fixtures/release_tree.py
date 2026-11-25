"""Deterministic, test-only release artifact trees.

Production installers are build outputs under ``.gitignore`` and are absent
from a clean checkout.  The helpers here create small stand-ins in pytest's
tmp_path with *real* SHA-256/SHA-512 hashes, a real signed-by-nothing manifest
and a real executable sidecar, so the integrity checks execute against genuine
bytes.  No binaries are committed and no developer untracked directory is
needed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

CANONICAL_VERSION = "0.1.1"

# Same names/count as the documented seven-checksum production release set.
# The 0.1.0 blockmap is required by the air-gap tamper test.
CHECKSUMMED_FILES = (
    "Keel-Setup-0.1.0.exe",
    "Keel-Setup-0.1.0.exe.blockmap",
    "Keel-Setup-0.1.1.exe",
    "Keel-Setup-0.1.1.exe.blockmap",
    "keel-app.jpg",
    "keel-settings-general.jpg",
    "keel-settings-providers.jpg",
)

SIDECAR = Path("keel-sidecar") / "keel.exe"
PUBLISHED_AT = "2026-01-01T00:00:00Z"


def reported_sidecar_version(executable: str | Path | None = None) -> str:
    """Return the version an executable reports for ``--version``.

    Used to keep the synthetic manifest truthful when the real sidecar binary
    from a production build is unavailable: the manifest version is derived
    from the executable that is actually shipped into the fixture.
    """
    result = subprocess.run(
        [str(executable or sys.executable), "--version"],
        capture_output=True, text=True, timeout=30, check=True)
    return result.stdout.strip().split()[-1]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_release_tree(base: str | Path, *, version: str = CANONICAL_VERSION,
                       sidecar_executable: str | Path | None = None,
                       include_sidecar: bool = True,
                       ) -> tuple[Path, Path]:
    """Create ``base/release`` and ``base/dist``; return ``(release, dist)``.

    Every checksum, file size, sha512 and version in the generated metadata is
    computed from the bytes actually written to disk.  The function is pure
    with respect to its arguments and the interpreter version (when the
    sidecar version is detected), so repeated runs are byte-identical.
    """
    root = Path(base)
    release = root / "release"
    dist = root / "dist"
    release.mkdir(parents=True, exist_ok=True)
    dist.mkdir(parents=True, exist_ok=True)

    payloads: dict[str, bytes] = {}
    for name in CHECKSUMMED_FILES:
        data = (f"KEEL-TEST-ARTIFACT\nname={name}\nversion={version}\n").encode("utf-8")
        (release / name).write_bytes(data)
        payloads[name] = data

    installer = f"Keel-Setup-{version}.exe"
    if installer not in payloads:
        data = payloads["Keel-Setup-0.1.1.exe"]
        (release / installer).write_bytes(data)
        payloads[installer] = data

    sums = "".join(
        f"{_sha256(payloads[name])}  {name}\n"
        for name in sorted(payloads) if name in CHECKSUMMED_FILES)
    sums += f"{_sha256(payloads[installer])}  {installer}\n" if installer not in CHECKSUMMED_FILES else ""
    (release / "RELEASE-SHA256SUMS.txt").write_text(sums, encoding="utf-8")

    manifest = {
        "name": "Keel Desktop",
        "version": version,
        "tag": f"v{version}",
        "edition": "standard",
        "generated": "test-fixture",
        "published_at": PUBLISHED_AT,
        "min_version": "0.1.0",
        "blocked_versions": [],
        "security_advisories": {},
        "rollout": {"mode": "full", "percentage": 100, "bucket_count": 100},
        "files": [{
            "platform": "windows",
            "arch": "x64",
            "version": version,
            "file": installer,
            "bytes": len(payloads[installer]),
            "sha256": _sha256(payloads[installer]),
            "url": f"https://example.invalid/{installer}",
        }],
        "checksums_file": "RELEASE-SHA256SUMS.txt",
    }
    (release / "RELEASE-MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (release / "DEPENDENCY-LICENSES.json").write_text(
        json.dumps({"tzdata": "Apache-2.0", "cryptography": "Apache-2.0"},
                   indent=2) + "\n", encoding="utf-8")

    # The update feed describes the bytes that are actually in dist/.
    shutil.copyfile(release / installer, dist / installer)
    digest = base64.b64encode(hashlib.sha512(payloads[installer]).digest()).decode()
    size = len(payloads[installer])
    (dist / "latest.yml").write_text(
        f"version: {version}\n"
        "files:\n"
        f"  - url: {installer}\n"
        f"    sha512: {digest}\n"
        f"    size: {size}\n"
        f"path: {installer}\n"
        f"sha512: {digest}\n"
        f"releaseDate: '{PUBLISHED_AT}'\n",
        encoding="utf-8")

    unpacked = dist / "win-unpacked"
    unpacked.mkdir(exist_ok=True)
    (unpacked / "README.txt").write_text("Keel test payload\n", encoding="utf-8")

    if include_sidecar:
        sidecar = dist / SIDECAR
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sidecar_executable or sys.executable, sidecar)
        if sys.platform == "win32":
            # A copied python.exe resolves its runtime DLL from PATH, but
            # copying the adjacent DLLs makes the fixture self-contained.
            source = Path(sidecar_executable or sys.executable).parent
            for dll in source.glob("python*.dll"):
                shutil.copy2(dll, sidecar.parent / dll.name)

    return release, dist
