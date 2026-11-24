"""Pure, stdlib-only repository/webhook/journal contracts (P0 addendum rows).

This module is the host-independent contract surface for four ``not_started``
P0 rows in ``PLAN-INDEX.json``:

* **Y5.4** -- incoming webhook authenticity: ``X-Webhook-Signature`` (hex
  HMAC-SHA256) + ``X-Webhook-Timestamp`` over ``timestamp.rawBody``, a five
  minute freshness window, and -- critically -- *no configured secret means
  every request is rejected (401)*.  Comparison is constant-time.
* **Y6.1** -- a cross-walk from the root evidence documents to plan IDs.  It
  verifies that the required in-scope documents are present, non-empty and
  reference recognised plan IDs; anything uncovered becomes an explicit row.
* **Y6.2** -- ``.verify-*``/``.build`` verification-artifact detection,
  gitignore/publish-allowlist handling and exclusion from publish.  Nothing is
  ever deleted: the only dispositions are ``ignore``, ``exclude_from_publish``
  and ``publish``.
* **Z4** -- a crash-safe turn journal: a write-ahead ``tool_started`` record
  before each tool run, a ``tool_done`` record afterwards, a per-record
  checksum with a hash chain so a torn tail is discarded atomically, and a
  pure recovery descriptor that names the interrupted tool ("retry or skip").

The module deliberately holds no host state.  It never reads the filesystem,
the environment, a clock, the network or a random source.  Callers supply the
document snapshot, the path list, the header mapping and the journal bytes;
``to_dict``/``as_dict`` exchange plain data for the caller's own storage layer.
An in-memory :class:`MemorySink` models the single atomic append; there is no
real I/O anywhere in this module.  ``PLAN-INDEX.json`` and all other existing
files are intentionally untouched.

Y6.4 (public-repo visibility) is *not* implemented here: it is owner-gated by
gate G1 and conflicts with the private-source requirement.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

FEATURE_IDS = ("Y5.4", "Y6.1", "Y6.2", "Z4")

# ---------------------------------------------------------------------------
# shared helpers / errors
# ---------------------------------------------------------------------------


class ContractError(ValueError):
    """Base class for repository-contract failures."""


class ContractValidationError(ContractError):
    """Fail-closed validation error carrying one or more written reasons."""

    def __init__(self, errors: Any):
        if isinstance(errors, str):
            errors = (errors,)
        self.errors = tuple(str(error) for error in errors)
        super().__init__("; ".join(self.errors))


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ENCODED_TRAVERSAL_RE = re.compile(r"(?i)%2e|%2f|%5c")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _named(value: Any, label: str) -> str:
    text = _text(value).strip()
    if not text or not _IDENTIFIER_RE.match(text):
        raise ContractValidationError("%s must be a non-empty safe identifier" % label)
    return text


def _values(values: Any, label: str) -> tuple[str, ...]:
    """Coerce an iterable of names; a bare string is never a list."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ContractValidationError("%s must be an iterable of names" % label)
    return tuple(_text(value) for value in values)


def _body_bytes(value: Any, label: str) -> bytes:
    """Accept explicit bytes-like bodies; never guess a string encoding."""
    if isinstance(value, str):
        raise ContractValidationError("%s must be bytes, not str" % label)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    raise ContractValidationError("%s must be a bytes-like object" % label)


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


# ===========================================================================
# Y5.4 -- webhook signature headers and no-secret rejection
# ===========================================================================

SIGNATURE_HEADER = "X-Webhook-Signature"
TIMESTAMP_HEADER = "X-Webhook-Timestamp"
SIGNATURE_ALGORITHM = "sha256"
DEFAULT_MAX_AGE_SECONDS = 300
MAX_WEBHOOK_AGE_SECONDS = 86_400
MAX_TIMESTAMP = 2**63 - 1
STATUS_ACCEPT = 200
STATUS_REJECT = 401

_DECIMAL_RE = re.compile(r"^[0-9]{1,19}$")

REASON_ACCEPTED = "verified"
REASON_NO_SECRET = "no_secret"
REASON_INVALID_REQUEST = "invalid_request"
REASON_INVALID_HEADER = "invalid_header"
REASON_AMBIGUOUS_HEADER = "ambiguous_header"
REASON_MISSING_SIGNATURE = "missing_signature"
REASON_MISSING_TIMESTAMP = "missing_timestamp"
REASON_BAD_SIGNATURE = "bad_signature"
REASON_BAD_TIMESTAMP = "bad_timestamp"
REASON_STALE_TIMESTAMP = "stale_timestamp"


@dataclass(frozen=True)
class WebhookDecision:
    """The pure disposition of one incoming webhook request."""

    ok: bool
    status: int
    reason: str

    def as_dict(self) -> dict:
        return {"ok": self.ok, "status": self.status, "reason": self.reason}


def _accept() -> WebhookDecision:
    return WebhookDecision(True, STATUS_ACCEPT, REASON_ACCEPTED)


def _reject(reason: str) -> WebhookDecision:
    # Authentication failures are uniform: a caller cannot distinguish
    # "no secret configured" from "bad signature" by status code.
    return WebhookDecision(False, STATUS_REJECT, reason)


