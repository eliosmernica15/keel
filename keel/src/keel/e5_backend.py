"""Backend contracts for the remaining desktop packaging/lifecycle features (E5.x).

This is the stdlib-only backend half of the desktop shell, release and updater
features. Like :mod:`keel.desktop_contracts` it expresses safety properties as
pure descriptors and policies that the shell, release pipeline and updater can
import and that tests can check adversarially. There is no network, no
subprocess, no filesystem write and no real credential anywhere in this module.

Feature map (the 13 ``not_started`` E5.x rows — all ``implementation_tier:
local_module``; the six P0 rows already live in ``desktop_contracts.py``):

E5.2   release_identity / assert_release_identity
E5.3   bundled_runtime_descriptor / assert_bundled_runtime
E5.5   activation_descriptor / ActivationJournal / execute_activation /
       recover_activation / TransactionLock / is_transaction_stale
E5.6   seed_manifest / assert_seed_manifest / offline_install_gate
E5.7   update_unit_descriptor / assert_update_unit / update_schedule /
       UpdateCheckCoordinator / update_install_plan
E5.8   plugin_manager_surface / authorize_plugin_operation
E5.10  locale_payload / assert_locale_payload / i18n_gate_scope
E5.11  dev_home_descriptor / dev_debug_ports / devtools_descriptor /
       effective_dev_config
E5.13  validate_app_id / validate_release_prerequisites
E5.16  update_environment / assert_distinct_update_origins
E5.17  signing_plan / assert_signing_steps_complete / redact_diagnostics /
       assert_signing_pin_not_persisted
E5.18  linux_release_targets / assert_linux_release_targets
E5.19  known_limitations_section / assert_known_limitations_complete
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Mapping
from urllib.parse import urlsplit

__all__ = [
    # errors
    "E5BackendError", "ReleaseIdentityError", "RuntimeIsolationError",
    "ActivationError", "SeedPackagingError", "UpdateUnitError",
    "PluginSurfaceError", "LocaleError", "DevIsolationError",
    "PrerequisiteError", "UpdateEnvironmentError", "SigningError",
    "LinuxTargetError", "LimitationsError",
    # E5.2
    "VERSION_RE", "INDEPENDENT_VERSION_FIELDS", "release_identity",
    "assert_release_identity",
    # E5.3
    "bundled_runtime_descriptor", "assert_bundled_runtime",
    # E5.5
    "ACTIVATION_STEPS", "activation_descriptor", "ActivationJournal",
    "plan_activation", "execute_activation", "recover_activation",
    "TransactionLock", "assert_transaction_owner", "is_transaction_stale",
    # E5.6
    "SEED_SHARD_COUNT", "SEED_COMPRESSION", "seed_shard_for", "seed_manifest",
    "assert_seed_manifest", "verify_seed_shard", "offline_install_gate",
    "first_run_extraction_descriptor",
    # E5.7
    "UPDATE_COMPONENTS", "update_unit_descriptor", "assert_update_unit",
    "update_schedule", "UpdateCheckCoordinator", "update_install_plan",
    # E5.8
    "PLUGIN_MANAGER_OPERATIONS", "FORBIDDEN_PLUGIN_CAPABILITIES",
    "plugin_manager_surface", "authorize_plugin_operation",
    # E5.10
    "SHELL_LOCALE_SURFACES", "DEFAULT_LOCALE", "locale_payload",
    "assert_locale_payload", "i18n_gate_scope",
    # E5.11
    "DEV_HOME_SCOPES", "dev_home_descriptor", "dev_debug_ports",
    "devtools_descriptor", "effective_dev_config",
    # E5.13
    "APP_ID_RE", "RELEASE_CREDENTIAL_NAMES", "validate_app_id",
    "validate_release_prerequisites",
    # E5.16
    "UPDATE_ENVIRONMENTS", "update_environment",
    "assert_distinct_update_origins",
    # E5.17
    "SIGNING_STEPS", "EXPECTED_SIGNING_AUTHORITIES", "signing_plan",
    "assert_signing_steps_complete", "redact_diagnostics",
    "assert_signing_pin_not_persisted",
    # E5.18
    "LINUX_RELEASE_FORMATS", "linux_release_targets",
    "assert_linux_release_targets",
    # E5.19
    "KNOWN_LIMITATION_TOPICS", "known_limitations_section",
    "assert_known_limitations_complete",
]


# ---------------------------------------------------------------------------
# Errors — one typed failure family, one subclass per feature
# ---------------------------------------------------------------------------

class E5BackendError(Exception):
    """Base class for every violated E5 backend contract."""


class ReleaseIdentityError(E5BackendError):
    """E5.2 — shell/backend version identity violation."""


class RuntimeIsolationError(E5BackendError):
    """E5.3 — a system/shell runtime or package-manager state was selected."""


class ActivationError(E5BackendError):
    """E5.5 — a profile swap, recovery or lock precondition was violated."""


class SeedPackagingError(E5BackendError):
    """E5.6 — the offline seed manifest is incomplete or non-deterministic."""


class UpdateUnitError(E5BackendError):
    """E5.7 — an update unit or install flow failed verification."""


class PluginSurfaceError(E5BackendError):
    """E5.8 — a plugin-manager request escaped the structured operation set."""


class LocaleError(E5BackendError):
    """E5.10 — shell copy is missing, non-shared or has no fallback."""


class DevIsolationError(E5BackendError):
    """E5.11 — a dev override would leak into the packaged app."""


class PrerequisiteError(E5BackendError):
    """E5.13 — a release prerequisite (identity or credentials) is invalid."""


class UpdateEnvironmentError(E5BackendError):
    """E5.16 — test and production update origins are not distinct."""


class SigningError(E5BackendError):
    """E5.17 — a signing/notarization step, authority or PIN rule failed."""


class LinuxTargetError(E5BackendError):
    """E5.18 — the Linux release formats are wrong or claimed as dsh-supported."""


class LimitationsError(E5BackendError):
    """E5.19 — the known-limitations section is missing required topics."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _sha256(value: str, error: type[E5BackendError], what: str) -> str:
    """Validate and normalize a SHA-256 hex digest, failing closed."""
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise error(f"{what} must be a SHA-256 hex string: {value!r}")
    return value.lower()


