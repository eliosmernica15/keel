"""Provider-agnostic signing and verification for Keel release artifacts.

Security model
--------------

* Keys are *never* generated for production here. ``generate_keypair`` exists
  only for throwaway development/test material.
* Key material is loaded from PEM files only. The public API accepts paths or
  ``SecretRef`` objects that name an environment variable, config entry or CI
  secret. Raw key values (PEM bytes on a command line or in an environment
  variable) are refused and are never printed in diagnostics.
* Three explicit modes exist:

  ``dev``
      Local development. No signature is required and unsigned artifacts are
      reported honestly as unsigned; no verification is implied.
  ``test``
      Ephemeral/synthetic Ed25519 keys. Signature mechanics can be verified,
      but a test key is never presented as a trusted distribution identity.
  ``distribution``
      Owner-controlled platform code signing (Authenticode on Windows,
      Developer ID + notarization on macOS). Fails closed unless trusted
      platform verifiers have been registered by the owner's CI and the
      owner's identity/secret names are configured.

Every verification path fails closed: missing, invalid, expired, mismatched or
unsigned material produces errors, never a silent success.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

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


class DistributionPendingError(SigningGateError):
    """Raised when trusted distribution cannot be proven in the current run."""


REQUIRE_SIGNED_ENV = "KEEL_REQUIRE_SIGNED"
MANIFEST_FILENAME = "RELEASE-MANIFEST.json"
CHECKSUMS_FILENAME = "RELEASE-SHA256SUMS.txt"
_TRUTHY = {"1", "true", "yes", "on"}

# Names of environment variables / config keys / CI secret names. Only names
# are read here; their values must be PEM *file paths*, never key material.
MODE_ENV = "KEEL_SIGNING_MODE"
PRIVATE_KEY_FILE_ENV = "KEEL_SIGNING_KEY_FILE"
PUBLIC_KEY_FILE_ENV = "KEEL_SIGNING_PUBLIC_KEY_FILE"
TRUSTED_KEYS_ENV = "KEEL_SIGNING_TRUSTED_KEYS"
PRIVATE_KEY_SECRET_NAME_ENV = "KEEL_SIGNING_PRIVATE_KEY_SECRET"
KEY_ID_ENV = "KEEL_SIGNING_KEY_ID"
WINDOWS_IDENTITY_ENV = "KEEL_WINDOWS_SIGNING_IDENTITY"
MACOS_IDENTITY_ENV = "KEEL_MACOS_SIGNING_IDENTITY"
NOTARY_PROFILE_ENV = "KEEL_MACOS_NOTARY_PROFILE"
PLATFORM_EVIDENCE_ENV = "KEEL_PLATFORM_SIGNING_EVIDENCE"

# All fields that participate in a manifest signature envelope. They are
# excluded from the canonical payload before verification.
SIGNATURE_FIELDS = frozenset({
    "signature",
    "signature_algorithm",
    "signature_key_id",
    "signature_mode",
    "signature_signed_at",
    "signature_expires_at",
})


class SigningMode(str, Enum):
    DEV = "dev"
    TEST = "test"
    DISTRIBUTION = "distribution"

    @classmethod
    def parse(cls, value: "str | SigningMode | None") -> "SigningMode":
        if value is None:
            return cls.DEV
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower()
        try:
            return cls(text)
        except ValueError as exc:
            raise SignatureError(
                f"unknown signing mode {value!r}; expected dev, test or distribution"
            ) from exc


def resolve_mode(
    explicit: "str | SigningMode | None" = None,
    *,
    default: "str | SigningMode" = SigningMode.DEV,
    env: Mapping[str, str] | None = None,
) -> SigningMode:
    """Resolve the signing mode from an explicit value, env, then *default*."""
    if explicit:
        return SigningMode.parse(explicit)
    environ = os.environ if env is None else env
    configured = str(environ.get(MODE_ENV, "")).strip()
    if configured:
        return SigningMode.parse(configured)
    return SigningMode.parse(default)


def _reject_key_material(value: str, label: str) -> None:
    """Refuse PEM bytes wherever a key *name* is expected."""
    if _looks_like_key_material(value):
        raise SignatureError(
            f"{label}: key values are never accepted; pass the name of an "
            "environment variable, config entry or CI secret whose value is a "
            "PEM file path"
        )


def _looks_like_key_material(value: str) -> bool:
    return (
        "-----BEGIN" in value
        or "\n" in value
        or "\r" in value
        or "PRIVATE KEY" in value.upper()
    )


@dataclass(frozen=True)
class SecretRef:
    """A reference to key material by *name* only.

    ``source`` is one of ``env``, ``config`` or ``ci``. Resolution returns a
    path to a PEM file; the secret value itself is never echoed.
    """

    name: str
    source: str = "env"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise SignatureError("secret name must be a non-empty string")
        if self.source not in {"env", "config", "ci"}:
            raise SignatureError("secret source must be env, config or ci")
        _reject_key_material(self.name, "secret name")
        object.__setattr__(self, "name", self.name.strip())

    def resolve(
        self,
        config: Mapping[str, str] | None = None,
        *,
        env: Mapping[str, str] | None = None,
    ) -> Path:
        environ = os.environ if env is None else env
        settings = config or {}
        if self.source == "env":
            value = environ.get(self.name)
        elif self.source == "config":
            value = settings.get(self.name)
        else:
            # A CI secret must be materialized as a file by the runner. The
            # name maps to a path via config or <SECRET_NAME>_FILE.
            value = settings.get(self.name) or environ.get(f"{self.name}_FILE")
            if not value:
                raise SignatureError(
                    f"CI secret {self.name} must be materialized as a PEM file "
                    f"path via config or {self.name}_FILE; never pass the "
                    "secret value"
                )
        if value is None or not str(value).strip():
            raise SignatureError(f"no value configured for {self.source} secret {self.name}")
        text = str(value).strip()
        _reject_key_material(text, f"{self.source} secret {self.name}")
        return Path(text)


def resolve_key_path(
    value: "str | Path | SecretRef | None",
    *,
    config: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    """Resolve a caller-supplied key name to a PEM file path.

    Strings may be plain paths or prefixed with ``env:``, ``config:`` or
    ``ci:`` to name a source. A bare PEM value is always refused.
    """
    if value is None:
        return None
    if isinstance(value, SecretRef):
        return value.resolve(config, env=env)
    if isinstance(value, Path):
        _reject_key_material(str(value), "key path")
        return value
    text = str(value).strip()
    _reject_key_material(text, "key path")
    for prefix, source in (("env:", "env"), ("config:", "config"), ("ci:", "ci")):
        if text.startswith(prefix):
            name = text[len(prefix):]
            return SecretRef(name, source).resolve(config, env=env)
    return Path(text)


# ---------------------------------------------------------------------------
# Backward-compatible primitives (used by build.py, verify.py, updater.py).
# ---------------------------------------------------------------------------


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


def load_private_key(
    path: "str | Path | SecretRef",
    *,
    config: Mapping[str, str] | None = None,
) -> Ed25519PrivateKey:
    key_path = resolve_key_path(path, config=config)
    if key_path is None or not key_path.is_file():
        raise SignatureError(f"private key file not found: {key_path}")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SignatureError("private key is not Ed25519")
    return key


def load_public_key(
    path: "str | Path | SecretRef",
    *,
    config: Mapping[str, str] | None = None,
) -> Ed25519PublicKey:
    key_path = resolve_key_path(path, config=config)
    if key_path is None or not key_path.is_file():
        raise SignatureError(f"public key file not found: {key_path}")
    key = serialization.load_pem_public_key(key_path.read_bytes())
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


def _parse_timestamp(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expiry_errors(doc: dict, now: datetime | None = None) -> list[str]:
    """Check signed envelope timestamps; fail closed on malformed values."""
    moment = now or _now()
    errors: list[str] = []
    for field in ("signature_signed_at", "signature_expires_at"):
        raw = doc.get(field)
        if raw is None:
            continue
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"{field}: invalid timestamp in signature envelope")
            continue
        try:
            parsed = _parse_timestamp(raw)
        except (ValueError, TypeError):
            errors.append(f"{field}: invalid timestamp in signature envelope")
            continue
        if field == "signature_expires_at" and parsed <= moment:
            errors.append("signature expired: signature envelope is no longer valid")
        if field == "signature_signed_at" and parsed > moment + timedelta(minutes=5):
            errors.append("signature timestamp is in the future")
    return errors


def sign_release_manifest(
    doc: dict,
    private_key: Ed25519PrivateKey,
    *,
    key_id: str | None = None,
    mode: "str | SigningMode" = SigningMode.TEST,
    lifetime_seconds: int | None = None,
    now: datetime | None = None,
) -> dict:
    """Sign *doc* with a bound, auditable Ed25519 envelope.

    The envelope binds the key id, mode and validity window into the signed
    payload, so rotation/expiry metadata cannot be swapped without breaking
    the signature.
    """
    signing_mode = SigningMode.parse(mode)
    moment = now or _now()
    payload = {k: v for k, v in doc.items() if k not in SIGNATURE_FIELDS}
    signed = dict(payload)
    signed["signature_envelope"] = "v2"
    signed["signature_algorithm"] = "ed25519"
    signed["signature_mode"] = signing_mode.value
    if key_id:
        if not isinstance(key_id, str) or not key_id.strip():
            raise SignatureError("key_id must be a non-empty string")
        signed["signature_key_id"] = key_id.strip()
    signed["signature_signed_at"] = moment.isoformat().replace("+00:00", "Z")
    if lifetime_seconds is not None:
        if not isinstance(lifetime_seconds, int):
            raise SignatureError("lifetime_seconds must be an integer")
        expires = moment + timedelta(seconds=lifetime_seconds)
        signed["signature_expires_at"] = expires.isoformat().replace("+00:00", "Z")
    signed["signature"] = sign_bytes(canonical_json(signed), private_key).hex()
    return signed


@dataclass(frozen=True)
class VerificationResult:
    """Fail-closed result of a unified verification pass."""

    ok: bool
    status: str
    errors: tuple[str, ...] = ()
    key_id: str | None = None
    mode: SigningMode = SigningMode.DEV

    @property
    def trusted_distribution(self) -> bool:
        return self.status == "distribution-verified"


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    public_key: Ed25519PublicKey


class KeyRing:
    """Trusted public keys, enabling gradual key rotation.

    If a manifest declares ``signature_key_id``, only the matching key is
    eligible. Legacy manifests without a key id are tried against every
    trusted key.
    """

    def __init__(self, keys: Iterable[TrustedKey] = ()) -> None:
        self._keys = tuple(keys)
        ids = [key.key_id for key in self._keys]
        if len(ids) != len(set(ids)):
            raise SignatureError("duplicate signing key ids in trusted key ring")

    @classmethod
    def from_refs(
        cls,
        refs: Iterable["str | Path | SecretRef"],
        *,
        config: Mapping[str, str] | None = None,
        key_ids: Iterable[str] | None = None,
    ) -> "KeyRing":
        keys: list[TrustedKey] = []
        ids = list(key_ids) if key_ids is not None else []
        for index, ref in enumerate(refs):
            path = resolve_key_path(ref, config=config)
            if path is None:
                raise SignatureError("empty trusted key reference")
            key = load_public_key(path, config=config)
            if index < len(ids):
                key_id = str(ids[index])
            else:
                key_id = path.stem
            keys.append(TrustedKey(key_id=key_id, public_key=key))
        return cls(keys)

    @classmethod
    def from_env(cls, *, env: Mapping[str, str] | None = None) -> "KeyRing":
        environ = os.environ if env is None else env
        raw = str(environ.get(TRUSTED_KEYS_ENV, "")).strip()
        refs = [item.strip() for item in raw.split(",") if item.strip()]
        if not refs:
            single = str(environ.get(PUBLIC_KEY_FILE_ENV, "")).strip()
            if single:
                refs = [single]
        ids_raw = str(environ.get(KEY_ID_ENV, "")).strip()
        key_ids = [item.strip() for item in ids_raw.split(",") if item.strip()] or None
        return cls.from_refs(refs, key_ids=key_ids)

    @property
    def key_ids(self) -> tuple[str, ...]:
        return tuple(key.key_id for key in self._keys)

    def verify(
        self,
        doc: dict,
        *,
        now: datetime | None = None,
    ) -> "VerificationResult":
        return verify_manifest_detailed(doc, keyring=self, now=now)

    def verify_detached(self, data: bytes, signature: bytes) -> bool:
        """Verify a raw detached signature against every trusted key."""
        return any(
            verify_bytes(data, signature, key.public_key) for key in self._keys
        )


def _signature_payload(doc: dict) -> dict:
    """Canonical payload covered by the signature.

    v2 envelopes bind all metadata (key id, mode, timestamps, algorithm) and
    strip only the signature value. Legacy ``sign_manifest`` envelopes add
    ``signature_algorithm`` after signing, so that field is excluded there.
    Removing the envelope marker from a v2 manifest cannot help an attacker:
    the signature then covers a different payload and verification fails.
    """
    if doc.get("signature_envelope") == "v2":
        return {k: v for k, v in doc.items() if k != "signature"}
    return {k: v for k, v in doc.items() if k not in SIGNATURE_FIELDS}


def verify_manifest_detailed(
    doc: dict,
    *,
    public_key: Ed25519PublicKey | None = None,
    keyring: KeyRing | None = None,
    now: datetime | None = None,
) -> VerificationResult:
    """Verify a signed manifest envelope and return readable failure reasons."""
    if not isinstance(doc, dict):
        return VerificationResult(False, "failed", ("manifest is not a JSON object",))

    errors = _expiry_errors(doc, now)
    signature_hex = doc.get("signature")
    if not isinstance(signature_hex, str) or not signature_hex.strip():
        errors.append("manifest is unsigned: no Ed25519 signature field")
    elif doc.get("signature_algorithm") != "ed25519":
        errors.append("manifest signature algorithm is not ed25519")
    else:
        try:
            signature = bytes.fromhex(signature_hex)
        except ValueError:
            errors.append("manifest signature is not valid hexadecimal")
            signature = None
        if signature is not None:
            if keyring is not None:
                declared = doc.get("signature_key_id")
                if declared is not None and not isinstance(declared, str):
                    errors.append("manifest signature_key_id is invalid")
                    candidates: tuple[TrustedKey, ...] = ()
                elif declared is not None:
                    candidates = tuple(
                        key for key in keyring._keys if key.key_id == declared
                    )
                    if not candidates:
                        errors.append(
                            f"no trusted key for signature_key_id {declared!r} "
                            "(key may have been rotated out)"
                        )
                else:
                    candidates = keyring._keys
            elif public_key is not None:
                candidates = (TrustedKey(key_id="default", public_key=public_key),)
            else:
                candidates = ()
                errors.append("verification requires an owner-supplied public key")
            payload = canonical_json(_signature_payload(doc))
            matched = next(
                (key for key in candidates
                 if verify_bytes(payload, signature, key.public_key)),
                None,
            )
            if matched is None and not any(
                "signature" in error or "key" in error for error in errors
            ):
                errors.append("manifest Ed25519 signature does not match any trusted key")
            if matched is not None and not errors:
                return VerificationResult(
                    True, "test-verified", (), matched.key_id, SigningMode.TEST
                )
    return VerificationResult(False, "failed", tuple(errors), None, SigningMode.TEST)


def verify_manifest(
    doc: dict,
    public_key: Ed25519PublicKey,
    *,
    now: datetime | None = None,
) -> bool:
    """Backward-compatible boolean manifest signature verification."""
    return verify_manifest_detailed(doc, public_key=public_key, now=now).ok


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


def _safe_artifact_name(name: str) -> bool:
    """Reject path traversal and non-plain filenames from untrusted manifests."""
    if not name or not isinstance(name, str) or "\x00" in name:
        return False
    if name != Path(name).name:
        return False
    if ".." in Path(name).parts or name in {".", ".."}:
        return False
    return True


def _checksum_file_errors(root: Path, digests: dict[str, str]) -> list[str]:
    """Cross-check an optional SHA256SUMS file against the signed manifest."""
    path = root / CHECKSUMS_FILENAME
    if not path.is_file():
        return []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"{CHECKSUMS_FILENAME}: could not read checksum file: {exc}"]
    for line in lines:
        text = line.strip()
        if not text:
            continue
        parts = text.split()
        if len(parts) != 2:
            errors.append(f"{CHECKSUMS_FILENAME}: malformed checksum line")
            continue
        digest, name = parts[0].strip().lower(), parts[1]
        if not _safe_artifact_name(name):
            errors.append(f"{CHECKSUMS_FILENAME}: unsafe artifact name {name!r}")
            continue
        artifact = root / name
        if not artifact.is_file():
            errors.append(f"{CHECKSUMS_FILENAME}: {name}: artifact missing")
            continue
        if digest != digests.get(name) or digest != _sha256_file(artifact):
            errors.append(f"{name}: checksum file SHA-256 does not match signed manifest")
    return errors


def verify_signed_release(
    root: Path,
    public_key_path: "str | Path | SecretRef | None",
    *,
    manifest_name: str = MANIFEST_FILENAME,
    now: datetime | None = None,
    keyring: KeyRing | None = None,
) -> list[str]:
    """Return why the staged release in *root* is not verifiably signed.

    An empty result means the release manifest and every artifact it lists
    carry valid Ed25519 signatures made by supplied trusted key(s), the
    artifact bytes still match the signed manifest's SHA-256 values, and any
    checksum file agrees. No signing key material is ever created or returned
    here. Missing/invalid keys and manifests are reported as gate errors.
    """
    if not public_key_path and keyring is None:
        return [
            "signing verification requires --public-key "
            "(owner-supplied Ed25519 public key PEM)"
        ]

    public_key: Ed25519PublicKey | None = None
    if keyring is None:
        key_path = resolve_key_path(public_key_path)
        if key_path is None or not key_path.is_file():
            return [f"public key file not found: {key_path}"]
        try:
            public_key = load_public_key(key_path)
        except Exception as exc:  # surfaced as a gate error below
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
    result = verify_manifest_detailed(
        doc, public_key=public_key, keyring=keyring, now=now)
    if not result.ok:
        errors.append(
            f"{manifest_name} is missing a valid Ed25519 signature "
            "(sign the release with an owner-controlled --signing-key)"
        )
        for error in result.errors:
            if "expired" in error or "future" in error or "key" in error.lower():
                errors.append(error)

    files = doc.get("files")
    if not isinstance(files, list) or not files:
        errors.append(f"{manifest_name} has no files list to verify")
        return errors
    digests: dict[str, str] = {}
    for entry in files:
        if not isinstance(entry, dict):
            errors.append("manifest file entry is not an object")
            continue
        name = entry.get("file")
        if not _safe_artifact_name(str(name)):
            errors.append(f"manifest file entry has unsafe file name: {name!r}")
            continue
        artifact = root / name
        signature = root / f"{name}.sig"
        if not artifact.is_file() or artifact.is_symlink():
            errors.append(f"{name}: artifact missing from {root}")
            continue
        if not signature.is_file() or signature.is_symlink():
            errors.append(f"{name}: signature file {name}.sig is missing")
            continue
        if public_key is not None and not verify_bytes(
            artifact.read_bytes(), signature.read_bytes(), public_key):
            errors.append(f"{name}: Ed25519 artifact signature is invalid")
        elif keyring is not None and not keyring.verify_detached(
            artifact.read_bytes(), signature.read_bytes()):
            # A detached artifact signature has no envelope metadata; try the
            # whole ring without a key-id constraint.
            errors.append(f"{name}: Ed25519 artifact signature is invalid")
        expected_sha = str(entry.get("sha256") or "").strip().lower()
        if len(expected_sha) != 64 or any(
            char not in "0123456789abcdef" for char in expected_sha):
            errors.append(f"{name}: manifest has no valid SHA-256 checksum")
            continue
        digests[name] = expected_sha
        if _sha256_file(artifact) != expected_sha:
            errors.append(f"{name}: artifact SHA-256 does not match signed manifest")
    errors.extend(_checksum_file_errors(root, digests))
    return errors


# ---------------------------------------------------------------------------
# Distribution trust: owner-provided platform verifiers, never self-asserted.
# ---------------------------------------------------------------------------

_PLATFORM_VERIFIERS: dict[
    str, Callable[[Path], tuple[bool, str]]
] = {}


def register_platform_verifier(
    platform: str, verifier: Callable[[Path], tuple[bool, str]]
) -> None:
    """Register an owner/CI-supplied verifier for native platform signatures.

    For Windows this should invoke ``signtool verify /pa``; for macOS
    ``codesign --verify --strict`` plus notarization staple validation. No
    verifier is bundled here, so distribution mode fails closed by default.
    """
    if platform not in {"windows", "macos"}:
        raise SignatureError(f"unsupported platform for signature verification: {platform}")
    if not callable(verifier):
        raise SignatureError("platform verifier must be callable")
    _PLATFORM_VERIFIERS[platform] = verifier


def unregister_platform_verifier(platform: str) -> None:
    _PLATFORM_VERIFIERS.pop(platform, None)


def distribution_readiness_errors(
    config: Mapping[str, str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Report missing owner-controlled identity/secret configuration."""
    environ = os.environ if env is None else env
    settings = config or {}
    required = (
        (WINDOWS_IDENTITY_ENV,
         "Windows Authenticode signing identity (EV/OV certificate)"),
        (MACOS_IDENTITY_ENV,
         "macOS Developer ID Application signing identity"),
        (NOTARY_PROFILE_ENV,
         "macOS notarytool credential profile for notarization"),
        (TRUSTED_KEYS_ENV,
         "owner-controlled trusted Ed25519 public key path(s), including "
         "previous keys for rotation"),
    )
    missing: list[str] = []
    for name, description in required:
        if not settings.get(name) and not str(environ.get(name, "")).strip():
            missing.append(f"trusted distribution pending: missing {name} ({description})")
    return missing


