"""keel.fleet.session_keys — session-only provider keys, entered via the UI.

The user pastes a key into the ENGINE panel; we verify it against an
AUTHENTICATED probe (OpenRouter's /models catalog is public and proves
nothing — it answers 200 for any bearer), and, only if accepted, hold it in
this process's environment for the lifetime of the bridge. Nothing is
written to disk and nothing is ever echoed back to the client. Restarting
the bridge forgets it.

Banned here, on purpose:
- logging the key (errors carry status codes and categories, never input)
- returning the key in any response
- persisting the key (file, fleet.db, settings.json)
- touching a key that came from the user's real environment at launch
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from ..providers import registry as provider_registry


class ProviderKeyError(Exception):
    """Validation failed; carries a safe-to-show category + detail."""

    def __init__(self, category: str, detail: str):
        super().__init__(detail)
        self.category = category
        self.detail = detail


# providers whose session key this process set (never the user's own env)
_SESSION_SET: set[str] = set()


def _models_request(cap) -> tuple[str, dict[str, str]]:
    base = cap.base_url.rstrip("/") if cap.base_url else ""
    if not base:
        raise ProviderKeyError("not_configured",
                               f"{cap.name}: no base_url configured")
    if cap.name == "google":
        return base + "/models", {"x-goog-api-key": "__KEY__"}
    if cap.name == "anthropic":
        return base + "/models", {"x-api-key": "__KEY__",
                                  "anthropic-version": "2023-06-01"}
    return base + "/models", {"Authorization": "Bearer __KEY__"}


def _verify_request(cap) -> tuple[str, dict[str, str]]:
    """Endpoint that actually requires a valid key.

    OpenRouter's /models catalog is public; /auth/key is not. Everywhere
    else the models endpoint is gated by its own credentials, so reuse it.
    """
    base = cap.base_url.rstrip("/") if cap.base_url else ""
    if not base:
        raise ProviderKeyError("not_configured",
                               f"{cap.name}: no base_url configured")
    if cap.name == "openrouter":
        return base + "/auth/key", {"Authorization": "Bearer __KEY__"}
    return _models_request(cap)


def _http_json(url: str, headers: dict[str, str], timeout: float) -> Any:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ProviderKeyError("invalid_key",
                                   f"provider rejected the key "
                                   f"(HTTP {exc.code})") from None
        raise ProviderKeyError("http_error",
                               f"provider returned HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ProviderKeyError("network_error",
                               f"could not reach the provider "
                               f"({getattr(exc, 'reason', 'no route')})") from None
    except Exception as exc:
        raise ProviderKeyError("network_error",
                               f"validation failed ({type(exc).__name__})") from None
    try:
        return json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise ProviderKeyError("bad_response",
                               "provider returned malformed JSON") from None


def parse_models(cap, payload: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(payload, dict):
        return out
    if cap.name == "google":
        for m in payload.get("models") or []:
            name = m.get("name") if isinstance(m, dict) else None
            if isinstance(name, str) and name:
                out.append(name.removeprefix("models/"))
    else:
        for m in payload.get("data") or []:
            mid = m.get("id") if isinstance(m, dict) else None
            if isinstance(mid, str) and mid:
                out.append(mid)
    # stable, de-duplicated, capped
    seen: set[str] = set()
    unique = [m for m in out if not (m in seen or seen.add(m))]
    return unique[:200]


def parse_models_meta(cap, payload: Any) -> list[dict]:
    """Richer per-model entries for the UI (capabilities, effort levels)."""
    out: list[dict] = []
    if not isinstance(payload, dict):
        return out
    if cap.name == "google":
        for m in payload.get("models") or []:
            if not isinstance(m, dict):
                continue
            name = m.get("name")
            if not isinstance(name, str) or not name:
                continue
            out.append({"id": name.removeprefix("models/"),
                        "supported_parameters": [],
                        "reasoning": None})
    else:
        for m in payload.get("data") or []:
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            if not isinstance(mid, str) or not mid:
                continue
            sp = m.get("supported_parameters")
            reasoning = m.get("reasoning")
            entry: dict[str, Any] = {
                "id": mid,
                "supported_parameters": [p for p in (sp or []) if isinstance(p, str)][:40],
            }
            cl = m.get("context_length")
            if isinstance(cl, (int, float)) and cl > 0:
                entry["context_length"] = int(cl)
            if isinstance(reasoning, dict) and reasoning.get("supported_efforts"):
                entry["reasoning"] = {
                    "supported_efforts": [e for e in reasoning["supported_efforts"]
                                          if isinstance(e, str)][:10],
                    "default_effort": reasoning.get("default_effort"),
                    "mandatory": bool(reasoning.get("mandatory")),
                }
            else:
                entry["reasoning"] = None
            out.append(entry)
    seen: set[str] = set()
    unique = [e for e in out if not (e["id"] in seen or seen.add(e["id"]))]
    return unique[:300]


def _load_catalog(name: str, key: str) -> tuple[Any, Any]:
    cap = provider_registry.capability(name)
    if cap is None:
        raise ProviderKeyError("unknown_provider", f"unknown provider {name!r}")
    if not key:
        raise ProviderKeyError("empty_key", "key must not be empty")
    v_url, v_headers = _verify_request(cap)
    v_headers = _hydrate(v_headers, key)
    verify_payload = _http_json(v_url, v_headers, timeout=10)  # raises on bad key
    m_url, m_headers = _models_request(cap)
    m_headers = _hydrate(m_headers, key)
    if m_url == v_url and m_headers == v_headers:
        # same endpoint doubles as the catalog (google/anthropic/nvidia/compat)
        payload = verify_payload
    else:
        # openrouter: catalog is public; only the probe is authenticated
        payload = _http_json(m_url, m_headers, timeout=10)
    return cap, payload


def fetch_models_with_meta(name: str, key: str) -> tuple[list[str], list[dict]]:
    cap, payload = _load_catalog(name, key)
    return parse_models(cap, payload), parse_models_meta(cap, payload)


def _hydrate(headers: dict[str, str], key: str) -> dict[str, str]:
    return {k: v.replace("__KEY__", key) for k, v in headers.items()}


def fetch_models(name: str, key: str) -> list[str]:
    """Verify the key against an authenticated probe, then read the catalog."""
    cap, payload = _load_catalog(name, key)
    return parse_models(cap, payload)


def set_session_key(name: str, key: str) -> None:
    cap = provider_registry.capability(name)
    if cap is None:
        raise ProviderKeyError("unknown_provider", f"unknown provider {name!r}")
    os.environ[cap.env_var] = key
    _SESSION_SET.add(name)


def clear_session_key(name: str) -> bool:
    """Clear only a key this process set; never one from the user's shell."""
    if name not in _SESSION_SET:
        return False
    cap = provider_registry.capability(name)
    if cap is not None:
        os.environ.pop(cap.env_var, None)
    _SESSION_SET.discard(name)
    return True


def is_session_key(name: str) -> bool:
    return name in _SESSION_SET


def session_providers() -> list[str]:
    return sorted(_SESSION_SET)
