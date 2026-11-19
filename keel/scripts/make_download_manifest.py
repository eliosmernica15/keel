"""Build the public /download manifest from verified release artifacts.

This is the bridge between the release pipeline and the website: it reads the
installers that were built, uploaded and checksum-verified, and emits the JSON
document that /ui/download.js renders. A channel is only marked available when
its primary file exists, the public base URL is HTTPS, and size + SHA-256 are
known. Anything less is rejected instead of being published as downloadable.

Usage:
  python scripts/make_download_manifest.py \
      --artifacts release --version 0.1.0 --tag v0.1.0 \
      --base-url https://download.keel.app --out download.json

The workflow runs this only *after* verify_public_release.py has downloaded
every public object and matched its SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

REQUIRED = {
    "windows": ["Keel-Setup-{version}.exe"],
    "macos": [
        "Keel-{version}-macos-arm64.dmg",
        "Keel-{version}-macos-arm64.zip",
    ],
    "linux": [
        "Keel-{version}-linux-x86_64.AppImage",
        "Keel-{version}-linux-amd64.deb",
    ],
}

# electron-builder has shipped both spellings for Linux x64 deb artifacts.
LINUX_DEB_ALTERNATES = ["Keel-{version}-linux-x86_64.deb"]

NOTES = {
    "windows": (
        "Unsigned NSIS installer for Windows x64. Windows SmartScreen will "
        "warn until code signing is configured."
    ),
    "macos": (
        "Unsigned DMG for Apple Silicon. macOS Gatekeeper will block the "
        "first launch until you allow it in System Settings -> Privacy & "
        "Security. Intel Macs are not supported by this build."
    ),
    "linux": (
        "AppImage for x86-64. You may need to chmod +x before running it. "
        "Unsigned; your distribution may show a policy warning."
    ),
}

INSTALLATION = {
    "windows": (
        "Run Keel-Setup-{version}.exe. If SmartScreen appears, choose "
        "More info -> Run anyway. Launch Keel from the Start Menu or the "
        "Desktop shortcut."
    ),
    "macos": (
        "Open the DMG, drag Keel into Applications, then right-click Keel "
        "and choose Open the first time (Gatekeeper). The ZIP is an "
        "alternative archive of the same app."
    ),
    "linux": (
        "Make the AppImage executable and run it. On Debian/Ubuntu the .deb "
        "can be installed with your package manager instead."
    ),
}

ALTERNATIVE_LABELS = {
    ".zip": "ZIP archive",
    ".deb": "Debian/Ubuntu package (.deb)",
}

NAME = {
    "windows": "Windows x64 (64-bit)",
    "macos": "macOS arm64 (Apple Silicon)",
    "linux": "Linux x86_64",
}
ARCH = {"windows": "x64", "macos": "arm64", "linux": "x86_64"}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_base_url(value: str, allow_http: bool) -> str:
    parsed = urlparse(value)
    schemes = {"https"} | ({"http"} if allow_http else set())
    if parsed.scheme not in schemes or not parsed.netloc:
        raise SystemExit(
            f"--base-url must be an absolute {'HTTPS' if not allow_http else 'HTTP(S)'} "
            f"URL, got {value!r}"
        )
    if parsed.query or parsed.fragment:
        raise SystemExit("--base-url must not contain a query string or fragment")
    return value.rstrip("/")


def _find_artifacts(root: Path, version: str) -> dict[str, list[Path]]:
    """Map each expected filename to its path(s) under root."""
    wanted: list[str] = []
    for names in REQUIRED.values():
        wanted.extend(n.format(version=version) for n in names)
    for n in LINUX_DEB_ALTERNATES:
        wanted.append(n.format(version=version))

    found: dict[str, list[Path]] = {name: [] for name in wanted}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name in found:
            found[path.name].append(path)
    return found


def _unique_file(root: Path, candidates: list[Path]) -> Path:
    """Return one file per basename; identical duplicates are tolerated."""
    if not candidates:
        raise AssertionError("no candidates")
    first = candidates[0]
    if len(candidates) == 1:
        return first
    first_hash = sha256_of(first)
    for other in candidates[1:]:
        if sha256_of(other) != first_hash:
            rel = ", ".join(str(p.relative_to(root)) for p in candidates)
            raise SystemExit(f"duplicate {first.name} with different contents: {rel}")
    return first


def build_manifest(
    artifacts: Path,
    version: str,
    tag: str,
    base_url: str,
    verified_at: str | None = None,
    allow_http: bool = False,
) -> dict:
    if tag != f"v{version}":
        raise SystemExit(f"--tag {tag!r} does not match --version {version!r} (expected v{version})")
    base = _validate_base_url(base_url, allow_http)
    if not artifacts.is_dir():
        raise SystemExit(f"--artifacts is not a directory: {artifacts}")

    found = _find_artifacts(artifacts, version)
    expected = [n.format(version=version) for names in REQUIRED.values() for n in names]
    resolved: dict[str, Path] = {}
    missing: list[str] = []
    for name in expected:
        candidates = found.get(name, [])
        if not candidates and name.endswith("-linux-amd64.deb"):
            alt = LINUX_DEB_ALTERNATES[0].format(version=version)
            candidates = found.get(alt, [])
        if not candidates:
            missing.append(name)
            continue
        resolved[name] = _unique_file(artifacts, candidates)
    if missing:
        raise SystemExit(
            "release is incomplete; missing required artifact(s):\n  "
            + "\n  ".join(missing)
        )

    def entry(name: str) -> dict:
        path = resolved[name]
        return {
            "file": path.name,
            "size": path.stat().st_size,
            "sha256": sha256_of(path),
            "url": f"{base}/{tag}/{quote(path.name)}",
        }

    win = entry("Keel-Setup-{version}.exe".format(version=version))
    mac_dmg = entry("Keel-{version}-macos-arm64.dmg".format(version=version))
    mac_zip = entry("Keel-{version}-macos-arm64.zip".format(version=version))
    linux_img = entry("Keel-{version}-linux-x86_64.AppImage".format(version=version))
    deb_name = next(
        name for name in resolved if name.endswith(".deb")
    )
    linux_deb = entry(deb_name)

    stamp = verified_at or _utc_now()

    def channel(key: str, primary: dict, alternatives: list[dict]) -> dict:
        return {
            "name": NAME[key],
            "arch": ARCH[key],
            "version": version,
            "file": primary["file"],
            "size": primary["size"],
            "sha256": primary["sha256"],
            "url": primary["url"],
            "available": True,
            "verified": True,
            "verified_at": stamp,
            "notes": NOTES[key],
            "installation": INSTALLATION[key].format(version=version),
            "alternatives": [
                {
                    **alt,
                    "arch": ARCH[key],
                    "label": ALTERNATIVE_LABELS.get(
                        Path(alt["file"]).suffix, alt["file"]
                    ),
                }
                for alt in alternatives
            ],
        }

    channels = {
        "windows": channel("windows", win, []),
        "macos": channel("macos", mac_dmg, [mac_zip]),
        "linux": channel("linux", linux_img, [linux_deb]),
    }

    return {
        "name": "Keel Desktop",
        "version": version,
        "tag": tag,
        "generated": "release-pipeline",
        "published_at": stamp,
        "verified_at": stamp,
        "base_url": base,
        "release_manifest_url": f"{base}/{tag}/RELEASE-MANIFEST.json",
        "channels": channels,
        "__hosting__": (
            "Installers are served by Keel-controlled object storage; every "
            "file was downloaded over public HTTPS and matched against its "
            "SHA-256 before this manifest was published."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", required=True, type=Path)
    ap.add_argument("--version", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--out", default="download.json", type=Path)
    ap.add_argument(
        "--verified-at",
        default=None,
        help="ISO-8601 verification timestamp (defaults to now, UTC)",
    )
    ap.add_argument(
        "--allow-http",
        action="store_true",
        help="allow an http:// base URL (local tests only, never production)",
    )
    args = ap.parse_args()

    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        print(f"invalid --version {args.version!r}", file=sys.stderr)
        return 1

    manifest = build_manifest(
        artifacts=args.artifacts,
        version=args.version,
        tag=args.tag,
        base_url=args.base_url,
        verified_at=args.verified_at,
        allow_http=args.allow_http,
    )
    args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"download manifest: {args.out}")
    for key, ch in manifest["channels"].items():
        alts = ", ".join(a["file"] for a in ch["alternatives"]) or "none"
        print(f"  {key:8} {ch['file']:38} {ch['size']:>10}  alternatives: {alts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
