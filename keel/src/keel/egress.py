"""Per-project network egress allowlist (B3.4).

Restricts which hosts the built-in web tools may contact. Configured through
``KEEL_EGRESS_ALLOWLIST`` (comma-separated hostnames, ``*.example.com``
suffixes, or ``*`` for all). When unset, egress is unrestricted so existing
local-first usage is unchanged. No external service is involved.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse


def load_allowlist() -> list[str]:
    raw = os.environ.get("KEEL_EGRESS_ALLOWLIST", "")
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def host_allowed(url: str, allowlist: list[str] | None = None) -> bool:
    entries = load_allowlist() if allowlist is None else allowlist
    if not entries:
        return True
    host = (urlparse(url).hostname or "").lower()
    for entry in entries:
        if entry == "*":
            return True
        if entry.startswith("*."):
            suffix = entry[1:]  # keep the leading dot
            if host == entry[2:] or host.endswith(suffix):
                return True
        elif host == entry or host.endswith("." + entry):
            return True
    return False


def check_url(url: str, allowlist: list[str] | None = None) -> None:
    if not host_allowed(url, allowlist):
        host = urlparse(url).hostname or ""
        raise ValueError(f"egress allowlist: host {host!r} is not permitted")
