"""Pure dev-workflow backend contracts for the remaining D7 registry rows.

This module is the stdlib-only, host-independent backend surface for the 16
``not_started`` P1/P2 rows of D7 in ``PLAN-INDEX.json``.  The four P0 rows
(``D7.1``, ``D7.9``, ``D7.12``, ``D7.19``) were implemented earlier in
``keel.gate_scheduler`` and are listed in ``P0_FEATURE_IDS`` for traceability
only; this module never duplicates or replaces them.

Like ``gate_scheduler``, this is a *contract and planning* layer.  It holds no
host state: no process, file read, environment read, network, clock or random
input.  Callers own every value; functions here validate, resolve, render,
compare and plan deterministically.  ``as_dict`` methods produce plain data so
a caller may persist it through its own storage layer.  This is real behavior
(cgroup text is parsed, TS client types are rendered, code fences are compiled,
labels are checked, versions are compared, digests are computed), not a stub,
but it does not itself start a CI job, install a git hook, sign a binary or
publish a package.

Feature map
-----------
D7.2 worker budgets, D7.3 face-separated type checks, D7.4 contract generation,
D7.5 build order and separate check stage, D7.6 build identity and record,
D7.7 local/official profiles, D7.8 Windows/WSL guidance, D7.10 git hooks,
D7.11 doc gates, D7.13 coverage gate, D7.14 test taxonomy, D7.15 release
rehearsals, D7.16 package hygiene, D7.17 signing docs/profiles, D7.18
breaking-change notices, D7.20 label taxonomy and stacked PRs.

Invariants (enforced by ``test_d7_workflow_backend``):

* every unknown, malformed or ambiguous value fails closed;
* every result, digest, render and plan is deterministic and order independent;
* no function reads the host environment, filesystem, clock or random source.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

FEATURE_IDS = (
    "D7.2", "D7.3", "D7.4", "D7.5", "D7.6", "D7.7", "D7.8", "D7.10",
    "D7.11", "D7.13", "D7.14", "D7.15", "D7.16", "D7.17", "D7.18", "D7.20",
)
P0_FEATURE_IDS = ("D7.1", "D7.9", "D7.12", "D7.19")


class ContractError(ValueError):
    """Base class for dev-workflow contract failures."""


class ContractValidationError(ContractError):
    """Fail-closed validation error carrying one or more written reasons."""

    def __init__(self, errors: Any):
        if isinstance(errors, str):
            errors = (errors,)
        self.errors = tuple(str(error) for error in errors)
        super().__init__("; ".join(self.errors))


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./\-]*$")
_GIT_DIR_RE = re.compile(r"^(?:\.|[A-Za-z0-9])[A-Za-z0-9_./\-]*$")
_COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-:]*$")
_LOOSE_NAME_RE = re.compile(r"^[A-Za-z0-9@][A-Za-z0-9_./@:\-]*$")
_TYPE_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
_REF_RE = re.compile(r"^#/definitions/([A-Z][A-Za-z0-9_]*)$")
_VERSION_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,12}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_RE = re.compile(r"^(?:env|keyring|secret|file):([A-Za-z0-9_./:\-]+)$")
_BOOL_TRUE = frozenset({"1", "true", "yes", "on"})
_BOOL_FALSE = frozenset({"0", "false", "no", "off"})


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _named(value: Any, label: str, pattern: re.Pattern = _IDENTIFIER_RE) -> str:
    text = _text(value).strip()
    if not text or not pattern.match(text):
        raise ContractValidationError("%s must be a non-empty safe name" % label)
    return text


def _names(values: Any, label: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ContractValidationError("%s must be an iterable of names" % label)
    return tuple(_named(value, label) for value in values)


def _loose_names(values: Any, label: str) -> tuple[str, ...]:
    """Names with one separator, e.g. ``kind/bug``, ``@keel/client``."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ContractValidationError("%s must be an iterable of names" % label)
    return tuple(_named(value, label, _LOOSE_NAME_RE) for value in values)


def _paths(values: Any, label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ContractValidationError("%s must be an iterable of paths" % label)
    result = []
    for value in values:
        path = _named(value, label, _PATH_RE)
        if path.startswith("/") or "\\" in path or any(
                part in ("", ".", "..") for part in path.split("/")):
            raise ContractValidationError("%s must be a relative safe path" % label)
        result.append(path)
    return tuple(result)


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ContractValidationError("%s must be a positive integer" % label)
    return value


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ContractValidationError("%s must be a boolean" % label)
    return value


def _flag(value: Any, label: str) -> bool:
    if type(value) is bool:
        return value
    if isinstance(value, str):
        flag = value.strip().lower()
        if flag in _BOOL_TRUE:
            return True
        if flag in _BOOL_FALSE:
            return False
    raise ContractValidationError("%s must be a boolean flag" % label)


def _version(value: Any, label: str = "version") -> str:
    text = _text(value).strip()
    if not _VERSION_RE.match(text):
        raise ContractValidationError(
            "%s must be a strict major.minor.patch version" % label)
    return text


def _version_key(value: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in _version(value).split("."))


def _digest(value: Any, label: str) -> str:
    text = _text(value).strip()
    if not _DIGEST_RE.match(text):
        raise ContractValidationError("%s must be a lowercase sha256 digest" % label)
    return text


def _canonical_digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _secret_ref(value: Any, label: str) -> str:
    text = _text(value).strip()
    if not _SECRET_RE.match(text) or ".." in text:
        raise ContractValidationError(
            "%s must be env:/keyring:/secret:/file: reference, not a literal" % label)
    return text


def _enum(value: Any, enum_cls: type, label: str):
    if isinstance(value, enum_cls):
        return value
    text = _text(value).strip()
    try:
        return enum_cls(text)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_cls)
        raise ContractValidationError(
            "%s must be one of: %s" % (label, allowed)) from None


def _errors(errors: Any, label: str) -> tuple[str, ...]:
    if not errors:
        return ()
    if isinstance(errors, str):
        return (errors,)
    return tuple(_text(error) for error in errors)


# ---------------------------------------------------------------------------
# D7.2 -- worker budgets (local cap and cgroup CPU quota)
# ---------------------------------------------------------------------------

WORKER_CI_ENV = "CI"
WORKER_CPUS_ENV = "KEEL_HARDWARE_CPUS"
WORKER_CAP_ENV = "KEEL_LOCAL_WORKER_CAP"
WORKER_QUOTA_ENV = "KEEL_CGROUP_CPU_QUOTA"
WORKER_ENV_KEYS = frozenset({WORKER_CI_ENV, WORKER_CPUS_ENV, WORKER_CAP_ENV,
                             WORKER_QUOTA_ENV})
DEFAULT_LOCAL_CAP = 2
MAX_LOCAL_CAP = 256


def parse_cgroup_cpu_quota(content: Any) -> float | None:
    """Parse cgroup v2 ``<quota> <period>`` text supplied by the caller.

    ``max`` means no quota.  No file is read: the caller passes the content.
    """
    if not isinstance(content, str):
        raise ContractValidationError("cgroup content must be a string")
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ContractValidationError("cgroup quota line needs quota and period")
        quota, period = parts
        if not period.isdigit() or int(period) <= 0:
            raise ContractValidationError("cgroup period must be a positive integer")
        if quota == "max":
            return None
        if not quota.isdigit() or int(quota) <= 0:
            raise ContractValidationError("cgroup quota must be positive or max")
        return int(quota) / int(period)
    raise ContractValidationError("cgroup content has no quota line")


def parse_cgroup_v1_cpu_quota(quota_text: Any, period_text: Any) -> float | None:
    """Parse the two cgroup v1 scalar files supplied by the caller."""
    for value, label in ((quota_text, "cgroup quota"), (period_text, "cgroup period")):
        if not isinstance(value, str) or not value.strip().lstrip("-").isdigit():
            raise ContractValidationError("%s must be an integer string" % label)
    quota, period = int(quota_text.strip()), int(period_text.strip())
    if period <= 0:
        raise ContractValidationError("cgroup period must be positive")
    if quota < -1:
        raise ContractValidationError("cgroup quota cannot be negative")
    if quota <= 0:  # cgroup v1 uses -1 (and 0) for "no limit"
        return None
    return quota / period


def parse_cpu_count(value: Any, label: str = "cpu count") -> float:
    """Parse a positive finite CPU count from a caller-owned value."""
    if type(value) in (int, float):
        number = float(value)
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value.strip()):
        number = float(value.strip())
    else:
        raise ContractValidationError("%s must be a positive decimal number" % label)
    if not math.isfinite(number) or number <= 0:
        raise ContractValidationError("%s must be a positive finite number" % label)
    return number


@dataclass(frozen=True)
class WorkerBudget:
    """Inputs that determine the effective worker count."""

    hardware_cpus: int
    is_ci: bool
    local_cap: int
    cgroup_cpus: float | None

    def as_dict(self) -> dict:
        return {"hardware_cpus": self.hardware_cpus, "is_ci": self.is_ci,
                "local_cap": self.local_cap, "cgroup_cpus": self.cgroup_cpus}


