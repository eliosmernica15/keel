"""Pure invariant contracts for the a9-v P0 addendum rows (V1/V2/V5/V16/V24/V26/V31).

This is an *additive*, stdlib-only module.  It does not import, edit or depend
on any existing Keel module (in particular not ``tool_contracts`` or
``session_contracts``): the seven P0 rows below are materialized here as real,
testable, fail-closed Python descriptors and checkers.  Every value is owned by
the caller; there is no file I/O, no network, no subprocess, no socket, no
clock, no chance and no import-time side effect.

Feature map
-----------
* **V1**  -- ``Scope`` / ``plugin_scope`` / ``register``: a context-manager
  scope tree.  Registrations (tools, hooks, routes, UI panels, timers,
  subprocesses) return ``Disposable`` handles that are disposed automatically
  on unload; permissions flow down to children only, never up, and a child can
  never escalate beyond its parent.
* **V2**  -- ``simulate`` / ``SimulationTrace``: a policy simulator that emits
  a JSON trace with ordered rule evaluations, matched rules, the winning rule,
  a per-resource decision, a human-readable multi-resource denial reason and a
  Tier-2 verdict.
* **V5**  -- ``preset_rules`` / ``STRICTNESS_ORDER``: Cautious, Balanced and
  Trusted as ordered rule sets built on the V2 matcher (monotonically more
  permissive).
* **V16** -- ``GATE_CATALOG`` / ``check_gate`` / ``run_all_gates``: the Keel
  invariant-gate catalog (Tier-2 table hash, offline suite, no secret in logs,
  presenter/plugin-manifest/i18n/migration/Any-baseline gates).  Every gate has
  a failing fixture that proves rejection.
* **V24** -- ``CONFORMANCE_CHECKS`` / ``check_tool_conformance`` /
  ``conformance_gate``: a tool conformance *descriptor/checker* (this is NOT
  the existing ``tool_contracts`` module).  Every check has a failing fixture.
* **V26** -- ``reconstruct_request`` / ``verify_reconstruction``: replay a
  session log into the exact provider request and byte/hash-compare it with
  what was sent ("model-visible = logged", D2.11).
* **V31** -- ``TRANSPORT_CANDIDATES`` / ``spike_decision`` / ``select_transport``:
  a descriptor-level local-socket transport spike (named pipe / UDS / TCP+token
  fallback) with streaming and backpressure criteria -- no real socket is ever
  opened.

Security invariants (enforced by ``test_invariant_contracts``):

* unknown or malformed values always fail closed (raise ``ContractValidationError``
  or produce a failing result), never silently permissive;
* denied-by-default policy evaluation, with deny winning over allow;
* permissions only inherit downward and can only be narrowed;
* no secret material in logs or trace output;
* all hashes are canonical (sorted keys, compact separators, UTF-8).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import threading
import weakref
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

FEATURE_IDS = ("V1", "V2", "V5", "V16", "V24", "V26", "V31")


# ---------------------------------------------------------------------------
# shared helpers: typed errors, canonical bytes, secret scrubbing
# ---------------------------------------------------------------------------


class ContractError(ValueError):
    """Base class for invariant-contract failures."""


class ContractValidationError(ContractError):
    """Fail-closed validation error; messages are always scrubbed."""

    def __init__(self, message: Any):
        self.raw_message = "" if message is None else str(message)
        super().__init__(redact_text(self.raw_message))


_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_\-]{12,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password)\b\s*[:=]\s*\S+"),
)


def is_secret_like(value: Any) -> bool:
    """Best-effort detection of a literal credential in caller-supplied text."""
    text = "" if value is None else str(value)
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def redact_text(value: Any) -> str:
    """Return text with detected secret material replaced by ``[REDACTED]``."""
    text = "" if value is None else str(value)
    for pattern in _SECRET_PATTERNS:
        if pattern is _SECRET_PATTERNS[-1]:
            text = pattern.sub(
                lambda m: "%s=[REDACTED]" % (m.group(1),), text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def canonical_bytes(value: Any) -> bytes:
    """Stable UTF-8 encoding shared by every fingerprint in this module."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value: Any) -> str:
    """SHA-256 of the canonical representation of ``value``."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _as_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractValidationError("%s must be a non-empty string" % label)
    return value


def _as_str_tuple(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, (list, tuple)) or not value:
        raise ContractValidationError("%s must be a non-empty sequence" % label)
    result = tuple(_as_str(item, "%s item" % label) for item in value)
    return result


def _as_mapping(value: Any, label: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise ContractValidationError("%s must be a mapping" % label)
    return value


# ===========================================================================
# V1 -- plugin scope tree
# ===========================================================================

REGISTRATION_KINDS = frozenset({
    "tool", "hook", "route", "ui_panel", "timer", "subprocess",
})


class ScopeError(ContractError):
    """Raised when a registration is attempted outside a live scope."""


@dataclass
class Disposable:
    """A registration handle.  ``close`` is idempotent."""

    kind: str
    name: str
    _on_dispose: Callable[[], None] | None = None
    disposed: bool = False

    def close(self) -> None:
        if self.disposed:
            return
        self.disposed = True
        if self._on_dispose is not None:
            self._on_dispose()

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return "Disposable(%s,%s,disposed=%s)" % (self.kind, self.name, self.disposed)


_ALL_SCOPES: "weakref.WeakSet[Scope]" = weakref.WeakSet()
_STATE = threading.local()


def _stack() -> list[Scope]:
    stack = getattr(_STATE, "stack", None)
    if stack is None:
        stack = []
        _STATE.stack = stack
    return stack


class Scope:
    """A lifecycle-safe scope.  Use as a context manager to load/unload.

    On exit the scope is closed: every registration is disposed (LIFO) and all
    child scopes are closed first.  A closed scope cannot register anything or
    grant permissions (fail closed).
    """

    def __init__(self, name: str, permissions: Iterable[str] = (),
                 parent: Scope | None = None):
        self.name = _as_str(name, "scope name")
        if parent is not None and not isinstance(parent, Scope):
            raise ContractValidationError("parent must be a Scope")
        self.parent = parent
        raw = tuple(permissions or ())
        if not all(isinstance(p, str) and p for p in raw):
            raise ContractValidationError("permissions must be non-empty strings")
        granted = frozenset(raw)
        if parent is not None:
            # permissions flow down only: a child may only narrow its parent.
            illegal = granted - parent._permissions
            if illegal:
                raise ContractValidationError(
                    "child cannot gain parent-unheld permission(s): %s"
                    % ",".join(sorted(illegal)))
        self._permissions = granted
        self.registrations: list[Disposable] = []
        self.children: list[Scope] = []
        self.closed = False
        _ALL_SCOPES.add(self)
        if parent is not None:
            parent.children.append(self)

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> Scope:
        if self.closed:
            raise ScopeError("cannot re-enter a closed scope")
        _stack().append(self)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        stack = _stack()
        if stack and stack[-1] is self:
            stack.pop()
        self.close()
        return False

    # -- lifecycle ----------------------------------------------------------
    def register(self, kind: str, name: str,
                 on_dispose: Callable[[], None] | None = None) -> Disposable:
        if self.closed:
            raise ScopeError("cannot register on a closed scope")
        if kind not in REGISTRATION_KINDS:
            raise ContractValidationError("unknown registration kind: %s" % kind)
        _as_str(name, "registration name")
        if on_dispose is not None and not callable(on_dispose):
            raise ContractValidationError("on_dispose must be callable")
        handle = Disposable(kind=kind, name=name, _on_dispose=on_dispose)
        self.registrations.append(handle)
        return handle

    def child(self, name: str, permissions: Iterable[str] = ()) -> Scope:
        if self.closed:
            raise ScopeError("cannot create a child on a closed scope")
        return Scope(name, permissions, parent=self)

    def close(self) -> int:
        """Dispose children then own registrations (LIFO).  Returns count."""
        if self.closed:
            return 0
        self.closed = True
        count = 0
        for child in list(self.children):
            count += child.close()
        for handle in reversed(self.registrations):
            handle.close()
            count += 1
        return count

    # -- permissions (inherit down, never up) -------------------------------
    def has_permission(self, permission: str) -> bool:
        return (not self.closed and isinstance(permission, str)
                and permission in self._permissions)

    def require_permission(self, permission: str) -> None:
        if not self.has_permission(permission):
            raise ScopeError("permission denied: %s" % permission)

    def grant_permission(self, permission: str) -> None:
        _as_str(permission, "permission")
        if self.closed:
            raise ScopeError("cannot grant on a closed scope")
        if self.parent is not None and not self.parent.has_permission(permission):
            raise ContractValidationError(
                "cannot escalate beyond parent permission: %s" % permission)
        self._permissions = self._permissions | {permission}

    def effective_permissions(self) -> frozenset[str]:
        return frozenset() if self.closed else frozenset(self._permissions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parent": self.parent.name if self.parent is not None else None,
            "permissions": sorted(self._permissions),
            "registrations": [
                {"kind": r.kind, "name": r.name, "disposed": r.disposed}
                for r in self.registrations
            ],
            "children": [c.name for c in self.children],
            "closed": self.closed,
        }


def active_scope() -> Scope | None:
    """Return the currently loaded scope, if any."""
    stack = _stack()
    return stack[-1] if stack else None


def plugin_scope(name: str, permissions: Iterable[str] = (),
                 parent: Scope | None = None) -> Scope:
    """Create a fresh scope for one plugin load.  Use in a ``with`` block."""
    return Scope(name, permissions, parent=parent)


def register(kind: str, name: str,
             on_dispose: Callable[[], None] | None = None) -> Disposable:
    """Register on the *active* scope only.  No active scope fails closed."""
    scope = active_scope()
    if scope is None:
        raise ScopeError("registration requires an active scope")
    return scope.register(kind, name, on_dispose)


def live_disposables() -> tuple[Disposable, ...]:
    """All not-yet-disposed handles across every scope (leak detection)."""
    live: list[Disposable] = []
    for scope in list(_ALL_SCOPES):
        live.extend(h for h in scope.registrations if not h.disposed)
    return tuple(live)


def assert_no_leaks() -> None:
    """Raise if any registration is still live (test/CI helper)."""
    leaked = live_disposables()
    if leaked:
        raise ScopeError("leaked %d registration(s): %s" % (
            len(leaked), ",".join(h.name for h in leaked)))


# ===========================================================================
# V2 -- policy simulator with winning-rule trace
# ===========================================================================


class Effect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class Verdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class Tier2Verdict(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    PASS = "pass"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Rule:
    id: str
    effect: Effect
    actions: tuple[str, ...]
    resources: tuple[str, ...]
    tier2_ack: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "effect": self.effect.value,
            "actions": list(self.actions), "resources": list(self.resources),
            "tier2_ack": self.tier2_ack,
        }


def make_rule(id: str, effect: Effect | str, actions: Any, resources: Any,
              tier2_ack: bool = False) -> Rule:
    """Validate and build an ordered policy rule."""
    rid = _as_str(id, "rule id")
    try:
        eff = Effect(effect)
    except (ValueError, TypeError):
        raise ContractValidationError("unknown rule effect: %s" % effect) from None
    if not isinstance(tier2_ack, bool):
        raise ContractValidationError("tier2_ack must be a bool")
    return Rule(rid, eff, _as_str_tuple(actions, "actions"),
                _as_str_tuple(resources, "resources"), tier2_ack)


@dataclass(frozen=True)
class Operation:
    action: str
    resources: tuple[str, ...]
    tier: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "resources": list(self.resources),
                "tier": self.tier}


def make_operation(action: str, resources: Any, tier: int = 1) -> Operation:
    act = _as_str(action, "action")
    if tier not in (1, 2) or isinstance(tier, bool):
        raise ContractValidationError("tier must be 1 or 2")
    return Operation(act, _as_str_tuple(resources, "resources"), tier)


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    effect: Effect
    matched: bool
    matched_resources: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "effect": self.effect.value,
                "matched": self.matched,
                "matched_resources": list(self.matched_resources),
                "reason": self.reason}


@dataclass(frozen=True)
class ResourceDecision:
    resource: str
    winner_id: str | None
    effect: Verdict | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"resource": self.resource, "winner_id": self.winner_id,
                "effect": self.effect.value if self.effect else None,
                "reason": self.reason}


def _pattern_matches(pattern: str, value: str) -> bool:
    return fnmatch.fnmatchcase(value, pattern)


def _rule_matches(rule: Rule, op: Operation, resource: str) -> bool:
    return (any(_pattern_matches(p, op.action) for p in rule.actions)
            and any(_pattern_matches(p, resource) for p in rule.resources))


@dataclass(frozen=True)
class SimulationTrace:
    operation: Operation
    evaluations: tuple[RuleEvaluation, ...]
    per_resource: tuple[ResourceDecision, ...]
    winner_id: str | None
    verdict: Verdict
    denial_reason: str
    tier2: Tier2Verdict

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.to_dict(),
            "rules": [e.to_dict() for e in self.evaluations],
            "per_resource": [d.to_dict() for d in self.per_resource],
            "winner_id": self.winner_id,
            "verdict": self.verdict.value,
            "denial_reason": self.denial_reason,
            "tier2_verdict": self.tier2.value,
        }

    def to_json(self) -> str:
        """Canonical JSON trace, suitable for ``keel policy test`` / the UI."""
        return json.dumps(self.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)


def simulate(operation: Operation, rules: Iterable[Rule],
             tier2_approved: bool = False) -> SimulationTrace:
    """Evaluate an operation against *ordered* rules; deny is fail-closed.

    For each resource the first matching DENY wins; otherwise the first
    matching ALLOW wins; otherwise the resource is denied by default.  A
    multi-resource operation is allowed only when every resource is allowed.
    Tier-2 operations additionally require an acknowledgement (rule-level or
    caller-level) or they are denied.
    """
    if not isinstance(operation, Operation):
        raise ContractValidationError("operation must be an Operation")
    if not isinstance(tier2_approved, bool):
        raise ContractValidationError("tier2_approved must be a bool")
    ordered = tuple(rules or ())
    if not all(isinstance(r, Rule) for r in ordered):
        raise ContractValidationError("rules must contain only Rule objects")

    evaluations: list[RuleEvaluation] = []
    for rule in ordered:
        matched = tuple(r for r in operation.resources
                        if _rule_matches(rule, operation, r))
        reason = ("matched %d resource(s)" % len(matched)) if matched else "no match"
        evaluations.append(RuleEvaluation(
            rule.id, rule.effect, bool(matched), matched, reason))

    per_resource: list[ResourceDecision] = []
    for resource in operation.resources:
        denies = [r for r in ordered if _rule_matches(r, operation, resource)
                  and r.effect is Effect.DENY]
        allows = [r for r in ordered if _rule_matches(r, operation, resource)
                  and r.effect is Effect.ALLOW]
        if denies:
            winner = denies[0]
            per_resource.append(ResourceDecision(
                resource, winner.id, Verdict.DENY,
                "resource %r matched deny rule %r" % (resource, winner.id)))
        elif allows:
            winner = allows[0]
            per_resource.append(ResourceDecision(
                resource, winner.id, Verdict.ALLOW,
                "resource %r allowed by rule %r" % (resource, winner.id)))
        else:
            per_resource.append(ResourceDecision(
                resource, None, None,
                "resource %r had no matching allow rule (default deny)" % resource))

    denied = [d for d in per_resource if d.effect is not Verdict.ALLOW]
    verdict = Verdict.DENY if denied else Verdict.ALLOW
    denial_reason = "; ".join(d.reason for d in denied)

    # winning rule = earliest deny that determined the verdict, else earliest
    # authorizing allow, else None (default deny).
    deny_indices = [i for i, r in enumerate(ordered)
                    if any(d.winner_id == r.id and d.effect is Verdict.DENY
                           for d in per_resource)]
    allow_indices = [i for i, r in enumerate(ordered)
                     if any(d.winner_id == r.id and d.effect is Verdict.ALLOW
                            for d in per_resource)]
    if deny_indices:
        winner_id = ordered[min(deny_indices)].id
    elif verdict is Verdict.ALLOW and allow_indices:
        winner_id = ordered[min(allow_indices)].id
    else:
        winner_id = None

    if operation.tier != 2:
        tier2 = Tier2Verdict.NOT_APPLICABLE
    elif verdict is Verdict.DENY:
        tier2 = Tier2Verdict.BLOCKED
    else:
        authorizers = [r for r in ordered
                       if any(d.winner_id == r.id for d in per_resource)]
        if tier2_approved or all(r.tier2_ack for r in authorizers):
            tier2 = Tier2Verdict.PASS
        else:
            tier2 = Tier2Verdict.REQUIRES_APPROVAL
            verdict = Verdict.DENY
            winner_id = None
            denial_reason = ("tier-2 operation requires approval: "
                             + denial_reason if denial_reason
                             else "tier-2 operation requires approval")

    return SimulationTrace(operation, tuple(evaluations), tuple(per_resource),
                           winner_id, verdict, denial_reason, tier2)


# ===========================================================================
# V5 -- strictness presets as ordered rule sets
# ===========================================================================


class Strictness(str, Enum):
    CAUTIOUS = "cautious"
    BALANCED = "balanced"
    TRUSTED = "trusted"


STRICTNESS_ORDER = (Strictness.CAUTIOUS, Strictness.BALANCED, Strictness.TRUSTED)


def _cautious_rules() -> tuple[Rule, ...]:
    return (
        make_rule("C-DENY-RISKY", Effect.DENY,
                  ("exec", "delete", "write"), "*"),
        make_rule("C-DENY-SECRET", Effect.DENY, "*", "secret:*"),
        make_rule("C-ALLOW-READ", Effect.ALLOW, "read", "*"),
    )


def _balanced_rules() -> tuple[Rule, ...]:
    return (
        make_rule("B-DENY-SECRET", Effect.DENY, "*", "secret:*"),
        make_rule("B-DENY-EXEC", Effect.DENY, ("exec", "delete"), "*"),
        make_rule("B-ALLOW-FILE", Effect.ALLOW, ("read", "write"),
                  ("file:*", "net:read", "config:read"), tier2_ack=True),
        make_rule("B-ALLOW-READ", Effect.ALLOW, "read", "*", tier2_ack=True),
    )


def _trusted_rules() -> tuple[Rule, ...]:
    return (
        make_rule("T-DENY-SECRET", Effect.DENY, "*", "secret:*"),
        make_rule("T-ALLOW-ALL", Effect.ALLOW, "*", "*", tier2_ack=True),
    )


_PRESETS: dict[Strictness, Callable[[], tuple[Rule, ...]]] = {
    Strictness.CAUTIOUS: _cautious_rules,
    Strictness.BALANCED: _balanced_rules,
    Strictness.TRUSTED: _trusted_rules,
}


def preset_rules(strictness: Strictness | str) -> tuple[Rule, ...]:
    """Return the ordered rule set for a strictness preset (fail closed)."""
    try:
        level = Strictness(strictness)
    except (ValueError, TypeError):
        raise ContractValidationError("unknown strictness: %s" % strictness) from None
    return _PRESETS[level]()


def describe_preset(strictness: Strictness | str) -> dict[str, Any]:
    levels = {s.value: s for s in STRICTNESS_ORDER}
    level = levels.get(str(strictness))
    if level is None:
        raise ContractValidationError("unknown strictness: %s" % strictness)
    rules = preset_rules(level)
    return {"strictness": level.value, "rule_ids": [r.id for r in rules],
            "rule_count": len(rules)}


# ===========================================================================
# V16 -- invariant-gate catalog
# ============================================================================

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Gate:
    id: str
    title: str
    description: str
    checker: str
    failing_fixture: dict[str, Any]


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    passed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"gate_id": self.gate_id, "passed": self.passed,
                "reason": self.reason}


def compute_tier2_hash(table: Any) -> str:
    """Canonical hash of the Tier-2 table (content, not object identity)."""
    _as_mapping(table, "tier2 table")
    return content_hash(dict(table))


def _obs(observation: Any, key: str, label: str = "observation") -> Any:
    data = _as_mapping(observation, label)
    if key not in data:
        raise KeyError(key)
    return data[key]


def _check_tier2_hash(obs: Mapping) -> tuple[bool, str]:
    expected = _obs(obs, "expected_hash")
    if not isinstance(expected, str) or not _HEX64_RE.match(expected):
        return False, "expected_hash must be a 64-char lowercase hex digest"
    if "table" in obs:
        actual = compute_tier2_hash(obs["table"])
    elif "current_hash" in obs:
        actual = obs["current_hash"]
    else:
        return False, "missing both 'table' and 'current_hash'"
    return (expected == actual), ("Tier-2 table hash unchanged"
                                  if expected == actual else "Tier-2 table hash changed")


def _check_offline_net(obs: Mapping) -> tuple[bool, str]:
    try:
        offline = _obs(obs, "offline")
        calls = _obs(obs, "network_calls")
    except KeyError as exc:
        return False, "missing observation key: %s" % exc.args[0]
    if not isinstance(offline, bool) or not isinstance(calls, int) or isinstance(calls, bool):
        return False, "offline must be bool and network_calls an int"
    ok = offline and calls == 0
    return ok, ("offline suite made no network calls" if ok
                else "offline suite observed %d network call(s)" % calls)


def _check_no_secret_logs(obs: Mapping) -> tuple[bool, str]:
    try:
        lines = _obs(obs, "log_lines")
    except KeyError as exc:
        return False, "missing observation key: %s" % exc.args[0]
    if isinstance(lines, (str, bytes)) or not isinstance(lines, Sequence):
        return False, "log_lines must be a sequence of strings"
    for line in lines:
        if is_secret_like(line):
            return False, "secret material found in log: %s" % redact_text(line)
    return True, "no secret material in logs"


def _check_tool_presenter(obs: Mapping) -> tuple[bool, str]:
    try:
        tools = _obs(obs, "tools")
    except KeyError as exc:
        return False, "missing observation key: %s" % exc.args[0]
    tools_map = _as_mapping(tools, "tools")
    missing = [name for name, meta in tools_map.items()
               if not isinstance(meta, Mapping) or meta.get("presenter") is not True]
    if missing:
        return False, "tools without presenter: %s" % ",".join(sorted(map(str, missing)))
    return True, "every tool declares a presenter"


def _check_plugin_permissions(obs: Mapping) -> tuple[bool, str]:
    try:
        manifests = _obs(obs, "manifests")
    except KeyError as exc:
        return False, "missing observation key: %s" % exc.args[0]
    manifests_map = _as_mapping(manifests, "manifests")
    missing = [name for name, manifest in manifests_map.items()
               if not isinstance(manifest, Mapping)
               or not isinstance(manifest.get("permissions"), list)]
    if missing:
        return False, "manifests without declared permissions: %s" % ",".join(
            sorted(map(str, missing)))
    return True, "every plugin manifest declares permissions"


def _check_no_hardcoded_copy(obs: Mapping) -> tuple[bool, str]:
    try:
        strings = _obs(obs, "ui_strings")
    except KeyError as exc:
        return False, "missing observation key: %s" % exc.args[0]
    if isinstance(strings, (str, bytes)) or not isinstance(strings, Sequence):
        return False, "ui_strings must be a sequence"
    bad = [s for s in strings
           if not isinstance(s, str) or not s.startswith("i18n:")]
    if bad:
        return False, "hardcoded UI copy: %s" % ",".join(redact_text(s) for s in bad)
    return True, "all UI copy is referenced through i18n keys"


def _check_migration_matrix(obs: Mapping) -> tuple[bool, str]:
    try:
        matrix = _obs(obs, "matrix")
        source = _obs(obs, "from_version")
        target = _obs(obs, "to_version")
    except KeyError as exc:
        return False, "missing observation key: %s" % exc.args[0]
    matrix_map = _as_mapping(matrix, "matrix")
    supported = matrix_map.get(source)
    if not isinstance(supported, (list, tuple)) or target not in supported:
        return False, "migration %s -> %s is not in the compat matrix" % (source, target)
    return True, "migration is covered by the compat matrix"


def _check_any_baseline(obs: Mapping) -> tuple[bool, str]:
    try:
        count = _obs(obs, "any_count")
        baseline = _obs(obs, "baseline_any_count")
    except KeyError as exc:
        return False, "missing observation key: %s" % exc.args[0]
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (count, baseline)):
        return False, "Any counts must be integers"
    ok = count <= baseline
    return ok, ("no Any baseline growth (%d <= %d)" % (count, baseline) if ok
                else "Any baseline grew (%d > %d)" % (count, baseline))


_GATE_CHECKERS: dict[str, Callable[[Mapping], tuple[bool, str]]] = {
    "tier2_hash": _check_tier2_hash,
    "offline_net": _check_offline_net,
    "no_secret_logs": _check_no_secret_logs,
    "tool_presenter": _check_tool_presenter,
    "plugin_permissions": _check_plugin_permissions,
    "no_hardcoded_copy": _check_no_hardcoded_copy,
    "migration_matrix": _check_migration_matrix,
    "any_baseline": _check_any_baseline,
}


GATE_CATALOG: tuple[Gate, ...] = (
    Gate("V16.TIER2_HASH", "Tier-2 table hash unchanged",
         "The canonical hash of the Tier-2 table must not drift.",
         "tier2_hash", {"expected_hash": "0" * 64, "current_hash": "1" * 64}),
    Gate("V16.OFFLINE_NET", "No outbound network in offline suite",
         "The offline suite must observe zero network calls.",
         "offline_net", {"offline": True, "network_calls": 1}),
    Gate("V16.NO_SECRET_LOGS", "No secret in logs",
         "No log line may contain a literal credential.",
         "no_secret_logs", {"log_lines": ["api_key=sk-abcdefghijklmnopqrstuvwxyz"]}),
    Gate("V16.TOOL_PRESENTER", "Every tool has a presenter",
         "Each registered tool must declare a presenter.",
         "tool_presenter", {"tools": {"shell": {"presenter": False}}}),
    Gate("V16.PLUGIN_PERMISSIONS", "Every plugin manifest declares permissions",
         "Each plugin manifest must carry an explicit permissions list.",
         "plugin_permissions", {"manifests": {"ext": {"name": "ext"}}}),
    Gate("V16.NO_HARDCODED_COPY", "No hardcoded UI copy",
         "UI strings must be i18n references, not literal copy.",
         "no_hardcoded_copy", {"ui_strings": ["Save"]}),
    Gate("V16.MIGRATION_MATRIX", "Migration compat matrix",
         "Every from->to migration must be listed in the compat matrix.",
         "migration_matrix",
         {"matrix": {"v1": ["v2"]}, "from_version": "v1", "to_version": "v3"}),
    Gate("V16.ANY_BASELINE", "No Any baseline growth",
         "The count of Any annotations must not exceed the frozen baseline.",
         "any_baseline", {"any_count": 12, "baseline_any_count": 11}),
)

_GATE_BY_ID = {gate.id: gate for gate in GATE_CATALOG}


def check_gate(gate_id: str, observation: Mapping) -> GateResult:
    """Run one catalog gate.  Unknown gate ids fail closed."""
    gate = _GATE_BY_ID.get(gate_id)
    if gate is None:
        raise ContractValidationError("unknown invariant gate: %s" % gate_id)
    checker = _GATE_CHECKERS[gate.checker]
    try:
        passed, reason = checker(_as_mapping(observation, "observation"))
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        return GateResult(gate.id, False, "gate input rejected: %s" % redact_text(exc))
    return GateResult(gate.id, bool(passed), reason)


def run_all_gates(observations: Mapping[str, Mapping]) -> tuple[GateResult, ...]:
    """Run the whole catalog; a missing observation is a failing gate."""
    _as_mapping(observations, "observations")
    results = []
    for gate in GATE_CATALOG:
        if gate.id not in observations:
            results.append(GateResult(gate.id, False, "missing gate observation"))
        else:
            results.append(check_gate(gate.id, observations[gate.id]))
    return tuple(results)


def all_gates_pass(results: Iterable[GateResult]) -> bool:
    return all(r.passed for r in results)


def gate_fixture_result(gate_id: str) -> GateResult:
    """Run a gate against its own failing fixture (must fail)."""
    gate = _GATE_BY_ID.get(gate_id)
    if gate is None:
        raise ContractValidationError("unknown invariant gate: %s" % gate_id)
    return check_gate(gate.id, gate.failing_fixture)


def check_all_failing_fixtures() -> dict[str, GateResult]:
    """Every catalog gate must reject its failing fixture."""
    return {gate.id: gate_fixture_result(gate.id) for gate in GATE_CATALOG}


# ===========================================================================
# V24 -- tool conformance kit (descriptor/checker, NOT tool_contracts)
# ===========================================================================


@dataclass(frozen=True)
class ConformanceCheck:
    id: str
    title: str
    required_keys: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title,
                "required_keys": list(self.required_keys)}


CONFORMANCE_CHECKS: tuple[ConformanceCheck, ...] = (
    ConformanceCheck("output_schema_declared", "Output schema declared",
                     ("output_schema",)),
    ConformanceCheck("presenter_pure_on_replay", "Presenter pure on replay",
                     ("presenter_pure", "replay_hashes")),
    ConformanceCheck("cancel_within_budget", "Cancel honored within N ms",
                     ("cancel_latency_ms", "max_cancel_ms")),
    ConformanceCheck("no_leaked_fields", "No leaked fields in schemas()",
                     ("output_schema", "secret_fields")),
    ConformanceCheck("concurrency_read_only", "Concurrency only on read-only tools",
                     ("concurrency", "read_only")),
    ConformanceCheck("timeout_cooperative", "Timeout cooperative",
                     ("timeout_cooperative",)),
    ConformanceCheck("errors_typed", "Errors typed",
                     ("error_codes", "allowed_error_codes")),
)

_CONFORMANCE_BY_ID = {c.id: c for c in CONFORMANCE_CHECKS}


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    passed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"check_id": self.check_id, "passed": self.passed,
                "reason": self.reason}


@dataclass(frozen=True)
class ConformanceReport:
    tool: str
    results: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "passed": self.passed,
                "checks": [r.to_dict() for r in self.results]}


def _check_conformance(check_id: str, meta: Mapping) -> CheckResult:
    check = _CONFORMANCE_BY_ID.get(check_id)
    if check is None:
        raise ContractValidationError("unknown conformance check: %s" % check_id)
    missing = [key for key in check.required_keys if key not in meta]
    if missing:
        return CheckResult(check_id, False, "missing metadata: %s" % ",".join(missing))

    if check_id == "output_schema_declared":
        schema = meta["output_schema"]
        ok = isinstance(schema, Mapping) and bool(schema) and "type" in schema
        reason = "output schema declared" if ok else "output_schema must be a non-empty schema with 'type'"

    elif check_id == "presenter_pure_on_replay":
        pure = meta["presenter_pure"]
        hashes = meta["replay_hashes"]
        ok = (pure is True and isinstance(hashes, (list, tuple))
              and len(hashes) >= 2 and all(isinstance(h, str) for h in hashes)
              and len(set(hashes)) == 1)
        reason = "presenter is pure on replay" if ok else "presenter replay hashes differ or presenter not pure"

    elif check_id == "cancel_within_budget":
        latency, budget = meta["cancel_latency_ms"], meta["max_cancel_ms"]
        ok = (isinstance(budget, (int, float)) and not isinstance(budget, bool)
              and budget > 0 and isinstance(latency, (int, float))
              and not isinstance(latency, bool) and latency <= budget)
        reason = "cancel within budget" if ok else "cancel latency %s exceeds budget %s" % (latency, budget)

    elif check_id == "no_leaked_fields":
        schema, secret_fields = meta["output_schema"], meta["secret_fields"]
        props = schema.get("properties", {}) if isinstance(schema, Mapping) else {}
        ok = isinstance(props, Mapping) and isinstance(secret_fields, (list, tuple, set, frozenset))
        leaked = set() if not ok else set(map(str, secret_fields)) & set(map(str, props.keys()))
        ok = ok and not leaked
        reason = "no leaked fields" if ok else "schema leaks field(s): %s" % ",".join(sorted(leaked))

    elif check_id == "concurrency_read_only":
        concurrency, read_only = meta["concurrency"], meta["read_only"]
        ok = (isinstance(concurrency, bool) and isinstance(read_only, bool)
              and (not concurrency or read_only))
        reason = "concurrency flag is valid" if ok else "concurrency flag set on a non-read-only tool"

    elif check_id == "timeout_cooperative":
        ok = meta["timeout_cooperative"] is True
        reason = "timeout is cooperative" if ok else "timeout is not cooperative"

    elif check_id == "errors_typed":
        codes, allowed = meta["error_codes"], meta["allowed_error_codes"]
        ok = (isinstance(codes, (list, tuple)) and isinstance(allowed, (list, tuple, set, frozenset))
              and bool(allowed) and all(isinstance(c, str) for c in codes)
              and set(codes) <= set(allowed))
        reason = "errors are typed" if ok else "error code outside the declared typed vocabulary"

    else:  # pragma: no cover - guarded above
        raise ContractValidationError("unhandled conformance check: %s" % check_id)

    return CheckResult(check_id, ok, reason)


def check_tool_conformance(name: str, metadata: Mapping) -> ConformanceReport:
    """Check one tool's conformance metadata.  Non-mapping input fails closed."""
    _as_str(name, "tool name")
    meta = _as_mapping(metadata, "tool conformance metadata")
    return ConformanceReport(name, tuple(
        _check_conformance(check.id, meta) for check in CONFORMANCE_CHECKS))


