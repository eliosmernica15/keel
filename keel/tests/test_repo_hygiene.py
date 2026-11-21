"""C1.1 — repository hygiene stack."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def test_hygiene_files_exist():
    for relative in (".editorconfig", ".gitleaks.toml",
                     ".pre-commit-config.yaml"):
        assert (REPO / relative).is_file(), relative
    assert (ROOT / "CHANGELOG.md").is_file()
    assert (ROOT / "patches" / "README.md").is_file()


def test_hygiene_checker_passes():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_repo_hygiene.py")],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_patch_policy_forbids_telemetry_and_weak_safety():
    text = (ROOT / "patches" / "README.md").read_text(encoding="utf-8")
    assert "telemetry" in text.lower()
    assert "permission" in text.lower()
