"""M1 release/artifact protection regression tests."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from keel.release.artifacts import (scan_secret_markers, scan_sidecar_payload,
                                    scan_tree, validate_staged_release)
from keel.release.common import expected_filenames
from keel.release.licenses import write_inventory

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
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


def test_scan_tree_flags_internal_json_metadata(tmp_path):
    root = tmp_path / "site"
    _touch(root, "download.json", '{"__hosting__": "internal note"}')
    assert "download.json" in scan_tree(root)


def test_committed_download_manifest_has_no_internal_metadata():
    doc = json.loads((SITE / "download.json").read_text(encoding="utf-8"))
    assert "__hosting__" not in doc


def test_scan_tree_accepts_allowed_packaged_files(tmp_path):
    root = tmp_path / "win-unpacked"
    _touch(root, "resources/site/index.html", "<html></html>")
    _touch(root, "resources/site/ui/app.js", "console.log(1)")
    _touch(root, "resources/site/LICENSE.electron.txt", "MIT")
    _touch(root, "resources/keel/keel.exe", "binary")
    assert scan_tree(root) == []


def test_sidecar_payload_accepts_legitimate_runtime(tmp_path):
    root = tmp_path / "keel-sidecar"
    root.mkdir(parents=True)
    (root / "keel.exe").write_bytes(b"MZ\x00\x01binary")
    skill = root / "keel" / "resources" / "default-skills" / "academy-guide"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: academy-guide\n---\n", encoding="utf-8")
    (skill / "LICENSE.txt").write_text("Apache License 2.0", encoding="utf-8")
    (skill / "font.ttf").write_bytes(b"\x00\x01\x00\x00binaryfont")
    assert scan_sidecar_payload(root) == []


def test_sidecar_payload_rejects_prohibited_files(tmp_path):
    root = tmp_path / "keel-sidecar"
    root.mkdir(parents=True)
    (root / "keel.exe").write_bytes(b"MZ\x00\x01binary")
    _touch(root, "keel/resources/default-skills/ok/SKILL.md", "---\nname: ok\n---\n")
    _touch(root, ".vercel/project.json", "{}")
    _touch(root, "licensing-and-provenance-review.md")
    _touch(root, "ui/app.js.map", "{}")
    _touch(root, "config/.env", "TOKEN=x")
    _touch(root, "tools/internal.py", "print(1)")
    _touch(root, "notes/secret.txt", 'api_key = "sk-abcdefghijklmnopqrstuvwxyz"')

    found = scan_sidecar_payload(root)
    assert ".vercel/project.json" in found
    assert "licensing-and-provenance-review.md" in found
    assert "ui/app.js.map" in found
    assert "config/.env" in found
    assert "tools/internal.py" in found
    assert "notes/secret.txt" in found
    assert "keel.exe" not in found
    assert "keel/resources/default-skills/ok/SKILL.md" not in found


def test_secret_marker_scan_skips_binary_runtime(tmp_path):
    (tmp_path / "keel.exe").write_bytes(b"MZ\x00sk-abcdefghijklmnopqrstuvwxyz")
    assert scan_secret_markers(tmp_path) == []


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


def test_gitleaks_config_is_present_and_narrowly_scoped():
    config = tomllib.loads((REPO / ".gitleaks.toml").read_text(encoding="utf-8"))
    assert config["extend"]["useDefault"] is True
    # No broad global allowlist may suppress whole commits or paths.
    assert "allowlist" not in config
    blocks = config["allowlists"]
    assert len(blocks) >= 10
    for block in blocks:
        assert block["condition"] == "AND"
        assert block["targetRules"] == ["generic-api-key"]
        assert len(block["commits"]) == 1
        assert len(block["commits"][0]) == 40
        assert len(block["paths"]) == 1
        assert block["description"]
    # Every reviewed historical finding is covered by an exact path.
    joined = "\n".join(block["paths"][0] for block in blocks)
    for path in (
        "stream-json-events\\.jsonl",
        "stream-json-toolcall\\.jsonl",
        "verify-stream-json-partial\\.jsonl",
        "AREA-SDK-STREAMING-SECTION\\.md",
        "observed-stream-event-sequence\\.jsonl",
        "claude-code-evidence\\.md",
        "keel/site/app\\.js",
        "keel/site/index\\.html",
    ):
        assert path in joined


def _allowlist_block():
    config = tomllib.loads((REPO / ".gitleaks.toml").read_text(encoding="utf-8"))
    return config["allowlists"][0]


def _allowlist_applies(block: dict, finding: dict) -> bool:
    """Mirror gitleaks allowlist semantics for the four regression cases."""
    if finding["rule"] not in block.get("targetRules", []):
        return False
    criteria: list[bool] = []
    if block.get("commits"):
        criteria.append(finding["commit"] in block["commits"])
    if block.get("paths"):
        criteria.append(any(re.search(p, finding["file"]) for p in block["paths"]))
    if not criteria:
        return False
    if block.get("condition", "OR") == "AND":
        return all(criteria)
    return any(criteria)


def test_allowlist_covers_exact_commit_and_path_for_target_rule():
    block = _allowlist_block()
    finding = {
        "commit": block["commits"][0],
        "file": "agent-reference-shots/area-headless-programmatic/stream-json-events.jsonl",
        "rule": "generic-api-key",
    }
    assert _allowlist_applies(block, finding) is True


def test_allowlist_does_not_cover_same_commit_different_path():
    block = _allowlist_block()
    finding = {
        "commit": block["commits"][0],
        "file": "agent-reference-shots/area11-interface-comm/other-capture.jsonl",
        "rule": "generic-api-key",
    }
    assert _allowlist_applies(block, finding) is False


def test_allowlist_does_not_cover_same_path_different_commit():
    block = _allowlist_block()
    finding = {
        "commit": "0" * 40,
        "file": "agent-reference-shots/area-headless-programmatic/stream-json-events.jsonl",
        "rule": "generic-api-key",
    }
    assert _allowlist_applies(block, finding) is False


def test_allowlist_does_not_cover_other_rules():
    block = _allowlist_block()
    finding = {
        "commit": block["commits"][0],
        "file": "agent-reference-shots/area-headless-programmatic/stream-json-events.jsonl",
        "rule": "aws-access-token",
    }
    assert _allowlist_applies(block, finding) is False


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
    assert package["homepage"] == "https://keel-desktop.vercel.app"
    assert package["build"]["linux"]["maintainer"] == "Keel Team"
    assert "github.com" not in json.dumps(package).lower()
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
