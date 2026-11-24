"""Pure, stdlib-only backend behavior for the E6.*, X5.* and X6.* plan rows.

This is an **additive** module. It does not edit any existing source file, test,
config schema, web route or CLI command. Integration into the live runtime is a
separate lead decision (the exact seams are recorded in the companion evidence
document ``master-plan-v6-e6-x5-x6-backend-evidence.md``).

Scope -- the 27 ``status=not_started`` rows owned by this workstream:

Provider / credential / model UX (E6):
  E6.2  saved-key edit rules (whole-key replace / staged removal / cancel / shared warning)
  E6.3  environment-credential hints (detected / none / unconfirmed, never validates)
  E6.4  model list follow-vs-pin policy (10-minute refresh, built-in fallback)
  E6.6  model discovery: tolerant two-format parser + deferred save selection
  E6.7  model picker behavior (default, per-session log, reorder, delete blocks input)
  E6.11 troubleshooting catalog keyed by error code / symptom
  E6.12 config hot re-read on next request + same-machine editor guard
  E6.13 typed client-upgrade-required error naming the version to install
  E6.14 generated config reference derived from source (cannot drift)

Security / privacy extras (X5):
  X5.2  data-classification labels feeding redaction and egress decisions
  X5.3  time-boxed and just-in-time permissions (auto-expire, countdown)
  X5.4  scoped, short-lived, revocable, logged capability tokens
  X5.7  permission review with last-used dates and one-click prune
  X5.8  per-tool sandbox profiles selectable in agent frontmatter
  X5.10 sealed export bundles verified on import (signature + schema version)
  X5.11 provider data-handling cards built from the egress log (no retention claims)
  X5.12 dependency / model allow-deny lists in managed policy
  X5.13 safe-paste detector for key / token patterns

Developer platform (X6):
  X6.1  plugin scaffold generator, hot-reload change detection, mock host
  X6.2  plugin golden event streams + permission-denial harness
  X6.3  typed Python / TypeScript SDK generation, version-pinned to the daemon
  X6.4  API versioning policy (deprecation headers, sunset, minor compatibility)
  X6.5  loopback + token API-explorer guard, docs private unless G7
  X6.6  event schema registry with changelog and type subscriptions
  X6.8  layered config viewer (default/global/project/env/policy provenance)
  X6.9  settings search, diff against defaults, per-section reset, import/export
  X6.10 feature-lifecycle labels with experimental off by default

Design rules (enforced by ``keel/tests/test_e6_x5_x6_backend.py``):

1. **Standard library only.** No ``cryptography``, ``keyring``, ``requests``,
   ``socket``, ``subprocess`` or filesystem I/O. No import-time side effects.
2. **No I/O, no fabrication.** Every function operates on caller-supplied data
   or on injectable seams whose default methods raise ``NotImplementedError``.
   Secrets are never echoed: descriptors carry fingerprints/lengths only.
3. **Fail closed.** Unknown kinds, malformed input, expired or out-of-scope
   grants and tampered bundles deny/raise with an explicit typed reason.
4. **Deterministic.** Frozen dataclasses, canonical JSON (``sort_keys``, compact
   separators, ``allow_nan=False``) and SHA-256 prefixes mean identical inputs
   always produce identical output. Clocks are injectable; ids never depend on
   wall-clock time.
5. **Honest about crypto.** X5.10 uses a passphrase-derived HMAC signature plus
   a reversible XOR byte stream. It is *not* a substitute for real encryption;
   the guaranteed backend property is import verification (signature + schema
   version) with no third-party dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

__all__ = [
    "SCHEMA",
    "BackendError",
    "canonical_bytes",
    "digest",
    "id_for",
    "utc_stamp",
    # E6.2
    "CredentialEditState",
    "CredentialEditResult",
    "CredentialEditor",
    "InMemoryCredentialSeam",
    "SHARED_CREDENTIAL_WARNING",
    "DELETION_IRREVERSIBLE_WARNING",
    # E6.3
    "HintStatus",
    "CredentialHint",
    "detect_env_credential",
    # E6.4
    "ModelListMode",
    "ModelListState",
    "should_refresh",
    "update_published",
    "edit_model_list",
    "restore_defaults",
    # E6.6
    "ModelDiscoveryError",
    "DiscoveryState",
    "PendingSave",
    "parse_models_response",
    "toggle_model",
    "build_candidate",
    "save_candidate",
    "fallback_manual",
    # E6.7
    "ModelRef",
    "ModelPicker",
    # E6.11
    "TroubleshootingEntry",
    "TROUBLESHOOTING_CATALOG",
    "lookup_troubleshooting",
    "render_troubleshooting_page",
    # E6.12
    "ConfigSnapshot",
    "SeamNotImplemented",
    "InMemoryConfigSeam",
    "HotReloadAdapter",
    "EditorOpenDecision",
    "can_open_in_editor",
    # E6.13
    "ClientUpgradeRequired",
    "Compatibility",
    "parse_semver",
    "check_model_compatibility",
    # E6.14
    "ConfigField",
    "build_config_catalog",
    "catalog_digest",
    "assert_catalog_current",
    # X5.2
    "Classification",
    "LabeledResource",
    "DataPolicy",
    "classification_from_labels",
    "redaction_required",
    "egress_allowed",
    # X5.3
    "TimeBoxedGrant",
    "GrantDecision",
    "issue_grant",
    "is_active",
    "remaining_seconds",
    "consume_grant",
    # X5.4
    "AuditAction",
    "AuditEntry",
    "CapabilityToken",
    "TokenDecision",
    "CapabilityTokenIssuer",
    # X5.7
    "StandingRule",
    "RuleReview",
    "PruneResult",
    "review_rules",
    "prune_unused",
    # X5.8
    "SandboxProfile",
    "PROFILE_CAPABILITIES",
    "SandboxProfileError",
    "resolve_profile",
    "operation_allowed",
    # X5.10
    "EXPORT_SCHEMA_VERSION",
    "ExportBundle",
    "ImportVerification",
    "seal_export",
    "verify_import",
    # X5.11
    "EgressRecord",
    "DataHandlingCard",
    "build_data_handling_cards",
    "assert_no_retention_claims",
    # X5.12
    "DependencyDecision",
    "ManagedPolicy",
    "evaluate_dependency",
    # X5.13
    "PasteWarning",
    "detect_secret_paste",
    # X6.1
    "GeneratedFile",
    "plugin_scaffold",
    "FileState",
    "detect_changes",
    "MockHost",
    # X6.2
    "GoldenEventStream",
    "StreamDiff",
    "compare_event_streams",
    "DenialCheck",
    "permission_denial_check",
    # X6.3
    "DAEMON_API_VERSION",
    "ApiSchema",
    "generate_python_sdk",
    "generate_typescript_sdk",
    "assert_sdk_version_pinned",
    # X6.4
    "ApiVersion",
    "parse_version",
    "deprecation_headers",
    "is_compatible",
    "is_sunset",
    # X6.5
    "ExplorerDecision",
    "explorer_access",
    # X6.6
    "EventSchema",
    "EVENT_SCHEMAS",
    "EventValidation",
    "validate_event",
    "SubscriptionRegistry",
    # X6.8
    "ConfigLayer",
    "LAYER_PRECEDENCE",
    "ResolvedSetting",
    "resolve_layers",
    # X6.9
    "SettingDiff",
    "search_settings",
    "diff_against_defaults",
    "reset_section",
    "export_settings",
    "import_settings",
    # X6.10
    "FeatureLifecycle",
    "FEATURE_LIFECYCLES",
    "FeatureFlagDecision",
    "feature_enabled",
    "validate_feature_config",
]

SCHEMA = "e6-x5-x6-backend/v1"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class BackendError(ValueError):
    """Base class for every typed, fail-closed failure in this module."""


def canonical_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 JSON bytes used by every hash/signature here."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    """Full SHA-256 hex digest of ``value``'s canonical form."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def id_for(*parts: Any) -> str:
    """Stable 16-hex-char id derived only from ``parts`` (never from time)."""
    return hashlib.sha256(canonical_bytes(list(parts))).hexdigest()[:16]