def secret_configured(secret: Any) -> bool:
    """True only for a non-blank string secret.  No environment is read."""
    return isinstance(secret, str) and bool(secret.strip())


def _validate_secret(secret: Any) -> str:
    if not secret_configured(secret):
        raise ContractValidationError("webhook secret is not configured")
    return secret


def _validate_now(now: Any) -> int:
    if type(now) is not int or not 0 <= now <= MAX_TIMESTAMP:
        raise ContractValidationError("now must be a non-negative integer timestamp")
    return now


def _validate_max_age(max_age: Any) -> int:
    if type(max_age) is not int or not 1 <= max_age <= MAX_WEBHOOK_AGE_SECONDS:
        raise ContractValidationError(
            "webhook max age must be an integer between 1 and %d"
            % MAX_WEBHOOK_AGE_SECONDS)
    return max_age


def _validate_timestamp(timestamp: Any) -> int:
    if type(timestamp) is not int or not 0 <= timestamp <= MAX_TIMESTAMP:
        raise ContractValidationError("timestamp must be a non-negative integer")
    return timestamp


def sign_webhook(raw_body: Any, secret: Any, timestamp: Any) -> str:
    """Return the lowercase hex HMAC-SHA256 of ``timestamp + "." + rawBody``.

    A blank or missing secret can never produce a signature: the caller must
    fail closed rather than emit an unsigned request.
    """
    body = _body_bytes(raw_body, "raw body")
    key = _validate_secret(secret)
    ts = _validate_timestamp(timestamp)
    message = str(ts).encode("ascii") + b"." + body
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def webhook_headers(raw_body: Any, secret: Any, timestamp: Any) -> dict:
    """Build exactly the two signed-request headers required by Y5.4."""
    ts = _validate_timestamp(timestamp)
    return {
        SIGNATURE_HEADER: sign_webhook(raw_body, secret, ts),
        TIMESTAMP_HEADER: str(ts),
    }


def _normalized_headers(headers: Mapping[str, Any]) -> dict[str, str] | None:
    """Case-insensitive, duplicate-intolerant header projection."""
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return None
        name = key.strip().lower()
        if not name or name in normalized:
            return None
        normalized[name] = value
    return normalized


def verify_webhook(headers: Mapping[str, Any], raw_body: Any, *, secret: Any,
                   now: Any, max_age: Any = DEFAULT_MAX_AGE_SECONDS
                   ) -> WebhookDecision:
    """Authenticate an incoming webhook, fail closed in every ambiguous case.

    Structural misuse (a non-mapping header set, non-bytes body, bad ``now``)
    raises :class:`ContractValidationError`.  Everything attacker-controlled is
    answered with a uniform ``401`` decision.  The signature is compared with
    :func:`hmac.compare_digest` (constant time), and a missing/blank secret is
    rejected *before* any signature material is considered.
    """
    current = _validate_now(now)
    window = _validate_max_age(max_age)
    body = _body_bytes(raw_body, "raw body")
    if not isinstance(headers, Mapping):
        raise ContractValidationError("headers must be a mapping")

    if not secret_configured(secret):
        return _reject(REASON_NO_SECRET)

    projected = _normalized_headers(headers)
    if projected is None:
        return _reject(REASON_INVALID_HEADER)

    signature_key = SIGNATURE_HEADER.lower()
    timestamp_key = TIMESTAMP_HEADER.lower()
    if signature_key not in projected:
        return _reject(REASON_MISSING_SIGNATURE)
    if timestamp_key not in projected:
        return _reject(REASON_MISSING_TIMESTAMP)

    signature = projected[signature_key].strip().lower()
    if not _HEX_DIGEST_RE.match(signature):
        return _reject(REASON_BAD_SIGNATURE)

    raw_timestamp = projected[timestamp_key].strip()
    if not _DECIMAL_RE.match(raw_timestamp):
        return _reject(REASON_BAD_TIMESTAMP)
    timestamp = int(raw_timestamp)
    if timestamp > MAX_TIMESTAMP:
        return _reject(REASON_BAD_TIMESTAMP)

    if abs(current - timestamp) > window:
        return _reject(REASON_STALE_TIMESTAMP)

    expected = sign_webhook(body, secret, timestamp)
    if not hmac.compare_digest(expected, signature):
        return _reject(REASON_BAD_SIGNATURE)
    return _accept()


class WebhookVerifier:
    """Receiver helper that binds one configured secret to every verification."""

    def __init__(self, secret: Any, *, max_age: Any = DEFAULT_MAX_AGE_SECONDS):
        self.secret = secret
        self.max_age = _validate_max_age(max_age)

    def sign(self, raw_body: Any, timestamp: Any) -> str:
        return sign_webhook(raw_body, self.secret, timestamp)

    def headers(self, raw_body: Any, timestamp: Any) -> dict:
        return webhook_headers(raw_body, self.secret, timestamp)

    def verify(self, headers: Mapping[str, Any], raw_body: Any, *,
               now: Any) -> WebhookDecision:
        return verify_webhook(headers, raw_body, secret=self.secret,
                              now=now, max_age=self.max_age)


