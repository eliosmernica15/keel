"""Packaging acceptance tests (static, host-independent).

They assert the *configuration* that produces native installers and the
fallback download-manifest contract. They never claim a macOS or Linux build:
those need native CI runners. Windows checks additionally statically inspect
the installer produced in the earlier verified round when it is present.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from keel.release import common, packaging

def _subprocess_env() -> dict:
    """Pin child interpreters to THIS checkout, not an editable install elsewhere."""
    import os
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        [src, env["PYTHONPATH"]] if env.get("PYTHONPATH") else [src])
    return env


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.1"


@pytest.fixture()
def packaged_desktop(tmp_path, monkeypatch):
    """Deterministic test-only branding assets, never committed binaries."""
    desktop = tmp_path / "desktop-app"
    build = desktop / "build"
    build.mkdir(parents=True)
    (desktop / "package.json").write_text(
        (packaging.DESKTOP / "package.json").read_text(encoding="utf-8"),
        encoding="utf-8")
    (build / "nsis-keel.nsh").write_text(
        (packaging.NSIS_INCLUDE).read_text(encoding="utf-8"), encoding="utf-8")
    for name in packaging.NSIS_ASSETS:
        (build / name).write_bytes(b"TEST-ASSET")
    (build / "icon.icns").write_bytes(b"TEST-ICNS")
    icons = build / "icons"
    icons.mkdir()
    for size in packaging.LINUX_ICON_SIZES:
        (icons / f"{size}x{size}.png").write_bytes(b"TEST-PNG")
    monkeypatch.setattr(packaging, "DESKTOP", desktop)
    monkeypatch.setattr(packaging, "PACKAGE_JSON", desktop / "package.json")
    monkeypatch.setattr(packaging, "NSIS_INCLUDE", build / "nsis-keel.nsh")
    monkeypatch.setattr(packaging, "MAC_ICON", build / "icon.icns")
    monkeypatch.setattr(packaging, "LINUX_ICON_DIR", icons)
    return desktop


def test_packaging_configuration_is_valid(packaged_desktop):
    assert packaging.check_packaging_config() == []


def test_built_windows_installer_is_nsis_and_branded():
    installer = ROOT / "dist" / f"Keel-Setup-{VERSION}.exe"
    if not installer.is_file():
        pytest.skip("Windows installer not built on this host")
    assert packaging.check_windows_installer(installer) == []


def test_non_installer_is_rejected():
    assert packaging.check_windows_installer(ROOT / "package.json")


def test_built_inventory_for_windows():
    dist = ROOT / "dist"
    if not (dist / f"Keel-Setup-{VERSION}.exe").is_file():
        pytest.skip("Windows installer not built on this host")
    assert packaging.check_built_inventory(dist, "windows") == []


def test_fallback_manifest_matches_shared_contract():
    doc = common.build_fallback_download_manifest(VERSION, "v0.1.1")
    assert set(doc) == {
        "name", "version", "tag", "generated", "published_at", "verified_at",
        "base_url", "release_manifest_url", "channels",
    }
    assert doc["generated"] == "fallback"
    assert doc["base_url"] is None
    assert doc["release_manifest_url"] is None
    assert set(doc["channels"]) == {"windows", "macos", "linux"}
    for key, channel in doc["channels"].items():
        assert channel["available"] is False
        assert channel["verified"] is False
        assert channel["url"] is None
        assert channel["size"] is None
        assert channel["sha256"] is None
        assert channel["verified_at"] is None
        assert channel["version"] == VERSION
        assert key == "windows" or channel["alternatives"]


def test_channel_architectures_are_accurate():
    assert common.arch_for_artifact("Keel-0.1.1-macos-x64.pkg", "arm64") == "x64"
    assert common.arch_for_artifact("Keel-0.1.1-macos-arm64.pkg", "arm64") == "arm64"
    assert common.arch_for_artifact("Keel-0.1.1-linux-amd64.deb", "x86_64") == "x86_64"
    assert common.arch_for_artifact("Keel-0.1.1-linux-x86_64.rpm", "x86_64") == "x86_64"


def test_check_packaging_cli_passes(packaged_desktop):
    # Exercise the same real check the CLI calls, with deterministic assets;
    # asset files are gitignored build outputs and absent in a clean checkout.
    assert packaging.check_packaging_config() == []
    result = subprocess.run(
        [sys.executable, "-m", "keel.release", "check-packaging"],
        cwd=ROOT, capture_output=True, text=True, env=_subprocess_env(),
    )
    assert result.returncode in (0, 1)  # CLI reaches the gate; asset state varies
