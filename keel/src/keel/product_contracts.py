"""Pure product-contract descriptors for four addendum-5 P0 rows.

This module is a *contract layer*, not an implementation of the underlying
runtime.  It validates, derives and compares caller-supplied data and returns
immutable descriptors.  It performs **no file I/O, no network, no subprocess,
no clock reads, no chance input and no secret storage**.  Every factory is
deterministic: equal inputs always produce equal descriptors.  Callers own the
bytes, bytes and sockets; this module only decides whether a proposed
descriptor is admissible.

Feature map (PLAN-INDEX.json, source: Addendum 5 "DeepSeek harness"):

* **W1.10** -- ``SAFETY.md`` surfaced as a first-run notice.  A *content check*
  validates the caller-supplied notice text (title, single version marker,
  sections, safe links, no credentials).  ``first_run_descriptor`` decides
  whether to show it; version and content digest are tracked like the EULA
  (C11.5), so a changed notice is shown again on the next run.
* **W4.3** -- OAuth for remote servers.  PKCE S256 challenge derivation,
  authorization-server discovery validation, bounded silent refresh, and
  credential references that live outside the project config.  A static
  ``Authorization`` header is authoritative: ``oauth:false`` header-key servers
  never enter an OAuth flow, and a conflict fails closed instead of silently
  falling back.  No token, client secret or key material is ever accepted or
  emitted -- only opaque references.
* **W6.1** -- Accuracy-over-approval response contract.  Claims carry a status,
  citations and an origin; finalization fails closed unless figures are
  verified, unknowns are stated plainly, and user-supplied numbers are paired
  with an independent estimate.  Ships a default ``PERSONA.md`` rigor section
  and a pure eval helper (V7).
* **W6.3** -- Anti-sycophancy rules: no praise of questions, immediate
  correction when the user is wrong, strongest counterargument first, no
  capitulation without new evidence.  The persona section keeps Keel's own
  safety messaging and Tier-2 behavior; the excluded "avoid all ethics /
  be aggressive" instruction is rejected by an explicit check.

Not implemented here: **W1.18** (MIT license / notices) is owner-gated and
conflicts with the proprietary license requirement; see
``OWNER_GATED_NOT_IMPLEMENTED``.

Security invariants (enforced by ``test_product_contracts``):

* unknown or malformed input fails closed with a typed ``ProductContractError``;
* error messages never carry credential material;
* no secret, token or keychain value survives into any descriptor or dict;
* all serialised rows are ``descriptor_only``, ``network=False``,
  ``runtime_claimed=False``.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

FEATURE_IDS: tuple[str, ...] = ("W1.10", "W4.3", "W6.1", "W6.3")
OWNER_GATED_NOT_IMPLEMENTED: tuple[str, ...] = ("W1.18",)


# ---------------------------------------------------------------------------
# Shared policy helpers and fail-closed errors
# ---------------------------------------------------------------------------

_CREDENTIAL_PREFIX_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9_\-]{8,}|"
    r"xox[baprs]-[A-Za-z0-9_\-]{8,}|AKIA[A-Z0-9]{8,}|AIza[A-Za-z0-9_\-]{8,})"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r'(?i)(?P<key>\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|'
    r'auth[_-]?token|client[_-]?secret|secret|password|passwd|credential|'
    r'authorization|bearer)\b)\s*[:=]\s*(?P<val>"[^"\n]*"|\'[^\'\n]*\'|[^\s,;}]+)'
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{6,}")
_PEM_RE = re.compile(
    r"(?s)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
_SAFE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/\-]{0,127}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9\-._~]{16,256}$")
_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


def _redact(value: Any) -> str:
    """Return text with literal credential material replaced."""
    text = "" if value is None else str(value)
    text = _PEM_RE.sub("[PRIVATE_KEY_REDACTED]", text)
    text = _CREDENTIAL_PREFIX_RE.sub("[REDACTED]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    return _SECRET_ASSIGNMENT_RE.sub(lambda m: "%s=[REDACTED]" % m.group("key"), text)


def looks_like_secret(value: Any) -> bool:
    """Best-effort detection of literal credential material in caller text."""
    text = "" if value is None else str(value)
    if not text:
        return False
    return bool(
        _CREDENTIAL_PREFIX_RE.search(text)
        or _BEARER_RE.search(text)
        or _SECRET_ASSIGNMENT_RE.search(text)
        or _PEM_RE.search(text)
    )


class ProductContractError(ValueError):
    """Fail-closed validation error.  Codes are stable; messages are redacted."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = _redact(detail)
        super().__init__(self.code if not detail else "[%s] %s" % (self.code, self.detail))


def _text(value: Any, label: str, *, limit: int = 4096, allow_empty: bool = False) -> str:
    """Validate a bounded, printable, secret-free text value."""
    if not isinstance(value, str):
        raise ProductContractError("bad_" + label)
    if not value.strip() and not allow_empty:
        raise ProductContractError("empty_" + label)
    if len(value) > limit:
        raise ProductContractError("oversized_" + label)
    if any((ord(ch) < 0x20 and ch not in "\n\t") or ord(ch) == 0x7F for ch in value):
        raise ProductContractError("control_char_in_" + label)
    if looks_like_secret(value):
        raise ProductContractError("secret_in_" + label)
    return value


def _safe_id(value: Any, label: str = "identifier") -> str:
    """Validate an opaque, safe identifier (never a path or a secret)."""
    text = _text(value, label, limit=256)
    if not _SAFE_ID_RE.match(text) or ".." in text:
        raise ProductContractError("unsafe_" + label)
    return text