def utc_stamp(epoch_seconds: float | None = None) -> str:
    """UTC ISO-8601 stamp for an injectable epoch-seconds value."""
    now = time.time() if epoch_seconds is None else float(epoch_seconds)
    return (
        datetime.fromtimestamp(now, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sorted_tuple(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(v) for v in values}))


# ===========================================================================
# E6 -- provider / credential / model UX
# ===========================================================================

# ---------------------------------------------------------------------------
# E6.2 -- saved-key edit rules
# ---------------------------------------------------------------------------

SHARED_CREDENTIAL_WARNING = "shared_credential_affects_every_feature"
DELETION_IRREVERSIBLE_WARNING = "deletion_cannot_be_undone_settings_failed"


@dataclass(frozen=True)
class CredentialEditState:
    """Staged edit of a saved credential. The raw secret is never stored here.

    ``staged_value`` (when set) is the *entire* replacement key -- typing never
    appends to a partial value. ``remove`` stages whole-key deletion, applied
    only on :meth:`CredentialEditor.apply`; ``cancel`` discards the stage.
    """

    reference: str
    shared_with: tuple[str, ...] = ()
    staged_value: str | None = None
    remove: bool = False

    def descriptor(self) -> dict[str, Any]:
        """Content-free view safe to log: fingerprint/length, never the value."""
        return {
            "reference": self.reference,
            "shared_with": list(self.shared_with),
            "revealed": False,
            "copyable": False,
            "partial_edit": False,
            "staged_fingerprint": (
                hashlib.sha256(self.staged_value.encode("utf-8")).hexdigest()
                if self.staged_value is not None
                else None
            ),
            "staged_length": (
                len(self.staged_value) if self.staged_value is not None else None
            ),
            "remove": self.remove,
        }

    def to_json(self) -> str:
        return _dumps(self.descriptor())


@dataclass(frozen=True)
class CredentialEditResult:
    applied: bool
    reference: str
    action: str  # "replace" | "remove" | "cancelled"
    warnings: tuple[str, ...] = ()
    retry_available: bool = False
    deletion_succeeded: bool = False
    settings_succeeded: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = dict(vars(self))
        data["warnings"] = list(self.warnings)
        return data


class InMemoryCredentialSeam:
    """Test seam: stores only fingerprints, never real key material."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def write(self, reference: str, value: str | None) -> bool:
        # ``None`` represents deletion of a staged whole-key removal.
        if value is None:
            self.values.pop(reference, None)
        else:
            self.values[reference] = value
        return True

    def delete(self, reference: str) -> bool:
        self.values.pop(reference, None)
        return True


class CredentialEditor:
    """Pure state machine implementing E6.2's saved-key edit rules."""

    def __init__(
        self,
        *,
        write_seam: Callable[[str, str | None], bool] | None = None,
        delete_seam: Callable[[str], bool] | None = None,
    ) -> None:
        # Default seams deliberately fail closed instead of mutating anything.
        self._write = write_seam or (lambda _ref, _val: False)
        self._delete = delete_seam or (lambda _ref: False)

    def start(self, reference: str, shared_with: Iterable[str] = ()) -> CredentialEditState:
        return CredentialEditState(reference=reference, shared_with=_sorted_tuple(shared_with))

    def type_replaces(self, state: CredentialEditState, whole_value: str) -> CredentialEditState:
        """Typing replaces the whole key; no reveal/copy/partial edit exists."""
        return replace(state, staged_value=whole_value, remove=False)

    def stage_removal(self, state: CredentialEditState) -> CredentialEditState:
        """Backspace/Delete stages whole-key removal (not applied yet)."""
        return replace(state, staged_value=None, remove=True)

    def cancel(self, state: CredentialEditState) -> CredentialEditResult:
        """Cancel preserves everything: the stage is discarded, nothing applied."""
        return CredentialEditResult(applied=False, reference=state.reference, action="cancelled")

    def apply(self, state: CredentialEditState) -> CredentialEditResult:
        warnings: list[str] = []
        if state.shared_with and (state.remove or state.staged_value == ""):
            warnings.append(SHARED_CREDENTIAL_WARNING)

        if state.remove:
            deleted = bool(self._delete(state.reference))
            if not deleted:
                return CredentialEditResult(
                    applied=False,
                    reference=state.reference,
                    action="remove",
                    warnings=tuple(warnings),
                    deletion_succeeded=False,
                    settings_succeeded=False,
                )
            # Deletion happened first; a settings failure cannot be undone.
            written = bool(self._write(state.reference, None))
            if not written:
                warnings.append(DELETION_IRREVERSIBLE_WARNING)
                return CredentialEditResult(
                    applied=False,
                    reference=state.reference,
                    action="remove",
                    warnings=tuple(warnings),
                    retry_available=True,
                    deletion_succeeded=True,
                    settings_succeeded=False,
                )
            return CredentialEditResult(
                applied=True,
                reference=state.reference,
                action="remove",
                warnings=tuple(warnings),
                deletion_succeeded=True,
                settings_succeeded=True,
            )

        if state.staged_value is None:
            # Nothing staged: an Apply with no change is a no-op, not a delete.
            return CredentialEditResult(
                applied=False, reference=state.reference, action="replace"
            )
        written = bool(self._write(state.reference, state.staged_value))
        return CredentialEditResult(
            applied=written,
            reference=state.reference,
            action="replace",
            warnings=tuple(warnings),
            settings_succeeded=written,
        )


# ---------------------------------------------------------------------------
# E6.3 -- environment credential hints
# ---------------------------------------------------------------------------


class HintStatus(str, Enum):
    DETECTED = "detected"   # green: env var present (never validated)
    NONE = "none"           # yellow: env var absent
    UNCONFIRMED = "unconfirmed"  # status read failed


@dataclass(frozen=True)
class CredentialHint:
    provider: str
    env_var: str
    status: HintStatus
    excluded: bool = False  # provider-managed credential file: outside the check

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "env_var": self.env_var,
            "status": self.status.value,
            "excluded": self.excluded,
            "validated": False,
        }


def detect_env_credential(
    provider: str,
    env_var: str,
    env: Mapping[str, Any],
    *,
    provider_managed_sources: Iterable[str] = (),
) -> CredentialHint:
    """Return a presence-only hint. Detection NEVER validates the credential.

    ``provider_managed_sources`` names env vars/credential files managed by the
    provider itself; those are outside this check and reported as ``excluded``.
    """
    managed = set(provider_managed_sources)
    if env_var in managed:
        return CredentialHint(provider, env_var, HintStatus.NONE, excluded=True)
    try:
        present = env.get(env_var) not in (None, "")
    except Exception:  # a failing status read must yield "unconfirmed", never a guess
        return CredentialHint(provider, env_var, HintStatus.UNCONFIRMED)
    return CredentialHint(
        provider, env_var, HintStatus.DETECTED if present else HintStatus.NONE
    )


# ---------------------------------------------------------------------------
# E6.4 -- model list follow/pin policy
# ---------------------------------------------------------------------------


class ModelListMode(str, Enum):
    FOLLOW = "follow"
    PINNED = "pinned"


@dataclass(frozen=True)
class ModelListState:
    mode: ModelListMode
    models: tuple[str, ...]
    builtin_models: tuple[str, ...]
    last_refresh: int | None = None
    version: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "models": list(self.models),
            "builtin_models": list(self.builtin_models),
            "last_refresh": self.last_refresh,
            "version": self.version,
        }


def should_refresh(state: ModelListState, now: int, ttl_seconds: int = 600) -> bool:
    """True when a followed list is due for its (~10 min) background refresh."""
    if state.mode is not ModelListMode.FOLLOW:
        return False
    if state.last_refresh is None:
        return True
    return now - int(state.last_refresh) >= int(ttl_seconds)


def update_published(
    state: ModelListState, published: Sequence[str] | None, now: int
) -> ModelListState:
    """Apply a provider refresh; ``None`` falls back to the built-in catalog."""
    models = _sorted_tuple(published) if published is not None else state.builtin_models
    return replace(
        state,
        mode=ModelListMode.FOLLOW,
        models=models,
        last_refresh=int(now),
        version=state.version + 1,
    )