def make_worker_budget(hardware_cpus: Any, is_ci: Any = False,
                       local_cap: Any = DEFAULT_LOCAL_CAP,
                       cgroup_cpus: Any = None) -> WorkerBudget:
    cpus = _positive_int(hardware_cpus, "hardware cpus")
    cap = _positive_int(local_cap, "local worker cap")
    if cap > MAX_LOCAL_CAP:
        raise ContractValidationError("local worker cap is too large")
    if cgroup_cpus is not None:
        cgroup_cpus = parse_cpu_count(cgroup_cpus, "cgroup cpus")
    return WorkerBudget(cpus, _boolean(is_ci, "is_ci"), cap, cgroup_cpus)


def parse_worker_env(env: Mapping[str, Any] | None,
                     cgroup_content: Any = None) -> WorkerBudget:
    """Build a budget from a caller-supplied environment mapping."""
    if env is None:
        env = {}
    if not isinstance(env, Mapping):
        raise ContractValidationError("worker environment must be a mapping")
    for key in env:
        if _text(key).startswith("KEEL_WORKER_") and key not in WORKER_ENV_KEYS:
            raise ContractValidationError("unknown worker environment key: %s" % key)
    cpus = parse_cpu_count(env.get(WORKER_CPUS_ENV, 1), "hardware cpus")
    if not cpus.is_integer():
        raise ContractValidationError("hardware cpus must be a whole number")
    cap = parse_cpu_count(env.get(WORKER_CAP_ENV, DEFAULT_LOCAL_CAP), "local worker cap")
    if not cap.is_integer() or cap > MAX_LOCAL_CAP:
        raise ContractValidationError("local worker cap must be a small whole number")
    quota = None
    if cgroup_content is not None:
        quota = parse_cgroup_cpu_quota(cgroup_content)
    elif WORKER_QUOTA_ENV in env:
        quota = parse_cpu_count(env[WORKER_QUOTA_ENV], WORKER_QUOTA_ENV)
    return make_worker_budget(int(cpus), _flag(env.get(WORKER_CI_ENV, "false"),
                                               WORKER_CI_ENV), int(cap), quota)


def effective_workers(budget: Any) -> int:
    """CI uses detected CPUs; local work is capped; cgroups cap both."""
    if not isinstance(budget, WorkerBudget):
        raise ContractValidationError("budget must be a WorkerBudget")
    count = budget.hardware_cpus
    if not budget.is_ci:
        count = min(count, budget.local_cap)
    if budget.cgroup_cpus is not None:
        count = min(count, math.floor(budget.cgroup_cpus))
    return max(1, count)


# ---------------------------------------------------------------------------
# D7.3 -- separate type-check programs for host and client faces
# ---------------------------------------------------------------------------

class Face(str, Enum):
    HOST = "host"
    CLIENT = "client"


FACES = (Face.HOST, Face.CLIENT)


@dataclass(frozen=True)
class TypecheckProgram:
    program_id: str
    face: Face
    packages: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"program_id": self.program_id, "face": self.face.value,
                "packages": list(self.packages)}


def make_typecheck_program(program_id: Any, face: Any,
                           packages: Iterable[Any]) -> TypecheckProgram:
    face_value = _enum(face, Face, "face")
    names = _names(packages, "packages")
    if not names:
        raise ContractValidationError("a typecheck program needs at least one package")
    if len(set(names)) != len(names):
        raise ContractValidationError("packages must be unique inside a program")
    return TypecheckProgram(_named(program_id, "program_id"), face_value, names)


DEFAULT_FACE_PROGRAMS = (
    make_typecheck_program("pyright-daemon", Face.HOST, ("keel", "keel.daemon")),
    make_typecheck_program("tsc-client", Face.CLIENT, ("keel_client", "keel_web")),
)


def validate_face_programs(programs: Iterable[TypecheckProgram]) -> tuple[str, ...]:
    """Return written errors: two faces, one owner per package, no combined run."""
    if isinstance(programs, (str, bytes)) or not isinstance(programs, Iterable):
        raise ContractValidationError("programs must be an iterable")
    items = tuple(programs)
    errors: list[str] = []
    for program in items:
        if not isinstance(program, TypecheckProgram):
            errors.append("program must be a TypecheckProgram")
            continue
        if program.face not in FACES:
            errors.append("combined or unknown face is forbidden: %s" % program.program_id)
    ids = [p.program_id for p in items if isinstance(p, TypecheckProgram)]
    if len(ids) != len(set(ids)):
        errors.append("typecheck program ids must be unique")
    seen_faces = [p.face for p in items if isinstance(p, TypecheckProgram)]
    for face in FACES:
        if seen_faces.count(face) != 1:
            errors.append("exactly one typecheck program is required for %s" % face.value)
    owners: dict[str, str] = {}
    for program in items:
        if not isinstance(program, TypecheckProgram):
            continue
        for package in program.packages:
            if package in owners:
                errors.append("package %s belongs to both %s and %s" % (
                    package, owners[package], program.program_id))
            else:
                owners[package] = program.program_id
    return tuple(errors)


def build_face_programs(programs: Iterable[TypecheckProgram]) -> tuple[TypecheckProgram, ...]:
    errors = validate_face_programs(programs)
    if errors:
        raise ContractValidationError(errors)
    return tuple(sorted(programs, key=lambda p: (p.face.value, p.program_id)))


def face_for_package(programs: Iterable[TypecheckProgram], package: Any) -> Face:
    for program in build_face_programs(programs):
        if _text(package) in program.packages:
            return program.face
    raise ContractValidationError("package is not covered by a face program: %s" % package)


# ---------------------------------------------------------------------------
# D7.4 -- typed remote-call contract generation and drift check
# ---------------------------------------------------------------------------

_SCALAR_TS = {"string": "string", "integer": "number", "number": "number",
              "boolean": "boolean", "null": "null"}
_SCHEMA_KEYS = frozenset({"type", "items", "properties", "required", "$ref", "enum"})
_MAX_SCHEMA_DEPTH = 12


def _validate_schema(schema: Any, label: str, depth: int = 0) -> None:
    if depth > _MAX_SCHEMA_DEPTH:
        raise ContractValidationError("schema nesting is too deep")
    if not isinstance(schema, Mapping) or not schema:
        raise ContractValidationError("%s must be a non-empty schema mapping" % label)
    unknown = sorted(set(schema) - _SCHEMA_KEYS)
    if unknown:
        raise ContractValidationError("%s has unsupported keys: %s" % (label, ", ".join(unknown)))
    if "$ref" in schema:
        if len(schema) != 1:
            raise ContractValidationError("%s ref must stand alone" % label)
        if not isinstance(schema["$ref"], str) or not _REF_RE.match(schema["$ref"]):
            raise ContractValidationError("%s ref must be #/definitions/<Name>" % label)
        return
    if "enum" in schema:
        values = schema["enum"]
        if schema.get("type") != "string" or not isinstance(values, (list, tuple)) \
                or not values or any(not isinstance(v, str) or not v for v in values):
            raise ContractValidationError("%s enum needs string values" % label)
        return
    kind = schema.get("type")
    if kind not in set(_SCALAR_TS) | {"array", "object"}:
        raise ContractValidationError("%s has unsupported type: %s" % (label, kind))
    if kind == "array":
        if "items" not in schema:
            raise ContractValidationError("%s array needs items" % label)
        _validate_schema(schema["items"], label + ".items", depth + 1)
        return
    if kind == "object":
        props = schema.get("properties")
        if not isinstance(props, Mapping):
            raise ContractValidationError("%s object needs properties" % label)
        required = schema.get("required", ())
        if isinstance(required, (str, bytes)) or not isinstance(required, Iterable):
            raise ContractValidationError("%s required must be an iterable" % label)
        required = tuple(required)
        for name in props:
            _named(name, "%s property" % label)
        if not set(required) <= set(props) or len(set(required)) != len(required):
            raise ContractValidationError("%s required must name distinct properties" % label)
        for name, child in props.items():
            _validate_schema(child, "%s.%s" % (label, name), depth + 1)


def render_ts_type(schema: Any, depth: int = 0) -> str:
    """Render a validated JSON Schema subset as a TypeScript type."""
    _validate_schema(schema, "schema")
    if "$ref" in schema:
        return _REF_RE.match(schema["$ref"]).group(1)
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    kind = schema["type"]
    if kind in _SCALAR_TS:
        return _SCALAR_TS[kind]
    if kind == "array":
        return "Array<%s>" % render_ts_type(schema["items"], depth + 1)
    parts = []
    required = set(schema.get("required", ()))
    for name, child in sorted(schema.get("properties", {}).items()):
        parts.append("  %s%s: %s;" % (name, "" if name in required else "?",
                                      render_ts_type(child, depth + 1)))
    return "{\n" + "\n".join(parts) + "\n}" if parts else "Record<string, never>"