def verify_platform_signatures(
    root: Path,
    *,
    platforms: Iterable[str] = ("windows", "macos"),
) -> list[str]:
    """Ask registered owner/CI verifiers about native platform signatures."""
    errors: list[str] = []
    for platform in platforms:
        verifier = _PLATFORM_VERIFIERS.get(platform)
        if verifier is None:
            errors.append(
                f"{platform}: no trusted platform signature verifier registered; "
                "trusted distribution pending"
            )
            continue
        try:
            ok, detail = verifier(Path(root))
        except Exception as exc:  # fail closed on verifier errors
            errors.append(f"{platform}: platform verifier failed ({type(exc).__name__})")
            continue
        if ok is not True:
            errors.append(f"{platform}: platform signature not verified: {detail}")
    return errors


def verify_release_bundle(
    root: "str | Path",
    *,
    public_key: "str | Path | SecretRef | None" = None,
    keyring: KeyRing | None = None,
    mode: "str | SigningMode | None" = None,
    config: Mapping[str, str] | None = None,
    now: datetime | None = None,
    manifest_name: str = MANIFEST_FILENAME,
) -> VerificationResult:
    """Unified, mode-aware verification of a staged release bundle."""
    signing_mode = resolve_mode(mode)
    root = Path(root)

    if signing_mode is SigningMode.DEV and public_key is None and keyring is None:
        manifest_path = root / manifest_name
        has_manifest = manifest_path.is_file()
        has_signature = False
        if has_manifest:
            try:
                doc = json.loads(manifest_path.read_text(encoding="utf-8"))
                has_signature = isinstance(doc, dict) and bool(doc.get("signature"))
            except (OSError, ValueError):
                has_signature = False
        note = "dev mode: no signature verification performed"
        if has_signature:
            note += "; signature field present but NOT verified"
        return VerificationResult(
            True, "unsigned", (note,), None, signing_mode,
        )

    errors = verify_signed_release(
        root, public_key, keyring=keyring, now=now, manifest_name=manifest_name)
    key_id = None
    if not errors:
        try:
            doc = json.loads((root / manifest_name).read_text(encoding="utf-8"))
            key_id = doc.get("signature_key_id")
        except (OSError, ValueError):
            pass

    if signing_mode is SigningMode.DISTRIBUTION:
        errors.extend(distribution_readiness_errors(config))
        errors.extend(verify_platform_signatures(root))

    status = "failed"
    if not errors:
        status = {
            SigningMode.DEV: "dev-verified",
            SigningMode.TEST: "test-verified",
            SigningMode.DISTRIBUTION: "distribution-verified",
        }[signing_mode]
    return VerificationResult(
        not errors, status, tuple(errors), key_id, signing_mode)
