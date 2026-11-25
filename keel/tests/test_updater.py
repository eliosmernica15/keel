"""Updater verification, atomic install and rollback tests."""

from __future__ import annotations

import json
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from keel.release import common, updater
from keel.release.signing import (
    generate_keypair,
    load_private_key,
    load_public_key,
    sign_bytes,
    sign_manifest,
)


@pytest.fixture
def signed_release(tmp_path):
    private_path = tmp_path / "test.pem"
    public_path = tmp_path / "test.pub.pem"
    generate_keypair(private_path, public_path)
    private = load_private_key(private_path)
    public = load_public_key(public_path)

    serve_root = tmp_path / "serve"
    tag_dir = serve_root / "v0.1.2"
    tag_dir.mkdir(parents=True)
    payload = b"new-installer-bytes"
    artifact = tag_dir / "Keel-Setup-0.1.2.exe"
    artifact.write_bytes(payload)
    (tag_dir / "Keel-Setup-0.1.2.exe.sig").write_bytes(
        sign_bytes(payload, private))

    manifest = common.build_release_manifest(
        {"Keel-Setup-0.1.2.exe": artifact},
        "0.1.2", "v0.1.2", f"http://127.0.0.1:8797")
    signed_manifest = sign_manifest(manifest, private)
    (serve_root / "download.json").write_text(
        json.dumps(signed_manifest), encoding="utf-8")

    server = ThreadingHTTPServer(
        ("127.0.0.1", 8797),
        lambda *a, **k: SimpleHTTPRequestHandler(*a, directory=str(serve_root), **k))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)
    try:
        yield public, "http://127.0.0.1:8797/download.json", payload
    finally:
        server.shutdown()
        server.server_close()


def test_check_and_download_signed_update(signed_release, tmp_path):
    public, manifest_url, payload = signed_release
    plan = updater.check_for_update(
        manifest_url, current_version="0.1.1", platform="windows",
        public_key=public, allow_http=True)
    assert plan is not None
    assert plan.version == "0.1.2"

    target = tmp_path / "downloaded.exe"
    updater.download_update(plan, target, public_key=public, allow_http=True)
    assert target.read_bytes() == payload


def test_check_rejects_tampered_manifest(signed_release, tmp_path):
    _, manifest_url, _ = signed_release
    path = Path(manifest_url.replace("http://127.0.0.1:8797/", ""))
    full = tmp_path / "tampered.json"
    doc = json.loads((tmp_path / "serve" / "download.json").read_text(
        encoding="utf-8"))
    doc["version"] = "0.1.3"
    full.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(updater.UpdateError):
        updater.check_for_update(
            str(full), current_version="0.1.1", platform="windows",
            public_key=load_public_key(tmp_path / "test.pub.pem"),
            allow_http=True)


def test_update_check_cli(signed_release, tmp_path):
    import subprocess
    import sys

    _, manifest_url, _ = signed_release
    public_key = tmp_path / "test.pub.pem"
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "keel.release", "update-check",
         "--manifest", manifest_url, "--current", "0.1.1",
         "--platform", "windows", "--public-key", str(public_key),
         "--allow-http"],
        cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["available"] if "available" in plan else plan["version"] == "0.1.2"


def test_electron_update_check_is_opt_in():
    source = (Path(__file__).resolve().parents[1] / "desktop-app" /
              "main.js").read_text(encoding="utf-8")
    assert "KEEL_UPDATE_MANIFEST_URL" in source
    assert "checkForUpdates();" in source
    # SEC-F-06: the advisory plan is now fail-closed on a missing key too.
    assert "if (!manifest || !key) return;" in source


def test_atomic_install_and_rollback(tmp_path):
    install = tmp_path / "install"
    backup = tmp_path / "backup"
    staged = tmp_path / "staged"
    install.mkdir()
    backup.mkdir()
    staged.mkdir()
    (install / "version.txt").write_text("old", encoding="utf-8")
    (staged / "version.txt").write_text("new", encoding="utf-8")

    updater.atomic_install(staged, install, backup)
    assert (install / "version.txt").read_text(encoding="utf-8") == "new"
    assert (backup / "version.txt").read_text(encoding="utf-8") == "old"

    updater.rollback(install, backup)
    assert (install / "version.txt").read_text(encoding="utf-8") == "old"


def test_failed_install_restores_original(tmp_path):
    install = tmp_path / "install"
    backup = tmp_path / "backup"
    install.mkdir()
    (install / "version.txt").write_text("old", encoding="utf-8")

    with pytest.raises(updater.UpdateError):
        updater.atomic_install(tmp_path / "missing", install, backup)
    assert (install / "version.txt").read_text(encoding="utf-8") == "old"