def _name(value: str, error: type[E5BackendError], what: str) -> str:
    """Validate a simple non-empty profile/owner/plugin name."""
    if (not isinstance(value, str) or not value or value != value.strip()
            or any(c in value for c in ("/", "\\", "\x00")) or ".." in value):
        raise error(f"invalid {what}: {value!r}")
    return value


# ---------------------------------------------------------------------------
# E5.2 — one exact release version for shell and backend
# ---------------------------------------------------------------------------

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z][0-9A-Za-z.-]*)?$")

# An independent version column is forbidden: a backend upgrade must be a
# desktop release, never a one-sided update.
INDEPENDENT_VERSION_FIELDS = (
    "backend_only_version", "shell_only_version", "daemon_version",
    "backend_version_override",
)


def release_identity(version: str) -> dict:
    """Describe a release where the shell and backend share one exact version.

    A backend upgrade is a desktop release; the updater never updates one side
    on its own.
    """
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ReleaseIdentityError(f"invalid release version: {version!r}")
    return {
        "version": version,
        "shell_version": version,
        "backend_version": version,
        "single_version": True,
        "upgrade_requires_desktop_release": True,
        "updates_one_side_only": False,
    }


def assert_release_identity(identity: Mapping[str, object]) -> None:
    """Fail closed on a split or independently-versioned shell/backend pair."""
    version = identity.get("version")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ReleaseIdentityError(f"invalid release version: {version!r}")
    for field in ("shell_version", "backend_version"):
        if identity.get(field) != version:
            raise ReleaseIdentityError(
                f"{field} {identity.get(field)!r} != release version {version!r}")
    if identity.get("single_version") is not True:
        raise ReleaseIdentityError("shell and backend must declare a single version")
    if identity.get("upgrade_requires_desktop_release") is not True:
        raise ReleaseIdentityError(
            "a backend upgrade must be released as a desktop release")
    if identity.get("updates_one_side_only"):
        raise ReleaseIdentityError("updater must never update one side alone")
    for field in INDEPENDENT_VERSION_FIELDS:
        if field in identity:
            raise ReleaseIdentityError(
                f"independent version field {field!r} is forbidden")


# ---------------------------------------------------------------------------
# E5.3 — bundled runtime, never system runtime or package-manager state
# ---------------------------------------------------------------------------

def bundled_runtime_descriptor() -> dict:
    """Describe the embedded Python used by the desktop backend.

    The backend never reads system Python site-packages and never runs on the
    shell's own runtime.
    """
    return {
        "python_source": "bundled_embedded",
        "backend_runtime": "bundled_python",
        "site_packages_source": "bundled_seed_only",
        "system_python_allowed": False,
        "package_manager_state_allowed": False,
        "reads_system_site_packages": False,
        "shell_runtime_for_backend": False,
        "note": ("Keel ships its own embedded Python; the backend runs on it "
                 "and never on the shell runtime or system site-packages"),
    }


def assert_bundled_runtime(descriptor: Mapping[str, object]) -> None:
    """Fail closed if system/shell runtime or package-manager state creeps in."""
    if descriptor.get("python_source") != "bundled_embedded":
        raise RuntimeIsolationError("Python must come from the embedded bundle")
    if descriptor.get("backend_runtime") != "bundled_python":
        raise RuntimeIsolationError("backend must run on the bundled Python")
    if descriptor.get("site_packages_source") != "bundled_seed_only":
        raise RuntimeIsolationError("site-packages must come from the bundled seed")
    for field in ("system_python_allowed", "package_manager_state_allowed",
                  "reads_system_site_packages", "shell_runtime_for_backend"):
        if descriptor.get(field):
            raise RuntimeIsolationError(
                f"forbidden runtime path enabled: {field}")


# ---------------------------------------------------------------------------
# E5.5 — transactional profile activation, journal, rollback and lock owner
# ---------------------------------------------------------------------------

ACTIVATION_STEPS = (
    "stage", "health_check", "swap_active", "journal", "retain_rollback",
)