# ===========================================================================
# Y6.1 -- repository evidence-document cross-walk
# ===========================================================================

REQUIRED_EVIDENCE_DOCS = (
    "agent-evidence-area-commands.md",
    "agent-evidence-area-interactive-tui.md",
    "agent-evidence-area10-skills.md",
    "agent-evidence-area12-dependencies.md",
    "agent-evidence-area4-file-editing.md",
    "agent-evidence-area5-sandboxing.md",
    "agent-evidence-area6-parallel-agents.md",
    "agent-evidence-area8-permission-modes.md",
    "agent-evidence-area9-mcp.md",
    "agent-evidence-area9-tools-reference.md",
    "benchmark-and-evaluation-plan.md",
    "compute-feasibility.md",
    "feature-checklist.md",
    "interface-spec.md",
    "llm-development-roadmap.md",
    "llm-research-review.md",
    "test-plan.md",
)
# Master 4.2.5: training-data and model-architecture docs stay out of scope.
OUT_OF_SCOPE_DOCS = (
    "model-architecture-proposal.md",
    "training-data-plan.md",
)

STATUS_MAPPED = "mapped"
STATUS_UNCOVERED = "uncovered"
STATUS_MISSING = "missing"
STATUS_EMPTY = "empty"

_DOC_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*\.md$")
_PLAN_ID_RE = re.compile(r"^[A-Z][0-9]+(?:\.[0-9]+){0,3}$")
# A trailing full stop is sentence punctuation, not part of the id; a dot
# followed by a digit or an adjacent alphanumeric would extend the id instead.
_ID_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_.])([A-Z][0-9]+(?:\.[0-9]+){0,3})(?![A-Za-z0-9]|\.[0-9])")


@dataclass(frozen=True)
class CrossWalkRow:
    """One document's cross-walk entry; an uncovered doc is a first-class row."""

    doc: str
    status: str
    plan_ids: tuple[str, ...] = ()
    unknown_ids: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "doc": self.doc,
            "status": self.status,
            "plan_ids": list(self.plan_ids),
            "unknown_ids": list(self.unknown_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CrossWalk:
    """Deterministic, sorted cross-walk of a supplied document snapshot."""

    rows: tuple[CrossWalkRow, ...]
    missing: tuple[str, ...]
    out_of_scope_ignored: tuple[str, ...]
    known_ids: tuple[str, ...]

    def rows_with_status(self, status: Any) -> tuple[CrossWalkRow, ...]:
        wanted = _text(status)
        return tuple(row for row in self.rows if row.status == wanted)

    @property
    def uncovered(self) -> tuple[CrossWalkRow, ...]:
        return tuple(row for row in self.rows
                     if row.status in (STATUS_MISSING, STATUS_EMPTY,
                                       STATUS_UNCOVERED))

    def as_dict(self) -> dict:
        return {
            "rows": [row.as_dict() for row in self.rows],
            "missing": list(self.missing),
            "out_of_scope_ignored": list(self.out_of_scope_ignored),
            "known_ids": list(self.known_ids),
        }


def _validate_documents(documents: Any) -> dict[str, str]:
    if not isinstance(documents, Mapping):
        raise ContractValidationError("evidence documents must be a mapping")
    for name, content in documents.items():
        if (not isinstance(name, str) or not _DOC_NAME_RE.match(name)
                or _ENCODED_TRAVERSAL_RE.search(name)):
            raise ContractValidationError("unsafe evidence document name: %s" % name)
        if not isinstance(content, str):
            raise ContractValidationError(
                "evidence document content must be text: %s" % name)
    return dict(documents)


def _validate_known_ids(known_ids: Any) -> frozenset[str]:
    if known_ids is None:
        raise ContractValidationError("known plan ids must be an iterable")
    values = _values(known_ids, "known plan ids")
    ids: set[str] = set()
    for value in values:
        if not _PLAN_ID_RE.match(value):
            raise ContractValidationError("invalid plan id: %s" % value)
        ids.add(value)
    return frozenset(ids)


def build_cross_walk(documents: Any, known_ids: Any) -> CrossWalk:
    """Cross-walk a caller-supplied ``{doc_name: text}`` snapshot to plan IDs.

    This function never opens a file.  "Exists" means "present in the supplied
    snapshot", which keeps the contract pure while still letting the caller's
    storage layer enforce the real filesystem boundary.  Malformed inputs fail
    closed; content-level gaps are returned as explicit uncovered rows.
    """
    docs = _validate_documents(documents)
    known = _validate_known_ids(known_ids)
    required = set(REQUIRED_EVIDENCE_DOCS)
    ignored = tuple(sorted(set(docs) & set(OUT_OF_SCOPE_DOCS)))

    rows: list[CrossWalkRow] = []
    for doc in sorted(required - set(docs)):
        rows.append(CrossWalkRow(
            doc=doc, status=STATUS_MISSING,
            reason="required evidence document not supplied"))

    for doc in sorted(docs):
        if doc in OUT_OF_SCOPE_DOCS:
            continue
        content = docs[doc]
        if not content.strip():
            rows.append(CrossWalkRow(
                doc=doc,
                status=STATUS_EMPTY if doc in required else STATUS_UNCOVERED,
                reason="evidence document has no content"))
            continue
        refs = set(_ID_REF_RE.findall(content))
        mapped = tuple(sorted(refs & known))
        unknown = tuple(sorted(refs - known))
        rows.append(CrossWalkRow(
            doc=doc,
            status=STATUS_MAPPED if mapped else STATUS_UNCOVERED,
            plan_ids=mapped,
            unknown_ids=unknown,
            reason="" if mapped else "no recognised plan id reference",
        ))

    return CrossWalk(
        rows=tuple(rows),
        missing=tuple(sorted(required - set(docs))),
        out_of_scope_ignored=ignored,
        known_ids=tuple(sorted(known)),
    )


def verify_cross_walk(walk: Any) -> tuple[str, ...]:
    """Collect every cross-walk inconsistency deterministically; empty means OK."""
    if not isinstance(walk, CrossWalk):
        return ("cross-walk must be a CrossWalk",)
    errors: list[str] = []
    for row in walk.rows:
        if row.status != STATUS_MAPPED:
            errors.append("evidence document %s is %s: %s"
                          % (row.doc, row.status, row.reason))
        if row.unknown_ids:
            errors.append("evidence document %s references unknown plan ids: %s"
                          % (row.doc, ", ".join(row.unknown_ids)))
    return tuple(sorted(set(errors)))


def verify_evidence_documents(documents: Any, known_ids: Any) -> tuple[str, ...]:
    """Convenience: build the cross-walk and verify it in one fail-closed call."""
    return verify_cross_walk(build_cross_walk(documents, known_ids))


def cross_walk_dict(walk: Any) -> dict:
    """Serialize a verified cross-walk; invalid cross-walks are rejected."""
    errors = verify_cross_walk(walk)
    if errors:
        raise ContractValidationError(errors)
    return walk.as_dict()


# ===========================================================================
# Y6.2 -- .verify-*/.build artifact handling (detect, ignore, exclude)
# ===========================================================================

ARTIFACT_DIR_PREFIX = ".verify-"
ARTIFACT_DIR_NAMES = frozenset({".build"})
GITIGNORE_PATTERNS = (".verify-*/", ".build/")

ACTION_PUBLISH = "publish"
ACTION_IGNORE = "ignore"
ACTION_EXCLUDE_FROM_PUBLISH = "exclude_from_publish"
_VALID_ACTIONS = frozenset({ACTION_PUBLISH, ACTION_IGNORE,
                            ACTION_EXCLUDE_FROM_PUBLISH})
_FORBIDDEN_ACTIONS = frozenset({"delete", "remove", "unlink", "rmtree", "purge"})

_PATH_CLASSES = ("source", "artifact")


@dataclass(frozen=True)
class ArtifactScan:
    """Deterministic classification of a caller-supplied path list."""

    artifacts: tuple[str, ...]
    publishable: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"artifacts": list(self.artifacts),
                "publishable": list(self.publishable)}