@dataclass(frozen=True)
class SchemaField:
    name: str
    schema: Mapping[str, Any]

    def as_dict(self) -> dict:
        return {"name": self.name, "schema": dict(self.schema)}


def make_field(name: Any, schema: Any) -> SchemaField:
    field_name = _named(name, "field name")
    _validate_schema(schema, "field %s" % field_name)
    return SchemaField(field_name, dict(schema))


@dataclass(frozen=True)
class ServiceMethod:
    name: str
    params: tuple[SchemaField, ...]
    returns: Mapping[str, Any]

    def as_dict(self) -> dict:
        return {"name": self.name, "params": [p.as_dict() for p in self.params],
                "returns": dict(self.returns)}


def make_method(name: Any, params: Iterable[SchemaField], returns: Any) -> ServiceMethod:
    method_name = _named(name, "method name")
    fields = tuple(params)
    if any(not isinstance(field, SchemaField) for field in fields):
        raise ContractValidationError("method params must be SchemaField values")
    names = [field.name for field in fields]
    if len(names) != len(set(names)):
        raise ContractValidationError("method params must be unique")
    _validate_schema(returns, "method %s return" % method_name)
    return ServiceMethod(method_name, fields, dict(returns))


@dataclass(frozen=True)
class RemoteService:
    name: str
    types: Mapping[str, Mapping[str, Any]]
    methods: tuple[ServiceMethod, ...]

    def as_dict(self) -> dict:
        return {"name": self.name,
                "types": {k: dict(v) for k, v in self.types.items()},
                "methods": [m.as_dict() for m in self.methods]}


def make_service(name: Any, methods: Iterable[ServiceMethod],
                 types: Mapping[str, Mapping[str, Any]] | None = None) -> RemoteService:
    service_name = _named(name, "service name", _TYPE_NAME_RE)
    method_list = tuple(methods)
    if not method_list:
        raise ContractValidationError("a service needs at least one method")
    if any(not isinstance(method, ServiceMethod) for method in method_list):
        raise ContractValidationError("service methods must be ServiceMethod values")
    ids = [method.name for method in method_list]
    if len(ids) != len(set(ids)):
        raise ContractValidationError("service method names must be unique")
    definitions = dict(types or {})
    for type_name, schema in definitions.items():
        _named(type_name, "type name", _TYPE_NAME_RE)
        _validate_schema(schema, "type %s" % type_name)
    refs: list[str] = []

    def collect(schema: Any) -> None:
        if "$ref" in schema:
            refs.append(_REF_RE.match(schema["$ref"]).group(1))
        elif schema.get("type") == "array":
            collect(schema["items"])
        elif schema.get("type") == "object":
            for child in schema.get("properties", {}).values():
                collect(child)

    for schema in definitions.values():
        collect(schema)
    for method in method_list:
        for field in method.params:
            collect(field.schema)
        collect(method.returns)
    missing = sorted(set(refs) - set(definitions))
    if missing:
        raise ContractValidationError("undefined contract types: %s" % ", ".join(missing))
    return RemoteService(service_name, definitions, method_list)


def render_typescript_client(services: Iterable[RemoteService]) -> str:
    """Render deterministic client types and method stubs from services."""
    items = tuple(services)
    if not items:
        raise ContractValidationError("contract generation needs at least one service")
    if any(not isinstance(service, RemoteService) for service in items):
        raise ContractValidationError("services must be RemoteService values")
    lines = ["// generated by keel:d7 contract generation; do not edit"]
    for service in sorted(items, key=lambda s: s.name):
        for type_name, schema in sorted(service.types.items()):
            lines.append("export type %s = %s;" % (type_name, render_ts_type(schema)))
        lines.append("export interface %sClient {" % service.name)
        for method in sorted(service.methods, key=lambda m: m.name):
            args = ", ".join("%s: %s" % (field.name, render_ts_type(field.schema))
                             for field in method.params)
            lines.append("  %s(%s): %s;" % (method.name, args,
                                            render_ts_type(method.returns)))
        lines.append("}")
    return "\n".join(lines) + "\n"


def contract_digest(services: Iterable[RemoteService]) -> str:
    items = tuple(services)
    if not items or any(not isinstance(s, RemoteService) for s in items):
        raise ContractValidationError("services must be a non-empty iterable of RemoteService")
    ordered = sorted((s.as_dict() for s in items), key=lambda d: d["name"])
    return _canonical_digest(ordered)


@dataclass(frozen=True)
class DriftReport:
    matches: bool
    recorded: str
    current: str

    def as_dict(self) -> dict:
        return {"matches": self.matches, "recorded": self.recorded,
                "current": self.current}


def check_contract_drift(services: Iterable[RemoteService],
                         recorded_digest: Any) -> DriftReport:
    current = contract_digest(services)
    recorded = _digest(recorded_digest, "recorded contract digest")
    return DriftReport(recorded == current, recorded, current)


# ---------------------------------------------------------------------------
# D7.5 -- build order and a separate, non-rebuilding check stage
# ---------------------------------------------------------------------------

BUILD_STAGES = (
    "native_addon", "contract_gen", "compile_host", "bundle_host",
    "compile_client", "bundle_client", "web",
)
CHECK_STAGE = "build:check"
_BUILD_VERB_RE = re.compile(r"\b(?:build|compile|bundle|webpack|rollup|esbuild)\b")
_CHECK_VERB_RE = re.compile(r"\b(?:test|tests|pytest|check|verify|lint|typecheck|inspect)\b")


@dataclass(frozen=True)
class BuildStage:
    stage_id: str
    command: str
    produces: tuple[str, ...]
    depends_on: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"stage_id": self.stage_id, "command": self.command,
                "produces": list(self.produces), "depends_on": list(self.depends_on)}


def make_build_stage(stage_id: Any, command: Any, produces: Iterable[Any],
                     depends_on: Iterable[Any] = ()) -> BuildStage:
    stage = _named(stage_id, "stage_id")
    text = _text(command).strip()
    if not text:
        raise ContractValidationError("build command cannot be empty")
    return BuildStage(stage, text, _paths(produces, "produces"),
                      _names(depends_on, "depends_on"))


def validate_build_order(stages: Iterable[BuildStage]) -> tuple[str, ...]:
    if isinstance(stages, (str, bytes)) or not isinstance(stages, Iterable):
        raise ContractValidationError("stages must be an iterable")
    items = tuple(stages)
    errors: list[str] = []
    if any(not isinstance(stage, BuildStage) for stage in items):
        return ("stages must be BuildStage values",)
    ids = [stage.stage_id for stage in items]
    if len(ids) != len(set(ids)):
        errors.append("build stage ids must be unique")
    if set(ids) != set(BUILD_STAGES):
        errors.append("build pipeline must contain exactly the seven documented stages")
    positions = {name: index for index, name in enumerate(BUILD_STAGES)}
    seen: list[str] = []
    for stage in items:
        if stage.stage_id not in positions:
            errors.append("unknown build stage: %s" % stage.stage_id)
            continue
        if not stage.produces:
            errors.append("stage must declare outputs: %s" % stage.stage_id)
        for dep in stage.depends_on:
            if dep not in positions:
                errors.append("unknown dependency: %s" % dep)
            elif dep not in seen:
                errors.append("stage %s depends on a later stage %s" % (
                    stage.stage_id, dep))
        seen.append(stage.stage_id)
    if seen != sorted(seen, key=lambda s: positions.get(s, len(BUILD_STAGES))):
        errors.append("stages must be supplied in documented build order")
    return tuple(errors)


def build_build_plan(stages: Iterable[BuildStage]) -> tuple[BuildStage, ...]:
    errors = validate_build_order(stages)
    if errors:
        raise ContractValidationError(errors)
    return tuple(sorted(stages, key=lambda s: BUILD_STAGES.index(s.stage_id)))


@dataclass(frozen=True)
class CheckPlan:
    commands: tuple[str, ...]
    built_outputs: tuple[str, ...]
    stage: str = CHECK_STAGE

    def as_dict(self) -> dict:
        return {"stage": self.stage, "commands": list(self.commands),
                "built_outputs": list(self.built_outputs)}


def make_check_plan(commands: Iterable[Any], built_outputs: Iterable[Any]) -> CheckPlan:
    """Plan a check stage that consumes built output and never rebuilds it."""
    cmds = tuple(_text(command).strip() for command in commands)
    outputs = _paths(built_outputs, "built_outputs")
    if not cmds or not all(cmds):
        raise ContractValidationError("check stage needs non-empty commands")
    if not outputs:
        raise ContractValidationError("check stage needs declared built outputs")
    errors: list[str] = []
    for command in cmds:
        lowered = command.lower()
        if not _CHECK_VERB_RE.search(lowered) and "--noemit" not in lowered:
            errors.append("check command must be a verify/test command: %s" % command)
        if _BUILD_VERB_RE.search(lowered) and "--noemit" not in lowered:
            errors.append("check command must not rebuild: %s" % command)
        if not any(output in command for output in outputs):
            errors.append("check command must target built output: %s" % command)
    if errors:
        raise ContractValidationError(errors)
    return CheckPlan(cmds, tuple(sorted(outputs)))


