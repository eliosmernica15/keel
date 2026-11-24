"""Backend behavior for the remaining W7.*, X1.*, Y5.* and D1.* plan rows.

This module is intentionally self-contained and **stdlib-only**. Every helper
here implements real, deterministic backend logic (security checks, dialect
adapters, webhook/channel plumbing, plugin/profile transactions) and performs
no network I/O, spawns no processes and requires no hosted account. Optional
integrations are described with explicit gates and are never silently enabled.

Feature IDs are taken verbatim from ``PLAN-INDEX.json``. The 26 P0 rows with
these prefixes were already implemented in other modules; this module covers
the 31 ``not_started`` rows only. See
``master-plan-v6-w7-x1-y5-d1-backend-evidence.md`` for the full mapping.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import hmac
import html
import json
import math
import os
import re
import secrets
import shlex
import tempfile
import threading
import time
import urllib.parse
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class BackendError(RuntimeError):
    """Base error for this module."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")
# Plugin ids may be dot-namespaced (e.g. ``acme.plugin``); bundles/profiles may not.
_PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[-_.][a-z0-9]+)*$")
_SECRET_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{8,})\b"
)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Public-share output must not publish assignment-style credentials.  As in
# the other backends, the value runs to the next assignment/newline rather
# than to the next space, so "token=super secret value" is removed in full.
_SECRET_KEYWORDS = (
    r"api[_-]?key|access[_-]?token|token|password|secret|authorization|pin"
)
_NEXT_ASSIGNMENT = (
    r"['\"]?\b\w*(?:" + _SECRET_KEYWORDS + r")\w*['\"]?\s*[:=]"
)
_ASSIGNED_SECRET_RE = re.compile(
    r"(?i)(?P<key>\b\w*(?:" + _SECRET_KEYWORDS + r")\w*)\s*['\"]?\s*[:=]\s*"
    r"(?:"
    r"(?P<q>['\"])(?:(?!(?P=q))[^\r\n])*(?P=q)"
    r"|(?:['\"]?(?:Bearer|Basic)\s+)?"
    r"(?:(?!(?:" + _NEXT_ASSIGNMENT + r"))[^\r\n])*"
    r")"
)
_BARE_BEARER_RE = re.compile(r"(?i)\b(?:Bearer|Basic)\s+[^\s,;'\"\r\n]{4,}")


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _scrub_secrets(text: str) -> str:
    """Remove credential-shaped substrings and e-mail addresses from text."""
    out = _SECRET_RE.sub("[REDACTED]", str(text))
    out = _ASSIGNED_SECRET_RE.sub(lambda m: f"{m.group('key')}=[REDACTED]", out)
    out = _BARE_BEARER_RE.sub("[REDACTED]", out)
    out = _EMAIL_RE.sub("[REDACTED]", out)
    return out


# Serialises the replace itself; every caller shares this lock.
_WRITE_LOCK = threading.RLock()

# Read-modify-write cycles need a lock keyed by the resolved *state file*, not
# by manager instance: two managers over one credentials dir must not both
# load the same document, append their own entry and overwrite each other.
_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _lock_for_path(path: str | Path) -> threading.RLock:
    key = str(Path(path).resolve())
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


def _contained_path(root: str | Path, name: str, *, label: str = "path") -> Path:
    """Build ``root / name`` while rejecting traversal/NUL in caller input.

    Caller-supplied credential and log directories must not be able to escape
    the directory they name via ``..`` segments or an embedded NUL byte.
    """
    if "\x00" in str(root) or "\x00" in str(name):
        raise BackendError(f"invalid {label}: NUL byte")
    base = Path(root)
    if any(part == ".." for part in base.parts) or ".." in Path(name).parts:
        raise BackendError(f"invalid {label}: traversal not allowed")
    candidate = base / name
    resolved_base = base.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_base and resolved_base not in resolved.parents:
        raise BackendError(f"{label} escapes its base directory")
    return candidate


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        # A unique temp file in the destination directory prevents concurrent
        # writers from sharing (and interleaving into) a fixed ``.tmp`` name.
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ===========================================================================
# D1.* — plugins, profiles, bundles, entrypoints and transactions
# ===========================================================================

# --- D1.2: reversible registration effects ---------------------------------


@dataclass
class Disposer:
    """Handle returned by :meth:`ReversibleEffectScope.register`."""

    scope: "ReversibleEffectScope"
    key: str

    def __call__(self) -> bool:
        return self.scope.dispose(self.key)

    dispose = __call__

    @property
    def active(self) -> bool:
        return self.scope.is_active(self.key)


@dataclass
class _Effect:
    key: str
    undo: Callable[[], None]
    disposed: bool = False


class ReversibleEffectScope:
    """D1.2: every ``register()`` returns a disposer tied to this scope.

    Unloading the plugin calls :meth:`unload`, which unwinds live effects in
    reverse registration order (LIFO). :meth:`leaked` is the leak detector.
    """

    def __init__(self, name: str):
        self.name = name
        self._effects: "OrderedDict[str, _Effect]" = OrderedDict()
        self._lock = threading.RLock()

    def register(self, key: str, undo: Callable[[], None], *, replace: bool = False) -> Disposer:
        if not callable(undo):
            raise BackendError("undo must be callable")
        with self._lock:
            if key in self._effects and not self._effects[key].disposed:
                if not replace:
                    raise BackendError(f"effect already registered: {key}")
                self.dispose(key)
            self._effects[key] = _Effect(key=key, undo=undo)
        return Disposer(self, key)

    def is_active(self, key: str) -> bool:
        with self._lock:
            effect = self._effects.get(key)
            return bool(effect and not effect.disposed)

    def dispose(self, key: str) -> bool:
        with self._lock:
            effect = self._effects.get(key)
            if effect is None or effect.disposed:
                return False
            effect.undo()
            effect.disposed = True
            return True

    def unload(self) -> list[str]:
        """Unwind all live effects; return the keys that were disposed."""
        unwound: list[str] = []
        with self._lock:
            for key in reversed(list(self._effects)):
                if self.dispose(key):
                    unwound.append(key)
        return unwound

    def leaked(self) -> list[str]:
        """Leak detector: keys still live when the scope is inspected."""
        with self._lock:
            return [key for key, effect in self._effects.items() if not effect.disposed]

    def __enter__(self) -> "ReversibleEffectScope":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.unload()


