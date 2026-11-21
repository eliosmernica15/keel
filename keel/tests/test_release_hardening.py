"""P0 release hardening: manifest policy, mirror failover, dry-run."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from keel.release import common, updater
from keel.release.signing import load_private_key, load_public_key, sign_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_contains_update_policy():
    manifest = common.build_release_manifest({}, "0.1.1", "v0.1.1", "https://example.test")
    assert manifest["min_version"] == "0.1.0"
    assert manifest["blocked_versions"] == []
    assert manifest["rollout"]["mode"] == "full"
    assert manifest["rollout"]["percentage"] == 100
    assert manifest["rollout"]["bucket_count"] == 100


def test_rollout_bucket_is_stable():
    a = updater.rollout_bucket("0.1.2", "device-A")
    b = updater.rollout_bucket("0.1.2", "device-A")
    c = updater.rollout_bucket("0.1.2", "device-B")
    assert a == b
    assert 0 <= a < 100
    assert a != c


def _signed_manifest_file(tmp_path, **overrides):
    private_path = tmp_path / "test.pem"
    public_path = tmp_path / "test.pub.pem"
    from keel.release.signing import generate_keypair

    generate_keypair(private_path, public_path)
    doc = common.build_release_manifest({}, "0.1.2", "v0.1.2", "https://example.test")
    doc.update(overrides)
    signed = sign_manifest(doc, load_private_key(private_path))
    path = tmp_path / "signed-download.json"
    path.write_text(json.dumps(signed), encoding="utf-8")
    return path, load_public_key(public_path)


def test_blocked_version_is_not_offered(tmp_path):
    path, public = _signed_manifest_file(
        tmp_path,
        files=[{"platform": "windows", "version": "0.1.2",
                "file": "a.exe", "url": "https://example.test/a.exe",
                "bytes": 1, "sha256": "0" * 64}],
        blocked_versions=["0.1.2"])
    assert updater.check_for_update(
        str(path), current_version="0.1.1", platform="windows",
        public_key=public) is None


def test_minimum_version_is_enforced(tmp_path):
    path, public = _signed_manifest_file(tmp_path, min_version="0.2.0")
    import pytest

    with pytest.raises(updater.UpdateError, match="below minimum"):
        updater.check_for_update(
            str(path), current_version="0.1.1", platform="windows",
            public_key=public)


def test_mirror_failover_uses_second_signed_manifest(tmp_path):
    path, public = _signed_manifest_file(
        tmp_path,
        files=[{"platform": "windows", "version": "0.1.2",
                "file": "a.exe", "url": "https://example.test/a.exe",
                "bytes": 1, "sha256": "0" * 64}])

    class NotFound(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 8798), NotFound)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.2)
    try:
        plan = updater.check_for_update(
            ["http://127.0.0.1:8798/download.json", str(path)],
            current_version="0.1.1", platform="windows",
            public_key=public, allow_http=True)
        assert plan is not None and plan.version == "0.1.2"
    finally:
        server.shutdown()
        server.server_close()


def test_release_dry_run_command():
    result = subprocess.run(
        [sys.executable, "-m", "keel.release", "dry-run",
         "--dist", str(ROOT / "nonexistent-dist"),
         "--artifacts", str(ROOT / "nonexistent-release")],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "no release published" in result.stdout