def activation_descriptor() -> dict:
    """Describe the ordered, fail-closed activation policy."""
    return {
        "steps": list(ACTIVATION_STEPS),
        "staging_before_swap": True,
        "full_backend_health_check": True,
        "swap_only_after_success": True,
        "rollback_profiles": 1,
        "journal": True,
        "recovery": "journal_plus_actual_directories",
        "transaction_lock_owner_recorded": True,
        "orphaned_worker_not_stale": True,
    }


@dataclass(frozen=True)
class ActivationJournal:
    """Durable record of one activation transaction (pure value object)."""

    transaction_id: str
    staged_profile: str
    active_profile: str
    rollback_profile: str
    state: str = "staged"  # staged | committed | rolled_back


def plan_activation(transaction_id: str, staged_profile: str,
                    active_profile: str) -> ActivationJournal:
    """Open a journal entry: stage first, keep exactly one rollback profile."""
    _name(transaction_id, ActivationError, "transaction id")
    _name(staged_profile, ActivationError, "staged profile")
    _name(active_profile, ActivationError, "active profile")
    if staged_profile == active_profile:
        raise ActivationError("staged and active profiles must differ")
    return ActivationJournal(
        transaction_id=transaction_id,
        staged_profile=staged_profile,
        active_profile=active_profile,
        rollback_profile=f"{active_profile}--rollback",
        state="staged",
    )


def execute_activation(journal: ActivationJournal, *,
                       health_check: Callable[[str], bool]) -> ActivationJournal:
    """Boot the staged profile fully; swap only when the health check passes.

    A failed check rolls back (the active profile is left untouched). The
    health-check callable receives the *staged* profile name so a caller cannot
    accidentally probe the currently active one.
    """
    if journal.state != "staged":
        raise ActivationError(
            f"activation {journal.transaction_id!r} is already {journal.state!r}")
    healthy = health_check(journal.staged_profile)
    if healthy is not True:
        return replace(journal, state="rolled_back")
    return replace(journal, state="committed")


def recover_activation(journal: ActivationJournal, *,
                       present_profiles: Iterable[str]) -> dict:
    """Combine the journal with directories that actually exist on disk.

    The journal is a hint, not the source of truth: a commit is trusted only if
    the swapped-to profile is present, otherwise the single rollback profile is
    used. An incomplete staging is discarded.
    """
    present = set(present_profiles)
    if journal.state == "committed":
        if journal.active_profile in present:
            return {"action": "keep", "profile": journal.active_profile,
                    "reason": "committed_active_present"}
        if journal.rollback_profile in present:
            return {"action": "rollback", "profile": journal.rollback_profile,
                    "reason": "committed_active_missing"}
        raise ActivationError(
            "committed active profile and its rollback profile are both missing")
    if journal.active_profile not in present:
        raise ActivationError("active profile missing from the filesystem")
    if journal.state == "rolled_back":
        return {"action": "keep", "profile": journal.active_profile,
                "reason": "rolled_back_active_present"}
    return {"action": "discard_staged", "profile": journal.active_profile,
            "reason": "incomplete_staging"}


@dataclass(frozen=True)
class TransactionLock:
    """The owner recorded in a transaction lock (an orphaned worker still owns)."""

    owner: str
    pid: int | None = None
    heartbeat: int | None = None


def assert_transaction_owner(lock: TransactionLock, owner: str) -> None:
    """Only the recorded owner may act on a locked transaction."""
    if lock.owner != owner:
        raise ActivationError(
            f"transaction is owned by {lock.owner!r}, not {owner!r}")


def is_transaction_stale(lock: TransactionLock, *,
                         liveness_probe: Callable[[TransactionLock], bool]) -> bool:
    """Treat a worker that still answers a liveness probe as live.

    The lock records the worker itself as owner, so an orphaned worker (whose
    parent exited) is *not* automatically stale — only a worker that fails the
    liveness probe is.
    """
    return not liveness_probe(lock)


# ---------------------------------------------------------------------------
# E5.6 — deterministic, offline, 16-shard seed store
# ---------------------------------------------------------------------------

SEED_SHARD_COUNT = 16
SEED_COMPRESSION = "none"  # the outer installer compresses; shards stay raw


def seed_shard_for(name: str) -> int:
    """Return the stable shard index for a dependency name (0..15)."""
    if not isinstance(name, str) or not name:
        raise SeedPackagingError(f"invalid seed member name: {name!r}")
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big") % SEED_SHARD_COUNT


def seed_manifest(packages: Mapping[str, str]) -> dict:
    """Build a deterministic manifest of 16 uncompressed shards.

    ``packages`` maps a dependency name to the SHA-256 of its wheel/archive.
    Assignment is by name hash and members are sorted, so an unchanged input
    produces byte-identical shards for differential updates.
    """
    if not isinstance(packages, Mapping):
        raise SeedPackagingError("seed packages must be a mapping")
    shards: list[dict] = []
    for index in range(SEED_SHARD_COUNT):
        members: list[dict] = []
        for name in sorted(packages):
            if seed_shard_for(name) != index:
                continue
            digest = _sha256(packages[name], SeedPackagingError,
                             f"seed digest for {name!r}")
            members.append({"name": name, "sha256": digest})
        canonical = "|".join(
            f"{member['name']}={member['sha256']}" for member in members
        ).encode("utf-8")
        shards.append({
            "index": index,
            "compression": SEED_COMPRESSION,
            "members": members,
            "sha256": hashlib.sha256(canonical).hexdigest(),
        })
    return {
        "shard_count": SEED_SHARD_COUNT,
        "compression": SEED_COMPRESSION,
        "differential_updates": True,
        "shards": shards,
    }


