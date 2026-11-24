"""Local secret encryption for Keel configuration (v5 §8, §11).

Provider keys are encrypted with AES-256-GCM before being written to
settings.json. The master key comes from the OS keyring when available; a
passphrase (KEEL_MASTER_PASSPHRASE) or a local 0600 key file is the fallback
for systems without a keyring. No secret is ever logged or included in an
error message.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENC_MARKER = "aes256gcm-v1"
NONCE_BYTES = 12
MASTER_KEY_SERVICE = "keel"
MASTER_KEY_NAME = "master-key"


class SecretStoreError(RuntimeError):
    pass


def _local_key_path(state_dir: Path) -> Path:
    return state_dir / "master.key"


def create_private_file(path: Path, data: str, *, encoding: str = "ascii") -> None:
    """Create *path* with owner-only permissions in a single atomic step.

    ``Path.write_text`` creates the file with the process umask (commonly 0644)
    and only applies ``chmod`` afterwards, leaving a window in which the key is
    readable by other local accounts. O_CREAT|O_EXCL with mode 0600 removes
    that window. An already-existing file (created by an older version with a
    permissive mode) is tightened before being replaced.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags, 0o600)
    except FileExistsError:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # best effort on platforms without POSIX modes
        path.write_text(data, encoding=encoding)
        return
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(data)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _master_key(state_dir: Path) -> bytes:
    """Resolve the 32-byte master key, preferring the OS keyring."""
    try:
        import keyring  # type: ignore
    except ImportError:
        keyring = None

    if keyring is not None:
        try:
            raw = keyring.get_password(MASTER_KEY_SERVICE, MASTER_KEY_NAME)
            if raw:
                key = base64.urlsafe_b64decode(raw.encode("ascii"))
                if len(key) == 32:
                    return key
            key = os.urandom(32)
            keyring.set_password(
                MASTER_KEY_SERVICE, MASTER_KEY_NAME,
                base64.urlsafe_b64encode(key).decode("ascii"))
            return key
        except Exception:
            pass  # keyring unavailable or locked: use the documented fallback

    passphrase = os.environ.get("KEEL_MASTER_PASSPHRASE", "")
    if passphrase:
        return hashlib.sha256(passphrase.encode("utf-8")).digest()

    path = _local_key_path(state_dir)
    try:
        if path.is_file():
            key = base64.urlsafe_b64decode(
                path.read_text(encoding="ascii").strip().encode("ascii"))
            if len(key) == 32:
                return key
    except (OSError, ValueError):
        pass

    key = os.urandom(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    create_private_file(path, base64.urlsafe_b64encode(key).decode("ascii"))
    return key


def _aead(state_dir: Path) -> AESGCM:
    return AESGCM(_master_key(state_dir))


def encrypt_secret(secret: str, *, state_dir: Path) -> str:
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = _aead(state_dir).encrypt(
        nonce, secret.encode("utf-8"), None)
    return base64.urlsafe_b64encode(
        nonce + ciphertext).decode("ascii")


def decrypt_secret(payload: str, *, state_dir: Path) -> str:
    """Decrypt a stored secret. Legacy plaintext values pass through."""
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        if len(raw) <= NONCE_BYTES:
            return payload
        plaintext = _aead(state_dir).decrypt(
            raw[:NONCE_BYTES], raw[NONCE_BYTES:], None)
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise SecretStoreError(
            f"stored secret could not be decrypted ({type(exc).__name__})"
        ) from None