@dataclass(frozen=True)
class ConformanceGateReport:
    tools: tuple[str, ...]
    reports: tuple[ConformanceReport, ...]
    missing_metadata: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing_metadata and all(r.passed for r in self.reports)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "tools": list(self.tools),
                "missing_metadata": list(self.missing_metadata),
                "reports": [r.to_dict() for r in self.reports]}


def conformance_gate(tools: Mapping[str, Mapping]) -> ConformanceGateReport:
    """Table-driven gate over a tool registry.

    A tool that has not registered conformance metadata fails the gate, so CI
    fails on any new tool that does not opt in (fail closed).
    """
    registry = _as_mapping(tools, "tools registry")
    reports: list[ConformanceReport] = []
    missing: list[str] = []
    for name, meta in registry.items():
        if (not isinstance(meta, Mapping) or "conformance" not in meta
                or not isinstance(meta["conformance"], Mapping)):
            missing.append(str(name))
            continue
        reports.append(check_tool_conformance(str(name), meta["conformance"]))
    return ConformanceGateReport(tuple(map(str, registry.keys())),
                                 tuple(reports), tuple(missing))


def assert_conformant(tools: Mapping[str, Mapping]) -> None:
    """CI entry point: raise if any tool fails conformance."""
    report = conformance_gate(tools)
    if not report.passed:
        failures = [r.tool for r in report.reports if not r.passed]
        raise ContractValidationError(
            "tool conformance gate failed (missing metadata: %s; failing tools: %s)"
            % (",".join(report.missing_metadata) or "-", ",".join(failures) or "-"))