def assert_seed_manifest(
    manifest: Mapping[str, object], *,
    expected_packages: Mapping[str, str] | None = None,
) -> None:
    """Re-derive the manifest from its members; reject drift or tampering.

    When ``expected_packages`` is supplied, the manifest must also cover that
    exact set, so a silently dropped member cannot pass verification.
    """
    if manifest.get("shard_count") != SEED_SHARD_COUNT:
        raise SeedPackagingError(
            f"seed archive must have {SEED_SHARD_COUNT} shards")
    if manifest.get("compression") != SEED_COMPRESSION:
        raise SeedPackagingError("seed shards must be uncompressed")
    shards = manifest.get("shards")
    if not isinstance(shards, list) or len(shards) != SEED_SHARD_COUNT:
        raise SeedPackagingError("seed manifest must contain 16 shards")
    packages: dict[str, str] = {}
    for expected_index, shard in enumerate(shards):
        if shard.get("index") != expected_index:
            raise SeedPackagingError("seed shards must be in index order")
        if shard.get("compression") != SEED_COMPRESSION:
            raise SeedPackagingError("each shard must be uncompressed")
        members = shard.get("members")
        if not isinstance(members, list):
            raise SeedPackagingError("shard members must be a list")
        names = [member.get("name") for member in members]
        if names != sorted(names):
            raise SeedPackagingError("shard members must be sorted by name")
        for member in members:
            name = member.get("name")
            digest = _sha256(member.get("sha256"), SeedPackagingError,
                             f"seed digest for {name!r}")
            if seed_shard_for(name) != expected_index:
                raise SeedPackagingError(
                    f"member {name!r} is in the wrong shard")
            if name in packages:
                raise SeedPackagingError(f"duplicate seed member {name!r}")
            packages[name] = digest
        canonical = "|".join(
            f"{m['name']}={m['sha256']}" for m in members
        ).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != shard.get("sha256"):
            raise SeedPackagingError(
                f"shard {expected_index} digest does not match its members")
    if seed_manifest(packages)["shards"] != shards:
        raise SeedPackagingError("seed manifest is not deterministic")
    if expected_packages is not None:
        expected = {
            name: _sha256(digest, SeedPackagingError, f"seed digest for {name!r}")
            for name, digest in expected_packages.items()
        }
        if packages != expected:
            raise SeedPackagingError("seed manifest does not cover the expected packages")


def verify_seed_shard(shard: Mapping[str, object], *, expected_digest: str) -> bool:
    """Compare a shard's digest against the shipped inventory value."""
    return str(shard.get("sha256", "")).lower() == expected_digest.lower()


def offline_install_gate(manifest: Mapping[str, object], *,
                         verified_offline: bool,
                         expected_packages: Mapping[str, str] | None = None) -> None:
    """A seed may not ship until it has passed an offline install."""
    assert_seed_manifest(manifest, expected_packages=expected_packages)
    if verified_offline is not True:
        raise SeedPackagingError(
            "offline install verification is required before shipping the seed")


def first_run_extraction_descriptor() -> dict:
    """Describe first-run extraction; disk use is measured separately."""
    return {
        "when": "first_run",
        "source": "bundled_seed_shards",
        "verify_each_shard": True,
        "disk_use_measured_separately_from_download_size": True,
        "compression": SEED_COMPRESSION,
    }


# ---------------------------------------------------------------------------
# E5.7 — one signed update unit, check schedule and install flow
# ---------------------------------------------------------------------------

UPDATE_COMPONENTS = ("shell", "backend_seed", "runtime")


def update_unit_descriptor(*, version: str, shell_digest: str,
                           seed_digest: str, runtime_digest: str,
                           signature: str) -> dict:
    """Describe one signed unit binding shell + matching seed + runtime."""
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise UpdateUnitError(f"invalid update unit version: {version!r}")
    if not isinstance(signature, str) or len(signature) < 16:
        raise UpdateUnitError("update unit must carry a signature")
    return {
        "version": version,
        "components": {
            "shell": _sha256(shell_digest, UpdateUnitError, "shell digest"),
            "backend_seed": _sha256(seed_digest, UpdateUnitError, "seed digest"),
            "runtime": _sha256(runtime_digest, UpdateUnitError, "runtime digest"),
        },
        "signature": signature,
        "signature_scheme": "ed25519",
        "signed": True,
        "single_unit": True,
        "verify_before_install": True,
    }


