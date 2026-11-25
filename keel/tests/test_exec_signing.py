"""Execution recheck: negative tests for signing / supply-chain gaps.

All keys are generated in-test with ``cryptography``. No real credential is
read, generated for production, or printed. Workflow and gitleaks invariants
are derived from the files on disk (never hardcoded), so a regression to a
mutable ref or a broad allowlist fails this collected suite.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from keel.release import common
from keel.release.signing import (
    TRUSTED_KEYS_ENV,
    KeyRing,
    SigningMode,
    distribution_readiness_errors,
    generate_keypair,
    load_private_key,
    load_public_key,
    register_platform_verifier,
    sign_bytes,
    sign_manifest,
    sign_release_manifest,
    unregister_platform_verifier,
    verify_release_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
GITLEAKS = ROOT / ".gitleaks.toml"
VERSION = common.validate_version()

IDENTITY_VARS = (
    "KEEL_WINDOWS_SIGNING_IDENTITY",
    "KEEL_MACOS_SIGNING_IDENTITY",
    "KEEL_MACOS_NOTARY_PROFILE",
    TRUSTED_KEYS_ENV,
)

_USES_RE = re.compile(r"uses:\s*(\S+)")
_SHA40_RE = re.compile(r"[0-9a-f]{40}\Z")


# ---------------------------------------------------------------------------
# Helpers (all key material is synthetic and lives only in tmp_path)
# ---------------------------------------------------------------------------


def _ephemeral(tmp_path: Path, label: str):
    private_path = tmp_path / "keys" / f"{label}.pem"
    public_path = tmp_path / "keys" / f"{label}.pub.pem"
    generate_keypair(private_path, public_path)
    return load_private_key(private_path), public_path


def _stage_v2(tmp_path: Path, private: Ed25519PrivateKey, *,
              key_id: str = "release-2026-01") -> Path:
    """Stage a complete bundle signed with a bound v2 envelope."""
    stage = tmp_path / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name in common.expected_filenames(VERSION):
        path = stage / name
        path.write_bytes(f"installer:{name}".encode("utf-8"))
        artifacts[name] = path
    doc = common.build_release_manifest(
        artifacts, VERSION, f"v{VERSION}", "https://example.invalid/download")
    doc = sign_release_manifest(doc, private, key_id=key_id, mode=SigningMode.TEST)
    for name, path in artifacts.items():
        (stage / f"{name}.sig").write_bytes(sign_bytes(path.read_bytes(), private))
    (stage / "RELEASE-MANIFEST.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return stage


def _set_identity(monkeypatch) -> None:
    for name in IDENTITY_VARS:
        monkeypatch.setenv(name, "configured-name")


def _register_passing_verifiers() -> None:
    register_platform_verifier("windows", lambda root: (True, "synthetic"))
    register_platform_verifier("macos", lambda root: (True, "synthetic"))


def _unregister_verifiers() -> None:
    unregister_platform_verifier("windows")
    unregister_platform_verifier("macos")


def _action_refs():
    refs = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = _USES_RE.search(line)
            if match:
                refs.append((workflow.name, lineno, match.group(1)))
    return refs


def _gitleaks_blocks():
    config = tomllib.loads(GITLEAKS.read_text(encoding="utf-8"))
    assert "allowlist" not in config  # no broad global allowlist
    return config["allowlists"]


# ---------------------------------------------------------------------------
# Gap 1: the full-SHA action-pin invariant was only checked in a `verify_*.py`
# utility that pytest does not collect. Derive and check it here.
# ---------------------------------------------------------------------------


def test_remote_actions_are_full_sha_pinned_from_files():
    refs = _action_refs()
    remote = [(name, line, ref) for name, line, ref in refs
              if "@" in ref and not ref.startswith("./")]
    assert remote, "no remote action refs found"
    for name, line, ref in remote:
        sha = ref.rsplit("@", 1)[1]
        assert _SHA40_RE.fullmatch(sha), (name, line, ref)
    # A local reusable-workflow call is not an action pin and must not carry
    # a mutable @ref; it is a repo-relative path.
    local = [(name, line, ref) for name, line, ref in refs
             if ref.startswith("./")]
    assert local, "expected a local reusable-workflow call"
    for name, line, ref in local:
        assert "@" not in ref, (name, line, ref)


def test_action_pin_predicate_rejects_mutable_and_short_refs():
    assert _SHA40_RE.fullmatch("a" * 40)
    for bad_ref in (
        "actions/checkout@main",
        "actions/checkout@v7",
        "actions/checkout@" + "a" * 39,
        "actions/checkout@" + "g" * 40,
    ):
        sha = bad_ref.rsplit("@", 1)[1]
        assert _SHA40_RE.fullmatch(sha) is None, bad_ref


# ---------------------------------------------------------------------------
# Gap 2: the existing gitleaks test checks commit *length* but not hex-ness,
# and never asserts path anchoring. Add exactness negatives.
# ---------------------------------------------------------------------------


def test_gitleaks_commits_are_full_lowercase_hex():
    commits = [commit for block in _gitleaks_blocks()
               for commit in block["commits"]]
    assert commits
    for commit in commits:
        assert re.fullmatch(r"[0-9a-f]{40}", commit), commit
    # Negative controls: a 40-character but non-hex / short value is not a
    # full commit SHA and must never qualify as an exact allowlist scope.
    assert re.fullmatch(r"[0-9a-f]{40}", "g" * 40) is None
    assert re.fullmatch(r"[0-9a-f]{40}", "a" * 39) is None


def test_gitleaks_paths_are_anchored_and_per_rule():
    blocks = _gitleaks_blocks()
    paths = [path for block in blocks for path in block["paths"]]
    assert paths
    for block in blocks:
        assert block["condition"] == "AND"
        assert len(block["targetRules"]) == 1
        assert block["targetRules"][0].strip()
    for path in paths:
        assert path.startswith("^") or path.startswith("(?:^|/)"), path
        assert path.rstrip().endswith("$"), path
    # Negative control: an unanchored path regex would silently cover a
    # different file that merely ends with the reviewed name.
    unanchored = r"keel/site/app\.js"
    assert re.search(unanchored, "unrelated/keel/site/app.js/extra")
    anchored = r"(?:^|/)keel/site/app\.js$"
    assert re.search(anchored, "keel/site/app.js")
    assert re.search(anchored, "unrelated/keel/site/app.js")
    assert not re.search(anchored, "unrelated/keel/site/app.js/extra")


# ---------------------------------------------------------------------------
# Gap 3: distribution fail-closed was tested for missing identity and for a
# failing verifier, but not for "identity configured + verifier says True"
# combined with an invalid/absent signature. No trusted claim may result.
# ---------------------------------------------------------------------------


def test_distribution_claim_blocked_when_identity_and_verifier_pass_but_signature_tampered(
        tmp_path, monkeypatch):
    _set_identity(monkeypatch)
    private, public_path = _ephemeral(tmp_path, "release")
    stage = _stage_v2(tmp_path, private)

    # Break the signed payload without re-signing.
    manifest = stage / "RELEASE-MANIFEST.json"
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["version"] = "0.0.0"
    manifest.write_text(json.dumps(doc), encoding="utf-8")

    _register_passing_verifiers()
    try:
        result = verify_release_bundle(
            stage, public_key=public_path, mode=SigningMode.DISTRIBUTION)
    finally:
        _unregister_verifiers()

    assert result.ok is False
    assert result.status == "failed"
    assert result.trusted_distribution is False
    assert distribution_readiness_errors(
        env={name: "configured-name" for name in IDENTITY_VARS}) == []


def test_distribution_claim_blocked_without_public_key_even_with_identity_and_verifier(
        tmp_path, monkeypatch):
    _set_identity(monkeypatch)
    private, _ = _ephemeral(tmp_path, "release")
    stage = _stage_v2(tmp_path, private)

    _register_passing_verifiers()
    try:
        result = verify_release_bundle(
            stage, public_key=None, mode=SigningMode.DISTRIBUTION)
    finally:
        _unregister_verifiers()

    assert result.ok is False
    assert result.status == "failed"
    assert result.trusted_distribution is False
    assert any("--public-key" in error for error in result.errors)


def test_partial_distribution_identity_is_pending(tmp_path):
    subset = {name: "configured-name" for name in IDENTITY_VARS[:-1]}
    errors = distribution_readiness_errors(env=subset)
    assert errors
    assert all("trusted distribution pending" in error for error in errors)
    assert any(TRUSTED_KEYS_ENV in error for error in errors)


def test_no_workflow_claims_distribution_mode_or_registers_verifiers():
    # Trusted identity is pending: no CI job may opt into distribution mode or
    # self-register a platform verifier before owner credentials exist.
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        assert workflow.name
        text = workflow.read_text(encoding="utf-8")
        assert "KEEL_SIGNING_MODE" not in text, workflow.name
        assert "register_platform_verifier" not in text, workflow.name


def test_every_workflow_declares_least_privilege_permissions():
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        header = workflow.read_text(encoding="utf-8").split("jobs:", 1)[0]
        assert "permissions:" in header, workflow.name
        assert "contents: write" not in header, workflow.name


# ---------------------------------------------------------------------------
# Gap 4: key-ring negatives not covered by the existing rotation tests.
# ---------------------------------------------------------------------------


def test_empty_keyring_never_verifies(tmp_path):
    private, public_path = _ephemeral(tmp_path, "release")
    doc = sign_release_manifest({"version": VERSION}, private, key_id="k1")
    assert KeyRing().verify(doc).ok is False
    assert KeyRing.from_refs([public_path], key_ids=["k1"]).verify(doc).ok is True


def test_v1_manifest_with_injected_key_id_cannot_be_promoted_by_keyring(tmp_path):
    private, public_path = _ephemeral(tmp_path, "legacy")
    # The legacy envelope does not bind signature_key_id, so it can be added
    # after signing. That must not let a foreign trusted key verify it.
    injected = dict(sign_manifest({"version": VERSION}, private),
                    signature_key_id="rotated-out")
    ring = KeyRing.from_refs([public_path], key_ids=["current-key"])
    result = ring.verify(injected)
    assert result.ok is False
    assert any("rotated out" in error for error in result.errors)

    other_private, other_public = _ephemeral(tmp_path, "other")
    assert other_private is not None
    foreign = KeyRing.from_refs([other_public], key_ids=["rotated-out"])
    assert foreign.verify(injected).ok is False
