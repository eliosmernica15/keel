"""Build RELEASE-MANIFEST.json for a Keel desktop release.

Scans a directory of downloaded release artifacts and emits a JSON manifest
with platform, arch, version, filename, size and sha256 for every installer
(plus the SHA256SUMS files, which are copied verbatim). Upload URLs are
included only when a public base URL is supplied; otherwise the field is
"pending" so the manifest can never masquerade as a live release.

Usage:
  python scripts/make_release_manifest.py \
      --artifacts artifacts --version 0.1.0 --tag v0.1.0 \
      [--base-url https://download.keel.example] [--out RELEASE-MANIFEST.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PLATFORM_RULES = [
    ("Keel-Setup-", ".exe", "windows", "x64"),
    ("Keel-", "-macos-arm64.dmg", "macos", "arm64"),
    ("Keel-", "-macos-arm64.zip", "macos", "arm64"),
    ("Keel-", "-linux-x86_64.AppImage", "linux", "x86_64"),
    ("Keel-", "-linux-amd64.deb", "linux", "amd64"),
    ("Keel-", "-linux-x86_64.deb", "linux", "x86_64"),
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def platform_for(name: str) -> tuple[str, str] | None:
    for prefix, suffix, platform, arch in PLATFORM_RULES:
        if name.startswith(prefix) and name.endswith(suffix):
            return platform, arch
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", required=True, help="directory containing release files")
    ap.add_argument("--version", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--base-url", default="", help="public download base, e.g. https://download.keel.app")
    ap.add_argument("--out", default="RELEASE-MANIFEST.json")
    args = ap.parse_args()

    root = Path(args.artifacts)
    if args.tag != f"v{args.version}":
        print(
            f"--tag {args.tag!r} does not match --version {args.version!r} "
            f"(expected v{args.version})",
            file=sys.stderr,
        )
        return 1
    files = sorted(p for p in root.rglob("*") if p.is_file())

    entries = []
    checksum_names: list[str] = []
    for path in files:
        name = path.name
        if name == "RELEASE-MANIFEST.json":
            continue
        if name.startswith("SHA256SUMS") or name == "RELEASE-SHA256SUMS.txt":
            checksum_names.append(name)
            continue
        kind = platform_for(name)
        if kind is None:
            continue
        platform, arch = kind
        entries.append({
            "platform": platform,
            "arch": arch,
            "version": args.version,
            "file": name,
            "bytes": path.stat().st_size,
            "sha256": sha256_of(path),
            "url": f"{args.base_url.rstrip('/')}/{args.tag}/{name}" if args.base_url else "pending",
        })

    if not entries:
        print("no installer files matched the platform rules under", root, file=sys.stderr)
        return 1

    checksums_file = (
        "RELEASE-SHA256SUMS.txt"
        if "RELEASE-SHA256SUMS.txt" in checksum_names
        else (checksum_names[0] if checksum_names else None)
    )
    manifest = {
        "name": "Keel Desktop",
        "version": args.version,
        "tag": args.tag,
        "generated": "release-pipeline",
        "files": entries,
        "checksums_file": checksums_file,
    }

    out = Path(args.out)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {out} ({len(entries)} files, checksums file: {checksums_file})")
    for e in entries:
        print(f"  {e['platform']:8} {e['arch']:4} {e['file']:38} {e['bytes']:>10}  {e['sha256'][:12]}…  {e['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
