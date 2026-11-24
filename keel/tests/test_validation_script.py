"""The reproducible desktop-validation script honestly reports its scope."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import keel

ROOT = Path(__file__).resolve().parents[1]


def _load_validation_script():
    path = ROOT / "scripts" / "validate_desktop.py"
    spec = importlib.util.spec_from_file_location("validate_desktop", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validation_script_reports_pass_and_external(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_desktop.py"),
         "--dist", str(ROOT / "dist")],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode in (0, 1)  # 1 only if a local check FAILs
    doc = json.loads(result.stdout)
    assert "checks" in doc and "unverified_external" in doc
    assert doc["summary"]["pass"] >= 1
    # Every external check must be explicitly unverified, never PASS.
    for item in doc["unverified_external"]:
        assert "reason" in item and "command" in item
        assert "owner" in item["reason"].lower() or "vm" in item["reason"].lower() \
            or "installed" in item["reason"].lower() or "two installer" in item["reason"].lower()


def test_validation_script_derives_installer_name_from_canonical_version(
        tmp_path, monkeypatch, capsys):
    script = _load_validation_script()
    assert script.read_version() == keel.__version__
    assert script.installer_name("0.1.1") == "Keel-Setup-0.1.1.exe"
    # A future version must be picked up without editing the script.
    monkeypatch.setattr(script, "read_version", lambda: "9.9.9")
    monkeypatch.setattr(sys, "argv", ["validate_desktop.py", "--dist", str(tmp_path)])
    assert script.main() == 1  # artifacts missing
    doc = json.loads(capsys.readouterr().out)
    external = {item["name"]: item for item in doc["unverified_external"]}
    assert "Keel-Setup-9.9.9.exe" in external["installer_install"]["command"]
    assert "install 0.1.0 then 9.9.9" in external["upgrade_and_rollback"]["command"]