def assert_update_unit(unit: Mapping[str, object], *,
                       expected_version: str | None = None) -> None:
    """Fail closed on an incomplete, unsigned or mismatched update unit."""
    if unit.get("signed") is not True or unit.get("single_unit") is not True:
        raise UpdateUnitError("shell, seed and runtime must form one signed unit")
    if unit.get("verify_before_install") is not True:
        raise UpdateUnitError("update unit must be verified before install")
    version = unit.get("version")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise UpdateUnitError(f"invalid update unit version: {version!r}")
    if expected_version is not None and version != expected_version:
        raise UpdateUnitError(
            f"update unit version {version!r} != expected {expected_version!r}")
    if not str(unit.get("signature", "")):
        raise UpdateUnitError("update unit signature is missing")
    components = unit.get("components")
    if not isinstance(components, Mapping) or set(components) != set(UPDATE_COMPONENTS):
        raise UpdateUnitError("update unit must bind shell, backend_seed and runtime")
    for name in UPDATE_COMPONENTS:
        _sha256(components[name], UpdateUnitError, f"{name} digest")


def update_schedule() -> dict:
    """Describe the updater timing, UI and ordered install flow."""
    return {
        "startup_check_delay_seconds": 10,
        "manual_check_menu_item": "Check for updates…",
        "native_confirmation_dialog": True,
        "wait_for_in_flight_check": True,
        "flow": ["verify", "stop_backend", "install", "reconcile_next_launch"],
    }


class UpdateCheckCoordinator:
    """Coalesce check requests so a second request waits for an in-flight one."""

    def __init__(self) -> None:
        self._in_flight = False

    @property
    def in_flight(self) -> bool:
        return self._in_flight

    def request_check(self) -> dict:
        """Start a check, or report that the caller must wait for the active one."""
        if self._in_flight:
            return {"started": False, "waited": True, "reason": "check_in_flight"}
        self._in_flight = True
        return {"started": True, "waited": False}

    def finish(self) -> None:
        self._in_flight = False

    def __enter__(self) -> "UpdateCheckCoordinator":
        self.request_check()
        return self

    def __exit__(self, *exc: object) -> None:
        self.finish()


def update_install_plan(unit: Mapping[str, object], *,
                        expected_version: str,
                        verify_signature: Callable[[Mapping[str, object]], bool]) -> dict:
    """Validate the unit and its signature, then order the install operations.

    ``verify_signature`` is invoked only after all structural checks pass; the
    backend is stopped only after verification, and reconciliation is the last
    step for the next launch.
    """
    assert_update_unit(unit, expected_version=expected_version)
    if verify_signature(unit) is not True:
        raise UpdateUnitError("update unit signature verification failed")
    return {
        "version": unit["version"],
        "operations": [
            {"kind": "verify", "signature_scheme": "ed25519"},
            {"kind": "stop_backend"},
            {"kind": "install", "components": list(UPDATE_COMPONENTS)},
            {"kind": "reconcile_next_launch"},
        ],
    }


# ---------------------------------------------------------------------------
# E5.8 — narrow, structured plugin-manager renderer surface
# ---------------------------------------------------------------------------

PLUGIN_MANAGER_OPERATIONS = ("list", "install", "remove", "update")

FORBIDDEN_PLUGIN_CAPABILITIES = (
    "filesystem", "raw_ipc", "shell", "arbitrary_args",
    "path", "argv", "cmd", "command", "cwd", "env", "eval", "exec", "raw",
)

_PLUGIN_REQUEST_FIELDS = frozenset(
    {"operation", "kind", "plugin", "version", "source", "reason"}
)


def plugin_manager_surface() -> dict:
    """Describe the separate renderer's allow-listed operation surface."""
    return {
        "renderer": "separate",
        "operations": list(PLUGIN_MANAGER_OPERATIONS),
        "structured_only": True,
        "capabilities_denied": list(FORBIDDEN_PLUGIN_CAPABILITIES),
        "no_filesystem": True,
        "no_raw_ipc": True,
        "no_shell": True,
        "no_arbitrary_package_manager_args": True,
    }


def authorize_plugin_operation(operation: Mapping[str, object]) -> dict:
    """Accept only a structured list/install/remove/update request.

    Any capability field (filesystem, raw IPC, shell, arbitrary package-manager
    arguments) and any path/command-looking value is rejected.
    """
    kind = operation.get("operation", operation.get("kind"))
    if kind not in PLUGIN_MANAGER_OPERATIONS:
        raise PluginSurfaceError(f"unsupported plugin operation: {kind!r}")
    for key in operation:
        if key in FORBIDDEN_PLUGIN_CAPABILITIES or key not in _PLUGIN_REQUEST_FIELDS:
            raise PluginSurfaceError(f"plugin request field {key!r} is not allowed")
    for key, value in operation.items():
        if not isinstance(value, str) or not value or value != value.strip():
            raise PluginSurfaceError(f"plugin request {key!r} must be a non-empty string")
        if ("\x00" in value or ".." in value or "/" in value or "\\" in value
                or any(c in value for c in ";|`$&")):
            raise PluginSurfaceError(
                f"plugin request {key!r} contains a path or shell metacharacter")
    authorized = dict(operation)
    authorized.pop("kind", None)
    authorized["operation"] = kind  # canonicalize the alias
    authorized["authorized"] = True
    return authorized


# ---------------------------------------------------------------------------
# E5.10 — one localized shell copy payload with English fallback
# ---------------------------------------------------------------------------

SHELL_LOCALE_SURFACES = ("menus", "native_dialogs", "plugin_window")
DEFAULT_LOCALE = "en"


