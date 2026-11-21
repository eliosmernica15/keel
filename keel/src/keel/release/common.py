from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VERSION_FILES = {
    "pyproject.toml": PROJECT_ROOT / "pyproject.toml",
    "desktop-app/package.json": PROJECT_ROOT / "desktop-app" / "package.json",
    "desktop-app/package-lock.json": PROJECT_ROOT / "desktop-app" / "package-lock.json",
    "site/download.json": PROJECT_ROOT / "site" / "download.json",
    "desktop/src-tauri/tauri.conf.json": PROJECT_ROOT / "desktop" / "src-tauri" / "tauri.conf.json",
    "src/keel/__init__.py": PROJECT_ROOT / "src" / "keel" / "__init__.py",
}

DEFAULT_REPO = "eliosmernica15/keel"

WINDOWS_NOTES = (
    "Built and checksummed by CI and install-tested on Windows 11 (silent install, "
    "launch, reinstall, silent uninstall, ~/.keel preserved). Unsigned - expect "
    "SmartScreen."
)
MACOS_NOTES = (
    "Built in CI for Apple Silicon (arm64) and Intel (x64). Unsigned - "
    "Gatekeeper will block first launch on both architectures."
)
LINUX_NOTES = (
    "Built in CI as AppImage, .deb and .rpm; artifacts are structure-inspected "
    "but not launched on desktop Linux. Unsigned; your distribution may show a "
    "policy warning."
)

WINDOWS_INSTALL = (
    "Run Keel-Setup-{version}.exe. Accept the installer prompts. Launch from the "
    "Start Menu shortcut or Desktop shortcut."
)
MACOS_INSTALL = (
    "Open the DMG, drag Keel into Applications, then right-click Keel and choose "
    "Open the first time (Gatekeeper)."
)
LINUX_INSTALL = (
    "Make the AppImage executable and run it. On Debian/Ubuntu use the .deb; on "
    "Fedora/RHEL use the .rpm with your package manager."
)

