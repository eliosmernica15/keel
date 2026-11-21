"""Ed25519 release signing infrastructure (ephemeral test keys only)."""

from __future__ import annotations

import json
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from keel.release import common, verify
from keel.release.signing import (
    canonical_json,
    generate_keypair,
    load_private_key,
    load_public_key,
    sign_bytes,
    sign_manifest,
    verify_bytes,
    verify_manifest,
)


def test_detached_signature_roundtrip_and_tamper(tmp_path):
    private_path = tmp_path / "test.pem"
    public_path = tmp_path / "test.pub.pem"
    generate_keypair(private_path, public_path)
    private = load_private_key(private_path)
    public = load_public_key(public_path)

    payload = b"artifact-bytes"
    signature = sign_bytes(payload, private)
    assert verify_bytes(payload, signature, public)
    assert not verify_bytes(b"tampered", signature, public)


def test_manifest_signature_roundtrip_and_tamper(tmp_path):
    private_path = tmp_path / "test.pem"
    public_path = tmp_path / "test.pub.pem"
    generate_keypair(private_path, public_path)
    private = load_private_key(private_path)
    public = load_public_key(public_path)

    doc = {"version": "0.1.1", "files": [{"file": "a.exe"}]}
    signed = sign_manifest(doc, private)
    assert signed["signature_algorithm"] == "ed25519"
    assert verify_manifest(signed, public)

    tampered = dict(signed)
    tampered["version"] = "0.1.2"
    assert not verify_manifest(tampered, public)


def test_verify_release_manifest_checks_detached_signatures(tmp_path):
    private_path = tmp_path / "test.pem"
    public_path = tmp_path / "test.pub.pem"
    generate_keypair(private_path, public_path)
    private = load_private_key(private_path)
    public = load_public_key(public_path)

    serve_root = tmp_path / "serve"
    tag_dir = serve_root / "v0.1.1"
    tag_dir.mkdir(parents=True)
    (tag_dir / "Keel-Setup-0.1.1.exe").write_bytes(b"installer")
    (tag_dir / "Keel-Setup-0.1.1.exe.sig").write_bytes(
        sign_bytes(b"installer", private))

    port = 8796
    server = ThreadingHTTPServer(
        ("127.0.0.1", port),
        lambda *a, **k: SimpleHTTPRequestHandler(*a, directory=str(serve_root), **k))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)
    try:
        base = f"http://127.0.0.1:{port}"
        manifest = common.build_release_manifest(
            {"Keel-Setup-0.1.1.exe": tag_dir / "Keel-Setup-0.1.1.exe"},
            "0.1.1", "v0.1.1", base)
        errors = verify.verify_release_manifest(
            manifest, allow_http=True, retries=1, public_key=public)
        assert errors == []

        (tag_dir / "Keel-Setup-0.1.1.exe.sig").write_bytes(b"bad-signature")
        errors = verify.verify_release_manifest(
            manifest, allow_http=True, retries=1, public_key=public)
        assert any("signature invalid" in e for e in errors)
    finally:
        server.shutdown()
        server.server_close()


def test_build_cli_exposes_signing_options():
    from keel.release.cli import build_parser

    parser = build_parser()
    build = parser.parse_args(["build", "--signing-key", "test.pem"])
    assert build.signing_key == "test.pem"
    check = parser.parse_args(["verify", "--manifest", "download.json",
                               "--public-key", "test.pub.pem"])
    assert check.public_key == "test.pub.pem"