def _strings(value: Any, label: str, *, limit: int = 64) -> tuple[str, ...]:
    """Normalise a sequence of unique, safe short tokens."""
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ProductContractError("bad_" + label)
    out: list[str] = []
    for item in value:
        token = _text(item, label, limit=128)
        if any(ch.isspace() for ch in token):
            raise ProductContractError("bad_" + label)
        if token not in out:
            out.append(token)
    if len(out) > limit:
        raise ProductContractError("too_many_" + label)
    return tuple(out)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_path(path: Any) -> str:
    """Pure lexical path normalisation (POSIX and Windows separators)."""
    raw = str(path or "").strip().replace("\\", "/")
    if any((ord(ch) < 0x20) or ord(ch) == 0x7F for ch in raw):
        raise ProductContractError("bad_path")
    drive = ""
    drive_match = re.match(r"^([A-Za-z]):", raw)
    if drive_match:
        drive = drive_match.group(1).lower() + ":"
        raw = raw[2:]
    absolute = raw.startswith("/")
    parts: list[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            else:
                parts.append("..")
            continue
        parts.append(part)
    prefix = drive + "/" if drive else ("/" if absolute else "")
    return prefix + "/".join(parts)


def _contained(path: Any, root: Any) -> bool:
    """Pure string containment check; both arguments are normalised first."""
    candidate = _normalize_path(path)
    anchor = _normalize_path(root)
    if not candidate or not anchor or ".." in candidate.split("/") \
            or ".." in anchor.split("/"):
        return False
    candidate = candidate.casefold()
    anchor = anchor.casefold().rstrip("/")
    return candidate == anchor or candidate.startswith(anchor + "/")


def _pct(value: Any) -> str:
    """Deterministic RFC 3986 percent-encoding of a single query component."""
    return "".join(
        chr(byte) if chr(byte) in _UNRESERVED else "%%%02X" % byte
        for byte in str(value).encode("utf-8")
    )


def _build_url(endpoint: str, params: Mapping[str, str]) -> str:
    query = "&".join("%s=%s" % (_pct(key), _pct(params[key]))
                     for key in sorted(params))
    return endpoint + ("&" if "?" in endpoint else "?") + query


def feature_descriptors() -> dict[str, dict[str, Any]]:
    """One uniform, honest summary row per implemented feature ID."""
    result: dict[str, dict[str, Any]] = {}
    contracts = {
        "W1.10": "SAFETY.md content check + versioned first-run notice descriptor",
        "W4.3": "OAuth PKCE/discovery/refresh + out-of-project credential refs",
        "W6.1": "accuracy-over-approval claim/citation finalization contract",
        "W6.3": "anti-sycophancy response checks + persona safety preservation",
    }
    for fid in FEATURE_IDS:
        result[fid] = {
            "layer": "descriptor_only",
            "io_performed": False,
            "network": False,
            "runtime_claimed": False,
            "secret_values": False,
            "contract": contracts[fid],
        }
    return result


# ===========================================================================
# W1.10 -- SAFETY.md first-run notice (descriptor + content check)
# ===========================================================================

SAFETY_FILENAME = "SAFETY.md"
MAX_SAFETY_BYTES = 64 * 1024
_SAFETY_VERSION_RE = re.compile(
    r"(?im)^[ \t]*version[ \t]*[:=][ \t]*(?P<version>[A-Za-z0-9][A-Za-z0-9._\-]{0,63})[ \t]*$"
)
_TITLE_RE = re.compile(r"(?im)^[ \t]*#[ \t]+(?P<title>.+?)[ \t]*$")
_SECTION_RE = re.compile(r"(?im)^[ \t]*##[ \t]+(?P<title>.+?)[ \t]*$")
_LINK_RE = re.compile(r"(?i)\]\((?P<target>[^)]*)\)")


@dataclass(frozen=True)
class SafetyNotice:
    """Validated content descriptor for the ``SAFETY.md`` notice."""

    version: str
    content_sha256: str
    title: str
    sections: tuple[str, ...]
    website_link: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": SAFETY_FILENAME,
            "version": self.version,
            "content_sha256": self.content_sha256,
            "title": self.title,
            "sections": list(self.sections),
            "website_link": self.website_link,
            "io_performed": False,
        }


def _validate_link(target: Any) -> str:
    """Validate a markdown link target without resolving or fetching it."""
    text = str(target or "").strip()
    if not text or any(ch.isspace() for ch in text):
        raise ProductContractError("bad_notice_link")
    lowered = text.casefold()
    if lowered.startswith(("javascript:", "data:", "file:", "vbscript:")):
        raise ProductContractError("unsafe_notice_link")
    if lowered.startswith(("http://", "https://")):
        try:
            validate_endpoint_url(text, "notice_link")
        except ProductContractError as exc:
            raise ProductContractError("unsafe_notice_link", exc.code) from exc
        return text
    if text.startswith("//"):
        raise ProductContractError("unsafe_notice_link")
    segments = text.split("/")
    if any(part == ".." for part in segments) or "\\" in text:
        raise ProductContractError("unsafe_notice_link")
    return text


def validate_safety_notice_text(text: Any) -> tuple[str, ...]:
    """Return every reason ``text`` is not a valid ``SAFETY.md`` notice."""
    if not isinstance(text, str):
        return ("safety notice content must be text",)
    errors: list[str] = []
    if not text.strip():
        errors.append("safety notice content must not be empty")
    if len(text.encode("utf-8", errors="replace")) > MAX_SAFETY_BYTES:
        errors.append("safety notice content exceeds 64 KiB")
    if any((ord(ch) < 0x20 and ch not in "\n\t") or ord(ch) == 0x7F for ch in text):
        errors.append("safety notice content contains control characters")
    if looks_like_secret(text):
        errors.append("safety notice content must not contain credentials")

    titles = [match.group("title").strip() for match in _TITLE_RE.finditer(text)]
    if not titles:
        errors.append("safety notice needs a level-one title")
    elif not any("safety" in title.casefold() for title in titles):
        errors.append("safety notice title must mention safety")

    versions = [match.group("version") for match in _SAFETY_VERSION_RE.finditer(text)]
    if not versions:
        errors.append("safety notice needs a Version: marker")
    elif len(versions) > 1:
        errors.append("safety notice has more than one Version: marker")

    sections = [match.group("title").strip() for match in _SECTION_RE.finditer(text)]
    if not sections:
        errors.append("safety notice needs at least one section")
    if any(not section for section in sections):
        errors.append("safety notice sections must have titles")

    for match in _LINK_RE.finditer(text):
        try:
            _validate_link(match.group("target"))
        except ProductContractError as exc:
            errors.append("notice link: %s" % exc.code)
    return tuple(dict.fromkeys(errors))