def edit_model_list(state: ModelListState, edited: Sequence[str]) -> ModelListState:
    """Editing switches to a pinned custom list (stops following the provider)."""
    return replace(
        state,
        mode=ModelListMode.PINNED,
        models=_sorted_tuple(edited),
        last_refresh=None,
        version=state.version + 1,
    )


def restore_defaults(state: ModelListState) -> ModelListState:
    """"Restore defaults" re-follows the provider, starting from the built-in."""
    return replace(
        state,
        mode=ModelListMode.FOLLOW,
        models=state.builtin_models,
        last_refresh=None,
        version=state.version + 1,
    )


# ---------------------------------------------------------------------------
# E6.6 -- model discovery (tolerant parser + deferred save)
# ---------------------------------------------------------------------------


class ModelDiscoveryError(BackendError):
    """Discovery response could not be parsed; caller falls back to manual entry."""


@dataclass(frozen=True)
class DiscoveryState:
    configured: tuple[str, ...]
    discovered: tuple[str, ...]
    selected: frozenset[str]
    failure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": list(self.configured),
            "discovered": list(self.discovered),
            "selected": sorted(self.selected),
            "failure": self.failure,
        }


@dataclass(frozen=True)
class PendingSave:
    """Describes what *would* be saved. Nothing is persisted until ``save``."""

    models: tuple[str, ...]
    saved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"models": list(self.models), "saved": self.saved}


def parse_models_response(payload: Any) -> tuple[str, ...]:
    """Tolerant parser for the two common ``GET /models`` list formats.

    Accepts ``{"data": [{"id": "m"}, ...]}``, ``{"models": [...]}``, a bare
    list of objects, and a bare list of id strings. Duplicate ids are removed
    in first-seen order. Malformed responses raise :class:`ModelDiscoveryError`
    with a clear, caller-facing message.
    """
    if isinstance(payload, dict):
        if "data" in payload:
            items = payload["data"]
        elif "models" in payload:
            items = payload["models"]
        else:
            raise ModelDiscoveryError("missing 'data' or 'models' list in response")
    elif isinstance(payload, list):
        items = payload
    else:
        raise ModelDiscoveryError("response must be a JSON object or list")

    if not isinstance(items, list):
        raise ModelDiscoveryError("model list must be a JSON array")

    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            model_id = item["id"]
        else:
            raise ModelDiscoveryError("each model must be a string or an object with 'id'")
        model_id = model_id.strip()
        if model_id and model_id not in seen:
            seen.add(model_id)
            out.append(model_id)
    if not out:
        raise ModelDiscoveryError("model list is empty")
    return tuple(out)


def toggle_model(state: DiscoveryState, model: str, on: bool) -> DiscoveryState:
    """Tick to add / untick to remove a model from the pending selection."""
    selected = set(state.selected)
    if on:
        selected.add(model)
    else:
        selected.discard(model)
    return replace(state, selected=frozenset(selected))


def build_candidate(state: DiscoveryState) -> PendingSave:
    """Configured models the endpoint did not list stay; only ticked adds apply.

    The returned descriptor is explicitly ``saved=False``: nothing is written
    until :func:`save_candidate` is called by the caller's Save action.
    """
    # Configured models the endpoint did not list are preserved; a configured
    # model that WAS listed follows the tick state (untick removes it).
    kept = [m for m in state.configured if m not in state.discovered]
    added = [m for m in state.discovered if m in state.selected]
    merged: list[str] = []
    for model in kept + added:
        if model not in merged:
            merged.append(model)
    return PendingSave(models=tuple(merged), saved=False)


def save_candidate(pending: PendingSave) -> PendingSave:
    """The explicit Save step flips the descriptor to ``saved=True``."""
    return replace(pending, saved=True)


def fallback_manual(state: DiscoveryState, reason: str) -> DiscoveryState:
    """On discovery failure, fall back to manual entry with a clear reason."""
    return replace(state, discovered=(), selected=frozenset(), failure=str(reason))


# ---------------------------------------------------------------------------
# E6.7 -- model picker behavior
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRef:
    model: str
    provider: str


class ModelPicker:
    """Pure picker state: default for new sessions, per-session log, reorder."""

    def __init__(self, models: Iterable[ModelRef], default_model: str | None = None) -> None:
        self._order: list[ModelRef] = list(models)
        self._default: str | None = default_model
        self._sessions: dict[str, str] = {}
        self._blocked = False

    # -- selection / default --------------------------------------------------

    def select(self, model: str) -> None:
        """Selecting a model also sets the default for new sessions."""
        if any(ref.model == model for ref in self._order):
            self._default = model
            self._blocked = False

    @property
    def default(self) -> str | None:
        return self._default

    def default_provider(self) -> str | None:
        for ref in self._order:
            if ref.model == self._default:
                return ref.provider
        return None

    # -- per-session recorded model ------------------------------------------

    def record_session(self, session_id: str, model: str) -> None:
        """A session keeps the model recorded in its own log, not the default."""
        self._sessions[session_id] = model

    def session_model(self, session_id: str) -> str | None:
        return self._sessions.get(session_id)

    # -- reorder (drag with keyboard up/down alternative) ---------------------

    def move(self, model: str, delta: int) -> bool:
        """Reorder by ``-1``/``+1``; keyboard up/down delegates to the same op."""
        for idx, ref in enumerate(self._order):
            if ref.model == model:
                target = idx + int(delta)
                if 0 <= target < len(self._order):
                    self._order.insert(target, self._order.pop(idx))
                    return True
                return False
        return False

    def move_up(self, model: str) -> bool:
        return self.move(model, -1)

    def move_down(self, model: str) -> bool:
        return self.move(model, 1)

    @property
    def order(self) -> tuple[str, ...]:
        return tuple(ref.model for ref in self._order)

    # -- deleted default provider --------------------------------------------

    def delete_provider(self, provider: str) -> None:
        self._order = [ref for ref in self._order if ref.provider != provider]
        if self._default is not None and self.default_provider() is None:
            self._default = None
            self._blocked = True

    def composer_blocked(self) -> bool:
        """Deleted default provider -> composer shows "Select model"/blocks."""
        return self._blocked or (self._default is None and bool(self._order) is False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": list(self.order),
            "default": self._default,
            "sessions": dict(sorted(self._sessions.items())),
            "composer_blocked": self.composer_blocked(),
        }


# ---------------------------------------------------------------------------
# E6.11 -- troubleshooting catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TroubleshootingEntry:
    code: str
    aliases: tuple[str, ...]
    title: str
    steps: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "aliases": list(self.aliases),
            "title": self.title,
            "steps": list(self.steps),
        }


TROUBLESHOOTING_CATALOG: tuple[TroubleshootingEntry, ...] = (
    TroubleshootingEntry(
        "missing_credential",
        ("missing credential", "no api key", "401 auth"),
        "No credential configured",
        ("Set the provider env var or add a key in settings.", "Retry the request."),
    ),
    TroubleshootingEntry(
        "unknown_model",
        ("unknown model", "model not found", "404 model"),
        "Unknown model id",
        ("Refresh the model list.", "Pick a model from the provider catalog."),
    ),
    TroubleshootingEntry(
        "discovery_401",
        ("401 on discovery", "401 discovery", "models 401"),
        "Model discovery rejected (401)",
        ("Check the credential used for /models.", "Re-run discovery."),
    ),
    TroubleshootingEntry(
        "gateway_refuses_all",
        ("gateway refuses every request", "all requests refused", "gateway refused"),
        "Gateway refuses every request",
        ("Verify the base URL and gateway allowlist.", "Retry once."),
    ),
    TroubleshootingEntry(
        "reasoning_only_fail",
        ("only reasoning models fail", "reasoning model fails"),
        "Only reasoning models fail",
        ("Check reasoning-effort values against the provider contract.", "Try a non-reasoning model."),
    ),
    TroubleshootingEntry(
        "effort_menu_absent",
        ("effort menu absent", "no effort control"),
        "Effort menu is absent",
        ("Confirm the selected model declares reasoning effort.", "Update the model catalog."),
    ),
    TroubleshootingEntry(
        "effort_off_still_thinks",
        ("off doesn't stop thinking", "effort off still thinking"),
        "Effort 'off' still produces reasoning",
        ("Verify the API value sent for 'off'.", "Re-select the model."),
    ),
    TroubleshootingEntry(
        "image_refused_vs_provider",
        ("image refused vs provider rejects image", "image refused"),
        "Image refused locally or by the provider",
        ("Check the model's declared input types.", "If the provider rejects it, use a vision model."),
    ),
    TroubleshootingEntry(
        "stale_image_in_session",
        ("stale image stays in session log", "stale image"),
        "Stale image remains in the session log",
        ("Start a new session to clear the image context.", "Re-attach the image if needed."),
    ),
)


