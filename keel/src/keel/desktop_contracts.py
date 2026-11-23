"""Pure desktop lifecycle, isolation and release/upload contracts (E5.x).

These are ``local_module`` descriptors and policies only: stdlib, no network,
no subprocess, no filesystem writes. The desktop shell and the release
pipeline import these shapes so the safety properties are expressed once and
can be checked adversarially in tests.

Feature map
-----------
E5.1  framed_transport_descriptor / frame codec / assert_no_listening_port
E5.4  single_instance_lock_descriptor / SingleInstanceGuard
E5.9  plugin_install_decision (install-time scripts rejected by default)
E5.12 target_build_layout / assert_target_confined / shared cache verification
E5.14 find_upload_secrets / strip_upload_credentials / build_completion_record
E5.15 authorize_upload / UploadPlan / channel_metadata_name / assert_no_deletes
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable, Mapping

__all__ = [
    "ContractError", "TransportError", "ProfileAccessError",
    "PluginScriptRejected", "TargetIsolationError", "CredentialLeakError",
    "StepIncompleteError", "UploadGuardError",
    "MAX_FRAME_BYTES", "framed_transport_descriptor", "assert_no_listening_port",
    "encode_frame", "decode_frames",
    "single_instance_lock_descriptor", "shared_product_data",
    "desktop_only_state", "plugin_environments", "SingleInstanceGuard",
    "INSTALL_TIME_HOOKS", "plugin_install_decision",
    "target_build_layout", "assert_target_confined", "shared_cache_entry",
    "verify_shared_cache",
    "UPLOAD_SECRET_ENV_NAMES", "UPLOAD_SECRET_SUFFIXES", "is_upload_secret_env",
    "find_upload_secrets", "assert_no_upload_secret", "strip_upload_credentials",
    "packaging_env", "Artifact", "CompletionRecord", "build_completion_record",
    "CHANNELS", "channel_metadata_name", "UploadPlan", "authorize_upload",
    "assert_no_deletes",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ContractError(Exception):
    """Base class for every violated desktop/release contract."""


class TransportError(ContractError):
    """E5.1 — framed transport or frame-size violation."""


class ProfileAccessError(ContractError):
    """E5.4 — profile access without (or outside) the single-instance lock."""


class PluginScriptRejected(ContractError):
    """E5.9 — an install-time lifecycle script was not reviewed/allowlisted."""


class TargetIsolationError(ContractError):
    """E5.12 — a target tried to use another target's mutable state."""


class CredentialLeakError(ContractError):
    """E5.14 — an upload credential would reach a packaging subprocess."""


class StepIncompleteError(ContractError):
    """E5.14 — a completion record was requested before build/sign success."""


class UploadGuardError(ContractError):
    """E5.15 — upload preconditions were not satisfied."""


# ---------------------------------------------------------------------------
# E5.1 — framed-byte transport, no listening port (decision C-19)
# ---------------------------------------------------------------------------

MAX_FRAME_BYTES = 16 * 1024 * 1024  # backpressure: cap a single buffered frame


def framed_transport_descriptor() -> dict:
    """Describe the desktop backend transport.

    The Python backend is a bundled child process. Requests and streaming
    responses travel over length-prefixed byte frames on stdio pipes; Node IPC
    carries lifecycle control only; client assets come from a custom ``app://``
    protocol. There is deliberately no TCP listener — loopback + token stays
    in ``keel web`` / CLI only (decision C-19).
    """
    return {
        "backend": "bundled_child",
        "transport": "framed_byte_pipe",
        "framing": "4-byte big-endian length prefix + payload",
        "requests": "framed_byte_pipe",
        "streaming_responses": "framed_byte_pipe",
        "backpressure": True,
        "ipc": "lifecycle_control_only",
        "assets": "app://",
        "listening_port": None,
        "loopback_tcp": False,
        "decision": "C-19",
        "note": "keel web/CLI keep loopback + token; desktop exposes no port",
    }


def assert_no_listening_port(descriptor: Mapping[str, object]) -> None:
    """Fail closed if a desktop descriptor reintroduces any TCP exposure."""
    if descriptor.get("listening_port") is not None:
        raise TransportError(
            "desktop backend must not open a listening port; "
            f"got {descriptor['listening_port']!r}")
    if descriptor.get("loopback_tcp"):
        raise TransportError(
            "desktop backend must not use loopback TCP; use framed byte pipes")


def encode_frame(payload: bytes) -> bytes:
    """Encode one length-prefixed frame (pure bytes, no I/O)."""
    data = bytes(payload)
    if len(data) > MAX_FRAME_BYTES:
        raise TransportError(f"frame too large: {len(data)} > {MAX_FRAME_BYTES}")
    return len(data).to_bytes(4, "big") + data