# ---------------------------------------------------------------------------
# D7.6 -- embedded build identity and build record
# ---------------------------------------------------------------------------

BUILD_RECORD_PATH = ".build-record.json"
OFFICIAL_DIRTY_MARKER = ""


@dataclass(frozen=True)
class BuildIdentity:
    version: str
    commit: str
    dirty: bool
    official: bool

    def as_dict(self) -> dict:
        return {"version": self.version, "commit": self.commit,
                "dirty": self.dirty, "official": self.official}


def make_build_identity(version: Any, commit: Any, dirty: Any = False,
                        official: Any = False) -> BuildIdentity:
    return BuildIdentity(_version(version), _named(commit, "commit", _COMMIT_RE),
                         _boolean(dirty, "dirty"), _boolean(official, "official"))


def identity_label(identity: Any) -> str:
    """Public form: official builds omit the dirty marker entirely."""
    if not isinstance(identity, BuildIdentity):
        raise ContractValidationError("identity must be a BuildIdentity")
    marker = "-dirty" if identity.dirty and not identity.official else OFFICIAL_DIRTY_MARKER
    return "v%s (%s%s)" % (identity.version, identity.commit, marker)


@dataclass(frozen=True)
class BuildRecord:
    identity: BuildIdentity
    output_digest: str
    outputs: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"identity": self.identity.as_dict(),
                "output_digest": self.output_digest, "outputs": list(self.outputs),
                "path": BUILD_RECORD_PATH}


def make_build_record(identity: Any, output_digest: Any,
                      outputs: Iterable[Any]) -> BuildRecord:
    if not isinstance(identity, BuildIdentity):
        raise ContractValidationError("identity must be a BuildIdentity")
    names = _paths(outputs, "outputs")
    if not names:
        raise ContractValidationError("build record must list outputs")
    return BuildRecord(identity, _digest(output_digest, "output digest"), names)


def verify_build_record(record: Any, expected_identity: Any,
                        expected_digest: Any, present: Any = True,
                        expected_outputs: Iterable[Any] | None = None) -> tuple[str, ...]:
    """Release packing gate: missing, stale or mismatched records fail closed."""
    if not isinstance(expected_identity, BuildIdentity):
        raise ContractValidationError("expected identity must be a BuildIdentity")
    expected_digest = _digest(expected_digest, "expected digest")
    if not _boolean(present, "record present"):
        return ("build record is missing from the output",)
    if not isinstance(record, BuildRecord):
        return ("build record is missing or malformed",)
    errors: list[str] = []
    if record.identity != expected_identity:
        errors.append("build record identity is stale")
    if identity_label(record.identity) != identity_label(expected_identity):
        errors.append("build record public identity is stale")
    if record.output_digest != expected_digest:
        errors.append("build record output digest is stale")
    if expected_outputs is not None:
        wanted = _paths(expected_outputs, "expected outputs")
        if tuple(sorted(record.outputs)) != tuple(sorted(wanted)):
            errors.append("build record output list is stale")
    return tuple(errors)


def release_pack_allowed(record: Any, expected_identity: Any,
                         expected_digest: Any, present: Any = True) -> bool:
    return not verify_build_record(record, expected_identity, expected_digest, present)


def record_is_gitignored(patterns: Iterable[Any]) -> bool:
    """Check that a caller-supplied ignore list covers the build record path."""
    for pattern in patterns:
        if fnmatch.fnmatch(BUILD_RECORD_PATH, _text(pattern).strip()) or \
                fnmatch.fnmatch("build-record.json", _text(pattern).lstrip(".!/")):
            return True
    return False


# ---------------------------------------------------------------------------
# D7.7 -- local vs official build profiles
# ---------------------------------------------------------------------------

class BuildProfile(str, Enum):
    LOCAL = "local"
    OFFICIAL = "official"


@dataclass(frozen=True)
class ProfileResolution:
    profile: BuildProfile
    identity: BuildIdentity
    branding: tuple[tuple[str, str], ...]
    branding_applied: bool

    def as_dict(self) -> dict:
        return {"profile": self.profile.value, "identity": self.identity.as_dict(),
                "branding": [list(item) for item in self.branding],
                "branding_applied": self.branding_applied}


def parse_profile_flag(argv: Iterable[Any]) -> BuildProfile:
    """Parse exactly one ``--profile local|official`` from caller-supplied argv."""
    args = tuple(_text(value) for value in argv)
    profiles: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--profile":
            index += 1
            if index >= len(args):
                raise ContractValidationError("--profile needs a value")
            profiles.append(args[index])
        elif arg.startswith("--profile="):
            profiles.append(arg.split("=", 1)[1])
        else:
            raise ContractValidationError("unexpected build argument: %s" % arg)
        index += 1
    if len(profiles) != 1:
        raise ContractValidationError("exactly one --profile flag is required")
    return _enum(profiles[0], BuildProfile, "build profile")


def resolve_build_profile(profile: Any, identity: Any,
                          inherited_branding: Mapping[str, Any] | None = None) -> ProfileResolution:
    profile_value = _enum(profile, BuildProfile, "build profile")
    if not isinstance(identity, BuildIdentity):
        raise ContractValidationError("identity must be a BuildIdentity")
    branding = dict(inherited_branding or {})
    if not isinstance(branding, dict):
        raise ContractValidationError("inherited branding must be a mapping")
    for key, value in branding.items():
        _named(key, "branding key")
        if not isinstance(value, str) or not value:
            raise ContractValidationError("branding values must be non-empty strings")
    if profile_value is BuildProfile.LOCAL:
        # Local keeps version/commit/dirty and discards inherited branding.
        return ProfileResolution(profile_value, identity, (), False)
    official = BuildIdentity(identity.version, identity.commit, identity.dirty, True)
    applied = tuple(sorted((key, value) for key, value in branding.items()))
    return ProfileResolution(profile_value, official, applied, bool(applied))


# ---------------------------------------------------------------------------
# D7.8 -- Windows and WSL guidance
# ---------------------------------------------------------------------------

class Environment(str, Enum):
    WINDOWS = "windows"
    WSL = "wsl"
    LINUX = "linux"
    MACOS = "macos"


@dataclass(frozen=True)
class BuilderEnvironment:
    checkout: Environment
    toolchain: Environment
    dep_roots: Mapping[str, str]
    native_validation: bool
    windows_lane_separate: bool

    def as_dict(self) -> dict:
        return {"checkout": self.checkout.value, "toolchain": self.toolchain.value,
                "dep_roots": dict(self.dep_roots),
                "native_validation": self.native_validation,
                "windows_lane_separate": self.windows_lane_separate}


def make_builder_environment(checkout: Any, toolchain: Any,
                             dep_roots: Mapping[str, Any],
                             native_validation: Any = False,
                             windows_lane_separate: Any = False) -> BuilderEnvironment:
    return BuilderEnvironment(_enum(checkout, Environment, "checkout environment"),
                              _enum(toolchain, Environment, "toolchain environment"),
                              {k: _named(v, "dep root", _PATH_RE)
                               for k, v in dict(dep_roots).items()},
                              _boolean(native_validation, "native validation"),
                              _boolean(windows_lane_separate, "windows lane separate"))


def validate_builder_environment(env: Any) -> tuple[str, ...]:
    if not isinstance(env, BuilderEnvironment):
        raise ContractValidationError("environment must be a BuilderEnvironment")
    errors: list[str] = []
    if env.checkout is not env.toolchain:
        errors.append("checkout and toolchain must use the same OS environment")
    for name in (env.checkout.value, env.toolchain.value):
        if name not in env.dep_roots:
            errors.append("dependency root is required for %s" % name)
    if len(set(env.dep_roots.values())) != len(env.dep_roots):
        errors.append("each environment needs its own dependency root")
    if Environment.WINDOWS in (env.checkout, env.toolchain):
        if not env.native_validation:
            errors.append("Windows behavior needs native validation")
        if not env.windows_lane_separate:
            errors.append("Windows needs a CI lane separate from Linux")
    if env.checkout is Environment.WSL and env.toolchain is Environment.WSL \
            and "windows" in env.dep_roots and "wsl" in env.dep_roots \
            and env.dep_roots["windows"] == env.dep_roots["wsl"]:
        errors.append("WSL and Windows must not share a dependency root")
    return tuple(errors)


def check_builder_environment(env: Any) -> BuilderEnvironment:
    errors = validate_builder_environment(env)
    if errors:
        raise ContractValidationError(errors)
    return env


# ---------------------------------------------------------------------------
# D7.10 -- worktree-local git hooks
# ---------------------------------------------------------------------------

