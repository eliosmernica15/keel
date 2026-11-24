"""Canonical, dependency-free error contracts shared by Keel's surfaces.

This module is the single source of truth for machine-readable error envelopes
used by the web bridge (:mod:`keel.webapp`), the capability hub
(:mod:`keel.capabilities`) and the CLI (:mod:`keel.cli.main`). It is
*additive*: no existing surface needs to change in order to import it. A
surface adopts the contract simply by returning :func:`error_envelope` instead
of an ad-hoc ``{"error": ...}`` dict. See
``master-plan-v6-api-contracts-evidence.md`` for the current adoption matrix.

Canonical error envelope (schema version 1.0)::

    {
      "ok": false,
      "error": {
        "code": "policy_denied",          # stable machine code, non-empty str
        "message": "execution policy denied cap: reason",  # human-readable str
        "status": 403,                     # HTTP status, integer 100..599
        "details": {"capability": "..."}   # optional structured context
      },
      "api_contract_version": "1.0"        # schema version (this constant)
    }

Extra top-level keys are deliberately tolerated by :func:`is_canonical_envelope`
so a caller can add non-conflicting fields (e.g. ``request_id``) during an
incremental adoption. The nested ``error`` object, however, is strict.

Design notes / rationale
------------------------
* ``ok: false`` keeps the success marker used by the capability hub
  (``invoke`` returns ``{"ok": true, ...}``) symmetrical across all surfaces.
* A stable ``code`` is separated from the human ``message`` so clients never
  have to parse prose (today's web bridge sometimes puts a code in ``error``,
  sometimes a message, and the CLI writes ``code: message`` as raw text).
* ``status`` is embedded so the same envelope is valid over HTTP, on the CLI
  and in logs without a second lookup table.
"""

from __future__ import annotations

from typing import Any

#: Schema version of the envelope defined here (not the product version).
CANONICAL_VERSION = "1.0"

#: The five ``CapabilityError.code`` values emitted by the capability hub.
CAPABILITY_ERROR_CODES = frozenset({
    "not_found",
    "permission_denied",
    "policy_denied",
    "bad_params",
    "handler_error",
})

#: Canonical machine code -> default HTTP status. Unlisted codes use 400.
ERROR_STATUS: dict[str, int] = {
    # capability hub
    "not_found": 404,
    "permission_denied": 403,
    "policy_denied": 403,
    "bad_params": 400,
    "handler_error": 500,
    "capability_error": 400,
    # web bridge / generic HTTP
    "refused": 403,
    "unauthorized": 401,
    "bad_origin": 403,
    "confirmation_required": 409,
    "method_not_allowed": 405,
    "bad_request": 400,
    "payload_too_large": 413,
    "internal_error": 500,
}

DEFAULT_ERROR_STATUS = 400


def http_status_for_code(code: str, *, default: int = DEFAULT_ERROR_STATUS) -> int:
    """Return the canonical HTTP status for a machine-readable error code."""
    return ERROR_STATUS.get(str(code), default)


def error_envelope(
    code: str,
    message: str = "",
    *,
    status: int | None = None,
    details: dict | None = None,
    **extra: Any,
) -> dict:
    """Build a canonical error envelope.

    Args:
        code: Stable machine code (coerced to ``str``).
        message: Human-readable description (coerced to ``str``).
        status: HTTP status; defaults to :func:`http_status_for_code`.
        details: Optional structured context, stored under ``error.details``.
        **extra: Optional additional top-level keys (e.g. ``surface``), kept
            additive so older clients that ignore unknown keys still work.

    The returned dict always satisfies :func:`is_canonical_envelope` and
    carries ``api_contract_version`` so clients can detect schema drift.
    """
    code = str(code)
    message = str(message)
    resolved = http_status_for_code(code) if status is None else int(status)
    if not 100 <= resolved <= 599:
        raise ValueError(f"status must be an HTTP status in 100..599, got {resolved}")
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "status": resolved,
    }
    if details is not None:
        if not isinstance(details, dict):
            raise TypeError("details must be a dict")
        error["details"] = details
    envelope: dict[str, Any] = {
        "ok": False,
        "error": error,
        "api_contract_version": CANONICAL_VERSION,
    }
    if extra:
        envelope.update(extra)
    return envelope


def is_canonical_envelope(obj: Any) -> bool:
    """Return True iff ``obj`` has the canonical error-envelope shape.

    Strict about the nested ``error`` object and the ``ok: false`` marker;
    permissive about additional top-level keys to allow additive adoption.
    """
    if not isinstance(obj, dict):
        return False
    if obj.get("ok") is not False:  # identity check rejects 0/None/1 lookalikes
        return False
    error = obj.get("error")
    if not isinstance(error, dict):
        return False
    code = error.get("code")
    message = error.get("message")
    status = error.get("status")
    if not isinstance(code, str) or not code:
        return False
    if not isinstance(message, str):
        return False
    if not isinstance(status, int) or isinstance(status, bool):
        return False
    if not 100 <= status <= 599:
        return False
    if "details" in error and not isinstance(error["details"], dict):
        return False
    return True


def from_capability_error(
    exc: Any,
    *,
    status: int | None = None,
    details: dict | None = None,
    surface: str | None = None,
) -> dict:
    """Adapt any ``CapabilityError``-like object (has ``.code``) to canonical form.

    Kept dependency-free on purpose: callers pass the exception they caught,
    so this module never has to import :mod:`keel.capabilities`.
    """
    code = getattr(exc, "code", None) or "capability_error"
    extra: dict[str, Any] = {}
    if surface is not None:
        extra["surface"] = surface
    return error_envelope(code, str(exc), status=status, details=details, **extra)


def classify_envelope(obj: Any) -> str:
    """Classify a response body: canonical | success | legacy_flat | legacy_other | unknown.

    Useful for conformance audits that need to report which surface still
    returns a non-canonical shape.
    """
    if is_canonical_envelope(obj):
        return "canonical"
    if not isinstance(obj, dict):
        return "unknown"
    if obj.get("ok") is True:
        return "success"
    if isinstance(obj.get("error"), str):
        return "legacy_flat"
    if "error" in obj:
        return "legacy_other"
    return "unknown"
