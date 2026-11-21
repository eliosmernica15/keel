"""C13.4 — installer smoke-test harness."""

from __future__ import annotations

import hashlib
import json

from keel.installer_smoke import check_manifest, ci_only_checks


def test_missing_manifest_reported(tmp_path):
    checks = check_manifest(tmp_path, "0.1.1")
    assert checks and checks[0].ok is False


def test_manifest_checksum_verification(tmp_path):
    name = "Keel-Setup-0.1.1.exe"
    payload = b"fake-installer"
    (tmp_path / name).write_bytes(payload)
    doc = {"files": [{"file": name,
                      "sha256": hashlib.sha256(payload).hexdigest()}],
           "min_version": "0.1.0", "blocked_versions": []}
    (tmp_path / "RELEASE-MANIFEST.json").write_text(
        json.dumps(doc), encoding="utf-8")
    checks = check_manifest(tmp_path, "0.1.1")
    win = next(c for c in checks if c.target == "windows")
    assert win.ok is True
    assert next(c for c in checks if c.target == "upgrade_policy").ok is True


def test_ci_only_checks_are_declared():
    checks = ci_only_checks()
    assert any("clean-VM" in c for c in checks)
    assert any("rollback" in c for c in checks)