def safety_notice_descriptor(
    text: Any, *, website_link: str = "/safety"
) -> SafetyNotice:
    """Validate notice text and return its immutable descriptor."""
    errors = validate_safety_notice_text(text)
    if errors:
        raise ProductContractError("invalid_safety_notice", "; ".join(errors))
    title = next(match.group("title").strip()
                 for match in _TITLE_RE.finditer(text)
                 if "safety" in match.group("title").casefold())
    version = _SAFETY_VERSION_RE.search(text).group("version")
    sections = tuple(match.group("title").strip() for match in _SECTION_RE.finditer(text))
    return SafetyNotice(
        version=version,
        content_sha256=_digest(text),
        title=title,
        sections=sections,
        website_link=_validate_link(website_link),
    )


@dataclass(frozen=True)
class SafetyNoticeState:
    """Pure acknowledgement state; callers persist it through their own store."""

    acknowledged_version: str | None = None
    acknowledged_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "acknowledged_version": self.acknowledged_version,
            "acknowledged_digest": self.acknowledged_digest,
        }


def validate_notice_state(state: Any) -> tuple[str, ...]:
    errors: list[str] = []
    if not isinstance(state, SafetyNoticeState):
        return ("notice state must be a SafetyNoticeState",)
    version, digest = state.acknowledged_version, state.acknowledged_digest
    if version is not None and (not isinstance(version, str) or not version):
        errors.append("acknowledged version must be a non-empty string or None")
    if digest is not None:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append("acknowledged digest must be a sha256 hex string or None")
    if version is None and digest is not None:
        errors.append("a digest cannot be acknowledged without a version")
    return tuple(errors)


def notice_reason(state: SafetyNoticeState | None, notice: SafetyNotice) -> str:
    """Return ``first_run``, ``version_changed``, ``content_changed`` or ``acknowledged``."""
    if not isinstance(notice, SafetyNotice):
        raise ProductContractError("bad_safety_notice")
    if state is None:
        return "first_run"
    errors = validate_notice_state(state)
    if errors:
        raise ProductContractError("invalid_notice_state", "; ".join(errors))
    if state.acknowledged_version is None:
        return "first_run"
    if state.acknowledged_version != notice.version:
        return "version_changed"
    if state.acknowledged_digest != notice.content_sha256:
        return "content_changed"
    return "acknowledged"


def needs_notice(state: SafetyNoticeState | None, notice: SafetyNotice) -> bool:
    """True on first run and whenever the version or content changed."""
    return notice_reason(state, notice) != "acknowledged"


def first_run_descriptor(
    notice: SafetyNotice, state: SafetyNoticeState | None = None
) -> dict[str, Any]:
    """Describe the in-app notice that must be surfaced before a run."""
    reason = notice_reason(state, notice)
    return {
        "filename": SAFETY_FILENAME,
        "show": reason != "acknowledged",
        "first_run": reason == "first_run",
        "reason": reason,
        "version": notice.version,
        "content_sha256": notice.content_sha256,
        "website_link": notice.website_link,
        "io_performed": False,
    }


def acknowledge_notice(
    state: SafetyNoticeState | None, notice: SafetyNotice
) -> SafetyNoticeState:
    """Return a new state acknowledging this exact version and content."""
    notice_reason(state, notice)  # validates both arguments
    return SafetyNoticeState(notice.version, notice.content_sha256)


def decline_notice(state: SafetyNoticeState | None) -> SafetyNoticeState:
    """Clear acknowledgement; the next run is a first run again."""
    if state is not None:
        errors = validate_notice_state(state)
        if errors:
            raise ProductContractError("invalid_notice_state", "; ".join(errors))
    return SafetyNoticeState()


# ===========================================================================
# W4.3 -- OAuth for remote servers (PKCE, discovery, refresh, credential refs)
# ===========================================================================

class AuthMode(str, Enum):
    HEADER = "header"
    OAUTH = "oauth"

    def __str__(self) -> str:
        return self.value


class RefreshAction(str, Enum):
    NONE = "none"
    REFRESH = "refresh"
    REAUTHENTICATE = "reauthenticate"

    def __str__(self) -> str:
        return self.value


LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "ip6-localhost"})
PKCE_METHOD = "S256"
MAX_REFRESH_ATTEMPTS = 1
SILENT_RETRY_LIMIT = 1
CREDENTIAL_STORES = frozenset({"keychain", "os-credential-store"})
CREDENTIAL_REF_PREFIX = "credential-ref:"

_URL_RE = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*)://(?P<authority>[^/?#]+)(?P<rest>[/?#].*)?$"
)
_HOST_RE = re.compile(
    r"^(?:\[(?P<v6>[^\]]+)\]|(?P<host>[A-Za-z0-9.\-]+))(?::(?P<port>\d{1,5}))?$"
)


def _split_url(url: Any, label: str) -> tuple[str, str, str, str]:
    """Pure URL parser; no DNS, no sockets, no request construction."""
    text = _text(url, label, limit=2048).strip()
    match = _URL_RE.match(text)
    if match is None:
        raise ProductContractError("bad_" + label)
    authority = match.group("authority")
    rest = match.group("rest") or ""
    if "@" in authority or rest.startswith("#"):
        raise ProductContractError("bad_" + label)
    host_match = _HOST_RE.match(authority)
    if host_match is None:
        raise ProductContractError("bad_" + label)
    host = (host_match.group("v6") or host_match.group("host") or "").casefold()
    if not host or ".." in host:
        raise ProductContractError("bad_" + label)
    port = host_match.group("port") or ""
    if port and not (1 <= int(port) <= 65535):
        raise ProductContractError("bad_" + label)
    scheme = match.group("scheme").casefold()
    if scheme not in ("http", "https"):
        raise ProductContractError("unsupported_" + label + "_scheme")
    if scheme == "http" and host not in LOOPBACK_HOSTS:
        raise ProductContractError("insecure_" + label)
    return scheme, host, port, rest


def validate_endpoint_url(url: Any, label: str = "endpoint") -> str:
    """Require HTTPS, or HTTP only on a loopback host.  Never opens a socket."""
    _split_url(url, label)
    return str(url).strip()


def _origin(url: Any, label: str) -> tuple[str, str, str]:
    scheme, host, port, _ = _split_url(url, label)
    return scheme, host, port or ("443" if scheme == "https" else "80")


