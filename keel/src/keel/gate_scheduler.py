"""Pure dev-workflow contracts: gate scheduler, strict linker, CI, benchmarks.

This module is the stdlib-only, host-independent contract surface for four P0
addendum-6 rows (``D7.1``, ``D7.9``, ``D7.12``, ``D7.19``).  It deliberately
holds no host state: no process, file, environment-read, network, clock or
chance input.  Callers own every identifier, outcome and context value; the
functions here only describe, validate, plan and render.  ``to_dict``/``as_dict``
exchange plain data so a caller may persist it through its own storage layer.

Feature map
-----------
* **D7.1** -- ``GateSpec``/``GateGraph`` model every gate as a dependency
  graph (with cycle detection); ``SchedulerPolicy``/``parse_scheduler_env``
  bound concurrency (``KEEL_GATE_CONCURRENCY``) and switch fail-fast
  (``KEEL_GATE_FAIL_FAST``); ``simulate_gates`` is a deterministic, *simulated*
  run over caller-supplied outcomes.  A failure skips only its transitive
  dependents so every independent error is still reported; fail-fast cancels
  only gates that have not started.
* **D7.9** -- ``LockEntry``/``DependencyManifest`` model a hash-pinned
  lockfile with an explicit build-script allowlist.  ``link_dependencies``
  fails closed on an undeclared import, a floating version, a missing or
  malformed hash, a duplicate pin, an unknown ecosystem or a build script
  that was not allowlisted for that exact package.
* **D7.12** -- ``CILane``/``CI_LANES`` describe the broad gates lane, the
  small Python matrix, separate native Windows/macOS workflows, required
  hosted-Linux benchmarks and the opt-in, self-skipping provider-e2e lane.
  ``partition_coverage`` shards coverage by per-platform timing data.
* **D7.19** -- ``BenchmarkMethod``/``BenchmarkTask`` pin the ``sdk-minimal``
  JSON-RPC agent profile and require a distinct isolated workspace and
  session id per independent task.

Invariants (enforced by ``test_gate_scheduler``):

* every unknown, malformed or ambiguous value fails closed (no silent pass,
  no wildcard allowlist, no implicit environment access);
* all results, digests and schedules are deterministic and order independent;
* simulation never starts a process - it is a pure function of its arguments;
* no secret material is accepted in a reference field.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

FEATURE_IDS = ("D7.1", "D7.9", "D7.12", "D7.19")


class ContractError(ValueError):
    """Base class for gate-scheduler contract failures."""


class ContractValidationError(ContractError):
    """Fail-closed validation error carrying one or more written reasons."""

    def __init__(self, errors: Any):
        if isinstance(errors, str):
            errors = (errors,)
        self.errors = tuple(str(error) for error in errors)
        super().__init__("; ".join(self.errors))


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_PACKAGE_RE = re.compile(
    r"^(?:@[a-z0-9][a-z0-9_.\-]*/)?[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z.+\-]*$")
_DIGEST_RE = re.compile(r"^(?:sha256:[0-9a-f]{64}|sha512:[0-9a-f]{128})$")
_WORKFLOW_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*\.yml$")
_PYTHON_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
_ENCODED_TRAVERSAL_RE = re.compile(r"(?i)%2e|%2f|%5c")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _named(value: Any, label: str) -> str:
    text = _text(value).strip()
    if not text or not _IDENTIFIER_RE.match(text):
        raise ContractValidationError(
            "%s must be a non-empty safe identifier" % label)
    return text


def _values(values: Any, label: str) -> tuple[str, ...]:
    """Coerce an iterable of caller-owned names; a bare string is not a list."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ContractValidationError("%s must be an iterable of names" % label)
    return tuple(_text(value) for value in values)