# A minimal, fully conformant metadata fixture and one failing fixture per check.
def conformant_metadata() -> dict[str, Any]:
    return {
        "output_schema": {"type": "object", "properties": {"stdout": {"type": "string"}}},
        "presenter_pure": True,
        "replay_hashes": ["abc123", "abc123"],
        "cancel_latency_ms": 5,
        "max_cancel_ms": 50,
        "secret_fields": [],
        "concurrency": False,
        "read_only": False,
        "timeout_cooperative": True,
        "error_codes": ["TIMEOUT", "DENIED"],
        "allowed_error_codes": ["TIMEOUT", "DENIED", "INVALID_ARGS"],
    }


_CONFORMANCE_FAILURES: dict[str, Callable[[dict[str, Any]], None]] = {
    "output_schema_declared": lambda m: m.pop("output_schema"),
    "presenter_pure_on_replay": lambda m: m.update(replay_hashes=["a", "b"]),
    "cancel_within_budget": lambda m: m.update(cancel_latency_ms=5000),
    "no_leaked_fields": lambda m: m.update(secret_fields=["stdout"]),
    "concurrency_read_only": lambda m: m.update(concurrency=True, read_only=False),
    "timeout_cooperative": lambda m: m.update(timeout_cooperative=False),
    "errors_typed": lambda m: m.update(error_codes=["UNKNOWN_CODE"]),
}


