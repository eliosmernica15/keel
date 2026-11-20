"""M1 release/artifact protection regression tests."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from keel.release.artifacts import scan_tree, validate_staged_release
from keel.release.common import expected_filenames
from keel.release.licenses import write_inventory

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def _touch(root: Path, rel: str, content: str = "x") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_scan_tree_flags_prohibited_files(tmp_path):
    root = tmp_path / "bundle"
    _touch(root, "site/index.html", "<html></html>")
    _touch(root, "site/ui/app.js", "console.log(1)")
    _touch(root, "site/.vercel/project.json", "{}")
    _touch(root, "site/app.js.map", "{}")
    _touch(root, "agent-reference-shots/capture.json", "{}")
    _touch(root, "docs/licensing-and-provenance-review.md")
    _touch(root, "docs/proprietary/EULA.draft.md")
    _touch(root, "docs/internal/DISTRIBUTION-TRANSITION-RUNBOOK.md")
    _touch(root, "site/.env", "SECRET=placeholder")

    found = scan_tree(root)
    assert "site/.vercel/project.json" in found
    assert "site/app.js.map" in found
    assert "agent-reference-shots/capture.json" in found
    assert "docs/licensing-and-provenance-review.md" in found
    assert "docs/proprietary/EULA.draft.md" in found
    assert "docs/internal/DISTRIBUTION-TRANSITION-RUNBOOK.md" in found
    assert "site/.env" in found
    assert "site/index.html" not in found
    assert "site/ui/app.js" not in found


def test_scan_tree_accepts_allowed_packaged_files(tmp_path):
    root = tmp_path / "win-unpacked"
    _touch(root, "resources/site/index.html", "<html></html>")
    _touch(root, "resources/site/ui/app.js", "console.log(1)")
    _touch(root, "resources/site/LICENSE.electron.txt", "MIT")
    _touch(root, "resources/keel/keel.exe", "binary")
    assert scan_tree(root) == []


def test_staged_release_rejects_prohibited_file(tmp_path):
    for name in expected_filenames("0.1.1"):
        _touch(tmp_path, name)
    _touch(tmp_path, "licensing-and-provenance-review.md")
    try:
        validate_staged_release(tmp_path, "0.1.1")
    except ValueError as exc:
        assert "licensing-and-provenance-review.md" in str(exc)
    else:
        raise AssertionError("prohibited staged file was accepted")


def test_staged_release_accepts_expected_files(tmp_path):
    for name in expected_filenames("0.1.1"):
        _touch(tmp_path, name)
    _touch(tmp_path, "RELEASE-MANIFEST.json")
    validate_staged_release(tmp_path, "0.1.1", set(expected_filenames("0.1.1")))


def test_staged_release_reports_missing_required_files(tmp_path):
    try:
        validate_staged_release(tmp_path, "0.1.1", {"Keel-Setup-0.1.1.exe"})
    except ValueError as exc:
        assert "Keel-Setup-0.1.1.exe" in str(exc)
    else:
        raise AssertionError("missing required artifact was accepted")


def test_gitleaks_config_is_present_and_scoped():
    config = tomllib.loads((REPO / ".gitleaks.toml").read_text(encoding="utf-8"))
    assert config["extend"]["useDefault"] is True
    allowlist = config["allowlist"]
    assert any("agent-reference-shots" in item for item in allowlist["paths"])
    assert len(allowlist["commits"]) >= 5
    assert all(len(commit) == 40 for commit in allowlist["commits"])


def test_secret_scan_workflow_is_pinned_and_redacted():
    workflow = (REPO / ".github" / "workflows" / "secret-scan.yml").read_text(
        encoding="utf-8")
    assert "fetch-depth: 0" in workflow
    assert "GITLEAKS_VERSION: 8.30.1" in workflow
    assert "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb" in workflow
    assert "--redact" in workflow
    assert "--config .gitleaks.toml" in workflow
    assert "sha256sum -c -" in workflow


def test_precommit_config_pins_gitleaks():
    config = (REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "https://github.com/gitleaks/gitleaks" in config
    assert "rev: v8.30.1" in config
    assert "--redact" in config


def test_packaging_excludes_development_metadata():
    package = json.loads((ROOT / "desktop-app" / "package.json").read_text(
        encoding="utf-8"))
    assert "repository" not in package
    assert "email" not in package["author"]
    site_resource = next(r for r in package["build"]["extraResources"]
                         if r["to"] == "site")
    filters = set(site_resource["filter"])
    assert "!**/.vercel/**" in filters
    assert "!**/.git/**" in filters
    assert "!README.md" in filters


def test_dependency_license_inventory_is_written(tmp_path):
    path = write_inventory(tmp_path / "inventory.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["generator"] == "keel.release.licenses"
    assert isinstance(doc["python"], list) and doc["python"]
    assert isinstance(doc["electron"], list) and doc["electron"]
    assert isinstance(doc["unresolved"], list)
    assert all({"name", "version", "license", "ecosystem"} <= set(item)
               for item in doc["python"] + doc["electron"])