def _canonical_digest(payload: Any) -> str:
    """sha256 over a canonical JSON form; no host state, no chance input."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _is_secret_reference(value: Any) -> bool:
    match = re.match(r"^(env|keyring|secret|file):(.+)$", _text(value).strip(),
                     re.IGNORECASE)
    if match is None:
        return False
    name = match.group(2)
    return bool(name) and not re.search(r"[^A-Za-z0-9_./:\-]", name) and ".." not in name


# ---------------------------------------------------------------------------
# D7.1 -- gate dependency graph
# ---------------------------------------------------------------------------

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_CANCELLED = "cancelled"

CONCURRENCY_ENV = "KEEL_GATE_CONCURRENCY"
FAIL_FAST_ENV = "KEEL_GATE_FAIL_FAST"
DEFAULT_CONCURRENCY = 4
MAX_CONCURRENCY = 64
_GATE_ENV_KEYS = frozenset({CONCURRENCY_ENV, FAIL_FAST_ENV})


@dataclass(frozen=True)
class GateSpec:
    """One gate: an identifier, its prerequisite gate ids and its CI lane."""

    gate_id: str
    depends_on: tuple[str, ...] = ()
    lane: str = "gates"

    def as_dict(self) -> dict:
        return {
            "gate_id": self.gate_id,
            "depends_on": list(self.depends_on),
            "lane": self.lane,
        }


def make_gate(gate_id: Any, depends_on: Iterable[Any] = (),
              lane: Any = "gates") -> GateSpec:
    """Build a validated gate.  Cross-gate checks happen in the graph builder."""
    name = _named(gate_id, "gate id")
    deps = _values(depends_on, "gate dependencies")
    for dep in deps:
        if not dep or not _IDENTIFIER_RE.match(dep):
            raise ContractValidationError("dependency id is not a safe identifier")
    if name in deps:
        raise ContractValidationError("gate %s cannot depend on itself" % name)
    if len(set(deps)) != len(deps):
        raise ContractValidationError("gate %s has duplicate dependencies" % name)
    return GateSpec(gate_id=name, depends_on=tuple(sorted(deps)),
                    lane=_named(lane, "gate lane"))


def find_cycle(specs: Iterable[GateSpec]) -> tuple[str, ...]:
    """Return one deterministic cycle ``(a, b, ..., a)`` or ``()`` if acyclic."""
    by_id: dict[str, GateSpec] = {}
    for spec in specs:
        if isinstance(spec, GateSpec):
            by_id[spec.gate_id] = spec
    edges = {
        name: [dep for dep in spec.depends_on if dep in by_id]
        for name, spec in by_id.items()
    }
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(name: str) -> tuple[str, ...]:
        state[name] = 1
        stack.append(name)
        for dep in sorted(edges.get(name, ())):
            if state.get(dep) == 1:
                index = stack.index(dep)
                return tuple(stack[index:] + [dep])
            if state.get(dep, 0) == 0:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        state[name] = 2
        return ()

    for name in sorted(by_id):
        if state.get(name, 0) == 0:
            cycle = visit(name)
            if cycle:
                return cycle
    return ()


def validate_gate_graph(gates: Iterable[GateSpec]) -> tuple[str, ...]:
    """Collect every graph error deterministically; an empty tuple means valid."""
    if isinstance(gates, (str, bytes)) or not isinstance(gates, Iterable):
        return ("gates must be an iterable of GateSpec",)
    specs = tuple(gates)
    if any(not isinstance(spec, GateSpec) for spec in specs):
        return ("gate graph entries must be GateSpec instances",)
    errors: list[str] = []
    seen: set[str] = set()
    known = {spec.gate_id for spec in specs}
    for spec in specs:
        if not spec.gate_id or not _IDENTIFIER_RE.match(spec.gate_id):
            errors.append("gate id is not a safe identifier")
        if spec.gate_id in seen:
            errors.append("duplicate gate id: %s" % spec.gate_id)
        seen.add(spec.gate_id)
        if not spec.lane or not _IDENTIFIER_RE.match(spec.lane):
            errors.append("gate %s has an unsafe lane" % spec.gate_id)
        for dep in spec.depends_on:
            if not dep or not _IDENTIFIER_RE.match(dep):
                errors.append("gate %s has an unsafe dependency id" % spec.gate_id)
            elif dep not in known:
                errors.append("gate %s depends on unknown gate %s" % (spec.gate_id, dep))
            elif dep == spec.gate_id:
                errors.append("gate %s depends on itself" % spec.gate_id)
    cycle = find_cycle(specs)
    if cycle:
        errors.append("dependency cycle detected: %s" % " -> ".join(cycle))
    return tuple(sorted(set(errors)))


@dataclass(frozen=True)
class GateGraph:
    """An immutable, sorted set of validated gates."""

    gates: tuple[GateSpec, ...]

    def as_dict(self) -> dict:
        return {"gates": [gate.as_dict() for gate in self.gates]}


def build_gate_graph(gates: Iterable[GateSpec]) -> GateGraph:
    """Build and validate a graph; any error fails closed."""
    errors = validate_gate_graph(gates)
    if errors:
        raise ContractValidationError(errors)
    return GateGraph(gates=tuple(sorted(gates, key=lambda spec: spec.gate_id)))


def topological_levels(graph: GateGraph) -> tuple[tuple[str, ...], ...]:
    """Deterministic Kahn levels; gates in one level have no inter-dependency."""
    if not isinstance(graph, GateGraph):
        raise ContractValidationError("topological_levels needs a GateGraph")
    done: set[str] = set()
    remaining = {spec.gate_id for spec in graph.gates}
    deps = {spec.gate_id: spec.depends_on for spec in graph.gates}
    levels: list[tuple[str, ...]] = []
    while remaining:
        ready = tuple(sorted(
            name for name in remaining if all(dep in done for dep in deps[name])))
        if not ready:
            raise ContractValidationError("gate graph contains a dependency cycle")
        levels.append(ready)
        done.update(ready)
        remaining.difference_update(ready)
    return tuple(levels)


def transitive_dependents(graph: GateGraph, gate_id: Any) -> frozenset[str]:
    """Every gate that directly or transitively depends on ``gate_id``."""
    if not isinstance(graph, GateGraph):
        raise ContractValidationError("transitive_dependents needs a GateGraph")
    name = _text(gate_id)
    reverse: dict[str, list[str]] = {}
    for spec in graph.gates:
        for dep in spec.depends_on:
            reverse.setdefault(dep, []).append(spec.gate_id)
    found: set[str] = set()
    pending = list(reverse.get(name, ()))
    while pending:
        current = pending.pop()
        if current in found or current == name:
            continue
        found.add(current)
        pending.extend(reverse.get(current, ()))
    return frozenset(found)


# ---------------------------------------------------------------------------
# D7.1 -- bounded concurrency policy (caller supplies the environment mapping)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchedulerPolicy:
    """Bounded concurrency plus the fail-fast switch."""

    concurrency: int
    fail_fast: bool

    def as_dict(self) -> dict:
        return {"concurrency": self.concurrency, "fail_fast": self.fail_fast}


def _validate_policy(policy: Any) -> None:
    if not isinstance(policy, SchedulerPolicy):
        raise ContractValidationError("scheduler policy must be a SchedulerPolicy")
    if type(policy.concurrency) is not int:
        raise ContractValidationError("gate concurrency must be an integer")
    if not 1 <= policy.concurrency <= MAX_CONCURRENCY:
        raise ContractValidationError(
            "gate concurrency must be between 1 and %d" % MAX_CONCURRENCY)
    if type(policy.fail_fast) is not bool:
        raise ContractValidationError("fail-fast switch must be a boolean")


def parse_scheduler_env(env: Mapping[str, Any] | None) -> SchedulerPolicy:
    """Parse the two gate env vars from a caller-provided mapping, fail closed.

    Unknown ``KEEL_GATE_*`` keys are rejected rather than ignored: a typo must
    not silently leave the gates running with an unintended policy.  No host
    environment is read here.
    """
    if env is None:
        env = {}
    if not isinstance(env, Mapping):
        raise ContractValidationError("gate environment must be a mapping")
    for key in env:
        if _text(key).startswith("KEEL_GATE_") and key not in _GATE_ENV_KEYS:
            raise ContractValidationError("unknown gate environment key: %s" % key)

    concurrency: Any = DEFAULT_CONCURRENCY
    if CONCURRENCY_ENV in env:
        raw = env[CONCURRENCY_ENV]
        if type(raw) is int:
            concurrency = raw
        elif isinstance(raw, str) and re.fullmatch(r"[1-9][0-9]*", raw):
            concurrency = int(raw)
        else:
            raise ContractValidationError(
                "%s must be a positive decimal integer" % CONCURRENCY_ENV)
        if not 1 <= concurrency <= MAX_CONCURRENCY:
            raise ContractValidationError(
                "%s must be between 1 and %d" % (CONCURRENCY_ENV, MAX_CONCURRENCY))

    fail_fast = False
    if FAIL_FAST_ENV in env:
        raw = env[FAIL_FAST_ENV]
        if type(raw) is bool:
            fail_fast = raw
        elif isinstance(raw, str):
            flag = raw.strip().lower()
            if flag in ("1", "true", "yes", "on"):
                fail_fast = True
            elif flag in ("0", "false", "no", "off"):
                fail_fast = False
            else:
                raise ContractValidationError(
                    "%s must be a boolean flag" % FAIL_FAST_ENV)
        else:
            raise ContractValidationError(
                "%s must be a boolean flag" % FAIL_FAST_ENV)

    return SchedulerPolicy(concurrency=concurrency, fail_fast=fail_fast)


@dataclass(frozen=True)
class GateResult:
    """The pure disposition of one gate in a simulation."""

    gate_id: str
    status: str
    reason: str = ""

    def as_dict(self) -> dict:
        return {"gate_id": self.gate_id, "status": self.status,
                "reason": self.reason}


@dataclass(frozen=True)
class GateRun:
    """A deterministic trace: ordered results plus the gates started per round."""

    results: tuple[GateResult, ...]
    rounds: tuple[tuple[str, ...], ...]
    policy: SchedulerPolicy

    def status_of(self, gate_id: Any) -> str:
        for result in self.results:
            if result.gate_id == _text(gate_id):
                return result.status
        return ""

    def ids_with_status(self, status: Any) -> tuple[str, ...]:
        wanted = _text(status)
        return tuple(result.gate_id for result in self.results
                     if result.status == wanted)

    def max_in_flight(self) -> int:
        return max((len(round_ids) for round_ids in self.rounds), default=0)

    def as_dict(self) -> dict:
        return {
            "results": [result.as_dict() for result in self.results],
            "rounds": [list(round_ids) for round_ids in self.rounds],
            "policy": self.policy.as_dict(),
        }


def simulate_gates(graph: GateGraph, outcomes: Mapping[str, bool],
                   policy: SchedulerPolicy) -> GateRun:
    """Simulate the gates under a bounded policy using caller-supplied outcomes.

    ``outcomes`` maps a gate id to ``True`` (pass) or ``False`` (fail).  It is
    validated strictly: unknown keys, missing outcomes for gates that need to
    run, and non-boolean values all fail closed.  A failed gate marks only its
    transitive dependents ``skipped``; all other independent gates still run so
    independent errors are all reported.  With fail-fast on, gates that had
    not started are ``cancelled`` once a failure is observed, while gates
    started in the same round always keep their result.

    This function is a pure scheduler simulation: it never launches a process.
    """
    if not isinstance(graph, GateGraph):
        raise ContractValidationError("simulate_gates needs a GateGraph")
    _validate_policy(policy)
    if not isinstance(outcomes, Mapping):
        raise ContractValidationError("gate outcomes must be a mapping")
    known = {spec.gate_id for spec in graph.gates}
    for key in outcomes:
        if key not in known:
            raise ContractValidationError("unknown gate in outcomes: %s" % key)
    for key, value in outcomes.items():
        if type(value) is not bool:
            raise ContractValidationError(
                "outcome for %s must be a boolean" % key)

    ids = sorted(known)
    deps = {spec.gate_id: spec.depends_on for spec in graph.gates}
    results: dict[str, GateResult] = {}
    failed: set[str] = set()
    skipped: set[str] = set()
    cancelled: set[str] = set()
    rounds: list[tuple[str, ...]] = []

    def propagate() -> None:
        """Resolve non-runnable gates until the state stops changing."""
        changed = True
        while changed:
            changed = False
            for name in ids:
                if name in results or name in skipped or name in cancelled:
                    continue
                prerequisites = deps[name]
                if any(dep in failed or dep in skipped for dep in prerequisites):
                    skipped.add(name)
                    changed = True
                elif any(dep in cancelled for dep in prerequisites):
                    cancelled.add(name)
                    changed = True

    while True:
        propagate()
        ready = [
            name for name in ids
            if name not in results and name not in skipped and name not in cancelled
            and all(dep in results and results[dep].status == STATUS_PASSED
                    for dep in deps[name])
        ]
        if not ready:
            break
        chosen = tuple(ready[:policy.concurrency])
        rounds.append(chosen)
        saw_failure = False
        for name in chosen:
            if name not in outcomes:
                raise ContractValidationError(
                    "missing gate outcome for %s" % name)
            passed = outcomes[name]
            status = STATUS_PASSED if passed else STATUS_FAILED
            results[name] = GateResult(gate_id=name, status=status)
            if not passed:
                failed.add(name)
                saw_failure = True
        propagate()
        if policy.fail_fast and saw_failure:
            for name in ids:
                if name not in results and name not in skipped:
                    cancelled.add(name)
            propagate()
            break

    unresolved = [name for name in ids
                  if name not in results and name not in skipped
                  and name not in cancelled]
    if unresolved:
        raise ContractValidationError(
            "gate graph could not be resolved: %s" % ", ".join(unresolved))

    # Skipped and cancelled gates are first-class results: a caller must see
    # why they did not run, not merely notice their absence.
    for name in sorted(skipped):
        results[name] = GateResult(gate_id=name, status=STATUS_SKIPPED,
                                   reason="dependency failed")
    for name in sorted(cancelled):
        results[name] = GateResult(gate_id=name, status=STATUS_CANCELLED,
                                   reason="fail-fast: cancelled before start")

    return GateRun(
        results=tuple(results[name] for name in sorted(results)),
        rounds=tuple(rounds),
        policy=policy,
    )


# ---------------------------------------------------------------------------
# D7.9 -- strict dependency linker
# ---------------------------------------------------------------------------

PYTHON = "python"
NODE = "node"
_ECOSYSTEMS = frozenset({PYTHON, NODE})


@dataclass(frozen=True)
class LockEntry:
    """One hash-pinned dependency with its declared build scripts."""

    package: str
    version: str
    digest: str
    scripts: tuple[str, ...] = ()
    ecosystem: str = PYTHON

    def as_dict(self) -> dict:
        return {
            "package": self.package,
            "version": self.version,
            "digest": self.digest,
            "scripts": list(self.scripts),
            "ecosystem": self.ecosystem,
        }

    @property
    def pin(self) -> str:
        separator = "==" if self.ecosystem == PYTHON else "@"
        return "%s%s%s" % (self.package, separator, self.version)


def _validate_lock_entry(entry: Any) -> tuple[str, ...]:
    if not isinstance(entry, LockEntry):
        return ("lockfile entries must be LockEntry instances",)
    errors: list[str] = []
    if not _PACKAGE_RE.match(entry.package):
        errors.append("unsafe dependency package name: %s" % entry.package)
    if not _VERSION_RE.match(entry.version):
        errors.append("dependency version must be pinned: %s" % entry.package)
    if not _DIGEST_RE.match(entry.digest):
        errors.append("dependency hash must be a lowercase sha256/sha512: %s"
                      % entry.package)
    if entry.ecosystem not in _ECOSYSTEMS:
        errors.append("unknown dependency ecosystem: %s" % entry.ecosystem)
    for script in entry.scripts:
        if not script or not _IDENTIFIER_RE.match(script):
            errors.append("unsafe build script name: %s" % script)
        if len(script.split(":")) != 1:
            errors.append("build script must be a plain name: %s" % script)
    if entry.ecosystem == PYTHON and entry.scripts:
        errors.append("python dependencies must be hash-pinned wheels without "
                      "build scripts: %s" % entry.package)
    return tuple(sorted(set(errors)))


def make_lock_entry(package: Any, version: Any, digest: Any,
                    scripts: Iterable[Any] = (),
                    ecosystem: Any = PYTHON) -> LockEntry:
    """Build a validated, fully pinned lockfile entry."""
    entry = LockEntry(
        package=_text(package).strip(),
        version=_text(version).strip(),
        digest=_text(digest).strip(),
        scripts=_values(scripts, "build scripts"),
        ecosystem=_text(ecosystem).strip().lower(),
    )
    errors = _validate_lock_entry(entry)
    if errors:
        raise ContractValidationError(errors)
    return entry


def is_script_allowed(package: Any, script: Any, allowlist: Iterable[Any]) -> bool:
    """True only for an exact ``package:script`` allowlist entry (no wildcards)."""
    wanted = "%s:%s" % (_text(package).strip(), _text(script).strip())
    try:
        entries = _values(allowlist, "build-script allowlist")
    except ContractValidationError:
        return False
    for entry in entries:
        parts = entry.strip().split(":")
        if len(parts) != 2:
            return False
        name, action = parts
        if not _PACKAGE_RE.match(name) or not _IDENTIFIER_RE.match(action):
            return False
        if wanted == "%s:%s" % (name, action):
            return True
    return False


@dataclass(frozen=True)
class DependencyManifest:
    """What is actually used, what is locked, and the approved build scripts."""

    required: tuple[str, ...]
    locked: tuple[LockEntry, ...]
    allowed_scripts: tuple[str, ...] = ()
    strict_scripts: bool = True

    def as_dict(self) -> dict:
        return {
            "required": list(self.required),
            "locked": [entry.as_dict() for entry in self.locked],
            "allowed_scripts": list(self.allowed_scripts),
            "strict_scripts": self.strict_scripts,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DependencyManifest":
        data = data if isinstance(data, Mapping) else {}
        entries: list[LockEntry] = []
        for raw in data.get("locked", ()):
            if not isinstance(raw, Mapping):
                raise ContractValidationError("serialized lock entry must be a mapping")
            # Unknown fields are dropped: a payload cannot smuggle a value into
            # a descriptor through extra keys.
            entries.append(make_lock_entry(
                raw.get("package"), raw.get("version"), raw.get("digest"),
                scripts=raw.get("scripts", ()),
                ecosystem=raw.get("ecosystem", PYTHON),
            ))
        return make_manifest(
            data.get("required", ()),
            entries,
            allowed_scripts=data.get("allowed_scripts", ()),
            strict_scripts=data.get("strict_scripts", True),
        )


def make_manifest(required: Iterable[Any], locked: Iterable[LockEntry],
                  allowed_scripts: Iterable[Any] = (),
                  strict_scripts: Any = True) -> DependencyManifest:
    """Build a manifest, validating local fields but not cross-entry policy."""
    needs = tuple(name.strip() for name in _values(required, "required packages"))
    for name in needs:
        if not _PACKAGE_RE.match(name):
            raise ContractValidationError("unsafe required package name: %s" % name)
    if len(set(needs)) != len(needs):
        raise ContractValidationError("duplicate required package")
    if isinstance(locked, (str, bytes)) or not isinstance(locked, Iterable):
        raise ContractValidationError("locked packages must be an iterable")
    entries = tuple(locked)
    if any(not isinstance(entry, LockEntry) for entry in entries):
        raise ContractValidationError("locked packages must be LockEntry instances")
    allowed = tuple(value.strip() for value in
                    _values(allowed_scripts, "build-script allowlist"))
    for value in allowed:
        if not _is_script_allowlist_entry(value):
            raise ContractValidationError("invalid build-script allowlist entry: %s"
                                          % value)
    if type(strict_scripts) is not bool:
        raise ContractValidationError("strict_scripts must be a boolean")
    return DependencyManifest(required=tuple(sorted(needs)), locked=entries,
                              allowed_scripts=tuple(sorted(allowed)),
                              strict_scripts=strict_scripts)


def _is_script_allowlist_entry(value: Any) -> bool:
    parts = _text(value).split(":")
    return (len(parts) == 2 and bool(_PACKAGE_RE.match(parts[0]))
            and bool(_IDENTIFIER_RE.match(parts[1])))


def undeclared_dependencies(manifest: DependencyManifest) -> tuple[str, ...]:
    """Required packages with no lockfile entry, sorted."""
    if not isinstance(manifest, DependencyManifest):
        raise ContractValidationError("manifest must be a DependencyManifest")
    locked = {entry.package for entry in manifest.locked}
    return tuple(sorted(set(manifest.required) - locked))


def validate_manifest(manifest: DependencyManifest) -> tuple[str, ...]:
    """Collect every linker error deterministically; empty tuple means linker OK."""
    if not isinstance(manifest, DependencyManifest):
        return ("manifest must be a DependencyManifest",)
    errors: list[str] = []
    for name in manifest.required:
        if not _PACKAGE_RE.match(name):
            errors.append("unsafe required package name: %s" % name)
    if len(set(manifest.required)) != len(manifest.required):
        errors.append("duplicate required package")
    locked_names = [entry.package for entry in manifest.locked
                    if isinstance(entry, LockEntry)]
    if len(locked_names) != len(set(locked_names)):
        errors.append("duplicate lockfile pin")
    for entry in manifest.locked:
        errors.extend(_validate_lock_entry(entry))
        if not isinstance(entry, LockEntry):
            continue
        for script in entry.scripts:
            if not is_script_allowed(entry.package, script,
                                     manifest.allowed_scripts):
                errors.append("build script not allowlisted: %s:%s"
                              % (entry.package, script))
    for name in undeclared_dependencies(manifest):
        errors.append("undeclared dependency: %s" % name)
    for value in manifest.allowed_scripts:
        if not _is_script_allowlist_entry(value):
            errors.append("invalid build-script allowlist entry: %s" % value)
    return tuple(sorted(set(errors)))


@dataclass(frozen=True)
class LinkReport:
    """The pure result of a successful strict link."""

    linked: tuple[str, ...]
    package_count: int
    script_count: int

    def as_dict(self) -> dict:
        return {"linked": list(self.linked), "package_count": self.package_count,
                "script_count": self.script_count}


def link_dependencies(manifest: DependencyManifest) -> LinkReport:
    """Fail closed unless every required dep is pinned, hashed and script-safe."""
    errors = validate_manifest(manifest)
    if errors:
        raise ContractValidationError(errors)
    entries = sorted(manifest.locked, key=lambda entry: entry.package)
    return LinkReport(
        linked=tuple(entry.pin for entry in entries),
        package_count=len(entries),
        script_count=sum(len(entry.scripts) for entry in entries),
    )


def lockfile_digest(manifest: DependencyManifest) -> str:
    """sha256 over a canonical, order-independent view of the whole lockfile."""
    errors = validate_manifest(manifest)
    if errors:
        raise ContractValidationError(errors)
    return _canonical_digest({
        "required": sorted(manifest.required),
        "locked": [entry.as_dict() for entry in sorted(
            manifest.locked, key=lambda entry: entry.package)],
        "allowed_scripts": sorted(manifest.allowed_scripts),
        "strict_scripts": manifest.strict_scripts,
    })


# ---------------------------------------------------------------------------
# D7.12 -- CI lane layout
# ---------------------------------------------------------------------------

LANE_GATES = "gates"
LANE_MATRIX = "matrix"
LANE_WINDOWS = "windows"
LANE_MACOS = "macos"
LANE_BENCHMARKS = "benchmarks"
LANE_PROVIDER_E2E = "provider-e2e"
PYTHON_VERSIONS = ("3.11", "3.12", "3.13")
PLATFORMS = ("linux", "windows", "macos")


class LaneKind(str, Enum):
    """The six non-overlapping CI lane kinds."""

    GATES = LANE_GATES
    MATRIX = LANE_MATRIX
    WINDOWS = LANE_WINDOWS
    MACOS = LANE_MACOS
    BENCHMARKS = LANE_BENCHMARKS
    PROVIDER_E2E = LANE_PROVIDER_E2E

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CILane:
    """A declarative lane descriptor; no workflow file is created here."""

    lane_id: str
    kind: LaneKind
    workflow: str
    runs_on: str
    matrix: tuple[str, ...] = ()
    opt_in: bool = False
    skip_without_key: bool = False
    key_ref: str | None = None
    owned_gates: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "lane_id": self.lane_id,
            "kind": self.kind.value,
            "workflow": self.workflow,
            "runs_on": self.runs_on,
            "matrix": list(self.matrix),
            "opt_in": self.opt_in,
            "skip_without_key": self.skip_without_key,
            "key_ref": self.key_ref,
            "owned_gates": list(self.owned_gates),
        }


def _lane_kind(value: Any) -> LaneKind:
    if isinstance(value, LaneKind):
        return value
    try:
        return LaneKind(_text(value).strip().lower())
    except ValueError:
        raise ContractValidationError("unknown CI lane kind: %s" % value) from None


def make_ci_lane(lane_id: Any, kind: Any, workflow: Any, runs_on: Any,
                 matrix: Iterable[Any] = (), opt_in: Any = False,
                 skip_without_key: Any = False, key_ref: Any = None,
                 owned_gates: Iterable[Any] = ()) -> CILane:
    """Build a lane descriptor with all local fields validated."""
    versions = tuple(_text(value).strip() for value in
                     _values(matrix, "lane matrix"))
    for version in versions:
        if not _PYTHON_VERSION_RE.match(version):
            raise ContractValidationError("invalid matrix version: %s" % version)
    gates = tuple(_text(value).strip() for value in
                  _values(owned_gates, "owned gates"))
    for gate in gates:
        if not _IDENTIFIER_RE.match(gate):
            raise ContractValidationError("invalid owned gate id: %s" % gate)
    for flag in (opt_in, skip_without_key):
        if type(flag) is not bool:
            raise ContractValidationError("lane switches must be booleans")
    if key_ref is not None and not isinstance(key_ref, str):
        raise ContractValidationError("key_ref must be a reference string or None")
    return CILane(
        lane_id=_named(lane_id, "lane id"),
        kind=_lane_kind(kind),
        workflow=_text(workflow).strip(),
        runs_on=_text(runs_on).strip(),
        matrix=versions,
        opt_in=opt_in,
        skip_without_key=skip_without_key,
        key_ref=key_ref,
        owned_gates=gates,
    )


CI_LANES: tuple[CILane, ...] = (
    make_ci_lane(LANE_GATES, LaneKind.GATES, "python-tests.yml",
                 "ubuntu-latest"),
    make_ci_lane(LANE_MATRIX, LaneKind.MATRIX, "python-tests.yml",
                 "ubuntu-latest", matrix=PYTHON_VERSIONS),
    make_ci_lane(LANE_WINDOWS, LaneKind.WINDOWS, "windows-gates.yml",
                 "windows-latest"),
    make_ci_lane(LANE_MACOS, LaneKind.MACOS, "macos-gates.yml",
                 "macos-latest"),
    make_ci_lane(LANE_BENCHMARKS, LaneKind.BENCHMARKS, "benchmarks.yml",
                 "ubuntu-latest"),
    make_ci_lane(LANE_PROVIDER_E2E, LaneKind.PROVIDER_E2E,
                 "provider-e2e.yml", "ubuntu-latest",
                 opt_in=True, skip_without_key=True,
                 key_ref="env:KEEL_E2E_API_KEY"),
)


def validate_ci_layout(lanes: Iterable[CILane]) -> tuple[str, ...]:
    """Validate the whole lane layout; every deviation is reported, fail closed."""
    if isinstance(lanes, (str, bytes)) or not isinstance(lanes, Iterable):
        return ("lanes must be an iterable of CILane",)
    items = tuple(lanes)
    if any(not isinstance(lane, CILane) for lane in items):
        return ("lane layout entries must be CILane instances",)
    errors: list[str] = []
    kinds = [lane.kind for lane in items]
    lane_ids = [lane.lane_id for lane in items]
    for kind in LaneKind:
        if kinds.count(kind) != 1:
            errors.append("CI layout needs exactly one %s lane" % kind.value)
    if len(set(lane_ids)) != len(lane_ids):
        errors.append("duplicate CI lane id")

    gates_workflow = next((lane.workflow for lane in items
                           if lane.kind is LaneKind.GATES), "")
    by_kind = {lane.kind: lane for lane in items}
    special = (LaneKind.WINDOWS, LaneKind.MACOS, LaneKind.BENCHMARKS,
               LaneKind.PROVIDER_E2E)
    workflows = [by_kind[kind].workflow for kind in special if kind in by_kind]
    if len(set(workflows)) != len(workflows):
        errors.append("platform-specific lanes need distinct workflows")
    for lane in items:
        if not _WORKFLOW_RE.match(lane.workflow):
            errors.append("lane %s has an invalid workflow name" % lane.lane_id)
        if not lane.runs_on:
            errors.append("lane %s has no runner" % lane.lane_id)
        if lane.kind in special and lane.workflow == gates_workflow:
            errors.append("lane %s must use a separate workflow" % lane.lane_id)
        if lane.kind is LaneKind.WINDOWS and not lane.runs_on.startswith("windows-"):
            errors.append("Windows lane must use a native Windows runner")
        if lane.kind is LaneKind.MACOS and not lane.runs_on.startswith("macos-"):
            errors.append("macOS lane must use a native macOS runner")
        if lane.kind is LaneKind.GATES and (lane.opt_in or lane.skip_without_key):
            errors.append("the gates lane is always required")
        if lane.kind is LaneKind.MATRIX:
            if tuple(lane.matrix) != PYTHON_VERSIONS or len(lane.matrix) > 3:
                errors.append("matrix lane must use exactly the pinned Python versions")
            if lane.opt_in:
                errors.append("the Python matrix lane is always required")
        if lane.kind is LaneKind.BENCHMARKS:
            if lane.runs_on != "ubuntu-latest" or lane.opt_in:
                errors.append("benchmarks are required on standard hosted Linux")
        if lane.kind is LaneKind.PROVIDER_E2E:
            if not lane.opt_in or not lane.skip_without_key:
                errors.append("provider e2e must be opt-in and self-skip")
            if not _is_secret_reference(lane.key_ref):
                errors.append("provider e2e key must be a secret reference, not a value")
    return tuple(sorted(set(errors)))


def lane_enabled(lane: CILane, context: Mapping[str, Any] | None = None) -> bool:
    """Decide whether a lane runs; opt-in and key presence must both be proven."""
    if not isinstance(lane, CILane):
        return False
    if context is None:
        context = {}
    if not isinstance(context, Mapping):
        return False
    if lane.opt_in and context.get("opt_in") is not True:
        return False
    if lane.skip_without_key and context.get("api_key_present") is not True:
        return False
    return True


def ci_layout_dict(lanes: Iterable[CILane] = CI_LANES) -> dict:
    """Serializable layout descriptor; invalid layouts are rejected."""
    errors = validate_ci_layout(lanes)
    if errors:
        raise ContractValidationError(errors)
    return {
        "lanes": [lane.as_dict() for lane in sorted(lanes, key=lambda l: l.lane_id)],
        "platforms": list(PLATFORMS),
        "python_versions": list(PYTHON_VERSIONS),
    }


@dataclass(frozen=True)
class CoveragePlan:
    """Deterministic, timing-balanced coverage shards for one platform."""

    platform: str
    partitions: tuple[tuple[str, ...], ...]
    seconds: tuple[float, ...]


def partition_coverage(platform: Any, timings: Mapping[str, Any],
                       partitions: Any = 2) -> CoveragePlan:
    """Partition coverage shards by measured duration (largest-first)."""
    name = _text(platform).strip()
    if name not in PLATFORMS:
        raise ContractValidationError("unknown coverage platform: %s" % name)
    if type(partitions) is not int or not 1 <= partitions <= 16:
        raise ContractValidationError("coverage partitions must be 1..16")
    if not isinstance(timings, Mapping) or not timings:
        raise ContractValidationError("coverage timings must be a non-empty mapping")
    measured: list[tuple[str, float]] = []
    for shard, seconds in timings.items():
        key = _text(shard)
        if not key or not _IDENTIFIER_RE.match(key):
            raise ContractValidationError("unsafe coverage shard id: %s" % key)
        if type(seconds) not in (int, float) or not math.isfinite(seconds) \
                or seconds <= 0:
            raise ContractValidationError(
                "coverage timing for %s must be a positive finite number" % key)
        measured.append((key, float(seconds)))

    bins: list[list[str]] = [[] for _ in range(partitions)]
    loads = [0.0] * partitions
    for shard, seconds in sorted(measured, key=lambda item: (-item[1], item[0])):
        index = min(range(partitions), key=lambda i: (loads[i], i))
        bins[index].append(shard)
        loads[index] += seconds
    return CoveragePlan(
        platform=name,
        partitions=tuple(tuple(bucket) for bucket in bins),
        seconds=tuple(loads),
    )


# ---------------------------------------------------------------------------
# D7.19 -- benchmark method descriptor
# ---------------------------------------------------------------------------

SDK_MINIMAL_PROFILE = "sdk-minimal"
JSONRPC_TRANSPORT = "json-rpc"
WORKSPACE_ROOT = "workspaces"


@dataclass(frozen=True)
class BenchmarkTask:
    """One independent benchmark task with its own workspace and session."""

    task_id: str
    workspace: str
    session_id: str

    def as_dict(self) -> dict:
        return {"task_id": self.task_id, "workspace": self.workspace,
                "session_id": self.session_id}


def _is_task_workspace(workspace: Any, task_id: Any) -> bool:
    text = _text(workspace)
    if not text or _ENCODED_TRAVERSAL_RE.search(text):
        return False
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        return False
    if text.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", text):
        return False
    segments = [part for part in text.replace("\\", "/").split("/")
                if part not in ("", ".")]
    if ".." in segments:
        return False
    return segments == [WORKSPACE_ROOT, _text(task_id)]


def _validate_task(task: Any) -> tuple[str, ...]:
    if not isinstance(task, BenchmarkTask):
        return ("benchmark tasks must be BenchmarkTask instances",)
    errors: list[str] = []
    if not _IDENTIFIER_RE.match(task.task_id):
        errors.append("benchmark task id is not a safe identifier")
    if not _IDENTIFIER_RE.match(task.session_id):
        errors.append("benchmark session id is not a safe identifier")
    if not _is_task_workspace(task.workspace, task.task_id):
        errors.append("benchmark workspace must be %s/<task_id>" % WORKSPACE_ROOT)
    return tuple(errors)


def make_benchmark_task(task_id: Any, workspace: Any,
                        session_id: Any) -> BenchmarkTask:
    """Build and validate one isolated benchmark task."""
    task = BenchmarkTask(task_id=_text(task_id).strip(),
                         workspace=_text(workspace).strip(),
                         session_id=_text(session_id).strip())
    errors = _validate_task(task)
    if errors:
        raise ContractValidationError(errors)
    return task


@dataclass(frozen=True)
class BenchmarkMethod:
    """The pinned SDK profile and the isolated task set."""

    method_id: str
    profile: str
    transport: str
    tasks: tuple[BenchmarkTask, ...]

    def as_dict(self) -> dict:
        return {
            "method_id": self.method_id,
            "profile": self.profile,
            "transport": self.transport,
            "tasks": [task.as_dict() for task in self.tasks],
        }


@dataclass(frozen=True)
class TaskInvocation:
    """A pure dispatch record; the caller transports it through its SDK."""

    task_id: str
    profile: str
    transport: str
    workspace: str
    session_id: str

    def as_dict(self) -> dict:
        return {
            "task_id": self.task_id, "profile": self.profile,
            "transport": self.transport, "workspace": self.workspace,
            "session_id": self.session_id,
        }


def validate_benchmark_method(method: Any) -> tuple[str, ...]:
    """Validate the profile, transport and per-task isolation, fail closed."""
    if not isinstance(method, BenchmarkMethod):
        return ("benchmark method must be a BenchmarkMethod",)
    errors: list[str] = []
    if not _IDENTIFIER_RE.match(method.method_id):
        errors.append("benchmark method id is not a safe identifier")
    if method.profile != SDK_MINIMAL_PROFILE:
        errors.append("benchmark profile must be %s" % SDK_MINIMAL_PROFILE)
    if method.transport != JSONRPC_TRANSPORT:
        errors.append("benchmark transport must be %s" % JSONRPC_TRANSPORT)
    if not method.tasks:
        errors.append("benchmark method needs at least one task")
    for task in method.tasks:
        errors.extend(_validate_task(task))
    task_ids = [task.task_id for task in method.tasks
                if isinstance(task, BenchmarkTask)]
    workspaces = [task.workspace for task in method.tasks
                  if isinstance(task, BenchmarkTask)]
    sessions = [task.session_id for task in method.tasks
                if isinstance(task, BenchmarkTask)]
    if len(set(task_ids)) != len(task_ids):
        errors.append("benchmark task ids must be unique")
    if len(set(workspaces)) != len(workspaces):
        errors.append("benchmark workspaces must be isolated per task")
    if len(set(sessions)) != len(sessions):
        errors.append("benchmark session ids must be unique per task")
    for index, workspace in enumerate(workspaces):
        for other in workspaces[index + 1:]:
            if workspace.startswith(other + "/") or other.startswith(workspace + "/"):
                errors.append("benchmark workspaces must not be nested")
    return tuple(sorted(set(errors)))


def make_benchmark_method(method_id: Any, tasks: Iterable[BenchmarkTask],
                          profile: Any = SDK_MINIMAL_PROFILE,
                          transport: Any = JSONRPC_TRANSPORT) -> BenchmarkMethod:
    """Build a method, rejecting any profile or isolation deviation."""
    if isinstance(tasks, (str, bytes)) or not isinstance(tasks, Iterable):
        raise ContractValidationError("benchmark tasks must be an iterable")
    method = BenchmarkMethod(
        method_id=_text(method_id).strip(),
        profile=_text(profile),
        transport=_text(transport),
        tasks=tuple(tasks),
    )
    errors = validate_benchmark_method(method)
    if errors:
        raise ContractValidationError(errors)
    return method


def benchmark_dispatch(method: BenchmarkMethod) -> tuple[TaskInvocation, ...]:
    """Pure dispatch plan: one SDK-minimal JSON-RPC call per isolated task."""
    errors = validate_benchmark_method(method)
    if errors:
        raise ContractValidationError(errors)
    return tuple(TaskInvocation(
        task_id=task.task_id,
        profile=method.profile,
        transport=method.transport,
        workspace=task.workspace,
        session_id=task.session_id,
    ) for task in sorted(method.tasks, key=lambda task: task.task_id))


def method_digest(method: BenchmarkMethod) -> str:
    """sha256 over a canonical method description (isolation is part of it)."""
    errors = validate_benchmark_method(method)
    if errors:
        raise ContractValidationError(errors)
    return _canonical_digest({
        "method_id": method.method_id,
        "profile": method.profile,
        "transport": method.transport,
        "tasks": [task.as_dict() for task in sorted(
            method.tasks, key=lambda task: task.task_id)],
    })


def is_isolated(method: Any) -> bool:
    """True only for a fully valid, isolated benchmark method."""
    return not validate_benchmark_method(method)


__all__ = [
    "FEATURE_IDS",
    "CONCURRENCY_ENV", "FAIL_FAST_ENV", "DEFAULT_CONCURRENCY", "MAX_CONCURRENCY",
    "STATUS_CANCELLED", "STATUS_FAILED", "STATUS_PASSED", "STATUS_SKIPPED",
    "LANE_BENCHMARKS", "LANE_GATES", "LANE_MATRIX", "LANE_MACOS",
    "LANE_PROVIDER_E2E", "LANE_WINDOWS", "PLATFORMS", "PYTHON_VERSIONS",
    "SDK_MINIMAL_PROFILE", "JSONRPC_TRANSPORT", "WORKSPACE_ROOT", "CI_LANES",
    "NODE", "PYTHON",
    "BenchmarkMethod", "BenchmarkTask", "CILane", "ContractError",
    "ContractValidationError", "CoveragePlan", "DependencyManifest", "GateGraph",
    "GateResult", "GateRun", "GateSpec", "LaneKind", "LinkReport", "LockEntry",
    "SchedulerPolicy", "TaskInvocation",
    "benchmark_dispatch", "build_gate_graph", "ci_layout_dict", "find_cycle",
    "is_isolated", "is_script_allowed", "lane_enabled", "link_dependencies",
    "lockfile_digest", "make_benchmark_method", "make_benchmark_task",
    "make_ci_lane", "make_gate", "make_lock_entry", "make_manifest",
    "method_digest", "parse_scheduler_env", "partition_coverage",
    "simulate_gates", "topological_levels", "transitive_dependents",
    "undeclared_dependencies", "validate_benchmark_method", "validate_ci_layout",
    "validate_gate_graph", "validate_manifest",
]
