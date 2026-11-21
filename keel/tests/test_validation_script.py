"""The reproducible desktop-validation script honestly reports its scope."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