def decode_frames(buffer: bytes) -> tuple[list[bytes], bytes]:
    """Decode complete frames; return ``(frames, unconsumed_tail)``.

    A partial frame is buffered rather than dispatched, which is what gives
    the pipe its backpressure semantics.
    """
    data = bytes(buffer)
    frames: list[bytes] = []
    while len(data) >= 4:
        size = int.from_bytes(data[:4], "big")
        if size > MAX_FRAME_BYTES:
            raise TransportError(f"frame too large: {size} > {MAX_FRAME_BYTES}")
        if len(data) < 4 + size:
            break
        frames.append(data[4:4 + size])
        data = data[4 + size:]
    return frames, data


# ---------------------------------------------------------------------------
# E5.4 — process-lifetime single-instance lock + two plugin environments
# ---------------------------------------------------------------------------

def shared_product_data() -> frozenset[str]:
    """Data CLI and desktop share (never executable/plugin state)."""
    return frozenset({"sessions", "settings", "credentials", "workspaces"})


def desktop_only_state() -> frozenset[str]:
    """State the desktop app owns exclusively."""
    return frozenset({"executable_packages", "plugin_activation",
                      "lockfiles", "site-packages"})


def plugin_environments() -> tuple[str, ...]:
    """Desktop and CLI run separate plugin environments."""
    return ("desktop", "cli")


def single_instance_lock_descriptor() -> dict:
    """Describe the lock acquired before any profile access."""
    return {
        "scope": "process_lifetime",
        "acquire_before": "profile_access",
        "profile_owner": "desktop_only",
        "shared_product_data": tuple(sorted(shared_product_data())),
        "desktop_only_state": tuple(sorted(desktop_only_state())),
        "plugin_environments": plugin_environments(),
        "note": ("single-instance lock + two plugin environments; "
                 "shared data excludes packages, activation, lockfiles, "
                 "site-packages"),
    }


class SingleInstanceGuard:
    """In-memory model of the desktop's process-lifetime profile lock."""

    def __init__(self) -> None:
        self._profile: str | None = None

    def acquire(self, profile: str) -> dict:
        if not profile:
            raise ProfileAccessError("a profile name is required for the lock")
        if self._profile is not None:
            raise ProfileAccessError(
                "single-instance lock already held by "
                f"{self._profile!r}; desktop profile is exclusive")
        self._profile = profile
        return {"profile": profile, "process_lifetime": True,
                "acquired_before": "profile_access"}

    def access_profile(self, profile: str) -> dict:
        if self._profile is None:
            raise ProfileAccessError(
                "profile access requires the single-instance lock first")
        if profile != self._profile:
            raise ProfileAccessError(
                f"lock does not own profile {profile!r} "
                f"(owns {self._profile!r})")
        return {"profile": profile, "owner": "desktop"}

    def release(self) -> None:
        self._profile = None

    def __enter__(self) -> "SingleInstanceGuard":
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


# ---------------------------------------------------------------------------
# E5.9 — install-time lifecycle scripts rejected unless allowlisted
# ---------------------------------------------------------------------------

INSTALL_TIME_HOOKS = frozenset({
    "setup.py", "build", "pre_install", "install", "post_install",
    "pre_build", "post_build", "develop", "egg_info",
})


def plugin_install_decision(
    name: str,
    version: str,
    *,
    distribution_type: str = "wheel",
    lifecycle_scripts=(),
    allowlist: Mapping[tuple[str, str], object] | object = frozenset(),
) -> dict:
    """Decide whether a plugin may be installed.

    Reject by default: any install-time lifecycle script, or any non-wheel
    distribution (an sdist builds via ``setup.py``), is refused unless the
    exact ``(name, version)`` pair appears in the reviewed allowlist.
    """
    scripts = tuple(lifecycle_scripts or ())
    if not name or not version:
        # An unidentified plugin can never match a reviewed (name, version)
        # pair, so fail closed with a rejection decision rather than an install.
        return {"allowed": False, "reason": "invalid_plugin_identity",
                "plugin": name, "version": version}
    allowed_pairs = set(allowlist)  # works for sets, frozensets and mappings
    reviewed = (name, version) in allowed_pairs
    if reviewed:
        return {"allowed": True, "reason": "reviewed_allowlist",
                "plugin": name, "version": version,
                "distribution": distribution_type}
    if scripts:
        return {"allowed": False, "reason": "unallowlisted_lifecycle_script",
                "plugin": name, "version": version,
                "scripts": scripts}
    if distribution_type.lower() != "wheel":
        return {"allowed": False, "reason": "non_wheel_distribution",
                "plugin": name, "version": version,
                "distribution": distribution_type}
    return {"allowed": True, "reason": "wheel_without_scripts",
            "plugin": name, "version": version, "distribution": "wheel"}