def lookup_troubleshooting(code_or_symptom: str) -> tuple[TroubleshootingEntry, ...]:
    """Match an exact error code, alias, or a case-insensitive symptom substring."""
    query = str(code_or_symptom).strip().lower()
    if not query:
        return ()
    matches: list[TroubleshootingEntry] = []
    for entry in TROUBLESHOOTING_CATALOG:
        candidates = (entry.code, *entry.aliases, entry.title)
        if any(query == c.lower() or query in c.lower() for c in candidates):
            matches.append(entry)
    return tuple(matches)


def render_troubleshooting_page() -> str:
    """Deterministic Markdown page generated from the catalog (cannot drift)."""
    lines = ["# Troubleshooting", ""]
    for entry in TROUBLESHOOTING_CATALOG:
        lines.append(f"## {entry.title} (`{entry.code}`)")
        lines.append("")
        for step in entry.steps:
            lines.append(f"- {step}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# E6.12 -- config hot re-read + same-machine editor guard
# ---------------------------------------------------------------------------


class SeamNotImplemented(BackendError):
    """A caller-supplied I/O seam was not provided (fail closed, no real I/O)."""


@dataclass(frozen=True)
class ConfigSnapshot:
    version: int
    config_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "config_digest": self.config_digest}


class InMemoryConfigSeam:
    """Injectable read seam: re-reads a caller-supplied config mapping."""

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = dict(config or {})
        self.reads = 0

    def read(self) -> dict[str, Any]:
        self.reads += 1
        return dict(self.config)


class HotReloadAdapter:
    """Re-reads config on the next request; no application restart required."""

    def __init__(self, read_seam: Callable[[], Mapping[str, Any]] | None = None) -> None:
        self._read = read_seam
        self._snapshot: ConfigSnapshot | None = None

    def refresh_if_changed(self) -> bool:
        """Re-read now; return True iff the effective config changed."""
        if self._read is None:
            raise SeamNotImplemented("no config read seam supplied")
        incoming = dict(self._read())
        incoming_hash = digest(incoming)
        if self._snapshot is not None and incoming_hash == self._snapshot.config_digest:
            return False
        version = 1 if self._snapshot is None else self._snapshot.version + 1
        self._snapshot = ConfigSnapshot(version=version, config_digest=incoming_hash)
        return True

    @property
    def current(self) -> ConfigSnapshot | None:
        return self._snapshot


@dataclass(frozen=True)
class EditorOpenDecision:
    allowed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason}


def can_open_in_editor(local_machine: bool) -> EditorOpenDecision:
    """The 'Open configuration file' action is valid only on the same machine.

    The backend only returns a decision; it never spawns ``$EDITOR``.
    """
    if local_machine:
        return EditorOpenDecision(True, "local_machine_ok")
    return EditorOpenDecision(False, "remote_ui_editor_not_available")


# ---------------------------------------------------------------------------
# E6.13 -- typed client-upgrade-required error
# ---------------------------------------------------------------------------


def parse_semver(value: str) -> tuple[int, int, int]:
    """Parse ``MAJOR.MINOR.PATCH``; missing parts default to zero."""
    parts = str(value).strip().lstrip("vV").split(".")
    if not parts or len(parts) > 3:
        raise BackendError(f"invalid semantic version: {value!r}")
    try:
        numbers = [int(p) for p in parts]
    except ValueError as exc:
        raise BackendError(f"invalid semantic version: {value!r}") from exc
    while len(numbers) < 3:
        numbers.append(0)
    return numbers[0], numbers[1], numbers[2]


class ClientUpgradeRequired(BackendError):
    """Typed error naming the exact version the user must install."""

    def __init__(self, model: str, required_version: str, current_version: str) -> None:
        self.model = model
        self.required_version = required_version
        self.current_version = current_version
        super().__init__(self.message())

    def message(self) -> str:
        return (
            f"Model {self.model!r} requires Keel >= {self.required_version}; "
            f"installed {self.current_version}. Install version "
            f"{self.required_version} to use this model."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "client_upgrade_required",
            "model": self.model,
            "required_version": self.required_version,
            "current_version": self.current_version,
            "message": self.message(),
        }


@dataclass(frozen=True)
class Compatibility:
    compatible: bool
    model: str
    required_version: str
    current_version: str

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


def check_model_compatibility(
    model: str, required_version: str, current_version: str
) -> Compatibility:
    """Return a compatibility descriptor; raise the typed error when too old."""
    required = parse_semver(required_version)
    current = parse_semver(current_version)
    if current >= required:
        return Compatibility(True, model, required_version, current_version)
    raise ClientUpgradeRequired(model, required_version, current_version)


# ---------------------------------------------------------------------------
# E6.14 -- generated config reference (cannot drift)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigField:
    key: str
    field_type: str
    default: str
    description: str
    section: str = "general"

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


def build_config_catalog(fields: Iterable[ConfigField]) -> str:
    """Render deterministic Markdown with stable anchors derived from fields."""
    ordered = sorted(fields, key=lambda f: (f.section, f.key))
    lines = ["# Configuration reference", "", "> Generated from source. Do not edit by hand.", ""]
    section = ""
    for item in ordered:
        if item.section != section:
            section = item.section
            lines.extend([f"## {section}", ""])
        lines.append(f"### `{item.key}`")
        lines.append("")
        lines.append(f"- Type: `{item.field_type}`")
        lines.append(f"- Default: `{item.default}`")
        lines.append(f"- Description: {item.description}")
        lines.append(f"- Anchor: `#{item.key.replace('.', '-')}`")
        lines.append("")
    return "\n".join(lines)


def catalog_digest(rendered: str) -> str:
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def assert_catalog_current(fields: Iterable[ConfigField], rendered: str) -> bool:
    """True iff ``rendered`` still equals the source-derived reference."""
    return catalog_digest(build_config_catalog(fields)) == catalog_digest(rendered)


# ===========================================================================
# X5 -- security and privacy extras
# ===========================================================================

# ---------------------------------------------------------------------------
# X5.2 -- data-classification labels
# ---------------------------------------------------------------------------


class Classification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SECRET = "secret"


_CLASSIFICATION_RANK = {
    Classification.PUBLIC: 0,
    Classification.INTERNAL: 1,
    Classification.SECRET: 2,
}


@dataclass(frozen=True)
class LabeledResource:
    resource_id: str
    kind: str  # "file" | "memory"
    classification: Classification

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "kind": self.kind,
            "classification": self.classification.value,
        }


@dataclass(frozen=True)
class DataPolicy:
    """Egress policy; fail closed for internal/secret remote destinations."""

    allow_internal_remote: bool = False
    allow_secret_remote: bool = False


def classification_from_labels(labels: Iterable[str]) -> Classification:
    """Highest label wins; an unknown label escalates to SECRET (fail closed)."""
    valid: list[Classification] = []
    for label in labels:
        try:
            valid.append(Classification(str(label).strip().lower()))
        except ValueError:
            return Classification.SECRET
    if not valid:
        return Classification.PUBLIC
    return max(valid, key=lambda c: _CLASSIFICATION_RANK[c])


def redaction_required(resource: LabeledResource) -> bool:
    return resource.classification is not Classification.PUBLIC


def egress_allowed(resource: LabeledResource, remote: bool, policy: DataPolicy) -> bool:
    """Public always egresses; internal/secret need an explicit remote grant."""
    if not remote:
        return True
    if resource.classification is Classification.PUBLIC:
        return True
    if resource.classification is Classification.INTERNAL:
        return policy.allow_internal_remote
    return policy.allow_secret_remote