def detect_effect_leaks(*scopes: ReversibleEffectScope) -> dict[str, list[str]]:
    """Aggregate leak-detector results across scopes (D1.2 acceptance test)."""
    return {scope.name: scope.leaked() for scope in scopes if scope.leaked()}


# --- D1.3: profiles and bundles --------------------------------------------


@dataclass(frozen=True)
class Profile:
    name: str
    bundles: tuple[str, ...]
    plugins: tuple[str, ...] = ()
    patch: str = ""


PROFILE_TEMPLATES: dict[str, dict[str, Any]] = {
    "web": {"bundles": ("core", "web-ui", "hmr"), "plugins": (), "patch": "profiles/web.patch.json"},
    "headless": {"bundles": ("core",), "plugins": (), "patch": "profiles/headless.patch.json"},
    "sdk": {"bundles": ("core", "sdk"), "plugins": (), "patch": "profiles/sdk.patch.json"},
    "sdk-minimal": {"bundles": ("core",), "plugins": (), "patch": "profiles/sdk-minimal.patch.json"},
    "acp": {"bundles": ("core", "acp"), "plugins": (), "patch": "profiles/acp.patch.json"},
}

_BUNDLES: dict[str, dict[str, Any]] = {
    "core": {"config_rows": 1, "code_modules": ("session", "tools", "model_dialects")},
    "web-ui": {"config_rows": 1, "code_modules": ("webapp",)},
    "hmr": {"config_rows": 1, "code_modules": ("file_watcher",)},
    "sdk": {"config_rows": 1, "code_modules": ("runner",)},
    "acp": {"config_rows": 1, "code_modules": ("cli",)},
}


def register_bundle(name: str, *, config_rows: int = 0, code_modules: tuple[str, ...] = ()) -> None:
    """D1.3: register a distributable bundle (config rows + code)."""
    if not _ID_RE.match(name):
        raise BackendError(f"invalid bundle name: {name}")
    _BUNDLES[name] = {"config_rows": int(config_rows), "code_modules": tuple(code_modules)}


def resolve_profile(name: str, *, extra_bundles: tuple[str, ...] = (),
                    extra_plugins: tuple[str, ...] = (), patch: str = "") -> Profile:
    """D1.3: resolve a named template into a concrete :class:`Profile`."""
    template = PROFILE_TEMPLATES.get(name)
    if template is None:
        raise BackendError(f"unknown profile: {name}")
    bundles = tuple(dict.fromkeys(template["bundles"] + tuple(extra_bundles)))
    unknown = [b for b in bundles if b not in _BUNDLES]
    if unknown:
        raise BackendError(f"unknown bundles: {unknown}")
    return Profile(name=name, bundles=bundles,
                   plugins=tuple(dict.fromkeys(template["plugins"] + tuple(extra_plugins))),
                   patch=patch or template["patch"])


def validate_profile(profile: Profile) -> list[str]:
    """Return a list of composition errors (empty means valid)."""
    errors: list[str] = []
    if profile.name not in PROFILE_TEMPLATES:
        errors.append(f"unknown profile: {profile.name}")
    for bundle in profile.bundles:
        if bundle not in _BUNDLES:
            errors.append(f"unknown bundle: {bundle}")
    for plugin in profile.plugins:
        if not _PLUGIN_ID_RE.match(plugin):
            errors.append(f"invalid plugin id: {plugin}")
    return errors


def profile_config_rows(profile: Profile) -> list[str]:
    """D1.3: flatten a profile into the ordered config rows it contributes."""
    rows: list[str] = []
    for bundle in profile.bundles:
        rows.extend([f"bundle:{bundle}:row:{i}"
                     for i in range(_BUNDLES[bundle]["config_rows"])])
    if profile.patch:
        rows.append(f"patch:{profile.patch}")
    return rows


# --- D1.6: config-only HMR toggle ------------------------------------------

INTERACTIVE_PROFILES = frozenset({"web"})


def hmr_enabled(profile: str | Profile) -> bool:
    """D1.6: HMR is on only for interactive (web) profiles."""
    name = profile.name if isinstance(profile, Profile) else profile
    return name in INTERACTIVE_PROFILES


def hmr_config(profile: str | Profile) -> dict:
    """D1.6: the config-only toggle row for the HMR plugin."""
    return {"plugins.load.hmr": {"enabled": hmr_enabled(profile),
                                 "mode": "config-only", "profile": profile.name
                                 if isinstance(profile, Profile) else profile}}


# --- D1.9: reserved command names ------------------------------------------

RESERVED_COMMANDS = frozenset({
    "plugin", "run", "serve", "attach", "tools", "costs", "model", "release",
    "init", "status", "gateway", "profile",
})


def is_reserved_command(name: str) -> bool:
    return name in RESERVED_COMMANDS


def validate_profile_name(name: str, *, allow_reserved: bool = False) -> str:
    """D1.9: ``plugin`` stays a command unless explicitly addressed as a profile."""
    if not _ID_RE.match(name):
        raise BackendError(f"invalid profile name: {name}")
    if is_reserved_command(name) and not allow_reserved:
        raise BackendError(f"'{name}' is a reserved command; use --profile {name} explicitly")
    return name


# --- D1.7: application entrypoint gate -------------------------------------