# ---------------------------------------------------------------------------
# E5.12 — per-target build isolation, shared cache verified by name + hash
# ---------------------------------------------------------------------------

_TARGET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _validate_target(target: str) -> str:
    if not isinstance(target, str) or not _TARGET_NAME_RE.fullmatch(target):
        raise TargetIsolationError(f"invalid target name: {target!r}")
    return target


def _normalize_posix_parts(path: str) -> tuple[str, ...]:
    if not isinstance(path, str) or "\\" in path:
        raise TargetIsolationError(f"invalid target path: {path!r}")
    pure = PurePosixPath(path)
    if pure.is_absolute():
        raise TargetIsolationError(f"absolute target path rejected: {path!r}")
    parts: list[str] = []
    for part in pure.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise TargetIsolationError(f"path escapes target root: {path!r}")
            parts.pop()
        else:
            parts.append(part)
    return tuple(parts)


def target_build_layout(target: str) -> dict[str, str]:
    """Return the private directory layout ``targets/<target>/...``."""
    _validate_target(target)
    root = f"targets/{target}"
    return {
        "root": root,
        "inputs": f"{root}/inputs",
        "runtime": f"{root}/runtime",
        "seed": f"{root}/seed",
        "artifacts": f"{root}/artifacts",
    }


def assert_target_confined(target: str, path: str) -> None:
    """Reject any path outside ``targets/<target>/`` (no cross-target state)."""
    _validate_target(target)
    parts = _normalize_posix_parts(path)
    root = ("targets", target)
    # The target's own root is owned by the target; the shared parent
    # ("targets") and any other target's tree are not.
    if len(parts) < len(root) or parts[:len(root)] != root:
        raise TargetIsolationError(
            f"path {path!r} is not confined to target {target!r}")


def shared_cache_entry(name: str, digest: str) -> dict:
    """Describe a shared download-cache entry, keyed by name + SHA-256."""
    if (not isinstance(name, str) or not _TARGET_NAME_RE.fullmatch(name)
            or name in (".", "..")):
        raise TargetIsolationError(f"invalid cache entry name: {name!r}")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise TargetIsolationError(f"cache digest must be a SHA-256 hex string: {digest!r}")
    normalized = digest.lower()
    return {"name": name, "sha256": normalized, "key": f"{name}-{normalized}"}


def verify_shared_cache(entry: Mapping[str, str], *,
                        expected_name: str, expected_digest: str) -> bool:
    """A target may only consume a cache entry with the exact name and hash."""
    return (entry.get("name") == expected_name
            and str(entry.get("sha256", "")).lower() == expected_digest.lower())


# ---------------------------------------------------------------------------
# E5.14 — no upload credentials in packaging; completion record written last
# ---------------------------------------------------------------------------

UPLOAD_SECRET_ENV_NAMES = frozenset({
    "AWS_ACCESS_KEY_ID", "KEEL_RELEASE_TOKEN", "KEEL_UPLOAD_TOKEN",
    "KEEL_UPLOAD_SECRET", "GH_TOKEN", "GITHUB_TOKEN",
})

UPLOAD_SECRET_SUFFIXES = (
    "_TOKEN", "TOKEN", "_SECRET", "SECRET", "_PASSWORD", "PASSWORD",
    "_API_KEY", "API_KEY", "_ACCESS_KEY", "ACCESS_KEY",
    "_PRIVATE_KEY", "PRIVATE_KEY", "_CREDENTIALS", "CREDENTIALS",
)


def is_upload_secret_env(name: str) -> bool:
    upper = name.upper()
    return (upper in UPLOAD_SECRET_ENV_NAMES
            or any(upper.endswith(suffix) for suffix in UPLOAD_SECRET_SUFFIXES))


def find_upload_secrets(env: Mapping[str, object]) -> list[str]:
    """Return sorted names of any upload credential present in an env map."""
    return sorted(name for name in env if is_upload_secret_env(name))


def assert_no_upload_secret(env: Mapping[str, object]) -> None:
    leaked = find_upload_secrets(env)
    if leaked:
        raise CredentialLeakError(
            "upload credentials must never reach packaging; found: "
            + ", ".join(leaked))