@dataclass(frozen=True)
class ArtifactAllowlist:
    """A canonical, artifact-free set of paths the caller may publish."""

    entries: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"entries": list(self.entries)}


@dataclass(frozen=True)
class Disposition:
    """One path's publish decision.  Deletion is never an available action."""

    path: str
    action: str
    reason: str

    def as_dict(self) -> dict:
        return {"path": self.path, "action": self.action, "reason": self.reason}


def _path_segments(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise ContractValidationError("path must be a string")
    text = value.strip()
    if not text or _CONTROL_RE.search(text) or _ENCODED_TRAVERSAL_RE.search(text):
        raise ContractValidationError("unsafe artifact path: %s" % value)
    normalized = re.sub(r"\\", "/", text)
    if normalized.startswith("/") or _DRIVE_RE.match(normalized):
        raise ContractValidationError("artifact path must be relative: %s" % value)
    segments: list[str] = []
    for part in normalized.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ContractValidationError("artifact path traversal: %s" % value)
        segments.append(part)
    if not segments:
        raise ContractValidationError("unsafe artifact path: %s" % value)
    return tuple(segments)


def _canonical_path(value: Any) -> str:
    return "/".join(_path_segments(value))


def classify_path(value: Any) -> str:
    """Return ``"artifact"`` or ``"source"``; unsafe paths fail closed."""
    for segment in (part.casefold() for part in _path_segments(value)):
        if segment in ARTIFACT_DIR_NAMES or segment.startswith(ARTIFACT_DIR_PREFIX):
            return "artifact"
    return "source"


def is_publishable(value: Any) -> bool:
    """True only for a safe, non-artifact path (unsafe paths return False)."""
    try:
        return classify_path(value) == "source"
    except ContractValidationError:
        return False


def scan_artifacts(paths: Any) -> ArtifactScan:
    """Classify and de-duplicate a caller-supplied path list deterministically."""
    if isinstance(paths, (str, bytes)) or not isinstance(paths, Iterable):
        raise ContractValidationError("paths must be an iterable of strings")
    items = tuple(paths)
    if any(not isinstance(item, str) for item in items):
        raise ContractValidationError("paths must be strings")
    artifacts: set[str] = set()
    sources: set[str] = set()
    for item in items:
        canonical = _canonical_path(item)
        (artifacts if classify_path(item) == "artifact" else sources).add(canonical)
    return ArtifactScan(artifacts=tuple(sorted(artifacts)),
                        publishable=tuple(sorted(sources)))


def make_allowlist(paths: Any) -> ArtifactAllowlist:
    """Build an artifact-free publish allowlist; wildcards are not permitted."""
    if isinstance(paths, ArtifactAllowlist):
        entries = paths.entries
    elif isinstance(paths, (str, bytes)) or not isinstance(paths, Iterable):
        raise ContractValidationError("allowlist paths must be an iterable")
    else:
        entries = tuple(paths)
    canonical: set[str] = set()
    for entry in entries:
        if not isinstance(entry, str) or "*" in entry or "?" in entry:
            raise ContractValidationError("allowlist entries must be literal paths")
        if classify_path(entry) != "source":
            raise ContractValidationError("artifact cannot be allowlisted: %s" % entry)
        canonical.add(_canonical_path(entry))
    return ArtifactAllowlist(entries=tuple(sorted(canonical)))


def is_allowed(path: Any, allowlist: Any) -> bool:
    """True only for a safe, non-artifact, canonically allowlisted path."""
    if not isinstance(allowlist, ArtifactAllowlist) or not is_publishable(path):
        return False
    try:
        return _canonical_path(path) in allowlist.entries
    except ContractValidationError:
        return False


def filter_publishable(paths: Any, allowlist: Any) -> tuple[str, ...]:
    """Return only safe paths that are also in the explicit publish allowlist."""
    scan = scan_artifacts(paths)
    if not isinstance(allowlist, ArtifactAllowlist):
        raise ContractValidationError("filter needs an ArtifactAllowlist")
    return tuple(sorted(path for path in scan.publishable
                        if path in allowlist.entries))


def artifact_disposition(paths: Any, allowlist: Any = None) -> tuple[Disposition, ...]:
    """Plan dispositions: ignore artifacts, exclude unlisted, publish the rest.

    There is no delete/remove action.  The caller uses :func:`gitignore_patterns`
    for ``ignore`` rows and simply omits ``exclude_from_publish`` rows from its
    publish manifest.  No file is ever touched by this module.
    """
    if isinstance(paths, (str, bytes)) or not isinstance(paths, Iterable):
        raise ContractValidationError("paths must be an iterable of strings")
    items = tuple(paths)
    scan = scan_artifacts(items)
    allowed = make_allowlist(()) if allowlist is None else make_allowlist(allowlist)
    result: list[Disposition] = []
    for canonical in sorted(set(_canonical_path(item) for item in items)):
        if canonical in scan.artifacts:
            result.append(Disposition(canonical, ACTION_IGNORE,
                                      "verification/build artifact"))
        elif canonical in allowed.entries:
            result.append(Disposition(canonical, ACTION_PUBLISH,
                                      "explicitly allowlisted"))
        else:
            result.append(Disposition(canonical, ACTION_EXCLUDE_FROM_PUBLISH,
                                      "not in publish allowlist"))
    if any(item.action not in _VALID_ACTIONS or item.action in _FORBIDDEN_ACTIONS
           for item in result):
        raise ContractValidationError("disposition produced an unsafe action")
    return tuple(result)


def validate_artifact_scan(scan: Any, allowlist: Any) -> tuple[str, ...]:
    """Errors for an artifact allowlist scan; empty tuple means safe to publish."""
    if not isinstance(scan, ArtifactScan) or not isinstance(allowlist, ArtifactAllowlist):
        return ("artifact scan and allowlist are required",)
    errors: list[str] = []
    for entry in allowlist.entries:
        if classify_path(entry) != "source":
            errors.append("artifact in publish allowlist: %s" % entry)
        if "*" in entry or "?" in entry:
            errors.append("wildcard in publish allowlist: %s" % entry)
    for artifact in scan.artifacts:
        if artifact in allowlist.entries:
            errors.append("artifact in publish allowlist: %s" % artifact)
    return tuple(sorted(set(errors)))


def gitignore_patterns() -> tuple[str, ...]:
    """Ignore patterns a caller can place in its own .gitignore (no writes)."""
    return GITIGNORE_PATTERNS


# ===========================================================================
# Z4 -- crash-safe turn journal (in-memory, no real I/O)
# ===========================================================================

GENESIS_DIGEST = "genesis"
RECORD_TOOL_STARTED = "tool_started"
RECORD_TOOL_DONE = "tool_done"
_RECORD_KINDS = frozenset({RECORD_TOOL_STARTED, RECORD_TOOL_DONE})
MAX_JOURNAL_BYTES = 1_000_000
MAX_RECORD_BYTES = 65_536
MAX_RECORDS = 10_000
PROMPT_TEXT = "interrupted tool, retry or skip"
ACTION_RETRY = "retry"
ACTION_SKIP = "skip"

_STARTED_KEYS = frozenset({"seq", "kind", "turn_id", "tool_call_id", "name",
                           "args_digest", "prev", "digest"})
_DONE_KEYS = frozenset({"seq", "kind", "turn_id", "tool_call_id",
                        "result_digest", "prev", "digest"})


class RecoveryAction(str, Enum):
    """The two choices offered for an interrupted tool call."""

    RETRY = ACTION_RETRY
    SKIP = ACTION_SKIP

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class InterruptedTool:
    """A write-ahead tool_started whose tool_done never became durable."""

    turn_id: str
    tool_call_id: str
    name: str
    args_digest: str
    started_seq: int

    def as_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "args_digest": self.args_digest,
            "started_seq": self.started_seq,
            "actions": [ACTION_RETRY, ACTION_SKIP],
        }