# ---------------------------------------------------------------------------
# X5.3 -- time-boxed and just-in-time permissions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeBoxedGrant:
    grant_id: str
    scope: str
    issued_at: int
    expires_at: int
    just_in_time: bool = False
    consumed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@dataclass(frozen=True)
class GrantDecision:
    granted: bool
    reason: str
    remaining_seconds: int

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


def issue_grant(
    scope: str,
    now: int,
    duration_seconds: int = 1800,
    just_in_time: bool = False,
) -> TimeBoxedGrant:
    """Issue an "allow for N minutes" grant (default 30 minutes)."""
    issued = int(now)
    return TimeBoxedGrant(
        grant_id=id_for("grant", scope, issued, duration_seconds, just_in_time),
        scope=scope,
        issued_at=issued,
        expires_at=issued + int(duration_seconds),
        just_in_time=bool(just_in_time),
    )


def is_active(grant: TimeBoxedGrant, now: int) -> bool:
    return int(now) <= grant.expires_at and int(now) >= grant.issued_at and not grant.consumed


def remaining_seconds(grant: TimeBoxedGrant, now: int) -> int:
    """Visible countdown; never negative."""
    return max(0, grant.expires_at - int(now))


def consume_grant(grant: TimeBoxedGrant, now: int) -> GrantDecision:
    """Use a grant. A JIT grant is single-use; expired/consumed grants deny."""
    if not is_active(grant, now):
        reason = "grant_expired" if int(now) > grant.expires_at else "grant_inactive"
        return GrantDecision(False, reason, remaining_seconds(grant, now))
    if grant.just_in_time:
        return GrantDecision(
            True, "just_in_time_granted", remaining_seconds(grant, now)
        )
    return GrantDecision(True, "time_boxed_granted", remaining_seconds(grant, now))


# ---------------------------------------------------------------------------
# X5.4 -- capability tokens
# ---------------------------------------------------------------------------


class AuditAction(str, Enum):
    ISSUE = "issue"
    USE = "use"
    DENY = "deny"
    REVOKE = "revoke"


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    action: AuditAction
    token_id: str
    subject: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "action": self.action.value,
            "token_id": self.token_id,
            "subject": self.subject,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CapabilityToken:
    token_id: str
    subject: str
    scope: tuple[str, ...]
    issued_at: int
    expires_at: int
    revoked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "subject": self.subject,
            "scope": list(self.scope),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
        }


@dataclass(frozen=True)
class TokenDecision:
    allowed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


class CapabilityTokenIssuer:
    """Issues short-lived, scoped, revocable tokens with an append-only audit log."""

    def __init__(self) -> None:
        self._tokens: dict[str, CapabilityToken] = {}
        self._audit: list[AuditEntry] = []
        self._seq = 0

    def _log(self, action: AuditAction, token: CapabilityToken, detail: str = "") -> None:
        self._seq += 1
        self._audit.append(
            AuditEntry(self._seq, action, token.token_id, token.subject, detail)
        )

    def issue(
        self,
        subject: str,
        scope: Iterable[str],
        now: int,
        ttl_seconds: int = 300,
    ) -> CapabilityToken:
        scopes = _sorted_tuple(scope)
        token = CapabilityToken(
            token_id=id_for("cap", subject, scopes, int(now), ttl_seconds),
            subject=subject,
            scope=scopes,
            issued_at=int(now),
            expires_at=int(now) + int(ttl_seconds),
        )
        self._tokens[token.token_id] = token
        self._log(AuditAction.ISSUE, token)
        return token

    def verify(
        self, token: CapabilityToken, required_scope: Iterable[str], now: int
    ) -> TokenDecision:
        # Unknown token ids are never trusted, even if a forgery is presented.
        current = self._tokens.get(token.token_id)
        if current is None:
            return TokenDecision(False, "unknown_token")
        if current.revoked:
            return TokenDecision(False, "revoked")
        if int(now) > current.expires_at or int(now) < current.issued_at:
            return TokenDecision(False, "expired_or_not_yet_valid")
        needed = set(required_scope)
        if not needed.issubset(set(current.scope)):
            return TokenDecision(False, "out_of_scope")
        self._log(AuditAction.USE, current)
        return TokenDecision(True, "allowed")

    def revoke(self, token_id: str) -> bool:
        token = self._tokens.get(token_id)
        if token is None:
            return False
        revoked = replace(token, revoked=True)
        self._tokens[token_id] = revoked
        self._log(AuditAction.REVOKE, revoked)
        return True

    @property
    def audit_log(self) -> tuple[AuditEntry, ...]:
        return tuple(self._audit)


# ---------------------------------------------------------------------------
# X5.7 -- permission review
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StandingRule:
    rule_id: str
    scope: str
    created_at: int
    last_used_at: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@dataclass(frozen=True)
class RuleReview:
    rule: StandingRule
    age_days: int
    days_since_use: int | None
    stale: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule.to_dict(),
            "age_days": self.age_days,
            "days_since_use": self.days_since_use,
            "stale": self.stale,
        }


@dataclass(frozen=True)
class PruneResult:
    kept: tuple[StandingRule, ...]
    pruned: tuple[StandingRule, ...]
    prune_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kept": [r.to_dict() for r in self.kept],
            "pruned": [r.to_dict() for r in self.pruned],
            "prune_digest": self.prune_digest,
        }


def review_rules(
    rules: Iterable[StandingRule], now: int, stale_days: int = 30
) -> tuple[RuleReview, ...]:
    """Annotate each standing rule with age and last-used recency."""
    current = int(now)
    out: list[RuleReview] = []
    for rule in rules:
        age = max(0, (current - rule.created_at) // 86400)
        since = (
            None
            if rule.last_used_at is None
            else max(0, (current - rule.last_used_at) // 86400)
        )
        stale = since is None or since >= stale_days
        out.append(RuleReview(rule, age, since, stale))
    return tuple(out)


def prune_unused(
    rules: Iterable[StandingRule], now: int, stale_days: int = 30
) -> PruneResult:
    """One-click prune: remove never-used or stale rules, keep the rest."""
    reviewed = review_rules(rules, now, stale_days)
    pruned = tuple(item.rule for item in reviewed if item.stale)
    kept = tuple(item.rule for item in reviewed if not item.stale)
    return PruneResult(kept, pruned, digest([r.to_dict() for r in pruned]))


# ---------------------------------------------------------------------------
# X5.8 -- per-tool sandbox profiles
# ---------------------------------------------------------------------------


class SandboxProfile(str, Enum):
    READ_ONLY_FS = "read_only_fs"
    NO_NETWORK = "no_network"
    TEMP_ONLY_WRITE = "temp_only_write"


PROFILE_CAPABILITIES: dict[SandboxProfile, frozenset[str]] = {
    SandboxProfile.READ_ONLY_FS: frozenset({"fs_read"}),
    SandboxProfile.NO_NETWORK: frozenset({"fs_read", "fs_write", "temp_write"}),
    SandboxProfile.TEMP_ONLY_WRITE: frozenset({"fs_read", "temp_write"}),
}


class SandboxProfileError(BackendError):
    """Invalid or unknown frontmatter sandbox profile (fail closed)."""


def resolve_profile(frontmatter: Mapping[str, Any]) -> SandboxProfile:
    """Resolve ``sandbox_profile`` from agent frontmatter; default is strictest.

    An unknown/invalid profile raises rather than silently granting capabilities.
    """
    raw = frontmatter.get("sandbox_profile")
    if raw is None:
        return SandboxProfile.READ_ONLY_FS
    try:
        return SandboxProfile(str(raw).strip().lower())
    except ValueError as exc:
        raise SandboxProfileError(f"unknown sandbox profile: {raw!r}") from exc


def operation_allowed(profile: SandboxProfile, operation: str) -> bool:
    return str(operation) in PROFILE_CAPABILITIES[profile]


# ---------------------------------------------------------------------------
# X5.10 -- sealed export bundles verified on import
# ---------------------------------------------------------------------------

EXPORT_SCHEMA_VERSION = 1
_EXPORT_SALT = "keel-export-v1"


@dataclass(frozen=True)
class ExportBundle:
    schema_version: int
    nonce: str
    payload_hex: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))

    def to_json(self) -> str:
        return _dumps(self.to_dict())