def failing_conformance_metadata(check_id: str) -> dict[str, Any]:
    if check_id not in _CONFORMANCE_FAILURES:
        raise ContractValidationError("unknown conformance check: %s" % check_id)
    meta = conformant_metadata()
    _CONFORMANCE_FAILURES[check_id](meta)
    return meta


# ===========================================================================
# V26 -- request reconstruction (model-visible = logged)
# ===========================================================================


@dataclass(frozen=True)
class RequestRecord:
    step_id: str
    request: dict[str, Any]
    request_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {"step_id": self.step_id, "request": self.request,
                "request_hash": self.request_hash}


def record_request(step_id: str, request: Mapping,
                   request_hash: str | None = None) -> RequestRecord:
    """Bind a provider request to its canonical hash for a session step."""
    sid = _as_str(step_id, "step_id")
    data = dict(_as_mapping(request, "request"))
    digest = request_hash or content_hash(data)
    return RequestRecord(sid, data, digest)


def reconstruct_request(log: Sequence[Mapping], model: str | None = None) -> dict[str, Any]:
    """Rebuild the exact provider request from logged events only.

    Recognized event kinds: ``model``, ``system_prompt``, ``message``,
    ``tool_spec`` and ``param``.  Anything else fails closed.
    """
    if isinstance(log, (str, bytes, Mapping)) or not isinstance(log, Sequence):
        raise ContractValidationError("session log must be a sequence of events")
    request: dict[str, Any] = {"model": model, "system": None,
                               "messages": [], "tools": [], "params": {}}
    for index, event in enumerate(log):
        if not isinstance(event, Mapping):
            raise ContractValidationError("log event %d must be a mapping" % index)
        kind = event.get("kind")
        if kind == "model":
            request["model"] = _as_str(event.get("value"), "model")
        elif kind == "system_prompt":
            text = event.get("value", "")
            if not isinstance(text, str):
                raise ContractValidationError("system_prompt value must be a string")
            request["system"] = text or None
        elif kind == "message":
            role = _as_str(event.get("role"), "message role")
            content = event.get("content")
            if not isinstance(content, str):
                raise ContractValidationError("message content must be a string")
            request["messages"].append({"role": role, "content": content})
        elif kind == "tool_spec":
            name = _as_str(event.get("name"), "tool name")
            schema = _as_mapping(event.get("schema"), "tool schema")
            request["tools"].append({"name": name, "schema": dict(schema)})
        elif kind == "param":
            key = _as_str(event.get("key"), "param key")
            request["params"][key] = event.get("value")
        else:
            raise ContractValidationError("unknown log event kind: %s" % kind)
    if not isinstance(request["model"], str) or not request["model"]:
        raise ContractValidationError("session log has no model: cannot reconstruct request")
    return request


