"""Deterministic final-artifact reconciliation tests.

These tests never build, publish or sign a release and never touch the
network. They prove that tracked download metadata advertises only assets that
are backed by real bytes, that checksums cover exactly those bytes, and that
v0.1.1's already-published release is classified honestly (stale archives,
incomplete checksums, unsigned).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from keel.release import common, github, reconciliation, signing
from keel.release.reconciliation import (
    build_reconciled_metadata,
    combined_checksums_text,
    download_manifest_asset_names,
    parse_checksums,
    stale_format_names,
    validate_checksums_coverage,
    validate_download_manifest,
    validate_manifest_files,
)

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.1"
TAG = "v0.1.1"

# Captured read-only from `gh api repos/eliosmernica15/keel/releases/tags/v0.1.1`
# on 2026-11-25. Kept as data so the audit is reproducible offline.
PUBLISHED_V011 = {
    "tag_name": TAG,
    "assets": [
        {"name": "download.json", "size": 3722,
         "digest": "sha256:4cd142201ba98add7389632cfe22cfae5e5a0ff558ba35a724073c898ef4cc9f"},
        {"name": "Keel-0.1.1-linux-amd64.deb", "size": 121246324,
         "digest": "sha256:e94fbedfb271f37a869506b4e38c5bef9f91f072200be203c55745eea8d6423e"},
        {"name": "Keel-0.1.1-linux-x86_64.AppImage", "size": 148923140,
         "digest": "sha256:4ee9a49da563860d1245e11ed5d2739e6b1ab869429bd047c8b2cf1a3f93e7a2"},
        {"name": "Keel-0.1.1-macos-arm64.dmg", "size": 130687032,
         "digest": "sha256:44b3b620c90259c1b6c11a8a9ec2c886d59f336f1bf22ed78d84455e6b8ae316"},
        {"name": "Keel-0.1.1-macos-arm64.zip", "size": 126706334,
         "digest": "sha256:295837e43fc3d5ec780e44cccd49ab5bd482f7bc016a5fb94158be47d215c130"},
        {"name": "Keel-Setup-0.1.1.exe", "size": 122153124,
         "digest": "sha256:917a58ff527b5ccb831329d6a761ed2a1ba9cefe9ea12e967e30ad8becb0a0bf"},
        {"name": "RELEASE-MANIFEST.json", "size": 1915,
         "digest": "sha256:078e5c3449d1183045def7da9a924d066662a7be34dbd5d8bc217fb1494857e9"},
        {"name": "RELEASE-SHA256SUMS.txt", "size": 192,
         "digest": "sha256:7b7b71fc39b721a7da86b407959f8b0b1dc97360cc75d4d26504939ee6d3bf56"},
    ],
}

# Exact content of the published RELEASE-SHA256SUMS.txt (two lines only).
PUBLISHED_CHECKSUMS = (
    "e94fbedfb271f37a869506b4e38c5bef9f91f072200be203c55745eea8d6423e  "
    "Keel-0.1.1-linux-amd64.deb\n"
    "4ee9a49da563860d1245e11ed5d2739e6b1ab869429bd047c8b2cf1a3f93e7a2  "
    "Keel-0.1.1-linux-x86_64.AppImage\n"
)


def _subprocess_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    for key in list(env):
        if key.startswith("KEEL_") or key in {"GH_TOKEN", "GITHUB_TOKEN"}:
            env.pop(key, None)
    return env


def _stage(root: Path, names: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(names):
        (root / name).write_bytes(f"real-installer-bytes-{index}".encode())


# --------------------------------------------------------------------------
# Version, formats and tracked metadata
# --------------------------------------------------------------------------

def test_authoritative_version_is_synced_everywhere() -> None:
    assert common.read_version() == VERSION
    assert common.validate_version() == VERSION
    assert set(common.load_versions().values()) == {VERSION}


def test_no_stale_formats_in_configured_channels() -> None:
    names = common.expected_filenames(VERSION)
    assert stale_format_names(names) == []
    assert any(name.endswith(".pkg") for name in names)
    assert any(name.endswith(".deb") for name in names)
    assert any(name.endswith(".rpm") for name in names)
    assert any(name.endswith(".exe") for name in names)


def test_tracked_download_has_no_stale_urls_and_is_all_unavailable() -> None:
    doc = reconciliation.load_tracked_download()
    assert reconciliation.validate_tracked_download() == []
    assert doc == common.build_fallback_download_manifest(VERSION, TAG)
    assert stale_format_names(download_manifest_asset_names(doc)) == []
    assert all(
        not channel["available"] and not channel["verified"]
        and channel["url"] is None and channel["sha256"] is None
        and channel["size"] is None
        for channel in doc["channels"].values()
    )
    assert all(
        not alt["available"] and not alt["verified"] and alt["url"] is None
        for channel in doc["channels"].values()
        for alt in channel["alternatives"]
    )


# --------------------------------------------------------------------------
# Manifest <-> file and checksum consistency
# --------------------------------------------------------------------------

def test_empty_tree_produces_honest_fallback_metadata(tmp_path: Path) -> None:
    result = build_reconciled_metadata(tmp_path)
    assert result["manifest"]["files"] == []
    assert result["checksums_text"] == ""
    assert result["download"] == common.build_fallback_download_manifest(VERSION, TAG)
    assert reconciliation.assert_metadata_consistent(tmp_path) == result


def test_manifest_matches_real_bytes_and_detects_tampering(tmp_path: Path) -> None:
    names = [
        "Keel-Setup-0.1.1.exe",
        "Keel-0.1.1-macos-arm64.pkg",
        "Keel-0.1.1-linux-amd64.deb",
    ]
    _stage(tmp_path, names)
    result = build_reconciled_metadata(tmp_path)
    assert {entry["file"] for entry in result["manifest"]["files"]} == set(names)
    assert validate_manifest_files(result["manifest"], tmp_path) == []
    assert reconciliation.assert_metadata_consistent(tmp_path) == result

    # A changed byte must break manifest-to-file consistency.
    (tmp_path / names[0]).write_bytes(b"tampered")
    errors = validate_manifest_files(result["manifest"], tmp_path)
    assert any("sha256 mismatch" in error for error in errors)


def test_checksum_coverage_is_exact(tmp_path: Path) -> None:
    names = ["Keel-Setup-0.1.1.exe", "Keel-0.1.1-linux-amd64.deb"]
    _stage(tmp_path, names)
    result = build_reconciled_metadata(tmp_path)
    manifest = result["manifest"]
    text = result["checksums_text"]
    assert text == combined_checksums_text(
        {name: tmp_path / name for name in names})
    assert validate_checksums_coverage(text, manifest, root=tmp_path) == []

    lines = text.splitlines()
    missing = "\n".join(lines[:-1]) + "\n"
    orphan = text + "0" * 64 + "  Keel-0.1.1-linux-x86_64.rpm\n"
    mismatch = text.replace(lines[0].split()[0], "1" * 64, 1)
    assert any("missing entry" in e for e in validate_checksums_coverage(missing, manifest))
    assert any("orphan entry" in e for e in validate_checksums_coverage(orphan, manifest))
    assert any("mismatch" in e for e in validate_checksums_coverage(mismatch, manifest))


def test_download_manifest_never_advertises_a_nonexistent_asset(tmp_path: Path) -> None:
    doc = common.build_fallback_download_manifest(VERSION, TAG)
    empty_release = common.build_release_manifest({}, VERSION, TAG, "")
    assert validate_download_manifest(doc, empty_release, tmp_path) == []

    win = doc["channels"]["windows"]
    win.update({
        "available": True,
        "verified": True,
        "url": "https://example.test/v0.1.1/Keel-Setup-0.1.1.exe",
        "size": 123,
        "sha256": "0" * 64,
    })
    errors = validate_download_manifest(doc, empty_release, tmp_path)
    assert any("without a checksummed local asset" in e for e in errors)

    win.update({"available": False, "verified": False, "url": None,
                "size": None, "sha256": None})
    doc["channels"]["macos"]["file"] = "Keel-0.1.1-macos-arm64.dmg"
    errors = validate_download_manifest(doc, empty_release, tmp_path)
    assert any("stale archive format" in e for e in errors)


def test_staging_artifact_is_advertisable_only_after_public_verification(tmp_path: Path) -> None:
    names = common.expected_filenames(VERSION)
    _stage(tmp_path, names)
    result = build_reconciled_metadata(tmp_path)
    # Even a complete local build stays unavailable until a real public URL is
    # downloaded and byte-verified by the release pipeline.
    assert all(not c["available"] and not c["verified"]
               for c in result["download"]["channels"].values())
    assert validate_download_manifest(
        result["download"], result["manifest"], tmp_path) == []


# --------------------------------------------------------------------------
# Fail-closed behaviour
# --------------------------------------------------------------------------

def test_missing_required_artifacts_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing required artifacts"):
        common.validate_artifacts(tmp_path, VERSION)


def test_stale_archive_in_staging_fails_closed(tmp_path: Path) -> None:
    _stage(tmp_path, ["Keel-Setup-0.1.1.exe"])
    (tmp_path / "Keel-0.1.1-macos-arm64.dmg").write_bytes(b"stale")
    with pytest.raises(ValueError, match="stale release formats"):
        build_reconciled_metadata(tmp_path)


def test_unknown_keel_asset_fails_closed(tmp_path: Path) -> None:
    _stage(tmp_path, ["Keel-0.1.1-linux-amd64.deb"])
    (tmp_path / "Keel-0.1.1-unknown.bin").write_bytes(b"unknown")
    with pytest.raises(ValueError, match="unexpected release assets"):
        build_reconciled_metadata(tmp_path)


def test_malformed_checksum_line_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid checksum line"):
        parse_checksums("not-a-checksum  Keel-Setup-0.1.1.exe\n")


# --------------------------------------------------------------------------
# Published v0.1.1 audit and honest status reporting
# --------------------------------------------------------------------------

def test_published_v011_is_stale_and_incomplete() -> None:
    audit = github.audit_published_release(
        PUBLISHED_V011, VERSION, checksums_text=PUBLISHED_CHECKSUMS)
    assert audit["tag"] == TAG
    assert audit["status"] == "stale"
    assert audit["signing"] == "unsigned"
    assets = audit["assets"]
    assert set(assets["stale_assets"]) == {
        "Keel-0.1.1-linux-x86_64.AppImage",
        "Keel-0.1.1-macos-arm64.dmg",
        "Keel-0.1.1-macos-arm64.zip",
    }
    assert set(assets["expected_present"]) == {
        "Keel-Setup-0.1.1.exe", "Keel-0.1.1-linux-amd64.deb"}
    assert set(assets["expected_missing"]) == {
        "Keel-0.1.1-macos-arm64.pkg",
        "Keel-0.1.1-macos-x64.pkg",
        "Keel-0.1.1-linux-x86_64.rpm",
    }
    assert assets["signature_assets"] == []
    checksums = audit["checksums"]
    assert checksums["entries"] == [
        "Keel-0.1.1-linux-amd64.deb", "Keel-0.1.1-linux-x86_64.AppImage"]
    assert "Keel-Setup-0.1.1.exe" in checksums["missing_coverage"]
    assert checksums["digest_mismatches"] == []
    assert any("stale archive assets" in reason for reason in audit["reasons"])
    assert any("checksums omit assets" in reason for reason in audit["reasons"])


def test_published_download_json_advertises_stale_archive_urls(tmp_path: Path) -> None:
    # Fixture mirrors the stale published download.json: DMG primary, ZIP and
    # DEB alternatives, AppImage primary on Linux. It must fail our gate.
    bad = {
        "version": VERSION, "tag": TAG,
        "base_url": "https://github.com/eliosmernica15/keel/releases/download",
        "channels": {
            "windows": {"version": VERSION, "file": "Keel-Setup-0.1.1.exe",
                        "available": True, "verified": True,
                        "url": "https://github.com/eliosmernica15/keel/releases/download/v0.1.1/Keel-Setup-0.1.1.exe",
                        "size": 122153124, "sha256": "0" * 64,
                        "alternatives": []},
            "macos": {"version": VERSION, "file": "Keel-0.1.1-macos-arm64.dmg",
                      "available": True, "verified": True,
                      "url": "https://example.test/Keel-0.1.1-macos-arm64.dmg",
                      "size": 1, "sha256": "0" * 64,
                      "alternatives": [{"file": "Keel-0.1.1-macos-arm64.zip",
                                        "available": True, "verified": True,
                                        "url": "https://example.test/Keel-0.1.1-macos-arm64.zip",
                                        "size": 1, "sha256": "0" * 64}]},
            "linux": {"version": VERSION, "file": "Keel-0.1.1-linux-x86_64.AppImage",
                      "available": True, "verified": True,
                      "url": "https://example.test/Keel-0.1.1-linux-x86_64.AppImage",
                      "size": 1, "sha256": "0" * 64,
                      "alternatives": []},
        },
    }
    empty_release = common.build_release_manifest({}, VERSION, TAG, "")
    errors = validate_download_manifest(bad, empty_release, tmp_path)
    assert any("stale archive format" in e for e in errors)
    assert any("without a checksummed local asset" in e for e in errors)


def test_release_authorization_has_no_valid_owner_marker() -> None:
    text = (ROOT.parent / "FINAL-GOVERNANCE-EVIDENCE.md").read_text(encoding="utf-8")
    in_fence = False
    markers: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if not in_fence and stripped.startswith("RELEASE-APPROVED:"):
            markers.append(stripped)
    assert markers and all("NOT-APPROVED" in marker for marker in markers)
    assert not any(f"RELEASE-APPROVED: {TAG} by @eliosmernica15" == m for m in markers)


def test_distribution_signing_is_pending_without_owner_identity(
        monkeypatch, tmp_path: Path) -> None:
    for name in ("KEEL_WINDOWS_SIGNING_IDENTITY", "KEEL_MACOS_SIGNING_IDENTITY",
                 "KEEL_MACOS_NOTARY_PROFILE", "KEEL_SIGNING_TRUSTED_KEYS"):
        monkeypatch.delenv(name, raising=False)
    missing = signing.distribution_readiness_errors(env={})
    assert len(missing) == 4
    result = signing.verify_release_bundle(
        tmp_path / "keel-no-artifacts-at-all", mode="distribution")
    assert result.ok is False
    assert result.status == "failed"
    assert result.trusted_distribution is False


def test_signing_status_cli_reports_unsigned(tmp_path: Path) -> None:
    home = tmp_path / "clean-home"
    home.mkdir()
    artifacts = tmp_path / "empty-artifacts"
    artifacts.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "keel.release", "signing-status",
         "--artifacts", str(artifacts)],
        cwd=ROOT, env=_subprocess_env(home), capture_output=True, text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "unsigned"
    assert payload["verified"] is False
    assert payload["trusted_distribution"] is False


def test_signing_status_distribution_mode_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "clean-home-dist"
    home.mkdir()
    artifacts = tmp_path / "empty-artifacts-dist"
    artifacts.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "keel.release", "signing-status",
         "--artifacts", str(artifacts), "--mode", "distribution"],
        cwd=ROOT, env=_subprocess_env(home), capture_output=True, text=True,
        timeout=120,
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["verified"] is False
    assert payload["trusted_distribution"] is False
    assert any("distribution pending" in error for error in payload["errors"])
