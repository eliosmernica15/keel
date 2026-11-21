"""C12.2/C12.3/C12.5 — distribution hardening scaffolding."""

from __future__ import annotations

from keel.distribution import (airgap_bundle, portable_manifest,
                               static_repo_layout, write_bundle_index)


def test_airgap_bundle(tmp_path):
    (tmp_path / "app.zip").write_bytes(b"payload")
    doc = airgap_bundle(["app.zip", "missing.zip"], tmp_path)
    assert doc["format"] == "keel-airgap-v1"
    assert len(doc["files"]) == 1 and doc["files"][0]["bytes"] == 7


def test_static_repo_layout(tmp_path):
    layout = static_repo_layout(tmp_path, "apt")
    assert layout["distro"] == "apt" and layout["complete"] is False
    for name in layout["expected"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    assert static_repo_layout(tmp_path, "apt")["complete"] is True


def test_portable_manifest_and_index(tmp_path):
    manifest = portable_manifest("0.1.1", "windows")
    assert manifest["portable"] is True and manifest["format"] == "zip"
    path = write_bundle_index(manifest, tmp_path / "index.json")
    assert path.is_file()