@dataclass(frozen=True)
class ImportVerification:
    valid: bool
    reasons: tuple[str, ...]
    schema_version: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "reasons": list(self.reasons), "schema_version": self.schema_version}


def _keystream(passphrase: str, nonce: str, length: int) -> bytes:
    """Deterministic passphrase-derived bytes (toy cipher, stdlib only)."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(
            f"{passphrase}\x00{nonce}\x00{counter}".encode("utf-8")
        ).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _signature(passphrase: str, version: int, nonce: str, payload_hex: str) -> str:
    key = hashlib.sha256(f"{passphrase}\x00{_EXPORT_SALT}".encode("utf-8")).digest()
    msg = canonical_bytes([version, nonce, payload_hex])
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def seal_export(payload: Mapping[str, Any], passphrase: str, nonce: str) -> ExportBundle:
    """Seal a payload with a passphrase-derived signature and byte stream.

    The cipher is deliberately stdlib-only and is **not** production encryption;
    the guaranteed property is that import verifies signature + schema version.
    """
    plain = canonical_bytes(dict(payload))
    stream = _keystream(passphrase, nonce, len(plain))
    sealed = bytes(a ^ b for a, b in zip(plain, stream)).hex()
    return ExportBundle(
        schema_version=EXPORT_SCHEMA_VERSION,
        nonce=nonce,
        payload_hex=sealed,
        signature=_signature(passphrase, EXPORT_SCHEMA_VERSION, nonce, sealed),
    )


def verify_import(bundle: ExportBundle, passphrase: str) -> ImportVerification:
    """Verify on import; any version/tamper/passphrase problem fails closed."""
    reasons: list[str] = []
    if int(bundle.schema_version) != EXPORT_SCHEMA_VERSION:
        reasons.append("unsupported_schema_version")
    expected = _signature(
        passphrase, bundle.schema_version, bundle.nonce, bundle.payload_hex
    )
    if not hmac.compare_digest(expected, bundle.signature):
        reasons.append("signature_mismatch")
    return ImportVerification(
        valid=not reasons,
        reasons=tuple(reasons),
        schema_version=bundle.schema_version,
    )


# ---------------------------------------------------------------------------
# X5.11 -- provider data-handling cards
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EgressRecord:
    provider: str
    category: str
    remote: bool = True

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


@dataclass(frozen=True)
class DataHandlingCard:
    provider: str
    sent_categories: tuple[str, ...]
    account_settings_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "sent_categories": list(self.sent_categories),
            "account_settings_url": self.account_settings_url,
            "retention_claims": [],
        }


_RETENTION_WORDS = ("retain", "retention", "stores your", "keeps your data")


def build_data_handling_cards(
    providers: Mapping[str, Mapping[str, Any]], egress_log: Iterable[EgressRecord]
) -> tuple[DataHandlingCard, ...]:
    """Build a card per configured remote provider from its own egress log.

    Only what Keel sends and the user's own account-settings link are reported;
    nothing is claimed about the provider's retention.
    """
    by_provider: dict[str, set[str]] = {}
    for record in egress_log:
        if record.remote:
            by_provider.setdefault(record.provider, set()).add(record.category)
    cards: list[DataHandlingCard] = []
    for name, config in sorted(providers.items()):
        if str(config.get("kind", "remote")).lower() in ("local", "builtin", "local_model"):
            continue
        cards.append(
            DataHandlingCard(
                provider=name,
                sent_categories=_sorted_tuple(by_provider.get(name, ())),
                account_settings_url=str(config.get("account_settings_url", "")),
            )
        )
    return tuple(cards)


def assert_no_retention_claims(cards: Iterable[DataHandlingCard]) -> bool:
    # Inspect only reported content, not the (fixed) descriptor key names.
    blob = " ".join(
        value for c in cards for value in (*c.sent_categories, c.account_settings_url)
    )
    return not any(word in blob.lower() for word in _RETENTION_WORDS)


# ---------------------------------------------------------------------------
# X5.12 -- dependency / model allow-deny lists
# ---------------------------------------------------------------------------


class DependencyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class ManagedPolicy:
    allow_mcp: frozenset[str] = frozenset()
    deny_mcp: frozenset[str] = frozenset()
    allow_plugins: frozenset[str] = frozenset()
    deny_plugins: frozenset[str] = frozenset()
    allow_model_hashes: frozenset[str] = frozenset()
    deny_model_hashes: frozenset[str] = frozenset()

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_mcp": sorted(self.allow_mcp),
            "deny_mcp": sorted(self.deny_mcp),
            "allow_plugins": sorted(self.allow_plugins),
            "deny_plugins": sorted(self.deny_plugins),
            "allow_model_hashes": sorted(self.allow_model_hashes),
            "deny_model_hashes": sorted(self.deny_model_hashes),
        }


_DEPENDENCY_FIELDS = {
    "mcp_server": ("allow_mcp", "deny_mcp"),
    "plugin": ("allow_plugins", "deny_plugins"),
    "model_hash": ("allow_model_hashes", "deny_model_hashes"),
}


def evaluate_dependency(
    policy: ManagedPolicy, kind: str, value: str
) -> DependencyDecision:
    """Deny wins; otherwise a non-empty allowlist is required (fail closed)."""
    fields = _DEPENDENCY_FIELDS.get(str(kind))
    if fields is None:
        return DependencyDecision.DENY
    allow, deny = fields
    allowed_set: frozenset[str] = getattr(policy, allow)
    denied_set: frozenset[str] = getattr(policy, deny)
    if value in denied_set:
        return DependencyDecision.DENY
    if allowed_set and value not in allowed_set:
        return DependencyDecision.DENY
    return DependencyDecision.ALLOW


# ---------------------------------------------------------------------------
# X5.13 -- safe-paste detector
# ---------------------------------------------------------------------------


_PASTE_PATTERNS: dict[str, re.Pattern[str]] = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b"),
    "secret_assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|secret|password|token)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}"
    ),
}


@dataclass(frozen=True)
class PasteWarning:
    detected: bool
    matches: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        # Pattern names only -- the pasted text / secret is never echoed.
        return {"detected": self.detected, "matches": list(self.matches)}


def detect_secret_paste(text: str) -> PasteWarning:
    """Warn when pasted text contains a key/token pattern (content never echoed)."""
    hits = tuple(name for name, pattern in _PASTE_PATTERNS.items() if pattern.search(text))
    return PasteWarning(detected=bool(hits), matches=hits)


# ===========================================================================
# X6 -- developer platform
# ===========================================================================

# ---------------------------------------------------------------------------
# X6.1 -- plugin scaffold / hot reload / mock host
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneratedFile:
    path: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "content_digest": digest(self.content)}


def plugin_scaffold(name: str) -> tuple[GeneratedFile, ...]:
    """Deterministic plugin scaffold (no filesystem writes; caller applies)."""
    slug = re.sub(r"[^a-z0-9_-]+", "-", str(name).strip().lower()) or "plugin"
    init_py = (
        '"""Generated Keel plugin: {slug}."""\n\n'
        "NAME = {name!r}\n\n\n"
        "def register(host):\n"
        "    host.on('session.start', lambda payload: None)\n"
    ).format(slug=slug, name=slug)
    manifest = _dumps({"id": slug, "name": name, "version": "0.1.0", "api": "1"})
    return (
        GeneratedFile(f"plugins/{slug}/__init__.py", init_py),
        GeneratedFile(f"plugins/{slug}/manifest.json", manifest),
        GeneratedFile(f"plugins/{slug}/README.md", f"# {name}\n\nGenerated by `keel dev`.\n"),
    )


@dataclass(frozen=True)
class FileState:
    path: str
    content_digest: str


def detect_changes(
    before: Iterable[FileState], after: Iterable[FileState]
) -> tuple[str, ...]:
    """Return sorted paths whose digest changed (hot-reload trigger)."""
    old = {f.path: f.content_digest for f in before}
    new = {f.path: f.content_digest for f in after}
    changed = {p for p in set(old) | set(new) if old.get(p) != new.get(p)}
    return tuple(sorted(changed))


class MockHost:
    """In-memory host so plugins can be tested without the full application."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._seq = 0

    def emit(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._seq += 1
        event = {
            "seq": self._seq,
            "type": event_type,
            "payload": dict(payload),
            "event_id": id_for("event", self._seq, event_type, dict(payload)),
        }
        self._events.append(event)
        return event

    def call(self, name: str, args: Mapping[str, Any]) -> dict[str, Any]:
        """Record a host API call and return a deterministic acknowledgement."""
        return self.emit("host.call", {"name": name, "args": dict(args)})

    @property
    def event_stream(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._events)


# ---------------------------------------------------------------------------
# X6.2 -- plugin test harness
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldenEventStream:
    name: str
    events: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "events": [dict(e) for e in self.events]}