CHANNELS = [
    {
        "key": "windows",
        "primary": "Keel-Setup-{version}.exe",
        "alternatives": [],
        "arch": "x64",
        "name": "Windows x64 (64-bit)",
        "notes": WINDOWS_NOTES,
        "installation": WINDOWS_INSTALL,
    },
    {
        "key": "macos",
        "primary": "Keel-{version}-macos-arm64.dmg",
        "alternatives": [
            "Keel-{version}-macos-arm64.zip",
            "Keel-{version}-macos-x64.dmg",
            "Keel-{version}-macos-x64.zip",
        ],
        "arch": "arm64",
        "name": "macOS arm64 (Apple Silicon)",
        "notes": MACOS_NOTES,
        "installation": MACOS_INSTALL,
    },
    {
        "key": "linux",
        "primary": "Keel-{version}-linux-x86_64.AppImage",
        "alternatives": [
            "Keel-{version}-linux-amd64.deb",
            "Keel-{version}-linux-x86_64.rpm",
        ],
        "arch": "x86_64",
        "name": "Linux x86_64",
        "notes": LINUX_NOTES,
        "installation": LINUX_INSTALL,
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def read_version() -> str:
    with open(VERSION_FILES["pyproject.toml"], "rb") as f:
        data = tomllib.load(f)
    return str(data["project"]["version"])


def load_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    pyproject = tomllib.loads(VERSION_FILES["pyproject.toml"].read_text(encoding="utf-8"))
    versions["pyproject.toml"] = pyproject["project"]["version"]

    desktop = json.loads(VERSION_FILES["desktop-app/package.json"].read_text(encoding="utf-8"))
    versions["desktop-app/package.json"] = desktop["version"]

    lock = json.loads(VERSION_FILES["desktop-app/package-lock.json"].read_text(encoding="utf-8"))
    versions["desktop-app/package-lock.json"] = lock.get("version", "")

    site = json.loads(VERSION_FILES["site/download.json"].read_text(encoding="utf-8"))
    versions["site/download.json (version)"] = site.get("version", "")

    tauri = json.loads(VERSION_FILES["desktop/src-tauri/tauri.conf.json"].read_text(encoding="utf-8"))
    versions["desktop/src-tauri/tauri.conf.json"] = tauri.get("version", "")

    package_init = VERSION_FILES["src/keel/__init__.py"].read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', package_init, re.MULTILINE)
    versions["src/keel/__init__.py"] = match.group(1) if match else ""

    return versions


def validate_version(tag: str | None = None) -> str:
    versions = load_versions()
    distinct = set(versions.values())
    if len(distinct) != 1:
        lines = ["VERSION MISMATCH"]
        for src, value in sorted(versions.items()):
            lines.append(f"  {src:38} {value}")
        raise ValueError("\n".join(lines))
    version = distinct.pop()
    if tag is not None:
        expected_tag = f"v{version}"
        if tag != expected_tag:
            raise ValueError(f"tag {tag!r} != {expected_tag!r}")
    return version


def detect_repo() -> str:
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo:
        return env_repo
    try:
        out = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return DEFAULT_REPO
    # Handle ssh and https forms.
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", out)
    if m:
        return m.group(1)
    return DEFAULT_REPO


def expected_filenames(version: str) -> list[str]:
    names: list[str] = []
    for channel in CHANNELS:
        names.append(channel["primary"].format(version=version))
        for alt in channel["alternatives"]:
            names.append(alt.format(version=version))
    return names


def find_artifacts(artifacts_root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    duplicates: list[str] = []
    for path in artifacts_root.rglob("Keel-*"):
        if not path.is_file():
            continue
        if path.name in found:
            duplicates.append(path.name)
        found[path.name] = path
    if duplicates:
        raise ValueError("duplicate artifact filenames: " + ", ".join(sorted(set(duplicates))))
    return found


def validate_artifacts(artifacts_root: Path, version: str) -> dict[str, Path]:
    found = find_artifacts(artifacts_root)
    expected = set(expected_filenames(version))
    missing = sorted(expected - set(found))
    if missing:
        raise ValueError("missing required artifacts: " + ", ".join(missing))
    return {name: found[name] for name in sorted(expected)}


def write_combined_checksums(artifacts: dict[str, Path], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    combined = out_dir / "RELEASE-SHA256SUMS.txt"
    lines = []
    for name in sorted(artifacts):
        digest = sha256_file(artifacts[name])
        lines.append(f"{digest.lower()}  {name}")
    combined.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return combined


def build_release_manifest(
    artifacts: dict[str, Path],
    version: str,
    tag: str,
    base_url: str,
) -> dict:
    entries = []
    for channel in CHANNELS:
        primary_name = channel["primary"].format(version=version)
        if primary_name not in artifacts:
            continue
        platform = channel["key"]
        arch = channel["arch"]
        for name in [primary_name] + [a.format(version=version) for a in channel["alternatives"]]:
            if name not in artifacts:
                continue
            entries.append(
                {
                    "platform": platform,
                    "arch": arch,
                    "version": version,
                    "file": name,
                    "bytes": artifacts[name].stat().st_size,
                    "sha256": sha256_file(artifacts[name]),
                    "url": (
                        f"{base_url.rstrip('/')}/{tag}/{quote(name, safe='')}"
                        if base_url
                        else "pending"
                    ),
                }
            )
    checksums_file = "RELEASE-SHA256SUMS.txt"
    return {
        "name": "Keel Desktop",
        "version": version,
        "tag": tag,
        "generated": "release-pipeline",
        "published_at": os.environ.get(
            "KEEL_PUBLISHED_AT",
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        "min_version": os.environ.get("KEEL_MIN_VERSION", "0.1.0"),
        "blocked_versions": [
            v.strip() for v in os.environ.get(
                "KEEL_BLOCKED_VERSIONS", "").split(",") if v.strip()],
        "security_advisories": {},
        "rollout": {
            "mode": os.environ.get("KEEL_ROLLOUT_MODE", "full"),
            "percentage": min(100, max(0, int(
                os.environ.get("KEEL_ROLLOUT_PERCENTAGE", "100") or "100"))),
            "bucket_count": 100,
        },
        "files": entries,
        "checksums_file": checksums_file,
    }


def build_download_manifest(
    artifacts: dict[str, Path],
    version: str,
    tag: str,
    base_url: str,
    *,
    available: bool,
    verified: bool,
    verified_at: str | None,
    published_at: str | None = None,
) -> dict:
    channels: dict[str, dict] = {}
    for channel in CHANNELS:
        primary_name = channel["primary"].format(version=version)
        if primary_name not in artifacts:
            continue
        alt_names = [a.format(version=version) for a in channel["alternatives"]]
        primary_url = (
            f"{base_url.rstrip('/')}/{tag}/{quote(primary_name, safe='')}"
            if (available and base_url)
            else None
        )
        alternatives = []
        for alt_name in alt_names:
            if alt_name not in artifacts:
                continue
            alt_url = (
                f"{base_url.rstrip('/')}/{tag}/{quote(alt_name, safe='')}"
                if (available and base_url)
                else None
            )
            alternatives.append(
                {
                    "file": alt_name,
                    "arch": channel["arch"],
                    "label": _alternative_label(alt_name),
                    "size": artifacts[alt_name].stat().st_size,
                    "sha256": sha256_file(artifacts[alt_name]),
                    "url": alt_url,
                    "available": bool(available),
                    "verified": bool(verified) if available else False,
                }
            )
        channels[channel["key"]] = {
            "name": channel["name"],
            "arch": channel["arch"],
            "version": version,
            "file": primary_name,
            "size": artifacts[primary_name].stat().st_size,
            "sha256": sha256_file(artifacts[primary_name]),
            "url": primary_url,
            "available": bool(available),
            "verified": bool(verified) if available else False,
            "verified_at": verified_at if available else None,
            "notes": channel["notes"],
            "installation": channel["installation"].format(version=version),
            "alternatives": alternatives,
        }

    generated = "release-pipeline" if available else "fallback"
    return {
        "name": "Keel Desktop",
        "version": version,
        "tag": tag,
        "generated": generated,
        "published_at": published_at,
        "verified_at": verified_at,
        "base_url": base_url.rstrip("/") if base_url else None,
        "release_manifest_url": (
            f"{base_url.rstrip('/')}/{tag}/RELEASE-MANIFEST.json" if base_url else None
        ),
        "channels": channels,
    }


def _alternative_label(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".zip":
        return "ZIP archive"
    if suffix == ".deb":
        return "Debian/Ubuntu package (.deb)"
    return filename


def run_cmd(cmd: list[str], cwd: Path) -> None:
    import os

    shell = os.name == "nt" and any(c.lower().endswith((".cmd", ".bat")) for c in cmd if isinstance(c, str))
    # npm/npx on Windows are .cmd shims.
    if os.name == "nt" and cmd and isinstance(cmd[0], str) and cmd[0].lower() in {"npm", "npx"}:
        shell = True
    subprocess.run(cmd, cwd=str(cwd), check=True, shell=shell)


def ensure_file(path: Path, message: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(message)