def classify_entrypoint(command: str) -> str:
    """D1.7: classify one executable command as launcher, bypass or unknown."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return "unknown"
    if not tokens:
        return "unknown"
    if "keel" in tokens or tokens[-1].replace("\\", "/").endswith("/keel"):
        if "--profile" in tokens:
            return "profile_launcher"
        return "bypass"
    if tokens[0] in ("python", "python3") and any(
            t.startswith("-m") or t == "keel" for t in tokens[1:]):
        return "bypass"
    return "unknown"


def verify_application_entrypoints(manifest: dict) -> dict:
    """D1.7: fail a manifest whose scripts/demos/bins bypass ``keel --profile``."""
    violations: list[dict] = []
    checked = 0
    for section in ("scripts", "bins", "demos", "entrypoints"):
        entries = manifest.get(section, {}) or {}
        items = entries.items() if isinstance(entries, dict) else enumerate(entries)
        for name, command in items:
            checked += 1
            kind = classify_entrypoint(str(command))
            if kind != "profile_launcher":
                violations.append({"section": section, "name": str(name),
                                   "command": str(command), "classification": kind})
    return {"ok": not violations, "checked": checked, "violations": violations}


# --- D1.8: SDK runtime launch -----------------------------------------------

_SDK_WHEEL_PLATFORMS = {
    "windows": "win_amd64",
    "linux": "manylinux_2_28_x86_64",
    "macos": "macosx_11_0_universal2",
}


def sdk_wheel_name(platform: str, version: str = "0.1.1") -> str:
    """D1.8: the bundled-runtime wheel tag for an OS/arch."""
    tag = _SDK_WHEEL_PLATFORMS.get(platform)
    if tag is None:
        raise BackendError(f"unsupported sdk platform: {platform}")
    return f"keel_runtime-{version}-py3-none-{tag}.whl"


def sdk_launch_args(*, home_dir: str, profile: str = "sdk") -> list[str]:
    """D1.8: client argv that always passes an explicit profile and data dir."""
    if profile not in ("sdk", "sdk-minimal"):
        raise BackendError("sdk client must launch with --profile sdk or sdk-minimal")
    if not home_dir or not str(home_dir).strip():
        raise BackendError("sdk client requires an explicit data/home dir")
    return ["keel", "--profile", profile, "--home", str(home_dir)]


def validate_sdk_args(argv: list[str]) -> bool:
    """D1.8: assert the SDK argv contract (profile + explicit home)."""
    if "--profile" not in argv or "--home" not in argv:
        return False
    try:
        profile = argv[argv.index("--profile") + 1]
        home = argv[argv.index("--home") + 1]
    except IndexError:
        return False
    return profile in ("sdk", "sdk-minimal") and bool(home)


# --- D1.11: plugin install transactions ------------------------------------


@dataclass
class TxStep:
    name: str
    do: Callable[[], Any]
    undo: Callable[[], Any]


@dataclass
class PluginTransaction:
    """D1.11: isolated per-profile install/update transaction with rollback."""

    profile: str
    env_root: str | Path
    steps: list[TxStep] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)

    @property
    def env_path(self) -> Path:
        return Path(self.env_root) / "profiles" / self.profile / "venv"

    def add(self, name: str, do: Callable[[], Any], undo: Callable[[], Any]) -> None:
        self.steps.append(TxStep(name=name, do=do, undo=undo))

    def rollback(self, through: int) -> None:
        for step in reversed(self.steps[:through]):
            try:
                step.undo()
                self.log.append({"step": step.name, "action": "rollback", "ok": True})
            except Exception as exc:  # best effort, keep unwinding
                self.log.append({"step": step.name, "action": "rollback",
                                 "ok": False, "error": str(exc)[:200]})

    def run(self) -> dict:
        self.env_path.mkdir(parents=True, exist_ok=True)
        applied = 0
        for step in self.steps:
            try:
                result = step.do()
                applied += 1
                self.log.append({"step": step.name, "action": "apply",
                                 "ok": True, "result": str(result)[:200]})
            except Exception as exc:
                self.log.append({"step": step.name, "action": "apply",
                                 "ok": False, "error": str(exc)[:200]})
                self.rollback(applied)
                return {"ok": False, "rolled_back": applied,
                        "failed_step": step.name, "log": list(self.log)}
        return {"ok": True, "applied": applied, "env": str(self.env_path),
                "log": list(self.log)}


# ===========================================================================
# W7.* — web/daemon security backend
# ===========================================================================

# --- W7.2: owner-only live view --------------------------------------------

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, private",
    "Pragma": "no-cache",
    "Expires": "0",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def live_view_headers(*, owner_only: bool = True) -> dict[str, str]:
    """W7.2: headers for live-view/viewer endpoints (no-store always)."""
    headers = dict(NO_STORE_HEADERS)
    if owner_only:
        headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return headers


def live_view_url(base: str, view_token: str) -> str:
    """W7.2: build a capability URL for the owner's live view."""
    parsed = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parsed.query)
    query.append(("view", view_token))
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))


def authorize_live_view(request_owner: str, resource_owner: str) -> bool:
    """W7.2: only the resource owner may open the live view."""
    return bool(request_owner) and hmac.compare_digest(
        str(request_owner), str(resource_owner))


# --- W7.7: browser-bound sealed sign-in ------------------------------------

# HMAC-SHA256 is only as strong as its key.  An arbitrarily short key yields a
# valid-looking token that is trivially brute-forceable, so reject it at the
# boundary instead of silently issuing weak signatures.
_SEAL_KEY_MIN_BYTES = 16


def _require_seal_key(key: bytes) -> bytes:
    if not isinstance(key, (bytes, bytearray)):
        raise BackendError("seal key must be bytes")
    value = bytes(key)
    if len(value) < _SEAL_KEY_MIN_BYTES:
        raise BackendError(f"seal key must be at least {_SEAL_KEY_MIN_BYTES} bytes")
    return value


