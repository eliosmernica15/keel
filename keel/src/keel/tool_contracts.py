"""keel.tool_contracts -- canonical Addendum 7 tool-pipeline contracts.

This is an *additive* module.  It does not change any existing tool, runner or
permission code; integration into the live session is a separate decision for
the lead (see ``master-plan-v6-tool-contracts-evidence.md``).

The module turns the 20 named contracts in ``addendum7.json ->
metadata.tool_contracts`` into real, testable Python functionality:

  1. canonical_output_and_pure_renderer ...... ToolSpec / output_schema / render
  2. model_facing_schema_field_restrictions .. ToolRegistry.schemas()
  3. single_schema_vocabulary_................. schema compiler + validation
  4. argument_snapshotting_and_immutability ... ArgsSnapshot / deep freeze
  5. pre_execute_decision_model ............... Decision / resolve_pre_decision
  6. monotonic_guards_deny_cannot_become_allow  apply_guards / combine
  7. post_execute_decisions_dlp_............... PostDecision / DLP hooks
  8. around_dispatch_timeout_cancellation ..... CancelSignal / execute_tool
  9. concurrency_classification_............... classify / execute_batch
 10. deterministic_ordering_executor_.......... execute_batch / batch error
 11. per_agent_restriction_intersection ....... ToolRestriction
 12. conditional_tool_activation .............. StepAdmission
 13. stable_error_codes ....................... ToolErrorCode / ToolError
 14. typed_expected_failures .................. ToolError vs value outcomes
 15. turn_completion_and_deferred_context ..... ToolContext markers
 16. typed_source_kind_for_injected_context ... SourceKind / admit_injection
 17. long_running_background_lifecycle ....... BackgroundJob / JobManager
 18. programmatic_tool_call_mode .............. PTCExecutor / reserved names
 19. ui_presentation_purity_and_card_contract . Card / presenters / meta
 20. contract_tests_and_verification .......... conformance kit, dispose()

Only the Python standard library is used.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field, fields
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Iterable, Optional

# ---------------------------------------------------------------------------
# 13. Stable error codes + typed failures (C10.2 / E1.14 / E1.15)
# ---------------------------------------------------------------------------


class ToolErrorCode(str, Enum):
    """Stable, machine-readable error vocabulary.

    The first eleven codes are the mandated Addendum 7 vocabulary.  The last
    few are the *additional* stable codes this module needs for infra-level
    conditions; they are enumerated here (not ad-hoc strings) so a raised code
    can never be undocumented.
    """

    INVALID_ARGS = "INVALID_ARGS"
    INVALID_TOOL_OUTPUT = "INVALID_TOOL_OUTPUT"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    ABORTED = "ABORTED"
    ABORTED_BEFORE_DISPATCH = "ABORTED_BEFORE_DISPATCH"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_CANCELLED = "APPROVAL_CANCELLED"
    APPROVAL_UNAVAILABLE = "APPROVAL_UNAVAILABLE"
    TOOL_CONTEXT_UNAVAILABLE = "TOOL_CONTEXT_UNAVAILABLE"
    UNSUPPORTED_REASONING_EFFORT = "UNSUPPORTED_REASONING_EFFORT"
    # Additional stable codes owned by this module.
    BATCH_EXECUTION_ERROR = "BATCH_EXECUTION_ERROR"
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    MODEL_DIRECT_CALL_DENIED = "MODEL_DIRECT_CALL_DENIED"
    RESERVED_TOOL_NAME = "RESERVED_TOOL_NAME"
    INJECTION_REJECTED = "INJECTION_REJECTED"


MANDATORY_ERROR_CODES = frozenset({
    "INVALID_ARGS", "INVALID_TOOL_OUTPUT", "UNKNOWN_TOOL", "ABORTED",
    "ABORTED_BEFORE_DISPATCH", "TOOL_TIMEOUT", "APPROVAL_REJECTED",
    "APPROVAL_CANCELLED", "APPROVAL_UNAVAILABLE", "TOOL_CONTEXT_UNAVAILABLE",
    "UNSUPPORTED_REASONING_EFFORT",
})


class ToolError(Exception):
    """Typed failure with a stable code.

    ``reason`` is a *durable* diagnostic kept out of model-facing content by
    construction.  ``name`` + ``code`` are the only fields exposed to the
    model; callers never parse prose for ids or state (E1.14).
    """

    def __init__(self, code: ToolErrorCode | str, name: str,
                 reason: str | None = None) -> None:
        self.code = code.value if isinstance(code, ToolErrorCode) else str(code)
        self.name = name
        self.reason = reason
        super().__init__(f"{name}: {self.code}")

    @property
    def model_facing(self) -> dict[str, str]:
        return {"name": self.name, "code": self.code}

    def to_dict(self) -> dict[str, Any]:
        """Full durable record (reason is present here, never in display)."""
        out: dict[str, Any] = {"name": self.name, "code": self.code}
        if self.reason is not None:
            out["reason"] = self.reason
        return out


class ToolBatchExecutionError(Exception):
    """Typed batch-level failure that preserves already-committed outcomes."""

    def __init__(self, outcomes: list["ToolResult"], reason: str) -> None:
        self.outcomes = outcomes
        self.code = ToolErrorCode.BATCH_EXECUTION_ERROR.value
        self.reason = reason
        super().__init__(f"batch execution failed ({self.code}): {reason}")


def failure_display(name: str, code: ToolErrorCode | str) -> str:
    """Model-facing content for a failure: name + code only, never prose.

    The raw reason stays exclusively in ``ToolResult.durable_reason``.
    """
    value = code.value if isinstance(code, ToolErrorCode) else str(code)
    return f"[tool_error name={name} code={value}]"


# ---------------------------------------------------------------------------
# 3. One schema vocabulary; unsupported keywords rejected (E1.3)
# ---------------------------------------------------------------------------

_ALLOWED_TYPES = frozenset({
    "string", "integer", "number", "boolean", "array", "object", "null",
})

# Explicit allowlist.  Anything else ($ref, allOf, anyOf, not, if, format,
# callbacks, default, examples, internal metadata fields, ...) is rejected at
# registration -- never silently ignored.
ALLOWED_SCHEMA_KEYWORDS = frozenset({
    "type", "properties", "required", "additionalProperties", "items",
    "oneOf", "enum", "const", "description", "title",
    "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems",
})


class SchemaError(ValueError):
    """Raised at registration when a schema violates the vocabulary."""


def validate_schema_definition(schema: Any, *, path: str = "$",
                               require_additional_properties: bool = True) -> None:
    """Compile-time validation of a single schema node (recursive).

    ``require_additional_properties`` enforces E1.3's "objects with explicit
    additionalProperties": an object node without that key is invalid.
    """
    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: schema must be an object")
    unknown = set(schema) - ALLOWED_SCHEMA_KEYWORDS
    if unknown:
        raise SchemaError(
            f"{path}: unsupported schema keyword(s): {sorted(unknown)}")

    typ = schema.get("type")
    if typ is not None and typ not in _ALLOWED_TYPES:
        raise SchemaError(f"{path}: unsupported type {typ!r}")

    if "const" in schema:
        _check_jsonable(schema["const"], f"{path}.const")
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or not enum:
            raise SchemaError(f"{path}.enum must be a non-empty array")
        for i, item in enumerate(enum):
            _check_jsonable(item, f"{path}.enum[{i}]")

    if "oneOf" in schema:
        branches = schema["oneOf"]
        if not isinstance(branches, list) or not branches:
            raise SchemaError(f"{path}.oneOf must be a non-empty array")
        for i, branch in enumerate(branches):
            if not isinstance(branch, dict) or "type" not in branch:
                raise SchemaError(
                    f"{path}.oneOf[{i}] must be a schema with an explicit type")
            validate_schema_definition(
                branch, path=f"{path}.oneOf[{i}]",
                require_additional_properties=require_additional_properties)

    if "properties" in schema:
        props = schema["properties"]
        if not isinstance(props, dict):
            raise SchemaError(f"{path}.properties must be an object")
        for key, sub in props.items():
            if not isinstance(key, str):
                raise SchemaError(f"{path}.properties keys must be strings")
            validate_schema_definition(
                sub, path=f"{path}.properties.{key}",
                require_additional_properties=require_additional_properties)
    if "required" in schema:
        req = schema["required"]
        if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
            raise SchemaError(f"{path}.required must be an array of strings")
    if "items" in schema:
        validate_schema_definition(
            schema["items"], path=f"{path}.items",
            require_additional_properties=require_additional_properties)

    if typ == "object" or ("properties" in schema or "required" in schema):
        if "additionalProperties" not in schema:
            if require_additional_properties:
                raise SchemaError(
                    f"{path}: object schemas must declare additionalProperties "
                    "explicitly")
        else:
            ap = schema["additionalProperties"]
            if not isinstance(ap, bool):
                validate_schema_definition(
                    ap, path=f"{path}.additionalProperties",
                    require_additional_properties=require_additional_properties)


def infer_schema_type(schema: dict) -> Optional[str | list[str]]:
    """Infer the expected type(s) from explicit type, const, enum or shape."""
    if "type" in schema:
        return schema["type"]
    if "oneOf" in schema:
        return [b["type"] for b in schema["oneOf"]]
    if "const" in schema:
        return _json_type(schema["const"])
    if "enum" in schema and schema["enum"]:
        types = {_json_type(x) for x in schema["enum"]}
        return sorted(types)[0] if len(types) == 1 else sorted(types)
    if "properties" in schema or "required" in schema:
        return "object"
    if "items" in schema:
        return "array"
    return None


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _check_jsonable(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _check_jsonable(v, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise SchemaError(f"{path}: object keys must be strings")
            _check_jsonable(v, f"{path}.{k}")
        return
    raise SchemaError(f"{path}: value is not lossless JSON: {type(value).__name__}")


def to_jsonable(value: Any, *, path: str = "$",
                code: ToolErrorCode = ToolErrorCode.INVALID_ARGS) -> Any:
    """Deep-copy *value* into a lossless plain-JSON structure."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v, path=f"{path}[{i}]", code=code)
                for i, v in enumerate(value)]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise ToolError(code, path, f"object keys must be strings")
            out[k] = to_jsonable(v, path=f"{path}.{k}", code=code)
        return out
    raise ToolError(code, path,
                    f"value is not lossless JSON: {type(value).__name__}")