def locale_payload(locale: str, catalog: Mapping[str, Mapping[str, Mapping[str, str]]],
                   keys: Iterable[str]) -> dict:
    """Resolve one shared copy payload for all shell surfaces.

    ``catalog`` is ``locale -> surface -> key -> text``. Every key is resolved
    identically for menus, native dialogs and the plugin window; a missing or
    empty translation falls back to English, and a missing English string is
    reported rather than silently dropped.
    """
    if not isinstance(locale, str) or not locale:
        raise LocaleError(f"invalid locale: {locale!r}")
    if not isinstance(catalog, Mapping):
        raise LocaleError("locale catalog must be a mapping")
    wanted = tuple(keys)
    if not wanted or len(set(wanted)) != len(wanted):
        raise LocaleError("shell copy keys must be a non-empty unique set")
    english = catalog.get(DEFAULT_LOCALE, {})
    selected = catalog.get(locale, english) if locale != DEFAULT_LOCALE else english
    surfaces: dict[str, dict[str, str]] = {}
    missing: list[str] = []
    for surface in SHELL_LOCALE_SURFACES:
        en_table = english.get(surface, {})
        chosen_table = selected.get(surface, {})
        row: dict[str, str] = {}
        for key in wanted:
            text = chosen_table.get(key)
            if not text:
                text = en_table.get(key)
            if not text:
                missing.append(f"{surface}:{key}")
                continue
            row[key] = text
        surfaces[surface] = row
    return {
        "locale": locale,
        "fallback": DEFAULT_LOCALE,
        "shared": True,
        "surfaces": surfaces,
        "missing_keys": tuple(missing),
    }


def assert_locale_payload(payload: Mapping[str, object]) -> None:
    """Fail closed on a partial, non-shared or fallback-less shell payload."""
    if payload.get("fallback") != DEFAULT_LOCALE:
        raise LocaleError("shell copy must fall back to English")
    if payload.get("shared") is not True:
        raise LocaleError("all shell surfaces must share one locale payload")
    surfaces = payload.get("surfaces")
    if not isinstance(surfaces, Mapping) or set(surfaces) != set(SHELL_LOCALE_SURFACES):
        raise LocaleError("menus, native dialogs and plugin window need copy")
    key_sets = [set(table) for table in surfaces.values()]
    if any(keys != key_sets[0] for keys in key_sets[1:]):
        raise LocaleError("shell surfaces must resolve the same key set")
    if payload.get("missing_keys"):
        raise LocaleError("shell copy is missing: " + ", ".join(
            str(key) for key in payload["missing_keys"]))


def i18n_gate_scope() -> dict:
    """The i18n gate must also inspect desktop shell sources."""
    return {
        "checks_desktop_shell_sources": True,
        "localized_surfaces": list(SHELL_LOCALE_SURFACES),
        "fallback_locale": DEFAULT_LOCALE,
    }


# ---------------------------------------------------------------------------
# E5.11 — disposable dev home; dev overrides never reach packaged builds
# ---------------------------------------------------------------------------

DEV_HOME_SCOPES = ("data", "project", "browser_data")


def dev_home_descriptor(root: str) -> dict:
    """Describe a disposable development home with isolated sub-folders."""
    _name(root, DevIsolationError, "dev home root")
    return {
        "root": root,
        "scopes": {scope: f"{root}/{scope}" for scope in DEV_HOME_SCOPES},
        "disposable": True,
        "environment": "development",
    }


def dev_debug_ports(env: Mapping[str, str]) -> dict:
    """Read optional debug ports from the environment, validating each."""
    result: dict[str, int | None] = {}
    for field, env_name in (("backend", "KEEL_DEV_DEBUG_PORT"),
                            ("browser", "KEEL_DEV_BROWSER_DEBUG_PORT")):
        raw = env.get(env_name)
        if raw in (None, ""):
            result[f"{field}_debug_port"] = None
            continue
        try:
            port = int(str(raw))
        except (TypeError, ValueError) as exc:
            raise DevIsolationError(f"{env_name} must be an integer") from exc
        if not 1 <= port <= 65535:
            raise DevIsolationError(f"{env_name} out of range: {port}")
        result[f"{field}_debug_port"] = port
    return result


def devtools_descriptor(env: Mapping[str, str]) -> dict:
    """Read the DevTools auto-open toggle from the development environment."""
    raw = str(env.get("KEEL_DEVTOOLS_AUTO_OPEN", "")).lower()
    return {"auto_open": raw in ("1", "true", "yes", "on")}


def effective_dev_config(packaged: bool, overrides: Mapping[str, object]) -> dict:
    """Return dev overrides only for development builds.

    Packaged apps ignore them entirely: an environment override cannot turn a
    production build into a dev build.
    """
    if packaged:
        if any(value not in (None, "", False) for value in overrides.values()):
            # Recorded and discarded: never applied to the packaged app.
            return {"applied": {}, "ignored": True, "packaged": True}
        return {"applied": {}, "ignored": False, "packaged": True}
    return {"applied": dict(overrides), "ignored": False, "packaged": False}


# ---------------------------------------------------------------------------
# E5.13 — release prerequisite validation before any build
# ---------------------------------------------------------------------------

APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+$")

RELEASE_CREDENTIAL_NAMES = (
    "KEEL_RELEASE_TOKEN",
    "KEEL_UPLOAD_TOKEN",
    "MACOS_NOTARIZATION_PASSWORD",
    "WINDOWS_SIGNING_PIN",
    "AWS_SECRET_ACCESS_KEY",
)


def validate_app_id(app_id: str) -> str:
    """Validate a reverse-DNS application id, rejecting malformed identity."""
    if not isinstance(app_id, str) or not APP_ID_RE.fullmatch(app_id):
        raise PrerequisiteError(f"malformed application id: {app_id!r}")
    return app_id


def validate_release_prerequisites(
    env: Mapping[str, object], *, app_id: str,
    required_credentials: Iterable[str] = RELEASE_CREDENTIAL_NAMES,
) -> dict:
    """Validate every release input up front (``release --dry-run`` semantics).

    A malformed app id, a control character in an identity value, or any
    missing/blank credential is a hard failure — no build starts on a partial
    prerequisite set.
    """
    problems: list[str] = []
    try:
        validate_app_id(app_id)
    except PrerequisiteError as exc:
        problems.append(str(exc))
    for name, value in env.items():
        if isinstance(value, str) and any(ord(char) < 32 for char in value):
            problems.append(f"control character in release value {name!r}")
    required = tuple(required_credentials)
    missing = [name for name in required
               if not isinstance(env.get(name), str) or not str(env[name]).strip()]
    if missing:
        problems.append("incomplete credential set: " + ", ".join(missing))
    if problems:
        raise PrerequisiteError("; ".join(problems))
    return {
        "app_id": app_id,
        "credentials_present": tuple(sorted(required)),
        "ready": True,
    }


# ---------------------------------------------------------------------------
# E5.16 — distinct test and production update origins
# ---------------------------------------------------------------------------

UPDATE_ENVIRONMENTS = {
    "test": {
        "origin": "https://beta-updates.example.com/keel",
        "channel": "prerelease",
    },
    "production": {
        "origin": "https://updates.example.com/keel",
        "channel": "stable",
    },
}


def update_environment(name: str) -> dict:
    """Return a copy of a named update environment descriptor."""
    if name not in UPDATE_ENVIRONMENTS:
        raise UpdateEnvironmentError(f"unknown update environment: {name!r}")
    return dict(UPDATE_ENVIRONMENTS[name])


def _origin(url: object) -> tuple[str, str, int | None]:
    """Reduce a URL to its origin (scheme, host, port) for comparison."""
    if not isinstance(url, str) or not url:
        raise UpdateEnvironmentError(f"invalid update origin: {url!r}")
    parts = urlsplit(url)
    if not parts.scheme or not parts.hostname:
        raise UpdateEnvironmentError(f"update origin needs a scheme and host: {url!r}")
    return parts.scheme.lower(), parts.hostname.lower(), parts.port


def assert_distinct_update_origins(
    environments: Mapping[str, Mapping[str, object]],
) -> None:
    """Reject a test feed that shares its origin with production."""
    for name in ("test", "production"):
        if name not in environments:
            raise UpdateEnvironmentError(f"missing update environment: {name!r}")
        _origin(environments[name].get("origin"))
    test_origin = _origin(environments["test"]["origin"])
    production_origin = _origin(environments["production"]["origin"])
    if test_origin == production_origin:
        raise UpdateEnvironmentError(
            "test and production update feeds must use distinct origins: "
            f"{test_origin!r}")


# ---------------------------------------------------------------------------
# E5.17 — signing/notarization verification pattern (paid certs excluded)
# ---------------------------------------------------------------------------

SIGNING_STEPS = {
    "macos-dmg": (
        "hardened_runtime", "timestamp", "deep_strict_verify",
        "notarize", "staple",
    ),
    "macos-app": (
        "hardened_runtime", "timestamp", "deep_strict_verify",
    ),
    "windows-exe": (
        "timestamp", "ev_token_sign", "deep_strict_verify",
    ),
}

EXPECTED_SIGNING_AUTHORITIES = {
    "macos-dmg": "Developer ID Application: Keel",
    "macos-app": "Developer ID Application: Keel",
    "windows-exe": "Keel EV Code Signing CA",
}


def signing_plan(target: str) -> dict:
    """Describe the ordered signing/notarization steps for a target.

    Hardware-token EV signing is used on Windows and the PIN is never stored.
    This is the verification pattern only: no certificate is required here.
    """
    if target not in SIGNING_STEPS:
        raise SigningError(f"unsupported signing target: {target!r}")
    return {
        "target": target,
        "steps": list(SIGNING_STEPS[target]),
        "timestamp_every_embedded_executable": True,
        "hardened_runtime": target.startswith("macos"),
        "deep_strict_verify": True,
        "pin_persisted": False,
        "diagnostics_redacted": True,
    }