@dataclass(frozen=True)
class PkceChallenge:
    """The public half of a PKCE exchange.  The verifier is never retained."""

    challenge: str
    method: str = PKCE_METHOD
    verifier_length: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "code_challenge": self.challenge,
            "code_challenge_method": self.method,
            "verifier_length": self.verifier_length,
            "verifier_retained": False,
        }


def pkce_challenge(verifier: Any, *, method: str = PKCE_METHOD) -> PkceChallenge:
    """Derive the RFC 7636 S256 challenge from a caller-supplied verifier."""
    if method != PKCE_METHOD:
        raise ProductContractError("plain_pkce_rejected")
    if not isinstance(verifier, str) or not (43 <= len(verifier) <= 128):
        raise ProductContractError("bad_pkce_verifier_length")
    if not re.fullmatch(r"[A-Za-z0-9\-._~]{43,128}", verifier):
        raise ProductContractError("bad_pkce_verifier_chars")
    if looks_like_secret(verifier):
        raise ProductContractError("secret_in_pkce_verifier")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PkceChallenge(challenge=challenge, method=PKCE_METHOD,
                         verifier_length=len(verifier))


@dataclass(frozen=True)
class AuthorizationServerMetadata:
    """Validated discovery metadata (endpoints only, no secrets)."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    pkce_methods: tuple[str, ...]
    grant_types: tuple[str, ...]
    response_types: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "code_challenge_methods_supported": list(self.pkce_methods),
            "grant_types_supported": list(self.grant_types),
            "response_types_supported": list(self.response_types),
            "secrets_included": False,
        }


def validate_discovery_document(
    metadata: Any, *, server_url: Any
) -> AuthorizationServerMetadata:
    """Validate caller-supplied discovery data; fail closed on anything missing."""
    if not isinstance(metadata, Mapping):
        raise ProductContractError("bad_discovery_document")
    _split_url(server_url, "server_url")
    for key, value in metadata.items():
        if looks_like_secret(value):
            raise ProductContractError("secret_in_discovery", str(key))
    issuer = _text(metadata.get("issuer"), "issuer", limit=2048).strip()
    _, _, _, issuer_rest = _split_url(issuer, "issuer")
    if issuer_rest.startswith(("?", "#")):
        raise ProductContractError("bad_issuer")
    if _origin(issuer, "issuer") != _origin(server_url, "server_url"):
        raise ProductContractError("issuer_origin_mismatch")
    auth_endpoint = validate_endpoint_url(metadata.get("authorization_endpoint"),
                                          "authorization_endpoint")
    token_endpoint = validate_endpoint_url(metadata.get("token_endpoint"),
                                           "token_endpoint")

    methods = _strings(metadata.get("code_challenge_methods_supported"), "pkce_methods")
    if PKCE_METHOD not in methods:
        raise ProductContractError("s256_not_supported")
    grants = _strings(metadata.get("grant_types_supported"), "grant_types")
    required_grants = {"authorization_code", "refresh_token"}
    if not required_grants <= set(grants):
        raise ProductContractError("missing_required_grants")
    raw_responses = metadata.get("response_types_supported", ("code",))
    responses = _strings(raw_responses, "response_types")
    if "code" not in responses:
        raise ProductContractError("code_response_not_supported")
    return AuthorizationServerMetadata(
        issuer=issuer, authorization_endpoint=auth_endpoint,
        token_endpoint=token_endpoint, pkce_methods=methods,
        grant_types=grants, response_types=responses,
    )


@dataclass(frozen=True)
class CredentialRef:
    """An opaque pointer to a credential held outside the project."""

    store: str
    key: str
    outside_project: bool = True
    never_in_config: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "store": self.store,
            "key": self.key,
            "outside_project": self.outside_project,
            "never_in_config": self.never_in_config,
            "credential_value": None,
        }


def credential_ref(store: Any, key: Any) -> CredentialRef:
    """Build a keychain-style reference; literal secrets are rejected."""
    store_text = _text(store, "credential_store", limit=64).strip().casefold()
    if store_text not in CREDENTIAL_STORES:
        raise ProductContractError("unknown_credential_store")
    key_text = _safe_id(key, "credential_key")
    if key_text.startswith("/") or re.match(r"^[A-Za-z]:", key_text):
        raise ProductContractError("credential_key_must_be_opaque")
    return CredentialRef(store=store_text, key=key_text)


def credential_ref_from_config(value: Any) -> CredentialRef:
    """Read an opaque ``credential-ref:`` marker from a config value."""
    if isinstance(value, CredentialRef):
        return value
    if isinstance(value, Mapping):
        candidate = value.get("$credentialRef", value.get("ref"))
    elif isinstance(value, str):
        candidate = value[len(CREDENTIAL_REF_PREFIX):] \
            if value.startswith(CREDENTIAL_REF_PREFIX) else None
    else:
        candidate = None
    if not isinstance(candidate, str) or not candidate:
        raise ProductContractError("literal_credential_in_config")
    return credential_ref("keychain", candidate)


_SECRET_CONFIG_KEYS = frozenset({
    "authorization", "client_secret", "token", "access_token", "refresh_token",
    "api_key", "password", "secret", "credentials",
})


def assert_no_credentials_in_config(config: Any) -> None:
    """Fail closed if a remote-server config embeds literal credential values."""
    if config is None:
        return
    if not isinstance(config, Mapping):
        raise ProductContractError("bad_server_config")

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                name = str(key).strip().casefold().replace("-", "_")
                if name in _SECRET_CONFIG_KEYS:
                    if isinstance(item, CredentialRef):
                        continue
                    if isinstance(item, Mapping) and (
                        "$credentialRef" in item or "ref" in item
                    ):
                        credential_ref_from_config(item)
                        continue
                    if isinstance(item, str) and item.startswith(CREDENTIAL_REF_PREFIX):
                        credential_ref_from_config(item)
                        continue
                    raise ProductContractError("literal_credential_in_config", name)
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, str) and looks_like_secret(value):
            raise ProductContractError("literal_credential_in_config")

    walk(config)


def assert_credential_store_outside_project(store_path: Any, project_root: Any) -> str:
    """Verify a caller-supplied store location is outside the project tree."""
    try:
        candidate = _normalize_path(store_path)
        root = _normalize_path(project_root)
    except ProductContractError as exc:
        raise ProductContractError("bad_store_path", exc.code) from exc
    if not candidate or not candidate.startswith(("/", "c:", "d:")):
        raise ProductContractError("credential_store_must_be_absolute")
    if _contained(candidate, root):
        raise ProductContractError("credential_store_inside_project")
    return candidate


@dataclass(frozen=True)
class OAuthFlowDescriptor:
    """Authorization-request descriptor.  Contains no token or client secret."""

    server: str
    metadata: AuthorizationServerMetadata
    redirect_uri: str
    client_id: str
    state: str
    scopes: tuple[str, ...]
    challenge: PkceChallenge
    authorization_url: str
    credential: CredentialRef
    client_secret_ref: CredentialRef | None = None
    retry_after_refresh_limit: int = SILENT_RETRY_LIMIT

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "server": self.server,
            "authorization_url": self.authorization_url,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "state": self.state,
            "scope": list(self.scopes),
            "token_endpoint": self.metadata.token_endpoint,
            "pkce": self.challenge.to_dict(),
            "credential": self.credential.to_dict(),
            "retry_after_refresh_limit": self.retry_after_refresh_limit,
            "network": False,
            "secret_values": False,
        }
        if self.client_secret_ref is not None:
            result["client_secret_ref"] = self.client_secret_ref.to_dict()
        return result


def oauth_flow_descriptor(
    server: Any,
    metadata: AuthorizationServerMetadata,
    *,
    redirect_uri: Any,
    client_id: Any,
    verifier: Any,
    state: Any,
    scope: Any = (),
    credential: CredentialRef | None = None,
    client_secret: Any = None,
) -> OAuthFlowDescriptor:
    """Build a PKCE authorization descriptor (data only, no network)."""
    server_id = _safe_id(server, "server")
    if not isinstance(metadata, AuthorizationServerMetadata):
        raise ProductContractError("bad_authorization_server_metadata")
    if client_secret is not None and not isinstance(client_secret, CredentialRef):
        raise ProductContractError("client_secret_must_be_keychain_ref")
    client = _safe_id(client_id, "client_id")
    redirect = validate_endpoint_url(redirect_uri, "redirect_uri")
    _, _, _, redirect_rest = _split_url(redirect, "redirect_uri")
    if not redirect_rest.startswith("/") or redirect_rest == "/":
        raise ProductContractError("bad_redirect_uri")
    state_text = _text(state, "state", limit=256).strip()
    if not _SAFE_TOKEN_RE.fullmatch(state_text):
        raise ProductContractError("bad_oauth_state")
    scopes = _strings(scope, "scope")
    challenge = pkce_challenge(verifier)
    credential_ref_value = credential or credential_ref(
        "keychain", "keel/mcp/%s/oauth" % server_id
    )
    if not isinstance(credential_ref_value, CredentialRef):
        raise ProductContractError("bad_credential_ref")
    params = {
        "response_type": "code",
        "client_id": client,
        "redirect_uri": redirect,
        "scope": " ".join(scopes),
        "state": state_text,
        "code_challenge": challenge.challenge,
        "code_challenge_method": challenge.method,
    }
    return OAuthFlowDescriptor(
        server=server_id,
        metadata=metadata,
        redirect_uri=redirect,
        client_id=client,
        state=state_text,
        scopes=scopes,
        challenge=challenge,
        authorization_url=_build_url(metadata.authorization_endpoint, params),
        credential=credential_ref_value,
        client_secret_ref=client_secret,
    )


@dataclass(frozen=True)
class RemoteAuthDescriptor:
    """The auth decision for one remote server (header key or OAuth)."""

    server: str
    url: str
    mode: AuthMode
    oauth_attempted: bool
    static_header_authoritative: bool
    credential: CredentialRef
    flow: OAuthFlowDescriptor | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "server": self.server,
            "url": self.url,
            "oauth": self.mode is AuthMode.OAUTH,
            "mode": self.mode.value,
            "oauth_attempted": self.oauth_attempted,
            "static_header_authoritative": self.static_header_authoritative,
            "credential": self.credential.to_dict(),
            "flow": self.flow.to_dict() if self.flow is not None else None,
            "network": False,
            "secret_values": False,
        }


def oauth_switch(config: Any) -> bool:
    """Read the ``oauth`` flag; a missing flag defaults to OAuth for remote servers."""
    if not isinstance(config, Mapping):
        raise ProductContractError("bad_server_config")
    if "oauth" not in config:
        return True
    value = config["oauth"]
    if not isinstance(value, bool):
        raise ProductContractError("bad_oauth_flag")
    return value


def remote_auth_descriptor(
    server: Any,
    url: Any,
    config: Mapping[str, Any],
    *,
    flow: OAuthFlowDescriptor | None = None,
) -> RemoteAuthDescriptor:
    """Resolve one remote server's auth mode from its config.

    ``oauth:false`` selects a header-key server.  A literal Authorization
    header or a header-key reference on an OAuth server is a conflict: it fails
    closed rather than silently downgrading a header-auth server into a flow
    the operator did not request.
    """
    server_id = _safe_id(server, "server")
    endpoint = validate_endpoint_url(url, "server_url")
    assert_no_credentials_in_config(config)
    use_oauth = oauth_switch(config)
    header_key = config.get("headerKeyRef", config.get("header_key_ref"))
    if not use_oauth:
        if flow is not None:
            raise ProductContractError("oauth_disabled_with_flow")
        if header_key is None:
            raise ProductContractError("header_server_needs_key_ref")
        ref = credential_ref_from_config(header_key)
        return RemoteAuthDescriptor(
            server=server_id, url=endpoint, mode=AuthMode.HEADER,
            oauth_attempted=False, static_header_authoritative=True,
            credential=ref, flow=None,
        )
    if header_key is not None:
        raise ProductContractError("header_auth_takes_precedence")
    if not isinstance(flow, OAuthFlowDescriptor) or flow.server != server_id:
        raise ProductContractError("missing_or_mismatched_oauth_flow")
    return RemoteAuthDescriptor(
        server=server_id, url=endpoint, mode=AuthMode.OAUTH,
        oauth_attempted=True, static_header_authoritative=False,
        credential=flow.credential, flow=flow,
    )


@dataclass(frozen=True)
class TokenState:
    """Metadata about a stored token.  Never carries the token value itself."""

    credential: CredentialRef
    expires_at: float | None = None
    scopes: tuple[str, ...] = ()
    refresh_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential": self.credential.to_dict(),
            "expires_at": self.expires_at,
            "scopes": list(self.scopes),
            "refresh_available": self.refresh_available,
            "token_value": None,
        }


def token_state(
    credential: CredentialRef,
    *,
    expires_at: Any = None,
    scopes: Any = (),
    refresh_available: bool = False,
) -> TokenState:
    """Build a token descriptor with metadata only."""
    if not isinstance(credential, CredentialRef):
        raise ProductContractError("bad_credential_ref")
    if expires_at is not None:
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)) \
                or expires_at < 0 or expires_at != expires_at or expires_at == float("inf"):
            raise ProductContractError("bad_expires_at")
    if not isinstance(refresh_available, bool):
        raise ProductContractError("bad_refresh_available")
    return TokenState(
        credential=credential, expires_at=expires_at,
        scopes=_strings(scopes, "token_scope"),
        refresh_available=refresh_available,
    )


@dataclass(frozen=True)
class RefreshDecision:
    action: RefreshAction
    reason: str
    attempts: int
    max_attempts: int = MAX_REFRESH_ATTEMPTS

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "network": False,
        }


def refresh_decision(
    state: TokenState, *, now: Any, attempts: int = 0
) -> RefreshDecision:
    """Decide whether to refresh, re-authenticate or do nothing (pure).

    At most one silent refresh is ever allowed; a second failure after that
    refresh must re-authenticate instead of looping against the token endpoint.
    """
    if not isinstance(state, TokenState):
        raise ProductContractError("bad_token_state")
    if isinstance(now, bool) or not isinstance(now, (int, float)) or now < 0 \
            or now != now or now == float("inf"):
        raise ProductContractError("bad_now")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        raise ProductContractError("bad_attempts")
    if state.expires_at is None:
        return RefreshDecision(RefreshAction.NONE, "no_expiry", attempts)
    if state.expires_at > now:
        return RefreshDecision(RefreshAction.NONE, "not_expired", attempts)
    if not state.refresh_available:
        return RefreshDecision(RefreshAction.REAUTHENTICATE, "no_refresh_token", attempts)
    if attempts >= MAX_REFRESH_ATTEMPTS:
        return RefreshDecision(RefreshAction.REAUTHENTICATE,
                               "refresh_limit_reached", attempts)
    return RefreshDecision(RefreshAction.REFRESH, "expired", attempts)


def assert_refresh_bounded(decisions: Sequence[RefreshDecision]) -> None:
    """Fail closed if a silent cycle ever asks for more than one refresh."""
    refreshes = [d for d in decisions or ()
                 if isinstance(d, RefreshDecision) and d.action is RefreshAction.REFRESH]
    if len(refreshes) > MAX_REFRESH_ATTEMPTS:
        raise ProductContractError("refresh_loop", "more than one silent refresh")


# ===========================================================================
# W6.1 -- accuracy-over-approval response contract
# ===========================================================================

class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    USER_SUPPLIED = "user_supplied"
    ESTIMATE = "estimate"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


CLAIM_ORIGINS = frozenset({"model", "user", "tool", "citation", "estimate"})
_CITATION_RE = re.compile(r"^(?:https?://|file:|tool:|doc:)[^\s]+$")
_UNKNOWN_MARKERS = (
    "unknown", "not verified", "cannot verify", "could not verify",
    "don't know", "do not know", "no source", "unverified",
)


def validate_citation(value: Any) -> str:
    """Validate a citation string without fetching it."""
    text = _text(value, "citation", limit=512).strip()
    if not _CITATION_RE.match(text):
        raise ProductContractError("bad_citation")
    if ".." in text or any(ord(ch) < 0x20 for ch in text):
        raise ProductContractError("bad_citation")
    if text.casefold().startswith(("http://", "https://")):
        try:
            validate_endpoint_url(text, "citation")
        except ProductContractError as exc:
            raise ProductContractError("bad_citation", exc.code) from exc
    return text


@dataclass(frozen=True)
class Claim:
    """One factual assertion with its evidence status and provenance."""

    text: str
    status: ClaimStatus
    sources: tuple[str, ...]
    topic: str
    value: str
    origin: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "status": self.status.value,
            "sources": list(self.sources),
            "topic": self.topic,
            "value": self.value,
            "origin": self.origin,
            "secret_values": False,
        }


def make_claim(
    text: Any,
    status: Any,
    *,
    sources: Any = (),
    topic: Any = "",
    value: Any = "",
    origin: Any = "model",
) -> Claim:
    """Build a validated claim; verification requires real citations."""
    claim_text = _text(text, "claim", limit=2048).strip()
    if isinstance(status, ClaimStatus):
        resolved = status
    else:
        try:
            resolved = ClaimStatus(str(status or "").strip().casefold())
        except ValueError as exc:
            raise ProductContractError("bad_claim_status") from exc
    source_tuple = tuple(validate_citation(item) for item in _strings(sources, "sources"))
    origin_text = _text(origin, "claim_origin", limit=64).strip().casefold()
    if origin_text not in CLAIM_ORIGINS:
        raise ProductContractError("bad_claim_origin")
    topic_text = _text(topic, "claim_topic", limit=128, allow_empty=True).strip()
    value_text = _text(value, "claim_value", limit=64, allow_empty=True).strip()
    if resolved is ClaimStatus.VERIFIED:
        if not source_tuple:
            raise ProductContractError("verified_claim_needs_source")
        if origin_text == "user":
            raise ProductContractError("user_assertion_not_verification")
    if resolved is ClaimStatus.UNKNOWN and source_tuple:
        raise ProductContractError("unknown_claim_has_sources")
    if resolved is ClaimStatus.ESTIMATE and not topic_text:
        raise ProductContractError("estimate_needs_topic")
    return Claim(
        text=claim_text, status=resolved, sources=source_tuple,
        topic=topic_text, value=value_text, origin=origin_text,
    )


def validate_claim(claim: Any) -> tuple[str, ...]:
    """Return every reason a directly-constructed claim is malformed."""
    if not isinstance(claim, Claim):
        return ("claim must be a Claim",)
    errors: list[str] = []
    if not isinstance(claim.text, str) or not claim.text.strip():
        errors.append("claim text must be non-empty")
    if not isinstance(claim.status, ClaimStatus):
        errors.append("claim status must be a known ClaimStatus")
    if not isinstance(claim.sources, tuple) or any(
            not isinstance(source, str) or not source for source in claim.sources):
        errors.append("claim sources must be citation strings")
    if not isinstance(claim.topic, str) or not isinstance(claim.value, str):
        errors.append("claim topic and value must be text")
    if claim.origin not in CLAIM_ORIGINS:
        errors.append("claim origin must be a known origin")
    if claims_like_secret(claim):
        errors.append("claim must not carry credential material")
    return tuple(dict.fromkeys(errors))


def claims_like_secret(claim: Claim) -> bool:
    """Best-effort scan of every textual field of a claim."""
    return any(looks_like_secret(value) for value in (
        claim.text, claim.topic, claim.value, *tuple(claim.sources),
    ))


def _numeric(value: Any) -> bool:
    text = str(value or "")
    return bool(re.search(r"\d", text))


def _has_unknown_marker(text: Any) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _UNKNOWN_MARKERS)


@dataclass(frozen=True)
class ResponseDraft:
    """A candidate final response plus the evidence used to produce it."""

    text: str
    claims: tuple[Claim, ...]
    user_premise: str
    user_wrong: bool | None
    strongest_counterargument: str
    pushback: bool
    new_evidence: tuple[str, ...]
    position_changed: bool
    acknowledged_unknowns: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "claims": [claim.to_dict() for claim in self.claims],
            "user_premise": self.user_premise,
            "user_wrong": self.user_wrong,
            "strongest_counterargument": self.strongest_counterargument,
            "pushback": self.pushback,
            "new_evidence": list(self.new_evidence),
            "position_changed": self.position_changed,
            "acknowledged_unknowns": list(self.acknowledged_unknowns),
        }


def make_response_draft(
    text: Any,
    *,
    claims: Any = (),
    user_premise: Any = "",
    user_wrong: bool | None = None,
    strongest_counterargument: Any = "",
    pushback: bool = False,
    new_evidence: Any = (),
    position_changed: bool = False,
    acknowledged_unknowns: Any = (),
) -> ResponseDraft:
    """Build a validated response draft; no claim is inferred implicitly."""
    body = _text(text, "response", limit=32 * 1024).strip()
    if isinstance(claims, Claim):
        claim_tuple = (claims,)
    elif claims is None or isinstance(claims, (str, bytes)) or not isinstance(claims, Sequence):
        raise ProductContractError("bad_claims")
    else:
        claim_tuple = tuple(claims)
    for claim in claim_tuple:
        errors = validate_claim(claim)
        if errors:
            raise ProductContractError("bad_claims", "; ".join(errors))
    if user_wrong is not None and not isinstance(user_wrong, bool):
        raise ProductContractError("bad_user_wrong")
    for flag, label in ((pushback, "pushback"), (position_changed, "position_changed")):
        if not isinstance(flag, bool):
            raise ProductContractError("bad_" + label)
    return ResponseDraft(
        text=body,
        claims=claim_tuple,
        user_premise=_text(user_premise, "user_premise", limit=2048,
                           allow_empty=True).strip(),
        user_wrong=user_wrong,
        strongest_counterargument=_text(
            strongest_counterargument, "counterargument", limit=2048,
            allow_empty=True).strip(),
        pushback=pushback,
        new_evidence=_strings(new_evidence, "new_evidence"),
        position_changed=position_changed,
        acknowledged_unknowns=_strings(acknowledged_unknowns, "unknowns"),
    )


def check_accuracy(draft: ResponseDraft) -> tuple[str, ...]:
    """W6.1: return every reason this draft cannot be finalized as truthful."""
    if not isinstance(draft, ResponseDraft):
        return ("response draft must be a ResponseDraft",)
    errors: list[str] = []
    user_figures: list[Claim] = []
    has_unknown = False
    for claim in draft.claims:
        for error in validate_claim(claim):
            errors.append(error)
        if claim.status is ClaimStatus.UNKNOWN:
            has_unknown = True
            if not _has_unknown_marker(claim.text) and claim.topic not in \
                    draft.acknowledged_unknowns:
                errors.append("unknown claim not stated plainly: %s" % claim.topic)
        if _numeric(claim.value):
            if claim.status is ClaimStatus.UNKNOWN:
                errors.append("unknown value must not be presented as a figure")
            if claim.origin == "user":
                user_figures.append(claim)
    for claim in user_figures:
        independent = [
            other for other in draft.claims
            if other.status is ClaimStatus.ESTIMATE
            and other.topic == claim.topic
            and other.origin != "user"
        ]
        if not independent:
            errors.append("user-supplied figure without independent estimate: %s"
                          % (claim.topic or "unnamed"))
    estimate_topics = {claim.topic for claim in draft.claims
                       if claim.status is ClaimStatus.ESTIMATE}
    for topic in estimate_topics:
        if not any(token in draft.text.casefold() for token in ("estimat", "approximately", "roughly")):
            errors.append("estimate not labelled in response: %s" % (topic or "unnamed"))
    if has_unknown and not _has_unknown_marker(draft.text):
        errors.append("response does not say unknown plainly")
    return tuple(dict.fromkeys(errors))


_PRAISE_RE = re.compile(
    r"(?i)\b(?:great|good|excellent|interesting|smart|brilliant|thoughtful|"
    r"nice|wonderful|fantastic|insightful)\s+"
    r"(?:point|question|observation|insight)\b"
)
_THANKS_QUESTION_RE = re.compile(
    r"(?i)\b(?:thanks for (?:asking|the (?:great|good) question)|"
    r"(?:i'?m|i am) glad you asked)\b"
)
_AGREEMENT_RE = re.compile(
    r"(?i)\b(?:as you (?:correctly|rightly) (?:pointed out|said)|"
    r"you'?re (?:absolutely |completely )?right|good catch)\b"
)
_CORRECTION_RE = re.compile(
    r"(?i)\b(?:actually|incorrect|not correct|that'?s wrong|this is wrong|"
    r"the premise is wrong|i disagree|false|no,)\b"
)


def _normalize_for_search(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


def check_anti_sycophancy(draft: ResponseDraft) -> tuple[str, ...]:
    """W6.3: return every reason this draft is sycophantic or evasive."""
    if not isinstance(draft, ResponseDraft):
        return ("response draft must be a ResponseDraft",)
    errors: list[str] = []
    body = draft.text
    if _PRAISE_RE.search(body) or _THANKS_QUESTION_RE.search(body):
        errors.append("praise_of_question")
    if draft.user_premise and draft.user_wrong is None:
        errors.append("user_correctness_not_assessed")
    if draft.user_wrong:
        opening = body[:240]
        if not _CORRECTION_RE.search(opening):
            errors.append("correction_not_immediate")
        if _AGREEMENT_RE.search(opening):
            errors.append("agreement_with_wrong_user")
        if not draft.strongest_counterargument:
            errors.append("missing_strongest_counterargument")
        elif _normalize_for_search(draft.strongest_counterargument) not in \
                _normalize_for_search(body):
            errors.append("counterargument_not_present_in_response")
    if draft.pushback and draft.position_changed and not draft.new_evidence:
        errors.append("capitulation_without_new_evidence")
    return tuple(errors)


PERSONA_RIGOR_SECTION = """\
<rigor-contract>
Verify before claiming done. A claim is only as strong as the evidence behind
it: cite the tool output or test result you observed in this turn. Separate
what you observed from what you assumed, and say which is which. Never invent
file contents, tool results, test outcomes, or external state. If a check was
not run, say so explicitly. When a verification command is available for the
project, run it after changes and report the result. Prefer a truthful
"not verified" over an optimistic "done".