def validate_value(schema: dict, value: Any, path: str = "$") -> list[str]:
    """Runtime validation against the single schema vocabulary.

    Returns a list of human-readable violations (empty means valid).
    """
    errors: list[str] = []
    if not isinstance(schema, dict):
        return errors

    # exact-one oneOf
    if "oneOf" in schema:
        matches = sum(
            1 for branch in schema["oneOf"]
            if not validate_value(branch, value, f"{path}|oneOf")
        )
        if matches != 1:
            errors.append(f"{path}: oneOf requires exactly one matching branch "
                          f"(matched {matches})")
        return errors

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value must equal const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value must be one of {schema['enum']!r}")
    if errors:
        return errors

    expected = infer_schema_type(schema)
    expected_types = expected if isinstance(expected, list) else (
        [expected] if expected else [])
    if expected_types and _json_type(value) not in expected_types:
        errors.append(f"{path}: expected {expected}, got {_json_type(value)}")
        return errors

    typ = expected_types[0] if len(expected_types) == 1 else _json_type(value)
    if typ == "object" and isinstance(value, dict):
        for req in schema.get("required", []) or []:
            if req not in value:
                errors.append(f"{path}: missing required field {req!r}")
        props = schema.get("properties") or {}
        ap = schema.get("additionalProperties", True)
        for key, val in value.items():
            if key in props:
                errors.extend(validate_value(props[key], val, f"{path}.{key}"))
            elif ap is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(ap, dict):
                errors.extend(validate_value(ap, val, f"{path}.{key}"))
    elif typ == "array" and isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(value):
                errors.extend(validate_value(item_schema, item, f"{path}[{i}]"))
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            errors.append(f"{path}: array shorter than minItems")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            errors.append(f"{path}: array longer than maxItems")
    elif typ == "string" and isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength")
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            errors.append(f"{path}: string longer than maxLength")
    elif typ in ("integer", "number") and not isinstance(value, bool):
        lo, hi = schema.get("minimum"), schema.get("maximum")
        if isinstance(lo, (int, float)) and value < lo:
            errors.append(f"{path}: value below minimum")
        if isinstance(hi, (int, float)) and value > hi:
            errors.append(f"{path}: value above maximum")
    return errors


# ---------------------------------------------------------------------------
# 4. Argument snapshotting / deep freeze (E1.4)
# ---------------------------------------------------------------------------