@dataclass(frozen=True)
class ReconstructionResult:
    passed: bool
    computed_hash: str
    expected_hash: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "computed_hash": self.computed_hash,
                "expected_hash": self.expected_hash, "reason": self.reason}


def verify_reconstruction(log: Sequence[Mapping], expected_hash: str,
                          sent_request: Mapping | None = None,
                          model: str | None = None) -> ReconstructionResult:
    """Replay ``log`` and prove the rebuilt request hashes to ``expected_hash``.

    When ``sent_request`` is supplied, its canonical bytes must also match the
    reconstructed request byte-for-byte (hash equality), proving that what the
    model saw is exactly what was logged.
    """
    if not isinstance(expected_hash, str) or not _HEX64_RE.match(expected_hash):
        raise ContractValidationError("expected_hash must be a 64-char hex digest")
    request = reconstruct_request(log, model=model)
    computed = content_hash(request)
    if sent_request is not None and content_hash(sent_request) != computed:
        return ReconstructionResult(False, computed, expected_hash,
                                     "sent request bytes differ from reconstructed request")
    if computed != expected_hash:
        return ReconstructionResult(False, computed, expected_hash,
                                     "reconstructed request hash differs from recorded request hash")
    return ReconstructionResult(True, computed, expected_hash,
                                 "model-visible request equals logged request")


