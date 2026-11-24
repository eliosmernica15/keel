"""Additive, stdlib-only contracts for the W7.x P0 security features.

This module is **additive by design**: it never imports, patches or reorders
live application code. It exposes small, typed, fail-closed seams that a caller
can adopt one at a time (see ``INTEGRATION_SEAMS``). It performs no network I/O,
starts no subprocesses and needs no third-party package.

Covered registry IDs (all P0, ``not_started`` at baseline 9201f2a):

    W7.1   typed trust boundaries / security-model documentation
    W7.3   AES-256-GCM sealing (12-byte IV, 16-byte tag, AAD) + session cookie
    W7.4   API keys: prefixed token, SHA-256-only storage, rate limit, idempotency
    W7.5   staged secret files consumed and deleted by the child setup script
    W7.6   log redaction + keyed pseudonyms instead of raw user ids
    W7.8   trusted-proxy address detection, pairing rate limits, return-path guard
    W7.10  SSRF-safe fetch: resolve-then-pin, redirect re-check, time/size caps
    W7.13  security headers for any served UI
    W7.14  rendering safety: escaped Markdown, scheme allowlist, sandboxed previews
    W7.16  publish path selector: realpath containment, no hidden files/symlinks
    W7.17  inbound channels: constant-time HMAC, 300 s window, nonce replay cache
    W7.19  honest known-limitations list

Security posture: every validation error is typed and carries a stable
``reason`` code. Error strings never include URL userinfo, query strings,
header values, tokens or secret material. All dataclasses are frozen.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets as _secrets
import socket
import stat
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Iterator, Mapping, Optional, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit

W7_IDS = (
    "W7.1", "W7.3", "W7.4", "W7.5", "W7.6", "W7.8",
    "W7.10", "W7.13", "W7.14", "W7.16", "W7.17", "W7.19",
)

INTEGRATION_SEAMS = (
    "W7.1: render render_trust_model()/render_known_limits_page() in the "
    "in-app About page and ship the same text as security-model.md.",
    "W7.3: call seal_secret/open_secret for values at rest and "
    "seal_session_cookie/open_session_cookie for the web session; the cookie "
    "flags come from session_cookie_header().",
    "W7.4: issue_api_key() at creation time; persist only key_id + digest; "
    "verify_api_key() on each request and ApiKeyStore.consume() for limits.",
    "W7.5: stage_secrets() before launching an MCP/plugin child; pass only "
    "plan.env/plan.argv; consume_staged_secrets() inside the setup script.",
    "W7.6: route log/trace lines through LogRedactor.redact() and identifiers "
    "through LogRedactor.pseudonymize().",
    "W7.8: client_address_from_headers() in the web request adapter, "
    "PairingRateLimiter.check() on sign-in/pairing, safe_return_path() on redirects.",
    "W7.10: validate_fetch_url()/validate_redirect_chain() before every "
    "outbound fetch; connect to plan.connection_target() with plan.host_header "
    "and stream the body through stream_limited().",
    "W7.13: merge build_security_headers() into every served UI response.",
    "W7.14: render Markdown only through render_safe_markdown(); previews use "
    "render_sandboxed_iframe(); inline HTML/SVG/XML use sandbox_headers_for_content_type().",
    "W7.16: build_publish_manifest(site_root) drives the sites exporter; copy "
    "only the returned PublishFile.source paths.",
    "W7.17: InboundChannelVerifier.verify() at the webhook/channel edge and "
    "default_channel_rules()/admit_channel_message() before starting work.",
)


# ===========================================================================
# W7.1 - explicit trust boundaries
# ===========================================================================

class TrustRole(str, Enum):
    """Typed principals. Values are stable identifiers for documentation."""

    CLIENT = "client"
    DAEMON = "daemon"
    AGENT = "agent"
    HOST_API = "host_api"
    THIRD_PARTY = "third_party"


@dataclass(frozen=True)
class TrustBoundary:
    source: TrustRole
    target: TrustRole
    rule: str
    rationale: str


TRUST_BOUNDARIES = (
    TrustBoundary(
        TrustRole.CLIENT, TrustRole.DAEMON,
        "Client input is untrusted: validate, authenticate and authorize everything; never send secrets to the client.",
        "Browsers, CLI and phone clients are attacker-controlled; any token they hold can be extracted.",
    ),
    TrustBoundary(
        TrustRole.DAEMON, TrustRole.AGENT,
        "The daemon alone holds secrets and grants scoped capabilities; the agent gets a restricted environment with redacted values.",
        "Agent code can be steered by untrusted content (prompt injection); its power must be explicit and revocable.",
    ),
    TrustBoundary(
        TrustRole.AGENT, TrustRole.HOST_API,
        "Host APIs are privileged and daemon-mediated: the agent cannot call them directly or widen a grant.",
        "Filesystem, shell and process APIs run with the user's full authority; no agent-side policy is final.",
    ),
    TrustBoundary(
        TrustRole.DAEMON, TrustRole.THIRD_PARTY,
        "Third parties are untrusted: outbound fetches are scheme-checked, address-pinned and size/time capped.",
        "DNS names, redirects and remote content can point back at private or metadata endpoints (SSRF).",
    ),
)

TRUST_MODEL = {
    "client": {"trust": "untrusted", "holds_secrets": False, "note": "Validated at the daemon edge."},
    "daemon": {"trust": "trusted", "holds_secrets": True, "note": "Sole secret holder and policy enforcer."},
    "agent": {"trust": "restricted", "environment": "restricted", "holds_secrets": False,
              "note": "Scoped tools, redacted values, daemon-mediated host access."},
    "host_api": {"trust": "trusted", "privileged": True, "holds_secrets": False,
                 "note": "Called only by the daemon after policy checks."},
    "third_party": {"trust": "untrusted", "holds_secrets": False,
                    "note": "Network peers, fetched content and inbound channels."},
}


def render_trust_model() -> str:
    """Markdown for the private security model and the in-app About panel."""
    lines = [
        "# What Keel protects - and what it cannot",
        "",
        "Keel treats the client as **untrusted**. The daemon is the only component "
        "that holds secrets. The agent runs in a **restricted** environment and "
        "never receives raw credentials. Host APIs are **privileged** and reached "
        "only through daemon mediation. Third parties are untrusted.",
        "",
        "| From | To | Rule | Why |",
        "|---|---|---|---|",
    ]
    for boundary in TRUST_BOUNDARIES:
        lines.append("| {0} | {1} | {2} | {3} |".format(
            boundary.source.value, boundary.target.value, boundary.rule, boundary.rationale))
    lines += ["", "## Known limits", ""]
    for limit in KNOWN_LIMITATIONS:
        lines.append("- **{0}**: {1} ({2})".format(limit.title, limit.statement, limit.mitigation))
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class KnownLimitation:
    id: str
    title: str
    statement: str
    mitigation: str


KNOWN_LIMITATIONS = (
    KnownLimitation(
        "KL-1", "Prompt injection can still misuse granted power",
        "Untrusted content can steer an agent into using capabilities it was granted.",
        "Keep grants narrow, require confirmation for risky actions, and monitor tool traces.",
    ),
    KnownLimitation(
        "KL-2", "Watch-only is client-side in openman",
        "In openman, watch-only is enforced only in the client; orgo-teammates enforces it server-side.",
        "Prefer the server-side watch-only mode when host authority matters.",
    ),
    KnownLimitation(
        "KL-3", "One shared sign-in budget",
        "Sign-in and pairing attempts share a single budget across users of an instance.",
        "Use narrow allowlists and trusted-proxy hop counts; watch pair/limit telemetry.",
    ),
    KnownLimitation(
        "KL-4", "Self-hosting is only as safe as its setup",
        "Provider keys, network exposure and spend limits are the operator's responsibility.",
        "Use narrowest-scope keys, never display keys on screen or recordings, set provider spend limits.",
    ),
)


def render_known_limits_page() -> str:
    lines = ["# Known limits", ""]
    for limit in KNOWN_LIMITATIONS:
        lines += ["## {0} - {1}".format(limit.id, limit.title), "",
                  limit.statement, "", "Mitigation: " + limit.mitigation, ""]
    return "\n".join(lines)


# ===========================================================================
# W7.10 - SSRF-safe fetch validation
# ===========================================================================

class SSRFValidationError(ValueError):
    """Fail-closed fetch validation error. Never contains secret material."""

    def __init__(self, reason: str, message: str = "", *, address: str = "", address_class: str = ""):
        self.reason = reason
        self.address = address
        self.address_class = address_class
        super().__init__(message or ("fetch rejected: " + reason))


class BodyTooLargeError(ValueError):
    pass


class AddressClass(str, Enum):
    GLOBAL = "global"
    LOOPBACK = "loopback"
    PRIVATE = "private"
    LINK_LOCAL = "link_local"
    METADATA = "metadata"
    UNSPECIFIED = "unspecified"
    RESERVED = "reserved"
    MULTICAST = "multicast"
    SPECIAL = "special"
    INVALID = "invalid"


METADATA_NETWORKS = (
    "169.254.169.254/32",   # AWS/GCP/Azure IMDSv1
    "fd00:ec2::254/128",    # AWS IPv6 IMDS
    "100.100.100.200/32",   # Alibaba metadata
)
# IPv6 prefixes that embed an IPv4 address; a naive is_global() check is unsafe.
_IPV4_EMBEDDED_NETWORKS = (
    "::/96",                # IPv4-compatible (except :: and ::1, checked earlier)
    "2002::/16",            # 6to4
    "64:ff9b::/96",         # NAT64 well-known prefix
    "64:ff9b:1::/48",       # NAT64 local-use prefix
)

SCHEME_ALLOWLIST = frozenset({"http", "https"})
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 10.0
DEFAULT_TOTAL_TIMEOUT = 30.0
DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_MAX_REDIRECTS = 5


def _import_ipaddress():
    import ipaddress
    return ipaddress


def _ip_of(value: str):
    try:
        return _import_ipaddress().ip_address(value.strip())
    except (ValueError, TypeError):
        return None


def _embedded_v4(ip):
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return mapped
    sixfour = getattr(ip, "sixtofour", None)
    if sixfour is not None:
        return sixfour
    ipa = _import_ipaddress()
    raw = ip.packed
    for net in ("64:ff9b::/96", "64:ff9b:1::/48", "::/96"):
        network = ipa.IPv6Network(net)
        if ip in network:
            prefix_len = network.prefixlen
            width = (128 - prefix_len) // 8
            if width == 4:
                return ipa.IPv4Address(raw[-4:])
            if width == 3:
                return ipa.IPv4Address(b"\x00" + raw[-3:]) if raw[-3] == 0 else None
    return None


def classify_address(value: str) -> AddressClass:
    """Classify an IP literal. IPv4-mapped/embedded IPv6 is classified by its IPv4 payload."""
    ip = _ip_of(value)
    if ip is None:
        return AddressClass.INVALID
    ipa = _import_ipaddress()
    if ip.is_unspecified:
        return AddressClass.UNSPECIFIED
    if ip.is_loopback:
        return AddressClass.LOOPBACK
    if ip.version == 6:
        embedded = _embedded_v4(ip)
        if embedded is not None:
            return classify_address(str(embedded))
        if ip in ipa.IPv6Network("64:ff9b::/96") or ip in ipa.IPv6Network("64:ff9b:1::/48"):
            return AddressClass.SPECIAL
    for network in METADATA_NETWORKS:
        if ip in ipa.ip_network(network):
            return AddressClass.METADATA
    if ip.is_link_local:
        return AddressClass.LINK_LOCAL
    if ip.is_multicast:
        return AddressClass.MULTICAST
    if ip.is_private:
        return AddressClass.PRIVATE
    if not ip.is_global:
        return AddressClass.RESERVED
    return AddressClass.GLOBAL


def assert_address_allowed(value: str, *, allowed_networks: Iterable[str] = (),
                           allow_metadata: bool = False) -> AddressClass:
    kind = classify_address(value)
    ip = _ip_of(value)
    if kind is AddressClass.METADATA:
        if not allow_metadata:
            raise SSRFValidationError("METADATA_ADDRESS", "cloud metadata endpoint is not allowed",
                                      address="[redacted]", address_class=kind.value)
        return kind
    if kind is AddressClass.GLOBAL:
        return kind
    if ip is not None:
        ipa = _import_ipaddress()
        for network in allowed_networks:
            try:
                if ip in ipa.ip_network(network, strict=False):
                    return kind
            except (ValueError, TypeError):
                continue
    reason = "METADATA_ADDRESS" if kind is AddressClass.METADATA else "UNSAFE_ADDRESS"
    raise SSRFValidationError(reason, "address class '{0}' is not allowed".format(kind.value),
                              address="[redacted]", address_class=kind.value)


def redact_url(url: str) -> str:
    """Scheme + host + port only. Never returns userinfo, query or fragment."""
    try:
        parts = urlsplit(str(url))
        return urlunsplit((parts.scheme, parts.netloc.split("@")[-1], "/", "", ""))
    except (ValueError, TypeError):
        return "[redacted]"


def resolve_host(host: str) -> Sequence[str]:
    """Default resolver: literals are returned verbatim, names use getaddrinfo.

    Callers should inject their own resolver in tests and in environments with
    a custom DNS policy.
    """
    ip = _ip_of(host)
    if ip is not None:
        return (str(host),)
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SSRFValidationError("RESOLUTION_FAILED", "DNS resolution failed: " + type(exc).__name__) from None
    unique = []
    for info in infos:
        addr = info[4][0]
        if addr not in unique:
            unique.append(addr)
    if not unique:
        raise SSRFValidationError("RESOLUTION_FAILED", "DNS resolution returned no addresses")
    return tuple(unique)


def _rebuild_netloc(parts, scheme: str, port: int) -> str:
    """Host (bracketed for IPv6) with a non-default port; never userinfo."""
    host = (parts.hostname or "").lower()
    if ":" in host:
        host = "[" + host + "]"
    default = 443 if scheme == "https" else 80
    return host if port == default else "{0}:{1}".format(host, port)


@dataclass(frozen=True)
class FetchPlan:
    url: str
    scheme: str
    host: str
    port: int
    address: str
    address_class: AddressClass
    tls_server_name: str
    host_header: str
    connect_timeout: float
    read_timeout: float
    total_timeout: float
    max_bytes: int

    @property
    def connection_target(self):
        return (self.address, self.port)

    @property
    def safe_summary(self) -> str:
        return "{0}://{1}:{2}/".format(self.scheme, self.host, self.port)


def _split_url(url: str):
    try:
        parts = urlsplit(url)
    except (ValueError, TypeError):
        raise SSRFValidationError("MALFORMED_URL", "malformed URL") from None
    if parts.scheme.lower() not in SCHEME_ALLOWLIST:
        raise SSRFValidationError("SCHEME_NOT_ALLOWED", "only http and https are allowed")
    if parts.netloc and "@" in parts.netloc:
        raise SSRFValidationError("CREDENTIALS_IN_URL", "credentials in URL are not allowed")
    try:
        host = parts.hostname
    except ValueError:
        raise SSRFValidationError("MALFORMED_URL", "malformed URL authority") from None
    if not host:
        raise SSRFValidationError("MISSING_HOST", "URL has no host")
    try:
        port = parts.port
    except ValueError:
        raise SSRFValidationError("INVALID_PORT", "invalid URL port") from None
    if port is None:
        port = 443 if parts.scheme.lower() == "https" else 80
    if port < 1 or port > 65535:
        raise SSRFValidationError("INVALID_PORT", "URL port out of range")
    return parts, parts.scheme.lower(), host.lower().rstrip("."), port


def validate_fetch_url(
    url: str,
    resolver: Callable[[str], Iterable[str]] = resolve_host,
    *,
    allowed_networks: Iterable[str] = (),
    allow_metadata: bool = False,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: float = DEFAULT_READ_TIMEOUT,
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    visited: Sequence[str] = (),
) -> FetchPlan:
    """Validate a URL, resolve its name and return a pinned connection plan.

    Every DNS answer is checked; the first checked answer is pinned. A literal
    address is used directly (no DNS lookup, so rebinding is impossible).
    The original hostname is preserved for Host/SNI via ``host_header`` and
    ``tls_server_name``; callers must connect to ``connection_target``.
    """
    if not isinstance(url, str) or not url or any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise SSRFValidationError("MALFORMED_URL", "malformed URL")
    parts, scheme, host, port = _split_url(url)
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if connect_timeout <= 0 or read_timeout <= 0 or total_timeout <= 0:
        raise ValueError("timeouts must be positive")
    normalized = urlunsplit((scheme, _rebuild_netloc(parts, scheme, port),
                             parts.path, parts.query, ""))
    if normalized in visited:
        raise SSRFValidationError("REDIRECT_LOOP", "redirect loop")
    if visited and scheme == "http" and any(v.startswith("https://") for v in visited):
        raise SSRFValidationError("HTTPS_DOWNGRADE", "https to http redirect is not allowed")

    literal = _ip_of(host)
    if literal is not None:
        addresses = (host,)
    else:
        try:
            addresses = tuple(resolver(host))
        except SSRFValidationError:
            raise
        except Exception:
            raise SSRFValidationError("RESOLUTION_FAILED", "DNS resolution failed") from None
        if not addresses:
            raise SSRFValidationError("RESOLUTION_FAILED", "DNS resolution returned no addresses")
    checked = []
    for address in addresses:
        if not isinstance(address, str):
            raise SSRFValidationError("UNSAFE_ADDRESS", "resolver returned a non-address")
        kind = assert_address_allowed(address, allowed_networks=allowed_networks, allow_metadata=allow_metadata)
        checked.append((address, kind))
    address, kind = checked[0]
    host_header = host if port in (80, 443) else "{0}:{1}".format(host, port)
    return FetchPlan(
        url=normalized, scheme=scheme, host=host, port=port, address=address,
        address_class=kind, tls_server_name=host, host_header=host_header,
        connect_timeout=float(connect_timeout), read_timeout=float(read_timeout),
        total_timeout=float(total_timeout), max_bytes=int(max_bytes),
    )


def validate_request_headers(headers: Mapping[str, str], *, forbidden_values: Iterable[str] = ()) -> dict:
    """Normalize request headers, rejecting CRLF injection and credential headers."""
    forbidden_names = {
        "host", "cookie", "set-cookie", "authorization", "proxy-authorization",
        "x-api-key", "x-auth-token", "x-forwarded-for", "x-forwarded-host", "content-length",
    }
    out = {}
    values = [str(v) for v in forbidden_values if str(v)]
    for name, value in (headers or {}).items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise SSRFValidationError("MALFORMED_HEADER", "headers must be string to string")
        if not name or any(ord(c) < 33 or ord(c) == 127 or c in ":()" for c in name):
            raise SSRFValidationError("MALFORMED_HEADER", "malformed header name")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise SSRFValidationError("MALFORMED_HEADER", "header value contains control characters")
        if name.lower() in forbidden_names or any(secret and secret in value for secret in values):
            raise SSRFValidationError("FORBIDDEN_HEADER", "header is not allowed on outbound fetches")
        out[name] = value
    return out


def parse_redirect_location(base_url: str, location: str) -> str:
    """Resolve a redirect target with strict Location validation."""
    if not isinstance(location, str) or not location.strip():
        raise SSRFValidationError("MALFORMED_LOCATION", "redirect has no Location")
    if any(ord(c) < 32 or ord(c) == 127 for c in location) or "\\" in location:
        raise SSRFValidationError("MALFORMED_LOCATION", "malformed Location header")
    target = urljoin(base_url, location.strip())
    parts, scheme, host, port = _split_url(target)
    if parts.username or parts.password or "@" in parts.netloc:
        raise SSRFValidationError("CREDENTIALS_IN_URL", "credentials in redirect are not allowed")
    return urlunsplit((scheme, _rebuild_netloc(parts, scheme, port),
                       parts.path, parts.query, ""))


def validate_redirect_chain(
    urls: Sequence[str],
    resolver: Callable[[str], Iterable[str]] = resolve_host,
    *,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    allowed_networks: Iterable[str] = (),
    allow_metadata: bool = False,
    **limits,
) -> tuple:
    """Validate the initial URL and every redirect hop before any request is made."""
    if not urls:
        raise SSRFValidationError("MALFORMED_URL", "empty redirect chain")
    plans = []
    visited = []
    seen = set()
    previous_scheme = None
    for index, target in enumerate(urls):
        if index > max_redirects:
            raise SSRFValidationError("TOO_MANY_REDIRECTS", "redirect limit exceeded")
        normalized = parse_redirect_location(visited[-1], target) if visited else target
        _, scheme, _, _ = _split_url(normalized)
        if normalized in seen:
            raise SSRFValidationError("REDIRECT_LOOP", "redirect loop")
        if previous_scheme == "https" and scheme == "http":
            raise SSRFValidationError("HTTPS_DOWNGRADE", "https to http redirect is not allowed")
        seen.add(normalized)
        previous_scheme = scheme
        plan = validate_fetch_url(
            normalized, resolver, allowed_networks=allowed_networks,
            allow_metadata=allow_metadata, visited=tuple(visited), **limits)
        visited.append(plan.url)
        plans.append(plan)
    return tuple(plans)


def stream_limited(chunks: Iterable[bytes], max_bytes: int) -> Iterator[bytes]:
    """Enforce a body limit while streaming, independent of Content-Length."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > max_bytes:
            raise BodyTooLargeError("response body exceeds the configured limit")
        yield chunk