def seal_value(value: dict, key: bytes, *, ttl: int = 600,
               now: int | None = None) -> str:
    """W7.7: seal a value as ``b64(payload).b64(hmac)`` with an expiry."""
    key = _require_seal_key(key)
    issued = int(now if now is not None else time.time())
    payload = dict(value)
    payload["exp"] = issued + int(ttl)
    raw = _b64u_encode(json.dumps(payload, sort_keys=True).encode("utf-8"))
    sig = _b64u_encode(hmac.new(key, raw.encode("ascii"), hashlib.sha256).digest())
    return f"{raw}.{sig}"


def unseal_value(token: str, key: bytes, *, now: int | None = None) -> dict | None:
    """W7.7: verify the HMAC in constant time and enforce expiry."""
    try:
        key = _require_seal_key(key)
    except BackendError:
        return None  # fail closed on an under-strength key
    try:
        raw, sig = token.rsplit(".", 1)
        expected = _b64u_encode(hmac.new(key, raw.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_b64u_decode(raw).decode("utf-8"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(now if now is not None else time.time()) >= int(payload.get("exp", 0)):
        return None
    return payload


def cookie_header(name: str, value: str, *, max_age: int = 600) -> str:
    """W7.7: a SameSite=Strict, HttpOnly, Secure cookie header."""
    return (f"{name}={value}; Path=/; HttpOnly; Secure; "
            f"SameSite=Strict; Max-Age={int(max_age)}")


def browser_fingerprint(headers: dict) -> str:
    """W7.7: derive a stable, non-secret browser fingerprint from headers."""
    material = "|".join(str(headers.get(h, "")) for h in
                        ("User-Agent", "Accept-Language", "Accept-Encoding"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class BrowserBoundSignIn:
    """W7.7: a sign-in that only the initiating browser can complete."""

    def __init__(self, key: bytes):
        self.key = _require_seal_key(key)
        self._states: dict[str, dict] = {}
        self._consumed: set[str] = set()
        self._lock = threading.RLock()

    def start(self, fingerprint: str, *, redirect: str = "") -> dict:
        state = secrets.token_urlsafe(24)
        cookie = seal_value({"state": state, "fp": fingerprint,
                             "kind": "signin"}, self.key)
        with self._lock:
            self._states[state] = {"fp": fingerprint, "redirect": redirect}
        return {"state": state, "cookie": cookie,
                "set_cookie": cookie_header("keel_signin", cookie),
                "authorize_url": f"/signin/callback?state={state}"}

    def complete(self, state: str, cookie: str, fingerprint: str) -> bool:
        payload = unseal_value(cookie, self.key)
        if payload is None or payload.get("kind") != "signin":
            return False
        with self._lock:
            expected = self._states.get(state)
            if expected is None or state in self._consumed:
                return False
            ok = (hmac.compare_digest(str(payload.get("state", "")), state)
                  and hmac.compare_digest(str(payload.get("fp", "")), fingerprint)
                  and hmac.compare_digest(str(expected["fp"]), fingerprint))
            if ok:
                self._consumed.add(state)
            return ok

    def bind_pairing(self, client_id: str, fingerprint: str) -> str:
        """W7.7/Y3.8: return a sealed cookie binding a pairing code to a client."""
        return seal_value({"client_id": client_id, "fp": fingerprint,
                           "kind": "pairing"}, self.key)

    def complete_pairing(self, cookie: str, client_id: str, fingerprint: str,
                         expected_code: str) -> bool:
        payload = unseal_value(cookie, self.key)
        if payload is None or payload.get("kind") != "pairing":
            return False
        return (hmac.compare_digest(str(payload.get("client_id", "")), client_id)
                and hmac.compare_digest(str(payload.get("fp", "")), fingerprint)
                and bool(expected_code))


# --- W7.9: CSRF origin check -----------------------------------------------


def check_csrf_origin(headers: dict, *, expected_origin: str, method: str) -> tuple[bool, str]:
    """W7.9: require a matching Origin on cookie-bearing state-changing calls.

    Safe methods (GET/HEAD/OPTIONS) and bearer-authenticated routes are exempt.
    Returns ``(ok, reason)``.
    """
    verb = method.upper()
    if verb in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return True, "safe-method"
    auth = str(headers.get("Authorization", ""))
    if auth.lower().startswith("bearer "):
        return True, "bearer-exempt"
    origin = headers.get("Origin")
    if not origin:
        return False, "missing-origin"
    if not str(origin).lower().startswith(("http://", "https://")):
        return False, "invalid-origin"
    if hmac.compare_digest(str(origin).rstrip("/").lower(),
                           str(expected_origin).rstrip("/").lower()):
        return True, "origin-match"
    return False, "origin-mismatch"


# --- W7.11: streaming body / multipart / recording bounds ------------------


class BodyTooLargeError(BackendError):
    pass


class StreamingBodyLimiter:
    """W7.11: enforce a byte cap while chunks stream (no Content-Length needed)."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max(1, int(max_bytes))
        self.received = 0

    def feed(self, chunk: bytes) -> bytes:
        self.received += len(chunk)
        if self.received > self.max_bytes:
            raise BodyTooLargeError(
                f"streamed body exceeds {self.max_bytes} bytes")
        return chunk

    def feed_all(self, chunks: Any) -> bytes:
        return b"".join(self.feed(c) for c in chunks)


def bounded_multipart(parts: list[tuple[str, bytes]], *, max_part_bytes: int = 1_000_000,
                      max_total_bytes: int = 4_000_000,
                      max_parts: int = 50) -> dict[str, bytes]:
    """W7.11: parse multipart fields under hard part/count/total bounds."""
    if len(parts) > max_parts:
        raise BodyTooLargeError("too many multipart parts")
    out: dict[str, bytes] = {}
    total = 0
    for name, value in parts:
        data = value if isinstance(value, bytes) else str(value).encode("utf-8")
        if len(data) > max_part_bytes:
            raise BodyTooLargeError(f"multipart part too large: {name}")
        total += len(data)
        if total > max_total_bytes:
            raise BodyTooLargeError("multipart total too large")
        out[str(name)] = data
    return out


def cap_recording(events: list[dict], *, max_events: int = 500,
                  max_bytes: int = 1_000_000) -> list[dict]:
    """W7.11: cap a recording by event count and serialized byte size."""
    kept: list[dict] = []
    size = 0
    for event in events[:max_events]:
        encoded = len(json.dumps(event, default=str).encode("utf-8"))
        if size + encoded > max_bytes:
            break
        kept.append(event)
        size += encoded
    return kept


# --- W7.12: generic client errors + request id -----------------------------


def generic_error(request_id: str | None = None, *,
                  message: str = "An internal error occurred. Please try again.") -> dict:
    """W7.12: a client-facing error with no internal detail."""
    return {"error": {"message": message,
                      "request_id": request_id or secrets.token_hex(8)}}


def log_error_detail(log_path: str | Path, request_id: str, detail: str) -> Path:
    """W7.12: write the real detail to the server-only log (never the client)."""
    path = _contained_path(Path(log_path).parent, Path(log_path).name,
                           label="log path")
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": _utc_now(), "request_id": request_id,
             "detail": str(detail)[:4000]}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return path


# --- W7.15: share tokens + public redaction --------------------------------

SHARE_TOKEN_BITS = 144


def new_share_token() -> str:
    """W7.15: 144 bits of CSPRNG randomness, encoded URL-safe."""
    return secrets.token_urlsafe(SHARE_TOKEN_BITS // 8)


def share_token_entropy_bits(token: str) -> int:
    """Estimate entropy from a token_urlsafe string (6 bits per char)."""
    return len(token) * 6


def public_share_view(transcript: dict, *, preview_chars: int = 160) -> dict:
    """W7.15: build a public view with redacted text and short tool previews.

    Owner identity and instructions are *never* included.
    """
    text_parts: list[str] = []
    for message in transcript.get("messages", []):
        if not isinstance(message, dict):
            continue
        content = message.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(b.get("text", "")) for b in content
                               if isinstance(b, dict))
        text_parts.append(str(content))
    joined = _scrub_secrets(" ".join(text_parts))
    previews: list[str] = []
    for call in transcript.get("tool_calls", [])[:5]:
        raw = call.get("args", "") if isinstance(call, dict) else str(call)
        previews.append(_scrub_secrets(str(raw))[:60])
    return {
        "text": joined[:preview_chars],
        "tool_previews": previews,
        "owner": None,
        "instructions": None,
        "redaction_level": "public-share",
    }


def render_share_html(view: dict) -> str:
    """W7.15/Z3: local HTML export using the same public redaction level."""
    # Scrub again: callers may hand this renderer a view they built themselves
    # rather than one returned by ``public_share_view``.
    safe_text = html.escape(_scrub_secrets(str(view.get("text", ""))))
    items = "".join(f"<li>{html.escape(_scrub_secrets(str(p)))}</li>"
                    for p in view.get("tool_previews", []))
    return ("<!doctype html><html><body>"
            f"<main><p>{safe_text}</p><ul>{items}</ul></main>"
            "</body></html>")


# --- W7.18: atomic spend ledger --------------------------------------------


class SpendLimitExceeded(BackendError):
    pass


class InvalidSpendAmount(BackendError):
    """A charge/cap that is not a positive, finite, representable amount."""


class AtomicSpendLedger:
    """W7.18/A3.10: check-then-increment inside one lock (DB transaction sim)."""

    _SCALE = 1_000_000  # integer micro-units avoid float drift

    def __init__(self, caps: dict[str, float]):
        self.caps = {k: self._units(v) for k, v in caps.items()}
        self._spent: dict[str, int] = {}
        self._lock = threading.Lock()

    @classmethod
    def _units(cls, amount: float) -> int:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise InvalidSpendAmount("amount must be a number")
        value = float(amount)
        if not math.isfinite(value) or value <= 0:
            raise InvalidSpendAmount("amount must be finite and > 0")
        units = int(round(value * cls._SCALE))
        if units <= 0:
            raise InvalidSpendAmount("amount is too small to represent in micro-units")
        return units

    def authorize_and_charge(self, vendor: str, amount: float) -> dict:
        cost = self._units(amount)
        with self._lock:  # atomic with respect to concurrent callers
            cap = self.caps.get(vendor, 0)
            used = self._spent.get(vendor, 0)
            if used + cost > cap:
                raise SpendLimitExceeded(
                    f"{vendor} spend cap exceeded: {used + cost} > {cap}")
            self._spent[vendor] = used + cost
            return {"vendor": vendor, "charged_units": cost,
                    "spent": (used + cost) / self._SCALE, "cap": cap / self._SCALE}

    def spent(self, vendor: str) -> float:
        with self._lock:
            return self._spent.get(vendor, 0) / self._SCALE


# --- W7.20: deployment hygiene ---------------------------------------------


def redact_keys_for_display(text: str) -> str:
    """W7.20: remove keys from anything shown on screen or in recordings."""
    out = _scrub_secrets(str(text))
    out = re.sub(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*\S+",
                 r"\1=[REDACTED]", out)
    return out


def deployment_hygiene_report(config: dict) -> dict:
    """W7.20: evaluate the operator's deployment-hygiene checklist."""
    checks = {
        "narrowest_scope_keys": bool(config.get("key_scope") == "narrow"),
        "no_keys_on_screen": bool(config.get("display_redaction", True)),
        "no_keys_in_recordings": bool(config.get("recording_redaction", True)),
        "provider_spend_limits": bool(config.get("provider_spend_limits")),
        "always_allow_guarded": not bool(config.get("always_allow", False)),
        "private_vuln_reporting": bool(config.get("private_vuln_reporting")),
        "latest_branch_only": bool(config.get("latest_branch_only", True)),
        "best_effort_fixes": bool(config.get("best_effort_fixes", True)),
    }
    failures = [name for name, ok in checks.items() if not ok]
    return {"checks": checks, "ok": not failures, "failures": failures}


def support_policy() -> str:
    """W7.20/X10: the published support-policy statement."""
    return ("Only the latest release branch is supported; fixes are best-effort. "
            "Report vulnerabilities privately. Keys are scoped narrowly, never "
            "displayed or recorded, and provider spend limits are set.")


# ===========================================================================
# X1.* — model/tool intelligence backend
# ===========================================================================

# --- X1.6: apply-model role -------------------------------------------------


def apply_model_merge(original: str, sketch: str, *, max_diff_lines: int = 40) -> dict:
    """X1.6: merge a sketch edit only if the diff stays under the size guard."""
    base = original.splitlines()
    new = sketch.splitlines()
    diff = list(difflib.unified_diff(base, new, lineterm=""))
    changed = sum(1 for line in diff
                  if line and line[0] in "+-" and not line.startswith(("+++", "---")))
    if changed > max_diff_lines:
        return {"applied": False, "content": original, "diff_lines": changed,
                "reason": "diff size guard exceeded"}
    return {"applied": True, "content": sketch, "diff_lines": changed, "reason": ""}


# --- X1.9: few-shot tool exemplars -----------------------------------------

FEW_SHOT_EXEMPLARS = [
    'assistant to=read_file {"path":"README.md"}',
    'assistant to=list_dir {"path":"."}',
    'assistant to=run_tests {"suite":"unit"}',
]


def exemplars_for_probe(probe_score: float, *, threshold: float = 0.6,
                        max_examples: int = 2) -> list[str]:
    """X1.9: inject exemplars only for weak models; strong models get none."""
    score = max(0.0, min(1.0, float(probe_score)))
    if score >= threshold:
        return []
    count = max_examples if score < threshold / 2 else 1
    return list(FEW_SHOT_EXEMPLARS[:count])


# --- X1.10: self-consistency voting ----------------------------------------


@dataclass
class VoteResult:
    winner: str | None
    counts: dict[str, int]
    judge_used: bool
    disabled: bool


def self_consistency_vote(samples: list[str], *, think_harder_level: int,
                          judge: Callable[[list[str]], str] | None = None) -> VoteResult:
    """X1.10: majority vote over N samples, only at user-enabled levels."""
    if think_harder_level <= 0 or not samples:
        return VoteResult(winner=None, counts={}, judge_used=False, disabled=True)
    counts = dict(Counter(samples))
    top = max(counts.values())
    leaders = sorted(k for k, v in counts.items() if v == top)
    if len(leaders) == 1:
        return VoteResult(winner=leaders[0], counts=counts,
                          judge_used=False, disabled=False)
    if judge is not None:
        return VoteResult(winner=judge(list(samples)), counts=counts,
                          judge_used=True, disabled=False)
    return VoteResult(winner=leaders[0], counts=counts,
                      judge_used=False, disabled=False)


# --- X1.11: streaming partial-JSON tool arguments --------------------------


class PartialJSONParser:
    """X1.11: show args while streaming; expose a result only when complete."""

    _MAX_CHARS = 100_000

    def __init__(self):
        self._buffer = ""
        self._complete = False
        self._value: dict | None = None

    def feed(self, chunk: str) -> dict:
        self._buffer += str(chunk)
        if len(self._buffer) > self._MAX_CHARS:
            raise BackendError("tool-argument stream too large")
        candidate = self._buffer.strip()
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate)
        try:
            parsed = json.loads(candidate)
        except (ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            self._complete = True
            self._value = parsed
        return {"partial": self._buffer, "complete": self._complete}

    def partial_view(self) -> dict:
        """Best-effort view of keys seen so far (never executed)."""
        keys = re.findall(r'"([^"\\]+)"\s*:', self._buffer)
        return {"keys": list(dict.fromkeys(keys)),
                "raw_length": len(self._buffer), "complete": self._complete}

    def result(self) -> dict:
        if not self._complete or self._value is None:
            raise BackendError("tool arguments are not complete/valid yet")
        return dict(self._value)


# --- X1.12: parallel tool calls with dependency check ----------------------


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    read_only: bool
    depends_on: tuple[str, ...] = ()


def plan_tool_batches(calls: list[ToolCall]) -> list[list[ToolCall]]:
    """X1.12: independent reads run in parallel; writes are serialized."""
    by_id = {c.id: c for c in calls}
    if len(by_id) != len(calls):
        raise BackendError("duplicate tool-call ids")
    for call in calls:
        for dep in call.depends_on:
            if dep not in by_id:
                raise BackendError(f"unknown dependency: {dep}")
    # Longest-path level from dependencies (also detects cycles via topo sort).
    level: dict[str, int] = {}
    visiting: set[str] = set()

    def visit(cid: str) -> int:
        if cid in level:
            return level[cid]
        if cid in visiting:
            raise BackendError("dependency cycle in tool calls")
        visiting.add(cid)
        deps = by_id[cid].depends_on
        lvl = 0 if not deps else 1 + max(visit(d) for d in deps)
        visiting.remove(cid)
        level[cid] = lvl
        return lvl

    for call in calls:
        visit(call.id)
    batches: list[list[ToolCall]] = []
    for lvl in sorted(set(level.values())):
        group = [c for c in calls if level[c.id] == lvl]
        reads = [c for c in group if c.read_only]
        writes = [c for c in group if not c.read_only]
        if reads:
            batches.append(reads)  # safe to run concurrently
        for write in writes:
            batches.append([write])  # one per batch => serialized
    return batches


# --- X1.14: model switch mid-session ---------------------------------------


def estimate_tokens(text: str) -> int:
    """Crude local token estimate (~4 chars/token) for context-fit warnings."""
    return max(1, (len(text) + 3) // 4)


def render_history(history: list[dict], dialect: str) -> list[dict]:
    """X1.14: re-render history into the new model's dialect."""
    if dialect not in ("anthropic", "openai"):
        raise BackendError(f"unknown dialect: {dialect}")
    rendered: list[dict] = []
    for message in history:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, list):
            text = " ".join(str(b.get("text", "")) for b in content
                            if isinstance(b, dict))
        else:
            text = str(content)
        if dialect == "anthropic":
            rendered.append({"role": role, "content": [{"type": "text", "text": text}]})
        else:
            rendered.append({"role": role, "content": text})
    return rendered


def context_fit_warning(token_count: int, capacity: int, *, threshold: float = 0.9) -> str | None:
    if capacity <= 0 or token_count <= threshold * capacity:
        return None
    return f"history ({token_count} tokens) may not fit new model context ({capacity})"


def switch_model(session: dict, new_model: str, *, dialect: str,
                 capacity: int) -> dict:
    """X1.14: switch model, re-render history and surface a context warning."""
    history = render_history(session.get("history", []), dialect)
    tokens = sum(estimate_tokens(json.dumps(m)) for m in history)
    updated = dict(session)
    updated.update({"model": new_model, "dialect": dialect, "history": history,
                    "estimated_tokens": tokens})
    warning = context_fit_warning(tokens, capacity)
    if warning:
        updated["warning"] = warning
    return updated


# --- X1.15: per-model prompt profiles --------------------------------------

PROMPT_PROFILES: dict[str, dict] = {
    "claude": {"version": 2, "system": "You are Keel, a precise coding assistant."},
    "gpt": {"version": 1, "system": "You are a helpful coding assistant. Be concise."},
    "small": {"version": 1, "system": "Follow the user's request exactly. Be brief."},
}


def model_family(model_id: str) -> str:
    """X1.15: classify a model id into a family + size bucket."""
    low = str(model_id).lower()
    if any(word in low for word in ("haiku", "mini", "small", "nano", "8b")):
        return "small"
    if "claude" in low or "anthropic" in low:
        return "claude"
    if any(word in low for word in ("gpt", "openai", "o1", "o3")):
        return "gpt"
    return "gpt"


def prompt_profile(model_id: str) -> dict:
    """X1.15: versioned system-prompt variant for a model."""
    family = model_family(model_id)
    profile = dict(PROMPT_PROFILES[family])
    profile.update({"family": family, "model": model_id})
    return profile


# --- X1.16: model health check ---------------------------------------------


def model_health_check(results: dict[str, bool]) -> dict:
    """X1.16: aggregate canned-probe results into a reliability report."""
    probes = ("tool_call", "json_validity", "long_context")
    passed = {name: bool(results.get(name, False)) for name in probes}
    ok = all(passed.values())
    return {"probes": passed, "ok": ok,
            "badge": "healthy" if ok else "degraded"}


# ===========================================================================
# Y5.* — channel plugins, webhooks and operations backend
# ===========================================================================

# --- Y5.1: plugin.json manifest + config namespace -------------------------


def validate_plugin_manifest(doc: dict) -> list[str]:
    """Y5.1: validate a plugin.json manifest; return errors (empty = valid)."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["manifest must be an object"]
    if not isinstance(doc.get("name"), str) or not _PLUGIN_ID_RE.match(doc["name"]):
        errors.append("invalid or missing 'name'")
    version = str(doc.get("version", ""))
    if not re.match(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$", version):
        errors.append("invalid or missing 'version'")
    if not isinstance(doc.get("keel"), dict):
        errors.append("missing 'keel' section")
    return errors


def config_namespace(plugin_id: str) -> dict:
    """Y5.1: the config keys owned by a channel plugin."""
    if not _PLUGIN_ID_RE.match(plugin_id):
        raise BackendError(f"invalid plugin id: {plugin_id}")
    return {"channels": f"channels.{plugin_id}",
            "load_paths_key": "plugins.load.paths",
            "local_dev": {"plugins.load.paths": [f"./plugins/{plugin_id}"]}}


# --- Y5.2: git URL install --------------------------------------------------

_GIT_SSH_RE = re.compile(r"^[\w.-]+@[\w.-]+:[\w./-]+\.git$")


def parse_install_source(source: str, *, link: bool = False) -> dict:
    """Y5.2: build an install plan from a git URL or local --link path."""
    source = str(source).strip()
    if link:
        if not source:
            raise BackendError("--link requires a local path")
        return {"method": "link", "source": source,
                "prepare": "pip install -e .", "link": True}
    parsed = urllib.parse.urlparse(source)
    is_https = parsed.scheme in ("http", "https") and parsed.netloc
    is_ssh = bool(_GIT_SSH_RE.match(source))
    if not (is_https or is_ssh):
        raise BackendError("plugin source must be a git URL or use --link")
    return {"method": "git", "source": source, "scheme": parsed.scheme or "ssh",
            "prepare": "python -m build && pip install dist/*.whl", "link": False}


# --- Y5.3: webhook subscription lifecycle ----------------------------------

SUPPORTED_EVENTS = frozenset({
    "message.received", "message.delivered", "message.read", "message.failed",
    "reaction.added", "reaction.removed", "typing.started", "typing.stopped",
})


class WebhookSubscriptionManager:
    """Y5.3: subscribe/unsubscribe with a retained signing secret."""

    def __init__(self, credentials_dir: str | Path):
        self.path = _contained_path(
            credentials_dir, "webhook-subscriptions.json", label="credentials path")
        self._lock = _lock_for_path(self.path)

    def _load(self) -> dict:
        doc = _load_json(self.path, {})
        return doc if isinstance(doc, dict) else {}

    def subscribe(self, url: str, events: list[str], *, label: str = "",
                  allow_http: bool = False) -> dict:
        events = list(events)
        unknown = [e for e in events if e not in SUPPORTED_EVENTS]
        if unknown or not events:
            raise BackendError(f"unsupported events: {unknown or 'empty'}")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise BackendError("webhook url must be http(s)")
        if parsed.scheme == "http" and not allow_http:
            raise BackendError("http webhook requires allow_http=True")
        sub_id = secrets.token_urlsafe(12)
        entry = {"id": sub_id, "url": url, "events": events, "label": str(label)[:80],
                 "signing_secret": secrets.token_urlsafe(32), "created_at": _utc_now(),
                 "active": True}
        with self._lock:
            doc = self._load()
            doc.setdefault("subscriptions", {})[sub_id] = entry
            _atomic_write(self.path, json.dumps(doc, indent=2) + "\n")
        return entry

    def get(self, sub_id: str) -> dict | None:
        return self._load().get("subscriptions", {}).get(sub_id)

    def list(self) -> list[dict]:
        return list(self._load().get("subscriptions", {}).values())

    def unsubscribe(self, sub_id: str) -> bool:
        with self._lock:
            doc = self._load()
            entry = doc.get("subscriptions", {}).get(sub_id)
            if not entry:
                return False
            entry["active"] = False
            _atomic_write(self.path, json.dumps(doc, indent=2) + "\n")
        return True


def create_webhook_subscription(manager: WebhookSubscriptionManager, url: str,
                                events: list[str], **kwargs: Any) -> dict:
    """Y5.3: exported programmatic helper for subscription creation."""
    return manager.subscribe(url, events, **kwargs)


# --- Y5.5: reaction mapping -------------------------------------------------

_SKIN_TONES = frozenset(chr(c) for c in range(0x1F3FB, 0x1F400))
REACTION_MAP = {
    "👍": {"native": "thumbsup", "group": "positive"},
    "❤️": {"native": "heart", "group": "affection"},
    "😂": {"native": "laugh", "group": "humor"},
    "🎉": {"native": "tada", "group": "celebration"},
    "👀": {"native": "eyes", "group": "attention"},
}


def _base_emoji(emoji: str) -> str:
    return "".join(ch for ch in emoji if ch not in _SKIN_TONES)


def map_reaction(emoji: str) -> dict | None:
    """Y5.5: map an emoji (incl. skin-tone variants) to a native reaction."""
    base = _base_emoji(str(emoji).strip())
    entry = REACTION_MAP.get(base)
    if entry is None:
        return None
    return dict(entry, emoji=base, skin_tone=str(emoji)[len(base):] or None)


def react_action(emoji: str, target: str, *, remove: bool = False) -> dict:
    """Y5.5: agent-usable react/remove action."""
    mapped = map_reaction(emoji)
    if mapped is None:
        raise BackendError(f"unsupported reaction: {emoji}")
    return {"action": "unreact" if remove else "react", "target": target,
            "native": mapped["native"], "emoji": mapped["emoji"]}


# --- Y5.6: chat-id mapping cache -------------------------------------------


class ChatIdCache:
    """Y5.6: cache external↔internal chat ids under the credentials dir."""

    def __init__(self, credentials_dir: str | Path):
        self.path = _contained_path(
            credentials_dir, "chat-id-map.json", label="credentials path")
        self._lock = _lock_for_path(self.path)

    def _load(self) -> dict:
        doc = _load_json(self.path, {})
        return doc if isinstance(doc, dict) else {}

    def put(self, channel: str, external_id: str, internal_id: str) -> None:
        with self._lock:
            doc = self._load()
            doc.setdefault(channel, {})[str(external_id)] = str(internal_id)
            _atomic_write(self.path, json.dumps(doc, indent=2) + "\n")

    def get(self, channel: str, external_id: str) -> str | None:
        return self._load().get(channel, {}).get(str(external_id))

    def size(self) -> int:
        return sum(len(v) for v in self._load().values() if isinstance(v, dict))

    def reset(self) -> bool:
        """Documented reset: delete the cache so it rebuilds from the gateway."""
        if self.path.is_file():
            self.path.unlink()
            return True
        return False


# --- Y5.7: status and gateway commands -------------------------------------


def channel_status(loaded_channels: dict) -> dict:
    """Y5.7: ``status`` — list loaded channels and their state."""
    entries = [{"id": cid, "enabled": bool(meta.get("enabled", True)),
                "state": meta.get("state", "idle")}
               for cid, meta in sorted((loaded_channels or {}).items())]
    return {"channels": entries, "count": len(entries)}


def gateway_start(config: dict) -> dict:
    """Y5.7: ``gateway start`` — describe a validated gateway launch."""
    channels = [c for c, meta in (config.get("channels", {}) or {}).items()
                if meta.get("enabled", True)]
    if not channels:
        raise BackendError("gateway start requires at least one enabled channel")
    return {"command": "gateway start", "state": "starting",
            "channels": sorted(channels)}


# --- Y5.8: troubleshooting by exact error strings --------------------------

TROUBLESHOOTING = {
    "token not configured": "Set the channel bot token in the credentials store and reload.",
    "fromNumber not configured": "Set the sending number in the channel config and reload.",
    "webhook not receiving": "Verify HTTPS, the signing secret, and that the URL is reachable.",
}


def troubleshoot(error: str) -> dict | None:
    """Y5.8: exact-string lookup only (no fuzzy matching)."""
    key = str(error)
    if key not in TROUBLESHOOTING:
        return None
    return {"error": key, "remediation": TROUBLESHOOTING[key]}


# --- Y5.9: excluded channels ------------------------------------------------

EXCLUDED_CHANNELS = {
    "linq-api": "Blocked for free",
    "imessage": "Blocked for free",
    "rcs": "Blocked for free",
    "sms": "Blocked for free",
}
SUPPORTED_CHANNELS = frozenset({"telegram", "discord", "slack", "whatsapp"})


def channel_availability(name: str) -> str:
    """Y5.9: Linq API/iMessage/RCS/SMS are paid/cloud and blocked for free."""
    key = str(name).lower()
    if key in EXCLUDED_CHANNELS:
        return EXCLUDED_CHANNELS[key]
    if key in SUPPORTED_CHANNELS:
        return "available"
    return "unknown"


__all__ = [name for name in globals() if not name.startswith("_") and name != "annotations"]