def session_log_fixture() -> list[dict[str, Any]]:
    """A deterministic session log used by replay tests."""
    return [
        {"kind": "model", "value": "keel-test-model"},
        {"kind": "system_prompt", "value": "You are Keel."},
        {"kind": "message", "role": "user", "content": "read config"},
        {"kind": "tool_spec", "name": "read", "schema": {"type": "object"}},
        {"kind": "param", "key": "temperature", "value": 0},
    ]


def tamper_log(log: Sequence[Mapping], index: int, field: str,
               value: Any) -> list[dict[str, Any]]:
    """Return a copy of ``log`` with one field changed (adversarial helper)."""
    copy_log = [dict(event) for event in log]
    if not 0 <= index < len(copy_log):
        raise ContractValidationError("tamper index out of range")
    copy_log[index][field] = value
    return copy_log


# ===========================================================================
# V31 -- local-socket transport spike descriptor (no real socket)
# ===========================================================================


class Transport(str, Enum):
    NAMED_PIPE = "named_pipe"
    UDS = "uds"
    TCP_TOKEN = "tcp_token"


SUPPORTED_OS = ("windows", "linux", "darwin")


@dataclass(frozen=True)
class TransportDescriptor:
    transport: Transport
    label: str
    os_support: frozenset[str]
    streaming: bool
    backpressure: bool
    peer_auth: bool
    loopback_only: bool
    fallback: bool

    @property
    def viable(self) -> bool:
        """A primary transport must stream, apply backpressure and auth peers."""
        return self.streaming and self.backpressure and self.peer_auth

    def to_dict(self) -> dict[str, Any]:
        return {"transport": self.transport.value, "label": self.label,
                "os_support": sorted(self.os_support), "streaming": self.streaming,
                "backpressure": self.backpressure, "peer_auth": self.peer_auth,
                "loopback_only": self.loopback_only, "fallback": self.fallback,
                "viable": self.viable}


