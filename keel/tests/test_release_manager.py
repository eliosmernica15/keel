"""Tests for the Python release manager.

Distribution uses GitHub Releases, so most tests run offline (manifest
generation, checksums, version checks) or against a loopback HTTP server
(actual download + size + SHA-256 verification). No external service is
contacted.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest

from keel.release import common, verify

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.1"
TAG = "v0.1.1"

ARTIFACTS = {
    "Keel-Setup-0.1.1.exe": b"windows-installer-bytes",
    "Keel-0.1.1-macos-arm64.dmg": b"macos-dmg-bytes",
    "Keel-0.1.1-macos-arm64.zip": b"macos-zip-bytes",
    "Keel-0.1.1-linux-x86_64.AppImage": b"linux-appimage-bytes",
    "Keel-0.1.1-linux-amd64.deb": b"linux-deb-bytes",
}


@pytest.fixture()
def artifacts(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    root.mkdir()
    for name, payload in ARTIFACTS.items():
        (root / name).write_bytes(payload)
    return root


def test_version_sync_ok() -> None:
    assert common.validate_version() == VERSION


def test_expected_filenames() -> None:
    names = common.expected_filenames(VERSION)
    assert set(names) == set(ARTIFACTS)
    assert len(names) == 5


def test_find_and_validate_artifacts(artifacts: Path) -> None:
    found = common.find_artifacts(artifacts)
    assert set(found) == set(ARTIFACTS)
    validated = common.validate_artifacts(artifacts, VERSION)
    assert set(validated) == set(ARTIFACTS)


def test_validate_artifacts_missing(artifacts: Path) -> None:
    (artifacts / "Keel-Setup-0.1.1.exe").unlink()
    with pytest.raises(ValueError, match="missing required artifacts"):
        common.validate_artifacts(artifacts, VERSION)


def test_sha256_file(artifacts: Path) -> None:
    path = artifacts / "Keel-Setup-0.1.1.exe"
    expected = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    assert common.sha256_file(path) == expected


def test_build_download_manifest(artifacts: Path) -> None:
    validated = common.validate_artifacts(artifacts, VERSION)
    base = "https://github.com/eliosmernica15/keel/releases/download"
    manifest = common.build_download_manifest(
        validated,
        VERSION,
        TAG,
        base,
        available=True,
        verified=True,
        verified_at="2026-01-01T00:00:00Z",
        published_at="2026-01-01T00:00:00Z",
    )
    assert manifest["version"] == VERSION
    assert manifest["tag"] == TAG
    assert manifest["base_url"] == base
    assert set(manifest["channels"]) == {"windows", "macos", "linux"}
    for key, channel in manifest["channels"].items():
        assert channel["available"] is True
        assert channel["verified"] is True
        assert channel["url"].startswith("https://")
        assert channel["size"] == len(ARTIFACTS[channel["file"]])
        assert channel["sha256"] == hashlib.sha256(ARTIFACTS[channel["file"]]).hexdigest().upper()
    # alternatives
    macos_alts = manifest["channels"]["macos"]["alternatives"]
    assert [a["file"] for a in macos_alts] == ["Keel-0.1.1-macos-arm64.zip"]
    linux_alts = manifest["channels"]["linux"]["alternatives"]
    assert [a["file"] for a in linux_alts] == ["Keel-0.1.1-linux-amd64.deb"]


def test_build_release_manifest(artifacts: Path) -> None:
    validated = common.validate_artifacts(artifacts, VERSION)
    base = "https://github.com/eliosmernica15/keel/releases/download"
    manifest = common.build_release_manifest(validated, VERSION, TAG, base)
    assert len(manifest["files"]) == 5
    assert all(f["url"].startswith("https://github.com/") for f in manifest["files"])
    assert manifest["checksums_file"] == "RELEASE-SHA256SUMS.txt"


def test_verify_manifest_success(artifacts: Path) -> None:
    # Serve artifacts under a tag directory so URLs resolve.
    serve_root = artifacts.parent / "serve"
    if serve_root.exists():
        shutil.rmtree(serve_root)
    tag_dir = serve_root / TAG
    tag_dir.mkdir(parents=True)
    for p in artifacts.iterdir():
        shutil.copy2(p, tag_dir / p.name)

    port = 8792
    httpd = ThreadingHTTPServer(("127.0.0.1", port), lambda *a, **k: SimpleHTTPRequestHandler(*a, directory=str(serve_root), **k))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.5)

    try:
        validated = common.validate_artifacts(artifacts, VERSION)
        base = f"http://127.0.0.1:{port}"
        manifest = common.build_download_manifest(
            validated, VERSION, TAG, base, available=True, verified=True,
            verified_at="2026-01-01T00:00:00Z",
        )
        errors = verify.verify_manifest(manifest, allow_http=True, retries=1, timeout=30)
        assert errors == [], errors
    finally:
        httpd.shutdown()


def test_verify_manifest_mismatch(artifacts: Path) -> None:
    serve_root = artifacts.parent / "serve2"
    if serve_root.exists():
        shutil.rmtree(serve_root)
    tag_dir = serve_root / TAG
    tag_dir.mkdir(parents=True)
    for p in artifacts.iterdir():
        shutil.copy2(p, tag_dir / p.name)

    port = 8793
    httpd = ThreadingHTTPServer(("127.0.0.1", port), lambda *a, **k: SimpleHTTPRequestHandler(*a, directory=str(serve_root), **k))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.5)

    try:
        validated = common.validate_artifacts(artifacts, VERSION)
        base = f"http://127.0.0.1:{port}"
        manifest = common.build_download_manifest(
            validated, VERSION, TAG, base, available=True, verified=True,
            verified_at="2026-01-01T00:00:00Z",
        )
        # Corrupt one served file.
        target = tag_dir / "Keel-Setup-0.1.1.exe"
        original = target.read_bytes()
        target.write_bytes(original + b"x")
        errors = verify.verify_manifest(manifest, allow_http=True, retries=1, timeout=30)
        assert any("sha256 mismatch" in e or "size mismatch" in e for e in errors)
        target.write_bytes(original)
    finally:
        httpd.shutdown()


def test_verify_cli_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "keel.release", "verify", "--help"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--manifest" in result.stdout


def test_publish_dry_run(artifacts: Path) -> None:
    out = artifacts.parent / "publishout"
    if out.exists():
        shutil.rmtree(out)
    result = subprocess.run(
        [sys.executable, "-m", "keel.release", "publish",
         "--artifacts", str(artifacts), "--tag", TAG, "--dry-run", "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    manifest_path = out / "download.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["available"] if "available" in manifest else True
    assert all(ch["available"] for ch in manifest["channels"].values())


def test_cli_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "keel.release", "--help"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "build" in result.stdout and "publish" in result.stdout and "verify" in result.stdout
