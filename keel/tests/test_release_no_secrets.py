"""A4.8 — release scans prove zero clear-text secrets in artifacts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from keel.release import artifacts

ROOT = Path(__file__).resolve().parents[1]


def _release_cmd(*args):
    return subprocess.run(
        [sys.executable, "-m", "keel.release", *args],
        cwd=ROOT, capture_output=True, text=True)


def test_secret_scan_detects_credential_shapes(tmp_path):
    (tmp_path / "config.json").write_text(
        '{"key": "sk-or-v1-abcdefghijklmnopqrstuvwx"}', encoding="utf-8")
    (tmp_path / "notes.txt").write_text("key=AKIAIOSFODNN7EXAMPLE", encoding="utf-8")
    hits = artifacts.scan_secret_markers(tmp_path)
    assert "config.json" in hits and "notes.txt" in hits


def test_secret_scan_ignores_clean_files(tmp_path):
    (tmp_path / "config.json").write_text('{"name": "Keel"}', encoding="utf-8")
    assert artifacts.scan_secret_markers(tmp_path) == []


def test_check_artifacts_fails_on_planted_secret(tmp_path):
    (tmp_path / "leak.txt").write_text(
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789", encoding="utf-8")
    result = _release_cmd("check-artifacts", str(tmp_path))
    assert result.returncode == 1
    assert "leak.txt" in result.stdout + result.stderr


def test_dry_run_fails_on_planted_secret(tmp_path):
    dist = tmp_path / "dist"
    staged = tmp_path / "release"
    dist.mkdir()
    staged.mkdir()
    (staged / "leak.json").write_text(
        '{"token": "AIzaSyD-abcdefghijklmnopqrstuvwxyz123456"}',
        encoding="utf-8")
    result = _release_cmd("dry-run", "--dist", str(dist),
                          "--artifacts", str(staged))
    assert result.returncode == 1
    assert "leak.json" in result.stderr
