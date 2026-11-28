"""Optional, local-first browser automation runtime for Keel.

This module provides an in-product browser *runtime*: named sessions with a
single owner, a domain allowlist that page content can never widen, structured
frame-aware snapshots with stable refs, action primitives (click/type/fill/
scroll), screenshot artifacts, download/upload where the driver supports them,
bounded output, cooperative timeouts/cancellation and a redacted event log.

Scope and limitations, stated plainly:

* **Local-first and optional.** Core operation uses only the Python standard
  library plus a supplied driver (including the in-memory fake in this
  module). Playwright is an *optional adapter*: it is imported lazily and, if
  unavailable, capability reporting says ``available=False``. No operation
  ever reports a fake success because a driver or Playwright is missing.
* **No OS screen control.** This is DOM/CDP-style automation of a browser
  session supplied by a driver. It does not move the mouse on the desktop,
  read or click arbitrary screen coordinates, or control other applications.
* **All page content and tool results are untrusted data, never instructions.**
  Snapshots are escaped, labelled ``trust: "untrusted"``, carry no instruction
  field, redact editable/value-bearing nodes at capture time, and flag (but
  never obey) prompt-injection-shaped text.
* **Credentials are never sent to the page by the agent and never logged.**
  Credential-shaped values and sensitive fields are blocked; login/2FA/
  payment/sensitive steps require an explicit human ``handoff`` followed by
  ``resume`` validated by a host-supplied confirmation provider. A caller
  cannot self-assert user confirmation: with no provider configured, resume
  fails closed.

Nothing in this module launches a process, writes outside an explicit artifact
directory, or performs network I/O on import. DNS resolution is injected and
re-checked at navigation and on arrival to resist rebinding.
"""

from __future__ import annotations

import html
import importlib
import ipaddress
import re
import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

__all__ = [
    "BrowserRuntime",
    "BrowserSession",
    "DomainPolicy",
    "BrowserDriver",
    "FakeBrowserDriver",
    "PlaywrightDriver",
    "Snapshot",
    "FrameSnapshot",
    "NodeRef",
    "CallContext",
    "EventLog",
    "playwright_capability",
    "load_playwright",
    "redact_text",
    "BrowserRuntimeError",
    "PolicyError",
    "OwnerConflict",
    "StaleRef",
    "HandoffRequired",
    "BrowserTimeout",
    "BrowserCancelled",
    "MissingDriver",
    "CredentialBlocked",
    "UnsupportedCapability",
    "DriverError",
    "SessionClosed",
]


# ---------------------------------------------------------------------------
# Errors (typed, so callers cannot silently ignore a refusal)
# ---------------------------------------------------------------------------