class HookName(str, Enum):
    PRE_COMMIT = "pre-commit"
    PRE_MERGE_COMMIT = "pre-merge-commit"
    PRE_PUSH = "pre-push"


HOOK_INSTALL_DIR = ".git/hooks"
CHECK_ALL = "check:all"
MAX_AUTOFIX_RETRIES = 2
HOOK_CHECKS = {
    HookName.PRE_COMMIT: ("staged-lint", "autofix", "whitespace",
                          "generated-metadata", "vendor-manifest"),
    HookName.PRE_MERGE_COMMIT: ("pre-merge-check",),
    HookName.PRE_PUSH: ("typecheck",),
}
_HOOK_COMMANDS = {
    "staged-lint": "keel lint --staged --profile staged",
    "autofix": "keel lint --fix --staged --max-retries {retries}",
    "whitespace": "git diff --check --cached",
    "generated-metadata": "keel gate generated-metadata --staged",
    "vendor-manifest": "keel gate vendor-manifest --staged",
    "pre-merge-check": "keel gate pre-merge-check",
    "typecheck": "keel typecheck --all-faces",
    CHECK_ALL: "keel check:all --no-tests --no-build",
}
_ALLOWED_CHECKS = frozenset(_HOOK_COMMANDS)


@dataclass(frozen=True)
class HookSpec:
    hook: HookName
    checks: tuple[str, ...]
    max_retries: int = MAX_AUTOFIX_RETRIES
    check_all_opt_in: bool = False

    def as_dict(self) -> dict:
        return {"hook": self.hook.value, "checks": list(self.checks),
                "max_retries": self.max_retries,
                "check_all_opt_in": self.check_all_opt_in}


def make_hook_spec(hook: Any, checks: Iterable[Any] | None = None,
                   max_retries: Any = MAX_AUTOFIX_RETRIES,
                   check_all_opt_in: Any = False) -> HookSpec:
    hook_value = _enum(hook, HookName, "hook")
    check_names = tuple(_text(name).strip() for name in checks) if checks is not None \
        else HOOK_CHECKS[hook_value]
    return HookSpec(hook_value, check_names, _positive_int(max_retries, "max_retries"),
                    _boolean(check_all_opt_in, "check_all_opt_in"))


def validate_hook_set(specs: Iterable[HookSpec],
                      check_all_enabled: Any = False) -> tuple[str, ...]:
    if isinstance(specs, (str, bytes)) or not isinstance(specs, Iterable):
        raise ContractValidationError("specs must be an iterable")
    enabled = _boolean(check_all_enabled, "check_all_enabled")
    items = tuple(specs)
    errors: list[str] = []
    if any(not isinstance(spec, HookSpec) for spec in items):
        return ("hook specs must be HookSpec values",)
    hooks = [spec.hook for spec in items]
    if set(hooks) != set(HookName) or len(hooks) != len(HookName):
        errors.append("hook set must contain each of the three hooks exactly once")
    for spec in items:
        for check in spec.checks:
            if check not in _ALLOWED_CHECKS:
                errors.append("unknown or test/build check in hook: %s" % check)
            if check == CHECK_ALL and not (enabled and spec.check_all_opt_in):
                errors.append("check:all is opt-in only")
            if "test" in check or "build" in check:
                errors.append("hooks must not run tests or builds: %s" % check)
        if set(spec.checks) != set(HOOK_CHECKS[spec.hook]) and CHECK_ALL not in spec.checks:
            errors.append("hook %s does not carry its staged profile" % spec.hook.value)
        if spec.max_retries > MAX_AUTOFIX_RETRIES:
            errors.append("autofix retry count is not bounded")
    return tuple(errors)


def build_hook_set(specs: Iterable[HookSpec],
                   check_all_enabled: Any = False) -> tuple[HookSpec, ...]:
    errors = validate_hook_set(specs, check_all_enabled)
    if errors:
        raise ContractValidationError(errors)
    return tuple(sorted(specs, key=lambda s: s.hook.value))


def render_hook_script(spec: Any, check_all_enabled: Any = False) -> str:
    if not isinstance(spec, HookSpec):
        raise ContractValidationError("spec must be a HookSpec")
    enabled = _boolean(check_all_enabled, "check_all_enabled")
    errors: list[str] = []
    for check in spec.checks:
        if check not in _ALLOWED_CHECKS:
            errors.append("unknown hook check: %s" % check)
        if "test" in check or "build" in check:
            errors.append("hooks must not run tests or builds: %s" % check)
        if check == CHECK_ALL and not (enabled and spec.check_all_opt_in):
            errors.append("check:all is opt-in only")
    if spec.max_retries > MAX_AUTOFIX_RETRIES:
        errors.append("autofix retry count is not bounded")
    if errors:
        raise ContractValidationError(errors)
    lines = ["#!/bin/sh", "set -eu"]
    for check in spec.checks:
        lines.append(_HOOK_COMMANDS[check].format(retries=spec.max_retries))
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class HookInstall:
    hook: HookName
    path: str
    mode: str = "0755"

    def as_dict(self) -> dict:
        return {"hook": self.hook.value, "path": self.path, "mode": self.mode}


def hook_install_plan(specs: Iterable[HookSpec], git_dir: Any = ".git") -> tuple[HookInstall, ...]:
    root = _named(git_dir, "git_dir", _GIT_DIR_RE)
    if root.startswith("/") or ".." in root.split("/"):
        raise ContractValidationError("hooks must be installed worktree-locally")
    return tuple(HookInstall(spec.hook, "%s/hooks/%s" % (root, spec.hook.value))
                 for spec in build_hook_set(specs))


# ---------------------------------------------------------------------------
# D7.11 -- documentation gates
# ---------------------------------------------------------------------------

DOC_GATES = ("doc-sync", "doc-typecheck", "type-equiv", "dead-links",
             "translation-pairing")
DOC_SYNC_AGGREGATE = "doc-sync"
_CODE_FENCE_RE = re.compile(r"```(?P<lang>[A-Za-z0-9_+\-]*)\n(?P<code>.*?)\n```", re.DOTALL)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_DECL_RE_TEMPLATE = r"^[ \t]*(?:export[ \t]+)?(?:class|def|interface|type|struct)[ \t]+%s\b[^\n]*$"


@dataclass(frozen=True)
class DocGateSpec:
    gate_id: str
    command: str
    bundles: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"gate_id": self.gate_id, "command": self.command,
                "bundles": list(self.bundles)}


def make_doc_gate(gate_id: Any, command: Any, bundles: Iterable[Any]) -> DocGateSpec:
    gid = _named(gate_id, "gate_id")
    return DocGateSpec(gid, _text(command).strip(), _names(bundles, "bundles"))


def validate_doc_gates(gates: Iterable[DocGateSpec]) -> tuple[str, ...]:
    items = tuple(gates)
    if any(not isinstance(gate, DocGateSpec) for gate in items):
        return ("doc gates must be DocGateSpec values",)
    ids = [gate.gate_id for gate in items]
    errors: list[str] = []
    if len(ids) != len(set(ids)):
        errors.append("doc gate ids must be unique")
    for required in DOC_GATES:
        if required not in ids:
            errors.append("missing doc gate: %s" % required)
    aggregate = next((g for g in items if g.gate_id == DOC_SYNC_AGGREGATE), None)
    if aggregate is not None:
        missing = set(DOC_GATES) - {DOC_SYNC_AGGREGATE} - set(aggregate.bundles)
        if missing:
            errors.append("doc-sync does not aggregate: %s" % ", ".join(sorted(missing)))
    return tuple(errors)


def extract_code_fences(document: Any, language: str = "python") -> tuple[str, ...]:
    """Extract fenced code blocks for one language from a caller-supplied doc."""
    if not isinstance(document, str):
        raise ContractValidationError("document must be a string")
    return tuple(match.group("code") for match in _CODE_FENCE_RE.finditer(document)
                 if match.group("lang").lower() == language.lower())


def typecheck_code_fences(document: Any, language: str = "python") -> int:
    """Compile every fence of a language; syntax errors fail closed."""
    fences = extract_code_fences(document, language)
    if not fences:
        raise ContractValidationError("no code fences found to typecheck")
    for index, code in enumerate(fences, 1):
        try:
            compile(code, "<doc-fence-%d>" % index, "exec")
        except (SyntaxError, ValueError) as exc:
            raise ContractValidationError(
                "doc fence %d does not compile: %s" % (index, exc)) from None
    return len(fences)


def check_type_equivalence(document: Any, source: Any, symbol: Any) -> bool:
    """Compare a pasted single-line declaration with the source declaration."""
    name = _named(symbol, "symbol")
    pattern = re.compile(_DECL_RE_TEMPLATE % re.escape(name), re.MULTILINE)
    doc_matches = pattern.findall(_text(document))
    src_matches = pattern.findall(_text(source))
    if len(doc_matches) != 1 or len(src_matches) != 1:
        return False
    normalize = lambda line: " ".join(line.split())
    return normalize(doc_matches[0]) == normalize(src_matches[0])