# ===========================================================================
# W7.13 - security headers
# ===========================================================================

class WeakCSPError(ValueError):
    pass


class HeaderSecretLeakError(ValueError):
    pass


DEFAULT_CSP = (
    "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; "
    "frame-ancestors 'none'; form-action 'self'; frame-src 'none'; "
    "connect-src 'self'; img-src 'self' data:; style-src 'self'; worker-src 'none'"
)
SANDBOX_CSP = (
    "default-src 'none'; script-src 'none'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'none'; sandbox"
)
FORBIDDEN_HEADER_NAMES = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "x-auth-token", "x-csrf-token", "x-secret", "x-session",
    "x-webhook-secret", "x-amz-security-token",
})
_SECRET_HEADER_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{12,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{12,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _parse_csp(csp: str) -> dict:
    directives = {}
    for part in str(csp).split(";"):
        tokens = part.split()
        if tokens:
            directives[tokens[0].lower()] = [t.lower() for t in tokens[1:]]
    return directives


def assert_strong_csp(csp: str) -> str:
    if not isinstance(csp, str) or not csp:
        raise WeakCSPError("CSP must be a non-empty string")
    directives = _parse_csp(csp)
    if "default-src" not in directives or "*" in directives["default-src"]:
        raise WeakCSPError("CSP needs a restricted default-src")
    if directives.get("frame-ancestors") != ["'none'"]:
        raise WeakCSPError("CSP frame-ancestors must be 'none'")
    if "object-src" not in directives or "*" in directives["object-src"]:
        raise WeakCSPError("CSP object-src must be 'none'")
    for name in ("script-src", "style-src", "default-src"):
        tokens = directives.get(name, [])
        if "unsafe-eval" in tokens or "unsafe-inline" in tokens or "*" in tokens:
            raise WeakCSPError("CSP must not use unsafe-eval, unsafe-inline or *")
    return csp


def build_csp(nonce: str | None = None) -> str:
    csp = DEFAULT_CSP
    if nonce:
        if not re.fullmatch(r"[A-Za-z0-9+/=_-]{8,}", nonce):
            raise ValueError("invalid CSP nonce")
        csp = csp.replace("script-src 'self'", "script-src 'self' 'nonce-{0}'".format(nonce))
    return assert_strong_csp(csp)


def build_security_headers(
    *,
    https: bool,
    csp: str | None = None,
    nonce: str | None = None,
    extra_headers: Mapping[str, str] | None = None,
    forbidden_values: Iterable[str] = (),
) -> dict:
    """Build a full, non-weakenable header set for a served UI response."""
    if csp is not None:
        csp = assert_strong_csp(csp)
    else:
        csp = build_csp(nonce)
    headers = {
        "Content-Security-Policy": csp,
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "X-Permitted-Cross-Domain-Policies": "none",
        "Permissions-Policy": (
            "microphone=(self), camera=(), geolocation=(), payment=(), usb=(), "
            "accelerometer=(), gyroscope=(), magnetometer=(), autoplay=(), "
            "encrypted-media=(), fullscreen=(), picture-in-picture=()"
        ),
    }
    if https:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        headers["Content-Security-Policy"] += "; upgrade-insecure-requests"
    values = [str(v) for v in forbidden_values if str(v)]
    for name, value in (extra_headers or {}).items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise HeaderSecretLeakError("headers must be string to string")
        if name.lower() in FORBIDDEN_HEADER_NAMES or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise HeaderSecretLeakError("header is not allowed in a UI response")
        if any(v and v in value for v in values) or any(p.search(value) for p in _SECRET_HEADER_PATTERNS):
            raise HeaderSecretLeakError("header value may contain secret material")
        if name.lower() in {k.lower() for k in headers}:
            raise HeaderSecretLeakError("security headers cannot be overridden")
        headers[name] = value
    return headers


def security_headers_for_url(url: str, **kwargs) -> dict:
    parts = urlsplit(url)
    if parts.scheme.lower() not in SCHEME_ALLOWLIST:
        raise ValueError("only http and https URLs have UI security headers")
    return build_security_headers(https=parts.scheme.lower() == "https", **kwargs)


def sandbox_headers_for_content_type(content_type: str) -> dict:
    """Inline HTML/SVG/XML must be served under a sandboxing CSP."""
    normalized = str(content_type).split(";")[0].strip().lower()
    if normalized in {"text/html", "application/xhtml+xml", "image/svg+xml",
                      "text/xml", "application/xml", "application/xhtml"}:
        return {
            "Content-Security-Policy": SANDBOX_CSP,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        }
    return {}


# ===========================================================================
# W7.14 - rendering safety
# ===========================================================================

class UnsafeLinkError(ValueError):
    pass


LINK_SCHEME_ALLOWLIST = frozenset({"http", "https", "mailto"})
DANGEROUS_HTML_APIS = (
    "dangerouslySetInnerHTML", "innerHTML", "outerHTML", "document.write",
    "eval(", "new Function(",
)


def assert_no_dangerous_html_api(source: str) -> None:
    """Guard for templates/components: no raw-HTML sinks allowed."""
    for needle in DANGEROUS_HTML_APIS:
        if needle in str(source):
            raise ValueError("raw HTML sink '{0}' is forbidden".format(needle))


def validate_link_url(
    url: str,
    *,
    schemes: frozenset = LINK_SCHEME_ALLOWLIST,
    allow_relative: bool = True,
) -> str:
    if not isinstance(url, str):
        raise UnsafeLinkError("link URL must be a string")
    cleaned = "".join(c for c in url if ord(c) >= 32 and ord(c) != 127).strip()
    if not cleaned or "\\" in cleaned or cleaned.startswith("//"):
        raise UnsafeLinkError("link URL is not allowed")
    parts = urlsplit(cleaned)
    scheme = parts.scheme.lower()
    if scheme:
        if scheme not in schemes:
            raise UnsafeLinkError("link scheme is not allowed")
        if parts.username or parts.password or "@" in parts.netloc:
            raise UnsafeLinkError("credentials in link are not allowed")
        if scheme in {"http", "https"} and not parts.hostname:
            raise UnsafeLinkError("absolute link has no host")
        if scheme == "mailto" and (not parts.path or "@" not in parts.path):
            raise UnsafeLinkError("mailto link has no recipient")
    elif not allow_relative or cleaned.startswith("/") and any(p == ".." for p in cleaned.split("/")):
        raise UnsafeLinkError("relative link is not allowed")
    return cleaned


_MD_TOKEN_RE = re.compile(
    r"(!?\[[^\]\n]*\]\([^\n]*?\))"          # image or link
    r"|(<[^>\n]*>)"                          # autolink / raw html
    r"|(`[^`\n]+`)"                          # code span
    r"|(\*\*[^*\n]+\*\*|\*[^*\n]+\*|__[^_\n]+__|_[^_\n]+_)",  # emphasis
)
_MD_LINK_RE = re.compile(r'^(!?)\[([^\]]*)\]\(\s*([^\s)]*)(?:\s+"([^"]*)")?\s*\)$')
_MD_AUTOLINK_RE = re.compile(r"^<(https?://[^>]+)>$", re.IGNORECASE)


class SafeMarkdownRenderer:
    """Conservative Markdown seam: raw HTML is never passed through.

    Only a small, explicit subset is rendered to markup. Every other byte is
    escaped with ``html.escape(quote=True)`` before reaching the output.
    """

    def __init__(self, *, allow_external_images: bool = False):
        self.allow_external_images = bool(allow_external_images)

    def render(self, text: str, *, allow_external_images: bool | None = None) -> str:
        if not isinstance(text, str):
            raise ValueError("markdown input must be a string")
        allow_images = self.allow_external_images if allow_external_images is None else bool(allow_external_images)
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        out = []
        paragraph = []

        def flush():
            if paragraph:
                out.append("<p>" + self._inline("\n".join(paragraph)) + "</p>")
                paragraph.clear()

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                flush()
                i += 1
                continue
            fence = re.match(r"^\s*```([A-Za-z0-9_+-]*)\s*$", line)
            if fence:
                flush()
                language = fence.group(1)
                i += 1
                code = []
                while i < len(lines) and not re.match(r"^\s*```\s*$", lines[i]):
                    code.append(lines[i])
                    i += 1
                i += 1  # closing fence (or EOF)
                cls = ' class="language-{0}"'.format(html.escape(language, quote=True)) if language else ""
                out.append("<pre><code{0}>{1}</code></pre>".format(
                    cls, html.escape("\n".join(code), quote=True)))
                continue
            heading = re.match(r"^\s*(#{1,6})\s+(.*)$", line)
            if heading:
                flush()
                level = len(heading.group(1))
                out.append("<h{0}>{1}</h{0}>".format(level, self._inline(heading.group(2))))
                i += 1
                continue
            if re.match(r"^\s*(---+|\*\*\*+|___+)\s*$", line):
                flush()
                out.append("<hr>")
                i += 1
                continue
            quote = re.match(r"^\s*>\s?(.*)$", line)
            if quote:
                flush()
                out.append("<blockquote>{0}</blockquote>".format(self._inline(quote.group(1))))
                i += 1
                continue
            bullet = re.match(r"^\s*[-*+]\s+(.*)$", line)
            ordered = re.match(r"^\s*\d+\.\s+(.*)$", line)
            if bullet or ordered:
                flush()
                tag = "ul" if bullet else "ol"
                pattern = r"^\s*[-*+]\s+(.*)$" if bullet else r"^\s*\d+\.\s+(.*)$"
                items = []
                while i < len(lines):
                    item = re.match(pattern, lines[i])
                    if not item:
                        break
                    items.append("<li>{0}</li>".format(self._inline(item.group(1))))
                    i += 1
                out.append("<{0}>{1}</{0}>".format(tag, "".join(items)))
                continue
            paragraph.append(line)
            i += 1
        flush()
        return "\n".join(out)

    def _inline(self, text: str) -> str:
        out = []
        pos = 0
        for match in _MD_TOKEN_RE.finditer(text):
            out.append(html.escape(text[pos:match.start()], quote=True))
            token = match.group(0)
            if match.group(1):
                out.append(self._link_token(token))
            elif match.group(2):
                autolink = _MD_AUTOLINK_RE.match(token)
                if autolink:
                    out.append(self._anchor(autolink.group(1), html.escape(autolink.group(1), quote=True)))
                else:
                    out.append(html.escape(token, quote=True))
            elif match.group(3):
                out.append("<code>{0}</code>".format(html.escape(token[1:-1], quote=True)))
            else:
                inner = token.strip("*")
                out.append("<strong>{0}</strong>".format(html.escape(inner, quote=True))
                           if token.startswith("**") else
                           "<em>{0}</em>".format(html.escape(inner, quote=True)))
            pos = match.end()
        out.append(html.escape(text[pos:], quote=True))
        return "".join(out)

    def _link_token(self, token: str) -> str:
        match = _MD_LINK_RE.match(token)
        if not match:
            return html.escape(token, quote=True)
        bang, label, raw_url, title = match.groups()
        label_html = html.escape(label, quote=True)
        if bang == "!":
            try:
                url = validate_link_url(raw_url, schemes=frozenset({"http", "https"}))
            except UnsafeLinkError:
                return '<span class="keel-blocked-image">External image blocked: {0}</span>'.format(label_html)
            is_external = bool(urlsplit(url).scheme)
            if is_external and not self.allow_external_images:
                return '<span class="keel-blocked-image">External image blocked: {0}</span>'.format(label_html)
            title_attr = ' title="{0}"'.format(html.escape(title, quote=True)) if title else ""
            return '<img src="{0}" alt="{1}"{2} loading="lazy" referrerpolicy="no-referrer">'.format(
                html.escape(url, quote=True), label_html, title_attr)
        try:
            url = validate_link_url(raw_url)
        except UnsafeLinkError:
            return '<span class="keel-unsafe-link">{0}</span>'.format(label_html)
        return self._anchor(url, label_html, title=title)

    @staticmethod
    def _anchor(url: str, label_html: str, *, title: str | None = None) -> str:
        title_attr = ' title="{0}"'.format(html.escape(title, quote=True)) if title else ""
        return '<a href="{0}"{1} rel="noopener noreferrer">{2}</a>'.format(
            html.escape(url, quote=True), title_attr, label_html)


def render_safe_markdown(text: str, *, allow_external_images: bool = False) -> str:
    return SafeMarkdownRenderer(allow_external_images=allow_external_images).render(text)


def sandboxed_iframe_attrs(src: str, *, title: str = "Generated site preview") -> dict:
    safe_src = validate_link_url(src, schemes=frozenset({"http", "https"}), allow_relative=True)
    return {
        "src": safe_src,
        "title": title,
        "sandbox": "allow-scripts",
        "referrerpolicy": "no-referrer",
        "csp": SANDBOX_CSP,
        "loading": "lazy",
    }


def render_sandboxed_iframe(src: str, *, title: str = "Generated site preview") -> str:
    attrs = sandboxed_iframe_attrs(src, title=title)
    rendered = " ".join('{0}="{1}"'.format(k, html.escape(str(v), quote=True)) for k, v in attrs.items())
    return "<iframe {0}></iframe>".format(rendered)


# ===========================================================================
# W7.16 - publish path selector
# ===========================================================================

class SafePathError(ValueError):
    def __init__(self, reason: str, message: str = ""):
        self.reason = reason
        super().__init__(message or ("publish path rejected: " + reason))


@dataclass(frozen=True)
class PublishFile:
    relative: str
    source: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class PublishManifest:
    version: str
    root: str
    digest: str
    files: tuple

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "root": self.root,
            "digest": self.digest,
            "files": [
                {"path": f.relative, "size": f.size, "sha256": f.sha256}
                for f in self.files
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _normcase_path(path: Path) -> str:
    return os.path.normcase(str(path))


def _within(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath([_normcase_path(root), _normcase_path(candidate)]) == _normcase_path(root)
    except (ValueError, OSError):
        return False


def _is_hidden(name: str) -> bool:
    return name.startswith(".")


def select_publish_files(
    site_root: str | Path,
    candidates: Optional[Iterable[str | Path]] = None,
    *,
    is_symlink: Optional[Callable[[Path], bool]] = None,
    hidden_predicate: Callable[[str], bool] = _is_hidden,
) -> tuple:
    """Select publishable regular files from the site's own folder only.

    ``is_symlink`` is injectable so hosts that forbid symlink creation can
    still exercise the rejection path. Every component is checked with lstat
    semantics before the final canonical-path containment check.
    """
    check_link = is_symlink or (lambda p: p.is_symlink())
    root = Path(site_root)
    if check_link(root):
        raise SafePathError("SYMLINK", "the site root must not be a symlink")
    if not root.is_dir():
        raise SafePathError("NOT_A_SITE", "site root is not a directory")
    real_root = root.resolve(strict=True)
    if check_link(real_root):
        raise SafePathError("SYMLINK", "the site root resolves through a symlink")

    if candidates is None:
        found = []

        def walk(directory: Path, parts: tuple):
            try:
                entries = sorted(os.scandir(directory), key=lambda e: e.name)
            except OSError:
                raise SafePathError("UNREADABLE", "site directory cannot be read")
            for entry in entries:
                name = entry.name
                if hidden_predicate(name):
                    continue
                path = Path(entry.path)
                if check_link(path):
                    raise SafePathError("SYMLINK", "symlinks are never published")
                child = parts + (name,)
                if entry.is_dir(follow_symlinks=False):
                    walk(path, child)
                elif entry.is_file(follow_symlinks=False):
                    found.append("/".join(child))
        walk(root, ())
        candidates = found

    selected = []
    seen = set()
    for candidate in sorted(str(c) for c in candidates):
        raw = candidate.replace("\\", "/")
        if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
            raise SafePathError("ABSOLUTE", "publish paths must be relative")
        parts = tuple(p for p in raw.split("/") if p not in ("", "."))
        if not parts or any(p == ".." for p in parts):
            raise SafePathError("TRAVERSAL", "publish path escapes the site folder")
        if any(hidden_predicate(p) for p in parts):
            raise SafePathError("HIDDEN", "hidden files are never published")
        relative = "/".join(parts)
        if relative in seen:
            continue
        seen.add(relative)
        current = root
        for part in parts:
            current = current / part
            if check_link(current):
                raise SafePathError("SYMLINK", "symlinks are never published")
            if not current.exists():
                raise SafePathError("MISSING", "publish path does not exist")
        if current.is_dir():
            raise SafePathError("NOT_A_FILE", "publish path is a directory")
        mode = os.lstat(current).st_mode
        if not stat.S_ISREG(mode):
            raise SafePathError("NOT_A_FILE", "only regular files are published")
        resolved = current.resolve(strict=True)
        if not _within(real_root, resolved) or resolved == real_root:
            raise SafePathError("TRAVERSAL", "publish path escapes the site folder")
        data = current.read_bytes()
        selected.append(PublishFile(
            relative=relative, source=resolved, size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ))
    return tuple(sorted(selected, key=lambda f: f.relative))


def build_publish_manifest(site_root: str | Path, candidates=None, **kwargs) -> PublishManifest:
    files = select_publish_files(site_root, candidates, **kwargs)
    payload = "".join("{0}\0{1}\0{2}\n".format(f.relative, f.size, f.sha256) for f in files)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return PublishManifest(version="1", root=Path(site_root).name, digest=digest, files=files)


# ===========================================================================
# W7.17 - inbound channel rules
# ===========================================================================

FRESHNESS_WINDOW_SECONDS = 300
DEFAULT_NONCE_CACHE_SIZE = 4096
MAX_INBOUND_BODY_BYTES = 1_000_000


class InboundVerificationError(ValueError):
    def __init__(self, reason: str, message: str = ""):
        self.reason = reason
        super().__init__(message or ("inbound message rejected: " + reason))


class Channel(str, Enum):
    EMAIL = "email"
    CHAT = "chat"
    VOICE = "voice"
    PHONE = "phone"
    WEBHOOK = "webhook"


@dataclass(frozen=True)
class VerifiedMessage:
    sender: str
    channel: Channel
    body: str
    timestamp: int
    nonce: str
    signature: str


def _secret_bytes(secret) -> bytes:
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    if not isinstance(secret, (bytes, bytearray)) or not bytes(secret):
        raise InboundVerificationError("NO_SECRET", "no inbound channel secret is configured")
    return bytes(secret)


def _canonical_message(sender: str, timestamp: int, nonce: str, body: str) -> bytes:
    payload = json.dumps([sender, int(timestamp), nonce, body],
                         ensure_ascii=False, separators=(",", ":"))
    return b"keel-inbound-v1\x00" + payload.encode("utf-8")


def is_clean_email_body(body: str) -> bool:
    """Conservative check for 'clean mail': plain text, no active content."""
    if not isinstance(body, str) or not body or len(body) > 20_000:
        return False
    if any((ord(c) < 32 and c not in "\n\t") or ord(c) == 127 for c in body):
        return False
    if "<" in body or ">" in body or "javascript:" in body.lower() or "data:" in body.lower():
        return False
    if re.search(r"on[a-z]+\s*=", body, re.IGNORECASE):
        return False
    return True


@dataclass(frozen=True)
class ChannelRule:
    channel: Channel
    allowed_senders: frozenset
    owner_only: bool = False
    plain_text_only: bool = False
    require_confirmation: bool = False
    pairing_required: bool = True


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str
    channel: Channel
    sender: str


def default_channel_rules(owner_email: str) -> dict:
    owner = str(owner_email).strip().lower()
    if not owner or "@" not in owner:
        raise ValueError("an owner email is required for inbound channel defaults")
    return {
        Channel.EMAIL: ChannelRule(Channel.EMAIL, frozenset({owner}), owner_only=True, plain_text_only=True),
        Channel.VOICE: ChannelRule(Channel.VOICE, frozenset({owner}), require_confirmation=True),
        Channel.PHONE: ChannelRule(Channel.PHONE, frozenset({owner}), require_confirmation=True),
        Channel.CHAT: ChannelRule(Channel.CHAT, frozenset()),
        Channel.WEBHOOK: ChannelRule(Channel.WEBHOOK, frozenset()),
    }


def admit_channel_message(
    sender: str,
    channel: Channel,
    body: str,
    rules: Mapping[Channel, ChannelRule],
    *,
    confirmation_code: str | None = None,
    expected_confirmation_code: str | None = None,
) -> AdmissionDecision:
    try:
        channel = Channel(channel)
    except ValueError:
        return AdmissionDecision(False, "UNKNOWN_CHANNEL", channel, str(sender))
    sender_norm = str(sender).strip().lower()
    rule = rules.get(channel)
    if rule is None or not sender_norm:
        return AdmissionDecision(False, "SENDER_NOT_APPROVED", channel, sender_norm)
    if not rule.allowed_senders:
        return AdmissionDecision(False, "PAIRING_REQUIRED", channel, sender_norm)
    if sender_norm not in rule.allowed_senders:
        return AdmissionDecision(False, "SENDER_NOT_APPROVED", channel, sender_norm)
    if rule.plain_text_only and not is_clean_email_body(body):
        return AdmissionDecision(False, "UNSAFE_CONTENT", channel, sender_norm)
    if rule.require_confirmation:
        if not confirmation_code or not expected_confirmation_code:
            return AdmissionDecision(False, "CONFIRMATION_REQUIRED", channel, sender_norm)
        if not hmac.compare_digest(str(confirmation_code).strip(), str(expected_confirmation_code).strip()):
            return AdmissionDecision(False, "CONFIRMATION_MISMATCH", channel, sender_norm)
    return AdmissionDecision(True, "ALLOWED", channel, sender_norm)


class InboundChannelVerifier:
    """Fail-closed inbound signature verifier.

    Signature = hex(HMAC-SHA256(secret, "keel-inbound-v1\\0" || JSON([sender,
    timestamp, nonce, body]))). Comparison is constant-time. Nonces are
    cached per (channel, sender) in a bounded LRU to stop replay.
    """

    def __init__(
        self,
        secret,
        *,
        approved_senders: Iterable[str] = (),
        now: Callable[[], float] = time.time,
        freshness_window: int = FRESHNESS_WINDOW_SECONDS,
        nonce_cache_size: int = DEFAULT_NONCE_CACHE_SIZE,
        require_confirmation: bool = False,
    ):
        self.secret = secret
        self.approved_senders = frozenset(str(s).strip().lower() for s in approved_senders if s)
        self.now = now
        self.freshness_window = int(freshness_window)
        self.nonce_cache_size = max(1, int(nonce_cache_size))
        self.require_confirmation = bool(require_confirmation)
        self._cache = OrderedDict()
        self._lock = threading.RLock()

    @property
    def nonce_cache(self) -> OrderedDict:
        return self._cache

    @staticmethod
    def sign(secret, sender: str, timestamp: int, nonce: str, body: str) -> str:
        key = _secret_bytes(secret)
        sender_norm = str(sender).strip().lower()
        return hmac.new(key, _canonical_message(sender_norm, int(timestamp), str(nonce), str(body)),
                        hashlib.sha256).hexdigest()

    def verify(
        self,
        *,
        sender: str,
        timestamp,
        nonce: str,
        body: str,
        signature: str,
        channel: Channel = Channel.WEBHOOK,
    ) -> VerifiedMessage:
        key = _secret_bytes(self.secret)  # NO_SECRET before anything else
        if not isinstance(sender, str) or not sender.strip() or "\x00" in sender:
            raise InboundVerificationError("MALFORMED_MESSAGE", "invalid sender")
        sender_norm = sender.strip().lower()
        if not self.approved_senders or sender_norm not in self.approved_senders:
            raise InboundVerificationError("SENDER_NOT_APPROVED", "sender is not approved")
        if not isinstance(nonce, str) or not 1 <= len(nonce) <= 256 or any(
                ord(c) < 32 or ord(c) == 127 for c in nonce):
            raise InboundVerificationError("MALFORMED_MESSAGE", "invalid nonce")
        if not isinstance(body, str) or len(body.encode("utf-8")) > MAX_INBOUND_BODY_BYTES:
            raise InboundVerificationError("MALFORMED_MESSAGE", "invalid body")
        if isinstance(timestamp, bool):
            raise InboundVerificationError("MALFORMED_MESSAGE", "invalid timestamp")
        try:
            ts = int(str(timestamp).strip())
        except (ValueError, TypeError):
            raise InboundVerificationError("MALFORMED_MESSAGE", "invalid timestamp") from None
        if ts <= 0:
            raise InboundVerificationError("MALFORMED_MESSAGE", "invalid timestamp")
        delta = float(self.now()) - ts
        if delta > self.freshness_window:
            raise InboundVerificationError("STALE", "message is outside the freshness window")
        if delta < -self.freshness_window:
            raise InboundVerificationError("FUTURE", "message timestamp is in the future")
        if not isinstance(signature, str):
            raise InboundVerificationError("BAD_SIGNATURE", "invalid signature")
        raw = signature[7:] if signature.startswith("sha256=") else signature
        try:
            provided = bytes.fromhex(raw)
        except ValueError:
            raise InboundVerificationError("BAD_SIGNATURE", "invalid signature") from None
        expected = hmac.new(key, _canonical_message(sender_norm, ts, nonce, body), hashlib.sha256).digest()
        if len(provided) != len(expected) or not hmac.compare_digest(provided, expected):
            raise InboundVerificationError("BAD_SIGNATURE", "invalid signature")
        try:
            channel = Channel(channel)
        except ValueError:
            raise InboundVerificationError("MALFORMED_MESSAGE", "unknown channel") from None
        cache_key = (channel.value, sender_norm, nonce)
        with self._lock:
            if cache_key in self._cache:
                raise InboundVerificationError("NONCE_REPLAY", "nonce has already been used")
            self._cache[cache_key] = True
            self._cache.move_to_end(cache_key)
            while len(self._cache) > self.nonce_cache_size:
                self._cache.popitem(last=False)
        return VerifiedMessage(sender_norm, channel, body, ts, nonce, signature)


# ===========================================================================
# W7.3 - AES-256-GCM sealing and session cookie (pure stdlib)
# ===========================================================================

class SealVerificationError(ValueError):
    pass


class SessionRevokedError(ValueError):
    pass


class SessionExpiredError(ValueError):
    pass


SECRET_KEY_BYTES = 32
_GCM_IV_BYTES = 12
_GCM_TAG_BYTES = 16


def _gf_mul(a: int, b: int) -> int:
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        high = a & 0x80
        a = (a << 1) & 0xFF
        if high:
            a ^= 0x1B
        b >>= 1
    return result


def _gf_pow(a: int, n: int) -> int:
    result = 1
    base = a
    while n:
        if n & 1:
            result = _gf_mul(result, base)
        base = _gf_mul(base, base)
        n >>= 1
    return result


def _build_sbox() -> bytes:
    box = bytearray(256)
    for i in range(256):
        inv = 0 if i == 0 else _gf_pow(i, 254)
        value = inv ^ 0x63
        for rotation in range(1, 5):
            value ^= ((inv << rotation) | (inv >> (8 - rotation))) & 0xFF
        box[i] = value
    return bytes(box)


_SBOX = _build_sbox()


def _xtime(a: int) -> int:
    return ((a << 1) & 0xFF) ^ (0x1B if a & 0x80 else 0)


def _expand_key(key: bytes) -> list:
    if not isinstance(key, (bytes, bytearray)) or len(key) != SECRET_KEY_BYTES:
        raise ValueError("AES-256 requires a 32-byte key")
    data = bytes(key)
    words = [list(data[i:i + 4]) for i in range(0, SECRET_KEY_BYTES, 4)]
    rcon = 1
    for i in range(8, 60):
        temp = words[-1][:]
        if i % 8 == 0:
            temp = [_SBOX[b] for b in temp[1:] + temp[:1]]
            temp[0] ^= rcon
            rcon = _xtime(rcon)
        elif i % 8 == 4:
            temp = [_SBOX[b] for b in temp]
        words.append([words[i - 8][j] ^ temp[j] for j in range(4)])
    return [bytes(b for word in words[r * 4:(r + 1) * 4] for b in word) for r in range(15)]


def _aes_encrypt_block(block: bytes, round_keys: list) -> bytes:
    state = list(block)

    def add_round(key):
        for i in range(16):
            state[i] ^= key[i]

    add_round(round_keys[0])
    for round_index in range(1, 15):
        state = [_SBOX[b] for b in state]
        state = [state[r + 4 * ((c + r) % 4)] for c in range(4) for r in range(4)]
        if round_index != 14:
            for c in range(4):
                i = 4 * c
                a0, a1, a2, a3 = state[i:i + 4]
                total = a0 ^ a1 ^ a2 ^ a3
                original = a0
                state[i] = a0 ^ total ^ _xtime(a0 ^ a1)
                state[i + 1] = a1 ^ total ^ _xtime(a1 ^ a2)
                state[i + 2] = a2 ^ total ^ _xtime(a2 ^ a3)
                state[i + 3] = a3 ^ total ^ _xtime(a3 ^ original)
        add_round(round_keys[round_index])
    return bytes(state)


_R = 0xE1000000000000000000000000000000


def _gf128_mul(x: int, y: int) -> int:
    z = 0
    v = y
    for i in range(128):
        if x & (1 << (127 - i)):
            z ^= v
        v = (v >> 1) ^ _R if v & 1 else v >> 1
    return z


def _ghash(h: int, aad: bytes, ciphertext: bytes) -> int:
    data = aad + b"\x00" * ((-len(aad)) % 16)
    data += ciphertext + b"\x00" * ((-len(ciphertext)) % 16)
    data += (((len(aad) * 8) << 64) | (len(ciphertext) * 8)).to_bytes(16, "big")
    y = 0
    for offset in range(0, len(data), 16):
        y = _gf128_mul(y ^ int.from_bytes(data[offset:offset + 16], "big"), h)
    return y


def _inc32(value: int) -> int:
    return (value & ~0xFFFFFFFF) | ((value + 1) & 0xFFFFFFFF)


def _gcm_j0(h: int, iv: bytes, round_keys: list) -> int:
    if len(iv) == _GCM_IV_BYTES:
        return int.from_bytes(iv + b"\x00\x00\x00\x01", "big")
    data = iv + b"\x00" * ((-len(iv)) % 16) + (len(iv) * 8).to_bytes(16, "big")
    y = 0
    for offset in range(0, len(data), 16):
        y = _gf128_mul(y ^ int.from_bytes(data[offset:offset + 16], "big"), h)
    return y


def _gctr(round_keys: list, initial_counter: int, data: bytes) -> bytes:
    out = bytearray()
    counter = initial_counter
    for offset in range(0, len(data), 16):
        stream = _aes_encrypt_block(counter.to_bytes(16, "big"), round_keys)
        chunk = data[offset:offset + 16]
        out.extend(a ^ b for a, b in zip(chunk, stream))
        counter = _inc32(counter)
    return bytes(out)


@dataclass(frozen=True)
class SealedSecret:
    version: int
    iv: bytes
    ciphertext: bytes
    tag: bytes
    text: bool = True


def aes_gcm_seal(plaintext: bytes, key: bytes, aad: bytes = b"", *, iv: Optional[bytes] = None) -> SealedSecret:
    """AES-256-GCM with a fresh random 12-byte IV and a 16-byte auth tag."""
    round_keys = _expand_key(key)
    nonce = bytes(iv) if iv is not None else _secrets.token_bytes(_GCM_IV_BYTES)
    if len(nonce) != _GCM_IV_BYTES:
        raise ValueError("GCM IV must be exactly 12 bytes")
    aad = aad or b""
    h = int.from_bytes(_aes_encrypt_block(bytes(16), round_keys), "big")
    j0 = _gcm_j0(h, nonce, round_keys)
    ciphertext = _gctr(round_keys, _inc32(j0), bytes(plaintext))
    tag_input = _ghash(h, aad, ciphertext).to_bytes(16, "big")
    tag = _gctr(round_keys, j0, tag_input)[:_GCM_TAG_BYTES]
    return SealedSecret(1, nonce, ciphertext, tag, text=False)


def aes_gcm_open(sealed: SealedSecret, key: bytes, aad: bytes = b"") -> bytes:
    if not isinstance(sealed, SealedSecret) or sealed.version != 1:
        raise SealVerificationError("unsupported sealed value")
    if len(sealed.iv) != _GCM_IV_BYTES or len(sealed.tag) != _GCM_TAG_BYTES:
        raise SealVerificationError("malformed sealed value")
    round_keys = _expand_key(key)
    h = int.from_bytes(_aes_encrypt_block(bytes(16), round_keys), "big")
    j0 = _gcm_j0(h, bytes(sealed.iv), round_keys)
    tag_input = _ghash(h, aad or b"", bytes(sealed.ciphertext)).to_bytes(16, "big")
    expected = _gctr(round_keys, j0, tag_input)[:_GCM_TAG_BYTES]
    if not hmac.compare_digest(expected, bytes(sealed.tag)):
        raise SealVerificationError("authentication failed")
    return _gctr(round_keys, _inc32(j0), bytes(sealed.ciphertext))


def seal_secret(value, key: bytes, aad: bytes = b"keel-secret-v1") -> SealedSecret:
    is_text = isinstance(value, str)
    raw = value.encode("utf-8") if is_text else bytes(value)
    sealed = aes_gcm_seal(raw, key, aad)
    return SealedSecret(sealed.version, sealed.iv, sealed.ciphertext, sealed.tag, text=is_text)


def open_secret(sealed: SealedSecret, key: bytes, aad: bytes = b"keel-secret-v1"):
    raw = aes_gcm_open(sealed, key, aad)
    return raw.decode("utf-8") if sealed.text else raw


@dataclass(frozen=True)
class SessionCookiePolicy:
    max_age: int = 30 * 24 * 60 * 60  # 30 days
    same_site: str = "Lax"
    http_only: bool = True
    secure_when_https: bool = True
    path: str = "/"
    aad: bytes = b"keel-session-v1"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(token: str) -> bytes:
    if not isinstance(token, str) or not token:
        raise ValueError("empty session cookie")
    return base64.urlsafe_b64decode(token + "=" * ((-len(token)) % 4))


def seal_session_cookie(
    payload: Mapping[str, Any],
    key: bytes,
    *,
    aad: bytes = b"keel-session-v1",
    now: Optional[float] = None,
    policy: SessionCookiePolicy = SessionCookiePolicy(),
) -> str:
    if aad != policy.aad:
        raise ValueError("session cookies must use the session AAD")
    current = int(time.time() if now is None else now)
    body = dict(payload)
    if "exp" not in body or int(body["exp"]) <= current:
        raise ValueError("session payload needs a future exp")
    sealed = aes_gcm_seal(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                          key, aad)
    return _b64encode(bytes([1]) + sealed.iv + sealed.tag + sealed.ciphertext)


def open_session_cookie(
    token: str,
    key: bytes,
    *,
    aad: bytes = b"keel-session-v1",
    now: Optional[float] = None,
    revoked_session_ids: Iterable[str] = (),
) -> dict:
    if aad != SessionCookiePolicy().aad:
        raise ValueError("session cookies must use the session AAD")
    raw = _b64decode(token)
    if len(raw) < 1 + _GCM_IV_BYTES + _GCM_TAG_BYTES or raw[0] != 1:
        raise SealVerificationError("malformed session cookie")
    offset = 1
    iv = raw[offset:offset + _GCM_IV_BYTES]
    offset += _GCM_IV_BYTES
    tag = raw[offset:offset + _GCM_TAG_BYTES]
    offset += _GCM_TAG_BYTES
    sealed = SealedSecret(1, iv, raw[offset:], tag, text=False)
    body = json.loads(aes_gcm_open(sealed, key, aad).decode("utf-8"))
    current = int(time.time() if now is None else now)
    if int(body.get("exp", 0)) <= current:
        raise SessionExpiredError("session cookie has expired")
    sid = body.get("sid")
    if sid is not None and str(sid) in {str(s) for s in revoked_session_ids}:
        raise SessionRevokedError("session has been revoked")
    return body


def session_cookie_header(name: str, value: str, *, https: bool,
                          policy: SessionCookiePolicy = SessionCookiePolicy()) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError("invalid cookie name")
    if any(ord(c) < 33 or ord(c) == 127 or c in ";,\\" for c in value):
        raise ValueError("invalid cookie value")
    parts = ["{0}={1}".format(name, value), "Path={0}".format(policy.path)]
    if policy.http_only:
        parts.append("HttpOnly")
    parts.append("SameSite={0}".format(policy.same_site))
    if https and policy.secure_when_https:
        parts.append("Secure")
    parts.append("Max-Age={0}".format(int(policy.max_age)))
    return "; ".join(parts)


# ===========================================================================
# W7.4 - API keys
# ===========================================================================

API_KEY_PREFIX = "keel_live_"


@dataclass(frozen=True)
class ApiKeyIssueResult:
    token: str
    key_id: str
    digest: str
    created_at: float
    owner: str = ""


def hash_api_key(token: str) -> str:
    if not isinstance(token, str) or not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_api_key(*, owner: str = "", now: Optional[float] = None) -> ApiKeyIssueResult:
    token = API_KEY_PREFIX + _secrets.token_urlsafe(32)
    key_id = API_KEY_PREFIX + _secrets.token_urlsafe(9)
    return ApiKeyIssueResult(token=token, key_id=key_id, digest=hash_api_key(token),
                             created_at=float(time.time() if now is None else now), owner=owner)


def verify_api_key(token: str, expected_digest: str) -> bool:
    digest = hash_api_key(token)
    if not digest or not isinstance(expected_digest, str) or len(expected_digest) != 64:
        return False
    return hmac.compare_digest(digest, expected_digest)


@dataclass(frozen=True)
class ApiKeyDecision:
    allowed: bool
    reason: str = "ALLOWED"
    retry_after: float = 0.0
    duplicate: bool = False
    cached_fingerprint: Optional[str] = None


@dataclass
class ApiKeyStore:
    rate_limit: int = 60
    window_seconds: float = 60.0
    now: Callable[[], float] = time.time

    _keys: dict = field(default_factory=dict, repr=False)
    _hits: dict = field(default_factory=dict, repr=False)
    _idempotency: dict = field(default_factory=dict, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def register(self, key_id: str, digest: str, *, owner: str) -> None:
        if not key_id or not digest or not owner:
            raise ValueError("key id, digest and owner are required")
        with self._lock:
            self._keys[key_id] = (digest, owner)
            self._hits.setdefault(key_id, deque())

    def consume(self, key_id: str, owner: str, idempotency_key: Optional[str] = None,
                fingerprint: str = "") -> ApiKeyDecision:
        current = float(self.now())
        with self._lock:
            record = self._keys.get(key_id)
            if record is None or record[1] != owner:
                return ApiKeyDecision(False, "UNKNOWN_KEY")
            idem = (owner, idempotency_key) if idempotency_key else None
            if idem is not None and idem in self._idempotency:
                cached = self._idempotency[idem]
                if cached != fingerprint:
                    return ApiKeyDecision(False, "IDEMPOTENCY_CONFLICT")
                return ApiKeyDecision(True, "IDEMPOTENT_REPLAY", duplicate=True, cached_fingerprint=cached)
            hits = self._hits.setdefault(key_id, deque())
            while hits and hits[0] <= current - self.window_seconds:
                hits.popleft()
            if len(hits) >= self.rate_limit:
                retry_after = max(0.001, hits[0] + self.window_seconds - current)
                return ApiKeyDecision(False, "RATE_LIMITED", retry_after=retry_after)
            hits.append(current)
            if idem is not None:
                self._idempotency[idem] = fingerprint
            return ApiKeyDecision(True)


# ===========================================================================
# W7.5 - staged secrets for child processes
# ===========================================================================

@dataclass(frozen=True)
class StagedSecretPlan:
    file_path: str
    env: Mapping[str, str]
    argv: tuple
    setup_script: str


_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_setup_script(names: Iterable[str]) -> str:
    """Python snippet run by the child setup step: read env, then delete file."""
    declared = tuple(names)
    if any(not _NAME_RE.match(str(n)) for n in declared):
        raise ValueError("invalid environment variable name")
    return (
        'import json, os\n'
        '_path = os.environ.get("KEEL_STAGED_SECRETS", "")\n'
        'if not _path:\n'
        '    raise SystemExit("staged secrets path is missing")\n'
        'try:\n'
        '    with open(_path, "r", encoding="utf-8") as _fh:\n'
        '        _values = json.load(_fh)\n'
        '    for _name, _value in _values.items():\n'
        '        os.environ[_name] = str(_value)\n'
        'finally:\n'
        '    try:\n'
        '        os.unlink(_path)\n'
        '    except FileNotFoundError:\n'
        '        pass\n'
    )


def stage_secrets(values: Mapping[str, str], stage_dir: str | Path,
                  *, base_env: Optional[Mapping[str, str]] = None) -> StagedSecretPlan:
    """Write secrets to a 0600 file; argv and env carry only the file path."""
    directory = Path(stage_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    clean = {}
    for name, value in values.items():
        if not _NAME_RE.match(str(name)) or not isinstance(value, str) or not value:
            raise ValueError("secret name/value is invalid")
        clean[str(name)] = value
    path = directory / ("keel-secrets-" + _secrets.token_hex(8) + ".json")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(clean, handle, sort_keys=True, separators=(",", ":"))
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    try:
        # Windows only exposes a read-only bit; drop all write bits there.
        os.chmod(path, stat.S_IREAD if os.name == "nt" else 0o600)
    except OSError:
        pass
    env = dict(base_env or {})
    env["KEEL_STAGED_SECRETS"] = str(path)
    argv = ("keel", "child-runtime", "--staged-secrets", str(path))
    return StagedSecretPlan(file_path=str(path), env=env, argv=argv,
                            setup_script=build_setup_script(clean.keys()))


def consume_staged_secrets(path: str | Path) -> dict:
    """Read a staged secret file and delete it even if parsing fails."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            values = json.load(handle)
    finally:
        if os.name == "nt":
            # Windows models the POSIX write bits as a read-only attribute;
            # clear it so the staged file can actually be removed.
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    if not isinstance(values, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                           for k, v in values.items()):
        raise ValueError("malformed staged secrets file")
    return values


def assert_no_secrets_in_argv(argv: Iterable[str], secret_values: Iterable[str]) -> None:
    args = [str(a) for a in argv]
    for secret in secret_values:
        if not secret:
            continue
        if any(str(secret) in arg for arg in args):
            raise ValueError("secret material must never appear in a child command line")


# ===========================================================================
# W7.6 - log redaction and keyed pseudonyms
# ===========================================================================

class NoHashKeyError(ValueError):
    pass


DEFAULT_REDACTION_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{12,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{12,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret)\s*[=:]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


class LogRedactor:
    def __init__(self, *, hash_key=None, secret_values: Iterable[str] = (),
                 extra_patterns: Iterable[str] = ()):
        self.hash_key = hash_key.encode("utf-8") if isinstance(hash_key, str) else hash_key
        self.secret_values = tuple(sorted((str(v) for v in secret_values if v), key=len, reverse=True))
        self.patterns = DEFAULT_REDACTION_PATTERNS + tuple(re.compile(p) for p in extra_patterns)

    def redact(self, text: str) -> str:
        result = str(text)
        for value in self.secret_values:
            result = result.replace(value, "[REDACTED]")
        for pattern in self.patterns:
            result = pattern.sub("[REDACTED]", result)
        return result

    def pseudonymize(self, identifier: str, *, namespace: str = "user") -> str:
        if not self.hash_key:
            raise NoHashKeyError("a configured key is required for stable pseudonyms")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", namespace):
            raise ValueError("invalid pseudonym namespace")
        digest = hmac.new(bytes(self.hash_key),
                          (namespace + "\x00" + str(identifier)).encode("utf-8"),
                          hashlib.blake2b).hexdigest()[:16]
        return "{0}_{1}".format(namespace, digest)


# ===========================================================================
# W7.8 - trusted proxy, pairing limits, relative return path
# ===========================================================================

class UnsafeRedirectError(ValueError):
    pass


@dataclass(frozen=True)
class ClientAddress:
    address: str
    source: str


def client_address_from_headers(
    headers: Mapping[str, str],
    *,
    remote_addr: Optional[str] = None,
    trusted_proxy_hops: int = 0,
    trusted_proxy_ips: Iterable[str] = (),
) -> ClientAddress:
    lowered = {str(k).lower(): v for k, v in (headers or {}).items()}
    direct = str(remote_addr).strip() if remote_addr else ""
    if _ip_of(direct) is None:
        direct = ""
    hops = max(0, int(trusted_proxy_hops))
    xff = lowered.get("x-forwarded-for", "")
    trusted = {str(ip).strip() for ip in trusted_proxy_ips}
    if hops and direct and direct in trusted and isinstance(xff, str):
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= hops:
            candidate = parts[-hops]
            if _ip_of(candidate) is not None:
                return ClientAddress(candidate, "trusted_proxy")
    if not direct:
        return ClientAddress("", "missing")
    return ClientAddress(direct, "direct")


def safe_return_path(path: str) -> str:
    if not isinstance(path, str) or not path or not path.startswith("/") or path.startswith("//"):
        raise UnsafeRedirectError("return path must be a same-origin relative path")
    if "\\" in path or any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise UnsafeRedirectError("return path contains unsafe characters")
    if urlsplit(path).scheme:
        raise UnsafeRedirectError("return path must not have a scheme")
    if any(part == ".." for part in path.split("/")):
        raise UnsafeRedirectError("return path must not traverse directories")
    return path


@dataclass
class PairingRateLimiter:
    max_per_address: int = 5
    max_global: int = 30
    window_seconds: float = 300.0
    now: Callable[[], float] = time.time

    _per_address: dict = field(default_factory=dict, repr=False)
    _global: deque = field(default_factory=deque, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def check(self, address: str) -> ApiKeyDecision:
        if not address or _ip_of(address) is None:
            return ApiKeyDecision(False, "UNKNOWN_ADDRESS")
        current = float(self.now())
        with self._lock:
            own = self._per_address.setdefault(address, deque())
            while own and own[0] <= current - self.window_seconds:
                own.popleft()
            while self._global and self._global[0] <= current - self.window_seconds:
                self._global.popleft()
            if len(own) >= self.max_per_address or len(self._global) >= self.max_global:
                return ApiKeyDecision(False, "RATE_LIMITED", retry_after=self.window_seconds)
            own.append(current)
            self._global.append(current)
            return ApiKeyDecision(True)