TRANSPORT_CANDIDATES: tuple[TransportDescriptor, ...] = (
    TransportDescriptor(Transport.NAMED_PIPE, "Windows named pipe",
                        frozenset({"windows"}), True, True, True, True, False),
    TransportDescriptor(Transport.UDS, "POSIX Unix domain socket",
                        frozenset({"linux", "darwin"}), True, True, True, True, False),
    TransportDescriptor(Transport.TCP_TOKEN, "Loopback TCP + token (fallback)",
                        frozenset(SUPPORTED_OS), True, True, True, True, True),
)

_BY_TRANSPORT = {d.transport: d for d in TRANSPORT_CANDIDATES}


def validate_transport(descriptor: Any) -> None:
    """Reject unknown or non-viable descriptors (fail closed)."""
    if not isinstance(descriptor, TransportDescriptor):
        raise ContractValidationError("descriptor must be a TransportDescriptor")
    try:
        Transport(descriptor.transport)
    except (ValueError, TypeError):
        raise ContractValidationError("unknown transport: %s" % descriptor.transport) from None
    if not descriptor.viable:
        raise ContractValidationError(
            "transport %s lacks streaming/backpressure/peer-auth" % descriptor.transport.value)


def platform_support(transport: Transport | str, os_name: str) -> bool:
    try:
        kind = Transport(transport)
    except (ValueError, TypeError):
        raise ContractValidationError("unknown transport: %s" % transport) from None
    if os_name not in SUPPORTED_OS:
        raise ContractValidationError("unknown OS: %s" % os_name)
    return os_name in _BY_TRANSPORT[kind].os_support