def check_dead_links(document: Any, available_targets: Iterable[Any]) -> tuple[str, ...]:
    """Return relative markdown link targets absent from the caller's target set."""
    if not isinstance(document, str):
        raise ContractValidationError("document must be a string")
    targets = set(_loose_names(available_targets, "available targets"))
    missing: list[str] = []
    for link in _MD_LINK_RE.findall(document):
        target = link.strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if target.split("#", 1)[0] not in targets:
            missing.append(target)
    return tuple(sorted(set(missing)))


@dataclass(frozen=True)
class TranslationPair:
    source_doc: str
    translated_doc: str
    language: str
    conflict_command: str

    def as_dict(self) -> dict:
        return {"source_doc": self.source_doc, "translated_doc": self.translated_doc,
                "language": self.language, "conflict_command": self.conflict_command}


CONFLICT_REPAIR_COMMAND = "keel docs repair-translation --accept-source %s"


def make_translation_pair(source_doc: Any, translated_doc: Any,
                          language: Any) -> TranslationPair:
    source = _named(source_doc, "source_doc", _PATH_RE)
    translated = _named(translated_doc, "translated_doc", _PATH_RE)
    lang = _named(language, "language")
    if source == translated:
        raise ContractValidationError("translation must be a distinct document")
    return TranslationPair(source, translated, lang, CONFLICT_REPAIR_COMMAND % source)


def validate_translation_pairs(pairs: Iterable[TranslationPair]) -> tuple[str, ...]:
    items = tuple(pairs)
    if any(not isinstance(pair, TranslationPair) for pair in items):
        return ("pairs must be TranslationPair values",)
    errors: list[str] = []
    seen = [pair.translated_doc for pair in items]
    if len(seen) != len(set(seen)):
        errors.append("a translated document must have one pairing record")
    for pair in items:
        if pair.conflict_command != CONFLICT_REPAIR_COMMAND % pair.source_doc:
            errors.append("translation pair is missing the merge-conflict repair command")
    return tuple(errors)


# ---------------------------------------------------------------------------
# D7.13 -- per-file coverage gate
# ---------------------------------------------------------------------------

SECURITY_CRITICAL_MODULES = ("permission_gate", "analyzer", "crypto")
STRICT_COVERAGE = 100.0
COVERAGE_GATE_COMMAND = "coverage:strict"


@dataclass(frozen=True)
class CoveragePolicy:
    strict_modules: tuple[str, ...]
    graded_threshold: float
    gate_command: str = COVERAGE_GATE_COMMAND
    test_command: str = "test"

    def as_dict(self) -> dict:
        return {"strict_modules": list(self.strict_modules),
                "graded_threshold": self.graded_threshold,
                "gate_command": self.gate_command, "test_command": self.test_command}


def make_coverage_policy(strict_modules: Iterable[Any] | None = None,
                         graded_threshold: Any = 90.0,
                         gate_command: Any = COVERAGE_GATE_COMMAND,
                         test_command: Any = "test") -> CoveragePolicy:
    modules = _names(SECURITY_CRITICAL_MODULES if strict_modules is None
                     else strict_modules, "strict_modules")
    if not modules:
        raise ContractValidationError("coverage policy needs strict modules")
    if type(graded_threshold) in (int, float) and not isinstance(graded_threshold, bool):
        threshold = float(graded_threshold)
    else:
        raise ContractValidationError("graded threshold must be a number")
    if not math.isfinite(threshold) or not 0 <= threshold < STRICT_COVERAGE:
        raise ContractValidationError("graded threshold must be in [0, 100)")
    gate = _named(gate_command, "gate_command", _COMMAND_ID_RE)
    tests = _named(test_command, "test_command", _COMMAND_ID_RE)
    if gate == tests:
        raise ContractValidationError("coverage gate must be separate from the test command")
    return CoveragePolicy(modules, threshold, gate, tests)


@dataclass(frozen=True)
class CoverageReport:
    failures: tuple[str, ...]
    checked: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict:
        return {"passed": self.passed, "failures": list(self.failures),
                "checked": list(self.checked)}


def evaluate_coverage(policy: Any, coverage: Mapping[str, Any]) -> CoverageReport:
    if not isinstance(policy, CoveragePolicy):
        raise ContractValidationError("policy must be a CoveragePolicy")
    if not isinstance(coverage, Mapping):
        raise ContractValidationError("coverage must be a mapping of file to percent")
    failures: list[str] = []
    for module in policy.strict_modules:
        if module not in coverage:
            failures.append("security-critical module has no coverage data: %s" % module)
    for name, value in sorted(coverage.items()):
        if type(value) in (int, float) and not isinstance(value, bool):
            percent = float(value)
        else:
            failures.append("coverage for %s must be a number" % name)
            continue
        if not math.isfinite(percent) or not 0 <= percent <= 100:
            failures.append("coverage for %s is out of range" % name)
            continue
        required = STRICT_COVERAGE if name in policy.strict_modules else policy.graded_threshold
        if percent < required:
            failures.append("%s has %.2f%% coverage, needs %.2f%%" % (
                name, percent, required))
    return CoverageReport(tuple(failures), tuple(sorted(coverage)))


# ---------------------------------------------------------------------------
# D7.14 -- test taxonomy
# ---------------------------------------------------------------------------

class TestClass(str, Enum):
    REAL_API_E2E = "real-api-e2e"
    EXPECTED = "expected"
    SNAPSHOT_REPLAY = "snapshot-replay"
    SNAPSHOT_RECORD = "snapshot-record"


SHIPPED_SNAPSHOT_PROFILE = "shipped"
DISPOSITION_RUN = "run"
DISPOSITION_SKIP = "skip"
DISPOSITION_NEEDS_KEY = "requires-key"


@dataclass(frozen=True)
class TestCase:
    test_id: str
    test_class: TestClass
    key_ref: str | None
    profile: str
    owner_local: bool
    shipped_profile: bool

    def as_dict(self) -> dict:
        return {"test_id": self.test_id, "test_class": self.test_class.value,
                "key_ref": self.key_ref, "profile": self.profile,
                "owner_local": self.owner_local,
                "shipped_profile": self.shipped_profile}


def make_test_case(test_id: Any, test_class: Any, key_ref: Any = None,
                   profile: Any = SHIPPED_SNAPSHOT_PROFILE,
                   owner_local: Any = False, shipped_profile: Any = True) -> TestCase:
    kind = _enum(test_class, TestClass, "test class")
    ref = _secret_ref(key_ref, "key_ref") if key_ref is not None else None
    return TestCase(_named(test_id, "test_id"), kind, ref,
                    _named(profile, "profile"), _boolean(owner_local, "owner_local"),
                    _boolean(shipped_profile, "shipped_profile"))


def validate_test_taxonomy(cases: Iterable[TestCase]) -> tuple[str, ...]:
    items = tuple(cases)
    if any(not isinstance(case, TestCase) for case in items):
        return ("cases must be TestCase values",)
    errors: list[str] = []
    ids = [case.test_id for case in items]
    if len(ids) != len(set(ids)):
        errors.append("test ids must be unique")
    for case in items:
        if case.test_class is TestClass.REAL_API_E2E and case.key_ref is None:
            errors.append("real-API e2e needs a key reference: %s" % case.test_id)
        if case.test_class is TestClass.EXPECTED and not case.owner_local:
            errors.append("expected tests must be owner-local: %s" % case.test_id)
        if case.test_class is TestClass.SNAPSHOT_RECORD and case.key_ref is None:
            errors.append("snapshot record mode needs a key reference: %s" % case.test_id)
        if case.test_class is TestClass.SNAPSHOT_REPLAY:
            if case.key_ref is not None:
                errors.append("snapshot replay must run without a key: %s" % case.test_id)
            if not case.shipped_profile:
                errors.append("snapshot replay needs a shipped profile: %s" % case.test_id)
    return tuple(errors)


def test_disposition(case: Any, key_present: Any = False) -> str:
    if not isinstance(case, TestCase):
        raise ContractValidationError("case must be a TestCase")
    present = _boolean(key_present, "key_present")
    if case.test_class is TestClass.REAL_API_E2E:
        return DISPOSITION_RUN if present else DISPOSITION_SKIP
    if case.test_class is TestClass.SNAPSHOT_RECORD:
        return DISPOSITION_RUN if present else DISPOSITION_NEEDS_KEY
    if case.test_class is TestClass.EXPECTED and not case.owner_local:
        raise ContractValidationError("expected tests must be owner-local")
    if case.test_class is TestClass.SNAPSHOT_REPLAY and not case.shipped_profile:
        raise ContractValidationError("snapshot replay needs a shipped profile")
    return DISPOSITION_RUN


# ---------------------------------------------------------------------------
# D7.15 -- credential-free release rehearsals and runner trust
# ---------------------------------------------------------------------------