class BrowserRuntimeError(RuntimeError):
    """Base class for honest, typed browser-runtime failures."""

    code = "browser_error"

    def __init__(self, message: str, *, code: str | None = None,
                 details: dict | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.details = dict(details or {})

    def as_dict(self) -> dict:
        return {"ok": False, "error": self.code, "message": str(self),
                "details": dict(self.details)}


class PolicyError(BrowserRuntimeError):
    code = "policy_error"


class OwnerConflict(BrowserRuntimeError):
    code = "owner_conflict"


class StaleRef(BrowserRuntimeError):
    code = "stale_ref"


class HandoffRequired(BrowserRuntimeError):
    code = "handoff_required"


class BrowserTimeout(BrowserRuntimeError):
    code = "timeout"


class BrowserCancelled(BrowserRuntimeError):
    code = "cancelled"


class MissingDriver(BrowserRuntimeError):
    code = "missing_driver"


class CredentialBlocked(BrowserRuntimeError):
    code = "credential_blocked"


class UnsupportedCapability(BrowserRuntimeError):
    code = "unsupported_capability"


class DriverError(BrowserRuntimeError):
    code = "driver_error"


class SessionClosed(BrowserRuntimeError):
    code = "session_closed"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?P<key>\b(?:password|passwd|passphrase|secret|token|api[_-]?key|"
    r"access[_-]?key|private[_-]?key|authorization|auth|pin|otp|cvv|"
    r"card[_-]?number)\b)\s*[:=]\s*(?P<quote>['\"]?)(?P<value>[^\s,;'\"}&\r\n]+)")
_SECRET_BEARER = re.compile(r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{4,}")
_SECRET_PREFIX = re.compile(
    r"\b(?:sk-or-v1-[A-Za-z0-9]{12,}|sk-[A-Za-z0-9_-]{16,}|"
    r"github_pat_[A-Za-z0-9_]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|"
    r"AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})\b")
_SECRET_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_CARD_LIKE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_INJECTION = re.compile(
    r"(?i)(?:ignore (?:all )?(?:previous|prior|above) instructions|"
    r"disregard (?:the )?(?:system|developer) (?:prompt|message)|"
    r"you must now|new system prompt|"
    r"(?:add|allow|whitelist|allowlist)\b.{0,40}\b(?:allowlist|domain|origin|site)\b|"
    r"send (?:me |us )?(?:the )?(?:password|secret|token|credentials))")

_OMIT_EVENT_KEYS = frozenset({
    "value", "text", "bytes", "body", "screenshot", "content", "credentials",
    "password", "token", "secret", "api_key", "authorization",
})


def redact_text(value: Any, *, limit: int = 256) -> str:
    """Redact credential-shaped substrings and bound the output length."""
    text = value if isinstance(value, str) else repr(value)
    text = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group('key')}=[REDACTED]", text)
    text = _SECRET_BEARER.sub("[REDACTED]", text)
    text = _SECRET_PREFIX.sub("[REDACTED]", text)
    text = _SECRET_JWT.sub("[REDACTED]", text)
    text = _CARD_LIKE.sub("[REDACTED]", text)
    if len(text) > limit:
        text = text[:limit] + "...[truncated]"
    return text


def _looks_like_credential(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if len(value) > 4096:
        return True
    for pattern in (_SECRET_PREFIX, _SECRET_JWT, _SECRET_BEARER, _CARD_LIKE):
        if pattern.search(value):
            return True
    # A short, high-entropy-looking token assigned to a credential-shaped key.
    if _SECRET_ASSIGNMENT.search(value) or re.match(
            r"(?i)^(?:password|passphrase|pin|otp|secret|token|cvv)\s*[:=]\s*\S+", value):
        return True
    return False


def _token(value: Any, field_name: str, *, max_len: int = 64) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise BrowserRuntimeError(f"invalid {field_name}", code="invalid_input")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        raise BrowserRuntimeError(f"invalid {field_name} characters", code="invalid_input")
    return value


# ---------------------------------------------------------------------------
# Cooperative deadlines / cancellation
# ---------------------------------------------------------------------------

class CallContext:
    """Deadline + cancel event handed to every driver call.

    Drivers must call :meth:`check` (or :meth:`sleep`) so timeouts and
    cancellation are cooperative and honest. A driver that ignores the context
    cannot be forcibly pre-empted; the runtime re-checks the deadline after
    the call returns and never hides that overrun.
    """

    def __init__(self, timeout_ms: float, cancel: threading.Event) -> None:
        self.timeout_ms = float(timeout_ms)
        self.deadline = time.monotonic() + self.timeout_ms / 1000.0
        self.cancel = cancel

    def check(self) -> None:
        if self.cancel.is_set():
            raise BrowserCancelled("operation cancelled")
        if time.monotonic() >= self.deadline:
            raise BrowserTimeout(f"operation timed out after {self.timeout_ms:g} ms")

    def sleep(self, seconds: float) -> None:
        """Cancel-aware sleep bounded by the deadline."""
        end = min(self.deadline, time.monotonic() + max(0.0, seconds))
        while True:
            self.check()
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            if self.cancel.wait(min(remaining, 0.05)):
                raise BrowserCancelled("operation cancelled")


# ---------------------------------------------------------------------------
# Domain allowlist (never widened by page content)
# ---------------------------------------------------------------------------

_DnsResolver = Callable[[str], Sequence[str]]
_MAX_URL_LEN = 2048
_MAX_RULES = 64


def _default_dns_resolver(host: str) -> Sequence[str]:
    """Resolve via the stdlib, failing closed on any error."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError("dns resolution failed") from exc
    return [str(info[4][0]) for info in infos if info[4]]


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _public_addresses(addresses: Sequence[Any]) -> bool:
    for candidate in addresses:
        try:
            address = ipaddress.ip_address(str(candidate))
        except ValueError:
            return False
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast or address.is_unspecified):
            return False
    return True


@dataclass(frozen=True)
class DomainPolicy:
    """Frozen per-session domain allowlist.

    Rules are exact hosts (``example.com``) or subdomain suffixes
    (``*.example.com``, which does not match the apex). A wildcard-only rule is
    rejected: there is no "allow everything" mode. IP literals and private/
    loopback destinations are never allowed, even if named explicitly.
    """

    hosts: tuple[str, ...]
    max_rules: int = _MAX_RULES

    def __init__(self, hosts: Sequence[str] = (), *, max_rules: int = _MAX_RULES) -> None:
        if isinstance(hosts, str):
            hosts = (hosts,)
        rules: list[str] = []
        for raw in hosts:
            if not isinstance(raw, str):
                raise PolicyError("invalid allowlist rule")
            rule = raw.strip().lower().rstrip(".")
            if not rule or rule == "*" or "*" in rule and not rule.startswith("*."):
                raise PolicyError("wildcard allowlist rules are not permitted",
                                  code="wildcard_rule_rejected")
            if rule.startswith("*."):
                tail = rule[2:]
            else:
                tail = rule
            if (not tail or len(rule) > 253 or _is_ip_literal(tail)
                    or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", tail)):
                raise PolicyError("invalid or non-domain allowlist rule")
            if rule not in rules:
                rules.append(rule)
        if not rules or len(rules) > max_rules:
            raise PolicyError("allowlist must have between 1 and "
                              f"{max_rules} rules")
        object.__setattr__(self, "hosts", tuple(rules))
        object.__setattr__(self, "max_rules", max_rules)

    def host_allowed(self, host: Any, *, resolve: bool = False,
                     dns_resolver: _DnsResolver | None = None) -> bool:
        """Host-only check (no DNS) used for passive content inspection."""
        if not isinstance(host, str) or not host:
            return False
        name = host.strip().lower().rstrip(".")
        if not name or _is_ip_literal(name):
            return False
        matched = False
        for rule in self.hosts:
            if rule.startswith("*."):
                suffix = rule[1:]  # ".example.com"
                matched = matched or (name.endswith(suffix) and name != suffix[1:])
            else:
                matched = matched or name == rule
        if not matched:
            return False
        if resolve:
            return self._public_host(name, dns_resolver)
        return True

    @staticmethod
    def _public_host(host: str, dns_resolver: _DnsResolver | None) -> bool:
        resolver = dns_resolver or _default_dns_resolver
        try:
            addresses = tuple(resolver(host))
        except Exception:
            return False
        return bool(addresses) and _public_addresses(addresses)

    def validate_url(self, url: Any, *, dns_resolver: _DnsResolver | None = None) -> str:
        """Validate a navigation target; return its normalized URL.

        Called *before* every navigation and again *on arrival* before any page
        content is read. DNS is re-checked on each call (rebinding defense).
        """
        if not isinstance(url, str) or not url or len(url) > _MAX_URL_LEN:
            raise PolicyError("invalid url", code="invalid_url")
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError as exc:
            raise PolicyError("invalid url port", code="invalid_url") from exc
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            raise PolicyError("unsupported url scheme", code="unsupported_scheme")
        if parts.username is not None or parts.password is not None:
            raise PolicyError("credentials in url are not permitted",
                              code="credentials_in_url")
        host = (parts.hostname or "").lower().rstrip(".")
        if not host:
            raise PolicyError("url has no host", code="missing_host")
        if _is_ip_literal(host):
            raise PolicyError("ip literal destinations are not allowed",
                              code="ip_literal_rejected")
        if not self.host_allowed(host):
            raise PolicyError(f"host {host!r} is not allow-listed", code="host_not_allowed")
        if port is not None and port not in (80, 443):
            raise PolicyError("disallowed port", code="invalid_port")
        if not self._public_host(host, dns_resolver):
            raise PolicyError(f"host {host!r} did not resolve to public addresses",
                              code="unsafe_host")
        netloc = host + (f":{port}" if port is not None else "")
        return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))

    def recheck_arrival(self, url: Any, *, dns_resolver: _DnsResolver | None = None) -> str:
        return self.validate_url(url, dns_resolver=dns_resolver)

    def derives_from(self, other: Any) -> bool:
        """True only when both policies have exactly the same frozen rules."""
        return isinstance(other, DomainPolicy) and self.hosts == other.hosts


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

class EventLog:
    """Bounded, redacted append-only log. Values are never stored verbatim."""

    def __init__(self, *, max_events: int = 200, clock: Callable[[], float] = time.time) -> None:
        self.max_events = max(1, int(max_events))
        self._clock = clock
        self._events: list[dict] = []

    def record(self, kind: str, **fields: Any) -> None:
        safe: dict[str, Any] = {}
        for key, value in fields.items():
            if key in _OMIT_EVENT_KEYS:
                safe[key] = "[omitted]"
            elif isinstance(value, str):
                safe[key] = redact_text(value)
            elif value is None or isinstance(value, (int, float, bool)):
                safe[key] = value
            else:
                safe[key] = redact_text(repr(value), limit=128)
        self._events.append({"kind": redact_text(kind, limit=64), "at": self._clock(), **safe})
        if len(self._events) > self.max_events:
            del self._events[:len(self._events) - self.max_events]

    def all(self) -> tuple[dict, ...]:
        return tuple(dict(event) for event in self._events)

    def __len__(self) -> int:
        return len(self._events)


# ---------------------------------------------------------------------------
# Structured, frame-aware snapshots with stable refs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NodeRef:
    """A stable reference to one node in one snapshot epoch."""

    id: str
    frame: int
    epoch: int
    role: str
    name: str

    def to_dict(self) -> dict:
        return {"id": self.id, "frame": self.frame, "epoch": self.epoch,
                "role": self.role, "name": self.name}


@dataclass(frozen=True)
class FrameSnapshot:
    index: int
    url: str
    title: str
    nodes: tuple[dict, ...]

    def to_dict(self) -> dict:
        return {"index": self.index, "url": self.url, "title": self.title,
                "nodes": [dict(node) for node in self.nodes]}


@dataclass(frozen=True)
class Snapshot:
    revision: int
    epoch: int
    url: str
    frames: tuple[FrameSnapshot, ...]
    refs: tuple[NodeRef, ...]
    truncated: bool
    flags: tuple[str, ...]
    trust: str = "untrusted"
    instructions: tuple[Any, ...] = ()

    def ref_map(self) -> dict[str, NodeRef]:
        return {ref.id: ref for ref in self.refs}

    def to_dict(self) -> dict:
        return {
            "ok": True,
            "revision": self.revision,
            "epoch": self.epoch,
            "url": self.url,
            "frames": [frame.to_dict() for frame in self.frames],
            "refs": [ref.to_dict() for ref in self.refs],
            "truncated": self.truncated,
            "flags": list(self.flags),
            "trust": self.trust,
            "instructions": [],
        }


def build_snapshot(raw: Any, *, url: str, epoch: int, revision: int,
                   policy: DomainPolicy, max_frames: int = 8, max_nodes: int = 200,
                   max_text: int = 400, max_total_chars: int = 20000) -> Snapshot:
    """Turn untrusted driver data into a bounded, escaped, redacted snapshot."""
    flags: list[str] = []
    if not isinstance(raw, dict):
        raw, flags = {}, flags + ["malformed_driver_data"]
    raw_frames = raw.get("frames", ())
    if not isinstance(raw_frames, (list, tuple)):
        raw_frames, flags = (), flags + ["malformed_driver_data"]

    frames: list[FrameSnapshot] = []
    refs: list[NodeRef] = []
    truncated = len(raw_frames) > max_frames
    total = 0
    node_budget = max_nodes

    for frame_no, frame in enumerate(raw_frames[:max_frames]):
        if not isinstance(frame, dict):
            flags.append("malformed_driver_data")
            continue
        frame_url = frame.get("url") or ""
        if isinstance(frame_url, str) and frame_url.startswith(("http://", "https://")):
            host = (urlsplit(frame_url).hostname or "").lower()
            if not policy.host_allowed(host):
                flags.append("blocked_frame")
                continue  # a page cannot widen the allowlist via iframe URLs
        nodes: list[dict] = []
        raw_nodes = frame.get("nodes", ())
        if not isinstance(raw_nodes, (list, tuple)):
            raw_nodes, flags = (), flags + ["malformed_driver_data"]
        for node in raw_nodes:
            if node_budget <= 0 or total >= max_total_chars:
                truncated = True
                break
            if not isinstance(node, dict):
                flags.append("malformed_driver_data")
                continue
            # Every page-controlled string is escaped; none is ever treated as
            # instructions in Keel's context or UI.
            role = html.escape(redact_text(node.get("role", "text"), limit=64))
            name = html.escape(redact_text(node.get("name", ""), limit=max_text))
            editable = bool(node.get("editable", False))
            # Value-bearing nodes are redacted *at capture*, never transported.
            text = "" if editable else html.escape(redact_text(node.get("text", ""),
                                                                limit=max_text))
            if len(text) > max_text:  # escaping can grow the string past the cap
                text = text[:max(0, max_text - 14)] + "...[truncated]"
            if node.get("value") not in (None, ""):
                text = ""
                flags.append("dropped_value_field")
            if _INJECTION.search(text) or _INJECTION.search(name):
                flags.append("suspected_prompt_injection")
            # The epoch is part of the id so an old ref string can never
            # silently point at a different node after navigation or a DOM
            # change; it becomes unknown instead of misleading.
            ref_id = f"f{frame_no}.e{len(nodes) + 1}@{epoch}"
            refs.append(NodeRef(ref_id, frame_no, epoch, role, name))
            nodes.append({"ref": ref_id, "role": role, "name": name,
                          "text": text, "editable": editable})
            total += len(text) + len(name)
            node_budget -= 1
        frames.append(FrameSnapshot(
            frame_no, html.escape(redact_text(frame_url, limit=512)),
            html.escape(redact_text(frame.get("title", ""), limit=256)),
            tuple(nodes)))

    return Snapshot(revision=revision, epoch=epoch, url=url,
                    frames=tuple(frames), refs=tuple(refs), truncated=truncated,
                    flags=tuple(sorted(set(flags))))


# ---------------------------------------------------------------------------
# Driver interface
# ---------------------------------------------------------------------------

class BrowserDriver(Protocol):
    """Transport interface implemented by the fake and the Playwright adapter.

    Implementations must honour ``ctx.check()``/``ctx.sleep()`` and must never
    treat page content as instructions.
    """

    def navigate(self, url: str, *, ctx: CallContext) -> str: ...

    def current_url(self, *, ctx: CallContext) -> str: ...

    def dom_version(self, *, ctx: CallContext) -> int: ...

    def snapshot(self, *, ctx: CallContext, max_nodes: int = 200, epoch: int = 0) -> dict: ...

    def click(self, ref: str, *, ctx: CallContext) -> None: ...

    def type_text(self, ref: str, text: str, *, ctx: CallContext) -> None: ...

    def fill(self, ref: str, value: str, *, ctx: CallContext) -> None: ...

    def scroll(self, delta: int, *, ctx: CallContext) -> None: ...

    def screenshot(self, *, ctx: CallContext) -> bytes: ...

    def download(self, ref: str, *, ctx: CallContext) -> bytes: ...

    def upload(self, ref: str, path: Path, *, ctx: CallContext) -> None: ...

    def capabilities(self) -> dict: ...

    def close(self, *, ctx: CallContext) -> None: ...


class FakeBrowserDriver:
    """Deterministic in-memory driver for tests and offline development."""

    def __init__(self, *, pages: dict[str, dict] | None = None,
                 capabilities: dict | None = None, delay_s: float = 0.0,
                 screenshot_bytes: bytes = b"\x89PNG\r\n\x1a\nfake") -> None:
        self.pages = dict(pages or {})
        self._url = "about:blank"
        self._dom = 0
        self._screenshot = screenshot_bytes
        self._caps = {"download": True, "upload": True, "screenshot": True,
                      "frames": True, **(capabilities or {})}
        self.delay_s = delay_s
        # Before the first navigate() the fake serves the first configured
        # page, so snapshots can be taken straight away in tests.
        self._default_page = next(iter(self.pages.values()), None)
        self.calls: list[tuple] = []
        self.clicked: list[str] = []
        self.typed: list[tuple[str, str]] = []
        # Simulation knobs used by adversarial tests.
        self.redirects: dict[str, str] = {}
        self.on_click: Callable[[str], None] | None = None

    def _page(self) -> dict:
        if self._url in _INTERNAL_URLS and self._default_page is not None:
            return self._default_page
        page = self.pages.get(self._url)
        if page is None:
            page_id = urlsplit(self._url).path or "/"
            page = self.pages.get(page_id)
        if page is None and self._default_page is not None:
            page = self._default_page
        if page is None:
            page = {"frames": [{"index": 0, "url": self._url, "title": "", "nodes": []}]}
        return page

    def _maybe_delay(self, ctx: CallContext) -> None:
        if self.delay_s:
            ctx.sleep(self.delay_s)

    def navigate(self, url: str, *, ctx: CallContext) -> str:
        ctx.check()
        self.calls.append(("navigate", url))
        self._maybe_delay(ctx)
        self._url = self.redirects.get(url, url)
        self._dom += 1
        ctx.check()
        return self._url

    def current_url(self, *, ctx: CallContext) -> str:
        ctx.check()
        return self._url

    def dom_version(self, *, ctx: CallContext) -> int:
        ctx.check()
        return self._dom

    def snapshot(self, *, ctx: CallContext, max_nodes: int = 200, epoch: int = 0) -> dict:
        ctx.check()
        self.calls.append(("snapshot",))
        self._maybe_delay(ctx)
        ctx.check()
        return self._page()

    def click(self, ref: str, *, ctx: CallContext) -> None:
        ctx.check()
        self.calls.append(("click", ref))
        self.clicked.append(ref)
        self._maybe_delay(ctx)
        if self.on_click is not None:
            self.on_click(ref)
        self._dom += 1
        ctx.check()

    def type_text(self, ref: str, text: str, *, ctx: CallContext) -> None:
        ctx.check()
        self.calls.append(("type_text", ref))
        self.typed.append((ref, text))
        self._maybe_delay(ctx)
        self._dom += 1
        ctx.check()

    def fill(self, ref: str, value: str, *, ctx: CallContext) -> None:
        ctx.check()
        self.calls.append(("fill", ref))
        self.typed.append((ref, value))
        self._maybe_delay(ctx)
        self._dom += 1
        ctx.check()

    def scroll(self, delta: int, *, ctx: CallContext) -> None:
        ctx.check()
        self.calls.append(("scroll", delta))
        self._maybe_delay(ctx)
        ctx.check()

    def screenshot(self, *, ctx: CallContext) -> bytes:
        ctx.check()
        self.calls.append(("screenshot",))
        self._maybe_delay(ctx)
        ctx.check()
        return self._screenshot

    def download(self, ref: str, *, ctx: CallContext) -> bytes:
        ctx.check()
        self.calls.append(("download", ref))
        self._maybe_delay(ctx)
        ctx.check()
        return b"downloaded-bytes"

    def upload(self, ref: str, path: Path, *, ctx: CallContext) -> None:
        ctx.check()
        self.calls.append(("upload", ref, str(path)))
        self._maybe_delay(ctx)
        ctx.check()

    def capabilities(self) -> dict:
        return dict(self._caps)

    def close(self, *, ctx: CallContext) -> None:
        ctx.check()
        self.calls.append(("close",))
        self._dom += 1


# ---------------------------------------------------------------------------
# Optional Playwright adapter (imported lazily, never at module import)
# ---------------------------------------------------------------------------

class CapabilityUnavailable(BrowserRuntimeError):
    code = "capability_unavailable"


def load_playwright(*, importer: Callable[[str], Any] | None = None) -> Any:
    """Import ``playwright.sync_api`` lazily; fail honestly if absent."""
    importer = importer or importlib.import_module
    try:
        return importer("playwright.sync_api")
    except Exception as exc:  # noqa: BLE001 - absence must be reported, not guessed
        raise CapabilityUnavailable(
            "playwright is not available in this environment",
            details={"reason": type(exc).__name__}) from exc


def playwright_capability(*, importer: Callable[[str], Any] | None = None) -> dict:
    """Report honest Playwright availability. Never implies a fake success."""
    try:
        load_playwright(importer=importer)
    except CapabilityUnavailable as exc:
        return {"available": False, "mode": "playwright-isolated",
                "reason": str(exc), "details": dict(exc.details)}
    return {"available": True, "mode": "playwright-isolated",
            "reason": "playwright.sync_api imported successfully", "details": {}}


_PW_SNAPSHOT_JS = """(opts) => {
  const out = [];
  let count = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (count >= opts.maxNodes) break;
    const tag = el.tagName.toLowerCase();
    if (tag === 'script' || tag === 'style' || tag === 'noscript') continue;
    const role = el.getAttribute('role') || tag;
    const name = el.getAttribute('aria-label') || el.getAttribute('title') || '';
    const editable = !!el.matches('input, textarea, select, [contenteditable="true"]')
      || tag === 'input' || tag === 'textarea' || tag === 'select';
    // Must match build_snapshot(): f<frame>.e<ordinal>@<epoch>.
    const ref = 'f' + opts.frame + '.e' + (count + 1) + '@' + opts.epoch;
    el.setAttribute('data-keel-ref', ref);
    let text = '';
    if (!editable) text = (el.textContent || '').trim().slice(0, 2000);
    out.push({ref: ref, role: role, name: name, text: text, editable: editable});
    count++;
  }
  return {url: location.href, title: document.title || '', nodes: out};
}"""


class PlaywrightDriver:
    """Optional adapter over a caller-supplied Playwright ``page``.

    Browser launch is the caller's choice; this adapter never downloads a
    browser and is never imported unless explicitly requested.
    """

    def __init__(self, page: Any, *, max_nodes: int = 200) -> None:
        self.page = page
        self._max_nodes = max_nodes
        self._dom = 0
        self._ref_frames: dict[str, Any] = {}
        try:
            page.on("framenavigated", lambda _frame: self._bump())
        except Exception:
            pass

    def _bump(self) -> None:
        self._dom += 1

    def _locator(self, ref: str) -> Any:
        frame = self._ref_frames.get(ref, self.page)
        return frame.locator(f'[data-keel-ref="{ref}"]')

    def navigate(self, url: str, *, ctx: CallContext) -> str:
        ctx.check()
        self.page.goto(url, wait_until="domcontentloaded", timeout=max(1, int(ctx.timeout_ms)))
        self._bump()
        ctx.check()
        return self.page.url

    def current_url(self, *, ctx: CallContext) -> str:
        ctx.check()
        return self.page.url

    def dom_version(self, *, ctx: CallContext) -> int:
        ctx.check()
        return self._dom

    def snapshot(self, *, ctx: CallContext, max_nodes: int = 200, epoch: int = 0) -> dict:
        ctx.check()
        frames: list[dict] = []
        for index, frame in enumerate([self.page, *self.page.frames]):
            if index >= 8:
                break
            ctx.check()
            try:
                data = frame.evaluate(_PW_SNAPSHOT_JS, {
                    "maxNodes": min(max_nodes, self._max_nodes),
                    "frame": index, "epoch": epoch})
            except Exception as exc:  # noqa: BLE001 - report, never fake a page
                raise DriverError("playwright snapshot failed",
                                  details={"reason": type(exc).__name__}) from exc
            if not isinstance(data, dict):
                raise DriverError("playwright snapshot returned invalid data")
            for node in data.get("nodes", [])[:max_nodes]:
                if isinstance(node, dict) and isinstance(node.get("ref"), str):
                    self._ref_frames[node["ref"]] = frame
            frames.append({"index": index, "url": data.get("url", ""),
                           "title": data.get("title", ""), "nodes": data.get("nodes", [])})
            ctx.check()
        ctx.check()
        return {"frames": frames}

    def click(self, ref: str, *, ctx: CallContext) -> None:
        ctx.check()
        self._locator(ref).click(timeout=max(1, int(ctx.timeout_ms)))
        self._bump()
        ctx.check()

    def type_text(self, ref: str, text: str, *, ctx: CallContext) -> None:
        ctx.check()
        self._locator(ref).type(text, timeout=max(1, int(ctx.timeout_ms)))
        self._bump()
        ctx.check()

    def fill(self, ref: str, value: str, *, ctx: CallContext) -> None:
        ctx.check()
        self._locator(ref).fill(value, timeout=max(1, int(ctx.timeout_ms)))
        self._bump()
        ctx.check()

    def scroll(self, delta: int, *, ctx: CallContext) -> None:
        ctx.check()
        self.page.mouse.wheel(0, delta)
        ctx.check()

    def screenshot(self, *, ctx: CallContext) -> bytes:
        ctx.check()
        data = self.page.screenshot(type="png", timeout=max(1, int(ctx.timeout_ms)))
        ctx.check()
        return bytes(data)

    def download(self, ref: str, *, ctx: CallContext) -> bytes:
        ctx.check()
        with self.page.expect_download(timeout=max(1, int(ctx.timeout_ms))) as info:
            self._locator(ref).click(timeout=max(1, int(ctx.timeout_ms)))
        path = info.value.path()
        ctx.check()
        return Path(path).read_bytes()

    def upload(self, ref: str, path: Path, *, ctx: CallContext) -> None:
        ctx.check()
        self._locator(ref).set_input_files(str(path), timeout=max(1, int(ctx.timeout_ms)))
        self._bump()
        ctx.check()

    def capabilities(self) -> dict:
        return {"download": True, "upload": True, "screenshot": True, "frames": True}

    def close(self, *, ctx: CallContext) -> None:
        ctx.check()
        self.page.context.close()
        self._bump()


# ---------------------------------------------------------------------------
# Session + runtime
# ---------------------------------------------------------------------------

_INTERNAL_URLS = frozenset({"about:blank", ""})
_HANDOFF_REASONS = frozenset({"login", "2fa", "payment", "sensitive", "other"})
_SENSITIVE_FIELD = re.compile(
    r"(?i)(?:password|passphrase|pin|otp|one[- ]time|2fa|verification\s*code|"
    r"card\s*number|cvv|secret|token|recovery\s*code)")


_MAX_ARTIFACT_BYTES = 32 * 1024 * 1024


def _artifact_target(artifact_dir: Path, requested: str | Path | None,
                     default_name: str, data_len: int) -> Path:
    """Resolve an artifact path inside ``artifact_dir``; fail closed otherwise.

    Callers may suggest a filename, never an arbitrary destination. Symlinks
    are resolved before the containment check, so they cannot escape.
    """
    if data_len > _MAX_ARTIFACT_BYTES:
        raise PolicyError("artifact exceeds the byte cap", code="artifact_too_large")
    root = artifact_dir.resolve()
    candidate = Path(requested) if requested is not None else artifact_dir / default_name
    target = candidate.resolve()
    if target == root or not target.is_relative_to(root):
        raise PolicyError("artifact path must stay inside the artifact directory",
                          code="artifact_root_violation")
    return target


@dataclass
class BrowserSession:
    """One named browser session, owned by exactly one caller."""

    name: str
    owner: str
    policy: DomainPolicy
    driver: BrowserDriver
    log: EventLog
    artifact_dir: Path
    timeout_ms: int = 5000
    max_nodes: int = 200
    max_frames: int = 8
    allowed_upload_roots: tuple[Path, ...] = ()
    dns_resolver: _DnsResolver | None = None
    state: str = "open"
    epoch: int = 0
    revision: int = 0
    url: str = "about:blank"
    handoff_reason: str | None = None
    # Host-supplied out-of-band confirmation check. Without it, resume fails
    # closed: the agent/session owner cannot assert that the user acted.
    confirmation_provider: Callable[[str], bool] | None = None
    _handoff_token: str | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)
    _last_dom: int = 0
    _refs: dict[str, NodeRef] = field(default_factory=dict)
    _snapshot: Snapshot | None = None
    _artifact_seq: int = 0

    # -- internal guards ---------------------------------------------------

    def _ctx(self, timeout_ms: int | None = None) -> CallContext:
        return CallContext(self.timeout_ms if timeout_ms is None else timeout_ms, self._cancel)

    def _state_check(self) -> None:
        if self._cancel.is_set() or self.state == "cancelled":
            raise BrowserCancelled("session was cancelled", details={"session": self.name})
        if self.state == "handoff":
            raise HandoffRequired(
                f"session is paused for {self.handoff_reason}; user action required",
                details={"session": self.name, "reason": self.handoff_reason})
        if self.state == "blocked":
            raise PolicyError("session is quarantined after an off-policy navigation",
                              code="session_blocked", details={"session": self.name})
        if self.state != "open":
            raise SessionClosed(f"session {self.name!r} is {self.state}",
                                details={"session": self.name})

    def _call(self, fn: Callable[[CallContext], Any], *, timeout_ms: int | None = None) -> Any:
        ctx = self._ctx(timeout_ms)
        ctx.check()
        try:
            result = fn(ctx)
        except (BrowserTimeout, BrowserCancelled):
            self.log.record("cancelled_or_timeout", session=self.name)
            raise
        ctx.check()  # honest post-call deadline check
        return result

    def _guard_content(self, ctx: CallContext) -> None:
        """Re-check the allowlist *before any page content is read*."""
        self._state_check()
        current = self.driver.current_url(ctx=ctx)
        if current in _INTERNAL_URLS:
            return
        if not isinstance(current, str) or not self.policy.host_allowed(
                (urlsplit(current).hostname or "").lower(), resolve=True,
                dns_resolver=self.dns_resolver):
            self.state = "blocked"
            self.log.record("blocked_off_policy_url", session=self.name, source=current)
            raise PolicyError("current page is outside the domain allowlist",
                              code="session_blocked", details={"session": self.name})
        self.url = self.policy.recheck_arrival(current, dns_resolver=self.dns_resolver)

    def _sync_dom(self, ctx: CallContext) -> None:
        """DOM changes invalidate every previously issued ref."""
        try:
            version = int(self.driver.dom_version(ctx=ctx))
        except (AttributeError, TypeError, ValueError):
            return
        if version != self._last_dom:
            self._last_dom = version
            self.epoch += 1
            self._refs = {}
            self.log.record("refs_invalidated", session=self.name, epoch=self.epoch)

    def _require_capability(self, name: str) -> None:
        caps = self.driver.capabilities()
        if not isinstance(caps, dict) or not caps.get(name, False):
            raise UnsupportedCapability(f"driver does not support {name}",
                                        details={"capability": name})

    # -- public operations -------------------------------------------------

    @property
    def owner_token(self) -> str:
        return self.owner

    def navigate(self, url: str, *, timeout_ms: int | None = None) -> dict:
        self._state_check()
        # Check BEFORE the driver is asked to navigate.
        target = self.policy.validate_url(url, dns_resolver=self.dns_resolver)
        self.log.record("navigate_requested", session=self.name, source=target)
        new_url = self._call(lambda ctx: self.driver.navigate(target, ctx=ctx),
                             timeout_ms=timeout_ms)
        # Check again ON ARRIVAL, before any page content can be read.
        if new_url not in _INTERNAL_URLS:
            try:
                self.policy.recheck_arrival(new_url, dns_resolver=self.dns_resolver)
            except PolicyError:
                self.state = "blocked"  # quarantine; no page content was read
                self.log.record("blocked_off_policy_url", session=self.name, source=new_url)
                raise
        self.epoch += 1
        self._refs = {}
        self._snapshot = None
        self._last_dom = self._call(lambda ctx: self.driver.dom_version(ctx=ctx),
                                    timeout_ms=timeout_ms)
        self.url = new_url
        self.log.record("navigated", session=self.name, source=new_url, epoch=self.epoch)
        return {"ok": True, "url": new_url, "epoch": self.epoch}

    def snapshot(self, *, timeout_ms: int | None = None,
                 max_nodes: int | None = None) -> dict:
        def work(ctx: CallContext) -> dict:
            self._sync_dom(ctx)
            self._guard_content(ctx)
            current = self.driver.current_url(ctx=ctx)
            raw = self.driver.snapshot(ctx=ctx,
                                       max_nodes=self.max_nodes if max_nodes is None else max_nodes,
                                       epoch=self.epoch)
            self.revision += 1
            snap = build_snapshot(raw, url=current, epoch=self.epoch,
                                  revision=self.revision, policy=self.policy,
                                  max_frames=self.max_frames,
                                  max_nodes=self.max_nodes if max_nodes is None else max_nodes)
            self._snapshot = snap
            self._refs = snap.ref_map()
            self.log.record("snapshot", session=self.name, revision=self.revision,
                            nodes=len(snap.refs), flags=snap.flags)
            return snap.to_dict()

        return self._call(work, timeout_ms=timeout_ms)

    def _resolve(self, ref: Any, ctx: CallContext) -> NodeRef:
        self._sync_dom(ctx)
        self._guard_content(ctx)
        ref_id = ref.id if isinstance(ref, NodeRef) else ref
        if not isinstance(ref_id, str) or ref_id not in self._refs:
            raise StaleRef(f"unknown ref {ref_id!r}; take a new snapshot",
                           details={"ref": str(ref_id), "epoch": self.epoch})
        node = self._refs[ref_id]
        if node.epoch != self.epoch:
            raise StaleRef(f"ref {ref_id!r} is stale after epoch {self.epoch}",
                           details={"ref": ref_id, "epoch": self.epoch})
        return node

    def _after_action(self, ref: str, action: str, ctx: CallContext,
                      *, value: Any = None) -> None:
        # Never log the value itself; only its length and the target ref.
        self.log.record(action, session=self.name, ref=ref,
                        value_length=len(value) if isinstance(value, str) else None)
        self._sync_dom(ctx)
        self._guard_content(ctx)  # a click may have navigated off-policy

    def click(self, ref: Any, *, timeout_ms: int | None = None) -> dict:
        def work(ctx: CallContext) -> dict:
            node = self._resolve(ref, ctx)
            self.driver.click(node.id, ctx=ctx)
            self._after_action(node.id, "click", ctx)
            return {"ok": True, "ref": node.id}

        return self._call(work, timeout_ms=timeout_ms)

    def type_text(self, ref: Any, text: str, *, timeout_ms: int | None = None) -> dict:
        return self._input(ref, text, mode="type_text", timeout_ms=timeout_ms)

    def fill(self, ref: Any, value: str, *, timeout_ms: int | None = None) -> dict:
        return self._input(ref, value, mode="fill", timeout_ms=timeout_ms)

    def _input(self, ref: Any, value: str, *, mode: str,
               timeout_ms: int | None = None) -> dict:
        if not isinstance(value, str):
            raise BrowserRuntimeError("input value must be a string", code="invalid_input")

        def work(ctx: CallContext) -> dict:
            node = self._resolve(ref, ctx)
            sensitive = bool(_SENSITIVE_FIELD.search(f"{node.name} {node.role}"))
            if sensitive or _looks_like_credential(value):
                reason = "2fa" if _SENSITIVE_FIELD.search(node.name) and re.search(
                    r"(?i)otp|one[- ]time|2fa|verification", node.name) else (
                    "payment" if re.search(r"(?i)card|cvv", node.name) else "login")
                self.log.record("credential_blocked", session=self.name, ref=node.id,
                                reason=reason)
                raise CredentialBlocked(
                    "credentials must be entered by a human via handoff, not by the agent",
                    details={"ref": node.id, "handoff_reason": reason})
            if mode == "fill":
                self.driver.fill(node.id, value, ctx=ctx)
            else:
                self.driver.type_text(node.id, value, ctx=ctx)
            self._after_action(node.id, mode, ctx, value=value)
            return {"ok": True, "ref": node.id, "mode": mode}

        return self._call(work, timeout_ms=timeout_ms)

    def scroll(self, delta: int, *, timeout_ms: int | None = None) -> dict:
        def work(ctx: CallContext) -> dict:
            self._guard_content(ctx)
            self.driver.scroll(int(delta), ctx=ctx)
            self.log.record("scroll", session=self.name, delta=int(delta))
            ctx.check()
            return {"ok": True, "delta": int(delta)}

        return self._call(work, timeout_ms=timeout_ms)

    def screenshot(self, *, path: str | Path | None = None,
                   timeout_ms: int | None = None) -> dict:
        self._require_capability("screenshot")

        def work(ctx: CallContext) -> dict:
            self._guard_content(ctx)
            data = self.driver.screenshot(ctx=ctx)
            if not isinstance(data, (bytes, bytearray)) or not data:
                raise DriverError("driver returned no screenshot bytes")
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
            self._artifact_seq += 1
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", self.name)[:48]
            target = _artifact_target(
                self.artifact_dir, path,
                f"{safe}-{int(time.time() * 1000)}-{self._artifact_seq}.png",
                len(data))
            target.write_bytes(bytes(data))
            self.log.record("screenshot", session=self.name, artifact=str(target),
                            bytes_written=len(data))
            return {"ok": True, "artifact": str(target), "bytes": len(data),
                    "trust": "untrusted",
                    "note": "screenshots may contain secrets; review before sharing"}

        return self._call(work, timeout_ms=timeout_ms)

    def download(self, ref: Any, *, path: str | Path | None = None,
                 timeout_ms: int | None = None) -> dict:
        self._require_capability("download")

        def work(ctx: CallContext) -> dict:
            node = self._resolve(ref, ctx)
            data = self.driver.download(node.id, ctx=ctx)
            if not isinstance(data, (bytes, bytearray)):
                raise DriverError("driver returned non-bytes download")
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
            self._artifact_seq += 1
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", self.name)[:48]
            target = _artifact_target(
                self.artifact_dir, path,
                f"{safe}-download-{self._artifact_seq}.bin",
                len(data))
            target.write_bytes(bytes(data))
            self.log.record("download", session=self.name, ref=node.id,
                            bytes_written=len(data))
            return {"ok": True, "artifact": str(target), "bytes": len(data)}

        return self._call(work, timeout_ms=timeout_ms)

    def upload(self, ref: Any, path: str | Path, *, timeout_ms: int | None = None) -> dict:
        self._require_capability("upload")
        target = Path(path)
        if not target.is_file():
            raise PolicyError("upload path is not a file", code="invalid_upload")
        resolved = target.resolve()
        roots = tuple(root.resolve() for root in self.allowed_upload_roots)
        if not roots or not any(resolved.is_relative_to(root) for root in roots):
            raise PolicyError("upload path is outside the configured roots",
                              code="upload_root_violation")

        def work(ctx: CallContext) -> dict:
            node = self._resolve(ref, ctx)
            self.driver.upload(node.id, resolved, ctx=ctx)
            self._after_action(node.id, "upload", ctx)
            return {"ok": True, "ref": node.id}

        return self._call(work, timeout_ms=timeout_ms)

    def handoff(self, reason: str) -> dict:
        """Pause the session and return control to the user.

        A page cannot complete a handoff. The returned token must be surfaced
        to the user by the host; only :meth:`resume` with a host-validated
        confirmation token can close the gate.
        """
        self._state_check()
        if not isinstance(reason, str) or reason not in _HANDOFF_REASONS:
            raise BrowserRuntimeError("invalid handoff reason", code="invalid_input")
        self.state = "handoff"
        self.handoff_reason = reason
        self._handoff_token = secrets.token_urlsafe(24)
        self.log.record("handoff", session=self.name, reason=reason,
                        token_issued=True)
        return {
            "ok": True,
            "status": "handoff_required",
            "session": self.name,
            "reason": reason,
            "confirmation_token": self._handoff_token,
            "message": ("Paused. The user must complete this step in the browser; "
                        "the host must validate the confirmation token before resume."),
        }

    def resume(self, *, confirmation_token: str) -> dict:
        """Resume only after the host confirms a real user action out of band.

        A boolean supplied by the same caller that drives automation is not
        evidence of user consent, so it is deliberately not accepted.
        """
        if self.state not in ("handoff", "cancelled"):
            raise BrowserRuntimeError("nothing to resume", code="invalid_state")
        if (not isinstance(confirmation_token, str) or not confirmation_token
                or confirmation_token != self._handoff_token):
            raise HandoffRequired(
                "resume requires the token issued by handoff",
                details={"session": self.name, "reason": self.handoff_reason})
        if self.confirmation_provider is None:
            raise HandoffRequired(
                "no host confirmation provider is configured; user consent cannot be verified",
                details={"session": self.name, "reason": self.handoff_reason})
        try:
            confirmed = bool(self.confirmation_provider(confirmation_token))
        except Exception as exc:  # noqa: BLE001 - host failure must fail closed
            raise HandoffRequired("confirmation provider failed",
                                  details={"session": self.name}) from exc
        if not confirmed:
            raise HandoffRequired("host did not confirm the user action",
                                  details={"session": self.name})
        previous = self.state
        self.state = "open"
        self.handoff_reason = None
        self._handoff_token = None
        if self._cancel.is_set():
            self._cancel = threading.Event()
        self.log.record("resumed", session=self.name, previous_state=previous,
                        confirmation="host-validated")
        return {"ok": True, "status": "open", "session": self.name}

    def cancel(self) -> dict:
        self._cancel.set()
        if self.state == "open":
            self.state = "cancelled"
        self.log.record("cancel", session=self.name)
        return {"ok": True, "status": "cancelled", "session": self.name}

    def events(self) -> tuple[dict, ...]:
        return self.log.all()

    def close(self, *, timeout_ms: int | None = None) -> dict:
        def work(ctx: CallContext) -> dict:
            self.driver.close(ctx=ctx)
            return {"ok": True, "session": self.name}

        result = self._call(work, timeout_ms=timeout_ms)
        self.state = "closed"
        self.log.record("closed", session=self.name)
        return result


class BrowserRuntime:
    """Registry of named, single-owner browser sessions."""

    def __init__(self, *, max_sessions: int = 8) -> None:
        self.max_sessions = max(1, int(max_sessions))
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = threading.RLock()

    def capabilities(self, *, importer: Callable[[str], Any] | None = None) -> dict:
        return {
            "core": {"available": True, "mode": "local-optional",
                     "driver_required": True,
                     "note": "core works with a supplied driver; no driver means no results"},
            "playwright": playwright_capability(importer=importer),
        }

    def open_session(
        self,
        name: str,
        owner: str,
        driver: BrowserDriver | None = None,
        policy: DomainPolicy | Sequence[str] | None = None,
        *,
        allowlist: Sequence[str] | None = None,
        allowed_hosts: Sequence[str] | None = None,
        artifact_dir: str | Path | None = None,
        timeout_ms: int = 5000,
        max_nodes: int = 200,
        max_frames: int = 8,
        allowed_upload_roots: Sequence[str | Path] = (),
        dns_resolver: _DnsResolver | None = None,
        confirmation_provider: Callable[[str], bool] | None = None,
    ) -> BrowserSession:
        """Create (or return the owner's existing) named session.

        No driver and no fake success: a missing driver is an explicit error.
        """
        name, owner = _token(name, "session name"), _token(owner, "owner")
        if driver is None:
            raise MissingDriver(
                "a browser driver is required; none is supplied (no fake results)")
        if isinstance(policy, DomainPolicy):
            resolved_policy = policy
        else:
            raw = policy if policy is not None else (
                allowlist if allowlist is not None else allowed_hosts)
            if raw is None:
                raise PolicyError("a domain allowlist is required")
            resolved_policy = DomainPolicy(tuple(raw))
        if not isinstance(timeout_ms, int) or not 1 <= timeout_ms <= 600000:
            raise BrowserRuntimeError("invalid timeout_ms", code="invalid_input")
        with self._lock:
            existing = self._sessions.get(name)
            if existing is not None:
                if existing.owner != owner:
                    raise OwnerConflict(
                        f"session {name!r} is owned by another caller",
                        details={"session": name, "owner": owner})
                return existing
            if len(self._sessions) >= self.max_sessions:
                raise BrowserRuntimeError("session limit reached", code="session_limit")
            session = BrowserSession(
                name=name, owner=owner, policy=resolved_policy, driver=driver,
                log=EventLog(),
                artifact_dir=Path(artifact_dir) if artifact_dir is not None else (
                    Path.home() / ".keel" / "browser-artifacts"),
                timeout_ms=timeout_ms, max_nodes=max(1, int(max_nodes)),
                max_frames=max(1, int(max_frames)),
                allowed_upload_roots=tuple(Path(root) for root in allowed_upload_roots),
                dns_resolver=dns_resolver,
                confirmation_provider=confirmation_provider)
            self._sessions[name] = session
            session.log.record("session_opened", session=name, owner=owner)
            return session

    def get_session(self, name: str, owner: str) -> BrowserSession:
        name, owner = _token(name, "session name"), _token(owner, "owner")
        session = self._sessions.get(name)
        if session is None:
            raise SessionClosed(f"no session named {name!r}", details={"session": name})
        if session.owner != owner:
            raise OwnerConflict(f"session {name!r} is owned by another caller",
                                details={"session": name, "owner": owner})
        return session

    def close_session(self, name: str, owner: str, *, timeout_ms: int | None = None) -> dict:
        session = self.get_session(name, owner)
        result = session.close(timeout_ms=timeout_ms)
        with self._lock:
            self._sessions.pop(name, None)
        return result

    def list_sessions(self, owner: str | None = None) -> tuple[str, ...]:
        with self._lock:
            return tuple(name for name, session in sorted(self._sessions.items())
                         if owner is None or session.owner == owner)
