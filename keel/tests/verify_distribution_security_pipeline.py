"""Agent F — distribution security: release integrity, signing and CI supply chain.

All functional tests use ephemeral Ed25519 keys and temporary files; no release
asset, credential or network endpoint is ever contacted. Known gaps are
``xfail(strict=False)`` with file:line evidence so they stay visible and turn
into XPASS once remediated. Controls are never weakened to make tests pass.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from keel.release import common, signing, verify

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT.parent / ".github" / "workflows"
SHA256 = "a" * 64


def _channel(url: str) -> dict:
    return {
        "version": "0.1.1",
        "channels": {
            "windows": {
                "available": True, "verified": True, "size": 123,
                "sha256": SHA256, "url": url,
            }
        },
    }


# --------------------------------------------------------------------------
# 1. Download integrity / URL policy
# --------------------------------------------------------------------------

def test_channel_verification_requires_public_https_url():
    for url in ("http://evil.example/Keel-Setup.exe", "file:///etc/passwd",
                "ftp://example.com/Keel-Setup.exe", ""):
        errors = verify.verify_manifest(_channel(url), allow_http=False, retries=1)
        assert any("url is not a public HTTPS URL" in e or "missing url" in e
                   for e in errors), (url, errors)


def test_channel_verification_rejects_available_without_verified_or_checksums():
    doc = _channel("https://example.com/Keel-Setup.exe")
    doc["channels"]["windows"]["verified"] = False
    doc["channels"]["windows"]["sha256"] = "short"
    doc["channels"]["windows"]["size"] = 0
    errors = verify.verify_manifest(doc, allow_http=False, retries=1)
    assert any("not marked verified" in e for e in errors)
    assert any("invalid size" in e for e in errors)
    assert any("invalid sha256" in e for e in errors)


def test_fetch_and_load_refuse_public_http_without_allow_http():
    with pytest.raises(ValueError, match="refusing non-HTTPS URL"):
        verify.fetch_bytes("http://example.com/m.json", allow_http=False, timeout=1)
    with pytest.raises(ValueError, match="manifest URL must be HTTPS"):
        verify.load_manifest("http://example.com/m.json", allow_http=False, timeout=1)


def test_release_manifest_files_require_https_scheme():
    doc = {"files": [{"file": "Keel-Setup.exe", "bytes": 1,
                      "sha256": SHA256, "url": "file:///nonexistent-keel-security-test"}]}
    errors = verify.verify_release_manifest(doc, allow_http=False, retries=1)
    assert any("url is not HTTPS" in e for e in errors), errors


def test_artifact_download_validates_redirect_targets():
    src = (ROOT / "src" / "keel" / "release" / "verify.py").read_text(encoding="utf-8")
    assert ("HTTPRedirectHandler" in src or "redirect_request" in src
            or "redirect: manual" in src), "no redirect validation in fetch_bytes"


# --------------------------------------------------------------------------
# 2. Generated manifests / no fake verified flags
# --------------------------------------------------------------------------

@pytest.fixture()
def all_artifacts(tmp_path):
    files = {}
    for name in common.expected_filenames("0.1.1"):
        p = tmp_path / name
        p.write_bytes(b"keel-test-artifact-" + name.encode())
        files[name] = p
    return files


def test_unavailable_generated_manifest_has_no_urls_or_verified_flags(all_artifacts):
    doc = common.build_download_manifest(
        all_artifacts, "0.1.1", "v0.1.1",
        "https://github.com/example/keel/releases/download",
        available=False, verified=False, verified_at=None,
    )
    assert doc["generated"] == "fallback"
    assert doc["base_url"] == "https://github.com/example/keel/releases/download"
    assert doc["verified_at"] is None
    for ch in doc["channels"].values():
        assert ch["available"] is False and ch["verified"] is False
        assert ch["url"] is None and ch["verified_at"] is None
        for alt in ch["alternatives"]:
            assert alt["available"] is False and alt["verified"] is False
            assert alt["url"] is None


def test_verified_only_with_explicit_flag_and_real_base_url(all_artifacts):
    doc = common.build_download_manifest(
        all_artifacts, "0.1.1", "v0.1.1", "",
        available=True, verified=True, verified_at="2026-01-01T00:00:00Z",
    )
    for ch in doc["channels"].values():
        assert ch["available"] is True
        assert ch["url"] is None  # no base_url => no fabricated URL
        assert ch["verified"] is True and ch["verified_at"] is not None


def test_release_manifest_urls_are_first_party_https(all_artifacts):
    doc = common.build_release_manifest(
        all_artifacts, "0.1.1", "v0.1.1",
        "https://github.com/example/keel/releases/download",
    )
    assert doc["files"], "no files in release manifest"
    for entry in doc["files"]:
        assert entry["url"].startswith(
            "https://github.com/example/keel/releases/download/v0.1.1/")
        assert entry["sha256"] == common.sha256_file(all_artifacts[entry["file"]])


# --------------------------------------------------------------------------
# 3. Ed25519 signing (separate from OS code signing)
# --------------------------------------------------------------------------

def test_signing_gate_fails_closed_without_public_key(tmp_path):
    errors = signing.verify_signed_release(tmp_path, None)
    assert errors and "public key" in errors[0].lower()
    assert signing.require_signed_enabled(False) is False
    assert signing.require_signed_enabled(True) is True


def test_signing_gate_verifies_manifest_signature_detached_signatures_and_bytes(tmp_path):
    priv, pub = tmp_path / "k.pem", tmp_path / "k.pub.pem"
    signing.generate_keypair(priv, pub)
    private = signing.load_private_key(priv)
    public = signing.load_public_key(pub)
    name = "Keel-Setup-0.1.1.exe"
    artifact = tmp_path / name
    artifact.write_bytes(b"installer-bytes")
    (tmp_path / f"{name}.sig").write_bytes(signing.sign_bytes(artifact.read_bytes(), private))
    doc = {"files": [{"file": name, "sha256": common.sha256_file(artifact)}]}
    manifest_path = tmp_path / "RELEASE-MANIFEST.json"
    manifest_path.write_text(json.dumps(signing.sign_manifest(doc, private)))

    assert signing.verify_signed_release(tmp_path, pub) == []

    artifact.write_bytes(b"tampered-bytes")
    errors = signing.verify_signed_release(tmp_path, pub)
    assert any("signature is invalid" in e or "SHA-256" in e for e in errors)

    artifact.write_bytes(b"installer-bytes")
    (tmp_path / f"{name}.sig").unlink()
    errors = signing.verify_signed_release(tmp_path, pub)
    assert any("signature file" in e for e in errors)


def test_manifest_signature_rejects_wrong_algorithm_and_tampering(tmp_path):
    priv, pub = tmp_path / "k.pem", tmp_path / "k.pub.pem"
    signing.generate_keypair(priv, pub)
    private, public = signing.load_private_key(priv), signing.load_public_key(pub)
    signed = signing.sign_manifest({"version": "0.1.1"}, private)
    assert signing.verify_manifest(signed, public)
    bad_alg = dict(signed, signature_algorithm="rsa")
    assert not signing.verify_manifest(bad_alg, public)
    tampered = dict(signed, version="0.1.2")
    assert not signing.verify_manifest(tampered, public)


def test_real_publish_is_unconditionally_signing_gated():
    src = (ROOT / "src" / "keel" / "release" / "publish.py").read_text(encoding="utf-8")
    assert "enforce_signing = (not dry_run)" in src
    assert "SigningGateError(" in src
    assert "RELEASE SIGNING GATE FAILED" in src
    assert "verify_release_manifest(" in src and "public_key=remote_public_key" in src


def test_os_code_signing_is_reported_honestly_as_unsigned():
    assert "Unsigned" in common.WINDOWS_NOTES and "SmartScreen" in common.WINDOWS_NOTES
    assert "Unsigned" in common.MACOS_NOTES and "Gatekeeper" in common.MACOS_NOTES
    assert "Unsigned" in common.LINUX_NOTES
    from keel.release.publish import _release_body
    signed = _release_body("0.1.1", "v0.1.1", signed=True)
    assert "Ed25519" in signed
    assert "notarized" not in signed.lower()
    unsigned = _release_body("0.1.1", "v0.1.1", signed=False)
    assert "unsigned" in unsigned.lower()


# --------------------------------------------------------------------------
# 4. CI least privilege, pinned dependencies, no secret exposure
# --------------------------------------------------------------------------

def _workflow_texts():
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted(WORKFLOWS.glob("*.yml"))}


def test_all_workflows_are_least_privilege():
    texts = _workflow_texts()
    assert texts, "no workflows found"
    for name, text in texts.items():
        header = text.split("jobs:", 1)[0]
        assert "permissions:" in header, name
        assert "contents: read" in header, name
        assert "contents: write" not in header, name
    publish = texts["build-desktop.yml"].split("  publish:", 1)[1]
    assert "contents: write" in publish  # only this job may write releases


def test_actions_are_pinned_to_full_commit_shas():
    for name, text in _workflow_texts().items():
        for m in re.finditer(r"uses:\s*([^\s@]+)@([^\s#]+)", text):
            assert re.fullmatch(r"[0-9a-f]{40}", m.group(2)), (name, m.group(0))


def test_build_dependencies_are_hash_pinned():
    texts = _workflow_texts()
    build = texts["build-desktop.yml"]
    assert "npm ci --no-audit --no-fund" in build
    assert 'npm_config_offline: "true"' in build
    assert "pip install --require-hashes -r requirements.lock.txt" in build
    assert "electron-builder mismatch" in build
    scan = texts["secret-scan.yml"]
    assert "GITLEAKS_SHA256" in scan and "sha256sum -c -" in scan
    assert "--redact" in scan


def test_ci_never_echoes_secret_values():
    for name, text in _workflow_texts().items():
        for line in text.splitlines():
            if "echo" in line.lower():
                assert "secrets." not in line, (name, line)
                assert not re.search(r'echo\s+"?\$\w*(CERT|PASS|KEY|TOKEN)', line), (name, line)
    readiness = _workflow_texts()["signing-readiness.yml"]
    assert "CONFIGURED" in readiness and "MISSING" in readiness


def test_native_runners_required_per_platform():
    build = _workflow_texts()["build-desktop.yml"]
    for runner in ("windows-latest", "macos-latest", "ubuntu-latest"):
        assert f"runs-on: {runner}" in build
    assert "--publish never" in build