class RehearsalKind(str, Enum):
    DEPENDENCY_LAYOUT = "dependency-layout"
    PACK = "pack"


@dataclass(frozen=True)
class Rehearsal:
    kind: RehearsalKind
    command: str
    uses_release_recipe: bool
    credential_refs: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"kind": self.kind.value, "command": self.command,
                "uses_release_recipe": self.uses_release_recipe,
                "credential_refs": list(self.credential_refs)}


def make_rehearsal(kind: Any, command: Any, uses_release_recipe: Any = True,
                   credential_refs: Iterable[Any] = ()) -> Rehearsal:
    refs = tuple(_secret_ref(ref, "credential ref") for ref in credential_refs)
    return Rehearsal(_enum(kind, RehearsalKind, "rehearsal kind"),
                     _text(command).strip(), _boolean(uses_release_recipe, "recipe"),
                     refs)


def validate_rehearsals(rehearsals: Iterable[Rehearsal]) -> tuple[str, ...]:
    items = tuple(rehearsals)
    if any(not isinstance(item, Rehearsal) for item in items):
        return ("rehearsals must be Rehearsal values",)
    errors: list[str] = []
    kinds = [item.kind for item in items]
    for kind in RehearsalKind:
        if kinds.count(kind) != 1:
            errors.append("rehearsal needed exactly once: %s" % kind.value)
    for item in items:
        if not item.command:
            errors.append("rehearsal command cannot be empty")
        if not item.uses_release_recipe:
            errors.append("rehearsal must use the exact release recipe: %s" % item.kind.value)
        if item.credential_refs:
            errors.append("rehearsal must run credential-free: %s" % item.kind.value)
        lowered = item.command.lower()
        if any(word in lowered for word in ("publish", "upload", "credential", "token")):
            errors.append("rehearsal must not publish: %s" % item.kind.value)
    return tuple(errors)


@dataclass(frozen=True)
class RunnerContext:
    is_pull_request: bool
    is_fork: bool
    is_bot: bool
    manual_publish: bool

    def as_dict(self) -> dict:
        return {"is_pull_request": self.is_pull_request, "is_fork": self.is_fork,
                "is_bot": self.is_bot, "manual_publish": self.manual_publish}


HOSTED_RUNNER = "hosted"
SELF_HOSTED_RUNNER = "self-hosted"


def select_runner(context: Any) -> str:
    """Self-host only for trusted non-fork, non-bot PRs; manual publish hosted."""
    if not isinstance(context, RunnerContext):
        raise ContractValidationError("context must be a RunnerContext")
    if context.manual_publish or not context.is_pull_request \
            or context.is_fork or context.is_bot:
        return HOSTED_RUNNER
    return SELF_HOSTED_RUNNER


def make_runner_context(is_pull_request: Any, is_fork: Any = False,
                        is_bot: Any = False, manual_publish: Any = False) -> RunnerContext:
    return RunnerContext(_boolean(is_pull_request, "is_pull_request"),
                         _boolean(is_fork, "is_fork"), _boolean(is_bot, "is_bot"),
                         _boolean(manual_publish, "manual_publish"))


# ---------------------------------------------------------------------------
# D7.16 -- package hygiene
# ---------------------------------------------------------------------------

class PackageEcosystem(str, Enum):
    PYTHON = "python"
    NODE = "node"


PYTHON_ECOSYSTEM = PackageEcosystem.PYTHON.value
NODE_ECOSYSTEM = PackageEcosystem.NODE.value
PYTHON_HYGIENE_CHECKS = ("twine check dist/*",
                         "clean-venv import smoke test against built wheel")
NODE_HYGIENE_CHECKS = ("publint-style entrypoint validation",
                       "clean consumer import against built declarations")


@dataclass(frozen=True)
class PackageArtifact:
    name: str
    ecosystem: str
    entrypoints: tuple[str, ...]
    files: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"name": self.name, "ecosystem": self.ecosystem,
                "entrypoints": list(self.entrypoints), "files": list(self.files)}


def make_package_artifact(name: Any, ecosystem: Any, entrypoints: Iterable[Any],
                          files: Iterable[Any]) -> PackageArtifact:
    ecosystem_value = _enum(ecosystem, PackageEcosystem, "ecosystem").value
    return PackageArtifact(_named(name, "package name", _LOOSE_NAME_RE), ecosystem_value,
                           _paths(entrypoints, "entrypoints"),
                           _paths(files, "files"))


def validate_entrypoints(artifact: Any) -> tuple[str, ...]:
    if not isinstance(artifact, PackageArtifact):
        raise ContractValidationError("artifact must be a PackageArtifact")
    errors: list[str] = []
    suffixes = (".py",) if artifact.ecosystem == PYTHON_ECOSYSTEM else (".js", ".cjs", ".mjs", ".d.ts")
    for entry in artifact.entrypoints:
        if not entry.endswith(suffixes):
            errors.append("entrypoint has the wrong suffix: %s" % entry)
        if entry not in artifact.files:
            errors.append("declared entrypoint is not in the package: %s" % entry)
    return tuple(errors)


def consumer_check_plan(artifact: Any) -> tuple[str, ...]:
    if not isinstance(artifact, PackageArtifact):
        raise ContractValidationError("artifact must be a PackageArtifact")
    errors = validate_entrypoints(artifact)
    if errors:
        raise ContractValidationError(errors)
    return PYTHON_HYGIENE_CHECKS if artifact.ecosystem == PYTHON_ECOSYSTEM \
        else NODE_HYGIENE_CHECKS


def package_hygiene_report(artifact: Any) -> dict:
    if not isinstance(artifact, PackageArtifact):
        raise ContractValidationError("artifact must be a PackageArtifact")
    errors = validate_entrypoints(artifact)
    return {"package": artifact.name, "entrypoint_errors": list(errors),
            "consumer_checks": [] if errors else list(consumer_check_plan(artifact)),
            "passed": not errors}


# ---------------------------------------------------------------------------
# D7.17 -- Windows signing docs and packaging profiles
# ---------------------------------------------------------------------------

class SigningMode(str, Enum):
    UNSIGNED = "unsigned"
    SELF_SIGNED = "self-signed"
    ORG_CERT = "org-cert"


PACKAGING_README = "packaging/README.md"
SIGNING_PROFILES = {
    SigningMode.UNSIGNED: "desktop-unsigned",
    SigningMode.SELF_SIGNED: "desktop-self-signed",
    SigningMode.ORG_CERT: "desktop-org-cert",
}


@dataclass(frozen=True)
class PackagingProfile:
    mode: SigningMode
    profile_id: str
    readme_present: bool
    cert_ref: str | None

    def as_dict(self) -> dict:
        return {"mode": self.mode.value, "profile_id": self.profile_id,
                "readme_present": self.readme_present, "cert_ref": self.cert_ref}


def make_packaging_profile(mode: Any, readme_present: Any = True,
                           cert_ref: Any = None) -> PackagingProfile:
    value = _enum(mode, SigningMode, "signing mode")
    ref = _secret_ref(cert_ref, "cert_ref") if cert_ref is not None else None
    return PackagingProfile(value, SIGNING_PROFILES[value],
                            _boolean(readme_present, "readme_present"), ref)


def validate_packaging_profile(profile: Any) -> tuple[str, ...]:
    if not isinstance(profile, PackagingProfile):
        return ("profile must be a PackagingProfile",)
    errors: list[str] = []
    if not profile.readme_present:
        errors.append("Windows signing docs are required reading: %s" % PACKAGING_README)
    if profile.profile_id != SIGNING_PROFILES[profile.mode]:
        errors.append("packaging profile does not match signing mode")
    if profile.mode is SigningMode.UNSIGNED:
        if profile.cert_ref is not None:
            errors.append("unsigned builds must not reference a signing certificate")
    elif profile.cert_ref is None:
        errors.append("signed packaging modes need a certificate reference")
    return tuple(errors)


def required_reading(profile: Any) -> tuple[str, ...]:
    if not isinstance(profile, PackagingProfile):
        raise ContractValidationError("profile must be a PackagingProfile")
    if validate_packaging_profile(profile):
        raise ContractValidationError(validate_packaging_profile(profile))
    return (PACKAGING_README,)


def default_packaging_profile() -> PackagingProfile:
    """Keel ships unsigned; signing modes stay documented for a future cert."""
    return make_packaging_profile(SigningMode.UNSIGNED, True, None)


# ---------------------------------------------------------------------------
# D7.18 -- update-time breaking-change notice
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UpgradeEntry:
    version: str
    breaking: bool
    summary: str

    def as_dict(self) -> dict:
        return {"version": self.version, "breaking": self.breaking,
                "summary": self.summary}


def make_upgrade_entry(version: Any, breaking: Any, summary: Any) -> UpgradeEntry:
    text = _text(summary).strip()
    if not text:
        raise ContractValidationError("upgrade guide entry needs a summary")
    return UpgradeEntry(_version(version), _boolean(breaking, "breaking"), text)


