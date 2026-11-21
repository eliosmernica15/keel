"""Locked v5 platform targets: macOS Intel and Linux RPM."""

from __future__ import annotations

import json
from pathlib import Path

from keel.release.common import expected_filenames

ROOT = Path(__file__).resolve().parents[1]


def test_package_config_builds_macos_intel_and_linux_rpm():
    package = json.loads((ROOT / "desktop-app" / "package.json").read_text(
        encoding="utf-8"))
    mac_targets = package["build"]["mac"]["target"]
    assert any(target["target"] == "dmg" and "x64" in target["arch"]
               for target in mac_targets)
    assert any(target["target"] == "zip" and "x64" in target["arch"]
               for target in mac_targets)
    assert "rpm" in package["build"]["linux"]["target"]


def test_release_manifest_expects_all_platform_artifacts():
    names = set(expected_filenames("0.1.1"))
    for expected in (
        "Keel-Setup-0.1.1.exe",
        "Keel-0.1.1-macos-arm64.dmg",
        "Keel-0.1.1-macos-x64.dmg",
        "Keel-0.1.1-linux-x86_64.AppImage",
        "Keel-0.1.1-linux-amd64.deb",
        "Keel-0.1.1-linux-x86_64.rpm",
    ):
        assert expected in names


def test_download_fallback_exposes_intel_and_rpm_alternatives():
    doc = json.loads((ROOT / "site" / "download.json").read_text(
        encoding="utf-8"))
    mac_names = {a["file"] for a in doc["channels"]["macos"]["alternatives"]}
    linux_names = {a["file"] for a in doc["channels"]["linux"]["alternatives"]}
    assert "Keel-0.1.1-macos-x64.dmg" in mac_names
    assert "Keel-0.1.1-linux-x86_64.rpm" in linux_names


def test_release_build_requests_both_macos_architectures_and_rpm():
    source = (ROOT / "src" / "keel" / "release" / "build.py").read_text(
        encoding="utf-8")
    assert '"--arm64"' in source
    assert '"--x64"' in source
    assert '"rpm"' in source