def assert_signing_steps_complete(
    target: str, steps: Iterable[Mapping[str, object]],
) -> None:
    """Require every step to succeed with the expected signing authority."""
    if target not in SIGNING_STEPS:
        raise SigningError(f"unsupported signing target: {target!r}")
    results = {str(step.get("name")): step for step in steps}
    for required in SIGNING_STEPS[target]:
        step = results.get(required)
        if step is None or step.get("ok") is not True:
            raise SigningError(f"signing step {required!r} did not succeed")
    verification = results["deep_strict_verify"]
    authority = verification.get("authority")
    expected = EXPECTED_SIGNING_AUTHORITIES[target]
    if authority != expected:
        raise SigningError(
            f"unexpected signing authority {authority!r}; expected {expected!r}")
    for step in results.values():
        if step.get("ok") is False:
            raise SigningError("a signing/notarization step failed")


# A secret's value runs to the next key assignment, a line break or a
# delimiter -- not just the next whitespace. The ``\w*`` prefix allows names
# such as ``KEEL_RELEASE_TOKEN`` to be recognised as assignments too.
_SECRET_ASSIGNMENT = r"\b\w*(?:pin|token|password|secret)\w*\s*[:=]\s*"
_INLINE_SECRET_RE = re.compile(
    r"(?i)(?P<key>\b\w*(?:pin|token|password|secret)\w*)\s*[:=]\s*"
    r"(?P<value>(?:(?!" + _SECRET_ASSIGNMENT + r")[^\r\n,;])*)"
)
# A bearer credential has no assignment key, so it needs its own rule:
# ``authorization: Bearer <token>`` previously survived untouched.
_BEARER_RE = re.compile(r"(?i)\b(?:Bearer|Basic)\s+[^\s,;'\"\r\n]{4,}")


def redact_diagnostics(text: str, secrets: Iterable[str] = ()) -> str:
    """Redact known secrets and any inline PIN/token values from diagnostics.

    The complete value of an inline assignment is removed: a multi-word secret
    (``token=super secret value``) must not leak its remaining words.  Bare
    Bearer/Basic credentials are removed as well.
    """
    redacted = str(text)
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _INLINE_SECRET_RE.sub(
        lambda match: f"{match.group('key')}=[REDACTED]", redacted,
    )
    return _BEARER_RE.sub("[REDACTED]", redacted)


def assert_signing_pin_not_persisted(config: Mapping[str, object]) -> None:
    """Fail if a signing PIN would be written to any config or diagnostic."""
    for key, value in config.items():
        if "pin" in str(key).lower() and value not in (None, "", False):
            raise SigningError("signing PIN must never be persisted")


# ---------------------------------------------------------------------------
# E5.18 — Keel keeps Linux; dsh does not
# ---------------------------------------------------------------------------

LINUX_RELEASE_FORMATS = ("AppImage", "DEB", "RPM")


def linux_release_targets() -> dict:
    """Describe Keel's Linux formats and the reference's dsh limitation."""
    return {
        "reference_dsh_supports_linux": False,
        "keel_supports_linux": True,
        "formats": list(LINUX_RELEASE_FORMATS),
        "owner_requirement": True,
    }


def assert_linux_release_targets(targets: Iterable[str]) -> None:
    """Require all three Linux formats and refuse a dsh-supported claim."""
    normalized = {str(target).strip().lower() for target in targets}
    required = {fmt.lower() for fmt in LINUX_RELEASE_FORMATS}
    if normalized != required:
        raise LinuxTargetError(
            f"expected {sorted(required)}, got {sorted(normalized)}")
    descriptor = linux_release_targets()
    if descriptor["keel_supports_linux"] is not True:
        raise LinuxTargetError("Keel must keep Linux as a release target")
    if descriptor["reference_dsh_supports_linux"] is not False:
        raise LinuxTargetError("dsh does not support Linux as a release target")


# ---------------------------------------------------------------------------
# E5.19 — documented known limitations
# ---------------------------------------------------------------------------

KNOWN_LIMITATION_TOPICS = (
    "server_dependent_features",
    "shared_vs_separate_state",
    "release_qualification_needs_production",
)

_KNOWN_LIMITATIONS = (
    ("Features disabled in the desktop app",
     "Some capabilities require a server and are disabled in the desktop "
     "build; the web/CLI surfaces keep them. <!-- server_dependent_features -->"),
    ("Shared versus separate state",
     "Desktop and CLI share sessions, settings, credentials and workspaces, "
     "but keep separate executable packages, plugin activation, lockfiles "
     "and site-packages. <!-- shared_vs_separate_state -->"),
    ("Release qualification",
     "A release is qualified only against the production update environment; "
     "the test feed exists for validation and is not a release channel. "
     "<!-- release_qualification_needs_production -->"),
)


def known_limitations_section() -> str:
    """Render the desktop README / About > Known limits section (stdlib only)."""
    lines = ["## Known limitations", ""]
    for title, body in _KNOWN_LIMITATIONS:
        lines.extend([f"### {title}", "", body, ""])
    return "\n".join(lines).rstrip() + "\n"


def assert_known_limitations_complete(text: str) -> None:
    """Fail if any required known-limitation topic is undocumented."""
    if not isinstance(text, str) or "## Known limitations" not in text:
        raise LimitationsError("missing 'Known limitations' section")
    for topic in KNOWN_LIMITATION_TOPICS:
        if topic not in text:
            raise LimitationsError(f"known-limitations topic missing: {topic}")
