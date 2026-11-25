"""Distribution package completeness: checksums, docs, scripts, instructions."""

from __future__ import annotations

import json
from pathlib import Path

from fixtures.release_tree import build_release_tree

ROOT = Path(__file__).resolve().parents[1]


def test_validation_doc_covers_all_steps():
    text = (ROOT / "docs" / "WINDOWS-EXTERNAL-VALIDATION.md").read_text(
        encoding="utf-8")
    for term in ("checksums", "Silent install", "Desktop startup",
                 "User data", "upgrade", "rollback", "Uninstall",
                 "Troubleshooting", "owner"):
        assert term.lower() in text.lower(), term


def test_release_manifest_has_policy_fields(tmp_path):
    release, _ = build_release_tree(tmp_path)
    doc = json.loads((release / "RELEASE-MANIFEST.json").read_text(
        encoding="utf-8"))
    for field in ("version", "min_version", "blocked_versions", "rollout",
                  "published_at", "files", "checksums_file"):
        assert field in doc
    assert doc["version"] == "0.1.1"


def test_checksums_file_matches_manifest_artifacts(tmp_path):
    release, _ = build_release_tree(tmp_path)
    sums = (release / "RELEASE-SHA256SUMS.txt").read_text()
    manifest = json.loads(
        (release / "RELEASE-MANIFEST.json").read_text())
    for entry in manifest["files"]:
        name = Path(entry["file"]).name
        assert name in sums
        assert entry["sha256"].lower() in sums.lower()


def test_validation_scripts_present():
    assert (ROOT / "scripts" / "validate_desktop.py").is_file()
    assert (ROOT / "scripts" / "build_plan_index.py").is_file()
