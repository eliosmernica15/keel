"""Release version consistency across all sources."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import keel
from keel import release
from keel.release.common import load_versions, validate_version

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "check_version_sync.py"
GATED_FILES = (
    "pyproject.toml",
    "desktop-app/package.json",
    "desktop-app/package-lock.json",
    "site/download.json",
    "desktop/src-tauri/tauri.conf.json",
    "desktop/src-tauri/Cargo.toml",
    "src/keel/__init__.py",
)


def test_package_version_matches_all_release_sources():
    versions = load_versions()
    assert keel.__version__ == "0.1.1"
    assert "desktop/src-tauri/Cargo.toml" in versions
    assert set(versions.values()) == {"0.1.1"}
    assert validate_version() == "0.1.1"


def test_standalone_gate_passes_and_rejects_cargo_drift(tmp_path):
    """The gate must read Cargo.toml, not just tauri.conf.json."""
    for rel in (*GATED_FILES, "scripts/check_version_sync.py"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)

    def run_gate():
        return subprocess.run(
            [sys.executable, str(tmp_path / "scripts" / "check_version_sync.py"),
             "--tag", "v0.1.1"],
            cwd=tmp_path, capture_output=True, text=True, timeout=60)

    result = run_gate()
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK - all sources agree on version 0.1.1 (tag v0.1.1)"

    cargo = tmp_path / "desktop" / "src-tauri" / "Cargo.toml"
    cargo.write_text(cargo.read_text(encoding="utf-8").replace(
        'version = "0.1.1"', 'version = "0.1.2"'), encoding="utf-8")
    result = run_gate()
    assert result.returncode == 1
    assert "VERSION MISMATCH" in result.stderr
    assert "Cargo.toml" in result.stderr and "0.1.2" in result.stderr


def test_secondary_version_constants_match_canonical():
    assert release.__version__ == keel.__version__
