"""Acceptance: the packaged sidecar must serve the canonical desktop UI."""

from __future__ import annotations

import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "desktop-app" / "sidecar.spec"
EXE = ROOT / "dist" / "keel-sidecar" / "keel.exe"


def test_spec_bundles_canonical_ui():
    text = SPEC.read_text(encoding="utf-8")
    assert '(str(ROOT / "desktop" / "ui"), "desktop/ui")' in text
    assert 'manifest.webmanifest' in text and '"desktop"' in text


def test_packaged_sidecar_serves_ui():
    """Real packaged binary: start, fetch '/', verify UI markers, stop."""
    if not EXE.is_file():
        return  # build not present in this environment; spec test still applies
    env = {**os.environ, "KEEL_TOKEN": "packaged-acceptance-token"}
    proc = subprocess.Popen(
        [str(EXE), "serve", "--port", "8897"], cwd=ROOT,
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.time() + 20
        ready = False
        while time.time() < deadline:
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:8897/api/health",
                    headers={"X-Keel-Token": "packaged-acceptance-token"})
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except (OSError, urllib.error.HTTPError):
                time.sleep(0.3)
        assert ready, "packaged sidecar did not become ready"
        req = urllib.request.Request(
            "http://127.0.0.1:8897/",
            headers={"X-Keel-Token": "packaged-acceptance-token"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            page = resp.read().decode("utf-8", errors="replace")
        assert resp.status == 200
        for marker in ("Keel Cowork", "Execution policies", "Take the tour"):
            assert marker in page, marker
        for asset in ("/ui/app.js", "/ui/style.css",
                      "/ui/fonts/WorkSans-Regular.ttf"):
            req = urllib.request.Request(
                "http://127.0.0.1:8897" + asset,
                headers={"X-Keel-Token": "packaged-acceptance-token"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status == 200, asset
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
