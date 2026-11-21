"""B5.1 — download page OS/CPU auto-detection."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "site" / "ui" / "landing-download.js"


def test_platform_detection_wired():
    js = JS.read_text(encoding="utf-8")
    assert "function detectPlatform" in js
    assert "userAgentData" in js
    assert "recommended" in js
    assert "data-os" in js


def test_js_syntax():
    result = subprocess.run(
        ["node", "--check", str(JS)], cwd=ROOT,
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