@dataclass(frozen=True)
class RecoveryDescriptor:
    """The exact durable resume point after a simulated power loss."""

    seq: int
    records: tuple[dict, ...]
    interrupted: tuple[InterruptedTool, ...]
    durable_bytes: int
    tail_discarded: bool
    errors: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.tail_discarded and not self.errors and not self.interrupted

    def actions(self) -> dict[str, tuple[str, ...]]:
        return {item.tool_call_id: (ACTION_RETRY, ACTION_SKIP)
                for item in self.interrupted}

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "records": [dict(record) for record in self.records],
            "interrupted": [item.as_dict() for item in self.interrupted],
            "durable_bytes": self.durable_bytes,
            "tail_discarded": self.tail_discarded,
            "errors": list(self.errors),
            "clean": self.clean,
        }


class MemorySink:
    """An append-only in-memory byte sink: no file descriptor, no clock.

    Each call appends exactly one newline-terminated record (no embedded
    newline), modelling the single atomic write-ahead append.  A torn tail can
    only be produced by a caller truncating the snapshot before recovery.
    """

    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    def append(self, chunk: Any) -> None:
        data = _body_bytes(chunk, "journal chunk")
        if not data or b"\n" in data[:-1] or not data.endswith(b"\n"):
            raise ContractValidationError(
                "sink append must be exactly one newline-terminated record")
        self._chunks.append(data)

    def snapshot(self) -> bytes:
        return b"".join(self._chunks)

    def chunks(self) -> tuple[bytes, ...]:
        return tuple(self._chunks)


