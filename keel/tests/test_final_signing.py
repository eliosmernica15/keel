"""Unified release signing pipeline tests (synthetic ephemeral keys only).

All keys are generated inside ``tmp_path`` for these tests. Nothing here
produces or represents a trusted Windows/macOS distribution signature.
"""

from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from keel.release import cli, common, publish
from keel.release.signing import (
    KEY_ID_ENV,
    MODE_ENV,
    PRIVATE_KEY_FILE_ENV,
    TRUSTED_KEYS_ENV,
    SigningGateError,
    SigningMode,
    SecretRef,
    canonical_json,
    distribution_readiness_errors,
    generate_keypair,
    load_private_key,
    load_public_key,
    register_platform_verifier,
    resolve_mode,
    sign_bytes,
    sign_manifest,
    sign_release_manifest,
    unregister_platform_verifier,
    verify_bytes,
    verify_manifest,
    verify_release_bundle,
    verify_signed_release,
    KeyRing,
)

VERSION = common.validate_version()
IDENTITY_ENV = (
    "KEEL_WINDOWS_SIGNING_IDENTITY",
    "KEEL_MACOS_SIGNING_IDENTITY",
    "KEEL_MACOS_NOTARY_PROFILE",
    "KEEL_SIGNING_TRUSTED_KEYS",
)


def _keys(tmp_path: Path, label: str = "release"):
    private_path = tmp_path / "keys" / f"{label}.pem"
    public_path = tmp_path / "keys" / f"{label}.pub.pem"
    generate_keypair(private_path, public_path)
    return private_path, public_path