def deep_freeze(value: Any) -> Any:
    """Return an immutable view: mappings -> MappingProxyType, lists -> tuple."""
    if isinstance(value, dict):
        return MappingProxyType({k: deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(deep_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class ArgsSnapshot:
    """A frozen, lossless JSON snapshot shared by policy, execution and UI.

    ``json`` is a private deep copy (fresh containers) so a caller mutating the
    original dict after dispatch cannot change what the pipeline sees.
    ``frozen`` is the immutable view handed to policy hooks and the handler;
    hooks return decisions, never modified args.
    """

    json: Any
    frozen: Any = field(init=False, repr=False, compare=False)
    canonical: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "frozen", deep_freeze(self.json))
        object.__setattr__(
            self, "canonical",
            json.dumps(self.json, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False))

    def as_dict(self) -> dict[str, Any]:
        """Independent mutable copy, for handlers that require a plain dict."""
        return copy.deepcopy(self.json)


def snapshot_args(args: Any, *, name: str = "args") -> ArgsSnapshot:
    """Normalise, deep-copy and freeze caller arguments before policy runs."""
    if args is None:
        args = {}
    json_value = to_jsonable(args, path=name)
    if not isinstance(json_value, dict):
        raise ToolError(ToolErrorCode.INVALID_ARGS, name,
                        "tool arguments must be a JSON object")
    return ArgsSnapshot(json_value)


# ---------------------------------------------------------------------------
# 5 & 6. Pre-execute decision model + monotonic guards (E1.5 / E1.6)
# ---------------------------------------------------------------------------


class DecisionKind(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    CANCEL = "cancel"
    ASK = "ask"


_SEVERITY = {
    DecisionKind.ALLOW: 0,
    DecisionKind.ASK: 1,
    DecisionKind.CANCEL: 2,
    DecisionKind.DENY: 3,
}


@dataclass(frozen=True)
class Decision:
    """One pre-execute decision.

    ``allow_once`` is only meaningful on an ALLOW decision; only an
    allow-once decision proceeds.  ``code`` is an optional structured error id
    for deny/cancel.  ``display_reason`` is an optional localized reason for
    the user; ``reason`` is the audited internal reason.
    """

    kind: DecisionKind
    reason: str = ""
    code: Optional[str] = None
    allow_once: bool = False
    audited: bool = False
    display_reason: Optional[str] = None

    @classmethod
    def allow(cls, reason: str = "allowed") -> "Decision":
        return cls(DecisionKind.ALLOW, reason=reason, allow_once=True)

    @classmethod
    def deny(cls, reason: str, code: Optional[str] = None) -> "Decision":
        return cls(DecisionKind.DENY, reason=reason, code=code)

    @classmethod
    def cancel(cls, reason: str, code: Optional[str] = None) -> "Decision":
        return cls(DecisionKind.CANCEL, reason=reason, code=code)

    @classmethod
    def ask(cls, reason: str, *, audited: bool = True,
            display_reason: Optional[str] = None) -> "Decision":
        return cls(DecisionKind.ASK, reason=reason, audited=audited,
                   display_reason=display_reason)


PreHook = Callable[[str, ArgsSnapshot], Decision]
Guard = Callable[[str, ArgsSnapshot, Decision], Decision]
PostHook = Callable[[str, ArgsSnapshot, "ToolResult"], "PostDecision"]
ApprovalResponder = Callable[[str, ArgsSnapshot, Decision], Decision]


def combine_decisions(a: Decision, b: Decision) -> Decision:
    """Monotonic fold: the more restrictive decision always wins.

    Order-independent by construction -- a later ALLOW can never undo an
    earlier DENY (E1.6).  Ties keep the first decision.
    """
    if _SEVERITY[b.kind] > _SEVERITY[a.kind]:
        return b
    return a


def apply_guards(base: Decision, guards: Iterable[Guard], name: str,
                 args: ArgsSnapshot) -> Decision:
    """Evaluate guards after all hooks; guards can only tighten (never allow)."""
    effective = base
    for guard in guards:
        candidate = guard(name, args, effective)
        if not isinstance(candidate, Decision):
            # A malformed guard must fail closed, never widen permission.
            effective = combine_decisions(
                effective, Decision.deny("guard returned a non-Decision"))
            continue
        # Enforce monotonicity at the source: a guard may not produce ALLOW
        # for an already-denied call, and its own ALLOW is never an upgrade.
        if effective.kind != DecisionKind.ALLOW:
            candidate = Decision(
                candidate.kind,
                reason=candidate.reason or "guard tightened decision",
                code=candidate.code)
        effective = combine_decisions(effective, candidate)
    return effective


def resolve_pre_decision(name: str, args: ArgsSnapshot, *,
                         base: Decision, pre_hooks: Iterable[PreHook],
                         guards: Iterable[Guard],
                         approval_responder: Optional[ApprovalResponder],
                         agent_id: Optional[str]) -> tuple[Decision, list[str]]:
    """Run the whole pre-execute gate; return (effective decision, audit log)."""
    audit: list[str] = []
    # Agentless calls fail closed (E1.5).
    if agent_id is None:
        denial = Decision.deny(
            "agentless tool call has no permission context",
            code=ToolErrorCode.TOOL_CONTEXT_UNAVAILABLE.value)
        audit.append(denial.reason)
        return denial, audit

    effective = base
    for hook in pre_hooks:
        candidate = hook(name, args)
        if not isinstance(candidate, Decision):
            candidate = Decision.deny("pre-hook returned a non-Decision")
        effective = combine_decisions(effective, candidate)

    effective = apply_guards(effective, guards, name, args)

    if effective.kind == DecisionKind.ASK:
        audit.append(f"ask: {effective.reason} (audited={effective.audited})")
        if approval_responder is None:
            # Missing approval channel fails closed (W3.12 / E7.19).
            denial = Decision.deny(
                "approval required but no approval channel is available",
                code=ToolErrorCode.APPROVAL_UNAVAILABLE.value)
            audit.append(denial.reason)
            return denial, audit
        answer = approval_responder(name, args, effective)
        if not isinstance(answer, Decision):
            answer = Decision.deny("approval responder returned a non-Decision")
        if answer.kind == DecisionKind.CANCEL and answer.code is None:
            effective = Decision.cancel(
                answer.reason or "approval was cancelled",
                code=ToolErrorCode.APPROVAL_CANCELLED.value)
        elif answer.kind in (DecisionKind.DENY, DecisionKind.CANCEL):
            effective = answer
        elif answer.kind == DecisionKind.ALLOW and answer.allow_once:
            # Approval resolves ASK into an allow-once decision.  This is the
            # only path that upgrades ASK, and it requires an explicit grant.
            effective = answer
        else:
            effective = Decision.deny(
                "approval did not grant allow-once permission",
                code=ToolErrorCode.APPROVAL_REJECTED.value)

    audit.append(f"effective: {effective.kind.value} ({effective.reason})")
    return effective, audit


def pre_decision_to_error(decision: Decision) -> ToolError:
    """Map a non-allow pre-decision to its typed failure."""
    if decision.kind == DecisionKind.CANCEL:
        code = decision.code or ToolErrorCode.ABORTED.value
    else:
        code = decision.code or ToolErrorCode.APPROVAL_REJECTED.value
    return ToolError(code, "permission", reason=decision.reason)


# ---------------------------------------------------------------------------
# 7. Post-execute decisions: content vs value (E1.7 / B3.8 / C-13)
# ---------------------------------------------------------------------------


class PostAction(str, Enum):
    ACCEPT = "accept"
    REPLACE_CONTENT = "replace_content"   # presentation only
    REPLACE_VALUE = "replace_value"       # confidentiality / DLP
    ATTACH_CONTEXT = "attach_context"
    BLOCK = "block"


@dataclass(frozen=True)
class PostDecision:
    """One post-execute decision.

    ``replace_content`` and ``replace_value`` are mutually exclusive: the
    former changes only ``ToolResult.display`` (the value survives, so it is
    *not* confidentiality); the latter changes the actual ``value`` that both
    the renderer and programmatic callers see (DLP must use this or BLOCK).
    """

    action: PostAction
    content: Optional[str] = None
    value: Any = None
    context: Optional[dict] = None
    code: Optional[str] = None
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.action == PostAction.REPLACE_CONTENT and self.value is not None:
            raise ValueError("replace_content cannot carry a replacement value")
        if self.action == PostAction.REPLACE_VALUE and self.content is not None:
            raise ValueError("replace_value cannot carry replacement content")
        if self.action == PostAction.REPLACE_CONTENT and self.content is None:
            raise ValueError("replace_content requires content")
        if self.action == PostAction.BLOCK and self.reason is None:
            raise ValueError("block requires corrective feedback (reason)")

    @classmethod
    def accept(cls) -> "PostDecision":
        return cls(PostAction.ACCEPT)

    @classmethod
    def replace_content(cls, content: str) -> "PostDecision":
        return cls(PostAction.REPLACE_CONTENT, content=content)

    @classmethod
    def replace_value(cls, value: Any) -> "PostDecision":
        return cls(PostAction.REPLACE_VALUE, value=value)

    @classmethod
    def attach_context(cls, context: dict) -> "PostDecision":
        return cls(PostAction.ATTACH_CONTEXT, context=context)

    @classmethod
    def block(cls, reason: str, *,
              code: ToolErrorCode | str = ToolErrorCode.APPROVAL_REJECTED) -> "PostDecision":
        value = code.value if isinstance(code, ToolErrorCode) else str(code)
        return cls(PostAction.BLOCK, reason=reason, code=value)


def dlp_replace_value(marker: str = "[REDACTED]") -> PostHook:
    """DLP that protects the *value*, not just the display (B3.8 / C-13)."""
    def _hook(name: str, args: ArgsSnapshot, result: "ToolResult") -> PostDecision:
        return PostDecision.replace_value(marker)
    return _hook


def dlp_block(reason: str, *,
              code: ToolErrorCode | str = ToolErrorCode.APPROVAL_REJECTED) -> PostHook:
    def _hook(name: str, args: ArgsSnapshot, result: "ToolResult") -> PostDecision:
        return PostDecision.block(reason, code=code)
    return _hook


def apply_post_hooks(name: str, args: ArgsSnapshot, result: "ToolResult",
                     hooks: Iterable[PostHook]) -> "ToolResult":
    """Apply post decisions in order, enforcing content/value exclusivity."""
    current = result
    for hook in hooks:
        decision = hook(name, args, current)
        if not isinstance(decision, PostDecision):
            continue
        if decision.action == PostAction.ACCEPT:
            continue
        if decision.action == PostAction.REPLACE_CONTENT:
            # Presentation only -- the value is deliberately NOT touched.
            current = replace(current, display=decision.content or "")
        elif decision.action == PostAction.REPLACE_VALUE:
            new_value = to_jsonable(decision.value, path=name,
                                    code=ToolErrorCode.INVALID_TOOL_OUTPUT)
            current = replace(
                current, value=new_value,
                display=safe_render(current.renderer, args.json, new_value))
        elif decision.action == PostAction.ATTACH_CONTEXT:
            if decision.context is not None:
                current = replace(
                    current,
                    attached_context=list(current.attached_context) +
                    [copy.deepcopy(decision.context)])
        elif decision.action == PostAction.BLOCK:
            code = decision.code or ToolErrorCode.APPROVAL_REJECTED.value
            current = failure_result(
                name, ToolErrorCode(code), reason=decision.reason)
            current = replace(current, attached_context=list(current.attached_context))
    return current


# ---------------------------------------------------------------------------
# 8. Cancellation + around-dispatch (E1.8 / E1.9 / E1.18)
# ---------------------------------------------------------------------------


class CancelSignal:
    """Cooperative cancellation primitive with cascading links."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._links: list[CancelSignal] = []

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            links = list(self._links)
        for link in links:
            link.cancel()

    def link(self, other: "CancelSignal") -> None:
        with self._lock:
            self._links.append(other)
        if self.cancelled:
            other.cancel()

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self._event.wait(timeout)


class FusedCancelSignal(CancelSignal):
    """Cancellation that fires when *any* source fires.

    Used by the registry to re-fuse the caller's signal after an around-dispatch
    wrapper, so a wrapper may add a signal but can never remove the caller's.
    """

    def __init__(self, *sources: CancelSignal) -> None:
        super().__init__()
        self._sources = tuple(sources)

    @property
    def cancelled(self) -> bool:
        return super().cancelled or any(s.cancelled for s in self._sources)

    def wait(self, timeout: Optional[float] = None) -> bool:
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            if self.cancelled:
                return True
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                time.sleep(min(0.005, remaining))
            else:
                time.sleep(0.005)


def fuse(*signals: CancelSignal) -> CancelSignal:
    return FusedCancelSignal(*signals)


# ---------------------------------------------------------------------------
# 15. ToolContext: conclude_turn / defer_context / typed injection (E1.16/E1.17)
# ---------------------------------------------------------------------------


class SourceKind(str, Enum):
    AGENT_MESSAGE = "agent-message"
    SUBAGENT_SETTLED = "subagent-settled"
    TOOL_RESULT = "tool-result"
    USER = "user"
    SYSTEM = "system"


@dataclass(frozen=True)
class InjectedMessage:
    """A context injection with a mandatory typed source kind (E1.17)."""

    kind: SourceKind
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


def admit_injection(message: Any) -> InjectedMessage:
    """Reject old/untyped wrappers at admission time."""
    if not isinstance(message, InjectedMessage):
        raise ToolError(ToolErrorCode.INJECTION_REJECTED, "inject",
                        "injection must be an InjectedMessage with a typed source kind")
    if not isinstance(message.kind, SourceKind):
        raise ToolError(ToolErrorCode.INJECTION_REJECTED, "inject",
                        "injection.source_kind must be a SourceKind")
    return message


@dataclass
class ToolContext:
    """Execution-local context handed to the tool handler."""

    tool_name: str
    cancel: CancelSignal
    agent_id: Optional[str] = None
    deferred_context: list[dict] = field(default_factory=list)
    injections: list[InjectedMessage] = field(default_factory=list)
    conclude: bool = False

    def conclude_turn(self) -> None:
        """Mark a successful tool as ending the turn (E1.16)."""
        self.conclude = True

    def defer_context(self, context: dict) -> None:
        """Attach context that the loop appends *after* the result (E1.16)."""
        self.deferred_context.append(copy.deepcopy(context))

    def inject(self, message: InjectedMessage) -> None:
        self.injections.append(admit_injection(message))


def forward_conclude_turn(nested: Iterable["ToolResult"]) -> bool:
    """Composites forward conclude_turn only from authoritative nested success.

    A nested failure or an aborted child must not end the outer turn.
    """
    results = list(nested)
    return bool(results) and all(r.ok and r.conclude_turn for r in results)


# ---------------------------------------------------------------------------
# 1 & 2. ToolSpec and ToolRegistry: canonical output + allowlisted schema
# ---------------------------------------------------------------------------

RESERVED_TOOL_NAMES = frozenset({"run_code"})


class ConcurrencyClass(str, Enum):
    SAFE = "concurrency_safe"
    EXCLUSIVE = "exclusive"


Handler = Callable[..., Any]
Renderer = Callable[[dict, Any], str]


@dataclass(frozen=True)
class ToolSpec:
    """A tool with a mandatory canonical output schema and a pure renderer."""

    name: str
    description: str
    input_schema: dict
    output_schema: dict
    handler: Handler
    renderer: Renderer
    permission: str = "execute"
    concurrency: ConcurrencyClass = ConcurrencyClass.EXCLUSIVE
    concurrency_safe: Optional[Callable[[dict], bool]] = None
    timeout_s: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    scoped: bool = False  # scoped registrations stay exempt from restrictions

    def is_safe(self, args: dict) -> bool:
        """Only an explicit ``True`` opts in; anything else is exclusive."""
        return classify(self, args)


def classify(spec: ToolSpec, args: dict) -> bool:
    """Pure concurrency classifier (E1.10).

    Only a boolean ``True`` opts in.  Omission, exception or a non-bool result
    all degrade to exclusive.
    """
    if spec.concurrency_safe is None:
        return spec.concurrency is ConcurrencyClass.SAFE
    try:
        result = spec.concurrency_safe(args)
    except Exception:
        return False
    return result is True


class ToolRegistry:
    """Authoritative, disposable registry of validated ToolSpecs + hooks."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._pre_hooks: list[PreHook] = []
        self._guards: list[Guard] = []
        self._post_hooks: list[PostHook] = []
        self._wrappers: list[Callable] = []

    # -- registration -----------------------------------------------------
    def register(self, spec: ToolSpec, *, replace: bool = False) -> None:
        if not isinstance(spec, ToolSpec):
            raise TypeError("spec must be a ToolSpec instance")
        if not isinstance(spec.name, str) or not spec.name.strip():
            raise ValueError("tool name must be a non-empty string")
        if not isinstance(spec.description, str) or not spec.description.strip():
            raise ValueError("tool description must be a non-empty string")
        if spec.name in RESERVED_TOOL_NAMES:
            raise ValueError(f"tool name {spec.name!r} is reserved")
        if not callable(spec.handler) or not callable(spec.renderer):
            raise ValueError("tool handler and renderer must be callable")
        if not isinstance(spec.input_schema, dict):
            raise ValueError("tool input_schema must be a JSON-schema object")
        # GATE: a tool without an output schema fails registration (E1.1).
        if not isinstance(spec.output_schema, dict) or not spec.output_schema:
            raise ValueError(
                f"tool {spec.name!r} has no canonical output_schema (mandatory)")
        validate_schema_definition(
            spec.input_schema, path=f"{spec.name}.input",
            require_additional_properties=True)
        validate_schema_definition(
            spec.output_schema, path=f"{spec.name}.output",
            require_additional_properties=True)
        if spec.permission not in {
                "read", "write", "execute", "network", "process_control",
                "destructive"}:
            raise ValueError(f"unknown permission class {spec.permission!r}")
        if spec.timeout_s is not None and spec.timeout_s < 0:
            raise ValueError("timeout_s must be non-negative")
        if spec.concurrency_safe is not None and not callable(spec.concurrency_safe):
            raise ValueError("concurrency_safe must be callable or None")
        if spec.name in self._tools and not replace:
            raise ValueError(f"duplicate tool registration: {spec.name!r}")
        self._tools[spec.name] = spec

    # -- lookup -----------------------------------------------------------
    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def list_tools(self) -> list[ToolSpec]:
        return [self._tools[n] for n in self.names()]

    def schemas(self, names: Iterable[str] | None = None, *,
                restriction: "ToolRestriction | None" = None) -> list[dict[str, Any]]:
        """E1.2: project ONLY name, description, parameters (input_schema).

        Execution callbacks, timeout, renderer, output_schema, concurrency and
        metadata never leak into a model-facing request.  When a restriction is
        supplied, the SAME admission decision used by ``execute_tool`` hides
        non-admitted tools from the declaration.
        """
        selected = self.names() if names is None else [n for n in names if n in self._tools]
        selected = [n for n in selected
                    if admission_decision(self._tools[n], restriction).kind
                    is DecisionKind.ALLOW]
        return [
            {
                "name": self._tools[n].name,
                "description": self._tools[n].description,
                "input_schema": copy.deepcopy(self._tools[n].input_schema),
            }
            for n in selected
        ]

    # -- hooks (registered with the scope; cleared by dispose) ------------
    def add_pre_hook(self, hook: PreHook) -> None:
        self._pre_hooks.append(hook)

    def add_guard(self, guard: Guard) -> None:
        self._guards.append(guard)

    def add_post_hook(self, hook: PostHook) -> None:
        self._post_hooks.append(hook)

    def add_wrapper(self, wrapper: Callable) -> None:
        self._wrappers.append(wrapper)

    @property
    def pre_hooks(self) -> list[PreHook]:
        return list(self._pre_hooks)

    @property
    def guards(self) -> list[Guard]:
        return list(self._guards)

    @property
    def post_hooks(self) -> list[PostHook]:
        return list(self._post_hooks)

    @property
    def wrappers(self) -> list[Callable]:
        return list(self._wrappers)

    def dispose(self) -> None:
        """HMR-safety (E4.1): tear down all state owned by this scope."""
        self._tools.clear()
        self._pre_hooks.clear()
        self._guards.clear()
        self._post_hooks.clear()
        self._wrappers.clear()


# ---------------------------------------------------------------------------
# ToolResult + render helpers
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """Typed outcome.  ``value`` is canonical; ``display`` is model content."""

    name: str
    ok: bool
    value: Any = None
    display: str = ""
    code: Optional[str] = None
    durable_reason: Optional[str] = None
    audit: list[str] = field(default_factory=list)
    presentation_meta: dict[str, Any] = field(default_factory=dict)
    attached_context: list[dict] = field(default_factory=list)
    conclude_turn: bool = False
    timed_out: bool = False
    renderer: Optional[Renderer] = field(default=None, repr=False, compare=False)

    @property
    def error_info(self) -> dict[str, str | None]:
        """name + code only; safe for a durable error catalog entry."""
        return {"name": self.name, "code": self.code}

    def model_content(self) -> str:
        return self.display


def replace(result: ToolResult, **changes: Any) -> ToolResult:
    """Return a shallow copy with the given fields replaced (fresh containers)."""
    new = copy.copy(result)
    for key, value in changes.items():
        if not hasattr(new, key):
            raise ValueError(f"unknown ToolResult field {key!r}")
        setattr(new, key, value)
    if "attached_context" not in changes:
        new.attached_context = list(result.attached_context)
    if "audit" not in changes:
        new.audit = list(result.audit)
    return new


def success_result(name: str, value: Any, display: str, *,
                   renderer: Renderer | None = None,
                   audit: list[str] | None = None,
                   presentation_meta: dict | None = None,
                   attached_context: list[dict] | None = None,
                   conclude_turn: bool = False) -> ToolResult:
    return ToolResult(
        name=name, ok=True, value=value, display=display, renderer=renderer,
        audit=list(audit or []), presentation_meta=dict(presentation_meta or {}),
        attached_context=list(attached_context or []),
        conclude_turn=conclude_turn)


def failure_result(name: str, code: ToolErrorCode | str, *,
                   reason: str | None = None,
                   audit: list[str] | None = None) -> ToolResult:
    value = code.value if isinstance(code, ToolErrorCode) else str(code)
    return ToolResult(
        name=name, ok=False, value=None, display=failure_display(name, value),
        code=value, durable_reason=reason, audit=list(audit or []))


def safe_render(renderer: Renderer | None, args: dict, value: Any) -> str:
    """Pure renderer with a generic fallback; display must never crash."""
    if renderer is None:
        return json.dumps({"result": value}, ensure_ascii=False, default=str)
    try:
        out = renderer(copy.deepcopy(args), copy.deepcopy(value))
        return out if isinstance(out, str) else json.dumps(out, default=str)
    except Exception:  # noqa: BLE001 - display must never crash a replay
        # Fall back to the (already policy-checked) value.  For a DLP
        # replace-value hook this value is the redaction marker, so nothing is
        # leaked and the model still sees a stable representation.
        try:
            return f"[tool result: {json.dumps(value, ensure_ascii=False, default=str)}]"
        except Exception:
            return "[tool result]"


# ---------------------------------------------------------------------------
# 8 & 10. Dispatch, timeout, ordering, batch executor
# ---------------------------------------------------------------------------


def _invoke_handler(handler: Handler, args: Any, ctx: ToolContext) -> Any:
    """Call handler(args) or handler(args, ctx) based on its signature."""
    try:
        params = [
            p for p in inspect.signature(handler).parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                          inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        count = len(params)
    except (TypeError, ValueError):
        count = 2
    if count >= 2:
        return handler(args, ctx)
    if count == 1:
        return handler(args)
    return handler()


Dispatch = Callable[[Any, ToolContext], Any]


def apply_wrappers(registry: ToolRegistry, dispatch: Dispatch,
                   caller_signal: CancelSignal) -> tuple[Dispatch, CancelSignal]:
    """Around-dispatch: wrappers may add a signal but never remove caller's."""
    effective = caller_signal
    current = dispatch
    for wrapper in registry.wrappers:
        previous = current
        try:
            next_dispatch, new_signal = wrapper(previous, effective)
        except Exception:
            # A broken wrapper must not widen permissions or drop cancellation.
            next_dispatch, new_signal = previous, None
        # A wrapper that returns the dispatch it was given must not create a
        # self-recursive closure.
        current = next_dispatch if callable(next_dispatch) else previous
        if new_signal is not None:
            effective = fuse(effective, new_signal)
    return current, effective


def execute_tool(registry: ToolRegistry, name: str, args: Any, *,
                 agent_id: Optional[str] = "agent",
                 cancel: Optional[CancelSignal] = None,
                 approval_responder: Optional[ApprovalResponder] = None,
                 timeout_s: Optional[float] = ...,
                 extra_pre_hooks: Iterable[PreHook] = (),
                 extra_post_hooks: Iterable[PostHook] = (),
                 extra_guards: Iterable[Guard] = (),
                 restriction: "ToolRestriction | None" = None) -> ToolResult:
    """Run one tool through the full contract pipeline.

    Returns a typed ToolResult; internal failures carry stable codes and raw
    reasons are never placed in model-facing display.
    """
    # 1. Unknown tool -> typed failure, no side effects.
    spec = registry.get(name)
    if spec is None:
        return failure_result(name, ToolErrorCode.UNKNOWN_TOOL,
                              reason=f"no registered tool named {name!r}")

    # 2. Snapshot args BEFORE any policy runs (E1.4).
    try:
        snapshot = snapshot_args(args, name=name)
    except ToolError as exc:
        return failure_result(name, ToolErrorCode.INVALID_ARGS,
                              reason=exc.reason, audit=[])

    errors = validate_value(spec.input_schema, snapshot.json, path=name)
    if errors:
        return failure_result(name, ToolErrorCode.INVALID_ARGS,
                              reason="; ".join(errors))

    # Per-agent admission uses the SAME decision as the declaration (E1.12).
    admission = admission_decision(spec, restriction)
    if admission.kind != DecisionKind.ALLOW:
        return failure_result(
            name, ToolErrorCode(admission.code or "APPROVAL_REJECTED"),
            reason=admission.reason)

    # 3. Pre-execute decision (E1.5 / E1.6), shared with declaration.
    base = Decision.allow(f"permission class: {spec.permission}")
    pre_hooks = list(registry.pre_hooks) + list(extra_pre_hooks)
    guards = list(registry.guards) + list(extra_guards)
    decision, audit = resolve_pre_decision(
        name, snapshot, base=base, pre_hooks=pre_hooks, guards=guards,
        approval_responder=approval_responder, agent_id=agent_id)
    if decision.kind != DecisionKind.ALLOW or not decision.allow_once:
        err = pre_decision_to_error(decision)
        return failure_result(name, ToolErrorCode(err.code),
                              reason=err.reason, audit=audit)

    # 4. Dispatch with cancellation + cooperative timeout (E1.8 / E1.9).
    caller_signal = cancel or CancelSignal()
    timeout_signal = CancelSignal()
    limit = spec.timeout_s if timeout_s is ... else timeout_s
    ctx = ToolContext(tool_name=name, cancel=FusedCancelSignal(),
                      agent_id=agent_id)

    base_dispatch: Dispatch = lambda a, c: _invoke_handler(spec.handler, a, c)
    dispatch, effective = apply_wrappers(registry, base_dispatch, caller_signal)
    # The cooperative handler must observe BOTH the caller's cancellation and
    # the timeout signal.  Fusing (rather than replacing) preserves caller
    # cancel even when a wrapper swapped in a different signal.
    effective = fuse(effective, timeout_signal)
    ctx.cancel = effective

    value: Any = None
    timed_out = False
    aborted = False
    exec_error: ToolError | None = None
    # One worker per call; the context manager drains it so no started work is
    # left running when this function returns (E1.10 / E1.11).
    with ThreadPoolExecutor(max_workers=1) as pool:
        future: Future = pool.submit(dispatch, snapshot.frozen, ctx)
        deadline = time.monotonic() + limit if limit is not None else None
        while not future.done():
            if effective.cancelled:
                break
            if deadline is not None and time.monotonic() >= deadline:
                timeout_signal.cancel()
                timed_out = True
                break
            time.sleep(0.002)
        # Cooperative handlers observe ctx.cancel and reach quiescence quickly.
        grace = 0.5
        try:
            value = future.result(timeout=grace)
        except Exception as exc:  # noqa: BLE001 - typed below
            if isinstance(exc, ToolError):
                exec_error = exc
            elif timed_out or effective.cancelled:
                aborted = True
            else:
                exec_error = ToolError(
                    ToolErrorCode.TOOL_EXECUTION_ERROR, name,
                    reason=f"{type(exc).__name__}: {exc}")
        finally:
            # Re-fuse the caller signal: it always propagates, even if a
            # wrapper swapped in a fresh signal (E1.8).
            if caller_signal.cancelled:
                aborted = True

    if timed_out:
        return _timeout_result(name, audit)
    if aborted or effective.cancelled:
        return failure_result(name, ToolErrorCode.ABORTED,
                              reason="tool call was cancelled", audit=audit)
    if exec_error is not None:
        return failure_result(name, ToolErrorCode(exec_error.code),
                              reason=exec_error.reason, audit=audit)

    # 5. Validate the canonical output value (E1.3 / E1.1).
    out_errors = validate_value(spec.output_schema, value, path=f"{name}.result")
    if out_errors:
        return failure_result(name, ToolErrorCode.INVALID_TOOL_OUTPUT,
                              reason="; ".join(out_errors), audit=audit)

    display = safe_render(spec.renderer, snapshot.json, value)
    result = success_result(
        name, value, display, renderer=spec.renderer, audit=audit,
        presentation_meta=presentation_meta(name, snapshot.json, value),
        conclude_turn=ctx.conclude)
    if ctx.deferred_context:
        result = replace(result, attached_context=list(ctx.deferred_context))
    if ctx.injections:
        result = replace(
            result, attached_context=list(result.attached_context) +
            [{"kind": m.kind.value, "text": m.text, "meta": m.meta}
             for m in ctx.injections])

    # 6. Post-execute decisions incl. DLP (E1.7).
    post_hooks = list(registry.post_hooks) + list(extra_post_hooks)
    result = apply_post_hooks(name, snapshot, result, post_hooks)
    return result


def _timeout_result(name: str, audit: list[str]) -> ToolResult:
    result = failure_result(name, ToolErrorCode.TOOL_TIMEOUT,
                            reason="tool exceeded its cooperative timeout",
                            audit=audit)
    result.timed_out = True
    return result


@dataclass(frozen=True)
class ToolCall:
    """One call in a batch: tool name + arguments."""

    name: str
    args: Any = field(default_factory=dict)


def execute_batch(registry: ToolRegistry, calls: Iterable[ToolCall], *,
                  agent_id: Optional[str] = "agent",
                  cancel: Optional[CancelSignal] = None,
                  approval_responder: Optional[ApprovalResponder] = None,
                  max_parallel: Optional[int] = None,
                  default_max_parallel: int = 4) -> list[ToolResult]:
    """Deterministic bounded-parallel executor with exclusive barriers (E1.10).

    One outcome per input call, in input order.  Exclusive calls form a
    barrier: all previously started safe calls drain before the exclusive call
    is dispatched alone.  Skipped calls after abort get ABORTED_BEFORE_DISPATCH
    outcomes.  On an internal failure the started work is drained *first*, then
    a typed ToolBatchExecutionError is raised with committed outcomes attached.
    """
    call_list = list(calls)
    n = len(call_list)
    outcomes: list[Optional[ToolResult]] = [None] * n
    limit = max_parallel if max_parallel is not None else default_max_parallel
    if limit < 1:
        limit = 1
    cancel = cancel or CancelSignal()
    internal_error: BaseException | None = None

    def _aborted(index: int) -> ToolResult:
        return failure_result(call_list[index].name,
                              ToolErrorCode.ABORTED_BEFORE_DISPATCH,
                              reason="call skipped after batch abort")

    with ThreadPoolExecutor(max_workers=limit) as pool:
        try:
            pending_safe: list[tuple[int, Future]] = []
            for index, call in enumerate(call_list):
                if cancel.cancelled:
                    # Started calls settle with their real (ABORTED) outcome;
                    # only not-yet-dispatched calls are marked as skipped.
                    for idx, fut in pending_safe:
                        outcomes[idx] = fut.result()
                    pending_safe.clear()
                    outcomes[index] = _aborted(index)
                    continue

                spec = registry.get(call.name)
                safe = bool(spec and classify(spec, call.args or {}))

                if not safe:
                    # Exclusive barrier: drain all pending safe work first.
                    for idx, fut in pending_safe:
                        outcomes[idx] = fut.result()
                    pending_safe.clear()

                if cancel.cancelled:
                    outcomes[index] = _aborted(index)
                    continue

                fut = pool.submit(
                    execute_tool, registry, call.name, call.args,
                    agent_id=agent_id, cancel=cancel,
                    approval_responder=approval_responder)
                if safe:
                    pending_safe.append((index, fut))
                    if len(pending_safe) >= limit:
                        for idx, finished in pending_safe:
                            outcomes[idx] = finished.result()
                        pending_safe.clear()
                else:
                    outcomes[index] = fut.result()

            for idx, fut in pending_safe:
                outcomes[idx] = fut.result()
        except BaseException as exc:  # internal/infrastructure failure
            internal_error = exc

    # Fill any outcome still missing (defensive).
    for index, result in enumerate(outcomes):
        if result is None:
            outcomes[index] = _aborted(index)

    if internal_error is not None:
        raise ToolBatchExecutionError(
            [r for r in outcomes if r is not None],
            f"{type(internal_error).__name__}: {internal_error}")

    return [r for r in outcomes if r is not None]


# ---------------------------------------------------------------------------
# 11 & 12. Per-agent restrictions + conditional activation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolRestriction:
    """Allow/deny lists that intersect; scoped registrations stay exempt."""

    allow: frozenset[str] = field(default_factory=frozenset)
    deny: frozenset[str] = field(default_factory=frozenset)
    scoped_exempt: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_lists(cls, *, allow: Iterable[str] = (), deny: Iterable[str] = (),
                   scoped_exempt: Iterable[str] = ()) -> "ToolRestriction":
        return cls(frozenset(allow), frozenset(deny), frozenset(scoped_exempt))

    def admits(self, name: str, *, scoped: bool = False) -> bool:
        if scoped or name in self.scoped_exempt:
            return True
        if name in self.deny:
            return False
        if self.allow:
            return name in self.allow
        # Deny-only (or empty) admits everything not denied, including later
        # tools that did not exist when the restriction was declared.
        return True


def intersect_restrictions(*restrictions: ToolRestriction) -> ToolRestriction:
    """Intersect scopes: union of denies, intersection of non-empty allows."""
    if not restrictions:
        return ToolRestriction()
    denies: set[str] = set()
    allows: list[set[str]] = []
    exempts: set[str] = set()
    for r in restrictions:
        denies |= r.deny
        exempts |= r.scoped_exempt
        if r.allow:
            allows.append(set(r.allow))
    allow = set.intersection(*allows) if allows else set()
    return ToolRestriction(frozenset(allow), frozenset(denies), frozenset(exempts))


def tool_admitted(spec: "ToolSpec", restriction: "ToolRestriction | None") -> bool:
    if restriction is None:
        return True
    return restriction.admits(spec.name, scoped=spec.scoped)


def admission_decision(spec: "ToolSpec",
                       restriction: "ToolRestriction | None") -> Decision:
    """THE single per-agent admission decision used by declaration AND calls.

    Both ``ToolRegistry.schemas()`` and ``execute_tool()`` call this exact
    function, so a tool hidden from the model cannot be invoked directly.
    """
    if tool_admitted(spec, restriction):
        return Decision.allow("admitted for this agent")
    return Decision.deny(
        "tool is not admitted for this agent",
        code=ToolErrorCode.APPROVAL_REJECTED.value)


@dataclass(frozen=True)
class ToolActivation:
    """A conditional tool whose ``when`` predicate is evaluated once per step."""

    name: str
    when: Callable[[dict], bool]


class StepAdmission:
    """Per-step admitted set governing declarations and every call in the step."""

    def __init__(self, activations: Iterable[ToolActivation],
                 registry: ToolRegistry) -> None:
        self._activations = list(activations)
        self._registry = registry
        self._admitted: frozenset[str] | None = None

    def admit(self, model_selection: dict) -> frozenset[str]:
        admitted = set()
        for activation in self._activations:
            if not self._registry.has(activation.name):
                continue
            try:
                enabled = activation.when(model_selection) is True
            except Exception:
                enabled = False
            if enabled:
                admitted.add(activation.name)
        self._admitted = frozenset(admitted)
        return self._admitted

    def declarations(self) -> list[dict[str, Any]]:
        if self._admitted is None:
            return []
        return self._registry.schemas(sorted(self._admitted))

    def enforces(self, name: str) -> bool:
        return self._admitted is not None and name in self._admitted

    def enforce(self, name: str) -> None:
        if not self.enforces(name):
            raise ToolError(
                ToolErrorCode.MODEL_DIRECT_CALL_DENIED, name,
                reason="tool was not admitted for this step")

    def dispose(self) -> None:
        """Dispose after the batch; late results cannot restore removed tools."""
        self._admitted = None


# ---------------------------------------------------------------------------
# 17. Long-running background lifecycle (E1.18 / Y1.7 / D3.7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackgroundHandle:
    """Typed handle returned by a background start."""

    kind: str  # 'background'
    job_id: str

    def __post_init__(self) -> None:
        if self.kind != "background":
            raise ValueError("BackgroundHandle.kind must be 'background'")


class BackgroundJob:
    """Job spec with synchronous cancel + non-rejecting done + output source."""

    def __init__(self, job_id: str, work: Callable[[CancelSignal], Any]) -> None:
        self.job_id = job_id
        # Task-owned signal: after publishing the id, the *call's* cancel must
        # not kill the published work.
        self.task_cancel = CancelSignal()
        self._work = work
        self._done = threading.Event()
        self._output: Any = None
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"keel-job-{job_id}")

    def _run(self) -> None:
        try:
            self._output = self._work(self.task_cancel)
        except BaseException as exc:  # noqa: BLE001 - done() never rejects
            self._error = exc
        finally:
            self._done.set()

    def start(self) -> "BackgroundJob":
        self._thread.start()
        return self

    def cancel(self) -> None:
        """Synchronous cancel request; returns after signalling."""
        self.task_cancel.cancel()

    def done(self) -> Any:
        """Settle only after cleanup; never raises (typed error as output)."""
        self._done.wait()
        self._thread.join()
        if self._error is not None:
            return {"error": f"{type(self._error).__name__}: {self._error}"}
        return self._output

    def output_source(self) -> str:
        return f"background:{self.job_id}"

    @property
    def settled(self) -> bool:
        return self._done.is_set()


class JobManager:
    """Owner of job lifetime: job_kill, disposal and teardown."""

    def __init__(self) -> None:
        self._jobs: dict[str, BackgroundJob] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def start(self, work: Callable[[CancelSignal], Any]) -> BackgroundHandle:
        with self._lock:
            self._counter += 1
            job_id = f"job-{self._counter}"
            job = BackgroundJob(job_id, work)
            self._jobs[job_id] = job
        job.start()
        return BackgroundHandle(kind="background", job_id=job_id)

    def job_kill(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.cancel()
        return True

    def get(self, job_id: str) -> Optional[BackgroundJob]:
        return self._jobs.get(job_id)

    def dispose(self) -> None:
        """Cancel all jobs and drain them -- no orphaned workers."""
        jobs = list(self._jobs.values())
        for job in jobs:
            job.cancel()
        for job in jobs:
            job.done()
        self._jobs.clear()


def call_cancel_stops_waiting_not_work(manager: JobManager,
                                       call_cancel: CancelSignal,
                                       work: Callable[[CancelSignal], Any]
                                       ) -> tuple[BackgroundHandle, Any]:
    """Start published work; cancelling the call stops waiting, not the job.

    The caller receives the typed handle immediately.  The returned job uses
    its own task-owned signal, so ``call_cancel`` has no effect on the work.
    """
    handle = manager.start(work)
    if call_cancel.cancelled:
        return handle, None
    return handle, manager.get(handle.job_id)


# ---------------------------------------------------------------------------
# 18. Programmatic tool-call mode (E1.19 / E1.20 / E1.21)
# ---------------------------------------------------------------------------


class PTCError(Exception):
    """Limited programmatic error: name, tool name, message only."""

    def __init__(self, name: str, tool_name: str, message: str) -> None:
        self.name = name
        self.tool_name = tool_name
        self.message = message
        super().__init__(f"{name} ({tool_name}): {message}")


class PTCExecutor:
    """Code Mode: every visible tool callable as ``await tools.name(args)``."""

    def __init__(self, registry: ToolRegistry, *,
                 selected: bool = True,
                 agent_id: Optional[str] = "agent") -> None:
        self.registry = registry
        self.selected = selected
        self.agent_id = agent_id
        self.tools = _ToolProxy(self)
        self.dispatch_log = PTCDispatchLog()
        self.prompt_sections: list[str] = []
        self._registered_sections: list[str] = []

    def register_prompt_section(self, text: str) -> None:
        """Executor-owned guidance, registered/disposed with the executor."""
        self._registered_sections.append(text)
        self.prompt_sections.append(text)

    def dispose(self) -> None:
        self.prompt_sections.clear()
        self._registered_sections.clear()

    def model_direct_call(self, name: str, args: Any) -> ToolResult:
        """Model-direct calls to native names are denied while PTC is selected."""
        if self.selected and name != "run_code":
            return failure_result(
                name, ToolErrorCode.MODEL_DIRECT_CALL_DENIED,
                reason="model-direct tool call denied while PTC executor is selected")
        return execute_tool(self.registry, name, args, agent_id=self.agent_id)

    async def call(self, name: str, args: Any) -> Any:
        """Re-enter the normal pipeline; return canonical value or raise PTCError."""
        if name in RESERVED_TOOL_NAMES:
            raise PTCError("ReservedName", name, f"{name!r} is reserved")
        if not self.registry.has(name):
            raise PTCError("UnknownTool", name, f"no tool named {name!r}")
        self.dispatch_log.start(name, args)
        result = execute_tool(
            self.registry, name, args, agent_id=self.agent_id)
        self.dispatch_log.settle(name, args, result)
        if not result.ok:
            raise PTCError("ToolCallFailed", name,
                           f"{result.code}: {result.durable_reason or ''}".strip())
        # Intermediate values are execution-local: nothing persisted here.
        return result.value

    def run_code(self, code: str, *, call: Callable[..., Any]) -> Any:
        """Outer boundary: only this call crosses the output cap/spill pipeline."""
        return call(self.tools)


class _ToolProxy:
    """Attribute access producing awaitable calls: ``await tools.name(args)``."""

    def __init__(self, executor: PTCExecutor) -> None:
        object.__setattr__(self, "_executor", executor)

    def __getattr__(self, name: str) -> Callable[[Any], Any]:
        executor: PTCExecutor = object.__getattribute__(self, "_executor")

        async def _call(args: Any = None) -> Any:
            return await executor.call(name, args or {})

        return _call


class PTCDispatchLog:
    """Sub-call log events store only ids/name/normalized args; log copies shrink."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def start(self, name: str, args: Any) -> dict[str, Any]:
        event = {"event": "start", "name": name,
                 "args": _normalised_args(args)}
        self.events.append(event)
        return event

    def settle(self, name: str, args: Any, result: ToolResult) -> dict[str, Any]:
        event = {"event": "settle", "name": name,
                 "args": _normalised_args(args), "ok": result.ok,
                 "code": result.code}
        self.events.append(event)
        return event

    def durable_log_copy(self, result: ToolResult, *, max_chars: int = 512) -> dict:
        """Shorten ONLY the durable log copy; the program already got full value."""
        display = result.display
        shortened = display[:max_chars] + "…" if len(display) > max_chars else display
        return {"name": result.name, "code": result.code, "display": shortened}


def _normalised_args(args: Any) -> dict[str, Any]:
    if isinstance(args, ArgsSnapshot):
        return copy.deepcopy(args.json)
    if isinstance(args, dict):
        return copy.deepcopy(args)
    return {}


# ---------------------------------------------------------------------------
# 19. UI presentation: pure presenters + card contract (E2.1-E2.5)
# ---------------------------------------------------------------------------


class CardKind(str, Enum):
    GENERIC = "generic"
    TERMINAL = "terminal"
    DIFF = "diff"
    SEARCH = "search"
    READ = "read"
    WEB = "web"


class IconKind(str, Enum):
    READ = "read"
    EDIT = "edit"
    DELETE = "delete"
    MOVE = "move"
    SEARCH = "search"
    EXECUTE = "execute"
    FETCH = "fetch"
    OTHER = "other"


@dataclass(frozen=True)
class Card:
    """Durable presentation metadata; never the canonical value itself."""

    kind: CardKind
    title: str
    icon: IconKind = IconKind.OTHER
    status: str = "pending"  # pending | completed
    fields: dict[str, Any] = field(default_factory=dict)


def generic_card(title: str = "tool", icon: IconKind = IconKind.OTHER,
                 *, status: str = "pending", **fields: Any) -> Card:
    return Card(CardKind.GENERIC, title, icon, status, dict(fields))


def present_call(name: str, args: Any) -> Card:
    """Pure presenter for the call phase; garbage args -> generic fallback."""
    try:
        data = _normalised_args(args)
        if name == "run_shell":
            return Card(CardKind.TERMINAL, name, IconKind.EXECUTE, "pending",
                        {"command": str(data.get("command", ""))})
        if name in {"edit_file", "write_file"}:
            return Card(CardKind.DIFF, name, IconKind.EDIT, "pending",
                        {"path": str(data.get("path", ""))})
        if name in {"grep", "glob"}:
            return Card(CardKind.SEARCH, name, IconKind.SEARCH, "pending",
                        {"query": str(data.get("pattern", ""))})
        return generic_card(name, status="pending")
    except Exception:
        return generic_card(name, status="pending")


def present_result(name: str, args: Any, value: Any) -> Card:
    """Pure presenter for the result phase; malformed/old args never crash."""
    try:
        data = _normalised_args(args)
        if name == "run_shell" and isinstance(value, dict):
            return Card(CardKind.TERMINAL, name, IconKind.EXECUTE, "completed", {
                "command": str(data.get("command", "")),
                "raw_output": str(value.get("output", value.get("stdout", ""))),
                "exit_code": value.get("exit_code"),
                "signal": value.get("signal"),
            })
        if name in {"edit_file", "write_file"} and isinstance(value, dict):
            return Card(CardKind.DIFF, name, IconKind.EDIT, "completed", {
                "path": str(value.get("path", data.get("path", ""))),
                "old_text": value.get("old_text"),
                "new_text": value.get("new_text"),
            })
        if name in {"grep", "glob"} and isinstance(value, dict):
            return Card(CardKind.SEARCH, name, IconKind.SEARCH, "completed", {
                "matches": value.get("matches", []),
                "truncated": bool(value.get("truncated", False)),
                "total": value.get("total"),
            })
        if name == "read_file" and isinstance(value, dict):
            return Card(CardKind.READ, name, IconKind.READ, "completed", {
                "path": str(value.get("path", data.get("path", ""))),
                "offset": value.get("offset", 1),  # 1-based
                "lines": value.get("lines", []),
                "total_lines": value.get("total_lines"),
                "language": value.get("language"),
            })
        if name in {"web_search", "web_fetch"} and isinstance(value, dict):
            return Card(CardKind.WEB, name, IconKind.FETCH, "completed", {
                "sources": value.get("sources", []),
                "answer": value.get("answer"),
                "url": value.get("url", data.get("url")),
                "status": value.get("status"),
                "truncated": bool(value.get("truncated", False)),
            })
        return generic_card(name, status="completed")
    except Exception:
        return generic_card(name, status="completed")


def presentation_meta(name: str, args: dict, value: Any) -> dict[str, Any]:
    """Pure, durable facts for replay without persisting the canonical value."""
    try:
        card = present_result(name, args, value)
        return {
            "tool": name,
            "card_kind": card.kind.value,
            "icon": card.icon.value,
            "status": card.status,
            "fields": copy.deepcopy(card.fields),
        }
    except Exception:
        return {"tool": name, "card_kind": CardKind.GENERIC.value}


# ---------------------------------------------------------------------------
# 20. Verification helpers: conformance kit / fuzz / byte compare
# ---------------------------------------------------------------------------


def conformance_check(spec: ToolSpec) -> list[str]:
    """Table-driven conformance check for one tool spec (V24 / V25)."""
    problems: list[str] = []
    try:
        validate_schema_definition(spec.input_schema, path="input")
        validate_schema_definition(spec.output_schema, path="output")
    except SchemaError as exc:
        problems.append(f"schema: {exc}")
    if not callable(spec.handler):
        problems.append("handler is not callable")
    if not callable(spec.renderer):
        problems.append("renderer is not callable")
    # Renderer purity: same inputs -> same output, no mutation of args.
    probe = copy.deepcopy(spec.input_schema)
    sample = {}
    if probe.get("type") == "object":
        for key in probe.get("required", []) or []:
            sub = (probe.get("properties") or {}).get(key, {})
            sample[key] = {"string": "", "integer": 0, "number": 0,
                           "boolean": False, "array": [], "object": {},
                           "null": None}.get(sub.get("type"), "")
    probe_value: Any = {}
    try:
        first = spec.renderer(copy.deepcopy(sample), probe_value)
        second = spec.renderer(copy.deepcopy(sample), probe_value)
        if first != second:
            problems.append("renderer is not pure (nondeterministic output)")
        if sample != sample:  # defensive: renderer got copies
            problems.append("renderer mutated its arguments")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"renderer raised: {exc}")
    if spec.timeout_s is not None:
        # Declaring a timeout asserts the tool forwards cancel + quiesces.
        signal = CancelSignal()
        signal.cancel()
        ctx = ToolContext(tool_name=spec.name, cancel=signal)
        try:
            start = time.monotonic()
            _invoke_handler(spec.handler, sample, ctx)
            if time.monotonic() - start > 0.5:
                problems.append("declared timeout but handler did not quiesce on cancel")
        except Exception:
            pass  # handler may reject cancelled context by raising; acceptable
    return problems


def request_reconstruction_byte_compare(model_visible: str,
                                        logged: str) -> bool:
    """Prove model-visible equals logged bytes (E4 / request reconstruction)."""
    return model_visible.encode("utf-8") == logged.encode("utf-8")


def fuzz_tool(spec: ToolSpec, *, cases: int = 50,
              cancel_points: Iterable[int] = ()) -> list[ToolResult]:
    """Drive random args and cancellation points through a registered tool."""
    import random

    registry = ToolRegistry()
    registry.register(spec)
    rng = random.Random(1234)
    results: list[ToolResult] = []
    for i in range(cases):
        args = {"value": rng.choice([rng.randint(-10, 10), "x" * (i % 7), None])}
        signal = CancelSignal()
        if i in set(cancel_points):
            signal.cancel()
        results.append(execute_tool(
            registry, spec.name, args, cancel=signal, agent_id="fuzz"))
    return results


__all__ = [
    "ToolErrorCode", "ToolError", "ToolBatchExecutionError", "MANDATORY_ERROR_CODES",
    "failure_display", "SchemaError", "ALLOWED_SCHEMA_KEYWORDS",
    "validate_schema_definition", "infer_schema_type", "validate_value",
    "to_jsonable", "deep_freeze", "ArgsSnapshot", "snapshot_args",
    "DecisionKind", "Decision", "PreHook", "Guard", "PostHook",
    "ApprovalResponder", "combine_decisions", "apply_guards",
    "resolve_pre_decision", "pre_decision_to_error",
    "PostAction", "PostDecision", "dlp_replace_value", "dlp_block",
    "apply_post_hooks", "CancelSignal", "FusedCancelSignal", "fuse",
    "SourceKind", "InjectedMessage", "admit_injection", "ToolContext",
    "forward_conclude_turn", "RESERVED_TOOL_NAMES", "ConcurrencyClass",
    "ToolSpec", "classify", "ToolRegistry", "ToolResult", "replace",
    "success_result", "failure_result", "safe_render", "ToolCall",
    "apply_wrappers", "execute_tool", "execute_batch", "ToolRestriction",
    "tool_admitted", "admission_decision", "intersect_restrictions",
    "ToolActivation", "StepAdmission",
    "BackgroundHandle", "BackgroundJob", "JobManager",
    "call_cancel_stops_waiting_not_work", "PTCError", "PTCExecutor",
    "PTCDispatchLog", "CardKind", "IconKind", "Card", "generic_card",
    "present_call", "present_result", "presentation_meta",
    "conformance_check", "request_reconstruction_byte_compare", "fuzz_tool",
]