Accuracy over approval (W6.1): verify every fact, figure and citation before
finalizing. Never fabricate a source. Say "unknown" plainly when something is
not verified. Do not anchor on numbers supplied by the user: produce an
independent estimate and label it as an estimate.

Anti-sycophancy (W6.3): never praise the question or the user's insight. If the
user is wrong, say so immediately. Lead with the strongest counterargument.
Do not capitulate under pushback without new evidence.

Keel keeps its own safety messaging and Tier-2 behavior. Never drop
ethics/safety caveats and never become "aggressive" toward the operator.
</rigor-contract>"""

PERSONA_REQUIRED_PHRASES = (
    "Verify before claiming done", "Never invent", "not verified",
    "unknown", "independent estimate", "never praise the question",
    "say so immediately", "strongest counterargument",
    "without new evidence", "safety messaging", "Tier-2",
)
FORBIDDEN_PERSONA_PHRASES = (
    "avoid all ethics", "avoid ethics", "ignore all ethics", "no safety caveats",
    "without ethics", "be aggressive", "ignore safety", "drop safety",
)


def persona_rigor_section() -> str:
    """W6.1/W6.3: the default ``PERSONA.md`` rigor section (V7 eval input)."""
    return PERSONA_RIGOR_SECTION.strip()


def validate_persona_section(text: Any) -> tuple[str, ...]:
    """Check that a persona section keeps rigor *and* Keel's safety behavior."""
    if not isinstance(text, str):
        return ("persona section must be text",)
    errors: list[str] = []
    lowered = text.casefold()
    for phrase in PERSONA_REQUIRED_PHRASES:
        if phrase.casefold() not in lowered:
            errors.append("persona missing required rule: %s" % phrase)
    for phrase in FORBIDDEN_PERSONA_PHRASES:
        if phrase in lowered:
            errors.append("persona removed safety behavior: %s" % phrase)
    return tuple(errors)


