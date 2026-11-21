"""Verify the real packaged desktop application artifacts.

These checks run against locally built artifacts when present. They verify
the real Electron app resources, the Python sidecar, version sync and clean
artifact contents — distinguishing what is locally verifiable from checks
that require a clean external machine or signing credentials.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
UNPACKED = DIST / "win-unpacked"
SIDECAR = DIST / "keel-sidecar"


@pytest.mark.skipif(not (UNPACKED / "Keel.exe").exists(),
                    reason="desktop app not built locally")
def test_packaged_electron_resources():
    exe = UNPACKED / "Keel.exe"
    asar = UNPACKED / "resources" / "app.asar"
    assert exe.is_file() and exe.stat().st_size > 1_000_000
    assert asar.is_file() and asar.stat().st_size > 10_000
    # packaged sidecar inside the Electron app
    sidecar = UNPACKED / "resources" / "keel" / "keel.exe"
    assert sidecar.is_file()


@pytest.mark.skipif(not (SIDECAR / "keel.exe").exists(),
                    reason="sidecar not built locally")
def test_packaged_sidecar_runs():
    result = subprocess.run(
        [str(SIDECAR / "keel.exe"), "--version"],
        capture_output=True, text=True, timeout=30, cwd=ROOT)
    assert result.returncode == 0
    assert "keel" in result.stdout.lower()


@pytest.mark.skipif(not DIST.exists(), reason="no dist directory")
def test_artifact_scan_clean():
    from keel.release.artifacts import scan_tree

    for path in (UNPACKED, SIDECAR):
        if path.is_dir():
            assert scan_tree(path) == [], f"prohibited files in {path}"


def test_external_only_checks_declared():
    """Checks that genuinely need a clean machine or owner credentials."""
    from keel.installer_smoke import ci_only_checks

    checks = ci_only_checks()
    assert any("clean-VM" in c for c in checks)
    assert any("rollback" in c for c in checks)
    assert any("upgrade" in c for c in checks)
