"""keel.settings — scoped settings registry (interface-spec §13).

A generic fold over scopes against a typed registry. No per-key special
cases in the resolver. Every resolved key records provenance; every
divergence is a diagnostic.

Scope order (highest first): managed > flags > local > project > user > env > defaults.
Managed-source merge modes: merge | locks | highest-priority-only.
Monotonic keys resolve to the most restrictive value across scopes.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

MANAGED, FLAGS, LOCAL, PROJECT, USER, ENV, DEFAULTS = (
    "managed", "flags", "local", "project", "user", "env", "defaults")
SCOPE_ORDER = [MANAGED, FLAGS, LOCAL, PROJECT, USER, ENV]


@dataclass(frozen=True)
class Entry:
    key: str
    type: str                     # string | number | boolean | string[] | object
    scopes: frozenset[str]        # which non-managed scopes may set it
    default: Any = None
    merge: str = "replace"        # replace | union | deep | monotonic-restrict
    monotonic: bool = False
    env_var: str | None = None
    deprecated: str | None = None
    rank: Callable[[Any], int] | None = None  # monotonic: higher = more restrictive


def _rank_bool_false_strictest(v: Any) -> int:
    return 1 if v is False else 0


_REGISTRY: list[Entry] = [
    Entry("model", "string",
          frozenset({FLAGS, LOCAL, PROJECT, USER, ENV}),
          default="", merge="replace", env_var="KEEL_MODEL"),
    Entry("permissionMode", "string",
          frozenset({FLAGS, LOCAL, PROJECT, USER, ENV}),
          default="default", merge="replace", env_var="KEEL_PERMISSION_MODE"),
    Entry("defaultProvider", "string",
          frozenset({FLAGS, LOCAL, PROJECT, USER, ENV}),
          default="auto", merge="replace", env_var="KEEL_DEFAULT_PROVIDER"),
    Entry("maxTurns", "number",
          frozenset({FLAGS, LOCAL, PROJECT, USER, ENV}),
          default=10, merge="replace", env_var="KEEL_MAX_TURNS"),
    Entry("permissions.allow", "string[]",
          frozenset({FLAGS, LOCAL, PROJECT, USER, ENV}),
          default=["$defaults"], merge="union", env_var="KEEL_PERMISSIONS_ALLOW"),
    Entry("permissions.ask", "string[]",
          frozenset({FLAGS, LOCAL, PROJECT, USER, ENV}),
          default=["$defaults"], merge="union", env_var="KEEL_PERMISSIONS_ASK"),
    Entry("permissions.deny", "string[]",
          frozenset({FLAGS, LOCAL, PROJECT, USER, ENV}),
          default=["$defaults"], merge="union", env_var="KEEL_PERMISSIONS_DENY"),
    Entry("dangerouslyAllowWithoutConfirm", "boolean",
          frozenset({FLAGS, LOCAL, USER, ENV}),   # project may not set it
          default=False, merge="monotonic-restrict", monotonic=True,
          env_var="KEEL_DANGER_ALLOW_UNCONFIRMED",
          rank=_rank_bool_false_strictest),
    Entry("bypassPermissionsEnabled", "boolean",
          frozenset({MANAGED, FLAGS, LOCAL, USER, ENV}),  # project may not set it
          default=False, merge="monotonic-restrict", monotonic=True,
          env_var="KEEL_BYPASS_PERMISSIONS_ENABLED",
          rank=_rank_bool_false_strictest),
    Entry("cleanupPeriodDays", "number",
          frozenset({LOCAL, PROJECT, USER, ENV}),
          default=30, merge="replace", env_var="KEEL_CLEANUP_PERIOD_DAYS"),
    # object deep-merge: {PreToolUse: [{matcher, command, timeout, name?}, ...]}
    Entry("hooks", "object",
          frozenset({FLAGS, LOCAL, PROJECT, USER, ENV}),
          default={}, merge="deep"),
    # object deep-merge: {<server>: {command, args?, env?, scope?}}
    Entry("mcpServers", "object",
          frozenset({FLAGS, LOCAL, PROJECT, USER, ENV}),
          default={}, merge="deep"),
]

_DEFAULT_LIST_SPLICES = {
    "permissions.allow": ["Bash(git status)", "Bash(git diff)", "Read(**/*.md)"],
    "permissions.ask": [],
    "permissions.deny": ["Read(**/.env)", "Read(**/.env.*)",
                         "Bash(git push --force*)"],
}

_BY_KEY = {e.key: e for e in _REGISTRY}


@dataclass
class Diagnostic:
    severity: str      # warning | error
    code: str
    message: str
    source: str = ""   # scope or file


@dataclass
class Resolved:
    value: dict[str, Any]
    provenance: dict[str, dict]
    diagnostics: list[Diagnostic]


def registry_keys() -> list[str]:
    return [e.key for e in _REGISTRY]


def _flatten(flat_prefix: tuple[str, ...] | None, obj: Any) -> dict[str, Any]:
    """Flatten nested object into dotted keys, leaving lists/scalars in place."""
    out: dict[str, Any] = {}
    prefix = flat_prefix or ()
    if not isinstance(obj, dict):
        head = ".".join(prefix)
        return {head: obj} if head else dict(obj)
    for key, val in obj.items():
        parts = prefix + (key,)
        if isinstance(val, dict):
            out.update(_flatten(parts, val))
        else:
            out[".".join(parts)] = val
    return out


def _unflatten(dotted: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in dotted.items():
        parts = key.split(".")
        node = out
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = val
    return out


def _type_ok(entry: Entry, value: Any) -> bool:
    t = entry.type
    if t == "string":
        return isinstance(value, str)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "string[]":
        return isinstance(value, list) and all(isinstance(x, str) for x in value)
    if t == "object":
        return isinstance(value, dict)
    return False


def _coerce_env(entry: Entry, raw: str) -> Any:
    if entry.type == "number":
        return float(raw) if "." in raw else int(raw)
    if entry.type == "boolean":
        if raw.lower() in ("1", "true", "yes"):
            return True
        if raw.lower() in ("0", "false", "no"):
            return False
        raise ValueError(f"not a boolean: {raw!r}")
    if entry.type == "string[]":
        return [x.strip() for x in raw.split(",") if x.strip()]
    return raw


def _splice_defaults(rules: list[str], key: str) -> list[str]:
    """$defaults splices at merge time (§13.6)."""
    spliced = _DEFAULT_LIST_SPLICES.get(key, [])
    result: list[str] = []
    for item in rules:
        if item == "$defaults":
            result.extend(spliced)
        else:
            result.append(item)
    return result


def _merge_values(entry: Entry, layered: list[tuple[str, Any]]) -> tuple[Any, dict]:
    """layered: [(scope, value)] in precedence order (managed first if present)."""
    if entry.merge == "union":
        collected: list[str] = []
        sources = []
        for scope, value in layered:
            collected.extend(_splice_defaults(value, entry.key))
            sources.append(scope)
        # ordered union, first occurrence wins
        seen: set[str] = set()
        out: list[str] = []
        for item in collected:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out, {"scope": sources[0] if sources else DEFAULTS,
                     "overridden": sources[1:]}
    if entry.merge == "monotonic-restrict":
        rank = entry.rank or (lambda v: 0)
        winner_scope, winner_value = max(layered, key=lambda kv: rank(kv[1]))
        overridden = [s for s, v in layered
                      if not (v is winner_value and s == winner_scope)]
        return winner_value, {"scope": winner_scope,
                              "overridden": overridden}
    # replace & deep: highest precedence wins
    if entry.merge == "deep":
        merged: dict[str, Any] = {}
        sources = []
        for scope, value in reversed(layered):
            merged = _deep_merge(merged, copy.deepcopy(value))
            sources.append(scope)
        return merged, {"scope": sources[-1] if sources else DEFAULTS,
                        "overridden": sources[:-1]}
    scope, value = layered[0]
    return copy.deepcopy(value), {"scope": scope,
                                  "overridden": [s for s, _ in layered[1:]]}


def _deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for key, val in b.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _load_json_file(path: Path, scope: str,
                    diagnostics: list[Diagnostic]) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8-sig")  # tolerate PowerShell BOM
    except OSError:
        return None  # absent is fine
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        diagnostics.append(Diagnostic(
            "warning", "settings_json_invalid",
            f"{path}: invalid JSON at line {exc.lineno} col {exc.colno}; "
            "file ignored, other scopes still resolve", scope))
        return None
    if not isinstance(data, dict):
        diagnostics.append(Diagnostic(
            "warning", "settings_json_invalid",
            f"{path}: top level must be a JSON object; file ignored", scope))
        return None
    return data


def load_scope_files(*, state_root: Path, cwd: Path,
                     diagnostics: list[Diagnostic] | None = None
                     ) -> tuple[dict[str, dict], list[Diagnostic]]:
    """Read the file-backed scopes. Managed merge mode is honoured."""
    diagnostics = diagnostics if diagnostics is not None else []
    scopes: dict[str, dict] = {}

    managed: dict[str, Any] = {}
    for base in (Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "keel",
                 Path("/etc/keel")):
        path = base / "managed-settings.json"
        data = _load_json_file(path, MANAGED, diagnostics)
        if data:
            managed.update(data)
        extra = base / "managed-settings.d"
        if extra.is_dir():
            for f in sorted(extra.glob("*.json")):
                data = _load_json_file(f, MANAGED, diagnostics)
                if data:
                    managed.update(data)
    if managed:
        scopes[MANAGED] = managed

    for scope, path in ((USER, Path(state_root) / "settings.json"),
                        (PROJECT, Path(cwd) / ".claude" / "settings.json"),
                        (LOCAL, Path(cwd) / ".claude" / "settings.local.json")):
        data = _load_json_file(path, scope, diagnostics)
        if data:
            scopes[scope] = data

    return scopes, diagnostics


def resolve(*, state_root: Path, cwd: Path, flags: dict[str, Any] | None = None,
            bare: bool = False) -> Resolved:
    diagnostics: list[Diagnostic] = []
    flags = flags or {}
    file_scopes, diagnostics = load_scope_files(
        state_root=state_root, cwd=cwd, diagnostics=diagnostics)
    if bare:
        # bare: no project/user/local files — flags and defaults only
        file_scopes = {MANAGED: file_scopes[MANAGED]} if MANAGED in file_scopes else {}

    flat_scopes: dict[str, dict[str, Any]] = {}
    managed_mode = "locks"
    for scope, obj in file_scopes.items():
        obj = dict(obj)
        if scope == MANAGED:
            managed_mode = str(obj.pop("$merge", "locks"))
            if managed_mode not in ("merge", "locks", "highest-priority-only"):
                diagnostics.append(Diagnostic(
                    "warning", "managed_merge_unknown",
                    f"$merge {managed_mode!r} not recognised; treating as 'locks'",
                    MANAGED))
                managed_mode = "locks"
        flat_scopes[scope] = _flatten((), obj)

    flat_scopes[FLAGS] = _flatten((), flags)

    env_flat: dict[str, Any] = {}
    for entry in _REGISTRY:
        if entry.env_var and entry.env_var in os.environ:
            try:
                env_flat[entry.key] = _coerce_env(
                    entry, os.environ[entry.env_var])
            except (ValueError, TypeError) as exc:
                diagnostics.append(Diagnostic(
                    "warning", "env_unparseable",
                    f"{entry.env_var}: {exc}; falling back to default",
                    ENV))
    if env_flat:
        flat_scopes[ENV] = env_flat

    # group object fragments ("hooks.Foo") into nested dicts per scope; the
    # scalar path never sees them
    object_keys = {e.key for e in _REGISTRY if e.type == "object"}
    object_scopes: dict[str, dict[str, dict]] = {k: {} for k in object_keys}
    scalar_scopes: dict[str, dict[str, Any]] = {}
    for scope, flat in flat_scopes.items():
        scalar: dict[str, Any] = {}
        for key, value in flat.items():
            matched_obj = next((ok for ok in object_keys
                                if key == ok or key.startswith(ok + ".")), None)
            if matched_obj is not None:
                rest = key[len(matched_obj):].lstrip(".")
                parts = [p for p in rest.split(".") if p]
                if not parts:  # a whole-object value set as one flag
                    if isinstance(value, dict):
                        object_scopes[matched_obj][scope] = \
                            _deep_merge(object_scopes[matched_obj].get(scope, {}),
                                        copy.deepcopy(value))
                    continue
                node = object_scopes[matched_obj].setdefault(scope, {})
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        node[part] = value
                    else:
                        node = node.setdefault(part, {})
                continue
            scalar[key] = value
        scalar_scopes[scope] = scalar
    flat_scopes = scalar_scopes

    reg_keys = set(_BY_KEY)
    dep_keys = {e.deprecated for e in _REGISTRY if e.deprecated}
    for scope, flat in flat_scopes.items():
        for key in flat:
            if key not in reg_keys and key not in dep_keys:
                diagnostics.append(Diagnostic(
                    "warning", "unknown_key",
                    f"{scope}: unknown settings key {key!r}; ignored",
                    scope))

    resolved: dict[str, Any] = {}
    flat_resolved: dict[str, Any] = {}
    provenance: dict[str, dict] = {}

    managed_keys = set(flat_scopes.get(MANAGED, {}))
    for entry in _REGISTRY:
        if entry.type == "object":
            continue  # handled by the object-fold pass below
        layered: list[tuple[str, Any]] = []
        skipped: list[str] = []

        def consider(scope: str, provided: dict[str, Any],
                     require_allowed: bool = True):
            if entry.key in provided:
                if require_allowed and scope != MANAGED and scope not in entry.scopes:
                    diagnostics.append(Diagnostic(
                        "warning", "scope_not_permitted",
                        f"{scope} scope may not set {entry.key}; ignored",
                        scope))
                    return
                value = provided[entry.key]
                if not _type_ok(entry, value):
                    diagnostics.append(Diagnostic(
                        "warning", "wrong_type",
                        f"{scope}: {entry.key} has the wrong type; "
                        "falling back to default", scope))
                    return
                layered.append((scope, value))
            # deprecated key honoured with provenance tag
            if entry.deprecated and entry.deprecated in provided:
                value = provided[entry.deprecated]
                if _type_ok(entry, value):
                    layered.append((scope, value))
                    provenance[entry.key] = {
                        "scope": scope,
                        "deprecated": entry.key,
                    }

        for scope in SCOPE_ORDER:  # precedence order
            if scope not in flat_scopes:
                continue
            if scope == MANAGED:
                if managed_mode == "highest-priority-only":
                    consider(MANAGED, flat_scopes[MANAGED],
                             require_allowed=False)
                    # only managed consulted for keys it sets; here we
                    # short-circuit by dropping all other scopes' values later
                    continue
                consider(MANAGED, flat_scopes[MANAGED],
                         require_allowed=False)
                continue
            if managed_mode == "highest-priority-only" and entry.key in managed_keys:
                continue
            consider(scope, flat_scopes[scope])

        if not layered:
            # default
            default = entry.default
            if isinstance(default, list):
                default = _splice_defaults(list(default), entry.key)
            flat_resolved[entry.key] = default
            provenance.setdefault(entry.key, {"scope": DEFAULTS})
            continue

        value, meta = _merge_values(entry, layered)
        flat_resolved[entry.key] = value
        provenance[entry.key] = meta

    # object-typed entries (deep merge, precedence order)
    for entry in (e for e in _REGISTRY if e.type == "object"):
        per_scope = object_scopes.get(entry.key, {})
        managed_sub = per_scope.get(MANAGED)
        layered: list[tuple[str, Any]] = []
        for scope in SCOPE_ORDER:
            fragment = per_scope.get(scope)
            if fragment is None:
                continue
            if (managed_mode == "highest-priority-only"
                    and scope != MANAGED and managed_sub):
                continue
            layered.append((scope, fragment))
        if not layered:
            flat_resolved[entry.key] = copy.deepcopy(entry.default)
            provenance[entry.key] = {"scope": DEFAULTS}
            continue
        merged: dict[str, Any] = {}
        for scope, fragment in reversed(layered):
            merged = _deep_merge(merged, copy.deepcopy(fragment))
        flat_resolved[entry.key] = merged
        provenance[entry.key] = {"scope": layered[0][0],
                                 "overridden": [s for s, _ in layered[1:]]}

    value = _unflatten(flat_resolved)
    for key, meta in provenance.items():
        if meta.get("deprecated"):
            meta["scope"] = f"deprecated:{meta['deprecated']}"
    return Resolved(value=value, provenance=_unflatten(provenance),
                    diagnostics=diagnostics)


def as_rule_lists(resolved: Resolved) -> tuple[list[str], list[str], list[str]]:
    perms = resolved.value.get("permissions", {})
    return (list(perms.get("deny", [])),
            list(perms.get("ask", [])),
            list(perms.get("allow", [])))


def default_state_root() -> Path:
    return Path(os.path.expanduser("~")) / ".keel"