def select_transport(os_name: str) -> Transport:
    """Choose the local primary for a target OS (fail closed for unknown OS)."""
    if os_name not in SUPPORTED_OS:
        raise ContractValidationError("unknown OS: %s" % os_name)
    if os_name == "windows":
        return Transport.NAMED_PIPE
    return Transport.UDS


@dataclass(frozen=True)
class SpikeDecision:
    primaries: tuple[Transport, ...]
    fallback: Transport
    covered_os: frozenset[str]
    streaming: bool
    backpressure: bool
    peer_auth: bool
    fallback_available: bool

    @property
    def complete(self) -> bool:
        return (self.covered_os == frozenset(SUPPORTED_OS)
                and self.streaming and self.backpressure
                and self.peer_auth and self.fallback_available)

    def to_dict(self) -> dict[str, Any]:
        return {"primaries": [t.value for t in self.primaries],
                "fallback": self.fallback.value,
                "covered_os": sorted(self.covered_os),
                "streaming": self.streaming, "backpressure": self.backpressure,
                "peer_auth": self.peer_auth,
                "fallback_available": self.fallback_available,
                "complete": self.complete}


def evaluate_spike() -> SpikeDecision:
    """Descriptor-level spike verdict: all 3 OSes covered, stream/backpressure,
    peer auth and a TCP+token fallback.  No socket is opened.
    """
    primaries = tuple(select_transport(os_name) for os_name in SUPPORTED_OS)
    primary_descriptors = tuple(_BY_TRANSPORT[t] for t in primaries)
    for descriptor in primary_descriptors:
        validate_transport(descriptor)
    fallback = next((d for d in TRANSPORT_CANDIDATES if d.fallback), None)
    if fallback is None:
        raise ContractValidationError("no fallback transport declared")
    validate_transport(fallback)
    covered = frozenset().union(*(d.os_support for d in primary_descriptors))
    return SpikeDecision(
        primaries=primaries, fallback=fallback.transport, covered_os=covered,
        streaming=all(d.streaming for d in primary_descriptors),
        backpressure=all(d.backpressure for d in primary_descriptors),
        peer_auth=all(d.peer_auth for d in primary_descriptors),
        fallback_available=fallback.transport is Transport.TCP_TOKEN,
    )


def spike_decision() -> SpikeDecision:
    """Return the (cached-free, deterministic) spike decision record."""
    return evaluate_spike()