def assert_safe_persona(text: Any) -> str:
    """Fail closed if a persona section drops safety or anti-sycophancy rules."""
    if not isinstance(text, str):
        raise ProductContractError("bad_persona_section")
    errors = validate_persona_section(text)
    if errors:
        raise ProductContractError("unsafe_persona_section", "; ".join(errors))
    return text


@dataclass(frozen=True)
class ResponseContract:
    """The result of a pre-finalization check (never a claim of truth)."""

    finalizable: bool
    accuracy_errors: tuple[str, ...]
    anti_sycophancy_errors: tuple[str, ...]

    @property
    def errors(self) -> tuple[str, ...]:
        return self.accuracy_errors + self.anti_sycophancy_errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "finalizable": self.finalizable,
            "accuracy_errors": list(self.accuracy_errors),
            "anti_sycophancy_errors": list(self.anti_sycophancy_errors),
            "runtime_claimed": False,
        }


def response_contract(draft: ResponseDraft) -> ResponseContract:
    """Compute the accuracy + anti-sycophancy contract without raising."""
    accuracy = check_accuracy(draft)
    anti = check_anti_sycophancy(draft)
    return ResponseContract(finalizable=not (accuracy or anti),
                            accuracy_errors=accuracy,
                            anti_sycophancy_errors=anti)