def _hex_digest(value: Any, label: str) -> str:
    digest = _text(value).strip()
    if not _HEX_DIGEST_RE.match(digest):
        raise ContractValidationError("%s must be a lowercase sha256 hex digest" % label)
    return digest


def _record_digest(record: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key != "digest"}
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _encode_record(record: Mapping[str, Any]) -> bytes:
    line = _canonical_bytes(record) + b"\n"
    if len(line) > MAX_RECORD_BYTES:
        raise ContractValidationError("journal record exceeds the size limit")
    return line


def _validate_record_shape(record: Any) -> dict:
    if not isinstance(record, Mapping):
        raise ContractValidationError("journal record must be an object")
    kind = record.get("kind")
    if kind == RECORD_TOOL_STARTED:
        expected = _STARTED_KEYS
    elif kind == RECORD_TOOL_DONE:
        expected = _DONE_KEYS
    else:
        raise ContractValidationError("unknown journal record kind: %s" % kind)
    if set(record) != expected:
        raise ContractValidationError("journal record fields do not match its kind")
    seq = record["seq"]
    if type(seq) is not int or not 1 <= seq <= MAX_RECORDS:
        raise ContractValidationError("journal record seq is out of range")
    value = {
        "seq": seq,
        "kind": kind,
        "turn_id": _named(record["turn_id"], "turn id"),
        "tool_call_id": _named(record["tool_call_id"], "tool call id"),
    }
    if kind == RECORD_TOOL_STARTED:
        value["name"] = _named(record["name"], "tool name")
        value["args_digest"] = _hex_digest(record["args_digest"], "args digest")
    else:
        value["result_digest"] = _hex_digest(record["result_digest"],
                                             "result digest")
    prev = _text(record["prev"])
    if prev != GENESIS_DIGEST and not _HEX_DIGEST_RE.match(prev):
        raise ContractValidationError("journal record prev digest is malformed")
    value["prev"] = prev
    value["digest"] = _hex_digest(record["digest"], "record digest")
    return value


def _validate_chain(records: Iterable[Mapping[str, Any]]) -> tuple[dict, ...]:
    accepted: list[dict] = []
    expected_seq = 1
    expected_prev = GENESIS_DIGEST
    for raw in records:
        record = _validate_record_shape(raw)
        if record["seq"] != expected_seq:
            raise ContractValidationError("journal seq gap at %d" % expected_seq)
        if record["prev"] != expected_prev:
            raise ContractValidationError("journal chain break at %d" % expected_seq)
        if record["digest"] != _record_digest(record):
            raise ContractValidationError("journal digest mismatch at %d" % expected_seq)
        accepted.append(record)
        expected_seq += 1
        expected_prev = record["digest"]
    return tuple(accepted)