def strip_upload_credentials(env: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of ``env`` with every upload credential removed."""
    return {key: value for key, value in env.items()
            if not is_upload_secret_env(key)}


def packaging_env(env: Mapping[str, object]) -> dict[str, object]:
    """The environment handed to packaging: stripped and proven clean."""
    clean = strip_upload_credentials(env)
    assert_no_upload_secret(clean)
    return clean


@dataclass(frozen=True)
class Artifact:
    name: str
    size: int
    sha512: str


@dataclass(frozen=True)
class CompletionRecord:
    environment: str
    target: str
    public_url: str
    version: str
    channel: str
    artifacts: tuple[Artifact, ...]
    complete: bool = True


def build_completion_record(
    *,
    target: str,
    environment: str,
    public_url: str,
    version: str,
    channel: str,
    artifacts,
    steps,
) -> CompletionRecord:
    """Write (describe) a target completion record only after full success.

    Every build/sign step must report ``ok=True``; a single failed or missing
    step fails closed, so no completion record can mark a partial build done.
    """
    step_list = list(steps)
    if not step_list:
        raise StepIncompleteError(
            "no steps recorded for build/sign; completion record not written")
    for step in step_list:
        if not step.get("ok"):
            raise StepIncompleteError(
                f"step {step.get('name', '<unnamed>')!r} did not succeed; "
                "completion record not written")
    return CompletionRecord(
        environment=environment, target=target, public_url=public_url,
        version=version, channel=channel, artifacts=tuple(artifacts),
        complete=True)


# ---------------------------------------------------------------------------
# E5.15 — upload guard: validate everything before credentials are read
# ---------------------------------------------------------------------------

CHANNELS = frozenset({"stable", "prerelease"})


def channel_metadata_name(channel: str) -> str:
    """Stable and prerelease channels use distinct channel metadata files."""
    if channel not in CHANNELS:
        raise UploadGuardError(
            f"unsupported release channel: {channel!r}; "
            "expected stable or prerelease")
    return f"{channel}.json"


@dataclass(frozen=True)
class UploadPlan:
    operations: tuple[dict, ...]
    channel: str
    channel_metadata_name: str
    retains_history: bool = True
    credentials_read: bool = True


def authorize_upload(
    record: CompletionRecord,
    *,
    environment: str,
    target: str,
    public_url: str,
    version: str,
    observed_artifacts: Mapping[str, tuple[int, str]],
    credential_reader: Callable[[], object],
) -> UploadPlan:
    """Validate the completion record and artifacts before reading credentials.

    The record must match the requested environment, target, public URL and
    version exactly; every artifact's name, size and SHA-512 must match what is
    on disk. Only then is ``credential_reader`` invoked. The returned plan
    uploads immutable versioned artifacts first and channel metadata last with
    ``no-cache``; it never deletes historical objects.
    """
    if not getattr(record, "complete", False):
        raise UploadGuardError("incomplete completion record cannot authorize upload")

    channel = record.channel
    if channel not in CHANNELS:
        raise UploadGuardError(
            f"unsupported channel in completion record: {channel!r}")

    for field, expected in (
        ("environment", environment),
        ("target", target),
        ("public_url", public_url),
        ("version", version),
    ):
        actual = getattr(record, field)
        if actual != expected:
            raise UploadGuardError(
                f"completion record {field} mismatch: "
                f"{actual!r} != {expected!r}")

    observed = dict(observed_artifacts)
    expected_names = {artifact.name for artifact in record.artifacts}
    if set(observed) != expected_names:
        raise UploadGuardError(
            "artifact name mismatch: "
            f"expected {sorted(expected_names)}, saw {sorted(observed)}")
    for artifact in record.artifacts:
        actual_size, actual_sha512 = observed[artifact.name]
        if actual_size != artifact.size:
            raise UploadGuardError(
                f"artifact size mismatch for {artifact.name}: "
                f"{actual_size} != {artifact.size}")
        if (len(artifact.sha512) != 128
                or not re.fullmatch(r"[0-9a-fA-F]{128}", artifact.sha512)):
            raise UploadGuardError(
                f"invalid artifact sha512 for {artifact.name}")
        if actual_sha512.lower() != artifact.sha512.lower():
            raise UploadGuardError(
                f"artifact sha512 mismatch for {artifact.name}")

    operations: list[dict] = []
    for artifact in sorted(record.artifacts, key=lambda a: a.name):
        operations.append({
            "kind": "put_artifact", "name": artifact.name,
            "size": artifact.size, "sha512": artifact.sha512.lower(),
            "version": record.version, "cache_control": "immutable",
        })
    metadata_name = channel_metadata_name(channel)
    operations.append({
        "kind": "put_channel_metadata", "name": metadata_name,
        "version": record.version, "cache_control": "no-cache",
    })

    plan = UploadPlan(
        operations=tuple(operations), channel=channel,
        channel_metadata_name=metadata_name, retains_history=True,
        credentials_read=True)
    assert_no_deletes(plan)

    # All checks passed; only now is the credential read permitted.
    credential_reader()
    return plan


def assert_no_deletes(plan: UploadPlan) -> None:
    """Historical objects are retained for rollback; no delete operations."""
    if not plan.retains_history:
        raise UploadGuardError("upload plan does not retain historical objects")
    for operation in plan.operations:
        if operation.get("kind") in ("delete", "remove", "delete_object"):
            raise UploadGuardError("upload plan must never delete historical objects")
