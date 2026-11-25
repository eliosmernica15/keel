"""Release integrity verification — including stale-manifest detection."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from keel.release_integrity import (verify_checksums, verify_latest_yml,
                                    verify_manifest, verify_sidecar_version,
                                    verify_latest_yml as check_latest)

from fixtures.release_tree import build_release_tree, reported_sidecar_version


def test_stale_latest_yml_detected(tmp_path):
    """A latest.yml that disagrees with the actual artifact must fail."""
    dist = tmp_path / "dist"
    release = tmp_path / "release"
    dist.mkdir()
    release.mkdir()
    artifact = dist / "Keel-Setup-0.1.1.exe"
    artifact.write_bytes(b"x" * 5000)
    doc = {"version": "0.1.1",
           "files": [{"platform": "windows", "file": artifact.name,
                      "bytes": artifact.stat().st_size,
                      "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}]}
    (release / "RELEASE-MANIFEST.json").write_text(json.dumps(doc))

    (dist / "latest.yml").write_text(
        "version: 0.1.1\nsize: 1\nsha512: bogus\npath: Keel-Setup-0.1.1.exe\n")
    result = verify_latest_yml(dist, release)
    assert result.ok is False
    assert "size" in result.detail or "sha512" in result.detail


def test_correct_latest_yml_passes(tmp_path):
    dist = tmp_path / "dist"
    release = tmp_path / "release"
    dist.mkdir()
    release.mkdir()
    artifact = dist / "Keel-Setup-0.1.1.exe"
    artifact.write_bytes(b"y" * 4096)
    digest = base64.b64encode(
        hashlib.sha512(artifact.read_bytes()).digest()).decode()
    (dist / "latest.yml").write_text(
        f"version: 0.1.1\nfiles:\n  - url: {artifact.name}\n"
        f"    sha512: {digest}\n    size: {artifact.stat().st_size}\n"
        f"path: {artifact.name}\nsha512: {digest}\n")
    doc = {"version": "0.1.1",
           "files": [{"platform": "windows", "file": artifact.name,
                      "bytes": artifact.stat().st_size,
                      "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}]}
    (release / "RELEASE-MANIFEST.json").write_text(json.dumps(doc))
    assert verify_latest_yml(dist, release).ok is True


def test_integrity_cli_on_real_artifacts(tmp_path):
    # Production installers are gitignored build outputs and are not present
    # in a clean checkout. Build a deterministic test-only tree whose hashes,
    # sizes and sidecar version are all derived from the bytes on disk.
    version = reported_sidecar_version()
    release, dist = build_release_tree(tmp_path, version=version)
    src = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(src), env["PYTHONPATH"]] if env.get("PYTHONPATH") else [str(src)])
    result = subprocess.run(
        [sys.executable, "-m", "keel.release", "integrity",
         "--dist", str(dist), "--artifacts", str(release)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "7/7 passed" in result.stdout
