"""Hard-fail release signing gate regression tests.

Every key is generated in-test with ``cryptography``. No real credential is
read, generated for production, or printed by these tests.
"""

from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from keel.release import cli, common, publish
from keel.release.signing import (
    SigningGateError,
    require_signed_enabled,
    sign_bytes,
    sign_manifest,
    verify_signed_release,
)

VERSION = common.validate_version()


def _ephemeral_key(tmp_path: Path):
    """Return (private_key, public_key_path) using a throwaway Ed25519 key."""
    private = Ed25519PrivateKey.generate()
    key_dir = tmp_path / "keys"
    key_dir.mkdir(exist_ok=True)
    public_path = key_dir / "release.pub.pem"
    public_path.write_bytes(private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    return private, public_path


def _stage_release(tmp_path: Path, private, *, signed: bool) -> Path:
    """Build a minimal staged release bundle with all expected artifacts."""
    stage = tmp_path / "stage"
    stage.mkdir(exist_ok=True)
    artifacts = {}
    for name in common.expected_filenames(VERSION):
        path = stage / name
        path.write_bytes(f"installer-bytes:{name}".encode("utf-8"))
        artifacts[name] = path
    doc = common.build_release_manifest(
        artifacts, VERSION, f"v{VERSION}", "https://example.invalid/download")
    if signed:
        doc = sign_manifest(doc, private)
        for name, path in artifacts.items():
            (stage / f"{name}.sig").write_bytes(
                sign_bytes(path.read_bytes(), private))
    (stage / "RELEASE-MANIFEST.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return stage


def _dry_run(*, artifacts: Path, public_key: Path | None,
             require_signed: bool = False) -> tuple[int, str, str]:
    argv = ["dry-run", "--artifacts", str(artifacts),
            "--dist", str(artifacts.parent / "no-dist")]
    if public_key is not None:
        argv += ["--public-key", str(public_key)]
    if require_signed:
        argv += ["--require-signed"]
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _publish_args(tmp_path: Path, stage: Path, public_key: Path | None,
                  *, dry_run: bool = False,
                  require_signed: bool = True) -> argparse.Namespace:
    return argparse.Namespace(
        artifacts=str(stage),
        out=str(tmp_path / "publish-out"),
        repo="owner/repo",
        tag=f"v{VERSION}",
        dry_run=dry_run,
        require_signed=require_signed,
        public_key=str(public_key) if public_key else None,
    )


# (a) unsigned manifest + require-signed -> non-zero + clear error
def test_unsigned_manifest_with_require_signed_fails(tmp_path):
    private, public_key = _ephemeral_key(tmp_path)
    stage = _stage_release(tmp_path, private, signed=False)

    code, out, err = _dry_run(
        artifacts=stage, public_key=public_key, require_signed=True)

    assert code != 0
    assert "RELEASE SIGNING GATE FAILED" in err
    assert "RELEASE-MANIFEST.json" in err
    assert "OK - dry run passed" not in out
    assert "PRIVATE KEY" not in out + err


def test_env_flag_enables_gate_and_default_stays_compatible(tmp_path, monkeypatch):
    private, public_key = _ephemeral_key(tmp_path)
    stage = _stage_release(tmp_path, private, signed=False)

    monkeypatch.delenv("KEEL_REQUIRE_SIGNED", raising=False)
    # No flag/env and no --public-key: unsigned local dry-run still passes.
    code, _, _ = _dry_run(artifacts=stage, public_key=None)
    assert code == 0  # backward-compatible unsigned local dry-run

    monkeypatch.setenv("KEEL_REQUIRE_SIGNED", "1")
    assert require_signed_enabled(False) is True
    code, _, err = _dry_run(artifacts=stage, public_key=public_key)
    assert code != 0
    assert "RELEASE SIGNING GATE FAILED" in err


# (b) signed manifest -> proceeds
def test_signed_manifest_proceeds(tmp_path):
    private, public_key = _ephemeral_key(tmp_path)
    stage = _stage_release(tmp_path, private, signed=True)

    code, out, err = _dry_run(
        artifacts=stage, public_key=public_key, require_signed=True)

    assert code == 0, err
    assert "Release signing gate: manifest and all artifacts verified" in out
    assert "OK - dry run passed" in out
    assert "PRIVATE KEY" not in out + err


def test_tampered_artifact_fails_gate(tmp_path):
    private, public_key = _ephemeral_key(tmp_path)
    stage = _stage_release(tmp_path, private, signed=True)
    first = common.expected_filenames(VERSION)[0]
    (stage / first).write_bytes(b"tampered-installer")

    code, _, err = _dry_run(
        artifacts=stage, public_key=public_key, require_signed=True)

    assert code != 0
    assert f"{first}: Ed25519 artifact signature is invalid" in err
    assert f"{first}: artifact SHA-256 does not match signed manifest" in err


# (c) publish path with unsigned artifacts -> blocked before any network write
def test_publish_blocks_unsigned_artifacts(tmp_path, monkeypatch):
    private, public_key = _ephemeral_key(tmp_path)
    stage = _stage_release(tmp_path, private, signed=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("network write attempted for unsigned release")

    monkeypatch.setattr(publish, "token_from_env", forbidden)
    monkeypatch.setattr(publish, "GitHubClient", forbidden)

    with pytest.raises(SigningGateError) as excinfo:
        publish.publish_command(
            _publish_args(tmp_path, stage, public_key, dry_run=False))

    message = str(excinfo.value)
    assert "RELEASE SIGNING GATE FAILED" in message
    assert "RELEASE-MANIFEST.json" in message
    assert "PRIVATE KEY" not in message


def test_publish_cli_returns_nonzero_for_unsigned_release(tmp_path, monkeypatch):
    private, public_key = _ephemeral_key(tmp_path)
    stage = _stage_release(tmp_path, private, signed=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("network write attempted for unsigned release")

    monkeypatch.setattr(publish, "token_from_env", forbidden)
    monkeypatch.setattr(publish, "GitHubClient", forbidden)

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([
            "publish", "--artifacts", str(stage),
            "--out", str(tmp_path / "publish-out"),
            "--repo", "owner/repo", "--tag", f"v{VERSION}",
            "--require-signed", "--public-key", str(public_key),
        ])
    assert code != 0
    assert "RELEASE SIGNING GATE FAILED" in err.getvalue()
    assert "Published Keel" not in out.getvalue()


def test_publish_dry_run_keeps_signed_manifest_authoritative(tmp_path, monkeypatch):
    private, public_key = _ephemeral_key(tmp_path)
    stage = _stage_release(tmp_path, private, signed=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("network access attempted during dry run")

    monkeypatch.setattr(publish, "token_from_env", forbidden)
    monkeypatch.setattr(publish, "GitHubClient", forbidden)

    args = _publish_args(tmp_path, stage, public_key, dry_run=True)
    assert publish.publish_command(args) == 0
    staged = json.loads((stage / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
    published = json.loads(
        (tmp_path / "publish-out" / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
    assert published == staged  # regeneration did not strip the signature


def test_publish_dry_run_unsigned_stays_backward_compatible(tmp_path, monkeypatch):
    private, public_key = _ephemeral_key(tmp_path)
    stage = _stage_release(tmp_path, private, signed=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("network access attempted during dry run")

    monkeypatch.setattr(publish, "token_from_env", forbidden)
    monkeypatch.setattr(publish, "GitHubClient", forbidden)

    code = publish.publish_command(_publish_args(
        tmp_path, stage, None, dry_run=True, require_signed=False))
    assert code == 0


# (d) missing public key -> clear error
def test_missing_public_key_is_clear_error(tmp_path):
    private, _ = _ephemeral_key(tmp_path)
    stage = _stage_release(tmp_path, private, signed=True)

    code, _, err = _dry_run(
        artifacts=stage, public_key=None, require_signed=True)
    assert code != 0
    assert "--public-key" in err
    assert "RELEASE SIGNING GATE FAILED" in err

    errors = verify_signed_release(stage, None)
    assert any("--public-key" in message for message in errors)

    absent = tmp_path / "keys" / "absent.pem"
    errors = verify_signed_release(stage, absent)
    assert any("public key file not found" in message for message in errors)


def test_gate_helpers_are_exposed_on_cli_parser():
    parser = cli.build_parser()
    args = parser.parse_args([
        "dry-run", "--require-signed", "--public-key", "pub.pem"])
    assert args.require_signed is True
    assert args.public_key == "pub.pem"
    publish_args = parser.parse_args([
        "publish", "--artifacts", "release", "--require-signed",
        "--public-key", "pub.pem"])
    assert publish_args.require_signed is True
    assert publish_args.public_key == "pub.pem"