class Journal:
    """Pure write-ahead journal backed by an in-memory :class:`MemorySink`."""

    def __init__(self, sink: Any = None):
        self._sink = sink if isinstance(sink, MemorySink) else MemorySink()
        self._records: tuple[dict, ...] = ()
        self._pending: dict[str, dict] = {}

    @classmethod
    def from_records(cls, records: Iterable[Mapping[str, Any]]) -> "Journal":
        journal = cls()
        for record in _validate_chain(records):
            journal._commit(record)
        return journal

    def _next_base(self) -> tuple[int, str]:
        seq = len(self._records) + 1
        if seq > MAX_RECORDS:
            raise ContractValidationError("journal record limit exceeded")
        prev = self._records[-1]["digest"] if self._records else GENESIS_DIGEST
        return seq, prev

    def _commit(self, record: Mapping[str, Any]) -> None:
        line = _encode_record(record)
        if len(self._sink.snapshot()) + len(line) > MAX_JOURNAL_BYTES:
            raise ContractValidationError("journal byte limit exceeded")
        self._sink.append(line)
        self._records = self._records + (dict(record),)
        if record["kind"] == RECORD_TOOL_STARTED:
            self._pending[record["tool_call_id"]] = dict(record)
        else:
            self._pending.pop(record["tool_call_id"], None)

    def begin_tool(self, turn_id: Any, tool_call_id: Any, name: Any,
                   args_digest: Any) -> str:
        """Write the write-ahead record *before* a tool is started."""
        turn = _named(turn_id, "turn id")
        call = _named(tool_call_id, "tool call id")
        tool = _named(name, "tool name")
        args = _hex_digest(args_digest, "args digest")
        if call in self._pending:
            raise ContractValidationError("tool call is already pending: %s" % call)
        seq, prev = self._next_base()
        record = {
            "seq": seq, "kind": RECORD_TOOL_STARTED,
            "turn_id": turn, "tool_call_id": call, "name": tool,
            "args_digest": args, "prev": prev,
        }
        record["digest"] = _record_digest(record)
        self._commit(record)
        return record["digest"]

    def finish_tool(self, tool_call_id: Any, result_digest: Any) -> str:
        """Mark a pending tool call done *after* its result is available."""
        call = _named(tool_call_id, "tool call id")
        result = _hex_digest(result_digest, "result digest")
        started = self._pending.get(call)
        if started is None:
            raise ContractValidationError("tool call is not pending: %s" % call)
        seq, prev = self._next_base()
        record = {
            "seq": seq, "kind": RECORD_TOOL_DONE,
            "turn_id": started["turn_id"], "tool_call_id": call,
            "result_digest": result, "prev": prev,
        }
        record["digest"] = _record_digest(record)
        self._commit(record)
        return record["digest"]

    def records(self) -> tuple[dict, ...]:
        return tuple(dict(record) for record in self._records)

    def pending_tool_calls(self) -> tuple[str, ...]:
        return tuple(sorted(self._pending))

    def bytes(self) -> bytes:
        """The durable snapshot the caller may persist through its own layer."""
        return self._sink.snapshot()

    def as_dict(self) -> dict:
        return {"records": [dict(record) for record in self._records],
                "pending": list(self.pending_tool_calls())}