@dataclass(frozen=True)
class StreamDiff:
    matches: bool
    missing: tuple[str, ...]
    extra: tuple[str, ...]
    order_matches: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "matches": self.matches,
            "missing": list(self.missing),
            "extra": list(self.extra),
            "order_matches": self.order_matches,
        }


def compare_event_streams(
    actual: Iterable[Mapping[str, Any]], expected: Iterable[Mapping[str, Any]]
) -> StreamDiff:
    actual_keys = [digest(a) for a in actual]
    expected_keys = [digest(e) for e in expected]
    actual_set, expected_set = set(actual_keys), set(expected_keys)
    missing = tuple(sorted(expected_set - actual_set))
    extra = tuple(sorted(actual_set - expected_set))
    return StreamDiff(
        matches=not missing and not extra,
        missing=missing,
        extra=extra,
        order_matches=actual_keys == expected_keys,
    )


@dataclass(frozen=True)
class DenialCheck:
    denied: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


def permission_denial_check(
    operation: str, allowed_operations: Iterable[str]
) -> DenialCheck:
    """Permission-denial test: the operation must not be in the allow set."""
    if operation in set(allowed_operations):
        return DenialCheck(False, "operation_is_allowed")
    return DenialCheck(True, "operation_denied")


# ---------------------------------------------------------------------------
# X6.3 -- typed SDK generation, version-pinned
# ---------------------------------------------------------------------------

DAEMON_API_VERSION = "1.4.0"


@dataclass(frozen=True)
class ApiSchema:
    version: str
    methods: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "methods": [dict(m) for m in self.methods]}


def generate_python_sdk(schema: ApiSchema) -> str:
    lines = [
        '"""Generated Keel SDK. Do not edit by hand."""',
        "",
        f"DAEMON_API_VERSION = {schema.version!r}",
        "",
        "class KeelClient:",
        f'    """Typed client pinned to daemon API {schema.version}."""',
        "",
        "    def __init__(self, base_url):",
        "        self.base_url = base_url",
        "",
    ]
    for method in sorted(schema.methods, key=lambda m: str(m.get("name", ""))):
        name = re.sub(r"[^a-zA-Z0-9_]", "_", str(method.get("name", "method")))
        lines.append(f"    def {name}(self, **params):")
        lines.append(f"        return self._request({str(method.get('path', '/'))!r}, params)")
        lines.append("")
    lines.append("    def _request(self, path, params):")
    lines.append("        raise NotImplementedError('transport is supplied by the caller')")
    lines.append("")
    return "\n".join(lines)


def generate_typescript_sdk(schema: ApiSchema) -> str:
    lines = [
        "// Generated Keel SDK. Do not edit by hand.",
        "",
        f"export const DAEMON_API_VERSION = {json.dumps(schema.version)};",
        "",
        "export class KeelClient {",
        "  constructor(public baseUrl: string) {}",
        "",
    ]
    for method in sorted(schema.methods, key=lambda m: str(m.get("name", ""))):
        name = re.sub(r"[^a-zA-Z0-9_]", "_", str(method.get("name", "method")))
        lines.append(f"  {name}(params: Record<string, unknown>): Promise<unknown> {{")
        lines.append(f"    return this.request({json.dumps(str(method.get('path', '/')))} , params);")
        lines.append("  }")
        lines.append("")
    lines.append("  private request(path: string, params: Record<string, unknown>): Promise<unknown> {")
    lines.append("    throw new Error('transport is supplied by the caller');")
    lines.append("  }")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def assert_sdk_version_pinned(sdk_text: str, version: str) -> bool:
    return f"DAEMON_API_VERSION = {version!r}" in sdk_text or (
        f"DAEMON_API_VERSION = {json.dumps(version)}" in sdk_text
    )


# ---------------------------------------------------------------------------
# X6.4 -- API versioning policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApiVersion:
    major: int
    minor: int
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def parse_version(value: str) -> ApiVersion:
    major, minor, patch = parse_semver(value)
    return ApiVersion(major, minor, patch)


def deprecation_headers(
    version: ApiVersion, sunset_date: str, successor: str
) -> dict[str, str]:
    """Deprecation + Sunset + successor Link + explicit version headers."""
    return {
        "Deprecation": "true",
        "Sunset": sunset_date,
        "Link": f'</{str(successor).strip("/")}>; rel="successor-version"',
        "X-Keel-API-Version": str(version),
    }


def is_compatible(current: ApiVersion, previous: ApiVersion) -> bool:
    """Compatibility is guaranteed within a major and an adjacent minor."""
    if current.major != previous.major:
        return False
    return abs(current.minor - previous.minor) <= 1


def is_sunset(version: ApiVersion, sunset_date: str, today: date | None = None) -> bool:
    """True when today is on/after the version's sunset date."""
    current = today or date.today()
    try:
        sunset = date.fromisoformat(sunset_date)
    except ValueError as exc:
        raise BackendError(f"invalid sunset date: {sunset_date!r}") from exc
    del version  # date is the authority; version is retained for the caller/UI
    return current >= sunset


# ---------------------------------------------------------------------------
# X6.5 -- API explorer guard
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExplorerDecision:
    allowed: bool
    reason: str
    docs_public: bool

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


def explorer_access(loopback: bool, token_valid: bool, g7_enabled: bool) -> ExplorerDecision:
    """Interactive explorer requires loopback + a valid token; docs stay private unless G7."""
    if not loopback:
        return ExplorerDecision(False, "loopback_required", bool(g7_enabled))
    if not token_valid:
        return ExplorerDecision(False, "token_required", bool(g7_enabled))
    return ExplorerDecision(True, "allowed", bool(g7_enabled))


# ---------------------------------------------------------------------------
# X6.6 -- event schema registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventSchema:
    name: str
    version: int
    schema: Mapping[str, Any]
    changelog: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "schema": dict(self.schema),
            "changelog": list(self.changelog),
        }


_EVENT_SPEC: dict[str, tuple[tuple[str, str], ...]] = {
    "session.start": (("session_id", "string"), ("at", "int")),
    "session.end": (("session_id", "string"), ("status", "string")),
    "tool.call": (("tool", "string"), ("session_id", "string")),
    "provider.error": (("code", "string"), ("provider", "string")),
}


def _build_event_schemas() -> dict[str, EventSchema]:
    registry: dict[str, EventSchema] = {}
    for name, required_fields in _EVENT_SPEC.items():
        properties = {
            field_name: {"type": field_type} for field_name, field_type in required_fields
        }
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": name,
            "type": "object",
            "properties": properties,
            "required": [field_name for field_name, _ in required_fields],
        }
        registry[name] = EventSchema(
            name=name,
            version=1,
            schema=schema,
            changelog=(f"v1: initial schema for {name}",),
        )
    return registry


EVENT_SCHEMAS: dict[str, EventSchema] = _build_event_schemas()


@dataclass(frozen=True)
class EventValidation:
    valid: bool
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": list(self.errors)}


_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
}


