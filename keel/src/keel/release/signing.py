"""Ed25519 signing and verification for Keel release artifacts.

Production keys are owner-controlled and never generated here. This module
only operates on keys supplied by the caller; tests use ephemeral keypairs.
"""

from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class SignatureError(ValueError):
    pass


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
