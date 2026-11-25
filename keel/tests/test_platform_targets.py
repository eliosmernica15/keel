"""Native-installer platform targets: macOS PKG, Linux DEB/RPM.

Updated for the production-distribution round: DMG/ZIP/AppImage are no longer
primary or alternative consumer paths. The fallback manifest generator (not the
committed site file) is the source of truth for Agent A's offline shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from keel.release.common import build_fallback_download_manifest, expected_filenames

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.1"
TAG = "v0.1.1"


def test_package_config_builds_native_installers_on_every_os():
    package = json.loads((ROOT / "desktop-app" / "package.json").read_text(
        encoding="utf-8"))
    mac_targets = package["build"]["mac"]["target"]
    assert any(target["target"] == "pkg" and "arm64" in target["arch"]
               for target in mac_targets)
    assert any(target["target"] == "pkg" and "x64" in target["arch"]
               for target in mac_targets)
    assert not any(target["target"] in {"dmg", "zip"} for target in mac_targets)
    linux_targets = package["build"]["linux"]["target"]
    assert "deb" in linux_targets and "rpm" in linux_targets
    assert "AppImage" not in linux_targets
    assert package["build"]["win"]["target"] == ["nsis"]


def test_release_manifest_expects_all_native_platform_artifacts():
    names = set(expected_filenames(VERSION))
    for expected in (
        "Keel-Setup-0.1.1.exe",
        "Keel-0.1.1-macos-arm64.pkg",
        "Keel-0.1.1-macos-x64.pkg",
        "Keel-0.1.1-linux-amd64.deb",
        "Keel-0.1.1-linux-x86_64.rpm",
    ):
        assert expected in names
    assert not any("AppImage" in n or ".dmg" in n or ".zip" in n for n in names)


def test_generated_fallback_exposes_intel_pkg_and_rpm_alternatives():
    doc = build_fallback_download_manifest(VERSION, TAG)
    assert doc["channels"]["macos"]["file"] == "Keel-0.1.1-macos-arm64.pkg"
    assert doc["channels"]["linux"]["file"] == "Keel-0.1.1-linux-amd64.deb"
    mac_names = {a["file"] for a in doc["channels"]["macos"]["alternatives"]}
    linux_names = {a["file"] for a in doc["channels"]["linux"]["alternatives"]}
    assert "Keel-0.1.1-macos-x64.pkg" in mac_names
    assert "Keel-0.1.1-linux-x86_64.rpm" in linux_names
    assert all(not ch["available"] and not ch["verified"]
               and ch["url"] is None for ch in doc["channels"].values())


def test_release_build_requests_both_macos_architectures_and_rpm():
    source = (ROOT / "src" / "keel" / "release" / "build.py").read_text(
        encoding="utf-8")
    assert '"--arm64"' in source
    assert '"--x64"' in source
    assert '"rpm"' in source
    assert '"AppImage"' not in source