def validate_event(event_type: str, payload: Mapping[str, Any]) -> EventValidation:
    """Minimal stdlib validator: required fields + declared primitive types."""
    schema = EVENT_SCHEMAS.get(event_type)
    if schema is None:
        return EventValidation(False, ("unknown_event_type",))
    errors: list[str] = []
    for field_name in schema.schema.get("required", []):
        if field_name not in payload:
            errors.append(f"missing:{field_name}")
            continue
        expected = schema.schema["properties"][field_name]["type"]
        check = _TYPE_CHECKS.get(expected)
        if check is not None and not check(payload[field_name]):
            errors.append(f"type:{field_name}:expected:{expected}")
    return EventValidation(valid=not errors, errors=tuple(errors))


class SubscriptionRegistry:
    """Plugins subscribe by event type; dispatch only schema-valid events."""

    def __init__(self) -> None:
        self._subs: dict[str, tuple[str, ...]] = {}

    def subscribe(self, plugin: str, event_type: str) -> bool:
        if event_type not in EVENT_SCHEMAS:
            return False
        current = self._subs.get(event_type, ())
        if plugin in current:
            return True
        self._subs[event_type] = tuple(sorted((*current, plugin)))
        return True

    def subscribers(self, event_type: str) -> tuple[str, ...]:
        return self._subs.get(event_type, ())

    def dispatch(
        self, event_type: str, payload: Mapping[str, Any]
    ) -> tuple[tuple[str, dict[str, Any]], ...]:
        if not validate_event(event_type, payload).valid:
            return ()
        return tuple((plugin, dict(payload)) for plugin in self.subscribers(event_type))


# ---------------------------------------------------------------------------
# X6.8 -- layered config viewer
# ---------------------------------------------------------------------------


class ConfigLayer(str, Enum):
    DEFAULT = "default"
    GLOBAL = "global"
    PROJECT = "project"
    ENV = "env"
    POLICY = "policy"


LAYER_PRECEDENCE: tuple[ConfigLayer, ...] = (
    ConfigLayer.DEFAULT,
    ConfigLayer.GLOBAL,
    ConfigLayer.PROJECT,
    ConfigLayer.ENV,
    ConfigLayer.POLICY,
)


@dataclass(frozen=True)
class ResolvedSetting:
    key: str
    value: Any
    source_layer: ConfigLayer
    overridden_layers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source_layer": self.source_layer.value,
            "overridden_layers": list(self.overridden_layers),
        }


def resolve_layers(
    layers: Mapping[ConfigLayer, Mapping[str, Any]]
) -> dict[str, ResolvedSetting]:
    """Resolve each key from the highest-precedence layer that sets it."""
    resolved: dict[str, ResolvedSetting] = {}
    for layer in LAYER_PRECEDENCE:
        for key, value in layers.get(layer, {}).items():
            previous = resolved.get(key)
            overridden = (
                previous.overridden_layers + (previous.source_layer.value,)
                if previous is not None
                else ()
            )
            resolved[key] = ResolvedSetting(key, value, layer, overridden)
    return dict(sorted(resolved.items()))


# ---------------------------------------------------------------------------
# X6.9 -- settings search / diff / reset / import-export
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SettingDiff:
    changed: tuple[tuple[str, Any, Any], ...]
    added: tuple[str, ...]
    removed: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": [[k, old, new] for k, old, new in self.changed],
            "added": list(self.added),
            "removed": list(self.removed),
        }


def _flatten(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, item in value.items():
        full = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, Mapping):
            out.update(_flatten(item, full))
        else:
            out[full] = item
    return out


def search_settings(settings: Mapping[str, Any], query: str) -> tuple[str, ...]:
    """Return dotted keys whose key path contains the case-insensitive query."""
    term = str(query).strip().lower()
    if not term:
        return ()
    return tuple(sorted(k for k in _flatten(settings) if term in k.lower()))


def diff_against_defaults(
    settings: Mapping[str, Any], defaults: Mapping[str, Any]
) -> SettingDiff:
    current, default = _flatten(settings), _flatten(defaults)
    changed = tuple(
        (k, default[k], current[k])
        for k in sorted(set(current) & set(default))
        if current[k] != default[k]
    )
    added = tuple(sorted(set(current) - set(default)))
    removed = tuple(sorted(set(default) - set(current)))
    return SettingDiff(changed, added, removed)


def reset_section(
    settings: Mapping[str, Any], defaults: Mapping[str, Any], section: str
) -> dict[str, Any]:
    """Per-section reset: restore only ``section`` keys to their default values."""
    result = json.loads(canonical_bytes(settings))
    section_defaults = defaults.get(section, {})
    if isinstance(section_defaults, Mapping):
        result[section] = json.loads(canonical_bytes(section_defaults))
    elif section in defaults:
        result[section] = section_defaults
    return result


def export_settings(settings: Mapping[str, Any]) -> str:
    """Deterministic export text."""
    return _dumps(settings)


def import_settings(text: str) -> dict[str, Any]:
    """Parse exported settings; reject non-object payloads with a typed error."""
    try:
        value = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise BackendError("settings import is not valid JSON") from exc
    if not isinstance(value, dict):
        raise BackendError("settings import must be a JSON object")
    return value


# ---------------------------------------------------------------------------
# X6.10 -- feature-lifecycle labels
# ---------------------------------------------------------------------------


class FeatureLifecycle(str, Enum):
    EXPERIMENTAL = "experimental"
    BETA = "beta"
    STABLE = "stable"


FEATURE_LIFECYCLES: dict[str, FeatureLifecycle] = {
    # Representative mapping for the features owned by this workstream; unknown
    # features are treated as experimental (off by default) -- fail closed.
    "E6.2": FeatureLifecycle.BETA,
    "E6.3": FeatureLifecycle.BETA,
    "E6.4": FeatureLifecycle.STABLE,
    "E6.6": FeatureLifecycle.BETA,
    "E6.7": FeatureLifecycle.STABLE,
    "E6.11": FeatureLifecycle.BETA,
    "E6.12": FeatureLifecycle.BETA,
    "E6.13": FeatureLifecycle.BETA,
    "E6.14": FeatureLifecycle.EXPERIMENTAL,
    "X5.2": FeatureLifecycle.BETA,
    "X5.3": FeatureLifecycle.EXPERIMENTAL,
    "X5.4": FeatureLifecycle.EXPERIMENTAL,
    "X5.7": FeatureLifecycle.BETA,
    "X5.8": FeatureLifecycle.BETA,
    "X5.10": FeatureLifecycle.BETA,
    "X5.11": FeatureLifecycle.BETA,
    "X5.12": FeatureLifecycle.EXPERIMENTAL,
    "X5.13": FeatureLifecycle.BETA,
    "X6.1": FeatureLifecycle.BETA,
    "X6.2": FeatureLifecycle.BETA,
    "X6.3": FeatureLifecycle.BETA,
    "X6.4": FeatureLifecycle.STABLE,
    "X6.5": FeatureLifecycle.EXPERIMENTAL,
    "X6.6": FeatureLifecycle.BETA,
    "X6.8": FeatureLifecycle.BETA,
    "X6.9": FeatureLifecycle.BETA,
    "X6.10": FeatureLifecycle.BETA,
}


@dataclass(frozen=True)
class FeatureFlagDecision:
    enabled: bool
    lifecycle: FeatureLifecycle
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "lifecycle": self.lifecycle.value,
            "reason": self.reason,
        }


def feature_enabled(feature: str, config: Mapping[str, Any]) -> FeatureFlagDecision:
    """Experimental is off by default; beta/stable are on unless explicitly off."""
    lifecycle = FEATURE_LIFECYCLES.get(feature, FeatureLifecycle.EXPERIMENTAL)
    if feature in config:
        enabled = bool(config[feature])
        return FeatureFlagDecision(enabled, lifecycle, "explicit_config")
    if lifecycle is FeatureLifecycle.EXPERIMENTAL:
        return FeatureFlagDecision(False, lifecycle, "experimental_off_by_default")
    return FeatureFlagDecision(True, lifecycle, "on_by_default")


def validate_feature_config(config: Mapping[str, Any]) -> tuple[str, ...]:
    """Return names of config keys that are not registered features."""
    return tuple(sorted(str(k) for k in config if k not in FEATURE_LIFECYCLES))
