"""Ed25519 signing and verification for Keel release artifacts.

Production keys are owner-controlled and never generated here. This module
only operates on keys supplied by the caller; tests use ephemeral keypairs.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class SignatureError(ValueError):
    pass


class SigningGateError(SignatureError):
    """Raised when a release cannot be proven signed and must not proceed.

    This is intentionally not swallowed by the CLI's generic error handler in
    a way that could be mistaken for success: every gate failure results in a
    non-zero exit status and an explicit ``RELEASE SIGNING GATE FAILED`` line.
    """


REQUIRE_SIGNED_ENV = "KEEL_REQUIRE_SIGNED"
MANIFEST_FILENAME = "RELEASE-MANIFEST.json"
_TRUTHY = {"1", "true", "yes", "on"}


def generate_keypair(private_path: Path, public_path: Path) -> None:
    """Generate an ephemeral/development keypair. Never use for production."""
    private = Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(private_bytes)
    public_path.write_bytes(public_bytes)
    try:
        private_path.chmod(0o600)
    except OSError:
        pass


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(
        path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SignatureError("private key is not Ed25519")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise SignatureError("public key is not Ed25519")
    return key


def sign_bytes(data: bytes, private_key: Ed25519PrivateKey) -> bytes:
    return private_key.sign(data)


def verify_bytes(data: bytes, signature: bytes,
                 public_key: Ed25519PublicKey) -> bool:
    try:
        public_key.verify(signature, data)
        return True
    except Exception:
        return False


def canonical_json(doc: dict) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sign_manifest(doc: dict, private_key: Ed25519PrivateKey) -> dict:
    """Return a copy of *doc* with an embedded detached signature."""
    signed = dict(doc)
    signed["signature"] = sign_bytes(
        canonical_json(doc), private_key).hex()
    signed["signature_algorithm"] = "ed25519"
    return signed


def verify_manifest(doc: dict, public_key: Ed25519PublicKey) -> bool:
    signature_hex = doc.get("signature")
    if not isinstance(signature_hex, str):
        return False
    if doc.get("signature_algorithm") != "ed25519":
        return False
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    payload = {k: v for k, v in doc.items()
               if k not in ("signature", "signature_algorithm")}
    return verify_bytes(canonical_json(payload), signature, public_key)


def require_signed_enabled(flag: bool = False) -> bool:
    """True when the hard signing gate was requested by flag or environment."""
    if flag:
        return True
    return os.environ.get(REQUIRE_SIGNED_ENV, "").strip().lower() in _TRUTHY


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_signed_release(
    root: Path,
    public_key_path: str | Path | None,
    *,
    manifest_name: str = MANIFEST_FILENAME,
) -> list[str]:
    """Return why the staged release in *root* is not verifiably signed.

    An empty result means both the release manifest and every artifact it
    lists carry valid Ed25519 signatures made by the supplied public key, and
    that the artifact bytes still match the signed manifest's SHA-256 values.
    No signing key material is ever created or returned here.

    This function never raises for a missing/invalid key or manifest: those
    conditions are reported as readable gate errors instead.
    """
    if not public_key_path:
        return [
            "signing verification requires --public-key "
            "(owner-supplied Ed25519 public key PEM)"
        ]
    key_path = Path(public_key_path)
    if not key_path.is_file():
        return [f"public key file not found: {key_path}"]
    try:
        public_key = load_public_key(key_path)
    except Exception as exc:  # noqa: BLE001 - surfaced as a gate error below
        return [f"could not load public key {key_path}: {exc}"]

    root = Path(root)
    manifest_path = root / manifest_name
    if not manifest_path.is_file():
        return [f"missing {manifest_name} in {root}: release cannot be proven signed"]
    try:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"could not read {manifest_name}: {exc}"]
    if not isinstance(doc, dict):
        return [f"{manifest_name} is not a JSON object"]

    errors: list[str] = []
    if not verify_manifest(doc, public_key):
        errors.append(
            f"{manifest_name} is missing a valid Ed25519 signature "
            "(sign the release with an owner-controlled --signing-key)"
        )

    files = doc.get("files")
    if not isinstance(files, list) or not files:
        errors.append(f"{manifest_name} has no files list to verify")
        return errors
    for entry in files:
        if not isinstance(entry, dict):
            errors.append("manifest file entry is not an object")
            continue
        name = entry.get("file")
        if not isinstance(name, str) or not name:
            errors.append("manifest file entry has no file name")
            continue
        artifact = root / name
        signature = root / f"{name}.sig"
        if not artifact.is_file():
            errors.append(f"{name}: artifact missing from {root}")
            continue
        if not signature.is_file():
            errors.append(f"{name}: signature file {name}.sig is missing")
            continue
        if not verify_bytes(artifact.read_bytes(), signature.read_bytes(),
                            public_key):
            errors.append(f"{name}: Ed25519 artifact signature is invalid")
        expected_sha = str(entry.get("sha256") or "").strip().lower()
        if expected_sha and _sha256_file(artifact) != expected_sha:
            errors.append(f"{name}: artifact SHA-256 does not match signed manifest")
    return errors
