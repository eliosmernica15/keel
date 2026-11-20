from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path

from .artifacts import validate_sidecar, validate_staged_release, validate_tree
from .common import (
    CHANNELS,
    PROJECT_ROOT,
    detect_repo,
    ensure_file,
    run_cmd,
    sha256_file,
    validate_artifacts,
    validate_version,
    write_combined_checksums,
    build_release_manifest,
)

HOST_PLATFORM = {
    "Windows": "windows",
    "Darwin": "macos",
    "Linux": "linux",
}


def detect_host_platform() -> str:
    return HOST_PLATFORM.get(platform.system(), "unknown")


def build_sidecar(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_cmd([sys.executable, "desktop-app/scripts/generate_assets.py"], cwd=PROJECT_ROOT)
    run_cmd(
        [sys.executable, "-m", "PyInstaller", "desktop-app/sidecar.spec",
         "--noconfirm", "--distpath", "dist/keel-sidecar"],
        cwd=PROJECT_ROOT,
    )
    sidecar_src = PROJECT_ROOT / "dist" / "keel-sidecar" / (
        "keel.exe" if os.name == "nt" else "keel"
    )
    ensure_file(sidecar_src, "PyInstaller did not produce the keel sidecar")
    target_dir = PROJECT_ROOT / "build" / "resources" / "keel"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / sidecar_src.name
    shutil.copy2(sidecar_src, target)


def npm_install() -> None:
    desktop = PROJECT_ROOT / "desktop-app"
    if not (desktop / "node_modules").exists():
        run_cmd(["npm", "install", "--no-audit", "--no-fund"], cwd=desktop)


def electron_build(platform_name: str) -> None:
    desktop = PROJECT_ROOT / "desktop-app"
    if platform_name == "windows":
        run_cmd(["npx", "electron-builder", "--win", "--publish", "never"], cwd=desktop)
    elif platform_name == "macos":
        run_cmd(["npx", "electron-builder", "--mac", "--publish", "never"], cwd=desktop)
    elif platform_name == "linux":
        run_cmd(
            ["npx", "electron-builder", "--linux", "AppImage", "deb", "--publish", "never"],
            cwd=desktop,
        )
    else:
        raise ValueError(f"unsupported platform: {platform_name}")


def validate_packaged_outputs() -> None:
    """Validate every packaged output, including the sidecar payload."""
    dist_dir = PROJECT_ROOT / "dist"
    if not dist_dir.is_dir():
        return
    for child in sorted(p for p in dist_dir.iterdir() if p.is_dir()):
        if child.name == "keel-sidecar":
            validate_sidecar(child)
        else:
            validate_tree(child)


def stage_release(out_dir: Path, version: str) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    dist_dir = PROJECT_ROOT / "dist"
    artifacts: dict[str, Path] = {}
    for path in dist_dir.rglob("Keel-*"):
        if not path.is_file():
            continue
        dest = out_dir / path.name
        shutil.copy2(path, dest)
        artifacts[path.name] = dest
    if not artifacts:
        raise RuntimeError("build produced no installer")
    write_combined_checksums(artifacts, out_dir)
    return artifacts


def build_command(args: argparse.Namespace) -> int:
    platform_name = args.platform
    if platform_name == "auto":
        platform_name = detect_host_platform()
    if platform_name not in {"windows", "macos", "linux"}:
        raise SystemExit(f"unknown platform: {platform_name}")
    if platform_name != detect_host_platform():
        raise SystemExit(
            f"cannot build {platform_name} on {detect_host_platform()}; "
            "run this command on the matching OS or in CI"
        )

    version = validate_version(args.tag)
    tag = args.tag or f"v{version}"
    validate_version(tag)

    print(f"Building Keel {version} ({platform_name})")
    build_sidecar(Path("unused"))
    npm_install()
    electron_build(platform_name)
    validate_packaged_outputs()

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    artifacts = stage_release(out_dir, version)
    repo = args.repo or detect_repo()
    base_url = args.base_url or f"https://github.com/{repo}/releases/download"
    manifest = build_release_manifest(artifacts, version, tag, base_url)
    (out_dir / "RELEASE-MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    platform_required = set()
    for channel in CHANNELS:
        if channel["key"] == platform_name:
            platform_required.add(channel["primary"].format(version=version))
            platform_required.update(
                alt.format(version=version) for alt in channel["alternatives"])
    validate_staged_release(out_dir, version, platform_required)
    print(f"staged {len(artifacts)} installers in {out_dir}")
    for name in sorted(artifacts):
        print(f"  {name}  {artifacts[name].stat().st_size} bytes  {sha256_file(artifacts[name])}")
    return 0