def assert_finalizable(draft: ResponseDraft) -> ResponseContract:
    """Finalization gate: fail closed unless every rule passes."""
    contract = response_contract(draft)
    if not contract.finalizable:
        raise ProductContractError("response_not_finalizable",
                                   "; ".join(contract.errors))
    return contract


def rigor_eval(draft: ResponseDraft) -> dict[str, Any]:
    """Pure V7-style eval: one boolean per rule and an overall pass flag."""
    accuracy = set(check_accuracy(draft))
    anti = set(check_anti_sycophancy(draft))
    persona = set(validate_persona_section(persona_rigor_section()))
    rules = {
        "facts_and_citations_verified": not accuracy,
        "no_fabrication": "verified_claim_needs_source" not in accuracy,
        "unknown_stated_plainly": "response does not say unknown plainly" not in accuracy,
        "independent_estimate": not any("independent estimate" in error
                                        for error in accuracy),
        "no_praise_of_question": "praise_of_question" not in anti,
        "correction_immediate": "correction_not_immediate" not in anti,
        "strongest_counterargument_first": not any("counterargument" in error
                                                   for error in anti),
        "no_capitulation_without_evidence": "capitulation_without_new_evidence" not in anti,
        "safety_behavior_preserved": not persona,
    }
    return {"rules": rules, "passed": all(rules.values()), "runtime_claimed": False}