@dataclass(frozen=True)
class BreakingNotice:
    installed: str
    target: str
    entries: tuple[UpgradeEntry, ...]

    @property
    def has_breaking_changes(self) -> bool:
        return bool(self.entries)

    def as_dict(self) -> dict:
        return {"installed": self.installed, "target": self.target,
                "entries": [entry.as_dict() for entry in self.entries]}


def build_breaking_notice(installed: Any, target: Any,
                          entries: Iterable[UpgradeEntry]) -> BreakingNotice:
    installed_version = _version(installed, "installed version")
    target_version = _version(target, "target version")
    if _version_key(installed_version) >= _version_key(target_version):
        raise ContractValidationError("target version must be newer than installed version")
    items = tuple(entries)
    if any(not isinstance(entry, UpgradeEntry) for entry in items):
        raise ContractValidationError("entries must be UpgradeEntry values")
    selected = tuple(sorted(
        (entry for entry in items
         if _version_key(installed_version) < _version_key(entry.version)
         <= _version_key(target_version) and entry.breaking),
        key=lambda entry: _version_key(entry.version)))
    return BreakingNotice(installed_version, target_version, selected)


def render_breaking_notice(notice: Any) -> str:
    if not isinstance(notice, BreakingNotice):
        raise ContractValidationError("notice must be a BreakingNotice")
    lines = ["What changes for you: v%s -> v%s" % (notice.installed, notice.target)]
    if not notice.entries:
        lines.append("No breaking changes in this update.")
    for entry in notice.entries:
        lines.append("- v%s: %s" % (entry.version, entry.summary))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# D7.20 -- label taxonomy and stacked PRs
# ---------------------------------------------------------------------------

KIND_LABELS = frozenset({"kind/bug", "kind/feature", "kind/chore", "kind/docs",
                         "kind/refactor", "kind/test"})
AREA_PREFIX = "area/"
STACK_POLICIES = ("merge-forward", "rebase")


def validate_pr_labels(labels: Iterable[Any]) -> tuple[str, ...]:
    names = _loose_names(labels, "labels")
    errors: list[str] = []
    kinds = [name for name in names if name.startswith("kind/")]
    areas = [name for name in names if name.startswith(AREA_PREFIX)]
    if len(kinds) != 1 or kinds[0] not in KIND_LABELS:
        errors.append("a PR needs exactly one known kind/* label")
    if not areas:
        errors.append("a PR needs at least one area/* label")
    for name in names:
        if not (name in KIND_LABELS or name.startswith(AREA_PREFIX)):
            errors.append("label is outside the taxonomy: %s" % name)
    return tuple(errors)


@dataclass(frozen=True)
class StackedPR:
    pr_id: str
    base: str
    labels: tuple[str, ...]
    policy: str
    native_stack: bool

    def as_dict(self) -> dict:
        return {"pr_id": self.pr_id, "base": self.base, "labels": list(self.labels),
                "policy": self.policy, "native_stack": self.native_stack}


def make_stacked_pr(pr_id: Any, base: Any, labels: Iterable[Any],
                    policy: Any = STACK_POLICIES[0], native_stack: Any = True) -> StackedPR:
    policy_text = _text(policy).strip()
    if policy_text not in STACK_POLICIES:
        raise ContractValidationError("stack policy must be merge-forward or rebase")
    return StackedPR(_named(pr_id, "pr_id"), _named(base, "base"),
                     _loose_names(labels, "labels"), policy_text,
                     _boolean(native_stack, "native_stack"))


def validate_stacked_prs(prs: Iterable[StackedPR]) -> tuple[str, ...]:
    items = tuple(prs)
    if any(not isinstance(pr, StackedPR) for pr in items):
        return ("stacked PRs must be StackedPR values",)
    errors: list[str] = []
    ids = [pr.pr_id for pr in items]
    if len(ids) != len(set(ids)):
        errors.append("PR ids must be unique")
    known = set(ids)
    policies = {pr.policy for pr in items}
    if len(policies) > 1:
        errors.append("a stack must use one merge policy")
    for pr in items:
        errors.extend(validate_pr_labels(pr.labels))
        if pr.base in known and pr.base == pr.pr_id:
            errors.append("PR cannot be its own base: %s" % pr.pr_id)
        if not pr.native_stack:
            errors.append("stacked PRs must use native stacks: %s" % pr.pr_id)
    for pr in items:
        seen = {pr.pr_id}
        cursor = pr.base
        while cursor in known:
            if cursor in seen:
                errors.append("stack has a base cycle at %s" % cursor)
                break
            seen.add(cursor)
            cursor = next(item.base for item in items if item.pr_id == cursor)
    return tuple(dict.fromkeys(errors))


__all__ = [
    "FEATURE_IDS", "P0_FEATURE_IDS", "ContractError", "ContractValidationError",
    # D7.2
    "WORKER_CI_ENV", "WORKER_CPUS_ENV", "WORKER_CAP_ENV", "WORKER_QUOTA_ENV",
    "WORKER_ENV_KEYS",
    "DEFAULT_LOCAL_CAP", "MAX_LOCAL_CAP", "WorkerBudget", "parse_cgroup_cpu_quota",
    "parse_cgroup_v1_cpu_quota", "parse_cpu_count", "make_worker_budget",
    "parse_worker_env", "effective_workers",
    # D7.3
    "Face", "FACES", "TypecheckProgram", "make_typecheck_program",
    "DEFAULT_FACE_PROGRAMS", "validate_face_programs", "build_face_programs",
    "face_for_package",
    # D7.4
    "SchemaField", "ServiceMethod", "RemoteService", "make_field", "make_method",
    "make_service", "render_ts_type", "render_typescript_client", "contract_digest",
    "DriftReport", "check_contract_drift",
    # D7.5
    "BUILD_STAGES", "CHECK_STAGE", "BuildStage", "make_build_stage",
    "validate_build_order", "build_build_plan", "CheckPlan", "make_check_plan",
    # D7.6
    "BUILD_RECORD_PATH", "BuildIdentity", "make_build_identity", "identity_label",
    "BuildRecord", "make_build_record", "verify_build_record", "release_pack_allowed",
    "record_is_gitignored",
    # D7.7
    "BuildProfile", "ProfileResolution", "parse_profile_flag", "resolve_build_profile",
    # D7.8
    "Environment", "BuilderEnvironment", "make_builder_environment",
    "validate_builder_environment", "check_builder_environment",
    # D7.10
    "HookName", "HOOK_INSTALL_DIR", "CHECK_ALL", "MAX_AUTOFIX_RETRIES", "HOOK_CHECKS",
    "HookSpec", "make_hook_spec", "validate_hook_set", "build_hook_set",
    "render_hook_script", "HookInstall", "hook_install_plan",
    # D7.11
    "DOC_GATES", "DOC_SYNC_AGGREGATE", "DocGateSpec", "make_doc_gate",
    "validate_doc_gates", "extract_code_fences", "typecheck_code_fences",
    "check_type_equivalence", "check_dead_links", "TranslationPair",
    "CONFLICT_REPAIR_COMMAND", "make_translation_pair", "validate_translation_pairs",
    # D7.13
    "SECURITY_CRITICAL_MODULES", "STRICT_COVERAGE", "COVERAGE_GATE_COMMAND",
    "CoveragePolicy", "make_coverage_policy", "CoverageReport", "evaluate_coverage",
    # D7.14
    "TestClass", "SHIPPED_SNAPSHOT_PROFILE", "DISPOSITION_RUN", "DISPOSITION_SKIP",
    "DISPOSITION_NEEDS_KEY", "TestCase", "make_test_case", "validate_test_taxonomy",
    "test_disposition",
    # D7.15
    "RehearsalKind", "Rehearsal", "make_rehearsal", "validate_rehearsals",
    "RunnerContext", "HOSTED_RUNNER", "SELF_HOSTED_RUNNER", "select_runner",
    "make_runner_context",
    # D7.16
    "PYTHON_ECOSYSTEM", "NODE_ECOSYSTEM", "PYTHON_HYGIENE_CHECKS",
    "NODE_HYGIENE_CHECKS", "PackageEcosystem", "PackageArtifact", "make_package_artifact",
    "validate_entrypoints", "consumer_check_plan", "package_hygiene_report",
    # D7.17
    "SigningMode", "PACKAGING_README", "SIGNING_PROFILES", "PackagingProfile",
    "make_packaging_profile", "validate_packaging_profile", "required_reading",
    "default_packaging_profile",
    # D7.18
    "UpgradeEntry", "make_upgrade_entry", "BreakingNotice", "build_breaking_notice",
    "render_breaking_notice",
    # D7.20
    "KIND_LABELS", "AREA_PREFIX", "STACK_POLICIES", "validate_pr_labels", "StackedPR",
    "make_stacked_pr", "validate_stacked_prs",
]