def _stage(
    tmp_path: Path,
    private: Ed25519PrivateKey,
    *,
    signed: bool = True,
    key_id: str = "release-2026-01",
    lifetime_seconds: int | None = None,
) -> Path:
    stage = tmp_path / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Path] = {}
    for name in common.expected_filenames(VERSION):
        path = stage / name
        path.write_bytes(f"installer:{name}".encode("utf-8"))
        artifacts[name] = path
    doc = common.build_release_manifest(
        artifacts, VERSION, f"v{VERSION}", "https://example.invalid/download")
    if signed:
        doc = sign_release_manifest(
            doc, private, key_id=key_id, mode=SigningMode.TEST,
            lifetime_seconds=lifetime_seconds)
        for name, path in artifacts.items():
            (stage / f"{name}.sig").write_bytes(
                sign_bytes(path.read_bytes(), private))
    (stage / "RELEASE-MANIFEST.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return stage


def _manifest(stage: Path) -> dict:
    return json.loads((stage / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))


def _write_manifest(stage: Path, doc: dict) -> None:
    (stage / "RELEASE-MANIFEST.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


# --- modes and secure key references ---------------------------------------


def test_modes_are_explicit_and_env_overridable():
    assert resolve_mode(None, env={}) is SigningMode.DEV
    assert resolve_mode(None, env={MODE_ENV: "test"}) is SigningMode.TEST
    assert resolve_mode("distribution", env={MODE_ENV: "test"}) is SigningMode.DISTRIBUTION
    with pytest.raises(ValueError, match="unknown signing mode"):
        resolve_mode("trusted", env={})


def test_secret_refs_accept_names_not_key_values(tmp_path):
    private_path, public_path = _keys(tmp_path)
    pem = private_path.read_text(encoding="utf-8")

    assert SecretRef(PRIVATE_KEY_FILE_ENV, "env").resolve(
        env={PRIVATE_KEY_FILE_ENV: str(private_path)}) == private_path
    assert SecretRef("config.key", "config").resolve(
        {"config.key": str(public_path)}) == public_path
    assert SecretRef("KEEL_RELEASE_ED25519", "ci").resolve(
        {"KEEL_RELEASE_ED25519": str(private_path)}) == private_path
    assert SecretRef("KEEL_RELEASE_ED25519", "ci").resolve(
        env={"KEEL_RELEASE_ED25519_FILE": str(private_path)}) == private_path

    for resolve in (
        lambda: SecretRef("bad", "env").resolve(env={"bad": pem}),
        lambda: SecretRef("bad", "config").resolve({"bad": pem}),
    ):
        with pytest.raises(ValueError, match="never accepted") as excinfo:
            resolve()
        assert "BEGIN PRIVATE KEY" not in str(excinfo.value)
    with pytest.raises(ValueError, match="must be materialized as a PEM file"):
        SecretRef("KEEL_RELEASE_ED25519", "ci").resolve({}, env={})
    with pytest.raises(ValueError, match="never accepted"):
        load_private_key(pem)
    assert load_private_key(private_path) is not None
    assert load_public_key(public_path) is not None


def test_key_material_is_never_leaked_in_errors(tmp_path):
    private_path, _ = _keys(tmp_path)
    pem = private_path.read_text(encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        SecretRef("bad", "env").resolve(env={"bad": pem})
    assert pem not in str(excinfo.value)
    assert "PRIVATE KEY" not in str(excinfo.value)


# --- signature mechanics ----------------------------------------------------


def test_detached_signature_roundtrip_and_tamper(tmp_path):
    private_path, public_path = _keys(tmp_path)
    private, public = load_private_key(private_path), load_public_key(public_path)
    signature = sign_bytes(b"artifact", private)
    assert verify_bytes(b"artifact", signature, public)
    assert not verify_bytes(b"tampered", signature, public)

    legacy = sign_manifest({"version": VERSION}, private)
    assert verify_manifest(legacy, public)
    tampered = dict(legacy, version="0.0.0")
    assert not verify_manifest(tampered, public)


def test_manifest_binding_covers_metadata_and_payload(tmp_path):
    private_path, public_path = _keys(tmp_path)
    private, public = load_private_key(private_path), load_public_key(public_path)
    doc = {"version": VERSION, "files": [{"file": "a.exe", "sha256": "ab" * 32}]}
    signed = sign_release_manifest(
        doc, private, key_id="release-2026-01", mode=SigningMode.TEST)
    assert signed["signature_mode"] == "test"
    assert signed["signature_key_id"] == "release-2026-01"
    assert verify_manifest(signed, public)

    for field, value in (
        ("version", "0.0.0"),
        ("signature_key_id", "other-key"),
        ("signature_mode", "dev"),
        ("signature", "00" * 64),
        ("signature_algorithm", "rsa"),
        ("signature_envelope", "legacy"),
    ):
        altered = dict(signed, **{field: value})
        assert not verify_manifest(altered, public), field
    assert canonical_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_expired_and_malformed_signatures_fail_closed(tmp_path):
    private_path, public_path = _keys(tmp_path)
    private, public = load_private_key(private_path), load_public_key(public_path)
    now = datetime.now(timezone.utc)
    doc = {"version": VERSION}
    expired = sign_release_manifest(
        doc, private, lifetime_seconds=-10, now=now)
    assert not verify_manifest(expired, public, now=now + timedelta(seconds=1))

    malformed = sign_release_manifest(
        doc, private, lifetime_seconds=600, now=now)
    malformed["signature_expires_at"] = "not-a-timestamp"
    assert not verify_manifest(malformed, public, now=now)
    future = sign_release_manifest(doc, private, now=now + timedelta(hours=1))
    assert not verify_manifest(future, public, now=now)


def test_missing_wrong_and_mismatched_signatures_fail(tmp_path):
    private_path, public_path = _keys(tmp_path)
    other_private_path, other_public_path = _keys(tmp_path, "other")
    private, public = load_private_key(private_path), load_public_key(public_path)
    other_public = load_public_key(other_public_path)

    assert not verify_manifest({"version": VERSION}, public)
    signed = sign_release_manifest({"version": VERSION}, private)
    assert not verify_manifest(signed, other_public)  # wrong key
    assert not verify_manifest(dict(signed, signature="zz"), public)
    assert not verify_manifest(dict(signed, signature_algorithm="ed25519+"), public)
    assert not verify_manifest(dict(signed, signature_key_id="unknown"), public)


def test_key_ring_supports_rotation_and_cutover(tmp_path):
    old_private_path, old_public_path = _keys(tmp_path, "old")
    new_private_path, new_public_path = _keys(tmp_path, "new")
    old_private, new_private = load_private_key(old_private_path), load_private_key(
        new_private_path)
    ring = KeyRing.from_refs(
        [old_public_path, new_public_path], key_ids=["old-key", "new-key"])
    doc = {"version": VERSION, "tag": f"v{VERSION}"}
    old_signed = sign_release_manifest(doc, old_private, key_id="old-key")
    new_signed = sign_release_manifest(doc, new_private, key_id="new-key")

    assert ring.verify(old_signed).ok
    assert ring.verify(new_signed).ok
    assert set(ring.key_ids) == {"old-key", "new-key"}

    cutover = KeyRing.from_refs([new_public_path], key_ids=["new-key"])
    assert not cutover.verify(old_signed).ok
    assert any("rotated out" in error for error in cutover.verify(old_signed).errors)
    spoofed = dict(new_signed, signature_key_id="old-key")
    assert not ring.verify(spoofed).ok


def test_key_ring_loads_trusted_keys_from_env_names(tmp_path, monkeypatch):
    _, old_public_path = _keys(tmp_path, "old")
    _, new_public_path = _keys(tmp_path, "new")
    monkeypatch.setenv(TRUSTED_KEYS_ENV,
                       f"{old_public_path},{new_public_path}")
    monkeypatch.setenv(KEY_ID_ENV, "old-key,new-key")
    ring = KeyRing.from_env()
    assert ring.key_ids == ("old-key", "new-key")


# --- staged bundle verification ---------------------------------------------


def test_verify_signed_release_fail_closed(tmp_path):
    private_path, public_path = _keys(tmp_path)
    private = load_private_key(private_path)
    stage = _stage(tmp_path, private)
    assert verify_signed_release(stage, public_path) == []

    first = common.expected_filenames(VERSION)[0]
    (stage / first).write_bytes(b"tampered")
    errors = verify_signed_release(stage, public_path)
    assert any(f"{first}: Ed25519 artifact signature is invalid" == e for e in errors)
    assert any("artifact SHA-256 does not match" in e for e in errors)
    (stage / first).write_bytes(f"installer:{first}".encode("utf-8"))

    doc = _manifest(stage)
    doc["version"] = "0.0.0"
    _write_manifest(stage, doc)
    assert any("missing a valid Ed25519 signature" in e
               for e in verify_signed_release(stage, public_path))
    doc = _manifest(stage)

    (stage / f"{first}.sig").unlink()
    assert any(f"{first}: signature file" in e
               for e in verify_signed_release(stage, public_path))
    (stage / f"{first}.sig").write_bytes(
        sign_bytes((stage / first).read_bytes(), private))

    (stage / "RELEASE-SHA256SUMS.txt").write_text(
        "00" * 32 + f"  {first}\n", encoding="utf-8")
    assert any("checksum file SHA-256" in e
               for e in verify_signed_release(stage, public_path))
    (stage / "RELEASE-SHA256SUMS.txt").unlink()

    assert any("--public-key" in e for e in verify_signed_release(stage, None))
    missing_key = tmp_path / "keys" / "absent.pem"
    assert any("public key file not found" in e
               for e in verify_signed_release(stage, missing_key))


def test_unsafe_and_incomplete_manifests_fail_closed(tmp_path):
    private_path, public_path = _keys(tmp_path)
    private = load_private_key(private_path)
    stage = _stage(tmp_path, private)

    doc = _manifest(stage)
    doc["files"][0]["file"] = "../escape.exe"
    _write_manifest(stage, sign_release_manifest(doc, private))
    assert any("unsafe file name" in e
               for e in verify_signed_release(stage, public_path))

    doc = _manifest(stage)
    doc["files"][0]["file"] = common.expected_filenames(VERSION)[0]
    doc["files"][0].pop("sha256")
    _write_manifest(stage, sign_release_manifest(doc, private))
    assert any("no valid SHA-256 checksum" in e
               for e in verify_signed_release(stage, public_path))


def test_expired_bundle_fails_and_unsigned_bundle_is_reported(tmp_path):
    private_path, public_path = _keys(tmp_path)
    private = load_private_key(private_path)
    stage = _stage(tmp_path, private, signed=False)
    dev = verify_release_bundle(stage, mode=SigningMode.DEV)
    assert dev.ok is True
    assert dev.status == "unsigned"
    assert any("no signature verification performed" in note for note in dev.errors)
    assert not verify_release_bundle(stage, public_key=public_path,
                                     mode=SigningMode.TEST).ok

    signed_stage = _stage(tmp_path / "dev-signed", private)
    dev_signed = verify_release_bundle(signed_stage, mode=SigningMode.DEV)
    assert dev_signed.status == "unsigned"  # honest: key was not supplied
    assert any("NOT verified" in note for note in dev_signed.errors)

    expired_stage = _stage(tmp_path, private, lifetime_seconds=-5)
    result = verify_release_bundle(
        expired_stage, public_key=public_path, mode=SigningMode.TEST,
        now=datetime.now(timezone.utc) + timedelta(seconds=1))
    assert result.ok is False
    assert any("expired" in error for error in result.errors)


# --- distribution trust -----------------------------------------------------


def test_distribution_mode_fails_closed_even_with_valid_test_signatures(
    tmp_path, monkeypatch):
    for name in IDENTITY_ENV:
        monkeypatch.delenv(name, raising=False)
    private_path, public_path = _keys(tmp_path)
    stage = _stage(tmp_path, load_private_key(private_path))
    assert verify_signed_release(stage, public_path) == []

    result = verify_release_bundle(
        stage, public_key=public_path, mode=SigningMode.DISTRIBUTION)
    assert result.ok is False
    assert result.status == "failed"
    assert result.trusted_distribution is False
    assert any("trusted distribution pending" in e for e in result.errors)
    assert any("no trusted platform signature verifier registered" in e
               for e in result.errors)

    # A synthetic verifier cannot manufacture trusted distribution status
    # while owner identity configuration is absent.
    register_platform_verifier("windows", lambda root: (True, "synthetic"))
    register_platform_verifier("macos", lambda root: (True, "synthetic"))
    try:
        still_pending = verify_release_bundle(
            stage, public_key=public_path, mode=SigningMode.DISTRIBUTION)
        assert still_pending.ok is False
        assert not still_pending.trusted_distribution
    finally:
        unregister_platform_verifier("windows")
        unregister_platform_verifier("macos")


def test_platform_verifier_errors_are_gate_errors(tmp_path, monkeypatch):
    for name in IDENTITY_ENV:
        monkeypatch.setenv(name, "configured-name")
    monkeypatch.setenv("KEEL_SIGNING_TRUSTED_KEYS", "owner-key.pem")
    private_path, public_path = _keys(tmp_path)
    stage = _stage(tmp_path, load_private_key(private_path))
    register_platform_verifier(
        "windows", lambda root: (False, "no valid Authenticode signature"))
    register_platform_verifier("macos", lambda root: (False, "not notarized"))
    try:
        result = verify_release_bundle(
            stage, public_key=public_path, mode=SigningMode.DISTRIBUTION)
        assert result.ok is False
        assert any("platform signature not verified" in e for e in result.errors)
        assert distribution_readiness_errors(env={
            name: "configured-name" for name in IDENTITY_ENV}) == []
    finally:
        unregister_platform_verifier("windows")
        unregister_platform_verifier("macos")


# --- CLI honesty and backward compatibility ---------------------------------


def test_signing_status_cli_reports_honest_unsigned_status(tmp_path):
    private_path, public_path = _keys(tmp_path)
    unsigned = _stage(tmp_path, load_private_key(private_path), signed=False)
    code, out, err = _run_cli(["signing-status", "--artifacts", str(unsigned)])
    assert code == 0, err
    payload = json.loads(out)
    assert payload["status"] == "unsigned"
    assert payload["verified"] is False  # dev mode performed no verification
    assert payload["trusted_distribution"] is False
    assert "no signature verification performed" in payload["errors"][0]

    signed = _stage(tmp_path / "signed", load_private_key(private_path))
    code, out, err = _run_cli([
        "signing-status", "--artifacts", str(signed),
        "--public-key", str(public_path), "--mode", "test"])
    assert code == 0, err
    payload = json.loads(out)
    assert payload["status"] == "test-verified"
    assert payload["mode"] == "test"
    assert payload["trusted_distribution"] is False
    assert "PRIVATE KEY" not in out + err


def test_dry_run_mode_gate_and_honest_status(tmp_path):
    private_path, public_path = _keys(tmp_path)
    private = load_private_key(private_path)
    unsigned = _stage(tmp_path, private, signed=False)
    dist = tmp_path / "no-dist"

    code, out, err = _run_cli([
        "dry-run", "--artifacts", str(unsigned), "--dist", str(dist)])
    assert code == 0, err
    assert "OK - dry run passed" in out
    assert "Signing status: unsigned" in out

    code, out, err = _run_cli([
        "dry-run", "--artifacts", str(unsigned), "--dist", str(dist),
        "--mode", "test", "--require-signed", "--public-key", str(public_path)])
    assert code != 0
    assert "RELEASE SIGNING GATE FAILED" in err
    assert "OK - dry run passed" not in out

    code, out, err = _run_cli([
        "dry-run", "--artifacts", str(unsigned), "--dist", str(dist),
        "--mode", "distribution", "--public-key", str(public_path)])
    assert code != 0
    assert "trusted distribution pending" in err

    signed = _stage(tmp_path / "signed", private)
    code, out, err = _run_cli([
        "dry-run", "--artifacts", str(signed), "--dist", str(dist),
        "--mode", "test", "--require-signed", "--public-key", str(public_path)])
    assert code == 0, err
    assert "Release signing gate: manifest and all artifacts verified" in out


def test_verify_cli_reports_unsigned_and_signed_status(tmp_path):
    private_path, public_path = _keys(tmp_path)
    plain = tmp_path / "download.json"
    plain.write_text(json.dumps({"channels": {}}), encoding="utf-8")
    code, out, err = _run_cli(["verify", "--manifest", str(plain)])
    assert code == 0, err
    assert "Signature status: UNSIGNED / NOT VERIFIED" in out

    signed = sign_release_manifest(
        {"channels": {}}, load_private_key(private_path), mode=SigningMode.TEST)
    signed_path = tmp_path / "signed-download.json"
    signed_path.write_text(json.dumps(signed), encoding="utf-8")
    code, out, err = _run_cli([
        "verify", "--manifest", str(signed_path),
        "--public-key", str(public_path)])
    assert code == 0, err
    assert "Ed25519 signature VERIFIED" in out
    assert "not trusted Windows/macOS platform signing" in out


def test_publish_dry_run_reports_test_signing_status(tmp_path, monkeypatch):
    private_path, public_path = _keys(tmp_path)
    signed = _stage(tmp_path, load_private_key(private_path))

    def forbidden(*args, **kwargs):
        raise AssertionError("network access attempted during dry run")

    monkeypatch.setattr(publish, "token_from_env", forbidden)
    monkeypatch.setattr(publish, "GitHubClient", forbidden)
    out = io.StringIO()
    with redirect_stdout(out):
        assert publish.publish_command(argparse.Namespace(
            artifacts=str(signed), out=str(tmp_path / "publish-out"),
            repo="owner/repo", tag=f"v{VERSION}", dry_run=True,
            require_signed=True, public_key=str(public_path),
            mode="test")) == 0
    assert "Signing status: TEST Ed25519 signatures verified" in out.getvalue()
    assert "not trusted platform signing" in out.getvalue()

    with pytest.raises(SigningGateError, match="trusted distribution pending"):
        publish.publish_command(argparse.Namespace(
            artifacts=str(signed), out=str(tmp_path / "publish-out-dist"),
            repo="owner/repo", tag=f"v{VERSION}", dry_run=True,
            require_signed=True, public_key=str(public_path),
            mode="distribution"))