def recover(stream: Any) -> RecoveryDescriptor:
    """Parse a journal snapshot into the exact durable resume point.

    Parsing stops at the first incomplete, corrupt or out-of-order record; the
    remainder is reported as a discarded tail rather than being silently
    skipped.  This is what makes the append atomic: a torn ``tool_done`` leaves
    its ``tool_started`` pending, so recovery offers "retry or skip".
    """
    data = _body_bytes(stream, "journal stream")
    if len(data) > MAX_JOURNAL_BYTES:
        raise ContractValidationError("journal stream exceeds the size limit")
    if not data:
        return RecoveryDescriptor(0, (), (), 0, False, ())

    parts = data.split(b"\n")
    ended_with_newline = parts[-1] == b""
    if ended_with_newline:
        parts = parts[:-1]

    accepted: list[dict] = []
    pending: dict[str, dict] = {}
    errors: list[str] = []
    tail_discarded = False
    expected_seq = 1
    expected_prev = GENESIS_DIGEST

    for index, line in enumerate(parts):
        location = "line %d" % (index + 1)
        if not line:
            tail_discarded = True
            errors.append("empty journal record at %s" % location)
            break
        if len(line) > MAX_RECORD_BYTES:
            tail_discarded = True
            errors.append("oversized journal record at %s" % location)
            break
        try:
            parsed = json.loads(line.decode("utf-8"))
            record = _validate_record_shape(parsed)
        except (ValueError, UnicodeDecodeError, ContractValidationError) as exc:
            tail_discarded = True
            errors.append("invalid journal record at %s: %s" % (location, exc))
            break

        problems: list[str] = []
        if record["seq"] != expected_seq:
            problems.append("seq gap at %s" % location)
        if record["prev"] != expected_prev:
            problems.append("chain break at %s" % location)
        if record["digest"] != _record_digest(record):
            problems.append("digest mismatch at %s" % location)
        if len(accepted) >= MAX_RECORDS:
            problems.append("journal record limit exceeded at %s" % location)
        if record["kind"] == RECORD_TOOL_STARTED:
            if record["tool_call_id"] in pending:
                problems.append("duplicate tool start at %s" % location)
        elif record["tool_call_id"] not in pending:
            problems.append("tool done without start at %s" % location)
        if problems:
            tail_discarded = True
            errors.extend(problems)
            break

        if record["kind"] == RECORD_TOOL_STARTED:
            pending[record["tool_call_id"]] = record
        else:
            pending.pop(record["tool_call_id"], None)
        accepted.append(record)
        expected_seq += 1
        expected_prev = record["digest"]

    consumed = 0
    for index, line in enumerate(parts[:len(accepted)]):
        has_newline = index < len(parts) - 1 or ended_with_newline
        consumed += len(line) + (1 if has_newline else 0)
    durable_bytes = min(consumed, len(data))

    interrupted = tuple(sorted(
        (InterruptedTool(
            turn_id=record["turn_id"],
            tool_call_id=record["tool_call_id"],
            name=record["name"],
            args_digest=record["args_digest"],
            started_seq=record["seq"],
        ) for record in pending.values()),
        key=lambda item: item.started_seq,
    ))
    return RecoveryDescriptor(
        seq=len(accepted),
        records=tuple(accepted),
        interrupted=interrupted,
        durable_bytes=durable_bytes,
        tail_discarded=tail_discarded,
        errors=tuple(errors),
    )


def interrupted_tool_prompt(descriptor: Any) -> str:
    """Render the exact restart prompt for every interrupted tool call."""
    if not isinstance(descriptor, RecoveryDescriptor):
        raise ContractValidationError("prompt needs a RecoveryDescriptor")
    if not descriptor.interrupted:
        return ""
    lines = [PROMPT_TEXT + ":"]
    for item in descriptor.interrupted:
        lines.append("- %s (turn %s, tool %s, seq %d, args %s): %s / %s" % (
            item.tool_call_id, item.turn_id, item.name, item.started_seq,
            item.args_digest, ACTION_RETRY, ACTION_SKIP))
    return "\n".join(lines)


def resume_journal(stream: Any) -> Journal:
    """Rebuild a journal from only the durable records; no I/O is performed."""
    return Journal.from_records(recover(stream).records)


__all__ = [
    "FEATURE_IDS",
    "SIGNATURE_HEADER", "TIMESTAMP_HEADER", "SIGNATURE_ALGORITHM",
    "DEFAULT_MAX_AGE_SECONDS", "MAX_WEBHOOK_AGE_SECONDS", "MAX_TIMESTAMP",
    "STATUS_ACCEPT", "STATUS_REJECT",
    "REASON_ACCEPTED", "REASON_NO_SECRET", "REASON_INVALID_REQUEST",
    "REASON_INVALID_HEADER", "REASON_AMBIGUOUS_HEADER",
    "REASON_MISSING_SIGNATURE", "REASON_MISSING_TIMESTAMP",
    "REASON_BAD_SIGNATURE", "REASON_BAD_TIMESTAMP", "REASON_STALE_TIMESTAMP",
    "REQUIRED_EVIDENCE_DOCS", "OUT_OF_SCOPE_DOCS",
    "STATUS_MAPPED", "STATUS_UNCOVERED", "STATUS_MISSING", "STATUS_EMPTY",
    "ARTIFACT_DIR_PREFIX", "ARTIFACT_DIR_NAMES", "GITIGNORE_PATTERNS",
    "ACTION_PUBLISH", "ACTION_IGNORE", "ACTION_EXCLUDE_FROM_PUBLISH",
    "GENESIS_DIGEST", "RECORD_TOOL_STARTED", "RECORD_TOOL_DONE",
    "MAX_JOURNAL_BYTES", "MAX_RECORD_BYTES", "MAX_RECORDS", "PROMPT_TEXT",
    "ACTION_RETRY", "ACTION_SKIP",
    "ArtifactAllowlist", "ArtifactScan", "ContractError",
    "ContractValidationError", "CrossWalk", "CrossWalkRow", "Disposition",
    "InterruptedTool", "Journal", "MemorySink", "RecoveryAction",
    "RecoveryDescriptor", "WebhookDecision", "WebhookVerifier",
    "artifact_disposition", "build_cross_walk", "classify_path",
    "cross_walk_dict", "filter_publishable",
    "gitignore_patterns", "interrupted_tool_prompt", "is_allowed",
    "is_publishable", "make_allowlist", "recover", "resume_journal",
    "scan_artifacts", "secret_configured", "sign_webhook", "validate_artifact_scan",
    "verify_cross_walk", "verify_evidence_documents", "verify_webhook",
    "webhook_headers",
]
